#!/usr/bin/env python3
"""
序列比对验证 — 对长度无法确定的段名变体做最终仲裁

流程:
  1. 读取 SUSPICIOUS 段名变体 + Canonical段间长度相近
  2. 从 FASTA 提取对应序列
  3. 两两全局比对 (Bio.Align.PairwiseAligner)
  4. 计算序列 identity / coverage

判定:
  identity > 90% + coverage > 80% → SAME (合并为同一段)
  identity < 70% → DIFFERENT (不同段)
  70% ≤ identity ≤ 90% → AMBIGUOUS (需人工)

Usage:
  python resolve_segments_by_sequence.py \
      --info All_Classified_Virus_Info.tsv \
      --fasta plant.virus.fasta \
      --audit_dir segment_audit/ \
      -o segment_resolved/ --threads 20
"""
import argparse, os, sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import polars as pl

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--info", required=True)
    p.add_argument("--fasta", required=True, help="plant.virus.fasta 或 final.cluster.ref.fasta")
    p.add_argument("--audit_dir", default="segment_audit/", help="audit_segment_lengths 输出目录")
    p.add_argument("-o", "--out_dir", default="segment_resolved/")
    p.add_argument("-t", "--threads", type=int, default=10)
    p.add_argument("--min-identity", type=float, default=0.90, help="合并阈值 (default 0.90)")
    p.add_argument("--max-identity", type=float, default=0.70, help="不同段阈值 (default 0.70)")
    p.add_argument("--max-pairs", type=int, default=500, help="最多比对多少对")
    return p.parse_args()


def load_fasta(fasta_path):
    """加载 FASTA, 返回 {accession: sequence}"""
    print(f"加载 FASTA: {fasta_path}")
    seqs = {}
    current_acc = None
    current_seq = []
    with open(fasta_path) as f:
        for line in f:
            if line.startswith('>'):
                if current_acc and current_seq:
                    seqs[current_acc] = ''.join(current_seq)
                current_acc = line[1:].split()[0].split('.')[0].upper()
                current_seq = []
            else:
                current_seq.append(line.strip())
        if current_acc and current_seq:
            seqs[current_acc] = ''.join(current_seq)
    print(f"  → {len(seqs)} 条序列")
    return seqs


def align_pair(seq1, seq2, min_identity=0.90):
    """全局比对两条序列, 返回 (identity, coverage, aligned_len)"""
    from Bio.Align import PairwiseAligner
    aligner = PairwiseAligner()
    aligner.mode = 'global'
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -5
    aligner.extend_gap_score = -2

    try:
        aln = aligner.align(seq1, seq2)
        if not aln:
            return 0, 0, 0
        best = aln[0]
        # count matches
        matches = sum(1 for a, b in zip(best[0], best[1]) if a == b)
        aln_len = max(len(best[0]), len(best[1]))
        identity = matches / aln_len if aln_len > 0 else 0
        coverage = aln_len / max(len(seq1), len(seq2)) if max(len(seq1), len(seq2)) > 0 else 0
        return round(identity, 4), round(coverage, 4), aln_len
    except Exception:
        return 0, 0, 0


def resolve_pair(task):
    """处理一对段名变体"""
    tax, canon_acc, canon_seg, canon_len, \
        variant_acc, variant_seg, variant_len, seqs, args = task

    s1 = seqs.get(canon_acc, "")
    s2 = seqs.get(variant_acc, "")
    if not s1 or not s2:
        return {**task, "identity": None, "coverage": None, "verdict": "NO_SEQ"}

    identity, coverage, aln_len = align_pair(s1, s2)

    if identity >= args.min_identity and coverage >= 0.8:
        verdict = "SAME"
    elif identity <= args.max_identity:
        verdict = "DIFFERENT"
    else:
        verdict = "AMBIGUOUS"

    return {
        "TaxID": tax,
        "Canon_Acc": canon_acc, "Canon_Seg": canon_seg, "Canon_Len": canon_len,
        "Variant_Acc": variant_acc, "Variant_Seg": variant_seg, "Variant_Len": variant_len,
        "Identity": identity, "Coverage": coverage, "Aln_Len": aln_len,
        "Verdict": verdict
    }


