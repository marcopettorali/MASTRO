import { useState, useEffect, useCallback } from 'react';
import {
  getContextEntries,
  getContextTypes,
  addContextEntry,
  enableContextEntry,
  disableContextEntry,
  revokeContextEntry,
} from '../api/mastro.js';

const REFRESH_MS = 10000;

// ── Helpers ───────────────────────────────────────────────────────────────────
const STATUS_CLASS = {
  active:   'status-ok',
  disabled: 'status-warn',
  consumed: 'status-ready',
  expired:  'status-unknown',
  revoked:  'status-error',
};

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString([], {
      year: '2-digit', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (_) { return iso; }
}

function toIsoOrNull(localValue) {
  // datetime-local gives a naive local timestamp: normalize to UTC ISO.
  if (!localValue) return null;
  const d = new Date(localValue);
  return isNaN(d.getTime()) ? null : d.toISOString();
}

// ── Add-entry modal ───────────────────────────────────────────────────────────
function AddEntryModal({ types, onClose, onSaved }) {
  const [type, setType]           = useState(types[0]?.type || '');
  const [summary, setSummary]     = useState('');
  const [mode, setMode]           = useState(types[0]?.default_mode || 'standing');
  const [validFrom, setValidFrom]   = useState('');
  const [validUntil, setValidUntil] = useState('');
  const [payloadText, setPayloadText] = useState('');
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');

  const selectType = (t) => {
    setType(t);
    const meta = types.find(x => x.type === t);
    if (meta) setMode(meta.default_mode);
  };

  const save = async () => {
    setError('');
    if (!summary.trim()) { setError('Summary is required.'); return; }
    let payload = null;
    if (payloadText.trim()) {
      try { payload = JSON.parse(payloadText); }
      catch (_) { setError('Payload is not valid JSON.'); return; }
    }
    setSaving(true);
    try {
      await addContextEntry({
        type,
        summary: summary.trim(),
        source: 'gui',
        mode,
        valid_from: toIsoOrNull(validFrom),
        valid_until: toIsoOrNull(validUntil),
        payload,
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(e.message || 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <h3 className="modal-title">Add context entry</h3>

        <div className="grid-2">
          <div className="form-group">
            <label className="form-label">Type</label>
            <select className="form-input" value={type} onChange={e => selectType(e.target.value)}>
              {types.map(t => (
                <option key={t.type} value={t.type}>{t.label} ({t.type})</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Mode</label>
            <select className="form-input" value={mode} onChange={e => setMode(e.target.value)}>
              <option value="standing">standing — injected at every run while valid</option>
              <option value="one_shot">one-shot — consumed by the first run</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Summary (injected into the agents' prompt)</label>
          <textarea
            className="form-textarea" rows={3} maxLength={500}
            placeholder="e.g. Node fog-2 under maintenance tomorrow 09:00-12:00 — drain workloads before the window."
            value={summary} onChange={e => setSummary(e.target.value)}
          />
        </div>

        <div className="grid-2">
          <div className="form-group">
            <label className="form-label">Valid from (optional)</label>
            <input type="datetime-local" className="form-input"
                   value={validFrom} onChange={e => setValidFrom(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Valid until (optional)</label>
            <input type="datetime-local" className="form-input"
                   value={validUntil} onChange={e => setValidUntil(e.target.value)} />
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Structured payload (optional, JSON)</label>
          <textarea
            className="form-textarea monospace" rows={3}
            placeholder='{"node_id": "fog-2", "window": "09:00-12:00"}'
            value={payloadText} onChange={e => setPayloadText(e.target.value)}
          />
        </div>

        {error && <div className="error-box">{error}</div>}

        <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
          <button className="btn-sm" onClick={onClose}>Cancel</button>
          <button className="btn-primary btn-sm" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Add entry'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Usage detail (expandable per row) ─────────────────────────────────────────
function UsageDetail({ entry }) {
  const usage = entry.usage || [];
  return (
    <div style={{
      background: 'rgba(0,0,0,0.35)', borderRadius: 6, padding: '10px 14px',
      fontSize: 12, border: '1px solid var(--border-dark, #27272a)',
    }}>
      <div style={{ marginBottom: 6 }} className="text-muted">
        Injected in <b>{entry.use_count || 0}</b> run(s)
        {entry.last_used_at && <> · last at {fmtDate(entry.last_used_at)}</>}
        {entry.status === 'consumed' && (
          <> · consumed by agent <b>{entry.consumed_by_agent || '?'}</b> (session {entry.consumed_by_session || '?'}) at {fmtDate(entry.consumed_at)}</>
        )}
        {entry.status === 'revoked' && (
          <> · revoked by <b>{entry.revoked_by || '?'}</b> at {fmtDate(entry.revoked_at)}</>
        )}
        {!entry.enabled && entry.status === 'active' && (
          <> · disabled by <b>{entry.disabled_by || '?'}</b> at {fmtDate(entry.disabled_at)}</>
        )}
      </div>
      {usage.length === 0
        ? <span style={{ color: '#52525b' }}>No runs have used this entry yet.</span>
        : (
          <table className="data-table" style={{ fontSize: 12 }}>
            <thead>
              <tr><th>When</th><th>Agent</th><th>Session</th></tr>
            </thead>
            <tbody>
              {[...usage].reverse().map((u, i) => (
                <tr key={i}>
                  <td>{fmtDate(u.timestamp)}</td>
                  <td>{u.agent_id || '—'}</td>
                  <td className="monospace">{u.session_id || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      {entry.payload && Object.keys(entry.payload).length > 0 && (
        <pre className="monospace" style={{ marginTop: 8, marginBottom: 0, whiteSpace: 'pre-wrap' }}>
          {JSON.stringify(entry.payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function ContextPage() {
  const [entries, setEntries]   = useState([]);
  const [types, setTypes]       = useState([]);
  const [view, setView]         = useState('active');   // active | history
  const [expanded, setExpanded] = useState(null);
  const [showAdd, setShowAdd]   = useState(false);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');

  const refresh = useCallback(async () => {
    try {
      const r = await getContextEntries(true, 200);
      if (r.ok) { setEntries(r.entries || []); setError(''); }
    } catch (e) {
      setError(e.message || 'Backend unreachable.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    getContextTypes().then(r => { if (r.ok) setTypes(r.types || []); }).catch(() => {});
    const t = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const toggleEnabled = async (entry) => {
    try {
      if (entry.enabled) await disableContextEntry(entry.id);
      else await enableContextEntry(entry.id);
      refresh();
    } catch (e) { setError(e.message); }
  };

  const revoke = async (entry) => {
    if (!window.confirm('Revoke this context entry? It will no longer be injected, but it stays in the history.')) return;
    try { await revokeContextEntry(entry.id); refresh(); }
    catch (e) { setError(e.message); }
  };

  const visible = entries.filter(e =>
    view === 'active'
      ? ['active', 'disabled'].includes(e.effective_status)
      : true
  );

  return (
    <div>
      <div className="row" style={{ marginBottom: 20 }}>
        <h2 className="page-title" style={{ margin: 0 }}>Operational Context</h2>
        <span className="spacer" />
        <button className="btn-primary btn-sm" onClick={() => setShowAdd(true)}>+ Add entry</button>
      </div>

      <p className="text-muted" style={{ fontSize: 13, marginTop: -8, marginBottom: 18 }}>
        Facts, constraints and upcoming events not visible through the agents' monitoring
        tools (maintenance windows, energy forecasts, operator directives). Active entries
        are injected into the system prompt of every agent run — chat and autonomous ticks —
        and every injection is tracked below.
      </p>

      <div className="sub-tabs">
        <button className={`sub-tab-btn${view === 'active' ? ' active' : ''}`}
                onClick={() => setView('active')}>
          Active ({entries.filter(e => ['active', 'disabled'].includes(e.effective_status)).length})
        </button>
        <button className={`sub-tab-btn${view === 'history' ? ' active' : ''}`}
                onClick={() => setView('history')}>
          All history ({entries.length})
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="card">
        {loading ? (
          <div className="loading-text">Loading context entries…</div>
        ) : visible.length === 0 ? (
          <div className="loading-text">
            {view === 'active' ? 'No active context entries.' : 'No context entries recorded yet.'}
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th style={{ width: '34%' }}>Summary</th>
                <th>Source</th>
                <th>Mode</th>
                <th>Created</th>
                <th>Valid until</th>
                <th>Uses</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map(e => (
                <>
                  <tr key={e.id} style={{ cursor: 'pointer' }}
                      onClick={() => setExpanded(expanded === e.id ? null : e.id)}>
                    <td className="monospace">{e.type}</td>
                    <td>{e.summary}</td>
                    <td className="monospace">{e.source}</td>
                    <td className="monospace">{e.mode === 'one_shot' ? 'one-shot' : 'standing'}</td>
                    <td>{fmtDate(e.created_at)}</td>
                    <td>{fmtDate(e.valid_until)}</td>
                    <td>
                      {e.use_count || 0}
                      {e.last_used_at && (
                        <span className="text-muted"> · {fmtDate(e.last_used_at)}</span>
                      )}
                    </td>
                    <td>
                      <span className={`status-badge ${STATUS_CLASS[e.effective_status] || 'status-unknown'}`}>
                        {e.effective_status}
                      </span>
                    </td>
                    <td onClick={ev => ev.stopPropagation()}>
                      {['active', 'disabled'].includes(e.effective_status) && (
                        <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                          <button className="btn-sm" onClick={() => toggleEnabled(e)}>
                            {e.enabled ? 'Disable' : 'Enable'}
                          </button>
                          <button className="btn-danger btn-sm" onClick={() => revoke(e)}>
                            Revoke
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                  {expanded === e.id && (
                    <tr key={`${e.id}-detail`}>
                      <td colSpan={9} style={{ padding: '4px 12px 12px' }}>
                        <UsageDetail entry={e} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showAdd && types.length > 0 && (
        <AddEntryModal
          types={types}
          onClose={() => setShowAdd(false)}
          onSaved={refresh}
        />
      )}
    </div>
  );
}
