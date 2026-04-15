import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

vi.mock("../../api", () => ({
  hideSegment: vi.fn(() => Promise.resolve({ ok: true })),
  restoreSegment: vi.fn(() => Promise.resolve({ ok: true })),
  hideConversation: vi.fn(() => Promise.resolve({ ok: true })),
  restoreConversation: vi.fn(() => Promise.resolve({ ok: true })),
  hideProject: vi.fn(() => Promise.resolve({ ok: true })),
  restoreProject: vi.fn(() => Promise.resolve({ ok: true })),
  restoreAll: vi.fn(() => Promise.resolve({ ok: true })),
  fetchStats: vi.fn(() => Promise.resolve({})),
}));

import { useHideRestore } from "../../hooks/useHideRestore";
import {
  hideSegment,
  restoreSegment,
  hideConversation,
  restoreConversation,
  hideProject,
  restoreProject,
  restoreAll,
  fetchStats,
} from "../../api";

function defaultProps(overrides = {}) {
  return {
    provider: "claude",
    selectedProject: null,
    loadProjects: vi.fn(() => Promise.resolve([])),
    loadSegments: vi.fn(() => Promise.resolve([])),
    setProjects: vi.fn(),
    setStats: vi.fn(),
    setSegments: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchStats.mockResolvedValue({ total_projects: 0 });
});

describe("useHideRestore — refreshAfterStateChange", () => {
  it("fetches projects + stats and sets both", async () => {
    const setProjects = vi.fn();
    const setStats = vi.fn();
    fetchStats.mockResolvedValue({ total_projects: 5 });
    const loadProjects = vi.fn(() =>
      Promise.resolve([{ name: "a", stats: { last_timestamp: "2026-01-01" } }])
    );
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadProjects, setProjects, setStats }))
    );
    await act(async () => {
      await result.current.refreshAfterStateChange();
    });
    expect(loadProjects).toHaveBeenCalled();
    expect(fetchStats).toHaveBeenCalledWith("claude");
    expect(setProjects).toHaveBeenCalled();
    expect(setStats).toHaveBeenCalledWith({ total_projects: 5 });
  });

  it("sorts projects by last_timestamp descending", async () => {
    const setProjects = vi.fn();
    const loadProjects = vi.fn(() =>
      Promise.resolve([
        { name: "older", stats: { last_timestamp: "2026-01-01" } },
        { name: "newest", stats: { last_timestamp: "2026-03-01" } },
        { name: "middle", stats: { last_timestamp: "2026-02-01" } },
      ])
    );
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadProjects, setProjects }))
    );
    await act(async () => {
      await result.current.refreshAfterStateChange();
    });
    const sorted = setProjects.mock.calls[0][0];
    expect(sorted.map((p) => p.name)).toEqual(["newest", "middle", "older"]);
  });

  it("sort comparator tolerates projects with missing stats (lines 29-30)", async () => {
    const setProjects = vi.fn();
    const loadProjects = vi.fn(() =>
      Promise.resolve([
        { name: "no-stats-a", stats: undefined },
        { name: "with-ts", stats: { last_timestamp: "2026-03-01" } },
        { name: "no-stats-b", stats: undefined },
      ])
    );
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadProjects, setProjects }))
    );
    await act(async () => {
      await result.current.refreshAfterStateChange();
    });
    const sorted = setProjects.mock.calls[0][0];
    // Project with a real timestamp should come first; others come in some order
    expect(sorted[0].name).toBe("with-ts");
  });

  it("reloads segments when a project is selected", async () => {
    const setSegments = vi.fn();
    const loadSegments = vi.fn(() => Promise.resolve([{ id: "s1" }]));
    const { result } = renderHook(() =>
      useHideRestore(
        defaultProps({
          selectedProject: "p1",
          loadSegments,
          setSegments,
        })
      )
    );
    await act(async () => {
      await result.current.refreshAfterStateChange();
    });
    expect(loadSegments).toHaveBeenCalledWith("p1");
    expect(setSegments).toHaveBeenCalledWith([{ id: "s1" }]);
  });

  it("does not reload segments when no project is selected", async () => {
    const setSegments = vi.fn();
    const loadSegments = vi.fn();
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadSegments, setSegments }))
    );
    await act(async () => {
      await result.current.refreshAfterStateChange();
    });
    expect(loadSegments).not.toHaveBeenCalled();
    expect(setSegments).not.toHaveBeenCalled();
  });

  it("non-fatal on fetch error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const loadProjects = vi.fn(() => Promise.reject(new Error("boom")));
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadProjects }))
    );
    await act(async () => {
      await result.current.refreshAfterStateChange();
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});

