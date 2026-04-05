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

// Fetch with hidden items visible
export async function fetchProjectsWithHidden(provider = "claude") {
  return request(`${BASE}/api/projects?show_hidden=true&provider=${provider}`);
}

export async function fetchSegmentsWithHidden(projectName, provider = "claude") {
  return request(
    `${BASE}/api/projects/${encodeURIComponent(projectName)}/segments?show_hidden=true&provider=${provider}`
  );
}
