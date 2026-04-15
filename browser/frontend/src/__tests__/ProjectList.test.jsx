import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProjectList from "../components/ProjectList";

function makeProject(overrides = {}) {
  return {
    name: "alpha",
    display_name: "alpha",
    total_requests: 5,
    hidden: false,
    stats: {
      total_words: 1000,
      total_conversations: 3,
      estimated_tokens: 250,
      total_tool_calls: 7,
      first_timestamp: "2026-01-01T00:00:00Z",
      last_timestamp: "2026-01-31T00:00:00Z",
      request_sizes: [100, 200, 300, 400, 500],
      conversation_timeline: ["2026-01-01T00:00:00Z", "2026-01-31T00:00:00Z"],
      tool_breakdown: { Bash: 3, Edit: 2 },
    },
    ...overrides,
  };
}

describe("ProjectList — empty state", () => {
  it("renders 'No projects found' when the list is empty", () => {
    render(<ProjectList projects={[]} onSelect={() => {}} />);
    expect(screen.getByText("No projects found")).toBeInTheDocument();
  });

  it("renders 'No projects found' when all projects are filtered out by date range", () => {
    const projects = [makeProject()];
    render(
      <ProjectList
        projects={projects}
        onSelect={() => {}}
        dateFrom="2027-01-01"
      />
    );
    expect(screen.getByText("No projects found")).toBeInTheDocument();
  });

  it("tolerates projects with missing stats.total_words (|| 0 fallback)", () => {
    const projects = [
      {
        name: "no-stats",
        display_name: "No Stats",
        total_requests: 3,
        hidden: false,
        stats: undefined,
      },
      makeProject({ name: "with", display_name: "With", total_requests: 2 }),
    ];
    render(<ProjectList projects={projects} onSelect={() => {}} />);
    // Both projects render without crashing — line 39 `|| 0` branch hit for the
    // stats-less project.
    expect(screen.getByText("No Stats")).toBeInTheDocument();
    expect(screen.getByText("With")).toBeInTheDocument();
  });
});

describe("ProjectList — rendering", () => {
  it("renders one entry per project with display name and request count", () => {
    const projects = [
      makeProject({ name: "a", display_name: "Alpha", total_requests: 5 }),
      makeProject({ name: "b", display_name: "Beta", total_requests: 2 }),
    ];
    render(<ProjectList projects={projects} onSelect={() => {}} />);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText(/5 requests/)).toBeInTheDocument();
    expect(screen.getByText(/2 requests/)).toBeInTheDocument();
  });

  it("adds 'selected' class to the item that matches the selected prop", () => {
    const { container } = render(
      <ProjectList
        projects={[makeProject({ name: "a" }), makeProject({ name: "b" })]}
        selected="a"
        onSelect={() => {}}
      />
    );
    const items = container.querySelectorAll(".project-item");
    expect(items[0].className).toContain("selected");
    expect(items[1].className).not.toContain("selected");
  });

  it("renders 'hidden' badge and 'project-hidden' class on hidden projects", () => {
    const { container } = render(
      <ProjectList
        projects={[makeProject({ hidden: true })]}
        onSelect={() => {}}
        onRestoreProject={() => {}}
      />
    );
    expect(screen.getByText("hidden")).toBeInTheDocument();
    expect(container.querySelector(".project-hidden")).not.toBeNull();
  });
});

describe("ProjectList — selection", () => {
  it("calls onSelect with the project name when a row is clicked", async () => {
    const onSelect = vi.fn();
    render(
      <ProjectList
        projects={[makeProject({ name: "alpha", display_name: "Alpha" })]}
        onSelect={onSelect}
      />
    );
    await userEvent.click(screen.getByText("Alpha"));
    expect(onSelect).toHaveBeenCalledWith("alpha");
  });
});

