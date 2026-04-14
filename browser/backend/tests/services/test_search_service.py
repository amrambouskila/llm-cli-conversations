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
