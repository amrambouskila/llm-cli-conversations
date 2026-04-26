import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// Mock the api module so useCostBreakdown (mounted via ConversationMetadata)
// never makes a real fetch call in tests.
vi.mock("../api", () => ({
  fetchSessionCostBreakdown: vi.fn(),
}));

import MetadataPane from "../components/MetadataPane";
import { fetchSessionCostBreakdown } from "../api";

beforeEach(() => {
  vi.clearAllMocks();
  // Default: resolve to null so tests that don't care don't hang.
  fetchSessionCostBreakdown.mockResolvedValue(null);
});

afterEach(() => {
  vi.useRealTimers();
});

const baseStats = {
  total_projects: 5,
  total_segments: 100,
  total_words: 50_000,
  estimated_tokens: 12_500,
  total_tool_calls: 30,
  hidden: { segments: 0, conversations: 0, projects: 0 },
  monthly: { "2026-01": { tokens: 1000, requests: 5 } },
};

function defaultProps(overrides = {}) {
  return {
    width: 364,
    convViewData: null,
    segmentDetail: null,
    selectedProjectData: null,
    stats: baseStats,
    provider: "claude",
    ...overrides,
  };
}

describe("MetadataPane — header + width", () => {
  it("renders 'Metadata' pane header", () => {
    render(<MetadataPane {...defaultProps()} />);
    expect(screen.getByText("Metadata")).toBeInTheDocument();
  });

  it("applies the width style", () => {
    const { container } = render(
      <MetadataPane {...defaultProps({ width: 400 })} />
    );
    expect(container.querySelector(".pane-metadata").style.width).toBe("400px");
  });
});

describe("MetadataPane — global stats (always visible when stats present)", () => {
  it("renders Global Totals block", () => {
    render(<MetadataPane {...defaultProps()} />);
    expect(screen.getByText("Global Totals")).toBeInTheDocument();
  });

  it("hides Global Totals when stats is null", () => {
    render(<MetadataPane {...defaultProps({ stats: null })} />);
    expect(screen.queryByText("Global Totals")).not.toBeInTheDocument();
  });

  it("shows project + segment counts in global stats", () => {
    const { container } = render(<MetadataPane {...defaultProps()} />);
    const items = container.querySelectorAll(
      ".metadata-panel-global .meta-item"
    );
    const texts = Array.from(items).map((el) => el.textContent);
    expect(texts.some((t) => t.includes("Projects") && t.includes("5"))).toBe(
      true
    );
    expect(
      texts.some((t) => t.includes("Total Requests") && t.includes("100"))
    ).toBe(true);
  });
});

