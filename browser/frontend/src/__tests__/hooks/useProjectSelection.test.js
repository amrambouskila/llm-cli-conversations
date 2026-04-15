import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("../../api", () => ({
  fetchSegments: vi.fn(),
  fetchSegmentsWithHidden: vi.fn(),
  fetchSegmentDetail: vi.fn(),
  fetchConversation: vi.fn(),
}));

import { useProjectSelection } from "../../hooks/useProjectSelection";
import {
  fetchSegments,
  fetchSegmentsWithHidden,
  fetchSegmentDetail,
  fetchConversation,
} from "../../api";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useProjectSelection — initial state", () => {
  it("all selections start as null / empty", () => {
    const { result } = renderHook(() => useProjectSelection("claude", false));
    expect(result.current.selectedProject).toBeNull();
    expect(result.current.segments).toEqual([]);
    expect(result.current.selectedSegmentId).toBeNull();
    expect(result.current.segmentDetail).toBeNull();
    expect(result.current.convViewData).toBeNull();
  });
});

describe("useProjectSelection — loadSegments", () => {
  it("routes to fetchSegments when showHidden is false", async () => {
    fetchSegments.mockResolvedValue([]);
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.loadSegments("proj-a");
    });
    expect(fetchSegments).toHaveBeenCalledWith("proj-a", "claude");
    expect(fetchSegmentsWithHidden).not.toHaveBeenCalled();
  });

  it("routes to fetchSegmentsWithHidden when showHidden is true", async () => {
    fetchSegmentsWithHidden.mockResolvedValue([]);
    const { result } = renderHook(() => useProjectSelection("claude", true));
    await act(async () => {
      await result.current.loadSegments("proj-a");
    });
    expect(fetchSegmentsWithHidden).toHaveBeenCalledWith("proj-a", "claude");
    expect(fetchSegments).not.toHaveBeenCalled();
  });
});

describe("useProjectSelection — handleSelectProject", () => {
  it("sets selectedProject and fetches segments", async () => {
    fetchSegments.mockResolvedValue([{ id: "s1" }, { id: "s2" }]);
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleSelectProject("my-proj");
    });
    expect(result.current.selectedProject).toBe("my-proj");
    expect(result.current.segments).toEqual([{ id: "s1" }, { id: "s2" }]);
  });

  it("resets downstream selection state", async () => {
    fetchSegments.mockResolvedValue([]);
    const { result } = renderHook(() => useProjectSelection("claude", false));
    // Pre-set some state by selecting a segment
    fetchSegmentDetail.mockResolvedValue({ id: "s1", preview: "x" });
    await act(async () => {
      await result.current.handleSelectProject("proj-a");
    });
    await act(async () => {
      await result.current.handleSelectSegment("s1");
    });
    expect(result.current.selectedSegmentId).toBe("s1");
    // Now re-select a project
    await act(async () => {
      await result.current.handleSelectProject("proj-b");
    });
    expect(result.current.selectedSegmentId).toBeNull();
    expect(result.current.segmentDetail).toBeNull();
    expect(result.current.convViewData).toBeNull();
  });

  it("logs but does not throw when fetch fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    fetchSegments.mockRejectedValue(new Error("net"));
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleSelectProject("x");
    });
    expect(consoleSpy).toHaveBeenCalled();
    expect(result.current.selectedProject).toBe("x");
    consoleSpy.mockRestore();
  });
});

describe("useProjectSelection — handleDeselectProject", () => {
  it("clears all selection state", async () => {
    fetchSegments.mockResolvedValue([{ id: "s1" }]);
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleSelectProject("proj-a");
    });
    expect(result.current.selectedProject).toBe("proj-a");
    expect(result.current.segments).toHaveLength(1);
    act(() => {
      result.current.handleDeselectProject();
    });
    expect(result.current.selectedProject).toBeNull();
    expect(result.current.segments).toEqual([]);
    expect(result.current.selectedSegmentId).toBeNull();
    expect(result.current.segmentDetail).toBeNull();
    expect(result.current.convViewData).toBeNull();
  });
});

