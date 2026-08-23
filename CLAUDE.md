# Conversations — LLM CLI Conversation Export

<mandatory_workflow>

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

</mandatory_workflow>

<critical_context>

## 0. Critical Context

**What this project is.** A personal observability platform and recall system for Claude CLI and Codex CLI usage — NOT a conversation browser. Every feature must justify itself as *faster recall OR faster pattern understanding*. If it doesn't, it's out of scope. See §12 of the master plan for the anti-bloat guardrails.

**Current phase.** v2.1.1 shipped 2026-04-22. Phase 9 "Drift remediation & full coverage push" is complete on top of the Phase 0-8 v2 migration. The project is feature-complete; changes now should be either bug fixes, small quality-of-life improvements, or new phases approved against the master plan.

**Project-level overrides of the global CLAUDE.md** (these are intentional deviations — do not flag them as drift):

- **GitHub Actions instead of GitLab CI.** Documented in master plan §10 Phase 6.7. The project is open-source on GitHub; GitLab isn't available.
- **npm instead of pnpm.** Documented in master plan §10 Phase 6.7. npm is the project's package manager.
- **React + plain JavaScript instead of React + TypeScript strict.** Documented in the Tech Stack section below. The frontend is small (~4400 lines), single-user, and optimizing for typing churn vs runtime guarantees yields no measurable benefit for a tool this size.
- **`pip` + `requirements.txt` with `>=` operators instead of `uv` with pinned deps.** Docker image builds lock transitive versions at build time; the runtime container is the reproducibility unit, not the requirements file.

**Sacred contracts that must not drift without master-plan approval:**
- The 7 Postgres tables under the `conversations` schema (`sessions`, `segments`, `tool_calls`, `session_topics`, `saved_searches`, `concepts`, `session_concepts`). Schema changes require a master-plan update.
- The cost formula in `browser/backend/load.py::estimate_cost_breakdown` (Phase 7.5: `input + output + 0.10 × cache_read + 1.25 × cache_creation`). See master plan §5.
- The search response shape (`SessionSearchResult` Pydantic model) — the frontend relies on it verbatim.

</critical_context>

<project_identity>

## What This Project Is

A personal observability platform and recall system for Claude CLI and Codex CLI usage. Two pillars:

1. **Searchable recall** — find past conversations by vague memory, not exact keywords
2. **KPI dashboard** — understand LLM usage patterns, cost, and efficiency

This is NOT a conversation browser or archive museum. See @DESIGN.md for the full product direction.

</project_identity>

<architecture>

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

1. Raw JSONL synced from `~/.claude/projects/` and `~/.codex/sessions/`
2. Python parsers (`convert_*.py`) convert to one markdown file per project
3. `parser.py` splits markdown on `>>>USER_REQUEST<<<` delimiters into segments
4. Segments grouped by conversation_id into sessions
5. Metrics computed: char/word/line/token counts, tool breakdowns
6. All API endpoints read from Postgres via SQLAlchemy async queries (Phase 2+). In-memory index retained only for the export pipeline's use of `parser.build_index()`.
7. `jsonl_reader.py` extracts model names + actual token usage from raw JSONL
8. `load.py` merges parser + JSONL data and upserts into Postgres (sessions, segments, tool_calls, session_topics)
9. `topics.py` + `classify.py` run heuristic topic extraction and session type classification
10. `import_graph.py` optionally loads Graphify concept graph when `graphify-out/graph.json` exists

</architecture>

<status>

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
- [x] GitHub Actions CI pipeline (Phase 6.7 — `ci.yml` with lint/sast/test/coverage/build/docker-build (+ Trivy), `release.yml` for semver bumps)
- [x] Backend coverage gate 70→90 (Phase 7.4 partial — at 94.56%)
- [ ] Frontend decomposition + ESLint + tests for 9 deferred components (Phase 7.3)
- [ ] Cost calculation audit + UI breakdown (Phase 7.5 — cache_write premium, 4-way breakdown, Top-5 widget)
- [ ] Final documentation pass (Phase 7.6 — `docs/status.md`, `docs/versions.md`, README updates)

</status>

<commands>

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

</commands>

<coding_standards>

## Code Conventions

