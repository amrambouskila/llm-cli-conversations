# Versions

Semver changelog, newest at top. The authoritative current version is the `version` field in `browser/frontend/package.json`. Bump via `.github/workflows/release.yml` (`workflow_dispatch`) — do not edit the field directly.

---

## v2.2.2 — 2026-08-20

### Backend coverage gate restored to 100% (2026-08-28)

The `test-backend` CI job was failing on the coverage gate alone — all 858 tests passed, but `--cov-fail-under=100` reported 99.93% (2 of 2878 statements uncovered). Both uncovered statements were introduced by the security wiring above and had no test exercising them:

- `app.py:137` — the body of the `InvalidSummaryKeyError` exception handler. Covered by a new wire-level test, `tests/test_api_summaries.py::test_api_summary_get_invalid_key_returns_404`: `GET /api/summary/bad.key` fails `SUMMARY_KEY_PATTERN` (a `.` is not permitted), and Starlette dispatches the registered handler. The test asserts the exact body `{"error": "summary not found"}` so it cannot pass via the route's own `{"error": "segment not found"}` 404 without executing the handler.
- `services/summary_service.py:32` — the `is_relative_to` escape guard in `_summary_file`. Unreachable by any string input (the regex admits only a separator-free single segment), so its real purpose is defending against a link planted inside the summary store. Covered by `tests/services/test_summary_key_confinement.py::test_link_planted_in_the_store_cannot_smuggle_a_key_outside_it`, which plants a real reparse point at `SUMMARIES_DIR/escape.md` pointing to a sibling directory and asserts the guard rejects it.

No production code changed; no `pragma: no cover` added. The link test uses `Path.symlink_to` with a `_winapi.CreateJunction` fallback so it runs on both platforms rather than skipping: symlinks need Developer Mode or admin on Windows (`WinError 1314`), a directory junction needs no privilege, and `Path.resolve()` follows both identically. A `skipif` guard was rejected because it would leave line 32 uncovered on Windows and break `fail_under = 100` on every local run while CI stayed green. Verified end-to-end in `python:3.13-slim` (the CI platform): 2878 statements, 0 missed, `Required test coverage of 100% reached`. Backend tests 858 -> 860; ruff clean.

Known-unrelated, still open: `jsonl_reader.py:36` tests `"/subagents/" in str(path)`, which never matches on Windows backslash paths — `test_read_claude_jsonl_skips_subagent` fails and line 37 is uncovered on a Windows host. CI is Linux, so the gate is unaffected.

### docker-build: Trivy action pinned to v0.36.0 (2026-08-28)

`docker-build` failed twice, for two distinct upstream-tag reasons:

1. `Unable to resolve action aquasecurity/trivy-action@0.28.0`. That repository tags releases with a `v` prefix — bare `0.28.0` never existed. Corrected to `v0.28.0`.
2. `Unable to resolve action aquasecurity/setup-trivy@v0.2.1`. `trivy-action@v0.28.0` delegates its install step to `aquasecurity/setup-trivy`, and the `v0.2.1` tag it pins has since been **deleted upstream** — `setup-trivy` now publishes only `v0.2.6`, `v0.3.0` and `v0.3.1`.

Because of (2), `trivy-action` v0.28.0–v0.30.0 are permanently unusable: each references its `setup-trivy` dependency by a **mutable tag** that has since been deleted (`v0.2.1` in v0.28.0, `v0.2.2` in v0.29.0/v0.30.0). **v0.31.0 switched that nested reference to a commit SHA**, which cannot be deleted by a tag cleanup — so v0.31.0+ are structurally immune to this failure mode. Pinned to the current `v0.36.0` (trivy binary v0.70.0), where both nested references (`aquasecurity/setup-trivy@3fb12ec`, `actions/cache@27d5ce7`) are SHA-pinned and were verified to exist.

Together these mean the Trivy scan had never actually executed in CI since it was added; the step failed at action resolution every time.

Verified locally against the real image: `docker build -f ./Dockerfile .` succeeds, and the exact scan the job runs (`--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`, repo `.trivyignore` mounted) exits 0 with `Total: 0 (HIGH: 0, CRITICAL: 0)` under **both** trivy v0.56.1 and v0.70.0 — so the version bump introduces no new findings. The four inputs in use (`image-ref`, `severity`, `exit-code`, `ignore-unfixed`) are identical across v0.28.0 and v0.36.0, so no other change was needed. Every other `uses:` reference in both workflow files was audited against the GitHub API and resolves.

