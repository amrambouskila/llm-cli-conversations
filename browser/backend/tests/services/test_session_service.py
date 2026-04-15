"""Unit tests for SessionService — segment detail, conversation view, visibility, related."""
from __future__ import annotations

import pytest
import pytest_asyncio

from models import Concept, SessionConcept
from repositories.concept_repository import ConceptRepository
from repositories.segment_repository import SegmentRepository
from repositories.session_repository import SessionRepository
from repositories.tool_call_repository import ToolCallRepository
from services.session_service import SessionService


def _service(db) -> SessionService:
    return SessionService(
        sessions=SessionRepository(db),
        segments=SegmentRepository(db),
        tool_calls=ToolCallRepository(db),
        concepts=ConceptRepository(db),
    )


# ---------------------------------------------------------------------------
# Segment detail / export
# ---------------------------------------------------------------------------

async def test_get_segment_detail_returns_full_shape(seed_sessions, db_session):
    data = await _service(db_session).get_segment_detail("seg-1a")
    assert data["id"] == "seg-1a"
    assert data["project_name"] == "conversations"
    assert data["metrics"]["tool_call_count"] == 2  # seg-1a has 2 Bash calls
    assert data["tool_breakdown"] == {"Bash": 2}
    assert "raw_markdown" in data


async def test_get_segment_detail_missing_returns_none(seed_sessions, db_session):
    assert await _service(db_session).get_segment_detail("no-such") is None


async def test_get_segment_export_shape(seed_sessions, db_session):
    data = await _service(db_session).get_segment_export("seg-1a")
    assert data["filename"].endswith(".md")
    assert "conversations" in data["filename"]
    assert data["content"] == "how do I fix docker auth in the buildkit pipeline"


async def test_get_segment_export_missing_returns_none(seed_sessions, db_session):
    assert await _service(db_session).get_segment_export("no-such") is None


# ---------------------------------------------------------------------------
# Project segment listing
# ---------------------------------------------------------------------------

async def test_list_project_segments_returns_entries(seed_sessions, db_session):
    data = await _service(db_session).list_project_segments("conversations", "claude", False)
    assert data is not None
    assert len(data) == 4  # 2 from s1, 2 from s2
    for entry in data:
        assert "metrics" in entry
        assert "hidden" in entry


async def test_list_project_segments_none_for_unknown_project(seed_sessions, db_session):
    assert await _service(db_session).list_project_segments("no-such", "claude", False) is None


async def test_list_project_segments_empty_list_for_hidden_project_default(seed_sessions, db_session):
    """archive has only hidden sessions → returns empty list (not None — project exists)."""
    data = await _service(db_session).list_project_segments("archive", "claude", False)
    assert data == []


# ---------------------------------------------------------------------------
# Conversation view
# ---------------------------------------------------------------------------

async def test_get_conversation_view_concatenates_segments(seed_sessions, db_session):
    data = await _service(db_session).get_conversation_view("conversations", "conv-1", "claude")
    assert data["segment_count"] == 2
    assert "docker auth" in data["raw_markdown"]
    assert "---" in data["raw_markdown"]  # separator between segments
    assert data["metrics"]["tool_call_count"] == 3  # seg-1a=2 Bash, seg-1b=1 Edit


async def test_get_conversation_view_exposes_session_id(seed_sessions, db_session):
    """Phase 7.5: ConversationView must include session_id so the frontend can
    fetch /api/sessions/{id}/cost-breakdown without an extra lookup."""
    data = await _service(db_session).get_conversation_view("conversations", "conv-1", "claude")
    assert data["session_id"] == "s1"


async def test_get_conversation_view_missing_returns_none(seed_sessions, db_session):
    assert await _service(db_session).get_conversation_view("conversations", "ghost", "claude") is None


# ---------------------------------------------------------------------------
# Per-session cost breakdown
# ---------------------------------------------------------------------------

async def test_get_cost_breakdown_returns_four_way_split(seed_sessions, db_session):
    """Phase 7.5: /api/sessions/{id}/cost-breakdown must return the 4-way USD split."""
    data = await _service(db_session).get_cost_breakdown("s1")
    assert data is not None
    for key in ("input_usd", "output_usd", "cache_read_usd", "cache_create_usd", "total_usd"):
        assert key in data
    # s1 is opus ($15/$75) with input=10000 output=4000 cache_read=2000 cache_creation=500.
    # input_usd = 10000 * 15 / 1e6 = 0.15
    # output_usd = 4000 * 75 / 1e6 = 0.30
    # cache_read_usd = 2000 * 15 * 0.1 / 1e6 = 0.003
    # cache_create_usd = 500 * 15 * 1.25 / 1e6 = 0.009375
    assert data["input_usd"] == pytest.approx(0.15, abs=0.0001)
    assert data["output_usd"] == pytest.approx(0.30, abs=0.0001)
    assert data["cache_read_usd"] == pytest.approx(0.003, abs=0.0001)
    assert data["cache_create_usd"] == pytest.approx(0.0094, abs=0.0001)


