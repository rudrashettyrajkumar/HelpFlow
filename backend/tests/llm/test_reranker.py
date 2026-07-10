"""`llm/reranker.py` — FlashRank rerank, degrade-to-noop (spec E4 Req 1)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.llm import reranker


@dataclass(frozen=True)
class _Chunk:
    n: int
    text: str


def _chunks():
    return [_Chunk(n=1, text="alpha"), _Chunk(n=2, text="beta"), _Chunk(n=3, text="gamma")]


def _settings(enabled: bool):
    return type("S", (), {"RERANK_ENABLED": enabled})()


async def test_disabled_returns_chunks_unchanged(monkeypatch):
    monkeypatch.setattr(reranker, "get_settings", lambda: _settings(False))
    result = await reranker.rerank("question", _chunks())
    assert result == _chunks()


async def test_empty_chunks_short_circuits():
    result = await reranker.rerank("question", [])
    assert result == []


async def test_ranker_unavailable_degrades_to_original_order(monkeypatch):
    monkeypatch.setattr(reranker, "get_settings", lambda: _settings(True))
    monkeypatch.setattr(reranker, "_get_ranker", lambda: None)
    result = await reranker.rerank("question", _chunks())
    assert result == _chunks()


async def test_scoring_reorders_and_renumbers_by_rank(monkeypatch):
    monkeypatch.setattr(reranker, "get_settings", lambda: _settings(True))
    monkeypatch.setattr(reranker, "_get_ranker", lambda: object())

    def fake_score(question, chunks):
        # Reverse rank order: chunk index 2 (gamma) is the best match.
        return [(2, 0.9), (0, 0.5), (1, 0.1)]

    monkeypatch.setattr(reranker, "_score", fake_score)
    result = await reranker.rerank("question", _chunks())

    assert [c.text for c in result] == ["gamma", "alpha", "beta"]
    assert [c.n for c in result] == [1, 2, 3]  # renumbered 1..k in the NEW order


async def test_scoring_failure_degrades_to_original_order(monkeypatch):
    monkeypatch.setattr(reranker, "get_settings", lambda: _settings(True))
    monkeypatch.setattr(reranker, "_get_ranker", lambda: object())

    async def failing_to_thread(fn, *args):
        raise RuntimeError("onnx crashed")

    monkeypatch.setattr(reranker.asyncio, "to_thread", failing_to_thread)
    result = await reranker.rerank("question", _chunks())
    assert result == _chunks()
