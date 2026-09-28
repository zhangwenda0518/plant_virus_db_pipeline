#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_species_canonical.py — 规范种名落库（把"手打补丁"变成数据列）

背景：参考集 Info 的 `Species_ICTV` 常填**俗名**（"Tomato necrotic spot tospovirus"），
权威 ICTV 二名在 VMR（"Orthotospovirus tomatonecromaculae"）。同一病毒被拆成两个
物种键后，RdRP 等记录会落在其中一个键上，另一个键就显示"缺记录"（TSWV 家族即实例）。
原先靠在 5 个生成器脚本里用 `wire_canonical.py` 各打 1 行补丁，脆弱且不可复现。

本脚本输出：
  <out>/species_canonical.tsv   accession → canonical / source / old_key（每行一条）
  <out>/canonical_summary.md    覆盖率、键分裂、未命中清单
  <out>/Plant_Virus_Ref.Info.canon.tsv   （仅 --apply）Info + 两列新字段，**不改原文件**

用法：
  python lib/build_species_canonical.py \
      --info ../docs/data/Plant_Virus_Ref.Info.tsv \
      --vmr  "D:/.../VMR_MSL41.xlsx" --out /tmp/canon --apply
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import polars as pl                                            # noqa: E402
from pvcore import write_tsv_safe                              # noqa: E402

ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}


def norm(name: str) -> str:
    """名称归一：小写、去标点/空格、罗马数字转阿拉伯、去尾号（-1/_1) """
    s = (name or "").strip().lower()
    if not s:
        return ""
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "", s)
    s = re.sub(r"(?<=[a-z])(i{1,3}|iv|v|vi)$", lambda m: ROMAN.get(m.group(1), m.group(1)), s)
    s = re.sub(r"[_-]?\d+$", "", s)
    return s


