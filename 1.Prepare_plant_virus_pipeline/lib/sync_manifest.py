#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_manifest.py — 关键产物对账清单（只读；用于本地 ↔ 服务器一致性核对）

背景：本地 `Plant_Virus_Ref.Info.tsv` 与服务器 `final.cluster.ref_info.tsv`
曾只差 1 条记录（AB113651.1 vs NC_002743.1）却无人发现。两边各跑一次本脚本，
`--compare` 就能把差异列出来。

用法
----
    # ① 两边各生成一份清单
    python lib/sync_manifest.py --preset pvdb --root ~/plant_virus_db --out /tmp/srv.json
    python lib/sync_manifest.py --preset pvdb --root D:/.../plant_virus_db_pipeline --out /tmp/loc.json

    # ② 对比
    python lib/sync_manifest.py --compare /tmp/loc.json /tmp/srv.json

    # 也可直接列文件
    python lib/sync_manifest.py --emit a.tsv b.fasta --out m.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pvcore import md5, count_rows, count_fasta, find_existing        # noqa: E402

# 逻辑名 → 候选相对路径（新名优先、旧名兜底；两边共用同一套逻辑名，便于对比）
PRESETS = {
    "pvdb": {
        "ref_info":    ["3.final-ref-virus.db/Plant_Virus_Ref.Info.tsv",
                        "3.final-ref-virus.db/final.cluster.ref_info.tsv",
                        "docs/data/Plant_Virus_Ref.Info.tsv"],
        "ref_fasta":   ["3.final-ref-virus.db/Plant_Virus_Ref.fasta",
                        "3.final-ref-virus.db/final.cluster.ref.fasta",
                        "docs/data/Plant_Virus_Ref.fasta"],
        "full_info":   ["docs/data/Plant_Virus_Full.Info.tsv",
                        "2.plant-virus.db/E-metadata/Plant_Virus_Full.Info.tsv"],
        "lca_tsv":     ["2.plant-virus.db/G-cluster/clusters_with_LCA.tsv"],
        "lca_plot":    ["2.plant-virus.db/G-cluster/clusters.LCA_Distribution.png"],
        "gene_cov":    ["2.plant-virus.db/H-virus_genes/virus_genes_cov.tsv"],
        "derep_summary": ["2.plant-virus.db/G-cluster/Dereplication_Global_Summary.tsv"],
    }
}


def describe(path: str) -> dict:
    info = {"path": path, "size": os.path.getsize(path),
            "mtime": int(os.path.getmtime(path)), "md5": md5(path)}
    if path.lower().endswith((".tsv", ".csv")):
        info["rows"] = count_rows(path)
    if path.lower().endswith((".fasta", ".fa", ".fna", ".ffn")):
        info["seqs"] = count_fasta(path)
    return info


def emit(items: dict, out: str | None):
    """items: {逻辑名: 绝对路径}"""
    man = {k: describe(p) for k, p in items.items() if p}
    text = json.dumps(man, ensure_ascii=False, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"已写出清单: {out}（{len(man)} 项）")
    else:
        print(text)


def compare(a_path: str, b_path: str, strict: bool = False) -> list:
    with open(a_path, encoding="utf-8") as f:
        a = json.load(f)
    with open(b_path, encoding="utf-8") as f:
        b = json.load(f)
    keys = sorted(set(a) | set(b))
    problems = []
    print(f"{'逻辑名':<16}{'A':<10}{'B':<10}{'行数 A/B':<18}{'MD5':<10}说明")
    for k in keys:
        ra, rb = a.get(k), b.get(k)
        if ra is None or rb is None:
            side = "仅在 B" if ra is None else "仅在 A"
            problems.append((k, "MISSING", f"{side}: {os.path.basename((rb or ra)['path'])}"))
            print(f"{k:<16}{'-' if ra is None else 'ok':<10}{'-' if rb is None else 'ok':<10}"
                  f"{'':<18}{'':<10}{side} 有、另一边没有")
            continue
        rows_a, rows_b = ra.get("rows") or ra.get("seqs"), rb.get("rows") or rb.get("seqs")
        same_md5 = ra["md5"] == rb["md5"]
        rowtxt = f"{rows_a}/{rows_b}"
        note = "一致" if same_md5 else "内容不同"
        if not same_md5:
            problems.append((k, "MD5", f"rows {rowtxt}  size {ra['size']}/{rb['size']}"))
        print(f"{k:<16}{'ok':<10}{'ok':<10}{rowtxt:<18}{'同' if same_md5 else '异':<10}{note}")
    print(f"\n差异项: {len(problems)}")
    for k, kind, why in problems:
        print(f"  - [{kind}] {k}: {why}")
    if strict and problems:
        sys.exit(1)
    return problems


def main():
    ap = argparse.ArgumentParser(description="关键产物对账清单（只读）")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="预置的产物清单")
    ap.add_argument("--root", help="预置路径的根目录")
    ap.add_argument("--emit", nargs="*", help="直接列出要登记的绝对/相对路径")
    ap.add_argument("--out", help="清单输出 JSON（缺省打印到 stdout）")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"), help="对比两份清单")
    ap.add_argument("--strict", action="store_true", help="发现差异时返回 1")
    args = ap.parse_args()

    if args.compare:
        compare(args.compare[0], args.compare[1], args.strict)
        return

    items = {}
    if args.preset:
        if not args.root:
            ap.error("--preset 需要配合 --root")
        for name, cands in PRESETS[args.preset].items():
            hit = find_existing([os.path.join(args.root, c) for c in cands])
            if hit:
                items[name] = hit
            else:
                print(f"  ⚠ 未找到 {name}（候选: {', '.join(cands)}）", file=sys.stderr)
    for p in (args.emit or []):
        items[os.path.basename(p)] = os.path.abspath(p)
    if not items:
        ap.error("请给出 --preset/--root 或 --emit")
    emit(items, args.out)


if __name__ == "__main__":
    main()
