import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  ToolBreakdownChart,
  ConversationTimeline,
  TokenCostEstimate,
  RequestSizeSparkline,
  MonthlyBreakdown,
  ProjectSizeBar,
} from "../components/Charts";

describe("ToolBreakdownChart", () => {
  it("renders null when breakdown is null", () => {
    const { container } = render(<ToolBreakdownChart breakdown={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders null when breakdown is undefined", () => {
    const { container } = render(<ToolBreakdownChart />);
    expect(container.firstChild).toBeNull();
  });

  it("renders null when breakdown is an empty object", () => {
    const { container } = render(<ToolBreakdownChart breakdown={{}} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the chart title when breakdown has entries", () => {
    render(<ToolBreakdownChart breakdown={{ Bash: 5 }} />);
    expect(screen.getByText("Tool Usage")).toBeInTheDocument();
  });

  it("renders one row per tool with name and count", () => {
    render(<ToolBreakdownChart breakdown={{ Bash: 5, Edit: 3 }} />);
    expect(screen.getByText("Bash")).toBeInTheDocument();
    expect(screen.getByText("Edit")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("sorts rows by count descending", () => {
    const { container } = render(
      <ToolBreakdownChart breakdown={{ Read: 2, Bash: 10, Edit: 5 }} />
    );
    const labels = Array.from(
      container.querySelectorAll(".tool-bar-label")
    ).map((el) => el.textContent);
    expect(labels).toEqual(["Bash", "Edit", "Read"]);
  });

  it("scales bar widths relative to the max count", () => {
    const { container } = render(
      <ToolBreakdownChart breakdown={{ Bash: 10, Edit: 5 }} />
    );
    const fills = container.querySelectorAll(".tool-bar-fill");
    expect(fills[0].style.width).toBe("100%");
    expect(fills[1].style.width).toBe("50%");
  });
});

describe("ConversationTimeline", () => {
  it("renders null when timestamps is null", () => {
    const { container } = render(<ConversationTimeline timestamps={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders null when timestamps has fewer than 2 entries", () => {
    const { container } = render(
      <ConversationTimeline timestamps={["2026-01-01T00:00:00Z"]} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders the chart title for >= 2 timestamps", () => {
    render(
      <ConversationTimeline
        timestamps={["2026-01-01T00:00:00Z", "2026-01-31T00:00:00Z"]}
      />
    );
    expect(screen.getByText("Conversation Timeline")).toBeInTheDocument();
  });

  it("places one dot per timestamp", () => {
    const { container } = render(
      <ConversationTimeline
        timestamps={[
          "2026-01-01T00:00:00Z",
          "2026-01-15T00:00:00Z",
          "2026-01-31T00:00:00Z",
        ]}
      />
    );
    expect(container.querySelectorAll(".timeline-dot").length).toBe(3);
  });

  it("positions first dot at 0% and last dot at 100% of range", () => {
    const { container } = render(
      <ConversationTimeline
        timestamps={["2026-01-01T00:00:00Z", "2026-01-31T00:00:00Z"]}
      />
    );
    const dots = container.querySelectorAll(".timeline-dot");
    expect(dots[0].style.left).toBe("0%");
    expect(dots[1].style.left).toBe("100%");
  });

  it("uses firstTs / lastTs when provided instead of timestamps[0] / [n-1]", () => {
    const { container } = render(
      <ConversationTimeline
        timestamps={["2026-01-15T00:00:00Z", "2026-01-16T00:00:00Z"]}
        firstTs="2026-01-01T00:00:00Z"
        lastTs="2026-01-31T00:00:00Z"
      />
    );
    const dots = container.querySelectorAll(".timeline-dot");
    expect(dots[0].style.left).not.toBe("0%");
    expect(dots[1].style.left).not.toBe("100%");
  });

  it("falls back to 1 when start equals end (guards div-by-zero)", () => {
    const { container } = render(
      <ConversationTimeline
        timestamps={["2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"]}
      />
    );
    const dots = container.querySelectorAll(".timeline-dot");
    expect(dots[0].style.left).toBe("0%");
    expect(dots[1].style.left).toBe("0%");
  });
});

describe("TokenCostEstimate", () => {
  it("renders null when tokens is 0 (falsy)", () => {
    const { container } = render(<TokenCostEstimate tokens={0} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders null when tokens is undefined", () => {
    const { container } = render(<TokenCostEstimate />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the chart title when tokens > 0", () => {
    render(<TokenCostEstimate tokens={1_000_000} />);
    // Phase 7.5 renamed the title to make the 80/20 heuristic explicit.
    expect(
      screen.getByText(/Rough cost estimate \(80\/20 heuristic\)/i)
    ).toBeInTheDocument();
  });

  it("shows both Claude models by default", () => {
    render(<TokenCostEstimate tokens={1_000_000} />);
    expect(screen.getByText("Sonnet")).toBeInTheDocument();
    expect(screen.getByText("Opus")).toBeInTheDocument();
  });

  it("shows OpenAI models when provider is codex", () => {
    render(<TokenCostEstimate tokens={1_000_000} provider="codex" />);
    expect(screen.getByText("GPT-4o")).toBeInTheDocument();
    expect(screen.getByText("o3")).toBeInTheDocument();
  });

  it("falls back to Claude when provider is unknown", () => {
    render(<TokenCostEstimate tokens={1_000_000} provider="unknown" />);
    expect(screen.getByText("Sonnet")).toBeInTheDocument();
    expect(screen.getByText("Opus")).toBeInTheDocument();
  });

  it("computes Sonnet cost correctly for 1M tokens (80/20 split)", () => {
    // 800K * 3/M + 200K * 15/M = 2.4 + 3.0 = 5.4
    render(<TokenCostEstimate tokens={1_000_000} />);
    expect(screen.getByText("$5.4000")).toBeInTheDocument();
  });

  it("computes Opus cost correctly for 1M tokens (80/20 split)", () => {
    // 800K * 15/M + 200K * 75/M = 12.0 + 15.0 = 27.0
    render(<TokenCostEstimate tokens={1_000_000} />);
    expect(screen.getByText("$27.0000")).toBeInTheDocument();
  });

  it("formats cost with 4 decimal places", () => {
    render(<TokenCostEstimate tokens={1000} />);
    expect(screen.getByText("$0.0054")).toBeInTheDocument();
  });
});

describe("RequestSizeSparkline", () => {
  it("renders null when sizes is null", () => {
    const { container } = render(<RequestSizeSparkline sizes={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders null when sizes has fewer than 2 entries", () => {
    const { container } = render(<RequestSizeSparkline sizes={[5]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the chart title for >= 2 sizes", () => {
    render(<RequestSizeSparkline sizes={[5, 10]} />);
    expect(screen.getByText("Request Sizes")).toBeInTheDocument();
  });

  it("renders one <rect> per size", () => {
    const { container } = render(
      <RequestSizeSparkline sizes={[1, 2, 3, 4, 5]} />
    );
    expect(container.querySelectorAll("rect").length).toBe(5);
  });

  it("shows min and max labels", () => {
    render(<RequestSizeSparkline sizes={[100, 500, 1200]} />);
    expect(screen.getByText("100 min")).toBeInTheDocument();
    expect(screen.getByText("1.2K max")).toBeInTheDocument();
  });

  it("scales tallest bar to full height when values differ", () => {
    const { container } = render(<RequestSizeSparkline sizes={[10, 100]} />);
    const rects = container.querySelectorAll("rect");
    const heights = Array.from(rects).map(
      (r) => parseFloat(r.getAttribute("height")) || 0
    );
    const max = Math.max(...heights);
    expect(max).toBeGreaterThanOrEqual(35);
  });

  it("falls back to height 1 when max is 0", () => {
    const { container } = render(<RequestSizeSparkline sizes={[0, 0]} />);
    const rects = container.querySelectorAll("rect");
    rects.forEach((r) => {
      expect(parseFloat(r.getAttribute("height"))).toBe(1);
    });
  });
});

describe("MonthlyBreakdown", () => {
  it("renders null when monthly is null", () => {
    const { container } = render(<MonthlyBreakdown monthly={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders null when monthly is empty", () => {
    const { container } = render(<MonthlyBreakdown monthly={{}} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the chart title when monthly has entries", () => {
    render(
      <MonthlyBreakdown
        monthly={{ "2026-01": { tokens: 1000, requests: 5 } }}
      />
    );
    expect(screen.getByText("Monthly Breakdown")).toBeInTheDocument();
  });

  it("renders header row with Month / Requests / Tokens + 2 model labels (claude)", () => {
    render(
      <MonthlyBreakdown
        monthly={{ "2026-01": { tokens: 1000, requests: 5 } }}
      />
    );
    expect(screen.getByText("Month")).toBeInTheDocument();
    expect(screen.getByText("Requests")).toBeInTheDocument();
    expect(screen.getByText("Tokens")).toBeInTheDocument();
    expect(screen.getByText("Sonnet")).toBeInTheDocument();
    expect(screen.getByText("Opus")).toBeInTheDocument();
  });

  it("renders OpenAI model labels when provider is codex", () => {
    render(
      <MonthlyBreakdown
        monthly={{ "2026-01": { tokens: 1000, requests: 5 } }}
        provider="codex"
      />
    );
    expect(screen.getByText("GPT-4o")).toBeInTheDocument();
    expect(screen.getByText("o3")).toBeInTheDocument();
  });

  it("falls back to Claude pricing for unknown provider", () => {
    render(
      <MonthlyBreakdown
        monthly={{ "2026-01": { tokens: 1000, requests: 5 } }}
        provider="unknown"
      />
    );
    expect(screen.getByText("Sonnet")).toBeInTheDocument();
  });

  it("renders one row per month with formatted tokens", () => {
    render(
      <MonthlyBreakdown
        monthly={{
          "2026-01": { tokens: 500_000, requests: 12 },
          "2026-02": { tokens: 1_200_000, requests: 20 },
        }}
      />
    );
    expect(screen.getByText("2026-01")).toBeInTheDocument();
    expect(screen.getByText("2026-02")).toBeInTheDocument();
    expect(screen.getByText("500.0K")).toBeInTheDocument();
    expect(screen.getByText("1.2M")).toBeInTheDocument();
  });

  it("formats per-row cost with 2 decimals", () => {
    // 1M tokens = 800K input + 200K output
    // Sonnet: 800K*3/M + 200K*15/M = 2.4 + 3.0 = $5.40
    render(
      <MonthlyBreakdown
        monthly={{ "2026-01": { tokens: 1_000_000, requests: 5 } }}
      />
    );
    expect(screen.getByText("$5.40")).toBeInTheDocument();
  });
});

describe("ProjectSizeBar", () => {
  it("renders null when maxSize is 0", () => {
    const { container } = render(<ProjectSizeBar size={10} maxSize={0} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders null when maxSize is undefined", () => {
    const { container } = render(<ProjectSizeBar size={10} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders a fill bar at (size / maxSize) * 100%", () => {
    const { container } = render(<ProjectSizeBar size={25} maxSize={100} />);
    const fill = container.querySelector(".project-size-bar-fill");
    expect(fill.style.width).toBe("25%");
  });

  it("caps at 100% when size equals maxSize", () => {
    const { container } = render(<ProjectSizeBar size={50} maxSize={50} />);
    const fill = container.querySelector(".project-size-bar-fill");
    expect(fill.style.width).toBe("100%");
  });

  it("renders a fill bar at 0% when size is 0", () => {
    const { container } = render(<ProjectSizeBar size={0} maxSize={100} />);
    const fill = container.querySelector(".project-size-bar-fill");
    expect(fill.style.width).toBe("0%");
  });
});
