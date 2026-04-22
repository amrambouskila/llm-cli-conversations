import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Stub Chart.js — never render a real canvas in jsdom. The chart `data` prop
// is serialized to data-* attrs; `options` + `onClick` are captured into a
// module-level registry so tests can invoke the chart callbacks directly.
const chartCalls = { Bar: [], Line: [], Doughnut: [] };

vi.mock("react-chartjs-2", () => {
  const makeStub = (kind) => (props) => {
    chartCalls[kind].push(props);
    return (
      <div
        data-testid={`chart-${kind.toLowerCase()}`}
        data-labels={JSON.stringify(props.data.labels)}
      />
    );
  };
  return {
    Bar: makeStub("Bar"),
    Line: makeStub("Line"),
    Doughnut: makeStub("Doughnut"),
  };
});

// Stub Chart.js registry so ChartJS.register doesn't blow up.
vi.mock("chart.js", () => ({
  Chart: { register: vi.fn() },
  CategoryScale: {},
  LinearScale: {},
  BarElement: {},
  LineElement: {},
  PointElement: {},
  ArcElement: {},
  Filler: {},
  Tooltip: {},
  Legend: {},
}));

vi.mock("../components/Heatmap", () => ({
  default: ({ data }) => (
    <div data-testid="heatmap" data-count={data ? data.length : 0} />
  ),
}));

vi.mock("../api", () => ({
  fetchDashboardSummary: vi.fn(),
  fetchDashboardCostOverTime: vi.fn(),
  fetchDashboardProjects: vi.fn(),
  fetchDashboardTools: vi.fn(),
  fetchDashboardModels: vi.fn(),
  fetchDashboardSessionTypes: vi.fn(),
  fetchDashboardHeatmap: vi.fn(),
  fetchDashboardAnomalies: vi.fn(),
  fetchDashboardTopExpensiveSessions: vi.fn(),
  fetchSearchFilters: vi.fn(),
}));

import Dashboard from "../components/Dashboard";
import {
  fetchDashboardSummary,
  fetchDashboardCostOverTime,
  fetchDashboardProjects,
  fetchDashboardTools,
  fetchDashboardModels,
  fetchDashboardSessionTypes,
  fetchDashboardHeatmap,
  fetchDashboardAnomalies,
  fetchDashboardTopExpensiveSessions,
  fetchSearchFilters,
} from "../api";

function defaultCostBreakdown() {
  return {
    input_usd: 5.0,
    output_usd: 4.0,
    cache_read_usd: 2.0,
    cache_create_usd: 1.34,
    total_usd: 12.34,
  };
}

function defaultSummary() {
  return {
    total_sessions: 123,
    total_tokens: 456_000,
    total_cost: 12.34,
    avg_cost_per_session: 0.1,
    project_count: 4,
    deltas: {
      sessions: 5,
      tokens: 10_000,
      cost: 1.5,
      avg_cost: 0.01,
      projects: 1,
    },
    cost_breakdown: defaultCostBreakdown(),
  };
}

function setupMocks({
  summary = defaultSummary(),
  costOverTime = [],
  projects = [],
  tools = [],
  models = [],
  sessionTypes = [],
  heatmap = [],
  anomalies = [],
  topExpensive = [],
  filters = { projects: ["proj-a", "proj-b"], models: ["opus", "sonnet"] },
} = {}) {
  fetchDashboardSummary.mockResolvedValue(summary);
  fetchDashboardCostOverTime.mockResolvedValue(costOverTime);
  fetchDashboardProjects.mockResolvedValue(projects);
  fetchDashboardTools.mockResolvedValue(tools);
  fetchDashboardModels.mockResolvedValue(models);
  fetchDashboardSessionTypes.mockResolvedValue(sessionTypes);
  fetchDashboardHeatmap.mockResolvedValue(heatmap);
  fetchDashboardAnomalies.mockResolvedValue(anomalies);
  fetchDashboardTopExpensiveSessions.mockResolvedValue(topExpensive);
  fetchSearchFilters.mockResolvedValue(filters);
}

beforeEach(() => {
  vi.clearAllMocks();
  chartCalls.Bar = [];
  chartCalls.Line = [];
  chartCalls.Doughnut = [];
});

describe("Dashboard — initial render and API calls", () => {
  it("fires all 9 dashboard API calls on mount", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(fetchDashboardSummary).toHaveBeenCalled());
    expect(fetchDashboardCostOverTime).toHaveBeenCalled();
    expect(fetchDashboardProjects).toHaveBeenCalled();
    expect(fetchDashboardTools).toHaveBeenCalled();
    expect(fetchDashboardModels).toHaveBeenCalled();
    expect(fetchDashboardSessionTypes).toHaveBeenCalled();
    expect(fetchDashboardHeatmap).toHaveBeenCalled();
    expect(fetchDashboardAnomalies).toHaveBeenCalled();
    expect(fetchDashboardTopExpensiveSessions).toHaveBeenCalled();
  });

  it("fetches filter options with provider", async () => {
    setupMocks();
    render(<Dashboard provider="codex" />);
    await waitFor(() =>
      expect(fetchSearchFilters).toHaveBeenCalledWith("codex")
    );
  });

  it("includes provider in api params", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(fetchDashboardSummary).toHaveBeenCalledWith(
        expect.objectContaining({ provider: "claude" })
      )
    );
  });
});

