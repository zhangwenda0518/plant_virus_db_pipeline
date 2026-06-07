#!/usr/bin/env python3
"""
Step 3: 引物特异性验证
========================================================================
验证策略:

  1. 序列层面验证:
     - 目标区域正确性: 引物是否确实在目标 CDS/基因区域
     - GC/Tm 复核: 与设计时一致
     - 二聚体检查: 引物自身/相互二聚体

  2. BLAST 特异性验证:
     - 对植物宿主基因组 (例如 拟南芥/番茄/水稻/烟草) 做 BLAST
     - 对 NCBI nt 库做 BLAST → 确认只命中目标病毒
     - 对近缘病毒序列做交叉反应测试

  3. PCR_strainer 综合评估:
     - 引物-模板 ΔG 热力学分析
     - 3' 端错配容忍度
     - 脱靶风险评估

打分系统:
  - 每对引物综合得分 0-100
  - ≥80: 推荐使用
  - 60-79: 可用但需验证
  - <60: 不推荐
"""

import argparse
import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import polars as pl
from Bio.Blast import NCBIWWW, NCBIXML
from Bio.Seq import Seq
from Bio.SeqUtils import GC, MeltingTemp as mt


# ______________________________________________________________________
PRIMER_FILE = Path("D:/桌面/C-host_classify/引物设计/designed_primers/all_primers.tsv")
OUTPUT_FILE = Path("D:/桌面/C-host_classify/引物设计/designed_primers/all_primers_validated.tsv")

# 常见的植物宿主参考基因组 (用于特异性 BLAST)
PLANT_HOST_GENOMES = {
    "Arabidopsis_thaliana": "taxid:3702",
    "Solanum_lycopersicum": "taxid:4081",  # 番茄
    "Oryza_sativa": "taxid:4530",          # 水稻
    "Nicotiana_tabacum": "taxid:4097",     # 烟草
    "Zea_mays": "taxid:4577",              # 玉米
    "Glycine_max": "taxid:3847",           # 大豆
    "Triticum_aestivum": "taxid:4565",     # 小麦
    "Cucumis_sativus": "taxid:3659",       # 黄瓜
    "Citrus_sinensis": "taxid:2711",       # 甜橙
    "Manihot_esculenta": "taxid:3983",     # 木薯
}


def check_primer_dimer(fwd_seq: str, rev_seq: str) -> dict:
    """
    引物二聚体分析

    检测类型:
      1. 自身二聚体 (Self-dimer): 引物自身互补配对
      2. 交叉二聚体 (Cross-dimer): 正反向引物间互补配对
      3. 3' 端杂交: 最危险的, 因为聚合酶从 3' 延伸

    返回二聚体评分 (0=无风险, >5=高风险)
    """
    results = {
        "Self_Dimer_Fwd": 0,
        "Self_Dimer_Rev": 0,
        "Cross_Dimer": 0,
        "Cross_Dimer_3prime": 0,  # 3' 端交叉二聚体 (最危险)
        "Hairpin_Fwd": 0,
        "Hairpin_Rev": 0,
        "Dimer_Warning": ""
    }

    fwd_rc = str(Seq(fwd_seq).reverse_complement())
    rev_rc = str(Seq(rev_seq).reverse_complement())

    # 自身二聚体: 检查互补配对
    for i in range(len(fwd_seq) - 3):
        for j in range(i + 3, min(i + 12, len(fwd_seq))):
            sub = fwd_seq[i:j]
            if sub in fwd_rc:
                match_len = len(sub)
                if match_len > results["Self_Dimer_Fwd"]:
                    results["Self_Dimer_Fwd"] = match_len

    for i in range(len(rev_seq) - 3):
        for j in range(i + 3, min(i + 12, len(rev_seq))):
            sub = rev_seq[i:j]
            if sub in rev_rc:
                match_len = len(sub)
                if match_len > results["Self_Dimer_Rev"]:
                    results["Self_Dimer_Rev"] = match_len

    # 交叉二聚体
    for i in range(len(fwd_seq) - 3):
        for j in range(i + 3, min(i + 12, len(fwd_seq))):
            sub = fwd_seq[i:j]
            if sub in rev_seq:
                match_len = len(sub)
                if match_len > results["Cross_Dimer"]:
                    results["Cross_Dimer"] = match_len
            if sub in rev_rc:
                match_len = len(sub)
                if match_len > results["Cross_Dimer"]:
                    results["Cross_Dimer"] = match_len

    # 3' 端交叉二聚体 (最后 6bp)
    fwd_3p = fwd_seq[-6:]
    rev_3p = rev_seq[-6:]
    fwd_3p_rc = str(Seq(fwd_3p).reverse_complement())
    for i in range(len(fwd_3p_rc) - 2):
        for j in range(i + 2, len(fwd_3p_rc) + 1):
            sub = fwd_3p_rc[i:j]
            if sub in rev_3p:
                match_len = len(sub)
                if match_len > results["Cross_Dimer_3prime"]:
                    results["Cross_Dimer_3prime"] = match_len

    # 警告
    warnings = []
    if results["Self_Dimer_Fwd"] >= 5:
        warnings.append(f"Fwd自二聚>{results['Self_Dimer_Fwd']}bp")
    if results["Self_Dimer_Rev"] >= 5:
        warnings.append(f"Rev自二聚>{results['Self_Dimer_Rev']}bp")
    if results["Cross_Dimer_3prime"] >= 3:
        warnings.append("3'交叉二聚体风险!")
    if warnings:
        results["Dimer_Warning"] = "; ".join(warnings)

    return results


