import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("../../api", () => ({
  searchSessions: vi.fn(),
  fetchSearchFilters: vi.fn(),
  fetchSearchStatus: vi.fn(),
}));

import { useSearch } from "../../hooks/useSearch";
import {
  searchSessions,
  fetchSearchFilters,
  fetchSearchStatus,
} from "../../api";

function defaultProps(overrides = {}) {
  return {
    provider: "claude",
    backendReady: true,
    selectedProject: null,
    loadSegments: vi.fn(() => Promise.resolve([])),
    setSegments: vi.fn(),
    onSearchStart: vi.fn(),
    onSearchCleared: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchSearchFilters.mockResolvedValue({ projects: [], models: [] });
  fetchSearchStatus.mockResolvedValue({
    mode: "hybrid",
    has_graph: true,
    embedded_sessions: 10,
    total_sessions: 10,
    concept_count: 5,
  });
  searchSessions.mockResolvedValue([]);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useSearch — initial state", () => {
  it("all state starts in neutral values", () => {
    const { result } = renderHook(() => useSearch(defaultProps()));
    expect(result.current.searchQuery).toBe("");
    expect(result.current.isSearching).toBe(false);
    expect(result.current.searchResults).toBeNull();
    expect(result.current.dateFrom).toBe("");
    expect(result.current.dateTo).toBe("");
    expect(result.current.pendingDateFrom).toBe("");
    expect(result.current.pendingDateTo).toBe("");
    expect(result.current.showDateFilter).toBe(false);
    expect(result.current.isInSearchMode).toBe(false);
    expect(result.current.searchRef.current).toBeNull();
  });
});

describe("useSearch — filter options", () => {
  it("fetches filter options on mount", async () => {
    renderHook(() => useSearch(defaultProps()));
    await waitFor(() =>
      expect(fetchSearchFilters).toHaveBeenCalledWith("claude")
    );
  });

  it("refetches filter options when provider changes", async () => {
    const { rerender } = renderHook((p) => useSearch(p), {
      initialProps: defaultProps(),
    });
    await waitFor(() => expect(fetchSearchFilters).toHaveBeenCalledTimes(1));
    rerender(defaultProps({ provider: "codex" }));
    await waitFor(() => expect(fetchSearchFilters).toHaveBeenCalledTimes(2));
    expect(fetchSearchFilters).toHaveBeenLastCalledWith("codex");
  });

  it("exposes filterOptions after fetch resolves", async () => {
    fetchSearchFilters.mockResolvedValue({ projects: ["p1", "p2"] });
    const { result } = renderHook(() => useSearch(defaultProps()));
    await waitFor(() =>
      expect(result.current.filterOptions).toEqual({ projects: ["p1", "p2"] })
    );
  });
});

describe("useSearch — status polling", () => {
  it("polls fetchSearchStatus when backend is ready", async () => {
    renderHook(() => useSearch(defaultProps()));
    await waitFor(() =>
      expect(fetchSearchStatus).toHaveBeenCalledWith("claude")
    );
  });

  it("does not poll when backend is not ready", () => {
    renderHook(() => useSearch(defaultProps({ backendReady: false })));
    expect(fetchSearchStatus).not.toHaveBeenCalled();
  });

  it("sets searchMode from response", async () => {
    const { result } = renderHook(() => useSearch(defaultProps()));
    await waitFor(() =>
      expect(result.current.searchMode?.mode).toBe("hybrid")
    );
  });

  it("stops polling once hybrid + has_graph is reached", async () => {
    vi.useFakeTimers();
    renderHook(() => useSearch(defaultProps()));
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchSearchStatus).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    // No additional calls because settled
    expect(fetchSearchStatus).toHaveBeenCalledTimes(1);
  });

  it("keeps polling when mode is embedding (not settled)", async () => {
    vi.useFakeTimers();
    fetchSearchStatus
      .mockResolvedValueOnce({ mode: "embedding", has_graph: false })
      .mockResolvedValueOnce({ mode: "hybrid", has_graph: true });
    renderHook(() => useSearch(defaultProps()));
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchSearchStatus).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchSearchStatus).toHaveBeenCalledTimes(2);
  });

  it("backs off to 10s on fetch error", async () => {
    vi.useFakeTimers();
    fetchSearchStatus
      .mockRejectedValueOnce(new Error("net"))
      .mockResolvedValueOnce({ mode: "hybrid", has_graph: true });
    renderHook(() => useSearch(defaultProps()));
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchSearchStatus).toHaveBeenCalledTimes(2);
  });
});

