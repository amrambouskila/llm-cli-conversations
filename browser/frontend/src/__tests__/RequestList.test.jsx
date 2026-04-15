import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RequestList from "../components/RequestList";

function makeSegment(overrides = {}) {
  return {
    id: "seg1",
    conversation_id: "conv1",
    timestamp: "2026-01-15T10:00:00Z",
    preview: "Hello world",
    hidden: false,
    project_name: "alpha",
    metrics: { word_count: 100, tool_call_count: 0 },
    ...overrides,
  };
}

describe("RequestList — empty state", () => {
  it("renders 'No requests found' when segments is empty", () => {
    render(<RequestList segments={[]} onSelect={() => {}} />);
    expect(screen.getByText("No requests found")).toBeInTheDocument();
  });

  it("renders 'No requests found' when date filter excludes all segments", () => {
    render(
      <RequestList
        segments={[makeSegment()]}
        onSelect={() => {}}
        dateFrom="2027-01-01"
      />
    );
    expect(screen.getByText("No requests found")).toBeInTheDocument();
  });
});

describe("RequestList — rendering", () => {
  it("renders one entry per segment with its preview", () => {
    const segments = [
      makeSegment({ id: "s1", preview: "First message" }),
      makeSegment({ id: "s2", preview: "Second message" }),
    ];
    render(<RequestList segments={segments} onSelect={() => {}} />);
    expect(screen.getByText("First message")).toBeInTheDocument();
    expect(screen.getByText("Second message")).toBeInTheDocument();
  });

  it("adds 'selected' class to the matching segment", () => {
    const { container } = render(
      <RequestList
        segments={[makeSegment({ id: "a" }), makeSegment({ id: "b" })]}
        selectedId="a"
        onSelect={() => {}}
      />
    );
    const items = container.querySelectorAll(".request-item");
    expect(items[0].className).toContain("selected");
    expect(items[1].className).not.toContain("selected");
  });

  it("renders the project name when showProject is true", () => {
    render(
      <RequestList
        segments={[makeSegment({ project_name: "my-proj" })]}
        onSelect={() => {}}
        showProject
      />
    );
    expect(screen.getByText("my-proj")).toBeInTheDocument();
  });

  it("does NOT render the project name when showProject is false", () => {
    render(
      <RequestList
        segments={[makeSegment({ project_name: "my-proj" })]}
        onSelect={() => {}}
      />
    );
    expect(screen.queryByText("my-proj")).not.toBeInTheDocument();
  });

  it("shows 'N tools' badge when tool_call_count > 0", () => {
    render(
      <RequestList
        segments={[
          makeSegment({
            metrics: { word_count: 50, tool_call_count: 3 },
          }),
        ]}
        onSelect={() => {}}
      />
    );
    expect(screen.getByText("3 tools")).toBeInTheDocument();
  });

  it("omits tools badge when tool_call_count is 0", () => {
    render(
      <RequestList
        segments={[makeSegment()]}
        onSelect={() => {}}
      />
    );
    expect(screen.queryByText(/tools$/)).not.toBeInTheDocument();
  });

  it("renders 'hidden' badge on hidden segments", () => {
    render(
      <RequestList
        segments={[makeSegment({ hidden: true })]}
        onSelect={() => {}}
        onRestoreSegment={() => {}}
      />
    );
    expect(screen.getByText("hidden")).toBeInTheDocument();
  });

  it("renders summary title in preview when provided", () => {
    const seg = makeSegment({ id: "seg1", preview: "Fallback text" });
    render(
      <RequestList
        segments={[seg]}
        onSelect={() => {}}
        summaryTitles={{ seg1: "Generated title" }}
      />
    );
    expect(screen.getByText("Generated title")).toBeInTheDocument();
    expect(screen.queryByText("Fallback text")).not.toBeInTheDocument();
  });
});

