import RequestList from "./RequestList";
import SearchResults from "./SearchResults";

export default function RequestsPane({
  width,
  header,
  isSearching,
  isInSearchMode,
  searchResults,
  searchQuery,
  onSelectSearchResult,
  segments,
  selectedSegmentId,
  onSelectSegment,
  selectedProject,
  onViewConversation,
  onHideSegment,
  onRestoreSegment,
  onHideConversation,
  onRestoreConversation,
  showProject,
  showHidden,
  dateFrom,
  dateTo,
  summaryTitles,
}) {
  return (
    <div className="pane pane-requests" style={{ width }}>
      <div className="pane-header">{header}</div>
      <div className="pane-content">
        {isSearching ? (
          <div className="loading">Searching...</div>
        ) : isInSearchMode && searchResults ? (
          <SearchResults
            results={searchResults}
            onSelectSession={onSelectSearchResult}
            searchQuery={searchQuery}
          />
        ) : segments.length > 0 ? (
          <RequestList
            segments={segments}
            selectedId={selectedSegmentId}
            onSelect={onSelectSegment}
            onViewConversation={selectedProject ? onViewConversation : null}
            onHideSegment={onHideSegment}
            onRestoreSegment={onRestoreSegment}
            onHideConversation={onHideConversation}
            onRestoreConversation={onRestoreConversation}
            showProject={showProject}
            showHidden={showHidden}
            dateFrom={dateFrom}
            dateTo={dateTo}
            summaryTitles={summaryTitles}
            projectName={selectedProject}
          />
        ) : selectedProject ? (
          <div className="empty-state">No requests found</div>
        ) : (
          <div className="empty-state">Select a project</div>
        )}
      </div>
    </div>
  );
}
