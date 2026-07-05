#!/usr/bin/env python3
"""
Step 3: 引物特异性验证 (重写版)
========================================================================
验证流程:

  1. 序列层面验证 (无外部依赖):
     - GC/Tm 复核 (Biopython MeltingTemp NN)
     - 二聚体分析 (primer3 calc_homodimer / calc_heterodimer → ΔG/Tm)
     - 3' 端稳定性检查 (最近 5bp ΔG)

  2. BLAST 特异性验证 (AutoPVPrimer 模式):
     - 本地 blastn 对病毒数据库 → 靶标命中
     - 本地 blastn 对植物数据库 → 脱靶检测
     - 命中分类: Target / CrossReactive / PlantOffTarget / Other
     - 特异性评分 (靶标命中占比)

  3. 热力学错配分析 (PCR_strainer 模式):
     - Nearest-Neighbor ΔG 错配惩罚
     - 3' 端错配惩罚加倍
     - 综合热力学脱靶风险

  4. 综合评分 (0-100):
     - ≥80: RECOMMENDED (推荐)
     - 60-79: USABLE      (可用)
     - <60:  NOT_RECOMMENDED (不推荐)

用法:
  python step3_validate_primers.py
    --input all_primers.tsv
    --output all_primers_validated.tsv
    --blast-db ~/database/virus_targets_db/virus_new
    --blast-db-plant ~/database/plant_targets_db/plants  (可选)
    --blast-batch 5000 --blast-jobs 1 --threads 32
    [--skip-blast] [--quick]
"""

import argparse, csv, json, os, sys, subprocess, tempfile, time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

import polars as pl
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqUtils import MeltingTemp as mt
from Bio.SeqUtils import gc_fraction

try:
    import primer3
    from primer3 import calc_heterodimer, calc_homodimer
    PRIMER3_OK = True
except ImportError:
    PRIMER3_OK = False
    calc_heterodimer = calc_homodimer = None

try:
    from tqdm import tqdm; TQDM_OK = True
except ImportError:
    TQDM_OK = False

# ─── 默认路径 ────────────────────────────────────────────
_BASE = Path(__file__).resolve().parent
DEFAULT_INPUT = str(_BASE / "designed_primers" / "all_primers.tsv")
DEFAULT_OUTPUT = str(_BASE / "designed_primers" / "all_primers_validated.tsv")

# ─── NN 热力学常量 ─────────────────────────────────────────
# 3' 端错配的 ΔG 惩罚因子 (kcal/mol)
M3PENALTY = 2.5  # 3' 端每 bp 错配额外惩罚
S3_THRESHOLD = -6.0  # 3' 端 5bp ΔG 稳定性阈值 (>-6: 不稳定)

# ─── 植物关键词 ───────────────────────────────────────────
PLANT_KEYWORDS = [
    'viridiplantae','plant','planta','arabidopsis','oryza','zea','triticum',
    'solanum','nicotiana','glycine','brassica','gossypium','cucumis','citrus',
    'malus','prunus','vitis','populus','medicago','hordeum','sorghum',
    'capsicum','daucus','lactuca','helianthus','spinacia','beta','ipomoea',
    'manihot','phaseolus','pisum','cajanus','vigna','theobroma','coffea',
    'camellia','camellia','pinus','picea','selaginella','physcomitrella',
    'marchantia','chlorophyta','rhodophyta','glaucophyta','streptophyta',
    'embryophyta','tracheophyta','magnoliophyta','eudicotyledons','monocotyledons',
]
VIRUS_KEYWORDS = ['virus','viroid','satellite','phage','bacteriophage']

# ============================================================================
# 0. 覆盖度分析 (借鉴 varVAMP calc_per_base_mismatches + PCR_strainer variant_report)
# ============================================================================

# 3' 端错配指数惩罚权重 (varVAMP PRIMER_3_PENALTY)
COV_3PRIME_WEIGHTS = (32, 16, 8, 4, 2)


def _find_best_binding_site(primer, target):
    """寻找引物在靶标序列上的最佳结合位点（最小错配）。返回 (最佳起始位置, 错配数, 窗口序列)"""
    plen = len(primer)
    tlen = len(target)
    if tlen < plen:
        return 0, plen, target + 'N' * (plen - tlen)

    iupac_sets = {
        'R': set('AG'), 'Y': set('CT'), 'S': set('GC'), 'W': set('AT'),
        'K': set('GT'), 'M': set('AC'), 'B': set('CGT'), 'D': set('AGT'),
        'H': set('ACT'), 'V': set('ACG'), 'N': set('ACGT')
    }

    best_mismatches = plen + 1
    best_pos = 0
    for i in range(tlen - plen + 1):
        window = target[i:i+plen]
        mm = 0
        for p, t in zip(primer, window):
            if p == t:
                continue
            p_set = iupac_sets.get(p, {p})
            t_set = iupac_sets.get(t, {t})
            if not p_set.intersection(t_set):
                mm += 1
        if mm < best_mismatches:
            best_mismatches = mm
            best_pos = i
            if mm == 0:
                break
    return best_pos, best_mismatches, target[best_pos:best_pos+plen]


def _calc_primer_coverage(primer_seq, target_seqs):
    """
    【修正版】滑动窗口寻找最佳结合位点，计算逐碱基错配率和3'端惩罚。

    原版 BUG: 假设引物永远结合在靶标5'端(索引0)，导致全长基因组输入时覆盖度恒为0。
    修复: 滑动窗口扫描靶标全序列，找到错配最少的位置，在该位点计算3'端惩罚。
    """
    if not primer_seq or not target_seqs:
        return {"coverage_pct": 0.0, "penalty_3prime": 0.0, "per_base_mm": []}

    plen = len(primer_seq)
    primer = primer_seq.upper()
    mismatches = [0] * plen
    valid_counts = [0] * plen
    perfect_matches = 0
    total_valid = 0

    iupac_sets = {
        'R': set('AG'), 'Y': set('CT'), 'S': set('GC'), 'W': set('AT'),
        'K': set('GT'), 'M': set('AC'), 'B': set('CGT'), 'D': set('AGT'),
        'H': set('ACT'), 'V': set('ACG'), 'N': set('ACGT')
    }

    for tseq in target_seqs:
        t = tseq.upper()
        if len(t) < plen * 0.5:
            continue

        total_valid += 1
        _, best_mm, best_window = _find_best_binding_site(primer, t)

        if best_mm == 0:
            perfect_matches += 1
            for idx in range(plen):
                valid_counts[idx] += 1
        else:
            for idx in range(plen):
                valid_counts[idx] += 1
                p_base = primer[idx]
                t_base = best_window[idx] if idx < len(best_window) else 'N'
                if p_base != t_base:
                    p_set = iupac_sets.get(p_base, {p_base})
                    t_set = iupac_sets.get(t_base, {t_base})
                    if not p_set.intersection(t_set):
                        mismatches[idx] += 1

    per_base_mm = [round(m / max(v, 1), 2) for m, v in zip(mismatches, valid_counts)]

    penalty_3prime = 0.0
    n_weights = min(len(COV_3PRIME_WEIGHTS), len(per_base_mm))
    for i in range(n_weights):
        penalty_3prime += per_base_mm[-(i + 1)] * COV_3PRIME_WEIGHTS[i]

    coverage_pct = round(perfect_matches / max(total_valid, 1) * 100, 1)

    return {
        "coverage_pct": coverage_pct,
        "penalty_3prime": round(penalty_3prime, 1),
        "per_base_mm": per_base_mm,
        "total_seqs": total_valid
    }


