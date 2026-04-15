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


# ---------------------------------------------------------------------------
# _tool_family fallback — pure unit, no DB
# ---------------------------------------------------------------------------

def test_tool_family_unknown_returns_other():
    from load import _tool_family
    assert _tool_family("SomeUnknownTool") == "other"
    assert _tool_family("") == "other"


def test_tool_family_known_mappings():
    from load import _tool_family
    assert _tool_family("Bash") == "execution"
    assert _tool_family("Read") == "file_ops"
    assert _tool_family("Grep") == "search"
    assert _tool_family("WebSearch") == "web"
    assert _tool_family("TaskCreate") == "planning"


# ---------------------------------------------------------------------------
# _parse_ts — empty input + unrecognized format fallback
# ---------------------------------------------------------------------------

def test_parse_ts_empty_and_none():
    from load import _parse_ts
    assert _parse_ts(None) is None
    assert _parse_ts("") is None


def test_parse_ts_unrecognized_format_returns_none():
    """Exhausts the format loop → returns None via final line."""
    from load import _parse_ts
    assert _parse_ts("not-a-real-ts") is None
    assert _parse_ts("2026/03/15 12:00:00") is None


def test_parse_ts_all_four_formats():
    """Exercise each format in the tuple so every continue path fires."""
    from load import _parse_ts
    assert _parse_ts("2026-03-15T12:00:00.123456Z") is not None
    assert _parse_ts("2026-03-15T12:00:00Z") is not None
    assert _parse_ts("2026-03-15T12:00:00.123456") is not None
    assert _parse_ts("2026-03-15T12:00:00") is not None


# ---------------------------------------------------------------------------
# _resolve_pricing — prefix fallback for unknown-but-family-like model names
# ---------------------------------------------------------------------------

def test_resolve_pricing_exact_match():
    from load import _resolve_pricing
    assert _resolve_pricing("claude-opus-4-6") == (15.00, 75.00)


def test_resolve_pricing_prefix_fallback():
    """Unknown exact key but shares prefix with a known model → gets that model's pricing.

    "claude-opus-4-6".rsplit("-", 1)[0] = "claude-opus-4" — any input that
    startswith("claude-opus-4") matches and inherits opus pricing.
    """
    from load import _resolve_pricing
    input_p, _ = _resolve_pricing("claude-opus-4-7-preview")
    assert input_p == 15.00


def test_resolve_pricing_complete_unknown_defaults_to_sonnet():
    """Non-matching model → final fallback (3.00, 15.00)."""
    from load import _resolve_pricing
    assert _resolve_pricing("completely-unknown-model") == (3.00, 15.00)
    # None falls back to "openai" which is in MODEL_PRICING (codex default).
    assert _resolve_pricing(None) == (2.50, 10.00)


# ---------------------------------------------------------------------------
# _group_segments_into_sessions — standalone-segment branch
# ---------------------------------------------------------------------------

_MARKDOWN_STANDALONE = """\
# project_standalone

---

>>>USER_REQUEST<<<
# User #1 \u2014 2026-03-17T10:00:00.000Z

orphan request without a conversation id

**Tool Call: `Bash`**
```json
{"command": "ls"}
```
"""


async def test_standalone_segment_becomes_own_session(tmp_path, db_engine, fake_embed):
    """A request missing `conv: \\`uuid\\`` ends up as its own session (one per segment)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from load import load_all

    md = tmp_path / "markdown"
    md.mkdir()
    (md / "project_standalone.md").write_text(_MARKDOWN_STANDALONE, encoding="utf-8")
    nonexistent = str(tmp_path / "nope")

    await load_all(str(md), nonexistent, nonexistent, nonexistent)

    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        rows = (await s.execute(select(Session).where(Session.project == "project_standalone"))).scalars().all()
    assert len(rows) == 1
    # Standalone session has NULL conversation_id
    assert rows[0].conversation_id is None
    assert rows[0].turn_count == 1


# ---------------------------------------------------------------------------
# _upsert_session summary_text truncation (line 307)
# ---------------------------------------------------------------------------

_MARKDOWN_LONG_PREVIEWS = """\
# project_long

