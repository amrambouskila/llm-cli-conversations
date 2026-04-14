"""Unit tests for StatsService — global header stats."""
from __future__ import annotations

from services.stats_service import StatsService


async def test_get_stats_shape(seed_sessions, db_session):
    data = await StatsService(db_session).get_stats("claude")
    for key in ("total_projects", "total_segments", "total_chars", "total_words",
                "total_tool_calls", "estimated_tokens", "monthly", "hidden"):
        assert key in data
    for h_key in ("segments", "conversations", "projects"):
        assert h_key in data["hidden"]


async def test_get_stats_visible_only(seed_sessions, db_session):
    data = await StatsService(db_session).get_stats("claude")
    assert data["total_projects"] == 2  # conversations + oft (archive hidden)
    assert data["total_segments"] == 5  # seg-1a, seg-1b, seg-2a, seg-2b, seg-3a


async def test_get_stats_codex(seed_sessions, db_session):
    data = await StatsService(db_session).get_stats("codex")
    assert data["total_projects"] == 1  # oft
    assert data["total_segments"] == 1


async def test_get_stats_hidden_counts(seed_sessions, db_session):
    """archive (s5) has conversation_id=conv-5 and is hidden → 1 hidden conversation."""
    data = await StatsService(db_session).get_stats("claude")
    assert data["hidden"]["conversations"] == 1
    assert data["hidden"]["projects"] == 1  # archive


async def test_get_stats_monthly_keyed_by_yyyy_mm(seed_sessions, db_session):
    data = await StatsService(db_session).get_stats("claude")
    for month_key in data["monthly"]:
        assert len(month_key) == 7  # "YYYY-MM"
        assert month_key[4] == "-"
    for entry in data["monthly"].values():
        assert "tokens" in entry and "requests" in entry


async def test_get_stats_empty_db(db_session):
    data = await StatsService(db_session).get_stats("claude")
    assert data["total_projects"] == 0
    assert data["total_segments"] == 0
    assert data["monthly"] == {}
