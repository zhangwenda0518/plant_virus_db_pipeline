/**
 * APS Image Database — 浏览器 Console 提取脚本
 *
 * 用法:
 * 1. 浏览器打开 https://imagedatabase.apsnet.org/ 并登录
 * 2. 搜索/筛选到你要的图片 (如搜索 "virus" 或选 Category: Viruses)
 * 3. F12 打开 Console, 粘贴运行此脚本
 * 4. 自动翻页收集所有图片数据, 完成后下载 TSV
 */

(async function extractAPS() {
  const results = [];
  const MAX_PAGES = 100; // 安全上限
  const DELAY = 1500;    // 页面间延迟 (ms)

  function parseImageCard(card) {
    const img = card.querySelector('img');
    if (!img) return null;
    const src = img.src || '';
    if (!src.includes('Image.ashx')) return null;

    // Get full-res URL
    const fullUrl = src.replace(/SZ=\d+/, 'SZ=800');

    // Parse text fields
    const text = card.innerText || '';
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

    let hostSci = '', hostCommon = '', agentType = '', pathogen = '', disease = '', contributor = '', caption = '';

    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (l.startsWith('Host Name')) {
        hostSci = lines[i+1] || '';
        hostCommon = (lines[i+2] || '').replace(/[()]/g, '').trim();
      }
      if (l.startsWith('Causal Agent Type')) agentType = lines[i+1] || '';
      if (l.startsWith('Pathogen Name')) {
        const pn = lines[i+1] || '';
        const m = pn.match(/^(.+?)\s*\((.+?)\)/);
        if (m) { pathogen = m[1].trim(); disease = m[2].trim(); }
        else pathogen = pn;
      }
      if (l.startsWith('Image Contributor')) contributor = lines[i+1] || '';
    }
    // Caption is usually the first line of the card
    caption = lines[0] || '';

    return { hostSci, hostCommon, agentType, pathogen, disease, contributor, caption, fullUrl, thumbUrl: src };
  }

  function collectCurrentPage() {
    const cards = document.querySelectorAll('.image-card, .result-item, [class*="result"], [class*="image-item"]');
    if (cards.length === 0) {
      // Fallback: find all Image.ashx links
      const imgs = document.querySelectorAll('img[src*="Image.ashx"]');
      imgs.forEach(img => {
        const card = img.closest('div,li,tr,td,article');
        if (card) {
          const r = parseImageCard(card);
          if (r) results.push(r);
        }
      });
    } else {
      cards.forEach(card => {
        const r = parseImageCard(card);
        if (r) results.push(r);
      });
    }
  }

  function findNextPageLink() {
    // Look for "Next" or ">" pagination link
    const links = document.querySelectorAll('a');
    for (const a of links) {
      if (a.textContent.match(/Next|>|»|下一页/) && a.href) return a;
    }
    // Try numbered page links
    const currentPageEl = document.querySelector('.current-page, .active-page, [class*="current"]');
    if (currentPageEl) {
      const next = currentPageEl.nextElementSibling;
      if (next && next.tagName === 'A') return next;
    }
    return null;
  }

  async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  console.log('APS Image Extractor — starting...');
  let page = 1;

  while (page <= MAX_PAGES) {
    console.log(`Page ${page}: collecting...`);
    collectCurrentPage();
    console.log(`  -> ${results.length} total images so far`);

    const nextLink = findNextPageLink();
    if (!nextLink) {
      console.log('No next page found. Done.');
      break;
    }

    console.log(`  -> navigating to next page...`);
    nextLink.click();
    await sleep(DELAY);

    // Wait for results to load
    let waited = 0;
    while (waited < 10) {
      const imgs = document.querySelectorAll('img[src*="Image.ashx"]');
      if (imgs.length > 0) break;
      await sleep(500);
      waited++;
    }
    page++;
  }

  // Download results
  const headers = ['hostSci','hostCommon','agentType','pathogen','disease','contributor','caption','fullUrl','thumbUrl'];
  const tsv = headers.join('\t') + '\n' + results.map(r =>
    headers.map(h => (r[h]||'').replace(/\t/g,' ').replace(/\n/g,' ')).join('\t')
  ).join('\n');

  const blob = new Blob([tsv], {type: 'text/tab-separated-values'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'aps_virus_images.tsv';
  a.click();
  URL.revokeObjectURL(url);

  console.log(`\nDone! ${results.length} images saved to aps_virus_images.tsv`);
  console.log(`  Virus entries: ${results.filter(r => r.agentType === 'virus').length}`);
  console.log(`  Unique pathogens: ${new Set(results.map(r => r.pathogen)).size}`);
})();
