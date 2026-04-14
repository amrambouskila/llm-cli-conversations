import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SearchResults from "../components/SearchResults";

const baseResult = (overrides = {}) => ({
  session_id: "s1",
  project: "conversations",
  date: "2026-04-01T10:00:00Z",
  model: "claude-opus-4-6",
  cost: 2.345,
  snippet: "the docker auth issue",
  tool_summary: "Bash(4), Edit(3)",
  tools: { Bash: 4, Edit: 3 },
  turn_count: 12,
  topics: ["docker", "auth"],
  conversation_id: "c1",
  rank: 1.0,
  ...overrides,
});

describe("SearchResults — empty state", () => {
  it("renders 'No results found' for an empty array", () => {
    render(
      <SearchResults
        results={[]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(screen.getByText("No results found")).toBeInTheDocument();
  });

  it("renders 'No results found' for null", () => {
    render(
      <SearchResults
        results={null}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(screen.getByText("No results found")).toBeInTheDocument();
  });
});

describe("SearchResults — single result", () => {
  it("renders rank #1, project, model, cost, snippet, tool summary, turn count", () => {
    const r = baseResult();
    render(
      <SearchResults results={[r]} onSelectSession={() => {}} searchQuery="" />
    );
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("conversations")).toBeInTheDocument();
    expect(screen.getByText("claude-opus-4-6")).toBeInTheDocument();
    expect(screen.getByText("$2.35")).toBeInTheDocument();
    expect(screen.getByText("the docker auth issue")).toBeInTheDocument();
    expect(screen.getByText("Bash(4), Edit(3)")).toBeInTheDocument();
    expect(screen.getByText("12 turns")).toBeInTheDocument();
  });

  it("renders date via formatTimestamp (non-empty, not N/A)", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult()]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    const date = container.querySelector(".search-result-date");
    expect(date).toBeInTheDocument();
    expect(date.textContent.length).toBeGreaterThan(0);
    expect(date.textContent).not.toBe("N/A");
  });

  it("renders empty date span when r.date is falsy", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ date: null })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    const date = container.querySelector(".search-result-date");
    expect(date).toBeInTheDocument();
    expect(date.textContent).toBe("");
  });

  it("renders topics joined by ', ', capped at 3", () => {
    render(
      <SearchResults
        results={[baseResult({ topics: ["a", "b", "c", "d", "e"] })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(screen.getByText("a, b, c")).toBeInTheDocument();
    expect(screen.queryByText("a, b, c, d")).not.toBeInTheDocument();
  });

  it("renders 1-2 topics with no trailing comma", () => {
    render(
      <SearchResults
        results={[baseResult({ topics: ["docker", "auth"] })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(screen.getByText("docker, auth")).toBeInTheDocument();
  });

  it("omits topics span entirely when topics is empty", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ topics: [] })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(container.querySelector(".search-result-topics")).toBeNull();
  });

  it("omits topics span when topics is undefined", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ topics: undefined })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(container.querySelector(".search-result-topics")).toBeNull();
  });
});

describe("SearchResults — multiple results", () => {
  it("renders rank labels #1, #2, #3", () => {
    const results = [
      baseResult({ session_id: "s1", rank: 1.0 }),
      baseResult({ session_id: "s2", rank: 0.5 }),
      baseResult({ session_id: "s3", rank: 0.25 }),
    ];
    render(
      <SearchResults
        results={results}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("#2")).toBeInTheDocument();
    expect(screen.getByText("#3")).toBeInTheDocument();
  });
});

