export default function Header({
  providers,
  provider,
  onProviderChange,
  activeTab,
  onTabChange,
  statsText,
  showHidden,
  onToggleShowHidden,
  hiddenTotal,
  onRestoreAll,
  theme,
  onToggleTheme,
  isUpdating,
  updateStatus,
  onUpdate,
}) {
  return (
    <div className="header">
      <div className="header-left">
        <h1>Conversation Browser</h1>
        {providers.length > 1 && (
          <select
            className="provider-select"
            value={provider}
            onChange={(e) => onProviderChange(e.target.value)}
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.projects} projects)
              </option>
            ))}
          </select>
        )}
        {providers.length <= 1 && (
          <span className="provider-label">
            {provider.charAt(0).toUpperCase() + provider.slice(1)}
          </span>
        )}
        <div className="header-tabs">
          <button
            className={`header-tab${
              activeTab === "conversations" ? " header-tab-active" : ""
            }`}
            onClick={() => onTabChange("conversations")}
          >
            Conversations
          </button>
          <button
            className={`header-tab${
              activeTab === "dashboard" ? " header-tab-active" : ""
            }`}
            onClick={() => onTabChange("dashboard")}
          >
            Dashboard
          </button>
          <button
            className={`header-tab${
              activeTab === "graph" ? " header-tab-active" : ""
            }`}
            onClick={() => onTabChange("graph")}
          >
            Knowledge Graph
          </button>
        </div>
      </div>
      <div className="header-right">
        <div className="stats">{statsText}</div>
        <button
          className={`toolbar-btn${showHidden ? " toolbar-btn-active" : ""}`}
          onClick={onToggleShowHidden}
          title={showHidden ? "Hide deleted items" : "Show deleted items"}
        >
          Trash{hiddenTotal > 0 ? ` (${hiddenTotal})` : ""}
        </button>
        {showHidden && hiddenTotal > 0 && (
          <button
            className="toolbar-btn"
            onClick={onRestoreAll}
            title="Restore all hidden items"
          >
            Restore All
          </button>
        )}
        <button
          className="toolbar-btn"
          onClick={onToggleTheme}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? "Light" : "Dark"}
        </button>
        <button
          className={`update-btn${isUpdating ? " updating" : ""}${
            updateStatus === "success" ? " success" : ""
          }${updateStatus === "error" ? " error" : ""}`}
          onClick={onUpdate}
          disabled={isUpdating}
          title="Sync latest conversations and re-index"
        >
          {isUpdating
            ? "Updating..."
            : updateStatus === "success"
            ? "Updated"
            : updateStatus === "error"
            ? "Failed"
            : "Update"}
        </button>
      </div>
    </div>
  );
}
