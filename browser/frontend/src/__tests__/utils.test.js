import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  formatNumber,
  formatTimestamp,
  renderMarkdown,
  highlightHtml,
  sanitizeHtml,
  formatStatsText,
  exportMarkdown,
} from "../utils";

describe("formatNumber", () => {
  it("stringifies values below 1,000", () => {
    expect(formatNumber(0)).toBe("0");
    expect(formatNumber(1)).toBe("1");
    expect(formatNumber(999)).toBe("999");
  });

  it("uses K suffix at and above 1,000", () => {
    expect(formatNumber(1_000)).toBe("1.0K");
    expect(formatNumber(9_999)).toBe("10.0K");
  });

  it("uses M suffix at and above 1,000,000", () => {
    expect(formatNumber(1_000_000)).toBe("1.0M");
    expect(formatNumber(1_500_000)).toBe("1.5M");
  });

  // Captures current behavior: negatives fail both >= checks and stringify raw.
  // No K/M suffix on negative magnitudes.
  it("falls through to plain stringify for negative values", () => {
    expect(formatNumber(-5)).toBe("-5");
    expect(formatNumber(-1500)).toBe("-1500");
    expect(formatNumber(-2_000_000)).toBe("-2000000");
  });
});

describe("formatTimestamp", () => {
  it("returns N/A for null", () => {
    expect(formatTimestamp(null)).toBe("N/A");
  });

  it("returns N/A for undefined", () => {
    expect(formatTimestamp(undefined)).toBe("N/A");
  });

  it("returns N/A for empty string (falsy)", () => {
    expect(formatTimestamp("")).toBe("N/A");
  });

  it("formats a valid ISO string into a non-empty locale string", () => {
    const out = formatTimestamp("2026-04-13T12:00:00Z");
    expect(typeof out).toBe("string");
    expect(out.length).toBeGreaterThan(0);
    expect(out).not.toBe("N/A");
  });

  it("formats a Date.toISOString round-trip", () => {
    const out = formatTimestamp(new Date(2026, 3, 13).toISOString());
    expect(typeof out).toBe("string");
    expect(out).not.toBe("N/A");
  });

  it("does not crash on a malformed date string (Invalid Date is fine)", () => {
    const out = formatTimestamp("not-a-date");
    expect(typeof out).toBe("string");
  });

  // new Date(Symbol()) throws TypeError synchronously, exercising the catch.
  it("returns the original ts when Date construction throws", () => {
    const sym = Symbol("trigger-throw");
    expect(formatTimestamp(sym)).toBe(sym);
  });
});

describe("renderMarkdown", () => {
  it("returns empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
  });

  it("escapes raw HTML so injected tags become entities, not live nodes", () => {
    const out = renderMarkdown("<script>alert(1)</script>");
    expect(out).not.toContain("<script>");
    expect(out).not.toContain("</script>");
    expect(out).toContain("&lt;script&gt;");
    expect(out).toContain("&lt;/script&gt;");
  });

  it("renders fenced code blocks with a language class", () => {
    const out = renderMarkdown("```python\nprint(1)\n```");
    expect(out).toContain('<pre><code class="language-python">');
    expect(out).toContain("print(1)");
    expect(out).toContain("</code></pre>");
  });

  it("renders fenced code with no language", () => {
    const out = renderMarkdown("```\nplain code\n```");
    expect(out).toContain('<pre><code class="language-">');
    expect(out).toContain("plain code");
  });

  it("renders inline code", () => {
    const out = renderMarkdown("text `inline` here");
    expect(out).toContain("<code>inline</code>");
  });

  it("renders headers h1-h4", () => {
    expect(renderMarkdown("# T1")).toContain("<h1>T1</h1>");
    expect(renderMarkdown("## T2")).toContain("<h2>T2</h2>");
    expect(renderMarkdown("### T3")).toContain("<h3>T3</h3>");
    expect(renderMarkdown("#### T4")).toContain("<h4>T4</h4>");
  });

  it("renders bold", () => {
    expect(renderMarkdown("**strong**")).toContain("<strong>strong</strong>");
  });

  it("renders italic", () => {
    expect(renderMarkdown("*emphasis*")).toContain("<em>emphasis</em>");
  });

  it("renders blockquote after escape (regex matches &gt; not raw >)", () => {
    expect(renderMarkdown("> quoted")).toContain(
      "<blockquote>quoted</blockquote>"
    );
  });

  it("renders horizontal rule", () => {
    expect(renderMarkdown("---")).toContain("<hr />");
    expect(renderMarkdown("------")).toContain("<hr />");
  });

  it("strips HTML comments", () => {
    const out = renderMarkdown("<!-- secret content -->");
    expect(out).not.toContain("secret");
  });

  it("renders unordered list and wraps in <ul>", () => {
    const out = renderMarkdown("- alpha\n- beta");
    expect(out).toContain("<ul>");
    expect(out).toContain("<li>alpha</li>");
    expect(out).toContain("<li>beta</li>");
    expect(out).toContain("</ul>");
  });

  it("wraps bare text lines in <p>", () => {
    expect(renderMarkdown("Hello world")).toBe("<p>Hello world</p>");
  });

  it('adds tool-call-header class to "Tool Call:", "Tool Result", "Tool Error"', () => {
    expect(renderMarkdown("**Tool Call:** Bash")).toContain(
      '<strong class="tool-call-header">Tool Call:'
    );
    expect(renderMarkdown("**Tool Result** ok")).toContain(
      '<strong class="tool-call-header">Tool Result'
    );
    expect(renderMarkdown("**Tool Error** boom")).toContain(
      '<strong class="tool-call-header">Tool Error'
    );
  });

  it("class attribute on allowed tag survives sanitization", () => {
    // Exercises the sanitizer's classMatch branch via fenced code's <code class="language-...">
    const out = renderMarkdown("```js\nx\n```");
    expect(out).toContain('<code class="language-js">');
  });
});

