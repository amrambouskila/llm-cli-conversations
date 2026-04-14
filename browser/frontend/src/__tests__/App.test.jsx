import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../api", () => {
  const fns = [
    "fetchReady",
    "fetchProviders",
    "fetchProjects",
    "fetchProjectsWithHidden",
    "fetchSegments",
    "fetchSegmentsWithHidden",
    "fetchSegmentDetail",
    "fetchConversation",
    "searchSegments",
    "searchSessions",
    "fetchSearchFilters",
    "fetchSearchStatus",
    "fetchRelatedSessions",
    "fetchStats",
    "triggerUpdate",
    "requestSummary",
    "getSummary",
    "deleteSummary",
    "requestConvSummary",
    "getConvSummary",
    "fetchSummaryTitles",
    "hideSegment",
    "restoreSegment",
    "hideConversation",
    "restoreConversation",
    "hideProject",
    "restoreProject",
    "restoreAll",
    "fetchHidden",
    "fetchDashboardSummary",
    "fetchDashboardCostOverTime",
    "fetchDashboardProjects",
    "fetchDashboardTools",
    "fetchDashboardModels",
    "fetchDashboardSessionTypes",
    "fetchDashboardHeatmap",
    "fetchDashboardAnomalies",
    "fetchDashboardGraph",
    "fetchDashboardGraphStatus",
    "triggerDashboardGraphGenerate",
    "importDashboardGraph",
  ];
  const obj = {};
  for (const f of fns) obj[f] = vi.fn();
  return obj;
});

vi.mock("../components/Dashboard", () => ({
  default: () => <div data-testid="dashboard-stub">Dashboard</div>,
}));

vi.mock("../components/KnowledgeGraph", () => ({
  default: () => <div data-testid="kg-stub">Knowledge Graph</div>,
}));

vi.mock("../components/Charts", () => ({
  TokenCostEstimate: () => null,
  MonthlyBreakdown: () => null,
  ToolBreakdownChart: () => null,
  ConversationTimeline: () => null,
  RequestSizeSparkline: () => null,
}));

vi.mock("../components/ContentViewer", () => ({
  default: () => <div data-testid="content-viewer-stub" />,
}));

vi.mock("../components/ProjectList", () => ({
  default: () => <div data-testid="project-list-stub" />,
}));

vi.mock("../components/RequestList", () => ({
  default: () => <div data-testid="request-list-stub" />,
}));

vi.mock("../components/MetadataPanel", () => ({
  default: () => <div data-testid="metadata-panel-stub" />,
}));

vi.mock("../components/FilterChips", () => ({
  default: () => <div data-testid="filter-chips-stub" />,
}));

import App from "../App";
import * as api from "../api";

const defaultProviders = [
  { id: "claude", name: "Claude", projects: 5 },
  { id: "codex", name: "Codex", projects: 3 },
];

const defaultStats = {
  total_projects: 5,
  total_segments: 100,
  total_words: 50_000,
  estimated_tokens: 12_500,
  total_tool_calls: 200,
  monthly: {},
  hidden: { segments: 0, conversations: 0, projects: 0 },
};

const sampleProject = {
  name: "conversations",
  display_name: "conversations",
  total_requests: 20,
  stats: {
    last_timestamp: "2026-04-01T10:00:00Z",
    total_conversations: 5,
    total_words: 10_000,
    estimated_tokens: 2500,
    total_tool_calls: 50,
  },
};

const sampleSearchResult = {
  session_id: "s1",
  project: "conversations",
  date: "2026-04-01T10:00:00Z",
  model: "opus",
  cost: 1.5,
  snippet: "the docker auth issue",
  tool_summary: "Bash(2)",
  tools: { Bash: 2 },
  turn_count: 8,
  topics: ["docker"],
  conversation_id: "c1",
  rank: 1.0,
};

const sampleConversation = {
  conversation_id: "c1",
  project_name: "conversations",
  segment_count: 5,
  raw_markdown: "# Conv",
  metrics: { word_count: 1000, estimated_tokens: 250, tool_call_count: 5 },
};

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchReady.mockResolvedValue({ ready: true });
  api.fetchProviders.mockResolvedValue(defaultProviders);
  api.fetchProjects.mockResolvedValue([sampleProject]);
  api.fetchProjectsWithHidden.mockResolvedValue([sampleProject]);
  api.fetchSegments.mockResolvedValue([]);
  api.fetchSegmentsWithHidden.mockResolvedValue([]);
  api.fetchStats.mockResolvedValue(defaultStats);
  api.fetchSummaryTitles.mockResolvedValue({});
  api.fetchSearchFilters.mockResolvedValue({
    projects: ["conversations"],
    models: ["opus"],
    tools: ["Bash"],
    topics: ["docker"],
  });
  // Settle search status so the polling effect doesn't reschedule.
  api.fetchSearchStatus.mockResolvedValue({
    mode: "hybrid",
    total_sessions: 100,
    embedded_sessions: 100,
    has_graph: true,
    concept_count: 50,
  });
  api.searchSessions.mockResolvedValue([sampleSearchResult]);
  api.fetchConversation.mockResolvedValue(sampleConversation);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  localStorage.clear();
});

async function renderAppReady() {
  const user = userEvent.setup();
  const utils = render(<App />);
  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: "Conversations" })
    ).toBeInTheDocument();
  });
  return { user, ...utils };
}

