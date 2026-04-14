"""Integration tests for /api/dashboard/* — 9 endpoints + 3 graph endpoints."""
from __future__ import annotations

import json

import pytest

# ---------------------------------------------------------------------------
# /api/dashboard/summary
# ---------------------------------------------------------------------------

async def test_summary_returns_expected_shape(seed_sessions, api_client):
    response = await api_client.get("/api/dashboard/summary?provider=claude")
    assert response.status_code == 200
    data = response.json()
    for key in ("total_sessions", "total_tokens", "total_cost",
                "avg_cost_per_session", "project_count", "deltas"):
        assert key in data
    for delta_key in ("sessions", "tokens", "cost", "avg_cost", "projects"):
        assert delta_key in data["deltas"]


async def test_summary_counts_match_seed(seed_sessions, api_client):
    data = (await api_client.get("/api/dashboard/summary?provider=claude")).json()
    # Visible claude sessions: s1, s2, s3
    assert data["total_sessions"] == 3
    assert data["project_count"] == 2  # conversations + oft


async def test_summary_filtered_by_project(seed_sessions, api_client):
    data = (await api_client.get(
        "/api/dashboard/summary?provider=claude&project=conversations"
    )).json()
    assert data["total_sessions"] == 2  # s1, s2
    assert data["project_count"] == 1


async def test_summary_empty_db(api_client):
    data = (await api_client.get("/api/dashboard/summary?provider=claude")).json()
    assert data["total_sessions"] == 0
    assert data["total_cost"] == 0


