import { useState } from 'react';
import { Download, FileText, Paperclip, X, Loader2, CheckCircle2, AlertCircle, Settings, Presentation, Image, Headphones, Video, Sparkles } from 'lucide-react';
import { ingestFile } from '../api/client';
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
      // Pass the state values for chunk size and overlap
      const res = await ingestFile(file, 'healthtech', chunkSize, overlap);
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fileCat = file ? getFileCategory(file.name) : null;
  const CatIcon = fileCat?.icon || FileText;

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
                  <span className="file-category-badge" style={{ borderColor: fileCat.color + '55', color: fileCat.color, background: fileCat.color + '18' }}>
                    <CatIcon size={11} className="badge-icon" /> {fileCat.label}
                  </span>
                </div>
                <span>{(file.size / 1024).toFixed(1)} KB</span>
              </div>
              <button className="btn" onClick={() => { setFile(null); setResult(null); setError(null); }}>
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

        <div className="ingest-sidebar">
          <div className="glass-card ingest-settings">
            <h4 className="settings-title flex-center gap-2"><Settings size={18} /> Settings</h4>
            
            <div className="setting-group">
              <label>Chunk Size</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input 
                  type="range" 
                  min="50" 
                  max="2000" 
                  step="10" 
                  value={chunkSize} 
                  onChange={e => setChunkSize(+e.target.value)} 
                  style={{ flex: 1 }}
                />
                <input 
                  type="number" 
                  value={chunkSize} 
                  onChange={e => setChunkSize(e.target.value === '' ? '' : Number(e.target.value))}
                  style={{ width: '60px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border)', background: 'rgba(0,0,0,0.2)', color: 'white' }}
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
                  onChange={e => setOverlap(+e.target.value)} 
                  style={{ flex: 1 }}
                />
                <input 
                  type="number" 
                  value={overlap} 
                  onChange={e => setOverlap(e.target.value === '' ? '' : Number(e.target.value))}
                  style={{ width: '60px', padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border)', background: 'rgba(0,0,0,0.2)', color: 'white' }}
                />
              </div>
            </div>
            
          </div>
        </div>
      </div>
    </div>
  );
}
