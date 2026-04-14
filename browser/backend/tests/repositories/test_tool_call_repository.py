"""Unit tests for ToolCallRepository — count aggregations and per-segment breakdowns."""
from __future__ import annotations

from repositories.tool_call_repository import ToolCallRepository


async def test_get_counts_by_session_and_tool(seed_sessions, db_session):
    repo = ToolCallRepository(db_session)
    counts = await repo.get_counts_by_session_and_tool(["s1", "s2"])
    assert counts["s1"]["Bash"] == 2
    assert counts["s1"]["Edit"] == 1
    assert counts["s2"] == {"Edit": 1, "Read": 1, "Grep": 1}


async def test_get_counts_empty_list(seed_sessions, db_session):
    assert await ToolCallRepository(db_session).get_counts_by_session_and_tool([]) == {}


async def test_get_counts_missing_sessions_omitted(seed_sessions, db_session):
    """Sessions with no tool calls (s5 in seed has none) aren't keyed in the result."""
    repo = ToolCallRepository(db_session)
    counts = await repo.get_counts_by_session_and_tool(["s5"])
    assert counts == {}


async def test_get_breakdown_for_segment(seed_sessions, db_session):
    repo = ToolCallRepository(db_session)
    # seg-1a has 2 Bash calls in the fixture
    bd = await repo.get_breakdown_for_segment("seg-1a")
    assert bd == {"Bash": 2}


async def test_get_breakdown_for_segment_no_tools(seed_sessions, db_session):
    # seg-2a is tied to s2 but let's use a segment with no tool calls in the seed
    # seg-3a has a WebSearch call; pick a segment with zero tools: none in seed data
    # Use a fabricated unknown segment id → empty dict
    assert await ToolCallRepository(db_session).get_breakdown_for_segment("no-such-segment") == {}


async def test_get_counts_by_segment(seed_sessions, db_session):
    repo = ToolCallRepository(db_session)
    counts = await repo.get_counts_by_segment(["seg-1a", "seg-1b", "seg-2b"])
    assert counts["seg-1a"] == 2  # 2 Bash calls
    assert counts["seg-1b"] == 1  # 1 Edit
    assert counts["seg-2b"] == 2  # 1 Read + 1 Grep


async def test_get_counts_by_segment_empty(seed_sessions, db_session):
    assert await ToolCallRepository(db_session).get_counts_by_segment([]) == {}


async def test_count_for_segments_sums_all(seed_sessions, db_session):
    repo = ToolCallRepository(db_session)
    total = await repo.count_for_segments(["seg-1a", "seg-1b", "seg-2a", "seg-2b"])
    assert total == 2 + 1 + 1 + 2  # = 6


async def test_count_for_segments_empty(seed_sessions, db_session):
    assert await ToolCallRepository(db_session).count_for_segments([]) == 0


async def test_distinct_tool_names_for_provider_claude(seed_sessions, db_session):
    repo = ToolCallRepository(db_session)
    tools = await repo.distinct_tool_names_for_provider("claude")
    assert tools == sorted(tools)
    # Claude side: Bash, Edit, Read, Grep, WebSearch
    assert set(tools) == {"Bash", "Edit", "Read", "Grep", "WebSearch"}


async def test_distinct_tool_names_for_provider_codex(seed_sessions, db_session):
    repo = ToolCallRepository(db_session)
    tools = await repo.distinct_tool_names_for_provider("codex")
    assert tools == ["Bash"]  # s4 only has one Bash call
