from __future__ import annotations

from fastapi import APIRouter, Depends

from db import get_session_service
from schemas import HiddenStateDetail, VisibilityResponse
from services.session_service import SessionService

router = APIRouter()


@router.post("/api/hide/segment/{segment_id}", response_model=VisibilityResponse)
async def api_hide_segment(
    segment_id: str,
    service: SessionService = Depends(get_session_service),
) -> dict:
    return {"ok": True, "hidden": await service.hide_segment(segment_id)}


@router.post("/api/restore/segment/{segment_id}", response_model=VisibilityResponse)
async def api_restore_segment(
    segment_id: str,
    service: SessionService = Depends(get_session_service),
) -> dict:
    return {"ok": True, "hidden": await service.restore_segment(segment_id)}


@router.post(
    "/api/hide/conversation/{project_name}/{conversation_id}",
    response_model=VisibilityResponse,
)
async def api_hide_conversation(
    project_name: str,
    conversation_id: str,
    service: SessionService = Depends(get_session_service),
) -> dict:
    return {"ok": True, "hidden": await service.hide_conversation(project_name, conversation_id)}


@router.post(
    "/api/restore/conversation/{project_name}/{conversation_id}",
    response_model=VisibilityResponse,
)
async def api_restore_conversation(
    project_name: str,
    conversation_id: str,
    service: SessionService = Depends(get_session_service),
) -> dict:
    return {"ok": True, "hidden": await service.restore_conversation(project_name, conversation_id)}


@router.post("/api/hide/project/{project_name}", response_model=VisibilityResponse)
async def api_hide_project(
    project_name: str,
    service: SessionService = Depends(get_session_service),
) -> dict:
    return {"ok": True, "hidden": await service.hide_project(project_name)}


@router.post("/api/restore/project/{project_name}", response_model=VisibilityResponse)
async def api_restore_project(
    project_name: str,
    service: SessionService = Depends(get_session_service),
) -> dict:
    return {"ok": True, "hidden": await service.restore_project(project_name)}


@router.post("/api/restore/all", response_model=VisibilityResponse)
async def api_restore_all(
    service: SessionService = Depends(get_session_service),
) -> dict:
    return {"ok": True, "hidden": await service.restore_all()}


@router.get("/api/hidden", response_model=HiddenStateDetail)
async def api_hidden(
    service: SessionService = Depends(get_session_service),
) -> dict:
    """Return full hidden state for the trash view."""
    return await service.get_hidden_detail()
