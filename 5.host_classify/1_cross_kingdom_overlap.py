# -*- coding: utf-8 -*-
"""
C5: Cross-kingdom analysis at all 7 taxonomic levels.
Outputs multi-level overlap tables and detailed species logs.

Usage:
  python C5_cross_kingdom_analysis.py -i classified_clean/ -o cross_analysis/ -s Plant
"""
import polars as pl
import os, argparse, csv
from collections import defaultdict

TAXA_LEVELS = {
    "Realm":   0, "Kingdom": 1, "Phylum": 2, "Class": 3,
    "Order":   4, "Family":  5, "Genus":  6, "Species": 7,
}
LEVEL_ORDER = list(TAXA_LEVELS.keys())

# =====================================================================
# 跨脚本共用常量 (本文件为唯一定义处, 被 2_plot_overlap.py / 3_host_probability.py
# 以 importlib 按路径加载导入, 保证"其他宿主界"枚举口径三处一致)
# =====================================================================
# 非宿主界的"类别"文件: Unknown / Environmental_NCBI / Algae 是来源或非宿主界标记,
# 参与"其他宿主界"枚举会系统性虚高; cross_species / miss 是衍生目录;
# Animal 是 C3b 拆分 (Aves/Mammalia/Animal_other/Human) 前的聚合父类, 参与会双重计数。
CATEGORIES_SKIP = {
    "Unknown", "Environmental_NCBI", "Algae",
    "cross_species", "miss", "Animal",
}
# 步骤产物/汇总文件 (按类别名前缀匹配, 不是宿主类别)
META_FILE_PREFIXES = ("All_Processed_Records", "Summary_Counts", "Task1_", "Task2_", "Plant_Virus_")

# HVT (high vector transmission) 家族: 跨宿主界传播/共进化噪声源,
# 供 2_plot_overlap.py --exclude-hvt 开关使用 (默认不过滤)。
HVT_FAMS = {"Mitoviridae", "Partitiviridae", "Endornaviridae", "Botourmiaviridae", "Narnaviridae"}

# 宿主属名碰撞清单 (病毒名中的属名 = 植物/昆虫宿主属名, 需人工判为碰撞而非真实跨界)。
# 来源: 上游 C4_clean_all_tsvs.py:110-111 GENUS_COLLISIONS (含 Acharia, 2026-10-03 同步)。
COLLISION_GENERA = {"Coelogyne", "Mansonia", "Charybdis", "Paphia", "Epiphyllum", "Acharia"}


def is_category_file(fname: str) -> bool:
    """判断 *.tsv 是否为可分析的宿主类别文件 (排除衍生目录与步骤产物)。"""
    if not fname.endswith('.tsv'):
        return False
    base = fname[:-4]
    if base in CATEGORIES_SKIP:
        return False
    return not any(base.startswith(p) for p in META_FILE_PREFIXES)


def load_taxa(path):
    """Load all 8 virus taxonomic levels from a TSV file."""
    df = pl.read_csv(path, separator='\t', truncate_ragged_lines=True)
    vp = pl.col("Virus_lineage") + ";;;;;;;;"
    exprs = []
    for name, idx in TAXA_LEVELS.items():
        c = vp.str.split(";").list.get(idx).str.strip_chars()
        if name == "Species":
            c = (c.str.replace_all(r"(?i)\s+RNA\s*\d+$", "")
                  .str.replace_all(r"(?i)\s+segment\s+\d+$", "")
                  .str.replace_all(r"(?i)\s+DNA\s+\d+$", ""))
        exprs.append(c.alias(f"V_{name}"))
    return df.with_columns(exprs)


SKIP = CATEGORIES_SKIP  # 向后兼容别名; 新代码请直接用 is_category_file() / CATEGORIES_SKIP


