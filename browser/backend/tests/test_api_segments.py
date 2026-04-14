"""Integration tests for segment list, segment detail, search, and search/status."""
from __future__ import annotations

from datetime import UTC

# ---------------------------------------------------------------------------
# /api/projects/{p}/segments
# ---------------------------------------------------------------------------

async def test_project_segments_returns_list(seed_sessions, api_client):
    response = await api_client.get("/api/projects/conversations/segments?provider=claude")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 4  # s1 has 2, s2 has 2
    for seg in data:
        assert "id" in seg
        assert "preview" in seg
        assert "metrics" in seg
        assert "conversation_id" in seg
        assert seg["project_name"] == "conversations"


async def test_project_segments_404_for_unknown_project(api_client):
    response = await api_client.get("/api/projects/does-not-exist/segments?provider=claude")
    assert response.status_code == 404
    assert "error" in response.json()


async def test_project_segments_excludes_hidden_by_default(seed_sessions, api_client, db_session):
    from datetime import datetime

    from sqlalchemy import update

    from models import Segment

    await db_session.execute(
        update(Segment).where(Segment.id == "seg-1a")
        .values(hidden_at=datetime(2026, 4, 1, tzinfo=UTC))
    )
    await db_session.commit()

    response = await api_client.get("/api/projects/conversations/segments?provider=claude")
    ids = [s["id"] for s in response.json()]
    assert "seg-1a" not in ids


# ---------------------------------------------------------------------------
# /api/segments/{id}
# ---------------------------------------------------------------------------

async def test_segment_detail_returns_full_data(seed_sessions, api_client):
    response = await api_client.get("/api/segments/seg-1a")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "seg-1a"
    assert "raw_markdown" in data
    assert "tool_breakdown" in data
    assert data["tool_breakdown"].get("Bash") == 2  # seed: 2 Bash on seg-1a


async def test_segment_detail_404_for_unknown_id(api_client):
    response = await api_client.get("/api/segments/does-not-exist")
    assert response.status_code == 404


async def test_segment_export_returns_filename_and_content(seed_sessions, api_client):
    response = await api_client.get("/api/segments/seg-1a/export")
    assert response.status_code == 200
    data = response.json()
    assert data["filename"].endswith(".md")
    assert "content" in data


async def test_segment_export_404_for_unknown_id(api_client):
    response = await api_client.get("/api/segments/does-not-exist/export")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/search basic
# ---------------------------------------------------------------------------

async def test_search_short_query_returns_empty(api_client):
    response = await api_client.get("/api/search?q=a")
    assert response.json() == []


async def test_search_empty_query_returns_empty(api_client):
    response = await api_client.get("/api/search?q=")
    assert response.json() == []


