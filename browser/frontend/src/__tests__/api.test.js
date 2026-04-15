import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import * as api from "../api";

// The production `request()` helper is not exported; we exercise it through
// every wrapper + the two error branches (network error + HTTP non-ok).

describe("api — request helper error branches", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("rethrows a network error with a wrapped message", async () => {
    fetch.mockRejectedValue(new TypeError("connection refused"));
    await expect(api.fetchReady()).rejects.toThrow(
      /Network error: connection refused/i
    );
  });

  it("throws on HTTP non-ok with status + body text", async () => {
    fetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Server Error",
      text: () => Promise.resolve("internal error body"),
    });
    await expect(api.fetchReady()).rejects.toThrow(
      /HTTP 500: internal error body/i
    );
  });

  it("falls back to statusText when body read fails", async () => {
    fetch.mockResolvedValue({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      text: () => Promise.reject(new Error("read fail")),
    });
    await expect(api.fetchReady()).rejects.toThrow(/HTTP 503: Service Unavailable/);
  });

  it("returns the parsed JSON body on ok", async () => {
    fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ready: true }),
    });
    const result = await api.fetchReady();
    expect(result).toEqual({ ready: true });
  });
});

// ---------------------------------------------------------------------------
// Every exported wrapper hits the correct URL + method, passes path
// parameters through encodeURIComponent, and returns the parsed JSON.
// ---------------------------------------------------------------------------

describe("api — wrapper URL + method contracts", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ stub: true }),
      })
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const cases = [
    // [fn, args, expectedUrlMatch, expectedMethod?]
    [api.fetchReady, [], "/api/ready"],
    [api.fetchProviders, [], "/api/providers"],
    [api.fetchProjects, [], "/api/projects?provider=claude"],
    [api.fetchProjects, ["codex"], "/api/projects?provider=codex"],
    [api.fetchSegments, ["my-proj"], "/api/projects/my-proj/segments?provider=claude"],
    [
      api.fetchSegments,
      ["needs%20encoding/slash", "codex"],
      "/api/projects/needs%2520encoding%2Fslash/segments?provider=codex",
    ],
    [api.fetchSegmentDetail, ["seg-1"], "/api/segments/seg-1?provider=claude"],
    [
      api.fetchConversation,
      ["proj", "conv-1"],
      "/api/projects/proj/conversation/conv-1?provider=claude",
    ],
    [api.searchSegments, ["docker"], "/api/search?q=docker&provider=claude"],
    [api.searchSessions, ["docker"], "/api/search?q=docker&provider=claude"],
    [api.searchSessions, ["a b"], "/api/search?q=a%20b&provider=claude"],
    [api.fetchSearchFilters, [], "/api/search/filters?provider=claude"],
    [api.fetchSearchStatus, ["codex"], "/api/search/status?provider=codex"],
    [api.fetchRelatedSessions, ["s1"], "/api/sessions/s1/related"],
    [api.fetchStats, ["claude"], "/api/stats?provider=claude"],
    [api.triggerUpdate, [], "/api/update", "POST"],
    [api.requestSummary, ["seg1"], "/api/summary/seg1?provider=claude", "POST"],
    [api.getSummary, ["seg1"], "/api/summary/seg1"],
    [api.deleteSummary, ["seg1"], "/api/summary/seg1", "DELETE"],
    [
      api.requestConvSummary,
      ["proj", "conv-1"],
      "/api/summary/conversation/proj/conv-1?provider=claude",
      "POST",
    ],
    [
      api.getConvSummary,
      ["proj", "conv-1"],
      "/api/summary/conversation/proj/conv-1",
    ],
    [api.fetchSummaryTitles, [], "/api/summary/titles"],
    [api.hideSegment, ["s1"], "/api/hide/segment/s1", "POST"],
    [api.restoreSegment, ["s1"], "/api/restore/segment/s1", "POST"],
    [
      api.hideConversation,
      ["proj", "c1"],
      "/api/hide/conversation/proj/c1",
      "POST",
    ],
    [
      api.restoreConversation,
      ["proj", "c1"],
      "/api/restore/conversation/proj/c1",
      "POST",
    ],
    [api.hideProject, ["proj"], "/api/hide/project/proj", "POST"],
    [api.restoreProject, ["proj"], "/api/restore/project/proj", "POST"],
    [api.restoreAll, [], "/api/restore/all", "POST"],
    [api.fetchHidden, [], "/api/hidden"],
    [api.fetchProjectsWithHidden, [], "/api/projects?show_hidden=true&provider=claude"],
    [
      api.fetchSegmentsWithHidden,
      ["proj"],
      "/api/projects/proj/segments?show_hidden=true&provider=claude",
    ],
    [api.fetchDashboardGraph, [], "/api/dashboard/graph?"],
    [api.fetchDashboardGraphStatus, [], "/api/dashboard/graph/status"],
    [api.triggerDashboardGraphGenerate, [], "/api/dashboard/graph/generate", "POST"],
    [api.importDashboardGraph, [], "/api/dashboard/graph/import", "POST"],
    [api.fetchSessionCostBreakdown, ["s1"], "/api/sessions/s1/cost-breakdown"],
    [api.fetchWikiIndex, [], "/api/graph/wiki/index"],
    [api.fetchWikiArticle, ["Community_1"], "/api/graph/wiki/Community_1"],
    [
      api.fetchWikiArticle,
      ["needs encoding/slash"],
      "/api/graph/wiki/needs%20encoding%2Fslash",
    ],
  ];

  it.each(cases)(
    "%o calls fetch with the expected URL and method",
    async (fn, args, expectedUrl, method = undefined) => {
      const result = await fn(...args);
      expect(result).toEqual({ stub: true });
      expect(fetch).toHaveBeenCalled();
      const [url, opts] = fetch.mock.calls[0];
      expect(url).toContain(expectedUrl);
      if (method) {
        expect(opts?.method).toBe(method);
      } else {
        // Default GET — either no opts object or no method specified
        expect(opts?.method).toBeUndefined();
      }
    }
  );
});

