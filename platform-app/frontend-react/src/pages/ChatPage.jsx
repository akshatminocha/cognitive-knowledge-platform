import { useState, useEffect, useRef } from 'react';
import { 
  MessageSquare, Package, Trash2, Send, Brain, User, Settings2, Zap, Clock, 
  Cpu, Activity, FileText, Search, Network, Database, Layers, Sparkles, 
  ArrowRightLeft, Globe, Wrench, UploadCloud, Download, CheckCircle2, AlertCircle, X, FileArchive 
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { queryAgent, getSkills, listSessions, getSession, deleteSession, exportUKA, importUKA } from '../api/client';
import './ChatPage.css';

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [skills, setSkills] = useState([]);
  const [activeSkill, setActiveSkill] = useState('auto');
  const [sessionId, setSessionId] = useState(null);
  const messagesEndRef = useRef(null);

  const [activeModel, setActiveModel] = useState('auto');
  const [sessions, setSessions] = useState([]);

  // UKA Import Modal State
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importError, setImportError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => { 
    getSkills().then(setSkills); 
    listSessions().then(setSessions);
  }, []);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleImportSubmit = async () => {
    if (!importFile || importing) return;
    setImporting(true);
    setImportError(null);
    setImportResult(null);

    try {
      const res = await importUKA(importFile);
      setImportResult(res);
      const updatedSessions = await listSessions();
      setSessions(updatedSessions);
    } catch (err) {
      setImportError(err.message || 'Failed to import UKA bundle');
    } finally {
      setImporting(false);
    }
  };

  const handleOpenImportedSession = async (sid) => {
    setShowImportModal(false);
    setImportFile(null);
    setImportResult(null);
    setImportError(null);
    await handleSessionClick(sid);
  };

  const handleSessionClick = async (sid) => {
    if (sessionId === sid) return;
    setSessionId(sid);
    setLoading(true);
    try {
      const msgs = await getSession(sid);
      const formattedMsgs = msgs
        .filter(m => m.role !== 'system')
        .map(m => ({
          role: m.role,
          content: m.content,
          metadata: m.metadata || {},
          ts: Date.parse(m.timestamp) || Date.now()
        }));
      setMessages(formattedMsgs);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSession = async (e, sid) => {
    e.stopPropagation(); // prevent clicking the session row
    try {
      await deleteSession(sid);
      if (sessionId === sid) {
        setSessionId(null);
        setMessages([]);
      }
      listSessions().then(setSessions);
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  const handleSend = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    const userMsg = { role: 'user', content: q, ts: Date.now() };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const result = await queryAgent(q, sessionId, 'healthtech', activeSkill, activeModel);
      const assistantMsg = {
        role: 'assistant',
        content: result.response || 'No response.',
        metadata: {
          model_used: result.model_used,
          total_steps: result.total_steps,
          duration_ms: result.duration_ms,
          tools_used: result.tools_used || [],
          sources: result.sources || [],
          smart_routed: result.smart_routed,
          complexity_tier: result.complexity_tier,
          intent: result.intent,
          estimated_cost_tier: result.estimated_cost_tier,
          routing_reason: result.routing_reason,
          cascade_fallback: result.cascade_fallback,
          cascade_reason: result.cascade_reason,
          mechanic_repairs: result.mechanic_repairs || 0,
        },
        ts: Date.now(),
      };
      setMessages(prev => [...prev, assistantMsg]);
      if (result.session_id) {
        setSessionId(result.session_id);
        listSessions().then(setSessions); // Refresh session list
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}`, ts: Date.now() }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };

  const clearChat = () => {
    setMessages([]);
    const newSid = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : 'sess-' + Math.random().toString(36).substring(2, 10);
    setSessionId(newSid);
  };

  const exportChat = () => {
    if (sessionId) {
      exportUKA(sessionId);
    } else {
      const blob = new Blob([JSON.stringify(messages, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url;
      a.download = `ckp_chat_${new Date().toISOString().slice(0,19).replace(/[:-]/g,'')}.json`;
      a.click(); URL.revokeObjectURL(url);
    }
  };

  const skillOptions = ['auto', ...skills.map(s => s.name)];

  return (
    <div className="chat-layout">
      <div className="chat-sidebar glass-card">
        <h3 className="sidebar-heading">Conversations</h3>
        <div className="session-list">
          {sessionId && !sessions.some(s => s.session_id === sessionId) && (
            <div className="session-item active" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <MessageSquare size={16} className="session-icon" />
                <span className="session-id">{sessionId.slice(0, 8)} (new)</span>
              </div>
            </div>
          )}
          {sessions.length === 0 && !sessionId ? (
            <p className="no-sessions">No previous sessions found</p>
          ) : (
            sessions.map(s => {
              const displayId = s.session_id.startsWith('session-')
                ? (s.session_id.replace(/^session-/, '').slice(0, 8) || 'session')
                : s.session_id.slice(0, 8);
              return (
                <div 
                  key={s.session_id} 
                  className={`session-item ${sessionId === s.session_id ? 'active' : ''}`}
                  onClick={() => handleSessionClick(s.session_id)}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <MessageSquare size={16} className="session-icon" />
                    <span className="session-id" title={s.session_id}>{displayId}</span>
                  </div>
                  <button 
                    className="btn icon-btn" 
                    style={{ padding: '4px', opacity: 0.7 }}
                    onClick={(e) => handleDeleteSession(e, s.session_id)}
                    title="Delete Session"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              );
            })
          )}
        </div>
        <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid var(--glass-border)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} onClick={clearChat}>
            <MessageSquare size={16} /> New Session
          </button>
          <button 
            className="btn btn-secondary uka-import-sidebar-btn" 
            style={{ width: '100%', justifyContent: 'center', background: 'var(--bg-card)' }} 
            onClick={() => { setShowImportModal(true); setImportResult(null); setImportError(null); setImportFile(null); }}
          >
            <UploadCloud size={16} /> Import .UKA
          </button>
        </div>
      </div>
      
      <div className="chat-page">
        <div className="page-header">
          <h2 className="gradient-text">Knowledge Agent</h2>
          <p>Ask questions about your ingested data using natural language.</p>
        </div>

        <div className="chat-toolbar">
          <div className="chat-toolbar-left flex-center gap-2">
            <span className="tag align-center"><Settings2 size={14} className="mr-1"/> Mode: {activeSkill === 'auto' ? 'Auto-routing' : activeSkill}</span>
          </div>
          <div className="chat-toolbar-right flex-center gap-2">
            <select value={activeSkill} onChange={e => setActiveSkill(e.target.value)} className="skill-select" title="Active Skill">
              {skillOptions.map(s => (
                <option key={s} value={s}>{s === 'auto' ? 'Auto-Select' : s}</option>
              ))}
            </select>
            <select value={activeModel} onChange={e => setActiveModel(e.target.value)} className="skill-select" title="Swap Model">
              <option value="auto">Auto (AI Economics)</option>
              <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
              <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
              <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
              <option value="gpt-4o">GPT-4o</option>
            </select>
            <div className="toolbar-actions">
              <button 
                className="btn icon-btn" 
                onClick={() => { setShowImportModal(true); setImportResult(null); setImportError(null); setImportFile(null); }} 
                title="Import Universal Knowledge Artifact (.uka)"
              >
                <UploadCloud size={18} />
              </button>
              {(messages.length > 0 || sessionId) && (
                <button className="btn icon-btn" onClick={exportChat} title="Export Universal Knowledge Artifact (.uka)">
                  <Download size={18} />
                </button>
              )}
              {messages.length > 0 && (
                <button className="btn icon-btn" onClick={clearChat} title="Clear chat">
                  <Trash2 size={18} />
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="chat-messages">
          {messages.length === 0 && !loading && (
            <div className="chat-welcome">
              <div className="chat-welcome-icon"><MessageSquare size={48} /></div>
              <h3>Start a Conversation</h3>
              <p>Ask questions about your knowledge base, generate reports, or explore your data graph.</p>
              <div className="chat-welcome-tags">
                <span className="tag flex-center gap-2"><Activity size={14}/> Clinical data</span>
                <span className="tag flex-center gap-2"><FileText size={14}/> Reports</span>
                <span className="tag flex-center gap-2"><Search size={14}/> Knowledge Q&A</span>
                <span className="tag flex-center gap-2"><Network size={14}/> Graph queries</span>
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`chat-bubble ${msg.role}`}>
              <div className="chat-bubble-avatar">
                {msg.role === 'user' ? <User size={20} /> : <Brain size={20} />}
              </div>
              <div className="chat-bubble-body">
                <div className="chat-bubble-content markdown-body">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
                {msg.role === 'assistant' && msg.metadata && msg.metadata.total_steps != null && (
                  <div className="chat-bubble-meta">
                    <div className="flex-center gap-3 meta-stats" style={{ flexWrap: 'wrap' }}>
                      <span className="flex-center gap-1"><Zap size={14} className="text-muted" /> {msg.metadata.total_steps} step{msg.metadata.total_steps !== 1 ? 's' : ''}</span>
                      <span className="flex-center gap-1"><Clock size={14} className="text-muted" /> {Math.round(msg.metadata.duration_ms)}ms</span>
                      <span className="flex-center gap-1"><Cpu size={14} className="text-muted" /> {msg.metadata.model_used}</span>
                      {msg.metadata.smart_routed && (
                        <span className="smart-route-badge" title={msg.metadata.routing_reason || "Routed by AI Economics"}>
                          <Sparkles size={12} className="badge-icon" /> Auto ({msg.metadata.complexity_tier ? msg.metadata.complexity_tier.replace('_', ' ').toUpperCase() : 'SMART'})
                        </span>
                      )}
                      {msg.metadata.cascade_fallback && (
                        <span className="cascade-fallback-badge" title={msg.metadata.cascade_reason || "Provider key unavailable; cascaded gracefully"}>
                          <ArrowRightLeft size={12} className="badge-icon" /> BYOK Cascaded
                        </span>
                      )}
                      {msg.metadata.intent && (
                        <span className="intent-badge">
                          {msg.metadata.intent === 'open_domain' ? (
                            <>
                              <Globe size={12} className="badge-icon" /> Open-Domain
                            </>
                          ) : (
                            <>
                              <Network size={12} className="badge-icon" /> Graph RAG
                            </>
                          )}
                        </span>
                      )}
                      {msg.metadata.mechanic_repairs > 0 && (
                        <span className="mechanic-repaired-badge" title="Query self-corrected by The Mechanic without consuming step budget">
                          <Wrench size={12} className="badge-icon" /> Self-Corrected
                        </span>
                      )}
                    </div>
                    {msg.metadata.sources && msg.metadata.sources.length > 0 && (
                      <div className="chat-sources-block">
                        <div className="chat-sources-header">
                          <Database size={13} className="chat-sources-icon" />
                          <span>Data Sources & Traceability</span>
                        </div>
                        <div className="chat-sources-list">
                          {msg.metadata.sources.map((src, idx) => {
                            const isString = typeof src === 'string';
                            const label = isString ? src : src.label;
                            const explanation = isString ? 'Source referenced during LLM generation.' : src.explanation;
                            const data = isString ? null : src.data;
                            
                            return (
                              <details key={idx} className="chat-source-item" open>
                                <summary className="chat-source-summary">
                                  <span className="source-label-wrapper">
                                    {src.type === 'graph' ? <Network size={12} className="source-type-icon" /> : src.type === 'vector' ? <Search size={12} className="source-type-icon" /> : <Database size={12} className="source-type-icon" />}
                                    <span>{label}</span>
                                    {src.mechanic_repaired && (
                                      <span className="source-mechanic-badge" title="Query automatically corrected by The Mechanic">
                                        <Wrench size={10} className="badge-icon" /> Repaired
                                      </span>
                                    )}
                                  </span>
                                </summary>
                                <div className="chat-source-details">
                                  <p className="chat-source-explanation">{explanation}</p>
                                  {data && data.length > 0 && (
                                    <div className="chat-source-data">
                                      {data.map((d, i) => (
                                        <div key={i} className="chat-data-row">
                                          {src.type === 'vector' ? `[${d.file}] ${d.snippet}` : (typeof d === 'object' ? JSON.stringify(d) : String(d))}
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </details>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="chat-bubble assistant">
              <div className="chat-bubble-avatar"><Brain size={20} /></div>
              <div className="chat-bubble-body">
                <div className="chat-typing">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-bar">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your knowledge base..."
            rows={1}
            className="chat-input"
            disabled={loading}
          />
          <button className="btn-primary chat-send-btn" onClick={handleSend} disabled={loading || !input.trim()}>
            {loading ? <span className="spinner" /> : <Send size={18} />}
          </button>
        </div>
      </div>

      {showImportModal && (
        <div className="uka-modal-backdrop" onClick={() => setShowImportModal(false)}>
          <div className="uka-modal-card glass-card" onClick={e => e.stopPropagation()}>
            <div className="uka-modal-header">
              <div className="uka-modal-title">
                <FileArchive size={20} className="text-accent" />
                <h3>Import Universal Knowledge Artifact</h3>
              </div>
              <button className="btn icon-btn" onClick={() => setShowImportModal(false)}>
                <X size={18} />
              </button>
            </div>

            <p className="uka-modal-subtitle">
              Upload a <code>.uka</code> or <code>.zip</code> bundle to rehydrate conversational memory, Neo4j knowledge subgraphs, Qdrant vectors, and multimodal media.
            </p>

            {!importResult ? (
              <div
                className={`uka-dropzone ${dragActive ? 'drag-active' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={e => {
                  e.preventDefault();
                  setDragActive(false);
                  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    setImportFile(e.dataTransfer.files[0]);
                    setImportError(null);
                  }
                }}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  accept=".uka,.zip"
                  style={{ display: 'none' }}
                  onChange={e => {
                    if (e.target.files && e.target.files[0]) {
                      setImportFile(e.target.files[0]);
                      setImportError(null);
                    }
                  }}
                />
                <UploadCloud size={40} className="uka-dropzone-icon" />
                <div className="uka-dropzone-text">
                  {importFile ? (
                    <span className="uka-selected-file">
                      <strong>{importFile.name}</strong> ({(importFile.size / 1024).toFixed(1)} KB)
                    </span>
                  ) : (
                    <>
                      <span>Drag & drop your <strong>.uka</strong> artifact here</span>
                      <small>or click to browse from your computer</small>
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="uka-result-card">
                <div className="uka-result-header">
                  <CheckCircle2 size={24} className="text-success" />
                  <h4>Session Rehydrated Successfully!</h4>
                </div>
                <div className="uka-stats-grid">
                  <div className="uka-stat-badge">
                    <span className="uka-stat-val">{importResult.nodes_restored}</span>
                    <span className="uka-stat-lbl">Graph Nodes</span>
                  </div>
                  <div className="uka-stat-badge">
                    <span className="uka-stat-val">{importResult.edges_restored}</span>
                    <span className="uka-stat-lbl">Graph Edges</span>
                  </div>
                  <div className="uka-stat-badge">
                    <span className="uka-stat-val">{importResult.vectors_restored}</span>
                    <span className="uka-stat-lbl">Vector Chunks</span>
                  </div>
                  <div className="uka-stat-badge">
                    <span className="uka-stat-val">{importResult.messages_restored}</span>
                    <span className="uka-stat-lbl">Messages</span>
                  </div>
                </div>
                {importResult.manifest && (
                  <div className="uka-manifest-summary">
                    <strong>{importResult.manifest.title}</strong>
                    <p>{importResult.manifest.description}</p>
                  </div>
                )}
              </div>
            )}

            {importError && (
              <div className="uka-error-banner">
                <AlertCircle size={18} />
                <span>{importError}</span>
              </div>
            )}

            <div className="uka-modal-actions">
              {!importResult ? (
                <>
                  <button className="btn btn-secondary" onClick={() => setShowImportModal(false)}>
                    Cancel
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={handleImportSubmit}
                    disabled={!importFile || importing}
                  >
                    {importing ? <span className="spinner" /> : <UploadCloud size={16} />}
                    {importing ? 'Rehydrating...' : 'Rehydrate Bundle'}
                  </button>
                </>
              ) : (
                <button
                  className="btn btn-primary"
                  style={{ width: '100%', justifyContent: 'center' }}
                  onClick={() => handleOpenImportedSession(importResult.session_id)}
                >
                  Open Rehydrated Session
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
