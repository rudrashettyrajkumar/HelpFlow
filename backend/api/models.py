"""`GET /api/models` · `POST /api/models/validate` (ARCHITECTURE §4.2/§7.1,
spec E4 Req 4).

`GET /api/models` serves the static BYOK catalog (`llm/catalog.py`) verbatim
and cached — Model Studio renders provider cards, model pickers, and "how to
get a key" steps straight from this response; adding a model to the catalog
is the only change needed to surface it here.

`POST /api/models/validate` does a ~1-token live probe so Model Studio can
show "key works ✓" before the user commits to it in a chat/crawl. The key
NEVER appears in the response or in any log line here — only a typed
`error_code` a broken key can be diagnosed from (invariant #9; the leak-grep
test covers this file too).
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from backend.llm import catalog, factory
from backend.llm.runconfig import Selection
from backend.services import demo_budget, embed_signature
from backend.utils.config import get_settings

router = APIRouter()
_log = logging.getLogger("helpflow.api.models")


class ValidateRequest(BaseModel):
    provider: str
    model: str
    key: str
    kind: Literal["chat", "embed"] = "chat"


def _classify(exc: Exception) -> str:
    """A typed, user-safe error code — never the raw provider exception text,
    which could (depending on the SDK) echo request details."""
    text = str(exc).lower()
    if any(s in text for s in ("401", "unauthorized", "invalid_api_key", "authentication")):
        return "key_invalid"
    if "429" in text or "rate limit" in text or "quota" in text:
        return "rate_limited"
    if "404" in text or "not found" in text or "does not exist" in text:
        return "model_not_found"
    return "provider_error"


@router.get("/api/models")
async def get_models() -> dict:
    return catalog.catalog_payload()


@router.get("/api/demo-budget")
async def get_demo_budget() -> dict:
    """DESIGN CHOICE (flagged, spec E8 Req 4): no route exposed
    `services/demo_budget.remaining_today` before E8 — it existed since E4
    as a "best-effort UI helper" (its own docstring) with nothing calling it
    yet, since E4 was backend-only. Model Studio's demo-mode card needs it
    ("today's remaining shared budget"); this wires the existing helper to
    an endpoint rather than inventing new budget-tracking logic."""
    settings = get_settings()
    tomorrow = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return {
        "chat": {
            "remaining": await demo_budget.remaining_today("chat"),
            "cap": settings.DEMO_CHAT_DAILY,
        },
        "embed": {
            "remaining": await demo_budget.remaining_today("embed"),
            "cap": settings.DEMO_EMBED_DAILY,
        },
        "resets_at": tomorrow.isoformat(),
    }


@router.post("/api/models/validate")
async def validate_model(body: ValidateRequest) -> dict:
    if not catalog.is_known_provider(body.provider):
        return {"ok": False, "error_code": "unknown_provider"}
    if body.kind == "embed" and not catalog.is_embed_provider(body.provider):
        return {"ok": False, "error_code": "unknown_provider"}

    selection = Selection(provider=body.provider, model=body.model, api_key=body.key)
    started = time.monotonic()
    try:
        if body.kind == "embed":
            await embed_signature.embed(["ping"], selection, is_demo=False)
        else:
            model = factory.build_chat_model(selection, timeout=8.0)
            await model.ainvoke([{"role": "user", "content": "hi"}])
    except Exception as exc:  # noqa: BLE001 — a probe must classify, never 500 or echo the key
        code = _classify(exc)
        _log.info("model validate failed", extra={"provider": body.provider, "error_code": code})
        return {"ok": False, "error_code": code}
    return {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)}
