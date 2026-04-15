import { useState, useEffect, useRef, useCallback } from "react";
import {
  searchSessions,
  fetchSearchFilters,
  fetchSearchStatus,
} from "../api";

const DEBOUNCE_MS = 300;
const STATUS_POLL_MS = 5000;
const STATUS_POLL_BACKOFF_MS = 10000;
const MIN_QUERY_LENGTH = 2;

export function useSearch({
  provider,
  backendReady,
  selectedProject,
  loadSegments,
  setSegments,
  onSearchStart,
  onSearchCleared,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [filterOptions, setFilterOptions] = useState(null);
  const [searchMode, setSearchMode] = useState(null);

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [pendingDateFrom, setPendingDateFrom] = useState("");
  const [pendingDateTo, setPendingDateTo] = useState("");
  const [showDateFilter, setShowDateFilter] = useState(false);

  const searchRef = useRef(null);
  const searchTimerRef = useRef(null);

  // Poll search status until both hybrid mode and graph are active
  useEffect(() => {
    if (!backendReady) return;
    let timer = null;
    let cancelled = false;
    const poll = () => {
      fetchSearchStatus(provider)
        .then((s) => {
          if (cancelled) return;
          setSearchMode(s);
          const settled = s.mode === "hybrid" && s.has_graph;
          if (!settled) timer = setTimeout(poll, STATUS_POLL_MS);
        })
        .catch(() => {
          if (!cancelled) timer = setTimeout(poll, STATUS_POLL_BACKOFF_MS);
        });
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [backendReady, provider]);

  // Reload filter options on provider change
  useEffect(() => {
    fetchSearchFilters(provider).then(setFilterOptions).catch(console.error);
  }, [provider]);

  // Debounced search
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (searchQuery.length < MIN_QUERY_LENGTH) {
      setIsSearching(false);
      setSearchResults(null);
      if (selectedProject && searchQuery.length === 0) {
        loadSegments(selectedProject)
          .then((segs) => {
            setSegments(segs);
            onSearchCleared?.(selectedProject);
          })
          .catch(console.error);
      }
      return;
    }
    setIsSearching(true);
    searchTimerRef.current = setTimeout(async () => {
      onSearchStart?.(searchQuery);
      try {
        const results = await searchSessions(searchQuery, provider);
        setSearchResults(results);
      } catch (err) {
        console.error(err);
      }
      setIsSearching(false);
    }, DEBOUNCE_MS);
  }, [
    searchQuery,
    selectedProject,
    loadSegments,
    setSegments,
    onSearchStart,
    onSearchCleared,
    provider,
  ]);

  const applyDateFilter = useCallback(() => {
    setDateFrom(pendingDateFrom);
    setDateTo(pendingDateTo);
  }, [pendingDateFrom, pendingDateTo]);

  const clearDateFilter = useCallback(() => {
    setDateFrom("");
    setDateTo("");
    setPendingDateFrom("");
    setPendingDateTo("");
  }, []);

  const resetSearch = useCallback(() => {
    setSearchQuery("");
    setSearchResults(null);
  }, []);

  const isInSearchMode = searchQuery.length >= MIN_QUERY_LENGTH;

  return {
    searchQuery,
    setSearchQuery,
    isSearching,
    searchResults,
    filterOptions,
    searchMode,
    dateFrom,
    dateTo,
    pendingDateFrom,
    setPendingDateFrom,
    pendingDateTo,
    setPendingDateTo,
    showDateFilter,
    setShowDateFilter,
    searchRef,
    applyDateFilter,
    clearDateFilter,
    resetSearch,
    isInSearchMode,
  };
}
