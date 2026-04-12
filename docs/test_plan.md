# QA / UAT Test Plan — Conversation Browser

Living document. Updated as each phase lands. Run the full plan after every phase delivery to catch regressions. All tests assume the app is running at `http://localhost:5050` via Docker (`r + Enter` in launcher).

**How to use this document:**
- **After any phase delivery:** Run every section top to bottom. Sections are cumulative — new phases add tests, old tests stay.
- **Quick smoke test:** Run Section 1 (backend curl) and Section 7 (regression table). If those pass, the system is healthy.
- **Before committing:** Run Section 1 + the section for the phase you just built + Section 7 regression.

**Legend:**
- (P0–P2) = delivered in Phases 0–2 (Postgres, data loader, endpoint migration)
- (P3) = delivered in Phase 3 (search upgrade)
- (P4) = delivered in Phase 4 (dashboard) — tests added when phase lands
- (P5) = delivered in Phase 5 (semantic search) — tests added when phase lands

---

## 1. Backend API Smoke Tests (curl)

### 1.1 App Health

```bash
# App responds at all
curl -s -o /dev/null -w "%{http_code}" http://localhost:5050/
```

**Expected:** `200`. If not, check `docker compose logs llm-browser`.

### 1.2 Providers (P0)

```bash
curl -s "http://localhost:5050/api/providers" | python3 -m json.tool
```

**Expected:** Array with at least one object: `{ "id": "claude", "name": "Claude", "projects": <N> }`.

### 1.3 Projects list (P0)

```bash
curl -s "http://localhost:5050/api/projects?provider=claude" | python3 -m json.tool | head -20
```

**Expected:** Array of project objects with `name`, `display_name`, `total_requests`, `stats`.

### 1.4 Project segments (P0)

```bash
# Replace <PROJECT> with an actual project name from 1.3
curl -s "http://localhost:5050/api/projects/<PROJECT>/segments?provider=claude" | python3 -m json.tool | head -20
```

**Expected:** Array of segment objects with `id`, `source_file`, `project_name`, `segment_index`, `preview`, `timestamp`, `conversation_id`, `metrics`.

### 1.5 Segment detail (P0)

```bash
# Replace <SEGMENT_ID> with an actual segment id from 1.4
curl -s "http://localhost:5050/api/segments/<SEGMENT_ID>?provider=claude" | python3 -m json.tool | head -10
```

**Expected:** Full segment with `raw_markdown`, `tool_breakdown`, `metrics`.

### 1.6 Conversation view (P0)

```bash
# Replace <PROJECT> and <CONVERSATION_ID> from a segment in 1.4
curl -s "http://localhost:5050/api/projects/<PROJECT>/conversation/<CONVERSATION_ID>?provider=claude" | python3 -m json.tool | head -10
```

**Expected:** Object with `conversation_id`, `project_name`, `segment_count`, `raw_markdown`, `metrics`.

### 1.7 Stats (P0)

```bash
curl -s "http://localhost:5050/api/stats?provider=claude" | python3 -m json.tool
```

**Expected:** Object with `total_projects`, `total_segments`, `total_words`, `estimated_tokens`, `total_tool_calls`, `monthly`, `hidden`.

### 1.8 Search — session-level results (P3)

```bash
curl -s "http://localhost:5050/api/search?q=docker" | python3 -m json.tool | head -30
```

**Expected:** Array of session-level objects with keys: `session_id`, `project`, `date`, `model`, `cost`, `snippet`, `tool_summary`, `tools`, `turn_count`, `topics`, `conversation_id`, `rank`.

**Failure indicator:** Old segment-level shape with `id`, `segment_index`, `preview`, `metrics`.

### 1.9 Search — empty/short query (P3)

```bash
curl -s "http://localhost:5050/api/search?q=a"
curl -s "http://localhost:5050/api/search?q="
```

**Expected:** `[]` for both.

### 1.10 Search — project filter (P3)

```bash
curl -s "http://localhost:5050/api/search?q=project:conversations+docker" | python3 -m json.tool
```

**Expected:** All results have `"project": "conversations"`. Snippet/rank reflects "docker".

### 1.11 Search — tool filter (P3)

```bash
curl -s "http://localhost:5050/api/search?q=tool:Bash+error" | python3 -m json.tool
```

**Expected:** Every result's `tools` object contains a `"Bash"` key.

### 1.12 Search — date range (P3)

```bash
curl -s "http://localhost:5050/api/search?q=after:2026-03-01+before:2026-04-01" | python3 -m json.tool
```

**Expected:** All results have `date` between 2026-03-01 and 2026-04-01 inclusive.

### 1.13 Search — cost threshold (P3)

