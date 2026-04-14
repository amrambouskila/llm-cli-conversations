from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Session

if TYPE_CHECKING:
    from services._filter_scope import SessionFilterScope


class SessionRepository:
    """Session-centric queries: batch fetch, vector similarity search, hidden state ops."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_ids(self, session_ids: list[str]) -> dict[str, Session]:
        if not session_ids:
            return {}
        result = await self.db.execute(
            select(Session).where(Session.id.in_(session_ids))
        )
        return {s.id: s for s in result.scalars().all()}

    async def search_vector_top_sessions(
        self,
        query_vector: list[float],
        scope: SessionFilterScope,
        limit: int = 50,
    ) -> list[tuple[str, float]]:
        """Cosine-similarity search against Session.embedding.

        Returns (session_id, similarity) pairs ordered by descending similarity.
        Only sessions with non-null embeddings are considered.
        """
        stmt = (
            select(
                Session.id.label("session_id"),
                (1 - Session.embedding.cosine_distance(query_vector)).label("similarity"),
            )
            .where(Session.embedding.is_not(None))
        )
        stmt = scope.apply(stmt)
        stmt = stmt.order_by(Session.embedding.cosine_distance(query_vector)).limit(limit)
        result = await self.db.execute(stmt)
        return [(r.session_id, float(r.similarity)) for r in result.all()]

    async def search_filter_only_top_sessions(
        self,
        scope: SessionFilterScope,
        limit: int = 50,
    ) -> list[str]:
        """Filter-only search: return session IDs ordered by recency.

        Phase 7.2 bug fix: returns plain session IDs. The previous
        implementation SELECTed `func.literal(1.0)` which compiled to a
        nonexistent Postgres `literal()` function — crashes on any query
        without free text.
        """
        stmt = select(Session.id.label("session_id")).select_from(Session)
        stmt = scope.apply(stmt)
        stmt = stmt.order_by(Session.started_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return [r.session_id for r in result.all()]

    # ------------------------------------------------------------------
    # Hidden state operations
    # ------------------------------------------------------------------

    async def hide_conversation(self, project: str, conversation_id: str) -> None:
        await self.db.execute(
            update(Session)
            .where(Session.project == project, Session.conversation_id == conversation_id)
            .values(hidden_at=func.now())
        )
        await self.db.commit()

    async def restore_conversation(self, project: str, conversation_id: str) -> None:
        await self.db.execute(
            update(Session)
            .where(Session.project == project, Session.conversation_id == conversation_id)
            .values(hidden_at=None)
        )
        await self.db.commit()

    async def hide_project(self, project: str) -> None:
        await self.db.execute(
            update(Session).where(Session.project == project).values(hidden_at=func.now())
        )
        await self.db.commit()

    async def restore_project(self, project: str) -> None:
        await self.db.execute(
            update(Session).where(Session.project == project).values(hidden_at=None)
        )
        await self.db.commit()

    async def restore_all_sessions(self) -> None:
        await self.db.execute(update(Session).values(hidden_at=None))
        await self.db.commit()

    async def count_hidden_conversations(self) -> int:
        result = await self.db.execute(
            select(func.count(distinct(Session.conversation_id))).where(
                Session.hidden_at.is_not(None), Session.conversation_id.is_not(None)
            )
        )
        return result.scalar_one()

    async def list_hidden_conversations(self) -> list[tuple[str, str, object]]:
        """Return (project, conversation_id, max_hidden_at) tuples for hidden conversations."""
        result = await self.db.execute(
            select(
                Session.project,
                Session.conversation_id,
                Session.hidden_at,
            )
            .where(Session.hidden_at.is_not(None), Session.conversation_id.is_not(None))
            .distinct(Session.project, Session.conversation_id)
        )
        return [(r.project, r.conversation_id, r.hidden_at) for r in result.all()]

    async def list_fully_hidden_projects(self) -> list[tuple[str, object]]:
        """Return (project_name, max_hidden_at) for projects whose every session is hidden."""
        result = await self.db.execute(
            select(
                Session.project,
                func.count(Session.id).label("total"),
                func.count(Session.hidden_at).label("hidden_count"),
                func.max(Session.hidden_at).label("max_hidden"),
            )
            .group_by(Session.project)
        )
        hidden_projects: list[tuple[str, object]] = []
        for row in result.all():
            if row.total > 0 and row.hidden_count == row.total:
                hidden_projects.append((row.project, row.max_hidden))
        return hidden_projects

    async def count_fully_hidden_projects(self, provider: str | None = None) -> int:
        stmt = (
            select(
                Session.project,
                func.count(Session.id).label("total"),
                func.count(Session.hidden_at).label("hidden_count"),
            )
            .group_by(Session.project)
        )
        if provider is not None:
            stmt = stmt.where(Session.provider == provider)
        result = await self.db.execute(stmt)
        return sum(1 for row in result.all() if row.total > 0 and row.hidden_count == row.total)

    # ------------------------------------------------------------------
    # Search-status counts + autocomplete distinct values
    # ------------------------------------------------------------------

    async def count_visible(self, provider: str) -> int:
        result = await self.db.execute(
            select(func.count(Session.id)).where(
                Session.provider == provider, Session.hidden_at.is_(None)
            )
        )
        return result.scalar_one()

    async def count_embedded(self, provider: str) -> int:
        result = await self.db.execute(
            select(func.count(Session.id)).where(
                Session.provider == provider,
                Session.hidden_at.is_(None),
                Session.embedding.is_not(None),
            )
        )
        return result.scalar_one()

    async def distinct_projects(self, provider: str) -> list[str]:
        result = await self.db.execute(
            select(distinct(Session.project))
            .where(Session.provider == provider, Session.hidden_at.is_(None))
            .order_by(Session.project)
        )
        return [r[0] for r in result.all()]

    async def distinct_models(self, provider: str) -> list[str]:
        result = await self.db.execute(
            select(distinct(Session.model))
            .where(
                Session.provider == provider,
                Session.hidden_at.is_(None),
                Session.model.is_not(None),
            )
            .order_by(Session.model)
        )
        return [r[0] for r in result.all()]
