import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import RequestsPane from "../components/RequestsPane";

function defaultProps(overrides = {}) {
  return {
    width: 340,
    header: "Requests",
    isSearching: false,
    isInSearchMode: false,
    searchResults: null,
    searchQuery: "",
    onSelectSearchResult: vi.fn(),
    segments: [],
    selectedSegmentId: null,
    onSelectSegment: vi.fn(),
    selectedProject: null,
    onViewConversation: vi.fn(),
    onHideSegment: vi.fn(),
    onRestoreSegment: vi.fn(),
    onHideConversation: vi.fn(),
    onRestoreConversation: vi.fn(),
    showProject: false,
    showHidden: false,
    dateFrom: "",
    dateTo: "",
    summaryTitles: {},
    ...overrides,
  };
}

describe("RequestsPane", () => {
  it("renders the pane header text", () => {
    render(<RequestsPane {...defaultProps({ header: "My Header" })} />);
    expect(screen.getByText("My Header")).toBeInTheDocument();
  });

  it("applies the width style", () => {
    const { container } = render(
      <RequestsPane {...defaultProps({ width: 500 })} />
    );
    expect(container.querySelector(".pane-requests").style.width).toBe("500px");
  });

  it("shows 'Searching...' loading state when isSearching", () => {
    render(<RequestsPane {...defaultProps({ isSearching: true })} />);
    expect(screen.getByText("Searching...")).toBeInTheDocument();
  });

  it("shows 'Select a project' empty state when no project + no segments", () => {
    render(<RequestsPane {...defaultProps()} />);
    expect(screen.getByText("Select a project")).toBeInTheDocument();
  });

  it("shows 'No requests found' when project selected but no segments", () => {
    render(
      <RequestsPane
        {...defaultProps({ selectedProject: "alpha", segments: [] })}
      />
    );
    expect(screen.getByText("No requests found")).toBeInTheDocument();
  });

  it("renders SearchResults when in search mode + results present", () => {
    const { container } = render(
      <RequestsPane
        {...defaultProps({
          isInSearchMode: true,
          searchResults: [
            {
              session_id: "s1",
              project: "p",
              date: "2026-01-01",
              snippet: "match",
              tools: {},
              turn_count: 1,
              topics: [],
              conversation_id: "c1",
              rank: 1,
            },
          ],
        })}
      />
    );
    // SearchResults renders the rank prefix
    expect(container.textContent).toContain("#1");
  });

  it("renders RequestList when there are segments and not in search mode", () => {
    render(
      <RequestsPane
        {...defaultProps({
          selectedProject: "p1",
          segments: [
            {
              id: "s1",
              conversation_id: "c1",
              timestamp: "2026-01-01T00:00:00Z",
              preview: "Hello",
              hidden: false,
              project_name: "p1",
              metrics: { word_count: 50, tool_call_count: 0 },
            },
          ],
        })}
      />
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("priority: search loading beats search results", () => {
    render(
      <RequestsPane
        {...defaultProps({
          isSearching: true,
          isInSearchMode: true,
          searchResults: [{ session_id: "s1", project: "p", date: "x", snippet: "y", tools: {}, turn_count: 1, topics: [], conversation_id: "c", rank: 1 }],
        })}
      />
    );
    expect(screen.getByText("Searching...")).toBeInTheDocument();
  });

  it("priority: search results beat segments when in search mode", () => {
    render(
      <RequestsPane
        {...defaultProps({
          isInSearchMode: true,
          searchResults: [{ session_id: "s1", project: "p", date: "x", snippet: "search snip", tools: {}, turn_count: 1, topics: [], conversation_id: "c", rank: 1 }],
          segments: [
            {
              id: "s1",
              conversation_id: "c1",
              timestamp: "x",
              preview: "browse",
              hidden: false,
              project_name: "p",
              metrics: { word_count: 1, tool_call_count: 0 },
            },
          ],
        })}
      />
    );
    expect(screen.queryByText("browse")).not.toBeInTheDocument();
  });

  it("renders segments without selectedProject passes null onViewConversation", () => {
    // Branch coverage: `selectedProject ? onViewConversation : null` → null path.
    render(
      <RequestsPane
        {...defaultProps({
          selectedProject: null,
          segments: [
            {
              id: "s2",
              conversation_id: "c2",
              timestamp: "2026-03-01T00:00:00Z",
              preview: "global context",
              hidden: false,
              project_name: "p",
              metrics: { word_count: 10, tool_call_count: 0 },
            },
          ],
        })}
      />
    );
    expect(screen.getByText("global context")).toBeInTheDocument();
  });
});
