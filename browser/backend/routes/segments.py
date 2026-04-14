from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from db import get_search_service, get_session_service
from schemas import (
    RelatedSession,
    SearchFilterValues,
    SearchStatus,
    SegmentDetail,
    SegmentExport,
    SessionSearchResult,
)
from services.search_service import SearchService
from services.session_service import SessionService

router = APIRouter()


@router.get("/api/segments/{segment_id}/export", response_model=SegmentExport)
async def api_segment_export(
    segment_id: str,
    provider: str = "claude",
    service: SessionService = Depends(get_session_service),
) -> dict | JSONResponse:
    """Return raw markdown for download/copy."""
    data = await service.get_segment_export(segment_id)
    if data is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return data


@router.get("/api/segments/{segment_id}", response_model=SegmentDetail)
async def api_segment_detail(
    segment_id: str,
    provider: str = "claude",
    service: SessionService = Depends(get_session_service),
) -> dict | JSONResponse:
    """Return full segment data including raw markdown."""
    data = await service.get_segment_detail(segment_id)
    if data is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return data


@router.get("/api/search", response_model=list[SessionSearchResult])
async def api_search(
    q: str | None = Query(None),
    show_hidden: bool = False,
    provider: str = "claude",
    service: SearchService = Depends(get_search_service),
) -> list[dict]:
    """Hybrid semantic + keyword search returning session-level results."""
    return await service.search(query=q, provider=provider, show_hidden=show_hidden)


@router.get("/api/search/status", response_model=SearchStatus)
async def api_search_status(
    provider: str = "claude",
    service: SearchService = Depends(get_search_service),
) -> dict:
    """Report embedding + graph coverage so the frontend can show search mode."""
    return await service.get_status(provider)


@router.get("/api/search/filters", response_model=SearchFilterValues)
async def api_search_filters(
    provider: str = "claude",
    service: SearchService = Depends(get_search_service),
) -> dict:
    """Return distinct values for filter autocomplete."""
    return await service.get_filters(provider)


@router.get("/api/sessions/{session_id}/related", response_model=list[RelatedSession])
async def api_related_sessions(
    session_id: str,
    service: SessionService = Depends(get_session_service),
) -> list[dict]:
    """Find sessions that share concept nodes with the given session."""
    return await service.get_related_sessions(session_id)
