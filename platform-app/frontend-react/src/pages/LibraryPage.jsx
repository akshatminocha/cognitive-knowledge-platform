import { useState, useEffect } from 'react';
import { Wrench, FileText, Library, Database, Settings, ChartColumn, Network } from 'lucide-react';
import { getSkills, getPrompts, getIngestedSources } from '../api/client';
import './LibraryPage.css';

export default function LibraryPage() {
  const [tab, setTab] = useState('skills');
  const [skills, setSkills] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [sources, setSources] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);

  useEffect(() => {
    getSkills().then(setSkills);
    getPrompts().then(setPrompts);
    getIngestedSources().then(setSources);
  }, []);

  let items = [];
  if (tab === 'skills') items = skills;
  if (tab === 'prompts') items = prompts;
  if (tab === 'sources') items = sources;

  return (
    <div className="library-page">
      <div className="page-header">
        <h2 className="gradient-text">Skills & Prompts Library</h2>
        <p>Browse, inspect, and create reusable agent skills and prompt templates.</p>
      </div>

      <div className="library-tabs">
        <button className={`library-tab flex-center gap-2 ${tab === 'skills' ? 'active' : ''}`} onClick={() => { setTab('skills'); setSelectedItem(null); }}>
          <Wrench size={16} /> Skills <span className="tab-count">{skills.length}</span>
        </button>
        <button className={`library-tab flex-center gap-2 ${tab === 'prompts' ? 'active' : ''}`} onClick={() => { setTab('prompts'); setSelectedItem(null); }}>
          <FileText size={16} /> Prompts <span className="tab-count">{prompts.length}</span>
        </button>
        <button className={`library-tab flex-center gap-2 ${tab === 'sources' ? 'active' : ''}`} onClick={() => { setTab('sources'); setSelectedItem(null); }}>
          <Library size={16} /> Sources <span className="tab-count">{sources.length}</span>
        </button>
      </div>

      {items.length === 0 && (
        <div className="library-empty glass-card">
          <div className="library-empty-icon">
            {tab === 'skills' ? <Wrench size={48} /> : tab === 'prompts' ? <FileText size={48} /> : <Library size={48} />}
          </div>
          <h3>No {tab} found</h3>
          <p>Create your first {tab === 'skills' ? 'skill' : tab === 'prompts' ? 'prompt template' : 'data source'} to get started.</p>
        </div>
      )}

      <div className="library-grid">
        {items.map((item, i) => (
          <div
            key={i}
            className={`library-card glass-card ${selectedItem === i ? 'selected' : ''}`}
            onClick={() => setSelectedItem(selectedItem === i ? null : i)}
            style={{ animationDelay: `${i * 0.06}s` }}
          >
            <div className="library-card-header">
              <h4>{item.name}</h4>
              {item.domain && <span className="tag">{item.domain}</span>}
              {item.store && <span className="tag">{item.store}</span>}
            </div>
            <p className="library-card-desc">
              {(item.description || item.type || '').slice(0, 120)}{(item.description || '').length > 120 ? '...' : ''}
            </p>
            <div className="library-card-footer">
              {item.tools && <span className="flex-center gap-2"><Settings size={14}/> {item.tools.length} tools</span>}
              {item.variables && <span className="flex-center gap-2"><ChartColumn size={14}/> {item.variables.length} vars</span>}
              {item.version && <span>v{item.version}</span>}
              {item.points_count !== undefined && <span className="flex-center gap-2"><Database size={14}/> {item.points_count} points</span>}
              {item.node_count !== undefined && <span className="flex-center gap-2"><Network size={14}/> {item.node_count} nodes</span>}
              {item.tags && item.tags.map((t, j) => <span key={j} className="tag">{t}</span>)}
            </div>

            {selectedItem === i && (
              <div className="library-card-detail" onClick={e => e.stopPropagation()}>
                <div className="detail-divider" />
                {item.system_prompt && (
                  <div className="detail-section">
                    <h5>System Prompt</h5>
                    <pre className="detail-code">{item.system_prompt}</pre>
                  </div>
                )}
                {item.template && (
                  <div className="detail-section">
                    <h5>Jinja2 Template</h5>
                    <pre className="detail-code">{item.template}</pre>
                  </div>
                )}
                {item.tools && item.tools.length > 0 && (
                  <div className="detail-section">
                    <h5>Tools</h5>
                    <div className="detail-tags">
                      {item.tools.map((t, j) => <span key={j} className="tag">{t}</span>)}
                    </div>
                  </div>
                )}
                {item.guardrails && (
                  <div className="detail-section">
                    <h5>Guardrails</h5>
                    <pre className="detail-code">{JSON.stringify(item.guardrails, null, 2)}</pre>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
