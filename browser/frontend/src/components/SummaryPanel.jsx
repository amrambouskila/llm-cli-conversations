import { useState, useEffect, useRef, useCallback } from "react";
import { renderMarkdown } from "../utils";
import { deleteSummary } from "../api";

// Idle timeout: how long we wait without any observable progress before
// declaring the watcher dead. The timer is reset whenever the backend
// reports a progress advance, so a long hierarchical conversation summary
// only trips this if the watcher actually stalls.
const WATCHER_IDLE_TIMEOUT_MS = 5 * 60_000;

const STARTING_PROGRESS = { phase: "starting", done: 0, total: 0, level: 0 };

export const progressSignature = (p) =>
  p ? `${p.phase || ""}:${p.level ?? 0}:${p.done ?? 0}/${p.total ?? 0}` : "";

export const formatProgress = (p) => {
  if (!p) return "Generating summary...";
  switch (p.phase) {
    case "starting":
      return "Starting summary...";
    case "segments":
      return p.total
        ? `Summarizing requests (${p.done}/${p.total})...`
        : "Summarizing requests...";
    case "rollup":
      return p.total
        ? `Combining summaries (level ${p.level + 1}, ${p.done}/${p.total})...`
        : "Combining summaries...";
    default:
      return "Generating summary...";
  }
};

export default function SummaryPanel({ summaryKey, onRequest, onPoll, onTitleReady }) {
  const [status, setStatus] = useState("none");
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(null);
  const pollRef = useRef(null);
  const timeoutRef = useRef(null);
  const lastKeyRef = useRef(null);
  const lastProgressSigRef = useRef("");

  const cleanup = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null; }
  };

  const startPolling = useCallback((cancelled = { value: false }, initialProgress = null) => {
    setStatus("pending");
    setSummary("");
    if (initialProgress) {
      setProgress(initialProgress);
      lastProgressSigRef.current = progressSignature(initialProgress);
    }

    const armIdleTimeout = () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        if (!cancelled.value) setStatus("no-watcher");
      }, WATCHER_IDLE_TIMEOUT_MS);
    };
    armIdleTimeout();

    pollRef.current = setInterval(async () => {
      try {
        const poll = await onPoll();
        if (cancelled.value) return;
        if (poll.status === "ready") {
          setSummary(poll.summary);
          setStatus("ready");
          if (poll.title && onTitleReady) onTitleReady(summaryKey, poll.title);
          cleanup();
          return;
        }
        // If the backend reported a progress advance, reset the idle timer
        // and update the loading UI.
        if (poll.progress) {
          const sig = progressSignature(poll.progress);
          if (sig !== lastProgressSigRef.current) {
            lastProgressSigRef.current = sig;
            setProgress(poll.progress);
            armIdleTimeout();
          }
        }
      } catch { /* keep polling */ }
    }, 2000);
  }, [onPoll, onTitleReady, summaryKey]);

  useEffect(() => {
    cleanup();

    if (!summaryKey || !onRequest || !onPoll) {
      setStatus("none");
      setSummary("");
      return;
    }

    // Defensive: React deps `[summaryKey]` never re-fire this effect with
    // the same key, so the AND-second-operand branch is unreachable under
    // normal flow. Kept as a stale-closure guard for future refactors.
    /* c8 ignore next */
    if (summaryKey === lastKeyRef.current && status === "ready") return;
    lastKeyRef.current = summaryKey;

    // Synchronously enter the pending state so React never renders a stale
    // "no-watcher" / "ready" view while we wait for onRequest to resolve.
    setStatus("pending");
    setSummary("");
    setError("");
    setProgress(STARTING_PROGRESS);
    lastProgressSigRef.current = progressSignature(STARTING_PROGRESS);

    const cancelled = { value: false };

    (async () => {
      try {
        const res = await onRequest();
        if (cancelled.value) return;
        if (res.status === "ready") {
          setSummary(res.summary);
          setStatus("ready");
          if (res.title && onTitleReady) onTitleReady(summaryKey, res.title);
          return;
        }
        startPolling(cancelled, res.progress || null);
      } catch (err) {
        if (cancelled.value) return;
        setStatus("error");
        setError(err.message);
      }
    })();

    return () => { cancelled.value = true; cleanup(); };
    // Intentionally only depends on summaryKey — the callback props are new
    // closures every render and would cause the summary request to refire
    // continuously. The fresh-prop assumption is documented in the parent
    // (ContentViewer wires summaryKey ↔ callbacks deterministically).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summaryKey]);

  const handleRegenerate = async () => {
    /* c8 ignore next 1 */ if (!summaryKey || !onRequest) return;
    cleanup();
    // Synchronously enter the pending state with a "starting" sentinel so
    // React doesn't briefly render "Generating summary..." (null progress)
    // or a leftover "no-watcher" view while we wait for the backend.
    setStatus("pending");
    setSummary("");
    setError("");
    setProgress(STARTING_PROGRESS);
    lastProgressSigRef.current = progressSignature(STARTING_PROGRESS);
    try {
      await deleteSummary(summaryKey);
      lastKeyRef.current = null;

      const res = await onRequest();
      if (res.status === "ready") {
        setSummary(res.summary);
        setStatus("ready");
        if (res.title && onTitleReady) onTitleReady(summaryKey, res.title);
      } else {
        startPolling({ value: false }, res.progress || null);
      }
    } catch (err) {
      console.error("Regenerate failed:", err);
      setStatus("error");
      setError(err.message);
    }
  };

  const regenerateBtn = summaryKey && onRequest && status !== "pending" ? (
    <div className="summary-toolbar">
      <button className="toolbar-btn" onClick={handleRegenerate} title="Regenerate summary">
        Regenerate
      </button>
    </div>
  ) : null;

  if (!summaryKey) {
    return (
      <div className="summary-panel">
        <div className="empty-state">Select a request to see its summary</div>
      </div>
    );
  }

  if (status === "pending") {
    return (
      <div className="summary-panel">
        <div className="summary-loading">
          <div className="summary-loading-bar">
            <div className="summary-loading-fill" />
          </div>
          <div className="summary-loading-text">{formatProgress(progress)}</div>
        </div>
      </div>
    );
  }

  if (status === "no-watcher") {
    return (
      <div className="summary-panel">
        {regenerateBtn}
        <div className="summary-install-guide">
          <h3>AI CLI Not Detected</h3>
          <p>
            AI-powered summaries require the <strong>AI CLI (Claude Code or equivalent)</strong> to be installed
            and authenticated on this computer. The summary watcher process does not appear
            to be running.
          </p>
          <h4>How to install</h4>
          <ol>
            <li><strong>Install AI CLI:</strong><pre>npm install -g @anthropic-ai/claude-code</pre></li>
            <li><strong>Authenticate:</strong> Run <code>claude</code> in your terminal and follow the login prompts.</li>
            <li><strong>Restart the service:</strong> Stop (press <code>k</code>) and run <code>./export_service.sh</code> again.</li>
          </ol>
          <p className="summary-hint">The rest of the browser works normally without the AI CLI.</p>
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="summary-panel">
        {regenerateBtn}
        <div className="summary-install-guide">
          <h3>Summary Unavailable</h3>
          <p>{error}</p>
          <p className="summary-hint">Make sure the summary watcher is running.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="summary-panel">
      {regenerateBtn}
      <div
        className="summary-content"
        dangerouslySetInnerHTML={{ __html: renderMarkdown(summary) }}
      />
    </div>
  );
}