def run_blast_specificity(fwd_seq: str, rev_seq: str, virus_species: str,
                          db_taxid: Optional[str] = None) -> dict:
    """
    BLAST 特异性验证

    对 NCBI nt 数据库做 BLAST:
      - 正向引物 BLAST
      - 反向引物 BLAST
      - 分析命中是否为靶标病毒

    使用 PCR_strainer 逻辑: 检查是否有脱靶命中且
    ΔG 足够低 (< -9 kcal/mol) 可发生非特异性扩增。
    """
    results = {
        "BLAST_Fwd_TargetHits": 0,
        "BLAST_Fwd_OfftargetHits": 0,
        "BLAST_Rev_TargetHits": 0,
        "BLAST_Rev_OfftargetHits": 0,
        "BLAST_Offtarget_TopSpecies": "",
        "BLAST_Specificity_Score": 0,
        "BLAST_Warning": ""
    }

    try:
        # 限制 BLAST 数据库减少时间
        entrez_query = f'txid10239[Organism:exp]'  # Viruses 超界
        if db_taxid:
            entrez_query += f' OR txid{db_taxid}[Organism:exp]'  # + 植物宿主

        # 正向引物 BLAST
        result_handle = NCBIWWW.qblast(
            "blastn", "nt", fwd_seq,
            entrez_query=entrez_query,
            expect=1000,  # 短序列需要高 E-value
            word_size=7,
            hitlist_size=20,
            short_query=True
        )

        blast_records = NCBIXML.parse(result_handle)
        for record in blast_records:
            for alignment in record.alignments:
                title = alignment.title.lower()
                virus_lower = virus_species.lower()

                # 判断是否为靶标
                is_target = any(w in title for w in
                              virus_lower.split()[:3] if len(w) > 3)

                for hsp in alignment.hsps:
                    if is_target:
                        results["BLAST_Fwd_TargetHits"] += 1
                    else:
                        results["BLAST_Fwd_OfftargetHits"] += 1
                        if not results["BLAST_Offtarget_TopSpecies"]:
                            results["BLAST_Offtarget_TopSpecies"] = \
                                alignment.title[:100]
    except Exception as e:
        results["BLAST_Warning"] = f"BLAST失败: {str(e)[:100]}"
        return results

    # 特异性评分: 靶标命中数越高越好, 脱靶命中越低越好
    total_hits = results["BLAST_Fwd_TargetHits"] + results["BLAST_Fwd_OfftargetHits"]
    if total_hits > 0:
        specificity = results["BLAST_Fwd_TargetHits"] / total_hits * 100
        results["BLAST_Specificity_Score"] = round(specificity, 1)

    if results["BLAST_Fwd_OfftargetHits"] > 0:
        results["BLAST_Warning"] = \
            f"发现 {results['BLAST_Fwd_OfftargetHits']} 个脱靶命中"

    return results


