"""Unit tests for search.parse_query — every filter prefix and edge case."""
from __future__ import annotations

from datetime import date

import pytest

from search import ParsedQuery, SearchFilters, parse_query


def test_parse_query_returns_parsed_query_type():
    parsed = parse_query("hello")
    assert isinstance(parsed, ParsedQuery)
    assert isinstance(parsed.filters, SearchFilters)


def test_empty_string():
    parsed = parse_query("")
    assert parsed.text == ""
    assert parsed.filters == SearchFilters()


def test_whitespace_only():
    parsed = parse_query("   \t  ")
    assert parsed.text == ""
    assert parsed.filters == SearchFilters()


def test_free_text_only():
    parsed = parse_query("docker auth fix")
    assert parsed.text == "docker auth fix"
    assert parsed.filters == SearchFilters()


def test_project_filter_only():
    parsed = parse_query("project:conversations")
    assert parsed.text == ""
    assert parsed.filters.project == "conversations"


def test_model_filter():
    parsed = parse_query("model:opus refactor")
    assert parsed.text == "refactor"
    assert parsed.filters.model == "opus"


def test_provider_filter():
    parsed = parse_query("provider:codex")
    assert parsed.filters.provider == "codex"


def test_after_filter_valid_date():
    parsed = parse_query("after:2026-03-01 something")
    assert parsed.filters.after == date(2026, 3, 1)
    assert parsed.text == "something"


def test_before_filter_valid_date():
    parsed = parse_query("before:2026-04-01")
    assert parsed.filters.before == date(2026, 4, 1)
    assert parsed.text == ""


def test_after_filter_malformed_left_in_text():
    parsed = parse_query("after:not-a-date docker")
    assert parsed.filters.after is None
    # Malformed filter stays in the text query verbatim
    assert "after:not-a-date" in parsed.text
    assert "docker" in parsed.text


def test_before_filter_malformed_left_in_text():
    parsed = parse_query("before:bogus-date hello")
    assert parsed.filters.before is None
    assert "before:bogus-date" in parsed.text


def test_tool_single_value():
    parsed = parse_query("tool:Bash error")
    assert parsed.filters.tools == ["Bash"]
    assert parsed.text == "error"


def test_tool_multi_value():
    parsed = parse_query("tool:Bash,Edit refactor")
    assert parsed.filters.tools == ["Bash", "Edit"]
    assert parsed.text == "refactor"


def test_tool_filter_strips_empty_segments():
    parsed = parse_query("tool:Bash,,Edit")
    assert parsed.filters.tools == ["Bash", "Edit"]


def test_topic_filter():
    parsed = parse_query("topic:docker")
    assert parsed.filters.topic == "docker"


def test_cost_filter_valid():
    parsed = parse_query("cost:>5.00 docker")
    assert parsed.filters.min_cost == 5.0
    assert parsed.text == "docker"


def test_cost_filter_malformed_left_in_text():
    parsed = parse_query("cost:>abc hello")
    assert parsed.filters.min_cost is None
    assert "cost:>abc" in parsed.text


def test_turns_filter_valid():
    parsed = parse_query("turns:>10 refactor")
    assert parsed.filters.min_turns == 10
    assert parsed.text == "refactor"


def test_turns_filter_malformed_left_in_text():
    parsed = parse_query("turns:>three hello")
    assert parsed.filters.min_turns is None
    assert "turns:>three" in parsed.text


def test_combined_filters_no_text():
    parsed = parse_query("project:conversations model:opus after:2026-03-01")
    assert parsed.text == ""
    assert parsed.filters.project == "conversations"
    assert parsed.filters.model == "opus"
    assert parsed.filters.after == date(2026, 3, 1)


def test_combined_filters_with_text():
    parsed = parse_query("project:conversations tool:Bash,Edit after:2026-03-01 fix the docker auth")
    assert parsed.filters.project == "conversations"
    assert parsed.filters.tools == ["Bash", "Edit"]
    assert parsed.filters.after == date(2026, 3, 1)
    assert "fix the docker auth" in parsed.text


def test_case_insensitive_prefix():
    parsed = parse_query("PROJECT:conversations Tool:Bash")
    assert parsed.filters.project == "conversations"
    assert parsed.filters.tools == ["Bash"]


def test_whitespace_collapsed_after_filter_removal():
    parsed = parse_query("a   project:foo   b")
    assert parsed.filters.project == "foo"
    # Multiple spaces collapsed to single
    assert parsed.text == "a b"


def test_all_filters_present():
    raw = (
        "project:conversations model:opus provider:claude after:2026-01-01 "
        "before:2026-12-31 tool:Bash,Edit topic:docker cost:>1.5 turns:>5 "
        "real query text"
    )
    parsed = parse_query(raw)
    f = parsed.filters
    assert f.project == "conversations"
    assert f.model == "opus"
    assert f.provider == "claude"
    assert f.after == date(2026, 1, 1)
    assert f.before == date(2026, 12, 31)
    assert f.tools == ["Bash", "Edit"]
    assert f.topic == "docker"
    assert f.min_cost == 1.5
    assert f.min_turns == 5
    assert "real query text" in parsed.text


def test_malformed_filters_dont_short_circuit_others():
    # after: malformed but cost: valid — the valid one must still parse.
    parsed = parse_query("after:not-a-date cost:>2.5 query")
    assert parsed.filters.after is None
    assert parsed.filters.min_cost == 2.5
    assert "after:not-a-date" in parsed.text
    assert "query" in parsed.text


@pytest.mark.parametrize(
    "raw, expected_field, expected_value",
    [
        ("project:foo", "project", "foo"),
        ("model:bar", "model", "bar"),
        ("provider:claude", "provider", "claude"),
        ("topic:auth", "topic", "auth"),
    ],
)
def test_string_filters_parametrized(raw, expected_field, expected_value):
    parsed = parse_query(raw)
    assert getattr(parsed.filters, expected_field) == expected_value


@pytest.mark.parametrize(
    "raw, expected_min_cost",
    [
        ("cost:>0", 0.0),
        ("cost:>1", 1.0),
        ("cost:>10.5", 10.5),
        ("cost:>0.001", 0.001),
    ],
)
def test_cost_threshold_parametrized(raw, expected_min_cost):
    parsed = parse_query(raw)
    assert parsed.filters.min_cost == expected_min_cost


@pytest.mark.parametrize(
    "raw, expected_min_turns",
    [
        ("turns:>0", 0),
        ("turns:>1", 1),
        ("turns:>100", 100),
    ],
)
def test_turns_threshold_parametrized(raw, expected_min_turns):
    parsed = parse_query(raw)
    assert parsed.filters.min_turns == expected_min_turns
