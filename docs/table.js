// Shared table logic for segmented.html and nonsegmented.html
let currentTable = null, currentRows = [], currentFields = [];
let currentSource = 'ref';

const SOURCES = {
  ref: { file: 'data/final.cluster.ref_info.tsv', label: 'Final Reference' },
  full: { file: 'data/Plant_Virus_Info.full.tsv', label: 'Full Database' }
};

async function loadTable(tableId, isSegmented) {
  const src = SOURCES[currentSource];
  document.getElementById('loading').style.display = '';
  document.getElementById('tableWrap').style.display = 'none';
  document.getElementById('toolbar').style.display = 'none';

  const resp = await fetch(src.file);
  if (!resp.ok) { document.getElementById('loading').innerHTML = '<p style="color:red">' + src.file + ' not found</p>'; return; }
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

      currentTable = $(tbl).DataTable({
        data: dataWithCheck, columns: cols, deferRender: true,
        pageLength: 50, lengthMenu: [[25, 50, 100, 500, -1], [25, 50, 100, 500, 'All']],
        order: [[1, 'asc']], scrollX: true, autoWidth: false, dom: 'Bfrtip',
        buttons: [{ extend: 'colvis', text: 'Columns' }],
        columnDefs: [{ targets: [0], searchable: false, render: (d) => d }]
      });
      // Fix alignment: redraw on window resize
      $(window).on('resize', function() { if (currentTable) currentTable.columns.adjust().draw(); });

      document.getElementById('countText').textContent = rows.length.toLocaleString() + ' records';
      document.getElementById('selectedCount').textContent = '';
      document.getElementById('loading').style.display = 'none';
      document.getElementById('tableWrap').style.display = '';
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
  document.getElementById('selectedCount').textContent = n > 0 ? n + ' selected' : '';
}

function exportSelected(fmt) {
  const rows = getSelected();
  if (!rows.length) {
    // Export all visible if none selected
    const allData = currentTable.rows({ filter: 'applied' }).data().toArray();
    const header = currentFields.join('\t');
    const body = allData.map(r => r.slice(1).join('\t')).join('\n');
    downloadBlob(header + '\n' + body, 'export.tsv', 'text/tab-separated-values');
    return;
  }
  const header = currentFields.join(fmt === 'tsv' ? '\t' : ',');
  const body = rows.map(r => r.map(v => fmt === 'tsv' ? v : '"' + v.replace(/"/g, '""') + '"').join(fmt === 'tsv' ? '\t' : ',')).join('\n');
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
  const isSeg = document.title.startsWith('Segmented');
  loadTable('#table', isSeg);
}