- Python: no type stubs, no docstrings unless logic is non-obvious
- React: functional components with hooks, no class components
- CSS: custom properties for theming, no Tailwind/utility classes
- No external charting library yet — current charts are custom SVG. Dashboard v1 will add Chart.js.
- Segment IDs are SHA256(source_file:segment_index), truncated to 16 chars
- Token estimates: currently char_count // 4 (rough). v2 uses actual token counts from JSONL `message.usage` fields.

</coding_standards>

<security>

## Security — SAST Scanning & Injection Safety (Non-Negotiable)

Implements global CLAUDE.md section 19 `<security>` for this repo. Security items are part of the Definition of Done for every change, not a later phase.

### SAST scanning — required `sast` stage in `ci.yml`

`.github/workflows/ci.yml` MUST carry a `sast` stage positioned after `lint-backend` / `lint-frontend` and before `test-backend` / `test-frontend` (`test-*` gain `needs: sast`), failing the pipeline on any HIGH/CRITICAL finding. MEDIUM findings are triaged: fixed, or suppressed inline with a written justification. `continue-on-error: true` on the stage is non-compliant. **Wired:** the `sast` job exists with `needs: [lint-backend, lint-frontend]` and job-level `permissions: security-events: write`; `test-backend` and `test-frontend` carry `needs: sast`; Trivy runs inside `docker-build` against the loaded image. Pipeline order is lint-backend + lint-frontend → sast → test-backend + test-frontend → build-frontend → docker-build (+ Trivy).

Tool set (GitHub / public project wiring):

