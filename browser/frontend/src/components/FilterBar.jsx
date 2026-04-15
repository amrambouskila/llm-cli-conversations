import FilterChips from "./FilterChips";

export default function FilterBar({
  filterOptions,
  searchQuery,
  onQueryChange,
  pendingDateFrom,
  onPendingDateFromChange,
  pendingDateTo,
  onPendingDateToChange,
  dateFrom,
  dateTo,
  onApply,
  onClear,
}) {
  return (
    <div className="filter-bar-expanded">
      <FilterChips
        filterOptions={filterOptions}
        searchQuery={searchQuery}
        onQueryChange={onQueryChange}
      />
      <div className="date-filter-bar">
        <label>
          From:
          <input
            type="date"
            value={pendingDateFrom}
            onChange={(e) => onPendingDateFromChange(e.target.value)}
          />
        </label>
        <label>
          To:
          <input
            type="date"
            value={pendingDateTo}
            onChange={(e) => onPendingDateToChange(e.target.value)}
          />
        </label>
        <button className="toolbar-btn" onClick={onApply}>
          Apply
        </button>
        {(dateFrom || dateTo) && (
          <button className="toolbar-btn" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
