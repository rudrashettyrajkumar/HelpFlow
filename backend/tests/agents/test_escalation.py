"""Exhaustive truth table for the deterministic escalation decision (spec E3
Required tests). Pure function — no mocking needed."""

from backend.agents.escalation import decide


def test_handoff_route_user_requested_escalates_regardless_of_streak():
    d = decide(
        route="handoff", handoff_reason="user_requested", low_relevance=False, low_conf_streak=0
    )
    assert d.action == "escalate"
    assert d.reason == "user_requested"
    assert d.new_streak == 0


def test_handoff_route_without_user_request_is_sensitive_intent():
    d = decide(route="handoff", handoff_reason=None, low_relevance=False, low_conf_streak=0)
    assert d.action == "escalate"
    assert d.reason == "sensitive_intent"


def test_handoff_route_overrides_low_relevance():
    d = decide(
        route="handoff", handoff_reason="user_requested", low_relevance=True, low_conf_streak=1
    )
    assert d.action == "escalate"
    assert d.reason == "user_requested"
    # handoff is not a confidence event — streak passes through unchanged.
    assert d.new_streak == 1


def test_first_low_relevance_turn_answers_with_grace_and_increments_streak():
    d = decide(route="retrieve", handoff_reason=None, low_relevance=True, low_conf_streak=0)
    assert d.action == "answer"
    assert d.reason is None
    assert d.new_streak == 1


def test_second_consecutive_low_relevance_turn_escalates():
    d = decide(route="retrieve", handoff_reason=None, low_relevance=True, low_conf_streak=1)
    assert d.action == "escalate"
    assert d.reason == "repeated_low_conf"
    assert d.new_streak == 2


def test_third_consecutive_low_relevance_turn_still_escalates():
    d = decide(route="retrieve", handoff_reason=None, low_relevance=True, low_conf_streak=2)
    assert d.action == "escalate"
    assert d.reason == "repeated_low_conf"
    assert d.new_streak == 3


def test_confident_retrieve_answers_and_resets_streak():
    d = decide(route="retrieve", handoff_reason=None, low_relevance=False, low_conf_streak=1)
    assert d.action == "answer"
    assert d.reason is None
    assert d.new_streak == 0


def test_direct_route_answers_and_resets_streak():
    d = decide(route="direct", handoff_reason=None, low_relevance=False, low_conf_streak=1)
    assert d.action == "answer"
    assert d.new_streak == 0


def test_low_relevance_after_a_confident_turn_starts_a_fresh_streak():
    d = decide(route="retrieve", handoff_reason=None, low_relevance=True, low_conf_streak=0)
    assert d.action == "answer"
    assert d.new_streak == 1
