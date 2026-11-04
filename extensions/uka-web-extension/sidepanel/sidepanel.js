/**
 * UKA Studio & Inspector — Side Panel Controller (Manifest V3)
 */

import { packageWebPageToUka, inspectUkaBundle } from '../lib/uka-packager.js';

let activeClipData = null;

// Tab elements
const tabButtons = document.querySelectorAll('.nav-tab');
const tabPanes = document.querySelectorAll('.tab-pane');

// Clipper elements
const elClipTitle = document.getElementById('clip-title');
const elClipUrl = document.getElementById('clip-url');
const elClipStatWords = document.getElementById('clip-stat-words');
const elClipStatEntities = document.getElementById('clip-stat-entities');
const elClipStatTables = document.getElementById('clip-stat-tables');
const elClipStatImages = document.getElementById('clip-stat-images');
const elClipDomain = document.getElementById('clip-domain');
const elEntitiesContainer = document.getElementById('entities-container');
const elEntityCountBadge = document.getElementById('entity-count-badge');
const elClipPreviewText = document.getElementById('clip-preview-text');
const elBtnRefreshClip = document.getElementById('btn-refresh-clip');
const elBtnSideDownload = document.getElementById('btn-sidepanel-download');
const elBtnSideSync = document.getElementById('btn-sidepanel-sync');
const elClipStatusMessage = document.getElementById('clip-status-message');

// Inspector elements
const elDropZone = document.getElementById('drop-zone');
const elFileInput = document.getElementById('file-input');
const elInspectResults = document.getElementById('inspect-results');
const elIntegrityBanner = document.getElementById('integrity-banner');
const elIntegrityIcon = document.getElementById('integrity-icon');
const elIntegrityTitle = document.getElementById('integrity-title');
const elIntegrityDesc = document.getElementById('integrity-desc');
const elInsArtifactId = document.getElementById('ins-artifact-id');
const elInsTitle = document.getElementById('ins-title');
const elInsDomain = document.getElementById('ins-domain');
const elInsCreated = document.getElementById('ins-created');
const elInsSize = document.getElementById('ins-size');
const elInsNodes = document.getElementById('ins-nodes-count');
const elInsEdges = document.getElementById('ins-edges-count');
const elInsChunks = document.getElementById('ins-chunks-count');
const elFileList = document.getElementById('file-verification-list');
const elInsContextView = document.getElementById('ins-context-view');

// Settings elements
const elCfgBackendUrl = document.getElementById('cfg-backend-url');
const elCfgPasscode = document.getElementById('cfg-passcode');
const elCfgDefaultDomain = document.getElementById('cfg-default-domain');
const elCfgBundlesCount = document.getElementById('cfg-bundles-count');
const elBtnTestConn = document.getElementById('btn-test-connection');
const elConnStatus = document.getElementById('connection-status');
const elBtnSaveSettings = document.getElementById('btn-save-settings');

document.addEventListener('DOMContentLoaded', async () => {
  setupTabs();
  setupClipper();
  setupInspector();
  await setupSettings();
  await loadActivePageContent();
});

/* ========================================================================= */
/* Tab Switching                                                             */
/* ========================================================================= */
function setupTabs() {
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab');
      tabButtons.forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      document.getElementById(targetId)?.classList.add('active');
    });
  });
}

/* ========================================================================= */
/* Clipper Controller                                                        */
/* ========================================================================= */
function setupClipper() {
  elBtnRefreshClip.addEventListener('click', loadActivePageContent);
  elBtnSideDownload.addEventListener('click', handleClipperDownload);
  elBtnSideSync.addEventListener('click', handleClipperSync);
}

async function loadActivePageContent() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) return;

    if (tab.url?.startsWith('chrome://') || tab.url?.startsWith('about:')) {
      elClipTitle.textContent = 'Restricted Internal Browser Page';
      elClipUrl.textContent = tab.url;
      elClipUrl.removeAttribute('href');
      return;
    }

    elClipTitle.textContent = tab.title || 'Loading active page...';
    elClipUrl.textContent = tab.url || '--';
    elClipUrl.href = tab.url || '#';

    let response;
    try {
      response = await chrome.tabs.sendMessage(tab.id, { action: 'EXTRACT_PAGE_CONTENT' });
    } catch {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content/content-script.js'],
      });
      response = await chrome.tabs.sendMessage(tab.id, { action: 'EXTRACT_PAGE_CONTENT' });
    }

    if (response?.success && response.data) {
      activeClipData = response.data;
      renderClippedPage(response.data);
    }
  } catch (err) {
    console.warn('[SidePanel] Content extraction note:', err.message);
  }
}