// ---------------------------------------------------------------------------
// Dashboard wrappers forward their params into the query string
// ---------------------------------------------------------------------------

describe("api — dashboard wrappers serialize params", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      })
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const dashboards = [
    [api.fetchDashboardSummary, "summary"],
    [api.fetchDashboardCostOverTime, "cost-over-time"],
    [api.fetchDashboardProjects, "projects"],
    [api.fetchDashboardTools, "tools"],
    [api.fetchDashboardModels, "models"],
    [api.fetchDashboardSessionTypes, "session-types"],
    [api.fetchDashboardHeatmap, "heatmap"],
    [api.fetchDashboardAnomalies, "anomalies"],
    [api.fetchDashboardTopExpensiveSessions, "top-expensive-sessions"],
  ];

  it.each(dashboards)(
    "%o builds the %s endpoint URL and includes the params",
    async (fn, slug) => {
      await fn({ provider: "claude", project: "p1" });
      const url = fetch.mock.calls[0][0];
      expect(url).toContain(`/api/dashboard/${slug}?`);
      expect(url).toContain("provider=claude");
      expect(url).toContain("project=p1");
    }
  );

  it("defaults to empty params when no object is passed", async () => {
    await api.fetchDashboardSummary();
    const url = fetch.mock.calls[0][0];
    expect(url).toMatch(/\/api\/dashboard\/summary\?$/);
  });
});

// ---------------------------------------------------------------------------
// fetchSessionCostBreakdown forwards the options bag
// ---------------------------------------------------------------------------

describe("api — fetchSessionCostBreakdown options", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      })
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("passes an AbortSignal through the options", async () => {
    const controller = new AbortController();
    await api.fetchSessionCostBreakdown("s1", { signal: controller.signal });
    const [, opts] = fetch.mock.calls[0];
    expect(opts?.signal).toBe(controller.signal);
  });
});

describe("api — wiki fetchers (Phase 8)", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ stub: true }),
      })
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetchWikiIndex forwards options.signal", async () => {
    const controller = new AbortController();
    await api.fetchWikiIndex({ signal: controller.signal });
    expect(fetch.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it("fetchWikiArticle forwards options.signal", async () => {
    const controller = new AbortController();
    await api.fetchWikiArticle("Community_1", { signal: controller.signal });
    expect(fetch.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it("resolveWikiSlug serializes both concept_id and concept_name when present", async () => {
    await api.resolveWikiSlug({ conceptId: "c1", conceptName: "docker" });
    const url = fetch.mock.calls[0][0];
    expect(url).toContain("/api/graph/wiki/lookup?");
    expect(url).toContain("concept_id=c1");
    expect(url).toContain("concept_name=docker");
  });

  it("resolveWikiSlug omits concept_id when null", async () => {
    await api.resolveWikiSlug({ conceptName: "docker" });
    const url = fetch.mock.calls[0][0];
    expect(url).toContain("concept_name=docker");
    expect(url).not.toContain("concept_id");
  });

  it("resolveWikiSlug omits concept_name when null", async () => {
    await api.resolveWikiSlug({ conceptId: "c1" });
    const url = fetch.mock.calls[0][0];
    expect(url).toContain("concept_id=c1");
    expect(url).not.toContain("concept_name");
  });

  it("resolveWikiSlug forwards options.signal", async () => {
    const controller = new AbortController();
    await api.resolveWikiSlug(
      { conceptName: "x" },
      { signal: controller.signal },
    );
    expect(fetch.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it("resolveWikiSlug returns the parsed JSON body", async () => {
    const result = await api.resolveWikiSlug({ conceptName: "x" });
    expect(result).toEqual({ stub: true });
  });
});
