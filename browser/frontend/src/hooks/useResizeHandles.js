import { useState, useRef, useEffect, useCallback } from "react";

const DEFAULTS = {
  projectsWidth: 220,
  requestsWidth: 340,
  metadataWidth: 364,
  wikiWidth: 360,
};

const BOUNDS = {
  projects: { min: 140, max: 400 },
  requests: { min: 200, max: 600 },
  metadata: { min: 250, max: 600 },
  wiki: { min: 280, max: 600 },
};

export function useResizeHandles() {
  const [projectsWidth, setProjectsWidth] = useState(DEFAULTS.projectsWidth);
  const [requestsWidth, setRequestsWidth] = useState(DEFAULTS.requestsWidth);
  const [metadataWidth, setMetadataWidth] = useState(DEFAULTS.metadataWidth);
  const [wikiWidth, setWikiWidth] = useState(DEFAULTS.wikiWidth);

  const dragging = useRef(null);
  const mainRef = useRef(null);
  const wikiContainerRef = useRef(null);

  useEffect(() => {
    const onMove = (e) => {
      if (!dragging.current) return;
      e.preventDefault();
      if (dragging.current === "wiki") {
        const wikiRect = wikiContainerRef.current?.getBoundingClientRect();
        if (!wikiRect) return;
        setWikiWidth(
          Math.max(BOUNDS.wiki.min, Math.min(BOUNDS.wiki.max, wikiRect.right - e.clientX))
        );
        return;
      }
      const mainRect = mainRef.current?.getBoundingClientRect();
      if (!mainRect) return;
      if (dragging.current === "projects") {
        setProjectsWidth(
          Math.max(
            BOUNDS.projects.min,
            Math.min(BOUNDS.projects.max, e.clientX - mainRect.left)
          )
        );
      } else if (dragging.current === "requests") {
        setRequestsWidth(
          Math.max(
            BOUNDS.requests.min,
            Math.min(
              BOUNDS.requests.max,
              e.clientX - mainRect.left - projectsWidth - 5
            )
          )
        );
      } else if (dragging.current === "metadata") {
        setMetadataWidth(
          Math.max(
            BOUNDS.metadata.min,
            Math.min(BOUNDS.metadata.max, mainRect.right - e.clientX)
          )
        );
      }
    };
    const onUp = () => {
      dragging.current = null;
      document.body.style.cursor = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, [projectsWidth]);

  const startDrag = useCallback((which) => {
    dragging.current = which;
  }, []);

  return {
    projectsWidth,
    requestsWidth,
    metadataWidth,
    wikiWidth,
    mainRef,
    wikiContainerRef,
    startDrag,
  };
}
