#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit.py — 管线产物只读体检（把"定稿前的人工核对"变成一条命令）

用法
----
    # 1) 直接指定 Info 表（本地也能跑，不碰任何数据）
    python lib/audit.py --info docs/data/Plant_Virus_Ref.Info.tsv --out /tmp/audit_x

    # 2) 对整条管线的产物目录做体检（在 run_all.sh 结尾自动调用）
    python lib/audit.py --work-dir ~/plant_virus_db --out ~/plant_virus_db/7.audit

    # 3) 与上一版快照自动对比（推荐：自动找同目录最新的 .bak* 作为基线）
    python lib/audit.py --info <tsv> --baseline auto --out ...

产出（全部写在 --out 目录，绝不改动既有数据）
--------------------------------------------
    audit_summary.md          总览：每条检查的 PASS/WARN/FAIL + 计数
    checks.tsv                机器可读（check / level / value / detail / samples）
    species_key_split.tsv     同一规范种名被拆成多个键（TSWV 类）
    species_segment_counts.tsv 各物种节段数量（供人/CI 比对）
    missing_segments.tsv      与参考段数比对后缺口
    baseline_diff.tsv         与基线相比新增/丢失的记录（按 Accession）
    lost_species.tsv          基线里有、现在完全没有记录的 TaxID（重点！）

退出码：默认 0（warn-only，不打断管线）；加 --strict 时有 FAIL 则返回 1。
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import polars as pl                                    # noqa: E402
from pvcore import (count_rows, count_fasta, find_existing, read_tsv,   # noqa: E402
                    git_sha, load_plant_families, load_genus_lengths, check_freshness,
                    write_tsv_safe)

# ---- 阈值（写成常量，改动需在 review 里说明；基线来自 2026-09-28 实测） ----
MIN_VMR_SPECIES_FILL = 0.08     # VMR_Species 非空率，实测 11%
MIN_VMR_FAMILY_FILL = 0.50      # VMR_Family/VMR_Genus 非空率，实测 58%
MAX_DUP_ACCESSION = 0          # 允许的重复 Accession 条数

# 常见节段病毒属的参考段数（用于"缺段"提示；可用 --segment-ref 用自家表覆盖）
BUILTIN_SEG_EXPECT = {
    "Orthotospovirus": 3, "Tospovirus": 3, "Ilarvirus": 3, "Cucumovirus": 3,
    "Bromovirus": 3, "Alfamovirus": 3, "Crinivirus": 3, "Amporavirus": 2,
    "Fijivirus": 10, "Phytoreovirus": 12, "Oryzavirus": 10, "Tenuivirus": 8,
    "Nepovirus": 2, "Sadwavirus": 2, "Fabavirus": 2, "Comovirus": 2,
    "Begomovirus": 2, "Babuvirus": 6, "Nanovirus": 6, "Tospovirus_": 3,
    "Emaravirus": 4, "Orthotospovirus_": 3,
}
SEG_TITLE_RE = re.compile(
    r"(?i)\b(?:segment|rna|dna)[\s\-_]*"   # 关键词：segment / RNA / DNA
    r"(?:[0-9]{1,2}[a-z]?\b"                # 3 / 10 / 5a
    r"|[a-z][0-9]{1,2}\b"                   # S1 / M2（"segment S1" 这类）
    r"|-[a-z]\b"                            # DNA-A / RNA-B
    r"|[a-z]\b)")                           # DNA A / segment S


