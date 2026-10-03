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

# 预合并数据（由 build_vector_db.py 生成），作为「整合视图」的权威来源。
# 缺失时不再静默渲染空视图: 置 data_missing 标志, /vector/ 顶部渲染警告条 (审计修复)。
if MERGED_FILE.exists():
    with open(MERGED_FILE, encoding="utf-8") as f:
        merged = json.load(f)
    merged.setdefault("data_missing", False)
else:
    print(f"[warn] {MERGED_FILE.name} 缺失 — Integrated Cards 视图将为空; "
          f"请先在 8.plant-insect/ 运行: python build_vector_db.py")
    merged = {"stats": {}, "viruses": [], "data_missing": True}

# 文献挖掘边（kg 三元组生成，见 build_lit_edges.py）
LIT_FILE = Path(__file__).parent / "vector_host_lit.json"
if LIT_FILE.exists():
    with open(LIT_FILE, encoding="utf-8") as f:
        lit = json.load(f)
else:
    lit = {"stats": {}, "edges": []}

# TaxID → ICTV 学名映射 + 病毒俗名 → ICTV 学名映射。
# Explorer 的 profile 深链只认 ICTV 双名（PROFILE_SPECIES），
# 而本页数据用的是俗名（Tomato spotted wilt virus），
# 通过参考库 TSV 的 Taxid 列桥接二者，供前端生成 /explorer/?profile= 链接。
REF_TSV = Path(__file__).parent.parent / "docs" / "data" / "Plant_Virus_Ref.Info.tsv"
tmap = {}
if REF_TSV.exists():
    with open(REF_TSV, encoding="utf-8", errors="replace") as f:
        for _row in csv.DictReader(f, delimiter="\t"):
            _tx = (_row.get("Taxid", "") or "").strip()
            _sp = (_row.get("Species_ICTV", "") or _row.get("Species_NCBI", "")).strip()
            if _tx and _sp:
                tmap[_tx] = _sp
nmap = {}
for _r in vh:
    _nm = (_r.get("Virus Name", "") or "").strip()
    _tx = (_r.get("Virus TaxID", "") or "").strip()
    if _nm and _tx and _tx in tmap:
        nmap[_nm] = tmap[_tx]

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
        data_missing=bool(merged.get("data_missing", False)),
        m_total=ms.get("total_viruses", 0),
        m_both=ms.get("source_both", 0),
        m_vh_only=ms.get("source_vh_only", 0),
        m_wur_only=ms.get("source_wur_only", 0),
        m_conflicts=ms.get("family_conflicts", 0),
        json_vh=json.dumps(vh, ensure_ascii=False),
        json_wur=json.dumps(wur, ensure_ascii=False),
        json_merged=json.dumps(merged.get("viruses", []), ensure_ascii=False),
        lit_edges=lit.get("stats", {}).get("total_edges", 0),
        lit_viruses=lit.get("stats", {}).get("viruses", 0),
        lit_papers=lit.get("stats", {}).get("papers", 0),
        json_lit=json.dumps(lit, ensure_ascii=False),
        json_nmap=json.dumps(nmap, ensure_ascii=False))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5005)), debug=False)