describe("useProjectSelection — handleSelectSegment", () => {
  it("sets selectedSegmentId and fetches detail", async () => {
    fetchSegmentDetail.mockResolvedValue({ id: "s-xyz", preview: "snip" });
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleSelectSegment("s-xyz");
    });
    expect(result.current.selectedSegmentId).toBe("s-xyz");
    expect(result.current.segmentDetail).toEqual({
      id: "s-xyz",
      preview: "snip",
    });
    expect(fetchSegmentDetail).toHaveBeenCalledWith("s-xyz", "claude");
  });

  it("clears convViewData when selecting a segment", async () => {
    fetchSegments.mockResolvedValue([]);
    fetchConversation.mockResolvedValue({ conversation_id: "c1" });
    fetchSegmentDetail.mockResolvedValue({ id: "s1" });
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleSelectProject("p1");
    });
    await act(async () => {
      await result.current.handleViewConversation("c1");
    });
    expect(result.current.convViewData).not.toBeNull();
    await act(async () => {
      await result.current.handleSelectSegment("s1");
    });
    expect(result.current.convViewData).toBeNull();
  });

  it("non-fatal on fetchSegmentDetail error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    fetchSegmentDetail.mockRejectedValue(new Error("fail"));
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleSelectSegment("s1");
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});

describe("useProjectSelection — handleViewConversation", () => {
  it("is a no-op without a selected project", async () => {
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleViewConversation("c1");
    });
    expect(fetchConversation).not.toHaveBeenCalled();
  });

  it("fetches conversation and clears segment selection", async () => {
    fetchSegments.mockResolvedValue([]);
    fetchConversation.mockResolvedValue({
      conversation_id: "c1",
      raw_markdown: "x",
    });
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleSelectProject("p1");
    });
    await act(async () => {
      await result.current.handleViewConversation("c1");
    });
    expect(fetchConversation).toHaveBeenCalledWith("p1", "c1", "claude");
    expect(result.current.convViewData).toEqual({
      conversation_id: "c1",
      raw_markdown: "x",
    });
    expect(result.current.selectedSegmentId).toBeNull();
    expect(result.current.segmentDetail).toBeNull();
  });

  it("non-fatal on fetchConversation error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    fetchSegments.mockResolvedValue([]);
    fetchConversation.mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleSelectProject("p1");
    });
    await act(async () => {
      await result.current.handleViewConversation("c1");
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});

describe("useProjectSelection — loadProjectConversation", () => {
  it("sets project + segments + conversation in one flow", async () => {
    fetchSegments.mockResolvedValue([{ id: "a" }, { id: "b" }]);
    fetchConversation.mockResolvedValue({ conversation_id: "c1" });
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.loadProjectConversation("proj-a", "c1");
    });
    expect(result.current.selectedProject).toBe("proj-a");
    expect(result.current.segments).toHaveLength(2);
    expect(result.current.convViewData).toEqual({ conversation_id: "c1" });
  });

  it("non-fatal on error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    fetchSegments.mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.loadProjectConversation("p1", "c1");
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});

describe("useProjectSelection — auto-refresh on showHidden change", () => {
  it("re-fetches segments when showHidden changes and a project is selected", async () => {
    fetchSegments.mockResolvedValue([{ id: "a" }]);
    fetchSegmentsWithHidden.mockResolvedValue([
      { id: "a" },
      { id: "b", hidden: true },
    ]);
    const { result, rerender } = renderHook(
      ({ sh }) => useProjectSelection("claude", sh),
      { initialProps: { sh: false } }
    );
    await act(async () => {
      await result.current.handleSelectProject("p1");
    });
    expect(result.current.segments).toHaveLength(1);
    rerender({ sh: true });
    await waitFor(() => expect(result.current.segments).toHaveLength(2));
  });

  it("does not fetch when no project is selected", async () => {
    fetchSegments.mockResolvedValue([]);
    const { rerender } = renderHook(
      ({ sh }) => useProjectSelection("claude", sh),
      { initialProps: { sh: false } }
    );
    rerender({ sh: true });
    rerender({ sh: false });
    expect(fetchSegments).not.toHaveBeenCalled();
    expect(fetchSegmentsWithHidden).not.toHaveBeenCalled();
  });
});

describe("useProjectSelection — resetAll", () => {
  it("clears all state", async () => {
    fetchSegments.mockResolvedValue([{ id: "a" }]);
    const { result } = renderHook(() => useProjectSelection("claude", false));
    await act(async () => {
      await result.current.handleSelectProject("p1");
    });
    act(() => {
      result.current.resetAll();
    });
    expect(result.current.selectedProject).toBeNull();
    expect(result.current.segments).toEqual([]);
  });
});
