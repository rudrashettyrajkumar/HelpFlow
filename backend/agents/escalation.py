"""Escalation decision — deterministic, NO LLM call (ARCHITECTURE §3.2 STEP 4 / §5.2,
spec E3 Req 6).

DESIGN CHOICE (flagged — ARCHITECTURE §3.2/§12 and spec Req 6 are contradictory as
literally written): both list three independent escalate triggers — `route=='handoff'`,
`low_relevance`, and "the 2nd consecutive low-confidence turn" — as an OR. Read
literally, `low_relevance` alone already escalates on turn 1, which makes the streak
bullet unreachable and directly contradicts the spec's own acceptance criterion ("Two
consecutive low-confidence turns -> escalate on the SECOND") and required truth-table
test. The only reading that makes every bullet meaningful AND satisfies that acceptance
criterion: a single low-relevance turn gets one grace answer (a hedge, per
`citation_rules.md` — "say you don't have that handy, offer a human" — which is honest,
not fabrication) and increments the streak; a SECOND consecutive low-relevance turn
escalates as `repeated_low_conf`. `route=='handoff'` (explicit request or sensitive
intent) always escalates immediately regardless of streak — those are unambiguous and
never get a grace turn.

Pure function: no I/O, no randomness, exhaustively unit-testable. Returns the new
`low_conf_streak` value the caller persists on the conversation row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Action = Literal["answer", "escalate"]
Reason = Literal["user_requested", "sensitive_intent", "low_relevance", "repeated_low_conf"]


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: Reason | None
    new_streak: int


def decide(
    *,
    route: str,
    handoff_reason: str | None,
    low_relevance: bool,
    low_conf_streak: int,
) -> Decision:
    """The one place the escalate-vs-answer call is made.

    `route` is the rewrite agent's `route` (direct|retrieve|handoff); `handoff_reason` is
    its `handoff_reason` field (`"user_requested"` or None); `low_relevance` is the
    retrieval agent's best-cosine-below-threshold flag (False/unused for direct/handoff
    routes, which skip retrieval); `low_conf_streak` is the conversation's streak BEFORE
    this turn.
    """
    if route == "handoff":
        reason: Reason = (
            "user_requested" if handoff_reason == "user_requested" else "sensitive_intent"
        )
        return Decision(action="escalate", reason=reason, new_streak=low_conf_streak)

    if low_relevance:
        new_streak = low_conf_streak + 1
        if new_streak >= 2:
            return Decision(action="escalate", reason="repeated_low_conf", new_streak=new_streak)
        return Decision(action="answer", reason=None, new_streak=new_streak)

    return Decision(action="answer", reason=None, new_streak=0)
