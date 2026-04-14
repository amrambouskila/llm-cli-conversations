"""Unit + integration tests for hybrid search helpers in routes.segments.

Covers every ranking helper per DESIGN.md §3 / master plan §7:
  * _rrf_merge — reciprocal rank fusion with [0, 1] normalization
  * _recency_boost — 1 / (1 + log(1 + days_ago / 30))
  * _length_signal — log-scaled word count
  * _exact_match_bonus — fraction of query terms in summary
  * _community_rerank — +0.05 per shared Leiden community with the top result
  * Full scoring formula: 0.6*rrf + 0.2*recency + 0.1*length + 0.1*exact
  * Vector-leg graceful fallback when embeddings are NULL / the model errors
  * Metadata filter pushdown to both keyword and vector legs
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

import embed
from models import Concept, Session, SessionConcept
from routes.segments import (
    COMMUNITY_BOOST_COEFFICIENT,
    _community_rerank,
    _exact_match_bonus,
    _length_signal,
    _recency_boost,
    _rrf_merge,
)


# ---------------------------------------------------------------------------
# _rrf_merge
# ---------------------------------------------------------------------------

def test_rrf_merge_empty_inputs():
    assert _rrf_merge([], []) == {}


def test_rrf_merge_single_keyword_result_normalizes_to_one():
    out = _rrf_merge([("s1", 0.9)], [])
    assert out == {"s1": 1.0}


def test_rrf_merge_keyword_ordering_preserved_after_normalization():
    out = _rrf_merge([("s1", 0.9), ("s2", 0.5), ("s3", 0.1)], [])
    # rank1 > rank2 > rank3 in raw RRF; normalized top is 1.0
    assert out["s1"] == 1.0
    assert out["s1"] > out["s2"] > out["s3"]


def test_rrf_merge_raw_formula_k_60():
    """Before normalization: score = 1/(k + rank). k defaults to 60."""
    out = _rrf_merge([("a", 1.0), ("b", 1.0)], [])
    # raw: a=1/61, b=1/62 → normalized: a=1.0, b=(1/62)/(1/61) = 61/62
    assert out["a"] == pytest.approx(1.0)
    assert out["b"] == pytest.approx(61.0 / 62.0, rel=1e-9)


def test_rrf_merge_custom_k_changes_score():
    out_k10 = _rrf_merge([("a", 1.0), ("b", 1.0)], [], k=10)
    out_k100 = _rrf_merge([("a", 1.0), ("b", 1.0)], [], k=100)
    # Higher k compresses the difference between ranks
    a_over_b_k10 = out_k10["a"] / out_k10["b"]
    a_over_b_k100 = out_k100["a"] / out_k100["b"]
    assert a_over_b_k10 > a_over_b_k100


def test_rrf_merge_shared_ids_accumulate_before_normalization():
    """If a session appears in both legs, its raw score is the sum of both ranks."""
    out = _rrf_merge([("shared", 1.0)], [("shared", 1.0)])
    # Only one candidate — normalized to 1.0
    assert out == {"shared": 1.0}


def test_rrf_merge_both_legs_different_orderings():
    # keyword puts a first, vector puts b first
    out = _rrf_merge(
        keyword_results=[("a", 0.9), ("b", 0.5)],
        vector_results=[("b", 0.9), ("a", 0.5)],
    )
    # Both should have same raw score: 1/61 + 1/62 → normalized both to 1.0
    assert out["a"] == pytest.approx(1.0)
    assert out["b"] == pytest.approx(1.0)


def test_rrf_merge_normalized_values_in_unit_range():
    out = _rrf_merge(
        [("a", 1.0), ("b", 1.0), ("c", 1.0), ("d", 1.0)],
        [("e", 1.0), ("f", 1.0)],
    )
    for score in out.values():
        assert 0.0 < score <= 1.0


# ---------------------------------------------------------------------------
# _recency_boost
# ---------------------------------------------------------------------------

def test_recency_boost_none_is_zero():
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert _recency_boost(None, now) == 0.0


def test_recency_boost_today_is_one():
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert _recency_boost(now, now) == pytest.approx(1.0)


def test_recency_boost_30_days_ago():
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    started = now - timedelta(days=30)
    expected = 1.0 / (1.0 + math.log(2.0))  # days/30 == 1 → log(1+1) = log 2
    assert _recency_boost(started, now) == pytest.approx(expected)


def test_recency_boost_1000_days_ago_is_small_but_positive():
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    started = now - timedelta(days=1000)
    boost = _recency_boost(started, now)
    assert 0.0 < boost < 0.3  # log decay but never negative


def test_recency_boost_monotonically_decreases_with_age():
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    b_today = _recency_boost(now, now)
    b_week = _recency_boost(now - timedelta(days=7), now)
    b_month = _recency_boost(now - timedelta(days=30), now)
    b_year = _recency_boost(now - timedelta(days=365), now)
    assert b_today > b_week > b_month > b_year > 0.0


def test_recency_boost_future_timestamp_clamped_to_zero_days():
    """Future `started_at` must not produce > 1.0 or a negative log input."""
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    future = now + timedelta(days=10)
    boost = _recency_boost(future, now)
    assert boost == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _length_signal
# ---------------------------------------------------------------------------

def test_length_signal_none_is_zero():
    assert _length_signal(None) == 0.0


def test_length_signal_zero_words_is_zero():
    assert _length_signal(0) == 0.0


def test_length_signal_negative_is_zero():
    assert _length_signal(-5) == 0.0


def test_length_signal_single_word_small_positive():
    s = _length_signal(1)
    assert 0.0 < s < 0.1


def test_length_signal_at_10k_words_approaches_one():
    s = _length_signal(10_000)
    assert 0.9 < s <= 1.0


def test_length_signal_capped_at_one():
    s = _length_signal(10_000_000)
    assert s == 1.0


def test_length_signal_monotonically_increasing():
    assert _length_signal(10) < _length_signal(100) < _length_signal(1000) < _length_signal(10000)


# ---------------------------------------------------------------------------
# _exact_match_bonus
# ---------------------------------------------------------------------------

def test_exact_match_bonus_none_summary_is_zero():
    assert _exact_match_bonus(None, "docker auth") == 0.0


def test_exact_match_bonus_empty_query_is_zero():
    assert _exact_match_bonus("anything", "") == 0.0


def test_exact_match_bonus_all_terms_match():
    assert _exact_match_bonus("docker auth issues", "docker auth") == pytest.approx(1.0)


def test_exact_match_bonus_half_match():
    assert _exact_match_bonus("docker but not the other one", "docker auth") == pytest.approx(0.5)


def test_exact_match_bonus_no_match():
    assert _exact_match_bonus("completely different", "docker auth") == 0.0


def test_exact_match_bonus_is_case_insensitive():
    assert _exact_match_bonus("DOCKER AUTH", "docker auth") == pytest.approx(1.0)


def test_exact_match_bonus_whitespace_only_query_is_zero():
    assert _exact_match_bonus("some summary", "   ") == 0.0


# ---------------------------------------------------------------------------
# _community_rerank (requires real DB for the concept/session_concept join)
# ---------------------------------------------------------------------------

async def test_community_rerank_empty_scored_returns_empty(db_session):
    assert await _community_rerank(db_session, {}) == {}


async def test_community_rerank_no_concept_data_returns_empty(seed_sessions, db_session):
    """Candidates exist but no session_concept rows → empty boosts."""
    scored = {"s1": 1.0, "s2": 0.8}
    assert await _community_rerank(db_session, scored) == {}


@pytest_asyncio.fixture
async def community_graph(seed_sessions, db_session):
    """Seed concepts + session_concepts so s1/s2 share community 1 and s3 is in community 2."""
    concepts = [
        Concept(id="c1", name="docker", community_id=1, degree=5),
        Concept(id="c2", name="auth", community_id=1, degree=3),
        Concept(id="c3", name="chart", community_id=2, degree=2),
    ]
    for c in concepts:
        db_session.add(c)
    await db_session.flush()

    edges = [
        # s1: communities {1}
        SessionConcept(session_id="s1", concept_id="c1", relationship_label="contains",
                       edge_type="extracted", confidence=0.9),
        # s2: communities {1} — shares one community with s1
        SessionConcept(session_id="s2", concept_id="c2", relationship_label="contains",
                       edge_type="extracted", confidence=0.9),
        # s3: communities {2} — shares none with s1
        SessionConcept(session_id="s3", concept_id="c3", relationship_label="contains",
                       edge_type="extracted", confidence=0.9),
    ]
    for e in edges:
        db_session.add(e)
    await db_session.commit()


async def test_community_rerank_boosts_sessions_sharing_top_communities(community_graph, db_session):
    # s1 scores highest; s2 shares community 1; s3 shares none
    scored = {"s1": 1.0, "s2": 0.5, "s3": 0.4}
    boosts = await _community_rerank(db_session, scored)
    assert boosts.get("s2") == pytest.approx(COMMUNITY_BOOST_COEFFICIENT * 1)
    assert "s3" not in boosts
    assert "s1" not in boosts  # top result is never boosted


async def test_community_rerank_top_without_concept_data_returns_empty(seed_sessions, db_session):
    """s4 has no concepts — no community data → no boosts applied anywhere."""
    concepts = [Concept(id="c_only_s1", name="x", community_id=1)]
    for c in concepts:
        db_session.add(c)
    db_session.add(SessionConcept(
        session_id="s1", concept_id="c_only_s1", relationship_label="contains",
        edge_type="extracted", confidence=0.9,
    ))
    await db_session.commit()

    # s4 is top-ranked but has no community membership → returns {}
    scored = {"s4": 1.0, "s1": 0.8}
    assert await _community_rerank(db_session, scored) == {}


async def test_community_rerank_overlap_multiplier(seed_sessions, db_session):
    """Boost scales with the number of shared communities."""
    concepts = [
        Concept(id="c_a", name="a", community_id=1, degree=1),
        Concept(id="c_b", name="b", community_id=2, degree=1),
    ]
    for c in concepts:
        db_session.add(c)
    # s1 in communities {1, 2}; s2 in {1, 2} — 2 overlap → boost = 2 * 0.05
    for sid in ("s1", "s2"):
        for cid in ("c_a", "c_b"):
            db_session.add(SessionConcept(
                session_id=sid, concept_id=cid, relationship_label="contains",
                edge_type="extracted", confidence=0.9,
            ))
    await db_session.commit()

    scored = {"s1": 1.0, "s2": 0.5}
    boosts = await _community_rerank(db_session, scored)
    assert boosts.get("s2") == pytest.approx(COMMUNITY_BOOST_COEFFICIENT * 2)


# ---------------------------------------------------------------------------
# Integration: vector-leg graceful fallback + filter pushdown
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_embed_text(monkeypatch):
    """Deterministic 384-dim vector — one for every possible query."""
    def _fake(text: str) -> list[float]:
        return [0.01] * embed.EMBEDDING_DIM
    monkeypatch.setattr(embed, "embed_text", _fake)
    return _fake


@pytest.fixture
def embed_text_raising(monkeypatch):
    """Simulate the embed model failing — vector leg should be skipped silently."""
    def _boom(text: str) -> list[float]:
        raise RuntimeError("ONNX model unavailable")
    monkeypatch.setattr(embed, "embed_text", _boom)
    return _boom


async def test_vector_leg_falls_back_when_no_embeddings(seed_sessions, api_client, fake_embed_text):
    """Seeded sessions have NULL embeddings. Keyword results must still return — no 500."""
    response = await api_client.get("/api/search", params={"q": "docker"})
    assert response.status_code == 200
    data = response.json()
    # Keyword match on "docker" from s1's segment text
    assert any(r["session_id"] == "s1" for r in data)


async def test_vector_leg_falls_back_when_embed_text_errors(seed_sessions, api_client, embed_text_raising, db_session):
    """Even if embeddings exist, if embed_text raises the vector leg is skipped and keyword wins."""
    fake_vec = [0.01] * embed.EMBEDDING_DIM
    await db_session.execute(
        update(Session).where(Session.provider == "claude", Session.hidden_at.is_(None))
        .values(embedding=fake_vec)
    )
    await db_session.commit()

    response = await api_client.get("/api/search", params={"q": "docker"})
    assert response.status_code == 200
    data = response.json()
    assert any(r["session_id"] == "s1" for r in data)


async def test_hybrid_mode_with_embeddings(seed_sessions, api_client, fake_embed_text, db_session):
    """With embeddings present, both legs contribute and results are re-ranked."""
    fake_vec = [0.01] * embed.EMBEDDING_DIM
    await db_session.execute(
        update(Session).where(Session.provider == "claude", Session.hidden_at.is_(None))
        .values(embedding=fake_vec)
    )
    await db_session.commit()

    response = await api_client.get("/api/search", params={"q": "docker"})
    assert response.status_code == 200
    data = response.json()
    assert data
    # rank field populated for every result
    for r in data:
        assert "rank" in r
    # Sorted descending by rank
    ranks = [r["rank"] for r in data]
    assert ranks == sorted(ranks, reverse=True)


async def test_metadata_filter_pushdown_to_both_legs(seed_sessions, api_client, fake_embed_text, db_session):
    """The project: filter must exclude sessions from other projects on BOTH keyword and vector legs."""
    fake_vec = [0.01] * embed.EMBEDDING_DIM
    await db_session.execute(
        update(Session).where(Session.provider == "claude", Session.hidden_at.is_(None))
        .values(embedding=fake_vec)
    )
    await db_session.commit()

    response = await api_client.get(
        "/api/search", params={"q": "project:conversations chart"}
    )
    assert response.status_code == 200
    for r in response.json():
        assert r["project"] == "conversations"


async def test_hidden_sessions_excluded_from_results(seed_sessions, api_client, fake_embed_text, db_session):
    """s5 is pre-hidden in the seed fixture — must not appear in results."""
    fake_vec = [0.01] * embed.EMBEDDING_DIM
    await db_session.execute(
        update(Session).where(Session.provider == "claude")
        .values(embedding=fake_vec)
    )
    await db_session.commit()

    response = await api_client.get("/api/search", params={"q": "archived session"})
    ids = [r["session_id"] for r in response.json()]
    assert "s5" not in ids


# ---------------------------------------------------------------------------
# Final scoring formula
# ---------------------------------------------------------------------------

async def test_final_score_formula_weights(api_client, fake_embed_text, db_session):
    """Craft a single-session scenario where rrf=1, recency=1, length=1, exact=1 →
    final score = 0.6 + 0.2 + 0.1 + 0.1 = 1.0."""
    now = datetime.now(timezone.utc)

    # Start fresh: no existing rows beyond the truncate
    sess = Session(
        id="only-session",
        provider="claude",
        project="proj",
        model="m",
        conversation_id="conv-only",
        started_at=now,
        ended_at=now,
        turn_count=1,
        input_tokens=100,
        output_tokens=100,
        total_chars=100,
        total_words=10_000,               # drives length_signal close to 1.0
        estimated_cost=Decimal("0.10"),
        source_file="x.md",
        summary_text="docker auth",       # contains every query term
        session_type="coding",
        embedding=[0.01] * embed.EMBEDDING_DIM,
    )
    db_session.add(sess)
    await db_session.flush()

    from models import Segment
    db_session.add(Segment(
        id="only-seg",
        session_id="only-session",
        segment_index=0,
        role="user",
        timestamp=now,
        char_count=100,
        word_count=10_000,
        raw_text="docker auth is great",   # tsvector matches "docker auth"
        preview="docker auth",
    ))
    await db_session.commit()

    response = await api_client.get("/api/search", params={"q": "docker auth"})
    data = response.json()
    assert data
    only = next(r for r in data if r["session_id"] == "only-session")
    assert only["rank"] == pytest.approx(1.0, abs=0.02)


# ---------------------------------------------------------------------------
# embed_text input shape (used by the vector leg)
# ---------------------------------------------------------------------------

def test_embed_text_mock_returns_expected_shape(fake_embed_text):
    v = embed.embed_text("anything")
    assert isinstance(v, list)
    assert len(v) == embed.EMBEDDING_DIM
    assert all(isinstance(x, float) for x in v)
