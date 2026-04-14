from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from models import Session, SessionTopic, ToolCall
from search import SearchFilters

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import Select


@dataclass
class SessionFilterScope:
    """Pre-compiled filter clauses derived from a SearchFilters object.

    Services build one scope per request; repositories apply it to their queries
    via `apply(stmt)`. This keeps filter-to-SQL translation centralized and lets
    repositories stay ignorant of SearchFilters' structure.
    """

    session_conditions: list[ColumnElement[bool]] = field(default_factory=list)
    tool_subquery: Select | None = None
    topic_subquery: Select | None = None

    @classmethod
    def build(
        cls,
        filters: SearchFilters,
        default_provider: str,
        show_hidden: bool,
    ) -> SessionFilterScope:
        effective_provider = filters.provider or default_provider
        conditions: list[ColumnElement[bool]] = [Session.provider == effective_provider]
        if not show_hidden:
            conditions.append(Session.hidden_at.is_(None))
        if filters.project:
            conditions.append(Session.project == filters.project)
        if filters.model:
            conditions.append(Session.model.ilike(f"%{filters.model}%"))
        # Phase 7.2 bug fix: pass date objects directly, not .isoformat() strings —
        # Postgres has no implicit cast from varchar to timestamptz.
        if filters.after:
            conditions.append(Session.started_at >= filters.after)
        if filters.before:
            # Use the start of the following day as an exclusive upper bound.
            conditions.append(Session.started_at < filters.before + timedelta(days=1))
        if filters.min_cost is not None:
            conditions.append(Session.estimated_cost >= filters.min_cost)
        if filters.min_turns is not None:
            conditions.append(Session.turn_count >= filters.min_turns)

        tool_subq: Select | None = None
        if filters.tools:
            tool_subq = (
                select(ToolCall.session_id)
                .where(ToolCall.tool_name.in_(filters.tools))
                .group_by(ToolCall.session_id)
            )
        topic_subq: Select | None = None
        if filters.topic:
            topic_subq = (
                select(SessionTopic.session_id)
                .where(SessionTopic.topic.ilike(f"%{filters.topic}%"))
            )

        return cls(
            session_conditions=conditions,
            tool_subquery=tool_subq,
            topic_subquery=topic_subq,
        )

    def apply(self, stmt: Select, include_tool_topic: bool = True) -> Select:
        for cond in self.session_conditions:
            stmt = stmt.where(cond)
        if include_tool_topic:
            if self.tool_subquery is not None:
                stmt = stmt.where(Session.id.in_(self.tool_subquery))
            if self.topic_subquery is not None:
                stmt = stmt.where(Session.id.in_(self.topic_subquery))
        return stmt