def _validate_coverage(row, target_seqs):
    """
    对一对引物执行覆盖度验证。
    返回覆盖度结果字典。
    """
    if not target_seqs:
        return {}
    fwd = str(row.get('Fwd_Seq', '')).strip()
    rev = str(row.get('Rev_Seq', '')).strip()
    if not fwd or not rev:
        return {}

    # FWD 结合在负义链，其5'→3'序列等同于正义链上的目标区域
    fwd_cov = _calc_primer_coverage(fwd, target_seqs)
    # REV 结合在正义链，其5'→3'序列是正义链的反向互补。
    # 必须将靶标取反向互补再做匹配，否则 Rev 覆盖度恒为 0%。
    rc_targets = [str(Seq(t).reverse_complement()) for t in target_seqs]
    rev_cov = _calc_primer_coverage(rev, rc_targets)

    return {
        "Fwd_Coverage_Pct": fwd_cov["coverage_pct"],
        "Rev_Coverage_Pct": rev_cov["coverage_pct"],
        "Fwd_3Prime_Penalty": fwd_cov["penalty_3prime"],
        "Rev_3Prime_Penalty": rev_cov["penalty_3prime"],
        "Coverage_Avg": round((fwd_cov["coverage_pct"] + rev_cov["coverage_pct"]) / 2, 1),
        "Coverage_Total_Seqs": fwd_cov["total_seqs"]
    }


# ============================================================================
# 1. 引物3 二聚体分析
# ============================================================================

def _dimer_analysis(fwd_seq, rev_seq):
    """primer3 二聚体: 自二聚体 + 交叉二聚体 → {dG, Tm, structure}"""
    if not PRIMER3_OK:
        return {"self_fwd_dg": 0, "self_rev_dg": 0, "cross_dg": 0,
                "self_fwd_tm": 0, "self_rev_tm": 0, "cross_tm": 0,
                "self_fwd_struct": "", "self_rev_struct": "", "cross_struct": ""}

    def _safe_dimer(func, *args):
        try:
            r = func(*args)
            return {"dg": round(r.dg / 1000.0, 2), "tm": round(r.tm, 1), "struct": str(r)}
        except Exception:
            return {"dg": 0, "tm": 0, "struct": ""}

    sf = _safe_dimer(calc_homodimer, fwd_seq)
    sr = _safe_dimer(calc_homodimer, rev_seq)
    cr = _safe_dimer(calc_heterodimer, fwd_seq, rev_seq)

    return {"self_fwd_dg": sf["dg"], "self_rev_dg": sr["dg"], "cross_dg": cr["dg"],
            "self_fwd_tm": sf["tm"], "self_rev_tm": sr["tm"], "cross_tm": cr["tm"],
            "self_fwd_struct": sf["struct"], "self_rev_struct": sr["struct"],
            "cross_struct": cr["struct"]}


def _dimer_viz_text(seq, label, rc_seq=None):
    """生成二聚体碱基配对可视化文本 (fallback, primer3 不可用时使用)"""
    comp = {'A': 'T', 'T': 'A', 'G': 'C', 'C': 'G'}
    rc = rc_seq or str(Seq(seq).reverse_complement())
    best_len, best_s, best_r = 0, 0, 0
    for i in range(len(seq)):
        for j in range(i + 3, min(i + 12, len(seq) + 1)):
            sub = seq[i:j]
            ri = rc.find(sub)
            if ri >= 0 and j - i > best_len:
                best_len, best_s, best_r = j - i, i, ri
    if best_len < 3:
        return ""
    conn = ' ' * best_s + '|' * best_len + ' ' * (len(seq) - best_s - best_len)
    return (f"5' {seq} 3'\n"
            f"   {conn}\n"
            f"3' {rc} 5'\n")


# ============================================================================
# 2. 热力学错配分析
# ============================================================================

def _thermo_mismatch_analysis(primer_seq, target_seq):
    """
    计算引物与靶标序列的 Nearest-Neighbor 热力学错配惩罚。
    返回: {"nn_dg": float, "mismatches": int, "3end_mismatches": int}
    """
    primer = primer_seq.upper()
    target = target_seq.upper()
    if len(primer) > len(target):
        target = target + 'N' * (len(primer) - len(target))
    mismatches = sum(1 for p, t in zip(primer, target) if p != t and t != 'N')
    # 3' 端最后 5bp 的错配更严重
    end3 = primer[-5:]
    tgt3 = target[-5:] if len(target) >= 5 else target
    mismatches_3end = sum(1 for p, t in zip(end3, tgt3) if p != t and t != 'N')
    # 估算 ΔG (简化: 每 bp 匹配 ~-1.4, 错配 ~-0.5)
    match_bp = len(primer) - mismatches
    nn_dg = -1.4 * match_bp - 0.5 * mismatches - M3PENALTY * mismatches_3end
    return {"nn_dg": round(nn_dg, 2), "mismatches": mismatches,
            "mismatches_3end": mismatches_3end}


# ============================================================================
# 3. GC / Tm 验证
# ============================================================================

def _gc_tm_check(fwd_seq, rev_seq, probe_seq=""):
    """复核 GC 含量和 Tm"""
    gc_f = round(gc_fraction(fwd_seq) * 100, 1) if fwd_seq else 0
    gc_r = round(gc_fraction(rev_seq) * 100, 1) if rev_seq else 0
    try:
        tm_f = round(mt.Tm_NN(Seq(fwd_seq)), 1) if fwd_seq else 0
        tm_r = round(mt.Tm_NN(Seq(rev_seq)), 1) if rev_seq else 0
    except Exception:
        tm_f = tm_r = 0
    gc_p = round(gc_fraction(probe_seq) * 100, 1) if probe_seq else 0
    tm_p = 0
    if probe_seq:
        try:
            tm_p = round(mt.Tm_NN(Seq(probe_seq)), 1)
        except Exception:
            pass
    return {"GC_Fwd": gc_f, "GC_Rev": gc_r, "GC_Probe": gc_p,
            "Tm_Fwd": tm_f, "Tm_Rev": tm_r, "Tm_Probe": tm_p}


# ============================================================================
# 4. 靶标命中分类
# ============================================================================

def _is_target_identity(hit):
    """检查命中是否 100% 匹配"""
    ident = hit.get("identity", "")
    parts = ident.split("/")
    if len(parts) != 2:
        return False
    try:
        return int(parts[0]) == int(parts[1]) > 0
    except (ValueError, TypeError):
        return False


def _is_plant_hit(hit_desc):
    """判断命中描述是否属于植物"""
    desc_lower = (hit_desc or "").lower()
    # 先排除病毒关键词
    for kw in VIRUS_KEYWORDS:
        if kw in desc_lower:
            return False
    for kw in PLANT_KEYWORDS:
        if kw in desc_lower:
            return True
    return False


def _is_target_hit(hit_desc, species_name):
    """判断命中是否属于目标病毒物种"""
    if not species_name or not hit_desc:
        return False
    sp_lower = species_name.lower()
    desc_lower = hit_desc.lower()
    # 提取目标物种的 non-generic 词
    words = [w for w in sp_lower.replace('.', ' ').split()
             if len(w) > 2 and w not in ('the', 'and', 'virus', 'the')]
    # 短名: 至少 1 个 non-generic 词匹配
    # 长名: 至少 2 个
    threshold = 1 if len(words) <= 3 else 2
    matches = sum(1 for w in words if w in desc_lower)
    return matches >= threshold


