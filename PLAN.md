# v2 Migration Plan

**Current phase: 3 (not started)**

Phased refactoring from in-memory index to PostgreSQL. Each phase produces a working system. No phase breaks existing functionality.

> Update the "Current phase" line above as each phase completes.

---

## Phase 0 — Scaffolding ✅

**Status: COMPLETE**

**What was built:**
- PostgreSQL 16 (pgvector/pgvector:pg16) added to `docker-compose.yml` with healthcheck, `pgdata` volume, `depends_on` with `service_healthy` condition
- `DATABASE_URL=postgresql+asyncpg://conversations:conversations@postgres:5432/conversations` wired into `llm-browser` service
- Backend split into modular routes: `index_store.py` + `routes/` (projects, segments, conversations, stats, summaries, visibility)
- SQLAlchemy 2.0 async declarative models (`models.py`) define all 7 tables in the `conversations` schema — replaces the originally planned `schema.sql`
- Pydantic v2 API schemas (`schemas.py`) with `from_attributes=True` — ready for Phase 2 endpoint migration
- `db.py` with SQLAlchemy async engine + `async_sessionmaker` + `init_db()` that creates extensions, schema, and tables on app startup
- Requirements: `sqlalchemy[asyncio]`, `asyncpg`, `pydantic`, `pgvector` (replaces originally planned `psycopg`/`psycopg_pool`)

**Architecture decision:** SQLAlchemy 2.0 async + asyncpg + Pydantic v2 instead of raw psycopg + SQL files. All tables in `conversations` schema (not `public`). Schema managed by Python models, created via `Base.metadata.create_all()` on startup — no SQL migration files.

**Phase 0 deliverable:** Postgres is running, schema is created, backend is modular, connection pool exists. Zero behavior changes. Frontend untouched.

---

## Phase 1 — Data Loader ✅

**Status: COMPLETE**

**What was built:**
- `jsonl_reader.py` — Extracts model names + actual token usage (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) from raw Claude JSONL files. Codex: extracts `model_provider` only (no token data available). Keyed by session UUID.
- `load.py` — Async data loader that merges `parser.py` markdown output with `jsonl_reader.py` metadata. Groups segments into sessions by `conversation_id`. Upserts into `sessions`, `segments`, `tool_calls`, `session_topics` via SQLAlchemy `pg_insert` with `on_conflict_do_update` (idempotent). Computes `estimated_cost` from actual tokens x model pricing (cache read tokens at 10% of input price). Runnable standalone via `python load.py` or wired into the app.
- `topics.py` — Heuristic topic extraction: project name segments, file extension keywords, keyword matching, tool-derived signals, word frequency. Returns up to 5 `(topic, confidence)` tuples per session.
- `classify.py` — Heuristic session type classification into coding/debugging/planning/research/writing/devops based on tool counts, topic keywords, and session characteristics.
- `import_graph.py` — Graphify concept graph import. `load.py` runs Graphify against `markdown/` to generate `graphify-out/graph.json`, then `import_graph.py` populates `concepts` and `session_concepts` tables and merges concepts into `session_topics` with `source='graphify'` and 0.9 confidence. Graphify is a dependency in `requirements.txt`. Failures are non-fatal.
- `app.py` — `run_export_pipeline()` is now `async`, calls `load.py`'s `load_all()` after rebuilding the in-memory index. Watch loop also syncs Postgres on markdown changes. Postgres sync failures are non-fatal (logged, don't break pipeline).

**Key design decisions:**
- The markdown parsers (`convert_claude_jsonl_to_md.py`, `convert_codex_sessions.py`) are **not replaced** — they are the source of truth for conversation structure. `jsonl_reader.py` only supplements with metadata (model, tokens) that the markdown format doesn't preserve.
- All DB writes use SQLAlchemy's PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` for idempotency.
- Tool calls are delete-and-reinsert per session (no natural unique key).

**Phase 1 deliverable:** Postgres has all the data. You can query it directly with `psql`. The app still serves from the in-memory index. Nothing is broken.

---

## Phase 2 — Migrate Reads ✅

**Status: COMPLETE**

