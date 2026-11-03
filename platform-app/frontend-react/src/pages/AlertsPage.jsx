import { useState, useEffect } from 'react';
import {
  Bell, AlertTriangle, AlertCircle, Info, CheckCircle2, ShieldAlert,
  Plus, Trash2, ToggleLeft, ToggleRight, Filter, RefreshCw, X, Radio,
  Send, ExternalLink, Sliders
} from 'lucide-react';
import {
  getAlertsFeed,
  markAlertRead,
  dismissAlert,
  listAlertRules,
  createAlertRule,
  toggleAlertRule,
  deleteAlertRule,
  getStoredRole
} from '../api/client';
import './AlertsPage.css';

export default function AlertsPage() {
  const [activeTab, setActiveTab] = useState('feed'); // 'feed' | 'rules'
  const [alerts, setAlerts] = useState([]);
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState(''); // '' | 'unread' | 'read'
  const [severityFilter, setSeverityFilter] = useState(''); // '' | 'CRITICAL' | 'WARNING' | 'INFO'
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [message, setMessage] = useState(null);

  const isAdmin = getStoredRole() === 'admin';

  // New Rule Form State
  const [ruleForm, setRuleForm] = useState({
    name: '',
    description: '',
    rule_type: 'property_threshold',
    target_label: 'Observation',
    property_name: 'value',
    operator: '>',
    threshold_value: '',
    severity: 'WARNING',
    webhook_url: '',
  });

  const loadFeed = async () => {
    setLoading(true);
    try {
      const res = await getAlertsFeed(statusFilter || null, severityFilter || null, 50);
      setAlerts(res.alerts || []);
    } catch (err) {
      console.error("Failed to load alerts feed:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadRules = async () => {
    try {
      const res = await listAlertRules();
      setRules(res.rules || []);
    } catch (err) {
      console.error("Failed to load rules:", err);
    }
  };

  useEffect(() => {
    if (activeTab === 'feed') {
      loadFeed();
    } else {
      loadRules();
    }
  }, [activeTab, statusFilter, severityFilter]);

  const handleMarkRead = async (id) => {
    try {
      await markAlertRead(id);
      setAlerts(prev => prev.map(a => a.id === id ? { ...a, status: 'read' } : a));
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to update alert.' });
    }
  };

  const handleDismiss = async (id) => {
    try {
      await dismissAlert(id);
      setAlerts(prev => prev.filter(a => a.id !== id));
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to dismiss alert.' });
    }
  };

  const handleToggleRule = async (ruleId) => {
    try {
      const updated = await toggleAlertRule(ruleId);
      setRules(prev => prev.map(r => r.id === ruleId ? updated : r));
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to toggle rule.' });
    }
  };

  const handleDeleteRule = async (ruleId) => {
    if (!window.confirm("Are you sure you want to delete this standing rule?")) return;
    try {
      await deleteAlertRule(ruleId);
      setRules(prev => prev.filter(r => r.id !== ruleId));
      setMessage({ type: 'success', text: "Standing rule deleted." });
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to delete rule.' });
    }
  };

  const handleCreateRuleSubmit = async (e) => {
    e.preventDefault();
    if (!ruleForm.name.trim()) return;

    try {
      // Parse numeric threshold if possible
      let val = ruleForm.threshold_value;
      if (!isNaN(Number(val)) && val.trim() !== '') {
        val = Number(val);
      }

      await createAlertRule({
        ...ruleForm,
        threshold_value: val,
      });

      setShowRuleModal(false);
      setMessage({ type: 'success', text: `Standing rule '${ruleForm.name}' activated!` });
      setRuleForm({
        name: '',
        description: '',
        rule_type: 'property_threshold',
        target_label: 'Observation',
        property_name: 'value',
        operator: '>',
        threshold_value: '',
        severity: 'WARNING',
        webhook_url: '',
      });
      loadRules();
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to create standing rule.' });
    }
  };

  return (
    <div className="alerts-page">
      {/* Page Header */}
      <div className="alerts-header">
        <div>
          <h2 className="gradient-text">Proactive Alerts & Standing Goals</h2>
          <p>Autonomous monitoring evaluating incoming data streams and graph events against critical safety thresholds.</p>
        </div>

        <div className="alerts-top-actions">
          <div className="tab-pill-group">
            <button
              className={`tab-pill ${activeTab === 'feed' ? 'active' : ''}`}
              onClick={() => setActiveTab('feed')}
            >
              <Bell size={15} /> Alerts Feed
            </button>
            <button
              className={`tab-pill ${activeTab === 'rules' ? 'active' : ''}`}
              onClick={() => setActiveTab('rules')}
            >
              <Sliders size={15} /> Standing Rules ({rules.length})
            </button>
          </div>

          {isAdmin && activeTab === 'rules' && (
            <button className="btn-create-rule" onClick={() => setShowRuleModal(true)}>
              <Plus size={15} /> New Standing Rule
            </button>
          )}
        </div>
      </div>

      {message && (
        <div className={`alert-toast-banner ${message.type}`}>
          {message.type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span>{message.text}</span>
          <button className="banner-close" onClick={() => setMessage(null)}><X size={14} /></button>
        </div>
      )}

      {/* Main Subview */}
      {activeTab === 'feed' ? (
        <div className="alerts-feed-view">
          {/* Filters Bar */}
          <div className="feed-filters glass-card">
            <div className="filter-item">
              <label>Status</label>
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All Statuses</option>
                <option value="unread">Unread Only</option>
                <option value="read">Read</option>
              </select>
            </div>

            <div className="filter-item">
              <label>Severity</label>
              <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
                <option value="">All Severities</option>
                <option value="CRITICAL">Critical</option>
                <option value="WARNING">Warning</option>
                <option value="INFO">Info</option>
              </select>
            </div>

            <button className="btn-refresh" onClick={loadFeed} disabled={loading}>
              <RefreshCw className={loading ? "spin" : ""} size={14} /> Refresh
            </button>
          </div>

          {/* Alerts Feed List */}
          <div className="alerts-list">
            {alerts.length === 0 ? (
              <div className="empty-alerts-state glass-card">
                <Bell size={42} className="empty-bell-icon" />
                <h4>No Alerts Triggered</h4>
                <p>Standing rules are actively monitoring data intake. Triggered alerts will appear here in real time.</p>
              </div>
            ) : (
              alerts.map((alert) => (
                <div key={alert.id} className={`alert-card glass-card severity-${alert.severity.toLowerCase()} status-${alert.status}`}>
                  <div className="alert-card-left">
                    <div className="severity-indicator">
                      {alert.severity === 'CRITICAL' && <AlertCircle size={20} className="icon-critical" />}
                      {alert.severity === 'WARNING' && <AlertTriangle size={20} className="icon-warning" />}
                      {alert.severity === 'INFO' && <Info size={20} className="icon-info" />}
                    </div>

                    <div className="alert-body">
                      <div className="alert-title-row">
                        <h4>{alert.title}</h4>
                        <span className={`severity-tag ${alert.severity.toLowerCase()}`}>{alert.severity}</span>
                        {alert.status === 'unread' && <span className="unread-dot">New</span>}
                      </div>

                      <p className="alert-message">{alert.message}</p>

                      <div className="alert-meta-row">
                        <span className="meta-chip">Entity: <strong>{alert.entity_label}</strong> ({alert.entity_id})</span>
                        {alert.matched_properties?.source_file && (
                          <span className="meta-chip">Source: {alert.matched_properties.source_file}</span>
                        )}
                        <span className="alert-timestamp">
                          {new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} • {new Date(alert.timestamp).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="alert-card-actions">
                    {alert.status === 'unread' && (
                      <button className="btn-action mark-read" onClick={() => handleMarkRead(alert.id)}>
                        Mark Read
                      </button>
                    )}
                    <button className="btn-action dismiss" onClick={() => handleDismiss(alert.id)}>
                      Dismiss
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      ) : (
        /* Standing Rules View */
        <div className="rules-view">
          <div className="rules-grid">
            {rules.map((rule) => (
              <div key={rule.id} className={`rule-card glass-card ${rule.enabled ? 'rule-active' : 'rule-inactive'}`}>
                <div className="rule-header-row">
                  <span className={`severity-tag ${rule.severity.toLowerCase()}`}>{rule.severity}</span>
                  <div className="rule-toggle-action">
                    {isAdmin && (
                      <button className="icon-toggle-btn" onClick={() => handleToggleRule(rule.id)}>
                        {rule.enabled ? <ToggleRight size={26} className="toggle-on" /> : <ToggleLeft size={26} className="toggle-off" />}
                      </button>
                    )}
                  </div>
                </div>

                <h4 className="rule-title">{rule.name}</h4>
                <p className="rule-desc">{rule.description}</p>

                <div className="rule-condition-box">
                  {rule.rule_type === 'cypher' ? (
                    <div className="cypher-condition">
                      <span className="cond-label">Graph Cypher Pattern:</span>
                      <code>{rule.cypher_query}</code>
                    </div>
                  ) : (
                    <div className="threshold-condition">
                      <span className="cond-label">Threshold Condition:</span>
                      <code>{rule.target_label}.{rule.property_name} {rule.operator} {String(rule.threshold_value)}</code>
                    </div>
                  )}
                </div>

                {rule.webhook_url && (
                  <div className="webhook-badge">
                    <Send size={12} /> Webhook: {rule.webhook_url}
                  </div>
                )}

                {isAdmin && (
                  <div className="rule-footer">
                    <span className="rule-status-text">{rule.enabled ? "Monitoring Active" : "Paused"}</span>
                    <button className="btn-rule-delete" onClick={() => handleDeleteRule(rule.id)}>
                      <Trash2 size={14} /> Delete
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Rule Builder Modal */}
      {showRuleModal && (
        <div className="rule-modal-backdrop">
          <div className="rule-modal glass-card">
            <div className="modal-header">
              <h3>Create Standing Goal Rule</h3>
              <button className="modal-close" onClick={() => setShowRuleModal(false)}><X size={18} /></button>
            </div>

            <form onSubmit={handleCreateRuleSubmit} className="rule-form">
              <div className="form-group">
                <label>Rule Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Critical Tachycardia Flag"
                  required
                  value={ruleForm.name}
                  onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label>Description</label>
                <textarea
                  rows="2"
                  placeholder="Clinical rationale or operational standing goal..."
                  value={ruleForm.description}
                  onChange={(e) => setRuleForm({ ...ruleForm, description: e.target.value })}
                />
              </div>

              <div className="form-row">
                <div className="form-group flex-1">
                  <label>Target Graph Label</label>
                  <input
                    type="text"
                    placeholder="e.g. Observation, Patient"
                    value={ruleForm.target_label}
                    onChange={(e) => setRuleForm({ ...ruleForm, target_label: e.target.value })}
                  />
                </div>

                <div className="form-group flex-1">
                  <label>Property Name</label>
                  <input
                    type="text"
                    placeholder="e.g. heart_rate, potassium"
                    value={ruleForm.property_name}
                    onChange={(e) => setRuleForm({ ...ruleForm, property_name: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group flex-1">
                  <label>Operator</label>
                  <select
                    value={ruleForm.operator}
                    onChange={(e) => setRuleForm({ ...ruleForm, operator: e.target.value })}
                  >
                    <option value=">">&gt; (Greater than)</option>
                    <option value=">=">&gt;= (Greater or equal)</option>
                    <option value="<">&lt; (Less than)</option>
                    <option value="<=">&lt;= (Less or equal)</option>
                    <option value="==">== (Equals)</option>
                    <option value="!=">!= (Not equals)</option>
                    <option value="contains">contains (String match)</option>
                  </select>
                </div>

                <div className="form-group flex-1">
                  <label>Threshold Value *</label>
                  <input
                    type="text"
                    placeholder="e.g. 5.5, 100, abnormal"
                    required
                    value={ruleForm.threshold_value}
                    onChange={(e) => setRuleForm({ ...ruleForm, threshold_value: e.target.value })}
                  />
                </div>

                <div className="form-group flex-1">
                  <label>Severity</label>
                  <select
                    value={ruleForm.severity}
                    onChange={(e) => setRuleForm({ ...ruleForm, severity: e.target.value })}
                  >
                    <option value="CRITICAL">Critical</option>
                    <option value="WARNING">Warning</option>
                    <option value="INFO">Info</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Dispatch Webhook URL (Optional)</label>
                <input
                  type="url"
                  placeholder="https://api.external-system.com/webhook"
                  value={ruleForm.webhook_url}
                  onChange={(e) => setRuleForm({ ...ruleForm, webhook_url: e.target.value })}
                />
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-cancel" onClick={() => setShowRuleModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-submit">
                  Activate Standing Goal
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
