from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import and_, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models import Concept, Session, SessionConcept, ToolCall

if TYPE_CHECKING:
    from sqlalchemy.sql.selectable import Select


GRAPHIFY_OUT = Path(os.environ.get("GRAPHIFY_OUT", "/data/graphify-out"))


TOOL_FAMILIES: dict[str, list[str]] = {
    "file_ops": ["Read", "Edit", "Write", "Glob", "NotebookEdit"],
    "search": ["Grep", "Agent"],
    "execution": ["Bash"],
    "web": ["WebSearch", "WebFetch"],
    "planning": ["TaskCreate", "TaskUpdate", "TodoWrite"],
}
TOOL_TO_FAMILY: dict[str, str] = {
    tool: family for family, tools in TOOL_FAMILIES.items() for tool in tools
}


@dataclass
class DashboardFilters:
    """Global filter bag for every /api/dashboard/* endpoint.

    date_from/date_to come in as YYYY-MM-DD strings from the query bar; invalid
    values are silently ignored to match the historical UI behavior.
    """

    provider: str | None = "claude"
    date_from: str | None = None
    date_to: str | None = None
    project: str | None = None
    model: str | None = None

    def apply(self, stmt: Select) -> Select:
        if self.provider:
            stmt = stmt.where(Session.provider == self.provider)
        stmt = stmt.where(Session.hidden_at.is_(None))
        if self.date_from:
            dt = _parse_date(self.date_from)
            if dt:
                stmt = stmt.where(Session.started_at >= dt)
        if self.date_to:
            dt = _parse_date(self.date_to)
            if dt:
                stmt = stmt.where(Session.started_at <= dt.replace(hour=23, minute=59, second=59))
        if self.project:
            stmt = stmt.where(Session.project == self.project)
        if self.model:
            stmt = stmt.where(Session.model.ilike(f"%{self.model}%"))
        return stmt


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