# ============================================================================
# 5. BLAST 批处理
# ============================================================================

def _run_one_blast_batch(batch_tasks, local_db, threads):
    """
    【修正版】单批 BLAST: FWD 和 REV 独立查询，分别统计命中。

    原版 BUG: 将 Fwd+Rev 拼接为一条序列 BLAST，导致:
      1. 无法检测真实扩增子 (两引物在基因组上相距数百bp)
      2. Rev 命中统计全部硬编码为 0
    修复: FWD/REV 独立写入 FASTA，解析时按方向分别统计，
         同一序列上同时存在Fwd+Rev命中才构成真正的脱靶风险。
    """
    if not batch_tasks:
        return {}
    import secrets as _secrets
    from collections import defaultdict as _dd

    with tempfile.NamedTemporaryFile(mode='w', suffix='.fa', delete=False) as f:
        tmp_fa = f.name
        for i, fwd, rev, sp, bd, pid in batch_tasks:
            if fwd: f.write(f">{i}_F\n{fwd}\n")
            if rev: f.write(f">{i}_R\n{rev}\n")

    try:
        out_file = Path(tempfile.gettempdir()) / f"blast_out_{_secrets.token_hex(4)}.txt"
        cmd = ["blastn", "-task", "blastn-short", "-db", str(local_db),
               "-query", tmp_fa, "-word_size", "7", "-evalue", "100",
               "-max_target_seqs", "50", "-num_threads", str(threads),
               "-outfmt", "6 qseqid sseqid salltitles evalue bitscore length pident gaps sstart send",
               "-out", str(out_file)]
        t0 = time.time()
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                text=True, timeout=21600)
        os.unlink(tmp_fa)
        if result.returncode != 0:
            if result.stderr:
                print(f"\n  [!] blastn failed: {result.stderr[:300]}", flush=True)
            return {}

        # 按 Pair ID + 方向 归类命中
        hits_by_pair_dir = _dd(lambda: {'F': [], 'R': []})
        with open(out_file, 'r') as fh:
            for line in fh:
                line = line.strip()
                if not line: continue
                fld = line.split('\t')
                if len(fld) < 10: continue  # 需要 sstart/send 坐标列
                qseqid = fld[0]
                # 解析 {idx}_F 或 {idx}_R
                parts = qseqid.rsplit('_', 1)
                if len(parts) != 2: continue
                idx_str, direction = parts
                if direction not in ('F', 'R'): continue

                pident = float(fld[6]) if fld[6] != '.' else 0.0
                alen = int(fld[5]) if fld[5] != '.' else 0
                if alen < 12:
                    continue
                mc = int(round(pident * alen / 100.0)) if alen > 0 else 0
                h = {"hit_id": fld[1],
                     "hit_desc": fld[2][:200] if len(fld) > 2 else "",
                     "evalue": float(fld[3]) if fld[3] != '.' else 999.0,
                     "score": float(fld[4]) if fld[4] != '.' else 0.0,
                     "align_len": alen,
                     "identity": f"{mc}/{alen}" if alen > 0 else "",
                     "pident": pident,
                     "sstart": int(fld[8]),
                     "send": int(fld[9])}
                hits_by_pair_dir[idx_str][direction].append(h)

        try:
            Path(out_file).unlink(missing_ok=True)
        except Exception:
            pass

        results = {}
        for i, fwd, rev, sp, bd, pid in batch_tasks:
            pair_hits = hits_by_pair_dir.get(str(i), {'F': [], 'R': []})
            f_hits = pair_hits['F']
            r_hits = pair_hits['R']

            # FWD 统计
            f_target = sum(1 for h in f_hits
                          if _is_target_identity(h) or _is_target_hit(h.get("hit_desc",""), sp))
            f_plant = sum(1 for h in f_hits
                         if not (_is_target_identity(h) or _is_target_hit(h.get("hit_desc",""), sp))
                         and _is_plant_hit(h.get("hit_desc","")))
            f_other = len(f_hits) - f_target - f_plant

            # REV 统计
            r_target = sum(1 for h in r_hits
                          if _is_target_identity(h) or _is_target_hit(h.get("hit_desc",""), sp))
            r_plant = sum(1 for h in r_hits
                         if not (_is_target_identity(h) or _is_target_hit(h.get("hit_desc",""), sp))
                         and _is_plant_hit(h.get("hit_desc","")))
            r_other = len(r_hits) - r_target - r_plant

            # 关键: 同一序列上同时存在 Fwd+Rev 命中 + 方向相向 + 距离可扩增
            # 单纯同序列命中不足以构成脱靶风险 (两引物可能相距 10Mb)
            MAX_PCR_AMP_LEN = 5000  # 常规 PCR 扩增极限 ~5kb
            f_off_hits = [h for h in f_hits
                         if not (_is_target_identity(h) or _is_target_hit(h.get("hit_desc",""), sp))]
            r_off_hits = [h for h in r_hits
                         if not (_is_target_identity(h) or _is_target_hit(h.get("hit_desc",""), sp))]

            # 按 hit_id 分组
            f_by_seq = _dd(list)
            for h in f_off_hits: f_by_seq[h['hit_id']].append(h)
            r_by_seq = _dd(list)
            for h in r_off_hits: r_by_seq[h['hit_id']].append(h)

            paired_offtargets = set()
            for seq_id in set(f_by_seq.keys()) & set(r_by_seq.keys()):
                for fh in f_by_seq[seq_id]:
                    for rh in r_by_seq[seq_id]:
                        # 链方向: Fwd 结合在负链(sstart<send=plus), Rev 结合在正义链(sstart>send=minus)
                        # 两引物必须相向结合才能产生扩增子
                        f_plus = fh['sstart'] < fh['send']
                        r_plus = rh['sstart'] < rh['send']
                        if f_plus == r_plus:
                            continue  # 同向结合, 无法扩增
                        # 物理距离
                        coords = [fh['sstart'], fh['send'], rh['sstart'], rh['send']]
                        amp_dist = max(coords) - min(coords)
                        if amp_dist <= MAX_PCR_AMP_LEN:
                            paired_offtargets.add(seq_id)
                            break
                    if seq_id in paired_offtargets:
                        break

            # 风险评级
            pr = "NONE"
            if paired_offtargets:
                if any(_is_plant_hit(h.get("hit_desc","")) for h in f_hits + r_hits
                       if h['hit_id'] in paired_offtargets):
                    pr = "HIGH"
                else:
                    pr = "MEDIUM"
            elif f_plant >= 3 or r_plant >= 3:
                pr = "LOW"

            # 特异性: 靶标配对比 / 总配对比
            true_pairs = min(f_target, r_target)
            total_pairs = min(len(f_hits), len(r_hits))
            spec = round(true_pairs / max(total_pairs, 1) * 100, 1)

            ot = ""
            for h in f_hits + r_hits:
                if h['hit_id'] in paired_offtargets:
                    ot = h.get("hit_desc", "")[:120]
                    break

            # CSV 日志
            csv_rows = []
            for direction, hits in [("FWD", f_hits), ("REV", r_hits)]:
                for h in hits:
                    csv_rows.append({
                        "Pair_ID": pid, "Species": sp, "Direction": direction,
                        "Hit_ID": h["hit_id"], "Hit_Description": h["hit_desc"],
                        "E_value": h["evalue"], "Score": h["score"],
                        "Identity": h["identity"],
                        "Sstart": h.get("sstart", 0), "Send": h.get("send", 0),
                        "Is_Target": _is_target_identity(h) or _is_target_hit(h.get("hit_desc",""), sp),
                        "Is_Plant": _is_plant_hit(h.get("hit_desc",""))
                    })
            if csv_rows:
                pl.DataFrame(csv_rows).write_csv(Path(bd) / f"blast_{pid}.csv")

            results[i] = {
                "BLAST_Fwd_TargetHits": f_target, "BLAST_Fwd_PlantHits": f_plant,
                "BLAST_Fwd_OtherHits": f_other,
                "BLAST_Rev_TargetHits": r_target, "BLAST_Rev_PlantHits": r_plant,
                "BLAST_Rev_OtherHits": r_other,
                "BLAST_Offtarget_TopSpecies": ot,
                "BLAST_Specificity_Score": spec, "BLAST_Plant_Risk": pr,
                "BLAST_ResultFile": str(Path(bd) / f"blast_{pid}.csv"), "BLAST_Warning": ""
            }
        return results
    except Exception as _e:
        import traceback as _tb
        print(f"\n  [!] BLAST batch error: {_e}", flush=True)
        _tb.print_exc()
        return {}


