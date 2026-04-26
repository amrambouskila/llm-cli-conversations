# Conversations — LLM CLI Conversation Export

> **MANDATORY WORKFLOW: READ THIS ENTIRE FILE BEFORE EVERY CHANGE.** Every time. No skimming, no assuming prior-session context carries over — it does not.
>
> **Why:** This project spans multiple sessions and months of development. Skipping the re-read produces decisions that contradict the architecture, duplicate existing patterns, break data contracts, or introduce tech debt that compounds.
>
> **The workflow, every time:**
> 1. Read this entire file in full.
> 2. Read `docs/CONVERSATIONS_MASTER_PLAN.md` — the single source of truth for product direction, phases, and architectural decisions.
> 3. Read `docs/status.md` — current state / what just shipped.
> 4. Read `docs/versions.md` — recent version history.
> 5. Read the source files you plan to modify — understand existing patterns first.
> 6. Then implement, following the rules and contracts defined here.

## 0. Critical Context

**What this project is.** A personal observability platform and recall system for Claude CLI and Codex CLI usage — NOT a conversation browser. Every feature must justify itself as *faster recall OR faster pattern understanding*. If it doesn't, it's out of scope. See §12 of the master plan for the anti-bloat guardrails.

**Current phase.** v2.1.1 shipped 2026-04-22. Phase 9 "Drift remediation & full coverage push" is complete on top of the Phase 0-8 v2 migration. The project is feature-complete; changes now should be either bug fixes, small quality-of-life improvements, or new phases approved against the master plan.

**Project-level overrides of the global AGENTS.md** (these are intentional deviations — do not flag them as drift):

- **GitHub Actions instead of GitLab CI.** Documented in master plan §10 Phase 6.7. The project is open-source on GitHub; GitLab isn't available.
- **npm instead of pnpm.** Documented in master plan §10 Phase 6.7. npm is the project's package manager.
- **React + plain JavaScript instead of React + TypeScript strict.** Documented in the Tech Stack section below. The frontend is small (~4400 lines), single-user, and optimizing for typing churn vs runtime guarantees yields no measurable benefit for a tool this size.
- **`pip` + `requirements.txt` with `>=` operators instead of `uv` with pinned deps.** Docker image builds lock transitive versions at build time; the runtime container is the reproducibility unit, not the requirements file.

**Sacred contracts that must not drift without master-plan approval:**
- The 7 Postgres tables under the `conversations` schema (`sessions`, `segments`, `tool_calls`, `session_topics`, `saved_searches`, `concepts`, `session_concepts`). Schema changes require a master-plan update.
- The cost formula in `browser/backend/load.py::estimate_cost_breakdown` (Phase 7.5: `input + output + 0.10 × cache_read + 1.25 × cache_creation`). See master plan §5.
- The search response shape (`SessionSearchResult` Pydantic model) — the frontend relies on it verbatim.

## What This Project Is

A personal observability platform and recall system for Claude CLI and Codex CLI usage. Two pillars:

1. **Searchable recall** — find past conversations by vague memory, not exact keywords
2. **KPI dashboard** — understand LLM usage patterns, cost, and efficiency

This is NOT a conversation browser or archive museum. See @DESIGN.md for the full product direction.

## Architecture

```
Raw JSONL (Claude/Codex CLI)
  → Python parsers (convert_*.py) → Markdown files
  → FastAPI backend + SQLAlchemy 2.0 async → PostgreSQL 16 (pgvector + pg_trgm) → REST API
  → React frontend (browser/frontend/) → 3-pane UI + Dashboard + Knowledge Graph tabs
```

### Key Paths

- `convert_claude_jsonl_to_md.py` — Claude CLI JSONL → Markdown
- `convert_codex_sessions.py` — Codex CLI sessions → Markdown
- `convert_export.py` — Cross-platform export orchestrator
- `browser/backend/app.py` — FastAPI app (API + serves React build), lifespan initializes DB
- `browser/backend/models.py` — SQLAlchemy 2.0 declarative models (all 7 tables, `conversations` schema)
- `browser/backend/schemas.py` — Pydantic v2 request/response models (`from_attributes=True`)
- `browser/backend/db.py` — SQLAlchemy async engine + session maker, `init_db()` creates extensions/schema/tables
- `browser/backend/search.py` — Query parser: extracts structured filter prefixes from free text, returns `ParsedQuery` Pydantic model
- `browser/backend/routes/` — APIRouter modules (projects, segments, conversations, stats, summaries, visibility, dashboard)
- `browser/backend/parser.py` — Markdown → in-memory index builder
- `browser/backend/jsonl_reader.py` — Extracts model + token usage from raw JSONL files
- `browser/backend/load.py` — Merges parser + JSONL data, upserts into Postgres
- `browser/backend/topics.py` — Heuristic topic extraction per session
- `browser/backend/classify.py` — Heuristic session type classification
- `browser/backend/import_graph.py` — Optional Graphify concept graph import
- `browser/backend/embed.py` — ONNX Runtime wrapper for `all-MiniLM-L6-v2` session embeddings (Phase 5)
- `browser/backend/graph_extract.py` — Concept extraction pipeline (claude CLI + graphifyy, Phase 4)
- `browser/frontend/src/App.jsx` — React root component
- `browser/frontend/src/components/` — UI components (ProjectList, RequestList, SearchResults, FilterChips, ContentViewer, MetadataPanel, Charts, SummaryPanel)

