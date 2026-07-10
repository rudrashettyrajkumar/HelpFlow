"""Single source of truth for all configuration (spec E1 Req 1).

CLAUDE.md invariant #8: every model ID, key, url, limit, and threshold reaches
the code from an environment variable *through this module* — never `os.getenv`
elsewhere, never a hardcoded model string in agent code. Values mirror
ARCHITECTURE.md §4 (models), §7 (interfaces / rate limits), and §9 (infra).

Ported from MyShiva/DocChat `config.py` and extended for HelpFlow's fusion:
Supabase stage machine (LeadFlow), the escalation threshold, crawl caps, the
sensitive-intent set, the admin/handoff tokens, and the per-widget rate limits.
"""

import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger("helpflow.config")

# Keys that MUST be present before prod traffic. The LLM gateways, all three
# data stores (vectors, Postgres, cache), and the admin/handoff shared secrets
# are load-bearing: a prod box that can neither reach a model, persist a
# conversation, rate-limit, nor authenticate the handoff webhook is broken.
REQUIRED_IN_PROD: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "SUPABASE_DB_URL",
    "UPSTASH_URL",
    "UPSTASH_TOKEN",
    "ADMIN_TOKEN",
    "HANDOFF_TOKEN",
    "JWT_SECRET",
)


class Settings(BaseSettings):
    """Typed, env-backed settings. Reads `.env` if present (dev only)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Runtime ---------------------------------------------------------
    ENV: str = "dev"
    # Comma-separated allowed origins for the widget/console (CORS). The widget
    # is embedded on arbitrary client sites, so this is permissive in the demo
    # ("*") but overridable per deploy.
    FRONTEND_ORIGIN: str = "*"

    # --- Demo-mode models (v2, spec E4 Req 9 — migrate by env alone; never
    # touch agent code). Free-tier open-source ONLY (ARCHITECTURE §4.3):
    # Groq's Llama 3.3 70B primary for both roles, OpenRouter's NVIDIA
    # Nemotron 3 Super the diverse fallback (`llm/factory.py:demo_chain`).
    # BYOK requests ignore these entirely (`llm/runconfig.py`).
    DEMO_REWRITER_MODEL: str = "groq/llama-3.3-70b-versatile"
    DEMO_ANSWERER_MODEL: str = "groq/llama-3.3-70b-versatile"
    DEMO_EMBED_MODEL: str = "openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free"

    # --- Provider credentials (demo mode only; BYOK keys arrive per-request) --
    OPENROUTER_API_KEY: str | None = None  # primary gateway (chat + embeddings)
    GROQ_API_KEY: str | None = None  # diverse failover provider
    GEMINI_API_KEY: str | None = None  # optional: not used by demo mode (Groq/OpenRouter only)

    # --- Demo-mode shared daily budget (Upstash `hf:demo:{yyyymmdd}:*`, spec E4
    # Req 6) — checked BEFORE every demo-mode provider call; BYOK never counts
    # against these.
    DEMO_CHAT_DAILY: int = 150
    DEMO_EMBED_DAILY: int = 100

    # --- FlashRank cross-encoder rerank (spec E4 Req 1, ~4MB ONNX, CPU) -------
    RERANK_ENABLED: bool = True

    # --- Vectors (Qdrant) -----------------------------------------------
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "helpflow_chunks"

    # --- Supabase / Postgres --------------------------------------------
    # The brain talks to Postgres over asyncpg (guarded UPDATEs + LISTEN/NOTIFY,
    # ARCHITECTURE §5.2/§3.3), so SUPABASE_DB_URL (the SESSION POOLER connection
    # string) is the load-bearing one — it connects as a privileged role that
    # bypasses RLS, which is exactly the "service-role, server-only" contract.
    # SUPABASE_URL + the two API keys exist for the console (PostgREST via the
    # anon key against the masked views) and for schema assertions.
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_KEY: str | None = None
    SUPABASE_DB_URL: str | None = None

    # --- Cache / rate limits (Upstash Redis, `hf:` prefix) ---------------
    UPSTASH_URL: str | None = None
    UPSTASH_TOKEN: str | None = None

    # --- Shared secrets (ARCHITECTURE §7) --------------------------------
    # ADMIN_TOKEN gates the owner /admin/* routes (simple bearer per the demo).
    # HANDOFF_TOKEN is the X-Handoff-Token the brain sends n8n and n8n checks.
    ADMIN_TOKEN: str | None = None
    HANDOFF_TOKEN: str | None = None
    # Where the brain POSTs the handoff webhook (n8n WF-H). Optional at boot; a
    # missing url degrades the escalate path to "logged, not notified" (E4).
    N8N_HANDOFF_URL: str | None = None

    # --- Accounts / JWT (E5, ARCHITECTURE §7.1) ---------------------------
    # HS256 signing key for our OWN JWT (never a third-party auth provider).
    JWT_SECRET: str | None = None
    JWT_TTL_DAYS: int = 7

    # --- Premium gate (E5, ARCHITECTURE §3.0/§5.3/§7.2) -------------------
    # Raj's contact links on the 403 gate payload — env, never hardcoded
    # (invariant #8). LEAD_TOKEN is the X-Lead-Token shared with n8n WF-P
    # (E6); N8N_PREMIUM_LEAD_URL follows N8N_HANDOFF_URL's degrade pattern —
    # optional at boot, a missing url just skips the best-effort notify (the
    # premium_leads row is the source of truth either way).
    RAJ_LINKEDIN_URL: str | None = None
    RAJ_WHATSAPP_URL: str | None = None
    RAJ_EMAIL: str | None = None
    LEAD_TOKEN: str | None = None
    N8N_PREMIUM_LEAD_URL: str | None = None
    PREMIUM_CONTACT_DAILY_PER_IP: int = 3

    # --- Trial caps (E5, ARCHITECTURE §5.3) -------------------------------
    # plan='trial' workspaces clamp to these; plan='premium' (and the seeded
    # plan='demo' tenant) use the v1 limits above (MAX_PAGES / RATE_MESSAGES_
    # PER_TENANT_DAY) unclamped.
    MAX_TRIAL_PAGES: int = 25
    TRIAL_MESSAGES_DAILY: int = 40

    # --- Tunables (ARCHITECTURE §4/§7/§9) --------------------------------
    MAX_CONCURRENT_LLM_CALLS: int = 8
    MAX_PAGES: int = 50  # crawl cap per source (ARCHITECTURE §3.1)
    CHUNK_TOKENS: int = 450
    CHUNK_OVERLAP: int = 80
    EMBED_BATCH_SIZE: int = 100
    # Escalation: best cosine below this ⇒ low_relevance ⇒ escalate not guess
    # (ARCHITECTURE §3.2 STEP 3/4, invariant #1). Grounded-or-handoff.
    RELEVANCE_THRESHOLD: float = 0.30
    # Intents that ALWAYS reach a human (ARCHITECTURE §3.2). Comma-separated in
    # env; read the parsed form via `sensitive_intents`.
    SENSITIVE_INTENTS: str = "refund,complaint,cancel,human"

    # --- Rate limits (ARCHITECTURE §7; enforced in E2/E3 middleware) -----
    RATE_MESSAGES_PER_CONVO_HOUR: int = 30
    RATE_MESSAGES_PER_TENANT_DAY: int = 200
    RATE_CRAWLS_PER_TENANT_DAY: int = 4

    @property
    def sensitive_intents(self) -> frozenset[str]:
        """The sensitive-intent set the escalation decision consumes (§3.2).

        Parsed from the comma-separated `SENSITIVE_INTENTS` env so the retarget
        surface (ARCHITECTURE §6) stays a one-line config edit.
        """
        return frozenset(
            part.strip().lower() for part in self.SENSITIVE_INTENTS.split(",") if part.strip()
        )

    @model_validator(mode="after")
    def _require_keys_in_prod(self) -> "Settings":
        """Fail fast in prod on any missing required key; warn-only in dev.

        Errors degrade, never break (CLAUDE.md invariant #7): a half-configured
        *dev* box still boots so the developer can work on the parts that are
        wired up. A half-configured *prod* box must never accept traffic.
        """
        missing = [k for k in REQUIRED_IN_PROD if not getattr(self, k)]
        if not missing:
            return self
        if self.ENV == "prod":
            raise ValueError(f"Missing required config in prod: {', '.join(missing)}")
        _log.warning(
            "Config incomplete (ENV=%s): missing %s — dev boot continues.",
            self.ENV,
            ", ".join(missing),
        )
        return self


@lru_cache
def get_settings() -> Settings:
    """Lazily-built, cached settings singleton."""
    return Settings()
