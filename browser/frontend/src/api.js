const BASE = "";

async function request(url, options) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (err) {
    throw new Error(`Network error: ${err.message}`);
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

export async function fetchReady() {
  return request(`${BASE}/api/ready`);
}

export async function fetchProviders() {
  return request(`${BASE}/api/providers`);
}

export async function fetchProjects(provider = "claude") {
  return request(`${BASE}/api/projects?provider=${provider}`);
}

export async function fetchSegments(projectName, provider = "claude") {
  return request(
    `${BASE}/api/projects/${encodeURIComponent(projectName)}/segments?provider=${provider}`
  );
}

export async function fetchSegmentDetail(segmentId, provider = "claude") {
  return request(`${BASE}/api/segments/${segmentId}?provider=${provider}`);
}

export async function fetchConversation(projectName, conversationId, provider = "claude") {
  return request(
    `${BASE}/api/projects/${encodeURIComponent(projectName)}/conversation/${encodeURIComponent(conversationId)}?provider=${provider}`
  );
}

export async function searchSegments(query, provider = "claude") {
  return request(`${BASE}/api/search?q=${encodeURIComponent(query)}&provider=${provider}`);
}

export async function searchSessions(query, provider = "claude") {
  return request(`${BASE}/api/search?q=${encodeURIComponent(query)}&provider=${provider}`);
}

export async function fetchSearchFilters(provider = "claude") {
  return request(`${BASE}/api/search/filters?provider=${provider}`);
}

export async function fetchSearchStatus(provider = "claude") {
  return request(`${BASE}/api/search/status?provider=${provider}`);
}

export async function fetchRelatedSessions(sessionId) {
  return request(`${BASE}/api/sessions/${encodeURIComponent(sessionId)}/related`);
}

export async function fetchStats(provider = "claude") {
  return request(`${BASE}/api/stats?provider=${provider}`);
}

export async function triggerUpdate() {
  return request(`${BASE}/api/update`, { method: "POST" });
}

// Summaries — segments
export async function requestSummary(segmentId, provider = "claude") {
  return request(`${BASE}/api/summary/${segmentId}?provider=${provider}`, { method: "POST" });
}

export async function getSummary(segmentId) {
  return request(`${BASE}/api/summary/${segmentId}`);
}

export async function deleteSummary(segmentId) {
  return request(`${BASE}/api/summary/${segmentId}`, { method: "DELETE" });
}

// Summaries — conversations
export async function requestConvSummary(projectName, conversationId, provider = "claude") {
  return request(
    `${BASE}/api/summary/conversation/${encodeURIComponent(projectName)}/${encodeURIComponent(conversationId)}?provider=${provider}`,
    { method: "POST" }
  );
}

export async function getConvSummary(projectName, conversationId) {
  return request(
    `${BASE}/api/summary/conversation/${encodeURIComponent(projectName)}/${encodeURIComponent(conversationId)}`
  );
}

// Bulk titles for the request list
export async function fetchSummaryTitles() {
  return request(`${BASE}/api/summary/titles`);
}

// Hide / Restore
export async function hideSegment(segmentId) {
  return request(`${BASE}/api/hide/segment/${segmentId}`, { method: "POST" });
}

export async function restoreSegment(segmentId) {
  return request(`${BASE}/api/restore/segment/${segmentId}`, { method: "POST" });
}

export async function hideConversation(projectName, conversationId) {
  return request(
    `${BASE}/api/hide/conversation/${encodeURIComponent(projectName)}/${encodeURIComponent(conversationId)}`,
    { method: "POST" }
  );
}

export async function restoreConversation(projectName, conversationId) {
  return request(
    `${BASE}/api/restore/conversation/${encodeURIComponent(projectName)}/${encodeURIComponent(conversationId)}`,
    { method: "POST" }
  );
}

export async function hideProject(projectName) {
  return request(`${BASE}/api/hide/project/${encodeURIComponent(projectName)}`, { method: "POST" });
}

export async function restoreProject(projectName) {
  return request(`${BASE}/api/restore/project/${encodeURIComponent(projectName)}`, { method: "POST" });
}

export async function restoreAll() {
  return request(`${BASE}/api/restore/all`, { method: "POST" });
}

export async function fetchHidden() {
  return request(`${BASE}/api/hidden`);
}

// Dashboard endpoints
export async function fetchDashboardSummary(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/summary?${qs}`);
}

export async function fetchDashboardCostOverTime(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/cost-over-time?${qs}`);
}

export async function fetchDashboardProjects(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/projects?${qs}`);
}

export async function fetchDashboardTools(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/tools?${qs}`);
}

export async function fetchDashboardModels(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/models?${qs}`);
}

export async function fetchDashboardSessionTypes(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/session-types?${qs}`);
}

export async function fetchDashboardHeatmap(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/heatmap?${qs}`);
}

export async function fetchDashboardAnomalies(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/anomalies?${qs}`);
}

export async function fetchDashboardTopExpensiveSessions(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/top-expensive-sessions?${qs}`);
}

export async function fetchSessionCostBreakdown(sessionId, options = {}) {
  return request(
    `${BASE}/api/sessions/${encodeURIComponent(sessionId)}/cost-breakdown`,
    options
  );
}

export async function fetchDashboardGraph(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`${BASE}/api/dashboard/graph?${qs}`);
}

export async function fetchDashboardGraphStatus() {
  return request(`${BASE}/api/dashboard/graph/status`);
}

export async function triggerDashboardGraphGenerate() {
  return request(`${BASE}/api/dashboard/graph/generate`, { method: "POST" });
}

export async function importDashboardGraph() {
  return request(`${BASE}/api/dashboard/graph/import`, { method: "POST" });
}

// Fetch with hidden items visible
export async function fetchProjectsWithHidden(provider = "claude") {
  return request(`${BASE}/api/projects?show_hidden=true&provider=${provider}`);
}

export async function fetchSegmentsWithHidden(projectName, provider = "claude") {
  return request(
    `${BASE}/api/projects/${encodeURIComponent(projectName)}/segments?show_hidden=true&provider=${provider}`
  );
}
