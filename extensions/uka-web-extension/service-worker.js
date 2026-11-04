/**
 * UKA Browser Extension — Background Service Worker (Manifest V3).
 * Coordinates context menus, side panel triggers, and background UKA downloads.
 */

// Initialize defaults on install
chrome.runtime.onInstalled.addListener(async () => {
  console.log('[UKA Extension] Service Worker installed');

  // Default configuration in storage
  const defaults = {
    ckpBackendUrl: 'http://localhost:8000',
    adminPasscode: 'ckp-admin-2026',
    defaultDomain: 'healthtech',
    autoSync: false,
    savedBundlesCount: 0,
  };

  const stored = await chrome.storage.local.get(Object.keys(defaults));
  const toSet = {};
  for (const [key, val] of Object.entries(defaults)) {
    if (stored[key] === undefined) toSet[key] = val;
  }
  if (Object.keys(toSet).length > 0) {
    await chrome.storage.local.set(toSet);
  }

  // Create context menu for quick 1-click clipping
  chrome.contextMenus.create({
    id: 'clip-to-uka-action',
    title: 'Clip Page to .UKA Knowledge Bundle',
    contexts: ['page', 'selection'],
  });
});

// Handle Context Menu click
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'clip-to-uka-action' && tab?.id) {
    try {
      // Inject content script if not already present
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content/content-script.js'],
      });

      // Request content extraction
      const response = await chrome.tabs.sendMessage(tab.id, { action: 'EXTRACT_PAGE_CONTENT' });
      if (response?.success && response.data) {
        // Flash badge
        await chrome.action.setBadgeText({ text: 'UKA', tabId: tab.id });
        await chrome.action.setBadgeBackgroundColor({ color: '#7a52f4', tabId: tab.id });

        // Show toast on page
        await chrome.tabs.sendMessage(tab.id, {
          action: 'SHOW_CLIP_NOTIFICATION',
          title: 'Web Page Clipped',
          subtitle: `Extracted ${response.data.wordCount} words & ${response.data.entities.length} entities`,
        });

        // Store last clipped data for popup / sidepanel
        await chrome.storage.local.set({ lastClippedData: response.data });
      }
    } catch (err) {
      console.error('[UKA Extension] Context menu clip failed:', err);
    }
  }
});

// Handle messages from Popup or Side Panel
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'OPEN_SIDE_PANEL') {
    (async () => {
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab?.windowId) {
          await chrome.sidePanel.open({ windowId: tab.windowId });
          sendResponse({ success: true });
        } else {
          sendResponse({ success: false, error: 'No active window found' });
        }
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true; // Keeps channel open for async response
  }

  if (message.action === 'DOWNLOAD_UKA_FILE') {
    (async () => {
      try {
        const downloadId = await chrome.downloads.download({
          url: message.dataUrl,
          filename: message.filename || 'bundle.uka',
          saveAs: true,
        });

        // Increment count in storage
        const { savedBundlesCount = 0 } = await chrome.storage.local.get('savedBundlesCount');
        await chrome.storage.local.set({ savedBundlesCount: savedBundlesCount + 1 });

        sendResponse({ success: true, downloadId });
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true;
  }
});

