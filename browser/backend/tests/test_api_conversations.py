"""Integration tests for /api/projects/{p}/conversation/{cid}."""
from __future__ import annotations


async def test_conversation_view_returns_combined_markdown(seed_sessions, api_client):
    response = await api_client.get("/api/projects/conversations/conversation/conv-1?provider=claude")
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == "conv-1"
    assert data["project_name"] == "conversations"
    assert data["segment_count"] == 2  # s1 has seg-1a + seg-1b
    assert "raw_markdown" in data
    assert "docker auth" in data["raw_markdown"]  # from seg-1a
    assert "registry" in data["raw_markdown"]    # from seg-1b
    metrics = data["metrics"]
    assert metrics["char_count"] > 0
    assert metrics["word_count"] > 0
    assert metrics["estimated_tokens"] > 0
    assert metrics["tool_call_count"] >= 0


async def test_conversation_view_404_for_unknown_conv(api_client):
    response = await api_client.get(
        "/api/projects/conversations/conversation/does-not-exist?provider=claude"
    )
    assert response.status_code == 404
    assert "error" in response.json()


async def test_conversation_view_404_when_project_mismatched(seed_sessions, api_client):
    """conv-1 exists under 'conversations', not under 'oft' — must 404."""
    response = await api_client.get("/api/projects/oft/conversation/conv-1?provider=claude")
    assert response.status_code == 404


async def test_conversation_view_provider_isolated(seed_sessions, api_client):
    """conv-1 is a claude conversation — querying with provider=codex must 404."""
    response = await api_client.get("/api/projects/conversations/conversation/conv-1?provider=codex")
    assert response.status_code == 404
