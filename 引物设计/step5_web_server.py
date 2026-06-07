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
DB_PATH = Path("D:/桌面/C-host_classify/引物设计/primer_database.db")

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
                    <li class="nav-item"><a class="nav-link" href="/browse"><i class="bi-list"></i> 浏览</a></li>
                    <li class="nav-item"><a class="nav-link" href="/api/"><i class="bi-code"></i> API</a></li>
                    <li class="nav-item"><a class="nav-link" href="/download"><i class="bi-download"></i> 下载</a></li>
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
    <div class="col-md-3">
        <div class="card card-stat bg-white">
            <div class="number text-primary">{{ species_count }}</div>
            <div class="text-muted">病毒物种</div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card card-stat bg-white">
            <div class="number text-success">{{ primer_count }}</div>
            <div class="text-muted">引物对</div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card card-stat bg-white">
            <div class="number text-info">{{ recommended_count }}</div>
            <div class="text-muted">推荐引物</div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card card-stat bg-white">
            <div class="number text-warning">{{ families_count }}</div>
            <div class="text-muted">病毒科</div>
        </div>
    </div>
</div>

<div class="row">
    <div class="col-md-6">
        <div class="card mb-4">
            <div class="card-header fw-bold"><i class="bi-bar-chart"></i> 引物类型分布</div>
            <div class="card-body">
                <canvas id="typeChart" width="400" height="250"></canvas>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card mb-4">
            <div class="card-header fw-bold"><i class="bi-star"></i> 评分最高的物种</div>
            <div class="card-body">
                <table class="table table-sm table-hover">
                    <thead><tr><th>物种</th><th>属</th><th>评分</th><th>引物数</th></tr></thead>
                    <tbody>
                    {% for row in top_species %}
                    <tr>
                        <td><a href="/species/{{ row.species_name | urlencode }}">{{ row.species_name }}</a></td>
                        <td>{{ row.genus }}</td>
                        <td><span class="score-badge recommended">{{ "%.1f"|format(row.avg_score) }}</span></td>
                        <td>{{ row.primer_count }}</td>
                    </tr>
                    {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<div class="card mb-4">
    <div class="card-header fw-bold"><i class="bi-lightning"></i> 快速入口</div>
    <div class="card-body">
        <div class="row">
            <div class="col-md-4">
                <h6>按引物类型</h6>
                <div class="d-grid gap-2">
                    <a href="/search?type=PCR" class="btn btn-outline-primary btn-sm">PCR 常规检测引物</a>
                    <a href="/search?type=qPCR" class="btn btn-outline-info btn-sm">qPCR 荧光定量引物</a>
                    <a href="/search?type=DEGENERATE" class="btn btn-outline-warning btn-sm">简并引物</a>
                    <a href="/search?type=TILED" class="btn btn-outline-secondary btn-sm">全基因组平铺引物</a>
                </div>
            </div>
            <div class="col-md-4">
                <h6>按评分</h6>
                <div class="d-grid gap-2">
                    <a href="/search?recommendation=RECOMMENDED" class="btn btn-outline-success btn-sm">推荐使用 (≥80分)</a>
                    <a href="/search?recommendation=USABLE" class="btn btn-outline-warning btn-sm">可用 (60-79分)</a>
                </div>
            </div>
            <div class="col-md-4">
                <h6>重要病毒科</h6>
                <div class="d-grid gap-2">
                    {% for fam in top_families %}
                    <a href="/search?family={{ fam.family | urlencode }}" class="btn btn-outline-dark btn-sm">
                        {{ fam.family }} ({{ fam.count }})
                    </a>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')


SEARCH_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''{% block content %}
<h2 class="mt-4"><i class="bi-search"></i> 搜索引物</h2>

<form action="/search" method="GET" class="row g-3 mb-4 bg-light p-3 rounded">
    <div class="col-md-6">
        <label class="form-label">病毒名称/物种</label>
        <input type="text" name="q" class="form-control" value="{{ query or '' }}"
               placeholder="输入物种名、属名或科名">
    </div>
    <div class="col-md-2">
        <label class="form-label">引物类型</label>
        <select name="type" class="form-select">
            <option value="">全部</option>
            {% for t in ['PCR', 'qPCR', 'DEGENERATE', 'TILED'] %}
            <option value="{{ t }}" {% if type_filter == t %}selected{% endif %}>{{ t }}</option>
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
            <span class="score-badge {{ 'recommended' if r.recommendation=='RECOMMENDED' else 'usable' if r.recommendation=='USABLE' else 'not-recommended' }}">
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
</div>

<div class="btn-group mb-3">
    <a href="/api/species/{{ species | urlencode }}?format=fasta" class="btn btn-success">
        <i class="bi-download"></i> 导出 FASTA
    </a>
    <a href="/api/species/{{ species | urlencode }}?format=csv" class="btn btn-primary">
        <i class="bi-download"></i> 导出 CSV
    </a>
</div>

{% if primers %}
<div class="table-responsive">
<table class="table table-hover">
    <thead class="table-dark">
        <tr>
            <th>#</th><th>类型</th><th>正向引物</th><th>反向引物</th>
            <th>探针</th><th>bp</th><th>GC%</th><th>评分</th><th>推荐</th>
        </tr>
    </thead>
    <tbody>
    {% for p in primers %}
    <tr>
        <td>{{ p.pair_id }}</td>
        <td><span class="badge bg-{{ 'primary' if p.primer_type=='PCR' else 'info' if p.primer_type=='qPCR' else 'warning' }}">{{ p.primer_type }}</span></td>
        <td><span class="primer-seq">{{ p.fwd_sequence[:30] }}{% if p.fwd_sequence|length > 30 %}...{% endif %}</span></td>
        <td><span class="primer-seq">{{ p.rev_sequence[:30] }}{% if p.rev_sequence|length > 30 %}...{% endif %}</span></td>
        <td>{% if p.probe_sequence %}<span class="probe-seq">{{ p.probe_sequence[:20] }}...</span>{% else %}-{% endif %}</td>
        <td>{{ p.product_size }}</td>
        <td>{{ "%.1f"|format(p.gc_fwd or 0) }}%/{{ "%.1f"|format(p.gc_rev or 0) }}%</td>
        <td><span class="score-badge {{ 'recommended' if p.recommendation=='RECOMMENDED' else 'usable' }}">{{ "%.0f"|format(p.overall_score or 0) }}</span></td>
        <td><a href="/primer/{{ p.primer_id }}" class="btn btn-sm btn-outline-primary">详情</a></td>
    </tr>
    {% endfor %}
    </tbody>
</table>
</div>
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
                    <tr><td><strong>产物大小</strong></td><td>{{ p.product_size }} bp</td></tr>
                </table>
            </div>
        </div>

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
                <h4 class="{{ 'recommended' if v.recommendation=='RECOMMENDED' else 'usable' if v.recommendation=='USABLE' else 'text-danger' }}">
                    {{ '%.0f'|format(v.overall_score or 0) }} 分 —
                    {% if v.recommendation == 'RECOMMENDED' %}✅ 推荐使用
                    {% elif v.recommendation == 'USABLE' %}⚠️ 可用
                    {% elif v.recommendation == 'CAUTION' %}⚠️ 谨慎使用
                    {% else %}❌ 不推荐{% endif %}
                </h4>

                <h6 class="mt-3">二聚体分析</h6>
                <table class="table table-sm">
                    <tr><td>自身二聚体 (Fwd)</td><td>{{ v.self_dimer_fwd }}bp</td></tr>
                    <tr><td>自身二聚体 (Rev)</td><td>{{ v.self_dimer_rev }}bp</td></tr>
                    <tr><td>交叉二聚体</td><td>{{ v.cross_dimer }}bp</td></tr>
                    <tr class="{{ 'table-danger' if v.cross_dimer_3prime >= 3 else '' }}"><td><strong>3' 交叉二聚体</strong></td><td><strong>{{ v.cross_dimer_3prime }}bp</strong></td></tr>
                </table>
                {% if v.dimer_warning %}<div class="alert alert-warning">{{ v.dimer_warning }}</div>{% endif %}
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


# ======================================================================
# Flask 应用
# ======================================================================

def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    """关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def create_app():
    """创建 Flask 应用"""
    app = Flask(__name__)
    app.teardown_appcontext(close_db)
    app.config['JSON_AS_ASCII'] = False

    # ========== 首页 ==========
    @app.route('/')
    def index():
        db = get_db()
        c = db.cursor()

        c.execute('SELECT COUNT(*) FROM taxonomy')
        species_count = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM primers')
        primer_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM validation WHERE recommendation='RECOMMENDED'")
        recommended_count = c.fetchone()[0]

        c.execute('SELECT COUNT(DISTINCT family) FROM taxonomy WHERE family != ""')
        families_count = c.fetchone()[0]

        c.execute('''
            SELECT t.species_name, t.genus, COUNT(p.primer_id) as primer_count,
                   ROUND(AVG(v.overall_score), 1) as avg_score
            FROM taxonomy t
            JOIN primers p ON t.species_name = p.species_name
            JOIN validation v ON p.primer_id = v.primer_id
            WHERE v.recommendation = 'RECOMMENDED'
            GROUP BY t.species_name
            ORDER BY avg_score DESC
            LIMIT 10
        ''')
        top_species = [dict(r) for r in c.fetchall()]

        c.execute('''
            SELECT family, COUNT(*) as count FROM taxonomy
            WHERE family != "" AND priority = 'HIGH'
            GROUP BY family ORDER BY count DESC LIMIT 6
        ''')
        top_families = [dict(r) for r in c.fetchall()]

        return render_template_string(INDEX_TEMPLATE,
            species_count=species_count,
            primer_count=primer_count,
            recommended_count=recommended_count,
            families_count=families_count,
            top_species=top_species,
            top_families=top_families,
            year=datetime.now().year
        )

    # ========== 搜索 ==========
    @app.route('/search')
    def search():
        db = get_db()
        c = db.cursor()

        query = request.args.get('q', '').strip()
        type_filter = request.args.get('type', '').strip()
        rec_filter = request.args.get('recommendation', '').strip()
        family_filter = request.args.get('family', '').strip()

        where = ['1=1']
        params = []

        if query:
            where.append('''(p.species_name LIKE ? OR t.genus LIKE ?
                          OR t.family LIKE ? OR p.fwd_sequence LIKE ?
                          OR p.rev_sequence LIKE ?)''')
            like_q = f'%{query}%'
            params.extend([like_q, like_q, like_q, like_q, like_q])

        if type_filter:
            where.append('p.primer_type = ?')
            params.append(type_filter)

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
            query=query, type_filter=type_filter, rec_filter=rec_filter,
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
        for row in primers_raw:
            d = dict(row)
            primers.append(d)
            if d.get('recommendation') == 'RECOMMENDED':
                recommended_count += 1

        return render_template_string(SPECIES_TEMPLATE,
            species=species, taxonomy=taxonomy,
            primers=primers, recommended_count=recommended_count,
            year=datetime.now().year
        )

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

        return render_template_string(PRIMER_DETAIL_TEMPLATE,
            p=p, v=v, year=datetime.now().year
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
            where.append('p.species_name LIKE ?')
            params.append(f'%{query}%')
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

    return app


def main():
    parser = argparse.ArgumentParser(description="启动植物病毒引物数据库 Web 服务器")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=5000, help="监听端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite 数据库路径")
    args = parser.parse_args()

    global DB_PATH
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
