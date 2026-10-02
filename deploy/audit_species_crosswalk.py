#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨库物种互联审计（taxid 锚定）——防 NCBI 名/ICTV 名漂移造成的数据缺口。

背景：参考库（NCBI 来源，带 Taxid）与下游各库（引物/媒介/照片）以名字为键，
NCBI 名与 ICTV 规范名不一致或某个库单独重建时，物种会静默丢失（典型案例：
TSWV / Orthotospovirus tomatomaculae 在参考库完好却在引物库整体缺失）。
本工具以 Plant_Virus_Ref.Info.tsv 的 Taxid 为锚，生成统一交叉表并核对每个库
的覆盖情况，任何一层重建后跑一遍即可发现新缺口。

用法（服务器默认路径；本地可传参覆盖）:
  python3 audit_species_crosswalk.py                # 报告 + 写 species_crosswalk.tsv
  python3 audit_species_crosswalk.py --strict       # 有关键缺口时退出码 1（可挂 CI/管线）
  python3 audit_species_crosswalk.py --migrate      # 顺带给 primer taxonomy 补 taxid 列（先备份）

输出:
  docs/data/species_crosswalk.tsv 一行一个规范物种:
    ictv_name, taxids(;), ncbi_names(;), ref_records, ref_complete,
    in_primer_taxonomy, primers_count, in_vector_db, in_photo_db, in_symptom_db
