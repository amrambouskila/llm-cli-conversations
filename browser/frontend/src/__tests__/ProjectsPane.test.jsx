import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectsPane from "../components/ProjectsPane";

function makeProject(name = "alpha") {
  return {
    name,
    display_name: name,
    total_requests: 5,
    hidden: false,
    stats: {
      total_words: 100,
      total_conversations: 1,
      estimated_tokens: 25,
      total_tool_calls: 0,
      first_timestamp: "2026-01-01T00:00:00Z",
      last_timestamp: "2026-01-31T00:00:00Z",
      request_sizes: [10, 20],
      conversation_timeline: ["2026-01-01T00:00:00Z"],
      tool_breakdown: {},
    },
  };
}

function defaultProps(overrides = {}) {
  return {
    width: 220,
    projects: [makeProject("alpha"), makeProject("beta")],
    selectedProject: null,
    onSelectProject: vi.fn(),
    onDeselectProject: vi.fn(),
    onHideProject: vi.fn(),
    onRestoreProject: vi.fn(),
    showHidden: false,
    dateFrom: "",
    dateTo: "",
    ...overrides,
  };
}

describe("ProjectsPane", () => {
  it("renders the 'Projects' header", () => {
    render(<ProjectsPane {...defaultProps()} />);
    expect(screen.getByText("Projects")).toBeInTheDocument();
  });

  it("applies the width style", () => {
    const { container } = render(
      <ProjectsPane {...defaultProps({ width: 300 })} />
    );
    expect(container.querySelector(".pane-projects").style.width).toBe("300px");
  });

  it("appends arrow when a project is selected", () => {
    render(<ProjectsPane {...defaultProps({ selectedProject: "alpha" })} />);
    expect(screen.getByText(/Projects/).textContent).toContain("\u2190");
  });

  it("clicking the header deselects when a project is selected", async () => {
    const onDeselect = vi.fn();
    render(
      <ProjectsPane
        {...defaultProps({
          selectedProject: "alpha",
          onDeselectProject: onDeselect,
        })}
      />
    );
    await userEvent.click(screen.getByText(/Projects/));
    expect(onDeselect).toHaveBeenCalled();
  });

  it("clicking the header is a no-op when no project is selected", async () => {
    const onDeselect = vi.fn();
    render(
      <ProjectsPane {...defaultProps({ onDeselectProject: onDeselect })} />
    );
    await userEvent.click(screen.getByText("Projects"));
    expect(onDeselect).not.toHaveBeenCalled();
  });

  it("renders the inner ProjectList items", () => {
    render(<ProjectsPane {...defaultProps()} />);
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
  });

  it("forwards onSelectProject to ProjectList rows", async () => {
    const onSelect = vi.fn();
    render(<ProjectsPane {...defaultProps({ onSelectProject: onSelect })} />);
    await userEvent.click(screen.getByText("alpha"));
    expect(onSelect).toHaveBeenCalledWith("alpha");
  });
});