```bash
curl -s "http://localhost:5050/api/search?q=cost:>1.00" | python3 -m json.tool
```

**Expected:** All results have `cost > 1.00`.

### 1.14 Search — turns threshold (P3)

```bash
curl -s "http://localhost:5050/api/search?q=turns:>10" | python3 -m json.tool
```

**Expected:** All results have `turn_count > 10`.

### 1.15 Search — multiple filters combined (P3)

```bash
curl -s "http://localhost:5050/api/search?q=project:conversations+tool:Edit+after:2026-01-01+refactor" | python3 -m json.tool
```

**Expected:** Results match ALL filters simultaneously.

### 1.16 Search — model filter (P3)

```bash
curl -s "http://localhost:5050/api/search?q=model:opus" | python3 -m json.tool
```

**Expected:** Results where the model field contains "opus" (case-insensitive).

### 1.17 Search — topic filter (P3)

```bash
curl -s "http://localhost:5050/api/search?q=topic:docker" | python3 -m json.tool
```

**Expected:** Results where at least one session topic contains "docker".

### 1.18 Search — malformed filter is non-fatal (P3)

```bash
curl -s "http://localhost:5050/api/search?q=after:not-a-date+docker" | python3 -m json.tool
```

**Expected:** No crash. `after:not-a-date` left in free text.

### 1.19 Autocomplete endpoint (P3)

```bash
curl -s "http://localhost:5050/api/search/filters?provider=claude" | python3 -m json.tool
```

**Expected:** `{ "projects": [...], "models": [...], "tools": [...], "topics": [...] }`. All arrays non-empty and alphabetically sorted.

### 1.20 Related sessions endpoint (P3)

```bash
SESSION_ID=$(curl -s "http://localhost:5050/api/search?q=docker" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r[0]['session_id'] if r else '')")
curl -s "http://localhost:5050/api/sessions/${SESSION_ID}/related" | python3 -m json.tool
```

**Expected:** Array of 0–5 objects with `session_id`, `project`, `date`, `model`, `summary`, `shared_concepts`, `conversation_id`. Returns `[]` if no Graphify concept data exists.

### 1.21 Provider filter on search (P3)

```bash
curl -s "http://localhost:5050/api/search?q=docker&provider=codex" | python3 -m json.tool
```

**Expected:** Only codex results (or `[]` if no codex data matches).

### 1.22 Hide/restore segment (P2)

```bash
# Replace <SEGMENT_ID> with an actual id
curl -s -X POST "http://localhost:5050/api/hide/segment/<SEGMENT_ID>" | python3 -m json.tool
curl -s -X POST "http://localhost:5050/api/restore/segment/<SEGMENT_ID>" | python3 -m json.tool
```

**Expected:** Both return success. Segment hidden_at is set then cleared.

### 1.23 Update pipeline (P1)

```bash
curl -s -X POST "http://localhost:5050/api/update" | python3 -m json.tool
```

**Expected:** Object with `"success": true`, `projects`, `segments`, `log` array. Takes 10–60s depending on data volume.

<!-- Phase 4 tests will be added here -->
<!-- ### 1.24+ Dashboard endpoints (P4) -->

<!-- Phase 5 tests will be added here -->
<!-- ### 1.30+ Semantic search endpoint (P5) -->

---

## 2. SQL Verification (psql)

Connect:

```bash
docker exec -it conversations-postgres psql -U conversations -d conversations
```

### 2.1 Core table row counts (P1)

```sql
SELECT 'sessions' AS tbl, count(*) FROM conversations.sessions
UNION ALL SELECT 'segments', count(*) FROM conversations.segments
UNION ALL SELECT 'tool_calls', count(*) FROM conversations.tool_calls
UNION ALL SELECT 'session_topics', count(*) FROM conversations.session_topics;
```

**Expected:** Non-zero counts for all four.

### 2.2 tsvector index exists and works (P2)

```sql
SELECT s.id, s.session_id,
       ts_rank(s.search_vector, plainto_tsquery('english', 'docker')) AS rank
FROM conversations.segments s
WHERE s.search_vector @@ plainto_tsquery('english', 'docker')
ORDER BY rank DESC LIMIT 5;
```

**Expected:** Rows ranked by relevance. If zero rows, try a different term that exists in your data.

### 2.3 Session grouping for search (P3)

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

### 2.4 Metadata filter queries (P3)

