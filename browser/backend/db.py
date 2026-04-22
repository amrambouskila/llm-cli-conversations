from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from repositories.concept_repository import ConceptRepository
    from repositories.segment_repository import SegmentRepository
    from repositories.session_repository import SessionRepository
    from repositories.session_topic_repository import SessionTopicRepository
    from repositories.tool_call_repository import ToolCallRepository
    from services.dashboard_service import DashboardService
    from services.graph_service import GraphService
    from services.project_service import ProjectService
    from services.search_service import SearchService
    from services.session_service import SessionService
    from services.stats_service import StatsService
    from services.summary_service import SummaryService

_DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://conversations:conversations@localhost:5432/conversations"
)
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=5)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create extensions, schema, and all tables on startup."""
    from models import Base

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS conversations"))
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# FastAPI DI providers — services + repositories
# ---------------------------------------------------------------------------


def get_session_repository(db: AsyncSession = Depends(get_db)) -> SessionRepository:
    from repositories.session_repository import SessionRepository

    return SessionRepository(db)


def get_segment_repository(db: AsyncSession = Depends(get_db)) -> SegmentRepository:
    from repositories.segment_repository import SegmentRepository

    return SegmentRepository(db)


def get_tool_call_repository(db: AsyncSession = Depends(get_db)) -> ToolCallRepository:
    from repositories.tool_call_repository import ToolCallRepository

    return ToolCallRepository(db)


def get_session_topic_repository(db: AsyncSession = Depends(get_db)) -> SessionTopicRepository:
    from repositories.session_topic_repository import SessionTopicRepository

    return SessionTopicRepository(db)


def get_concept_repository(db: AsyncSession = Depends(get_db)) -> ConceptRepository:
    from repositories.concept_repository import ConceptRepository

    return ConceptRepository(db)


def get_search_service(
    sessions: SessionRepository = Depends(get_session_repository),
    segments: SegmentRepository = Depends(get_segment_repository),
    tool_calls: ToolCallRepository = Depends(get_tool_call_repository),
    topics: SessionTopicRepository = Depends(get_session_topic_repository),
    concepts: ConceptRepository = Depends(get_concept_repository),
) -> SearchService:
    from services.search_service import SearchService

    return SearchService(
        sessions=sessions,
        segments=segments,
        tool_calls=tool_calls,
        topics=topics,
        concepts=concepts,
    )


def get_session_service(
    sessions: SessionRepository = Depends(get_session_repository),
    segments: SegmentRepository = Depends(get_segment_repository),
    tool_calls: ToolCallRepository = Depends(get_tool_call_repository),
    concepts: ConceptRepository = Depends(get_concept_repository),
) -> SessionService:
    from services.session_service import SessionService

    return SessionService(
        sessions=sessions,
        segments=segments,
        tool_calls=tool_calls,
        concepts=concepts,
    )


def get_dashboard_service(db: AsyncSession = Depends(get_db)) -> DashboardService:
    from services.dashboard_service import DashboardService

    return DashboardService(db)


def get_graph_service(db: AsyncSession = Depends(get_db)) -> GraphService:
    from services.graph_service import GraphService

    return GraphService(db)


def get_project_service(db: AsyncSession = Depends(get_db)) -> ProjectService:
    from services.project_service import ProjectService

    return ProjectService(db)


def get_stats_service(db: AsyncSession = Depends(get_db)) -> StatsService:
    from services.stats_service import StatsService

    return StatsService(db)


def get_summary_service(db: AsyncSession = Depends(get_db)) -> SummaryService:
    from services.summary_service import SummaryService

    return SummaryService(db)
