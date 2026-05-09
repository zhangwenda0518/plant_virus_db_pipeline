#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 植物病毒基因组数据库构建 Pipeline — 一键执行脚本
# ============================================================
# 用法:
#   bash run_all.sh                        # 使用默认路径运行
#   bash run_all.sh --help                 # 显示帮助信息
#   WORK_DIR=/data/virus bash run_all.sh   # 通过环境变量自定义路径
#
# 断点续跑: 每个阶段会检查产物是否已存在，已存在的步骤自动跳过
# 日志: 所有 stdout/stderr 同时输出到终端和 00_logs/ 目录
# ============================================================

# ==================== 帮助信息 ====================
show_help() {
    cat << 'HELP'
┌──────────────────────────────────────────────────────────────┐
│         植物病毒参考基因组数据库构建 Pipeline                  │
│         Plant Virus Reference Genome Database Construction    │
├──────────────────────────────────────────────────────────────┤
│ 用法:                                                         │
│   bash run_all.sh                             直接运行        │
│   bash run_all.sh --help                      显示此帮助      │
│   bash run_all.sh --check                     仅检查前置条件  │
├──────────────────────────────────────────────────────────────┤
│ 环境变量 (运行前按需设置):                                    │
│                                                              │
│   WORK_DIR        工作目录, 所有产物输出位置                   │
│                   默认: $HOME/plant_virus_db                  │
│   RAW_DIR         原始下载数据目录                            │
│                   默认: $WORK_DIR/raw_data                    │
│   DATABASE_DIR    本地数据库根目录                            │
│                   默认: $HOME/database                        │
│   TAXONOMY_DIR    NCBI Taxonomy 数据目录                      │
│                   默认: $DATABASE_DIR/taxonomy                │
│   EMAIL           NCBI API 邮箱 (必填)                         │
│   API_KEY         NCBI API Key (可选, 提升下载速度)            │
│   NCPU            通用并行线程数 默认: 60                      │
│   MMSEQS_THREADS  MMseqs2 聚类线程数 默认: 32                  │
├──────────────────────────────────────────────────────────────┤
│ 前置条件 (运行前须就位):                                      │
│                                                              │
│   $RAW_DIR/AllNucleotide.fa.gz      NCBI 全量病毒序列         │
│   $RAW_DIR/AllNuclMetadata.csv      NCBI 病毒元数据           │
│   $RAW_DIR/VHostMetadata.tsv        NCBI 病毒宿主关联表       │
│   $RAW_DIR/virushostdb.tsv          KEGG Virus-Host DB        │
│   $RAW_DIR/VMR_MSL41.*.xlsx         ICTV VMR 电子表格         │
│   $TAXONOMY_DIR/names.dmp           NCBI 物种名称映射         │
│   $TAXONOMY_DIR/nucl_gb.accession2taxid   Accession→TaxID 映射│
├──────────────────────────────────────────────────────────────┤
│ 输出产物 (按阶段分目录):                                      │
│                                                              │
│   $WORK_DIR/00_logs/               ★ 运行日志                 │
│   $WORK_DIR/01_merge/              A 元数据整合产物            │
│   $WORK_DIR/02_ictv/               B ICTV 宿主拆分产物         │
│   $WORK_DIR/03_host/               C 宿主分类产物              │
│   $WORK_DIR/04_sequences/          D 植物病毒序列              │
│   $WORK_DIR/05_metadata/           E 完整元数据                │
│   $WORK_DIR/06_dedup/              F 去冗余产物                │
│   $WORK_DIR/07_cluster/            ★ 最终参考基因组            │
├──────────────────────────────────────────────────────────────┤
│ 运行示例:                                                     │
│                                                              │
│   # 最小配置                                                   │
│   EMAIL="me@qq.com" bash run_all.sh                           │
│                                                              │
│   # 完整配置                                                   │
│   WORK_DIR=/data/plant_virus \                               │
│   RAW_DIR=/data/raw \                                        │
│   EMAIL="me@qq.com" \                                        │
│   API_KEY="abc123" \                                         │
│   NCPU=30 \                                                  │
│   bash run_all.sh                                             │
│                                                              │
│   # 断点续跑 (中断后直接重新执行)                              │
│   bash run_all.sh    # 已完成步骤自动跳过                      │
└──────────────────────────────────────────────────────────────┘
HELP
    exit 0
}

