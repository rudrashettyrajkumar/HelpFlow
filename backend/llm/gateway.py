"""The single chokepoint for every LLM call — BYOK-aware successor to
`utils/llm_router.py` (ARCHITECTURE §4.6, spec E4 Req 2).

Agents NEVER import LangChain (or a provider SDK) directly; they call
`complete(role, messages, cfg)` or `stream(role, messages, cfg)` here. The
`cfg: RunConfig` decides the deployment chain:

- **BYOK** (`cfg.chat` set): exactly ONE deployment — the user's own
  provider/model/key. No server fallback, by design: a broken user key must
  fail loudly with a fixable message, never silently burn demo credit.
- **Demo** (`cfg.chat` None): the shared daily budget is checked FIRST
  (`services.demo_budget`, spec Req 6) — over cap raises `DemoBudgetExceeded`
  before any provider is touched — then the env primary, then the pinned
  Groq<->OpenRouter fallback (`factory.demo_chain`).

The chain loop replaces the old Router's deployment groups: try each in
order, log a structured `llm_failover` event when a non-primary serves. One
global `asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)` still wraps both public
calls, and `stream()` still holds its slot for the WHOLE stream lifetime — a
slot freed after connection setup would let open streams burst a provider's
RPM (same guarantee `llm_router.py` made).

`StreamInterrupted(partial_tokens)` is preserved verbatim from `llm_router.py`
(spec Req 2: "SAME public surface") — a stream dying AFTER at least one token
must never silently restart from token 0 (duplicate text); the caller decides
how to surface the interruption.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from backend.llm import factory
from backend.llm.runconfig import DEFAULT, RunConfig, Selection
from backend.services import demo_budget
from backend.utils.config import get_settings

_log = logging.getLogger("helpflow.llm_gateway")

# Per-role request timeout (seconds) — UNCHANGED from `llm_router.py` (spec Req 2).
ROLE_TIMEOUTS: dict[str, float] = {
    "rewrite": 8.0,
    "answer": 30.0,
}


class StreamInterrupted(Exception):
    """A stream died AFTER at least one token was delivered.

    Carries the tokens already sent downstream so the caller can decide how to
    surface the interruption instead of silently duplicating text.
    """

    def __init__(self, partial_tokens: list[str]) -> None:
        self.partial_tokens = partial_tokens
        super().__init__(f"stream interrupted after {len(partial_tokens)} tokens")


class LLMUnavailable(RuntimeError):
    """Every deployment in the chain failed.

    `user_detail` is safe to show the end user — for BYOK it names the
    provider/model so they can fix their key or pick another model.
    """

    def __init__(self, message: str, *, user_detail: str) -> None:
        super().__init__(message)
        self.user_detail = user_detail


_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Lazily build the global concurrency gate (bound to the running loop)."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().MAX_CONCURRENT_LLM_CALLS)
    return _semaphore


def _check_role(role: str) -> float:
    """Return the role's timeout, or fail loudly on an unknown role."""
    try:
        return ROLE_TIMEOUTS[role]
    except KeyError:
        raise ValueError(f"unknown LLM role: {role!r}") from None


async def _chain_for(role: str, cfg: RunConfig) -> list[Selection]:
    """The ordered deployment chain for this request (see module docstring).

    Demo mode (`cfg.chat is None`) checks the shared daily budget FIRST
    (spec Req 6: "checked BEFORE any demo-mode provider call") — raises
    `demo_budget.DemoBudgetExceeded` before any deployment is even built.
    """
    if cfg.chat is not None:
        return [cfg.chat]
    await demo_budget.check_and_increment("chat")
    return factory.demo_chain(role)


def _no_deployments(cfg: RunConfig) -> LLMUnavailable:
    return LLMUnavailable(
        "no LLM deployment configured",
        user_detail=(
            "No AI model is configured on the server. Open Model Studio and "
            "connect your own API key."
            if cfg.chat is None
            else "Your selected model could not be reached."
        ),
    )


def _user_detail(selection: Selection, cfg: RunConfig, exc: Exception) -> str:
    if cfg.chat is None:
        return (
            "Demo mode runs on free-tier open-source models (Llama 3.3 70B on Groq, "
            "NVIDIA Nemotron on OpenRouter) and they're rate-limited or briefly down. "
            "Try again in a minute — or add your own API key in Model Studio for "
            "reliable, unthrottled access."
        )
    reason = str(exc)[:200]
    return (
        f"Your {selection.provider} model “{selection.model}” returned an error: "
        f"{reason} — check your API key and model choice in Model Studio."
    )


