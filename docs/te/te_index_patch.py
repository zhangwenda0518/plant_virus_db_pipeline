#!/usr/bin/env python3
"""Patch te/index.html to add interactive sequence data table."""
import re

path = "/opt/plant_virus_db/plant_virus_db_pipeline/docs/te/index.html"
with open(path, encoding="utf-8") as f:
    html = f.read()

extra_css = """
.srch{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.srch input{padding:8px 14px;border:1px solid #ddd;border-radius:6px;font-size:13px;width:240px}
.srch select{padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:13px}
.srch .cnt{font-size:12px;color:#999;margin-left:auto}
.tbl-wrap{overflow-x:auto;max-height:520px;overflow-y:auto}
.tbl-wrap table{width:100%;border-collapse:collapse;font-size:12px;min-width:900px}
.tbl-wrap thead{position:sticky;top:0;z-index:2}
.tbl-wrap th{background:#6C3483;color:#fff;padding:10px 12px;text-align:left;cursor:pointer;user-select:none;white-space:nowrap}
.tbl-wrap th:hover{background:#7D3C98}
.tbl-wrap th .arr{margin-left:4px;font-size:10px}
.tbl-wrap td{padding:8px 12px;border-bottom:1px solid #f0e6f6;white-space:nowrap}
.tbl-wrap td.desc-col{white-space:normal;min-width:300px;max-width:500px}
.tbl-wrap tr:hover{background:#faf5fc}
.pager{display:flex;align-items:center;gap:8px;margin-top:12px;font-size:13px}
.pager button{padding:6px 14px;border:1px solid #8E44AD;background:#fff;color:#8E44AD;border-radius:6px;cursor:pointer;font-size:12px}
.pager button:hover{background:#8E44AD;color:#fff}
.pager button:disabled{opacity:.3;cursor:default}
.pager span{color:#666}
.tag-cat{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700}
.tag-raw{background:#fff3e0;color:#e65100}
.tag-clean{background:#e8f5e9;color:#2e7d32}
.tag-ex{background:#e3f2fd;color:#1565c0}
"""

table_html = r"""
<div class="card" id="seqTable">
  <h3>Sequence Browser <span style="font-weight:400;font-size:13px;color:#999">(rvdb.ENRV + ENRV_clean + EX_clean)</span></h3>
  <div class="srch">
    <input type="text" id="teSearch" placeholder="Search accession / organism / description..." oninput="renderTable()">
    <select id="teCatFilter" onchange="renderTable()">
      <option value="all">All Categories</option>
      <option value="rvdb.ENRV">rvdb.ENRV (raw)</option>
      <option value="ENRV_clean">ENRV_clean</option>
      <option value="EX_clean">EX_clean</option>
    </select>
    <span class="cnt" id="teCnt"></span>
  </div>
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th onclick="sortTable('cat')">Category <span class="arr" id="arr-cat"></span></th>
          <th onclick="sortTable('acc')">Accession <span class="arr" id="arr-acc"></span></th>
          <th onclick="sortTable('org')">Organism <span class="arr" id="arr-org"></span></th>
          <th style="min-width:180px" onclick="sortTable('desc')">Description <span class="arr" id="arr-desc"></span></th>
          <th onclick="sortTable('len')">Length (bp) <span class="arr" id="arr-len"></span></th>
          <th onclick="sortTable('date')">Date <span class="arr" id="arr-date"></span></th>
        </tr>
      </thead>
      <tbody id="teTbody"></tbody>
    </table>
  </div>
  <div class="pager">
    <button id="tePrev" onclick="changePage(-1)">&#8592; Prev</button>
    <span id="tePageInfo">Page 1</span>
    <button id="teNext" onclick="changePage(1)">Next &#8594;</button>
    <span style="margin-left:12px;font-size:11px;color:#999" id="tePageTotal"></span>
  </div>
</div>
"""