# 处理命令行参数
case "${1:-}" in
    --help|-h)  show_help ;;
    --check)    CHECK_ONLY=1 ;;
    "")         ;;  # 正常运行
    *)          echo "未知参数: $1 (使用 --help 查看帮助)"; exit 1 ;;
esac

# ==================== CONFIG ====================
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK_DIR="${WORK_DIR:-$HOME/plant_virus_db}"
RAW_DIR="${RAW_DIR:-$WORK_DIR/raw_data}"
DATABASE_DIR="${DATABASE_DIR:-$HOME/database}"
TAXONOMY_DIR="${TAXONOMY_DIR:-$DATABASE_DIR/taxonomy}"
TAXONKIT_BIN="${TAXONKIT_BIN:-taxonkit}"
NCPU="${NCPU:-60}"
MMSEQS_THREADS="${MMSEQS_THREADS:-32}"
EMAIL="${EMAIL:-your_email@example.com}"
API_KEY="${API_KEY:-}"

# 阶段产物目录 + 日志目录
mkdir -p "$WORK_DIR"/{00_logs,01_merge,02_ictv,03_host,04_sequences,05_metadata,06_dedup,07_cluster}
LOG_DIR="$WORK_DIR/00_logs"
touch "$LOG_DIR/pipeline.log"

# 原始输入
ALLNUCL_FA="$RAW_DIR/AllNucleotide.fa.gz"
ALLNUCL_CSV="$RAW_DIR/AllNuclMetadata.csv"
VHOST_TSV="$RAW_DIR/VHostMetadata.tsv"
VHDB_TSV="$RAW_DIR/virushostdb.tsv"
VMR_XLSX="$RAW_DIR/VMR_MSL41.v1.20260320.xlsx"
TAXID_DB="$TAXONOMY_DIR/nucl_gb.accession2taxid"
NAMES_DMP="$TAXONOMY_DIR/names.dmp"

# ==================== UTILS ====================
log(){
    local msg="[$(date '+%H:%M:%S')] $*"
    echo "$msg" | tee -a "$LOG_DIR/pipeline.log"
}
check(){
    if [ ! -e "$1" ]; then
        log "✗ 缺少: $1"
        exit 1
    fi
}
done_or_skip(){
    if [ -f "$1" ]; then
        log "⊙ 跳过 [$2] — 产物已存在"
        return 0
    fi
    return 1
}
# run 将脚本 stdout/stderr 同时写入终端和阶段日志
# 返回码非零时打印 FAILED，但不会中断整个 pipeline (set +e 包裹)
run(){
    local step="$1" out="$2"; shift 2
    local stage_log="$LOG_DIR/${step}.log"
    done_or_skip "$out" "$step" && return 0
    log "▶ 开始 [$step]"
    set +e
    "$@" >> >(tee -a "$stage_log") 2>> >(tee -a "$stage_log" >&2)
    local rc=$?
    set -e
    if [ $rc -eq 0 ]; then
        log "✓ [$step] 完成 → $out"
    else
        log "✗ [$step] 失败 (返回码=$rc)，详见 $stage_log"
    fi
}

# ==================== 前置检查 ====================
echo "============================================"
echo "  植物病毒基因组数据库构建 Pipeline"
echo "============================================"
log "工作目录:   $WORK_DIR"
log "原始数据:   $RAW_DIR"
log "数据库目录: $DATABASE_DIR"
log "脚本目录:   $BIN_DIR"
log "Email:      $EMAIL"
log "并行线程:   $NCPU (通用) / $MMSEQS_THREADS (MMseqs)"
echo ""

log "检查原始数据文件..."
missing=0
check_input(){
    if [ -e "$1" ]; then
        log "  ✓ 存在: $1"
    else
        log "  ✗ 缺失: $1"
        missing=$((missing + 1))
    fi
}
check_input "$ALLNUCL_FA"
check_input "$ALLNUCL_CSV"
check_input "$VHOST_TSV"
check_input "$VHDB_TSV"
check_input "$VMR_XLSX"
check_input "$TAXID_DB"
check_input "$NAMES_DMP"

