import { useCallback } from "react";
import {
  hideSegment,
  restoreSegment,
  hideConversation,
  restoreConversation,
  hideProject,
  restoreProject,
  restoreAll,
  fetchStats,
} from "../api";

export function useHideRestore({
  provider,
  selectedProject,
  loadProjects,
  loadSegments,
  setProjects,
  setStats,
  setSegments,
}) {
  const refreshAfterStateChange = useCallback(async () => {
    try {
      const [newProjects, newStats] = await Promise.all([
        loadProjects(),
        fetchStats(provider),
      ]);
      newProjects.sort((a, b) =>
        (b.stats?.last_timestamp || "").localeCompare(
          a.stats?.last_timestamp || ""
        )
      );
      setProjects(newProjects);
      setStats(newStats);
      if (selectedProject) {
        const segs = await loadSegments(selectedProject);
        setSegments(segs);
      }
    } catch (err) {
      console.error(err);
    }
  }, [
    provider,
    selectedProject,
    loadProjects,
    loadSegments,
    setProjects,
    setStats,
    setSegments,
  ]);

  const handleHideSegment = useCallback(
    async (segId) => {
      try {
        await hideSegment(segId);
        await refreshAfterStateChange();
      } catch (err) {
        console.error(err);
      }
    },
    [refreshAfterStateChange]
  );

  const handleRestoreSegment = useCallback(
    async (segId) => {
      try {
        await restoreSegment(segId);
        await refreshAfterStateChange();
      } catch (err) {
        console.error(err);
      }
    },
    [refreshAfterStateChange]
  );

  const handleHideConversation = useCallback(
    async (convId) => {
      if (!selectedProject) return;
      try {
        await hideConversation(selectedProject, convId);
        await refreshAfterStateChange();
      } catch (err) {
        console.error(err);
      }
    },
    [selectedProject, refreshAfterStateChange]
  );

  const handleRestoreConversation = useCallback(
    async (convId) => {
      if (!selectedProject) return;
      try {
        await restoreConversation(selectedProject, convId);
        await refreshAfterStateChange();
      } catch (err) {
        console.error(err);
      }
    },
    [selectedProject, refreshAfterStateChange]
  );

  const handleHideProject = useCallback(
    async (name) => {
      try {
        await hideProject(name);
        await refreshAfterStateChange();
      } catch (err) {
        console.error(err);
      }
    },
    [refreshAfterStateChange]
  );

  const handleRestoreProject = useCallback(
    async (name) => {
      try {
        await restoreProject(name);
        await refreshAfterStateChange();
      } catch (err) {
        console.error(err);
      }
    },
    [refreshAfterStateChange]
  );

  const handleRestoreAll = useCallback(async () => {
    try {
      await restoreAll();
      await refreshAfterStateChange();
    } catch (err) {
      console.error(err);
    }
  }, [refreshAfterStateChange]);

  return {
    refreshAfterStateChange,
    handleHideSegment,
    handleRestoreSegment,
    handleHideConversation,
    handleRestoreConversation,
    handleHideProject,
    handleRestoreProject,
    handleRestoreAll,
  };
}
