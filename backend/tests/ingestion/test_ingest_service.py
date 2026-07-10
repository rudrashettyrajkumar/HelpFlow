"""ingest_service tests (spec E2 Required tests): progress event sequence with
mocked crawler/extractor/embed/qdrant/supabase, and rollback-on-failure
deleting prior points + flipping every touched source row to 'error'.
`discover`/`extract_page`/`chunk_page` are patched to fixed fakes so these
tests are independent of their own (separately tested) behavior.
"""

import contextlib
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.ingestion import ingest_service
from backend.ingestion.chunker import Chunk
from backend.ingestion.extractor import ExtractResult
from backend.services.embed_signature import EmbeddingError

_TENANT_ID = str(uuid.uuid4())
_URLS = ["https://example.com/a", "https://example.com/b"]

# Each page extracts to one chunk; 2 pages -> 2 chunks total.
_EXTRACT_RESULTS = {
    _URLS[0]: ExtractResult(text="content of page a " * 20, title="Page A"),
    _URLS[1]: ExtractResult(text="content of page b " * 20, title="Page B"),
}


def _fake_chunks_for(url: str, title: str) -> list[Chunk]:
    return [
        Chunk(
            chunk_index=0,
            text=f"chunk of {url}",
            source_url=url,
            page_title=title,
            token_count=5,
        )
    ]


@pytest.fixture(autouse=True)
def _batch_size(monkeypatch):
    """Force each embed batch to hold exactly 1 chunk so 2 chunks -> 2 batches
    (progress sequence has more than one embedding event)."""
    monkeypatch.setenv("EMBED_BATCH_SIZE", "1")
    from backend.utils.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fake_qdrant():
    client = AsyncMock()
    client.upsert = AsyncMock()
    client.delete = AsyncMock()
    return client


async def _collect(agen):
    return [event async for event in agen]


@contextlib.contextmanager
def _patches(*, qdrant, embed_mock, supabase_source_ids=None):
    """Common patch set: discover -> _URLS; extract_page -> per-url fixture;
    chunk_page -> one fake chunk per page; source-row insert hands back
    deterministic uuids without touching real Supabase."""
    source_ids = iter(supabase_source_ids or [str(uuid.uuid4()) for _ in _URLS])
    url_to_source_id: dict[str, str] = {}

    async def fake_extract(url):
        return _EXTRACT_RESULTS[url]

    async def fake_insert(tenant_id, url):
        sid = next(source_ids)
        url_to_source_id[url] = sid
        return sid

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(ingest_service, "discover", AsyncMock(return_value=_URLS)))
        stack.enter_context(patch.object(ingest_service, "extract_page", fake_extract))
        stack.enter_context(
            patch.object(
                ingest_service,
                "chunk_page",
                lambda *, source_url, page_title, text: _fake_chunks_for(source_url, page_title),
            )
        )
        stack.enter_context(patch.object(ingest_service, "_insert_source_row", fake_insert))
        stack.enter_context(patch.object(ingest_service, "get_qdrant", return_value=qdrant))
        stack.enter_context(patch.object(ingest_service.embed_signature, "embed", embed_mock))
        stack.enter_context(patch.object(ingest_service, "_mark_ready", AsyncMock()))
        stack.enter_context(patch.object(ingest_service, "_mark_error", AsyncMock()))
        yield url_to_source_id


async def test_happy_path_progress_event_sequence():
    qdrant = _fake_qdrant()
    embed_mock = AsyncMock(side_effect=lambda texts, *a, **kw: [[0.1, 0.2] for _ in texts])

    with _patches(qdrant=qdrant, embed_mock=embed_mock):
        events = await _collect(ingest_service.run_ingestion(tenant_id=_TENANT_ID, url="https://example.com/"))

    stages = [e["stage"] for e in events]
    assert stages == ["discovering", "fetching", "fetching", "embedding", "embedding", "ready"]
    assert events[-1] == {"stage": "ready", "pages": 2, "chunks": 2}
    assert events[1]["total"] == 2
    assert {events[1]["done"], events[2]["done"]} == {1, 2}
    assert qdrant.upsert.await_count == 2  # 2 batches of 1 chunk each
    assert qdrant.delete.await_count == 0

    # Spot-check one upserted point's payload matches ARCHITECTURE §5.1 exactly.
    first_call_points = qdrant.upsert.await_args_list[0].kwargs["points"]
    payload = first_call_points[0].payload
    assert set(payload) == {
        "tenant_id", "source_id", "source_url", "page_title", "chunk_index", "text", "created_at",
    }
    assert payload["tenant_id"] == _TENANT_ID
    assert isinstance(payload["created_at"], float)


