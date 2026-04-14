from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Segment, Session

router = APIRouter()


async def _hidden_counts(db: AsyncSession) -> dict:
    """Return counts of hidden items."""
    seg_count = await db.execute(
        select(func.count(Segment.id)).where(Segment.hidden_at.is_not(None))
    )
    conv_count = await db.execute(
        select(func.count(func.distinct(Session.conversation_id)))
        .where(Session.hidden_at.is_not(None), Session.conversation_id.is_not(None))
    )
    # Projects where ALL sessions are hidden
    proj_result = await db.execute(
        select(Session.project,
               func.count(Session.id).label("total"),
               func.count(Session.hidden_at).label("hidden_count"))
        .group_by(Session.project)
    )
    hidden_proj = 0
    for row in proj_result.all():
        if row.total > 0 and row.hidden_count == row.total:
            hidden_proj += 1

    return {
        "segments": seg_count.scalar_one(),
        "conversations": conv_count.scalar_one(),
        "projects": hidden_proj,
    }


@router.post("/api/hide/segment/{segment_id}")
async def api_hide_segment(segment_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(
        update(Segment).where(Segment.id == segment_id).values(hidden_at=func.now())
    )
    await db.commit()
    counts = await _hidden_counts(db)
    return {"ok": True, "hidden": counts}


@router.post("/api/restore/segment/{segment_id}")
async def api_restore_segment(segment_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(
        update(Segment).where(Segment.id == segment_id).values(hidden_at=None)
    )
    await db.commit()
    counts = await _hidden_counts(db)
    return {"ok": True, "hidden": counts}


@router.post("/api/hide/conversation/{project_name}/{conversation_id}")
async def api_hide_conversation(project_name: str, conversation_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(
        update(Session)
        .where(Session.project == project_name, Session.conversation_id == conversation_id)
        .values(hidden_at=func.now())
    )
    await db.commit()
    counts = await _hidden_counts(db)
    return {"ok": True, "hidden": counts}


@router.post("/api/restore/conversation/{project_name}/{conversation_id}")
async def api_restore_conversation(project_name: str, conversation_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(
        update(Session)
        .where(Session.project == project_name, Session.conversation_id == conversation_id)
        .values(hidden_at=None)
    )
    await db.commit()
    counts = await _hidden_counts(db)
    return {"ok": True, "hidden": counts}


@router.post("/api/hide/project/{project_name}")
async def api_hide_project(project_name: str, db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(
        update(Session).where(Session.project == project_name).values(hidden_at=func.now())
    )
    await db.commit()
    counts = await _hidden_counts(db)
    return {"ok": True, "hidden": counts}


@router.post("/api/restore/project/{project_name}")
async def api_restore_project(project_name: str, db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(
        update(Session).where(Session.project == project_name).values(hidden_at=None)
    )
    await db.commit()
    counts = await _hidden_counts(db)
    return {"ok": True, "hidden": counts}


@router.post("/api/restore/all")
async def api_restore_all(db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(update(Session).values(hidden_at=None))
    await db.execute(update(Segment).values(hidden_at=None))
    await db.commit()
    counts = await _hidden_counts(db)
    return {"ok": True, "hidden": counts}


@router.get("/api/hidden")
async def api_hidden(db: AsyncSession = Depends(get_db)) -> dict:
    """Return full hidden state for the trash view."""
    # Hidden segments
    seg_result = await db.execute(
        select(Segment, Session)
        .join(Session)
        .where(Segment.hidden_at.is_not(None))
    )
    hidden_segments = []
    for row in seg_result.all():
        seg, session = row
        hidden_segments.append({
            "id": seg.id,
            "preview": seg.preview or "",
            "project_name": session.project,
            "conversation_id": session.conversation_id,
            "hidden_at": seg.hidden_at.isoformat() if seg.hidden_at else None,
        })

    # Hidden conversations
    conv_result = await db.execute(
        select(
            Session.project,
            Session.conversation_id,
            Session.hidden_at,
        )
        .where(Session.hidden_at.is_not(None), Session.conversation_id.is_not(None))
        .distinct(Session.project, Session.conversation_id)
    )
    hidden_conversations = []
    for row in conv_result.all():
        hidden_conversations.append({
            "key": f"{row.project}:{row.conversation_id}",
            "hidden_at": row.hidden_at.isoformat() if row.hidden_at else None,
        })

    # Hidden projects (all sessions hidden)
    proj_result = await db.execute(
        select(Session.project,
               func.count(Session.id).label("total"),
               func.count(Session.hidden_at).label("hidden_count"),
               func.max(Session.hidden_at).label("max_hidden"))
        .group_by(Session.project)
    )
    hidden_projects = []
    for row in proj_result.all():
        if row.total > 0 and row.hidden_count == row.total:
            hidden_projects.append({
                "name": row.project,
                "hidden_at": row.max_hidden.isoformat() if row.max_hidden else None,
            })

    return {
        "segments": hidden_segments,
        "conversations": hidden_conversations,
        "projects": hidden_projects,
    }
