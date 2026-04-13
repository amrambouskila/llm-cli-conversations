import React, { useState, useEffect, useCallback, useRef } from "react";
import ProjectList from "./components/ProjectList";
import RequestList from "./components/RequestList";
import SearchResults from "./components/SearchResults";
import FilterChips from "./components/FilterChips";
import ContentViewer from "./components/ContentViewer";
import MetadataPanel from "./components/MetadataPanel";
import Dashboard from "./components/Dashboard";
import KnowledgeGraph from "./components/KnowledgeGraph";
import {
  TokenCostEstimate,
  MonthlyBreakdown,
  ToolBreakdownChart,
  ConversationTimeline,
  RequestSizeSparkline,
} from "./components/Charts";
import {
  fetchProjects,
  fetchSegments,
  fetchSegmentDetail,
  fetchConversation,
  searchSessions,
  fetchSearchFilters,
  fetchSearchStatus,
  fetchStats,
  triggerUpdate,
  hideSegment,
  restoreSegment,
  hideConversation,
  restoreConversation,
  hideProject,
  restoreProject,
  restoreAll,
  fetchProjectsWithHidden,
  fetchSegmentsWithHidden,
  fetchSummaryTitles,
  fetchProviders,
  fetchReady,
} from "./api";
import { formatNumber, formatTimestamp } from "./utils";

