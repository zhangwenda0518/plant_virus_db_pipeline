// Shared table logic for segmented.html and nonsegmented.html
async function initTable(tableId, filterFn, pageTitle) {
  document.title = pageTitle + ' — Plant Virus DB';

  const resp = await fetch('data/final.cluster.ref_info.tsv');
  if (!resp.ok) { document.getElementById('loading').innerHTML = '<p style="color:red">Failed to load data</p>'; return; }
  const text = await resp.text();

  Papa.parse(text, {
    header: true, skipEmptyLines: true, delimiter: '\t',
    complete(results) {
      const fields = results.meta.fields;
      const catIdx = fields.indexOf('Category');
      const allRows = [];
      let segN = 0, nsN = 0;

      for (const row of results.data) {
        const cat = row['Category'] || '';
        const arr = fields.map(f => row[f] || '');
        if (cat.startsWith('Segmented')) segN++;
        else nsN++;
        if (filterFn(cat)) allRows.push(arr);
      }

      document.getElementById('tableTitle').textContent = pageTitle;
      document.getElementById('countText').textContent = allRows.length.toLocaleString() + ' records';

      const table = $(tableId).DataTable({
        data: allRows,
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
    }
  });
}
