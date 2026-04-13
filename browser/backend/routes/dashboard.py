from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Float, and_, cast, distinct, func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Concept, Segment, Session, SessionConcept, SessionTopic, ToolCall

GRAPHIFY_OUT = Path(os.environ.get("GRAPHIFY_OUT", "/data/graphify-out"))

router = APIRouter()

TOOL_FAMILIES = {
    "file_ops": ["Read", "Edit", "Write", "Glob", "NotebookEdit"],
    "search": ["Grep", "Agent"],
    "execution": ["Bash"],
    "web": ["WebSearch", "WebFetch"],
    "planning": ["TaskCreate", "TaskUpdate", "TodoWrite"],
}

TOOL_TO_FAMILY = {}
for family, tools in TOOL_FAMILIES.items():
    for tool in tools:
        TOOL_TO_FAMILY[tool] = family


def _parse_date(s: str) -> Optional[datetime]:
    """Parse a YYYY-MM-DD string to a timezone-aware datetime."""
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _apply_global_filters(
    stmt,
    provider: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    project: Optional[str],
    model: Optional[str],
):
    if provider:
        stmt = stmt.where(Session.provider == provider)
    stmt = stmt.where(Session.hidden_at.is_(None))
    if date_from:
        dt = _parse_date(date_from)
        if dt:
            stmt = stmt.where(Session.started_at >= dt)
    if date_to:
        dt = _parse_date(date_to)
        if dt:
            stmt = stmt.where(Session.started_at <= dt.replace(hour=23, minute=59, second=59))
    if project:
        stmt = stmt.where(Session.project == project)
    if model:
        stmt = stmt.where(Session.model.ilike(f"%%{model}%%"))
    return stmt


@router.get("/api/dashboard/summary")
async def dashboard_summary(
    provider: str = "claude",
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    base = select(
        func.count(Session.id).label("total_sessions"),
        func.coalesce(func.sum(Session.input_tokens), 0).label("total_input"),
        func.coalesce(func.sum(Session.output_tokens), 0).label("total_output"),
        func.coalesce(func.sum(Session.estimated_cost), 0).label("total_cost"),
        func.count(distinct(Session.project)).label("project_count"),
    )
    base = _apply_global_filters(base, provider, date_from, date_to, project, model)
    result = await db.execute(base)
    row = result.one()

    total_sessions = row.total_sessions
    total_tokens = int(row.total_input) + int(row.total_output)
    total_cost = float(row.total_cost)
    avg_cost = total_cost / total_sessions if total_sessions > 0 else 0
    project_count = row.project_count

    # Week-over-week deltas
    now = datetime.now(timezone.utc)
    last_7 = now - timedelta(days=7)
    prior_7 = now - timedelta(days=14)

    async def _week_stats(start: datetime, end: datetime):
        stmt = select(
            func.count(Session.id).label("sessions"),
            func.coalesce(func.sum(Session.input_tokens), 0).label("input_t"),
            func.coalesce(func.sum(Session.output_tokens), 0).label("output_t"),
            func.coalesce(func.sum(Session.estimated_cost), 0).label("cost"),
            func.count(distinct(Session.project)).label("projects"),
        ).where(
            Session.started_at >= start,
            Session.started_at < end,
            Session.hidden_at.is_(None),
        )
        if provider:
            stmt = stmt.where(Session.provider == provider)
        if project:
            stmt = stmt.where(Session.project == project)
        if model:
            stmt = stmt.where(Session.model.ilike(f"%%{model}%%"))
        r = await db.execute(stmt)
        return r.one()

    this_week = await _week_stats(last_7, now)
    prev_week = await _week_stats(prior_7, last_7)

    def _delta(current, previous):
        return int(current) - int(previous)

    this_tokens = int(this_week.input_t) + int(this_week.output_t)
    prev_tokens = int(prev_week.input_t) + int(prev_week.output_t)

    return {
        "total_sessions": total_sessions,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 2),
        "avg_cost_per_session": round(avg_cost, 4),
        "project_count": project_count,
        "deltas": {
            "sessions": _delta(this_week.sessions, prev_week.sessions),
            "tokens": _delta(this_tokens, prev_tokens),
            "cost": round(float(this_week.cost) - float(prev_week.cost), 2),
            "avg_cost": round(
                (float(this_week.cost) / max(1, this_week.sessions))
                - (float(prev_week.cost) / max(1, prev_week.sessions)),
                4,
            ),
            "projects": _delta(this_week.projects, prev_week.projects),
        },
    }


