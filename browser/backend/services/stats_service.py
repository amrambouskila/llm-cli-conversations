from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models import Segment, Session, ToolCall


class StatsService:
    """Global statistics (the header stats bar)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_stats(self, provider: str) -> dict:
        totals = await self.db.execute(
            select(
                func.count(Segment.id).label("total_segments"),
                func.coalesce(func.sum(Segment.char_count), 0).label("total_chars"),
                func.coalesce(func.sum(Segment.word_count), 0).label("total_words"),
            )
            .join(Session, Segment.session_id == Session.id)
            .where(Session.provider == provider, Session.hidden_at.is_(None))
        )
        row = totals.one()

        proj_count = await self.db.execute(
            select(func.count(func.distinct(Session.project)))
            .where(Session.provider == provider, Session.hidden_at.is_(None))
        )
        total_projects = proj_count.scalar_one()

        tool_count = await self.db.execute(
            select(func.count(ToolCall.id))
            .join(Session, ToolCall.session_id == Session.id)
            .where(Session.provider == provider, Session.hidden_at.is_(None))
        )
        total_tool_calls = tool_count.scalar_one()

        monthly_result = await self.db.execute(
            select(
                func.to_char(Segment.timestamp, "YYYY-MM").label("month"),
                func.coalesce(func.sum(Segment.char_count / 4), 0).label("tokens"),
                func.count(Segment.id).label("requests"),
            )
            .join(Session, Segment.session_id == Session.id)
            .where(
                Session.provider == provider,
                Session.hidden_at.is_(None),
                Segment.timestamp.is_not(None),
            )
            .group_by(text("1"))
            .order_by(text("1"))
        )
        monthly: dict[str, dict] = {}
        for m_row in monthly_result.all():
            if m_row.month:
                monthly[m_row.month] = {"tokens": int(m_row.tokens), "requests": m_row.requests}

        hidden_segs = await self.db.execute(
            select(func.count(Segment.id)).where(Segment.hidden_at.is_not(None))
        )
        hidden_convs = await self.db.execute(
            select(func.count(func.distinct(Session.conversation_id)))
            .where(Session.hidden_at.is_not(None), Session.conversation_id.is_not(None))
        )
        all_projects_result = await self.db.execute(
            select(
                Session.project,
                func.count(Session.id).label("total"),
                func.count(Session.hidden_at).label("hidden_count"),
            )
            .where(Session.provider == provider)
            .group_by(Session.project)
        )
        hidden_project_count = sum(
            1 for r in all_projects_result.all() if r.total > 0 and r.hidden_count == r.total
        )

        total_chars = row.total_chars
        return {
            "total_projects": total_projects,
            "total_segments": row.total_segments,
            "total_chars": total_chars,
            "total_words": row.total_words,
            "total_tool_calls": total_tool_calls,
            "estimated_tokens": total_chars // 4,
            "monthly": monthly,
            "hidden": {
                "segments": hidden_segs.scalar_one(),
                "conversations": hidden_convs.scalar_one(),
                "projects": hidden_project_count,
            },
        }
