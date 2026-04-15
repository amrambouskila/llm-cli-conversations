export default function SearchBar({
  searchRef,
  searchQuery,
  onQueryChange,
  searchMode,
  showDateFilter,
  onToggleDateFilter,
}) {
  return (
    <div className="search-bar">
      <input
        ref={searchRef}
        type="text"
        placeholder="Search conversations... (Cmd+K) — try project:name tool:Bash after:2026-01-01"
        value={searchQuery}
        onChange={(e) => onQueryChange(e.target.value)}
      />
      {searchMode && searchMode.mode !== "unavailable" && (
        <div className="search-mode-badges">
          <span
            className={`search-mode-badge search-mode-${searchMode.mode}`}
            title={
              searchMode.mode === "hybrid"
                ? `Hybrid search — ${searchMode.embedded_sessions}/${searchMode.total_sessions} sessions embedded`
                : searchMode.mode === "embedding"
                ? `Embedding in progress — ${searchMode.embedded_sessions}/${searchMode.total_sessions} sessions`
                : "Keyword search only — embeddings generating..."
            }
          >
            {searchMode.mode === "hybrid"
              ? "Hybrid"
              : searchMode.mode === "embedding"
              ? `Embedding ${Math.round(
                  (searchMode.embedded_sessions / searchMode.total_sessions) *
                    100
                )}%`
              : "Keyword"}
          </span>
          <span
            className={`search-mode-badge search-mode-graph-${
              searchMode.has_graph ? "on" : "off"
            }`}
            title={
              searchMode.has_graph
                ? `Knowledge graph active — ${searchMode.concept_count} concepts with community data`
                : "Knowledge graph not loaded — community re-ranking inactive"
            }
          >
            {searchMode.has_graph ? "Graph" : "No Graph"}
          </span>
        </div>
      )}
      <button
        className="toolbar-btn filter-toggle"
        onClick={onToggleDateFilter}
        title="Toggle filters"
      >
        {showDateFilter ? "Hide Filters" : "Filters"}
      </button>
    </div>
  );
}
