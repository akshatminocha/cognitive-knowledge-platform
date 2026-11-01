import { useState, useEffect, useRef } from 'react';
import {
  Download,
  FileText,
  X,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Settings,
  Presentation,
  Image,
  Headphones,
  Video,
  Sparkles,
  Bot,
  Play,
  Pause,
  RefreshCw,
  FolderSync,
  Cloud,
  Server,
  Zap,
  Activity,
} from 'lucide-react';
import {
  ingestFile,
  getCrawlerStatus,
  toggleCrawler,
  getCrawlerLogs,
  scanCrawlerNow,
} from '../api/client';
import './IngestPage.css';

const getFileCategory = (filename) => {
  if (!filename) return { label: 'Document', icon: FileText, color: '#a855f7' };
  const ext = filename.split('.').pop().toLowerCase();
  if (['pptx'].includes(ext)) return { label: 'Presentation (Slides & Tables)', icon: Presentation, color: '#f59e0b' };
  if (['png', 'jpg', 'jpeg'].includes(ext)) return { label: 'Vision Document (Diagrams & Layout)', icon: Image, color: '#38bdf8' };
  if (['mp3', 'wav'].includes(ext)) return { label: 'Audio Stream (Speaker Diarized)', icon: Headphones, color: '#ec4899' };
  if (['mp4'].includes(ext)) return { label: 'Video Stream (Scene Chronology)', icon: Video, color: '#10b981' };
  return { label: 'Document', icon: FileText, color: '#a855f7' };
};

