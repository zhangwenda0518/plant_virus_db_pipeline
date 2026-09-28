#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pvcore — 管线自查公共库（只读为主，绝不修改既有数据）

设计原则
---------
1. 只读：本库的函数除非显式调用 quarantine()/Ledger.write()，否则不写任何文件；
2. 缺失即显式：文件不存在时计数函数返回 None，绝不返回 0（避免"静默 0"事故）；
3. 不破坏：隔离(quarantine)是"复制到新目录"，不做删除；
4. 无第三方依赖除 polars（管线本就用它）。

主要导出
--------
- md5 / count_rows / count_fasta / find_existing
- Ledger                     过滤账本
- quarantine                 隔离（复制，不删）
- guard_vmr_says_plant       VMR 权威护栏：说 plants 的物种不得当非植物删
- guard_refseq_complete      RefSeq+complete+长度正常 → 不得降级/删除
- guard_length_outlier       长度离群（如 13kb 的 badnavirus）→ 标记复核
- write_manifest / read_manifest / check_freshness
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

import polars as pl

# ---------------------------------------------------------------- 基础工具

NULLISH = {"", "na", "n/a", "-", "unknown", "none", "nan", "null"}


def md5(path: str, chunk: int = 1 << 20) -> str | None:
    """文件 md5；不存在返回 None（不抛异常，便于在报告里显示"缺失"）"""
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.md5()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def find_existing(candidates, required: bool = False) -> str | None:
    """在候选名中找第一个存在的文件。

    用途：数据文件改过名（plant.virus.fasta → Plant_Virus_Full.fasta 等），
    调用方给出"新名优先、旧名兜底"的候选列表，避免改名后脚本找不到文件。
    """
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    if required:
        raise FileNotFoundError("候选文件均不存在: " + " | ".join(str(c) for c in candidates))
    return None


def count_rows(path: str) -> int | None:
    """TSV 数据行数（不含表头）；文件不存在返回 None —— 绝不返回 0。

    必须返回 None 的原因：历史上 summarize_pipeline.py 对已扁平化的旧路径
    统计出 0，报告里 4 个指标静默变成 0 而无人察觉。
    """
    if not path or not os.path.isfile(path):
        return None
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return max(n - 1, 0)


def count_fasta(path: str) -> int | None:
    """FASTA 序列数；文件不存在返回 None"""
    if not path or not os.path.isfile(path):
        return None
    n = 0
    with open(path, "rb") as f:
        for line in f:
            if line.startswith(b">"):
                n += 1
    return n


def count_distinct(path: str, column: str, sep: str = "\t") -> int | None:
    """某列去重计数（流式逐行读，内存友好）；文件不存在返回 None"""
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        header = f.readline().rstrip("\n").split(sep)
        if column not in header:
            raise KeyError(f"{column} 不在 {os.path.basename(path)} 的表头: {header[:8]}...")
        i = header.index(column)
        seen = set()
        for line in f:
            parts = line.rstrip("\n").split(sep)
            if len(parts) > i:
                seen.add(parts[i])
    return len(seen)


def read_tsv(path: str, columns=None, truncate: bool = True) -> pl.DataFrame:
    """读 TSV 为全 Utf8（避免类型推断把 ID 变成数字/丢前导零）"""
    df = pl.read_csv(path, separator="\t", infer_schema_length=0,
                     truncate_ragged_lines=truncate, quote_char=None)
    if columns:
        keep = [c for c in columns if c in df.columns]
        df = df.select(keep)
    return df


def norm_null_expr(col: str) -> pl.Expr:
    """空值归一：'' / NA / '-' / unknown 等统一成 null"""
    c = pl.col(col).cast(pl.Utf8)
    return pl.when(c.is_null() | c.str.to_lowercase().str.strip_chars().is_in(list(NULLISH))) \
             .then(None).otherwise(c)


def stringify_lists(df: pl.DataFrame, sep: str = ";") -> pl.DataFrame:
    """把 List 列压成字符串后再写 TSV。

    原因：polars 的 write_csv 不支持嵌套列（如 group_by().agg(unique()) 产出的
    List 列），直接写会抛 "CSV format does not support nested data"。
    """
    if df is None or df.height == 0:
        return df
    exprs = []
    for c in df.columns:
        try:
            if isinstance(df.schema[c], pl.List):
                exprs.append(pl.col(c).map_elements(
                    lambda v, _s=sep: _s.join(str(x) for x in v) if v is not None else "",
                    return_dtype=pl.Utf8).alias(c))
        except Exception:
            continue
    return df.with_columns(exprs) if exprs else df


