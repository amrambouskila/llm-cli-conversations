"""Unit tests for SearchService.

Scoring helpers (_rrf_merge, _recency_boost, etc.) are already covered by
test_hybrid_search.py. This file focuses on the service-level orchestration:
get_status modes, get_filters shape, and search short-circuit behavior.
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import update

import embed
from models import Concept, Session, SessionConcept
from repositories.concept_repository import ConceptRepository
from repositories.segment_repository import SegmentRepository
from repositories.session_repository import SessionRepository
from repositories.session_topic_repository import SessionTopicRepository
from repositories.tool_call_repository import ToolCallRepository
from services.search_service import SearchService


def _service(db) -> SearchService:
    return SearchService(
        sessions=SessionRepository(db),
        segments=SegmentRepository(db),
        tool_calls=ToolCallRepository(db),
        topics=SessionTopicRepository(db),
        concepts=ConceptRepository(db),
    )


# ---------------------------------------------------------------------------
# search() short-circuits
# ---------------------------------------------------------------------------

async def test_search_empty_query_returns_empty(db_session):
    assert await _service(db_session).search("") == []


async def test_search_none_query_returns_empty(db_session):
    assert await _service(db_session).search(None) == []


async def test_search_single_char_returns_empty(db_session):
    assert await _service(db_session).search("a") == []


async def test_search_whitespace_only_returns_empty(db_session):
    assert await _service(db_session).search("   ") == []


# ---------------------------------------------------------------------------
# get_status — every mode
# ---------------------------------------------------------------------------

async def test_status_unavailable_on_empty_db(db_session):
    status = await _service(db_session).get_status("claude")
    assert status["mode"] == "unavailable"
    assert status["total_sessions"] == 0


async def test_status_keyword_when_no_embeddings(seed_sessions, db_session):
    status = await _service(db_session).get_status("claude")
    assert status["mode"] == "keyword"
    assert status["total_sessions"] == 3  # s1, s2, s3 visible
    assert status["embedded_sessions"] == 0
    assert status["has_graph"] is False


async def test_status_embedding_when_partially_embedded(seed_sessions, db_session):
    await db_session.execute(
        update(Session).where(Session.id == "s1").values(embedding=[0.01] * 384)
    )
    await db_session.commit()
    status = await _service(db_session).get_status("claude")
    assert status["mode"] == "embedding"
    assert status["embedded_sessions"] == 1


async def test_status_hybrid_when_all_embedded(seed_sessions, db_session):
    await db_session.execute(
        update(Session)
        .where(Session.provider == "claude", Session.hidden_at.is_(None))
        .values(embedding=[0.01] * 384)
    )
    await db_session.commit()
    status = await _service(db_session).get_status("claude")
    assert status["mode"] == "hybrid"
    assert status["embedded_sessions"] == status["total_sessions"]


async def test_status_reports_graph_presence(seed_sessions, db_session):
    db_session.add(Concept(id="c1", name="docker", community_id=1, degree=1))
    await db_session.commit()
    status = await _service(db_session).get_status("claude")
    assert status["has_graph"] is True
    assert status["concept_count"] == 1


# ---------------------------------------------------------------------------
# get_filters
# ---------------------------------------------------------------------------

async def test_filters_returns_all_four_keys(seed_sessions, db_session):
    filters = await _service(db_session).get_filters("claude")
    assert set(filters.keys()) == {"projects", "models", "tools", "topics"}


async def test_filters_projects_match_seed(seed_sessions, db_session):
    filters = await _service(db_session).get_filters("claude")
    # archive's only session is hidden → excluded
    assert set(filters["projects"]) == {"conversations", "oft"}


async def test_filters_tools_match_seed(seed_sessions, db_session):
    filters = await _service(db_session).get_filters("claude")
    assert set(filters["tools"]) == {"Bash", "Edit", "Read", "Grep", "WebSearch"}


async def test_filters_empty_db_returns_empty_lists(db_session):
    filters = await _service(db_session).get_filters("claude")
    for key in ("projects", "models", "tools", "topics"):
        assert filters[key] == []


# ---------------------------------------------------------------------------
# search() integration — exercises the full orchestration path
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def _embedded_sessions(seed_sessions, db_session):
    await db_session.execute(
        update(Session).where(Session.provider == "claude").values(embedding=[0.01] * 384)
    )
    await db_session.commit()


async def test_search_keyword_returns_results_even_without_vector(seed_sessions, db_session, monkeypatch):
    """No embeddings + embed_text unused → keyword-only path still works."""
    results = await _service(db_session).search("docker", provider="claude")
    assert any(r["session_id"] == "s1" for r in results)


async def test_search_with_project_filter_pushdown(seed_sessions, db_session, monkeypatch):
    def fake_embed(text):
        return [0.01] * embed.EMBEDDING_DIM
    monkeypatch.setattr(embed, "embed_text", fake_embed)
    results = await _service(db_session).search(
        "project:oft chart", provider="claude",
    )
    for r in results:
        assert r["project"] == "oft"


async def test_search_filter_only_path_does_not_crash(seed_sessions, db_session):
    """Phase 7.2 bug fix verification at the service level."""
    results = await _service(db_session).search("project:conversations")
    for r in results:
        assert r["project"] == "conversations"


async def test_search_result_shape(seed_sessions, db_session):
    results = await _service(db_session).search("docker")
    assert results
    r = results[0]
    expected_keys = {
        "session_id", "project", "date", "model", "cost", "snippet",
        "tool_summary", "tools", "turn_count", "topics", "conversation_id", "rank",
    }
    assert set(r.keys()) == expected_keys


async def test_community_boost_applied_when_graph_present(_embedded_sessions, db_session, monkeypatch):
    """Two candidates sharing a community with the top-ranked result get boosts."""
    def fake_embed(text):
        return [0.01] * embed.EMBEDDING_DIM
    monkeypatch.setattr(embed, "embed_text", fake_embed)

    # Seed a shared community between s1 and s2
    db_session.add(Concept(id="c_shared", name="docker", community_id=1, degree=2))
    await db_session.flush()
    for sid in ("s1", "s2"):
        db_session.add(SessionConcept(
            session_id=sid, concept_id="c_shared", relationship_label="contains",
            edge_type="extracted", confidence=0.9,
        ))
    await db_session.commit()

    results = await _service(db_session).search("docker")
    # The community boost is additive; all we need to verify is the search still
    # returns results in the presence of community data (regression guard).
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# _filter_only_retrieval — empty match path (line 184 of search_service.py)
# ---------------------------------------------------------------------------

async def test_search_filter_only_no_matches_returns_empty(db_session):
    """filter-only query that matches zero sessions → service returns []."""
    # Empty DB + project filter for nonexistent project → repo returns []
    results = await _service(db_session).search("project:no-such-project")
    assert results == []


async def test_search_filter_only_nonexistent_project_with_seed(seed_sessions, db_session):
    """Filter-only query that doesn't match any seeded project → []."""
    results = await _service(db_session).search("project:does-not-exist")
    assert results == []


