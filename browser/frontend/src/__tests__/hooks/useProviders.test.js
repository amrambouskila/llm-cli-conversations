import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

vi.mock("../../api", () => ({
  fetchProviders: vi.fn(),
}));

import { useProviders } from "../../hooks/useProviders";
import { fetchProviders } from "../../api";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useProviders", () => {
  it("returns an empty array before the first fetch resolves", () => {
    fetchProviders.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useProviders());
    expect(result.current).toEqual([]);
  });

  it("returns the fetched provider list", async () => {
    const providers = [
      { id: "claude", name: "Claude", projects: 5 },
      { id: "codex", name: "Codex", projects: 2 },
    ];
    fetchProviders.mockResolvedValue(providers);
    const { result } = renderHook(() => useProviders());
    await waitFor(() => expect(result.current).toEqual(providers));
  });

  it("keeps the empty array on fetch error", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    fetchProviders.mockRejectedValue(new Error("network"));
    const { result } = renderHook(() => useProviders());
    await waitFor(() => expect(consoleSpy).toHaveBeenCalled());
    expect(result.current).toEqual([]);
    consoleSpy.mockRestore();
  });

  it("fires fetchProviders exactly once per mount", async () => {
    fetchProviders.mockResolvedValue([]);
    const { rerender } = renderHook(() => useProviders());
    await waitFor(() => expect(fetchProviders).toHaveBeenCalledTimes(1));
    rerender();
    expect(fetchProviders).toHaveBeenCalledTimes(1);
  });
});
