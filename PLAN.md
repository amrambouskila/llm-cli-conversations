# v2 Migration Plan

**Current phase: 0 (not started)**

Phased refactoring from in-memory index to PostgreSQL. Each phase produces a working system. No phase breaks existing functionality.

> Update the "Current phase" line above as each phase completes.

---

## Phase 0 — Scaffolding

**Goal:** Set up Postgres infrastructure and backend module structure without changing any existing behavior.

### 0.1 — Add Postgres to Docker Compose

Add a `postgres` service to `docker-compose.yml` alongside the existing `llm-browser` service:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: conversations-postgres
    environment:
      POSTGRES_USER: conversations
      POSTGRES_PASSWORD: conversations
      POSTGRES_DB: conversations
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./browser/backend/schema.sql:/docker-entrypoint-initdb.d/001_schema.sql:ro
    ports:
      - "5432:5432"
    restart: unless-stopped

volumes:
  pgdata:
```

Also update the `llm-browser` service to connect to Postgres:
- Add `DATABASE_URL=postgresql://conversations:conversations@postgres:5432/conversations` to its environment
- Add `depends_on: [postgres]` so it waits for the database

The app won't use the connection yet, but it needs to be wired up so Phases 1 and 2 work without further docker-compose changes.

### 0.2 — Create schema.sql

Create `browser/backend/schema.sql` with the exact schema from DESIGN.md §5. This is the source of truth for the database — the design doc is the rationale, this file is the implementation.

Contents:
- `CREATE EXTENSION` for `vector` and `pg_trgm`
- All table definitions (sessions, segments, tool_calls, session_topics, saved_searches)
- All indexes (metadata, GIN for tsvector, HNSW for pgvector, trigram)
- Mounted into Postgres container at `/docker-entrypoint-initdb.d/` so it runs on first boot

**Schema changes after first boot:** `docker-entrypoint-initdb.d` only runs when the data volume is empty. If the schema changes later, either apply the change manually with `psql`, or wipe and recreate: `docker compose down -v && docker compose up -d postgres` then re-run `load.py`. No migration tool (Alembic etc.) is needed for this project's scale.

### 0.3 — Split backend into modules

Current `app.py` is one large file. Split into modules *without changing any logic*:

```
browser/backend/
├── app.py              ← stays as FastAPI app, imports routes
├── index_store.py      ← NEW: INDEX/CODEX_INDEX/INDEXES globals + get_index()
├── routes/
│   ├── __init__.py
│   ├── projects.py     ← /api/projects, /api/providers
│   ├── segments.py     ← /api/segments, /api/search
│   ├── conversations.py← /api/projects/{p}/conversation/{c}
│   ├── stats.py        ← /api/stats
│   ├── summaries.py    ← /api/summary/*
│   └── visibility.py   ← /api/hide/*, /api/restore/*, /api/hidden
├── parser.py           ← unchanged
├── state.py            ← unchanged
├── db.py               ← NEW: Postgres connection pool (empty initially)
├── schema.sql          ← NEW: database schema
└── requirements.txt    ← add psycopg[binary], psycopg_pool
```

Each route module is a FastAPI `APIRouter`. `app.py` imports and includes them. Every endpoint returns the exact same JSON as before. The in-memory `INDEX` dict remains the data source.

**What stays in `app.py`** (not moved to route modules):
- FastAPI app creation, CORS middleware, lifespan context manager
- The `_watch_loop()` and `sync_directory()` helpers
- The `/api/update` endpoint (depends on export pipeline helpers)
- The static file catch-all route `/{full_path:path}` (must be last)

**Avoiding circular imports:** Extract `INDEX` / `CODEX_INDEX` / `INDEXES` / `get_index()` into a new `browser/backend/index_store.py` module. Both `app.py` and route modules import from `index_store` — never from each other. `app.py` writes to the globals (on startup and rebuild); route modules only read.

**Verification:** Frontend works identically. All API responses unchanged. `api.js` needs zero changes.

### 0.4 — Add psycopg to requirements

```
fastapi>=0.115
uvicorn[standard]>=0.34
psycopg[binary]>=3.2
psycopg_pool>=3.2
```

### 0.5 — Create db.py connection module

