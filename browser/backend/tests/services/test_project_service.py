"""Unit tests for ProjectService — provider list + per-project aggregations."""
from __future__ import annotations

from services.project_service import ProjectService

# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

async def test_list_providers_returns_all_providers(seed_sessions, db_session):
    providers = await ProjectService(db_session).list_providers()
    ids = {p["id"] for p in providers}
    assert {"claude", "codex"}.issubset(ids)


async def test_list_providers_empty_db_still_returns_claude_default(db_session):
    """Even without data, the claude entry is inserted as a default."""
    providers = await ProjectService(db_session).list_providers()
    assert any(p["id"] == "claude" for p in providers)


async def test_list_providers_entry_shape(seed_sessions, db_session):
    providers = await ProjectService(db_session).list_providers()
    for p in providers:
        assert {"id", "name", "projects", "segments"} <= set(p.keys())


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

async def test_list_projects_returns_visible_only_by_default(seed_sessions, db_session):
    projects = await ProjectService(db_session).list_projects("claude", show_hidden=False)
    names = {p["name"] for p in projects}
    # archive is fully hidden → excluded
    assert "conversations" in names
    assert "oft" in names
    assert "archive" not in names


async def test_list_projects_includes_hidden_when_requested(seed_sessions, db_session):
    projects = await ProjectService(db_session).list_projects("claude", show_hidden=True)
    names = {p["name"] for p in projects}
    assert "archive" in names


async def test_list_projects_entry_shape(seed_sessions, db_session):
    projects = await ProjectService(db_session).list_projects("claude", show_hidden=False)
    assert projects
    entry = projects[0]
    assert {"name", "display_name", "total_requests", "total_files", "hidden", "stats"} <= set(entry.keys())
    stats = entry["stats"]
    for key in ("total_conversations", "total_words", "total_chars", "estimated_tokens",
                "total_tool_calls", "first_timestamp", "last_timestamp",
                "request_sizes", "conversation_timeline", "tool_breakdown"):
        assert key in stats


async def test_list_projects_counts_correctly(seed_sessions, db_session):
    projects = await ProjectService(db_session).list_projects("claude", show_hidden=False)
    conv = next(p for p in projects if p["name"] == "conversations")
    assert conv["total_requests"] == 4  # s1 has 2, s2 has 2 segments
    assert conv["stats"]["total_conversations"] == 2  # conv-1, conv-2


async def test_list_projects_hidden_flag_true_when_fully_hidden(seed_sessions, db_session):
    """show_hidden=True + archive fully hidden → hidden: true."""
    projects = await ProjectService(db_session).list_projects("claude", show_hidden=True)
    archive = next((p for p in projects if p["name"] == "archive"), None)
    assert archive is not None
    assert archive["hidden"] is True


async def test_list_projects_request_sizes_are_word_counts(seed_sessions, db_session):
    projects = await ProjectService(db_session).list_projects("claude", show_hidden=False)
    conv = next(p for p in projects if p["name"] == "conversations")
    # All 4 conversations segments' word_counts
    assert all(isinstance(n, int) for n in conv["stats"]["request_sizes"])


async def test_list_projects_empty_db(db_session):
    assert await ProjectService(db_session).list_projects("claude", False) == []
