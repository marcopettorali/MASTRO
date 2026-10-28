import { useState, useEffect, useRef, useCallback } from 'react';
import {
  getMcpStatus,
  getMcpNodes,
  getMcpLogs,
  startMcpServer,
  stopMcpServer,
} from '../api/mastro.js';

// ── StatusBadge inline ────────────────────────────────────────────────────────
function RunBadge({ running }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 10px', borderRadius: 999, fontSize: 12, fontWeight: 700,
      background: running ? 'rgba(74,222,128,0.12)' : 'rgba(161,161,170,0.12)',
      color: running ? '#4ade80' : '#a1a1aa',
      border: `1px solid ${running ? '#4ade80' : '#3f3f46'}`,
    }}>
      <span style={{ fontSize: 8 }}>●</span>
      {running ? 'RUNNING' : 'STOPPED'}
    </span>
  );
}

// ── Log viewer ────────────────────────────────────────────────────────────────
function LogViewer({ running }) {
  const [lines, setLines]     = useState([]);
  const [autoScroll, setAuto] = useState(true);
  const endRef = useRef(null);

  const fetchLogs = useCallback(async () => {
    try {
      const r = await getMcpLogs(100);
      if (r.ok) setLines(r.lines || []);
    } catch (_) {}
  }, []);

  useEffect(() => {
    if (!running) return;
    fetchLogs();
    const t = setInterval(fetchLogs, 2000);
    return () => clearInterval(t);
  }, [running, fetchLogs]);

  useEffect(() => {
    if (autoScroll && endRef.current) endRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [lines, autoScroll]);

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="row" style={{ marginBottom: 8, alignItems: 'center' }}>
        <span className="card-title" style={{ margin: 0 }}>Log output</span>
        <span className="spacer" />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer' }}>
          <input type="checkbox" checked={autoScroll} onChange={e => setAuto(e.target.checked)} />
          Auto-scroll
        </label>
        <button className="btn-sm" style={{ marginLeft: 8 }} onClick={fetchLogs}>↻</button>
      </div>
      <div style={{
        background: 'rgba(0,0,0,0.4)', borderRadius: 6, padding: '10px 14px',
        fontFamily: 'monospace', fontSize: 11, lineHeight: 1.6,
        height: 260, overflowY: 'auto',
        border: '1px solid var(--border-dark, #27272a)',
      }}>
        {lines.length === 0
          ? <span style={{ color: '#52525b' }}>{running ? 'Waiting for output…' : 'Server not running.'}</span>
          : lines.map((l, i) => {
              const col = l.includes('ERROR') ? '#f87171'
                        : l.includes('WARN')  ? '#fbbf24'
                        : l.includes('INFO')  ? '#a5b4fc'
                        : '#d4d4d8';
              return <div key={i} style={{ color: col }}>{l}</div>;
            })
        }
        <div ref={endRef} />
      </div>
    </div>
  );
}

