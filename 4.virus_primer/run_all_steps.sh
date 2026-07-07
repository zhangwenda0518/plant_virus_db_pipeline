#!/usr/bin/env bash
# ============================================================================
# 植物病毒引物设计完整流程
# 用法: bash run_all_steps.sh
# ============================================================================
set -e

BIN=~/bin
DB_DIR=~/plant_virus_db/2.plant-virus.db
FULL_INFO=$DB_DIR/E-metadata/Plant_Virus_Full.Info.tsv
THREADS=60

SPLIT=~/split_species_new
DESIGN=~/designed_primers_new

echo "================================================================"
echo "  Step 1: 解析数据库, 按物种拆分 FASTA + 生成 species_index.tsv"
echo "================================================================"
python $BIN/step1_parse_db.py \
  --local-db "$DB_DIR" \
  --full-info "$FULL_INFO" \
  -o "$SPLIT"

echo ""
echo "================================================================"
echo "  Step 2: 设计引物 (PCR / qPCR / Degenerate / Tiled)"
echo "================================================================"
mkdir -p "$DESIGN"

# 获取所有 species FASTA
FASTA_LIST=$(ls "$SPLIT/species/"*.fasta 2>/dev/null | head -7000 | paste -sd, -)
python $BIN/step2_design_primers.py \
  --fasta "$FASTA_LIST" \
  --output "$DESIGN" \
  --threads $THREADS

echo ""
echo "================================================================"
echo "  Step 3: 引物验证 (二聚体 + GC/Tm + BLAST)"
echo "================================================================"

# 用病毒 FASTA 构建小 BLAST 库 (秒级加载)
VIRUS_DB=~/database/virus_targets_db/virus_new
cat "$SPLIT/species/"*.fasta > ~/database/all_virus_new.fasta
mkdir -p ~/database/virus_targets_db
makeblastdb -in ~/database/all_virus_new.fasta -dbtype nucl -out "$VIRUS_DB"

python $BIN/step3_validate_primers.py \
  --input "$DESIGN/all_primers.tsv" \
  --output "$DESIGN/all_primers_validated.tsv" \
  --blast-db "$VIRUS_DB" \
  --blast-batch 5000 --blast-jobs 1 --threads $THREADS

echo ""
echo "================================================================"
echo "  Step 4: 构建 SQLite 数据库"
echo "================================================================"
python $BIN/step4_build_database.py \
  --primers "$DESIGN/all_primers_validated.tsv" \
  --species-index "$SPLIT/species_index.tsv" \
  --db ~/primer_database_new.db

echo ""
echo "================================================================"
echo "  Step 5: 启动 Web 服务器"
echo "================================================================"
echo "  手动启动: python $BIN/step5_web_server.py --db ~/primer_database_new.db"
echo ""
echo "  或导出到静态网站:"
echo "    python $BIN/export_primers_static.py --input $DESIGN/all_primers_validated.tsv --output ~/primers_data/ --species-index $SPLIT/species_index.tsv --db ~/primer_database_new.db"
echo ""
echo "================================================================"
echo "  全流程完成!"
echo "================================================================"
