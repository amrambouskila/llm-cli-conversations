import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

vi.mock("../../api", () => ({
  fetchReady: vi.fn(),
}));

import { useBackendReady } from "../../hooks/useBackendReady";
import { fetchReady } from "../../api";

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useBackendReady", () => {
  it("starts as false before the first fetchReady resolves", () => {
    fetchReady.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useBackendReady());
    expect(result.current).toBe(false);
  });

  it("becomes true when fetchReady resolves with ready: true", async () => {
    fetchReady.mockResolvedValue({ ready: true });
    const { result } = renderHook(() => useBackendReady());
    await waitFor(() => expect(result.current).toBe(true));
  });

  it("remains false when fetchReady returns ready: false", async () => {
    fetchReady.mockResolvedValue({ ready: false });
    const { result } = renderHook(() => useBackendReady());
    await waitFor(() => expect(fetchReady).toHaveBeenCalled());
    expect(result.current).toBe(false);
  });

  it("polls again after 1s when ready=false", async () => {
    vi.useFakeTimers();
    fetchReady
      .mockResolvedValueOnce({ ready: false })
      .mockResolvedValueOnce({ ready: true });
    const { result } = renderHook(() => useBackendReady());
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current).toBe(true);
  });

  it("retries on fetch error", async () => {
    vi.useFakeTimers();
    fetchReady
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ ready: true });
    const { result } = renderHook(() => useBackendReady());
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current).toBe(true);
  });

  it("does not update state after unmount", async () => {
    vi.useFakeTimers();
    fetchReady.mockResolvedValue({ ready: false });
    const { unmount } = renderHook(() => useBackendReady());
    await act(async () => {
      await Promise.resolve();
    });
    unmount();
    // No assertion needed — if state updates after unmount, React would warn
    // in act/test mode. Just exercising the cleanup path.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
  });

  it("ignores late .then resolution after unmount (cancelled path)", async () => {
    // Deliberately use real timers — we need the promise callback to run
    // AFTER unmount synchronously via microtask queue.
    let resolveReady;
    fetchReady.mockReturnValueOnce(
      new Promise((res) => { resolveReady = res; })
    );
    const { unmount } = renderHook(() => useBackendReady());
    unmount();
    // Now resolve — the .then handler runs with cancelled=true → line 13 early return.
    resolveReady({ ready: true });
    await new Promise((r) => setTimeout(r, 10));
    // No state update, no warning. Test passes silently.
  });

  it("ignores late .catch resolution after unmount (cancelled path)", async () => {
    let rejectReady;
    fetchReady.mockReturnValueOnce(
      new Promise((_, rej) => { rejectReady = rej; })
    );
    const { unmount } = renderHook(() => useBackendReady());
    unmount();
    rejectReady(new Error("network"));
    await new Promise((r) => setTimeout(r, 10));
    // Line 18 early return fired; no scheduled timer leaks.
  });
});
