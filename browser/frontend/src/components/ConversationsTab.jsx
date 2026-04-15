import SearchBar from "./SearchBar";
import FilterBar from "./FilterBar";
import ProjectsPane from "./ProjectsPane";
import RequestsPane from "./RequestsPane";
import ContentPane from "./ContentPane";
import MetadataPane from "./MetadataPane";

export default function ConversationsTab({
  // Search
  searchRef,
  searchQuery,
  onQueryChange,
  searchMode,
  showDateFilter,
  onToggleDateFilter,
  isSearching,
  isInSearchMode,
  searchResults,
  onSelectSearchResult,
  // Filter
  filterOptions,
  pendingDateFrom,
  onPendingDateFromChange,
  pendingDateTo,
  onPendingDateToChange,
  dateFrom,
  dateTo,
  onApplyDateFilter,
  onClearDateFilter,
  // Layout
  mainRef,
  startDrag,
  projectsWidth,
  requestsWidth,
  metadataWidth,
  // Projects
  projects,
  selectedProject,
  onSelectProject,
  onDeselectProject,
  onHideProject,
  onRestoreProject,
  showHidden,
  // Requests
  requestsHeader,
  segments,
  selectedSegmentId,
  onSelectSegment,
  onViewConversation,
  onHideSegment,
  onRestoreSegment,
  onHideConversation,
  onRestoreConversation,
  showProject,
  summaryTitles,
  // Content
  viewingMarkdown,
  viewingSource,
  onExport,
  convViewData,
  segmentDetail,
  provider,
  onTitleReady,
  // Metadata
  selectedProjectData,
  stats,
}) {
  return (
    <>
      <SearchBar
        searchRef={searchRef}
        searchQuery={searchQuery}
        onQueryChange={onQueryChange}
        searchMode={searchMode}
        showDateFilter={showDateFilter}
        onToggleDateFilter={onToggleDateFilter}
      />
      {showDateFilter && (
        <FilterBar
          filterOptions={filterOptions}
          searchQuery={searchQuery}
          onQueryChange={onQueryChange}
          pendingDateFrom={pendingDateFrom}
          onPendingDateFromChange={onPendingDateFromChange}
          pendingDateTo={pendingDateTo}
          onPendingDateToChange={onPendingDateToChange}
          dateFrom={dateFrom}
          dateTo={dateTo}
          onApply={onApplyDateFilter}
          onClear={onClearDateFilter}
        />
      )}
      <div className="main" ref={mainRef}>
        <ProjectsPane
          width={projectsWidth}
          projects={projects}
          selectedProject={selectedProject}
          onSelectProject={onSelectProject}
          onDeselectProject={onDeselectProject}
          onHideProject={onHideProject}
          onRestoreProject={onRestoreProject}
          showHidden={showHidden}
          dateFrom={dateFrom}
          dateTo={dateTo}
        />
        <div
          className="resize-handle"
          onMouseDown={() => startDrag("projects")}
        />
        <RequestsPane
          width={requestsWidth}
          header={requestsHeader}
          isSearching={isSearching}
          isInSearchMode={isInSearchMode}
          searchResults={searchResults}
          searchQuery={searchQuery}
          onSelectSearchResult={onSelectSearchResult}
          segments={segments}
          selectedSegmentId={selectedSegmentId}
          onSelectSegment={onSelectSegment}
          selectedProject={selectedProject}
          onViewConversation={onViewConversation}
          onHideSegment={onHideSegment}
          onRestoreSegment={onRestoreSegment}
          onHideConversation={onHideConversation}
          onRestoreConversation={onRestoreConversation}
          showProject={showProject}
          showHidden={showHidden}
          dateFrom={dateFrom}
          dateTo={dateTo}
          summaryTitles={summaryTitles}
        />
        <div
          className="resize-handle"
          onMouseDown={() => startDrag("requests")}
        />
        <ContentPane
          markdown={viewingMarkdown}
          searchQuery={searchQuery.length >= 2 ? searchQuery : null}
          onExport={viewingMarkdown ? onExport : null}
          sourceFile={viewingSource}
          segmentId={convViewData ? null : selectedSegmentId}
          conversationId={convViewData ? convViewData.conversation_id : null}
          projectName={selectedProject}
          provider={provider}
          onTitleReady={onTitleReady}
        />
        <div
          className="resize-handle"
          onMouseDown={() => startDrag("metadata")}
        />
        <MetadataPane
          width={metadataWidth}
          convViewData={convViewData}
          segmentDetail={segmentDetail}
          selectedProjectData={selectedProjectData}
          stats={stats}
          provider={provider}
        />
      </div>
    </>
  );
}
