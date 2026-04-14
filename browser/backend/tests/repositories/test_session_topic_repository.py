"""Unit tests for SessionTopicRepository — topic lookups and autocomplete values."""
from __future__ import annotations

from repositories.session_topic_repository import SessionTopicRepository


async def test_get_topics_by_session_orders_by_confidence(seed_sessions, db_session):
    repo = SessionTopicRepository(db_session)
    topics = await repo.get_topics_by_session(["s1"])
    # s1 has docker(0.9) and authentication(0.7) → docker comes first
    assert topics["s1"] == ["docker", "authentication"]


async def test_get_topics_by_session_multiple_sessions(seed_sessions, db_session):
    repo = SessionTopicRepository(db_session)
    topics = await repo.get_topics_by_session(["s2", "s3"])
    assert "search" in topics["s2"]
    assert "visualization" in topics["s3"]


async def test_get_topics_empty_input(seed_sessions, db_session):
    assert await SessionTopicRepository(db_session).get_topics_by_session([]) == {}


async def test_get_topics_session_without_topics_omitted(seed_sessions, db_session):
    """s5 has no topics in the fixture → not present in the result dict."""
    repo = SessionTopicRepository(db_session)
    topics = await repo.get_topics_by_session(["s5"])
    assert topics == {}


async def test_distinct_topics_for_provider(seed_sessions, db_session):
    repo = SessionTopicRepository(db_session)
    topics = await repo.distinct_topics_for_provider("claude")
    # docker, authentication, search, refactoring, visualization
    expected = {"docker", "authentication", "search", "refactoring", "visualization"}
    assert set(topics) == expected
    assert topics == sorted(topics)


async def test_distinct_topics_for_codex(seed_sessions, db_session):
    repo = SessionTopicRepository(db_session)
    topics = await repo.distinct_topics_for_provider("codex")
    # s4 (codex) has "visualization" topic
    assert topics == ["visualization"]