class Report:
    def __init__(self, outdir: str):
        self.outdir = outdir
        os.makedirs(outdir, exist_ok=True)
        self.rows = []
        self.artifacts = {}

    def add(self, check: str, level: str, value, detail: str = "", samples=()):
        """level: PASS / WARN / FAIL / INFO"""
        self.rows.append({
            "check": check, "level": level, "value": value, "detail": detail,
            "samples": "; ".join(str(s) for s in list(samples)[:5]),
        })
        tag = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗", "INFO": "·"}.get(level, "·")
        print(f"  [{tag} {level:<4}] {check:<38} {value}  {detail}")

    def artifact(self, name: str, df: pl.DataFrame, note: str = ""):
        path = os.path.join(self.outdir, name)
        write_tsv_safe(df, path)                    # 自动压平 List 列，避免写 CSV 报错
        self.artifacts[name] = (df.height, note)
        return path

    def flush(self, title: str = "管线产物体检报告"):
        pl.DataFrame(self.rows).write_csv(os.path.join(self.outdir, "checks.tsv"), separator="\t")
        n = {"PASS": 0, "WARN": 0, "FAIL": 0, "INFO": 0}
        for r in self.rows:
            n[r["level"]] = n.get(r["level"], 0) + 1
        lines = [f"# {title}", "",
                 f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
                 f"- 代码版本：{git_sha()}",
                 f"- 汇总：**FAIL {n['FAIL']} / WARN {n['WARN']} / PASS {n['PASS']}**", "",
                 "| 检查 | 级别 | 数值 | 说明 |", "|---|---|---|---|"]
        for r in self.rows:
            lines.append(f"| {r['check']} | {r['level']} | {r['value']} | {r['detail']} |")
        if self.artifacts:
            lines += ["", "## 明细文件", ""]
            for k, (h, note) in self.artifacts.items():
                lines.append(f"- `{k}`（{h} 行）{(' — ' + note) if note else ''}")
        with open(os.path.join(self.outdir, "audit_summary.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return n


# ------------------------------------------------------------------ 各项检查

def check_contracts(rep: Report, info: str, vmr: str | None, plant_families: set):
    """Info 表结构 + 覆盖率 + 物种键分裂 + 污染物"""
    if not info or not os.path.isfile(info):
        rep.add("info.exists", "FAIL", info or "(未指定)", "Info 表不存在")
        return None
    df = read_tsv(info)
    rep.add("info.rows", "PASS" if df.height else "FAIL", df.height)
    if df.height == 0:
        return df

    need = ["Accession", "Taxid", "Species_ICTV", "Segment", "Segment_std",
            "Nuc_Completeness", "GenBank_Title"]
    missing = [c for c in need if c not in df.columns]
    rep.add("info.columns", "FAIL" if missing else "PASS",
            len(df.columns), f"缺少必需列: {missing}" if missing else "")

    if "Accession" in df.columns:
        dup = df.group_by("Accession").len().filter(pl.col("len") > 1)
        rep.add("info.duplicate_accession",
                "FAIL" if dup.height > MAX_DUP_ACCESSION else "PASS",
                dup.height, "", dup["Accession"].to_list()[:5])

    for col, thr, name in (("VMR_Species", MIN_VMR_SPECIES_FILL, "vmr_species_fill"),
                           ("VMR_Family", MIN_VMR_FAMILY_FILL, "vmr_family_fill")):
        if col in df.columns:
            filled = int((df[col].cast(pl.Utf8).fill_null("").str.strip_chars() != "").sum())
            rate = filled / max(df.height, 1)
            rep.add(f"info.{name}", "PASS" if rate >= thr else "WARN",
                    f"{rate:.1%}", f"阈值 {thr:.0%}（非空 {filled}/{df.height}）")

    if "Nuc_Completeness" in df.columns:
        empty = int((df["Nuc_Completeness"].cast(pl.Utf8).fill_null("").str.strip_chars() == "").sum())
        rep.add("info.nuc_completeness_empty", "PASS" if empty == 0 else "WARN", empty)

    # 物种键分裂：同一"权威种名"落在多个 TaxID / 多个 Species_ICTV 上
    keycol = "VMR_Species" if "VMR_Species" in df.columns else None
    if keycol and "Species_ICTV" in df.columns:
        sub = df.with_columns([
            pl.col(keycol).cast(pl.Utf8).fill_null("").str.strip_chars().alias("_k"),
            pl.col("Species_ICTV").cast(pl.Utf8).fill_null("").str.strip_chars().alias("_ictv"),
            pl.col("Taxid").cast(pl.Utf8).alias("_tx"),
        ]).filter(pl.col("_k") != "")
        g = (sub.group_by("_k")
                .agg([pl.col("_tx").n_unique().alias("n_taxid"),
                      pl.col("_ictv").n_unique().alias("n_ictv"),
                      pl.col("_ictv").unique().alias("ictv_keys"),
                      pl.col("_tx").unique().alias("taxids"),
                      pl.len().alias("n_rows")])
                .filter((pl.col("n_taxid") > 1) | (pl.col("n_ictv") > 1))
                .sort("n_rows", descending=True))
        rep.artifact("species_key_split.tsv", g,
                     "同一 VMR 规范种名对应多个 TaxID 或多个 Species_ICTV 写法")
        rep.add("info.species_key_split", "PASS" if g.height == 0 else "WARN", g.height,
                "同种被拆成多个键（TSWV 类）；见表 species_key_split.tsv",
                g["_k"].to_list()[:5] if g.height else [])

    # 污染物哨兵：已知污染 accession 不应出现在任何产物里
    contaminants = {"HM107843.1"}
    if "Accession" in df.columns:
        hit = df.filter(pl.col("Accession").is_in(sorted(contaminants)))
        rep.add("info.contaminant_present", "PASS" if hit.height == 0 else "WARN",
                hit.height, "应为 0（C4 的 L0 规则负责剔除）", hit["Accession"].to_list()[:3])

    # 标题声明了节段但节段列为空（NC_003749.1 那类）
    if {"GenBank_Title", "Segment", "Segment_std"} <= set(df.columns):
        bad = df.with_columns([
            pl.col("GenBank_Title").cast(pl.Utf8).fill_null("").alias("_t"),
            pl.col("Segment").cast(pl.Utf8).fill_null("").str.strip_chars().alias("_s"),
            pl.col("Segment_std").cast(pl.Utf8).fill_null("").str.strip_chars().alias("_ss"),
        ]).filter((pl.col("_s") == "") & (pl.col("_ss") == "")
                  & pl.col("_t").str.contains(SEG_TITLE_RE.pattern))
        rep.artifact("empty_segment_with_title.tsv",
                     bad.select([c for c in ("Accession", "Taxid", "Species_ICTV",
                                             "GenBank_Title") if c in bad.columns]),
                     "标题里明确写了节段号，但 Segment/Segment_std 为空")
        rep.add("info.empty_segment_label", "PASS" if bad.height == 0 else "WARN", bad.height,
                "见表 empty_segment_with_title.tsv", bad["Accession"].to_list()[:5] if bad.height else [])

    if vmr and plant_families:
        rep.add("vmr.plant_families_loaded", "INFO", len(plant_families),
                "用于护栏：Host source 含 plants 的科名单")
    return df


def check_segments(rep: Report, df: pl.DataFrame, seg_ref: str | None):
    """节段：物种内风格一致性 + 段数 + 与参考段数比对"""
    if df is None or df.height == 0 or "Segment_std" not in df.columns:
        return
    style = re.compile(r"^(?P<pfx>[A-Za-z]+)?[\-_]?(?P<num>\d+)$")

    def style_of(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        m = style.match(s)
        if m:
            return (m.group("pfx") or "").upper() + "#"
        if re.match(r"^DNA[\-_]?[A-Z]$", s, re.I):
            return "DNA-"
        if len(s) <= 2:
            return "LETTER"
        return "OTHER"

    sub = df.with_columns([
        pl.col("Segment_std").cast(pl.Utf8).fill_null("").str.strip_chars().alias("_ss"),
        pl.col("Species_ICTV").cast(pl.Utf8).fill_null("").alias("_sp"),
        pl.col("Taxid").cast(pl.Utf8).alias("_tx"),
        pl.col("Length").cast(pl.Int64, strict=False).alias("_len"),
    ]).filter(pl.col("_ss") != "")
    sub = sub.with_columns(pl.col("_ss").map_elements(style_of, return_dtype=pl.Utf8).alias("_style"))

    counts = (sub.group_by(["_tx", "_sp"])
                 .agg([pl.col("_ss").n_unique().alias("n_segments"),
                       pl.col("_ss").unique().sort().alias("segments"),
                       pl.col("_style").n_unique().alias("n_styles"),
                       pl.col("_style").unique().alias("styles"),
                       pl.len().alias("n_rows")])
                 .sort("n_segments", descending=True)
                 .rename({"_tx": "Taxid", "_sp": "Species_ICTV"}))
    rep.artifact("species_segment_counts.tsv", counts, "各物种节段清单")
    mixed = counts.filter(pl.col("n_styles") > 1)
    rep.add("segments.style_mixed_within_species", "PASS" if mixed.height == 0 else "WARN",
            mixed.height, "同一物种内节段命名风格不统一（如 RNA10 vs S10）",
            [f"{r['Species_ICTV']}={r['styles']}" for r in mixed.head(3).to_dicts()] if mixed.height else [])

    dup = (sub.group_by(["_tx", "_sp", "_ss"]).len().filter(pl.col("len") > 1))
    rep.add("segments.duplicate_label", "INFO", dup.height,
            "同一物种同一段标签出现多条（可能是多簇代表，属正常，供核对）")

    expected = dict(BUILTIN_SEG_EXPECT)
    if seg_ref and os.path.isfile(seg_ref):
        try:
            r = read_tsv(seg_ref)
            gcol = next((c for c in r.columns if c.lower() == "genus"), None)
            ncol = next((c for c in r.columns if "n_seg_expected" in c.lower()), None)
            if gcol and ncol:
                for row in r.iter_rows(named=True):
                    g = (row.get(gcol) or "").strip()
                    try:
                        expected[g] = int(float(row.get(ncol)))
                    except (TypeError, ValueError):
                        pass
                rep.add("segments.ref_table_loaded", "INFO", len(expected),
                        f"参考段数来自 {os.path.basename(seg_ref)}")
        except Exception as e:  # 参考表坏了也不该影响主流程
            rep.add("segments.ref_table_loaded", "WARN", 0, f"读取失败: {e}")

    rows = []
    if "VMR_Genus" in df.columns:
        genus_of = {r["_tx"]: (r.get("_g") or "").strip() for r in
                    df.with_columns([pl.col("Taxid").cast(pl.Utf8).alias("_tx"),
                                     pl.col("VMR_Genus").cast(pl.Utf8).fill_null("").alias("_g")])
                      .select(["_tx", "_g"]).unique().iter_rows(named=True)}
        for r in counts.iter_rows(named=True):
            exp = expected.get(genus_of.get(r["Taxid"], ""), None)
            if exp and r["n_segments"] < exp:
                rows.append({"Taxid": r["Taxid"], "Species_ICTV": r["Species_ICTV"],
                             "n_segments": r["n_segments"], "n_seg_expected": exp,
                             "missing": exp - r["n_segments"],
                             "segments": ",".join(r["segments"])})
    if rows:
        miss = pl.DataFrame(rows).sort("missing", descending=True)
    else:
        miss = pl.DataFrame(schema={"Taxid": pl.Utf8, "Species_ICTV": pl.Utf8,
                                    "n_segments": pl.Int64, "n_seg_expected": pl.Int64,
                                    "missing": pl.Int64, "segments": pl.Utf8})
    rep.artifact("missing_segments.tsv", miss, "与参考段数比对后的缺口（参考值为属级经验值，需人工确认）")
    rep.add("segments.missing_vs_expected", "PASS" if miss.height == 0 else "WARN", miss.height,
            "见表 missing_segments.tsv", miss["Species_ICTV"].to_list()[:5] if miss.height else [])


def check_baseline(rep: Report, info: str, baseline: str | None):
    """与上一版快照对比：新增/丢失记录 + 整族消失的 TaxID（重点）"""
    if not baseline:
        return
    if baseline == "auto":
        cands = [p for p in glob.glob(info + ".bak*") if os.path.isfile(p)]
        if not cands:
            rep.add("baseline.auto", "INFO", 0, "同目录没有 .bak* 快照可作基线")
            return
        baseline = max(cands, key=os.path.getmtime)
    if not os.path.isfile(baseline):
        rep.add("baseline.exists", "WARN", baseline, "基线文件不存在")
        return
    cur, old = read_tsv(info), read_tsv(baseline)
    rep.add("baseline.used", "INFO", os.path.basename(baseline),
            f"基线 {old.height} 行 → 当前 {cur.height} 行")
    if "Accession" not in cur.columns or "Accession" not in old.columns:
        return
    joined = old.select(["Accession"]).join(cur.select(["Accession"]), on="Accession", how="anti")
    added = cur.select(["Accession"]).join(old.select(["Accession"]), on="Accession", how="anti")
    cols = [c for c in ("Accession", "Taxid", "Species_ICTV", "VMR_Species",
                        "VMR_Family", "GenBank_Title") if c in old.columns]
    diff = pl.concat([
        old.join(joined, on="Accession", how="inner").select(cols).with_columns(pl.lit("REMOVED").alias("change")),
        cur.join(added, on="Accession", how="inner").select(cols).with_columns(pl.lit("ADDED").alias("change")),
    ]) if (joined.height or added.height) else pl.DataFrame(schema={"change": pl.Utf8})
    rep.artifact("baseline_diff.tsv", diff, "相对基线的增删明细")
    rep.add("baseline.accession_delta", "INFO", f"-{joined.height} / +{added.height}",
            "见 baseline_diff.tsv", joined["Accession"].to_list()[:5])

    if "Taxid" in cur.columns and "Taxid" in old.columns:
        lost = (old.select([pl.col("Taxid").cast(pl.Utf8).alias("t")]).unique()
                   .join(cur.select([pl.col("Taxid").cast(pl.Utf8).alias("t")]).unique(),
                         on="t", how="anti"))
        if lost.height:
            detail = (old.with_columns(pl.col("Taxid").cast(pl.Utf8).alias("t"))
                         .filter(pl.col("t").is_in(lost["t"].to_list()))
                         .group_by(["t", "Species_ICTV"]).len()
                         .rename({"t": "Taxid"}).sort("len", descending=True))
            rep.artifact("lost_species.tsv", detail, "基线有、当前完全没有记录的物种 —— 必须逐条确认")
        rep.add("baseline.lost_species", "PASS" if lost.height == 0 else "FAIL", lost.height,
                "整族消失的 TaxID（zetainfla 事故就是这样被漏掉的）",
                lost["t"].to_list()[:5])


def check_artifacts(rep: Report, work_dir: str):
    """对关键产物目录做新鲜度检查（有 _manifest.json 才检查）"""
    if not work_dir:
        return
    for sub in ("1.virus-host_db/C-host_classify/classified_clean",
                "2.plant-virus.db/F-dedup", "2.plant-virus.db/G-cluster",
                "3.final-ref-virus.db"):
        d = os.path.join(work_dir, sub)
        if not os.path.isdir(d):
            continue
        probs = check_freshness(d)
        if probs:
            rep.add(f"freshness.{sub}", "INFO" if "缺少 _manifest.json" in probs[0] else "WARN",
                    len(probs), probs[0], probs[1:4])
    # 关键文件存在性：只有当"该阶段确实跑过"时才 FAIL，避免在只跑了前半段的
    # work dir 上误报（误报多了就没人看报告了）。
    final = find_existing([os.path.join(work_dir, p) for p in
                           ("3.final-ref-virus.db/Plant_Virus_Ref.Info.tsv",
                            "3.final-ref-virus.db/final.cluster.ref_info.tsv")])
    gcluster = os.path.isdir(os.path.join(work_dir, "2.plant-virus.db/G-cluster"))
    checks = [
        ("ref_info", final, None, "最终参考集 Info"),
        ("ref_fasta", find_existing([os.path.join(work_dir, p) for p in
                                     ("3.final-ref-virus.db/Plant_Virus_Ref.fasta",
                                      "3.final-ref-virus.db/final.cluster.ref.fasta")]),
         final, "最终参考集 FASTA（与 Info 必须同时存在）"),
        ("lca_plot", find_existing([os.path.join(work_dir,
                                                 "2.plant-virus.db/G-cluster/clusters.LCA_Distribution.png")]),
         gcluster, "G2 的 LCA 分布图"),
    ]
    for name, hit, precondition, why in checks:
        if hit:
            rep.add(f"artifact.{name}", "PASS", os.path.basename(hit))
        elif precondition:
            rep.add(f"artifact.{name}", "FAIL", "缺失", f"{why}：该阶段跑过但文件不在")
        else:
            rep.add(f"artifact.{name}", "INFO", "不适用", f"{why}：对应阶段尚未运行，跳过")


def pick_auto_baseline(root: str, info: str, name: str = "ref_info_snapshot.tsv") -> str | None:
    """在 root/*/name 里挑比当前 Info 更旧的最新一份快照作基线。

    这样每次跑管线都自动与"上一次运行"对比，不需要人工留 .bak；
    整族消失的物种（如 Badnavirus zetainflatheobromae）会在下一次运行时自动报 FAIL。
    """
    if not root or not info or not os.path.isfile(info):
        return None
    cur_m = os.path.getmtime(info)
    cands = [p for p in glob.glob(os.path.join(root, "*", name)) if os.path.isfile(p)]
    older = [(os.path.getmtime(p), p) for p in cands if os.path.getmtime(p) < cur_m]
    if not older:
        return None
    return max(older)[1]


def take_snapshot(info: str, outdir: str, name: str = "ref_info_snapshot.tsv") -> str | None:
    """把当前 Info 复制一份到本次审计目录，供下一次运行作基线（只新增文件，不改动原文件）"""
    if not info or not os.path.isfile(info):
        return None
    dst = os.path.join(outdir, name)
    shutil.copy2(info, dst)
    return dst


# ------------------------------------------------------------------ 入口

def main():
    ap = argparse.ArgumentParser(description="管线产物只读体检")
    ap.add_argument("--info", help="参考集 Info TSV（如 3.final-ref-virus.db/Plant_Virus_Ref.Info.tsv）")
    ap.add_argument("--work-dir", help="管线工作目录；给出则自动定位 Info 与产物")
    ap.add_argument("--vmr", help="VMR 表（xlsx 或 tsv），用于生成植物科权威名单（护栏用）")
    ap.add_argument("--segment-ref", help="段数参考表（含 genus / n_seg_expected 列）")
    ap.add_argument("--genus-lens", help="属级长度分布表（genus/median/p25/p75），供护栏核对")
    ap.add_argument("--baseline", help="基线 Info TSV，或 auto（自动找最新的 .bak*）")
    ap.add_argument("--auto-baseline-dir",
                    help="自动对比目录：在其 */ref_info_snapshot.tsv 里挑比当前 Info 更旧的最新一份作基线")
    ap.add_argument("--snapshot-name", default="ref_info_snapshot.tsv",
                    help="本次运行结束后，把当前 Info 快照成该文件名（放在 --out 目录内）")
    ap.add_argument("--out", required=True, help="报告输出目录（新建，不改动既有数据）")
    ap.add_argument("--strict", action="store_true", help="有 FAIL 时返回退出码 1")
    args = ap.parse_args()

    info = args.info
    if not info and args.work_dir:
        info = find_existing([os.path.join(args.work_dir, p) for p in
                              ("3.final-ref-virus.db/Plant_Virus_Ref.Info.tsv",
                               "3.final-ref-virus.db/final.cluster.ref_info.tsv")])
    print(f"=== 管线体检 @ {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    print(f"Info : {info}")
    print(f"输出 : {args.out}\n")

    rep = Report(args.out)
    plant_families = load_plant_families(args.vmr) if args.vmr else set()
    df = check_contracts(rep, info, args.vmr, plant_families)
    check_segments(rep, df, args.segment_ref)

    # 基线：优先用"上一次运行的快照"，否则退回 --baseline 指定的文件/auto
    baseline = args.baseline if args.baseline else None
    auto = pick_auto_baseline(args.auto_baseline_dir, info, args.snapshot_name) if args.auto_baseline_dir else None
    if auto:
        rep.add("baseline.auto_snapshot", "INFO", os.path.basename(os.path.dirname(auto)),
                "与上一次运行的快照对比")
        baseline = auto
    elif not baseline:
        rep.add("baseline.none", "INFO", "-",
                "没有可用基线（首次运行或 Info 未变化）；本次已留快照，下次运行将自动对比")
    check_baseline(rep, info, baseline)
    check_artifacts(rep, args.work_dir)
    snap = take_snapshot(info, args.out, args.snapshot_name)
    if snap:
        rep.add("baseline.snapshot_written", "INFO", os.path.basename(snap),
                "已留快照，供下一次运行自动对比")
    n = rep.flush()
    print(f"\n汇总: FAIL {n['FAIL']} / WARN {n['WARN']} / PASS {n['PASS']}  → {args.out}/audit_summary.md")
    if args.strict and n["FAIL"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