function renderClippedPage(data) {
  elClipTitle.textContent = data.title || 'Untitled Web Document';
  elClipUrl.textContent = data.url || '--';
  elClipUrl.href = data.url || '#';

  elClipStatWords.textContent = (data.wordCount || 0).toLocaleString();
  elClipStatEntities.textContent = (data.entities?.length || 0).toLocaleString();
  elClipStatTables.textContent = (data.tables?.length || 0).toLocaleString();
  elClipStatImages.textContent = (data.images?.length || 0).toLocaleString();

  // Render Entity Tags
  elEntitiesContainer.innerHTML = '';
  if (Array.isArray(data.entities) && data.entities.length > 0) {
    elEntityCountBadge.textContent = `${data.entities.length} concepts`;
    data.entities.forEach(ent => {
      const tag = document.createElement('span');
      tag.className = 'entity-tag';
      tag.innerHTML = `
        <span class="tag-label">${escapeHtml(ent.label || 'Concept')}</span>
        <span>${escapeHtml(ent.name)}</span>
      `;
      elEntitiesContainer.appendChild(tag);
    });
  } else {
    elEntityCountBadge.textContent = '0 concepts';
    elEntitiesContainer.innerHTML = '<span class="empty-text">No domain entities detected.</span>';
  }

  // Render Markdown Preview
  const preview = `# ${data.title || 'Untitled Document'}\n\n> Source: ${data.url}\n\n## 1. Executive Summary\n${data.content?.slice(0, 800) || ''}...\n\n---\n*Clipped via UKA Web Clipper*`;
  elClipPreviewText.textContent = preview;
}

async function handleClipperDownload() {
  if (!activeClipData) return;

  try {
    showClipperStatus('info', 'Synthesizing UKA bundle with SHA-256 catalog...');
    activeClipData.schemaDomain = elClipDomain.value;

    const { blob, bundleId } = await packageWebPageToUka(activeClipData);
    const dataUrl = await blobToDataUrl(blob);
    const filename = `${sanitizeFilename(activeClipData.title || bundleId)}.uka`;

    const res = await chrome.runtime.sendMessage({
      action: 'DOWNLOAD_UKA_FILE',
      dataUrl,
      filename,
    });

    if (res?.success) {
      showClipperStatus('success', `Artifact downloaded successfully: ${filename}`);
    } else {
      throw new Error(res?.error || 'Download failed');
    }
  } catch (err) {
    showClipperStatus('error', `Download error: ${err.message}`);
  }
}

async function handleClipperSync() {
  if (!activeClipData) return;

  try {
    showClipperStatus('info', 'Packaging artifact and uploading to CKP platform...');
    activeClipData.schemaDomain = elClipDomain.value;

    const { blob, bundleId } = await packageWebPageToUka(activeClipData);
    const { ckpBackendUrl = 'http://localhost:8000' } = await chrome.storage.local.get('ckpBackendUrl');

    const formData = new FormData();
    const filename = `${sanitizeFilename(activeClipData.title || bundleId)}.uka`;
    formData.append('file', blob, filename);
    formData.append('session_id', bundleId);

    const response = await fetch(`${ckpBackendUrl}/api/v2/uka/import`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }

    const result = await response.json();
    showClipperStatus(
      'success',
      `Rehydrated into CKP! (${result.nodes_restored ?? 0} nodes, ${result.edges_restored ?? 0} edges, ${result.vectors_restored ?? 0} chunks).`
    );
  } catch (err) {
    showClipperStatus('error', `Sync failed: ${err.message}. Ensure backend is running.`);
  }
}

function showClipperStatus(type, msg) {
  elClipStatusMessage.className = `status-banner ${type}`;
  elClipStatusMessage.textContent = msg;
}

/* ========================================================================= */
/* Inspector Controller                                                      */
/* ========================================================================= */
function setupInspector() {
  elDropZone.addEventListener('click', () => elFileInput.click());

  elFileInput.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    if (file) inspectFile(file);
  });

  elDropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    elDropZone.classList.add('dragover');
  });

  elDropZone.addEventListener('dragleave', () => {
    elDropZone.classList.remove('dragover');
  });

  elDropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    elDropZone.classList.remove('dragover');
    const file = e.dataTransfer.files?.[0];
    if (file) inspectFile(file);
  });
}

