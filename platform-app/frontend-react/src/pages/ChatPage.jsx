import { useState, useEffect, useRef } from 'react';
import { queryAgent, getSkills } from '../api/client';
import './ChatPage.css';

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [skills, setSkills] = useState([]);
  const [activeSkill, setActiveSkill] = useState('auto');
  const [sessionId, setSessionId] = useState(null);
  const messagesEndRef = useRef(null);

  useEffect(() => { getSkills().then(setSkills); }, []);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    const userMsg = { role: 'user', content: q, ts: Date.now() };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const result = await queryAgent(q, sessionId, 'healthtech', activeSkill);
      const assistantMsg = {
        role: 'assistant',
        content: result.response || 'No response.',
        metadata: {
          model_used: result.model_used,
          total_steps: result.total_steps,
          duration_ms: result.duration_ms,
          tools_used: result.tools_used || [],
        },
        ts: Date.now(),
      };
      setMessages(prev => [...prev, assistantMsg]);
      if (result.session_id) setSessionId(result.session_id);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}`, ts: Date.now() }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };

  const clearChat = () => { setMessages([]); setSessionId(null); };

  const exportChat = () => {
    const blob = new Blob([JSON.stringify(messages, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url;
    a.download = `ckp_chat_${new Date().toISOString().slice(0,19).replace(/[:-]/g,'')}.json`;
    a.click(); URL.revokeObjectURL(url);
  };

  const skillOptions = ['auto', ...skills.map(s => s.name)];

  return (
    <div className="chat-page">
      <div className="page-header">
        <h2 className="gradient-text">Knowledge Agent</h2>
        <p>Ask questions about your ingested data using natural language.</p>
      </div>

      <div className="chat-toolbar">
        <div className="chat-toolbar-left">
          <span className="tag">Mode: {activeSkill === 'auto' ? 'Auto-routing' : activeSkill}</span>
        </div>
        <div className="chat-toolbar-right">
          <select value={activeSkill} onChange={e => setActiveSkill(e.target.value)} className="skill-select">
            {skillOptions.map(s => (
              <option key={s} value={s}>{s === 'auto' ? '🤖 Auto-Select' : `⚡ ${s}`}</option>
            ))}
          </select>
          {messages.length > 0 && (
            <>
              <button className="btn" onClick={exportChat} title="Export chat">📥</button>
              <button className="btn" onClick={clearChat} title="Clear chat">🗑️</button>
            </>
          )}
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && !loading && (
          <div className="chat-welcome">
            <div className="chat-welcome-icon">💬</div>
            <h3>Start a Conversation</h3>
            <p>Ask questions about your knowledge base, generate reports, or explore your data graph.</p>
            <div className="chat-welcome-tags">
              <span className="tag">💊 Clinical data</span>
              <span className="tag">📊 Reports</span>
              <span className="tag">🔍 Knowledge Q&A</span>
              <span className="tag">🕸️ Graph queries</span>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble ${msg.role}`}>
            <div className="chat-bubble-avatar">{msg.role === 'user' ? '👤' : '🧠'}</div>
            <div className="chat-bubble-body">
              <div className="chat-bubble-content">{msg.content}</div>
              {msg.metadata && (
                <div className="chat-bubble-meta">
                  <span>⚡ {msg.metadata.total_steps} step{msg.metadata.total_steps !== 1 ? 's' : ''}</span>
                  <span>⏱️ {Math.round(msg.metadata.duration_ms)}ms</span>
                  <span>🤖 {msg.metadata.model_used}</span>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-bubble assistant">
            <div className="chat-bubble-avatar">🧠</div>
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
          {loading ? <span className="spinner" /> : '➤'}
        </button>
      </div>
    </div>
  );
}
