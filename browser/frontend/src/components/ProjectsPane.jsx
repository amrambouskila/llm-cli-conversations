import ProjectList from "./ProjectList";

export default function ProjectsPane({
  width,
  projects,
  selectedProject,
  onSelectProject,
  onDeselectProject,
  onHideProject,
  onRestoreProject,
  showHidden,
  dateFrom,
  dateTo,
}) {
  return (
    <div className="pane pane-projects" style={{ width }}>
      <div
        className="pane-header"
        style={{ cursor: selectedProject ? "pointer" : "default" }}
        onClick={selectedProject ? onDeselectProject : undefined}
        title={selectedProject ? "Click to deselect project" : ""}
      >
        Projects{selectedProject ? " \u2190" : ""}
      </div>
      <div className="pane-content">
        <ProjectList
          projects={projects}
          selected={selectedProject}
          onSelect={onSelectProject}
          onHideProject={onHideProject}
          onRestoreProject={onRestoreProject}
          showHidden={showHidden}
          dateFrom={dateFrom}
          dateTo={dateTo}
        />
      </div>
    </div>
  );
}