describe("useHideRestore — segment handlers", () => {
  it("handleHideSegment calls hideSegment + refresh", async () => {
    const loadProjects = vi.fn(() => Promise.resolve([]));
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadProjects }))
    );
    await act(async () => {
      await result.current.handleHideSegment("seg1");
    });
    expect(hideSegment).toHaveBeenCalledWith("seg1");
    expect(loadProjects).toHaveBeenCalled();
  });

  it("handleRestoreSegment calls restoreSegment + refresh", async () => {
    const loadProjects = vi.fn(() => Promise.resolve([]));
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadProjects }))
    );
    await act(async () => {
      await result.current.handleRestoreSegment("seg1");
    });
    expect(restoreSegment).toHaveBeenCalledWith("seg1");
    expect(loadProjects).toHaveBeenCalled();
  });

  it("handleHideSegment is non-fatal on API error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    hideSegment.mockRejectedValueOnce(new Error("net"));
    const { result } = renderHook(() => useHideRestore(defaultProps()));
    await act(async () => {
      await result.current.handleHideSegment("seg1");
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it("handleRestoreSegment is non-fatal on API error (lines 70-71)", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    restoreSegment.mockRejectedValueOnce(new Error("net"));
    const { result } = renderHook(() => useHideRestore(defaultProps()));
    await act(async () => {
      await result.current.handleRestoreSegment("seg1");
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});

describe("useHideRestore — conversation handlers", () => {
  it("handleHideConversation is a no-op without selectedProject", async () => {
    const loadProjects = vi.fn(() => Promise.resolve([]));
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ selectedProject: null, loadProjects }))
    );
    await act(async () => {
      await result.current.handleHideConversation("conv1");
    });
    expect(hideConversation).not.toHaveBeenCalled();
    expect(loadProjects).not.toHaveBeenCalled();
  });

  it("handleHideConversation calls hideConversation with project + convId", async () => {
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ selectedProject: "p1" }))
    );
    await act(async () => {
      await result.current.handleHideConversation("conv1");
    });
    expect(hideConversation).toHaveBeenCalledWith("p1", "conv1");
  });

  it("handleRestoreConversation is a no-op without selectedProject", async () => {
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ selectedProject: null }))
    );
    await act(async () => {
      await result.current.handleRestoreConversation("conv1");
    });
    expect(restoreConversation).not.toHaveBeenCalled();
  });

  it("handleRestoreConversation calls restoreConversation", async () => {
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ selectedProject: "p2" }))
    );
    await act(async () => {
      await result.current.handleRestoreConversation("conv1");
    });
    expect(restoreConversation).toHaveBeenCalledWith("p2", "conv1");
  });

  it("handleHideConversation is non-fatal on API error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    hideConversation.mockRejectedValueOnce(new Error("bad"));
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ selectedProject: "p1" }))
    );
    await act(async () => {
      await result.current.handleHideConversation("c1");
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});

describe("useHideRestore — project handlers", () => {
  it("handleHideProject calls hideProject + refresh", async () => {
    const loadProjects = vi.fn(() => Promise.resolve([]));
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadProjects }))
    );
    await act(async () => {
      await result.current.handleHideProject("proj-a");
    });
    expect(hideProject).toHaveBeenCalledWith("proj-a");
    expect(loadProjects).toHaveBeenCalled();
  });

  it("handleRestoreProject calls restoreProject + refresh", async () => {
    const loadProjects = vi.fn(() => Promise.resolve([]));
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadProjects }))
    );
    await act(async () => {
      await result.current.handleRestoreProject("proj-a");
    });
    expect(restoreProject).toHaveBeenCalledWith("proj-a");
    expect(loadProjects).toHaveBeenCalled();
  });

  it("handleHideProject is non-fatal on API error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    hideProject.mockRejectedValueOnce(new Error("bad"));
    const { result } = renderHook(() => useHideRestore(defaultProps()));
    await act(async () => {
      await result.current.handleHideProject("p1");
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it("handleRestoreProject is non-fatal on API error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    restoreProject.mockRejectedValueOnce(new Error("bad"));
    const { result } = renderHook(() => useHideRestore(defaultProps()));
    await act(async () => {
      await result.current.handleRestoreProject("p1");
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});

describe("useHideRestore — restoreConversation error path", () => {
  it("handleRestoreConversation is non-fatal on API error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    restoreConversation.mockRejectedValueOnce(new Error("bad"));
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ selectedProject: "p1" }))
    );
    await act(async () => {
      await result.current.handleRestoreConversation("c1");
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});

describe("useHideRestore — restoreAll", () => {
  it("handleRestoreAll calls restoreAll + refresh", async () => {
    const loadProjects = vi.fn(() => Promise.resolve([]));
    const { result } = renderHook(() =>
      useHideRestore(defaultProps({ loadProjects }))
    );
    await act(async () => {
      await result.current.handleRestoreAll();
    });
    expect(restoreAll).toHaveBeenCalled();
    expect(loadProjects).toHaveBeenCalled();
  });

  it("handleRestoreAll is non-fatal on API error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    restoreAll.mockRejectedValueOnce(new Error("bad"));
    const { result } = renderHook(() => useHideRestore(defaultProps()));
    await act(async () => {
      await result.current.handleRestoreAll();
    });
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});
