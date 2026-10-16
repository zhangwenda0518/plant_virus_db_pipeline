#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络图页数据构建脚本 (docs/network/network.json)
================================================
双数据源合并, 供 /network/ 页两个标签页使用:

  Tab 1  病毒–宿主网络: 直接复用 docs/association/associations.json
                        (199,070 GenBank 序列, 14,791 关联对) — 运行时聚合, 本脚本
                        仅为其预计算搜索别名 (alias1) 与 Explorer 深链 (vlink)

  Tab 2  媒介–病毒–宿主网络: 8.plant-insect/virus_vector_host.tsv
                        (1,375 条实验验证三元组, 含媒介目/科/属、传毒机制、DOI)
                        宿主谱系经 NCBI taxdump 由 Host TaxID 解析

输出 docs/network/network.json:
  meta    统计与来源
  modes   传毒机制字符串表 (vh 行内以索引引用)
  dois    DOI 字符串表 (vh 行内以索引引用)
  vh      [病毒名, 媒介名, 宿主名, mode_idx, doi_idx 列表] 三元组
  v2      病毒名 → [order, family, genus, ICTV双名, GenBank序列数]
  ve      媒介名 → [order, family, genus, taxid]
  h2      宿主名 → [kingdom, order, family, genus, taxid]
  alias1  Tab1 搜索别名: 小写别名 → associations.json 的 vtax 键
  alias2  Tab2 搜索别名: 小写别名 → VH 病毒名
  vlink   Tab1 中可深链到 /explorer/?profile= 的病毒名列表 (vtax 键 ∩ Ref TSV Species_ICTV)
  elink   Tab2 中可深链到 /explorer/?profile= 的 ICTV 双名列表 (v2 的 ICTV 列 ∩ Ref TSV)

