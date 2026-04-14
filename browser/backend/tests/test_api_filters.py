"""Integration tests for /api/search/filters — autocomplete source values."""
from __future__ import annotations


async def test_filters_returns_all_keys(seed_sessions, api_client):
    response = await api_client.get("/api/search/filters?provider=claude")
    assert response.status_code == 200
    data = response.json()
    for key in ("projects", "models", "tools", "topics"):
        assert key in data
        assert isinstance(data[key], list)


async def test_filters_projects_alphabetical_and_distinct(seed_sessions, api_client):
    data = (await api_client.get("/api/search/filters?provider=claude")).json()
    projects = data["projects"]
    assert projects == sorted(projects)
    assert len(projects) == len(set(projects))
    assert "conversations" in projects
    assert "oft" in projects


async def test_filters_models_distinct(seed_sessions, api_client):
    data = (await api_client.get("/api/search/filters?provider=claude")).json()
    models = data["models"]
    assert "claude-opus-4-6" in models
    assert "claude-sonnet-4-6" in models


async def test_filters_tools_alphabetical(seed_sessions, api_client):
    data = (await api_client.get("/api/search/filters?provider=claude")).json()
    tools = data["tools"]
    assert tools == sorted(tools)
    # seed tools touch claude sessions: Bash, Edit, Read, Grep, WebSearch
    for t in ("Bash", "Edit", "Read", "Grep", "WebSearch"):
        assert t in tools


async def test_filters_topics_alphabetical(seed_sessions, api_client):
    data = (await api_client.get("/api/search/filters?provider=claude")).json()
    topics = data["topics"]
    assert topics == sorted(topics)
    assert "docker" in topics


async def test_filters_empty_db(api_client):
    """All four arrays empty when DB is empty."""
    response = await api_client.get("/api/search/filters?provider=claude")
    data = response.json()
    assert data == {"projects": [], "models": [], "tools": [], "topics": []}
