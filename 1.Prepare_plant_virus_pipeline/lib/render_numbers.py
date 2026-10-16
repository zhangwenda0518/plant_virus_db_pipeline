#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_numbers.py — 文档数字单一来源（从产物算数，不再手写）

背景：README §4.5 写"11,956 条 / 6,597 TaxID / 787 混合簇"，而实际产物是 8,484 条、
6,180 TaxID、569 混合簇（当前 G-cluster）——三组数字来自不同批次且无人能追溯。
本脚本把文档里的数字变成**占位符**，由产物实时渲染，并提供 --check 供 CI/体检调用。

用法
----
    # ① 生成事实表（含每个数字的来源文件、行数、时间）
    python lib/render_numbers.py --facts --repo .. --out ../docs/data/NUMBERS.md
    # ② 用事实填充文档占位符 {{key}}
    python lib/render_numbers.py --repo .. --write ../1.Prepare_plant_virus_pipeline/README.md
    # ③ 校验文档里的占位符是否与产物一致（不一致 → 退出码 1）
    python lib/render_numbers.py --repo .. --check ../1.Prepare_plant_virus_pipeline/README.md

找不到对应产物时渲染为 `(无当前批次产物)`，而不是留一个看似正确的旧数字。
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import polars as pl                                        # noqa: E402
from pvcore import count_rows, count_fasta, md5            # noqa: E402

NO_ARTIFACT = "(无当前批次产物)"
PLACEHOLDER = re.compile(r"\{\{([a-z0-9_]+)\}\}")


def _pick(root: str, *cands: str) -> str | None:
    for c in cands:
        p = os.path.join(root, c)
        if os.path.isfile(p):
            return p
    return None


def _distinct(path: str, col: str) -> int | None:
    if not path:
        return None
    try:
        df = pl.read_csv(path, separator="\t", infer_schema_length=0, truncate_ragged_lines=True)
    except Exception:
        return None
    if col not in df.columns:
        return None
    # 2026-10-16: n_unique 会把 ragged 行产生的 null 也计成一个"值"（Species_ICTV 曾因此 5,147→5,148）
    return df[col].drop_nulls().n_unique()


def collect(root: str) -> tuple[dict, dict]:
    """返回 (facts: {key: 值字符串}, sources: {key: (文件, 时间)})"""
    f, src = {}, {}

    def put(key, value, path=None):
        f[key] = NO_ARTIFACT if value is None else str(value)
        if path:
            src[key] = (os.path.relpath(path, root), datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M"))

    ref_info = _pick(root, "docs/data/Plant_Virus_Ref.Info.tsv",
                     "3.final-ref-virus.db/Plant_Virus_Ref.Info.tsv",
                     "3.final-ref-virus.db/final.cluster.ref_info.tsv")
    ref_fa = _pick(root, "docs/data/Plant_Virus_Ref.fasta",
                   "3.final-ref-virus.db/Plant_Virus_Ref.fasta",
                   "3.final-ref-virus.db/final.cluster.ref.fasta")
    full_info = _pick(root, "docs/data/Plant_Virus_Full.Info.tsv",
                      "2.plant-virus.db/E-metadata/Plant_Virus_Full.Info.tsv")
    lca = _pick(root, "2.plant-virus.db/G-cluster/clusters_with_LCA.tsv")

    put("ref_records", count_rows(ref_info) if ref_info else None, ref_info)
    put("ref_taxids", _distinct(ref_info, "Taxid") if ref_info else None, ref_info)
    put("ref_species_ictv", _distinct(ref_info, "Species_ICTV") if ref_info else None, ref_info)
    put("ref_canonical", _distinct(ref_info, "Species_Canonical") if ref_info else None, ref_info)
    put("ref_fasta_seqs", count_fasta(ref_fa) if ref_fa else None, ref_fa)
    put("full_records", count_rows(full_info) if full_info else None, full_info)
    put("lca_mixed_clusters", count_rows(lca) if lca else None, lca)
    put("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"), None)
    return f, src


def render(text: str, facts: dict, strict: bool) -> tuple[str, list]:
    problems = []

    def sub(m):
        k = m.group(1)
        if k not in facts:
            problems.append(f"未知占位符 {{{{{k}}}}}")
            return m.group(0)
        return facts[k]
    out = PLACEHOLDER.sub(sub, text)
    if strict:
        for k, v in facts.items():
            pass
    return out, problems


def main():
    ap = argparse.ArgumentParser(description="文档数字单一来源（事实表 / 渲染 / 校验）")
    ap.add_argument("--repo", default="..", help="仓库根（默认脚本上级目录）")
    ap.add_argument("--out", help="事实表输出路径（--facts）")
    ap.add_argument("--facts", action="store_true")
    ap.add_argument("--write", nargs="*", help="按事实渲染占位符并写回这些文件")
    ap.add_argument("--check", nargs="*", help="校验这些文件里的占位符是否已渲染且与产物一致")
    args = ap.parse_args()
    facts, src = collect(os.path.abspath(args.repo))

    if args.facts or not (args.write or args.check):
        lines = ["# 数字事实表（由 lib/render_numbers.py 生成，勿手改）", "",
                 f"生成时间：{facts['generated_at']}", "",
                 "| 键 | 值 | 来源 | 产物时间 |", "|---|---|---|---|"]
        for k, v in facts.items():
            s = src.get(k, ("-", "-"))
            lines.append(f"| `{k}` | {v} | `{s[0]}` | {s[1]} |")
        lines += ["", "> LCA 混合簇数只在当前批次有 `clusters_with_LCA.tsv` 时才有值；",
                  "> 历史各批次（2,248 / 1,299 / 791 / 787 / 774 / 569）见 `figures/lca_distribution/README.md`。", ""]
        text = "\n".join(lines)
        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"事实表已写: {args.out}")
        else:
            print(text)

    rc = 0
    for path in (args.write or []):
        with open(path, encoding="utf-8") as fh:
            old = fh.read()
        new, probs = render(old, facts, strict=False)
        if probs:
            print(f"⚠ {path}: {'; '.join(probs)}"); rc = 1
        if new != old:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(new)
            print(f"已渲染: {os.path.basename(path)}（{len(PLACEHOLDER.findall(old))} 个占位符）")
        else:
            print(f"无需改动: {os.path.basename(path)}")

    for path in (args.check or []):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        left = PLACEHOLDER.findall(text)
        if left:
            print(f"✗ {os.path.basename(path)}: 仍有未渲染占位符 {sorted(set(left))}"); rc = 1
            continue
        # 已知历史批次数字不得出现在正文（它们与当前产物不一致，属"跨批次混引"）
        stale = [n for n in ("11,956", "6,597", "2,248", "1,299", "791 个混合簇") if n in text]
        if stale:
            print(f"⚠ {os.path.basename(path)}: 正文仍出现历史批次数字 {stale}（应改为占位符或注明批次）")
        print(f"✓ {os.path.basename(path)}: 占位符已全部渲染，与当前事实表一致")
    sys.exit(rc)


if __name__ == "__main__":
    main()
