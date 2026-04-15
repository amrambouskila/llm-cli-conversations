import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useKeyboardShortcuts } from "../../hooks/useKeyboardShortcuts";

function fireKey(key, opts = {}) {
  const event = new KeyboardEvent("keydown", {
    key,
    ctrlKey: opts.ctrl ?? false,
    metaKey: opts.meta ?? false,
    bubbles: true,
    cancelable: true,
  });
  document.dispatchEvent(event);
  return event;
}

function setup({
  segments = [],
  selectedSegmentId = null,
  onSelectSegment = vi.fn(),
  onClearSearch = vi.fn(),
  activeElementFactory = () => null,
  searchInput = null,
} = {}) {
  const input = searchInput ?? document.createElement("input");
  if (!searchInput) {
    // Default: attach to body so focus works in jsdom
    document.body.appendChild(input);
  }
  const activeEl = activeElementFactory(input);
  if (activeEl) activeEl.focus();
  const hook = renderHook(() =>
    useKeyboardShortcuts({
      searchRef: { current: input },
      segments,
      selectedSegmentId,
      onSelectSegment,
      onClearSearch,
    })
  );
  return { hook, input, onSelectSegment, onClearSearch };
}

beforeEach(() => {
  // Clean up body between tests
  document.body.innerHTML = "";
});

describe("useKeyboardShortcuts — Cmd/Ctrl+K", () => {
  it("Cmd+K focuses the search input", () => {
    const { input } = setup();
    const focusSpy = vi.spyOn(input, "focus");
    fireKey("k", { meta: true });
    expect(focusSpy).toHaveBeenCalled();
  });

  it("Ctrl+K focuses the search input", () => {
    const { input } = setup();
    const focusSpy = vi.spyOn(input, "focus");
    fireKey("k", { ctrl: true });
    expect(focusSpy).toHaveBeenCalled();
  });

  it("Plain 'k' (no modifier) does not focus the search input", () => {
    const { input } = setup();
    const focusSpy = vi.spyOn(input, "focus");
    fireKey("k");
    expect(focusSpy).not.toHaveBeenCalled();
  });

  it("Cmd+K calls preventDefault", () => {
    setup();
    const event = fireKey("k", { meta: true });
    expect(event.defaultPrevented).toBe(true);
  });
});

describe("useKeyboardShortcuts — Escape", () => {
  it("Escape on the search input calls onClearSearch and blurs", () => {
    const { input, onClearSearch } = setup({
      activeElementFactory: (i) => i,
    });
    const blurSpy = vi.spyOn(input, "blur");
    fireKey("Escape");
    expect(onClearSearch).toHaveBeenCalled();
    expect(blurSpy).toHaveBeenCalled();
  });

  it("Escape elsewhere is a no-op", () => {
    const { onClearSearch } = setup();
    fireKey("Escape");
    expect(onClearSearch).not.toHaveBeenCalled();
  });
});

describe("useKeyboardShortcuts — Arrow navigation", () => {
  const segments = [{ id: "a" }, { id: "b" }, { id: "c" }];

  it("ArrowDown advances to the next segment", () => {
    const { onSelectSegment } = setup({ segments, selectedSegmentId: "a" });
    fireKey("ArrowDown");
    expect(onSelectSegment).toHaveBeenCalledWith("b");
  });

  it("ArrowDown wraps from last to first", () => {
    const { onSelectSegment } = setup({ segments, selectedSegmentId: "c" });
    fireKey("ArrowDown");
    expect(onSelectSegment).toHaveBeenCalledWith("a");
  });

  it("ArrowUp moves to the previous segment", () => {
    const { onSelectSegment } = setup({ segments, selectedSegmentId: "b" });
    fireKey("ArrowUp");
    expect(onSelectSegment).toHaveBeenCalledWith("a");
  });

  it("ArrowUp wraps from first to last", () => {
    const { onSelectSegment } = setup({ segments, selectedSegmentId: "a" });
    fireKey("ArrowUp");
    expect(onSelectSegment).toHaveBeenCalledWith("c");
  });

  it("ArrowUp with no selection wraps to last (idx -1 path)", () => {
    const { onSelectSegment } = setup({ segments, selectedSegmentId: null });
    fireKey("ArrowUp");
    expect(onSelectSegment).toHaveBeenCalledWith("c");
  });

  it("ArrowDown with no selection advances to first (idx -1 → 0)", () => {
    const { onSelectSegment } = setup({ segments, selectedSegmentId: null });
    fireKey("ArrowDown");
    expect(onSelectSegment).toHaveBeenCalledWith("a");
  });

  it("ArrowDown with empty segments is a no-op", () => {
    const { onSelectSegment } = setup({ segments: [], selectedSegmentId: null });
    fireKey("ArrowDown");
    expect(onSelectSegment).not.toHaveBeenCalled();
  });

  it("ArrowDown while focused on an input is ignored", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    const { onSelectSegment } = setup({
      segments,
      selectedSegmentId: "a",
      searchInput: input,
      activeElementFactory: () => input,
    });
    fireKey("ArrowDown");
    expect(onSelectSegment).not.toHaveBeenCalled();
  });

  it("ArrowDown calls preventDefault when a segment is selected", () => {
    setup({ segments, selectedSegmentId: "a" });
    const event = fireKey("ArrowDown");
    expect(event.defaultPrevented).toBe(true);
  });
});

describe("useKeyboardShortcuts — unrelated keys", () => {
  it("Typing an unrelated key does nothing", () => {
    const { onSelectSegment, onClearSearch } = setup({
      segments: [{ id: "a" }],
      selectedSegmentId: "a",
    });
    fireKey("Enter");
    fireKey("x");
    fireKey("Tab");
    expect(onSelectSegment).not.toHaveBeenCalled();
    expect(onClearSearch).not.toHaveBeenCalled();
  });
});

describe("useKeyboardShortcuts — cleanup", () => {
  it("removes the event listener on unmount", () => {
    const onSelectSegment = vi.fn();
    const input = document.createElement("input");
    document.body.appendChild(input);
    function TestHook() {
      const ref = { current: input };
      return useKeyboardShortcuts({
        searchRef: ref,
        segments: [{ id: "a" }, { id: "b" }],
        selectedSegmentId: "a",
        onSelectSegment,
        onClearSearch: vi.fn(),
      });
    }
    const { unmount } = renderHook(TestHook);
    unmount();
    fireKey("ArrowDown");
    expect(onSelectSegment).not.toHaveBeenCalled();
  });
});
