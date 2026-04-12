import React from "react";
import { formatTimestamp } from "../utils";

export default function SearchResults({ results, onSelectSession, searchQuery }) {
  if (!results || results.length === 0) {
    return <div className="empty-state">No results found</div>;
  }

  return (
    <div className="search-results">
      {results.map((r) => (
        <div
          key={r.session_id}
          className="search-result-card"
          onClick={() => onSelectSession(r)}
        >
          <div className="search-result-header">
            <span className="search-result-project">{r.project}</span>
            <span className="search-result-date">
              {r.date ? formatTimestamp(r.date) : ""}
            </span>
          </div>
          <div className="search-result-meta-line">
            {r.model && <span className="search-result-model">{r.model}</span>}
            {r.cost != null && (
              <span className="search-result-cost">${r.cost.toFixed(2)}</span>
            )}
          </div>
          <div className="search-result-snippet">
            {highlightSnippet(r.snippet || "", searchQuery)}
          </div>
          <div className="search-result-footer">
            {r.tool_summary && (
              <span className="search-result-tools">{r.tool_summary}</span>
            )}
            {r.turn_count != null && (
              <span className="search-result-turns">{r.turn_count} turns</span>
            )}
            {r.topics && r.topics.length > 0 && (
              <span className="search-result-topics">
                {r.topics.slice(0, 3).join(", ")}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function highlightSnippet(snippet, query) {
  if (!query || query.length < 2) return snippet;

  // Extract just the free-text portion (strip filter prefixes)
  const freeText = query
    .replace(/\b(project|model|provider|after|before|tool|topic|cost|turns):\S*/gi, "")
    .trim();

  if (!freeText || freeText.length < 2) return snippet;

  const terms = freeText.split(/\s+/).filter((t) => t.length >= 2);
  if (terms.length === 0) return snippet;

  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(${escaped.join("|")})`, "gi");

  const parts = snippet.split(regex);
  return parts.map((part, i) =>
    regex.test(part) ? (
      <mark key={i}>{part}</mark>
    ) : (
      <React.Fragment key={i}>{part}</React.Fragment>
    )
  );
}