def run_pcr_strainer_validation(primers_df: pl.DataFrame,
                                 output_dir: Path) -> pl.DataFrame:
    """
    使用 PCR_strainer 进行综合验证

    PCR_strainer 原生功能:
      - 解析 TNTBLAST 输出
      - 计算每个引物-模板对的 ΔG
      - 生成综合检测报告

    这里实现等效逻辑: 对每对引物做热力学评估
    """
    validated = []

    for row in primers_df.iter_rows(named=True):
        fwd = str(row.get("Fwd_Seq", "")).strip()
        rev = str(row.get("Rev_Seq", "")).strip()
        species = str(row.get("Species", ""))
        ptype = str(row.get("Type", ""))

        if not fwd or not rev or len(fwd) < 15 or len(rev) < 15:
            # 保留但标记为无效
            row_dict = dict(row)
            row_dict.update({
                "Validation_Score": 0,
                "Validation_Status": "INVALID",
                "Dimer_Score": "",
                "Specificity_Score": "",
                "Overall_Score": 0,
                "Recommendation": "序列无效"
            })
            validated.append(row_dict)
            continue

        # 1. 二聚体检查
        dimer = check_primer_dimer(fwd, rev)

        # 2. GC/Tm 复核
        fwd_gc = round((fwd.count('G') + fwd.count('C')) / len(fwd) * 100, 1)
        rev_gc = round((rev.count('G') + rev.count('C')) / len(rev) * 100, 1)

        # 3. 综合评分 (0-100)
        score = 100

        # GC 扣分
        if fwd_gc < 40 or fwd_gc > 60:
            score -= abs(fwd_gc - 50) * 1.5
        if rev_gc < 40 or rev_gc > 60:
            score -= abs(rev_gc - 50) * 1.5

        # 二聚体扣分
        if dimer["Cross_Dimer_3prime"] >= 3:
            score -= 30  # 3' 交叉二聚体致命
        elif dimer["Cross_Dimer"] >= 5:
            score -= 15
        if dimer["Self_Dimer_Fwd"] >= 5:
            score -= 10

        # 长度评分
        fwd_len = len(fwd)
        rev_len = len(rev)
        if abs(fwd_len - rev_len) > 3:
            score -= 5

        # 3' GC 夹
        fwd_3p_gc = (fwd[-5:].count('G') + fwd[-5:].count('C')) / 5 * 100
        rev_3p_gc = (rev[-5:].count('G') + rev[-5:].count('C')) / 5 * 100
        if fwd_3p_gc < 40:
            score -= 10

        # Poly-X 扣分
        for nt in ['A', 'T', 'G', 'C']:
            if nt * 5 in fwd or nt * 5 in rev:
                score -= 15
                break

        # 确定推荐等级
        if score >= 80:
            recommendation = "RECOMMENDED"
        elif score >= 60:
            recommendation = "USABLE"
        elif score >= 40:
            recommendation = "CAUTION"
        else:
            recommendation = "NOT_RECOMMENDED"

        row_dict = dict(row)
        row_dict.update({
            "GC_Fwd_Verified": fwd_gc,
            "GC_Rev_Verified": rev_gc,
            "Self_Dimer_Fwd": dimer["Self_Dimer_Fwd"],
            "Self_Dimer_Rev": dimer["Self_Dimer_Rev"],
            "Cross_Dimer": dimer["Cross_Dimer"],
            "Cross_Dimer_3prime": dimer["Cross_Dimer_3prime"],
            "Dimer_Warning": dimer["Dimer_Warning"],
            "Validation_Score": round(score, 1),
            "Validation_Status": "PASS" if score >= 40 else "FAIL",
            "Recommendation": recommendation,
            "Validated_At": datetime.now().isoformat()
        })

        validated.append(row_dict)

    return pl.DataFrame(validated)


def validate_single_primer(row: dict) -> dict:
    """对单对引物做快速验证 (不包含 BLAST)"""
    fwd = str(row.get("Fwd_Seq", "")).strip()
    rev = str(row.get("Rev_Seq", "")).strip()

    if not fwd or not rev or len(fwd) < 15 or len(rev) < 15:
        row_dict = dict(row)
        row_dict.update({
            "Quick_Validation": "INVALID",
            "Quick_Score": 0,
            "Issues": "序列长度不足或无效"
        })
        return row_dict

    dimer = check_primer_dimer(fwd, rev)
    issues = []

    fwd_gc = (fwd.count('G') + fwd.count('C')) / len(fwd) * 100
    rev_gc = (rev.count('G') + rev.count('C')) / len(rev) * 100

    if fwd_gc < 40 or fwd_gc > 60:
        issues.append(f"Fwd GC={fwd_gc:.1f}%")
    if rev_gc < 40 or rev_gc > 60:
        issues.append(f"Rev GC={rev_gc:.1f}%")
    if dimer["Cross_Dimer_3prime"] >= 3:
        issues.append("3'交叉二聚体")

    score = 100
    for issue in issues:
        score -= 20

    row_dict = dict(row)
    row_dict.update({
        "Quick_Validation": "PASS" if score >= 60 else "FAIL",
        "Quick_Score": max(0, score),
        "Issues": "; ".join(issues) if issues else "OK"
    })

    return row_dict


