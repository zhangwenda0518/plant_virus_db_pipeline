#!/usr/bin/env python3
"""Plant Virus Literature Tracker — Flask API + Web UI"""

import json, os, sys, time
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

BASE = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = Path(os.environ.get("PAPERS_JSON", str(BASE / "data" / "papers.json")))
app = Flask(__name__, static_folder=str(BASE / "web"), static_url_path="/literature/static")


def load_papers():
    if not DATA_FILE.exists():
        return {"papers": [], "total": 0, "last_updated": "", "new_since_update": 0}
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


PAGE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Plant Virus Literature</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
<link href="https://unpkg.com/bootstrap-table@1.22.1/dist/bootstrap-table.min.css" rel="stylesheet">
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;color:#333;margin:0}
nav{background:#1a5276;display:flex;align-items:center;padding:0 24px;height:52px}
nav a{color:rgba(255,255,255,.8);text-decoration:none;padding:14px 18px;font-size:14px}
nav a:hover{background:rgba(255,255,255,.15);color:#fff}
nav .brand{font-weight:700;font-size:16px;color:#fff;margin-right:8px;padding:0}
.hero{background:linear-gradient(135deg,#1a5276,#2e86c1);color:#fff;padding:28px 24px;margin-bottom:20px}
.hero h1{margin:0;font-size:22px}.hero p{margin:4px 0 0;opacity:.85;font-size:13px}
.main{max-width:1400px;margin:0 auto;padding:0 16px}
.fixed-table-toolbar .search input{height:36px!important;padding:6px 14px!important;font-size:13px!important}
.j-badge{display:inline-block;padding:2px 10px;border-radius:4px;font-size:11px;font-weight:600;color:#fff;margin-right:6px;white-space:nowrap}
.j-hi{background:#dc3545}.j-md{background:#fd7e14}.j-lo{background:#6c757d}
.abs-pv{font-size:13px;color:#666;line-height:1.5;max-height:0;overflow:hidden;transition:max-height .3s}
.abs-pv.open{max-height:2000px;margin:4px 0}
.abs-tg{font-size:12px;color:#2e86c1;cursor:pointer;display:inline-block;margin-top:2px}
.abs-tg:hover{text-decoration:underline}
.plink{color:#1a5276;font-weight:600;text-decoration:none}
.plink:hover{text-decoration:underline}
.new-row td{background:#fffde7!important}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}
.stat{background:#fff;padding:14px;border-radius:8px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.stat .val{font-size:22px;font-weight:700;color:#1a5276}.stat .lbl{font-size:11px;color:#888}
footer{background:#1a5276;color:rgba(255,255,255,.7);text-align:center;padding:14px;margin-top:40px;font-size:12px}
footer a{color:rgba(255,255,255,.9)}
</style></head><body>
<nav><a class="brand" href="/">Plant Virus DB</a><a href="/reference/">参考库</a><a href="/explorer/">浏览器</a><a href="/virus/">病毒详情</a><a href="/primers/">引物</a><a href="/vector/">媒介</a><a href="/te/">TE·EVE</a><a href="/metabuli/">Metabuli</a><a href="/literature/" style="color:#fff;font-weight:600">文献</a><a href="/knowledge/">知识</a></nav>
<div class="hero"><h1>Plant Virus Literature Tracker</h1><p>Auto-tracking recent plant virus papers from PubMed &middot; Updated daily</p></div>
<div class="main">
<div class="stats"><div class="stat"><div class="val" id="stat-total">{{total}}</div><div class="lbl">Papers Indexed</div></div><div class="stat"><div class="val green" id="stat-new">{{new_count}}</div><div class="lbl">New This Update</div></div><div class="stat"><div class="val">{{current_year}}</div><div class="lbl">Current Year</div></div><div class="stat"><div class="val">{{last_update}}</div><div class="lbl">Last Updated</div></div></div>
<table id="paper-table"></table>
</div>
<footer>Plant Virus Literature Tracker | Auto-updated from PubMed via NCBI E-utilities | <a href="/reference/">Reference DB</a> &middot; <a href="/primers/">Primers</a> &middot; <a href="/explorer/">Explorer</a></footer>

<script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://unpkg.com/bootstrap-table@1.22.1/dist/bootstrap-table.min.js"></script>
<script>
const TOP8=['annu rev virol','proc natl acad sci','front plant sci','plos pathog','mol plant pathol','j virol','virology','virus res'];
const MID7=['arch virol','plant dis','viruses','front microbiol','j gen virol','virol j','phytopathology'];
function jCls(j){j=(j||'').toLowerCase();if(TOP8.some(t=>j.includes(t)))return'j-hi';if(MID7.some(t=>j.includes(t)))return'j-md';return'j-lo'}
function esc(t){if(!t)return'';return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function toggleAbs(el){var p=$(el).prev('.abs-pv');if(p.hasClass('open')){p.removeClass('open');$(el).text('Show abstract')}else{p.addClass('open');$(el).text('Hide abstract')}}

function infoFormatter(value,row){
 var h='<span class=\"j-badge '+jCls(row.journal)+'\">'+esc(row.journal||'?')+'</span> ';
 if(row.categories&&row.categories.length){
  row.categories.forEach(function(c){h+='<span style=\"display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;background:#e3f2fd;color:#1565c0;margin-right:3px\">'+c+'</span>'});
  h+=' ';
 }
 h+='<a class=\"plink\" href=\"https://pubmed.ncbi.nlm.nih.gov/'+row.pmid+'\" target=\"_blank\">'+esc(row.title||'Untitled')+'</a>';
 h+='<div style=\"font-size:12px;color:#555;margin-top:2px\">'+esc(row.authors||'')+'</div>';
 h+='<div style=\"font-size:12px;color:#888\">'+esc(row.journal||'')+', '+row.year+(row.doi?' &middot; <a href=\"https://doi.org/'+row.doi+'\" target=\"_blank\" style=\"font-size:11px\">DOI</a>':'')+'</div>';
 if(row.abstract){
  h+='<div class=\"abs-pv\">'+esc(row.abstract)+'</div>';
  h+='<span class=\"abs-tg\" onclick=\"toggleAbs(this)\">Show abstract</span>';
 }
 return h;
}
function actionFormatter(value,row){
 var h='<a href=\"https://pubmed.ncbi.nlm.nih.gov/'+row.pmid+'\" target=\"_blank\" class=\"btn btn-sm btn-outline-primary\" title=\"PubMed\"><i class=\"bi-journal-text\"></i></a> ';
 if(row.doi)h+='<a href=\"https://doi.org/'+row.doi+'\" target=\"_blank\" class=\"btn btn-sm btn-outline-secondary\" title=\"DOI\"><i class=\"bi-link-45deg\"></i></a>';
 return h;
}
function newRowClass(row,index){if(row.added_date)return 'new-row';return {}}

async function init(){
 try{
  var r=await fetch('/literature/api/papers');var d=await r.json();var papers=d.papers||[];
  document.getElementById('stat-total').textContent=papers.length;
  document.getElementById('stat-new').textContent=d.new_since_update||0;
  $('#paper-table').bootstrapTable({
   data:papers,
   pagination:true,search:true,searchAlign:'left',sortable:true,
   pageSize:25,pageList:'[25,50,100]',
   rowAttributes:newRowClass,
   columns:[
    {field:'year',title:'Year',sortable:true,width:70},
    {field:'title',title:'Title / Info',sortable:true,formatter:infoFormatter,escape:false},
    {field:'pmid',title:'Actions',sortable:false,width:90,formatter:actionFormatter,escape:false}
   ]
  });
 }catch(e){console.error(e);$('#paper-table').html('<tr><td colspan=3>Error: '+e.message+'</td></tr>')}
}
init();
</script></body></html>'''


@app.route("/literature/")
@app.route("/literature")
def index():
    data = load_papers()
    last = data.get("last_updated", "")[:10]
    current_year = str(datetime.now().year)
    new_count = data.get("new_since_update", len(data.get("papers", [])))
    return render_template_string(PAGE,
        total=len(data.get("papers", [])),
        new_count=new_count,
        current_year=current_year,
        last_update=last,
        last_update_short=last,
    )


@app.route("/literature/api/papers")
def api_papers():
    data = load_papers()
    return jsonify(data)


@app.route("/literature/api/stats")
def api_stats():
    data = load_papers()
    papers = data.get("papers", [])
    years = {}
    journals = {}
    for p in papers:
        y = str(p.get("year", "unknown"))
        years[y] = years.get(y, 0) + 1
        j = p.get("journal", "unknown")
        journals[j] = journals.get(j, 0) + 1
    return jsonify({
        "total": len(papers),
        "last_updated": data.get("last_updated", ""),
        "new_since_update": data.get("new_since_update", 0),
        "years": years,
        "top_journals": sorted(journals.items(), key=lambda x: -x[1])[:20],
    })


@app.route("/literature/v2/")
@app.route("/literature/v2")
def index_v2():
    """Serve the new static web app."""
    return app.send_static_file("index.html")


@app.route("/literature/api/papers/filtered")
def api_papers_filtered():
    """Return filtered papers by category/year/search."""
    data = load_papers()
    papers = data.get("papers", [])
    category = request.args.get("category", "")
    year = request.args.get("year", "")
    search = request.args.get("search", "").lower()
    limit = int(request.args.get("limit", 100))

    if category:
        papers = [p for p in papers if category in (p.get("categories") or [])]
    if year:
        papers = [p for p in papers if str(p.get("year")) == year]
    if search:
        papers = [p for p in papers if search in (p.get("title", "") + p.get("abstract", "")).lower()]

    return jsonify({"papers": papers[:limit], "total": len(papers)})


@app.route("/literature/api/categories")
def api_categories():
    """Return categories with counts."""
    data = load_papers()
    cats = {}
    for p in data.get("papers", []):
        for c in (p.get("categories") or []):
            cats[c] = cats.get(c, 0) + 1
    return jsonify({"categories": cats, "total": len(data.get("papers", []))})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5003))
    app.run(host="0.0.0.0", port=port, debug=False)

