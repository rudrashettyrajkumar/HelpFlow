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

    # --- Models (migrate by changing env alone; never touch agent code) --
    # Gemini models served VIA OpenRouter (one gateway, one key); Groq is the
    # diverse failover (ARCHITECTURE §4). The key for each model is derived from
    # its provider prefix (llm_router._key_for), so a per-model migration stays a
    # one-line env change.
    ROUTER_MODEL: str = "openrouter/google/gemini-3.1-flash-lite-preview"
    ANSWER_MODEL: str = "openrouter/google/gemini-3-flash-preview"
    EMBED_MODEL: str = "openrouter/google/gemini-embedding-001"

    # --- Provider credentials -------------------------------------------
    OPENROUTER_API_KEY: str | None = None  # primary gateway (all LLM + embeddings)
    GROQ_API_KEY: str | None = None  # failover provider
    # Optional: only used if a *_MODEL id is pointed at a bare gemini/* id
    # (Gemini-direct). Not required — the stack runs entirely through OpenRouter.
    GEMINI_API_KEY: str | None = None

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