"""

import argparse
import csv
import json
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

DEFAULT_ROOT = "/opt/plant_virus_db/plant_virus_db_pipeline"
LOCAL_FALLBACK = Path(__file__).resolve().parent.parent


def candidates(root, rel):
    return [Path(root) / rel,
            Path(root).parent / rel,
            LOCAL_FALLBACK / rel,
            LOCAL_FALLBACK.parent / rel]


def first_existing(root, rel):
    for p in candidates(root, rel):
        if p.exists():
            return p
    return None


def load_ref(root):
    """参考层交叉表: 规范名 -> {taxids, ncbi_names, records, complete}。"""
    p = first_existing(root, "docs/data/Plant_Virus_Ref.Info.tsv")
    if not p:
        sys.exit(f"参考交叉表不存在: {p}")
    species = {}
    with open(p, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            ictv = (r.get("Species_ICTV") or "").strip()
            ncbi = (r.get("Species_NCBI") or "").strip()
            taxid = (r.get("Taxid") or "").strip()
            name = ictv if ictv and not ictv.startswith("PENDING") else ncbi
            if not name or name.startswith("PENDING"):
                continue
            s = species.setdefault(name, {"taxids": set(), "ncbi": set(),
                                          "records": 0, "complete": 0})
            if taxid:
                s["taxids"].add(taxid)
            if ncbi and ncbi != name:
                s["ncbi"].add(ncbi)
            s["records"] += 1
            if "Complete" in (r.get("Category") or ""):
                s["complete"] += 1
    return species


def load_name_map(root):
    p = first_existing(root, "docs/data/name_mapping.tsv")
    if not p:
        return {}
    m = {}
    with open(p, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            m[row.get("Lookup_Key", "").strip().lower()] = row
    return m


def load_primer(root, db_path=None):
    p = db_path or first_existing(root, "primer_design_server/primer_database.db")
    if not p or not Path(p).exists():
        return None
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT species_name, COUNT(*) FROM primers GROUP BY species_name")
    primers = dict(c.fetchall())
    c.execute("SELECT species_name, taxid FROM taxonomy" if _has_col(c, "taxonomy", "taxid")
              else "SELECT species_name, NULL FROM taxonomy")
    taxonomy = {r[0].strip(): r[1] for r in c.fetchall()}
    conn.close()
    return {"primers": primers, "taxonomy": taxonomy, "path": str(p)}


def _has_col(cursor, table, col):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cursor.fetchall())


def canonical_bridges(ref, name_map):
    """所有别名/俗名/NCBI名 -> 规范名（供名字型库桥接）。"""
    bridges = defaultdict(set)
    for ictv in ref:
        bridges[ictv.lower()].add(ictv)
    for row in name_map.values():
        ictv = (row.get("ICTV_Name") or "").strip()
        if not ictv or ictv not in ref:
            continue
        for key in (row.get("Lookup_Key"), row.get("Common_Name"), row.get("Abbreviation")):
            k = (key or "").strip().lower()
            if len(k) >= 3:
                bridges[k].add(ictv)
    return bridges


def bridge_set(names, bridges):
    out = set()
    for n in names or []:
        out |= bridges.get((n or "").strip().lower(), set())
    return out


def load_vector(root, bridges):
    p = first_existing(root, "8.plant-insect/virus_vector_merged.json")
    if not p:
        return set()
    d = json.loads(p.read_text(encoding="utf-8"))
    found = set()
    for v in d.get("viruses") or []:
        names = [v.get("ictv_name") or "", v.get("canonical_name") or ""]
        names += list(v.get("matched_names") or [])
        found |= {c for c in bridge_set(names, bridges) if c in ref_species_cache}
    return found


def load_photos(root, bridges):
    out = {"photos": set(), "symptoms": set()}
    for rel, key in (("docs/data/unified_gallery.json", "photos"),
                     ("docs/data/symptom_table.json", "symptoms")):
        p = first_existing(root, rel)
        if not p:
            continue
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for it in items or []:
            found = bridge_set([it.get("virus_ictv") or it.get("virus") or ""], bridges)
            out[key] |= {c for c in found if c in ref_species_cache}
    return out


ref_species_cache = set()


def main():
    global ref_species_cache
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--primer-db", default=None)
    ap.add_argument("--out", default=None, help="交叉表输出路径（默认 docs/data/species_crosswalk.tsv）")
    ap.add_argument("--strict", action="store_true", help="有关键缺口时退出码 1")
    ap.add_argument("--migrate", action="store_true", help="给 primer taxonomy 补 taxid 列并回填（先备份）")
    ap.add_argument("--add-aliases", action="store_true",
                    help="把参考层 NCBI 名/规范名补进 name_mapping.tsv（C 类修复，追加不覆盖）")
    args = ap.parse_args()
    root = args.root

    ref = load_ref(root)
    ref_species_cache = set(ref)
    name_map = load_name_map(root)
    bridges = canonical_bridges(ref, name_map)
    primer = load_primer(root, args.primer_db)
    vector = load_vector(root, bridges)
    media = load_photos(root, bridges)

    # 上一轮交叉表：origin=legacy 的遗留物种继续立档；首次见到的未解释物种
    # 本轮自动立档（origin=legacy_primer_db），之后 B 类只报"新出现、未甄别"的
    prev_cross = {}
    prev_p = first_existing(root, "docs/data/species_crosswalk.tsv")
    if prev_p and prev_p.exists():
        with open(prev_p, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                prev_cross[r["ictv_name"]] = r
    prev_legacy = {n for n, r in prev_cross.items()
                   if r.get("origin") == "legacy_primer_db"}
    unexplained = set()
    if primer:
        unexplained = {n for n in primer["taxonomy"] if n not in ref}
    legacy_known = {n for n in prev_legacy
                    if primer and n in primer["taxonomy"]} | unexplained
    new_unarchived = sorted(unexplained - set(prev_cross)) if primer else []
    if primer:
        legacy_known = {n for n in legacy_known
                        if n in primer["taxonomy"] and n not in ref}

    # C 类修复：参考层 NCBI 名/规范名/遗留物种名补进 name_mapping（追加，不覆盖）
    if args.add_aliases:
        alias_p = first_existing(root, "docs/data/name_mapping.tsv")
        existing = set(name_map)
        add = []

        def _add_row(key, ictv, common):
            k = (key or "").strip().lower()
            if len(k) >= 3 and k not in existing:
                existing.add(k)
                add.append({"Lookup_Key": k, "ICTV_Name": ictv,
                            "Common_Name": common, "Abbreviation": ""})

        for ictv, s in ref.items():
            for n in s["ncbi"]:
                _add_row(n, ictv, n)
            _add_row(ictv, ictv, ictv)
        for n in legacy_known:
            _add_row(n, n, n)
        if add and alias_p:
            with open(alias_p, "a", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["Lookup_Key", "ICTV_Name",
                                                  "Common_Name", "Abbreviation"],
                                   delimiter="\t")
                w.writerows(add)
            print(f"[add-aliases] name_mapping.tsv 追加 {len(add)} 行 -> {alias_p}")
        elif not add:
            print("[add-aliases] 无需追加（别名已全覆盖）")
        for r in add:
            name_map[r["Lookup_Key"]] = r

    # 名字型库（引物库在 taxid 迁移前）按规范名直接比对；未命中再走别名桥
    def primer_state(ictv):
        if not primer:
            return (False, 0, "")
        tax = primer["taxonomy"]
        if ictv in tax:
            return (True, primer["primers"].get(ictv, 0), tax[ictv] or "")
        alt = bridge_set([ictv], bridges) - {ictv}
        for a in alt:
            if a in tax:
                return (True, primer["primers"].get(a, 0), tax[a] or "")
        return (False, 0, "")

    rows, missing_primer, no_alias = [], [], []
    for ictv, s in sorted(ref.items()):
        in_tax, n_prim, taxid_col = primer_state(ictv)
        taxids = ";".join(sorted(s["taxids"]))
        rows.append({
            "ictv_name": ictv,
            "taxids": taxids,
            "ncbi_names": ";".join(sorted(s["ncbi"])),
            "ref_records": s["records"],
            "ref_complete": s["complete"],
            "in_primer_taxonomy": int(in_tax),
            "primers_count": n_prim,
            "taxid_in_primer_db": taxid_col,
            "in_vector_db": int(ictv in vector),
            "in_photo_db": int(ictv in media["photos"]),
            "in_symptom_db": int(ictv in media["symptoms"]),
            "origin": "reference",
        })
        if s["complete"] > 0 and not in_tax:
            missing_primer.append((ictv, s["complete"], n_prim))
        if ictv not in name_map and ictv.lower() not in name_map:
            no_alias.append(ictv)
    # 遗留物种立档（参考层已无、引物数据保留，origin=legacy_primer_db）
    for ictv in sorted(legacy_known):
        in_tax, n_prim, taxid_col = primer_state(ictv)
        prev = prev_cross.get(ictv, {})
        rows.append({
            "ictv_name": ictv,
            "taxids": prev.get("taxids", ""),
            "ncbi_names": prev.get("ncbi_names", ""),
            "ref_records": prev.get("ref_records", "0"),
            "ref_complete": prev.get("ref_complete", "0"),
            "in_primer_taxonomy": int(in_tax),
            "primers_count": n_prim,
            "taxid_in_primer_db": taxid_col,
            "in_vector_db": int(ictv in vector),
            "in_photo_db": int(ictv in media["photos"]),
            "in_symptom_db": int(ictv in media["symptoms"]),
            "origin": "legacy_primer_db",
        })
        if ictv not in name_map and ictv.lower() not in name_map:
            no_alias.append(ictv)
    if primer:
        # B 类 = 引物库里既不在参考层、也未在遗留档案中立档的未知物种
        known = set(ref) | legacy_known
        missing_ref = sorted(n for n in primer["taxonomy"] if n not in known)

    # ---- 交叉表落盘 ----
    out = Path(args.out) if args.out else first_existing(root, "docs/data")
    out = Path(out) / "species_crosswalk.tsv" if out.is_dir() else Path(out)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    # ---- 报告 ----
    n_multi = sum(1 for s in ref.values() if len(s["taxids"]) > 1)
    print(f"参考层规范物种: {len(ref)}（{n_multi} 个对应多个 taxid）")
    print(f"primer taxonomy: {len(primer['taxonomy']) if primer else 'N/A'} | "
          f"vector 覆盖: {len(vector)} | 照片覆盖: {len(media['photos'])} | 症状覆盖: {len(media['symptoms'])}")
    print(f"交叉表 -> {out}")
    print()
    print(f"== A. 参考库有完整基因组、引物库缺失（{len(missing_primer)} 个）==")
    for n, comp, nprim in missing_primer[:30]:
        print(f"  - {n}  (complete={comp}, primers={nprim})")
    if len(missing_primer) > 30:
        print(f"  ... 另 {len(missing_primer) - 30} 个")
    print(f"== B. 引物库有、参考库没有（{len(missing_ref)} 个）==")
    for n in missing_ref[:15]:
        print(f"  - {n}")
    print(f"== C. 参考物种在 name_mapping 无任何别名条目（{len(no_alias)} 个，检索兜底变弱）==")
    for n in no_alias[:10]:
        print(f"  - {n}")

    # --migrate: primer taxonomy 补 taxid
    if args.migrate and primer:
        dbp = Path(primer["path"])
        bak = dbp.with_suffix(".db.bak_taxid_" + time.strftime("%Y%m%d_%H%M%S"))
        shutil.copy2(dbp, bak)
        print(f"\n[migrate] 备份 -> {bak}")
        conn = sqlite3.connect(str(dbp))
        c = conn.cursor()
        if not _has_col(c, "taxonomy", "taxid"):
            c.execute("ALTER TABLE taxonomy ADD COLUMN taxid TEXT DEFAULT ''")
        updated = 0
        for r in rows:
            if r["taxids"] and r["in_primer_taxonomy"]:
                c.execute("UPDATE taxonomy SET taxid=? WHERE species_name=?",
                          (r["taxids"], r["ictv_name"]))
                updated += c.rowcount
        conn.commit()
        conn.close()
        print(f"[migrate] taxonomy.taxid 回填 {updated} 行")

    if args.strict and (missing_primer or missing_ref):
        print(f"\n[strict] 存在关键缺口: A={len(missing_primer)}, B={len(missing_ref)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
