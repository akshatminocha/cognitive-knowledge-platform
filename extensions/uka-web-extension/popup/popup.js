/**
 * UKA Knowledge Clipper — Popup Controller
 */

import { packageWebPageToUka } from '../lib/uka-packager.js';

let currentClipData = null;
let currentTab = null;

// DOM Elements
const elTitle = document.getElementById('page-title');
const elUrl = document.getElementById('page-url');
const elStatWords = document.getElementById('stat-words');
const elStatEntities = document.getElementById('stat-entities');
const elStatMedia = document.getElementById('stat-media');
const elDomainSelect = document.getElementById('domain-select');
const elBtnDownload = document.getElementById('btn-download-uka');
const elBtnSync = document.getElementById('btn-sync-platform');
const elBtnSidepanel = document.getElementById('btn-open-sidepanel');
const elBtnSettings = document.getElementById('btn-settings');
const elStatusBox = document.getElementById('status-box');
const elStatusTitle = document.getElementById('status-title');
const elStatusDesc = document.getElementById('status-desc');
const elBackendLabel = document.getElementById('backend-label');

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', async () => {
  await loadBackendConfig();
  await inspectActiveTab();
  wireEventListeners();
});

async function loadBackendConfig() {
  try {
    const { ckpBackendUrl = 'http://localhost:8000', defaultDomain = 'healthtech' } =
      await chrome.storage.local.get(['ckpBackendUrl', 'defaultDomain']);

    if (elBackendLabel) {
      const urlObj = new URL(ckpBackendUrl);
      elBackendLabel.textContent = `CKP: ${urlObj.host}`;
    }
    if (elDomainSelect && defaultDomain) {
      elDomainSelect.value = defaultDomain;
    }
  } catch (err) {
    console.warn('[Popup] Could not load backend config:', err);
  }
}

async function inspectActiveTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    currentTab = tab;

    if (!tab || !tab.id) {
      showStatus('error', 'Tab Unavailable', 'Could not access the active browser tab.');
      disableActions(true);
      return;
    }

    if (tab.url?.startsWith('chrome://') || tab.url?.startsWith('edge://') || tab.url?.startsWith('about:')) {
      elTitle.textContent = 'System Page';
      elUrl.textContent = tab.url;
      showStatus('error', 'Restricted URL', 'Browser internal pages cannot be clipped into UKA artifacts.');
      disableActions(true);
      return;
    }

    elTitle.textContent = tab.title || 'Untitled Page';
    elUrl.textContent = tab.url || '--';

    // Inject content script if necessary and extract content
    let response;
    try {
      response = await chrome.tabs.sendMessage(tab.id, { action: 'EXTRACT_PAGE_CONTENT' });
    } catch {
      // Content script not yet present, inject dynamically
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content/content-script.js'],
      });
      response = await chrome.tabs.sendMessage(tab.id, { action: 'EXTRACT_PAGE_CONTENT' });
    }

    if (response?.success && response.data) {
      currentClipData = response.data;
      elStatWords.textContent = (response.data.wordCount || 0).toLocaleString();
      elStatEntities.textContent = (response.data.entities?.length || 0).toLocaleString();
      const mediaCount = (response.data.images?.length || 0) + (response.data.tables?.length || 0);
      elStatMedia.textContent = mediaCount.toLocaleString();
      disableActions(false);
    } else {
      throw new Error(response?.error || 'Content extraction failed');
    }
  } catch (err) {
    console.error('[Popup] Tab inspection error:', err);
    showStatus('error', 'Extraction Failed', err.message || 'Could not parse web page DOM.');
    disableActions(true);
  }
}

function wireEventListeners() {
  elBtnDownload.addEventListener('click', handleDownloadUka);
  elBtnSync.addEventListener('click', handleSyncPlatform);

  elBtnSidepanel.addEventListener('click', openSidePanel);
  elBtnSettings.addEventListener('click', openSidePanel);
}

async function handleDownloadUka() {
  if (!currentClipData) return;

  try {
    disableActions(true);
    showStatus('loading', 'Packaging UKA...', 'Generating subgraph, embeddings layout, and SHA-256 catalog.');

    currentClipData.schemaDomain = elDomainSelect.value;
    const { blob, bundleId } = await packageWebPageToUka(currentClipData);

    // Convert blob to Data URL for Chrome downloads API
    const dataUrl = await blobToDataUrl(blob);

    const filename = `${sanitizeFilename(currentClipData.title || bundleId)}.uka`;

    const downloadRes = await chrome.runtime.sendMessage({
      action: 'DOWNLOAD_UKA_FILE',
      dataUrl,
      filename,
    });

    if (downloadRes?.success) {
      showStatus(
        'success',
        'Artifact Saved!',
        `Saved as ${filename} (ID: ${bundleId.slice(0, 12)}...). 100% SHA-256 verified.`
      );
    } else {
      throw new Error(downloadRes?.error || 'Download failed');
    }
  } catch (err) {
    console.error('[Popup] Download UKA error:', err);
    showStatus('error', 'Packaging Error', err.message);
  } finally {
    disableActions(false);
  }
}

async function handleSyncPlatform() {
  if (!currentClipData) return;

  try {
    disableActions(true);
    showStatus('loading', 'Synthesizing Bundle...', 'Packaging artifact and connecting to CKP backend...');

    currentClipData.schemaDomain = elDomainSelect.value;
    const { blob, bundleId } = await packageWebPageToUka(currentClipData);

    const { ckpBackendUrl = 'http://localhost:8000' } = await chrome.storage.local.get('ckpBackendUrl');

    showStatus('loading', 'Uploading to CKP Platform...', `Posting to ${ckpBackendUrl}/api/v2/uka/import`);

    const formData = new FormData();
    const filename = `${sanitizeFilename(currentClipData.title || bundleId)}.uka`;
    formData.append('file', blob, filename);
    formData.append('session_id', bundleId);

    const response = await fetch(`${ckpBackendUrl}/api/v2/uka/import`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errText}`);
    }

    const result = await response.json();
    const nodes = result.nodes_restored ?? 0;
    const edges = result.edges_restored ?? 0;
    const vectors = result.vectors_restored ?? 0;

    showStatus(
      'success',
      'Synced to Platform!',
      `Rehydrated ${nodes} nodes, ${edges} edges, and ${vectors} vectors into Neo4j & Qdrant.`
    );
  } catch (err) {
    console.error('[Popup] Sync Platform error:', err);
    showStatus(
      'error',
      'Sync Failed',
      `Could not upload to CKP: ${err.message}. Ensure backend is running.`
    );
  } finally {
    disableActions(false);
  }
}

async function openSidePanel() {
  try {
    await chrome.runtime.sendMessage({ action: 'OPEN_SIDE_PANEL' });
    window.close(); // Close popup once side panel opens
  } catch (err) {
    console.error('[Popup] Open side panel error:', err);
  }
}

function showStatus(type, title, desc) {
  elStatusBox.className = `status-box ${type}`;
  elStatusTitle.textContent = title;
  elStatusDesc.textContent = desc;
}

function disableActions(disabled) {
  elBtnDownload.disabled = disabled;
  elBtnSync.disabled = disabled;
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