describe("SearchResults — relevance bar", () => {
  it("top result fill width is 100%", () => {
    const results = [
      baseResult({ session_id: "s1", rank: 1.0 }),
      baseResult({ session_id: "s2", rank: 0.5 }),
    ];
    const { container } = render(
      <SearchResults
        results={results}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    const fills = container.querySelectorAll(".search-result-relevance-fill");
    expect(fills[0].style.width).toBe("100%");
  });

  it("subsequent result fill is proportional (rank/maxRank)", () => {
    const results = [
      baseResult({ session_id: "s1", rank: 1.0 }),
      baseResult({ session_id: "s2", rank: 0.5 }),
    ];
    const { container } = render(
      <SearchResults
        results={results}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    const fills = container.querySelectorAll(".search-result-relevance-fill");
    expect(fills[1].style.width).toBe("50%");
  });
});

describe("SearchResults — click handler", () => {
  it("invokes onSelectSession with the full result object on card click", async () => {
    const onSelect = vi.fn();
    const r = baseResult();
    const { container } = render(
      <SearchResults
        results={[r]}
        onSelectSession={onSelect}
        searchQuery=""
      />
    );
    const card = container.querySelector(".search-result-card");
    await userEvent.click(card);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(r);
  });
});

describe("SearchResults — snippet highlighting", () => {
  it("wraps query matches in <mark>", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ snippet: "the docker auth issue" })]}
        onSelectSession={() => {}}
        searchQuery="docker"
      />
    );
    const marks = container.querySelectorAll("mark");
    expect(marks.length).toBe(1);
    expect(marks[0].textContent).toBe("docker");
  });

  it("strips filter prefixes from query before highlighting (no false marks)", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ snippet: "the foo and the docker" })]}
        onSelectSession={() => {}}
        searchQuery="project:foo docker"
      />
    );
    const marks = container.querySelectorAll("mark");
    expect(marks.length).toBe(1);
    expect(marks[0].textContent).toBe("docker");
    const snippet = container.querySelector(".search-result-snippet");
    expect(snippet.textContent).toContain("foo");
  });

  it("does not highlight on single-char query", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ snippet: "a quick brown fox" })]}
        onSelectSession={() => {}}
        searchQuery="a"
      />
    );
    expect(container.querySelectorAll("mark").length).toBe(0);
  });

  it("does not highlight when query is only filter prefixes (no free text left)", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ snippet: "foo bar baz" })]}
        onSelectSession={() => {}}
        searchQuery="project:foo"
      />
    );
    expect(container.querySelectorAll("mark").length).toBe(0);
  });

  it("does not highlight when free text exists but every term is shorter than 2 chars", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ snippet: "the docker auth issue" })]}
        onSelectSession={() => {}}
        searchQuery="a b c"
      />
    );
    expect(container.querySelectorAll("mark").length).toBe(0);
    expect(
      container.querySelector(".search-result-snippet").textContent
    ).toBe("the docker auth issue");
  });
});

describe("SearchResults — nullish fallbacks", () => {
  it("treats undefined rank as 0 in relevance bar width", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ rank: undefined })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    const fill = container.querySelector(".search-result-relevance-fill");
    expect(fill.style.width).toBe("0%");
  });

  it("treats null snippet as empty string in renderer", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ snippet: null })]}
        onSelectSession={() => {}}
        searchQuery="docker"
      />
    );
    expect(
      container.querySelector(".search-result-snippet").textContent
    ).toBe("");
  });
});

describe("SearchResults — null-safe rendering", () => {
  it("hides cost when null (does not render '$null' or crash)", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ cost: null })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(container.querySelector(".search-result-cost")).toBeNull();
    expect(container.textContent).not.toContain("$null");
  });

  it("hides cost when undefined", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ cost: undefined })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(container.querySelector(".search-result-cost")).toBeNull();
  });

  it("hides model span when model is falsy", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ model: null })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(container.querySelector(".search-result-model")).toBeNull();
  });

  it("hides turn_count span when turn_count is null", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ turn_count: null })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(container.querySelector(".search-result-turns")).toBeNull();
  });

  it("hides tool_summary span when tool_summary is empty", () => {
    const { container } = render(
      <SearchResults
        results={[baseResult({ tool_summary: "" })]}
        onSelectSession={() => {}}
        searchQuery=""
      />
    );
    expect(container.querySelector(".search-result-tools")).toBeNull();
  });
});