async def test_mid_embed_failure_rolls_back_and_emits_error():
    qdrant = _fake_qdrant()

    call_count = 0

    async def _embed_fails_second_batch(texts, *a, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [[0.1, 0.2] for _ in texts]
        raise EmbeddingError("gateway down")  # the batch call AND its one retry

    with _patches(qdrant=qdrant, embed_mock=AsyncMock(side_effect=_embed_fails_second_batch)):
        events = await _collect(ingest_service.run_ingestion(tenant_id=_TENANT_ID, url="https://example.com/"))

    assert events[-1]["stage"] == "error"
    assert not any(e["stage"] == "ready" for e in events)

    # First batch's points were upserted; the failure must roll ALL of this
    # crawl's touched source_ids back (spec Req 5: "no half-ingested tenant").
    assert qdrant.upsert.await_count == 1
    qdrant.delete.assert_awaited_once()

    # Embed was retried exactly once for the failing batch.
    assert call_count == 3  # batch 1 (ok) + batch 2 (fail) + batch 2 retry (fail)


async def test_upsert_failure_rolls_back_and_emits_error():
    qdrant = _fake_qdrant()
    qdrant.upsert = AsyncMock(side_effect=[None, RuntimeError("qdrant unavailable")])
    embed_mock = AsyncMock(side_effect=lambda texts, *a, **kw: [[0.1, 0.2] for _ in texts])

    with _patches(qdrant=qdrant, embed_mock=embed_mock):
        events = await _collect(ingest_service.run_ingestion(tenant_id=_TENANT_ID, url="https://example.com/"))

    assert events[-1]["stage"] == "error"
    assert not any(e["stage"] == "ready" for e in events)
    qdrant.delete.assert_awaited_once()


async def test_extraction_failure_on_one_page_does_not_abort_the_crawl():
    """One page fails extraction (spec Req 3: 'one failed page never aborts
    the crawl') — the other page still ingests normally."""
    qdrant = _fake_qdrant()
    embed_mock = AsyncMock(side_effect=lambda texts, *a, **kw: [[0.1, 0.2] for _ in texts])

    async def flaky_extract(url):
        if url == _URLS[0]:
            return None  # unextractable
        return _EXTRACT_RESULTS[url]

    with (
        patch.object(ingest_service, "discover", AsyncMock(return_value=_URLS)),
        patch.object(ingest_service, "extract_page", flaky_extract),
        patch.object(
            ingest_service,
            "chunk_page",
            lambda *, source_url, page_title, text: _fake_chunks_for(source_url, page_title),
        ),
        patch.object(
            ingest_service,
            "_insert_source_row",
            AsyncMock(side_effect=lambda t, u: str(uuid.uuid4())),
        ),
        patch.object(ingest_service, "get_qdrant", return_value=qdrant),
        patch("backend.services.embed_signature.embed", embed_mock),
        patch.object(ingest_service, "_mark_ready", AsyncMock()) as mark_ready,
        patch.object(ingest_service, "_mark_error", AsyncMock()) as mark_error,
    ):
        events = await _collect(ingest_service.run_ingestion(tenant_id=_TENANT_ID, url="https://example.com/"))

    assert events[-1] == {"stage": "ready", "pages": 2, "chunks": 1}
    mark_error.assert_awaited_once()  # the failed page
    mark_ready.assert_awaited_once()  # the successful page
    assert qdrant.delete.await_count == 0


async def test_no_crawlable_pages_emits_error_without_touching_qdrant():
    qdrant = _fake_qdrant()

    with (
        patch.object(ingest_service, "discover", AsyncMock(return_value=[])),
        patch.object(ingest_service, "get_qdrant", return_value=qdrant),
    ):
        events = await _collect(ingest_service.run_ingestion(tenant_id=_TENANT_ID, url="https://example.com/"))

    assert events == [
        {"stage": "discovering"},
        {"stage": "error", "detail": "No crawlable pages were found at that URL."},
    ]
    qdrant.upsert.assert_not_awaited()
