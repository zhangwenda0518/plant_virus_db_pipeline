// Plant Virus Literature Tracker — App Logic
let allPapers = [];
let stats = {};
let currentCat = '';
let currentPage = 1;
const PAGE_SIZE = 25;

const CATS = [
  'General','Gemini_Begomo','Potyviridae','Tobamo_Virga','Tospo_Bunya',
  'Luteo_Solemo','Clostero_Beta','Seco_Bromo_Tombus','Rhabdo_Reo_Fiji_Tenu',
  'Nanoviridae','Caulimo_Badna_Tungro','Endorna_Parti_Amalga',
  'Viroid','Methods_Resistance','Methods_Omics','Transmission_Epi'
];

// ── Init ──
async function init() {
  try {
    // Load stats
    const sr = await fetch('data/stats.json');
    stats = await sr.json();
    renderMetrics();
    renderCharts();

    // Load index to populate year filter
    const ir = await fetch('data/index.json');
    const yearIndex = await ir.json();

    // Populate year filter
    const yf = document.getElementById('yearFilter');
    yearIndex.forEach(yi => {
      const o = document.createElement('option');
      o.value = yi.year; o.textContent = yi.year + ' (' + yi.count + ')';
      yf.appendChild(o);
    });

    // Populate year sidebar
    const yl = document.getElementById('yearList');
    yearIndex.slice(0, 8).forEach(yi => {
      const d = document.createElement('div');
      d.className = 'cat-item';
      d.innerHTML = `<span>${yi.year}</span><span class="cat-count">${yi.count}</span>`;
      d.onclick = () => { document.getElementById('yearFilter').value = yi.year; renderPapers(); };
      yl.appendChild(d);
    });

    // Load all papers (lazy: first year, then rest)
    await loadPapers(yearIndex);
    renderCategorySidebar();
    renderPapers();
    document.getElementById('loading').style.display = 'none';
  } catch (e) {
    document.getElementById('loading').innerHTML = 'Error loading data: ' + e.message;
    console.error(e);
  }
}

