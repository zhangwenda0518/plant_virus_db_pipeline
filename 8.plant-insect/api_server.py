#!/usr/bin/env python3
"""Virus-Vector-Host + WUR Database Browser."""

import csv, json, os
from pathlib import Path
from collections import defaultdict
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
VH_FILE = Path(__file__).parent / "virus_vector_host.tsv"
WUR_FILE = Path(__file__).parent / "wur_virus_full.tsv"

def load_tsv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))

vh = load_tsv(VH_FILE)
wur = load_tsv(WUR_FILE) if WUR_FILE.exists() else []

with open(Path(__file__).parent / "vector_page.html", encoding="utf-8") as f:
    PAGE = f.read()


@app.route("/vector/")
@app.route("/vector")
def index():
    viruses = len(set(r["Virus Name"] for r in vh))
    vectors = len(set(r["Vector"] for r in vh))
    hosts = len(set(r["Virus Host"] for r in vh))
    families = len(set(r["Virus Family"] for r in vh))
    return render_template_string(PAGE,
        total=len(vh), viruses=viruses, vectors=vectors, hosts=hosts, families=families,
        wur_count=len(wur),
        json_vh=json.dumps(vh, ensure_ascii=False),
        json_wur=json.dumps(wur, ensure_ascii=False))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5005)), debug=False)
