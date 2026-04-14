from __future__ import annotations

import math
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Select, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Concept, Segment, Session, SessionConcept, SessionTopic, ToolCall
from search import parse_query

router = APIRouter()


def _segment_to_dict(seg: Segment, session: Session, tool_breakdown: dict[str, int] | None = None) -> dict:
    """Convert a Segment ORM object to the API dict shape."""
    char_count = seg.char_count or 0
    word_count = seg.word_count or 0
    raw_text = seg.raw_text or ""
    lines = raw_text.count("\n") + 1 if raw_text else 0

    return {
        "id": seg.id,
        "source_file": session.source_file,
        "project_name": session.project,
        "segment_index": seg.segment_index or 0,
        "preview": seg.preview or "",
        "timestamp": seg.timestamp.isoformat().replace("+00:00", "Z") if seg.timestamp else None,
        "conversation_id": session.conversation_id,
        "entry_number": seg.segment_index,
        "metrics": {
            "char_count": char_count,
            "word_count": word_count,
            "line_count": lines,
            "estimated_tokens": max(1, char_count // 4),
            "tool_call_count": sum(tool_breakdown.values()) if tool_breakdown else 0,
        },
        "tool_breakdown": tool_breakdown or {},
        "raw_markdown": raw_text,
    }


async def _get_tool_breakdown(db: AsyncSession, segment_id: str) -> dict[str, int]:
    """Get tool breakdown for a segment."""
    result = await db.execute(
        select(ToolCall.tool_name, func.count(ToolCall.id).label("cnt"))
        .where(ToolCall.segment_id == segment_id)
        .group_by(ToolCall.tool_name)
    )
    return {r.tool_name: r.cnt for r in result.all()}


@router.get("/api/segments/{segment_id}/export")
async def api_segment_export(
    segment_id: str,
    provider: str = "claude",
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return raw markdown for download/copy."""
    result = await db.execute(
        select(Segment, Session)
        .join(Session)
        .where(Segment.id == segment_id)
    )
    row = result.one_or_none()
    if row:
        seg, session = row
        return JSONResponse({
            "filename": f"{session.project}_request_{(seg.segment_index or 0) + 1}.md",
            "content": seg.raw_text or "",
        })
    return JSONResponse({"error": "not found"}, status_code=404)


@router.get("/api/segments/{segment_id}", response_model=None)
async def api_segment_detail(
    segment_id: str,
    provider: str = "claude",
    db: AsyncSession = Depends(get_db),
) -> dict | JSONResponse:
    """Return full segment data including raw markdown."""
    result = await db.execute(
        select(Segment, Session)
        .join(Session)
        .where(Segment.id == segment_id)
    )
    row = result.one_or_none()
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)

    seg, session = row
    tool_bd = await _get_tool_breakdown(db, segment_id)
    return _segment_to_dict(seg, session, tool_bd)


# ---------------------------------------------------------------------------
# Hybrid retrieval helpers (Phase 5.2 — DESIGN.md §3)
# ---------------------------------------------------------------------------


def _rrf_merge(
    keyword_results: list[tuple[str, float]],
    vector_results: list[tuple[str, float]],
    k: int = 60,
) -> dict[str, float]:
    """Reciprocal Rank Fusion: merge two ranked result lists.

    Each leg contributes 1/(k + rank) per result. Scores are then
    normalized to [0, 1] so the final scoring formula weights work correctly.
    """
    scores: dict[str, float] = {}
    for rank, (sid, _) in enumerate(keyword_results, 1):
        scores[sid] = scores.get(sid, 0) + 1 / (k + rank)
    for rank, (sid, _) in enumerate(vector_results, 1):
        scores[sid] = scores.get(sid, 0) + 1 / (k + rank)

    # Normalize to [0, 1]
    max_score = max(scores.values()) if scores else 1.0
    if max_score > 0:
        scores = {sid: s / max_score for sid, s in scores.items()}

    return scores


def _recency_boost(started_at: datetime | None, now: datetime) -> float:
    """Gentle log-decay: 1 / (1 + log(1 + days_ago / 30))."""
    if not started_at:
        return 0.0
    days_ago = max(0.0, (now - started_at).total_seconds() / 86400)
    return 1.0 / (1.0 + math.log(1.0 + days_ago / 30.0))


def _length_signal(total_words: int | None) -> float:
    """Longer sessions slightly preferred. Log-scaled, normalized to [0, 1]."""
    if not total_words or total_words <= 0:
        return 0.0
    return min(1.0, math.log(1 + total_words) / math.log(10001))


def _exact_match_bonus(summary_text: str | None, query: str) -> float:
    """Fraction of query terms that appear verbatim in the session summary."""
    if not summary_text or not query:
        return 0.0
    summary_lower = summary_text.lower()
    terms = query.lower().split()
    if not terms:
        return 0.0
    matches = sum(1 for t in terms if t in summary_lower)
    return matches / len(terms)


# Additive boost per shared community with a top-ranked result
# (master plan §10 Phase 5.4). Conservative default — tunable without code changes.
COMMUNITY_BOOST_COEFFICIENT = 0.05


async def _community_rerank(
    db: AsyncSession,
    scored: dict[str, float],
) -> dict[str, float]:
    """Compute community-based re-ranking boosts.

    After RRF + base scoring produces a candidate list, sessions that share
    Leiden community membership with the top-ranked result get a small
    additive boost. Returns a dict of session_id -> boost (0.0 for most).

    Falls back to empty dict when no community data exists.
    """
    if not scored:
        return {}

    candidate_ids = list(scored.keys())

    # Fetch community memberships for all candidates in one query:
    # session_concepts -> concepts.community_id
    comm_result = await db.execute(
        select(
            SessionConcept.session_id,
            Concept.community_id,
        )
        .join(Concept, SessionConcept.concept_id == Concept.id)
        .where(
            SessionConcept.session_id.in_(candidate_ids),
            Concept.community_id.is_not(None),
        )
    )
    rows = comm_result.all()

    if not rows:
        return {}

    # Build session -> set of community IDs
    communities_by_session: dict[str, set[int]] = {}
    for sid, cid in rows:
        communities_by_session.setdefault(sid, set()).add(cid)

    # Identify the top-ranked session's communities
    top_sid = max(scored, key=scored.get)
    top_communities = communities_by_session.get(top_sid, set())

    if not top_communities:
        return {}

    # Boost other sessions that share communities with the top result
    boosts: dict[str, float] = {}
    for sid, communities in communities_by_session.items():
        if sid == top_sid:
            continue
        overlap = len(communities & top_communities)
        if overlap > 0:
            boosts[sid] = COMMUNITY_BOOST_COEFFICIENT * overlap

    return boosts


@router.get("/api/search")
async def api_search(
    q: str | None = Query(None),
    show_hidden: bool = False,
    provider: str = "claude",
    db: AsyncSession = Depends(get_db),
) -> list:
    """Hybrid semantic + keyword search returning session-level results.

    When free text is present, runs two retrieval legs:
    1. Keyword: tsvector full-text search over segments (top 50)
    2. Semantic: cosine similarity over session embeddings (top 50)
    Then merges via Reciprocal Rank Fusion and re-ranks with recency,
    length, and exact-match signals per DESIGN.md section 3.
    """
    if not q or len(q.strip()) < 2:
        return []

    parsed = parse_query(q)
    query_text = parsed.text
    f = parsed.filters
    has_text = len(query_text.strip()) >= 2

    # --- Common metadata filter conditions ---
    effective_provider = f.provider or provider
    session_conditions = [Session.provider == effective_provider]
    if not show_hidden:
        session_conditions.append(Session.hidden_at.is_(None))
    if f.project:
        session_conditions.append(Session.project == f.project)
    if f.model:
        session_conditions.append(Session.model.ilike(f"%%{f.model}%%"))
    if f.after:
        session_conditions.append(Session.started_at >= f.after.isoformat())
    if f.before:
        session_conditions.append(Session.started_at <= f.before.isoformat() + "T23:59:59")
    if f.min_cost is not None:
        session_conditions.append(Session.estimated_cost >= f.min_cost)
    if f.min_turns is not None:
        session_conditions.append(Session.turn_count >= f.min_turns)

    tool_subq = None
    if f.tools:
        tool_subq = (
            select(ToolCall.session_id)
            .where(ToolCall.tool_name.in_(f.tools))
            .group_by(ToolCall.session_id)
        )
    topic_subq = None
    if f.topic:
        topic_subq = (
            select(SessionTopic.session_id)
            .where(SessionTopic.topic.ilike(f"%%{f.topic}%%"))
        )

    def _apply_filters(stmt: Select, include_tool_topic: bool = True) -> Select:
        for cond in session_conditions:
            stmt = stmt.where(cond)
        if include_tool_topic:
            if tool_subq is not None:
                stmt = stmt.where(Session.id.in_(tool_subq))
            if topic_subq is not None:
                stmt = stmt.where(Session.id.in_(topic_subq))
        return stmt

    if has_text:
        # === Keyword leg: tsvector search over segments, grouped by session ===
        ts_query = func.plainto_tsquery("english", query_text)
        kw_stmt = (
            select(
                Session.id.label("session_id"),
                func.max(func.ts_rank(Segment.search_vector, ts_query)).label("best_rank"),
            )
            .select_from(Segment)
            .join(Session, Segment.session_id == Session.id)
            .where(Segment.search_vector.op("@@")(ts_query))
        )
        kw_stmt = _apply_filters(kw_stmt)
        if not show_hidden:
            kw_stmt = kw_stmt.where(Segment.hidden_at.is_(None))
        kw_stmt = kw_stmt.group_by(Session.id).order_by(text("best_rank DESC")).limit(50)

        kw_result = await db.execute(kw_stmt)
        keyword_ranked = [(r.session_id, float(r.best_rank)) for r in kw_result.all()]

        # === Vector leg: cosine similarity over session embeddings ===
        vector_ranked: list[tuple[str, float]] = []
        try:
            from embed import embed_text
            query_vector = embed_text(query_text)

            vec_stmt = (
                select(
                    Session.id.label("session_id"),
                    (1 - Session.embedding.cosine_distance(query_vector)).label("similarity"),
                )
                .where(Session.embedding.is_not(None))
            )
            vec_stmt = _apply_filters(vec_stmt)
            vec_stmt = vec_stmt.order_by(
                Session.embedding.cosine_distance(query_vector)
            ).limit(50)

            vec_result = await db.execute(vec_stmt)
            vector_ranked = [(r.session_id, float(r.similarity)) for r in vec_result.all()]
        except Exception:
            pass

        # === RRF fusion ===
        if vector_ranked:
            rrf_scores = _rrf_merge(keyword_ranked, vector_ranked)
        else:
            # Keyword-only fallback: still normalize to [0, 1]
            raw = {}
            for rank, (sid, _) in enumerate(keyword_ranked, 1):
                raw[sid] = 1 / (60 + rank)
            max_s = max(raw.values()) if raw else 1.0
            rrf_scores = {sid: s / max_s for sid, s in raw.items()} if max_s > 0 else raw

        if not rrf_scores:
            return []

        # Fetch session data for all candidates to compute final scores
        candidate_ids = list(rrf_scores.keys())
        sess_result = await db.execute(
            select(Session).where(Session.id.in_(candidate_ids))
        )
        sessions_by_id = {s.id: s for s in sess_result.scalars().all()}

        # === Final scoring: DESIGN.md §3 ranking formula ===
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

        # === Community-based re-ranking (master plan §10 Phase 5.4) ===
        # Only active when concepts table has community data.
        if scored:
            community_boost = await _community_rerank(db, scored)
            for sid, boost in community_boost.items():
                if sid in scored:
                    scored[sid] += boost

        ranked = sorted(scored.items(), key=lambda x: -x[1])
        session_ids = [sid for sid, _ in ranked[:20]]
        rank_map = {sid: sc for sid, sc in ranked[:20]}

    else:
        # --- Filter-only mode: no text, return sessions by recency ---
        stmt = (
            select(
                Session.id.label("session_id"),
                func.literal(1.0).label("best_rank"),
            )
            .select_from(Session)
        )
        stmt = _apply_filters(stmt)
        stmt = stmt.order_by(Session.started_at.desc()).limit(50)

        session_ranks = await db.execute(stmt)
        ranked_sessions = session_ranks.all()
        if not ranked_sessions:
            return []

        session_ids = [r.session_id for r in ranked_sessions]
        rank_map = {r.session_id: float(r.best_rank) for r in ranked_sessions}

        sess_result = await db.execute(
            select(Session).where(Session.id.in_(session_ids))
        )
        sessions_by_id = {s.id: s for s in sess_result.scalars().all()}

    # For each session, get the best-matching segment as snippet.
    # tsvector matches get ranked snippets; vector-only results fall back
    # to a simple text scan for query-term context.
    snippets: dict[str, str] = {}
    if has_text:
        ts_query = func.plainto_tsquery("english", query_text)
        snip_result = await db.execute(
            select(
                Segment.session_id,
                Segment.preview,
                Segment.raw_text,
                func.ts_rank(Segment.search_vector, ts_query).label("seg_rank"),
            )
            .where(
                Segment.session_id.in_(session_ids),
                Segment.search_vector.op("@@")(ts_query),
            )
            .order_by(Segment.session_id, text("seg_rank DESC"))
        )
        for row in snip_result.all():
            if row.session_id not in snippets:
                raw = row.raw_text or row.preview or ""
                snippet = _extract_snippet(raw, query_text)
                snippets[row.session_id] = snippet

        # For sessions found by vector search but not tsvector, scan their
        # segments for query terms to build a contextual snippet
        missing_snippet_ids = [sid for sid in session_ids if sid not in snippets]
        if missing_snippet_ids:
            fallback_result = await db.execute(
                select(Segment.session_id, Segment.preview, Segment.raw_text)
                .where(Segment.session_id.in_(missing_snippet_ids))
                .order_by(Segment.session_id, Segment.segment_index)
            )
            for row in fallback_result.all():
                if row.session_id not in snippets:
                    raw = row.raw_text or row.preview or ""
                    snippet = _extract_snippet(raw, query_text)
                    if snippet and snippet != raw[:250]:
                        snippets[row.session_id] = snippet

    # Get tool summaries per session
    tool_result = await db.execute(
        select(
            ToolCall.session_id,
            ToolCall.tool_name,
            func.count(ToolCall.id).label("cnt"),
        )
        .where(ToolCall.session_id.in_(session_ids))
        .group_by(ToolCall.session_id, ToolCall.tool_name)
    )
    tool_summaries: dict[str, dict[str, int]] = {}
    for row in tool_result.all():
        tool_summaries.setdefault(row.session_id, {})[row.tool_name] = row.cnt

    # Get topics per session
    topic_result = await db.execute(
        select(SessionTopic.session_id, SessionTopic.topic)
        .where(SessionTopic.session_id.in_(session_ids))
        .order_by(SessionTopic.confidence.desc())
    )
    topics_by_session: dict[str, list[str]] = {}
    for row in topic_result.all():
        topics_by_session.setdefault(row.session_id, []).append(row.topic)

    # Build response in rank order
    results = []
    for sid in session_ids:
        session = sessions_by_id.get(sid)
        if not session:
            continue
        snippet = snippets.get(sid) or session.summary_text or ""
        if len(snippet) > 250:
            snippet = snippet[:250] + "..."
        tools = tool_summaries.get(sid, {})
        tool_summary_str = ", ".join(f"{name}({cnt})" for name, cnt in sorted(tools.items(), key=lambda x: -x[1]))

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


def _extract_snippet(raw_text: str, query: str, max_len: int = 250) -> str:
    """Extract a snippet centered around the first occurrence of query terms."""
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

    # Center the snippet around the match
    start = max(0, best_pos - max_len // 3)
    end = start + max_len
    snippet = raw_text[start:end]

    # Clean up: avoid starting/ending mid-word
    if start > 0:
        space = snippet.find(" ")
        if space >= 0 and space < 30:
            snippet = "..." + snippet[space + 1:]
    if end < len(raw_text):
        space = snippet.rfind(" ")
        if space > len(snippet) - 30:
            snippet = snippet[:space] + "..."

    # Strip markdown noise
    snippet = snippet.replace(">>>USER_REQUEST<<<", "").replace("---", "").strip()
    return snippet


# ---------------------------------------------------------------------------
# Search status — tells the frontend which search mode is active
# ---------------------------------------------------------------------------

@router.get("/api/search/status")
async def api_search_status(
    provider: str = "claude",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Report embedding + graph coverage so the frontend can show search mode."""
    total = await db.execute(
        select(func.count(Session.id)).where(
            Session.provider == provider,
            Session.hidden_at.is_(None),
        )
    )
    embedded = await db.execute(
        select(func.count(Session.id)).where(
            Session.provider == provider,
            Session.hidden_at.is_(None),
            Session.embedding.is_not(None),
        )
    )
    total_count = total.scalar_one()
    embedded_count = embedded.scalar_one()

    # Check if knowledge graph community data exists
    concept_count_result = await db.execute(
        select(func.count(Concept.id)).where(Concept.community_id.is_not(None))
    )
    concept_count = concept_count_result.scalar_one()
    has_graph = concept_count > 0

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
        "has_graph": has_graph,
        "concept_count": concept_count,
    }


# ---------------------------------------------------------------------------
# Autocomplete endpoints for filter UI
# ---------------------------------------------------------------------------

@router.get("/api/search/filters")
async def api_search_filters(
    provider: str = "claude",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return distinct values for filter autocomplete."""
    projects_q = await db.execute(
        select(distinct(Session.project))
        .where(Session.provider == provider, Session.hidden_at.is_(None))
        .order_by(Session.project)
    )
    models_q = await db.execute(
        select(distinct(Session.model))
        .where(Session.provider == provider, Session.hidden_at.is_(None), Session.model.isnot(None))
        .order_by(Session.model)
    )
    tools_q = await db.execute(
        select(distinct(ToolCall.tool_name))
        .join(Session, ToolCall.session_id == Session.id)
        .where(Session.provider == provider)
        .order_by(ToolCall.tool_name)
    )
    topics_q = await db.execute(
        select(distinct(SessionTopic.topic))
        .join(Session, SessionTopic.session_id == Session.id)
        .where(Session.provider == provider)
        .order_by(SessionTopic.topic)
    )

    return {
        "projects": [r[0] for r in projects_q.all()],
        "models": [r[0] for r in models_q.all()],
        "tools": [r[0] for r in tools_q.all()],
        "topics": [r[0] for r in topics_q.all()],
    }


# ---------------------------------------------------------------------------
# 3.4 — Related sessions via concept graph
# ---------------------------------------------------------------------------

@router.get("/api/sessions/{session_id}/related")
async def api_related_sessions(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list:
    """Find sessions that share concept nodes with the given session."""
    # Check if session_concepts has any data for this session
    check = await db.execute(
        select(func.count(SessionConcept.concept_id))
        .where(SessionConcept.session_id == session_id)
    )
    if check.scalar_one() == 0:
        return []

    # Self-join: find other sessions sharing concepts with this one
    my_concepts = (
        select(SessionConcept.concept_id)
        .where(SessionConcept.session_id == session_id)
    ).subquery()

    related_q = await db.execute(
        select(
            SessionConcept.session_id,
            func.count(distinct(SessionConcept.concept_id)).label("shared_count"),
        )
        .where(
            SessionConcept.concept_id.in_(select(my_concepts.c.concept_id)),
            SessionConcept.session_id != session_id,
        )
        .group_by(SessionConcept.session_id)
        .order_by(text("shared_count DESC"))
        .limit(5)
    )
    related_rows = related_q.all()

    if not related_rows:
        return []

    related_ids = [r.session_id for r in related_rows]
    shared_counts = {r.session_id: r.shared_count for r in related_rows}

    # Fetch session details
    sess_result = await db.execute(
        select(Session).where(Session.id.in_(related_ids), Session.hidden_at.is_(None))
    )
    sessions = {s.id: s for s in sess_result.scalars().all()}

    results = []
    for sid in related_ids:
        session = sessions.get(sid)
        if not session:
            continue
        results.append({
            "session_id": session.id,
            "project": session.project,
            "date": session.started_at.isoformat().replace("+00:00", "Z") if session.started_at else None,
            "model": session.model,
            "summary": (session.summary_text or "")[:150],
            "shared_concepts": shared_counts.get(sid, 0),
            "conversation_id": session.conversation_id,
        })

    return results