describe("ProjectList — expand/collapse stats", () => {
  it("expands stats panel when the toggle is clicked", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <ProjectList projects={[makeProject()]} onSelect={() => {}} />
    );
    expect(container.querySelector(".project-stats")).toBeNull();
    await user.click(container.querySelector(".stats-toggle"));
    expect(container.querySelector(".project-stats")).not.toBeNull();
    expect(screen.getByText("Conversations")).toBeInTheDocument();
    expect(screen.getByText("Words")).toBeInTheDocument();
    expect(screen.getByText("Est. Tokens")).toBeInTheDocument();
    expect(screen.getByText("Tool Calls")).toBeInTheDocument();
  });

  it("collapses the stats panel on second click", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <ProjectList projects={[makeProject()]} onSelect={() => {}} />
    );
    const toggle = container.querySelector(".stats-toggle");
    await user.click(toggle);
    expect(container.querySelector(".project-stats")).not.toBeNull();
    await user.click(toggle);
    expect(container.querySelector(".project-stats")).toBeNull();
  });

  it("stats toggle does NOT trigger onSelect (click propagation stopped)", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    const { container } = render(
      <ProjectList projects={[makeProject()]} onSelect={onSelect} />
    );
    await user.click(container.querySelector(".stats-toggle"));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("renders first/last timestamps in the expanded panel when present", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <ProjectList projects={[makeProject()]} onSelect={() => {}} />
    );
    await user.click(container.querySelector(".stats-toggle"));
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Last")).toBeInTheDocument();
  });

  it("omits timestamp rows when first/last timestamps are missing", async () => {
    const user = userEvent.setup();
    const project = makeProject();
    project.stats.first_timestamp = null;
    project.stats.last_timestamp = null;
    const { container } = render(
      <ProjectList projects={[project]} onSelect={() => {}} />
    );
    await user.click(container.querySelector(".stats-toggle"));
    expect(screen.queryByText("First")).not.toBeInTheDocument();
    expect(screen.queryByText("Last")).not.toBeInTheDocument();
  });
});

describe("ProjectList — hide/restore", () => {
  it("hide button calls onHideProject with the project name", async () => {
    const onHide = vi.fn();
    render(
      <ProjectList
        projects={[makeProject({ name: "alpha", hidden: false })]}
        onSelect={() => {}}
        onHideProject={onHide}
      />
    );
    await userEvent.click(
      screen.getByTitle("Hide this project")
    );
    expect(onHide).toHaveBeenCalledWith("alpha");
  });

  it("hide button is absent when onHideProject is not provided", () => {
    render(
      <ProjectList
        projects={[makeProject({ name: "alpha", hidden: false })]}
        onSelect={() => {}}
      />
    );
    expect(
      screen.queryByTitle("Hide this project")
    ).not.toBeInTheDocument();
  });

  it("restore button calls onRestoreProject with the project name", async () => {
    const onRestore = vi.fn();
    render(
      <ProjectList
        projects={[makeProject({ name: "alpha", hidden: true })]}
        onSelect={() => {}}
        onRestoreProject={onRestore}
      />
    );
    await userEvent.click(
      screen.getByTitle("Restore this project")
    );
    expect(onRestore).toHaveBeenCalledWith("alpha");
  });

  it("restore button is absent when onRestoreProject is not provided", () => {
    render(
      <ProjectList
        projects={[makeProject({ name: "alpha", hidden: true })]}
        onSelect={() => {}}
      />
    );
    expect(
      screen.queryByTitle("Restore this project")
    ).not.toBeInTheDocument();
  });

  it("hidden projects do NOT show a hide button", () => {
    render(
      <ProjectList
        projects={[makeProject({ name: "alpha", hidden: true })]}
        onSelect={() => {}}
        onHideProject={() => {}}
        onRestoreProject={() => {}}
      />
    );
    expect(
      screen.queryByTitle("Hide this project")
    ).not.toBeInTheDocument();
  });

  it("visible projects do NOT show a restore button", () => {
    render(
      <ProjectList
        projects={[makeProject({ name: "alpha", hidden: false })]}
        onSelect={() => {}}
        onHideProject={() => {}}
        onRestoreProject={() => {}}
      />
    );
    expect(
      screen.queryByTitle("Restore this project")
    ).not.toBeInTheDocument();
  });

  it("clicking hide does NOT trigger onSelect (propagation stopped)", async () => {
    const onSelect = vi.fn();
    render(
      <ProjectList
        projects={[makeProject({ name: "alpha", hidden: false })]}
        onSelect={onSelect}
        onHideProject={() => {}}
      />
    );
    await userEvent.click(
      screen.getByTitle("Hide this project")
    );
    expect(onSelect).not.toHaveBeenCalled();
  });
});

