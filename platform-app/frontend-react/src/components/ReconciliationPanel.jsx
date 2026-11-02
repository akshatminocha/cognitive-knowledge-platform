import { useState, useEffect } from 'react';
import {
  Sparkles, GitMerge, Search, RotateCcw, CheckCircle2, AlertTriangle,
  ArrowRight, ShieldCheck, RefreshCw, Layers, History, Eye
} from 'lucide-react';
import {
  scanDuplicates,
  executeMerge,
  autoMergeDuplicates,
  getReconciliationAudit,
  rollbackMerge,
  getStoredRole
} from '../api/client';
import './ReconciliationPanel.css';

export default function ReconciliationPanel() {
  const [candidates, setCandidates] = useState([]);
  const [history, setHistory] = useState([]);
  const [threshold, setThreshold] = useState(0.85);
  const [labelFilter, setLabelFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [activeSubTab, setActiveSubTab] = useState('candidates'); // 'candidates' | 'audit'
  const isAdmin = getStoredRole() === 'admin';

  const handleScan = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const res = await scanDuplicates(labelFilter || null, parseFloat(threshold));
      setCandidates(res.candidates || []);
      setMessage({ type: 'success', text: `Scan complete: Found ${res.count} duplicate candidates (≥ ${(threshold * 100).toFixed(0)}% match).` });
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to scan for duplicate entities.' });
    } finally {
      setLoading(false);
    }
  };

  const loadAudit = async () => {
    try {
      const res = await getReconciliationAudit(50);
      setHistory(res.history || []);
    } catch (err) {
      console.warn("Audit log fetch error:", err);
    }
  };

  useEffect(() => {
    loadAudit();
  }, []);

  const handleMerge = async (candidate, dryRun = false) => {
    setLoading(true);
    setMessage(null);
    try {
      const res = await executeMerge(candidate, dryRun);
      if (dryRun) {
        setMessage({ type: 'info', text: `[Dry Run] Validated merge for '${candidate.source_name}' -> '${candidate.canonical_name}'. No mutations applied.` });
      } else {
        setMessage({ type: 'success', text: `Merged '${candidate.source_name}' into '${candidate.canonical_name}'. Graph edges redirected and vector payloads updated.` });
        setCandidates(prev => prev.filter(c => c.source_id !== candidate.source_id));
        loadAudit();
      }
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Merge failed.' });
    } finally {
      setLoading(false);
    }
  };

  const handleAutoMerge = async () => {
    if (!window.confirm("Are you sure you want to auto-merge all high-confidence duplicate entities (≥ 90%)?")) return;
    setLoading(true);
    setMessage(null);
    try {
      const res = await autoMergeDuplicates(0.90, labelFilter || null, false);
      setMessage({ type: 'success', text: `Auto-merge complete: Merged ${res.merged_count} duplicate entity pairs.` });
      handleScan();
      loadAudit();
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Auto-merge failed.' });
    } finally {
      setLoading(false);
    }
  };

  const handleRollback = async (mergeId) => {
    if (!window.confirm("Rollback this entity merge? This will recreate the duplicate node.")) return;
    setLoading(true);
    setMessage(null);
    try {
      await rollbackMerge(mergeId);
      setMessage({ type: 'success', text: `Merge ${mergeId.slice(0, 8)} successfully rolled back.` });
      loadAudit();
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Rollback failed.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="reconciliation-panel">
      {/* Subnav & Header */}
      <div className="reconciliation-header">
        <div>
          <h3>Self-Healing Knowledge Graph (Reconciliation)</h3>
          <p className="reconciliation-subtitle">
            Background agent detecting semantic and structural duplicate nodes across Neo4j and Qdrant,
            atomically redirecting relationships and preserving audit logs.
          </p>
        </div>
        <div className="reconciliation-tabs">
          <button
            className={`subtab-btn ${activeSubTab === 'candidates' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('candidates')}
          >
            <GitMerge size={15} /> Candidates ({candidates.length})
          </button>
          <button
            className={`subtab-btn ${activeSubTab === 'audit' ? 'active' : ''}`}
            onClick={() => { setActiveSubTab('audit'); loadAudit(); }}
          >
            <History size={15} /> Audit Log ({history.length})
          </button>
        </div>
      </div>

      {/* Status banner */}
      {message && (
        <div className={`reconcile-banner ${message.type}`}>
          {message.type === 'success' && <CheckCircle2 size={16} />}
          {message.type === 'error' && <AlertTriangle size={16} />}
          {message.type === 'info' && <Eye size={16} />}
          <span>{message.text}</span>
        </div>
      )}

      {activeSubTab === 'candidates' ? (
        <>
          {/* Controls Bar */}
          <div className="reconcile-controls glass-card">
            <div className="control-group">
              <label>Domain Label</label>
              <input
                type="text"
                placeholder="All Labels (e.g. Doctor, Medication)"
                value={labelFilter}
                onChange={(e) => setLabelFilter(e.target.value)}
              />
            </div>

            <div className="control-group">
              <label>Similarity Threshold: {(threshold * 100).toFixed(0)}%</label>
              <input
                type="range"
                min="0.70"
                max="0.99"
                step="0.01"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
              />
            </div>

            <div className="control-actions">
              <button className="btn-primary" onClick={handleScan} disabled={loading}>
                {loading ? <RefreshCw className="spin" size={15} /> : <Search size={15} />}
                <span>Scan Graph</span>
              </button>
              {isAdmin && (
                <button
                  className="btn-accent"
                  onClick={handleAutoMerge}
                  disabled={loading || candidates.length === 0}
                  title="Auto-merge candidates with ≥ 90% match"
                >
                  <Sparkles size={15} />
                  <span>Auto-Merge (≥90%)</span>
                </button>
              )}
            </div>
          </div>

          {/* Candidate Cards Feed */}
          <div className="candidates-container">
            {candidates.length === 0 ? (
              <div className="empty-reconcile-state">
                <Layers size={40} className="empty-icon" />
                <h4>No Duplicate Candidates Detected</h4>
                <p>Run a graph scan above to identify duplicate entities with differing aliases, addresses, or spellings.</p>
              </div>
            ) : (
              candidates.map((cand, idx) => (
                <div key={idx} className="candidate-card glass-card">
                  <div className="card-top-row">
                    <span className="entity-label-pill">{cand.entity_label}</span>
                    <span className="match-score-pill">
                      {(cand.similarity_score * 100).toFixed(1)}% Match
                    </span>
                  </div>

                  <div className="comparison-row">
                    <div className="node-side duplicate-side">
                      <span className="side-label">Duplicate Entity (Source)</span>
                      <h5>{cand.source_name}</h5>
                      <div className="node-meta-grid">
                        {Object.entries(cand.source_props || {})
                          .filter(([k]) => !k.startsWith('_') && k !== 'name')
                          .slice(0, 3)
                          .map(([k, v]) => (
                            <span key={k} className="meta-pair"><strong>{k}:</strong> {String(v)}</span>
                          ))}
                      </div>
                    </div>

                    <div className="merge-arrow-col">
                      <ArrowRight size={20} />
                      <span className="merge-action-text">Merges Into</span>
                    </div>

                    <div className="node-side canonical-side">
                      <span className="side-label">Canonical Entity (Target)</span>
                      <h5>{cand.canonical_name}</h5>
                      <div className="node-meta-grid">
                        {Object.entries(cand.canonical_props || {})
                          .filter(([k]) => !k.startsWith('_') && k !== 'name')
                          .slice(0, 3)
                          .map(([k, v]) => (
                            <span key={k} className="meta-pair"><strong>{k}:</strong> {String(v)}</span>
                          ))}
                      </div>
                    </div>
                  </div>

                  {cand.match_reasons && cand.match_reasons.length > 0 && (
                    <div className="reasons-row">
                      {cand.match_reasons.map((r, rIdx) => (
                        <span key={rIdx} className="reason-chip">{r}</span>
                      ))}
                    </div>
                  )}

                  <div className="card-actions">
                    <button
                      className="btn-secondary btn-sm"
                      onClick={() => handleMerge(cand, true)}
                      disabled={loading}
                    >
                      Dry Run
                    </button>
                    {isAdmin ? (
                      <button
                        className="btn-primary btn-sm"
                        onClick={() => handleMerge(cand, false)}
                        disabled={loading}
                      >
                        <GitMerge size={14} /> Merge & Re-wire
                      </button>
                    ) : (
                      <span className="admin-only-hint">Admin required to apply</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      ) : (
        /* Audit Log Table */
        <div className="audit-table-container glass-card">
          {history.length === 0 ? (
            <div className="empty-reconcile-state">
              <History size={40} className="empty-icon" />
              <h4>No Merge History Found</h4>
              <p>Completed entity merges will appear here with atomic rollback capability.</p>
            </div>
          ) : (
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Label</th>
                  <th>Canonical (Target)</th>
                  <th>Duplicate (Merged)</th>
                  <th>Vectors Synced</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {history.map((rec) => (
                  <tr key={rec.merge_id}>
                    <td>{new Date(rec.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
                    <td><span className="entity-label-pill">{rec.entity_label}</span></td>
                    <td className="bold-cell">{rec.canonical_name}</td>
                    <td className="strikethrough-cell">{rec.duplicate_name}</td>
                    <td>{rec.qdrant_points_updated} pts</td>
                    <td>
                      <span className={`status-pill ${rec.status}`}>
                        {rec.status === 'merged' ? 'Merged' : 'Reverted'}
                      </span>
                    </td>
                    <td>
                      {isAdmin && rec.status === 'merged' && (
                        <button
                          className="btn-rollback btn-sm"
                          onClick={() => handleRollback(rec.merge_id)}
                          disabled={loading}
                        >
                          <RotateCcw size={13} /> Rollback
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
