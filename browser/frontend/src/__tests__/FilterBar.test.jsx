import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FilterBar from "../components/FilterBar";

function defaultProps(overrides = {}) {
  return {
    filterOptions: {
      projects: ["alpha"],
      models: ["opus"],
      tools: ["Bash"],
      topics: ["docker"],
    },
    searchQuery: "",
    onQueryChange: vi.fn(),
    pendingDateFrom: "",
    onPendingDateFromChange: vi.fn(),
    pendingDateTo: "",
    onPendingDateToChange: vi.fn(),
    dateFrom: "",
    dateTo: "",
    onApply: vi.fn(),
    onClear: vi.fn(),
    ...overrides,
  };
}

describe("FilterBar", () => {
  it("renders FilterChips (chips + dropdowns)", () => {
    render(<FilterBar {...defaultProps()} />);
    expect(screen.getByRole("button", { name: "project" })).toBeInTheDocument();
  });

  it("renders From and To date inputs", () => {
    const { container } = render(<FilterBar {...defaultProps()} />);
    const dateInputs = container.querySelectorAll("input[type='date']");
    expect(dateInputs.length).toBe(2);
  });

  it("typing in the From input fires onPendingDateFromChange", async () => {
    const onChange = vi.fn();
    const { container } = render(
      <FilterBar {...defaultProps({ onPendingDateFromChange: onChange })} />
    );
    const fromInput = container.querySelectorAll("input[type='date']")[0];
    await userEvent.type(fromInput, "2026-01-01");
    expect(onChange).toHaveBeenCalled();
  });

  it("typing in the To input fires onPendingDateToChange", async () => {
    const onChange = vi.fn();
    const { container } = render(
      <FilterBar {...defaultProps({ onPendingDateToChange: onChange })} />
    );
    const toInput = container.querySelectorAll("input[type='date']")[1];
    await userEvent.type(toInput, "2026-02-28");
    expect(onChange).toHaveBeenCalled();
  });

  it("Apply button fires onApply", async () => {
    const onApply = vi.fn();
    render(<FilterBar {...defaultProps({ onApply })} />);
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onApply).toHaveBeenCalled();
  });

  it("Clear button is absent when no active dates", () => {
    render(<FilterBar {...defaultProps()} />);
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });

  it("Clear button is present when dateFrom is set", () => {
    render(<FilterBar {...defaultProps({ dateFrom: "2026-01-01" })} />);
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
  });

  it("Clear button is present when dateTo is set", () => {
    render(<FilterBar {...defaultProps({ dateTo: "2026-01-31" })} />);
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
  });

  it("Clear button fires onClear", async () => {
    const onClear = vi.fn();
    render(
      <FilterBar {...defaultProps({ dateFrom: "2026-01-01", onClear })} />
    );
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(onClear).toHaveBeenCalled();
  });

  it("pending date values display in the inputs", () => {
    const { container } = render(
      <FilterBar
        {...defaultProps({
          pendingDateFrom: "2026-01-01",
          pendingDateTo: "2026-02-28",
        })}
      />
    );
    const inputs = container.querySelectorAll("input[type='date']");
    expect(inputs[0].value).toBe("2026-01-01");
    expect(inputs[1].value).toBe("2026-02-28");
  });
});
