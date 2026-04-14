"""Unit tests for ConceptRepository — community lookups + related-session queries."""
from __future__ import annotations

import pytest_asyncio

from models import Concept, SessionConcept
from repositories.concept_repository import ConceptRepository


@pytest_asyncio.fixture
async def concept_graph(seed_sessions, db_session):
    """Seed concepts + session_concepts so s1/s2 share community 1 and s3 is alone in community 2."""
    concepts = [
        Concept(id="c1", name="docker", community_id=1, degree=5),
        Concept(id="c2", name="auth", community_id=1, degree=3),
        Concept(id="c3", name="chart", community_id=2, degree=2),
    ]
    for c in concepts:
        db_session.add(c)
    await db_session.flush()

    edges = [
        SessionConcept(session_id="s1", concept_id="c1", relationship_label="contains",
                       edge_type="extracted", confidence=0.9),
        SessionConcept(session_id="s1", concept_id="c2", relationship_label="contains",
                       edge_type="extracted", confidence=0.8),
        SessionConcept(session_id="s2", concept_id="c1", relationship_label="contains",
                       edge_type="extracted", confidence=0.9),
        SessionConcept(session_id="s3", concept_id="c3", relationship_label="contains",
                       edge_type="extracted", confidence=0.9),
    ]
    for e in edges:
        db_session.add(e)
    await db_session.commit()


async def test_get_communities_by_session(concept_graph, db_session):
    repo = ConceptRepository(db_session)
    communities = await repo.get_communities_by_session(["s1", "s2", "s3"])
    assert communities["s1"] == {1}
    assert communities["s2"] == {1}
    assert communities["s3"] == {2}


async def test_get_communities_empty_input(seed_sessions, db_session):
    assert await ConceptRepository(db_session).get_communities_by_session([]) == {}


async def test_get_communities_no_concept_data(seed_sessions, db_session):
    """Without concept_graph fixture → empty dict."""
    repo = ConceptRepository(db_session)
    assert await repo.get_communities_by_session(["s1", "s2"]) == {}


async def test_count_concepts_with_community(concept_graph, db_session):
    assert await ConceptRepository(db_session).count_concepts_with_community() == 3


async def test_count_concepts_with_community_none_when_empty(seed_sessions, db_session):
    assert await ConceptRepository(db_session).count_concepts_with_community() == 0


async def test_count_concepts_for_session(concept_graph, db_session):
    repo = ConceptRepository(db_session)
    assert await repo.count_concepts_for_session("s1") == 2
    assert await repo.count_concepts_for_session("s3") == 1
    assert await repo.count_concepts_for_session("s5") == 0


async def test_find_related_sessions_orders_by_overlap(concept_graph, db_session):
    """s1 shares c1 with s2 → s2 is related (1 shared concept)."""
    repo = ConceptRepository(db_session)
    related = await repo.find_related_sessions("s1", limit=5)
    ids = [sid for sid, _ in related]
    assert "s2" in ids
    shared = dict(related)
    assert shared["s2"] == 1


async def test_find_related_sessions_none_when_no_concepts(seed_sessions, db_session):
    assert await ConceptRepository(db_session).find_related_sessions("s1") == []


async def test_get_visible_sessions_by_ids_filters_hidden(seed_sessions, db_session):
    repo = ConceptRepository(db_session)
    result = await repo.get_visible_sessions_by_ids(["s1", "s5"])
    # s5 is hidden in the fixture
    assert "s1" in result and "s5" not in result


async def test_get_visible_sessions_empty_ids(seed_sessions, db_session):
    assert await ConceptRepository(db_session).get_visible_sessions_by_ids([]) == {}
