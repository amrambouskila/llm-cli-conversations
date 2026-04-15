import MetadataPanel from "./MetadataPanel";
import {
  TokenCostEstimate,
  MonthlyBreakdown,
  ToolBreakdownChart,
  ConversationTimeline,
  RequestSizeSparkline,
} from "./Charts";
import { formatNumber, formatTimestamp } from "../utils";
import { useCostBreakdown } from "../hooks/useCostBreakdown";

function formatUsd(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "$0.00";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function CostAttribution({ sessionId, metrics }) {
  const { data, loading, error } = useCostBreakdown(sessionId);

  if (!sessionId) return null;
  if (loading) {
    return (
      <div className="chart-section">
        <div className="chart-title">Cost Attribution</div>
        <div className="cost-attribution-empty">Loading cost breakdown…</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="chart-section">
        <div className="chart-title">Cost Attribution</div>
        <div className="cost-attribution-empty">
          Could not load cost breakdown.
        </div>
      </div>
    );
  }
  if (!data) return null;

  // Token counts may not be in the /cost-breakdown response — the breakdown
  // returns only USD. Display per-bucket $ only; if per-bucket tokens become
  // useful later, add them to the endpoint.
  const rows = [
    { label: "Input", usd: data.input_usd },
    { label: "Output", usd: data.output_usd },
    { label: "Cache read", usd: data.cache_read_usd },
    { label: "Cache write", usd: data.cache_create_usd },
  ];

  return (
    <div className="chart-section">
      <div className="chart-title">Cost Attribution</div>
      <div className="cost-attribution-grid">
        {rows.map((r) => (
          <div key={r.label} className="cost-attribution-row">
            <span className="cost-attribution-label">{r.label}</span>
            <span className="cost-attribution-value">{formatUsd(r.usd)}</span>
          </div>
        ))}
        <div className="cost-attribution-row cost-attribution-total">
          <span className="cost-attribution-label">Total</span>
          <span className="cost-attribution-value">{formatUsd(data.total_usd)}</span>
        </div>
      </div>
      {metrics?.estimated_tokens ? (
        <div className="cost-attribution-note">
          {formatNumber(metrics.estimated_tokens)} estimated tokens total
        </div>
      ) : null}
    </div>
  );
}

function ConversationMetadata({ convViewData }) {
  return (
    <div className="metadata-panel">
      <h4>Conversation View</h4>
      <div className="metadata-list">
        <div className="meta-item">
          <span className="label">Conversation</span>
          <span className="value">{convViewData.conversation_id}</span>
        </div>
        <div className="meta-item">
          <span className="label">Segments</span>
          <span className="value">{convViewData.segment_count}</span>
        </div>
        <div className="meta-item">
          <span className="label">Words</span>
          <span className="value">
            {formatNumber(convViewData.metrics.word_count)}
          </span>
        </div>
        <div className="meta-item">
          <span className="label">Est. Tokens</span>
          <span className="value">
            {formatNumber(convViewData.metrics.estimated_tokens)}
          </span>
        </div>
        <div className="meta-item">
          <span className="label">Tool Calls</span>
          <span className="value">{convViewData.metrics.tool_call_count}</span>
        </div>
      </div>
      <CostAttribution
        sessionId={convViewData.session_id}
        metrics={convViewData.metrics}
      />
    </div>
  );
}

function ProjectMetadata({ project }) {
  const stats = project.stats;
  return (
    <div className="metadata-panel">
      <h4>Project: {project.display_name}</h4>
      <div className="metadata-list">
        <div className="meta-item">
          <span className="label">Requests</span>
          <span className="value">{project.total_requests}</span>
        </div>
        <div className="meta-item">
          <span className="label">Conversations</span>
          <span className="value">{stats?.total_conversations}</span>
        </div>
        <div className="meta-item">
          <span className="label">Words</span>
          <span className="value">{formatNumber(stats?.total_words || 0)}</span>
        </div>
        <div className="meta-item">
          <span className="label">Est. Tokens</span>
          <span className="value">
            {formatNumber(stats?.estimated_tokens || 0)}
          </span>
        </div>
        <div className="meta-item">
          <span className="label">Tool Calls</span>
          <span className="value">{stats?.total_tool_calls}</span>
        </div>
        {stats?.first_timestamp && (
          <div className="meta-item">
            <span className="label">First Activity</span>
            <span className="value">
              {formatTimestamp(stats.first_timestamp)}
            </span>
          </div>
        )}
        {stats?.last_timestamp && (
          <div className="meta-item">
            <span className="label">Last Activity</span>
            <span className="value">
              {formatTimestamp(stats.last_timestamp)}
            </span>
          </div>
        )}
      </div>
      <RequestSizeSparkline sizes={stats?.request_sizes} />
      <ConversationTimeline
        timestamps={stats?.conversation_timeline}
        firstTs={stats?.first_timestamp}
        lastTs={stats?.last_timestamp}
      />
      <ToolBreakdownChart breakdown={stats?.tool_breakdown} />
    </div>
  );
}

function GlobalStats({ stats, provider }) {
  return (
    <div className="metadata-panel metadata-panel-global">
      <h4>Global Totals</h4>
      <div className="metadata-list">
        <div className="meta-item">
          <span className="label">Projects</span>
          <span className="value">{stats.total_projects}</span>
        </div>
        <div className="meta-item">
          <span className="label">Total Requests</span>
          <span className="value">{stats.total_segments}</span>
        </div>
        <div className="meta-item">
          <span className="label">Total Words</span>
          <span className="value">{formatNumber(stats.total_words)}</span>
        </div>
        <div className="meta-item">
          <span className="label">Total Tokens</span>
          <span className="value">{formatNumber(stats.estimated_tokens)}</span>
        </div>
        <div className="meta-item">
          <span className="label">Total Tool Calls</span>
          <span className="value">{stats.total_tool_calls}</span>
        </div>
      </div>
      <TokenCostEstimate tokens={stats.estimated_tokens} provider={provider} />
      <MonthlyBreakdown monthly={stats.monthly} provider={provider} />
    </div>
  );
}

export default function MetadataPane({
  width,
  convViewData,
  segmentDetail,
  selectedProjectData,
  stats,
  provider,
}) {
  return (
    <div className="pane pane-metadata" style={{ width, flexShrink: 0 }}>
      <div className="pane-header">Metadata</div>
      <div className="pane-content">
        {convViewData && <ConversationMetadata convViewData={convViewData} />}
        {!convViewData && segmentDetail && (
          <MetadataPanel segment={segmentDetail} provider={provider} />
        )}
        {!convViewData && !segmentDetail && selectedProjectData && (
          <ProjectMetadata project={selectedProjectData} />
        )}
        {stats && <GlobalStats stats={stats} provider={provider} />}
      </div>
    </div>
  );
}
