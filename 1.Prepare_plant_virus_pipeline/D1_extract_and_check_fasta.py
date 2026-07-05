#!/usr/bin/env python3
"""
D1: 病毒序列比对与提取 (加速版)

优化:
  - FASTA 索引缓存 (zgrep 一次生成 .idx.tsv, 后续直接读缓存)
  - seqkit grep -j 并行提取 (若安装了 seqkit)
  - 回退 Python 流式提取

Usage:
  python D1_extract_and_check_fasta.py -t Plant.tsv -f AllNucleotide.fa.gz -o out/
"""
import polars as pl
import os, sys, time, argparse, gzip, shutil, subprocess


def build_or_load_index(fasta_path):
    """Build FASTA index or load cached .idx.tsv."""
    idx_path = fasta_path + ".idx.tsv"

    # Try loading cached index
    if os.path.exists(idx_path):
        try:
            df = pl.read_csv(idx_path, separator='\t',
                            schema={"Base_Accession": pl.Utf8, "Fasta_ID": pl.Utf8})
            if df.height > 0:
                print(f"   📂 加载缓存索引: {idx_path} ({df.height:,} 条)")
                return df
        except Exception:
            pass

    print(f"   🔧 构建 FASTA 索引...")
    t0 = time.time()

    # Build index: decompress → grep headers → parse
    rgzip = shutil.which("rapidgzip")
    if rgzip:
        sh_cmd = f'set -o pipefail; {rgzip} -d -c -P 0 "{fasta_path}" | grep "^>"'
    else:
        sh_cmd = f'set -o pipefail; zgrep "^>" "{fasta_path}"'

    result = subprocess.run(['bash', '-c', sh_cmd], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        base_to_raw = {}
        for line in result.stdout.strip().split('\n'):
            sid = line.strip().lstrip('>')
            if sid:
                base_to_raw[sid.split('.')[0]] = sid
        df = pl.DataFrame({"Base_Accession": list(base_to_raw.keys()),
                           "Fasta_ID": list(base_to_raw.values())})
        df.write_csv(idx_path, separator='\t')
        print(f"   -> 索引: {df.height:,} 条 (耗时 {time.time()-t0:.1f}s)")
        return df

    # Fallback: Python streaming
    print("   ⚠ 回退 Python 扫描...")
    base_to_raw = {}
    open_func = gzip.open if fasta_path.endswith('.gz') else open
    with open_func(fasta_path, 'rt', encoding='utf-8') as f:
        for line in f:
            if line.startswith('>'):
                raw_id = line[1:].split()[0]
                base_to_raw[raw_id.split('.')[0]] = raw_id
    df = pl.DataFrame({"Base_Accession": list(base_to_raw.keys()),
                       "Fasta_ID": list(base_to_raw.values())})
    df.write_csv(idx_path, separator='\t')
    print(f"   -> 索引: {df.height:,} 条 (耗时 {time.time()-t0:.1f}s)")
    return df


def extract_fasta_seqkit(fasta_path, output_path, id_list, n_parallel=8):
    """Use seqkit grep with parallel extraction."""
    id_file = output_path + ".ids.tmp"
    with open(id_file, 'w') as f:
        f.write('\n'.join(id_list) + '\n')

    seqkit_bin = shutil.which("seqkit")
    try:
        if seqkit_bin:
            cmd = [seqkit_bin, "grep", "-f", id_file, fasta_path, "-o", output_path, "-j", str(n_parallel)]
            print(f"   🏃 seqkit grep -j {n_parallel}...")
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        else:
            cmd = ["seqtk", "subseq", fasta_path, id_file]
            print(f"   🏃 seqtk subseq (fallback)...")
            with open(output_path, 'w') as out_f:
                subprocess.run(cmd, check=True, capture_output=False, stdout=out_f)
    finally:
        if os.path.exists(id_file):
            os.remove(id_file)

    result = subprocess.run(["grep", "-c", "^>", output_path], capture_output=True, text=True)
    return int(result.stdout.strip()) if result.returncode == 0 else 0


def extract_fasta_python(fasta_path, output_path, target_ids):
    """Pure Python streaming extraction (fallback)."""
    matched = 0
    open_func = gzip.open if fasta_path.endswith('.gz') else open
    target = set(target_ids)
    with open_func(fasta_path, 'rt', encoding='utf-8') as f_in, \
         open(output_path, 'w', encoding='utf-8') as f_out:
        write_flag = False
        for line in f_in:
            if line.startswith('>'):
                rid = line[1:].split()[0]
                write_flag = rid in target
                if write_flag:
                    f_out.write(line)
                    matched += 1
            elif write_flag:
                f_out.write(line)
    return matched


def main():
    p = argparse.ArgumentParser(description="D1: 病毒序列比对与提取 (加速版)")
    p.add_argument("-t", "--tsv", required=True)
    p.add_argument("-f", "--fasta", required=True)
    p.add_argument("-o", "--out_dir", default="Database_Update")
    p.add_argument("-j", "--threads", type=int, default=16)
    args = p.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    prefix = os.path.splitext(os.path.basename(args.tsv))[0]
    t_start = time.time()

    print("=" * 60)
    print(f"  D1 序列提取 | 目标: {prefix}")
    print("=" * 60)

    # 1. Load target TSV
    print(f"\n[1] 加载目标 TSV: {args.tsv}")
    target = pl.read_csv(args.tsv, separator='\t').with_columns(
        pl.col("Accession").cast(pl.Utf8).str.split(".").list.first().alias("Base_Accession")
    )
    print(f"    待检查记录: {target.height:,}")

    # 2. Load/build FASTA index
    print(f"\n[2] FASTA 索引: {args.fasta}")
    idx_df = build_or_load_index(args.fasta)

    # 3. Join
    print(f"\n[3] 比对...")
    t3 = time.time()
    existing = target.join(idx_df, on="Base_Accession", how="inner")
    missing = target.join(idx_df, on="Base_Accession", how="anti").drop("Base_Accession")
    existing_ids = set(existing["Fasta_ID"].to_list())
    print(f"    命中: {existing.height:,}  |  缺失: {missing.height:,}  (耗时 {time.time()-t3:.2f}s)")

    # 4. Extract FASTA
    out_fasta = os.path.join(args.out_dir, f"{prefix}_Extracted_Sequences.fasta")
    if existing.height > 0:
        print(f"\n[4] 提取序列...")
        t4 = time.time()
        try:
            n = extract_fasta_seqkit(args.fasta, out_fasta, list(existing_ids), args.threads)
        except (subprocess.CalledProcessError, FileNotFoundError):
            n = extract_fasta_python(args.fasta, out_fasta, list(existing_ids))
        print(f"    提取完成: {n:,} 条序列 (耗时 {time.time()-t4:.1f}s)")
        if n < existing.height * 0.9:
            print(f"   ⚠ 提取率偏低! 请求 {existing.height:,} 条, 实得 {n:,} 条, 检查索引")

    # 5. Save metadata
    print(f"\n[5] 保存元数据...")
    existing_meta = os.path.join(args.out_dir, f"{prefix}_Existing_Metadata.tsv")
    missing_meta = os.path.join(args.out_dir, f"{prefix}_Missing_Metadata.tsv")
    missing_txt = os.path.join(args.out_dir, f"{prefix}_missing_accessions.txt")

    if existing.height > 0:
        existing.drop(["Base_Accession", "Fasta_ID"]).write_csv(existing_meta, separator='\t')
    if missing.height > 0:
        missing.write_csv(missing_meta, separator='\t')
        with open(missing_txt, 'w') as f:
            f.write('\n'.join(missing["Accession"].to_list()) + '\n')
        api_key = os.environ.get("NCBI_API_KEY", "YOUR_API_KEY_HERE")
        print(f"\n💡 下载缺失序列 (datasets CLI):")
        print(f'   datasets download virus genome accession --inputfile {os.path.basename(missing_txt)} --filename {prefix}_viruses.zip --api-key "{api_key}"')
    else:
        print("   🎉 全部命中, 无缺失!")

    print(f"\n⏱️  总耗时: {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()