@router.get("/api/dashboard/cost-over-time")
async def dashboard_cost_over_time(
    group_by: str = Query("week"),
    stack_by: str = Query("project"),
    provider: str = "claude",
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if group_by == "day":
        period_expr = func.to_char(Session.started_at, "YYYY-MM-DD")
    elif group_by == "month":
        period_expr = func.to_char(Session.started_at, "YYYY-MM")
    else:
        period_expr = func.to_char(Session.started_at, "IYYY-\"W\"IW")

    stack_col = {
        "project": Session.project,
        "model": Session.model,
        "provider": Session.provider,
    }.get(stack_by, Session.project)

    stmt = (
        select(
            period_expr.label("period"),
            stack_col.label("stack"),
            func.coalesce(func.sum(Session.estimated_cost), 0).label("cost"),
        )
        .where(Session.started_at.is_not(None))
    )
    stmt = _apply_global_filters(stmt, provider, date_from, date_to, project, model)
    stmt = stmt.group_by(text("1"), text("2")).order_by(text("1"))

    result = await db.execute(stmt)
    rows = result.all()

    periods: dict[str, dict[str, float]] = {}
    for row in rows:
        p = row.period
        s = row.stack or "unknown"
        if p not in periods:
            periods[p] = {}
        periods[p][s] = round(float(row.cost), 4)

    return [{"period": p, "stacks": stacks} for p, stacks in periods.items()]


@router.get("/api/dashboard/projects")
async def dashboard_projects(
    provider: str = "claude",
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(
        Session.project,
        func.coalesce(func.sum(Session.estimated_cost), 0).label("total_cost"),
        func.count(Session.id).label("session_count"),
    )
    stmt = _apply_global_filters(stmt, provider, date_from, date_to, project, model)
    stmt = stmt.group_by(Session.project).order_by(text("total_cost DESC"))

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "project": r.project,
            "total_cost": round(float(r.total_cost), 4),
            "session_count": r.session_count,
            "avg_cost_per_session": round(float(r.total_cost) / max(1, r.session_count), 4),
        }
        for r in rows
    ]


@router.get("/api/dashboard/tools")
async def dashboard_tools(
    provider: str = "claude",
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(
            ToolCall.tool_name,
            func.count(ToolCall.id).label("call_count"),
            func.count(distinct(ToolCall.session_id)).label("session_count"),
        )
        .join(Session, ToolCall.session_id == Session.id)
    )
    stmt = _apply_global_filters(stmt, provider, date_from, date_to, project, model)
    stmt = stmt.group_by(ToolCall.tool_name).order_by(text("call_count DESC"))

    result = await db.execute(stmt)
    rows = result.all()

    tools = []
    for r in rows:
        family = TOOL_TO_FAMILY.get(r.tool_name, "other")
        tools.append({
            "tool_name": r.tool_name,
            "call_count": r.call_count,
            "session_count": r.session_count,
            "family": family,
        })

    return tools


@router.get("/api/dashboard/models")
async def dashboard_models(
    provider: str = "claude",
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(
        Session.model,
        func.count(Session.id).label("total_sessions"),
        func.coalesce(func.sum(Session.estimated_cost), 0).label("total_cost"),
        func.coalesce(
            func.avg(
                func.coalesce(Session.input_tokens, 0) + func.coalesce(Session.output_tokens, 0)
            ),
            0,
        ).label("avg_tokens_per_session"),
    )
    stmt = _apply_global_filters(stmt, provider, date_from, date_to, project, model)
    stmt = stmt.where(Session.model.is_not(None))
    stmt = stmt.group_by(Session.model).order_by(text("total_cost DESC"))

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "model": r.model,
            "total_sessions": r.total_sessions,
            "total_cost": round(float(r.total_cost), 4),
            "avg_tokens_per_session": round(float(r.avg_tokens_per_session)),
        }
        for r in rows
    ]


@router.get("/api/dashboard/session-types")
async def dashboard_session_types(
    provider: str = "claude",
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Total count for percentage calc
    total_stmt = select(func.count(Session.id))
    total_stmt = _apply_global_filters(total_stmt, provider, date_from, date_to, project, model)
    total_result = await db.execute(total_stmt)
    total = total_result.scalar_one()

    stmt = select(
        func.coalesce(Session.session_type, "unknown").label("session_type"),
        func.count(Session.id).label("count"),
        func.coalesce(func.avg(Session.estimated_cost), 0).label("avg_cost"),
    )
    stmt = _apply_global_filters(stmt, provider, date_from, date_to, project, model)
    stmt = stmt.group_by(text("1")).order_by(text("count DESC"))

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "session_type": r.session_type,
            "count": r.count,
            "percentage": round(r.count / max(1, total) * 100, 1),
            "avg_cost": round(float(r.avg_cost), 4),
        }
        for r in rows
    ]