async function loadPapers(yearIndex) {
  // Load current year's data first, then recent years
  const currentYear = new Date().getFullYear().toString();
  const recent = yearIndex.filter(y => y.year >= '2020').map(y => y.year);
  const toLoad = [currentYear, ...recent.filter(y => y !== currentYear)].slice(0, 4);

  for (const year of toLoad) {
    try {
      const r = await fetch(`data/${year}.json`);
      const papers = await r.json();
      allPapers = allPapers.concat(papers);
    } catch (e) {
      console.warn(`Year ${year} not available`);
    }
  }

  // Deduplicate
  const seen = new Set();
  allPapers = allPapers.filter(p => {
    const k = p.pmid || p.doi || p.title?.substring(0, 80);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

// ── Metrics ──
function renderMetrics() {
  document.getElementById('mTotal').textContent = stats.total?.toLocaleString() || '-';
  const years = stats.by_year ? Object.keys(stats.by_year) : [];
  document.getElementById('mYear').textContent = years.length ? `${years[0]}-${years[years.length-1]}` : '-';
  document.getElementById('mAI').textContent = stats.ai_summarized?.toLocaleString() || '0';
  document.getElementById('mCats').textContent = stats.by_category ? Object.keys(stats.by_category).length : '-';
  document.getElementById('mUpdate').textContent = (stats.last_updated || '').substring(0, 10);
}

// ── Charts ──
function renderCharts() {
  // Year distribution
  if (stats.by_year) {
    const years = Object.keys(stats.by_year).sort();
    new Chart(document.getElementById('chartYear'), {
      type: 'bar',
      data: {
        labels: years,
        datasets: [{
          label: 'Papers',
          data: years.map(y => stats.by_year[y]),
          backgroundColor: '#2e86c1',
          borderRadius: 3,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { font: { size: 10 }, maxTicksLimit: 15 } } }
      }
    });
  }

  // Category distribution
  if (stats.by_category) {
    const entries = Object.entries(stats.by_category).sort((a,b) => b[1]-a[1]).slice(0, 12);
    const colors = ['#2e86c1','#27ae60','#e74c3c','#f39c12','#8e44ad','#1abc9c',
                    '#e67e22','#2980b9','#c0392b','#16a085','#7d3c98','#2c3e50'];
    new Chart(document.getElementById('chartCat'), {
      type: 'bar',
      data: {
        labels: entries.map(e => e[0]),
        datasets: [{
          label: 'Papers',
          data: entries.map(e => e[1]),
          backgroundColor: entries.map((_,i) => colors[i % colors.length]),
          borderRadius: 3,
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { font: { size: 10 } } } }
      }
    });
  }
}

// ── Category Sidebar ──
function renderCategorySidebar() {
  const counts = {};
  allPapers.forEach(p => {
    (p.categories || []).forEach(c => { counts[c] = (counts[c] || 0) + 1; });
  });
  document.getElementById('catAll').textContent = allPapers.length;

  const cl = document.getElementById('catList');
  CATS.forEach(cat => {
    if (!counts[cat]) return;
    const d = document.createElement('div');
    d.className = 'cat-item' + (currentCat === cat ? ' active' : '');
    d.setAttribute('data-cat', cat);
    d.innerHTML = `<span>${cat}</span><span class="cat-count">${counts[cat]}</span>`;
    d.onclick = () => filterCat(cat);
    cl.appendChild(d);
  });
}

function filterCat(cat) {
  currentCat = cat;
  document.querySelectorAll('#catList .cat-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('data-cat') === cat);
  });
  currentPage = 1;
  renderPapers();
}

// ── Render Papers ──
function renderPapers() {
  let filtered = [...allPapers];
  const search = (document.getElementById('searchInput').value || '').toLowerCase();
  const year = document.getElementById('yearFilter').value;
  const source = document.getElementById('sourceFilter').value;
  const level = document.getElementById('levelFilter').value;

  if (currentCat) {
    filtered = filtered.filter(p => (p.categories || []).includes(currentCat));
  }
  if (year) {
    filtered = filtered.filter(p => String(p.year) === year);
  }
  if (source) {
    filtered = filtered.filter(p => p.source === source);
  }
  if (level) {
    filtered = filtered.filter(p => p.relevance_level === level);
  }
  if (search) {
    filtered = filtered.filter(p => {
      const txt = [p.title, p.authors, p.journal, p.abstract, (p.keyword_hits||[]).join(' ')].join(' ').toLowerCase();
      return txt.includes(search);
    });
  }

  document.getElementById('resultCount').textContent = `${filtered.length} papers`;
  if (!filtered.length) {
    document.getElementById('paperList').innerHTML = '<div class="empty"><h3>No papers found</h3><p>Try different filters or run a fetch</p></div>';
    document.getElementById('pagination').innerHTML = '';
    return;
  }

  // Paginate
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const start = (currentPage - 1) * PAGE_SIZE;
  const page = filtered.slice(start, start + PAGE_SIZE);

  // Render pagination
  const pg = document.getElementById('pagination');
  let pgHtml = '';
  if (totalPages > 1) {
    for (let i = 1; i <= Math.min(totalPages, 10); i++) {
      pgHtml += `<button class="${i===currentPage?'active':''}" onclick="goPage(${i})">${i}</button>`;
    }
    if (totalPages > 10) pgHtml += `<button disabled>...</button><button>${totalPages}</button>`;
  }
  pg.innerHTML = pgHtml;

  // Render paper items
  const pl = document.getElementById('paperList');
  let h = '';
  page.forEach(p => {
    const cats = p.categories || [];
    const catTags = cats.slice(0, 3).map(c => `<span class="badge badge-cat">${c}</span>`).join(' ');
    const jq = p.journal_quality || 'other';
    const jqBadge = jq === 'high' ? '<span class="badge badge-hi">Q1</span>'
      : jq === 'medium' ? '<span class="badge badge-md">Q2</span>'
      : jq === 'other' ? '<span class="badge badge-lo">Other</span>' : '';
    const addedTag = p.added_date && new Date(p.added_date) > new Date(Date.now() - 7*86400000)
      ? '<span class="badge badge-new">NEW</span>' : '';
    const aiTag = p.ai_done ? '<span class="badge badge-ai">AI</span>' : '';
    const srcTag = p.source_strategy ? `<span class="badge badge-source">${p.source_strategy}</span>` : '';
    const authors = (p.authors || '').substring(0, 200);
    const year = p.year || '?';

    h += `<div class="paper-item${p.added_date ? ' new' : ''}">
      <div class="paper-header">
        <a class="paper-title" href="https://pubmed.ncbi.nlm.nih.gov/${p.pmid || ''}" target="_blank">${esc(p.title || 'Untitled')}</a>
        <span style="white-space:nowrap">${addedTag}${aiTag}${jqBadge}${srcTag}</span>
      </div>
      <div class="paper-meta">
        <span>${esc(p.journal || '')}</span>
        <span>${year}</span>
        <span>${esc((p.first_author || ''))}</span>
      </div>
      <div class="paper-meta" style="margin-top:4px">${catTags}</div>`;

    // AI summary
    if (p.ai_done && (p.summary_zh || p.innovation)) {
      h += `<div class="ai-summary">`;
      if (p.summary_zh && p.summary_zh !== 'Not Mentioned') {
        h += `<div class="ai-field"><span class="ai-label">摘要</span><span class="ai-value">${esc(p.summary_zh)}</span></div>`;
      }
      if (p.innovation && p.innovation !== 'Not Mentioned') {
        h += `<div class="ai-field"><span class="ai-label">创新点</span><span class="ai-value">${esc(p.innovation)}</span></div>`;
      }
      if (p.study_object && p.study_object !== 'Not Mentioned') {
        h += `<div class="ai-field"><span class="ai-label">研究对象</span><span class="ai-value">${esc(p.study_object)}</span></div>`;
      }
      if (p.disease && p.disease !== 'Not Mentioned') {
        h += `<div class="ai-field"><span class="ai-label">病害</span><span class="ai-value">${esc(p.disease)}</span></div>`;
      }
      if (p.method_zh && p.method_zh !== 'Not Mentioned') {
        h += `<div class="ai-field"><span class="ai-label">方法</span><span class="ai-value">${esc(p.method_zh)}</span></div>`;
      }
      h += `</div>`;
    }

    // Abstract
    if (p.abstract) {
      const absId = 'abs_' + (p.pmid || Math.random().toString(36).substr(2, 8));
      h += `<span class="abs-toggle" onclick="toggleAbs('${absId}')">Show abstract</span>`;
      h += `<div class="paper-abstract" id="${absId}">${esc(p.abstract)}</div>`;
    }

    h += '</div>';
  });
  pl.innerHTML = h;
}

function goPage(n) {
  currentPage = n;
  renderPapers();
  window.scrollTo(0, 200);
}

function toggleAbs(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('open');
  const tg = el.previousElementSibling;
  if (tg) tg.textContent = el.classList.contains('open') ? 'Hide abstract' : 'Show abstract';
}

// ── Theme ──
function toggleTheme() {
  document.body.classList.toggle('dark');
  localStorage.setItem('pvlit-theme', document.body.classList.contains('dark') ? 'dark' : 'light');
}

// ── Helpers ──
function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

// ── Start ──
(function() {
  if (localStorage.getItem('pvlit-theme') === 'dark') {
    document.body.classList.add('dark');
  }
  init();
})();
