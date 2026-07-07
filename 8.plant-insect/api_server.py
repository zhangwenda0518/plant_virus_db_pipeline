#!/usr/bin/env python3
"""Virus-Vector-Host + WUR Database Browser."""

import csv, json, os
from pathlib import Path
from collections import defaultdict
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
VH_FILE = Path(__file__).parent / "virus_vector_host.tsv"
WUR_FILE = Path(__file__).parent / "wur_virus_full.tsv"
MERGED_FILE = Path(__file__).parent / "virus_vector_merged.json"

def load_tsv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))

vh = load_tsv(VH_FILE)
wur = load_tsv(WUR_FILE) if WUR_FILE.exists() else []
# refs 列为 scrape_wur.py 输出的 JSON 数组，解析为结构化对象供前端展示
for _r in wur:
    _raw = (_r.get("refs", "") or "").strip()
    try:
        _r["refs"] = json.loads(_raw) if _raw.startswith("[") else []
    except (ValueError, TypeError):
        _r["refs"] = []

# 预合并数据（由 build_vector_db.py 生成），作为「整合视图」的权威来源
if MERGED_FILE.exists():
    with open(MERGED_FILE, encoding="utf-8") as f:
        merged = json.load(f)
else:
    merged = {"stats": {}, "viruses": []}

with open(Path(__file__).parent / "vector_page.html", encoding="utf-8") as f:
    PAGE = f.read()


@app.route("/vector/")
@app.route("/vector")
def index():
    viruses = len(set(r["Virus Name"] for r in vh))
    vectors = len(set(r["Vector"] for r in vh))
    hosts = len(set(r["Virus Host"] for r in vh))
    families = len(set(r["Virus Family"] for r in vh))
    ms = merged.get("stats", {})
    return render_template_string(PAGE,
        total=len(vh), viruses=viruses, vectors=vectors, hosts=hosts, families=families,
        wur_count=len(wur),
        m_total=ms.get("total_viruses", 0),
        m_both=ms.get("source_both", 0),
        m_vh_only=ms.get("source_vh_only", 0),
        m_wur_only=ms.get("source_wur_only", 0),
        m_conflicts=ms.get("family_conflicts", 0),
        json_vh=json.dumps(vh, ensure_ascii=False),
        json_wur=json.dumps(wur, ensure_ascii=False),
        json_merged=json.dumps(merged.get("viruses", []), ensure_ascii=False))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5005)), debug=False)