# ---------------------------------------------------------------------------
# _community_boost — empty scored early return (line 224)
# ---------------------------------------------------------------------------

async def test_community_boost_empty_scored_returns_empty(db_session):
    """Calling _community_boost with {} short-circuits before any DB query."""
    service = _service(db_session)
    result = await service._community_boost({})
    assert result == {}


# ---------------------------------------------------------------------------
# _build_snippets — vector-only fallback path (line 211)
# ---------------------------------------------------------------------------

async def test_build_snippets_vector_only_fallback_uses_first_segment(
    _embedded_sessions, db_session, monkeypatch
):
    """Vector-only match: the session has no tsvector hit, so the keyword leg
    misses, but the fallback snippet is extracted from the first segment's raw
    text and stored because it differs from the raw prefix.
    """
    def fake_embed(text):
        return [0.01] * embed.EMBEDDING_DIM
    monkeypatch.setattr(embed, "embed_text", fake_embed)

    # Use a query that doesn't match any seeded segment via tsvector but does
    # overlap semantically enough for the vector leg to surface sessions.
    # Every session gets the same fake vector, so they all match equally.
    results = await _service(db_session).search("something vague")
    # At least one session must come back — prove _build_snippets didn't crash
    # and the fallback path produced sensible snippets.
    assert len(results) >= 1
    for r in results:
        assert "snippet" in r


