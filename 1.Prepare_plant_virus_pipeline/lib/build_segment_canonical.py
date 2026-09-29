#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_segment_canonical.py — 节段名规范层（把"一次性批改"变成可复算的数据列）

现状机制（历史做法，脆弱点）：
  1) F2_classify_segmented.py 的 normalize_segment_names() 做基础归一；
  2) 一次性脚本 normalize_segments.py / push_segment_norm.py 按"物种内主导风格"批量改写
     （DB Info 854 处、服务器 ref_info 792 行）——改完没有留痕，也无从复算；
  3) F3 按长度做质量校验（同名不同长按质量取舍）。
  结果：`Segment_std` 只是"当时改对了"，换一批数据/重跑就回到 173 种写法混写，
  且"标题写了 segment 但段列为空"（如 NC_003749.1）、"同科跨属风格不一致"
  （Oryzavirus 用 RNA1-10、同科 Fijivirus 用 S1-S10）无人自动发现。

本脚本输出（--apply 只另存新文件，不改原文件）：
  <out>/segment_canonical.tsv   Accession → Segment_Std / Style / Source / Note
  <out>/segment_report.md       风格归并、从标题补段、重复、缺段、跨属风格不一致
  <out>/<info>.segnorm.tsv      Info + Segment_Std2 / Segment_Style 两列

规则：
  - 风格按**物种内主导**（该物种自身记录的多数前缀），保留既定惯例：
    Bromoviridae 的 RNA1-3、Fijivirus/Phytoreovirus 的 S1-S10、单字母 L/M/S、DNA-A/DNA-B；
  - 段列为空但标题里出现节段记号时，从标题补齐（并标注来源 title）；
  - 纯函数、可复算；不删记录、不改行数。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import polars as pl                                       # noqa: E402

TSV = "\t"
# 标题里的节段记号：segment 9 / segment S1 / RNA3 / RNA5a / DNA-A / DNA A
TITLE_SEG = re.compile(r"(?i)\b(?:segment|rna|dna)[\s\-_]*(-[a-z]\b|[a-z]\d{1,2}\b|\d{1,2}[a-z]?\b|[a-z]\b)")
# 段标签解析：前缀 + 核心
PARSE = re.compile(r"^(?P<pfx>DNA|RNA|S|M|L)?[\s\-_]*(?P<core>-?[A-Z]?\d{1,2}[A-Za-z]?)$", re.I)
LETTER_ONLY = re.compile(r"^[LMSC]$", re.I)
# 风格"具体度"排序：只允许平级或升级改写，禁止降级
RANK = {"DNA#": 4, "LETTER": 4, "S#": 3, "RNA#": 3, "OTHER": 2, "NUM#": 1, "": 0}


def parse_label(raw: str) -> tuple[str, str]:
    """返回 (风格, 核心)。风格 ∈ {RNA#, S#, DNA-#, LETTER, NUM#, OTHER, ''}"""
    s = (raw or "").strip()
    if not s:
        return "", ""
    if LETTER_ONLY.match(s):
        return "LETTER", s.upper()
    m = PARSE.match(s)
    if not m:
        return "OTHER", s
    pfx = (m.group("pfx") or "").upper()
    core = m.group("core").upper().replace("-", "")
    if pfx == "DNA":
        return "DNA#", core.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") or core
    if pfx == "S":
        return "S#", core
    if pfx == "RNA":
        return "RNA#", core
    if pfx == "M" or pfx == "L":
        return "LETTER", pfx
    return "NUM#", core          # 裸数字 3 / 10 / 5A


def core_of(raw: str) -> str:
    """段身份（跨写法可比）：DNA-A→A；RNA3→3；S7→7；5a→5A；L→L"""
    st, core = parse_label(raw)
    if st == "LETTER":
        return core
    if st == "DNA#" and core:
        return core.upper()
    m = re.search(r"([A-Z]?\d+[A-Z]?)", core.upper())
    return m.group(1) if m else core.upper()


def render(style: str, core: str) -> str:
    if style == "LETTER":
        return core.upper()
    if style == "DNA#":
        return "DNA-" + core.upper()
    if style == "S#":
        return "S" + core
    if style == "RNA#":
        return "RNA" + core
    if style == "NUM#":
        return core
    return core


