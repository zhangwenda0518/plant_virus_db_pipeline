# -*- coding: utf-8 -*-
"""16.fold_web — ColabFold 批量预测平台核心：任务队列 + 收集 + 运行 + 整理入库。

流程（自动）：收集(UniProt 按 accession/清单拉 FASTA) → 预测(colabfold_batch 子进程)
→ 整理(取 rank_001 + pLDDT 校验) → 入库(structures_index.tsv sources+=SELF + 模型落盘)。
手动：上传 FASTA 直接建预测任务；上传 colabfold 结果 ZIP 直接入库。

环境变量（均可在 README 部署节查默认值）：
  FOLDWEB_MODULE_DIR  数据模块根（默认 ../../15.uniprot_plant_virus_structures）
  FOLDWEB_DB          任务库 SQLite 路径（默认 <module>/colabfold_input/fold_jobs.db）
  FOLDWEB_PREDICT_CMD 预测命令模板，{input} {output} 占位（默认 colabfold_batch ...）
  FOLDWEB_JOBS_DIR    工作目录（默认 <module>/colabfold_input/jobs）
"""
import csv
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
MODULE = Path(os.environ.get(
    "FOLDWEB_MODULE_DIR",
    (BASE.parent / "15.uniprot_plant_virus_structures"))).resolve()
DB_PATH = Path(os.environ.get("FOLDWEB_DB", MODULE / "colabfold_input" / "fold_jobs.db"))
JOBS_DIR = Path(os.environ.get("FOLDWEB_JOBS_DIR", MODULE / "colabfold_input" / "jobs"))
SELF_DIR = MODULE / "structures_selffold"
INDEX = MODULE / "structures_index.tsv"
PREDICT_CMD = os.environ.get(
    "FOLDWEB_PREDICT_CMD",
    "colabfold_batch --msa-mode mmseqs2_uniref_env --num-models 3 --num-recycle 3 "
    "--model-type alphafold2_ptm --rank plddt {input} {output}")
UA = "plant_virus_db_pipeline/1.0"

# 手动上传 ZIP 的解压预检上限（防 zip 炸弹撑爆磁盘）
ZIP_MAX_BYTES = 50 * 1024 ** 3
ZIP_MAX_MEMBERS = 200_000

# 「自身结构」口径：sources 含任一即算（与 15 模块/前端三处保持一致）
OWN_SOURCES = ("PDB", "AFDB", "RVPSD", "SELF")


