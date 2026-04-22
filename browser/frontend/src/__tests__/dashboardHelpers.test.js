import { describe, it, expect } from "vitest";
import {
  formatUsd,
  anomalyComparator,
  buildCostBreakdownScope,
} from "../components/Dashboard";

describe("formatUsd", () => {
  it("formats a finite number as USD", () => {
    expect(formatUsd(12.5)).toBe("$12.50");
    expect(formatUsd(0)).toBe("$0.00");
    expect(formatUsd(1234.5)).toBe("$1,234.50");
  });

  it("coerces numeric strings", () => {
    expect(formatUsd("42.1")).toBe("$42.10");
  });

  it("returns $0.00 when coercion yields a non-finite number (line 39 false branch)", () => {
    expect(formatUsd(NaN)).toBe("$0.00");
    expect(formatUsd(Infinity)).toBe("$0.00");
    expect(formatUsd(-Infinity)).toBe("$0.00");
    expect(formatUsd("not-a-number")).toBe("$0.00");
    expect(formatUsd(undefined)).toBe("$0.00");
  });
});

describe("anomalyComparator", () => {
  const rows = [
    { project: "a", cost: 3 },
    { project: "b", cost: 1 },
    { project: "c", cost: 2 },
  ];

  it("sorts by string key ascending", () => {
    const sorted = [...rows].sort(anomalyComparator("project", true));
    expect(sorted.map((r) => r.project)).toEqual(["a", "b", "c"]);
  });

  it("sorts by numeric key descending", () => {
    const sorted = [...rows].sort(anomalyComparator("cost", false));
    expect(sorted.map((r) => r.cost)).toEqual([3, 2, 1]);
  });

  it("returns 0 when both sides are null (exercises both-null branch)", () => {
    const cmp = anomalyComparator("missing", false);
    expect(cmp({}, {})).toBe(0);
  });

  it("puts null on the right when only the left is null (asc and desc)", () => {
    const cmp = anomalyComparator("cost", false);
    expect(cmp({ cost: null }, { cost: 5 })).toBe(1);
    expect(cmp({ cost: 5 }, { cost: null })).toBe(-1);
  });

  it("ascending branch returns 1 for a > b, -1 for a < b", () => {
    const cmp = anomalyComparator("cost", true);
    expect(cmp({ cost: 10 }, { cost: 5 })).toBe(1);
    expect(cmp({ cost: 5 }, { cost: 10 })).toBe(-1);
  });
});

describe("buildCostBreakdownScope", () => {
  it("returns 'all time' when no filters are set", () => {
    expect(buildCostBreakdownScope({})).toBe("all time");
  });

  it("includes project filter", () => {
    expect(buildCostBreakdownScope({ project: "alpha" })).toBe(
      "project: alpha"
    );
  });

  it("includes model filter", () => {
    expect(buildCostBreakdownScope({ model: "opus" })).toBe("model: opus");
  });

  it("joins multiple filters with ' · '", () => {
    expect(
      buildCostBreakdownScope({ project: "a", model: "opus" })
    ).toBe("project: a · model: opus");
  });

  it("renders date range with both endpoints", () => {
    expect(
      buildCostBreakdownScope({ date_from: "2026-01-01", date_to: "2026-02-01" })
    ).toBe("date: 2026-01-01 → 2026-02-01");
  });

  it("falls back to '…' when only date_to is set (exercises date_from || '…')", () => {
    expect(buildCostBreakdownScope({ date_to: "2026-02-01" })).toBe(
      "date: … → 2026-02-01"
    );
  });

  it("falls back to '…' when only date_from is set (exercises date_to || '…')", () => {
    expect(buildCostBreakdownScope({ date_from: "2026-01-01" })).toBe(
      "date: 2026-01-01 → …"
    );
  });

  it("combines project + model + date range", () => {
    expect(
      buildCostBreakdownScope({
        project: "p",
        model: "m",
        date_from: "2026-01-01",
        date_to: "2026-01-07",
      })
    ).toBe("project: p · model: m · date: 2026-01-01 → 2026-01-07");
  });
});