if [ "$missing" -gt 0 ]; then
    log "✗ 缺失 $missing 个必要文件, 请先下载 (详见 README: 原始数据下载)"
    exit 1
fi
log "✓ 全部 $missing 个必要文件已就位"

# --check 模式: 仅检查前置条件后退出
if [ "${CHECK_ONLY:-0}" = "1" ]; then
    log "--check 模式: 前置条件检查通过, 退出"
    exit 0
fi
log "开始执行 Pipeline ..."

# ============================================================
# 阶段 A: 元数据整合
# ============================================================
log "========== 阶段 A: 元数据整合 =========="

run "A1-数据质检" "$WORK_DIR/01_merge/summary.csv" \
    python "$BIN_DIR/A1_check_data.py" -i "$VHOST_TSV" -o "$WORK_DIR/01_merge/summary.csv"

run "A2-VHDB+NCBI合并" "$WORK_DIR/01_merge/Merged.VHostMetadata.tsv" \
    python "$BIN_DIR/A2_merge_vhost_vhdb.py" \
        --vhdb "$VHDB_TSV" --ncbi "$VHOST_TSV" \
        -o "$WORK_DIR/01_merge/Merged.VHostMetadata.tsv"

run "A1b-合并后质检" "$WORK_DIR/01_merge/merge_summary.csv" \
    python "$BIN_DIR/A1_check_data.py" -i "$WORK_DIR/01_merge/Merged.VHostMetadata.tsv" \
        -o "$WORK_DIR/01_merge/merge_summary.csv"

run "A3-宿主补全" "$WORK_DIR/01_merge/Merged.VHostMetadata.imputer.tsv" \
    python "$BIN_DIR/A3_vhost_imputer.py" \
        -i "$WORK_DIR/01_merge/Merged.VHostMetadata.tsv" \
        -o "$WORK_DIR/01_merge/Merged.VHostMetadata.imputer.tsv"

run "A4-添加谱系" "$WORK_DIR/01_merge/Merged.VHostMetadata.lineage.tsv" \
    python "$BIN_DIR/A4_add_lineage.py" \
        "$WORK_DIR/01_merge/Merged.VHostMetadata.imputer.tsv" \
        -o "$WORK_DIR/01_merge/Merged.VHostMetadata.lineage.tsv" \
        --processes "$NCPU" --data-dir "$TAXONOMY_DIR"

# ============================================================
# 阶段 B: ICTV 宿主拆分
# ============================================================
log "========== 阶段 B: ICTV 宿主拆分 =========="

run "B1-Excel转TSV" "$WORK_DIR/02_ictv/VMR_MSL41.tsv" \
    bash -c "xlsx2csv -s 2 '$VMR_XLSX' | csvformat -T > '$WORK_DIR/02_ictv/VMR_MSL41.tsv'"

run "B2-VMR宿主拆分" "$WORK_DIR/02_ictv/VMR_Split_By_Host/VMR_Plant.tsv" \
    python "$BIN_DIR/B1_vmr_split_by_host.py" \
        --vmr "$WORK_DIR/02_ictv/VMR_MSL41.tsv" \
        --vhost "$WORK_DIR/01_merge/Merged.VHostMetadata.lineage.tsv" \
        --out_dir "$WORK_DIR/02_ictv/VMR_Split_By_Host"

# ============================================================
# 阶段 C: 宿主信息整合
# ============================================================
log "========== 阶段 C: 宿主信息整合 =========="

run "C1-宿主信息提取" "$WORK_DIR/03_host/host_extract/Final_Virus_Host_Lineage.tsv" \
    python "$BIN_DIR/C1_virus_host_info_extract.py" \
        --all_nucl "$ALLNUCL_CSV" \
        --vhost "$WORK_DIR/01_merge/Merged.VHostMetadata.lineage.tsv" \
        --taxid_db "$TAXID_DB" \
        --outdir "$WORK_DIR/03_host/host_extract" \
        --api "$API_KEY" --batch_size 200

