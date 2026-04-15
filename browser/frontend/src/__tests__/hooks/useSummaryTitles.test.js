import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("../../api", () => ({
  fetchSummaryTitles: vi.fn(),
}));

import { useSummaryTitles } from "../../hooks/useSummaryTitles";
import { fetchSummaryTitles } from "../../api";

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useSummaryTitles", () => {
  it("returns an empty object on mount before the first fetch resolves", () => {
    fetchSummaryTitles.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useSummaryTitles());
    expect(result.current.summaryTitles).toEqual({});
  });

  it("populates summaryTitles with the initial fetch", async () => {
    fetchSummaryTitles.mockResolvedValue({ seg1: "Title 1", seg2: "Title 2" });
    const { result } = renderHook(() => useSummaryTitles());
    await waitFor(() =>
      expect(result.current.summaryTitles).toEqual({
        seg1: "Title 1",
        seg2: "Title 2",
      })
    );
  });

  it("polls fetchSummaryTitles every 10 seconds", async () => {
    vi.useFakeTimers();
    fetchSummaryTitles.mockResolvedValue({});
    renderHook(() => useSummaryTitles());
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchSummaryTitles).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchSummaryTitles).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchSummaryTitles).toHaveBeenCalledTimes(3);
  });

  it("handleTitleReady adds a single title to the map", async () => {
    fetchSummaryTitles.mockResolvedValue({ existing: "X" });
    const { result } = renderHook(() => useSummaryTitles());
    await waitFor(() =>
      expect(result.current.summaryTitles.existing).toBe("X")
    );
    act(() => {
      result.current.handleTitleReady("new", "Fresh title");
    });
    expect(result.current.summaryTitles).toEqual({
      existing: "X",
      new: "Fresh title",
    });
  });

  it("handleTitleReady overwrites an existing key", async () => {
    fetchSummaryTitles.mockResolvedValue({ k: "old" });
    const { result } = renderHook(() => useSummaryTitles());
    await waitFor(() => expect(result.current.summaryTitles.k).toBe("old"));
    act(() => {
      result.current.handleTitleReady("k", "new");
    });
    expect(result.current.summaryTitles.k).toBe("new");
  });

  it("initial fetch errors are logged (non-fatal)", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    fetchSummaryTitles.mockRejectedValueOnce(new Error("boom"));
    renderHook(() => useSummaryTitles());
    await waitFor(() => expect(consoleSpy).toHaveBeenCalled());
    consoleSpy.mockRestore();
  });

  it("polling errors are silent (no console.error)", async () => {
    vi.useFakeTimers();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    fetchSummaryTitles
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error("transient"))
      .mockResolvedValueOnce({ ok: "yes" });
    const { result } = renderHook(() => useSummaryTitles());
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    // The polling error should NOT call console.error
    expect(consoleSpy).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(result.current.summaryTitles).toEqual({ ok: "yes" });
    consoleSpy.mockRestore();
  });

  it("clears the interval on unmount", () => {
    vi.useFakeTimers();
    fetchSummaryTitles.mockResolvedValue({});
    const { unmount } = renderHook(() => useSummaryTitles());
    unmount();
    vi.advanceTimersByTime(20_000);
    // If interval wasn't cleared, fetchSummaryTitles would fire multiple times
    expect(fetchSummaryTitles).toHaveBeenCalledTimes(1);
  });
});
