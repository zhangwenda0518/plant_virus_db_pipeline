#!/usr/bin/env python3
"""
导出引物数据为 GitHub Pages 静态文件
=====================================
用法:
  python export_primers_static.py --input all_primers_validated.tsv --output primers/

输出:
  primers/
    index.json          — 物种索引 (物种名→各类型引物数)
    stats.json          — 全局统计
    species/             — 每物种详细引物数据 (JSON)
      Abaca_bunchy_top_virus.json
      ...
"""

import argparse, csv, json, sys
from pathlib import Path
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser(description="导出引物静态数据")
    parser.add_argument("--input", required=True, help="all_primers_validated.tsv 路径")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--species-index", default="",
                        help="species_index.tsv (含分类信息, 可选)")
    parser.add_argument("--db", default="",
                        help="primer_database.db (读取 genome_length, 可选)")
    args = parser.parse_args()

    out_dir = Path(args.output)
    species_dir = out_dir / "species"
    species_dir.mkdir(parents=True, exist_ok=True)

    # 加载分类信息
    taxonomy = {}
    if args.species_index and Path(args.species_index).exists():
        with open(args.species_index, 'r') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                sp = row.get("Species", "").strip()
                if sp:
                    taxonomy[sp] = {
                        "family": row.get("Family", ""),
                        "genus": row.get("Genus", ""),
                        "segment": row.get("Segment", ""),
                        "genome_length": row.get("Genome_Length", "")
                    }

    # 从数据库加载 genome_length (优先)
    genome_lens = {}
    if args.db and Path(args.db).exists():
        import sqlite3
        conn = sqlite3.connect(args.db)
        for sp, gl in conn.execute("SELECT species_name, genome_length FROM taxonomy WHERE genome_length > 0"):
            genome_lens[sp] = gl
        conn.close()
    for sp in taxonomy:
        if sp in genome_lens:
            taxonomy[sp]["genome_length"] = str(genome_lens[sp])

    # 按物种分组引物
    by_species = defaultdict(list)
    stats = {"pcr": 0, "qpcr": 0, "degenerate": 0, "tiled": 0, "total_pairs": 0,
             "total_species": 0, "families": set(), "genera": set(),
             "recommended": 0, "usable": 0, "not_recommended": 0}

    with open(args.input, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            sp = row.get("Species", "").strip()
            if not sp: continue
            ptype = (row.get("Type") or "").strip()
            by_species[sp].append({
                "type": ptype,
                "segment": (row.get("Segment") or "").strip(),
                "pair_id": (row.get("Pair_ID") or "").strip(),
                "fwd_seq": (row.get("Fwd_Seq") or "").strip(),
                "rev_seq": (row.get("Rev_Seq") or "").strip(),
                "probe_seq": (row.get("Probe_Seq") or "").strip(),
                "fwd_tm": _s(row.get("Fwd_Tm")),
                "rev_tm": _s(row.get("Rev_Tm")),
                "probe_tm": _s(row.get("Probe_Tm")),
                "product": _s(row.get("Product")),
                "gc_fwd": _s(row.get("GC_Fwd")),
                "gc_rev": _s(row.get("GC_Rev")),
                "fwd_start": _s(row.get("Fwd_Start")),
                "rev_start": _s(row.get("Rev_Start")),
                "degen": _s(row.get("Total_Degeneracy")),
                "tile_id": _s(row.get("Tile_ID")),
                "tile_start": _s(row.get("Tile_Start")),
                "tile_end": _s(row.get("Tile_End")),
                "score": _s(row.get("Validation_Score")),
                "recommendation": (row.get("Recommendation") or "").strip(),
                "dimer_fwd": _s(row.get("Self_Dimer_Fwd")),
                "dimer_rev": _s(row.get("Self_Dimer_Rev")),
                "dimer_cross": _s(row.get("Cross_Dimer")),
                "dimer_cross_3prime": _s(row.get("Cross_Dimer_3prime")),
                "dimer_warning": _s(row.get("Dimer_Warning")),
                "specificity": _s(row.get("BLAST_Specificity_Score")),
                "plant_risk": (row.get("BLAST_Plant_Risk") or "").strip(),
            })

    # 写每物种 JSON
    species_index = {}
    total_pairs = 0
    print(f"写入 {len(by_species)} 个物种的引物数据...")

    for sp, primers in sorted(by_species.items()):
        safe_name = sp.replace("/", "_").replace("\\", "_")
        safe_name = safe_name.replace("[", "(").replace("]", ")").replace(":", "_")
        safe_name = safe_name.replace("*", "_").replace("?", "_").replace("\"", "_")
        safe_name = safe_name.replace("<", "_").replace(">", "_").replace("|", "_")
        fname = f"{safe_name}.json"
        fpath = species_dir / fname

        # 统计该物种的各类型数量
        type_counts = {"PCR": 0, "qPCR": 0, "DEGENERATE": 0, "TILED": 0}
        for p in primers:
            t = p["type"]
            if t in type_counts: type_counts[t] += 1
        total = sum(type_counts.values())
        total_pairs += total

        # 如果有分类信息
        tax = taxonomy.get(sp, {})
        tax_family = tax.get("family", "")
        tax_genus = tax.get("genus", "")
        if tax_family: stats["families"].add(tax_family)
        if tax_genus: stats["genera"].add(tax_genus)

        # 统计推荐状态
        for p in primers:
            r = p.get("recommendation", "")
            if r == "RECOMMENDED": stats["recommended"] += 1
            elif r in ("CAUTION", "USABLE"): stats["usable"] += 1
            elif r == "NOT_RECOMMENDED": stats["not_recommended"] += 1

        # 物种级别 JSON
        sp_data = {
            "species": sp,
            "family": tax_family,
            "genus": tax_genus,
            "segment": tax.get("segment", ""),
            "genome_length": tax.get("genome_length", ""),
            "pcr": type_counts["PCR"],
            "qpcr": type_counts["qPCR"],
            "degenerate": type_counts["DEGENERATE"],
            "tiled": type_counts["TILED"],
            "total": total,
            "primers": primers
        }
        fpath.write_text(json.dumps(sp_data, ensure_ascii=False), encoding='utf-8')

        # 索引条目 (不含 primers 详情)
        species_index[sp] = {
            "family": tax_family,
            "genus": tax_genus,
            "pcr": type_counts["PCR"],
            "qpcr": type_counts["qPCR"],
            "degenerate": type_counts["DEGENERATE"],
            "tiled": type_counts["TILED"],
            "total": total,
            "file": f"species/{fname}"
        }

        # 累计类型统计
        for t in ["PCR", "qPCR", "DEGENERATE", "TILED"]:
            stats[t.lower()] += type_counts[t]

    # 写索引文件
    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps(species_index, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"  {index_path} ({len(species_index)} 物种)")

    # 写统计文件
    stats["total_pairs"] = total_pairs
    stats["total_species"] = len(species_index)
    stats["families"] = len(stats["families"])
    stats["genera"] = len(stats["genera"])
    del stats["families"]  # 删除 set, 已转为 int
    # 注意: families/genera 在 stats 中先被当 set 累计, 最后转 int
    # 修复: 重新统计
    stats2 = {
        "pcr": stats["pcr"], "qpcr": stats["qpcr"],
        "degenerate": stats["degenerate"], "tiled": stats["tiled"],
        "total_pairs": total_pairs, "total_species": len(species_index),
        "recommended": stats["recommended"],
        "usable": stats["usable"],
        "not_recommended": stats["not_recommended"]
    }
    # 重新计算 families/genera
    all_fams = set()
    all_gens = set()
    for sp, info in species_index.items():
        if info["family"]: all_fams.add(info["family"])
        if info["genus"]: all_gens.add(info["genus"])
    stats2["families"] = len(all_fams)
    stats2["genera"] = len(all_gens)

    stats_path = out_dir / "stats.json"
    stats_path.write_text(json.dumps(stats2, ensure_ascii=False), encoding='utf-8')
    print(f"  {stats_path}")

    print(f"\n完成: {total_pairs} 对引物, {len(species_index)} 物种")
    print(f"  PCR={stats2['pcr']}, qPCR={stats2['qpcr']}, "
          f"Degenerate={stats2['degenerate']}, Tiled={stats2['tiled']}")


def _s(v):
    """安全转为字符串"""
    if v is None: return ""
    return str(v).strip()


if __name__ == "__main__":
    main()
