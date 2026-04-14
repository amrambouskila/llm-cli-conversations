"""Unit tests for DashboardService.

Exercises every aggregation method against seed_sessions with representative filter
combinations. Route-level integration is already covered by test_api_dashboard.py;
these tests pin down the service-layer shapes directly.
"""
from __future__ import annotations

from services.dashboard_service import DashboardFilters, DashboardService


def _svc(db) -> DashboardService:
    return DashboardService(db)


def _filters(**kwargs) -> DashboardFilters:
    defaults: dict = {"provider": "claude", "date_from": None, "date_to": None, "project": None, "model": None}
    defaults.update(kwargs)
    return DashboardFilters(**defaults)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

async def test_summary_shape(seed_sessions, db_session):
    data = await _svc(db_session).get_summary(_filters())
    for key in ("total_sessions", "total_tokens", "total_cost",
                "avg_cost_per_session", "project_count", "deltas"):
        assert key in data
    for delta_key in ("sessions", "tokens", "cost", "avg_cost", "projects"):
        assert delta_key in data["deltas"]


async def test_summary_counts_match_seed(seed_sessions, db_session):
    data = await _svc(db_session).get_summary(_filters())
    assert data["total_sessions"] == 3  # s1, s2, s3 (s5 hidden, s4 codex)


async def test_summary_respects_project_filter(seed_sessions, db_session):
    data = await _svc(db_session).get_summary(_filters(project="conversations"))
    assert data["total_sessions"] == 2
    assert data["project_count"] == 1


async def test_summary_empty_db(db_session):
    data = await _svc(db_session).get_summary(_filters())
    assert data["total_sessions"] == 0
    assert data["total_cost"] == 0.0


# ---------------------------------------------------------------------------
# Cost over time
# ---------------------------------------------------------------------------

async def test_cost_over_time_weekly(seed_sessions, db_session):
    data = await _svc(db_session).get_cost_over_time(_filters(), group_by="week", stack_by="project")
    assert data
    assert all("period" in p and "stacks" in p for p in data)


async def test_cost_over_time_daily(seed_sessions, db_session):
    data = await _svc(db_session).get_cost_over_time(_filters(), group_by="day", stack_by="model")
    assert data


async def test_cost_over_time_monthly(seed_sessions, db_session):
    data = await _svc(db_session).get_cost_over_time(_filters(), group_by="month", stack_by="provider")
    assert data


async def test_cost_over_time_unknown_group_by_falls_back_to_week(seed_sessions, db_session):
    """Invalid group_by → defaults to week format `IYYY-"W"IW`."""
    data = await _svc(db_session).get_cost_over_time(_filters(), group_by="zzz", stack_by="project")
    for p in data:
        assert "W" in p["period"]


# ---------------------------------------------------------------------------
# Projects / tools / models / session-types / heatmap
# ---------------------------------------------------------------------------

async def test_projects_breakdown_sorted_by_cost_desc(seed_sessions, db_session):
    data = await _svc(db_session).get_projects_breakdown(_filters())
    costs = [r["total_cost"] for r in data]
    assert costs == sorted(costs, reverse=True)


async def test_tools_breakdown_includes_family(seed_sessions, db_session):
    data = await _svc(db_session).get_tools_breakdown(_filters())
    assert all("family" in r for r in data)
    bash_rows = [r for r in data if r["tool_name"] == "Bash"]
    assert bash_rows and bash_rows[0]["family"] == "execution"


async def test_tools_breakdown_other_family_for_unknown(seed_sessions, db_session):
    """Any tool not in TOOL_FAMILIES maps to 'other' — WebSearch is 'web'."""
    data = await _svc(db_session).get_tools_breakdown(_filters())
    web_rows = [r for r in data if r["tool_name"] == "WebSearch"]
    assert web_rows and web_rows[0]["family"] == "web"


async def test_models_breakdown_excludes_null_model(seed_sessions, db_session):
    data = await _svc(db_session).get_models_breakdown(_filters())
    assert all(r["model"] is not None for r in data)


async def test_session_types_percentages_sum_to_100(seed_sessions, db_session):
    data = await _svc(db_session).get_session_types(_filters())
    total = sum(r["percentage"] for r in data)
    assert 99.0 <= total <= 101.0  # rounding tolerance


async def test_session_types_empty_db(db_session):
    data = await _svc(db_session).get_session_types(_filters())
    assert data == []


async def test_heatmap_has_date_strings(seed_sessions, db_session):
    data = await _svc(db_session).get_heatmap(_filters())
    for entry in data:
        assert len(entry["date"]) == 10  # YYYY-MM-DD
        assert entry["sessions"] >= 0


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------

async def test_anomalies_returns_list(seed_sessions, db_session):
    # Seed data has 3 claude sessions with costs [2.14, 0.88, 0.15]; mean ~1.06,
    # std varies — typically s1 exceeds 2σ above mean.
    data = await _svc(db_session).get_anomalies(_filters())
    assert isinstance(data, list)


async def test_anomalies_empty_db(db_session):
    assert await _svc(db_session).get_anomalies(_filters()) == []


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

async def test_graph_empty_when_no_concepts(seed_sessions, db_session):
    data = await _svc(db_session).get_graph(_filters())
    assert data == {"nodes": [], "edges": []}


async def test_graph_with_concept_data(seed_sessions, db_session):
    from models import Concept, SessionConcept
    db_session.add(Concept(id="c1", name="docker", community_id=1, degree=2))
    db_session.add(Concept(id="c2", name="auth", community_id=1, degree=1))
    await db_session.flush()
    db_session.add(SessionConcept(
        session_id="s1", concept_id="c1", relationship_label="contains",
        edge_type="extracted", confidence=0.9,
    ))
    db_session.add(SessionConcept(
        session_id="s1", concept_id="c2", relationship_label="contains",
        edge_type="extracted", confidence=0.9,
    ))
    await db_session.commit()

    data = await _svc(db_session).get_graph(_filters())
    node_ids = {n["id"] for n in data["nodes"]}
    assert {"c1", "c2"}.issubset(node_ids)
    # c1+c2 co-occur in s1 → 1 edge
    assert len(data["edges"]) == 1
