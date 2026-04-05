import React, { useState, useMemo } from "react";
import { formatNumber, formatTimestamp } from "../utils";

function groupByConversation(segments) {
  const map = new Map();
  for (const s of segments) {
    const key = s.conversation_id || "__none__";
    if (!map.has(key)) {
      map.set(key, {
        conversationId: s.conversation_id,
        firstTimestamp: s.timestamp,
        segments: [],
      });
    }
    map.get(key).segments.push(s);
  }
  return Array.from(map.values());
}

export default function RequestList({
  segments,
  selectedId,
  onSelect,
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
  projectName,
}) {
  const [collapsed, setCollapsed] = useState(new Set());

  const filtered = useMemo(() => {
    if (!dateFrom && !dateTo) return segments;
    // Parse date picker values as local midnight boundaries
    const fromMs = dateFrom ? new Date(dateFrom + "T00:00:00").getTime() : null;
    const toMs = dateTo ? new Date(dateTo + "T23:59:59.999").getTime() : null;
    return segments.filter((s) => {
      if (!s.timestamp) return true;
      const ms = new Date(s.timestamp).getTime();
      if (fromMs && ms < fromMs) return false;
      if (toMs && ms > toMs) return false;
      return true;
    });
  }, [segments, dateFrom, dateTo]);

  const groups = useMemo(() => groupByConversation(filtered), [filtered]);

  if (!filtered.length) {
    return <div className="empty-state">No requests found</div>;
  }

  const toggleConversation = (convId) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(convId)) next.delete(convId);
      else next.add(convId);
      return next;
    });
  };

  const singleConversation = groups.length === 1;
  let globalIndex = 0;

  // Check if entire conversation is hidden (all segments hidden)
  const isConvFullyHidden = (group) =>
    group.segments.length > 0 && group.segments.every((s) => s.hidden);

  return (
    <>
      {groups.map((group) => {
        const convKey = group.conversationId || "__none__";
        const isCollapsed = collapsed.has(convKey);
        const convShort = group.conversationId
          ? group.conversationId.substring(0, 8)
          : "unknown";
        // Use summary title for conversation if available
        const convTitleKey = projectName && group.conversationId
          ? `conv_${projectName}_${group.conversationId}`
          : null;
        const convTitle = convTitleKey && summaryTitles?.[convTitleKey];
        const convHidden = isConvFullyHidden(group);

        return (
          <div key={convKey}>
            {!singleConversation && (
              <div className={`conv-header${convHidden ? " conv-hidden" : ""}`}>
                <span
                  className="conv-toggle"
                  onClick={() => toggleConversation(convKey)}
                >
                  {isCollapsed ? "\u25b6" : "\u25bc"}
                </span>
                <span
                  className="conv-label"
                  onClick={() => toggleConversation(convKey)}
                >
                  {convTitle || convShort}
                </span>
                <span className="conv-count">
                  {group.segments.length} request{group.segments.length !== 1 ? "s" : ""}
                </span>
                {onViewConversation && group.conversationId && (
                  <button
                    className="conv-view-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onViewConversation(group.conversationId);
                    }}
                    title="View full conversation"
                  >
                    Full
                  </button>
                )}
                {/* Hide/restore entire conversation */}
                {group.conversationId && onHideConversation && !convHidden && (
                  <button
                    className="conv-action-btn conv-hide-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onHideConversation(group.conversationId);
                    }}
                    title="Hide entire conversation"
                  >
                    &times;
                  </button>
                )}
                {group.conversationId && onRestoreConversation && convHidden && (
                  <button
                    className="conv-action-btn conv-restore-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRestoreConversation(group.conversationId);
                    }}
                    title="Restore conversation"
                  >
                    Restore
                  </button>
                )}
                {group.firstTimestamp && (
                  <span
                    className="conv-ts"
                    onClick={() => toggleConversation(convKey)}
                  >
                    {formatTimestamp(group.firstTimestamp)}
                  </span>
                )}
              </div>
            )}

            {(!isCollapsed || singleConversation) &&
              group.segments.map((s) => {
                globalIndex++;
                const localIndex = globalIndex;
                const isHidden = s.hidden;
                const toolBadge =
                  s.metrics.tool_call_count > 0 ? (
                    <span className="badge badge-tools">
                      {s.metrics.tool_call_count} tools
                    </span>
                  ) : null;

                return (
                  <div
                    key={s.id}
                    className={`request-item${!singleConversation ? " request-item-nested" : ""}${selectedId === s.id ? " selected" : ""}${isHidden ? " request-hidden" : ""}`}
                    onClick={() => onSelect(s.id)}
                  >
                    <div className="req-index">
                      {showProject ? (
                        <span style={{ color: "var(--accent)" }}>
                          {s.project_name}
                        </span>
                      ) : null}
                      {showProject ? " \u00b7 " : ""}
                      #{localIndex}
                      {isHidden && <span className="badge badge-hidden">hidden</span>}
                    </div>
                    <div className="req-preview">
                      {summaryTitles?.[s.id] || s.preview}
                    </div>
                    <div className="req-meta">
                      {s.timestamp ? (
                        <span>{formatTimestamp(s.timestamp)}</span>
                      ) : null}
                      <span>{formatNumber(s.metrics.word_count)} words</span>
                      {toolBadge}
                      {/* Hide / Restore button */}
                      {!isHidden && onHideSegment && (
                        <button
                          className="req-hide-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            onHideSegment(s.id);
                          }}
                          title="Hide this request"
                        >
                          &times;
                        </button>
                      )}
                      {isHidden && onRestoreSegment && (
                        <button
                          className="req-restore-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            onRestoreSegment(s.id);
                          }}
                          title="Restore this request"
                        >
                          Restore
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        );
      })}
    </>
  );
}
