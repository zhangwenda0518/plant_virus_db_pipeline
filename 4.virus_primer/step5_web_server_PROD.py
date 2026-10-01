#!/usr/bin/env python3
"""
Step 5: 植物病毒引物数据库 Web 界面
========================================================================
基于 Flask 的 Web 应用，提供:

  功能:
    1. 首页 — 数据库概览 + 快速搜索
    2. 搜索页 — 按物种/属/科/类型/评分搜索引物
    3. 物种详情页 — 某物种的所有引物 (含验证信息)
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
    tokens = _re.findall(r"[A-Za-z][A-Za-z0-9\-']*", msg)
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


# Design service imports
try:
    from primer_design_service import DesignJobManager
    DESIGN_SERVICE_AVAILABLE = True
except ImportError:
    DESIGN_SERVICE_AVAILABLE = False

# Flask 可能未安装
try:
    from flask import Flask, request, jsonify, render_template_string, g, send_file
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


# ======================================================================
# HTML 模板 (内嵌, 无需外部模板文件)
# ======================================================================

BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}植物病毒引物数据库{% endblock %}</title>
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
                <i class="bi-virus"></i> PlantVirus Primer DB
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item"><a class="nav-link" href="/"><i class="bi-house"></i> 首页</a></li>
                    <li class="nav-item"><a class="nav-link" href="/search"><i class="bi-search"></i> 搜索</a></li>
                    <li class="nav-item"><a class="nav-link" href="/primers/design"><i class="bi-pencil-square"></i> 设计</a></li>
                    <li class="nav-item"><a class="nav-link" href="/browse"><i class="bi-list"></i> 浏览</a></li>
                    <li class="nav-item"><a class="nav-link" href="/api/"><i class="bi-code"></i> API</a></li>
                    <li class="nav-item"><a class="nav-link" href="/download"><i class="bi-download"></i> 下载</a></li>
                    <li class="nav-item"><a class="nav-link" href="/reference/" style="color:#81c784"><i class="bi-arrow-left-right"></i> Reference DB</a></li>
                    <li class="nav-item"><a class="nav-link" href="/explorer/" style="color:#64b5f6"><i class="bi-arrow-left-right"></i> Explorer</a></li>
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
                alert('已复制!');
            });
        }
    </script>
    {% block scripts %}{% endblock %}
    <!-- AI Chat -->
    <button id="ai-chat-btn" onclick="toggleChat()" title="AI助手">?</button>
    <div id="ai-chat-panel">
        <div class="chat-header"><span>PrimerDB AI助手</span><div><button onclick="toggleSettings()" style="background:none;border:none;color:#fff;font-size:14px;cursor:pointer;margin-right:8px" title="设置">⚙</button><button onclick="toggleChat()">×</button></div></div>
        <div id="ai-settings-inline" style="display:none;padding:10px 12px;border-bottom:1px solid #eee;background:#f8f9fa">
            <div style="display:flex;gap:6px;flex-wrap:wrap">
                <input id="ai-api-key" type="password" placeholder="API Key (sk-...)" style="flex:1;min-width:120px;padding:5px 8px;border:1px solid #dee2e6;border-radius:4px;font-size:11px">
                <input id="ai-model" value="deepseek-chat" style="width:120px;padding:5px 8px;border:1px solid #dee2e6;border-radius:4px;font-size:11px">
                <button onclick="saveAISettings()" style="padding:5px 10px;background:#667eea;color:#fff;border:none;border-radius:4px;font-size:11px;cursor:pointer">保存</button>
            </div>
        </div>
        <div class="preset-qs" id="preset-qs">
<button class="preset-q" onclick="askPreset('TSWV的最佳PCR引物有哪些？')">TSWV最佳PCR引物</button>
<button class="preset-q" onclick="askPreset('推荐检测TMV的qPCR引物')">TMV的qPCR引物</button>
<button class="preset-q" onclick="askPreset('比较PCR和qPCR引物的优缺点')">PCR vs qPCR对比</button>
<button class="preset-q" onclick="askPreset('引物评分RECOMMENDED是什么意思？')">引物评分说明</button>
</div>
        <div class="chat-msgs" id="chat-msgs"><div class="chat-msg system">你好！我是PrimerDB AI助手。可以直接点下方预设问题，或输入你的问题。</div></div>
        <div class="chat-input-row">
            <input id="chat-input" placeholder="输入问题..." onkeydown="if(event.key==='Enter')sendMsg()">
            <button onclick="sendMsg()">发送</button></div>
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
        addChatMsg('system', '设置已保存');
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
        div.textContent = text;
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
            addChatMsg('system', '请求失败: ' + e.message);
        }
    }
    </script>
    <script src="/reference/i18n.js"></script>
    <script>PVDB_i18n.init({navSelector:'nav.navbar,.navbar'});</script>
</body>
</html>
'''


INDEX_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''{% block content %}
<div class="row mt-4">
    <div class="col-12">
        <div class="p-5 mb-4 bg-success text-white rounded">
            <h1><i class="bi-virus2"></i> 植物病毒引物数据库</h1>
            <p class="lead">
                为 {{ species_count }} 种植物病毒设计了 {{ primer_count }} 对 PCR/qPCR 引物，
                覆盖植物病毒主要科属，支持保守区检测、简并引物和多重平铺扩增。
            </p>
            <form action="/search" method="GET" class="row g-2">
                <div class="col-md-8">
                    <input type="text" name="q" class="form-control form-control-lg"
                           placeholder="输入病毒名称搜索... (例如: Tobacco Mosaic Virus, Potyvirus)">
                </div>
                <div class="col-md-4">
                    <button type="submit" class="btn btn-light btn-lg w-100">
                        <i class="bi-search"></i> 搜索引物
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>

<div class="row g-4 mb-4">
    <div class="col-md-3"><div class="card card-stat bg-white">
            <div class="number text-warning">{{ families_count }}</div>
            <div class="text-muted">病毒科</div>
        </div>
    </div>
    <div class="col-md-3"><div class="card card-stat bg-white">
            <div class="number text-primary">{{ species_count }}</div>
            <div class="text-muted">病毒物种</div>
        </div>
    </div>
    <div class="col-md-3"><div class="card card-stat bg-white">
            <div class="number text-success">{{ primer_count }}</div>
            <div class="text-muted">引物对</div>
        </div>
    </div>
    <div class="col-md-3"><div class="card card-stat bg-white">
            <div class="number text-info">{{ recommended_count }}</div>
            <div class="text-muted">推荐引物</div>
        </div>
    </div>

<div class="row mt-3">
    <div class="col-md-8">
        <div class="card mb-4">
            <div class="card-header fw-bold"><i class="bi-lightning"></i> 快速入口</div>
            <div class="card-body">
                <div class="row">
                <div class="col-md-4"><h6>按引物类型</h6>
                    <a href="/search?type=PCR" class="btn btn-outline-primary btn-sm d-block mb-1">PCR 常规检测</a>
                    <a href="/search?type=qPCR" class="btn btn-outline-info btn-sm d-block mb-1">qPCR 荧光定量</a>
                    <a href="/search?type=DEGENERATE" class="btn btn-outline-warning btn-sm d-block mb-1">简并引物</a>
                    <a href="/search?type=TILED" class="btn btn-outline-secondary btn-sm d-block">全基因组平铺</a></div>
                <div class="col-md-4"><h6>按评分</h6>
                    <a href="/search?recommendation=RECOMMENDED" class="btn btn-outline-success btn-sm d-block mb-1">推荐使用 (>=80分)</a>
                    <a href="/search?recommendation=USABLE" class="btn btn-outline-warning btn-sm d-block">可用 (60-79分)</a></div>
                <div class="col-md-4"><h6>数据下载</h6>
                    <a href="/download" class="btn btn-outline-dark btn-sm d-block mb-1">下载页面</a>
                    <a href="/api/all_primers?format=csv" class="btn btn-outline-dark btn-sm d-block">导出全部 CSV</a></div>
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card mb-4">
            <div class="card-header fw-bold"><i class="bi-bar-chart"></i> 引物类型分布</div>
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
    <div class="card-header fw-bold"><i class="bi-trophy"></i> 各类型评分最高物种 TOP5</div>
    <div class="card-body">
        <div class="row">
        {% set type_names = {'PCR':'PCR 常规检测','qPCR':'qPCR 荧光定量','DEGENERATE':'简并引物','TILED':'全基因组平铺'} %}
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
<h2 class="mt-4"><i class="bi-search"></i> 搜索引物</h2>

<form action="/search" method="GET" class="row g-3 mb-4 bg-light p-3 rounded">
    <div class="col-md-4">
        <label class="form-label">病毒名称/物种</label>
        <input type="text" name="q" class="form-control" value="{{ query or '' }}"
               placeholder="输入物种名、属名或科名">
    </div>
    <div class="col-md-2">
        <label class="form-label">引物类型</label>
        <select name="type" id="typeSelect" onchange="filterMethods()" class="form-select">
            <option value="">全部</option>
            {% for t in ['PCR', 'qPCR', 'DEGENERATE', 'TILED'] %}
            <option value="{{ t }}" {% if type_filter == t %}selected{% endif %}>{{ t }}</option>
            {% endfor %}
        </select>
    </div>
    <div class="col-md-2">
        <label class="form-label">设计工具</label>
        <select name="method" id="methodSelect" class="form-select">
            <option value="">全部</option>
            {% for m in ['Primer3','Simple_Thermo','Primer3_qPCR','IUPAC_Degenerate','varVAMP','Olivar','varVAMP_tiled','PrimerForge'] %}
            <option value="{{ m }}" {% if method_filter == m %}selected{% endif %}>{{ m }}</option>
            {% endfor %}
        </select>
    </div>
    <div class="col-md-2">
        <label class="form-label">推荐级别</label>
        <select name="recommendation" class="form-select">
            <option value="">全部</option>
            {% for r in ['RECOMMENDED', 'USABLE', 'CAUTION', 'NOT_RECOMMENDED'] %}
            <option value="{{ r }}" {% if rec_filter == r %}selected{% endif %}>{{ r }}</option>
            {% endfor %}
        </select>
    </div>
    <div class="col-md-2 d-flex align-items-end">
        <button type="submit" class="btn btn-primary w-100">
            <i class="bi-search"></i> 搜索
        </button>
    </div>
</form>

{% if results %}
<div class="alert alert-info">
    找到 <strong>{{ total }}</strong> 对引物 (显示前 {{ results|length }} 对)
</div>

<div class="table-responsive">
<table class="table table-hover table-primer">
    <thead class="table-dark">
        <tr>
            <th>物种</th>
            <th>类型</th>
            <th>正向引物 (5'→3')</th>
            <th>反向引物 (5'→3')</th>
            <th>产物</th>
            <th>评分</th>
            <th>操作</th>
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
            <button class="copy-btn btn btn-sm btn-outline-secondary" onclick="copyToClipboard('{{ r.fwd_sequence }}')" title="复制">📋</button>
        </td>
        <td><span class="primer-seq">{{ r.rev_sequence }}</span>
            <button class="copy-btn btn btn-sm btn-outline-secondary" onclick="copyToClipboard('{{ r.rev_sequence }}')" title="复制">📋</button>
        </td>
        <td>{{ r.product_size }}bp</td>
        <td>
            <span class="score-badge {{ 'recommended' if r.recommendation in ('RECOMMENDED','PASS') else 'usable' if r.recommendation=='USABLE' else 'not-recommended' }}">
                {{ "%.0f"|format(r.overall_score or 0) }}
            </span>
        </td>
        <td>
            <a href="/primer/{{ r.primer_id }}" class="btn btn-sm btn-outline-primary">详情</a>
            <a href="/api/primer/{{ r.primer_id }}?format=fasta" class="btn btn-sm btn-outline-success">FASTA</a>
        </td>
    </tr>
    {% endfor %}
    </tbody>
</table>
</div>
{% elif query or type_filter %}
<div class="alert alert-warning">未找到匹配的引物</div>
{% endif %}
<script>
var methodGroups = {Primer3:'PCR',Simple_Thermo:'PCR',Primer3_qPCR:'qPCR',IUPAC_Degenerate:'DEGENERATE',varVAMP:'DEGENERATE',Olivar:'TILED',varVAMP_tiled:'TILED',PrimerForge:'TILED'};
(function(){
  var opts = document.getElementById('methodSelect').options;
  for (var i = 0; i < opts.length; i++) {
    if (opts[i].value) opts[i].setAttribute('data-type', methodGroups[opts[i].value] || '');
  }
  // 页面加载时根据当前 type 过滤, 但保留已有的 method 选中值
  filterMethods(false);
})();
function filterMethods(resetVal) {
  var t = document.getElementById('typeSelect').value;
  var sel = document.getElementById('methodSelect');
  if (resetVal !== false) sel.value = '';  // 用户切换类型时才重置
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
    {% if taxonomy.genus %}属: <strong>{{ taxonomy.genus }}</strong> |{% endif %}
    {% if taxonomy.family %}科: <strong>{{ taxonomy.family }}</strong> |{% endif %}
    优先级: <span class="badge bg-{{ 'danger' if taxonomy.priority=='HIGH' else 'warning' if taxonomy.priority=='MEDIUM' else 'secondary' }}">{{ taxonomy.priority }}</span>
</p>

<div class="row g-3 mb-4">
    <div class="col-md-3">
        <div class="card text-center"><div class="card-body">
            <h3 class="text-primary">{{ primers|length if primers else 0 }}</h3>
            <small class="text-muted">引物对</small>
        </div></div>
    </div>
    <div class="col-md-3">
        <div class="card text-center"><div class="card-body">
            <h3 class="text-success">{{ recommended_count }}</h3>
            <small class="text-muted">推荐引物</small>
        </div></div>
    </div>
    {% if est_genome_len > 0 %}
    <div class="col-md-3">
        <div class="card text-center"><div class="card-body">
            <h3 class="text-info">{{ est_genome_len }}</h3>
            <small class="text-muted">基因组长度 (bp)</small>
        </div></div>
    </div>
    {% endif %}
</div>

{% if est_genome_len > 0 %}
<div class="card mb-3"><div class="card-body">
    <h5>基因组引物覆盖图 ({{ est_genome_len }} bp)</h5>
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
        {# 类病毒环状拼接越界修正: 取模映射回真实基因组坐标 #}
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
        <i class="bi-download"></i> 导出 FASTA
    </a>
    <a href="/api/species/{{ species | urlencode }}?format=csv" class="btn btn-primary">
        <i class="bi-download"></i> 导出 CSV
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
  <h5><i class="bi-puzzle"></i> 平铺方案 ({{ tiled_by_method|length }} 组)</h5>
  {% for m, plist in tiled_by_method.items() %}
  <div style="border-left:3px solid #6741d9;padding-left:10px;margin-bottom:12px">
    <strong>{{ m }}</strong>: {{ plist|length }} 扩增子
    {% set bp = namespace(v=0) %}{% for p in plist %}{% set bp.v = bp.v + (p.product_size or 0) %}{% endfor %}
    | 覆盖 {{ bp.v }} bp
    {% if est_genome_len > 0 %}| {{ "%.0f"|format(bp.v / est_genome_len * 100) }}% 基因组{% endif %}
    | 平均 {{ "%.0f"|format(bp.v / plist|length) if plist else '-' }} bp
    {% set best = plist|selectattr('overall_score')|map(attribute='overall_score')|list %}
    {% if best %}| 评分 {{ "%.0f"|format(best|sum / best|length) }}{% endif %}
  </div>
  {% endfor %}
</div></div>
{% endif %}
<div class="table-responsive">
<table class="table table-hover"><thead class="table-dark"><tr>
  <th onclick="sortCol(0)"># ▼</th><th onclick="sortCol(1)">类型 ▼</th><th>正向引物</th><th>反向引物</th>
  <th>探针</th><th onclick="sortCol(5)">位置 ▼</th><th onclick="sortColNum(6)">bp ▼</th><th onclick="sortColNum(7)">GC% ▼</th><th onclick="sortColNum(8)">评分 ▼</th><th>详情</th>
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
    <td><a href="/primer/{{ p.primer_id }}" class="btn btn-sm btn-outline-primary">详情</a></td>
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
<div class="alert alert-warning">该物种暂无引物数据。请先运行引物设计流程。</div>
{% endif %}
{% endblock %}''')


PRIMER_DETAIL_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''{% block content %}
<h2 class="mt-4"><i class="bi-eye"></i> 引物详情</h2>

<div class="row">
    <div class="col-md-8">
        <div class="card mb-3">
            <div class="card-header fw-bold">基本信息</div>
            <div class="card-body">
                <table class="table table-sm">
                    <tr><td width="150"><strong>物种</strong></td><td><a href="/species/{{ p.species_name | urlencode }}">{{ p.species_name }}</a></td></tr>
                    <tr><td><strong>引物类型</strong></td><td><span class="badge bg-primary">{{ p.primer_type }}</span></td></tr>
                    <tr><td><strong>对号</strong></td><td>#{{ p.pair_id }}</td></tr>
                    <tr><td><strong>设计方法</strong></td><td>{{ p.design_method or 'N/A' }}</td></tr>
                    <tr><td><strong>基因组大小</strong></td><td>{{ genome_len }} bp</td></tr>
                    {% if (p.fwd_position or 0) > 0 and (p.rev_position or 0) > (p.fwd_position or 0) %}
                    <tr><td><strong>引物位置</strong></td><td>Fwd: {{ p.fwd_position }} &mdash; Rev: {{ p.rev_position }}</td></tr>
                    {% endif %}
                    <tr><td><strong>产物大小</strong></td><td>{{ p.product_size }} bp</td></tr>
                </table>
            </div>
        </div>

        {% if genome_len > 0 and ((p.fwd_position or 0) > 0 or (p.product_size or 0) > 0) %}
        <div class="card mb-3">
            <div class="card-header fw-bold">基因组位置</div>
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
                    <span><span style="color:#1971c2">&#9632;</span> 扩增子</span>
                    <span><span style="color:#e03131">&#9632;</span> Rev</span>
                </div>
            </div>
        </div>
        {% endif %}

        <div class="card mb-3">
            <div class="card-header fw-bold">引物序列</div>
            <div class="card-body">
                <h6>正向引物 (Forward, 5'→3')</h6>
                <div class="primer-seq p-3 mb-3">{{ p.fwd_sequence }} <button class="copy-btn btn btn-sm btn-outline-secondary float-end" onclick="copyToClipboard('{{ p.fwd_sequence }}')">复制</button></div>
                <div class="row">
                    <div class="col">长度: {{ p.fwd_sequence|length }}bp</div>
                    <div class="col">Tm: {{ "%.1f"|format(p.fwd_tm or 0) }}°C</div>
                    <div class="col">GC: {{ "%.1f"|format(p.gc_fwd or 0) }}%</div>
                </div>

                <hr>

                <h6>反向引物 (Reverse, 5'→3')</h6>
                <div class="primer-seq p-3 mb-3">{{ p.rev_sequence }} <button class="copy-btn btn btn-sm btn-outline-secondary float-end" onclick="copyToClipboard('{{ p.rev_sequence }}')">复制</button></div>
                <div class="row">
                    <div class="col">长度: {{ p.rev_sequence|length }}bp</div>
                    <div class="col">Tm: {{ "%.1f"|format(p.rev_tm or 0) }}°C</div>
                    <div class="col">GC: {{ "%.1f"|format(p.gc_rev or 0) }}%</div>
                </div>

                {% if p.probe_sequence %}
                <hr>
                <h6><i class="bi bi-pin"></i> TaqMan 探针</h6>
                <div class="probe-seq p-3 mb-2">{{ p.probe_sequence }}</div>
                <small>探针 Tm: {{ "%.1f"|format(p.probe_tm or 0) }}°C</small>
                {% endif %}
            </div>
        </div>

        {% if v %}
        <div class="card mb-3">
            <div class="card-header fw-bold">验证结果</div>
            <div class="card-body">
                <h4 class="{{ 'recommended' if v.recommendation in ('RECOMMENDED','PASS') else 'usable' if v.recommendation=='USABLE' else 'text-danger' }}">
                    {{ '%.0f'|format(v.overall_score or 0) }} 分 —
                    {% if v.recommendation in ('RECOMMENDED','PASS') %}✅ 推荐使用
                    {% elif v.recommendation == 'USABLE' %}⚠️ 可用
                    {% elif v.recommendation == 'CAUTION' %}⚠️ 谨慎使用
                    {% else %}❌ 不推荐{% endif %}
                </h4>

                <h6 class="mt-3">二聚体分析</h6>
                {% set dimer_html = _dimer_viz_html(p.fwd_sequence, 'Fwd Self-Dimer') %}
                {% if dimer_html %}<div class="mb-2">{{ dimer_html | safe }}</div>{% endif %}
                {% set dimer_html = _dimer_viz_html(p.rev_sequence, 'Rev Self-Dimer') %}
                {% if dimer_html %}<div class="mb-2">{{ dimer_html | safe }}</div>{% endif %}
                <table class="table table-sm">
                    <tr><td>自身二聚体 (Fwd)</td><td>{{ _dimer_bp(p.fwd_sequence) }}bp</td></tr>
                    <tr><td>自身二聚体 (Rev)</td><td>{{ _dimer_bp(p.rev_sequence) }}bp</td></tr>
                    <tr><td>交叉二聚体</td><td>{{ _cross_dimer_bp(p.fwd_sequence, p.rev_sequence) }}bp</td></tr>
                    <tr class="{{ 'table-danger' if v.cross_dimer_3prime >= 3 else '' }}"><td><strong>3' 交叉二聚体</strong></td><td><strong>{{ v.cross_dimer_3prime }}bp</strong></td></tr>
                </table>
                {% if v.dimer_warning %}<div class="alert alert-warning">{{ v.dimer_warning }}</div>{% endif %}

                {% if v.probe_hairpin_tm or v.probe_self_dimer_dg or v.probe_fwd_dimer_dg or v.probe_rev_dimer_dg or v.probe_warning %}
                <h6 class="mt-3"><i class="bi-pin"></i> 探针验证 (qPCR)</h6>
                <table class="table table-sm">
                    {% if v.probe_hairpin_tm %}<tr><td>探针发夹 Tm</td><td>{{ "%.1f"|format(v.probe_hairpin_tm) }}°C</td></tr>{% endif %}
                    {% if v.probe_self_dimer_dg %}<tr><td>探针自二聚体 ΔG</td><td>{{ "%.1f"|format(v.probe_self_dimer_dg) }} kcal/mol</td></tr>{% endif %}
                    {% if v.probe_fwd_dimer_dg %}<tr><td>探针-Fwd 交叉二聚体</td><td>{{ "%.1f"|format(v.probe_fwd_dimer_dg) }} kcal/mol</td></tr>{% endif %}
                    {% if v.probe_rev_dimer_dg %}<tr><td>探针-Rev 交叉二聚体</td><td>{{ "%.1f"|format(v.probe_rev_dimer_dg) }} kcal/mol</td></tr>{% endif %}
                    <tr class="{{ 'table-danger' if not v.probe_tm_diff_ok else '' }}"><td>探针-引物 Tm 差</td><td>{{ '✅ 合格' if v.probe_tm_diff_ok else '❌ 不合格 (需 5-10°C)' }}</td></tr>
                </table>
                {% if v.probe_warning %}<div class="alert alert-warning small">{{ v.probe_warning }}</div>{% endif %}
                {% endif %}

                {% if (v.coverage_avg or 0) > 0 %}
                <h6 class="mt-3"><i class="bi-graph-up"></i> 覆盖度分析</h6>
                <table class="table table-sm">
                    <tr><td>Fwd 覆盖度</td><td><span class="{{ 'text-success' if (v.fwd_coverage_pct or 0) >= 90 else 'text-warning' if (v.fwd_coverage_pct or 0) >= 70 else 'text-danger' }}">{{ "%.1f"|format(v.fwd_coverage_pct or 0) }}%</span> ({{ v.coverage_total_seqs }} 条序列)</td></tr>
                    <tr><td>Rev 覆盖度</td><td><span class="{{ 'text-success' if (v.rev_coverage_pct or 0) >= 90 else 'text-warning' if (v.rev_coverage_pct or 0) >= 70 else 'text-danger' }}">{{ "%.1f"|format(v.rev_coverage_pct or 0) }}%</span></td></tr>
                    <tr><td>平均覆盖度</td><td><strong>{{ "%.1f"|format(v.coverage_avg or 0) }}%</strong></td></tr>
                    <tr><td>Fwd 3'端惩罚</td><td>{{ "%.1f"|format(v.fwd_3prime_penalty or 0) }}</td></tr>
                    <tr><td>Rev 3'端惩罚</td><td>{{ "%.1f"|format(v.rev_3prime_penalty or 0) }}</td></tr>
                </table>
                {% endif %}
            </div>
        </div>
        {% endif %}
    </div>

    <div class="col-md-4">
        <div class="card mb-3">
            <div class="card-header fw-bold">下载</div>
            <div class="card-body">
                <a href="/api/primer/{{ p.primer_id }}?format=fasta" class="btn btn-success w-100 mb-2">下载 FASTA</a>
                <a href="/api/primer/{{ p.primer_id }}?format=json" class="btn btn-info w-100">下载 JSON</a>
            </div>
        </div>
        {% if v and ((v.blast_specificity_score or 0) > 0 or (v.blast_rev_target_hits or 0) > 0) %}
        <div class="card mb-3">
            <div class="card-header fw-bold">BLAST 特异性</div>
            <div class="card-body">
                <p>特异性评分: <strong>{{ '%.1f'|format(v.blast_specificity_score or 0) }}%</strong></p>
                <table class="table table-sm mb-2">
                    <tr><td></td><td><small>FWD</small></td><td><small>REV</small></td></tr>
                    <tr><td>靶标命中</td><td>{{ v.blast_fwd_target_hits|default(0) }}</td><td>{{ v.blast_rev_target_hits|default(0) }}</td></tr>
                    <tr><td>植物命中</td><td>{{ v.blast_fwd_plant_hits|default(0) }}</td><td>{{ v.blast_rev_plant_hits|default(0) }}</td></tr>
                    <tr><td>其他命中</td><td>{{ v.blast_fwd_other_hits|default(0) }}</td><td>{{ v.blast_rev_other_hits|default(0) }}</td></tr>
                </table>
                {% if v.blast_offtarget_top %}<p class="text-warning small">脱靶物种: {{ v.blast_offtarget_top[:120] }}</p>{% endif %}
            </div>
        </div>
        {% endif %}

        {% if epcr %}
        <div class="card mb-3">
            <div class="card-header fw-bold"><i class="bi-diagram-3"></i> 电子PCR扩增子</div>
            <div class="card-body" style="max-height:400px;overflow-y:auto">
                <p class="small text-muted">方向相向 + 距离 ≤ {{ 5000 }}bp 的配对命中</p>
                {% for a in epcr %}
                <div style="border-left:3px solid {{ '#198754' if a.is_target else '#dc3545' if a.is_plant else '#6c757d' }};padding:4px 8px;margin:4px 0;font-size:12px">
                    <div style="display:flex;justify-content:space-between">
                        <span style="font-weight:600;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{{ a.seq_id }}">{{ a.seq_id }}</span>
                        <span style="font-weight:700;min-width:50px;text-align:right">{{ a.amp_len }}bp</span>
                    </div>
                    <div class="text-muted" style="font-size:10px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ a.desc }}</div>
                    <span class="badge bg-{{ 'success' if a.is_target else 'danger' if a.is_plant else 'secondary' }}" style="font-size:9px">{{ '靶标' if a.is_target else '植物' if a.is_plant else '其他' }}</span>
                </div>
                {% endfor %}
                {% if epcr|length >= 50 %}<p class="small text-muted mt-1">仅显示前50条</p>{% endif %}
            </div>
        </div>
        {% endif %}
        <div class="card">
            <div class="card-header fw-bold">相关引物</div>
            <div class="card-body">
                <p class="text-muted">同一物种的其他引物对</p>
                <a href="/species/{{ p.species_name | urlencode }}" class="btn btn-outline-primary btn-sm">查看全部 →</a>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')


BROWSE_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''{% block content %}
<h2 class="mt-4"><i class="bi-list"></i> 浏览物种</h2>

<div class="row mb-3">
    <div class="col-md-4">
        <input type="text" class="form-control" id="filterInput" placeholder="过滤物种名...">
    </div>
</div>

<div class="table-responsive">
<table class="table table-hover" id="speciesTable">
    <thead class="table-dark">
        <tr>
            <th>物种</th><th>属</th><th>科</th><th>优先级</th><th>引物数</th><th>平均分</th>
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

DESIGN_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', r'''{% block content %}
<h2 class="mt-4"><i class="bi-pencil-square"></i> 引物设计</h2>
<p class="text-muted">上传FASTA序列或选择已知病毒物种，在线设计PCR/qPCR/简并/平铺引物。</p>

<ul class="nav nav-tabs mb-3" id="designTabs">
    <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#tab-upload">上传FASTA</button></li>
    <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-species">已知病毒物种</button></li>
    <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-jobs">设计任务 ({{ jobs|length }})</button></li>
</ul>

<div class="tab-content">
    <!-- Tab 1: Upload FASTA -->
        <!-- Tab 1: Upload FASTA -->
    <div class="tab-pane fade show active" id="tab-upload">
        <div class="card"><div class="card-body">
            <h5><i class="bi-cloud-upload"></i> 上传/粘贴序列</h5>
            <!-- Input mode switch -->
            <div class="btn-group btn-group-sm mb-3" role="group">
                <input type="radio" class="btn-check" name="inputMode" id="mode-file" value="file" checked>
                <label class="btn btn-outline-secondary" for="mode-file"><i class="bi-file-earmark"></i> 上传文件</label>
                <input type="radio" class="btn-check" name="inputMode" id="mode-paste" value="paste">
                <label class="btn btn-outline-secondary" for="mode-paste"><i class="bi-clipboard"></i> 粘贴序列</label>
            </div>

            <!-- File upload area -->
            <div id="fileUploadArea">
                <div class="row g-3">
                    <div class="col-md-8">
                        <label class="form-label">FASTA文件 (.fa/.fasta/.fna)</label>
                        <input type="file" name="fasta" id="fastaFile" class="form-control" accept=".fa,.fasta,.fna">
                    </div>
                    <div class="col-md-4 d-flex align-items-end">
                        <button type="button" class="btn btn-outline-info btn-sm" onclick="loadExample()" title="加载示例FASTA序列">
                            <i class="bi-lightbulb"></i> 加载示例
                        </button>
                    </div>
                </div>
            </div>

            <!-- Paste area -->
            <div id="pasteArea" style="display:none">
                <label class="form-label">粘贴FASTA序列 <small class="text-muted">(或纯序列，自动包装为FASTA)</small></label>
                <textarea id="pasteSeq" class="form-control font-monospace" rows="8"
                    style="font-size:13px; resize:vertical"
                    placeholder=">seq1&#10;ATGCGTACGTAGCTAGCTAGCATCGATCGTAGCTAGCTAGCTAGCTAGC&#10;>seq2&#10;ATGCGTACGTAGCTAGCATCGATCGTAGCTAGCTAGCTAGCTAGCTGA&#10;&#10;支持FASTA格式，也支持直接粘贴纯序列（会自动包装）"></textarea>
                <div class="mt-2">
                    <small id="pasteCharCount" class="text-muted">0 碱基</small>
                    <button type="button" class="btn btn-outline-info btn-sm float-end" onclick="loadExample()">
                        <i class="bi-lightbulb"></i> 加载示例
                    </button>
                </div>
            </div>

            <form id="uploadForm" enctype="multipart/form-data">
                <div class="row g-3 mt-2">
                    <div class="col-md-6">
                        <label class="form-label">物种名称 (可选)</label>
                        <input type="text" name="species_name" id="speciesName" class="form-control" placeholder="如 Tobacco mosaic virus">
                    </div>
                    <div class="col-md-3">
                        <label class="form-label">设计模式</label>
                        <select name="mode" class="form-select">
                            <option value="PCR">PCR 常规检测</option>
                            <option value="qPCR">qPCR 荧光定量 (+探针)</option>
                            <option value="DEGENERATE">简并引物 (varVAMP)</option>
                            <option value="TILED">全基因组平铺 (Olivar)</option>
                        </select>
                    </div>
                    <div class="col-md-1">
                        <label class="form-label">对数</label>
                        <input type="number" name="num_pairs" class="form-control" value="5" min="1" max="20">
                    </div>
                    <div class="col-md-1">
                        <label class="form-label">最小bp</label>
                        <input type="number" name="prod_min" class="form-control" value="250" min="60" max="2000">
                    </div>
                    <div class="col-md-1">
                        <label class="form-label">最大bp</label>
                        <input type="number" name="prod_max" class="form-control" value="1000" min="80" max="5000">
                    </div>
                    <div class="col-md-3 d-flex align-items-end">
                        <button type="submit" class="btn btn-primary w-100" id="uploadBtn">
                            <i class="bi-rocket-takeoff"></i> 开始设计
                        </button>
                    </div>
                </div>
                <!-- Hidden fields for paste mode -->
                <input type="hidden" name="paste_seq" id="hiddenPasteSeq" value="">
            </form>
            <div id="uploadStatus" class="mt-3" style="display:none"></div>
        </div></div>
    </div>

<!-- Tab 2: Known Species -->
    <div class="tab-pane fade" id="tab-species">
        <div class="card"><div class="card-body">
            <h5><i class="bi-virus"></i> 选择已知病毒物种</h5>
            <div class="row g-3 mb-3">
                <div class="col-md-8">
                    <input type="text" id="speciesSearch" class="form-control" placeholder="输入病毒名称搜索...">
                </div>
                <div class="col-md-4">
                    <button class="btn btn-outline-primary w-100" onclick="searchSpecies()">
                        <i class="bi-search"></i> 搜索
                    </button>
                </div>
            </div>
            <div id="speciesList" class="list-group" style="max-height: 400px; overflow-y: auto">
                <div class="text-muted p-3">输入关键词搜索可用物种...</div>
            </div>
            <div id="speciesDesignForm" class="mt-3" style="display:none">
                <hr>
                <h6 id="selectedSpeciesName"></h6>
                <div class="row g-3">
                    <div class="col-md-3">
                        <label class="form-label">设计模式</label>
                        <select id="spMode" class="form-select">
                            <option value="PCR">PCR</option>
                            <option value="qPCR">qPCR</option>
                            <option value="DEGENERATE">Degenerate</option>
                            <option value="TILED">Tiled</option>
                        </select>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label">引物对数</label>
                        <input type="number" id="spNum" class="form-control" value="5" min="1" max="20">
                    </div>
                    <div class="col-md-3 d-flex align-items-end">
                        <button class="btn btn-success w-100" onclick="designForSpecies()">
                            <i class="bi-rocket-takeoff"></i> 设计引物
                        </button>
                    </div>
                </div>
                <div id="speciesStatus" class="mt-2"></div>
            </div>
        </div></div>
    </div>

    <!-- Tab 3: Job History -->
    <div class="tab-pane fade" id="tab-jobs">
        <div class="card"><div class="card-body">
            <h5><i class="bi-list-check"></i> 设计任务列表</h5>
            <div id="jobsList">
                {% if jobs %}
                <table class="table table-sm">
                    <thead><tr><th>任务ID</th><th>物种</th><th>模式</th><th>状态</th><th>引物数</th><th>时间</th><th>操作</th></tr></thead>
                    <tbody>
                    {% for j in jobs %}
                    <tr>
                        <td><code>{{ j.job_id[:8] }}</code></td>
                        <td>{{ j.species_name[:30] }}</td>
                        <td><span class="badge bg-secondary">{{ j.design_mode }}</span></td>
                        <td><span class="badge bg-{{ 'success' if j.status=='completed' else 'warning' if j.status=='running' else 'danger' if j.status=='failed' else 'info' }}">{{ j.status }}</span></td>
                        <td>{{ j.primer_count }}</td>
                        <td><small>{{ j.created_at[:16] }}</small></td>
                        <td>
                            {% if j.status == 'completed' %}
                            <button class="btn btn-sm btn-outline-primary" onclick="pollJob('{{ j.job_id }}')">查看结果</button>
                            {% elif j.status == 'running' %}
                            <button class="btn btn-sm btn-outline-warning" onclick="pollJob('{{ j.job_id }}')">刷新</button>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p class="text-muted">暂无设计任务。上传FASTA或选择物种开始设计。</p>
                {% endif %}
            </div>
        </div></div>
    </div>
</div>

<script>
// ── Inline results table builder ──
var _lastJobId = null;
function buildResultsTable(results, speciesName, designMode) {
    if (!results || results.length === 0) {
        return '<div class="alert alert-warning">未设计出引物，请尝试调整参数或使用其他序列。</div>';
    }

    // ── 构建基因组结合位置可视化 SVG ──
    var genomeViz = '';
    var hasPositions = false;
    for (var i = 0; i < results.length; i++) {
        var fs = parseInt(results[i].Fwd_Start) || 0;
        var rs = parseInt(results[i].Rev_Start) || 0;
        if (fs > 0 && rs > 0) { hasPositions = true; break; }
    }
    if (hasPositions) {
        // 估算基因组长度
        var maxPos = 0;
        for (var i = 0; i < results.length; i++) {
            var rs2 = parseInt(results[i].Rev_Start) || 0;
            if (rs2 > maxPos) maxPos = rs2;
        }
        var genomeLen = Math.max(maxPos + 200, 500);
        // 颜色方案
        var colors = ['#e03131','#1971c2','#2b8a3e','#e8590c','#862e9c',
                      '#c92a2a','#1864ab','#2f9e44','#d9480f','#9c36b5'];
        var svgW = 780, svgH = 22 * results.length + 40, padL = 55, padR = 60, barW = svgW - padL - padR;
        genomeViz = '<div class="mt-2 mb-3 p-2 bg-light rounded"><strong><i class="bi-diagram-3"></i> 引物结合位置 (基因组 ~' + genomeLen.toLocaleString() + ' bp)</strong>';
        genomeViz += '<svg width="100%" viewBox="0 0 ' + svgW + ' ' + svgH + '" style="max-width:820px; font-family:Consolas,monospace; font-size:11px;">';
        // 基因组主干
        genomeViz += '<rect x="' + padL + '" y="' + (svgH - 16) + '" width="' + barW + '" height="6" rx="3" fill="#dee2e6" stroke="#adb5bd" stroke-width="1"/>';
        // 刻度标记
        for (var t = 0; t <= 1; t += 0.25) {
            var tx = padL + t * barW;
            genomeViz += '<line x1="' + tx + '" y1="' + (svgH - 20) + '" x2="' + tx + '" y2="' + (svgH - 10) + '" stroke="#868e96" stroke-width="1"/>';
            genomeViz += '<text x="' + tx + '" y="' + (svgH - 2) + '" text-anchor="middle" fill="#495057">' + Math.round(t * genomeLen) + '</text>';
        }
        // 每对引物
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
            // 产物连接线
            var ampLeft = fLeft + fW;
            var ampW = rLeft - (fLeft + fW);
            if (ampW > 0) {
                genomeViz += '<rect x="' + ampLeft + '" y="' + (y + 5) + '" width="' + ampW + '" height="3" fill="' + col + '" opacity="0.3" rx="1"/>';
            }
            // Fwd 块
            genomeViz += '<rect x="' + fLeft + '" y="' + y + '" width="' + fW + '" height="8" fill="' + col + '" opacity="0.85" rx="2"/>';
            genomeViz += '<text x="' + Math.max(fLeft - 2, padL - 50) + '" y="' + (y + 7) + '" text-anchor="end" fill="' + col + '" font-weight="bold">F' + (i+1) + '</text>';
            // Rev 块  
            genomeViz += '<rect x="' + rLeft + '" y="' + y + '" width="' + rW + '" height="8" fill="' + col + '" opacity="0.55" rx="2"/>';
            // 坐标标注
            genomeViz += '<text x="' + (rLeft + rW + 3) + '" y="' + (y + 7) + '" fill="' + col + '" font-size="9">' + fs2 + '..' + (rs2 + rLen) + '</text>';
        }
        genomeViz += '</svg></div>';
    }

    // ── 模拟凝胶电泳 SVG ──
    var gelViz = '';
    var products = [];
    for (var i = 0; i < results.length; i++) {
        var pv = parseInt(results[i].Product) || 0;
        if (pv > 0) products.push({idx: i, size: pv});
    }
    if (products.length > 0) {
        // Sort by product size ascending (smaller = runs further = higher band)
        products.sort(function(a, b) { return a.size - b.size; });
        var gelW = 440, gelH = 22 * products.length + 80, laneX = 180, laneW = 200, padT = 35, padB = 25;
        // DNA ladder reference sizes
        var ladder = [100, 200, 300, 400, 500, 700, 1000, 1500];
        var maxSize = Math.max.apply(null, ladder.concat(products.map(function(p) { return p.size; })));
        var scale = function(sz) { return padT + (1 - Math.log(sz) / Math.log(maxSize + 1)) * (gelH - padT - padB); };

        var gelColors = ['#e03131','#1971c2','#2b8a3e','#e8590c','#862e9c',
                         '#c92a2a','#1864ab','#2f9e44','#d9480f','#9c36b5'];
        gelViz = '<div class="mt-3 mb-3 p-2 bg-dark rounded text-white"><strong><i class="bi-droplet"></i> \u6a21\u62df\u51dd\u80f6\u7535\u6cf3</strong>';
        gelViz += ' <small class="text-white-50">(\u4ea7\u7269\u6761\u5e26)</small>';
        gelViz += '<svg width="100%" viewBox="0 0 ' + gelW + ' ' + gelH + '" style="max-width:480px; font-family:Consolas,monospace; font-size:10px;">';

        // Gel background
        gelViz += '<rect x="' + laneX + '" y="' + padT + '" width="' + laneW + '" height="' + (gelH - padT - padB) + '" fill="#1a1a2e" rx="4"/>';
        gelViz += '<rect x="' + laneX + '" y="' + padT + '" width="' + laneW + '" height="' + (gelH - padT - padB) + '" fill="url(#gelGrad)" rx="4" opacity="0.6"/>';

        // Gradient definition
        gelViz += '<defs><linearGradient id="gelGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#667eea" stop-opacity="0.15"/><stop offset="100%" stop-color="#764ba2" stop-opacity="0.05"/></linearGradient></defs>';

        // Well marks at top
        gelViz += '<rect x="' + (laneX + laneW/2 - 20) + '" y="' + (padT - 10) + '" width="40" height="10" fill="#333" rx="2" stroke="#555" stroke-width="1"/>';
        gelViz += '<text x="' + (laneX + laneW/2) + '" y="' + (padT - 14) + '" text-anchor="middle" fill="#aaa" font-size="9">\u70b9\u6837\u5b54</text>';

        // Ladder bands (lighter)
        for (var li = 0; li < ladder.length; li++) {
            var ly = scale(ladder[li]);
            gelViz += '<line x1="' + (laneX - 30) + '" y1="' + ly + '" x2="' + (laneX + laneW + 30) + '" y2="' + ly + '" stroke="#555" stroke-width="0.5" stroke-dasharray="3,3"/>';
            gelViz += '<text x="' + (laneX - 34) + '" y="' + (ly + 3) + '" text-anchor="end" fill="#888" font-size="9">' + ladder[li] + 'bp</text>';
        }

        // Sample bands
        for (var pi = 0; pi < products.length; pi++) {
            var p = products[pi];
            var by = scale(p.size);
            var col = gelColors[p.idx % gelColors.length];
            // Glow
            gelViz += '<rect x="' + (laneX + 30) + '" y="' + (by - 3) + '" width="' + (laneW - 60) + '" height="6" fill="' + col + '" opacity="0.3" rx="3"/>';
            // Band
            gelViz += '<rect x="' + (laneX + 30) + '" y="' + (by - 2) + '" width="' + (laneW - 60) + '" height="4" fill="' + col + '" opacity="0.9" rx="2"/>';
            // Label
            gelViz += '<text x="' + (laneX + laneW + 6) + '" y="' + (by + 3) + '" fill="' + col + '" font-size="10" font-weight="bold">P' + (p.idx + 1) + ' ' + p.size + 'bp</text>';
        }

        gelViz += '</svg></div>';
    }

    var h = '<div class="card mt-3"><div class="card-header"><strong><i class="bi-clipboard-check"></i> 设计结果</strong>';
    h += ' <span class="badge bg-primary">' + (designMode || '') + '</span>';
    h += ' <small class="text-muted ms-2">' + (speciesName || '') + '</small>';
    h += ' <span class="float-end">';
    h += '<button class="btn btn-sm btn-outline-info me-1" onclick="downloadResults(\'json\')">JSON</button>';
    h += '<button class="btn btn-sm btn-outline-success me-1" onclick="downloadResults(\'tsv\')">TSV</button>';
    h += '<button class="btn btn-sm btn-outline-primary" onclick="downloadResults(\'fasta\')">FASTA</button>';
    h += '</span></div><div class="card-body">';
    h += genomeViz;
    h += '<div class="table-responsive"><table class="table table-hover table-sm">';
    h += '<thead class="table-dark"><tr><th>#</th><th>正向引物 (5\'→3\')</th><th>Tm</th><th>GC%</th><th>反向引物 (5\'→3\')</th><th>Tm</th><th>GC%</th><th>产物</th><th>方法</th><th>评分</th></tr></thead><tbody>';
    for (var i = 0; i < results.length; i++) {
        var r = results[i];
        var fwd = r.Fwd_Seq || '';
        var rev = r.Rev_Seq || '';
        // Robust number formatting
        var prodVal = parseInt(r.Product) || 0;
        var prod = prodVal > 0 ? (prodVal + ' bp') : '—';
        var tmF = isFinite(parseFloat(r.Fwd_Tm)) ? parseFloat(r.Fwd_Tm).toFixed(1) : '—';
        var tmR = isFinite(parseFloat(r.Rev_Tm)) ? parseFloat(r.Rev_Tm).toFixed(1) : '—';
        var gcF = isFinite(parseFloat(r.GC_Fwd)) ? parseFloat(r.GC_Fwd).toFixed(1) + '%' : '—';
        var gcR = isFinite(parseFloat(r.GC_Rev)) ? parseFloat(r.GC_Rev).toFixed(1) + '%' : '—';
        var method = r.Method || '—';
        var penalty = r.Penalty != null ? r.Penalty : '—';
        var probe = r.Probe_Seq || '';
        h += '<tr><td>' + (i + 1) + '</td>';
        h += '<td><span class="primer-seq">' + fwd + '</span></td>';
        h += '<td>' + tmF + '</td><td>' + gcF + '</td>';
        h += '<td><span class="primer-seq">' + rev + '</span></td>';
        h += '<td>' + tmR + '</td><td>' + gcR + '</td>';
        h += '<td>' + prod + '</td><td>' + method + '</td>';
        h += '<td>' + penalty + '</td></tr>';
        if (probe) {
            h += '<tr><td></td><td colspan="9"><span class="probe-seq">探针: ' + probe + '</span></td></tr>';
        }
    }
    h += '</tbody></table></div></div></div>';
    return h;
}
function downloadResults(fmt) {
    if (_lastJobId) window.open('/api/design/results/' + _lastJobId + '?format=' + fmt, '_blank');
}

// ── Paste mode & example ──
var SAMPLE_FASTA = ">TMV_example|Tobacco_mosaic_virus_complete_genome\nGTATTTTTACAACAATTACCAACAACAACAAACAACAAACAACATTACAATTACTA\nTTTACAATTACAATGGCTTACACTAGATCAGCAATCGAGTTTCAAAATCAACAAGAA\nTCGACTACCTCTGCATCCGCCGGTTACGTGTCCAACGTTAGACAAGCCAACACGGCT\nATCCAGCAGACTATAGCTAATCTACTCAACACTATCCGTGCTAACAACGCTAGCCAG\nTCAGAGTCAGCCTCTTTGTCAAGCGCTGACTACGAGACACTTCCTAACCCAAACCCA\nAAGCCCCCAACAATGAAGAGGCTCCTAACACTATCCTTTGAATCTGTACGCTCATGG\nTATGATGTAGATAATCCTACTAATCCTTTGTCAACTGACGATCCCGAGTTACTGTCT\nAAGGCGGTTGCTGATATGTGTGCTTCTGGTGACGCAATATCTGAATCAGATGAGTTC\nATAGATGCAGTTCTCATTGCTGCGGCATTCCCTTCGTACTTCGTAAAATTCTCACTT\nCGTTTTAGAAGTCTCATATCTAAATTGATATCTCCTGCGAGGTTTGGACCTAAGGTT\nATTAGAGAGTTTGAGAATTCAGTCGTTT\n>TMV_CP|capsid_protein_gene\nATGTCTTACAGTATCACTACTCCATCTCAGTTCGTGTTCTTGTCATCAGCGTGGGCC\nGACCCAATAGAGTTAATTAATTTATGTACTAATGCCTTAGGAAATCAGTTTCAAACA\nCAACAAGCTCGAACTGTCGTTCAAAGACAATTCAGTGAGTGGAAACCTTCACCAGGT\nTCGACGGTGCGTTTTCCTGACAGTGACTTCAAGGTCTTATCTGATTCGACCGCCGCT\nTCGTATATACACACCAATACCATAGTCGAGATACAGTCCGCATCAGGAATCTACAAC\nCAGAATGCTATTTTGGACGTGTTCAATACTGGAAGTCA";

function loadExample() {{
    if (document.getElementById('mode-paste').checked) {{
        document.getElementById('pasteSeq').value = SAMPLE_FASTA;
        var cnt = SAMPLE_FASTA.replace(/[^ATGCatgc]/g, '').length;
        document.getElementById('pasteCharCount').textContent = cnt + ' \u78b1\u57fa, ' + (SAMPLE_FASTA.split('\n').filter(function(l){{return l.startsWith('>');}}).length) + ' \u6761\u5e8f\u5217';
    }} else {{
        document.getElementById('speciesName').value = 'Tobacco mosaic virus (TMV example)';
        document.getElementById('hiddenPasteSeq').value = SAMPLE_FASTA;
    }}
}}

// Mode switch
document.getElementById('mode-file').addEventListener('change', function() {{
    document.getElementById('fileUploadArea').style.display = 'block';
    document.getElementById('pasteArea').style.display = 'none';
    document.getElementById('fastaFile').required = true;
    document.getElementById('hiddenPasteSeq').value = '';
}});
document.getElementById('mode-paste').addEventListener('change', function() {{
    document.getElementById('fileUploadArea').style.display = 'none';
    document.getElementById('pasteArea').style.display = 'block';
    document.getElementById('fastaFile').required = false;
}});

// Paste char counter
document.getElementById('pasteSeq').addEventListener('input', function() {{
    var raw = this.value;
    var cnt = raw.replace(/[^ATGCatgc]/g, '').length;
    var seqs = raw.split('\n').filter(function(l){{return l.startsWith('>');}}).length || (raw.trim() ? 1 : 0);
    document.getElementById('pasteCharCount').textContent = cnt + ' \u78b1\u57fa, ' + seqs + ' \u6761\u5e8f\u5217';
}});

// ── Upload handler ──
document.getElementById("uploadForm").addEventListener("submit", async function(e) {{
    e.preventDefault();
    var btn = document.getElementById("uploadBtn");
    var status = document.getElementById("uploadStatus");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> \u63d0\u4ea4\u4e2d...';
    status.style.display = "block";

    // Check if paste mode
    var pasteSeq = document.getElementById('pasteSeq').value.trim();
    if (pasteSeq && document.getElementById('mode-paste').checked) {{
        if (!pasteSeq.startsWith('>')) {{
            pasteSeq = '>seq1\n' + pasteSeq.replace(/\s+/g, '\n').replace(/(.{{60}})/g, '$1\n');
        }}
        var blob = new Blob([pasteSeq], {{type: 'text/plain'}});
        var form = new FormData();
        form.append('fasta', blob, 'pasted.fasta');
        form.append('species_name', document.getElementById('speciesName').value);
        form.append('mode', document.querySelector('[name="mode"]').value);
        form.append('num_pairs', document.querySelector('[name="num_pairs"]').value);
        form.append('prod_min', document.querySelector('[name="prod_min"]').value);
        form.append('prod_max', document.querySelector('[name="prod_max"]').value);
        submitDesign(form, btn, status);
        return;
    }}

    var form = new FormData(this);
    submitDesign(form, btn, status);
}});
async function submitDesign(form, btn, status) {{
    status.innerHTML = '<div class="alert alert-info">\u6b63\u5728\u63d0\u4ea4\u8bbe\u8ba1\u4efb\u52a1...</div>';
    try {{
        var resp = await fetch("/api/design/upload", {{method: "POST", body: form}});
        var data = await resp.json();
        if (data.error) {{
            status.innerHTML = '<div class="alert alert-danger">' + data.error + '</div>';
        }} else {{
            status.innerHTML = '<div class="alert alert-info"><div class="spinner-border spinner-border-sm"></div> \u4efb\u52a1 <code>' + data.job_id + '</code> \u5df2\u63d0\u4ea4\uff0c\u6b63\u5728\u8bbe\u8ba1\u4e2d...</div>';
            startPolling(data.job_id, status, form.get('species_name') || 'custom_input', form.get('mode') || 'PCR');
        }}
    }} catch(err) {{
        status.innerHTML = '<div class="alert alert-danger">\u7f51\u7edc\u9519\u8bef: ' + err.message + '</div>';
    }}
    btn.disabled = false;
    btn.innerHTML = '<i class="bi-rocket-takeoff"></i> \u5f00\u59cb\u8bbe\u8ba1';
}}
function startPolling(jobId, el, speciesName, designMode) {
    var iv = setInterval(async function() {
        try {
            var r = await fetch("/api/design/status/" + jobId);
            var d = await r.json();
            if (d.status === "completed") {
                clearInterval(iv);
                _lastJobId = jobId;
                try {
                    var rr = await fetch("/api/design/results/" + jobId + "?format=json");
                    var results = await rr.json();
                    if (results.error) {
                        el.innerHTML = '<div class="alert alert-danger">' + results.error + '</div>';
                    } else {
                        el.innerHTML = '<div class="alert alert-success"><i class="bi-check-circle"></i> 设计完成! <strong>' + (results.length || 0) + '</strong> 对引物</div>'
                            + buildResultsTable(results, speciesName || d.species_name, designMode || d.design_mode);
                    }
                } catch(e2) {
                    el.innerHTML = '<div class="alert alert-warning">设计完成但获取结果失败: ' + e2.message + '</div>';
                }
            } else if (d.status === "failed") {
                clearInterval(iv);
                el.innerHTML = '<div class="alert alert-danger"><i class="bi-exclamation-triangle"></i> 设计失败: ' + (d.error || "未知错误") + '</div>';
            } else {
                el.innerHTML = '<div class="alert alert-info"><div class="spinner-border spinner-border-sm"></div> ' + (d.progress_msg || "设计中...") + ' (' + (d.progress_pct || 0) + '%)</div>';
            }
        } catch(e) { clearInterval(iv); }
    }, 3000);
}

// Species search
async function searchSpecies() {
    var q = document.getElementById("speciesSearch").value;
    var list = document.getElementById("speciesList");
    list.innerHTML = '<div class="text-muted p-3">搜索中...</div>';
    try {
        var r = await fetch("/api/design/species-list?q=" + encodeURIComponent(q));
        var data = await r.json();
        if (data.species.length === 0) {
            list.innerHTML = '<div class="text-muted p-3">未找到匹配物种。请尝试其他关键词。</div>';
        } else {
            list.innerHTML = data.species.map(function(s) {
                return '<a href="#" class="list-group-item list-group-item-action" onclick="selectSpecies(\'' + s.species_name + '\', ' + s.n_sequences + '); return false">' +
                    '<strong>' + s.species_name + '</strong> <span class="badge bg-info float-end">' + s.n_sequences + ' 条序列</span>' +
                    '<br><small class="text-muted">' + s.file_size_kb + ' KB</small></a>';
            }).join("");
        }
    } catch(e) {
        list.innerHTML = '<div class="text-danger p-3">搜索失败: ' + e.message + '</div>';
    }
}

var selectedSpecies = "";
function selectSpecies(name, nseq) {
    selectedSpecies = name;
    document.getElementById("selectedSpeciesName").innerHTML = '<i class="bi-virus"></i> ' + name + ' <span class="badge bg-info">' + nseq + ' 条序列</span>';
    document.getElementById("speciesDesignForm").style.display = "block";
    // Highlight
    document.querySelectorAll("#speciesList .list-group-item").forEach(function(el) {
        el.classList.remove("active");
        if (el.textContent.includes(name)) el.classList.add("active");
    });
}

async function designForSpecies() {
    var status = document.getElementById("speciesStatus");
    status.innerHTML = '<div class="alert alert-info">提交任务...</div>';
    try {
        var r = await fetch("/api/design/species/" + encodeURIComponent(selectedSpecies), {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                mode: document.getElementById("spMode").value,
                num_pairs: parseInt(document.getElementById("spNum").value)
            })
        });
        var data = await r.json();
        if (data.error) {
            status.innerHTML = '<div class="alert alert-danger">' + data.error + '</div>';
        } else {
            status.innerHTML = '<div class="alert alert-info"><div class="spinner-border spinner-border-sm"></div> 任务 <code>' + data.job_id + '</code> 已提交，正在设计中...</div>';
            startPolling(data.job_id, status, selectedSpecies, document.getElementById("spMode").value);
        }
    } catch(e) {
        status.innerHTML = '<div class="alert alert-danger">错误: ' + e.message + '</div>';
    }
}

function pollJob(jobId) {
    // Jump to upload tab and show inline results for this job
    var tab = document.querySelector('[data-bs-target="#tab-upload"]');
    if (tab) { var bt = new bootstrap.Tab(tab); bt.show(); }
    var status = document.getElementById("uploadStatus");
    status.style.display = "block";
    status.innerHTML = '<div class="alert alert-info"><div class="spinner-border spinner-border-sm"></div> 加载任务 <code>' + jobId + '</code>...</div>';
    startPolling(jobId, status, '', '');
}

// Enter key search
document.getElementById("speciesSearch").addEventListener("keydown", function(e) {
    if (e.key === "Enter") { e.preventDefault(); searchSpecies(); }
});

// Auto-fill species from species detail page
(function() {
    var sp = sessionStorage.getItem('designSpecies');
    if (sp) {
        var el = document.getElementById('speciesSearch');
        if (el) { el.value = sp; }
        // Switch to species tab
        setTimeout(function() {
            var tab = document.querySelector('[data-bs-target="#tab-species"]');
            if (tab) { var bt = new bootstrap.Tab(tab); bt.show(); }
            searchSpecies();
        }, 300);
        sessionStorage.removeItem('designSpecies');
    }
})();
// Auto-load job from URL param (redirected from results page)
(function() {
    var params = new URLSearchParams(window.location.search);
    var jid = params.get('job_id');
    if (jid) {
        var tab = document.querySelector('[data-bs-target="#tab-upload"]');
        if (tab) { var bt = new bootstrap.Tab(tab); bt.show(); }
        var status = document.getElementById("uploadStatus");
        status.style.display = "block";
        status.innerHTML = '<div class="alert alert-info"><div class="spinner-border spinner-border-sm"></div> 加载任务 <code>' + jid + '</code>...</div>';
        startPolling(jid, status, '', '');
    }
})();
</script>
{% endblock %}''')



# ======================================================================
# Flask 应用
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
        """计算交叉二聚体最长匹配bp数"""
        from Bio.Seq import Seq
        rc_rev = str(Seq(rev).reverse_complement())
        best = 0
        for i in range(len(fwd)):
            for j in range(i + 3, min(i + 13, len(fwd) + 1)):
                if fwd[i:j] in rc_rev: best = max(best, j - i)
        return best

    app.jinja_env.globals['_dimer_bp'] = _dimer_bp
    app.jinja_env.globals['_cross_dimer_bp'] = _cross_dimer_bp
    # ── Design service ──
    app.config['BASE_TEMPLATE'] = BASE_TEMPLATE
    app.config['DESIGN_TEMPLATE'] = DESIGN_TEMPLATE
    if DESIGN_SERVICE_AVAILABLE:
        from pathlib import Path as _Path
        mgr = DesignJobManager(
            jobs_dir=_Path("design_jobs"),
            species_fasta_dir=_Path("split_species/species")
        )
        app.config['design_mgr'] = mgr
        try:
            from design_web_routes import register_design_routes
            register_design_routes(app)
            print("Design routes registered")
        except ImportError as e:
            print(f"Warning: design_web_routes not available: {e}")
    else:
        print("Warning: DesignJobManager not available")


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

        # 每种类型的 TOP5 物种
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

    # ========== 物种详情 ==========
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

        # 基因组长度估计
        est_genome_len = int(taxonomy.get('genome_length', 0) or 0)

        return render_template_string(SPECIES_TEMPLATE,
            species=species, taxonomy=taxonomy,
            primers=primers, recommended_count=recommended_count,
            est_genome_len=est_genome_len,
            year=datetime.now().year
        )

    # ========== 电子PCR扩增子计算 ==========
    BLAST_DIR = Path("designed_primers/blast")
    MAX_EPCR_AMP_LEN = 5000

    def _compute_epcr_amplicons(species, ptype, pair_id):
        """从 BLAST CSV 中提取配对扩增子（方向相向 + 距离 ≤ 5000bp）"""
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
            # 读取所有匹配的CSV，找到属于此引物对的命中
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

            # 找配对扩增子
            for sid in set(fwd_by_seq.keys()) & set(rev_by_seq.keys()):
                if sid in {'nan', 'None', ''}: continue
                for _, fh in fwd_by_seq[sid].iterrows():
                    for _, rh in rev_by_seq[sid].iterrows():
                        f_plus = fh['Sstart'] < fh['Send']
                        r_plus = rh['Sstart'] < rh['Send']
                        if f_plus == r_plus:
                            continue  # 同向 → 无法扩增
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
            return "引物未找到", 404

        c.execute('SELECT * FROM validation WHERE primer_id = ?', (primer_id,))
        v_row = c.fetchone()

        p = dict(p_row)
        v = dict(v_row) if v_row else None

        # 基因组长度
        c.execute('SELECT genome_length FROM taxonomy WHERE species_name = ?',
                  (p.get('species_name', ''),))
        tax_row = c.fetchone()
        genome_len = tax_row['genome_length'] if tax_row else 0

        # 电子PCR扩增子
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
            <h2 class="mt-4"><i class="bi-download"></i> 数据下载</h2>
            <div class="row g-4 mt-2">
                <div class="col-md-4">
                    <div class="card"><div class="card-body text-center">
                        <i class="bi-filetype-fasta" style="font-size:3em;color:#198754"></i>
                        <h5 class="mt-2">全部引物 FASTA</h5>
                        <p class="text-muted">所有推荐引物的 FASTA 格式</p>
                        <a href="/api/all_primers?format=fasta" class="btn btn-success">下载</a>
                    </div></div>
                </div>
                <div class="col-md-4">
                    <div class="card"><div class="card-body text-center">
                        <i class="bi-filetype-csv" style="font-size:3em;color:#0d6efd"></i>
                        <h5 class="mt-2">引物列表 CSV</h5>
                        <p class="text-muted">完整引物信息表格</p>
                        <a href="/api/all_primers?format=csv" class="btn btn-primary">下载</a>
                    </div></div>
                </div>
                <div class="col-md-4">
                    <div class="card"><div class="card-body text-center">
                        <i class="bi-database" style="font-size:3em;color:#6f42c1"></i>
                        <h5 class="mt-2">SQLite 数据库</h5>
                        <p class="text-muted">完整数据库文件</p>
                        <a href="/api/database" class="btn btn-secondary">下载</a>
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
                "/api/species/<name>": "按物种获取引物 (支持 ?format=json|fasta|csv)",
                "/api/primer/<id>": "按 ID 获取引物详情 (支持 ?format=json|fasta)",
                "/api/search": "搜索引物 (?q=关键词&type=PCR&recommendation=RECOMMENDED)",
                "/api/all_primers": "获取全部引物 (?format=csv|fasta&recommendation=RECOMMENDED)",
                "/api/stats": "获取数据库统计信息",
                "/api/database": "下载 SQLite 数据库文件",
                "/api/taxonomy/<name>": "获取分类学信息"
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

        return jsonify(results[:500])  # JSON 限制 500 条

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
            return jsonify({"reply": "未配置API Key。请点击 ⚙ 设置，或联系管理员在服务器配置。"})

        context = data.get('context', 'primers')
        db = get_db()
        c = db.cursor()

        # 注入 AI 上下文的实时统计
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

        # 物种意图：用 NAME_MAP 别名词典直接扫描消息（拉丁名/通用名/缩写），
        # 命中后解析成 ICTV 规范名再查库。替换旧的触发词正则——旧正则在中英文
        # 绝大多数语序下都取不到物种名，且规范种名落库后按旧名查库必然落空，
        # 静默降级成"无库数据"模式。
        extra_info = ""
        try:
            for canon, matched in _extract_species_from_message(user_msg):
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
                    extra_info = "\n\n[根据用户消息解析出的物种记录——请基于这些数据回答]:\n"
                extra_info += f'- 库内物种: {sp}'
                if sp != canon:
                    extra_info += f'（"{matched}" 的规范名）'
                else:
                    extra_info += f'（用户写法: "{matched}"）'
                extra_info += f' | {r.get("genus") or "属未知"} / {r.get("family") or "科未知"} | 基因组 {r.get("genome_length") or "?"} nt\n'
                c.execute("SELECT primer_type, COUNT(*) as cnt FROM primers WHERE species_name=? GROUP BY primer_type", (sp,))
                pt = dict(c.fetchall())
                c.execute("SELECT recommendation, COUNT(*) FROM validation v JOIN primers p USING(primer_id) WHERE p.species_name=? GROUP BY recommendation", (sp,))
                rt = dict(c.fetchall())
                extra_info += f"  引物类型: {pt}; 评分分布: {rt}\n"
                c.execute('''SELECT p.primer_type, p.fwd_sequence, p.rev_sequence, p.probe_sequence,
                                    p.product_size, p.gc_fwd, p.gc_rev, p.design_method,
                                    v.overall_score, v.recommendation
                             FROM primers p JOIN validation v USING(primer_id)
                             WHERE p.species_name=? ORDER BY v.overall_score DESC LIMIT 5''', (sp,))
                for t in [dict(x) for x in c.fetchall()]:
                    extra_info += f"    [{t['primer_type']}] Fwd={t['fwd_sequence']} Rev={t['rev_sequence']}"
                    if t.get('probe_sequence'): extra_info += f" Probe={t['probe_sequence']}"
                    extra_info += f" | {t['product_size']}bp | GC={t.get('gc_fwd','')}/{t.get('gc_rev','')} | 评分={t['overall_score']} {t['recommendation']}\n"
        except Exception as e:
            app.logger.warning("[api/chat] species lookup failed: %s", e)

        # 知识库接地（explorer / reference_db 分支）：只调本机 RAG 服务的纯检索
        # 接口，不多花一次 LLM 调用，RAG 不可用时静默跳过。
        kb_info = ""
        if context in ('explorer', 'reference_db'):
            try:
                rr = requests.get(KB_SEARCH_URL, params={"q": user_msg, "limit": 3}, timeout=8)
                if rr.status_code == 200:
                    items = (rr.json() or {}).get("results") or []
                    if items:
                        kb_info = "\n\n[知识库检索片段——回答病毒学内容时请以这些片段为准并标注 [来源]]:\n"
                        for k, it in enumerate(items, 1):
                            kb_info += f"[{k}] ({it.get('source', '')}) {it.get('title', '')}: {(it.get('text') or '')[:600]}\n"
            except Exception as e:
                app.logger.warning("[api/chat] KB retrieval failed: %s", e)

        if context == 'reference_db':
            db_context = f"""你是植物病毒参考数据库(Plant Virus Reference Database)的AI助手。完整参考集含约19.9万条植物病毒序列（NCBI GenBank + RefSeq，按95%相似度去冗余后约8,465条），按 ICTV VMR 覆盖约6,200个物种。
