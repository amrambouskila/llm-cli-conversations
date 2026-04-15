import { useState, useEffect, useCallback } from "react";
import Dashboard from "./components/Dashboard";
import KnowledgeGraph from "./components/KnowledgeGraph";
import Header from "./components/Header";
import ConversationsTab from "./components/ConversationsTab";
import {
  fetchProjects,
  fetchStats,
  triggerUpdate,
  fetchProjectsWithHidden,
} from "./api";
import { exportMarkdown, formatStatsText } from "./utils";
import { useTheme } from "./hooks/useTheme";
import { useBackendReady } from "./hooks/useBackendReady";
import { useProviders } from "./hooks/useProviders";
import { useSummaryTitles } from "./hooks/useSummaryTitles";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useResizeHandles } from "./hooks/useResizeHandles";
import { useProjectSelection } from "./hooks/useProjectSelection";
import { useSearch } from "./hooks/useSearch";
import { useHideRestore } from "./hooks/useHideRestore";

export default function App() {
  const { theme, setTheme } = useTheme();
  const backendReady = useBackendReady();
  const providers = useProviders();
  const { summaryTitles, handleTitleReady } = useSummaryTitles();
  const [provider, setProvider] = useState("claude");
  const [projects, setProjects] = useState([]);
  const [stats, setStats] = useState(null);
  const [showHidden, setShowHidden] = useState(false);

  const {
    selectedProject,
    segments,
    selectedSegmentId,
    segmentDetail,
    convViewData,
    loadSegments,
    setSegments,
    handleSelectProject: selectProject,
    handleDeselectProject,
    handleSelectSegment,
    handleViewConversation,
    loadProjectConversation,
    resetAll: resetSelection,
  } = useProjectSelection(provider, showHidden);

  const [requestsHeader, setRequestsHeader] = useState("Requests");

  const handleSearchStart = useCallback(
    (query) => setRequestsHeader(`Search: "${query}"`),
    []
  );
  const handleSearchCleared = useCallback(
    (project) => setRequestsHeader(`Requests \u2014 ${project}`),
    []
  );

  const {
    searchQuery,
    setSearchQuery,
    isSearching,
    searchResults,
    filterOptions,
    searchMode,
    dateFrom,
    dateTo,
    pendingDateFrom,
    setPendingDateFrom,
    pendingDateTo,
    setPendingDateTo,
    showDateFilter,
    setShowDateFilter,
    searchRef,
    applyDateFilter,
    clearDateFilter,
    resetSearch,
    isInSearchMode,
  } = useSearch({
    provider,
    backendReady,
    selectedProject,
    loadSegments,
    setSegments,
    onSearchStart: handleSearchStart,
    onSearchCleared: handleSearchCleared,
  });

  const [isUpdating, setIsUpdating] = useState(false);
  const [updateStatus, setUpdateStatus] = useState(null);

  // Pane widths (resizable)
  const {
    projectsWidth,
    requestsWidth,
    metadataWidth,
    wikiWidth,
    mainRef,
    wikiContainerRef,
    startDrag,
  } = useResizeHandles();

  const [activeTab, setActiveTab] = useState("conversations");

  const loadProjects = useCallback(() => {
    const fn = showHidden ? fetchProjectsWithHidden : fetchProjects;
    return fn(provider);
  }, [showHidden, provider]);

  // Reset selection when switching provider
  const handleProviderChange = useCallback((newProvider) => {
    setProvider(newProvider);
    resetSelection();
    setRequestsHeader("Requests");
    resetSearch();
  }, [resetSelection, resetSearch]);

  const handleSelectProject = useCallback(async (name) => {
    await selectProject(name);
    setRequestsHeader(`Requests \u2014 ${name}`);
    setSearchQuery("");
  }, [selectProject, setSearchQuery]);

  const handleDeselectProjectWithHeader = useCallback(() => {
    handleDeselectProject();
    setRequestsHeader("Requests");
  }, [handleDeselectProject]);

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
  }, [loadProjects, provider]);

  const {
    refreshAfterStateChange,
    handleHideSegment,
    handleRestoreSegment,
    handleHideConversation,
    handleRestoreConversation,
    handleHideProject,
    handleRestoreProject,
    handleRestoreAll,
  } = useHideRestore({
    provider,
    selectedProject,
    loadProjects,
    loadSegments,
    setProjects,
    setStats,
    setSegments,
  });

  const handleSelectSearchResult = useCallback(async (result) => {
    const project = result.project;
    const conversationId = result.conversation_id;
    if (!project || !conversationId) return;
    await loadProjectConversation(project, conversationId);
    setRequestsHeader(`Requests \u2014 ${project}`);
  }, [loadProjectConversation]);

  const handleExport = useCallback(
    (mode) => exportMarkdown(mode, convViewData, segmentDetail),
    [segmentDetail, convViewData]
  );

  const handleDashboardNavigate = useCallback(async (project, conversationId, searchTerm) => {
    setActiveTab("conversations");
    if (searchTerm) {
      setSearchQuery(searchTerm);
      return;
    }
    if (project && conversationId) {
      await loadProjectConversation(project, conversationId);
      setRequestsHeader(`Requests \u2014 ${project}`);
    }
  }, [loadProjectConversation, setSearchQuery]);

  const handleOpenConceptInConversations = useCallback((conceptName) => {
    setActiveTab("conversations");
    setSearchQuery(`topic:${conceptName}`);
  }, [setSearchQuery]);

  const handleUpdate = useCallback(async () => {
    setIsUpdating(true); setUpdateStatus(null);
    try {
      const result = await triggerUpdate();
      if (result.success) { setUpdateStatus("success"); await refreshAfterStateChange(); }
      else { setUpdateStatus("error"); console.error("Update failed:", result.error); }
    } catch (err) { setUpdateStatus("error"); console.error(err); }
    finally { setIsUpdating(false); setTimeout(() => setUpdateStatus(null), 4000); }
  }, [refreshAfterStateChange]);

  useKeyboardShortcuts({
    searchRef,
    segments,
    selectedSegmentId,
    onSelectSegment: handleSelectSegment,
    onClearSearch: resetSearch,
  });

  const statsText = formatStatsText(stats, provider);

  const hiddenTotal = stats?.hidden ? stats.hidden.segments + stats.hidden.conversations + stats.hidden.projects : 0;
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
      <Header
        providers={providers}
        provider={provider}
        onProviderChange={handleProviderChange}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        statsText={statsText}
        showHidden={showHidden}
        onToggleShowHidden={() => setShowHidden(!showHidden)}
        hiddenTotal={hiddenTotal}
        onRestoreAll={handleRestoreAll}
        theme={theme}
        onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
        isUpdating={isUpdating}
        updateStatus={updateStatus}
        onUpdate={handleUpdate}
      />

      {activeTab === "conversations" && (
        <ConversationsTab
          searchRef={searchRef}
          searchQuery={searchQuery}
          onQueryChange={setSearchQuery}
          searchMode={searchMode}
          showDateFilter={showDateFilter}
          onToggleDateFilter={() => setShowDateFilter(!showDateFilter)}
          isSearching={isSearching}
          isInSearchMode={isInSearchMode}
          searchResults={searchResults}
          onSelectSearchResult={handleSelectSearchResult}
          filterOptions={filterOptions}
          pendingDateFrom={pendingDateFrom}
          onPendingDateFromChange={setPendingDateFrom}
          pendingDateTo={pendingDateTo}
          onPendingDateToChange={setPendingDateTo}
          dateFrom={dateFrom}
          dateTo={dateTo}
          onApplyDateFilter={applyDateFilter}
          onClearDateFilter={clearDateFilter}
          mainRef={mainRef}
          startDrag={startDrag}
          projectsWidth={projectsWidth}
          requestsWidth={requestsWidth}
          metadataWidth={metadataWidth}
          projects={projects}
          selectedProject={selectedProject}
          onSelectProject={handleSelectProject}
          onDeselectProject={handleDeselectProjectWithHeader}
          onHideProject={handleHideProject}
          onRestoreProject={handleRestoreProject}
          showHidden={showHidden}
          requestsHeader={requestsHeader}
          segments={segments}
          selectedSegmentId={selectedSegmentId}
          onSelectSegment={handleSelectSegment}
          onViewConversation={handleViewConversation}
          onHideSegment={handleHideSegment}
          onRestoreSegment={handleRestoreSegment}
          onHideConversation={handleHideConversation}
          onRestoreConversation={handleRestoreConversation}
          showProject={showProject}
          summaryTitles={summaryTitles}
          viewingMarkdown={viewingMarkdown}
          viewingSource={viewingSource}
          onExport={handleExport}
          convViewData={convViewData}
          segmentDetail={segmentDetail}
          provider={provider}
          onTitleReady={handleTitleReady}
          selectedProjectData={selectedProjectData}
          stats={stats}
        />
      )}

      {activeTab === "dashboard" && (
        <Dashboard provider={provider} onNavigateToConversation={handleDashboardNavigate} />
      )}

      {activeTab === "graph" && (
        <KnowledgeGraph
          provider={provider}
          onOpenInConversations={handleOpenConceptInConversations}
          wikiContainerRef={wikiContainerRef}
          wikiWidth={wikiWidth}
          startDrag={startDrag}
        />
      )}
    </div>
  );
}
