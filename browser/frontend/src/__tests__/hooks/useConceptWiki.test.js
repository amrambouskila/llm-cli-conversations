import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

vi.mock("../../api", () => ({
  fetchWikiIndex: vi.fn(),
  fetchWikiArticle: vi.fn(),
  resolveWikiSlug: vi.fn(),
}));

import {
  fetchWikiArticle,
  fetchWikiIndex,
  resolveWikiSlug,
} from "../../api";
import { useConceptWiki } from "../../hooks/useConceptWiki";

const sampleIndex = {
  title: "Knowledge Graph Index",
  markdown: "# Knowledge Graph Index\n",
  articles: [
    { slug: "Community_1", title: "Community 1", kind: "community" },
    { slug: "docker", title: "docker", kind: "god_node" },
  ],
};

const sampleArticle = {
  slug: "docker",
  title: "Docker",
  markdown: "# Docker\n\nBody.",
};

beforeEach(() => {
  vi.clearAllMocks();
  fetchWikiIndex.mockResolvedValue(sampleIndex);
  fetchWikiArticle.mockResolvedValue(sampleArticle);
  resolveWikiSlug.mockResolvedValue({ slug: "docker" });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useConceptWiki — initial load", () => {
  it("initial state is empty (no article, no breadcrumb, not loading)", () => {
    fetchWikiIndex.mockReturnValue(new Promise(() => {})); // pending
    const { result } = renderHook(() => useConceptWiki("claude"));
    expect(result.current.article).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.breadcrumb).toEqual([]);
    expect(result.current.selectedSlug).toBeNull();
  });

  it("loads the wiki index on mount", async () => {
    const { result } = renderHook(() => useConceptWiki("claude"));
    await waitFor(() => expect(result.current.index).toEqual(sampleIndex));
    expect(result.current.indexError).toBeNull();
  });

  it("captures index load failures in indexError", async () => {
    const err = new Error("404");
    fetchWikiIndex.mockRejectedValue(err);
    const { result } = renderHook(() => useConceptWiki("claude"));
    await waitFor(() => expect(result.current.indexError).toBe(err));
    expect(result.current.index).toBeNull();
  });

  it("re-fetches the index when provider changes", async () => {
    const { rerender } = renderHook(({ p }) => useConceptWiki(p), {
      initialProps: { p: "claude" },
    });
    await waitFor(() => expect(fetchWikiIndex).toHaveBeenCalledTimes(1));
    rerender({ p: "codex" });
    await waitFor(() => expect(fetchWikiIndex).toHaveBeenCalledTimes(2));
  });

  it("ignores late index resolution after unmount", async () => {
    let resolveIndex;
    fetchWikiIndex.mockReturnValueOnce(
      new Promise((res) => {
        resolveIndex = res;
      }),
    );
    const { unmount, result } = renderHook(() => useConceptWiki("claude"));
    unmount();
    resolveIndex(sampleIndex);
    await new Promise((r) => setTimeout(r, 10));
    expect(result.current.index).toBeNull();
  });

  it("ignores late index error after unmount", async () => {
    let rejectIndex;
    fetchWikiIndex.mockReturnValueOnce(
      new Promise((_, rej) => {
        rejectIndex = rej;
      }),
    );
    const { unmount, result } = renderHook(() => useConceptWiki("claude"));
    unmount();
    rejectIndex(new Error("late 404"));
    await new Promise((r) => setTimeout(r, 10));
    expect(result.current.indexError).toBeNull();
  });
});

