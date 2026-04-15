import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Header from "../components/Header";

function defaultProps(overrides = {}) {
  return {
    providers: [
      { id: "claude", name: "Claude", projects: 5 },
      { id: "codex", name: "Codex", projects: 2 },
    ],
    provider: "claude",
    onProviderChange: vi.fn(),
    activeTab: "conversations",
    onTabChange: vi.fn(),
    statsText: "5 projects | 10 requests",
    showHidden: false,
    onToggleShowHidden: vi.fn(),
    hiddenTotal: 0,
    onRestoreAll: vi.fn(),
    theme: "dark",
    onToggleTheme: vi.fn(),
    isUpdating: false,
    updateStatus: null,
    onUpdate: vi.fn(),
    ...overrides,
  };
}

describe("Header — rendering", () => {
  it("renders the title", () => {
    render(<Header {...defaultProps()} />);
    expect(screen.getByText("Conversation Browser")).toBeInTheDocument();
  });

  it("renders the stats text", () => {
    render(<Header {...defaultProps({ statsText: "my stats" })} />);
    expect(screen.getByText("my stats")).toBeInTheDocument();
  });

  it("renders all 3 tab buttons", () => {
    render(<Header {...defaultProps()} />);
    expect(
      screen.getByRole("button", { name: "Conversations" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dashboard" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Knowledge Graph" })
    ).toBeInTheDocument();
  });
});

describe("Header — provider select/label", () => {
  it("renders provider select when multiple providers exist", () => {
    render(<Header {...defaultProps()} />);
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(screen.getByDisplayValue(/Claude/)).toBeInTheDocument();
  });

  it("renders capitalized provider label when only one provider exists", () => {
    render(
      <Header
        {...defaultProps({
          providers: [{ id: "claude", name: "Claude", projects: 5 }],
        })}
      />
    );
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText("Claude")).toBeInTheDocument();
  });

  it("provider change fires onProviderChange", async () => {
    const onChange = vi.fn();
    render(<Header {...defaultProps({ onProviderChange: onChange })} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "codex");
    expect(onChange).toHaveBeenCalledWith("codex");
  });
});

describe("Header — tab navigation", () => {
  it("active tab has the 'header-tab-active' class", () => {
    render(<Header {...defaultProps({ activeTab: "dashboard" })} />);
    expect(
      screen.getByRole("button", { name: "Dashboard" }).className
    ).toContain("header-tab-active");
    expect(
      screen.getByRole("button", { name: "Conversations" }).className
    ).not.toContain("header-tab-active");
  });

  it("clicking a tab fires onTabChange", async () => {
    const onTab = vi.fn();
    render(<Header {...defaultProps({ onTabChange: onTab })} />);
    await userEvent.click(screen.getByRole("button", { name: "Dashboard" }));
    expect(onTab).toHaveBeenCalledWith("dashboard");
    await userEvent.click(
      screen.getByRole("button", { name: "Knowledge Graph" })
    );
    expect(onTab).toHaveBeenCalledWith("graph");
  });
});

describe("Header — trash / restore-all", () => {
  it("Trash button renders with count when hiddenTotal > 0", () => {
    render(<Header {...defaultProps({ hiddenTotal: 3 })} />);
    expect(screen.getByRole("button", { name: "Trash (3)" })).toBeInTheDocument();
  });

  it("Trash button shows no count when hiddenTotal is 0", () => {
    render(<Header {...defaultProps({ hiddenTotal: 0 })} />);
    expect(screen.getByRole("button", { name: "Trash" })).toBeInTheDocument();
  });

  it("clicking Trash fires onToggleShowHidden", async () => {
    const onToggle = vi.fn();
    render(<Header {...defaultProps({ onToggleShowHidden: onToggle })} />);
    await userEvent.click(screen.getByRole("button", { name: "Trash" }));
    expect(onToggle).toHaveBeenCalled();
  });

  it("Trash button has 'active' class when showHidden is true", () => {
    render(<Header {...defaultProps({ showHidden: true })} />);
    expect(
      screen.getByRole("button", { name: "Trash" }).className
    ).toContain("toolbar-btn-active");
  });

  it("Restore All button visible only when showHidden + hiddenTotal > 0", () => {
    const { rerender } = render(
      <Header {...defaultProps({ showHidden: false, hiddenTotal: 3 })} />
    );
    expect(
      screen.queryByRole("button", { name: "Restore All" })
    ).not.toBeInTheDocument();
    rerender(<Header {...defaultProps({ showHidden: true, hiddenTotal: 0 })} />);
    expect(
      screen.queryByRole("button", { name: "Restore All" })
    ).not.toBeInTheDocument();
    rerender(<Header {...defaultProps({ showHidden: true, hiddenTotal: 3 })} />);
    expect(
      screen.getByRole("button", { name: "Restore All" })
    ).toBeInTheDocument();
  });

  it("clicking Restore All fires onRestoreAll", async () => {
    const onRestoreAll = vi.fn();
    render(
      <Header
        {...defaultProps({
          showHidden: true,
          hiddenTotal: 3,
          onRestoreAll,
        })}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "Restore All" }));
    expect(onRestoreAll).toHaveBeenCalled();
  });
});

describe("Header — theme toggle", () => {
  it("shows 'Light' label when theme is dark", () => {
    render(<Header {...defaultProps({ theme: "dark" })} />);
    expect(screen.getByRole("button", { name: "Light" })).toBeInTheDocument();
  });

  it("shows 'Dark' label when theme is light", () => {
    render(<Header {...defaultProps({ theme: "light" })} />);
    expect(screen.getByRole("button", { name: "Dark" })).toBeInTheDocument();
  });

  it("clicking the theme button fires onToggleTheme", async () => {
    const onToggle = vi.fn();
    render(<Header {...defaultProps({ onToggleTheme: onToggle })} />);
    await userEvent.click(screen.getByRole("button", { name: "Light" }));
    expect(onToggle).toHaveBeenCalled();
  });
});

describe("Header — update button", () => {
  it("default state shows 'Update' label and is enabled", () => {
    render(<Header {...defaultProps()} />);
    const btn = screen.getByRole("button", { name: "Update" });
    expect(btn).toBeInTheDocument();
    expect(btn).not.toBeDisabled();
  });

  it("shows 'Updating...' and is disabled when isUpdating", () => {
    render(<Header {...defaultProps({ isUpdating: true })} />);
    const btn = screen.getByRole("button", { name: "Updating..." });
    expect(btn).toBeDisabled();
  });

  it("shows 'Updated' with success class when updateStatus is success", () => {
    render(<Header {...defaultProps({ updateStatus: "success" })} />);
    const btn = screen.getByRole("button", { name: "Updated" });
    expect(btn.className).toContain("success");
  });

  it("shows 'Failed' with error class when updateStatus is error", () => {
    render(<Header {...defaultProps({ updateStatus: "error" })} />);
    const btn = screen.getByRole("button", { name: "Failed" });
    expect(btn.className).toContain("error");
  });

  it("clicking the update button fires onUpdate", async () => {
    const onUpdate = vi.fn();
    render(<Header {...defaultProps({ onUpdate })} />);
    await userEvent.click(screen.getByRole("button", { name: "Update" }));
    expect(onUpdate).toHaveBeenCalled();
  });
});
