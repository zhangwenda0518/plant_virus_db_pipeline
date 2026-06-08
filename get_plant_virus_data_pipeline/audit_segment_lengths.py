#!/usr/bin/env python3
"""
用序列长度验证段名规范化: 同 TaxID 内，core 匹配的段名变体，长度是否一致？

逻辑:
  1. core 匹配 + 长度差 ≤100bp → 确认同一段 (CONFIRMED)
  2. core 匹配 + 长度差 >100bp → 可疑，需人工审查 (SUSPICIOUS)
  3. canonical 段名之间长度差 >100bp → 确认不同段 (DIFFERENT)
  4. core 无法匹配的变体 → 新段候选 (UNMATCHED)

Usage:
  python audit_segment_lengths.py \
      --info All_Classified_Virus_Info.tsv \
      -o segment_audit/
"""
import polars as pl
import argparse, os
from collections import defaultdict

def segment_core(seg: str) -> str:
    if not seg: return ""
    seg = seg.upper()
    for p in sorted(['GENOMICRNA','GENOMICDNA','SUBGENOMICRNA','DEFECTIVERNA',
                     'DSRNA','DSDNA','RNA','DNA','SEGMENT','COMPONENT'],
                    key=len, reverse=True):
        if seg.startswith(p) and len(seg) > len(p):
            seg = seg[len(p):]
            break
    return seg.strip()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--info", required=True, help="All_Classified_Virus_Info.tsv")
    p.add_argument("-o", "--out_dir", default="segment_audit/")
    p.add_argument("--len-tol", type=int, default=100, help="长度容差 (bp), 默认 100")
    p.add_argument("--top", type=int, default=100, help="报告展示 Top N")
    args = p.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    df = pl.read_csv(args.info, separator='\t', ignore_errors=True, truncate_ragged_lines=True)
    seg = df.filter(pl.col("Category").str.starts_with("Segmented_"))

    is_canonical = lambda st: ("RefSeq" in str(st) or "ICTV" in str(st)) if st else False

    # 按 TaxID 收集: (acc, raw_seg, clean_seg, length, is_canonical, seq_type)
    taxid_data = defaultdict(list)
    for row in seg.iter_rows(named=True):
        tax = str(row["Taxid"])
        seg_val = str(row.get("Segment", "")).strip()
        if not seg_val:
            continue
        clean = seg_val.replace(" ", "").replace("-", "").replace("_", "").upper()
        length = int(row.get("Length", 0)) if row.get("Length") else 0
        st = str(row.get("Sequence_Type", ""))
        taxid_data[tax].append({
            "acc": row["Accession"],
            "raw_seg": seg_val,
            "clean": clean,
            "core": segment_core(clean),
            "length": length,
            "canonical": is_canonical(st),
            "seq_type": st
        })

    # 分析每个 TaxID
    confirmed = []     # core匹配 + 长度差≤100
    suspicious = []    # core匹配 + 长度差>100
    canonical_diff = [] # canonical 段之间的长度差 (验证不同段)
    unmatched = []     # core 无法匹配 canonical 的变体

    for tax, records in taxid_data.items():
        canon = [r for r in records if r["canonical"]]
        non_canon = [r for r in records if not r["canonical"]]

        if not canon:
            continue

        # 建立 core → canonical record 映射
        core_map = {}
        for cr in canon:
            c = cr["core"]
            if c and c not in core_map:
                core_map[c] = cr

        # canonical 段之间的长度验证
        canon_cores = list(core_map.keys())
        for i in range(len(canon_cores)):
            for j in range(i+1, len(canon_cores)):
                ci, cj = canon_cores[i], canon_cores[j]
                ri, rj = core_map[ci], core_map[cj]
                diff = abs(ri["length"] - rj["length"])
                canonical_diff.append({
                    "TaxID": tax, "Core1": ci, "Core2": cj,
                    "Seg1": ri["clean"], "Seg2": rj["clean"],
                    "Len1": ri["length"], "Len2": rj["length"],
                    "Diff": diff, "Status": "SAME_SEGMENT?" if diff <= args.len_tol else "DIFFERENT"
                })

        # 非 canonical → 尝试匹配 canonical
        for nr in non_canon:
            core = nr["core"]
            matched = core_map.get(core)
            if matched:
                diff = abs(nr["length"] - matched["length"])
                entry = {
                    "TaxID": tax,
                    "NonCanon_Seg": nr["clean"], "NonCanon_Len": nr["length"],
                    "NonCanon_Acc": nr["acc"], "NonCanon_Type": nr["seq_type"],
                    "Canon_Seg": matched["clean"], "Canon_Len": matched["length"],
                    "Canon_Acc": matched["acc"], "Canon_Type": matched["seq_type"],
                    "Core": core, "Len_Diff": diff,
                    "Status": "CONFIRMED" if diff <= args.len_tol else "SUSPICIOUS"
                }
                if diff <= args.len_tol:
                    confirmed.append(entry)
                else:
                    suspicious.append(entry)
            else:
                # 看看能不能通过其他方式匹配 (相似长度?)
                best = None
                for cr in canon:
                    diff = abs(nr["length"] - cr["length"])
                    if diff <= args.len_tol:
                        best = (cr, diff)
                        break
                unmatched.append({
                    "TaxID": tax,
                    "NonCanon_Seg": nr["clean"], "NonCanon_Len": nr["length"],
                    "NonCanon_Acc": nr["acc"],
                    "Best_Canon_Seg": best[0]["clean"] if best else "N/A",
                    "Best_Len_Diff": best[1] if best else "N/A",
                    "Status": "LEN_MATCH" if best else "NO_MATCH"
                })

    # 写入报告
    out = os.path.join(args.out_dir, "segment_length_audit.txt")
    with open(out, 'w', encoding='utf-8') as f:
        f.write("=" * 90 + "\n")
        f.write("段名规范化 — 序列长度验证报告\n")
        f.write(f"长度容差: ≤{args.len_tol}bp 视为同一段\n")
        f.write("=" * 90 + "\n\n")

        f.write(f"CONFIRMED (core匹配 + 长度差≤{args.len_tol}bp): {len(confirmed)} 个变体\n")
        f.write(f"SUSPICIOUS (core匹配 + 长度差>{args.len_tol}bp): {len(suspicious)} 个\n")
        f.write(f"UNMATCHED (core无法匹配): {len(unmatched)} 个\n")
        f.write(f"Canonical段间长度验证: {len(canonical_diff)} 对\n\n")

        # CONFIRMED 样例
        f.write("-" * 90 + "\n")
        f.write(f"CONFIRMED — 长度验证通过的段名匹配 (前 {args.top}):\n")
        f.write("-" * 90 + "\n")
        f.write(f"{'TaxID':<10} {'变体段名':<20} {'len':>6} {'→规范段名':<20} {'len':>6} {'差':>6} {'状态'}\n")
        for entry in confirmed[:args.top]:
            f.write(f"{entry['TaxID']:<10} {entry['NonCanon_Seg']:<20} {entry['NonCanon_Len']:>6} "
                    f"→{entry['Canon_Seg']:<20} {entry['Canon_Len']:>6} {entry['Len_Diff']:>6} {entry['Status']}\n")

        # SUSPICIOUS
        if suspicious:
            f.write(f"\n{'='*90}\n")
            f.write(f"SUSPICIOUS — core匹配但长度差>{args.len_tol}bp, 需人工审查:\n")
            f.write(f"{'='*90}\n")
            f.write(f"{'TaxID':<10} {'变体段名':<20} {'len':>6} {'→规范段名':<20} {'len':>6} {'差':>6} {'规范类型'}\n")
            for entry in suspicious[:args.top]:
                f.write(f"{entry['TaxID']:<10} {entry['NonCanon_Seg']:<20} {entry['NonCanon_Len']:>6} "
                        f"→{entry['Canon_Seg']:<20} {entry['Canon_Len']:>6} {entry['Len_Diff']:>6} {entry['Canon_Type']}\n")

        # Canonical 段间验证 — 找出长度太接近的 canonical 段 (可能实际是同一段)
        close_canon = [d for d in canonical_diff if d["Diff"] <= args.len_tol]
        if close_canon:
            f.write(f"\n{'='*90}\n")
            f.write(f"⚠  Canonical 段之间长度差≤{args.len_tol}bp ({len(close_canon)} 对) — 可能是同一段?\n")
            f.write(f"{'='*90}\n")
            f.write(f"{'TaxID':<10} {'段1':<20} {'len':>6} {'段2':<20} {'len':>6} {'差':>6}\n")
            for d in close_canon[:args.top]:
                f.write(f"{d['TaxID']:<10} {d['Seg1']:<20} {d['Len1']:>6} {d['Seg2']:<20} {d['Len2']:>6} {d['Diff']:>6}\n")

        # UNMATCHED
        if unmatched:
            f.write(f"\n{'='*90}\n")
            f.write(f"UNMATCHED — core无法匹配 canonical 的段名变体:\n")
            f.write(f"{'='*90}\n")
            len_match = [u for u in unmatched if u["Status"] == "LEN_MATCH"]
            no_match = [u for u in unmatched if u["Status"] == "NO_MATCH"]
            f.write(f"  长度匹配 (len差≤{args.len_tol}): {len(len_match)} 个\n")
            f.write(f"  无匹配: {len(no_match)} 个\n")
            for u in no_match[:30]:
                f.write(f"  TaxID={u['TaxID']} seg={u['NonCanon_Seg']} len={u['NonCanon_Len']}\n")

    print(f"Done → {out}")

    # 同时输出 TSV 便于进一步分析
    if confirmed:
        pl.DataFrame(confirmed).write_csv(os.path.join(args.out_dir, "confirmed.tsv"), separator='\t')
    if suspicious:
        pl.DataFrame(suspicious).write_csv(os.path.join(args.out_dir, "suspicious.tsv"), separator='\t')

if __name__ == "__main__":
    main()
