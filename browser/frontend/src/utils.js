import DOMPurify from "isomorphic-dompurify";

/**
 * Header stats line — counts plus per-model cost estimates given an 80/20
 * input/output token split.
 */
const STATS_PRICING = {
  claude: [
    { l: "Sonnet", i: 3, o: 15 },
    { l: "Opus", i: 15, o: 75 },
  ],
  codex: [
    { l: "GPT-4o", i: 2.5, o: 10 },
    { l: "o3", i: 10, o: 40 },
  ],
};

export function formatStatsText(stats, provider) {
  if (!stats) return "";
  const t = stats.estimated_tokens;
  const inp = Math.round(t * 0.8);
  const out = Math.round(t * 0.2);
  const models = STATS_PRICING[provider] || STATS_PRICING.claude;
  const costs = models
    .map((m) => `${m.l} $${((inp * m.i + out * m.o) / 1e6).toFixed(2)}`)
    .join(" | ");
  return `${stats.total_projects} projects | ${stats.total_segments} requests | ${formatNumber(stats.total_words)} words | ${formatNumber(t)} tokens | ${costs}`;
}

/**
 * Export the active conversation or segment markdown via copy or download.
 * Falls back to a textarea + execCommand("copy") when the Clipboard API
 * isn't available (some browsers, jsdom in tests).
 */
export async function exportMarkdown(mode, convViewData, segmentDetail) {
  const md = convViewData?.raw_markdown || segmentDetail?.raw_markdown;
  if (!md) return;
  const name = convViewData
    ? `${convViewData.project_name}_conversation_${convViewData.conversation_id.substring(0, 8)}.md`
    : `${segmentDetail.project_name}_request_${segmentDetail.segment_index + 1}.md`;
  if (mode === "copy") {
    try {
      await navigator.clipboard.writeText(md);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = md;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  } else if (mode === "download") {
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }
}

export function formatNumber(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

export function formatTimestamp(ts) {
  if (!ts) return "N/A";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

/**
 * Allowlisted HTML tags that renderMarkdown may produce. Passed to DOMPurify
 * as the explicit ALLOWED_TAGS whitelist so the sanitizer accepts exactly the
 * set our markdown renderer emits — nothing else.
 */
const ALLOWED_TAGS = [
  "h1", "h2", "h3", "h4",
  "p", "br", "hr",
  "strong", "em", "code", "pre",
  "ul", "ol", "li",
  "blockquote",
  "a",
  "mark",
];

/**
 * Attributes that survive sanitization. `class` is used for tool-call
 * highlighting and syntax-highlighted code blocks; `data-wiki-slug` is used
 * by the wiki-link click handler in ConceptWikiPane.
 */
const ALLOWED_ATTR = ["class", "data-wiki-slug"];

/**
 * Compute the wiki article filename for a concept label. Mirrors
 * graphify.wiki._safe_filename exactly (locked by a backend parity test);
 * keep the three substitutions in sync if graphifyy ever changes its rules.
 */
export function wikiSlug(label) {
  return label.replace(/\//g, "-").replace(/ /g, "_").replace(/:/g, "-");
}

/**
 * Lightweight Markdown-to-HTML renderer.
 * No external dependency — covers the patterns in the exported files.
 *
 * Security: escapes all HTML first, then applies markdown transformations
 * that only produce allowlisted tags, then runs a final sanitization pass
 * to strip anything unexpected.
 */
export function renderMarkdown(md) {
  // Escape HTML first — neutralizes all raw HTML in the source
  let html = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

  // Fenced code blocks — lang is restricted to \w* so it cannot break out
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="language-${lang}">${code}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Headers (process largest first to avoid double-matching)
  html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // Bold / italic
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Wiki links — rewrite [[Label]] to clickable anchors. Operates on
  // already-escaped text so the captured label is HTML-safe; the data-wiki-slug
  // attribute survives DOMPurify's ALLOWED_ATTR whitelist.
  html = html.replace(/\[\[([^[\]]+)\]\]/g, (_, label) => {
    return `<a class="wiki-link" data-wiki-slug="${wikiSlug(label)}">${label}</a>`;
  });

  // Blockquotes
  html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

  // Horizontal rules
  html = html.replace(/^---+$/gm, "<hr />");

  // HTML comments — hide entry keys
  html = html.replace(/&lt;!-- .+? --&gt;/g, "");

  // Unordered lists
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

  // Wrap remaining bare text lines as paragraphs
  html = html.replace(
    /^(?!<[hupob\-lr]|<\/)(.+)$/gm,
    "<p>$1</p>"
  );

  // Clean empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, "");

  // Tool-call highlighting (adds class to already-allowed <strong> tags)
  html = html.replace(
    /<strong>Tool Call:/g,
    '<strong class="tool-call-header">Tool Call:'
  );
  html = html.replace(
    /<strong>Tool Result/g,
    '<strong class="tool-call-header">Tool Result'
  );
  html = html.replace(
    /<strong>Tool Error/g,
    '<strong class="tool-call-header">Tool Error'
  );

  // Final sanitization: DOMPurify enforces the ALLOWED_TAGS + ALLOWED_ATTR
  // whitelists. Any tag or attribute our markdown pipeline did not produce is
  // stripped here as defense-in-depth against injection via user content.
  return DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR });
}

/**
 * Highlight all occurrences of `query` in rendered HTML, skipping inside tags.
 */
export function highlightHtml(html, query) {
  if (!query || query.length < 2) return html;
  // Escape regex special chars in query
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // Split HTML into tags and text segments, only highlight in text
  return html.replace(
    /(<[^>]+>)|([^<]+)/g,
    (match, tag, text) => {
      if (tag) return tag;
      return text.replace(
        new RegExp(`(${escaped})`, "gi"),
        "<mark>$1</mark>"
      );
    }
  );
}