def main():
    ap = argparse.ArgumentParser(description="节段名规范层（只读；--apply 另存新文件）")
    ap.add_argument("--info", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    df = pl.read_csv(args.info, separator=TSV, infer_schema_length=0, truncate_ragged_lines=True)
    cols = {c.lower(): c for c in df.columns}
    raw_col = cols.get("segment_std") or cols.get("segment")
    title_col = cols.get("genbank_title")
    sp_col = cols.get("species_canonical") or cols.get("species_ictv")
    tx_col = cols.get("taxid")

    rows = df.select([c for c in (cols.get("accession"), tx_col, sp_col, raw_col, title_col) if c]).to_dicts()
    by_species = defaultdict(list)
    for r in rows:
        by_species[(r.get(tx_col), r.get(sp_col))].append(r)

    out, style_conflicts, from_title, dup_rows = [], [], [], []
    for (tx, sp), recs in by_species.items():
        # 1) 物种内主导风格（只统计非空标签）
        styles = Counter(parse_label(r.get(raw_col))[0] for r in recs if parse_label(r.get(raw_col))[0])
        if styles:
            dom = styles.most_common(1)[0][0]
        else:
            dom = ""
        if len(styles) > 1 and dom:
            style_conflicts.append({"Taxid": tx, "Species": sp, "styles": ";".join(sorted(styles)),
                                    "dominant": dom, "n_records": len(recs)})
        # 2) 逐条渲染
        seen = Counter()
        for r in recs:
            raw = r.get(raw_col) or ""
            st, core = parse_label(raw)
            src, note = "kept", ""
            if not core and title_col:
                m = TITLE_SEG.search(str(r.get(title_col) or ""))
                if m:
                    tok = m.group(1)
                    core = core_of(tok if tok.upper().startswith(("S", "RNA", "DNA")) else tok)
                    st, src, note = parse_label(tok)[0] or dom, "title", "从标题补段"
                    from_title.append({"Accession": r.get(cols.get("accession")), "Taxid": tx,
                                       "Species": sp, "raw": raw, "from_title": tok,
                                       "Title": str(r.get(title_col))[:110]})
            if not core:
                out.append({"Accession": r.get(cols.get("accession")), "Segment_Std2": "",
                            "Style": "", "Source": "none", "Note": ""})
                continue
            use_style = dom or st or "NUM#"
            # 不降级原则：记录自身写法若比目标风格更具体（RNA2 > 2、DNA-A > A），
            # 保留自身写法。避免"把规范的 RNA2 改写成裸数字 2"这类信息损失。
            if st and RANK.get(use_style, 0) < RANK.get(st, 0):
                use_style = st
            canon = render(use_style, core) if st != "OTHER" else (raw or "")
            # 信息不得丢失：改写后若原标签里的字母/数字被吃掉（DNA U2→DNA-2、S7→7），
            # 说明把不同组份混为一谈，一律保留原样并标注。
            def _alnum(x):
                return set(ch for ch in str(x).lower() if ch.isalnum())
            if st != "OTHER" and raw and not _alnum(raw) <= _alnum(canon):
                canon = raw.strip()
                note = (note + "; 保留原写法(改写会丢信息)").strip("; ")
            if raw and canon != raw.strip():
                src, note = ("style", f"{raw.strip()} → {canon}") if src == "kept" else (src, note)
            if st and dom and st != dom:
                note = (note + f"; 风格由 {st} 归到 {dom}").strip("; ")
            seen[core] += 1
            out.append({"Accession": r.get(cols.get("accession")), "Segment_Std2": canon,
                        "Style": use_style, "Source": src, "Note": note})
        for core, n in seen.items():
            if n > 1:
                dup_rows.append({"Taxid": tx, "Species": sp, "core": core, "n": n})

    res = pl.DataFrame(out)
    res.write_csv(os.path.join(args.out, "segment_canonical.tsv"), separator=TSV)
    changed = res.filter(pl.col("Note").str.contains("→") | (pl.col("Source") == "title"))
    with open(os.path.join(args.out, "segment_report.md"), "w", encoding="utf-8") as f:
        f.write(f"# 节段名规范报告\n\n- {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"- 记录 {res.height} 行；有段标签 {int((res['Segment_Std2']!='').sum())}，"
                f"其中**从标题补段 {len(from_title)}**、**写法改写 {changed.height}**\n"
                f"- 物种内曾出现多种风格的物种：**{len(style_conflicts)}**（已按主导风格归并）\n"
                f"- 同一物种同一段出现多条：{len(dup_rows)}（多簇代表属正常，供核对）\n")
    print(f"记录 {res.height} | 有标签 {int((res['Segment_Std2']!='').sum())} | "
          f"从标题补段 {len(from_title)} | 改写 {changed.height} | 曾风格混用物种 {len(style_conflicts)}")
    for r in style_conflicts[:5]:
        print("   混用:", str(r["Species"])[:36], r["styles"], "→", r["dominant"])
    for r in from_title[:5]:
        print("   补段:", r["Accession"], "|", str(r["Title"])[:56])

    if args.apply:
        m = dict(zip(res["Accession"].to_list(), zip(res["Segment_Std2"].to_list(), res["Style"].to_list())))
        d2 = df.with_columns([
            pl.Series("Segment_Std2", [m.get(a, ("", ""))[0] for a in df[cols["accession"]].to_list()]),
            pl.Series("Segment_Style", [m.get(a, ("", ""))[1] for a in df[cols["accession"]].to_list()]),
        ])
        dst = os.path.join(args.out, os.path.basename(args.info).replace(".tsv", ".segnorm.tsv"))
        d2.write_csv(dst, separator=TSV)
        print("已写:", dst, "（原文件未改动）")


if __name__ == "__main__":
    main()
