#!/usr/bin/env python3
"""
小数据 BLAST 批处理诊断脚本
==============================
使用方式 (在服务器上):
  python test_blast_batch.py --blast-db ~/database/nt-db/blast_db/nt --input all_primers.tsv
"""

import sys, os, argparse, tempfile, subprocess
from pathlib import Path

# ============================================================
# 测试 1: 单对引物手动 blastn (不经过 Python 包装)
# ============================================================
def test_raw_blastn(blast_db, fwd, rev):
    """直接用 blastn 命令测试单对引物"""
    print("=" * 60)
    print("测试 1: 原始 blastn 命令测试")
    print("=" * 60)
    fwd = fwd.strip(); rev = rev.strip()
    print(f"  Fwd: {fwd} ({len(fwd)}bp)")
    print(f"  Rev: {rev} ({len(rev)}bp)")

    # 测试 a: 单独 blast fwd
    with tempfile.NamedTemporaryFile(mode='w', suffix='.fa', delete=False) as f:
        f.write(f">fwd\n{fwd}\n")
        tmp_fwd = f.name

    cmd = ["blastn", "-task", "blastn-short", "-db", blast_db,
           "-query", tmp_fwd, "-word_size", "7", "-evalue", "1000",
           "-max_target_seqs", "5", "-num_threads", "4",
           "-outfmt", "6 qseqid sseqid salltitles evalue bitscore length pident gaps"]
    print(f"  运行: {' '.join(cmd[:6])} ...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    os.unlink(tmp_fwd)

    fwd_lines = [l for l in r.stdout.strip().split('\n') if l]
    print(f"  Fwd 单独 blast: returncode={r.returncode}, 命中行数={len(fwd_lines)}")
    if r.stderr: print(f"  stderr: {r.stderr[:500]}")
    if fwd_lines:
        print(f"  前3行:")
        for line in fwd_lines[:3]:
            print(f"    {line[:200]}")

    # 测试 b: 单独 blast rev
    with tempfile.NamedTemporaryFile(mode='w', suffix='.fa', delete=False) as f2:
        f2.write(f">rev\n{rev}\n")
        tmp_rev = f2.name

    cmd2 = ["blastn", "-task", "blastn-short", "-db", blast_db,
            "-query", tmp_rev, "-word_size", "7", "-evalue", "1000",
            "-max_target_seqs", "5", "-num_threads", "4",
            "-outfmt", "6 qseqid sseqid salltitles evalue bitscore length pident gaps"]
    r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
    os.unlink(tmp_rev)

    rev_lines = [l for l in r2.stdout.strip().split('\n') if l]
    print(f"  Rev 单独 blast: returncode={r2.returncode}, 命中行数={len(rev_lines)}")
    if r2.stderr: print(f"  stderr: {r2.stderr[:500]}")
    if rev_lines:
        print(f"  前3行:")
        for line in rev_lines[:3]:
            print(f"    {line[:200]}")

    # 测试 c: fwd+rev 拼接 (模拟当前代码)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.fa', delete=False) as f3:
        f3.write(f">concat\n{fwd}{rev}\n")
        tmp_concat = f3.name

    cmd3 = ["blastn", "-task", "blastn-short", "-db", blast_db,
            "-query", tmp_concat, "-word_size", "7", "-evalue", "1000",
            "-max_target_seqs", "5", "-num_threads", "4",
            "-outfmt", "6 qseqid sseqid salltitles evalue bitscore length pident gaps"]
    r3 = subprocess.run(cmd3, capture_output=True, text=True, timeout=300)
    os.unlink(tmp_concat)

    concat_lines = [l for l in r3.stdout.strip().split('\n') if l]
    print(f"  Fwd+Rev 拼接 blast: returncode={r3.returncode}, 命中行数={len(concat_lines)}")
    if r3.stderr: print(f"  stderr: {r3.stderr[:500]}")
    if concat_lines:
        print(f"  前3行:")
        for line in concat_lines[:3]:
            print(f"    {line[:200]}")

    success = len(fwd_lines) > 0 or len(rev_lines) > 0
    print(f"\n  结论: {'OK - blastn 可以正常返回结果' if success else 'FAIL - blastn 无命中! 请检查 blast_db 路径'}")
    return success


# ============================================================
# 测试 2: 调用 _run_one_blast_batch (当前代码)
# ============================================================
def test_run_one_batch(blast_db, fwd, rev, species_name):
    """测试当前的 _run_one_blast_batch 函数"""
    print("\n" + "=" * 60)
    print("测试 2: _run_one_blast_batch 函数测试")
    print("=" * 60)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from step3_validate_primers import _run_one_blast_batch

    tasks = [(0, fwd.strip(), rev.strip(), species_name or "TestVirus", "/tmp", "test_blast")]

    try:
        results = _run_one_blast_batch(tasks, Path(blast_db), 4)
    except Exception as e:
        print(f"  FAIL - 异常: {e}")
        import traceback; traceback.print_exc()
        return False

    print(f"  返回结果数: {len(results)}")
    if results:
        for idx, r in results.items():
            print(f"  [{idx}] Target={r.get('BLAST_Fwd_TargetHits',0)} "
                  f"Plant={r.get('BLAST_Fwd_PlantHits',0)} "
                  f"Other={r.get('BLAST_Fwd_OtherHits',0)} "
                  f"Spec={r.get('BLAST_Specificity_Score',0)}% "
                  f"Risk={r.get('BLAST_Plant_Risk','?')}")

            # 检查 CSV 是否写入
            csv_path = r.get("BLAST_ResultFile", "")
            if csv_path and Path(csv_path).exists():
                import polars as pl
                try:
                    df = pl.read_csv(csv_path)
                    print(f"  CSV 行数: {len(df)}, 文件: {csv_path}")
                    if len(df) > 0:
                        print(f"  列: {df.columns}")
                except Exception as e:
                    print(f"  CSV 读取失败: {e}")
            else:
                print(f"  CSV 未生成 (path={csv_path})")

        has_hits = any(r.get('BLAST_Fwd_TargetHits', 0) + r.get('BLAST_Fwd_PlantHits', 0) + r.get('BLAST_Fwd_OtherHits', 0) > 0 for r in results.values())
        print(f"\n  结论: {'OK - 有 BLAST 命中' if has_hits else 'WARN - 无命中 (可能是靶标物种不在nt库中)'}")
        return True
    else:
        print("  结论: FAIL - 返回空结果!")
        return False


# ============================================================
# 测试 3: 读取 all_primers.tsv 前 N 条做小批量测试
# ============================================================
def test_small_batch(blast_db, input_tsv, n_pairs=10):
    """从 all_primers.tsv 取前 N 对引物，调用 step3 BLAST 验证"""
    print("\n" + "=" * 60)
    print(f"测试 3: 小批量 step3 BLAST ({n_pairs} 对引物)")
    print("=" * 60)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from step3_validate_primers import _batch_local_blast

    if not Path(input_tsv).exists():
        print(f"  错误: 找不到 {input_tsv}")
        return False

    # 用 csv.DictReader 读取 (避免 polars 问题)
    import csv
    rows = []
    with open(input_tsv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            rows.append(row)
            if len(rows) >= n_pairs:
                break

    print(f"  读取到 {len(rows)} 行")

    # 检查列名
    if rows:
        print(f"  列名: {list(rows[0].keys())}")
        has_fwd = 'Fwd_Seq' in rows[0]
        has_rev = 'Rev_Seq' in rows[0]
        print(f"  Fwd_Seq 存在: {has_fwd}, Rev_Seq 存在: {has_rev}")

        if not has_fwd or not has_rev:
            print("  FAIL - 缺少 Fwd_Seq/Rev_Seq 列!")
            return False

        # 显示前3个序列
        for i, row in enumerate(rows[:3]):
            fwd = row.get("Fwd_Seq", "")
            rev = row.get("Rev_Seq", "")
            sp = row.get("Species", "")
            print(f"  [{i}] {sp}: Fwd={fwd[:20]}...({len(fwd)}bp) Rev={rev[:20]}...({len(rev)}bp)")

    # 构建批量任务
    output_dir = Path("/tmp/test_blast_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    batch_tasks = []
    for i, row in enumerate(rows):
        fwd = str(row.get("Fwd_Seq", "")).strip()
        rev = str(row.get("Rev_Seq", "")).strip()
        sp = str(row.get("Species", "unknown")).strip()
        pid = f"test_{i}"
        if fwd and rev:
            batch_tasks.append((i, fwd, rev, sp, str(output_dir), pid))

    print(f"  有效任务: {len(batch_tasks)}/{len(rows)} (跳过 {len(rows)-len(batch_tasks)} 个空序列)")

    if not batch_tasks:
        print("  FAIL - 无有效任务!")
        return False

    # 单批测试 (batch_size=0 = 全放一批)
    print(f"  开始 BLAST (batch_size=0, 全部 {len(batch_tasks)} 对一起跑)...")
    import time
    t0 = time.time()
    results = _batch_local_blast(batch_tasks, blast_db, threads=4, batch_size=0)
    elapsed = time.time() - t0
    print(f"  耗时: {elapsed:.1f}s, 结果数: {len(results)}")

    hit_count = 0
    for i, r in sorted(results.items()):
        th = r.get('BLAST_Fwd_TargetHits', 0)
        ph = r.get('BLAST_Fwd_PlantHits', 0)
        oh = r.get('BLAST_Fwd_OtherHits', 0)
        sp = r.get('BLAST_Specificity_Score', 0)
        if th + ph + oh > 0:
            hit_count += 1
            print(f"  [{i}] Target={th} Plant={ph} Other={oh} Spec={sp}%")

    zero_hits = len(results) - hit_count
    if zero_hits > 0:
        print(f"  {zero_hits} 对引物无命中")

    print(f"\n  结论: {hit_count}/{len(results)} 有命中, {zero_hits} 无命中")
    return hit_count > 0


# ============================================================
# 主入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="BLAST 批处理诊断")
    parser.add_argument("--blast-db", required=True, help="本地 BLAST 数据库路径")
    parser.add_argument("--input", default="", help="all_primers.tsv 路径 (可选)")
    parser.add_argument("--fwd", default="CGTCTCGGTGAGATAGCTATA", help="测试用正向引物")
    parser.add_argument("--rev", default="GTAGGAGCTCAGTAGATGACA", help="测试用反向引物")
    parser.add_argument("--species", default="TestVirus", help="测试用物种名")
    parser.add_argument("--n-pairs", type=int, default=10, help="小批量测试引物对数")
    parser.add_argument("--all", action="store_true", help="全部测试 (包括小批量)")
    args = parser.parse_args()

    if not Path(args.blast_db + ".nsq").exists() and not Path(args.blast_db + ".00.nsq").exists():
        print(f"错误: BLAST 数据库不存在: {args.blast_db}")
        print(f"  检查: {args.blast_db}.nsq 或 {args.blast_db}.00.nsq")
        sys.exit(1)

    print(f"BLAST DB: {args.blast_db}")
    print(f"测试引物: Fwd={args.fwd} Rev={args.rev}")
    print()

    ok1 = test_raw_blastn(args.blast_db, args.fwd, args.rev)
    ok2 = test_run_one_batch(args.blast_db, args.fwd, args.rev, args.species)

    if args.input or args.all:
        inp = args.input or str(Path(__file__).resolve().parent / "designed_primers" / "all_primers.tsv")
        if Path(inp).exists():
            ok3 = test_small_batch(args.blast_db, inp, args.n_pairs)
        else:
            print(f"\n跳过测试3: 找不到 {inp}")
            ok3 = None

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    if ok1 and ok2:
        print("  测试1-2 通过: BLAST 基本功能正常")
        print("  如果之前全量运行 hits=0，问题可能在:")
        print("    1. all_primers.tsv 中 Fwd_Seq/Rev_Seq 为空")
        print("    2. blastn 多批次并行时资源竞争 (内存不足)")
        print("    3. blastn-short 对大数据库的索引加载问题")
    else:
        print("  测试失败! 请根据上面的错误信息排查")
        if not ok1:
            print("  -> 原始 blastn 命令失败: 检查 blast_db 路径和 blastn 版本")
        if not ok2:
            print("  -> _run_one_blast_batch 失败: 检查 Python 环境和依赖")


if __name__ == "__main__":
    main()
