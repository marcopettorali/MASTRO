// MASTRO backend (agentic modules). The orchestrator is reached by the backend, not by the GUI.
const BASE = 'http://127.0.0.1:9100/api';

async function api(path, opts = {}, timeoutMs = 0) {
  const controller = timeoutMs > 0 ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const fetchOpts = controller ? { ...opts, signal: controller.signal } : opts;
    const res = await fetch(`${BASE}${path}`, fetchOpts);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        detail = body.detail || body.error || JSON.stringify(body);
      } catch (_) { /* ignore JSON parse errors */ }
      throw new Error(detail);
    }
    return res.json();
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export const ping = () => api('/ping');

// ── MCP Gateway ───────────────────────────────────────────────────────────────
export const getMcpStatus = () => api('/mcp/status');
export const getMcpNodes  = () => api('/mcp/nodes');
export const getMcpLogs   = (lines = 80) => api(`/mcp/logs?lines=${lines}`);
export const startMcpServer = (config) =>
  api('/mcp/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
export const stopMcpServer = () =>
  api('/mcp/stop', { method: 'POST' });


// ── INTENT Module ─────────────────────────────────────────────────────────────
export const listSessions = (agentId = '') =>
  api(`/intent/sessions${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''}`);

export const getSession = (sessionId) =>
  api(`/intent/sessions/${encodeURIComponent(sessionId)}`);

export const deleteSession = (sessionId) =>
  api(`/intent/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });

// intentChat is handled directly via fetch() in ChatPage for SSE streaming.
// intentChat / reconnect streams are consumed via raw fetch() in ChatPage (SSE).
export const intentChatUrl = `${BASE}/intent/chat`;
export const intentStreamUrl = (runId) =>
  `${BASE}/intent/stream/${encodeURIComponent(runId)}`;
export const getActiveRun = (sessionId) =>
  api(`/intent/active?session_id=${encodeURIComponent(sessionId)}`);

// ── Agents & Skills ───────────────────────────────────────────────────────────
export const getAgents  = () => api('/agents');
export const createAgent = (data) =>
  api('/agents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const updateAgent = (id, data) =>
  api(`/agents/${encodeURIComponent(id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
export const deleteAgent = (id) =>
  api(`/agents/${encodeURIComponent(id)}`, { method: 'DELETE' });

export const getSkills  = () => api('/skills');
export const getSkill   = (name) => api(`/skills/${encodeURIComponent(name)}`);
export const createSkill = (name, description, content) =>
  api('/skills', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description, content }) });
export const updateSkill = (name, content) =>
  api(`/skills/${encodeURIComponent(name)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) });
export const deleteSkill = (name) =>
  api(`/skills/${encodeURIComponent(name)}`, { method: 'DELETE' });

// ── LLM Settings ──────────────────────────────────────────────────────────────
export const getLlmSettings  = () => api('/config/llm');
export const saveLlmSettings = (settings) =>
  api('/config/llm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ settings }) });

// ── MongoDB Config ────────────────────────────────────────────────────────────
export const getMongoConfig  = () => api('/config/mongodb');
export const saveMongoConfig = (config) =>
  api('/config/mongodb', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ config }) });
export const testMongoConnection = (uri, database) =>
  api('/config/mongodb/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ uri, database }) });

// ── MCP Server test ───────────────────────────────────────────────────────────
export const testMcpServer = (url) =>
  api('/mcp/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) });

// ── Notifications & Autonomous loop ───────────────────────────────────────────
export const NOTIFICATIONS_STREAM_URL = `${BASE}/notifications/stream`;

export const listNotifications = (limit = 50, unreadOnly = false) =>
  api(`/notifications?limit=${limit}&unread_only=${unreadOnly}`);
export const markNotificationRead = (id) =>
  api(`/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' });
export const markAllNotificationsRead = () =>
  api('/notifications/read-all', { method: 'POST' });

export const getAutonomousStatus = () => api('/autonomous/status');
export const tickAgent = (agentId) =>
  api(`/autonomous/${encodeURIComponent(agentId)}/tick`, { method: 'POST' });
export const getAgentTickHistory = (agentId, limit = 100) =>
  api(`/autonomous/${encodeURIComponent(agentId)}/history?limit=${limit}`);

export const getNotificationsConfig = () => api('/config/notifications');
export const saveNotificationsConfig = (config) =>
  api('/config/notifications', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ config }) });
export const testNotificationsWebhook = (webhook_url) =>
  api('/config/notifications/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ webhook_url }) });

// ── Operational context ───────────────────────────────────────────────────────
export const getContextEntries = (includeHistory = true, limit = 200) =>
  api(`/context?include_history=${includeHistory}&limit=${limit}`);
export const getContextTypes = () => api('/context/types');
export const addContextEntry = (entry) =>
  api('/context', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(entry) });
export const enableContextEntry = (id) =>
  api(`/context/${encodeURIComponent(id)}/enable`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ by: 'gui' }) });
export const disableContextEntry = (id) =>
  api(`/context/${encodeURIComponent(id)}/disable`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ by: 'gui' }) });
export const revokeContextEntry = (id) =>
  api(`/context/${encodeURIComponent(id)}/revoke`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ by: 'gui' }) });