run "C2-宿主分类" "$WORK_DIR/03_host/VHostMetadata/Plant.tsv" \
    bash -c "POLARS_MAX_THREADS=$MMSEQS_THREADS python '$BIN_DIR/C2_classify_by_host.py' \
        --vhost '$WORK_DIR/03_host/host_extract/Final_Virus_Host_Lineage.tsv' \
        --allnucl '$ALLNUCL_CSV' \
        --out_dir '$WORK_DIR/03_host/VHostMetadata'"

# ============================================================
# 阶段 D: 植物病毒序列获取
# ============================================================
log "========== 阶段 D: 序列获取 =========="

run "D1-比对提取FASTA" "$WORK_DIR/04_sequences/Plant_virus_db/Plant_Extracted_Sequences.fasta" \
    python "$BIN_DIR/D1_extract_and_check_fasta.py" \
        --tsv "$WORK_DIR/03_host/VHostMetadata/Plant.tsv" \
        --fasta "$ALLNUCL_FA" \
        --out_dir "$WORK_DIR/04_sequences/Plant_virus_db"

# D2: 仅在缺失列表非空时运行
if [ -f "$WORK_DIR/04_sequences/Plant_virus_db/Plant_missing_accessions.txt" ] && \
   [ -s "$WORK_DIR/04_sequences/Plant_virus_db/Plant_missing_accessions.txt" ]; then
    run "D2-下载缺失序列" "$WORK_DIR/04_sequences/Plant_virus_db/Downloaded_Plant_Viruses.fasta" \
        python "$BIN_DIR/D2_download_missing.py" \
            -i "$WORK_DIR/04_sequences/Plant_virus_db/Plant_missing_accessions.txt" \
            -o "$WORK_DIR/04_sequences/Plant_virus_db/Downloaded_Plant_Viruses.fasta" \
            -k "$API_KEY" --resume
else
    log "⊙ 跳过 [D2] — 无缺失序列或列表为空"
fi

# D3: 合并 + 整理
if [ ! -f "$WORK_DIR/04_sequences/plant.virus.fasta" ]; then
    log "▶ 合并序列文件..."
    cd "$WORK_DIR/04_sequences/Plant_virus_db"
    cat Plant_Extracted_Sequences.fasta Downloaded_Plant_Viruses.fasta 2>/dev/null > "$WORK_DIR/04_sequences/plant.virus.fasta"
    sed -i 's/ .*//' "$WORK_DIR/04_sequences/plant.virus.fasta"
    grep ">" "$WORK_DIR/04_sequences/plant.virus.fasta" | sed 's/>//' > "$WORK_DIR/04_sequences/plant.virus.id"
    log "✓ 序列合并完成"
fi

# ============================================================
# 阶段 E: 元数据完善
# ============================================================
log "========== 阶段 E: 元数据完善 =========="

run "E1-提取元数据" "$WORK_DIR/05_metadata/Plant_Virus_Info.tsv" \
    python "$BIN_DIR/E1_extract_metadata.py" \
        -i "$WORK_DIR/04_sequences/plant.virus.id" \
        -m "$ALLNUCL_CSV" \
        -t "$TAXID_DB" \
        -o "$WORK_DIR/05_metadata/Plant_Virus_Info.tsv"

run "E2-获取拓扑结构" "$WORK_DIR/05_metadata/Plant_Virus_Topology_Molecule_Type.info.tsv" \
    python "$BIN_DIR/E2_fetch_topology.py" \
        --input "$WORK_DIR/04_sequences/plant.virus.id" \
        --output "$WORK_DIR/05_metadata/Plant_Virus_Topology_Molecule_Type.info.tsv" \
        --email "$EMAIL" --batch 200

run "E3-合并拓扑信息" "$WORK_DIR/05_metadata/Plant_Virus_Info.tsv" \
    python "$BIN_DIR/E3_merge_topology.py" \
        --seq "$WORK_DIR/05_metadata/Plant_Virus_Topology_Molecule_Type.info.tsv" \
        --plant "$WORK_DIR/05_metadata/Plant_Virus_Info.tsv"

run "E4-补充NCBI命名" "$WORK_DIR/05_metadata/Plant_Virus_Info.tsv" \
    python "$BIN_DIR/E4_add_ncbi_names.py" \
        --input "$WORK_DIR/05_metadata/Plant_Virus_Info.tsv" \
        --email "$EMAIL" \
        --names_dmp "$NAMES_DMP"

