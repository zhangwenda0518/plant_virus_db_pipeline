#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宿主-病毒关联分析页数据构建脚本
================================
从 Plant_Virus_Full.Info.tsv (199k accessions) + NCBI taxdump 构建双层分类关联表:

  病毒侧: Taxid → NCBI lineage (目/科/属/种, NCBI 已与 ICTV MSL 同步)
  宿主侧: Host 文本 → names.dmp → Taxid → lineage (界/目/科/属/种, 取最细可用阶元)

输出 docs/association/associations.json:
  meta   统计信息
  vtax   病毒种 → [目, 科, 属]
  htax   宿主叶 → [界, 目, 科, 属]   (界: Plant/Algae/Fungi/Animal/...)
  pairs  [病毒种, 宿主叶, accession 数]

用法: python build_associations.py [--taxdump ../../data/external/taxdump]
"""
import os
import re
import sys
import csv
import json
import gzip
import argparse
import time
import collections
from array import array

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
TSV = os.path.join(ROOT, "docs", "data", "Plant_Virus_Full.Info.tsv")
TAXDUMP = os.path.join(ROOT, "data", "external", "taxdump")
OUT_JSON = os.path.join(HERE, "associations.json")

ROOT_TAXID = 1
# 分类判定用祖先 TaxID (与 1.Prepare/B1 的分类语义一致)
TAX_ANCHORS = [
    (9606, "Human"),        # Homo sapiens
    (33090, "Plant"),       # Viridiplantae
    (2763, "Algae"),        # Rhodophyta
    (3041, "Algae"),        # Chlorophyta
    (38254, "Algae"),       # Stramenopiles 中的硅藻等 (部分藻类)
    (4751, "Fungi"),
    (33208, "Animal"),      # Metazoa (含昆虫媒介宿主)
    (2, "Bacteria"),
    (2157, "Archaea"),
]

AUTH_TOKEN = re.compile(r"^[A-Z][a-z]?\.?$")   # 命名人后缀: L. / Mill. / Spach.


def norm_name(s):
    return " ".join((s or "").lower().replace("_", " ").split()).strip(" .,;")


def host_query_variants(raw):
    """由原始 Host 文本生成按优先级排列的查询候选。"""
    cands = []

    def add(s):
        if s and s not in cands:
            cands.append(s)

    s = raw.strip()
    add(s)
    if ";" in s:
        s = s.split(";")[0].strip()
        add(s)
    if "(" in s:
        s2 = re.sub(r"\s*\([^)]*\)", "", s).strip()
        add(s2)
        s = s2
    # 去命名人后缀 / sp. spp. cf. 等
    toks = s.split()
    while len(toks) > 1 and (toks[-1].lower() in ("sp.", "spp.", "sp", "spp", "cf.", "aff.", "x")
                             or AUTH_TOKEN.match(toks[-1])):
        toks.pop()
        add(" ".join(toks))
    if len(toks) >= 2:
        add(" ".join(toks[:2]))       # 双名
    if toks:
        add(toks[0])                  # 属
    return cands


class Taxdump:
    """nodes.dmp → 父指针 + rank 数组; names.dmp 按需两遍扫描。"""

    def __init__(self, taxdump_dir):
        self.dir = taxdump_dir
        self.parent = None
        self.rank_code = None
        self.ranks = []
        self.max_id = 0

    def load_nodes(self):
        t0 = time.time()
        parent = {}
        ranks = {}
        rank_ids = {}
        with open(os.path.join(self.dir, "nodes.dmp"), encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split("|")
                if len(parts) < 5:
                    continue
                tid = int(parts[0])
                par = int(parts[1])
                rank = parts[2].strip()
                parent[tid] = par
                ri = rank_ids.get(rank)
                if ri is None:
                    ri = len(rank_ids)
                    rank_ids[rank] = ri
                ranks[tid] = ri
        self.max_id = max(parent)
        self.parent = array("i", bytes(4 * (self.max_id + 1)))
        self.rank_code = array("h", bytes(2 * (self.max_id + 1)))
        rank_code_values = array("h", bytes(2))  # 0
        for tid, par in parent.items():
            self.parent[tid] = par
        for tid, ri in ranks.items():
            self.rank_code[tid] = ri
        self.ranks = [None] * len(rank_ids)
        for r, i in rank_ids.items():
            self.ranks[i] = r
        print(f"  nodes.dmp: {len(parent):,} nodes, max_id={self.max_id:,} ({time.time()-t0:.0f}s)")

    def lineage(self, taxid, wanted=("species", "genus", "family", "order", "superkingdom", "kingdom", "phylum")):
        """向上走谱系, 返回 {rank: taxid} (取最近祖先, 含自身)。"""
        out = {}
        seen = 0
        cur = taxid
        while cur and cur != ROOT_TAXID and seen < 100:
            ri = self.rank_code[cur] if 0 <= cur <= self.max_id else 0
            rank = self.ranks[ri] if ri is not None else None
            if rank in wanted and rank not in out:
                out[rank] = cur
            cur = self.parent[cur] if 0 <= cur <= self.max_id else 0
            seen += 1
        return out

    def kingdom_of(self, taxid):
        cur = taxid
        chain = set()
        while cur and cur != ROOT_TAXID and cur not in chain:
            chain.add(cur)
            cur = self.parent[cur] if 0 <= cur <= self.max_id else 0
        for anchor, label in TAX_ANCHORS:
            if anchor in chain:
                return label
        return "Other"

    def match_host_names(self, queries):
        """一遍扫描 names.dmp, 归一化匹配查询集 → norm → (priority, taxid)。"""
        t0 = time.time()
        best = {}
        PRIOR = {"scientific name": 0, "genbank common name": 1, "common name": 2,
                 "synonym": 3, "equivalent name": 3, "genbank synonym": 4,
                 "genbank anamorph": 4, "teleomorph": 4, "includes": 5, "in-part": 5}
        qset = {}
        for q, variants in queries.items():
            for v in variants:
                n = norm_name(v)
                if n and n not in qset:
                    qset[n] = q
        print(f"  matching {len(qset):,} name variants in names.dmp ...")
        with open(os.path.join(self.dir, "names.dmp"), encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split("|")
                if len(parts) < 4:
                    continue
                nm = norm_name(parts[1])
                q = qset.get(nm)
                if q is None:
                    continue
                pri = PRIOR.get(parts[3].strip(), 6)
                cur = best.get(q)
                if cur is None or pri < cur[0]:
                    best[q] = (pri, int(parts[0]), parts[1].strip())
        print(f"  resolved {len(best):,}/{len(queries):,} host strings ({time.time()-t0:.0f}s)")
        return best

    def scientific_names(self, taxids):
        """第二遍 names.dmp: 仅取指定 taxid 的学名。"""
        want = set(taxids)
        out = {}
        with open(os.path.join(self.dir, "names.dmp"), encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split("|")
                if len(parts) < 4 or parts[3].strip() != "scientific name":
                    continue
                tid = int(parts[0])
                if tid in want:
                    out[tid] = parts[1].strip()
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--taxdump", default=TAXDUMP)
    ap.add_argument("--tsv", default=TSV)
    ap.add_argument("-o", "--out", default=OUT_JSON)
    args = ap.parse_args()

    td = Taxdump(args.taxdump)
    t0 = time.time()
    td.load_nodes()
    print(f"taxdump loaded ({time.time()-t0:.0f}s)")

    # ── 1. TSV 主扫描: 收集行级 (病毒taxid, 宿主文本) 与唯一值 ──
    t0 = time.time()
    rows = []           # (taxid, host_raw, species_ictv, species_ncbi, family)
    with open(args.tsv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                tid = int(row["Taxid"])
            except (TypeError, ValueError):
                continue  # 2026-10-16: 新批次 TSV 含空/非数字 Taxid 行（无法映射谱系），跳过而非崩溃
            rows.append((tid,
                         (row.get("Host") or "").strip(),
                         (row.get("Species_ICTV") or "").strip(),
                         (row.get("Species_NCBI") or "").strip(),
                         (row.get("Family") or "").strip()))
    print(f"TSV: {len(rows):,} rows ({time.time()-t0:.0f}s)")
    v_taxids = sorted({r[0] for r in rows})
    host_raws = sorted({r[1] for r in rows if r[1]})
    print(f"unique virus taxids: {len(v_taxids):,}, host strings: {len(host_raws):,}")

    # ── 2. 病毒 taxid → 谱系 ──
    t0 = time.time()
    v_line = {tid: td.lineage(tid) for tid in v_taxids}
    all_lineage_ids = set(v_taxids)
    for lin in v_line.values():
        all_lineage_ids.update(lin.values())
    v_names = td.scientific_names(all_lineage_ids)
    print(f"virus lineages resolved ({time.time()-t0:.0f}s)")

    def v_tax_of(tid):
        lin = v_line.get(tid, {})
        g = lambda r: v_names.get(lin.get(r, 0), "") if lin.get(r) else ""
        return {"order": g("order"), "family": g("family"), "genus": g("genus"), "species": g("species")}

    # ── 3. 宿主文本 → taxid → 谱系 ──
    queries = {h: host_query_variants(h) for h in host_raws}
    matched = td.match_host_names(queries)
    host_taxids = {m[1] for m in matched.values()}
    host_line_ids = set(host_taxids)
    host_line = {}
    for t in host_taxids:
        lin = td.lineage(t)
        host_line[t] = lin
        host_line_ids.update(lin.values())
    host_line_ids -= all_lineage_ids
    host_names = td.scientific_names(host_line_ids) if host_line_ids else {}
    all_names = dict(v_names)
    all_names.update(host_names)

    h_resolved = {}
    for raw in host_raws:
        m = matched.get(raw)
        if not m:
            h_resolved[raw] = None
            continue
        _, tid, shown = m
        lin = host_line[tid]
        g = lambda r: all_names.get(lin.get(r, 0), "") if lin.get(r) else ""
        h_resolved[raw] = {
            "kingdom": td.kingdom_of(tid),
            "order": g("order"), "family": g("family"), "genus": g("genus"), "species": g("species"),
        }

    # ── 4. 聚合 ──
    t0 = time.time()
    pair_counter = collections.Counter()
    vtax = {}
    htax = {}
    n_no_host = 0
    for tid, host, sp_ictv, sp_ncbi, fam in rows:
        vt = v_tax_of(tid)
        vsp = vt["species"] or sp_ictv or sp_ncbi
        if not vsp:
            vsp = "Unclassified virus"
        if vsp not in vtax:
            vtax[vsp] = [vt["order"] or "(no order)", vt["family"] or fam or "(no family)",
                         vt["genus"] or "(no genus)"]
        if not host:
            n_no_host += 1
            hkey, hr = "(unknown host)", None
        else:
            hr = h_resolved.get(host)
            if hr is None:
                hkey = "Unresolved: " + host
            else:
                hkey = hr["species"] or hr["genus"] or hr["family"] or hr["order"] or "(unknown host)"
        if hkey not in htax:
            if hr is None:
                htax[hkey] = ["Unknown", "", "", ""]
            else:
                htax[hkey] = [hr["kingdom"], hr["order"], hr["family"], hr["genus"]]
        pair_counter[(vsp, hkey)] += 1
    print(f"aggregated {len(pair_counter):,} pairs ({time.time()-t0:.0f}s)")

    # ── 5. 输出 ──
    n_vsp = len(vtax)
    n_host = len(htax)
    n_plant_host = sum(1 for v in htax.values() if v[0] in ("Plant", "Algae"))
    stats = {
        "sequences": len(rows),
        "pairs": len(pair_counter),
        "virus_species": n_vsp,
        "host_leaves": n_host,
        "plant_host_leaves": n_plant_host,
        "no_host_rows": n_no_host,
    }
    data = {
        "meta": {
            "generated": time.strftime("%Y-%m-%d %H:%M"),
            "source": "Plant_Virus_Full.Info.tsv + NCBI taxdump (taxid-resolved lineages, ICTV-synced)",
            "stats": stats,
        },
        "vtax": vtax,
        "htax": htax,
        "pairs": [[k[0], k[1], v] for k, v in pair_counter.items()],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {args.out} ({os.path.getsize(args.out)/1e6:.1f} MB)")
    print(json.dumps(stats, indent=2))

    # 未解析宿主 top20 (供人工核查)
    unres = collections.Counter()
    for r in rows:
        h = r[1]
        if h and h_resolved.get(h) is None:
            unres[h] += 1
    if unres:
        print("\ntop unresolved hosts:")
        for h, c in unres.most_common(20):
            print(f"  {c:>6}  {h}")


if __name__ == "__main__":
    main()