describe("useConceptWiki — openSlug + article fetch", () => {
  it("openSlug(slug) sets selectedSlug and fetches the article", async () => {
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("docker");
    });
    expect(result.current.selectedSlug).toBe("docker");
    await waitFor(() => expect(result.current.article).toEqual(sampleArticle));
    expect(fetchWikiArticle).toHaveBeenCalledWith(
      "docker",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("openSlug(null) is a no-op", () => {
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug(null);
    });
    expect(result.current.selectedSlug).toBeNull();
    expect(fetchWikiArticle).not.toHaveBeenCalled();
  });

  it("openSlug with the same slug as current is a no-op (no breadcrumb push)", async () => {
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("docker");
    });
    await waitFor(() => expect(result.current.article).toEqual(sampleArticle));
    act(() => {
      result.current.openSlug("docker");
    });
    expect(result.current.breadcrumb).toEqual([]);
  });

  it("openSlug with a new slug pushes the previous selectedSlug onto the breadcrumb", async () => {
    fetchWikiArticle.mockResolvedValueOnce({ ...sampleArticle, slug: "docker" });
    fetchWikiArticle.mockResolvedValueOnce({ ...sampleArticle, slug: "k8s", title: "K8s" });
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("docker");
    });
    await waitFor(() => expect(result.current.article?.slug).toBe("docker"));
    act(() => {
      result.current.openSlug("k8s");
    });
    expect(result.current.breadcrumb).toEqual(["docker"]);
    await waitFor(() => expect(result.current.article?.slug).toBe("k8s"));
  });

  it("loading is true while the article fetch is pending", () => {
    fetchWikiArticle.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("docker");
    });
    expect(result.current.loading).toBe(true);
    expect(result.current.article).toBeNull();
  });

  it("captures non-abort article fetch errors", async () => {
    const err = new Error("boom");
    fetchWikiArticle.mockRejectedValue(err);
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("docker");
    });
    await waitFor(() => expect(result.current.error).toBe(err));
    expect(result.current.loading).toBe(false);
    expect(result.current.article).toBeNull();
  });

  it("ignores AbortError on article fetch (no state update)", async () => {
    const abortErr = new Error("aborted");
    abortErr.name = "AbortError";
    fetchWikiArticle.mockRejectedValue(abortErr);
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("docker");
    });
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current.error).toBeNull();
    expect(result.current.article).toBeNull();
  });

  it("aborts in-flight article fetch when slug changes", async () => {
    let firstSignal;
    let secondSignal;
    fetchWikiArticle
      .mockImplementationOnce((_, opts) => {
        firstSignal = opts.signal;
        return new Promise(() => {});
      })
      .mockImplementationOnce((_, opts) => {
        secondSignal = opts.signal;
        return Promise.resolve(sampleArticle);
      });
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("docker");
    });
    act(() => {
      result.current.openSlug("k8s");
    });
    expect(firstSignal.aborted).toBe(true);
    expect(secondSignal.aborted).toBe(false);
  });
});

describe("useConceptWiki — goBack + jumpToBreadcrumb + close", () => {
  it("goBack pops the last breadcrumb entry into selectedSlug", async () => {
    fetchWikiArticle
      .mockResolvedValueOnce({ ...sampleArticle, slug: "a", title: "A" })
      .mockResolvedValueOnce({ ...sampleArticle, slug: "b", title: "B" })
      .mockResolvedValueOnce({ ...sampleArticle, slug: "a", title: "A" });
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("a");
    });
    await waitFor(() => expect(result.current.article?.slug).toBe("a"));
    act(() => {
      result.current.openSlug("b");
    });
    await waitFor(() => expect(result.current.article?.slug).toBe("b"));
    expect(result.current.breadcrumb).toEqual(["a"]);

    act(() => {
      result.current.goBack();
    });
    expect(result.current.selectedSlug).toBe("a");
    expect(result.current.breadcrumb).toEqual([]);
  });

  it("goBack with empty breadcrumb is a no-op", () => {
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.goBack();
    });
    expect(result.current.selectedSlug).toBeNull();
    expect(result.current.breadcrumb).toEqual([]);
  });

  it("jumpToBreadcrumb truncates forward history (browser-back semantics)", async () => {
    fetchWikiArticle
      .mockResolvedValueOnce({ ...sampleArticle, slug: "a" })
      .mockResolvedValueOnce({ ...sampleArticle, slug: "b" })
      .mockResolvedValueOnce({ ...sampleArticle, slug: "c" })
      .mockResolvedValueOnce({ ...sampleArticle, slug: "a" });
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("a");
    });
    await waitFor(() => expect(result.current.article?.slug).toBe("a"));
    act(() => {
      result.current.openSlug("b");
    });
    await waitFor(() => expect(result.current.article?.slug).toBe("b"));
    act(() => {
      result.current.openSlug("c");
    });
    await waitFor(() => expect(result.current.article?.slug).toBe("c"));
    expect(result.current.breadcrumb).toEqual(["a", "b"]);

    act(() => {
      result.current.jumpToBreadcrumb(0);
    });
    expect(result.current.selectedSlug).toBe("a");
    expect(result.current.breadcrumb).toEqual([]);
  });

  it("jumpToBreadcrumb with out-of-range index is a no-op", () => {
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.jumpToBreadcrumb(5);
    });
    expect(result.current.selectedSlug).toBeNull();

    act(() => {
      result.current.jumpToBreadcrumb(-1);
    });
    expect(result.current.selectedSlug).toBeNull();
  });

  it("close() clears selectedSlug, breadcrumb, and lets article state settle to null", async () => {
    const { result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("docker");
    });
    await waitFor(() => expect(result.current.article).toEqual(sampleArticle));

    act(() => {
      result.current.close();
    });
    expect(result.current.selectedSlug).toBeNull();
    expect(result.current.breadcrumb).toEqual([]);
    await waitFor(() => expect(result.current.article).toBeNull());
    expect(result.current.loading).toBe(false);
  });
});

