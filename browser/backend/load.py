"""Data loader: populate Postgres from parsed markdown + raw JSONL metadata.

Reads both data sources:
1. parser.py for markdown content (segments, text, tool calls)
2. jsonl_reader.py for metadata (model, token usage)

Merges by conversation_id/sessionId, then inserts into Postgres.
Idempotent via ON CONFLICT DO UPDATE.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlalchemy import select, text, update


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db import async_session, engine
from jsonl_reader import (
    SessionMetadata,
    read_claude_metadata,
    read_codex_metadata,
)
from models import (
    Concept,
    Segment,
    Session,
    SessionConcept,
    SessionTopic,
    ToolCall,
)
from parser import build_index, compute_tool_breakdown
from classify import classify_session
from topics import extract_topics

# USD per 1M tokens (input, output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
    # Older model names
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    # Codex fallback
    "openai": (2.50, 10.00),
}

# Cache read tokens use 10% of input price
CACHE_READ_DISCOUNT = 0.1

TOOL_FAMILIES: dict[str, list[str]] = {
    "file_ops": ["Read", "Edit", "Write", "Glob", "NotebookEdit"],
    "search": ["Grep", "Agent"],
    "execution": ["Bash"],
    "web": ["WebSearch", "WebFetch"],
    "planning": ["TaskCreate", "TaskUpdate", "TodoWrite"],
}


def _tool_family(tool_name: str) -> str:
    for family, tools in TOOL_FAMILIES.items():
        if tool_name in tools:
            return family
    return "other"


def _estimate_cost(
    meta: Optional[SessionMetadata],
    model: Optional[str],
    char_count: int,
) -> Decimal:
    """Compute estimated cost in USD."""
    if meta and (meta.input_tokens > 0 or meta.output_tokens > 0):
        pricing_key = meta.model or model or "openai"
        # Try exact match, then prefix match
        input_price, output_price = MODEL_PRICING.get(pricing_key, (0, 0))
        if input_price == 0:
            for key, prices in MODEL_PRICING.items():
                if pricing_key.startswith(key.rsplit("-", 1)[0]):
                    input_price, output_price = prices
                    break
            else:
                input_price, output_price = (3.00, 15.00)

        cost = (
            meta.input_tokens * input_price / 1_000_000
            + meta.output_tokens * output_price / 1_000_000
            + meta.cache_read_tokens * input_price * CACHE_READ_DISCOUNT / 1_000_000
            + meta.cache_creation_tokens * input_price / 1_000_000
        )
        return Decimal(str(round(cost, 4)))

    # Fallback: estimate from char count
    est_tokens = char_count // 4
    return Decimal(str(round(est_tokens * 3.00 / 1_000_000, 4)))


def _parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string to timezone-aware datetime."""
    if not ts_str:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(ts_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _group_segments_into_sessions(
    index: dict,
    provider: str,
) -> dict[str, dict]:
    """Group parsed segments into sessions by conversation_id.

    Returns dict keyed by session_id with session data + segment list.
    """
    sessions: dict[str, dict] = {}

    for project in index["projects"]:
        project_name = project["name"]

        # Group segments by conversation_id
        conv_groups: dict[Optional[str], list[dict]] = defaultdict(list)
        for seg_summary in project["segments"]:
            seg_data = index["segments"][seg_summary["id"]]
            conv_groups[seg_data.get("conversation_id")].append(seg_data)

        for conv_id, segs in conv_groups.items():
            if conv_id:
                session_id = conv_id
            else:
                # Standalone segments each become their own session
                for seg in segs:
                    sid = seg["id"]
                    ts = _parse_ts(seg.get("timestamp"))
                    tool_bd = compute_tool_breakdown(seg.get("raw_markdown", ""))
                    sessions[sid] = {
                        "id": sid,
                        "provider": provider,
                        "project": project_name,
                        "conversation_id": None,
                        "started_at": ts,
                        "ended_at": ts,
                        "turn_count": 1,
                        "total_chars": seg["metrics"]["char_count"],
                        "total_words": seg["metrics"]["word_count"],
                        "source_file": seg.get("source_file"),
                        "segments": [seg],
                        "tool_counts": tool_bd,
                    }
                continue

            # Multi-segment session
            timestamps = [_parse_ts(s.get("timestamp")) for s in segs]
            timestamps = [t for t in timestamps if t is not None]
            timestamps.sort()

            total_chars = sum(s["metrics"]["char_count"] for s in segs)
            total_words = sum(s["metrics"]["word_count"] for s in segs)

            agg_tools: dict[str, int] = {}
            for seg in segs:
                for tool, cnt in compute_tool_breakdown(seg.get("raw_markdown", "")).items():
                    agg_tools[tool] = agg_tools.get(tool, 0) + cnt

            sessions[session_id] = {
                "id": session_id,
                "provider": provider,
                "project": project_name,
                "conversation_id": conv_id,
                "started_at": timestamps[0] if timestamps else None,
                "ended_at": timestamps[-1] if timestamps else None,
                "turn_count": len(segs),
                "total_chars": total_chars,
                "total_words": total_words,
                "source_file": segs[0].get("source_file") if segs else None,
                "segments": segs,
                "tool_counts": agg_tools,
            }

    return sessions


async def _upsert_session(db: AsyncSession, session_data: dict, meta: Optional[SessionMetadata]) -> None:
    """Insert or update a single session and its segments/tool_calls/topics."""
    model = meta.model if meta else None
    model_provider = meta.model_provider if meta else None

    # Build summary text from first user segment
    summary_text = None
    user_text_parts = []
    for seg in session_data["segments"]:
        preview = seg.get("preview", "")
        if preview and preview != "(empty request)":
            user_text_parts.append(preview)
    if user_text_parts:
        summary_text = " | ".join(user_text_parts[:3])
        if len(summary_text) > 500:
            summary_text = summary_text[:500]

    # Extract topics
    all_user_text = " ".join(
        seg.get("raw_markdown", "") for seg in session_data["segments"]
    )
    tool_names = list(session_data.get("tool_counts", {}).keys())
    topic_list = extract_topics(
        session_data["project"],
        all_user_text,
        tool_names,
    )

    # Classify session type
    session_type = classify_session(
        summary_text or "",
        session_data.get("tool_counts", {}),
        [t[0] for t in topic_list],
        session_data.get("total_words", 0),
        session_data.get("turn_count", 0),
    )

    estimated_cost = _estimate_cost(
        meta,
        model or model_provider,
        session_data.get("total_chars", 0),
    )

    # Upsert session
    session_values = {
        "id": session_data["id"],
        "provider": session_data["provider"],
        "project": session_data["project"],
        "model": model,
        "conversation_id": session_data.get("conversation_id"),
        "started_at": session_data.get("started_at"),
        "ended_at": session_data.get("ended_at"),
        "turn_count": session_data.get("turn_count"),
        "input_tokens": meta.input_tokens if meta else None,
        "output_tokens": meta.output_tokens if meta else None,
        "cache_read_tokens": meta.cache_read_tokens if meta else None,
        "cache_creation_tokens": meta.cache_creation_tokens if meta else None,
        "total_chars": session_data.get("total_chars"),
        "total_words": session_data.get("total_words"),
        "estimated_cost": estimated_cost,
        "source_file": session_data.get("source_file"),
        "summary_text": summary_text,
        "session_type": session_type,
    }

    stmt = pg_insert(Session).values(**session_values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={k: v for k, v in session_values.items() if k != "id"},
    )
    await db.execute(stmt)

    # Upsert segments
    for seg in session_data["segments"]:
        seg_ts = _parse_ts(seg.get("timestamp"))
        seg_values = {
            "id": seg["id"],
            "session_id": session_data["id"],
            "segment_index": seg.get("segment_index"),
            "role": "user",
            "timestamp": seg_ts,
            "char_count": seg["metrics"]["char_count"],
            "word_count": seg["metrics"]["word_count"],
            "raw_text": seg.get("raw_markdown"),
            "preview": seg.get("preview"),
        }

        seg_stmt = pg_insert(Segment).values(**seg_values)
        seg_stmt = seg_stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={k: v for k, v in seg_values.items() if k != "id"},
        )
        await db.execute(seg_stmt)

        # Tool calls for this segment
        tool_bd = compute_tool_breakdown(seg.get("raw_markdown", ""))
        for tool_name, count in tool_bd.items():
            for _ in range(count):
                # Tool calls don't have a natural unique key, so we delete
                # and re-insert per session to stay idempotent
                pass

    # Delete existing tool calls for this session and re-insert
    await db.execute(
        text("DELETE FROM conversations.tool_calls WHERE session_id = :sid"),
        {"sid": session_data["id"]},
    )
    for seg in session_data["segments"]:
        tool_bd = compute_tool_breakdown(seg.get("raw_markdown", ""))
        for tool_name, count in tool_bd.items():
            for _ in range(count):
                tc_values = {
                    "session_id": session_data["id"],
                    "segment_id": seg["id"],
                    "tool_name": tool_name,
                    "tool_family": _tool_family(tool_name),
                    "timestamp": _parse_ts(seg.get("timestamp")),
                }
                await db.execute(pg_insert(ToolCall).values(**tc_values))

    # Upsert topics
    for topic, confidence in topic_list:
        topic_values = {
            "session_id": session_data["id"],
            "topic": topic,
            "confidence": confidence,
            "source": "heuristic",
        }
        topic_stmt = pg_insert(SessionTopic).values(**topic_values)
        topic_stmt = topic_stmt.on_conflict_do_update(
            index_elements=["session_id", "topic"],
            set_={"confidence": confidence, "source": "heuristic"},
        )
        await db.execute(topic_stmt)


