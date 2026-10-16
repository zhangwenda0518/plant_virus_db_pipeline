// Shared table logic for segmented.html and nonsegmented.html
// i18n helper: pick zh when the page language is Chinese (set by /i18n.js)
function T(en, zh) {
  try { return (window.PVDB_i18n && PVDB_i18n.lang() === 'zh') ? zh : en; } catch (e) { return en; }
}
let currentTable = null, currentRows = [], currentFields = [], currentIsSeg = false;
let currentSource = 'ref';

const SOURCES = {
  ref: { file: 'data/Plant_Virus_Ref.Info.tsv', label: 'Final Reference' },
  full: { file: 'data/Plant_Virus_Full.Info.tsv', label: 'Full Database' }
};

async function loadTable(tableId, isSegmented) {
  currentIsSeg = isSegmented;
  const src = SOURCES[currentSource];
  document.getElementById('loading').style.display = '';
  document.getElementById('tableWrap').style.display = 'none';
  document.getElementById('toolbar').style.display = 'none';

  const resp = await fetch(src.file + '?v=2');
  if (!resp.ok) {
    if (currentSource === 'full' && resp.status === 404) {
      document.getElementById('loading').innerHTML = '<p style="color:#856404;background:#fff3cd;padding:12px;border-radius:6px">' + T('Full database (211K rows) only available on', '完整库（21.1 万条）仅在') + ' <a href="http://39.106.101.94/reference/" target="_blank">' + T('production server', '生产服务器') + '</a>' + T('. Showing Ref database below.', ' 上提供，下面展示参考库。') + '</p>';
      currentSource = 'ref';
      return loadTable(tableId, isSegmented);
    }
    document.getElementById('loading').innerHTML = '<p style="color:red">' + src.file + ' not found</p>'; return;
  }
  const text = await resp.text();

  Papa.parse(text, {
    header: true, skipEmptyLines: true, delimiter: '\t',
    complete(results) {
      const fields = results.meta.fields;
      const hasCategory = fields.includes('Category');
      const rows = [];
      for (const row of results.data) {
        const arr = fields.map(f => (row[f] != null ? String(row[f]) : ''));
        const cat = hasCategory ? (row['Category'] || '') : null;
        if (hasCategory) {
          if (isSegmented && cat.startsWith('Segmented')) rows.push(arr);
          else if (!isSegmented && cat.startsWith('NonSegmented')) rows.push(arr);
        } else {
          const s = (row['Segment'] || '').trim();
          const hs = s.length > 0 && !/^\d+$/.test(s);
          if ((isSegmented && hs) || (!isSegmented && !hs)) rows.push(arr);
        }
      }
      currentRows = rows;
      currentFields = fields;

      // Destroy old table and replace DOM
      if (currentTable) { currentTable.destroy(); currentTable = null; }
      $('#tableWrap').empty();
      const tbl = document.createElement('table');
      tbl.className = 'display'; tbl.style.width = '100%';
      document.getElementById('tableWrap').appendChild(tbl);

      // Find Accession column index (column 0 in fields)
      const accIdx = fields.findIndex(f => f === 'Accession');

      const cols = [{ title: '<input type="checkbox" id="selectAll" onclick="toggleAll(this)">', orderable: false, width: '30px' },
        ...fields.map((f, i) => ({ title: f }))];

      const dataWithCheck = rows.map((r, i) => {
        const row = r.map(escapeHtml);
        if (accIdx >= 0) {
          const acc = row[accIdx];
          row[accIdx] = '<a href="https://www.ncbi.nlm.nih.gov/nuccore/' + acc + '" target="_blank" rel="noopener">' + acc + '</a>';
        }
        return ['<input type="checkbox" class="rowCheck" data-idx="' + i + '">', ...row];
      });

      document.getElementById('loading').style.display = 'none';
      document.getElementById('tableWrap').style.display = '';

      currentTable = $(tbl).DataTable({
        data: dataWithCheck, columns: cols, deferRender: true,
        pageLength: 50, lengthMenu: [[25, 50, 100, 500, -1], [25, 50, 100, 500, T('All', '全部')]],
        language: {
          search: T('Search:', '搜索：'),
          lengthMenu: T('Show _MENU_ entries', '显示 _MENU_ 条'),
          info: T('Showing _START_ to _END_ of _TOTAL_ entries', '显示第 _START_–_END_ 条，共 _TOTAL_ 条'),
          infoEmpty: T('No entries', '无记录'),
          infoFiltered: T('(filtered from _MAX_ total entries)', '（从 _MAX_ 条中筛选）'),
          zeroRecords: T('No matching records found', '未找到匹配记录'),
          paginate: { first: T('First', '首页'), last: T('Last', '末页'),
                      next: T('Next', '下一页'), previous: T('Previous', '上一页') }
        },
        order: [[1, 'asc']], dom: 'Bfrtip',
        buttons: [
          { extend: 'colvis', text: T('Columns', '列') },
          { text: T('CSV Selected', '导出所选 CSV'), action: function() { exportSelected('csv'); } },
          { text: T('TSV Selected', '导出所选 TSV'), action: function() { exportSelected('tsv'); } },
          { text: T('Copy Selected', '复制所选'), action: function() { exportSelected('copy'); } }
        ],
        columnDefs: [{ targets: [0], searchable: false, render: (d) => d }],
        initComplete: function() { this.api().columns.adjust().draw(); }
      });
      // Fix alignment after tab switch or resize
      $(window).on('resize', function() { if (currentTable) currentTable.columns.adjust().draw(); });

      document.getElementById('countText').textContent =
        rows.length.toLocaleString() + T(' records', ' 条记录');
      document.getElementById('selectedCount').textContent = '';
      document.getElementById('toolbar').style.display = '';
      document.querySelectorAll('.src-toggle').forEach(b => b.classList.toggle('active', b.dataset.src === currentSource));
    }
  });
}