### CI hardening + dependency remediation (2026-08-24)

- **Semgrep invocation corrected.** The job used `semgrep ci` with `--severity` and `--error`, which that subcommand does not accept — it exits 2 with a usage error before scanning. Switched to `semgrep scan`, which supports both.
- **Release workflow hardened against script injection.** `${{ inputs.bump }}` and `${{ steps.bump.outputs.new_version }}` were interpolated directly into `run:` blocks, where the value becomes shell code. Both now pass through `env:` and are read as quoted shell variables. The input is `type: choice`, so this was not exploitable today — it is the pattern that breaks the moment the input type changes.
- **Base-image security patches in the Dockerfile.** The Debian slim bases ship a `util-linux` that Trivy flags HIGH (CVE-2026-53612..53615, fixed upstream in 2.41.5). Measured directly: `python:3.13-slim` carries 38 fixable HIGH/CRITICAL, `3.12-slim` 36, `3.11-slim` 38, while `nginx:alpine` is clean. These come from the base layer, so an `apt-get upgrade` step is required even where nothing else installs them.
- **`.trivyignore` added** for two findings with no in-image remediation: `CVE-2025-47273` (setuptools 70.3.0) and `GHSA-6v7p-g79w-8964` (msgpack 1.1.2). Both come from pip's vendored manifest in the base image, not from project dependencies — and setuptools 70.3.0 is not even installed (`find` finds nothing; the image ships 84.x). Upgrading pip does not rewrite that manifest. Each entry carries its justification inline.
- **Dependency remediation.** `vite ^6.3.5 -> ^6.4.3`, and `vitest` + `@vitest/coverage-v8` `^2.1 -> ^3.2.6`. vitest 2.x has no patched release for the advisory, so this is a deliberate major upgrade; npm proposed 4.x, and 3.2.6 is the smallest patched jump. `npm audit --audit-level=high` reports 0 vulnerabilities; build passes and all 887 tests across 38 files pass on the new runner.
- **Root-level scripts are now linted.** `convert_claude_jsonl_to_md.py`, `convert_codex_sessions.py`, `convert_export.py` and `graph_extract.py` sat outside the `browser/backend` ruff scope and were never checked. A second `ruff check` step in `ci.yml` covers them with `E,F,I,N,UP,S`; nine findings fixed (unused import/variable, f-strings without placeholders) and the subprocess/except-pass sites carry justified `# noqa` with reasons.


**Security documentation + SAST wiring.** Propagates the global `<security>` standard (SAST stage + injection-safety inventory) into this repo's instruction files, master plan, and status docs, then wires it: `sast` CI stage, Trivy, ruff `S`, ESLint security plugins, FastAPI security headers, and summary-store path confinement. Stays a **patch**: no new endpoint, schema, or contract; the two runtime changes are hardening of existing behavior (response headers added; summary keys that were never valid now 404 deterministically instead of reaching the filesystem).

### Security wiring

