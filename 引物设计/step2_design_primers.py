#!/usr/bin/env python3
"""
Step 2: 核心引物设计引擎
========================================================================
输入: step1_parse_db.py 拆分好的 per-species FASTA 目录

用法:
  python step2_design_primers.py --species-dir split_species/species -t 8

四种设计策略:
  A - PCR 保守引物     (MSA -> Shannon熵 -> Primer3)
  B - qPCR + TaqMan 探针 (短扩增子 + 内部探针扫描)
  C - 简并引物         (MSA -> IUPAC共识 -> 低简并区)
  D - 全基因组平铺扩断   (滑动窗口 tiles -> 每 tile 两端引物)
"""

import argparse
import os
import sys
import math
import subprocess
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

import polars as pl
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqUtils import GC

try:
    import primer3
    PRIMER3_OK = True
except ImportError:
    PRIMER3_OK = False

# ======================================================================
# 3a. MSA 多序列比对
# ======================================================================

def run_msa(sequences: list[str], aligner: str = "auto") -> list[str]:
    """
    多序列比对 (MAFFT / MUSCLE / ClustalOmega)。

    优先使用 MAFFT (准确度最高), 备选 MUSCLE, 再备选 ClustalOmega。
    当无可用的比对工具时, 回退到截断对齐 (假设序列左端对齐)。

    参数:
      sequences: 未比对的原始序列
      aligner:   "mafft" / "muscle" / "clustalo" / "auto" / "no"

    返回:
      比对后的序列列表 (含 gap '-')
    """
    import shutil
    import tempfile

    # 只有 1 条序列或已禁用比对
    if len(sequences) < 2 or aligner == "no":
        return [s for s in sequences if s]

    # 检测可用的比对工具
    tools = []
    if aligner == "auto":
        for cmd in ["mafft", "muscle", "clustalo"]:
            if shutil.which(cmd):
                tools.append(cmd)
    elif shutil.which(aligner):
        tools.append(aligner)

    if not tools:
        print("      ⚠ 未找到 MSA 工具 (mafft/muscle/clustalo), 使用截断对齐")
        min_len = min(len(s) for s in sequences if s)
        return [s[:min_len] for s in sequences if s]

    try:
        # 写临时 FASTA
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fa', delete=False,
                                         encoding='utf-8') as f:
            tmpl_fa = f.name
            for i, s in enumerate(sequences):
                f.write(f'>seq_{i}\n{s}\n')

        out_fa = tmpl_fa + ".aln"
        tool = tools[0]
        args = []
        if tool == "mafft":
            args = ["mafft", "--auto", "--adjustdirection", tmpl_fa]
        elif tool == "muscle":
            args = ["muscle", "-align", tmpl_fa, "-output", out_fa]
        elif tool == "clustalo":
            args = ["clustalo", "-i", tmpl_fa, "-o", out_fa, "--force"]

        # 运行
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=1200
        )
        subprocess.run  # noqa (keep reference to subprocess)
    except Exception as e:
        print(f"      ⚠ MSA 失败: {e}")
        # 清理临时文件
        for f in [tmpl_fa, out_fa]:
            try: os.unlink(f)
            except: pass
        # 回退到截断
        min_len = min(len(s) for s in sequences if s)
        return [s[:min_len] for s in sequences if s]

    # 解析比对结果
    aligned = []
    try:
        for record in SeqIO.parse(out_fa, "fasta"):
            aligned.append(str(record.seq))
    except Exception:
        # MAFFT 输出到 stdout
        aligned = []
        for line in result.stdout.split('\n'):
            if line.startswith('>'):
                continue
            if line.strip():
                aligned.append(line.strip().upper())

    # 清理
    for f in [tmpl_fa, out_fa]:
        try: os.unlink(f)
        except: pass

    if aligned:
        print(f"      MSA ({tool}): {len(aligned)} 条, "
              f"长度 {len(aligned[0])}bp")
        return aligned

    # 后备: 截断对齐
    min_len = min(len(s) for s in sequences if s)
    return [s[:min_len] for s in sequences if s]


# ======================================================================
# 3b. Shannon 熵保守区分析 (MSA 之后)
# ======================================================================

def find_conserved_regions(sequences: list[str],
                           window: int = 100,
                           step: int = 50,
                           max_entropy: float = 0.5,
                           do_align: bool = True,
                           aligner: str = "auto",
                           ignore_gap: bool = False) -> list[tuple]:
    """
    MSA → Shannon 熵滑动窗口 — 找到序列中最保守的区域用于引物设计。
    (集成 VirPrimer 的 Ignore gap 逻辑)

    VirPrimer 'Ignore gap' 借鉴:
      当 ignore_gap=True 时, 直接跳过 Indel 区域的位点。
      Indel 区域的引物在某些分离株中会因插入缺失而完全失效。

    科学原理:
      H(i) = -Σ p_i * log₂(p_i)
      每个位点 H=0 表示完全保守 (所有序列同一碱基), H=2 表示完全随机。
      低熵区域最适合作为引物结合位点。
    """
    if not sequences:
        return []

    # Step 1: MSA
    if do_align and len(sequences) > 1:
        aligned = run_msa(sequences, aligner)
    else:
        if len(sequences) > 1:
            min_len = min(len(s) for s in sequences if s)
            aligned = [s[:min_len] for s in sequences if s]
        else:
            aligned = [s for s in sequences if s]

    if not aligned:
        return []

    aln_len = len(aligned[0])
    if aln_len < window:
        return [(0, aln_len)] if aln_len >= 150 else []

    # Step 2: Shannon 熵滑动窗口 (带 Ignore gap 选项)
    wins = []
    for start in range(0, aln_len - window, step):
        end = start + window
        e_total = 0.0
        valid_positions = 0
        for pos in range(start, end):
            counts = {'A': 0, 'T': 0, 'G': 0, 'C': 0}

            # ★ VirPrimer 借鉴: Ignore gap = True 时跳过 indel 位点
            if ignore_gap:
                has_gap = False
                for s in aligned:
                    if s[pos] == '-':
                        has_gap = True
                        break
                if has_gap:
                    continue  # 跳过该位点, 不计入 entropy

            for s in aligned:
                nt = s[pos]
                if nt in counts:
                    counts[nt] += 1

            total = sum(counts.values())
            if total == 0:
                continue

            h = 0.0
            for c in counts.values():
                if c > 0:
                    p = c / total
                    h -= p * math.log2(p)
            e_total += h
            valid_positions += 1

        if valid_positions < window * 0.5:
            continue  # 跳过 gap 过多的窗口
        avg_e = e_total / valid_positions
        wins.append((start, end, avg_e))

    # 合并相邻低熵窗口
    conserved = []
    i = 0
    while i < len(wins):
        if wins[i][2] <= max_entropy:
            rs, _, _ = wins[i]
            re = rs + window
            j = i + 1
            while j < len(wins) and wins[j][2] <= max_entropy:
                re = wins[j][1]
                j += 1
            if re - rs >= 150:
                conserved.append((rs, re))
            i = j
        else:
            i += 1

    return conserved


