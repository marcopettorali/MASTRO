import { useState, useEffect } from 'react';
import {
  getAgents, createAgent, updateAgent, deleteAgent,
  getSkills, getSkill, createSkill, updateSkill, deleteSkill,
  getLlmSettings, saveLlmSettings,
  getMongoConfig, saveMongoConfig, testMongoConnection,
  testMcpServer,
  getAutonomousStatus, tickAgent, getAgentTickHistory,
  getNotificationsConfig, saveNotificationsConfig, testNotificationsWebhook,
} from '../api/mastro.js';

function MongoDBTab() {
  const [cfg, setCfg] = useState({ uri: '', database: 'mastro_agent' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    getMongoConfig().then(r => { if (r.ok) setCfg(r.config || {}); }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true); setResult(null);
    try { const r = await saveMongoConfig(cfg); setResult(r.ok ? { ok: true, msg: 'Saved.' } : { ok: false, msg: 'Save failed' }); }
    catch (e) { setResult({ ok: false, msg: e.message }); } finally { setSaving(false); }
  }

  async function test() {
    setTesting(true); setTestResult(null);
    try { const r = await testMongoConnection(cfg.uri, cfg.database); setTestResult(r); }
    catch (e) { setTestResult({ ok: false, message: e.message }); } finally { setTesting(false); }
  }

  if (loading) return <div className="loading-text">Loading...</div>;
  return (
    <div style={{ maxWidth: 560 }}>
      <p className="text-muted" style={{ marginBottom: 16, fontSize: 13 }}>
        Configure MongoDB for persisting chat sessions and reasoning logs. Leave URI empty to use in-memory storage.
      </p>
      <div className="form-group">
        <div className="form-label">MongoDB URI</div>
        <input className="form-input" type="text" placeholder="mongodb://localhost:27017"
          value={cfg.uri || ''} onChange={e => setCfg(c => ({ ...c, uri: e.target.value }))} />
        <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
          e.g. mongodb://user:pass@localhost:27017 or mongodb+srv://...
        </div>
      </div>
      <div className="form-group">
        <div className="form-label">Database Name</div>
        <input className="form-input" type="text" placeholder="mastro_agent"
          value={cfg.database || ''} onChange={e => setCfg(c => ({ ...c, database: e.target.value }))} />
      </div>
      {testResult && <div className={testResult.ok ? 'success-box' : 'error-box'} style={{ marginBottom: 12 }}>{testResult.ok ? '✓ ' : '✗ '}{testResult.message}</div>}
      {result && <div className={result.ok ? 'success-box' : 'error-box'} style={{ marginBottom: 12 }}>{result.msg}</div>}
      <div className="row">
        <button className="btn-primary" onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
        <button onClick={test} disabled={testing || !cfg.uri}>{testing ? 'Testing...' : 'Test Connection'}</button>
      </div>

      <NotificationsConfigCard />
    </div>
  );
}

function NotificationsConfigCard() {
  const [cfg, setCfg] = useState({ webhook_url: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    getNotificationsConfig().then(r => { if (r.ok) setCfg(r.config || { webhook_url: '' }); })
      .catch(() => {}).finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true); setResult(null);
    try { const r = await saveNotificationsConfig(cfg); setResult(r.ok ? { ok: true, msg: 'Saved.' } : { ok: false, msg: 'Save failed' }); }
    catch (e) { setResult({ ok: false, msg: e.message }); } finally { setSaving(false); }
  }

  async function test() {
    setTesting(true); setTestResult(null);
    try { const r = await testNotificationsWebhook(cfg.webhook_url); setTestResult(r); }
    catch (e) { setTestResult({ ok: false, message: e.message }); } finally { setTesting(false); }
  }

  if (loading) return null;
  return (
    <div style={{ marginTop: 32, borderTop: '1px solid #3a3a40', paddingTop: 20 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#cfcfd4', marginBottom: 8 }}>
        Push Notifications (webhook)
      </div>
      <p className="text-muted" style={{ marginBottom: 12, fontSize: 13 }}>
        ntfy-compatible webhook for pushing autonomous agent alerts to your devices.
        Leave empty to use in-app notifications only.
      </p>
      <div className="form-group">
        <div className="form-label">Webhook URL</div>
        <input className="form-input" type="text" placeholder="https://ntfy.sh/your-topic"
          value={cfg.webhook_url || ''} onChange={e => setCfg(c => ({ ...c, webhook_url: e.target.value }))} />
      </div>
      {testResult && <div className={testResult.ok ? 'success-box' : 'error-box'} style={{ marginBottom: 12 }}>{testResult.ok ? '✓ ' : '✗ '}{testResult.message}</div>}
      {result && <div className={result.ok ? 'success-box' : 'error-box'} style={{ marginBottom: 12 }}>{result.msg}</div>}
      <div className="row">
        <button className="btn-primary" onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
        <button onClick={test} disabled={testing || !(cfg.webhook_url || '').trim()}>{testing ? 'Sending...' : 'Send Test'}</button>
      </div>
    </div>
  );
}

function LLMSettingsTab() {
  const DEFAULTS = { base_url: 'http://localhost:11434/v1', model: 'qwen2.5:32b', api_key: 'ollama', temperature: 0.2, max_tokens: 2048, timeout_s: 120 };
  const [cfg, setCfg] = useState(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    getLlmSettings().then(r => { if (r.ok) setCfg({ ...DEFAULTS, ...(r.settings || {}) }); }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true); setResult(null);
    try { const r = await saveLlmSettings(cfg); setResult(r.ok ? { ok: true, msg: 'Saved.' } : { ok: false, msg: 'Save failed' }); }
    catch (e) { setResult({ ok: false, msg: e.message }); } finally { setSaving(false); }
  }

  const upd = (k, v) => setCfg(c => ({ ...c, [k]: v }));
  if (loading) return <div className="loading-text">Loading...</div>;
  return (
    <div style={{ maxWidth: 560 }}>
      <p className="text-muted" style={{ marginBottom: 16, fontSize: 13 }}>
        Default LLM endpoint for all agents. Each agent can override individually.
        Compatible with Ollama, vLLM, OpenAI, LM Studio.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 16px' }}>
        {[
          { key: 'base_url', label: 'Base URL', type: 'text', placeholder: 'http://localhost:11434/v1', full: true },
          { key: 'model', label: 'Model', type: 'text', placeholder: 'qwen2.5:32b' },
          { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'ollama' },
          { key: 'temperature', label: 'Temperature', type: 'number' },
          { key: 'max_tokens', label: 'Max Tokens', type: 'number' },
          { key: 'timeout_s', label: 'Timeout (s)', type: 'number' },
        ].map(f => (
          <div key={f.key} style={f.full ? { gridColumn: '1 / -1' } : {}}>
            <div className="form-label">{f.label}</div>
            <input className="form-input" type={f.type} placeholder={f.placeholder || ''}
              value={cfg[f.key] ?? ''} onChange={e => upd(f.key, f.type === 'number' ? Number(e.target.value) : e.target.value)} />
          </div>
        ))}
      </div>
      {result && <div className={result.ok ? 'success-box' : 'error-box'} style={{ margin: '12px 0' }}>{result.msg}</div>}
      <div style={{ marginTop: 14 }}>
        <button className="btn-primary" onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save LLM Settings'}</button>
      </div>
    </div>
  );
}

function SkillEditor({ skillName, onClose, onSave }) {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (skillName) {
      getSkill(skillName).then(r => { if (r.ok) setContent(r.content || ''); }).finally(() => setLoading(false));
    } else {
      setContent('---\nname: new-skill\ndescription: Describe what this skill provides.\n---\n\n# New Skill\n\nAdd domain knowledge and instructions here.\n');
      setLoading(false);
    }
  }, [skillName]);

  async function save() {
    setSaving(true);
    try {
      if (skillName) {
        await updateSkill(skillName, content);
      } else {
        const match = content.match(/^---[\s\S]*?name:\s*([^\n]+)/);
        const name = match ? match[1].trim() : 'new-skill';
        await createSkill(name, '', content);
      }
      onSave();
    } catch (e) { alert('Save failed: ' + e.message); } finally { setSaving(false); }
  }

  if (loading) return <div className="loading-text">Loading...</div>;
  return (
    <div>
      <div className="row" style={{ marginBottom: 12 }}>
        <strong>{skillName ? 'Edit: ' + skillName : 'New Skill'}</strong>
        <span className="spacer" />
        <button className="btn-sm" onClick={onClose}>Cancel</button>
      </div>
      <textarea className="form-textarea" rows={22} style={{ fontFamily: 'monospace', fontSize: 12 }}
        value={content} onChange={e => setContent(e.target.value)} />
      <div style={{ marginTop: 10 }}>
        <button className="btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save Skill'}</button>
      </div>
    </div>
  );
}

const DEFAULT_AUTONOMOUS = {
  enabled: false,
  interval_seconds: 300,
  task_prompt: 'Analyse the current state of the managed infrastructure: node status, metrics and job activity. Identify anomalies or conditions that deserve the operator\'s attention.',
  notify_on: ['warning', 'critical'],
};

function AgentModal({ agent, allSkills, onClose, onSave }) {
  const [form, setForm] = useState(agent ? { ...agent } : { name: '', description: '', system_prompt: 'You are a MASTRO agent operating managed infrastructure.', skills: [], llm_override: null });
  const [saving, setSaving] = useState(false);
  const upd = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const auto = { ...DEFAULT_AUTONOMOUS, ...(form.autonomous || {}) };
  const updAuto = (k, v) => setForm(f => ({ ...f, autonomous: { ...DEFAULT_AUTONOMOUS, ...(f.autonomous || {}), [k]: v } }));
  const toggleNotify = (sev) => updAuto('notify_on',
    auto.notify_on.includes(sev) ? auto.notify_on.filter(s => s !== sev) : [...auto.notify_on, sev]);

  async function save() {
    setSaving(true);
    try {
      if (agent) await updateAgent(agent.id, form);
      else await createAgent(form);
      onSave();
    } catch (e) { alert('Save failed: ' + e.message); } finally { setSaving(false); }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box" style={{ maxWidth: 640 }}>
        <div className="modal-title">{agent ? 'Edit Agent' : 'New Agent'}</div>
        <div className="form-group">
          <div className="form-label">Name</div>
          <input className="form-input" value={form.name} onChange={e => upd('name', e.target.value)} placeholder="e.g. Thermal Agent" />
        </div>
        <div className="form-group">
          <div className="form-label">Description</div>
          <input className="form-input" value={form.description} onChange={e => upd('description', e.target.value)} placeholder="Short description" />
        </div>
        <div className="form-group">
          <div className="form-label">System Prompt</div>
          <textarea className="form-textarea" rows={6} style={{ fontFamily: 'monospace', fontSize: 12 }}
            value={form.system_prompt} onChange={e => upd('system_prompt', e.target.value)} />
        </div>
        <div className="form-group">
          <div className="form-label">Skills (click to toggle)</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: 10, background: '#18181b', borderRadius: 6, border: '1px solid #3a3a40' }}>
            {allSkills.length === 0 && <span className="text-muted" style={{ fontSize: 12 }}>No skills available. Create skills in the Skills sub-tab.</span>}
            {allSkills.map(s => {
              const active = (form.skills || []).includes(s.name);
              return (
                <button key={s.name} title={s.description}
                  onClick={() => upd('skills', active ? form.skills.filter(x => x !== s.name) : [...(form.skills || []), s.name])}
                  style={{ fontSize: 12, padding: '3px 10px', borderRadius: 999, cursor: 'pointer',
                    background: active ? '#4a9eff22' : 'transparent',
                    border: '1px solid ' + (active ? '#4a9eff' : '#3a3a40'),
                    color: active ? '#4a9eff' : '#9ca3af' }}>
                  {s.name}
                </button>
              );
            })}
          </div>
        </div>
        <div className="form-group">
          <div className="form-label">Autonomous Mode</div>
          <div style={{ padding: 10, background: '#18181b', borderRadius: 6, border: '1px solid #3a3a40' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={auto.enabled}
                onChange={e => updAuto('enabled', e.target.checked)} />
              Enable periodic autonomous sampling
            </label>
            {auto.enabled && (
              <div style={{ marginTop: 12 }}>
                <div className="form-label">Sampling interval (seconds, min 30)</div>
                <input className="form-input" type="number" min={30} style={{ maxWidth: 160 }}
                  value={auto.interval_seconds}
                  onChange={e => updAuto('interval_seconds', Math.max(30, parseInt(e.target.value || '30', 10)))} />
                <div className="form-label" style={{ marginTop: 10 }}>Task prompt (executed at every tick)</div>
                <textarea className="form-textarea" rows={3} style={{ fontFamily: 'monospace', fontSize: 12 }}
                  value={auto.task_prompt} onChange={e => updAuto('task_prompt', e.target.value)} />
                <div className="form-label" style={{ marginTop: 10 }}>Notify operator on</div>
                <div style={{ display: 'flex', gap: 16 }}>
                  {['warning', 'critical'].map(sev => (
                    <label key={sev} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
                      <input type="checkbox" checked={auto.notify_on.includes(sev)}
                        onChange={() => toggleNotify(sev)} />
                      {sev}
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="row" style={{ marginTop: 16 }}>
          <button className="btn-primary" onClick={save} disabled={saving || !form.name}>{saving ? 'Saving...' : 'Save Agent'}</button>
          <button onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

// ── MCP Servers sub-tab (inside Agents & Skills) ─────────────────────────────

function McpServersTab({ agents, onReload }) {
  // Form state for adding a new server to a selected agent
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [form, setForm] = useState({ name: '', url: '' });
  const [saving, setSaving]   = useState(false);
  const [testResults, setTestResults] = useState({}); // key: `${agentId}-${serverId}`
  const [testing, setTesting]   = useState({});

  // Flatten: all (agent, server) pairs for the table
  const rows = agents.flatMap(ag =>
    (ag.mcp_servers || []).map(srv => ({ agent: ag, server: srv }))
  );

  async function testServer(agentId, serverId, url) {
    const key = `${agentId}-${serverId}`;
    setTesting(t => ({ ...t, [key]: true }));
    setTestResults(r => ({ ...r, [key]: null }));
    try {
      const res = await testMcpServer(url);
      setTestResults(r => ({ ...r, [key]: res }));
    } catch (e) {
      setTestResults(r => ({ ...r, [key]: { ok: false, message: e.message } }));
    } finally {
      setTesting(t => ({ ...t, [key]: false }));
    }
  }

  async function removeServer(agent, serverId) {
    const updated = { ...agent, mcp_servers: (agent.mcp_servers || []).filter(s => s.id !== serverId) };
    try {
      await updateAgent(agent.id, updated);
      onReload();
    } catch (e) { alert('Remove failed: ' + e.message); }
  }

  async function addServer() {
    if (!selectedAgentId || !form.url.trim()) return;
    setSaving(true);
    try {
      const agent = agents.find(a => a.id === selectedAgentId);
      if (!agent) return;
      const newServer = { id: 'mcp-' + Date.now(), name: form.name.trim() || form.url.trim(), url: form.url.trim() };
      const updated = { ...agent, mcp_servers: [...(agent.mcp_servers || []), newServer] };
      await updateAgent(agent.id, updated);
      setForm({ name: '', url: '' });
      setSelectedAgentId('');
      onReload();
    } catch (e) { alert('Save failed: ' + e.message); } finally { setSaving(false); }
  }

  return (
    <div>
      {/* ── Configured servers table ─────────────────────────── */}
      {rows.length === 0 ? (
        <div className="text-muted" style={{ padding: '16px 0', fontSize: 13 }}>
          No MCP servers configured yet. Use the form below to add one.
        </div>
      ) : (
        <table className="data-table" style={{ marginBottom: 24 }}>
          <thead>
            <tr><th>Agent</th><th>Name</th><th>URL</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map(({ agent, server }) => {
              const key = `${agent.id}-${server.id}`;
              const result = testResults[key];
              return (
                <tr key={key}>
                  <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>{agent.name}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{server.name}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12, color: '#9ca3af' }}>{server.url}</td>
                  <td style={{ minWidth: 180 }}>
                    {result ? (
                      <span style={{ fontSize: 11, color: result.ok ? '#4ade80' : '#f87171' }}>
                        {result.ok ? '✓ ' : '✗ '}{result.message}
                      </span>
                    ) : (
                      <span style={{ fontSize: 11, color: '#4b5563' }}>—</span>
                    )}
                  </td>
                  <td>
                    <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
                      <button className="btn-sm"
                        disabled={testing[key]}
                        onClick={() => testServer(agent.id, server.id, server.url)}>
                        {testing[key] ? 'Testing…' : 'Test'}
                      </button>
                      <button className="btn-danger btn-sm"
                        onClick={() => removeServer(agent, server.id)}>
                        Remove
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {/* ── Add server form ──────────────────────────────────── */}
      <div style={{ borderTop: '1px solid #3a3a40', paddingTop: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#cfcfd4', marginBottom: 12 }}>
          Add MCP Server to Agent
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 2fr', gap: '8px 12px', alignItems: 'end' }}>
          <div>
            <div className="form-label">Agent</div>
            <select className="form-input" value={selectedAgentId}
              onChange={e => setSelectedAgentId(e.target.value)}>
              <option value="">— select agent —</option>
              {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          <div>
            <div className="form-label">Name</div>
            <input className="form-input" placeholder="e.g. MASTRO MCP Gateway"
              value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          </div>
          <div>
            <div className="form-label">URL</div>
            <input className="form-input" placeholder="http://localhost:8001/mcp"
              value={form.url} onChange={e => setForm(f => ({ ...f, url: e.target.value }))} />
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="btn-primary btn-sm"
            onClick={addServer}
            disabled={saving || !selectedAgentId || !form.url.trim()}>
            {saving ? 'Saving…' : '+ Add Server'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Autonomous sub-tab (inside Agents & Skills) ───────────────────────────────

const STATUS_COLORS = { ok: '#4ade80', warning: '#fbbf24', critical: '#f87171', unknown: '#9ca3af' };

function TickHistory({ agentId, refreshKey }) {
  const [ticks, setTicks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    setLoading(true);
    getAgentTickHistory(agentId).then(r => setTicks(r.ticks || []))
      .catch(() => {}).finally(() => setLoading(false));
  }, [agentId, refreshKey]);

  if (loading) return <div className="loading-text" style={{ padding: 12 }}>Loading history...</div>;
  if (ticks.length === 0) return (
    <div className="text-muted" style={{ padding: 12, fontSize: 12 }}>
      No ticks recorded yet for this agent.
    </div>
  );
  return (
    <div style={{ padding: '8px 0', maxHeight: 420, overflowY: 'auto' }}>
      {ticks.map(t => (
        <div key={t.id} style={{ borderBottom: '1px solid #26262b' }}>
          <div onClick={() => setExpanded(expanded === t.id ? null : t.id)}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', cursor: 'pointer' }}>
            <span style={{ width: 8, height: 8, borderRadius: 999, flexShrink: 0,
              background: STATUS_COLORS[t.status] || '#9ca3af' }} />
            <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#9ca3af', whiteSpace: 'nowrap' }}>
              {t.timestamp ? new Date(t.timestamp).toLocaleString() : ''}
            </span>
            <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 999, whiteSpace: 'nowrap',
              background: t.trigger === 'manual' ? '#4a9eff22' : '#26262b',
              color: t.trigger === 'manual' ? '#4a9eff' : '#6b7280',
              border: '1px solid ' + (t.trigger === 'manual' ? '#4a9eff44' : '#3a3a40') }}>
              {t.trigger}
            </span>
            <span style={{ flex: 1, fontSize: 12, color: '#f2f2f3',
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {t.summary || '(no summary)'}
            </span>
            <span style={{ fontSize: 10, color: '#4b5563', whiteSpace: 'nowrap' }}>
              {t.duration_ms != null ? `${(t.duration_ms / 1000).toFixed(1)}s` : ''}
            </span>
            <span style={{ fontSize: 10, color: '#4b5563' }}>{expanded === t.id ? '▾' : '▸'}</span>
          </div>
          {expanded === t.id && (
            <pre style={{ margin: '0 10px 10px', padding: 10, fontSize: 11, lineHeight: 1.5,
              background: '#101013', border: '1px solid #26262b', borderRadius: 6,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: '#cfcfd4', maxHeight: 260, overflowY: 'auto' }}>
              {t.answer || t.details || '(empty answer)'}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}

function AutonomousTab({ agents, onReload }) {
  const [status, setStatus] = useState({});       // agent_id -> status info
  const [intervals, setIntervals] = useState({}); // agent_id -> edited value
  const [busy, setBusy] = useState({});           // agent_id -> 'tick' | 'save'
  const [openHistory, setOpenHistory] = useState(null);
  const [historyKey, setHistoryKey] = useState(0);

  async function loadStatus() {
    try {
      const r = await getAutonomousStatus();
      const map = {};
      (r.agents || []).forEach(a => { map[a.agent_id] = a; });
      setStatus(map);
    } catch (_) {}
  }

  useEffect(() => {
    loadStatus();
    const timer = setInterval(loadStatus, 5000);
    return () => clearInterval(timer);
  }, []);

  async function runNow(agent) {
    setBusy(b => ({ ...b, [agent.id]: 'tick' }));
    try {
      await tickAgent(agent.id);
      await loadStatus();
      setHistoryKey(k => k + 1);
    } catch (e) { alert('Tick failed: ' + e.message); }
    finally { setBusy(b => ({ ...b, [agent.id]: null })); }
  }

  async function saveInterval(agent) {
    const raw = intervals[agent.id];
    const value = Math.max(30, parseInt(raw, 10) || 30);
    setBusy(b => ({ ...b, [agent.id]: 'save' }));
    try {
      await updateAgent(agent.id, {
        ...agent,
        autonomous: { ...(agent.autonomous || {}), interval_seconds: value },
      });
      setIntervals(iv => ({ ...iv, [agent.id]: undefined }));
      onReload();
      await loadStatus();
    } catch (e) { alert('Save failed: ' + e.message); }
    finally { setBusy(b => ({ ...b, [agent.id]: null })); }
  }

  const configured = agents.filter(a => a.autonomous);
  const unconfigured = agents.filter(a => !a.autonomous);

  return (
    <div>
      {configured.length === 0 && (
        <div className="text-muted" style={{ padding: '16px 0', fontSize: 13 }}>
          No agents with autonomous mode configured. Enable it from Agents → Edit → Autonomous Mode.
        </div>
      )}
      {configured.map(agent => {
        const st = status[agent.id] || {};
        const verdict = st.last_verdict;
        const enabled = !!(agent.autonomous && agent.autonomous.enabled);
        const editedInterval = intervals[agent.id];
        const currentInterval = agent.autonomous?.interval_seconds ?? 300;
        return (
          <div key={agent.id} style={{ border: '1px solid #3a3a40', borderRadius: 8,
            marginBottom: 14, background: '#1c1c20', overflow: 'hidden' }}>
            {/* ── Row: identity + interval + actions ─────────────────── */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', flexWrap: 'wrap' }}>
              <span style={{ width: 9, height: 9, borderRadius: 999, flexShrink: 0,
                background: st.loop_active ? '#4ade80' : (enabled ? '#fbbf24' : '#4b5563') }}
                title={st.loop_active ? 'Loop running' : (enabled ? 'Enabled, loop not active' : 'Disabled')} />
              <span style={{ fontWeight: 600, fontSize: 14 }}>{agent.name}</span>
              <span style={{ fontSize: 11, color: '#6b7280' }}>
                {st.tick_running ? 'tick in progress…'
                  : st.last_tick_at ? `last tick: ${new Date(st.last_tick_at).toLocaleString()}` : 'no ticks yet'}
              </span>
              <span style={{ flex: 1 }} />
              <span style={{ fontSize: 12, color: '#9ca3af' }}>every</span>
              <input className="form-input" type="number" min={30}
                style={{ width: 90, padding: '4px 8px', fontSize: 12 }}
                value={editedInterval !== undefined ? editedInterval : currentInterval}
                onChange={e => setIntervals(iv => ({ ...iv, [agent.id]: e.target.value }))} />
              <span style={{ fontSize: 12, color: '#9ca3af' }}>s</span>
              {editedInterval !== undefined && String(editedInterval) !== String(currentInterval) && (
                <button className="btn-primary btn-sm" disabled={busy[agent.id] === 'save'}
                  onClick={() => saveInterval(agent)}>
                  {busy[agent.id] === 'save' ? 'Saving…' : 'Save'}
                </button>
              )}
              <button className="btn-sm" disabled={busy[agent.id] === 'tick' || st.tick_running}
                onClick={() => runNow(agent)}>
                {busy[agent.id] === 'tick' ? 'Running…' : '▶ Run now'}
              </button>
              <button className="btn-sm"
                onClick={() => setOpenHistory(openHistory === agent.id ? null : agent.id)}>
                History {openHistory === agent.id ? '▾' : '▸'}
              </button>
            </div>
            {/* ── Last verdict ─────────────────────────────────────────── */}
            {verdict && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 14px 12px' }}>
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, fontWeight: 600,
                  background: (STATUS_COLORS[verdict.status] || '#9ca3af') + '22',
                  color: STATUS_COLORS[verdict.status] || '#9ca3af',
                  border: '1px solid ' + (STATUS_COLORS[verdict.status] || '#9ca3af') + '44' }}>
                  {verdict.status}
                </span>
                <span style={{ fontSize: 12, color: '#cfcfd4' }}>{verdict.summary}</span>
              </div>
            )}
            {/* ── Tick history ─────────────────────────────────────────── */}
            {openHistory === agent.id && (
              <div style={{ borderTop: '1px solid #3a3a40', background: '#18181b' }}>
                <TickHistory agentId={agent.id} refreshKey={historyKey} />
              </div>
            )}
          </div>
        );
      })}
      {unconfigured.length > 0 && (
        <div className="text-muted" style={{ fontSize: 12, marginTop: 8 }}>
          Not configured: {unconfigured.map(a => a.name).join(', ')} — enable autonomous mode from Agents → Edit.
        </div>
      )}
    </div>
  );
}

function AgentsTab() {
  const [agents, setAgents] = useState([]);
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editAgent, setEditAgent] = useState(null);
  const [skillEdit, setSkillEdit] = useState(null);
  const [subTab, setSubTab] = useState('agents');

  async function load() {
    setLoading(true);
    try {
      const [ag, sk] = await Promise.all([getAgents(), getSkills()]);
      setAgents(ag.agents || []);
      setSkills(sk.skills || []);
    } catch (_) {} finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function handleDeleteAgent(id) {
    if (!confirm('Delete this agent?')) return;
    await deleteAgent(id).catch(() => {}); load();
  }
  async function handleDeleteSkill(name) {
    if (!confirm('Delete skill "' + name + '"?')) return;
    await deleteSkill(name).catch(() => {}); load();
  }

  if (loading) return <div className="loading-text">Loading...</div>;
  return (
    <div>
      <div className="sub-tabs" style={{ marginBottom: 16 }}>
        <button className={'sub-tab-btn' + (subTab === 'agents' ? ' active' : '')} onClick={() => setSubTab('agents')}>Agents ({agents.length})</button>
        <button className={'sub-tab-btn' + (subTab === 'skills' ? ' active' : '')} onClick={() => setSubTab('skills')}>Skills ({skills.length})</button>
        <button className={'sub-tab-btn' + (subTab === 'mcp' ? ' active' : '')} onClick={() => setSubTab('mcp')}>MCP Servers</button>
        <button className={'sub-tab-btn' + (subTab === 'autonomous' ? ' active' : '')} onClick={() => setSubTab('autonomous')}>Autonomous</button>
      </div>

      {subTab === 'agents' && (
        <div>
          <div style={{ marginBottom: 12 }}>
            <button className="btn-primary btn-sm" onClick={() => setEditAgent({})}>+ New Agent</button>
          </div>
          {agents.length === 0 && <div className="text-muted" style={{ padding: '20px 0' }}>No agents configured yet.</div>}
          <table className="data-table">
            <thead><tr><th>Name</th><th>Description</th><th>Skills</th><th>Autonomous</th><th></th></tr></thead>
            <tbody>
              {agents.map(a => (
                <tr key={a.id}>
                  <td style={{ fontWeight: 600 }}>{a.name}</td>
                  <td className="text-muted">{a.description}</td>
                  <td>
                    {(a.skills || []).map(s => (
                      <span key={s} style={{ fontSize: 11, padding: '2px 7px', borderRadius: 999, marginRight: 4,
                        background: '#4a9eff22', color: '#4a9eff', border: '1px solid #4a9eff44' }}>{s}</span>
                    ))}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {a.autonomous && a.autonomous.enabled ? (
                      <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 999,
                        background: '#4ade8022', color: '#4ade80', border: '1px solid #4ade8044' }}>
                        ● every {a.autonomous.interval_seconds || 300}s
                      </span>
                    ) : (
                      <span style={{ fontSize: 11, color: '#4b5563' }}>—</span>
                    )}
                  </td>
                  <td>
                    <div className="row" style={{ justifyContent: 'flex-end', gap: 6 }}>
                      <button className="btn-sm" onClick={() => setEditAgent(a)}>Edit</button>
                      <button className="btn-danger btn-sm" onClick={() => handleDeleteAgent(a.id)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {subTab === 'skills' && (
        <div>
          {skillEdit !== null ? (
            <SkillEditor skillName={skillEdit || null} onClose={() => setSkillEdit(null)} onSave={() => { setSkillEdit(null); load(); }} />
          ) : (
            <>
              <div style={{ marginBottom: 12 }}>
                <button className="btn-primary btn-sm" onClick={() => setSkillEdit('')}>+ New Skill</button>
              </div>
              {skills.length === 0 && <div className="text-muted" style={{ padding: '20px 0' }}>No skills found in skills/</div>}
              <table className="data-table">
                <thead><tr><th>Name</th><th>Description</th><th></th></tr></thead>
                <tbody>
                  {skills.map(s => (
                    <tr key={s.name}>
                      <td style={{ fontWeight: 600, fontFamily: 'monospace', fontSize: 12 }}>{s.name}</td>
                      <td className="text-muted">{s.description}</td>
                      <td>
                        <div className="row" style={{ justifyContent: 'flex-end', gap: 6 }}>
                          <button className="btn-sm" onClick={() => setSkillEdit(s.name)}>Edit</button>
                          <button className="btn-danger btn-sm" onClick={() => handleDeleteSkill(s.name)}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}

      {subTab === 'mcp' && (
        <McpServersTab agents={agents} onReload={load} />
      )}

      {subTab === 'autonomous' && (
        <AutonomousTab agents={agents} onReload={load} />
      )}

      {editAgent !== null && (
        <AgentModal agent={editAgent && editAgent.id ? editAgent : null} allSkills={skills}
          onClose={() => setEditAgent(null)} onSave={() => { setEditAgent(null); load(); }} />
      )}
    </div>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState('agents');
  const tabs = [
    { id: 'agents',  label: 'Agents & Skills' },
    { id: 'llm',     label: 'LLM Settings' },
    { id: 'mongodb', label: 'MongoDB' },
  ];
  return (
    <div>
      <h1 className="page-title">Settings</h1>
      <div className="sub-tabs">
        {tabs.map(t => (
          <button key={t.id} className={'sub-tab-btn' + (tab === t.id ? ' active' : '')} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'agents'  && <AgentsTab />}
      {tab === 'llm'     && <LLMSettingsTab />}
      {tab === 'mongodb' && <MongoDBTab />}
    </div>
  );
}