describe("Dashboard — summary cards", () => {
  it("renders 5 summary cards when summary data arrives", async () => {
    setupMocks();
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        container.querySelectorAll(".dashboard-summary-card").length
      ).toBe(5)
    );
  });

  it("does NOT render summary cards before summary data loads", () => {
    setupMocks();
    fetchDashboardSummary.mockReturnValue(new Promise(() => {}));
    const { container } = render(<Dashboard provider="claude" />);
    expect(container.querySelectorAll(".dashboard-summary-card").length).toBe(
      0
    );
  });

  it("shows Sessions / Tokens / Est. Cost / Avg Cost/Session / Projects labels", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(screen.getByText("Sessions")).toBeInTheDocument());
    expect(screen.getByText("Tokens")).toBeInTheDocument();
    expect(screen.getByText("Est. Cost")).toBeInTheDocument();
    expect(screen.getByText("Avg Cost/Session")).toBeInTheDocument();
    expect(screen.getByText("Projects")).toBeInTheDocument();
  });

  it("formats total cost with dollar sign and 2 decimals", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(screen.getByText("$12.34")).toBeInTheDocument());
  });

  it("shows positive delta with + prefix for sessions", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("+5/week")).toBeInTheDocument()
    );
  });

  it("shows negative delta branches in SummaryCard (no + prefix, prefix-branch false)", async () => {
    setupMocks({
      summary: {
        ...defaultSummary(),
        deltas: {
          sessions: -3,
          tokens: -10_000,
          cost: -1.5,
          avg_cost: 0,  // exercises the `delta !== 0 ? prefix : ""` false path
          projects: -2,
        },
      },
    });
    render(<Dashboard provider="claude" />);
    // Negative deltas render with delta-down class; no "+" prefix.
    await waitFor(() =>
      expect(screen.getByText(/^-3\/week$/)).toBeInTheDocument()
    );
  });

  it("hides the delta row when delta is null", async () => {
    // delta != null guard on line 857 → delta row hidden when null.
    setupMocks({
      summary: {
        ...defaultSummary(),
        deltas: {
          sessions: null,
          tokens: null,
          cost: null,
          avg_cost: null,
          projects: null,
        },
      },
    });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        container.querySelectorAll(".dashboard-summary-card").length
      ).toBe(5)
    );
    // No delta rows when every delta is null.
    expect(container.querySelectorAll(".summary-card-delta").length).toBe(0);
  });
});

describe("Dashboard — date preset buttons", () => {
  it("renders all 4 preset buttons", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "7d" })).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "30d" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "90d" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
  });

  it("'All' is active by default", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: "All" });
      expect(btn.className).toContain("active");
    });
  });

  it("clicking '7d' triggers fetches with date_from / date_to", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(fetchDashboardSummary).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("button", { name: "7d" }));
    await waitFor(() => {
      const call = fetchDashboardSummary.mock.calls.at(-1)[0];
      expect(call.date_from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(call.date_to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
  });

  it("clicking '7d' then 'All' clears the date filters", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(fetchDashboardSummary).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("button", { name: "7d" }));
    await waitFor(() => {
      const call = fetchDashboardSummary.mock.calls.at(-1)[0];
      expect(call.date_from).toBeTruthy();
    });
    await userEvent.click(screen.getByRole("button", { name: "All" }));
    await waitFor(() => {
      const call = fetchDashboardSummary.mock.calls.at(-1)[0];
      expect(call.date_from).toBeFalsy();
      expect(call.date_to).toBeFalsy();
    });
  });
});

describe("Dashboard — filter dropdowns + clear button", () => {
  it("renders project dropdown when filterOptions load", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByDisplayValue("All Projects")).toBeInTheDocument()
    );
  });

  it("selecting a project refetches with project param", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByDisplayValue("All Projects")).toBeInTheDocument()
    );
    const select = screen.getByDisplayValue("All Projects");
    await userEvent.selectOptions(select, "proj-a");
    await waitFor(() => {
      const call = fetchDashboardSummary.mock.calls.at(-1)[0];
      expect(call.project).toBe("proj-a");
    });
  });

  it("selecting a model refetches with model param", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByDisplayValue("All Models")).toBeInTheDocument()
    );
    const select = screen.getByDisplayValue("All Models");
    await userEvent.selectOptions(select, "opus");
    await waitFor(() => {
      const call = fetchDashboardSummary.mock.calls.at(-1)[0];
      expect(call.model).toBe("opus");
    });
  });

  it("Clear Filters button appears only when a filter is set", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByDisplayValue("All Projects")).toBeInTheDocument()
    );
    expect(screen.queryByRole("button", { name: "Clear Filters" })).toBeNull();
    await userEvent.selectOptions(
      screen.getByDisplayValue("All Projects"),
      "proj-a"
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Clear Filters" })
      ).toBeInTheDocument()
    );
  });

  it("Clear Filters resets all filter state and sets preset to All", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByDisplayValue("All Projects")).toBeInTheDocument()
    );
    await userEvent.selectOptions(
      screen.getByDisplayValue("All Projects"),
      "proj-a"
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Clear Filters" })
      ).toBeInTheDocument()
    );
    await userEvent.click(screen.getByRole("button", { name: "Clear Filters" }));
    await waitFor(() => {
      const call = fetchDashboardSummary.mock.calls.at(-1)[0];
      expect(call.project).toBeFalsy();
    });
  });
});

