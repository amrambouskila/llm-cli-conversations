import ContentViewer from "./ContentViewer";

export default function ContentPane({
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
  return (
    <div className="pane-content-area">
      <ContentViewer
        markdown={markdown}
        searchQuery={searchQuery}
        onExport={onExport}
        sourceFile={sourceFile}
        segmentId={segmentId}
        conversationId={conversationId}
        projectName={projectName}
        provider={provider}
        onTitleReady={onTitleReady}
      />
    </div>
  );
}