async def load_provider(
    provider: str,
    markdown_dir: str,
    jsonl_metadata: dict[str, SessionMetadata],
) -> int:
    """Load all sessions for a provider into Postgres.

    Returns the number of sessions loaded.
    """
    index = build_index(markdown_dir)
    sessions = _group_segments_into_sessions(index, provider)

    async with async_session() as db:
        for session_id, session_data in sessions.items():
            meta = jsonl_metadata.get(session_id)
            await _upsert_session(db, session_data, meta)
        await db.commit()

    return len(sessions)


async def _embed_new_sessions() -> int:
    """Generate embeddings for sessions that don't have them yet.

    Queries Postgres for sessions with NULL embedding, builds compressed
    session text per DESIGN.md section 3, embeds via all-MiniLM-L6-v2 ONNX,
    and stores the 384-dim vectors back into the sessions table.
    """
    from embed import build_session_text, embed_text

    async with async_session() as db:
        # Find sessions without embeddings
        result = await db.execute(
            select(
                Session.id,
                Session.project,
                Session.model,
                Session.summary_text,
            ).where(Session.embedding.is_(None))
        )
        rows = result.all()

        if not rows:
            return 0

        session_ids = [r[0] for r in rows]

        # Batch fetch topics for all unembedded sessions
        topics_result = await db.execute(
            select(SessionTopic.session_id, SessionTopic.topic).where(
                SessionTopic.session_id.in_(session_ids)
            )
        )
        topics_by_session: dict[str, list[str]] = defaultdict(list)
        for sid, topic in topics_result.all():
            topics_by_session[sid].append(topic)

        # Batch fetch distinct tool names per session
        tools_result = await db.execute(
            select(ToolCall.session_id, ToolCall.tool_name)
            .where(ToolCall.session_id.in_(session_ids))
            .distinct()
        )
        tools_by_session: dict[str, list[str]] = defaultdict(list)
        for sid, tool_name in tools_result.all():
            tools_by_session[sid].append(tool_name)

        count = 0
        for sid, project, model, summary_text in rows:
            session_text = build_session_text(
                project,
                model,
                summary_text,
                topics_by_session.get(sid, []),
                tools_by_session.get(sid, []),
            )
            if not session_text.strip():
                continue

            vector = embed_text(session_text)
            await db.execute(
                update(Session)
                .where(Session.id == sid)
                .values(embedding=vector)
            )
            count += 1

            if count % 100 == 0:
                _log(f"  Embedded {count}/{len(rows)} sessions...")
                await db.commit()

        await db.commit()

    return count


