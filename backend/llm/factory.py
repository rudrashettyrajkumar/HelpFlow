"""LangChain chat-model construction — the only module that imports provider SDKs.

Ported near-verbatim from DocChat v3 `backend/llm/factory.py` (ARCHITECTURE
§4.6). Each provider maps to exactly one LangChain integration class, imported
lazily inside the builder (same deferred-heavy-import pattern the old Router
used) so the app boots, and the test suite runs, on boxes where a given
integration isn't installed. Groq and OpenRouter both speak the OpenAI wire
protocol, so they reuse `ChatOpenAI` with a `base_url` — three integration
packages cover all five providers.

Demo mode (no BYOK headers) keeps the original env-driven failover chain: the
`DEMO_REWRITER_MODEL`/`DEMO_ANSWERER_MODEL` primary (the old router-style
`provider/model` ids, unchanged so existing Railway env vars keep working)
followed by the pinned Groq<->OpenRouter fallback. BYOK requests get NO
server fallback — a broken user key must surface as an error the user can
fix, never silently burn the demo credit (ARCHITECTURE §4.6, invariant #7).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.llm.runconfig import Selection
from backend.utils.config import get_settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_GROQ_BASE = "https://api.groq.com/openai/v1"

# Providers whose endpoint honours OpenAI's `response_format` JSON mode.
_OPENAI_COMPATIBLE = ("openrouter", "groq", "openai")

# Demo-mode diverse fallbacks (ARCHITECTURE §4.3): whichever provider is NOT the
# env primary supplies the second deployment, so a rate-limit or outage on one
# free tier fails over to the other. Both are open-source: Groq's Llama 3.3 70B
# (fast on LPUs, reliable citer) and OpenRouter's NVIDIA Nemotron 3 Super.
_GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"
_OPENROUTER_FALLBACK_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

# Role -> the Settings field carrying its demo-mode env primary.
_ROLE_ENV_FIELD: dict[str, str] = {
    "rewrite": "DEMO_REWRITER_MODEL",
    "answer": "DEMO_ANSWERER_MODEL",
}


def build_chat_model(
    selection: Selection, *, timeout: float, streaming: bool = False
) -> BaseChatModel:
    """One LangChain chat model for `selection`, with the role's timeout baked in.

    `max_retries=0` throughout: retry/failover policy belongs to the gateway's
    chain loop, not hidden inside an SDK.
    """
    provider, model, key = selection.provider, selection.model, selection.api_key

    if provider in ("openrouter", "groq", "openai"):
        from langchain_openai import ChatOpenAI

        base_url = {"openrouter": _OPENROUTER_BASE, "groq": _GROQ_BASE}.get(provider)
        chat = ChatOpenAI(
            model=model,
            api_key=key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
            streaming=streaming,
        )
        if provider == "openrouter":
            # Many OpenRouter free models (Nemotron, gpt-oss, Qwen3) are
            # "reasoning" models by default: they burn a hidden, unbounded
            # thinking budget BEFORE the first visible token — measured 70+s
            # of silence on Nemotron 3 Super, blowing the role timeout and
            # violating "the demo must feel instant". `reasoning.enabled=false`
            # is an OpenRouter-only unified control (400s on Groq/OpenAI —
            # never bind it there); harmless on models without extended
            # thinking. THE single highest-impact live finding from DocChat.
            chat = chat.bind(reasoning={"enabled": False})
        return chat
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=key,
            timeout=timeout,
            max_retries=0,
            max_tokens=4096,
            streaming=streaming,
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=key,
            timeout=timeout,
            max_retries=0,
        )
    raise ValueError(f"unknown provider: {provider!r}")  # runconfig already blocks this


def bind_json_mode(model: BaseChatModel, selection: Selection) -> Any:
    """Ask for a JSON object where the wire protocol supports it.

    Anthropic/Gemini have no `response_format` equivalent worth coupling to —
    the rewrite prompt already demands JSON and its parser strips fences and
    degrades on garbage, so prompt-level JSON is enough there.
    """
    if selection.provider in _OPENAI_COMPATIBLE:
        return model.bind(response_format={"type": "json_object"})
    return model


def parse_env_model(env_id: str) -> tuple[str, str]:
    """Split an env-config `provider/model` id (`openrouter/nvidia/x`, `groq/y`) into
    (provider, provider-native model id). Bare ids default to openrouter."""
    for provider in ("openrouter", "groq"):
        prefix = f"{provider}/"
        if env_id.startswith(prefix):
            return provider, env_id.removeprefix(prefix)
    return "openrouter", env_id


def demo_chain(role: str) -> list[Selection]:
    """Demo-mode failover chain for a role: env primary, then the OTHER free
    provider as a diverse fallback (Groq<->OpenRouter, whichever isn't primary).

    Deployments whose provider key is missing are dropped (a half-configured
    dev box still boots and degrades at call time — config.py's philosophy).
    """
    s = get_settings()
    env_id = getattr(s, _ROLE_ENV_FIELD[role])
    provider, model = parse_env_model(env_id)

    keys = {"openrouter": s.OPENROUTER_API_KEY, "groq": s.GROQ_API_KEY}
    chain: list[Selection] = []
    if keys.get(provider):
        chain.append(Selection(provider=provider, model=model, api_key=keys[provider]))

    # Diverse fallback: the provider the primary is NOT, with its pinned model.
    fb_provider = "openrouter" if provider == "groq" else "groq"
    fb_model = _OPENROUTER_FALLBACK_MODEL if fb_provider == "openrouter" else _GROQ_FALLBACK_MODEL
    if keys.get(fb_provider) and (fb_provider, fb_model) != (provider, model):
        chain.append(Selection(provider=fb_provider, model=fb_model, api_key=keys[fb_provider]))
    return chain
