#!/usr/bin/env python3
"""
Step 2: 核心引物设计引擎 (v2 稳定版)
========================================================================
四种设计策略: A-PCR保守 / B-qPCR+探针 / C-简并 / D-平铺
保留原始输出风格 + 所有关键修复
"""
import argparse, os, sys, math, subprocess
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import polars as pl
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqUtils import gc_fraction

try:
    import primer3; PRIMER3_OK = True
except ImportError:
    PRIMER3_OK = False
try:
    from tqdm import tqdm; TQDM_OK = True
except ImportError:
    TQDM_OK = False

# ========== MSA ==========
def run_msa(sequences, aligner="auto"):
    if len(sequences) < 2 or aligner == "no":
        return [s for s in sequences if s]
    import shutil, tempfile
    tools = []
    if aligner == "auto":
        for cmd in ["mafft", "muscle", "clustalo"]:
            if shutil.which(cmd): tools.append(cmd)
    elif shutil.which(aligner): tools.append(aligner)
    if not tools:
        min_len = min(len(s) for s in sequences if s)
        return [s[:min_len] for s in sequences if s]
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fa', delete=False, encoding='utf-8') as f:
            tmpl_fa = f.name
            for i, s in enumerate(sequences): f.write(f'>seq_{i}\n{s}\n')
        out_fa = tmpl_fa + ".aln"
        tool = tools[0]
        if tool == "mafft":
            args_list = ["mafft", "--auto", "--adjustdirection", "--quiet", tmpl_fa]
            with open(out_fa, 'w') as out_handle:
                result = subprocess.run(args_list, stdout=out_handle, stderr=subprocess.PIPE, text=True, timeout=1200)
        elif tool == "muscle":
            args_list = ["muscle", "-align", tmpl_fa, "-output", out_fa]
            result = subprocess.run(args_list, capture_output=True, text=True, timeout=1200)
        else:
            args_list = ["clustalo", "-i", tmpl_fa, "-o", out_fa, "--force"]
            result = subprocess.run(args_list, capture_output=True, text=True, timeout=1200)
        if result.returncode != 0:
            raise RuntimeError(f"{tool} rc={result.returncode}")
    except Exception as e:
        for f in [tmpl_fa, out_fa]:
            try: os.unlink(f)
            except: pass
        min_len = min(len(s) for s in sequences if s)
        return [s[:min_len] for s in sequences if s]
    aligned = []
    try:
        for record in SeqIO.parse(out_fa, "fasta"):
            aligned.append(str(record.seq).upper())  # 修复: 强制大写
    except Exception:
        aligned = _parse_fasta_stdout(result.stdout) if tool == "mafft" else []
    for f in [tmpl_fa, out_fa]:
        try: os.unlink(f)
        except: pass
    if aligned:
        print(f"      MSA ({tool}): {len(aligned)} 条, 长度 {len(aligned[0])}bp")
        return aligned
    min_len = min(len(s) for s in sequences if s)
    return [s[:min_len] for s in sequences if s]

def _parse_fasta_stdout(text):
    if not text: return []
    from collections import defaultdict as _dd
    seqs = _dd(list)
    cid = None
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        if line.startswith('>'): cid = line[1:].split()[0]
        elif cid: seqs[cid].append(line.replace(' ','').upper())
    return [''.join(blocks) for blocks in seqs.values()] if seqs else []

# ========== Shannon 熵保守区 ==========
def find_conserved_regions(sequences, window=100, step=50, max_entropy=0.5,
                           do_align=True, aligner="auto", ignore_gap=False,
                           pre_aligned=None):
    if not sequences: return []
    if pre_aligned is not None: aligned = pre_aligned
    elif do_align and len(sequences) > 1: aligned = run_msa(sequences, aligner)
    elif len(sequences) > 1:
        min_len = min(len(s) for s in sequences if s); aligned = [s[:min_len] for s in sequences if s]
    else: aligned = [s for s in sequences if s]
    if not aligned: return []
    aln_len = len(aligned[0])
    if aln_len < window: return [(0, aln_len)] if aln_len >= 150 else []
    wins = []
    for start in range(0, aln_len - window, step):
        end = start + window; e_total = 0.0; valid_positions = 0
        for pos in range(start, end):
            if ignore_gap:
                if any(s[pos] == '-' for s in aligned): continue
            counts = {'A':0,'T':0,'G':0,'C':0}
            for s in aligned:
                nt = s[pos].upper()
                if nt in counts: counts[nt] += 1
            total = sum(counts.values())
            if total == 0: continue
            h = 0.0
            for c in counts.values():
                if c > 0: p = c / total; h -= p * math.log2(p)
            e_total += h; valid_positions += 1
        if valid_positions < window * 0.5: continue
        wins.append((start, end, e_total / valid_positions))
    conserved = []; i = 0
    while i < len(wins):
        if wins[i][2] <= max_entropy:
            rs, _, _ = wins[i]; re = rs + window; j = i + 1
            while j < len(wins) and wins[j][2] <= max_entropy: re = wins[j][1]; j += 1
            if re - rs >= 150: conserved.append((rs, re))
            i = j
        else: i += 1
    return conserved

# ========== IUPAC 清理 ==========
def _build_consensus(aligned):
    """多数表决法构建一致性序列"""
    if not aligned: return ""
    aln_len = len(aligned[0])
    consensus = []
    for pos in range(aln_len):
        counts = {}
        for s in aligned:
            c = s[pos].upper()
            if c in 'ATGC':
                counts[c] = counts.get(c, 0) + 1
        consensus.append(max(counts, key=counts.get) if counts else 'N')
    return ''.join(consensus)


def _filter_outliers(aligned, seqs, min_identity=0.60):
    """
    自动过滤疑似不属于同一物种的序列。
    对每条序列计算与参考序列（第一条）的 pairwise identity。
    低于 min_identity 的序列被标记为离群值，返回过滤后的序列列表。
    """
    if len(aligned) < 3:
        return aligned, seqs, []
    # 用第一条序列作为参考 (原始行为)
    ref = aligned[0].upper()
    keep_idx = [0]
    removed_names = []
    for i in range(1, len(aligned)):
        s = aligned[i].upper()
        matches = sum(1 for a, b in zip(ref, s) if a == b and a != '-')
        total = sum(1 for a, b in zip(ref, s) if a != '-' or b != '-')
        ident = matches / max(total, 1)
        if ident >= min_identity:
            keep_idx.append(i)
        else:
            removed_names.append(f"seq_{i}")
    if not removed_names:
        return aligned, seqs, []
    # 保护: 过滤掉超过半数 → 跳过(序列高度分化)
    if len(removed_names) > len(aligned) * 0.5:
        return aligned, seqs, []
    filtered_aligned = [aligned[i] for i in keep_idx]
    filtered_seqs = [seqs[i] for i in keep_idx if i < len(seqs)]
    return filtered_aligned, filtered_seqs, removed_names


def _est_tm(seq):
    """Nearest-Neighbor Tm (18-25bp 引物). 回退 Wallace 仅用于 <14bp"""
    from Bio.SeqUtils import MeltingTemp as _mt
    from Bio.Seq import Seq as _Seq
    clean = ''.join(c for c in seq.upper() if c in 'ATGC')
    if len(clean) < 14:
        return 2 * (clean.count('A') + clean.count('T')) + 4 * (clean.count('G') + clean.count('C'))
    try: return _mt.Tm_NN(_Seq(clean))
    except: return 64.9 + 41 * (clean.count('G') + clean.count('C') - 16.4) / max(len(clean), 1)


def _sanitize_for_primer3(seq):
    """非 ATGC 字符替换为 N, Primer3 会自动避开 N 区域设计引物"""
    return ''.join(c if c in 'ATGC' else 'N' for c in seq.upper())

