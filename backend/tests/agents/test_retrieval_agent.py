"""Retrieval agent: the tenant_id filter is present on every Qdrant search (the ONE
choke point), cross-tenant isolation, and the degrade-never-break paths (spec E3
Required tests / ARCHITECTURE §5.1)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.agents.retrieval_agent import retrieve
from backend.services.embed_signature import EmbeddingError


def _point(id_, text, source_url, score, tenant_id):
    return SimpleNamespace(
        id=id_,
        score=score,
        payload={
            "tenant_id": tenant_id,
            "source_id": "src-1",
            "source_url": source_url,
            "page_title": "Some Page",
            "chunk_index": 0,
            "text": text,
        },
    )


async def test_every_search_call_carries_the_tenant_filter():
    captured_filters = []

    async def fake_search(*, collection_name, query_vector, query_filter, limit):
        captured_filters.append(query_filter)
        return [_point("p1", "hello", "https://a.example/x", 0.9, "tenant-a")]

    fake_qdrant = SimpleNamespace(search=fake_search)

    with (
        patch("backend.agents.retrieval_agent.embed", AsyncMock(return_value=[[0.1] * 768])),
        patch("backend.agents.retrieval_agent.get_qdrant", return_value=fake_qdrant),
    ):
        result = await retrieve(["hello"], "tenant-a")

    assert len(captured_filters) == 1
    must = captured_filters[0].must
    assert len(must) == 1
    assert must[0].key == "tenant_id"
    assert must[0].match.value == "tenant-a"
    assert result.chunks[0].source_url == "https://a.example/x"


async def test_cross_tenant_isolation_tenant_a_cannot_see_tenant_b_chunks():
    """The fake Qdrant only ever returns points matching the filter's tenant_id —
    simulating real Qdrant server-side filtering — proving tenant B's data is never
    reachable through tenant A's query."""

    points_by_tenant = {
        "tenant-a": [_point("a1", "a content", "https://a.example", 0.9, "tenant-a")],
        "tenant-b": [_point("b1", "b content", "https://b.example", 0.9, "tenant-b")],
    }

    async def fake_search(*, collection_name, query_vector, query_filter, limit):
        tenant_id = query_filter.must[0].match.value
        return points_by_tenant[tenant_id]

    fake_qdrant = SimpleNamespace(search=fake_search)

    with (
        patch("backend.agents.retrieval_agent.embed", AsyncMock(return_value=[[0.1] * 768])),
        patch("backend.agents.retrieval_agent.get_qdrant", return_value=fake_qdrant),
    ):
        result_a = await retrieve(["question"], "tenant-a")

    urls = {c.source_url for c in result_a.chunks}
    assert urls == {"https://a.example"}
    assert "https://b.example" not in urls


async def test_empty_queries_degrades_to_empty_result_without_calling_qdrant():
    fake_qdrant = SimpleNamespace(search=AsyncMock())
    with patch("backend.agents.retrieval_agent.get_qdrant", return_value=fake_qdrant):
        result = await retrieve([], "tenant-a")
    assert result.chunks == []
    assert result.low_relevance is True
    fake_qdrant.search.assert_not_called()


async def test_embedding_failure_degrades_to_low_relevance_empty_result():
    with patch(
        "backend.agents.retrieval_agent.embed", AsyncMock(side_effect=EmbeddingError("no credit"))
    ):
        result = await retrieve(["hello"], "tenant-a")
    assert result.chunks == []
    assert result.low_relevance is True


async def test_all_searches_failing_degrades_to_low_relevance_empty_result():
    async def failing_search(*, collection_name, query_vector, query_filter, limit):
        raise RuntimeError("qdrant unreachable")

    fake_qdrant = SimpleNamespace(search=failing_search)
    with (
        patch("backend.agents.retrieval_agent.embed", AsyncMock(return_value=[[0.1] * 768])),
        patch("backend.agents.retrieval_agent.get_qdrant", return_value=fake_qdrant),
    ):
        result = await retrieve(["hello"], "tenant-a")
    assert result.chunks == []
    assert result.low_relevance is True


async def test_best_score_below_threshold_flags_low_relevance():
    async def fake_search(*, collection_name, query_vector, query_filter, limit):
        return [_point("p1", "weak match", "https://a.example", 0.05, "tenant-a")]

    fake_qdrant = SimpleNamespace(search=fake_search)
    with (
        patch("backend.agents.retrieval_agent.embed", AsyncMock(return_value=[[0.1] * 768])),
        patch("backend.agents.retrieval_agent.get_qdrant", return_value=fake_qdrant),
    ):
        result = await retrieve(["hello"], "tenant-a")
    assert result.low_relevance is True
    assert len(result.chunks) == 1
