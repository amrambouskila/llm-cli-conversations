from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models import Segment, Session, ToolCall


class ProjectService:
    """Provider and project-level aggregations.

    Per-project stats are bespoke shapes (request sizes, conversation timeline,
    tool breakdown) that no other endpoint needs — so the queries live here
    rather than being fanned out across four repositories.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_providers(self) -> list[dict]:
        result = await self.db.execute(
            select(
                Session.provider,
                func.count(func.distinct(Session.project)).label("projects"),
                func.count(Session.id).label("sessions"),
            )
            .group_by(Session.provider)
        )
        rows = result.all()

        seg_result = await self.db.execute(
            select(
                Session.provider,
                func.count(Segment.id).label("segments"),
            )
            .join(Segment, Segment.session_id == Session.id)
            .group_by(Session.provider)
        )
        seg_counts = {r.provider: r.segments for r in seg_result.all()}

        providers = [
            {
                "id": row.provider,
                "name": row.provider.title(),
                "projects": row.projects,
                "segments": seg_counts.get(row.provider, 0),
            }
            for row in rows
        ]
        if not any(p["id"] == "claude" for p in providers):
            providers.insert(0, {"id": "claude", "name": "Claude", "projects": 0, "segments": 0})
        return providers

    async def list_projects(
        self,
        provider: str,
        show_hidden: bool,
    ) -> list[dict]:
        filters = [Session.provider == provider]
        if not show_hidden:
            filters.append(Session.hidden_at.is_(None))

        proj_result = await self.db.execute(
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

        result: list[dict] = []
        for proj in projects:
            result.append(await self._build_project_entry(proj, provider, show_hidden))
        return result

    async def _build_project_entry(
        self,
        proj_row: object,
        provider: str,
        show_hidden: bool,
    ) -> dict:
        project_name = proj_row.project
        seg_filters = [Session.provider == provider, Session.project == project_name]
        if not show_hidden:
            seg_filters.extend([Session.hidden_at.is_(None), Segment.hidden_at.is_(None)])

        seg_result = await self.db.execute(
            select(
                func.count(Segment.id).label("total_requests"),
                func.coalesce(func.sum(Segment.char_count), 0).label("total_chars"),
                func.coalesce(func.sum(Segment.word_count), 0).label("total_words"),
            )
            .join(Session, Segment.session_id == Session.id)
            .where(*seg_filters)
        )
        seg_row = seg_result.one()

        tool_result = await self.db.execute(
            select(func.count(ToolCall.id))
            .join(Session, ToolCall.session_id == Session.id)
            .where(Session.provider == provider, Session.project == project_name)
        )
        total_tools = tool_result.scalar_one()

        tool_bd_result = await self.db.execute(
            select(ToolCall.tool_name, func.count(ToolCall.id).label("cnt"))
            .join(Session, ToolCall.session_id == Session.id)
            .where(Session.provider == provider, Session.project == project_name)
            .group_by(ToolCall.tool_name)
            .order_by(func.count(ToolCall.id).desc())
        )
        tool_breakdown = {r.tool_name: r.cnt for r in tool_bd_result.all()}

        sizes_result = await self.db.execute(
            select(Segment.word_count)
            .join(Session, Segment.session_id == Session.id)
            .where(*seg_filters)
            .order_by(Segment.timestamp, Segment.segment_index)
        )
        request_sizes = [r.word_count or 0 for r in sizes_result.all()]

        timeline_result = await self.db.execute(
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

        file_result = await self.db.execute(
            select(func.count(func.distinct(Session.source_file)))
            .where(Session.provider == provider, Session.project == project_name)
        )
        total_files = file_result.scalar_one()

        is_hidden = False
        if show_hidden:
            hidden_check = await self.db.execute(
                select(
                    func.count(Session.id).label("total"),
                    func.count(Session.hidden_at).label("hidden_count"),
                )
                .where(Session.provider == provider, Session.project == project_name)
            )
            hc = hidden_check.one()
            is_hidden = hc.total > 0 and hc.hidden_count == hc.total

        total_chars = seg_row.total_chars
        first_ts = proj_row.first_timestamp
        last_ts = proj_row.last_timestamp

        return {
            "name": project_name,
            "display_name": project_name,
            "total_requests": seg_row.total_requests,
            "total_files": total_files,
            "hidden": is_hidden,
            "stats": {
                "total_conversations": proj_row.total_conversations,
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
        }
