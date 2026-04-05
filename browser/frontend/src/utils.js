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
 * Allowlisted HTML tags that renderMarkdown may produce.
 * Any tag not in this set is stripped in the final sanitization pass.
 */
const ALLOWED_TAGS = new Set([
  "h1", "h2", "h3", "h4",
  "p", "br", "hr",
  "strong", "em", "code", "pre",
  "ul", "ol", "li",
  "blockquote",
  "a",
  "mark",
]);

/**
 * Strip any HTML tag whose name is not in ALLOWED_TAGS.
 * Permits class attributes on allowed tags but removes all other attributes
 * (blocks event handlers like onerror, onclick, etc.).
 */
function sanitizeHtml(html) {
  return html.replace(/<\/?([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)?\/?>/g, (match, tag, attrs) => {
    const lower = tag.toLowerCase();
    if (!ALLOWED_TAGS.has(lower)) {
      return "";
    }
    // For allowed tags, keep only class="..." attributes
    if (attrs) {
      const classMatch = attrs.match(/\bclass="([^"]*)"/);
      if (classMatch) {
        return match.replace(attrs, ` class="${classMatch[1]}"`);
      }
      // Strip all attributes
      const isClosing = match.startsWith("</");
      const isSelfClosing = match.endsWith("/>");
      if (isClosing) return `</${lower}>`;
      if (isSelfClosing) return `<${lower} />`;
      return `<${lower}>`;
    }
    return match;
  });
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

  // Final sanitization: strip any tag not in the allowlist
  html = sanitizeHtml(html);

  return html;
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