**What was built:**
- All route modules (`stats`, `projects`, `segments`, `conversations`, `visibility`, `summaries`) rewritten to read from Postgres via SQLAlchemy async queries with `Depends(get_db)`.
- All endpoints are `async def` with `AsyncSession` injection.
- Queries use `select(Segment, Session).join(Session)` tuple pattern to avoid lazy-loading `MissingGreenlet` errors in async context.
- Hidden state migrated from file-based `state.py` to `hidden_at` columns via `UPDATE` statements.
- Search upgraded from substring matching to PostgreSQL `tsvector`/`ts_rank` full-text search — results are now ranked by relevance.
- Summary endpoints migrated segment lookups to Postgres; filesystem-based summary pipeline (`.md`/`.pending`/`.input` files + watcher) unchanged.
- `load_all()` runs on app startup in the lifespan, so Postgres is populated before the first request — no need to manually trigger `/api/update`.
- In-memory index (`index_store.py`) still exists for the export pipeline (`app.py`'s `run_export_pipeline` and `_watch_loop`) but is no longer read by any route module.

**Key implementation details:**
- Avoided `selectinload`/relationship lazy loading entirely — all queries that need Session fields select `(Segment, Session)` as a tuple and unpack both explicitly.
- Timestamp serialization uses `.isoformat().replace("+00:00", "Z")` to match the original ISO 8601 format the frontend expects.
- Tool call counts computed via separate `COUNT` queries on `tool_calls` table since segments don't store `tool_call_count` directly.

**What's left for Phase 6 cleanup:**
- Remove `index_store.py` and its imports from `app.py`
- Remove `state.py` (hidden state now in Postgres)
- Remove in-memory `init_indexes()` / `rebuild_index()` calls from `app.py`
- Remove `_watch_loop` (Postgres loader handles sync)

**Phase 2 deliverable:** All API reads come from Postgres. Frontend is unchanged. Search is now ranked via tsvector. Hidden state is in the database.

---

## Phase 3 — Search Upgrade

**Goal:** Add metadata filter parsing and session-level results to the search endpoint.

### 3.1 — Filter parser

Create `browser/backend/search.py`:
- Parse structured query syntax: `project:X after:Y tool:Bash docker auth`
- Extract filter tokens, pass remainder as the free-text query
- Return a Pydantic `ParsedQuery` model: `ParsedQuery(text="docker auth", filters=SearchFilters(project="X", after=date(2026,3,1), tools=["Bash"]))`

### 3.2 — Session-level search results

Current search returns individual segments. Change to:
1. Search segments with tsvector
2. Group results by session_id
3. For each session, pick the best-matching segment as the snippet
4. Return session-level results with: project, date, model, cost, snippet, tool summary, topics, turn count

The API response shape changes here — this is the first frontend change needed. Update the search results UI to render session cards instead of individual segment rows.

### 3.3 — Filter UI

Add filter chips to the search bar in the frontend. Clicking a chip adds the structured prefix to the query. Autocomplete for project names, model names, tool names, and topics from Postgres `DISTINCT` queries.

### 3.4 — (Optional) Related sessions via concept graph

**Condition:** Only available if `session_concepts` table has data (i.e., Graphify import ran in Phase 1.5). Gracefully absent otherwise — no empty "Related" section shown.

Add a "Related sessions" feature to search results:
- When viewing a session's detail or a search result, query `session_concepts` for other sessions sharing concept nodes with the current session
- Rank related sessions by number of shared concepts (more shared = more related)
- Display as a compact "Related conversations" section below the main search result or in the session detail view
- API: `GET /api/sessions/{session_id}/related` — returns up to 5 related sessions with shared concept names
- Query via SQLAlchemy: self-join `SessionConcept` aliased twice, join to `Concept` for names, group by session, order by shared count DESC, limit 5
- Frontend: add a small "Related" section to the session detail view. Only rendered when the API returns results.

**Phase 3 deliverable:** Search returns ranked, session-level results with metadata filters. Frontend has a proper search UI.

---

## Phase 4 — Dashboard

**Goal:** Add the KPI dashboard as a separate view.

### 4.1 — Dashboard API endpoints

Add new routes in `browser/backend/routes/dashboard.py`:

- `GET /api/dashboard/summary` — summary cards (total sessions, tokens, cost, avg cost, project count, week-over-week deltas)
- `GET /api/dashboard/cost-over-time?group_by=week&stack_by=project` — time series data
- `GET /api/dashboard/projects` — project breakdown (cost, sessions, avg cost)
- `GET /api/dashboard/tools` — tool usage with family grouping
- `GET /api/dashboard/models` — model comparison
- `GET /api/dashboard/session-types` — session type distribution
- `GET /api/dashboard/heatmap` — daily cost for activity heatmap
- `GET /api/dashboard/anomalies` — flagged expensive/looping sessions

All endpoints accept the global filter params: `date_from`, `date_to`, `provider`, `project`, `model`.

All data comes from SQL aggregations — no new tables needed, just queries over existing tables.

### 4.2 — Frontend: tab system + dashboard view

Add a tab switcher to the existing UI header bar (next to the provider dropdown and global stats). Two tabs:

- **Conversations** — the current 3-pane layout (ProjectList, RequestList, ContentViewer + MetadataPanel). This is the default.
- **Dashboard** — replaces the 3-pane layout with a single scrollable dashboard.

Implementation in `App.jsx`:
- Add `activeTab` state (`'conversations'` | `'dashboard'`)
- Render tab buttons in the header
- Conditionally render either the existing pane layout or the new `Dashboard.jsx` based on `activeTab`
- The header (title, provider dropdown, tab buttons) stays visible in both views

`Dashboard.jsx` component:
- Summary cards row
- Cost over time (stacked area) — add a lightweight charting library (Chart.js)
- Project breakdown (horizontal bars)
- Tool usage (horizontal bars)
- Fetches data from `/api/dashboard/*` endpoints on mount and when filters change
- Shares the provider selection from the header

This is the v1 dashboard — 4 charts, dense layout. The existing conversation view is completely untouched.

### 4.3 — Dashboard v1.5 charts

Add remaining charts:
- Model comparison (grouped bars)
- Session type distribution (donut + table)
- Activity heatmap (GitHub-style)
- Anomaly/efficiency table
- Global filter bar
- Click-to-filter on all charts

**Phase 4 deliverable:** Full dashboard as designed in DESIGN.md §4.

---

## Phase 5 — Semantic Search

**Goal:** Add vector embeddings and hybrid retrieval.

### 5.1 — Embedding pipeline

- Add `onnxruntime` + `tokenizers` to requirements
- Download `all-MiniLM-L6-v2` ONNX model (bundle in Docker image or download on first run)
- Create `browser/backend/embed.py`:
  - `embed_text(text: str) -> list[float]` — returns 384-dim vector
  - `embed_session(session) -> list[float]` — builds compressed session text, embeds it
- Extend `load.py` to generate embeddings for all sessions and store via SQLAlchemy `update(Session).where(Session.id == sid).values(embedding=vector)`
- Incremental: only embed sessions where `Session.embedding.is_(None)`

### 5.2 — Hybrid retrieval

Extend `search.py`:
1. Embed the query text
2. Run vector search via SQLAlchemy: `select(Session).order_by(Session.embedding.cosine_distance(query_vector)).limit(50)`
3. Run tsvector search (already exists from Phase 3)
4. Reciprocal Rank Fusion to merge results
5. Apply recency boost + exact match bonus
6. Return top 20

### 5.3 — Frontend updates

Search results should show a relevance indicator (score or visual ranking). No other frontend changes — the search result shape is already session-level from Phase 3.

### 5.4 — (Optional) Community-based re-ranking signal

**Condition:** Only active if `concepts` table has community data (i.e., Graphify import ran). Falls back to standard RRF when absent.

Use Leiden community membership from Graphify as a re-ranking boost in the hybrid retrieval pipeline:
- After RRF fusion produces the candidate list, check if multiple results share a `community_id` via `session_concepts → concepts`
- Sessions in the same community as a top-ranked result get a small additive boost (e.g., `+0.05 * community_overlap_count`)
- This is a tuning knob — the coefficient is configurable and defaults to a conservative value
- Surfaces structural connections that both keyword and embedding similarity miss (e.g., Docker auth work in `conversations` related to Dockerfile work in `biochemistry`)

This does not change the ranking formula for users without Graphify data — the community term is zero when no community data exists.

**Phase 5 deliverable:** Hybrid semantic + keyword search as designed in DESIGN.md §3.

---

## Phase 6 — Cleanup

**Goal:** Remove dead code and legacy paths.

### 6.1 — Remove in-memory index code

- Delete `index_store.py` and all imports of it from route modules
- Remove `build_index()` call from startup
- Remove `_watch_loop`
- `parser.py` stays — it's used by `load.py` to parse markdown

### 6.2 — Remove file-based hidden state

- Delete `state.py` (hidden state is now in Postgres `hidden_at` columns)
- Remove `browser_state.json` from Docker volume mount if no longer needed for summaries
- Keep the `summaries/` directory — that pipeline still uses the filesystem

### 6.3 — Clean up docker-compose.yml

- Remove the `./browser_state:/data/state` volume mount if only summaries remain (or narrow it to summaries only)
- `DATABASE_URL` and `depends_on` were already added in Phase 0.1

### 6.4 — Update export_service.sh

After the export + convert step, add a call to `load.py` to sync new data into Postgres. This replaces the file-watch-based reindexing.

### 6.5 — Update CLAUDE.md

Reflect the new architecture: Postgres as primary storage, no in-memory index, module structure.

**Phase 6 deliverable:** No legacy code remains. Clean architecture. Single source of truth in Postgres.

---

## Phase summary

| Phase | Status | What changes | What breaks | Frontend changes |
|-------|--------|-------------|-------------|-----------------|
| 0 — Scaffolding | ✅ Done | Postgres running, SQLAlchemy models, Pydantic schemas, backend split into modules | Nothing | None |
| 1 — Data Loader | ✅ Done | Postgres populated, topics + types extracted, optional Graphify concept import | Nothing | None |
| 2 — Migrate Reads | ✅ Done | All API reads from Postgres via SQLAlchemy. Search upgraded to tsvector ranking. Hidden state in DB. | Nothing (same JSON shapes) | None |
| 3 — Search Upgrade | Not started | Ranked + filtered + session-level search, optional "Related sessions" via concept graph | Search results shape changes | Search UI updated |
| 4 — Dashboard | Not started | New dashboard view | Nothing | New Dashboard component |
| 5 — Semantic Search | Not started | Vector embeddings + hybrid retrieval, optional community-based re-ranking | Nothing | Minor search UI polish |
| 6 — Cleanup | Not started | Dead code removed (index_store.py, state.py, in-memory globals) | Nothing | None |

Every phase produces a working system. Phases 0–2 are invisible to the frontend. Phase 3 is the first user-visible improvement. Phase 4 is the second. Phase 5 is the third.