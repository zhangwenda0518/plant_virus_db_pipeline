#!/usr/bin/env python3
"""Metabuli Contig Classification API."""

import os, json, uuid, time, subprocess, threading, shutil
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template_string

app = Flask(__name__)

METABULI_BIN = "/usr/local/bin/metabuli"
METABULI_DB = "/opt/plant_virus_db/ref.virus.build.metabuli_db"
JOBS_DIR = Path("/opt/plant_virus_db/metabuli_jobs")
MAX_SIZE = 100 * 1024 * 1024
os.makedirs(JOBS_DIR, exist_ok=True)
jobs = {}

def _classify(job_id, fasta_path):
    job = jobs.get(job_id)
    if not job: return
    outdir = JOBS_DIR / job_id / "output"
    os.makedirs(outdir, exist_ok=True)
    job["status"] = "running"
    try:
        subprocess.run([METABULI_BIN, "classify", str(fasta_path), METABULI_DB, str(outdir),
            job_id, "--seq-mode","3", "--threads","2", "--max-ram","1"],
            capture_output=True, text=True, timeout=600)
        tsv = outdir / f"{job_id}_classifications.tsv"
        rept = outdir / f"{job_id}_report.tsv"
        kr = outdir / f"{job_id}_krona.html"
        ok = tsv.exists() or rept.exists()
        job["status"] = "done" if ok else "no_result"
        job["files"] = {"classifications": str(tsv) if tsv.exists() else None,
            "report": str(rept) if rept.exists() else None,
            "krona": str(kr) if kr.exists() else None}
        if rept.exists():
            top = []
            with open(rept) as f:
                for line in f:
                    if line.startswith("#") or not line.strip(): continue
                    p = line.strip().split("\t")
                    if len(p) >= 6: top.append({"proportion":p[0],"count":p[1],"taxon_count":p[2],"rank":p[3],"taxid":p[4],"name":p[5]})
                    if len(top) >= 15: break
            job["summary"] = top
        if fasta_path.exists(): fasta_path.unlink()
        def _c():
            time.sleep(7200)
            d = JOBS_DIR / job_id
            if d.exists(): shutil.rmtree(d, ignore_errors=True)
            jobs.pop(job_id, None)
        threading.Thread(target=_c, daemon=True).start()
    except subprocess.TimeoutExpired:
        job["status"] = "timeout"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)

def _start(content, fname):
    jid = uuid.uuid4().hex[:12]
    jd = JOBS_DIR / jid; os.makedirs(jd, exist_ok=True)
    fp = jd / "input.fasta"; fp.write_bytes(content)
    jobs[jid] = {"id":jid, "status":"queued", "created":datetime.now().isoformat(),
        "filename":fname, "size":len(content), "files":{}}
    threading.Thread(target=_classify, args=(jid, fp), daemon=True).start()
    return jsonify({"job_id":jid, "status":"queued"})

@app.route("/metabuli/classify", methods=["POST"])
def classify():
    f = request.files.get("file")
    if f and f.filename and f.filename.lower().endswith((".fasta",".fa",".fna",".faa")):
        c = f.read()
        if len(c) > MAX_SIZE: return jsonify({"error":"File >100MB"}), 400
        return _start(c, f.filename)
    data = request.get_json(silent=True) or {}
    seq = data.get("sequence","").strip()
    if seq:
        if not seq.startswith(">"): return jsonify({"error":"Must start with >"}), 400
        if len(seq) > MAX_SIZE: return jsonify({"error":"Input >100MB"}), 400
        return _start(seq.encode(), "pasted.fasta")
    return jsonify({"error":"No input"}), 400

@app.route("/metabuli/status/<job_id>")
def status(job_id):
    j = jobs.get(job_id)
    return jsonify(j) if j else (jsonify({"error":"Not found"}), 404)

@app.route("/metabuli/classifications/<job_id>")
def classifications_json(job_id):
    j = jobs.get(job_id, {})
    p = j.get("files",{}).get("classifications")
    if not p or not os.path.exists(p): return jsonify({"error":"Not found"}), 404
    data = []
    with open(p) as f:
        for line in f:
            if line.startswith("#") or not line.strip(): continue
            parts = line.strip().split("\t")
            if len(parts) >= 8:
                data.append({"classified":parts[0],"name":parts[1],"taxid":parts[2],
                    "length":parts[3],"score":parts[4],"evalue":parts[5],"rank":parts[6],
                    "lineage":parts[7] if len(parts)>7 else ""})
    return jsonify(data)

@app.route("/metabuli/report/<job_id>")
def report_json(job_id):
    j = jobs.get(job_id, {})
    p = j.get("files",{}).get("report")
    if not p or not os.path.exists(p): return jsonify({"error":"Not found"}), 404
    data = []
    with open(p) as f:
        for line in f:
            if line.startswith("#") or not line.strip(): continue
            parts = line.strip().split("\t")
            if len(parts) >= 6:
                data.append({"proportion":parts[0],"count":parts[1],"taxon_count":parts[2],
                    "rank":parts[3],"taxid":parts[4],"name":parts[5]})
    return jsonify(data)

@app.route("/metabuli/krona/<job_id>")
def krona_view(job_id):
    j = jobs.get(job_id, {})
    p = j.get("files",{}).get("krona")
    if not p or not os.path.exists(p): return jsonify({"error":"Not found"}), 404
    return send_file(p)

@app.route("/metabuli/download/<job_id>/<ftype>")
def download(job_id, ftype):
    j = jobs.get(job_id, {})
    p = j.get("files",{}).get(ftype)
    if not p or not os.path.exists(p): return jsonify({"error":"Not found"}), 404
    return send_file(p, as_attachment=True)

# Separate HTML file for cleaner maintenance
HTML_FILE = Path(__file__).parent / "metabuli_page.html"

@app.route("/metabuli/")
def index():
    if HTML_FILE.exists():
        return render_template_string(HTML_FILE.read_text(encoding="utf-8"))
    return "<h1>Page not found</h1>", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5004)), debug=False)
