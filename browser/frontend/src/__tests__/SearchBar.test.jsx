import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import SearchBar from "../components/SearchBar";

function Wrapper(props) {
  const ref = useRef(null);
  return <SearchBar searchRef={ref} {...props} />;
}

function defaultProps(overrides = {}) {
  return {
    searchQuery: "",
    onQueryChange: vi.fn(),
    searchMode: null,
    showDateFilter: false,
    onToggleDateFilter: vi.fn(),
    ...overrides,
  };
}

describe("SearchBar — input", () => {
  it("renders the search input with placeholder", () => {
    render(<Wrapper {...defaultProps()} />);
    expect(
      screen.getByPlaceholderText(/Search conversations/)
    ).toBeInTheDocument();
  });

  it("input value reflects searchQuery prop", () => {
    render(<Wrapper {...defaultProps({ searchQuery: "docker" })} />);
    expect(screen.getByDisplayValue("docker")).toBeInTheDocument();
  });

  it("typing fires onQueryChange with the new value", async () => {
    const onChange = vi.fn();
    render(<Wrapper {...defaultProps({ onQueryChange: onChange })} />);
    await userEvent.type(
      screen.getByPlaceholderText(/Search conversations/),
      "x"
    );
    expect(onChange).toHaveBeenCalledWith("x");
  });
});

describe("SearchBar — filter toggle button", () => {
  it("shows 'Filters' when showDateFilter is false", () => {
    render(<Wrapper {...defaultProps({ showDateFilter: false })} />);
    expect(
      screen.getByRole("button", { name: "Filters" })
    ).toBeInTheDocument();
  });

  it("shows 'Hide Filters' when showDateFilter is true", () => {
    render(<Wrapper {...defaultProps({ showDateFilter: true })} />);
    expect(
      screen.getByRole("button", { name: "Hide Filters" })
    ).toBeInTheDocument();
  });

  it("clicking the button fires onToggleDateFilter", async () => {
    const onToggle = vi.fn();
    render(<Wrapper {...defaultProps({ onToggleDateFilter: onToggle })} />);
    await userEvent.click(screen.getByRole("button", { name: "Filters" }));
    expect(onToggle).toHaveBeenCalled();
  });
});

describe("SearchBar — search mode badges", () => {
  it("omits badges when searchMode is null", () => {
    const { container } = render(<Wrapper {...defaultProps()} />);
    expect(container.querySelector(".search-mode-badges")).toBeNull();
  });

  it("omits badges when searchMode.mode is 'unavailable'", () => {
    const { container } = render(
      <Wrapper
        {...defaultProps({ searchMode: { mode: "unavailable", has_graph: false } })}
      />
    );
    expect(container.querySelector(".search-mode-badges")).toBeNull();
  });

  it("renders 'Hybrid' badge when mode is hybrid", () => {
    render(
      <Wrapper
        {...defaultProps({
          searchMode: {
            mode: "hybrid",
            embedded_sessions: 10,
            total_sessions: 10,
            has_graph: true,
            concept_count: 50,
          },
        })}
      />
    );
    expect(screen.getByText("Hybrid")).toBeInTheDocument();
  });

  it("renders 'Keyword' badge when mode is keyword", () => {
    render(
      <Wrapper
        {...defaultProps({
          searchMode: {
            mode: "keyword",
            embedded_sessions: 0,
            total_sessions: 10,
            has_graph: false,
          },
        })}
      />
    );
    expect(screen.getByText("Keyword")).toBeInTheDocument();
  });

  it("renders 'Embedding NN%' badge when mode is embedding", () => {
    render(
      <Wrapper
        {...defaultProps({
          searchMode: {
            mode: "embedding",
            embedded_sessions: 25,
            total_sessions: 100,
            has_graph: false,
          },
        })}
      />
    );
    expect(screen.getByText("Embedding 25%")).toBeInTheDocument();
  });

  it("renders 'Graph' badge when has_graph is true", () => {
    render(
      <Wrapper
        {...defaultProps({
          searchMode: {
            mode: "hybrid",
            embedded_sessions: 5,
            total_sessions: 5,
            has_graph: true,
            concept_count: 20,
          },
        })}
      />
    );
    expect(screen.getByText("Graph")).toBeInTheDocument();
  });

  it("renders 'No Graph' badge when has_graph is false", () => {
    render(
      <Wrapper
        {...defaultProps({
          searchMode: {
            mode: "keyword",
            embedded_sessions: 0,
            total_sessions: 5,
            has_graph: false,
          },
        })}
      />
    );
    expect(screen.getByText("No Graph")).toBeInTheDocument();
  });

  it("hybrid badge tooltip mentions sessions embedded ratio", () => {
    render(
      <Wrapper
        {...defaultProps({
          searchMode: {
            mode: "hybrid",
            embedded_sessions: 8,
            total_sessions: 10,
            has_graph: true,
            concept_count: 30,
          },
        })}
      />
    );
    expect(screen.getByText("Hybrid").getAttribute("title")).toContain(
      "8/10 sessions"
    );
  });

  it("graph badge tooltip mentions concept_count", () => {
    render(
      <Wrapper
        {...defaultProps({
          searchMode: {
            mode: "hybrid",
            embedded_sessions: 5,
            total_sessions: 5,
            has_graph: true,
            concept_count: 42,
          },
        })}
      />
    );
    expect(screen.getByText("Graph").getAttribute("title")).toContain("42");
  });
});
