import { useState, useEffect, useRef } from 'react';
import { MessageSquare, Package, Trash2, Send, Brain, User, Settings2, Zap, Clock, Cpu, Activity, FileText, Search, Network } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { queryAgent, getSkills, listSessions, getSession, deleteSession, exportUKA } from '../api/client';
import './ChatPage.css';

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [skills, setSkills] = useState([]);
  const [activeSkill, setActiveSkill] = useState('auto');
  const [sessionId, setSessionId] = useState(null);
  const messagesEndRef = useRef(null);

  const [activeModel, setActiveModel] = useState('gemini-2.5-flash');
  const [sessions, setSessions] = useState([]);

  useEffect(() => { 
    getSkills().then(setSkills); 
    listSessions().then(setSessions);
  }, []);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

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

  const clearChat = () => { setMessages([]); setSessionId(null); };

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
          {sessions.length === 0 ? (
            <p className="no-sessions">No previous sessions found</p>
          ) : (
            sessions.map(s => (
              <div 
                key={s.session_id} 
                className={`session-item ${sessionId === s.session_id ? 'active' : ''}`}
                onClick={() => handleSessionClick(s.session_id)}
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <MessageSquare size={16} className="session-icon" />
                  <span className="session-id">{s.session_id.split('-')[0]}</span>
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
            ))
          )}
        </div>
        <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid var(--border-light)' }}>
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} onClick={clearChat}>
            <MessageSquare size={16} /> New Session
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
              <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
              <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
              <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
              <option value="gpt-4o">GPT-4o</option>
            </select>
            {messages.length > 0 && (
              <div className="toolbar-actions">
                <button className="btn icon-btn" onClick={exportChat} title="Export Universal Knowledge Artifact (UKA) / Zip"><Package size={18} /></button>
                <button className="btn icon-btn" onClick={clearChat} title="Clear chat"><Trash2 size={18} /></button>
              </div>
            )}
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
                {msg.metadata && (
                  <div className="chat-bubble-meta">
                    <div className="flex-center gap-3 meta-stats">
                      <span className="flex-center gap-1"><Zap size={14} className="text-muted" /> {msg.metadata.total_steps} step{msg.metadata.total_steps !== 1 ? 's' : ''}</span>
                      <span className="flex-center gap-1"><Clock size={14} className="text-muted" /> {Math.round(msg.metadata.duration_ms)}ms</span>
                      <span className="flex-center gap-1"><Cpu size={14} className="text-muted" /> {msg.metadata.model_used}</span>
                    </div>
                    {msg.metadata.sources && msg.metadata.sources.length > 0 && (
                      <div className="chat-sources-block">
                        <strong>📚 Data Sources:</strong>
                        <div className="chat-sources-list">
                          {msg.metadata.sources.map((src, idx) => {
                            const isString = typeof src === 'string';
                            const label = isString ? src : src.label;
                            const explanation = isString ? 'Source referenced during LLM generation.' : src.explanation;
                            const data = isString ? null : src.data;
                            
                            return (
                              <details key={idx} className="chat-source-item">
                                <summary className="chat-source-summary">{label}</summary>
                                <div className="chat-source-details">
                                  <p className="chat-source-explanation">{explanation}</p>
                                  {data && data.length > 0 && (
                                    <div className="chat-source-data">
                                      {data.map((d, i) => (
                                        <div key={i} className="chat-data-row">
                                          {src.type === 'vector' ? `[${d.file}] ${d.snippet}` : d}
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
    </div>
  );
}