- `.github/workflows/ci.yml` — new `sast` job (`needs: [lint-backend, lint-frontend]`, `permissions: security-events: write`): CodeQL `python` + `javascript-typescript` (`init@v3` → `analyze@v3`), Semgrep (`pipx run semgrep scan --config auto --config p/owasp-top-ten --config p/python --config p/typescript --config p/react --config p/docker --severity ERROR --error`, SARIF uploaded via `codeql-action/upload-sarif` + fail-on-findings step), `gitleaks/gitleaks-action@v2` (`fetch-depth: 0`), `pipx run pip-audit -r browser/backend/requirements.txt`, `npm audit --audit-level=high`. `test-backend` and `test-frontend` now `needs: sast`. `docker-build` builds with `load: true` and runs `aquasecurity/trivy-action@0.28.0` (`severity: HIGH,CRITICAL`, `exit-code: 1`, `ignore-unfixed: true`).
- `browser/backend/pyproject.toml` — ruff `select` gains `S`; `tests/**/*.py` per-file-ignores gain `S101`.
- `browser/backend/security_headers.py` (new) — `SecurityHeadersMiddleware` sets CSP (`default-src 'self'`, `script-src 'self'`, `style-src 'self' 'unsafe-inline'`, `img-src 'self' data: blob:`, `font-src 'self' data:`, `connect-src 'self'`, `worker-src 'self' blob:`, `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` via `setdefault` on every response. Registered in `app.py`.
- `browser/backend/services/summary_service.py` — every summary-store path is built by `_summary_file(key, ext)`, which validates the key against `SUMMARY_KEY_PATTERN` (`^[A-Za-z0-9][A-Za-z0-9_\-]*$`) and refuses resolved paths outside `SUMMARIES_DIR.resolve()`, raising `InvalidSummaryKeyError`. `app.py` registers an exception handler mapping it to 404.
- Justified `# noqa` suppressions: `S603` on the two constant-argv `subprocess.run` calls in `app.py`; `S110` on the optional vector-leg fallback in `services/search_service.py`; `S106` (`tests/conftest.py` throwaway container password) and `S108` (`tests/test_import_graph.py` fixture path).
- `browser/frontend/eslint.config.js` — `eslint-plugin-security` + `eslint-plugin-no-unsanitized` recommended configs applied to every linted file (0 errors, warnings only). `package.json` gains devDependencies `eslint-plugin-security ^4.0.1`, `eslint-plugin-no-unsanitized ^4.1.5` and a `sast` script (`pipx run semgrep scan --config auto --error . && gitleaks detect --no-git --redact`).
- Tests (new): `browser/backend/tests/test_security_headers.py` (2), `browser/backend/tests/services/test_summary_key_confinement.py` (3, parametrized: well-formed keys resolve inside the store, malformed keys rejected before any filesystem access, service entry points reject traversal). 17 non-DB tests pass locally; the DB-backed confinement test runs in CI via testcontainers.
- Still pending after this entry: `Query(max_length=...)` on `q` + `ge`/`le` on the remaining integer params; per-file size bound in the JSONL/Markdown loaders; explicit no-tool pin on `claude -p`

### Docs

- `CLAUDE.md` / `AGENTS.md` — new `<security>` section: required `sast` stage in `.github/workflows/ci.yml` (Semgrep + CodeQL with SARIF upload, ruff `S` rules in `lint-backend`, `eslint-plugin-security` + `eslint-plugin-no-unsanitized` in `lint-frontend`, `pip-audit` / `npm audit`, gitleaks, Trivy on `docker-build`; fail on HIGH/CRITICAL, MEDIUM triaged with written justification); full input-boundary inventory (REST params, wiki slug, summary `segment_id`, `POST /api/update`, graph-generate sentinel, env vars, JSONL/Markdown loaders, Graphify artifacts, `claude -p` prompt injection, `dangerouslySetInnerHTML` XSS) with per-row injection class and in-place vs required defense; project-specific notes (transcripts are PII, `hidden_at` is not access control, single-user localhost-only); Security check added to the self-audit.
- `docs/CONVERSATIONS_MASTER_PLAN.md` — §5 Security section (tool set + local reproduction), `1a. sast` inserted between `lint-*` and `test-*` in the §10 pipeline stage list, and the two SAST gate lines ("SAST stage green — zero HIGH/CRITICAL findings; MEDIUM findings triaged with written justification" / "New input boundaries in this phase are injection-safe and documented in `CLAUDE.md` `<security>`") added to every phase gate list.
- `docs/status.md` — Security section lists what is wired vs. still pending; CI pipeline line shows `sast` between lint and test and Trivy on `docker-build`.
- `README.md` — CI paragraph describes the wired `sast` stage, the Trivy scan, and the local `npm run sast` command.
- Instruction files, master plan, and status docs were reconciled after the wiring landed: every "not yet wired" / "required" / "not present today" statement about the items above now reads as current state; only the genuinely pending items remain marked pending.
- `docs/versions.md` — this entry.

---

## v2.1.1 — 2026-04-22

**Phase 9 — Drift remediation & full coverage push.** Closes every drift item surfaced by two independent audits (one external, one self-conducted against global CLAUDE.md), replaces the custom HTML sanitizer with DOMPurify, hoists the last of the inline JSX arrow wrappers into named `useCallback`s, and lifts the entire frontend to a flat 100% line + branch + function coverage gate.

### Infrastructure

- `docker-compose.yml` now substitutes `${POSTGRES_USER:-conversations}` / `${POSTGRES_PASSWORD:-conversations}` / `${POSTGRES_DB:-conversations}` / `${POSTGRES_PORT:-5432}` throughout — no more hard-coded `conversations:conversations` strings. Healthcheck reads `pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"`. The `llm-browser` service gets a `CORS_ORIGINS` env entry so the FastAPI middleware can be locked down or opened without a code change.
- New committed `.env.example` enumerates every overridable value (`POSTGRES_*`, `PORT`, `CORS_ORIGINS`, `CLAUDE_PROJECTS_DIR`, `CODEX_SESSIONS_DIR`) with one-line comments.

### Backend

- `browser/backend/app.py` gained `_DEFAULT_CORS_ORIGINS` + `_parse_cors_origins(raw)` — a pure helper that the `CORSMiddleware` reads from, respecting the new `CORS_ORIGINS` env var. New `browser/backend/tests/test_cors.py` (6 tests, 100% coverage) exercises default / single / multi / whitespace-stripped / empty-string / filter-empty-entries paths.
- `browser/backend/db.py` hoisted its fallback DATABASE_URL into a `_DEFAULT_DATABASE_URL` module constant so the override path has clear intent.
- `browser/backend/tests/test_api_visibility.py` rewrote the `_hidden_at` helper from an f-string `text(f"SELECT hidden_at FROM conversations.{table} ...")` to a SQLAlchemy Core form accepting a model class + a `WhereClause`. Zero runtime behavior change; eliminates the last backend SQL injection smell.

### Frontend

- **DOMPurify swap.** Added `isomorphic-dompurify` (3.9.0). `browser/frontend/src/utils.js` deleted the hand-rolled `sanitizeHtml` regex sanitizer — `renderMarkdown` now finishes with `DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR })` where the whitelists are exported module constants. The 3 `dangerouslySetInnerHTML` call sites (`ConceptWikiPane.jsx`, `ContentViewer.jsx`, `SummaryPanel.jsx`) are unchanged because they all go through `renderMarkdown`.
- **Node 25 localStorage polyfill.** `src/__tests__/setup.js` now installs an in-memory `Storage` implementation on `globalThis.localStorage` + `window.localStorage`. Fixes a Node 25 + jsdom 25 interaction where Node's partial built-in `localStorage` (activated by `--localstorage-file`) shadows jsdom's and breaks `.clear()`. Makes the test suite robust across Node 20 (CI) and Node 25+ (local dev).
- **App.jsx inline-arrow hoist.** `onToggleShowHidden`, `onToggleTheme`, and `onToggleDateFilter` are now named `handleToggle*` callbacks wrapped in `useCallback`. Moves App.jsx's function-level coverage from 25% → 100% by giving the test suite a stable identity to invoke via the Header/ConversationsTab mock props.
- **Coverage fills via pure-helper extraction.**
  - `Dashboard.jsx` exports `formatUsd`, `anomalyComparator`, `buildCostBreakdownScope` — tested directly in new `src/__tests__/dashboardHelpers.test.js`. Closes the `|| "…"` date-scope fallback branches, the non-finite-input formatUsd branch, and the null-handling paths in the anomaly sort comparator.
  - `ConceptGraph.jsx` exports `shouldShowLabel`, `buildTooltipHtml`, `labelY`, `collisionRadius`, `collectCommunityIds` — tested directly in new `src/__tests__/conceptGraphHelpers.test.js`. Closes 17 branches that were previously unreachable via the d3 tick/drag/hover handlers that `jsdom` can't drive.
  - `SummaryPanel.jsx` exports `progressSignature` and `formatProgress` — tested directly with null / missing-field / unknown-phase inputs.
- **Targeted `/* c8 ignore */` pragmas** on 3 genuinely unreachable defensive branches: the `summaryKey === lastKeyRef.current && status === "ready"` stale-closure guard in `SummaryPanel` (unreachable without StrictMode double-invocation after the ready state), and the two `viewingMarkdown` / `viewingSource` fallback `||` chains in `App.jsx` that only fire when nothing is selected. Each pragma has a justifying comment.
- **`Dashboard.test.jsx` extensions.** New `"Dashboard — branch/function gap closers"` describe block exercises: filter-bar toggle-off (line 200, 204 true branches), per-period stack-data fallback (line 266), unknown-model label fallback (line 370), filterOptions missing `projects`/`models` arrays (lines 540, 550), and clicks on the Project/Date/Turns anomaly column headers (L749, L750, L752 inline-arrow functions).
- **`ConceptGraph.test.jsx` extensions.** Four new tests: minimal-data render (degree/weight/community_id all missing → exercises `|| 1` fallbacks across 4 d3 callbacks), unknown-colorScheme from localStorage (both at mount and post-mount via slider change → exercises line 157 `|| COLOR_SCHEMES.tableau10` in BOTH effects), StrictMode-driven same-dataKey early-return, and a data-null settings-before-mount render.
- **`SummaryPanel.test.jsx` extensions.** New describe blocks: `"cancellation paths"` (unmount-during-onRequest success, unmount-during-onRequest error, unmount-during-poll); `"regenerate with no progress field"` (line 159 `|| null` fallback); direct unit tests for the exported `progressSignature` and `formatProgress` helpers (empty-input, missing-field, unknown-phase branches).

### Coverage gates

- Backend `pyproject.toml` unchanged at `fail_under = 100`.
- Frontend `vitest.config.js` — removed all 4 per-file reductions and the 95% global floor. Now a single flat `thresholds: { lines: 100, functions: 100, branches: 100 }` applied to every file in `src/`. The justification comment for the residual sub-100 paths is deleted (no longer true).

### Docs

- `CLAUDE.md` prepended with the master plan's mandatory-re-read directive + new §0 (critical context, current phase, explicit project-level overrides of global CLAUDE.md, sacred data contracts). Matches the contract in global CLAUDE.md §3.
- `docs/status.md` updated with the v2.1.1 posture, updated coverage table, and the new flat-gate CI line.
- `docs/versions.md` — this entry.
- `docs/CONVERSATIONS_MASTER_PLAN.md` — Phase 9 added to §10 with the same per-subphase breakdown used for Phase 8, summary table row, and banner refresh.

### Counts

- **Frontend tests:** 887 across 38 files (was 818 / 36). +~69 new tests across `dashboardHelpers`, `conceptGraphHelpers`, `SummaryPanel`, `Dashboard`, `ConceptGraph`, `App`, `utils`, and the new `test_cors.py`.
- **Backend tests:** 850+ (was 834). +6 from `test_cors.py`; `test_api_visibility.py` preserved its 10 cases but at a cleaner helper implementation.
- **Coverage:** backend 100/100/100 (unchanged). Frontend 100/100/100 (was 100 / 96.30 / 97.40).

---

## v2.1.0 — 2026-04-15

**Phase 8 — Knowledge Graph wiki integration.** Plain click on a concept node opens the matching community/god-node wiki article in a split pane inside the Knowledge Graph tab; Cmd/Ctrl+click preserves the v2.0.0 "jump to Conversations with `topic:<name>`" fast-path. Every coverage gate held.

### Backend (8.1)

- `graph_extract.py::build_graph` now calls `graphify.wiki.to_wiki(G, communities, str(out_dir / "wiki"), god_nodes_data=_derive_god_nodes(G))` after `to_json(...)`. Community articles get auto-labeled "Community N"; god-node articles are generated for the top-15 highest-degree nodes. `graphify-out/wiki/` regenerates on every extraction run — no manual step.
- `file_type` values normalized to graphify's 5-enum `{code, document, image, paper, rationale}` via `FILE_TYPE_ALIASES` + `_normalize_file_type()` applied inside the node merge loop. System prompt tightened to enumerate the allowed values.
- New `browser/backend/routes/graph.py` with three endpoints under `/api/graph/wiki/`:
  - `GET /index` → `WikiIndex { title, markdown, articles: [{ slug, title, kind }] }`. 404 when wiki dir absent.
  - `GET /lookup?concept_id=…&concept_name=…` → `WikiLookup { slug }`. God-node article (by name) preferred over community article (by `concepts.community_id` lookup). 404 when neither resolves.
  - `GET /{slug}` → `WikiArticle { slug, title, markdown }`. 404 when resolved path escapes the wiki root or doesn't exist.
- `GraphService._wiki_slug` reimplements `graphify.wiki._safe_filename` in-repo (three-char substitution). Locked by a 16-case parity test.
- `GraphService._safe_wiki_path(slug)` mirrors `app.py::_register_spa_routes`: resolve + `relative_to()` → catches `..`, absolute paths, null bytes.
- `schemas.py` added `WikiArticleSummary`, `WikiIndex`, `WikiArticle`, `WikiLookup`. Every route has `response_model=…`.

### Frontend (8.2)

- New `src/components/ConceptWikiPane.jsx` — loading / error / article / null states + delegated wiki-link click handler + breadcrumb nav + Open-in-Conversations + Close actions.
- New `src/hooks/useConceptWiki.js` — AbortController-based fetch lifecycle (same shape as `useCostBreakdown`), unlimited breadcrumb with browser-back semantics, `openByConcept` that silently no-ops when resolveWikiSlug 404s.
- `src/components/KnowledgeGraph.jsx` became a split-pane layout. When `graphReady && wiki.selectedSlug`, renders `<ConceptGraph>` left + `.resize-handle-wiki` + `<ConceptWikiPane>` right.
- `src/components/ConceptGraph.jsx` click branching: plain click → `onConceptActivate(d)` (opens wiki pane); `metaKey || ctrlKey` → `onConceptOpenInConversations(d.name)` (v2.0.0 fast-path preserved). Prop rename `onConceptClick` → `onConceptActivate`.
- `src/App.jsx` inline `onConceptClick` arrow replaced by a named `handleOpenConceptInConversations(conceptName)` callback; resize plumbing (`wikiWidth`, `wikiContainerRef`, `startDrag`) threaded from `useResizeHandles` into `KnowledgeGraph`.
- `src/hooks/useResizeHandles.js` extended with `wikiWidth` (default 360, bounds 280-600) + `wikiContainerRef` + `"wiki"` handle key.
- `src/utils.js` exported `wikiSlug(label)`; `renderMarkdown` rewrites inline `[[Label]]` → `<a class="wiki-link" data-wiki-slug="…">Label</a>`; `sanitizeHtml` preserves `data-wiki-slug` on `<a>`.
- `src/api.js` added `fetchWikiIndex`, `fetchWikiArticle`, `resolveWikiSlug` (all forward `options.signal`).
- `src/App.css` new styles for `.knowledge-graph-split`, `.resize-handle-wiki`, `.concept-wiki-pane/*`, `.wiki-breadcrumb*`, `.wiki-link*`.

### Tests (8.3)

- Backend: 83 new tests across 3 files (`test_api_graph_wiki.py`, `tests/services/test_graph_service.py` extensions, `test_graph_extract.py`). Total **834 passing; coverage 100% lines + branches + functions**. Ruff clean.
- Frontend: 144 new tests. Total **818 passing across 36 files; 100% lines globally; every new module at 100/100/100**. `vitest.config.js` gained per-file thresholds for `ConceptWikiPane.jsx` and `useConceptWiki.js`; `App.jsx` functions threshold adjusted 40 → 25 (jsdom-inherent inline-arrow gap, same pattern as existing Dashboard/SummaryPanel/ConceptGraph entries).

### Design decisions locked in v2.1.0

| # | Decision | Rationale |
|---|----------|-----------|
| 6 | Pane default 360px, bounds 280-600 | Compact / graph-dominant; matches "wiki as reference sidebar" framing. |
| 7 | Missing-wiki UX: silent no-op on concept click | Pane never opens when index/article missing. User uses the KG header's existing Regenerate button. No toast, no inline empty pane. |
| 8 | Ephemeral pane state | Empty on tab entry; no localStorage, no URL hash. Matches the rest of the app. |
| 9 | Unlimited breadcrumb depth | Full navigation trail remains visible until the pane is closed. Click-to-jump truncates forward history. |
| 10 | Cmd/Ctrl+click preserves v2.0.0 fast-path | Power-user muscle memory retained. Plain click opens the wiki pane; modifier click jumps to Conversations tab with `topic:<name>`. |

### Known deferrals

- Descriptive community labels (currently auto-labeled "Community N" by graphifyy). Would need integration with `graphify.report._safe_community_name` or similar. Out of Phase 8 scope.
- Wire-level path-traversal HTTP tests. httpx's ASGITransport URL-decodes `%2F` → `/` before the test client reaches the ASGI interface, which routes the request to the SPA catch-all instead of hitting the `{slug}` handler. The service-level `test_safe_wiki_path_rejects_traversal_with_parent` is the definitive coverage of the guard.

---

## v2.0.0 — 2026-04-14

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