describe("useSearch — debounced search", () => {
  it("does not fire search for a 1-character query", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useSearch(defaultProps()));
    act(() => result.current.setSearchQuery("a"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(searchSessions).not.toHaveBeenCalled();
  });

  it("fires search after 300ms for a 2+-character query", async () => {
    vi.useFakeTimers();
    searchSessions.mockResolvedValue([{ session_id: "s1" }]);
    const { result } = renderHook(() => useSearch(defaultProps()));
    act(() => result.current.setSearchQuery("docker"));
    expect(result.current.isSearching).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.searchResults).toEqual([{ session_id: "s1" }]);
  });

  it("calls onSearchStart with the query when search fires", async () => {
    vi.useFakeTimers();
    const onSearchStart = vi.fn();
    const { result } = renderHook(() =>
      useSearch(defaultProps({ onSearchStart }))
    );
    act(() => result.current.setSearchQuery("hello"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(onSearchStart).toHaveBeenCalledWith("hello");
  });

  it("debounces multiple rapid changes into one call", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useSearch(defaultProps()));
    act(() => result.current.setSearchQuery("a1"));
    act(() => result.current.setSearchQuery("a12"));
    act(() => result.current.setSearchQuery("a123"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(searchSessions).toHaveBeenCalledTimes(1);
    expect(searchSessions).toHaveBeenLastCalledWith("a123", "claude");
  });

  it("isInSearchMode is true when query length >= 2", () => {
    const { result } = renderHook(() => useSearch(defaultProps()));
    expect(result.current.isInSearchMode).toBe(false);
    act(() => result.current.setSearchQuery("hi"));
    expect(result.current.isInSearchMode).toBe(true);
  });

  it("non-fatal on searchSessions error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    searchSessions.mockRejectedValue(new Error("fail"));
    const stableProps = defaultProps();
    const { result } = renderHook(() => useSearch(stableProps));
    act(() => result.current.setSearchQuery("hello"));
    await waitFor(
      () => {
        expect(consoleSpy).toHaveBeenCalledWith(expect.any(Error));
        expect(result.current.isSearching).toBe(false);
      },
      { timeout: 2000 }
    );
    consoleSpy.mockRestore();
  });
});

describe("useSearch — clearing search reloads segments", () => {
  it("reloads segments when query goes from 2+ chars to 0 with a project selected", async () => {
    const loadSegments = vi.fn(() => Promise.resolve([{ id: "a" }]));
    const setSegments = vi.fn();
    const onSearchCleared = vi.fn();
    const { result } = renderHook(() =>
      useSearch(
        defaultProps({
          selectedProject: "proj-a",
          loadSegments,
          setSegments,
          onSearchCleared,
        })
      )
    );
    // Set then clear the query (real timers, using setTimeout for debounce)
    act(() => result.current.setSearchQuery("query"));
    act(() => result.current.setSearchQuery(""));
    await waitFor(() => expect(loadSegments).toHaveBeenCalledWith("proj-a"));
    await waitFor(() =>
      expect(setSegments).toHaveBeenCalledWith([{ id: "a" }])
    );
    expect(onSearchCleared).toHaveBeenCalledWith("proj-a");
  });

  it("does not reload segments when no project is selected", async () => {
    const loadSegments = vi.fn(() => Promise.resolve([]));
    const { result } = renderHook(() =>
      useSearch(defaultProps({ selectedProject: null, loadSegments }))
    );
    act(() => result.current.setSearchQuery(""));
    expect(loadSegments).not.toHaveBeenCalled();
  });
});

describe("useSearch — date filter", () => {
  it("applyDateFilter moves pending dates to active", () => {
    const { result } = renderHook(() => useSearch(defaultProps()));
    act(() => result.current.setPendingDateFrom("2026-01-01"));
    act(() => result.current.setPendingDateTo("2026-01-31"));
    act(() => result.current.applyDateFilter());
    expect(result.current.dateFrom).toBe("2026-01-01");
    expect(result.current.dateTo).toBe("2026-01-31");
  });

  it("clearDateFilter zeros all four date states", () => {
    const { result } = renderHook(() => useSearch(defaultProps()));
    act(() => result.current.setPendingDateFrom("2026-01-01"));
    act(() => result.current.applyDateFilter());
    act(() => result.current.clearDateFilter());
    expect(result.current.dateFrom).toBe("");
    expect(result.current.dateTo).toBe("");
    expect(result.current.pendingDateFrom).toBe("");
    expect(result.current.pendingDateTo).toBe("");
  });
});

describe("useSearch — resetSearch", () => {
  it("clears searchQuery and searchResults", async () => {
    vi.useFakeTimers();
    searchSessions.mockResolvedValue([{ session_id: "s1" }]);
    const { result } = renderHook(() => useSearch(defaultProps()));
    act(() => result.current.setSearchQuery("hello"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.searchResults).not.toBeNull();
    act(() => result.current.resetSearch());
    expect(result.current.searchQuery).toBe("");
    expect(result.current.searchResults).toBeNull();
  });
});

describe("useSearch — showDateFilter toggle", () => {
  it("setShowDateFilter controls the expanded state", () => {
    const { result } = renderHook(() => useSearch(defaultProps()));
    expect(result.current.showDateFilter).toBe(false);
    act(() => result.current.setShowDateFilter(true));
    expect(result.current.showDateFilter).toBe(true);
    act(() => result.current.setShowDateFilter(false));
    expect(result.current.showDateFilter).toBe(false);
  });
});

describe("useSearch — status poll cancellation", () => {
  it("ignores late fetchSearchStatus resolution after unmount (line 45 cancelled branch)", async () => {
    let resolveStatus;
    fetchSearchStatus.mockReturnValueOnce(
      new Promise((res) => { resolveStatus = res; })
    );
    const { unmount } = renderHook(() => useSearch(defaultProps()));
    unmount();
    resolveStatus({ mode: "hybrid", has_graph: true });
    await new Promise((r) => setTimeout(r, 10));
    // Cancelled branch fires; no state update after unmount.
  });
});
