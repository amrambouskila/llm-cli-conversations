import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("../components/SummaryPanel", () => ({
  default: () => <div data-testid="summary-panel-stub" />,
}));

vi.mock("../api", () => ({
  requestSummary: vi.fn(),
  getSummary: vi.fn(),
  requestConvSummary: vi.fn(),
  getConvSummary: vi.fn(),
}));

import ContentPane from "../components/ContentPane";

describe("ContentPane", () => {
  it("renders an empty state when markdown is null", () => {
    const { container } = render(<ContentPane markdown={null} />);
    expect(container.querySelector(".pane-content-area")).not.toBeNull();
    expect(
      screen.getByText("Select a request to view its content")
    ).toBeInTheDocument();
  });

  it("renders the rendered markdown when provided", () => {
    const { container } = render(<ContentPane markdown="# Title" />);
    expect(container.querySelector("h1")).not.toBeNull();
    expect(container.querySelector("h1").textContent).toBe("Title");
  });

  it("forwards searchQuery for highlighting", () => {
    const { container } = render(
      <ContentPane markdown="docker setup" searchQuery="docker" />
    );
    expect(container.querySelector("mark")).not.toBeNull();
  });

  it("forwards onExport — Copy/Download buttons appear", () => {
    render(<ContentPane markdown="x" onExport={() => {}} />);
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Download" })
    ).toBeInTheDocument();
  });

  it("renders a SummaryPanel stub", () => {
    render(<ContentPane markdown="x" segmentId="s1" />);
    expect(screen.getByTestId("summary-panel-stub")).toBeInTheDocument();
  });

  it("source file basename appears in the toolbar", () => {
    render(
      <ContentPane
        markdown="x"
        sourceFile="/some/path/file.md"
        onExport={() => {}}
      />
    );
    expect(screen.getByText("file.md")).toBeInTheDocument();
  });
});
