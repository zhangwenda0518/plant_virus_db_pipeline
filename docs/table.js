// Shared table logic for segmented.html and nonsegmented.html
let currentTable = null;
let currentSource = 'ref'; // 'ref' or 'full'

const SOURCES = {
  ref: { file: 'data/final.cluster.ref_info.tsv', label: 'Final Reference' },
  full: { file: 'data/Plant_Virus_Info.full.tsv', label: 'Full Database' }
};

async function loadTable(tableId, isSegmented) {
  const src = SOURCES[currentSource];
  const pageTitle = (isSegmented ? 'Segmented' : 'Non-Segmented') + ' Viruses';
  document.title = pageTitle + ' — Plant Virus DB';
  document.getElementById('sourceLabel').textContent = 'Source: ' + src.label;
  document.getElementById('loading').style.display = '';
  document.getElementById('tableWrap').style.display = 'none';

  const resp = await fetch(src.file);
  if (!resp.ok) {
    document.getElementById('loading').innerHTML = '<p style="color:red">' + src.file + ' not found</p>';
    return;
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
        const seg = row['Segment'] || '';

        if (hasCategory) {
          // Ref data: use Category column
          if (isSegmented && cat.startsWith('Segmented')) rows.push(arr);
          else if (!isSegmented && cat.startsWith('NonSegmented')) rows.push(arr);
        } else {
          // Full data: use Segment column as heuristic
          const hasSegment = seg && seg.trim().length > 0 && !/^\d+$/.test(seg.trim());
          if ((isSegmented && hasSegment) || (!isSegmented && !hasSegment)) rows.push(arr);
        }
      }

      document.getElementById('countText').textContent = rows.length.toLocaleString() + ' records';

      if (currentTable) currentTable.destroy();
      currentTable = $(tableId).DataTable({
        data: rows,
        columns: fields.map(f => ({ title: f })),
        deferRender: true,
        pageLength: 50,
        lengthMenu: [[25, 50, 100, 500, -1], [25, 50, 100, 500, 'All']],
        order: [[0, 'asc']],
        scrollX: true,
        dom: 'Bfrtip',
        buttons: [
          { extend: 'colvis', text: 'Columns' },
          { extend: 'csv', text: 'CSV', exportOptions: { columns: ':visible' } },
          { extend: 'copy', text: 'Copy' }
        ],
        columnDefs: [{ targets: [13, 14, 19], visible: false }]
      });

      document.getElementById('loading').style.display = 'none';
      document.getElementById('tableWrap').style.display = '';
      // Update toggle buttons
      document.querySelectorAll('.src-toggle').forEach(b => {
        b.classList.toggle('active', b.dataset.src === currentSource);
      });
    }
  });
}

function switchSource(src) {
  if (src === currentSource) return;
  currentSource = src;
  const isSeg = document.title.startsWith('Segmented');
  loadTable('#table', isSeg);
}
