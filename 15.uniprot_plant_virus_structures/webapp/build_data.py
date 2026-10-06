# -*- coding: utf-8 -*-
"""15.uniprot_plant_virus_structures/webapp 数据生成：TSV -> data/*.json。

产出：data/stats.json（面板汇总）、data/proteins.json（蛋白级索引，压缩键）、
      data/virus_coverage.json（病毒级覆盖表）。
重跑幂等；数据源变更后重跑即可。
"""
import csv
import json
import collections
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)

COMBO_LABEL = {
    "PDB": "PDB 实验结构", "AFDB": "AFDB 自身预测", "RVPSD": "RVPSD AF2",
    "BFVD": "BFVD 同源(簇代表)", "SELF": "自建折叠", "": "无任何结构",
}


def main():
    rows = list(csv.DictReader(open(MODULE / "structures_index.tsv", encoding="utf-8"), delimiter="\t"))
    cov = list(csv.DictReader(open(MODULE / "virus_coverage.tsv", encoding="utf-8"), delimiter="\t"))
    N = len(rows)

    combos = {}
    for r in rows:
        key = ",".join(sorted(r["sources"].split(","))) if r["sources"] else ""
        combos[key] = combos.get(key, 0) + 1
    own = sum(v for k, v in combos.items() if set(k.split(",")) & {"PDB", "AFDB", "RVPSD", "SELF"})
    anyv = N - combos.get("", 0)
    by_src = collections.Counter()
    for k, v in combos.items():
        for s in (k.split(",") if k else []):
            by_src[s] += v

    species = {}
    for r in rows:
        o = species.setdefault(r["organism"], {"n": 0, "own": 0, "any": 0})
        o["n"] += 1
        srcs = set(r["sources"].split(",")) if r["sources"] else set()
        if srcs & {"PDB", "AFDB", "RVPSD", "SELF"}:
            o["own"] += 1
        if srcs:
            o["any"] += 1
    sp_full = sum(1 for v in species.values() if v["own"] == v["n"])
    sp_part = sum(1 for v in species.values() if 0 < v["own"] < v["n"])
    sp_zero = sum(1 for v in species.values() if v["own"] == 0)

    # pending 分层（与 pending_prediction.tsv 同口径）
    p3 = p1 = p2 = p4 = 0
    for r in rows:
        if r["sources"]:
            continue
        L = int(r["length"]) if r["length"].isdigit() else 0
        if L > 2700:
            p3 += 1
        elif L < 50:
            p4 += 1
        elif r["reviewed"] == "reviewed":
            p1 += 1
        else:
            p2 += 1

    stats = {
        "built": datetime.now().isoformat(timespec="seconds"),
        "uniprot_release": "2026_03",
        "query": "(taxonomy_id:10239) AND virus_host_id:33090 AND virus_host_id:35493",
        "proteins": N,
        "species": len(species),
        "reviewed": sum(1 for r in rows if r["reviewed"] == "reviewed"),
        "own": own, "any": anyv, "none": combos.get("", 0),
        "own_pct": round(own / N * 100, 1), "any_pct": round(anyv / N * 100, 1),
        "by_src": dict(sorted(by_src.items(), key=lambda kv: -kv[1])),
        "combos": {COMBO_LABEL.get(k, k): v for k, v in
                   sorted(combos.items(), key=lambda kv: -kv[1])},
        "species_full_own": sp_full, "species_partial_own": sp_part, "species_zero_own": sp_zero,
        "species_any": len(species) - sp_zero,
        "pending": {"P1-reviewed(≤2700aa)": p1, "P2-unreviewed(≤2700aa)": p2,
                    "P3-多聚蛋白(>2700aa,需切分)": p3, "P4-极小(<50aa)": p4},
        "pipeline_notes": {
            "sifts_delta": len(open(MODULE / "unique_pdb_ids_sifts_delta.txt", encoding="utf-8").read().split()),
            "afdb_probe": "435 hit / 4,375 miss（4,810 全探测）",
            "bfvd_hit": by_src.get("BFVD", 0),
            "rvpsd_bridge": "GenBank ProteinId 精确桥接 9,122 对",
            "removed_alga": "1,993 条 / 8 物种（removed_green_alga_viruses.tsv）",
            "gcva_batch": 6,
        },
    }
    json.dump(stats, open(DATA / "stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    proteins = [{"a": r["accession"], "e": r["entry"], "rv": r["reviewed"], "o": r["organism"],
                 "L": r["length"], "s": sorted(r["sources"].split(",")) if r["sources"] else [],
                 "p": r["pdb_ids"], "af": r["afdb_model"], "rv": r["rvpsd_model"],
                 "sf": r.get("selffold_model", ""), "bf": r.get("bfvd_cluster", "")}
                for r in rows]
    json.dump(proteins, open(DATA / "proteins.json", "w", encoding="utf-8"), ensure_ascii=False)

    json.dump(cov, open(DATA / "virus_coverage.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"stats: proteins={N} own={own} any={anyv} species={len(species)} | "
          f"proteins.json={round((DATA/'proteins.json').stat().st_size/1e6,1)}MB")


if __name__ == "__main__":
    main()
