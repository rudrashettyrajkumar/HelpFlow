"""`cluster_gaps._parse_themes` — the LLM JSON-output parser (spec E9 Req 4).
Pure function, no DB/network; `cluster_tenant`/`main` touch Postgres directly
and are a live exception (same as the rest of `backend/scripts/`), verified
by running the script, not by this suite."""

import pytest

from backend.scripts.cluster_gaps import _parse_themes


def test_parses_a_clean_json_array():
    raw = (
        '[{"theme": "Shipping to Canada", "frequency": 3, '
        '"example_questions": ["do you ship to Canada?"]}]'
    )
    themes = _parse_themes(raw)
    assert themes == [
        {
            "theme": "Shipping to Canada",
            "frequency": 3,
            "example_questions": ["do you ship to Canada?"],
        }
    ]


def test_strips_markdown_fences():
    raw = '```json\n[{"theme": "Returns", "frequency": 1, "example_questions": []}]\n```'
    themes = _parse_themes(raw)
    assert themes[0]["theme"] == "Returns"


def test_drops_zero_frequency_and_blank_theme_entries():
    raw = (
        '[{"theme": "Valid", "frequency": 2, "example_questions": []}, '
        '{"theme": "", "frequency": 5, "example_questions": []}, '
        '{"theme": "Zero", "frequency": 0, "example_questions": []}]'
    )
    themes = _parse_themes(raw)
    assert len(themes) == 1
    assert themes[0]["theme"] == "Valid"


def test_caps_example_questions_at_three():
    raw = (
        '[{"theme": "X", "frequency": 4, '
        '"example_questions": ["a", "b", "c", "d", "e"]}]'
    )
    themes = _parse_themes(raw)
    assert len(themes[0]["example_questions"]) == 3


def test_non_array_raises():
    with pytest.raises(ValueError):
        _parse_themes('{"theme": "not an array"}')


def test_malformed_json_raises():
    with pytest.raises(Exception):  # noqa: B017 — json.JSONDecodeError, no need to over-specify
        _parse_themes("not json at all")
