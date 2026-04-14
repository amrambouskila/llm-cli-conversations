from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.concept_repository import ConceptRepository
from repositories.segment_repository import SegmentRepository
from repositories.session_repository import SessionRepository
from repositories.session_topic_repository import SessionTopicRepository
from repositories.tool_call_repository import ToolCallRepository
from search import parse_query
from services._filter_scope import SessionFilterScope

if TYPE_CHECKING:
    from models import Session


RRF_K = 60
COMMUNITY_BOOST_COEFFICIENT = 0.05
SESSIONS_PER_LEG = 50
FINAL_RESULT_LIMIT = 20
SNIPPET_MAX_LEN = 250


class SearchService:
    """Hybrid semantic + keyword search returning session-level results.

    Runs the two retrieval legs (tsvector and pgvector), fuses via Reciprocal
    Rank Fusion, applies DESIGN.md §3 final scoring signals (recency, length,
    exact-match), awards Leiden-community-overlap boosts (master plan §10
    Phase 5.4), then extracts term-centered snippets per session.
    """

    def __init__(
        self,
        sessions: SessionRepository,
        segments: SegmentRepository,
        tool_calls: ToolCallRepository,
        topics: SessionTopicRepository,
        concepts: ConceptRepository,
    ) -> None:
        self.sessions = sessions
        self.segments = segments
        self.tool_calls = tool_calls
        self.topics = topics
        self.concepts = concepts

    async def search(
        self,
        query: str | None,
        provider: str = "claude",
        show_hidden: bool = False,
    ) -> list[dict]:
        if not query or len(query.strip()) < 2:
            return []

        parsed = parse_query(query)
        query_text = parsed.text
        scope = SessionFilterScope.build(parsed.filters, provider, show_hidden)
        has_text = len(query_text.strip()) >= 2

        if has_text:
            session_ids, rank_map, sessions_by_id = await self._hybrid_retrieval(
                query_text, scope, show_hidden,
            )
        else:
            session_ids, rank_map, sessions_by_id = await self._filter_only_retrieval(scope)

        if not session_ids:
            return []

        snippets = await self._build_snippets(session_ids, query_text, has_text=has_text)
        tool_summaries = await self.tool_calls.get_counts_by_session_and_tool(session_ids)
        topics_by_session = await self.topics.get_topics_by_session(session_ids)

        return _format_results(
            session_ids,
            sessions_by_id,
            snippets,
            tool_summaries,
            topics_by_session,
            rank_map,
        )

    async def get_status(self, provider: str) -> dict:
        """Embedding coverage + knowledge graph state for the UI mode badges."""
        total_count = await self.sessions.count_visible(provider)
        embedded_count = await self.sessions.count_embedded(provider)
        concept_count = await self.concepts.count_concepts_with_community()
        if total_count == 0:
            mode = "unavailable"
        elif embedded_count == 0:
            mode = "keyword"
        elif embedded_count < total_count:
            mode = "embedding"
        else:
            mode = "hybrid"
        return {
            "mode": mode,
            "total_sessions": total_count,
            "embedded_sessions": embedded_count,
            "has_graph": concept_count > 0,
            "concept_count": concept_count,
        }

    async def get_filters(self, provider: str) -> dict:
        """Distinct values per filter category for autocomplete dropdowns."""
        return {
            "projects": await self.sessions.distinct_projects(provider),
            "models": await self.sessions.distinct_models(provider),
            "tools": await self.tool_calls.distinct_tool_names_for_provider(provider),
            "topics": await self.topics.distinct_topics_for_provider(provider),
        }

    async def _hybrid_retrieval(
        self,
        query_text: str,
        scope: SessionFilterScope,
        show_hidden: bool,
    ) -> tuple[list[str], dict[str, float], dict[str, Session]]:
        keyword_ranked = await self.segments.search_keyword_top_sessions(
            query_text, scope, show_hidden, limit=SESSIONS_PER_LEG,
        )

        # Vector leg is lazy so the ONNX model only loads when a real search runs.
        # Any failure (missing model, no embedded sessions) falls back to keyword-only.
        vector_ranked: list[tuple[str, float]] = []
        try:
            from embed import embed_text

            query_vector = embed_text(query_text)
            vector_ranked = await self.sessions.search_vector_top_sessions(
                query_vector, scope, limit=SESSIONS_PER_LEG,
            )
        except Exception:
            pass

        if vector_ranked:
            rrf_scores = _rrf_merge(keyword_ranked, vector_ranked)
        else:
            raw = {sid: 1 / (RRF_K + rank) for rank, (sid, _) in enumerate(keyword_ranked, 1)}
            max_s = max(raw.values(), default=1.0)
            rrf_scores = {sid: s / max_s for sid, s in raw.items()} if max_s > 0 else raw

        if not rrf_scores:
            return [], {}, {}

        sessions_by_id = await self.sessions.get_by_ids(list(rrf_scores.keys()))

        now = datetime.now(UTC)
        scored: dict[str, float] = {}
        for sid, rrf in rrf_scores.items():
            session = sessions_by_id.get(sid)
            if not session:
                continue
            scored[sid] = (
                0.6 * rrf
                + 0.2 * _recency_boost(session.started_at, now)
                + 0.1 * _length_signal(session.total_words)
                + 0.1 * _exact_match_bonus(session.summary_text, query_text)
            )

        community_boost = await self._community_boost(scored)
        for sid, boost in community_boost.items():
            if sid in scored:
                scored[sid] += boost

        ranked = sorted(scored.items(), key=lambda x: -x[1])[:FINAL_RESULT_LIMIT]
        session_ids = [sid for sid, _ in ranked]
        rank_map = dict(ranked)
        return session_ids, rank_map, sessions_by_id

    async def _filter_only_retrieval(
        self,
        scope: SessionFilterScope,
    ) -> tuple[list[str], dict[str, float], dict[str, Session]]:
        session_ids = await self.sessions.search_filter_only_top_sessions(
            scope, limit=SESSIONS_PER_LEG,
        )
        if not session_ids:
            return [], {}, {}
        sessions_by_id = await self.sessions.get_by_ids(session_ids)
        rank_map = dict.fromkeys(session_ids, 1.0)
        return session_ids, rank_map, sessions_by_id

    async def _build_snippets(
        self,
        session_ids: list[str],
        query_text: str,
        has_text: bool,
    ) -> dict[str, str]:
        if not has_text:
            return {}
        best_texts = await self.segments.get_best_match_raw_texts(session_ids, query_text)
        snippets: dict[str, str] = {
            sid: _extract_snippet(raw, query_text) for sid, raw in best_texts.items()
        }

        missing = [sid for sid in session_ids if sid not in snippets]
        if missing:
            fallback_texts = await self.segments.get_first_raw_texts(missing)
            for sid, raw in fallback_texts.items():
                snippet = _extract_snippet(raw, query_text)
                # Only use the fallback snippet if it found a term — otherwise
                # _extract_snippet returns the raw prefix, and session.summary_text
                # is a better default (applied in _format_results).
                if snippet and snippet != raw[:SNIPPET_MAX_LEN]:
                    snippets[sid] = snippet
        return snippets

    async def _community_boost(
        self,
        scored: dict[str, float],
    ) -> dict[str, float]:
        """Additive boost per shared Leiden community with the top-ranked session.

        Returns {} when no concept data exists — the feature degrades gracefully
        per master plan §10 Phase 5.4.
        """
        if not scored:
            return {}
        communities_by_session = await self.concepts.get_communities_by_session(
            list(scored.keys())
        )
        return _compute_community_boosts(communities_by_session, scored)