@router.get("/api/dashboard/heatmap")
async def dashboard_heatmap(
    provider: str = "claude",
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Last 365 days of daily activity
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)

    stmt = (
        select(
            func.to_char(Session.started_at, "YYYY-MM-DD").label("date"),
            func.count(Session.id).label("sessions"),
            func.coalesce(func.sum(Session.estimated_cost), 0).label("cost"),
        )
        .where(Session.started_at >= cutoff)
    )
    stmt = _apply_global_filters(stmt, provider, date_from, date_to, project, model)
    stmt = stmt.group_by(text("1")).order_by(text("1"))

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "date": r.date,
            "sessions": r.sessions,
            "cost": round(float(r.cost), 2),
        }
        for r in rows
    ]


@router.get("/api/dashboard/anomalies")
async def dashboard_anomalies(
    provider: str = "claude",
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Compute mean and stddev of cost
    stats_stmt = select(
        func.avg(Session.estimated_cost).label("mean_cost"),
        func.stddev(Session.estimated_cost).label("std_cost"),
    )
    stats_stmt = _apply_global_filters(stats_stmt, provider, date_from, date_to, project, model)
    stats_stmt = stats_stmt.where(Session.estimated_cost.is_not(None))
    stats_result = await db.execute(stats_stmt)
    stats_row = stats_result.one()

    mean_cost = float(stats_row.mean_cost or 0)
    std_cost = float(stats_row.std_cost or 0)
    threshold = mean_cost + 2 * std_cost if std_cost > 0 else mean_cost * 2

    # Fetch sessions above cost threshold
    stmt = (
        select(
            Session.id,
            Session.project,
            Session.started_at,
            Session.turn_count,
            Session.input_tokens,
            Session.output_tokens,
            Session.estimated_cost,
            Session.conversation_id,
        )
        .where(
            Session.estimated_cost > threshold,
            Session.estimated_cost.is_not(None),
        )
    )
    stmt = _apply_global_filters(stmt, provider, date_from, date_to, project, model)
    stmt = stmt.order_by(Session.estimated_cost.desc()).limit(20)

    result = await db.execute(stmt)
    rows = result.all()

    anomalies = []
    for r in rows:
        tokens = (r.input_tokens or 0) + (r.output_tokens or 0)
        anomalies.append({
            "session_id": r.id,
            "project": r.project,
            "date": r.started_at.isoformat().replace("+00:00", "Z") if r.started_at else None,
            "turns": r.turn_count,
            "tokens": tokens,
            "cost": round(float(r.estimated_cost or 0), 4),
            "conversation_id": r.conversation_id,
            "flag": "High cost",
        })

    return anomalies


@router.get("/api/dashboard/graph")
async def dashboard_graph(
    provider: str = "claude",
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Check if concepts table has any data — if not, try importing graph.json
    count_result = await db.execute(select(func.count(Concept.id)))
    if count_result.scalar_one() == 0:
        graph_file = GRAPHIFY_OUT / "graph.json"
        if graph_file.exists():
            try:
                from import_graph import import_graph
                await import_graph(str(graph_file))
                print("Graph imported on demand from graph.json")
            except Exception as e:
                print(f"Graph import failed: {e}")
                return {"nodes": [], "edges": []}
            # Re-check after import
            count_result = await db.execute(select(func.count(Concept.id)))
            if count_result.scalar_one() == 0:
                return {"nodes": [], "edges": []}
        else:
            return {"nodes": [], "edges": []}

    # Get session IDs matching filters
    session_filter = select(Session.id)
    session_filter = _apply_global_filters(session_filter, provider, date_from, date_to, project, model)
    session_ids_sub = session_filter.subquery()

    # Get concepts linked to matching sessions
    concept_ids_stmt = (
        select(distinct(SessionConcept.concept_id))
        .where(SessionConcept.session_id.in_(select(session_ids_sub.c.id)))
    )
    concept_ids_result = await db.execute(concept_ids_stmt)
    concept_ids = [r[0] for r in concept_ids_result.all()]

    if not concept_ids:
        return {"nodes": [], "edges": []}

    # Cap at 200 most-connected concepts to keep d3 visualization manageable
    if len(concept_ids) > 200:
        top_concepts = await db.execute(
            select(Concept.id)
            .where(Concept.id.in_(concept_ids))
            .order_by(Concept.degree.desc().nulls_last())
            .limit(200)
        )
        concept_ids = [r[0] for r in top_concepts.all()]

    # Fetch concept details
    concepts_result = await db.execute(
        select(Concept).where(Concept.id.in_(concept_ids))
    )
    concepts = concepts_result.scalars().all()

    # Count sessions per concept (within filter)
    session_counts_result = await db.execute(
        select(
            SessionConcept.concept_id,
            func.count(distinct(SessionConcept.session_id)).label("session_count"),
        )
        .where(
            SessionConcept.concept_id.in_(concept_ids),
            SessionConcept.session_id.in_(select(session_ids_sub.c.id)),
        )
        .group_by(SessionConcept.concept_id)
    )
    session_counts = {r.concept_id: r.session_count for r in session_counts_result.all()}

    nodes = [
        {
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "community_id": c.community_id,
            "degree": c.degree or 0,
            "session_count": session_counts.get(c.id, 0),
        }
        for c in concepts
    ]

    # Build co-occurrence edges: concepts sharing sessions
    # Self-join session_concepts to find concept pairs co-occurring in the same session
    sc1 = SessionConcept.__table__.alias("sc1")
    sc2 = SessionConcept.__table__.alias("sc2")

    edges_stmt = (
        select(
            sc1.c.concept_id.label("source"),
            sc2.c.concept_id.label("target"),
            func.count(distinct(sc1.c.session_id)).label("weight"),
        )
        .select_from(sc1)
        .join(sc2, and_(sc1.c.session_id == sc2.c.session_id, sc1.c.concept_id < sc2.c.concept_id))
        .where(
            sc1.c.concept_id.in_(concept_ids),
            sc2.c.concept_id.in_(concept_ids),
            sc1.c.session_id.in_(select(session_ids_sub.c.id)),
        )
        .group_by(sc1.c.concept_id, sc2.c.concept_id)
        .having(func.count(distinct(sc1.c.session_id)) > 0)
    )
    edges_result = await db.execute(edges_stmt)
    edges = [
        {"source": r.source, "target": r.target, "weight": r.weight}
        for r in edges_result.all()
    ]

    return {"nodes": nodes, "edges": edges}


@router.get("/api/dashboard/graph/status")
async def dashboard_graph_status(db: AsyncSession = Depends(get_db)):
    """Return graph generation status, progress, and whether data exists."""
    count_result = await db.execute(select(func.count(Concept.id)))
    has_data = count_result.scalar_one() > 0

    status_file = GRAPHIFY_OUT / ".status"
    graph_file = GRAPHIFY_OUT / "graph.json"
    trigger_file = GRAPHIFY_OUT / ".generate_requested"

    if trigger_file.exists():
        status = "generating"
    elif status_file.exists():
        status = status_file.read_text(encoding="utf-8").strip()
    elif graph_file.exists():
        status = "ready"
    else:
        status = "none"

    progress = None
    if status == "generating":
        progress_file = GRAPHIFY_OUT / ".progress"
        if progress_file.exists():
            try:
                progress = json.loads(progress_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        if progress is None:
            progress = {"done": 0, "total": 0, "current": None, "ok": 0, "failed": 0, "model": ""}

    return {"status": status, "has_data": has_data, "progress": progress}


@router.post("/api/dashboard/graph/generate")
async def dashboard_graph_generate():
    """Trigger graph re-generation by writing a request file for the host watcher."""
    GRAPHIFY_OUT.mkdir(parents=True, exist_ok=True)
    trigger = GRAPHIFY_OUT / ".generate_requested"
    trigger.write_text("1", encoding="utf-8")
    status_file = GRAPHIFY_OUT / ".status"
    status_file.write_text("generating", encoding="utf-8")
    return {"status": "generating"}


@router.post("/api/dashboard/graph/import")
async def dashboard_graph_import():
    """Import graph.json from disk into Postgres on demand."""
    graph_file = GRAPHIFY_OUT / "graph.json"
    if not graph_file.exists():
        return {"ok": False, "error": "No graph.json found"}

    try:
        from import_graph import import_graph
        await import_graph(str(graph_file))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
