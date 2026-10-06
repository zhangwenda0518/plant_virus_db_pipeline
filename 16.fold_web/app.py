# -*- coding: utf-8 -*-
"""16.fold_web — 病毒蛋白结构批量预测平台（Flask）。

  自动：收集(UniProt accession/清单) → ColabFold 预测 → 整理 → 入库 structures_index
  手动：上传 FASTA 建预测任务；上传 ColabFold 结果 ZIP 直接入库
部署：GPU 服务器上 `pip install colabfold[alphafold] flask`，`python app.py`（或 gunicorn -w 1）。
"""
import io
import os
import re
import tempfile
import threading
import zipfile
from pathlib import Path

from flask import Flask, jsonify, request, render_template
from werkzeug.utils import secure_filename

import foldcore as fc

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB 上传上限

ACCESSION_RE = re.compile(
    r"[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}){1,2}[0-9]")
JOBS_FIELDS = ("id", "kind", "status", "progress", "total", "message", "created", "finished")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    return jsonify(fc.coverage_stats())


@app.route("/api/jobs")
def api_jobs():
    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    except ValueError:
        limit = 100
    return jsonify([{k: r[k] for k in JOBS_FIELDS} for r in fc.list_jobs(limit)])


@app.route("/api/job/<int:job_id>/log")
def api_job_log(job_id):
    job = fc.get_job(job_id)
    if not job or not job["log_path"] or not Path(job["log_path"]).exists():
        return jsonify({"log": "(no log)", "status": job["status"] if job else None}), 200
    text = Path(job["log_path"]).read_text(encoding="utf-8", errors="ignore")
    return jsonify({"log": text[-20000:], "status": job["status"]})


@app.route("/api/job/<int:job_id>/retry", methods=["POST"])
def api_job_retry(job_id):
    new_id, err = fc.retry_job(job_id)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"job_id": new_id})


@app.route("/api/job/<int:job_id>", methods=["DELETE"])
def api_job_delete(job_id):
    err = fc.delete_job(job_id)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/job/new", methods=["POST"])
def api_job_new():
    d = request.get_json(silent=True) or {}
    accs = [a.strip().upper() for a in re.split(r"[\s,;]+", d.get("accessions", "")) if a.strip()]
    accs = list(dict.fromkeys(accs))
    if not accs:
        return jsonify({"error": "accessions 为空"}), 400
    if len(accs) > 20000:
        return jsonify({"error": f"单任务最多 20,000 条（收到 {len(accs)}），请分批"}), 400
    bad = [a for a in accs if not ACCESSION_RE.fullmatch(a)]
    if bad:
        return jsonify({"error": f"非 UniProt accession 格式: {bad[:5]}"}), 400
    job_id = fc.create_job("predict", {"accessions": accs})
    return jsonify({"job_id": job_id, "n": len(accs)})


def _save_upload(file_storage, prefix, accept_suffixes):
    """上传落盘到临时目录：文件名不信任客户端，只保留白名单后缀。"""
    suffix = Path(secure_filename(file_storage.filename or "")).suffix.lower()
    if not suffix or (accept_suffixes and suffix not in accept_suffixes):
        return None
    tmpdir = Path(tempfile.mkdtemp(prefix=prefix))
    dest = tmpdir / ("upload" + suffix)
    file_storage.save(dest)
    return dest


@app.route("/api/job/upload_fasta", methods=["POST"])
def api_upload_fasta():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "no file"}), 400
    tmp = _save_upload(f, "foldweb_upload_", (".fa", ".fasta", ".txt"))
    if not tmp:
        return jsonify({"error": "需要 .fa/.fasta/.txt 文件"}), 400
    job_id = fc.create_job("predict", {"fasta_path": str(tmp)})
    return jsonify({"job_id": job_id})