async def test_get_cost_breakdown_missing_session_returns_none(seed_sessions, db_session):
    assert await _service(db_session).get_cost_breakdown("no-such-session") is None


async def test_get_cost_breakdown_session_without_tokens(seed_sessions, db_session):
    """A session with all-zero tokens returns a zero breakdown rather than crashing."""
    from datetime import UTC, datetime, timedelta

    from models import Session as SessionModel

    base = datetime(2026, 3, 15, tzinfo=UTC)
    db_session.add(SessionModel(
        id="zero-tokens",
        provider="claude",
        project="conversations",
        model="claude-opus-4-6",
        conversation_id="conv-zero",
        started_at=base,
        ended_at=base + timedelta(hours=1),
        turn_count=0,
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        total_chars=0,
        total_words=0,
    ))
    await db_session.commit()

    data = await _service(db_session).get_cost_breakdown("zero-tokens")
    assert data is not None
    assert data["total_usd"] == 0.0


# ---------------------------------------------------------------------------
# Related sessions
# ---------------------------------------------------------------------------

async def test_get_related_sessions_empty_when_no_concepts(seed_sessions, db_session):
    assert await _service(db_session).get_related_sessions("s1") == []


@pytest_asyncio.fixture
async def _related_graph(seed_sessions, db_session):
    db_session.add(Concept(id="c1", name="docker", community_id=1, degree=5))
    await db_session.flush()
    for sid in ("s1", "s2"):
        db_session.add(SessionConcept(
            session_id=sid, concept_id="c1", relationship_label="contains",
            edge_type="extracted", confidence=0.9,
        ))
    await db_session.commit()


async def test_get_related_sessions_with_shared_concept(_related_graph, db_session):
    results = await _service(db_session).get_related_sessions("s1")
    assert any(r["session_id"] == "s2" for r in results)
    for r in results:
        assert "shared_concepts" in r


async def test_get_related_sessions_session_with_concept_but_no_peers(seed_sessions, db_session):
    """Session has concepts but no OTHER session shares any → returns []."""
    db_session.add(Concept(id="c_solo", name="unique", community_id=1, degree=1))
    await db_session.flush()
    db_session.add(SessionConcept(
        session_id="s1", concept_id="c_solo", relationship_label="contains",
        edge_type="extracted", confidence=0.9,
    ))
    await db_session.commit()
    assert await _service(db_session).get_related_sessions("s1") == []


async def test_get_related_sessions_skips_hidden_peer(seed_sessions, db_session):
    """When a related session is hidden (not in get_visible_sessions_by_ids), it's skipped."""
    db_session.add(Concept(id="c_with_hidden", name="shared", community_id=1, degree=2))
    await db_session.flush()
    # s1 (visible) and s5 (hidden) both have this concept
    for sid in ("s1", "s5"):
        db_session.add(SessionConcept(
            session_id=sid, concept_id="c_with_hidden", relationship_label="contains",
            edge_type="extracted", confidence=0.9,
        ))
    await db_session.commit()
    results = await _service(db_session).get_related_sessions("s1")
    # s5 is hidden → filtered out of sessions_by_id → skipped in the results loop
    assert all(r["session_id"] != "s5" for r in results)


# ---------------------------------------------------------------------------
# Hide / restore + hidden counts
# ---------------------------------------------------------------------------

async def test_hide_segment_returns_counts(seed_sessions, db_session):
    counts = await _service(db_session).hide_segment("seg-1a")
    assert counts["segments"] == 1


async def test_restore_segment_decrements(seed_sessions, db_session):
    svc = _service(db_session)
    await svc.hide_segment("seg-1a")
    counts = await svc.restore_segment("seg-1a")
    assert counts["segments"] == 0


async def test_hide_conversation_updates_counts(seed_sessions, db_session):
    """Fixture starts with 1 hidden conversation (archive/conv-5). Hiding conv-1 makes 2."""
    counts = await _service(db_session).hide_conversation("conversations", "conv-1")
    assert counts["conversations"] == 2


async def test_hide_project_updates_counts(seed_sessions, db_session):
    """After hiding the conversations project, archive + conversations = 2 fully hidden."""
    counts = await _service(db_session).hide_project("conversations")
    assert counts["projects"] == 2


async def test_restore_all_clears_everything(seed_sessions, db_session):
    svc = _service(db_session)
    await svc.hide_segment("seg-1a")
    counts = await svc.restore_all()
    assert counts["segments"] == 0
    assert counts["conversations"] == 0
    assert counts["projects"] == 0


async def test_get_hidden_detail_shape(seed_sessions, db_session):
    svc = _service(db_session)
    await svc.hide_segment("seg-1a")
    detail = await svc.get_hidden_detail()
    assert len(detail["segments"]) == 1
    assert detail["segments"][0]["id"] == "seg-1a"
    assert any(conv["key"] == "archive:conv-5" for conv in detail["conversations"])
    assert any(proj["name"] == "archive" for proj in detail["projects"])
