from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Segment, Session, ToolCall

router = APIRouter()


@router.get("/api/stats")
async def api_stats(provider: str = "claude", db: AsyncSession = Depends(get_db)) -> dict:
    """Return global statistics."""
    # Totals
    totals = await db.execute(
        select(
            func.count(Session.id).label("total_projects_placeholder"),
            func.count(Segment.id).label("total_segments"),
            func.coalesce(func.sum(Segment.char_count), 0).label("total_chars"),
            func.coalesce(func.sum(Segment.word_count), 0).label("total_words"),
        )
        .join(Session, Segment.session_id == Session.id)
        .where(Session.provider == provider, Session.hidden_at.is_(None))
    )
    row = totals.one()
    total_segments = row.total_segments
    total_chars = row.total_chars
    total_words = row.total_words

    # Project count
    proj_count = await db.execute(
        select(func.count(func.distinct(Session.project)))
        .where(Session.provider == provider, Session.hidden_at.is_(None))
    )
    total_projects = proj_count.scalar_one()

    # Tool call count
    tool_count = await db.execute(
        select(func.count(ToolCall.id))
        .join(Session, ToolCall.session_id == Session.id)
        .where(Session.provider == provider, Session.hidden_at.is_(None))
    )
    total_tool_calls = tool_count.scalar_one()

    # Monthly breakdown
    monthly_result = await db.execute(
        select(
            func.to_char(Segment.timestamp, 'YYYY-MM').label("month"),
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
    monthly = {}
    for m_row in monthly_result.all():
        if m_row.month:
            monthly[m_row.month] = {"tokens": int(m_row.tokens), "requests": m_row.requests}

    # Hidden counts
    hidden_segs = await db.execute(
        select(func.count(Segment.id)).where(Segment.hidden_at.is_not(None))
    )
    hidden_convs = await db.execute(
        select(func.count(func.distinct(Session.conversation_id)))
        .where(Session.hidden_at.is_not(None), Session.conversation_id.is_not(None))
    )
    # Only count projects where ALL sessions are hidden
    all_projects_result = await db.execute(
        select(Session.project, func.count(Session.id).label("total"),
               func.count(Session.hidden_at).label("hidden_count"))
        .where(Session.provider == provider)
        .group_by(Session.project)
    )
    hidden_project_count = 0
    for p_row in all_projects_result.all():
        if p_row.total > 0 and p_row.hidden_count == p_row.total:
            hidden_project_count += 1

    est_tokens = total_chars // 4

    return {
        "total_projects": total_projects,
        "total_segments": total_segments,
        "total_chars": total_chars,
        "total_words": total_words,
        "total_tool_calls": total_tool_calls,
        "estimated_tokens": est_tokens,
        "monthly": monthly,
        "hidden": {
            "segments": hidden_segs.scalar_one(),
            "conversations": hidden_convs.scalar_one(),
            "projects": hidden_project_count,
        },
    }
