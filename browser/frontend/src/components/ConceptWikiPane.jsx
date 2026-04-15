import { useCallback } from "react";
import { renderMarkdown } from "../utils";

export default function ConceptWikiPane({
  article,
  loading,
  error,
  breadcrumb,
  onSlugClick,
  onJumpToBreadcrumb,
  onOpenInConversations,
  onClose,
  onRegenerate,
}) {
  const handleBodyClick = useCallback(
    (e) => {
      const anchor = e.target.closest(".wiki-link");
      if (!anchor) return;
      e.preventDefault();
      const slug = anchor.dataset.wikiSlug;
      if (slug) onSlugClick(slug);
    },
    [onSlugClick],
  );

  if (loading) {
    return (
      <div className="concept-wiki-pane">
        <div className="concept-wiki-header">
          <div className="concept-wiki-title">Loading{"\u2026"}</div>
          <button
            className="concept-wiki-close"
            onClick={onClose}
            aria-label="Close pane"
          >
            {"\u00d7"}
          </button>
        </div>
        <div className="concept-wiki-body concept-wiki-empty">
          Loading article{"\u2026"}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="concept-wiki-pane">
        <div className="concept-wiki-header">
          <div className="concept-wiki-title">Article not found</div>
          <button
            className="concept-wiki-close"
            onClick={onClose}
            aria-label="Close pane"
          >
            {"\u00d7"}
          </button>
        </div>
        <div className="concept-wiki-body concept-wiki-empty">
          Could not load this wiki article. Regenerate the wiki to rebuild the
          community + god-node article set.
          <button
            className="dashboard-preset-btn concept-wiki-regen"
            onClick={onRegenerate}
          >
            Regenerate wiki
          </button>
        </div>
      </div>
    );
  }

  if (!article) return null;

  return (
    <div className="concept-wiki-pane">
      <div className="concept-wiki-header">
        <div className="concept-wiki-title">{article.title}</div>
        <div className="concept-wiki-actions">
          <button
            className="dashboard-preset-btn"
            onClick={() => onOpenInConversations(article.title)}
            title="Switch to Conversations tab and search for this concept"
          >
            Open in Conversations
          </button>
          <button
            className="concept-wiki-close"
            onClick={onClose}
            aria-label="Close pane"
            title="Close pane"
          >
            {"\u00d7"}
          </button>
        </div>
      </div>
      {breadcrumb.length > 0 && (
        <nav className="wiki-breadcrumb" aria-label="Wiki navigation history">
          {breadcrumb.map((slug, i) => (
            <button
              key={`${slug}-${i}`}
              className="wiki-breadcrumb-entry"
              onClick={() => onJumpToBreadcrumb(i)}
              title={`Back to ${slug.replace(/_/g, " ")}`}
            >
              {slug.replace(/_/g, " ")}
            </button>
          ))}
          <span className="wiki-breadcrumb-current" aria-current="page">
            {article.title}
          </span>
        </nav>
      )}
      <div
        className="concept-wiki-body"
        onClick={handleBodyClick}
        dangerouslySetInnerHTML={{ __html: renderMarkdown(article.markdown) }}
      />
    </div>
  );
}
