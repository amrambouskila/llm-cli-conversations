import React, { useEffect, useRef, useCallback } from "react";
import { renderMarkdown, highlightHtml } from "../utils";
import SummaryPanel from "./SummaryPanel";
import {
  requestSummary,
  getSummary,
  requestConvSummary,
  getConvSummary,
} from "../api";

export default function ContentViewer({
  markdown,
  searchQuery,
  onExport,
  sourceFile,
  segmentId,
  conversationId,
  projectName,
  provider,
  onTitleReady,
}) {
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = 0;
  }, [markdown]);

  // Determine summary key and callbacks
  const isConversation = !!conversationId && !segmentId;
  const summaryKey = isConversation
    ? `conv_${projectName}_${conversationId}`
    : segmentId || null;

  const handleRequest = useCallback(() => {
    if (isConversation) return requestConvSummary(projectName, conversationId, provider);
    return requestSummary(segmentId, provider);
  }, [isConversation, projectName, conversationId, segmentId, provider]);

  const handlePoll = useCallback(() => {
    if (isConversation) return getConvSummary(projectName, conversationId);
    return getSummary(segmentId);
  }, [isConversation, projectName, conversationId, segmentId]);

  if (!markdown) {
    return (
      <div className="content-viewer-wrapper">
        <div className="content-viewer">
          <div className="empty-state">Select a request to view its content</div>
        </div>
      </div>
    );
  }

  let html = renderMarkdown(markdown);
  if (searchQuery) html = highlightHtml(html, searchQuery);

  return (
    <div className="content-viewer-wrapper">
      {(onExport || sourceFile) && (
        <div className="content-toolbar">
          {sourceFile && (
            <span className="toolbar-file" title={sourceFile}>
              {sourceFile.split("/").pop()}
            </span>
          )}
          <div className="toolbar-actions">
            {onExport && (
              <>
                <button className="toolbar-btn" onClick={() => onExport("copy")} title="Copy raw markdown">
                  Copy
                </button>
                <button className="toolbar-btn" onClick={() => onExport("download")} title="Download as .md">
                  Download
                </button>
              </>
            )}
          </div>
        </div>
      )}
      <div className="content-viewer" ref={ref} dangerouslySetInnerHTML={{ __html: html }} />
      <div className="content-summary-divider"><span>Summary</span></div>
      <SummaryPanel
        summaryKey={summaryKey}
        onRequest={summaryKey ? handleRequest : null}
        onPoll={summaryKey ? handlePoll : null}
        onTitleReady={onTitleReady}
      />
    </div>
  );
}
