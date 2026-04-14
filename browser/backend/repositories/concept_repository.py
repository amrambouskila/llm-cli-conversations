from __future__ import annotations

from sqlalchemy import distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models import Concept, Session, SessionConcept


class ConceptRepository:
    """Graphify concept graph queries: community lookup and related-session discovery."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_communities_by_session(
        self,
        session_ids: list[str],
    ) -> dict[str, set[int]]:
        """Map session_id → set of Leiden community IDs the session belongs to.

        Returns an empty dict when no concept data exists — callers degrade gracefully.
        """
        if not session_ids:
            return {}
        stmt = (
            select(SessionConcept.session_id, Concept.community_id)
            .join(Concept, SessionConcept.concept_id == Concept.id)
            .where(
                SessionConcept.session_id.in_(session_ids),
                Concept.community_id.is_not(None),
            )
        )
        result = await self.db.execute(stmt)
        grouped: dict[str, set[int]] = {}
        for row in result.all():
            grouped.setdefault(row.session_id, set()).add(row.community_id)
        return grouped

    async def count_concepts_with_community(self) -> int:
        result = await self.db.execute(
            select(func.count(Concept.id)).where(Concept.community_id.is_not(None))
        )
        return result.scalar_one()

    async def count_concepts_for_session(self, session_id: str) -> int:
        stmt = (
            select(func.count(SessionConcept.concept_id))
            .where(SessionConcept.session_id == session_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def find_related_sessions(
        self,
        session_id: str,
        limit: int = 5,
    ) -> list[tuple[str, int]]:
        """For a session, find other sessions sharing concept nodes.

        Returns (other_session_id, shared_concept_count) pairs ordered by shared count.
        Empty list when the source session has no concepts.
        """
        my_concepts = (
            select(SessionConcept.concept_id)
            .where(SessionConcept.session_id == session_id)
        ).subquery()

        stmt = (
            select(
                SessionConcept.session_id,
                func.count(distinct(SessionConcept.concept_id)).label("shared_count"),
            )
            .where(
                SessionConcept.concept_id.in_(select(my_concepts.c.concept_id)),
                SessionConcept.session_id != session_id,
            )
            .group_by(SessionConcept.session_id)
            .order_by(text("shared_count DESC"))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [(r.session_id, r.shared_count) for r in result.all()]

    async def get_visible_sessions_by_ids(
        self,
        session_ids: list[str],
    ) -> dict[str, Session]:
        """Fetch sessions by ID, filtering out hidden ones. Used by related-sessions display."""
        if not session_ids:
            return {}
        stmt = select(Session).where(
            Session.id.in_(session_ids), Session.hidden_at.is_(None)
        )
        result = await self.db.execute(stmt)
        return {s.id: s for s in result.scalars().all()}
