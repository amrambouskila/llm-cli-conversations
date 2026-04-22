import { describe, it, expect } from "vitest";
import {
  shouldShowLabel,
  buildTooltipHtml,
  labelY,
  collisionRadius,
  collectCommunityIds,
} from "../components/ConceptGraph";

describe("shouldShowLabel", () => {
  it("shows a label when degree meets the threshold", () => {
    expect(shouldShowLabel({ degree: 5 }, 10, 0.5)).toBe(true);
    expect(shouldShowLabel({ degree: 10 }, 10, 0.5)).toBe(true);
  });

  it("hides a label when degree is below the threshold and session_count is low", () => {
    expect(shouldShowLabel({ degree: 1, session_count: 0 }, 10, 0.5)).toBe(
      false
    );
  });

  it("shows a label when session_count >= 3 even if degree is below threshold", () => {
    expect(shouldShowLabel({ degree: 1, session_count: 3 }, 10, 0.5)).toBe(
      true
    );
    expect(shouldShowLabel({ degree: 0, session_count: 10 }, 100, 0.9)).toBe(
      true
    );
  });

  it("falls back to 0 when degree is undefined (exercises `|| 0`)", () => {
    expect(shouldShowLabel({ session_count: 0 }, 10, 0.5)).toBe(false);
  });

  it("falls back to 0 when session_count is undefined (exercises `|| 0`)", () => {
    expect(shouldShowLabel({ degree: 0 }, 10, 0.5)).toBe(false);
  });

  it("handles a node missing both degree and session_count", () => {
    expect(shouldShowLabel({}, 10, 0.5)).toBe(false);
  });

  it("handles threshold 0 — everything shows", () => {
    expect(shouldShowLabel({ degree: 0, session_count: 0 }, 10, 0)).toBe(true);
  });
});

describe("buildTooltipHtml", () => {
  it("includes all four fields for a complete node", () => {
    const html = buildTooltipHtml({
      name: "Docker",
      type: "technology",
      community_id: 5,
      session_count: 12,
    });
    expect(html).toContain("<strong>Docker</strong>");
    expect(html).toContain("Type: technology");
    expect(html).toContain("Community: 5");
    expect(html).toContain("Sessions: 12");
  });

  it("falls back to N/A when type is missing (exercises `|| \"N/A\"`)", () => {
    const html = buildTooltipHtml({ name: "X", session_count: 1 });
    expect(html).toContain("Type: N/A");
  });

  it("falls back to N/A when community_id is null (exercises `?? \"N/A\"`)", () => {
    const html = buildTooltipHtml({
      name: "X",
      type: "t",
      community_id: null,
      session_count: 1,
    });
    expect(html).toContain("Community: N/A");
  });

  it("preserves community_id 0 (nullish-coalescing keeps falsy-but-defined)", () => {
    const html = buildTooltipHtml({
      name: "X",
      type: "t",
      community_id: 0,
      session_count: 1,
    });
    expect(html).toContain("Community: 0");
  });

  it("falls back to 0 when session_count is missing", () => {
    const html = buildTooltipHtml({ name: "X", type: "t", community_id: 1 });
    expect(html).toContain("Sessions: 0");
  });
});

describe("labelY", () => {
  const identityScale = (n) => n;

  it("returns y - sizeScale(degree) - 4 for a full node", () => {
    expect(labelY({ y: 100, degree: 10 }, identityScale)).toBe(86);
  });

  it("falls back to degree=1 when degree is undefined (exercises `|| 1`)", () => {
    expect(labelY({ y: 100 }, identityScale)).toBe(95);
  });

  it("handles degree=0 by falling back to 1", () => {
    expect(labelY({ y: 50, degree: 0 }, identityScale)).toBe(45);
  });
});

describe("collisionRadius", () => {
  const identityScale = (n) => n * 2;

  it("uses sizeScale when provided", () => {
    expect(collisionRadius(identityScale, 5, 3)).toBe(13); // 5*2 + 3
  });

  it("falls back to hard-coded 6 when sizeScale is null (settings-before-mount path)", () => {
    expect(collisionRadius(null, 5, 3)).toBe(9); // 6 + 3
  });

  it("falls back to 1 for degree when degree is undefined", () => {
    expect(collisionRadius(identityScale, undefined, 0)).toBe(2); // 1*2 + 0
  });

  it("falls back to 1 for degree=0", () => {
    expect(collisionRadius(identityScale, 0, 1)).toBe(3); // 1*2 + 1
  });

  it("null sizeScale + undefined degree still returns 6 + padding", () => {
    expect(collisionRadius(null, undefined, 2)).toBe(8);
  });
});

describe("collectCommunityIds", () => {
  it("returns distinct community IDs across all nodes", () => {
    const data = {
      nodes: [
        { community_id: 0 },
        { community_id: 1 },
        { community_id: 0 },
        { community_id: 2 },
      ],
    };
    expect(collectCommunityIds(data)).toEqual([0, 1, 2]);
  });

  it("preserves null/undefined community IDs in the set", () => {
    const data = {
      nodes: [{ community_id: 0 }, { community_id: null }],
    };
    expect(collectCommunityIds(data)).toEqual([0, null]);
  });

  it("returns [] when data is null (settings-effect-before-mount path)", () => {
    expect(collectCommunityIds(null)).toEqual([]);
  });

  it("returns [] when data is undefined", () => {
    expect(collectCommunityIds(undefined)).toEqual([]);
  });
});
