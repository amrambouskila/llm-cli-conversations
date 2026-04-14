"""Pytest configuration and shared fixtures.

Run inside Docker (host has no Python toolchain):

    docker run --rm \\
        -v "$(pwd)/browser/backend:/app" \\
        -v /var/run/docker.sock:/var/run/docker.sock \\
        -w /app \\
        python:3.13-slim \\
        bash -c "apt-get update -qq && apt-get install -y -qq --no-install-recommends libgomp1 gcc && \\
                 pip install -q -r requirements.txt -r requirements-dev.txt && pytest -v"

The host docker socket is required so testcontainers can spin up a real
Postgres (pgvector/pgvector:pg16) for integration tests. DATABASE_URL is set
inside the db_engine fixture (lazy) — pure unit tests that never request
db_engine pay zero container cost.
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

# These must be set BEFORE testcontainers is imported anywhere.
# Ryuk (the auto-cleanup sidecar) tries to connect back to itself over a host
# port, which fails when the test runner is itself a sibling container started
# via the host docker socket. We disable it and rely on fixture teardown.
# HOST_OVERRIDE makes get_container_host_ip() return host.docker.internal so
# the test container reaches sibling containers via Docker Desktop's bridge.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
os.environ.setdefault("TESTCONTAINERS_HOST_OVERRIDE", "host.docker.internal")

import pytest
import pytest_asyncio

# Make backend modules importable regardless of pytest cwd.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="session")
def _pg_container() -> Iterator:
    """Boot Postgres testcontainer for the test session.

    NullPool means every checkout opens a fresh asyncpg connection. Across the
    full test suite that's ~thousands of connections — PG's default max of 100
    saturates. Bump max_connections so the suite can run end-to-end.
    """
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="conversations",
        password="conversations",
        dbname="conversations",
        driver="asyncpg",
    )
    container.with_command("postgres -c max_connections=500")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def db_engine(_pg_container):
    """Patch db.engine + db.async_session to use a NullPool engine bound to the testcontainer.

    NullPool gives every checkout a fresh asyncpg connection in the caller's event loop —
    eliminating cross-loop reuse errors when each test runs in its own loop.
    """
    db_url = _pg_container.get_connection_url()
    os.environ["DATABASE_URL"] = db_url

    import db
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    new_engine = create_async_engine(db_url, poolclass=NullPool)
    new_session = async_sessionmaker(new_engine, expire_on_commit=False)

    db.DATABASE_URL = db_url
    db.engine = new_engine
    db.async_session = new_session

    # Replace stale references in modules that imported async_session/engine by name.
    for mod_name in ("load", "import_graph"):
        try:
            mod = __import__(mod_name)
        except ImportError:
            continue
        if hasattr(mod, "async_session"):
            mod.async_session = new_session
        if hasattr(mod, "engine"):
            mod.engine = new_engine

    asyncio.run(db.init_db())
    return new_engine


_TRUNCATE_SQL = (
    "TRUNCATE "
    "conversations.session_concepts, "
    "conversations.concepts, "
    "conversations.session_topics, "
    "conversations.tool_calls, "
    "conversations.segments, "
    "conversations.sessions, "
    "conversations.saved_searches "
    "RESTART IDENTITY CASCADE"
)


@pytest.fixture(autouse=True)
def _truncate_tables(request) -> Iterator[None]:
    """Wipe tables before each test that uses the database."""
    if "db_engine" not in request.fixturenames:
        yield
        return

    engine = request.getfixturevalue("db_engine")
    from sqlalchemy import text

    async def _wipe():
        async with engine.begin() as conn:
            await conn.execute(text(_TRUNCATE_SQL))

    asyncio.run(_wipe())
    yield


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncIterator:
    """Yield a fresh AsyncSession bound to the test engine."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def api_client(db_engine) -> AsyncIterator:
    """ASGI test client wired to the test database."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import db as db_module
    from app import app

    test_session_maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override_get_db():
        async with test_session_maker() as session:
            yield session

    app.dependency_overrides[db_module.get_db] = _override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seed_sessions(db_session):
    """Insert a deterministic small set of sessions/segments/tool_calls/topics.

    Layout:
      - 3 claude sessions across 2 projects (conversations x2, oft x1)
      - 1 codex session in project oft
      - 1 hidden claude session in project archive
      - segments + tool_calls + topics attached so search/dashboard queries return non-trivial data
    """
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from models import Segment, Session, SessionTopic, ToolCall

    base = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    sessions = [
        Session(
            id="s1",
            provider="claude",
            project="conversations",
            model="claude-opus-4-6",
            conversation_id="conv-1",
            started_at=base,
            ended_at=base + timedelta(hours=1),
            turn_count=12,
            input_tokens=10000,
            output_tokens=4000,
            cache_read_tokens=2000,
            cache_creation_tokens=500,
            total_chars=8000,
            total_words=1200,
            estimated_cost=Decimal("2.1400"),
            source_file="markdown/conversations.md",
            summary_text="Fixed Docker auth by switching to buildkit secrets",
            session_type="devops",
        ),
        Session(
            id="s2",
            provider="claude",
            project="conversations",
            model="claude-sonnet-4-6",
            conversation_id="conv-2",
            started_at=base + timedelta(days=5),
            ended_at=base + timedelta(days=5, hours=2),
            turn_count=20,
            input_tokens=18000,
            output_tokens=6000,
            cache_read_tokens=3000,
            cache_creation_tokens=800,
            total_chars=15000,
            total_words=2300,
            estimated_cost=Decimal("0.8800"),
            source_file="markdown/conversations.md",
            summary_text="Refactored search to use tsvector ranking",
            session_type="coding",
        ),
        Session(
            id="s3",
            provider="claude",
            project="oft",
            model="claude-opus-4-6",
            conversation_id="conv-3",
            started_at=base + timedelta(days=10),
            ended_at=base + timedelta(days=10, hours=1),
            turn_count=4,
            input_tokens=2000,
            output_tokens=1000,
            cache_read_tokens=500,
            cache_creation_tokens=100,
            total_chars=2000,
            total_words=300,
            estimated_cost=Decimal("0.1500"),
            source_file="markdown/oft.md",
            summary_text="Quick research on chart libraries",
            session_type="research",
        ),
        Session(
            id="s4",
            provider="codex",
            project="oft",
            model="openai",
            conversation_id="conv-4",
            started_at=base + timedelta(days=12),
            ended_at=base + timedelta(days=12, hours=1),
            turn_count=8,
            input_tokens=5000,
            output_tokens=2000,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            total_chars=4000,
            total_words=600,
            estimated_cost=Decimal("0.0500"),
            source_file="markdown_codex/oft.md",
            summary_text="Codex prototype for chart rendering",
            session_type="coding",
        ),
        Session(
            id="s5",
            provider="claude",
            project="archive",
            model="claude-haiku-4-5",
            conversation_id="conv-5",
            started_at=base - timedelta(days=30),
            ended_at=base - timedelta(days=30, hours=-1),
            turn_count=2,
            input_tokens=500,
            output_tokens=200,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            total_chars=400,
            total_words=60,
            estimated_cost=Decimal("0.0100"),
            source_file="markdown/archive.md",
            summary_text="Old archived session",
            session_type="research",
            hidden_at=base,
        ),
    ]
    for s in sessions:
        db_session.add(s)
    await db_session.flush()

    segments = [
        Segment(
            id="seg-1a", session_id="s1", segment_index=0, role="user",
            timestamp=base, char_count=4000, word_count=600,
            raw_text="how do I fix docker auth in the buildkit pipeline",
            preview="how do I fix docker auth",
        ),
        Segment(
            id="seg-1b", session_id="s1", segment_index=1, role="user",
            timestamp=base + timedelta(minutes=20), char_count=4000, word_count=600,
            raw_text="follow up on docker registry token leakage",
            preview="follow up on docker registry",
        ),
        Segment(
            id="seg-2a", session_id="s2", segment_index=0, role="user",
            timestamp=base + timedelta(days=5), char_count=8000, word_count=1200,
            raw_text="refactor search to use tsvector ranking instead of substring",
            preview="refactor search to use tsvector",
        ),
        Segment(
            id="seg-2b", session_id="s2", segment_index=1, role="user",
            timestamp=base + timedelta(days=5, minutes=30), char_count=7000, word_count=1100,
            raw_text="add filter chips for project model and tool",
            preview="add filter chips",
        ),
        Segment(
            id="seg-3a", session_id="s3", segment_index=0, role="user",
            timestamp=base + timedelta(days=10), char_count=2000, word_count=300,
            raw_text="which chart library should I use for the dashboard",
            preview="which chart library",
        ),
        Segment(
            id="seg-4a", session_id="s4", segment_index=0, role="user",
            timestamp=base + timedelta(days=12), char_count=4000, word_count=600,
            raw_text="codex prototype for chart rendering with d3",
            preview="codex prototype for chart rendering",
        ),
    ]
    for seg in segments:
        db_session.add(seg)
    await db_session.flush()

    tool_calls = [
        ToolCall(session_id="s1", segment_id="seg-1a", tool_name="Bash", tool_family="execution", timestamp=base),
        ToolCall(session_id="s1", segment_id="seg-1a", tool_name="Bash", tool_family="execution", timestamp=base),
        ToolCall(session_id="s1", segment_id="seg-1b", tool_name="Edit", tool_family="file_ops", timestamp=base),
        ToolCall(session_id="s2", segment_id="seg-2a", tool_name="Edit", tool_family="file_ops", timestamp=base),
        ToolCall(session_id="s2", segment_id="seg-2b", tool_name="Read", tool_family="file_ops", timestamp=base),
        ToolCall(session_id="s2", segment_id="seg-2b", tool_name="Grep", tool_family="search", timestamp=base),
        ToolCall(session_id="s3", segment_id="seg-3a", tool_name="WebSearch", tool_family="web", timestamp=base),
        ToolCall(session_id="s4", segment_id="seg-4a", tool_name="Bash", tool_family="execution", timestamp=base),
    ]
    for tc in tool_calls:
        db_session.add(tc)
    await db_session.flush()

    topics = [
        SessionTopic(session_id="s1", topic="docker", confidence=0.9, source="heuristic"),
        SessionTopic(session_id="s1", topic="authentication", confidence=0.7, source="heuristic"),
        SessionTopic(session_id="s2", topic="search", confidence=0.8, source="heuristic"),
        SessionTopic(session_id="s2", topic="refactoring", confidence=0.6, source="heuristic"),
        SessionTopic(session_id="s3", topic="visualization", confidence=0.8, source="heuristic"),
        SessionTopic(session_id="s4", topic="visualization", confidence=0.7, source="heuristic"),
    ]
    for t in topics:
        db_session.add(t)
    await db_session.commit()

    return {
        "sessions": sessions,
        "segments": segments,
        "tool_calls": tool_calls,
        "topics": topics,
    }