```sql
-- project
SELECT id, project FROM conversations.sessions WHERE project = 'conversations' LIMIT 3;

-- date range
SELECT id, project, started_at FROM conversations.sessions
WHERE started_at >= '2026-03-01' AND started_at <= '2026-04-01T23:59:59' LIMIT 3;

-- cost threshold
SELECT id, project, estimated_cost FROM conversations.sessions
WHERE estimated_cost >= 1.00 ORDER BY estimated_cost DESC LIMIT 5;

-- turns threshold
SELECT id, project, turn_count FROM conversations.sessions
WHERE turn_count >= 10 ORDER BY turn_count DESC LIMIT 5;

-- tool filter
SELECT DISTINCT tc.session_id FROM conversations.tool_calls tc
WHERE tc.tool_name = 'Bash' LIMIT 5;
```

### 2.5 Autocomplete source queries (P3)

```sql
SELECT DISTINCT project FROM conversations.sessions WHERE hidden_at IS NULL ORDER BY project;
SELECT DISTINCT model FROM conversations.sessions WHERE model IS NOT NULL ORDER BY model;
SELECT DISTINCT tool_name FROM conversations.tool_calls ORDER BY tool_name;
SELECT DISTINCT topic FROM conversations.session_topics ORDER BY topic;
```

**Expected:** Each returns a non-empty, alphabetically sorted list.

### 2.6 Graphify concept data (P1, optional)

```sql
SELECT 'concepts' AS tbl, count(*) FROM conversations.concepts
UNION ALL SELECT 'session_concepts', count(*) FROM conversations.session_concepts;
```

**Expected:** If Graphify ran, both non-zero. If not, both 0 (and `/related` correctly returns `[]`).

### 2.7 Related sessions query (P3, if concept data exists)

```sql
-- Pick a session with concept data
SELECT session_id, count(concept_id) AS n
FROM conversations.session_concepts GROUP BY session_id ORDER BY n DESC LIMIT 1;

-- Find related (replace <SID>)
SELECT sc.session_id, count(DISTINCT sc.concept_id) AS shared
FROM conversations.session_concepts sc
WHERE sc.concept_id IN (
    SELECT concept_id FROM conversations.session_concepts WHERE session_id = '<SID>'
) AND sc.session_id != '<SID>'
GROUP BY sc.session_id ORDER BY shared DESC LIMIT 5;
```

### 2.8 Hidden state in database (P2)

```sql
SELECT count(*) AS hidden_sessions FROM conversations.sessions WHERE hidden_at IS NOT NULL;
SELECT count(*) AS hidden_segments FROM conversations.segments WHERE hidden_at IS NOT NULL;
```

**Expected:** Matches what the UI shows in the Trash count.

<!-- Phase 4: dashboard aggregation queries -->
<!-- Phase 5: embedding vector queries -->

---

## 3. UI — Browsing Flow (P0–P2)

Core three-pane browsing. Must work in every phase.

| # | Action | Expected |
|---|--------|----------|
| 1 | Open `http://localhost:5050` | App loads. Header shows title, provider, stats. Three panes visible. |
| 2 | Project list populated | Left pane shows project names sorted by most recent activity |
| 3 | Click a project | Middle pane loads segments grouped by conversation. Right pane shows project metadata. |
| 4 | Click a segment | Content viewer shows rendered markdown. Metadata panel shows segment detail (words, tokens, tools, cost estimate). |
| 5 | Click "Full" on a conversation header | Content viewer shows full concatenated conversation. Metadata shows conversation-level stats. |
| 6 | Click the "Projects" header (with back arrow) | Project deselected. Middle pane shows "Select a project". |
| 7 | Conversation collapse/expand | Click triangle on conversation header. Segments toggle visibility. Sticky header stays visible when scrolling. |

---

## 4. UI — Search Flow (P3)

### 4.1 Basic search

| # | Action | Expected |
|---|--------|----------|
| 1 | Type `docker` in search bar | After ~300ms debounce, middle pane shows **session cards** (not segment rows) |
| 2 | Inspect a session card | Shows: project name (blue, top-left), date (dim, top-right), model + cost line, 2–3 line snippet with "docker" highlighted, footer with tool summary, turn count, topics |
| 3 | Type single char `a` | No search fires, pane reverts to previous state |
| 4 | Clear search bar completely | Returns to normal browsing mode |
| 5 | Cmd+K | Search bar focused |
| 6 | Escape (while search bar focused) | Search bar clears, blur |

### 4.2 Click-to-navigate from search result

| # | Action | Expected |
|---|--------|----------|
| 1 | Search, then click a session card | Project selected in left pane, conversation loads in content viewer, middle pane switches to segment list for that project |
| 2 | Content viewer | Shows full conversation markdown for the clicked result |

### 4.3 Structured filter syntax (typed in search bar)

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

### 4.4 Provider switch clears search

| # | Action | Expected |
|---|--------|----------|
| 1 | Search for something | Results appear |
| 2 | Switch provider dropdown | Search bar clears, results clear, pane resets |

---

## 5. UI — Filter Chips (P3)

