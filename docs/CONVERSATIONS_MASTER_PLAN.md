# Conversations Master Plan

**The single source of truth for this project.** Covers product direction, architectural decisions, tech stack, phased migration, and the full QA/UAT test plan. Supersedes and replaces `PLAN.md` and `docs/test_plan.md`.

> **Current phase: 6 (6.1–6.4 done, 6.5 next) — Phases 0-5 complete**
>
> Update the "Current phase" line above as each phase completes.

---

## Table of Contents

1. [Product Thesis](#1-product-thesis)
2. [Scope](#2-scope)
3. [Architecture Overview](#3-architecture-overview)
4. [Tech Stack](#4-tech-stack)
5. [Architectural Decisions](#5-architectural-decisions)
6. [Data Model](#6-data-model)
7. [Semantic Search Design](#7-semantic-search-design)
8. [KPI Dashboard Design](#8-kpi-dashboard-design)
9. [Graphify Enrichment Layer](#9-graphify-enrichment-layer)
10. [Phased Migration Plan](#10-phased-migration-plan)
11. [Phase Summary Table](#11-phase-summary-table)
12. [Anti-Bloat Guardrails](#12-anti-bloat-guardrails)
13. [QA / UAT Test Plan](#13-qa--uat-test-plan)
14. [Closing Reminders](#14-closing-reminders)

---

## 1. Product Thesis

This project is an **observability platform for LLM CLI usage** and a **recall system for recovering past ideas**. It answers two questions:

1. "What did I discuss with Claude/Codex about X?"
2. "Where is my LLM budget actually going?"

It is **not** a conversation browser. It is a search engine and a dashboard.

Two pillars:

1. **Searchable recall** — find past conversations by vague memory, not exact keywords. Full-text search (tsvector) with metadata filters, session-level results, ranked snippets. Semantic search via pgvector hybrid retrieval.
2. **KPI dashboard** — understand LLM usage patterns, cost, and efficiency. Six chart types (Chart.js), activity heatmap, anomaly detection, global filters. Knowledge graph (d3 force-directed) with automated concept extraction.

Every feature must justify itself as: **faster recall OR faster pattern understanding**.

---

## 2. Scope

### Must Have

| Feature | Justification |
|---------|---------------|
| Hybrid semantic + keyword search | Core recall system. Matches vague human memory to past sessions. |
| Session-level retrieval with ranked snippets | Avoids chunk spam; returns conversations, not fragments. |
| Metadata filters on search | Project, model, date range, tool family, cost threshold. |
| KPI dashboard: cost over time | The single most useful chart — "where is money going?" |
| KPI dashboard: project breakdown | Second most useful — "which projects consume the most?" |
| KPI dashboard: tool usage distribution | Understand workflow patterns. |
| KPI dashboard: model comparison | Claude vs Codex, Sonnet vs Opus. |
| PostgreSQL storage for index + metadata | Current in-memory approach won't survive vector search scale. Postgres gives pgvector + tsvector natively. |
| Session-level topic extraction | Lightweight auto-tagging (1–3 tags per session) to power filters and analytics. |

### Nice to Have

| Feature | Justification |
|---------|---------------|
| Saved searches | "Show me all Docker conversations" as a one-click bookmark. |
| Cost anomaly highlighting | Flag sessions that are >2σ expensive for their length — catches loops/waste. |
| Session type classification | Coding / debugging / planning / research / writing — needed for dashboard breakdowns. Cheap heuristic, no LLM. |
| Weekly/monthly usage digest | Pre-computed summary: "This week: 14 sessions, $12.40, heaviest project: conversations." |
| Graphify concept graph enrichment | Cross-session, cross-project concept graph. Powers "related sessions" discovery, richer topic extraction, and corpus-level structural overview. |

### Exclude

| Feature | Why |
|---------|-----|
| Per-conversation notes/annotations | User doesn't revisit conversations in detail. |
| Session replay or timeline view | Museum feature. |
| Manual tagging | User won't do it. |
| Collaborative features | Single-user tool. |
| Export/sharing | Learnings are documented in actual projects already. |
| Real-time streaming ingestion | Batch is fine; review happens after the fact. |
| Elaborate AI re-summarization | Current summaries work. More effort here is diminishing returns. |

---

## 3. Architecture Overview

### Data flow

```mermaid
graph TD
    A[Claude CLI JSONL<br/>~/.claude/projects] --> B[convert_claude_jsonl_to_md.py]
    C[Codex CLI sessions<br/>~/.codex/sessions] --> D[convert_codex_sessions.py]
    B --> E[markdown/*.md]
    D --> F[markdown_codex/*.md]
    E --> G[parser.py]
    F --> G
    G --> H[In-memory index<br/>export pipeline only]
    E --> I[jsonl_reader.py]
    F --> I
    I --> J[load.py]
    G --> J
    J --> K[(Postgres 16<br/>pgvector + pg_trgm)]
    J --> L[embed.py<br/>all-MiniLM-L6-v2 ONNX]
    L --> K
    E --> M[graph_extract.py<br/>claude -p + graphifyy]
    M --> N[graphify-out/graph.json]
    N --> O[import_graph.py]
    O --> K
    K --> P[FastAPI backend<br/>routes/*.py]
    P --> Q[React 19 frontend<br/>Chart.js + d3]
    Q --> R[Browser at :5050]
```

### Phase timeline

```mermaid
gantt
    title Phased v2 Migration
    dateFormat YYYY-MM-DD
    axisFormat %b %d

    section Foundation
    Phase 0 — Scaffolding         :done, p0, 2026-01-01, 7d
    Phase 1 — Data Loader         :done, p1, after p0, 10d

    section Migration
    Phase 2 — Migrate Reads       :done, p2, after p1, 10d
    Phase 3 — Search Upgrade      :done, p3, after p2, 14d

    section Features
    Phase 4 — Dashboard           :done, p4, after p3, 14d
    Phase 5 — Semantic Search     :done, p5, after p4, 14d

    section Completion
    Phase 6 — Cleanup Testing CI  :active, p6, after p5, 21d
```

### Module dependencies

```mermaid
graph LR
    app[app.py] --> routes
    app --> db
    app --> load
    app --> index_store

    subgraph routes
        proj[projects.py]
        seg[segments.py]
        conv[conversations.py]
        stats[stats.py]
        summ[summaries.py]
        vis[visibility.py]
        dash[dashboard.py]
    end

    routes --> db[db.py]
    routes --> models[models.py]
    routes --> schemas[schemas.py]
    seg --> search[search.py]
    seg --> embed[embed.py]

    load --> db
    load --> models
    load --> parser[parser.py]
    load --> jsonl[jsonl_reader.py]
    load --> topics[topics.py]
    load --> classify[classify.py]
    load --> import_graph[import_graph.py]
    load --> embed

    import_graph --> db
    import_graph --> models

    db --> models

    style embed fill:#9cf
    style import_graph fill:#fc9
    style search fill:#9cf
```

Blue = Phase 5 semantic search additions. Orange = Graphify enrichment (optional).

---

## 4. Tech Stack

### Backend
- **Python 3.13** on `python:3.13-slim` Debian-based image
- **FastAPI** + Uvicorn (async, WebSocket-capable)
- **SQLAlchemy 2.0** async + asyncpg
- **Pydantic v2** for API request/response schemas (`from_attributes=True`)
- **pgvector** Python package (matches Postgres `vector` extension)
- **onnxruntime** + **tokenizers** + **huggingface-hub** for local embedding inference
- **numpy** for vector math in the embedding pipeline
- **graphifyy** for knowledge graph construction (optional sidecar)
- **libgomp1** system package required by onnxruntime (installed in Dockerfile)

### Frontend
- **React 19** + **Vite 6**
- **Chart.js** via `react-chartjs-2` + `chartjs-plugin-datalabels` for dashboard charts
- **d3** for force-directed knowledge graph
- Custom CSS (dark/light theme via CSS custom properties) — no component library, no Tailwind
- Session-level search cards, filter chips with autocomplete dropdowns, two-part search mode badges

### Storage
- **PostgreSQL 16** via `pgvector/pgvector:pg16` image
- Extensions: `vector` (pgvector), `pg_trgm` (fuzzy matching) — created on app startup
- Single schema: all tables under `conversations.*`
- HNSW index on embeddings (`m=16, ef_construction=64`, `vector_cosine_ops`)
- GIN indexes on tsvector columns (`search_vector` on sessions and segments)
- GIN trigram index on `sessions.summary_text`

### Deployment
- **Docker** multi-stage build: `node:20-alpine` for React build → `python:3.13-slim` for runtime
- **docker-compose** with healthcheck on Postgres and `depends_on: service_healthy`
- Port 5050 (FastAPI serves API + static React build)
- Named volume `pgdata` for Postgres persistence
- Bind mounts for `raw/`, `markdown/`, `markdown_codex/`, `browser_state/`, `graphify-out/`

### Launcher
- `export_service.sh` (macOS/Linux) and `export_service.bat` (Windows) — identical feature set
- `[k]` stop keep images, `[q]` stop remove images, `[v]` full cleanup, `[r]` full reset + restart
- Both scripts spawn background watchers: summary watcher (host-side claude CLI) + graph watcher
- Timestamped logs `[HH:MM:SS]` prefix across `load.py`, `app.py`, `graph_extract.py`

---

## 5. Architectural Decisions

### Why PostgreSQL over in-memory
The v1 browser used an in-memory index rebuilt on every startup. That approach:
- Won't scale to vector search (384-dim embeddings per session, HNSW index)
- Can't persist hidden state across restarts without a sidecar file
- Can't support cross-session analytics (dashboard aggregations) efficiently
- Makes concurrent writes impossible

pgvector gives us vector similarity search + full-text search + metadata filters in one query, against one database, with proper indexes. `pg_trgm` handles fuzzy matching for free.

### Why SQLAlchemy 2.0 async + Pydantic v2
- **SQLAlchemy async + asyncpg** is the canonical modern Python DB stack. Matches FastAPI's async model natively.
- **Pydantic v2** with `from_attributes=True` lets us pass ORM objects directly through `model_validate()` — no manual dict construction.
- **No Alembic / migration files**: the project is single-user and can afford "wipe and reload." Schema changes go through `Base.metadata.create_all()` on startup. This is a deliberate choice that trades migration safety for schema simplicity. If the project ever becomes multi-user or has production data worth preserving, introduce Alembic.

### Why no in-memory index reads after Phase 2
All API endpoints read from Postgres via SQLAlchemy. The only remaining use of the in-memory index is the export pipeline (`app.py`'s `run_export_pipeline`), which still walks the parsed markdown tree. Phase 6 removes `index_store.py` entirely.

### Why session-level search, not segment-level
- Session-level embeddings are 10–50x fewer vectors to store and search
- A session-level hit is directly actionable — click through to the conversation
- Avoids "chunk spam" where the same conversation dominates the results
- Snippet extraction does a second-pass keyword search within the matched session's segments

### Why `all-MiniLM-L6-v2` via ONNX Runtime
| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| `all-MiniLM-L6-v2` via `onnxruntime` | Local, free, 384-dim, fast, good quality | Needs ONNX export (~90MB) | **Chosen** |
| OpenAI `text-embedding-3-small` | Excellent quality, tiny API call | Costs money, external dependency | Rejected — prefer local |
| `nomic-embed-text` via Ollama | Local, good quality | Requires Ollama running | Rejected — no Ollama in stack |
| `sentence-transformers` + PyTorch | Easiest Python API | ~2GB image size bloat | Rejected — too heavy for Docker |

ONNX Runtime is a ~90MB model file + a small native library. It runs on CPU (no GPU needed) and is fast enough for our scale (~1000 sessions embeds in seconds).

### Why Reciprocal Rank Fusion for hybrid retrieval
RRF (`1/(k+rank)` with k=60) combines two ranked lists without needing to normalize their scores. Vector cosine distance and tsvector ts_rank have completely different scales, so naive score addition would bias toward one leg. RRF treats both purely by rank position, which is robust across score distributions.

After RRF, we normalize to `[0, 1]` and then layer the DESIGN-specified weights:
```
final_score = 0.6 * rrf_normalized
            + 0.2 * recency_boost       # 1 / (1 + log(1 + days_ago / 30))
            + 0.1 * length_signal       # log-scaled word count
            + 0.1 * exact_match_bonus   # fraction of query terms in summary
```

### Why community-based re-ranking (optional 5.4)
Leiden community membership from Graphify surfaces structural connections that neither keyword nor embedding similarity catches. Two sessions can be semantically distant (different words, different domain jargon) but share a Leiden community (e.g., both discuss Docker auth in very different project contexts).

- **Coefficient**: `+0.05 * community_overlap_count` — conservative, tunable via `COMMUNITY_BOOST_COEFFICIENT`
- **Fallback**: returns `{}` when no community data exists. Zero code path cost.
- **Applied after base scoring** so the top-ranked session's communities drive the boost for others

### Why binary for large numerical payloads (future — not yet implemented)
Not currently a bottleneck because the dashboard aggregates server-side and returns small JSON. If embeddings ever need to cross the wire (e.g., client-side similarity for exploration), switch to MessagePack.

### Why multi-stage Dockerfile
- Stage 1: `node:20-alpine` installs npm deps and builds the React bundle
- Stage 2: `python:3.13-slim` runs FastAPI and serves the built bundle as static files
- Only the final React `dist/` copies into the runtime image — no node_modules bloat
- `libgomp1` installed via `apt-get` in stage 2 — required by onnxruntime's OpenMP runtime, absent from `slim`

### Why timestamped logs
Graphify extraction can take 20-60s per file. When running the launcher and walking away, the logs before this change had no way to tell when a given step started or finished. `[HH:MM:SS]` prefix lets the user scroll back and reconstruct the timeline. Applied uniformly in `load.py`, `app.py`, and `graph_extract.py`.

### Why no tests yet
Deliberate. Phases 0-5 built features that needed fast iteration. Phase 6 adds the full test suite (pytest + vitest, 100% coverage target) + GitHub Actions CI. Tests landing after features is a conscious tradeoff for a single-user personal project.

### What we explicitly rejected
- **Django / Tortoise / Peewee** — Django ORM is too heavyweight, others lack async maturity
- **Flask** — no async, no native WebSocket
- **bokeh / altair / plotnine** as chart libraries — Chart.js + d3 cover the full spectrum (standard + custom + performance)
- **SQLite for prototyping** — Postgres is the production target, start there (no "upgrade later" trap)
- **sentence-transformers + PyTorch** — image size (2GB+) not worth it for a local embedding call

---

## 6. Data Model

All tables live under the `conversations` Postgres schema. Source of truth is `browser/backend/models.py`. The descriptions below are a reference.

### Tables

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| `sessions` | `id TEXT` | One row per conversation. Provider, project, model, timestamps, token counts, estimated cost, summary text, session type, 384-dim embedding, soft-delete `hidden_at`, generated `tsvector`. |
| `segments` | `id TEXT` | Individual request/response segments within a session. FK to `sessions`. Role, timestamps, char/word counts, raw text, preview, generated `tsvector`. UNIQUE on `(session_id, segment_index)`. |
| `tool_calls` | `id SERIAL` | One row per tool invocation. FK to both `sessions` and `segments`. Tool name, tool family, timestamp. |
| `session_topics` | `(session_id, topic)` | Auto-extracted topics per session. Confidence score and `source` (`'heuristic'` or `'graphify'`). |
| `saved_searches` | `id SERIAL` | User-saved search queries with JSONB filter storage. |
| `concepts` | `id TEXT` | Graphify concept nodes (optional). Name, type, Leiden `community_id`, `degree`. |
| `session_concepts` | `(session_id, concept_id, relationship)` | Graphify edges linking sessions to concepts (optional). Edge type and confidence. |

### Indexes

Defined in `models.py` `__table_args__`:

- **Metadata filters** (B-tree): `sessions.project`, `sessions.provider`, `sessions.started_at`, `sessions.model`, `sessions.estimated_cost`, `sessions.session_type`, `segments.session_id`, `tool_calls.session_id`, `tool_calls.tool_name`, `session_topics.topic`
- **Full-text search** (GIN): `sessions.search_vector`, `segments.search_vector`
- **Vector similarity** (HNSW): `sessions.embedding` with `vector_cosine_ops` (m=16, ef_construction=64)
- **Fuzzy matching** (GIN trigram): `sessions.summary_text` with `gin_trgm_ops`
- **Graphify** (B-tree): `session_concepts.concept_id`, `concepts.community_id`

### Example queries

```sql
-- Full-text search with ranking
SELECT id, project, summary_text,
       ts_rank(search_vector, plainto_tsquery('english', 'docker auth')) AS rank
FROM conversations.sessions
WHERE search_vector @@ plainto_tsquery('english', 'docker auth')
  AND hidden_at IS NULL
ORDER BY rank DESC LIMIT 50;

-- Vector similarity search (cosine)
SELECT id, project, summary_text,
       1 - (embedding <=> $1::vector) AS similarity
FROM conversations.sessions
WHERE embedding IS NOT NULL
  AND hidden_at IS NULL
ORDER BY embedding <=> $1::vector
LIMIT 50;

-- Combined: metadata + full-text
SELECT s.id, s.project, s.estimated_cost,
       ts_rank(s.search_vector, q) AS rank
FROM conversations.sessions s, plainto_tsquery('english', 'refactor') q
WHERE s.search_vector @@ q
  AND s.hidden_at IS NULL
  AND s.provider = 'claude'
  AND s.started_at >= '2026-03-01'
  AND s.project = 'conversations'
ORDER BY rank DESC;
```

### Tool family mapping

```python
TOOL_FAMILIES = {
    'file_ops':   ['Read', 'Edit', 'Write', 'Glob', 'NotebookEdit'],
    'search':     ['Grep', 'Agent'],
    'execution':  ['Bash'],
    'web':        ['WebSearch', 'WebFetch'],
    'planning':   ['TaskCreate', 'TaskUpdate', 'TodoWrite'],
    'other':      [],  # catch-all
}
```

### Session type classification (heuristic)

```python
def classify_session(session, tool_counts, topics):
    if any(t in topics for t in ['docker', 'ci', 'deploy', 'nginx', 'k8s']):
        return 'devops'
    if tool_counts.get('Edit', 0) + tool_counts.get('Write', 0) > 3:
        return 'coding'
    if tool_counts.get('Bash', 0) > 5 and 'error' in session.summary_text.lower():
        return 'debugging'
    if sum(tool_counts.values()) < 3 and session.total_words > 2000:
        return 'planning'
    if tool_counts.get('WebSearch', 0) + tool_counts.get('WebFetch', 0) > 0:
        return 'research'
    if session.turn_count <= 4 and tool_counts.get('Edit', 0) == 0:
        return 'research'
    return 'coding'
```

### Topic extraction (heuristic)

Extracts topics from:
1. **Project name segments** (split on `-` and camelCase)
2. **File paths mentioned** (`.py` → python, `Dockerfile` → docker)
3. **Keyword frequency** in user messages (TF-IDF against corpus, top 3)
4. **Tool-derived signals** (heavy WebSearch → "research", heavy Bash+error → "debugging")

Graphify concepts, when available, merge into `session_topics` with `source='graphify'` and 0.9 confidence — higher than heuristic tags.

---

## 7. Semantic Search Design

### Retrieval approach: hybrid two-stage

```
Query → [Embedding Model]    → Vector similarity (top 50 sessions)
Query → [Keyword / tsvector] → BM25 matches       (top 50 sessions)
                             ↓
                    Reciprocal Rank Fusion (RRF)
                             ↓
                    Final scoring (recency + length + exact match)
                             ↓
                    Optional community re-ranking
                             ↓
                        Top 20 ranked results
```

**Stage 1 — Retrieval (broad recall):**
- **Semantic leg**: `embed_text()` produces a 384-dim vector, `Session.embedding.cosine_distance(query_vector)` ordered ASC, top 50
- **Keyword leg**: PostgreSQL `tsvector`/`tsquery` with `ts_rank` over `segments.search_vector`, grouped by session, top 50
- **Fusion**: RRF (`1 / (k + rank)` with k=60) merges both ranked lists

**Stage 2 — Filter + re-rank:**
- Metadata filters (project, model, date range, tool, topic) applied as SQL WHERE on **both legs** (pushdown for efficiency)
- Final score combines RRF with recency, length, and exact-match signals
- Snippet extraction: tsvector matches get their best-ranked segment; vector-only matches fall back to a scan for query-term context

### Indexing strategy

**Unit of embedding: session (conversation-level), not segment.**

Each session gets one embedding computed from `build_session_text()`:

```
[Project: conversations] [Model: opus] [Tools: Bash, Edit, Read]
[Topics: semantic search, FastAPI, SQLite]
User asked about adding vector search to the conversation browser...
```

~100-200 tokens per session. Generated from `summary_text` + topics + tool names + project + model.

**Why session-level, not chunk-level:**
- Session-level retrieval is the goal, not chunk spam
- Session-level embeddings are 10-50x fewer vectors
- A session-level hit is directly actionable
- Snippet extraction uses a second-pass keyword search within the matched session

### Ranking formula

```python
final_score = (
    0.6 * rrf_normalized        # semantic + keyword fusion, scaled to [0, 1]
  + 0.2 * recency_boost         # 1 / (1 + log(1 + days_ago / 30))
  + 0.1 * length_signal         # min(1, log(1 + total_words) / log(10001))
  + 0.1 * exact_match_bonus     # matches / len(terms)
)

# Optional community boost (Phase 5.4)
if has_graph_data:
    final_score += 0.05 * community_overlap_with_top_result
```

### Metadata filters

| Filter | Type | Example syntax |
|--------|------|----------------|
| `project` | exact match | `project:conversations` |
| `model` | ilike substring | `model:opus` |
| `provider` | enum | `provider:claude` |
| `date_from` / `date_to` | date range | `after:2026-03-01 before:2026-04-01` |
| `tools` | contains any | `tool:Bash,Edit` |
| `topic` | ilike substring | `topic:docker` |
| `min_cost` | threshold | `cost:>5.00` |
| `min_turns` | threshold | `turns:>10` |

### Result presentation

```
┌─────────────────────────────────────────────────────┐
│ #1 ▓▓▓▓▓▓▓▓▓▓ (full bar)                            │
│ [conversations] — 2026-03-28 — opus — $2.14         │
│ "Fixed Docker auth by switching to buildkit          │
│  secrets instead of ARG for the registry token..."   │
│ Tools: Bash(4), Edit(3) · 12 turns · docker          │
├─────────────────────────────────────────────────────┤
│ #2 ▓▓▓▓▓▓ (60% bar)                                 │
│ [deploy-infra] — 2026-03-15 — sonnet — $0.88       │
│ ...                                                  │
└─────────────────────────────────────────────────────┘
```

- **Rank number + relevance bar** — bar width proportional to `score / max_score`
- **Query terms highlighted** with `<mark>` in the snippet
- **Click** navigates to the conversation

### Search mode UI

Two-part status badge in the search bar, polled from `/api/search/status` every 5s until both settle:

| Embeddings | Graph | Badge 1 | Badge 2 |
|------------|-------|---------|---------|
| None | — | **Keyword** (grey) | — |
| In progress | — | **Embedding XX%** (pulsing accent2) | — |
| Complete | Absent | **Hybrid** (accent) | **No Graph** (dim grey) |
| Complete | Present | **Hybrid** (accent) | **Graph** (accent) |

### Failure modes and mitigations

| Failure mode | Mitigation |
|-------------|------------|
| Model download fails | Vector leg try/except; keyword-only fallback; `_embed_new_sessions()` wrapped in non-fatal try/except |
| Specific query ("error code XYZ-123") returns irrelevant results | Keyword leg catches exact matches; exact_match_bonus in ranking |
| Vague query returns too many results | Recency boost + cost/length signals; user can add filters |
| Session-level embedding misses buried detail | Second-pass snippet extraction searches within matched session's segments |
| Embedding model slow on initial build | Background `asyncio.create_task` in startup; incremental thereafter |
| pgvector extension not installed | Not applicable — `CREATE EXTENSION vector` runs on startup |
| No community data | `_community_rerank()` returns `{}` gracefully |
| Session embedding is NULL | `.where(Session.embedding.is_not(None))` in vector query |

---

## 8. KPI Dashboard Design

### Layout

Dashboard is a **separate tab** from conversations (not a mode toggle). Single scrollable page. Dense, no whitespace waste.

### Row 1: Summary cards

```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Sessions │ │ Tokens   │ │ Est.Cost │ │ Avg Cost │ │ Projects │
│   847    │ │  12.4M   │ │  $284    │ │ $0.34/s  │ │    23    │
│ +42/week │ │ +890K/wk │ │ +$18/wk  │ │ ↓12%     │ │ +2/month │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

**Answers:** How much am I using? Is usage trending up or down?

### Row 2: Cost over time (stacked area chart)

- X-axis: weeks (default) or days/months (toggle)
- Y-axis: estimated cost in USD
- Stacked by: project (default) or model or provider
- Hover: tooltip with exact values

**Answers:** Where am I spending the most tokens? What weeks had heaviest usage?

### Row 3: Two-column layout

**Left — Project breakdown (horizontal bar chart):**
- Projects ranked by total cost
- Shows cost, session count, avg cost/session
- Click project → filters dashboard to that project

**Right — Model comparison (grouped bar chart):**
- Claude Opus vs Claude Sonnet vs Codex models
- Bars: total cost, total sessions
- Side-by-side grouped bars

### Row 4: Two-column layout

**Left — Tool usage (horizontal bars):**
- Tools ranked by call count
- Grouped by family (file_ops, search, execution, web, planning, other)
- Percentage of sessions using each tool

**Right — Session type distribution (donut chart + table):**
- Auto-classified: Coding, Debugging, Planning, Research, Writing, DevOps
- Shows: count, % of total, avg cost per type

### Row 5: Efficiency / anomaly table

Flags:
- **High cost**: >2σ above mean cost for session length
- **Many retries**: >3 consecutive similar Bash commands (loop detection)
- **Long tail**: >40 turns with decreasing new content

Table omitted entirely when no anomalies exist.

### Row 6: Activity heatmap

- GitHub-style contribution heatmap (52 weeks × 7 days)
- Color intensity = cost (not just session count)
- Hover shows: date, session count, total cost

### Global filters

- Date range presets (7d, 30d, 90d, All)
- Provider: Claude / Codex / All
- Project: dropdown
- Model: dropdown

### Interactive behavior

- Click any chart element → filters the dashboard to that dimension
- Click a session in the anomaly table → opens it in the conversations tab
- All charts update together when filters change (coordinated views)

### Knowledge Graph tab

The Knowledge Graph is its own full-screen tab (not a dashboard row). d3 force-directed layout with:
- **Community coloring** — same Leiden community = same color
- **Degree-based sizing** — larger nodes = more connections
- **Co-occurrence edges** — thicker = more shared sessions
- **Interactive settings panel** (cog icon): center force, repel force, repel range, link force, link distance, collision pad, label threshold, color scheme
- **Settings persist in localStorage**
- **Click node** → switches to conversations tab with `topic:<name>` search
- **Regenerate button** → triggers host-side watcher to re-extract

---

## 9. Graphify Enrichment Layer

[Graphify](https://github.com/safishamsi/graphify) (`graphifyy` package) transforms folders of mixed-media content into queryable knowledge graphs. It extracts named concepts and relationships from each file, labels edges (EXTRACTED / INFERRED / AMBIGUOUS), and runs Leiden community detection.

Runs as an **optional sidecar**. Every feature degrades gracefully when Graphify output is absent.

### What it provides

1. **Richer topic extraction.** Graphify concepts merge into `session_topics` with `source='graphify'` and 0.9 confidence — higher than heuristic tags. The heuristic covers sessions Graphify might miss; Graphify provides depth where it runs.

2. **"Related sessions" discovery.** `/api/sessions/{id}/related` endpoint finds sessions sharing concept nodes, ranked by shared concept count. Returns `[]` gracefully when no concept data exists.

3. **Corpus-level structural overview.** `graphify-out/GRAPH_REPORT.md` and `graph.html` give a bird's-eye view — god nodes, community clusters, cross-project connections.

4. **Community-based re-ranking signal** (Phase 5.4). Leiden community overlap with the top-ranked result awards `+0.05 * overlap_count` to other candidates.

### Extraction pipeline

```
markdown/*.md
  → graph_extract.py (condenses + calls claude -p --system-prompt)
  → .graphify_chunk_*.json (cached per-file, skips already-extracted on re-run)
  → graphifyy build_from_json + cluster + to_json
  → graphify-out/graph.json
  → import_graph.py
  → Postgres: concepts + session_concepts + merge to session_topics
```

Key design:
- **`--system-prompt` architecturally separates** extraction instructions from document content, preventing Claude from treating conversation markdown as a conversation to continue
- **Markdown condensation** (strip assistant responses, tool output, code blocks) reduces 29MB files to ~165KB, making extraction reliable on all file sizes
- **Chunk cache** in `.graphify_chunk_*.json` — subsequent runs skip already-extracted files
- **Host-side watcher** (via launcher) — calls the claude CLI from outside the container, polls `.generate_requested` for dashboard-triggered regeneration

### Integration points

| Phase | Step | What happens |
|-------|------|-------------|
| 1 (Data Loader) | 1.5 | `import_graph.py` reads `graphify-out/graph.json`, maps nodes to sessions by file path, populates `concepts` and `session_concepts`. Skipped if absent. |
| 1.2 (Topics) | merge | Graphify concepts merge into `session_topics` with `source='graphify'` marker. |
| 3 (Search) | 3.4 | "Related sessions" query — find sessions sharing concept nodes. |
| 4 (Dashboard) | 4.2 | Full-screen Knowledge Graph tab with d3 force-directed visualization. |
| 5 (Semantic) | 5.4 | Leiden `community_id` used as optional re-ranking signal in hybrid retrieval. |

### Constraints

- `graphifyy` is in `browser/backend/requirements.txt` and available inside the app container
- The app must produce a fully working system even if Graphify produces no output
- `graphify-out/` is gitignored and regenerated on demand
- `import_graph.py` is idempotent — safe to re-run

---

## 10. Phased Migration Plan

Phased refactoring from in-memory index to PostgreSQL. Each phase produces a working system. No phase breaks existing functionality.

### Phase 0 — Scaffolding ✅

**Status: COMPLETE**

**What was built:**
- PostgreSQL 16 (`pgvector/pgvector:pg16`) added to `docker-compose.yml` with healthcheck, `pgdata` volume, `depends_on` with `service_healthy` condition
- `DATABASE_URL=postgresql+asyncpg://conversations:conversations@postgres:5432/conversations` wired into `llm-browser` service
- Backend split into modular routes: `index_store.py` + `routes/` (projects, segments, conversations, stats, summaries, visibility)
- SQLAlchemy 2.0 async declarative models (`models.py`) define all 7 tables in the `conversations` schema
- Pydantic v2 API schemas (`schemas.py`) with `from_attributes=True`
- `db.py` with SQLAlchemy async engine + `async_sessionmaker` + `init_db()` that creates extensions, schema, and tables on app startup
- Requirements: `sqlalchemy[asyncio]`, `asyncpg`, `pydantic`, `pgvector`

**Architectural decision:** SQLAlchemy 2.0 async + asyncpg + Pydantic v2 instead of raw psycopg + SQL files. All tables in `conversations` schema (not `public`). Schema managed by Python models via `Base.metadata.create_all()` on startup — no SQL migration files.

**Deliverable:** Postgres running, schema created, backend modular, connection pool exists. Zero behavior changes. Frontend untouched.

---

### Phase 1 — Data Loader ✅

**Status: COMPLETE**

**What was built:**
- `jsonl_reader.py` — extracts model names + actual token usage (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) from raw Claude JSONL files. Codex: extracts `model_provider` only.
- `load.py` — async data loader merging `parser.py` markdown output with `jsonl_reader.py` metadata. Groups segments into sessions by `conversation_id`. Upserts via SQLAlchemy `pg_insert` with `on_conflict_do_update`. Computes `estimated_cost` from actual tokens × model pricing (cache read tokens at 10% of input price).
- `topics.py` — heuristic topic extraction from project name, file extensions, keyword matching, tool-derived signals. Returns up to 5 `(topic, confidence)` tuples per session.
- `classify.py` — heuristic session type classification into coding/debugging/planning/research/writing/devops.
- `import_graph.py` — Graphify concept graph import. Failures are non-fatal.
- `app.py` — `run_export_pipeline()` is now `async`, calls `load_all()` after rebuilding the in-memory index. Postgres sync failures are non-fatal.

**Key decisions:**
- Markdown parsers (`convert_claude_jsonl_to_md.py`, `convert_codex_sessions.py`) are **not replaced** — they are the source of truth for conversation structure. `jsonl_reader.py` only supplements metadata (model, tokens) that markdown doesn't preserve.
- All DB writes use PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` for idempotency.
- Tool calls are delete-and-reinsert per session (no natural unique key).

**Deliverable:** Postgres has all the data. Queryable with `psql`. App still serves from in-memory index. Nothing broken.

---

### Phase 2 — Migrate Reads ✅

**Status: COMPLETE**

**What was built:**
- All route modules rewritten to read from Postgres via SQLAlchemy async queries with `Depends(get_db)`.
- All endpoints are `async def` with `AsyncSession` injection.
- Queries use `select(Segment, Session).join(Session)` tuple pattern to avoid lazy-loading `MissingGreenlet` errors in async context.
- Hidden state migrated from file-based `state.py` to `hidden_at` columns via `UPDATE` statements.
- Search upgraded from substring matching to PostgreSQL `tsvector`/`ts_rank` full-text search.
- Summary endpoints migrated segment lookups to Postgres; filesystem-based summary pipeline unchanged.
- `load_all()` runs on app startup in the lifespan — no need to manually trigger `/api/update`.
- In-memory index still exists for the export pipeline but no longer read by any route module.

**Key implementation details:**
- Avoided `selectinload`/relationship lazy loading entirely — all queries that need Session fields select `(Segment, Session)` as a tuple.
- Timestamp serialization uses `.isoformat().replace("+00:00", "Z")` to match the ISO 8601 format the frontend expects.
- Tool call counts computed via separate `COUNT` queries since segments don't store `tool_call_count` directly.

**Deliverable:** All API reads from Postgres. Frontend unchanged. Search ranked via tsvector. Hidden state in database.

---

### Phase 3 — Search Upgrade ✅

**Status: COMPLETE**

**What was built:**
- `search.py` — filter parser with `ParsedQuery` and `SearchFilters` Pydantic models. Parses structured query syntax mixed with free text. Malformed filter values are left in the free-text query (no crash).
- `/api/search` rewritten for session-level results: searches segments via tsvector, groups by session, picks best-matching segment as snippet, applies metadata filters as SQL WHERE clauses.
- `/api/search/filters` — distinct values for autocomplete.
- `/api/sessions/{session_id}/related` — finds sessions sharing Graphify concept nodes. Returns `[]` when no concept data exists.
- `SearchResults.jsx` — session-level search result cards with query term highlighting.
- `FilterChips.jsx` — filter chip buttons with autocomplete dropdowns.
- `App.jsx` updated for session-level flow. `App.css` extended with new styles.

**Key design decisions:**
- Search response shape changed from segment-level to session-level — the first breaking API change.
- Filter-only queries (no free text) return sessions matching metadata filters ordered by recency.
- Snippet extraction centers a ~250-char window around the first query term, stripping markdown noise.

**Deliverable:** Ranked session-level search with metadata filters. Session cards, filter chips with autocomplete, click-to-navigate. Related sessions endpoint.

---

### Phase 4 — Dashboard ✅

**Status: COMPLETE**

**What was built:**

**4.1 Dashboard API endpoints:**
- `routes/dashboard.py` — 9 dashboard endpoints: summary, cost-over-time, projects, tools, models, session-types, heatmap, anomalies. All accept global filter params (`date_from`, `date_to`, `provider`, `project`, `model`). All data from SQL aggregations.
- 3 graph endpoints: `GET /api/dashboard/graph`, `GET /api/dashboard/graph/status`, `POST /api/dashboard/graph/generate`, `POST /api/dashboard/graph/import`.

**4.2 Frontend 3-tab system:**
- Conversations / Dashboard / Knowledge Graph tabs in the header
- `Dashboard.jsx` — summary cards, cost-over-time, project breakdown, tool usage, model comparison, session type distribution, activity heatmap, anomaly table
- Global filter bar with date presets, project/model dropdowns, click-to-filter
- `KnowledgeGraph.jsx` — self-contained tab with graph status polling, auto-import, regenerate button
- `ConceptGraph.jsx` — d3 force layout with interactive settings panel, `localStorage` persistence
- Startup loading screen (`/api/ready` polling)

**4.3 Concept graph extraction pipeline:**
- `graph_extract.py` — condenses markdown → `claude -p --system-prompt` → `graphifyy build + cluster`
- `graph_watcher.bat` — Windows companion
- Launchers auto-start the watcher

**Key design decisions:**
- Knowledge Graph is its own tab (not embedded in dashboard) — gives it full-screen space
- Concept extraction uses `--system-prompt` to architecturally separate instructions from document content
- Markdown condensation (strip assistant responses, tool output, code blocks) reduces 29MB files to ~165KB
- d3 force settings persist in `localStorage`
- Graph auto-generates on service startup; re-generation via dashboard button

**New dependencies:** `chart.js`, `react-chartjs-2`, `d3` in frontend.

**Deliverable:** Full KPI dashboard with 6 chart types + heatmap + anomaly table + global filters. Full-screen knowledge graph with interactive force settings. Automated concept extraction pipeline.

---

### Phase 5 — Semantic Search ✅

**Status: COMPLETE**

**What was built:**

**5.1 Embedding pipeline:**
- `browser/backend/embed.py` — lazy-loads `sentence-transformers/all-MiniLM-L6-v2` via `huggingface_hub` on first use (downloads `tokenizer.json` + `onnx/model.onnx`, ~90MB, cached for container lifetime). `embed_text(text) -> list[float]` runs ONNX inference with mean-pooling + L2 normalization, returns 384-dim vector. `build_session_text(project, model, summary_text, topics, tools)` builds the compressed session representation.
- `browser/backend/load.py` — `_embed_new_sessions()` queries for sessions where `embedding IS NULL`, batch-fetches topics + tools (3 queries total regardless of session count), embeds, stores via `update(Session).values(embedding=vector)`. Commits every 100 sessions. Wrapped in try/except in `load_all()` — non-fatal if model download fails.
- Dependencies: `onnxruntime>=1.17`, `tokenizers>=0.19`, `huggingface-hub>=0.23`, `numpy>=1.26`. Dockerfile installs `libgomp1` (required by onnxruntime, missing from `python:3.13-slim`).

**5.2 Hybrid retrieval:**
- `routes/segments.py` `api_search()` rewritten. When free text is present: keyword leg (tsvector, top 50) + vector leg (`Session.embedding.cosine_distance(query_vector)`, top 50). Both legs respect metadata filters via `_apply_filters()` helper.
- `_rrf_merge()` — RRF with k=60, normalized to [0, 1]
- Final scoring: `0.6 * rrf + 0.2 * recency_boost + 0.1 * length_signal + 0.1 * exact_match_bonus`
- Helpers: `_recency_boost()` with log-decay, `_length_signal()` log-scaled word count, `_exact_match_bonus()` fraction of query terms in summary
- Snippet fallback for vector-only results
- Results capped at top 20 (was 50 in Phase 3)

**5.3 Frontend relevance indicator + search mode badges:**
- `SearchResults.jsx` — rank number (`#1`, `#2`, ...) and a thin horizontal bar proportional to `score / max_score`
- `App.jsx` — two-part search mode indicator. Badge 1: Keyword / Embedding XX% / Hybrid. Badge 2: Graph / No Graph. Polls `/api/search/status` every 5s until both settle.
- `routes/segments.py` `GET /api/search/status` — returns `{ mode, total_sessions, embedded_sessions, has_graph, concept_count }`
- `App.css` — translucent badge backgrounds via `color-mix(in srgb, var(--accent) 15%, transparent)`

**5.4 Community-based re-ranking:**
- `_community_rerank()` — after base scoring, queries `session_concepts → concepts` for candidates, identifies top-ranked session's Leiden communities, awards `+0.05 * overlap_count` to others sharing communities. Returns `{}` when no community data exists.
- `COMMUNITY_BOOST_COEFFICIENT = 0.05` — tunable module constant

**Operational improvements landed with Phase 5:**
- Timestamped logs (`[HH:MM:SS]` prefix) via `_log()` helpers in `load.py`, `app.py`, `graph_extract.py`
- `export_service.sh` adds `echo` after `read -rp` for clean separation
- `export_service.bat` brought to parity with `.sh`: Codex sessions export, `stop_graph_watcher` on `v` option, `echo.` after `set /p`

**Key design decisions:**
- Embedding runs as background during startup (`asyncio.create_task`) — app serves requests immediately with keyword-only fallback while embeddings populate
- Model download happens on first call inside the container, not during Docker build
- RRF scores normalized to [0, 1] before weighted combination (raw RRF values would be swamped by recency/length/exact-match signals otherwise)
- Community re-ranking uses `dict[str, float]` for additive boosts before final sort

**Deliverable:** Hybrid semantic + keyword search. Graceful degradation across all failure modes. Two-part UI indicator.

---

### Phase 6 — Cleanup, Testing & CI

**Goal:** Remove dead code, add comprehensive test coverage, set up CI pipeline, then refactor to OOP with the test suite as a safety net. **Final phase — project completion.**

**Execution order:** 6.1–6.4 (cleanup, done) → 6.5–6.6 (tests) → 6.7 (CI) → 6.8 (OOP refactor, done last under test + CI protection) → 6.9 (docs). Tests are written against the current functional architecture so they capture real behavior; 6.8 then refactors under that safety net.

#### 6.1 Remove in-memory index code ✅
- Deleted `index_store.py`; removed `INDEX`/`CODEX_INDEX`, `init_indexes`, `rebuild_index` from `app.py`
- Removed `_watch_loop`, `_get_dir_mtime`, `WATCH_INTERVAL` config, and `watch_interval` field from `/api/stats`
- `run_export_pipeline` no longer touches the in-memory index; reports Postgres session counts
- `parser.py` stayed — `load.py` still uses `build_index()` to parse markdown

#### 6.2 Remove file-based hidden state ✅
- Deleted `state.py` (hidden state lives in `sessions.hidden_at` / `segments.hidden_at` since Phase 2)
- No imports remained; removal was purely dead-code deletion

#### 6.3 Clean up docker-compose.yml ✅
- Narrowed `./browser_state:/data/state` to `./browser_state/summaries:/data/state/summaries` — only the AI summary cache remains file-based
- Renamed env var `STATE_DIR` → `SUMMARY_DIR`; simplified the path join in `routes/summaries.py`

#### 6.4 Update export_service.sh / .bat ✅
- Added `sync_postgres` helper in both launchers — polls `/api/ready` then runs `docker compose exec -T llm-browser python /app/load.py`
- Invoked after initial `up --build -d` and inside the `[r]` restart branch
- Replaces file-watch-based reindexing removed in 6.1

#### 6.5 Unit + integration tests (backend)
Add `pytest` + `pytest-asyncio` + `pytest-cov` in `browser/backend/tests/`.

**Unit tests (mocked DB):**
- `test_search.py` — `parse_query()` for every filter prefix, combined filters, malformed values, edge cases
- `test_topics.py`, `test_classify.py` — heuristic extraction/classification

**Integration tests (real Postgres via testcontainer):**
- `test_api_search.py`, `test_api_filters.py`, `test_api_related.py`
- `test_api_projects.py`, `test_api_segments.py`, `test_api_conversations.py`
- `test_api_visibility.py`, `test_api_stats.py`
- `test_api_dashboard.py` — all dashboard endpoints
- `test_load.py` — idempotent re-run verification
- `test_embed.py` — embedding pipeline unit tests
- `test_hybrid_search.py` — RRF fusion, scoring formula, community re-ranking

**Test infrastructure:**
- `conftest.py` — async test fixtures, Postgres testcontainer, deterministic test data seeding
- Coverage target: **100%** on `search.py`, `topics.py`, `classify.py`, `embed.py`. `pragma: no cover` only on startup/lifespan glue.
- Tests target the current functional route handlers so they capture pre-refactor behavior as the contract for 6.8.

#### 6.6 Frontend tests
Add `vitest` + `@testing-library/react` in `browser/frontend/src/__tests__/`.

- `SearchResults.test.jsx` — session cards, highlighting, click handler, empty state
- `FilterChips.test.jsx` — chip rendering, dropdown, filter add/remove
- `App.test.jsx` — integration: search flow, provider switch, filter bar
- `utils.test.js` — formatters
- `tests/setup.js` — import `cleanup` from `@testing-library/react`, call in `afterEach` (Vitest does NOT auto-cleanup)

#### 6.7 GitHub Actions CI
This project is intentionally on **GitHub** (public, open-source) rather than the global-default GitLab — explicit per-project override of the global CLAUDE.md's GitLab mandate.

`.github/workflows/ci.yml` with stages (in order):
1. **lint** — `ruff check .` for backend, `pnpm lint` for frontend
2. **test-backend** — Postgres service container, `pytest --cov --cov-report=xml`
3. **test-frontend** — `pnpm test -- --coverage`
4. **coverage-gate** — fail if coverage drops below threshold (target 100%, pragmatic starting gate 90%)
5. **build-frontend** — `pnpm build`
6. **docker-build** — `docker build` against Dockerfile

**Triggers:** push to `main`, PRs to `main`.
**Release pipeline:** manually triggered on `main` with `BUMP` variable (patch/minor/major) — bumps `package.json` + `pyproject.toml` versions.

CI must be green before 6.8 begins — the refactor needs both the test suite and the automated gate.

#### 6.8 OOP refactoring
Refactor to proper OOP patterns under the 6.5–6.7 safety net. Current state is functional — route handlers with inline query logic, helper functions scattered. Target state:
- **Service layer classes**: `SearchService`, `SessionService`, `LoaderService`, `SummaryService`
- **Repository pattern**: `browser/backend/repositories/` — one per model
- **Dependency injection**: services instantiated with repositories, injected via FastAPI `Depends()`
- **Thin route handlers**: parse params, call service, return response. No query logic in routes.
- **One class per file** per project conventions
- Coverage target extended to 100% on service classes and repositories once they exist.

This is a refactor, not a rewrite. The test suite from 6.5–6.6 validates no behavior changes; CI enforces it. If any test fails during the refactor, the refactor is wrong — not the test.

#### 6.9 Update documentation
- Update this master plan to reflect final architecture
- Update README.md with testing section, CI badge, architecture diagram
- Mark all Phase 6 rows complete in this document

**Deliverable:** No legacy code. OOP architecture with service/repository layers. Full test suite. GitHub Actions CI enforcing lint, tests, coverage, build, and Docker build. **Project complete.**

---

## 11. Phase Summary Table

| Phase | Status | What changes | What breaks | Frontend changes |
|-------|--------|-------------|-------------|------------------|
| 0 — Scaffolding | ✅ Done | Postgres running, SQLAlchemy models, Pydantic schemas, backend split into modules | Nothing | None |
| 1 — Data Loader | ✅ Done | Postgres populated, topics + types extracted, optional Graphify concept import | Nothing | None |
| 2 — Migrate Reads | ✅ Done | All API reads from Postgres via SQLAlchemy. Search upgraded to tsvector ranking. Hidden state in DB. | Nothing (same JSON shapes) | None |
| 3 — Search Upgrade | ✅ Done | Session-level search with metadata filter parsing, filter chips with autocomplete, related sessions endpoint | Search results shape changed (session-level) | Session cards, filter chips, autocomplete dropdowns |
| 4 — Dashboard | ✅ Done | KPI dashboard (6 charts + heatmap + anomalies), Knowledge Graph tab (d3 force layout + settings), automated concept extraction pipeline | Nothing | Dashboard, KnowledgeGraph, ConceptGraph, Heatmap components; Chart.js + d3 deps |
| 5 — Semantic Search | ✅ Done | Vector embeddings (all-MiniLM-L6-v2 ONNX) + hybrid retrieval (RRF + recency/length/exact-match) + community-based re-ranking. Search mode + graph badges in UI. Timestamped launcher logs. | Nothing | Relevance bar per result, search mode + graph badges in search bar |
| 6 — Cleanup, Testing & CI | 🟡 In progress (6.1–6.4 done) | Dead code removed (6.1–6.4 ✅), full test suite (pytest + vitest) → GitHub Actions CI → OOP refactor last under test/CI safety net → docs | Nothing | None (internal quality) |

Every phase produces a working system. Phases 0-2 invisible to the frontend. Phase 3 is the first user-visible improvement (session-level search + filters). Phase 4 is the second (dashboard + concept graph). Phase 5 is the third (semantic search). Phase 6 is the capstone (code quality, tests, CI). **Phase 6 completes the project.**

---

## 12. Anti-Bloat Guardrails

Reject these unless a strong, specific use case emerges:

| Tempting Feature | Why to Reject |
|-----------------|---------------|
| LLM-powered query expansion | Embedding model already handles semantic matching. LLM call per search is slow and expensive for marginal gain. |
| Conversation clustering / auto-grouping | Topics + project already provide grouping. Clustering adds complexity without clear UI value. |
| Multi-user support | Personal tool. |
| Real-time ingest / streaming | Batch is fine. Review happens after conversations end. |
| Natural language dashboard queries | Filters do this faster and more reliably. |
| Conversation diff / comparison view | Museum feature. |
| Export to Notion/Obsidian/etc. | Learnings are documented in projects already. |
| Custom dashboards / widget builder | One good default dashboard beats a configurable one. |
| Elaborate AI re-summarization | Current summaries work. Improving them is diminishing returns. |
| Per-turn cost attribution | Token estimates at session level are sufficient. |
| Tagging UI | Auto-classification is enough. |
| Full-text indexing of tool outputs | Massive index bloat for rare recall value. Search user/assistant messages only. |
| Per-conversation notes/annotations | User doesn't revisit conversations in detail. |
| Session replay / timeline view | Museum feature. |
| Manual tagging | User won't do it. |

Every feature must justify itself as: **faster recall OR faster pattern understanding**.

---

## 13. QA / UAT Test Plan

Living section. Updated as each phase lands. Run the full plan after every phase delivery to catch regressions. All tests assume the app is running at `http://localhost:5050` via Docker (`r + Enter` in launcher).

**How to use:**
- **After any phase delivery:** Run every section top to bottom. Sections are cumulative.
- **Quick smoke test:** Run Section 13.1 (backend curl) and Section 13.8 (regression table). If those pass, the system is healthy.
- **Before committing:** Run Section 13.1 + the section for the phase you just built + Section 13.8 regression.

**Legend:**
- (P0-P2) = delivered in Phases 0-2
- (P3) = delivered in Phase 3
- (P4) = delivered in Phase 4
- (P5) = delivered in Phase 5

### 13.1 Backend API smoke tests (curl)

#### 13.1.1 App health
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5050/
```
**Expected:** `200`. If not, check `docker compose logs llm-browser`.

#### 13.1.2 Providers (P0)
```bash
curl -s "http://localhost:5050/api/providers" | python3 -m json.tool
```
**Expected:** Array with at least one object: `{ "id": "claude", "name": "Claude", "projects": <N> }`.

#### 13.1.3 Projects list (P0)
```bash
curl -s "http://localhost:5050/api/projects?provider=claude" | python3 -m json.tool | head -20
```
**Expected:** Array of project objects with `name`, `display_name`, `total_requests`, `stats`.

#### 13.1.4 Project segments (P0)
```bash
curl -s "http://localhost:5050/api/projects/<PROJECT>/segments?provider=claude" | python3 -m json.tool | head -20
```
**Expected:** Array of segment objects with `id`, `source_file`, `project_name`, `segment_index`, `preview`, `timestamp`, `conversation_id`, `metrics`.

#### 13.1.5 Segment detail (P0)
```bash
curl -s "http://localhost:5050/api/segments/<SEGMENT_ID>?provider=claude" | python3 -m json.tool | head -10
```
**Expected:** Full segment with `raw_markdown`, `tool_breakdown`, `metrics`.

#### 13.1.6 Conversation view (P0)
```bash
curl -s "http://localhost:5050/api/projects/<PROJECT>/conversation/<CONVERSATION_ID>?provider=claude" | python3 -m json.tool | head -10
```
**Expected:** Object with `conversation_id`, `project_name`, `segment_count`, `raw_markdown`, `metrics`.

#### 13.1.7 Stats (P0)
```bash
curl -s "http://localhost:5050/api/stats?provider=claude" | python3 -m json.tool
```
**Expected:** Object with `total_projects`, `total_segments`, `total_words`, `estimated_tokens`, `total_tool_calls`, `monthly`, `hidden`.

#### 13.1.8 Search — session-level results (P3)
```bash
curl -s "http://localhost:5050/api/search?q=docker" | python3 -m json.tool | head -30
```
**Expected:** Array of session-level objects with keys: `session_id`, `project`, `date`, `model`, `cost`, `snippet`, `tool_summary`, `tools`, `turn_count`, `topics`, `conversation_id`, `rank`.

**Failure indicator:** Old segment-level shape with `id`, `segment_index`, `preview`, `metrics`.

#### 13.1.9 Search — empty/short query (P3)
```bash
curl -s "http://localhost:5050/api/search?q=a"
curl -s "http://localhost:5050/api/search?q="
```
**Expected:** `[]` for both.

#### 13.1.10 Search — project filter (P3)
```bash
curl -s "http://localhost:5050/api/search?q=project:conversations+docker" | python3 -m json.tool
```
**Expected:** All results have `"project": "conversations"`. Snippet/rank reflects "docker".

#### 13.1.11 Search — tool filter (P3)
```bash
curl -s "http://localhost:5050/api/search?q=tool:Bash+error" | python3 -m json.tool
```
**Expected:** Every result's `tools` object contains a `"Bash"` key.

#### 13.1.12 Search — date range (P3)
```bash
curl -s "http://localhost:5050/api/search?q=after:2026-03-01+before:2026-04-01" | python3 -m json.tool
```
**Expected:** All results have `date` between 2026-03-01 and 2026-04-01 inclusive.

#### 13.1.13 Search — cost threshold (P3)
```bash
curl -s "http://localhost:5050/api/search?q=cost:>1.00" | python3 -m json.tool
```
**Expected:** All results have `cost > 1.00`.

#### 13.1.14 Search — turns threshold (P3)
```bash
curl -s "http://localhost:5050/api/search?q=turns:>10" | python3 -m json.tool
```
**Expected:** All results have `turn_count > 10`.

#### 13.1.15 Search — multiple filters combined (P3)
```bash
curl -s "http://localhost:5050/api/search?q=project:conversations+tool:Edit+after:2026-01-01+refactor" | python3 -m json.tool
```
**Expected:** Results match ALL filters simultaneously.

#### 13.1.16 Search — model filter (P3)
```bash
curl -s "http://localhost:5050/api/search?q=model:opus" | python3 -m json.tool
```
**Expected:** Results where the model field contains "opus" (case-insensitive).

#### 13.1.17 Search — topic filter (P3)
```bash
curl -s "http://localhost:5050/api/search?q=topic:docker" | python3 -m json.tool
```
**Expected:** Results where at least one session topic contains "docker".

#### 13.1.18 Search — malformed filter is non-fatal (P3)
```bash
curl -s "http://localhost:5050/api/search?q=after:not-a-date+docker" | python3 -m json.tool
```
**Expected:** No crash. `after:not-a-date` left in free text.

#### 13.1.19 Autocomplete endpoint (P3)
```bash
curl -s "http://localhost:5050/api/search/filters?provider=claude" | python3 -m json.tool
```
**Expected:** `{ "projects": [...], "models": [...], "tools": [...], "topics": [...] }`. All arrays non-empty and alphabetically sorted.

#### 13.1.20 Related sessions endpoint (P3)
```bash
SESSION_ID=$(curl -s "http://localhost:5050/api/search?q=docker" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r[0]['session_id'] if r else '')")
curl -s "http://localhost:5050/api/sessions/${SESSION_ID}/related" | python3 -m json.tool
```
**Expected:** Array of 0-5 objects with `session_id`, `project`, `date`, `model`, `summary`, `shared_concepts`, `conversation_id`. Returns `[]` if no Graphify concept data exists.

#### 13.1.21 Provider filter on search (P3)
```bash
curl -s "http://localhost:5050/api/search?q=docker&provider=codex" | python3 -m json.tool
```
**Expected:** Only codex results (or `[]` if no codex data matches).

#### 13.1.22 Hide/restore segment (P2)
```bash
curl -s -X POST "http://localhost:5050/api/hide/segment/<SEGMENT_ID>" | python3 -m json.tool
curl -s -X POST "http://localhost:5050/api/restore/segment/<SEGMENT_ID>" | python3 -m json.tool
```
**Expected:** Both return success. Segment `hidden_at` is set then cleared.

#### 13.1.23 Update pipeline (P1)
```bash
curl -s -X POST "http://localhost:5050/api/update" | python3 -m json.tool
```
**Expected:** `{ "success": true, "projects": N, "segments": N, "log": [...] }`. Takes 10-60s depending on data volume.

#### 13.1.24 Dashboard summary (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/summary?provider=claude" | python3 -m json.tool
```
**Expected:** Object with `total_sessions` (int >0), `total_tokens` (int), `total_cost` (float), `avg_cost_per_session` (float), `project_count` (int), `deltas` object.

#### 13.1.25 Dashboard cost-over-time (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/cost-over-time?provider=claude&group_by=week&stack_by=project" | python3 -m json.tool | head -30
```
**Expected:** Array of `{ "period": "YYYY-WNN", "stacks": { "<project>": <cost>, ... } }`. Periods in chronological order.

Also test: `group_by=day` (period format `YYYY-MM-DD`), `group_by=month` (period format `YYYY-MM`), `stack_by=model`, `stack_by=provider`.

#### 13.1.26 Dashboard projects (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/projects?provider=claude" | python3 -m json.tool
```
**Expected:** Array sorted by `total_cost` descending. Each object: `project`, `total_cost`, `session_count`, `avg_cost_per_session`.

#### 13.1.27 Dashboard tools (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/tools?provider=claude" | python3 -m json.tool
```
**Expected:** Array sorted by `call_count` descending. Each object: `tool_name`, `call_count`, `session_count`, `family`.

Verify: `Read` → `file_ops`, `Bash` → `execution`, `Grep` → `search`, `WebSearch` → `web`.

#### 13.1.28 Dashboard models (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/models?provider=claude" | python3 -m json.tool
```
**Expected:** Array of `{ "model", "total_sessions", "total_cost", "avg_tokens_per_session" }`. Sorted by cost descending.

#### 13.1.29 Dashboard session-types (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/session-types?provider=claude" | python3 -m json.tool
```
**Expected:** Array of `{ "session_type", "count", "percentage", "avg_cost" }`. Percentages sum to ~100.

#### 13.1.30 Dashboard heatmap (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/heatmap?provider=claude" | python3 -m json.tool | head -20
```
**Expected:** Array of `{ "date": "YYYY-MM-DD", "sessions": N, "cost": N.NN }`. Chronological order. Up to 365 days.

#### 13.1.31 Dashboard anomalies (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/anomalies?provider=claude" | python3 -m json.tool
```
**Expected:** Array of `{ "session_id", "project", "date", "turns", "tokens", "cost", "conversation_id", "flag" }`. All entries above 2-sigma threshold. May be empty.

#### 13.1.32 Dashboard graph (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/graph?provider=claude" | python3 -m json.tool | head -30
```
**Expected:** `{ "nodes": [...], "edges": [...] }`. If no Graphify data, both arrays empty. If present: nodes have `id`, `name`, `type`, `community_id`, `degree`, `session_count`; edges have `source`, `target`, `weight`.

#### 13.1.33 Dashboard graph status + import (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/graph/status" | python3 -m json.tool
curl -s -X POST "http://localhost:5050/api/dashboard/graph/generate" | python3 -m json.tool
curl -s -X POST "http://localhost:5050/api/dashboard/graph/import" | python3 -m json.tool
```
**Expected:** Status returns `{ "status": "ready"|"generating"|"none"|"error", "has_data": bool, "progress": {...}|null }`. Generate returns `{ "status": "generating" }`. Import returns `{ "ok": true }` or `{ "ok": false, "error": "..." }`.

#### 13.1.34 Dashboard global filters (P4)
```bash
curl -s "http://localhost:5050/api/dashboard/summary?provider=claude&project=conversations" | python3 -m json.tool
curl -s "http://localhost:5050/api/dashboard/projects?provider=claude&date_from=2026-03-01&date_to=2026-04-01" | python3 -m json.tool
curl -s "http://localhost:5050/api/dashboard/tools?provider=claude&model=opus" | python3 -m json.tool
```
**Expected:** Each returns filtered data. Project filter: `project_count` = 1. Date filter: only sessions in range. Model filter: only tool calls from sessions using that model.

#### 13.1.35 Search status (P5)
```bash
curl -s "http://localhost:5050/api/search/status?provider=claude" | python3 -m json.tool
```
**Expected:** `{ "mode": "keyword"|"embedding"|"hybrid"|"unavailable", "total_sessions": N, "embedded_sessions": N, "has_graph": bool, "concept_count": N }`.

- Immediately after wiping the DB: `"mode": "unavailable"` or `"keyword"`
- While embeddings generate: `"mode": "embedding"` with `embedded_sessions < total_sessions`
- After embeddings finish: `"mode": "hybrid"` with `embedded_sessions == total_sessions`

#### 13.1.36 Hybrid search response (P5)
```bash
curl -s "http://localhost:5050/api/search?q=vector+embeddings" | python3 -m json.tool | head -40
```
**Expected:** Session-level results with `rank` field reflecting the final score (0.6*rrf + 0.2*recency + 0.1*length + 0.1*exact_match). Results should show semantic matches even when exact keywords aren't present — e.g., a session about "cosine distance" might rank if the query is "vector similarity".

#### 13.1.37 Hybrid search falls back gracefully (P5)
```bash
# If embeddings haven't been generated yet, vector leg should fail silently
# and results should still come from tsvector
curl -s "http://localhost:5050/api/search?q=docker" | python3 -m json.tool | head -20
```
**Expected:** Still returns results (keyword-only fallback). No 500 error.

### 13.2 SQL verification (psql)

Connect:
```bash
docker exec -it conversations-postgres psql -U conversations -d conversations
```

#### 13.2.1 Core table row counts (P1)
```sql
SELECT 'sessions' AS tbl, count(*) FROM conversations.sessions
UNION ALL SELECT 'segments', count(*) FROM conversations.segments
UNION ALL SELECT 'tool_calls', count(*) FROM conversations.tool_calls
UNION ALL SELECT 'session_topics', count(*) FROM conversations.session_topics;
```
**Expected:** Non-zero counts for all four.

#### 13.2.2 tsvector index exists and works (P2)
```sql
SELECT s.id, s.session_id,
       ts_rank(s.search_vector, plainto_tsquery('english', 'docker')) AS rank
FROM conversations.segments s
WHERE s.search_vector @@ plainto_tsquery('english', 'docker')
ORDER BY rank DESC LIMIT 5;
```
**Expected:** Rows ranked by relevance. If zero rows, try a different term.

#### 13.2.3 Session grouping for search (P3)
```sql
SELECT seg.session_id,
       max(ts_rank(seg.search_vector, plainto_tsquery('english', 'docker'))) AS best_rank
FROM conversations.segments seg
JOIN conversations.sessions sess ON seg.session_id = sess.id
WHERE seg.search_vector @@ plainto_tsquery('english', 'docker')
  AND sess.hidden_at IS NULL AND seg.hidden_at IS NULL
GROUP BY seg.session_id
ORDER BY best_rank DESC LIMIT 10;
```
**Expected:** One row per session, ordered by best segment match rank.

#### 13.2.4 Metadata filter queries (P3)
```sql
SELECT id, project FROM conversations.sessions WHERE project = 'conversations' LIMIT 3;

SELECT id, project, started_at FROM conversations.sessions
WHERE started_at >= '2026-03-01' AND started_at <= '2026-04-01T23:59:59' LIMIT 3;

SELECT id, project, estimated_cost FROM conversations.sessions
WHERE estimated_cost >= 1.00 ORDER BY estimated_cost DESC LIMIT 5;

SELECT id, project, turn_count FROM conversations.sessions
WHERE turn_count >= 10 ORDER BY turn_count DESC LIMIT 5;

SELECT DISTINCT tc.session_id FROM conversations.tool_calls tc
WHERE tc.tool_name = 'Bash' LIMIT 5;
```

#### 13.2.5 Autocomplete source queries (P3)
```sql
SELECT DISTINCT project FROM conversations.sessions WHERE hidden_at IS NULL ORDER BY project;
SELECT DISTINCT model FROM conversations.sessions WHERE model IS NOT NULL ORDER BY model;
SELECT DISTINCT tool_name FROM conversations.tool_calls ORDER BY tool_name;
SELECT DISTINCT topic FROM conversations.session_topics ORDER BY topic;
```
**Expected:** Each returns a non-empty, alphabetically sorted list.

#### 13.2.6 Graphify concept data (P1, optional)
```sql
SELECT 'concepts' AS tbl, count(*) FROM conversations.concepts
UNION ALL SELECT 'session_concepts', count(*) FROM conversations.session_concepts;
```
**Expected:** If Graphify ran, both non-zero. If not, both 0 (and `/related` correctly returns `[]`).

#### 13.2.7 Related sessions query (P3, if concept data exists)
```sql
SELECT session_id, count(concept_id) AS n
FROM conversations.session_concepts GROUP BY session_id ORDER BY n DESC LIMIT 1;

SELECT sc.session_id, count(DISTINCT sc.concept_id) AS shared
FROM conversations.session_concepts sc
WHERE sc.concept_id IN (
    SELECT concept_id FROM conversations.session_concepts WHERE session_id = '<SID>'
) AND sc.session_id != '<SID>'
GROUP BY sc.session_id ORDER BY shared DESC LIMIT 5;
```

#### 13.2.8 Hidden state in database (P2)
```sql
SELECT count(*) AS hidden_sessions FROM conversations.sessions WHERE hidden_at IS NOT NULL;
SELECT count(*) AS hidden_segments FROM conversations.segments WHERE hidden_at IS NOT NULL;
```
**Expected:** Matches what the UI shows in the Trash count.

#### 13.2.9 Dashboard aggregation queries (P4)
```sql
-- Summary totals
SELECT count(*) AS sessions,
       coalesce(sum(input_tokens), 0) + coalesce(sum(output_tokens), 0) AS total_tokens,
       coalesce(sum(estimated_cost), 0) AS total_cost,
       count(DISTINCT project) AS projects
FROM conversations.sessions
WHERE provider = 'claude' AND hidden_at IS NULL;

-- Cost over time (weekly)
SELECT to_char(started_at, 'IYYY-"W"IW') AS period, project,
       coalesce(sum(estimated_cost), 0) AS cost
FROM conversations.sessions
WHERE provider = 'claude' AND hidden_at IS NULL AND started_at IS NOT NULL
GROUP BY 1, 2 ORDER BY 1;

-- Tool family mapping
SELECT tool_name,
       CASE
         WHEN tool_name IN ('Read','Edit','Write','Glob','NotebookEdit') THEN 'file_ops'
         WHEN tool_name IN ('Grep','Agent') THEN 'search'
         WHEN tool_name = 'Bash' THEN 'execution'
         WHEN tool_name IN ('WebSearch','WebFetch') THEN 'web'
         WHEN tool_name IN ('TaskCreate','TaskUpdate','TodoWrite') THEN 'planning'
         ELSE 'other'
       END AS family,
       count(*) AS calls
FROM conversations.tool_calls tc
JOIN conversations.sessions s ON tc.session_id = s.id
WHERE s.provider = 'claude'
GROUP BY 1, 2 ORDER BY calls DESC;

-- Anomaly threshold
SELECT avg(estimated_cost) AS mean, stddev(estimated_cost) AS std,
       avg(estimated_cost) + 2 * stddev(estimated_cost) AS threshold
FROM conversations.sessions
WHERE provider = 'claude' AND hidden_at IS NULL AND estimated_cost IS NOT NULL;

-- Concept co-occurrence edges (if Graphify data exists)
SELECT sc1.concept_id AS source, sc2.concept_id AS target,
       count(DISTINCT sc1.session_id) AS weight
FROM conversations.session_concepts sc1
JOIN conversations.session_concepts sc2
  ON sc1.session_id = sc2.session_id AND sc1.concept_id < sc2.concept_id
GROUP BY 1, 2 ORDER BY weight DESC LIMIT 10;
```

#### 13.2.10 Embedding column populated (P5)
```sql
-- How many sessions have embeddings?
SELECT count(*) AS embedded,
       count(*) FILTER (WHERE embedding IS NULL) AS null_embeddings,
       count(*) FILTER (WHERE embedding IS NOT NULL) AS with_embeddings
FROM conversations.sessions
WHERE hidden_at IS NULL;

-- Sanity check: embeddings are 384-dim
SELECT id, vector_dims(embedding) AS dims
FROM conversations.sessions
WHERE embedding IS NOT NULL LIMIT 3;

-- HNSW index present
SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname = 'conversations' AND tablename = 'sessions' AND indexname LIKE '%embedding%';
```
**Expected:** After Phase 5 embedding completes, `with_embeddings == total` (ignoring hidden). `vector_dims` returns 384. Index named `idx_sessions_embedding` exists with `hnsw` method.

#### 13.2.11 Vector similarity query (P5)
```sql
-- Pick an arbitrary embedding and find its 5 most similar sessions
WITH q AS (SELECT embedding FROM conversations.sessions WHERE embedding IS NOT NULL LIMIT 1)
SELECT s.id, s.project, s.summary_text,
       1 - (s.embedding <=> (SELECT embedding FROM q)) AS similarity
FROM conversations.sessions s, q
WHERE s.embedding IS NOT NULL
ORDER BY s.embedding <=> (SELECT embedding FROM q)
LIMIT 5;
```
**Expected:** First row is the query session itself (similarity = 1.0). Subsequent rows have similarity < 1.0, monotonically decreasing.

### 13.3 UI — browsing flow (P0-P2)

Core three-pane browsing. Must work in every phase.

| # | Action | Expected |
|---|--------|----------|
| 1 | Open `http://localhost:5050` | App loads. Header shows title, provider, stats. Three panes visible. |
| 2 | Project list populated | Left pane shows project names sorted by most recent activity |
| 3 | Click a project | Middle pane loads segments grouped by conversation. Right pane shows project metadata. |
| 4 | Click a segment | Content viewer shows rendered markdown. Metadata panel shows segment detail. |
| 5 | Click "Full" on a conversation header | Content viewer shows full concatenated conversation. Metadata shows conversation-level stats. |
| 6 | Click the "Projects" header (with back arrow) | Project deselected. Middle pane shows "Select a project". |
| 7 | Conversation collapse/expand | Click triangle on conversation header. Segments toggle visibility. Sticky header stays visible when scrolling. |

### 13.4 UI — search flow (P3)

#### 13.4.1 Basic search

| # | Action | Expected |
|---|--------|----------|
| 1 | Type `docker` in search bar | After ~300ms debounce, middle pane shows **session cards** (not segment rows) |
| 2 | Inspect a session card | Shows: rank + relevance bar (P5), project name (blue, top-left), date (dim, top-right), model + cost line, 2-3 line snippet with "docker" highlighted, footer with tool summary, turn count, topics |
| 3 | Type single char `a` | No search fires, pane reverts to previous state |
| 4 | Clear search bar completely | Returns to normal browsing mode |
| 5 | Cmd+K | Search bar focused |
| 6 | Escape (while search bar focused) | Search bar clears, blur |

#### 13.4.2 Click-to-navigate from search result

| # | Action | Expected |
|---|--------|----------|
| 1 | Search, then click a session card | Project selected in left pane, conversation loads in content viewer, middle pane switches to segment list for that project |
| 2 | Content viewer | Shows full conversation markdown for the clicked result |

#### 13.4.3 Structured filter syntax (typed in search bar)

| Query | Expected behavior |
|-------|-------------------|
| `project:conversations docker` | Only "conversations" project results, matching "docker" |
| `tool:Bash error` | Only sessions with Bash tool, matching "error" |
| `tool:Edit,Write refactor` | Sessions with Edit OR Write tool, matching "refactor" |
| `after:2026-03-01 search` | Sessions after March 1, matching "search" |
| `before:2026-02-01` | Sessions before Feb 1, no text filter (filter-only) |
| `cost:>2.00` | Sessions costing more than $2 |
| `turns:>15 refactor` | Sessions with 15+ turns matching "refactor" |
| `model:opus` | Sessions with "opus" in model name |
| `topic:docker` | Sessions with "docker" topic |
| `model:opus project:conversations` | Filter-only, no free text — all opus sessions in conversations |
| `project:conversations tool:Edit after:2026-03-01 refactor` | All four filters + text combined |

#### 13.4.4 Provider switch clears search

| # | Action | Expected |
|---|--------|----------|
| 1 | Search for something | Results appear |
| 2 | Switch provider dropdown | Search bar clears, results clear, pane resets |

### 13.5 UI — filter chips (P3)

#### 13.5.1 Toggle

| # | Action | Expected |
|---|--------|----------|
| 1 | Click "Filters" button (right of search bar) | Filter bar expands: chips row (project, model, tool, topic, after, before, cost >, turns >) plus date pickers |
| 2 | Click "Hide Filters" | Collapses |
| 3 | Re-expand | State preserved |

#### 13.5.2 Autocomplete chips (project, model, tool, topic)

| # | Action | Expected |
|---|--------|----------|
| 1 | Click "project" chip | Dropdown with search input + scrollable list of all project names |
| 2 | Type in dropdown search | List filters in real time |
| 3 | Click a project name | `project:<name>` appended to search bar, dropdown closes, search triggers |
| 4 | Click "model" chip | Dropdown with model names |
| 5 | Click "tool" chip | Dropdown with tool names |
| 6 | Click "topic" chip | Dropdown with topic strings |

#### 13.5.3 Non-autocomplete chips (after, before, cost, turns)

| # | Action | Expected |
|---|--------|----------|
| 1 | Click "after" chip | `after:` appended to search bar cursor (no dropdown) |
| 2 | Click "cost >" chip | `cost:>` appended |
| 3 | Click "turns >" chip | `turns:>` appended |

#### 13.5.4 Active filter tags

| # | Action | Expected |
|---|--------|----------|
| 1 | Add a filter via chip | Tag appears below chips: "project: conversations" with X button |
| 2 | Add second filter | Second tag appears alongside first |
| 3 | Click X on a tag | Filter removed from search bar, search re-triggers |
| 4 | Clear search bar manually | All tags disappear |

#### 13.5.5 Dropdown dismissal

| # | Action | Expected |
|---|--------|----------|
| 1 | Open dropdown, click outside | Closes |
| 2 | Open dropdown, click different chip | First closes, second opens |

### 13.6 UI — date filter (P0, extended P3)

| # | Action | Expected |
|---|--------|----------|
| 1 | Expand Filters, set From and To dates, click Apply | Segment list in browsing mode filters by date (client-side) |
| 2 | Click Clear | Date filter removed |
| 3 | Combine with search | Client-side date filter applies to browsing; `after:`/`before:` in search bar applies server-side to search results |

### 13.7 UI — dashboard (P4)

#### 13.7.1 Tab switching

| # | Action | Expected |
|---|--------|----------|
| 1 | On load | "Conversations" tab is active, 3-pane layout visible |
| 2 | Click "Dashboard" tab | 3-pane layout replaced by scrollable dashboard. Search bar hidden. |
| 3 | Click "Knowledge Graph" tab | Full-screen d3 force graph (or loading/generating state) |
| 4 | Click "Conversations" tab | Returns to 3-pane layout. Previous selection state preserved. |
| 5 | Header remains | Title, provider dropdown, 3 tab buttons, stats, theme toggle, update button all visible on all tabs |

#### 13.7.2 Dashboard filter bar

| # | Action | Expected |
|---|--------|----------|
| 1 | Dashboard loads | Filter bar at top with date presets (7d, 30d, 90d, All), project dropdown, model dropdown |
| 2 | Click "7d" | Button highlights, all charts update to show only last 7 days |
| 3 | Click "30d" | Charts update to 30-day window |
| 4 | Click "All" | Clears date filter, shows all data |
| 5 | Select a project from dropdown | All charts filter to that project. "Clear Filters" button appears |
| 6 | Select a model from dropdown | All charts filter to that model |
| 7 | Click "Clear Filters" | All filters reset, "All" preset highlighted |

#### 13.7.3 Summary cards (Row 1)

| # | Check | Expected |
|---|-------|----------|
| 1 | Cards visible | 5 cards in a row: Sessions, Tokens, Est. Cost, Avg Cost/Session, Projects |
| 2 | Values populated | Non-zero numbers matching the curl output from 13.1.24 |
| 3 | Deltas shown | Each card shows "+N/week" or similar delta below the value |
| 4 | Delta coloring | Positive deltas green, negative deltas red/pink, zero neutral |
| 5 | Filter response | Changing filters updates all card values |

#### 13.7.4 Cost over time chart (Row 2)

| # | Check | Expected |
|---|-------|----------|
| 1 | Chart renders | Stacked area/line chart with periods on X-axis, dollar amounts on Y-axis |
| 2 | Legend | Shows stack names (projects by default) with color key |
| 3 | Hover tooltip | Shows exact values per stack for that period |
| 4 | Group by toggle | Dropdown: Daily/Weekly/Monthly. Changing updates X-axis labels and aggregation |
| 5 | Stack by toggle | Dropdown: By Project/By Model/By Provider. Changing updates stack colors/legend |
| 6 | Theme compat | Chart text, grid lines, and tooltips adapt to dark/light theme |

#### 13.7.5 Project breakdown chart (Row 3, left)

| # | Check | Expected |
|---|-------|----------|
| 1 | Chart renders | Horizontal bar chart, projects on Y-axis, cost on X-axis |
| 2 | Sort order | Sorted by total cost descending (most expensive at top) |
| 3 | Max 15 bars | Large project lists truncated to top 15 |
| 4 | Hover tooltip | Shows total cost, session count, avg cost/session |
| 5 | Click a bar | Dashboard filters to that project (same as selecting it in dropdown) |
| 6 | Click same bar again | Clears the project filter (toggle) |

#### 13.7.6 Model comparison chart (Row 3, right)

| # | Check | Expected |
|---|-------|----------|
| 1 | Chart renders | Grouped bar chart with models on X-axis |
| 2 | Two bar groups | "Total Cost ($)" and "Sessions" for each model |
| 3 | Hover tooltip | Shows cost, sessions, avg tokens/session |
| 4 | Click a bar | Filters dashboard to that model |

#### 13.7.7 Tool usage chart (Row 4, left)

| # | Check | Expected |
|---|-------|----------|
| 1 | Chart renders | Horizontal bar chart, tools on Y-axis, call count on X-axis |
| 2 | Family grouping | Tools grouped by family (file_ops together, then search, execution, web, planning, other) |
| 3 | Family colors | Each family has a distinct color |
| 4 | Hover tooltip | Shows call count, session count, family name |

#### 13.7.8 Session type distribution (Row 4, right)

| # | Check | Expected |
|---|-------|----------|
| 1 | Doughnut chart | Renders with segments for each session type |
| 2 | Legend | Shows type names with colors, positioned to the right |
| 3 | Hover tooltip | Shows type name, count, percentage, avg cost |
| 4 | Table below chart | Shows Type, Count, %, Avg Cost columns. Data matches doughnut. |

#### 13.7.9 Activity heatmap

| # | Check | Expected |
|---|-------|----------|
| 1 | Heatmap renders | GitHub-style grid of colored cells, ~52 weeks x 7 days |
| 2 | Day labels | Mon, Wed, Fri on the left |
| 3 | Month labels | Jan-Dec across the top |
| 4 | Color intensity | Empty days light/transparent, active days colored (darker = higher cost) |
| 5 | Hover tooltip | Shows date, session count, cost |
| 6 | Legend | "Less" to "More" with 5 color swatches |
| 7 | Horizontal scroll | If calendar is wider than container, horizontal scrollbar appears |

#### 13.7.10 Knowledge Graph tab

Full-screen tab (not a dashboard section).

**Generation states:**

| # | Check | Expected |
|---|-------|----------|
| 1 | Generating (on startup) | Progress bar with "Extracting concepts: N / M files", current file name, ok/failed counts, model name |
| 2 | Importing | "Importing graph into database..." with loading bar after extraction completes |
| 3 | Error | Error message with "Retry" button |
| 4 | Waiting | "Waiting for concept graph extraction to start..." if status is none |

**Graph visualization (once data is loaded):**

| # | Check | Expected |
|---|-------|----------|
| 1 | Full-screen graph | Graph fills entire tab area below header |
| 2 | Force layout | Nodes position themselves via physics simulation (settle in ~2-3s) |
| 3 | Node coloring | Nodes colored by community — same community = same color |
| 4 | Node sizing | Higher-degree nodes are larger |
| 5 | Edges | Lines between co-occurring concepts. Thicker = more shared sessions |
| 6 | Labels | Nodes above the label threshold show text labels |
| 7 | Hover tooltip | Shows concept name, type, community ID, session count |
| 8 | Click node | Switches to conversations tab with `topic:<concept_name>` in search bar |
| 9 | Zoom/pan | Mouse wheel zooms, click-drag pans |
| 10 | Drag node | Click-drag a node repositions it, neighbors stay loose |
| 11 | Regenerate button | Visible in header when graph is loaded. Clicking triggers full re-extraction. |

**Settings panel:**

| # | Check | Expected |
|---|-------|----------|
| 1 | Cog icon | Settings cog visible in top-right corner of graph area |
| 2 | Click cog | Opens settings panel with sliders and color scheme dropdown |
| 3 | Center Force slider | Moving it adjusts how strongly nodes pull toward center |
| 4 | Repel Force slider | More negative = nodes push apart more |
| 5 | Repel Range slider | Limits repulsion distance |
| 6 | Link Force slider | Higher = linked nodes stay closer together |
| 7 | Link Distance slider | Adjusts ideal distance between linked nodes |
| 8 | Collision Pad slider | Adds spacing around nodes |
| 9 | Label Threshold slider | Lower = more labels visible |
| 10 | Color Scheme dropdown | Changes node colors (tableau10, category10, dark2, set2, paired, pastel1) |
| 11 | Real-time update | All slider changes apply immediately without rebuilding the graph |
| 12 | Persistence | Settings survive tab switches, page refreshes (stored in localStorage) |
| 13 | Reset button | Restores all settings to defaults |
| 14 | Zoom preserved | Adjusting sliders does not reset zoom/pan position |

#### 13.7.11 Anomaly / flagged sessions table

| # | Check | Expected |
|---|-------|----------|
| 1 | Table visible | "Flagged Sessions" section at bottom (only if anomalies exist) |
| 2 | Columns | Project, Date, Turns, Tokens, Cost, Flag |
| 3 | Sorted by cost | Highest cost first by default |
| 4 | Click column header | Re-sorts by that column, toggles asc/desc |
| 5 | Click a row | Switches to conversations tab, navigates to that conversation |
| 6 | Flag column | Shows "High cost" in red/pink text |
| 7 | **No anomalies** | If all sessions are within 2 sigma: section is completely absent |

#### 13.7.12 Coordinated filtering

| # | Action | Expected |
|---|--------|----------|
| 1 | Click project bar in chart | All other charts update to show only that project |
| 2 | Click model bar | All charts filter to that model |
| 3 | Select "7d" preset | Summary cards, all charts, heatmap, anomalies all update |
| 4 | Combine project dropdown + date preset | Both filters active simultaneously across all charts |
| 5 | Clear Filters | All charts return to unfiltered state |

### 13.7b UI — search mode badges (P5)

| # | Action | Expected |
|---|--------|----------|
| 1 | Fresh DB, no embeddings yet | Badge 1: "Keyword" grey. Badge 2: "No Graph" dim grey (or "Graph" if Graphify already ran). |
| 2 | During initial embedding | Badge 1: "Embedding XX%" with pulsing accent2 color. Updates every 5s. |
| 3 | All embeddings done, Graphify absent | Badge 1: "Hybrid" accent. Badge 2: "No Graph" dim grey. Polling stops. |
| 4 | All embeddings done, Graphify ran | Badge 1: "Hybrid" accent. Badge 2: "Graph" accent. Polling stops. |
| 5 | Hover Badge 1 | Tooltip shows "Hybrid search — N/N sessions embedded" |
| 6 | Hover Badge 2 | Tooltip shows "Knowledge graph active — N concepts with community data" (or "Knowledge graph not loaded — community re-ranking inactive") |
| 7 | Switch provider | Polling resets; badges recompute for the new provider |

### 13.7c UI — relevance indicator (P5)

| # | Check | Expected |
|---|-------|----------|
| 1 | Run a search | Every result card shows `#N` rank number and a thin horizontal bar above the project name |
| 2 | Bar widths | Top result has full-width bar. Other results scaled proportionally to `score / max_score`. |
| 3 | Bar color | Accent color, smooth transition when changing searches |
| 4 | Theme compat | Bar track uses `--border`, fill uses `--accent`, adapts in both dark and light themes |

### 13.8 UI — regression checklist (run after every phase)

Every item here must pass regardless of which phase was just delivered. If any breaks, it's a regression.

| # | Feature | Test | Expected |
|---|---------|------|----------|
| 1 | Project list | Click a project | Segments load in middle pane |
| 2 | Segment selection | Click a segment | Content viewer shows markdown, metadata panel shows segment detail |
| 3 | Conversation view | Click "Full" on conversation header | Concatenated conversation in content viewer |
| 4 | Hide segment | Hover segment, click X | Segment disappears (unless Trash is on) |
| 5 | Restore segment | Trash on, click Restore | Segment reappears |
| 6 | Hide conversation | Click X on conversation header | All segments hidden |
| 7 | Hide project | Click X on project | Project hidden |
| 8 | Restore All | Header: Restore All | All hidden items restored |
| 9 | Export — copy | Click Copy in content toolbar | Markdown to clipboard |
| 10 | Export — download | Click Download | `.md` file downloads |
| 11 | Theme toggle | Click Light/Dark | Theme switches cleanly |
| 12 | Update pipeline | Click Update | Pipeline runs, data reloads |
| 13 | Keyboard: Cmd+K | Focuses search bar | |
| 14 | Keyboard: Escape | Clears and blurs search bar | |
| 15 | Keyboard: Arrow keys | Navigate segments (when search bar not focused) | |
| 16 | Resizable panes | Drag any resize handle | Pane widths change |
| 17 | Summary titles | Wait 10s or reload | Summary titles appear in request list |
| 18 | Provider switch | Change provider | Clears all state, loads new provider data |
| 19 | Search: session cards (P3+) | Type 2+ chars | Session-level cards, not segment rows |
| 20 | Search: click result (P3+) | Click a session card | Navigates to that conversation |
| 21 | Filter chips (P3+) | Open Filters, click a chip | Dropdown or prefix appended |
| 22 | Dashboard tab (P4+) | Click Dashboard tab | Dashboard view loads, search bar hidden |
| 23 | Dashboard summary cards (P4+) | Inspect summary row | 5 cards with values and deltas |
| 24 | Dashboard charts (P4+) | Inspect each chart | Data renders, hover tooltips work |
| 25 | Dashboard filters (P4+) | Click date preset, select project | All charts update together |
| 26 | Dashboard click-through (P4+) | Click anomaly row | Switches to conversations tab, opens that conversation |
| 27 | Dashboard theme (P4+) | Toggle dark/light | All chart text, tooltips, grid lines adapt |
| 28 | Tab round-trip (P4+) | Conversations → Dashboard → Knowledge Graph → Conversations | No lost state, no JS errors |
| 29 | Knowledge Graph tab (P4+) | Click Knowledge Graph tab | Full-screen graph or generation progress |
| 30 | Graph settings persist (P4+) | Adjust sliders, switch tabs, switch back | Settings preserved |
| 31 | Graph click-through (P4+) | Click a concept node | Switches to conversations tab with topic search |
| 32 | Search rank + bar (P5+) | Run a search | Every card shows `#N` and proportional relevance bar |
| 33 | Search mode badge (P5+) | Search bar area | Badges show current embedding + graph state, poll until settled |
| 34 | Hybrid results (P5+) | Search with a semantic-ish query | Results reflect semantic matches, not just exact keywords |
| 35 | Graceful fallback (P5+) | Force an embedding failure | Vector leg fails silently, keyword-only results still return |

### 13.9 Edge cases and error handling

| # | Scenario | Test | Expected |
|---|----------|------|----------|
| 1 | No search results | Search `xyzzy_nonexistent_gibberish` | "No results found" in middle pane |
| 2 | Filter-only, no free text | `project:conversations` | All sessions in project, sorted by recency |
| 3 | Malformed date filter | `after:not-a-date` | No crash, left in free text |
| 4 | Malformed cost filter | `cost:>abc` | No crash, left in free text |
| 5 | Very long query | Paste 500+ chars | No crash |
| 6 | Special characters in search | `C++`, `$PATH`, `<script>alert(1)</script>` | No crash, no XSS |
| 7 | Rapid typing | Type fast without pausing | Debounce fires once, no duplicate requests |
| 8 | Search then browse | Search, then click a project | Clears search, switches to browsing |
| 9 | Codex provider empty | Switch to Codex, search | `[]` or codex results, no errors |
| 10 | Related sessions no concept data | `/api/sessions/{id}/related` | `[]`, no error |
| 11 | Nonexistent segment ID | `/api/segments/doesnotexist` | 404 JSON error, not a crash |
| 12 | Nonexistent project | `/api/projects/doesnotexist/segments` | 404 JSON error |
| 13 | Empty database | Wipe Postgres volume, restart without running loader | App starts, all endpoints return empty arrays, no crashes |
| 14 | Postgres down | Stop postgres container, hit any API | 500 error (not a hang or crash) |
| 15 | Dashboard with no data (P4) | Open dashboard with empty DB | Charts render "No ... data" empty states, no JS errors |
| 16 | Knowledge Graph with no data (P4) | Click Knowledge Graph tab when concepts table empty | Shows "Waiting for concept graph extraction to start..." or generation progress |
| 17 | Dashboard with no anomalies (P4) | All sessions within 2 sigma | Flagged Sessions section completely absent |
| 18 | Dashboard filter returns empty (P4) | Filter to nonexistent project | Summary shows zeros, charts show empty states |
| 19 | Embedding column NULL (P5) | Search before embeddings generate | Vector leg fails silently; keyword-only fallback; no error |
| 20 | Model download fails (P5) | Remove network, restart | Embedding wrapped in try/except, logged non-fatal; app works keyword-only |
| 21 | No Graphify data + Phase 5 community re-rank (P5) | Search with Graphify absent | `_community_rerank()` returns `{}`; final scoring unchanged |
| 22 | Search status during embedding (P5) | Poll `/api/search/status` during generation | Returns `mode: "embedding"` with progress; completes to `"hybrid"` |

### 13.10 Visual / theme checks

Test in **both dark and light themes** (click the Light/Dark toggle).

| Element | What to verify |
|---------|---------------|
| Header bar | Background, text, buttons all adapt |
| Project list items | Hover, selected, hidden states all themed |
| Segment items | Hover, selected, nested indent, hidden states |
| Conversation headers | Sticky header, toggle arrow, timestamp |
| Content viewer | Headings, code blocks, blockquotes, inline code, horizontal rules |
| Search result cards (P3) | Background, hover, text colors, snippet `<mark>` highlighting |
| Filter chips (P3) | Default, hover, active states |
| Active filter tags (P3) | Accent background, readable text, X button |
| Filter dropdown (P3) | Background, border, shadow, item hover |
| Metadata panel | Labels, values, cost estimate, charts |
| Badges (tools, hidden) | Colors visible and readable |
| Scrollbars | Custom scrollbar thumb and track |
| Resize handles | Hover highlight color |
| Tab buttons (P4) | Active state highlight, inactive dim |
| Dashboard filter bar (P4) | Preset buttons, select dropdowns, clear button |
| Dashboard summary cards (P4) | Card backgrounds, value text, delta colors (green up, red down) |
| Dashboard chart containers (P4) | Chart.js axis labels, grid lines, legend text, tooltip backgrounds |
| Heatmap cells (P4) | Level-0 matches surface, level-1 through level-4 use accent with increasing opacity |
| Heatmap tooltip (P4) | Background, border, text readable in both themes |
| Knowledge Graph tab (P4) | Node colors visible, edge color adapts, labels readable, tooltip styled, settings panel themed |
| Anomaly table (P4) | Header, rows, hover state, cost column monospace green, flag column red |
| Relevance bar (P5) | Track uses `--border`, fill uses `--accent`, visible in both themes |
| Search mode badges (P5) | Translucent `color-mix` backgrounds adapt cleanly. Pulse animation visible in both themes. |

### 13.11 Performance sanity

Not formal benchmarks — just "does it feel right."

| Check | How | Expected |
|-------|-----|----------|
| App startup | `docker compose up --build`, watch logs | < 60s to "Backend ready — serving data" (Postgres load, embedding run, Graphify optional) |
| Project list load | Click app, watch left pane | Appears within 1s |
| Segment list load | Click a project | Loads within 1-2s |
| Search response | Type a query | Results appear within 1s of debounce |
| Filter autocomplete | Open a chip dropdown | Options appear instantly (< 200ms) |
| Conversation view | Click "Full" on a large conversation | Loads within 2s |
| Content rendering | Scroll through a long conversation | No visible jank |
| Dashboard load (P4) | Click Dashboard tab | All charts render within 2-3s |
| Dashboard filter switch (P4) | Click a date preset | Charts re-render within 1-2s |
| Heatmap render (P4) | Dashboard loads | Heatmap SVG appears, no scroll jank |
| Knowledge Graph load (P4) | Click Knowledge Graph tab (with data) | Force simulation settles within 3s, full-screen |
| Graph settings response (P4) | Adjust any slider | Simulation re-heats and settles within 1-2s |
| First semantic search (P5) | Search after fresh restart, embeddings not yet loaded | Keyword-only fallback is instant; vector leg kicks in once model downloads (< 60s) |
| Subsequent semantic search (P5) | Search with model cached | Results within 2s |
| Incremental embedding (P5) | Re-run launcher after already embedded | `_embed_new_sessions()` finds zero NULL embeddings, returns immediately |

---

## 14. Closing Reminders

- **Re-read this master plan before every non-trivial change.** Multi-session work drifts without grounding.
- **Update this document at the end of each phase** — mark status, add what was built, update the phase summary table.
- **Mermaid diagrams should stay current** — when a new component is added, update the module dependency graph.
- **Every feature must justify itself** as: faster recall OR faster pattern understanding. If it doesn't, it's out of scope.
- **Graceful degradation is sacred.** Every optional component (Graphify, embeddings, AI summaries) must have a working fallback.
- **Phase 6 is the final phase.** After 6.5–6.9 land (tests → CI → OOP refactor → docs), the project is complete. No more features unless a concrete new use case justifies them.
