"""The static BYOK provider/model catalog — one source of truth for backend AND UI.

Ported near-verbatim from DocChat v3 `backend/llm/catalog.py` (ARCHITECTURE §4.2).
`GET /api/models` serves this verbatim; Model Studio renders provider cards,
model pickers, accuracy meters, and "how to get a key" steps straight from it,
so adding a model here is the ONLY change needed to surface it end-to-end.

Accuracy is a coarse 1-5 editorial tier (5 = frontier reasoning, 1 = small/fast)
so users can trade accuracy against cost/speed at a glance — it is deliberately
NOT a benchmark number that would rot within a month. Model ids were verified
against provider docs in July 2026; free-tier lineups (Groq, OpenRouter `:free`)
change without notice, so `notes` carries the caveat where it matters.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any, Literal

ProviderId = Literal["groq", "openrouter", "openai", "anthropic", "gemini"]

# Providers that can serve 768-dim embeddings through an OpenAI-compatible
# `/embeddings` endpoint (Groq and Anthropic offer no embedding models).
EMBED_PROVIDERS: tuple[str, ...] = ("openrouter", "openai", "gemini")


@dataclass(frozen=True)
class ModelInfo:
    """One selectable chat or embedding model."""

    id: str  # provider-native model id, sent back verbatim in X-LLM-Model
    name: str  # display name
    accuracy: int  # 1-5 editorial tier (see module docstring)
    speed: Literal["blazing", "fast", "balanced", "deliberate"]
    cost: str  # short human string: "Free", "$0.15/M in", ...
    context: str  # human context window: "131K", "1M"
    free: bool = False
    recommended: bool = False
    notes: str = ""


@dataclass(frozen=True)
class ProviderInfo:
    """One key-issuing provider: its models plus how a user gets a key."""

    id: ProviderId
    name: str
    tagline: str
    kind: Literal["free", "freemium", "paid"]
    key_url: str
    key_steps: list[str]
    models: list[ModelInfo]
    embedding_models: list[ModelInfo] = field(default_factory=list)
    allows_custom_model: bool = False


_GROQ = ProviderInfo(
    id="groq",
    name="Groq",
    tagline="Open-source models on LPU hardware — genuinely free, absurdly fast",
    kind="free",
    key_url="https://console.groq.com/keys",
    key_steps=[
        "Go to console.groq.com and sign up — no credit card needed.",
        "Open the “API Keys” page from the left sidebar.",
        "Click “Create API Key”, name it (e.g. “helpflow”), and copy the gsk_… key.",
        "Paste it below. Free tier: ~30 requests/min, ~1,000/day per model.",
    ],
    models=[
        ModelInfo(
            id="llama-3.3-70b-versatile",
            name="Llama 3.3 70B",
            accuracy=3,
            speed="blazing",
            cost="Free",
            context="131K",
            free=True,
            recommended=True,
            notes="Best free all-rounder — strong grounded answers at ~280 tok/s.",
        ),
        ModelInfo(
            id="openai/gpt-oss-120b",
            name="GPT-OSS 120B",
            accuracy=4,
            speed="blazing",
            cost="Free",
            context="131K",
            free=True,
            notes="OpenAI's open-weights reasoner — highest accuracy on Groq's free tier.",
        ),
        ModelInfo(
            id="openai/gpt-oss-20b",
            name="GPT-OSS 20B",
            accuracy=3,
            speed="blazing",
            cost="Free",
            context="131K",
            free=True,
        ),
        ModelInfo(
            id="qwen/qwen3-32b",
            name="Qwen3 32B",
            accuracy=3,
            speed="blazing",
            cost="Free",
            context="131K",
            free=True,
            notes="Preview model on Groq — may be retired without notice.",
        ),
        ModelInfo(
            id="llama-3.1-8b-instant",
            name="Llama 3.1 8B Instant",
            accuracy=2,
            speed="blazing",
            cost="Free",
            context="131K",
            free=True,
            notes="Fastest option (~560 tok/s) — fine for simple lookups.",
        ),
    ],
)

_OPENROUTER = ProviderInfo(
    id="openrouter",
    name="OpenRouter",
    tagline="One key, 400+ models — includes a rotating free open-source tier",
    kind="freemium",
    key_url="https://openrouter.ai/settings/keys",
    key_steps=[
        "Go to openrouter.ai and sign in (Google/GitHub works).",
        "Open Settings → Keys and click “Create Key”.",
        "Copy the sk-or-… key and paste it below.",
        "Models ending in “:free” cost nothing (≈20 req/min, 50–200/day). "
        "Add credit later to unlock every paid model with the same key.",
    ],
    models=[
        ModelInfo(
            id="nvidia/nemotron-3-ultra-550b-a55b:free",
            name="Nemotron 3 Ultra 550B (free)",
            accuracy=5,
            speed="deliberate",
            cost="Free",
            context="1M",
            free=True,
            notes="Open frontier reasoner (NVIDIA, June 2026) — highest accuracy in "
            "the free lineup; deliberate speed.",
        ),
        ModelInfo(
            id="nvidia/nemotron-3-super-120b-a12b:free",
            name="Nemotron 3 Super 120B (free)",
            accuracy=4,
            speed="balanced",
            cost="Free",
            context="1M",
            free=True,
            recommended=True,
            notes="Open weights (NVIDIA Open License) — the model HelpFlow's demo "
            "mode answers with.",
        ),
        ModelInfo(
            id="nvidia/nemotron-3-nano-30b-a3b:free",
            name="Nemotron 3 Nano 30B (free)",
            accuracy=3,
            speed="fast",
            cost="Free",
            context="1M",
            free=True,
            notes="Smallest Nemotron tier — pick this when speed matters more than depth.",
        ),
        ModelInfo(
            id="openai/gpt-oss-120b:free",
            name="GPT-OSS 120B (free)",
            accuracy=4,
            speed="fast",
            cost="Free",
            context="131K",
            free=True,
            notes="Strongest general free model on OpenRouter right now.",
        ),
        ModelInfo(
            id="meta-llama/llama-3.3-70b-instruct:free",
            name="Llama 3.3 70B (free)",
            accuracy=3,
            speed="balanced",
            cost="Free",
            context="131K",
            free=True,
        ),
        ModelInfo(
            id="google/gemma-4-31b-it:free",
            name="Gemma 4 31B (free)",
            accuracy=3,
            speed="fast",
            cost="Free",
            context="262K",
            free=True,
        ),
        ModelInfo(
            id="qwen/qwen3-next-80b-a3b-instruct:free",
            name="Qwen3 Next 80B (free)",
            accuracy=3,
            speed="fast",
            cost="Free",
            context="262K",
            free=True,
        ),
    ],
    embedding_models=[
        ModelInfo(
            id="nvidia/llama-nemotron-embed-vl-1b-v2:free",
            name="Nemotron Embed 1B (free)",
            accuracy=3,
            speed="fast",
            cost="Free",
            context="131K",
            free=True,
            recommended=True,
            notes="Open-source NVIDIA embedder — free on OpenRouter, Matryoshka "
            "768-dim. Same model HelpFlow's demo mode uses.",
        ),
        ModelInfo(
            id="qwen/qwen3-embedding-0.6b",
            name="Qwen3 Embedding 0.6B",
            accuracy=3,
            speed="fast",
            cost="~$0.01/M tokens",
            context="32K",
            notes="Open-source embedder, pinned to 768 dimensions. Needs credit.",
        ),
        ModelInfo(
            id="openai/text-embedding-3-small",
            name="text-embedding-3-small",
            accuracy=3,
            speed="fast",
            cost="$0.02/M tokens",
            context="8K",
        ),
    ],
    allows_custom_model=True,
)

_OPENAI = ProviderInfo(
    id="openai",
    name="OpenAI",
    tagline="GPT-5.x flagship quality — paid key required",
    kind="paid",
    key_url="https://platform.openai.com/api-keys",
    key_steps=[
        "Go to platform.openai.com and sign in.",
        "Open Settings → Billing and add a payment method (min $5 credit).",
        "Open “API keys” → “Create new secret key” and copy the sk-… key.",
        "Paste it below — usage is billed to your OpenAI account.",
    ],
    models=[
        ModelInfo(
            id="gpt-5.5",
            name="GPT-5.5",
            accuracy=5,
            speed="deliberate",
            cost="$$$",
            context="400K",
            notes="OpenAI's flagship reasoner — top accuracy for hard support questions.",
        ),
        ModelInfo(
            id="gpt-5.4",
            name="GPT-5.4",
            accuracy=4,
            speed="balanced",
            cost="$2.50/M in",
            context="400K",
        ),
        ModelInfo(
            id="gpt-5.4-mini",
            name="GPT-5.4 mini",
            accuracy=3,
            speed="fast",
            cost="$",
            context="400K",
            recommended=True,
            notes="Best price/accuracy balance for grounded support answers.",
        ),
        ModelInfo(
            id="gpt-4.1",
            name="GPT-4.1",
            accuracy=4,
            speed="balanced",
            cost="$2/M in",
            context="1M",
            notes="Pick this for very large knowledge bases (1M-token context).",
        ),
        ModelInfo(
            id="gpt-4o-mini",
            name="GPT-4o mini",
            accuracy=2,
            speed="fast",
            cost="$0.15/M in",
            context="128K",
            notes="Legacy budget option — still fine for simple FAQs.",
        ),
    ],
    embedding_models=[
        ModelInfo(
            id="text-embedding-3-small",
            name="text-embedding-3-small",
            accuracy=3,
            speed="fast",
            cost="$0.02/M tokens",
            context="8K",
            recommended=True,
        ),
        ModelInfo(
            id="text-embedding-3-large",
            name="text-embedding-3-large",
            accuracy=4,
            speed="balanced",
            cost="$0.13/M tokens",
            context="8K",
        ),
    ],
)

_ANTHROPIC = ProviderInfo(
    id="anthropic",
    name="Anthropic",
    tagline="Claude — highest answer accuracy and citation faithfulness",
    kind="paid",
    key_url="https://console.anthropic.com/settings/keys",
    key_steps=[
        "Go to console.anthropic.com and sign in.",
        "Open Settings → Billing and add credit (min $5).",
        "Open “API Keys” → “Create Key” and copy the sk-ant-… key.",
        "Paste it below — usage is billed to your Anthropic account.",
    ],
    models=[
        ModelInfo(
            id="claude-fable-5",
            name="Claude Fable 5",
            accuracy=5,
            speed="deliberate",
            cost="$$$",
            context="200K",
            notes="Anthropic's frontier model — maximum accuracy for nuanced support cases.",
        ),
        ModelInfo(
            id="claude-opus-4-8",
            name="Claude Opus 4.8",
            accuracy=5,
            speed="balanced",
            cost="$$$",
            context="200K",
        ),
        ModelInfo(
            id="claude-sonnet-5",
            name="Claude Sonnet 5",
            accuracy=4,
            speed="fast",
            cost="$$",
            context="200K",
            recommended=True,
            notes="The sweet spot — near-Opus accuracy at a fraction of the cost.",
        ),
        ModelInfo(
            id="claude-haiku-4-5-20251001",
            name="Claude Haiku 4.5",
            accuracy=3,
            speed="blazing",
            cost="$",
            context="200K",
        ),
    ],
)

_GEMINI = ProviderInfo(
    id="gemini",
    name="Google Gemini",
    tagline="Gemini 3.x — generous free tier with an AI Studio key",
    kind="freemium",
    key_url="https://aistudio.google.com/apikey",
    key_steps=[
        "Go to aistudio.google.com/apikey and sign in with any Google account.",
        "Click “Create API key” (no credit card needed for the free tier).",
        "Copy the AIza… key and paste it below.",
        "Free-tier quotas apply per model; add billing later for higher limits.",
    ],
    models=[
        ModelInfo(
            id="gemini-3.5-flash",
            name="Gemini 3.5 Flash",
            accuracy=4,
            speed="fast",
            cost="Free tier",
            context="1M",
            free=True,
            recommended=True,
            notes="Near-Pro accuracy at Flash speed — free-tier quota included.",
        ),
        ModelInfo(
            id="gemini-2.5-pro",
            name="Gemini 2.5 Pro",
            accuracy=4,
            speed="deliberate",
            cost="$$",
            context="1M",
            notes="Deep reasoning for complex support cases.",
        ),
        ModelInfo(
            id="gemini-2.5-flash",
            name="Gemini 2.5 Flash",
            accuracy=3,
            speed="fast",
            cost="Free tier",
            context="1M",
            free=True,
        ),
        ModelInfo(
            id="gemini-3.1-flash-lite",
            name="Gemini 3.1 Flash-Lite",
            accuracy=2,
            speed="blazing",
            cost="Free tier",
            context="1M",
            free=True,
        ),
    ],
    embedding_models=[
        ModelInfo(
            id="gemini-embedding-001",
            name="Gemini Embedding 001",
            accuracy=4,
            speed="fast",
            cost="Free tier",
            context="8K",
            recommended=True,
            notes="Google's embedder with a free-tier quota — pinned to 768 dimensions.",
        ),
    ],
)

PROVIDERS: tuple[ProviderInfo, ...] = (_GROQ, _OPENROUTER, _OPENAI, _ANTHROPIC, _GEMINI)

_BY_ID: dict[str, ProviderInfo] = {p.id: p for p in PROVIDERS}


def get_provider(provider_id: str) -> ProviderInfo | None:
    return _BY_ID.get(provider_id)


def is_known_provider(provider_id: str) -> bool:
    return provider_id in _BY_ID


def is_embed_provider(provider_id: str) -> bool:
    return provider_id in EMBED_PROVIDERS


@lru_cache
def catalog_payload() -> dict[str, Any]:
    """The JSON body of `GET /api/models` (cached — the catalog is static)."""
    return {
        "providers": [asdict(p) for p in PROVIDERS],
        "embed_providers": list(EMBED_PROVIDERS),
    }
