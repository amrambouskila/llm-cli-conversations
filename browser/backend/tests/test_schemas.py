"""Instantiate every Pydantic model in schemas.py to exercise field definitions and from_attributes paths."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from schemas import (
    ConceptRead,
    SavedSearchCreate,
    SavedSearchRead,
    SegmentBase,
    SegmentCreate,
    SegmentRead,
    SessionBase,
    SessionConceptRead,
    SessionCreate,
    SessionRead,
    SessionTopicRead,
    ToolCallBase,
    ToolCallCreate,
    ToolCallRead,
)


def test_session_base_minimal():
    s = SessionBase(provider="claude", project="conversations")
    assert s.provider == "claude"
    assert s.project == "conversations"
    assert s.model is None
    assert s.started_at is None


def test_session_base_full():
    now = datetime(2026, 3, 15, tzinfo=UTC)
    s = SessionBase(
        provider="claude",
        project="conversations",
        model="opus",
        conversation_id="c1",
        started_at=now,
        ended_at=now,
        turn_count=5,
        input_tokens=1000,
        output_tokens=500,
        cache_read_tokens=200,
        cache_creation_tokens=50,
        total_chars=4000,
        total_words=600,
        estimated_cost=1.23,
        source_file="markdown/a.md",
        summary_text="hello",
        session_type="coding",
    )
    assert s.turn_count == 5
    assert s.estimated_cost == 1.23


def test_session_create():
    s = SessionCreate(id="s1", provider="claude", project="p")
    assert s.id == "s1"


def test_session_read_from_attributes():
    attrs = SimpleNamespace(
        id="s1",
        provider="claude",
        project="p",
        model=None,
        conversation_id=None,
        started_at=None,
        ended_at=None,
        turn_count=None,
        input_tokens=None,
        output_tokens=None,
        cache_read_tokens=None,
        cache_creation_tokens=None,
        total_chars=None,
        total_words=None,
        estimated_cost=None,
        source_file=None,
        summary_text=None,
        session_type=None,
        hidden_at=None,
        created_at=None,
    )
    s = SessionRead.model_validate(attrs)
    assert s.id == "s1"
    assert s.provider == "claude"


def test_segment_base_minimal():
    s = SegmentBase(session_id="s1")
    assert s.session_id == "s1"
    assert s.role is None


def test_segment_create():
    s = SegmentCreate(id="seg-1", session_id="s1", segment_index=0, role="user")
    assert s.id == "seg-1"
    assert s.segment_index == 0


def test_segment_read_from_attributes():
    attrs = SimpleNamespace(
        id="seg-1",
        session_id="s1",
        segment_index=0,
        role="user",
        timestamp=None,
        char_count=10,
        word_count=2,
        input_tokens=None,
        output_tokens=None,
        raw_text="hi",
        preview="hi",
        hidden_at=None,
    )
    s = SegmentRead.model_validate(attrs)
    assert s.id == "seg-1"
    assert s.char_count == 10


def test_tool_call_base():
    t = ToolCallBase(session_id="s1", tool_name="Bash")
    assert t.tool_name == "Bash"


def test_tool_call_create():
    t = ToolCallCreate(session_id="s1", tool_name="Edit", tool_family="file_ops")
    assert t.tool_family == "file_ops"


def test_tool_call_read_from_attributes():
    attrs = SimpleNamespace(
        id=42,
        session_id="s1",
        segment_id="seg-1",
        tool_name="Bash",
        tool_family="execution",
        timestamp=None,
    )
    t = ToolCallRead.model_validate(attrs)
    assert t.id == 42
    assert t.tool_name == "Bash"


def test_session_topic_read_from_attributes():
    attrs = SimpleNamespace(
        session_id="s1",
        topic="docker",
        confidence=0.9,
        source="heuristic",
    )
    t = SessionTopicRead.model_validate(attrs)
    assert t.topic == "docker"
    assert t.source == "heuristic"


def test_session_topic_read_default_source():
    t = SessionTopicRead(session_id="s1", topic="x")
    assert t.source == "heuristic"


def test_saved_search_create():
    s = SavedSearchCreate(name="docker", query="docker auth", filters_json={"project": "x"})
    assert s.name == "docker"
    assert s.filters_json == {"project": "x"}


def test_saved_search_create_optional_filters():
    s = SavedSearchCreate(name="n", query="q")
    assert s.filters_json is None


def test_saved_search_read_from_attributes():
    attrs = SimpleNamespace(
        id=1,
        name="saved",
        query="docker",
        filters_json=None,
        created_at=None,
    )
    s = SavedSearchRead.model_validate(attrs)
    assert s.id == 1
    assert s.name == "saved"


def test_concept_read_minimal():
    c = ConceptRead(id="c1", name="Docker")
    assert c.id == "c1"
    assert c.community_id is None


def test_concept_read_full_from_attributes():
    attrs = SimpleNamespace(
        id="c1",
        name="Docker",
        type="technology",
        community_id=3,
        degree=10,
    )
    c = ConceptRead.model_validate(attrs)
    assert c.community_id == 3
    assert c.degree == 10


def test_session_concept_read():
    sc = SessionConceptRead(
        session_id="s1",
        concept_id="c1",
        relationship_label="contains",
        edge_type="extracted",
        confidence=0.8,
    )
    assert sc.relationship_label == "contains"
    assert sc.confidence == 0.8