describe("useConceptWiki — openByConcept", () => {
  it("openByConcept resolves the slug and opens the article", async () => {
    resolveWikiSlug.mockResolvedValue({ slug: "Community_1" });
    fetchWikiArticle.mockResolvedValue({
      ...sampleArticle,
      slug: "Community_1",
      title: "Community 1",
    });
    const { result } = renderHook(() => useConceptWiki("claude"));
    await act(async () => {
      await result.current.openByConcept({
        conceptId: "c1",
        conceptName: "docker",
      });
    });
    expect(resolveWikiSlug).toHaveBeenCalledWith({
      conceptId: "c1",
      conceptName: "docker",
    });
    await waitFor(() =>
      expect(result.current.article?.slug).toBe("Community_1"),
    );
  });

  it("openByConcept silently no-ops when resolveWikiSlug rejects", async () => {
    resolveWikiSlug.mockRejectedValue(new Error("404"));
    const { result } = renderHook(() => useConceptWiki("claude"));
    await act(async () => {
      await result.current.openByConcept({ conceptName: "missing" });
    });
    expect(result.current.selectedSlug).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("openByConcept silently no-ops when resolveWikiSlug returns no slug", async () => {
    resolveWikiSlug.mockResolvedValue({});
    const { result } = renderHook(() => useConceptWiki("claude"));
    await act(async () => {
      await result.current.openByConcept({ conceptName: "x" });
    });
    expect(result.current.selectedSlug).toBeNull();
  });

  it("openByConcept handles undefined response without crashing", async () => {
    resolveWikiSlug.mockResolvedValue(undefined);
    const { result } = renderHook(() => useConceptWiki("claude"));
    await act(async () => {
      await result.current.openByConcept({ conceptName: "x" });
    });
    expect(result.current.selectedSlug).toBeNull();
  });

  it("ignores late article fetch resolution after unmount (cancelled branch)", async () => {
    let resolveArticle;
    fetchWikiArticle.mockReturnValue(
      new Promise((res) => {
        resolveArticle = res;
      }),
    );
    const { unmount, result } = renderHook(() => useConceptWiki("claude"));
    act(() => {
      result.current.openSlug("docker");
    });
    unmount();
    // Resolve AFTER unmount — exercises `if (cancelled) return;` at
    // useConceptWiki.js:60 inside the .then callback.
    resolveArticle({ slug: "docker", title: "Docker", markdown: "x" });
    await new Promise((r) => setTimeout(r, 10));
    expect(result.current.article).toBeNull();
  });
});
