import { useState, useEffect } from 'react';
import {
  Shield, Zap, GitBranch, Eye, EyeOff, Mail, Phone, CreditCard,
  Hash, Calendar, Globe, SlidersHorizontal, Timer, Database,
  ArrowRightLeft, Boxes, CircleDot, Save, RotateCcw, Settings, Sparkles
} from 'lucide-react';
import ReconciliationPanel from '../components/ReconciliationPanel';
import OntologyEvolutionPanel from '../components/OntologyEvolutionPanel';
import './AdminPage.css';

// ─── Default Guardrails Config ─────────────────────────────────────────────────
const DEFAULT_GUARDRAILS = [
  { id: 'ssn', label: 'SSN Detector', desc: 'Social Security Numbers (XXX-XX-XXXX)', icon: Hash, enabled: true },
  { id: 'phone', label: 'Phone Detector', desc: 'Phone numbers (domestic & intl)', icon: Phone, enabled: true },
  { id: 'email', label: 'Email Detector', desc: 'Email addresses (user@domain)', icon: Mail, enabled: true },
  { id: 'credit_card', label: 'Credit Card', desc: 'Visa, Mastercard, Amex patterns', icon: CreditCard, enabled: false },
  { id: 'dob', label: 'Date of Birth', desc: 'Date patterns (MM/DD/YYYY)', icon: Calendar, enabled: true },
  { id: 'ip_address', label: 'IP Address', desc: 'IPv4 and IPv6 addresses', icon: Globe, enabled: false },
  { id: 'npi', label: 'NPI Detector', desc: 'National Provider Identifier (CMS 10-digit Luhn check)', icon: Hash, enabled: true },
  { id: 'dea', label: 'DEA Number', desc: 'Drug Enforcement Admin Rx checksum (2 letters + 7 digits)', icon: Hash, enabled: true },
  { id: 'mrn', label: 'Medical Record (MRN)', desc: 'Clinical chart identifiers (MRN-XXXXXX)', icon: Hash, enabled: true },
  { id: 'ein', label: 'US EIN / ITIN', desc: 'Federal Taxpayer Identification numbers', icon: Hash, enabled: false },
  { id: 'cusip', label: 'CUSIP / Securities', desc: 'Financial equity & bond identifiers', icon: Hash, enabled: false },
];

// ─── Default Gateway Config ────────────────────────────────────────────────────
const DEFAULT_GATEWAY = {
  rpm: 20,
  tpm: 100000,
  cacheTTL: 300,
  fallbackModels: [
    { name: 'Gemini 2.5 Flash', provider: 'google' },
    { name: 'GPT-4o Mini', provider: 'openai' },
    { name: 'Llama 3.1 8B', provider: 'ollama' },
  ],
};

// ─── Default Ontology Schema ───────────────────────────────────────────────────
const DEFAULT_ONTOLOGY = [
  {
    label: 'Patient',
    properties: [
      { key: 'name', type: 'String' },
      { key: 'age', type: 'Integer' },
      { key: 'gender', type: 'String' },
    ],
    relations: ['HAS_DIAGNOSIS', 'PRESCRIBED_MEDICATION', 'HAS_VISIT'],
  },
  {
    label: 'Diagnosis',
    properties: [
      { key: 'name', type: 'String' },
      { key: 'icd_code', type: 'String' },
      { key: 'diagnosed_date', type: 'Date' },
    ],
    relations: ['TREATED_WITH', 'OBSERVED_IN'],
  },
  {
    label: 'Medication',
    properties: [
      { key: 'name', type: 'String' },
      { key: 'dosage', type: 'String' },
      { key: 'frequency', type: 'String' },
    ],
    relations: ['PRESCRIBED_FOR', 'INTERACTS_WITH'],
  },
  {
    label: 'Observation',
    properties: [
      { key: 'type', type: 'String' },
      { key: 'value', type: 'Float' },
      { key: 'unit', type: 'String' },
    ],
    relations: ['OBSERVED_IN', 'MEASURED_DURING'],
  },
];