def write_tsv_safe(df: pl.DataFrame, path: str, sep: str = "\t") -> str:
    """写 TSV（自动压平 List 列），供所有报告类产物使用"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    (stringify_lists(df, ";" if sep == "\t" else ",")).write_csv(path, separator=sep)
    return path


def git_sha(repo_dir: str | None = None) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=repo_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------- 过滤账本

class Ledger:
    """过滤账本：每条删除/降级规则都留下"规则名 + 原因 + 条数 + 样本"。

    用法::

        led = Ledger(outdir)
        led.add("L1_kingdom", "宿主界与目标类别不符", removed_df)
        ...
        led.write()          # 写 filter_ledger.tsv + samples/<rule>.tsv(前 N 条)
    """

    def __init__(self, outdir: str, sample_n: int = 20):
        self.outdir = outdir
        self.sample_n = sample_n
        self.rows = []
        os.makedirs(os.path.join(outdir, "samples"), exist_ok=True)

    def add(self, rule: str, reason: str, removed: pl.DataFrame, key_col: str | None = None):
        n = 0 if removed is None else removed.height
        self.rows.append({"rule": rule, "reason": reason, "n_removed": n})
        if n:
            safe = re.sub(r"[^\w.\-]+", "_", rule)
            removed.head(self.sample_n).write_csv(
                os.path.join(self.outdir, "samples", f"{safe}.tsv"), separator="\t")
        return n

    def write(self) -> str:
        path = os.path.join(self.outdir, "filter_ledger.tsv")
        if self.rows:
            pl.DataFrame(self.rows).write_csv(path, separator="\t")
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write("rule\treason\tn_removed\n")
        return path

    def total(self) -> int:
        return sum(r["n_removed"] for r in self.rows)


def quarantine(df: pl.DataFrame, outdir: str, tag: str, note: str = "") -> str:
    """把"本会被删除、但被护栏救回"的记录复制到隔离目录（复制，不删原文件）"""
    qdir = os.path.join(outdir, "quarantine")
    os.makedirs(qdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    path = os.path.join(qdir, f"{stamp}_{re.sub(r'[^\\w.\\-]+', '_', tag)}.tsv")
    df.write_csv(path, separator="\t")
    with open(os.path.join(qdir, "README.md"), "a", encoding="utf-8") as f:
        f.write(f"- `{os.path.basename(path)}` — {note}（{df.height} 条，{datetime.now():%Y-%m-%d %H:%M}）\n")
    return path


# ---------------------------------------------------------------- 护栏

def load_genus_lengths(path: str) -> dict:
    """读属级长度分布（列: genus / median / p25 / p75 或 min / max，容错多种表头）"""
    if not path or not os.path.isfile(path):
        return {}
    out = {}
    df = read_tsv(path)
    cols = {c.lower(): c for c in df.columns}
    gcol = cols.get("genus") or df.columns[0]
    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None
    med = pick("median", "len_median", "median_len")
    p25, p75 = pick("p25", "q1"), pick("p75", "q3")
    for r in df.iter_rows(named=True):
        g = (r.get(gcol) or "").strip()
        if not g:
            continue
        try:
            out[g] = {
                "median": float(r[med]) if med and r.get(med) not in (None, "") else None,
                "p25": float(r[p25]) if p25 and r.get(p25) not in (None, "") else None,
                "p75": float(r[p75]) if p75 and r.get(p75) not in (None, "") else None,
            }
        except (TypeError, ValueError):
            continue
    return out


def load_plant_families(vmr_path: str) -> set:
    """从 VMR 表里取 Host source 含 plants 的科名单（用于"植物权威"护栏）"""
    if not vmr_path or not os.path.isfile(vmr_path):
        return set()
    try:
        if vmr_path.lower().endswith((".xlsx", ".xls")):
            import pandas as pd  # 可选依赖：只在读 xlsx 时需要
            df = pd.read_excel(vmr_path, sheet_name="VMR MSL41", dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
        else:
            df = read_tsv(vmr_path).to_pandas()
    except Exception:
        return set()
    fam_col = next((c for c in df.columns if str(c).strip().lower() == "family"), None)
    host_col = next((c for c in df.columns if "host source" in str(c).strip().lower()), None)
    if not fam_col or not host_col:
        return set()
    m = df[df[host_col].fillna("").str.contains(r"(?i)\bplants?\b", regex=True)]
    return {str(x).strip() for x in m[fam_col].dropna() if str(x).strip()}


def _length_range_ok(genus_lens: dict, genus: str, length: float, k: float = 3.0):
    """属内长度合理性：中位数 ± k 倍四分位距（缺分布信息时视为"无法判断"，返回 True 放过）"""
    st = genus_lens.get(genus)
    if not st or st.get("median") is None or st.get("p25") is None or st.get("p75") is None:
        return True
    iqr = max(st["p75"] - st["p25"], 1.0)
    return (st["median"] - k * iqr) <= length <= (st["median"] + k * iqr)


def guard_vmr_says_plant(removed: pl.DataFrame, plant_families: set) -> pl.DataFrame:
    """护栏①：VMR 权威说"植物"的物种，不允许被当非植物删掉。

    触发背景：Badnavirus zetainflatheobromae（cacao swollen shoot Togo A virus）
    在 VMR 里 Host source = plants，却被"剔除非植物"那一步整族删除。
    """
    if removed is None or removed.height == 0:
        return removed
    conds = []
    for col, pat in (("Host source", r"(?i)\bplants?\b"),
                     ("VMR_Raw_Host", r"(?i)\bplants?\b")):
        if col in removed.columns:
            conds.append(pl.col(col).cast(pl.Utf8).str.contains(pat))
    if "VMR_Family" in removed.columns and plant_families:
        conds.append(pl.col("VMR_Family").cast(pl.Utf8).is_in(sorted(plant_families)))
    if not conds:
        return removed.head(0)
    keep = conds[0]
    for c in conds[1:]:
        keep = keep | c
    return removed.filter(keep)


def guard_refseq_complete(removed: pl.DataFrame, genus_lens: dict, k: float = 3.0) -> pl.DataFrame:
    """护栏②：RefSeq(NC_) + Nuc_Completeness=complete + 长度在属内合理区间
    → 不许被降级/删除（F2 的"标题含 gene 即判 CDS_Fragment"曾误伤 270 条完整基因组）。
    """
    if removed is None or removed.height == 0:
        return removed
    if "Accession" not in removed.columns:
        return removed.head(0)
    sub = removed.filter(pl.col("Accession").cast(pl.Utf8).str.starts_with("NC_"))
    if "Nuc_Completeness" in sub.columns:
        sub = sub.filter(pl.col("Nuc_Completeness").cast(pl.Utf8).str.to_lowercase() == "complete")
    if sub.height == 0:
        return sub
    if not genus_lens or "VMR_Genus" not in sub.columns or "Length" not in sub.columns:
        return sub  # 无长度参考时仍拦下（宁可复核，不可静默降级）
    kept = []
    for r in sub.iter_rows(named=True):
        try:
            ln = float(r.get("Length") or 0)
        except (TypeError, ValueError):
            ln = 0
        if ln <= 0 or _length_range_ok(genus_lens, (r.get("VMR_Genus") or "").strip(), ln, k):
            kept.append(r)
    return pl.DataFrame(kept, schema=sub.schema) if kept else sub.head(0)


def guard_length_outlier(df: pl.DataFrame, genus_lens: dict, k: float = 3.0) -> pl.DataFrame:
    """护栏③：长度离群记录（如 13,221 bp 的 badnavirus）→ 标记复核，不静默采用为代表"""
    if df is None or df.height == 0 or not genus_lens:
        return df.head(0) if df is not None else df
    if "VMR_Genus" not in df.columns or "Length" not in df.columns:
        return df.head(0)
    hits = []
    for r in df.iter_rows(named=True):
        try:
            ln = float(r.get("Length") or 0)
        except (TypeError, ValueError):
            continue
        if ln > 0 and not _length_range_ok(genus_lens, (r.get("VMR_Genus") or "").strip(), ln, k):
            hits.append(r)
    return pl.DataFrame(hits, schema=df.schema) if hits else df.head(0)


# ---------------------------------------------------------------- 产物清单

def write_manifest(outdir: str, outputs, inputs=None, params=None, script: str = "", extra=None) -> str:
    """为产物目录写 _manifest.json：脚本 + git SHA + 参数 + 输入 md5/行数 + 产物行数/序列数。

    这样"表是旧的""数字对不上"可以在生成时立刻发现，而不是定稿前人工比对。
    """
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "script": script or (sys.argv[0] if sys.argv else ""),
        "git": git_sha(),
        "params": params or {},
        "inputs": {str(p): {"md5": md5(str(p)), "rows": count_rows(str(p))} for p in (inputs or [])},
        "outputs": {str(p): {"rows": count_rows(str(p)), "seqs": count_fasta(str(p))} for p in (outputs or [])},
    }
    if extra:
        payload.update(extra)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "_manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def read_manifest(outdir: str) -> dict | None:
    path = os.path.join(outdir, "_manifest.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_freshness(outdir: str) -> list[str]:
    """校验目录里 _manifest.json 记录的输入是否仍然与磁盘一致。

    返回问题列表（空列表表示新鲜）。不抛异常、不改文件。
    """
    problems = []
    man = read_manifest(outdir)
    if man is None:
        return [f"{outdir}: 缺少 _manifest.json（产物无出处，无法判断新鲜度）"]
    for p, meta in (man.get("inputs") or {}).items():
        cur = md5(p)
        if cur is None:
            problems.append(f"输入缺失: {p}")
        elif meta.get("md5") and cur != meta["md5"]:
            problems.append(f"输入已变更: {p}（清单 {meta['md5'][:8]} ≠ 现值 {cur[:8]}）")
    return problems
