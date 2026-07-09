"""Chunker golden tests (spec E2 Required tests): exact chunk boundaries and
overlap correctness, pinned to precomputed `cl100k_base` token counts, plus
url/title mapping across a chunk boundary (ported from DocChat's
`test_chunker.py`, adapted from page-tracking to url/title-tracking — HelpFlow
chunks one page at a time, so every chunk carries the SAME source_url/
page_title; the interesting assertion is that it stays constant across a
boundary the overlap logic creates, not that it changes).

Every word below is verified to encode to exactly ONE `cl100k_base` token both
alone and mid-sequence, so `count_tokens(" ".join(words)) == len(words)` —
chunks can be hand-computed exactly instead of asserted on fuzzy bounds.
"""

import pytest

from backend.ingestion.chunker import Chunk, chunk_page, count_tokens

# Sixteen distinct single-`cl100k_base`-token words (verified via `enc.encode`).
_W = ["cat", "dog", "bird", "fish", "lion", "wolf", "bear", "deer", "fox", "hawk",
      "crow", "duck", "frog", "moth", "worm", "camel"]

# Twenty-five distinct single-token words, for the hard-split test.
_W25 = ["cat", "dog", "bird", "fish", "lion", "wolf", "bear", "deer", "fox", "hawk",
        "crow", "duck", "frog", "moth", "worm", "camel", "apple", "bread", "chair",
        "table", "river", "stone", "cloud", "grass", "house"]

_URL = "https://example.com/docs/getting-started"
_TITLE = "Getting Started"


@pytest.fixture(autouse=True)
def _small_budget(monkeypatch):
    """CHUNK_TOKENS=10 / CHUNK_OVERLAP=3 — small enough to hand-compute exact
    chunk boundaries with a handful of words."""
    monkeypatch.setenv("CHUNK_TOKENS", "10")
    monkeypatch.setenv("CHUNK_OVERLAP", "3")
    from backend.utils.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _chunk(text: str) -> list[Chunk]:
    return chunk_page(source_url=_URL, page_title=_TITLE, text=text)


def test_count_tokens_matches_word_count_for_verified_words():
    assert count_tokens(" ".join(_W)) == len(_W)


def test_empty_text_yields_no_chunks():
    assert _chunk("") == []


def test_single_short_page_is_one_chunk():
    text = " ".join(_W[:4])  # 4 tokens, well under the 10-token budget
    assert _chunk(text) == [
        Chunk(chunk_index=0, text=text, source_url=_URL, page_title=_TITLE, token_count=4)
    ]


def test_overlap_carries_url_and_title_across_the_boundary():
    """Two paragraphs, budget=10 packs the first into chunk 0 with a third
    forcing chunk 1 to open with the overlap tail. Both chunks must report the
    SAME source_url/page_title (spec Req 4: carried through every split)."""
    p1, p2, p3 = " ".join(_W[0:5]), " ".join(_W[5:10]), " ".join(_W[10:15])
    text = f"{p1}\n\n{p2}\n\n{p3}"

    chunks = _chunk(text)

    assert len(chunks) == 2
    assert chunks[0] == Chunk(
        chunk_index=0, text=f"{p1}\n\n{p2}", source_url=_URL, page_title=_TITLE, token_count=10
    )
    # Chunk 1 = the overlap tail (p2) + the new paragraph (p3).
    assert chunks[1] == Chunk(
        chunk_index=1, text=f"{p2}\n\n{p3}", source_url=_URL, page_title=_TITLE, token_count=10
    )
    assert chunks[0].source_url == chunks[1].source_url == _URL
    assert chunks[0].page_title == chunks[1].page_title == _TITLE


def test_oversized_paragraph_hard_splits_on_raw_token_windows():
    """A single 25-token paragraph (no blank lines) with a 10-token budget must
    be hard-split into three windows, then packed+overlapped like any other
    unit. Every source word survives, in order, across the chunks."""
    text = " ".join(_W25)  # 25 tokens, well over the 10-token budget

    chunks = _chunk(text)

    assert len(chunks) == 3
    assert all(c.source_url == _URL and c.page_title == _TITLE for c in chunks)
    # No mid-word cut: every word from every chunk is one of the source words.
    for chunk in chunks:
        for word in chunk.text.split():
            assert word in _W25
    # Every source word appears somewhere, and in original order overall.
    seen = " ".join(c.text for c in chunks).split()
    assert set(_W25) <= set(seen)
    first_positions = {word: seen.index(word) for word in _W25}
    assert sorted(first_positions, key=first_positions.get) == _W25
    # Overlap: at least one word is duplicated across consecutive chunks.
    assert any(
        set(chunks[i].text.split()) & set(chunks[i + 1].text.split())
        for i in range(len(chunks) - 1)
    )


def test_chunking_is_deterministic():
    text = f"{' '.join(_W[0:5])}\n\n{' '.join(_W[5:10])}\n\n{' '.join(_W[10:15])}"
    assert _chunk(text) == _chunk(text)


def test_chunk_index_is_sequential():
    text = f"{' '.join(_W[0:5])}\n\n{' '.join(_W[5:10])}\n\n{' '.join(_W[10:15])}"
    chunks = _chunk(text)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
