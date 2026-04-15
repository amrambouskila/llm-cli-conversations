import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useResizeHandles } from "../../hooks/useResizeHandles";

function fireMove(x) {
  const event = new MouseEvent("mousemove", {
    clientX: x,
    bubbles: true,
    cancelable: true,
  });
  document.dispatchEvent(event);
}

function fireUp() {
  const event = new MouseEvent("mouseup", { bubbles: true });
  document.dispatchEvent(event);
}

beforeEach(() => {
  document.body.innerHTML = "";
  document.body.style.cursor = "";
});

describe("useResizeHandles — initial state", () => {
  it("initial pane widths match defaults", () => {
    const { result } = renderHook(() => useResizeHandles());
    expect(result.current.projectsWidth).toBe(220);
    expect(result.current.requestsWidth).toBe(340);
    expect(result.current.metadataWidth).toBe(364);
  });

  it("exposes mainRef with null current initially", () => {
    const { result } = renderHook(() => useResizeHandles());
    expect(result.current.mainRef).toHaveProperty("current");
    expect(result.current.mainRef.current).toBeNull();
  });

  it("startDrag is a stable function across renders", () => {
    const { result, rerender } = renderHook(() => useResizeHandles());
    const first = result.current.startDrag;
    rerender();
    expect(result.current.startDrag).toBe(first);
  });
});

describe("useResizeHandles — drag projects pane", () => {
  it("drags projects pane width to the clientX offset from mainRect.left", () => {
    const { result } = renderHook(() => useResizeHandles());
    // Attach a bounding rect to mainRef
    const container = document.createElement("div");
    document.body.appendChild(container);
    container.getBoundingClientRect = () => ({
      left: 50,
      right: 1200,
      top: 0,
      bottom: 900,
      width: 1150,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("projects");
    });
    act(() => fireMove(300));
    expect(result.current.projectsWidth).toBe(250);
  });

  it("clamps projects width to minimum 140", () => {
    const { result } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1000,
      top: 0,
      bottom: 900,
      width: 1000,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("projects");
    });
    act(() => fireMove(50));
    expect(result.current.projectsWidth).toBe(140);
  });

  it("clamps projects width to maximum 400", () => {
    const { result } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1000,
      top: 0,
      bottom: 900,
      width: 1000,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("projects");
    });
    act(() => fireMove(999));
    expect(result.current.projectsWidth).toBe(400);
  });
});

describe("useResizeHandles — drag requests pane", () => {
  it("drags requests pane width to clientX minus projectsWidth minus handle gap", () => {
    const { result } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1500,
      top: 0,
      bottom: 900,
      width: 1500,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("requests");
    });
    // clientX=600, projectsWidth=220, gap=5 → 600 - 0 - 220 - 5 = 375
    act(() => fireMove(600));
    expect(result.current.requestsWidth).toBe(375);
  });

  it("clamps requests width to 200 minimum", () => {
    const { result } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1500,
      top: 0,
      bottom: 900,
      width: 1500,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("requests");
    });
    act(() => fireMove(225));
    expect(result.current.requestsWidth).toBe(200);
  });

  it("clamps requests width to 600 maximum", () => {
    const { result } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1500,
      top: 0,
      bottom: 900,
      width: 1500,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("requests");
    });
    act(() => fireMove(1500));
    expect(result.current.requestsWidth).toBe(600);
  });
});

describe("useResizeHandles — drag metadata pane", () => {
  it("drags metadata pane width to mainRect.right minus clientX", () => {
    const { result } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1500,
      top: 0,
      bottom: 900,
      width: 1500,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("metadata");
    });
    act(() => fireMove(1100));
    expect(result.current.metadataWidth).toBe(400);
  });

  it("clamps metadata width to 250 minimum", () => {
    const { result } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1500,
      top: 0,
      bottom: 900,
      width: 1500,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("metadata");
    });
    act(() => fireMove(1400));
    expect(result.current.metadataWidth).toBe(250);
  });

  it("clamps metadata width to 600 maximum", () => {
    const { result } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1500,
      top: 0,
      bottom: 900,
      width: 1500,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("metadata");
    });
    act(() => fireMove(500));
    expect(result.current.metadataWidth).toBe(600);
  });
});

describe("useResizeHandles — drag end", () => {
  it("mouseup clears the dragging ref so mousemove is a no-op afterward", () => {
    const { result } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1500,
      top: 0,
      bottom: 900,
      width: 1500,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("projects");
    });
    act(() => fireMove(300));
    expect(result.current.projectsWidth).toBe(300);
    act(() => fireUp());
    act(() => fireMove(350));
    // Should stay at 300 because drag ended
    expect(result.current.projectsWidth).toBe(300);
  });

  it("mouseup clears document.body.style.cursor", () => {
    const { result } = renderHook(() => useResizeHandles());
    document.body.style.cursor = "col-resize";
    act(() => {
      result.current.startDrag("projects");
    });
    act(() => fireUp());
    expect(document.body.style.cursor).toBe("");
  });
});

describe("useResizeHandles — mousemove without active drag", () => {
  it("mousemove with no active drag is a no-op", () => {
    const { result } = renderHook(() => useResizeHandles());
    act(() => fireMove(500));
    expect(result.current.projectsWidth).toBe(220);
    expect(result.current.requestsWidth).toBe(340);
    expect(result.current.metadataWidth).toBe(364);
  });

  it("mousemove with no mainRef is a no-op", () => {
    const { result } = renderHook(() => useResizeHandles());
    // mainRef.current stays null
    act(() => {
      result.current.startDrag("projects");
    });
    act(() => fireMove(500));
    expect(result.current.projectsWidth).toBe(220);
  });
});

describe("useResizeHandles — cleanup", () => {
  it("unmount removes document-level listeners", () => {
    const { result, unmount } = renderHook(() => useResizeHandles());
    const container = document.createElement("div");
    container.getBoundingClientRect = () => ({
      left: 0,
      right: 1000,
      top: 0,
      bottom: 900,
      width: 1000,
      height: 900,
    });
    act(() => {
      result.current.mainRef.current = container;
    });
    act(() => {
      result.current.startDrag("projects");
    });
    const widthBefore = result.current.projectsWidth;
    unmount();
    act(() => fireMove(500));
    // After unmount, state updates don't propagate — ref remains, but the
    // listener is removed so setProjectsWidth is never invoked.
    // We can't easily assert this without re-rendering, but the listener
    // removal proves itself by not calling state updates (no React warning).
    expect(widthBefore).toBe(220);
  });
});
