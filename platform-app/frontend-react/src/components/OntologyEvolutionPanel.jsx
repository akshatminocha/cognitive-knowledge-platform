import { useState, useEffect, useCallback } from 'react';
import {
  GitBranch, Sparkles, AlertCircle, CheckCircle2, XCircle, ArrowRight,
  ShieldCheck, Activity, Eye, X, RefreshCw, FileCode, Check
} from 'lucide-react';
import {
  getEvolutionCandidates,
  generateEvolutionProposal,
  listEvolutionProposals,
  approveEvolutionProposal,
  rejectEvolutionProposal
} from '../api/client';
import './OntologyEvolutionPanel.css';

export default function OntologyEvolutionPanel({ activeSchema = 'healthtech' }) {
  const [candidates, setCandidates] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedProposal, setSelectedProposal] = useState(null);
  const [feedback, setFeedback] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [candData, propData] = await Promise.all([
        getEvolutionCandidates(),
        listEvolutionProposals(),
      ]);
      setCandidates(candData.candidates || []);
      setClusters(candData.clusters || []);
      setProposals(propData.proposals || []);
    } catch (err) {
      console.error('Failed to load evolution data:', err);
      setFeedback({ type: 'error', text: 'Failed to connect to ontology evolution registry.' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSynthesizeProposal = async (cluster) => {
    try {
      setActionLoading(true);
      setFeedback({ type: 'info', text: `Synthesizing Palantir-compliant schema proposal for ${cluster.canonical_name}...` });
      
      const res = await generateEvolutionProposal(
        activeSchema,
        cluster.canonical_name,
        cluster.context_snippets?.[0] || null
      );
      
      setFeedback({ type: 'success', text: `Proposal ${res.proposal.proposal_id} generated successfully!` });
      await loadData();
      setSelectedProposal(res.proposal);
    } catch (err) {
      console.error('Failed to synthesize proposal:', err);
      setFeedback({ type: 'error', text: `Synthesis failed: ${err.message}` });
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async (proposalId) => {
    try {
      setActionLoading(true);
      const res = await approveEvolutionProposal(proposalId, 'Approved via Admin Configuration Hub');
      setFeedback({
        type: 'success',
        text: `Schema '${res.schema_name}' v${res.version} approved and hot-reloaded successfully!`
      });
      setSelectedProposal(null);
      await loadData();
    } catch (err) {
      console.error('Failed to approve proposal:', err);
      setFeedback({ type: 'error', text: `Approval failed: ${err.message}` });
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (proposalId) => {
    try {
      setActionLoading(true);
      await rejectEvolutionProposal(proposalId, 'Rejected via Admin Review');
      setFeedback({ type: 'info', text: 'Proposal marked as REJECTED.' });
      setSelectedProposal(null);
      await loadData();
    } catch (err) {
      console.error('Failed to reject proposal:', err);
      setFeedback({ type: 'error', text: `Rejection failed: ${err.message}` });
    } finally {
      setActionLoading(false);
    }
  };

  const renderDiffLine = (line, idx) => {
    let className = 'diff-line diff-context';
    if (line.startsWith('+') && !line.startsWith('+++')) {
      className = 'diff-line diff-add';
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      className = 'diff-line diff-del';
    } else if (line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++')) {
      className = 'diff-line diff-info';
    }
    return (
      <div key={idx} className={className}>
        {line}
      </div>
    );
  };

  return (
    <div className="evolution-panel">
      {/* Feedback Banner */}
      {feedback && (
        <div className={`glass-card p-3 d-flex align-items-center justify-content-between ${
          feedback.type === 'error' ? 'text-error' : feedback.type === 'success' ? 'text-success' : 'text-primary'
        }`} style={{
          background: feedback.type === 'error' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(122, 82, 244, 0.1)',
          border: `1px solid ${feedback.type === 'error' ? '#ef4444' : '#7a52f4'}`,
          borderRadius: '8px',
          padding: '10px 16px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {feedback.type === 'error' ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
            <span style={{ fontSize: '0.88rem', fontWeight: 500 }}>{feedback.text}</span>
          </div>
          <button className="btn-icon" onClick={() => setFeedback(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>
            <X size={14} />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="evolution-header">
        <div>
          <div className="evolution-header-title">
            <GitBranch size={22} color="var(--accent-primary, #a855f7)" />
            <h3 style={{ margin: 0 }}>Dynamic Ontology Evolution</h3>
            <span className="evolution-badge">Palantir Architecture</span>
          </div>
          <p style={{ margin: '6px 0 0', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            Autonomous learning loop intercepting unmapped concepts, synthesizing Palantir-governed schemas, and calculating graph density impacts.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={loadData} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          <span>Refresh Candidates</span>
        </button>
      </div>

      {/* Section 1: Emerging Candidate Concepts */}
      <div className="candidate-section">
        <div className="candidate-section-title">
          <span>Emerging Candidate Concepts ({clusters.length} Clusters)</span>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Observed across ingested unstructured clinical notes
          </span>
        </div>

        {clusters.length === 0 ? (
          <div className="glass-card" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            No unmapped candidate concepts detected. All ingested entities currently conform to the active schema.
          </div>
        ) : (
          <div className="candidate-grid">
            {clusters.map((cluster) => (
              <div key={cluster.cluster_id} className="candidate-card">
                <div className="candidate-card-header">
                  <div className="candidate-name-wrap">
                    <span className="candidate-name">{cluster.canonical_name}</span>
                    <span className="candidate-count">{cluster.total_occurrences} refs</span>
                  </div>
                  <span className="evolution-badge" style={{ fontSize: '0.65rem' }}>{cluster.category}</span>
                </div>

                {cluster.context_snippets?.length > 0 && (
                  <div className="candidate-snippets">
                    "{cluster.context_snippets[0]}"
                  </div>
                )}

                {cluster.suggested_properties?.length > 0 && (
                  <div className="candidate-tags">
                    {cluster.suggested_properties.slice(0, 4).map((p, i) => (
                      <span key={i} className="candidate-tag">+{p}</span>
                    ))}
                  </div>
                )}

                <div style={{ marginTop: 'auto', paddingTop: '8px' }}>
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', fontSize: '0.82rem', padding: '8px 12px', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '6px' }}
                    onClick={() => handleSynthesizeProposal(cluster)}
                    disabled={actionLoading}
                  >
                    <Sparkles size={14} />
                    <span>Synthesize Evolution Proposal</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Section 2: Schema Evolution Proposals */}
      <div className="proposals-section">
        <div className="candidate-section-title">
          <span>Schema Evolution Proposals ({proposals.length})</span>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Human-in-the-loop review with visual unified YAML diffs
          </span>
        </div>

        {proposals.length === 0 ? (
          <div className="glass-card" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            No proposals drafted yet. Click "Synthesize Evolution Proposal" above to generate one.
          </div>
        ) : (
          <div className="proposals-grid">
            {proposals.map((prop) => (
              <div key={prop.proposal_id} className="proposal-item">
                <div className="proposal-info">
                  <div className="proposal-title-row">
                    <span className="proposal-title">{prop.title}</span>
                    <span className={`proposal-status-badge status-${prop.status.toLowerCase()}`}>
                      {prop.status}
                    </span>
                  </div>
                  <span className="proposal-meta">
                    Target: <strong>{prop.schema_name}</strong> • Concept: <strong>{prop.concept_name}</strong> • Created: {new Date(prop.created_at).toLocaleString()}
                  </span>
                </div>

                <div>
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: '0.82rem', padding: '8px 14px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    onClick={() => setSelectedProposal(prop)}
                  >
                    <Eye size={14} />
                    <span>View Diff & Impact</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Proposal Review Modal / Diff Viewer */}
      {selectedProposal && (
        <div className="evolution-modal-overlay" onClick={() => setSelectedProposal(null)}>
          <div className="evolution-modal" onClick={(e) => e.stopPropagation()}>
            <div className="evolution-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <FileCode size={20} color="var(--accent-primary, #a855f7)" />
                <div>
                  <h4 style={{ margin: 0, color: 'var(--text-primary)' }}>{selectedProposal.title}</h4>
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    Proposal ID: {selectedProposal.proposal_id} • Status: {selectedProposal.status}
                  </span>
                </div>
              </div>
              <button className="btn-icon" onClick={() => setSelectedProposal(null)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>

            <div className="evolution-modal-body">
              {/* Impact Assessment KPIs */}
              {selectedProposal.impact_assessment && (
                <div className="impact-grid">
                  <div className="impact-metric-card">
                    <span className="impact-metric-label">Palantir Score</span>
                    <span className="impact-metric-val" style={{ color: '#10b981' }}>
                      {selectedProposal.impact_assessment.palantir_governance_score}%
                    </span>
                  </div>
                  <div className="impact-metric-card">
                    <span className="impact-metric-label">Proposed Entities</span>
                    <span className="impact-metric-val">
                      {selectedProposal.impact_assessment.proposed_entities_count}
                    </span>
                  </div>
                  <div className="impact-metric-card">
                    <span className="impact-metric-label">Fan-out Risk</span>
                    <span className="impact-metric-val" style={{ color: '#38bdf8' }}>
                      {selectedProposal.impact_assessment.fanout_risk}
                    </span>
                  </div>
                  <div className="impact-metric-card">
                    <span className="impact-metric-label">Query Impact</span>
                    <span className="impact-metric-val" style={{ fontSize: '0.95rem', color: '#a78bfa' }}>
                      {selectedProposal.impact_assessment.query_performance_impact}
                    </span>
                  </div>
                </div>
              )}

              {/* Governance Checks */}
              {selectedProposal.impact_assessment?.governance_checks && (
                <div className="governance-checks">
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#34d399', textTransform: 'uppercase' }}>
                    Palantir Structural Governance Verification
                  </span>
                  {selectedProposal.impact_assessment.governance_checks.map((chk, i) => (
                    <div key={i} className="governance-check-item">
                      <CheckCircle2 size={14} />
                      <span>{chk}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Unified Diff */}
              <div className="diff-container">
                <div className="diff-header">
                  <span>UNIFIED YAML SCHEMA DIFF</span>
                  <span>{selectedProposal.schema_name}.yaml</span>
                </div>
                <div className="diff-body">
                  {selectedProposal.diff ? (
                    selectedProposal.diff.split('\n').map((line, idx) => renderDiffLine(line, idx))
                  ) : (
                    <div style={{ padding: '16px', color: 'var(--text-muted)' }}>No diff available</div>
                  )}
                </div>
              </div>
            </div>

            <div className="evolution-modal-footer">
              {selectedProposal.status === 'PENDING' ? (
                <>
                  <button
                    className="btn btn-reject"
                    onClick={() => handleReject(selectedProposal.proposal_id)}
                    disabled={actionLoading}
                  >
                    <XCircle size={15} />
                    <span>Reject Proposal</span>
                  </button>
                  <button
                    className="btn btn-approve"
                    onClick={() => handleApprove(selectedProposal.proposal_id)}
                    disabled={actionLoading}
                  >
                    <Check size={15} />
                    <span>Approve & Hot-Reload Schema</span>
                  </button>
                </>
              ) : (
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', alignSelf: 'center' }}>
                  This proposal has been {selectedProposal.status.toLowerCase()} on {selectedProposal.reviewed_at ? new Date(selectedProposal.reviewed_at).toLocaleDateString() : 'N/A'}.
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
