"""The chat turn as a LangGraph StateGraph (ARCHITECTURE §3.2, spec E4 Req 5).

Ported near-verbatim from DocChat v3 `backend/graph/chat_graph.py`, adapted to
HelpFlow's pipeline LAW (unchanged since E3):

    human_guard ─(assigned)─────────────────────────────────────────▶ END
       │
    guardrail ─(blocked)────────────────────────────────────────────▶ END
       │
    rewrite (route/queries/intent, one small LLM call)
       │
    retrieve ─(route=retrieve, zero ready sources)──────────────────▶ END
       │        (route!=retrieve -> chunks=[], low_relevance=False)
    escalation_decision (DETERMINISTIC — no LLM, invariant #1)
       │
       ├─(escalate)──▶ END  (kind="escalate")
       └─(answer)────▶ END  (kind="answer")

Every node is a PLAIN async function returning a partial state update, which
buys two things: they unit-test without langgraph installed, and `prepare()`
falls back to running them sequentially when the langgraph import fails
(errors degrade, never break — a missing optional dep must not take chat
down). Nodes never raise for business reasons — a demo-mode budget
exhaustion during rewrite silently degrades (the LLM-call boundary already
catches everything there); a budget exhaustion during retrieval's query
embed IS surfaced, as `kind="notice"`, because embed failures don't have an
answer-time second chance the way the rewrite step does.

Answer streaming intentionally stays OUTSIDE the graph, in `chat_pipeline`:
token-level SSE plumbed through graph event streams adds fragility with zero
user benefit; the graph's job ends once the state holds everything the
answerer needs (ARCHITECTURE §3.2 note on `pipeline/chat_pipeline.py`).
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from backend.agents import escalation, rewrite_agent
from backend.agents.retrieval_agent import RetrievedChunk, retrieve
from backend.channels import conversation_store
from backend.llm import reranker
from backend.llm.runconfig import DEFAULT, RunConfig
from backend.services.demo_budget import DemoBudgetExceeded
from backend.utils.config import get_settings
from backend.utils.guardrails import check_input, deflection

_log = logging.getLogger("helpflow.support_graph")


class SupportState(TypedDict, total=False):
    # Inputs (set once by chat_pipeline)
    tenant: dict[str, Any]
    conversation: dict[str, Any]
    message: str
    cfg: RunConfig
    # Outputs (filled by nodes)
    kind: str  # human_turn|guardrail|no_sources|notice|answer|escalate
    canned_text: str | None
    notice_code: str | None
    history: list[dict[str, Any]]
    route: str | None
    handoff_reason: str | None
    queries: list[str]
    chunks: list[RetrievedChunk]
    low_relevance: bool
    reason: str | None
    new_streak: int


def _sensitive_intents(tenant: dict[str, Any]) -> frozenset[str]:
    """Per-tenant override (`tenants.sensitive_intents`) if set, else the env default."""
    per_tenant = tenant.get("sensitive_intents") or []
    if per_tenant:
        return frozenset(s.lower() for s in per_tenant)
    return get_settings().sensitive_intents


async def human_guard_node(state: SupportState) -> dict[str, Any]:
    """STEP 0 — the AI must NEVER answer a human-assigned conversation (invariant #5)."""
    if state["conversation"]["status"] == "human_assigned":
        return {"kind": "human_turn"}
    return {}


async def guardrail_node(state: SupportState) -> dict[str, Any]:
    """STEP 1 — input rail. Zero LLM calls; a blocked message is never stored (invariant #3)."""
    if check_input(state["message"]) is not None:
        return {"kind": "guardrail", "canned_text": deflection()}
    return {}


async def rewrite_node(state: SupportState) -> dict[str, Any]:
    """STEP 2 — query rewrite (never raises; degrades to route=retrieve internally,
    including on a demo-mode budget exhaustion here — the answer step gets the
    real, surfaced notice)."""
    tenant = state["tenant"]
    history = await conversation_store.recent_history(state["conversation"]["id"])
    rw = await rewrite_agent.rewrite(
        state["message"],
        history,
        tenant_name=tenant.get("name") or "the business",
        sensitive_intents=_sensitive_intents(tenant),
        cfg=state.get("cfg", DEFAULT),
    )
    return {
        "history": history,
        "route": rw.route,
        "handoff_reason": rw.handoff_reason,
        "queries": rw.queries,
    }


async def retrieve_node(state: SupportState) -> dict[str, Any]:
    """STEP 3/4 — multi-query retrieval in the tenant's PINNED embedding space,
    then the open-source cross-encoder rerank (no-op when unavailable)."""
    if state.get("route") != "retrieve":
        # direct/handoff routes skip retrieval entirely (ARCHITECTURE §3.2).
        return {"chunks": [], "low_relevance": False}

    tenant_id = str(state["tenant"]["id"])
    ready = await conversation_store.count_ready_sources(tenant_id)
    if ready == 0:
        return {"kind": "no_sources"}

    cfg = state.get("cfg", DEFAULT)
    try:
        result = await retrieve(state.get("queries", []), tenant_id, cfg)
    except DemoBudgetExceeded:
        # spec E4 Req 6: a demo-mode embed budget exhaustion must surface as
        # the designed notice, never silently degrade to a wrong answer.
        return {"kind": "notice", "notice_code": "demo_exhausted"}

    chunks = await reranker.rerank(state["message"], result.chunks)
    return {"chunks": chunks, "low_relevance": result.low_relevance}


async def escalation_node(state: SupportState) -> dict[str, Any]:
    """STEP 5 — the deterministic escalation decision (invariant #1, NO LLM)."""
    decision = escalation.decide(
        route=state.get("route", "retrieve"),
        handoff_reason=state.get("handoff_reason"),
        low_relevance=state.get("low_relevance", False),
        low_conf_streak=state["conversation"]["low_conf_streak"],
    )
    kind = "escalate" if decision.action == "escalate" else "answer"
    return {"kind": kind, "reason": decision.reason, "new_streak": decision.new_streak}


def _after_human_guard(state: SupportState) -> str:
    return "end" if state.get("kind") else "guardrail"


def _after_guardrail(state: SupportState) -> str:
    return "end" if state.get("kind") else "rewrite"


def _after_retrieve(state: SupportState) -> str:
    return "end" if state.get("kind") else "escalation"


_graph: Any = None
_graph_failed = False  # remember a failed langgraph import; log the fallback once


def build_graph() -> Any:
    """Compile the StateGraph once (lazy langgraph import; None if unavailable)."""
    global _graph, _graph_failed
    if _graph is not None or _graph_failed:
        return _graph
    try:
        from langgraph.graph import END, StateGraph

        g = StateGraph(SupportState)
        g.add_node("human_guard", human_guard_node)
        g.add_node("guardrail", guardrail_node)
        g.add_node("rewrite", rewrite_node)
        g.add_node("retrieve", retrieve_node)
        g.add_node("escalation", escalation_node)
        g.set_entry_point("human_guard")
        g.add_conditional_edges(
            "human_guard", _after_human_guard, {"guardrail": "guardrail", "end": END}
        )
        g.add_conditional_edges(
            "guardrail", _after_guardrail, {"rewrite": "rewrite", "end": END}
        )
        g.add_edge("rewrite", "retrieve")
        g.add_conditional_edges(
            "retrieve", _after_retrieve, {"escalation": "escalation", "end": END}
        )
        g.add_edge("escalation", END)
        _graph = g.compile()
    except ImportError as exc:
        _graph_failed = True
        _log.warning(
            "langgraph unavailable; chat runs the sequential fallback",
            extra={"reason": repr(exc)},
        )
    return _graph


async def _sequential(state: SupportState) -> SupportState:
    """The exact same nodes in the exact same order, without langgraph."""
    merged: SupportState = dict(state)  # type: ignore[assignment]
    merged.update(await human_guard_node(merged))
    if _after_human_guard(merged) == "end":
        return merged
    merged.update(await guardrail_node(merged))
    if _after_guardrail(merged) == "end":
        return merged
    merged.update(await rewrite_node(merged))
    merged.update(await retrieve_node(merged))
    if _after_retrieve(merged) == "end":
        return merged
    merged.update(await escalation_node(merged))
    return merged


async def prepare(state: SupportState) -> SupportState:
    """Run the pre-answer workflow → the final state chat_pipeline streams from.

    LangGraph when installed; the sequential fallback otherwise. A langgraph
    RUNTIME failure (not just import) also degrades to sequential — the nodes
    themselves never raise for business reasons, so an error here is graph
    plumbing, not business logic.
    """
    graph = build_graph()
    if graph is not None:
        try:
            return await graph.ainvoke(state)
        except Exception as exc:  # noqa: BLE001 — plumbing failure degrades to sequential
            _log.warning("langgraph run failed; sequential fallback", extra={"error": repr(exc)})
    return await _sequential(state)
