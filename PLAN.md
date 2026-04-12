# v2 Migration Plan

**Current phase: 4 (not started)**

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

## Phase 3 — Search Upgrade ✅

**Status: COMPLETE**

**What was built:**
- `browser/backend/search.py` — Filter parser module with `ParsedQuery` and `SearchFilters` Pydantic models. Parses structured query syntax (`project:`, `model:`, `provider:`, `after:`, `before:`, `tool:`, `topic:`, `cost:>`, `turns:>`) mixed with free text. Malformed filter values are left in the free-text query (no crash).
- `/api/search` endpoint rewritten for session-level results: searches segments via tsvector, groups by session, picks best-matching segment as snippet, applies metadata filters as SQL WHERE clauses, returns session-level objects with `session_id`, `project`, `date`, `model`, `cost`, `snippet`, `tool_summary`, `tools`, `turn_count`, `topics`, `conversation_id`, `rank`.
- `GET /api/search/filters` — returns distinct values for autocomplete: `projects`, `models`, `tools`, `topics`.
- `GET /api/sessions/{session_id}/related` — finds sessions sharing Graphify concept nodes. Returns up to 5 related sessions ranked by shared concept count. Returns `[]` gracefully when no concept data exists.
- `SearchResults.jsx` — session-level search result cards with project, date, model, cost, snippet (with query term highlighting), tool summary, turn count, topics. Clicking a card navigates to that conversation.
- `FilterChips.jsx` — filter chip buttons with autocomplete dropdowns for project/model/tool/topic values, active filter tags with remove buttons.
- `App.jsx` updated: session-level search flow, filter options loaded on mount, `SearchResults` rendered in search mode, `FilterChips` in expanded filter bar, provider switch clears search state.
- `App.css` extended: styles for filter chips, dropdowns, active filter tags, search result session cards — all using existing CSS custom properties for dark/light theme support.

**Key design decisions:**
- Search response shape changed from segment-level to session-level — this is the first breaking API change. The old `searchSegments()` function still exists in `api.js` for backward compatibility but `App.jsx` now uses `searchSessions()`.
- Filter-only queries (no free text) return sessions matching metadata filters ordered by recency — enabling browsing by dimension (e.g., `project:conversations` shows all sessions in that project).
- Snippet extraction centers a ~250-char window around the first occurrence of query terms in the best-matching segment, stripping markdown noise.
- The existing segment detail, segment export, and all non-search endpoints are completely untouched.

**Phase 3 deliverable:** Search returns ranked, session-level results with metadata filters. Frontend has session cards, filter chips with autocomplete, and click-to-navigate. Related sessions endpoint available when Graphify data exists.

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

### 4.4 — Concept graph visualization (Graphify)

**Condition:** Only rendered when `concepts` and `session_concepts` tables have data. Gracefully absent otherwise — no empty graph placeholder.

Add a "Knowledge Graph" section to the dashboard:

**Backend:**
- `GET /api/dashboard/graph` — returns the concept graph as nodes + edges for d3 rendering. Nodes: concepts (id, name, type, community_id, degree). Edges: session-concept links or concept-concept co-occurrence (two concepts appearing in the same session). Accepts the global dashboard filter params. Returns `{ nodes: [], edges: [] }` — empty arrays when no Graphify data exists.
- Node data includes `community_id` (Leiden cluster, for coloring), `degree` (edge count, for sizing), and `session_count` (number of sessions linked to this concept, for tooltip).

**Frontend:**
- `ConceptGraph.jsx` component using d3.js force-directed layout wrapped in React (`useRef` + `useEffect`).
- Nodes colored by Leiden community (d3 color scale on `community_id`), sized by degree.
- Edges between concepts that co-occur in the same session (thicker = more shared sessions).
- Hover tooltip: concept name, type, community, linked session count.
- Click a concept node: filters the dashboard to sessions linked to that concept, or navigates to a search with `topic:<concept_name>`.
- Zoom/pan via d3-zoom.
- Rendered as one of the dashboard sections (after the charts, before the anomaly table). Only rendered when the API returns non-empty `nodes`.