### Tech Stack

- **Frontend:** React 19 + Vite 6, custom CSS (dark/light themes), no component library
- **Backend:** FastAPI + Uvicorn, Python 3.13
- **ORM / DB layer:** SQLAlchemy 2.0 async + asyncpg, Pydantic v2 for API schemas
- **Storage:** PostgreSQL 16 (pgvector/pgvector:pg16) with pgvector + pg_trgm extensions. All tables in the `conversations` schema. Schema managed by SQLAlchemy declarative models (`models.py`), created on app startup via `Base.metadata.create_all()`.
- **Deployment:** Docker (multi-stage: Node build → Python runtime), docker-compose with volume mounts
- **Port:** 5050 (FastAPI serves API + static React build)

### Graphify Enrichment

[Graphify](https://github.com/safishamsi/graphify) (`graphify-ai`) is a dependency in `requirements.txt`. It transforms the `markdown/` directory into a cross-session concept graph (`graphify-out/graph.json`). On data load, `import_graph.py` reads the graph and populates `concepts` and `session_concepts` tables in Postgres, enabling richer topic data and "related sessions" discovery. See DESIGN.md §9 for full details.

### Data Flow

1. Raw JSONL synced from `~/.codex/projects/` and `~/.codex/sessions/`
2. Python parsers (`convert_*.py`) convert to one markdown file per project
3. `parser.py` splits markdown on `>>>USER_REQUEST<<<` delimiters into segments
4. Segments grouped by conversation_id into sessions
5. Metrics computed: char/word/line/token counts, tool breakdowns
6. All API endpoints read from Postgres via SQLAlchemy async queries (Phase 2+). In-memory index retained only for the export pipeline's use of `parser.build_index()`.
7. `jsonl_reader.py` extracts model names + actual token usage from raw JSONL
8. `load.py` merges parser + JSONL data and upserts into Postgres (sessions, segments, tool_calls, session_topics)
9. `topics.py` + `classify.py` run heuristic topic extraction and session type classification
10. `import_graph.py` optionally loads Graphify concept graph when `graphify-out/graph.json` exists

## Current State

The conversation browser is functional — parsers, FastAPI backend, React UI, Docker deployment all work. Phases 0 through 6 of the v2 migration are complete; Phase 7 is in progress (7.1 + 7.2 + initial 7.4 shipped):

- **Phase 0 (done):** PostgreSQL 16 with pgvector running in Docker Compose. Backend split into modular routes. SQLAlchemy 2.0 async models define the `conversations` schema (7 tables). Pydantic v2 schemas ready for API layer. Database initialized on app startup via `init_db()`.
- **Phase 1 (done):** Data loader pipeline (`load.py`) populates Postgres from parsed markdown + raw JSONL metadata. Heuristic topic extraction and session type classification. Graphify concept graph import (via `graphifyy` package). Wired into `/api/update`, watch loop, and app startup.
- **Phase 2 (done):** All API endpoints read from Postgres via SQLAlchemy async queries. Search upgraded from substring to tsvector full-text ranking. Hidden state stored in Postgres `hidden_at` columns. In-memory index retained only for the export pipeline.
- **Phase 3 (done):** Search returns session-level results with metadata filter parsing (`project:`, `model:`, `tool:`, `topic:`, `after:`, `before:`, `cost:>`, `turns:>`). Frontend renders session cards with snippet highlighting, filter chips with autocomplete dropdowns, and click-to-navigate. Related sessions endpoint via Graphify concept graph (graceful when no data). New files: `search.py`, `SearchResults.jsx`, `FilterChips.jsx`.
- **Phase 4 (done):** KPI dashboard with 6 chart types (Chart.js), activity heatmap (custom SVG), anomaly table, global filters with click-to-filter. Knowledge graph in its own full-screen tab (d3 force-directed layout with interactive settings panel, `localStorage` persistence). Automated concept extraction pipeline (`graph_extract.py` via `claude -p --system-prompt` + graphifyy clustering) auto-starts on service launch. New files: `routes/dashboard.py`, `Dashboard.jsx`, `Heatmap.jsx`, `ConceptGraph.jsx`, `KnowledgeGraph.jsx`, `graph_extract.py`, `graph_watcher.bat`.
- **Phase 5 (done):** Hybrid semantic + keyword search. `embed.py` loads `sentence-transformers/all-MiniLM-L6-v2` via ONNX Runtime (downloaded on first run, ~90MB, cached). `load.py` incrementally embeds sessions where `embedding IS NULL`. `api_search` runs tsvector + vector legs, merges via Reciprocal Rank Fusion (k=60, normalized to [0,1]), then applies `0.6*rrf + 0.2*recency + 0.1*length + 0.1*exact_match` scoring. Optional community re-ranking boosts sessions sharing Leiden communities with the top result (`+0.05 * overlap_count`). Relevance bar per result card, two-part status badges (Hybrid/Keyword + Graph/No Graph) in the search bar, `/api/search/status` endpoint for polling. Timestamped launcher logs. New files: `browser/backend/embed.py`. New dependencies: `onnxruntime`, `tokenizers`, `huggingface-hub`, `numpy` + `libgomp1` system package in Dockerfile.
- **Phase 6 (done):** Test + CI safety net for the Phase 7 restructure. Dead code removed: `index_store.py`, `state.py`, `INDEX`/`CODEX_INDEX` globals, `WATCH_INTERVAL`, `_watch_loop` (6.1-6.2). Docker volume narrowed to `browser_state/summaries` only (6.3). Launcher scripts (`export_service.sh`, `.bat`) gained `sync_postgres` helper and `[r]` restart loop with full parity (6.4). Backend: 348 pytest tests across 20 files via pytest-asyncio + testcontainers/pgvector + NullPool engine swap + deterministic seed fixtures (6.5). Frontend: 104 vitest tests across 6 files via jsdom + @testing-library/react + @testing-library/user-event (6.6). Two pre-existing bugs in `routes/segments.py` (`func.literal(1.0)` at line 379, and date `.isoformat()` cast at lines 252/254) captured as `xfail(strict=True)` for Phase 7 XPASS handoff. GitHub Actions `ci.yml` (lint-backend → test-backend → test-frontend → build-frontend → docker-build on main/staging/dev + PR + manual dispatch, per-ref concurrency, `--cov-fail-under=70` backend gate, per-file frontend thresholds in `vitest.config.js`). `release.yml` for manual semver bumps of `browser/frontend/package.json`. Ruff fully green after 272-error cleanup (6.7).
- **Phase 7 (in progress):**
  - **7.1 (done):** Backend OOP restructure. New `browser/backend/services/` tree with 7 service classes (`SearchService`, `SessionService`, `DashboardService`, `GraphService`, `ProjectService`, `StatsService`, `SummaryService`) + shared `SessionFilterScope` helper in `services/_filter_scope.py`. New `browser/backend/repositories/` tree with 5 repositories (`SessionRepository`, `SegmentRepository`, `ToolCallRepository`, `SessionTopicRepository`, `ConceptRepository`). `db.py` gained FastAPI DI providers chaining repos → services → routes. Every route handler in `browser/backend/routes/` is now a thin shell calling `Depends(get_*_service)`. Pydantic `response_model=` applied to every endpoint with shapes defined in `schemas.py` (`SessionSearchResult`, `DashboardSummary`, `VisibilityResponse`, `HiddenStateDetail`, etc.).
  - **7.2 (done):** Both Phase 6.5 `xfail(strict=True)` bugs fixed in the same commit as `SearchService` extraction. `func.literal(1.0)` replaced with explicit Python rank assignment in `SearchService._filter_only_retrieval`. Date filters pass `date` objects directly via `Session.started_at >= filters.after` + `Session.started_at < filters.before + timedelta(days=1)` in `SessionFilterScope.build`. Strict XPASS handoff complete: both decorators removed, tests pass as normal.
  - **7.4 partial (done):** Backend `--cov-fail-under` raised 70 → 90 in `pyproject.toml` and `ci.yml`. Total coverage now **94.56%** (up from 76%) because services + repositories are directly traced by pytest-cov.
  - **7.3 (pending):** `App.jsx` decomposition + ESLint + tests for 6.6-deferred components.
  - **7.5 (pending):** Cost audit (`CACHE_WRITE_PREMIUM_5M = 1.25`), 4-way cost-breakdown UI, Top-5 expensive sessions widget, `$644` investigation.
  - **7.6 (pending):** Final documentation pass, `docs/status.md` + `docs/versions.md` creation, README.md updates.
  - **Test state post-7.1/7.2/7.4(partial):** 621/621 pass (333 pre-Phase-7 + 179 new dedicated service/repo tests + 109 existing integration tests). 12 new test files under `tests/services/` and `tests/repositories/`. Ruff clean.

### Next: v2 Upgrade Phase 7 (final phase — partially shipped)

- @DESIGN.md — product direction, schema, dashboard spec, anti-bloat guardrails
- @docs/CONVERSATIONS_MASTER_PLAN.md — **single source of truth** for product direction, architectural decisions, phased migration (Phases 0-7), phase summary table, anti-bloat guardrails, and the full QA/UAT test plan. Supersedes the old `PLAN.md` and `docs/test_plan.md`.

**When working on v2:** Follow the master plan's phases in order (0 → 1 → 2 → 3 → 4 → 5 → 6 → 7). Do not skip ahead — each phase depends on the previous one. Check which phase is current (see the "Current phase" line at the top of the master plan) before starting work. Each phase must produce a working system before moving to the next. **Phases 0-6 complete. Phase 7 in progress: 7.1 (backend OOP) + 7.2 (latent bug fixes) + initial 7.4 (coverage gate 70→90) shipped; 7.3 (frontend decomposition + ESLint), 7.5 (cost audit + UI breakdown), 7.6 (final docs), and remainder of 7.4 still pending.**

### v1 Targets (all complete)

- [x] PostgreSQL service in docker-compose (pgvector + pg_trgm extensions)
- [x] Schema: sessions, segments, tool_calls, session_topics tables with tsvector columns
- [x] asyncpg integration in FastAPI backend (via SQLAlchemy 2.0 async)
- [x] tsvector/tsquery keyword search replacing substring match
- [x] Metadata filter parsing in search bar
- [x] Session-level search results with ranked snippets
- [x] Heuristic topic extraction and session type classification
- [x] Dashboard view with cost-over-time, project breakdown, tool usage, summary cards
- [x] Graphify concept graph visualization (d3 force-directed, Phase 4)

### v1.5 Targets (all complete)

- [x] Semantic search via `all-MiniLM-L6-v2` + `pgvector`
- [x] Hybrid retrieval with Reciprocal Rank Fusion
- [x] Community-based re-ranking via Graphify Leiden communities
- [x] Dashboard: model comparison, session type distribution, activity heatmap

### v2 Targets (Project Completion)

- [x] Dead code removal (Phase 6.1-6.2 — `index_store.py`, `state.py`, `INDEX`, `CODEX_INDEX`, `WATCH_INTERVAL`, `_watch_loop` all removed)
- [x] OOP refactoring: service layer + repository pattern (Phase 7.1 — 7 services, 5 repositories, DI wiring, Pydantic response_models on every route)
- [x] Latent bug fixes: `func.literal(1.0)` + date-range cast (Phase 7.2 — XPASS handoff complete)
- [x] Full unit + integration test suite (Phase 6.5-6.6 — 348 pytest + 104 vitest across 26 files; Phase 7.1 added 179 more in 12 files → 621 total)
- [x] GitHub Actions CI pipeline (Phase 6.7 — `ci.yml` with lint/test/coverage/build/docker-build, `release.yml` for semver bumps)
- [x] Backend coverage gate 70→90 (Phase 7.4 partial — at 94.56%)
- [ ] Frontend decomposition + ESLint + tests for 9 deferred components (Phase 7.3)
- [ ] Cost calculation audit + UI breakdown (Phase 7.5 — cache_write premium, 4-way breakdown, Top-5 widget)
- [ ] Final documentation pass (Phase 7.6 — `docs/status.md`, `docs/versions.md`, README updates)

## Development

```bash
# Frontend dev (hot reload)
cd browser/frontend && npm run dev    # localhost:5174, proxies API to :5050

# Backend dev
cd browser/backend && uvicorn app:app --reload --port 5050

# Full stack via Docker
docker compose up --build             # localhost:5050

# Run export pipeline (sync + convert)
./export_service.sh

# Build frontend for production
cd browser/frontend && npm run build
```

## Code Conventions

- Python: no type stubs, no docstrings unless logic is non-obvious
- React: functional components with hooks, no class components
- CSS: custom properties for theming, no Tailwind/utility classes
- No external charting library yet — current charts are custom SVG. Dashboard v1 will add Chart.js.
- Segment IDs are SHA256(source_file:segment_index), truncated to 16 chars
- Token estimates: currently char_count // 4 (rough). v2 uses actual token counts from JSONL `message.usage` fields.

## Anti-Patterns to Avoid

- Do not add features that assume the user will manually browse old conversations
- Do not add manual tagging, annotation, or note-taking features
- Do not add conversation comparison, diff, or replay features
- Do not index tool output content (Bash stdout, file contents) — only index user/assistant messages
- Do not add per-turn cost attribution — session-level estimates are sufficient
- Every feature must justify itself as: faster recall OR faster pattern understanding

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