describe("RequestList — grouping by conversation", () => {
  it("single conversation does NOT render a conversation header", () => {
    const { container } = render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1" }),
          makeSegment({ id: "b", conversation_id: "c1" }),
        ]}
        onSelect={() => {}}
      />
    );
    expect(container.querySelector(".conv-header")).toBeNull();
  });

  it("multiple conversations render one header each", () => {
    const { container } = render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1aaaaaaaa" }),
          makeSegment({ id: "b", conversation_id: "c2bbbbbbbb" }),
        ]}
        onSelect={() => {}}
      />
    );
    expect(container.querySelectorAll(".conv-header").length).toBe(2);
  });

  it("shows 'N requests' on conversation header", () => {
    render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1aaaaaaaa" }),
          makeSegment({ id: "b", conversation_id: "c1aaaaaaaa" }),
          makeSegment({ id: "c", conversation_id: "c2bbbbbbbb" }),
        ]}
        onSelect={() => {}}
      />
    );
    expect(screen.getByText("2 requests")).toBeInTheDocument();
    expect(screen.getByText("1 request")).toBeInTheDocument();
  });

  it("uses summary title for conversation header when available", () => {
    render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "conv1" }),
          makeSegment({ id: "b", conversation_id: "conv2" }),
        ]}
        onSelect={() => {}}
        projectName="alpha"
        summaryTitles={{ conv_alpha_conv1: "Conversation title" }}
      />
    );
    expect(screen.getByText("Conversation title")).toBeInTheDocument();
  });

  it("falls back to 8-char truncated conversation id when no summary title", () => {
    render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1aaaaaaaabbbbbb" }),
          makeSegment({ id: "b", conversation_id: "c2bbbbbbbbcccccc" }),
        ]}
        onSelect={() => {}}
      />
    );
    expect(screen.getByText("c1aaaaaa")).toBeInTheDocument();
    expect(screen.getByText("c2bbbbbb")).toBeInTheDocument();
  });

  it("renders 'unknown' label for segment without a conversation id", () => {
    render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: null }),
          makeSegment({ id: "b", conversation_id: "c1xxxxxx" }),
        ]}
        onSelect={() => {}}
      />
    );
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });
});

describe("RequestList — collapse toggle", () => {
  it("clicking the toggle collapses the conversation's segments", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1" }),
          makeSegment({ id: "b", conversation_id: "c1" }),
          makeSegment({ id: "c", conversation_id: "c2" }),
        ]}
        onSelect={() => {}}
      />
    );
    expect(container.querySelectorAll(".request-item").length).toBe(3);
    const firstToggle = container.querySelectorAll(".conv-toggle")[0];
    await user.click(firstToggle);
    // First conversation's 2 segments hidden, c2's 1 segment remains
    expect(container.querySelectorAll(".request-item").length).toBe(1);
  });

  it("clicking the toggle again expands the conversation", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1" }),
          makeSegment({ id: "b", conversation_id: "c2" }),
        ]}
        onSelect={() => {}}
      />
    );
    const firstToggle = container.querySelectorAll(".conv-toggle")[0];
    await user.click(firstToggle);
    expect(container.querySelectorAll(".request-item").length).toBe(1);
    await user.click(firstToggle);
    expect(container.querySelectorAll(".request-item").length).toBe(2);
  });

  it("clicking the conv-label also toggles", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1" }),
          makeSegment({ id: "b", conversation_id: "c2" }),
        ]}
        onSelect={() => {}}
      />
    );
    const label = container.querySelectorAll(".conv-label")[0];
    await user.click(label);
    expect(container.querySelectorAll(".request-item").length).toBe(1);
  });

  it("clicking the conv-ts timestamp also toggles", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1" }),
          makeSegment({ id: "b", conversation_id: "c2" }),
        ]}
        onSelect={() => {}}
      />
    );
    const ts = container.querySelectorAll(".conv-ts")[0];
    await user.click(ts);
    expect(container.querySelectorAll(".request-item").length).toBe(1);
  });
});

describe("RequestList — selection", () => {
  it("clicking a request row calls onSelect with the segment id", async () => {
    const onSelect = vi.fn();
    render(
      <RequestList
        segments={[makeSegment({ id: "seg-xyz", preview: "Click me" })]}
        onSelect={onSelect}
      />
    );
    await userEvent.click(screen.getByText("Click me"));
    expect(onSelect).toHaveBeenCalledWith("seg-xyz");
  });
});

describe("RequestList — view full conversation", () => {
  it("renders 'Full' button when onViewConversation + conversation_id are present", () => {
    render(
      <RequestList
        segments={[
          makeSegment({ conversation_id: "c1aaaa" }),
          makeSegment({ conversation_id: "c2bbbb" }),
        ]}
        onSelect={() => {}}
        onViewConversation={() => {}}
      />
    );
    expect(screen.getAllByRole("button", { name: "Full" }).length).toBe(2);
  });

  it("'Full' button calls onViewConversation with conversation id and stops propagation", async () => {
    const onView = vi.fn();
    const onSelect = vi.fn();
    render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1xyz" }),
          makeSegment({ id: "b", conversation_id: "c2xyz" }),
        ]}
        onSelect={onSelect}
        onViewConversation={onView}
      />
    );
    await userEvent.click(screen.getAllByRole("button", { name: "Full" })[0]);
    expect(onView).toHaveBeenCalledWith("c1xyz");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("'Full' button is absent when onViewConversation is not provided", () => {
    render(
      <RequestList
        segments={[
          makeSegment({ conversation_id: "c1aaaa" }),
          makeSegment({ conversation_id: "c2bbbb" }),
        ]}
        onSelect={() => {}}
      />
    );
    expect(screen.queryByRole("button", { name: "Full" })).not.toBeInTheDocument();
  });
});

