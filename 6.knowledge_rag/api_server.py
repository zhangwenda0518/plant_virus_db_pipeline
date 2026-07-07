#!/usr/bin/env python3
"""Plant Virus Knowledge RAG — Flask API + Web UI"""

import os, json, re, sys
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string
from retriever import get_kb, PlantVirusKnowledgeBase

app = Flask(__name__)
kb = None

def _init_kb():
    global kb
    if kb is None:
        base = Path(os.environ.get("KB_DIR", os.path.dirname(os.path.abspath(__file__))))
        kb = PlantVirusKnowledgeBase()
        kb.load_all(str(base))
    return kb

def _load_env():
    cfg = {}
    for p in [Path("/opt/plant_virus_db/.env"), Path(".env")]:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg

SYS_PROMPT = """You are a plant virus knowledge assistant. Answer based on the fragments below.
Rules: 1) Cite sources with [N] markers 2) Don't fabricate 3) Say "not found in database" if insufficient 4) Concise, under 200 words 5) Match the question's language"""

@app.route("/query", methods=["POST"])
def query():
    data = request.get_json(force=True)
    q = data.get("query", "").strip()
    if not q: return jsonify({"error": "query required"}), 400
    kb = _init_kb()
    results = kb.search(q, top_k=5) or kb.search_full_text(q, top_k=3)
    if not results:
        return jsonify({"answer": "No relevant information found in the knowledge base.", "sources": [], "query": q})
    fragments = [f"[{i}] [{r['source']}] {r['title']}\n{r['text'][:1500]}" for i, r in enumerate(results, 1)]
    ctx = "\n\n".join(fragments)
    env = _load_env()
    api_key = env.get("AI_API_KEY", "")
    api_url = env.get("AI_API_URL", "https://api.deepseek.com/v1/chat/completions")
    model = env.get("AI_MODEL", "deepseek-chat")
    user_key = data.get("api_key", "")
    if not api_key and not user_key:
        return jsonify({"answer": "API key not configured.", "sources": [{"title": r["title"], "source": r["source"]} for r in results], "fragments": fragments, "query": q})
    try:
        import requests
        r = requests.post(api_url, headers={"Authorization": f"Bearer {user_key or api_key}", "Content-Type": "application/json"}, json={"model": model, "messages": [{"role": "system", "content": SYS_PROMPT}, {"role": "user", "content": f"Fragments:\n\n{ctx}\n\nQuestion: {q}"}], "temperature": 0.3, "max_tokens": 600}, timeout=30)
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        answer = f"AI generation failed: {e}"
    return jsonify({"answer": answer, "sources": [{"title": r["title"], "source": r["source"]} for r in results], "query": q})

@app.route("/search", methods=["GET"])
def search():
    q = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 10)), 20)
    if not q: return jsonify({"error": "q required"}), 400
    kb = _init_kb()
    results = kb.search(q, top_k=limit) or kb.search_full_text(q, top_k=limit)
    return jsonify({"query": q, "count": len(results), "results": results})

@app.route("/stats", methods=["GET"])
def stats():
    kb = _init_kb()
    return jsonify({"total_docs": len(kb._docs), "sources": {"ICTV": sum(1 for d in kb._docs if d["source"] == "ICTV"), "DPV": sum(1 for d in kb._docs if d["source"] == "DPV"), "ViroidDB": sum(1 for d in kb._docs if d["source"] == "ViroidDB")}, "loaded": kb._loaded})

