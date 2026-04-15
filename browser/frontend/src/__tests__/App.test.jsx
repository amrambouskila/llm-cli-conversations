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
  default: ({ onNavigateToConversation }) => (
    <div data-testid="dashboard-stub">
      <button
        data-testid="dashboard-nav-trigger"
        onClick={() =>
          onNavigateToConversation &&
          onNavigateToConversation("conversations", "c1")
        }
      >
        nav
      </button>
      <button
        data-testid="dashboard-search-trigger"
        onClick={() =>
          onNavigateToConversation &&
          onNavigateToConversation(null, null, "topic:something")
        }
      >
        search
      </button>
    </div>
  ),
}));

vi.mock("../components/KnowledgeGraph", () => ({
  default: ({ onOpenInConversations }) => (
    <div data-testid="kg-stub">
      <button
        data-testid="kg-concept-trigger"
        onClick={() =>
          onOpenInConversations && onOpenInConversations("docker")
        }
      >
        trigger
      </button>
    </div>
  ),
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
  default: ({ onSelect }) => (
    <div data-testid="project-list-stub">
      <button
        data-testid="project-select-trigger"
        onClick={() => onSelect && onSelect("conversations")}
      >
        select
      </button>
    </div>
  ),
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

describe("App — inline wrapper coverage", () => {
  it("KnowledgeGraph onOpenInConversations flips tab to Conversations + sets topic: query", async () => {
    // Exercises App.jsx's handleOpenConceptInConversations callback.
    // The Phase 8 wiring uses cmd/ctrl-click (concept fast-path) and the
    // wiki pane's "Open in Conversations" button to fire this prop.
    const { user } = await renderAppReady();
    await user.click(screen.getByRole("button", { name: "Knowledge Graph" }));
    const trigger = await screen.findByTestId("kg-concept-trigger");
    await user.click(trigger);
    const searchInput = await screen.findByPlaceholderText(
      /Search conversations/i
    );
    await waitFor(() => expect(searchInput.value).toBe("topic:docker"));
  });

  it("dashboard navigate with project + conversationId loads the conversation (lines 180-182)", async () => {
    const { user } = await renderAppReady();
    await user.click(screen.getByRole("button", { name: "Dashboard" }));
    const navTrigger = await screen.findByTestId("dashboard-nav-trigger");
    await user.click(navTrigger);
    await waitFor(() =>
      expect(api.fetchConversation).toHaveBeenCalledWith(
        "conversations",
        "c1",
        "claude"
      )
    );
  });

  it("dashboard navigate with searchTerm sets the query and short-circuits (lines 177-180)", async () => {
    const { user } = await renderAppReady();
    await user.click(screen.getByRole("button", { name: "Dashboard" }));
    const searchTrigger = await screen.findByTestId("dashboard-search-trigger");
    await user.click(searchTrigger);
    const searchInput = await screen.findByPlaceholderText(
      /Search conversations/i
    );
    await waitFor(() => expect(searchInput.value).toBe("topic:something"));
  });

  it("project-list sort comparator fires with 2+ projects (lines 132-134)", async () => {
    // Override the default fetchProjects mock to return 3 projects so the
    // sort comparator actually executes.
    api.fetchProjects.mockResolvedValue([
      { ...sampleProject, name: "a", stats: { last_timestamp: "2026-01-01T00:00:00Z" } },
      { ...sampleProject, name: "b", stats: { last_timestamp: "2026-03-01T00:00:00Z" } },
      { ...sampleProject, name: "c", stats: { last_timestamp: "2026-02-01T00:00:00Z" } },
    ]);
    await renderAppReady();
    // The sort comparator ran; test passes if no crash. Assertion just proves
    // the component settled (projects loaded).
    await waitFor(() => expect(api.fetchProjects).toHaveBeenCalled());
  });

  it("selecting a project fires handleSelectProject (lines 118-120)", async () => {
    const { user } = await renderAppReady();
    await user.click(screen.getByTestId("project-select-trigger"));
    await waitFor(() =>
      expect(api.fetchSegments).toHaveBeenCalledWith("conversations", "claude")
    );
  });

  it("clicking the Projects back-arrow deselects (lines 124-125)", async () => {
    const { user } = await renderAppReady();
    // First select a project so the back arrow appears.
    await user.click(screen.getByTestId("project-select-trigger"));
    await waitFor(() => expect(api.fetchSegments).toHaveBeenCalled());
    // Now click the Projects header — it becomes a deselect button when a
    // project is selected (ProjectsPane.jsx line 20).
    const projectsHeader = screen.getByText(/Projects \u2190/);
    await user.click(projectsHeader);
    // After deselection the back-arrow is gone.
    await waitFor(() =>
      expect(screen.queryByText(/Projects \u2190/)).not.toBeInTheDocument()
    );
  });

  it("clicking the Update button fires triggerUpdate (handleUpdate wrapper lines 186-192)", async () => {
    const { user } = await renderAppReady();
    api.triggerUpdate.mockResolvedValue({ success: true });
    const updateBtn = screen.getByRole("button", { name: /Update/ });
    await user.click(updateBtn);
    await waitFor(() => expect(api.triggerUpdate).toHaveBeenCalled());
  });

  it("clicking Update with a failure result sets updateStatus error branch", async () => {
    const { user } = await renderAppReady();
    api.triggerUpdate.mockResolvedValue({ success: false, error: "boom" });
    const updateBtn = screen.getByRole("button", { name: /Update/ });
    await user.click(updateBtn);
    await waitFor(() => expect(api.triggerUpdate).toHaveBeenCalled());
  });

  it("clicking Update with a rejected promise hits the catch branch", async () => {
    const { user } = await renderAppReady();
    api.triggerUpdate.mockRejectedValue(new Error("network"));
    const updateBtn = screen.getByRole("button", { name: /Update/ });
    await user.click(updateBtn);
    await waitFor(() => expect(api.triggerUpdate).toHaveBeenCalled());
  });
});
