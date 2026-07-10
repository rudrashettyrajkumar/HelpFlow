"""FastAPI app factory — the brain's entrypoint: `uvicorn backend.main:app`.

E1 mounts only `/health`; ingestion (E2), chat (E3), and console (E6) routers
are added by their epics. Startup does the idempotent, best-effort wiring:
warm the Redis TLS handshake, ensure the Qdrant collection, and preload the
prompt files — none of which may block boot (errors degrade, never break).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import (
    admin_sources,
    auth,
    chat,
    conversations,
    health,
    models,
    premium,
    widget,
    workspaces,
)
from backend.scripts.create_collection import ensure_collection
from backend.utils import redis_client, supabase_client
from backend.utils.config import get_settings
from backend.utils.guardrails import _responses

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("helpflow.app")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Pay the Upstash TLS handshake before the first user request (measured >2s
    # cold — it would otherwise blow the per-call timeout on that request).
    try:
        await redis_client.warm_up()
    except Exception as exc:  # noqa: BLE001 — warm-up is an optimization, not a gate
        _log.warning("redis warm-up failed; will warm on first use", extra={"reason": repr(exc)})
    # Idempotent collection/index setup (spec E1 Req 3: "called on startup too").
    try:
        await ensure_collection()
    except Exception as exc:  # noqa: BLE001 — collection setup is not a boot gate
        _log.warning("qdrant collection setup failed", extra={"reason": repr(exc)})
    # Preload + validate the prompt files once so a missing/empty prompt surfaces
    # at boot, not mid-conversation (cached thereafter).
    try:
        _responses()
    except Exception as exc:  # noqa: BLE001 — falls back to a hardcoded deflection
        _log.warning("prompt preload failed", extra={"reason": repr(exc)})
    yield
    # Best-effort clean shutdown of the DB pool on redeploy.
    try:
        await supabase_client.close_pool()
    except Exception as exc:  # noqa: BLE001
        _log.warning("db pool close failed", extra={"reason": repr(exc)})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="HelpFlow", version="0.1.0", lifespan=_lifespan)

    # CORS: the widget is embedded on arbitrary client sites and the console
    # lives on Vercel — both cross-origin. FRONTEND_ORIGIN is comma-separated;
    # "*" (the demo default) disables credentialed cookies (we use header tokens,
    # not cookies), so wildcard + tokens is safe here.
    origins = [o.strip() for o in settings.FRONTEND_ORIGIN.split(",") if o.strip()]
    allow_credentials = origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(admin_sources.router)
    app.include_router(chat.router)
    app.include_router(widget.router)
    app.include_router(models.router)
    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(premium.router)
    app.include_router(conversations.router)

    return app


app = create_app()
