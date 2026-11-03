/**
 * CKP API Client — v2 with Enterprise Access Gate.
 *
 * All authenticated requests automatically attach the Bearer JWT token
 * from sessionStorage.  The token is set by the AccessModal on login.
 */

const API_BASE = 'http://localhost:8000/api/v2';

// ---------------------------------------------------------------------------
// Token helpers
// ---------------------------------------------------------------------------
const TOKEN_KEY = 'ckp_access_token';
const ROLE_KEY  = 'ckp_access_role';

export function getStoredToken()  { return sessionStorage.getItem(TOKEN_KEY); }
export function getStoredRole()   { return sessionStorage.getItem(ROLE_KEY); }
export function storeAuth(token, role) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(ROLE_KEY, role);
}
export function clearAuth() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(ROLE_KEY);
}
export function isAuthenticated() { return !!getStoredToken(); }

// ---------------------------------------------------------------------------
// Core fetch wrapper (auto-attaches JWT)
// ---------------------------------------------------------------------------
async function fetchJSON(url, options = {}) {
  const token = getStoredToken();
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401 || res.status === 403) {
    // Token expired or invalid — clear auth and force re-login
    clearAuth();
    window.dispatchEvent(new CustomEvent('ckp:auth_expired'));
  }
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    const msg = errBody.detail || `HTTP ${res.status}: ${res.statusText}`;
    throw new Error(msg);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Auth Endpoints
// ---------------------------------------------------------------------------
export async function verifyAccess(passcode) {
  return fetchJSON(`${API_BASE}/auth/verify`, {
    method: 'POST',
    body: JSON.stringify({ passcode }),
  });
}

export async function getQuota() {
  return fetchJSON(`${API_BASE}/auth/quota`);
}

export async function logoutSession() {
  try {
    await fetchJSON(`${API_BASE}/auth/logout`, { method: 'POST' });
  } catch { /* swallow — we clear client-side anyway */ }
  clearAuth();
}

// ---------------------------------------------------------------------------
// Query Endpoints
// ---------------------------------------------------------------------------
export async function queryAgent(query, sessionId = null, schema = 'healthtech', activeSkill = 'auto', model = 'gemini-3.5-flash') {
  return fetchJSON(`${API_BASE}/query`, {
    method: 'POST',
    body: JSON.stringify({ query, session_id: sessionId, schema_name: schema, active_skill: activeSkill, model }),
  });
}

