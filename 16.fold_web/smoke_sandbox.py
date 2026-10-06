# -*- coding: utf-8 -*-
"""fold_web 沙箱端到端冒烟（不污染真实数据）：
临时模块副本 + stub 预测器，走 FASTA 上传 -> 队列 -> 预测 -> 入库 -> pending 联动，
并验证 /api/export/foldify 的 ZIP 结构。真实 structures_index.tsv 只读不改。
"""
import csv, io, os, sys, time, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REAL_MODULE = ROOT.parent / "15.uniprot_plant_virus_structures"
REAL_INDEX = REAL_MODULE / "structures_index.tsv"
STUB = ROOT / "test_stub_predictor.py"

sandbox = Path(tempfile.mkdtemp(prefix="foldweb_smoke_"))
mod = sandbox / "module"
(mod / "colabfold_input").mkdir(parents=True)

# 挑 2 条无自身结构且 <=600aa 的真实 accession 作为沙箱输入
cands = []
with open(REAL_INDEX, encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f, delimiter="\t"))
own = ("PDB", "AFDB", "RVPSD", "SELF")
for r in rows:
    if not any(s in r["sources"].split(",") for s in own) and r["length"].isdigit() and 0 < int(r["length"]) <= 600:
        cands.append(r["accession"])
    if len(cands) == 2:
        break
assert len(cands) == 2, "index 里找不到可用的待预测样本"
acc_a, acc_b = cands
(mod / "structures_index.tsv").write_text(REAL_INDEX.read_text(encoding="utf-8"), encoding="utf-8")

fasta = sandbox / "input.fasta"
fasta.write_text(f">{acc_a} test seq A\nMKVLWA\n>{acc_b} test seq B\nMSTGQE\n", encoding="utf-8")

os.environ["FOLDWEB_MODULE_DIR"] = str(mod)
os.environ["FOLDWEB_DB"] = str(mod / "colabfold_input" / "fold_jobs.db")
os.environ["FOLDWEB_JOBS_DIR"] = str(mod / "colabfold_input" / "jobs")
os.environ["FOLDWEB_PREDICT_CMD"] = f'"{sys.executable}" "{STUB}" {{input}} {{output}}'

sys.path.insert(0, str(ROOT))
import app as flask_app  # noqa: E402
import foldcore as fc  # noqa: E402

c = flask_app.app.test_client()
ok, fail = [], []
def check(name, cond, detail=""):
    (ok if cond else fail).append(f"{name}{': ' + detail if detail else ''}")

# 1) 首页
r = c.get("/")
check("GET / == 200", r.status_code == 200, str(r.status_code))

# 2) stats 与真实索引账目一致（副本未动时）
r = c.get("/api/stats")
st = r.get_json()
check("GET /api/stats == 200", r.status_code == 200)
check("stats.proteins == 真实索引行数", st["proteins"] == len(rows), f'{st["proteins"]} vs {len(rows)}')

# 3) 上传 FASTA -> 全链路
rv = c.post("/api/job/upload_fasta", data={"file": (open(fasta, "rb"), "input.fasta")},
            content_type="multipart/form-data")
jid = rv.get_json().get("job_id")
check("upload_fasta 建任务", rv.status_code == 200 and jid is not None, rv.get_data(as_text=True)[:200])

deadline = time.time() + 120
job = None
while time.time() < deadline:
    job = next((j for j in c.get("/api/jobs").get_json() if j["id"] == jid), None)
    if job and job["status"] in ("done", "error"):
        break
    time.sleep(2)
check("任务终态 done", job is not None and job["status"] == "done",
      f"status={job and job['status']} msg={job and job['message']}")

# 入库校验：沙箱 SELF 目录有模型 + 索引副本 sources 含 SELF
self_pdbs = list((mod / "structures_selffold").rglob("*.pdb"))
check("selffold 模型落盘 2 个", len(self_pdbs) == 2, f"got {len(self_pdbs)}")
with open(mod / "structures_index.tsv", encoding="utf-8", newline="") as f:
    now_rows = {r["accession"]: r for r in csv.DictReader(f, delimiter="\t")}
flipped = [a for a in (acc_a, acc_b) if "SELF" in now_rows[a]["sources"].split(",")]
check("索引 sources += SELF", len(flipped) == 2, f"flipped={flipped}")

# 4) pending 联动：这两条应从待预测清单消失
pend = c.get("/pending_accessions.txt").get_data(as_text=True).split()
check("pending 联动（2 条移出）", acc_a not in pend and acc_b not in pend)

# 5) Foldify 导出 ZIP 结构（真实网络拉 UniProt，最多 3 条）
r = c.get("/api/export/foldify?max=3")
check("GET /api/export/foldify == 200", r.status_code == 200, str(r.status_code))
if r.status_code == 200:
    z = zipfile.ZipFile(io.BytesIO(r.data))
    names = z.namelist()
    blocks = [n for n in names if n.startswith("foldify_block") and n.endswith(".fasta")]
    check("ZIP 含 manifest+README", "foldify_manifest.tsv" in names and "README.txt" in names, str(names))
    maxlen = 0
    for b in blocks:
        for line in z.read(b).decode("utf-8").splitlines():
            if not line.startswith(">"):
                maxlen = max(maxlen, len(line.strip()))
    # 行宽 60，序列按 60 切块，任一序列 >600 会出现满 60 行且超限——用总长校验更稳
    total = {}
    cur = None
    for b in blocks:
        for line in z.read(b).decode("utf-8").splitlines():
            if line.startswith(">"):
                cur = line[1:].split()[0]
                total[cur] = 0
            elif cur:
                total[cur] += len(line.strip())
    check("导出序列全部 <=600aa", all(0 < v <= 600 for v in total.values()), str(total))

print("\n".join("PASS " + s for s in ok))
print("\n".join("FAIL " + s for s in fail))
print(f"\n{len(ok)} passed, {len(fail)} failed; sandbox={sandbox}")
sys.exit(1 if fail else 0)
