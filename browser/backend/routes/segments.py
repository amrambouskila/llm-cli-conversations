from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Segment, Session, SessionConcept, SessionTopic, ToolCall
from search import parse_query

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
    """Search and return session-level results with the best-matching snippet per session."""
    if not q or len(q.strip()) < 2:
        return []

    parsed = parse_query(q)
    query_text = parsed.text
    f = parsed.filters

    # If no free text remains after filter extraction, search session summary instead
    has_text = len(query_text.strip()) >= 2

    if has_text:
        ts_query = func.plainto_tsquery("english", query_text)
        # Search segments, rank by ts_rank, group by session
        stmt = (
            select(
                Session.id.label("session_id"),
                func.max(func.ts_rank(Segment.search_vector, ts_query)).label("best_rank"),
            )
            .select_from(Segment)
            .join(Session, Segment.session_id == Session.id)
            .where(Segment.search_vector.op("@@")(ts_query))
        )
    else:
        # No free text — return sessions matching filters only, ordered by recency
        stmt = (
            select(
                Session.id.label("session_id"),
                func.literal(1.0).label("best_rank"),
            )
            .select_from(Session)
        )

    # Provider filter (always applied)
    effective_provider = f.provider or provider
    stmt = stmt.where(Session.provider == effective_provider)

    if not show_hidden:
        stmt = stmt.where(Session.hidden_at.is_(None))
        if has_text:
            stmt = stmt.where(Segment.hidden_at.is_(None))

    # Apply metadata filters
    if f.project:
        stmt = stmt.where(Session.project == f.project)
    if f.model:
        stmt = stmt.where(Session.model.ilike(f"%%{f.model}%%"))
    if f.after:
        stmt = stmt.where(Session.started_at >= f.after.isoformat())
    if f.before:
        stmt = stmt.where(Session.started_at <= f.before.isoformat() + "T23:59:59")
    if f.min_cost is not None:
        stmt = stmt.where(Session.estimated_cost >= f.min_cost)
    if f.min_turns is not None:
        stmt = stmt.where(Session.turn_count >= f.min_turns)
    if f.tools:
        # Session must have at least one of the specified tools
        stmt = stmt.where(
            Session.id.in_(
                select(ToolCall.session_id)
                .where(ToolCall.tool_name.in_(f.tools))
                .group_by(ToolCall.session_id)
            )
        )
    if f.topic:
        stmt = stmt.where(
            Session.id.in_(
                select(SessionTopic.session_id)
                .where(SessionTopic.topic.ilike(f"%%{f.topic}%%"))
            )
        )

    if has_text:
        stmt = stmt.group_by(Session.id)

    stmt = stmt.order_by(text("best_rank DESC")).limit(50)

    session_ranks = await db.execute(stmt)
    ranked_sessions = session_ranks.all()

    if not ranked_sessions:
        return []

    session_ids = [r.session_id for r in ranked_sessions]
    rank_map = {r.session_id: float(r.best_rank) for r in ranked_sessions}

    # Fetch full session data
    sess_result = await db.execute(
        select(Session).where(Session.id.in_(session_ids))
    )
    sessions_by_id = {s.id: s for s in sess_result.scalars().all()}

    # For each session, get the best-matching segment as snippet
    snippets: dict[str, str] = {}
    if has_text:
        ts_query = func.plainto_tsquery("english", query_text)
        snip_result = await db.execute(
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
        for row in snip_result.all():
            if row.session_id not in snippets:
                # Extract a snippet: first ~200 chars of the matching segment's text
                raw = row.raw_text or row.preview or ""
                # Try to find the query terms in the text for context
                snippet = _extract_snippet(raw, query_text)
                snippets[row.session_id] = snippet

    # Get tool summaries per session
    tool_result = await db.execute(
        select(
            ToolCall.session_id,
            ToolCall.tool_name,
            func.count(ToolCall.id).label("cnt"),
        )
        .where(ToolCall.session_id.in_(session_ids))
        .group_by(ToolCall.session_id, ToolCall.tool_name)
    )
    tool_summaries: dict[str, dict[str, int]] = {}
    for row in tool_result.all():
        tool_summaries.setdefault(row.session_id, {})[row.tool_name] = row.cnt

    # Get topics per session
    topic_result = await db.execute(
        select(SessionTopic.session_id, SessionTopic.topic)
        .where(SessionTopic.session_id.in_(session_ids))
        .order_by(SessionTopic.confidence.desc())
    )
    topics_by_session: dict[str, list[str]] = {}
    for row in topic_result.all():
        topics_by_session.setdefault(row.session_id, []).append(row.topic)

    # Build response in rank order
    results = []
    for sid in session_ids:
        session = sessions_by_id.get(sid)
        if not session:
            continue
        snippet = snippets.get(sid) or session.summary_text or ""
        if len(snippet) > 250:
            snippet = snippet[:250] + "..."
        tools = tool_summaries.get(sid, {})
        tool_summary_str = ", ".join(f"{name}({cnt})" for name, cnt in sorted(tools.items(), key=lambda x: -x[1]))

        results.append({
            "session_id": session.id,
            "project": session.project,
            "date": session.started_at.isoformat().replace("+00:00", "Z") if session.started_at else None,
            "model": session.model,
            "cost": float(session.estimated_cost) if session.estimated_cost else None,
            "snippet": snippet,
            "tool_summary": tool_summary_str,
            "tools": tools,
            "turn_count": session.turn_count,
            "topics": topics_by_session.get(sid, [])[:5],
            "conversation_id": session.conversation_id,
            "rank": rank_map.get(sid, 0),
        })

    return results


def _extract_snippet(raw_text: str, query: str, max_len: int = 250) -> str:
    """Extract a snippet centered around the first occurrence of query terms."""
    text_lower = raw_text.lower()
    terms = query.lower().split()

    best_pos = -1
    for term in terms:
        pos = text_lower.find(term)
        if pos >= 0:
            best_pos = pos
            break

    if best_pos < 0:
        return raw_text[:max_len]

    # Center the snippet around the match
    start = max(0, best_pos - max_len // 3)
    end = start + max_len
    snippet = raw_text[start:end]

    # Clean up: avoid starting/ending mid-word
    if start > 0:
        space = snippet.find(" ")
        if space >= 0 and space < 30:
            snippet = "..." + snippet[space + 1:]
    if end < len(raw_text):
        space = snippet.rfind(" ")
        if space > len(snippet) - 30:
            snippet = snippet[:space] + "..."

    # Strip markdown noise
    snippet = snippet.replace(">>>USER_REQUEST<<<", "").replace("---", "").strip()
    return snippet


# ---------------------------------------------------------------------------
# Autocomplete endpoints for filter UI
# ---------------------------------------------------------------------------

@router.get("/api/search/filters")
async def api_search_filters(
    provider: str = "claude",
    db: AsyncSession = Depends(get_db),
):
    """Return distinct values for filter autocomplete."""
    projects_q = await db.execute(
        select(distinct(Session.project))
        .where(Session.provider == provider, Session.hidden_at.is_(None))
        .order_by(Session.project)
    )
    models_q = await db.execute(
        select(distinct(Session.model))
        .where(Session.provider == provider, Session.hidden_at.is_(None), Session.model.isnot(None))
        .order_by(Session.model)
    )
    tools_q = await db.execute(
        select(distinct(ToolCall.tool_name))
        .join(Session, ToolCall.session_id == Session.id)
        .where(Session.provider == provider)
        .order_by(ToolCall.tool_name)
    )
    topics_q = await db.execute(
        select(distinct(SessionTopic.topic))
        .join(Session, SessionTopic.session_id == Session.id)
        .where(Session.provider == provider)
        .order_by(SessionTopic.topic)
    )

    return {
        "projects": [r[0] for r in projects_q.all()],
        "models": [r[0] for r in models_q.all()],
        "tools": [r[0] for r in tools_q.all()],
        "topics": [r[0] for r in topics_q.all()],
    }


# ---------------------------------------------------------------------------
# 3.4 — Related sessions via concept graph
# ---------------------------------------------------------------------------

@router.get("/api/sessions/{session_id}/related")
async def api_related_sessions(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Find sessions that share concept nodes with the given session."""
    # Check if session_concepts has any data for this session
    check = await db.execute(
        select(func.count(SessionConcept.concept_id))
        .where(SessionConcept.session_id == session_id)
    )
    if check.scalar_one() == 0:
        return []

    # Self-join: find other sessions sharing concepts with this one
    my_concepts = (
        select(SessionConcept.concept_id)
        .where(SessionConcept.session_id == session_id)
    ).subquery()

    related_q = await db.execute(
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
        .limit(5)
    )
    related_rows = related_q.all()

    if not related_rows:
        return []

    related_ids = [r.session_id for r in related_rows]
    shared_counts = {r.session_id: r.shared_count for r in related_rows}

    # Fetch session details
    sess_result = await db.execute(
        select(Session).where(Session.id.in_(related_ids), Session.hidden_at.is_(None))
    )
    sessions = {s.id: s for s in sess_result.scalars().all()}

    results = []
    for sid in related_ids:
        session = sessions.get(sid)
        if not session:
            continue
        results.append({
            "session_id": session.id,
            "project": session.project,
            "date": session.started_at.isoformat().replace("+00:00", "Z") if session.started_at else None,
            "model": session.model,
            "summary": (session.summary_text or "")[:150],
            "shared_concepts": shared_counts.get(sid, 0),
            "conversation_id": session.conversation_id,
        })

    return results
