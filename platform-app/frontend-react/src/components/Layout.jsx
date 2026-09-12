import { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { getHealth, getSchemas } from '../api/client';
import './Layout.css';

const NAV_ITEMS = [
  { path: '/', icon: '💬', label: 'Chat' },
  { path: '/ingest', icon: '📤', label: 'Ingest' },
  { path: '/library', icon: '🧩', label: 'Library' },
  { path: '/diagnostics', icon: '📊', label: 'Diagnostics' },
];

export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const [health, setHealth] = useState({});
  const [schemas, setSchemas] = useState([]);
  const [activeSchema, setActiveSchema] = useState('healthtech');
  const location = useLocation();

  useEffect(() => {
    getHealth().then(setHealth);
    getSchemas().then(s => { setSchemas(s); if (s.length) setActiveSchema(s[0]); });
    const interval = setInterval(() => getHealth().then(setHealth), 15000);
    return () => clearInterval(interval);
  }, []);

  const isHealthy = health.status === 'healthy';

  return (
    <div className="layout">
      <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-logo">🧠</div>
          {!collapsed && (
            <div className="sidebar-title">
              <h1 className="gradient-text">CKP</h1>
              <span className="sidebar-subtitle">Cognitive Knowledge Platform</span>
            </div>
          )}
          <button className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)} title={collapsed ? 'Expand' : 'Collapse'}>
            {collapsed ? '▶' : '◀'}
          </button>
        </div>

        {!collapsed && (
          <div className="sidebar-schema">
            <label className="sidebar-label">Schema</label>
            <select value={activeSchema} onChange={e => setActiveSchema(e.target.value)} className="sidebar-select">
              {schemas.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        )}

        <nav className="sidebar-nav">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              title={item.label}
            >
              <span className="nav-icon">{item.icon}</span>
              {!collapsed && <span className="nav-label">{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className={`status-dot ${isHealthy ? 'online' : 'offline'}`} />
            {!collapsed && (
              <span style={{ color: isHealthy ? 'var(--success)' : 'var(--error)', fontWeight: 500, fontSize: '0.82rem' }}>
                {isHealthy ? 'Connected' : 'Unreachable'}
              </span>
            )}
          </div>
          {!collapsed && (
            <div className="sidebar-version">
              <span className="sidebar-label">Version</span>
              <span style={{ color: 'var(--text-secondary)', fontWeight: 600, fontSize: '0.85rem' }}>
                v{health.version || '2.0.0'}
              </span>
            </div>
          )}
        </div>
      </aside>

      <main className={`main-content ${collapsed ? 'expanded' : ''}`}>
        {children}
      </main>
    </div>
  );
}