run "F1-基础统计" "$WORK_DIR/05_metadata/Plant_Virus_Info.summary" \
    python "$BIN_DIR/F1_analyze_summary.py" \
        --input "$WORK_DIR/05_metadata/Plant_Virus_Info.tsv" \
        > "$WORK_DIR/05_metadata/Plant_Virus_Info.summary"

# ============================================================
# 阶段 F: 分类与去冗余
# ============================================================
log "========== 阶段 F: 分类与去冗余 =========="

run "F2-节段分类拆分" "$WORK_DIR/06_dedup/split_results/All_Classified_Virus_Info.tsv" \
    python "$BIN_DIR/F2_classify_segmented.py" \
        -i "$WORK_DIR/05_metadata/Plant_Virus_Info.tsv" \
        --vmr "$WORK_DIR/02_ictv/VMR_MSL41.tsv" \
        -f "$WORK_DIR/04_sequences/plant.virus.fasta" \
        -o "$WORK_DIR/06_dedup/split_results" \
        --taxid-tsv "$TAXID_DB"

run "F3-元数据去重" "$WORK_DIR/06_dedup/virus.dedup/Final_Deduplicated_Info.tsv" \
    python "$BIN_DIR/F3_metadata_dedup.py" \
        --info "$WORK_DIR/06_dedup/split_results/All_Classified_Virus_Info.tsv" \
        --fasta_dir "$WORK_DIR/06_dedup/split_results" \
        --out_dir "$WORK_DIR/06_dedup/virus.dedup"

# F4: 非节段去冗余
run "F4a-非节段去冗余" "$WORK_DIR/06_dedup/Final_DB_Build/nonsegmented_mmseqs_0.98.fasta" \
    python "$BIN_DIR/F4_seqkit_mmseqs_rescue.py" \
        -f "$WORK_DIR/06_dedup/virus.dedup/Final_NonSegmented_Deduplicated.fasta" \
        -i "$WORK_DIR/06_dedup/virus.dedup/Final_Deduplicated_Info.tsv" \
        -m nonsegmented -o "$WORK_DIR/06_dedup/Final_DB_Build" -t "$MMSEQS_THREADS"

# F4: 节段去冗余
run "F4b-节段去冗余" "$WORK_DIR/06_dedup/Final_DB_Build/segmented_mmseqs_0.98.fasta" \
    python "$BIN_DIR/F4_seqkit_mmseqs_rescue.py" \
        -f "$WORK_DIR/06_dedup/virus.dedup/Final_Segmented_Deduplicated.fasta" \
        -i "$WORK_DIR/06_dedup/virus.dedup/Final_Deduplicated_Info.tsv" \
        -m segmented -o "$WORK_DIR/06_dedup/Final_DB_Build" -t "$MMSEQS_THREADS"

# 合并最终代表性基因组
if [ ! -f "$WORK_DIR/06_dedup/plant.final.rmdup.fasta" ]; then
    log "▶ 合并非节段+节段最终序列..."
    cd "$WORK_DIR/06_dedup/Final_DB_Build"
    cat nonsegmented_mmseqs_0.98.fasta segmented_mmseqs_0.98.fasta > "$WORK_DIR/06_dedup/plant.final.rmdup.fasta"
    cat nonsegmented_mmseqs_0.98_info.tsv segmented_mmseqs_0.98_info.tsv | sed '2,${/^Accession/d;}' > "$WORK_DIR/06_dedup/plant.final.rmdup_info.tsv"
    grep ">" "$WORK_DIR/06_dedup/plant.final.rmdup.fasta" | sed 's/>//' > "$WORK_DIR/06_dedup/plant.final.rmdup.id"
    log "✓ 合并完成"
fi

# ============================================================
# 阶段 G: 最终聚类与评估
# ============================================================
log "========== 阶段 G: 最终聚类与评估 =========="

run "G1-SeqID→TaxID映射" "$WORK_DIR/07_cluster/seqid2taxid.map" \
    python "$BIN_DIR/G1_seqid_to_taxid.py" \
        -j 30 -b 100000 \
        --query-file "$WORK_DIR/06_dedup/plant.final.rmdup.id" \
        --map-file "$TAXID_DB" \
        -o "$WORK_DIR/07_cluster/seqid2taxid.map"

