#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_global_index.py — 门户全局检索索引构建

聚合各模块可检索实体为一份 docs/data/global_search_index.json，
供门户检索框（/data/global_search_index.json）做前端模糊搜索（Fuse.js）。

实体轴与主键：病毒物种（Species_Canonical，别名归一复用流水线产物）。
其余模块（结构/引物/照片/文献/OneKP/PamirDB）按名字解析回物种轴后，
把计数折叠进物种记录；无法归并的实体以独立类型入索引。

用法：
    python scripts/build_global_index.py

输入源（缺失时跳过并在 meta.sources 标记）：
    docs/data/Plant_Virus_Ref.Info.tsv          物种轴 + 别名（Species_Canonical）
    docs/data/Plant_Virus_Full.Info.tsv         全量序列计数
    15.uniprot_plant_virus_structures/structures_index.tsv   3D 结构
    docs/data/primers/primer_reference.tsv      引物（按 Species 聚合对数）
    docs/data/unified_gallery.json              症状照片
    7.literature_tracker/web/data/data.json     文献（virus_name 的 (ACRO) 反哺缩写别名）
    docs/genes/data/{NLR_all,UPS_all,sRNA_all,miRNA_genes}.tsv   抗病毒基因
    docs/data/antivirals.json                   抗病毒化合物（/genes/#avc）
    docs/eve/data/eve_landscape.json            EVE 宿主科
    12.pamirdb/data/pamirdb.sqlite              PV-miRNA
    13.onekp_virus/all_viruses.best.summary.tsv OneKP 病毒检出（UTF-16）

