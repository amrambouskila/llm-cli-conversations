"""Integration tests for /api/providers and /api/projects."""
from __future__ import annotations


async def test_providers_returns_list_with_claude_always(api_client):
    """Empty DB still returns claude with zeros."""
    response = await api_client.get("/api/providers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(p["id"] == "claude" for p in data)


async def test_providers_lists_seeded_providers(seed_sessions, api_client):
    response = await api_client.get("/api/providers")
    data = response.json()
    by_id = {p["id"]: p for p in data}
    assert "claude" in by_id
    assert "codex" in by_id
    # claude has 3 visible projects (conversations, oft, archive-hidden — counted by handler)
    assert by_id["claude"]["projects"] >= 2
    assert by_id["claude"]["segments"] >= 5


async def test_projects_default_excludes_hidden(seed_sessions, api_client):
    response = await api_client.get("/api/projects?provider=claude")
    assert response.status_code == 200
    data = response.json()
    names = [p["name"] for p in data]
    assert "conversations" in names
    assert "oft" in names
    # archive is fully hidden — should be absent by default
    assert "archive" not in names


async def test_projects_show_hidden_includes_archive(seed_sessions, api_client):
    response = await api_client.get("/api/projects?provider=claude&show_hidden=true")
    data = response.json()
    names = [p["name"] for p in data]
    assert "archive" in names


async def test_projects_codex(seed_sessions, api_client):
    response = await api_client.get("/api/projects?provider=codex")
    data = response.json()
    names = [p["name"] for p in data]
    assert names == ["oft"]


async def test_projects_stats_shape(seed_sessions, api_client):
    response = await api_client.get("/api/projects?provider=claude")
    data = response.json()
    convo_proj = next(p for p in data if p["name"] == "conversations")
    assert "display_name" in convo_proj
    assert "total_requests" in convo_proj
    assert "total_files" in convo_proj
    assert "stats" in convo_proj
    stats = convo_proj["stats"]
    for key in (
        "total_conversations", "total_words", "total_chars",
        "estimated_tokens", "total_tool_calls",
        "first_timestamp", "last_timestamp",
        "request_sizes", "conversation_timeline", "tool_breakdown",
    ):
        assert key in stats
    # conversations project has 4 segments + 5 tool calls in seed data
    assert convo_proj["total_requests"] == 4
    assert stats["total_tool_calls"] == 6  # 3 in s1 + 3 in s2


async def test_projects_empty_db_returns_empty_list(api_client):
    response = await api_client.get("/api/projects?provider=claude")
    assert response.status_code == 200
    assert response.json() == []
