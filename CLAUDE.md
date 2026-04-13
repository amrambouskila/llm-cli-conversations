# Conversations — LLM CLI Conversation Export

## What This Project Is

A personal observability platform and recall system for Claude CLI and Codex CLI usage. Two pillars:

1. **Searchable recall** — find past conversations by vague memory, not exact keywords
2. **KPI dashboard** — understand LLM usage patterns, cost, and efficiency

This is NOT a conversation browser or archive museum. See @DESIGN.md for the full product direction.

## Architecture

```
Raw JSONL (Claude/Codex CLI)
  → Python parsers (convert_*.py) → Markdown files
  → FastAPI backend (parser.py) → In-memory index → REST API
  → React frontend (browser/frontend/) → 3-pane UI
```

### Key Paths

- `convert_claude_jsonl_to_md.py` — Claude CLI JSONL → Markdown
- `convert_codex_sessions.py` — Codex CLI sessions → Markdown
- `convert_export.py` — Cross-platform export orchestrator
- `browser/backend/app.py` — FastAPI app (API + serves React build), lifespan initializes DB
- `browser/backend/models.py` — SQLAlchemy 2.0 declarative models (all 7 tables, `conversations` schema)
- `browser/backend/schemas.py` — Pydantic v2 request/response models (`from_attributes=True`)
- `browser/backend/db.py` — SQLAlchemy async engine + session maker, `init_db()` creates extensions/schema/tables
- `browser/backend/index_store.py` — In-memory index globals (INDEX, CODEX_INDEX) + get_index()
- `browser/backend/search.py` — Query parser: extracts structured filter prefixes from free text, returns `ParsedQuery` Pydantic model
- `browser/backend/routes/` — APIRouter modules (projects, segments, conversations, stats, summaries, visibility)
- `browser/backend/parser.py` — Markdown → in-memory index builder
- `browser/backend/jsonl_reader.py` — Extracts model + token usage from raw JSONL files
- `browser/backend/load.py` — Merges parser + JSONL data, upserts into Postgres
- `browser/backend/topics.py` — Heuristic topic extraction per session
- `browser/backend/classify.py` — Heuristic session type classification
- `browser/backend/import_graph.py` — Optional Graphify concept graph import
- `browser/backend/state.py` — Persistent hide/restore state (file-based, pre-Postgres)
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

1. Raw JSONL synced from `~/.claude/projects/` and `~/.codex/sessions/`
2. Python parsers (`convert_*.py`) convert to one markdown file per project
3. `parser.py` splits markdown on `>>>USER_REQUEST<<<` delimiters into segments
4. Segments grouped by conversation_id into sessions
5. Metrics computed: char/word/line/token counts, tool breakdowns
6. In-memory index served via REST API at `/api/*` (current, being migrated)
7. `jsonl_reader.py` extracts model names + actual token usage from raw JSONL
8. `load.py` merges parser + JSONL data and upserts into Postgres (sessions, segments, tool_calls, session_topics)
9. `topics.py` + `classify.py` run heuristic topic extraction and session type classification
10. `import_graph.py` optionally loads Graphify concept graph when `graphify-out/graph.json` exists

## Current State

The conversation browser is functional — parsers, FastAPI backend, React UI, Docker deployment all work. Phases 0 through 5 of the v2 migration are complete:

- **Phase 0 (done):** PostgreSQL 16 with pgvector running in Docker Compose. Backend split into modular routes. SQLAlchemy 2.0 async models define the `conversations` schema (7 tables). Pydantic v2 schemas ready for API layer. Database initialized on app startup via `init_db()`.
- **Phase 1 (done):** Data loader pipeline (`load.py`) populates Postgres from parsed markdown + raw JSONL metadata. Heuristic topic extraction and session type classification. Graphify concept graph import (via `graphifyy` package). Wired into `/api/update`, watch loop, and app startup.
- **Phase 2 (done):** All API endpoints read from Postgres via SQLAlchemy async queries. Search upgraded from substring to tsvector full-text ranking. Hidden state stored in Postgres `hidden_at` columns. In-memory index retained only for the export pipeline.
- **Phase 3 (done):** Search returns session-level results with metadata filter parsing (`project:`, `model:`, `tool:`, `topic:`, `after:`, `before:`, `cost:>`, `turns:>`). Frontend renders session cards with snippet highlighting, filter chips with autocomplete dropdowns, and click-to-navigate. Related sessions endpoint via Graphify concept graph (graceful when no data). New files: `search.py`, `SearchResults.jsx`, `FilterChips.jsx`.
- **Phase 4 (done):** KPI dashboard with 6 chart types (Chart.js), activity heatmap (custom SVG), anomaly table, global filters with click-to-filter. Knowledge graph in its own full-screen tab (d3 force-directed layout with interactive settings panel, `localStorage` persistence). Automated concept extraction pipeline (`graph_extract.py` via `claude -p --system-prompt` + graphifyy clustering) auto-starts on service launch. New files: `routes/dashboard.py`, `Dashboard.jsx`, `Heatmap.jsx`, `ConceptGraph.jsx`, `KnowledgeGraph.jsx`, `graph_extract.py`, `graph_watcher.bat`.
- **Phase 5 (done):** Hybrid semantic + keyword search. `embed.py` loads `sentence-transformers/all-MiniLM-L6-v2` via ONNX Runtime (downloaded on first run, ~90MB, cached). `load.py` incrementally embeds sessions where `embedding IS NULL`. `api_search` runs tsvector + vector legs, merges via Reciprocal Rank Fusion (k=60, normalized to [0,1]), then applies `0.6*rrf + 0.2*recency + 0.1*length + 0.1*exact_match` scoring. Optional community re-ranking boosts sessions sharing Leiden communities with the top result (`+0.05 * overlap_count`). Relevance bar per result card, two-part status badges (Hybrid/Keyword + Graph/No Graph) in the search bar, `/api/search/status` endpoint for polling. Timestamped launcher logs. New files: `browser/backend/embed.py`. New dependencies: `onnxruntime`, `tokenizers`, `huggingface-hub`, `numpy` + `libgomp1` system package in Dockerfile.

### Next: v2 Upgrades (Phase 6)

- @DESIGN.md — product direction, schema, dashboard spec, anti-bloat guardrails
- @docs/CONVERSATIONS_MASTER_PLAN.md — **single source of truth** for product direction, architectural decisions, phased migration (Phases 0-6), phase summary table, anti-bloat guardrails, and the full QA/UAT test plan. Supersedes the old `PLAN.md` and `docs/test_plan.md`.

**When working on v2:** Follow the master plan's phases in order (0 → 1 → 2 → 3 → 4 → 5 → 6). Do not skip ahead — each phase depends on the previous one. Check which phase is current (see the "Current phase" line at the top of the master plan) before starting work. Each phase must produce a working system before moving to the next.

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

- [ ] Dead code removal (index_store.py, state.py, in-memory globals)
- [ ] OOP refactoring: service layer + repository pattern
- [ ] Full unit + integration test suite (pytest + vitest)
- [ ] GitHub Actions CI pipeline (lint, test, coverage, build, docker-build)

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
