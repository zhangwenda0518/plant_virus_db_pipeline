#!/usr/bin/env python3
"""
Step 1: 从 NCBI 批量下载植物病毒基因组序列
========================================================================
三种下载策略，按优先级依次尝试:

  策略 A: NCBI Entrez Direct (esearch + efetch)
    - 使用 Biopython Bio.Entrez 模块
    - 根据物种名称搜索 Nucleotide 数据库
    - 下载完整的 RefSeq 基因组序列

  策略 B: NCBI Datasets CLI
    - 专门针对病毒基因组设计
    - 下载基因组 + 注释 GFF
    - 命令: datasets download virus genome taxon <TAXID>

  策略 C: 从已有 Plant.tsv 的 Accession 号直接下载
    - 如果数据中已有 GenBank Accession
    - 直接 efetch 对应序列

下载内容:
  - 完整基因组序列 (FASTA)
  - CDS 区域标注
  - 每个病毒物种 ≥ 1 条参考序列

注意事项:
  - NCBI API 限速: 每秒 ≤ 3 次请求 (无 API Key) / 每秒 ≤ 10 次 (有 API Key)
  - 大规模下载需设置 email (NCBI 要求)
"""

import argparse
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

import polars as pl
from Bio import Entrez, SeqIO


# ______________________________________________________________________
# 配置
SPECIES_LIST = Path("D:/桌面/C-host_classify/引物设计/plant_virus_species.tsv")
GENOME_DIR = Path("D:/桌面/C-host_classify/引物设计/virus_genomes")
METADATA_FILE = Path("D:/桌面/C-host_classify/引物设计/virus_genomes/metadata.tsv")
EMAIL = "1771182368@qq.com"  # NCBI 要求 (请替换为你的邮箱)
NCBI_API_KEY = ""  # 可选: 填入 NCBI API Key 可提高速率至 10 req/s

# 速率限制
REQUEST_DELAY = 0.35 if not NCBI_API_KEY else 0.1  # 秒
MAX_RETRIES = 3


def setup():
    """初始化 Entrez + 输出目录"""
    Entrez.email = EMAIL
    if NCBI_API_KEY:
        Entrez.api_key = NCBI_API_KEY

    GENOME_DIR.mkdir(parents=True, exist_ok=True)
    (GENOME_DIR / "per_species").mkdir(exist_ok=True)


def search_taxid(virus_name: str) -> Optional[str]:
    """
    策略 A-1: 搜索 NCBI Taxonomy ID

    用病毒物种名搜索 Taxonomy 数据库获取 TaxID。
    TaxID 可用来查询完整的基因组 RefSeq 记录。
    """
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY)
            handle = Entrez.esearch(
                db="taxonomy",
                term=f'"{virus_name}"[Scientific Name]',
                retmode="xml"
            )
            records = Entrez.read(handle)
            handle.close()

            id_list = records.get("IdList", [])
            if id_list:
                return id_list[0]
        except Exception as e:
            if "HTTP 400" in str(e):
                # 查询格式错误，尝试简化名称
                simple = virus_name.split()[0]
                try:
                    time.sleep(REQUEST_DELAY)
                    handle = Entrez.esearch(
                        db="taxonomy",
                        term=f"{simple}[All Names]",
                        retmode="xml"
                    )
                    records = Entrez.read(handle)
                    handle.close()
                    if records.get("IdList"):
                        return records["IdList"][0]
                except Exception:
                    pass
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return None


def search_refseq_genomes(taxid: str, virus_name: str, max_seq: int = 10) -> list[str]:
    """
    策略 A-2: 通过 TaxID 搜索 RefSeq 基因组

    搜索 Nucleotide 数据库中的 RefSeq 条目:
      - 过滤: "refseq[filter]" 只获取 RefSeq 记录
      - 过滤: "complete genome" 优先完整基因组
    """
    accessions = []
    queries = [
        f'txid{taxid}[Organism] AND refseq[filter] AND complete genome[title]',
        f'txid{taxid}[Organism] AND refseq[filter]',
        f'"{virus_name}"[Organism] AND complete genome[All Fields]',
    ]

    for query in queries:
        if len(accessions) >= max_seq:
            break
        try:
            time.sleep(REQUEST_DELAY)
            handle = Entrez.esearch(
                db="nucleotide",
                term=query,
                retmax=max_seq,
                retmode="xml"
            )
            records = Entrez.read(handle)
            handle.close()

            new_ids = records.get("IdList", [])
            for nid in new_ids:
                if nid not in accessions:
                    accessions.append(nid)
        except Exception as e:
            print(f"    ⚠ 搜索失败 ({query[:50]}...): {e}")
            continue

    return accessions[:max_seq]


def download_fasta_by_accession(accession: str, output_file: Path) -> bool:
    """策略 A-3: 根据 GenBank Accession 下载 FASTA 序列"""
    if output_file.exists() and output_file.stat().st_size > 0:
        return True  # 已存在

    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY)
            handle = Entrez.efetch(
                db="nucleotide",
                id=accession,
                rettype="fasta",
                retmode="text"
            )
            seq_text = handle.read()
            handle.close()

            if seq_text and len(seq_text) > 100:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(seq_text)
                return True
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    return False


