import React from "react";
import { formatNumber, formatTimestamp } from "../utils";
import { ToolBreakdownChart, TokenCostEstimate } from "./Charts";

export default function MetadataPanel({ segment, provider = "claude" }) {
  if (!segment) return null;

  const items = [
    ["Project", segment.project_name],
    ["Segment #", segment.segment_index + 1],
    ["Conversation", segment.conversation_id || "N/A"],
    ["Entry #", segment.entry_number || "N/A"],
    ["Timestamp", formatTimestamp(segment.timestamp)],
    ["Characters", formatNumber(segment.metrics.char_count)],
    ["Words", formatNumber(segment.metrics.word_count)],
    ["Lines", formatNumber(segment.metrics.line_count)],
    ["Est. Tokens", formatNumber(segment.metrics.estimated_tokens)],
    ["Tool Calls", segment.metrics.tool_call_count],
    ["Source File", segment.source_file.split("/").pop()],
  ];

  return (
    <div className="metadata-panel">
      <div className="metadata-list">
        {items.map(([label, value]) => (
          <div className="meta-item" key={label}>
            <span className="label">{label}</span>
            <span className="value">{String(value)}</span>
          </div>
        ))}
      </div>
      <TokenCostEstimate tokens={segment.metrics.estimated_tokens} provider={provider} />
      <ToolBreakdownChart breakdown={segment.tool_breakdown} />
    </div>
  );
}
