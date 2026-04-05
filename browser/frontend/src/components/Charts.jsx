import React from "react";
import { formatNumber } from "../utils";

// Muted color palette for charts
const TOOL_COLORS = [
  "var(--accent)", "var(--accent2)", "var(--tool-badge)",
  "#cba6f7", "#f38ba8", "#89dceb", "#fab387", "#94e2d5",
  "#f5c2e7", "#74c7ec", "#a6e3a1", "#eba0ac",
];

/**
 * 1. ToolBreakdownChart — horizontal bars showing tool usage
 */
export function ToolBreakdownChart({ breakdown }) {
  if (!breakdown || Object.keys(breakdown).length === 0) return null;

  const entries = Object.entries(breakdown).sort((a, b) => b[1] - a[1]);
  const max = entries[0][1];

  return (
    <div className="chart-section">
      <div className="chart-title">Tool Usage</div>
      <div className="tool-breakdown">
        {entries.map(([name, count], i) => (
          <div key={name} className="tool-bar-row">
            <span className="tool-bar-label">{name}</span>
            <div className="tool-bar-track">
              <div
                className="tool-bar-fill"
                style={{
                  width: `${(count / max) * 100}%`,
                  background: TOOL_COLORS[i % TOOL_COLORS.length],
                }}
              />
            </div>
            <span className="tool-bar-count">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * 2. ConversationTimeline — dot plot showing when conversations occurred
 */
export function ConversationTimeline({ timestamps, firstTs, lastTs }) {
  if (!timestamps || timestamps.length < 2) return null;

  const start = new Date(firstTs || timestamps[0]).getTime();
  const end = new Date(lastTs || timestamps[timestamps.length - 1]).getTime();
  const range = end - start || 1;

  return (
    <div className="chart-section">
      <div className="chart-title">Conversation Timeline</div>
      <div className="timeline-track">
        {timestamps.map((ts, i) => {
          const pos = ((new Date(ts).getTime() - start) / range) * 100;
          return (
            <div
              key={i}
              className="timeline-dot"
              style={{ left: `${pos}%` }}
              title={new Date(ts).toLocaleDateString()}
            />
          );
        })}
      </div>
      <div className="timeline-labels">
        <span>{new Date(start).toLocaleDateString()}</span>
        <span>{new Date(end).toLocaleDateString()}</span>
      </div>
    </div>
  );
}

/**
 * 3. TokenCostEstimate — shows cost next to token count
 *    Provider-aware: Claude uses Sonnet/Opus pricing, Codex uses GPT-4o/o3 pricing.
 *    We assume ~80% input, ~20% output for a conversation segment.
 *
 *    Claude:  Sonnet $3/$15, Opus $15/$75 per M tokens (input/output)
 *    OpenAI:  GPT-4o $2.50/$10, o3 $10/$40 per M tokens (input/output)
 */
const PRICING = {
  claude: [
    { label: "Sonnet", inputPerM: 3, outputPerM: 15 },
    { label: "Opus",   inputPerM: 15, outputPerM: 75 },
  ],
  codex: [
    { label: "GPT-4o", inputPerM: 2.5, outputPerM: 10 },
    { label: "o3",     inputPerM: 10, outputPerM: 40 },
  ],
};

export function TokenCostEstimate({ tokens, provider = "claude" }) {
  if (!tokens) return null;

  const inputTokens = Math.round(tokens * 0.8);
  const outputTokens = Math.round(tokens * 0.2);
  const models = PRICING[provider] || PRICING.claude;

  return (
    <div className="chart-section">
      <div className="chart-title">Estimated Cost</div>
      <div className="cost-grid">
        {models.map((m) => {
          const cost = (inputTokens * m.inputPerM + outputTokens * m.outputPerM) / 1_000_000;
          return (
            <div key={m.label} className="cost-row">
              <span className="cost-label">{m.label}</span>
              <span className="cost-value">${cost.toFixed(4)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * 4. RequestSizeSparkline — mini bar chart of word counts per request
 */
export function RequestSizeSparkline({ sizes }) {
  if (!sizes || sizes.length < 2) return null;

  const max = Math.max(...sizes);
  const barWidth = Math.max(1, Math.min(6, Math.floor(200 / sizes.length)));

  return (
    <div className="chart-section">
      <div className="chart-title">Request Sizes</div>
      <div className="sparkline-container">
        <svg
          width="100%"
          height="40"
          viewBox={`0 0 ${sizes.length * (barWidth + 1)} 40`}
          preserveAspectRatio="none"
        >
          {sizes.map((size, i) => {
            const h = max > 0 ? (size / max) * 36 : 1;
            return (
              <rect
                key={i}
                x={i * (barWidth + 1)}
                y={40 - h}
                width={barWidth}
                height={h}
                rx={1}
                fill="var(--accent)"
                opacity={0.7}
              >
                <title>{formatNumber(size)} words</title>
              </rect>
            );
          })}
        </svg>
        <div className="sparkline-labels">
          <span>{formatNumber(Math.min(...sizes))} min</span>
          <span>{formatNumber(Math.max(...sizes))} max</span>
        </div>
      </div>
    </div>
  );
}

/**
 * 5. MonthlyBreakdown — table of monthly tokens and costs
 */
export function MonthlyBreakdown({ monthly, provider = "claude" }) {
  if (!monthly || Object.keys(monthly).length === 0) return null;

  const entries = Object.entries(monthly);
  const models = PRICING[provider] || PRICING.claude;

  return (
    <div className="chart-section">
      <div className="chart-title">Monthly Breakdown</div>
      <div className="monthly-table">
        <div className="monthly-row monthly-header-row">
          <span>Month</span>
          <span>Requests</span>
          <span>Tokens</span>
          {models.map((m) => <span key={m.label}>{m.label}</span>)}
        </div>
        {entries.map(([month, d]) => {
          const inp = Math.round(d.tokens * 0.8);
          const out = Math.round(d.tokens * 0.2);
          return (
            <div key={month} className="monthly-row">
              <span>{month}</span>
              <span>{d.requests}</span>
              <span>{formatNumber(d.tokens)}</span>
              {models.map((m) => {
                const cost = (inp * m.inputPerM + out * m.outputPerM) / 1_000_000;
                return <span key={m.label} className="cost-value">${cost.toFixed(2)}</span>;
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * 6. ProjectSizeBar — thin bar showing relative project size (for ProjectList)
 */
export function ProjectSizeBar({ size, maxSize }) {
  if (!maxSize || maxSize === 0) return null;
  const pct = (size / maxSize) * 100;

  return (
    <div className="project-size-bar-track">
      <div
        className="project-size-bar-fill"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