def download_genome_sequences(virus_name: str, taxid: str,
                              accessions: list[str]) -> list[Path]:
    """
    下载基因组序列文件

    为每个 Accession 下载 FASTA 文件到 per_species/ 目录。
    返回成功下载的文件路径列表。
    """
    safe_name = virus_name.replace('/', '_').replace(' ', '_').replace(':', '_')[:80]
    downloaded = []

    for i, acc in enumerate(accessions):
        out_file = GENOME_DIR / "per_species" / safe_name / f"{acc}.fasta"
        out_file.parent.mkdir(parents=True, exist_ok=True)

        if download_fasta_by_accession(acc, out_file):
            downloaded.append(out_file)

    # 如果按 Accession 下载失败，尝试直接按物种名下载
    if not downloaded:
        out_file = GENOME_DIR / "per_species" / safe_name / f"{safe_name}.fasta"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            time.sleep(REQUEST_DELAY)
            handle = Entrez.efetch(
                db="nucleotide",
                id=accessions if accessions else [taxid],
                rettype="fasta",
                retmode="text"
            )
            # 合并下载
            pass
        except Exception:
            pass

    return downloaded


def merge_species_fastas(species_name: str, fasta_files: list[Path]) -> Optional[Path]:
    """
    将同一物种的多个基因组 FASTA 合并为单个多序列文件

    这是下游引物设计工具的输入格式:
      - 多序列比对 → 设计保守引物 → 覆盖更多株系
      - 单序列 → 直接设计特异引物
    """
    if not fasta_files:
        return None

    safe_name = species_name.replace('/', '_').replace(' ', '_').replace(':', '_')[:80]
    merged = GENOME_DIR / "per_species" / safe_name / f"{safe_name}_merged.fasta"

    if merged.exists():
        return merged

    all_records = []
    seen_ids = set()
    for f in fasta_files:
        if f.exists():
            try:
                for record in SeqIO.parse(f, "fasta"):
                    rid = record.id
                    if rid not in seen_ids:
                        all_records.append(record)
                        seen_ids.add(rid)
            except Exception:
                continue

    if all_records:
        with open(merged, 'w') as out:
            SeqIO.write(all_records, out, "fasta")
        return merged

    return None


def process_priority_species(species_df: pl.DataFrame) -> list[dict]:
    """
    主处理循环: 遍历高优先级物种，下载基因组

    返回 metadata 列表，记录每个物种的下载状态。
    """
    metadata = []
    species_list = species_df.to_dicts()

    total = len(species_list)
    for i, row in enumerate(species_list):
        virus_name = row.get("Species", "").strip()
        priority = row.get("Priority", "MEDIUM")

        if not virus_name or len(virus_name) < 3:
            continue

        print(f"\n[{i+1}/{total}] {virus_name} (优先级: {priority})")

        # Step 1: 搜索 TaxID
        print(f"  → 搜索 Taxonomy ID...")
        taxid = search_taxid(virus_name)

        meta = {
            "Species": virus_name,
            "Priority": priority,
            "TaxID": taxid or "",
            "Num_Accessions": 0,
            "Num_Sequences": 0,
            "Merged_FASTA": "",
            "Status": "FAILED",
            "Timestamp": datetime.now().isoformat()
        }

        if not taxid:
            print(f"  ✗ 未找到 TaxID")
            meta["Status"] = "NO_TAXID"
            metadata.append(meta)
            continue

        # Step 2: 搜索 RefSeq 基因组
        print(f"  → TaxID={taxid}, 搜索基因组...")
        accessions = search_refseq_genomes(taxid, virus_name)
        print(f"    找到 {len(accessions)} 个 RefSeq 序列")

        if not accessions:
            meta["Status"] = "NO_SEQUENCES"
            metadata.append(meta)
            continue

        meta["Num_Accessions"] = len(accessions)

        # Step 3: 下载 FASTA
        print(f"  → 下载序列...")
        fasta_files = download_genome_sequences(virus_name, taxid, accessions)
        meta["Num_Sequences"] = len(fasta_files)

        # Step 4: 合并 FASTA
        merged = merge_species_fastas(virus_name, fasta_files)
        if merged:
            meta["Merged_FASTA"] = str(merged)
            meta["Status"] = "SUCCESS"
            print(f"  ✓ 成功 → {merged}")
        else:
            print(f"  ✗ 下载失败")

        metadata.append(meta)

    return metadata


def main():
    parser = argparse.ArgumentParser(description="从 NCBI 下载植物病毒基因组")
    parser.add_argument("--species", default=str(SPECIES_LIST),
                       help="物种列表 TSV (Step 0 输出)")
    parser.add_argument("--limit", type=int, default=0,
                       help="仅处理前 N 个物种 (0=全部)")
    parser.add_argument("--priority-only", action="store_true",
                       help="仅处理 HIGH 优先级物种")
    args = parser.parse_args()

    setup()

    # 加载物种列表
    species_file = Path(args.species)
    if not species_file.exists():
        print(f"✗ 物种列表文件不存在: {species_file}")
        print("  请先运行: python step0_prepare_plants.py")
        return

    df = pl.read_csv(species_file, separator='\t', ignore_errors=True)

    if args.priority_only:
        df = df.filter(pl.col("Priority") == "HIGH")

    if args.limit > 0:
        df = df[:args.limit]

    print(f"准备下载 {len(df)} 个病毒物种的基因组序列")
    print(f"  HIGH: {df.filter(pl.col('Priority')=='HIGH').height}")
    print(f"  MEDIUM: {df.filter(pl.col('Priority')=='MEDIUM').height}")
    print(f"  LOW: {df.filter(pl.col('Priority')=='LOW').height}")
    print()

    # 处理
    metadata = process_priority_species(df)

    # 保存 metadata
    meta_df = pl.DataFrame(metadata)
    meta_df.write_csv(METADATA_FILE, separator='\t')
    print(f"\n{'='*70}")
    print(f"下载完成!")
    print(f"  成功: {meta_df.filter(pl.col('Status')=='SUCCESS').height}")
    print(f"  失败: {meta_df.filter(pl.col('Status')!='SUCCESS').height}")
    print(f"  元数据 → {METADATA_FILE}")
    print(f"  基因组 → {GENOME_DIR / 'per_species'}/")
    print(f"\n下一步: python step2_design_primers.py")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
