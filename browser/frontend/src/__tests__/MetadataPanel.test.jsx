import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("../components/Charts", () => ({
  TokenCostEstimate: () => null,
  ToolBreakdownChart: () => null,
}));

import MetadataPanel from "../components/MetadataPanel";

const baseSegment = (overrides = {}) => ({
  project_name: "conversations",
  segment_index: 4,
  conversation_id: "abc123",
  entry_number: 7,
  timestamp: "2026-04-01T10:00:00Z",
  source_file: "/data/markdown/conversations.md",
  metrics: {
    char_count: 12_345,
    word_count: 2_500,
    line_count: 180,
    estimated_tokens: 3_086,
    tool_call_count: 12,
  },
  tool_breakdown: { Bash: 4, Edit: 3 },
  ...overrides,
});

describe("MetadataPanel", () => {
  it("returns null when segment is not provided", () => {
    const { container } = render(<MetadataPanel segment={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders all eleven metadata items with their values", () => {
    render(<MetadataPanel segment={baseSegment()} />);
    expect(screen.getByText("Project")).toBeInTheDocument();
    expect(screen.getByText("conversations")).toBeInTheDocument();
    expect(screen.getByText("Segment #")).toBeInTheDocument();
    // segment_index 4 → displayed as "5" (1-indexed)
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Conversation")).toBeInTheDocument();
    expect(screen.getByText("abc123")).toBeInTheDocument();
    expect(screen.getByText("Entry #")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Timestamp")).toBeInTheDocument();
    expect(screen.getByText("Characters")).toBeInTheDocument();
    expect(screen.getByText("12.3K")).toBeInTheDocument();
    expect(screen.getByText("Words")).toBeInTheDocument();
    expect(screen.getByText("2.5K")).toBeInTheDocument();
    expect(screen.getByText("Lines")).toBeInTheDocument();
    expect(screen.getByText("180")).toBeInTheDocument();
    expect(screen.getByText("Est. Tokens")).toBeInTheDocument();
    expect(screen.getByText("3.1K")).toBeInTheDocument();
    expect(screen.getByText("Tool Calls")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Source File")).toBeInTheDocument();
    // basename of /data/markdown/conversations.md
    expect(screen.getByText("conversations.md")).toBeInTheDocument();
  });

  it("falls back to N/A for missing conversation_id and entry_number", () => {
    render(
      <MetadataPanel
        segment={baseSegment({ conversation_id: null, entry_number: null })}
      />
    );
    // Two N/A spans expected (conversation + entry #)
    expect(screen.getAllByText("N/A").length).toBe(2);
  });

  it("renders timestamp via formatTimestamp (non-empty, not N/A)", () => {
    const { container } = render(
      <MetadataPanel segment={baseSegment()} />
    );
    const items = container.querySelectorAll(".meta-item");
    const tsItem = Array.from(items).find(
      (el) => el.querySelector(".label")?.textContent === "Timestamp"
    );
    expect(tsItem).toBeDefined();
    const tsValue = tsItem.querySelector(".value").textContent;
    expect(tsValue.length).toBeGreaterThan(0);
    expect(tsValue).not.toBe("N/A");
  });
});
