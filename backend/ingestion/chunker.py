"""Token-aware chunking with url/title tracking (ARCHITECTURE §3.1 STEP 3,
spec E2 Req 4).

Ported from DocChat `ingestion/chunker.py`. CHUNK_TOKENS/CHUNK_OVERLAP
(config.py) are counted with tiktoken's `cl100k_base` — same tokenizer family
the embedding/answer models roughly approximate, so a "450-token chunk" means
something consistent regardless of which model ends up reading it. Packing
prefers whole paragraphs; a paragraph that alone exceeds the budget is
hard-split on raw token boundaries (not sentence-safe).

DocChat's chunker tracked PAGE NUMBERS across a multi-page PDF because one
`doc_id` could span many pages. HelpFlow's crawl unit is the opposite: one
`sources` row IS one page/URL (ARCHITECTURE §5.2), so there is no "page break
within a chunk" to track — `chunk_page()` runs once per page and every chunk
it emits carries the SAME `source_url`/`page_title` (spec Req 4: "carry
source_url/page_title/chunk_index through splits"). No page numbers — the
citation unit is the URL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from backend.utils.config import get_settings

# A run of 2+ newlines is a paragraph break; a single newline inside a
# paragraph is just a line-wrap and is folded to a space so chunk text reads
# as continuous prose.
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")
_INTRALINE_BREAK = re.compile(r"\s*\n\s*")


@lru_cache(maxsize=1)
def _encoding():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """`cl100k_base` token count of `text` — the single counting method shared
    by chunking and any caller that needs to reason about chunk size."""
    return len(_encoding().encode(text))


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    text: str
    source_url: str
    page_title: str
    token_count: int


@dataclass(frozen=True)
class _Unit:
    """One packable span of text."""

    text: str
    tokens: int


def _paragraphs(text: str) -> list[_Unit]:
    """Page text split into paragraph units (blank lines removed, each unit's
    internal line-wraps folded to spaces)."""
    units: list[_Unit] = []
    for para in _PARAGRAPH_BOUNDARY.split(text):
        cleaned = _INTRALINE_BREAK.sub(" ", para).strip()
        if cleaned:
            units.append(_Unit(text=cleaned, tokens=count_tokens(cleaned)))
    return units


def _hard_split(unit: _Unit, budget: int) -> list[_Unit]:
    """Cut an oversized paragraph into `budget`-token windows, raw token
    boundaries (no sentence awareness — spec Req 4's "hard-split")."""
    enc = _encoding()
    tokens = enc.encode(unit.text)
    pieces: list[_Unit] = []
    for start in range(0, len(tokens), budget):
        window = tokens[start : start + budget]
        pieces.append(_Unit(text=enc.decode(window), tokens=len(window)))
    return pieces


def _units_for_text(text: str, budget: int) -> list[_Unit]:
    units: list[_Unit] = []
    for para in _paragraphs(text):
        units.extend(_hard_split(para, budget) if para.tokens > budget else [para])
    return units


def _overlap_tail(units: list[_Unit], overlap_tokens: int) -> list[_Unit]:
    """The trailing units of a just-emitted chunk, ~`overlap_tokens` worth,
    carried into the next chunk for continuity."""
    tail: list[_Unit] = []
    total = 0
    for unit in reversed(units):
        if total >= overlap_tokens:
            break
        tail.insert(0, unit)
        total += unit.tokens
    return tail


def _finalize(units: list[_Unit], chunk_index: int, *, source_url: str, page_title: str) -> Chunk:
    return Chunk(
        chunk_index=chunk_index,
        text="\n\n".join(u.text for u in units),
        source_url=source_url,
        page_title=page_title,
        token_count=sum(u.tokens for u in units),
    )


def chunk_page(*, source_url: str, page_title: str, text: str) -> list[Chunk]:
    """Pack one page's `text` into ~`CHUNK_TOKENS`-token chunks with
    `CHUNK_OVERLAP` overlap (spec Req 4). Every chunk carries the same
    `source_url`/`page_title` and a `chunk_index` scoped to this page (0..N-1)
    — Qdrant point ids are `UUID5(source_id, chunk_index)`, and `source_id` is
    per-page, so `chunk_index` only needs to be unique within one page.
    """
    settings = get_settings()
    budget = settings.CHUNK_TOKENS
    overlap = settings.CHUNK_OVERLAP

    units = _units_for_text(text, budget)
    if not units:
        return []

    chunks: list[Chunk] = []
    current: list[_Unit] = []
    current_tokens = 0
    for unit in units:
        if current and current_tokens + unit.tokens > budget:
            chunks.append(
                _finalize(current, len(chunks), source_url=source_url, page_title=page_title)
            )
            current = _overlap_tail(current, overlap)
            current_tokens = sum(u.tokens for u in current)
        current.append(unit)
        current_tokens += unit.tokens
    if current:
        chunks.append(_finalize(current, len(chunks), source_url=source_url, page_title=page_title))
    return chunks