**Why d3 and not Chart.js:** This is a force-directed network graph — a non-standard visualization. Per stack conventions, Chart.js handles bar/line/doughnut/area charts; d3 handles custom layouts.

**Phase 4 deliverable:** Full dashboard as designed in DESIGN.md §4, plus a Graphify concept graph visualization when concept data is available.

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

## Phase 6 — Cleanup, Testing & CI

**Goal:** Remove dead code, refactor to OOP, add comprehensive test coverage, set up CI pipeline. This is the final phase — project completion.

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

### 6.5 — OOP refactoring

Refactor the backend to proper OOP patterns. Current state is functional — route handlers with inline query logic, helper functions scattered in route files. Target state:

- **Service layer classes** — extract business logic from route handlers into service classes:
  - `SearchService` — owns query parsing, session-level search, snippet extraction, related sessions. Currently inline in `routes/segments.py`.
  - `SessionService` — owns session CRUD, hide/restore, project listing, stats aggregation. Currently spread across `routes/projects.py`, `routes/stats.py`, `routes/visibility.py`.
  - `LoaderService` — owns the data loading pipeline. Currently in `load.py` as module-level functions.
  - `SummaryService` — owns summary generation pipeline. Currently in `routes/summaries.py`.
- **Repository pattern** — extract raw SQLAlchemy queries into repository classes (one per model) so service classes don't directly construct SQL. Repositories live in `browser/backend/repositories/`.
- **Dependency injection** — services instantiated with repositories, injected into routes via FastAPI `Depends()`.
- **Route handlers become thin** — parse request params, call service, return response. No query logic in routes.
- **One class per file** — per project conventions.

This is a refactor, not a rewrite. No behavior changes. All endpoints return identical responses. The test suite (6.6) validates this.

### 6.6 — Unit tests

Add `pytest` + `pytest-asyncio` + `pytest-cov` test suite in `browser/backend/tests/`.

**Unit tests (mocked DB):**
- `test_search.py` — `parse_query()` for every filter prefix, combined filters, malformed values, empty input, edge cases (special characters, very long input).
- `test_topics.py` — heuristic topic extraction for various session profiles.
- `test_classify.py` — session type classification for each type (coding, debugging, planning, research, writing, devops).
- `test_services.py` — service layer methods with mocked repositories (after 6.5 refactor).

**Integration tests (real Postgres via test container):**
- `test_api_search.py` — `/api/search` with free text, each filter type, combined filters, empty results, provider switching. Verifies response shape matches the session-level contract.
- `test_api_filters.py` — `/api/search/filters` returns correct distinct values.
- `test_api_related.py` — `/api/sessions/{id}/related` with and without concept data.
- `test_api_projects.py` — `/api/projects`, `/api/projects/{name}/segments`, project-level stats.
- `test_api_segments.py` — `/api/segments/{id}`, `/api/segments/{id}/export`.
- `test_api_conversations.py` — `/api/projects/{name}/conversation/{id}`.
- `test_api_visibility.py` — hide/restore for segments, conversations, projects, restore-all.
- `test_api_stats.py` — `/api/stats` response shape and values.
- `test_api_dashboard.py` — all `/api/dashboard/*` endpoints (after Phase 4).
- `test_load.py` — `load_all()` populates tables correctly, idempotent on re-run.

**Test infrastructure:**
- `conftest.py` — async test fixtures: test database (Postgres test container via `testcontainers-python` or a dedicated `docker-compose.test.yml`), async session factory, test data seeding (small set of known sessions/segments/tool_calls/topics for deterministic assertions).
- Coverage target: 100% on `search.py`, `topics.py`, `classify.py`, service classes, repositories. `pragma: no cover` only on startup/lifespan glue.

### 6.7 — Frontend tests

Add `vitest` + `@testing-library/react` test suite in `browser/frontend/src/__tests__/`.

