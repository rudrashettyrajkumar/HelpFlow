"""Per-request BYOK selection, parsed from headers at the API boundary.

Ported near-verbatim from DocChat v3 `backend/llm/runconfig.py` (ARCHITECTURE
§4.4). HelpFlow never stores a user's provider key: the browser keeps it in
localStorage and sends it on each request via headers —

    X-LLM-Provider / X-LLM-Model / X-LLM-Key          (chat model)
    X-Embed-Provider / X-Embed-Model / X-Embed-Key    (embeddings)

No headers → **demo mode**: the server's own env-configured models and keys
(Raj's Groq/OpenRouter free-tier keys) with the existing per-day budget. Any
BYOK header present → the whole chat (or embed) trio is validated here, once,
so agents downstream can trust a `RunConfig` blindly.

This module is pure parsing/validation — no I/O, no provider SDKs, and never
logs/stores/echoes the key itself (invariant #9) — which is what keeps the
400s fast (rejected before any stream/LLM work starts) and this module
trivially testable for the leak-grep requirement.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from backend.llm import catalog

_log = logging.getLogger("helpflow.runconfig")

_MAX_KEY_LEN = 256
_MAX_MODEL_LEN = 128


class BYOKError(ValueError):
    """A user-correctable BYOK header problem → surfaced as a 422 JSON body."""


@dataclass(frozen=True)
class Selection:
    """One validated (provider, model, api_key) triple."""

    provider: str
    model: str
    api_key: str


@dataclass(frozen=True)
class RunConfig:
    """Everything model-related one request runs with.

    `chat`/`embed` of `None` mean "use the server's env-configured default"
    (demo mode) — the two halves are independent, so a user can bring a Groq
    chat key while embeddings stay on the server default.
    """

    chat: Selection | None = None
    embed: Selection | None = None

    @property
    def is_byok(self) -> bool:
        return self.chat is not None or self.embed is not None


#: The demo-mode singleton (also what tests and internal callers default to).
DEFAULT = RunConfig()


def _clean(value: str | None, *, field: str, max_len: int) -> str:
    text = (value or "").strip()
    if not text:
        raise BYOKError(f"missing {field}")
    if len(text) > max_len or any(ch.isspace() for ch in text):
        raise BYOKError(f"invalid {field}")
    return text


def _chat_selection(headers: Mapping[str, str]) -> Selection | None:
    provider_h = headers.get("x-llm-provider")
    model_h = headers.get("x-llm-model")
    key_h = headers.get("x-llm-key")
    if not any((provider_h, model_h, key_h)):
        return None

    provider = _clean(provider_h, field="X-LLM-Provider", max_len=32).lower()
    info = catalog.get_provider(provider)
    if info is None:
        raise BYOKError(f"unknown provider {provider!r}")
    api_key = _clean(key_h, field="X-LLM-Key", max_len=_MAX_KEY_LEN)

    if model_h is None or not model_h.strip():
        # Header trio sent without a model: fall back to the provider's
        # recommended pick rather than failing a whole chat turn over it.
        model = next((m.id for m in info.models if m.recommended), info.models[0].id)
    else:
        model = _clean(model_h, field="X-LLM-Model", max_len=_MAX_MODEL_LEN)
        known = any(m.id == model for m in info.models)
        if not known and not info.allows_custom_model:
            # Permissive by design: new provider models appear faster than this
            # catalog updates. The provider itself will reject a truly bad id.
            _log.info(
                "byok model not in catalog; passing through",
                extra={"provider": provider, "model": model},
            )
    return Selection(provider=provider, model=model, api_key=api_key)


def _embed_selection(headers: Mapping[str, str]) -> Selection | None:
    provider_h = headers.get("x-embed-provider")
    model_h = headers.get("x-embed-model")
    key_h = headers.get("x-embed-key")
    if not any((provider_h, model_h, key_h)):
        return None

    provider = _clean(provider_h, field="X-Embed-Provider", max_len=32).lower()
    if not catalog.is_embed_provider(provider):
        raise BYOKError(
            f"provider {provider!r} cannot serve embeddings; "
            f"use one of {', '.join(catalog.EMBED_PROVIDERS)}"
        )
    api_key = _clean(key_h, field="X-Embed-Key", max_len=_MAX_KEY_LEN)

    if model_h is None or not model_h.strip():
        info = catalog.get_provider(provider)
        candidates = info.embedding_models if info else []
        if not candidates:
            raise BYOKError(f"missing X-Embed-Model for provider {provider!r}")
        model = next((m.id for m in candidates if m.recommended), candidates[0].id)
    else:
        model = _clean(model_h, field="X-Embed-Model", max_len=_MAX_MODEL_LEN)
    return Selection(provider=provider, model=model, api_key=api_key)


def from_headers(headers: Mapping[str, str]) -> RunConfig:
    """Parse + validate the BYOK headers of one request (raises `BYOKError`).

    `headers` is expected to be case-insensitive (starlette's `Headers` is);
    plain dicts in tests should use lowercase keys.
    """
    return RunConfig(chat=_chat_selection(headers), embed=_embed_selection(headers))
