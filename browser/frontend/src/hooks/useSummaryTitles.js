import { useState, useEffect, useCallback } from "react";
import { fetchSummaryTitles } from "../api";

const POLL_INTERVAL_MS = 10_000;

export function useSummaryTitles() {
  const [summaryTitles, setSummaryTitles] = useState({});

  useEffect(() => {
    fetchSummaryTitles().then(setSummaryTitles).catch(console.error);
    const interval = setInterval(() => {
      fetchSummaryTitles().then(setSummaryTitles).catch(() => {});
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const handleTitleReady = useCallback((key, title) => {
    setSummaryTitles((prev) => ({ ...prev, [key]: title }));
  }, []);

  return { summaryTitles, setSummaryTitles, handleTitleReady };
}