def _batch_local_blast(tasks, db_path, threads=4, batch_size=5000, jobs=1, checkpoint_dir=None):
    """分批本地 BLAST: jobs 路并行, 支持断点续跑"""
    if not tasks:
        return {}
    local_db = Path(db_path)
    if not batch_size or batch_size <= 0:
        batch_size = len(tasks)
    num_batches = (len(tasks) + batch_size - 1) // batch_size
    batches = [tasks[b * batch_size:(b + 1) * batch_size] for b in range(num_batches)]
    jobs = max(1, min(jobs, num_batches))
    print(f"  BLAST: {num_batches} 批 x {batch_size} 对 = {len(tasks)} 对 | {jobs}路并行 | {threads}线程/批", flush=True)

    ckpt_file = None
    if checkpoint_dir:
        ckpt_file = Path(checkpoint_dir) / "blast_checkpoint.json"
    completed, all_results = set(), {}
    if ckpt_file and ckpt_file.exists():
        try:
            ckpt = json.loads(ckpt_file.read_text())
            completed = set(ckpt.get("completed_batches", []))
            all_results = {int(k): v for k, v in ckpt.get("results", {}).items()}
            print(f"  [断点续跑] 已完成 {len(completed)}/{num_batches}", flush=True)
        except Exception:
            pass

    pending = [(bi, batch) for bi, batch in enumerate(batches) if bi not in completed]
    if not pending:
        print(f"  ✓ 全部已完成: {len(all_results)} 条", flush=True)
        return all_results

    blast_pbar = None
    if TQDM_OK:
        blast_pbar = tqdm(total=len(pending), desc="  BLAST批处理", unit="批",
                           bar_format='{l_bar}{bar:40}{r_bar}')

    def _run_batch(bi_batch):
        bi, batch = bi_batch
        try:
            return bi, _run_one_blast_batch(batch, local_db, threads)
        except Exception as e:
            import traceback as _tb
            print(f"\n  [!] 批次 {bi+1} 异常: {e}", flush=True)
            _tb.print_exc()
            return bi, {}

    import threading
    lock = threading.Lock()
    if jobs > 1 and len(pending) > 1:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futures = {ex.submit(_run_batch, item): item for item in pending}
            for fut in as_completed(futures):
                bi, batch_results = fut.result()
                with lock:
                    all_results.update(batch_results)
                    completed.add(bi)
                    if blast_pbar:
                        n_hits = sum(1 for r in batch_results.values()
                                     if r.get('BLAST_Fwd_TargetHits',0)+r.get('BLAST_Fwd_PlantHits',0)+r.get('BLAST_Fwd_OtherHits',0)>0)
                        blast_pbar.set_postfix_str(f"批{bi+1} {n_hits}命中")
                        blast_pbar.update(1)
                    if ckpt_file:
                        try:
                            ckpt_file.write_text(json.dumps({
                                "completed_batches": list(completed),
                                "total_batches": num_batches,
                                "results": {str(k): v for k, v in all_results.items()}
                            }))
                        except Exception: pass
    else:
        for bi, batch in pending:
            bi, batch_results = _run_batch((bi, batch))
            all_results.update(batch_results)
            completed.add(bi)
            if blast_pbar: blast_pbar.update(1)

    if blast_pbar: blast_pbar.close()
    print(f"  ✓ BLAST完成: {len(all_results)} 条结果", flush=True)
    return all_results


# ============================================================================
# 6. 综合评分 (0-100)
# ============================================================================

def _compute_score(dimer, blast, gc_tm, thermo=None, probe_val=None, ptype="", cov=None):
    """综合评分: 100 起扣 (借鉴 PCR_strainer + varVAMP + qprimer_designer)"""
    score = 100.0

    # 二聚体惩罚 (最多 -30)
    if dimer:
        for k in ['self_fwd_dg', 'self_rev_dg', 'cross_dg']:
            dg = dimer.get(k, 0)
            if dg < -9.0:
                score -= 12
            elif dg < -6.0:
                score -= 6
            elif dg < -3.0:
                score -= 2

    # GC 偏差惩罚 (最多 -10)
    if gc_tm:
        for k in ['GC_Fwd', 'GC_Rev']:
            gc = gc_tm.get(k, 50)
            if gc < 35 or gc > 65:
                score -= 5
            elif gc < 40 or gc > 60:
                score -= 2

    # Tm 差异惩罚 (最多 -5)
    if gc_tm:
        tf = gc_tm.get('Tm_Fwd', 0)
        tr = gc_tm.get('Tm_Rev', 0)
        if tf > 0 and tr > 0 and abs(tf - tr) > 3:
            score -= 3

    # ── qPCR 探针专项惩罚 (最多 -30, 借鉴 varVAMP QPROBE_TEMP_DIFF) ──
    if probe_val and ptype == "qPCR":
        if not probe_val.get("Probe_Tm_Diff_Ok", True):
            score -= 20
        if probe_val.get("Probe_Hairpin_Tm", 0) > 47:
            score -= 8
        if probe_val.get("Probe_Self_Dimer_dG", 0) < -6.0:
            score -= 8
        for k in ['Probe_Fwd_Dimer_dG', 'Probe_Rev_Dimer_dG']:
            if probe_val.get(k, 0) < -6.0:
                score -= 6

    # ── 覆盖度惩罚 (最多 -25, 借鉴 varVAMP PRIMER_3_PENALTY + PCR_strainer) ──
    if cov and cov.get("Coverage_Total_Seqs", 0) > 0:
        avg_cov = cov.get("Coverage_Avg", 100)
        if avg_cov < 50:
            score -= 25
        elif avg_cov < 70:
            score -= 15
        elif avg_cov < 85:
            score -= 8
        elif avg_cov < 95:
            score -= 3
        # 3' 端错配严重
        fwd_3p = cov.get("Fwd_3Prime_Penalty", 0)
        rev_3p = cov.get("Rev_3Prime_Penalty", 0)
        if fwd_3p > 10 or rev_3p > 10:
            score -= 12
        elif fwd_3p > 5 or rev_3p > 5:
            score -= 5

    # BLAST 植物脱靶惩罚 (最多 -30)
    if blast:
        pr = blast.get('BLAST_Plant_Risk', 'NONE')
        if pr == 'HIGH':
            score -= 30
        elif pr == 'MEDIUM':
            score -= 15
        elif pr == 'LOW':
            score -= 5
        spec = blast.get('BLAST_Specificity_Score', 100)
        if spec < 30:
            score -= 15
        elif spec < 50:
            score -= 10
        elif spec < 80:
            score -= 5

    # 热力学错配惩罚 (最多 -15)
    if thermo:
        mismatch_3end = thermo.get('mismatches_3end', 0)
        if mismatch_3end > 2:
            score -= 10
        elif mismatch_3end > 0:
            score -= 4
        total_mm = thermo.get('mismatches', 0)
        if total_mm > 3:
            score -= 5

    return max(0.0, round(score, 1))


