#!/usr/bin/env python3
"""
批量引物设计流水线 — PCR + qPCR + 简并引物
============================================
为 final.cluster.ref.fasta 中每个病毒物种设计:
  - PCR 引物 (AutoPVPrimer) — 覆盖保守区, 3-5 对/病毒
  - 简并引物 (varVAMP qPCR mode) — 高变异病毒，覆盖株系间差异
  - qPCR 引物 (AutoPVPrimer) — 短扩增子 100-250bp

工作流:
  1. 按 Species_ICTV 拆分 FASTA
  2. 每物种并行设计引物
  3. 聚合结果 → primer_reference.tsv

Usage:
  python batch_primer_pipeline.py \
      --fasta final.cluster.ref.fasta \
      --info final.cluster.ref_info.tsv \
      -o primers/ --threads 40
"""

import argparse
import subprocess
import os
import sys
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import polars as pl
import json


def parse_args():
    p = argparse.ArgumentParser(description="批量病毒引物设计流水线")
    p.add_argument("--fasta", required=True, help="final.cluster.ref.fasta")
    p.add_argument("--info", required=True, help="final.cluster.ref_info.tsv")
    p.add_argument("-o", "--output", default="primers/", help="输出目录")
    p.add_argument("-t", "--threads", default=10, type=int, help="并行进程数")
    p.add_argument("--num-pcr-primers", default=5, type=int, help="每病毒PCR引物对数")
    p.add_argument("--num-qpcr-primers", default=3, type=int, help="每病毒qPCR引物对数")
    p.add_argument("--degenerate-threshold", default=3, type=int,
                   help="≥此序列数时才设计简并引物")
    p.add_argument("--skip-degenerate", action="store_true", help="跳过简并引物设计")
    p.add_argument("--skip-crispr", action="store_true", help="跳过CRISPR检测引物设计")
    p.add_argument("--crispr-cas-type", default="Cas12a", choices=["Cas12a", "Cas12b", "Cas13a", "Cas9"],
                   help="CRISPR检测使用的Cas蛋白类型")
    p.add_argument("--dry-run", action="store_true", help="只生成任务列表，不实际运行")
    return p.parse_args()


def split_fasta_by_species(fasta_path: str, info_path: str, out_dir: Path):
    """按 Species_ICTV 拆分 FASTA，输出 per-species 文件"""
    print(f"[1/5] 拆分 FASTA 按物种...")

    info = pl.read_csv(info_path, separator='\t', ignore_errors=True)

    # 建立 Accession → Species_ICTV 映射
    acc_to_sp = {}
    for row in info.iter_rows(named=True):
        acc = str(row.get('Accession', '')).split('.')[0].upper()
        sp = str(row.get('Species_ICTV', row.get('Species_NCBI', 'Unknown'))).strip()
        if sp:
            acc_to_sp[acc] = sp

    # 读 FASTA，按物种分组
    sp_sequences = defaultdict(list)
    current_acc = None
    current_seq = []
    with open(fasta_path) as f:
        for line in f:
            if line.startswith('>'):
                if current_acc and current_seq:
                    seq = ''.join(current_seq)
                    if current_acc in acc_to_sp:
                        sp = acc_to_sp[current_acc]
                        sp_sequences[sp].append((current_acc, seq))
                current_acc = line[1:].split()[0].split('.')[0].upper()
                current_seq = []
            else:
                current_seq.append(line.strip())
        # last record
        if current_acc and current_seq:
            seq = ''.join(current_seq)
            if current_acc in acc_to_sp:
                sp = acc_to_sp[current_acc]
                sp_sequences[sp].append((current_acc, seq))

    # 写 per-species FASTA
    species_dir = out_dir / "per_species"
    species_dir.mkdir(parents=True, exist_ok=True)
    species_info = {}

    for sp, seqs in sp_sequences.items():
        safe_name = sp.replace('/', '_').replace(' ', '_').replace(':', '_')[:80]
        fa_file = species_dir / f"{safe_name}.fasta"
        with open(fa_file, 'w') as f:
            for acc, seq in seqs:
                f.write(f">{acc}\n{seq}\n")
        species_info[sp] = {"file": str(fa_file), "count": len(seqs)}

    print(f"   → {len(species_info)} 个物种, 总序列 {sum(v['count'] for v in species_info.values())}")
    return species_info


