#!/usr/bin/env python3
"""
Step 4: 构建引物数据库 + 搜索 API
========================================================================
将验证后的引物数据存入 SQLite 数据库，提供:
  - 按病毒物种/属/科搜索
  - 按引物类型过滤 (PCR/qPCR/DEGENERATE)
  - 按验证评分排序
  - 引物详情查询 (含探针信息)
  - 导出为 FASTA/TSV

数据库表结构:
  - primers: 引物信息 (主表)
  - taxonomy: 病毒分类学信息
  - validation: 验证结果

这是 Web 界面的数据后端。
"""

import argparse
import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

import polars as pl
from Bio import SeqIO


# ______________________________________________________________________
VALIDATED_PRIMERS = Path("designed_primers/all_primers_validated.tsv")
_BASE = Path(__file__).resolve().parent
DB_PATH = _BASE / "primer_database.db"
DEFAULT_SPECIES_INDEX = Path("split_species/species_index.tsv")


def create_database(db_path: Path):
    """创建 SQLite 数据库表结构"""
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    # 防止并发访问锁库 + 加速写入
    c.executescript('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA synchronous=NORMAL;')

    # 病毒分类学表
    c.execute('''CREATE TABLE IF NOT EXISTS taxonomy (
            species_id INTEGER PRIMARY KEY AUTOINCREMENT,
            species_name TEXT NOT NULL UNIQUE,
            genus TEXT DEFAULT '',
            family TEXT DEFAULT '',
            order_name TEXT DEFAULT '',
            priority TEXT DEFAULT 'MEDIUM',
            num_sequences INTEGER DEFAULT 0,
            genome_length INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 兼容旧表缺列
    try:
        c.execute('ALTER TABLE taxonomy ADD COLUMN genome_length INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    # 引物主表
    c.execute('''
        CREATE TABLE IF NOT EXISTS primers (
            primer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            species_name TEXT NOT NULL,
            primer_type TEXT NOT NULL CHECK(primer_type IN (
                'PCR', 'qPCR', 'DEGENERATE', 'TILED',
                'CRISPR_Cas12a', 'CRISPR_Cas9', 'DELIVERY_VERIFY'
            )),
            pair_id TEXT NOT NULL,
            fwd_sequence TEXT NOT NULL,
            rev_sequence TEXT NOT NULL,
            probe_sequence TEXT DEFAULT '',
            probe_tm REAL DEFAULT 0,
            fwd_tm REAL DEFAULT 0,
            rev_tm REAL DEFAULT 0,
            fwd_position INTEGER DEFAULT 0,
            rev_position INTEGER DEFAULT 0,
            product_size INTEGER DEFAULT 0,
            gc_fwd REAL DEFAULT 0,
            gc_rev REAL DEFAULT 0,
            tile_id INTEGER DEFAULT 0,
            crrna_spacer TEXT DEFAULT '',
            pam_site TEXT DEFAULT '',
            target_region TEXT DEFAULT '',
            design_method TEXT DEFAULT '',
            penalty REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (species_name) REFERENCES taxonomy(species_name)
        )
    ''')

    # 验证结果表
    c.execute('''
        CREATE TABLE IF NOT EXISTS validation (
            validation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            primer_id INTEGER NOT NULL UNIQUE,
            gc_fwd_verified REAL DEFAULT 0,
            gc_rev_verified REAL DEFAULT 0,
            self_dimer_fwd INTEGER DEFAULT 0,
            self_dimer_rev INTEGER DEFAULT 0,
            cross_dimer INTEGER DEFAULT 0,
            cross_dimer_3prime INTEGER DEFAULT 0,
            dimer_warning TEXT DEFAULT '',
            blast_specificity_score REAL DEFAULT 0,
            blast_offtarget_top TEXT DEFAULT '',
            overall_score REAL DEFAULT 0,
            recommendation TEXT DEFAULT 'UNVALIDATED',
            validated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (primer_id) REFERENCES primers(primer_id)
        )
    ''')

    # 兼容: 旧表新增列 (探针验证 + 覆盖度 + BLAST Fwd/Rev 分离)
    alter_cols = [
        ("ALTER TABLE primers ADD COLUMN probe_gc REAL DEFAULT 0", "probe_gc"),
        ("ALTER TABLE validation ADD COLUMN blast_fwd_target_hits INTEGER DEFAULT 0", "blast_fwd_target_hits"),
        ("ALTER TABLE validation ADD COLUMN blast_fwd_plant_hits INTEGER DEFAULT 0", "blast_fwd_plant_hits"),
        ("ALTER TABLE validation ADD COLUMN blast_fwd_other_hits INTEGER DEFAULT 0", "blast_fwd_other_hits"),
        ("ALTER TABLE validation ADD COLUMN blast_rev_target_hits INTEGER DEFAULT 0", "blast_rev_target_hits"),
        ("ALTER TABLE validation ADD COLUMN blast_rev_plant_hits INTEGER DEFAULT 0", "blast_rev_plant_hits"),
        ("ALTER TABLE validation ADD COLUMN blast_rev_other_hits INTEGER DEFAULT 0", "blast_rev_other_hits"),
        ("ALTER TABLE validation ADD COLUMN probe_hairpin_tm REAL DEFAULT 0", "probe_hairpin_tm"),
        ("ALTER TABLE validation ADD COLUMN probe_self_dimer_dg REAL DEFAULT 0", "probe_self_dimer_dg"),
        ("ALTER TABLE validation ADD COLUMN probe_fwd_dimer_dg REAL DEFAULT 0", "probe_fwd_dimer_dg"),
        ("ALTER TABLE validation ADD COLUMN probe_rev_dimer_dg REAL DEFAULT 0", "probe_rev_dimer_dg"),
        ("ALTER TABLE validation ADD COLUMN probe_tm_diff_ok INTEGER DEFAULT 1", "probe_tm_diff_ok"),
        ("ALTER TABLE validation ADD COLUMN probe_warning TEXT DEFAULT ''", "probe_warning"),
        ("ALTER TABLE validation ADD COLUMN fwd_coverage_pct REAL DEFAULT 0", "fwd_coverage_pct"),
        ("ALTER TABLE validation ADD COLUMN rev_coverage_pct REAL DEFAULT 0", "rev_coverage_pct"),
        ("ALTER TABLE validation ADD COLUMN fwd_3prime_penalty REAL DEFAULT 0", "fwd_3prime_penalty"),
        ("ALTER TABLE validation ADD COLUMN rev_3prime_penalty REAL DEFAULT 0", "rev_3prime_penalty"),
        ("ALTER TABLE validation ADD COLUMN coverage_avg REAL DEFAULT 0", "coverage_avg"),
        ("ALTER TABLE validation ADD COLUMN coverage_total_seqs INTEGER DEFAULT 0", "coverage_total_seqs"),
    ]
    for stmt, _col in alter_cols:
        try:
            c.execute(stmt)
        except sqlite3.OperationalError:
            pass  # 列已存在, 忽略

    # 索引
    c.execute('CREATE INDEX IF NOT EXISTS idx_species ON primers(species_name)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_type ON primers(primer_type)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_recommendation ON validation(recommendation)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_overall_score ON validation(overall_score)')

    # 全文搜索 (FTS5) 用于快速物种名搜索
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS primers_fts USING fts5(
            species_name, fwd_sequence, rev_sequence,
            content='primers', content_rowid='primer_id'
        )
    ''')

    conn.commit()
    conn.close()
    print(f"数据库已创建: {db_path}")


