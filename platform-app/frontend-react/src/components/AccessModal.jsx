import { useState, useEffect, useRef } from 'react';
import { Shield, ShieldCheck, Eye, EyeOff, LogIn, Sparkles, Lock, Zap } from 'lucide-react';
import { verifyAccess, isAuthenticated, storeAuth } from '../api/client';
import './AccessModal.css';

/**
 * Glassmorphic Access Modal — Enterprise Access Gate.
 *
 * Shown on app launch when no valid session token is found.
 * Provides two entry paths:
 *   1. "Evaluator / Recruiter" — pre-filled demo code (10 queries)
 *   2. "Admin Passcode"       — full admin access
 */
export default function AccessModal({ onAuthenticated }) {
  const [mode, setMode] = useState(null); // null | 'demo' | 'admin'
  const [passcode, setPasscode] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [shake, setShake] = useState(false);
  const inputRef = useRef(null);

  // Auto-skip if already authenticated
  useEffect(() => {
    if (isAuthenticated()) onAuthenticated?.();
  }, []);

  useEffect(() => {
    if (mode && inputRef.current) inputRef.current.focus();
  }, [mode]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!passcode.trim()) return;

    setLoading(true);
    setError('');
    try {
      const result = await verifyAccess(passcode.trim());
      // Store auth
      storeAuth(result.token, result.role);
      onAuthenticated?.(result);
    } catch (err) {
      setError(err.message || 'Invalid passcode');
      setShake(true);
      setTimeout(() => setShake(false), 600);
    } finally {
      setLoading(false);
    }
  };

  const selectMode = (m) => {
    setMode(m);
    setError('');
    setPasscode(m === 'demo' ? 'ckp-demo' : '');
  };

  return (
    <div className="access-overlay">
      {/* Animated background orbs */}
      <div className="access-bg-orb orb-1" />
      <div className="access-bg-orb orb-2" />
      <div className="access-bg-orb orb-3" />

      <div className={`access-modal ${shake ? 'shake' : ''}`}>
        {/* Header */}
        <div className="access-header">
          <div className="access-logo">
            <Shield size={40} strokeWidth={1.5} />
          </div>
          <h1 className="access-title">
            <span className="gradient-text">CKP</span>
          </h1>
          <p className="access-subtitle">Cognitive Knowledge Platform</p>
          <p className="access-desc">
            Enterprise-grade agentic AI platform for knowledge graph intelligence
          </p>
        </div>

        {/* Mode Selection */}
        {!mode && (
          <div className="access-modes">
            <button className="access-mode-btn demo" onClick={() => selectMode('demo')}>
              <div className="mode-icon"><Eye size={22} /></div>
              <div className="mode-info">
                <span className="mode-label">Evaluator / Recruiter</span>
                <span className="mode-hint">Quick access with 10 query limit</span>
              </div>
              <Zap size={16} className="mode-arrow" />
            </button>

            <button className="access-mode-btn admin" onClick={() => selectMode('admin')}>
              <div className="mode-icon"><ShieldCheck size={22} /></div>
              <div className="mode-info">
                <span className="mode-label">Admin Access</span>
                <span className="mode-hint">Full platform control</span>
              </div>
              <Lock size={16} className="mode-arrow" />
            </button>
          </div>
        )}

        {/* Passcode Form */}
        {mode && (
          <form className="access-form" onSubmit={handleSubmit}>
            <div className="access-form-header">
              <button type="button" className="access-back" onClick={() => { setMode(null); setPasscode(''); setError(''); }}>
                ← Back
              </button>
              <span className="access-mode-tag">
                {mode === 'demo' ? '🔍 Evaluator Mode' : '🔐 Admin Mode'}
              </span>
            </div>

            <div className="access-input-group">
              <label className="access-label">
                {mode === 'demo' ? 'Demo Code' : 'Admin Passcode'}
              </label>
              <div className="access-input-wrapper">
                <input
                  ref={inputRef}
                  type={showPass ? 'text' : 'password'}
                  className="access-input"
                  value={passcode}
                  onChange={e => setPasscode(e.target.value)}
                  placeholder={mode === 'demo' ? 'Pre-filled for you' : 'Enter admin passcode'}
                  autoComplete="off"
                />
                <button type="button" className="access-toggle-vis" onClick={() => setShowPass(!showPass)}>
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="access-error">{error}</div>
            )}

            <button type="submit" className="access-submit" disabled={loading || !passcode.trim()}>
              {loading ? (
                <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />
              ) : (
                <>
                  <LogIn size={16} />
                  {mode === 'demo' ? 'Enter as Evaluator' : 'Authenticate'}
                </>
              )}
            </button>

            {mode === 'demo' && (
              <p className="access-quota-note">
                <Sparkles size={14} /> Limited to 10 AI queries per session
              </p>
            )}
          </form>
        )}

        {/* Footer */}
        <div className="access-footer">
          <span>Built by <strong>Akshat Minocha</strong></span>
          <span className="access-dot">•</span>
          <span>v3.0.0</span>
        </div>
      </div>
    </div>
  );
}
