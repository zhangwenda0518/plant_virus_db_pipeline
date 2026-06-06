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
        df = pl.DataFrame(all_primers)
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