describe("highlightHtml", () => {
  it("is a no-op when query is empty/null/undefined", () => {
    expect(highlightHtml("<p>hi</p>", "")).toBe("<p>hi</p>");
    expect(highlightHtml("<p>hi</p>", null)).toBe("<p>hi</p>");
    expect(highlightHtml("<p>hi</p>", undefined)).toBe("<p>hi</p>");
  });

  it("is a no-op for single-char query (length < 2)", () => {
    expect(highlightHtml("<p>aaaaa</p>", "a")).toBe("<p>aaaaa</p>");
  });

  it("wraps matches in <mark>", () => {
    const out = highlightHtml("<p>the docker auth issue</p>", "docker");
    expect(out).toContain("<mark>docker</mark>");
  });

  it("does not highlight matches inside tag attributes", () => {
    const out = highlightHtml(
      '<a href="foo.com">click foo here</a>',
      "foo"
    );
    expect(out).toBe('<a href="foo.com">click <mark>foo</mark> here</a>');
  });

  it("escapes regex-special chars in the query (literal match)", () => {
    expect(highlightHtml("<p>using C++</p>", "C++")).toContain(
      "<mark>C++</mark>"
    );
    expect(highlightHtml("<p>config a.b here</p>", "a.b")).toContain(
      "<mark>a.b</mark>"
    );
    // Without escaping, "a.b" regex would match "axb" — verify it does not.
    expect(highlightHtml("<p>axb</p>", "a.b")).not.toContain("<mark>");
  });

  it("matches case-insensitively and preserves original casing", () => {
    expect(highlightHtml("<p>HELLO world</p>", "hello")).toContain(
      "<mark>HELLO</mark>"
    );
  });
});

// Directly tests the private sanitizer's defensive branches that renderMarkdown
// output never reaches. Covered here for safety-net documentation.
describe("sanitizeHtml (direct)", () => {
  it("strips disallowed tags entirely (exercises ALLOWED_TAGS miss branch)", () => {
    expect(sanitizeHtml("<script>x</script>")).toBe("x");
    expect(sanitizeHtml("<iframe></iframe>")).toBe("");
    expect(sanitizeHtml("before<div>middle</div>after")).toBe(
      "beforemiddleafter"
    );
  });

  it("keeps an allowed tag with no attributes unchanged", () => {
    expect(sanitizeHtml("<p>hi</p>")).toBe("<p>hi</p>");
    expect(sanitizeHtml("<strong>x</strong>")).toBe("<strong>x</strong>");
  });

  it("preserves the class attribute on an allowed tag", () => {
    expect(
      sanitizeHtml('<code class="language-js">x</code>')
    ).toBe('<code class="language-js">x</code>');
  });

  it("strips non-class attributes on an opening tag (reduces to bare tag)", () => {
    expect(sanitizeHtml('<p onclick="evil">x</p>')).toBe("<p>x</p>");
    expect(sanitizeHtml('<strong data-x="1">y</strong>')).toBe(
      "<strong>y</strong>"
    );
  });

  it("strips non-class attributes on a closing tag", () => {
    expect(sanitizeHtml("</p stray>")).toBe("</p>");
  });

  it("preserves self-closing <hr /> when attrs present", () => {
    expect(sanitizeHtml("<hr />")).toBe("<hr />");
    expect(sanitizeHtml('<hr style="color:red" />')).toBe("<hr />");
  });

  it("is a no-op when no tags are present", () => {
    expect(sanitizeHtml("plain text")).toBe("plain text");
  });
});

