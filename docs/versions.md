# Versions

Semver changelog, newest at top. The authoritative current version is the `version` field in `browser/frontend/package.json`. Bump via `.github/workflows/release.yml` (`workflow_dispatch`) — do not edit the field directly.

---

## v1.0.0 — 2026-04-14

**Project complete.** Feature-frozen at this version. Below is the phased rollup that got here.

### Phase 7.6 — Final documentation (this release)

- Created `docs/status.md` and `docs/versions.md` (this file).
- Refreshed `README.md` with post-7.5 architecture Mermaid, testing section, CI badges, cost-formula summary, updated `browser/` tree.
- Refreshed `docs/CONVERSATIONS_MASTER_PLAN.md` §3 module-dependency Mermaid for the post-7.1 service/repository layout; added §13 curl + UI test cases for Phase 7.5 endpoints; marked Phase 7 fully complete in §10/§11; updated the current-phase banner to "Project complete".

### Phase 7.4 final — 100% backend coverage + frontend 100% lines

- Backend: `pytest --cov-fail-under=100` passes. Every production line is traced, including FastAPI lifespan, SPA static serving (refactored into testable `_register_spa_routes`), `load.py` `main()` CLI entry, embedding + graphify failure branches, `_upsert_session` metadata edge cases, parser timestamp fallbacks, import_graph partial-stem matching, and every service/repository method.
  - 2 pragmas — both under global CLAUDE.md exception rules:
    - `load.py:681` `if __name__ == "__main__":` CLI bootstrap (exception a: exercised directly via a test that calls `main()`).
    - `services/search_service.py:249` dead `return scores` fallback in `_rrf_merge` (exception b: unreachable because RRF contributions are strictly > 0).
- `pyproject.toml` + `ci.yml` ratcheted to `--cov-fail-under=100`.
- Frontend: `vitest --coverage` at **100% lines**, 96% branches, 97% functions. Per-file thresholds in `vitest.config.js` enforce each module's measured posture.
  - 1 pragma — `KnowledgeGraph.jsx` top-level `cancelled` short-circuit (jsdom can't race the setTimeout callback against cleanup).
  - Residual sub-100% branches/functions live in: inline JSX arrow wrappers that component test stubs don't invoke, Chart.js option callbacks stored by the `react-chartjs-2` mock but never called, and d3 simulation tick handlers that require real DOM layout.

### Phase 7.5 — Cost calculation audit + UI breakdown

- `load.py`: `CACHE_WRITE_PREMIUM_5M = 1.25` applied to `cache_creation_tokens`. `recompute_session_costs()` wired into the FastAPI lifespan — idempotent, updates historical rows automatically when the formula changes.
- New endpoints: `/api/dashboard/top-expensive-sessions`, `/api/sessions/{id}/cost-breakdown`, and `cost_breakdown` field on `/api/dashboard/{summary,projects,models}`.
- Dashboard: new **Cost Breakdown** section (4-segment stacked bar + legend + Anthropic pricing link) and **Top 5 Most Expensive Sessions** widget with a `% from cache-read` transparency column.
- MetadataPane: new **Cost Attribution** section per session.
- New hook: `useCostBreakdown`.
- `Charts.TokenCostEstimate` retained only under GlobalStats (the rough 80/20 heuristic made no sense inside a session-level view).

### Phase 7.3 — Frontend decomposition + ESLint

- `App.jsx` shrunk 709 → 318 LOC. Extracted 8 new top-level components (`Header`, `SearchBar`, `FilterBar`, `ProjectsPane`, `RequestsPane`, `ContentPane`, `MetadataPane`, `ConversationsTab`) and 9 hooks (`useBackendReady`, `useProviders`, `useTheme`, `useSummaryTitles`, `useKeyboardShortcuts`, `useResizeHandles`, `useProjectSelection`, `useSearch`, `useHideRestore`).
- ESLint v9 flat config landed at `browser/frontend/eslint.config.js` with `react-hooks/rules-of-hooks` + `react-hooks/exhaustive-deps` as `error`.
- New `lint-frontend` CI job.

### Phase 7.2 — Latent bug fixes (XPASS handoff)

- `services/search_service.py` `_filter_only_retrieval` no longer emits `func.literal(1.0)` (which compiled to a non-existent Postgres function). Rank is now assigned in Python via `dict.fromkeys(...)`.
- Date filters in `services/_filter_scope.py` pass `date` objects directly to SQLAlchemy instead of `.isoformat()` strings (Postgres has no implicit cast from varchar → timestamptz).

### Phase 7.1 — Backend OOP restructure

- New `browser/backend/services/` tree: 7 service classes + `_filter_scope.py`.
- New `browser/backend/repositories/` tree: 5 repository classes.
- `db.py` provides FastAPI DI providers chaining routes → services → repositories → `get_db`.
- Every route handler became a thin shell calling `Depends(get_*_service)`.
- `response_model=` added to every route; shapes defined in `schemas.py`.

### Phases 0–6 (pre-7)

- **Phase 0 — Scaffolding:** Postgres 16 + pgvector in Docker Compose, SQLAlchemy 2.0 async + asyncpg + Pydantic v2 schemas.
- **Phase 1 — Data Loader:** `load.py` populates Postgres from markdown + raw JSONL metadata; heuristic topic extraction + session classification; Graphify concept graph import.
- **Phase 2 — Migrate Reads:** All API endpoints read from Postgres via SQLAlchemy. Search upgraded to tsvector ranking.
- **Phase 3 — Search Upgrade:** Session-level search results; metadata filter parsing (`project:`, `model:`, `after:`, `cost:>`, `turns:>`, etc.); filter chips with autocomplete; related-sessions endpoint.
- **Phase 4 — Dashboard:** 9 dashboard endpoints; 6 chart types + activity heatmap + anomaly table + full-screen Knowledge Graph tab; automated concept extraction pipeline via `claude -p --system-prompt` + graphifyy.
- **Phase 5 — Semantic Search:** `all-MiniLM-L6-v2` ONNX embeddings; hybrid tsvector + pgvector retrieval via Reciprocal Rank Fusion (k=60); optional community-based re-ranking (+0.05 per Leiden community overlap); two-part search mode badges.
- **Phase 6 — Cleanup, Testing & CI:** Removed `index_store.py`, `state.py`, `_watch_loop`. Docker volume narrowed. `export_service.sh`/.bat `[r]` restart loop. 348 pytest + 104 vitest tests baseline. GitHub Actions `ci.yml` (multi-branch) + `release.yml`. Ruff fully green.