# Embedded HTML page
PAGE = r'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Plant Virus Knowledge Base</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"><style>
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;color:#333;margin:0}
nav{background:#1a5276;display:flex;align-items:center;padding:0 24px;height:52px;position:sticky;top:0;z-index:10}
nav a{color:rgba(255,255,255,.8);text-decoration:none;padding:14px 18px;font-size:14px;border-radius:6px 6px 0 0}
nav a:hover,nav .active{background:rgba(255,255,255,.15);color:#fff}
nav .brand{font-weight:700;font-size:16px;color:#fff;margin-right:8px;padding:0}
.hero{background:linear-gradient(135deg,#1a5276,#2e86c1);color:#fff;padding:32px 24px;margin-bottom:20px}
.hero h1{margin:0;font-size:22px}.hero p{margin:6px 0 0;opacity:.85;font-size:13px;max-width:700px}
.main{max-width:1200px;margin:0 auto;padding:0 16px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px}
.stat{background:#fff;padding:14px;border-radius:8px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.stat .val{font-size:22px;font-weight:700;color:#1a5276}.stat .lbl{font-size:11px;color:#888;margin-top:2px}
.sbar{display:flex;gap:10px;margin-bottom:18px}
.sbar input{flex:1;padding:12px 18px;border:2px solid #e0e0e0;border-radius:8px;font-size:15px;outline:none;transition:.2s}
.sbar input:focus{border-color:#2e86c1}
.sbar button{padding:12px 28px;background:#1a5276;color:#fff;border:none;border-radius:8px;font-size:15px;cursor:pointer;font-weight:500}
.sbar button:hover{background:#2e86c1}
.examples{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
.examples a{font-size:12px;color:#666;text-decoration:none;background:#fff;padding:5px 12px;border-radius:14px;border:1px solid #e0e0e0;transition:.2s}
.examples a:hover{background:#1a5276;color:#fff;border-color:#1a5276}
.grid{display:grid;grid-template-columns:1fr 380px;gap:20px;margin-bottom:24px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.r-card{background:#fff;border-radius:8px;padding:18px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.04);border-left:3px solid #2e86c1;transition:.2s}
.r-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.08)}
.r-title{font-size:15px;font-weight:600;color:#1a5276;margin-bottom:6px}
.r-meta{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.r-meta span{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:500}
.t-ictv{background:#e3f2fd;color:#1565c0}.t-dpv{background:#e8f5e9;color:#2e7d32}.t-vdb{background:#fce4ec;color:#c62828}
.t-fam{background:#f3e5f5;color:#6a1b9a}.t-gen{background:#e0f2f1;color:#00695c}.t-acr{background:#fff3e0;color:#e65100}
.r-text{font-size:13px;color:#555;line-height:1.6;max-height:100px;overflow:hidden}
.r-text.exp{max-height:none}
.r-tog{font-size:12px;color:#2e86c1;cursor:pointer;margin-top:6px;user-select:none}
.r-src{font-size:11px;color:#999;margin-bottom:6px}
.ai-panel{position:sticky;top:72px}
.ai-card{background:#fff;border-radius:8px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:16px}
.ai-card h3{font-size:15px;color:#1a5276;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #e8e8e8}
.ai-out{font-size:13px;line-height:1.7;color:#444;min-height:60px}
.ai-out .cit{color:#2e86c1;font-weight:500;cursor:help}
.ai-meta{font-size:11px;color:#999;margin-top:10px}
.ai-inp{display:flex;gap:6px}
.ai-inp input{flex:1;padding:8px 12px;border:1px solid #e0e0e0;border-radius:6px;font-size:13px;outline:none}
.ai-inp button{padding:8px 14px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:6px;font-size:13px;cursor:pointer;white-space:nowrap}
.emp{text-align:center;padding:60px 20px;color:#999}.emp .ic{font-size:48px;margin-bottom:12px}
footer{background:#1a5276;color:rgba(255,255,255,.7);text-align:center;padding:14px;margin-top:40px;font-size:12px}
footer a{color:rgba(255,255,255,.9)}
</style></head><body>
<nav><a class="brand" href="/knowledge/">Knowledge Base</a><a href="/reference/">Reference DB</a><a href="/primers/">Primers</a><a href="/explorer/">Explorer</a></nav>
<div class="hero"><h1>Plant Virus Knowledge Base</h1><p>ICTV (192) + DPV (363) + ViroidDB (9,691) &mdash; knowledge retrieval and AI-powered Q&A for plant virology research</p></div>
<div class="main">
<div class="stats"><div class="stat"><div class="val">{{total}}</div><div class="lbl">Documents</div></div><div class="stat"><div class="val">ICTV</div><div class="lbl">Taxonomy Reports</div></div><div class="stat"><div class="val">DPV</div><div class="lbl">Virus Descriptions</div></div></div>
<div class="sbar"><input id="q" placeholder="Search: Tobacco mosaic virus, Potyvirus, viroid, transmission..." onkeydown="if(event.key==='Enter')S()"><button onclick="S()">Search</button></div>
<div class="examples"><a href="javascript:Q('Tobacco mosaic virus transmission')">TMV transmission</a><a href="javascript:Q('Potyvirus host range and vector')">Potyvirus host & vector</a><a href="javascript:Q('viroid replication mechanism')">Viroid replication</a><a href="javascript:Q('Geminiviridae whitefly transmission')">Geminiviridae vector</a><a href="javascript:Q('Tobamovirus genome organization')">Tobamovirus genome</a></div>
<div class="grid">
<div id="R"><div class="emp" id="E"><div class="ic">&#128269;</div>Search the knowledge base above</div></div>
<div class="ai-panel">
<div class="ai-card"><h3>AI Q&A</h3><div id="AO" class="ai-out" style="color:#999">Ask about any plant virus &mdash; taxonomy, host range, transmission, symptoms, genome structure...</div><div class="ai-inp mt-3"><input id="AQ" placeholder="Ask a question..." onkeydown="if(event.key==='Enter')A()"><button onclick="A()">Ask</button></div></div>
<div class="ai-card" id="SC" style="display:none"><h3>Sources</h3><div id="SL" style="font-size:12px;color:#666"></div></div>
</div></div></div>
<footer>Plant Virus Knowledge Base | ICTV + DPV + ViroidDB | <a href="/reference/">Reference DB</a> &middot; <a href="/primers/">Primers</a> &middot; <a href="/explorer/">Explorer</a></footer>
<script>
function esc(t){return t.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>')}
async function S(){const q=document.getElementById('q').value.trim();if(!q)return;document.getElementById('E').style.display='none';document.getElementById('R').innerHTML='<div class="emp"><div class="spinner-border text-primary mb-2"></div><div>Searching...</div></div>';try{const r=await fetch('/knowledge/search?q='+encodeURIComponent(q)+'&limit=10');const d=await r.json();if(!d.results||!d.results.length){document.getElementById('R').innerHTML='<div class="emp"><div class="ic">&#128533;</div><div>No results for "'+q+'"</div></div>';return}let h='<h5 style="margin:0 0 14px;font-size:15px;color:#555">'+d.count+' results</h5>';d.results.forEach((r,i)=>{const s=r.text.substring(0,220);const more=r.text.length>220;let m='',st='';if(r.source==='ICTV')st='t-ictv';else if(r.source==='DPV')st='t-dpv';else st='t-vdb';if(r.fields){if(r.fields.Family)m+='<span class="t-fam">'+r.fields.Family+'</span>';if(r.fields.Genus)m+='<span class="t-gen">'+r.fields.Genus+'</span>';if(r.fields.Acronym)m+='<span class="t-acr">'+r.fields.Acronym+'</span>'}h+='<div class="r-card"><div class="r-src"><span class="'+st+'" style="padding:1px 6px;border-radius:3px;font-size:10px">'+r.source+'</span></div><div class="r-title">'+r.title+'</div>';if(m)h+='<div class="r-meta">'+m+'</div>';h+='<div class="r-text" id="t'+i+'">'+esc(s)+'</div>';if(more){h+='<span class="r-tog" onclick="T('+i+')" id="g'+i+'">Show more</span><div style="display:none" id="f'+i+'">'+esc(r.text.substring(220))+'</div>'}h+='</div>'});document.getElementById('R').innerHTML=h}catch(e){document.getElementById('R').innerHTML='<div class="emp"><div>Error: '+e.message+'</div></div>'}}
function T(i){const e=document.getElementById('t'+i),f=document.getElementById('f'+i),g=document.getElementById('g'+i);if(e.classList.contains('exp')){e.classList.remove('exp');e.style.maxHeight='100px';f.style.display='none';g.textContent='Show more'}else{e.classList.add('exp');e.style.maxHeight='none';f.style.display='block';g.textContent='Show less'}}
function Q(q){document.getElementById('q').value=q;S()}
async function A(){const q=document.getElementById('AQ').value.trim();if(!q)return;const o=document.getElementById('AO');o.innerHTML='<div class="spinner-border spinner-border-sm text-secondary"></div> Thinking...';try{const r=await fetch('/knowledge/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})});const d=await r.json();o.innerHTML=d.answer.replace(/\n/g,'<br>').replace(/\[(\d+)\]/g,'<span class="cit">[$1]</span>');if(d.sources&&d.sources.length){document.getElementById('SC').style.display='block';document.getElementById('SL').innerHTML=d.sources.map(s=>'<div style="margin:4px 0">['+s.source+'] '+s.title+'</div>').join('')}}catch(e){o.innerHTML='Error: '+e.message}}
</script></body></html>'''

@app.route("/")
def index():
    k = _init_kb()
    return render_template_string(PAGE, total=len(k._docs))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=False)