---

## Conversation `conv-long` (started 2026-03-15T12:00:00.000Z)

""" + "\n".join(
    f">>>USER_REQUEST<<<\n# User #{i} \u2014 2026-03-15T12:{i:02d}:00.000Z \u2014 conv: `conv-long`\n\n" +
    ("very detailed content line spread out " * 20) + "\n"
    for i in range(1, 4)
)


async def test_summary_text_truncated_at_500_chars(tmp_path, db_engine, fake_embed, monkeypatch):
    """Three previews > 166 chars each → joined summary exceeds 500 → truncate fires.

    `extract_preview` normally caps preview at 120 chars, so the truncation branch
    is unreachable via natural markdown. We monkeypatch it to return a 200-char
    string so three joined previews total 606 chars and trigger line 307's slice.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import parser as parser_mod
    from load import load_all

    monkeypatch.setattr(parser_mod, "extract_preview", lambda *a, **k: "x" * 200)

    md = tmp_path / "markdown"
    md.mkdir()
    (md / "project_long.md").write_text(_MARKDOWN_LONG_PREVIEWS, encoding="utf-8")
    nonexistent = str(tmp_path / "nope")

    await load_all(str(md), nonexistent, nonexistent, nonexistent)

    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        row = (await s.execute(select(Session).where(Session.id == "conv-long"))).scalar_one()
    assert row.summary_text is not None
    # 200*3 + 6 " | " separators = 606 → sliced to 500 exactly.
    assert len(row.summary_text) == 500


# ---------------------------------------------------------------------------
# _embed_new_sessions — skip-empty-text + batch-commit branches
# ---------------------------------------------------------------------------

async def test_embed_skipped_when_session_text_is_empty(tmp_path, db_engine, monkeypatch):
    """`if not session_text.strip(): continue` fires when build_session_text returns empty."""
    import embed
    from load import _embed_new_sessions

    called_for: list[str] = []

    def fake_embed_text(text: str) -> list[float]:
        called_for.append(text)
        return [0.0] * embed.EMBEDDING_DIM

    # build_session_text returns empty string unconditionally → all sessions skipped.
    # Patch `embed.build_session_text` (not `load.build_session_text`) — load does
    # `from embed import build_session_text` inside the function, rebinding each call.
    monkeypatch.setattr(embed, "build_session_text", lambda *a, **k: "   ")
    monkeypatch.setattr(embed, "embed_text", fake_embed_text)

    # Seed one session with NULL embedding.
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        s.add(Session(
            id="s-empty-text",
            provider="claude",
            project="proj",
            model="claude-opus-4-6",
            conversation_id="c-empty",
            started_at=datetime(2026, 3, 15, tzinfo=UTC),
            ended_at=datetime(2026, 3, 15, tzinfo=UTC) + timedelta(hours=1),
            turn_count=1,
            total_chars=10,
            total_words=2,
            source_file="x.md",
        ))
        await s.commit()

    count = await _embed_new_sessions()
    assert count == 0
    assert called_for == []


async def test_embed_commits_every_100_sessions(tmp_path, db_engine, monkeypatch):
    """Fire the `if count % 100 == 0:` branch by seeding exactly 100 embeddable sessions."""
    import embed
    from load import _embed_new_sessions

    monkeypatch.setattr(embed, "embed_text", lambda text: [0.01] * embed.EMBEDDING_DIM)

    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import async_sessionmaker

    base = datetime(2026, 3, 15, tzinfo=UTC)
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as s:
        for i in range(100):
            s.add(Session(
                id=f"sb-{i:03d}",
                provider="claude",
                project="bulk",
                model="claude-opus-4-6",
                conversation_id=f"c-{i:03d}",
                started_at=base + timedelta(minutes=i),
                ended_at=base + timedelta(minutes=i + 1),
                turn_count=1,
                total_chars=100,
                total_words=20,
                summary_text=f"session {i}",
                source_file="x.md",
            ))
        await s.commit()

    count = await _embed_new_sessions()
    assert count == 100


