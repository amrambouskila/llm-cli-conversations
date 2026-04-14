"""Unit tests for SegmentRepository — keyword search, snippets, hidden state ops."""
from __future__ import annotations

from repositories.segment_repository import SegmentRepository
from search import SearchFilters
from services._filter_scope import SessionFilterScope


async def test_get_with_session_returns_pair(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    result = await repo.get_with_session("seg-1a")
    assert result is not None
    seg, session = result
    assert seg.id == "seg-1a"
    assert session.project == "conversations"


async def test_get_with_session_missing_returns_none(seed_sessions, db_session):
    assert await SegmentRepository(db_session).get_with_session("no-such-segment") is None


async def test_search_keyword_finds_tsvector_match(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    scope = SessionFilterScope.build(SearchFilters(), "claude", show_hidden=False)
    results = await repo.search_keyword_top_sessions("docker", scope, show_hidden=False, limit=50)
    assert results
    sids = {sid for sid, _ in results}
    assert "s1" in sids  # s1's segments mention "docker"


async def test_search_keyword_respects_scope_filter(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    scope = SessionFilterScope.build(
        SearchFilters(project="oft"), "claude", show_hidden=False,
    )
    results = await repo.search_keyword_top_sessions("chart", scope, show_hidden=False, limit=50)
    sids = {sid for sid, _ in results}
    assert sids <= {"s3"}  # only s3 in project oft (claude side)


async def test_search_keyword_excludes_hidden_segments_by_default(seed_sessions, db_session):
    """Hide s1's segments, confirm they're excluded from keyword results."""
    repo = SegmentRepository(db_session)
    await repo.hide_segment("seg-1a")
    await repo.hide_segment("seg-1b")
    scope = SessionFilterScope.build(SearchFilters(), "claude", show_hidden=False)
    results = await repo.search_keyword_top_sessions("docker", scope, show_hidden=False, limit=50)
    sids = {sid for sid, _ in results}
    assert "s1" not in sids


async def test_search_keyword_empty_result(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    scope = SessionFilterScope.build(SearchFilters(), "claude", show_hidden=False)
    assert await repo.search_keyword_top_sessions("xyzzy_nomatch", scope, False, limit=50) == []


async def test_get_best_match_raw_texts_returns_one_per_session(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    texts = await repo.get_best_match_raw_texts(["s1"], "docker")
    assert "s1" in texts
    assert "docker" in texts["s1"].lower()


async def test_get_best_match_empty_ids(seed_sessions, db_session):
    assert await SegmentRepository(db_session).get_best_match_raw_texts([], "docker") == {}


async def test_get_first_raw_texts_returns_first_segment(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    texts = await repo.get_first_raw_texts(["s1"])
    # seg-1a has segment_index=0 so it's the first
    assert "seg-1a" not in texts  # we return raw_text, not ids
    assert texts["s1"].startswith("how do I fix docker")


async def test_get_first_raw_texts_empty_ids(seed_sessions, db_session):
    assert await SegmentRepository(db_session).get_first_raw_texts([]) == {}


async def test_list_project_segments_orders_by_timestamp(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    rows = await repo.list_project_segments("conversations", "claude", show_hidden=False)
    # 4 segments: 2 from s1 + 2 from s2, all visible
    assert len(rows) == 4
    timestamps = [seg.timestamp for seg, _ in rows if seg.timestamp]
    assert timestamps == sorted(timestamps)


async def test_list_project_segments_hides_hidden_by_default(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    await repo.hide_segment("seg-1a")
    rows = await repo.list_project_segments("conversations", "claude", show_hidden=False)
    assert "seg-1a" not in {seg.id for seg, _ in rows}


async def test_list_project_segments_includes_hidden_when_requested(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    await repo.hide_segment("seg-1a")
    rows = await repo.list_project_segments("conversations", "claude", show_hidden=True)
    assert "seg-1a" in {seg.id for seg, _ in rows}


async def test_project_exists_true(seed_sessions, db_session):
    assert await SegmentRepository(db_session).project_exists("conversations", "claude") is True


async def test_project_exists_false(seed_sessions, db_session):
    assert await SegmentRepository(db_session).project_exists("no-such", "claude") is False


async def test_list_conversation_segments_returns_all_segments(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    segs = await repo.list_conversation_segments("conversations", "conv-1", "claude")
    assert [s.id for s in segs] == ["seg-1a", "seg-1b"]


async def test_list_conversation_segments_empty_if_missing(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    assert await repo.list_conversation_segments("conversations", "ghost", "claude") == []


async def test_hide_and_restore_segment(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    await repo.hide_segment("seg-1a")
    row = await repo.get_with_session("seg-1a")
    assert row[0].hidden_at is not None
    await repo.restore_segment("seg-1a")
    row = await repo.get_with_session("seg-1a")
    assert row[0].hidden_at is None


async def test_count_hidden_initially_zero(seed_sessions, db_session):
    assert await SegmentRepository(db_session).count_hidden() == 0


async def test_count_hidden_after_hiding(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    await repo.hide_segment("seg-1a")
    assert await repo.count_hidden() == 1


async def test_restore_all_segments(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    await repo.hide_segment("seg-1a")
    await repo.hide_segment("seg-1b")
    await repo.restore_all_segments()
    assert await repo.count_hidden() == 0


async def test_list_hidden_returns_segment_session_pairs(seed_sessions, db_session):
    repo = SegmentRepository(db_session)
    await repo.hide_segment("seg-1a")
    rows = await repo.list_hidden()
    assert len(rows) == 1
    seg, session = rows[0]
    assert seg.id == "seg-1a"
    assert session.id == "s1"
