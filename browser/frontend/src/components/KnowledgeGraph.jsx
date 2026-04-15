import { useState, useEffect, useCallback } from "react";
import {
  fetchDashboardGraph,
  fetchDashboardGraphStatus,
  triggerDashboardGraphGenerate,
  importDashboardGraph,
} from "../api";
import ConceptGraph from "./ConceptGraph";

export default function KnowledgeGraph({ provider, onConceptClick }) {
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [graphStatus, setGraphStatus] = useState("loading");
  const [graphProgress, setGraphProgress] = useState(null);

  const apiParams = { provider };

  // Poll status, auto-import when ready, show progress while generating
  useEffect(() => {
    let pollTimer = null;
    let cancelled = false;

    const checkGraph = async () => {
      /* c8 ignore next 1 */ if (cancelled) return;
      try {
        const status = await fetchDashboardGraphStatus();
        if (cancelled) return;

        if (status.has_data) {
          const data = await fetchDashboardGraph(apiParams);
          if (!cancelled) {
            setGraphData(data);
            setGraphStatus(data.nodes.length > 0 ? "ready" : "none");
          }
          return;
        }

        if (status.status === "generating") {
          setGraphStatus("generating");
          if (status.progress) setGraphProgress(status.progress);
          pollTimer = setTimeout(checkGraph, 3000);
          return;
        }

        if (status.status === "ready") {
          setGraphStatus("importing");
          try {
            const importResult = await importDashboardGraph();
            if (!cancelled && importResult.ok) {
              const data = await fetchDashboardGraph(apiParams);
              if (!cancelled) {
                setGraphData(data);
                setGraphStatus(data.nodes.length > 0 ? "ready" : "none");
              }
            } else if (!cancelled) {
              setGraphStatus("error");
            }
          } catch {
            if (!cancelled) setGraphStatus("error");
          }
          return;
        }

        if (status.status === "error") {
          setGraphStatus("error");
          return;
        }

        setGraphStatus("none");
        pollTimer = setTimeout(checkGraph, 5000);
      } catch {
        if (!cancelled) setGraphStatus("error");
      }
    };

    checkGraph();

    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
    // apiParams is { provider } and is recomputed each render — relying on
    // provider directly avoids re-running the polling effect every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  const handleRegenerate = useCallback(async () => {
    setGraphStatus("generating");
    setGraphProgress(null);
    try {
      await triggerDashboardGraphGenerate();
    } catch {
      setGraphStatus("error");
    }
  }, []);

  return (
    <div className="knowledge-graph-view">
      <div className="knowledge-graph-header">
        <h2>Knowledge Graph</h2>
        {graphStatus === "ready" && (
          <button className="dashboard-preset-btn" onClick={handleRegenerate}>
            Regenerate
          </button>
        )}
      </div>

      {graphStatus === "generating" ? (
        <div className="graph-loading">
          {graphProgress && graphProgress.total > 0 ? (
            <div className="graph-progress">
              <div className="graph-progress-bar-track">
                <div
                  className="graph-progress-bar-fill"
                  style={{ width: `${(graphProgress.done / graphProgress.total) * 100}%` }}
                />
              </div>
              <div className="graph-progress-text">
                Extracting concepts: {graphProgress.done} / {graphProgress.total} files
              </div>
              {graphProgress.current && (
                <div className="graph-progress-detail">
                  Current: {graphProgress.current.replace(/-/g, " / ")}
                </div>
              )}
              <div className="graph-progress-detail">
                {graphProgress.ok > 0 && <span>{graphProgress.ok} extracted</span>}
                {graphProgress.failed > 0 && <span> &middot; {graphProgress.failed} failed</span>}
                {graphProgress.model && <span> &middot; model: {graphProgress.model}</span>}
              </div>
            </div>
          ) : (
            <>
              <div className="graph-loading-bar">
                <div className="graph-loading-fill" />
              </div>
              <div className="graph-loading-text">
                Starting concept graph extraction...
              </div>
            </>
          )}
        </div>
      ) : graphStatus === "importing" || graphStatus === "loading" ? (
        <div className="graph-loading">
          <div className="graph-loading-bar">
            <div className="graph-loading-fill" />
          </div>
          <div className="graph-loading-text">
            {graphStatus === "importing" ? "Importing graph into database..." : "Loading..."}
          </div>
        </div>
      ) : graphStatus === "error" ? (
        <div className="graph-loading">
          <div className="graph-loading-text">
            Graph generation failed. Check that the claude CLI is installed and graphifyy is available on the host.
          </div>
          <button className="dashboard-preset-btn" onClick={handleRegenerate} style={{ marginTop: 8 }}>
            Retry
          </button>
        </div>
      ) : graphData.nodes.length > 0 ? (
        <ConceptGraph data={graphData} onConceptClick={onConceptClick} />
      ) : (
        <div className="graph-loading">
          <div className="graph-loading-text">
            Waiting for concept graph extraction to start...
          </div>
        </div>
      )}
    </div>
  );
}