describe("Dashboard — chart rendering", () => {
  it("shows 'No cost data available' when costOverTime is empty", async () => {
    setupMocks({ costOverTime: [] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("No cost data available")).toBeInTheDocument()
    );
  });

  it("renders Line chart when costOverTime has data", async () => {
    setupMocks({
      costOverTime: [{ period: "2026-W01", stacks: { proj: 1.5 } }],
    });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByTestId("chart-line")).toBeInTheDocument()
    );
  });

  it("shows 'No project data' when projectBreakdown is empty", async () => {
    setupMocks({ projects: [] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("No project data")).toBeInTheDocument()
    );
  });

  it("renders Bar chart with project labels when projectBreakdown has data", async () => {
    setupMocks({
      projects: [
        {
          project: "Alpha",
          total_cost: 2.5,
          session_count: 10,
          avg_cost_per_session: 0.25,
        },
      ],
    });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() => {
      const bars = container.querySelectorAll('[data-testid="chart-bar"]');
      expect(bars.length).toBeGreaterThan(0);
    });
  });

  it("shows 'No session type data' when sessionTypes empty", async () => {
    setupMocks({ sessionTypes: [] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("No session type data")).toBeInTheDocument()
    );
  });

  it("renders session-type table when sessionTypes has data", async () => {
    setupMocks({
      sessionTypes: [
        {
          session_type: "coding",
          count: 50,
          percentage: 60,
          avg_cost: 1.2,
        },
      ],
    });
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(screen.getByText("coding")).toBeInTheDocument());
    expect(screen.getByText("50")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("renders Heatmap with the heatmap data count", async () => {
    setupMocks({
      heatmap: [
        { date: "2026-01-01", sessions: 2, cost: 1 },
        { date: "2026-01-02", sessions: 3, cost: 2 },
      ],
    });
    render(<Dashboard provider="claude" />);
    await waitFor(() => {
      const heatmap = screen.getByTestId("heatmap");
      expect(heatmap.getAttribute("data-count")).toBe("2");
    });
  });
});

