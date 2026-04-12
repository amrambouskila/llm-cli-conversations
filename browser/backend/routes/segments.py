from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db import get_db
from models import Segment, Session, ToolCall

router = APIRouter()


def _segment_to_dict(seg: Segment, session: Session, tool_breakdown: dict[str, int] | None = None) -> dict:
    """Convert a Segment ORM object to the API dict shape."""
    char_count = seg.char_count or 0
    word_count = seg.word_count or 0
    raw_text = seg.raw_text or ""
    lines = raw_text.count("\n") + 1 if raw_text else 0

    return {
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
            "line_count": lines,
            "estimated_tokens": max(1, char_count // 4),
            "tool_call_count": sum(tool_breakdown.values()) if tool_breakdown else 0,
        },
        "tool_breakdown": tool_breakdown or {},
        "raw_markdown": raw_text,
    }


async def _get_tool_breakdown(db: AsyncSession, segment_id: str) -> dict[str, int]:
    """Get tool breakdown for a segment."""
    result = await db.execute(
        select(ToolCall.tool_name, func.count(ToolCall.id).label("cnt"))
        .where(ToolCall.segment_id == segment_id)
        .group_by(ToolCall.tool_name)
    )
    return {r.tool_name: r.cnt for r in result.all()}


@router.get("/api/segments/{segment_id}/export")
async def api_segment_export(segment_id: str, provider: str = "claude", db: AsyncSession = Depends(get_db)):
    """Return raw markdown for download/copy."""
    result = await db.execute(
        select(Segment, Session)
        .join(Session)
        .where(Segment.id == segment_id)
    )
    row = result.one_or_none()
    if row:
        seg, session = row
        return JSONResponse({
            "filename": f"{session.project}_request_{(seg.segment_index or 0) + 1}.md",
            "content": seg.raw_text or "",
        })
    return JSONResponse({"error": "not found"}, status_code=404)


@router.get("/api/segments/{segment_id}")
async def api_segment_detail(segment_id: str, provider: str = "claude", db: AsyncSession = Depends(get_db)):
    """Return full segment data including raw markdown."""
    result = await db.execute(
        select(Segment, Session)
        .join(Session)
        .where(Segment.id == segment_id)
    )
    row = result.one_or_none()
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)

    seg, session = row
    tool_bd = await _get_tool_breakdown(db, segment_id)
    return _segment_to_dict(seg, session, tool_bd)


@router.get("/api/search")
async def api_search(
    q: Optional[str] = Query(None),
    show_hidden: bool = False,
    provider: str = "claude",
    db: AsyncSession = Depends(get_db),
):
    """Search across all segments using tsvector full-text search."""
    if not q or len(q.strip()) < 2:
        return []

    query_text = q.strip()

    # Use plainto_tsquery for full-text search
    ts_query = func.plainto_tsquery("english", query_text)

    filters = [
        Segment.search_vector.op("@@")(ts_query),
        Session.provider == provider,
    ]
    if not show_hidden:
        filters.extend([Session.hidden_at.is_(None), Segment.hidden_at.is_(None)])

    result = await db.execute(
        select(
            Segment,
            Session,
            func.ts_rank(Segment.search_vector, ts_query).label("rank"),
        )
        .join(Session)
        .where(*filters)
        .order_by(text("rank DESC"))
        .limit(100)
    )
    rows = result.all()

    # Get tool counts for matched segments
    seg_ids = [row.Segment.id for row in rows]
    tool_counts: dict[str, int] = {}
    if seg_ids:
        tc_result = await db.execute(
            select(ToolCall.segment_id, func.count(ToolCall.id).label("cnt"))
            .where(ToolCall.segment_id.in_(seg_ids))
            .group_by(ToolCall.segment_id)
        )
        tool_counts = {r.segment_id: r.cnt for r in tc_result.all()}

    results = []
    for row in rows:
        seg = row.Segment
        session = row.Session
        is_hidden = seg.hidden_at is not None
        results.append({
            "id": seg.id,
            "project_name": session.project,
            "segment_index": seg.segment_index or 0,
            "preview": seg.preview or "",
            "timestamp": seg.timestamp.isoformat().replace("+00:00", "Z") if seg.timestamp else None,
            "conversation_id": session.conversation_id,
            "metrics": {
                "char_count": seg.char_count or 0,
                "word_count": seg.word_count or 0,
                "line_count": (seg.raw_text or "").count("\n") + 1,
                "estimated_tokens": max(1, (seg.char_count or 0) // 4),
                "tool_call_count": tool_counts.get(seg.id, 0),
            },
            "hidden": is_hidden,
        })

    return results