```python
# browser/backend/db.py
import os
from contextlib import contextmanager
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://conversations:conversations@localhost:5432/conversations"
)

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=2, max_size=10)
    return _pool

@contextmanager
def get_db():
    pool = get_pool()
    with pool.connection() as conn:
        yield conn
```

At this point `db.py` exists but nothing calls it. The app still runs entirely off the in-memory index.

**Phase 0 deliverable:** Postgres is running, schema is created, backend is modular, connection pool exists. Zero behavior changes. Frontend untouched.

---

## Phase 1 — Data Loader

**Goal:** Populate Postgres from existing parsed data. Both the in-memory index and Postgres contain the same data. Postgres is not yet read by any API.

### 1.0 — Extract model and usage from raw JSONL

The raw JSONL files contain exact model names and token counts that the current markdown pipeline throws away. Every assistant record has:

```json
{
  "message": {
    "model": "claude-opus-4-6",
    "usage": {
      "input_tokens": 3,
      "output_tokens": 26,
      "cache_read_input_tokens": 11269,
      "cache_creation_input_tokens": 4849
    }
  }
}
```

Create `browser/backend/jsonl_reader.py`:
- `read_session_metadata(jsonl_dir) -> dict` — scans all JSONL files in a directory and extracts per-session metadata
- **Claude JSONL** (files in `raw/projects/{project}/`):
  - Each file is one conversation. The filename UUID = the conversation's `sessionId`
  - `model`: from the first assistant record's `message.model` (e.g., `claude-opus-4-6`)
  - Per-turn token usage: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` from `message.usage`
  - Aggregated session totals (sum across all assistant turns in that file)
  - Match to markdown conversations via the UUID in the filename, which corresponds to `conversation_id` in the parsed markdown headings
- **Codex JSONL** (files in `~/.codex/sessions/{year}/{month}/{day}/`):
  - Model name is NOT available (Codex CLI doesn't record it). Use `model_provider` from `session_meta` payload (e.g., `"openai"`)
  - Token usage is NOT available. Fall back to `char_count // 4` estimation
  - Session ID from `session_meta.payload.id`
- Returns a dict keyed by session/conversation ID with model + aggregated usage (or None for fields unavailable in Codex)

This module reads JSONL directly — it does NOT go through the markdown pipeline. The loader (1.1) will merge this metadata with the parsed markdown data.

**Why this matters:** Without this, `sessions.model` is NULL (model comparison dashboard broken), and `estimated_cost` uses `char_count // 4` instead of real token counts. Claude JSONL has exact data — use it. Codex doesn't, so it falls back to estimates.

### 1.1 — Create load.py

Create `browser/backend/load.py` — a script that reads both sources:
1. `parser.py` for markdown content (segments, text, tool calls)
2. `jsonl_reader.py` for metadata (model, token usage)

And writes every session, segment, and tool call into Postgres.

This script:
- Calls `build_index()` from `parser.py` for both Claude and Codex
- Calls `read_session_metadata()` from `jsonl_reader.py` to get model + tokens
- Merges both data sources by matching `conversation_id` / `sessionId`
- Maps parsed segments into sessions using these rules:
  - Segments with the same `conversation_id` belong to the same session
  - Segments with `conversation_id = None` each become their own session (standalone requests)
  - Session ID = the `conversation_id` if present, otherwise the segment's own ID
  - Session timestamps: `started_at` = earliest segment timestamp, `ended_at` = latest
  - Session metrics: aggregated from all constituent segments (sum of tokens, words, chars; count of turns)
- Inserts into `sessions`, `segments`, `tool_calls` tables
- Computes `estimated_cost` using actual tokens × model pricing. Pricing is a hardcoded dict in load.py:
  ```python
  # USD per 1M tokens (input / output)
  MODEL_PRICING = {
      'claude-opus-4-6':     (15.00, 75.00),
      'claude-sonnet-4-6':   (3.00,  15.00),
      'claude-haiku-4-5':    (0.80,  4.00),
      # Codex fallback (rough estimate)
      'openai':              (2.50,  10.00),
  }
  ```
  Cache read tokens use 10% of input price. Cache creation tokens use full input price. Update these numbers as pricing changes.
- Runs topic extraction heuristic (from DESIGN.md §5) and inserts into `session_topics`
- Runs session type classification heuristic and updates `sessions.session_type`
- Uses `ON CONFLICT DO UPDATE` so it can be re-run safely (idempotent)

