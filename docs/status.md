# Project Status

**Current version:** v2.1.0 (see `browser/frontend/package.json` — bump triggered via `.github/workflows/release.yml`).

**Phase:** 8 — **COMPLETE**. v2.1.0 shipped 2026-04-15.

**Posture:** v2.1.0 closes out the Phase 8 Knowledge Graph wiki integration. `graph_extract.py::build_graph` now writes `graphify-out/wiki/` (auto-labeled community articles + top-15 god-node articles) alongside `graph.json`. The Knowledge Graph tab is now a split pane: plain click on a concept node opens the matching wiki article in-place via `/api/graph/wiki/{index,lookup,{slug}}`; Cmd/Ctrl+click preserves the v2.0.0 "jump to Conversations with `topic:<name>`" fast-path; inline `[[WikiLink]]` anchors swap articles within the pane with unlimited-depth breadcrumb navigation. Every coverage gate held: backend 100% lines + branches + functions (834 pytest tests); frontend 100% lines globally with every new module at 100/100/100 (818 vitest tests, 36 files). Full spec: `docs/CONVERSATIONS_MASTER_PLAN.md` §10 Phase 8.

---

## What's shipped

The project is a personal observability + recall platform for Claude/Codex CLI conversations:

- Full-text + hybrid semantic search (tsvector + pgvector with `all-MiniLM-L6-v2` ONNX embeddings, RRF fusion, Leiden-community re-ranking).
- KPI dashboard with cost breakdown, project/model/tool rollups, activity heatmap, anomaly detection, and a Top 5 Most Expensive Sessions transparency widget.
- Knowledge Graph tab with d3 force-directed layout **plus in-tab wiki exploration** (Phase 8): plain click on a concept node opens the matching community/god-node article in a split-pane `ConceptWikiPane`; Cmd/Ctrl+click preserves the v2.0.0 jump-to-Conversations fast-path; inline `[[WikiLink]]` anchors swap articles within the pane with unlimited breadcrumb history.
- Per-session cost attribution via the same 4-way breakdown used by the dashboard.

---

## Architecture (post-Phase 7.1)

**Backend** (`browser/backend/`) — FastAPI + SQLAlchemy 2.0 async + Postgres 16 (pgvector). Routes are thin shells; all read/write logic lives in the service layer:

- `routes/` — FastAPI APIRouters, one per resource (`projects`, `segments`, `conversations`, `stats`, `summaries`, `visibility`, `dashboard`, `graph`). Phase 8 added `routes/graph.py` for `/api/graph/wiki/{index,lookup,{slug}}`.
- `services/` — 7 service classes (`SearchService`, `SessionService`, `DashboardService`, `GraphService`, `ProjectService`, `StatsService`, `SummaryService`) + `_filter_scope.py` shared filter compiler. Phase 8 extended `GraphService` with `_wiki_slug`, `_safe_wiki_path`, `load_wiki_index`, `load_wiki_article`, `resolve_wiki_slug`.
- `repositories/` — 5 repository classes (`SessionRepository`, `SegmentRepository`, `ToolCallRepository`, `SessionTopicRepository`, `ConceptRepository`)
- `models.py` — SQLAlchemy declarative models (all in the `conversations` schema)
- `schemas.py` — Pydantic v2 request/response models (`from_attributes=True`). Phase 8 added `WikiArticleSummary`, `WikiIndex`, `WikiArticle`, `WikiLookup`.
- `db.py` — async engine, session maker, FastAPI DI providers
- `graph_extract.py` (project root) — invokes `graphify.wiki.to_wiki(...)` alongside `to_json(...)` on every extraction run so `graphify-out/wiki/` regenerates automatically. `FILE_TYPE_ALIASES` normalizes extracted `file_type` values to the 5-enum `{code, document, image, paper, rationale}`.

**Frontend** (`browser/frontend/`) — React 19 + Vite 6 + Chart.js + d3, post-Phase-7.3 decomposition:

- 9 top-level components (`Header`, `SearchBar`, `FilterBar`, `ProjectsPane`, `RequestsPane`, `ContentPane`, `MetadataPane`, `ConversationsTab`, plus Phase 8's `ConceptWikiPane`) + `App.jsx` as the integration shell
- 11 custom hooks in `src/hooks/` (`useBackendReady`, `useProviders`, `useTheme`, `useSummaryTitles`, `useKeyboardShortcuts`, `useResizeHandles`, `useProjectSelection`, `useSearch`, `useHideRestore`, `useCostBreakdown`, plus Phase 8's `useConceptWiki`)
- `api.js` thin fetch wrapper per endpoint (Phase 8 added `fetchWikiIndex`, `fetchWikiArticle`, `resolveWikiSlug`)
- `utils.js` — Phase 8 exported `wikiSlug(label)` and extended `renderMarkdown` to rewrite `[[Label]]` into clickable wiki-link anchors; `sanitizeHtml` preserves `data-wiki-slug` on `<a>`.
- Tabs: Conversations (default), Dashboard, Knowledge Graph. The KG tab is now a split pane — graph on the left, `ConceptWikiPane` on the right (hidden until a concept is activated).

---

## Test coverage

| Layer    | Tests | Lines | Branches | Functions |
|----------|-------|-------|----------|-----------|
| Backend  | 834   | **100%** | **100%** | **100%** |
| Frontend | 818   | **100%** | 96.30%   | 97.40%   |

The residual frontend branch/function gaps live in inline JSX arrow wrappers that test stubs never invoke and Chart.js option callbacks that `react-chartjs-2`'s jsdom mock stores but never runs. Every hook, every helper, every route handler, and every service method has a direct test exercising its logic.

CI gates enforce: backend `--cov-fail-under=100`; frontend per-file thresholds in `vitest.config.js` matching the measured posture — any regression fails the build.

---

## CI pipeline

`.github/workflows/ci.yml` — lint-backend (ruff) → test-backend (pytest + 100% coverage gate) → lint-frontend (ESLint v9) → test-frontend (vitest + per-file gates) → build-frontend (Vite) → docker-build. Triggers on push + PR against `main|staging|dev` + manual dispatch. Per-ref concurrency cancels in-flight runs.

`.github/workflows/release.yml` — manual `workflow_dispatch` to bump `browser/frontend/package.json`'s semver (patch / minor / major).

---

## What's next

**No further phases planned.** v2.1.0 is feature-frozen. Future work is reactive:

- Bug fixes.
- Cost-formula tweaks if Anthropic pricing changes (adjust `CACHE_WRITE_PREMIUM_5M` or add a `CACHE_WRITE_PREMIUM_1H = 2.0` multiplier if per-turn TTL ever becomes visible in the JSONL; add a 1.5× tier for calls with >200K input tokens if per-call input-size tracking lands).
- Optional polish on the Phase 8 wiki surface when usage reveals concrete gaps. Candidates flagged during Phase 8 but deliberately deferred: descriptive community labels via `graphify.report._safe_community_name` (articles currently auto-label as "Community N"), a backend wire-level path-traversal test that bypasses httpx's ASGITransport URL normalization, and localStorage/URL-hash persistence for the wiki pane (currently ephemeral per Decision 8).

Reading order for any future session in this repo:
1. `CLAUDE.md` (re-read in full per global policy)
2. `docs/CONVERSATIONS_MASTER_PLAN.md` (authoritative spec)
3. `docs/status.md` (this file — describes current state)
4. `docs/versions.md` (version history)
