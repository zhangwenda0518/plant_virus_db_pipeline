"""
统一项目配置文件 — 所有模块从此处读取数据路径
=============================================
覆盖: 病毒DB流水线 / 引物设计 / 可视化探索器

用法:
    from config import DATA_DIR, PIPELINE_OUTPUTS
    df = pd.read_csv(PIPELINE_OUTPUTS['full_tsv'], sep='\t')

所有路径均可通过环境变量覆盖，格式: PVDB_<KEY>=<path>
例如: PVDB_FULL_TSV=/data/custom/full.tsv
"""
import os

# ── 项目根目录 ──────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ── 数据目录 (从环境变量或默认值读取) ─────────────────────
def _env_or(key: str, default: str) -> str:
    return os.environ.get(f"PVDB_{key}", default)

DATA_DIR = _env_or("DATA_DIR", os.path.join(PROJECT_ROOT, "docs", "data"))

# ── 流水线产出文件 ──────────────────────────────────────
PIPELINE_OUTPUTS = {
    # 最终聚类参考序列 (非冗余代表集, ~8,465 条)
    "cluster_fasta":   _env_or("CLUSTER_FASTA",   os.path.join(DATA_DIR, "final.cluster.ref.fasta")),
    # 最终聚类参考元数据
    "cluster_info":    _env_or("CLUSTER_INFO",    os.path.join(DATA_DIR, "final.cluster.ref_info.tsv")),
    # 全量植物病毒元数据 (~199k 条)
    "full_tsv":        _env_or("FULL_TSV",        os.path.join(DATA_DIR, "Plant_Virus_Info.full.tsv")),
    # 全量植物病毒序列 (~199k 条, 377MB)
    "full_fasta":      _env_or("FULL_FASTA",      os.path.join(DATA_DIR, "plant.virus.fasta")),
    # 最终完整参考序列 (较新的完整聚类)
    "complete_fasta":  _env_or("COMPLETE_FASTA",  os.path.join(DATA_DIR, "final.complete_ref.fasta")),
    # 最终完整参考元数据
    "complete_info":   _env_or("COMPLETE_INFO",   os.path.join(DATA_DIR, "final.complete_ref_info.tsv")),
    # 基因覆盖度表
    "gene_cov":        _env_or("GENE_COV",        os.path.join(DATA_DIR, "virus_genes_cov.tsv")),
    # 完整 accession 列表
    "complete_acc":    _env_or("COMPLETE_ACC",    os.path.join(DATA_DIR, "complete_acc.txt")),
}

# ── 引物设计产出 ────────────────────────────────────────
PRIMER_DIR = _env_or("PRIMER_DIR", os.path.join(DATA_DIR, "primers"))
PRIMER_OUTPUTS = {
    "reference_tsv": os.path.join(PRIMER_DIR, "primer_reference.tsv"),
    "per_species":   os.path.join(PRIMER_DIR, "per_species"),
}

# ── 宿主分类产出 ────────────────────────────────────────
HOST_DIR = _env_or("HOST_DIR", os.path.join(DATA_DIR, "host_analysis"))
HOST_OUTPUTS = {
    "species_prob": os.path.join(HOST_DIR, "species_host_probability.tsv"),
    "genus_prob":   os.path.join(HOST_DIR, "genus_host_probability.tsv"),
    "family_prob":  os.path.join(HOST_DIR, "family_host_probability.tsv"),
}

# ── 数据版本 ──────────────────────────────────────────
VERSION_FILE = os.path.join(DATA_DIR, "DATA_VERSION")

def load_version() -> dict[str, str]:
    """读取 DATA_VERSION 文件，返回 dict"""
    version = {}
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    version[k.strip()] = v.strip()
    return version

def get_version_string() -> str:
    """返回人类可读的版本字符串"""
    v = load_version()
    if not v:
        return "Unknown"
    return f"{v.get('VERSION', '?')} | {v.get('SOURCE_ICTV', '?')} | {v.get('RECORDS_TOTAL', '?')} records"


# ── 辅助: 验证关键文件存在 ──────────────────────────────
def check_required(keys: list[str] = None) -> dict[str, bool]:
    """检查指定文件是否存在。默认检查 explorer 所需文件。"""
    if keys is None:
        keys = ["full_tsv", "full_fasta"]
    result = {}
    for k in keys:
        path = PIPELINE_OUTPUTS.get(k, "")
        result[k] = os.path.exists(path) if path else False
    return result

if __name__ == "__main__":
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"DATA_DIR:     {DATA_DIR}")
    print()
    for k, v in PIPELINE_OUTPUTS.items():
        ok = "✓" if os.path.exists(v) else "✗"
        print(f"  {ok} {k}: {v}")
    print()
    for k, v in PRIMER_OUTPUTS.items():
        ok = "✓" if os.path.exists(v) else "✗"
        print(f"  {ok} primer.{k}: {v}")