function toggleAll(el) {
  const checked = el.checked;
  document.querySelectorAll('.rowCheck').forEach(cb => { cb.checked = checked; });
  updateSelectedCount();
}
document.addEventListener('change', function(e) { if (e.target.classList.contains('rowCheck')) updateSelectedCount(); });

function getSelected() {
  const sel = [];
  document.querySelectorAll('.rowCheck:checked').forEach(cb => {
    const i = parseInt(cb.dataset.idx);
    if (i >= 0 && i < currentRows.length) sel.push(currentRows[i]);
  });
  return sel;
}
function updateSelectedCount() {
  const n = document.querySelectorAll('.rowCheck:checked').length;
  document.getElementById('selectedCount').textContent = n > 0 ? T(n + ' selected', '已选 ' + n + ' 条') : '';
}

function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text);
  } else {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
}

function exportSelected(fmt) {
  const rows = getSelected();
  if (!rows.length) {
    // Export all visible if none selected
    const allData = currentTable.rows({ filter: 'applied' }).data().toArray();
    const header = currentFields.join('\t');
    const body = allData.map(r => r.slice(1).join('\t')).join('\n');
    if (fmt === 'copy') {
      copyToClipboard(header + '\n' + body);
      return;
    }
    downloadBlob(header + '\n' + body, 'export.tsv', 'text/tab-separated-values');
    return;
  }
  const sep = fmt === 'tsv' ? '\t' : ',';
  const header = currentFields.join(sep);
  const body = rows.map(r => r.map(v => sep !== '\t' ? '"' + v.replace(/"/g, '""') + '"' : v).join(sep)).join('\n');
  if (fmt === 'copy') {
    copyToClipboard(header + '\n' + body);
    alert(T(rows.length + ' rows copied to clipboard', '已复制 ' + rows.length + ' 行到剪贴板'));
    return;
  }
  const ext = fmt === 'tsv' ? '.tsv' : '.csv';
  const mime = fmt === 'tsv' ? 'text/tab-separated-values' : 'text/csv';
  downloadBlob(header + '\n' + body, 'selected' + ext, mime);
}

function downloadBlob(content, filename, mime) {
  const blob = new Blob([content], { type: mime + ';charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function escapeHtml(str) {
  const div = document.createElement('div'); div.textContent = str; return div.innerHTML;
}

function switchSource(src) {
  if (src === currentSource) return;
  currentSource = src;
  loadTable('#table', currentIsSeg);
}

// 语言切换后重建表格，让 DataTables 自身生成的界面文案跟着变
window.PVDB_onLangChange = function () {
  if (currentTable) loadTable('#table', currentIsSeg);
};