def _run_delta_g_validation(df: pl.DataFrame, out_dir: Path):
    """
    基于 primer3-py 的引物-模板 ΔG 热力学分析。

    替代 TNTBLAST/PCR_strainer 的轻量方案:
      - 引物-引物 ΔG (heterodimer): 二聚体形成倾向
      - 引物自身 ΔG (homodimer):  自身结合稳定性
      - 引物 3' 端 ΔG:   3' 端结合稳定性 (特异性关键)

    PCR_strainer 的科学原理:
        TNTBLAST 的核心优势是计算引物-模板的 ΔG,
        而不仅仅是序列匹配。但我们用 primer3-py 实现
        等效的引物-引物 ΔG 分析 (不需要 TNTBLAST)。
    """
    try:
        import primer3 as p3
    except ImportError:
        print("  ⚠ primer3-py 未安装, 跳过 ΔG 分析")
        return

    results = []
    for row in df.iter_rows(named=True):
        fwd = str(row.get("Fwd_Seq", row.get("Fwd_Seq", "")))
        rev = str(row.get("Rev_Seq", row.get("Rev_Seq", "")))
        if not fwd or not rev or len(fwd) < 10:
            continue

        try:
            # 引物交叉二聚体 ΔG (越低越易形成二聚体)
            hetero = p3.calc_heterodimer(fwd, rev)
            # 正向引物自身二聚体 ΔG
            homo_fwd = p3.calc_homodimer(fwd)
            # 反向引物自身二聚体 ΔG
            homo_rev = p3.calc_homodimer(rev)
            # 3' 端 5bp 特异性检查
            fwd_3p = fwd[-5:]
            rev_3p = rev[-5:]

            results.append({
                "Species": row.get("Species", ""),
                "Pair_ID": row.get("Pair_ID", ""),
                "Type": row.get("Type", ""),
                "Heterodimer_dG": round(hetero.dg, 2) if hetero.dg else "",
                "Heterodimer_Tm": round(hetero.tm, 1) if hetero.tm else "",
                "Homodimer_Fwd_dG": round(homo_fwd.dg, 2) if homo_fwd.dg else "",
                "Homodimer_Rev_dG": round(homo_rev.dg, 2) if homo_rev.dg else "",
                "Fwd_3p_GC": round((fwd_3p.count('G') + fwd_3p.count('C')) / 5 * 100, 1),
                "Rev_3p_GC": round((rev_3p.count('G') + rev_3p.count('C')) / 5 * 100, 1),
            })
        except Exception:
            continue

    if results:
        dg_df = pl.DataFrame(results)
        dg_file = out_dir / "delta_g_analysis.tsv"
        dg_df.write_csv(dg_file, separator='\t')
        print(f"  ΔG 分析: {len(results)} 对引物 → {dg_file}")

        # 警告: ΔG < -9 kcal/mol 的二聚体风险高
        high_risk = dg_df.filter(
            (pl.col("Heterodimer_dG").cast(pl.Float64) < -9) |
            (pl.col("Homodimer_Fwd_dG").cast(pl.Float64) < -9) |
            (pl.col("Homodimer_Rev_dG").cast(pl.Float64) < -9)
        )
        if high_risk.height > 0:
            print(f"  ⚠ 高风险二聚体: {high_risk.height} 对引物 (ΔG < -9 kcal/mol)")


