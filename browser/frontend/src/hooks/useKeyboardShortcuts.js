import { useEffect } from "react";

export function useKeyboardShortcuts({
  searchRef,
  segments,
  selectedSegmentId,
  onSelectSegment,
  onClearSearch,
}) {
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (e.key === "Escape" && document.activeElement === searchRef.current) {
        onClearSearch();
        searchRef.current.blur();
        return;
      }
      if (
        (e.key === "ArrowDown" || e.key === "ArrowUp") &&
        document.activeElement?.tagName !== "INPUT"
      ) {
        if (!segments.length) return;
        e.preventDefault();
        const idx = segments.findIndex((s) => s.id === selectedSegmentId);
        const next =
          e.key === "ArrowDown"
            ? idx < segments.length - 1
              ? idx + 1
              : 0
            : idx > 0
            ? idx - 1
            : segments.length - 1;
        onSelectSegment(segments[next].id);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [searchRef, segments, selectedSegmentId, onSelectSegment, onClearSearch]);
}