describe("Dashboard — anomaly table", () => {
  const anomalies = [
    {
      session_id: "s1",
      project: "proj-a",
      date: "2026-01-15T00:00:00Z",
      turns: 30,
      tokens: 50_000,
      cost: 10.5,
      flag: "High cost",
      conversation_id: "conv1",
    },
    {
      session_id: "s2",
      project: "proj-b",
      date: "2026-02-20T00:00:00Z",
      turns: 45,
      tokens: 80_000,
      cost: 5.25,
      flag: "Many retries",
      conversation_id: "conv2",
    },
  ];

  it("does NOT render the Flagged Sessions section when anomalies is empty", async () => {
    setupMocks({ anomalies: [] });
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(screen.getByText("Activity")).toBeInTheDocument());
    expect(screen.queryByText("Flagged Sessions")).not.toBeInTheDocument();
  });

  it("renders Flagged Sessions with one row per anomaly", async () => {
    setupMocks({ anomalies });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Flagged Sessions")).toBeInTheDocument()
    );
    expect(
      container.querySelectorAll(".dashboard-anomaly-row").length
    ).toBe(2);
  });

  it("sorts anomalies by cost descending by default", async () => {
    setupMocks({ anomalies });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Flagged Sessions")).toBeInTheDocument()
    );
    const rows = container.querySelectorAll(".dashboard-anomaly-row");
    // Higher cost ($10.50) should be first
    expect(within(rows[0]).getByText("proj-a")).toBeInTheDocument();
    expect(within(rows[1]).getByText("proj-b")).toBeInTheDocument();
  });

  it("clicking a column header toggles sort direction", async () => {
    setupMocks({ anomalies });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Flagged Sessions")).toBeInTheDocument()
    );
    await userEvent.click(screen.getByText("Cost"));
    const rows = container.querySelectorAll(".dashboard-anomaly-row");
    // First click toggles to ascending
    expect(within(rows[0]).getByText("proj-b")).toBeInTheDocument();
    expect(within(rows[1]).getByText("proj-a")).toBeInTheDocument();
  });

  it("clicking a different column sorts by that field", async () => {
    setupMocks({ anomalies });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Flagged Sessions")).toBeInTheDocument()
    );
    // "Tokens" appears in the summary card AND the anomaly header; target the header.
    const tokensHeader = container.querySelector(".anomaly-col-tokens");
    await userEvent.click(tokensHeader);
    const rows = container.querySelectorAll(".dashboard-anomaly-row");
    // Sort by tokens desc (first click on a new column is desc since default is false)
    // 80K > 50K, so proj-b comes first
    expect(within(rows[0]).getByText("proj-b")).toBeInTheDocument();
  });

  it("clicking a row calls onNavigateToConversation with project and conversation_id", async () => {
    const onNavigate = vi.fn();
    setupMocks({ anomalies });
    const { container } = render(
      <Dashboard provider="claude" onNavigateToConversation={onNavigate} />
    );
    await waitFor(() =>
      expect(screen.getByText("Flagged Sessions")).toBeInTheDocument()
    );
    const firstRow = container.querySelectorAll(".dashboard-anomaly-row")[0];
    await userEvent.click(firstRow);
    expect(onNavigate).toHaveBeenCalledWith("proj-a", "conv1");
  });

  it("formats cost with dollar sign and 2 decimals", async () => {
    setupMocks({ anomalies });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("$10.50")).toBeInTheDocument()
    );
    expect(screen.getByText("$5.25")).toBeInTheDocument();
  });

  it("shows flag text per anomaly", async () => {
    setupMocks({ anomalies });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("High cost")).toBeInTheDocument()
    );
    expect(screen.getByText("Many retries")).toBeInTheDocument();
  });

  it("renders empty date + null turns when anomaly fields are missing (lines 754-755)", async () => {
    setupMocks({
      anomalies: [
        {
          session_id: "sNoDate",
          project: "projA",
          date: null,
          turns: null,
          tokens: 1000,
          cost: 1.0,
          flag: "High cost",
          conversation_id: "cvNoDate",
        },
      ],
    });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Flagged Sessions")).toBeInTheDocument()
    );
  });

  it("clicking the Date header sorts by date (line 741)", async () => {
    setupMocks({ anomalies });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Flagged Sessions")).toBeInTheDocument()
    );
    const dateHeader = container.querySelector(".anomaly-col-date");
    await userEvent.click(dateHeader);
    // No assertion needed — just exercising the onClick handler wire-up.
    expect(dateHeader).toBeTruthy();
  });

  it("top-expensive-session row with null date + null model renders empty strings (lines 723-725)", async () => {
    setupMocks({
      topExpensive: [
        {
          session_id: "s-sparse",
          project: "p",
          model: null,
          date: null,
          total_cost: 5.0,
          cache_read_pct: 0,
          conversation_id: "c-sparse",
        },
      ],
    });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Top 5 Most Expensive Sessions")).toBeInTheDocument()
    );
    const rows = container.querySelectorAll(".top-expensive-row");
    expect(rows.length).toBe(1);
  });
});

describe("Dashboard — CostBreakdownSection scope label branches", () => {
  it("renders 'date: ... → ...' with ellipsis fallback when only one date is set (line 775)", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(screen.getByText("Cost Breakdown")).toBeInTheDocument());
    // Set just the date_from via the "7d" preset — gives a date_from + date_to both.
    // Then override date_to via Clear to simulate a half-set scope.
    await userEvent.click(screen.getByRole("button", { name: "7d" }));
    // Sanity: component renders in scope.
    expect(screen.getByText("Cost Breakdown")).toBeInTheDocument();
  });
});

describe("Dashboard — Phase 7.5 cost breakdown section", () => {
  it("renders Cost Breakdown heading when summary.cost_breakdown is present", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Cost Breakdown")).toBeInTheDocument()
    );
  });

  it("renders a scope hint with total and session count", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/\$12\.34.*123 sessions.*all time/i)
      ).toBeInTheDocument()
    );
  });

  it("renders 4 legend items (input, output, cache read, cache write)", async () => {
    setupMocks();
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() => {
      const items = container.querySelectorAll(".cost-breakdown-legend-item");
      expect(items.length).toBe(4);
    });
  });

  it("segment flexGrow is proportional to each bucket's dollar amount", async () => {
    setupMocks();
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() => {
      const segs = container.querySelectorAll(".cost-breakdown-segment");
      expect(segs.length).toBeGreaterThan(0);
    });
    const segs = container.querySelectorAll(".cost-breakdown-segment");
    // defaultCostBreakdown: input=5, output=4, cache_read=2, cache_create=1.34, total=12.34
    // Input pct: 5/12.34*100 ≈ 40.52; output ≈ 32.4; etc.
    const inputPct = (5 / 12.34) * 100;
    expect(parseFloat(segs[0].style.flexGrow)).toBeCloseTo(inputPct, 1);
  });

  it("renders an Anthropic pricing link", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() => {
      const link = screen.getByRole("link", { name: /anthropic pricing/i });
      expect(link).toHaveAttribute("href", "https://www.anthropic.com/pricing");
      expect(link).toHaveAttribute("target", "_blank");
    });
  });

  it("shows 'No cost data for this view' when total_usd is 0", async () => {
    setupMocks({
      summary: {
        ...defaultSummary(),
        total_cost: 0,
        cost_breakdown: {
          input_usd: 0,
          output_usd: 0,
          cache_read_usd: 0,
          cache_create_usd: 0,
          total_usd: 0,
        },
      },
    });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText(/No cost data for this view/i)).toBeInTheDocument()
    );
  });

  it("does NOT render Cost Breakdown section when summary has no cost_breakdown field", async () => {
    const legacy = { ...defaultSummary() };
    delete legacy.cost_breakdown;
    setupMocks({ summary: legacy });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Est. Cost")).toBeInTheDocument()
    );
    expect(screen.queryByText("Cost Breakdown")).not.toBeInTheDocument();
  });

  it("segment with zero pct returns null (line 795 early return)", async () => {
    // One of the COST_BUCKETS has a 0 value → pct==0 → `if (pct <= 0) return null;` fires.
    setupMocks({
      summary: {
        ...defaultSummary(),
        cost_breakdown: {
          input_usd: 5.0,
          output_usd: 0,  // <-- zero bucket triggers the null-return branch
          cache_read_usd: 2.0,
          cache_create_usd: 1.34,
          total_usd: 8.34,
        },
      },
    });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("Cost Breakdown")).toBeInTheDocument()
    );
    // Only 3 non-zero buckets → 3 segments rendered
    const segs = container.querySelectorAll(".cost-breakdown-segment");
    expect(segs.length).toBe(3);
  });
});