本服务器规范物种表实时统计: {total_tax_species} 个物种 / {total_tax_families} 个科；引物层: {total_primers} 对引物，覆盖 {total_species} 个物种。

你可以帮用户:
1. 回答植物病毒分类学问题 (Realm/Kingdom/Phylum/Class/Order/Family/Genus/Species)
2. 解释分节段病毒(Segmented)和非分节段病毒(Non-Segmented)的区别
3. 提供病毒宿主信息查询引导
4. 解释基因组类型 (dsDNA/ssDNA/dsRNA/ssRNA+/ssRNA-等)
5. 说明数据库构建方法和数据来源

注意：
- 库内物种按 ICTV 规范双名存储（如 "Tomato yellow leaf curl virus" → "Begomovirus coheni"）；用户消息里的通用名/缩写会自动解析，命中时下方会附上对应库内记录。
- 若下方附有知识库检索片段，病毒学内容请以片段为准并标注来源；片段不足以回答时如实说明，不要编造。
- 需要具体序列或引物请引导到Primers数据库(/primers/)；可视化分析引导到Explorer(/explorer/)；文献问题引导到知识库(/knowledge/)。
- 保持回复简洁，200字以内"""
        elif context == 'explorer':
            kpis = ((SITE_FACTS.get('full') or {}).get('kpis') or {}) if SITE_FACTS else {}
            top_hosts = ((SITE_FACTS.get('full') or {}).get('topHosts') or []) if SITE_FACTS else []
            hosts_txt = '、'.join(f"{h} ({c})" for h, c in top_hosts[:5]) or '暂无'
            db_context = f"""你是植物病毒时空探索器(Plant Virus Explorer)的AI助手。
