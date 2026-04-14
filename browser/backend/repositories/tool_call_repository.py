from __future__ import annotations

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Session, ToolCall


class ToolCallRepository:
    """Tool-call aggregations: per-segment breakdown and per-session tool counts."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def distinct_tool_names_for_provider(self, provider: str) -> list[str]:
        result = await self.db.execute(
            select(distinct(ToolCall.tool_name))
            .join(Session, ToolCall.session_id == Session.id)
            .where(Session.provider == provider)
            .order_by(ToolCall.tool_name)
        )
        return [r[0] for r in result.all()]

    async def get_counts_by_session_and_tool(
        self,
        session_ids: list[str],
    ) -> dict[str, dict[str, int]]:
        if not session_ids:
            return {}
        stmt = (
            select(
                ToolCall.session_id,
                ToolCall.tool_name,
                func.count(ToolCall.id).label("cnt"),
            )
            .where(ToolCall.session_id.in_(session_ids))
            .group_by(ToolCall.session_id, ToolCall.tool_name)
        )
        result = await self.db.execute(stmt)
        grouped: dict[str, dict[str, int]] = {}
        for row in result.all():
            grouped.setdefault(row.session_id, {})[row.tool_name] = row.cnt
        return grouped

    async def get_breakdown_for_segment(
        self,
        segment_id: str,
    ) -> dict[str, int]:
        stmt = (
            select(ToolCall.tool_name, func.count(ToolCall.id).label("cnt"))
            .where(ToolCall.segment_id == segment_id)
            .group_by(ToolCall.tool_name)
        )
        result = await self.db.execute(stmt)
        return {r.tool_name: r.cnt for r in result.all()}

    async def get_counts_by_segment(
        self,
        segment_ids: list[str],
    ) -> dict[str, int]:
        """Single query: total tool-call count per segment."""
        if not segment_ids:
            return {}
        stmt = (
            select(ToolCall.segment_id, func.count(ToolCall.id).label("cnt"))
            .where(ToolCall.segment_id.in_(segment_ids))
            .group_by(ToolCall.segment_id)
        )
        result = await self.db.execute(stmt)
        return {r.segment_id: r.cnt for r in result.all()}

    async def count_for_segments(
        self,
        segment_ids: list[str],
    ) -> int:
        """Total tool-call count across the given segments."""
        if not segment_ids:
            return 0
        stmt = select(func.count(ToolCall.id)).where(ToolCall.segment_id.in_(segment_ids))
        result = await self.db.execute(stmt)
        return result.scalar_one()
