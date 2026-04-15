# Project Status

**Current version:** v1.0.0 (see `browser/frontend/package.json`).

**Phase:** 7 — **COMPLETE**. v1.0.0 shipped 2026-04-14. Phase 8 — **PLANNED** (v1.1.0 target).

**Posture:** v1.0.0 is the stable baseline. Phase 8 is a targeted enhancement: surface the Graphify-produced wiki inside the Knowledge Graph tab so clicking a concept stays in the exploration context instead of routing to Conversations. Full spec: `docs/CONVERSATIONS_MASTER_PLAN.md` §10 Phase 8.

---

## What's shipped

The project is a personal observability + recall platform for Claude/Codex CLI conversations:

- Full-text + hybrid semantic search (tsvector + pgvector with `all-MiniLM-L6-v2` ONNX embeddings, RRF fusion, Leiden-community re-ranking).
- KPI dashboard with cost breakdown, project/model/tool rollups, activity heatmap, anomaly detection, and a Top 5 Most Expensive Sessions transparency widget.
- Knowledge graph tab (d3 force-directed layout over Graphify concept extraction).
- Per-session cost attribution via the same 4-way breakdown used by the dashboard.

---

## Architecture (post-Phase 7.1)

**Backend** (`browser/backend/`) — FastAPI + SQLAlchemy 2.0 async + Postgres 16 (pgvector). Routes are thin shells; all read/write logic lives in the service layer:

- `routes/` — FastAPI APIRouters, one per resource
- `services/` — 7 service classes (`SearchService`, `SessionService`, `DashboardService`, `GraphService`, `ProjectService`, `StatsService`, `SummaryService`) + `_filter_scope.py` shared filter compiler
- `repositories/` — 5 repository classes (`SessionRepository`, `SegmentRepository`, `ToolCallRepository`, `SessionTopicRepository`, `ConceptRepository`)
- `models.py` — SQLAlchemy declarative models (all in the `conversations` schema)
- `schemas.py` — Pydantic v2 request/response models (`from_attributes=True`)
- `db.py` — async engine, session maker, FastAPI DI providers

**Frontend** (`browser/frontend/`) — React 19 + Vite 6 + Chart.js + d3, post-Phase-7.3 decomposition:

- 8 top-level components (`Header`, `SearchBar`, `FilterBar`, `ProjectsPane`, `RequestsPane`, `ContentPane`, `MetadataPane`, `ConversationsTab`) + `App.jsx` as the integration shell
- 10 custom hooks in `src/hooks/` (`useBackendReady`, `useProviders`, `useTheme`, `useSummaryTitles`, `useKeyboardShortcuts`, `useResizeHandles`, `useProjectSelection`, `useSearch`, `useHideRestore`, `useCostBreakdown`)
- `api.js` thin fetch wrapper per endpoint
- Tabs: Conversations (default), Dashboard, Knowledge Graph

---

## Test coverage

| Layer    | Tests | Lines | Branches | Functions |
|----------|-------|-------|----------|-----------|
| Backend  | 751   | **100%** | **100%** | **100%** |
| Frontend | 736   | **100%** | 96.04%   | 97.29%   |

The residual frontend branch/function gaps live in inline JSX arrow wrappers that test stubs never invoke and Chart.js option callbacks that `react-chartjs-2`'s jsdom mock stores but never runs. Every hook, every helper, every route handler, and every service method has a direct test exercising its logic.

CI gates enforce: backend `--cov-fail-under=100`; frontend per-file thresholds in `vitest.config.js` matching the measured posture — any regression fails the build.

---

## CI pipeline

`.github/workflows/ci.yml` — lint-backend (ruff) → test-backend (pytest + 100% coverage gate) → lint-frontend (ESLint v9) → test-frontend (vitest + per-file gates) → build-frontend (Vite) → docker-build. Triggers on push + PR against `main|staging|dev` + manual dispatch. Per-ref concurrency cancels in-flight runs.

`.github/workflows/release.yml` — manual `workflow_dispatch` to bump `browser/frontend/package.json`'s semver (patch / minor / major).

---

## What's next

**Phase 8 — Knowledge Graph wiki integration (v1.1.0 target).** Full spec in `docs/CONVERSATIONS_MASTER_PLAN.md` §10 Phase 8. Summary:

- Wire `graphify.wiki.to_wiki()` into the extraction pipeline so `graphify-out/wiki/` is always regenerated alongside `graph.json`.
- New `GET /api/graph/wiki/{index,slug,lookup}` endpoints on `GraphService` with a path-traversal guard.
- Knowledge Graph tab becomes a split pane: `ConceptGraph` on the left (unchanged), new `ConceptWikiPane` on the right.
- Click semantics: clicking a concept node loads the matching community / god-node wiki article **in-place** in the KG tab. The old "jump to Conversations with `topic:<name>`" behavior becomes an explicit "Open in Conversations" button on the wiki pane.
- New `useConceptWiki` hook; inline `[[WikiLink]]` anchors in rendered markdown swap articles within the pane with a breadcrumb trail; degrade gracefully (regenerate button) when `graphify-out/wiki/` is missing.
- Tests maintain 100% lines gate on both backend and frontend.

Beyond Phase 8, no further phases are planned — future work is reactive (bug fixes, cost-formula tweaks if Anthropic pricing changes).

Reading order for any future session in this repo:
1. `CLAUDE.md` (re-read in full per global policy)
2. `docs/CONVERSATIONS_MASTER_PLAN.md` (authoritative spec)
3. `docs/status.md` (this file — describes current state)
4. `docs/versions.md` (version history)
