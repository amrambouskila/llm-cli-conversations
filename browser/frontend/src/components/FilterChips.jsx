import { useState, useRef, useEffect } from "react";

const FILTER_PREFIXES = [
  { label: "project", prefix: "project:", placeholder: "project name" },
  { label: "model", prefix: "model:", placeholder: "model name" },
  { label: "tool", prefix: "tool:", placeholder: "tool name" },
  { label: "topic", prefix: "topic:", placeholder: "topic" },
  { label: "after", prefix: "after:", placeholder: "YYYY-MM-DD" },
  { label: "before", prefix: "before:", placeholder: "YYYY-MM-DD" },
  { label: "cost >", prefix: "cost:>", placeholder: "amount" },
  { label: "turns >", prefix: "turns:>", placeholder: "count" },
];

export default function FilterChips({ filterOptions, searchQuery, onQueryChange }) {
  const [activeDropdown, setActiveDropdown] = useState(null);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setActiveDropdown(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleChipClick = (filter) => {
    const key = filter.prefix.replace(":", "").replace(">", "");
    const optionsKey = key === "project" ? "projects" : key === "model" ? "models" : key + "s";
    const options = filterOptions?.[optionsKey];

    if (options && options.length > 0) {
      setActiveDropdown(activeDropdown === key ? null : key);
    } else {
      // No autocomplete options — just insert the prefix
      const newQuery = searchQuery + (searchQuery ? " " : "") + filter.prefix;
      onQueryChange(newQuery);
    }
  };

  const handleOptionSelect = (prefix, value) => {
    const newQuery = searchQuery + (searchQuery ? " " : "") + prefix + value;
    onQueryChange(newQuery);
    setActiveDropdown(null);
  };

  // Parse active filters from the current query
  const activeFilters = [];
  const filterRegex = /\b(project|model|provider|after|before|tool|topic):(\S+)/gi;
  const costRegex = /cost:>(\S+)/gi;
  const turnsRegex = /turns:>(\S+)/gi;
  let match;
  while ((match = filterRegex.exec(searchQuery)) !== null) {
    activeFilters.push({ type: match[1].toLowerCase(), value: match[2] });
  }
  while ((match = costRegex.exec(searchQuery)) !== null) {
    activeFilters.push({ type: "cost", value: ">" + match[1] });
  }
  while ((match = turnsRegex.exec(searchQuery)) !== null) {
    activeFilters.push({ type: "turns", value: ">" + match[1] });
  }

  const removeFilter = (type, value) => {
    let newQuery = searchQuery;
    if (type === "cost") {
      newQuery = newQuery.replace(/cost:>\S+/i, "").trim();
    } else if (type === "turns") {
      newQuery = newQuery.replace(/turns:>\S+/i, "").trim();
    } else {
      const regex = new RegExp(`${type}:${value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "i");
      newQuery = newQuery.replace(regex, "").trim();
    }
    newQuery = newQuery.replace(/\s+/g, " ").trim();
    onQueryChange(newQuery);
  };

  return (
    <div className="filter-chips-container" ref={dropdownRef}>
      <div className="filter-chips">
        {FILTER_PREFIXES.map((filter) => {
          const key = filter.prefix.replace(":", "").replace(">", "");
          return (
            <div key={key} className="filter-chip-wrapper">
              <button
                className={`filter-chip${activeDropdown === key ? " filter-chip-active" : ""}`}
                onClick={() => handleChipClick(filter)}
              >
                {filter.label}
              </button>
              {activeDropdown === key && (
                <FilterDropdown
                  filter={filter}
                  options={getOptionsForFilter(filter, filterOptions)}
                  onSelect={(value) => handleOptionSelect(filter.prefix, value)}
                />
              )}
            </div>
          );
        })}
      </div>
      {activeFilters.length > 0 && (
        <div className="active-filters">
          {activeFilters.map((f, i) => (
            <span key={i} className="active-filter-tag">
              {f.type}: {f.value}
              <button
                className="active-filter-remove"
                onClick={() => removeFilter(f.type, f.value)}
              >
                &times;
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function getOptionsForFilter(filter, filterOptions) {
  if (!filterOptions) return [];
  const key = filter.prefix.replace(":", "").replace(">", "");
  if (key === "project") return filterOptions.projects || [];
  if (key === "model") return filterOptions.models || [];
  if (key === "tool") return filterOptions.tools || [];
  if (key === "topic") return filterOptions.topics || [];
  return [];
}

function FilterDropdown({ filter, options, onSelect }) {
  const [filterText, setFilterText] = useState("");

  const filtered = options.filter((o) =>
    o.toLowerCase().includes(filterText.toLowerCase())
  );

  return (
    <div className="filter-dropdown">
      <input
        className="filter-dropdown-search"
        type="text"
        placeholder={`Filter ${filter.label}...`}
        value={filterText}
        onChange={(e) => setFilterText(e.target.value)}
        autoFocus
        onClick={(e) => e.stopPropagation()}
      />
      <div className="filter-dropdown-list">
        {filtered.length === 0 && (
          <div className="filter-dropdown-empty">No matches</div>
        )}
        {filtered.slice(0, 20).map((opt) => (
          <div
            key={opt}
            className="filter-dropdown-item"
            onClick={(e) => {
              e.stopPropagation();
              onSelect(opt);
            }}
          >
            {opt}
          </div>
        ))}
      </div>
    </div>
  );
}