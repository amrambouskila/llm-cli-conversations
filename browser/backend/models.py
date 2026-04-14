from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


Base.metadata.schema = "conversations"


# ---------------------------------------------------------------------------
# Core tables
# ---------------------------------------------------------------------------

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    project: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    turn_count: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_creation_tokens: Mapped[int | None] = mapped_column(Integer)
    total_chars: Mapped[int | None] = mapped_column(Integer)
    total_words: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(10, 4))
    source_file: Mapped[str | None] = mapped_column(Text)
    summary_text: Mapped[str | None] = mapped_column(Text)
    session_type: Mapped[str | None] = mapped_column(Text)
    embedding = mapped_column(Vector(384), nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_vector = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(summary_text, ''))", persisted=True),
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    segments: Mapped[list[Segment]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
    )
    topics: Mapped[list[SessionTopic]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
    )
    session_concepts: Mapped[list[SessionConcept]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_sessions_project", "project"),
        Index("idx_sessions_provider", "provider"),
        Index("idx_sessions_started", "started_at"),
        Index("idx_sessions_model", "model"),
        Index("idx_sessions_cost", "estimated_cost"),
        Index("idx_sessions_type", "session_type"),
        Index("idx_sessions_fts", "search_vector", postgresql_using="gin"),
        Index(
            "idx_sessions_embedding", "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "idx_sessions_summary_trgm", "summary_text",
            postgresql_using="gin",
            postgresql_ops={"summary_text": "gin_trgm_ops"},
        ),
    )


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.sessions.id", ondelete="CASCADE"), nullable=False,
    )
    segment_index: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    char_count: Mapped[int | None] = mapped_column(Integer)
    word_count: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str | None] = mapped_column(Text)
    preview: Mapped[str | None] = mapped_column(Text)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_vector = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(raw_text, ''))", persisted=True),
    )

    session: Mapped[Session] = relationship(back_populates="segments")
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="segment", cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("session_id", "segment_index"),
        Index("idx_segments_session", "session_id"),
        Index("idx_segments_fts", "search_vector", postgresql_using="gin"),
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.sessions.id", ondelete="CASCADE"), nullable=False,
    )
    segment_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.segments.id", ondelete="CASCADE"),
    )
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    tool_family: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[Session] = relationship(back_populates="tool_calls")
    segment: Mapped[Segment | None] = relationship(back_populates="tool_calls")

    __table_args__ = (
        Index("idx_tool_calls_session", "session_id"),
        Index("idx_tool_calls_name", "tool_name"),
    )


class SessionTopic(Base):
    __tablename__ = "session_topics"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.sessions.id", ondelete="CASCADE"), primary_key=True,
    )
    topic: Mapped[str] = mapped_column(Text, primary_key=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(Text, server_default="heuristic")

    session: Mapped[Session] = relationship(back_populates="topics")

    __table_args__ = (
        Index("idx_session_topics_topic", "topic"),
    )


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    filters_json = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Graphify enrichment tables (DESIGN.md §9)
# ---------------------------------------------------------------------------

class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str | None] = mapped_column(Text)
    community_id: Mapped[int | None] = mapped_column(Integer)
    degree: Mapped[int | None] = mapped_column(Integer)

    session_concepts: Mapped[list[SessionConcept]] = relationship(
        back_populates="concept", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_concepts_community", "community_id"),
    )


class SessionConcept(Base):
    __tablename__ = "session_concepts"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.sessions.id", ondelete="CASCADE"), primary_key=True,
    )
    concept_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.concepts.id", ondelete="CASCADE"), primary_key=True,
    )
    relationship_label: Mapped[str] = mapped_column(
        "relationship", Text, primary_key=True,
    )
    edge_type: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)

    session: Mapped[Session] = relationship(back_populates="session_concepts")
    concept: Mapped[Concept] = relationship(back_populates="session_concepts")

    __table_args__ = (
        Index("idx_session_concepts_concept", "concept_id"),
    )
