from __future__ import annotations

from fastapi import APIRouter, Depends

from db import get_stats_service
from schemas import GlobalStats
from services.stats_service import StatsService

router = APIRouter()


@router.get("/api/stats", response_model=GlobalStats)
async def api_stats(
    provider: str = "claude",
    service: StatsService = Depends(get_stats_service),
) -> dict:
    """Return global statistics."""
    return await service.get_stats(provider)
