#!/usr/bin/env python3
"""
Step 5: Plant Virus Primer Database Web Interface
========================================================================
基于 Flask 的 Web 应用，提供:

  功能:
    1. 首页 — 数据库概览 + 快速搜索
    2. 搜索页 — 按Species/属/科/类型/Score搜索引物
    3. Species详情页 — 某Species的所有引物 (含验证信息)
    4. 引物详情页 — 单对引物的完整信息 (序列/探针/验证)
    5. 批量下载 — 导出 FASTA/CSV
    6. API — JSON 接口供外部调用

  技术栈:
    - Flask (Web 框架)
    - SQLite (数据存储)
    - Jinja2 (模板引擎, 内嵌 HTML)
    - Bootstrap 5 (CSS, CDN 加载)

启动:
  python step5_web_server.py
  # 浏览器打开 http://localhost:5000

生产部署:
  gunicorn -w 4 -b 0.0.0.0:5000 step5_web_server:app
"""

import argparse
import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

# ______________________________________________________________________
DB_PATH = Path("primer_database.db")

# 加载服务器端 AI 配置 (不暴露给前端)
def _load_env(paths=None):
    if paths is None:
        paths = [Path("/opt/plant_virus_db/.env"), Path(".env")]
    cfg = {}
    for p in paths:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg

SERVER_AI_CONFIG = _load_env()

# 加载 ICTV 名称映射表 (内存缓存，避免每次请求读文件)
NAME_MAP = {}
_name_map_candidates = (
    Path("/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/name_mapping.tsv"),
    Path(__file__).resolve().parent.parent / "docs" / "data" / "name_mapping.tsv",
)
_name_map_path = next((p for p in _name_map_candidates if p.exists()), None)
if _name_map_path:
    import csv as _csv
    with open(_name_map_path, encoding='utf-8') as f:
        for row in _csv.DictReader(f, delimiter='\t'):
            NAME_MAP[row.get('Lookup_Key', '')] = {
                'ICTV_Name': row.get('ICTV_Name', ''),
                'Common_Name': row.get('Common_Name', ''),
                'Abbreviation': row.get('Abbreviation', '')
            }
    print(f"Loaded {len(NAME_MAP)} name mappings into memory")

def _expand_search_terms(query):
    """将搜索词扩展为 [原始词, ICTV名, 通用名, 缩写]"""
    terms = [query]
    ql = query.lower().strip()
    if ql in NAME_MAP:
        m = NAME_MAP[ql]
        for k in ('ICTV_Name', 'Common_Name', 'Abbreviation'):
            v = m.get(k, '').strip()
            if v and v.lower() != ql and v not in terms:
                terms.append(v)
    return terms

# ── /api/chat AI 助手：物种别名词典 + 站点事实表 + 本机 RAG 接口 ──
SPECIES_ALIASES = None   # 延迟构建: {小写别名: ICTV 规范名}


def _build_species_aliases():
    global SPECIES_ALIASES
    if SPECIES_ALIASES is None:
        aliases = {}
        for row in NAME_MAP.values():
            canon = (row.get('ICTV_Name') or '').strip()
            if not canon:
                continue
            for v in (canon, (row.get('Common_Name') or '').strip(),
                      (row.get('Abbreviation') or '').strip()):
                key = v.lower()
                if len(key) < 3:
                    continue
                lst = aliases.setdefault(key, [])
                if canon not in lst:
                    lst.append(canon)
        SPECIES_ALIASES = aliases
    return SPECIES_ALIASES


def _extract_species_from_message(msg, max_species=5):
    """扫描消息里的物种名（拉丁名/通用名/缩写），n-gram 最长匹配优先。
    返回 [(ICTV规范名, 用户原文)]；一个缩写对应多个物种时全部返回（如 CMV），
    交由后续 DB 记录与 LLM 消歧。与触发词/语序无关，中英文均可。"""
    import re as _re
    aliases = _build_species_aliases()
    if not aliases:
        return []
    tokens = _re.findall(r"[A-Za-z0-9][A-Za-z0-9\-']*", msg)  # 首字符允许数字：Coptis virus 1 等名字以数字结尾
    low = [t.lower() for t in tokens]
    n = len(low)
    found, seen, i = [], set(), 0
    while i < n:
        hit = None
        for w in range(min(6, n - i), 0, -1):
            canons = aliases.get(' '.join(low[i:i + w]))
            if canons:
                hit = (w, canons)
                break
        if hit is None:
            i += 1
            continue
        w, canons = hit
        for canon in canons:
            if canon not in seen:
                seen.add(canon)
                found.append((canon, ' '.join(tokens[i:i + w])))
                if len(found) >= max_species:
                    break
        i += w
    return found


# 站点事实表（explorer / reference_db 分支用的真实数字，~7KB，随进程常驻）
SITE_FACTS = {}
for _facts_path in (Path("/opt/plant_virus_db/plant_virus_db_pipeline/docs/data/dashboard_stats.json"),
                    Path(__file__).resolve().parent.parent / "docs" / "data" / "dashboard_stats.json"):
    if _facts_path.exists():
        try:
            SITE_FACTS = json.loads(_facts_path.read_text(encoding='utf-8'))
            break
        except Exception:
            pass

# 本机知识库 RAG 检索接口（explorer / reference_db 分支接地用，纯检索不花 LLM）
KB_SEARCH_URL = SERVER_AI_CONFIG.get('KB_SEARCH_URL', 'http://127.0.0.1:5002/search')


# ── 跨库取数：媒介-宿主库（8.plant-insect）+ 症状照片库（docs/data）──
def _pipeline_candidates(rel):
    return (Path("/opt/plant_virus_db/plant_virus_db_pipeline") / rel,
            Path(__file__).resolve().parent.parent / rel)

_VECTOR_INDEX = None
_PHOTO_INDEX = None
_SYMPTOM_INDEX = None


def _bridge_canonical(name):
    """俗名/别名 → ICTV 规范名（走别名词典，取首个命中）。"""
    lst = _build_species_aliases().get((name or '').strip().lower())
    return lst[0] if lst else None


def _canon_of(name):
    """词典直接命中失败时退回 n-gram 扫描（如 'Alfamovirus AMV' → AMV → Alfalfa mosaic virus）。"""
    canon = _bridge_canonical(name)
    if canon:
        return canon
    ext = _extract_species_from_message(name or '', 1)
    return ext[0][0] if ext else None


def _build_vector_index():
    global _VECTOR_INDEX
    if _VECTOR_INDEX is None:
        _VECTOR_INDEX = {}
        for p in _pipeline_candidates("8.plant-insect/virus_vector_merged.json"):
            if not p.exists():
                continue
            try:
                d = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                continue
            for v in d.get('viruses') or []:
                names = [v.get('ictv_name') or '', v.get('canonical_name') or '']
                names += list(v.get('matched_names') or [])
                for nm in names:
                    canon = _bridge_canonical(nm)
                    if canon:
                        _VECTOR_INDEX.setdefault(canon, v)
            break
    return _VECTOR_INDEX


def _build_media_indexes():
    global _PHOTO_INDEX, _SYMPTOM_INDEX
    if _PHOTO_INDEX is not None:
        return
    _PHOTO_INDEX, _SYMPTOM_INDEX = {}, {}
    for p in _pipeline_candidates("docs/data/unified_gallery.json"):
        if p.exists():
            try:
                items = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                items = []
            for it in items or []:
                canon = _canon_of((it.get('virus_ictv') or '') or (it.get('virus') or ''))
                if not canon:
                    continue
                lst = _PHOTO_INDEX.setdefault(canon, [])
                if len(lst) < 3:
                    lst.append({'thumb': (it.get('thumb') or '').strip(),
                                'full': (it.get('full') or '').strip(),
                                'caption': (it.get('capt') or it.get('caption') or '').strip()[:120]})
            break
    for p in _pipeline_candidates("docs/data/symptom_table.json"):
        if p.exists():
            try:
                items = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                items = []
            for it in items or []:
                canon = _canon_of(it.get('virus') or '')
                s = (it.get('symptoms_std') or it.get('symptoms') or '').strip()
                if not canon or not s:
                    continue
                host = (it.get('host_latin') or '').strip()
                entry = s + ((' (host: ' + host + ')') if host else '')
                lst = _SYMPTOM_INDEX.setdefault(canon, [])
                if entry not in lst and len(lst) < 4:
                    lst.append(entry)
            break


def _cross_db_info(canons, base, zh=False):
    """媒介-宿主 + 症状照片 + 站内深链，一次取齐供 AI 回填。"""
    import re as _re
    from urllib.parse import quote as _q
    vidx = _build_vector_index()
    _build_media_indexes()
    lines = []
    for c in canons[:3]:
        v = vidx.get(c)
        if v:
            vectors, modes, hosts, dois = [], [], [], []
            for r in (v.get('relationships') or [])[:10]:
                for key, bag, cap in (('vector', vectors, 6), ('host', hosts, 5)):
                    val = (r.get(key) or '').strip()
                    if val and val not in bag and len(bag) < cap:
                        bag.append(val)
                m = (r.get('transmission_mode') or r.get('transmission_category') or '').strip()
                if m and m not in modes and len(modes) < 3:
                    modes.append(m)
                for dk in ('doi_insect', 'doi_transmission'):
                    for one in _re.split(r'[;；,，\s]+', (r.get(dk) or '').strip()):
                        if one.startswith('http') and one not in dois and len(dois) < 2:
                            dois.append(one)
            seg = f"- {'媒介-宿主库' if zh else 'Vector-host DB'} | {c}"
            ictv = (v.get('ictv_name') or '').strip()
            if ictv and ictv != c:
                seg += f" ({ictv})"
            lines.append(seg + ":")
            if vectors:
                lines.append(f"  {'传播介体' if zh else 'vectors'}: {'; '.join(vectors)}")
            if modes:
                lines.append(f"  {'传播方式' if zh else 'transmission'}: {'; '.join(modes)}")
            if hosts:
                lines.append(f"  {'宿主(部分)' if zh else 'hosts (examples)'}: {'; '.join(hosts)}")
            if dois:
                lines.append(f"  {'证据' if zh else 'evidence'}: {'; '.join(dois)}")
        photos = _PHOTO_INDEX.get(c) or []
        sympt = _SYMPTOM_INDEX.get(c) or []
        if photos or sympt:
            lines.append(f"- {'症状照片库' if zh else 'Symptom records'} | {c}:")
            for ph in photos[:2]:
                url = ph['thumb']
                if url and not url.startswith('http'):
                    url = base + '/' + url.lstrip('/')
                if url:
                    lines.append(f"  {'照片' if zh else 'photo'}: {url}"
                                 + (f" ({ph['caption']})" if ph['caption'] else ''))
            if sympt:
                lines.append(f"  {'典型症状' if zh else 'typical symptoms'}: {' | '.join(sympt[:3])}")
    if canons:
        q = _q(canons[0])
        links = [('引物检索', 'Primers search', f'{base}/primers/search?q={q}'),
                 ('物种页', 'Species page', f'{base}/species/{q}'),
                 ('时空探索器', 'Explorer profile', f'{base}/explorer/?profile={q}'),
                 ('媒介库', 'Vector-host DB', f'{base}/vector/'),
                 ('症状照片', 'Symptom photos', f'{base}/photos/'),
                 ('知识库', 'Knowledge base', f'{base}/knowledge/')]
        if zh:
            lines.append("- 站内深链（回答末尾请附“相关页面直达：”一节，逐字列出以下网址）:")
            lines += [f"  {a}: {u}" for a, _, u in links]
        else:
            lines.append("- Deep links (end your reply with a 'Relevant pages:' section quoting these URLs verbatim):")
            lines += [f"  {b}: {u}" for _, b, u in links]
    if not lines:
        return ""
    head = ("\n\n【跨库记录——请与引物/知识数据一并引用】:\n" if zh
            else "\n\n[Cross-database records — cite these alongside the primers/knowledge data]:\n")
    return head + "\n".join(lines) + "\n"


# Flask 可能未安装
try:
    from flask import Flask, request, jsonify, render_template_string, g, send_file
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# Primer design service (optional, falls back gracefully)
try:
    from primer_design_service import DesignJobManager
    DESIGN_SERVICE_AVAILABLE = True
except ImportError:
    DESIGN_SERVICE_AVAILABLE = False


# ======================================================================
# HTML 模板 (内嵌, 无需外部模板文件)
# ======================================================================

BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Plant Virus Primer Database{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        body { padding-top: 60px; background-color: #f8f9fa; }
        .navbar-brand { font-weight: bold; }
        .primer-seq { font-family: 'Courier New', monospace; font-size: 14px;
                      background: #e9ecef; padding: 4px 8px; border-radius: 4px;
                      word-break: break-all; }
        .score-badge { font-weight: bold; }
        .card-stat { text-align: center; padding: 20px; }
        .card-stat .number { font-size: 2.5em; font-weight: bold; }
        .recommended { color: #198754; }
        .usable { color: #ffc107; }
        .caution { color: #fd7e14; }
        .not-recommended { color: #dc3545; }
        .search-highlight { background-color: #fff3cd; }
        .table-primer td { vertical-align: middle; }
        .copy-btn { cursor: pointer; font-size: 12px; }
        .probe-seq { font-family: 'Courier New', monospace; font-size: 13px;
                     background: #d1ecf1; padding: 3px 6px; border-radius: 4px; }
        #ai-chat-btn {position:fixed;bottom:24px;right:24px;width:48px;height:48px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:50%;font-size:20px;cursor:pointer;z-index:9999;box-shadow:0 4px 12px rgba(102,126,234,.4);transition:transform .2s}
        #ai-chat-btn:hover {transform:scale(1.1)}
        #ai-chat-panel {position:fixed;bottom:84px;right:24px;width:420px;max-height:560px;background:#fff;border:1px solid #dee2e6;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.15);z-index:9998;display:none;flex-direction:column}
        .chat-header {display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid #eee;border-radius:12px 12px 0 0;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;font-weight:600;font-size:14px}
        .chat-header button {background:none;border:none;color:#fff;font-size:18px;cursor:pointer}
        .chat-msgs {flex:1;overflow-y:auto;padding:12px;max-height:380px}
        .chat-msg {margin:6px 0;padding:8px 12px;border-radius:10px;font-size:13px;line-height:1.5;max-width:85%;word-break:break-word}
        .chat-msg.user {background:#667eea;color:#fff;margin-left:auto}
        .chat-msg.ai {background:#f0f0f5;color:#333}
        .chat-msg.system {background:#fff3cd;color:#856404;text-align:center;max-width:100%;font-size:11px}
        .chat-input-row {display:flex;gap:8px;padding:10px 12px;border-top:1px solid #eee}
        .chat-input-row input {flex:1;padding:8px 12px;border:1px solid #dee2e6;border-radius:20px;font-size:13px;outline:none}
        .chat-input-row button {padding:6px 16px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:20px;font-size:13px;cursor:pointer}
        #ai-settings-inline input {outline:none}
        .ai-typing {display:flex;gap:4px;padding:8px 12px}
        .ai-typing span {width:6px;height:6px;background:#999;border-radius:50%;animation:aiBounce 1.4s infinite ease-in-out}
        .ai-typing span:nth-child(2) {animation-delay:.2s}
        .ai-typing span:nth-child(3) {animation-delay:.4s}
        @keyframes aiBounce {0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}
        .preset-qs {display:flex;flex-wrap:wrap;gap:4px;padding:6px 10px;border-bottom:1px solid #eee;background:#fafafa}
        .preset-q {background:#fff;border:1px solid #dee2e6;border-radius:14px;padding:3px 10px;font-size:11px;cursor:pointer;color:#555;white-space:nowrap;max-width:180px;overflow:hidden;text-overflow:ellipsis;transition:all .2s}
        .preset-q:hover {background:#667eea;color:#fff;border-color:#667eea}
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
        <div class="container">
            <a class="navbar-brand" href="/">
                Plant Virus DB
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                                                <ul class="navbar-nav ms-auto">
                    <li class="nav-item"><a class="nav-link" href="/reference/">Reference</a></li>
                    <li class="nav-item"><a class="nav-link" href="/photos/">Photos</a></li>
                    <li class="nav-item"><a class="nav-link" href="/vector/">Vector</a></li>
                    <li class="nav-item"><a class="nav-link" href="/te/">TE & EVE</a></li>
                    <li class="nav-item"><a class="nav-link" href="/genes/">Genes</a></li>
                    <li class="nav-item"><a class="nav-link active" href="/primers/">Primers</a></li>
                    <li class="nav-item"><a class="nav-link" href="/onekp/">OneKP</a></li>
                    <li class="nav-item"><span class="nav-link sep-nav">|</span></li>
                    <li class="nav-item"><a class="nav-link" href="/explorer/">Explorer</a></li>
                    <li class="nav-item"><a class="nav-link" href="/metabuli/">Metabuli</a></li>
                    <li class="nav-item"><a class="nav-link" href="/pamirdb/">PV-miRNA</a></li>
                    <li class="nav-item"><span class="nav-link sep-nav">|</span></li>
                    <li class="nav-item"><a class="nav-link" href="/literature/">Literature</a></li>
                    <li class="nav-item"><a class="nav-link" href="/knowledge/">Knowledge</a></li>
                    <li class="nav-item"><a class="nav-link" href="/resources.html">Resources</a></li>
                    <li class="nav-item"><a class="nav-link" href="/help/">Help</a></li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container">
        {% block content %}{% endblock %}
    </div>

    <footer class="bg-dark text-white mt-5 py-3">
        <div class="container text-center">
            <small>Plant Virus Primer Database &copy; {{ year }}
            &nbsp;|&nbsp; Powered by AutoPVPrimer + Primer3 + varVAMP
            &nbsp;|&nbsp; <a href="/api/" class="text-white-50">API</a></small>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(function() {
                alert('Copied!');
            });
        }
    </script>
    {% block scripts %}{% endblock %}
    <!-- AI Chat -->
    <button id="ai-chat-btn" onclick="toggleChat()" title="AI Assistant">?</button>
    <div id="ai-chat-panel">
        <div class="chat-header"><span>PrimerDB AI Assistant</span><div><button onclick="toggleSettings()" style="background:none;border:none;color:#fff;font-size:14px;cursor:pointer;margin-right:8px" title="Settings">⚙</button><button onclick="toggleChat()">×</button></div></div>
        <div id="ai-settings-inline" style="display:none;padding:10px 12px;border-bottom:1px solid #eee;background:#f8f9fa">
            <div style="display:flex;gap:6px;flex-wrap:wrap">
                <input id="ai-api-key" type="password" placeholder="API Key (sk-...)" style="flex:1;min-width:120px;padding:5px 8px;border:1px solid #dee2e6;border-radius:4px;font-size:11px">
                <input id="ai-model" value="deepseek-chat" style="width:120px;padding:5px 8px;border:1px solid #dee2e6;border-radius:4px;font-size:11px">
                <button onclick="saveAISettings()" style="padding:5px 10px;background:#667eea;color:#fff;border:none;border-radius:4px;font-size:11px;cursor:pointer">Save</button>
            </div>
        </div>
        <div class="preset-qs" id="preset-qs">
<button class="preset-q" onclick="askPreset('Best PCR primers for TSWV?')">Best TSWV PCR Primers</button>
<button class="preset-q" onclick="askPreset('Recommended qPCR primers for TMV')">TMV qPCR Primers</button>
<button class="preset-q" onclick="askPreset('PCR vs qPCR comparison')">PCR vs qPCR</button>
<button class="preset-q" onclick="askPreset('What does RECOMMENDED score mean?')">Scoring Guide</button>
</div>
        <div class="chat-msgs" id="chat-msgs"><div class="chat-msg system">Hello! I am PrimerDB AI Assistant. Click a preset question below or type your own.</div></div>
        <div class="chat-input-row">
            <input id="chat-input" placeholder="Type a question..." onkeydown="if(event.key==='Enter')sendMsg()">
            <button onclick="sendMsg()">Send</button></div>
    </div>
    <script>
    var chatConv = [];
    var chatOpen = false;
    function askPreset(q) {
        document.getElementById('chat-input').value = q;
        sendMsg();
    }
    function toggleChat() {
        chatOpen = !chatOpen;
        document.getElementById('ai-chat-panel').style.display = chatOpen ? 'flex' : 'none';
    }
    function toggleSettings() {
        var p = document.getElementById('ai-settings-inline');
        p.style.display = p.style.display === 'none' ? 'block' : 'none';
    }
    function saveAISettings() {
        localStorage.setItem('ai_api_key', document.getElementById('ai-api-key').value);
        localStorage.setItem('ai_api_url', document.getElementById('ai-api-url').value);
        localStorage.setItem('ai_model', document.getElementById('ai-model').value);
        document.getElementById('ai-settings-inline').style.display = 'none';
        addChatMsg('system', 'Settings saved');
    }
    (function(){
        var k = localStorage.getItem('ai_api_key');
        if(k) document.getElementById('ai-api-key').value = k;
        var u = localStorage.getItem('ai_api_url');
        if(u) document.getElementById('ai-api-url').value = u;
        var m = localStorage.getItem('ai_model');
        if(m) document.getElementById('ai-model').value = m;
    })();
    function addChatMsg(role, text) {
        var div = document.createElement('div');
        div.className = 'chat-msg ' + role;
        var safe = String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        var urlRe = new RegExp('(https?:)(//[^ <>]+)', 'g');
        safe = safe.replace(urlRe, '<a href="$1$2" target="_blank" rel="noopener">$1$2</a>');
        div.innerHTML = safe.split(String.fromCharCode(10)).join('<br>');
        document.getElementById('chat-msgs').appendChild(div);
        document.getElementById('chat-msgs').scrollTop = document.getElementById('chat-msgs').scrollHeight;
    }
    function showTyping() {
        var div = document.createElement('div');
        div.className = 'ai-typing';
        div.id = 'typing-indicator';
        div.innerHTML = '<span></span><span></span><span></span>';
        document.getElementById('chat-msgs').appendChild(div);
    }
    function hideTyping() {
        var t = document.getElementById('typing-indicator');
        if(t) t.remove();
    }
    async function sendMsg() {
        var inp = document.getElementById('chat-input');
        var msg = inp.value.trim();
        if(!msg) return;
        addChatMsg('user', msg);
        inp.value = '';
        chatConv.push({role:'user', content:msg});
        var key = localStorage.getItem('ai_api_key') || '';
        // Server-side key will be used if no local key
        showTyping();
        try {
            var resp = await fetch('/api/chat', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    message: msg,
                    api_key: key,
                    api_url: localStorage.getItem('ai_api_url')||'https://api.deepseek.com/v1/chat/completions',
                    model: localStorage.getItem('ai_model')||'deepseek-chat',
                    conversation: chatConv.slice(-8)
                })
            });
            var data = await resp.json();
            hideTyping();
            addChatMsg('ai', data.reply);
            chatConv.push({role:'assistant', content:data.reply});
        } catch(e) {
            hideTyping();
            addChatMsg('system', 'Request failed: ' + e.message);
        }
    }
    </script>
</body>
</html>
'''


INDEX_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''{% block content %}
<div class="row mt-4">
    <div class="col-12">
        <div class="p-5 mb-4 bg-success text-white rounded">
            <h1><i class="bi-virus2"></i> Plant Virus Primer Database</h1>
            <p class="lead">
                {{ primer_count }} PCR/qPCR primer pairs designed for {{ species_count }} plant virus species, 
                Covering major plant virus families; supports conserved-region detection, degenerate primers, and tiled amplicon design.
            </p>
            <form action="/search" method="GET" class="row g-2">
                <div class="col-md-8">
                    <input type="text" name="q" class="form-control form-control-lg"
                           placeholder="Search by virus name... (e.g. Tobacco Mosaic Virus, Potyvirus)">
                </div>
                <div class="col-md-4">
                    <button type="submit" class="btn btn-light btn-lg w-100">
                        <i class="bi-search"></i> Search Primers
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>

<div class="row g-4 mb-4">
    <div class="col-md-3"><div class="card card-stat bg-white">
            <div class="number text-warning">{{ families_count }}</div>
            <div class="text-muted">Virus Families</div>
        </div>
    </div>
    <div class="col-md-3"><div class="card card-stat bg-white">
            <div class="number text-primary">{{ species_count }}</div>
            <div class="text-muted">Virus Species</div>
        </div>
    </div>
    <div class="col-md-3"><div class="card card-stat bg-white">
            <div class="number text-success">{{ primer_count }}</div>
            <div class="text-muted">Primer Pairs</div>
        </div>
    </div>
    <div class="col-md-3"><div class="card card-stat bg-white">
            <div class="number text-info">{{ recommended_count }}</div>
            <div class="text-muted">Recommended Primers</div>
        </div>
    </div>

<div class="row mt-3">
    <div class="col-md-8">
        <div class="card mb-4">
            <div class="card-header fw-bold"><i class="bi-lightning"></i> Quick Access</div>
            <div class="card-body">
                <div class="row">
                <div class="col-md-4"><h6>By Primer Type</h6>
                    <a href="/search?type=PCR" class="btn btn-outline-primary btn-sm d-block mb-1">PCR Detection</a>
                    <a href="/search?type=qPCR" class="btn btn-outline-info btn-sm d-block mb-1">qPCR Real-time</a>
                    <a href="/search?type=DEGENERATE" class="btn btn-outline-warning btn-sm d-block mb-1">Degenerate Primers</a>
                    <a href="/search?type=TILED" class="btn btn-outline-secondary btn-sm d-block">Tiled Amplicons</a></div>
                <div class="col-md-4"><h6>By Score</h6>
                    <a href="/search?recommendation=RECOMMENDED" class="btn btn-outline-success btn-sm d-block mb-1">RECOMMENDED (≥80)</a>
                    <a href="/search?recommendation=USABLE" class="btn btn-outline-warning btn-sm d-block">USABLE (60–79)</a></div>
                <div class="col-md-4"><h6>Data Download</h6>
                    <a href="/download" class="btn btn-outline-dark btn-sm d-block mb-1">Download Page</a>
                    <a href="/api/all_primers?format=csv" class="btn btn-outline-dark btn-sm d-block">Export All CSV</a></div>
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card mb-4">
            <div class="card-header fw-bold"><i class="bi-bar-chart"></i> Primer Type Distribution</div>
            <div class="card-body">
                {% set type_counts = {'PCR':0,'qPCR':0,'DEGENERATE':0,'TILED':0} %}
                {% for p in primers_for_stats %}{% set _ = type_counts.update({p.primer_type: type_counts.get(p.primer_type,0)+1}) %}{% endfor %}
                {% set max_count = [type_counts.values()|max, 1]|max %}
                {% for t in ['PCR','qPCR','DEGENERATE','TILED'] %}
                {% set c = type_counts.get(t,0) %}
                <div style="display:flex;align-items:center;margin:6px 0">
                  <span style="width:85px;font-size:11px">{{t}}</span>
                  <div style="flex:1;height:18px;background:#e9ecef;border-radius:3px;overflow:hidden">
                    <div style="height:100%;width:{{ (c/max_count*100)|int }}%;min-width:{{ '0' if c==0 else '8' }}px;background:{{ '#2b8a3e' if t=='PCR' else '#1971c2' if t=='qPCR' else '#e8590c' if t=='DEGENERATE' else '#6741d9' }};border-radius:3px;display:flex;align-items:center;padding-left:4px;font-size:10px;color:white">{{c if c>0 else ''}}</div>
                  </div>
                  <span style="width:35px;text-align:right;font-size:11px;margin-left:4px">{{c}}</span>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
</div>

<div class="card mb-4 mt-3">
    <div class="card-header fw-bold"><i class="bi-trophy"></i> Top 5 Species by Type &amp; Score</div>
    <div class="card-body">
        <div class="row">
        {% set type_names = {'PCR':'PCR Detection','qPCR':'qPCR Real-time','DEGENERATE':'Degenerate Primers','TILED':'Tiled Amplicons'} %}
        {% set type_colors = {'PCR':'#2b8a3e','qPCR':'#1971c2','DEGENERATE':'#e8590c','TILED':'#6741d9'} %}
        {% for t in ['PCR','qPCR','DEGENERATE','TILED'] %}
        <div class="col-md-3 mb-3">
            <div style="border-left:3px solid {{type_colors[t]}};padding-left:8px">
                <h6 style="color:{{type_colors[t]}}">{{type_names[t]}}</h6>
                {% for row in top_by_type.get(t,[]) %}
                <div style="font-size:12px;margin:3px 0;display:flex;justify-content:space-between">
                    <a href="/species/{{row.species_name|urlencode}}" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block" title="{{row.species_name}}">{{row.species_name}}</a>
                    <span style="min-width:55px;text-align:right"><span style="font-weight:600;color:{{'#2b8a3e' if row.avg_score >= 80 else '#e8590c'}}">{{'%.0f'|format(row.avg_score)}}</span> <small class="text-muted">{{row.cnt}}</small></span>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
        </div>
    </div>
</div>
{% endblock %}''')


SEARCH_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''{% block content %}
<h2 class="mt-4"><i class="bi-search"></i> Search Primers</h2>

<form action="/search" method="GET" class="row g-3 mb-4 bg-light p-3 rounded">
    <div class="col-md-4">
        <label class="form-label">Virus Name / Species</label>
        <input type="text" name="q" class="form-control" value="{{ query or '' }}"
               placeholder="Enter species, genus, or family name">
    </div>
    <div class="col-md-2">
        <label class="form-label">Primer Type</label>
        <select name="type" id="typeSelect" onchange="filterMethods()" class="form-select">
            <option value="">All</option>
            {% for t in ['PCR', 'qPCR', 'DEGENERATE', 'TILED'] %}
            <option value="{{ t }}" {% if type_filter == t %}selected{% endif %}>{{ t }}</option>
            {% endfor %}
        </select>
    </div>
    <div class="col-md-2">
        <label class="form-label">Design Tool</label>
        <select name="method" id="methodSelect" class="form-select">
            <option value="">All</option>
            {% for m in ['Primer3','Simple_Thermo','Primer3_qPCR','IUPAC_Degenerate','varVAMP','Olivar','varVAMP_tiled','PrimerForge'] %}
            <option value="{{ m }}" {% if method_filter == m %}selected{% endif %}>{{ m }}</option>
            {% endfor %}
        </select>
    </div>
    <div class="col-md-2">
        <label class="form-label">Recommendation</label>
        <select name="recommendation" class="form-select">
            <option value="">All</option>
            {% for r in ['RECOMMENDED', 'USABLE', 'CAUTION', 'NOT_RECOMMENDED'] %}
            <option value="{{ r }}" {% if rec_filter == r %}selected{% endif %}>{{ r }}</option>
            {% endfor %}
        </select>
    </div>
    <div class="col-md-2 d-flex align-items-end">
        <button type="submit" class="btn btn-primary w-100">
            <i class="bi-search"></i> Search
        </button>
    </div>
</form>

{% if results %}
<div class="alert alert-info">
    <strong>{{ total }}</strong> primer pairs found (showing first {{ results|length }})
</div>

<div class="table-responsive">
<table class="table table-hover table-primer">
    <thead class="table-dark">
        <tr>
            <th>Species</th>
            <th>Type</th>
            <th>Forward (5'→3')</th>
            <th>Reverse (5'→3')</th>
            <th>Product</th>
            <th>Score</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
    {% for r in results %}
    <tr>
        <td>
            <a href="/species/{{ r.species_name | urlencode }}">{{ r.species_name[:30] }}</a>
            {% if r.genus %}<br><small class="text-muted">{{ r.genus }}</small>{% endif %}
        </td>
        <td><span class="badge bg-{{ 'primary' if r.primer_type=='PCR' else 'info' if r.primer_type=='qPCR' else 'warning' }}">{{ r.primer_type }}</span></td>
        <td><span class="primer-seq">{{ r.fwd_sequence }}</span>
            <button class="copy-btn btn btn-sm btn-outline-secondary" onclick="copyToClipboard('{{ r.fwd_sequence }}')" title="Copy">📋</button>
        </td>
        <td><span class="primer-seq">{{ r.rev_sequence }}</span>
            <button class="copy-btn btn btn-sm btn-outline-secondary" onclick="copyToClipboard('{{ r.rev_sequence }}')" title="Copy">📋</button>
        </td>
        <td>{{ r.product_size }}bp</td>
        <td>
            <span class="score-badge {{ 'recommended' if r.recommendation in ('RECOMMENDED','PASS') else 'usable' if r.recommendation=='USABLE' else 'not-recommended' }}">
                {{ "%.0f"|format(r.overall_score or 0) }}
            </span>
        </td>
        <td>
            <a href="/primer/{{ r.primer_id }}" class="btn btn-sm btn-outline-primary">Details</a>
            <a href="/api/primer/{{ r.primer_id }}?format=fasta" class="btn btn-sm btn-outline-success">FASTA</a>
        </td>
    </tr>
    {% endfor %}
    </tbody>
</table>
</div>
{% elif query or type_filter %}
<div class="alert alert-warning">No matching primers found.</div>
{% endif %}
<script>
var methodGroups = {Primer3:'PCR',Simple_Thermo:'PCR',Primer3_qPCR:'qPCR',IUPAC_Degenerate:'DEGENERATE',varVAMP:'DEGENERATE',Olivar:'TILED',varVAMP_tiled:'TILED',PrimerForge:'TILED'};
(function(){
  var opts = document.getElementById('methodSelect').options;
  for (var i = 0; i < opts.length; i++) {
    if (opts[i].value) opts[i].setAttribute('data-type', methodGroups[opts[i].value] || '');
  }
  // Filter by current type on page load, preserving existing method selection
  filterMethods(false);
})();
function filterMethods(resetVal) {
  var t = document.getElementById('typeSelect').value;
  var sel = document.getElementById('methodSelect');
  if (resetVal !== false) sel.value = '';  // Reset only when user switches type
  for (var i = 0; i < sel.options.length; i++) {
    var ok = !t || sel.options[i].getAttribute('data-type') === t || !sel.options[i].value;
    sel.options[i].disabled = !ok;
  }
}
</script>
{% endblock %}''')


SPECIES_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''{% block content %}
<h2 class="mt-4"><i class="bi-virus"></i> {{ species }}</h2>
<p class="text-muted">
    {% if taxonomy.genus %}Genus: <strong>{{ taxonomy.genus }}</strong> |{% endif %}
    {% if taxonomy.family %}Family: <strong>{{ taxonomy.family }}</strong> |{% endif %}
    Priority: <span class="badge bg-{{ 'danger' if taxonomy.priority=='HIGH' else 'warning' if taxonomy.priority=='MEDIUM' else 'secondary' }}">{{ taxonomy.priority }}</span>
</p>

<div class="row g-3 mb-4">
    <div class="col-md-3">
        <div class="card text-center"><div class="card-body">
            <h3 class="text-primary">{{ primers|length if primers else 0 }}</h3>
            <small class="text-muted">Primer Pairs</small>
        </div></div>
    </div>
    <div class="col-md-3">
        <div class="card text-center"><div class="card-body">
            <h3 class="text-success">{{ recommended_count }}</h3>
            <small class="text-muted">Recommended</small>
        </div></div>
    </div>
    {% if est_genome_len > 0 %}
    <div class="col-md-3">
        <div class="card text-center"><div class="card-body">
            <h3 class="text-info">{{ est_genome_len }}</h3>
            <small class="text-muted">Genome Length (bp)</small>
        </div></div>
    </div>
    {% endif %}
</div>

{% if est_genome_len > 0 %}
<div class="card mb-3"><div class="card-body">
    <h5>Genome Primer Coverage Map ({{ est_genome_len }} bp)</h5>
    <div id="genome-viz-container" style="overflow-x:auto;max-width:100%">
    <div id="genome-viz-inner" style="min-width:600px">
    {% set types = ['PCR','qPCR','DEGENERATE','TILED'] %}
    {% set colors = {'PCR':'#2b8a3e','qPCR':'#1971c2','DEGENERATE':'#e8590c','TILED':'#6741d9'} %}
    {% set light_colors = {'PCR':'#d3f9d8','qPCR':'#d0ebff','DEGENERATE':'#ffe8cc','TILED':'#e8d9ff'} %}
    {% for t in types %}
    {% set t_primers = primers | selectattr('primer_type','equalto',t) | selectattr('fwd_position') | list %}
    <div class="genome-track" data-type="{{t}}" style="margin:6px 0;{% if t_primers|length == 0 %}display:none{% endif %}">
      <div style="display:flex;align-items:center">
        <span style="width:80px;font-size:12px;font-weight:700;color:{{colors[t]}};flex-shrink:0">{{t}} <span style="font-weight:400;font-size:10px;color:#868e96">{{t_primers|length}}</span></span>
        <div style="flex:1;position:relative;background:#fafafa;border-radius:4px;border:1px solid #e0e0e0;min-height:{{t_primers|length*14+4}}px">
        {% for p in t_primers %}
        {% set mc = {'Olivar':'#7b2d8e','varVAMP_tiled':'#2d8e7b','PrimerForge':'#8e7b2d'}.get(p.design_method, colors[t]) %}
        {% set mlc = {'Olivar':'#e8d9ff','varVAMP_tiled':'#d9ffe8','PrimerForge':'#ffe8d9'}.get(p.design_method, light_colors[t]) %}
        {% set raw_fp = (p.fwd_position or 0) | float %}
        {% set raw_rp = (p.rev_position or 0) | float %}
        {# Viroid circular assembly fix: wrap modulo to real genome coordinates #}
        {% set fp = raw_fp % est_genome_len if est_genome_len > 0 else raw_fp %}
        {% set rp_diff = raw_rp - raw_fp %}
        {% set rp = fp + rp_diff %}
        {% if rp > fp %}
        {% set left_pct = [fp / est_genome_len * 100, 95] | min %}
        {% set width_pct = [rp_diff / est_genome_len * 100, 100 - left_pct] | min %}
        {% set primer_w = (p.fwd_sequence|length or 21) / est_genome_len * 100 %}
        {% set rev_w = (p.rev_sequence|length or 21) / est_genome_len * 100 %}
        {% set top_y = loop.index0 * 14 + 2 %}
        <a href="/primer/{{p.primer_id}}" style="text-decoration:none" title="Pair {{p.pair_id}} | {{t}} | {{fp|int}}-{{rp|int}} ({{(rp-fp)|int}}bp) | Score: {{'%.0f'|format(p.overall_score or 0)}}">
        <div style="position:absolute;left:{{'%.2f'|format(left_pct)}}%;top:{{top_y+4}}px;width:{{'%.2f'|format(width_pct)}}%;height:3px;background:{{mlc}};border-radius:1px;cursor:pointer"></div>
        <div style="position:absolute;left:{{'%.2f'|format(left_pct)}}%;top:{{top_y}}px;width:{{'%.2f'|format(primer_w)}}%;height:10px;background:{{mc}};border-radius:3px;cursor:pointer;opacity:0.8"></div>
        <div style="position:absolute;left:{{'%.2f'|format(left_pct+width_pct-rev_w)}}%;top:{{top_y}}px;width:{{'%.2f'|format(rev_w)}}%;height:10px;background:{{mc}};border-radius:3px;cursor:pointer;opacity:0.5"></div>
        </a>
        {% elif (p.product_size or 0) > 0 or p.primer_type == 'TILED' %}
        {% set tile_id = (p.tile_id or 1) | int %}
        {% set left_pct = [(tile_id * 5) % 90, 90] | min %}
        {% set width_pct = [[(p.product_size or 200) / est_genome_len * 100, 20]|min, 100 - left_pct] | min %}
        {% set top_y = loop.index0 * 14 + 2 %}
        <a href="/primer/{{p.primer_id}}" style="text-decoration:none" title="Pair {{p.pair_id}} | {{t}} | {{(p.product_size or 0)|int}}bp | Score: {{'%.0f'|format(p.overall_score or 0)}}">
        <div style="position:absolute;left:{{'%.2f'|format(left_pct)}}%;top:{{top_y+4}}px;width:{{'%.2f'|format(width_pct)}}%;height:3px;background:{{mlc}};border-radius:1px;cursor:pointer"></div>
        <div style="position:absolute;left:{{'%.2f'|format(left_pct)}}%;top:{{top_y}}px;width:{{'%.2f'|format(primer_w)}}%;height:10px;background:{{mc}};border-radius:3px;cursor:pointer;opacity:0.8"></div>
        <div style="position:absolute;left:{{'%.2f'|format(left_pct+width_pct-rev_w)}}%;top:{{top_y}}px;width:{{'%.2f'|format(rev_w)}}%;height:10px;background:{{mc}};border-radius:3px;cursor:pointer;opacity:0.5"></div>
        </a>
        {% endif %}
        {% endfor %}
        </div>
      </div>
    </div>
    {% endfor %}
    <div style="display:flex;margin-top:6px;padding-left:80px;font-size:10px;color:#868e96;justify-content:space-between;border-top:1px solid #eee;padding-top:4px">
      <span>1 bp</span><span>{{ (est_genome_len/2)|int }} bp</span><span>{{ est_genome_len }} bp</span>
    </div>
    </div></div>
</div></div>
{% endif %}

<div class="btn-group mb-3">
    <a href="/api/species/{{ species | urlencode }}?format=fasta" class="btn btn-success">
        <i class="bi-download"></i> Export FASTA
    </a>
    <a href="/api/species/{{ species | urlencode }}?format=csv" class="btn btn-primary">
        <i class="bi-download"></i> Export CSV
    </a>
    <a href="/primers/design" class="btn btn-warning" onclick="sessionStorage.setItem('designSpecies','{{ species }}'); return true;">
        <i class="bi-pencil-square"></i> Design New Primers
    </a>
</div>

{% if primers %}
<style>
.tab-btn { cursor:pointer; padding:6px 16px; border:1px solid #dee2e6; background:#fff; border-radius:4px 4px 0 0; margin-right:2px; }
.tab-btn.active { background:#0d6efd; color:#fff; border-color:#0d6efd; }
.tab-panel { display:none; }
.tab-panel.active { display:block; }
</style>
<div style="margin-bottom:8px">
  <button class="tab-btn active" onclick="switchTab('all')">All ({{primers|length}})</button>
  {% set pcr_list = primers|selectattr('primer_type','equalto','PCR')|list %}
  <button class="tab-btn" onclick="switchTab('PCR')">PCR ({{pcr_list|length}})</button>
  {% set qpcr_list = primers|selectattr('primer_type','equalto','qPCR')|list %}
  <button class="tab-btn" onclick="switchTab('qPCR')">qPCR ({{qpcr_list|length}})</button>
  {% set deg_list = primers|selectattr('primer_type','equalto','DEGENERATE')|list %}
  <button class="tab-btn" onclick="switchTab('DEGENERATE')">DEGENERATE ({{deg_list|length}})</button>
  {% set tiled_list = primers|selectattr('primer_type','equalto','TILED')|list %}
  <button class="tab-btn" onclick="switchTab('TILED')">TILED ({{tiled_list|length}})</button>
</div>
{% for tab_type in ['all','PCR','qPCR','DEGENERATE','TILED'] %}
<div class="tab-panel {% if tab_type=='all' %}active{% endif %}" id="tab-{{tab_type}}">
{% if tab_type=='TILED' and tiled_list %}
{% set tiled_by_method = {} %}
{% for p in tiled_list %}
  {% set m = p.design_method or 'Unknown' %}
  {% if m not in tiled_by_method %}{% set _ = tiled_by_method.update({m: []}) %}{% endif %}
  {% set _ = tiled_by_method[m].append(p) %}
{% endfor %}
<div class="card mb-3"><div class="card-body">
  <h5><i class="bi-puzzle"></i> Tiling Schemes ({{ tiled_by_method|length }} groups)</h5>
  {% for m, plist in tiled_by_method.items() %}
  <div style="border-left:3px solid #6741d9;padding-left:10px;margin-bottom:12px">
    <strong>{{ m }}</strong>: {{ plist|length }} amplicons
    {% set bp = namespace(v=0) %}{% for p in plist %}{% set bp.v = bp.v + (p.product_size or 0) %}{% endfor %}
    | coverage {{ bp.v }} bp
    {% if est_genome_len > 0 %}| {{ "%.0f"|format(bp.v / est_genome_len * 100) }}% genome{% endif %}
    | avg {{ "%.0f"|format(bp.v / plist|length) if plist else '-' }} bp
    {% set best = plist|selectattr('overall_score')|map(attribute='overall_score')|list %}
    {% if best %}| Score {{ "%.0f"|format(best|sum / best|length) }}{% endif %}
  </div>
  {% endfor %}
</div></div>
{% endif %}
<div class="table-responsive">
<table class="table table-hover"><thead class="table-dark"><tr>
  <th onclick="sortCol(0)"># ▼</th><th onclick="sortCol(1)">Type ▼</th><th>Forward</th><th>Reverse</th>
  <th>Probe</th><th onclick="sortCol(5)">Position ▼</th><th onclick="sortColNum(6)">bp ▼</th><th onclick="sortColNum(7)">GC% ▼</th><th onclick="sortColNum(8)">Score ▼</th><th>Details</th>
</tr></thead><tbody>
{% for p in primers %}
  {% if tab_type=='all' or p.primer_type==tab_type %}
  <tr>
    <td>{{ p.pair_id }}</td>
    <td><span class="badge bg-{{ 'primary' if p.primer_type=='PCR' else 'info' if p.primer_type=='qPCR' else 'warning' if p.primer_type=='DEGENERATE' else 'secondary' }}">{{ p.primer_type }}</span></td>
    <td style="font-family:monospace;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{{p.fwd_sequence}}">{{ p.fwd_sequence[:30] }}{% if p.fwd_sequence|length > 30 %}...{% endif %}</td>
    <td style="font-family:monospace;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{{p.rev_sequence}}">{{ p.rev_sequence[:30] }}{% if p.rev_sequence|length > 30 %}...{% endif %}</td>
    <td>{% if p.probe_sequence %}<span style="color:#1971c2;font-family:monospace">{{ p.probe_sequence[:20] }}...</span>{% else %}-{% endif %}</td>
    <td>{% if (p.fwd_position or 0) > 0 %}{{p.fwd_position}}-{{p.rev_position}}{% else %}-{% endif %}</td>
    <td>{{ p.product_size }}</td>
    <td>{{ "%.0f"|format(p.gc_fwd or 0) }}/{{ "%.0f"|format(p.gc_rev or 0) }}%</td>
    <td><span class="score-badge {{ 'recommended' if p.recommendation in ('RECOMMENDED','PASS') else 'usable' if p.recommendation=='USABLE' else 'caution' if p.recommendation=='CAUTION' else 'not-recommended' }}">{{ "%.0f"|format(p.overall_score or 0) }}</span></td>
    <td><a href="/primer/{{ p.primer_id }}" class="btn btn-sm btn-outline-primary">Details</a></td>
  </tr>
  {% endif %}
{% endfor %}
</tbody></table></div></div>
{% endfor %}
<script>
function switchTab(type) {
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>{if(b.textContent.trim().startsWith(type))b.classList.add('active')});
  document.getElementById('tab-'+type).classList.add('active');
  // Toggle genome tracks to match
  document.querySelectorAll('.genome-track').forEach(track => {
    if (type === 'all') { track.style.display = ''; }
    else { track.style.display = track.dataset.type === type ? '' : 'none'; }
  });
  // Show scrollbar only for 'all' view
  var c = document.getElementById('genome-viz-container');
  if (c) { c.style.overflowX = type === 'all' ? 'auto' : 'hidden'; }
}
var sortDir = {};
function getSortTbody() {
  var panel = document.querySelector('.tab-panel.active') || document.querySelector('.tab-panel');
  return panel ? panel.querySelector('tbody') : document.querySelector('tbody');
}
function sortCol(n) {
  var t = getSortTbody(); if (!t) return;
  var rows = Array.from(t.rows);
  sortDir[n] = !sortDir[n];
  rows.sort(function(a,b) {
    var va = (a.cells[n]||{textContent:''}).textContent.trim();
    var vb = (b.cells[n]||{textContent:''}).textContent.trim();
    return sortDir[n] ? va.localeCompare(vb) : vb.localeCompare(va);
  });
  rows.forEach(function(r){ t.appendChild(r); });
}
function sortColNum(n) {
  var t = getSortTbody(); if (!t) return;
  var rows = Array.from(t.rows);
  sortDir[n] = !sortDir[n];
  rows.sort(function(a,b) {
    var va = parseFloat((a.cells[n]||{textContent:'0'}).textContent)||0;
    var vb = parseFloat((b.cells[n]||{textContent:'0'}).textContent)||0;
    return sortDir[n] ? va - vb : vb - va;
  });
  rows.forEach(function(r){ t.appendChild(r); });
}
</script>
{% else %}
<div class="alert alert-warning">No primer data for this species. Please run the primer design pipeline first.</div>
{% endif %}
{% endblock %}''')


PRIMER_DETAIL_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''{% block content %}
<h2 class="mt-4"><i class="bi-eye"></i> Primer Details</h2>

<div class="row">
    <div class="col-md-8">
        <div class="card mb-3">
            <div class="card-header fw-bold">Basic Information</div>
            <div class="card-body">
                <table class="table table-sm">
                    <tr><td width="150"><strong>Species</strong></td><td><a href="/species/{{ p.species_name | urlencode }}">{{ p.species_name }}</a></td></tr>
                    <tr><td><strong>Primer Type</strong></td><td><span class="badge bg-primary">{{ p.primer_type }}</span></td></tr>
                    <tr><td><strong>Pair #</strong></td><td>#{{ p.pair_id }}</td></tr>
                    <tr><td><strong>Design Method</strong></td><td>{{ p.design_method or 'N/A' }}</td></tr>
                    <tr><td><strong>Genome Size</strong></td><td>{{ genome_len }} bp</td></tr>
                    {% if (p.fwd_position or 0) > 0 and (p.rev_position or 0) > (p.fwd_position or 0) %}
                    <tr><td><strong>Primer Position</strong></td><td>Fwd: {{ p.fwd_position }} &mdash; Rev: {{ p.rev_position }}</td></tr>
                    {% endif %}
                    <tr><td><strong>Product Size</strong></td><td>{{ p.product_size }} bp</td></tr>
                </table>
            </div>
        </div>

        {% if genome_len > 0 and ((p.fwd_position or 0) > 0 or (p.product_size or 0) > 0) %}
        <div class="card mb-3">
            <div class="card-header fw-bold">Genome Position</div>
            <div class="card-body">
                <div style="position:relative;height:40px;background:#f5f5f5;border-radius:4px;border:1px solid #e0e0e0">
                    {% if (p.fwd_position or 0) > 0 %}
                    {% set fp2 = (p.fwd_position or 0) | float %}
                    {% set rp2_diff = ((p.rev_position or 0) - fp2) | float %}
                    {% set left2 = [fp2 / genome_len * 100, 95] | min %}
                    {% set w2 = [rp2_diff / genome_len * 100, 100 - left2] | min %}
                    {% elif (p.product_size or 0) > 0 %}
                    {% set left2 = [20, 90] | min %}
                    {% set w2 = [[p.product_size / genome_len * 100, 30]|min, 100 - left2] | min %}
                    {% endif %}
                    <div style="position:absolute;left:{{'%.1f'|format(left2)}}%;top:8px;width:{{'%.1f'|format(w2)}}%;height:10px;background:#1971c2;border-radius:3px;opacity:0.7"></div>
                    <div style="position:absolute;left:{{'%.1f'|format(left2)}}%;top:22px;height:8px;width:2px;background:#2b8a3e" title="Fwd {{ p.fwd_position }}"></div>
                    <div style="position:absolute;left:{{'%.1f'|format(left2+w2)}}%;top:22px;height:8px;width:2px;background:#e03131" title="Rev {{ p.rev_position }}"></div>
                    <div style="position:absolute;left:0;bottom:0;font-size:9px;color:#868e96;padding:2px 4px">1 bp</div>
                    <div style="position:absolute;right:0;bottom:0;font-size:9px;color:#868e96;padding:2px 4px">{{ genome_len }} bp</div>
                </div>
                <div style="display:flex;margin-top:4px;font-size:10px;color:#868e96;gap:8px">
                    <span><span style="color:#2b8a3e">&#9632;</span> Fwd</span>
                    <span><span style="color:#1971c2">&#9632;</span> amplicons</span>
                    <span><span style="color:#e03131">&#9632;</span> Rev</span>
                </div>
            </div>
        </div>
        {% endif %}

        <div class="card mb-3">
            <div class="card-header fw-bold">Primer Sequences</div>
            <div class="card-body">
                <h6>Forward Primer (5'→3')</h6>
                <div class="primer-seq p-3 mb-3">{{ p.fwd_sequence }} <button class="copy-btn btn btn-sm btn-outline-secondary float-end" onclick="copyToClipboard('{{ p.fwd_sequence }}')">Copy</button></div>
                <div class="row">
                    <div class="col">Length: {{ p.fwd_sequence|length }}bp</div>
                    <div class="col">Tm: {{ "%.1f"|format(p.fwd_tm or 0) }}°C</div>
                    <div class="col">GC: {{ "%.1f"|format(p.gc_fwd or 0) }}%</div>
                </div>

                <hr>

                <h6>Reverse Primer (5'→3')</h6>
                <div class="primer-seq p-3 mb-3">{{ p.rev_sequence }} <button class="copy-btn btn btn-sm btn-outline-secondary float-end" onclick="copyToClipboard('{{ p.rev_sequence }}')">Copy</button></div>
                <div class="row">
                    <div class="col">Length: {{ p.rev_sequence|length }}bp</div>
                    <div class="col">Tm: {{ "%.1f"|format(p.rev_tm or 0) }}°C</div>
                    <div class="col">GC: {{ "%.1f"|format(p.gc_rev or 0) }}%</div>
                </div>

                {% if p.probe_sequence %}
                <hr>
                <h6><i class="bi bi-pin"></i> TaqMan Probe</h6>
                <div class="probe-seq p-3 mb-2">{{ p.probe_sequence }}</div>
                <small>Probe Tm: {{ "%.1f"|format(p.probe_tm or 0) }}°C</small>
                {% endif %}
            </div>
        </div>

        {% if v %}
        <div class="card mb-3">
            <div class="card-header fw-bold">Validation Results</div>
            <div class="card-body">
                <h4 class="{{ 'recommended' if v.recommendation in ('RECOMMENDED','PASS') else 'usable' if v.recommendation=='USABLE' else 'text-danger' }}">
                    {{ '%.0f'|format(v.overall_score or 0) }}  — 
                    {% if v.recommendation in ('RECOMMENDED','PASS') %}✅ RECOMMENDED
                    {% elif v.recommendation == 'USABLE' %}⚠️ USABLE
                    {% elif v.recommendation == 'CAUTION' %}⚠️ CAUTION
                    {% else %}❌ NOT RECOMMENDED{% endif %}
                </h4>

                <h6 class="mt-3">Dimer Analysis</h6>
                {% set dimer_html = _dimer_viz_html(p.fwd_sequence, 'Fwd Self-Dimer') %}
                {% if dimer_html %}<div class="mb-2">{{ dimer_html | safe }}</div>{% endif %}
                {% set dimer_html = _dimer_viz_html(p.rev_sequence, 'Rev Self-Dimer') %}
                {% if dimer_html %}<div class="mb-2">{{ dimer_html | safe }}</div>{% endif %}
                <table class="table table-sm">
                    <tr><td>Self-Dimer (Fwd)</td><td>{{ _dimer_bp(p.fwd_sequence) }}bp</td></tr>
                    <tr><td>Self-Dimer (Rev)</td><td>{{ _dimer_bp(p.rev_sequence) }}bp</td></tr>
                    <tr><td>Cross-Dimer</td><td>{{ _cross_dimer_bp(p.fwd_sequence, p.rev_sequence) }}bp</td></tr>
                    <tr class="{{ 'table-danger' if v.cross_dimer_3prime >= 3 else '' }}"><td><strong>3' Cross-Dimer</strong></td><td><strong>{{ v.cross_dimer_3prime }}bp</strong></td></tr>
                </table>
                {% if v.dimer_warning %}<div class="alert alert-warning">{{ v.dimer_warning }}</div>{% endif %}

                {% if v.probe_hairpin_tm or v.probe_self_dimer_dg or v.probe_fwd_dimer_dg or v.probe_rev_dimer_dg or v.probe_warning %}
                <h6 class="mt-3"><i class="bi-pin"></i> Probe Validation (qPCR)</h6>
                <table class="table table-sm">
                    {% if v.probe_hairpin_tm %}<tr><td>Probe Hairpin Tm</td><td>{{ "%.1f"|format(v.probe_hairpin_tm) }}°C</td></tr>{% endif %}
                    {% if v.probe_self_dimer_dg %}<tr><td>Probe Self-Dimer ΔG</td><td>{{ "%.1f"|format(v.probe_self_dimer_dg) }} kcal/mol</td></tr>{% endif %}
                    {% if v.probe_fwd_dimer_dg %}<tr><td>Probe-Fwd Cross-Dimer</td><td>{{ "%.1f"|format(v.probe_fwd_dimer_dg) }} kcal/mol</td></tr>{% endif %}
                    {% if v.probe_rev_dimer_dg %}<tr><td>Probe-Rev Cross-Dimer</td><td>{{ "%.1f"|format(v.probe_rev_dimer_dg) }} kcal/mol</td></tr>{% endif %}
                    <tr class="{{ 'table-danger' if not v.probe_tm_diff_ok else '' }}"><td>Probe-Primer Tm Diff</td><td>{{ '✅ PASS' if v.probe_tm_diff_ok else '❌ FAIL (5–10°C required)' }}</td></tr>
                </table>
                {% if v.probe_warning %}<div class="alert alert-warning small">{{ v.probe_warning }}</div>{% endif %}
                {% endif %}

                {% if (v.coverage_avg or 0) > 0 %}
                <h6 class="mt-3"><i class="bi-graph-up"></i> Coverage Analysis</h6>
                <table class="table table-sm">
                    <tr><td>Fwd Coverage</td><td><span class="{{ 'text-success' if (v.fwd_coverage_pct or 0) >= 90 else 'text-warning' if (v.fwd_coverage_pct or 0) >= 70 else 'text-danger' }}">{{ "%.1f"|format(v.fwd_coverage_pct or 0) }}%</span> ({{ v.coverage_total_seqs }}  sequences)</td></tr>
                    <tr><td>Rev Coverage</td><td><span class="{{ 'text-success' if (v.rev_coverage_pct or 0) >= 90 else 'text-warning' if (v.rev_coverage_pct or 0) >= 70 else 'text-danger' }}">{{ "%.1f"|format(v.rev_coverage_pct or 0) }}%</span></td></tr>
                    <tr><td>avgCoverage</td><td><strong>{{ "%.1f"|format(v.coverage_avg or 0) }}%</strong></td></tr>
                    <tr><td>Fwd 3' 3' Penalty</td><td>{{ "%.1f"|format(v.fwd_3prime_penalty or 0) }}</td></tr>
                    <tr><td>Rev 3' 3' Penalty</td><td>{{ "%.1f"|format(v.rev_3prime_penalty or 0) }}</td></tr>
                </table>
                {% endif %}
            </div>
        </div>
        {% endif %}
    </div>

    <div class="col-md-4">
        <div class="card mb-3">
            <div class="card-header fw-bold">Download</div>
            <div class="card-body">
                <a href="/api/primer/{{ p.primer_id }}?format=fasta" class="btn btn-success w-100 mb-2">Download FASTA</a>
                <a href="/api/primer/{{ p.primer_id }}?format=json" class="btn btn-info w-100">Download JSON</a>
            </div>
        </div>
        {% if v and ((v.blast_specificity_score or 0) > 0 or (v.blast_rev_target_hits or 0) > 0) %}
        <div class="card mb-3">
            <div class="card-header fw-bold">BLAST Specificity</div>
            <div class="card-body">
                <p>Specificity Score: <strong>{{ '%.1f'|format(v.blast_specificity_score or 0) }}%</strong></p>
                <table class="table table-sm mb-2">
                    <tr><td></td><td><small>FWD</small></td><td><small>REV</small></td></tr>
                    <tr><td>Target Hits</td><td>{{ v.blast_fwd_target_hits|default(0) }}</td><td>{{ v.blast_rev_target_hits|default(0) }}</td></tr>
                    <tr><td>Plant Hits</td><td>{{ v.blast_fwd_plant_hits|default(0) }}</td><td>{{ v.blast_rev_plant_hits|default(0) }}</td></tr>
                    <tr><td>Other Hits</td><td>{{ v.blast_fwd_other_hits|default(0) }}</td><td>{{ v.blast_rev_other_hits|default(0) }}</td></tr>
                </table>
                {% if v.blast_offtarget_top %}<p class="text-warning small">Off-target:  {{ v.blast_offtarget_top[:120] }}</p>{% endif %}
            </div>
        </div>
        {% endif %}

        {% if epcr %}
        <div class="card mb-3">
            <div class="card-header fw-bold"><i class="bi-diagram-3"></i> In Silico PCR Amplicons</div>
            <div class="card-body" style="max-height:400px;overflow-y:auto">
                <p class="small text-muted">Paired hits with convergent orientation, distance ≤ {{ 5000 }}bp</p>
                {% for a in epcr %}
                <div style="border-left:3px solid {{ '#198754' if a.is_target else '#dc3545' if a.is_plant else '#6c757d' }};padding:4px 8px;margin:4px 0;font-size:12px">
                    <div style="display:flex;justify-content:space-between">
                        <span style="font-weight:600;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{{ a.seq_id }}">{{ a.seq_id }}</span>
                        <span style="font-weight:700;min-width:50px;text-align:right">{{ a.amp_len }}bp</span>
                    </div>
                    <div class="text-muted" style="font-size:10px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ a.desc }}</div>
                    <span class="badge bg-{{ 'success' if a.is_target else 'danger' if a.is_plant else 'secondary' }}" style="font-size:9px">{{ 'Target' if a.is_target else 'Plant' if a.is_plant else 'Other' }}</span>
                </div>
                {% endfor %}
                {% if epcr|length >= 50 %}<p class="small text-muted mt-1">Showing first 50 only</p>{% endif %}
            </div>
        </div>
        {% endif %}
        <div class="card">
            <div class="card-header fw-bold">Related Primers</div>
            <div class="card-body">
                <p class="text-muted">Other primer pairs for this species</p>
                <a href="/species/{{ p.species_name | urlencode }}" class="btn btn-outline-primary btn-sm">View All →</a>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')


BROWSE_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''{% block content %}
<h2 class="mt-4"><i class="bi-list"></i> Browse Species</h2>

<div class="row mb-3">
    <div class="col-md-4">
        <input type="text" class="form-control" id="filterInput" placeholder="Filter species name...">
    </div>
</div>

<div class="table-responsive">
<table class="table table-hover" id="speciesTable">
    <thead class="table-dark">
        <tr>
            <th>Species</th><th>Genus</th><th>Family</th><th>Priority</th><th>Primers</th><th>Avg Score</th>
        </tr>
    </thead>
    <tbody>
    {% for row in species_list %}
    <tr class="species-row">
        <td><a href="/species/{{ row.species_name | urlencode }}">{{ row.species_name }}</a></td>
        <td class="genus-cell">{{ row.genus }}</td>
        <td class="family-cell">{{ row.family }}</td>
        <td><span class="badge bg-{{ 'danger' if row.priority=='HIGH' else 'warning' if row.priority=='MEDIUM' else 'secondary' }}">{{ row.priority }}</span></td>
        <td>{{ row.primer_count }}</td>
        <td><span class="score-badge {{ 'recommended' if (row.avg_score or 0) >= 80 }}">{{ "%.0f"|format(row.avg_score or 0) }}</span></td>
    </tr>
    {% endfor %}
    </tbody>
</table>
</div>
{% endblock %}''')


# ======================================================================

DESIGN_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''{% block content %}
<h2 class="mt-4"><i class="bi-pencil-square"></i> Primer Design</h2>
<p class="text-muted">Upload a FASTA file or paste sequences to design PCR/qPCR primers online.</p>

<div class="row g-3 mb-3">
    <!-- Left: Upload FASTA File -->
    <div class="col-md-6">
        <div class="card h-100"><div class="card-body">
            <h5><i class="bi-file-earmark-arrow-up"></i> Upload FASTA File</h5>
            <div class="mb-3">
                <label class="form-label">Select FASTA file (.fa / .fasta / .fna)</label>
                <input type="file" id="fastaFileInput" class="form-control" accept=".fa,.fasta,.fna,.txt">
            </div>
            <button type="button" class="btn btn-outline-info btn-sm" onclick="loadExampleFasta()">
                <i class="bi-lightbulb"></i> Load TMV Example FASTA
            </button>
            <div class="form-text mt-1" id="fileInfo"></div>
        </div></div>
    </div>

    <!-- Right: Paste Sequences -->
    <div class="col-md-6">
        <div class="card h-100"><div class="card-body">
            <h5><i class="bi-clipboard"></i> Paste Sequences</h5>
            <textarea id="pasteSeqInput" class="form-control font-monospace" rows="8"
                style="font-size:13px; resize:vertical;"
                placeholder=">seq1&#10;ATGCGTACGTAGCTAGCTAGCATCGATCGTAGCTAGCTAGCTAGCTAGC&#10;>seq2&#10;ATGCGTACGTAGCTAGCATCGATCGTAGCTAGCTAGCTAGCTAGCTGA&#10;&#10;Supports FASTA format; plain sequences are auto-wrapped to FASTA"></textarea>
            <div class="mt-2 d-flex justify-content-between align-items-center">
                <small id="pasteCharCount" class="text-muted">0  bp, 0  seqs</small>
                <button type="button" class="btn btn-outline-info btn-sm" onclick="loadExamplePaste()">
                    <i class="bi-lightbulb"></i> Load TMV Example Sequence
                </button>
            </div>
        </div></div>
    </div>
</div>

<!-- Design Parameters -->
<div class="card mb-3"><div class="card-body">
    <div class="row g-3 align-items-end">
        <div class="col-md-3">
            <label class="form-label">Species Name (optional)</label>
            <input type="text" id="speciesNameInput" class="form-control" placeholder="e.g. Tobacco mosaic virus">
        </div>
        <div class="col-md-2">
            <label class="form-label">Design Mode</label>
            <select id="designModeSelect" class="form-select">
                <option value="PCR">PCR Detection</option>
                <option value="qPCR">qPCR Real-time (+Probe)</option>
                <option value="DEGENERATE">Degenerate Primers (varVAMP)</option>
                <option value="TILED">Tiled Amplicons (Olivar)</option>
            </select>
        </div>
        <div class="col-md-1">
            <label class="form-label">Primer Pairs</label>
            <input type="number" id="numPairsInput" class="form-control" value="5" min="1" max="20">
        </div>
        <div class="col-md-1">
            <label class="form-label">Prod Min</label>
            <input type="number" id="prodMinInput" class="form-control" value="250" min="60" max="2000">
        </div>
        <div class="col-md-1">
            <label class="form-label">Prod Max</label>
            <input type="number" id="prodMaxInput" class="form-control" value="1000" min="80" max="5000">
        </div>
        <div class="col-md-4 d-flex">
            <button type="button" class="btn btn-primary w-100 btn-lg" id="designBtn" onclick="submitDesign()">
                <i class="bi-rocket-takeoff"></i> Start Design
            </button>
        </div>
    </div>
</div></div>

<!-- Results -->
<div id="designStatusArea" style="display:none"></div>
<div id="designResultsArea"></div>

<script>
// ── TMV Example Sequence ──
var TMV_EXAMPLE = ">TMV_example|Tobacco_mosaic_virus_complete_genome" + "\n" +
    "GTATTTTTACAACAATTACCAACAACAACAAACAACAAACAACATTACAATTACTA" + "\n" +
    "TTTACAATTACAATGGCTTACACTAGATCAGCAATCGAGTTTCAAAATCAACAAGAA" + "\n" +
    "TCGACTACCTCTGCATCCGCCGGTTACGTGTCCAACGTTAGACAAGCCAACACGGCT" + "\n" +
    "ATCCAGCAGACTATAGCTAATCTACTCAACACTATCCGTGCTAACAACGCTAGCCAG" + "\n" +
    "TCAGAGTCAGCCTCTTTGTCAAGCGCTGACTACGAGACACTTCCTAACCCAAACCCA" + "\n" +
    "AAGCCCCCAACAATGAAGAGGCTCCTAACACTATCCTTTGAATCTGTACGCTCATGG" + "\n" +
    "TATGATGTAGATAATCCTACTAATCCTTTGTCAACTGACGATCCCGAGTTACTGTCT" + "\n" +
    "AAGGCGGTTGCTGATATGTGTGCTTCTGGTGACGCAATATCTGAATCAGATGAGTTC" + "\n" +
    "ATAGATGCAGTTCTCATTGCTGCGGCATTCCCTTCGTACTTCGTAAAATTCTCACTT" + "\n" +
    "CGTTTTAGAAGTCTCATATCTAAATTGATATCTCCTGCGAGGTTTGGACCTAAGGTT" + "\n" +
    "ATTAGAGAGTTTGAGAATTCAGTCGTTT" + "\n" +
    ">TMV_CP|capsid_protein_gene" + "\n" +
    "ATGTCTTACAGTATCACTACTCCATCTCAGTTCGTGTTCTTGTCATCAGCGTGGGCC" + "\n" +
    "GACCCAATAGAGTTAATTAATTTATGTACTAATGCCTTAGGAAATCAGTTTCAAACA" + "\n" +
    "CAACAAGCTCGAACTGTCGTTCAAAGACAATTCAGTGAGTGGAAACCTTCACCAGGT" + "\n" +
    "TCGACGGTGCGTTTTCCTGACAGTGACTTCAAGGTCTTATCTGATTCGACCGCCGCT" + "\n" +
    "TCGTATATACACACCAATACCATAGTCGAGATACAGTCCGCATCAGGAATCTACAAC" + "\n" +
    "CAGAATGCTATTTTGGACGTGTTCAATACTGGAAGTCA";

function loadExamplePaste() {
    document.getElementById('pasteSeqInput').value = TMV_EXAMPLE;
    updatePasteCount();
}
function loadExampleFasta() {
    // Create a Blob and programmatically set it as the file
    document.getElementById('speciesNameInput').value = 'Tobacco mosaic virus (TMV)';
    var blob = new Blob([TMV_EXAMPLE], {type: 'text/plain'});
    var file = new File([blob], 'TMV_example.fasta', {type: 'text/plain'});
    var dt = new DataTransfer();
    dt.items.add(file);
    document.getElementById('fastaFileInput').files = dt.files;
    document.getElementById('fileInfo').textContent = 'TMV_example.fasta (\u5df2\u52a0\u8f7d\u793a\u4f8b)';
}

// Paste char counter
function updatePasteCount() {
    var raw = document.getElementById('pasteSeqInput').value;
    var clean = raw.replace(/[^ATGCatgc]/g, '');
    var nSeqs = (raw.match(/^>/gm) || []).length || (raw.trim() ? 1 : 0);
    document.getElementById('pasteCharCount').textContent = (clean.length || 0) + ' \u78b1\u57fa, ' + nSeqs + ' \u6761\u5e8f\u5217';
}
document.getElementById('pasteSeqInput').addEventListener('input', updatePasteCount);

// File input info
document.getElementById('fastaFileInput').addEventListener('change', function() {
    var f = this.files[0];
    document.getElementById('fileInfo').textContent = f ? (f.name + ' (' + (f.size/1024).toFixed(1) + ' KB)') : '';
});

var _lastJobId = null;

// ── Submit Design ──
async function submitDesign() {
    var btn = document.getElementById('designBtn');
    var status = document.getElementById('designStatusArea');
    var mode = document.getElementById('designModeSelect').value;
    var speciesName = document.getElementById('speciesNameInput').value.trim();
    var numPairs = document.getElementById('numPairsInput').value;
    var prodMin = document.getElementById('prodMinInput').value;
    var prodMax = document.getElementById('prodMaxInput').value;

    var form = new FormData();
    form.append('species_name', speciesName);
    form.append('mode', mode);
    form.append('num_pairs', numPairs);
    form.append('prod_min', prodMin);
    form.append('prod_max', prodMax);

    // Determine input source
    var pasteSeq = document.getElementById('pasteSeqInput').value.trim();
    var fileInput = document.getElementById('fastaFileInput');
    var file = fileInput.files[0];

    if (pasteSeq) {
        // Paste mode: wrap as FASTA if needed
        if (!pasteSeq.startsWith('>')) {
            pasteSeq = '>seq1' + "\n" + pasteSeq.replace(/\s+/g, "\n").replace(/(.{60})/g, "$1\n");
        }
        var blob = new Blob([pasteSeq], {type: 'text/plain'});
        form.append('fasta', blob, 'pasted.fasta');
    } else if (file) {
        form.append('fasta', file);
    } else {
        status.style.display = 'block';
        status.innerHTML = '<div class="alert alert-warning">\u8bf7\u4e0a\u4f20FASTA\u6587\u4ef6\u6216\u7c98\u8d34\u5e8f\u5217\u3002</div>';
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> \u63d0\u4ea4\u4e2d...';
    status.style.display = 'block';
    status.innerHTML = '<div class="alert alert-info"><div class="spinner-border spinner-border-sm"></div> \u6b63\u5728\u63d0\u4ea4\u8bbe\u8ba1\u4efb\u52a1...</div>';

    try {
        var resp = await fetch('/api/design/upload', {method: 'POST', body: form});
        var data = await resp.json();
        if (data.error) {
            status.innerHTML = '<div class="alert alert-danger">' + data.error + '</div>';
            btn.disabled = false;
            btn.innerHTML = '<i class="bi-rocket-takeoff"></i> \u5f00\u59cb\u8bbe\u8ba1';
        } else {
            status.innerHTML = '<div class="alert alert-info"><div class="spinner-border spinner-border-sm"></div> \u4efb\u52a1 <code>' + data.job_id + '</code> \u5df2\u63d0\u4ea4\uff0c\u6b63\u5728\u8bbe\u8ba1\u4e2d...</div>';
            startPolling(data.job_id, speciesName || 'custom_input', mode);
        }
    } catch(err) {
        status.innerHTML = '<div class="alert alert-danger">\u7f51\u7edc\u9519\u8bef: ' + err.message + '</div>';
        btn.disabled = false;
        btn.innerHTML = '<i class="bi-rocket-takeoff"></i> \u5f00\u59cb\u8bbe\u8ba1';
    }
}

// ── Poll ──
function startPolling(jobId, speciesName, designMode) {
    var status = document.getElementById('designStatusArea');
    var results = document.getElementById('designResultsArea');
    var iv = setInterval(async function() {
        try {
            var r = await fetch('/api/design/status/' + jobId);
            var d = await r.json();
            if (d.status === 'completed') {
                clearInterval(iv);
                _lastJobId = jobId;
                try {
                    var rr = await fetch('/api/design/results/' + jobId + '?format=json');
                    var res = await rr.json();
                    if (res.error) {
                        status.innerHTML = '<div class="alert alert-danger">' + res.error + '</div>';
                    } else {
                        status.innerHTML = '<div class="alert alert-success"><i class="bi-check-circle"></i> \u8bbe\u8ba1\u5b8c\u6210! <strong>' + (res.length || 0) + '</strong> \u5bf9\u5f15\u7269</div>';
                        results.innerHTML = buildResultsTable(res, speciesName || d.species_name, designMode || d.design_mode);
                    }
                } catch(e2) {
                    status.innerHTML = '<div class="alert alert-warning">\u8bbe\u8ba1\u5b8c\u6210\u4f46\u83b7\u53d6\u7ed3\u679c\u5931\u8d25: ' + e2.message + '</div>';
                }
                var btn = document.getElementById('designBtn');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi-rocket-takeoff"></i> \u5f00\u59cb\u8bbe\u8ba1';
            } else if (d.status === 'failed') {
                clearInterval(iv);
                status.innerHTML = '<div class="alert alert-danger"><i class="bi-exclamation-triangle"></i> \u8bbe\u8ba1\u5931\u8d25: ' + (d.error || '\u672a\u77e5\u9519\u8bef') + '</div>';
                var btn = document.getElementById('designBtn');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi-rocket-takeoff"></i> \u5f00\u59cb\u8bbe\u8ba1';
            } else {
                status.innerHTML = '<div class="alert alert-info"><div class="spinner-border spinner-border-sm"></div> ' + (d.progress_msg || '\u8bbe\u8ba1\u4e2d...') + ' (' + (d.progress_pct || 0) + '%)</div>';
            }
        } catch(e) { clearInterval(iv); }
    }, 3000);
}

// ── Build Results Table ──
function buildResultsTable(results, speciesName, designMode) {
    if (!results || results.length === 0) {
        return '<div class="alert alert-warning">\u672a\u8bbe\u8ba1\u51fa\u5f15\u7269\uff0c\u8bf7\u5c1d\u8bd5\u8c03\u6574\u53c2\u6570\u6216\u4f7f\u7528\u5176\u4ed6\u5e8f\u5217\u3002</div>';
    }

    // ── SVG \u57fa\u56e0\u7ec4\u4f4d\u7f6e\u56fe ──
    var genomeViz = '';
    var hasPositions = false;
    for (var i = 0; i < results.length; i++) {
        var fs = parseInt(results[i].Fwd_Start) || 0;
        var rs = parseInt(results[i].Rev_Start) || 0;
        if (fs > 0 && rs > 0) { hasPositions = true; break; }
    }
    if (hasPositions) {
        var maxPos = 0;
        for (var i = 0; i < results.length; i++) {
            var rs2 = parseInt(results[i].Rev_Start) || 0;
            if (rs2 > maxPos) maxPos = rs2;
        }
        var genomeLen = Math.max(maxPos + 200, 500);
        var colors = ['#e03131','#1971c2','#2b8a3e','#e8590c','#862e9c','#c92a2a','#1864ab','#2f9e44','#d9480f','#9c36b5'];
        var svgW = 780, svgH = 22 * results.length + 40, padL = 55, padR = 60, barW = svgW - padL - padR;
        genomeViz = '<div class="mt-2 mb-3 p-2 bg-light rounded"><strong><i class="bi-diagram-3"></i> \u5f15\u7269\u7ed3\u5408\u4f4d\u7f6e (\u57fa\u56e0\u7ec4 ~' + genomeLen.toLocaleString() + ' bp)</strong>';
        genomeViz += '<svg width="100%" viewBox="0 0 ' + svgW + ' ' + svgH + '" style="max-width:820px; font-family:Consolas,monospace; font-size:11px;">';
        genomeViz += '<rect x="' + padL + '" y="' + (svgH - 16) + '" width="' + barW + '" height="6" rx="3" fill="#dee2e6" stroke="#adb5bd" stroke-width="1"/>';
        for (var t = 0; t <= 1; t += 0.25) {
            var tx = padL + t * barW;
            genomeViz += '<line x1="' + tx + '" y1="' + (svgH - 20) + '" x2="' + tx + '" y2="' + (svgH - 10) + '" stroke="#868e96" stroke-width="1"/>';
            genomeViz += '<text x="' + tx + '" y="' + (svgH - 2) + '" text-anchor="middle" fill="#495057">' + Math.round(t * genomeLen) + '</text>';
        }
        for (var i = 0; i < results.length; i++) {
            var r = results[i];
            var fs2 = parseInt(r.Fwd_Start) || 0;
            var rs2 = parseInt(r.Rev_Start) || 0;
            var fLen = (r.Fwd_Seq || '').length || 20;
            var rLen = (r.Rev_Seq || '').length || 20;
            if (fs2 <= 0 || rs2 <= 0) continue;
            var col = colors[i % colors.length];
            var y = 4 + i * 22;
            var fLeft = padL + (fs2 / genomeLen) * barW;
            var fW = Math.max((fLen / genomeLen) * barW, 3);
            var rLeft = padL + (rs2 / genomeLen) * barW;
            var rW = Math.max((rLen / genomeLen) * barW, 3);
            var ampLeft = fLeft + fW;
            var ampW = rLeft - (fLeft + fW);
            if (ampW > 0) {
                genomeViz += '<rect x="' + ampLeft + '" y="' + (y + 5) + '" width="' + ampW + '" height="3" fill="' + col + '" opacity="0.3" rx="1"/>';
            }
            genomeViz += '<rect x="' + fLeft + '" y="' + y + '" width="' + fW + '" height="8" fill="' + col + '" opacity="0.85" rx="2"/>';
            genomeViz += '<text x="' + Math.max(fLeft - 2, padL - 50) + '" y="' + (y + 7) + '" text-anchor="end" fill="' + col + '" font-weight="bold">F' + (i+1) + '</text>';
            genomeViz += '<rect x="' + rLeft + '" y="' + y + '" width="' + rW + '" height="8" fill="' + col + '" opacity="0.55" rx="2"/>';
            genomeViz += '<text x="' + (rLeft + rW + 3) + '" y="' + (y + 7) + '" fill="' + col + '" font-size="9">' + fs2 + '..' + (rs2 + rLen) + '</text>';
        }
        genomeViz += '</svg></div>';
    }

    // ── \u8868\u683c ──
    var h = '<div class="card mt-3"><div class="card-header"><strong><i class="bi-clipboard-check"></i> \u8bbe\u8ba1\u7ed3\u679c</strong>';
    h += ' <span class="badge bg-primary">' + (designMode || '') + '</span>';
    h += ' <small class="text-muted ms-2">' + (speciesName || '') + '</small>';
    h += ' <span class="float-end">';
    h += '<button class="btn btn-sm btn-outline-info me-1" onclick="downloadResults(\'json\')">JSON</button>';
    h += '<button class="btn btn-sm btn-outline-success me-1" onclick="downloadResults(\'tsv\')">TSV</button>';
    h += '<button class="btn btn-sm btn-outline-primary" onclick="downloadResults(\'fasta\')">FASTA</button>';
    h += '</span></div><div class="card-body">';
    h += genomeViz;
    h += '<div class="table-responsive"><table class="table table-hover table-sm">';
    h += '<thead class="table-dark"><tr><th>#</th><th>\u6b63\u5411\u5f15\u7269 (5\'→3\')</th><th>Tm</th><th>GC%</th><th>\u53cd\u5411\u5f15\u7269 (5\'→3\')</th><th>Tm</th><th>GC%</th><th>\u4ea7\u7269</th><th>\u65b9\u6cd5</th><th>\u8bc4\u5206</th></tr></thead><tbody>';
    for (var i = 0; i < results.length; i++) {
        var r = results[i];
        var fwd = r.Fwd_Seq || '';
        var rev = r.Rev_Seq || '';
        var prodVal = parseInt(r.Product) || 0;
        var prod = prodVal > 0 ? (prodVal + ' bp') : '\u2014';
        var tmF = isFinite(parseFloat(r.Fwd_Tm)) ? parseFloat(r.Fwd_Tm).toFixed(1) : '\u2014';
        var tmR = isFinite(parseFloat(r.Rev_Tm)) ? parseFloat(r.Rev_Tm).toFixed(1) : '\u2014';
        var gcF = isFinite(parseFloat(r.GC_Fwd)) ? parseFloat(r.GC_Fwd).toFixed(1) + '%' : '\u2014';
        var gcR = isFinite(parseFloat(r.GC_Rev)) ? parseFloat(r.GC_Rev).toFixed(1) + '%' : '\u2014';
        var method = r.Method || '\u2014';
        var penalty = r.Penalty != null ? r.Penalty : '\u2014';
        var probe = r.Probe_Seq || '';
        h += '<tr><td>' + (i + 1) + '</td>';
        h += '<td><span class="primer-seq">' + fwd + '</span></td>';
        h += '<td>' + tmF + '</td><td>' + gcF + '</td>';
        h += '<td><span class="primer-seq">' + rev + '</span></td>';
        h += '<td>' + tmR + '</td><td>' + gcR + '</td>';
        h += '<td>' + prod + '</td><td>' + method + '</td>';
        h += '<td>' + penalty + '</td></tr>';
        if (probe) {
            h += '<tr><td></td><td colspan="9"><span class="probe-seq">\u63a2\u9488: ' + probe + '</span></td></tr>';
        }
    }
    h += '</tbody></table></div></div></div>';
    return h;
}

// ── \u4e0b\u8f7d ──
function downloadResults(fmt) {
    if (_lastJobId) window.open('/api/design/results/' + _lastJobId + '?format=' + fmt, '_blank');
}

// ── Auto-load job from URL param ──
(function() {
    var params = new URLSearchParams(window.location.search);
    var jid = params.get('job_id');
    if (jid) {
        var status = document.getElementById('designStatusArea');
        status.style.display = 'block';
        status.innerHTML = '<div class="alert alert-info"><div class="spinner-border spinner-border-sm"></div> \u52a0\u8f7d\u4efb\u52a1 <code>' + jid + '</code>...</div>';
        startPolling(jid, '', '');
    }
})();
</script>
{% endblock %}''')


# ======================================================================

def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.executescript('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA synchronous=NORMAL;')
    return g.db


def close_db(e=None):
    """关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def _dimer_viz_html(seq, label, max_len=12):
    """生成引物二聚体碱基配对可视化 HTML"""
    from Bio.Seq import Seq
    rc = str(Seq(seq).reverse_complement())
    best_len, best_start, best_rc = 0, 0, 0
    for i in range(len(seq)):
        for j in range(i + 3, min(i + max_len + 1, len(seq) + 1)):
            if seq[i:j] in rc:
                if j - i > best_len:
                    best_len = j - i; best_start = i; best_rc = rc.find(seq[i:j])
    if best_len < 3: return ''
    s = seq; r = rc
    conn = [' '] * len(s)
    for k in range(best_len): conn[best_start + k] = '|'
    html = f'<div style="font-family:Consolas,monospace;font-size:11px;line-height:1.3;margin:2px 0;white-space:nowrap;overflow-x:auto">'
    html += f'<b>{label}</b> ({best_len}bp)<br>'
    html += f'5\' <span style="color:#e03131">{s[:best_start]}</span>'
    html += f'<span style="background:#ffe3e3;color:#c92a2a;font-weight:700">{s[best_start:best_start+best_len]}</span>'
    html += f'<span style="color:#e03131">{s[best_start+best_len:]}</span> 3\'<br>'
    html += f'&nbsp;&nbsp;&nbsp;{"".join(conn[:best_start])}<span style="color:#2b8a3e;font-weight:700">{"".join(conn[best_start:best_start+best_len])}</span>{"".join(conn[best_start+best_len:])}<br>'
    html += f'3\' <span style="color:#1971c2">{r[:best_rc]}</span>'
    html += f'<span style="background:#d0ebff;color:#1864ab;font-weight:700">{r[best_rc:best_rc+best_len]}</span>'
    html += f'<span style="color:#1971c2">{r[best_rc+best_len:]}</span> 5\'</div>'
    return html


def create_app():
    """创建 Flask 应用"""
    app = Flask(__name__)
    app.teardown_appcontext(close_db)
    app.config['JSON_AS_ASCII'] = False
    app.jinja_env.globals['_dimer_viz_html'] = _dimer_viz_html

    def _dimer_bp(seq):
        """计算自二聚体最长匹配bp数"""
        from Bio.Seq import Seq
        rc = str(Seq(seq).reverse_complement())
        best = 0
        for i in range(len(seq)):
            for j in range(i + 3, min(i + 13, len(seq) + 1)):
                if seq[i:j] in rc: best = max(best, j - i)
        return best

    def _cross_dimer_bp(fwd, rev):
        """计算Cross-Dimer最长匹配bp数"""
        from Bio.Seq import Seq
        rc_rev = str(Seq(rev).reverse_complement())
        best = 0
        for i in range(len(fwd)):
            for j in range(i + 3, min(i + 13, len(fwd) + 1)):
                if fwd[i:j] in rc_rev: best = max(best, j - i)
        return best

    app.jinja_env.globals['_dimer_bp'] = _dimer_bp
    app.jinja_env.globals['_cross_dimer_bp'] = _cross_dimer_bp

    # ── Primer Design Service ──
    design_mgr = None
    if DESIGN_SERVICE_AVAILABLE:
        from pathlib import Path as _Path
        design_mgr = DesignJobManager(
            jobs_dir=_Path("design_jobs"),
            species_fasta_dir=_Path("split_species/species")
        )
    app.config['design_mgr'] = design_mgr


    # ========== 首页 ==========
    @app.route('/')
    def index():
        db = get_db()
        c = db.cursor()

        c.execute('SELECT COUNT(*) FROM taxonomy')
        species_count = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM primers')
        primer_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM validation WHERE recommendation IN ('RECOMMENDED','PASS')")
        recommended_count = c.fetchone()[0]

        c.execute('SELECT COUNT(DISTINCT family) FROM taxonomy WHERE family != ""')
        families_count = c.fetchone()[0]

        # 每种类型的 TOP5 Species
        top_by_type = {}
        for ptype in ['PCR','qPCR','DEGENERATE','TILED']:
            c.execute('''
                SELECT t.species_name, COUNT(p.primer_id) as cnt,
                       ROUND(AVG(v.overall_score),1) as avg_score,
                       MAX(t.genome_length) as glen
                FROM primers p
                JOIN taxonomy t ON p.species_name = t.species_name
                JOIN validation v ON p.primer_id = v.primer_id
                WHERE p.primer_type = ?
                GROUP BY t.species_name
                ORDER BY avg_score DESC LIMIT 5
            ''', (ptype,))
            top_by_type[ptype] = [dict(r) for r in c.fetchall()]

        c.execute('SELECT primer_type FROM primers')
        type_dist = c.fetchall()

        return render_template_string(INDEX_TEMPLATE,
            species_count=species_count,
            primer_count=primer_count,
            primers_for_stats=[dict(r) for r in type_dist],
            recommended_count=recommended_count,
            families_count=families_count,
            top_by_type=top_by_type,
            year=datetime.now().year
        )

    # ========== 搜索 ==========
    @app.route('/search')
    def search():
        db = get_db()
        c = db.cursor()

        query = request.args.get('q', '').strip()
        type_filter = request.args.get('type', '').strip()
        method_filter = request.args.get('method', '').strip()
        rec_filter = request.args.get('recommendation', '').strip()
        family_filter = request.args.get('family', '').strip()

        where = ['1=1']
        params = []

        if query:
            terms = _expand_search_terms(query)
            sp_clauses = ' OR '.join(['p.species_name LIKE ?'] * len(terms))
            where.append(f'''({sp_clauses} OR t.genus LIKE ?
                          OR t.family LIKE ? OR p.fwd_sequence LIKE ?
                          OR p.rev_sequence LIKE ?)''')
            like_q = f'%{query}%'
            params.extend([f'%{t}%' for t in terms])
            params.extend([like_q, like_q, like_q, like_q])

        if type_filter:
            where.append('p.primer_type = ?')
            params.append(type_filter)

        if method_filter:
            where.append('p.design_method = ?')
            params.append(method_filter)

        if rec_filter:
            where.append('v.recommendation = ?')
            params.append(rec_filter)

        if family_filter:
            where.append('t.family = ?')
            params.append(family_filter)

        sql = f'''
            SELECT p.primer_id, p.species_name, p.primer_type, p.pair_id,
                   p.fwd_sequence, p.rev_sequence, p.probe_sequence,
                   p.product_size, p.gc_fwd, p.gc_rev,
                   t.genus, t.family, t.priority,
                   v.overall_score, v.recommendation, v.dimer_warning
            FROM primers p
            LEFT JOIN taxonomy t ON p.species_name = t.species_name
            LEFT JOIN validation v ON p.primer_id = v.primer_id
            WHERE {' AND '.join(where)}
            ORDER BY v.overall_score DESC, p.product_size ASC
            LIMIT 200
        '''

        c.execute(sql, params)
        results = [dict(r) for r in c.fetchall()]

        c.execute(f'''
            SELECT COUNT(*) FROM primers p
            LEFT JOIN taxonomy t ON p.species_name = t.species_name
            LEFT JOIN validation v ON p.primer_id = v.primer_id
            WHERE {' AND '.join(where)}
        ''', params)

        try:
            total = c.fetchone()[0]
        except Exception:
            total = len(results)

        return render_template_string(SEARCH_TEMPLATE,
            query=query, type_filter=type_filter, method_filter=method_filter, rec_filter=rec_filter,
            results=results, total=total, year=datetime.now().year
        )

    # ========== Species详情 ==========
    @app.route('/species/<path:species>')
    def species_detail(species):
        from urllib.parse import unquote
        species = unquote(species)
        db = get_db()
        c = db.cursor()

        c.execute('SELECT * FROM taxonomy WHERE species_name = ?', (species,))
        tax_row = c.fetchone()
        taxonomy = dict(tax_row) if tax_row else {}

        c.execute('''
            SELECT p.*, v.*
            FROM primers p
            LEFT JOIN validation v ON p.primer_id = v.primer_id
            WHERE p.species_name = ?
            ORDER BY v.overall_score DESC, p.pair_id ASC
        ''', (species,))
        primers_raw = c.fetchall()

        primers = []
        recommended_count = 0
        max_product = 0; max_tile = 0
        for row in primers_raw:
            d = dict(row)
            primers.append(d)
            if d.get('recommendation') in ('RECOMMENDED','PASS'):
                recommended_count += 1
            if (d.get('product_size') or 0) > max_product:
                max_product = d['product_size']
            if (d.get('tile_id') or 0) > max_tile:
                max_tile = d['tile_id']

        # genome长度估计
        est_genome_len = int(taxonomy.get('genome_length', 0) or 0)

        return render_template_string(SPECIES_TEMPLATE,
            species=species, taxonomy=taxonomy,
            primers=primers, recommended_count=recommended_count,
            est_genome_len=est_genome_len,
            year=datetime.now().year
        )

    # ========== In Silico PCR Amplicons计算 ==========
    BLAST_DIR = Path("designed_primers/blast")
    MAX_EPCR_AMP_LEN = 5000

    def _compute_epcr_amplicons(species, ptype, pair_id):
        """从 BLAST CSV 中提取配对amplicons（方向相向 + 距离 ≤ 5000bp）"""
        amplicons = []
        if not BLAST_DIR.exists():
            return amplicons
        # 匹配文件名: blast_{species}_{type}_{idx}.csv
        safe_sp = species.replace(' ', '_')[:30]
        pattern = f"blast_{safe_sp}_{ptype}_"
        csv_files = sorted(BLAST_DIR.glob(f"{pattern}*.csv"))
        if not csv_files:
            return amplicons

        try:
            # 读取所有匹配的CSV，找到属于此Primer Pairs的命中
            import pandas as _pd
            all_hits = []
            for cf in csv_files:
                df = _pd.read_csv(cf)
                all_hits.append(df)
            if not all_hits:
                return amplicons
            df = _pd.concat(all_hits, ignore_index=True)

            # 分离 FWD/REV
            fwd_hits = df[df['Direction'] == 'FWD']
            rev_hits = df[df['Direction'] == 'REV']

            # 按 Hit_ID 分组
            fwd_by_seq = {}
            for _, h in fwd_hits.iterrows():
                sid = h['Hit_ID']
                fwd_by_seq.setdefault(sid, []).append(h)
            rev_by_seq = {}
            for _, h in rev_hits.iterrows():
                sid = h['Hit_ID']
                rev_by_seq.setdefault(sid, []).append(h)

            # 找配对amplicons
            for sid in set(fwd_by_seq.keys()) & set(rev_by_seq.keys()):
                if sid in {'nan', 'None', ''}: continue
                for _, fh in fwd_by_seq[sid].iterrows():
                    for _, rh in rev_by_seq[sid].iterrows():
                        f_plus = fh['Sstart'] < fh['Send']
                        r_plus = rh['Sstart'] < rh['Send']
                        if f_plus == r_plus:
                            continue  # Same direction → cannot amplify
                        coords = [fh['Sstart'], fh['Send'], rh['Sstart'], rh['Send']]
                        amp_len = max(coords) - min(coords)
                        if amp_len > MAX_EPCR_AMP_LEN:
                            continue
                        is_target = fh.get('Is_Target', False) or rh.get('Is_Target', False)
                        is_plant = fh.get('Is_Plant', False) or rh.get('Is_Plant', False)
                        amplicons.append({
                            'seq_id': str(sid)[:60],
                            'amp_len': int(amp_len),
                            'desc': str(fh.get('Hit_Description', ''))[:80],
                            'is_target': bool(is_target),
                            'is_plant': bool(is_plant)
                        })
        except Exception:
            pass

        # 去重排序
        seen = set()
        uniq = []
        for a in amplicons:
            key = (a['seq_id'], a['amp_len'])
            if key not in seen:
                seen.add(key)
                uniq.append(a)
        uniq.sort(key=lambda x: (not x['is_target'], x['amp_len']))
        return uniq[:50]

    # ========== 引物详情 ==========
    @app.route('/primer/<int:primer_id>')
    def primer_detail(primer_id):
        db = get_db()
        c = db.cursor()

        c.execute('SELECT * FROM primers WHERE primer_id = ?', (primer_id,))
        p_row = c.fetchone()
        if not p_row:
            return "Primer not found", 404

        c.execute('SELECT * FROM validation WHERE primer_id = ?', (primer_id,))
        v_row = c.fetchone()

        p = dict(p_row)
        v = dict(v_row) if v_row else None

        # genome长度
        c.execute('SELECT genome_length FROM taxonomy WHERE species_name = ?',
                  (p.get('species_name', ''),))
        tax_row = c.fetchone()
        genome_len = tax_row['genome_length'] if tax_row else 0

        # In Silico PCR Amplicons
        epcr = _compute_epcr_amplicons(
            p.get('species_name', ''), p.get('primer_type', ''), p.get('pair_id', '')
        )

        return render_template_string(PRIMER_DETAIL_TEMPLATE,
            p=p, v=v, epcr=epcr, genome_len=genome_len, year=datetime.now().year
        )

    # ========== 浏览 ==========
    @app.route('/browse')
    def browse():
        db = get_db()
        c = db.cursor()

        c.execute('''
            SELECT t.species_name, t.genus, t.family, t.priority,
                   COUNT(p.primer_id) as primer_count,
                   ROUND(AVG(v.overall_score), 1) as avg_score
            FROM taxonomy t
            LEFT JOIN primers p ON t.species_name = p.species_name
            LEFT JOIN validation v ON p.primer_id = v.primer_id
            GROUP BY t.species_name
            ORDER BY t.priority DESC, avg_score DESC
            LIMIT 500
        ''')
        species_list = [dict(r) for r in c.fetchall()]

        return render_template_string(BROWSE_TEMPLATE,
            species_list=species_list, year=datetime.now().year
        )

    # ========== 下载 ==========
    @app.route('/download')
    def download():
        return render_template_string(BASE_TEMPLATE.replace(
            '{% block content %}{% endblock %}',
            '''{% block content %}
            <h2 class="mt-4"><i class="bi-download"></i> Data Download</h2>
            <div class="row g-4 mt-2">
                <div class="col-md-4">
                    <div class="card"><div class="card-body text-center">
                        <i class="bi-filetype-fasta" style="font-size:3em;color:#198754"></i>
                        <h5 class="mt-2">All Primers FASTA</h5>
                        <p class="text-muted">FASTA format of all recommended primers</p>
                        <a href="/api/all_primers?format=fasta" class="btn btn-success">Download</a>
                    </div></div>
                </div>
                <div class="col-md-4">
                    <div class="card"><div class="card-body text-center">
                        <i class="bi-filetype-csv" style="font-size:3em;color:#0d6efd"></i>
                        <h5 class="mt-2">Primer List CSV</h5>
                        <p class="text-muted">Complete primer info table</p>
                        <a href="/api/all_primers?format=csv" class="btn btn-primary">Download</a>
                    </div></div>
                </div>
                <div class="col-md-4">
                    <div class="card"><div class="card-body text-center">
                        <i class="bi-database" style="font-size:3em;color:#6f42c1"></i>
                        <h5 class="mt-2">SQLite Database</h5>
                        <p class="text-muted">Full database file</p>
                        <a href="/api/database" class="btn btn-secondary">Download</a>
                    </div></div>
                </div>
            </div>
            {% endblock %}'''
        ), year=datetime.now().year)

    # ========== API 接口 ==========
    @app.route('/api/')
    def api_docs():
        return jsonify({
            "name": "PlantVirus Primer DB API",
            "version": "1.0.0",
            "endpoints": {
                "/api/species/<name>": "Get primers by species (supports ?format=json|fasta|csv)",
                "/api/primer/<id>": "Get primer details by ID (supports ?format=json|fasta)",
                "/api/search": "Search primers (?q=keyword&type=PCR&recommendation=RECOMMENDED)",
                "/api/all_primers": "Get all primers (?format=csv|fasta&recommendation=RECOMMENDED)",
                "/api/stats": "Get database statistics",
                "/api/database": "Download SQLite Database file",
                "/api/taxonomy/<name>": "Get taxonomy information"
            }
        })

    @app.route('/api/species/<path:species>')
    def api_species(species):
        from urllib.parse import unquote
        species = unquote(species)
        fmt = request.args.get('format', 'json')
        db = get_db()
        c = db.cursor()

        c.execute('''
            SELECT p.*, v.* FROM primers p
            LEFT JOIN validation v ON p.primer_id = v.primer_id
            WHERE p.species_name = ?
            ORDER BY v.overall_score DESC
        ''', (species,))
        results = [dict(r) for r in c.fetchall()]

        if fmt == 'fasta':
            fasta_lines = []
            for r in results:
                fasta_lines.append(
                    f">{species}|{r['primer_type']}|{r['pair_id']}|FWD "
                    f"score={r.get('overall_score','NA')}"
                )
                fasta_lines.append(r['fwd_sequence'])
                fasta_lines.append(
                    f">{species}|{r['primer_type']}|{r['pair_id']}|REV "
                    f"score={r.get('overall_score','NA')}"
                )
                fasta_lines.append(r['rev_sequence'])
            return '\n'.join(fasta_lines), 200, {'Content-Type': 'text/plain; charset=utf-8'}

        if fmt == 'csv':
            import io
            output = io.StringIO()
            output.write("Species\tType\tPair\tForward\tReverse\tProductSize\tScore\tRecommendation\n")
            for r in results:
                output.write(f"{species}\t{r['primer_type']}\t{r['pair_id']}\t"
                           f"{r['fwd_sequence']}\t{r['rev_sequence']}\t"
                           f"{r['product_size']}\t{r.get('overall_score','')}\t"
                           f"{r.get('recommendation','')}\n")
            return output.getvalue(), 200, {
                'Content-Type': 'text/csv; charset=utf-8',
                'Content-Disposition': f'attachment; filename={species}_primers.csv'
            }

        return jsonify(results)

    @app.route('/api/primer/<int:primer_id>')
    def api_primer(primer_id):
        fmt = request.args.get('format', 'json')
        db = get_db()
        c = db.cursor()

        c.execute('''
            SELECT p.*, v.* FROM primers p
            LEFT JOIN validation v ON p.primer_id = v.primer_id
            WHERE p.primer_id = ?
        ''', (primer_id,))
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404

        result = dict(row)

        if fmt == 'fasta':
            fasta = (
                f">{result['species_name']}|{result['primer_type']}|FWD "
                f"score={result.get('overall_score','NA')}\n"
                f"{result['fwd_sequence']}\n"
                f">{result['species_name']}|{result['primer_type']}|REV "
                f"score={result.get('overall_score','NA')}\n"
                f"{result['rev_sequence']}\n"
            )
            if result.get('probe_sequence'):
                fasta += (
                    f">{result['species_name']}|{result['primer_type']}|PROBE\n"
                    f"{result['probe_sequence']}\n"
                )
            return fasta, 200, {'Content-Type': 'text/plain; charset=utf-8'}

        return jsonify(result)

    @app.route('/api/search')
    def api_search():
        query = request.args.get('q', '').strip()
        ptype = request.args.get('type', '').strip()
        recommendation = request.args.get('recommendation', '').strip()
        limit = min(int(request.args.get('limit', 100)), 1000)

        db = get_db()
        c = db.cursor()
        where = ['1=1']
        params = []

        if query:
            terms = _expand_search_terms(query)
            where.append('(' + ' OR '.join(['p.species_name LIKE ?'] * len(terms)) + ')')
            params.extend([f'%{t}%' for t in terms])
        if ptype:
            where.append('p.primer_type = ?')
            params.append(ptype)
        if recommendation:
            where.append('v.recommendation = ?')
            params.append(recommendation)

        c.execute(f'''
            SELECT p.*, v.* FROM primers p
            LEFT JOIN validation v ON p.primer_id = v.primer_id
            WHERE {' AND '.join(where)}
            ORDER BY v.overall_score DESC
            LIMIT ?
        ''', params + [limit])

        return jsonify([dict(r) for r in c.fetchall()])

    @app.route('/api/all_primers')
    def api_all_primers():
        fmt = request.args.get('format', 'json')
        recommendation = request.args.get('recommendation', '').strip()

        db = get_db()
        c = db.cursor()

        if recommendation:
            c.execute('''
                SELECT p.*, v.* FROM primers p
                LEFT JOIN validation v ON p.primer_id = v.primer_id
                WHERE v.recommendation = ?
                ORDER BY v.overall_score DESC
            ''', (recommendation,))
        else:
            c.execute('''
                SELECT p.*, v.* FROM primers p
                LEFT JOIN validation v ON p.primer_id = v.primer_id
                ORDER BY v.overall_score DESC
            ''')

        results = [dict(r) for r in c.fetchall()]

        if fmt == 'fasta':
            fasta_lines = []
            for r in results:
                fasta_lines.append(
                    f">{r['species_name']}|{r['primer_type']}|{r['pair_id']}|FWD"
                )
                fasta_lines.append(r['fwd_sequence'])
                fasta_lines.append(
                    f">{r['species_name']}|{r['primer_type']}|{r['pair_id']}|REV"
                )
                fasta_lines.append(r['rev_sequence'])
            return '\n'.join(fasta_lines), 200, {
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Disposition': 'attachment; filename=all_plant_virus_primers.fasta'
            }

        if fmt == 'csv':
            import io
            output = io.StringIO()
            output.write("Species\tType\tPair\tForward(5'-3')\tReverse(5'-3')\t"
                        "ProductSize\tScore\tRecommendation\n")
            for r in results:
                output.write(f"{r['species_name']}\t{r['primer_type']}\t{r['pair_id']}\t"
                           f"{r['fwd_sequence']}\t{r['rev_sequence']}\t"
                           f"{r['product_size']}\t{r.get('overall_score','')}\t"
                           f"{r.get('recommendation','')}\n")
            return output.getvalue(), 200, {
                'Content-Type': 'text/csv; charset=utf-8',
                'Content-Disposition': 'attachment; filename=all_plant_virus_primers.csv'
            }

        return jsonify(results[:500])  # JSON limit 500 records

    @app.route('/api/stats')
    def api_stats():
        db = get_db()
        c = db.cursor()

        c.execute('SELECT COUNT(*) FROM taxonomy')
        species_count = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM primers')
        primer_count = c.fetchone()[0]

        c.execute('SELECT primer_type, COUNT(*) as count FROM primers GROUP BY primer_type')
        type_counts = [dict(r) for r in c.fetchall()]

        c.execute('SELECT recommendation, COUNT(*) as count FROM validation GROUP BY recommendation')
        rec_counts = [dict(r) for r in c.fetchall()]

        c.execute('SELECT COUNT(DISTINCT family) FROM taxonomy WHERE family != ""')
        family_count = c.fetchone()[0]

        return jsonify({
            "total_species": species_count,
            "total_primers": primer_count,
            "total_families": family_count,
            "by_type": type_counts,
            "by_recommendation": rec_counts
        })

    @app.route('/api/database')
    def api_database():
        if DB_PATH.exists():
            return send_file(
                str(DB_PATH),
                mimetype='application/octet-stream',
                as_attachment=True,
                download_name='plant_virus_primers.db'
            )
        return jsonify({"error": "Database not found"}), 404

    @app.route('/api/taxonomy/<path:name>')
    def api_taxonomy(name):
        from urllib.parse import unquote
        name = unquote(name)
        db = get_db()
        c = db.cursor()
        c.execute('SELECT * FROM taxonomy WHERE species_name LIKE ?', (f'%{name}%',))
        results = [dict(r) for r in c.fetchall()]
        return jsonify(results)

    # ========== AI 助手 API ==========
    @app.route('/api/chat', methods=['POST'])
    def api_chat():
        import requests
        data = request.get_json(force=True)
        user_msg = data.get('message', '').strip()
        api_key = data.get('api_key', '').strip()
        api_url = data.get('api_url', 'https://api.deepseek.com/v1/chat/completions').strip()
        model = data.get('model', 'deepseek-chat').strip()
        conversation = data.get('conversation', [])

        # 使用用户提供的 key，或服务器预配置的 key
        if not api_key:
            api_key = SERVER_AI_CONFIG.get("AI_API_KEY", "")
        if not api_url or api_url == "https://api.deepseek.com/v1/chat/completions":
            api_url = SERVER_AI_CONFIG.get("AI_API_URL", api_url)
        if not model or model == "deepseek-chat":
            model = SERVER_AI_CONFIG.get("AI_MODEL", model)

        if not user_msg or not api_key:
            return jsonify({"reply": "API Key not configured. Click ⚙ to set, or contact admin for server-side config."})

        context = data.get('context', 'primers')
        db = get_db()
        c = db.cursor()

        # Real-time stats injected into the AI context
        c.execute('SELECT COUNT(*) FROM primers')
        total_primers = c.fetchone()[0]
        c.execute('SELECT COUNT(DISTINCT species_name) FROM primers')
        total_species = c.fetchone()[0]
        c.execute('SELECT primer_type, COUNT(*) FROM primers GROUP BY primer_type')
        type_stats = dict(c.fetchall())
        c.execute('SELECT recommendation, COUNT(*) FROM validation GROUP BY recommendation')
        rec_stats = dict(c.fetchall())
        c.execute('SELECT COUNT(*) FROM taxonomy')
        total_tax_species = c.fetchone()[0]
        c.execute('SELECT COUNT(DISTINCT family) FROM taxonomy')
        total_tax_families = c.fetchone()[0]

        # Species intent: scan the message against the NAME_MAP alias dictionary
        # (Latin names / common names / acronyms), resolve each hit to its ICTV
        # canonical name, then pull that species' records from the DB. Replaces the
        # old trigger-word regex, which missed most phrasings in either language and
        # silently degraded to "no database context" whenever species had been
        # migrated to canonical names.
        extra_info = ""
        canon_list = []
        try:
            for canon, matched in _extract_species_from_message(user_msg):
                canon_list.append(canon)
                c.execute("SELECT species_name, genus, family, genome_length FROM taxonomy WHERE species_name = ? LIMIT 1", (canon,))
                row = c.fetchone()
                if row is None:
                    c.execute("SELECT species_name, genus, family, genome_length FROM taxonomy WHERE species_name LIKE ? LIMIT 1", (f'%{canon}%',))
                    row = c.fetchone()
                if row is None:
                    continue
                r = dict(row)
                sp = r['species_name']
                if not extra_info:
                    extra_info = "\n\n[Species records resolved from the user's message — answer from these]:\n"
                extra_info += f'- DB species: {sp}'
                if sp != canon:
                    extra_info += f' (canonical form of "{matched}")'
                else:
                    extra_info += f' (user wrote: "{matched}")'
                extra_info += f' | {r.get("genus") or "genus n/a"} / {r.get("family") or "family n/a"} | genome {r.get("genome_length") or "?"} nt\n'
                c.execute("SELECT primer_type, COUNT(*) as cnt FROM primers WHERE species_name=? GROUP BY primer_type", (sp,))
                pt = dict(c.fetchall())
                c.execute("SELECT recommendation, COUNT(*) FROM validation v JOIN primers p USING(primer_id) WHERE p.species_name=? GROUP BY recommendation", (sp,))
                rt = dict(c.fetchall())
                extra_info += f"  Primer types: {pt}; Score distribution: {rt}\n"
                c.execute('''SELECT p.primer_type, p.fwd_sequence, p.rev_sequence, p.probe_sequence,
                                    p.product_size, p.gc_fwd, p.gc_rev, p.design_method,
                                    v.overall_score, v.recommendation
                             FROM primers p JOIN validation v USING(primer_id)
                             WHERE p.species_name=? ORDER BY v.overall_score DESC LIMIT 5''', (sp,))
                for t in [dict(x) for x in c.fetchall()]:
                    extra_info += f"    [{t['primer_type']}] Fwd={t['fwd_sequence']} Rev={t['rev_sequence']}"
                    if t.get('probe_sequence'): extra_info += f" Probe={t['probe_sequence']}"
                    extra_info += f" | {t['product_size']}bp | GC={t.get('gc_fwd','')}/{t.get('gc_rev','')} | Score={t['overall_score']} {t['recommendation']}\n"
        except Exception as e:
            app.logger.warning("[api/chat] species lookup failed: %s", e)

        # 跨库取数：媒介-宿主 + 症状照片 + 站内深链（解析到物种时附加）
        xlib_info = ""
        if canon_list:
            try:
                xlib_info = _cross_db_info(canon_list, request.host_url.rstrip('/'), zh=False)
            except Exception as e:
                app.logger.warning("[api/chat] cross-db lookup failed: %s", e)

        # Knowledge-base grounding for explorer / reference_db contexts: retrieval
        # only from the local RAG service (no extra LLM call, safe to fail).
        kb_info = ""
        try:
            rr = requests.get(KB_SEARCH_URL, params={"q": user_msg, "limit": 3}, timeout=8)
            if rr.status_code == 200:
                items = (rr.json() or {}).get("results") or []
                if items:
                    kb_info = "\n\n[Knowledge base fragments — ground virus-biology answers in these and cite the [SOURCE]]:\n"
                    for k, it in enumerate(items, 1):
                        kb_info += f"[{k}] ({it.get('source', '')}) {it.get('title', '')}: {(it.get('text') or '')[:600]}\n"
        except Exception as e:
            app.logger.warning("[api/chat] KB retrieval failed: %s", e)

        if context == 'reference_db':
            db_context = f"""You are the AI assistant for the Plant Virus Reference Database. The full reference set holds ~199k plant-virus sequences (NCBI GenBank + RefSeq, deduplicated at 95% identity to ~8,465 non-redundant sequences) covering ~6,200 species per ICTV VMR.
Real-time canonical species table on this server: {total_tax_species} species in {total_tax_families} families; primer layer: {total_primers} primer pairs covering {total_species} species.

You can help users with:
1. Answering plant virus taxonomy questions (Realm/Kingdom/Phylum/Class/Order/Family/Genus/Species)
2. Explaining the difference between segmented and non-segmented viruses
3. Guiding virus host information queries
4. Explaining genome types (dsDNA/ssDNA/dsRNA/ssRNA+/ssRNA-, etc.)
5. Describing the database construction method and data sources

Notes:
- Species are stored under ICTV canonical binomials (e.g. "Tomato yellow leaf curl virus" → "Begomovirus coheni"); common names/acronyms in the user's message are resolved automatically and matching DB records are attached below when found.
- If knowledge base fragments are attached below, ground biology answers in them and cite the sources; if they are insufficient, say so instead of fabricating.
- Cross-database records (vector-host, symptom photos) and deep links may also be attached; use them the same way and end with the "Relevant pages:" section.
- If users need specific sequences or primers, guide them to the Primers database (/primers/); for visual analysis, Explorer (/explorer/); for literature, Knowledge Base (/knowledge/).
- Keep replies concise, under 200 words"""
        elif context == 'explorer':
            kpis = ((SITE_FACTS.get('full') or {}).get('kpis') or {}) if SITE_FACTS else {}
            top_hosts = ((SITE_FACTS.get('full') or {}).get('topHosts') or []) if SITE_FACTS else []
            hosts_txt = ', '.join(f"{h} ({c})" for h, c in top_hosts[:5]) or 'n/a'
            db_context = f"""You are the AI assistant for the Plant Virus Explorer (spatiotemporal visualization of plant virus sequences).
Site facts (precomputed from the full reference dataset): {kpis.get('sequences', '~199k')} sequences, {kpis.get('taxids', '~6.2k')} species, {kpis.get('families', '~49')} families; top hosts: {hosts_txt}.
Real-time on this server: {total_tax_species} species / {total_tax_families} families in the canonical species table; {total_primers} primer pairs covering {total_species} species, by type {type_stats}.

You can help users with:
1. Explaining how to use the Explorer's features
2. Interpreting spatiotemporal distribution maps and CP gene variation analysis
3. Answering questions about virus diversity and host distribution
4. Providing guidance on data filtering and export

Notes:
- Data boundary: interactive queries (maps, BLAST/alignment, CP variation) run inside the Explorer pages themselves; you answer from the stats above and any knowledge base fragments attached below.
- If knowledge base fragments are attached below, ground biology answers in them and cite the sources; otherwise say when you are not certain.
- Cross-database records (vector-host, symptom photos) and deep links may also be attached; use them the same way and end with the "Relevant pages:" section.
- When species records with primer sequences are attached after the user's message, list the primers directly (one per line: [Type] Fwd/Rev, product bp, score); only for further filtering or downloads point to Primers (/primers/); raw data tables are in Reference DB (/reference/).
- Keep replies concise, under 200 words"""
        else:
            db_context = f"""You are the AI assistant for the Plant Virus Primer Database (PrimerDB). You have access to the following real-time data:
- Total primer pairs: {total_primers}
- Total species: {total_species}
- By type: {type_stats}
- By score: {rec_stats}

You can help users with:
1. Searching for primers for a specific species (use URL /search?q=species_name)
2. Comparing advantages of different primer types
3. Explaining validation score meanings (RECOMMENDED>=80, USABLE 60-79, NOT_RECOMMENDED<60)
4. Recommending best primers for specific viruses
5. Answering primer design questions

Notes:
- Species are stored under ICTV canonical binomials (e.g. "Tomato yellow leaf curl virus" → "Begomovirus coheni"). When species records are attached after the user's message, answer from them directly and mention the canonical name used.
- Vector-host relationships, symptom photos and deep links are also attached when a species is resolved: weave relevant ones into the answer and end with a "Relevant pages:" section quoting the provided URLs verbatim.

Reply format requirements:
1. No Markdown tables; use concise plain-text lists. One primer per line.
2. For Top 5 primers, give sequences directly: "[Type] Fwd:XXX Rev:XXX | Product bp | Score XX"
3. When analyzing primers, list only key metrics: Tm/GC/dimers/specificity, no more than 3 lines per primer pair.
4. Keep replies concise, under 300 words.
5. If species records with primer sequences are attached after the user's message, list ALL sequences without omission.

The database is accessed via SQLite with schema: taxonomy(species_name,genus,family), primers(primer_id,species_name,primer_type,fwd_sequence,rev_sequence,probe_sequence,product_size,design_method), validation(primer_id,overall_score,recommendation,probe_warning)."""

        messages = [
            {"role": "system", "content": db_context},
        ]
        for item in conversation[-10:]:
            messages.append(item)
        messages.append({"role": "user", "content": user_msg + extra_info + xlib_info + kb_info})

        try:
            resp = requests.post(api_url, json={
                "model": model, "messages": messages,
                "temperature": 0.3, "max_tokens": 800
            }, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }, timeout=30)
            if resp.status_code == 200:
                reply = resp.json()['choices'][0]['message']['content']
            else:
                reply = f"API Error ({resp.status_code}): {resp.text[:200]}"
        except Exception as e:
            reply = f"Connection failed: {str(e)[:200]}"

        return jsonify({"reply": reply})


    # ── Design routes moved to /metabuli/primer_design ──

    return app


def main():
    global DB_PATH
    parser = argparse.ArgumentParser(description="Start Plant Virus Primer Database Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=5000, help="Listen port")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite database path")
    args = parser.parse_args()
    DB_PATH = Path(args.db)

    if not DB_PATH.exists():
        print(f"⚠ Database not found: {DB_PATH}")
        print("  Run first: python step4_build_database.py")
        print("  Or use --db to specify existing database path")
        print("\n  Starting in empty-database mode (limited functionality)...")
        # Create empty database
        conn = sqlite3.connect(str(DB_PATH))
        conn.close()

    app = create_app()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║          Plant Virus Primer Database Web Server              ║
║                                                              ║
║  URL: http://localhost:{args.port}                              ║
║  API: http://localhost:{args.port}/api/                         ║
║                                                              ║
║  Pages:                                                       ║
║    /           — Home (overview + quick search)               ║
║    /search     — Search primers                              ║
║    /browse     — Browse species list                         ║
║    /species/X  — Species detail + primer list                ║
║    /primer/ID  — Primer detail + validation results          ║
║    /download   — Download data                               ║
║                                                              ║
║  API:                                                        ║
║    /api/species/<name>?format=json|fasta|csv                   ║
║    /api/primer/<id>?format=json|fasta                         ║
║    /api/search?q=<keyword>&type=PCR&recommendation=RECOMMENDED ║
║    /api/all_primers?format=csv|fasta                          ║
║    /api/stats                                                ║
║    /api/database                                             ║
╚══════════════════════════════════════════════════════════════╝
    """)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
