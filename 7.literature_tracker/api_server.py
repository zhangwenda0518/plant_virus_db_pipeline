#!/usr/bin/env python3
"""Plant Virus Literature Tracker — Flask API + Web UI"""

import functools, hmac, json, os, sys, threading, time
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

BASE = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(BASE))
DATA_FILE = Path(os.environ.get("PAPERS_JSON", str(BASE / "data" / "papers.json")))
app = Flask(__name__, static_folder=str(BASE / "web"), static_url_path="/literature/static")
from summarize_papers import SYSTEM_PROMPT, DIGEST_PROMPT, _llm_call, _parse_json_lenient, summarize_digest

# ── Security / limits (audit S3 + D4, 2026-10-03) ──
# Optional shared-secret auth for the LLM endpoints. When empty the endpoints are
# open — acceptable only for local development, never for the public deployment.
LITERATURE_API_TOKEN = os.environ.get("LITERATURE_API_TOKEN", "")
# SSRF guard: the server key may only ever be sent to this fixed provider.
ALLOWED_LLM_BASE_URLS = ("https://api.deepseek.com",)
# Request-body / list caps (DoS guard: no unbounded client input).
MAX_BODY_CHARS = 32_000
MAX_CONTENT_LENGTH = MAX_BODY_CHARS * 4  # bytes; UTF-8 is at most 4 bytes/char
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

if not LITERATURE_API_TOKEN:
    print("=" * 78, file=sys.stderr)
    print("WARNING: LITERATURE_API_TOKEN is not set — /literature/api/summarize/*", file=sys.stderr)
    print("         accepts ANONYMOUS requests and will spend this server's LLM key.", file=sys.stderr)
    print("         Set LITERATURE_API_TOKEN in the service environment (see service file).", file=sys.stderr)
    print("=" * 78, file=sys.stderr)


