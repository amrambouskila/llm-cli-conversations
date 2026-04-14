"""Integration tests for hide/restore endpoints — verifies hidden_at column writes."""
from __future__ import annotations

from sqlalchemy import text


async def _hidden_at(db_engine, table: str, where_sql: str, params: dict):
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(f"SELECT hidden_at FROM conversations.{table} WHERE {where_sql} LIMIT 1"),
            params,
        )
        row = result.first()
    return row.hidden_at if row else None


# ---------------------------------------------------------------------------
# Segment hide / restore
# ---------------------------------------------------------------------------

async def test_hide_segment_sets_hidden_at(seed_sessions, api_client, db_engine):
    response = await api_client.post("/api/hide/segment/seg-1a")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "hidden" in body
    assert await _hidden_at(db_engine, "segments", "id = :id", {"id": "seg-1a"}) is not None


async def test_restore_segment_clears_hidden_at(seed_sessions, api_client, db_engine):
    await api_client.post("/api/hide/segment/seg-1a")
    response = await api_client.post("/api/restore/segment/seg-1a")
    assert response.status_code == 200
    assert await _hidden_at(db_engine, "segments", "id = :id", {"id": "seg-1a"}) is None


# ---------------------------------------------------------------------------
# Conversation hide / restore
# ---------------------------------------------------------------------------

async def test_hide_conversation_sets_hidden_at_on_session(seed_sessions, api_client, db_engine):
    response = await api_client.post("/api/hide/conversation/conversations/conv-1")
    assert response.status_code == 200
    h = await _hidden_at(
        db_engine, "sessions",
        "project = :p AND conversation_id = :c",
        {"p": "conversations", "c": "conv-1"},
    )
    assert h is not None


async def test_restore_conversation_clears_hidden_at(seed_sessions, api_client, db_engine):
    await api_client.post("/api/hide/conversation/conversations/conv-1")
    response = await api_client.post("/api/restore/conversation/conversations/conv-1")
    assert response.status_code == 200
    h = await _hidden_at(
        db_engine, "sessions",
        "project = :p AND conversation_id = :c",
        {"p": "conversations", "c": "conv-1"},
    )
    assert h is None


# ---------------------------------------------------------------------------
# Project hide / restore
# ---------------------------------------------------------------------------

async def test_hide_project_marks_all_sessions(seed_sessions, api_client, db_engine):
    response = await api_client.post("/api/hide/project/conversations")
    assert response.status_code == 200
    async with db_engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT count(*) AS hidden FROM conversations.sessions "
            "WHERE project = 'conversations' AND hidden_at IS NOT NULL"
        ))
        assert result.scalar_one() == 2  # s1, s2


async def test_restore_project_clears_all_sessions(seed_sessions, api_client, db_engine):
    await api_client.post("/api/hide/project/conversations")
    response = await api_client.post("/api/restore/project/conversations")
    assert response.status_code == 200
    async with db_engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT count(*) AS hidden FROM conversations.sessions "
            "WHERE project = 'conversations' AND hidden_at IS NOT NULL"
        ))
        assert result.scalar_one() == 0


# ---------------------------------------------------------------------------
# Restore all
# ---------------------------------------------------------------------------

async def test_restore_all_clears_everything(seed_sessions, api_client, db_engine):
    # s5 starts hidden; also hide a segment for good measure
    await api_client.post("/api/hide/segment/seg-1a")
    response = await api_client.post("/api/restore/all")
    assert response.status_code == 200
    async with db_engine.connect() as conn:
        sess_hidden = await conn.execute(text(
            "SELECT count(*) FROM conversations.sessions WHERE hidden_at IS NOT NULL"
        ))
        seg_hidden = await conn.execute(text(
            "SELECT count(*) FROM conversations.segments WHERE hidden_at IS NOT NULL"
        ))
    assert sess_hidden.scalar_one() == 0
    assert seg_hidden.scalar_one() == 0


# ---------------------------------------------------------------------------
# /api/hidden — full hidden state
# ---------------------------------------------------------------------------

async def test_hidden_endpoint_returns_state(seed_sessions, api_client):
    """s5 in seed is pre-hidden — should appear in hidden_conversations."""
    response = await api_client.get("/api/hidden")
    assert response.status_code == 200
    data = response.json()
    assert "segments" in data
    assert "conversations" in data
    assert "projects" in data
    conv_keys = [c["key"] for c in data["conversations"]]
    assert "archive:conv-5" in conv_keys


async def test_hidden_endpoint_includes_hidden_segment(seed_sessions, api_client):
    await api_client.post("/api/hide/segment/seg-1a")
    response = await api_client.get("/api/hidden")
    data = response.json()
    seg_ids = [s["id"] for s in data["segments"]]
    assert "seg-1a" in seg_ids


async def test_fully_hidden_project_appears_as_hidden(seed_sessions, api_client):
    await api_client.post("/api/hide/project/conversations")
    response = await api_client.get("/api/hidden")
    data = response.json()
    proj_names = [p["name"] for p in data["projects"]]
    assert "conversations" in proj_names