站点事实（全量参考集预计算）: {kpis.get('sequences', '~19.9万')} 条序列、{kpis.get('taxids', '~6200')} 个物种、{kpis.get('families', '~49')} 个科；主要宿主: {hosts_txt}。
本服务器实时统计: 规范物种表 {total_tax_species} 个物种 / {total_tax_families} 个科；引物库 {total_primers} 对引物覆盖 {total_species} 个物种，按类型 {type_stats}。

你可以帮用户:
1. 解释如何使用探索器的各项功能
2. 解读时空分布图和CP基因变异分析
3. 解答病毒多样性、宿主分布相关问题
4. 提供数据筛选和导出的指导

注意：
- 数据边界: 交互式查询（地图、BLAST比对、CP变异）在探索器页面内完成；你基于上面的统计数字和下方附带的知识库片段回答。
- 若下方附有知识库检索片段，病毒学内容请以片段为准并标注来源；没有片段时对不确定的内容如实说明。
- 需要具体引物信息请引导用户到Primers数据库(/primers/)；原始数据表引导到Reference DB(/reference/)。
- 保持回复简洁，200字以内"""
        else:
            db_context = f"""你是植物病毒引物数据库(PrimerDB)的AI助手。你可以访问以下实时数据:
- 总引物对: {total_primers}
- 总物种: {total_species}
- 按类型: {type_stats}
- 按评分: {rec_stats}