describe("App — initial render", () => {
  it("shows the loading screen until the backend reports ready", () => {
    api.fetchReady.mockResolvedValue({ ready: false });
    render(<App />);
    expect(
      screen.getByText("Loading conversations into database...")
    ).toBeInTheDocument();
  });

  it("renders header, provider select, three tab buttons, theme toggle, and stats once ready", async () => {
    await renderAppReady();
    expect(
      screen.getByRole("button", { name: "Conversations" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Dashboard" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Knowledge Graph" })
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    // Default theme is dark → toggle button reads "Light"
    expect(screen.getByRole("button", { name: "Light" })).toBeInTheDocument();
    // Stats appears in the .stats div as a pipe-delimited summary.
    // Don't match on "5 projects" alone — that substring also appears in the
    // provider <option> "Claude (5 projects)".
    await waitFor(() => {
      expect(screen.getByText(/5 projects \| 100 requests/)).toBeInTheDocument();
    });
  });
});

describe("App — search flow", () => {
  it("fires search after the 300ms debounce when query is 2+ chars", async () => {
    const { user } = await renderAppReady();
    const input = screen.getByPlaceholderText(/Search conversations/i);
    await user.type(input, "docker");
    await waitFor(
      () => {
        expect(api.searchSessions).toHaveBeenCalledWith("docker", "claude");
      },
      { timeout: 1500 }
    );
    await waitFor(() => {
      expect(
        document.querySelector(".search-result-card")
      ).toBeInTheDocument();
    });
  });

  it("does not fire search for a single-character query", async () => {
    const { user } = await renderAppReady();
    const input = screen.getByPlaceholderText(/Search conversations/i);
    await user.type(input, "a");
    // Wait past the 300ms debounce window — confirms no timer was scheduled.
    await new Promise((r) => setTimeout(r, 400));
    expect(api.searchSessions).not.toHaveBeenCalled();
  });

  it("clearing the query removes search results and shows the browsing empty state", async () => {
    const { user } = await renderAppReady();
    const input = screen.getByPlaceholderText(/Search conversations/i);
    await user.type(input, "docker");
    await waitFor(
      () => {
        expect(
          document.querySelector(".search-result-card")
        ).toBeInTheDocument();
      },
      { timeout: 1500 }
    );
    await user.clear(input);
    await waitFor(() => {
      expect(
        document.querySelector(".search-result-card")
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText("Select a project")).toBeInTheDocument();
  });
});

describe("App — keyboard shortcuts", () => {
  it("Cmd+K focuses the search input", async () => {
    const { user } = await renderAppReady();
    const input = screen.getByPlaceholderText(/Search conversations/i);
    expect(input).not.toHaveFocus();
    await user.keyboard("{Meta>}k{/Meta}");
    expect(input).toHaveFocus();
  });

  it("Ctrl+K also focuses the search input", async () => {
    const { user } = await renderAppReady();
    const input = screen.getByPlaceholderText(/Search conversations/i);
    await user.keyboard("{Control>}k{/Control}");
    expect(input).toHaveFocus();
  });

  it("Escape clears the value and blurs when the search input is focused", async () => {
    const { user } = await renderAppReady();
    const input = screen.getByPlaceholderText(/Search conversations/i);
    await user.click(input);
    await user.type(input, "test");
    expect(input).toHaveValue("test");
    expect(input).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(input).toHaveValue(""));
    expect(input).not.toHaveFocus();
  });
});

describe("App — search result interaction", () => {
  it("clicking a search result loads the matching conversation", async () => {
    const { user } = await renderAppReady();
    const input = screen.getByPlaceholderText(/Search conversations/i);
    await user.type(input, "docker");
    await waitFor(
      () => {
        expect(
          document.querySelector(".search-result-card")
        ).toBeInTheDocument();
      },
      { timeout: 1500 }
    );
    const card = document.querySelector(".search-result-card");
    await user.click(card);
    await waitFor(() => {
      expect(api.fetchConversation).toHaveBeenCalledWith(
        "conversations",
        "c1",
        "claude"
      );
    });
  });
});

describe("App — provider switching", () => {
  it("switching provider clears the search bar", async () => {
    const { user } = await renderAppReady();
    const input = screen.getByPlaceholderText(/Search conversations/i);
    await user.type(input, "docker");
    expect(input).toHaveValue("docker");
    await user.selectOptions(screen.getByRole("combobox"), "codex");
    await waitFor(() => expect(input).toHaveValue(""));
  });
});

describe("App — tab switching", () => {
  it("Conversations → Dashboard → Knowledge Graph → Conversations round-trip preserves the header", async () => {
    const { user } = await renderAppReady();
    expect(
      screen.getByPlaceholderText(/Search conversations/i)
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Dashboard" }));
    expect(screen.getByTestId("dashboard-stub")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText(/Search conversations/i)
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Knowledge Graph" }));
    expect(screen.getByTestId("kg-stub")).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-stub")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Conversations" }));
    expect(
      screen.getByPlaceholderText(/Search conversations/i)
    ).toBeInTheDocument();
    expect(screen.queryByTestId("kg-stub")).not.toBeInTheDocument();

    // Header tabs remain visible across all three tabs (regression row 28)
    expect(
      screen.getByRole("button", { name: "Conversations" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Dashboard" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Knowledge Graph" })
    ).toBeInTheDocument();
  });
});
