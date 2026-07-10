"""Route + rewrite + intent agent — one small LLM call (ARCHITECTURE §3.2 STEP 2,
spec E3 Req 4).

Ported from DocChat `agents/rewrite_agent.py`, extended with the `handoff`/intent
control signal HelpFlow needs. Turns the raw customer turn into the strict JSON the
rest of the pipeline runs on: `route` (direct|retrieve|handoff), standalone `queries`
for multi-query retrieval, `handoff_reason`, and an `intent` classification.

Degraded beats broken (DocChat DEFAULT pattern / MyShiva detection_agent.py): ANY
failure on this pre-retrieval hot path — LLM timeout/error, malformed JSON, a missing
field, an out-of-enum value — falls back to `Rewrite(route="retrieve",
queries=[message], handoff_reason=None, intent="question")`, logged with its reason.
This module never raises out to the pipeline.

Defense in depth: even when the model's own `route` misses it, a message whose
`intent` lands in the tenant's sensitive-intent set is force-routed to `handoff`
here in Python — never left to the model alone to enforce (invariant #1,
grounded-or-handoff must never depend solely on one LLM call getting it right).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError, field_validator

from backend.utils import llm_router

_log = logging.getLogger("helpflow.rewrite_agent")

# Show the model only the last 6 turns (ARCHITECTURE §3.2 short-term window).
_HISTORY_TURNS = 6
_MIN_QUERIES = 1
_MAX_QUERIES = 3

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "router.md"
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")

Intent = Literal["question", "refund", "complaint", "cancel", "human", "chitchat"]


class Rewrite(BaseModel):
    """The validated E3 control signal: route + standalone queries + intent."""

    route: Literal["direct", "retrieve", "handoff"]
    queries: list[str]
    handoff_reason: Literal["user_requested"] | None = None
    intent: Intent = "question"

    @field_validator("route", mode="before")
    @classmethod
    def _normalize_route(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("intent", mode="before")
    @classmethod
    def _normalize_intent(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("handoff_reason", mode="before")
    @classmethod
    def _normalize_handoff_reason(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip().lower()
            return stripped or None
        return value

    @field_validator("queries", mode="after")
    @classmethod
    def _clean_queries(cls, value: list[str]) -> list[str]:
        return [q.strip() for q in value if isinstance(q, str) and q.strip()]


class _ParseError(Exception):
    """A categorized reason the model output could not become a valid Rewrite."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


async def rewrite(
    message: str,
    history: list[dict[str, Any]] | None = None,
    tenant_name: str = "the business",
    sensitive_intents: frozenset[str] = frozenset(),
) -> Rewrite:
    """Turn one customer turn into a validated `Rewrite` (never raises).

    `history` is recent turns (oldest-first, dicts with `role`/`content`); only the
    last 6 are shown to the model. `sensitive_intents` is the tenant's (or global
    default) always-escalate intent set — enforced here even if the model's `route`
    disagrees. Any failure -> the safe default, logged with its reason.
    """
    messages = _build_messages(message, history or [], tenant_name)
    try:
        response = await llm_router.complete(
            "rewrite", messages, response_format={"type": "json_object"}
        )
        text = response.choices[0].message.content
    except Exception as exc:  # noqa: BLE001 — boundary: any LLM/timeout failure degrades
        return _default_rewrite(message, f"llm_call_failed: {exc!r}")
    try:
        parsed = _to_rewrite(_loads(text))
    except _ParseError as exc:
        return _default_rewrite(message, exc.reason)
    return _enforce_sensitive_intents(parsed, sensitive_intents)


def _enforce_sensitive_intents(parsed: Rewrite, sensitive_intents: frozenset[str]) -> Rewrite:
    """Force `route=handoff` when `intent` is sensitive, even if the model missed it."""
    if parsed.route != "handoff" and parsed.intent in sensitive_intents:
        _log.info(
            "sensitive intent override",
            extra={"event": "sensitive_intent_override", "intent": parsed.intent},
        )
        return parsed.model_copy(update={"route": "handoff"})
    return parsed


def _to_rewrite(data: dict[str, Any]) -> Rewrite:
    """Validate the parsed dict into a Rewrite; raise `_ParseError` on rejection."""
    try:
        parsed = Rewrite.model_validate(data)
    except ValidationError as exc:
        raise _ParseError(f"schema_invalid: {_first_error(exc)}") from exc
    if parsed.route == "retrieve" and not (_MIN_QUERIES <= len(parsed.queries) <= _MAX_QUERIES):
        raise _ParseError("query_count_out_of_range")
    return parsed


def _loads(raw: str) -> dict[str, Any]:
    """Strip accidental ```json fences → json.loads → require a JSON object."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = _FENCE_RE.sub("", text).strip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise _ParseError(f"json_decode_failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise _ParseError("output_not_a_json_object")
    return parsed


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "unknown"
    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", ())) or "?"
    return f"{loc}: {first.get('msg', '')}"


def _build_messages(
    message: str, history: list[dict[str, Any]], tenant_name: str
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _prompt()},
        {"role": "user", "content": _user_turn(message, history, tenant_name)},
    ]


def _user_turn(message: str, history: list[dict[str, Any]], tenant_name: str) -> str:
    return (
        f"BUSINESS: {tenant_name}\n"
        f"HISTORY (oldest first, last 6 turns):\n{_format_history(history)}\n\n"
        f'MESSAGE:\n"""\n{message}\n"""\n\n'
        "Return ONLY the rewrite JSON object now."
    )


def _format_history(history: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for turn in history[-_HISTORY_TURNS:]:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "user")).strip() or "user"
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior turns)"


_PROMPT_CACHE: str | None = None


def _prompt() -> str:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is None:
        _PROMPT_CACHE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_CACHE


def _default_rewrite(message: str, reason: str) -> Rewrite:
    """Degraded-but-answerable fallback (DocChat DEFAULT pattern).

    The customer's own message becomes the single retrieval query so the chat
    pipeline still gets relevant chunks; logged with the precise `reason`.
    """
    _log.warning(
        "rewrite fallback",
        extra={"event": "rewrite_fallback", "fallback_reason": reason},
    )
    query = message.strip()[:200] or "What can you help me with?"
    return Rewrite(route="retrieve", queries=[query], handoff_reason=None, intent="question")
