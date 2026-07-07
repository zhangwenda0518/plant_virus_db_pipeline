#!/usr/bin/env python3
"""
build_taxid_lineage.py — 从 NCBI taxonomy dump 生成权威的 taxid → ICTV 8 级分类表。

Metabuli report.tsv 的谱系是有损的(会丢 genus、用过时同名)。本脚本直接遍历
nodes.dmp + names.dmp(构建 Metabuli DB 所用、含 ICTV 名的完整分类树),为数据库
涉及的所有 taxid(taxID_list 及其全部祖先)计算标准 8 级分类,输出 taxid_lineage.tsv。

供 metabuli_api.py 启动时加载,把每条 contig 的 taxid 直接映射为正确的
域界门纲目科属种(NCBI 现已采用 ICTV 双名法,如 Betacytorhabdovirus lycii)。
"""

import os
import argparse

RANKS = ["realm", "kingdom", "phylum", "class", "order", "family", "genus", "species"]


def load_nodes(path):
    par, rank = {}, {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            p = [x.strip() for x in line.split("\t|\t")]
            if len(p) >= 3:
                par[p[0]] = p[1]
                rank[p[0]] = p[2]
    return par, rank


def load_names(path):
    """只取 scientific name。"""
    name = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            p = [x.strip() for x in line.split("\t|\t")]
            if len(p) >= 4 and p[3].replace("\t|", "").strip() == "scientific name":
                name[p[0]] = p[1]
    return name


def ancestors(tid, par):
    out, seen = [], set()
    while tid and tid in par and tid not in seen:
        seen.add(tid)
        out.append(tid)
        if tid == "1":
            break
        tid = par[tid]
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--taxdir", default="/opt/plant_virus_db/taxonomy")
    ap.add_argument("--db", default="/opt/plant_virus_db/ref.virus.build.metabuli_db")
    ap.add_argument("--out", default=os.path.join(here, "taxid_lineage.tsv"))
    args = ap.parse_args()

    print(f"[1/4] 加载 nodes.dmp: {args.taxdir}/nodes.dmp")
    par, rank = load_nodes(os.path.join(args.taxdir, "nodes.dmp"))
    print(f"      → {len(par):,} 节点")
    print(f"[2/4] 加载 names.dmp")
    name = load_names(os.path.join(args.taxdir, "names.dmp"))
    print(f"      → {len(name):,} scientific names")

    # 收集 DB 可分配的全部 taxid:参考序列 taxid(acc2taxid + taxID_list)及其全部祖先。
    # Metabuli 直接分配到参考 taxid 或其 LCA 祖先,二者都被覆盖。
    print(f"[3/4] 收集 DB taxid + 祖先")
    leaves = set()
    acc2taxid = os.path.join(args.db, "acc2taxid.map")
    if os.path.exists(acc2taxid):
        with open(acc2taxid, encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.split()
                if len(p) >= 2 and p[1].isdigit():
                    leaves.add(p[1])
    taxid_list = os.path.join(args.db, "taxID_list")
    if os.path.exists(taxid_list):
        with open(taxid_list, encoding="utf-8", errors="replace") as f:
            for line in f:
                t = line.strip()
                if t.isdigit():
                    leaves.add(t)
    needed = set()
    for t in leaves:
        needed.update(ancestors(t, par))
    print(f"      → {len(leaves):,} 叶 taxid, {len(needed):,} 含祖先需计算谱系")

    print(f"[4/4] 计算 8 级谱系并写出: {args.out}")
    with open(args.out, "w", encoding="utf-8") as fo:
        fo.write("taxid\tsciname\t" + "\t".join(RANKS) + "\n")
        for tid in sorted(needed, key=lambda x: int(x) if x.isdigit() else 0):
            rd = {r: "" for r in RANKS}
            for anc in ancestors(tid, par):
                ar = rank.get(anc, "")
                if ar in rd and not rd[ar]:
                    rd[ar] = name.get(anc, "")
            sciname = name.get(tid, "")
            fo.write(tid + "\t" + sciname + "\t" + "\t".join(rd[r] for r in RANKS) + "\n")
    print(f"完成: {args.out}")


if __name__ == "__main__":
    main()