def main():
    p = argparse.ArgumentParser(description="C5: Multi-level cross-kingdom analysis")
    p.add_argument("--input_dir", "-i", default="classified_clean/")
    p.add_argument("--output_dir", "-o", default="cross_analysis/")
    p.add_argument("--source", "-s", default="Plant")
    args = p.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    detail_dir = os.path.join(args.output_dir, "cross_details")
    os.makedirs(detail_dir, exist_ok=True)

    # Find category files (统一口径: 排除 Unknown/Environmental_NCBI/Algae/Animal 等非宿主界类别)
    tsv_files = sorted(f for f in os.listdir(args.input_dir) if is_category_file(f))
    print(f"Categories: {len(tsv_files)}")

    # Load source taxa at all levels
    source_file = os.path.join(args.input_dir, f"{args.source}.tsv")
    df_src = load_taxa(source_file)

    src_taxa = {}
    for lvl in LEVEL_ORDER:
        col = f"V_{lvl}"
        src_taxa[lvl] = set(df_src[col].to_list()) - {""}
    print(f"Source ({args.source}): {df_src.height} records")
    for lvl in LEVEL_ORDER:
        print(f"  {lvl:10s}: {len(src_taxa[lvl]):>6,d}")

    # Compute overlap at all levels
    all_overlap = {}  # {category: {level: shared_count}}

    for f in tsv_files:
        cat = f.replace('.tsv', '')
        if cat == args.source:
            continue
        df_cat = load_taxa(os.path.join(args.input_dir, f))
        cat_taxa = {}
        for lvl in LEVEL_ORDER:
            col = f"V_{lvl}"
            cat_taxa[lvl] = set(df_cat[col].to_list()) - {""}
        all_overlap[cat] = {}
        for lvl in LEVEL_ORDER:
            all_overlap[cat][lvl] = len(src_taxa[lvl] & cat_taxa[lvl])

    # Print table
    print(f"\n{'Category':18s}", end="")
    for lvl in LEVEL_ORDER:
        print(f" {lvl:>8s}", end="")
    print()
    print("-" * (18 + 9 * len(LEVEL_ORDER)))
    for cat in sorted(all_overlap):
        print(f"{cat:18s}", end="")
        for lvl in LEVEL_ORDER:
            n = all_overlap[cat].get(lvl, 0)
            print(f" {n:>8d}", end="")
        print()

    # 分类阈值使用模块级常量 (HVT_FAMS / COLLISION_GENERA, 供 2/3 号脚本共享)：
    # HVT 家族 = 跨宿主界共进化噪声; 碰撞属 = 属名撞名的假跨界
    cross_fams = HVT_FAMS
    collision_gens = COLLISION_GENERA

    # Host genera from source
    hp = pl.col("Host_lineage") + ";;;;;;;;"
    df_src = df_src.with_columns(hp.str.split(";").list.get(6).str.strip_chars().alias("_H_Genus"))

    sp_class = {}
    all_detail = []

    for cat in sorted(all_overlap):
        cat_path = os.path.join(args.input_dir, f"{cat}.tsv")
        df_cat = load_taxa(cat_path)
        cat_sps = set(df_cat["V_Species"].to_list()) - {""}
        shared = src_taxa["Species"] & cat_sps
        if not shared:
            continue

        detail_rows = []
        type_counts = defaultdict(int)

        for sp in sorted(shared):
            src_cnt = df_src.filter(pl.col("V_Species") == sp).height
            cat_cnt = df_cat.filter(pl.col("V_Species") == sp).height
            info = df_src.filter(pl.col("V_Species") == sp).head(1)
            fam = info["V_Family"][0] or ""
            hg = info["_H_Genus"][0] or ""
            vn = info["Virus_Name"][0] or ""
            hn = info["Host_Name"][0] or ""

            # Classify
            if fam in cross_fams:
                tp = "GENUINE_CROSS"
            elif hg in collision_gens:
                tp = "GENUS_COLLISION"
            elif cat in ("Insecta",):
                tp = "VECTOR_INSECT"
            elif cat in ("Arachnida",):
                tp = "VECTOR_ARACHNID"
            elif cat in ("Aves", "Mammalia", "Animal_other"):
                tp = "DIET_TRANSIT"
            elif src_cnt <= 2 and cat_cnt > 10:
                tp = "RESIDUAL"
            elif cat == "Fungi":
                tp = "GENUINE_CROSS"
            else:
                tp = "OTHER"

            type_counts[tp] += 1
            sp_class[sp] = tp
            row = {
                "Cross_Type": tp, "Target_Category": cat, "Species": sp,
                "Family": fam, "Source_Records": src_cnt, "Target_Records": cat_cnt,
                "Host_Genus": hg, "Host_Name": hn, "Virus_Name": vn,
            }
            detail_rows.append(row)
            all_detail.append(row)

        type_str = ", ".join(f"{t}={type_counts[t]}" for t in
            ["GENUINE_CROSS", "VECTOR_INSECT", "VECTOR_ARACHNID", "DIET_TRANSIT", "GENUS_COLLISION", "RESIDUAL"]
            if type_counts[t] > 0)
        print(f"  {cat:16s} species={len(shared):>4d}  → {type_str}")

        # Save per-category detail
        with open(os.path.join(detail_dir, f"{args.source}_vs_{cat}.tsv"), 'w', newline='') as f:
            w = csv.DictWriter(f, delimiter='\t', fieldnames=detail_rows[0].keys())
            w.writeheader(); w.writerows(detail_rows)

    # Save multi-level overlap table
    overlap_path = os.path.join(args.output_dir, "multi_level_overlap.tsv")
    with open(overlap_path, 'w') as f:
        f.write("Category\t" + "\t".join(LEVEL_ORDER) + "\n")
        for cat in sorted(all_overlap):
            vals = "\t".join(str(all_overlap[cat].get(l, 0)) for l in LEVEL_ORDER)
            f.write(f"{cat}\t{vals}\n")
    print(f"\nMulti-level overlap: {overlap_path}")

    # Save merged detail
    detail_path = os.path.join(args.output_dir, "cross_kingdom_all_details.tsv")
    if all_detail:
        with open(detail_path, 'w', newline='') as f:
            w = csv.DictWriter(f, delimiter='\t', fieldnames=all_detail[0].keys())
            w.writeheader(); w.writerows(all_detail)
    print(f"All details: {detail_path}")

    # Classification summary
    print(f"\n{'='*50}")
    print("CLASSIFICATION SUMMARY")
    print(f"{'='*50}")
    for t in ["GENUINE_CROSS", "VECTOR_INSECT", "VECTOR_ARACHNID", "DIET_TRANSIT", "GENUS_COLLISION", "RESIDUAL"]:
        sps = [sp for sp, tp in sp_class.items() if tp == t]
        if sps:
            print(f"  {t:20s}: {len(sps):>4d} species")


if __name__ == "__main__":
    main()
