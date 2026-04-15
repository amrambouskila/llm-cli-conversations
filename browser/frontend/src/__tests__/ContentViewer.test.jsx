import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../components/SummaryPanel", () => ({
  default: function MockSummaryPanel({ summaryKey, onRequest, onPoll, onTitleReady }) {
    return (
      <div data-testid="summary-panel">
        <span data-testid="summary-key">{summaryKey || ""}</span>
        <span data-testid="summary-has-request">{onRequest ? "yes" : "no"}</span>
        <span data-testid="summary-has-poll">{onPoll ? "yes" : "no"}</span>
        <button
          data-testid="summary-call-request"
          onClick={() => onRequest && onRequest()}
        >
          call-request
        </button>
        <button
          data-testid="summary-call-poll"
          onClick={() => onPoll && onPoll()}
        >
          call-poll
        </button>
        <button
          data-testid="summary-title-ready"
          onClick={() =>
            onTitleReady && onTitleReady(summaryKey, "Generated Title")
          }
        >
          title-ready
        </button>
      </div>
    );
  },
}));

vi.mock("../api", () => ({
  requestSummary: vi.fn(() => Promise.resolve({ status: "pending" })),
  getSummary: vi.fn(() => Promise.resolve({ status: "pending" })),
  requestConvSummary: vi.fn(() => Promise.resolve({ status: "pending" })),
  getConvSummary: vi.fn(() => Promise.resolve({ status: "pending" })),
}));

import ContentViewer from "../components/ContentViewer";
import {
  requestSummary,
  getSummary,
  requestConvSummary,
  getConvSummary,
} from "../api";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ContentViewer — empty state", () => {
  it("renders an empty-state message when markdown is falsy", () => {
    render(<ContentViewer markdown={null} />);
    expect(
      screen.getByText("Select a request to view its content")
    ).toBeInTheDocument();
  });

  it("does not render the toolbar or SummaryPanel in empty state", () => {
    const { container } = render(<ContentViewer markdown={null} />);
    expect(container.querySelector(".content-toolbar")).toBeNull();
    expect(screen.queryByTestId("summary-panel")).not.toBeInTheDocument();
  });
});

describe("ContentViewer — markdown rendering", () => {
  it("renders rendered HTML when markdown is provided", () => {
    const { container } = render(
      <ContentViewer markdown="# Hello" segmentId="s1" />
    );
    expect(container.querySelector("h1")).not.toBeNull();
    expect(container.querySelector("h1").textContent).toBe("Hello");
  });

  it("highlights search query matches in the rendered markdown", () => {
    const { container } = render(
      <ContentViewer markdown="the docker auth issue" searchQuery="docker" segmentId="s1" />
    );
    expect(container.querySelector("mark")).not.toBeNull();
    expect(container.querySelector("mark").textContent).toBe("docker");
  });

  it("does NOT highlight when searchQuery is empty", () => {
    const { container } = render(
      <ContentViewer markdown="no highlights here" searchQuery="" segmentId="s1" />
    );
    expect(container.querySelector("mark")).toBeNull();
  });
});

describe("ContentViewer — toolbar", () => {
  it("renders toolbar when sourceFile is provided (no onExport)", () => {
    const { container } = render(
      <ContentViewer
        markdown="body"
        sourceFile="/some/path/to/file.md"
        segmentId="s1"
      />
    );
    expect(container.querySelector(".content-toolbar")).not.toBeNull();
  });

  it("renders only the filename (basename) in the toolbar", () => {
    render(
      <ContentViewer
        markdown="body"
        sourceFile="/deep/nested/file-name.md"
        segmentId="s1"
      />
    );
    expect(screen.getByText("file-name.md")).toBeInTheDocument();
  });

  it("sets full path as the title attribute on the filename span", () => {
    const { container } = render(
      <ContentViewer
        markdown="body"
        sourceFile="/deep/nested/file-name.md"
        segmentId="s1"
      />
    );
    const span = container.querySelector(".toolbar-file");
    expect(span.getAttribute("title")).toBe("/deep/nested/file-name.md");
  });

  it("renders Copy + Download buttons when onExport is provided", () => {
    render(
      <ContentViewer markdown="body" onExport={() => {}} segmentId="s1" />
    );
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Download" })
    ).toBeInTheDocument();
  });

  it("Copy button calls onExport('copy')", async () => {
    const onExport = vi.fn();
    render(
      <ContentViewer markdown="body" onExport={onExport} segmentId="s1" />
    );
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(onExport).toHaveBeenCalledWith("copy");
  });

  it("Download button calls onExport('download')", async () => {
    const onExport = vi.fn();
    render(
      <ContentViewer markdown="body" onExport={onExport} segmentId="s1" />
    );
    await userEvent.click(screen.getByRole("button", { name: "Download" }));
    expect(onExport).toHaveBeenCalledWith("download");
  });

  it("does not render toolbar when neither onExport nor sourceFile is provided", () => {
    const { container } = render(
      <ContentViewer markdown="body" segmentId="s1" />
    );
    expect(container.querySelector(".content-toolbar")).toBeNull();
  });
});