def main():
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    # 加载序列
    seqs = load_fasta(args.fasta)

    # 读取长度审计的 SUSPICIOUS TSV
    suspicious_file = os.path.join(args.audit_dir, "suspicious.tsv")
    if not os.path.exists(suspicious_file):
        print(f"未找到 {suspicious_file}, 先运行 audit_segment_lengths.py")
        sys.exit(1)

    # 加载元数据获取 Accession → TaxID mapping
    info = pl.read_csv(args.info, separator='\t', ignore_errors=True, truncate_ragged_lines=True)
    taxid_to_canon = {}
    for row in info.iter_rows(named=True):
        acc = str(row.get("Accession", "")).split('.')[0].upper()
        tax = str(row.get("Taxid", ""))
        st = str(row.get("Sequence_Type", ""))
        if "RefSeq" in st or "ICTV" in st:
            taxid_to_canon[acc] = tax

    # 构建比对任务: SUSPICIOUS 中长度差>100 的, 挑关键的比对
    suspicious = pl.read_csv(suspicious_file, separator='\t', ignore_errors=True)
    print(f"SUSPICIOUS 记录: {suspicious.height}")

    # 优先处理: 非 CDS 片段 + 长度差不太大 (< 5000bp) → 值得比对的
    tasks = []
    for row in suspicious.iter_rows(named=True):
        diff = row.get("Len_Diff", 0)
        canon_type = row.get("Canon_Type", "")
        canon_len = row.get("Canon_Len", 0)
        variant_len = row.get("NonCanon_Len", 0)
        # CDS 片段 vs 完整基因组 → 跳过 (肯定不同)
        if variant_len < 1000 and canon_len > 2000:
            continue
        # 长度差太大 → 几乎肯定不同, 也跳过
        if diff > 5000:
            continue
        tasks.append((
            row["TaxID"],
            row.get("Canon_Acc", ""), row.get("Canon_Seg", ""), canon_len,
            row.get("NonCanon_Acc", ""), row.get("NonCanon_Seg", ""), variant_len,
            seqs, args
        ))

    print(f"选定 {len(tasks[:args.max_pairs])} 对进行序列比对...")

    # 并行比对
    results = []
    with ProcessPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(resolve_pair, t): t for t in tasks[:args.max_pairs]}
        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                r = future.result()
                results.append(r)
            except Exception as e:
                pass
            if done % 50 == 0:
                print(f"  进度: {done}/{min(len(tasks), args.max_pairs)}")

    # 写入结果
    if results:
        df = pl.DataFrame(results)
        df.write_csv(os.path.join(args.out_dir, "segment_sequence_resolved.tsv"), separator='\t')

        # 统计
        print(f"\n=== 序列比对验证结果 ===")
        for v in ["SAME", "DIFFERENT", "AMBIGUOUS", "NO_SEQ"]:
            cnt = len([r for r in results if r["Verdict"] == v])
            print(f"  {v}: {cnt}")

        # SAME 的详细列表
        same = [r for r in results if r["Verdict"] == "SAME"]
        if same:
            print(f"\n=== SAME — 确认为同一段 (identity≥{args.min_identity}), 应合并: {len(same)} 对 ===")
            for r in same[:30]:
                print(f"  TaxID={r['TaxID']} {r['Variant_Seg']}({r['Variant_Len']}bp) → "
                      f"{r['Canon_Seg']}({r['Canon_Len']}bp) identity={r['Identity']:.1%} coverage={r['Coverage']:.1%}")

        # AMBIGUOUS — 需人工判断
        amb = [r for r in results if r["Verdict"] == "AMBIGUOUS"]
        if amb:
            print(f"\n=== AMBIGUOUS — identity 在 {args.max_identity*100:.0f}%-{args.min_identity*100:.0f}% 之间, 需人工: {len(amb)} 对 ===")
            for r in amb[:20]:
                print(f"  TaxID={r['TaxID']} {r['Variant_Seg']}({r['Variant_Len']}bp) → "
                      f"{r['Canon_Seg']}({r['Canon_Len']}bp) identity={r['Identity']:.1%}")


if __name__ == "__main__":
    main()
