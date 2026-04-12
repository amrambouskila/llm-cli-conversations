from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Segment, Session, ToolCall

router = APIRouter()


@router.get("/api/providers")
async def api_providers(db: AsyncSession = Depends(get_db)):
    """Return available providers and their project counts."""
    result = await db.execute(
        select(
            Session.provider,
            func.count(func.distinct(Session.project)).label("projects"),
            func.count(Session.id).label("sessions"),
        )
        .group_by(Session.provider)
    )
    rows = result.all()

    # Count segments per provider
    seg_result = await db.execute(
        select(
            Session.provider,
            func.count(Segment.id).label("segments"),
        )
        .join(Segment, Segment.session_id == Session.id)
        .group_by(Session.provider)
    )
    seg_counts = {r.provider: r.segments for r in seg_result.all()}

    providers = []
    for row in rows:
        providers.append({
            "id": row.provider,
            "name": row.provider.title(),
            "projects": row.projects,
            "segments": seg_counts.get(row.provider, 0),
        })

    # Always include claude even if empty
    if not any(p["id"] == "claude" for p in providers):
        providers.insert(0, {"id": "claude", "name": "Claude", "projects": 0, "segments": 0})

    return providers


@router.get("/api/projects")
async def api_projects(show_hidden: bool = False, provider: str = "claude", db: AsyncSession = Depends(get_db)):
    """Return list of projects with summaries including per-project stats."""
    # Base filter
    filters = [Session.provider == provider]
    if not show_hidden:
        filters.append(Session.hidden_at.is_(None))

    # Get project-level aggregations from sessions
    proj_result = await db.execute(
        select(
            Session.project,
            func.count(func.distinct(Session.conversation_id)).label("total_conversations"),
            func.min(Session.started_at).label("first_timestamp"),
            func.max(Session.ended_at).label("last_timestamp"),
        )
        .where(*filters)
        .group_by(Session.project)
        .order_by(func.max(Session.ended_at).desc())
    )
    projects = proj_result.all()

    result = []
    for proj in projects:
        project_name = proj.project

        # Segment-level stats
        seg_filters = [Session.provider == provider, Session.project == project_name]
        if not show_hidden:
            seg_filters.extend([Session.hidden_at.is_(None), Segment.hidden_at.is_(None)])

        seg_result = await db.execute(
            select(
                func.count(Segment.id).label("total_requests"),
                func.coalesce(func.sum(Segment.char_count), 0).label("total_chars"),
                func.coalesce(func.sum(Segment.word_count), 0).label("total_words"),
            )
            .join(Session, Segment.session_id == Session.id)
            .where(*seg_filters)
        )
        seg_row = seg_result.one()

        # Tool call count
        tool_result = await db.execute(
            select(func.count(ToolCall.id))
            .join(Session, ToolCall.session_id == Session.id)
            .where(Session.provider == provider, Session.project == project_name)
        )
        total_tools = tool_result.scalar_one()

        # Tool breakdown
        tool_bd_result = await db.execute(
            select(ToolCall.tool_name, func.count(ToolCall.id).label("cnt"))
            .join(Session, ToolCall.session_id == Session.id)
            .where(Session.provider == provider, Session.project == project_name)
            .group_by(ToolCall.tool_name)
            .order_by(func.count(ToolCall.id).desc())
        )
        tool_breakdown = {r.tool_name: r.cnt for r in tool_bd_result.all()}

        # Request sizes (word counts per segment)
        sizes_result = await db.execute(
            select(Segment.word_count)
            .join(Session, Segment.session_id == Session.id)
            .where(*seg_filters)
            .order_by(Segment.timestamp, Segment.segment_index)
        )
        request_sizes = [r.word_count or 0 for r in sizes_result.all()]

        # Conversation timeline (first timestamp per conversation)
        timeline_result = await db.execute(
            select(func.min(Segment.timestamp).label("first_ts"))
            .join(Session, Segment.session_id == Session.id)
            .where(
                Session.provider == provider,
                Session.project == project_name,
                Session.conversation_id.is_not(None),
            )
            .group_by(Session.conversation_id)
            .order_by(text("first_ts"))
        )
        conv_timeline = [
            r.first_ts.isoformat().replace("+00:00", "Z") if r.first_ts else None
            for r in timeline_result.all()
        ]
        conv_timeline = [t for t in conv_timeline if t]

        # File count (distinct source files)
        file_result = await db.execute(
            select(func.count(func.distinct(Session.source_file)))
            .where(Session.provider == provider, Session.project == project_name)
        )
        total_files = file_result.scalar_one()

        # Check if project is hidden (all sessions hidden)
        if show_hidden:
            hidden_check = await db.execute(
                select(
                    func.count(Session.id).label("total"),
                    func.count(Session.hidden_at).label("hidden_count"),
                )
                .where(Session.provider == provider, Session.project == project_name)
            )
            hc = hidden_check.one()
            is_hidden = hc.total > 0 and hc.hidden_count == hc.total
        else:
            is_hidden = False

        total_chars = seg_row.total_chars
        first_ts = proj.first_timestamp
        last_ts = proj.last_timestamp

        result.append({
            "name": project_name,
            "display_name": project_name,
            "total_requests": seg_row.total_requests,
            "total_files": total_files,
            "hidden": is_hidden,
            "stats": {
                "total_conversations": proj.total_conversations,
                "total_words": seg_row.total_words,
                "total_chars": total_chars,
                "estimated_tokens": total_chars // 4,
                "total_tool_calls": total_tools,
                "first_timestamp": first_ts.isoformat().replace("+00:00", "Z") if first_ts else None,
                "last_timestamp": last_ts.isoformat().replace("+00:00", "Z") if last_ts else None,
                "request_sizes": request_sizes,
                "conversation_timeline": conv_timeline,
                "tool_breakdown": tool_breakdown,
            },
        })

    return result