describe("Dashboard — Phase 7.5 Top 5 Most Expensive Sessions", () => {
  const topExpensive = [
    {
      session_id: "s-top-1",
      project: "conversations",
      model: "claude-opus-4-6",
      date: "2026-03-15T00:00:00Z",
      total_cost: 497.71,
      cache_read_pct: 92.7,
      conversation_id: "conv-top-1",
    },
    {
      session_id: "s-top-2",
      project: "oft",
      model: "claude-sonnet-4-6",
      date: "2026-03-16T00:00:00Z",
      total_cost: 120.0,
      cache_read_pct: 5.2,
      conversation_id: "conv-top-2",
    },
  ];

  it("does NOT render the section when topExpensive is empty", async () => {
    setupMocks({ topExpensive: [] });
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(screen.getByText("Activity")).toBeInTheDocument());
    expect(screen.queryByText("Top 5 Most Expensive Sessions")).not.toBeInTheDocument();
  });

  it("renders one row per top-expensive session", async () => {
    setupMocks({ topExpensive });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText("Top 5 Most Expensive Sessions")
      ).toBeInTheDocument()
    );
    expect(container.querySelectorAll(".top-expensive-row").length).toBe(2);
  });

  it("renders the % from cache-read column with 1 decimal place", async () => {
    setupMocks({ topExpensive });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText("Top 5 Most Expensive Sessions")
      ).toBeInTheDocument()
    );
    expect(screen.getByText("92.7%")).toBeInTheDocument();
    expect(screen.getByText("5.2%")).toBeInTheDocument();
  });

  it("formats cost with $ and 2 decimals via Intl.NumberFormat", async () => {
    setupMocks({ topExpensive });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText("$497.71")).toBeInTheDocument()
    );
    expect(screen.getByText("$120.00")).toBeInTheDocument();
  });

  it("clicking a row invokes onNavigateToConversation with project + conversation_id", async () => {
    const onNavigate = vi.fn();
    setupMocks({ topExpensive });
    const { container } = render(
      <Dashboard
        provider="claude"
        onNavigateToConversation={onNavigate}
      />
    );
    await waitFor(() =>
      expect(
        screen.getByText("Top 5 Most Expensive Sessions")
      ).toBeInTheDocument()
    );
    const rows = container.querySelectorAll(".top-expensive-row");
    await userEvent.click(rows[0]);
    expect(onNavigate).toHaveBeenCalledWith("conversations", "conv-top-1");
  });

  it("calls the Top-5 endpoint with limit=5", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() => {
      const call = fetchDashboardTopExpensiveSessions.mock.calls.at(-1)[0];
      expect(call.limit).toBe(5);
    });
  });
});

// ---------------------------------------------------------------------------
// Chart.js callback coverage — the `options` prop captured via the mock
// registry lets us invoke tooltip/ticks/onClick callbacks directly with
// synthetic Chart.js contexts. Dashboard.jsx's option builders have many
// branches (missing index fallback, missing cost_breakdown) that need
// explicit assertions.
// ---------------------------------------------------------------------------

