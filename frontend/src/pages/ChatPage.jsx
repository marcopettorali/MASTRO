import { useState, useEffect, useRef, useCallback } from 'react';
import {
  getAgents, getMcpStatus,
  listSessions, getSession, deleteSession,
  getActiveRun, intentChatUrl, intentStreamUrl,
} from '../api/mastro.js';

// ── Reasoning step accordion ──────────────────────────────────────────────────

function ReasoningTrace({ steps }) {
  const [open, setOpen] = useState(false);
  if (!steps || steps.length === 0) return null;
  const thoughts = steps.filter(s => s.type === 'thought').length;
  const actions  = steps.filter(s => s.type === 'action').length;
  return (
    <div style={{ marginTop: 6 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'transparent', border: '1px solid #3a3a40', borderRadius: 5,
          color: '#6b7280', fontSize: 11, padding: '2px 8px', cursor: 'pointer',
        }}
      >
        {open ? '▾' : '▸'} {thoughts} thought{thoughts !== 1 ? 's' : ''}, {actions} tool call{actions !== 1 ? 's' : ''}
      </button>
      {open && (
        <div style={{ marginTop: 6, borderLeft: '2px solid #3a3a40', paddingLeft: 12 }}>
          {steps.map((s, i) => (
            <div key={i} style={{ marginBottom: 8, fontSize: 12 }}>
              {s.type === 'thought' && (
                <div>
                  <span style={{ color: '#818cf8', fontWeight: 600 }}>Thought {s.step}</span>
                  <div style={{ color: '#cfcfd4', marginTop: 2, whiteSpace: 'pre-wrap' }}>{s.content}</div>
                </div>
              )}
              {s.type === 'action' && (
                <div>
                  <span style={{ color: '#fbbf24', fontWeight: 600 }}>Action {s.step}</span>
                  {' — '}
                  <code style={{ color: '#38bdf8', fontSize: 11 }}>{s.tool}</code>
                  {s.args && Object.keys(s.args).length > 0 && (
                    <pre style={{
                      background: '#18181b', borderRadius: 4, padding: '4px 8px',
                      fontSize: 11, color: '#9ca3af', marginTop: 3, overflowX: 'auto',
                    }}>
                      {JSON.stringify(s.args, null, 2)}
                    </pre>
                  )}
                </div>
              )}
              {s.type === 'observation' && (
                <div>
                  <span style={{ color: '#4ade80', fontWeight: 600 }}>Observation {s.step}</span>
                  <pre style={{
                    background: '#18181b', borderRadius: 4, padding: '4px 8px',
                    fontSize: 11, color: '#9ca3af', marginTop: 3, overflowX: 'auto',
                    maxHeight: 160, overflow: 'auto',
                  }}>
                    {String(s.content).slice(0, 800)}{String(s.content).length > 800 ? '\n…' : ''}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Lightweight Markdown renderer (no external deps) ─────────────────────────

function MarkdownRenderer({ content }) {
  if (!content) return null;

  // Split into blocks (paragraphs, code fences, tables, lists)
  const blocks = [];
  const lines = content.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      blocks.push({ type: 'code', lang, text: codeLines.join('\n') });
      i++;
      continue;
    }

    // Heading
    const hMatch = line.match(/^(#{1,3})\s+(.+)/);
    if (hMatch) {
      blocks.push({ type: 'heading', level: hMatch[1].length, text: hMatch[2] });
      i++; continue;
    }

    // Table (starts with |)
    if (line.startsWith('|')) {
      const tableLines = [];
      while (i < lines.length && lines[i].startsWith('|')) {
        tableLines.push(lines[i]);
        i++;
      }
      blocks.push({ type: 'table', lines: tableLines });
      continue;
    }

    // Unordered list item
    if (/^(\s*[-*+]\s)/.test(line)) {
      const items = [];
      while (i < lines.length && /^(\s*[-*+]\s)/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s/, ''));
        i++;
      }
      blocks.push({ type: 'ul', items });
      continue;
    }

    // Ordered list item
    if (/^\d+\.\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ''));
        i++;
      }
      blocks.push({ type: 'ol', items });
      continue;
    }

    // Blank line — skip
    if (line.trim() === '') { i++; continue; }

    // Paragraph — accumulate until blank or block-level element
    const paraLines = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].startsWith('```') &&
      !lines[i].startsWith('#') &&
      !lines[i].startsWith('|') &&
      !/^(\s*[-*+]\s)/.test(lines[i]) &&
      !/^\d+\.\s/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length) blocks.push({ type: 'para', text: paraLines.join(' ') });
  }

  // Inline markdown: bold, italic, inline code
  function inline(text) {
    const parts = [];
    // Split on **bold**, *italic*, `code`
    const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
    let last = 0, m;
    let key = 0;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) parts.push(text.slice(last, m.index));
      const tok = m[0];
      if (tok.startsWith('**'))
        parts.push(<strong key={key++}>{tok.slice(2, -2)}</strong>);
      else if (tok.startsWith('`'))
        parts.push(<code key={key++} style={{ background: '#111', borderRadius: 3, padding: '1px 5px', fontSize: '0.88em', color: '#38bdf8' }}>{tok.slice(1, -1)}</code>);
      else
        parts.push(<em key={key++}>{tok.slice(1, -1)}</em>);
      last = m.index + tok.length;
    }
    if (last < text.length) parts.push(text.slice(last));
    return parts;
  }

  const s = {
    h1: { fontSize: 16, fontWeight: 700, color: '#f2f2f3', margin: '8px 0 4px' },
    h2: { fontSize: 14, fontWeight: 700, color: '#f2f2f3', margin: '6px 0 3px' },
    h3: { fontSize: 13, fontWeight: 600, color: '#cfcfd4', margin: '5px 0 2px' },
    p:  { margin: '4px 0', lineHeight: 1.6 },
    li: { margin: '2px 0', lineHeight: 1.5 },
    code: { display: 'block', background: '#111', borderRadius: 5, padding: '8px 10px',
      fontSize: 12, color: '#9ca3af', overflowX: 'auto', margin: '6px 0', fontFamily: 'monospace' },
    th: { padding: '4px 10px', borderBottom: '1px solid #3a3a40', fontWeight: 600,
      color: '#cfcfd4', textAlign: 'left', whiteSpace: 'nowrap' },
    td: { padding: '3px 10px', borderBottom: '1px solid #2a2a2e', color: '#d1d5db', whiteSpace: 'nowrap' },
  };

  return (
    <div>
      {blocks.map((b, bi) => {
        if (b.type === 'heading') {
          const hs = [s.h1, s.h2, s.h3][b.level - 1] || s.h3;
          return <div key={bi} style={hs}>{inline(b.text)}</div>;
        }
        if (b.type === 'code') return (
          <pre key={bi} style={s.code}>{b.text}</pre>
        );
        if (b.type === 'para') return (
          <p key={bi} style={s.p}>{inline(b.text)}</p>
        );
        if (b.type === 'ul') return (
          <ul key={bi} style={{ margin: '4px 0', paddingLeft: 18 }}>
            {b.items.map((it, ii) => <li key={ii} style={s.li}>{inline(it)}</li>)}
          </ul>
        );
        if (b.type === 'ol') return (
          <ol key={bi} style={{ margin: '4px 0', paddingLeft: 18 }}>
            {b.items.map((it, ii) => <li key={ii} style={s.li}>{inline(it)}</li>)}
          </ol>
        );
        if (b.type === 'table') {
          const rows = b.lines
            .filter(l => !l.match(/^\|[-| :]+\|$/))
            .map(l => l.replace(/^\||\|$/g, '').split('|').map(c => c.trim()));
          if (!rows.length) return null;
          const [head, ...body] = rows;
          return (
            <div key={bi} style={{ overflowX: 'auto', margin: '6px 0' }}>
              <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%' }}>
                <thead>
                  <tr>{head.map((c, ci) => <th key={ci} style={s.th}>{inline(c)}</th>)}</tr>
                </thead>
                <tbody>
                  {body.map((row, ri) => (
                    <tr key={ri}>{row.map((c, ci) => <td key={ci} style={s.td}>{inline(c)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

// ── Chat message bubble ───────────────────────────────────────────────────────

function Message({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      alignItems: isUser ? 'flex-end' : 'flex-start',
      marginBottom: 14,
    }}>
      <div style={{
        maxWidth: '82%',
        background: isUser ? '#4a9eff22' : '#2a2a2e',
        border: `1px solid ${isUser ? '#4a9eff55' : '#3a3a40'}`,
        borderRadius: isUser ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
        padding: '10px 14px',
        fontSize: 14, color: '#f2f2f3', lineHeight: 1.55,
        wordBreak: 'break-word',
      }}>
        {isUser ? (
          <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
        ) : (
          msg.streaming
            ? <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}<span style={{ display: 'inline-block', width: 8, height: 14, background: '#4a9eff', marginLeft: 2, borderRadius: 2, animation: 'blink 0.8s step-end infinite' }} /></span>
            : <MarkdownRenderer content={msg.content} />
        )}
      </div>
      {msg.reasoning_steps && <ReasoningTrace steps={msg.reasoning_steps} />}
      {msg.timestamp && (
        <div style={{ fontSize: 10, color: '#4b5563', marginTop: 3 }}>
          {new Date(msg.timestamp).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}

// ── Live streaming step indicator ─────────────────────────────────────────────

function StreamingStatus({ status }) {
  if (!status) return null;
  const colors = { thought: '#818cf8', action: '#fbbf24', observation: '#4ade80' };
  const labels = { thought: '💭 Reasoning…', action: '⚡ Calling tool…', observation: '👁 Observing…' };
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px',
      borderRadius: 6, fontSize: 12, background: '#18181b', border: '1px solid #3a3a40',
      color: colors[status.type] || '#cfcfd4', marginBottom: 8,
    }}>
      <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>⟳</span>
      {labels[status.type] || status.type}
      {status.tool && <code style={{ color: '#38bdf8', fontSize: 11 }}>{status.tool}</code>}
    </div>
  );
}

// ── Session history panel ─────────────────────────────────────────────────────

function SessionPanel({ agentId, activeSessionId, onSelect, onDelete, refreshKey }) {
  const [sessions, setSessions] = useState([]);
  useEffect(() => {
    listSessions(agentId).then(r => setSessions(r.sessions || [])).catch(() => {});
  }, [agentId, refreshKey]);

  if (sessions.length === 0) return (
    <div style={{ color: '#4b5563', fontSize: 12, padding: '12px 0', textAlign: 'center' }}>
      No past sessions
    </div>
  );
  return (
    <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 280px)' }}>
      {sessions.map(s => (
        <div key={s.id} onClick={() => onSelect(s.id)} style={{
          padding: '8px 10px', borderRadius: 6, marginBottom: 4, cursor: 'pointer',
          background: s.id === activeSessionId ? '#4a9eff22' : 'transparent',
          border: `1px solid ${s.id === activeSessionId ? '#4a9eff55' : 'transparent'}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ flex: 1, fontSize: 12, color: '#f2f2f3', whiteSpace: 'nowrap',
              overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {s.agent_name || 'Session'}
            </span>
            {s.session_type === 'autonomous' && (
              <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 999,
                background: '#4ade8022', color: '#4ade80', border: '1px solid #4ade8044' }}>
                auto
              </span>
            )}
            <button onClick={e => { e.stopPropagation(); onDelete(s.id); }}
              style={{ background: 'transparent', border: 'none', color: '#6b7280',
                fontSize: 13, padding: 0, cursor: 'pointer' }}>✕</button>
          </div>
          <div style={{ fontSize: 10, color: '#4b5563', marginTop: 2 }}>
            {s.updated_at ? new Date(s.updated_at).toLocaleString() : ''}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main ChatPage ─────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [agents, setAgents]             = useState([]);
  const [agentId, setAgentId]           = useState('');
  const [mcpRunning, setMcpRunning]     = useState(false);
  const [messages, setMessages]         = useState([]);
  const [input, setInput]               = useState('');
  const [sending, setSending]           = useState(false);
  const [streamStatus, setStreamStatus] = useState(null);
  const [sessionId, setSessionId]       = useState(null);
  const [sessionRefresh, setSessionRefresh] = useState(0);
  const [showHistory, setShowHistory]   = useState(true);
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);
  const abortRef  = useRef(null);    // AbortController for the current SSE fetch
  const mountedRef = useRef(true);   // guard against setState after unmount

  // Track mount status and cancel any in-flight stream on unmount.
  // The run keeps executing server-side and persists on its own.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    getAgents().then(r => {
      const list = r.agents || [];
      setAgents(list);
      if (list.length > 0) setAgentId(list[0].id);
    }).catch(() => {});
    getMcpStatus().then(r => setMcpRunning(r.running || false)).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamStatus]);

  // Consume an SSE response (from a fresh POST or a reconnect GET).
  // Updates the last assistant bubble in place. Aborting the fetch ends it cleanly.
  const consumeStream = useCallback(async (resp) => {
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const collectedSteps = [];

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          let evt;
          try { evt = JSON.parse(line.slice(5).trim()); } catch (_) { continue; }
          if (!mountedRef.current) continue;

          if (evt.type === 'token') {
            setMessages(prev => {
              const u = [...prev];
              const last = { ...u[u.length - 1] };
              last.content = (last.content || '') + (evt.content || '');
              u[u.length - 1] = last;
              return u;
            });
            setStreamStatus(null);
          } else if (evt.type === 'thought') {
            setStreamStatus({ type: 'thought' });
            collectedSteps.push(evt);
          } else if (evt.type === 'action') {
            setStreamStatus({ type: 'action', tool: evt.tool });
            collectedSteps.push(evt);
          } else if (evt.type === 'observation') {
            setStreamStatus({ type: 'observation' });
            collectedSteps.push(evt);
          } else if (evt.type === 'done') {
            setMessages(prev => {
              const u = [...prev];
              const last = { ...u[u.length - 1] };
              last.streaming = false;
              last.reasoning_steps = evt.reasoning_steps || collectedSteps;
              u[u.length - 1] = last;
              return u;
            });
            setStreamStatus(null);
            setSessionRefresh(k => k + 1);
          } else if (evt.type === 'error') {
            setMessages(prev => {
              const u = [...prev];
              const last = { ...u[u.length - 1] };
              last.content = `⚠ Error: ${evt.message}`;
              last.streaming = false;
              u[u.length - 1] = last;
              return u;
            });
            setStreamStatus(null);
          } else if (evt.type === 'warning') {
            // Show warnings as a system note inline
            setMessages(prev => {
              const u = [...prev];
              const last = { ...u[u.length - 1] };
              last.content = (last.content ? last.content + '\n' : '') + `ℹ ${evt.message}`;
              u[u.length - 1] = last;
              return u;
            });
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return;   // navigated away / superseded — run continues server-side
      if (!mountedRef.current) return;
      setMessages(prev => {
        const u = [...prev];
        const last = { ...u[u.length - 1] };
        last.content = `⚠ Connection error: ${err.message}`;
        last.streaming = false;
        u[u.length - 1] = last;
        return u;
      });
      setStreamStatus(null);
    }
  }, []);

  // If a run is still in progress for this session, resume observing it.
  const reconnectIfActive = useCallback(async (sid) => {
    if (!sid) return;
    let info;
    try { info = await getActiveRun(sid); } catch (_) { return; }
    if (!mountedRef.current || !info?.ok || !info.run_id) return;

    setSending(true);
    setStreamStatus(null);
    setMessages(prev => [
      ...prev,
      { role: 'user', content: info.user_message || '', timestamp: new Date().toISOString() },
      { role: 'assistant', content: '', streaming: true,
        timestamp: new Date().toISOString(), reasoning_steps: [] },
    ]);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const resp = await fetch(intentStreamUrl(info.run_id), { signal: controller.signal });
      await consumeStream(resp);
    } catch (err) {
      if (err.name !== 'AbortError' && mountedRef.current) setStreamStatus(null);
    } finally {
      if (mountedRef.current) setSending(false);
    }
  }, [consumeStream]);

  const startNewSession = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]); setSessionId(null); setStreamStatus(null); setSending(false);
  }, []);

  const loadSession = useCallback(async (sid) => {
    abortRef.current?.abort();   // stop observing the current run before switching
    try {
      const r = await getSession(sid);
      if (r.ok && r.session && mountedRef.current) {
        setSessionId(sid);
        setMessages(r.session.messages || []);
        setStreamStatus(null);
        setSending(false);
      }
    } catch (_) {}
    // If a turn is still running for this session, resume its live stream.
    await reconnectIfActive(sid);
  }, [reconnectIfActive]);

  const handleDeleteSession = useCallback(async (sid) => {
    await deleteSession(sid);
    if (sid === sessionId) startNewSession();
    setSessionRefresh(k => k + 1);
  }, [sessionId, startNewSession]);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || sending || !agentId) return;
    const userMsg = input.trim();
    setInput('');
    setSending(true);
    setStreamStatus(null);

    const userEntry      = { role: 'user',      content: userMsg, timestamp: new Date().toISOString() };
    const assistantEntry = { role: 'assistant', content: '', streaming: true,
      timestamp: new Date().toISOString(), reasoning_steps: [] };
    setMessages(prev => [...prev, userEntry, assistantEntry]);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const resp = await fetch(intentChatUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId, message: userMsg, session_id: sessionId || undefined }),
        signal: controller.signal,
      });

      const newSid = resp.headers.get('X-Session-Id');
      if (newSid && mountedRef.current) setSessionId(newSid);

      await consumeStream(resp);
    } catch (err) {
      if (err.name === 'AbortError') return;   // navigated away — run continues server-side
      if (!mountedRef.current) return;
      setMessages(prev => {
        const u = [...prev];
        const last = { ...u[u.length - 1] };
        last.content = `⚠ Connection error: ${err.message}`;
        last.streaming = false;
        u[u.length - 1] = last;
        return u;
      });
      setStreamStatus(null);
    } finally {
      if (mountedRef.current) {
        setSending(false);
        inputRef.current?.focus();
      }
    }
  }, [input, sending, agentId, sessionId, consumeStream]);

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const selectedAgent = agents.find(a => a.id === agentId);

  return (
    <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 100px)', minHeight: 500 }}>
      <style>{`
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes spin  { to{transform:rotate(360deg)} }
      `}</style>

      {/* History sidebar */}
      {showHistory && (
        <div style={{ width: 220, flexShrink: 0, background: '#18181b',
          border: '1px solid #3a3a40', borderRadius: 8, padding: 12,
          display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: '#cfcfd4',
              textTransform: 'uppercase', letterSpacing: '0.06em' }}>History</span>
            <button className="btn-primary btn-sm" onClick={startNewSession}>+ New</button>
          </div>
          <SessionPanel agentId={agentId} activeSessionId={sessionId}
            onSelect={loadSession} onDelete={handleDeleteSession} refreshKey={sessionRefresh} />
        </div>
      )}

      {/* Main chat */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>

        {/* Toolbar — agent selector + MCP status only */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <select className="form-input" style={{ maxWidth: 280, flex: '1 1 180px' }}
            value={agentId} onChange={e => { setAgentId(e.target.value); startNewSession(); }}>
            {agents.length === 0 && <option value="">No agents configured</option>}
            {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>

          <span style={{
            fontSize: 11, padding: '3px 10px', borderRadius: 999, whiteSpace: 'nowrap',
            background: mcpRunning ? 'rgba(74,222,128,0.12)' : 'rgba(161,161,170,0.12)',
            color: mcpRunning ? '#4ade80' : '#a1a1aa',
            border: `1px solid ${mcpRunning ? '#4ade80' : '#3f3f46'}`,
          }}>
            ● MCP {mcpRunning ? 'Running' : 'Stopped'}
          </span>

          <button className="btn-sm" onClick={() => setShowHistory(h => !h)} style={{ marginLeft: 'auto' }}>
            {showHistory ? '◀ Hide' : '▶ History'}
          </button>
        </div>

        {/* Agent info line */}
        {selectedAgent && (
          <div style={{ fontSize: 12, color: '#6b7280' }}>
            <span style={{ color: '#9ca3af' }}>{selectedAgent.description}</span>
            {selectedAgent.skills?.length > 0 && (
              <span style={{ color: '#4b5563' }}>
                {' · '}Skills: {selectedAgent.skills.join(', ')}
              </span>
            )}
          </div>
        )}

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 2px', display: 'flex', flexDirection: 'column' }}>
          {messages.length === 0 && (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#4b5563', flexDirection: 'column', gap: 8 }}>
              <div style={{ fontSize: 32 }}>🤖</div>
              <div style={{ fontSize: 14 }}>
                {agents.length === 0
                  ? 'Configure an agent in Settings → Agents & Skills'
                  : `Start a conversation with ${selectedAgent?.name || 'the agent'}`}
              </div>
              {!mcpRunning && (
                <div style={{ fontSize: 12, color: '#fbbf24', marginTop: 4 }}>
                  ⚠ MCP server is not running. Start it from the MCP tab for tool access.
                </div>
              )}

            </div>
          )}
          {messages.map((msg, i) => <Message key={i} msg={msg} />)}
          <StreamingStatus status={streamStatus} />
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end',
          background: '#18181b', border: '1px solid #3a3a40',
          borderRadius: 8, padding: '8px 10px' }}>
          <textarea ref={inputRef} className="form-textarea" rows={2}
            style={{ flex: 1, resize: 'none', border: 'none', background: 'transparent',
              fontSize: 14, padding: 0, outline: 'none', color: '#f2f2f3',
              minHeight: 40, maxHeight: 120 }}
            placeholder={sending ? 'Agent is thinking…' : 'Send a message… (Enter to send, Shift+Enter for newline)'}
            value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey} disabled={sending || !agentId} />
          <button className="btn-primary"
            style={{ alignSelf: 'flex-end', minWidth: 68, height: 38 }}
            onClick={sendMessage} disabled={sending || !input.trim() || !agentId}>
            {sending ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}
