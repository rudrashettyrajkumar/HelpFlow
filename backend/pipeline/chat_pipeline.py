"""Chat pipeline — the async orchestrator (ARCHITECTURE §3.2, spec E3 Req 1-10;
retrofitted to the v2 model layer by spec E4 Req 5).

The pipeline order is LAW and UNCHANGED since E3: conversation load (done by the
caller, `api/chat.py`, before rate-limit checks) → human_assigned guard →
guardrail → route/rewrite → retrieve (route=retrieve only) → escalation decision
→ answer OR escalate → persist. `prepare_turn()` now makes every one of those
decisions by invoking `graph/support_graph.py` (a thin wrapper, per spec E4 Req 5)
instead of running them inline — the decisions themselves, their order, and the
escalation truth table are byte-identical to E3.

`prepare_turn()` never streams, never persists; `_run_turn()` is the single core
that streams the answer AND schedules every persistence side effect as a
`BackgroundTasks` job (never blocks the response). `run_chat_stream()` and
`run_chat_once()` are thin adapters over the SAME `_run_turn()` core — one for
`POST /chat/stream` (SSE), one for `POST /chat` (n8n/WhatsApp's non-streaming
sibling) — so the escalation truth table and persistence logic exist in exactly
one place, never duplicated between the two endpoints.

New in E4: every entry point takes an optional `cfg: RunConfig` (BYOK selection
parsed by `api/chat.py` from the request's `X-LLM-*`/`X-Embed-*` headers;
defaults to demo mode) and the pipeline emits ONE additive SSE event, `notice`
(demo_exhausted | embed_mismatch | key_invalid) — the existing `token`/`sources`/
`handoff`/`human_turn`/`done`/`error` shapes are byte-compatible with E3.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks

from backend.agents import answer_agent
from backend.agents.retrieval_agent import RetrievedChunk
from backend.channels import conversation_store
from backend.graph import support_graph
from backend.llm.gateway import LLMUnavailable
from backend.llm.runconfig import DEFAULT, RunConfig
from backend.services.demo_budget import DemoBudgetExceeded
from backend.utils.config import get_settings
from backend.utils.sse import PING, format_event, format_token, with_heartbeat

_log = logging.getLogger("helpflow.chat_pipeline")

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_FRIENDLY_STREAM_ERROR = "Something went wrong while generating the answer. Please try again."

_NOTICE_LINKS: dict[str, list[dict[str, str]]] = {
    "demo_exhausted": [
        {"label": "Get a Groq key", "url": "https://console.groq.com/keys"},
        {"label": "Get an OpenRouter key", "url": "https://openrouter.ai/settings/keys"},
        {"label": "Open Model Studio", "url": "/model-studio"},
    ],
    "key_invalid": [{"label": "Open Model Studio", "url": "/model-studio"}],
    "embed_mismatch": [{"label": "Open Model Studio", "url": "/model-studio"}],
}


# --------------------------------------------------------------------------- decision


@dataclass
class TurnContext:
    """Everything `_run_turn` needs — the output of every pre-answer decision."""

    kind: str  # "human_turn"|"guardrail"|"no_sources"|"notice"|"answer"|"escalate"
    conversation: dict[str, Any]
    history: list[dict[str, Any]] = field(default_factory=list)
    canned_text: str | None = None
    chunks: list[RetrievedChunk] = field(default_factory=list)
    low_relevance: bool = False
    route: str | None = None
    reason: str | None = None
    new_streak: int = 0
    notice_code: str | None = None


def _state_to_context(state: support_graph.SupportState) -> TurnContext:
    """Adapt the graph's final state into the `TurnContext` `_run_turn` consumes."""
    return TurnContext(
        kind=state.get("kind", "answer"),
        conversation=state["conversation"],
        history=state.get("history", []),
        canned_text=state.get("canned_text"),
        chunks=state.get("chunks", []),
        low_relevance=state.get("low_relevance", False),
        route=state.get("route"),
        reason=state.get("reason"),
        new_streak=state.get("new_streak", 0),
        notice_code=state.get("notice_code"),
    )


async def prepare_turn(
    *,
    tenant: dict[str, Any],
    conversation: dict[str, Any],
    message: str,
    cfg: RunConfig = DEFAULT,
) -> TurnContext:
    """Steps 0(guard)-5 of §3.2 via the LangGraph support graph — every decision,
    zero side effects, zero streaming (spec E4 Req 5: a thin invoker)."""
    state: support_graph.SupportState = {
        "tenant": tenant,
        "conversation": conversation,
        "message": message,
        "cfg": cfg,
    }
    final_state = await support_graph.prepare(state)
    return _state_to_context(final_state)


# --------------------------------------------------------------------------- canned text


def _load_variants(filename: str) -> tuple[str, ...]:
    """`---`-separated canned reply variants from a prompts/*.md file (guardrails.md's
    pattern, generalized) — random pick avoids the reply feeling scripted."""
    raw = (_PROMPTS_DIR / filename).read_text(encoding="utf-8")
    parts = (p.strip() for p in raw.split("\n---\n"))
    return tuple(p for p in parts if p)


_HANDOFF_CACHE: tuple[str, ...] | None = None
_NO_SOURCES_CACHE: str | None = None
_DEMO_EXHAUSTED_CACHE: str | None = None


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


