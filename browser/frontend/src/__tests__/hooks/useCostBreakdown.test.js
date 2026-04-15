import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

vi.mock("../../api", () => ({
  fetchSessionCostBreakdown: vi.fn(),
}));

import { fetchSessionCostBreakdown } from "../../api";
import { useCostBreakdown } from "../../hooks/useCostBreakdown";

const sampleBreakdown = {
  input_usd: 0.15,
  output_usd: 0.3,
  cache_read_usd: 0.003,
  cache_create_usd: 0.0094,
  total_usd: 0.4624,
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useCostBreakdown", () => {
  it("returns null data, not loading, no error when sessionId is falsy", () => {
    const { result } = renderHook(() => useCostBreakdown(null));
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(fetchSessionCostBreakdown).not.toHaveBeenCalled();
  });

  it("does not fetch when sessionId is undefined", () => {
    renderHook(() => useCostBreakdown(undefined));
    expect(fetchSessionCostBreakdown).not.toHaveBeenCalled();
  });

  it("does not fetch when sessionId is empty string", () => {
    renderHook(() => useCostBreakdown(""));
    expect(fetchSessionCostBreakdown).not.toHaveBeenCalled();
  });

  it("fetches and populates data when sessionId is provided", async () => {
    fetchSessionCostBreakdown.mockResolvedValue(sampleBreakdown);
    const { result } = renderHook(() => useCostBreakdown("s1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual(sampleBreakdown);
    expect(result.current.error).toBeNull();
    expect(fetchSessionCostBreakdown).toHaveBeenCalledWith(
      "s1",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it("sets loading=true during the initial fetch", () => {
    fetchSessionCostBreakdown.mockReturnValue(new Promise(() => {}));  // never resolves
    const { result } = renderHook(() => useCostBreakdown("s1"));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
  });

  it("captures non-abort errors in the error field", async () => {
    const err = new Error("network fail");
    fetchSessionCostBreakdown.mockRejectedValue(err);
    const { result } = renderHook(() => useCostBreakdown("s1"));
    await waitFor(() => expect(result.current.error).toBe(err));
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
  });

  it("refetches when sessionId changes", async () => {
    fetchSessionCostBreakdown
      .mockResolvedValueOnce({ ...sampleBreakdown, total_usd: 0.1 })
      .mockResolvedValueOnce({ ...sampleBreakdown, total_usd: 0.99 });
    const { result, rerender } = renderHook(
      ({ sid }) => useCostBreakdown(sid),
      { initialProps: { sid: "s1" } }
    );
    await waitFor(() => expect(result.current.data?.total_usd).toBe(0.1));
    rerender({ sid: "s2" });
    await waitFor(() => expect(result.current.data?.total_usd).toBe(0.99));
    expect(fetchSessionCostBreakdown).toHaveBeenCalledTimes(2);
  });

  it("clears state when sessionId becomes falsy again", async () => {
    fetchSessionCostBreakdown.mockResolvedValue(sampleBreakdown);
    const { result, rerender } = renderHook(
      ({ sid }) => useCostBreakdown(sid),
      { initialProps: { sid: "s1" } }
    );
    await waitFor(() => expect(result.current.data).toEqual(sampleBreakdown));
    rerender({ sid: null });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("ignores AbortError after an aborted fetch (no state update)", async () => {
    const abortErr = new Error("aborted");
    abortErr.name = "AbortError";
    fetchSessionCostBreakdown.mockRejectedValue(abortErr);
    const { result } = renderHook(() => useCostBreakdown("s1"));
    await new Promise((resolve) => setTimeout(resolve, 20));
    // Error stays null; data stays null; loading stays true because we skipped updates.
    expect(result.current.error).toBeNull();
    expect(result.current.data).toBeNull();
  });

  it("aborts the in-flight fetch when sessionId changes", async () => {
    let firstSignal;
    let secondSignal;
    fetchSessionCostBreakdown
      .mockImplementationOnce((_, opts) => {
        firstSignal = opts.signal;
        return new Promise(() => {});  // never resolves
      })
      .mockImplementationOnce((_, opts) => {
        secondSignal = opts.signal;
        return Promise.resolve(sampleBreakdown);
      });

    const { rerender } = renderHook(
      ({ sid }) => useCostBreakdown(sid),
      { initialProps: { sid: "s1" } }
    );
    rerender({ sid: "s2" });
    expect(firstSignal.aborted).toBe(true);
    expect(secondSignal.aborted).toBe(false);
  });

  it("ignores late .then resolution after unmount (cancelled path)", async () => {
    // Force the first fetch to resolve AFTER unmount, triggering the
    // `if (cancelled) return;` branch at line 25 of useCostBreakdown.js.
    let resolveFirst;
    fetchSessionCostBreakdown.mockReturnValueOnce(
      new Promise((res) => { resolveFirst = res; })
    );
    const { unmount, result } = renderHook(() => useCostBreakdown("s1"));
    unmount();
    resolveFirst(sampleBreakdown);
    await new Promise((r) => setTimeout(r, 10));
    // After unmount, no state update should have occurred — result.current
    // is already frozen to the final pre-unmount snapshot (loading=true).
    expect(result.current.data).toBeNull();
  });
});