async def test_search_session_level_shape(seed_sessions, api_client):
    response = await api_client.get("/api/search", params={"q": "docker"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        result = data[0]
        for key in (
            "session_id", "project", "date", "model", "cost", "snippet",
            "tool_summary", "tools", "turn_count", "topics", "conversation_id", "rank",
        ):
            assert key in result


# ---------------------------------------------------------------------------
# /api/search filter prefixes — §13.1.10–13.1.18
#
# All multi-token queries are passed via params={} so httpx URL-encodes spaces
# correctly. Each filter test pairs the prefix with a free-text term so the
# request hits the text-path (RRF) branch — the filter-only branch crashes
# on `func.literal(1.0)` (Postgres has no literal() function). That latent
# bug is captured in test_search_filter_only_path_crashes_xfail below.
# ---------------------------------------------------------------------------

async def test_search_project_filter(seed_sessions, api_client):
    response = await api_client.get("/api/search", params={"q": "project:conversations docker"})
    assert response.status_code == 200
    data = response.json()
    for r in data:
        assert r["project"] == "conversations"


async def test_search_tool_filter(seed_sessions, api_client):
    response = await api_client.get("/api/search", params={"q": "tool:Bash docker"})
    assert response.status_code == 200
    data = response.json()
    for r in data:
        assert "Bash" in r["tools"]


async def test_search_tool_multi_value_filter(seed_sessions, api_client):
    response = await api_client.get("/api/search", params={"q": "tool:Bash,Edit docker"})
    assert response.status_code == 200
    data = response.json()
    for r in data:
        assert ("Bash" in r["tools"]) or ("Edit" in r["tools"])


async def test_search_date_range_filter(seed_sessions, api_client):
    """Phase 7.2 fix: filters pass `date` objects directly, not `.isoformat()` strings."""
    response = await api_client.get(
        "/api/search", params={"q": "after:2026-03-15 before:2026-04-30 docker"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for r in data:
        if r["date"]:
            assert r["date"] >= "2026-03-15"


async def test_search_cost_threshold(seed_sessions, api_client):
    response = await api_client.get("/api/search", params={"q": "cost:>1.00 docker"})
    assert response.status_code == 200
    data = response.json()
    for r in data:
        if r["cost"] is not None:
            assert r["cost"] > 1.00


async def test_search_turns_threshold(seed_sessions, api_client):
    response = await api_client.get("/api/search", params={"q": "turns:>10 docker"})
    assert response.status_code == 200
    data = response.json()
    for r in data:
        if r["turn_count"] is not None:
            assert r["turn_count"] > 10


async def test_search_combined_filters(seed_sessions, api_client):
    """Phase 7.2: all four filters (project, tool, date, free text) compose cleanly."""
    response = await api_client.get(
        "/api/search",
        params={"q": "project:conversations tool:Edit after:2026-01-01 refactor"},
    )
    assert response.status_code == 200
    data = response.json()
    for r in data:
        assert r["project"] == "conversations"
        assert "Edit" in r["tools"]
        if r["date"]:
            assert r["date"] >= "2026-01-01"


async def test_search_model_filter(seed_sessions, api_client):
    response = await api_client.get("/api/search", params={"q": "model:opus docker"})
    assert response.status_code == 200
    data = response.json()
    for r in data:
        assert "opus" in (r["model"] or "").lower()


async def test_search_topic_filter(seed_sessions, api_client):
    response = await api_client.get("/api/search", params={"q": "topic:docker fix"})
    assert response.status_code == 200
    data = response.json()
    for r in data:
        assert any("docker" in t.lower() for t in r["topics"])


async def test_search_malformed_filter_does_not_crash(seed_sessions, api_client):
    response = await api_client.get(
        "/api/search", params={"q": "after:not-a-date docker"}
    )
    assert response.status_code == 200


async def test_search_special_chars_safe(seed_sessions, api_client):
    """C++, $PATH, <script>alert(1)</script> must not crash or reflect XSS."""
    for q in ("C++", "$PATH", "<script>alert(1)</script>"):
        response = await api_client.get("/api/search", params={"q": q})
        assert response.status_code == 200
        body = response.text
        assert "<script>alert(1)</script>" not in body


async def test_search_provider_filter(seed_sessions, api_client):
    response = await api_client.get("/api/search", params={"q": "chart", "provider": "codex"})
    assert response.status_code == 200
    data = response.json()
    if data:
        for r in data:
            assert r["project"] == "oft"


async def test_search_filter_only_path(seed_sessions, api_client):
    """Phase 7.2 fix: filter-only queries (no free text) return sessions by recency.

    Master plan §13.4.3 expects `project:conversations` alone to return results.
    Previously crashed with UndefinedFunctionError because the path used
    `func.literal(1.0)` which translates to a nonexistent Postgres `literal()`.
    """
    response = await api_client.get(
        "/api/search", params={"q": "project:conversations"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for r in data:
        assert r["project"] == "conversations"


# ---------------------------------------------------------------------------
# /api/search/status
# ---------------------------------------------------------------------------

async def test_search_status_empty_db(api_client):
    response = await api_client.get("/api/search/status?provider=claude")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "unavailable"
    assert data["total_sessions"] == 0
    assert data["embedded_sessions"] == 0
    assert data["has_graph"] is False
    assert data["concept_count"] == 0


async def test_search_status_keyword_mode(seed_sessions, api_client):
    """All seeded sessions have NULL embeddings — mode should be 'keyword'."""
    response = await api_client.get("/api/search/status?provider=claude")
    data = response.json()
    assert data["mode"] == "keyword"
    assert data["embedded_sessions"] == 0


async def test_search_status_hybrid_mode(seed_sessions, api_client, db_session):
    """When all visible sessions have embeddings, mode is 'hybrid'."""
    from sqlalchemy import update

    from models import Session
    fake_vec = [0.01] * 384
    await db_session.execute(
        update(Session).where(Session.provider == "claude", Session.hidden_at.is_(None))
        .values(embedding=fake_vec)
    )
    await db_session.commit()

    response = await api_client.get("/api/search/status?provider=claude")
    data = response.json()
    assert data["mode"] == "hybrid"
    assert data["embedded_sessions"] == data["total_sessions"]


async def test_search_status_partial_embedding_mode(seed_sessions, api_client, db_session):
    """When only some sessions are embedded, mode is 'embedding'."""
    from sqlalchemy import update

    from models import Session
    await db_session.execute(
        update(Session).where(Session.id == "s1").values(embedding=[0.01] * 384)
    )
    await db_session.commit()

    response = await api_client.get("/api/search/status?provider=claude")
    data = response.json()
    assert data["mode"] == "embedding"
    assert 0 < data["embedded_sessions"] < data["total_sessions"]