你可以帮用户:
1. 搜索特定物种的引物 (用URL /search?q=物种名)
2. 比较不同引物类型的优劣
3. 解释验证评分含义 (RECOMMENDED>=80, USABLE 60-79, NOT_RECOMMENDED<60)
4. 推荐针对特定病毒的最佳引物
5. 解答引物设计相关问题

注意：
- 库内物种按 ICTV 规范双名存储（如 "Tomato yellow leaf curl virus" → "Begomovirus coheni"）。用户消息后附有解析出的物种记录时，直接基于这些记录回答，并说明所用的规范名。

回复格式要求:
1. 不用Markdown表格，用简洁的纯文本列表。每条引物一行。
2. Top5引物直接给序列: "[类型] Fwd:XXX Rev:XXX | 产物bp | 评分XX"
3. 分析引物时只列关键指标: Tm/GC/二聚体/特异性，每对引物不超过3行。
4. 保持回复简洁，控制在300字以内。
5. 用户消息后附带的物种记录里如有引物序列，必须逐条列出全部序列，不得省略。
数据库通过SQLite访问，schema为: taxonomy(species_name,genus,family), primers(primer_id,species_name,primer_type,fwd_sequence,rev_sequence,probe_sequence,product_size,design_method), validation(primer_id,overall_score,recommendation,probe_warning)。"""

        messages = [
            {"role": "system", "content": db_context},
        ]
        for item in conversation[-10:]:
            messages.append(item)
        messages.append({"role": "user", "content": user_msg + extra_info + kb_info})

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
                reply = f"API 错误 ({resp.status_code}): {resp.text[:200]}"
        except Exception as e:
            reply = f"连接失败: {str(e)[:200]}"

        return jsonify({"reply": reply})

    return app


def main():
    global DB_PATH
    parser = argparse.ArgumentParser(description="启动植物病毒引物数据库 Web 服务器")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=5000, help="监听端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite 数据库路径")
    args = parser.parse_args()
    DB_PATH = Path(args.db)

    if not DB_PATH.exists():
        print(f"⚠ 数据库不存在: {DB_PATH}")
        print("  请先运行: python step4_build_database.py")
        print("  或使用 --db 指定已有数据库路径")
        print("\n  将以空数据库模式启动 (功能受限)...")
        # 创建空数据库
        conn = sqlite3.connect(str(DB_PATH))
        conn.close()

    app = create_app()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║          植物病毒引物数据库 Web 服务器                          ║
║                                                              ║
║  URL: http://localhost:{args.port}                              ║
║  API: http://localhost:{args.port}/api/                         ║
║                                                              ║
║  页面:                                                        ║
║    /           — 首页 (概览 + 快速搜索)                         ║
║    /search     — 搜索引物                                     ║
║    /browse     — 浏览物种列表                                  ║
║    /species/X  — 物种详情 + 引物列表                            ║
║    /primer/ID  — 引物详情 + 验证结果                            ║
║    /download   — 下载数据                                     ║
║                                                              ║
║  API:                                                        ║
║    /api/species/<name>?format=json|fasta|csv                   ║
║    /api/primer/<id>?format=json|fasta                         ║
║    /api/search?q=<关键词>&type=PCR&recommendation=RECOMMENDED  ║
║    /api/all_primers?format=csv|fasta                          ║
║    /api/stats                                                ║
║    /api/database                                             ║
╚══════════════════════════════════════════════════════════════╝
    """)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
