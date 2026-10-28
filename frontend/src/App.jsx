import { useState } from 'react';
import './App.css';
import ChatPage         from './pages/ChatPage.jsx';
import ContextPage      from './pages/ContextPage.jsx';
import MCPPage          from './pages/MCPPage.jsx';
import SettingsPage     from './pages/SettingsPage.jsx';
import NotificationBell from './components/NotificationBell.jsx';

const TABS = [
  { id: 'chat',     label: '🤖 Chat' },
  { id: 'context',  label: '📋 Context' },
  { id: 'mcp',      label: 'MCP Gateway' },
  { id: 'settings', label: 'Settings' },
];

export default function App() {
  const [active, setActive] = useState('chat');

  const page = {
    chat:     <ChatPage />,
    context:  <ContextPage />,
    mcp:      <MCPPage />,
    settings: <SettingsPage />,
  }[active];

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">MASTRO</span>
        <nav className="tab-bar">
          {TABS.map(t => (
            <button
              key={t.id}
              className={`tab-btn${active === t.id ? ' active' : ''}`}
              onClick={() => setActive(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <NotificationBell />
      </header>
      <main className="app-body">{page}</main>
    </div>
  );
}