# ========== 策略 A: PCR ==========
def design_primers(sequences, num_pairs=5, prod_min=250, prod_max=1000,
                   do_align=True, aligner="auto", ignore_gap=False,
                   pre_aligned=None, is_viroid=False):
    if not sequences: return []
    if len(sequences) > 1:
        aligned = pre_aligned
        if aligned is None and do_align: aligned = run_msa(sequences, aligner)
        cons = find_conserved_regions(sequences, do_align=False, aligner=aligner,
                                       ignore_gap=ignore_gap, pre_aligned=aligned)
    else: cons = [(0, len(sequences[0]))]
    # 无保守区 → 回退到全序列设计 (高度变异病毒 fallback)
    if not cons:
        cons = [(0, len(sequences[0].replace('-', '')))]
    ref = sequences[0].replace('-', '')
    all_p = []
    for rs, re in cons:
        if pre_aligned is not None or (len(sequences) > 1 and do_align):
            a = pre_aligned[0] if pre_aligned else sequences[0]
            rs_u = sum(1 for c in a[:rs] if c != '-')
            re_u = rs_u + sum(1 for c in a[rs:re] if c != '-')
        else: rs_u, re_u = rs, re
        if re_u - rs_u < prod_min + (40 if is_viroid else 80): continue
        region = ref[rs_u:re_u]
        p = _primer3_design(region, rs_u, num_pairs, prod_min, prod_max, is_viroid=is_viroid) if PRIMER3_OK else _simple_design(region, rs_u, num_pairs, prod_min, prod_max, is_viroid=is_viroid)
        all_p.extend(p)

    # 单参考基因组兜底: 保守区无产出 → 对 Ref 序列全长相搜
    if not all_p:
        all_p = _primer3_design(ref, 0, num_pairs*4, prod_min, prod_max, is_viroid=is_viroid) if PRIMER3_OK else _simple_design(ref, 0, num_pairs*4, prod_min, prod_max, is_viroid=is_viroid)

    all_p.sort(key=lambda x: x.get("Penalty", 999))
    # 空间多样性过滤 (借鉴 varVAMP single mode):
    #   按 Penalty 排序, 贪婪选取非重叠扩增子, 确保引物分布在基因组不同区域
    diverse = []
    overlap_min = max(prod_min // 4, 60)  # 放宽间距以提高引物对产出
    for p in all_p:
        mid = (p.get("Fwd_Start", 0) + p.get("Rev_Start", 0)) / 2
        if all(abs(mid - (d.get("Fwd_Start", 0) + d.get("Rev_Start", 0)) / 2) >= overlap_min
               for d in diverse):
            diverse.append(p)
            if len(diverse) >= num_pairs:
                break
    return diverse[:num_pairs] if diverse else all_p[:num_pairs]

def _primer3_design(seq, offset, n, pmin, pmax, is_viroid=False):
    # 类病毒降级: 放宽自二聚/端二聚限制
    self_any = 8 if is_viroid else 4
    self_end = 6 if is_viroid else 4
    try:
        res = primer3.design_primers(
            {'SEQUENCE_TEMPLATE': _sanitize_for_primer3(seq)},
            {'PRIMER_NUM_RETURN': max(20, n * 4),
             'PRIMER_PRODUCT_SIZE_RANGE': [[pmin, pmax]],
             'PRIMER_MIN_SIZE':18,'PRIMER_OPT_SIZE':21,'PRIMER_MAX_SIZE':23,
             'PRIMER_MIN_TM':52.0,'PRIMER_OPT_TM':60.0,'PRIMER_MAX_TM':63.0,
             'PRIMER_MIN_GC':40.0,'PRIMER_OPT_GC_PERCENT':50.0,'PRIMER_MAX_GC':60.0,
             'PRIMER_PAIR_MAX_DIFF_TM':3.0,
             'PRIMER_MAX_END_STABILITY':9.0,
             'PRIMER_THERMODYNAMIC_OLIGO_ALIGNMENT':1,
             'PRIMER_MAX_SELF_ANY':self_any,'PRIMER_MAX_SELF_END':self_end,
             'PRIMER_PAIR_MAX_COMPL_ANY':4,'PRIMER_PAIR_MAX_COMPL_END':4,
             'PRIMER_MAX_POLY_X':4}
        )
        out = []
        for i in range(res.get('PRIMER_PAIR_NUM_RETURNED', 0)):
            f = res.get(f'PRIMER_LEFT_{i}_SEQUENCE','')
            r = res.get(f'PRIMER_RIGHT_{i}_SEQUENCE','')
            if not f or not r: continue
            ld = res.get(f'PRIMER_LEFT_{i}', (0,0)); rd = res.get(f'PRIMER_RIGHT_{i}', (0,0))

            # 扩增子 GC 检查 (借鉴 varVAMP QAMPLICON_GC)
            amp_start = ld[0]; amp_end = min(rd[0] + rd[1], len(seq))
            if amp_end > amp_start:
                amp_seq = seq[amp_start:amp_end]
                amp_gc = (amp_seq.count('G') + amp_seq.count('C')) / len(amp_seq) * 100
                if amp_gc < 40 or amp_gc > 60:
                    continue

            out.append({"Fwd_Seq":f,"Rev_Seq":r,
                "Fwd_Start":ld[0]+offset+1,"Rev_Start":rd[0]+offset+1,
                "Fwd_Tm":round(res.get(f'PRIMER_LEFT_{i}_TM',0),1),
                "Rev_Tm":round(res.get(f'PRIMER_RIGHT_{i}_TM',0),1),
                "Product":res.get(f'PRIMER_PAIR_{i}_PRODUCT_SIZE',0),
                "GC_Fwd":round(gc_fraction(f)*100,1),"GC_Rev":round(gc_fraction(r)*100,1),
                "Penalty":round(res.get(f'PRIMER_PAIR_{i}_PENALTY',0),4),
                "Method":"Primer3"})
        return out
    except Exception: return []

def _has_dinuc_repeats(seq, max_run=4):
    """检查二核苷酸重复 (借鉴 varVAMP calc_max_dinuc_repeats)"""
    for s in [seq, seq[1:]]:
        if len(s) < 2: continue
        counter = 1
        prev = s[0:2]
        for i in range(2, len(s) - 1, 2):
            cur = s[i:i+2]
            if cur == prev:
                counter += 1
                if counter > max_run:
                    return True
            else:
                counter = 1
                prev = cur
    return False


def _simple_design(seq, offset, n, pmin, pmax, is_viroid=False):
    """
    Fallback primer design when primer3-py is unavailable.

    借鉴 varVAMP (Fuchs et al., 2025 Nat. Comm.) k-mer 质量过滤管线:
      1. GC 40-60%
      2. Tm 52-62°C
      3. 3' GC clamp: 最后5bp含1-3个GC
      4. Poly-X ≤5
      5. 二核苷酸重复 ≤4
      6. 发夹 Tm ≤47°C (类病毒放宽至 ≤60°C)
      7. 自二聚体 ΔG ≥ -9 kcal/mol (类病毒放宽至 ≥ -13)
      8. 交叉二聚体 ΔG ≥ -9 kcal/mol
      9. 扩增子 GC 40-60%
    """
    # 类病毒降级阈值
    hairpin_max = 60 if is_viroid else 47
    homodimer_min = -13000 if is_viroid else -9000  # cal/mol
    # ── Phase 1: 收集候选引物单体 ──
    cand = []
    L = len(seq)
    for pos in range(0, L - 23, 3):
        for plen in [19, 20, 21, 22]:
            if pos + plen > L:
                break
            o = seq[pos:pos+plen]

            # 1. GC 40-60%
            gc = (o.count('G') + o.count('C')) / plen
            if gc < 0.40 or gc > 0.60:
                continue

            # 2. Tm 52-62°C (对齐 Primer3 主路径)
            tm = _est_tm(o)
            if tm < 52 or tm > 62:
                continue

            # 3. 3' GC clamp: 最后5bp含1-3个GC (借鉴 varVAMP)
            gc_end = o[-5:].count('G') + o[-5:].count('C')
            if gc_end < 1 or gc_end > 3:
                continue

            # 4. Poly-X ≤5
            if any(nt * 6 in o for nt in 'ATGC'):
                continue

            # 5. 二核苷酸重复 ≤4 (借鉴 varVAMP)
            if _has_dinuc_repeats(o, max_run=4):
                continue

            # 6. 发夹 Tm ≤47°C (借鉴 varVAMP)
            if PRIMER3_OK:
                try:
                    hp = primer3.calc_hairpin(o)
                    if hp.tm > hairpin_max:
                        continue
                except Exception:
                    pass

            # 7. 自二聚体 ΔG ≥ -9 kcal/mol (借鉴 varVAMP)
            if PRIMER3_OK:
                try:
                    hd = primer3.calc_homodimer(o)
                    if hd.dg < homodimer_min:  # primer3 返回 cal/mol
                        continue
                except Exception:
                    pass

            cand.append({"pos": pos, "len": plen, "seq": o, "gc": gc, "tm": tm})

    # ── Phase 2: 组合引物对 ──
    out = []
    seen = set()
    for f in cand:
        for r in cand:
            if f["pos"] >= r["pos"]:
                continue

            # 8. 产物大小检查
            ps = r["pos"] + r["len"] - f["pos"]
            if ps < pmin or ps > pmax:
                continue

            # 9. 引物间 Tm 差 ≤3°C
            if abs(f["tm"] - r["tm"]) > 3:
                continue

            # 10. 交叉二聚体 (借鉴 varVAMP)
            if PRIMER3_OK:
                try:
                    r_seq = str(Seq(r["seq"]).reverse_complement())
                    xd = primer3.calc_heterodimer(f["seq"], r_seq)
                    if xd.dg < -9000:
                        continue
                except Exception:
                    pass

            # 11. 扩增子 GC 40-60% (借鉴 varVAMP)
            amp_seq = seq[f["pos"]:r["pos"] + r["len"]]
            amp_gc = (amp_seq.count('G') + amp_seq.count('C')) / len(amp_seq)
            if amp_gc < 0.40 or amp_gc > 0.60:
                continue

            # 12. 空间去重: 同一 50bp 网格只保留一对
            rk = (f["pos"] // 50, r["pos"] // 50)
            if rk in seen:
                continue
            seen.add(rk)

            r_seq = str(Seq(r["seq"]).reverse_complement())

            # 综合评分: Tm偏差 + GC偏差 + 长度偏差 (借鉴 varVAMP base_penalty)
            tm_score = abs(f["tm"] - 60) + abs(r["tm"] - 60)
            gc_score = abs(f["gc"] - 0.5) * 30 + abs((r["gc"]) - 0.5) * 30  # 注意: r["gc"] 是 Rev 原始序列的 GC, GC互补不变
            size_score = abs(f["len"] - 21) * 0.5 + abs(r["len"] - 21) * 0.5
            penalty = round(tm_score + gc_score + size_score, 2)

            out.append({"Fwd_Seq": f["seq"], "Rev_Seq": r_seq,
                        "Fwd_Tm": round(f["tm"], 1), "Rev_Tm": round(r["tm"], 1),
                        "Product": ps,
                        "GC_Fwd": round(f["gc"] * 100, 1), "GC_Rev": round(r["gc"] * 100, 1),
                        "Penalty": penalty,
                        "Method": "Simple_Thermo"})

            if len(out) >= n * 3:
                break
        if len(out) >= n * 3:
            break

    out.sort(key=lambda x: x["Penalty"])
    return out

# ========== 策略 B: qPCR ==========
def _design_qpcr_core(seq, offset, n, amp_min, amp_max):
    """qPCR 核心调用: Primer3 + 双轨探针 + 二聚体/扩增子检查。
    被 design_qpcr (保守区) 和单参考兜底机制复用。"""
    all_d = []
    if not PRIMER3_OK:
        return all_d
    try:
        r = primer3.design_primers(
            {'SEQUENCE_TEMPLATE': _sanitize_for_primer3(seq)},
            {'PRIMER_NUM_RETURN': max(20, n * 4),
             'PRIMER_PRODUCT_SIZE_RANGE': [[amp_min, amp_max]],
             'PRIMER_MIN_SIZE':18,'PRIMER_OPT_SIZE':21,'PRIMER_MAX_SIZE':23,
             'PRIMER_MIN_TM':54.0,'PRIMER_OPT_TM':60.0,'PRIMER_MAX_TM':61.0,
             'PRIMER_MIN_GC':45.0,'PRIMER_OPT_GC_PERCENT':50.0,'PRIMER_MAX_GC':55.0,
             'PRIMER_PAIR_MAX_DIFF_TM':2.0,
             'PRIMER_PICK_INTERNAL_OLIGO':1,
             'PRIMER_THERMODYNAMIC_OLIGO_ALIGNMENT':1,
             'PRIMER_SECONDARY_STRUCTURE_ALIGNMENT':1,
             'PRIMER_ANNEALING_TEMP':50.0,
             'PRIMER_MAX_END_STABILITY':9.0,
             'PRIMER_MAX_SELF_ANY':3,'PRIMER_MAX_SELF_END':3,
             'PRIMER_PAIR_MAX_COMPL_ANY':3,'PRIMER_PAIR_MAX_COMPL_END':3,
             'PRIMER_MAX_POLY_X':4}
        )
        for i in range(r.get('PRIMER_PAIR_NUM_RETURNED', 0)):
            f = r.get(f'PRIMER_LEFT_{i}_SEQUENCE','')
            rev = r.get(f'PRIMER_RIGHT_{i}_SEQUENCE','')
            if not f or not rev: continue
            left_data = r.get(f'PRIMER_LEFT_{i}', (0,0))
            right_data = r.get(f'PRIMER_RIGHT_{i}', (0,0))
            fe = left_data[0] + left_data[1] if len(left_data) >= 2 else len(f)
            rs2 = (right_data[0] - right_data[1] + 1) if len(right_data) >= 2 else 0
            fwd_tm = r.get(f'PRIMER_LEFT_{i}_TM', 0)
            rev_tm = r.get(f'PRIMER_RIGHT_{i}_TM', 0)

            p3_probe = r.get(f'PRIMER_INTERNAL_{i}_SEQUENCE', '')
            p3_probe_tm = r.get(f'PRIMER_INTERNAL_{i}_TM', 0)
            custom_probe = _find_probe(seq[fe:rs2], primer_tms=(fwd_tm, rev_tm))

            probe = {"seq": "", "tm": ""}
            if p3_probe and len(p3_probe) >= 18:
                probe = {"seq": p3_probe, "tm": str(round(p3_probe_tm, 1))}
            elif custom_probe.get("seq"):
                probe = custom_probe

            if probe.get("seq") and PRIMER3_OK:
                try:
                    p_fwd_dg = primer3.calc_heterodimer(probe["seq"], f).dg / 1000.0
                    p_rev_dg = primer3.calc_heterodimer(probe["seq"], rev).dg / 1000.0
                    if p_fwd_dg < -6.0 or p_rev_dg < -6.0:
                        if custom_probe.get("seq") and custom_probe != probe:
                            probe = custom_probe
                            p_fwd_dg2 = primer3.calc_heterodimer(probe["seq"], f).dg / 1000.0
                            p_rev_dg2 = primer3.calc_heterodimer(probe["seq"], rev).dg / 1000.0
                            if p_fwd_dg2 < -6.0 or p_rev_dg2 < -6.0:
                                probe = {"seq": "", "tm": ""}
                        else:
                            probe = {"seq": "", "tm": ""}
                except Exception:
                    pass

            if probe.get("seq"):
                amp_seq = seq[fe:rs2]
                amp_gc = (amp_seq.count('G') + amp_seq.count('C')) / max(len(amp_seq), 1) * 100
                if amp_gc < 40 or amp_gc > 60:
                    probe = {"seq": "", "tm": ""}
                elif 'NN' in amp_seq:
                    probe = {"seq": "", "tm": ""}

            all_d.append({"Fwd_Seq":f,"Rev_Seq":rev,
                "Fwd_Start":left_data[0]+offset+1,"Rev_Start":right_data[0]+offset+1,
                "Probe_Seq":probe.get("seq",""),"Probe_Tm":probe.get("tm",""),
                "Fwd_Tm":round(r.get(f'PRIMER_LEFT_{i}_TM',0),1),
                "Rev_Tm":round(r.get(f'PRIMER_RIGHT_{i}_TM',0),1),
                "Product":r.get(f'PRIMER_PAIR_{i}_PRODUCT_SIZE',0),
                "GC_Fwd":round(gc_fraction(f)*100,1),"GC_Rev":round(gc_fraction(rev)*100,1),
                "Penalty":round(r.get(f'PRIMER_PAIR_{i}_PENALTY',0),4),
                "Method":"Primer3_qPCR"})
    except Exception: pass
    return all_d


def design_qpcr(sequences, n=3, amp_min=80, amp_max=200,
                do_align=True, aligner="auto", ignore_gap=False,
                pre_aligned=None, is_viroid=False):
    if not sequences: return []
    ref = sequences[0].replace('-', '')
    if len(sequences) > 1:
        cons = find_conserved_regions(sequences, window=60, step=30, max_entropy=0.3,
                                       ignore_gap=ignore_gap, do_align=do_align,
                                       aligner=aligner, pre_aligned=pre_aligned)
    else: cons = [(0, len(ref))]
    if not cons:
        cons = [(0, len(ref))]
    all_d = []
    for rs, re in cons:
        if pre_aligned is not None or (len(sequences) > 1 and do_align):
            a = pre_aligned[0] if pre_aligned else sequences[0]
            rs_u = sum(1 for c in a[:rs] if c != '-')
            re_u = rs_u + sum(1 for c in a[rs:re] if c != '-')
        else: rs_u, re_u = rs, re
        if re_u - rs_u < amp_min + 60: continue
        reg = ref[rs_u:re_u]
        all_d.extend(_design_qpcr_core(reg, rs_u, n, amp_min, amp_max))

    # 单参考基因组兜底: 保守区无产出 → 对 Ref 序列全长相搜
    if not all_d:
        all_d = _design_qpcr_core(ref, 0, n * 2, amp_min, amp_max)

    all_d.sort(key=lambda x: x.get("Penalty", 999))
    return all_d[:n]

def _find_probe(seq, mn=18, mx=28, primer_tms=None):
    """
    Find optimal TaqMan probe in region between primers.

    借鉴 varVAMP qPCR 模式 (Fuchs et al., 2025 Nat. Comm.) 和
    qprimer_designer (Broad Institute) + qPrimer (NAR 2024) 的探针质量过滤管线:
      1. 5'/3' 端不能是 G (荧光淬灭)
      2. GC 40-60%
      3. 同聚物 ≤4bp
      4. Tm 范围 (有引物时: 引物Tm+5~10°C; 无引物时: 60-72°C)
      5. 探针距同链引物 4-15nt (varVAMP QPROBE_DISTANCE)
      6. 自二聚体 ΔG ≥ -6 kcal/mol (qprimer_designer PROBE_DG_MIN)
      7. 发夹 Tm ≤47°C (varVAMP qPCR filter_probe_direction_dependent)
      8. 3' GC clamp: 最后5bp含0-4个GC (varVAMP QPROBE_GC_END)

    多轮降级: 严格约束 → 放宽距离 → 放宽Tm差 → 基础约束
    """
    from Bio.SeqUtils import MeltingTemp as mt
    import re

    if primer_tms:
        min_probe_tm = max(primer_tms) + 5.0
        max_probe_tm = max(primer_tms) + 10.0
    else:
        min_probe_tm = 60.0
        max_probe_tm = 72.0

    def _has_homopolymer(s, max_run=4):
        return bool(re.search(
            r'(A{' + str(max_run+1) + r',}|T{' + str(max_run+1) + r',}'
            r'|G{' + str(max_run+1) + r',}|C{' + str(max_run+1) + r',})',
            s, re.IGNORECASE))

    def _self_dimer_ok(s):
        """自二聚体 ΔG 检查 (借鉴 qprimer_designer)"""
        if not PRIMER3_OK:
            return True
        try:
            dg = primer3.calc_homodimer(s).dg / 1000.0
            return dg >= -6.0
        except Exception:
            return True

    # 多轮扫描: 逐轮放宽约束
    passes = [
        # (label, apply_distance, apply_tm_strict, apply_homopolymer, apply_self_dimer)
        ("strict",      True,  True,  True,  True),
        ("relax_dist",  False, True,  True,  True),
        ("relax_tm",    False, False, True,  True),
        ("basic",       False, False, False, False),
    ]

    def _scan_pass(chk_dist, chk_tm, chk_hp, chk_dimer):
        """扫描一轮, 返回 (seq, tm, gc, length, quality_score) 列表"""
        candidates = []
        for l in range(mx, mn-1, -1):
            for s_pos in range(len(seq)-l+1):
                c = seq[s_pos:s_pos+l]

                # 1. 5' and 3' ends cannot be G
                if c[0] == 'G' or c[-1] == 'G':
                    continue

                # 2. GC content 40-60%
                gc = (c.count('G') + c.count('C')) / l
                if gc < 0.40 or gc > 0.60:
                    continue

                # 3. Homopolymer ≤4bp (借鉴 qprimer_designer)
                if chk_hp and _has_homopolymer(c, 4):
                    continue

                # 4. Tm calculation
                try:
                    tm = mt.Tm_NN(c)
                except Exception:
                    tm = 64.9 + 41 * (gc * l - 16.4) / l

                # 5. Tm range check
                if chk_tm:
                    if not (min_probe_tm <= tm <= max_probe_tm):
                        continue
                else:
                    if not (60 <= tm <= 72):
                        continue

                # 6. Distance to primer: 4-15nt from one primer (借鉴 varVAMP)
                if chk_dist:
                    dist_to_fwd = s_pos
                    dist_to_rev = len(seq) - (s_pos + l)
                    if not (4 <= dist_to_fwd <= 15 or 4 <= dist_to_rev <= 15):
                        continue

                # 7. Self-dimer (借鉴 qprimer_designer)
                if chk_dimer and not _self_dimer_ok(c):
                    continue

                # 8. Hairpin Tm ≤47°C (借鉴 varVAMP qPCR filter_probe_direction_dependent)
                if PRIMER3_OK:
                    try:
                        if primer3.calc_hairpin(c).tm > 47:
                            continue
                    except Exception:
                        pass

                # 9. GC end clamp: 最后5bp含0-4个GC (借鉴 varVAMP QPROBE_GC_END)
                gc_end = c[-5:].count('G') + c[-5:].count('C')
                if gc_end < 0 or gc_end > 4:
                    continue

                # Quality score: 偏向长探针 + GC接近50% + Tm接近目标
                target_tm = (min_probe_tm + max_probe_tm) / 2 if primer_tms else 66
                quality = (l - 18) * 0.3 + (10 - abs(gc*100 - 50)) * 0.1 + (10 - abs(tm - target_tm)) * 0.1
                candidates.append((c, tm, gc, l, s_pos, quality))
        return candidates

    for pass_label, chk_dist, chk_tm, chk_hp, chk_dimer in passes:
        cands = _scan_pass(chk_dist, chk_tm, chk_hp, chk_dimer)
        if cands:
            # 按质量分降序排列, 最优优先
            cands.sort(key=lambda x: x[5], reverse=True)
            best = cands[0]
            return {"seq": best[0], "tm": round(best[1], 1), "gc": round(best[2]*100, 1)}
    return {"seq": "", "tm": ""}

# ========== 策略 C: 简并引物 ==========
IUPAC_TABLE = {frozenset(['A']):'A',frozenset(['C']):'C',frozenset(['G']):'G',frozenset(['T']):'T',
    frozenset(['A','G']):'R',frozenset(['C','T']):'Y',frozenset(['G','C']):'S',frozenset(['A','T']):'W',
    frozenset(['G','T']):'K',frozenset(['A','C']):'M',frozenset(['A','C','G']):'V',frozenset(['A','C','T']):'H',
    frozenset(['A','G','T']):'D',frozenset(['C','G','T']):'B',frozenset(['A','C','G','T']):'N'}

def iupac_consensus(sequences):
    aln_len = len(sequences[0]); consensus = []
    for pos in range(aln_len):
        nts = set()
        for s in sequences:
            n = s[pos].upper()
            if n in ('A','T','G','C'): nts.add(n)
        consensus.append(IUPAC_TABLE.get(frozenset(nts),'N') if nts else 'N')
    return ''.join(consensus)

def _degenerate_properties(seq):
    """
    计算简并引物的 GC/Tm min-max 范围 (借鉴 G老师建议)。

    IUPAC 简并碱基展开:
      R(A|G) Y(C|T) S(G|C) W(A|T) K(G|T) M(A|C)
      B(C|G|T) D(A|G|T) H(A|C|T) V(A|C|G) N(A|C|G|T)
    """
    iupac_gc_bounds = {
        'A': (0,0), 'T': (0,0), 'G': (1,1), 'C': (1,1),
        'R': (0,1), 'Y': (0,1), 'S': (1,1), 'W': (0,0),
        'K': (0,1), 'M': (0,1), 'B': (0,1), 'D': (0,1),
        'H': (0,1), 'V': (0,1), 'N': (0,1)
    }
    min_gc = sum(iupac_gc_bounds.get(c, (0,0))[0] for c in seq)
    max_gc = sum(iupac_gc_bounds.get(c, (0,0))[1] for c in seq)
    L = max(len(seq), 1)
    # Wallace Tm 范围: 2°C×(A+T) + 4°C×(G+C)
    min_tm = 2 * (L - max_gc) + 4 * max_gc
    max_tm = 2 * (L - min_gc) + 4 * min_gc
    return {
        "min_gc": round(min_gc / L * 100, 1),
        "max_gc": round(max_gc / L * 100, 1),
        "min_tm": round(min_tm, 1),
        "max_tm": round(max_tm, 1),
    }


def design_degenerate_primers(sequences, do_align=True, aligner="auto",
                               num_pairs=3, pre_aligned=None):
    if len(sequences) < 2: return []
    if pre_aligned is not None: aligned = pre_aligned
    elif do_align: aligned = run_msa(sequences, aligner)
    else:
        min_len = min(len(s) for s in sequences if s); aligned = [s[:min_len] for s in sequences if s]
    if not aligned: return []
    con_seq = iupac_consensus(aligned); aln_len = len(con_seq)
    def _deg(code):
        if code in 'ATGC': return 1
        if code in 'RYSWKM': return 2
        if code in 'BDHV': return 3
        if code == 'N': return 4
        return 1
    # 高简并度碱基 (会对3'端延伸造成严重摇摆)
    HIGH_DEG_BASES = set('VHBDN')
    best_regions = []
    for start in range(0, aln_len-250, 10):
        end = min(start+200, aln_len)
        fwd_region = con_seq[start:start+80]; rev_region = con_seq[end-80:end]
        fwd_degen = sum(_deg(c) for c in fwd_region); rev_degen = sum(_deg(c) for c in rev_region)
        best_regions.append((fwd_degen+rev_degen, start, end))
    best_regions.sort(key=lambda x: x[0])
    designs = []
    for score, start, end in best_regions[:num_pairs*3]:
        fwd_cand = con_seq[start:start+22]; rev_cand = con_seq[end-22:end]
        if len(fwd_cand) < 18 or len(rev_cand) < 18: continue

        # P1: 3' 端最后 4bp 不能含高简并度碱基 (借鉴 G老师 + varVAMP)
        if any(c in HIGH_DEG_BASES for c in fwd_cand[-4:]):
            continue
        if any(c in HIGH_DEG_BASES for c in rev_cand[:4]):  # Rev 原始方向的 5'=反转后3'
            continue

        rev_cand_rc = str(Seq(rev_cand).reverse_complement())
        fwd_deg = 1
        for c in fwd_cand: fwd_deg *= _deg(c)
        rev_deg = 1
        for c in rev_cand_rc: rev_deg *= _deg(c)
        total_deg = fwd_deg * rev_deg
        if total_deg > 256: continue

        # GC 范围估算 (借鉴 G老师)
        fwd_props = _degenerate_properties(fwd_cand)
        rev_props = _degenerate_properties(rev_cand_rc)

        # 必须满足: max_gc ≥ 30 且 min_gc ≤ 70 (至少理论上可能)
        if fwd_props["max_gc"] < 30 or fwd_props["min_gc"] > 70:
            continue
        if rev_props["max_gc"] < 30 or rev_props["min_gc"] > 70:
            continue

        designs.append({
            "Fwd_Seq": fwd_cand, "Rev_Seq": rev_cand_rc,
            "Probe_Seq": "", "Probe_Tm": "",
            "Fwd_Tm": f"{fwd_props['min_tm']}-{fwd_props['max_tm']}",
            "Rev_Tm": f"{rev_props['min_tm']}-{rev_props['max_tm']}",
            "Product": end - start,
            "GC_Fwd": f"{fwd_props['min_gc']}-{fwd_props['max_gc']}",
            "GC_Rev": f"{rev_props['min_gc']}-{rev_props['max_gc']}",
            "Fwd_Degeneracy": fwd_deg, "Rev_Degeneracy": rev_deg,
            "Total_Degeneracy": total_deg,
            "Penalty": total_deg, "Method": "IUPAC_Degenerate"
        })
    designs.sort(key=lambda x: x.get("Penalty", 999))
    return designs

# ========== 策略 D: 平铺 ==========
def design_tiled_amplicons(sequences, tile_len=1200, overlap=100, num_pairs_per_tile=2,
                            amp_min=200, amp_max=500):
    if not sequences: return []
    ref = max(sequences, key=len); ref_len = len(ref); step = tile_len - overlap
    designs = []
    last_tile_end = 0
    for tile_i, start in enumerate(range(0, ref_len - tile_len, step)):
        end = min(start+tile_len, ref_len); last_tile_end = max(last_tile_end, end)
        tile_seq = ref[start:end]
        left_region = tile_seq[:min(500, len(tile_seq))]; right_region = tile_seq[-min(500, len(tile_seq)):]
        for side, region in [("left",left_region),("right",right_region)]:
            primers = _primer3_design(region, start if side=="left" else end-len(region),
                                       num_pairs_per_tile//2+1, amp_min, amp_max) if PRIMER3_OK else \
                      _simple_design(region, start if side=="left" else end-len(region),
                                      num_pairs_per_tile//2+1, amp_min, amp_max)
            # 每侧只保留最优的 num_pairs_per_tile//2+1 对 (去重叠)
            primers.sort(key=lambda x: x.get("Penalty", 999))
            kept_mids = []; kept = 0; target = max(1, num_pairs_per_tile // 2)
            for p in primers:
                # 检查是否与同一 tile 已保留的引物重叠 (中点间距 ≥ 100bp)
                f_start = p.get("Fwd_Start", 0)
                r_start = p.get("Rev_Start", 0)
                mid = (f_start + r_start) / 2
                if all(abs(mid - d_mid) >= 100 for d_mid in kept_mids):
                    p["Tile_ID"] = tile_i + 1
                    p["Tile_Start"] = start; p["Tile_End"] = end
                    p["Tiled_Side"] = side; p["Method"] = "Tiled_Primer3"
                    designs.append(p)
                    kept_mids.append(mid)
                    kept += 1
                    if kept >= target:
                        break

    # P2: 末端覆盖修复 — 强制追加最后一个 tile 覆盖基因组末尾 (借鉴 G老师建议)
    if last_tile_end < ref_len - 10:
        final_start = max(0, ref_len - tile_len)
        final_tile_seq = ref[final_start:ref_len]
        left_region = final_tile_seq[:min(500, len(final_tile_seq))]
        right_region = final_tile_seq[-min(500, len(final_tile_seq)):]
        final_tile = len(designs) // num_pairs_per_tile + 1
        for side, region in [("left", left_region), ("right", right_region)]:
            primers = _primer3_design(region, final_start if side=="left" else ref_len-len(region),
                                       num_pairs_per_tile//2+1, amp_min, amp_max) if PRIMER3_OK else \
                      _simple_design(region, final_start if side=="left" else ref_len-len(region),
                                      num_pairs_per_tile//2+1, amp_min, amp_max)
            primers.sort(key=lambda x: x.get("Penalty", 999))
            f_kept_mids = []; f_kept = 0; f_target = max(1, num_pairs_per_tile // 2)
            for p in primers:
                f_start = p.get("Fwd_Start", 0)
                r_start = p.get("Rev_Start", 0)
                mid = (f_start + r_start) / 2
                if all(abs(mid - m) >= 100 for m in f_kept_mids):
                    p["Tile_ID"] = final_tile; p["Tile_Start"] = final_start; p["Tile_End"] = ref_len
                    p["Tiled_Side"] = side; p["Method"] = "Tiled_Primer3"; designs.append(p)
                    f_kept_mids.append(mid)
                    f_kept += 1
                    if f_kept >= f_target:
                        break

    # P2: 跨 tile 二聚体检查 — 排除多重PCR中强烈互配的引物对 (借鉴 G老师 + Olivar SADDLE)
    if PRIMER3_OK and len(designs) > 2:
        dimers_found = 0
        for i in range(len(designs)):
            for j in range(i + 1, len(designs)):
                # 仅检查不同 tile 之间的引物对
                if designs[i].get("Tile_ID") == designs[j].get("Tile_ID"):
                    continue
                try:
                    # 检查 Fwd_i vs Fwd_j, Fwd_i vs Rev_j, Rev_i vs Fwd_j, Rev_i vs Rev_j
                    for s1_key, s2_key in [("Fwd_Seq","Fwd_Seq"),("Fwd_Seq","Rev_Seq"),
                                           ("Rev_Seq","Fwd_Seq"),("Rev_Seq","Rev_Seq")]:
                        s1 = designs[i].get(s1_key, "")
                        s2 = designs[j].get(s2_key, "")
                        if len(s1) < 14 or len(s2) < 14:
                            continue
                        xd = primer3.calc_heterodimer(s1, s2)
                        if xd.dg < -10000:  # ΔG < -10 kcal/mol → 严重二聚体
                            dimers_found += 1
                            break  # 该对已标记, 跳至下一对
                except Exception:
                    pass
            if dimers_found > 50:  # 过多二聚体告警 → 停止检查
                break
        if dimers_found > 0:
            # 输出警告, 但不在此阶段移除引物 (留给 step3 验证处理)
            pass

    return designs

# ========== 排除过滤 ==========
def _filter_by_exclusion(primers, exclude_seqs):
    if not primers or not exclude_seqs: return primers
    try: import primer3 as p3
    except ImportError: return primers
    def _has_risk(primer, ex_seq, kmer_len=8):
        plen = len(primer)
        if len(ex_seq) < plen: return False
        kmer = primer[-kmer_len:]; rc_kmer = str(Seq(kmer).reverse_complement())
        pos = 0; ex_len = len(ex_seq)
        while pos < ex_len:
            idx = ex_seq.find(rc_kmer, pos)
            if idx == -1: break
            win_start = max(0, idx+kmer_len-plen)
            for start in range(win_start, min(idx+1, ex_len-plen+1)):
                window = ex_seq[start:start+plen]
                try:
                    if p3.calc_heterodimer(primer, window).dg < -9: return True
                except: continue
            pos = idx + 1
        return False
    filtered = []
    for p in primers:
        fwd = p.get("Fwd_Seq",""); rev = p.get("Rev_Seq","")
        if not fwd or not rev: filtered.append(p); continue
        if any(_has_risk(fwd, es) for es in exclude_seqs if len(es)>=20): continue
        if any(_has_risk(rev, es) for es in exclude_seqs if len(es)>=20): continue
        filtered.append(p)
    return filtered

# ========== varVAMP / Olivar ==========
def _varvamp_available():
    import shutil; return shutil.which("varvamp") is not None
def _olivar_available():
    import shutil; return shutil.which("olivar") is not None

def _primerforge_tiled_available():
    import shutil
    return shutil.which("micromamba") is not None

def _safe_float(val, default=99.0):
    try: return float(val)
    except: return default

def _run_varvamp(seqs, sp, segment, args, pre_aligned=None):
    import tempfile, shutil, subprocess, csv as _csv
    if pre_aligned is not None: aligned = pre_aligned
    else: aligned = run_msa(seqs, aligner=args.aligner)
    safe_name = f"{sp}_{segment}".replace(' ','_').replace('/','_')[:60]
    tmp_dir = Path(tempfile.mkdtemp())
    fa_file = tmp_dir / f"{safe_name}.fasta"
    with open(fa_file, 'w') as f:
        for i, s in enumerate(aligned): f.write(f">seq_{i}\n{s.replace('-','')}\n")
    out_dir = Path(args.output) / "varvamp_tmp" / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = Path(args.output) / "varvamp_logs"; log_dir.mkdir(parents=True, exist_ok=True)
    designs = []
    try:
        opt_len = min(args.pmax, max((len(s) for s in seqs), default=args.pmax))
        cmd = ["varvamp","single","-ol",str(opt_len),"-n",str(args.num_degen*2),
               "-th",str(args.threads), str(fa_file), str(out_dir)]
        with open(log_dir / f"{safe_name}_varvamp.log", 'w') as lf:
            result = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True, timeout=1800)
        if result.returncode != 0:
            # failure logged, see varvamp_logs/
            return []
        for tsv in out_dir.glob("*.tsv"):
            try:
                with open(tsv, 'r') as f:
                    reader = _csv.DictReader(f, delimiter='\t')
                    cols = reader.fieldnames or []
                    amp_col = next((c for c in ['amlicon_name','amplicon_name'] if c in cols), None)
                    name_col = next((c for c in ['primer_name','primer_name_all_primers'] if c in cols), None)
                    if not amp_col or not name_col: continue
                    groups = {}
                    for row in reader:
                        amp = str(row.get(amp_col,'')); pname = str(row.get(name_col,'')).upper()
                        if amp not in groups: groups[amp] = {}
                        if 'LEFT' in pname: groups[amp]['fwd'] = row
                        elif 'RIGHT' in pname: groups[amp]['rev'] = row
                    for amp, pair in groups.items():
                        fr = pair.get('fwd',{}); rr = pair.get('rev',{})
                        fwd = str(fr.get('seq','')).upper(); rev = str(rr.get('seq','')).upper()
                        if fwd and rev and len(fwd) >= 15:
                            designs.append({"Fwd_Seq":fwd,"Rev_Seq":rev,
                                "Fwd_Start":str(fr.get('start','')),"Rev_Start":str(rr.get('start','')),
                                "Probe_Seq":str(fr.get('probe','')).upper(),
                                "Fwd_Tm":str(fr.get('temp_best','')),"Rev_Tm":str(rr.get('temp_best','')),
                                "Product":str(fr.get('amplicon_length','')),
                                "Fwd_Degeneracy":fr.get('degeneracy_fwd',''),
                                "Rev_Degeneracy":rr.get('degeneracy_rev',''),
                                "Penalty":_safe_float(fr.get('penalty',''),99.0),"Method":"varVAMP"})
            except Exception: continue
        if designs:
            pass  # counted in summary
    except Exception as e:
        pass  # failure caught, see varvamp_logs/
    try: shutil.rmtree(tmp_dir)
    except: pass
    return designs

def _run_varvamp_tiled(seqs, sp, segment, args, pre_aligned=None):
    import tempfile, shutil, subprocess, csv as _csv
    if pre_aligned is not None: aligned = pre_aligned
    else: aligned = run_msa(seqs, aligner=args.aligner)
    safe_name = f"{sp}_{segment}_tiled".replace(' ','_').replace('/','_')[:60]
    tmp_dir = Path(tempfile.mkdtemp())
    fa_file = tmp_dir / f"{safe_name}.fasta"
    with open(fa_file, 'w') as f:
        for i, s in enumerate(aligned): f.write(f">seq_{i}\n{s.replace('-','')}\n")
    out_dir = Path(args.output) / "varvamp_tmp" / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = Path(args.output) / "varvamp_logs"; log_dir.mkdir(parents=True, exist_ok=True)
    designs = []
    try:
        opt_len = min(args.tile_len, max((len(s) for s in seqs), default=args.tile_len))
        cmd = ["varvamp","tiled","-ol",str(opt_len),"-o",str(args.tile_overlap),
               "-a","2","-th",str(args.threads), str(fa_file), str(out_dir)]
        with open(log_dir / f"{safe_name}_varvamp_tiled.log", 'w') as lf:
            result = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True, timeout=1800)
        if result.returncode != 0:
            # failure logged
            return []
        for tsv in out_dir.glob("*.tsv"):
            try:
                with open(tsv, 'r') as f:
                    reader = _csv.DictReader(f, delimiter='\t')
                    cols = reader.fieldnames or []
                    amp_col = next((c for c in ['amlicon_name','amplicon_name'] if c in cols), None)
                    name_col = next((c for c in ['primer_name','primer_name_all_primers'] if c in cols), None)
                    if not amp_col or not name_col: continue
                    groups = {}
                    for row in reader:
                        amp = str(row.get(amp_col,'')); pname = str(row.get(name_col,'')).upper()
                        if amp not in groups: groups[amp] = {}
                        if 'LEFT' in pname: groups[amp]['fwd'] = row
                        elif 'RIGHT' in pname: groups[amp]['rev'] = row
                    for amp, pair in groups.items():
                        fr = pair.get('fwd',{}); rr = pair.get('rev',{})
                        fwd = str(fr.get('seq','')).upper(); rev = str(rr.get('seq','')).upper()
                        if fwd and rev and len(fwd) >= 15:
                            designs.append({"Fwd_Seq":fwd,"Rev_Seq":rev,
                                "Fwd_Start":str(fr.get('start','')),"Rev_Start":str(rr.get('start','')),
                                "Probe_Seq":"","Probe_Tm":"",
                                "Fwd_Tm":str(fr.get('temp_best','')),"Rev_Tm":str(rr.get('temp_best','')),
                                "Product":str(fr.get('amplicon_length','')),
                                "GC_Fwd":"","GC_Rev":"",
                                "Penalty":_safe_float(fr.get('penalty',''),99.0),"Method":"varVAMP_tiled"})
            except Exception: continue
        if designs: pass
    except Exception as e:
        print(f"      varVAMP tiled 失败: {e}", flush=True)
    try: shutil.rmtree(tmp_dir)
    except: pass
    return designs

def _run_primerforge_tiled(seqs, sp, segment, args, pre_aligned=None):
    """PrimerForge DP 平铺路由 (CLI调用, 独立conda环境)"""
    import tempfile, shutil, subprocess, re as _re
    ref = seqs[0].replace('-', '')
    if len(ref) < args.tile_min_len:
        return []
    safe_name = f"{sp}_{segment}_pf".replace(' ','_').replace('/','_')[:60]
    tmp_dir = Path(tempfile.mkdtemp())
    fa_file = tmp_dir / f"{safe_name}.fasta"
    with open(fa_file, 'w') as f:
        f.write(f">ref\n{ref}\n")
    designs = []
    try:
        cmd = ["micromamba", "run", "-n", "primerforge_env", "primerforge", "design",
               "--target", str(fa_file), "--tiled", "--num-return", "50",
               "--model-dir", os.path.expanduser("~/primerforge_models")]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            return []
        # 解析 CLI 文本输出:
        # [Tile Set N] Success Probability: X% | Range: start-endbp
        #   Forward: SEQ (Tm=Y°C, GC=Z%)
        #   Reverse: SEQ (Tm=Y°C, GC=Z%)
        tile_id = 0
        current = {}
        for line in result.stdout.split('\n'):
            m = _re.match(r'\[Tile Set (\d+)\].*Range: (\d+)-(\d+)bp', line)
            if m:
                if current.get('fwd'):
                    tile_id += 1
                    designs.append(current)
                current = {'tile_id': m.group(1), 'abs_start': m.group(2), 'abs_end': m.group(3)}
                # 提取成功率
                sm = _re.search(r'Success Probability:\s*([\d.]+)%', line)
                if sm:
                    current['success'] = sm.group(1)
                continue
            fm = _re.match(r'\s+Forward:\s+(\S+)', line)
            if fm:
                current['fwd'] = fm.group(1)
                tmm = _re.search(r'Tm=([\d.]+)', line)
                if tmm: current['fwd_tm'] = tmm.group(1)
                continue
            rm = _re.match(r'\s+Reverse:\s+(\S+)', line)
            if rm:
                current['rev'] = rm.group(1)
                tmm = _re.search(r'Tm=([\d.]+)', line)
                if tmm: current['rev_tm'] = tmm.group(1)
                continue
        # 最后一个
        if current.get('fwd') and current.get('rev'):
            tile_id += 1
            designs.append(current)

        result_designs = []
        for i, d in enumerate(designs):
            prod = int(d.get('abs_end', 0)) - int(d.get('abs_start', 0))
            success = float(d.get('success', 50))
            result_designs.append({
                "Fwd_Seq": d.get('fwd', '').upper(), "Rev_Seq": d.get('rev', '').upper(),
                "Fwd_Start": d.get('abs_start', ''), "Rev_Start": d.get('abs_end', ''),
                "Probe_Seq": "", "Probe_Tm": "",
                "Fwd_Tm": d.get('fwd_tm', ''), "Rev_Tm": d.get('rev_tm', ''),
                "Product": str(prod) if prod > 0 else "",
                "GC_Fwd": "", "GC_Rev": "",
                "Tile_ID": str(i + 1),
                "Penalty": round(100 - success, 1),
                "Method": "PrimerForge"
            })
        return result_designs
    except Exception:
        return []
    finally:
        try: shutil.rmtree(tmp_dir)
        except: pass


def _run_olivar(seqs, sp, segment, args, pre_aligned=None):
    import tempfile, shutil, subprocess, time as _time, csv as _csv, re
    safe_name = f"{sp}_{segment}".replace(' ','_').replace('/','_')[:60]
    tmp_dir = Path(tempfile.mkdtemp())
    log_dir = Path(args.output) / "olivar_logs"; log_dir.mkdir(parents=True, exist_ok=True)
    # 清除简并碱基 (Olivar 不支持 IUPAC 编码)
    def _clean_seq(s):
        return ''.join(c if c in 'ATGC-' else 'N' for c in s.upper())

    if pre_aligned is not None:
        fa_file = tmp_dir / f"{safe_name}_msa.fasta"
        with open(fa_file, 'w') as f:
            for i, s in enumerate(pre_aligned): f.write(f">seq_{i}\n{_clean_seq(s)}\n")
        build_flag, input_path = "--msa", fa_file
    elif len(seqs) > 1:
        fa_file = tmp_dir / f"{safe_name}.fasta"
        with open(fa_file, 'w') as f:
            for i, s in enumerate(seqs): f.write(f">seq_{i}\n{_clean_seq(s)}\n")
        build_flag, input_path = "--msa", fa_file
    else:
        ref_file = tmp_dir / f"{safe_name}_ref.fasta"
        with open(ref_file, 'w') as f: f.write(f">ref\n{_clean_seq(seqs[0])}\n")
        build_flag, input_path = "--fasta", ref_file
    out_dir = Path(args.output) / "olivar_tmp" / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)
    designs = []
    try:
        # Olivar running, output in log
        build_dir = out_dir / "build"
        build_cmd = ["olivar","build",build_flag,str(input_path),
                     "--title",f"{safe_name}_{_time.time():.0f}",
                     "--output",str(build_dir),"--threads",str(args.threads)]
        with open(log_dir / f"{safe_name}_build.log", 'w') as lf:
            br = subprocess.run(build_cmd, stdout=lf, stderr=subprocess.STDOUT, text=True, timeout=600)
        if br.returncode != 0:
            raise RuntimeError(f"build failed, see {log_dir}/{safe_name}_build.log")
        olvr_files = list(build_dir.glob(f"*{safe_name}*.olvr")) or list(build_dir.glob("*.olvr"))
        if not olvr_files: raise RuntimeError("no .olvr generated")
        olvr_path = olvr_files[0]
        # tiling done, output in log
        tile_dir = out_dir / "tiling"
        tile_cmd = ["olivar","tiling",str(olvr_path),"--output",str(tile_dir),
                    "--max-amp-len",str(args.tile_len),"--threads",str(args.threads)]
        with open(log_dir / f"{safe_name}_tiling.log", 'w') as lf:
            tr = subprocess.run(tile_cmd, stdout=lf, stderr=subprocess.STDOUT, text=True, timeout=1800)
        if tr.returncode != 0:
            raise RuntimeError(f"tiling failed, see {log_dir}/{safe_name}_tiling.log")
        csv_patterns = ["*design*.csv","*primer*.csv","*.csv"]
        for pattern in csv_patterns:
            for csv_file in tile_dir.glob(pattern):
                try:
                    with open(csv_file, 'r') as f:
                        reader = _csv.DictReader(f)
                        # 按 amplicon_id 分组，每 tile 只保留最佳一对
                        tile_best = {}  # amplicon_id -> best row
                        for row in reader:
                            fwd = str(row.get('fP',row.get('fwd',row.get('forward','')))).upper()
                            rev = str(row.get('rP',row.get('rev',row.get('reverse','')))).upper()
                            if not fwd or not rev: continue
                            amp_id = str(row.get('amplicon_id',row.get('pool','')))
                            olv_s = row.get('start','') or row.get('insert_start','')
                            olv_e = row.get('end','') or row.get('insert_end','')
                            try: prod = int(olv_e) - int(olv_s) if olv_s and olv_e else 0
                            except: prod = 0
                            # 优先选产物长度最接近 tile_len 的
                            if amp_id not in tile_best:
                                tile_best[amp_id] = (row, prod)
                            else:
                                _, prev_prod = tile_best[amp_id]
                                if abs(prod - args.tile_len) < abs(prev_prod - args.tile_len):
                                    tile_best[amp_id] = (row, prod)
                        for amp_id, (row, _) in tile_best.items():
                            fwd = str(row.get('fP',row.get('fwd',row.get('forward','')))).upper()
                            rev = str(row.get('rP',row.get('rev',row.get('reverse','')))).upper()
                            olv_start = row.get('start','') or row.get('insert_start','')
                            olv_end = row.get('end','') or row.get('insert_end','')
                            try: prod = int(olv_end) - int(olv_start) if olv_start and olv_end else 0
                            except: prod = 0
                            designs.append({"Fwd_Seq":fwd,"Rev_Seq":rev,
                                "Probe_Seq":"","Probe_Tm":"",
                                "Fwd_Start": str(olv_start) if olv_start else "",
                                "Rev_Start": str(olv_end) if olv_end else "",
                                "Fwd_Tm":"","Rev_Tm":"",
                                "Product":str(prod),
                                "GC_Fwd":"","GC_Rev":"",
                                "Tile_ID":re.findall(r'\d+', str(row.get('amplicon_id',row.get('pool',''))))[-1] if re.findall(r'\d+', str(row.get('amplicon_id',row.get('pool','')))) else "0",
                                "Penalty":99.0,"Method":"Olivar"})
                except Exception: continue
        if designs: pass
    except Exception as e:
        pass
    try: shutil.rmtree(tmp_dir)
    except: pass
    return designs

# ========== 主处理 ==========
def process_species(sp, records, args):
    if not records: return []
    # RefSeq 序列优先做参照 → 移到第一位
    for i, r in enumerate(records):
        if str(r.get("seq_type","")).upper() == "REFSEQ":
            if i != 0: records[0], records[i] = records[i], records[0]
            break
    family = records[0].get("family",""); genus = records[0].get("genus","")
    do_align = not args.no_align; aligner = args.aligner
    has_segments = any(r.get("segment","") for r in records if r.get("seq"))
    if has_segments:
        segments = defaultdict(list)
        for r in records:
            if r.get("seq"): segments[r.get("segment","unknown") or "unknown"].append(r)
        out = []
        for seg_name, seg_records in segments.items():
            seqs = [r["seq"] for r in seg_records if r.get("seq")]
            if not seqs: continue
            out += _design_for_species(sp, seqs, family, genus, seg_name, args, do_align, aligner,
                                        exclude_seqs=getattr(args,'exclude_seqs',[]))
        return out
    else:
        seqs = [r["seq"] for r in records if r.get("seq")]
        if not seqs: return []
        return _design_for_species(sp, seqs, family, genus, "", args, do_align, aligner,
                                    exclude_seqs=getattr(args,'exclude_seqs',[]))

def _design_for_species(sp, seqs, family, genus, segment, args, do_align, aligner, exclude_seqs=None):
    n_seqs = len(seqs); max_len = max((len(s) for s in seqs), default=0)
    exclude_seqs = exclude_seqs or []

    # 类病毒/微小序列绿色通道: 环状拼接 + 降级质检
    is_viroid = ('viroid' in sp.lower() or 'viroid' in family.lower() or
                 'viroid' in genus.lower() or max_len < 500)
    if is_viroid:
        print(f"  [!] 类病毒/微小序列 ({sp}), 环状拼接 + 降级质检", flush=True)
        seqs = [s + s for s in seqs]  # 模拟环状多聚体
        max_len = max((len(s) for s in seqs), default=0)

    cached_msa = None
    if do_align and n_seqs > 1:
        cached_msa = run_msa(seqs, aligner=aligner)
        # 自动过滤疑似不属于同一物种的序列 (pairwise identity < 60%)
        if len(cached_msa) > 2:
            cached_msa, seqs_filtered, removed = _filter_outliers(cached_msa, seqs)
            if removed:
                print(f"  [!] 过滤 {len(removed)} 条离群序列 (identity<60%), 剩余 {len(seqs_filtered)} 条", flush=True)
                seqs = seqs_filtered
                n_seqs = len(seqs)
                max_len = max((len(s) for s in seqs), default=0)
        do_align = False
    # 先从 args 获取基准值
    if args.primers_per_kb > 0 and max_len > 0:
        scaled = max(1, round(max_len/1000*args.primers_per_kb))
        num_pcr = scaled; num_qpcr = max(1, scaled//2); num_degen = max(1, scaled//2)
    else:
        num_pcr = args.num_pcr; num_qpcr = args.num_qpcr; num_degen = args.num_degen
    # 湿实验红线 + 动态分流: 类病毒150bp, 正常病毒继承args.pmin(250)
    if is_viroid:
        pmin = 150  # 跑胶分辨底线, 与二聚体(40-60bp)清晰分离
        pmax = max(250, max_len)
        qpcr_amp_min, qpcr_amp_max = 80, min(200, max_len)
        num_pcr = max(1, num_pcr//2); num_qpcr = max(1, num_qpcr//2)
    elif max_len < 2000:
        # 中型病毒: 防止在短基因组上要求超长产物
        pmin = min(args.pmin, max_len - 100) if max_len > args.pmin + 100 else args.pmin
        pmax = max(500, min(args.pmax, max_len))
        qpcr_amp_min, qpcr_amp_max = 80, min(200, max_len)
        num_pcr = max(2, num_pcr); num_qpcr = max(1, num_qpcr)
    else:
        pmin = args.pmin; pmax = args.pmax; qpcr_amp_min, qpcr_amp_max = 80, 200

    out = []
    print(f"  [{sp}{'/'+segment if segment else ''}] {n_seqs} seqs, {max_len}bp", flush=True)

    counts = {"P":0,"Q":0,"D":0,"T":0}
    if not args.skip_pcr:
        b0 = len(out)
        for p in design_primers(seqs, num_pcr, pmin, pmax, do_align=do_align, aligner=aligner,
                                ignore_gap=True, pre_aligned=cached_msa, is_viroid=is_viroid):
            p.update({"Species":sp,"Type":"PCR","Family":family,"Genus":genus,"Segment":segment,"Num_Seqs":n_seqs})
            out.append(p)
        counts["P"] = len(out) - b0
    if not args.skip_qpcr:
        b0 = len(out)
        for p in design_qpcr(seqs, num_qpcr, amp_min=qpcr_amp_min, amp_max=qpcr_amp_max,
                              do_align=do_align, aligner=aligner, ignore_gap=True,
                              pre_aligned=cached_msa, is_viroid=is_viroid):
            p.update({"Species":sp,"Type":"qPCR","Family":family,"Genus":genus,"Segment":segment,"Num_Seqs":n_seqs})
            out.append(p)
        counts["Q"] = len(out) - b0
    if not args.skip_degenerate and n_seqs >= args.degen_threshold:
        b0 = len(out)
        if not args.no_varvamp and _varvamp_available():
            for p in _run_varvamp(seqs, sp, segment, args, pre_aligned=cached_msa):
                p.update({"Species":sp,"Type":"DEGENERATE","Family":family,"Genus":genus,"Segment":segment,"Num_Seqs":n_seqs})
                out.append(p)
        else:
            for p in design_degenerate_primers(seqs, do_align=do_align, aligner=aligner, num_pairs=args.num_degen, pre_aligned=cached_msa):
                p.update({"Species":sp,"Type":"DEGENERATE","Family":family,"Genus":genus,"Segment":segment,"Num_Seqs":n_seqs})
                out.append(p)
        counts["D"] = len(out) - b0
    if not args.skip_tiled and max_len > args.tile_min_len:
        b0 = len(out); tiled_count = 0
        # Olivar (SADDLE) → varVAMP tiled (Dijkstra)
        if not args.no_olivar and _olivar_available():
            for p in _run_olivar(seqs, sp, segment, args, pre_aligned=cached_msa):
                p.update({"Species":sp,"Type":"TILED","Family":family,"Genus":genus,"Segment":segment,"Num_Seqs":n_seqs})
                out.append(p); tiled_count += 1
        if not args.no_varvamp and _varvamp_available():
            for p in _run_varvamp_tiled(seqs, sp, segment, args, pre_aligned=cached_msa):
                p.update({"Species":sp,"Type":"TILED","Family":family,"Genus":genus,"Segment":segment,"Num_Seqs":n_seqs})
                out.append(p); tiled_count += 1
        counts["T"] = len(out) - b0
    if exclude_seqs and out:
        before = len(out); out = _filter_by_exclusion(out, exclude_seqs)
    # 放宽二轮: PCR=0 或 qPCR=0 时用类病毒级降级标准重新搜索 (step3 仍会评分过滤)
    if counts["P"] == 0 and not args.skip_pcr:
        for p in design_primers(seqs, num_pcr, pmin, pmax, do_align=False, aligner="no",
                                ignore_gap=True, pre_aligned=None, is_viroid=True):
            if not any(existing.get("Fwd_Seq") == p.get("Fwd_Seq") and existing.get("Rev_Seq") == p.get("Rev_Seq") for existing in out):
                p.update({"Species":sp,"Type":"PCR","Family":family,"Genus":genus,"Segment":segment,"Num_Seqs":n_seqs})
                out.append(p)
        counts["P"] = sum(1 for p in out if p.get("Type") == "PCR")
    if counts["Q"] == 0 and not args.skip_qpcr:
        for p in design_qpcr(seqs, num_qpcr, amp_min=qpcr_amp_min, amp_max=qpcr_amp_max,
                              do_align=False, aligner="no", ignore_gap=True,
                              pre_aligned=None, is_viroid=True):
            if not any(existing.get("Fwd_Seq") == p.get("Fwd_Seq") and existing.get("Rev_Seq") == p.get("Rev_Seq") for existing in out):
                p.update({"Species":sp,"Type":"qPCR","Family":family,"Genus":genus,"Segment":segment,"Num_Seqs":n_seqs})
                out.append(p)
        counts["Q"] = sum(1 for p in out if p.get("Type") == "qPCR")
    # 单行输出 (原子性, 不交织)
    parts = [f"PCR:{counts['P']}",f"qPCR:{counts['Q']}",f"Deg:{counts['D']}",f"Tiled:{counts['T']}"]
    label = f"{sp}{'/'+segment if segment else ''}"
    print(f"  [{label}] {n_seqs}s {max_len}bp -> {' '.join(parts)} ({len(out)} total)", flush=True)
    return out

# ========== main ==========
def main():
    p = argparse.ArgumentParser(description="植物病毒引物批量设计 v3")
    p.add_argument('--species-dir', required=True)
    p.add_argument('--species', default='')
    p.add_argument('-o','--output', default='designed_primers')
    p.add_argument('-t','--threads', type=int, default=4, help='工具线程数')
    p.add_argument('-j','--jobs', type=int, default=4, help='并行进程数')
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--num-pcr', type=int, default=5); p.add_argument('--num-qpcr', type=int, default=3)
    p.add_argument('--num-degen', type=int, default=3)
    p.add_argument('--pmin', type=int, default=250); p.add_argument('--pmax', type=int, default=1000)
    p.add_argument('--degen-threshold', type=int, default=2)
    p.add_argument('--tile-len', type=int, default=1200); p.add_argument('--tile-overlap', type=int, default=100)
    p.add_argument('--tile-min-len', type=int, default=2000)
    p.add_argument('--no-align', action='store_true')
    p.add_argument('--aligner', default='auto', choices=['auto','mafft','muscle','clustalo','no'])
    p.add_argument('--skip-pcr', action='store_true'); p.add_argument('--skip-qpcr', action='store_true')
    p.add_argument('--skip-degenerate', action='store_true'); p.add_argument('--skip-tiled', action='store_true')
    p.add_argument('--ignore-gap', action='store_true')
    p.add_argument('--exclude-fasta', default='')
    p.add_argument('--primers-per-kb', type=float, default=0)
    p.add_argument('--no-varvamp', action='store_true'); p.add_argument('--no-olivar', action='store_true')
    args = p.parse_args()
    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)

    exclude_seqs = []
    if args.exclude_fasta:
        ep = Path(args.exclude_fasta)
        if ep.exists():
            for rec in SeqIO.parse(ep, 'fasta'): exclude_seqs.append(str(rec.seq).upper())
    args.exclude_seqs = exclude_seqs

    species_dir = Path(args.species_dir)
    idx_file = species_dir.parent / "species_index.tsv"
    sp_meta = {}
    if idx_file.exists():
        try:
            for row in pl.read_csv(idx_file, separator='\t', ignore_errors=True).iter_rows(named=True):
                sp_meta[str(row.get('Species','')).strip()] = {
                    'family': str(row.get('Family','')).strip(),
                    'genus': str(row.get('Genus','')).strip()}
        except: pass

    species_map = {}
    # 从 species_index.tsv 建立 FASTA 文件 → (物种, 属, 科, 节段) 映射
    fa_to_meta = {}
    idx_file = species_dir.parent / "species_index.tsv"
    if idx_file.exists():
        try:
            for row in pl.read_csv(idx_file, separator='\t', ignore_errors=True).iter_rows(named=True):
                fa_path = str(row.get('FASTA', '')).strip()
                if fa_path:
                    fa_to_meta[Path(fa_path).name] = {
                        'species': str(row.get('Species', '')).strip(),
                        'genus': str(row.get('Genus', '')).strip(),
                        'family': str(row.get('Family', '')).strip(),
                    }
        except Exception: pass

    for fa_file in sorted(species_dir.glob('*.fasta')):
        meta = fa_to_meta.get(fa_file.name, {})
        sp_name = meta.get('species', fa_file.stem.replace('_', ' ').strip())
        family = meta.get('family', '')
        genus = meta.get('genus', '')
        records = []
        for rec in SeqIO.parse(fa_file, 'fasta'):
            desc = rec.description
            seg = desc.split("|segment=")[1].split('|')[0].strip() if "|segment=" in desc else ""
            records.append({'acc':rec.id, 'seq':str(rec.seq).upper(),
                'family':family, 'genus':genus, 'segment':seg})
        if records: species_map[sp_name] = records

    items = list(species_map.items())
    if args.species: items = [(n,r) for n,r in items if args.species.lower() in n.lower()]
    items.sort(key=lambda x: len(x[1]), reverse=True)
    if args.limit: items = items[:args.limit]

    # 断点续传
    out_tsv = out_dir / "all_primers.tsv"
    completed = set(); existing_results = []
    if out_tsv.exists():
        try:
            prev = pl.read_csv(out_tsv, separator='\t', ignore_errors=True)
            if 'Species' in prev.columns:
                completed = set(prev['Species'].unique().to_list())
                existing_results = prev.to_dicts()
                print(f"> 续传: {len(completed)} 物种已完成, 跳过")
        except: pass
    if completed:
        items = [(n,r) for n,r in items if n not in completed]
        if not items: print("> 全部完成"); return

    print(f"\n▶ 开始: {len(items)} 个物种 (已完成 {len(completed)}), {sum(len(r) for _, r in items)} 条序列")
    print(f"  MSA: {'截断' if args.no_align else f'{args.aligner}'}")
    print(f"  PCR: {'✓' if not args.skip_pcr else '✗'} ({args.num_pcr} 对/物种)")
    print(f"  qPCR: {'✓' if not args.skip_qpcr else '✗'} ({args.num_qpcr} 对/物种)")
    print(f"  简并: {'✓' if not args.skip_degenerate else '✗'} ({args.num_degen} 对/物种, >={args.degen_threshold}条)")
    print(f"  平铺: {'✓' if not args.skip_tiled else '✗'} ({args.tile_len}bp, >={args.tile_min_len}bp)")
    print(f"  并行: {args.jobs} 进程 x {args.threads} 线程\n")

    all_results = []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        fut_to_sp = {ex.submit(process_species, sp, rec, args): sp for sp, rec in items}
        pbar = tqdm(total=len(items), desc="Designing primers", unit="sp", disable=not TQDM_OK) if TQDM_OK else None
        for fut in as_completed(fut_to_sp):
            sp = fut_to_sp[fut]
            try: all_results.extend(fut.result())
            except Exception as e:
                if TQDM_OK: tqdm.write(f"  X {sp}: {e}")
                else: print(f"  X {sp}: {e}")
            if pbar: pbar.update(1); pbar.set_postfix(primers=len(all_results))
        if pbar: pbar.close()

    all_results = existing_results + all_results
    if all_results:
        cols = ["Species","Type","Segment","Family","Genus","Num_Seqs","Pair_ID",
                "Fwd_Seq","Rev_Seq","Fwd_Start","Rev_Start",
                "Probe_Seq","Probe_Tm","Fwd_Tm","Rev_Tm","Product",
                "GC_Fwd","GC_Rev","Fwd_Degeneracy","Rev_Degeneracy","Total_Degeneracy",
                "Tile_ID","Tile_Start","Tile_End","Penalty","Method"]
        norm = []
        for idx, r in enumerate(all_results):
            row = {}
            for c in cols:
                v = r.get(c, "")
                if c == "Penalty": v = str(_safe_float(v, 99.0))
                elif c in ("GC_Fwd","GC_Rev"): v = str(_safe_float(v, 0.0))
                elif c in ("Fwd_Degeneracy","Rev_Degeneracy","Total_Degeneracy"): v = str(v) if v != "" else ""
                elif c == "Pair_ID": v = str(v) if v else f"P{idx+1:05d}"
                row[c] = str(v) if v != "" else ""
            norm.append(row)
        df = pl.DataFrame(norm)
        df.write_csv(out_tsv, separator='\t')
        print(f"\n{'='*70}"); print("Done!"); print(f"  Total: {len(df)} primers")
        for r in df.group_by("Type").agg(pl.len().alias("Count")).iter_rows(named=True):
            print(f"    {r['Type']}: {r['Count']} pairs")
        print(f"  -> {out_tsv}"); print(f"{'='*70}")
    else:
        print("\n  No primers generated")

if __name__ == "__main__":
    main()
