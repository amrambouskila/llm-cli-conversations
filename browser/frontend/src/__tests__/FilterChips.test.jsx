import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FilterChips from "../components/FilterChips";

const filterOptions = {
  projects: ["conversations", "graphify", "ml-pipeline"],
  models: ["claude-opus-4-6", "claude-sonnet-4-6", "gpt-5"],
  tools: ["Bash", "Edit", "Read", "Grep"],
  topics: ["docker", "search", "embeddings"],
};

describe("FilterChips — autocomplete chips", () => {
  it("renders all 8 filter chips by default", () => {
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    for (const label of [
      "project",
      "model",
      "tool",
      "topic",
      "after",
      "before",
      "cost >",
      "turns >",
    ]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("clicking 'project' opens a dropdown with search input + all project names", async () => {
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "project" }));
    expect(screen.getByPlaceholderText("Filter project...")).toBeInTheDocument();
    expect(screen.getByText("conversations")).toBeInTheDocument();
    expect(screen.getByText("graphify")).toBeInTheDocument();
    expect(screen.getByText("ml-pipeline")).toBeInTheDocument();
  });

  it("typing in the dropdown filters the option list in real time", async () => {
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    await user.click(screen.getByRole("button", { name: "project" }));
    const input = screen.getByPlaceholderText("Filter project...");
    await user.type(input, "graph");
    expect(screen.getByText("graphify")).toBeInTheDocument();
    expect(screen.queryByText("conversations")).not.toBeInTheDocument();
    expect(screen.queryByText("ml-pipeline")).not.toBeInTheDocument();
  });

  it("filter is case-insensitive", async () => {
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    await user.click(screen.getByRole("button", { name: "project" }));
    await user.type(screen.getByPlaceholderText("Filter project..."), "GRAPH");
    expect(screen.getByText("graphify")).toBeInTheDocument();
  });

  it("shows 'No matches' when filter text matches nothing", async () => {
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    await user.click(screen.getByRole("button", { name: "project" }));
    await user.type(screen.getByPlaceholderText("Filter project..."), "xyzzy");
    expect(screen.getByText("No matches")).toBeInTheDocument();
  });

  it("clicking a project option appends 'project:<name>' to an empty query", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={onChange}
      />
    );
    await user.click(screen.getByRole("button", { name: "project" }));
    await user.click(screen.getByText("graphify"));
    expect(onChange).toHaveBeenCalledWith("project:graphify");
  });

  it("clicking an option separates from existing query with a space", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="docker"
        onQueryChange={onChange}
      />
    );
    await user.click(screen.getByRole("button", { name: "project" }));
    await user.click(screen.getByText("graphify"));
    expect(onChange).toHaveBeenCalledWith("docker project:graphify");
  });

  it("model chip opens dropdown with model names", async () => {
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    await user.click(screen.getByRole("button", { name: "model" }));
    expect(screen.getByText("claude-opus-4-6")).toBeInTheDocument();
  });

  it("tool chip opens dropdown with tool names", async () => {
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    await user.click(screen.getByRole("button", { name: "tool" }));
    expect(screen.getByText("Bash")).toBeInTheDocument();
  });

  it("topic chip opens dropdown with topic strings", async () => {
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    await user.click(screen.getByRole("button", { name: "topic" }));
    expect(screen.getByText("docker")).toBeInTheDocument();
  });
});

describe("FilterChips — non-autocomplete chips", () => {
  it("clicking 'after' appends 'after:' to empty query", async () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={onChange}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "after" }));
    expect(onChange).toHaveBeenCalledWith("after:");
  });

  it("clicking 'before' appends 'before:'", async () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={onChange}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "before" }));
    expect(onChange).toHaveBeenCalledWith("before:");
  });

  it("clicking 'cost >' appends 'cost:>'", async () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={onChange}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "cost >" }));
    expect(onChange).toHaveBeenCalledWith("cost:>");
  });

  it("clicking 'turns >' appends 'turns:>'", async () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={onChange}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "turns >" }));
    expect(onChange).toHaveBeenCalledWith("turns:>");
  });

  it("non-autocomplete prefix is space-separated from existing query", async () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="docker"
        onQueryChange={onChange}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "after" }));
    expect(onChange).toHaveBeenCalledWith("docker after:");
  });
});