def require_api_token(fn):
    """403 unless X-API-Token matches LITERATURE_API_TOKEN (no-op when unset)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        token = LITERATURE_API_TOKEN
        if token:
            supplied = request.headers.get("X-API-Token", "") or ""
            if not hmac.compare_digest(str(supplied), str(token)):
                app.logger.warning("403 %s from %s (bad/missing X-API-Token)",
                                   request.path, request.remote_addr)
                return jsonify({"error": "Forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper


def _is_allowed_base_url(url: str) -> bool:
    u = (url or "").strip().rstrip("/")
    return any(u == p or u.startswith(p + "/") for p in ALLOWED_LLM_BASE_URLS)


def _read_json_body():
    """Parse the JSON request body with the 32k-character cap.

    Returns (payload, error_response); exactly one of them is None.
    """
    raw = request.get_data(cache=True) or b""
    text = raw.decode("utf-8", "replace")
    if len(text) > MAX_BODY_CHARS:
        return None, (jsonify({"error": f"Request body too large "
                                        f"(max {MAX_BODY_CHARS} characters)"}), 400)
    try:
        payload = json.loads(text) if text.strip() else {}
    except Exception:
        return None, (jsonify({"error": "Invalid JSON body"}), 400)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "JSON body must be an object"}), 400)
    return payload, None


@app.errorhandler(413)
def _payload_too_large(e):
    return jsonify({"error": f"Request body too large (max {MAX_BODY_CHARS} characters)"}), 400


# ── papers.json cache ──
# Every request used to re-parse the 30k+ paper master (tens of MB) — a trivial
# CPU/memory DoS. Cache the parsed dict by (path, mtime_ns, size); the dict is
# shared read-only between requests and reloaded only when the file changes.
_CACHE_LOCK = threading.Lock()
_PAPERS_CACHE = {"key": None, "data": None}


def _data_file_key():
    try:
        st = DATA_FILE.stat()
        return (str(DATA_FILE), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(DATA_FILE), None, None)


def load_papers():
    """Load papers.json (cached by path+mtime+size). Treat result as read-only."""
    key = _data_file_key()
    with _CACHE_LOCK:
        if _PAPERS_CACHE["data"] is not None and _PAPERS_CACHE["key"] == key:
            return _PAPERS_CACHE["data"]
    if not DATA_FILE.exists():
        data = {"papers": [], "total": 0, "last_updated": "", "new_since_update": 0}
    else:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
    with _CACHE_LOCK:
        _PAPERS_CACHE["key"] = key
        _PAPERS_CACHE["data"] = data
    return data


PAGE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Plant Virus Literature</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
<link href="https://unpkg.com/bootstrap-table@1.22.1/dist/bootstrap-table.min.css" rel="stylesheet">
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;color:#333;margin:0}
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
<script src="/lib/site-nav.js?v=2"></script>

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
function esc(t){if(t===undefined||t===null)return'';return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function toggleAbs(el){var p=$(el).prev('.abs-pv');if(p.hasClass('open')){p.removeClass('open');$(el).text('Show abstract')}else{p.addClass('open');$(el).text('Hide abstract')}}

function infoFormatter(value,row){
 var h='<span class=\"j-badge '+jCls(row.journal)+'\">'+esc(row.journal||'?')+'</span> ';
 if(row.categories&&row.categories.length){
  row.categories.forEach(function(c){h+='<span style=\"display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;background:#e3f2fd;color:#1565c0;margin-right:3px\">'+c+'</span>'});
  h+=' ';
 }
 h+='<a class=\"plink\" href=\"https://pubmed.ncbi.nlm.nih.gov/'+esc(row.pmid)+'\" target=\"_blank\">'+esc(row.title||'Untitled')+'</a>';
 h+='<div style=\"font-size:12px;color:#555;margin-top:2px\">'+esc(row.authors||'')+'</div>';
 h+='<div style=\"font-size:12px;color:#888\">'+esc(row.journal||'')+', '+esc(row.year)+(row.doi?' &middot; <a href=\"https://doi.org/'+esc(row.doi)+'\" target=\"_blank\" style=\"font-size:11px\">DOI</a>':'')+'</div>';
 if(row.abstract){
  h+='<div class=\"abs-pv\">'+esc(row.abstract)+'</div>';
  h+='<span class=\"abs-tg\" onclick=\"toggleAbs(this)\">Show abstract</span>';
 }
 return h;
}
function actionFormatter(value,row){
 var h='<a href=\"https://pubmed.ncbi.nlm.nih.gov/'+esc(row.pmid)+'\" target=\"_blank\" class=\"btn btn-sm btn-outline-primary\" title=\"PubMed\"><i class=\"bi-journal-text\"></i></a> ';
 if(row.doi)h+='<a href=\"https://doi.org/'+esc(row.doi)+'\" target=\"_blank\" class=\"btn btn-sm btn-outline-secondary\" title=\"DOI\"><i class=\"bi-link-45deg\"></i></a>';
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
    """Serve the main literature web app."""
    return app.send_static_file("index.html")


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


@app.route("/literature/v2/<path:filename>")
def static_v2(filename):
    """Serve static assets (data files, JS, CSS) for the v2 web app."""
    return app.send_static_file(filename)


@app.route("/literature/api/papers/filtered")
def api_papers_filtered():
    """Return filtered papers by category/year/search."""
    data = load_papers()
    papers = data.get("papers", [])
    category = request.args.get("category", "")
    year = request.args.get("year", "")
    search = request.args.get("search", "").lower()
    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid 'limit' parameter (integer expected)"}), 400
    if limit < 1:
        return jsonify({"error": "'limit' must be >= 1"}), 400
    limit = min(limit, MAX_LIMIT)

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


@app.route("/literature/api/summarize/paper", methods=["POST"])
@require_api_token
def api_summarize_paper():
    """Summarize a single paper using AI. Returns 13-field extraction."""
    data, err = _read_json_body()
    if err:
        return err
    title = str(data.get("title", "") or "").strip()
    abstract = str(data.get("abstract", "") or "").strip()
    if not title and not abstract:
        return jsonify({"error": "No title or abstract provided"}), 400

    model = data.get("model") or os.environ.get("LLM_MODEL", "deepseek-v4-flash")
    base_url = str(data.get("base_url") or os.environ.get(
        "LLM_BASE_URL", "https://api.deepseek.com/v1")).strip()
    if not _is_allowed_base_url(base_url):
        return jsonify({"error": "base_url not allowed"}), 400
    # Server key only, and only to the allow-listed provider (audit S3: no
    # client-controlled URL, no client-supplied credential).
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        return jsonify({"error": "AI summarization is not configured on this server"}), 500

    user_msg = f"标题: {title}\n\n摘要: {abstract}"
    try:
        content = _llm_call(
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "user", "content": user_msg}],
            model, base_url, api_key, max_tokens=600,
        )
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        ai = _parse_json_lenient(content)
        return jsonify({"success": True, "result": ai})
    except Exception:
        # Never echo exception text to the caller (upstream errors can leak the
        # endpoint, key fragments, or internal paths). Full traceback goes to logs.
        app.logger.exception("summarize/paper failed (pmid=%s)", data.get("pmid", ""))
        return jsonify({"error": "AI summarization failed; see server logs"}), 500


@app.route("/literature/api/summarize/digest", methods=["POST"])
@require_api_token
def api_summarize_digest():
    """Generate AI narrative digest for a set of papers."""
    data, err = _read_json_body()
    if err:
        return err
    papers = data.get("papers", [])
    period = str(data.get("period", "周"))[:16]
    if not papers or not isinstance(papers, list):
        return jsonify({"error": "No papers provided"}), 400

    model = data.get("model") or os.environ.get("LLM_MODEL", "deepseek-v4-flash")
    base_url = str(data.get("base_url") or os.environ.get(
        "LLM_BASE_URL", "https://api.deepseek.com/v1")).strip()
    if not _is_allowed_base_url(base_url):
        return jsonify({"error": "base_url not allowed"}), 400
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        return jsonify({"error": "AI summarization is not configured on this server"}), 500

    try:
        result = summarize_digest(papers, period=period, model=model,
                                  base_url=base_url, api_key=api_key)
        return jsonify({"success": True, "result": result})
    except Exception:
        app.logger.exception("summarize/digest failed (%d papers)", len(papers))
        return jsonify({"error": "AI summarization failed; see server logs"}), 500


@app.route("/literature/<path:filename>")
def static_lit(filename):
    """Serve static assets (data files, JS, CSS) for the main literature page."""
    if filename.startswith("api/"):
        from flask import abort
        abort(404)
    return app.send_static_file(filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5003))
    app.run(host="0.0.0.0", port=port, debug=False)

