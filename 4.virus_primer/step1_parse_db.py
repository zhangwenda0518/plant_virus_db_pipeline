#!/usr/bin/env python3
"""
Step 1: 解析本地参考基因组数据库，按物种拆分序列
========================================================================
输入:
  --local-db   plant-virus.db 目录（自动发现数据文件）
  --fasta      自定义 FASTA + --info 元数据 TSV

输出:
  per_species/ 目录，每个物种一个 FASTA 文件 (+ per-species 合并日志)
  species_index.tsv  物种列表 + 序列数 + 分类学信息

用法:
  # 对接 plant-virus.db (服务器)
  python step1_parse_db.py --local-db ~/plant_virus_db/2.plant-virus.db -o split_species

  # 自定义输入
  python step1_parse_db.py --fasta sequences.fasta --info metadata.tsv -o split_species

对接 pipeline 的标准输出格式:
  F-dedup/split_results/NonSegmented_Complete.fasta  + _Info.tsv
  F-dedup/split_results/Segmented_Complete.fasta      + _Info.tsv
  G-cluster/final.cluster.ref.fasta                   + _Info.tsv
"""

import argparse
import os
import re
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Optional
import polars as pl
from Bio import SeqIO

def _normalize_segment(name: str) -> str:
    """归一化 Segment 名称: DNA_S/S/DNA-S/DNA S → S, RNA_1/RNA1 → 1"""
    import re
    s = name.strip().upper()
    # 去掉 DNA/RNA 前缀 (含各种分隔符)
    s = re.sub(r'^(DNA|RNA)[_\-\s]*', '', s)
    # 去掉连续空格/下划线
    s = re.sub(r'[_\-\s]+', '_', s).strip('_')
    return s if s else name.upper()


# ======================================================================
# 数据库自动发现
# ======================================================================

def discover_local_db(db_root: Path) -> dict:
    """
    自动发现 plant-virus.db 中的可用数据文件。
    优先选择含多序列的完整基因组，其次单序列后备。

    返回:
      {"primary": [{"fasta":..., "info":..., "source":..., "seq_count":...}, ...],
       "fallback": {"fasta":..., "info":..., "source":..., "seq_count":...},
       "metadata": Path or None}
    """
    result = {"primary": None, "fallback": None, "metadata": None}
    split_dir = db_root / "F-dedup" / "split_results"

    # 优先: Complete 基因组
    complete_sources = []
    for cat in ["NonSegmented_Complete", "Segmented_Complete"]:
        fa = split_dir / f"{cat}.fasta"
        info = split_dir / f"{cat}_Info.tsv"
        if fa.exists():
            try:
                with open(fa) as f:
                    sc = sum(1 for line in f if line.startswith('>'))
            except Exception:
                sc = 0
            complete_sources.append({
                "fasta": fa, "info": info if info.exists() else None,
                "source": f"{cat}", "seq_count": sc
            })

    if complete_sources:
        complete_sources.sort(key=lambda x: x["seq_count"], reverse=True)
        result["primary"] = complete_sources
        print(f"  ▶ 主源: {' + '.join(c['source'] for c in complete_sources)}")
        ttl = sum(c['seq_count'] for c in complete_sources)
        print(f"    总序列: {ttl:,} 条")

    # 后备: 单序列代表
    for fa_path, info_path, desc in [
        (db_root / "G-cluster" / "final.cluster.ref.fasta",
         db_root / "G-cluster" / "final.cluster.ref_info.tsv",
         "G-cluster/vclust"),
        (db_root / "F-dedup" / "plant.final.rmdup.fasta",
         db_root / "F-dedup" / "plant.final.rmdup_info.tsv",
         "F-dedup去冗余"),
    ]:
        if fa_path.exists():
            try:
                with open(fa_path) as f:
                    sc = sum(1 for line in f if line.startswith('>'))
            except Exception:
                sc = 0
            result["fallback"] = {
                "fasta": fa_path, "info": info_path if info_path.exists() else None,
                "source": desc, "seq_count": sc
            }
            print(f"  ▶ 后备: {desc} ({sc:,} 条)")
            break

    # 全量元数据
    for mp in [
        db_root / "E-metadata" / "Plant_Virus_Info.full.tsv",
        db_root / "G-cluster" / "final.cluster.ref_info.tsv",
    ]:
        if mp.exists():
            result["metadata"] = mp
            break

    return result


