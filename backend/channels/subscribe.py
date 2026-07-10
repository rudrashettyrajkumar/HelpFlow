"""`GET /chat/subscribe` — live delivery of human replies + status changes
(ARCHITECTURE §3.3, spec E3 Req 11).

DESIGN CHOICE (flagged): ARCHITECTURE §3.3 offers "Postgres LISTEN/NOTIFY (or a 3s
poll fallback)". This ships the poll fallback: a true `LISTEN` needs one DEDICATED
asyncpg connection held open per open widget subscription, which would let a handful
of concurrently-open chat widgets exhaust the whole 8-connection pool
(`supabase_client.POOL_MAX_SIZE`) that also serves every other request. A 3s poll
against `conversations`/`messages` costs one short-lived pooled connection per tick
per subscriber — cheap, and the ARCHITECTURE text explicitly allows it. Revisit with
a real LISTEN (or a small dedicated connection) if E4/E6 show poll latency is a
problem in practice.

Reconnect-safe by construction: each call starts a fresh poll loop from "now" (no
Last-Event-ID state to restore) — a widget reconnect just opens a new subscription and
free-rides on `last_activity_at`/message history it already has locally.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from backend.channels import conversation_store
from backend.utils.sse import format_event

POLL_INTERVAL_S = 3.0


async def stream_conversation_events(
    conversation_id: str,
    *,
    interval: float = POLL_INTERVAL_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
):
    """Yield SSE frames for `conversation_id`: `{message}` (agent replies) and
    `{status}` changes, polling every `interval`s. Runs until the client disconnects
    (FastAPI stops iterating the generator) — an unknown/deleted conversation ends
    the stream immediately rather than polling forever on nothing.
    """
    convo = await conversation_store.get_conversation(conversation_id)
    if convo is None:
        return

    last_status: str | None = None
    last_seen: Any = None

    while True:
        convo = await conversation_store.get_conversation(conversation_id)
        if convo is None:
            return

        if convo["status"] != last_status:
            yield format_event("status", {"status": convo["status"]})
            last_status = convo["status"]

        new_messages = await conversation_store.list_messages_since(
            conversation_id, after=last_seen, roles=("agent",)
        )
        for message in new_messages:
            yield format_event(
                "message",
                {
                    "role": message["role"],
                    "body": message["body"],
                    "created_at": message["created_at"].isoformat(),
                },
            )
            last_seen = message["created_at"]

        await sleep(interval)