const TABS = [
  { id: 'guardrails', label: 'Guardrails', icon: Shield },
  { id: 'gateway', label: 'Gateway', icon: Zap },
  { id: 'ontology', label: 'Active Schema', icon: Boxes },
  { id: 'evolution', label: 'Ontology Evolution', icon: GitBranch },
  { id: 'reconciliation', label: 'Self-Healing Graph', icon: Sparkles },
];

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState('guardrails');
  const [guardrails, setGuardrails] = useState(DEFAULT_GUARDRAILS);
  const [promptThreshold, setPromptThreshold] = useState(0.85);
  const [activeDomain, setActiveDomain] = useState('healthtech');
  const [enableZeroShotAudit, setEnableZeroShotAudit] = useState(true);
  const [zeroShotThreshold, setZeroShotThreshold] = useState(0.60);
  const [strictComplianceMode, setStrictComplianceMode] = useState(false);
  const [gateway, setGateway] = useState(DEFAULT_GATEWAY);
  const [ontology] = useState(DEFAULT_ONTOLOGY);
  const [hasChanges, setHasChanges] = useState(false);

  // Live PII & Policy Inspector state
  const [inspectText, setInspectText] = useState('Patient John Doe (email: john.doe@hospital.org, MRN: 987654) treated by Dr. Robert Vance (NPI: 1234567893, DEA: AB1234563).');
  const [inspectRole, setInspectRole] = useState('viewer');
  const [inspectResults, setInspectResults] = useState(null);
  const [inspectLoading, setInspectLoading] = useState(false);

  useEffect(() => {
    fetch('/api/v2/admin/config')
      .then(res => res.json())
      .then(data => {
        if (data.guardrails) setGuardrails(data.guardrails);
        if (data.promptThreshold !== undefined) setPromptThreshold(data.promptThreshold);
        if (data.activeDomain) setActiveDomain(data.activeDomain);
        if (data.enableZeroShotAudit !== undefined) setEnableZeroShotAudit(data.enableZeroShotAudit);
        if (data.zeroShotAuditThreshold !== undefined) setZeroShotThreshold(data.zeroShotAuditThreshold);
        if (data.strictComplianceMode !== undefined) setStrictComplianceMode(data.strictComplianceMode);
        if (data.gateway) setGateway(data.gateway);
      })
      .catch(err => console.error("Failed to load admin config:", err));
  }, []);

  const applyDomainPreset = (preset) => {
    setActiveDomain(preset);
    setHasChanges(true);
    if (preset === 'healthtech') {
      const enabledIds = new Set(['ssn', 'phone', 'email', 'dob', 'npi', 'dea', 'mrn']);
      setGuardrails(prev => prev.map(g => ({ ...g, enabled: enabledIds.has(g.id) })));
      setInspectText('Patient John Doe (email: john.doe@hospital.org, MRN: 987654) treated by Dr. Robert Vance (NPI: 1234567893, DEA: AB1234563).');
    } else if (preset === 'fintech') {
      const enabledIds = new Set(['credit_card', 'ein', 'cusip', 'ssn', 'email', 'phone']);
      setGuardrails(prev => prev.map(g => ({ ...g, enabled: enabledIds.has(g.id) })));
      setInspectText('Apex Holdings LLC with EIN 12-3456789 issued payment with Credit Card 4532-1234-5678-9012 holding CUSIP 037833100.');
    } else {
      const enabledIds = new Set(['ssn', 'phone', 'email', 'credit_card', 'dob']);
      setGuardrails(prev => prev.map(g => ({ ...g, enabled: enabledIds.has(g.id) })));
      setInspectText('User Jane Smith (phone: +1-415-555-2671, email: jane.smith@domain.com) requested account access.');
    }
  };

  const toggleGuardrail = (id) => {
    setGuardrails(prev => prev.map(g => g.id === id ? { ...g, enabled: !g.enabled } : g));
    setHasChanges(true);
  };

  const updateGateway = (key, value) => {
    setGateway(prev => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleInspect = async () => {
    if (!inspectText.trim()) return;
    setInspectLoading(true);
    try {
      const res = await fetch('/api/v2/guardrails/inspect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: inspectText,
          domain: activeDomain,
          user_role: inspectRole,
        }),
      });
      const data = await res.json();
      setInspectResults(data);
    } catch (err) {
      console.error('Guardrail inspection failed:', err);
    } finally {
      setInspectLoading(false);
    }
  };

  const handleSave = () => {
    fetch('/api/v2/admin/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        guardrails,
        promptThreshold,
        activeDomain,
        enableZeroShotAudit,
        zeroShotAuditThreshold: zeroShotThreshold,
        strictComplianceMode,
        gateway,
      })
    })
    .then(res => res.json())
    .then(() => setHasChanges(false))
    .catch(err => console.error("Failed to save admin config:", err));
  };

  const handleReset = () => {
    setGuardrails(DEFAULT_GUARDRAILS);
    setPromptThreshold(0.85);
    setGateway(DEFAULT_GATEWAY);
    setHasChanges(true); // marked as true so they can save the reset state
  };

  return (
    <div className="admin-page">
      {/* Header */}
      <div className="admin-header">
        <h2 className="gradient-text">Admin Configuration Hub</h2>
        <p>Dynamically configure Guardrails, Gateway policies, and Ontology schemas at runtime.</p>
      </div>

      {/* Tabs */}
      <div className="admin-tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`admin-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <tab.icon size={16} />
            {tab.label}
            {tab.id === 'guardrails' && (
              <span className="admin-tab-badge">{guardrails.filter(g => g.enabled).length}</span>
            )}
            {tab.id === 'ontology' && (
              <span className="admin-tab-badge">{ontology.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* ─── Guardrails Tab ──────────────────────────────────────────────── */}
      {activeTab === 'guardrails' && (
        <div className="admin-section">
          {/* Domain Compliance Presets */}
          <div className="admin-section-header">
            <div className="admin-section-title">
              <Shield size={20} color="var(--accent-primary)" />
              <div>
                <h3>Compliance & Domain Presets</h3>
                <span className="admin-section-desc">Instantly configure regulatory policies and entity detectors</span>
              </div>
            </div>
            <div className="domain-presets-bar">
              <button
                className={`preset-btn ${activeDomain === 'healthtech' ? 'active' : ''}`}
                onClick={() => applyDomainPreset('healthtech')}
              >
                Healthcare (HIPAA Safe Harbor)
              </button>
              <button
                className={`preset-btn ${activeDomain === 'fintech' ? 'active' : ''}`}
                onClick={() => applyDomainPreset('fintech')}
              >
                Fintech (PCI-DSS &amp; GLBA)
              </button>
              <button
                className={`preset-btn ${activeDomain === 'general' ? 'active' : ''}`}
                onClick={() => applyDomainPreset('general')}
              >
                General (GDPR / ISO 27001)
              </button>
            </div>
          </div>

          <div className="admin-toggle-grid">
            {guardrails.map(g => (
              <div key={g.id} className="glass-card admin-toggle-card">
                <div className="admin-toggle-info">
                  <div className="admin-toggle-icon">
                    {g.enabled ? <Eye size={16} /> : <EyeOff size={16} />}
                  </div>
                  <div className="admin-toggle-text">
                    <h4>{g.label}</h4>
                    <p>{g.desc}</p>
                  </div>
                </div>
                <label className="toggle-switch">
                  <input type="checkbox" checked={g.enabled} onChange={() => toggleGuardrail(g.id)} />
                  <span className="toggle-slider" />
                </label>
              </div>
            ))}
          </div>

          {/* Hybrid Zero-Shot NER & PEP Governance Controls */}
          <div className="admin-slider-group">
            <div className="admin-section-title" style={{ marginBottom: 16 }}>
              <Sparkles size={20} color="var(--accent-primary)" />
              <div>
                <h3>Hybrid Zero-Shot NER &amp; Policy Governance</h3>
                <span className="admin-section-desc">Tier 1 Flash LLM auditor for ambiguous entities &amp; PEP-PDP rules</span>
              </div>
            </div>

            <div className="glass-card admin-slider-row">
              <div className="admin-slider-header">
                <span className="admin-slider-label">
                  <Sparkles size={14} /> Zero-Shot LLM Audit Layer (Gemini 2.5 Flash)
                </span>
                <label className="toggle-switch">
                  <input
                    type="checkbox"
                    checked={enableZeroShotAudit}
                    onChange={e => { setEnableZeroShotAudit(e.target.checked); setHasChanges(true); }}
                  />
                  <span className="toggle-slider" />
                </label>
              </div>
              <p className="admin-slider-desc">
                Automatically activates low-latency LLM auditor when Presidio confidence is below threshold ({zeroShotThreshold}).
              </p>
            </div>

            <div className="glass-card admin-slider-row">
              <div className="admin-slider-header">
                <span className="admin-slider-label">
                  <SlidersHorizontal size={14} /> Zero-Shot Audit Trigger Threshold
                </span>
                <span className="admin-slider-value">{(zeroShotThreshold * 100).toFixed(0)}%</span>
              </div>
              <div className="admin-slider">
                <input
                  type="range"
                  min="0.3"
                  max="0.8"
                  step="0.05"
                  value={zeroShotThreshold}
                  onChange={e => { setZeroShotThreshold(parseFloat(e.target.value)); setHasChanges(true); }}
                />
              </div>
              <p className="admin-slider-desc">
                Scores below this trigger the asynchronous Tier 1 Flash auditor with strict 800ms circuit breaker.
              </p>
            </div>

            <div className="glass-card admin-slider-row">
              <div className="admin-slider-header">
                <span className="admin-slider-label">
                  <Shield size={14} /> Strict Compliance Mode
                </span>
                <label className="toggle-switch">
                  <input
                    type="checkbox"
                    checked={strictComplianceMode}
                    onChange={e => { setStrictComplianceMode(e.target.checked); setHasChanges(true); }}
                  />
                  <span className="toggle-slider" />
                </label>
              </div>
              <p className="admin-slider-desc">
                Enforces Zero-Shot LLM Audit on all incoming prompts regardless of Presidio confidence.
              </p>
            </div>

            {/* Prompt Injection Threshold */}
            <div className="glass-card admin-slider-row">
              <div className="admin-slider-header">
                <span className="admin-slider-label">
                  <Shield size={14} /> Prompt Injection Detection Strictness
                </span>
                <span className="admin-slider-value">{(promptThreshold * 100).toFixed(0)}%</span>
              </div>
              <div className="admin-slider">
                <input
                  type="range"
                  min="0.5"
                  max="1"
                  step="0.01"
                  value={promptThreshold}
                  onChange={e => { setPromptThreshold(parseFloat(e.target.value)); setHasChanges(true); }}
                />
              </div>
              <p className="admin-slider-desc">
                Lower values are more strict (more false positives). Higher values are more lenient.
              </p>
            </div>
          </div>

          {/* Interactive Live PII & Policy Inspector */}
          <div className="admin-slider-group" style={{ marginTop: 24 }}>
            <div className="admin-section-title" style={{ marginBottom: 16 }}>
              <Eye size={20} color="var(--accent-primary)" />
              <div>
                <h3>Live PII &amp; PEP Policy Inspector</h3>
                <span className="admin-section-desc">Test real-time hybrid entity detection, tokenization, and RBAC authorization</span>
              </div>
            </div>

            <div className="glass-card pii-inspector-card">
              <div className="inspector-controls-bar">
                <div className="role-selector-wrap">
                  <span className="inspector-role-lbl">Simulated Role:</span>
                  <select
                    className="inspector-role-select"
                    value={inspectRole}
                    onChange={e => setInspectRole(e.target.value)}
                  >
                    <option value="viewer">Viewer (Public / Unauthorized)</option>
                    <option value="compliance_officer">Compliance Officer (Authorized Unmask)</option>
                    <option value="admin">Administrator (Full Clearance)</option>
                  </select>
                </div>
                <button
                  className="btn-primary inspector-btn"
                  onClick={handleInspect}
                  disabled={inspectLoading}
                >
                  {inspectLoading ? 'Analyzing...' : 'Inspect & Evaluate Policy (PEP)'}
                </button>
              </div>

              <textarea
                className="inspector-textarea"
                rows={3}
                value={inspectText}
                onChange={e => setInspectText(e.target.value)}
                placeholder="Enter text containing PII/PHI to test..."
              />

              {inspectResults && (
                <div className="inspector-results-grid">
                  <div className="inspector-col">
                    <span className="inspector-res-lbl">Masked Text (LLM Ingestion View):</span>
                    <div className="inspector-code-box">{inspectResults.masked_text}</div>
                    <div className="policy-badge-row">
                      <span className="policy-badge action-mask">
                        PEP Action: {inspectResults.policy_decision?.action}
                      </span>
                      <span className="policy-rule-lbl">
                        Rule: {inspectResults.policy_decision?.rule}
                      </span>
                    </div>
                  </div>

                  <div className="inspector-col">
                    <span className="inspector-res-lbl">Detected Entities ({inspectResults.findings?.length || 0}):</span>
                    <div className="inspector-findings-list">
                      {inspectResults.findings?.map((f, i) => (
                        <div key={i} className="finding-pill-item">
                          <span className="finding-type">{f.entity_type}</span>
                          <span className="finding-val">{f.value}</span>
                          <span className="finding-source">{f.source}</span>
                          <span className="finding-score">{(f.score * 100).toFixed(0)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ─── Gateway Tab ─────────────────────────────────────────────────── */}
      {activeTab === 'gateway' && (
        <div className="admin-section">
          <div className="admin-section-header">
            <div className="admin-section-title">
              <SlidersHorizontal size={20} color="var(--accent-primary)" />
              <div>
                <h3>Rate Limiting & Caching</h3>
                <span className="admin-section-desc">Control API throughput and semantic cache behavior</span>
              </div>
            </div>
          </div>

          <div className="admin-slider-group">
            {/* RPM */}
            <div className="glass-card admin-slider-row">
              <div className="admin-slider-header">
                <span className="admin-slider-label"><Zap size={14} /> Requests Per Minute (RPM)</span>
                <span className="admin-slider-value">{gateway.rpm}</span>
              </div>
              <div className="admin-slider">
                <input type="range" min="1" max="100" value={gateway.rpm} onChange={e => updateGateway('rpm', parseInt(e.target.value))} />
              </div>
              <p className="admin-slider-desc">Maximum LLM API calls allowed per minute per user session.</p>
            </div>

            {/* TPM */}
            <div className="glass-card admin-slider-row">
              <div className="admin-slider-header">
                <span className="admin-slider-label"><Database size={14} /> Tokens Per Minute (TPM)</span>
                <span className="admin-slider-value">{gateway.tpm.toLocaleString()}</span>
              </div>
              <div className="admin-slider">
                <input type="range" min="10000" max="500000" step="10000" value={gateway.tpm} onChange={e => updateGateway('tpm', parseInt(e.target.value))} />
              </div>
              <p className="admin-slider-desc">Maximum tokens consumed per minute across all active sessions.</p>
            </div>

            {/* Cache TTL */}
            <div className="glass-card admin-slider-row">
              <div className="admin-slider-header">
                <span className="admin-slider-label"><Timer size={14} /> Semantic Cache TTL</span>
                <span className="admin-slider-value">{gateway.cacheTTL}s</span>
              </div>
              <div className="admin-slider">
                <input type="range" min="30" max="3600" step="30" value={gateway.cacheTTL} onChange={e => updateGateway('cacheTTL', parseInt(e.target.value))} />
              </div>
              <p className="admin-slider-desc">Time-to-live for cached semantic query results. Set higher for cost savings.</p>
            </div>
          </div>

          {/* Fallback Routing */}
          <div className="admin-section-title" style={{ marginBottom: 16 }}>
            <ArrowRightLeft size={20} color="var(--accent-primary)" />
            <div>
              <h3>LLM Fallback Routing</h3>
              <span className="admin-section-desc">Priority order for model failover when primary is unavailable</span>
            </div>
          </div>
          <div className="gateway-fallback-list">
            {gateway.fallbackModels.map((model, idx) => (
              <div key={idx} className="glass-card gateway-fallback-row">
                <span className="gateway-priority">{idx + 1}</span>
                <span className="gateway-model-name">{model.name}</span>
                <span className="gateway-model-provider">{model.provider}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── Ontology Tab ────────────────────────────────────────────────── */}
      {activeTab === 'ontology' && (
        <div className="admin-section">
          <div className="admin-section-header">
            <div className="admin-section-title">
              <Boxes size={20} color="var(--accent-primary)" />
              <div>
                <h3>Domain Schema (HealthTech)</h3>
                <span className="admin-section-desc">Governed entity labels, properties, and relationship types</span>
              </div>
            </div>
          </div>

          <div className="ontology-schema-grid">
            {ontology.map((entity, idx) => (
              <div key={idx} className="glass-card ontology-entity-card" style={{ animationDelay: `${idx * 0.05}s` }}>
                <div className="ontology-entity-header">
                  <div className="ontology-entity-icon">
                    <CircleDot size={16} />
                  </div>
                  <span className="ontology-entity-name">{entity.label}</span>
                </div>

                <div className="ontology-entity-props">
                  {entity.properties.map((prop, pi) => (
                    <div key={pi} className="ontology-prop">
                      <span className="ontology-prop-key">{prop.key}</span>
                      <span className="ontology-prop-type">{prop.type}</span>
                    </div>
                  ))}
                </div>

                <div className="ontology-relations">
                  {entity.relations.map((rel, ri) => (
                    <span key={ri} className="ontology-relation-tag">
                      <ArrowRightLeft size={10} /> {rel}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── Tab 4: Dynamic Ontology Evolution (Phase 5) ───────────────── */}
      {activeTab === 'evolution' && <OntologyEvolutionPanel />}

      {/* ─── Tab 5: Self-Healing Knowledge Graph (Reconciliation) ──────── */}
      {activeTab === 'reconciliation' && <ReconciliationPanel />}

      {/* ─── Save Bar ────────────────────────────────────────────────────── */}
      {hasChanges && (
        <div className="admin-save-bar">
          <span className="admin-save-hint">You have unsaved configuration changes</span>
          <button className="btn" onClick={handleReset}>
            <RotateCcw size={14} /> Reset
          </button>
          <button className="btn btn-primary" onClick={handleSave}>
            <Save size={14} /> Save Configuration
          </button>
        </div>
      )}
    </div>
  );
}
