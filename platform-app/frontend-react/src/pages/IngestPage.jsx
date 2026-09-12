import { useState } from 'react';
import { ingestFile } from '../api/client';
import './IngestPage.css';

export default function IngestPage() {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [chunkSize, setChunkSize] = useState(512);
  const [overlap, setOverlap] = useState(64);

  const handleDrop = (e) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  };

  const handleFileSelect = (e) => {
    const f = e.target.files[0];
    if (f) setFile(f);
  };

  const handleIngest = async () => {
    if (!file) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await ingestFile(file);
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ingest-page">
      <div className="page-header">
        <h2 className="gradient-text">Data Ingestion</h2>
        <p>Upload files to build and expand your knowledge graph.</p>
      </div>

      <div className="ingest-grid">
        <div className="ingest-main">
          <div
            className={`drop-zone glass-card ${dragging ? 'dragging' : ''}`}
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => document.getElementById('file-input').click()}
          >
            <input id="file-input" type="file" accept=".pdf,.txt,.md,.csv,.json,.docx" onChange={handleFileSelect} hidden />
            <div className="drop-zone-icon">{dragging ? '📥' : '📄'}</div>
            <h3 className="drop-zone-title">
              {dragging ? 'Drop it here!' : 'Drag & drop or click to upload'}
            </h3>
            <p className="drop-zone-subtitle">PDF · TXT · Markdown · CSV · JSON · DOCX</p>
          </div>

          {file && (
            <div className="file-info glass-card">
              <span className="file-info-icon">📎</span>
              <div className="file-info-text">
                <strong>{file.name}</strong>
                <span>{(file.size / 1024).toFixed(1)} KB</span>
              </div>
              <button className="btn" onClick={() => { setFile(null); setResult(null); setError(null); }}>✕</button>
            </div>
          )}

          {file && !loading && !result && (
            <button className="btn-primary ingest-btn" onClick={handleIngest}>
              ⚡ Ingest File
            </button>
          )}

          {loading && (
            <div className="ingest-loading glass-card">
              <div className="spinner" />
              <span>Processing {file?.name}...</span>
            </div>
          )}

          {error && (
            <div className="ingest-error glass-card">
              <span>❌</span> <span>{error}</span>
            </div>
          )}

          {result && (
            <div className="ingest-result">
              <div className="ingest-result-header glass-card">
                <span>✅</span> <strong>Ingestion Complete!</strong>
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

        <div className="ingest-sidebar">
          <div className="glass-card ingest-settings">
            <h4 className="settings-title">⚙️ Settings</h4>
            <div className="setting-group">
              <label>Chunk Size <span className="setting-value">{chunkSize}</span></label>
              <input type="range" min="128" max="1024" step="64" value={chunkSize} onChange={e => setChunkSize(+e.target.value)} />
            </div>
            <div className="setting-group">
              <label>Overlap <span className="setting-value">{overlap}</span></label>
              <input type="range" min="0" max="256" step="16" value={overlap} onChange={e => setOverlap(+e.target.value)} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