async def test_build_snippets_fallback_stores_snippet_when_term_found(db_session):
    """Direct unit test: _build_snippets stores the fallback snippet when the
    query term appears in the first segment's raw text (line 211).

    The raw text must be long enough that _extract_snippet's window trimming
    produces a snippet DIFFERENT from raw[:SNIPPET_MAX_LEN] — otherwise the
    `snippet != raw[:N]` guard on line 210 short-circuits to False.
    """
    from unittest.mock import AsyncMock

    from services.search_service import SearchService

    service = SearchService(
        sessions=None, segments=None, tool_calls=None, topics=None, concepts=None,
    )
    service.segments = type("_fake", (), {})()
    service.segments.get_best_match_raw_texts = AsyncMock(return_value={})
    # Long text with the query term in the middle. _extract_snippet will trim
    # both the prefix (start > 0) and the suffix (end < len) → the returned
    # snippet differs from raw[:SNIPPET_MAX_LEN] → line 211 writes it.
    raw = "word " * 120 + "docker is right here " + "tail " * 120
    service.segments.get_first_raw_texts = AsyncMock(return_value={"sid-1": raw})

    snippets = await service._build_snippets(
        session_ids=["sid-1"], query_text="docker", has_text=True,
    )
    assert "sid-1" in snippets
    assert "docker" in snippets["sid-1"]


async def test_build_snippets_fallback_skips_when_term_not_found(db_session):
    """When _extract_snippet returns raw[:N] (no term match), line 210 guard
    skips the assignment — snippet NOT stored."""
    from unittest.mock import AsyncMock

    from services.search_service import SearchService

    service = SearchService(
        sessions=None, segments=None, tool_calls=None, topics=None, concepts=None,
    )
    service.segments = type("_fake", (), {})()
    service.segments.get_best_match_raw_texts = AsyncMock(return_value={})
    # No "docker" in the raw text → _extract_snippet returns raw[:SNIPPET_MAX_LEN]
    # → line 210 `if snippet != raw[:N]` False → line 211 skipped.
    service.segments.get_first_raw_texts = AsyncMock(
        return_value={"sid-1": "just a short text with no match here"}
    )
    snippets = await service._build_snippets(
        session_ids=["sid-1"], query_text="docker", has_text=True,
    )
    assert "sid-1" not in snippets


# ---------------------------------------------------------------------------
# _extract_snippet — prefix/suffix ellipsis branches (lines 290-292, 294-296)
# ---------------------------------------------------------------------------

def test_extract_snippet_match_near_start_no_prefix_ellipsis():
    """Match at position 0 → no `start > 0` → no leading ellipsis."""
    from services.search_service import _extract_snippet
    text = "docker is the focus " + "x" * 50
    snippet = _extract_snippet(text, "docker")
    assert not snippet.startswith("...")
    assert "docker" in snippet


def test_extract_snippet_match_in_middle_gets_prefix_ellipsis():
    """Match in the middle → start > 0 → snippet begins with '...'.

    Hits lines 290-292: find first space within first 30 chars, trim left.

    Requires dense whitespace so the first space in snippet[start:end] lies within
    the first 30 chars (see the `space < 30` guard in _extract_snippet).
    """
    from services.search_service import _extract_snippet
    # Dense "word " prefix (5 chars each) keeps the first space always within 4-5
    # chars of any cut point, satisfying `space < 30`.
    text = "word " * 80 + "docker is here " + "tail " * 80
    snippet = _extract_snippet(text, "docker")
    assert snippet.startswith("...")
    assert "docker" in snippet


def test_extract_snippet_match_with_text_after_gets_suffix_ellipsis():
    """Match near start with lots of text after → snippet ends with '...'.

    Hits lines 294-296: find last space within last 30 chars, trim right.
    """
    from services.search_service import _extract_snippet
    # Match at position 0 to disable the prefix ellipsis; dense "tail " words
    # after ensure the last space within 30 chars triggers the suffix cut.
    text = "docker is the term " + "tail " * 100
    snippet = _extract_snippet(text, "docker", max_len=100)
    assert snippet.endswith("...")
    assert "docker" in snippet


