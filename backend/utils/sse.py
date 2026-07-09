"""SSE formatting helpers shared by ingestion (E2) and conversation (E3) endpoints.

Ported from DocChat `utils/sse.py`. HelpFlow's SSE contract is deliberately
simpler than a resumable-stream system: there is no job queue and no
cross-reconnect producer registry (ARCHITECTURE §3.1 — "a queue is
over-engineering at this scale"). Each request drives its own generator for the
lifetime of that one HTTP connection; a widget reconnect (§8: "Last-Event-ID,
exponential retry") simply retries the request. This module owns only:

* **Frame formatting** — one-line JSON `data:` per SSE event, optional `id:`.
* **Heartbeat** — a `: ping` comment after `HEARTBEAT_INTERVAL_S` of producer
  silence, so proxies/browsers don't time out an idle connection, without ever
  dropping a token that arrives concurrently with the timer firing.

Event *names* and payload shapes (`token`, `sources`, `handoff`, `done`,
`human_turn`, the crawl progress events) belong to E2/E3, not here.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

# A heartbeat comment is emitted after this many seconds of producer silence
# (ARCHITECTURE §3.2 — "15s heartbeat").
HEARTBEAT_INTERVAL_S = 15.0

# Comment-line heartbeat. EventSource ignores comments, so it never disturbs
# event parsing or any `id:` a client may be tracking.
PING = ": ping\n\n"


def format_event(event: str, data: dict[str, Any], *, event_id: int | None = None) -> str:
    """One SSE frame: optional `id:`, the `event:` name, a one-line JSON `data:`."""
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def format_token(seq: int, text: str) -> str:
    """`event: token` frame carrying a monotonically increasing `seq` (ARCHITECTURE §3.2)."""
    return format_event("token", {"seq": seq, "t": text}, event_id=seq)


async def with_heartbeat(
    tokens: AsyncIterator[str],
    *,
    interval: float = HEARTBEAT_INTERVAL_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[str]:
    """Yield `tokens` through, injecting `PING` after `interval`s of silence.

    Races the pending "next token" wait against a sleep timer so a heartbeat
    never discards or delays a token that arrives at the same moment: on a
    heartbeat the wait task is kept and re-raced, never cancelled-and-recreated.
    `sleep` is injectable so tests can drive heartbeat cadence on a mocked clock.
    """
    iterator = tokens.__aiter__()
    next_task: asyncio.Task[str] | None = None
    try:
        while True:
            if next_task is None:
                next_task = asyncio.ensure_future(iterator.__anext__())
            timer = asyncio.ensure_future(sleep(interval))
            done, _pending = await asyncio.wait(
                {next_task, timer}, return_when=asyncio.FIRST_COMPLETED
            )
            if next_task in done:
                timer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await timer
                try:
                    yield next_task.result()
                except StopAsyncIteration:
                    return
                finally:
                    next_task = None
            else:
                yield PING  # silence — heartbeat, but KEEP next_task pending
    finally:
        if next_task is not None:
            next_task.cancel()
            with contextlib.suppress(BaseException):
                await next_task