// ── MCPPage ───────────────────────────────────────────────────────────────────
export default function MCPPage() {
  // Status
  const [status,    setStatus]    = useState(null);
  const [loadingStatus, setLS]    = useState(true);

  // Available nodes from nodes_info
  const [availNodes, setAvailNodes] = useState({});   // {node_id: {host, runtime_port}}

  // Form state
  const [mockMode,    setMockMode]   = useState(false);
  const [selectedAll, setSelAll]     = useState(true);
  const [selectedIds, setSelIds]     = useState([]);
  const [transport,   setTransport]  = useState('http');
  const [port,        setPort]       = useState(8001);
  const [dryRun,      setDryRun]     = useState(false);

  // Action state
  const [busy,  setBusy]  = useState(false);
  const [error, setError] = useState(null);
  const [msg,   setMsg]   = useState(null);

  // ── Load status + nodes ────────────────────────────────────────────────────
  const refresh = useCallback(async () => {
    try {
      const [s, n] = await Promise.all([getMcpStatus(), getMcpNodes()]);
      setStatus(s);
      if (n.ok) {
        setAvailNodes(n.nodes || {});
        if (Object.keys(n.nodes || {}).length > 0 && selectedIds.length === 0) {
          setSelIds(Object.keys(n.nodes));
        }
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLS(false);
    }
  }, []); // eslint-disable-line

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  // ── Handlers ───────────────────────────────────────────────────────────────
  function toggleNode(id) {
    setSelIds(prev =>
      prev.includes(id) ? prev.filter(n => n !== id) : [...prev, id]
    );
  }

  async function handleStart() {
    setBusy(true); setError(null); setMsg(null);
    try {
      const nodeIds = mockMode ? null : (selectedAll ? null : selectedIds);
      const r = await startMcpServer({
        mock_mode:  mockMode,
        dry_run:    dryRun,
        transport,
        port,
        node_ids:   nodeIds,
      });
      if (r.ok) {
        setMsg(`MCP Gateway started (PID ${r.pid}).`);
        refresh();
      } else {
        setError(r.error || 'Start failed.');
      }
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function handleStop() {
    setBusy(true); setError(null); setMsg(null);
    try {
      const r = await stopMcpServer();
      if (r.ok) { setMsg('MCP Gateway stopped.'); refresh(); }
      else setError(r.error || 'Stop failed.');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const running    = status?.running === true;
  const nodeList   = Object.entries(availNodes);
  const hasNodes   = nodeList.length > 0;

  return (
    <div>
      <div className="row" style={{ marginBottom: 20 }}>
        <h1 className="page-title" style={{ margin: 0 }}>MASTRO MCP Gateway</h1>
        <span className="spacer" />
        <button onClick={refresh} style={{ fontSize: 13 }}>↻ Refresh</button>
      </div>

      {/* ── Status card ────────────────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row" style={{ alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span className="card-title" style={{ margin: 0 }}>Status</span>
          {loadingStatus
            ? <span className="text-muted" style={{ fontSize: 13 }}>Loading…</span>
            : <RunBadge running={running} />
          }
          {running && status.pid && (
            <span style={{ fontSize: 12, color: 'var(--text-on-dark-soft)' }}>
              PID {status.pid}
            </span>
          )}
          {running && status.mock_mode && (
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999,
              background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid #fbbf24' }}>
              MOCK MODE
            </span>
          )}
          {running && status.dry_run && (
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999,
              background: 'rgba(167,139,250,0.12)', color: '#a78bfa', border: '1px solid #a78bfa' }}>
              DRY RUN
            </span>
          )}
        </div>

        {running && (
          <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            {status.transport === 'http' && (
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-on-dark-soft)', marginBottom: 2 }}>URL (MCP Inspector)</div>
                <code style={{ fontSize: 12, background: 'rgba(0,0,0,0.3)', padding: '3px 8px', borderRadius: 4 }}>
                  {status.url}
                </code>
              </div>
            )}
            {status.node_ids && (
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-on-dark-soft)', marginBottom: 2 }}>Connected nodes</div>
                <div style={{ fontSize: 12 }}>{status.node_ids.join(', ')}</div>
              </div>
            )}
            {!status.node_ids && !status.mock_mode && (
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-on-dark-soft)', marginBottom: 2 }}>Connected nodes</div>
                <div style={{ fontSize: 12 }}>all</div>
              </div>
            )}
            {status.started_at && (
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-on-dark-soft)', marginBottom: 2 }}>Started</div>
                <div style={{ fontSize: 12 }}>{new Date(status.started_at).toLocaleTimeString()}</div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Config + controls ──────────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Configuration</div>

        {running && (
          <div style={{ fontSize: 13, color: 'var(--text-on-dark-soft)', marginBottom: 12 }}>
            The server is running. Stop it to change the configuration.
          </div>
        )}

        <div style={{ opacity: running ? 0.5 : 1, pointerEvents: running ? 'none' : 'auto' }}>

          {/* Mode: Mock / Real nodes */}
          <div style={{ marginBottom: 16 }}>
            <div className="form-label">Mode</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className={mockMode ? 'btn-primary' : ''}
                style={{ fontSize: 12, minWidth: 120,
                  ...(mockMode ? {} : { background: 'transparent',
                    border: '1px solid var(--border-dark, #3f3f46)', color: 'var(--text-on-dark-soft)' }) }}
                onClick={() => setMockMode(true)}
              >
                🎭 Mock Mode
              </button>
              <button
                className={!mockMode ? 'btn-primary' : ''}
                style={{ fontSize: 12, minWidth: 120,
                  ...(!mockMode ? {} : { background: 'transparent',
                    border: '1px solid var(--border-dark, #3f3f46)', color: 'var(--text-on-dark-soft)' }) }}
                onClick={() => setMockMode(false)}
              >
                🖥️ Real nodes
              </button>
            </div>
            {mockMode && (
              <div style={{ fontSize: 12, color: '#fbbf24', marginTop: 6 }}>
                Mock Mode: no connection to the orchestrator — simulated data.
              </div>
            )}
          </div>

          {/* Node selection (real mode only) */}
          {!mockMode && (
            <div style={{ marginBottom: 16 }}>
              <div className="form-label">Runtime nodes to connect</div>
              {!hasNodes ? (
                <div style={{ fontSize: 12, color: '#f87171' }}>
                  No node available from the orchestrator (or it is not reachable).
                  Configure the nodes in your orchestrator.
                </div>
              ) : (
                <>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6,
                    fontSize: 12, cursor: 'pointer', marginBottom: 8 }}>
                    <input
                      type="checkbox"
                      checked={selectedAll}
                      onChange={e => setSelAll(e.target.checked)}
                    />
                    <strong>All nodes</strong>
                  </label>
                  {!selectedAll && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingLeft: 8 }}>
                      {nodeList.map(([nid, meta]) => (
                        <label key={nid}
                          style={{ display: 'flex', alignItems: 'center', gap: 6,
                            fontSize: 12, cursor: 'pointer',
                            padding: '4px 10px', borderRadius: 6,
                            background: selectedIds.includes(nid)
                              ? 'rgba(74,158,255,0.12)' : 'rgba(255,255,255,0.03)',
                            border: `1px solid ${selectedIds.includes(nid) ? '#4a9eff' : '#3f3f46'}`,
                          }}>
                          <input
                            type="checkbox"
                            checked={selectedIds.includes(nid)}
                            onChange={() => toggleNode(nid)}
                          />
                          <span>
                            <strong>{nid}</strong>
                            <span style={{ color: 'var(--text-on-dark-soft)', marginLeft: 4 }}>
                              {meta.host}:{meta.runtime_port}
                            </span>
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Transport + Port */}
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
            <div>
              <div className="form-label">Transport</div>
              <select className="form-input" value={transport}
                onChange={e => setTransport(e.target.value)} style={{ width: 140 }}>
                <option value="http">HTTP (Inspector)</option>
                <option value="stdio">Stdio (Agent Engine)</option>
              </select>
            </div>
            {transport === 'http' && (
              <div>
                <div className="form-label">Port</div>
                <input className="form-input" type="number" value={port}
                  onChange={e => setPort(parseInt(e.target.value, 10) || 8001)}
                  style={{ width: 100 }} />
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 4 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6,
                fontSize: 12, cursor: 'pointer' }}>
                <input type="checkbox" checked={dryRun}
                  onChange={e => setDryRun(e.target.checked)} />
                Dry Run (no actuation)
              </label>
            </div>
          </div>

        </div>{/* end disabled overlay */}

        {/* Feedback */}
        {error && <div className="error-box"   style={{ marginBottom: 10 }}>{error}</div>}
        {msg   && <div className="success-box" style={{ marginBottom: 10 }}>{msg}</div>}

        {/* Buttons */}
        <div className="row" style={{ gap: 8 }}>
          {!running ? (
            <button className="btn-primary" onClick={handleStart} disabled={busy}>
              {busy ? '…' : '▶ Start MCP Gateway'}
            </button>
          ) : (
            <button
              className="btn-primary"
              style={{ background: 'var(--error-color, #e53e3e)' }}
              onClick={handleStop}
              disabled={busy}
            >
              {busy ? '…' : '■ Stop MCP Gateway'}
            </button>
          )}
        </div>

      </div>

      {/* ── Log viewer ─────────────────────────────────────────────────────── */}
      <LogViewer running={running} />
    </div>
  );
}
