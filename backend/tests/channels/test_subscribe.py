"""`/chat/subscribe` poll loop: status changes and agent replies are pushed as SSE
frames (ARCHITECTURE §3.3, spec E3 Required tests) — a human reply appears on an
open subscription."""

import json
from datetime import UTC, datetime
from unittest.mock import patch

from backend.channels.subscribe import stream_conversation_events


def _frames_to_events(frames: list[str]) -> list[dict]:
    events = []
    for frame in frames:
        lines = frame.strip().splitlines()
        event_line = next(line for line in lines if line.startswith("event: "))
        data_line = next(line for line in lines if line.startswith("data: "))
        events.append(
            {"event": event_line[len("event: ") :], "data": json.loads(data_line[len("data: ") :])}
        )
    return events


async def _noop_sleep(_seconds: float) -> None:
    return None


async def test_status_change_is_pushed_once():
    convo_sequence = iter(
        [
            {"status": "ai_handling"},
            {"status": "ai_handling"},
            {"status": "needs_human"},
        ]
    )

    async def fake_get_conversation(_conversation_id):
        return next(convo_sequence, None)

    async def fake_list_messages_since(_conversation_id, *, after, roles):
        return []

    with (
        patch(
            "backend.channels.subscribe.conversation_store.get_conversation", fake_get_conversation
        ),
        patch(
            "backend.channels.subscribe.conversation_store.list_messages_since",
            fake_list_messages_since,
        ),
    ):
        gen = stream_conversation_events("convo-1", sleep=_noop_sleep)
        frames = [await gen.__anext__() for _ in range(2)]
        await gen.aclose()

    events = _frames_to_events(frames)
    assert events[0] == {"event": "status", "data": {"status": "ai_handling"}}
    assert events[1] == {"event": "status", "data": {"status": "needs_human"}}


async def test_agent_reply_is_pushed_as_message_event():
    now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)

    async def fake_get_conversation(_conversation_id):
        return {"status": "human_assigned"}

    calls = {"n": 0}

    async def fake_list_messages_since(_conversation_id, *, after, roles):
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"role": "agent", "body": "Hi, I'm Priya, happy to help!", "created_at": now}]
        return []

    with (
        patch(
            "backend.channels.subscribe.conversation_store.get_conversation", fake_get_conversation
        ),
        patch(
            "backend.channels.subscribe.conversation_store.list_messages_since",
            fake_list_messages_since,
        ),
    ):
        gen = stream_conversation_events("convo-1", sleep=_noop_sleep)
        frames = [await gen.__anext__() for _ in range(2)]
        await gen.aclose()

    events = _frames_to_events(frames)
    assert events[0] == {"event": "status", "data": {"status": "human_assigned"}}
    assert events[1]["event"] == "message"
    assert events[1]["data"]["role"] == "agent"
    assert events[1]["data"]["body"] == "Hi, I'm Priya, happy to help!"


async def test_unknown_conversation_ends_the_stream_immediately():
    async def fake_get_conversation(_conversation_id):
        return None

    with patch(
        "backend.channels.subscribe.conversation_store.get_conversation", fake_get_conversation
    ):
        gen = stream_conversation_events("missing", sleep=_noop_sleep)
        frames = [frame async for frame in gen]

    assert frames == []
