#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_index_doc.py — 校验"表格索引文档"与磁盘实际文件是否一致（只读）

背景：`docs/data_tables_index.md` 里写着每个表的行数，但实际产物会过期或缺失
（例：索引写 `genera_no_core_species.tsv` 有 1 行，实际文件 0 行；索引把
`segment_domain_table.tsv` 列为当前表，实际是 8 月 23 日的旧表）。

用法
----
    python lib/check_index_doc.py \
        --index-md  ../docs/data_tables_index.md \
        --tables-dir ../docs/archive/tables \
        [--strict]

退出码：默认 0；--strict 且发现不一致时返回 1。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pvcore import count_rows, md5                              # noqa: E402

ROW_RE = re.compile(r"\|\s*\*{0,2}([A-Za-z0-9_.\-]+\.(?:tsv|csv|fasta|fa|png|json))\*{0,2}\s*\|"
                    r"\s*\*{0,2}([0-9][0-9,]*)\*{0,2}\s*\|")


def parse_index(path: str) -> dict:
    """从 markdown 中提取 {文件名: 声明行数}"""
    declared = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            for name, n in ROW_RE.findall(line):
                declared[name] = int(n.replace(",", ""))
    return declared


def main():
    ap = argparse.ArgumentParser(description="索引文档 vs 实际表文件 一致性校验")
    ap.add_argument("--index-md", required=True, help="索引 markdown（如 docs/data_tables_index.md）")
    ap.add_argument("--tables-dir", required=True, help="实际表所在目录")
    ap.add_argument("--recursive", action="store_true", help="在 tables-dir 下递归找同名文件")
    ap.add_argument("--stale-days", type=int, default=30,
                    help="与索引里最新的表相比落后多少天算过期（默认 30）")
    ap.add_argument("--strict", action="store_true", help="有不一致时返回 1")
    args = ap.parse_args()

    declared = parse_index(args.index_md)
    print(f"=== 索引文档校验 @ {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    print(f"索引: {args.index_md}（声明 {len(declared)} 个文件）")
    print(f"目录: {args.tables_dir}\n")

    def locate(name: str):
        cand = os.path.join(args.tables_dir, name)
        if os.path.isfile(cand):
            return cand
        if args.recursive:
            for root, _, files in os.walk(args.tables_dir):
                if name in files:
                    return os.path.join(root, name)
        return None

    problems, checked, resolved = [], 0, {}
    for name, decl in sorted(declared.items()):
        p = locate(name)
        if p is None:
            problems.append(("MISSING", name, decl, None, "索引里列了，磁盘上没有"))
            continue
        if not name.lower().endswith((".tsv", ".csv")):
            checked += 1                      # 非表格只校验存在性
            continue
        act = count_rows(p)
        checked += 1
        resolved[name] = (p, decl, act)
        if act is None:
            problems.append(("UNREADABLE", name, decl, None, "无法统计行数"))
        elif act != decl:
            problems.append(("ROWS", name, decl, act, f"索引 {decl} 行 vs 实际 {act} 行"))

    # 相对新鲜度：与"索引里最新的那个表"相比，落后超过 --stale-days 天即提示
    # （这是实际踩过的坑：segment_domain_table.tsv 停在 8-23，却被索引当作当前表）
    if resolved:
        newest = max(os.path.getmtime(p) for p, _, _ in resolved.values())
        for name, (p, decl, act) in resolved.items():
            lag = (newest - os.path.getmtime(p)) / 86400
            if lag > args.stale_days:
                problems.append(("STALE", name, decl, act,
                                 f"比索引里最新的表旧 {lag:.0f} 天（阈值 {args.stale_days}）"))

    # 目录里存在、但索引没提到的表
    if os.path.isdir(args.tables_dir):
        on_disk = {f for f in os.listdir(args.tables_dir) if f.endswith(".tsv")}
        for extra in sorted(on_disk - set(declared)):
            if extra.endswith(".bak.20260928_refupdate") or ".bak" in extra:
                continue
            problems.append(("UNDECLARED", extra, None, count_rows(os.path.join(args.tables_dir, extra)),
                             "目录里有、索引未收录"))

    if problems:
        print(f"{'类型':<12}{'文件':<44}{'索引':>7}{'实际':>7}  说明")
        for kind, name, decl, act, why in problems:
            print(f"{kind:<12}{name:<44}{str(decl or '-'):>7}{str(act if act is not None else '-'):>7}  {why}")
    print(f"\n汇总: 校验 {checked} 个文件，问题 {len(problems)} 项")
    if args.strict and problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