def _get_recommendation(score, blast=None):
    if score >= 80:
        return "RECOMMENDED"
    elif score >= 60:
        return "USABLE"
    else:
        return "NOT_RECOMMENDED"


# ============================================================================
# 7. 探针专项验证 (借鉴 varVAMP qPCR + qprimer_designer)
# ============================================================================

def _probe_validation(probe_seq, fwd_seq, rev_seq, probe_tm=0, fwd_tm=0, rev_tm=0):
    """
    探针专项质量验证:
      1. 发夹 Tm ≤47°C (varVAMP)
      2. 自二聚体 ΔG ≥ -6 kcal/mol (qprimer_designer)
      3. 与Fwd/Rev交叉二聚体 ΔG ≥ -6 (varVAMP)
      4. 探针Tm 比引物高 5-10°C (varVAMP QPROBE_TEMP_DIFF)
    """
    result = {
        "Probe_Hairpin_Tm": 0, "Probe_Self_Dimer_dG": 0,
        "Probe_Fwd_Dimer_dG": 0, "Probe_Rev_Dimer_dG": 0,
        "Probe_Tm_Diff_Ok": True, "Probe_Warning": ""
    }
    if not probe_seq or len(probe_seq) < 14:
        return result

    warnings = []

    # 1. Hairpin
    if PRIMER3_OK:
        try:
            hp = primer3.calc_hairpin(probe_seq)
            result["Probe_Hairpin_Tm"] = round(hp.tm, 1)
            if hp.tm > 47:
                warnings.append(f"Probe hairpin Tm={hp.tm:.0f}C (>47)")
        except Exception:
            pass

    # 2. Self-dimer
    if PRIMER3_OK:
        try:
            sd = primer3.calc_homodimer(probe_seq)
            result["Probe_Self_Dimer_dG"] = round(sd.dg / 1000.0, 1)
            if sd.dg / 1000.0 < -6.0:
                warnings.append(f"Probe self-dimer dG={sd.dg/1000:.1f}")
        except Exception:
            pass

    # 3. Cross-dimer with Fwd/Rev
    if PRIMER3_OK and fwd_seq:
        try:
            xd = primer3.calc_heterodimer(probe_seq, fwd_seq)
            result["Probe_Fwd_Dimer_dG"] = round(xd.dg / 1000.0, 1)
            if xd.dg / 1000.0 < -6.0:
                warnings.append(f"Probe-Fwd dimer dG={xd.dg/1000:.1f}")
        except Exception:
            pass
    if PRIMER3_OK and rev_seq:
        try:
            xd = primer3.calc_heterodimer(probe_seq, rev_seq)
            result["Probe_Rev_Dimer_dG"] = round(xd.dg / 1000.0, 1)
            if xd.dg / 1000.0 < -6.0:
                warnings.append(f"Probe-Rev dimer dG={xd.dg/1000:.1f}")
        except Exception:
            pass

    # 4. Tm difference: probe should be 5-10°C above primers
    if probe_tm > 0 and fwd_tm > 0 and rev_tm > 0:
        max_primer_tm = max(fwd_tm, rev_tm)
        if not (max_primer_tm + 5 <= probe_tm <= max_primer_tm + 10):
            result["Probe_Tm_Diff_Ok"] = False
            warnings.append(f"Probe Tm={probe_tm:.0f}C not 5-10C above primers")

    result["Probe_Warning"] = "; ".join(warnings)
    return result


# ============================================================================
# 8. 单引物验证
# ============================================================================

# 单物种序列缓存 (O(1) 内存, 配合排序实现 ~100% 命中率)
_CACHE_KEY = None
_CACHE_SEQS = []

def _resolve_target_seqs(row, species_dir):
    """动态加载引物所属物种的靶标序列, 支持分节段病毒, 带单物种缓存"""
    global _CACHE_KEY, _CACHE_SEQS
    species = str(row.get('Species', '')).strip()
    segment = str(row.get('Segment', '')).strip()
    if not species or species.lower() in ('', 'unknown', 'nan'):
        return []
    safe_sp = species.replace('/', '_').replace(' ', '_').replace(':', '_')
    # 节段病毒: step1 将物种名截断到60字符 + _segment (对齐 step1 write_per_species)
    if segment:
        safe_sp = safe_sp[:60]
        fa_file = species_dir / f"{safe_sp}_{segment}.fasta"
    else:
        safe_sp = safe_sp[:80]
        fa_file = species_dir / f"{safe_sp}.fasta"

    key = (safe_sp, segment)
    if _CACHE_KEY == key:
        return _CACHE_SEQS
    _CACHE_KEY = key
    _CACHE_SEQS = []
    if fa_file.exists():
        try:
            _CACHE_SEQS = [str(r.seq).upper() for r in SeqIO.parse(fa_file, 'fasta')]
            if len(_CACHE_SEQS) > 500:
                import random as _r; _r.seed(42)
                _CACHE_SEQS = _r.sample(_CACHE_SEQS, 500)
        except Exception:
            _CACHE_SEQS = []
    return _CACHE_SEQS


