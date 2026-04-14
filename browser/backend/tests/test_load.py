"""Loader integration tests against a real Postgres testcontainer.

Verifies load_all:
  * creates sessions / segments / tool_calls / session_topics from markdown
  * is idempotent — re-running produces no duplicate rows
  * populates Session.embedding once embed_text is mocked
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

import embed
from load import load_all
from models import Segment, Session, SessionTopic, ToolCall


# Two minimal markdown files in the format produced by convert_claude_jsonl_to_md.py.
# Em-dashes (—) and the >>>USER_REQUEST<<< sentinel are required for parser.py to
# split correctly. Tool calls are detected by the **Tool Call: `Name`** marker.
_MARKDOWN_A = """\
# project_a

---

## Conversation `conv-a` (started 2026-03-15T12:00:00.000Z)

>>>USER_REQUEST<<<
# User #1 \u2014 2026-03-15T12:00:00.000Z \u2014 conv: `conv-a`

how do I fix docker auth in the buildkit pipeline

**Tool Call: `Bash`**
```json
{"command": "docker login"}
```

>>>USER_REQUEST<<<
# User #2 \u2014 2026-03-15T12:30:00.000Z \u2014 conv: `conv-a`

follow up about the registry token

**Tool Call: `Edit`**
```json
{"file": "Dockerfile"}
```
"""

_MARKDOWN_B = """\
# project_b

---

## Conversation `conv-b` (started 2026-03-16T09:00:00.000Z)

>>>USER_REQUEST<<<
# User #1 \u2014 2026-03-16T09:00:00.000Z \u2014 conv: `conv-b`

refactor the search to use tsvector ranking

**Tool Call: `Read`**
```json
{"file": "search.py"}
```
"""


@pytest.fixture
def md_dir(tmp_path: Path) -> Path:
    md = tmp_path / "markdown"
    md.mkdir()
    (md / "project_a.md").write_text(_MARKDOWN_A, encoding="utf-8")
    (md / "project_b.md").write_text(_MARKDOWN_B, encoding="utf-8")
    return md


@pytest.fixture
def fake_embed(monkeypatch):
    """Replace embed_text with a deterministic 384-dim vector. Track calls."""
    calls: list[str] = []

    def _fake(text: str) -> list[float]:
        calls.append(text)
        return [0.01] * embed.EMBEDDING_DIM

    monkeypatch.setattr(embed, "embed_text", _fake)
    return calls


async def _row_counts(db_engine) -> dict[str, int]:
    """Snapshot row counts across the core tables."""
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        sessions = (await s.execute(select(func.count(Session.id)))).scalar_one()
        segments = (await s.execute(select(func.count(Segment.id)))).scalar_one()
        tool_calls = (await s.execute(select(func.count(ToolCall.id)))).scalar_one()
        topics = (await s.execute(select(func.count()).select_from(SessionTopic))).scalar_one()
        embedded = (await s.execute(
            select(func.count(Session.id)).where(Session.embedding.is_not(None))
        )).scalar_one()
    return {
        "sessions": sessions,
        "segments": segments,
        "tool_calls": tool_calls,
        "topics": topics,
        "embedded": embedded,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_load_all_creates_rows_from_markdown(md_dir, tmp_path, db_engine, fake_embed):
    nonexistent = str(tmp_path / "does_not_exist")

    results = await load_all(
        str(md_dir),
        nonexistent,        # codex markdown dir — absent → codex skipped
        nonexistent,        # raw_projects_dir — absent → no JSONL metadata
        nonexistent,        # codex sessions dir — absent
    )

    # Per-provider session counts in the return value
    assert results == {"claude": 2}

    counts = await _row_counts(db_engine)
    assert counts["sessions"] == 2
    assert counts["segments"] == 3       # 2 from project_a + 1 from project_b
    assert counts["tool_calls"] == 3     # 1 Bash + 1 Edit + 1 Read
    assert counts["topics"] > 0
    assert counts["embedded"] == 2       # both sessions got an embedding


async def test_load_all_is_idempotent_on_re_run(md_dir, tmp_path, db_engine, fake_embed):
    nonexistent = str(tmp_path / "does_not_exist")

    await load_all(str(md_dir), nonexistent, nonexistent, nonexistent)
    first = await _row_counts(db_engine)

    await load_all(str(md_dir), nonexistent, nonexistent, nonexistent)
    second = await _row_counts(db_engine)

    assert first["sessions"] == second["sessions"]
    assert first["segments"] == second["segments"]
    assert first["tool_calls"] == second["tool_calls"]
    assert first["topics"] == second["topics"]


async def test_embed_skipped_for_already_embedded_sessions(md_dir, tmp_path, db_engine, fake_embed):
    """Second pass must not re-embed: _embed_new_sessions filters embedding IS NULL."""
    nonexistent = str(tmp_path / "does_not_exist")

    await load_all(str(md_dir), nonexistent, nonexistent, nonexistent)
    first_embed_calls = len(fake_embed)

    # All sessions now have embeddings — second pass must call embed_text 0 times
    await load_all(str(md_dir), nonexistent, nonexistent, nonexistent)
    second_embed_calls = len(fake_embed) - first_embed_calls

    assert first_embed_calls == 2
    assert second_embed_calls == 0


async def test_session_fields_populated(md_dir, tmp_path, db_engine, fake_embed):
    nonexistent = str(tmp_path / "does_not_exist")
    await load_all(str(md_dir), nonexistent, nonexistent, nonexistent)

    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        result = await s.execute(select(Session).where(Session.id == "conv-a"))
        session_a = result.scalar_one()

    assert session_a.provider == "claude"
    assert session_a.project == "project_a"
    assert session_a.conversation_id == "conv-a"
    assert session_a.turn_count == 2
    assert session_a.session_type is not None
    assert session_a.embedding is not None


async def test_tool_calls_attached_to_correct_segments(md_dir, tmp_path, db_engine, fake_embed):
    nonexistent = str(tmp_path / "does_not_exist")
    await load_all(str(md_dir), nonexistent, nonexistent, nonexistent)

    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        # project_a session has both Bash and Edit
        result = await s.execute(
            select(ToolCall.tool_name, func.count(ToolCall.id))
            .where(ToolCall.session_id == "conv-a")
            .group_by(ToolCall.tool_name)
        )
        breakdown = {name: count for name, count in result.all()}

    assert breakdown == {"Bash": 1, "Edit": 1}


async def test_codex_markdown_dir_absent_skips_codex(md_dir, tmp_path, db_engine, fake_embed):
    """When codex markdown dir doesn't exist, results['codex'] is absent."""
    nonexistent = str(tmp_path / "does_not_exist")
    results = await load_all(str(md_dir), nonexistent, nonexistent, nonexistent)
    assert "codex" not in results