describe("FilterChips — active filter tags", () => {
  it("renders one tag for one parsed filter", () => {
    const { container } = render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="project:conversations"
        onQueryChange={() => {}}
      />
    );
    const tags = container.querySelectorAll(".active-filter-tag");
    expect(tags.length).toBe(1);
    expect(tags[0]).toHaveTextContent("project: conversations");
  });

  it("renders multiple tags for multiple parsed filters", () => {
    const { container } = render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="project:conversations tool:Bash"
        onQueryChange={() => {}}
      />
    );
    const tags = container.querySelectorAll(".active-filter-tag");
    expect(tags.length).toBe(2);
    expect(tags[0]).toHaveTextContent("project: conversations");
    expect(tags[1]).toHaveTextContent("tool: Bash");
  });

  it("renders cost tag with '>' prefixed value", () => {
    const { container } = render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="cost:>2.00"
        onQueryChange={() => {}}
      />
    );
    expect(container.querySelector(".active-filter-tag")).toHaveTextContent(
      "cost: >2.00"
    );
  });

  it("renders turns tag with '>' prefixed value", () => {
    const { container } = render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="turns:>10"
        onQueryChange={() => {}}
      />
    );
    expect(container.querySelector(".active-filter-tag")).toHaveTextContent(
      "turns: >10"
    );
  });

  it("clicking the X on a tag removes that filter", async () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="project:conversations"
        onQueryChange={onChange}
      />
    );
    const tag = document.querySelector(".active-filter-tag");
    const removeBtn = within(tag).getByRole("button");
    await userEvent.click(removeBtn);
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("removes only the targeted filter when multiple exist", async () => {
    const onChange = vi.fn();
    const { container } = render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="project:conversations tool:Bash"
        onQueryChange={onChange}
      />
    );
    const tags = container.querySelectorAll(".active-filter-tag");
    const projectRemoveBtn = within(tags[0]).getByRole("button");
    await userEvent.click(projectRemoveBtn);
    expect(onChange).toHaveBeenCalledWith("tool:Bash");
  });

  it("removing a cost filter clears it", async () => {
    const onChange = vi.fn();
    const { container } = render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="cost:>2.00"
        onQueryChange={onChange}
      />
    );
    const tag = container.querySelector(".active-filter-tag");
    await userEvent.click(within(tag).getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("removing a turns filter clears it", async () => {
    const onChange = vi.fn();
    const { container } = render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="turns:>10"
        onQueryChange={onChange}
      />
    );
    const tag = container.querySelector(".active-filter-tag");
    await userEvent.click(within(tag).getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("hides active-filters section when query is empty (manual clear)", () => {
    const { container } = render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    expect(container.querySelector(".active-filters")).toBeNull();
  });

  it("hides active-filters section when query is only free text", () => {
    const { container } = render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery="docker"
        onQueryChange={() => {}}
      />
    );
    expect(container.querySelector(".active-filters")).toBeNull();
  });
});

describe("FilterChips — dropdown dismissal", () => {
  it("clicking outside the chips container closes the dropdown", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <FilterChips
          filterOptions={filterOptions}
          searchQuery=""
          onQueryChange={() => {}}
        />
        <div data-testid="outside">outside</div>
      </div>
    );
    await user.click(screen.getByRole("button", { name: "project" }));
    expect(
      screen.getByPlaceholderText("Filter project...")
    ).toBeInTheDocument();
    await user.click(screen.getByTestId("outside"));
    expect(
      screen.queryByPlaceholderText("Filter project...")
    ).not.toBeInTheDocument();
  });

  it("clicking the same chip again toggles its dropdown closed", async () => {
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    const projectBtn = screen.getByRole("button", { name: "project" });
    await user.click(projectBtn);
    expect(
      screen.getByPlaceholderText("Filter project...")
    ).toBeInTheDocument();
    await user.click(projectBtn);
    expect(
      screen.queryByPlaceholderText("Filter project...")
    ).not.toBeInTheDocument();
  });

  it("clicking a different chip switches the open dropdown", async () => {
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    await user.click(screen.getByRole("button", { name: "project" }));
    expect(
      screen.getByPlaceholderText("Filter project...")
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "model" }));
    expect(
      screen.queryByPlaceholderText("Filter project...")
    ).not.toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("Filter model...")
    ).toBeInTheDocument();
  });

  it("selecting an option closes the dropdown", async () => {
    const user = userEvent.setup();
    render(
      <FilterChips
        filterOptions={filterOptions}
        searchQuery=""
        onQueryChange={() => {}}
      />
    );
    await user.click(screen.getByRole("button", { name: "project" }));
    await user.click(screen.getByText("graphify"));
    expect(
      screen.queryByPlaceholderText("Filter project...")
    ).not.toBeInTheDocument();
  });
});

describe("FilterChips — graceful behavior with no filterOptions", () => {
  it("with null filterOptions, autocomplete chip falls back to prefix insertion", async () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        filterOptions={null}
        searchQuery=""
        onQueryChange={onChange}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "project" }));
    expect(onChange).toHaveBeenCalledWith("project:");
  });

  it("with empty options array, autocomplete chip falls back to prefix insertion", async () => {
    const onChange = vi.fn();
    render(
      <FilterChips
        filterOptions={{ projects: [] }}
        searchQuery=""
        onQueryChange={onChange}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "project" }));
    expect(onChange).toHaveBeenCalledWith("project:");
  });
});