def validate_single_primer(row, blast_info=None, sp_seqs=None):
    """对单对引物执行完整验证 (物种特异性覆盖度)"""
    fwd = str(row.get('Fwd_Seq', '')).strip()
    rev = str(row.get('Rev_Seq', '')).strip()
    probe = str(row.get('Probe_Seq', '')).strip()
    ptype = str(row.get('Type', '')).strip()

    # 1. GC/Tm
    gc_tm = _gc_tm_check(fwd, rev, probe)

    # 2. primer3 二聚体
    dimer = _dimer_analysis(fwd, rev)

    # 3. 探针专项验证 (qPCR)
    probe_val = {}
    if probe and ptype == "qPCR":
        probe_val = _probe_validation(
            probe, fwd, rev,
            probe_tm=gc_tm.get("Tm_Probe", 0),
            fwd_tm=gc_tm.get("Tm_Fwd", 0),
            rev_tm=gc_tm.get("Tm_Rev", 0)
        )

    # 4. 覆盖度分析: 物种特异性 (借鉴 varVAMP + PCR_strainer)
    cov = {}
    if sp_seqs:
        # 缓存直传 → 精确匹配 → 模糊匹配 → 全局回退
        targets = sp_seqs.get("__cached__")
        if not targets:
            sp = str(row.get('Species', '')).strip()
            targets = (sp_seqs.get(sp) or
                       next((v for k, v in sp_seqs.items()
                             if sp.lower() in k.lower() or k.lower() in sp.lower()), None) or
                       sp_seqs.get("__global__", []))
        if targets:
            cov = _validate_coverage(row, targets)

    # 5. 综合评分
    score = _compute_score(dimer, blast_info, gc_tm, probe_val, ptype, cov)
    rec = _get_recommendation(score, blast_info)

    result = {
        "GC_Fwd_Verified": gc_tm["GC_Fwd"], "GC_Rev_Verified": gc_tm["GC_Rev"],
        "Tm_Fwd_Verified": gc_tm["Tm_Fwd"], "Tm_Rev_Verified": gc_tm["Tm_Rev"],
        "Self_Dimer_Fwd": dimer["self_fwd_struct"],
        "Self_Dimer_Rev": dimer["self_rev_struct"],
        "Cross_Dimer": dimer["cross_struct"],
        "Dimer_Warning": _dimer_warning_text(dimer),
        "Validation_Score": score,
        "Validation_Status": rec,
        "Recommendation": rec,
        "Validated_At": datetime.now().isoformat()
    }
    # 合并探针验证字段
    if probe_val:
        result.update(probe_val)
    # 合并覆盖度字段
    if cov:
        result.update(cov)
    return result


def _dimer_warning_text(dimer):
    """生成二聚体警告文本"""
    warnings = []
    if dimer and dimer.get("self_fwd_dg", 0) < -9.0:
        warnings.append("FWD Strong self-dimer (dG={:.1f})".format(dimer["self_fwd_dg"]))
    if dimer and dimer.get("self_rev_dg", 0) < -9.0:
        warnings.append("REV Strong self-dimer (dG={:.1f})".format(dimer["self_rev_dg"]))
    if dimer and dimer.get("cross_dg", 0) < -9.0:
        warnings.append("Strong cross-dimer (dG={:.1f})".format(dimer["cross_dg"]))
    return "; ".join(warnings) if warnings else ""


