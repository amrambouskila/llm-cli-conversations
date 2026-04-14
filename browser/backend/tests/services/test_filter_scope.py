"""Unit tests for SessionFilterScope — pure filter-compilation helper.

Covers the Phase 7.2 date-range bug fix (dates pass as date objects, not strings)
and verifies every field in SearchFilters gets mapped to the right SQL condition.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from models import Session
from search import SearchFilters
from services._filter_scope import SessionFilterScope


def _compile(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_default_scope_filters_by_provider_and_hides_by_default():
    scope = SessionFilterScope.build(SearchFilters(), "claude", show_hidden=False)
    assert len(scope.session_conditions) == 2  # provider + hidden


def test_show_hidden_drops_hidden_condition():
    scope = SessionFilterScope.build(SearchFilters(), "claude", show_hidden=True)
    # Provider only
    assert len(scope.session_conditions) == 1


def test_filter_provider_override():
    scope = SessionFilterScope.build(
        SearchFilters(provider="codex"), default_provider="claude", show_hidden=False,
    )
    sql = _compile(scope.apply(select(Session.id)))
    assert "'codex'" in sql
    assert "'claude'" not in sql


def test_filter_project_adds_condition():
    scope = SessionFilterScope.build(
        SearchFilters(project="conversations"), "claude", show_hidden=False,
    )
    sql = _compile(scope.apply(select(Session.id)))
    assert "'conversations'" in sql


def test_filter_model_uses_case_insensitive_like():
    """Model filter compiles to case-insensitive LIKE (SQLAlchemy's .ilike())."""
    scope = SessionFilterScope.build(SearchFilters(model="opus"), "claude", show_hidden=False)
    sql = _compile(scope.apply(select(Session.id))).lower()
    # SQLAlchemy compiles ilike() to lower() LIKE lower() in the generic dialect
    assert "lower" in sql
    assert "'%opus%'" in sql


def test_filter_after_binds_date_not_string():
    """Phase 7.2 regression check — after must bind as DATE (or TIMESTAMPTZ-compatible),
    not as a raw VARCHAR string that Postgres can't cast."""
    d = date(2026, 3, 1)
    scope = SessionFilterScope.build(SearchFilters(after=d), "claude", show_hidden=False)
    sql = _compile(scope.apply(select(Session.id)))
    assert "2026-03-01" in sql
    # Must NOT include a trailing "T23:59:59" or similar string fragment
    assert "T23:59:59" not in sql


def test_filter_before_uses_exclusive_next_day():
    """Phase 7.2 fix: before → started_at < before + 1 day (exclusive upper bound)."""
    d = date(2026, 4, 1)
    scope = SessionFilterScope.build(SearchFilters(before=d), "claude", show_hidden=False)
    sql = _compile(scope.apply(select(Session.id)))
    # next day is 2026-04-02
    assert "2026-04-02" in sql
    assert "<" in sql


def test_filter_min_cost():
    scope = SessionFilterScope.build(SearchFilters(min_cost=1.5), "claude", show_hidden=False)
    sql = _compile(scope.apply(select(Session.id)))
    assert "1.5" in sql


def test_filter_min_turns():
    scope = SessionFilterScope.build(SearchFilters(min_turns=10), "claude", show_hidden=False)
    sql = _compile(scope.apply(select(Session.id)))
    assert "10" in sql


def test_tool_subquery_built_when_tools_present():
    scope = SessionFilterScope.build(
        SearchFilters(tools=["Bash", "Edit"]), "claude", show_hidden=False,
    )
    assert scope.tool_subquery is not None
    assert scope.topic_subquery is None


def test_topic_subquery_built_when_topic_present():
    scope = SessionFilterScope.build(
        SearchFilters(topic="docker"), "claude", show_hidden=False,
    )
    assert scope.topic_subquery is not None
    assert scope.tool_subquery is None


def test_apply_with_include_tool_topic_false_skips_subqueries():
    scope = SessionFilterScope.build(
        SearchFilters(tools=["Bash"], topic="docker"), "claude", show_hidden=False,
    )
    with_subq = _compile(scope.apply(select(Session.id), include_tool_topic=True))
    without_subq = _compile(scope.apply(select(Session.id), include_tool_topic=False))
    assert "tool_calls" in with_subq
    assert "tool_calls" not in without_subq


def test_all_filters_compose():
    """Every filter applies together — no short-circuit."""
    scope = SessionFilterScope.build(
        SearchFilters(
            project="conversations",
            model="opus",
            after=date(2026, 3, 1),
            before=date(2026, 4, 1),
            tools=["Bash"],
            topic="docker",
            min_cost=1.0,
            min_turns=5,
        ),
        "claude",
        show_hidden=False,
    )
    # provider + hidden + project + model + 2 date + cost + turns = 8
    assert len(scope.session_conditions) == 8
    assert scope.tool_subquery is not None
    assert scope.topic_subquery is not None


def test_before_uses_timedelta_arithmetic():
    """Spot check: before=2026-12-31 → next day is 2027-01-01 (year rollover)."""
    scope = SessionFilterScope.build(
        SearchFilters(before=date(2026, 12, 31)), "claude", show_hidden=False,
    )
    sql = _compile(scope.apply(select(Session.id)))
    assert "2027-01-01" in sql
    _ = timedelta  # keep the import used
