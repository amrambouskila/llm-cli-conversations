import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

describe("toolchain smoke", () => {
  it("renders and queries DOM", () => {
    render(<div>Hello</div>);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });
});