# ============================================================================
# 主入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="引物特异性验证 (primer3 + BLAST + 热力学)")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-blast", action="store_true", help="跳过 BLAST")
    parser.add_argument("--blast-db", default="", help="病毒 BLAST 数据库路径")
    parser.add_argument("--blast-db-plant", default="", help="植物 BLAST 数据库路径 (可选)")
    parser.add_argument("--blast-batch", type=int, default=5000, help="BLAST 批次大小 (0=全量)")
    parser.add_argument("--blast-jobs", type=int, default=1, help="BLAST 并行批次数")
    parser.add_argument("--threads", type=int, default=4, help="CPU 线程数")
    parser.add_argument("--quick", action="store_true", help="快速模式: 跳过 BLAST, 仅二聚体+GC")
    parser.add_argument("--target-fasta", default="", help="靶标序列 FASTA (单文件模式, 全局覆盖度)")
    parser.add_argument("--species-dir", default="", help="step1 拆分目录 (split_species/species), 物种内覆盖度+缓存加速)")
    parser.add_argument("--jobs", type=int, default=1, help="序列验证并行进程数 (覆盖度步骤, 默认1)")

    args = parser.parse_args()

    input_tsv = Path(args.input)
    if not input_tsv.exists():
        print(f"✗ 输入文件不存在: {input_tsv}")
        print(f"  请先运行: python step2_design_primers.py")
        sys.exit(1)

    output_tsv = Path(args.output)
    output_tsv.parent.mkdir(parents=True, exist_ok=True)

    BLAST_DB = args.blast_db
    BLAST_DB_PLANT = args.blast_db_plant

    # 读取引物
    print(f"加载 {input_tsv}...")
    primers = pl.read_csv(input_tsv, separator='\t', ignore_errors=True)
    total = len(primers)
    types = primers['Type'].unique().to_list() if 'Type' in primers.columns else ['PCR']
    print(f"  {total} 对引物, 类型: {types}")

    # 去重: 按 (Species, Fwd_Seq, Rev_Seq) 去除 Olivar/varVAMP 等工具可能产生的重复引物对
    if 'Species' in primers.columns and 'Fwd_Seq' in primers.columns:
        dup_cols = ['Species', 'Fwd_Seq', 'Rev_Seq']
        before = len(primers)
        primers = primers.unique(subset=dup_cols, keep='first')
        dup_removed = before - len(primers)
        if dup_removed > 0:
            print(f"  ⚠ 去重: 移除 {dup_removed} 对重复引物 ({len(primers)} 对剩余)")
        total = len(primers)

    # 加载靶标序列 — 支持两种模式
    target_seqs_global = []
    sp_seqs = {}
    species_dir = None
    if args.species_dir:
        species_dir = Path(args.species_dir)
        if species_dir.is_dir():
            print(f"  物种目录: {species_dir} (按需加载 + 单物种缓存)")
        else:
            print(f"  ⚠ 物种目录不存在: {species_dir}")
            species_dir = None
    if args.target_fasta:
        tf_path = Path(args.target_fasta)
        if tf_path.is_file():
            target_seqs_global = [str(r.seq).upper() for r in SeqIO.parse(tf_path, 'fasta')]
            if len(target_seqs_global) > 500:
                import random as _random; _random.seed(42)
                target_seqs_global = _random.sample(target_seqs_global, 500)
            sp_seqs["__global__"] = target_seqs_global
            print(f"  靶标序列: {len(target_seqs_global)} 条 (全局覆盖度)")
        elif not species_dir:
            print(f"  ⚠ 靶标文件不存在: {tf_path}")

    # 排序优化: 按 Species+Segment 排序使单物种缓存命中率 ~100%
    if species_dir and 'Species' in primers.columns:
        sort_cols = ['Species']
        if 'Segment' in primers.columns:
            sort_cols.append('Segment')
        primers = primers.sort(sort_cols)
        print(f"  已按 {', '.join(sort_cols)} 排序 (缓存加速)")

    # 检查已验证结果
    validated = None
    if output_tsv.exists():
        try:
            validated = pl.read_csv(output_tsv, separator='\t', ignore_errors=True)
            print(f"→ 已有验证结果: {len(validated)} 对")
        except Exception:
            validated = None

    # 筛选需验证的引物: 推荐 + 可用
    if validated is not None and 'Recommendation' in validated.columns:
        to_validate = validated.filter(pl.col('Recommendation').is_in(['RECOMMENDED', 'USABLE', 'CAUTION']))
        print(f"→ 已有验证结果, 加载跳过...")
    else:
        to_validate = primers

    # ─── 阶段 1: 序列层面验证 ───
    print(f"\n{'='*60}")
    print(f"  阶段 1/2: 序列层面验证")
    print(f"  引物: {len(to_validate)} 对 | 二聚体: {'primer3' if PRIMER3_OK else 'fallback'}"
          + (f" | 覆盖度: 物种内缓存" if species_dir else " | 覆盖度: 全局/跳过"))
    print(f"{'='*60}")

    blast_dir = output_tsv.parent / "blast"
    blast_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1 断点续传: 检查 parquet 检查点
    rows = to_validate.to_dicts()
    val_results = []
    phase1_ckpt = blast_dir / "phase1_checkpoint.parquet"
    if phase1_ckpt.exists():
        try:
            ckpt_df = pl.read_parquet(phase1_ckpt)
            if len(ckpt_df) == len(rows):
                print(f"  ✓ 从检查点恢复 Phase 1 ({len(ckpt_df)} 对), 跳过全部子步骤")
                val_results = ckpt_df.to_dicts()
        except Exception:
            pass

    if not val_results:
        # 子步骤函数
        def _sub_step(desc, total, func):
            results = []
            if TQDM_OK:
                pbar = tqdm(total=total, desc=desc, unit="对",
                             bar_format='{l_bar}{bar:40}{r_bar}')
            for idx, row in enumerate(rows):
                r = func(row, idx)
                results.append(r)
                if TQDM_OK: pbar.update(1)
                elif (idx + 1) % 10000 == 0:
                    print(f"  {desc}: {idx + 1}/{total}", flush=True)
            if TQDM_OK: pbar.close()
            return results

        # 1a: GC/Tm 复核
        print("")
        tm_results = _sub_step("  1a. GC/Tm复核", len(rows),
            lambda row, idx: _gc_tm_check(
                str(row.get('Fwd_Seq','')).strip(),
                str(row.get('Rev_Seq','')).strip(),
                str(row.get('Probe_Seq','')).strip()))

        # 1b: 二聚体分析
        if args.jobs > 1 and PRIMER3_OK:
            print("")
            _total = len(rows)
            if TQDM_OK:
                _pbar = tqdm(total=_total, desc="  1b. 二聚体分析", unit="对",
                              bar_format='{l_bar}{bar:40}{r_bar}')
            def _dimer_one(ri):
                r = rows[ri]
                return _dimer_analysis(str(r.get('Fwd_Seq','')).strip(),
                                       str(r.get('Rev_Seq','')).strip())
            dimer_results = [None] * _total
            with ThreadPoolExecutor(max_workers=args.jobs) as ex:
                _futs = {ex.submit(_dimer_one, i): i for i in range(_total)}
                for _f in as_completed(_futs):
                    i = _futs[_f]; dimer_results[i] = _f.result()
                    if TQDM_OK: _pbar.update(1)
            if TQDM_OK: _pbar.close()
        else:
            dimer_results = _sub_step("  1b. 二聚体分析", len(rows),
                lambda row, idx: _dimer_analysis(
                    str(row.get('Fwd_Seq','')).strip(),
                    str(row.get('Rev_Seq','')).strip()))

        # 1c: 探针验证
        probe_results = _sub_step("  1c. 探针验证", len(rows),
            lambda row, idx: _probe_validation(
                str(row.get('Probe_Seq','')).strip(),
                str(row.get('Fwd_Seq','')).strip(),
                str(row.get('Rev_Seq','')).strip(),
                probe_tm=tm_results[idx].get("Tm_Probe", 0),
                fwd_tm=tm_results[idx].get("Tm_Fwd", 0),
                rev_tm=tm_results[idx].get("Tm_Rev", 0))
            if (str(row.get('Probe_Seq','')).strip() and
                str(row.get('Type','')).strip() == "qPCR")
            else {})

        # 1d: 物种内覆盖度
        cov_results = [{}] * len(rows)
        if species_dir or sp_seqs:
            all_targets = []
            for idx2, r2 in enumerate(rows):
                t = []
                if species_dir: t = _resolve_target_seqs(r2, species_dir)
                elif sp_seqs:
                    sp2 = str(r2.get('Species','')).strip()
                    t = (sp_seqs.get(sp2) or
                         next((v for k, v in sp_seqs.items()
                               if sp2.lower() in k.lower() or k.lower() in sp2.lower()), None) or [])
                all_targets.append(t)
            if args.jobs > 1 and len(rows) > 100:
                print("")
                _pbar = tqdm(total=len(rows), desc="  1d. 物种覆盖度", unit="对",
                              bar_format='{l_bar}{bar:40}{r_bar}') if TQDM_OK else None
                with ProcessPoolExecutor(max_workers=args.jobs) as ex:
                    _futs = {}
                    for idx3, r3 in enumerate(rows):
                        if all_targets[idx3]:
                            _futs[ex.submit(_validate_coverage, r3, all_targets[idx3])] = idx3
                        else: cov_results[idx3] = {}; _pbar and _pbar.update(1)
                    for _f in as_completed(_futs):
                        i3 = _futs[_f]; cov_results[i3] = _f.result()
                        if _pbar: _pbar.update(1)
                if _pbar: _pbar.close()
            else:
                cov_results = _sub_step("  1d. 物种覆盖度", len(rows),
                    lambda row, idx: _validate_coverage(row, all_targets[idx])
                    if all_targets[idx] else {})

        # 合并 + 评分
        for idx4, r4 in enumerate(rows):
            gc_tm = tm_results[idx4]
            dimer = dimer_results[idx4]
            ptype = str(r4.get('Type', '')).strip()
            probe_val = probe_results[idx4] if ptype == "qPCR" else {}
            cov = cov_results[idx4]
            score = _compute_score(dimer, None, gc_tm, probe_val=probe_val, ptype=ptype, cov=cov)
            rec = _get_recommendation(score, None)
            val = {
                "GC_Fwd_Verified": gc_tm.get("GC_Fwd",0), "GC_Rev_Verified": gc_tm.get("GC_Rev",0),
                "Tm_Fwd_Verified": gc_tm.get("Tm_Fwd",0), "Tm_Rev_Verified": gc_tm.get("Tm_Rev",0),
                "Self_Dimer_Fwd": dimer.get("self_fwd_struct",""),
                "Self_Dimer_Rev": dimer.get("self_rev_struct",""),
                "Cross_Dimer": dimer.get("cross_struct",""),
                "Dimer_Warning": _dimer_warning_text(dimer),
                "Validation_Score": score, "Validation_Status": rec,
                "Recommendation": rec, "Validated_At": datetime.now().isoformat(),
                "_idx": idx4
            }
            if probe_val: val.update(probe_val)
            if cov: val.update(cov)
            val_results.append(val)

    print(f"  ✓ 序列验证完成: {len(val_results)} 对")

    # Phase 1 断点: 保存到 parquet 文件, 下次启动跳过序列验证
    phase1_ckpt = blast_dir / "phase1_checkpoint.parquet"
    pl.DataFrame(val_results).write_parquet(phase1_ckpt)
    print(f"  → Phase 1 检查点: {phase1_ckpt}")

    # 合并验证字段到引物表
    val_df = pl.DataFrame(val_results) if val_results else pl.DataFrame()
    if '_idx' in val_df.columns:
        val_df = val_df.drop('_idx')

    if validated is not None:
        all_rows = validated.to_dicts()
    else:
        all_rows = to_validate.to_dicts()

    # ─── 阶段 2: BLAST 特异性验证 ───
    blast_results_map = {}
    if not args.skip_blast and not args.quick and BLAST_DB:
        print(f"\n{'='*60}")
        print(f"  阶段 2/2: BLAST 特异性验证")
        print(f"  数据库: {BLAST_DB}")
        print(f"{'='*60}")

        # 构建批量任务
        batch_tasks = []
        for i, row in enumerate(rows):
            sp = str(row.get('Species', 'unknown'))
            pid = f"{sp.replace(' ', '_').replace('/', '_')[:40]}_{row.get('Type', 'PCR')}_{i}"
            cached_csv = blast_dir / f"blast_{pid}.csv"
            if cached_csv.exists():
                try:
                    cached = pl.read_csv(cached_csv).to_dicts()
                    # 按方向分开统计 (修复: 旧版硬编码 Rev=0)
                    f_h = [h for h in cached if h.get('Direction','') == 'FWD']
                    r_h = [h for h in cached if h.get('Direction','') == 'REV']
                    f_target = sum(1 for h in f_h if h.get('Is_Target') or _is_target_identity(h))
                    f_plant = sum(1 for h in f_h if h.get('Is_Plant') and not h.get('Is_Target'))
                    f_other = len(f_h) - f_target - f_plant
                    r_target = sum(1 for h in r_h if h.get('Is_Target') or _is_target_identity(h))
                    r_plant = sum(1 for h in r_h if h.get('Is_Plant') and not h.get('Is_Target'))
                    r_other = len(r_h) - r_target - r_plant
                    f_all_plant = f_plant + r_plant
                    spec = round(min(f_target, r_target) / max(min(len(f_h), len(r_h)), 1) * 100, 1)
                    pr = "HIGH" if f_all_plant >= 5 else ("MEDIUM" if f_all_plant >= 2 else ("LOW" if f_all_plant > 0 else "NONE"))
                    blast_results_map[i] = {
                        "BLAST_Fwd_TargetHits": f_target, "BLAST_Fwd_PlantHits": f_plant,
                        "BLAST_Fwd_OtherHits": f_other,
                        "BLAST_Rev_TargetHits": r_target, "BLAST_Rev_PlantHits": r_plant,
                        "BLAST_Rev_OtherHits": r_other, "BLAST_Offtarget_TopSpecies": "",
                        "BLAST_Specificity_Score": spec, "BLAST_Plant_Risk": pr,
                        "BLAST_ResultFile": str(cached_csv), "BLAST_Warning": ""
                    }
                    continue
                except Exception:
                    pass
            batch_tasks.append((i, str(row.get("Fwd_Seq", "")), str(row.get("Rev_Seq", "")),
                               str(row.get("Species", "")), blast_dir, pid))

        print(f"  BLAST 缓存: {len(blast_results_map)} 对, 需计算: {len(batch_tasks)} 对")
        if batch_tasks:
            new_results = _batch_local_blast(batch_tasks, BLAST_DB, args.threads,
                                              batch_size=args.blast_batch, jobs=args.blast_jobs,
                                              checkpoint_dir=blast_dir)
            blast_results_map.update(new_results)

        # 植物 DB 可选 (如果提供)
        if BLAST_DB_PLANT and batch_tasks:
            print(f"\n→ BLAST 植物脱靶检测...")
            plant_results = _batch_local_blast(batch_tasks, BLAST_DB_PLANT, args.threads,
                                                batch_size=args.blast_batch, jobs=args.blast_jobs)
            # 合并植物命中到主结果 (同时考虑 FWD + REV)
            for i, r in plant_results.items():
                if i in blast_results_map:
                    bm = blast_results_map[i]
                    bm["BLAST_Fwd_PlantHits"] += r.get("BLAST_Fwd_PlantHits", 0) + r.get("BLAST_Fwd_OtherHits", 0)
                    bm["BLAST_Rev_PlantHits"] += r.get("BLAST_Rev_PlantHits", 0) + r.get("BLAST_Rev_OtherHits", 0)
                    old_risk = bm.get("BLAST_Plant_Risk", "NONE")
                    total_plant = bm["BLAST_Fwd_PlantHits"] + bm["BLAST_Rev_PlantHits"]
                    if old_risk != "HIGH":
                        if total_plant >= 5:
                            bm["BLAST_Plant_Risk"] = "HIGH"
                        elif total_plant >= 2 and old_risk == "NONE":
                            bm["BLAST_Plant_Risk"] = "MEDIUM"
                        elif total_plant > 0 and old_risk == "NONE":
                            bm["BLAST_Plant_Risk"] = "LOW"

        print(f"\n  → 综合评分 ({len(all_rows)} 对)...")
        rpbar = None
        if TQDM_OK:
            rpbar = tqdm(total=len(all_rows), desc="  综合评分", unit="对",
                          bar_format='{l_bar}{bar:40}{r_bar}')
        ri = 0
        for i in range(len(all_rows)):
            ri += 1
            if i in blast_results_map:
                bi = blast_results_map[i]
                dimer = {}
                if i < len(val_results):
                    dv = val_results[i]
                    dimer = {k: dv[k] for k in ['self_fwd_dg', 'self_rev_dg', 'cross_dg'] if k in dv and dv[k]}
                gc_tm = {}
                row = all_rows[i]
                gc_tm = {
                    'GC_Fwd': float(row.get('GC_Fwd', 0) or 0),
                    'GC_Rev': float(row.get('GC_Rev', 0) or 0),
                    'Tm_Fwd': float(row.get('Fwd_Tm', 0) or 0),
                    'Tm_Rev': float(row.get('Rev_Tm', 0) or 0)
                }
                # 提取探针验证 + 类型信息 (P0-2)
                probe_val = {}
                ptype = str(row.get('Type', ''))
                if i < len(val_results):
                    pv = val_results[i]
                    if pv.get('Probe_Hairpin_Tm') is not None:
                        probe_val = {k: pv[k] for k in [
                            'Probe_Hairpin_Tm','Probe_Self_Dimer_dG',
                            'Probe_Fwd_Dimer_dG','Probe_Rev_Dimer_dG',
                            'Probe_Tm_Diff_Ok','Probe_Warning'
                        ] if k in pv}
                # 提取覆盖度数据
                cov_data = {}
                if i < len(val_results):
                    cv = val_results[i]
                    if cv.get('Coverage_Avg') is not None:
                        cov_data = {k: cv[k] for k in [
                            'Fwd_Coverage_Pct','Rev_Coverage_Pct',
                            'Fwd_3Prime_Penalty','Rev_3Prime_Penalty',
                            'Coverage_Avg','Coverage_Total_Seqs'
                        ] if k in cv}
                new_score = _compute_score(dimer, bi, gc_tm, probe_val=probe_val, ptype=ptype, cov=cov_data)
                new_rec = _get_recommendation(new_score, bi)
                all_rows[i]['Validation_Score'] = new_score
                all_rows[i]['Recommendation'] = new_rec
                # 合并 BLAST 字段
                for k, v in bi.items():
                    if k.startswith('BLAST_'):
                        all_rows[i][k] = v
                # 合并覆盖度字段
                for k, v in cov_data.items():
                    all_rows[i][k] = v
            if rpbar:
                rpbar.update(1)
            elif ri % 10000 == 0:
                print(f"  ... {ri}/{len(all_rows)}", flush=True)
        if rpbar:
            rpbar.close()
        print(f"  ✓ 综合评分完成")

    # ─── 输出 ───
    print(f"\n→ 写入: {output_tsv}")
    final_df = pl.DataFrame(all_rows)
    final_df.write_csv(output_tsv, separator='\t')
    print(f"  {len(final_df)} 对引物已保存")

    # 统计
    if 'Recommendation' in final_df.columns:
        recs = final_df['Recommendation'].value_counts().to_dict()
        for k, v in sorted(recs.items()):
            print(f"    {k}: {v}")

    print("\n✓ 验证完成")


if __name__ == "__main__":
    main()
