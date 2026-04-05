import React, { useState, useMemo } from "react";
import { formatNumber, formatTimestamp } from "../utils";
import {
  ProjectSizeBar,
  RequestSizeSparkline,
  ConversationTimeline,
  ToolBreakdownChart,
} from "./Charts";

export default function ProjectList({
  projects,
  selected,
  onSelect,
  onHideProject,
  onRestoreProject,
  showHidden,
  dateFrom,
  dateTo,
}) {
  const [expandedStats, setExpandedStats] = useState(null);

  // Filter projects by date range — hide projects with no activity in the range
  const filtered = useMemo(() => {
    if (!dateFrom && !dateTo) return projects;
    const fromMs = dateFrom ? new Date(dateFrom + "T00:00:00").getTime() : null;
    const toMs = dateTo ? new Date(dateTo + "T23:59:59.999").getTime() : null;
    return projects.filter((p) => {
      const first = p.stats?.first_timestamp;
      const last = p.stats?.last_timestamp;
      if (!first || !last) return false;
      // Project is outside range if it ended before fromDate or started after toDate
      if (fromMs && new Date(last).getTime() < fromMs) return false;
      if (toMs && new Date(first).getTime() > toMs) return false;
      return true;
    });
  }, [projects, dateFrom, dateTo]);

  // Compute max word count across all projects for the size bar
  const maxWords = useMemo(
    () => Math.max(1, ...filtered.map((p) => p.stats?.total_words || 0)),
    [filtered]
  );

  if (!filtered.length) {
    return <div className="empty-state">No projects found</div>;
  }

  return (
    <>
      {filtered.map((p) => {
        const isExpanded = expandedStats === p.name;
        const s = p.stats;
        const isHidden = p.hidden;
        return (
          <div key={p.name}>
            <div
              className={`project-item${selected === p.name ? " selected" : ""}${isHidden ? " project-hidden" : ""}`}
              onClick={() => onSelect(p.name)}
            >
              {/* Size bar behind the project name */}
              {s && <ProjectSizeBar size={s.total_words} maxSize={maxWords} />}
              <div className="name">
                {p.display_name}
                {isHidden && <span className="badge badge-hidden">hidden</span>}
              </div>
              <div className="meta">
                {p.total_requests} requests
                {s && (
                  <span
                    className="stats-toggle"
                    onClick={(e) => {
                      e.stopPropagation();
                      setExpandedStats(isExpanded ? null : p.name);
                    }}
                    title="Toggle project stats"
                  >
                    {isExpanded ? " \u25b4" : " \u25be"}
                  </span>
                )}
                {!isHidden && onHideProject && (
                  <button
                    className="project-hide-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onHideProject(p.name);
                    }}
                    title="Hide this project"
                  >
                    &times;
                  </button>
                )}
                {isHidden && onRestoreProject && (
                  <button
                    className="project-restore-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRestoreProject(p.name);
                    }}
                    title="Restore this project"
                  >
                    Restore
                  </button>
                )}
              </div>
            </div>
            {isExpanded && s && (
              <div className="project-stats">
                <div className="project-stat">
                  <span>Conversations</span><span>{s.total_conversations}</span>
                </div>
                <div className="project-stat">
                  <span>Words</span><span>{formatNumber(s.total_words)}</span>
                </div>
                <div className="project-stat">
                  <span>Est. Tokens</span><span>{formatNumber(s.estimated_tokens)}</span>
                </div>
                <div className="project-stat">
                  <span>Tool Calls</span><span>{s.total_tool_calls}</span>
                </div>
                {s.first_timestamp && (
                  <div className="project-stat">
                    <span>First</span><span>{formatTimestamp(s.first_timestamp)}</span>
                  </div>
                )}
                {s.last_timestamp && (
                  <div className="project-stat">
                    <span>Last</span><span>{formatTimestamp(s.last_timestamp)}</span>
                  </div>
                )}
                <RequestSizeSparkline sizes={s.request_sizes} />
                <ConversationTimeline
                  timestamps={s.conversation_timeline}
                  firstTs={s.first_timestamp}
                  lastTs={s.last_timestamp}
                />
                <ToolBreakdownChart breakdown={s.tool_breakdown} />
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}
