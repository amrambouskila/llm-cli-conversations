"""Tests for import_graph: reading graphify graph.json and populating Postgres."""
from __future__ import annotations

import json

from sqlalchemy import select

import import_graph
from import_graph import _normalize_source, import_graph as run_import_graph
from models import Concept, SessionConcept, SessionTopic


def test_normalize_source_strips_dir_and_ext():
    assert _normalize_source("markdown/conversations.md") == "conversations"
    assert _normalize_source("/data/markdown/IMPORTANT-conversations.md") == "IMPORTANT-conversations"
    assert _normalize_source("") == ""


async def test_import_graph_missing_file_is_noop(tmp_path, db_engine):
    # Should not raise even with no DB activity
    await run_import_graph(str(tmp_path / "nothing.json"))


async def test_import_graph_empty_nodes_is_noop(tmp_path, db_engine):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
    await run_import_graph(str(path))


async def test_import_graph_populates_concepts_and_links(tmp_path, seed_sessions, db_session, db_engine):
    graph = {
        "nodes": [
            {
                "id": "n1",
                "label": "Docker",
                "file_type": "technology",
                "community": 7,
                "source_file": "/data/markdown/conversations.md",
            },
            {
                "id": "n2",
                "name": "Kubernetes",
                "community_id": 3,
                "source_file": "/data/markdown/conversations.md",
            },
            {
                "id": "n3",
                "label": "Unmapped",
                "source_file": "/data/markdown/no-match.md",
            },
            {
                "id": "",  # skipped
                "label": "Empty",
            },
        ],
        "links": [
            {"source": "n1", "target": "n2"},
            {"source": "n1", "target": "n3"},
        ],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")

    await run_import_graph(str(path))

    # Concepts upserted (3 with non-empty id)
    res = await db_session.execute(select(Concept))
    concepts = {c.id: c for c in res.scalars().all()}
    assert set(concepts.keys()) == {"n1", "n2", "n3"}
    assert concepts["n1"].name == "Docker"
    assert concepts["n1"].community_id == 7
    assert concepts["n1"].degree == 2  # n1 appears in 2 links
    assert concepts["n2"].name == "Kubernetes"
    assert concepts["n2"].community_id == 3

    # session_concepts populated for nodes matching seed source_file "markdown/conversations.md"
    res = await db_session.execute(select(SessionConcept))
    scs = res.scalars().all()
    concept_ids = {sc.concept_id for sc in scs}
    assert "n1" in concept_ids
    assert "n2" in concept_ids
    # n3 has no matching session
    assert "n3" not in concept_ids

    # session_topics merged with graphify source
    res = await db_session.execute(
        select(SessionTopic).where(SessionTopic.source == "graphify")
    )
    topics = [t.topic for t in res.scalars().all()]
    assert "docker" in topics
    assert "kubernetes" in topics


async def test_import_graph_fallback_stem_match(tmp_path, seed_sessions, db_session, db_engine):
    """When source_file paths in graph don't directly match, the partial-stem fallback kicks in."""
    graph = {
        "nodes": [
            {
                "id": "nX",
                "label": "Auth",
                "source_file": "/tmp/conversations.md",  # stem matches "conversations"
            },
        ],
        "links": [],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")

    await run_import_graph(str(path))

    res = await db_session.execute(select(SessionConcept).where(SessionConcept.concept_id == "nX"))
    scs = res.scalars().all()
    # Fallback: first-path matched by direct-stem ("conversations" == "conversations")
    assert len(scs) >= 1


async def test_import_graph_edges_key_alternative(tmp_path, db_engine):
    """Graph with 'edges' key instead of 'links' should still compute degrees."""
    graph = {
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "edges": [{"source": "a", "target": "b"}],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    await run_import_graph(str(path))

    from db import async_session as ases
    async with ases() as s:
        res = await s.execute(select(Concept))
        concepts = {c.id: c for c in res.scalars().all()}
    assert concepts["a"].degree == 1
    assert concepts["b"].degree == 1


def test_module_has_async_session_export():
    # conftest re-points this reference; confirm the attribute exists.
    assert hasattr(import_graph, "async_session")
