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
- `browser/backend/app.py` — FastAPI app (API + serves React build)
- `browser/backend/parser.py` — Markdown → in-memory index builder
- `browser/backend/state.py` — Persistent hide/restore state
- `browser/frontend/src/App.jsx` — React root component
- `browser/frontend/src/components/` — UI components (ProjectList, RequestList, ContentViewer, MetadataPanel, Charts)

### Tech Stack

- **Frontend:** React 19 + Vite 6, custom CSS (dark/light themes), no component library
- **Backend:** FastAPI + Uvicorn, Python 3.13
- **Storage:** Currently in-memory index rebuilt from markdown files on startup. Migrating to PostgreSQL + pgvector.
- **Deployment:** Docker (multi-stage: Node build → Python runtime), docker-compose with volume mounts
- **Port:** 5050 (FastAPI serves API + static React build)

### Data Flow

1. Raw JSONL synced from `~/.claude/projects/` and `~/.codex/sessions/`
2. Python parsers convert to one markdown file per project
3. `parser.py` splits markdown on `>>>USER_REQUEST<<<` delimiters into segments
4. Segments grouped by conversation_id into sessions
5. Metrics computed: char/word/line/token counts, tool breakdowns
6. Index served via REST API at `/api/*`

## Current State

The conversation browser is functional — parsers, FastAPI backend, React UI, Docker deployment all work. The system currently uses an in-memory index rebuilt from markdown files on startup, with substring search.

### Next: v2 Upgrades

Migrate to PostgreSQL + pgvector for persistent storage, ranked search, and a proper dashboard.

- @DESIGN.md — product direction, schema, dashboard spec, anti-bloat guardrails
- @PLAN.md — phased migration plan (6 phases, each produces a working system)

**When working on v2:** Follow PLAN.md phases in order (0 → 1 → 2 → 3 → 4 → 5 → 6). Do not skip ahead — each phase depends on the previous one. Check which phase is current before starting work. Each phase must produce a working system before moving to the next.

### v1 Targets

- [ ] PostgreSQL service in docker-compose (pgvector + pg_trgm extensions)
- [ ] Schema: sessions, segments, tool_calls, session_topics tables with tsvector columns
- [ ] `psycopg` integration in FastAPI backend
- [ ] tsvector/tsquery keyword search replacing substring match
- [ ] Metadata filter parsing in search bar
- [ ] Session-level search results with ranked snippets
- [ ] Heuristic topic extraction and session type classification
- [ ] Dashboard view with cost-over-time, project breakdown, tool usage, summary cards

### v1.5 Targets

- [ ] Semantic search via `all-MiniLM-L6-v2` + `pgvector`
- [ ] Hybrid retrieval with Reciprocal Rank Fusion
- [ ] Dashboard: model comparison, session type distribution, activity heatmap

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