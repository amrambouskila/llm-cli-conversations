from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from db import get_session_service
from schemas import ConversationView, SegmentListEntry
from services.session_service import SessionService

router = APIRouter()


@router.get(
    "/api/projects/{project_name}/segments",
    response_model=list[SegmentListEntry],
)
async def api_project_segments(
    project_name: str,
    show_hidden: bool = False,
    provider: str = "claude",
    service: SessionService = Depends(get_session_service),
) -> list[dict] | JSONResponse:
    """Return segment list for a project (previews, no full content)."""
    data = await service.list_project_segments(project_name, provider, show_hidden)
    if data is None:
        return JSONResponse({"error": "project not found"}, status_code=404)
    return data


@router.get(
    "/api/projects/{project_name}/conversation/{conversation_id}",
    response_model=ConversationView,
)
async def api_conversation_view(
    project_name: str,
    conversation_id: str,
    provider: str = "claude",
    service: SessionService = Depends(get_session_service),
) -> dict | JSONResponse:
    """Return all segments for a single conversation, concatenated."""
    data = await service.get_conversation_view(project_name, conversation_id, provider)
    if data is None:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return data
