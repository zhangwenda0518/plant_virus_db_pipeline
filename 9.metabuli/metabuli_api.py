#!/usr/bin/env python3
"""Metabuli Contig Classification API."""

import os, json, uuid, time, subprocess, threading, shutil, re
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template_string, Response

app = Flask(__name__)

METABULI_BIN = "/usr/local/bin/metabuli"
METABULI_DB = "/opt/plant_virus_db/ref.virus.build.metabuli_db"
JOBS_DIR = Path("/opt/plant_virus_db/metabuli_jobs")
MAX_SIZE = 100 * 1024 * 1024
os.makedirs(JOBS_DIR, exist_ok=True)
jobs = {}

# 标准病毒分类 8 级 (域界门纲目科属种)
RANKS = ["realm", "kingdom", "phylum", "class", "order", "family", "genus", "species"]


def _load_taxlin(path):
    """加载 build_taxid_lineage.py 生成的权威 taxid → ICTV 8 级分类表。"""
    tl = {}
    if not path.exists():
        return tl
    with open(path, encoding="utf-8", errors="replace") as f:
        f.readline()  # header: taxid, sciname, realm..species
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 2:
                continue
            rec = {"sciname": p[1]}
            for i, r in enumerate(RANKS):
                rec[r] = p[2 + i] if 2 + i < len(p) else ""
            tl[p[0]] = rec
    return tl


TAXLIN = _load_taxlin(Path(__file__).parent / "taxid_lineage.tsv")
print(f"Taxid lineage: {len(TAXLIN)} entries")


def _parse_fasta(path):
    """纯 Python 解析 FASTA，键为 header 首个空白前的 token（与 Metabuli contig 名一致）。"""
    seqs, name, buf = {}, None, []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(">"):
                if name is not None:
                    seqs[name] = "".join(buf)
                name = line[1:].strip().split()[0] if line[1:].strip() else ""
                buf = []
            else:
                buf.append(line.strip())
    if name is not None:
        seqs[name] = "".join(buf)
    return seqs


def _wrap(seq, w=70):
    return "\n".join(seq[i:i + w] for i in range(0, len(seq), w))


def _extract_virus(job_id, outdir, cls_path, fasta_path):
    """提取被分类(视为病毒)的 contig：输出分类表 TSV + 序列 FASTA。
    分类等级取自权威 taxid_lineage 表(NCBI/ICTV 完整谱系)。
    返回 (virus_fasta_path, virus_tsv_path, n_virus, n_total, rows)。"""
    contigs, n_total = [], 0
    with open(cls_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 3:
                continue
            n_total += 1
            if p[0] != "1":          # is_classified != 1 → 未分类，跳过
                continue
            contigs.append((p[1], p[2], p[3] if len(p) > 3 else "", p[4] if len(p) > 4 else ""))
    seqs = _parse_fasta(fasta_path) if fasta_path.exists() else {}
    vtsv = outdir / f"{job_id}_virus_classification.tsv"
    vfa = outdir / f"{job_id}_virus_sequences.fasta"
    rows = []
    with open(vtsv, "w", encoding="utf-8") as ft, open(vfa, "w", encoding="utf-8") as fa:
        ft.write("contig\ttaxid\ttaxon\t" + "\t".join(RANKS) + "\tlength\tscore\n")
        for name, taxid, length, score in contigs:
            info = TAXLIN.get(taxid, {})
            taxon = info.get("sciname", "")
            rankvals = [info.get(r, "") for r in RANKS]
            ft.write("\t".join([name, taxid, taxon] + rankvals + [length, score]) + "\n")
            row = {"contig": name, "taxid": taxid, "taxon": taxon, "length": length, "score": score}
            for r in RANKS:
                row[r] = info.get(r, "")
            rows.append(row)
            seq = seqs.get(name)
            if seq:
                lineage = ";".join(v for v in rankvals if v)
                fa.write(f">{name} taxid={taxid} taxon={taxon.replace(' ', '_')} lineage={lineage}\n{_wrap(seq)}\n")
    return str(vfa), str(vtsv), len(contigs), n_total, rows

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
        # 病毒序列分类结果 + 序列提取（在删除输入前完成）
        if tsv.exists():
            try:
                vfa, vtsv, n_virus, n_total, vrows = _extract_virus(job_id, outdir, tsv, fasta_path)
                job["files"]["virus_fasta"] = vfa if n_virus > 0 else None
                job["files"]["virus_tsv"] = vtsv if n_virus > 0 else None
                job["virus_summary"] = {"virus_contigs": n_virus, "total_contigs": n_total}
                job["virus_contigs"] = vrows[:5000]
            except Exception as e:
                job["virus_error"] = str(e)
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


@app.route("/metabuli/virus_contigs/<job_id>")
def virus_contigs_json(job_id):
    j = jobs.get(job_id, {})
    return jsonify({"summary": j.get("virus_summary", {}), "contigs": j.get("virus_contigs", [])})


def _strip_unclassified(html):
    """从 Krona HTML 中移除 unclassified 叶节点，并把父节点 'all' 的总量相应减少，
    使 classified 部分占满 100%。找不到则原样返回（安全回退）。"""
    m = re.search(r'<node name="unclassified"><magnitude><val>([\d.]+)</val></magnitude></node>', html)
    if not m:
        return html
    u = float(m.group(1))
    html = html[:m.start()] + html[m.end():]
    am = re.search(r'(<node name="all"><magnitude><val>)([\d.]+)(</val>)', html)
    if am:
        new = float(am.group(2)) - u
        newstr = str(int(new)) if new == int(new) else ("%g" % new)
        html = html[:am.start()] + am.group(1) + newstr + am.group(3) + html[am.end():]
    return html


@app.route("/metabuli/krona/<job_id>")
def krona_view(job_id):
    j = jobs.get(job_id, {})
    p = j.get("files", {}).get("krona")
    if not p or not os.path.exists(p):
        return jsonify({"error": "Not found"}), 404
    # 默认隐藏 unclassified；?unclassified=1 时显示原图
    if request.args.get("unclassified") == "1":
        return send_file(p)
    html = Path(p).read_text(encoding="utf-8", errors="replace")
    return Response(_strip_unclassified(html), mimetype="text/html")

@app.route("/metabuli/download/<job_id>/<ftype>")
def download(job_id, ftype):
    j = jobs.get(job_id, {})
    p = j.get("files",{}).get(ftype)
    if not p or not os.path.exists(p): return jsonify({"error":"Not found"}), 404
    return send_file(p, as_attachment=True)

# Separate HTML file for cleaner maintenance
HTML_FILE = Path(__file__).parent / "metabuli_page.html"
EXAMPLES_FILE = Path(__file__).parent / "metabuli_examples.json"


@app.route("/metabuli/examples")
def examples():
    if EXAMPLES_FILE.exists():
        with open(EXAMPLES_FILE, encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({})


@app.route("/metabuli/")
def index():
    if HTML_FILE.exists():
        return render_template_string(HTML_FILE.read_text(encoding="utf-8"))
    return "<h1>Page not found</h1>", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5004)), debug=False)