# ---------------------------------------------------------------------------
# Scoring helpers — module-level so they're unit-testable without a DB
# ---------------------------------------------------------------------------


def _rrf_merge(
    keyword_results: list[tuple[str, float]],
    vector_results: list[tuple[str, float]],
    k: int = RRF_K,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for rank, (sid, _) in enumerate(keyword_results, 1):
        scores[sid] = scores.get(sid, 0) + 1 / (k + rank)
    for rank, (sid, _) in enumerate(vector_results, 1):
        scores[sid] = scores.get(sid, 0) + 1 / (k + rank)
    max_score = max(scores.values(), default=1.0)
    if max_score > 0:
        return {sid: s / max_score for sid, s in scores.items()}
    return scores


def _recency_boost(started_at: datetime | None, now: datetime) -> float:
    if not started_at:
        return 0.0
    days_ago = max(0.0, (now - started_at).total_seconds() / 86400)
    return 1.0 / (1.0 + math.log(1.0 + days_ago / 30.0))


def _length_signal(total_words: int | None) -> float:
    if not total_words or total_words <= 0:
        return 0.0
    return min(1.0, math.log(1 + total_words) / math.log(10001))


def _exact_match_bonus(summary_text: str | None, query: str) -> float:
    if not summary_text or not query:
        return 0.0
    summary_lower = summary_text.lower()
    terms = query.lower().split()
    if not terms:
        return 0.0
    return sum(1 for t in terms if t in summary_lower) / len(terms)


def _extract_snippet(raw_text: str, query: str, max_len: int = SNIPPET_MAX_LEN) -> str:
    text_lower = raw_text.lower()
    terms = query.lower().split()
    best_pos = -1
    for term in terms:
        pos = text_lower.find(term)
        if pos >= 0:
            best_pos = pos
            break
    if best_pos < 0:
        return raw_text[:max_len]
    start = max(0, best_pos - max_len // 3)
    end = start + max_len
    snippet = raw_text[start:end]
    if start > 0:
        space = snippet.find(" ")
        if space >= 0 and space < 30:
            snippet = "..." + snippet[space + 1:]
    if end < len(raw_text):
        space = snippet.rfind(" ")
        if space > len(snippet) - 30:
            snippet = snippet[:space] + "..."
    return snippet.replace(">>>USER_REQUEST<<<", "").replace("---", "").strip()


def _compute_community_boosts(
    communities_by_session: dict[str, set[int]],
    scored: dict[str, float],
) -> dict[str, float]:
    """Pure scoring helper: given community memberships and base scores, return boost deltas.

    Shared by SearchService._community_boost and the test-facing _community_rerank wrapper.
    """
    if not communities_by_session or not scored:
        return {}
    top_sid = max(scored, key=scored.get)
    top_communities = communities_by_session.get(top_sid, set())
    if not top_communities:
        return {}
    boosts: dict[str, float] = {}
    for sid, communities in communities_by_session.items():
        if sid == top_sid:
            continue
        overlap = len(communities & top_communities)
        if overlap > 0:
            boosts[sid] = COMMUNITY_BOOST_COEFFICIENT * overlap
    return boosts


async def _community_rerank(
    db: AsyncSession,
    scored: dict[str, float],
) -> dict[str, float]:
    """Async wrapper for tests and ad-hoc callers: fetch communities, compute boosts.

    Production code uses SearchService._community_boost via the composed service;
    this free function keeps the old ``_community_rerank(db, scored)`` signature
    working so tests can exercise the behavior without constructing the full service.
    """
    if not scored:
        return {}
    concepts = ConceptRepository(db)
    communities_by_session = await concepts.get_communities_by_session(list(scored.keys()))
    return _compute_community_boosts(communities_by_session, scored)


def _format_results(
    session_ids: list[str],
    sessions_by_id: dict[str, Session],
    snippets: dict[str, str],
    tool_summaries: dict[str, dict[str, int]],
    topics_by_session: dict[str, list[str]],
    rank_map: dict[str, float],
) -> list[dict]:
    results: list[dict] = []
    for sid in session_ids:
        session = sessions_by_id.get(sid)
        if not session:
            continue
        snippet = snippets.get(sid) or session.summary_text or ""
        if len(snippet) > SNIPPET_MAX_LEN:
            snippet = snippet[:SNIPPET_MAX_LEN] + "..."
        tools = tool_summaries.get(sid, {})
        tool_summary_str = ", ".join(
            f"{name}({cnt})" for name, cnt in sorted(tools.items(), key=lambda x: -x[1])
        )
        results.append({
            "session_id": session.id,
            "project": session.project,
            "date": session.started_at.isoformat().replace("+00:00", "Z") if session.started_at else None,
            "model": session.model,
            "cost": float(session.estimated_cost) if session.estimated_cost else None,
            "snippet": snippet,
            "tool_summary": tool_summary_str,
            "tools": tools,
            "turn_count": session.turn_count,
            "topics": topics_by_session.get(sid, [])[:5],
            "conversation_id": session.conversation_id,
            "rank": rank_map.get(sid, 0),
        })
    return results