async def load_all(
    claude_markdown_dir: str,
    codex_markdown_dir: str,
    raw_projects_dir: str,
    codex_sessions_dir: str,
) -> dict[str, int]:
    """Load all providers into Postgres.

    Returns dict with counts per provider.
    """
    results = {}

    # Claude
    claude_meta = read_claude_metadata(raw_projects_dir)
    _log(f"Read JSONL metadata for {len(claude_meta)} Claude sessions")
    count = await load_provider("claude", claude_markdown_dir, claude_meta)
    results["claude"] = count
    _log(f"Loaded {count} Claude sessions into Postgres")

    # Codex
    if Path(codex_markdown_dir).exists():
        codex_meta = read_codex_metadata(codex_sessions_dir)
        _log(f"Read JSONL metadata for {len(codex_meta)} Codex sessions")
        count = await load_provider("codex", codex_markdown_dir, codex_meta)
        results["codex"] = count
        _log(f"Loaded {count} Codex sessions into Postgres")

    # Run Graphify and import concept graph
    await _run_graphify_and_import(claude_markdown_dir)

    # Generate embeddings for sessions that don't have them yet.
    # Non-fatal: if model download fails or ONNX errors out, the app
    # still works with keyword-only search. Incremental on next run.
    try:
        embedded = await _embed_new_sessions()
        if embedded > 0:
            _log(f"Generated embeddings for {embedded} sessions")
    except Exception as e:
        _log(f"Embedding generation failed (non-fatal): {e}")

    return results


