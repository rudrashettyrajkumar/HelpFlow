"""Chat pipeline — the async orchestrator (ARCHITECTURE §3.2, spec E3 Req 1-10).

The pipeline order is LAW: conversation load (done by the caller, `api/chat.py`,
before rate-limit checks) → human_assigned guard → guardrail → route/rewrite →
retrieve (route=retrieve only) → escalation decision → answer OR escalate → persist.
Two deterministic early exits before any answer: the `human_assigned` guard
(invariant #5 — the AI must NEVER answer a human-assigned conversation) and the
guardrail (invariant #3). Both run before any LLM call — tested with
`assert_no_llm_calls`.

`prepare_turn()` makes every decision (never streams, never persists); `_run_turn()`
is the single core that streams the answer AND schedules every persistence side
effect as a `BackgroundTasks` job (never blocks the response). `run_chat_stream()`
and `run_chat_once()` are thin adapters over the SAME `_run_turn()` core — one for
`POST /chat/stream` (SSE), one for `POST /chat` (n8n/WhatsApp's non-streaming
sibling) — so the escalation truth table and persistence logic exist in exactly one
place, never duplicated between the two endpoints.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks

from backend.agents import answer_agent, escalation, rewrite_agent
from backend.agents.retrieval_agent import RetrievedChunk, retrieve
from backend.channels import conversation_store
from backend.utils.config import get_settings
from backend.utils.guardrails import check_input, deflection
from backend.utils.sse import PING, format_event, format_token, with_heartbeat

_log = logging.getLogger("helpflow.chat_pipeline")

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_FRIENDLY_STREAM_ERROR = "Something went wrong while generating the answer. Please try again."


# --------------------------------------------------------------------------- decision


@dataclass
class TurnContext:
    """Everything `_run_turn` needs — the output of every pre-answer decision."""

    kind: str  # "human_turn" | "guardrail" | "no_sources" | "answer" | "escalate"
    conversation: dict[str, Any]
    history: list[dict[str, Any]] = field(default_factory=list)
    canned_text: str | None = None
    chunks: list[RetrievedChunk] = field(default_factory=list)
    low_relevance: bool = False
    route: str | None = None
    reason: str | None = None
    new_streak: int = 0


def _sensitive_intents(tenant: dict[str, Any]) -> frozenset[str]:
    """Per-tenant override (`tenants.sensitive_intents`) if set, else the env default."""
    per_tenant = tenant.get("sensitive_intents") or []
    if per_tenant:
        return frozenset(s.lower() for s in per_tenant)
    return get_settings().sensitive_intents


async def prepare_turn(
    *, tenant: dict[str, Any], conversation: dict[str, Any], message: str
) -> TurnContext:
    """Steps 0(guard)-4 of §3.2: every decision, zero side effects, zero streaming.

    Order matters for the required tests: the human_assigned guard and the
    guardrail check BOTH return before `rewrite_agent`/history are ever touched —
    the only way to guarantee zero LLM-router calls on those two paths.
    """
    if conversation["status"] == "human_assigned":
        return TurnContext(kind="human_turn", conversation=conversation)

    if check_input(message) is not None:
        return TurnContext(kind="guardrail", conversation=conversation, canned_text=deflection())

    history = await conversation_store.recent_history(conversation["id"])
    rw = await rewrite_agent.rewrite(
        message,
        history,
        tenant_name=tenant.get("name") or "the business",
        sensitive_intents=_sensitive_intents(tenant),
    )

    chunks: list[RetrievedChunk] = []
    low_relevance = False
    if rw.route == "retrieve":
        ready = await conversation_store.count_ready_sources(str(tenant["id"]))
        if ready == 0:
            return TurnContext(
                kind="no_sources", conversation=conversation, history=history, route=rw.route
            )
        result = await retrieve(rw.queries, str(tenant["id"]))
        chunks = result.chunks
        low_relevance = result.low_relevance

    decision = escalation.decide(
        route=rw.route,
        handoff_reason=rw.handoff_reason,
        low_relevance=low_relevance,
        low_conf_streak=conversation["low_conf_streak"],
    )

    if decision.action == "escalate":
        return TurnContext(
            kind="escalate",
            conversation=conversation,
            history=history,
            chunks=chunks,
            route=rw.route,
            reason=decision.reason,
            new_streak=decision.new_streak,
        )

    return TurnContext(
        kind="answer",
        conversation=conversation,
        history=history,
        chunks=chunks,
        low_relevance=low_relevance,
        route=rw.route,
        new_streak=decision.new_streak,
    )


# --------------------------------------------------------------------------- canned text


def _load_variants(filename: str) -> tuple[str, ...]:
    """`---`-separated canned reply variants from a prompts/*.md file (guardrails.md's
    pattern, generalized) — random pick avoids the reply feeling scripted."""
    raw = (_PROMPTS_DIR / filename).read_text(encoding="utf-8")
    parts = (p.strip() for p in raw.split("\n---\n"))
    return tuple(p for p in parts if p)


_HANDOFF_CACHE: tuple[str, ...] | None = None
_NO_SOURCES_CACHE: str | None = None


def _handoff_message() -> str:
    import random

    global _HANDOFF_CACHE
    if _HANDOFF_CACHE is None:
        _HANDOFF_CACHE = _load_variants("handoff_message.md") or (
            "Let me connect you with a person from our team.",
        )
    return random.choice(_HANDOFF_CACHE)  # noqa: S311 — not cryptographic, just variety


def _no_sources_message() -> str:
    global _NO_SOURCES_CACHE
    if _NO_SOURCES_CACHE is None:
        _NO_SOURCES_CACHE = (_PROMPTS_DIR / "no_sources.md").read_text(encoding="utf-8").strip()
    return _NO_SOURCES_CACHE


def _tenant_tone(tenant: dict[str, Any]) -> str:
    widget_config = tenant.get("widget_config") or {}
    if isinstance(widget_config, dict):
        return widget_config.get("tone") or "friendly and professional"
    return "friendly and professional"


# --------------------------------------------------------------------------- persistence


async def _persist_human_turn(conversation_id: str, message: str) -> None:
    await conversation_store.insert_message(conversation_id, role="user", body=message)
    await conversation_store.insert_event(conversation_id, "human_turn")
    await conversation_store.touch_last_activity(conversation_id)


async def _persist_canned_answer(conversation_id: str, message: str, reply: str) -> None:
    """The `no_sources` exit: a real (canned) answer, so it IS persisted — unlike the
    guardrail exit, which is never stored (invariant #3)."""
    await conversation_store.insert_message(conversation_id, role="user", body=message)
    await conversation_store.insert_message(
        conversation_id, role="assistant", body=reply, confidence="low"
    )
    await conversation_store.insert_event(conversation_id, "answered")
    await conversation_store.touch_last_activity(conversation_id)


async def _persist_answer(
    conversation_id: str,
    message: str,
    answer_text: str,
    sources: list[dict[str, Any]],
    confidence: str,
    new_streak: int,
) -> None:
    await conversation_store.insert_message(conversation_id, role="user", body=message)
    await conversation_store.insert_message(
        conversation_id,
        role="assistant",
        body=answer_text,
        citations=sources,
        confidence=confidence,
    )
    await conversation_store.update_low_conf_streak(conversation_id, new_streak)
    await conversation_store.insert_event(conversation_id, "answered")
    await conversation_store.touch_last_activity(conversation_id)


async def _notify_handoff(conversation_id: str, tenant_id: str, reason: str) -> None:
    """Fire-and-forget `POST {N8N_HANDOFF_URL}/webhook/handoff` (spec Req 8): n8n being
    down/unconfigured must never break the customer's chat — logged, not raised."""
    settings = get_settings()
    if not settings.N8N_HANDOFF_URL:
        _log.warning(
            "handoff webhook not configured; escalation logged, not notified",
            extra={"conversation_id": conversation_id},
        )
        return
    try:
        async with httpx.AsyncClient(timeout=3.0) as http:
            resp = await http.post(
                f"{settings.N8N_HANDOFF_URL.rstrip('/')}/webhook/handoff",
                headers={"X-Handoff-Token": settings.HANDOFF_TOKEN or ""},
                json={
                    "conversation_id": conversation_id,
                    "tenant_id": tenant_id,
                    "reason": reason,
                    "transcript_url": None,
                },
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — n8n down must not break the customer's chat
        _log.warning(
            "handoff webhook failed", extra={"conversation_id": conversation_id, "error": str(exc)}
        )


async def _persist_escalation(
    conversation: dict[str, Any], message: str, handoff_text: str, reason: str, new_streak: int
) -> None:
    conversation_id = str(conversation["id"])
    tenant_id = str(conversation["tenant_id"])
    await conversation_store.insert_message(conversation_id, role="user", body=message)
    await conversation_store.insert_message(
        conversation_id, role="assistant", body=handoff_text, confidence="escalated"
    )
    await conversation_store.update_low_conf_streak(conversation_id, new_streak)
    await conversation_store.guarded_transition(
        conversation_id, expected_status="ai_handling", new_status="needs_human"
    )
    await conversation_store.insert_escalation(conversation_id, reason)
    await conversation_store.insert_event(conversation_id, "escalated", {"reason": reason})
    await conversation_store.touch_last_activity(conversation_id)
    await _notify_handoff(conversation_id, tenant_id, reason)


# --------------------------------------------------------------------------- the core


async def _run_turn(
    ctx: TurnContext, tenant: dict[str, Any], message: str, background_tasks: BackgroundTasks
) -> AsyncIterator[dict[str, Any]]:
    """Yield abstract turn events (`{"type": ...}`) — format-agnostic so both the SSE
    and non-streaming adapters can consume the exact same sequence."""
    conversation_id = str(ctx.conversation["id"])

    if ctx.kind == "human_turn":
        background_tasks.add_task(_persist_human_turn, conversation_id, message)
        yield {"type": "human_turn"}
        return

    if ctx.kind == "guardrail":
        # Invariant #3: a blocked message is never stored — nothing scheduled here.
        yield {"type": "token", "text": ctx.canned_text}
        yield {"type": "sources", "sources": []}
        yield {"type": "done"}
        return

    if ctx.kind == "no_sources":
        text = _no_sources_message()
        background_tasks.add_task(_persist_canned_answer, conversation_id, message, text)
        yield {"type": "token", "text": text}
        yield {"type": "sources", "sources": []}
        yield {"type": "done"}
        return

    if ctx.kind == "escalate":
        text = _handoff_message()
        yield {"type": "token", "text": text}
        yield {"type": "handoff", "reason": ctx.reason}
        yield {"type": "done"}
        background_tasks.add_task(
            _persist_escalation, ctx.conversation, message, text, ctx.reason, ctx.new_streak
        )
        return

    # kind == "answer"
    answer_parts: list[str] = []
    try:
        token_stream = answer_agent.stream_answer(
            ctx.chunks,
            ctx.history,
            message,
            ctx.low_relevance,
            business_name=tenant.get("name") or "Our team",
            business_tone=_tenant_tone(tenant),
        )
        async for token in with_heartbeat(token_stream):
            if token == PING:
                yield {"type": "ping"}
                continue
            answer_parts.append(token)
            yield {"type": "token", "text": token}
    except Exception as exc:  # noqa: BLE001 — mid-stream failure degrades to one error event
        _log.warning("answer stream failed", extra={"error": repr(exc)})
        # A mid-stream failure stores NOTHING (neither question nor partial answer) —
        # matches DocChat's chat_pipeline convention.
        yield {"type": "error", "detail": _FRIENDLY_STREAM_ERROR}
        return

    answer_text = "".join(answer_parts)
    sources = answer_agent.cited_sources(ctx.chunks, answer_text)
    yield {"type": "sources", "sources": sources}
    yield {"type": "done"}

    confidence = "low" if ctx.low_relevance else "answered"
    background_tasks.add_task(
        _persist_answer, conversation_id, message, answer_text, sources, confidence, ctx.new_streak
    )


# --------------------------------------------------------------------------- adapters


async def run_chat_stream(
    *,
    tenant: dict[str, Any],
    conversation: dict[str, Any],
    message: str,
    background_tasks: BackgroundTasks,
) -> AsyncIterator[str]:
    """`POST /chat/stream` — the frozen SSE contract: token/seq, sources, handoff,
    done, human_turn, error (spec Req 1/11)."""
    ctx = await prepare_turn(tenant=tenant, conversation=conversation, message=message)
    seq = 0
    async for event in _run_turn(ctx, tenant, message, background_tasks):
        kind = event["type"]
        if kind == "token":
            yield format_token(seq, event["text"])
            seq += 1
        elif kind == "ping":
            yield PING
        elif kind == "sources":
            yield format_event("sources", {"sources": event["sources"]})
        elif kind == "handoff":
            yield format_event("handoff", {"reason": event["reason"]})
        elif kind == "human_turn":
            yield format_event("human_turn", {})
        elif kind == "error":
            yield format_event("error", {"detail": event["detail"]})
        elif kind == "done":
            yield format_event("done", {})


async def run_chat_once(
    *,
    tenant: dict[str, Any],
    conversation: dict[str, Any],
    message: str,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """`POST /chat` — the non-streaming sibling for n8n/WhatsApp (spec Req 10)."""
    ctx = await prepare_turn(tenant=tenant, conversation=conversation, message=message)
    reply_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    escalated = False
    reason: str | None = None
    status = ctx.conversation["status"]
    failed = False

    async for event in _run_turn(ctx, tenant, message, background_tasks):
        kind = event["type"]
        if kind == "token":
            reply_parts.append(event["text"])
        elif kind == "sources":
            sources = event["sources"]
        elif kind == "handoff":
            escalated = True
            reason = event["reason"]
            status = "needs_human"
        elif kind == "human_turn":
            status = "human_assigned"
        elif kind == "error":
            failed = True

    return {
        "reply": None if failed else "".join(reply_parts) or None,
        "sources": sources,
        "escalated": escalated,
        "reason": reason,
        "conversation_id": str(ctx.conversation["id"]),
        "status": status,
    }
