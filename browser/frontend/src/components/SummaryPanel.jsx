import React, { useState, useEffect, useRef, useCallback } from "react";
import { renderMarkdown } from "../utils";
import { deleteSummary } from "../api";

const WATCHER_TIMEOUT_MS = 60_000;

export default function SummaryPanel({ summaryKey, onRequest, onPoll, onTitleReady }) {
  const [status, setStatus] = useState("none");
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");
  const pollRef = useRef(null);
  const timeoutRef = useRef(null);
  const lastKeyRef = useRef(null);

  const cleanup = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null; }
  };

  const startPolling = useCallback((cancelled = { value: false }) => {
    setStatus("pending");
    setSummary("");

    timeoutRef.current = setTimeout(() => {
      if (!cancelled.value) setStatus("no-watcher");
    }, WATCHER_TIMEOUT_MS);

    pollRef.current = setInterval(async () => {
      try {
        const poll = await onPoll();
        if (cancelled.value) return;
        if (poll.status === "ready") {
          setSummary(poll.summary);
          setStatus("ready");
          if (poll.title && onTitleReady) onTitleReady(summaryKey, poll.title);
          cleanup();
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

    if (summaryKey === lastKeyRef.current && status === "ready") return;
    lastKeyRef.current = summaryKey;

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
        startPolling(cancelled);
      } catch (err) {
        if (cancelled.value) return;
        setStatus("error");
        setError(err.message);
      }
    })();

    return () => { cancelled.value = true; cleanup(); };
  }, [summaryKey]);

  const handleRegenerate = async () => {
    if (!summaryKey || !onRequest) return;
    cleanup();
    try {
      await deleteSummary(summaryKey);
      lastKeyRef.current = null;
      setStatus("pending");
      setSummary("");
      setError("");

      const res = await onRequest();
      if (res.status === "ready") {
        setSummary(res.summary);
        setStatus("ready");
        if (res.title && onTitleReady) onTitleReady(summaryKey, res.title);
      } else {
        startPolling({ value: false });
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
          <div className="summary-loading-text">Generating summary...</div>
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