export default function App() {
  const [backendReady, setBackendReady] = useState(false);
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("claude");
  const [projects, setProjects] = useState([]);
  const [stats, setStats] = useState(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");

  const [selectedProject, setSelectedProject] = useState(null);
  const [segments, setSegments] = useState([]);
  const [selectedSegmentId, setSelectedSegmentId] = useState(null);
  const [segmentDetail, setSegmentDetail] = useState(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [filterOptions, setFilterOptions] = useState(null);
  const [searchMode, setSearchMode] = useState(null);
  const searchRef = useRef(null);
  const searchTimerRef = useRef(null);

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [pendingDateFrom, setPendingDateFrom] = useState("");
  const [pendingDateTo, setPendingDateTo] = useState("");
  const [showDateFilter, setShowDateFilter] = useState(false);

  const [requestsHeader, setRequestsHeader] = useState("Requests");

  const [isUpdating, setIsUpdating] = useState(false);
  const [updateStatus, setUpdateStatus] = useState(null);

  const [convViewData, setConvViewData] = useState(null);

  // Pane widths (resizable)
  const [projectsWidth, setProjectsWidth] = useState(220);
  const [requestsWidth, setRequestsWidth] = useState(340);
  const [metadataWidth, setMetadataWidth] = useState(364);
  const dragging = useRef(null);
  const mainRef = useRef(null);

  const [activeTab, setActiveTab] = useState("conversations");
  const [showHidden, setShowHidden] = useState(false);
  const [summaryTitles, setSummaryTitles] = useState({});

  // Apply theme
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  // Poll backend readiness
  useEffect(() => {
    let timer = null;
    const check = () => {
      fetchReady()
        .then((r) => {
          if (r.ready) setBackendReady(true);
          else timer = setTimeout(check, 1000);
        })
        .catch(() => { timer = setTimeout(check, 1000); });
    };
    check();
    return () => { if (timer) clearTimeout(timer); };
  }, []);

  // Poll search status until both hybrid mode and graph are active
  useEffect(() => {
    if (!backendReady) return;
    let timer = null;
    let cancelled = false;
    const poll = () => {
      fetchSearchStatus(provider)
        .then((s) => {
          if (cancelled) return;
          setSearchMode(s);
          const settled = s.mode === "hybrid" && s.has_graph;
          if (!settled) timer = setTimeout(poll, 5000);
        })
        .catch(() => {
          if (!cancelled) timer = setTimeout(poll, 10000);
        });
    };
    poll();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [backendReady, provider]);

  const loadProjects = useCallback(() => {
    const fn = showHidden ? fetchProjectsWithHidden : fetchProjects;
    return fn(provider);
  }, [showHidden, provider]);

  const loadSegments = useCallback((name) => {
    const fn = showHidden ? fetchSegmentsWithHidden : fetchSegments;
    return fn(name, provider);
  }, [showHidden, provider]);

  // Load providers on mount
  useEffect(() => {
    fetchProviders().then(setProviders).catch(console.error);
  }, []);

  // Reset selection when switching provider
  const handleProviderChange = useCallback((newProvider) => {
    setProvider(newProvider);
    setSelectedProject(null);
    setSegments([]);
    setSelectedSegmentId(null);
    setSegmentDetail(null);
    setConvViewData(null);
    setRequestsHeader("Requests");
    setSearchQuery("");
    setSearchResults(null);
  }, []);

  // Load data when provider or showHidden changes
  useEffect(() => {
    loadProjects().then((ps) => {
      ps.sort((a, b) => {
        const ta = a.stats?.last_timestamp || "";
        const tb = b.stats?.last_timestamp || "";
        return tb.localeCompare(ta);
      });
      setProjects(ps);
    }).catch(console.error);
    fetchStats(provider).then(setStats).catch(console.error);
    fetchSummaryTitles().then(setSummaryTitles).catch(console.error);
    fetchSearchFilters(provider).then(setFilterOptions).catch(console.error);
  }, [loadProjects, provider]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchSummaryTitles().then(setSummaryTitles).catch(() => {});
    }, 10_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedProject) {
      loadSegments(selectedProject).then(setSegments).catch(console.error);
    }
  }, [showHidden, selectedProject, loadSegments]);

  const refreshAfterStateChange = useCallback(async () => {
    const [newProjects, newStats] = await Promise.all([loadProjects(), fetchStats(provider)]);
    newProjects.sort((a, b) => (b.stats?.last_timestamp || "").localeCompare(a.stats?.last_timestamp || ""));
    setProjects(newProjects);
    setStats(newStats);
    if (selectedProject) {
      const segs = await loadSegments(selectedProject);
      setSegments(segs);
    }
  }, [selectedProject, loadProjects, loadSegments]);

  const handleSelectProject = useCallback(async (name) => {
    setSelectedProject(name);
    setSelectedSegmentId(null);
    setSegmentDetail(null);
    setConvViewData(null);
    setRequestsHeader(`Requests \u2014 ${name}`);
    setSearchQuery("");
    try {
      const fn = showHidden ? fetchSegmentsWithHidden : fetchSegments;
      setSegments(await fn(name, provider));
    } catch (err) { console.error(err); }
  }, [showHidden, provider]);

  const handleDeselectProject = useCallback(() => {
    setSelectedProject(null);
    setSegments([]);
    setSelectedSegmentId(null);
    setSegmentDetail(null);
    setConvViewData(null);
    setRequestsHeader("Requests");
  }, []);

  const handleSelectSegment = useCallback(async (segId) => {
    setSelectedSegmentId(segId);
    setConvViewData(null);
    try { setSegmentDetail(await fetchSegmentDetail(segId, provider)); }
    catch (err) { console.error(err); }
  }, [provider]);

  const handleViewConversation = useCallback(async (conversationId) => {
    if (!selectedProject) return;
    try {
      setConvViewData(await fetchConversation(selectedProject, conversationId, provider));
      setSelectedSegmentId(null);
      setSegmentDetail(null);
    } catch (err) { console.error(err); }
  }, [selectedProject, provider]);

  const handleSelectSearchResult = useCallback(async (result) => {
    // Navigate to the conversation from a search result
    const project = result.project;
    const conversationId = result.conversation_id;
    if (!project || !conversationId) return;
    setSelectedProject(project);
    try {
      const segs = await (showHidden ? fetchSegmentsWithHidden : fetchSegments)(project, provider);
      setSegments(segs);
      setConvViewData(await fetchConversation(project, conversationId, provider));
      setSelectedSegmentId(null);
      setSegmentDetail(null);
      setRequestsHeader(`Requests \u2014 ${project}`);
    } catch (err) { console.error(err); }
  }, [showHidden, provider]);

  const handleTitleReady = useCallback((key, title) => {
    setSummaryTitles((prev) => ({ ...prev, [key]: title }));
  }, []);

  const handleExport = useCallback(async (mode) => {
    const md = convViewData?.raw_markdown || segmentDetail?.raw_markdown;
    const name = convViewData
      ? `${convViewData.project_name}_conversation_${convViewData.conversation_id.substring(0, 8)}.md`
      : `${segmentDetail.project_name}_request_${segmentDetail.segment_index + 1}.md`;
    if (!md) return;
    if (mode === "copy") {
      try { await navigator.clipboard.writeText(md); }
      catch {
        const ta = document.createElement("textarea");
        ta.value = md; document.body.appendChild(ta); ta.select();
        document.execCommand("copy"); document.body.removeChild(ta);
      }
    } else if (mode === "download") {
      const blob = new Blob([md], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
    }
  }, [segmentDetail, convViewData]);

  const handleHideSegment = useCallback(async (segId) => {
    try { await hideSegment(segId); await refreshAfterStateChange(); } catch (err) { console.error(err); }
  }, [refreshAfterStateChange]);
  const handleRestoreSegment = useCallback(async (segId) => {
    try { await restoreSegment(segId); await refreshAfterStateChange(); } catch (err) { console.error(err); }
  }, [refreshAfterStateChange]);
  const handleHideConversation = useCallback(async (convId) => {
    if (!selectedProject) return;
    try { await hideConversation(selectedProject, convId); await refreshAfterStateChange(); } catch (err) { console.error(err); }
  }, [selectedProject, refreshAfterStateChange]);
  const handleRestoreConversation = useCallback(async (convId) => {
    if (!selectedProject) return;
    try { await restoreConversation(selectedProject, convId); await refreshAfterStateChange(); } catch (err) { console.error(err); }
  }, [selectedProject, refreshAfterStateChange]);
  const handleHideProject = useCallback(async (name) => {
    try { await hideProject(name); await refreshAfterStateChange(); } catch (err) { console.error(err); }
  }, [refreshAfterStateChange]);
  const handleRestoreProject = useCallback(async (name) => {
    try { await restoreProject(name); await refreshAfterStateChange(); } catch (err) { console.error(err); }
  }, [refreshAfterStateChange]);
  const handleRestoreAll = useCallback(async () => {
    try { await restoreAll(); await refreshAfterStateChange(); } catch (err) { console.error(err); }
  }, [refreshAfterStateChange]);

  const handleDashboardNavigate = useCallback(async (project, conversationId, searchTerm) => {
    setActiveTab("conversations");
    if (searchTerm) {
      setSearchQuery(searchTerm);
      return;
    }
    if (project && conversationId) {
      setSelectedProject(project);
      try {
        const segs = await (showHidden ? fetchSegmentsWithHidden : fetchSegments)(project, provider);
        setSegments(segs);
        setConvViewData(await fetchConversation(project, conversationId, provider));
        setSelectedSegmentId(null);
        setSegmentDetail(null);
        setRequestsHeader(`Requests \u2014 ${project}`);
      } catch (err) { console.error(err); }
    }
  }, [showHidden, provider]);

  const handleUpdate = useCallback(async () => {
    setIsUpdating(true); setUpdateStatus(null);
    try {
      const result = await triggerUpdate();
      if (result.success) { setUpdateStatus("success"); await refreshAfterStateChange(); }
      else { setUpdateStatus("error"); console.error("Update failed:", result.error); }
    } catch (err) { setUpdateStatus("error"); console.error(err); }
    finally { setIsUpdating(false); setTimeout(() => setUpdateStatus(null), 4000); }
  }, [refreshAfterStateChange]);

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (searchQuery.length < 2) {
      setIsSearching(false);
      setSearchResults(null);
      if (selectedProject && searchQuery.length === 0) {
        loadSegments(selectedProject).then((segs) => {
          setSegments(segs); setRequestsHeader(`Requests \u2014 ${selectedProject}`);
        }).catch(console.error);
      }
      return;
    }
    setIsSearching(true);
    searchTimerRef.current = setTimeout(async () => {
      setRequestsHeader(`Search: "${searchQuery}"`);
      try {
        const results = await searchSessions(searchQuery, provider);
        setSearchResults(results);
      } catch (err) { console.error(err); }
      setIsSearching(false);
    }, 300);
  }, [searchQuery, selectedProject, loadSegments]);

  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") { e.preventDefault(); searchRef.current?.focus(); }
      if (e.key === "Escape" && document.activeElement === searchRef.current) { setSearchQuery(""); searchRef.current.blur(); }
      if ((e.key === "ArrowDown" || e.key === "ArrowUp") && document.activeElement?.tagName !== "INPUT") {
        if (!segments.length) return;
        e.preventDefault();
        const idx = segments.findIndex((s) => s.id === selectedSegmentId);
        const next = e.key === "ArrowDown" ? (idx < segments.length - 1 ? idx + 1 : 0) : (idx > 0 ? idx - 1 : segments.length - 1);
        handleSelectSegment(segments[next].id);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [segments, selectedSegmentId, handleSelectSegment]);

  // Resizable panes — all 4 handles
  useEffect(() => {
    const onMove = (e) => {
      if (!dragging.current) return;
      e.preventDefault();
      const mainRect = mainRef.current?.getBoundingClientRect();
      if (!mainRect) return;
      if (dragging.current === "projects") {
        setProjectsWidth(Math.max(140, Math.min(400, e.clientX - mainRect.left)));
      } else if (dragging.current === "requests") {
        setRequestsWidth(Math.max(200, Math.min(600, e.clientX - mainRect.left - projectsWidth - 5)));
      } else if (dragging.current === "metadata") {
        setMetadataWidth(Math.max(250, Math.min(600, mainRect.right - e.clientX)));
      }
    };
    const onUp = () => { dragging.current = null; document.body.style.cursor = ""; };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => { document.removeEventListener("mousemove", onMove); document.removeEventListener("mouseup", onUp); };
  }, [projectsWidth]);

  const statsText = (() => {
    if (!stats) return "";
    const t = stats.estimated_tokens;
    const inp = Math.round(t * 0.8);
    const out = Math.round(t * 0.2);
    const models = provider === "codex"
      ? [{ l: "GPT-4o", i: 2.5, o: 10 }, { l: "o3", i: 10, o: 40 }]
      : [{ l: "Sonnet", i: 3, o: 15 }, { l: "Opus", i: 15, o: 75 }];
    const costs = models.map((m) => `${m.l} $${((inp * m.i + out * m.o) / 1e6).toFixed(2)}`).join(" | ");
    return `${stats.total_projects} projects | ${stats.total_segments} requests | ${formatNumber(stats.total_words)} words | ${formatNumber(t)} tokens | ${costs}`;
  })();

  const hiddenTotal = stats?.hidden ? stats.hidden.segments + stats.hidden.conversations + stats.hidden.projects : 0;
  const isInSearchMode = searchQuery.length >= 2;
  const showProject = isInSearchMode;
  const viewingMarkdown = convViewData?.raw_markdown || segmentDetail?.raw_markdown || null;
  const viewingSource = segmentDetail?.source_file || null;

  // Get selected project data for project-level analytics
  const selectedProjectData = selectedProject ? projects.find((p) => p.name === selectedProject) : null;

  if (!backendReady) {
    return (
      <div className="app">
        <div className="startup-loading">
          <h1>Conversation Browser</h1>
          <div className="startup-loading-bar">
            <div className="startup-loading-fill" />
          </div>
          <div className="startup-loading-text">Loading conversations into database...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="header">
        <div className="header-left">
          <h1>Conversation Browser</h1>
          {providers.length > 1 && (
            <select
              className="provider-select"
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value)}
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.projects} projects)
                </option>
              ))}
            </select>
          )}
          {providers.length <= 1 && (
            <span className="provider-label">{provider.charAt(0).toUpperCase() + provider.slice(1)}</span>
          )}
          <div className="header-tabs">
            <button
              className={`header-tab${activeTab === "conversations" ? " header-tab-active" : ""}`}
              onClick={() => setActiveTab("conversations")}
            >
              Conversations
            </button>
            <button
              className={`header-tab${activeTab === "dashboard" ? " header-tab-active" : ""}`}
              onClick={() => setActiveTab("dashboard")}
            >
              Dashboard
            </button>
            <button
              className={`header-tab${activeTab === "graph" ? " header-tab-active" : ""}`}
              onClick={() => setActiveTab("graph")}
            >
              Knowledge Graph
            </button>
          </div>
        </div>
        <div className="header-right">
          <div className="stats">{statsText}</div>
          <button className={`toolbar-btn${showHidden ? " toolbar-btn-active" : ""}`} onClick={() => setShowHidden(!showHidden)} title={showHidden ? "Hide deleted items" : "Show deleted items"}>
            Trash{hiddenTotal > 0 ? ` (${hiddenTotal})` : ""}
          </button>
          {showHidden && hiddenTotal > 0 && (
            <button className="toolbar-btn" onClick={handleRestoreAll} title="Restore all hidden items">Restore All</button>
          )}
          <button className="toolbar-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
            {theme === "dark" ? "Light" : "Dark"}
          </button>
          <button className={`update-btn${isUpdating ? " updating" : ""}${updateStatus === "success" ? " success" : ""}${updateStatus === "error" ? " error" : ""}`} onClick={handleUpdate} disabled={isUpdating} title="Sync latest conversations and re-index">
            {isUpdating ? "Updating..." : updateStatus === "success" ? "Updated" : updateStatus === "error" ? "Failed" : "Update"}
          </button>
        </div>
      </div>

      {activeTab === "conversations" && (
        <>
          <div className="search-bar">
            <input ref={searchRef} type="text" placeholder="Search conversations... (Cmd+K) — try project:name tool:Bash after:2026-01-01" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
            {searchMode && searchMode.mode !== "unavailable" && (
              <div className="search-mode-badges">
                <span className={`search-mode-badge search-mode-${searchMode.mode}`} title={
                  searchMode.mode === "hybrid"
                    ? `Hybrid search — ${searchMode.embedded_sessions}/${searchMode.total_sessions} sessions embedded`
                    : searchMode.mode === "embedding"
                    ? `Embedding in progress — ${searchMode.embedded_sessions}/${searchMode.total_sessions} sessions`
                    : "Keyword search only — embeddings generating..."
                }>
                  {searchMode.mode === "hybrid" ? "Hybrid" : searchMode.mode === "embedding" ? `Embedding ${Math.round((searchMode.embedded_sessions / searchMode.total_sessions) * 100)}%` : "Keyword"}
                </span>
                <span className={`search-mode-badge search-mode-graph-${searchMode.has_graph ? "on" : "off"}`} title={
                  searchMode.has_graph
                    ? `Knowledge graph active — ${searchMode.concept_count} concepts with community data`
                    : "Knowledge graph not loaded — community re-ranking inactive"
                }>
                  {searchMode.has_graph ? "Graph" : "No Graph"}
                </span>
              </div>
            )}
            <button className="toolbar-btn filter-toggle" onClick={() => setShowDateFilter(!showDateFilter)} title="Toggle filters">
              {showDateFilter ? "Hide Filters" : "Filters"}
            </button>
          </div>
          {showDateFilter && (
            <div className="filter-bar-expanded">
              <FilterChips filterOptions={filterOptions} searchQuery={searchQuery} onQueryChange={setSearchQuery} />
              <div className="date-filter-bar">
                <label>From:<input type="date" value={pendingDateFrom} onChange={(e) => setPendingDateFrom(e.target.value)} /></label>
                <label>To:<input type="date" value={pendingDateTo} onChange={(e) => setPendingDateTo(e.target.value)} /></label>
                <button className="toolbar-btn" onClick={() => { setDateFrom(pendingDateFrom); setDateTo(pendingDateTo); }}>Apply</button>
                {(dateFrom || dateTo) && <button className="toolbar-btn" onClick={() => { setDateFrom(""); setDateTo(""); setPendingDateFrom(""); setPendingDateTo(""); }}>Clear</button>}
              </div>
            </div>
          )}

          <div className="main" ref={mainRef}>
            {/* Pane 1: Projects */}
            <div className="pane pane-projects" style={{ width: projectsWidth }}>
              <div className="pane-header" style={{ cursor: selectedProject ? "pointer" : "default" }} onClick={selectedProject ? handleDeselectProject : undefined} title={selectedProject ? "Click to deselect project" : ""}>Projects{selectedProject ? " \u2190" : ""}</div>
              <div className="pane-content">
                <ProjectList projects={projects} selected={selectedProject} onSelect={handleSelectProject} onHideProject={handleHideProject} onRestoreProject={handleRestoreProject} showHidden={showHidden} dateFrom={dateFrom} dateTo={dateTo} />
              </div>
            </div>

            <div className="resize-handle" onMouseDown={() => { dragging.current = "projects"; }} />

            {/* Pane 2: Requests / Search Results */}
            <div className="pane pane-requests" style={{ width: requestsWidth }}>
              <div className="pane-header">{requestsHeader}</div>
              <div className="pane-content">
                {isSearching ? <div className="loading">Searching...</div>
                  : isInSearchMode && searchResults ? <SearchResults results={searchResults} onSelectSession={handleSelectSearchResult} searchQuery={searchQuery} />
                  : segments.length > 0 ? <RequestList segments={segments} selectedId={selectedSegmentId} onSelect={handleSelectSegment} onViewConversation={selectedProject ? handleViewConversation : null} onHideSegment={handleHideSegment} onRestoreSegment={handleRestoreSegment} onHideConversation={handleHideConversation} onRestoreConversation={handleRestoreConversation} showProject={showProject} showHidden={showHidden} dateFrom={dateFrom} dateTo={dateTo} summaryTitles={summaryTitles} projectName={selectedProject} />
                  : selectedProject ? <div className="empty-state">No requests found</div>
                  : <div className="empty-state">Select a project</div>}
              </div>
            </div>

            <div className="resize-handle" onMouseDown={() => { dragging.current = "requests"; }} />

            {/* Pane 3: Content viewer */}
            <div className="pane-content-area">
              <ContentViewer markdown={viewingMarkdown} searchQuery={searchQuery.length >= 2 ? searchQuery : null} onExport={viewingMarkdown ? handleExport : null} sourceFile={viewingSource} segmentId={convViewData ? null : selectedSegmentId} conversationId={convViewData ? convViewData.conversation_id : null} projectName={selectedProject} provider={provider} onTitleReady={handleTitleReady} />
            </div>

            {/* Resize handle for metadata */}
            <div className="resize-handle" onMouseDown={() => { dragging.current = "metadata"; }} />

            {/* Pane 4: Metadata */}
            <div className="pane pane-metadata" style={{ width: metadataWidth, flexShrink: 0 }}>
              <div className="pane-header">Metadata</div>
              <div className="pane-content">
                {/* Contextual: segment or conversation detail */}
                {convViewData && (
                  <div className="metadata-panel">
                    <h4>Conversation View</h4>
                    <div className="metadata-list">
                      <div className="meta-item"><span className="label">Conversation</span><span className="value">{convViewData.conversation_id}</span></div>
                      <div className="meta-item"><span className="label">Segments</span><span className="value">{convViewData.segment_count}</span></div>
                      <div className="meta-item"><span className="label">Words</span><span className="value">{formatNumber(convViewData.metrics.word_count)}</span></div>
                      <div className="meta-item"><span className="label">Est. Tokens</span><span className="value">{formatNumber(convViewData.metrics.estimated_tokens)}</span></div>
                      <div className="meta-item"><span className="label">Tool Calls</span><span className="value">{convViewData.metrics.tool_call_count}</span></div>
                    </div>
                    <TokenCostEstimate tokens={convViewData.metrics.estimated_tokens} provider={provider} />
                  </div>
                )}
                {!convViewData && segmentDetail && (
                  <MetadataPanel segment={segmentDetail} provider={provider} />
                )}

                {/* Project-level analytics (always shown when a project is selected) */}
                {!convViewData && !segmentDetail && selectedProjectData && (
                  <div className="metadata-panel">
                    <h4>Project: {selectedProjectData.display_name}</h4>
                    <div className="metadata-list">
                      <div className="meta-item"><span className="label">Requests</span><span className="value">{selectedProjectData.total_requests}</span></div>
                      <div className="meta-item"><span className="label">Conversations</span><span className="value">{selectedProjectData.stats?.total_conversations}</span></div>
                      <div className="meta-item"><span className="label">Words</span><span className="value">{formatNumber(selectedProjectData.stats?.total_words || 0)}</span></div>
                      <div className="meta-item"><span className="label">Est. Tokens</span><span className="value">{formatNumber(selectedProjectData.stats?.estimated_tokens || 0)}</span></div>
                      <div className="meta-item"><span className="label">Tool Calls</span><span className="value">{selectedProjectData.stats?.total_tool_calls}</span></div>
                      {selectedProjectData.stats?.first_timestamp && <div className="meta-item"><span className="label">First Activity</span><span className="value">{formatTimestamp(selectedProjectData.stats.first_timestamp)}</span></div>}
                      {selectedProjectData.stats?.last_timestamp && <div className="meta-item"><span className="label">Last Activity</span><span className="value">{formatTimestamp(selectedProjectData.stats.last_timestamp)}</span></div>}
                    </div>
                    <TokenCostEstimate tokens={selectedProjectData.stats?.estimated_tokens || 0} provider={provider} />
                    <RequestSizeSparkline sizes={selectedProjectData.stats?.request_sizes} />
                    <ConversationTimeline timestamps={selectedProjectData.stats?.conversation_timeline} firstTs={selectedProjectData.stats?.first_timestamp} lastTs={selectedProjectData.stats?.last_timestamp} />
                    <ToolBreakdownChart breakdown={selectedProjectData.stats?.tool_breakdown} />
                  </div>
                )}

                {/* Global stats + monthly — always visible at the bottom */}
                {stats && (
                  <div className="metadata-panel metadata-panel-global">
                    <h4>Global Totals</h4>
                    <div className="metadata-list">
                      <div className="meta-item"><span className="label">Projects</span><span className="value">{stats.total_projects}</span></div>
                      <div className="meta-item"><span className="label">Total Requests</span><span className="value">{stats.total_segments}</span></div>
                      <div className="meta-item"><span className="label">Total Words</span><span className="value">{formatNumber(stats.total_words)}</span></div>
                      <div className="meta-item"><span className="label">Total Tokens</span><span className="value">{formatNumber(stats.estimated_tokens)}</span></div>
                      <div className="meta-item"><span className="label">Total Tool Calls</span><span className="value">{stats.total_tool_calls}</span></div>
                    </div>
                    <TokenCostEstimate tokens={stats.estimated_tokens} provider={provider} />
                    <MonthlyBreakdown monthly={stats.monthly} provider={provider} />
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {activeTab === "dashboard" && (
        <Dashboard provider={provider} onNavigateToConversation={handleDashboardNavigate} />
      )}

      {activeTab === "graph" && (
        <KnowledgeGraph
          provider={provider}
          onConceptClick={(concept) => {
            setActiveTab("conversations");
            handleDashboardNavigate(null, null, `topic:${concept.name}`);
          }}
        />
      )}
    </div>
  );
}