- **Semgrep** — `pipx run semgrep scan` with `--config auto --config p/owasp-top-ten --config p/python --config p/typescript --config p/react --config p/docker --severity ERROR --error`, writing `semgrep.sarif`; the SARIF is uploaded via `github/codeql-action/upload-sarif` (category `semgrep`) so findings render under Security → Code scanning, then a separate step fails the job if Semgrep reported findings. Project rules, when needed, live in `.semgrep/` at the repo root.
- **CodeQL** — `github/codeql-action/init@v3` → `analyze@v3` (category `codeql`) for `python` and `javascript-typescript`, inside the `sast` job.
- **ruff `S` rules (backend)** — wired: `browser/backend/pyproject.toml` `[tool.ruff.lint] select = ["E", "F", "I", "N", "UP", "ANN", "S"]` with `"tests/**/*.py" = ["ANN", "S101"]` in `per-file-ignores`. `subprocess(shell=True)`, `eval`/`exec`, `pickle`, unsafe `yaml.load`, string-built SQL (`S608`) and hard-coded credentials are now caught by the existing `lint-backend` job. Every `S` suppression carries an inline justification: `S603` on the two constant-argv `subprocess.run` calls in `app.py`, `S110` on the optional vector-leg fallback in `services/search_service.py`, `S106`/`S108` on test fixtures.
- **ESLint security plugins (frontend)** — wired: `security.configs.recommended` + `noUnsanitized.configs.recommended` (`eslint-plugin-security`, `eslint-plugin-no-unsanitized`) apply to every linted file in `browser/frontend/eslint.config.js`; `npm run lint` reports 0 errors (warnings only). The three `dangerouslySetInnerHTML` call sites listed below are the only permitted ones and each must be fed exclusively by `renderMarkdown()` (DOMPurify-sanitized).
- **Dependency audit** — wired in `sast`: `pipx run pip-audit -r browser/backend/requirements.txt` and `npm audit --audit-level=high` in `browser/frontend` (project uses npm, not pnpm — see §0 overrides).
- **Secret scanning** — wired in `sast`: `gitleaks/gitleaks-action@v2` on a `fetch-depth: 0` checkout (`gitleaks detect --no-git --redact` locally).
- **Container scanning** — wired: `docker-build` now builds with `load: true` and runs `aquasecurity/trivy-action@0.28.0` (`severity: HIGH,CRITICAL`, `exit-code: 1`, `ignore-unfixed: true`) against `conversations:ci-${{ github.sha }}`.
- **Security response headers** — wired: `browser/backend/security_headers.py::SecurityHeadersMiddleware` (registered in `app.py`) sets `Content-Security-Policy` (`default-src 'self'`, `script-src 'self'`, `connect-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`; `style-src` allows `'unsafe-inline'` for the Vite/Chart.js inline styles, `img-src`/`font-src`/`worker-src` allow `data:`/`blob:`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` on every response via `setdefault`. Covered by `tests/test_security_headers.py`.

Local reproduction (run from the repo root before pushing):

```bash
semgrep scan --config auto --error .
gitleaks detect --no-git --redact
cd browser/backend && ruff check . && pip-audit -r requirements.txt
cd browser/frontend && npm run lint && npm audit --audit-level=high
npm --prefix browser/frontend run sast   # semgrep scan --config auto --error . && gitleaks detect --no-git --redact
```

Semgrep and gitleaks must be installed on the host (`pipx install semgrep`, `brew install gitleaks` / `winget install gitleaks`) — `npm run sast` shells out to them.

### Injection safety — input boundary inventory

Everything below crosses into the process from outside. Each entry names the injection class(es) and the defense this codebase requires. "In place" = verified in the current source; "required" = not yet implemented, must land with the next change that touches the boundary.

| Boundary | Where | Injection class(es) | Defense |
|---|---|---|---|
| REST query/path params (`q`, `provider`, `project`, `model`, `date_from`/`date_to`, `group_by`, `stack_by`, `segment_id`, `session_id`, `project_name`, `conversation_id`, `concept_id`/`concept_name`) | `browser/backend/routes/*.py` → `services/` → `repositories/` | SQL injection, resource exhaustion | In place: all queries are SQLAlchemy Core/ORM with bound parameters; `text()` appears only for literal `ORDER BY`/`GROUP BY` aliases and the `:sid` bind in `load.py`. Never interpolate a request value into `text()`; `group_by`/`stack_by`/`provider` must be matched against an allowlist, never used to pick a column. Required: length cap on `q` (`Query(max_length=...)`) and `ge`/`le` bounds on every integer param (`/api/dashboard/top-expensive-sessions` already has `ge=1, le=50`). |
| `/api/graph/wiki/{slug}`, `/api/graph/wiki/lookup` | `routes/graph.py`, `services/graph_service.py` | Path traversal | In place: `GraphService._safe_wiki_path` resolves `graphify-out/wiki/{slug}.md` and rejects anything outside the wiki root via `relative_to()`; traversal → 404. Covered by `test_safe_wiki_path_rejects_traversal_with_parent`. |
| `/api/summary/{segment_id}` (GET/POST/DELETE), `/api/summary/conversation/...` | `routes/summaries.py`, `services/summary_service.py` | Path traversal, resource exhaustion | Path params build file names under `SUMMARIES_DIR` (`{segment_id}.md/.pending/.input/.state.json`). In place: every summary-store path goes through `services/summary_service.py::_summary_file(key, ext)`, which rejects keys not matching `SUMMARY_KEY_PATTERN` (`^[A-Za-z0-9][A-Za-z0-9_\-]*$`) and refuses any resolved path that is not `relative_to(SUMMARIES_DIR.resolve())`, raising `InvalidSummaryKeyError`; `app.py` maps that exception to 404. POST 404s unknown segment IDs via DB lookup so arbitrary jobs cannot be enqueued. Covered by `tests/services/test_summary_key_confinement.py` (malformed keys rejected before any filesystem access; service entry points reject traversal). |
| `POST /api/update` | `browser/backend/app.py` | Command injection | In place: `subprocess.run([sys.executable, script, src_dir, out_dir])` list form; arguments come from env/constants, never from the request body. `shell=True` is banned (`S602`). |
| `POST /api/dashboard/graph/generate` | `routes/dashboard.py`, `services/graph_service.py` | Command injection (indirect) | In place: writes a `.generate_requested` sentinel only; the host-side `graph_watcher.{sh,bat}` decides what runs. No request data reaches the watcher. |
| Environment variables (`DATABASE_URL`, `CORS_ORIGINS`, `*_DIR`, `POSTGRES_*`, `SUMMARY_MODEL`) | `app.py`, `db.py`, `load.py`, `services/*`, `docker-compose.yml`, launchers | Auth/secrets, misconfiguration | In place: Postgres credentials flow only through `${VAR:-default}` + `.env` (`.env*` writes are hook-blocked); `CORS_ORIGINS` is an explicit comma-separated allowlist parsed by `_parse_cors_origins` — `*` is never permitted. Directory env vars are trusted deployment config, not user input. |
| Raw JSONL + generated Markdown loaders | `jsonl_reader.py`, `parser.py`, `load.py`, `convert_*.py` | Unsafe deserialization, resource exhaustion | In place: `json.loads` only — no `pickle`/`marshal`/`yaml.load`. File content (including tool output embedded in transcripts) is data: it is indexed and embedded, never executed or used to build paths or SQL. Required: per-file size bound before `read_text()`. |
| Graphify artifacts (`graphify-out/graph.json`, `graphify-out/wiki/*.md`) | `import_graph.py`, `services/graph_service.py`, `services/dashboard_service.py` | Unsafe deserialization, XSS (downstream) | In place: `json.loads` + field-by-field mapping into `concepts`/`session_concepts`; wiki Markdown is served verbatim to the frontend and sanitized there (see XSS row). Treat these files as LLM output (next row). |
| LLM calls — `claude -p` | `graph_extract.py` (stdin: condensed session Markdown, `--system-prompt`), `summary_watcher.{sh,bat}` + `export_service.sh` (stdin: `*.input` job file) | **Prompt injection**, command injection | Conversation transcripts contain tool results, pasted web pages and other untrusted text. In place: the instruction sits in the system prompt / positional prompt, transcript content arrives only on stdin as data; model output is consumed strictly as text (summaries: `TITLE:` line + body) or parsed JSON (`parse_graph_json` → `_normalize_file_type` coerces `file_type` to the `FILE_TYPE_ALIASES` enum). Model output never selects a file path, tool, URL or shell command. Required, and must hold for any new LLM call: pin the `claude -p` invocation to no tool access explicitly (today the calls rely on non-interactive defaults — verify against the CLI docs and make the restriction explicit when the invocation is next touched); keep the `timeout=300`; never splice transcript text into the prompt argument or a shell string (`subprocess` list form / stdin redirection only). |
| Rendering untrusted Markdown/HTML in React | `ContentViewer.jsx:80`, `SummaryPanel.jsx:242`, `ConceptWikiPane.jsx:117` (`dangerouslySetInnerHTML`) ← `utils.js::renderMarkdown` | XSS | In place: every call site renders `renderMarkdown()` output, which ends in `DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR })` (`isomorphic-dompurify`, Phase 9.3). No new `dangerouslySetInnerHTML` site without going through `renderMarkdown`; `eslint-plugin-no-unsanitized` enforces this. In place: FastAPI serves the SPA (no nginx), so `SecurityHeadersMiddleware` (`security_headers.py`, registered in `app.py`) emits the CSP (`default-src 'self'`, `script-src 'self'` — no `unsafe-inline` scripts — `connect-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` on every response. Covered by `tests/test_security_headers.py`. |

### Project-specific additions

- **Transcripts are PII.** Raw JSONL and Markdown under `raw/`, `markdown/`, `markdown_codex/`, `browser_state/summaries/` contain the user's full CLI history (file paths, code, credentials that may have been pasted). They are gitignored, bind-mounted, and never leave the machine except as stdin to the local `claude` CLI. No endpoint may return a file path outside the transcript set; no log line may echo transcript content.
- **Hidden state is not an access control.** `hidden_at` hides rows from the UI; it is a single-user convenience, not authorization. Do not describe or build on it as a security boundary.
- **Single-user, localhost-bound service.** There is no auth layer by design (§0). Any change that binds the service to a non-loopback interface or adds a second user must first add authentication and revisit every row above — raise it against the master plan before coding.

### Self-audit

The task-completion self-audit (global CLAUDE.md section 15) now includes a **Security check** for this repo: local SAST clean (commands above); every touched input boundary names its injection class(es) and defense in the table above; the table is updated if a boundary was added or changed.

</security>

<pitfalls>

## Anti-Patterns to Avoid

- Do not add features that assume the user will manually browse old conversations
- Do not add manual tagging, annotation, or note-taking features
- Do not add conversation comparison, diff, or replay features
- Do not index tool output content (Bash stdout, file contents) — only index user/assistant messages
- Do not add per-turn cost attribution — session-level estimates are sufficient
- Every feature must justify itself as: faster recall OR faster pattern understanding

</pitfalls>

<graphify>

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current

</graphify>
