import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Heatmap from "../components/Heatmap";

function todayOffset(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

describe("Heatmap — empty state", () => {
  it("renders null when data is null", () => {
    const { container } = render(<Heatmap data={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders null when data is undefined", () => {
    const { container } = render(<Heatmap />);
    expect(container.firstChild).toBeNull();
  });

  it("renders null when data is an empty array", () => {
    const { container } = render(<Heatmap data={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("Heatmap — rendering", () => {
  it("renders the legend when data is provided", () => {
    render(
      <Heatmap data={[{ date: todayOffset(1), sessions: 2, cost: 1.5 }]} />
    );
    expect(screen.getByText("Less")).toBeInTheDocument();
    expect(screen.getByText("More")).toBeInTheDocument();
  });

  it("renders 5 legend-cell swatches (levels 0-4)", () => {
    const { container } = render(
      <Heatmap data={[{ date: todayOffset(1), sessions: 2, cost: 1.5 }]} />
    );
    expect(container.querySelectorAll(".heatmap-legend-cell").length).toBe(5);
  });

  it("renders day labels Mon / Wed / Fri", () => {
    render(
      <Heatmap data={[{ date: todayOffset(1), sessions: 2, cost: 1.5 }]} />
    );
    expect(screen.getByText("Mon")).toBeInTheDocument();
    expect(screen.getByText("Wed")).toBeInTheDocument();
    expect(screen.getByText("Fri")).toBeInTheDocument();
  });

  it("renders at least one <rect> cell for the 365-day grid", () => {
    const { container } = render(
      <Heatmap data={[{ date: todayOffset(1), sessions: 2, cost: 1.5 }]} />
    );
    const cells = container.querySelectorAll("rect.heatmap-cell");
    expect(cells.length).toBeGreaterThan(300);
  });

  it("renders month labels for the past year (at least 10 distinct months)", () => {
    const { container } = render(
      <Heatmap data={[{ date: todayOffset(1), sessions: 2, cost: 1.5 }]} />
    );
    const monthLabels = container.querySelectorAll(".heatmap-month-label");
    expect(monthLabels.length).toBeGreaterThan(10);
  });
});

describe("Heatmap — color levels", () => {
  it("all cells with no data get level 0 class", () => {
    const { container } = render(
      <Heatmap data={[{ date: todayOffset(100), sessions: 1, cost: 10 }]} />
    );
    const level0Cells = container.querySelectorAll(".heatmap-level-0");
    expect(level0Cells.length).toBeGreaterThan(300);
  });

  it("assigns level 4 to a cell at max cost", () => {
    const data = [
      { date: todayOffset(1), sessions: 1, cost: 10 },
      { date: todayOffset(2), sessions: 1, cost: 0.5 },
    ];
    const { container } = render(<Heatmap data={data} />);
    expect(container.querySelectorAll(".heatmap-level-4").length).toBeGreaterThanOrEqual(1);
  });

  it("assigns a non-zero level between 1 and 4 for below-max costs", () => {
    const data = [];
    for (let i = 1; i <= 10; i++) {
      data.push({ date: todayOffset(i), sessions: 1, cost: i });
    }
    const { container } = render(<Heatmap data={data} />);
    const nonZeroLevels = [1, 2, 3, 4].flatMap((lvl) =>
      Array.from(container.querySelectorAll(`.heatmap-level-${lvl}`))
    );
    expect(nonZeroLevels.length).toBeGreaterThan(0);
  });
});

describe("Heatmap — tooltip", () => {
  it("shows the tooltip on mouseenter over a cell", () => {
    const { container } = render(
      <Heatmap data={[{ date: todayOffset(1), sessions: 3, cost: 2.75 }]} />
    );
    const cellsWithData = container.querySelectorAll(
      ".heatmap-cell:not(.heatmap-level-0)"
    );
    expect(cellsWithData.length).toBeGreaterThan(0);
    fireEvent.mouseEnter(cellsWithData[0]);
    expect(container.querySelector(".heatmap-tooltip")).not.toBeNull();
  });

  it("tooltip text includes date, session count, and formatted cost", () => {
    const dateStr = todayOffset(1);
    const { container } = render(
      <Heatmap data={[{ date: dateStr, sessions: 3, cost: 2.75 }]} />
    );
    const cellsWithData = container.querySelectorAll(
      ".heatmap-cell:not(.heatmap-level-0)"
    );
    fireEvent.mouseEnter(cellsWithData[0]);
    const tooltip = container.querySelector(".heatmap-tooltip");
    expect(tooltip.textContent).toContain(dateStr);
    expect(tooltip.textContent).toContain("3 sessions");
    expect(tooltip.textContent).toContain("$2.75");
  });

  it("tooltip uses singular 'session' for count of 1", () => {
    const { container } = render(
      <Heatmap data={[{ date: todayOffset(1), sessions: 1, cost: 1 }]} />
    );
    const cellsWithData = container.querySelectorAll(
      ".heatmap-cell:not(.heatmap-level-0)"
    );
    fireEvent.mouseEnter(cellsWithData[0]);
    const tooltip = container.querySelector(".heatmap-tooltip");
    expect(tooltip.textContent).toContain("1 session,");
    expect(tooltip.textContent).not.toContain("1 sessions");
  });

  it("clears the tooltip on mouseleave", () => {
    const { container } = render(
      <Heatmap data={[{ date: todayOffset(1), sessions: 2, cost: 1 }]} />
    );
    const cellsWithData = container.querySelectorAll(
      ".heatmap-cell:not(.heatmap-level-0)"
    );
    fireEvent.mouseEnter(cellsWithData[0]);
    expect(container.querySelector(".heatmap-tooltip")).not.toBeNull();
    fireEvent.mouseLeave(cellsWithData[0]);
    expect(container.querySelector(".heatmap-tooltip")).toBeNull();
  });

  it("tooltip with zero-sessions uses plural 'sessions'", () => {
    const { container } = render(
      <Heatmap
        data={[
          { date: todayOffset(1), sessions: 0, cost: 0 },
          { date: todayOffset(2), sessions: 1, cost: 1 },
        ]}
      />
    );
    const allCells = container.querySelectorAll(".heatmap-cell");
    fireEvent.mouseEnter(allCells[0]);
    const tooltip = container.querySelector(".heatmap-tooltip");
    expect(tooltip.textContent).toContain("0 sessions");
  });
});