describe("ProjectList — date range filtering", () => {
  const base = makeProject();
  const jan = {
    ...base,
    name: "jan",
    display_name: "Jan project",
    stats: {
      ...base.stats,
      first_timestamp: "2026-01-01T00:00:00Z",
      last_timestamp: "2026-01-31T00:00:00Z",
    },
  };
  const mar = {
    ...base,
    name: "mar",
    display_name: "Mar project",
    stats: {
      ...base.stats,
      first_timestamp: "2026-03-01T00:00:00Z",
      last_timestamp: "2026-03-31T00:00:00Z",
    },
  };
  const empty = {
    ...base,
    name: "empty",
    display_name: "Empty project",
    stats: { ...base.stats, first_timestamp: null, last_timestamp: null },
  };

  it("returns all projects when no date range is set", () => {
    render(
      <ProjectList projects={[jan, mar]} onSelect={() => {}} />
    );
    expect(screen.getByText("Jan project")).toBeInTheDocument();
    expect(screen.getByText("Mar project")).toBeInTheDocument();
  });

  it("excludes a project whose last_timestamp is before dateFrom", () => {
    render(
      <ProjectList
        projects={[jan, mar]}
        onSelect={() => {}}
        dateFrom="2026-02-15"
      />
    );
    expect(screen.queryByText("Jan project")).not.toBeInTheDocument();
    expect(screen.getByText("Mar project")).toBeInTheDocument();
  });

  it("excludes a project whose first_timestamp is after dateTo", () => {
    render(
      <ProjectList
        projects={[jan, mar]}
        onSelect={() => {}}
        dateTo="2026-02-15"
      />
    );
    expect(screen.getByText("Jan project")).toBeInTheDocument();
    expect(screen.queryByText("Mar project")).not.toBeInTheDocument();
  });

  it("includes a project whose range straddles the filter range", () => {
    render(
      <ProjectList
        projects={[jan]}
        onSelect={() => {}}
        dateFrom="2026-01-15"
        dateTo="2026-01-20"
      />
    );
    expect(screen.getByText("Jan project")).toBeInTheDocument();
  });

  it("excludes projects with no timestamps at all when a date filter is set", () => {
    render(
      <ProjectList
        projects={[jan, empty]}
        onSelect={() => {}}
        dateFrom="2026-01-01"
      />
    );
    expect(screen.getByText("Jan project")).toBeInTheDocument();
    expect(screen.queryByText("Empty project")).not.toBeInTheDocument();
  });
});

describe("ProjectList — size bar", () => {
  it("renders a size bar track for each project with stats", () => {
    const { container } = render(
      <ProjectList projects={[makeProject()]} onSelect={() => {}} />
    );
    expect(container.querySelector(".project-size-bar-track")).not.toBeNull();
  });

  it("scales size bars relative to the largest project", () => {
    const large = makeProject({ name: "large", display_name: "Large" });
    large.stats = { ...large.stats, total_words: 100 };
    const small = makeProject({ name: "small", display_name: "Small" });
    small.stats = { ...small.stats, total_words: 25 };
    const { container } = render(
      <ProjectList projects={[large, small]} onSelect={() => {}} />
    );
    const fills = container.querySelectorAll(".project-size-bar-fill");
    const items = container.querySelectorAll(".project-item");
    const largeFill = within(items[0]).getByRole
      ? items[0].querySelector(".project-size-bar-fill")
      : fills[0];
    const smallFill = items[1].querySelector(".project-size-bar-fill");
    expect(largeFill.style.width).toBe("100%");
    expect(smallFill.style.width).toBe("25%");
  });
});