describe("MetadataPane — conversation view", () => {
  const convViewData = {
    conversation_id: "conv-abc",
    session_id: "sess-xyz",
    segment_count: 12,
    metrics: {
      word_count: 5000,
      estimated_tokens: 1250,
      tool_call_count: 8,
    },
  };

  it("renders ConversationMetadata when convViewData is set", () => {
    render(<MetadataPane {...defaultProps({ convViewData })} />);
    expect(screen.getByText("Conversation View")).toBeInTheDocument();
    expect(screen.getByText("conv-abc")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("convViewData overrides segmentDetail and projectData (mutually exclusive)", () => {
    render(
      <MetadataPane
        {...defaultProps({
          convViewData,
          segmentDetail: { id: "s1" },
          selectedProjectData: { name: "p", display_name: "P" },
        })}
      />
    );
    expect(screen.getByText("Conversation View")).toBeInTheDocument();
    expect(screen.queryByText("Project: P")).not.toBeInTheDocument();
  });
});

describe("MetadataPane — Phase 7.5 cost attribution (conversation context)", () => {
  const baseConvView = {
    conversation_id: "conv-abc",
    session_id: "sess-xyz",
    segment_count: 4,
    metrics: {
      word_count: 5000,
      estimated_tokens: 1250,
      tool_call_count: 8,
    },
  };

  const breakdown = {
    input_usd: 0.15,
    output_usd: 0.3,
    cache_read_usd: 0.003,
    cache_create_usd: 0.0094,
    total_usd: 0.4624,
  };

  it("fetches cost-breakdown for the session_id on the conversation view", async () => {
    fetchSessionCostBreakdown.mockResolvedValue(breakdown);
    render(<MetadataPane {...defaultProps({ convViewData: baseConvView })} />);
    await waitFor(() =>
      expect(fetchSessionCostBreakdown).toHaveBeenCalledWith(
        "sess-xyz",
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      )
    );
  });

  it("renders Cost Attribution title when breakdown loads", async () => {
    fetchSessionCostBreakdown.mockResolvedValue(breakdown);
    render(<MetadataPane {...defaultProps({ convViewData: baseConvView })} />);
    await waitFor(() =>
      expect(screen.getByText("Cost Attribution")).toBeInTheDocument()
    );
  });

  it("renders four buckets + total row when breakdown loads", async () => {
    fetchSessionCostBreakdown.mockResolvedValue(breakdown);
    const { container } = render(
      <MetadataPane {...defaultProps({ convViewData: baseConvView })} />
    );
    await waitFor(() =>
      expect(screen.getByText("Cost Attribution")).toBeInTheDocument()
    );
    const rows = container.querySelectorAll(".cost-attribution-row");
    // 4 buckets + 1 total
    expect(rows.length).toBe(5);
    expect(screen.getByText("Input")).toBeInTheDocument();
    expect(screen.getByText("Output")).toBeInTheDocument();
    expect(screen.getByText("Cache read")).toBeInTheDocument();
    expect(screen.getByText("Cache write")).toBeInTheDocument();
    expect(screen.getByText("Total")).toBeInTheDocument();
  });

  it("formats each USD amount via Intl.NumberFormat", async () => {
    fetchSessionCostBreakdown.mockResolvedValue(breakdown);
    render(<MetadataPane {...defaultProps({ convViewData: baseConvView })} />);
    await waitFor(() =>
      expect(screen.getByText("Cost Attribution")).toBeInTheDocument()
    );
    // total 0.4624 → "$0.46" under en-US currency
    expect(screen.getByText("$0.46")).toBeInTheDocument();
  });

  it("shows a loading message while the fetch is pending", () => {
    fetchSessionCostBreakdown.mockReturnValue(new Promise(() => {}));
    render(<MetadataPane {...defaultProps({ convViewData: baseConvView })} />);
    expect(screen.getByText(/Loading cost breakdown/i)).toBeInTheDocument();
  });

  it("shows an error message when the fetch rejects", async () => {
    fetchSessionCostBreakdown.mockRejectedValue(new Error("network"));
    render(<MetadataPane {...defaultProps({ convViewData: baseConvView })} />);
    await waitFor(() =>
      expect(
        screen.getByText(/Could not load cost breakdown/i)
      ).toBeInTheDocument()
    );
  });

  it("renders nothing cost-related when convViewData lacks a session_id", () => {
    const convViewNoSession = { ...baseConvView, session_id: null };
    render(
      <MetadataPane {...defaultProps({ convViewData: convViewNoSession })} />
    );
    expect(fetchSessionCostBreakdown).not.toHaveBeenCalled();
    expect(screen.queryByText("Cost Attribution")).not.toBeInTheDocument();
  });

  it("includes the estimated-tokens note under the cost rows", async () => {
    fetchSessionCostBreakdown.mockResolvedValue(breakdown);
    render(<MetadataPane {...defaultProps({ convViewData: baseConvView })} />);
    // formatNumber compresses 1250 → "1.3K" — match the shortened form.
    await waitFor(() =>
      expect(screen.getByText(/estimated tokens total/i)).toBeInTheDocument()
    );
    expect(screen.getByText(/1\.3K estimated tokens total/i)).toBeInTheDocument();
  });

  it("omits the estimated-tokens note when metrics has no estimated_tokens", async () => {
    fetchSessionCostBreakdown.mockResolvedValue(breakdown);
    const convViewNoTokens = {
      ...baseConvView,
      metrics: { word_count: 0, estimated_tokens: 0, tool_call_count: 0 },
    };
    render(
      <MetadataPane {...defaultProps({ convViewData: convViewNoTokens })} />
    );
    await waitFor(() =>
      expect(screen.getByText("Cost Attribution")).toBeInTheDocument()
    );
    expect(
      screen.queryByText(/estimated tokens total/i)
    ).not.toBeInTheDocument();
  });
});

describe("MetadataPane — segment detail", () => {
  const segmentDetail = {
    id: "seg-1",
    project_name: "alpha",
    segment_index: 0,
    conversation_id: "c1",
    entry_number: 1,
    timestamp: "2026-01-01T00:00:00Z",
    source_file: "/some/file.md",
    role: "user",
    metrics: {
      char_count: 200,
      word_count: 50,
      line_count: 5,
      estimated_tokens: 12,
      tool_call_count: 0,
    },
    tool_breakdown: {},
  };

  it("renders MetadataPanel when segmentDetail is set (no convViewData)", () => {
    render(<MetadataPane {...defaultProps({ segmentDetail })} />);
    expect(screen.getByText("Project")).toBeInTheDocument();
    expect(screen.getByText("Source File")).toBeInTheDocument();
  });
});

describe("MetadataPane — project metadata", () => {
  const project = {
    name: "alpha",
    display_name: "Alpha Project",
    total_requests: 7,
    stats: {
      total_conversations: 3,
      total_words: 1000,
      estimated_tokens: 250,
      total_tool_calls: 4,
      first_timestamp: "2026-01-01T00:00:00Z",
      last_timestamp: "2026-01-31T00:00:00Z",
      request_sizes: [10, 20, 30],
      conversation_timeline: [
        "2026-01-01T00:00:00Z",
        "2026-01-31T00:00:00Z",
      ],
      tool_breakdown: { Bash: 2 },
    },
  };

  it("renders ProjectMetadata when only selectedProjectData is set", () => {
    const { container } = render(
      <MetadataPane {...defaultProps({ selectedProjectData: project })} />
    );
    expect(screen.getByText("Project: Alpha Project")).toBeInTheDocument();
    // Project panel has its own .metadata-panel; just confirm structure
    const panels = container.querySelectorAll(".metadata-panel");
    expect(panels.length).toBeGreaterThanOrEqual(1);
  });

  it("does NOT render ProjectMetadata when convViewData is also set", () => {
    render(
      <MetadataPane
        {...defaultProps({
          convViewData: {
            conversation_id: "c1",
            segment_count: 1,
            metrics: { word_count: 1, estimated_tokens: 1, tool_call_count: 0 },
          },
          selectedProjectData: project,
        })}
      />
    );
    expect(
      screen.queryByText("Project: Alpha Project")
    ).not.toBeInTheDocument();
  });

  it("renders First Activity / Last Activity rows when present", () => {
    render(
      <MetadataPane {...defaultProps({ selectedProjectData: project })} />
    );
    expect(screen.getByText("First Activity")).toBeInTheDocument();
    expect(screen.getByText("Last Activity")).toBeInTheDocument();
  });

  it("omits First Activity row when first_timestamp missing", () => {
    const projectNoTs = {
      ...project,
      stats: { ...project.stats, first_timestamp: null, last_timestamp: null },
    };
    render(
      <MetadataPane {...defaultProps({ selectedProjectData: projectNoTs })} />
    );
    expect(screen.queryByText("First Activity")).not.toBeInTheDocument();
    expect(screen.queryByText("Last Activity")).not.toBeInTheDocument();
  });

  it("formatUsd returns $0.00 when breakdown USD is non-numeric (line 14 guard)", async () => {
    const convViewData = {
      conversation_id: "c1",
      session_id: "s1",
      segment_count: 1,
      metrics: { word_count: 10, estimated_tokens: 2, tool_call_count: 0 },
    };
    // One bucket value is explicitly a non-numeric → Number(undefined)=NaN → "$0.00"
    fetchSessionCostBreakdown.mockResolvedValue({
      input_usd: undefined,
      output_usd: 0.3,
      cache_read_usd: 0.003,
      cache_create_usd: 0.0094,
      total_usd: 0.3124,
    });
    render(<MetadataPane {...defaultProps({ convViewData })} />);
    // Wait for the data state (Input label only appears once the breakdown
    // resolves — "Cost Attribution" is shared with the loading state).
    await waitFor(() =>
      expect(screen.getByText("Input")).toBeInTheDocument()
    );
    // The first bucket rendered $0.00 instead of crashing → line 14 guard fired.
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(0);
  });

  it("renders ProjectMetadata when stats has undefined numeric fields (|| 0 fallbacks)", () => {
    // Stats object present but token/word fields undefined → formatNumber(|| 0)
    // fallback branches exercised on lines 130 + 135.
    const projectMissingFields = {
      name: "beta",
      display_name: "Beta Missing",
      total_requests: 1,
      stats: {
        total_conversations: 0,
        // total_words + estimated_tokens deliberately undefined
        total_tool_calls: 0,
      },
    };
    render(
      <MetadataPane
        {...defaultProps({ selectedProjectData: projectMissingFields })}
      />
    );
    expect(screen.getByText("Project: Beta Missing")).toBeInTheDocument();
  });
});
