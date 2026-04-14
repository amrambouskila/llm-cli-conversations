from __future__ import annotations

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Session, SessionTopic


class SessionTopicRepository:
    """Per-session topic lookups."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_topics_by_session(
        self,
        session_ids: list[str],
    ) -> dict[str, list[str]]:
        """Return topics per session, ordered by confidence (highest first)."""
        if not session_ids:
            return {}
        stmt = (
            select(SessionTopic.session_id, SessionTopic.topic)
            .where(SessionTopic.session_id.in_(session_ids))
            .order_by(SessionTopic.confidence.desc())
        )
        result = await self.db.execute(stmt)
        grouped: dict[str, list[str]] = {}
        for row in result.all():
            grouped.setdefault(row.session_id, []).append(row.topic)
        return grouped

    async def distinct_topics_for_provider(self, provider: str) -> list[str]:
        result = await self.db.execute(
            select(distinct(SessionTopic.topic))
            .join(Session, SessionTopic.session_id == Session.id)
            .where(Session.provider == provider)
            .order_by(SessionTopic.topic)
        )
        return [r[0] for r in result.all()]