def design_primers(sequences: list[str], num_pairs: int = 5,
                   prod_min: int = 250, prod_max: int = 1000,
                   do_align: bool = True, aligner: str = "auto",
                   ignore_gap: bool = False
                   ) -> list[dict]:
    """
    策略 A: PCR 保守引物设计

    输入: 一个病毒物种的所有序列
    流程:
      1. 如果多条序列 → MSA → Shannon 熵找保守区
      2. 如果单条序列 → 整条作为候选区
      3. 在保守区内运行 Primer3
      4. 按 Penalty 排序, 取 top-N

    输出: [{"Fwd_Seq":..., "Rev_Seq":..., "Fwd_Tm":..., ...}, ...]
    """
    if not sequences:
        return []
    ref = sequences[0]

    if len(sequences) > 1:
        cons = find_conserved_regions(sequences, do_align=do_align,
                                       aligner=aligner,
                                       ignore_gap=ignore_gap)
    else:
        cons = [(0, len(ref))]

    all_p = []
    for rs, re in cons:
        if re - rs < prod_min + 80:
            continue
        region = ref[rs:re]

        if PRIMER3_OK:
            p = _primer3_design(region, rs, num_pairs, prod_min, prod_max)
        else:
            p = _simple_design(region, rs, num_pairs, prod_min, prod_max)

        all_p.extend(p)

    all_p.sort(key=lambda x: x.get("Penalty", 999))
    return all_p[:num_pairs]


def _primer3_design(seq: str, offset: int, n: int,
                    pmin: int, pmax: int) -> list[dict]:
    """Primer3 引擎"""
    args = {
        'SEQUENCE_TEMPLATE': seq,
        'SEQUENCE_TARGET': [0, len(seq)],
        'PRIMER_NUM_RETURN': n * 2,
        'PRIMER_PRODUCT_SIZE_RANGE': [[pmin, pmax]],
        'PRIMER_MIN_SIZE': 18, 'PRIMER_OPT_SIZE': 20, 'PRIMER_MAX_SIZE': 25,
        'PRIMER_MIN_TM': 58.0, 'PRIMER_OPT_TM': 60.0, 'PRIMER_MAX_TM': 62.0,
        'PRIMER_MIN_GC': 40.0, 'PRIMER_OPT_GC': 50.0, 'PRIMER_MAX_GC': 60.0,
        'PRIMER_MAX_END_STABILITY': 9.0,
        'PRIMER_MAX_SELF_ANY': 4, 'PRIMER_MAX_SELF_END': 4,
        'PRIMER_PAIR_MAX_COMPL_ANY': 4, 'PRIMER_PAIR_MAX_COMPL_END': 4,
        'PRIMER_MAX_POLY_X': 5,
    }
    try:
        res = primer3.design_primers(args)
        out = []
        for i in range(res.get('PRIMER_PAIR_NUM_RETURNED', 0)):
            f = res.get(f'PRIMER_LEFT_{i}_SEQUENCE', '')
            r = res.get(f'PRIMER_RIGHT_{i}_SEQUENCE', '')
            if not f or not r:
                continue
            out.append({
                "Fwd_Seq": f, "Rev_Seq": r,
                "Fwd_Tm": round(res.get(f'PRIMER_LEFT_{i}_TM', 0), 1),
                "Rev_Tm": round(res.get(f'PRIMER_RIGHT_{i}_TM', 0), 1),
                "Product": res.get(f'PRIMER_PAIR_{i}_PRODUCT_SIZE', 0),
                "GC_Fwd": round(GC(f), 1), "GC_Rev": round(GC(r), 1),
                "Penalty": round(res.get(f'PRIMER_PAIR_{i}_PENALTY', 0), 2),
                "Method": "Primer3"
            })
        return out
    except Exception:
        return []


