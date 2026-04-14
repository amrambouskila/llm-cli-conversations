from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SessionBase(BaseModel):
    provider: str
    project: str
    model: str | None = None
    conversation_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    turn_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    total_chars: int | None = None
    total_words: int | None = None
    estimated_cost: float | None = None
    source_file: str | None = None
    summary_text: str | None = None
    session_type: str | None = None


class SessionCreate(SessionBase):
    id: str


class SessionRead(SessionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hidden_at: datetime | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------

class SegmentBase(BaseModel):
    session_id: str
    segment_index: int | None = None
    role: str | None = None
    timestamp: datetime | None = None
    char_count: int | None = None
    word_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_text: str | None = None
    preview: str | None = None


class SegmentCreate(SegmentBase):
    id: str


class SegmentRead(SegmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hidden_at: datetime | None = None


# ---------------------------------------------------------------------------
# Tool call
# ---------------------------------------------------------------------------

class ToolCallBase(BaseModel):
    session_id: str
    segment_id: str | None = None
    tool_name: str
    tool_family: str | None = None
    timestamp: datetime | None = None


class ToolCallCreate(ToolCallBase):
    pass


class ToolCallRead(ToolCallBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------------------------------------------------------------------------
# Session topic
# ---------------------------------------------------------------------------

class SessionTopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    topic: str
    confidence: float | None = None
    source: str | None = "heuristic"


# ---------------------------------------------------------------------------
# Saved search
# ---------------------------------------------------------------------------

class SavedSearchCreate(BaseModel):
    name: str
    query: str
    filters_json: dict | None = None


class SavedSearchRead(SavedSearchCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Graphify enrichment
# ---------------------------------------------------------------------------

class ConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str | None = None
    community_id: int | None = None
    degree: int | None = None


class SessionConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    concept_id: str
    relationship_label: str
    edge_type: str | None = None
    confidence: float | None = None