describe("RequestList — hide/restore segment", () => {
  it("hide segment button calls onHideSegment and stops propagation", async () => {
    const onHide = vi.fn();
    const onSelect = vi.fn();
    render(
      <RequestList
        segments={[makeSegment({ id: "segA" })]}
        onSelect={onSelect}
        onHideSegment={onHide}
      />
    );
    await userEvent.click(screen.getByTitle("Hide this request"));
    expect(onHide).toHaveBeenCalledWith("segA");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("hide button absent when onHideSegment not provided", () => {
    render(
      <RequestList
        segments={[makeSegment()]}
        onSelect={() => {}}
      />
    );
    expect(screen.queryByTitle("Hide this request")).not.toBeInTheDocument();
  });

  it("hidden segments show Restore instead of Hide", () => {
    render(
      <RequestList
        segments={[makeSegment({ hidden: true })]}
        onSelect={() => {}}
        onHideSegment={() => {}}
        onRestoreSegment={() => {}}
      />
    );
    expect(screen.queryByTitle("Hide this request")).not.toBeInTheDocument();
    expect(screen.getByTitle("Restore this request")).toBeInTheDocument();
  });

  it("restore button calls onRestoreSegment with segment id", async () => {
    const onRestore = vi.fn();
    render(
      <RequestList
        segments={[makeSegment({ id: "segB", hidden: true })]}
        onSelect={() => {}}
        onRestoreSegment={onRestore}
      />
    );
    await userEvent.click(screen.getByTitle("Restore this request"));
    expect(onRestore).toHaveBeenCalledWith("segB");
  });
});

describe("RequestList — hide/restore conversation", () => {
  it("hide conversation button present on multi-conv when callback provided and not fully hidden", () => {
    render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1" }),
          makeSegment({ id: "b", conversation_id: "c2" }),
        ]}
        onSelect={() => {}}
        onHideConversation={() => {}}
      />
    );
    expect(screen.getAllByTitle("Hide entire conversation").length).toBe(2);
  });

  it("hide conversation button calls onHideConversation with conversation id", async () => {
    const onHide = vi.fn();
    render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "cvX" }),
          makeSegment({ id: "b", conversation_id: "cvY" }),
        ]}
        onSelect={() => {}}
        onHideConversation={onHide}
      />
    );
    await userEvent.click(screen.getAllByTitle("Hide entire conversation")[0]);
    expect(onHide).toHaveBeenCalledWith("cvX");
  });

  it("restore conversation button visible when all segments are hidden", () => {
    render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "c1", hidden: true }),
          makeSegment({ id: "b", conversation_id: "c2", hidden: false }),
        ]}
        onSelect={() => {}}
        onRestoreConversation={() => {}}
      />
    );
    expect(screen.getAllByTitle("Restore conversation").length).toBe(1);
  });

  it("restore conversation button calls onRestoreConversation with conversation id", async () => {
    const onRestore = vi.fn();
    render(
      <RequestList
        segments={[
          makeSegment({ id: "a", conversation_id: "cvHidden", hidden: true }),
          makeSegment({ id: "b", conversation_id: "cvVisible", hidden: false }),
        ]}
        onSelect={() => {}}
        onRestoreConversation={onRestore}
      />
    );
    await userEvent.click(screen.getByTitle("Restore conversation"));
    expect(onRestore).toHaveBeenCalledWith("cvHidden");
  });
});

describe("RequestList — date range filtering", () => {
  const jan = makeSegment({
    id: "jan",
    timestamp: "2026-01-15T00:00:00Z",
    preview: "Jan msg",
  });
  const mar = makeSegment({
    id: "mar",
    timestamp: "2026-03-15T00:00:00Z",
    preview: "Mar msg",
  });
  const noTs = makeSegment({
    id: "no-ts",
    timestamp: null,
    preview: "No ts",
  });

  it("renders all segments when no date range is set", () => {
    render(<RequestList segments={[jan, mar]} onSelect={() => {}} />);
    expect(screen.getByText("Jan msg")).toBeInTheDocument();
    expect(screen.getByText("Mar msg")).toBeInTheDocument();
  });

  it("filters out segments before dateFrom", () => {
    render(
      <RequestList
        segments={[jan, mar]}
        onSelect={() => {}}
        dateFrom="2026-02-01"
      />
    );
    expect(screen.queryByText("Jan msg")).not.toBeInTheDocument();
    expect(screen.getByText("Mar msg")).toBeInTheDocument();
  });

  it("filters out segments after dateTo", () => {
    render(
      <RequestList
        segments={[jan, mar]}
        onSelect={() => {}}
        dateTo="2026-02-01"
      />
    );
    expect(screen.getByText("Jan msg")).toBeInTheDocument();
    expect(screen.queryByText("Mar msg")).not.toBeInTheDocument();
  });

  it("keeps segments with no timestamp when a date filter is set", () => {
    render(
      <RequestList
        segments={[jan, mar, noTs]}
        onSelect={() => {}}
        dateFrom="2026-03-01"
      />
    );
    expect(screen.getByText("No ts")).toBeInTheDocument();
  });
});