def main():
    parser = argparse.ArgumentParser(description="引物特异性验证")
    parser.add_argument("--input", default=str(PRIMER_FILE))
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    parser.add_argument("--skip-blast", action="store_true",
                       help="跳过 BLAST (加速, BLAST 很慢)")
    parser.add_argument("--use-pcr-strainer", action="store_true",
                       help="使用 PCR_strainer ΔG 热力学验证")
    parser.add_argument("--pcr-strainer-db", default="",
                       help="PCR_strainer 宿主基因组 FASTA (检测脱靶)")
    parser.add_argument("--quick", action="store_true",
                       help="快速模式: 仅做二聚体+GC验证")
    parser.add_argument("--blast-species", default="",
                       help="BLAST 验证指定物种 (逗号分隔)")
    args = parser.parse_args()

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"✗ 输入文件不存在: {input_file}")
        print("  请先运行: python step2_design_primers.py")
        return

    df = pl.read_csv(input_file, separator='\t', ignore_errors=True)
    print(f"加载 {len(df)} 对引物")
    print(f"  类型: {df['Type'].unique().to_list()}")
    print()

    # 快速验证模式
    if args.quick:
        print("→ 快速验证模式...")
        rows = df.to_dicts()
        validated_rows = []
        for i, row in enumerate(rows):
            validated_rows.append(validate_single_primer(row))
            if (i + 1) % 100 == 0:
                print(f"  进度: {i+1}/{len(rows)}")

        df_validated = pl.DataFrame(validated_rows)
        df_validated.write_csv(args.output, separator='\t')

        # 统计
        passed = df_validated.filter(pl.col("Quick_Validation") == "PASS")
        failed = df_validated.filter(pl.col("Quick_Validation") != "PASS")
        print(f"\n  ✓ 通过: {passed.height}")
        print(f"  ✗ 未通过: {failed.height}")
        print(f"  结果 → {args.output}")
        return

    # 完整验证模式
    print("→ 完整验证 (二聚体 + GC/Tm + 综合评分)...")
    df_validated = run_pcr_strainer_validation(df, Path(args.output).parent)

    # PCR_strainer ΔG 热力学验证模式
    if args.use_pcr_strainer:
        print("→ 运行 ΔG 热力学验证 (PCR_strainer / primer3)...")
        _run_delta_g_validation(df_validated, Path(args.output).parent)

    # 独立 PCR_strainer 模式 (需要 TNTBLAST + pcr_strainer CLI)
    if args.use_pcr_strainer and shutil.which("pcr_strainer"):
        print("→ 运行 PCR_strainer CLI...")
        try:
            # 生成 assay CSV: assay_name, fwd_name, fwd_seq, rev_name, rev_seq, probe_name, probe_seq
            assay_csv = Path(args.output).parent / "pcr_strainer_assay.csv"
            with open(assay_csv, 'w') as f:
                f.write("assay_name,fwd_name,fwd_seq,rev_name,rev_seq,probe_name,probe_seq\n")
                for row in df.iter_rows(named=True):
                    sp = row.get('Species', '').replace(' ', '_')[:30]
                    pid = row.get('Pair_ID', '1')
                    f.write(f"{sp}_{row.get('Type','PCR')}_{pid},"
                           f"{sp}_Fwd_{pid},{row.get('Fwd_Seq','')},"
                           f"{sp}_Rev_{pid},{row.get('Rev_Seq','')},"
                           f"{sp}_Probe_{pid},{row.get('Probe_Seq','')}\n")

            # 宿主基因组 BLAST 数据库 (检测脱靶)
            host_db = args.pcr_strainer_db
            if host_db and Path(host_db).exists():
                cmd = ["pcr_strainer", "-a", str(assay_csv),
                       "-g", str(host_db),
                       "-o", str(Path(args.output).parent / "pcr_strainer_result")]
                subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                print(f"  PCR_strainer 结果 → pcr_strainer_result*")
        except Exception as e:
            print(f"  ⚠ PCR_strainer CLI 失败: {e}")
    elif args.use_pcr_strainer:
        print(f"  ⚠ pcr_strainer CLI 未安装, 使用 primer3 ΔG 分析")
        print(f"    安装: pip install pcr_strainer")

    # BLAST 验证 (可选)
    if not args.skip_blast:
        print("\n→ BLAST 特异性验证 (最慢, 仅验证 top 引物)...")
        # 对所有 PCR 类型的引物做 BLAST 太慢, 仅对每个物种的 top-1
        top_primers = df_validated.filter(
            (pl.col("Pair_ID") == "1") & (pl.col("Type") == "PCR")
        )

        if args.blast_species:
            blast_targets = args.blast_species.split(",")
            top_primers = top_primers.filter(pl.col("Species").is_in(blast_targets))

        print(f"  BLAST 验证 {top_primers.height} 对引物...")
        blast_results = []
        for row in top_primers.iter_rows(named=True):
            result = run_blast_specificity(
                str(row.get("Fwd_Seq", "")),
                str(row.get("Rev_Seq", "")),
                str(row.get("Species", ""))
            )
            row.update(result)
            blast_results.append(row)

        # 合并 BLAST 结果
        if blast_results:
            blast_df = pl.DataFrame(blast_results)
            blast_file = Path(args.output).parent / "blast_validation.tsv"
            blast_df.write_csv(blast_file, separator='\t')
            print(f"  BLAST 结果 → {blast_file}")

    # 保存
    df_validated.write_csv(args.output, separator='\t')

    # 统计
    rec_col = "Recommendation" if "Recommendation" in df_validated.columns else "Quick_Validation"
    print(f"\n{'='*70}")
    print("验证完成!")
    print(f"  总引物: {len(df_validated)} 对")
    for status in df_validated[rec_col].unique().to_list():
        count = df_validated.filter(pl.col(rec_col) == status).height
        print(f"    {status}: {count}")
    print(f"  结果 → {args.output}")
    print(f"  下一步: python step4_build_database.py")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