def iter_index_rows():
    with open(INDEX, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t")


def has_own_source(row):
    return any(s in row["sources"].split(",") for s in OWN_SOURCES)

DDL = """
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT,             -- predict | ingest_zip
  status TEXT,           -- queued | collecting | running | ingesting | done | error
  params TEXT,           -- JSON
  progress INTEGER DEFAULT 0,
  total INTEGER DEFAULT 0,
  message TEXT DEFAULT '',
  workdir TEXT,
  log_path TEXT,
  created TEXT, finished TEXT
);
"""


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(DDL)
    return conn


def create_job(kind, params):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO jobs(kind,status,params,progress,total,message,created) "
            "VALUES(?,?,?,0,0,'',?)",
            (kind, "queued", json.dumps(params, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")))
        return cur.lastrowid


def update_job(job_id, **kw):
    with db() as conn:
        sets = ", ".join(f"{k}=?" for k in kw)
        conn.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*kw.values(), job_id))


def get_job(job_id):
    with db() as conn:
        return conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


def list_jobs(limit=100):
    with db() as conn:
        return conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# ---------------------------------------------------------------- collector
def fetch_fasta_map(accs, log=print):
    """UniProt 分块拉 FASTA -> {acc: seq}（curl 子进程重试，复用 15 模块验证过的通道）。"""
    accs = list(dict.fromkeys(accs))
    out = {}
    tmpfd, tmppath = tempfile.mkstemp(suffix=".fa")
    os.close(tmpfd)
    CH = 100
    try:
        for i in range(0, len(accs), CH):
            chunk = accs[i:i + CH]
            q = "%20OR%20".join("accession:" + a for a in chunk)
            url = f"https://rest.uniprot.org/uniprotkb/stream?query=({q})&format=fasta"
            ok = False
            for attempt in range(5):
                # 每次尝试前清空临时文件：失败重试时避免把上一块残留当成本块结果
                open(tmppath, "w").close()
                rc = subprocess.run(["curl", "-s", "--compressed", "--retry", "3",
                                     "--retry-all-errors", "--max-time", "600",
                                     "-o", tmppath, url]).returncode
                if rc == 0:
                    ok = True
                    break
                time.sleep(3 * (attempt + 1))
            if not ok:
                log(f"WARN chunk {i // CH + 1}: curl 5 次重试后仍失败，跳过 {len(chunk)} 条")
                continue
            acc = None
            for line in open(tmppath, encoding="utf-8"):
                if line.startswith(">"):
                    parts = line[1:].split("|")
                    acc = parts[1].strip() if len(parts) >= 3 else line[1:].split()[0].strip()
                    out[acc] = []
                elif acc:
                    out[acc].append(line.strip())
            log(f"collected {len(out)}/{len(accs)}")
    finally:
        try:
            os.remove(tmppath)
        except OSError:
            pass
    return {a: "".join(v) for a, v in out.items()}


# ---------------------------------------------------------------- runner
def job_logger(log_path):
    """任务日志：收集/入库阶段的进度写入 runner.log（与 colabfold 输出同文件，页面上可看）。"""
    def log(msg):
        stamp = datetime.now().strftime("%H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(f"[{stamp}] {msg}\n")
    return log


def run_collect_predict(job_id, params):
    """任务类型 predict：params.accessions 列表 或 params.fasta 上传文件路径。"""
    workdir = JOBS_DIR / f"job{job_id:04d}"
    (workdir / "input").mkdir(parents=True, exist_ok=True)
    (workdir / "output").mkdir(parents=True, exist_ok=True)
    log_path = workdir / "runner.log"
    log = job_logger(log_path)
    update_job(job_id, workdir=str(workdir), status="collecting",
               log_path=str(log_path))

    if params.get("fasta_path"):
        shutil.copy(params["fasta_path"], workdir / "input" / "upload.fasta")
        accs = [l[1:].split()[0].strip() for l in
                open(workdir / "input" / "upload.fasta", encoding="utf-8") if l.startswith(">")]
        log(f"uploaded fasta: {len(accs)} seqs")
    else:
        accs = params.get("accessions", [])
        seqs = fetch_fasta_map(accs, log=log)
        with open(workdir / "input" / "collected.fasta", "w", encoding="utf-8") as f:
            for a in accs:
                if a in seqs and seqs[a]:
                    f.write(f">{a}\n" + "\n".join(seqs[a][i:i+60] for i in range(0, len(seqs[a]), 60)) + "\n")
        log(f"collected {sum(1 for a in accs if seqs.get(a))}/{len(accs)} sequences")

    fasta = workdir / "input" / ("upload.fasta" if params.get("fasta_path") else "collected.fasta")
    n = sum(1 for l in open(fasta, encoding="utf-8") if l.startswith(">"))
    if n == 0:
        update_job(job_id, status="error", message="no sequences resolved", finished=now())
        return
    update_job(job_id, status="running", total=n,
               message=f"colabfold_batch running on {n} seqs")
    cmd = PREDICT_CMD.format(input=str(fasta), output=str(workdir / "output"))
    with open(workdir / "runner.log", "a", encoding="utf-8") as lf:
        lf.write(f"$ {cmd}\n")
        p = subprocess.Popen(cmd, shell=True, stdout=lf, stderr=subprocess.STDOUT)
    while p.poll() is None:
        time.sleep(10)
        done = count_results(workdir / "output")
        update_job(job_id, progress=done)
    if p.returncode != 0:
        update_job(job_id, status="error", message=f"colabfold exit {p.returncode}", finished=now())
        return
    update_job(job_id, status="ingesting", progress=count_results(workdir / "output"))
    stats = ingest_colabfold_dir(workdir / "output", log=log)
    update_job(job_id, status="done", progress=stats["ingested"],
               message=f"ingested {stats['ingested']} models ({stats['mean_plddt']:.0f} avg pLDDT)",
               finished=now())


def check_zip_safe(zpath):
    """解压预检：成员数 / 总解压量 / 路径合法性。raise ValueError 则拒绝入库。"""
    with zipfile.ZipFile(zpath) as z:
        infos = z.infolist()
        if len(infos) > ZIP_MAX_MEMBERS:
            raise ValueError(f"zip 成员数 {len(infos)} 超上限 {ZIP_MAX_MEMBERS}")
        total = 0
        for zi in infos:
            total += zi.file_size
            if total > ZIP_MAX_BYTES:
                raise ValueError(f"zip 解压总量超 {ZIP_MAX_BYTES // 1024 ** 3} GB 上限")
            name = zi.filename.replace("\\", "/")
            parts = name.split("/")
            if name.startswith("/") or ".." in parts or (len(parts[0]) == 2 and parts[0][1] == ":"):
                raise ValueError(f"非法 zip 成员路径: {zi.filename!r}")


def run_ingest_zip(job_id, params):
    """任务类型 ingest_zip：手动上传 colabfold 结果 ZIP（或目录内直接挑文件）。"""
    zpath = Path(params["zip_path"])
    workdir = JOBS_DIR / f"job{job_id:04d}"
    workdir.mkdir(parents=True, exist_ok=True)
    outdir = workdir / "output"
    outdir.mkdir(exist_ok=True)
    log = job_logger(workdir / "runner.log")
    update_job(job_id, status="ingesting", workdir=str(workdir),
               log_path=str(workdir / "runner.log"))
    check_zip_safe(zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(outdir)
    stats = ingest_colabfold_dir(outdir, log=log)
    update_job(job_id, status="done", progress=stats["ingested"], total=stats["ingested"],
               message=f"ingested {stats['ingested']} models", finished=now())


def count_results(outdir):
    return sum(1 for _ in outdir.glob("**/*rank_001*.pdb")) if Path(outdir).exists() else 0


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- ingest
def find_best_model(job_out_dir, acc):
    """colabfold 输出目录里找该 accession 的 rank_001 模型 + 平均 pLDDT。"""
    cands = list(job_out_dir.glob(f"**/{acc}/**/*rank_001*.pdb")) + \
            list(job_out_dir.glob(f"**/{acc}_*rank_001*.pdb")) + \
            list(job_out_dir.glob(f"**/{acc}.*rank_001*.pdb"))
    pdb = next((p for p in cands if "relaxed" in p.name or "unrelaxed" in p.name), cands[0] if cands else None)
    if not pdb:
        return None, None
    plddt = None
    for sj in job_out_dir.glob(f"**/{acc}_*scores_rank_001*.json"):
        try:
            d = json.loads(sj.read_text(encoding="utf-8"))
            if "mean_plddt" in d:
                plddt = round(float(d["mean_plddt"]), 1)
                break
        except Exception:
            pass
    if plddt is None:
        bs = []
        for l in pdb.read_text(encoding="utf-8", errors="ignore").splitlines():
            if l.startswith(("ATOM", "HETATM")) and len(l) >= 66:
                try:
                    bs.append(float(l[60:66]))  # PDB 规范: B-factor 固定列 61-66
                except ValueError:
                    pass
        if bs:
            plddt = round(sum(bs) / len(bs), 1)
    return pdb, plddt


def ingest_colabfold_dir(job_out_dir, log=print):
    """把 colabfold 结果整理入库：模型落盘 structures_selffold/，index sources+=SELF。"""
    SELF_DIR.mkdir(parents=True, exist_ok=True)
    accs = set()
    for p in job_out_dir.glob("**/*rank_001*.pdb"):
        # 目录名/文件名以 accession 开头
        m = re.search(r"([A-Z0-9]{6,10})(?:[._]|$)", p.name)
        if m:
            accs.add(m.group(1))
    idx = list(csv.DictReader(open(INDEX, encoding="utf-8"), delimiter="\t"))
    known = {r["accession"]: r for r in idx}
    ingested, plddts = 0, []
    manifest_path = SELF_DIR / "selffold_manifest.tsv"
    man_exists = manifest_path.exists()
    with open(manifest_path, "a", newline="", encoding="utf-8") as mf:
        w = csv.writer(mf, delimiter="\t")
        if not man_exists:
            w.writerow(["accession", "file", "mean_pLDDT", "ingested"])
        for acc in sorted(accs):
            pdb, plddt = find_best_model(job_out_dir, acc)
            if not pdb:
                log(f"skip {acc}: no rank_001 model")
                continue
            dst = SELF_DIR / f"{acc}.pdb"
            shutil.copy2(pdb, dst)
            w.writerow([acc, dst.name, plddt if plddt is not None else "", now()])
            ingested += 1
            if plddt:
                plddts.append(plddt)
            if acc in known:
                r = known[acc]
                if "SELF" not in r["sources"].split(","):
                    r["sources"] = ",".join(filter(None, r["sources"].split(",") + ["SELF"]))
                if r.get("selffold_model", "") == "":
                    r["selffold_model"] = dst.name
    # 写回 index（临时文件 + 原子替换，避免并发读到半截 TSV）
    cols = list(idx[0].keys())
    if "selffold_model" not in cols:
        cols.append("selffold_model")
    for r in idx:
        r.setdefault("selffold_model", "")
    tmp_index = INDEX.with_name(INDEX.name + ".tmp")
    with open(tmp_index, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader(); w.writerows(idx)
    os.replace(tmp_index, INDEX)
    log(f"ingested {ingested} self models into structures_index")
    return {"ingested": ingested, "mean_plddt": (sum(plddts)/len(plddts)) if plddts else 0}


# ---------------------------------------------------------------- stats
def group_by_organism(rows):
    out = {}
    for r in rows:
        o = out.setdefault(r["organism"], {"n": 0, "own": 0, "n_any": 0})
        o["n"] += 1
        if has_own_source(r):
            o["own"] += 1
        if r["sources"]:
            o["n_any"] += 1
    return out


def coverage_stats():
    rows = list(iter_index_rows())
    N = len(rows)
    own = sum(1 for r in rows if has_own_source(r))
    anyv = sum(1 for r in rows if r["sources"])
    by_org = group_by_organism(rows)
    return {"proteins": N, "own": own, "any": anyv,
            "missing": N - anyv, "own_missing": N - own,
            "species": len(by_org),
            "species_own": sum(1 for v in by_org.values() if v["own"] > 0),
            "species_full_own": sum(1 for v in by_org.values() if v["own"] == v["n"]),
            "species_zero_any": sum(1 for v in by_org.values() if v["n_any"] == 0),
            "species_zero_own": sum(1 for v in by_org.values() if v["own"] == 0)}


# ---------------------------------------------------------------- job ops
def retry_job(job_id):
    """对 error 状态任务按原参数重新排队；返回 (new_id, error)。"""
    job = get_job(job_id)
    if not job:
        return None, "job not found"
    if job["status"] != "error":
        return None, f"仅失败任务可重试（当前 {job['status']}）"
    return create_job(job["kind"], json.loads(job["params"])), None


def delete_job(job_id):
    """删除已完成/失败任务的记录（jobs/ 工作目录文件保留，可手动清理）。"""
    job = get_job(job_id)
    if not job:
        return "job not found"
    if job["status"] not in ("done", "error"):
        return f"任务仍在 {job['status']}，仅完成/失败任务可删除"
    with db() as conn:
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return None


# ---------------------------------------------------------------- worker
class Worker(threading.Thread):
    """单 worker 串行跑队列（colabfold 本身就吃满一张卡，无需并行）。"""
    daemon = True

    def run(self):
        while True:
            with db() as conn:
                row = conn.execute(
                    "SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
            if not row:
                time.sleep(3)
                continue
            try:
                if row["kind"] == "predict":
                    run_collect_predict(row["id"], json.loads(row["params"]))
                elif row["kind"] == "ingest_zip":
                    run_ingest_zip(row["id"], json.loads(row["params"]))
                else:
                    update_job(row["id"], status="error", message=f"unknown kind {row['kind']}")
            except Exception as e:  # 队列worker永不因单任务异常退出
                update_job(row["id"], status="error",
                           message=f"{type(e).__name__}: {e}", finished=now())
