import { useState, useEffect, useRef } from 'react';
import {
  listNotifications, markNotificationRead, markAllNotificationsRead,
  NOTIFICATIONS_STREAM_URL,
} from '../api/mastro.js';

const SEVERITY_COLORS = {
  critical: '#f87171',
  warning:  '#fbbf24',
  ok:       '#4ade80',
};

export default function NotificationBell() {
  const [items, setItems]   = useState([]);
  const [open, setOpen]     = useState(false);
  const wrapRef             = useRef(null);

  const unread = items.filter(n => !n.read).length;

  // Initial load
  useEffect(() => {
    listNotifications(50).then(r => setItems(r.notifications || [])).catch(() => {});
  }, []);

  // Real-time updates via SSE
  useEffect(() => {
    const es = new EventSource(NOTIFICATIONS_STREAM_URL);
    es.onmessage = (e) => {
      try {
        const notif = JSON.parse(e.data);
        setItems(prev => [notif, ...prev.filter(n => n.id !== notif.id)].slice(0, 50));
      } catch (_) { /* ignore malformed events */ }
    };
    es.onerror = () => { /* EventSource auto-reconnects */ };
    return () => es.close();
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function onClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  async function handleRead(id) {
    setItems(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
    try { await markNotificationRead(id); } catch (_) {}
  }

  async function handleReadAll() {
    setItems(prev => prev.map(n => ({ ...n, read: true })));
    try { await markAllNotificationsRead(); } catch (_) {}
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative', marginLeft: 'auto' }}>
      <button
        onClick={() => setOpen(o => !o)}
        title="Notifications"
        style={{
          background: 'transparent', border: 'none', cursor: 'pointer',
          fontSize: 18, padding: '6px 8px', position: 'relative', lineHeight: 1,
        }}>
        🔔
        {unread > 0 && (
          <span style={{
            position: 'absolute', top: 0, right: 0,
            background: '#f87171', color: '#fff', borderRadius: 999,
            fontSize: 10, fontWeight: 700, minWidth: 16, height: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '0 4px',
          }}>
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          position: 'absolute', right: 0, top: 'calc(100% + 8px)',
          width: 360, maxHeight: 440, overflowY: 'auto', zIndex: 200,
          background: '#18181b', border: '1px solid #3a3a40', borderRadius: 8,
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', padding: '10px 12px',
            borderBottom: '1px solid #3a3a40',
          }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#f2f2f3' }}>
              Notifications
            </span>
            <span style={{ flex: 1 }} />
            {unread > 0 && (
              <button onClick={handleReadAll}
                style={{
                  background: 'transparent', border: 'none', cursor: 'pointer',
                  fontSize: 11, color: '#4a9eff', padding: 0,
                }}>
                Mark all read
              </button>
            )}
          </div>

          {items.length === 0 ? (
            <div style={{ padding: 20, fontSize: 12, color: '#6b7280', textAlign: 'center' }}>
              No notifications
            </div>
          ) : items.map(n => (
            <div key={n.id}
              onClick={() => !n.read && handleRead(n.id)}
              style={{
                padding: '10px 12px', borderBottom: '1px solid #26262b',
                cursor: n.read ? 'default' : 'pointer',
                opacity: n.read ? 0.55 : 1,
              }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  width: 8, height: 8, borderRadius: 999, flexShrink: 0,
                  background: SEVERITY_COLORS[n.severity] || '#9ca3af',
                }} />
                <span style={{
                  fontSize: 12, fontWeight: 600, color: '#f2f2f3',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {n.title}
                </span>
              </div>
              <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
                {n.message}
              </div>
              <div style={{ fontSize: 10, color: '#4b5563', marginTop: 4 }}>
                {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