### 5.1 Toggle

| # | Action | Expected |
|---|--------|----------|
| 1 | Click "Filters" button (right of search bar) | Filter bar expands: chips row (project, model, tool, topic, after, before, cost >, turns >) plus date pickers |
| 2 | Click "Hide Filters" | Collapses |
| 3 | Re-expand | State preserved |

### 5.2 Autocomplete chips (project, model, tool, topic)

| # | Action | Expected |
|---|--------|----------|
| 1 | Click "project" chip | Dropdown with search input + scrollable list of all project names |
| 2 | Type in dropdown search | List filters in real time |
| 3 | Click a project name | `project:<name>` appended to search bar, dropdown closes, search triggers |
| 4 | Click "model" chip | Dropdown with model names |
| 5 | Click "tool" chip | Dropdown with tool names |
| 6 | Click "topic" chip | Dropdown with topic strings |

### 5.3 Non-autocomplete chips (after, before, cost, turns)

| # | Action | Expected |
|---|--------|----------|
| 1 | Click "after" chip | `after:` appended to search bar cursor (no dropdown) |
| 2 | Click "cost >" chip | `cost:>` appended |
| 3 | Click "turns >" chip | `turns:>` appended |

### 5.4 Active filter tags

| # | Action | Expected |
|---|--------|----------|
| 1 | Add a filter via chip | Tag appears below chips: "project: conversations" with X button |
| 2 | Add second filter | Second tag appears alongside first |
| 3 | Click X on a tag | Filter removed from search bar, search re-triggers |
| 4 | Clear search bar manually | All tags disappear |

### 5.5 Dropdown dismissal

| # | Action | Expected |
|---|--------|----------|
| 1 | Open dropdown, click outside | Closes |
| 2 | Open dropdown, click different chip | First closes, second opens |

---

## 6. UI — Date Filter (P0, extended P3)

| # | Action | Expected |
|---|--------|----------|
| 1 | Expand Filters, set From and To dates, click Apply | Segment list in browsing mode filters by date (client-side) |
| 2 | Click Clear | Date filter removed |
| 3 | Combine with search | Client-side date filter applies to browsing; `after:`/`before:` in search bar applies server-side to search results |

---

## 7. UI — Regression Checklist (run after every phase)

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
| 13 | Keyboard: Cmd+K | Focuses search bar |  |
| 14 | Keyboard: Escape | Clears and blurs search bar |  |
| 15 | Keyboard: Arrow keys | Navigate segments (when search bar not focused) |  |
| 16 | Resizable panes | Drag any resize handle | Pane widths change |
| 17 | Summary titles | Wait 10s or reload | Summary titles appear in request list |
| 18 | Provider switch | Change provider | Clears all state, loads new provider data |
| 19 | Search: session cards (P3+) | Type 2+ chars | Session-level cards, not segment rows |
| 20 | Search: click result (P3+) | Click a session card | Navigates to that conversation |
| 21 | Filter chips (P3+) | Open Filters, click a chip | Dropdown or prefix appended |
<!-- | 22 | Dashboard tab (P4+) | Click Dashboard tab | Dashboard view loads | -->
<!-- | 23 | Dashboard charts (P4+) | Inspect each chart | Data renders, hover tooltips work | -->
<!-- | 24 | Semantic search relevance (P5+) | Search vague query | Results are semantically relevant, not just keyword matches | -->

---

## 8. Edge Cases & Error Handling

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
<!-- | 15 | Dashboard with no data (P4) | Open dashboard with empty DB | Charts render empty states, no JS errors | -->
<!-- | 16 | Embedding column null (P5) | Search before embeddings generated | Falls back to keyword-only, no error | -->

---

## 9. Visual / Theme Checks

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
<!-- | Dashboard cards (P4) | Card backgrounds, text, borders | -->
<!-- | Dashboard charts (P4) | Chart colors, axes, tooltips, legends | -->

---

## 10. Performance Sanity

Not formal benchmarks — just "does it feel right."

| Check | How | Expected |
|-------|-----|----------|
| App startup | `docker compose up --build`, watch logs | < 60s to "Uvicorn running" (includes Postgres load) |
| Project list load | Click app, watch left pane | Appears within 1s |
| Segment list load | Click a project | Loads within 1–2s |
| Search response | Type a query | Results appear within 1s of debounce |
| Filter autocomplete | Open a chip dropdown | Options appear instantly (< 200ms) |
| Conversation view | Click "Full" on a large conversation | Loads within 2s |
| Content rendering | Scroll through a long conversation | No visible jank |
<!-- | Dashboard load (P4) | Click Dashboard tab | Charts render within 2s | -->
<!-- | Semantic search (P5) | Search vague query | Results within 2s | -->