def _log_failover(role: str, primary: Selection, served: Selection) -> None:
    if served == primary:
        return
    _log.warning(
        "llm failover",
        extra={
            "event": "llm_failover",
            "role": role,
            "from_provider": f"{primary.provider}/{primary.model}",
            "to_provider": f"{served.provider}/{served.model}",
            "reason": "primary unavailable; served by fallback deployment",
        },
    )


def _text_of(content: Any) -> str:
    """Normalize LangChain message content to plain text.

    Anthropic (and thinking-enabled models generally) return a list of typed
    blocks; everything else returns a plain string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


async def complete(
    role: str, messages: list[dict[str, Any]], cfg: RunConfig = DEFAULT, **kw: Any
) -> str:
    """Non-streaming completion for `role` → the reply text.

    `json_mode=True` binds the OpenAI-compatible JSON response format where
    the provider supports it (kept as a kwarg so call sites read the same as
    the old `llm_router.complete(..., response_format=...)` shape). Tries each
    deployment in the chain; raises `LLMUnavailable` (with a user-safe detail)
    only when ALL fail. The semaphore slot is scoped to a single round-trip.
    """
    json_mode = bool(kw.pop("json_mode", False)) or kw.get("response_format") is not None
    timeout = _check_role(role)
    chain = await _chain_for(role, cfg)
    if not chain:
        raise _no_deployments(cfg)

    last_exc: Exception | None = None
    for selection in chain:
        model = factory.build_chat_model(selection, timeout=timeout)
        if json_mode:
            model = factory.bind_json_mode(model, selection)
        try:
            async with _get_semaphore():
                response = await model.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001 — chain boundary: try the next deployment
            last_exc = exc
            _log.warning(
                "llm call failed",
                extra={
                    "role": role,
                    "provider": f"{selection.provider}/{selection.model}",
                    "error": repr(exc)[:300],
                },
            )
            continue
        _log_failover(role, chain[0], selection)
        return _text_of(response.content)

    assert last_exc is not None
    raise LLMUnavailable(
        f"all deployments failed for role {role!r}: {last_exc!r}",
        user_detail=_user_detail(chain[-1], cfg, last_exc),
    ) from last_exc


async def stream(
    role: str, messages: list[dict[str, Any]], cfg: RunConfig = DEFAULT
) -> AsyncIterator[str]:
    """Stream reply text tokens for `role`, holding the semaphore slot for the
    whole stream lifetime (released in `finally` after the last token).

    Failover only happens BEFORE the first token: once tokens have reached the
    caller there is no safe way to substitute a different model mid-answer —
    a death after ≥1 token raises `StreamInterrupted` with what was already
    sent (never a silent restart from token 0, matching `llm_router.py`).
    """
    timeout = _check_role(role)
    chain = await _chain_for(role, cfg)
    if not chain:
        raise _no_deployments(cfg)

    sem = _get_semaphore()
    await sem.acquire()
    tokens: list[str] = []
    try:
        last_exc: Exception | None = None
        for selection in chain:
            model = factory.build_chat_model(selection, timeout=timeout, streaming=True)
            started = False
            try:
                async for chunk in model.astream(messages):
                    if not started:
                        started = True
                        _log_failover(role, chain[0], selection)
                    token = _text_of(chunk.content)
                    if token:
                        tokens.append(token)
                        yield token
                return
            except Exception as exc:
                if started:  # mid-stream: no substitution possible
                    raise StreamInterrupted(tokens) from exc
                last_exc = exc
                _log.warning(
                    "llm stream failed before first token",
                    extra={
                        "role": role,
                        "provider": f"{selection.provider}/{selection.model}",
                        "error": repr(exc)[:300],
                    },
                )
                continue

        assert last_exc is not None
        raise LLMUnavailable(
            f"all deployments failed for role {role!r}: {last_exc!r}",
            user_detail=_user_detail(chain[-1], cfg, last_exc),
        ) from last_exc
    finally:
        sem.release()


_LIVENESS_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
}


async def liveness() -> bool:
    """Cheap gateway reachability probe for `/health` (spec E4 Req 9: "keys off
    the demo chain"). A free, no-token models-list GET against whichever
    provider leads today's demo `answer` chain — reachability + key, never a
    paid completion call."""
    import httpx

    chain = factory.demo_chain("answer")
    if not chain:
        return False
    selection = chain[0]
    url = _LIVENESS_URLS.get(selection.provider)
    if url is None:
        return True
    async with httpx.AsyncClient(timeout=2.0) as http:
        resp = await http.get(url, headers={"Authorization": f"Bearer {selection.api_key}"})
        resp.raise_for_status()
    return True
