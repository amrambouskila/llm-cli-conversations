from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Segment, Session, ToolCall

router = APIRouter()


@router.get("/api/projects/{project_name}/segments")
async def api_project_segments(
    project_name: str,
    show_hidden: bool = False,
    provider: str = "claude",
    db: AsyncSession = Depends(get_db),
):
    """Return segment list for a project (previews, no full content)."""
    filters = [Session.provider == provider, Session.project == project_name]
    if not show_hidden:
        filters.extend([Session.hidden_at.is_(None), Segment.hidden_at.is_(None)])

    result = await db.execute(
        select(Segment, Session)
        .join(Session)
        .where(*filters)
        .order_by(Segment.timestamp, Segment.segment_index)
    )
    rows = result.all()

    if not rows:
        # Check if the project exists at all
        proj_exists = await db.execute(
            select(Session.id).where(Session.provider == provider, Session.project == project_name).limit(1)
        )
        if not proj_exists.scalar_one_or_none():
            return JSONResponse({"error": "project not found"}, status_code=404)
        return []

    # Get tool counts per segment
    seg_ids = [row.Segment.id for row in rows]
    tc_result = await db.execute(
        select(ToolCall.segment_id, func.count(ToolCall.id).label("cnt"))
        .where(ToolCall.segment_id.in_(seg_ids))
        .group_by(ToolCall.segment_id)
    )
    tool_counts = {r.segment_id: r.cnt for r in tc_result.all()}

    result_list = []
    for row in rows:
        seg = row.Segment
        session = row.Session
        char_count = seg.char_count or 0
        word_count = seg.word_count or 0
        raw_text = seg.raw_text or ""
        is_hidden = seg.hidden_at is not None

        result_list.append({
            "id": seg.id,
            "source_file": session.source_file,
            "project_name": session.project,
            "segment_index": seg.segment_index or 0,
            "preview": seg.preview or "",
            "timestamp": seg.timestamp.isoformat().replace("+00:00", "Z") if seg.timestamp else None,
            "conversation_id": session.conversation_id,
            "entry_number": seg.segment_index,
            "metrics": {
                "char_count": char_count,
                "word_count": word_count,
                "line_count": raw_text.count("\n") + 1,
                "estimated_tokens": max(1, char_count // 4),
                "tool_call_count": tool_counts.get(seg.id, 0),
            },
            "hidden": is_hidden,
        })

    return result_list


@router.get("/api/projects/{project_name}/conversation/{conversation_id}")
async def api_conversation_view(
    project_name: str,
    conversation_id: str,
    provider: str = "claude",
    db: AsyncSession = Depends(get_db),
):
    """Return all segments for a single conversation, concatenated."""
    result = await db.execute(
        select(Segment)
        .join(Session)
        .where(
            Session.conversation_id == conversation_id,
            Session.project == project_name,
            Session.provider == provider,
        )
        .order_by(Segment.segment_index)
    )
    segments = result.scalars().all()

    if not segments:
        return JSONResponse({"error": "conversation not found"}, status_code=404)

    combined_markdown = "\n\n---\n\n".join(seg.raw_text or "" for seg in segments)
    total_chars = sum(s.char_count or 0 for s in segments)
    total_words = sum(s.word_count or 0 for s in segments)

    # Tool call count
    seg_ids = [s.id for s in segments]
    tc_result = await db.execute(
        select(func.count(ToolCall.id))
        .where(ToolCall.segment_id.in_(seg_ids))
    )
    total_tools = tc_result.scalar_one()

    return {
        "conversation_id": conversation_id,
        "project_name": project_name,
        "segment_count": len(segments),
        "raw_markdown": combined_markdown,
        "metrics": {
            "char_count": total_chars,
            "word_count": total_words,
            "line_count": combined_markdown.count("\n") + 1,
            "estimated_tokens": total_chars // 4,
            "tool_call_count": total_tools,
        },
    }
