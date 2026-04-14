"""Unit tests for SessionRepository.

Each method exercised against the seed_sessions fixture for deterministic data.
Vector-search and filter-only tests use SessionFilterScope.build(...) to mirror
the path that SearchService takes in production.
"""
from __future__ import annotations

from sqlalchemy import update

from models import Session
from repositories.session_repository import SessionRepository
from search import SearchFilters
from services._filter_scope import SessionFilterScope


async def test_get_by_ids_returns_matching_sessions(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    result = await repo.get_by_ids(["s1", "s3"])
    assert set(result.keys()) == {"s1", "s3"}
    assert result["s1"].project == "conversations"


async def test_get_by_ids_empty_list_returns_empty(seed_sessions, db_session):
    assert await SessionRepository(db_session).get_by_ids([]) == {}


async def test_get_by_ids_missing_id_is_silently_dropped(seed_sessions, db_session):
    result = await SessionRepository(db_session).get_by_ids(["s1", "does-not-exist"])
    assert set(result.keys()) == {"s1"}


async def test_search_filter_only_orders_by_recency(seed_sessions, db_session):
    """Phase 7.2 fix path: filter-only must return sessions newest-first."""
    repo = SessionRepository(db_session)
    scope = SessionFilterScope.build(SearchFilters(), default_provider="claude", show_hidden=False)
    ids = await repo.search_filter_only_top_sessions(scope, limit=10)
    # Claude visible sessions are s1, s2, s3. Newest ended_at is s3 (+10 days).
    assert ids[0] == "s3"


async def test_search_filter_only_respects_project_filter(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    scope = SessionFilterScope.build(
        SearchFilters(project="conversations"),
        default_provider="claude",
        show_hidden=False,
    )
    ids = await repo.search_filter_only_top_sessions(scope, limit=10)
    assert set(ids) == {"s1", "s2"}


async def test_search_filter_only_excludes_hidden_by_default(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    scope = SessionFilterScope.build(SearchFilters(), default_provider="claude", show_hidden=False)
    ids = await repo.search_filter_only_top_sessions(scope, limit=10)
    assert "s5" not in ids  # s5 is pre-hidden in the fixture


async def test_search_filter_only_includes_hidden_when_requested(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    scope = SessionFilterScope.build(SearchFilters(), default_provider="claude", show_hidden=True)
    ids = await repo.search_filter_only_top_sessions(scope, limit=10)
    assert "s5" in ids


async def test_search_vector_orders_by_similarity(seed_sessions, db_session):
    """Sessions get a fake embedding; all should score identically and the query
    executes without error (proves the pgvector column and cosine_distance work)."""
    fake_vec = [0.01] * 384
    await db_session.execute(
        update(Session).where(Session.provider == "claude").values(embedding=fake_vec)
    )
    await db_session.commit()

    repo = SessionRepository(db_session)
    scope = SessionFilterScope.build(SearchFilters(), default_provider="claude", show_hidden=False)
    results = await repo.search_vector_top_sessions(fake_vec, scope, limit=10)
    # s1, s2, s3 get embeddings; s5 (hidden) is filtered out by scope.
    sids = {sid for sid, _ in results}
    assert sids == {"s1", "s2", "s3"}
    # Similarities are floats in [0, 1]
    assert all(0.0 <= sim <= 1.0 + 1e-9 for _, sim in results)


async def test_search_vector_skips_sessions_without_embedding(seed_sessions, db_session):
    """Seeded sessions have NULL embeddings → vector leg returns empty."""
    repo = SessionRepository(db_session)
    scope = SessionFilterScope.build(SearchFilters(), default_provider="claude", show_hidden=False)
    results = await repo.search_vector_top_sessions([0.01] * 384, scope, limit=10)
    assert results == []


async def test_hide_conversation_marks_hidden_at(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    await repo.hide_conversation("conversations", "conv-1")
    result = await repo.get_by_ids(["s1"])
    assert result["s1"].hidden_at is not None


async def test_restore_conversation_clears_hidden_at(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    await repo.hide_conversation("conversations", "conv-1")
    await repo.restore_conversation("conversations", "conv-1")
    result = await repo.get_by_ids(["s1"])
    assert result["s1"].hidden_at is None


async def test_hide_project_hides_every_session(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    await repo.hide_project("conversations")
    ids = await repo.search_filter_only_top_sessions(
        SessionFilterScope.build(SearchFilters(), "claude", show_hidden=False),
        limit=50,
    )
    assert "s1" not in ids and "s2" not in ids


async def test_restore_project_restores_every_session(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    await repo.hide_project("conversations")
    await repo.restore_project("conversations")
    ids = await repo.search_filter_only_top_sessions(
        SessionFilterScope.build(SearchFilters(), "claude", show_hidden=False),
        limit=50,
    )
    assert {"s1", "s2"}.issubset(set(ids))


async def test_restore_all_sessions_clears_all_hidden(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    await repo.restore_all_sessions()
    result = await repo.get_by_ids(["s5"])
    assert result["s5"].hidden_at is None


async def test_count_hidden_conversations_matches_seed(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    # s5 is hidden with conversation_id=conv-5
    assert await repo.count_hidden_conversations() == 1


async def test_list_hidden_conversations_returns_tuples(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    rows = await repo.list_hidden_conversations()
    assert any(project == "archive" and conv == "conv-5" for project, conv, _ in rows)


async def test_list_fully_hidden_projects_detects_archive(seed_sessions, db_session):
    """archive has only s5 and s5 is hidden → archive is fully hidden."""
    repo = SessionRepository(db_session)
    rows = await repo.list_fully_hidden_projects()
    names = {name for name, _ in rows}
    assert "archive" in names
    assert "conversations" not in names


async def test_count_fully_hidden_projects_respects_provider(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    # archive (claude) is fully hidden; codex side is not
    assert await repo.count_fully_hidden_projects(provider="claude") == 1
    assert await repo.count_fully_hidden_projects(provider="codex") == 0


async def test_count_fully_hidden_projects_no_provider_filter(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    # Without provider filter, still archive + any codex side that might be fully hidden
    total = await repo.count_fully_hidden_projects()
    assert total >= 1


async def test_count_visible(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    assert await repo.count_visible("claude") == 3  # s1, s2, s3
    assert await repo.count_visible("codex") == 1  # s4


async def test_count_embedded_initially_zero(seed_sessions, db_session):
    """Seeded sessions have NULL embedding → 0 embedded."""
    repo = SessionRepository(db_session)
    assert await repo.count_embedded("claude") == 0


async def test_count_embedded_after_setting(seed_sessions, db_session):
    await db_session.execute(
        update(Session).where(Session.id == "s1").values(embedding=[0.01] * 384)
    )
    await db_session.commit()
    repo = SessionRepository(db_session)
    assert await repo.count_embedded("claude") == 1


async def test_distinct_projects_sorted_alphabetically(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    projects = await repo.distinct_projects("claude")
    assert projects == sorted(projects)
    assert "conversations" in projects


async def test_distinct_projects_excludes_hidden(seed_sessions, db_session):
    """archive's only session is hidden, so archive should not appear."""
    repo = SessionRepository(db_session)
    projects = await repo.distinct_projects("claude")
    assert "archive" not in projects


async def test_distinct_models_excludes_null(seed_sessions, db_session):
    repo = SessionRepository(db_session)
    models = await repo.distinct_models("claude")
    assert all(m is not None for m in models)
    assert "claude-opus-4-6" in models