const getDomainBadge = (domain) => {
  switch (domain?.toLowerCase()) {
    case 'healthtech':
      return { label: 'HealthTech', bg: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: 'rgba(56, 189, 248, 0.3)' };
    case 'fintech':
      return { label: 'FinTech', bg: 'rgba(16, 185, 129, 0.15)', color: '#10b981', border: 'rgba(16, 185, 129, 0.3)' };
    case 'edtech':
      return { label: 'EdTech', bg: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b', border: 'rgba(245, 158, 11, 0.3)' };
    case 'enterprise_ops':
      return { label: 'Enterprise Ops', bg: 'rgba(168, 85, 247, 0.15)', color: '#a855f7', border: 'rgba(168, 85, 247, 0.3)' };
    default:
      return { label: domain || 'General', bg: 'rgba(255, 255, 255, 0.08)', color: '#94a3b8', border: 'rgba(255, 255, 255, 0.15)' };
  }
};

export default function IngestPage() {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [chunkSize, setChunkSize] = useState(512);
  const [overlap, setOverlap] = useState(64);

  // Autonomous Crawler state
  const [crawlerStatus, setCrawlerStatus] = useState(null);
  const [crawlerLogs, setCrawlerLogs] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [toggling, setToggling] = useState(false);

  const fetchCrawlerData = async () => {
    try {
      const [statusRes, logsRes] = await Promise.all([
        getCrawlerStatus(),
        getCrawlerLogs(30),
      ]);
      setCrawlerStatus(statusRes);
      setCrawlerLogs(logsRes.logs || []);
    } catch (err) {
      console.warn('Failed to fetch crawler data:', err);
    }
  };

  useEffect(() => {
    fetchCrawlerData();
    const interval = setInterval(fetchCrawlerData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  };

  const handleFileSelect = (e) => {
    const f = e.target.files[0];
    if (f) setFile(f);
  };

  const handleIngest = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await ingestFile(file, 'healthtech', chunkSize, overlap);
      setResult(res);
      fetchCrawlerData();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleCrawler = async () => {
    setToggling(true);
    try {
      const nextAction = crawlerStatus?.status === 'running' ? 'pause' : 'resume';
      const updated = await toggleCrawler(nextAction);
      setCrawlerStatus(updated);
    } catch (err) {
      console.error('Failed to toggle crawler:', err);
    } finally {
      setToggling(false);
    }
  };

  const handleScanNow = async () => {
    setScanning(true);
    try {
      await scanCrawlerNow();
      await fetchCrawlerData();
    } catch (err) {
      console.error('Scan now error:', err);
    } finally {
      setScanning(false);
    }
  };

  const fileCat = file ? getFileCategory(file.name) : null;
  const CatIcon = fileCat?.icon || FileText;

  const isCrawlerRunning = crawlerStatus?.status === 'running';
  const isCrawlerPaused = crawlerStatus?.status === 'paused';

  return (
    <div className="ingest-page">
      <div className="page-header ingest-header-row">
        <div>
          <h2 className="gradient-text">Data Ingestion & Autonomous Crawler</h2>
          <p>Manual drop-in & 24/7 background agents expanding your knowledge graph.</p>
        </div>

        <div className="crawler-status-pill-wrap">
          <div className={`crawler-pill glass-card ${isCrawlerRunning ? 'active' : isCrawlerPaused ? 'paused' : 'offline'}`}>
            <span className="crawler-pulse-dot" />
            <Bot size={15} className="crawler-bot-icon" />
            <span className="crawler-pill-text">
              {isCrawlerRunning
                ? 'Autonomous Crawler: Active'
                : isCrawlerPaused
                ? 'Autonomous Crawler: Paused'
                : 'Autonomous Crawler: Idle'}
            </span>
          </div>
        </div>
      </div>

      <div className="ingest-grid">
        <div className="ingest-main">
          {/* Drop Zone */}
          <div
            className={`drop-zone glass-card ${dragging ? 'dragging' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => document.getElementById('file-input').click()}
          >
            <input
              id="file-input"
              type="file"
              accept=".pdf,.txt,.md,.csv,.json,.docx,.pptx,.png,.jpg,.jpeg,.mp3,.wav,.mp4"
              onChange={handleFileSelect}
              hidden
            />
            <div className="drop-zone-icon">
              {dragging ? <Download size={48} /> : <FileText size={48} />}
            </div>
            <h3 className="drop-zone-title">
              {dragging ? 'Drop it here!' : 'Drag & drop or click to upload'}
            </h3>
            <p className="drop-zone-subtitle">Multimodal intake: Documents · Slides · Vision · Audio · Video</p>
            <div className="format-pills-row">
              <span className="format-pill"><FileText size={12} className="format-icon" /> Documents</span>
              <span className="format-pill"><Presentation size={12} className="format-icon" /> PPTX</span>
              <span className="format-pill"><Image size={12} className="format-icon" /> Vision</span>
              <span className="format-pill"><Headphones size={12} className="format-icon" /> Audio</span>
              <span className="format-pill"><Video size={12} className="format-icon" /> Video</span>
            </div>
          </div>

          {file && (
            <div className="file-info glass-card">
              <span className="file-info-icon" style={{ color: fileCat.color }}>
                <CatIcon size={22} />
              </span>
              <div className="file-info-text">
                <div className="file-name-row">
                  <strong>{file.name}</strong>
                  <span
                    className="file-category-badge"
                    style={{
                      borderColor: fileCat.color + '55',
                      color: fileCat.color,
                      background: fileCat.color + '18',
                    }}
                  >
                    <CatIcon size={11} className="badge-icon" /> {fileCat.label}
                  </span>
                </div>
                <span>{(file.size / 1024).toFixed(1)} KB</span>
              </div>
              <button
                className="btn"
                onClick={() => {
                  setFile(null);
                  setResult(null);
                  setError(null);
                }}
              >
                <X size={16} />
              </button>
            </div>
          )}

          {file && !loading && !result && (
            <button className="btn-primary ingest-btn" onClick={handleIngest}>
              Ingest File
            </button>
          )}

          {loading && (
            <div className="ingest-loading glass-card flex-center gap-2">
              <Loader2 className="spinner" size={24} />
              <span>Processing {file?.name}...</span>
            </div>
          )}

          {error && (
            <div className="ingest-error glass-card flex-center gap-2">
              <AlertCircle size={24} className="text-error" /> <span>{error}</span>
            </div>
          )}

          {result && (
            <div className="ingest-result">
              <div className="ingest-result-header glass-card flex-center gap-2">
                <CheckCircle2 size={24} className="text-success" /> <strong>Ingestion Complete!</strong>
              </div>
              <div className="ingest-metrics">
                <div className="metric-card glass-card">
                  <span className="metric-value gradient-text">{result.chunks_created || 0}</span>
                  <span className="metric-label">Chunks</span>
                </div>
                <div className="metric-card glass-card">
                  <span className="metric-value gradient-text">{result.entities_extracted || 0}</span>
                  <span className="metric-label">Entities</span>
                </div>
                <div className="metric-card glass-card">
                  <span className="metric-value gradient-text">{result.relationships_extracted || 0}</span>
                  <span className="metric-label">Relations</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar Controls & Crawler Status */}
        <div className="ingest-sidebar">
          {/* Autonomous Crawler Control Box */}
          <div className="glass-card crawler-card">
            <div className="crawler-card-header">
              <div className="crawler-title-group">
                <Bot size={18} className="text-accent" />
                <h4 className="settings-title">Autonomous Crawler</h4>
              </div>
              <span className={`crawler-state-chip ${crawlerStatus?.status || 'stopped'}`}>
                {crawlerStatus?.status?.toUpperCase() || 'STOPPED'}
              </span>
            </div>

            <p className="crawler-desc">
              Continuously indexes incoming files from drop directories, cloud buckets, and SFTP endpoints.
            </p>

            <div className="crawler-connectors-list">
              <div className="connector-pill">
                <FolderSync size={12} /> Local Drop (<code>data/incoming/</code>)
              </div>
              <div className="connector-pill">
                <Cloud size={12} /> Google Cloud Storage (GCS)
              </div>
              <div className="connector-pill">
                <Server size={12} /> SFTP Remote / S3 / Azure
              </div>
            </div>

            <div className="crawler-actions-row">
              <button
                className={`btn crawler-toggle-btn ${isCrawlerRunning ? 'btn-pause' : 'btn-resume'}`}
                onClick={handleToggleCrawler}
                disabled={toggling}
              >
                {toggling ? (
                  <Loader2 size={14} className="spinner" />
                ) : isCrawlerRunning ? (
                  <>
                    <Pause size={14} /> Pause
                  </>
                ) : (
                  <>
                    <Play size={14} /> Resume
                  </>
                )}
              </button>

              <button
                className="btn btn-scan"
                onClick={handleScanNow}
                disabled={scanning}
                title="Force scan drop folders and connectors now"
              >
                <RefreshCw size={14} className={scanning ? 'spinner' : ''} />
                <span>{scanning ? 'Scanning...' : 'Scan Now'}</span>
              </button>
            </div>

            {crawlerStatus?.stats && (
              <div className="crawler-stats-mini">
                <div className="c-stat-item">
                  <span className="c-stat-val">{crawlerStatus.stats.total_crawled || 0}</span>
                  <span className="c-stat-lbl">Crawled</span>
                </div>
                <div className="c-stat-item">
                  <span className="c-stat-val">{crawlerStatus.stats.total_chunks || 0}</span>
                  <span className="c-stat-lbl">Chunks</span>
                </div>
                <div className="c-stat-item">
                  <span className="c-stat-val">{crawlerStatus.stats.total_entities || 0}</span>
                  <span className="c-stat-lbl">Entities</span>
                </div>
              </div>
            )}
          </div>

          {/* Parser Settings */}
          <div className="glass-card ingest-settings">
            <h4 className="settings-title flex-center gap-2">
              <Settings size={18} /> Settings
            </h4>

            <div className="setting-group">
              <label>Chunk Size</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input
                  type="range"
                  min="50"
                  max="2000"
                  step="10"
                  value={chunkSize}
                  onChange={(e) => setChunkSize(+e.target.value)}
                  style={{ flex: 1 }}
                />
                <input
                  type="number"
                  value={chunkSize}
                  onChange={(e) => setChunkSize(e.target.value === '' ? '' : Number(e.target.value))}
                  className="setting-number-box"
                />
              </div>
            </div>

            <div className="setting-group">
              <label>Overlap</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input
                  type="range"
                  min="0"
                  max="500"
                  step="10"
                  value={overlap}
                  onChange={(e) => setOverlap(+e.target.value)}
                  style={{ flex: 1 }}
                />
                <input
                  type="number"
                  value={overlap}
                  onChange={(e) => setOverlap(e.target.value === '' ? '' : Number(e.target.value))}
                  className="setting-number-box"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Live Autonomous Activity Feed */}
      <div className="crawler-feed-section glass-card">
        <div className="feed-header">
          <div className="feed-title-wrap">
            <Activity size={18} className="text-accent" />
            <h3 className="feed-title">Live Autonomous Crawler Feed</h3>
            <span className="feed-count-badge">{crawlerLogs.length} events</span>
          </div>
          <button className="btn feed-refresh-btn" onClick={fetchCrawlerData} title="Refresh activity feed">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        {crawlerLogs.length === 0 ? (
          <div className="feed-empty-state">
            <Bot size={36} className="text-muted" />
            <p>No autonomous events recorded yet.</p>
            <span>
              Drop any document into <code>data/incoming/</code> or invoke <code>POST /api/v2/crawler/webhook</code> to observe proactive background ingestion.
            </span>
          </div>
        ) : (
          <div className="feed-table-wrap">
            <table className="feed-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Source</th>
                  <th>Detected Domain</th>
                  <th>Chunks</th>
                  <th>Entities</th>
                  <th>Status</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {crawlerLogs.map((item) => {
                  const domainInfo = getDomainBadge(item.detected_domain);
                  return (
                    <tr key={item.id} className="feed-row">
                      <td className="feed-file-cell">
                        <FileText size={15} className="feed-file-icon" />
                        <span className="feed-filename" title={item.filename}>
                          {item.filename}
                        </span>
                      </td>
                      <td>
                        <span className="feed-source-chip">
                          {item.source}
                        </span>
                      </td>
                      <td>
                        <span
                          className="feed-domain-badge"
                          style={{
                            background: domainInfo.bg,
                            color: domainInfo.color,
                            borderColor: domainInfo.border,
                          }}
                        >
                          {domainInfo.label}
                        </span>
                      </td>
                      <td className="feed-num-cell">{item.chunks_created || 0}</td>
                      <td className="feed-num-cell">{item.entities_extracted || 0}</td>
                      <td>
                        <span className={`feed-status-badge status-${item.status}`}>
                          {item.status === 'processing' && <Loader2 size={10} className="spinner" />}
                          {item.status}
                        </span>
                      </td>
                      <td className="feed-time-cell">
                        {item.created_at ? new Date(item.created_at).toLocaleTimeString() : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
