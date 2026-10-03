#!/usr/bin/env bash
# ============================================================================
# 植物病毒引物设计完整流程
# 用法: bash run_all_steps.sh
#
# 可在命令行/环境变量覆盖的参数 (见下方变量区):
#   MAX_SPECIES  step2 处理的物种数上限 (0=全部, 走 step2 --limit)
#   PLANT_DB     植物 BLAST 库前缀 (step3 --blast-db-plant 脱靶检测, 必需)
#   THREADS      线程数
# ============================================================================
set -e

BIN=~/bin
DB_DIR=~/plant_virus_db/2.plant-virus.db
FULL_INFO=$DB_DIR/E-metadata/Plant_Virus_Full.Info.tsv
THREADS=${THREADS:-60}

SPLIT=~/split_species_new
DESIGN=~/designed_primers_new

# ── step2 物种数上限 ──
# 旧版用 `ls ... | head -7000` 硬编码静默截断 (按文件名字母序, 还会丢掉长名物种);
# 现改为显式变量, 经 step2 自身的 --limit 生效 (按序列数从多到少取前 N 个物种)。
# 例: MAX_SPECIES=2000 bash run_all_steps.sh    # 0 或不设 = 全部
MAX_SPECIES=${MAX_SPECIES:-0}

# ── step3 植物脱靶 BLAST 库 ──
# 审计确认: 主流程原先不传 --blast-db-plant → 植物交叉反应验证根本不执行;
# 且 --skip-blast 时旧输出无验证列。此处改为显式必需, 缺失即报错退出 (不静默跳过)。
# 注意用 ${PLANT_DB-...} (非 :-): 显式置空会被视为"未设置"而报错, 而不是回退默认路径。
# 例: PLANT_DB=~/database/plant_targets_db/plants bash run_all_steps.sh
PLANT_DB=${PLANT_DB-~/database/plant_targets_db/plants}

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

# step2 只接受 --species-dir (旧版误传不存在的 --fasta → argparse 报错, set -e 直接终止)
LIMIT_ARG=()
if [ "$MAX_SPECIES" -gt 0 ] 2>/dev/null; then
  LIMIT_ARG=(--limit "$MAX_SPECIES")
  echo "  (物种数上限: $MAX_SPECIES, 其余物种本次跳过)"
fi
python $BIN/step2_design_primers.py \
  --species-dir "$SPLIT/species" \
  --output "$DESIGN" \
  --threads $THREADS \
  "${LIMIT_ARG[@]}"

echo ""
echo "================================================================"
echo "  Step 3: 引物验证 (二聚体 + GC/Tm + BLAST 病毒/植物双库)"
echo "================================================================"

# 用病毒 FASTA 构建小 BLAST 库 (秒级加载)
VIRUS_DB=~/database/virus_targets_db/virus_new
cat "$SPLIT/species/"*.fasta > ~/database/all_virus_new.fasta
mkdir -p ~/database/virus_targets_db
makeblastdb -in ~/database/all_virus_new.fasta -dbtype nucl -out "$VIRUS_DB"

# 校验植物库存在 (变量缺失/库不存在时明确报错, 不静默跳过脱靶验证)
if [ -z "$PLANT_DB" ]; then
  echo "✗ PLANT_DB 未设置: 植物脱靶 BLAST 库是 step3 交叉反应验证的必需输入, 拒绝静默跳过。" >&2
  echo "  用法: PLANT_DB=/path/to/plant_targets_db/plants bash run_all_steps.sh" >&2
  echo "  确实没有植物库时请直接调用 step3 --skip-blast, 并接受 UNVALIDATED 输出。" >&2
  exit 1
fi
if [ ! -f "${PLANT_DB}.nin" ] && [ ! -f "${PLANT_DB}.ndb" ]; then
  echo "✗ 植物 BLAST 库不存在: ${PLANT_DB}.nin/.ndb" >&2
  echo "  先构建: makeblastdb -in plants.fasta -dbtype nucl -out $PLANT_DB" >&2
  exit 1
fi

python $BIN/step3_validate_primers.py \
  --input "$DESIGN/all_primers.tsv" \
  --output "$DESIGN/all_primers_validated.tsv" \
  --blast-db "$VIRUS_DB" \
  --blast-db-plant "$PLANT_DB" \
  --species-dir "$SPLIT/species" \
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
