from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SessionBase(BaseModel):
    provider: str
    project: str
    model: Optional[str] = None
    conversation_id: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    turn_count: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_creation_tokens: Optional[int] = None
    total_chars: Optional[int] = None
    total_words: Optional[int] = None
    estimated_cost: Optional[float] = None
    source_file: Optional[str] = None
    summary_text: Optional[str] = None
    session_type: Optional[str] = None


class SessionCreate(SessionBase):
    id: str


class SessionRead(SessionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hidden_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------

class SegmentBase(BaseModel):
    session_id: str
    segment_index: Optional[int] = None
    role: Optional[str] = None
    timestamp: Optional[datetime] = None
    char_count: Optional[int] = None
    word_count: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    raw_text: Optional[str] = None
    preview: Optional[str] = None


class SegmentCreate(SegmentBase):
    id: str


class SegmentRead(SegmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hidden_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Tool call
# ---------------------------------------------------------------------------

class ToolCallBase(BaseModel):
    session_id: str
    segment_id: Optional[str] = None
    tool_name: str
    tool_family: Optional[str] = None
    timestamp: Optional[datetime] = None


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
    confidence: Optional[float] = None
    source: Optional[str] = "heuristic"


# ---------------------------------------------------------------------------
# Saved search
# ---------------------------------------------------------------------------

class SavedSearchCreate(BaseModel):
    name: str
    query: str
    filters_json: Optional[dict] = None


class SavedSearchRead(SavedSearchCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Graphify enrichment
# ---------------------------------------------------------------------------

class ConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: Optional[str] = None
    community_id: Optional[int] = None
    degree: Optional[int] = None


class SessionConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    concept_id: str
    relationship_label: str
    edge_type: Optional[str] = None
    confidence: Optional[float] = None