run "G2-vclust聚类" "$WORK_DIR/07_cluster/final.cluster.ref.fasta" \
    python "$BIN_DIR/G2_vclust_cluster.py" \
        --fasta "$WORK_DIR/06_dedup/plant.final.rmdup.fasta" \
        --info "$WORK_DIR/06_dedup/plant.final.rmdup_info.tsv" \
        --map "$WORK_DIR/07_cluster/seqid2taxid.map" \
        --out_tsv "$WORK_DIR/07_cluster/clusters_with_LCA.tsv" \
        --out_plot "$WORK_DIR/07_cluster/clusters.LCA_Distribution.png" \
        --out_fasta "$WORK_DIR/07_cluster/final.cluster.ref.fasta" \
        --out_taxid_clusters "$WORK_DIR/07_cluster/clusters.taxid.tsv" \
        --out_info "$WORK_DIR/07_cluster/final.cluster.ref_info.tsv"

run "G3-去冗余评估" "$WORK_DIR/07_cluster/derep.summary.tsv" \
    python "$BIN_DIR/G3_derep_evaluate.py" \
        --info "$WORK_DIR/06_dedup/split_results/All_Classified_Virus_Info.tsv" \
        --fasta_files \
            "$WORK_DIR/04_sequences/plant.virus.fasta" \
            "$WORK_DIR/06_dedup/plant.final.rmdup.fasta" \
            "$WORK_DIR/07_cluster/final.cluster.ref.fasta" \
            "$WORK_DIR/06_dedup/Final_DB_Build/nonsegmented_mmseqs_0.98.fasta" \
            "$WORK_DIR/06_dedup/Final_DB_Build/segmented_mmseqs_0.98.fasta" \
        -o "$WORK_DIR/07_cluster" \
        > "$WORK_DIR/07_cluster/derep.summary.tsv"

# G4: 基因覆盖度 (需要 pyrodigal-rv)
run "G4a-基因预测" "$WORK_DIR/07_cluster/virus.gene.gff3" \
    pyrodigal-rv -i "$WORK_DIR/07_cluster/final.cluster.ref.fasta" \
        -a "$WORK_DIR/07_cluster/virus.gene_pep.fasta" \
        -d "$WORK_DIR/07_cluster/virus.gene_nuc.fasta" \
        -o "$WORK_DIR/07_cluster/virus.gene.gff3" -j 120

run "G4b-覆盖度计算" "$WORK_DIR/07_cluster/virus_genes_cov.tsv" \
    python "$BIN_DIR/G4_gene_coverage.py" \
        --gff "$WORK_DIR/07_cluster/virus.gene.gff3" \
        --map "$WORK_DIR/07_cluster/seqid2taxid_len.map" \
        --out "$WORK_DIR/07_cluster/virus_genes_cov.tsv" \
        --unpredicted "$WORK_DIR/07_cluster/unpredicted_genes_cov.tsv"

# ============================================================
# 总结报告
# ============================================================
log "▶ 生成学术风格总结报告..."
python "$BIN_DIR/summarize_pipeline.py" --work-dir "$WORK_DIR" \
    | tee "$LOG_DIR/pipeline_summary.txt"
log "✓ 总结报告已保存 → $LOG_DIR/pipeline_summary.txt"

# ============================================================
# 完成
# ============================================================
echo ""
echo "============================================"
echo "  Pipeline 执行完毕"
echo "============================================"
echo "最终产物:"
echo "  序列:     $WORK_DIR/07_cluster/final.cluster.ref.fasta"
echo "  信息:     $WORK_DIR/07_cluster/final.cluster.ref_info.tsv"
echo "  覆盖度:   $WORK_DIR/07_cluster/virus_genes_cov.tsv"
echo "  评估报告: $WORK_DIR/07_cluster/derep.summary.tsv"
echo "  LCA 分布: $WORK_DIR/07_cluster/clusters.LCA_Distribution.png"
echo "  总结报告: $LOG_DIR/pipeline_summary.txt"
echo "============================================"
