import { useState, useEffect } from 'react';
import { getHealth, getDiagnostics, getSchemas, getSkills, getPrompts } from '../api/client';
import './DiagnosticsPage.css';

export default function DiagnosticsPage() {
  const [health, setHealth] = useState({});
  const [diag, setDiag] = useState({});
  const [schemas, setSchemas] = useState([]);
  const [skillCount, setSkillCount] = useState(0);
  const [promptCount, setPromptCount] = useState(0);

  useEffect(() => {
    getHealth().then(setHealth);
    getDiagnostics().then(setDiag);
    getSchemas().then(setSchemas);
    getSkills().then(s => setSkillCount(s.length));
    getPrompts().then(p => setPromptCount(p.length));
  }, []);

  const isHealthy = health.status === 'healthy';

  const infra = [
    { name: 'Neo4j', desc: 'Graph Database', icon: '🕸️', ui: 'http://localhost:7474', conn: 'bolt://localhost:7687' },
    { name: 'Qdrant', desc: 'Vector Store', icon: '🔮', ui: 'http://localhost:6333/dashboard', conn: 'http://localhost:6333' },
    { name: 'PostgreSQL', desc: 'Tabular Store', icon: '🗃️', ui: '—', conn: 'postgresql://localhost:5432' },
  ];

  const schemaIcons = { healthtech: '💊', fintech: '💰', edtech: '🎓', enterprise_ops: '🏢' };

  return (
    <div className="diagnostics-page">
      <div className="page-header">
        <h2 className="gradient-text">System Diagnostics</h2>
        <p>Monitor platform health, configuration, and infrastructure status.</p>
      </div>

      {/* Top metrics */}
      <div className="diag-metrics">
        <div className="diag-metric glass-card">
          <span className="diag-metric-label">Status</span>
          <span className="diag-metric-icon">{isHealthy ? '🟢' : '🔴'}</span>
          <span className="diag-metric-value">{isHealthy ? 'Healthy' : 'Down'}</span>
        </div>
        <div className="diag-metric glass-card">
          <span className="diag-metric-label">Version</span>
          <span className="diag-metric-icon">📦</span>
          <span className="diag-metric-value">v{health.version || '2.0.0'}</span>
        </div>
        <div className="diag-metric glass-card">
          <span className="diag-metric-label">Skills</span>
          <span className="diag-metric-icon">🛠️</span>
          <span className="diag-metric-value gradient-text">{skillCount}</span>
        </div>
        <div className="diag-metric glass-card">
          <span className="diag-metric-label">Prompts</span>
          <span className="diag-metric-icon">📝</span>
          <span className="diag-metric-value gradient-text">{promptCount}</span>
        </div>
        <div className="diag-metric glass-card">
          <span className="diag-metric-label">Schemas</span>
          <span className="diag-metric-icon">📋</span>
          <span className="diag-metric-value gradient-text">{schemas.length}</span>
        </div>
      </div>

      {/* Infrastructure */}
      <h3 className="diag-section-title">🗄️ Infrastructure</h3>
      <div className="diag-infra-grid">
        {infra.map((svc, i) => (
          <div key={i} className="glass-card diag-infra-card" style={{ animationDelay: `${i * 0.08}s` }}>
            <div className="diag-infra-header">
              <span className="diag-infra-icon">{svc.icon}</span>
              <div>
                <h4>{svc.name}</h4>
                <span className="diag-infra-desc">{svc.desc}</span>
              </div>
            </div>
            <div className="diag-infra-details">
              <div className="diag-infra-row">
                <span className="diag-infra-key">🌐 UI</span>
                <code className="diag-infra-val">{svc.ui}</code>
              </div>
              <div className="diag-infra-row">
                <span className="diag-infra-key">🔌 Conn</span>
                <code className="diag-infra-val">{svc.conn}</code>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Schemas */}
      <h3 className="diag-section-title">📋 Available Schemas</h3>
      <div className="diag-schemas-grid">
        {schemas.map((s, i) => (
          <div key={i} className="glass-card diag-schema-card" style={{ animationDelay: `${i * 0.06}s` }}>
            <span className="diag-schema-icon">{schemaIcons[s] || '📄'}</span>
            <span className="diag-schema-name">{s}</span>
          </div>
        ))}
      </div>

      {/* Raw data */}
      <details className="diag-raw">
        <summary className="diag-raw-toggle">🔧 Raw Diagnostics Data</summary>
        <pre className="diag-raw-content">{JSON.stringify({ health, diagnostics: diag }, null, 2)}</pre>
      </details>
    </div>
  );
}