table_js = r"""
var teData = [];
var teFiltered = [];
var teSortCol = "cat";
var teSortAsc = true;
var tePage = 0;
var tePageSize = 25;
var catLabel = {"rvdb.ENRV":"rvdb.ENRV (raw)","ENRV_clean":"ENRV_clean","EX_clean":"EX_clean"};

fetch("data/te_table_data.json")
  .then(function(r) { return r.json(); })
  .then(function(d) { teData = d; renderTable(); })
  .catch(function(e) { console.error("Failed to load TE data:", e); });

function applyFilters() {
  var q = (document.getElementById("teSearch").value || "").toLowerCase();
  var cat = document.getElementById("teCatFilter").value;
  teFiltered = teData.filter(function(row) {
    if (cat !== "all" && row.cat !== cat) return false;
    if (q && row.acc.toLowerCase().indexOf(q) < 0 && row.org.toLowerCase().indexOf(q) < 0 && row.desc.toLowerCase().indexOf(q) < 0) return false;
    return true;
  });
}

function sortTable(col) {
  if (teSortCol === col) { teSortAsc = !teSortAsc; }
  else { teSortCol = col; teSortAsc = true; }
  applyFilters();
  var asc = teSortAsc ? 1 : -1;
  teFiltered.sort(function(a,b) {
    var va = a[col], vb = b[col];
    if (typeof va === "number") return (va - vb) * asc;
    return String(va).localeCompare(String(vb)) * asc;
  });
  tePage = 0;
  renderRows();
}

function changePage(delta) {
  var totalPages = Math.ceil(teFiltered.length / tePageSize);
  tePage = Math.max(0, Math.min(totalPages - 1, tePage + delta));
  renderRows();
}

function renderTable() {
  applyFilters();
  tePage = 0;
  teFiltered.sort(function(a,b) {
    var va = a[teSortCol], vb = b[teSortCol];
    if (typeof va === "number") return (va - vb) * (teSortAsc ? 1 : -1);
    return String(va).localeCompare(String(vb)) * (teSortAsc ? 1 : -1);
  });
  renderRows();
}

function renderRows() {
  var totalPages = Math.ceil(teFiltered.length / tePageSize);
  if (tePage >= totalPages) tePage = Math.max(0, totalPages - 1);
  var start = tePage * tePageSize;
  var page = teFiltered.slice(start, start + tePageSize);
  var tbody = document.getElementById("teTbody");
  var html = "";
  for (var i = 0; i < page.length; i++) {
    var row = page[i];
    var tagCls = row.cat === "rvdb.ENRV" ? "tag-raw" : row.cat === "ENRV_clean" ? "tag-clean" : "tag-ex";
    html += "<tr>" +
      '<td><span class="tag-cat ' + tagCls + '">' + (catLabel[row.cat] || row.cat) + "</span></td>" +
      '<td><a href="https://www.ncbi.nlm.nih.gov/nuccore/' + row.acc + '" target="_blank">' + row.acc + "</a></td>" +
      "<td>" + (row.org || "-") + "</td>" +
      '<td class="desc-col">' + (row.desc || "-") + "</td>" +
      "<td>" + row.len.toLocaleString() + "</td>" +
      "<td>" + (row.date || "-") + "</td>" +
      "</tr>";
  }
  tbody.innerHTML = html;
  document.getElementById("teCnt").textContent = teFiltered.length + " sequences";
  document.getElementById("tePageInfo").textContent = "Page " + (tePage + 1) + " / " + (totalPages || 1);
  document.getElementById("tePageTotal").textContent = teFiltered.length + " total";
  document.getElementById("tePrev").disabled = tePage <= 0;
  document.getElementById("teNext").disabled = tePage >= totalPages - 1;
  var arrs = ["cat","acc","org","desc","len","date"];
  for (var j = 0; j < arrs.length; j++) {
    var el = document.getElementById("arr-" + arrs[j]);
    if (el) el.textContent = arrs[j] === teSortCol ? (teSortAsc ? "\u25B2" : "\u25BC") : "";
  }
}
"""

# Insert CSS before </style>
html = html.replace("</style>", extra_css + "</style>")

# Insert table section before the Pipeline Info section
html = html.replace("<!-- Pipeline Info -->", table_html + "\n\n<!-- Pipeline Info -->")

# Insert JS before the final </script>
html = html.replace("\n</script>\n</body>", table_js + "\n</script>\n</body>")

with open(path, "w", encoding="utf-8") as f:
    f.write(html)

print("Updated te/index.html successfully")
