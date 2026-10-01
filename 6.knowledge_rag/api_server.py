#!/usr/bin/env python3
"""Plant Virus Knowledge RAG — Flask API + Web UI"""

import os, json, re, sys, uuid, sqlite3
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, g
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


# ---- 会话历史（按浏览器 cookie 身份保存，SQLite 持久化）----
CHAT_DB = Path("/opt/plant_virus_db/knowledge_chats.db")


def _db():
    conn = sqlite3.connect(CHAT_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS conversations(
        id TEXT PRIMARY KEY, client_id TEXT NOT NULL,
        title TEXT, created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT NOT NULL,
        role TEXT NOT NULL, content TEXT NOT NULL,
        sources TEXT, created_at TEXT)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_conv_client
        ON conversations(client_id, created_at DESC)""")
    return conn


def _ensure_client():
    """匿名客户端身份：cookie pvdb_cid（比 IP 准——同一出口 IP 不会串）。"""
    cid = request.cookies.get("pvdb_cid")
    if not cid or len(cid) < 8:
        cid = uuid.uuid4().hex
        g.new_cid = cid
    return cid


@app.after_request
def _set_cid_cookie(resp):
    if getattr(g, "new_cid", None):
        resp.set_cookie("pvdb_cid", g.new_cid, max_age=10 * 365 * 24 * 3600, samesite="Lax")
    return resp


def _conv_owned(conv_id, cid):
    if not conv_id:
        return None
    conn = _db()
    row = conn.execute("SELECT id FROM conversations WHERE id=? AND client_id=?",
                       (conv_id, cid)).fetchone()
    conn.close()
    return row[0] if row else None


def _recent_messages(conv_id, limit=6):
    conn = _db()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE conv_id=? ORDER BY id DESC LIMIT ?",
        (conv_id, limit)).fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def _save_message(conv_id, role, content, sources=None):
    conn = _db()
    conn.execute(
        "INSERT INTO messages(conv_id, role, content, sources, created_at) VALUES(?,?,?,?,?)",
        (conv_id, role, content[:20000],
         json.dumps(sources, ensure_ascii=False) if sources else None,
         __import__("time").strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

SYS_PROMPT = """You are a plant virology expert assistant. Answer the question using ONLY the numbered fragments retrieved from the knowledge base (ICTV taxonomy reports, DPV virus descriptions, ViroidDB records, research paper abstracts, antiviral compound profiles).
Answer structure (be thorough and informative):
1) Direct answer — state the key fact(s) first, in 1-3 sentences.
2) Key details — expand with structured bullets covering all relevant aspects found in the fragments: taxonomy, host range, transmission (vector species, mode), symptoms, genome organization, detection methods, geographic distribution, control measures, affected crops — whichever the fragments support.
3) Mechanisms & evidence — where fragments give mechanisms, experimental results or numbers (efficacy, years, locations), include them with their citations.
4) Practical notes — if fragments mention detection or management options, summarize them.
Citation rules:
- Cite fragments with [N] markers, attaching each claim to the fragment(s) that support it.
- Cite accurately: attach [N] ONLY to claims that fragment directly supports — never attach citations to general background or filler statements the fragment does not specifically address.
- If the fragments do not contain part of what was asked, say explicitly what is missing — never fabricate.
Answer in the same language as the question (English question → English answer; 中文提问 → 中文回答). Keep scientific names in Latin. Length: aim for a comprehensive answer, typically 300-700 words when the fragments support it."""


@app.route("/query", methods=["POST"])
def query():
    data = request.get_json(force=True)
    q = data.get("query", "").strip()
    conv_id = (data.get("conversation_id") or "").strip()
    if not q: return jsonify({"error": "query required"}), 400
    kb = _init_kb()
    cid = _ensure_client()
    # 会话：无效/他人的 conv_id 一律视为新开会话
    if conv_id and not _conv_owned(conv_id, cid):
        conv_id = ""
    is_new = not conv_id
    if is_new:
        conv_id = uuid.uuid4().hex[:16]
        conn = _db()
        conn.execute("INSERT INTO conversations(id, client_id, title, created_at) VALUES(?,?,?,?)",
                     (conv_id, cid, q[:40], __import__("time").strftime("%Y-%m-%d %H:%M")))
        conn.commit(); conn.close()
    history = [] if is_new else _recent_messages(conv_id, 6)
    # 多轮追问：把上一条用户消息主题并入检索词（轻量 query rewrite），
    # 否则 "How is it transmitted?" 这类追问检索不到指代对象
    retrieval_q = q
    if history:
        last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        if last_user:
            retrieval_q = f"{last_user[:120]} {q}"
    results = kb.search(retrieval_q, top_k=8, per_doc_limit=2) or kb.search_full_text(retrieval_q, top_k=3)
    if not results:
        return jsonify({"answer": "No relevant information found in the knowledge base.", "sources": [], "query": q})
    def _frag_header(i, r):
        h = f"[{i}] [{r['source']}] {r['title']}"
        if r["source"] == "Papers":
            prov = []
            if r.get("year"): prov.append(r["year"])
            if r.get("doi"): prov.append(f"doi:{r['doi']}")
            elif r.get("pmid"): prov.append(f"PMID:{r['pmid']}")
            if prov: h += f" ({', '.join(prov)})"
        return h
    fragments = [f"{_frag_header(i, r)}\n{r['text'][:1200]}" for i, r in enumerate(results, 1)]
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
        msgs = [{"role": "system", "content": SYS_PROMPT}]
        for m in history:
            msgs.append({"role": "user" if m["role"] == "user" else "assistant",
                         "content": m["content"][:800]})
        msgs.append({"role": "user", "content": f"Fragments:\n\n{ctx}\n\nQuestion: {q}"})
        r = requests.post(api_url, headers={"Authorization": f"Bearer {user_key or api_key}", "Content-Type": "application/json"}, json={"model": model, "messages": msgs, "temperature": 0.2, "max_tokens": 2500, "stream": False}, timeout=150)
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        answer = f"AI generation failed: {e}"
    _save_message(conv_id, "user", q)
    # sources: 按 (source, title) 去重，保持检索顺序；文献带 DOI 链接
    seen, sources = set(), []
    for r in results:
        key = (r["source"], r["title"])
        if key not in seen:
            seen.add(key)
            s = {"title": r["title"], "source": r["source"]}
            if r.get("doi"):
                s["url"] = f"https://doi.org/{r['doi']}"
            elif r.get("pmid"):
                s["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/"
            if r.get("year"):
                s["year"] = r["year"]
            sources.append(s)
    _save_message(conv_id, "assistant", answer, sources)
    return jsonify({"answer": answer, "sources": sources,
                    "fragments": fragments, "query": q,
                    "conversation_id": conv_id})


# ---- 会话历史 API ----
@app.route("/conversations", methods=["GET"])
def conversations_list():
    cid = _ensure_client()
    conn = _db()
    rows = conn.execute(
        """SELECT c.id, c.title, c.created_at, COUNT(m.id) n
           FROM conversations c LEFT JOIN messages m ON m.conv_id = c.id
           WHERE c.client_id = ? GROUP BY c.id
           ORDER BY c.created_at DESC LIMIT 30""", (cid,)).fetchall()
    conn.close()
    return jsonify({"conversations": [
        {"id": r[0], "title": r[1], "created_at": r[2], "messages": r[3]} for r in rows]})


@app.route("/conversations/<conv_id>", methods=["GET"])
def conversations_get(conv_id):
    cid = _ensure_client()
    if not _conv_owned(conv_id, cid):
        return jsonify({"error": "not found"}), 404
    conn = _db()
    msgs = conn.execute(
        "SELECT role, content, sources FROM messages WHERE conv_id=? ORDER BY id",
        (conv_id,)).fetchall()
    conn.close()
    return jsonify({"id": conv_id, "messages": [
        {"role": r, "content": c, "sources": json.loads(s) if s else None}
        for r, c, s in msgs]})


@app.route("/conversations/<conv_id>", methods=["DELETE"])
def conversations_delete(conv_id):
    cid = _ensure_client()
    if not _conv_owned(conv_id, cid):
        return jsonify({"error": "not found"}), 404
    conn = _db()
    conn.execute("DELETE FROM messages WHERE conv_id=?", (conv_id,))
    conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit(); conn.close()
    return jsonify({"deleted": True})

@app.route("/search", methods=["GET"])
def search():
    q = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 10)), 20)
    if not q: return jsonify({"error": "q required"}), 400
    kb = _init_kb()
    passages = kb.search(q, top_k=24, per_doc_limit=2) or kb.search_full_text(q, top_k=limit)
    # 段落聚合回文档级（保留最佳段落文本）
    agg, order = {}, []
    for p in passages:
        if "doc_id" not in p:  # search_full_text 兜底结果
            order.append(p)
            continue
        key = (p["source"], p["title"])
        if key not in agg:
            item = {"title": p["title"], "source": p["source"], "text": p["text"],
                    "fields": p.get("fields"), "score": p["score"]}
            for extra in ("doi", "pmid", "year"):
                if p.get(extra):
                    item[extra] = p[extra]
            if item.get("doi"):
                item["url"] = f"https://doi.org/{item['doi']}"
            elif item.get("pmid"):
                item["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{item['pmid']}/"
            agg[key] = item
            order.append(item)
        else:
            agg[key]["score"] = max(agg[key]["score"], p["score"])
    results = order[:limit]
    return jsonify({"query": q, "count": len(results), "results": results})

@app.route("/stats", methods=["GET"])
def stats():
    kb = _init_kb()
    return jsonify({"total_docs": len(kb._docs), "sources": {"ICTV": sum(1 for d in kb._docs if d["source"] == "ICTV"), "DPV": sum(1 for d in kb._docs if d["source"] == "DPV"), "ViroidDB": sum(1 for d in kb._docs if d["source"] == "ViroidDB"), "Papers": sum(1 for d in kb._docs if d["source"] == "Papers"), "Antivirals": sum(1 for d in kb._docs if d["source"] == "Antivirals")}, "loaded": kb._loaded})

# Embedded HTML page
PAGE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Plant Virus Knowledge Base</title><link href="/lib/bootstrap.min.css" rel="stylesheet"><style>
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;color:#333;margin:0}
nav{background:#1a5276;display:flex;align-items:center;padding:0 12px;height:52px;position:sticky;top:0;z-index:10;white-space:nowrap;overflow-x:auto}
nav a{color:rgba(255,255,255,.8);text-decoration:none;padding:14px 10px;font-size:13px;border-radius:6px 6px 0 0;white-space:nowrap}
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
.t-ictv{background:#e3f2fd;color:#1565c0}.t-dpv{background:#e8f5e9;color:#2e7d32}.t-vdb{background:#fce4ec;color:#c62828}.t-pap{background:#fff8e1;color:#b26a00}
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
.convlist{display:flex;gap:6px;overflow-x:auto;padding:0 0 8px;font-size:11px}
.conv-chip{flex:0 0 auto;background:#eef5fb;border:1px solid #d7e7f4;border-radius:12px;padding:3px 10px;cursor:pointer;color:#1a5276;max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.conv-chip:hover{background:#d7e7f4}
.conv-chip b{color:#c62828;cursor:pointer;margin-left:4px}
.newchat{font-size:11px;padding:3px 12px;border-radius:12px;border:1px solid #1a5276;background:#fff;color:#1a5276;cursor:pointer;white-space:nowrap}
.newchat:hover{background:#eaf2f8}
#AO .m-user{background:#1a5276;color:#fff;margin-left:auto}
#AO .m-ai{background:#eaf2f8;color:#333}
#AO .m-user,#AO .m-ai{padding:7px 11px;border-radius:10px;font-size:13px;line-height:1.55;max-width:92%;margin:4px 0;word-break:break-word}
.emp{text-align:center;padding:60px 20px;color:#999}.emp .ic{font-size:48px;margin-bottom:12px}
footer{background:#1a5276;color:rgba(255,255,255,.7);text-align:center;padding:14px;margin-top:40px;font-size:12px}
footer a{color:rgba(255,255,255,.9)}
</style></head><body>
<nav><a class="brand" href="/">Plant Virus DB</a><a href="/reference/">Reference</a>
  <a href="/virus/">Virus Profile</a><a href="/photos/">Photos</a><a href="/vector/">Vector</a><a href="/eve/">EVE</a><a href="/genes/">Genes</a><a href="/primers/">Primers</a><a href="/onekp/">OneKP</a><a href="/explorer/">Explorer</a><a href="/metabuli/">Metabuli</a><a href="/pamirdb/">PV-miRNA</a><a href="/literature/">Literature</a><a href="/knowledge/" style="color:#fff;font-weight:600">Knowledge</a><a href="/resources.html">Resources</a><a href="/help/">Help</a></nav>
<div class="hero"><h1>Plant Virus Knowledge Base</h1><p>ICTV (192) + DPV (363) + ViroidDB (9,691) + Literature ({{papers}} papers w/ abstracts) &mdash; knowledge retrieval and AI-powered Q&amp;A for plant virology research</p></div>
<div class="main">
<div class="stats"><div class="stat"><div class="val">{{total}}</div><div class="lbl">Documents</div></div><div class="stat"><div class="val">{{papers}}</div><div class="lbl">Research Papers</div></div><div class="stat"><div class="val">ICTV+DPV</div><div class="lbl">Taxonomy &amp; Descriptions</div></div></div>
<div class="sbar"><input id="q" placeholder="Search: Tobacco mosaic virus, Potyvirus, viroid, transmission..." onkeydown="if(event.key==='Enter')S()"><button onclick="S()">Search</button></div>
<div class="examples"><a href="javascript:Q('Tobacco mosaic virus transmission')">TMV transmission</a><a href="javascript:Q('Potyvirus host range and vector')">Potyvirus host & vector</a><a href="javascript:Q('viroid replication mechanism')">Viroid replication</a><a href="javascript:Q('Geminiviridae whitefly transmission')">Geminiviridae vector</a><a href="javascript:Q('RT-RPA detection rice virus')">RT-RPA rice virus detection</a><a href="javascript:Q('recombinase polymerase assay plant virus')">RPA assays</a></div>
<div class="grid">
<div id="R"><div class="emp" id="E"><div class="ic">&#128269;</div>Search the knowledge base above</div></div>
<div class="ai-panel">
<div class="ai-card"><h3 style="display:flex;justify-content:space-between;align-items:center">AI Q&amp;A <button class="newchat" onclick="newChat()">+ New chat</button></h3><div class="convlist" id="convList"><span style="color:#aaa">Loading history...</span></div><div id="AO" class="ai-out" style="min-height:110px;max-height:430px;overflow-y:auto;color:#999">Ask about any plant virus &mdash; taxonomy, host range, transmission, symptoms, genome structure... History is saved in your browser.</div><div class="ai-inp mt-3"><input id="AQ" placeholder="Ask a question..." onkeydown="if(event.key==='Enter')A()"><button onclick="A()">Ask</button></div></div>
<div class="ai-card" id="SC" style="display:none"><h3>Sources</h3><div id="SL" style="font-size:12px;color:#666"></div></div>
</div></div></div>
<footer>Plant Virus Knowledge Base | ICTV + DPV + ViroidDB | <a href="/reference/">Reference DB</a> &middot; <a href="/primers/">Primers</a> &middot; <a href="/explorer/">Explorer</a></footer>
<script>
function esc(t){return t.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>')}
async function S(){const q=document.getElementById('q').value.trim();if(!q)return;document.getElementById('E').style.display='none';document.getElementById('R').innerHTML='<div class="emp"><div class="spinner-border text-primary mb-2"></div><div>Searching...</div></div>';try{const r=await fetch('/knowledge/search?q='+encodeURIComponent(q)+'&limit=10');const d=await r.json();if(!d.results||!d.results.length){document.getElementById('R').innerHTML='<div class="emp"><div class="ic">&#128533;</div><div>No results for "'+q+'"</div></div>';return}let h='<h5 style="margin:0 0 14px;font-size:15px;color:#555">'+d.count+' results</h5>';d.results.forEach((r,i)=>{const s=r.text.substring(0,220);const more=r.text.length>220;let m='',st='';if(r.source==='ICTV')st='t-ictv';else if(r.source==='DPV')st='t-dpv';else if(r.source==='Papers')st='t-pap';else st='t-vdb';if(r.fields){if(r.fields.Family)m+='<span class="t-fam">'+r.fields.Family+'</span>';if(r.fields.Genus)m+='<span class="t-gen">'+r.fields.Genus+'</span>';if(r.fields.Acronym)m+='<span class="t-acr">'+r.fields.Acronym+'</span>'}if(r.source==='Papers'&&r.year)m+='<span class="t-pap">'+r.year+'</span>';h+='<div class="r-card"><div class="r-src"><span class="'+st+'" style="padding:1px 6px;border-radius:3px;font-size:10px">'+r.source+'</span>'+(r.source==='Papers'?' <span style="font-size:11px;color:#999">'+(r.url?'<a href="'+r.url+'" target="_blank" style="color:#2e86c1">'+(r.doi||r.pmid||'source')+'</a> ':'' )+'</span>':'')+'</div><div class="r-title">'+(r.source==='Papers'?esc(r.title):r.title)+'</div>';if(m)h+='<div class="r-meta">'+m+'</div>';h+='<div class="r-text" id="t'+i+'">'+esc(s)+'</div>';if(more){h+='<span class="r-tog" onclick="T('+i+')" id="g'+i+'">Show more</span><div style="display:none" id="f'+i+'">'+esc(r.text.substring(220))+'</div>'}h+='</div>'});document.getElementById('R').innerHTML=h}catch(e){document.getElementById('R').innerHTML='<div class="emp"><div>Error: '+e.message+'</div></div>'}}
function T(i){const e=document.getElementById('t'+i),f=document.getElementById('f'+i),g=document.getElementById('g'+i);if(e.classList.contains('exp')){e.classList.remove('exp');e.style.maxHeight='100px';f.style.display='none';g.textContent='Show more'}else{e.classList.add('exp');e.style.maxHeight='none';f.style.display='block';g.textContent='Show less'}}
function Q(q){document.getElementById('q').value=q;S()}
var CONV_ID=null,MSGS=[];
function mdLite(t){return String(t).replace(/^#{1,6}\s*(.+)$/gm,'<b>$1</b>').replace(/^#{1,6}\s*/gm,'').replace(/\*\*([^*]+)\*\*/g,'$1').replace(/(^|\n)[-*]\s/g,'$1&#8226; ')}
function renderThread(){const o=document.getElementById('AO');if(!MSGS.length){o.innerHTML='<span style="color:#999">Ask about any plant virus &mdash; taxonomy, host range, transmission, symptoms, genome structure... History is saved in your browser.</span>';return}o.innerHTML=MSGS.map(m=>'<div class="'+(m.role==='user'?'m-user':'m-ai')+'">'+(m.role==='user'?esc(m.content):mdLite(m.content).replace(/\[(\d+)\]/g,'<span class="cit">[$1]</span>'))+'</div>').join('');o.scrollTop=o.scrollHeight}
function showSourcesL(sources){if(!sources||!sources.length)return;document.getElementById('SC').style.display='block';document.getElementById('SL').innerHTML=sources.map(s=>'<div style="margin:4px 0">['+s.source+'] '+esc(s.title)+(s.url?' <a href="'+s.url+'" target="_blank" style="color:#2e86c1;font-size:11px">'+(s.year?s.year+' ':'')+'source</a>':'')+'</div>').join('')}
function refreshConvs(){fetch('/knowledge/conversations').then(r=>r.json()).then(d=>{const list=d.conversations||[];document.getElementById('convList').innerHTML=list.length?list.map(c=>'<span class="conv-chip" onclick="loadConv(\''+c.id+'\')" title="'+esc(c.title)+'">'+esc(c.title.length>18?c.title.slice(0,18)+'…':c.title)+'<b onclick="event.stopPropagation();delConv(\''+c.id+'\')">×</b></span>').join(''):'<span style="color:#aaa">No history yet</span>'}).catch(function(){})}
function newChat(){CONV_ID=null;MSGS=[];renderThread()}
function loadConv(id){fetch('/knowledge/conversations/'+id).then(r=>r.json()).then(d=>{if(d.error)return;CONV_ID=id;MSGS=(d.messages||[]).map(m=>({role:m.role,content:m.content}));renderThread();const last=[...(d.messages||[])].reverse().find(m=>m.sources);if(last)showSourcesL(last.sources)}).catch(function(){})}
function delConv(id){fetch('/knowledge/conversations/'+id,{method:'DELETE'}).then(function(){refreshConvs();if(CONV_ID===id){CONV_ID=null;MSGS=[];renderThread()}}).catch(function(){})}
refreshConvs();
async function A(){const q=document.getElementById('AQ').value.trim();if(!q)return;document.getElementById('AQ').value='';MSGS.push({role:'user',content:q});renderThread();const o=document.getElementById('AO');o.scrollTop=o.scrollHeight;try{const r=await fetch('/knowledge/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,conversation_id:CONV_ID})});const d=await r.json();CONV_ID=d.conversation_id||CONV_ID;MSGS.push({role:'assistant',content:d.answer});renderThread();if(d.sources&&d.sources.length)showSourcesL(d.sources);refreshConvs()}catch(e){MSGS.push({role:'assistant',content:'Error: '+e.message});renderThread()}}
</script></body></html>'''

@app.route("/")
def index():
    k = _init_kb()
    return render_template_string(PAGE, total=len(k._docs),
                                  papers=sum(1 for d in k._docs if d["source"] == "Papers"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=False)