- `SearchResults.test.jsx` — renders session cards, highlights query terms, calls onSelectSession on click, shows "No results found" for empty array.
- `FilterChips.test.jsx` — renders all chips, opens dropdown on click, appends filter on selection, shows active tags, removes filter on X click.
- `App.test.jsx` — integration: search flow (type query → results render → click result → navigates), provider switch clears state, filter bar toggle.
- `utils.test.js` — `formatNumber`, `formatTimestamp`, `renderMarkdown`, `highlightHtml`.

**Test infrastructure:**
- `tests/setup.js` — import `cleanup` from `@testing-library/react`, call in `afterEach` (Vitest does NOT auto-cleanup).
- Mock `fetch` via `vi.fn()` for API calls.

### 6.8 — GitHub Actions CI

Create `.github/workflows/ci.yml`:

**Pipeline stages (in order):**
1. **lint** — `ruff check .` for backend (rules: `["E", "F", "I", "N", "UP", "ANN"]`, line-length 120). `pnpm lint` for frontend.
2. **test-backend** — spin up Postgres service container, run `pytest --cov --cov-report=xml`. Fail on any test failure.
3. **test-frontend** — `pnpm test -- --coverage`. Fail on any test failure.
4. **coverage-gate** — fail if backend or frontend coverage drops below threshold (target: 100%, pragmatic starting gate: 90%+ to unblock the first CI run, ratchet up).
5. **build-frontend** — `pnpm build`. Must compile without errors.
6. **docker-build** — `docker build` against the Dockerfile. Catches Dockerfile drift.

**Triggers:** push to `main`, pull requests to `main`.

**Secrets:** None needed — no external services in tests. Postgres runs as a GitHub Actions service container.

### 6.9 — Update documentation

- Update CLAUDE.md: reflect final architecture (no in-memory index, OOP service layer, repository pattern, test commands).
- Update README.md: add testing section, CI badge, architecture diagram reflecting the refactored structure.
- Update `docs/test_plan.md`: uncomment Phase 6 rows, add CI verification steps.

**Phase 6 deliverable:** No legacy code. OOP architecture with service/repository layers. Full test suite (unit + integration, backend + frontend). GitHub Actions CI pipeline enforcing lint, tests, coverage, build, and Docker build on every push. Project complete.

---

## Phase summary

| Phase | Status | What changes | What breaks | Frontend changes |
|-------|--------|-------------|-------------|-----------------|
| 0 — Scaffolding | ✅ Done | Postgres running, SQLAlchemy models, Pydantic schemas, backend split into modules | Nothing | None |
| 1 — Data Loader | ✅ Done | Postgres populated, topics + types extracted, optional Graphify concept import | Nothing | None |
| 2 — Migrate Reads | ✅ Done | All API reads from Postgres via SQLAlchemy. Search upgraded to tsvector ranking. Hidden state in DB. | Nothing (same JSON shapes) | None |
| 3 — Search Upgrade | ✅ Done | Session-level search with metadata filter parsing, filter chips with autocomplete, related sessions endpoint | Search results shape changed (session-level) | Session cards, filter chips, autocomplete dropdowns |
| 4 — Dashboard | Not started | Dashboard view with Chart.js charts + d3 concept graph visualization | Nothing | Dashboard component, ConceptGraph component, Chart.js + d3 deps |
| 5 — Semantic Search | Not started | Vector embeddings + hybrid retrieval, optional community-based re-ranking | Nothing | Minor search UI polish |
| 6 — Cleanup, Testing & CI | Not started | Dead code removed, OOP refactoring (service/repository layers), full test suite (pytest + vitest), GitHub Actions CI pipeline | Nothing | None (internal quality) |

Every phase produces a working system. Phases 0–2 are invisible to the frontend. Phase 3 is the first user-visible improvement (session-level search + filters). Phase 4 is the second (dashboard + concept graph). Phase 5 is the third (semantic search). Phase 6 is the capstone (code quality, tests, CI). **Phase 6 completes the project.**