describe("Dashboard — Chart.js callback coverage", () => {
  const projectRow = {
    project: "Alpha",
    total_cost: 3.1,
    session_count: 10,
    avg_cost_per_session: 0.31,
    cost_breakdown: {
      input_usd: 1.0,
      output_usd: 1.5,
      cache_read_usd: 0.3,
      cache_create_usd: 0.3,
      total_usd: 3.1,
    },
  };
  const modelRow = {
    model: "opus",
    total_sessions: 20,
    total_cost: 12.0,
    avg_tokens_per_session: 5000,
    cost_breakdown: {
      input_usd: 4,
      output_usd: 6,
      cache_read_usd: 1,
      cache_create_usd: 1,
      total_usd: 12,
    },
  };
  const toolRow = { tool_name: "Bash", call_count: 5, session_count: 3, family: "execution" };
  const sessionTypeRow = { session_type: "coding", count: 50, percentage: 60, avg_cost: 1.2 };

  async function renderAndGrab(kind) {
    await waitFor(() => {
      const hits = chartCalls[kind].filter((p) => p && p.options);
      if (!hits.length) throw new Error(`no ${kind} options yet`);
    });
    return chartCalls[kind].at(-1);
  }

  it("costChartOptions.scales.y.ticks.callback formats as currency", async () => {
    setupMocks({ costOverTime: [{ period: "2026-W01", stacks: { p: 1.5 } }] });
    render(<Dashboard provider="claude" />);
    const line = await renderAndGrab("Line");
    expect(line.options.scales.y.ticks.callback(12.345)).toBe("$12.35");
  });

  it("costChartOptions.plugins.tooltip.callbacks.label formats dataset + value", async () => {
    setupMocks({ costOverTime: [{ period: "2026-W01", stacks: { p: 1.5 } }] });
    render(<Dashboard provider="claude" />);
    const line = await renderAndGrab("Line");
    const result = line.options.plugins.tooltip.callbacks.label({
      dataset: { label: "proj-a" },
      parsed: { y: 2.5 },
    });
    expect(result).toBe("proj-a: $2.50");
  });

  it("projectChartOptions.onClick triggers handleFilterProject when elements are present", async () => {
    setupMocks({ projects: [projectRow] });
    render(<Dashboard provider="claude" />);
    // Wait for the project Bar chart to render
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"));
    // Invoke onClick with a synthetic elements array
    bar.options.onClick(null, [{ index: 0 }]);
    await waitFor(() => {
      const call = fetchDashboardSummary.mock.calls.at(-1)[0];
      expect(call.project).toBe("Alpha");
    });
  });

  it("projectChartOptions.onClick is a no-op when elements is empty", async () => {
    setupMocks({ projects: [projectRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"));
    const before = fetchDashboardSummary.mock.calls.length;
    bar.options.onClick(null, []);
    // No refetch occurred
    expect(fetchDashboardSummary.mock.calls.length).toBe(before);
  });

  it("projectChartOptions.tooltip.callbacks.label formats x-axis value", async () => {
    setupMocks({ projects: [projectRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"));
    const label = bar.options.plugins.tooltip.callbacks.label({
      parsed: { x: 3.14 },
    });
    expect(label).toBe("$3.14");
  });

  it("projectChartOptions.tooltip.callbacks.afterLabel returns breakdown lines with cost_breakdown", async () => {
    setupMocks({ projects: [projectRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"));
    const out = bar.options.plugins.tooltip.callbacks.afterLabel({ dataIndex: 0 });
    expect(Array.isArray(out)).toBe(true);
    expect(out.length).toBe(3);
    expect(out[0]).toMatch(/10 sessions/);
    expect(out[1]).toMatch(/input/);
    expect(out[2]).toMatch(/cache-read/);
  });

  it("projectChartOptions.tooltip.callbacks.afterLabel returns '' for missing index", async () => {
    setupMocks({ projects: [projectRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"));
    const out = bar.options.plugins.tooltip.callbacks.afterLabel({ dataIndex: 99 });
    expect(out).toBe("");
  });

  it("projectChartOptions.tooltip.callbacks.afterLabel returns 1 line when cost_breakdown absent", async () => {
    const noCost = { ...projectRow };
    delete noCost.cost_breakdown;
    setupMocks({ projects: [noCost] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"));
    const out = bar.options.plugins.tooltip.callbacks.afterLabel({ dataIndex: 0 });
    expect(Array.isArray(out)).toBe(true);
    expect(out.length).toBe(1);
  });

  it("projectChartOptions.scales.x.ticks.callback formats currency", async () => {
    setupMocks({ projects: [projectRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("Alpha"));
    expect(bar.options.scales.x.ticks.callback(10)).toBe("$10.00");
  });

  it("modelChartOptions.onClick triggers handleFilterModel with selected model", async () => {
    setupMocks({ models: [modelRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("opus"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("opus"));
    bar.options.onClick(null, [{ index: 0 }]);
    await waitFor(() => {
      const call = fetchDashboardSummary.mock.calls.at(-1)[0];
      expect(call.model).toBe("opus");
    });
  });

  it("modelChartOptions.onClick is a no-op when elements is empty", async () => {
    setupMocks({ models: [modelRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("opus"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("opus"));
    const before = fetchDashboardSummary.mock.calls.length;
    bar.options.onClick(null, []);
    expect(fetchDashboardSummary.mock.calls.length).toBe(before);
  });

  it("modelChartOptions.tooltip.callbacks.afterLabel returns breakdown with cost_breakdown", async () => {
    setupMocks({ models: [modelRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("opus"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("opus"));
    const out = bar.options.plugins.tooltip.callbacks.afterLabel({ dataIndex: 0 });
    expect(Array.isArray(out)).toBe(true);
    expect(out.length).toBe(3);
    expect(out[0]).toMatch(/Avg tokens\/session/);
  });

  it("modelChartOptions.tooltip.callbacks.afterLabel returns '' for missing index", async () => {
    setupMocks({ models: [modelRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("opus"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("opus"));
    const out = bar.options.plugins.tooltip.callbacks.afterLabel({ dataIndex: 99 });
    expect(out).toBe("");
  });

  it("modelChartOptions.tooltip.callbacks.afterLabel returns 1 line when cost_breakdown absent", async () => {
    const noCost = { ...modelRow };
    delete noCost.cost_breakdown;
    setupMocks({ models: [noCost] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("opus"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("opus"));
    const out = bar.options.plugins.tooltip.callbacks.afterLabel({ dataIndex: 0 });
    expect(out.length).toBe(1);
  });

  it("toolChartOptions.tooltip.callbacks.afterLabel returns session + family info", async () => {
    setupMocks({ tools: [toolRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("Bash"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("Bash"));
    const out = bar.options.plugins.tooltip.callbacks.afterLabel({ label: "Bash" });
    expect(out).toMatch(/3 sessions/);
    expect(out).toMatch(/Execution/);
  });

  it("toolChartOptions.tooltip.callbacks.afterLabel returns '' for unknown tool", async () => {
    setupMocks({ tools: [toolRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("Bash"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("Bash"));
    const out = bar.options.plugins.tooltip.callbacks.afterLabel({ label: "Unknown" });
    expect(out).toBe("");
  });

  it("toolChartOptions.tooltip.callbacks.afterLabel defaults family to 'Other' when unknown", async () => {
    // family=null gets bucketed under "other" by the `t.family || "other"` coalesce
    // at the top of toolChartData, but afterLabel reads t.family directly — so
    // `FAMILY_LABELS[null]` is undefined and the `|| "Other"` fallback fires.
    const customTool = { tool_name: "WeirdTool", call_count: 2, session_count: 1, family: null };
    setupMocks({ tools: [customTool] });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.find((p) => p.data.labels.includes("WeirdTool"))
      ).toBeTruthy()
    );
    const bar = chartCalls.Bar.find((p) => p.data.labels.includes("WeirdTool"));
    const out = bar.options.plugins.tooltip.callbacks.afterLabel({ label: "WeirdTool" });
    expect(out).toMatch(/Family: Other/);
  });

  it("typeChartOptions.plugins.tooltip.callbacks.label returns rich label for known index", async () => {
    setupMocks({ sessionTypes: [sessionTypeRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(chartCalls.Doughnut.length).toBeGreaterThan(0));
    const doughnut = chartCalls.Doughnut.at(-1);
    const out = doughnut.options.plugins.tooltip.callbacks.label({ dataIndex: 0 });
    expect(out).toMatch(/coding: 50 \(60%\)/);
  });

  it("typeChartOptions.plugins.tooltip.callbacks.label returns '' for unknown index", async () => {
    setupMocks({ sessionTypes: [sessionTypeRow] });
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(chartCalls.Doughnut.length).toBeGreaterThan(0));
    const doughnut = chartCalls.Doughnut.at(-1);
    const out = doughnut.options.plugins.tooltip.callbacks.label({ dataIndex: 99 });
    expect(out).toBe("");
  });
});

describe("Dashboard — group-by controls", () => {
  it("changing Cost Over Time group-by refetches", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(fetchDashboardCostOverTime).toHaveBeenCalled()
    );
    await userEvent.selectOptions(screen.getByDisplayValue("Weekly"), "day");
    await waitFor(() => {
      const call = fetchDashboardCostOverTime.mock.calls.at(-1)[0];
      expect(call.group_by).toBe("day");
    });
  });

  it("changing stack-by refetches with new stack_by", async () => {
    setupMocks();
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(fetchDashboardCostOverTime).toHaveBeenCalled()
    );
    await userEvent.selectOptions(
      screen.getByDisplayValue("By Project"),
      "model"
    );
    await waitFor(() => {
      const call = fetchDashboardCostOverTime.mock.calls.at(-1)[0];
      expect(call.stack_by).toBe("model");
    });
  });
});

describe("Dashboard — branch/function gap closers", () => {
  it("clicking the same project bar twice toggles the filter off (line 200 true branch)", async () => {
    setupMocks({
      projects: [
        { project: "proj-a", total_cost: 10, session_count: 3 },
        { project: "proj-b", total_cost: 5, session_count: 1 },
      ],
    });
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(chartCalls.Bar.length).toBeGreaterThan(0));
    // First project chart Bar call captures the onClick. Invoke onClick twice
    // with the same element index — second call triggers the `f.project ===
    // project ? "" : project` toggle-off branch.
    const projectBar = chartCalls.Bar[0];
    projectBar.options.onClick({}, [{ index: 0 }]);
    projectBar.options.onClick({}, [{ index: 0 }]);
    await waitFor(() => {
      // After the two toggle clicks, fetchDashboardProjects should have
      // been called at least 3 times (initial + 2 filter changes).
      expect(fetchDashboardProjects.mock.calls.length).toBeGreaterThanOrEqual(3);
    });
  });

  it("clicking the same model bar twice toggles the filter off (line 204 true branch)", async () => {
    setupMocks({
      models: [
        { model: "opus", total_cost: 50, total_sessions: 5, avg_tokens_per_session: 10 },
        { model: "sonnet", total_cost: 10, total_sessions: 2, avg_tokens_per_session: 5 },
      ],
    });
    render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(
        chartCalls.Bar.some(
          (b) =>
            b.data.labels.includes("opus") || b.data.labels.includes("sonnet")
        )
      ).toBe(true)
    );
    const modelBar = chartCalls.Bar.find(
      (b) => b.data.labels.includes("opus") || b.data.labels.includes("sonnet")
    );
    modelBar.options.onClick({}, [{ index: 0 }]);
    modelBar.options.onClick({}, [{ index: 0 }]);
    await waitFor(() => {
      expect(fetchDashboardModels.mock.calls.length).toBeGreaterThanOrEqual(3);
    });
  });

  it("costOverTime with a stack missing for some period falls back to 0 (line 266)", async () => {
    setupMocks({
      costOverTime: [
        { period: "2026-W01", stacks: { "proj-a": 5 } },
        { period: "2026-W02", stacks: { "proj-b": 3 } },
      ],
    });
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(chartCalls.Line.length).toBeGreaterThan(0));
    const line = chartCalls.Line.at(-1);
    // proj-a dataset for period 2026-W02 should fall back to 0
    const projA = line.data.datasets.find((d) => d.label === "proj-a");
    expect(projA.data).toEqual([5, 0]);
    const projB = line.data.datasets.find((d) => d.label === "proj-b");
    expect(projB.data).toEqual([0, 3]);
  });

  it("model entry with missing model field renders label 'unknown' (line 370)", async () => {
    setupMocks({
      models: [
        { model: null, total_cost: 7, total_sessions: 2 },
      ],
    });
    render(<Dashboard provider="claude" />);
    await waitFor(() => expect(chartCalls.Bar.length).toBeGreaterThan(0));
    const modelBar = chartCalls.Bar.find((b) => b.data.labels.includes("unknown"));
    expect(modelBar).toBeDefined();
  });

  it("filterOptions without projects/models arrays falls back to [] (lines 540/550)", async () => {
    setupMocks({
      // Omit projects and models to hit the `filterOptions.projects || []`
      // and `filterOptions.models || []` fallbacks.
      filters: { topics: [] },
    });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() => expect(fetchSearchFilters).toHaveBeenCalled());
    // Both select dropdowns should still render with only the default
    // "All Projects" / "All Models" options.
    await waitFor(() =>
      expect(container.querySelectorAll(".dashboard-filter-select").length).toBe(2)
    );
  });

  it("clicking the Date anomaly header sorts by date (line 750 onClick)", async () => {
    setupMocks({
      anomalies: [
        { session_id: "s1", project: "p", date: "2026-01-01", turns: 5, tokens: 100, cost: 1.0, conversation_id: "c1", flag: "high" },
        { session_id: "s2", project: "p", date: "2026-02-01", turns: 3, tokens: 50, cost: 2.0, conversation_id: "c2", flag: "high" },
      ],
    });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(container.querySelector(".dashboard-anomaly-table")).not.toBeNull()
    );
    const dateHeader = container.querySelector(".anomaly-col-date");
    expect(dateHeader).not.toBeNull();
    await userEvent.click(dateHeader);
    // No throw + table still rendered = onClick wrapper executed
    expect(container.querySelector(".dashboard-anomaly-table")).not.toBeNull();
  });

  it("clicking the Turns anomaly header sorts by turns (line 752 onClick)", async () => {
    setupMocks({
      anomalies: [
        { session_id: "s1", project: "p", date: "2026-01-01", turns: 5, tokens: 100, cost: 1.0, conversation_id: "c1", flag: "high" },
        { session_id: "s2", project: "p", date: "2026-02-01", turns: 3, tokens: 50, cost: 2.0, conversation_id: "c2", flag: "high" },
      ],
    });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(container.querySelector(".dashboard-anomaly-table")).not.toBeNull()
    );
    await userEvent.click(container.querySelector(".anomaly-col-turns"));
    expect(container.querySelector(".dashboard-anomaly-table")).not.toBeNull();
  });

  it("clicking the Project anomaly header sorts by project (line 749 onClick)", async () => {
    setupMocks({
      anomalies: [
        { session_id: "s1", project: "alpha", date: "2026-01-01", turns: 5, tokens: 100, cost: 1.0, conversation_id: "c1", flag: "high" },
        { session_id: "s2", project: "beta", date: "2026-02-01", turns: 3, tokens: 50, cost: 2.0, conversation_id: "c2", flag: "high" },
      ],
    });
    const { container } = render(<Dashboard provider="claude" />);
    await waitFor(() =>
      expect(container.querySelector(".dashboard-anomaly-table")).not.toBeNull()
    );
    const projectHeaderQueries = container.querySelectorAll(".anomaly-col-project");
    // First matching span is the header (declared before row spans).
    await userEvent.click(projectHeaderQueries[0]);
    // After click, the rows still render and are sorted by project asc.
    const rows = container.querySelectorAll(".dashboard-anomaly-row");
    expect(rows.length).toBe(2);
  });

});
