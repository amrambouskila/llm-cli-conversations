from __future__ import annotations

from typing import TYPE_CHECKING

from repositories.concept_repository import ConceptRepository
from repositories.segment_repository import SegmentRepository
from repositories.session_repository import SessionRepository
from repositories.tool_call_repository import ToolCallRepository

if TYPE_CHECKING:
    from models import Segment, Session


class SessionService:
    """Session-level read/write operations that aren't part of hybrid search.

    Covers: segment detail + export, full-conversation view, related-session
    discovery via the concept graph, hide/restore, and the "trash" view.
    """

    def __init__(
        self,
        sessions: SessionRepository,
        segments: SegmentRepository,
        tool_calls: ToolCallRepository,
        concepts: ConceptRepository,
    ) -> None:
        self.sessions = sessions
        self.segments = segments
        self.tool_calls = tool_calls
        self.concepts = concepts

    # ------------------------------------------------------------------
    # Segment detail / export
    # ------------------------------------------------------------------

    async def get_segment_detail(self, segment_id: str) -> dict | None:
        row = await self.segments.get_with_session(segment_id)
        if row is None:
            return None
        seg, session = row
        tool_breakdown = await self.tool_calls.get_breakdown_for_segment(segment_id)
        return _segment_to_dict(seg, session, tool_breakdown)

    async def get_segment_export(self, segment_id: str) -> dict | None:
        row = await self.segments.get_with_session(segment_id)
        if row is None:
            return None
        seg, session = row
        return {
            "filename": f"{session.project}_request_{(seg.segment_index or 0) + 1}.md",
            "content": seg.raw_text or "",
        }

    async def list_project_segments(
        self,
        project_name: str,
        provider: str,
        show_hidden: bool,
    ) -> list[dict] | None:
        """Return project's segment list with tool counts. None if project doesn't exist."""
        rows = await self.segments.list_project_segments(project_name, provider, show_hidden)
        if not rows:
            exists = await self.segments.project_exists(project_name, provider)
            if not exists:
                return None
            return []

        seg_ids = [seg.id for seg, _ in rows]
        tool_counts = await self.tool_calls.get_counts_by_segment(seg_ids)

        return [_segment_list_entry(seg, session, tool_counts.get(seg.id, 0)) for seg, session in rows]

    async def get_conversation_view(
        self,
        project_name: str,
        conversation_id: str,
        provider: str,
    ) -> dict | None:
        segments = await self.segments.list_conversation_segments(
            project_name, conversation_id, provider
        )
        if not segments:
            return None

        combined_markdown = "\n\n---\n\n".join(seg.raw_text or "" for seg in segments)
        total_chars = sum(s.char_count or 0 for s in segments)
        total_words = sum(s.word_count or 0 for s in segments)
        seg_ids = [s.id for s in segments]
        total_tools = await self.tool_calls.count_for_segments(seg_ids)

        # All segments of one conversation share a session_id (conversations and
        # sessions are 1:1 in the data model). Expose it so the frontend can fetch
        # the session-level cost-breakdown endpoint without an extra lookup.
        session_id = segments[0].session_id if segments else None

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
            "session_id": session_id,
        }

    # ------------------------------------------------------------------
    # Per-session cost breakdown
    # ------------------------------------------------------------------

    async def get_cost_breakdown(self, session_id: str) -> dict | None:
        """Return the 4-way USD cost breakdown for a single session.

        Returns None if the session does not exist. Computes from the stored
        token columns via estimate_cost_breakdown() so the value stays in sync
        with the dashboard aggregations (same pure function, same pricing table).
        """
        from load import estimate_cost_breakdown

        session = await self.sessions.get(session_id)
        if session is None:
            return None
        breakdown = estimate_cost_breakdown(
            input_tokens=session.input_tokens or 0,
            output_tokens=session.output_tokens or 0,
            cache_read_tokens=session.cache_read_tokens or 0,
            cache_creation_tokens=session.cache_creation_tokens or 0,
            model=session.model,
        )
        return breakdown.model_dump()

    # ------------------------------------------------------------------
    # Related sessions (Graphify concept graph)
    # ------------------------------------------------------------------

    async def get_related_sessions(self, session_id: str, limit: int = 5) -> list[dict]:
        if await self.concepts.count_concepts_for_session(session_id) == 0:
            return []
        related = await self.concepts.find_related_sessions(session_id, limit=limit)
        if not related:
            return []
        related_ids = [sid for sid, _ in related]
        shared_counts = dict(related)
        sessions_by_id = await self.concepts.get_visible_sessions_by_ids(related_ids)

        results: list[dict] = []
        for sid in related_ids:
            session = sessions_by_id.get(sid)
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

    # ------------------------------------------------------------------
    # Hide / restore + hidden state introspection
    # ------------------------------------------------------------------

    async def hide_segment(self, segment_id: str) -> dict:
        await self.segments.hide_segment(segment_id)
        return await self._hidden_counts()

    async def restore_segment(self, segment_id: str) -> dict:
        await self.segments.restore_segment(segment_id)
        return await self._hidden_counts()

    async def hide_conversation(self, project: str, conversation_id: str) -> dict:
        await self.sessions.hide_conversation(project, conversation_id)
        return await self._hidden_counts()

    async def restore_conversation(self, project: str, conversation_id: str) -> dict:
        await self.sessions.restore_conversation(project, conversation_id)
        return await self._hidden_counts()

    async def hide_project(self, project: str) -> dict:
        await self.sessions.hide_project(project)
        return await self._hidden_counts()

    async def restore_project(self, project: str) -> dict:
        await self.sessions.restore_project(project)
        return await self._hidden_counts()

    async def restore_all(self) -> dict:
        await self.sessions.restore_all_sessions()
        await self.segments.restore_all_segments()
        return await self._hidden_counts()

    async def get_hidden_detail(self) -> dict:
        """Full hidden state for the trash view."""
        hidden_segments_rows = await self.segments.list_hidden()
        hidden_segments = [
            {
                "id": seg.id,
                "preview": seg.preview or "",
                "project_name": session.project,
                "conversation_id": session.conversation_id,
                "hidden_at": seg.hidden_at.isoformat() if seg.hidden_at else None,
            }
            for seg, session in hidden_segments_rows
        ]

        hidden_conversations = [
            {
                "key": f"{project}:{conversation_id}",
                "hidden_at": hidden_at.isoformat() if hidden_at else None,
            }
            for project, conversation_id, hidden_at in await self.sessions.list_hidden_conversations()
        ]

        hidden_projects = [
            {
                "name": name,
                "hidden_at": hidden_at.isoformat() if hidden_at else None,
            }
            for name, hidden_at in await self.sessions.list_fully_hidden_projects()
        ]

        return {
            "segments": hidden_segments,
            "conversations": hidden_conversations,
            "projects": hidden_projects,
        }

    async def _hidden_counts(self) -> dict:
        segments = await self.segments.count_hidden()
        conversations = await self.sessions.count_hidden_conversations()
        projects = await self.sessions.count_fully_hidden_projects()
        return {
            "segments": segments,
            "conversations": conversations,
            "projects": projects,
        }


# ---------------------------------------------------------------------------
# Response shapers — kept module-level and pure so they stay unit-testable.
# ---------------------------------------------------------------------------


def _segment_to_dict(
    seg: Segment,
    session: Session,
    tool_breakdown: dict[str, int] | None = None,
) -> dict:
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


def _segment_list_entry(
    seg: Segment,
    session: Session,
    tool_call_count: int,
) -> dict:
    char_count = seg.char_count or 0
    word_count = seg.word_count or 0
    raw_text = seg.raw_text or ""
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
            "line_count": raw_text.count("\n") + 1,
            "estimated_tokens": max(1, char_count // 4),
            "tool_call_count": tool_call_count,
        },
        "hidden": seg.hidden_at is not None,
    }
