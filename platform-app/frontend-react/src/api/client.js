const API_BASE = 'http://localhost:8000/api/v2';

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function queryAgent(query, sessionId = null, schema = 'healthtech', activeSkill = 'auto') {
  return fetchJSON(`${API_BASE}/query`, {
    method: 'POST',
    body: JSON.stringify({ query, session_id: sessionId, schema_name: schema, active_skill: activeSkill }),
  });
}

export async function ingestFile(file, schema = 'healthtech') {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/ingest?schema_name=${schema}`, { method: 'POST', body: form });
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