class DashboardService:
    """Read-model service for every /api/dashboard/* endpoint.

    These are pure aggregations — no write operations. Queries span multiple
    ORM entities and return shaped response dicts, so they live here rather than
    in per-model repositories.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_summary(self, filters: DashboardFilters) -> dict:
        base = select(
            func.count(Session.id).label("total_sessions"),
            func.coalesce(func.sum(Session.input_tokens), 0).label("total_input"),
            func.coalesce(func.sum(Session.output_tokens), 0).label("total_output"),
            func.coalesce(func.sum(Session.estimated_cost), 0).label("total_cost"),
            func.count(distinct(Session.project)).label("project_count"),
        )
        base = filters.apply(base)
        result = await self.db.execute(base)
        row = result.one()

        total_sessions = row.total_sessions
        total_tokens = int(row.total_input) + int(row.total_output)
        total_cost = float(row.total_cost)
        avg_cost = total_cost / total_sessions if total_sessions > 0 else 0
        project_count = row.project_count

        now = datetime.now(UTC)
        last_7 = now - timedelta(days=7)
        prior_7 = now - timedelta(days=14)

        this_week = await self._week_stats(filters, last_7, now)
        prev_week = await self._week_stats(filters, prior_7, last_7)

        this_tokens = int(this_week.input_t) + int(this_week.output_t)
        prev_tokens = int(prev_week.input_t) + int(prev_week.output_t)

        return {
            "total_sessions": total_sessions,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 2),
            "avg_cost_per_session": round(avg_cost, 4),
            "project_count": project_count,
            "deltas": {
                "sessions": int(this_week.sessions) - int(prev_week.sessions),
                "tokens": this_tokens - prev_tokens,
                "cost": round(float(this_week.cost) - float(prev_week.cost), 2),
                "avg_cost": round(
                    (float(this_week.cost) / max(1, this_week.sessions))
                    - (float(prev_week.cost) / max(1, prev_week.sessions)),
                    4,
                ),
                "projects": int(this_week.projects) - int(prev_week.projects),
            },
        }

    async def _week_stats(
        self,
        filters: DashboardFilters,
        start: datetime,
        end: datetime,
    ) -> object:
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
        # Date filters don't apply here — this is a fixed 7-day window.
        if filters.provider:
            stmt = stmt.where(Session.provider == filters.provider)
        if filters.project:
            stmt = stmt.where(Session.project == filters.project)
        if filters.model:
            stmt = stmt.where(Session.model.ilike(f"%{filters.model}%"))
        result = await self.db.execute(stmt)
        return result.one()

    async def get_cost_over_time(
        self,
        filters: DashboardFilters,
        group_by: str = "week",
        stack_by: str = "project",
    ) -> list[dict]:
        if group_by == "day":
            period_expr = func.to_char(Session.started_at, "YYYY-MM-DD")
        elif group_by == "month":
            period_expr = func.to_char(Session.started_at, "YYYY-MM")
        else:
            period_expr = func.to_char(Session.started_at, 'IYYY-"W"IW')

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
        stmt = filters.apply(stmt)
        stmt = stmt.group_by(text("1"), text("2")).order_by(text("1"))

        result = await self.db.execute(stmt)
        periods: dict[str, dict[str, float]] = {}
        for row in result.all():
            periods.setdefault(row.period, {})[row.stack or "unknown"] = round(float(row.cost), 4)
        return [{"period": p, "stacks": stacks} for p, stacks in periods.items()]

    async def get_projects_breakdown(self, filters: DashboardFilters) -> list[dict]:
        stmt = select(
            Session.project,
            func.coalesce(func.sum(Session.estimated_cost), 0).label("total_cost"),
            func.count(Session.id).label("session_count"),
        )
        stmt = filters.apply(stmt)
        stmt = stmt.group_by(Session.project).order_by(text("total_cost DESC"))
        result = await self.db.execute(stmt)
        return [
            {
                "project": r.project,
                "total_cost": round(float(r.total_cost), 4),
                "session_count": r.session_count,
                "avg_cost_per_session": round(float(r.total_cost) / max(1, r.session_count), 4),
            }
            for r in result.all()
        ]

    async def get_tools_breakdown(self, filters: DashboardFilters) -> list[dict]:
        stmt = (
            select(
                ToolCall.tool_name,
                func.count(ToolCall.id).label("call_count"),
                func.count(distinct(ToolCall.session_id)).label("session_count"),
            )
            .join(Session, ToolCall.session_id == Session.id)
        )
        stmt = filters.apply(stmt)
        stmt = stmt.group_by(ToolCall.tool_name).order_by(text("call_count DESC"))
        result = await self.db.execute(stmt)
        return [
            {
                "tool_name": r.tool_name,
                "call_count": r.call_count,
                "session_count": r.session_count,
                "family": TOOL_TO_FAMILY.get(r.tool_name, "other"),
            }
            for r in result.all()
        ]

    async def get_models_breakdown(self, filters: DashboardFilters) -> list[dict]:
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
        stmt = filters.apply(stmt)
        stmt = stmt.where(Session.model.is_not(None))
        stmt = stmt.group_by(Session.model).order_by(text("total_cost DESC"))
        result = await self.db.execute(stmt)
        return [
            {
                "model": r.model,
                "total_sessions": r.total_sessions,
                "total_cost": round(float(r.total_cost), 4),
                "avg_tokens_per_session": round(float(r.avg_tokens_per_session)),
            }
            for r in result.all()
        ]

    async def get_session_types(self, filters: DashboardFilters) -> list[dict]:
        total_stmt = filters.apply(select(func.count(Session.id)))
        total = (await self.db.execute(total_stmt)).scalar_one()

        stmt = select(
            func.coalesce(Session.session_type, "unknown").label("session_type"),
            func.count(Session.id).label("count"),
            func.coalesce(func.avg(Session.estimated_cost), 0).label("avg_cost"),
        )
        stmt = filters.apply(stmt)
        stmt = stmt.group_by(text("1")).order_by(text("count DESC"))
        result = await self.db.execute(stmt)
        return [
            {
                "session_type": r.session_type,
                "count": r.count,
                "percentage": round(r.count / max(1, total) * 100, 1),
                "avg_cost": round(float(r.avg_cost), 4),
            }
            for r in result.all()
        ]

    async def get_heatmap(self, filters: DashboardFilters) -> list[dict]:
        cutoff = datetime.now(UTC) - timedelta(days=365)
        stmt = (
            select(
                func.to_char(Session.started_at, "YYYY-MM-DD").label("date"),
                func.count(Session.id).label("sessions"),
                func.coalesce(func.sum(Session.estimated_cost), 0).label("cost"),
            )
            .where(Session.started_at >= cutoff)
        )
        stmt = filters.apply(stmt)
        stmt = stmt.group_by(text("1")).order_by(text("1"))
        result = await self.db.execute(stmt)
        return [
            {
                "date": r.date,
                "sessions": r.sessions,
                "cost": round(float(r.cost), 2),
            }
            for r in result.all()
        ]

    async def get_anomalies(self, filters: DashboardFilters) -> list[dict]:
        stats_stmt = select(
            func.avg(Session.estimated_cost).label("mean_cost"),
            func.stddev(Session.estimated_cost).label("std_cost"),
        )
        stats_stmt = filters.apply(stats_stmt)
        stats_stmt = stats_stmt.where(Session.estimated_cost.is_not(None))
        stats_row = (await self.db.execute(stats_stmt)).one()

        mean_cost = float(stats_row.mean_cost or 0)
        std_cost = float(stats_row.std_cost or 0)
        threshold = mean_cost + 2 * std_cost if std_cost > 0 else mean_cost * 2

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
        stmt = filters.apply(stmt)
        stmt = stmt.order_by(Session.estimated_cost.desc()).limit(20)
        result = await self.db.execute(stmt)
        anomalies: list[dict] = []
        for r in result.all():
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

    async def get_graph(self, filters: DashboardFilters) -> dict:
        count_result = await self.db.execute(select(func.count(Concept.id)))
        if count_result.scalar_one() == 0:
            # Auto-import from disk on first request, so the dashboard lights up
            # after the host-side extraction finishes without requiring a manual
            # POST to /api/dashboard/graph/import.
            graph_file = GRAPHIFY_OUT / "graph.json"
            if not graph_file.exists():
                return {"nodes": [], "edges": []}
            try:
                from import_graph import import_graph

                await import_graph(str(graph_file))
            except Exception as e:
                print(f"Graph import failed: {e}")
                return {"nodes": [], "edges": []}
            recheck = await self.db.execute(select(func.count(Concept.id)))
            if recheck.scalar_one() == 0:
                return {"nodes": [], "edges": []}

        session_filter = filters.apply(select(Session.id))
        session_ids_sub = session_filter.subquery()

        concept_ids_stmt = (
            select(distinct(SessionConcept.concept_id))
            .where(SessionConcept.session_id.in_(select(session_ids_sub.c.id)))
        )
        concept_ids_result = await self.db.execute(concept_ids_stmt)
        concept_ids = [r[0] for r in concept_ids_result.all()]

        if not concept_ids:
            return {"nodes": [], "edges": []}

        # Keep d3 responsive — cap at 200 most-connected concepts.
        if len(concept_ids) > 200:
            top_concepts = await self.db.execute(
                select(Concept.id)
                .where(Concept.id.in_(concept_ids))
                .order_by(Concept.degree.desc().nulls_last())
                .limit(200)
            )
            concept_ids = [r[0] for r in top_concepts.all()]

        concepts_result = await self.db.execute(
            select(Concept).where(Concept.id.in_(concept_ids))
        )
        concepts = concepts_result.scalars().all()

        session_counts_result = await self.db.execute(
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
        edges_result = await self.db.execute(edges_stmt)
        edges = [
            {"source": r.source, "target": r.target, "weight": r.weight}
            for r in edges_result.all()
        ]
        return {"nodes": nodes, "edges": edges}
