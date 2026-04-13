"""Import Graphify concept graph into Postgres.

Reads graphify-out/graph.json (node_link_data format produced by
graphify's to_json), maps concept nodes to sessions by matching
source_file paths to session source_file columns, and populates
the concepts and session_concepts tables.

Idempotent via ON CONFLICT DO UPDATE. Safe to re-run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db import async_session
from models import Concept, Session, SessionConcept, SessionTopic


def _normalize_source(source_file: str) -> str:
    """Extract a comparable filename stem from a source_file path.

    Graphify source_file: '/data/markdown/IMPORTANT-Projects-conversations.md'
    Session source_file:  'markdown/IMPORTANT-Projects-conversations.md'

    We normalize to just the basename without extension for matching.
    """
    return Path(source_file).stem if source_file else ""


async def import_graph(graph_path: str) -> None:
    """Read graph.json and populate concepts + session_concepts tables."""
    path = Path(graph_path)
    if not path.exists():
        return

    data = json.loads(path.read_text(encoding="utf-8"))

    nodes = data.get("nodes", [])
    # Graphify uses "links" key in node_link_data format
    links = data.get("links", data.get("edges", []))

    if not nodes:
        return

    async with async_session() as db:
        # Build a map of normalized source file stem -> list of session IDs
        sess_result = await db.execute(
            select(Session.id, Session.source_file)
            .where(Session.source_file.is_not(None))
        )
        source_to_sessions: dict[str, list[str]] = {}
        for row in sess_result.all():
            stem = _normalize_source(row.source_file)
            if stem:
                source_to_sessions.setdefault(stem, []).append(row.id)

        # Count edges per node to compute degree
        degree_map: dict[str, int] = {}
        for link in links:
            src = link.get("source", "")
            tgt = link.get("target", "")
            degree_map[src] = degree_map.get(src, 0) + 1
            degree_map[tgt] = degree_map.get(tgt, 0) + 1

        # Upsert concepts and track which concepts map to which sessions
        concept_sessions: dict[str, set[str]] = {}
        concept_names: dict[str, str] = {}
        any_source_matched = False

        for node in nodes:
            node_id = str(node.get("id", ""))
            if not node_id:
                continue

            name = node.get("label") or node.get("name", node_id)
            community_id = node.get("community") or node.get("community_id")
            degree = degree_map.get(node_id, 0)

            concept_values = {
                "id": node_id,
                "name": name,
                "type": node.get("file_type") or node.get("type"),
                "community_id": community_id,
                "degree": degree,
            }

            stmt = pg_insert(Concept).values(**concept_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={k: v for k, v in concept_values.items() if k != "id"},
            )
            await db.execute(stmt)

            concept_names[node_id] = name

            # Map concept to sessions via source_file
            source_file = node.get("source_file", "")
            if source_file:
                stem = _normalize_source(source_file)
                matching_sessions = source_to_sessions.get(stem, [])
                if matching_sessions:
                    concept_sessions[node_id] = set(matching_sessions)
                    any_source_matched = True

        # Fallback: if no source_file matched any session (e.g. source_file
        # paths differ between graph and DB), try matching by partial stem.
        # Markdown files: "IMPORTANT-Projects-conversations.md" in graph vs
        # "markdown/IMPORTANT-Projects-conversations.md" in session.
        if not any_source_matched and source_to_sessions:
            # Build reverse map: stem -> concept_ids
            stem_to_concepts: dict[str, list[str]] = {}
            for node in nodes:
                nid = str(node.get("id", ""))
                sf = node.get("source_file", "")
                if nid and sf:
                    stem = _normalize_source(sf)
                    stem_to_concepts.setdefault(stem, []).append(nid)

            # Try matching session stems against concept stems
            for stem, session_ids in source_to_sessions.items():
                for concept_stem, concept_ids in stem_to_concepts.items():
                    if stem == concept_stem or stem in concept_stem or concept_stem in stem:
                        for cid in concept_ids:
                            concept_sessions.setdefault(cid, set()).update(session_ids)

        # Upsert session_concepts
        for concept_id, session_ids in concept_sessions.items():
            for session_id in session_ids:
                sc_values = {
                    "session_id": session_id,
                    "concept_id": concept_id,
                    "relationship": "contains",
                    "edge_type": "extracted",
                    "confidence": 0.8,
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

        # Merge Graphify concepts into session_topics with higher confidence
        for concept_id, session_ids in concept_sessions.items():
            concept_name = concept_names.get(concept_id)
            if not concept_name:
                continue

            for session_id in session_ids:
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

        total_mappings = sum(len(sids) for sids in concept_sessions.values())
        print(f"  {len(concept_names)} concepts, {total_mappings} session-concept links, {len(links)} edges")
