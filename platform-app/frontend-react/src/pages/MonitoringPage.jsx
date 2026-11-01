import { useState, useEffect, useCallback } from 'react';
import { 
  DollarSign, 
  Activity, 
  Sparkles, 
  Clock, 
  Zap, 
  Download, 
  RefreshCw, 
  Search, 
  CheckCircle2, 
  AlertTriangle, 
  ArrowRightLeft, 
  FileSpreadsheet, 
  Eye, 
  X, 
  Cpu, 
  Globe, 
  Network 
} from 'lucide-react';
import { getMonitoringLogs, getMonitoringSummary, exportMonitoring } from '../api/client';
import './MonitoringPage.css';

export default function MonitoringPage() {
  const [summary, setSummary] = useState(null);
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedLog, setSelectedLog] = useState(null);

  // Filters
  const [search, setSearch] = useState('');
  const [modelFilter, setModelFilter] = useState('');
  const [smartRoutedFilter, setSmartRoutedFilter] = useState('');

  const fetchTelemetry = useCallback(async () => {
    setLoading(true);
    try {
      const [sumData, logData] = await Promise.all([
        getMonitoringSummary().catch(() => null),
        getMonitoringLogs(50, 0, modelFilter, smartRoutedFilter, search).catch(() => ({ logs: [], total: 0 })),
      ]);
      setSummary(sumData);
      setLogs(logData.logs || []);
      setTotal(logData.total || 0);
    } catch (err) {
      console.error('Failed to load telemetry:', err);
    } finally {
      setLoading(false);
    }
  }, [search, modelFilter, smartRoutedFilter]);

  useEffect(() => {
    fetchTelemetry();
  }, [fetchTelemetry]);

  const handleExportCSV = () => {
    exportMonitoring('csv');
  };

  const handleExportExcel = () => {
    exportMonitoring('excel');
  };

  const formatCost = (val) => {
    if (val == null) return '$0.00000';
    return `$${Number(val).toFixed(5)}`;
  };

  const formatTokens = (num) => {
    if (num == null) return '0';
    return Number(num).toLocaleString();
  };

  return (
    <div className="monitoring-page">
      <div className="page-header">
        <div className="page-header-text">
          <h2 className="gradient-text">Real-Time Observability & Monitoring</h2>
          <p>Live LLM call telemetry, AI Economics spend analytics, and cost-optimization KPIs.</p>
        </div>
        <div className="page-header-actions">
          <button className="btn btn-secondary" onClick={handleExportCSV} title="Download CSV Audit Report">
            <Download size={14} className="icon-mr" /> Export CSV
          </button>
          <button className="btn btn-primary" onClick={handleExportExcel} title="Download Excel Audit Report">
            <FileSpreadsheet size={14} className="icon-mr" /> Export Excel
          </button>
          <button className="btn icon-btn" onClick={fetchTelemetry} title="Refresh Telemetry">
            <RefreshCw size={16} className={loading ? 'spin-icon' : ''} />
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="monitoring-kpis">
        <div className="kpi-card glass-card">
          <div className="kpi-card-header">
            <span className="kpi-label">Total Spend (USD)</span>
            <div className="kpi-icon-wrap icon-spend">
              <DollarSign size={20} />
            </div>
          </div>
          <div className="kpi-value">{formatCost(summary?.total_spend_usd)}</div>
          <div className="kpi-subtext">Across {summary?.total_requests || 0} audited calls</div>
        </div>

        <div className="kpi-card glass-card">
          <div className="kpi-card-header">
            <span className="kpi-label">AI Economics Savings</span>
            <div className="kpi-icon-wrap icon-savings">
              <Sparkles size={20} />
            </div>
          </div>
          <div className="kpi-value gradient-text">
            {formatCost(summary?.estimated_savings_usd)}
          </div>
          <div className="kpi-subtext">
            {summary?.savings_percentage || 0}% saved vs frontier baseline
          </div>
        </div>

        <div className="kpi-card glass-card">
          <div className="kpi-card-header">
            <span className="kpi-label">Smart-Routed %</span>
            <div className="kpi-icon-wrap icon-router">
              <Zap size={20} />
            </div>
          </div>
          <div className="kpi-value">
            {summary?.smart_routed_percentage != null ? `${summary.smart_routed_percentage}%` : '0%'}
          </div>
          <div className="kpi-subtext">{summary?.smart_routed_count || 0} automated model switches</div>
        </div>

        <div className="kpi-card glass-card">
          <div className="kpi-card-header">
            <span className="kpi-label">Tokens Processed</span>
            <div className="kpi-icon-wrap icon-tokens">
              <Activity size={20} />
            </div>
          </div>
          <div className="kpi-value">{formatTokens(summary?.total_tokens)}</div>
          <div className="kpi-subtext">
            In: {formatTokens(summary?.total_input_tokens)} | Out: {formatTokens(summary?.total_output_tokens)}
          </div>
        </div>

        <div className="kpi-card glass-card">
          <div className="kpi-card-header">
            <span className="kpi-label">Avg Execution Latency</span>
            <div className="kpi-icon-wrap icon-latency">
              <Clock size={20} />
            </div>
          </div>
          <div className="kpi-value">{summary?.avg_duration_ms ? `${Math.round(summary.avg_duration_ms)}ms` : '—'}</div>
          <div className="kpi-subtext">End-to-end agent run duration</div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="monitoring-filters glass-card">
        <div className="filter-search-box">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            className="filter-input"
            placeholder="Search prompt, session ID, or call ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="filter-selects">
          <select
            className="filter-select"
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
            title="Filter by Model"
          >
            <option value="">All Models</option>
            <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
            <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
            <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
            <option value="gpt-4o">GPT-4o</option>
            <option value="gpt-4o-mini">GPT-4o Mini</option>
          </select>

          <select
            className="filter-select"
            value={smartRoutedFilter}
            onChange={(e) => setSmartRoutedFilter(e.target.value)}
            title="Filter by Routing Mode"
          >
            <option value="">All Routing Modes</option>
            <option value="true">Smart-Routed Only</option>
            <option value="false">Explicit Only</option>
          </select>
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="monitoring-table-container glass-card">
        <div className="table-header-info">
          <h3>Live Telemetry Audit Logs ({total} records)</h3>
        </div>

        {logs.length === 0 ? (
          <div className="table-empty">
            <Activity size={32} className="text-muted" />
            <p>No telemetry logs recorded matching your filters.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="monitoring-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Prompt Preview</th>
                  <th>Model Used</th>
                  <th>Tier</th>
                  <th>Intent</th>
                  <th>Tokens (In/Out)</th>
                  <th>Total Cost</th>
                  <th>Duration</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const d = new Date(log.timestamp);
                  const isValid = !isNaN(d.getTime());
                  const datePart = isValid
                    ? d.toLocaleDateString([], {
                        year: 'numeric',
                        month: 'short',
                        day: '2-digit',
                      })
                    : log.timestamp;
                  const timePart = isValid
                    ? d.toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })
                    : '';

                  return (
                    <tr key={log.call_id}>
                      <td className="cell-timestamp" title={log.timestamp}>
                        <div className="timestamp-wrapper">
                          <span className="timestamp-date">{datePart}</span>
                          <span className="timestamp-time">{timePart}</span>
                        </div>
                      </td>
                      <td className="cell-prompt" title={log.prompt_preview}>
                        {log.prompt_preview || '—'}
                      </td>
                      <td>
                        <span className="model-chip">
                          <Cpu size={12} className="chip-icon" />
                          {log.model_name}
                        </span>
                      </td>
                      <td>
                        {log.complexity_tier ? (
                          <span className={`tier-chip tier-${log.complexity_tier}`}>
                            <Sparkles size={11} className="chip-icon" />
                            {log.complexity_tier.replace('_', ' ').toUpperCase()}
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td>
                        {log.intent === 'open_domain' ? (
                          <span className="intent-chip open-domain">
                            <Globe size={11} className="chip-icon" /> Open
                          </span>
                        ) : log.intent === 'graph_rag' ? (
                          <span className="intent-chip graph-rag">
                            <Network size={11} className="chip-icon" /> Graph
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="cell-tokens">
                        {log.input_tokens + log.output_tokens > 0 ? (
                          <span>
                            {log.input_tokens} / {log.output_tokens}
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="cell-cost">{formatCost(log.total_cost_usd)}</td>
                      <td className="cell-duration">{Math.round(log.duration_ms)}ms</td>
                      <td>
                        {log.status === 'fallback' ? (
                          <span className="status-chip fallback" title={log.cascade_reason || 'Fallback used'}>
                            <ArrowRightLeft size={11} className="chip-icon" /> Fallback
                          </span>
                        ) : log.status === 'error' ? (
                          <span className="status-chip error">
                            <AlertTriangle size={11} className="chip-icon" /> Error
                          </span>
                        ) : (
                          <span className="status-chip success">
                            <CheckCircle2 size={11} className="chip-icon" /> Success
                          </span>
                        )}
                      </td>
                      <td>
                        <button
                          className="btn-inspect"
                          onClick={() => setSelectedLog(log)}
                          title="Inspect Telemetry Details"
                        >
                          <Eye size={13} className="chip-icon" /> Inspect
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Inspect Log Modal */}
      {selectedLog && (
        <div className="modal-backdrop" onClick={() => setSelectedLog(null)}>
          <div className="modal-content glass-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-wrap">
                <Sparkles size={18} className="text-primary" />
                <h3>Telemetry Audit Inspector</h3>
              </div>
              <button className="btn icon-btn" onClick={() => setSelectedLog(null)}>
                <X size={18} />
              </button>
            </div>

            <div className="modal-body">
              <div className="inspect-grid">
                <div className="inspect-item">
                  <span className="inspect-label">Call ID</span>
                  <span className="inspect-value monospace">{selectedLog.call_id}</span>
                </div>
                <div className="inspect-item">
                  <span className="inspect-label">Session ID</span>
                  <span className="inspect-value monospace">{selectedLog.session_id || '—'}</span>
                </div>
                <div className="inspect-item">
                  <span className="inspect-label">Timestamp</span>
                  <span className="inspect-value">{new Date(selectedLog.timestamp).toLocaleString()}</span>
                </div>
                <div className="inspect-item">
                  <span className="inspect-label">Model & Provider</span>
                  <span className="inspect-value">{selectedLog.model_name} ({selectedLog.provider})</span>
                </div>
                <div className="inspect-item">
                  <span className="inspect-label">Smart Routed</span>
                  <span className="inspect-value">{selectedLog.is_smart_routed ? 'Yes (AI Economics)' : 'No (Explicit Selection)'}</span>
                </div>
                <div className="inspect-item">
                  <span className="inspect-label">Tier & Intent</span>
                  <span className="inspect-value">{selectedLog.complexity_tier || 'N/A'} • {selectedLog.intent || 'N/A'}</span>
                </div>
                <div className="inspect-item">
                  <span className="inspect-label">Input Tokens</span>
                  <span className="inspect-value">{formatTokens(selectedLog.input_tokens)} ({formatCost(selectedLog.input_cost_usd)})</span>
                </div>
                <div className="inspect-item">
                  <span className="inspect-label">Output Tokens</span>
                  <span className="inspect-value">{formatTokens(selectedLog.output_tokens)} ({formatCost(selectedLog.output_cost_usd)})</span>
                </div>
                <div className="inspect-item">
                  <span className="inspect-label">Total Cost</span>
                  <span className="inspect-value highlight-cost">{formatCost(selectedLog.total_cost_usd)}</span>
                </div>
                <div className="inspect-item">
                  <span className="inspect-label">Duration</span>
                  <span className="inspect-value">{selectedLog.duration_ms} ms</span>
                </div>
              </div>

              {selectedLog.routing_reason && (
                <div className="inspect-block">
                  <span className="inspect-label">Routing Decision Rationale</span>
                  <div className="inspect-text-block">{selectedLog.routing_reason}</div>
                </div>
              )}

              {selectedLog.cascade_reason && (
                <div className="inspect-block">
                  <span className="inspect-label">Graceful Cascade Justification</span>
                  <div className="inspect-text-block">{selectedLog.cascade_reason}</div>
                </div>
              )}

              <div className="inspect-block">
                <span className="inspect-label">Prompt Content</span>
                <div className="inspect-text-block">{selectedLog.prompt_preview || 'No prompt content recorded.'}</div>
              </div>

              {selectedLog.tools_called && selectedLog.tools_called.length > 0 && (
                <div className="inspect-block">
                  <span className="inspect-label">Tools Executed ({selectedLog.tools_called.length})</span>
                  <div className="tools-chip-list">
                    {selectedLog.tools_called.map((tool, i) => (
                      <span key={i} className="tool-chip">
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