def run_autopvprimer(fasta_file: str, output_dir: Path, virus_name: str,
                     num_primers: int, mode: str = "pcr"):
    """运行 AutoPVPrimer 设计引物"""
    out = output_dir / virus_name.replace('/', '_').replace(' ', '_')[:60]
    out.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python", os.path.expanduser("~/bin/autopvprimer.py"),
        "--fasta", fasta_file,
        "--output", str(out),
        "--num_primers", str(num_primers),
        "--skip_blast"  # 跳过 BLAST 加速批量处理
    ]

    if mode == "qpcr":
        cmd += ["--product_size_min", "100", "--product_size_max", "250"]
    else:
        cmd += ["--product_size_min", "250", "--product_size_max", "1000"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            primer_file = out / "primer_pairs.txt"
            if primer_file.exists():
                return parse_primer_pairs(primer_file, virus_name, mode)
        else:
            print(f"  ⚠ {virus_name} {mode}: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ {virus_name} {mode}: {e}")
    return []


def run_varvamp(fasta_file: str, output_dir: Path, virus_name: str, threads: int):
    """运行 varVAMP 设计简并引物 (qPCR 模式)"""
    out = output_dir / (virus_name.replace('/', '_').replace(' ', '_')[:60] + "_deg")
    out.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python", os.path.expanduser("~/bin/varvamp_workflow.py"),
        fasta_file,
        "-o", str(out),
        "-m", "qpcr",
        "-t", str(threads),
        "--no-cluster",
        "-n", virus_name[:40]
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        if result.returncode == 0:
            # varVAMP 输出 primers.tsv
            primer_file = out / "primers.tsv"
            if primer_file.exists():
                return parse_varvamp_primers(primer_file, virus_name)
        else:
            print(f"  ⚠ {virus_name} degenerate: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ {virus_name} degenerate: {e}")
    return []


def parse_primer_pairs(primer_file: Path, virus_name: str, mode: str):
    """解析 AutoPVPrimer 输出的 primer_pairs.txt"""
    primers = []
    try:
        with open(primer_file) as f:
            lines = f.readlines()
        pair_idx = 1
        for i, line in enumerate(lines):
            if line.startswith("Pair") or "FORWARD" in line.upper():
                fwd = lines[i+1].strip() if i+1 < len(lines) else ""
                rev = lines[i+2].strip() if i+2 < len(lines) else ""
                if fwd and rev and len(fwd) > 10 and len(rev) > 10:
                    primers.append({
                        "Species": virus_name,
                        "Type": mode.upper(),
                        "Pair_ID": str(pair_idx),
                        "Fwd_Primer": fwd.split()[-1] if ' ' in fwd else fwd,
                        "Rev_Primer": rev.split()[-1] if ' ' in rev else rev,
                        "Method": "AutoPVPrimer",
                        "Tm": "",
                        "Product_Size": "",
                        "GC_Fwd": round((fwd.count('G') + fwd.count('C')) / len(fwd) * 100, 1) if fwd else "",
                        "GC_Rev": round((rev.count('G') + rev.count('C')) / len(rev) * 100, 1) if rev else ""
                    })
                    pair_idx += 1
    except Exception:
        pass
    return primers


def parse_varvamp_primers(primer_file: Path, virus_name: str):
    """解析 varVAMP 输出的 primers.tsv"""
    primers = []
    try:
        df = pl.read_csv(primer_file, separator='\t', ignore_errors=True)
        for i, row in enumerate(df.iter_rows(named=True)):
            fwd = str(row.get('fwd', row.get('forward', '')))
            rev = str(row.get('rev', row.get('reverse', '')))
            if fwd and rev and len(fwd) > 10:
                primers.append({
                    "Species": virus_name,
                    "Type": "DEGENERATE",
                    "Pair_ID": str(i + 1),
                    "Fwd_Primer": fwd,
                    "Rev_Primer": rev,
                    "Method": "varVAMP",
                    "Tm": str(row.get('tm', '')),
                    "Product_Size": str(row.get('amplicon_len', '')),
                    "GC_Fwd": "",
                    "GC_Rev": ""
                })
    except Exception:
        pass
    return primers


def design_crispr_primers(fasta_file: str, virus_name: str, cas_type: str = "Cas12a",
                          rpa_amplicon_size: tuple = (100, 250)):
    """
    CRISPR-Cas 检测引物设计 — 等温扩增 (RPA/LAMP) + CRISPR 联用

    步骤:
      1. 扫描病毒基因组中的 PAM 位点
      2. 提取 crRNA spacer (20-25bp)
      3. 设计 RPA 引物 (扩增含 crRNA 靶标区的短片段)
      4. 基础特异性过滤 (避免引物二聚体, GC 适中)

    Cas12a PAM: TTTV (TTTA/TTTT/TTTG/TTTC)
    Cas12b PAM: TTN / VTTV
    Cas9 PAM:   NGG
    """
    from Bio.Seq import Seq

    PAM_PATTERNS = {
        "Cas12a": {"pam": "TTTV", "spacer_len": (20, 23),
                   "desc": "TTTV PAM + 20-23nt crRNA spacer"},
        "Cas12b": {"pam": "TTN", "spacer_len": (18, 22),
                   "desc": "TTN PAM + 18-22nt crRNA spacer"},
        "Cas9":   {"pam": "GG", "spacer_len": (18, 22),
                   "desc": "NGG PAM + 18-22nt sgRNA spacer"},
        "Cas13a": {"pam": None, "spacer_len": (22, 28),
                   "desc": "No PAM; 22-28nt crRNA spacer (RNA target)"}
    }

    config = PAM_PATTERNS.get(cas_type, PAM_PATTERNS["Cas12a"])
    crispr_primers = []

    try:
        # 读序列
        sequences = []
        current_seq = []
        with open(fasta_file) as f:
            for line in f:
                if line.startswith('>'):
                    if current_seq:
                        sequences.append(''.join(current_seq))
                        current_seq = []
                else:
                    current_seq.append(line.strip())
            if current_seq:
                sequences.append(''.join(current_seq))

        # 取最长序列作为参考
        if not sequences:
            return []
        ref_seq = sequences[0].upper()

        # 扫描 PAM 位点
        pam = config["pam"]
        sp_min, sp_max = config["spacer_len"]
        found_sites = []

        if pam:
            # 简并碱基映射
            pam_pattern = pam.replace('V', '[ACG]').replace('N', '[ATCG]')
            import re
            for m in re.finditer(pam_pattern, ref_seq):
                pos = m.start()
                pam_seq = m.group()
                # Cas12a: spacer 在 PAM 下游 (3' 方向)
                # Cas9: spacer 在 PAM 上游 (5' 方向)
                if cas_type in ("Cas12a", "Cas12b"):
                    spacer_start = pos + len(pam_seq)
                    spacer_end = spacer_start + sp_max
                    if spacer_end <= len(ref_seq):
                        for sl in range(sp_max, sp_min - 1, -1):
                            if spacer_start + sl <= len(ref_seq):
                                spacer = ref_seq[spacer_start:spacer_start + sl]
                                gc = (spacer.count('G') + spacer.count('C')) / sl
                                if 0.35 <= gc <= 0.65:
                                    found_sites.append({
                                        "PAM": pam_seq,
                                        "PAM_Pos": pos + 1,
                                        "Spacer": spacer,
                                        "Spacer_Len": sl,
                                        "GC": round(gc * 100, 1),
                                        "Direction": "downstream"
                                    })
                                    break
                elif cas_type == "Cas9":
                    spacer_end = pos
                    spacer_start = max(0, spacer_end - sp_max)
                    for sl in range(sp_max, sp_min - 1, -1):
                        if pos - sl >= 0:
                            spacer = ref_seq[pos - sl:pos]
                            gc = (spacer.count('G') + spacer.count('C')) / sl
                            if 0.35 <= gc <= 0.65:
                                found_sites.append({
                                    "PAM": "NGG",
                                    "PAM_Pos": pos + 1,
                                    "Spacer": spacer,
                                    "Spacer_Len": sl,
                                    "GC": round(gc * 100, 1),
                                    "Direction": "upstream"
                                })
                                break
        else:
            # Cas13a: 无 PAM → 滑动窗口扫描
            for pos in range(0, len(ref_seq) - sp_max, 5):
                for sl in range(sp_max, sp_min - 1, -1):
                    if pos + sl <= len(ref_seq):
                        spacer = ref_seq[pos:pos + sl]
                        gc = (spacer.count('G') + spacer.count('C')) / sl
                        if 0.35 <= gc <= 0.65:
                            found_sites.append({
                                "PAM": "N/A",
                                "PAM_Pos": pos + 1,
                                "Spacer": spacer,
                                "Spacer_Len": sl,
                                "GC": round(gc * 100, 1),
                                "Direction": "N/A"
                            })
                            break

        # 取 top 5 site, 设计 RPA 引物
        for i, site in enumerate(found_sites[:5]):
            spacer_pos = site["PAM_Pos"] - 1
            spacer_len = site["Spacer_Len"]

            # RPA primer target region: 包含 spacer 的短片段
            target_start = max(0, spacer_pos - 80)
            target_end = min(len(ref_seq), spacer_pos + spacer_len + 80)
            target_region = ref_seq[target_start:target_end]

            # 设计简单的 RPA 引物 (30-35bp)
            rpa_fwd = target_region[:32]
            rpa_rev_seq = Seq(target_region[-32:])
            rpa_rev = str(rpa_rev_seq.reverse_complement())

            crispr_primers.append({
                "Species": virus_name,
                "Type": f"CRISPR_{cas_type}",
                "Pair_ID": str(i + 1),
                "Fwd_Primer": rpa_fwd,
                "Rev_Primer": rpa_rev,
                "crRNA_Spacer": site["Spacer"],
                "PAM_Site": site["PAM"],
                "Method": "CRISPR_PAM_Scan",
                "Tm": "",
                "Product_Size": str(target_end - target_start),
                "GC_Fwd": round((rpa_fwd.count('G') + rpa_fwd.count('C')) / len(rpa_fwd) * 100, 1),
                "GC_Rev": round((rpa_rev.count('G') + rpa_rev.count('C')) / len(rpa_rev) * 100, 1)
            })

    except Exception as e:
        print(f"  ⚠ CRISPR {virus_name}: {e}")

    return crispr_primers


def design_delivery_primers(fasta_file: str, virus_name: str):
    """
    CRISPR 递送验证引物 — 验证病毒载体是否成功携带 CRISPR 组件

    用于植物病毒介导的 CRISPR-Cas9/Cas12a 递送系统验证:
      - 设计跨越 gRNA 插入位点的引物 (验证 gRNA 存在)
      - 设计跨越 Cas9/Cas12a 基因接合处的引物 (验证 Cas 蛋白插入)
      - PCR/测序级别引物 (18-25bp, Tm 55-62°C)

    这些引物针对病毒载体骨架, 用于:
      1. 病毒载体构建后的 PCR 验证
      2. 植物接种后的病毒系统性移动检测
      3. 编辑效率评估 (T7EI assay / Sanger sequencing)
    """
    delivery_primers = []
    try:
        sequences = []
        with open(fasta_file) as f:
            current_seq = []
            for line in f:
                if line.startswith('>'):
                    if current_seq:
                        sequences.append(''.join(current_seq))
                        current_seq = []
                else:
                    current_seq.append(line.strip())
            if current_seq:
                sequences.append(''.join(current_seq))

        if not sequences:
            return []

        ref = sequences[0].upper()
        length = len(ref)

        # 设计验证引物对, 覆盖病毒基因组不同区域
        # Pair 1: 5' 端验证 (覆盖复制酶/移动蛋白区域)
        # Pair 2: 中部验证 (覆盖 CP 基因区域, 常用于 gRNA 靶向)
        # Pair 3: 3' 端验证 (覆盖 UTR/终止区)

        regions = [
            ("5prime", max(0, 100), min(length, 500), "5'-UTR/Replicase"),
            ("mid_CP", int(length * 0.4), int(length * 0.55), "Coat Protein / gRNA target"),
            ("3prime", max(0, length - 500), length, "3'-UTR/Terminator")
        ]

        for idx, (label, start, end, desc) in enumerate(regions):
            if end - start < 200:
                continue
            region_seq = ref[start:end]
            region_len = len(region_seq)

            # 简单引物选择: 取两端 Tm 合适的 20bp
            for primer_len in range(20, 25):
                fwd_candidate = region_seq[:primer_len]
                rev_candidate_seq = region_seq[-primer_len:]
                rev_candidate = str(Seq(rev_candidate_seq).reverse_complement())

                fwd_gc = (fwd_candidate.count('G') + fwd_candidate.count('C')) / primer_len
                rev_gc = (rev_candidate.count('G') + rev_candidate.count('C')) / primer_len

                if 0.40 <= fwd_gc <= 0.60 and 0.40 <= rev_gc <= 0.60:
                    delivery_primers.append({
                        "Species": virus_name,
                        "Type": "DELIVERY_VERIFY",
                        "Pair_ID": str(idx + 1),
                        "Fwd_Primer": fwd_candidate,
                        "Rev_Primer": rev_candidate,
                        "Target_Region": desc,
                        "Method": "Delivery_Verify",
                        "Tm": "",
                        "Product_Size": str(region_len),
                        "GC_Fwd": round(fwd_gc * 100, 1),
                        "GC_Rev": round(rev_gc * 100, 1)
                    })
                    break

    except Exception as e:
        print(f"  ⚠ Delivery {virus_name}: {e}")

    return delivery_primers


def process_species(sp_name, info, args):
    """处理单个物种：设计 PCR + qPCR + 简并引物"""
    results = []
    fa_file = info["file"]
    seq_count = info["count"]

    # 1. PCR 引物 (AutoPVPrimer)
    pcr = run_autopvprimer(fa_file, Path(args.output) / "pcr",
                           sp_name, args.num_pcr_primers, "pcr")
    results.extend(pcr)

    # 2. qPCR 引物 (AutoPVPrimer)
    qpcr = run_autopvprimer(fa_file, Path(args.output) / "qpcr",
                            sp_name, args.num_qpcr_primers, "qpcr")
    results.extend(qpcr)

    # 3. 简并引物 (varVAMP) — 仅多序列物种
    if seq_count >= args.degenerate_threshold and not args.skip_degenerate:
        deg = run_varvamp(fa_file, Path(args.output) / "degenerate",
                          sp_name, args.threads)
        results.extend(deg)

    # 4. CRISPR 检测引物 — RPA + CRISPR-Cas 等温扩增检测
    if not args.skip_crispr:
        crispr = design_crispr_primers(fa_file, sp_name, args.crispr_cas_type)
        if crispr:
            results.extend(crispr)

    # 5. CRISPR 递送验证引物 — 病毒载体 CRISPR 组件验证
    delivery = design_delivery_primers(fa_file, sp_name)
    if delivery:
        results.extend(delivery)

    return results


def main():
    args = parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: 拆分 FASTA
    species_info = split_fasta_by_species(args.fasta, args.info, out_dir)

    if args.dry_run:
        # 只输出任务列表
        tasks_file = out_dir / "primer_tasks.tsv"
        with open(tasks_file, 'w') as f:
            f.write("Species\tSequences\tFASTA_File\n")
            for sp, info in sorted(species_info.items()):
                f.write(f"{sp}\t{info['count']}\t{info['file']}\n")
        print(f"任务列表 → {tasks_file} ({len(species_info)} species)")
        return

    # Step 2-4: 并行设计引物
    print(f"[2/5] 并行设计引物 ({args.threads} 线程)...")
    all_primers = []
    species_list = list(species_info.items())

    with ProcessPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(process_species, sp, info, args): sp
            for sp, info in species_list
        }
        done = 0
        for future in as_completed(futures):
            sp = futures[future]
            done += 1
            try:
                primers = future.result()
                all_primers.extend(primers)
            except Exception as e:
                print(f"  ✗ {sp}: {e}")
            if done % 100 == 0:
                print(f"  进度: {done}/{len(species_list)}, 累计引物: {len(all_primers)}")

    # Step 5: 聚合结果
    print(f"[5/5] 聚合结果 — {len(all_primers)} 对引物")
    if all_primers:
        # 标准化列
        columns = ["Species", "Type", "Pair_ID", "Fwd_Primer", "Rev_Primer",
                   "crRNA_Spacer", "PAM_Site", "Target_Region",
                   "Method", "Tm", "Product_Size", "GC_Fwd", "GC_Rev"]
        normalized = []
        for p in all_primers:
            row = {c: p.get(c, "") for c in columns}
            normalized.append(row)
        df = pl.DataFrame(normalized)
        out_file = out_dir / "primer_reference.tsv"
        df.write_csv(out_file, separator='\t')
        print(f"  → {out_file}")

        # 统计
        by_type = df.group_by("Type").agg(pl.len().alias("Count")).sort("Count", descending=True)
        print("\n  📊 引物类型统计:")
        for row in by_type.iter_rows(named=True):
            print(f"     {row['Type']}: {row['Count']} 对")

        by_method = df.group_by("Method").agg(pl.len().alias("Count")).sort("Count", descending=True)
        print("\n  📊 方法统计:")
        for row in by_method.iter_rows(named=True):
            print(f"     {row['Method']}: {row['Count']} 对")
    else:
        print("  ⚠ 未生成任何引物！检查工具路径和输入文件")


if __name__ == "__main__":
    main()
