from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from db import get_dashboard_service, get_graph_service
from schemas import (
    AnomalyRow,
    CostOverTimePeriod,
    DashboardSummary,
    GraphGenerateResponse,
    GraphImportResponse,
    GraphResponse,
    GraphStatus,
    HeatmapDay,
    ModelBreakdown,
    ProjectBreakdown,
    SessionTypeDistribution,
    ToolUsage,
)
from services.dashboard_service import DashboardFilters, DashboardService
from services.graph_service import GraphService

router = APIRouter()


def _filters(
    provider: str = "claude",
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    project: str | None = Query(None),
    model: str | None = Query(None),
) -> DashboardFilters:
    return DashboardFilters(
        provider=provider,
        date_from=date_from,
        date_to=date_to,
        project=project,
        model=model,
    )


@router.get("/api/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    filters: DashboardFilters = Depends(_filters),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    return await service.get_summary(filters)


@router.get("/api/dashboard/cost-over-time", response_model=list[CostOverTimePeriod])
async def dashboard_cost_over_time(
    group_by: str = Query("week"),
    stack_by: str = Query("project"),
    filters: DashboardFilters = Depends(_filters),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[dict]:
    return await service.get_cost_over_time(filters, group_by=group_by, stack_by=stack_by)


@router.get("/api/dashboard/projects", response_model=list[ProjectBreakdown])
async def dashboard_projects(
    filters: DashboardFilters = Depends(_filters),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[dict]:
    return await service.get_projects_breakdown(filters)


@router.get("/api/dashboard/tools", response_model=list[ToolUsage])
async def dashboard_tools(
    filters: DashboardFilters = Depends(_filters),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[dict]:
    return await service.get_tools_breakdown(filters)


@router.get("/api/dashboard/models", response_model=list[ModelBreakdown])
async def dashboard_models(
    filters: DashboardFilters = Depends(_filters),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[dict]:
    return await service.get_models_breakdown(filters)


@router.get("/api/dashboard/session-types", response_model=list[SessionTypeDistribution])
async def dashboard_session_types(
    filters: DashboardFilters = Depends(_filters),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[dict]:
    return await service.get_session_types(filters)


@router.get("/api/dashboard/heatmap", response_model=list[HeatmapDay])
async def dashboard_heatmap(
    filters: DashboardFilters = Depends(_filters),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[dict]:
    return await service.get_heatmap(filters)


@router.get("/api/dashboard/anomalies", response_model=list[AnomalyRow])
async def dashboard_anomalies(
    filters: DashboardFilters = Depends(_filters),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[dict]:
    return await service.get_anomalies(filters)


@router.get("/api/dashboard/graph", response_model=GraphResponse)
async def dashboard_graph(
    filters: DashboardFilters = Depends(_filters),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    return await service.get_graph(filters)


@router.get("/api/dashboard/graph/status", response_model=GraphStatus)
async def dashboard_graph_status(
    service: GraphService = Depends(get_graph_service),
) -> dict:
    return await service.get_status()


@router.post("/api/dashboard/graph/generate", response_model=GraphGenerateResponse)
async def dashboard_graph_generate(
    service: GraphService = Depends(get_graph_service),
) -> dict:
    return await service.trigger_regeneration()


@router.post(
    "/api/dashboard/graph/import",
    response_model=GraphImportResponse,
    response_model_exclude_none=True,
)
async def dashboard_graph_import(
    service: GraphService = Depends(get_graph_service),
) -> dict:
    # Omit the `error` field on success — matches the pre-response_model shape.
    return await service.import_from_disk()
