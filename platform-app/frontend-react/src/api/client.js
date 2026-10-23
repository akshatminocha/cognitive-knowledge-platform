const API_BASE = 'http://localhost:8000/api/v2';

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function queryAgent(query, sessionId = null, schema = 'healthtech', activeSkill = 'auto', model = 'gemini-2.5-flash') {
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
  model = 'gemini-2.5-flash',
  onEvent = () => {}
) {
  const res = await fetch(`${API_BASE}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      session_id: sessionId,
      schema_name: schema,
      active_skill: activeSkill,
      model,
    }),
  });

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

export async function ingestFile(file, schema = 'healthtech', chunkSize = 512, overlap = 64) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/ingest?schema_name=${schema}&chunk_size=${chunkSize}&chunk_overlap=${overlap}`, { method: 'POST', body: form });
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
  // Download the ZIP file directly
  window.open(`${API_BASE}/sessions/${sessionId}/export?format=zip`, '_blank');
}

export async function importUKA(file, sessionId = null) {
  const form = new FormData();
  form.append('file', file);
  if (sessionId) form.append('session_id', sessionId);
  const res = await fetch(`${API_BASE}/uka/import`, {
    method: 'POST',
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