用法: python build_network.py [--taxdump ../../data/external/taxdump]
"""
import os
import re
import sys
import csv
import json
import time
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "association"))   # 复用 Taxdump

TAXDUMP = os.path.join(ROOT, "data", "external", "taxdump")
ASSOC_JSON = os.path.join(HERE, "..", "association", "associations.json")
NAME_MAP = os.path.join(ROOT, "data", "external", "name_mapping.tsv")
VH_TSV = os.path.join(ROOT, "8.plant-insect", "virus_vector_host.tsv")
OUT_JSON = os.path.join(HERE, "network.json")

from build_associations import Taxdump  # noqa: E402


def split_dois(raw):
    """把 DOI 自由文本列拆成单个 DOI / URL 列表, 保持原顺序去重。

    源表这一列不是规整的 DOI: 一行常塞多个, 分隔符混用半角 ; 与全角 ；,
    有的行给的是出版方 / ProQuest / ResearchGate 链接而非 DOI, 还有
    10.1128JVI/01479-15 这种漏掉反斜杠的写法。前端只按单个 DOI 渲染链接,
    所以在这里统一拆开并补齐基础格式。
    """
    out = []
    for p in re.split(r"[;；\n]", raw or ""):
        p = p.strip().rstrip(".,; ")
        if not p:
            continue
        p = re.sub(r"\s+", " ", p)
        p = re.sub(r"^https?://(dx\.)?doi\.org/", "", p)
        if re.match(r"^10\.\d+[A-Za-z]", p):          # 10.1128JVI/... → 10.1128/JVI...
            p = re.sub(r"^(10\.\d+)", r"\1/", p)
        # 期刊缩写与文章号之间误用了 / : 10.1128/JVI/01479-15 → 10.1128/JVI.01479-15
        p = re.sub(r"^(10\.\d+/[A-Za-z]+)/(?=\d+-\d+$|e\d+$)", r"\1.", p)
        # Springer 图书章节 DOI 用 _ 而不是 / : 10.1007/978-3-642-46115-6/5 → ..._5
        # 源表里同一章节两种写法都出现过, 归一成 _ 才能与其余行去重合并
        p = re.sub(r"^(10\.1007/978-[\d-]+)/(\d+)$", r"\1_\2", p)
        if p and p not in out:
            out.append(p)
    return out


def main():
    t_start = time.time()

    # ── 1. 读 associations.json (Tab 1 运行时聚合源 + 病毒序列计数) ──
    print("loading associations.json ...")
    with open(ASSOC_JSON, encoding="utf-8") as f:
        assoc = json.load(f)
    vtax = assoc["vtax"]
    acc_of = collections.Counter()
    for v, h, c in assoc["pairs"]:
        acc_of[v] += c
    print(f"  vtax keys: {len(vtax):,}")

    # ── 2. 读 VH 三元组 ──
    print("loading virus_vector_host.tsv ...")
    vh_rows = []
    with open(VH_TSV, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            vh_rows.append(row)
    print(f"  triplets: {len(vh_rows):,}")

    # ── 3. 宿主谱系: Host TaxID → taxdump ──
    host_taxids = sorted({t for t in ((r.get("Host TaxID") or "").strip() for r in vh_rows)
                          if t.isdigit()})
    print(f"resolving {len(host_taxids)} host taxids via taxdump ...")
    td = Taxdump(TAXDUMP)
    td.load_nodes()
    print(f"taxdump loaded ({time.time()-t_start:.0f}s)")
    h_line = {}
    line_ids = set()
    for t in host_taxids:
        lin = td.lineage(int(t))
        h_line[t] = lin
        line_ids.update(lin.values())
    h_names = td.scientific_names(line_ids)

    def name_of(tid):
        return h_names.get(tid, "")

    # ── 3b. 病毒目: VH TSV 无 Virus Order 列, 由 Virus TaxID → taxdump 补;
    #          taxid 缺失/未解析时用 associations.json vtax 的 科→目 映射兜底 ──
    v_taxids = sorted({t for t in ((r.get("Virus TaxID") or "").strip() for r in vh_rows)
                       if t.isdigit()})
    v_line, v_line_ids = {}, set()
    for t in v_taxids:
        lin = td.lineage(int(t))
        v_line[t] = lin
        v_line_ids.update(lin.values())
    v_names = td.scientific_names(v_line_ids - line_ids)
    fam2ord = {}
    for sp, r in vtax.items():
        if r[0] and not r[0].startswith("(") and r[1] and not r[1].startswith("("):
            fam2ord.setdefault(r[1].lower(), r[0])

    def virus_order_of(row):
        tid = (row.get("Virus TaxID") or "").strip()
        if tid.isdigit():
            lin = v_line.get(tid, {})
            if lin.get("order"):
                return v_names.get(lin["order"], "")
        fam = (row.get("Virus Family") or "").strip().lower()
        return fam2ord.get(fam, "")

    # ── 4. 聚合三元组实体 ──
    v2, ve, h2 = {}, {}, {}
    triplets = []
    mode_counter = collections.Counter()
    doi_counter = collections.Counter()
    lower_vtax = {k.lower(): k for k in vtax}
    # VH 病毒名 → vtax 键 (直接或经 ICTV 双名), 用于补 GenBank 序列数
    ictv_to_vtax = {}
    for row in vh_rows:
        v = (row["Virus Name"] or "").strip()
        lin = (row.get("Lineage") or "").strip()
        ictv = lin.split(";")[-1].strip() if lin else ""
        if ictv:
            k = lower_vtax.get(v.lower()) or lower_vtax.get(ictv.lower())
            if k:
                ictv_to_vtax[ictv] = k
    for r in vh_rows:
        v = (r["Virus Name"] or "").strip()
        vec = (r["Vector"] or "").strip()
        h = (r["Virus Host"] or "").strip()
        # 120 条记录只验证了病毒-媒介关系, 宿主列为 'NA' → 保留病毒-媒介边, 不画宿主
        if h.upper() in ("NA", "N/A", "NONE", "-"):
            h = ""
        mode = (r["Virus Transmission Mode"] or "").strip() or "NA"
        doi = (r.get("DOI for Validation Virus-Insect Relationships") or "").strip()
        if not (v and vec):
            continue
        lin = (r.get("Lineage") or "").strip()
        ictv = lin.split(";")[-1].strip() if lin else ""
        acc = acc_of.get(lower_vtax.get(v.lower()) or lower_vtax.get(ictv.lower()) or "\x00", 0)
        if v not in v2:
            v2[v] = [virus_order_of(r),
                     (r.get("Virus Family") or "").strip(),
                     (r.get("Virus Genus") or "").strip(),
                     ictv, acc]
        if vec not in ve:
            ve[vec] = [(r.get("Vector Order") or "").strip(),
                       (r.get("Vector Family") or "").strip(),
                       (r.get("Vector Genus") or "").strip(),
                       (r.get("Vector TaxID") or "").strip()]
        if h and h not in h2:
            tid = (r.get("Host TaxID") or "").strip()
            lin_h = h_line.get(tid, {}) if tid.isdigit() else {}
            g = lambda rk: name_of(lin_h[rk]) if lin_h.get(rk) else ""  # noqa: E731
            h2[h] = [td.kingdom_of(int(tid)) if tid.isdigit() else "Unknown",
                     g("order"), g("family"), g("genus"), tid]
        mode_counter[mode] += 1
        triplets.append((v, vec, h, mode, split_dois(doi)))

    # ── DOI 归一化 ──
    # 源表的 DOI 列是自由文本: 一行里常塞多个 DOI, 分隔符混用 ; 与 ；,
    # 个别行干脆放的是出版方 URL / ProQuest / ResearchGate 链接, 还有
    # 10.1128JVI/01479-15 这种漏了反斜杠的写法。整条字符串原样入库的话,
    # 详情面板会渲染成一个点不开的超长链接, 所以先拆成单个 DOI 再计数。
    doi_counter = collections.Counter()
    for tr in triplets:
        for one in tr[4]:
            doi_counter[one] += 1
    modes = [m for m, _ in mode_counter.most_common()]
    dois = [d for d, _ in doi_counter.most_common() if d]
    mode_idx = {m: i for i, m in enumerate(modes)}
    doi_idx = {d: i for i, d in enumerate(dois)}
    vh_compact = [[v, e, h, mode_idx[m], [doi_idx[x] for x in ds if x in doi_idx]]
                  for v, e, h, m, ds in triplets]
    print(f"  viruses {len(v2)}, vectors {len(ve)}, hosts {len(h2)}, modes {len(modes)}, dois {len(dois)}")

    # ── 5. 搜索别名 + Tab1 Explorer 深链 ──
    # 深链规则: explorer 的 ?profile= 只认 Ref TSV 的 Species_ICTV; vtax 键约 93% 即 ICTV 双名本身
    # (NCBI 已与 ICTV MSL 同步), 其余为未获批的 NCBI 暂定学名, 无 ICTV 对应则不给链接。
    print("building explorer link set from Plant_Virus_Ref.Info.tsv ...")
    ref_ictv = set()
    with open(os.path.join(ROOT, "docs", "data", "Plant_Virus_Ref.Info.tsv"),
              encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ic = (row.get("Species_ICTV") or "").strip()
            if ic:
                ref_ictv.add(ic)
    vlink = sorted(k for k in vtax if k in ref_ictv)
    elink = sorted({val[3] for val in v2.values() if val[3] and val[3] in ref_ictv})
    print(f"  explorer links: {len(vlink):,}/{len(vtax):,} (tab1), {len(elink):,} ICTV names (tab2)")

    print("building alias tables from name_mapping.tsv ...")
    alias1 = {}       # 小写 → vtax key
    alias2 = {}       # 小写 → VH 病毒名
    lower_vh = {v.lower(): v for v in v2}
    lower_ictv_vh = {val[3].lower(): k for k, val in v2.items() if val[3]}
    # tab1 的病毒节点只到属, 而常用缩写(TSWV 这一档)多半指向一个本库没有 GenBank 记录的
    # ICTV 双名 —— 精确匹配碰不到, 得退到该双名的属上, 否则"搜缩写 = 无结果"。
    vtax_genera = {v[2].lower(): v[2] for v in vtax.values() if len(v) > 2 and v[2]}

    def add_alias1(names, tgt):
        for a in names:
            al = a.strip().lower()
            if al and al != tgt.lower() and len(al) <= 60:
                alias1.setdefault(al, tgt)

    with open(NAME_MAP, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    genus_only = []   # 精确命不中的行, 第二轮退属
    for row in rows:
        ictv = (row.get("ICTV_Name") or "").strip()
        common = (row.get("Common_Name") or "").strip()
        abbr = (row.get("Abbreviation") or "").strip()
        if not ictv and not common:
            continue
        # Tab1: 命中 vtax 键 (vtax 键以 ICTV/NCBI 现行学名为主, 故 ICTV 列优先)
        tgt1 = lower_vtax.get(ictv.lower()) or lower_vtax.get(common.lower())
        if tgt1:
            add_alias1((common, ictv, abbr), tgt1)
        else:
            genus_only.append((ictv, common, abbr))
        # Tab2: 命中 VH 病毒名
        tgt2 = lower_vh.get(common.lower()) or lower_vh.get(ictv.lower()) or lower_ictv_vh.get(ictv.lower())
        if tgt2:
            for a in (common, ictv, abbr):
                al = a.strip().lower()
                if al and al != tgt2.lower() and len(al) <= 60:
                    alias2.setdefault(al, tgt2)
    # 第二轮退属: 必须放在精确命中之后 —— 一个缩写常对应好几种病毒(PEV1 = Peach virus 1
    # 也是 Phytophthora endornavirus 1), 先从表格顺序占住会把真身顶掉。
    for ictv, common, abbr in genus_only:
        genus = None
        for cand in (ictv, common):
            # ICTV 双名法首词即属名; 俗名 ("tomato spotted wilt virus") 首词不是属名, 扫不中
            if cand and ' ' in cand:
                genus = vtax_genera.get(cand.split()[0].strip().lower())
                if genus:
                    break
        if genus:
            add_alias1((common, ictv, abbr), genus)
    # VH 病毒自身的 ICTV 双名也注册为别名
    for v, val in v2.items():
        if val[3]:
            alias2.setdefault(val[3].lower(), v)
    print(f"  alias1: {len(alias1):,}, alias2: {len(alias2):,}, vlink: {len(vlink):,}")

    # ── 6. 输出 ──
    stats = {
        "vh_triplets": len(vh_compact),
        "vh_no_host": sum(1 for t in triplets if not t[2]),
        "vh_viruses": len(v2),
        "vh_vectors": len(ve),
        "vh_hosts": len(h2),
        "vh_virus_genera": len({v[2] for v in v2.values() if v[2]}),
        "vh_virus_families": len({v[1] for v in v2.values() if v[1]}),
        "vh_vector_genera": len({v[2] for v in ve.values() if v[2]}),
        "modes": len(modes),
        "dois": len(dois),
        "vlink": len(vlink),
        "vhost_sequences": assoc["meta"]["stats"]["sequences"],
        "vhost_pairs": assoc["meta"]["stats"]["pairs"],
        "vhost_virus_species": assoc["meta"]["stats"]["virus_species"],
        "vhost_host_leaves": assoc["meta"]["stats"]["host_leaves"],
    }
    data = {
        "meta": {
            "generated": time.strftime("%Y-%m-%d %H:%M"),
            "sources": "virus_vector_host.tsv (VIP-DB experimentally validated virus-vector-host triplets; host lineages via NCBI taxdump) + associations.json (GenBank accessions)",
            "stats": stats,
        },
        "modes": modes,
        "dois": dois,
        "vh": vh_compact,
        "v2": v2,
        "ve": ve,
        "h2": h2,
        "alias1": alias1,
        "alias2": alias2,
        "vlink": vlink,
        "elink": elink,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT_JSON} ({os.path.getsize(OUT_JSON)/1e6:.2f} MB, {time.time()-t_start:.0f}s)")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