def load_vmr(path: str) -> list[dict]:
    if path.lower().endswith((".xlsx", ".xls")):
        import pandas as pd
        df = pd.read_excel(path, sheet_name="VMR MSL41", dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        return df.to_dict("records")
    return pl.read_csv(path, separator="\t", infer_schema_length=0,
                       truncate_ragged_lines=True).to_dicts()


def build_alias(rows: list[dict]) -> tuple[dict, dict, set]:
    """返回 (别名→规范名, 规范名归一→规范名, 全部规范名集合)"""
    alias, canon_by_norm, all_canon = {}, {}, set()
    for r in rows:
        sp = str(r.get("Species") or "").strip()
        if not sp:
            continue
        all_canon.add(sp)
        canon_by_norm[norm(sp)] = sp
        alias[norm(sp)] = sp                                     # 二名本身
        for col in ("Virus name(s)", "Virus name abbreviation(s)"):
            for part in re.split(r"[;,]", str(r.get(col) or "")):
                p = part.strip()
                if len(p) >= 4:                                   # 太短的缩写不可靠
                    alias.setdefault(norm(p), sp)
    return alias, canon_by_norm, all_canon


def vmr_accession_map(rows: list[dict]) -> dict:
    """VMR 'Virus GENBANK accession' → 规范种名。单元格可能是 'L: KT984754; M: KT984753'"""
    acc2sp = {}
    for r in rows:
        sp = str(r.get("Species") or "").strip()
        cell = str(r.get("Virus GENBANK accession") or "")
        for part in re.split(r"[;,]", cell):
            tok = part.split(":")[-1].strip() if ":" in part else part.strip()
            m = re.match(r"^([A-Za-z]{1,4}\d{5,})", tok)
            if m and sp:
                acc2sp[m.group(1).upper()] = sp
    return acc2sp


def main():
    ap = argparse.ArgumentParser(description="规范种名落库（只读原文件；--apply 写新文件）")
    ap.add_argument("--info", required=True)
    ap.add_argument("--vmr", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--apply", action="store_true", help="另存 <info>.canon.tsv（不覆盖原文件）")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    rows = load_vmr(args.vmr)
    alias, _, all_canon = build_alias(rows)
    acc2sp = vmr_accession_map(rows)
    print(f"VMR: {len(rows)} 行, 规范种名 {len(all_canon)}, 别名 {len(alias)}, accession 锚点 {len(acc2sp)}")

    info = pl.read_csv(args.info, separator="\t", infer_schema_length=0, truncate_ragged_lines=True)
    keys = [c for c in ("Species_ICTV", "Species_NCBI", "VMR_Species") if c in info.columns]

    out = []
    for r in info.iter_rows(named=True):
        acc = str(r.get("Accession") or "").split(".")[0].upper()
        canonical, src = "", ""
        if acc in acc2sp:
            canonical, src = acc2sp[acc], "vmr_accession"
        if not canonical:
            for k in keys:
                n = norm(str(r.get(k) or ""))
                if n and n in alias:
                    canonical, src = alias[n], f"alias:{k}"
                    break
        old_key = str(r.get("Species_ICTV") or "")
        out.append({"Accession": r.get("Accession"), "canonical": canonical,
                    "by": src, "old_key": old_key,
                    "taxid": str(r.get("Taxid") or "")})
    res = pl.DataFrame(out)

    # 归属规则：同科内种加词唯一匹配（补 alias 未命中者）
    extra = 0
    if "VMR_Genus" in info.columns:
        genus_of = dict(zip(info["Accession"].to_list(), info["VMR_Genus"].to_list()))
        canon_by_epithet = {}
        for sp in all_canon:
            parts = sp.split()
            if len(parts) >= 2:
                canon_by_epithet.setdefault((parts[0], norm(parts[1])), sp)
        fixed = []
        for r in res.iter_rows(named=True):
            if r["canonical"]:
                fixed.append(r); continue
            sp = (r["old_key"] or "").strip().split()
            g = str(genus_of.get(r["Accession"]) or "").strip()
            if len(sp) >= 2 and g:
                hit = canon_by_epithet.get((g, norm(sp[-1])))
                if hit and norm(hit) != norm(r["old_key"]):
                    r = dict(r, canonical=hit, by="epithet"); extra += 1
            fixed.append(r)
        res = pl.DataFrame(fixed)

    res = res.with_columns([
        pl.col("canonical").fill_null(""),
        pl.col("by").fill_null(""),
    ])
    cov = (res["canonical"] != "").sum()
    splits = (res.filter(pl.col("canonical") != "")
                 .with_columns(pl.col("canonical").alias("_c"))
                 .group_by("_c")
                 .agg([pl.col("old_key").n_unique().alias("n_old_keys"),
                       pl.col("taxid").n_unique().alias("n_taxid")])
                 .filter((pl.col("n_old_keys") > 1) | (pl.col("n_taxid") > 1))
                 .sort("n_old_keys", descending=True))

    write_tsv_safe(res.select(["Accession", "canonical", "by", "old_key", "taxid"]),
                   os.path.join(args.out, "species_canonical.tsv"))
    if splits.height:
        write_tsv_safe(splits, os.path.join(args.out, "canonical_key_splits.tsv"))
    unmatched = res.filter(pl.col("canonical") == "").select(["Accession", "old_key"]).head(50)
    write_tsv_safe(unmatched, os.path.join(args.out, "canonical_unmatched.tsv"))

    with open(os.path.join(args.out, "canonical_summary.md"), "w", encoding="utf-8") as f:
        f.write(f"# 规范种名归属报告\n\n- {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"- 记录 {res.height} 行：命中 **{cov}**（{cov/max(res.height,1):.1%}），"
                f"未命中 {res.height - cov}（其中种加词规则补充 {extra}）\n"
                f"- 归并前后：旧键 {res['old_key'].n_unique()} 个 → 规范名 {res.filter(pl.col('canonical')!='')['canonical'].n_unique()} 个\n"
                f"- 仍存在键分裂的规范名：**{splits.height}** 个（见 canonical_key_splits.tsv）\n")
    print(f"记录 {res.height} | 命中 {cov} ({cov/max(res.height,1):.1%}) | 未命中 {res.height-cov} | "
          f"规范名 {res.filter(pl.col('canonical')!='')['canonical'].n_unique()} 个 | 键分裂 {splits.height}")

    if args.apply:
        info2 = pl.read_csv(args.info, separator="\t", infer_schema_length=0, truncate_ragged_lines=True)
        m = dict(zip(res["Accession"].to_list(), zip(res["canonical"].to_list(), res["by"].to_list())))
        canon = [m.get(a, ("", ""))[0] for a in info2["Accession"].to_list()]
        src = [m.get(a, ("", ""))[1] for a in info2["Accession"].to_list()]
        info2 = info2.with_columns([pl.Series("Species_Canonical", canon),
                                    pl.Series("Species_Canonical_Source", src)])
        dst = os.path.join(args.out, os.path.basename(args.info).replace(".tsv", ".canon.tsv"))
        info2.write_csv(dst, separator="\t")
        print(f"已写: {dst}（原文件未改动，请复核后再替换）")


if __name__ == "__main__":
    main()
