"""Integration tests for /api/sessions/{id}/related — Graphify-backed discovery."""
from __future__ import annotations

import pytest_asyncio

from models import Concept, SessionConcept


@pytest_asyncio.fixture
async def seeded_concepts(seed_sessions, db_session):
    """Add concept graph data so /related returns ranked results."""
    concepts = [
        Concept(id="c-docker", name="docker", type="topic", community_id=1, degree=10),
        Concept(id="c-auth", name="auth", type="topic", community_id=1, degree=8),
        Concept(id="c-search", name="search", type="topic", community_id=2, degree=6),
    ]
    for c in concepts:
        db_session.add(c)
    await db_session.flush()

    edges = [
        SessionConcept(session_id="s1", concept_id="c-docker", relationship_label="contains",
                       edge_type="extracted", confidence=0.9),
        SessionConcept(session_id="s1", concept_id="c-auth", relationship_label="contains",
                       edge_type="extracted", confidence=0.8),
        SessionConcept(session_id="s2", concept_id="c-docker", relationship_label="contains",
                       edge_type="extracted", confidence=0.6),
        SessionConcept(session_id="s2", concept_id="c-search", relationship_label="contains",
                       edge_type="extracted", confidence=0.9),
        SessionConcept(session_id="s3", concept_id="c-docker", relationship_label="contains",
                       edge_type="extracted", confidence=0.5),
    ]
    for e in edges:
        db_session.add(e)
    await db_session.commit()


async def test_related_empty_when_no_concept_data(seed_sessions, api_client):
    response = await api_client.get("/api/sessions/s1/related")
    assert response.status_code == 200
    assert response.json() == []


async def test_related_returns_sessions_sharing_concepts(seeded_concepts, api_client):
    response = await api_client.get("/api/sessions/s1/related")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    ids = [r["session_id"] for r in data]
    # s2 and s3 both share concept c-docker with s1
    assert "s2" in ids
    assert "s3" in ids
    assert "s1" not in ids  # never include self


async def test_related_ranked_by_shared_concept_count(seeded_concepts, api_client):
    response = await api_client.get("/api/sessions/s1/related")
    data = response.json()
    # Sorted descending by shared_concepts
    counts = [r["shared_concepts"] for r in data]
    assert counts == sorted(counts, reverse=True)
    # s2 shares only c-docker → 1; s3 shares c-docker → 1
    # so each has shared_concepts == 1
    assert all(c >= 1 for c in counts)


async def test_related_returns_full_metadata(seeded_concepts, api_client):
    data = (await api_client.get("/api/sessions/s1/related")).json()
    assert data
    sample = data[0]
    for key in ("session_id", "project", "date", "model", "summary", "shared_concepts", "conversation_id"):
        assert key in sample


async def test_related_unknown_session_returns_empty(seed_sessions, api_client):
    """No concept data for the queried session → returns []."""
    response = await api_client.get("/api/sessions/nonexistent/related")
    assert response.status_code == 200
    assert response.json() == []