def import_taxonomy(db_path: Path, taxonomy_file: Path):
    """导入病毒分类学信息"""
    if not taxonomy_file.exists():
        print(f"  ⚠ 分类学文件不存在: {taxonomy_file}")
        return

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    df = pl.read_csv(taxonomy_file, separator='\t', ignore_errors=True)
    imported = 0

    for row in df.iter_rows(named=True):
        sp = str(row.get("Species", "")).strip()
        if not sp:
            continue
        try:
            c.execute('''
                INSERT OR REPLACE INTO taxonomy
                (species_name, genus, family, priority, num_sequences, genome_length)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                sp,
                str(row.get("Genus", "")).strip(),
                str(row.get("Family", "")).strip(),
                str(row.get("Priority", "MEDIUM")).strip(),
                int(row.get("Record_Count", 0)),
                int(row.get("Genome_Length", 0))
            ))
            imported += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    print(f"  分类学: {imported} 个物种已导入")


def update_genome_lengths(db_path: Path, species_index: Path):
    """从 FASTA 文件读取真实基因组长度并更新 taxonomy 表"""
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    updated = 0
    try:
        if not species_index.exists():
            conn.close(); return
        idx = pl.read_csv(species_index, separator='\t', ignore_errors=True)
        for row in idx.iter_rows(named=True):
            sp = str(row.get("Species", "")).strip()
            fa_path = str(row.get("FASTA", "")).strip()
            if not sp or not fa_path: continue
            try:
                fa_full = str(Path(species_index).parent / Path(fa_path))
                max_len = max((len(r.seq) for r in SeqIO.parse(fa_full, "fasta")), default=0)
                if max_len > 0:
                    c.execute("UPDATE taxonomy SET genome_length = ? WHERE species_name = ?",
                              (max_len, sp))
                    if c.rowcount > 0: updated += 1
            except Exception: continue
        conn.commit()
    except Exception: pass
    finally:
        conn.close()
    print(f"({updated} 物种)", end=" ", flush=True)


def import_primers(db_path: Path, primer_file: Path):
    """导入引物数据"""
    if not primer_file.exists():
        print(f"  ⚠ 引物文件不存在: {primer_file}")
        return

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    df = pl.read_csv(primer_file, separator='\t', ignore_errors=True)
    imported_primers = 0
    imported_validation = 0

    for row in df.iter_rows(named=True):
        sp = str(row.get("Species", "")).strip()
        ptype = str(row.get("Type", "PCR")).strip()
        pair_id = str(row.get("Pair_ID", "1"))
        fwd = str(row.get("Fwd_Seq", "")).strip().upper()
        rev = str(row.get("Rev_Seq", "")).strip().upper()

        if not sp or not fwd or not rev:
            continue

        # 确保物种在 taxonomy 表中
        c.execute('SELECT species_name FROM taxonomy WHERE species_name = ?', (sp,))
        if not c.fetchone():
            c.execute(
                'INSERT OR IGNORE INTO taxonomy (species_name) VALUES (?)',
                (sp,)
            )

        # 导入引物
        try:
            c.execute('''
                INSERT INTO primers (
                    species_name, primer_type, pair_id,
                    fwd_sequence, rev_sequence, probe_sequence,
                    probe_tm, fwd_tm, rev_tm,
                    fwd_position, rev_position, product_size,
                    gc_fwd, gc_rev, tile_id,
                    crrna_spacer, pam_site, target_region,
                    design_method, penalty
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                sp, ptype, pair_id,
                fwd, rev,
                str(row.get("Probe_Seq", "")).strip(),
                _to_float(row.get("Probe_Tm", 0)),
                _to_float(row.get("Fwd_Tm", 0)),
                _to_float(row.get("Rev_Tm", 0)),
                _to_int(row.get("Fwd_Start", row.get("Fwd_Pos", 0))),
                _to_int(row.get("Rev_Start", row.get("Rev_Pos", 0))),
                _to_int(row.get("Product", row.get("Product_Size", 0))),
                _to_float(row.get("GC_Fwd", row.get("GC_Fwd_Verified", 0))),
                _to_float(row.get("GC_Rev", row.get("GC_Rev_Verified", 0))),
                _to_int(row.get("Tile_ID", 0)),
                str(row.get("crRNA_Spacer", "")).strip(),
                str(row.get("PAM_Site", "")).strip(),
                str(row.get("Target_Region", "")).strip(),
                str(row.get("Method", "")).strip(),
                _to_float(row.get("Penalty", 0))
            ))
            primer_id = c.lastrowid
            imported_primers += 1

            # 导入验证结果 (含探针验证 + 覆盖度 + BLAST Fwd/Rev 分离)
            c.execute('''
                INSERT OR REPLACE INTO validation (
                    primer_id, gc_fwd_verified, gc_rev_verified,
                    self_dimer_fwd, self_dimer_rev,
                    cross_dimer, cross_dimer_3prime,
                    dimer_warning, blast_specificity_score,
                    blast_offtarget_top, overall_score,
                    recommendation, validated_at,
                    blast_fwd_target_hits, blast_fwd_plant_hits, blast_fwd_other_hits,
                    blast_rev_target_hits, blast_rev_plant_hits, blast_rev_other_hits,
                    probe_hairpin_tm, probe_self_dimer_dg, probe_fwd_dimer_dg, probe_rev_dimer_dg,
                    probe_tm_diff_ok, probe_warning,
                    fwd_coverage_pct, rev_coverage_pct, fwd_3prime_penalty, rev_3prime_penalty,
                    coverage_avg, coverage_total_seqs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                primer_id,
                _to_float(row.get("GC_Fwd_Verified", row.get("GC_Fwd", 0))),
                _to_float(row.get("GC_Rev_Verified", row.get("GC_Rev", 0))),
                _to_int(row.get("Self_Dimer_Fwd", 0)),
                _to_int(row.get("Self_Dimer_Rev", 0)),
                _to_int(row.get("Cross_Dimer", 0)),
                _to_int(row.get("Cross_Dimer_3prime", 0)),
                str(row.get("Dimer_Warning", "")).strip(),
                _to_float(row.get("BLAST_Specificity_Score", 0)),
                str(row.get("BLAST_Offtarget_TopSpecies", "")).strip()[:200],
                _to_float(row.get("Validation_Score", row.get("Quick_Score", 0))),
                str(row.get("Recommendation", row.get("Quick_Validation", "UNVALIDATED"))).strip(),
                str(row.get("Validated_At", datetime.now().isoformat())),
                # BLAST Fwd
                _to_int(row.get("BLAST_Fwd_TargetHits", 0)),
                _to_int(row.get("BLAST_Fwd_PlantHits", 0)),
                _to_int(row.get("BLAST_Fwd_OtherHits", 0)),
                # BLAST Rev
                _to_int(row.get("BLAST_Rev_TargetHits", 0)),
                _to_int(row.get("BLAST_Rev_PlantHits", 0)),
                _to_int(row.get("BLAST_Rev_OtherHits", 0)),
                # 探针验证
                _to_float(row.get("Probe_Hairpin_Tm", 0)),
                _to_float(row.get("Probe_Self_Dimer_dG", 0)),
                _to_float(row.get("Probe_Fwd_Dimer_dG", 0)),
                _to_float(row.get("Probe_Rev_Dimer_dG", 0)),
                1 if row.get("Probe_Tm_Diff_Ok", True) else 0,
                str(row.get("Probe_Warning", "")).strip(),
                # 覆盖度
                _to_float(row.get("Fwd_Coverage_Pct", 0)),
                _to_float(row.get("Rev_Coverage_Pct", 0)),
                _to_float(row.get("Fwd_3Prime_Penalty", 0)),
                _to_float(row.get("Rev_3Prime_Penalty", 0)),
                _to_float(row.get("Coverage_Avg", 0)),
                _to_int(row.get("Coverage_Total_Seqs", 0))
            ))
            imported_validation += 1

        except Exception as e:
            print(f"  ⚠ 导入失败 {sp}/{ptype}/{pair_id}: {e}")

    conn.commit()
    conn.close()
    print(f"  引物: {imported_primers} 对已导入")
    print(f"  验证: {imported_validation} 条已导入")


def _to_float(val, default=0.0):
    """安全转为浮点数，处理简并引物的范围字符串 (如 '55.0-63.0')"""
    try:
        if isinstance(val, str) and '-' in val and not val.strip().startswith('-'):
            parts = val.split('-')
            if len(parts) == 2:
                return (float(parts[0]) + float(parts[1])) / 2
        return float(val)
    except (ValueError, TypeError):
        return default


def _to_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def optimize_database(db_path: Path):
    """优化数据库: VACUUM + ANALYZE"""
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute('VACUUM')
    c.execute('ANALYZE')
    conn.close()
    print("  数据库已优化")


def print_statistics(db_path: Path):
    """打印数据库统计信息"""
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    print(f"\n{'='*70}")
    print("数据库统计")

    c.execute('SELECT COUNT(*) FROM taxonomy')
    print(f"  病毒物种: {c.fetchone()[0]}")

    c.execute('SELECT primer_type, COUNT(*) FROM primers GROUP BY primer_type ORDER BY COUNT(*) DESC')
    for row in c.fetchall():
        print(f"    {row[0]}: {row[1]} 对")

    c.execute('SELECT recommendation, COUNT(*) FROM validation GROUP BY recommendation ORDER BY COUNT(*) DESC')
    for row in c.fetchall():
        print(f"    {row[0]}: {row[1]} 条")

    # 得分分布
    c.execute('''
        SELECT
            CASE
                WHEN overall_score >= 80 THEN '80-100'
                WHEN overall_score >= 60 THEN '60-79'
                WHEN overall_score >= 40 THEN '40-59'
                ELSE '0-39'
            END AS score_range,
            COUNT(*)
        FROM validation
        GROUP BY score_range
        ORDER BY score_range DESC
    ''')
    print(f"  评分分布:")
    for row in c.fetchall():
        print(f"    {row[0]}: {row[1]} 对")

    conn.close()


def build_search_api_examples(db_path: Path):
    """生成搜索 API 使用示例"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    examples = {}

    # 示例 1: 按物种搜索
    c.execute('''
        SELECT p.primer_id, p.species_name, p.primer_type, p.pair_id,
               p.fwd_sequence, p.rev_sequence, p.probe_sequence,
               p.product_size, p.gc_fwd, p.gc_rev,
               v.overall_score, v.recommendation
        FROM primers p
        LEFT JOIN validation v ON p.primer_id = v.primer_id
        WHERE v.recommendation = 'RECOMMENDED'
        ORDER BY v.overall_score DESC
        LIMIT 5
    ''')
    examples["top_recommended"] = [dict(r) for r in c.fetchall()]

    # 示例 2: 按引物类型 + 评分过滤
    for ptype in ['PCR', 'qPCR', 'DEGENERATE']:
        c.execute('''
            SELECT p.species_name, p.primer_type, COUNT(*) as count,
                   AVG(v.overall_score) as avg_score
            FROM primers p
            LEFT JOIN validation v ON p.primer_id = v.primer_id
            WHERE p.primer_type = ?
            GROUP BY p.species_name
            ORDER BY avg_score DESC
            LIMIT 10
        ''', (ptype,))
        examples[f"best_{ptype.lower()}_species"] = [dict(r) for r in c.fetchall()]

    conn.close()

    # 写入 JSON 供 Web API 直接使用
    api_file = Path(db_path).parent / "api_examples.json"
    with open(api_file, 'w', encoding='utf-8') as f:
        json.dump(examples, f, indent=2, ensure_ascii=False)
    print(f"  API 示例 → {api_file}")

    return examples


def main():
    parser = argparse.ArgumentParser(description="构建引物数据库")
    parser.add_argument("--primers", default=str(VALIDATED_PRIMERS))
    parser.add_argument("--species-index", default=str(DEFAULT_SPECIES_INDEX),
                       help="step1 输出的 species_index.tsv")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--force", action="store_true", help="强制重建数据库")
    args = parser.parse_args()

    db_path = Path(args.db)

    if args.force and db_path.exists():
        db_path.unlink()
        print(f"已删除旧数据库: {db_path}")

    # 创建数据库
    if not db_path.exists():
        create_database(db_path)

    # 导入数据
    print("\n→ 导入数据...")
    import_taxonomy(db_path, Path(args.species_index))
    import_primers(db_path, Path(args.primers))

    print("  基因组长度: 从 species_index.tsv 直接读取 (跳过 FASTA 解析)", flush=True)

    # 优化
    print("\n→ 优化数据库...")
    optimize_database(db_path)

    # 统计
    print_statistics(db_path)

    # 生成 API 示例
    print("\n→ 生成 API 示例...")
    build_search_api_examples(db_path)

    print(f"\n{'='*70}")
    print("数据库构建完成!")
    print(f"  数据库: {db_path}")
    print(f"  下一步: python step5_web_server.py")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
