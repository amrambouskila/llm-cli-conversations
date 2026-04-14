"""Integration tests for /api/stats — including the watch_interval removal check."""
from __future__ import annotations


async def test_stats_returns_expected_shape(seed_sessions, api_client):
    response = await api_client.get("/api/stats?provider=claude")
    assert response.status_code == 200
    data = response.json()
    for key in (
        "total_projects", "total_segments", "total_chars",
        "total_words", "total_tool_calls", "estimated_tokens",
        "monthly", "hidden",
    ):
        assert key in data
    assert "segments" in data["hidden"]
    assert "conversations" in data["hidden"]
    assert "projects" in data["hidden"]


async def test_stats_does_not_include_watch_interval(seed_sessions, api_client):
    """watch_interval was removed in Phase 6.1 — must not regress."""
    response = await api_client.get("/api/stats?provider=claude")
    assert "watch_interval" not in response.json()


async def test_stats_counts_match_seed(seed_sessions, api_client):
    response = await api_client.get("/api/stats?provider=claude")
    data = response.json()
    # claude visible: s1, s2 (conversations) + s3 (oft); s5 hidden
    # Visible projects: conversations, oft = 2
    assert data["total_projects"] == 2
    # Visible segments across s1+s2+s3 = 5
    assert data["total_segments"] == 5
    # Tool calls visible (all are not hidden_at on session level for s1/s2/s3): 7 total
    # s1: 3, s2: 3, s3: 1 = 7
    assert data["total_tool_calls"] == 7


async def test_stats_empty_db(api_client):
    response = await api_client.get("/api/stats?provider=claude")
    assert response.status_code == 200
    data = response.json()
    assert data["total_segments"] == 0
    assert data["total_projects"] == 0
    assert data["monthly"] == {}


async def test_stats_codex(seed_sessions, api_client):
    response = await api_client.get("/api/stats?provider=codex")
    data = response.json()
    assert data["total_projects"] == 1  # oft
    assert data["total_segments"] == 1  # seg-4a