describe("ContentViewer — summary key derivation", () => {
  it("uses segmentId as the summary key when segmentId is present", () => {
    render(<ContentViewer markdown="x" segmentId="seg-abc" />);
    expect(screen.getByTestId("summary-key").textContent).toBe("seg-abc");
  });

  it("uses 'conv_<project>_<convId>' when only conversationId + projectName are set", () => {
    render(
      <ContentViewer
        markdown="x"
        conversationId="conv1"
        projectName="alpha"
      />
    );
    expect(screen.getByTestId("summary-key").textContent).toBe(
      "conv_alpha_conv1"
    );
  });

  it("prefers segmentId over conversationId when both are present", () => {
    render(
      <ContentViewer
        markdown="x"
        segmentId="seg-z"
        conversationId="conv1"
        projectName="alpha"
      />
    );
    expect(screen.getByTestId("summary-key").textContent).toBe("seg-z");
  });

  it("passes a null summary key when neither segment nor conversation is set", () => {
    render(<ContentViewer markdown="x" />);
    expect(screen.getByTestId("summary-key").textContent).toBe("");
  });

  it("does not wire onRequest/onPoll callbacks when summary key is null", () => {
    render(<ContentViewer markdown="x" />);
    expect(screen.getByTestId("summary-has-request").textContent).toBe("no");
    expect(screen.getByTestId("summary-has-poll").textContent).toBe("no");
  });

  it("wires onRequest/onPoll callbacks when summary key is present", () => {
    render(<ContentViewer markdown="x" segmentId="s1" />);
    expect(screen.getByTestId("summary-has-request").textContent).toBe("yes");
    expect(screen.getByTestId("summary-has-poll").textContent).toBe("yes");
  });
});

describe("ContentViewer — API routing", () => {
  it("segment-mode onRequest routes to requestSummary", async () => {
    render(<ContentViewer markdown="x" segmentId="seg1" provider="claude" />);
    await userEvent.click(screen.getByTestId("summary-call-request"));
    expect(requestSummary).toHaveBeenCalledWith("seg1", "claude");
    expect(requestConvSummary).not.toHaveBeenCalled();
  });

  it("segment-mode onPoll routes to getSummary", async () => {
    render(<ContentViewer markdown="x" segmentId="seg1" />);
    await userEvent.click(screen.getByTestId("summary-call-poll"));
    expect(getSummary).toHaveBeenCalledWith("seg1");
    expect(getConvSummary).not.toHaveBeenCalled();
  });

  it("conversation-mode onRequest routes to requestConvSummary", async () => {
    render(
      <ContentViewer
        markdown="x"
        conversationId="cv1"
        projectName="proj"
        provider="claude"
      />
    );
    await userEvent.click(screen.getByTestId("summary-call-request"));
    expect(requestConvSummary).toHaveBeenCalledWith("proj", "cv1", "claude");
    expect(requestSummary).not.toHaveBeenCalled();
  });

  it("conversation-mode onPoll routes to getConvSummary", async () => {
    render(
      <ContentViewer
        markdown="x"
        conversationId="cv1"
        projectName="proj"
      />
    );
    await userEvent.click(screen.getByTestId("summary-call-poll"));
    expect(getConvSummary).toHaveBeenCalledWith("proj", "cv1");
    expect(getSummary).not.toHaveBeenCalled();
  });
});

describe("ContentViewer — onTitleReady passthrough", () => {
  it("forwards onTitleReady calls from SummaryPanel", async () => {
    const onTitleReady = vi.fn();
    render(
      <ContentViewer
        markdown="x"
        segmentId="seg-t"
        onTitleReady={onTitleReady}
      />
    );
    await userEvent.click(screen.getByTestId("summary-title-ready"));
    expect(onTitleReady).toHaveBeenCalledWith("seg-t", "Generated Title");
  });
});
