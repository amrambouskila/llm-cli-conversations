import { useState, useEffect, useCallback } from "react";
import {
  fetchSegments,
  fetchSegmentsWithHidden,
  fetchSegmentDetail,
  fetchConversation,
} from "../api";

export function useProjectSelection(provider, showHidden) {
  const [selectedProject, setSelectedProject] = useState(null);
  const [segments, setSegments] = useState([]);
  const [selectedSegmentId, setSelectedSegmentId] = useState(null);
  const [segmentDetail, setSegmentDetail] = useState(null);
  const [convViewData, setConvViewData] = useState(null);

  const loadSegments = useCallback(
    (name) => {
      const fn = showHidden ? fetchSegmentsWithHidden : fetchSegments;
      return fn(name, provider);
    },
    [showHidden, provider]
  );

  useEffect(() => {
    if (selectedProject) {
      loadSegments(selectedProject).then(setSegments).catch(console.error);
    }
  }, [showHidden, selectedProject, loadSegments]);

  const handleSelectProject = useCallback(
    async (name) => {
      setSelectedProject(name);
      setSelectedSegmentId(null);
      setSegmentDetail(null);
      setConvViewData(null);
      try {
        const segs = await loadSegments(name);
        setSegments(segs);
      } catch (err) {
        console.error(err);
      }
    },
    [loadSegments]
  );

  const handleDeselectProject = useCallback(() => {
    setSelectedProject(null);
    setSegments([]);
    setSelectedSegmentId(null);
    setSegmentDetail(null);
    setConvViewData(null);
  }, []);

  const handleSelectSegment = useCallback(
    async (segId) => {
      setSelectedSegmentId(segId);
      setConvViewData(null);
      try {
        setSegmentDetail(await fetchSegmentDetail(segId, provider));
      } catch (err) {
        console.error(err);
      }
    },
    [provider]
  );

  const handleViewConversation = useCallback(
    async (conversationId) => {
      if (!selectedProject) return;
      try {
        setConvViewData(
          await fetchConversation(selectedProject, conversationId, provider)
        );
        setSelectedSegmentId(null);
        setSegmentDetail(null);
      } catch (err) {
        console.error(err);
      }
    },
    [selectedProject, provider]
  );

  /**
   * Bridges external flows (search result click, dashboard navigation) by
   * selecting a project and jumping directly to a conversation in one atomic
   * operation. Used by handlers that originate outside this hook.
   */
  const loadProjectConversation = useCallback(
    async (project, conversationId) => {
      setSelectedProject(project);
      try {
        const segs = await loadSegments(project);
        setSegments(segs);
        setConvViewData(
          await fetchConversation(project, conversationId, provider)
        );
        setSelectedSegmentId(null);
        setSegmentDetail(null);
      } catch (err) {
        console.error(err);
      }
    },
    [loadSegments, provider]
  );

  /**
   * Full reset — used when the provider changes.
   */
  const resetAll = useCallback(() => {
    setSelectedProject(null);
    setSegments([]);
    setSelectedSegmentId(null);
    setSegmentDetail(null);
    setConvViewData(null);
  }, []);

  return {
    selectedProject,
    segments,
    selectedSegmentId,
    segmentDetail,
    convViewData,
    loadSegments,
    setSegments,
    handleSelectProject,
    handleDeselectProject,
    handleSelectSegment,
    handleViewConversation,
    loadProjectConversation,
    resetAll,
  };
}
