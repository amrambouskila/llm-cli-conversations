from __future__ import annotations

from fastapi import APIRouter, Depends

from db import get_project_service
from schemas import ProjectEntry, ProviderEntry
from services.project_service import ProjectService

router = APIRouter()


@router.get("/api/providers", response_model=list[ProviderEntry])
async def api_providers(
    service: ProjectService = Depends(get_project_service),
) -> list[dict]:
    """Return available providers and their project counts."""
    return await service.list_providers()


@router.get("/api/projects", response_model=list[ProjectEntry])
async def api_projects(
    show_hidden: bool = False,
    provider: str = "claude",
    service: ProjectService = Depends(get_project_service),
) -> list[dict]:
    """Return list of projects with summaries including per-project stats."""
    return await service.list_projects(provider, show_hidden)
