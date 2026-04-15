import { useCallback, useEffect, useState } from "react";
import {
  fetchWikiArticle,
  fetchWikiIndex,
  resolveWikiSlug,
} from "../api";

/**
 * Owns the wiki pane state for the Knowledge Graph tab: the optional index,
 * the currently displayed article, the breadcrumb stack of previously visited
 * slugs, and the loading/error lifecycle. Modeled after `useCostBreakdown`
 * (AbortController-based fetch cancellation, AbortError swallowed).
 *
 * Breadcrumb is unlimited depth per Decision 9 in the Phase 8 plan; clicking
 * an entry jumps to that slug and truncates forward history.
 */
export function useConceptWiki(provider) {
  const [index, setIndex] = useState(null);
  const [indexError, setIndexError] = useState(null);
  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [breadcrumb, setBreadcrumb] = useState([]);
  const [selectedSlug, setSelectedSlug] = useState(null);

  // Load the wiki index once per provider. A 404 here means the wiki dir is
  // absent — the pane renders a Regenerate empty state via `indexError`.
  useEffect(() => {
    let cancelled = false;
    setIndex(null);
    setIndexError(null);
    fetchWikiIndex()
      .then((data) => {
        if (!cancelled) setIndex(data);
      })
      .catch((err) => {
        if (!cancelled) setIndexError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [provider]);

  // Fetch the article whenever selectedSlug changes. Aborts the in-flight
  // request on rapid slug changes; AbortError is swallowed (cancellation is
  // not a user-visible error).
  useEffect(() => {
    if (!selectedSlug) {
      setArticle(null);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchWikiArticle(selectedSlug, { signal: controller.signal })
      .then((data) => {
        if (cancelled) return;
        setArticle(data);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled || err.name === "AbortError") return;
        setError(err);
        setLoading(false);
        setArticle(null);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [selectedSlug]);

  const openSlug = useCallback((slug) => {
    if (!slug) return;
    setSelectedSlug((prev) => {
      if (prev === slug) return prev;
      if (prev) setBreadcrumb((b) => [...b, prev]);
      return slug;
    });
  }, []);

  const goBack = useCallback(() => {
    setBreadcrumb((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      setSelectedSlug(last);
      return prev.slice(0, -1);
    });
  }, []);

  const jumpToBreadcrumb = useCallback((idx) => {
    setBreadcrumb((prev) => {
      if (idx < 0 || idx >= prev.length) return prev;
      setSelectedSlug(prev[idx]);
      return prev.slice(0, idx);
    });
  }, []);

  const close = useCallback(() => {
    setBreadcrumb([]);
    setSelectedSlug(null);
  }, []);

  const openByConcept = useCallback(
    async ({ conceptId, conceptName }) => {
      try {
        const result = await resolveWikiSlug({ conceptId, conceptName });
        if (result?.slug) openSlug(result.slug);
      } catch {
        // Concept has no wiki article (god-node or community). Silent no-op —
        // pane stays in its current state (empty or showing previous article).
      }
    },
    [openSlug],
  );

  return {
    index,
    indexError,
    article,
    loading,
    error,
    breadcrumb,
    selectedSlug,
    openSlug,
    openByConcept,
    goBack,
    jumpToBreadcrumb,
    close,
  };
}