async function inspectFile(file) {
  try {
    const arrayBuffer = await file.arrayBuffer();
    const inspection = await inspectUkaBundle(arrayBuffer);
    renderInspectionResults(inspection, file.name);
  } catch (err) {
    console.error('[SidePanel] Inspection failed:', err);
    alert(`Failed to inspect UKA artifact: ${err.message}`);
  }
}

function renderInspectionResults(data, filename) {
  elInspectResults.classList.remove('hidden');

  // 1. Integrity Banner
  if (data.integrityPassed) {
    elIntegrityBanner.className = 'integrity-banner valid';
    elIntegrityIcon.textContent = '✓';
    elIntegrityTitle.textContent = 'Cryptographic Integrity Verified';
    elIntegrityDesc.textContent = `All ${data.verificationResults.length} files matched SHA-256 checksums in manifest.json.`;
  } else {
    elIntegrityBanner.className = 'integrity-banner invalid';
    elIntegrityIcon.textContent = '✕';
    elIntegrityTitle.textContent = 'Integrity Compromised / Tampered';
    elIntegrityDesc.textContent = 'One or more files have checksum mismatches or are missing.';
  }

  // 2. Manifest Properties
  elInsArtifactId.textContent = data.manifest.artifact_id || data.manifest.bundle_id || 'N/A';
  elInsTitle.textContent = data.manifest.title || filename;
  elInsDomain.textContent = data.manifest.domain || 'N/A';
  elInsCreated.textContent = data.manifest.created_at ? new Date(data.manifest.created_at).toLocaleString() : 'N/A';
  elInsSize.textContent = formatBytes(data.totalSize);

  // 3. Stats
  elInsNodes.textContent = (data.nodesCount || 0).toLocaleString();
  elInsEdges.textContent = (data.edgesCount || 0).toLocaleString();
  elInsChunks.textContent = (data.chunksCount || 0).toLocaleString();

  // 4. File Verification Table
  elFileList.innerHTML = '';
  data.verificationResults.forEach(item => {
    const row = document.createElement('div');
    row.className = 'file-item';
    const statusClass = item.status === 'VERIFIED' ? 'status-verified' : (item.status === 'TAMPERED' ? 'status-tampered' : 'status-missing');
    row.innerHTML = `
      <span class="file-name">${escapeHtml(item.path)}</span>
      <span class="file-status-pill ${statusClass}">${item.status}</span>
    `;
    elFileList.appendChild(row);
  });

  // 5. Context View
  elInsContextView.textContent = data.contextMd || '(No context.md found in bundle)';
}

/* ========================================================================= */
/* Settings Controller                                                       */
/* ========================================================================= */
async function setupSettings() {
  const defaults = {
    ckpBackendUrl: 'http://localhost:8000',
    adminPasscode: 'ckp-admin-2026',
    defaultDomain: 'healthtech',
    savedBundlesCount: 0,
  };

  const stored = await chrome.storage.local.get(Object.keys(defaults));
  elCfgBackendUrl.value = stored.ckpBackendUrl || defaults.ckpBackendUrl;
  elCfgPasscode.value = stored.adminPasscode || defaults.adminPasscode;
  elCfgDefaultDomain.value = stored.defaultDomain || defaults.defaultDomain;
  elCfgBundlesCount.textContent = stored.savedBundlesCount || '0';

  elBtnSaveSettings.addEventListener('click', async () => {
    await chrome.storage.local.set({
      ckpBackendUrl: elCfgBackendUrl.value.trim().replace(/\/+$/, ''),
      adminPasscode: elCfgPasscode.value.trim(),
      defaultDomain: elCfgDefaultDomain.value,
    });
    alert('Settings saved successfully.');
  });

  elBtnTestConn.addEventListener('click', async () => {
    const url = elCfgBackendUrl.value.trim().replace(/\/+$/, '');
    elConnStatus.textContent = 'Pinging backend...';
    elConnStatus.style.color = '#38bdf8';

    const start = performance.now();
    try {
      const res = await fetch(`${url}/docs`, { method: 'GET', mode: 'no-cors' });
      const latency = Math.round(performance.now() - start);
      elConnStatus.textContent = `Connected! (${latency}ms latency)`;
      elConnStatus.style.color = '#10b981';
    } catch (err) {
      elConnStatus.textContent = `Connection failed: ${err.message}`;
      elConnStatus.style.color = '#f43f5e';
    }
  });
}

/* ========================================================================= */
/* Helpers                                                                   */
/* ========================================================================= */
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function sanitizeFilename(title) {
  return (title || 'bundle')
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, '_')
    .replace(/_+/g, '_')
    .slice(0, 40);
}

function escapeHtml(str) {
  return (str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