深链 URL 约定依据 analysis/global_search_20261015/DEEP_LINKS.md。
"""
import csv
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data" / "global_search_index.json"

TYPE_ORDER = ["virus", "family", "structure", "primer", "paper", "gene",
              "photo", "compound", "host", "pamir", "module"]

# 常用缩写 → NCBI 物种名（人工维护的最小集；文献 (ACRO) 模式会自动补充更多）。
# 构建时若对应物种在库中找不到会打印告警，便于修剪。
MANUAL_ACRONYMS = {
    "TMV": "Tobacco mosaic virus", "CMV": "Cucumber mosaic virus",
    "TuMV": "Turnip mosaic virus", "PVY": "Potato virus Y",
    "PVX": "Potato virus X", "PVA": "Potato virus A",
    "PVM": "Potato virus M", "PVS": "Potato virus S",
    "PPV": "Plum pox virus", "TEV": "Tobacco etch virus",
    "LMV": "Lettuce mosaic virus", "ZYMV": "Zucchini yellow mosaic virus",
    "WMV": "Watermelon mosaic virus", "MDMV": "Maize dwarf mosaic virus",
    "SCMV": "Sugarcane mosaic virus", "SrMV": "Sorghum mosaic virus",
    "BYMV": "Bean yellow mosaic virus", "CYVV": "Clover yellow vein virus",
    "ToMV": "Tomato mosaic virus", "ToLCV": "Tomato leaf curl virus",
    "TYLCV": "Tomato yellow leaf curl virus", "PepMV": "Pepino mosaic virus",
    "TSWV": "Tomato spotted wilt virus", "INSV": "Impatiens necrotic spot virus",
    "GRSV": "Groundnut ringspot virus", "TCSV": "Tomato chlorotic spot virus",
    "BYDV": "Barley yellow dwarf virus", "RSV": "Rice stripe virus",
    "RDV": "Rice dwarf virus", "RYMV": "Rice yellow mottle virus",
    "CaMV": "Cauliflower mosaic virus", "BCTV": "Beet curly top virus",
    "BSCTV": "Beet severe curly top virus", "GFLV": "Grapevine fanleaf virus",
    "ArMV": "Arabis mosaic virus", "TRV": "Tobacco rattle virus",
    "PMMoV": "Pepper mild mottle virus", "MSV": "Maize streak virus",
    "WDV": "Wheat dwarf virus", "CTV": "Citrus tristeza virus",
    "CGMMV": "Cucumber green mottle mosaic virus", "AMV": "Alfalfa mosaic virus",
    "TAV": "Tomato aspermy virus", "PNRSV": "Prunus necrotic ringspot virus",
    "ApMV": "Apple mosaic virus", "ToBRFV": "Tomato brown rugose fruit virus",
    "WSMV": "Wheat streak mosaic virus",
}

# 传统名 → 库内物种名（管线数据已被新命名归一、传统名不存在时的手工桥，可继续扩充）
MANUAL_NAME_ALIASES = {
    "Alfalfa mosaic virus": "Alfamovirus AMV",
}

MODULES = [
    ("Plant Virus Database Portal", ["门户", "首页", "portal", "home"], "/"),
    ("Reference Genomes", ["参考数据库", "参考序列", "reference"], "/reference/"),
    ("Data Explorer", ["数据浏览器", "explorer", "时空演变"], "/explorer/"),
    ("Primer Database", ["引物数据库", "引物", "primers", "PCR", "qPCR", "LAMP"], "/primers/"),
    ("Vector-Host Relations", ["媒介宿主", "传播", "vector", "介体"], "/relations/#vector"),
    ("EVE Landscape", ["内源性病毒", "EVE", "古病毒"], "/eve/"),
    ("Metabuli Classification", ["宏基因组", "分类", "metabuli", "contig"], "/metabuli/"),
    ("Symptom Photos", ["症状照片", "图库", "photos"], "/photos/"),
    ("Antiviral Genes", ["抗病毒基因", "免疫基因", "NLR", "genes"], "/genes/"),
    ("PamirDB PV-miRNA", ["miRNA", "pamirdb", "靶标预测"], "/pamirdb/"),
    ("OneKP Virome", ["1KP", "转录组", "onekp"], "/onekp/"),
    ("3D Structures Atlas", ["蛋白质结构", "结构", "structures", "AlphaFold", "PDB"], "/structures3d/atlas/"),
    ("Literature Tracker", ["文献追踪", "文献", "literature", "PubMed"], "/literature/"),
    ("Knowledge Base RAG", ["知识库", "AI 问答", "knowledge", "RAG"], "/knowledge/"),
    ("Phylogeny", ["进化树", "系统发育", "phylo"], "/phylo/"),
]

_ACRO_RE = re.compile(r"([A-Za-z][A-Za-z0-9 \-'\.]+?(?:virus|viroid))\s*\(([A-Za-z][A-Za-z0-9-]{1,11})\)", re.I)
_NONALNUM = re.compile(r"[^a-z0-9]+")

# 照片孤儿名里的句子碎片首词（PDF 图注残留），命中即丢弃
_FRAG_WORDS = {
    "against", "after", "actions", "additionally", "advance", "advances", "adaptation",
    "accumulation", "infection", "levels", "cloned", "although", "all", "among", "also",
    "both", "during", "each", "from", "however", "many", "more", "most", "several",
    "such", "than", "these", "those", "their", "this", "that", "while", "with",
    "within", "without", "was", "were", "been", "analysis", "based", "using",
    "as", "assembly", "attempts", "amplification", "antagonistic", "activity",
}


def norm(s):
    """检索归一化：小写 + 仅保留字母数字（中文名归一后为空，回退原串）。"""
    s = (s or "").strip()
    n = _NONALNUM.sub("", s.lower())
    return n or s


def read_tsv_dicts(path, encoding="utf-8"):
    with open(path, encoding=encoding, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


class IndexBuilder:
    def __init__(self):
        self.records = []
        self.warnings = []
        self.sources = {}

    def warn(self, msg):
        self.warnings.append(msg)

    # ---------- 别名注册与解析 ----------
    def resolve(self, name):
        if not name:
            return None
        n = norm(name)
        hit = self.norm2canon.get(n)
        if hit:
            return hit
        stripped_name = name.strip()
        hit = self.acro2canon.get(stripped_name.upper())
        if hit:
            return hit
        # organism 常带 "(strain XX)" "(TuMV)" 等括号后缀 → 剥掉重试
        stripped = re.sub(r"\([^)]*\)", " ", name)
        if stripped != name:
            hit = self.norm2canon.get(norm(stripped))
            if hit:
                return hit
        # 最后回退：括号内容可能是别名（长名）或缩写（短名），递归解析
        for token in re.findall(r"\(([^)]+)\)", name):
            hit = self.acro2canon.get(token.strip().upper()) or self.norm2canon.get(norm(token))
            if hit:
                return hit
        # 尾部大写 token（如 "Alfamovirus AMV" 结尾的 AMV）
        m = re.search(r"\b([A-Z][A-Za-z0-9]{1,9})\s*$", name.strip())
        if m:
            return self.acro2canon.get(m.group(1).upper())
        return None

    def run(self):
        t0 = time.time()
        self.build_species_axis()      # 主轴：canonical 物种 + 别名
        self.fold_full_sequences()     # 211k 行的传统名注册为别名桥（需在文献/照片之前）
        self.fold_literature()         # 文献计数 + (ACRO) 别名反哺
        self.fold_primers()
        self.fold_structures()
        self.fold_photos()
        self.fold_onekp()
        self.fold_pamirdb()
        self.emit_families()
        self.emit_genes()
        self.emit_eve_hosts()
        self.emit_compounds()
        self.emit_papers()
        self.emit_modules()
        self.sort_and_write(t0)

    # ---------- 各数据源 ----------
    def build_species_axis(self):
        path = ROOT / "docs/data/Plant_Virus_Ref.Info.tsv"
        rows = read_tsv_dicts(path)
        self.norm2canon, self.acro2canon = {}, {}
        self.sp = defaultdict(lambda: {
            "ncbi": Counter(), "ictv": "", "vmr": "", "fam": Counter(), "gen": Counter(),
            "hosts": set(), "ref": 0, "full": 0, "prm": 0, "str": 0,
            "pic": 0, "pic_thumb": "", "lit": 0, "kp": set(), "tgt": 0,
        })
        for r in rows:
            canon = (r.get("Species_Canonical") or "").strip() or (r.get("Species_ICTV") or "").strip()
            if not canon:
                continue
            info = self.sp[canon]
            info["ref"] += 1
            ncbi = (r.get("Species_NCBI") or "").strip()
            if ncbi:
                info["ncbi"][ncbi] += 1
                self.norm2canon.setdefault(norm(ncbi), canon)
                # 去括号常用名（"Turnip mosaic virus (isolate UK1)" -> "Turnip mosaic virus"）
                base = re.sub(r"\([^)]*\)", " ", ncbi).strip()
                if base and base != ncbi:
                    self.norm2canon.setdefault(norm(base), canon)
            ictv = (r.get("Species_ICTV") or "").strip()
            if ictv and not info["ictv"]:
                info["ictv"] = ictv
            if ictv:
                self.norm2canon.setdefault(norm(ictv), canon)
            vmr = (r.get("VMR_Species") or "").strip()
            if vmr:
                if not info["vmr"]:
                    info["vmr"] = vmr
                self.norm2canon.setdefault(norm(vmr), canon)
            self.norm2canon.setdefault(norm(canon), canon)
            fam = (r.get("VMR_Family") or "").strip()
            gen = (r.get("VMR_Genus") or "").strip()
            if fam:
                info["fam"][fam] += 1
            if gen:
                info["gen"][gen] += 1
            host = (r.get("Host") or "").strip()
            if host:
                info["hosts"].add(host)
            names = (r.get("Virus name(s)") or "").strip()
            for extra in re.split(r"[;；]", names):
                extra = extra.strip()
                if extra:
                    self.norm2canon.setdefault(norm(extra), canon)
        # 人工缩写表
        misses = []
        for acro, name in MANUAL_ACRONYMS.items():
            canon = self.norm2canon.get(norm(name))
            if canon:
                self.acro2canon[acro.upper()] = canon
            else:
                misses.append(f"{acro} -> {name}")
        if misses:
            self.warn("MANUAL_ACRONYMS 未命中: " + "; ".join(misses))
        # 传统名桥（反向表供 emit_virus_records 写入别名）
        self.name_alias_of = defaultdict(list)
        nmisses = []
        for trad, name in MANUAL_NAME_ALIASES.items():
            canon = self.norm2canon.get(norm(name))
            if canon:
                self.norm2canon.setdefault(norm(trad), canon)
                self.name_alias_of[canon].append(trad)
            else:
                nmisses.append(f"{trad} -> {name}")
        if nmisses:
            self.warn("MANUAL_NAME_ALIASES 未命中: " + "; ".join(nmisses))
        self.sources["ref_info"] = f"{len(rows)} rows -> {len(self.sp)} species"
        # 家族/genus 计数（emit_families 用）
        self.fam_species = defaultdict(set)
        self.fam_rows = Counter()
        for canon, info in self.sp.items():
            for fam in info["fam"]:
                self.fam_species[fam].add(canon)
                self.fam_rows[fam] += info["ref"]

    def fold_full_sequences(self):
        path = ROOT / "docs/data/Plant_Virus_Full.Info.tsv"
        rows = read_tsv_dicts(path)
        miss = 0
        for r in rows:
            ncbi = (r.get("Species_NCBI") or "").strip()
            ictv = (r.get("Species_ICTV") or "").strip()
            canon = self.resolve(ncbi) or self.resolve(ictv)
            if canon:
                self.sp[canon]["full"] += 1
                # 传统名（Full.Info 的 GenBank 命名）注册为别名桥，供照片/文献/照片解析
                for nm in (ncbi, ictv):
                    if nm:
                        self.norm2canon.setdefault(norm(nm), canon)
                base = re.sub(r"\([^)]*\)", " ", ncbi).strip() if ncbi else ""
                if base and base != ncbi:
                    self.norm2canon.setdefault(norm(base), canon)
                host = (r.get("Host") or "").strip()
                if host:
                    self.sp[canon]["hosts"].add(host)
            else:
                miss += 1
        self.sources["full_info"] = f"{len(rows)} rows, {miss} unresolved"

    def fold_literature(self):
        path = ROOT / "7.literature_tracker/web/data/data.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.papers = data
        for r in data:
            vn = (r.get("virus_name") or "").strip()
            hit = False
            for canon in {self.resolve(vn), *filter(None, (self.resolve(n) for n, _ in _ACRO_RE.findall(vn)))}:
                if canon:
                    self.sp[canon]["lit"] += 1
                    hit = True
                # (英文名 (ACRO)) 模式 → 反哺缩写别名
            for name, acro in _ACRO_RE.findall(vn):
                canon = self.resolve(name)
                if canon:
                    self.acro2canon.setdefault(acro.upper(), canon)
            if vn and not hit:
                pass  # 未命中物种的文献仍以 title 入索引（emit_papers），不算丢失
        self.sources["literature"] = f"{len(data)} papers"

    def fold_primers(self):
        path = ROOT / "docs/data/primers/primer_reference.tsv"
        if not path.exists():
            self.sources["primers"] = "SKIPPED (file missing)"
            return
        rows = read_tsv_dicts(path)
        miss = Counter()
        pair_ids = set()
        for r in rows:
            sp = (r.get("Species") or "").strip()
            pid = (r.get("Pair_ID") or "").strip()
            if pid:
                pair_ids.add(pid)
            canon = self.resolve(sp)
            if canon:
                self.sp[canon]["prm"] += 1
            elif sp:
                miss[sp] += 1
        self.primer_designs = len(pair_ids)
        self.primer_orphans = miss
        self.sources["primers"] = f"{len(rows)} primer pairs, {len(miss)} orphan species"

    def fold_structures(self):
        path = ROOT / "15.uniprot_plant_virus_structures/structures_index.tsv"
        rows = read_tsv_dicts(path)
        self.struct_rows = rows
        miss = Counter()
        for r in rows:
            has_model = any((r.get(c) or "").strip() for c in
                            ("pdb_ids", "afdb_model", "selffold_model", "rvpsd_model"))
            if not has_model:
                continue
            org = (r.get("organism") or "").strip()
            canon = self.resolve(org)
            if canon:
                self.sp[canon]["str"] += 1
            elif org:
                miss[org] += 1
        self.sources["structures"] = f"{len(rows)} entries, {len(miss)} unresolved organisms"
        if miss:
            top = "; ".join(f"{k}({v})" for k, v in miss.most_common(8))
            self.warn(f"结构 organism 未命中物种轴 top8: {top}")

    def fold_photos(self):
        path = ROOT / "docs/data/unified_gallery.json"
        gal = json.loads(path.read_text(encoding="utf-8"))
        miss = Counter()
        junk = {"ICTV"}
        junk_tokens = ("description", "descr", "abbreviation", "quantification", "supplement")
        for g in gal:
            raw = (g.get("virus") or "").strip()
            name = re.sub(r"\s+", " ", raw)
            # PDF 源残留头部词（"Abstract Cucumber mosaic virus"）
            name = re.sub(r"^(abstract|highlights|editorial)\s+", "", name, flags=re.I)
            canon = None
            for field in ("virus", "virus_latin", "virus_ictv"):
                canon = self.resolve(re.sub(r"\s+", " ", (g.get(field) or "").strip()))
                if canon:
                    break
            # PDF 源常见 "AbMV Abutilon mosaic virus" 连写：剥前导缩写再试
            if not canon:
                m = re.match(r"^([A-Za-z0-9]{2,6})\s+(.+)$", name)
                if m and sum(1 for ch in m.group(1) if ch.isupper()) >= 2:
                    canon = self.resolve(m.group(2))
            # 句子片段尾部常是真实病毒名（"Accumulation levels of Tobacco mosaic virus"）
            if not canon:
                words = name.split()
                for k in (6, 5, 4, 3, 2):
                    if len(words) >= k:
                        canon = self.resolve(" ".join(words[-k:]))
                        if canon:
                            break
            if canon:
                info = self.sp[canon]
                info["pic"] += 1
                if not info["pic_thumb"]:
                    info["pic_thumb"] = g.get("thumb") or ""
            else:
                # 孤儿只保留「长得像 NCBI 物种名」的：首词大写 + 中间全小写 + virus/viroid 结尾，
                # 或纯缩写；句子碎片（冠词/常见句首词开头）一律丢弃
                words = name.split()
                strict = bool(re.match(r"^[A-Z][a-zA-Z]+(?: [a-z0-9'\-]+)* (virus|viroid)s?$", name))
                looks_acro = bool(re.match(r"^[A-Za-z0-9]{2,10}$", name)) and sum(1 for ch in name if ch.isupper()) >= 2
                fragment = (bool(re.match(r"^(a|an|the)\s+", name, re.I))
                            or bool(re.search(r"\s(and|or)\s", name, re.I))
                            or any(w.lower() in _FRAG_WORDS for w in words[:-1]))
                if ((strict or looks_acro) and not fragment and len(words) <= 6
                        and not any(t in name.lower() for t in junk_tokens)):
                    miss[name] += 1
        self.photo_orphans = miss
        self.sources["photos"] = f"{len(gal)} photos, {len(miss)} distinct unresolved names"

    def fold_onekp(self):
        path = ROOT / "13.onekp_virus/all_viruses.best.summary.tsv"
        if not path.exists():
            self.sources["onekp"] = "SKIPPED (file missing)"
            return
        rows = read_tsv_dicts(path, encoding="utf-16")
        miss = Counter()
        for r in rows:
            canon = self.resolve(r.get("Species_NCBI")) or self.resolve(r.get("Species_ICTV"))
            sample = (r.get("Sample") or "").strip()
            if canon and sample:
                self.sp[canon]["kp"].add(sample)
            elif r.get("Species_NCBI"):
                miss[r["Species_NCBI"]] += 1
        self.sources["onekp"] = f"{len(rows)} hit rows, {len(miss)} unresolved"

    def fold_pamirdb(self):
        path = ROOT / "12.pamirdb/data/pamirdb.sqlite"
        if not path.exists():
            self.sources["pamirdb"] = "SKIPPED (file missing)"
            return
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            vir_cols = {r[1] for r in con.execute("PRAGMA table_info(viruses)")}
            pred_cols = {r[1] for r in con.execute("PRAGMA table_info(predictions)")}
            vname_col = next((c for c in ("name", "virus_name", "species", "virus") if c in vir_cols), None)
            m_col = next((c for c in ("mirna_id", "miRNA_id", "mirna") if c in pred_cols), None)
            v_col = next((c for c in ("virus_id", "virus") if c in pred_cols), None)
            self.pamir_mirnas = [r[0] for r in con.execute("SELECT mirna_id FROM mirnas ORDER BY mirna_id")]
            if vname_col and v_col and m_col:
                # 按列名自适应取 virus_id -> 名称映射
                vid2name = {}
                idcol = "id" if "id" in vir_cols else ("virus_id" if "virus_id" in vir_cols else None)
                if idcol:
                    for r in con.execute(f"SELECT {idcol} AS vid, {vname_col} AS vn FROM viruses"):
                        vid2name[r["vid"]] = r["vn"]
                for r in con.execute(f"SELECT {m_col} AS m, {v_col} AS v FROM predictions"):
                    vn = vid2name.get(r["v"])
                    canon = self.resolve(vn) if vn else None
                    if canon:
                        self.sp[canon]["tgt"] += 1
                self.pamir_predictions = con.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
            self.sources["pamirdb"] = f"{len(self.pamir_mirnas)} miRNAs"
        finally:
            con.close()

    # ---------- 记录生成 ----------
    def emit_families(self):
        for fam in sorted(self.fam_species, key=lambda f: -len(self.fam_species[f])):
            self.records.append({
                "t": "family", "n": fam,
                "s": f"virus family · {len(self.fam_species[fam])} species · {self.fam_rows[fam]} ref seqs",
                "u": f"/phylo/?q={quote(fam)}",
            })

    def emit_genes(self):
        specs = [
            ("docs/genes/data/NLR_all_genes.tsv", "NLR", "nlr", "NLR immune receptor"),
            ("docs/genes/data/UPS_all_genes.tsv", "UPS", "ups", "ubiquitin-proteasome"),
            ("docs/genes/data/sRNA_all_genes.tsv", "sRNA", "srna", "RNA silencing"),
            ("docs/genes/data/miRNA_genes.tsv", "miRNA", "mirna", "miRNA gene"),
        ]
        for rel, cat, anchor, cat_en in specs:
            path = ROOT / rel
            if not path.exists():
                self.sources[f"genes_{cat}"] = "SKIPPED"
                continue
            rows = read_tsv_dicts(path)
            self.gene_total = getattr(self, "gene_total", 0) + len(rows)
            for r in rows:
                sym = (r.get("Symbol") or "").strip()
                sp = (r.get("Species") or "").strip()
                full = (r.get("FullName") or "").strip()
                if not sym and not full:
                    continue
                self.records.append({
                    "t": "gene",
                    "n": f"{sym or full} · {sp}",
                    "s": f"{cat_en} gene · {full}" if full and full != sym else f"{cat_en} gene",
                    "u": f"/genes/gene_browser.html#{anchor}",
                })
            self.sources[f"genes_{cat}"] = f"{len(rows)} genes"

    def emit_eve_hosts(self):
        path = ROOT / "docs/eve/data/eve_landscape.json"
        if not path.exists():
            self.sources["eve_hosts"] = "SKIPPED"
            return
        e = json.loads(path.read_text(encoding="utf-8"))
        for h in e.get("host_families", []):
            self.records.append({
                "t": "host", "n": h.get("n", ""),
                "s": f"EVE host family · {h.get('grp', '?')} · {h.get('l', 0)} EVE loci",
                "u": "/eve/?view=host",
            })
        self.sources["eve_hosts"] = f"{len(e.get('host_families', []))} host families"

    def emit_compounds(self):
        path = ROOT / "docs/data/antivirals.json"
        if not path.exists():
            self.sources["compounds"] = "SKIPPED"
            return
        a = json.loads(path.read_text(encoding="utf-8"))
        self.compound_total = len(a.get("compounds", []))
        for c in a.get("compounds", []):
            self.records.append({
                "t": "compound", "n": c.get("name", ""),
                "s": f"antiviral compound · {c.get('n_viruses', 0)} viruses · {c.get('n_papers', 0)} papers",
                "u": "/genes/gene_browser.html#avc",
            })
        self.sources["compounds"] = f"{len(a.get('compounds', []))} compounds"

    def emit_papers(self):
        for r in self.papers:
            title = (r.get("title") or "").strip()
            if not title:
                continue
            journal = (r.get("journal") or "").strip()
            year = r.get("year") or (r.get("pub_date") or "")[:4]
            sub = " · ".join(x for x in (journal, str(year) if year else "") if x and x != "None")
            self.records.append({"t": "paper", "n": title[:150], "s": sub, "u": "/literature/"})
        self.sources["papers_emitted"] = str(len(self.papers))

    def emit_modules(self):
        for name, aliases, url in MODULES:
            self.records.append({"t": "module", "n": name, "a": aliases, "u": url})

    def emit_virus_records(self):
        for canon, info in self.sp.items():
            # 显示名：去括号后最高频的 NCBI 常用名（"Turnip mosaic virus"），
            # 深链名：Species_ICTV（explorer 下拉选项本体，保证 ?profile= 命中）
            ncbi_full = info["ncbi"].most_common(1)[0][0] if info["ncbi"] else ""
            ncbi_base = re.sub(r"\([^)]*\)", " ", ncbi_full).strip() if ncbi_full else ""
            label = ncbi_base or canon
            url_name = info["ictv"] or ncbi_full or canon
            fam = info["fam"].most_common(1)[0][0] if info["fam"] else ""
            gen = info["gen"].most_common(1)[0][0] if info["gen"] else ""
            counts = {k: v for k, v in (
                ("ref", info["ref"]), ("full", info["full"]), ("primers", info["prm"]),
                ("structures", info["str"]), ("photos", info["pic"]), ("papers", info["lit"]),
                ("onekp", len(info["kp"])), ("pv-mirna targets", info["tgt"])) if v}
            sub_parts = [x for x in (fam, gen) if x]
            sub_parts.append(f"{info['ref']} ref / {info['full']} seqs")
            if info["ictv"] and info["ictv"].lower() not in {label.lower(), canon.lower()}:
                sub_parts.append(f"ICTV: {info['ictv']}")
            hosts = sorted(info["hosts"], key=len)[:3]
            if hosts:
                sub_parts.append("hosts: " + "; ".join(hosts))
            aliases = []
            seen = {label.lower(), canon.lower()}
            for cand in (canon, info["ictv"], info["vmr"], ncbi_full, *self.name_alias_of.get(canon, [])):
                if cand and cand.lower() not in seen:
                    aliases.append(cand)
                    seen.add(cand.lower())
            for acro, c2 in self.acro2canon.items():
                if c2 == canon and acro.lower() not in seen:
                    aliases.append(acro)
                    seen.add(acro.lower())
            rec = {
                "t": "virus", "n": label,
                "s": " · ".join(sub_parts),
                "u": f"/explorer/?profile={quote(url_name)}",
                "c": counts,
                "x": {
                    "primers": f"/primers/search?q={quote(label)}",
                    "phylo": f"/phylo/?q={quote(label)}",
                },
            }
            if aliases:
                rec["a"] = aliases[:10]
            if info["pic_thumb"]:
                rec["img"] = info["pic_thumb"]
            self.records.append(rec)
            # 引物种级详情页（物种轴命中时作为附加深链）
            if info["prm"]:
                rec["x"]["primer_species"] = f"/primers/species/{quote(label)}"

    def emit_orphans(self):
        # 无法归并到物种轴的引物物种 / 照片名 → 独立记录，保证可检索
        for name, n in getattr(self, "primer_orphans", {}).items():
            self.records.append({
                "t": "primer", "n": name,
                "s": f"primer species · {n} primer pairs",
                "u": f"/primers/search?q={quote(name)}",
            })
        for name, n in getattr(self, "photo_orphans", {}).items():
            if not name:
                continue
            self.records.append({
                "t": "photo", "n": name,
                "s": f"symptom photos · {n}",
                "u": "/photos/",
            })

    def emit_structures(self):
        for r in self.struct_rows:
            has_model = any((r.get(c) or "").strip() for c in
                            ("pdb_ids", "afdb_model", "selffold_model", "rvpsd_model"))
            if not has_model:
                continue
            acc = (r.get("accession") or "").strip()
            entry = (r.get("entry") or "").strip()
            org_raw = (r.get("organism") or "").strip()
            org = re.sub(r"\([^)]*\)", " ", org_raw).strip() or org_raw
            length = (r.get("length") or "").strip()
            pdb = [p for p in re.split(r"[,;]", (r.get("pdb_ids") or "").strip()) if p]
            has_af = bool((r.get("afdb_model") or "").strip())
            has_self = bool((r.get("selffold_model") or "").strip())
            # viewer.html 已支持 pdb/af/self/rv 四种 src（RVPSD 模型由 /structures3d/structures/ 服务）
            if pdb:
                u = f"/structures3d/atlas/viewer.html?acc={quote(acc)}&src=pdb"
            elif has_af:
                u = f"/structures3d/atlas/viewer.html?acc={quote(acc)}&src=af"
            elif has_self:
                u = f"/structures3d/atlas/viewer.html?acc={quote(acc)}&src=self"
            else:
                u = f"/structures3d/atlas/viewer.html?acc={quote(acc)}&src=rv"
            srcs = []
            if pdb:
                srcs.append("PDB " + ",".join(pdb[:3]))
            if has_af:
                srcs.append("AFDB")
            if has_self:
                srcs.append("self-fold")
            if (r.get("rvpsd_model") or "").strip():
                srcs.append("RVPSD")
            rec = {
                "t": "structure",
                "n": f"{org} · {acc}",
                "s": f"3D structure · {length} aa · {' / '.join(srcs)}",
                "u": u,
            }
            aliases = [a for a in (entry, *pdb) if a and a.lower() != acc.lower()]
            if aliases:
                rec["a"] = aliases[:6]
            self.records.append(rec)

    def emit_pamir_mirnas(self):
        for m in getattr(self, "pamir_mirnas", []):
            self.records.append({
                "t": "pamir", "n": m,
                "s": "PV-miRNA · plant antiviral miRNA",
                "u": "/pamirdb/",
            })

    def emit_platform_stats(self):
        """docs/data/platform_stats.json —— 门户统计带数据源（轻量文件，随月更自动刷新）"""
        st = {}
        try:
            ss = json.loads((ROOT / "docs/data/site_stats.json").read_text(encoding="utf-8"))
            for k in ("reference_records", "species", "symptom_photos",
                      "vector_host_pairs", "papers_tracked", "onekp_samples"):
                if isinstance(ss.get(k), int):
                    st[k] = ss[k]
        except Exception:
            pass
        st["reference_records"] = st.get("reference_records") or sum(i["ref"] for i in self.sp.values())
        st["species"] = st.get("species") or len(self.sp)
        st["full_sequences"] = sum(i["full"] for i in self.sp.values())
        if getattr(self, "primer_designs", 0):
            st["primer_designs"] = self.primer_designs
        if getattr(self, "papers", None) is not None:
            st["ai_curated_papers"] = len(self.papers)
        if getattr(self, "gene_total", 0):
            st["immune_genes"] = self.gene_total
        if getattr(self, "compound_total", 0):
            st["compounds"] = self.compound_total
        if getattr(self, "pamir_predictions", 0):
            st["pv_mirna_predictions"] = self.pamir_predictions
        # PV-miRNA 预测口径：v7 预计算全量集（11,006）优先，sqlite 仅是本地检索库
        try:
            s = (ROOT / "docs/genes/data/pamirdb_v7_data.js").read_text(encoding="utf-8")
            m = re.search(r"=\s*(\{.*\})\s*;?\s*$", s, re.S)
            if m:
                d = json.loads(m.group(1))
                if isinstance(d.get("total"), int):
                    st["pv_mirna_predictions"] = d["total"]
                elif isinstance(d.get("rows"), list):
                    st["pv_mirna_predictions"] = len(d["rows"])
        except Exception:
            pass
        try:
            e = json.loads((ROOT / "docs/eve/data/eve_landscape.json").read_text(encoding="utf-8"))
            ov = e.get("overview", {})
            if ov.get("loci") is not None:
                st["eve_loci"] = ov["loci"]
            if ov.get("host_families") is not None:
                st["eve_host_families"] = ov["host_families"]
        except Exception:
            pass
        try:
            s = json.loads((ROOT / "14.rvpsd_structures/webapp/data/structures_index.json").read_text(encoding="utf-8"))
            n = s.get("count_proteins") if isinstance(s, dict) else (len(s) if isinstance(s, list) else None)
            if n:
                st["rvpsd_models"] = n
        except Exception:
            pass
        out = ROOT / "docs" / "data" / "platform_stats.json"
        tmp = out.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "stats": st}, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, out)
        print(f"[OK] {out.relative_to(ROOT)}  stats={len(st)}")

    def sort_and_write(self, t0):
        self.emit_virus_records()
        self.emit_structures()
        self.emit_pamir_mirnas()
        self.emit_orphans()
        self.emit_platform_stats()

        order = {t: i for i, t in enumerate(TYPE_ORDER)}

        def score(rec):
            return -sum(v for v in (rec.get("c") or {}).values() if isinstance(v, int))

        self.records.sort(key=lambda r: (order.get(r["t"], 99), score(r), r["n"].lower()))

        counts = Counter(r["t"] for r in self.records)
        meta = {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": len(self.records),
            "counts": {t: counts[t] for t in TYPE_ORDER if counts[t]},
            "sources": self.sources,
            "warnings": self.warnings[:40],
            "schema": {"t": "type", "n": "label", "a": "aliases", "s": "sublabel",
                       "u": "primary url", "x": "extra module links", "c": "per-module counts",
                       "img": "thumbnail (virus with photos)"},
        }
        payload = {"meta": meta, "records": self.records}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, OUT)
        size_mb = OUT.stat().st_size / 1e6
        print(f"[OK] {OUT.relative_to(ROOT)}  records={len(self.records)}  size={size_mb:.2f} MB  elapsed={time.time()-t0:.1f}s")
        for t in TYPE_ORDER:
            if counts[t]:
                print(f"     {t:<10} {counts[t]:>6}")
        if self.warnings:
            print("[WARNINGS]")
            for w in self.warnings[:40]:
                print("  -", w)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    b = IndexBuilder()
    b.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
