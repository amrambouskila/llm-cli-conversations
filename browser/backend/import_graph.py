"""Import Graphify concept graph into Postgres.

Reads graphify-out/graph.json (produced by running Graphify externally
against markdown/), maps nodes to sessions by source file path, and
populates the concepts and session_concepts tables.

Idempotent via ON CONFLICT DO UPDATE. Safe to re-run after Graphify
re-indexes.

This module is NOT a dependency — it only runs when graph.json exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db import async_session
from models import Concept, SessionConcept, SessionTopic


async def import_graph(graph_path: str) -> None:
    """Read graph.json and populate concepts + session_concepts tables."""
    path = Path(graph_path)
    if not path.exists():
        return

    data = json.loads(path.read_text(encoding="utf-8"))

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if not nodes:
        return

    async with async_session() as db:
        # Upsert concepts
        for node in nodes:
            node_id = str(node.get("id", ""))
            if not node_id:
                continue

            concept_values = {
                "id": node_id,
                "name": node.get("name", node_id),
                "type": node.get("type"),
                "community_id": node.get("community_id"),
                "degree": node.get("degree"),
            }

            stmt = pg_insert(Concept).values(**concept_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={k: v for k, v in concept_values.items() if k != "id"},
            )
            await db.execute(stmt)

        # Build a lookup of concept_id -> concept name for topic merging
        concept_names: dict[str, str] = {
            str(n.get("id", "")): n.get("name", "") for n in nodes
        }

        # Upsert session_concepts from edges
        # Each edge connects a source file (session) to a concept
        sessions_with_concepts: set[tuple[str, str]] = set()

        for edge in edges:
            session_id = edge.get("session_id") or edge.get("source")
            concept_id = str(edge.get("concept_id") or edge.get("target", ""))
            relationship = edge.get("relationship") or edge.get("label", "related")

            if not session_id or not concept_id:
                continue

            sc_values = {
                "session_id": session_id,
                "concept_id": concept_id,
                "relationship": relationship,
                "edge_type": edge.get("edge_type", "extracted"),
                "confidence": edge.get("confidence"),
            }

            stmt = pg_insert(SessionConcept).values(**sc_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["session_id", "concept_id", "relationship"],
                set_={
                    "edge_type": sc_values["edge_type"],
                    "confidence": sc_values["confidence"],
                },
            )
            await db.execute(stmt)

            sessions_with_concepts.add((session_id, concept_id))

        # Merge Graphify concepts into session_topics with higher confidence
        for session_id, concept_id in sessions_with_concepts:
            concept_name = concept_names.get(concept_id)
            if not concept_name:
                continue

            topic_values = {
                "session_id": session_id,
                "topic": concept_name.lower(),
                "confidence": 0.9,
                "source": "graphify",
            }

            stmt = pg_insert(SessionTopic).values(**topic_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["session_id", "topic"],
                set_={"confidence": 0.9, "source": "graphify"},
            )
            await db.execute(stmt)

        await db.commit()
