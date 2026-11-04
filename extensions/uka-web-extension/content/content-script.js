/**
 * UKA Content Script — High-Fidelity Web Page Distiller & Entity Harvester.
 * Extracts clean structured markdown, tables, images, and entity candidates.
 */

(() => {
  // Prevent duplicate execution
  if (window.__UKA_CONTENT_SCRIPT_LOADED__) return;
  window.__UKA_CONTENT_SCRIPT_LOADED__ = true;

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'EXTRACT_PAGE_CONTENT') {
      try {
        const data = extractPageContent();
        sendResponse({ success: true, data });
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
      return true;
    } else if (message.action === 'SHOW_CLIP_NOTIFICATION') {
      showClipToast(message.title || 'Knowledge Clipped', message.subtitle || 'Saved as .UKA bundle');
      sendResponse({ success: true });
      return true;
    }
  });

  function extractPageContent() {
    const title = getTitle();
    const url = window.location.href;
    const author = getAuthor();
    const publishDate = getPublishDate();
    const metaDescription = getMetaDescription();

    // Clone DOM body to extract content safely without modifying live DOM
    const clone = document.body.cloneNode(true);

    // Remove noise elements
    const selectorsToRemove = [
      'script', 'style', 'noscript', 'iframe', 'svg',
      'nav', 'footer', 'header', '.ad', '.advertisement',
      '#comments', '.comments', '.cookie-banner', '.newsletter-signup'
    ];
    selectorsToRemove.forEach(sel => {
      clone.querySelectorAll(sel).forEach(el => el.remove());
    });

    // Extract Markdown tables from original document
    const tables = [];
    document.querySelectorAll('table').forEach(table => {
      const mdTable = convertHtmlTableToMarkdown(table);
      if (mdTable) tables.push(mdTable);
    });

    // Extract Content Images
    const images = [];
    document.querySelectorAll('article img, main img, .content img, img').forEach(img => {
      const src = img.src;
      const alt = img.alt || '';
      const width = img.naturalWidth || img.width;
      const height = img.naturalHeight || img.height;
      if (src && width > 120 && height > 120 && !src.includes('analytics') && !src.includes('avatar')) {
        images.push({ src, alt, width, height });
      }
    });

    // Convert cleaned content to readable Markdown
    const markdownContent = convertNodeToMarkdown(clone);

    // Heuristic entity harvesting (Capitalized terms, acronyms, drug/disease candidates)
    const entities = harvestCandidateEntities(markdownContent);

    return {
      title,
      url,
      author,
      publishDate,
      metaDescription,
      summary: metaDescription || summarizeText(markdownContent),
      content: markdownContent,
      tables,
      images: images.slice(0, 10),
      entities,
      wordCount: markdownContent.split(/\s+/).length,
    };
  }

  function getTitle() {
    return document.querySelector('meta[property="og:title"]')?.content ||
           document.querySelector('meta[name="twitter:title"]')?.content ||
           document.querySelector('h1')?.innerText?.trim() ||
           document.title || 'Untitled Document';
  }

  function getAuthor() {
    return document.querySelector('meta[name="author"]')?.content ||
           document.querySelector('meta[property="article:author"]')?.content ||
           document.querySelector('.byline, .author, [rel="author"]')?.innerText?.trim() || '';
  }

  function getPublishDate() {
    return document.querySelector('meta[property="article:published_time"]')?.content ||
           document.querySelector('time')?.getAttribute('datetime') ||
           document.querySelector('time')?.innerText?.trim() || '';
  }

  function getMetaDescription() {
    return document.querySelector('meta[name="description"]')?.content ||
           document.querySelector('meta[property="og:description"]')?.content || '';
  }

  function summarizeText(text) {
    const sentences = text.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length > 20);
    return sentences.slice(0, 3).join('. ') + (sentences.length > 0 ? '.' : '');
  }

  function convertHtmlTableToMarkdown(table) {
    const rows = Array.from(table.querySelectorAll('tr'));
    if (rows.length < 2) return null;

    const mdRows = [];
    rows.forEach((tr, rIdx) => {
      const cells = Array.from(tr.querySelectorAll('th, td')).map(c => c.innerText.replace(/[\n\r]+/g, ' ').trim());
      if (cells.length > 0) {
        mdRows.push(`| ${cells.join(' | ')} |`);
        if (rIdx === 0) {
          mdRows.push(`| ${cells.map(() => '---').join(' | ')} |`);
        }
      }
    });
    return mdRows.join('\n');
  }

  function convertNodeToMarkdown(node) {
    let output = '';
    const walk = (el) => {
      if (el.nodeType === Node.TEXT_NODE) {
        output += el.textContent.replace(/\s+/g, ' ');
      } else if (el.nodeType === Node.ELEMENT_NODE) {
        const tag = el.tagName.toLowerCase();
        if (/^h[1-6]$/.test(tag)) {
          const level = '#'.repeat(parseInt(tag[1]));
          output += `\n\n${level} ${el.innerText.trim()}\n\n`;
        } else if (tag === 'p') {
          output += `\n\n${el.innerText.trim()}\n\n`;
        } else if (tag === 'li') {
          output += `\n* ${el.innerText.trim()}`;
        } else if (tag === 'blockquote') {
          output += `\n\n> ${el.innerText.trim()}\n\n`;
        } else if (tag === 'pre' || tag === 'code') {
          output += `\n\`\`\`\n${el.innerText.trim()}\n\`\`\`\n`;
        } else {
          for (const child of el.childNodes) {
            walk(child);
          }
        }
      }
    };
    walk(node);
    return output.replace(/\n{3,}/g, '\n\n').trim();
  }

  function harvestCandidateEntities(text) {
    const entityMap = new Map();
    // Match Capitalized Phrases (e.g. "Lisinopril", "Phase III", "Metformin", "Acute Renal Failure")
    const matches = text.match(/\b[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*\b/g) || [];
    
    const stopwords = new Set([
      'The', 'A', 'An', 'This', 'That', 'These', 'Those', 'In', 'On', 'At', 'By', 'For',
      'With', 'About', 'Against', 'Between', 'Into', 'Through', 'During', 'Before', 'After',
      'Above', 'Below', 'To', 'From', 'Up', 'Down', 'Out', 'Off', 'Over', 'Under', 'Again',
      'Further', 'Then', 'Once', 'Here', 'There', 'When', 'Where', 'Why', 'How', 'All', 'Any',
      'Both', 'Each', 'Few', 'More', 'Most', 'Other', 'Some', 'Such', 'No', 'Nor', 'Not',
      'Only', 'Own', 'Same', 'So', 'Than', 'Too', 'Very', 'Can', 'Will', 'Just', 'Should', 'Now'
    ]);

    matches.forEach(m => {
      const term = m.trim();
      if (term.length > 2 && !stopwords.has(term) && !/^\d+$/.test(term)) {
        entityMap.set(term, (entityMap.get(term) || 0) + 1);
      }
    });

    const results = [];
    for (const [name, occurrences] of entityMap.entries()) {
      if (occurrences >= 2) {
        results.push({ name, occurrences, label: inferEntityLabel(name) });
      }
    }
    return results.sort((a, b) => b.occurrences - a.occurrences).slice(0, 20);
  }

  function inferEntityLabel(term) {
    const lower = term.toLowerCase();
    if (lower.includes('patient') || lower.includes('case')) return 'Patient';
    if (lower.includes('trial') || lower.includes('study')) return 'ClinicalTrial';
    if (lower.includes('syndrome') || lower.includes('disease') || lower.includes('itis')) return 'Diagnosis';
    if (lower.includes('pril') || lower.includes('olol') || lower.includes('statin') || lower.includes('formin')) return 'Medication';
    return 'DomainConcept';
  }

  function showClipToast(title, subtitle) {
    const existing = document.getElementById('__uka_toast__');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = '__uka_toast__';
    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 2147483647;
      display: flex;
      align-items: center;
      gap: 12px;
      background: #111422;
      border: 1px solid rgba(122, 82, 244, 0.4);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(122, 82, 244, 0.2);
      border-radius: 12px;
      padding: 14px 20px;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      animation: __uka_slide_in 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    `;

    toast.innerHTML = `
      <div style="width: 32px; height: 32px; border-radius: 8px; background: linear-gradient(135deg, #7a52f4, #a855f7); display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 16px;">
        U
      </div>
      <div>
        <div style="font-weight: 600; font-size: 14px; color: #f8fafc;">${escapeHtml(title)}</div>
        <div style="font-size: 12px; color: #94a3b8;">${escapeHtml(subtitle)}</div>
      </div>
    `;

    const style = document.createElement('style');
    style.textContent = `
      @keyframes __uka_slide_in {
        from { transform: translateY(50px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
    `;
    document.head.appendChild(style);
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(20px)';
      setTimeout(() => toast.remove(), 400);
    }, 3500);
  }

  function escapeHtml(str) {
    return str.replace(/[&<>'"]/g, tag => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[tag] || tag));
  }
})();