### 1.2 — Topic extraction module

Create `browser/backend/topics.py`:
- `extract_topics(session, segments) -> list[tuple[str, float]]`
- Heuristic: project name segments + file extension keywords + TF-IDF top terms from user messages
- Returns list of `(topic, confidence)` tuples

### 1.3 — Session type classification module

Create `browser/backend/classify.py`:
- `classify_session(session, tool_counts, topics) -> str`
- Heuristic from DESIGN.md §5
- Returns one of: `coding`, `debugging`, `planning`, `research`, `writing`, `devops`

### 1.4 — Wire load.py into the update pipeline

When `app.py` rebuilds the in-memory index (via `/api/update` or the watch loop), also run the Postgres loader after rebuilding the index. This keeps Postgres in sync with the in-memory index.

Both data sources now contain the same data, but all API reads still come from the in-memory index.

**Phase 1 deliverable:** Postgres has all the data. You can query it directly with `psql` or any SQL tool. The app still serves from the in-memory index. Nothing is broken.

---

## Phase 2 — Migrate Reads (one endpoint at a time)

**Goal:** Switch each API endpoint from in-memory index to Postgres, one at a time. After each switch, verify the frontend still works.

The key constraint: **every endpoint must return the exact same JSON shape as before.** The frontend (`api.js`) doesn't change. Only the backend data source changes.

### Migration order (by dependency and risk):

#### 2.1 — `/api/stats`

**Why first:** No frontend navigation depends on it. It's a pure aggregation. Easy to verify: compare JSON output before and after.

Replace the Python loop that sums metrics across all segments with:
```sql
SELECT COUNT(*),
       SUM(input_tokens), SUM(output_tokens),
       SUM(total_words), SUM(estimated_cost)
FROM sessions WHERE provider = $1 AND hidden_at IS NULL;
```

Monthly breakdown:
```sql
SELECT DATE_TRUNC('month', started_at),
       SUM(input_tokens + output_tokens), COUNT(*)
FROM sessions WHERE provider = $1 AND hidden_at IS NULL
GROUP BY 1 ORDER BY 1;
```

#### 2.2 — `/api/providers`

Simple: `SELECT provider, COUNT(*) FROM sessions GROUP BY provider`

#### 2.3 — `/api/projects`

This is the big one — the left pane depends on it. The current endpoint loops all projects, computes stats, filters hidden items. Replace with:

```sql
SELECT project, COUNT(*) as total_requests,
       SUM(total_words) as words,
       SUM(input_tokens + output_tokens) as tokens,
       MIN(started_at) as first_activity, MAX(started_at) as last_activity
FROM sessions WHERE provider = $1
GROUP BY project ORDER BY last_activity DESC;
```

Hidden filtering moves from Python state.py checks to `WHERE hidden_at IS NULL` (the `hidden_at` column is already in the schema).

#### 2.4 — `/api/projects/{project}/segments`

```sql
SELECT s.id, s.session_id, s.segment_index, s.preview, s.timestamp,
       s.char_count, s.word_count, s.input_tokens, s.output_tokens
FROM segments s
JOIN sessions sess ON s.session_id = sess.id
WHERE sess.project = $1 AND sess.provider = $2
ORDER BY s.timestamp, s.segment_index;
```

#### 2.5 — `/api/segments/{segment_id}`

```sql
SELECT * FROM segments WHERE id = $1;
```

Plus tool breakdown:
```sql
SELECT tool_name, COUNT(*) FROM tool_calls WHERE segment_id = $1 GROUP BY tool_name;
```

#### 2.6 — `/api/projects/{project}/conversation/{conv_id}`

```sql
SELECT * FROM segments
WHERE session_id IN (SELECT id FROM sessions WHERE conversation_id = $1 AND project = $2)
ORDER BY segment_index;
```

#### 2.7 — `/api/search`

Replace substring search with tsvector:
```sql
SELECT s.id, s.preview, sess.project, sess.provider,
       ts_rank(s.search_vector, plainto_tsquery('english', $1)) AS rank
FROM segments s
JOIN sessions sess ON s.session_id = sess.id
WHERE s.search_vector @@ plainto_tsquery('english', $1)
ORDER BY rank DESC LIMIT 100;
```

This is the first endpoint where behavior *improves* — ranked results instead of substring matching.