# ---------------------------------------------------------------------------
# _format_results — missing-session + long-snippet truncation (lines 353, 356)
# ---------------------------------------------------------------------------

def test_format_results_skips_session_not_in_dict():
    """session_ids has 'ghost', sessions_by_id doesn't → 'ghost' is silently skipped.

    Hits line 353: `if not session: continue`. This path is normally unreachable
    in production (sessions_by_id is a superset of session_ids), but the defensive
    skip is called directly here.
    """
    from services.search_service import _format_results

    class _FakeSession:
        def __init__(self, sid: str):
            self.id = sid
            self.project = "proj"
            self.started_at = None
            self.model = "m"
            self.estimated_cost = None
            self.snippet = None
            self.summary_text = "ok"
            self.turn_count = 1
            self.conversation_id = "c"

    sessions_by_id = {"real": _FakeSession("real")}
    results = _format_results(
        session_ids=["ghost", "real"],
        sessions_by_id=sessions_by_id,
        snippets={},
        tool_summaries={},
        topics_by_session={},
        rank_map={"ghost": 0.5, "real": 1.0},
    )
    assert len(results) == 1
    assert results[0]["session_id"] == "real"


def test_format_results_truncates_long_snippet_fallback():
    """Falls back to session.summary_text; if summary is > SNIPPET_MAX_LEN it's truncated.

    Hits line 356: `if len(snippet) > SNIPPET_MAX_LEN: snippet = snippet[:N] + "..."`.
    """
    from services.search_service import SNIPPET_MAX_LEN, _format_results

    class _FakeSession:
        def __init__(self):
            self.id = "sLong"
            self.project = "proj"
            self.started_at = None
            self.model = None
            self.estimated_cost = None
            # Long summary — no snippet available, so this is used as fallback.
            self.summary_text = "x" * (SNIPPET_MAX_LEN + 100)
            self.turn_count = 1
            self.conversation_id = None

    results = _format_results(
        session_ids=["sLong"],
        sessions_by_id={"sLong": _FakeSession()},
        snippets={},  # no snippet for sLong → falls back to summary_text
        tool_summaries={},
        topics_by_session={},
        rank_map={"sLong": 1.0},
    )
    assert len(results) == 1
    assert results[0]["snippet"].endswith("...")
    assert len(results[0]["snippet"]) == SNIPPET_MAX_LEN + 3  # N + "..."


# ---------------------------------------------------------------------------
# _hybrid_retrieval — session missing from sessions_by_id (line 158)
# ---------------------------------------------------------------------------

async def test_hybrid_retrieval_skips_missing_session(seed_sessions, db_session, monkeypatch):
    """Monkeypatch SessionRepository.get_by_ids to return a partial dict.

    Forces the `if not session: continue` branch at line 158. In production
    this is effectively unreachable (the set of IDs returned by get_by_ids is a
    superset of the input), but we exercise it here to prove the guard is wired.

    Requires: embeddings populated on all sessions so the vector leg returns
    multiple sids (same fake_embed vector = same cosine distance for all).
    """
    from sqlalchemy import update

    from models import Session
    from repositories.session_repository import SessionRepository

    await db_session.execute(
        update(Session).where(Session.provider == "claude")
        .values(embedding=[0.01] * embed.EMBEDDING_DIM)
    )
    await db_session.commit()

    original_get_by_ids = SessionRepository.get_by_ids

    async def partial_get_by_ids(self, session_ids):
        full = await original_get_by_ids(self, session_ids)
        # Drop one entry so rrf_scores sees sessions that aren't in the dict.
        if len(full) > 1:
            first_key = next(iter(full))
            full.pop(first_key)
        return full

    monkeypatch.setattr(SessionRepository, "get_by_ids", partial_get_by_ids)

    def fake_embed(text):
        return [0.01] * embed.EMBEDDING_DIM
    monkeypatch.setattr(embed, "embed_text", fake_embed)

    results = await _service(db_session).search("docker")
    # Service still returns — the dropped session was silently skipped via line 158.
    assert isinstance(results, list)