async def _run_graphify_and_import(markdown_dir: str) -> None:
    """Import a pre-generated Graphify concept graph into Postgres.

    Graphify's semantic extraction requires LLM API access and is too
    expensive to run automatically on every data load. Instead, the user
    generates graphify-out/graph.json externally (via the graphify CLI)
    and this function imports it on startup.

    If no graph.json exists, this is silently skipped.
    """
    graphify_out = Path(os.environ.get("GRAPHIFY_OUT", "/data/graphify-out"))
    graph_path = graphify_out / "graph.json"

    if not graph_path.exists():
        return

    try:
        from import_graph import import_graph
        await import_graph(str(graph_path))
        _log("Graphify concept graph imported into Postgres")
    except Exception as e:
        _log(f"Graphify import failed (non-fatal): {e}")


async def main() -> None:
    """CLI entry point for standalone loading."""
    from db import init_db

    script_dir = Path(__file__).resolve().parent
    claude_md = os.environ.get(
        "MARKDOWN_DIR",
        str(script_dir.parent.parent / "markdown"),
    )
    codex_md = os.environ.get(
        "CODEX_MARKDOWN_DIR",
        str(Path(claude_md).parent / "markdown_codex"),
    )
    raw_dir = os.environ.get(
        "RAW_DIR",
        str(script_dir.parent.parent / "raw"),
    )
    raw_projects = str(Path(raw_dir) / "projects")
    codex_sessions = os.environ.get(
        "CODEX_SESSIONS_SRC",
        str(Path.home() / ".codex" / "sessions"),
    )

    await init_db()
    results = await load_all(claude_md, codex_md, raw_projects, codex_sessions)
    _log(f"Load complete: {results}")


if __name__ == "__main__":
    asyncio.run(main())