#### 2.8 — `/api/hide/*`, `/api/restore/*`, `/api/hidden`

Migrate hidden state from `browser_state.json` to a `hidden_at TIMESTAMPTZ` column on sessions and segments. The `state.py` module gets replaced with SQL updates:

```sql
UPDATE sessions SET hidden_at = NOW() WHERE id = $1;
UPDATE sessions SET hidden_at = NULL WHERE id = $1;
```

#### 2.9 — Summary endpoints

These depend on the filesystem (`.md`, `.pending`, `.state.json` files) and the external summary watcher process. They need the in-memory index only for segment lookups, which by this point are already on Postgres. Migrate the segment lookups but leave the filesystem-based summary pipeline as-is — it works and isn't in scope for v2.

### After all endpoints are migrated:

- Remove `parser.py` import from route modules
- Remove the global `INDEX` / `CODEX_INDEX` / `INDEXES` dicts from `app.py`
- Remove the `build_index()` call on startup
- Remove the `_watch_loop` (Postgres is the source of truth now; the loader runs after export)
- Keep `parser.py` as a module — `load.py` still uses it to parse markdown before inserting into Postgres

**Phase 2 deliverable:** All API reads come from Postgres. The in-memory index is gone. Frontend is unchanged. Search is now ranked. Hidden state is in the database.

---

## Phase 3 — Search Upgrade

**Goal:** Add metadata filter parsing and session-level results to the search endpoint.

### 3.1 — Filter parser

Create `browser/backend/search.py`:
- Parse structured query syntax: `project:X after:Y tool:Bash docker auth`
- Extract filter tokens, pass remainder as the free-text query
- Return `ParsedQuery(text="docker auth", filters={project: "X", after: "2026-03-01", tools: ["Bash"]})`

### 3.2 — Session-level search results

Current search returns individual segments. Change to:
1. Search segments with tsvector
2. Group results by session_id
3. For each session, pick the best-matching segment as the snippet
4. Return session-level results with: project, date, model, cost, snippet, tool summary, topics, turn count

The API response shape changes here — this is the first frontend change needed. Update the search results UI to render session cards instead of individual segment rows.

### 3.3 — Filter UI

Add filter chips to the search bar in the frontend. Clicking a chip adds the structured prefix to the query. Autocomplete for project names, model names, tool names, and topics from Postgres `DISTINCT` queries.

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
- Extend `load.py` to generate embeddings for all sessions and store via `UPDATE sessions SET embedding = $1 WHERE id = $2`
- Incremental: only embed sessions where `embedding IS NULL`

### 5.2 — Hybrid retrieval

Extend `search.py`:
1. Embed the query text
2. Run vector search: `ORDER BY embedding <=> $1::vector LIMIT 50`
3. Run tsvector search (already exists from Phase 3)
4. Reciprocal Rank Fusion to merge results
5. Apply recency boost + exact match bonus
6. Return top 20

### 5.3 — Frontend updates

Search results should show a relevance indicator (score or visual ranking). No other frontend changes — the search result shape is already session-level from Phase 3.

**Phase 5 deliverable:** Hybrid semantic + keyword search as designed in DESIGN.md §3.

---

## Phase 6 — Cleanup

**Goal:** Remove dead code and legacy paths.

### 6.1 — Remove in-memory index code

- Delete the `INDEX`, `CODEX_INDEX`, `INDEXES` globals if not already removed
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

| Phase | What changes | What breaks | Frontend changes |
|-------|-------------|-------------|-----------------|
| 0 — Scaffolding | Postgres running, backend split into modules, schema exists | Nothing | None |
| 1 — Data Loader | Postgres populated, topics + types extracted | Nothing | None |
| 2 — Migrate Reads | API reads from Postgres instead of in-memory | Nothing (same JSON shapes) | None |
| 3 — Search Upgrade | Ranked + filtered + session-level search | Search results shape changes | Search UI updated |
| 4 — Dashboard | New dashboard view | Nothing | New Dashboard component |
| 5 — Semantic Search | Vector embeddings + hybrid retrieval | Nothing | Minor search UI polish |
| 6 — Cleanup | Dead code removed | Nothing | None |

Every phase produces a working system. Phases 0–2 are invisible to the frontend. Phase 3 is the first user-visible improvement. Phase 4 is the second. Phase 5 is the third.