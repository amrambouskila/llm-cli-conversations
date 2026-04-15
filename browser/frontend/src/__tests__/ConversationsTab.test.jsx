import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("../components/SummaryPanel", () => ({
  default: () => <div data-testid="summary-panel-stub" />,
}));

vi.mock("../api", () => ({
  requestSummary: vi.fn(),
  getSummary: vi.fn(),
  requestConvSummary: vi.fn(),
  getConvSummary: vi.fn(),
}));

import ConversationsTab from "../components/ConversationsTab";

function defaultProps(overrides = {}) {
  return {
    searchRef: { current: null },
    searchQuery: "",
    onQueryChange: vi.fn(),
    searchMode: null,
    showDateFilter: false,
    onToggleDateFilter: vi.fn(),
    isSearching: false,
    isInSearchMode: false,
    searchResults: null,
    onSelectSearchResult: vi.fn(),
    filterOptions: { projects: [], models: [], tools: [], topics: [] },
    pendingDateFrom: "",
    onPendingDateFromChange: vi.fn(),
    pendingDateTo: "",
    onPendingDateToChange: vi.fn(),
    dateFrom: "",
    dateTo: "",
    onApplyDateFilter: vi.fn(),
    onClearDateFilter: vi.fn(),
    mainRef: { current: null },
    startDrag: vi.fn(),
    projectsWidth: 220,
    requestsWidth: 340,
    metadataWidth: 364,
    projects: [],
    selectedProject: null,
    onSelectProject: vi.fn(),
    onDeselectProject: vi.fn(),
    onHideProject: vi.fn(),
    onRestoreProject: vi.fn(),
    showHidden: false,
    requestsHeader: "Requests",
    segments: [],
    selectedSegmentId: null,
    onSelectSegment: vi.fn(),
    onViewConversation: vi.fn(),
    onHideSegment: vi.fn(),
    onRestoreSegment: vi.fn(),
    onHideConversation: vi.fn(),
    onRestoreConversation: vi.fn(),
    showProject: false,
    summaryTitles: {},
    viewingMarkdown: null,
    viewingSource: null,
    onExport: vi.fn(),
    convViewData: null,
    segmentDetail: null,
    provider: "claude",
    onTitleReady: vi.fn(),
    selectedProjectData: null,
    stats: { total_projects: 0, total_segments: 0, total_words: 0, estimated_tokens: 0, total_tool_calls: 0, hidden: { segments: 0, conversations: 0, projects: 0 }, monthly: {} },
    ...overrides,
  };
}

describe("ConversationsTab — composition", () => {
  it("renders SearchBar", () => {
    render(<ConversationsTab {...defaultProps()} />);
    expect(
      screen.getByPlaceholderText(/Search conversations/)
    ).toBeInTheDocument();
  });

  it("renders all 3 panes (Projects / Requests / Metadata) in main", () => {
    const { container } = render(<ConversationsTab {...defaultProps()} />);
    expect(container.querySelector(".pane-projects")).not.toBeNull();
    expect(container.querySelector(".pane-requests")).not.toBeNull();
    expect(container.querySelector(".pane-metadata")).not.toBeNull();
  });

  it("renders the content pane area", () => {
    const { container } = render(<ConversationsTab {...defaultProps()} />);
    expect(container.querySelector(".pane-content-area")).not.toBeNull();
  });

  it("renders 3 resize handles", () => {
    const { container } = render(<ConversationsTab {...defaultProps()} />);
    expect(container.querySelectorAll(".resize-handle").length).toBe(3);
  });

  it("does NOT render FilterBar when showDateFilter is false", () => {
    const { container } = render(<ConversationsTab {...defaultProps()} />);
    expect(container.querySelector(".filter-bar-expanded")).toBeNull();
  });

  it("renders FilterBar when showDateFilter is true", () => {
    const { container } = render(
      <ConversationsTab {...defaultProps({ showDateFilter: true })} />
    );
    expect(container.querySelector(".filter-bar-expanded")).not.toBeNull();
  });

  it("uses the requestsHeader prop in the requests pane", () => {
    render(
      <ConversationsTab {...defaultProps({ requestsHeader: "Custom Header" })} />
    );
    expect(screen.getByText("Custom Header")).toBeInTheDocument();
  });

  it("applies pane width props correctly", () => {
    const { container } = render(
      <ConversationsTab
        {...defaultProps({
          projectsWidth: 100,
          requestsWidth: 200,
          metadataWidth: 300,
        })}
      />
    );
    expect(container.querySelector(".pane-projects").style.width).toBe("100px");
    expect(container.querySelector(".pane-requests").style.width).toBe("200px");
    expect(container.querySelector(".pane-metadata").style.width).toBe("300px");
  });
});

describe("ConversationsTab — resize-handle onMouseDown wrappers", () => {
  it("fires startDrag('projects') when the first handle is mousedowned", () => {
    const startDrag = vi.fn();
    const { container } = render(
      <ConversationsTab {...defaultProps({ startDrag })} />
    );
    const handles = container.querySelectorAll(".resize-handle");
    fireEvent.mouseDown(handles[0]);
    expect(startDrag).toHaveBeenCalledWith("projects");
  });

  it("fires startDrag('requests') when the second handle is mousedowned", () => {
    const startDrag = vi.fn();
    const { container } = render(
      <ConversationsTab {...defaultProps({ startDrag })} />
    );
    const handles = container.querySelectorAll(".resize-handle");
    fireEvent.mouseDown(handles[1]);
    expect(startDrag).toHaveBeenCalledWith("requests");
  });

  it("fires startDrag('metadata') when the third handle is mousedowned", () => {
    const startDrag = vi.fn();
    const { container } = render(
      <ConversationsTab {...defaultProps({ startDrag })} />
    );
    const handles = container.querySelectorAll(".resize-handle");
    fireEvent.mouseDown(handles[2]);
    expect(startDrag).toHaveBeenCalledWith("metadata");
  });
});