# ======================================================================
# 按物种拆分
# ======================================================================

def split_by_species(fasta_path: Path, info_path: Optional[Path],
                     species_filter: str = "",
                     segment_mode: str = "auto",
                     seg_override: dict = None) -> dict:
    """
    将 FASTA 按物种分组，同时提取节段信息。

    节段病毒处理 (参考 MRPrimerV):
      - 非节段病毒: 所有序列是同一基因组的不同分离株 → 按物种分组
      - 节段病毒: 同一物种的不同节段是独立的基因组分子
        → 按 (物种, 节段) 分组，每个节段独立设计引物
        → MRPrimerV: "if valid primers exist for some segments of a virus
           with a segmented genome, we can detect that virus using those
           primers even when there are no valid primers for the remaining segments"

    返回:
      {species_name: [{"acc":..., "seq":..., "family":..., "genus":..., "segment":...}, ...]}

    segment_mode:
      - "auto": 从 Info 的 Category 列判断 (NonSegmented/Segmented)
      - "nonsegmented": 强制不分节段
      - "segmented": 强制分节段
    """
    acc_to_sp = {}
    sp_family = {}
    sp_genus = {}
    acc_to_seqtype = {}  # RefSeq 标记
    # ★ 新增: 记录每条序列的节段信息
    acc_to_segment = dict(seg_override) if seg_override else {}
    acc_to_category = {}
    is_segmented_source = (segment_mode == "segmented")

    if info_path and info_path.exists():
        try:
            info = pl.read_csv(info_path, separator='\t', ignore_errors=True,
                               infer_schema_length=5000)

            sp_col = next((c for c in ["Species_ICTV", "Species_NCBI", "Species",
                                        "species", "organism"] if c in info.columns), None)
            acc_col = next((c for c in ["Accession", "acc", "SeqID"] if c in info.columns), None)
            fam_col = "Family" if "Family" in info.columns else None
            gen_col = "Genus" if "Genus" in info.columns else None

            # ★ 新增: 识别 Segment / Category 列
            seg_col = next((c for c in ["Segment_Normalized", "Segment", "segment"]
                           if c in info.columns), None)
            cat_col = "Category" if "Category" in info.columns else None

            if acc_col and sp_col:
                for row in info.iter_rows(named=True):
                    acc = str(row.get(acc_col, "")).strip().split('.')[0].upper()
                    sp = str(row.get(sp_col, "")).strip()
                    if acc and sp and sp.lower() not in ("", "unknown", "unclassified"):
                        acc_to_sp[acc] = sp
                        if fam_col:
                            sp_family[sp] = str(row.get(fam_col, "")).strip()
                        if gen_col:
                            sp_genus[sp] = str(row.get(gen_col, "")).strip()
                        # RefSeq 标记
                        st = str(row.get("Sequence_Type", "")).strip()
                        if st:
                            acc_to_seqtype[acc] = st

                        # ★ 提取节段信息 (优先 Segment_Normalized, 否则手动归一化)
                        if seg_col:
                            raw_seg = str(row.get(seg_col, ""))
                            # 已有预归一化列则直接使用, 否则手动归一化
                            seg = raw_seg if seg_col == "Segment_Normalized" else _normalize_segment(raw_seg)
                            if seg and seg.lower() not in ("", "nan", "none", "unassigned"):
                                acc_to_segment[acc] = seg

                        # ★ 判断是否节段源
                        if cat_col and not is_segmented_source:
                            cat = str(row.get(cat_col, "")).strip()
                            if cat.startswith("Segmented"):
                                is_segmented_source = True
        except Exception as e:
            print(f"  ⚠ 读取 info 失败: {e}")

    # 解析 FASTA
    sp_sequences = defaultdict(list)
    unassigned = []

    for record in SeqIO.parse(fasta_path, "fasta"):
        base = record.id.split('.')[0].upper()
        seq_str = str(record.seq).upper()
        sp = acc_to_sp.get(base) or acc_to_sp.get(record.id)

        # ★ 获取节段名
        seg_name = acc_to_segment.get(base, acc_to_segment.get(record.id, ""))

        if sp:
            if not species_filter or species_filter.lower() in sp.lower():
                entry = {
                    "acc": record.id, "seq": seq_str,
                    "family": sp_family.get(sp, ""),
                    "genus": sp_genus.get(sp, ""),
                    "segment": seg_name,
                    "seq_type": acc_to_seqtype.get(base, acc_to_seqtype.get(record.id, ""))
                }
                sp_sequences[sp].append(entry)
        else:
            sp_h = _species_from_header(record.description)
            if sp_h and (not species_filter or species_filter.lower() in sp_h.lower()):
                sp_sequences[sp_h].append({
                    "acc": record.id, "seq": seq_str,
                    "family": "", "genus": "",
                    "segment": ""
                })
            else:
                unassigned.append(record.id)

    if unassigned:
        print(f"  ⚠ {len(unassigned)} 条序列无法归类")

    return dict(sp_sequences), is_segmented_source