def _simple_design(seq: str, offset: int, n: int,
                   pmin: int, pmax: int) -> list[dict]:
    """简化引物设计 (Primer3 不可用时的后备)"""
    cand = []
    L = len(seq)
    for pos in range(0, L - 23, 3):
        for plen in [19, 20, 21, 22]:
            if pos + plen > L:
                break
            o = seq[pos:pos + plen]
            gc = (o.count('G') + o.count('C')) / plen
            if gc < 0.40 or gc > 0.60:
                continue
            tm = 2 * (o.count('A') + o.count('T')) + 4 * (o.count('G') + o.count('C'))
            if tm < 56 or tm > 62:
                continue
            if (o[-5:].count('G') + o[-5:].count('C')) / 5 < 0.4:
                continue
            if any(nt * 6 in o for nt in 'ATGC'):
                continue
            if _self_comp(o) >= 5:
                continue
            cand.append({"pos": pos, "len": plen, "seq": o, "gc": gc, "tm": tm})

    out = []
    seen = set()
    for f in cand:
        for r in cand:
            if f["pos"] >= r["pos"]:
                continue
            ps = r["pos"] + r["len"] - f["pos"]
            if ps < pmin or ps > pmax:
                continue
            if abs(f["tm"] - r["tm"]) > 5:
                continue
            rk = (f["pos"] // 50, r["pos"] // 50)
            if rk in seen:
                continue
            seen.add(rk)
            r_seq = str(Seq(r["seq"]).reverse_complement())
            if _pair_comp(f["seq"], r_seq) >= 5:
                continue
            out.append({
                "Fwd_Seq": f["seq"], "Rev_Seq": r_seq,
                "Fwd_Tm": round(f["tm"], 1), "Rev_Tm": round(r["tm"], 1),
                "Product": ps,
                "GC_Fwd": round(f["gc"] * 100, 1),
                "GC_Rev": round(r["gc"] * 100, 1),
                "Penalty": round(abs(f["tm"] - 60) + abs(r["tm"] - 60) +
                                abs(f["gc"] - 0.5) * 20, 2),
                "Method": "Simple_Thermo"
            })
            if len(out) >= n * 3:
                break
        if len(out) >= n * 3:
            break

    out.sort(key=lambda x: x["Penalty"])
    return out[:n]


def _self_comp(seq: str) -> int:
    rc = str(Seq(seq).reverse_complement())
    m = 0
    for i in range(len(seq)):
        for j in range(i + 1, len(seq) + 1):
            s = seq[i:j]
            if len(s) > m and s in rc:
                m = len(s)
    return m


def _pair_comp(f: str, r: str) -> int:
    rc = str(Seq(f).reverse_complement())
    m = 0
    for i in range(len(rc)):
        for j in range(i + 1, len(rc) + 1):
            s = rc[i:j]
            if len(s) > m and s in r:
                m = len(s)
    return m


def design_qpcr(sequences: list[str], n: int = 3,
                amp_min: int = 80, amp_max: int = 200,
                do_align: bool = True, aligner: str = "auto",
                ignore_gap: bool = False) -> list[dict]:
    """
    策略 B: qPCR + TaqMan 探针

    qPCR 与常规 PCR 的关键区别:
      - 短扩增子 (80-200bp) 保证扩增效率 > 90%
      - TaqMan 探针 Tm 比引物高 8-10°C (68-70°C)
      - 探针 5' 端不能是 G (会淬灭荧光)
    """
    if not sequences:
        return []
    ref = sequences[0]

    if len(sequences) > 1:
        cons = find_conserved_regions(sequences, window=60, step=30,
                                       max_entropy=0.3,
                                       ignore_gap=ignore_gap,
                                       do_align=do_align, aligner=aligner)
    else:
        cons = [(0, len(ref))]

    all_d = []
    for rs, re in cons:
        if re - rs < amp_max + 100:
            continue
        reg = ref[rs:re]

        if PRIMER3_OK:
            try:
                r = primer3.design_primers({
                    'SEQUENCE_TEMPLATE': reg,
                    'PRIMER_NUM_RETURN': n * 2,
                    'PRIMER_PRODUCT_SIZE_RANGE': [[amp_min, amp_max]],
                    'PRIMER_MIN_SIZE': 18, 'PRIMER_OPT_SIZE': 20, 'PRIMER_MAX_SIZE': 22,
                    'PRIMER_MIN_TM': 58.0, 'PRIMER_OPT_TM': 59.0, 'PRIMER_MAX_TM': 61.0,
                    'PRIMER_MIN_GC': 40.0, 'PRIMER_MAX_GC': 60.0,
                    'PRIMER_MAX_END_STABILITY': 9.0,
                    'PRIMER_MAX_SELF_ANY': 3, 'PRIMER_MAX_SELF_END': 3,
                    'PRIMER_PAIR_MAX_COMPL_ANY': 3, 'PRIMER_PAIR_MAX_COMPL_END': 3,
                    'PRIMER_MAX_POLY_X': 4,
                })
                for i in range(r.get('PRIMER_PAIR_NUM_RETURNED', 0)):
                    f = r.get(f'PRIMER_LEFT_{i}_SEQUENCE', '')
                    rev = r.get(f'PRIMER_RIGHT_{i}_SEQUENCE', '')
                    if not f or not rev:
                        continue
                    fe = r.get(f'PRIMER_LEFT_{i}_0', 0) + len(f)
                    rs2 = r.get(f'PRIMER_RIGHT_{i}_0', 0)
                    probe = _find_probe(reg[fe:rs2])
                    all_d.append({
                        "Fwd_Seq": f, "Rev_Seq": rev,
                        "Probe_Seq": probe.get("seq", ""),
                        "Probe_Tm": probe.get("tm", ""),
                        "Fwd_Tm": round(r.get(f'PRIMER_LEFT_{i}_TM', 0), 1),
                        "Rev_Tm": round(r.get(f'PRIMER_RIGHT_{i}_TM', 0), 1),
                        "Product": r.get(f'PRIMER_PAIR_{i}_PRODUCT_SIZE', 0),
                        "GC_Fwd": round(GC(f), 1), "GC_Rev": round(GC(rev), 1),
                        "Penalty": round(r.get(f'PRIMER_PAIR_{i}_PENALTY', 0), 2),
                        "Method": "Primer3_qPCR"
                    })
            except Exception:
                pass

    all_d.sort(key=lambda x: x.get("Penalty", 999))
    return all_d[:n]


def _find_probe(seq: str, mn: int = 18, mx: int = 28) -> dict:
    """TaqMan 探针扫描"""
    for l in range(mx, mn - 1, -1):
        for s in range(len(seq) - l + 1):
            c = seq[s:s + l]
            if c[0] == 'G' or c[-1] == 'G':
                continue
            gc = (c.count('G') + c.count('C')) / l
            if gc < 0.40 or gc > 0.60:
                continue
            tm = 2 * (c.count('A') + c.count('T')) + 4 * (c.count('G') + c.count('C'))
            if 65 <= tm <= 72:
                return {"seq": c, "tm": round(tm, 1), "gc": round(gc * 100, 1)}
    return {"seq": "", "tm": ""}


# ======================================================================
# 3c. 简并引物设计 (策略 C)
# ======================================================================

IUPAC_TABLE = {
    frozenset(['A']): 'A', frozenset(['C']): 'C',
    frozenset(['G']): 'G', frozenset(['T']): 'T',
    frozenset(['A', 'G']): 'R', frozenset(['C', 'T']): 'Y',
    frozenset(['G', 'C']): 'S', frozenset(['A', 'T']): 'W',
    frozenset(['G', 'T']): 'K', frozenset(['A', 'C']): 'M',
    frozenset(['A', 'C', 'G']): 'V', frozenset(['A', 'C', 'T']): 'H',
    frozenset(['A', 'G', 'T']): 'D', frozenset(['C', 'G', 'T']): 'B',
    frozenset(['A', 'C', 'G', 'T']): 'N',
}


def iupac_consensus(sequences: list[str]) -> str:
    """
    从多序列比对结果生成 IUPAC 简并一致性序列。

    输入必须是 MSA 后的序列 (含 gap '-')。
    输出: 一条含 IUPAC 简并码的 consensus 序列。
    """
    aln_len = len(sequences[0])
    consensus = []
    for pos in range(aln_len):
        nts = set()
        for s in sequences:
            n = s[pos]
            if n in ('A', 'T', 'G', 'C'):
                nts.add(n)
            # gap 视为缺失, 不投票
        if not nts:
            consensus.append('N')
        else:
            consensus.append(IUPAC_TABLE.get(frozenset(nts), 'N'))
    return ''.join(consensus)


def design_degenerate_primers(sequences: list[str],
                               do_align: bool = True,
                               aligner: str = "auto",
                               num_pairs: int = 3) -> list[dict]:
    """
    策略 C: 简并引物设计

    适用: 高变异病毒, 同一物种不同株系在引物结合区存在变异。

    流程:
      1. MSA 对齐多序列
      2. 生成 IUPAC 简并共识序列
      3. 在低简并度区域 (保守区) 设计引物
      4. 计算每条引物的简并度
    """
    if len(sequences) < 2:
        return []

    # MSA
    if do_align:
        aligned = run_msa(sequences, aligner)
    else:
        min_len = min(len(s) for s in sequences if s)
        aligned = [s[:min_len] for s in sequences if s]

    if not aligned:
        return []

    # IUPAC consensus
    con_seq = iupac_consensus(aligned)
    aln_len = len(con_seq)

    # 滑动窗口: 找简并度最低的区域 (最适合放引物)
    # 简并度 = IUPAC 码对应的碱基组合数
    def degeneracy(code):
        if code in 'ATGC': return 1
        if code in 'RYSWKM': return 2
        if code in 'BDHV': return 3
        if code == 'N': return 4
        return 1

    # 打分: 滑动窗口, 计算窗口内平均简并度
    best_regions = []
    for start in range(0, aln_len - 250, 10):
        end = min(start + 200, aln_len)
        # 前80bp (正向引物区) + 中间gap + 后80bp (反向引物区)
        fwd_region = con_seq[start:start + 80]
        rev_region = con_seq[end - 80:end]

        fwd_degen = sum(degeneracy(c) for c in fwd_region)
        rev_degen = sum(degeneracy(c) for c in rev_region)

        score = fwd_degen + rev_degen
        best_regions.append((score, start, end))

    best_regions.sort(key=lambda x: x[0])

    designs = []
    for score, start, end in best_regions[:num_pairs * 3]:
        # 从保守区提取引物
        fwd_cand = con_seq[start:start + 22]
        rev_cand = con_seq[end - 22:end]

        if len(fwd_cand) < 18 or len(rev_cand) < 18:
            continue
        rev_cand = str(Seq(rev_cand).reverse_complement())

        # 计算引物简并度
        fwd_deg = 1
        for c in fwd_cand:
            fwd_deg *= degeneracy(c)
        rev_deg = 1
        for c in rev_cand:
            rev_deg *= degeneracy(c)

        # GC 含量 (简并引物放宽到 35-65%)
        fwd_gc = (fwd_cand.count('G') + fwd_cand.count('C') +
                  fwd_cand.count('S')) / 22 * 100
        rev_gc = (rev_cand.count('G') + rev_cand.count('C') +
                  rev_cand.count('S')) / 22 * 100

        total_deg = fwd_deg * rev_deg
        if total_deg > 256:     # 简并度过高, 引物浓度会被稀释
            continue
        if not (20 <= fwd_gc <= 80 and 20 <= rev_gc <= 80):
            continue

        designs.append({
            "Fwd_Seq": fwd_cand, "Rev_Seq": rev_cand,
            "Probe_Seq": "", "Probe_Tm": "",
            "Fwd_Tm": "", "Rev_Tm": "",
            "Product": end - start,
            "GC_Fwd": round(fwd_gc, 1), "GC_Rev": round(rev_gc, 1),
            "Fwd_Degeneracy": fwd_deg, "Rev_Degeneracy": rev_deg,
            "Total_Degeneracy": total_deg,
            "Penalty": total_deg,
            "Method": "IUPAC_Degenerate"
        })

    designs.sort(key=lambda x: x.get("Penalty", 999))
    return designs[:num_pairs]


# ======================================================================
# 3d. 全基因组平铺扩增 (策略 D)
# ======================================================================

def design_tiled_amplicons(sequences: list[str],
                           tile_len: int = 1200,
                           overlap: int = 100,
                           num_pairs_per_tile: int = 2) -> list[dict]:
    """
    策略 D: 全基因组平铺扩增引物设计

    适用: 全基因组测序 / 宏基因组学, 需要覆盖整个病毒基因组。

    流程:
      1. 选择最长序列作为参考
      2. 滑动窗口生成 tiles (步长 = tile_len - overlap)
      3. 每个 tile 内用 Primer3 设计引物
      4. 每个 tile 可产生多对引物 (以数量确保覆盖率)
    """
    if not sequences:
        return []

    # 选最长序列做参考
    ref = max(sequences, key=len)
    ref_len = len(ref)

    designs = []
    step = tile_len - overlap

    for tile_i, start in enumerate(range(0, ref_len - tile_len, step)):
        end = min(start + tile_len, ref_len)
        tile_seq = ref[start:end]

        # 对该 tile 的左右两端设计引物
        # 左端: 前 500bp
        left_region = tile_seq[:min(500, len(tile_seq))]
        # 右端: 后 500bp
        right_region = tile_seq[-min(500, len(tile_seq)):]

        # 在左右端分别设计
        for side, region in [("left", left_region), ("right", right_region)]:
            if PRIMER3_OK:
                primers = _primer3_design(
                    region, start if side == "left" else end - len(region),
                    num_pairs_per_tile // 2 + 1, 200, 500
                )
            else:
                primers = _simple_design(
                    region, start if side == "left" else end - len(region),
                    num_pairs_per_tile // 2 + 1, 200, 500
                )
            for p in primers:
                p["Tile_ID"] = tile_i + 1
                p["Tile_Start"] = start
                p["Tile_End"] = end
                p["Tiled_Side"] = side
                p["Method"] = "Tiled_Primer3"
                designs.append(p)

    return designs


# ======================================================================
# 4. 单个物种处理
# ======================================================================

def process_species(sp: str, records: list[dict], args) -> list[dict]:
    """
    为一个物种设计所有类型的引物。

    节段病毒处理 (MRPrimerV 策略):
      - 非节段: 所有序列是同一基因组的不同分离株 → 放在一起做 MSA
      - 节段:   不同节段是独立的基因组, 按节段分组, 每个节段独立设计
      - MRPrimerV: "if valid primers exist for some segments of a virus,
           we can detect that virus using those primers even when there
           are no valid primers for the remaining segments"
    """
    if not records:
        return []

    family = records[0].get("family", "")
    genus = records[0].get("genus", "")
    do_align = not args.no_align
    aligner = args.aligner

    # 检查是否有节段信息
    has_segments = any(r.get("segment", "") for r in records if r.get("seq"))

    if has_segments:
        # ★ 节段病毒: 按节段分组, 每组独立设计引物
        segments = defaultdict(list)
        for r in records:
            if r.get("seq"):
                seg = r.get("segment", "unknown") or "unknown"
                segments[seg].append(r)

        out = []
        for seg_name, seg_records in segments.items():
            seqs = [r["seq"] for r in seg_records if r.get("seq")]
            if not seqs:
                continue
            exclude = getattr(args, 'exclude_seqs', [])
            out += _design_for_species(
                sp, seqs, family, genus, seg_name, args, do_align, aligner,
                exclude_seqs=exclude
            )
        return out
    else:
        # ★ 非节段: 所有序列作为不同分离株处理
        seqs = [r["seq"] for r in records if r.get("seq")]
        if not seqs:
            return []
        exclude = getattr(args, 'exclude_seqs', [])
        return _design_for_species(
            sp, seqs, family, genus, "", args, do_align, aligner,
            exclude_seqs=exclude
        )


def _design_for_species(sp: str, seqs: list[str],
                         family: str, genus: str,
                         segment: str, args,
                         do_align: bool, aligner: str,
                         exclude_seqs: list = None) -> list[dict]:
    """
    对一组序列 (同一物种同一节段) 执行四种引物设计策略。

    VirPrimer 借鉴:
      - Ignore gap: 跳过 Indel 区域
      - Exclusion filtering: 排除序列集过滤脱靶引物
      - Primers per kb: 按基因组长度缩放引物数
    """
    n_seqs = len(seqs)
    max_len = max((len(s) for s in seqs), default=0)
    exclude_seqs = exclude_seqs or []

    # VirPrimer 借鉴: 按基因组长度缩放引物数
    if args.primers_per_kb > 0 and max_len > 0:
        scaled = max(1, round(max_len / 1000 * args.primers_per_kb))
        num_pcr = scaled
        num_qpcr = max(1, scaled // 2)
        num_degen = max(1, scaled // 2)
    else:
        num_pcr = args.num_pcr
        num_qpcr = args.num_qpcr
        num_degen = args.num_degen

    out = []

    # A: PCR 保守引物
    if not args.skip_pcr:
        for p in design_primers(seqs, num_pcr,
                                args.pmin, args.pmax,
                                do_align=do_align, aligner=aligner,
                                ignore_gap=args.ignore_gap):
            p.update({"Species": sp, "Type": "PCR",
                      "Family": family, "Genus": genus,
                      "Segment": segment, "Num_Seqs": n_seqs})
            out.append(p)

    # B: qPCR + TaqMan 探针
    if not args.skip_qpcr:
        for p in design_qpcr(seqs, args.num_qpcr,
                              do_align=do_align, aligner=aligner,
                              ignore_gap=args.ignore_gap):
            p.update({"Species": sp, "Type": "qPCR",
                      "Family": family, "Genus": genus,
                      "Segment": segment, "Num_Seqs": n_seqs})
            out.append(p)

    # C: 简并引物 (仅当 ≥2 条序列时)
    if not args.skip_degenerate and n_seqs >= args.degen_threshold:
        if args.use_varvamp and _varvamp_available():
            for p in _run_varvamp(seqs, sp, segment, args):
                p.update({"Species": sp, "Type": "DEGENERATE",
                          "Family": family, "Genus": genus,
                          "Segment": segment, "Num_Seqs": n_seqs})
                out.append(p)
        else:
            for p in design_degenerate_primers(seqs, do_align=do_align,
                                                aligner=aligner,
                                                num_pairs=args.num_degen):
                p.update({"Species": sp, "Type": "DEGENERATE",
                          "Family": family, "Genus": genus,
                          "Segment": segment, "Num_Seqs": n_seqs})
                out.append(p)

    # D: 全基因组平铺扩增 (仅当基因组 > 2000bp)
    if not args.skip_tiled and max_len > args.tile_min_len:
        if args.use_olivar and _olivar_available():
            for p in _run_olivar(seqs, sp, segment, args):
                p.update({"Species": sp, "Type": "TILED",
                          "Family": family, "Genus": genus,
                          "Segment": segment, "Num_Seqs": n_seqs})
                out.append(p)
        else:
            for p in design_tiled_amplicons(seqs, tile_len=args.tile_len,
                                             overlap=args.tile_overlap):
                p.update({"Species": sp, "Type": "TILED",
                          "Family": family, "Genus": genus,
                          "Segment": segment, "Num_Seqs": n_seqs})
                out.append(p)

    # ★ VirPrimer 借鉴: 排除序列过滤
    if exclude_seqs and out:
        before = len(out)
        out = _filter_by_exclusion(out, exclude_seqs)
        removed = before - len(out)
        if removed:
            print(f"      排除序列过滤: 移除 {removed} 对脱靶引物")

    return out


def _filter_by_exclusion(primers: list[dict],
                          exclude_seqs: list[str]) -> list[dict]:
    """
    VirPrimer 借鉴: 排除序列集过滤。

    对于每对引物, 检查正向/反向引物是否与排除序列互补结合。
    使用 primer3-py 的 calc_heterodimer 评估结合 ΔG。
    如果正反向引物都与排除序列的任一位置有 ΔG < -9 kcal/mol 的结合,
    则认为该引物对会扩增排除序列 (脱靶), 需要移除。
    """
    if not primers or not exclude_seqs:
        return primers

    try:
        import primer3 as p3
    except ImportError:
        return primers

    filtered = []
    for p in primers:
        fwd = p.get("Fwd_Seq", "")
        rev = p.get("Rev_Seq", "")
        if not fwd or not rev:
            filtered.append(p)
            continue

        # 检查正向引物是否与排除序列结合
        fwd_offtarget = False
        rev_offtarget = False

        for ex_seq in exclude_seqs:
            if len(ex_seq) < 20:
                continue
            # 滑动窗口: 排除序列中找到与引物互补的区域
            for i in range(len(ex_seq) - len(fwd) + 1):
                window = ex_seq[i:i + len(fwd)]
                try:
                    dg = p3.calc_heterodimer(fwd, window).dg
                    if dg and dg < -9:  # 强结合 → 脱靶风险
                        fwd_offtarget = True
                        break
                except Exception:
                    continue
            if fwd_offtarget:
                break

        # 同上, 检查反向引物
        for ex_seq in exclude_seqs:
            if len(ex_seq) < 20:
                continue
            for i in range(len(ex_seq) - len(rev) + 1):
                window = ex_seq[i:i + len(rev)]
                try:
                    dg = p3.calc_heterodimer(rev, window).dg
                    if dg and dg < -9:
                        rev_offtarget = True
                        break
                except Exception:
                    continue
            if rev_offtarget:
                break

        # 只有当正反向引物都不与排除序列结合时才保留
        if not fwd_offtarget and not rev_offtarget:
            filtered.append(p)

    return filtered


# ======================================================================
# 3e. 第三方工具集成: varVAMP
# ======================================================================

def _varvamp_available() -> bool:
    """检测 varVAMP 是否已安装"""
    import shutil
    return shutil.which("varvamp") is not None or \
           (Path(__file__).parent / "varVAMP" / "varvamp" / "__main__.py").exists()


def _run_varvamp(seqs: list[str], sp: str, segment: str,
                  args) -> list[dict]:
    """
    调用 varVAMP 设计简并引物。

    varVAMP 核心价值 (Nature Communications 2025):
      - 动态规划优化简并编码
      - 最小化 3' 端错配
      - 平衡覆盖率和引物简并度
      - 支持 qPCR/SINGLE/TILED 三种模式
    """
    import tempfile, shutil, subprocess

    # 写临时 FASTA
    safe_name = f"{sp}_{segment}".replace(' ', '_').replace('/', '_')[:60]
    tmp_dir = Path(tempfile.mkdtemp())
    fa_file = tmp_dir / f"{safe_name}.fasta"
    with open(fa_file, 'w') as f:
        for i, s in enumerate(seqs):
            f.write(f">seq_{i}\n{s}\n")

    out_dir = Path(args.output) / "varvamp_tmp" / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 尝试用 pip 安装的 varvamp
        cmd = ["varvamp", str(fa_file), "-o", str(out_dir),
               "-m", "qpcr", "-t", str(args.threads), "--no-cluster"]
        # 如果 pip 版本不可用, 用本地脚本
        local_script = Path(__file__).parent / "varVAMP" / "varvamp" / "__main__.py"
        if local_script.exists() and not shutil.which("varvamp"):
            cmd = ["python", str(local_script), str(fa_file),
                   "-o", str(out_dir), "-m", "qpcr",
                   "-t", str(args.threads), "--no-cluster"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

        if result.returncode != 0:
            raise RuntimeError(result.stderr[:500])

        # 解析 varVAMP 输出
        primer_file = out_dir / "primers.tsv"
        if not primer_file.exists():
            # 尝试查找其他输出文件名
            primer_files = list(out_dir.glob("*primers*"))
            primer_file = primer_files[0] if primer_files else None

        designs = []
        if primer_file and primer_file.exists():
            df = pl.read_csv(primer_file, separator='\t', ignore_errors=True)
            for row in df.iter_rows(named=True):
                fwd = str(row.get('fwd', row.get('forward', '')))
                rev = str(row.get('rev', row.get('reverse', '')))
                if fwd and rev and len(fwd) >= 15:
                    designs.append({
                        "Fwd_Seq": fwd, "Rev_Seq": rev,
                        "Probe_Seq": str(row.get('probe', '')),
                        "Fwd_Tm": str(row.get('tm_fwd', row.get('tm', ''))),
                        "Rev_Tm": str(row.get('tm_rev', '')),
                        "Product": str(row.get('amplicon_len', row.get('product_size', ''))),
                        "Fwd_Degeneracy": row.get('degeneracy_fwd', ''),
                        "Rev_Degeneracy": row.get('degeneracy_rev', ''),
                        "Penalty": row.get('penalty', ''),
                        "Method": "varVAMP"
                    })
            if designs:
                print(f"      varVAMP: {len(designs)} 对简并引物")
    except Exception as e:
        print(f"      ⚠ varVAMP 失败: {e}")

    # 清理临时文件
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    return designs[:args.num_degen]


# ======================================================================
# 3f. 第三方工具集成: Olivar
# ======================================================================

def _olivar_available() -> bool:
    """检测 Olivar 是否已安装"""
    import shutil
    return shutil.which("olivar") is not None


def _run_olivar(seqs: list[str], sp: str, segment: str,
                 args) -> list[dict]:
    """
    调用 Olivar 设计全基因组平铺扩增引物。

    Olivar 核心价值 (Nature Communications 2024):
      - 两相 PCR 策略: Phase 1 (长, 1.2-2.5kb) + Phase 2 (短, 200-500bp)
      - SADDLE 算法: 全局引物二聚体最小化
      - GC 偏差校正
      - BLAST 宿主基因组特异性过滤
    """
    import tempfile, shutil, subprocess

    safe_name = f"{sp}_{segment}".replace(' ', '_').replace('/', '_')[:60]
    tmp_dir = Path(tempfile.mkdtemp())
    fa_file = tmp_dir / f"{safe_name}.fasta"
    ref_file = tmp_dir / f"{safe_name}_ref.fasta"

    # Olivar 支持两种输入模式:
    # Mode 1: MSA (多条序列)
    # Mode 2: 参考序列 + VCF (单条)
    # 对多于1条序列用 Mode 1, 单条用 Mode 2
    if len(seqs) > 1:
        with open(fa_file, 'w') as f:
            for i, s in enumerate(seqs):
                f.write(f">seq_{i}\n{s}\n")
        input_path = fa_file
    else:
        with open(ref_file, 'w') as f:
            f.write(f">ref\n{seqs[0]}\n")
        input_path = ref_file

    out_dir = Path(args.output) / "olivar_tmp" / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)

    designs = []
    try:
        # 1. build
        build_cmd = ["olivar", "build", "-i", str(input_path),
                     "-o", str(out_dir / "build"),
                     "-p", str(args.threads)]
        subprocess.run(build_cmd, capture_output=True, text=True, timeout=600)

        # 2. tiling
        tile_cmd = ["olivar", "tiling", "-i", str(out_dir / "build"),
                    "-o", str(out_dir / "tiling"),
                    "-p", str(args.threads),
                    "--amplicon-size", str(args.tile_len),
                    "--overlap", str(args.tile_overlap)]
        subprocess.run(tile_cmd, capture_output=True, text=True, timeout=600)

        # 3. 解析 Olivar 输出 (.primers.tsv / .primer.bed)
        for tsv in (out_dir / "tiling").glob("*primers*"):
            df = pl.read_csv(tsv, separator='\t', ignore_errors=True)
            for row in df.iter_rows(named=True):
                fwd = str(row.get('forward', row.get('fwd', '')))
                rev = str(row.get('reverse', row.get('rev', '')))
                if fwd and rev:
                    designs.append({
                        "Fwd_Seq": fwd, "Rev_Seq": rev,
                        "Probe_Seq": "", "Probe_Tm": "",
                        "Fwd_Tm": str(row.get('tm_fwd', '')),
                        "Rev_Tm": str(row.get('tm_rev', '')),
                        "Product": str(row.get('amplicon_len', row.get('product_size', ''))),
                        "GC_Fwd": "", "GC_Rev": "",
                        "Tile_ID": row.get('tile', row.get('pool', '')),
                        "Penalty": '',
                        "Method": "Olivar"
                    })

        if designs:
            print(f"      Olivar: {len(designs)} 对平铺引物")

    except Exception as e:
        print(f"      ⚠ Olivar 失败: {e}")

    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    return designs


# ======================================================================
# 5. 主入口
# ======================================================================

def main():
    p = argparse.ArgumentParser(description="植物病毒引物批量设计 v3")

    p.add_argument('--species-dir', required=True,
                   help='step1 输出的 species 目录 (含 *.fasta 文件)')
    p.add_argument('--species', default='', help='仅设计指定物种（支持部分匹配）')

    p.add_argument('-o', '--output', default='designed_primers')
    p.add_argument('-t', '--threads', type=int, default=8)
    p.add_argument('--limit', type=int, default=0, help='限制物种处理数')

    # PCR 参数
    p.add_argument('--num-pcr', type=int, default=5)
    p.add_argument('--num-qpcr', type=int, default=3)
    p.add_argument('--num-degen', type=int, default=3)
    p.add_argument('--pmin', type=int, default=250, help='PCR 最小产物')
    p.add_argument('--pmax', type=int, default=1000, help='PCR 最大产物')
    p.add_argument('--degen-threshold', type=int, default=2,
                   help='GE N条序列才设计简并引物 (默认: 2)')

    # 平铺扩增参数
    p.add_argument('--tile-len', type=int, default=1200,
                   help='平铺扩增子长度 (默认: 1200bp)')
    p.add_argument('--tile-overlap', type=int, default=100,
                   help='平铺扩增子重叠 (默认: 100bp)')
    p.add_argument('--tile-min-len', type=int, default=2000,
                   help='最小基因组大小才启用平铺 (默认: 2000bp)')

    # MSA 参数
    p.add_argument('--no-align', action='store_true',
                   help='跳过多序列比对 (MSA), 使用截断对齐')
    p.add_argument('--aligner', default='auto',
                   choices=['auto', 'mafft', 'muscle', 'clustalo', 'no'],
                   help='MSA 比对工具 (默认: auto 自动检测)')

    # 跳过选项 (默认启用简并和平铺)
    p.add_argument('--skip-pcr', action='store_true')
    p.add_argument('--skip-qpcr', action='store_true')
    p.add_argument('--skip-degenerate', action='store_true')
    p.add_argument('--skip-tiled', action='store_true')

    # VirPrimer 借鉴: Ignore gap, 排除序列, 按长度缩放引物数
    p.add_argument('--ignore-gap', action='store_true',
                   help='VirPrimer模式: 跳过 Indel 区域设计引物')
    p.add_argument('--exclude-fasta', default='',
                   help='VirPrimer模式: 排除序列集 FAST (脱靶过滤)')
    p.add_argument('--primers-per-kb', type=float, default=0,
                   help='VirPrimer模式: 每kb基因组设计引物对数 (0=使用--num-pcr固定值)')

    # 第三方工具集成
    p.add_argument('--use-varvamp', action='store_true',
                   help='使用 varVAMP 设计简并引物 (需 pip install varvamp)')
    p.add_argument('--use-olivar', action='store_true',
                   help='使用 Olivar 设计平铺扩增引物 (需 conda install olivar)')

    args = p.parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 加载排除序列集 (VirPrimer 借鉴) ---
    exclude_seqs = []
    if args.exclude_fasta:
        excl_path = Path(args.exclude_fasta)
        if excl_path.exists():
            for rec in SeqIO.parse(excl_path, 'fasta'):
                exclude_seqs.append(str(rec.seq).upper())
            print(f"> 排除序列集: {excl_path.name} ({len(exclude_seqs)} 条)")
        else:
            print(f"  ⚠ 排除序列文件不存在: {excl_path}")

    args.exclude_seqs = exclude_seqs  # 存到 args 供 process_species 使用

    # --- 加载 step1 输出的 species 目录 ---
    species_dir = Path(args.species_dir)
    if not species_dir.exists():
        print(f"X species 目录不存在: {species_dir}"); return

    species_map = {}
    for fa_file in sorted(species_dir.glob('*.fasta')):
        sp_name = fa_file.stem.replace('_', ' ').strip()
        records = []
        for rec in SeqIO.parse(fa_file, 'fasta'):
            # 从 header 中提取节段信息: >acc|segment=Seg1
            seg = ""
            desc = rec.description
            if "|segment=" in desc:
                seg = desc.split("|segment=")[1].split()[0].strip()
            records.append({
                'acc': rec.id, 'seq': str(rec.seq).upper(),
                'family': '', 'genus': '', 'segment': seg
            })
        if records:
            species_map[sp_name] = records

    total_multi = sum(1 for r in species_map.values() if len(r) >= 2
                       and not any(x.get('segment') for x in r))
    total_single = sum(1 for r in species_map.values()
                        if len(r) == 1 and not any(x.get('segment') for x in r))
    total_seg = sum(1 for r in species_map.values()
                     if any(x.get('segment') for x in r))
    print(f"> {len(species_map)} 物种: {total_multi} 多序列, {total_single} 单序列, {total_seg} 节段")
    if not species_map:
        print("✗ 未解析到任何物种"); return

    # 过滤 + 排序
    items = list(species_map.items())
    if args.species:
        items = [(n, r) for n, r in items if args.species.lower() in n.lower()]
    items.sort(key=lambda x: len(x[1]), reverse=True)
    if args.limit:
        items = items[:args.limit]

    print(f"\n▶ 开始: {len(items)} 个物种, {sum(len(r) for _, r in items)} 条序列")
    print(f"  MSA: {'截断对齐' if args.no_align else f'{args.aligner}'}")
    print(f"  PCR:  {'✓' if not args.skip_pcr else '✗'} ({args.num_pcr} 对/物种)")
    print(f"  qPCR: {'✓' if not args.skip_qpcr else '✗'} ({args.num_qpcr} 对/物种)")
    print(f"  简并: {'✓' if not args.skip_degenerate else '✗'} ({args.num_degen} 对/物种, ≥{args.degen_threshold}条)")
    print(f"  平铺: {'✓' if not args.skip_tiled else '✗'} ({args.tile_len}bp扩增子, ≥{args.tile_min_len}bp基因组)")
    print(f"  并行: {args.threads} 线程\n")

    # 并行处理
    all_results = []
    with ProcessPoolExecutor(max_workers=args.threads) as ex:
        fut_to_sp = {ex.submit(process_species, sp, rec, args): sp
                     for sp, rec in items}
        done = 0
        for fut in as_completed(fut_to_sp):
            sp = fut_to_sp[fut]
            done += 1
            try:
                r = fut.result()
                all_results.extend(r)
            except Exception as e:
                print(f"  ✗ {sp}: {e}")
            if done % 50 == 0 or done == len(fut_to_sp):
                print(f"  进度: {done}/{len(fut_to_sp)}, 累计引物: {len(all_results)}")

    # 保存
    if all_results:
        cols = ["Species", "Type", "Segment", "Family", "Genus", "Num_Seqs",
                "Fwd_Seq", "Rev_Seq",
                "Probe_Seq", "Probe_Tm",
                "Fwd_Tm", "Rev_Tm",
                "Product",
                "GC_Fwd", "GC_Rev",
                "Fwd_Degeneracy", "Rev_Degeneracy", "Total_Degeneracy",
                "Tile_ID", "Tile_Start", "Tile_End",
                "Penalty", "Method"]
        norm = [{c: r.get(c, "") for c in cols} for r in all_results]
        df = pl.DataFrame(norm)
        out_tsv = out_dir / "all_primers.tsv"
        df.write_csv(out_tsv, separator='\t')

        print(f"\n{'='*70}")
        print("设计完成!")
        print(f"  总引物对: {len(df)}")
        for r in df.group_by("Type").agg(pl.len().alias("Count")).iter_rows(named=True):
            print(f"    {r['Type']}: {r['Count']} 对")
        print(f"  结果: {out_tsv}")
        print(f"  验证: python step3_validate_primers.py --input {out_tsv} --quick")
        print(f"{'='*70}")
    else:
        print("\n⚠ 未生成引物. 检查输入数据质量.")


if __name__ == "__main__":
    main()