@app.route("/api/job/upload_results", methods=["POST"])
def api_upload_results():
    f = request.files.get("file")
    if not f or not secure_filename(f.filename or "").lower().endswith(".zip"):
        return jsonify({"error": "需要 .zip（ColabFold 输出目录打包）"}), 400
    tmp = _save_upload(f, "foldweb_results_", (".zip",))
    if not tmp:
        return jsonify({"error": "需要 .zip（ColabFold 输出目录打包）"}), 400
    job_id = fc.create_job("ingest_zip", {"zip_path": str(tmp)})
    return jsonify({"job_id": job_id})


@app.route("/pending_accessions.txt")
def pending_accessions():
    accs = "\n".join(r["accession"] for r in fc.iter_index_rows() if not fc.has_own_source(r))
    return app.response_class(accs + "\n", mimetype="text/plain")


@app.route("/api/export/foldify")
def api_export_foldify():
    """导出 Foldify 友好的待预测 FASTA（外部手动通道）。

    Foldify 限制：单序列 ≤600 aa、每用户并发 5、无公开 API —— 只适合人工小批量
    补漏，不能当批量通道。导出口径：待预测清单中 ≤600 aa 的蛋白，按 100 条一个
    文件分块（对应其 ~5 并发的人工消化节奏），另附 manifest。
    同步拉取 UniProt FASTA 可能耗时数分钟，故默认只导 1,000 条（?max= 可调，上限 5,000）。
    """
    try:
        max_n = min(max(int(request.args.get("max", 1000)), 1), 5000)
    except ValueError:
        max_n = 1000
    rows = [r for r in fc.iter_index_rows()
            if not fc.has_own_source(r) and r["length"].isdigit() and 0 < int(r["length"]) <= 600]
    total_pending = len(rows)
    cand = rows[:max_n]
    seqs = fc.fetch_fasta_map([r["accession"] for r in cand])
    cand = [r for r in cand if seqs.get(r["accession"])]
    blocks, meta = [], [["block", "accession", "length", "organism"]]
    per_block = 100
    for i in range(0, len(cand), per_block):
        blk = cand[i:i + per_block]
        fa = []
        for r in blk:
            a = r["accession"]; s = seqs[a]
            meta.append([f"block{i//per_block+1:02d}", a, len(s), r["organism"]])
            fa.append(f">{a} {r['organism']}")
            fa.extend(s[j:j+60] for j in range(0, len(s), 60))
        blocks.append((f"foldify_block{i//per_block+1:02d}.fasta", "\n".join(fa) + "\n"))
    manifest = "block\taccession\tlength\torganism\n" + \
               "\n".join("\t".join(str(x) for x in m) for m in meta[1:])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in blocks:
            z.writestr(name, text)
        z.writestr("foldify_manifest.tsv", manifest)
        z.writestr("README.txt",
            "Foldify 手动通道导出\n"
            "平台: https://foldify-open.cloud.e-infra.cz/  (免费无登录, 单序列<=600aa,\n"
            "并发5, 结果保留7-30天)。每个 block*.fasta 内的序列逐条人工提交;\n"
            "跑完下载结果打包后从本平台「上传结果入库」导回 structures_index。\n\n"
            f"本次导出: {len(cand)} 条 (<=600aa 待预测共 {total_pending} 条,\n"
            f"受 max={max_n} 限制; UniProt 实际取回序列 {len(cand)} 条)。\n")
    buf.seek(0)
    return app.response_class(buf.read(), mimetype="application/zip",
                              headers={"Content-Disposition":
                                       "attachment; filename=foldify_export.zip"})


_worker_lock = threading.Lock()
_worker_started = False


@app.before_request
def ensure_worker():
    global _worker_started
    if not _worker_started:
        with _worker_lock:
            if not _worker_started:
                fc.Worker().start()
                _worker_started = True


if __name__ == "__main__":
    # 生产环境用 gunicorn -w 1 -b 127.0.0.1:8800 app:app（worker 线程随首个请求启动；
    # 更稳妥可用 systemd 单独跑 `python -c "import foldcore as fc; fc.Worker().start(); import time; time.sleep(1<<30)"`）
    app.run(host=os.environ.get("FOLDWEB_HOST", "127.0.0.1"),
            port=int(os.environ.get("FOLDWEB_PORT", "8800")), threaded=True)