def _species_from_header(desc: str) -> Optional[str]:
    """从 FASTA header 提取物种名"""
    m = re.search(r'\[(.+?)\]', desc)
    if m:
        name = m.group(1).strip()
        if 3 < len(name) < 100 and ' ' in name:
            return name
    parts = desc.split(None, 1)
    if len(parts) > 1:
        rest = re.sub(
            r',\s*(complete|partial|segment|isolate|strain|clone'
            r'|genome|sequence|protein|gene|capsid|coat|replicase'
            r'|polymerase|polyprotein|glycoprotein).*',
            '', parts[1], flags=re.IGNORECASE
        ).strip().rstrip(',')
        if 3 < len(rest) < 100 and ' ' in rest:
            return rest
    return None


def write_per_species(species_map: dict, out_dir: Path,
                       is_segmented: bool = False) -> Path:
    """
    输出 per-species FASTA + species_index.tsv + segment_map.tsv。

    MRPrimerV 参考:
      节段病毒: 每个节段独立为设计目标。
      "if valid primers exist for some segments, the virus can be detected"
    """
    sp_dir = out_dir / "species"
    sp_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    seg_rows = []  # segment 映射表

    for sp, records in species_map.items():
        safe = sp.replace('/', '_').replace(' ', '_').replace(':', '_')[:80]
        has_segments = any(r.get("segment", "") for r in records)

        if has_segments:
            # 按 segment 拆分 → 每个 segment 一个文件
            seg_groups = defaultdict(list)
            for r in records:
                seg = r.get("segment", "unknown") or "unknown"
                seg_groups[seg].append(r)

            for seg, seg_records in seg_groups.items():
                # 先压缩物种名, 为节段名预留 20 字符空间
                safe_sp = safe[:60]
                seg_safe = f"{safe_sp}_{seg}".replace('/', '_')[:80]
                fa_file = sp_dir / f"{seg_safe}.fasta"
                with open(fa_file, 'w') as f:
                    for r in seg_records:
                        header = r['acc'] + f"|segment={seg}"
                        f.write(f">{header}\n{r['seq']}\n")
                        seg_rows.append({"Species": sp, "Accession": r['acc'], "Segment": seg})
                n_segs = len(seg_records)
                genome_len = max((len(r.get("seq","")) for r in seg_records), default=0)
                rows.append({
                    "Species": sp, "Num_Sequences": n_segs,
                    "Num_Segments": 1, "Has_Segments": True,
                    "FASTA": str(fa_file),
                    "Family": seg_records[0].get("family", ""),
                    "Genus": seg_records[0].get("genus", ""),
                    "Has_Multi_Seq": n_segs >= 2,
                    "Has_Multi_Seq_Per_Segment": False,
                    "Genome_Length": genome_len
                })
        else:
            fa_file = sp_dir / f"{safe}.fasta"
            with open(fa_file, 'w') as f:
                for r in records:
                    header = r['acc']
                    f.write(f">{header}\n{r['seq']}\n")
            n_seqs = len(records)
            genome_len = max((len(r.get("seq","")) for r in records), default=0)
            rows.append({
                "Species": sp, "Num_Sequences": n_seqs,
                "Num_Segments": 0, "Has_Segments": False,
                "FASTA": str(fa_file),
                "Family": records[0].get("family", ""),
                "Genus": records[0].get("genus", ""),
                "Has_Multi_Seq": n_seqs >= 2,
                "Has_Multi_Seq_Per_Segment": False,
                "Genome_Length": genome_len
            })

    df = pl.DataFrame(rows)
    idx_file = out_dir / "species_index.tsv"
    df.write_csv(idx_file, separator='\t')

    # 输出 segment 映射表 (供 step2 使用)
    if seg_rows:
        seg_df = pl.DataFrame(seg_rows).unique()
        seg_file = out_dir / "segment_map.tsv"
        seg_df.write_csv(seg_file, separator='\t')
        print(f"  → {seg_file} ({len(seg_df)} 条节段记录)")

    multi_sp = sum(1 for r in rows if r["Has_Multi_Seq"])
    single_sp = sum(1 for r in rows if not r["Has_Multi_Seq"] and not r["Has_Segments"])
    seg_sp = sum(1 for r in rows if r["Has_Segments"])
    print(f"  → {len(rows)} 物种: {multi_sp} 多序列, {single_sp} 单序列, {seg_sp} 节段")
    print(f"  → {sp_dir}/")
    print(f"  → {idx_file}")

    return idx_file