export async function streamAgentQuery(
  query,
  sessionId = null,
  schema = 'healthtech',
  activeSkill = 'auto',
  model = 'gemini-3.5-flash',
  onEvent = () => {}
) {
  const token = getStoredToken();
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}/query/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query,
      session_id: sessionId,
      schema_name: schema,
      active_skill: activeSkill,
      model,
    }),
  });

  if (res.status === 401 || res.status === 403) {
    clearAuth();
    window.dispatchEvent(new CustomEvent('ckp:auth_expired'));
    throw new Error('Authentication required');
  }
  if (res.status === 429) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.detail || 'Demo query limit reached');
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const chunk of lines) {
      const trimmed = chunk.trim();
      if (!trimmed || !trimmed.startsWith('data: ')) continue;
      const payloadStr = trimmed.slice(6);
      if (payloadStr === '[DONE]') {
        onEvent({ type: 'stream_done' });
        continue;
      }
      try {
        const parsed = JSON.parse(payloadStr);
        onEvent(parsed);
      } catch (err) {
        console.warn('Failed to parse SSE payload:', payloadStr, err);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Ingestion Endpoints
// ---------------------------------------------------------------------------
export async function ingestFile(file, schema = 'healthtech', chunkSize = 512, overlap = 64) {
  const form = new FormData();
  form.append('file', file);
  const token = getStoredToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/ingest?schema_name=${schema}&chunk_size=${chunkSize}&chunk_overlap=${overlap}`, {
    method: 'POST',
    headers,
    body: form,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function getHealth() {
  try { return await fetchJSON('http://localhost:8000/health'); }
  catch { return { status: 'unreachable' }; }
}

export async function getSchemas() {
  try { const data = await fetchJSON(`${API_BASE}/schemas`); return data.schemas || []; }
  catch { return ['healthtech', 'fintech', 'edtech', 'enterprise_ops']; }
}

export async function getSkills() {
  try { const data = await fetchJSON(`${API_BASE}/skills`); return data.skills || []; }
  catch { return []; }
}

export async function getPrompts() {
  try { const data = await fetchJSON(`${API_BASE}/prompts`); return data.prompts || []; }
  catch { return []; }
}

export async function getDiagnostics() {
  try { return await fetchJSON(`${API_BASE}/diagnostics`); }
  catch { return {}; }
}

export async function createSkill(description, domain = 'general') {
  return fetchJSON(`${API_BASE}/skills/create`, {
    method: 'POST',
    body: JSON.stringify({ description, domain }),
  });
}

export async function createPrompt(description) {
  return fetchJSON(`${API_BASE}/prompts/create`, {
    method: 'POST',
    body: JSON.stringify({ description }),
  });
}

export async function listSessions() {
  try {
    const data = await fetchJSON(`${API_BASE}/sessions`);
    return data.sessions || [];
  } catch {
    return [];
  }
}

export async function getSession(sessionId) {
  try {
    const data = await fetchJSON(`${API_BASE}/sessions/${sessionId}`);
    return data.messages || [];
  } catch {
    return [];
  }
}

export async function deleteSession(sessionId) {
  return fetchJSON(`${API_BASE}/sessions/${sessionId}`, { method: 'DELETE' });
}

export async function exportUKA(sessionId) {
  window.open(`${API_BASE}/sessions/${sessionId}/export?format=zip`, '_blank');
}

export async function importUKA(file, sessionId = null) {
  const form = new FormData();
  form.append('file', file);
  if (sessionId) form.append('session_id', sessionId);
  const token = getStoredToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/uka/import`, {
    method: 'POST',
    headers,
    body: form,
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `HTTP ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

export async function getIngestedSources() {
  try {
    const data = await fetchJSON(`${API_BASE}/ingest/sources`);
    return data.sources || [];
  } catch {
    return [];
  }
}

export async function getMonitoringLogs(limit = 50, offset = 0, model = '', smartRouted = null, search = '') {
  let url = `${API_BASE}/monitoring/logs?limit=${limit}&offset=${offset}`;
  if (model) url += `&model=${encodeURIComponent(model)}`;
  if (smartRouted !== null && smartRouted !== undefined && smartRouted !== '') url += `&smart_routed=${smartRouted}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  return fetchJSON(url);
}

export async function getMonitoringSummary() {
  return fetchJSON(`${API_BASE}/monitoring/summary`);
}

export function exportMonitoring(format = 'csv') {
  window.open(`${API_BASE}/monitoring/export?format=${format}`, '_blank');
}

// Crawler APIs
export async function getCrawlerStatus() {
  try {
    return await fetchJSON(`${API_BASE}/crawler/status`);
  } catch (err) {
    return { status: 'disabled', error: err.message, connectors: [], stats: {} };
  }
}

export async function toggleCrawler(action = 'toggle') {
  return fetchJSON(`${API_BASE}/crawler/toggle`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  });
}

export async function getCrawlerLogs(limit = 50) {
  try {
    return await fetchJSON(`${API_BASE}/crawler/logs?limit=${limit}`);
  } catch (err) {
    return { logs: [], total: 0 };
  }
}

export async function scanCrawlerNow() {
  return fetchJSON(`${API_BASE}/crawler/scan-now`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export async function triggerCrawlerWebhook(filename, content = '', schemaName = null, metadata = null) {
  return fetchJSON(`${API_BASE}/crawler/webhook`, {
    method: 'POST',
    body: JSON.stringify({ filename, content, schema_name: schemaName, metadata }),
  });
}

// Reconciliation APIs (Self-Healing Knowledge Agent)
export async function scanDuplicates(label = null, threshold = 0.85) {
  return fetchJSON(`${API_BASE}/reconciliation/scan`, {
    method: 'POST',
    body: JSON.stringify({ label, threshold }),
  });
}

export async function executeMerge(candidate, dryRun = false) {
  return fetchJSON(`${API_BASE}/reconciliation/merge`, {
    method: 'POST',
    body: JSON.stringify({ candidate, dry_run: dryRun }),
  });
}

export async function autoMergeDuplicates(threshold = 0.9, label = null, dryRun = false) {
  return fetchJSON(`${API_BASE}/reconciliation/merge`, {
    method: 'POST',
    body: JSON.stringify({ auto_merge_threshold: threshold, label, dry_run: dryRun }),
  });
}

export async function getReconciliationAudit(limit = 50) {
  return fetchJSON(`${API_BASE}/reconciliation/audit?limit=${limit}`);
}

export async function rollbackMerge(mergeId) {
  return fetchJSON(`${API_BASE}/reconciliation/rollback`, {
    method: 'POST',
    body: JSON.stringify({ merge_id: mergeId }),
  });
}

// Proactive Alerting & Standing Goals APIs
export async function listAlertRules(enabledOnly = false) {
  return fetchJSON(`${API_BASE}/alerts/rules?enabled_only=${enabledOnly}`);
}

export async function createAlertRule(ruleData) {
  return fetchJSON(`${API_BASE}/alerts/rules`, {
    method: 'POST',
    body: JSON.stringify(ruleData),
  });
}

export async function updateAlertRule(ruleId, updates) {
  return fetchJSON(`${API_BASE}/alerts/rules/${ruleId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

export async function deleteAlertRule(ruleId) {
  return fetchJSON(`${API_BASE}/alerts/rules/${ruleId}`, {
    method: 'DELETE',
  });
}

export async function toggleAlertRule(ruleId) {
  return fetchJSON(`${API_BASE}/alerts/rules/${ruleId}/toggle`, {
    method: 'POST',
  });
}

export async function getAlertsFeed(status = null, severity = null, limit = 50) {
  let url = `${API_BASE}/alerts/feed?limit=${limit}`;
  if (status) url += `&status=${encodeURIComponent(status)}`;
  if (severity) url += `&severity=${encodeURIComponent(severity)}`;
  return fetchJSON(url);
}

export async function markAlertRead(alertId) {
  return fetchJSON(`${API_BASE}/alerts/${alertId}/read`, {
    method: 'POST',
  });
}

export async function dismissAlert(alertId) {
  return fetchJSON(`${API_BASE}/alerts/${alertId}/dismiss`, {
    method: 'POST',
  });
}

export async function getUnreadAlertsCount() {
  try {
    const data = await fetchJSON(`${API_BASE}/alerts/unread-count`);
    return data.unread_count || 0;
  } catch {
    return 0;
  }
}

// Dynamic Ontology Evolution APIs
export async function getEvolutionCandidates(category = null, minOccurrences = 1) {
  let url = `${API_BASE}/ontology/evolution/candidates?min_occurrences=${minOccurrences}`;
  if (category) url += `&category=${encodeURIComponent(category)}`;
  return fetchJSON(url);
}

export async function recordCandidateConcept(candidateData) {
  return fetchJSON(`${API_BASE}/ontology/evolution/candidates`, {
    method: 'POST',
    body: JSON.stringify(candidateData),
  });
}

export async function dismissCandidateConcept(name) {
  return fetchJSON(`${API_BASE}/ontology/evolution/candidates/${encodeURIComponent(name)}/dismiss`, {
    method: 'POST',
  });
}

export async function generateEvolutionProposal(schemaName, clusterName, description = null) {
  return fetchJSON(`${API_BASE}/ontology/evolution/proposals/generate`, {
    method: 'POST',
    body: JSON.stringify({
      schema_name: schemaName,
      cluster_name: clusterName,
      description,
    }),
  });
}

export async function listEvolutionProposals(status = null) {
  let url = `${API_BASE}/ontology/evolution/proposals`;
  if (status) url += `?status=${encodeURIComponent(status)}`;
  return fetchJSON(url);
}

export async function getEvolutionProposal(proposalId) {
  return fetchJSON(`${API_BASE}/ontology/evolution/proposals/${proposalId}`);
}

export async function approveEvolutionProposal(proposalId, notes = '') {
  return fetchJSON(`${API_BASE}/ontology/evolution/proposals/${proposalId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ notes }),
  });
}

export async function rejectEvolutionProposal(proposalId, notes = '') {
  return fetchJSON(`${API_BASE}/ontology/evolution/proposals/${proposalId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ notes }),
  });
}

