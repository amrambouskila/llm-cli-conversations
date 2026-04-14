import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Filler,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar, Line, Doughnut } from "react-chartjs-2";
import {
  fetchDashboardSummary,
  fetchDashboardCostOverTime,
  fetchDashboardProjects,
  fetchDashboardTools,
  fetchDashboardModels,
  fetchDashboardSessionTypes,
  fetchDashboardHeatmap,
  fetchDashboardAnomalies,
  fetchSearchFilters,
} from "../api";
import { formatNumber, formatTimestamp } from "../utils";
import Heatmap from "./Heatmap";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Filler,
  Tooltip,
  Legend
);

const DATE_PRESETS = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
  { label: "All", days: null },
];

const FAMILY_ORDER = ["file_ops", "search", "execution", "web", "planning", "other"];
const FAMILY_LABELS = {
  file_ops: "File Ops",
  search: "Search",
  execution: "Execution",
  web: "Web",
  planning: "Planning",
  other: "Other",
};

export default function Dashboard({ provider, onNavigateToConversation }) {
  const [filters, setFilters] = useState({
    provider: provider,
    date_from: "",
    date_to: "",
    project: "",
    model: "",
  });
  const [datePreset, setDatePreset] = useState("All");
  const [filterOptions, setFilterOptions] = useState(null);

  const [summary, setSummary] = useState(null);
  const [costOverTime, setCostOverTime] = useState([]);
  const [projectBreakdown, setProjectBreakdown] = useState([]);
  const [toolUsage, setToolUsage] = useState([]);
  const [modelComparison, setModelComparison] = useState([]);
  const [sessionTypes, setSessionTypes] = useState([]);
  const [heatmapData, setHeatmapData] = useState([]);
  const [anomalies, setAnomalies] = useState([]);

  const [costGroupBy, setCostGroupBy] = useState("week");
  const [costStackBy, setCostStackBy] = useState("project");
  const [anomalySort, setAnomalySort] = useState({ key: "cost", asc: false });

  const chartThemeRef = useRef({});

  // Read theme colors from CSS custom properties
  const readThemeColors = useCallback(() => {
    const style = getComputedStyle(document.documentElement);
    chartThemeRef.current = {
      text: style.getPropertyValue("--text").trim(),
      textDim: style.getPropertyValue("--text-dim").trim(),
      border: style.getPropertyValue("--border").trim(),
      accent: style.getPropertyValue("--accent").trim(),
      accent2: style.getPropertyValue("--accent2").trim(),
      bgSurface: style.getPropertyValue("--bg-surface").trim(),
      bgSurface2: style.getPropertyValue("--bg-surface2").trim(),
    };
  }, []);

  useEffect(() => {
    readThemeColors();
    const observer = new MutationObserver(readThemeColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [readThemeColors]);

  // Sync provider prop to filters
  useEffect(() => {
    setFilters((f) => ({ ...f, provider }));
  }, [provider]);

  // Build params for API calls
  const apiParams = useMemo(() => {
    const p = {};
    if (filters.provider) p.provider = filters.provider;
    if (filters.date_from) p.date_from = filters.date_from;
    if (filters.date_to) p.date_to = filters.date_to;
    if (filters.project) p.project = filters.project;
    if (filters.model) p.model = filters.model;
    return p;
  }, [filters]);

  // Fetch filter options
  useEffect(() => {
    fetchSearchFilters(filters.provider).then(setFilterOptions).catch(console.error);
  }, [filters.provider]);

  // Fetch all dashboard data
  useEffect(() => {
    const params = { ...apiParams };
    fetchDashboardSummary(params).then(setSummary).catch(console.error);
    fetchDashboardCostOverTime({ ...params, group_by: costGroupBy, stack_by: costStackBy }).then(setCostOverTime).catch(console.error);
    fetchDashboardProjects(params).then(setProjectBreakdown).catch(console.error);
    fetchDashboardTools(params).then(setToolUsage).catch(console.error);
    fetchDashboardModels(params).then(setModelComparison).catch(console.error);
    fetchDashboardSessionTypes(params).then(setSessionTypes).catch(console.error);
    fetchDashboardHeatmap(params).then(setHeatmapData).catch(console.error);
    fetchDashboardAnomalies(params).then(setAnomalies).catch(console.error);
  }, [apiParams, costGroupBy, costStackBy]);


  const handleDatePreset = useCallback((preset) => {
    setDatePreset(preset.label);
    if (preset.days === null) {
      setFilters((f) => ({ ...f, date_from: "", date_to: "" }));
    } else {
      const to = new Date();
      const from = new Date();
      from.setDate(from.getDate() - preset.days);
      setFilters((f) => ({
        ...f,
        date_from: from.toISOString().slice(0, 10),
        date_to: to.toISOString().slice(0, 10),
      }));
    }
  }, []);

  const handleFilterProject = useCallback((project) => {
    setFilters((f) => ({ ...f, project: f.project === project ? "" : project }));
  }, []);

  const handleFilterModel = useCallback((model) => {
    setFilters((f) => ({ ...f, model: f.model === model ? "" : model }));
  }, []);

  const handleAnomalyClick = useCallback((anomaly) => {
    if (onNavigateToConversation) {
      onNavigateToConversation(anomaly.project, anomaly.conversation_id);
    }
  }, [onNavigateToConversation]);

  const sortedAnomalies = useMemo(() => {
    const sorted = [...anomalies];
    sorted.sort((a, b) => {
      const va = a[anomalySort.key];
      const vb = b[anomalySort.key];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return anomalySort.asc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });
    return sorted;
  }, [anomalies, anomalySort]);

  const handleAnomalySort = useCallback((key) => {
    setAnomalySort((s) => ({
      key,
      asc: s.key === key ? !s.asc : false,
    }));
  }, []);

  // Chart palette
  const STACK_COLORS = [
    "#89b4fa", "#a6e3a1", "#f9e2af", "#cba6f7", "#f38ba8",
    "#89dceb", "#fab387", "#94e2d5", "#f5c2e7", "#74c7ec",
    "#b4befe", "#eba0ac",
  ];

  const SESSION_TYPE_COLORS = [
    "#89b4fa", "#a6e3a1", "#f9e2af", "#cba6f7", "#f38ba8", "#89dceb", "#fab387",
  ];

  // --- Chart.js configurations ---

  const defaultChartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: chartThemeRef.current.text || "#cdd6f4", font: { size: 11 } },
      },
      tooltip: {
        backgroundColor: chartThemeRef.current.bgSurface || "#252536",
        titleColor: chartThemeRef.current.text || "#cdd6f4",
        bodyColor: chartThemeRef.current.text || "#cdd6f4",
        borderColor: chartThemeRef.current.border || "#45455a",
        borderWidth: 1,
      },
    },
    scales: {
      x: {
        ticks: { color: chartThemeRef.current.textDim || "#8888aa", font: { size: 10 } },
        grid: { color: (chartThemeRef.current.border || "#45455a") + "33" },
      },
      y: {
        ticks: { color: chartThemeRef.current.textDim || "#8888aa", font: { size: 10 } },
        grid: { color: (chartThemeRef.current.border || "#45455a") + "33" },
      },
    },
  }), []);

  // Cost over time stacked area chart
  const costChartData = useMemo(() => {
    if (!costOverTime.length) return null;
    const labels = costOverTime.map((d) => d.period);
    const allStacks = new Set();
    for (const d of costOverTime) {
      for (const s of Object.keys(d.stacks)) allStacks.add(s);
    }
    const stackNames = [...allStacks];
    const datasets = stackNames.map((name, i) => ({
      label: name,
      data: costOverTime.map((d) => d.stacks[name] || 0),
      backgroundColor: STACK_COLORS[i % STACK_COLORS.length],
      borderColor: STACK_COLORS[i % STACK_COLORS.length],
      borderWidth: 2,
      fill: false,
      pointRadius: 0,
      tension: 0.25,
    }));
    return { labels, datasets };
  }, [costOverTime]);

  const costChartOptions = useMemo(() => ({
    ...defaultChartOptions,
    interaction: { mode: "index", intersect: false },
    scales: {
      ...defaultChartOptions.scales,
      x: { ...defaultChartOptions.scales.x, stacked: false },
      y: {
        ...defaultChartOptions.scales.y,
        stacked: false,
        ticks: {
          ...defaultChartOptions.scales.y.ticks,
          callback: (v) => "$" + v.toFixed(2),
        },
      },
    },
    plugins: {
      ...defaultChartOptions.plugins,
      tooltip: {
        ...defaultChartOptions.plugins.tooltip,
        callbacks: { label: (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}` },
      },
    },
  }), [defaultChartOptions]);

  // Project breakdown horizontal bar
  const projectChartData = useMemo(() => {
    if (!projectBreakdown.length) return null;
    const top = projectBreakdown.slice(0, 15);
    return {
      labels: top.map((p) => p.project),
      datasets: [{
        label: "Total Cost",
        data: top.map((p) => p.total_cost),
        backgroundColor: (chartThemeRef.current.accent || "#89b4fa") + "aa",
        borderColor: chartThemeRef.current.accent || "#89b4fa",
        borderWidth: 1,
      }],
    };
  }, [projectBreakdown]);

  const projectChartOptions = useMemo(() => ({
    ...defaultChartOptions,
    indexAxis: "y",
    onClick: (_event, elements) => {
      if (elements.length > 0) {
        const idx = elements[0].index;
        handleFilterProject(projectBreakdown[idx]?.project);
      }
    },
    plugins: {
      ...defaultChartOptions.plugins,
      legend: { display: false },
      tooltip: {
        ...defaultChartOptions.plugins.tooltip,
        callbacks: {
          label: (ctx) => `$${ctx.parsed.x.toFixed(2)}`,
          afterLabel: (ctx) => {
            const p = projectBreakdown[ctx.dataIndex];
            return p ? `${p.session_count} sessions, avg $${p.avg_cost_per_session.toFixed(2)}/session` : "";
          },
        },
      },
    },
    scales: {
      ...defaultChartOptions.scales,
      x: {
        ...defaultChartOptions.scales.x,
        ticks: {
          ...defaultChartOptions.scales.x.ticks,
          callback: (v) => "$" + v.toFixed(2),
        },
      },
    },
  }), [defaultChartOptions, projectBreakdown, handleFilterProject]);

  // Model comparison grouped bar
  const modelChartData = useMemo(() => {
    if (!modelComparison.length) return null;
    return {
      labels: modelComparison.map((m) => m.model || "unknown"),
      datasets: [
        {
          label: "Total Cost ($)",
          data: modelComparison.map((m) => m.total_cost),
          backgroundColor: STACK_COLORS[0] + "aa",
          borderColor: STACK_COLORS[0],
          borderWidth: 1,
        },
        {
          label: "Sessions",
          data: modelComparison.map((m) => m.total_sessions),
          backgroundColor: STACK_COLORS[1] + "aa",
          borderColor: STACK_COLORS[1],
          borderWidth: 1,
        },
      ],
    };
  }, [modelComparison]);

  const modelChartOptions = useMemo(() => ({
    ...defaultChartOptions,
    onClick: (_event, elements) => {
      if (elements.length > 0) {
        const idx = elements[0].index;
        handleFilterModel(modelComparison[idx]?.model);
      }
    },
    plugins: {
      ...defaultChartOptions.plugins,
      tooltip: {
        ...defaultChartOptions.plugins.tooltip,
        callbacks: {
          afterLabel: (ctx) => {
            const m = modelComparison[ctx.dataIndex];
            return m ? `Avg tokens/session: ${formatNumber(m.avg_tokens_per_session)}` : "";
          },
        },
      },
    },
  }), [defaultChartOptions, modelComparison, handleFilterModel]);

  // Tool usage horizontal bar (grouped by family)
  const toolChartData = useMemo(() => {
    if (!toolUsage.length) return null;
    // Group by family, then sort within each family
    const byFamily = {};
    for (const t of toolUsage) {
      const fam = t.family || "other";
      if (!byFamily[fam]) byFamily[fam] = [];
      byFamily[fam].push(t);
    }
    const labels = [];
    const values = [];
    const colors = [];
    const familyColors = {
      file_ops: STACK_COLORS[0],
      search: STACK_COLORS[1],
      execution: STACK_COLORS[2],
      web: STACK_COLORS[3],
      planning: STACK_COLORS[4],
      other: STACK_COLORS[5],
    };
    for (const fam of FAMILY_ORDER) {
      const tools = byFamily[fam];
      if (!tools) continue;
      tools.sort((a, b) => b.call_count - a.call_count);
      for (const t of tools) {
        labels.push(t.tool_name);
        values.push(t.call_count);
        colors.push(familyColors[fam] + "aa");
      }
    }
    return {
      labels,
      datasets: [{
        label: "Calls",
        data: values,
        backgroundColor: colors,
        borderWidth: 0,
      }],
    };
  }, [toolUsage]);

  const toolChartOptions = useMemo(() => ({
    ...defaultChartOptions,
    indexAxis: "y",
    plugins: {
      ...defaultChartOptions.plugins,
      legend: { display: false },
      tooltip: {
        ...defaultChartOptions.plugins.tooltip,
        callbacks: {
          afterLabel: (ctx) => {
            const t = toolUsage.find((tool) => tool.tool_name === ctx.label);
            return t ? `${t.session_count} sessions, Family: ${FAMILY_LABELS[t.family] || "Other"}` : "";
          },
        },
      },
    },
  }), [defaultChartOptions, toolUsage]);

  // Session type doughnut
  const typeChartData = useMemo(() => {
    if (!sessionTypes.length) return null;
    return {
      labels: sessionTypes.map((t) => t.session_type),
      datasets: [{
        data: sessionTypes.map((t) => t.count),
        backgroundColor: sessionTypes.map((_, i) => SESSION_TYPE_COLORS[i % SESSION_TYPE_COLORS.length] + "cc"),
        borderColor: sessionTypes.map((_, i) => SESSION_TYPE_COLORS[i % SESSION_TYPE_COLORS.length]),
        borderWidth: 1,
      }],
    };
  }, [sessionTypes]);

  const typeChartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "right",
        labels: { color: chartThemeRef.current.text || "#cdd6f4", font: { size: 11 }, padding: 8 },
      },
      tooltip: {
        ...defaultChartOptions.plugins.tooltip,
        callbacks: {
          label: (ctx) => {
            const t = sessionTypes[ctx.dataIndex];
            return t ? `${t.session_type}: ${t.count} (${t.percentage}%), avg $${t.avg_cost.toFixed(2)}` : "";
          },
        },
      },
    },
  }), [defaultChartOptions, sessionTypes]);

  return (
    <div className="dashboard">
      {/* Global filter bar */}
      <div className="dashboard-filters">
        <div className="dashboard-filter-presets">
          {DATE_PRESETS.map((p) => (
            <button
              key={p.label}
              className={`dashboard-preset-btn${datePreset === p.label ? " active" : ""}`}
              onClick={() => handleDatePreset(p)}
            >
              {p.label}
            </button>
          ))}
        </div>
        {filterOptions && (
          <>
            <select
              className="dashboard-filter-select"
              value={filters.project}
              onChange={(e) => setFilters((f) => ({ ...f, project: e.target.value }))}
            >
              <option value="">All Projects</option>
              {(filterOptions.projects || []).map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            <select
              className="dashboard-filter-select"
              value={filters.model}
              onChange={(e) => setFilters((f) => ({ ...f, model: e.target.value }))}
            >
              <option value="">All Models</option>
              {(filterOptions.models || []).map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </>
        )}
        {(filters.project || filters.model || filters.date_from) && (
          <button
            className="dashboard-clear-btn"
            onClick={() => {
              setFilters((f) => ({ ...f, project: "", model: "", date_from: "", date_to: "" }));
              setDatePreset("All");
            }}
          >
            Clear Filters
          </button>
        )}
      </div>

      {/* Row 1: Summary cards */}
      {summary && (
        <div className="dashboard-summary-row">
          <SummaryCard
            label="Sessions"
            value={formatNumber(summary.total_sessions)}
            delta={summary.deltas.sessions}
            deltaLabel="/week"
          />
          <SummaryCard
            label="Tokens"
            value={formatNumber(summary.total_tokens)}
            delta={summary.deltas.tokens}
            deltaLabel="/week"
            formatDelta={formatNumber}
          />
          <SummaryCard
            label="Est. Cost"
            value={"$" + summary.total_cost.toFixed(2)}
            delta={summary.deltas.cost}
            deltaLabel="/week"
            prefix="$"
          />
          <SummaryCard
            label="Avg Cost/Session"
            value={"$" + summary.avg_cost_per_session.toFixed(2)}
            delta={summary.deltas.avg_cost}
            deltaLabel=""
            prefix="$"
          />
          <SummaryCard
            label="Projects"
            value={summary.project_count}
            delta={summary.deltas.projects}
            deltaLabel="/week"
          />
        </div>
      )}

      {/* Row 2: Cost over time */}
      <div className="dashboard-section">
        <div className="dashboard-section-header">
          <h3>Cost Over Time</h3>
          <div className="dashboard-section-controls">
            <select className="dashboard-mini-select" value={costGroupBy} onChange={(e) => setCostGroupBy(e.target.value)}>
              <option value="day">Daily</option>
              <option value="week">Weekly</option>
              <option value="month">Monthly</option>
            </select>
            <select className="dashboard-mini-select" value={costStackBy} onChange={(e) => setCostStackBy(e.target.value)}>
              <option value="project">By Project</option>
              <option value="model">By Model</option>
              <option value="provider">By Provider</option>
            </select>
          </div>
        </div>
        <div className="dashboard-chart-container" style={{ height: 280 }}>
          {costChartData ? (
            <Line data={costChartData} options={costChartOptions} />
          ) : (
            <div className="dashboard-empty">No cost data available</div>
          )}
        </div>
      </div>

      {/* Row 3: Project breakdown + Model comparison */}
      <div className="dashboard-row-2col">
        <div className="dashboard-section">
          <h3>Project Breakdown</h3>
          <div className="dashboard-chart-container" style={{ height: Math.max(200, Math.min(15, projectBreakdown.length) * 28 + 40) }}>
            {projectChartData ? (
              <Bar data={projectChartData} options={projectChartOptions} />
            ) : (
              <div className="dashboard-empty">No project data</div>
            )}
          </div>
        </div>
        <div className="dashboard-section">
          <h3>Model Comparison</h3>
          <div className="dashboard-chart-container" style={{ height: 280 }}>
            {modelChartData ? (
              <Bar data={modelChartData} options={modelChartOptions} />
            ) : (
              <div className="dashboard-empty">No model data</div>
            )}
          </div>
        </div>
      </div>

      {/* Row 4: Tool usage + Session types */}
      <div className="dashboard-row-2col">
        <div className="dashboard-section">
          <h3>Tool Usage</h3>
          <div className="dashboard-chart-container" style={{ height: Math.max(200, toolUsage.length * 24 + 40) }}>
            {toolChartData ? (
              <Bar data={toolChartData} options={toolChartOptions} />
            ) : (
              <div className="dashboard-empty">No tool data</div>
            )}
          </div>
        </div>
        <div className="dashboard-section">
          <h3>Session Types</h3>
          <div className="dashboard-chart-container" style={{ height: 220 }}>
            {typeChartData ? (
              <Doughnut data={typeChartData} options={typeChartOptions} />
            ) : (
              <div className="dashboard-empty">No session type data</div>
            )}
          </div>
          {sessionTypes.length > 0 && (
            <div className="dashboard-type-table">
              <div className="dashboard-type-row dashboard-type-header">
                <span>Type</span><span>Count</span><span>%</span><span>Avg Cost</span>
              </div>
              {sessionTypes.map((t) => (
                <div key={t.session_type} className="dashboard-type-row">
                  <span>{t.session_type}</span>
                  <span>{t.count}</span>
                  <span>{t.percentage}%</span>
                  <span>${t.avg_cost.toFixed(2)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Activity Heatmap */}
      <div className="dashboard-section">
        <h3>Activity</h3>
        <Heatmap data={heatmapData} />
      </div>

      {/* Anomaly table */}
      {anomalies.length > 0 && (
        <div className="dashboard-section">
          <h3>Flagged Sessions</h3>
          <div className="dashboard-anomaly-table">
            <div className="dashboard-anomaly-header">
              <span className="anomaly-col-project" onClick={() => handleAnomalySort("project")}>Project</span>
              <span className="anomaly-col-date" onClick={() => handleAnomalySort("date")}>Date</span>
              <span className="anomaly-col-turns" onClick={() => handleAnomalySort("turns")}>Turns</span>
              <span className="anomaly-col-tokens" onClick={() => handleAnomalySort("tokens")}>Tokens</span>
              <span className="anomaly-col-cost" onClick={() => handleAnomalySort("cost")}>Cost</span>
              <span className="anomaly-col-flag">Flag</span>
            </div>
            {sortedAnomalies.map((a) => (
              <div
                key={a.session_id}
                className="dashboard-anomaly-row"
                onClick={() => handleAnomalyClick(a)}
              >
                <span className="anomaly-col-project">{a.project}</span>
                <span className="anomaly-col-date">{a.date ? new Date(a.date).toLocaleDateString() : ""}</span>
                <span className="anomaly-col-turns">{a.turns ?? ""}</span>
                <span className="anomaly-col-tokens">{formatNumber(a.tokens)}</span>
                <span className="anomaly-col-cost">${a.cost.toFixed(2)}</span>
                <span className="anomaly-col-flag anomaly-flag">{a.flag}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value, delta, deltaLabel, prefix = "", formatDelta }) {
  const isPositive = delta > 0;
  const isNegative = delta < 0;
  const deltaStr = formatDelta
    ? (isPositive ? "+" : "") + formatDelta(delta)
    : (isPositive ? "+" : "") + (prefix && delta !== 0 ? prefix : "") + (typeof delta === "number" ? (Math.abs(delta) < 1 && delta !== 0 ? delta.toFixed(2) : delta) : delta);

  return (
    <div className="dashboard-summary-card">
      <div className="summary-card-label">{label}</div>
      <div className="summary-card-value">{value}</div>
      {delta != null && (
        <div className={`summary-card-delta${isPositive ? " delta-up" : ""}${isNegative ? " delta-down" : ""}`}>
          {deltaStr}{deltaLabel}
        </div>
      )}
    </div>
  );
}
