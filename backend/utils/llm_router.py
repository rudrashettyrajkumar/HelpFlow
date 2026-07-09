"""The single chokepoint for every LLM call in the brain (ARCHITECTURE §4).

Ported from MyShiva `utils/llm_router.py`. Agents NEVER import `litellm`
directly — they call `complete(role, ...)` or `stream(role, ...)` here. A
"role" (`rewrite` / `answer`) maps to a LiteLLM Router deployment GROUP: the
same `model_name` registered twice *is* the §4 failover chain (env-driven
OpenRouter primary → pinned Groq fallback), and LiteLLM rotates across the group
on 429/5xx/timeout (`num_retries=2`, `retry_after=0.5`). Retries + failover are
owned by the Router — never a manual retry loop (spec E1 Req 2).

Two cross-cutting guarantees live here:

* **Concurrency cap** — one global `asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)`
  wraps both public calls. For `stream()` the slot is held for the WHOLE stream
  lifetime (released in the generator's `finally`); a slot freed after mere
  connection setup would let dozens of open streams burst a provider's RPM.
* **Mid-stream failover policy** — a primary dying BEFORE the first token is
  healed transparently by LiteLLM. Dying AFTER tokens have flowed must NOT
  silently restart from token 0 (duplicate text): we raise `StreamInterrupted`
  carrying the tokens-so-far and let the caller decide (E3).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from backend.utils.config import Settings, get_settings

if TYPE_CHECKING:
    from litellm import Router

_log = logging.getLogger("helpflow.llm_router")

# Per-role request timeout (seconds), ARCHITECTURE §3.2. The rewrite call sits on
# the latency-critical pre-answer path (~400ms budget); the answer call streams a
# longer grounded reply.
ROLE_TIMEOUTS: dict[str, float] = {
    "rewrite": 8.0,
    "answer": 30.0,
}

# Fixed fallback model IDs (ARCHITECTURE §4 table). Role primaries are env-driven
# (config.py); this Groq provider-contract string is the pinned failover link of
# each chain (primary = OpenRouter Gemini, fallback = Groq — a deliberately
# diverse second provider so one OpenRouter outage isn't total).
_GROQ_70B = "groq/llama-3.3-70b-versatile"


class StreamInterrupted(Exception):
    """A stream died AFTER at least one token was delivered.

    Carries the tokens already sent downstream so the caller can decide how to
    surface the interruption instead of silently duplicating text (a LiteLLM
    restart would replay from token 0). Failures BEFORE the first token never
    reach here — LiteLLM heals those transparently.
    """

    def __init__(self, partial_tokens: list[str]) -> None:
        self.partial_tokens = partial_tokens
        super().__init__(f"stream interrupted after {len(partial_tokens)} tokens")


def _key_for(model: str, s: Settings) -> str | None:
    """The provider credential matching a model id's `provider/` prefix.

    Lets a role's env primary migrate to any provider (invariant #8) without
    touching this module: the right key is picked from the id alone. Defaults to
    OpenRouter, the primary gateway.
    """
    if model.startswith("groq/"):
        return s.GROQ_API_KEY
    if model.startswith("gemini/"):
        return s.GEMINI_API_KEY
    return s.OPENROUTER_API_KEY


def _dep(name: str, model: str, s: Settings) -> dict[str, Any]:
    """One Router deployment: a role `name` bound to a model + its provider key."""
    return {
        "model_name": name,
        "litellm_params": {"model": model, "api_key": _key_for(model, s)},
    }


def _build_model_list(s: Settings) -> list[dict[str, Any]]:
    """The two §4 failover chains, ordered primary-first per role.

    Order within each `model_name` group is the failover order: an env-driven
    OpenRouter Gemini primary then the pinned Groq fallback.
    """
    return [
        # route + rewrite + intent (strict JSON).
        _dep("rewrite", s.ROUTER_MODEL, s),
        _dep("rewrite", _GROQ_70B, s),
        # grounded, cited, streamed answer.
        _dep("answer", s.ANSWER_MODEL, s),
        _dep("answer", _GROQ_70B, s),
    ]


_router: Router | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_router() -> Router:
    """Lazily build the shared Router singleton (heavy import deferred)."""
    global _router
    if _router is None:
        from litellm import Router

        _router = Router(
            model_list=_build_model_list(get_settings()),
            num_retries=2,
            retry_after=0.5,
        )
    return _router


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


def _bare(model_id: str) -> str:
    """Drop the `provider/` prefix so a served model compares to a config id."""
    return model_id.split("/")[-1]


def _primary_for(role: str) -> str:
    """The env-configured primary model id for a role."""
    s = get_settings()
    return {"rewrite": s.ROUTER_MODEL, "answer": s.ANSWER_MODEL}[role]


def _log_failover(role: str, served_model: str | None) -> None:
    """Log a structured failover event when a non-primary deployment served."""
    if not served_model:
        return
    primary = _primary_for(role)
    if _bare(served_model) == _bare(primary):
        return
    _log.warning(
        "llm failover",
        extra={
            "event": "llm_failover",
            "role": role,
            "from_provider": primary,
            "to_provider": served_model,
            "reason": "primary unavailable; served by fallback deployment",
        },
    )


def _token_of(chunk: Any) -> str:
    """Best-effort text delta from a streaming chunk ('' if none)."""
    try:
        return chunk.choices[0].delta.content or ""
    except (AttributeError, IndexError, TypeError):
        return ""


async def complete(role: str, messages: list[dict[str, Any]], **kw: Any) -> Any:
    """Non-streaming completion for `role`, through the semaphore + failover chain.

    Returns the raw LiteLLM response (agents read `.choices[0].message.content`).
    Acquiring/releasing the slot is scoped to the single round-trip.
    """
    timeout = _check_role(role)
    async with _get_semaphore():
        response = await _get_router().acompletion(
            model=role, messages=messages, timeout=timeout, **kw
        )
    _log_failover(role, getattr(response, "model", None))
    return response


async def stream(
    role: str, messages: list[dict[str, Any]], **kw: Any
) -> AsyncIterator[str]:
    """Stream text tokens for `role`, holding the semaphore for the whole stream.

    The slot is acquired before the call and released in `finally` only after the
    last token (or an interruption) — see the module docstring on RPM bursting.
    A mid-stream death after ≥1 token raises `StreamInterrupted` with the partial
    text; a death before the first token is left to LiteLLM's transparent retry.
    """
    timeout = _check_role(role)
    sem = _get_semaphore()
    await sem.acquire()
    tokens: list[str] = []
    served_seen = False
    try:
        response = await _get_router().acompletion(
            model=role, messages=messages, stream=True, timeout=timeout, **kw
        )
        try:
            async for chunk in response:
                if not served_seen:
                    served_seen = True
                    _log_failover(role, getattr(chunk, "model", None))
                token = _token_of(chunk)
                if token:
                    tokens.append(token)
                    yield token
        except Exception as exc:
            # Tokens already on the wire: never let LiteLLM restart from token 0
            # (duplicate text). Hand the partial up; the caller decides.
            if tokens:
                _log.warning(
                    "stream interrupted mid-flight",
                    extra={
                        "event": "stream_interrupted",
                        "role": role,
                        "tokens_sent": len(tokens),
                        "reason": str(exc),
                    },
                )
                raise StreamInterrupted(tokens) from exc
            # Nothing sent yet — surface whatever LiteLLM couldn't heal.
            raise
    finally:
        sem.release()


async def liveness() -> bool:
    """Cheap gateway reachability probe for /health (spec E1 Req 6).

    Lists OpenRouter's model catalog — a free, no-token GET that proves the
    gateway is reachable and the key valid. Never raises here for the caller's
    convenience is deliberately NOT done: the health probe wrapper owns the
    try/except so a real error is logged with its dependency name.
    """
    import httpx

    settings = get_settings()
    async with httpx.AsyncClient(timeout=2.0) as http:
        resp = await http.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
        )
        resp.raise_for_status()
    return True
