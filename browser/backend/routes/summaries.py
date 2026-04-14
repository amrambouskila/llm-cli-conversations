from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from db import get_summary_service
from schemas import SummaryDeleteResponse, SummaryStatus
from services.summary_service import SummaryService

router = APIRouter()


@router.get("/api/summary/titles", response_model=dict[str, str])
def api_summary_titles() -> dict[str, str]:
    """Return all cached summary titles as a map of {key: title}."""
    return SummaryService.get_all_titles()


@router.get(
    "/api/summary/conversation/{project_name}/{conversation_id}",
    response_model=SummaryStatus,
)
async def api_conv_summary_get(
    project_name: str,
    conversation_id: str,
    service: SummaryService = Depends(get_summary_service),
) -> dict:
    """Check if a summary exists for a conversation."""
    return await service.get_conversation_summary(project_name, conversation_id, "claude")


@router.post(
    "/api/summary/conversation/{project_name}/{conversation_id}",
    response_model=SummaryStatus,
)
async def api_conv_summary_request(
    project_name: str,
    conversation_id: str,
    provider: str = "claude",
    service: SummaryService = Depends(get_summary_service),
) -> dict | JSONResponse:
    """Request a hierarchical summary for an entire conversation."""
    result = await service.request_conversation_summary(project_name, conversation_id, provider)
    if result is None:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return result


@router.delete("/api/summary/{segment_id}", response_model=SummaryDeleteResponse)
def api_summary_delete(
    segment_id: str,
    service: SummaryService = Depends(get_summary_service),
) -> dict:
    """Delete a cached summary so it can be regenerated."""
    service.delete_summary(segment_id)
    return {"ok": True}


@router.get("/api/summary/{segment_id}", response_model=SummaryStatus)
def api_summary_get(
    segment_id: str,
    service: SummaryService = Depends(get_summary_service),
) -> dict:
    """Check if a summary exists for a segment."""
    return service.get_segment_summary(segment_id)


@router.post("/api/summary/{segment_id}", response_model=SummaryStatus)
async def api_summary_request(
    segment_id: str,
    provider: str = "claude",
    service: SummaryService = Depends(get_summary_service),
) -> dict | JSONResponse:
    """Request a summary for a segment."""
    result = await service.request_segment_summary(segment_id)
    if result is None:
        return JSONResponse({"error": "segment not found"}, status_code=404)
    return result
