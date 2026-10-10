import { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { MessageSquare, Upload, Library, Activity, Brain, ChevronLeft, ChevronRight, CheckCircle2, XCircle, Settings } from 'lucide-react';
import { getHealth, getSchemas } from '../api/client';
import './Layout.css';

const NAV_ITEMS = [
  { path: '/', icon: MessageSquare, label: 'Chat' },
  { path: '/ingest', icon: Upload, label: 'Ingest' },
  { path: '/library', icon: Library, label: 'Library' },
  { path: '/diagnostics', icon: Activity, label: 'Diagnostics' },
  { path: '/admin', icon: Settings, label: 'Admin' },
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
          <div className="sidebar-logo"><Brain size={32} className="text-primary" /></div>
          {!collapsed && (
            <div className="sidebar-title">
              <h1 className="gradient-text">CKP</h1>
              <span className="sidebar-subtitle">Cognitive Knowledge Platform</span>
            </div>
          )}
          <button className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)} title={collapsed ? 'Expand' : 'Collapse'}>
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {!collapsed && (
          <div className="sidebar-schema">
            <label className="sidebar-label">Active Schema</label>
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
              <span className="nav-icon"><item.icon size={20} /></span>
              {!collapsed && <span className="nav-label">{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-status">
            {isHealthy ? <CheckCircle2 size={16} className="text-success" /> : <XCircle size={16} className="text-error" />}
            {!collapsed && (
              <span className={isHealthy ? 'text-success' : 'text-error'} style={{ fontWeight: 500, fontSize: '0.85rem' }}>
                {isHealthy ? 'System Online' : 'Unreachable'}
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
