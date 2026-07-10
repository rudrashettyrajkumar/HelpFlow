"""Answer agent — streamed, cited reply (ARCHITECTURE §3.2 STEP 5a / §6, spec E3 Req 7).

Streams through `llm_router.stream("answer", ...)` (env-driven flash primary → Groq
fallback), wrapped in `guardrails.guard_stream()` so a leaked prompt-block marker cuts
the stream before it reaches the client (E1's output rail).

Unlike every other agent in this codebase, this module does NOT catch and degrade its
own failures: by the time a mid-stream error happens, tokens may already have reached
the client, so there is no "safe default" to substitute — the failure must propagate to
`chat_pipeline`, which turns it into the one SSE `error` event (errors-degrade-never-break
enforced one layer up).

Prompt assembly (§6): system = `answerer_identity.md` (tenant name/tone injected) +
`citation_rules.md`; user turn = `[CONTEXT]` (numbered, citation-labeled chunks) +
`[HISTORY]` (last 6 turns) + `[QUESTION]`. These bracketed labels are also
`guard_stream`'s leak signature — the answerer must never see them spelled any other way.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from backend.agents.retrieval_agent import RetrievedChunk
from backend.utils import llm_router
from backend.utils.guardrails import guard_stream

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_HISTORY_TURNS = 6

# Matches citation markers the model emits inline, e.g. "...ships in 3-5 days [1][3]."
_CITATION_RE = re.compile(r"\[(\d+)\]")

_IDENTITY_CACHE: str | None = None
_CITATION_RULES_CACHE: str | None = None


def _read(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _identity_template() -> str:
    global _IDENTITY_CACHE
    if _IDENTITY_CACHE is None:
        _IDENTITY_CACHE = _read("answerer_identity.md")
    return _IDENTITY_CACHE


def _citation_rules() -> str:
    global _CITATION_RULES_CACHE
    if _CITATION_RULES_CACHE is None:
        _CITATION_RULES_CACHE = _read("citation_rules.md")
    return _CITATION_RULES_CACHE


def system_prompt(business_name: str, business_tone: str) -> str:
    """Identity (tenant name/tone injected) + citation rules, in that order (§6)."""
    identity = _identity_template().format(business_name=business_name, business_tone=business_tone)
    return f"{identity}\n\n{_citation_rules()}"


def _format_context(chunks: list[RetrievedChunk], low_relevance: bool) -> str:
    if not chunks:
        return "(no relevant content found)"
    body = "\n\n".join(f"[{c.n}] {c.citation_label}\n{c.text}" for c in chunks)
    if low_relevance:
        return f"(marked low relevance — this material may not answer the question)\n\n{body}"
    return body


def _format_history(history: list[dict[str, Any]]) -> str:
    turns = history[-_HISTORY_TURNS:]
    lines: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "user")).strip() or "user"
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior turns)"


def user_turn(
    chunks: list[RetrievedChunk], history: list[dict[str, Any]], question: str, low_relevance: bool
) -> str:
    """Assemble `[CONTEXT]` + `[HISTORY]` + `[QUESTION]` in that fixed order (§6)."""
    return (
        f"[CONTEXT]\n{_format_context(chunks, low_relevance)}\n\n"
        f"[HISTORY]\n{_format_history(history)}\n\n"
        f"[QUESTION]\n{question}"
    )


def build_messages(
    chunks: list[RetrievedChunk],
    history: list[dict[str, Any]],
    question: str,
    low_relevance: bool,
    business_name: str,
    business_tone: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt(business_name, business_tone)},
        {"role": "user", "content": user_turn(chunks, history, question, low_relevance)},
    ]


def stream_answer(
    chunks: list[RetrievedChunk],
    history: list[dict[str, Any]],
    question: str,
    low_relevance: bool,
    *,
    business_name: str = "Our team",
    business_tone: str = "friendly and professional",
) -> AsyncIterator[str]:
    """Guarded answer token stream for the assembled prompt (spec Req 7).

    Any gateway/provider failure or `GuardrailTripped` propagates to the caller.
    """
    messages = build_messages(
        chunks, history, question, low_relevance, business_name, business_tone
    )
    return guard_stream(llm_router.stream("answer", messages))


def cited_sources(chunks: list[RetrievedChunk], answer_text: str) -> list[dict[str, object]]:
    """The `sources` SSE event payload (spec Req 7).

    `cited` is true only for chunks whose `[n]` actually appears in the final answer
    text — a citation number the model never used stays `cited: false` rather than
    being dropped, so the widget can still show it dimmed.
    """
    cited_numbers = {int(m) for m in _CITATION_RE.findall(answer_text)}
    return [
        {
            "n": chunk.n,
            "source_url": chunk.source_url,
            "page_title": chunk.page_title,
            "snippet": chunk.text[:300],
            "score": chunk.score,
            "cited": chunk.n in cited_numbers,
        }
        for chunk in chunks
    ]
