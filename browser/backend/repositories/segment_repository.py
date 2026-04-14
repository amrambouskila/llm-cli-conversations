from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Segment, Session

if TYPE_CHECKING:
    from services._filter_scope import SessionFilterScope


class SegmentRepository:
    """Segment-level queries: tsvector keyword search, snippet fetch, hidden state ops."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_with_session(self, segment_id: str) -> tuple[Segment, Session] | None:
        result = await self.db.execute(
            select(Segment, Session).join(Session).where(Segment.id == segment_id)
        )
        row = result.one_or_none()
        return None if row is None else (row.Segment, row.Session)

    async def list_project_segments(
        self,
        project: str,
        provider: str,
        show_hidden: bool,
    ) -> list[tuple[Segment, Session]]:
        conditions = [Session.provider == provider, Session.project == project]
        if not show_hidden:
            conditions.extend([Session.hidden_at.is_(None), Segment.hidden_at.is_(None)])
        result = await self.db.execute(
            select(Segment, Session)
            .join(Session)
            .where(*conditions)
            .order_by(Segment.timestamp, Segment.segment_index)
        )
        return [(r.Segment, r.Session) for r in result.all()]

    async def project_exists(self, project: str, provider: str) -> bool:
        result = await self.db.execute(
            select(Session.id)
            .where(Session.provider == provider, Session.project == project)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def list_conversation_segments(
        self,
        project: str,
        conversation_id: str,
        provider: str,
    ) -> list[Segment]:
        result = await self.db.execute(
            select(Segment)
            .join(Session)
            .where(
                Session.conversation_id == conversation_id,
                Session.project == project,
                Session.provider == provider,
            )
            .order_by(Segment.segment_index)
        )
        return list(result.scalars().all())

    async def hide_segment(self, segment_id: str) -> None:
        await self.db.execute(
            update(Segment).where(Segment.id == segment_id).values(hidden_at=func.now())
        )
        await self.db.commit()

    async def restore_segment(self, segment_id: str) -> None:
        await self.db.execute(
            update(Segment).where(Segment.id == segment_id).values(hidden_at=None)
        )
        await self.db.commit()

    async def restore_all_segments(self) -> None:
        await self.db.execute(update(Segment).values(hidden_at=None))
        await self.db.commit()

    async def count_hidden(self) -> int:
        result = await self.db.execute(
            select(func.count(Segment.id)).where(Segment.hidden_at.is_not(None))
        )
        return result.scalar_one()

    async def list_hidden(self) -> list[tuple[Segment, Session]]:
        result = await self.db.execute(
            select(Segment, Session).join(Session).where(Segment.hidden_at.is_not(None))
        )
        return [(r.Segment, r.Session) for r in result.all()]

    async def search_keyword_top_sessions(
        self,
        query_text: str,
        scope: SessionFilterScope,
        show_hidden: bool,
        limit: int = 50,
    ) -> list[tuple[str, float]]:
        """tsvector full-text search over segments, grouped by session.

        Returns (session_id, best_rank) pairs sorted by descending rank, where
        best_rank is the maximum ts_rank across that session's segments.
        """
        ts_query = func.plainto_tsquery("english", query_text)
        stmt = (
            select(
                Session.id.label("session_id"),
                func.max(func.ts_rank(Segment.search_vector, ts_query)).label("best_rank"),
            )
            .select_from(Segment)
            .join(Session, Segment.session_id == Session.id)
            .where(Segment.search_vector.op("@@")(ts_query))
        )
        stmt = scope.apply(stmt)
        if not show_hidden:
            stmt = stmt.where(Segment.hidden_at.is_(None))
        stmt = stmt.group_by(Session.id).order_by(text("best_rank DESC")).limit(limit)
        result = await self.db.execute(stmt)
        return [(r.session_id, float(r.best_rank)) for r in result.all()]

    async def get_best_match_raw_texts(
        self,
        session_ids: list[str],
        query_text: str,
    ) -> dict[str, str]:
        """For each session with a tsvector match, return the best-matching segment's raw text."""
        if not session_ids:
            return {}
        ts_query = func.plainto_tsquery("english", query_text)
        stmt = (
            select(
                Segment.session_id,
                Segment.preview,
                Segment.raw_text,
                func.ts_rank(Segment.search_vector, ts_query).label("seg_rank"),
            )
            .where(
                Segment.session_id.in_(session_ids),
                Segment.search_vector.op("@@")(ts_query),
            )
            .order_by(Segment.session_id, text("seg_rank DESC"))
        )
        result = await self.db.execute(stmt)
        best_per_session: dict[str, str] = {}
        for row in result.all():
            if row.session_id not in best_per_session:
                best_per_session[row.session_id] = row.raw_text or row.preview or ""
        return best_per_session

    async def get_first_raw_texts(
        self,
        session_ids: list[str],
    ) -> dict[str, str]:
        """For each session, return the first segment's raw text (for vector-only snippet fallback)."""
        if not session_ids:
            return {}
        stmt = (
            select(Segment.session_id, Segment.preview, Segment.raw_text)
            .where(Segment.session_id.in_(session_ids))
            .order_by(Segment.session_id, Segment.segment_index)
        )
        result = await self.db.execute(stmt)
        first_per_session: dict[str, str] = {}
        for row in result.all():
            if row.session_id not in first_per_session:
                first_per_session[row.session_id] = row.raw_text or row.preview or ""
        return first_per_session