# ---------------------------------------------------------------------------
# /api/dashboard/cost-over-time
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("group_by", ["day", "week", "month"])
async def test_cost_over_time_group_by_variants(seed_sessions, api_client, group_by):
    response = await api_client.get(
        f"/api/dashboard/cost-over-time?provider=claude&group_by={group_by}&stack_by=project"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for entry in data:
        assert "period" in entry
        assert "stacks" in entry


@pytest.mark.parametrize("stack_by", ["project", "model", "provider"])
async def test_cost_over_time_stack_by_variants(seed_sessions, api_client, stack_by):
    response = await api_client.get(
        f"/api/dashboard/cost-over-time?provider=claude&stack_by={stack_by}"
    )
    assert response.status_code == 200


async def test_cost_over_time_default_group_by_unknown_falls_back_to_week(seed_sessions, api_client):
    """Unrecognized group_by value falls into the else branch (week format)."""
    response = await api_client.get(
        "/api/dashboard/cost-over-time?provider=claude&group_by=invalid"
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /api/dashboard/projects
# ---------------------------------------------------------------------------

async def test_projects_breakdown_sorted_desc_by_cost(seed_sessions, api_client):
    data = (await api_client.get("/api/dashboard/projects?provider=claude")).json()
    assert isinstance(data, list)
    costs = [p["total_cost"] for p in data]
    assert costs == sorted(costs, reverse=True)
    for p in data:
        for key in ("project", "total_cost", "session_count", "avg_cost_per_session"):
            assert key in p


# ---------------------------------------------------------------------------
# /api/dashboard/tools
# ---------------------------------------------------------------------------

async def test_tools_breakdown_with_family(seed_sessions, api_client):
    data = (await api_client.get("/api/dashboard/tools?provider=claude")).json()
    assert isinstance(data, list)
    by_name = {t["tool_name"]: t for t in data}
    # Family mapping
    assert by_name["Read"]["family"] == "file_ops"
    assert by_name["Bash"]["family"] == "execution"
    assert by_name["Grep"]["family"] == "search"
    assert by_name["WebSearch"]["family"] == "web"


async def test_tools_sorted_desc_by_call_count(seed_sessions, api_client):
    data = (await api_client.get("/api/dashboard/tools?provider=claude")).json()
    counts = [t["call_count"] for t in data]
    assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# /api/dashboard/models
# ---------------------------------------------------------------------------

async def test_models_breakdown(seed_sessions, api_client):
    data = (await api_client.get("/api/dashboard/models?provider=claude")).json()
    assert isinstance(data, list)
    for m in data:
        for key in ("model", "total_sessions", "total_cost", "avg_tokens_per_session"):
            assert key in m
    models = [m["model"] for m in data]
    assert "claude-opus-4-6" in models
    assert "claude-sonnet-4-6" in models


# ---------------------------------------------------------------------------
# /api/dashboard/session-types
# ---------------------------------------------------------------------------

async def test_session_types_distribution(seed_sessions, api_client):
    data = (await api_client.get("/api/dashboard/session-types?provider=claude")).json()
    assert isinstance(data, list)
    for entry in data:
        for key in ("session_type", "count", "percentage", "avg_cost"):
            assert key in entry
    # Percentages should sum to ~100
    total_pct = sum(e["percentage"] for e in data)
    assert 99.0 <= total_pct <= 101.0


# ---------------------------------------------------------------------------
# /api/dashboard/heatmap
# ---------------------------------------------------------------------------

async def test_heatmap_returns_daily_buckets(seed_sessions, api_client):
    data = (await api_client.get("/api/dashboard/heatmap?provider=claude")).json()
    assert isinstance(data, list)
    for entry in data:
        for key in ("date", "sessions", "cost"):
            assert key in entry


# ---------------------------------------------------------------------------
# /api/dashboard/anomalies
# ---------------------------------------------------------------------------

async def test_anomalies_returns_list(seed_sessions, api_client):
    response = await api_client.get("/api/dashboard/anomalies?provider=claude")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for entry in data:
        for key in ("session_id", "project", "date", "turns",
                    "tokens", "cost", "conversation_id", "flag"):
            assert key in entry


async def test_anomalies_empty_when_no_data(api_client):
    data = (await api_client.get("/api/dashboard/anomalies?provider=claude")).json()
    assert data == []


# ---------------------------------------------------------------------------
# /api/dashboard/graph + status + generate + import
# ---------------------------------------------------------------------------

async def test_graph_returns_empty_when_no_concepts(seed_sessions, api_client):
    """No concepts in DB and no graph.json → empty nodes/edges."""
    response = await api_client.get("/api/dashboard/graph?provider=claude")
    assert response.status_code == 200
    data = response.json()
    assert data == {"nodes": [], "edges": []}


async def test_graph_returns_nodes_and_edges_with_concepts(seed_sessions, api_client, db_session):
    from models import Concept, SessionConcept
    db_session.add(Concept(id="c1", name="docker", type="topic", community_id=1, degree=5))
    db_session.add(Concept(id="c2", name="auth", type="topic", community_id=1, degree=3))
    db_session.add(SessionConcept(session_id="s1", concept_id="c1", relationship_label="contains",
                                  edge_type="extracted", confidence=0.9))
    db_session.add(SessionConcept(session_id="s1", concept_id="c2", relationship_label="contains",
                                  edge_type="extracted", confidence=0.9))
    db_session.add(SessionConcept(session_id="s2", concept_id="c1", relationship_label="contains",
                                  edge_type="extracted", confidence=0.9))
    await db_session.commit()

    data = (await api_client.get("/api/dashboard/graph?provider=claude")).json()
    assert len(data["nodes"]) == 2
    # c1 + c2 co-occur in s1, so 1 edge (sc1.concept_id < sc2.concept_id)
    assert len(data["edges"]) == 1
    edge = data["edges"][0]
    assert {edge["source"], edge["target"]} == {"c1", "c2"}


async def test_graph_status_no_data(seed_sessions, api_client, monkeypatch, tmp_path):
    monkeypatch.setattr("routes.dashboard.GRAPHIFY_OUT", tmp_path)
    response = await api_client.get("/api/dashboard/graph/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "none"
    assert data["has_data"] is False
    assert data["progress"] is None


async def test_graph_status_generating_with_progress(seed_sessions, api_client, monkeypatch, tmp_path):
    monkeypatch.setattr("routes.dashboard.GRAPHIFY_OUT", tmp_path)
    (tmp_path / ".generate_requested").write_text("1")
    (tmp_path / ".progress").write_text(json.dumps({
        "done": 5, "total": 10, "current": "file.md", "ok": 4, "failed": 1, "model": "opus",
    }))

    data = (await api_client.get("/api/dashboard/graph/status")).json()
    assert data["status"] == "generating"
    assert data["progress"]["done"] == 5
    assert data["progress"]["total"] == 10


async def test_graph_status_ready(seed_sessions, api_client, monkeypatch, tmp_path):
    monkeypatch.setattr("routes.dashboard.GRAPHIFY_OUT", tmp_path)
    (tmp_path / "graph.json").write_text("{}")
    data = (await api_client.get("/api/dashboard/graph/status")).json()
    assert data["status"] == "ready"


async def test_graph_generate_writes_trigger_files(api_client, monkeypatch, tmp_path):
    monkeypatch.setattr("routes.dashboard.GRAPHIFY_OUT", tmp_path)
    response = await api_client.post("/api/dashboard/graph/generate")
    assert response.status_code == 200
    assert response.json() == {"status": "generating"}
    assert (tmp_path / ".generate_requested").exists()
    assert (tmp_path / ".status").read_text() == "generating"


async def test_graph_import_no_file(api_client, monkeypatch, tmp_path):
    monkeypatch.setattr("routes.dashboard.GRAPHIFY_OUT", tmp_path)
    response = await api_client.post("/api/dashboard/graph/import")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "graph.json" in body["error"]


async def test_graph_import_with_minimal_graph_json(seed_sessions, api_client, monkeypatch, tmp_path):
    monkeypatch.setattr("routes.dashboard.GRAPHIFY_OUT", tmp_path)
    minimal = {
        "nodes": [
            {"id": "n1", "label": "docker", "source_file": "/anywhere/conversations.md"},
        ],
        "links": [],
    }
    (tmp_path / "graph.json").write_text(json.dumps(minimal))

    response = await api_client.post("/api/dashboard/graph/import")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


# ---------------------------------------------------------------------------
# Global filter passthrough — date_from, date_to, provider, project, model
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/dashboard/summary",
        "/api/dashboard/cost-over-time",
        "/api/dashboard/projects",
        "/api/dashboard/tools",
        "/api/dashboard/models",
        "/api/dashboard/session-types",
        "/api/dashboard/heatmap",
        "/api/dashboard/anomalies",
    ],
)
async def test_global_filters_accepted(seed_sessions, api_client, endpoint):
    response = await api_client.get(
        endpoint
        + "?provider=claude"
        + "&date_from=2026-03-01&date_to=2026-04-30"
        + "&project=conversations&model=opus"
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/dashboard/summary",
        "/api/dashboard/projects",
        "/api/dashboard/tools",
    ],
)
async def test_malformed_date_does_not_crash(seed_sessions, api_client, endpoint):
    response = await api_client.get(endpoint + "?provider=claude&date_from=not-a-date")
    assert response.status_code == 200