describe("formatStatsText", () => {
  const stats = {
    total_projects: 5,
    total_segments: 100,
    total_words: 50_000,
    estimated_tokens: 12_500,
  };

  it("returns empty string when stats is null", () => {
    expect(formatStatsText(null, "claude")).toBe("");
  });

  it("returns empty string when stats is undefined", () => {
    expect(formatStatsText(undefined, "claude")).toBe("");
  });

  it("includes counts and Claude model costs by default", () => {
    const out = formatStatsText(stats, "claude");
    expect(out).toContain("5 projects");
    expect(out).toContain("100 requests");
    expect(out).toContain("50.0K words");
    expect(out).toContain("12.5K tokens");
    expect(out).toContain("Sonnet $");
    expect(out).toContain("Opus $");
  });

  it("uses OpenAI model labels when provider is codex", () => {
    const out = formatStatsText(stats, "codex");
    expect(out).toContain("GPT-4o $");
    expect(out).toContain("o3 $");
    expect(out).not.toContain("Sonnet");
  });

  it("falls back to Claude pricing for unknown provider", () => {
    const out = formatStatsText(stats, "unknown");
    expect(out).toContain("Sonnet");
  });
});

describe("exportMarkdown", () => {
  let writeTextSpy;
  let createObjectURLSpy;
  let revokeObjectURLSpy;
  let clickSpy;

  beforeEach(() => {
    writeTextSpy = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: writeTextSpy },
      configurable: true,
    });
    createObjectURLSpy = vi.fn(() => "blob:mock");
    revokeObjectURLSpy = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      value: createObjectURLSpy,
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeObjectURLSpy,
      configurable: true,
    });
    clickSpy = vi.fn();
    HTMLAnchorElement.prototype.click = clickSpy;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is a no-op when neither convViewData nor segmentDetail has markdown", async () => {
    await exportMarkdown("copy", null, null);
    expect(writeTextSpy).not.toHaveBeenCalled();
  });

  it("copy mode writes conversation markdown to clipboard", async () => {
    await exportMarkdown(
      "copy",
      {
        raw_markdown: "# Hello",
        project_name: "alpha",
        conversation_id: "conv12345abcdef",
      },
      null
    );
    expect(writeTextSpy).toHaveBeenCalledWith("# Hello");
  });

  it("copy mode prefers convViewData over segmentDetail", async () => {
    await exportMarkdown(
      "copy",
      { raw_markdown: "conv md", project_name: "p", conversation_id: "c1abcdef" },
      { raw_markdown: "seg md", project_name: "p", segment_index: 0 }
    );
    expect(writeTextSpy).toHaveBeenCalledWith("conv md");
  });

  it("copy mode falls back to segmentDetail when no convViewData", async () => {
    await exportMarkdown("copy", null, {
      raw_markdown: "seg md",
      project_name: "p",
      segment_index: 0,
    });
    expect(writeTextSpy).toHaveBeenCalledWith("seg md");
  });

  it("copy mode falls back to textarea+execCommand when clipboard throws", async () => {
    writeTextSpy.mockRejectedValueOnce(new Error("no clipboard"));
    document.execCommand = vi.fn();
    await exportMarkdown(
      "copy",
      { raw_markdown: "x", project_name: "p", conversation_id: "c1abcdef" },
      null
    );
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });

  it("download mode creates an object URL and triggers click", async () => {
    await exportMarkdown(
      "download",
      { raw_markdown: "x", project_name: "alpha", conversation_id: "c1abcdef" },
      null
    );
    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock");
  });

  it("conversation download filename uses first 8 chars of conversation_id", async () => {
    let downloadName;
    HTMLAnchorElement.prototype.click = function () {
      downloadName = this.download;
    };
    await exportMarkdown(
      "download",
      {
        raw_markdown: "x",
        project_name: "alpha",
        conversation_id: "abcdefgh-rest-of-id",
      },
      null
    );
    expect(downloadName).toBe("alpha_conversation_abcdefgh.md");
  });

  it("segment download filename uses 1-indexed segment_index", async () => {
    let downloadName;
    HTMLAnchorElement.prototype.click = function () {
      downloadName = this.download;
    };
    await exportMarkdown("download", null, {
      raw_markdown: "x",
      project_name: "beta",
      segment_index: 5,
    });
    expect(downloadName).toBe("beta_request_6.md");
  });
});