def _demo_exhausted_message() -> str:
    global _DEMO_EXHAUSTED_CACHE
    if _DEMO_EXHAUSTED_CACHE is None:
        _DEMO_EXHAUSTED_CACHE = (
            (_PROMPTS_DIR / "demo_exhausted.md").read_text(encoding="utf-8").strip()
        )
    return _DEMO_EXHAUSTED_CACHE


def _notice_payload(code: str, *, detail: str | None = None) -> dict[str, Any]:
    """The additive `notice` SSE event body (spec E4 Req 8, ARCHITECTURE §3.2/§4.3).

    Rendered as a friendly designed card by the widget/portal — never a raw
    error. `demo_exhausted` always uses the product copy in
    `prompts/demo_exhausted.md`; `key_invalid`/`embed_mismatch` use the
    caller-supplied `detail` when available.
    """
    message = _demo_exhausted_message() if code == "demo_exhausted" else (detail or code)
    return {"code": code, "message": message, "links": _NOTICE_LINKS.get(code, [])}


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
    ctx: TurnContext,
    tenant: dict[str, Any],
    message: str,
    background_tasks: BackgroundTasks,
    cfg: RunConfig = DEFAULT,
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

    if ctx.kind == "notice":
        # A demo-budget exhaustion caught during retrieval's query embed (spec E4
        # Req 6) — nothing is stored, same as any other infra-availability notice.
        yield {"type": "notice", **_notice_payload(ctx.notice_code or "demo_exhausted")}
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
            cfg=cfg,
        )
        async for token in with_heartbeat(token_stream):
            if token == PING:
                yield {"type": "ping"}
                continue
            answer_parts.append(token)
            yield {"type": "token", "text": token}
    except DemoBudgetExceeded:
        # spec E4 Req 6: exhaustion (including a provider-side quota error that
        # slipped past the pre-check) is ALWAYS the designed notice, never a
        # raw error — nothing stored, same as the guardrail/no_sources exits.
        _log.info("demo chat budget exhausted mid-turn", extra={"conversation_id": conversation_id})
        yield {"type": "notice", **_notice_payload("demo_exhausted")}
        yield {"type": "done"}
        return
    except LLMUnavailable as exc:
        # A BYOK selection failed outright (bad key/model/rate-limit) — no
        # server fallback by design (invariant #7); surfaced as a fixable
        # notice, never a raw provider error. A demo-mode exhaustion (all
        # deployments unavailable) maps to the same `demo_exhausted` copy.
        code = "demo_exhausted" if cfg.chat is None else "key_invalid"
        _log.warning(
            "llm unavailable mid-turn",
            extra={"conversation_id": conversation_id, "code": code},
        )
        yield {"type": "notice", **_notice_payload(code, detail=exc.user_detail)}
        yield {"type": "done"}
        return
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
    cfg: RunConfig = DEFAULT,
) -> AsyncIterator[str]:
    """`POST /chat/stream` — the frozen SSE contract: token/seq, sources, handoff,
    done, human_turn, error (spec E3 Req 1/11), plus the additive `notice` event
    (spec E4 Req 8).

    DESIGN CHOICE (flagged, spec E7): `done`'s payload widens from `{}` to
    `{conversation_id}` — additive only, no existing key changes. Needed
    because this is otherwise the ONLY place a brand-new web conversation's
    server-minted id could reach the widget: `/chat/stream`'s SSE frames never
    carried it, and the widget must persist it (reload continuity) and hand it
    to `/chat/subscribe` for live human replies (spec Req 6). `/chat`
    (`run_chat_once`, n8n/WhatsApp's sibling) already returns `conversation_id`
    in its JSON body and is unaffected.
    """
    ctx = await prepare_turn(tenant=tenant, conversation=conversation, message=message, cfg=cfg)
    conversation_id = str(ctx.conversation["id"])
    seq = 0
    async for event in _run_turn(ctx, tenant, message, background_tasks, cfg):
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
        elif kind == "notice":
            yield format_event(
                "notice",
                {"code": event["code"], "message": event["message"], "links": event["links"]},
            )
        elif kind == "error":
            yield format_event("error", {"detail": event["detail"]})
        elif kind == "done":
            yield format_event("done", {"conversation_id": conversation_id})


async def run_chat_once(
    *,
    tenant: dict[str, Any],
    conversation: dict[str, Any],
    message: str,
    background_tasks: BackgroundTasks,
    cfg: RunConfig = DEFAULT,
) -> dict[str, Any]:
    """`POST /chat` — the non-streaming sibling for n8n/WhatsApp (spec Req 10)."""
    ctx = await prepare_turn(tenant=tenant, conversation=conversation, message=message, cfg=cfg)
    reply_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    escalated = False
    reason: str | None = None
    notice: dict[str, Any] | None = None
    status = ctx.conversation["status"]
    failed = False

    async for event in _run_turn(ctx, tenant, message, background_tasks, cfg):
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
        elif kind == "notice":
            notice = {"code": event["code"], "message": event["message"], "links": event["links"]}
        elif kind == "error":
            failed = True

    return {
        "reply": None if failed else "".join(reply_parts) or None,
        "sources": sources,
        "escalated": escalated,
        "reason": reason,
        "notice": notice,
        "conversation_id": str(ctx.conversation["id"]),
        "status": status,
    }