# ---------------------------------------------------------------------------
# load_all — embedding + graphify failure branches (non-fatal)
# ---------------------------------------------------------------------------

async def test_load_all_embedding_failure_non_fatal(md_dir, tmp_path, db_engine, monkeypatch):
    """embed_text raising → outer try/except in load_all catches it (line 622-623)."""
    import embed

    def boom(text):
        raise RuntimeError("ONNX unavailable")
    monkeypatch.setattr(embed, "embed_text", boom)

    nonexistent = str(tmp_path / "does_not_exist")
    # Should not raise — exception is caught and logged non-fatally.
    results = await load_all(str(md_dir), nonexistent, nonexistent, nonexistent)
    assert results == {"claude": 2}


async def test_run_graphify_and_import_exception_branch(tmp_path, db_engine, monkeypatch):
    """Graphify import raising → outer try/except in _run_graphify_and_import catches (lines 644-649)."""
    from load import _run_graphify_and_import

    graphify_out = tmp_path / "graphify-out"
    graphify_out.mkdir()
    (graphify_out / "graph.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_OUT", str(graphify_out))

    async def broken_import(_path):
        raise RuntimeError("import exploded")

    import import_graph as ig
    monkeypatch.setattr(ig, "import_graph", broken_import)

    # Should not raise — exception is caught and logged non-fatally.
    await _run_graphify_and_import(str(tmp_path / "markdown"))


async def test_run_graphify_and_import_success_logs_import(tmp_path, db_engine, monkeypatch):
    """Graphify import succeeding → `_log('Graphify concept graph imported...')` runs (line 647)."""
    from load import _run_graphify_and_import

    graphify_out = tmp_path / "graphify-out"
    graphify_out.mkdir()
    (graphify_out / "graph.json").write_text('{"nodes": [], "links": []}', encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_OUT", str(graphify_out))

    called_with: list[str] = []

    async def fake_import(path):
        called_with.append(path)

    import import_graph as ig
    monkeypatch.setattr(ig, "import_graph", fake_import)

    await _run_graphify_and_import(str(tmp_path / "markdown"))
    assert called_with  # import was called → success log path fired


# ---------------------------------------------------------------------------
# Codex load branch (lines 606-610)
# ---------------------------------------------------------------------------

async def test_codex_markdown_dir_present_loads_codex_sessions(md_dir, tmp_path, db_engine, fake_embed):
    """Codex markdown dir exists → load_provider('codex', ...) runs, results['codex'] present."""
    codex_md = tmp_path / "markdown_codex"
    codex_md.mkdir()
    codex_file = codex_md / "codex_session.md"
    codex_file.write_text(
        "# codex_session\n\n---\n\n## Session `cx-1` (started 2026-03-18T10:00:00.000Z)\n\n"
        ">>>USER_REQUEST<<<\n# User #1 \u2014 2026-03-18T10:00:00.000Z \u2014 conv: `cx-1`\n\n"
        "first codex request\n",
        encoding="utf-8",
    )
    nonexistent = str(tmp_path / "raw_missing")

    results = await load_all(str(md_dir), str(codex_md), nonexistent, nonexistent)
    assert "codex" in results
    assert results["codex"] == 1


# ---------------------------------------------------------------------------
# main() CLI entry point (lines 654-677)
# ---------------------------------------------------------------------------

async def test_main_cli_runs_with_env_vars(md_dir, tmp_path, db_engine, fake_embed, monkeypatch):
    """Call main() directly with env vars pointing at tmp_path so the CLI entry is covered."""
    from load import main

    monkeypatch.setenv("MARKDOWN_DIR", str(md_dir))
    monkeypatch.setenv("CODEX_MARKDOWN_DIR", str(tmp_path / "nope_codex"))
    monkeypatch.setenv("RAW_DIR", str(tmp_path / "nope_raw"))
    monkeypatch.setenv("CODEX_SESSIONS_SRC", str(tmp_path / "nope_cs"))

    # Should complete without raising. `init_db()` is idempotent so re-running
    # inside the test's fixtured DB is safe.
    await main()