# ======================================================================
# 主入口
# ======================================================================

def main():
    p = argparse.ArgumentParser(description="Step 1: 解析本地数据库，按物种拆分")

    g = p.add_argument_group("输入模式 (二选一)")
    g.add_argument("--local-db", help="plant-virus.db 目录路径")
    g.add_argument("--full-info", help="全量元数据 (覆盖 local-db 自带的 info, 含 Family/Genus)")
    g.add_argument("--fasta", help="FASTA 文件 (需配合 --info, 多个用逗号分隔)")
    g.add_argument("--fasta2", help="FASTA2 文件 (同上)")
    g.add_argument("--info", help="元数据 TSV")
    g.add_argument("--info2", help="元数据 TSV2")
    g.add_argument("--segment-info", help="节段规范化 TSV")
    g.add_argument("--segment-info2", help="节段规范化 TSV2")

    p.add_argument("-o", "--output", default="split_species",
                   help="输出目录 (默认: split_species)")
    p.add_argument("--species", default="", help="仅处理指定物种")
    p.add_argument("--combine", action="store_true",
                   help="合并所有序列到单文件 (不按物种拆分)")
    p.add_argument("--no-fallback", action="store_true",
                   help="不使用 G-cluster 后备")

    args = p.parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    species_map = {}
    is_segmented = False

    # 从 segment-info 文件加载节段映射 (供 --fasta 和 --local-db 使用)
    seg_override = None
    if args.segment_info:
        sip = Path(args.segment_info)
        if sip.exists():
            try:
                si = pl.read_csv(sip, separator='\t', ignore_errors=True)
                seg_col_name = next((c for c in ["Segment_Normalized", "Segment", "segment"]
                                    if c in si.columns), None)
                acc_col_name = next((c for c in ["Accession", "acc"] if c in si.columns), None)
                if seg_col_name and acc_col_name:
                    seg_override = {}
                    for row in si.iter_rows(named=True):
                        acc = str(row.get(acc_col_name, "")).strip().split('.')[0].upper()
                        seg = str(row.get(seg_col_name, "")).strip()
                        if acc and seg and seg.lower() not in ("", "nan", "none"):
                            seg_override[acc] = seg
                    print(f"  已加载 {len(seg_override)} 条节段映射")
            except Exception as e:
                print(f"  ⚠ 加载节段映射失败: {e}")

    if args.local_db:
        db = Path(args.local_db)
        if not db.exists():
            print(f"✗ 数据库路径不存在: {db}")
            return
        print(f"▶ 加载本地数据库: {db}")

        db_files = discover_local_db(db)
        if not db_files["primary"] and not db_files["fallback"]:
            print("✗ 未找到有效文件"); return

        # 主源: Complete 基因组
        # 全量元数据覆盖 (--full-info)
        override_info = Path(args.full_info) if args.full_info else None
        if override_info and not override_info.exists():
            print(f"  ⚠ full-info 不存在: {override_info}"); override_info = None

        if db_files["primary"]:
            for src in db_files["primary"]:
                info_to_use = override_info if override_info else src["info"]
                print(f"  → 解析: {src['fasta'].name} ({src['seq_count']} 条)")
                sp_map, sp_seg = split_by_species(src["fasta"], info_to_use, args.species, seg_override=seg_override)
                is_segmented = is_segmented or sp_seg
                for sp_name, records in sp_map.items():
                    if sp_name in species_map:
                        existing = {r["acc"] for r in species_map[sp_name]}
                        for r in records:
                            if r["acc"] not in existing:
                                species_map[sp_name].append(r)
                    else:
                        species_map[sp_name] = records
            print(f"  Complete 基因组: {len(species_map)} 物种")

        # 后备补充
        if not args.no_fallback and db_files["fallback"]:
            fb_map, _ = split_by_species(
                db_files["fallback"]["fasta"],
                override_info if override_info else db_files["fallback"]["info"],
                args.species
            )
            added = 0
            for sp_name in fb_map:
                if sp_name not in species_map and sp_name != "_UNASSIGNED_":
                    species_map[sp_name] = fb_map[sp_name]
                    added += 1
            if added > 0:
                print(f"  → 后备补充: +{added} 物种")

        total_multi = sum(1 for r in species_map.values() if len(r) >= 2)
        total_single = sum(1 for r in species_map.values() if len(r) == 1)
        print(f"  → 总计: {len(species_map)} 物种 "
              f"(多序列: {total_multi}, 单序列: {total_single})")

    elif args.fasta:
        # 支持多组 FASTA+info+segment-info
        fasta_list = [Path(x.strip()) for x in args.fasta.split(',') if x.strip()]
        info_list = [Path(x.strip()) for x in (args.info or '').split(',') if x.strip()]
        seg_list = [Path(x.strip()) for x in (args.segment_info or '').split(',') if x.strip()]

        if args.fasta2:
            fasta_list.append(Path(args.fasta2))
            if args.info2: info_list.append(Path(args.info2))
            if args.segment_info2: seg_list.append(Path(args.segment_info2))

        for i, fp in enumerate(fasta_list):
            ip = info_list[i] if i < len(info_list) else None
            sip = seg_list[i] if i < len(seg_list) else None
            if not fp.exists():
                print(f"✗ FASTA 不存在: {fp}"); continue
            print(f"▶ 加载 FASTA: {fp}")
            # 每个 FASTA 可单独加载 segment-info
            seg_ov = dict(seg_override) if seg_override else None
            if sip and sip.exists() and seg_ov is None:
                try:
                    si = pl.read_csv(sip, separator='\t', ignore_errors=True)
                    sc = next((c for c in ["Segment_Normalized","Segment","segment"] if c in si.columns), None)
                    ac = next((c for c in ["Accession","acc"] if c in si.columns), None)
                    if sc and ac:
                        seg_ov = {}
                        for row in si.iter_rows(named=True):
                            a = str(row.get(ac,'')).split('.')[0].upper()
                            s = str(row.get(sc,'')).strip()
                            if a and s and s.lower() not in ('','nan','none'): seg_ov[a] = s
                except: pass
            sp_map, is_segmented = split_by_species(fp, ip, args.species, seg_override=seg_ov)
            # 合并到 species_map
            for sp_name, records in sp_map.items():
                if sp_name in species_map:
                    existing = {r["acc"] for r in species_map[sp_name]}
                    for r in records:
                        if r["acc"] not in existing:
                            species_map[sp_name].append(r)
                else:
                    species_map[sp_name] = records
            print(f"  → 累计 {len(species_map)} 物种")

    else:
        p.print_help()
        print("\n请指定 --local-db 或 --fasta"); return


    if not species_map:
        print("✗ 未解析到任何物种"); return

    # 合并模式
    if args.combine:
        merged = out_dir / "all_sequences.fasta"
        with open(merged, 'w') as f:
            for records in species_map.values():
                for r in records:
                    f.write(f">{r['acc']}\n{r['seq']}\n")
        print(f"  → 合并: {merged}")
        return

    # 按物种拆分输出
    write_per_species(species_map, out_dir, is_segmented)


if __name__ == "__main__":
    main()
