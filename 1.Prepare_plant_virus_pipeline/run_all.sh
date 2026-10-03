#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 植物病毒基因组数据库构建 Pipeline — 一键执行脚本
# ============================================================
# 用法:
#   bash run_all.sh -e me@qq.com                           # 最小运行
#   bash run_all.sh -w /data/virus -e me@qq.com -k KEY     # 完整配置
#   bash run_all.sh --help                                 # 显示帮助
#
# 断点续跑: 每个阶段会检查产物是否已存在，已存在的步骤自动跳过
# 日志: 所有 stdout/stderr 同时输出到终端和 00_logs/ 目录
# ============================================================

# ==================== 参数解析 ====================
EMAIL_ARG=""
API_KEY_ARG=""
WORK_DIR_ARG=""
RAW_DIR_ARG=""
DATABASE_DIR_ARG=""
TAXONOMY_DIR_ARG=""
NCPU_ARG=""
MMSEQS_THREADS_ARG=""
TAXONKIT_BIN_ARG=""
CHECK_ONLY=""
AUDIT_ONLY=""          # --audit        : 只跑产物体检(只读)后退出, 不需要原始数据
NO_AUDIT=""            # --no-audit     : 跑完不做体检
STRICT_AUDIT=""        # --strict-audit : 体检出现 FAIL 时以非 0 退出码结束
FROM_STAGE=""          # --from F1      : 强制重跑该步骤及其后所有步骤

show_help() {
    cat << 'HELP'
┌──────────────────────────────────────────────────────────────┐
│         植物病毒参考基因组数据库构建 Pipeline                  │
│         Plant Virus Reference Genome Database Construction    │
├──────────────────────────────────────────────────────────────┤
│ 用法:                                                         │
│   bash run_all.sh -e <邮箱>                       最小运行    │
│   bash run_all.sh --help                          显示帮助    │
│   bash run_all.sh --check                         检查前置    │
├──────────────────────────────────────────────────────────────┤
│ 命令行参数:                                                   │
│                                                              │
│   -e, --email <EMAIL>          NCBI 邮箱 (必填)               │
│   -w, --work-dir <DIR>         工作目录                       │
│                                默认: $HOME/plant_virus_db     │
│   -r, --raw-dir <DIR>          原始数据目录                   │
│                                默认: <work_dir>/0.raw_data    │
│   -d, --db-dir <DIR>           本地数据库根目录               │
│                                默认: $HOME/database           │
│   -t, --taxonomy-dir <DIR>     NCBI Taxonomy 目录            │
│                                默认: <db_dir>/taxonomy        │
│   -k, --api-key <KEY>          NCBI API Key (提升频率限制)    │
│   -p, --ncpu <N>               通用并行数 默认: 60            │
│   -m, --mmseqs-threads <N>     MMseqs2 线程 默认: 32          │
│   --check                      仅检查前置条件, 不运行         │
│   -h, --help                   显示此帮助                     │
├──────────────────────────────────────────────────────────────┤
│ 前置输入文件 (须预先下载到位):                                │
│                                                              │
│   $RAW_DIR/AllNucleotide.fa.gz       NCBI 全量病毒序列        │
│   $RAW_DIR/AllNuclMetadata.csv       NCBI 病毒元数据          │
│   $RAW_DIR/VHostMetadata.tsv         NCBI 病毒宿主关联        │
│   $RAW_DIR/virushostdb.tsv           KEGG Virus-Host DB       │
│   $RAW_DIR/VMR_MSL41.*.xlsx          ICTV VMR 电子表格        │
│   $TAXONOMY_DIR/names.dmp            NCBI 物种名映射          │
│   $TAXONOMY_DIR/nucl_gb.accession2taxid  Accession→TaxID     │
├──────────────────────────────────────────────────────────────┤
│ 输出产物 (四大目录):                                          │
│                                                              │
│   $WORK_DIR/0.raw_data/             ★ 原始输入数据            │
│   $WORK_DIR/1.virus-host_db/        ★ 病毒-宿主数据库         │
│     ├── A-merge/                    阶段 A: 元数据整合        │
│     ├── B-ictv/                     阶段 B: ICTV VMR 拆分     │
│     └── C-host_classify/            阶段 C: 宿主分类+清洗      │
│         ├── VHostMetadata/          C2 粗分类                  │
│         └── classified_clean/       C4 ICTV多层清洗            │
│   $WORK_DIR/2.plant-virus.db/       ★ 植物病毒参考基因组      │
│     ├── D-sequences/                阶段 D: 序列获取          │
│     ├── E-metadata/                 阶段 E: 元数据完善        │
│     ├── F-dedup/                    阶段 F: 分类去冗余        │
│     └── G-cluster/                  阶段 G: 聚类评估          │
│   $WORK_DIR/3.final-ref-virus.db/   ★ 最终参考数据库(软链接)    │
│   $WORK_DIR/4.host_classify/        ★ 宿主分类研究 (C5-C9)       │
│   $WORK_DIR/5.virus.ref.build.db/   ★ 下游数据库构建             │
│   $WORK_DIR/6.logs/                 ★ 全部运行日志               │
├──────────────────────────────────────────────────────────────┤
│ 运行示例:                                                     │
│                                                              │
│   bash run_all.sh -e me@qq.com                                │
│   bash run_all.sh -w /data/virus -e me@qq.com -k mykey -p 30  │
│   bash run_all.sh --check                                     │
│   bash run_all.sh --audit  -w /data/virus                     │
│       ↑ 只跑产物体检(只读): 物种缺失/键分裂/缺段/计数为0 等    │
│   bash run_all.sh --strict-audit -w /data/virus               │
│   bash run_all.sh --from F1 -w /data/virus                    │
│       ↑ 强制重跑 F1 及其后所有步骤 (增量更新后"触发去冗余")    │
│       ↑ 体检 FAIL 时以非 0 退出码结束 (默认只提示)             │
└──────────────────────────────────────────────────────────────┘
HELP
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)       show_help ;;
        --check)         CHECK_ONLY=1; shift ;;
        --audit)         AUDIT_ONLY=1; shift ;;
        --no-audit)      NO_AUDIT=1; shift ;;
        --strict-audit)  STRICT_AUDIT=1; shift ;;
        --from)          FROM_STAGE="${2^^}"; shift 2 ;;
        -e|--email)      EMAIL_ARG="$2"; shift 2 ;;
        -k|--api-key)    API_KEY_ARG="$2"; shift 2 ;;
        -w|--work-dir)   WORK_DIR_ARG="$2"; shift 2 ;;
        -r|--raw-dir)    RAW_DIR_ARG="$2"; shift 2 ;;
        -d|--db-dir)     DATABASE_DIR_ARG="$2"; shift 2 ;;
        -t|--taxonomy-dir) TAXONOMY_DIR_ARG="$2"; shift 2 ;;
        --taxonkit)      TAXONKIT_BIN_ARG="$2"; shift 2 ;;
        -p|--ncpu)       NCPU_ARG="$2"; shift 2 ;;
        -m|--mmseqs-threads) MMSEQS_THREADS_ARG="$2"; shift 2 ;;
        *) echo "未知参数: $1 (使用 --help 查看帮助)"; exit 1 ;;
    esac
done

# ==================== 产物体检 (只读, 不改动任何数据) ====================
# 报告写到 <work>/7.audit/<时间戳>/ ; 会自动与"上一次运行的快照"对比:
# 整族消失的物种 / 重复 accession / 物种键分裂 / 缺段 / 计数静默为 0 等会显式列出。
# 默认只提示不中断 (warn-only); 只有 --strict-audit 才让 FAIL 影响退出码。
AUDIT_OUT=""
_audit_msg(){ if [ -n "${LOG_DIR:-}" ] && [ -d "${LOG_DIR:-}" ]; then log "$*"; else echo "[audit] $*"; fi; }
audit_report(){
    local wd="$1" raw="$2"
    local audit_root="$wd/7.audit"
    local out="$audit_root/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$out"
    AUDIT_OUT="$out"
    local args=(--work-dir "$wd" --out "$out" --auto-baseline-dir "$audit_root")
    if [ -f "$raw/VMR_MSL41.v1.20260320.xlsx" ]; then args+=(--vmr "$raw/VMR_MSL41.v1.20260320.xlsx"); fi
    if [ -f "$raw/genus_lens.tsv" ]; then args+=(--genus-lens "$raw/genus_lens.tsv"); fi
    if [ -n "${STRICT_AUDIT:-}" ]; then args+=(--strict); fi
    _audit_msg "▶ 产物体检(只读) → $out"
    python "$BIN_DIR/lib/audit.py" "${args[@]}" | tee "$out/console.log"
}

# --audit: 只做体检, 放在 CONFIG 之前 —— 不需要原始数据/分类学库, 也不去 realpath 这些路径
if [ "${AUDIT_ONLY:-0}" = "1" ]; then
    BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
    if [ ! -f "$BIN_DIR/lib/audit.py" ]; then
        echo "✗ 缺少 $BIN_DIR/lib/audit.py"; exit 1
    fi
    _A_WORK="${WORK_DIR_ARG:-${WORK_DIR:-$HOME/plant_virus_db}}"
    _A_WORK="$(cd "$_A_WORK" 2>/dev/null && pwd || echo "$_A_WORK")"
    if audit_report "$_A_WORK" "${RAW_DIR_ARG:-${RAW_DIR:-$_A_WORK/0.raw_data}}"; then exit 0; else exit 1; fi
fi

# ==================== CONFIG ====================
# 优先级: 命令行参数 > 环境变量 > 默认值
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
# 确保所有目录为绝对路径, run() 会 cd 到产物目录执行
WORK_DIR="$(realpath "${WORK_DIR_ARG:-${WORK_DIR:-$HOME/plant_virus_db}}")"
RAW_DIR="$(realpath "${RAW_DIR_ARG:-${RAW_DIR:-$WORK_DIR/0.raw_data}}")"
DATABASE_DIR="$(realpath "${DATABASE_DIR_ARG:-${DATABASE_DIR:-$HOME/database}}")"
TAXONOMY_DIR="$(realpath "${TAXONOMY_DIR_ARG:-${TAXONOMY_DIR:-$DATABASE_DIR/taxonomy}}")"
TAXONKIT_BIN="${TAXONKIT_BIN_ARG:-${TAXONKIT_BIN:-taxonkit}}"
NCPU="${NCPU_ARG:-${NCPU:-60}}"
MMSEQS_THREADS="${MMSEQS_THREADS_ARG:-${MMSEQS_THREADS:-32}}"
EMAIL="${EMAIL_ARG:-${EMAIL:-your_email@example.com}}"
API_KEY="${API_KEY_ARG:-${API_KEY:-}}"

# 产出目录结构
# 0.raw_data       原始输入 (用户手动下载)
# 1.virus-host_db  病毒-宿主数据库构建 (阶段 A+B+C)
# 2.plant-virus.db 植物病毒参考基因组 (阶段 D+E+F+G+H)
# 3.final-ref-virus.db 最终参考数据库 (软链接)
# 4.host_classify  宿主分类研究 (C5-C9 下游分析)
# 5.virus.ref.build.db 下游数据库构建 (build_virus_db)
# 6.logs           全部运行日志
VHOST_DIR="$WORK_DIR/1.virus-host_db"
PLANT_DIR="$WORK_DIR/2.plant-virus.db"
LOG_DIR="$WORK_DIR/6.logs"
RAW_INPUT_DIR="$WORK_DIR/0.raw_data"
mkdir -p "$LOG_DIR"
mkdir -p "$VHOST_DIR"/{A-merge,B-ictv,C-host_classify}
mkdir -p "$PLANT_DIR"/{D-sequences,E-metadata,F-dedup,G-cluster,H-virus_genes}
mkdir -p "$WORK_DIR"/4.host_classify
mkdir -p "$WORK_DIR"/5.virus.ref.build.db
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
# --from <STEP>: 强制重跑该步骤及其后全部步骤（字母序 + 数字序比较；解析失败则保守跳过强制）
_stage_rank(){ [[ "$1" =~ ^([A-Ga-g])([0-9]+) ]] && echo "${BASH_REMATCH[1]^^}${BASH_REMATCH[2]}" || echo ""; }
_should_force(){
    [ -n "${FROM_STAGE:-}" ] || return 1
    local cur; cur="$(_stage_rank "$1")" || true
    [ -n "$cur" ] || return 1
    local cf="${FROM_STAGE:0:1}" cn="${FROM_STAGE:1}" uf="${cur:0:1}" un="${cur:1}"
    case "$cn$un" in *[!0-9]*|"") return 1 ;; esac      # 非纯数字则不强制
    if [ "$uf" \> "$cf" ]; then return 0; fi
    if [ "$uf" = "$cf" ] && [ "$un" -ge "$cn" ]; then return 0; fi
    return 1
}
done_or_skip(){
    if _should_force "$2"; then
        log "⟳ [$2] 命中 --from $FROM_STAGE, 强制重跑"
        return 1
    fi
    if [ -s "$1" ]; then
        log "⊙ 跳过 [$2] — 产物已存在"
        return 0
    fi
    # 空文件视为未完成, 删除后重新执行
    if [ -f "$1" ]; then
        log "⊘ 产物为空, 重新执行 [$2]"
        rm -f "$1"
    fi
    return 1
}
# 检查上游依赖产物, 缺失时跳过当前步骤
need(){
    local dep="$1" step="$2"
    if [ ! -e "$dep" ]; then
        log "⊙ 跳过 [$step] — 上游产物缺失: $dep"
        return 1
    fi
    return 0
}

run(){
    local step="$1" out="$2"; shift 2
    local stage_log="$LOG_DIR/${step}.log"
    done_or_skip "$out" "$step" && return 0
    log "▶ 开始 [$step]"
    # 在产物所在目录执行, 避免临时文件散落在 CWD
    local run_dir; run_dir="$(dirname "$out")"
    mkdir -p "$run_dir"
    (cd "$run_dir" && "$@") >> >(tee -a "$stage_log") 2>> >(tee -a "$stage_log" >&2)
    log "✓ [$step] 完成 → $out"
}

# ==================== 规范层（物种名 / 节段名；只增列，不改原文件）====================
# 物种名：VMR accession 锚点 → 别名 → 同科种加词；节段名：按物种内主导风格 + 不降级 + 信息不丢失。
# 产物写入 <work>/7.canonical/ （<info>.canon.tsv 与 <info>.segnorm.tsv），原文件不动。
# 失败只告警，不影响主流程与已产出的数据。
canonicalize_ref(){
    local info="$1" out="$WORK_DIR/7.canonical" cur="$1"
    mkdir -p "$out"
    if [ -n "${VMR_XLSX:-}" ] && [ -f "$VMR_XLSX" ]; then
        if python "$BIN_DIR/lib/build_species_canonical.py" --info "$cur" --vmr "$VMR_XLSX" --out "$out" --apply >>"$out/canonical.log" 2>&1; then
            local cand="$out/$(basename "$cur" .tsv).canon.tsv"
            if [ -f "$cand" ]; then cur="$cand"; fi
        else
            _audit_msg "⚠ 物种名规范层失败(不影响主流程)，详见 $out/canonical.log"
        fi
    fi
    if python "$BIN_DIR/lib/build_segment_canonical.py" --info "$cur" --out "$out" --apply >>"$out/canonical.log" 2>&1; then
        _audit_msg "✓ 规范层产物 → $out/（物种名 + 节段名，只增列；复核后再替换正式 Info）"
    else
        _audit_msg "⚠ 节段名规范层失败(不影响主流程)，详见 $out/canonical.log"
    fi
    return 0
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
log "✓ 全部必要文件已就位"

# --check 模式: 仅检查前置条件后退出
if [ "${CHECK_ONLY:-0}" = "1" ]; then
    log "--check 模式: 前置条件检查通过, 退出"
    exit 0
fi
log "开始执行 Pipeline ..."

# ============================================================
# 阶段 A: 元数据整合 → 1.virus-host_db/A-merge/
# ============================================================
log "========== 阶段 A: 元数据整合 =========="

run "A1-数据质检" "$VHOST_DIR/A-merge/summary.csv" \
    python "$BIN_DIR/A1_check_data.py" -i "$VHOST_TSV" -o "$VHOST_DIR/A-merge/summary.csv"

run "A2-VHDB+NCBI合并" "$VHOST_DIR/A-merge/Merged.VHostMetadata.tsv" \
    python "$BIN_DIR/A2_merge_vhost_vhdb.py" \
        --vhdb "$VHDB_TSV" --ncbi "$VHOST_TSV" \
        -o "$VHOST_DIR/A-merge/Merged.VHostMetadata.tsv"

run "A1b-合并后质检" "$VHOST_DIR/A-merge/merge_summary.csv" \
    python "$BIN_DIR/A1_check_data.py" -i "$VHOST_DIR/A-merge/Merged.VHostMetadata.tsv" \
        -o "$VHOST_DIR/A-merge/merge_summary.csv"

run "A3-宿主补全" "$VHOST_DIR/A-merge/Merged.VHostMetadata.imputer.tsv" \
    python "$BIN_DIR/A3_vhost_imputer.py" \
        -i "$VHOST_DIR/A-merge/Merged.VHostMetadata.tsv" \
        -o "$VHOST_DIR/A-merge/Merged.VHostMetadata.imputer.tsv"

run "A4-添加谱系" "$VHOST_DIR/A-merge/Merged.VHostMetadata.lineage.tsv" \
    python "$BIN_DIR/A4_add_lineage.py" \
        "$VHOST_DIR/A-merge/Merged.VHostMetadata.imputer.tsv" \
        -o "$VHOST_DIR/A-merge/Merged.VHostMetadata.lineage.tsv" \
        --processes "$NCPU" --data-dir "$TAXONOMY_DIR"

# ============================================================
# 阶段 B: ICTV 宿主拆分 → 1.virus-host_db/B-ictv/
# ============================================================
log "========== 阶段 B: ICTV 宿主拆分 =========="

run "B1-Excel转TSV" "$VHOST_DIR/B-ictv/VMR_MSL41.tsv" \
    bash -c "xlsx2csv -s 2 '$VMR_XLSX' | csvformat -T > '$VHOST_DIR/B-ictv/VMR_MSL41.tsv'"

run "B2-VMR宿主拆分" "$VHOST_DIR/B-ictv/VMR_Split_By_Host/VMR_Plant.tsv" \
    python "$BIN_DIR/B1_vmr_split_by_host.py" \
        --vmr "$VHOST_DIR/B-ictv/VMR_MSL41.tsv" \
        --vhost "$VHOST_DIR/A-merge/Merged.VHostMetadata.lineage.tsv" \
        --out_dir "$VHOST_DIR/B-ictv/VMR_Split_By_Host"

# ============================================================
# 阶段 C: 宿主信息整合 + 多层清洗 → 1.virus-host_db/C-host_classify/
# ============================================================
log "========== 阶段 C: 宿主分类与清洗 =========="

run "C1-宿主信息提取" "$VHOST_DIR/C-host_classify/host_extract/Final_Virus_Host_Lineage.tsv" \
    python "$BIN_DIR/C1_virus_host_info_extract.py" \
        --all_nucl "$ALLNUCL_CSV" \
        --vhost "$VHOST_DIR/A-merge/Merged.VHostMetadata.lineage.tsv" \
        --taxid_db "$TAXID_DB" \
        --outdir "$VHOST_DIR/C-host_classify/host_extract" \
        --api "$API_KEY" --batch_size 200

run "C2-宿主分类" "$VHOST_DIR/C-host_classify/VHostMetadata/Plant.tsv" \
    bash -c "POLARS_MAX_THREADS=$MMSEQS_THREADS python '$BIN_DIR/C2_classify_by_host.py' \
        --vhost '$VHOST_DIR/C-host_classify/host_extract/Final_Virus_Host_Lineage.tsv' \
        --allnucl '$ALLNUCL_CSV' \
        --out_dir '$VHOST_DIR/C-host_classify/VHostMetadata'"

run "C3a-藻类拆分" "$VHOST_DIR/C-host_classify/VHostMetadata/Algae.tsv" \
    python "$BIN_DIR/C3a_algae_split.py" \
        -i "$VHOST_DIR/C-host_classify/VHostMetadata" \
        -o "$VHOST_DIR/C-host_classify/VHostMetadata"

run "C3b-动物宿主细分" "$VHOST_DIR/C-host_classify/VHostMetadata/Insecta.tsv" \
    python "$BIN_DIR/C3b_animal_subsplit.py" \
        -i "$VHOST_DIR/C-host_classify/VHostMetadata/Animal.tsv" \
        -o "$VHOST_DIR/C-host_classify/VHostMetadata"

VMR_TSV="$VHOST_DIR/B-ictv/VMR_MSL41.tsv"
VHOSTMETA_DIR="$VHOST_DIR/C-host_classify/VHostMetadata"
CLASSIFIED_DIR="$VHOST_DIR/C-host_classify/classified_clean"

run "C4-多类别清洗" "$CLASSIFIED_DIR/Plant.tsv" \
    python "$BIN_DIR/C4_clean_all_tsvs.py" \
        -i "$VHOSTMETA_DIR" \
        -o "$CLASSIFIED_DIR" \
        -v "$VMR_TSV"

# ============================================================
# 阶段 D: 序列获取 → 2.plant-virus.db/D-sequences/
# ============================================================
log "========== 阶段 D: 序列获取 =========="

run "D1-比对提取FASTA" "$PLANT_DIR/D-sequences/Plant_Extracted_Sequences.fasta" \
    python "$BIN_DIR/D1_extract_and_check_fasta.py" \
        --tsv "$CLASSIFIED_DIR/Plant.tsv" \
        --fasta "$ALLNUCL_FA" \
        --out_dir "$PLANT_DIR/D-sequences"

# D2: 仅在缺失列表非空时运行
if [ -f "$PLANT_DIR/D-sequences/Plant_missing_accessions.txt" ] && \
   [ -s "$PLANT_DIR/D-sequences/Plant_missing_accessions.txt" ]; then
    run "D2-下载缺失序列" "$PLANT_DIR/D-sequences/Downloaded_Plant_Viruses.fasta" \
        python "$BIN_DIR/D2_download_missing.py" \
            -i "$PLANT_DIR/D-sequences/Plant_missing_accessions.txt" \
            -o "$PLANT_DIR/D-sequences/Downloaded_Plant_Viruses.fasta" \
            -k "$API_KEY" --resume
else
    log "⊙ 跳过 [D2] — 无缺失序列或列表为空"
fi

# D3: 合并 (使用绝对路径, 避免 cd 失败)
MERGED_FASTA="$PLANT_DIR/D-sequences/Plant_Virus_Full.fasta"
MERGED_IDS="$PLANT_DIR/D-sequences/plant.virus.id"
EXTRACTED_FA="$PLANT_DIR/D-sequences/Plant_Extracted_Sequences.fasta"
DOWNLOADED_FA="$PLANT_DIR/D-sequences/Downloaded_Plant_Viruses.fasta"

if [ ! -f "$MERGED_FASTA" ]; then
    log "▶ 合并序列文件 (提取: $EXTRACTED_FA + 下载: $DOWNLOADED_FA)..."
    > "$MERGED_FASTA"  # 确保输出文件存在(空)
    [ -f "$EXTRACTED_FA" ] && cat "$EXTRACTED_FA" >> "$MERGED_FASTA" && log "  + 已提取序列"
    [ -f "$DOWNLOADED_FA" ]  && cat "$DOWNLOADED_FA"  >> "$MERGED_FASTA" && log "  + 已下载序列"
    if [ -s "$MERGED_FASTA" ]; then
        sed -i 's/ .*//' "$MERGED_FASTA"
        grep ">" "$MERGED_FASTA" | sed 's/>//' > "$MERGED_IDS"
        n=$(grep -c '>' "$MERGED_FASTA" || echo 0)
        log "✓ 序列合并完成 → $MERGED_FASTA ($n 条)"
    else
        log "✗ 合并失败: 合并后文件为空"
    fi
fi

# ============================================================
# 阶段 E: 元数据完善 → 2.plant-virus.db/E-metadata/
# ============================================================
log "========== 阶段 E: 元数据完善 =========="

run "E1-提取元数据" "$PLANT_DIR/E-metadata/Plant_Virus_Info.tsv" \
    python "$BIN_DIR/E1_extract_metadata.py" \
        -i "$PLANT_DIR/D-sequences/plant.virus.id" \
        -m "$ALLNUCL_CSV" \
        -t "$TAXID_DB" \
        -o "$PLANT_DIR/E-metadata/Plant_Virus_Info.tsv" \
        -k "$API_KEY"

run "E2-获取拓扑结构" "$PLANT_DIR/E-metadata/Plant_Virus_Topology_Molecule_Type.info.tsv" \
    python "$BIN_DIR/E2_fetch_topology.py" \
        --input "$PLANT_DIR/D-sequences/plant.virus.id" \
        --output "$PLANT_DIR/E-metadata/Plant_Virus_Topology_Molecule_Type.info.tsv" \
        --email "$EMAIL" --batch 200

# E3/E4 输出为独立文件, 串联时用临时产物传递
INFO_TSV="$PLANT_DIR/E-metadata/Plant_Virus_Info.tsv"
INFO_TOPO_TSV="$PLANT_DIR/E-metadata/Plant_Virus_Info.topo.tsv"
INFO_FULL_TSV="$PLANT_DIR/E-metadata/Plant_Virus_Full.Info.tsv"

run "E3-合并拓扑信息" "$INFO_TOPO_TSV" \
    python "$BIN_DIR/E3_merge_topology.py" \
        --seq "$PLANT_DIR/E-metadata/Plant_Virus_Topology_Molecule_Type.info.tsv" \
        --plant "$INFO_TSV" \
        --output "$INFO_TOPO_TSV"

run "E4-补充NCBI命名" "$INFO_FULL_TSV" \
    python "$BIN_DIR/E4_add_ncbi_names.py" \
        --input "$INFO_TOPO_TSV" \
        --output "$INFO_FULL_TSV" \
        --email "$EMAIL" \
        --names_dmp "$NAMES_DMP"

# 用全量版本替换原始版本, 后续步骤统一使用 INFO_FULL_TSV
INFO_TSV="$INFO_FULL_TSV"

# F1 需要 shell 重定向, 不用通用的 run()
F1_SUMMARY="$PLANT_DIR/E-metadata/Plant_Virus_Info.summary"
if [ -s "$F1_SUMMARY" ]; then
    log "⊙ 跳过 [F1-基础统计] — 产物已存在"
else
    log "▶ 开始 [F1-基础统计]"
    F1_LOG="$LOG_DIR/F1-基础统计.log"
    python "$BIN_DIR/F1_analyze_summary.py" --input "$INFO_TSV" \
        > "$F1_SUMMARY" 2>> "$F1_LOG"
    log "✓ [F1-基础统计] 完成 → $F1_SUMMARY"
fi

# ============================================================
# 阶段 F: 分类与去冗余 → 2.plant-virus.db/F-dedup/
# ============================================================
log "========== 阶段 F: 分类与去冗余 =========="

run "F2-节段分类拆分" "$PLANT_DIR/F-dedup/split_results/All_Classified_Virus_Info.tsv" \
    python "$BIN_DIR/F2_classify_segmented.py" \
        -i "$INFO_TSV" \
        --vmr "$VHOST_DIR/B-ictv/VMR_MSL41.tsv" \
        -f "$PLANT_DIR/D-sequences/Plant_Virus_Full.fasta" \
        -o "$PLANT_DIR/F-dedup/split_results" \
        --taxid-tsv "$TAXID_DB"

F2_INFO="$PLANT_DIR/F-dedup/split_results/All_Classified_Virus_Info.tsv"
F3_INFO="$PLANT_DIR/F-dedup/virus.dedup/Final_Deduplicated_Info.tsv"

if need "$F2_INFO" "F3-元数据去重"; then
    run "F3-元数据去重" "$F3_INFO" \
        python "$BIN_DIR/F3_metadata_dedup.py" \
            --info "$F2_INFO" \
            --fasta_dir "$PLANT_DIR/F-dedup/split_results" \
            --out_dir "$PLANT_DIR/F-dedup/virus.dedup"
fi

F3_NS_FA="$PLANT_DIR/F-dedup/virus.dedup/Final_NonSegmented_Deduplicated.fasta"

# F4: 非节段去冗余
if need "$F3_INFO" "F4a-非节段去冗余" && need "$F3_NS_FA" "F4a-非节段去冗余"; then
    run "F4a-非节段去冗余" "$PLANT_DIR/F-dedup/Final_DB_Build/nonsegmented_mmseqs_0.98.fasta" \
        python "$BIN_DIR/F4_seqkit_mmseqs_rescue.py" \
            -f "$F3_NS_FA" \
            -i "$F3_INFO" \
            -m nonsegmented -o "$PLANT_DIR/F-dedup/Final_DB_Build" -t "$MMSEQS_THREADS"
fi

# F4: 节段去冗余
F3_S_FA="$PLANT_DIR/F-dedup/virus.dedup/Final_Segmented_Deduplicated.fasta"
if need "$F3_INFO" "F4b-节段去冗余" && need "$F3_S_FA" "F4b-节段去冗余"; then
    run "F4b-节段去冗余" "$PLANT_DIR/F-dedup/Final_DB_Build/segmented_mmseqs_0.98.fasta" \
        python "$BIN_DIR/F4_seqkit_mmseqs_rescue.py" \
            -f "$F3_S_FA" \
            -i "$F3_INFO" \
            -m segmented -o "$PLANT_DIR/F-dedup/Final_DB_Build" -t "$MMSEQS_THREADS"
fi

# 合并最终代表性基因组
BUILD_DIR="$PLANT_DIR/F-dedup/Final_DB_Build"
RMDUP_FA="$PLANT_DIR/F-dedup/plant.final.rmdup.fasta"
RMDUP_INFO="$PLANT_DIR/F-dedup/plant.final.rmdup_info.tsv"
RMDUP_IDS="$PLANT_DIR/F-dedup/plant.final.rmdup.id"

# 文件不存在或为空文件时重新合并
if [ ! -s "$RMDUP_FA" ]; then
    log "▶ 合并非节段+节段最终序列..."
    cat "$BUILD_DIR/nonsegmented_mmseqs_0.98.fasta" "$BUILD_DIR/segmented_mmseqs_0.98.fasta" > "$RMDUP_FA"
    cat "$BUILD_DIR/nonsegmented_mmseqs_0.98_info.tsv" "$BUILD_DIR/segmented_mmseqs_0.98_info.tsv" | sed '2,${/^Accession/d;}' > "$RMDUP_INFO"
    grep ">" "$RMDUP_FA" | sed 's/>//' > "$RMDUP_IDS"
    log "✓ 合并完成 ($(grep -c '>' "$RMDUP_FA" || echo 0) 条序列)"
fi

# ============================================================
# 阶段 G: 最终聚类与评估 → 2.plant-virus.db/G-cluster/
# ============================================================
log "========== 阶段 G: 最终聚类与评估 =========="

run "G1-SeqID→TaxID映射" "$PLANT_DIR/G-cluster/seqid2taxid.map" \
    python "$BIN_DIR/G1_seqid_to_taxid.py" \
        -j 30 -b 100000 \
        --query-file "$PLANT_DIR/F-dedup/plant.final.rmdup.id" \
        --map-file "$TAXID_DB" \
        -o "$PLANT_DIR/G-cluster/seqid2taxid.map"

# G1b: 添加序列长度信息 (seqid2taxid.map → seqid2taxid_len.map)
run "G1b-添加序列长度" "$PLANT_DIR/G-cluster/seqid2taxid_len.map" \
    python "$BIN_DIR/G1b_add_length.py" \
        -i "$PLANT_DIR/G-cluster/seqid2taxid.map" \
        -f "$PLANT_DIR/F-dedup/plant.final.rmdup.fasta" \
        --type nucleotide \
        -p "$NCPU" \
        -o "$PLANT_DIR/G-cluster/seqid2taxid_len.map"

# vclust 会在 cwd 产生中间文件, 在 tmp.vclust 里运行并清理
G2_OUT="$PLANT_DIR/G-cluster/Plant_Virus_Ref.fasta"
if [ -s "$G2_OUT" ]; then
    log "⊙ 跳过 [G2-vclust聚类] — 产物已存在"
else
    log "▶ 开始 [G2-vclust聚类]"
    VCLUST_TMP="$PLANT_DIR/G-cluster/tmp.vclust"
    mkdir -p "$VCLUST_TMP"
    G2_LOG="$LOG_DIR/G2-vclust聚类.log"
    (cd "$VCLUST_TMP" && python "$BIN_DIR/G2_vclust_cluster.py" \
        --fasta "$PLANT_DIR/F-dedup/plant.final.rmdup.fasta" \
        --info "$PLANT_DIR/F-dedup/plant.final.rmdup_info.tsv" \
        --map "$PLANT_DIR/G-cluster/seqid2taxid.map" \
        --out_tsv "$PLANT_DIR/G-cluster/clusters_with_LCA.tsv" \
        --out_plot "$PLANT_DIR/G-cluster/clusters.LCA_Distribution.png" \
        --out_fasta "$PLANT_DIR/G-cluster/Plant_Virus_Ref.fasta" \
        --out_taxid_clusters "$PLANT_DIR/G-cluster/clusters.taxid.tsv" \
        --out_info "$PLANT_DIR/G-cluster/Plant_Virus_Ref.Info.tsv" \
        --out_cat_seg_conflict "$PLANT_DIR/G-cluster/category_segment_conflict.tsv" \
        --out_replacement_log "$PLANT_DIR/G-cluster/refseq_replacement_log.tsv" \
    ) >> >(tee -a "$G2_LOG") 2>> >(tee -a "$G2_LOG" >&2)
    # 清理 vclust 中间文件
    rm -rf "$VCLUST_TMP"
    log "✓ [G2-vclust聚类] 完成 → $G2_OUT"
fi

run "G3-去冗余评估" "$PLANT_DIR/G-cluster/Dereplication_Global_Summary.tsv" \
    python "$BIN_DIR/G3_derep_evaluate.py" \
        --info "$PLANT_DIR/F-dedup/split_results/All_Classified_Virus_Info.tsv" \
        --fasta_files \
            "$PLANT_DIR/D-sequences/Plant_Virus_Full.fasta" \
            "$PLANT_DIR/F-dedup/plant.final.rmdup.fasta" \
            "$PLANT_DIR/G-cluster/Plant_Virus_Ref.fasta" \
            "$PLANT_DIR/F-dedup/Final_DB_Build/nonsegmented_mmseqs_0.98.fasta" \
            "$PLANT_DIR/F-dedup/Final_DB_Build/segmented_mmseqs_0.98.fasta" \
        -o "$PLANT_DIR/G-cluster"

# G4: 基因覆盖度 → 2.plant-virus.db/H-virus_genes/
GENE_DIR="$PLANT_DIR/H-virus_genes"
mkdir -p "$GENE_DIR"

run "G4a-基因预测" "$GENE_DIR/virus.gene.gff3" \
    pyrodigal-rv -i "$PLANT_DIR/G-cluster/Plant_Virus_Ref.fasta" \
        -a "$GENE_DIR/virus.gene_pep.fasta" \
        -d "$GENE_DIR/virus.gene_nuc.fasta" \
        -o "$GENE_DIR/virus.gene.gff3" -j 120

run "G4b-覆盖度计算" "$GENE_DIR/virus_genes_cov.tsv" \
    python "$BIN_DIR/G4_gene_coverage.py" \
        --gff "$GENE_DIR/virus.gene.gff3" \
        --map "$PLANT_DIR/G-cluster/seqid2taxid_len.map" \
        --out "$GENE_DIR/virus_genes_cov.tsv" \
        --unpredicted "$GENE_DIR/unpredicted_genes_cov.tsv"

# G4c: 清理 pyrodigal 序列头部 (NC_116488.1_1 # 77 # ... → NC_116488.1_1)
for fa in "$GENE_DIR/virus.gene_pep.fasta" "$GENE_DIR/virus.gene_nuc.fasta"; do
    if [ -f "$fa" ] && grep -qm1 '#' "$fa"; then
        log "▶ 清理 pyrodigal 序列头部: $(basename "$fa")"
        sed -i 's/ .*//' "$fa"
        log "✓ $(basename "$fa") 清理完成 ($(grep -c '>' "$fa") 条)"
    fi
done

# ============================================================
# 最终产物归档 → 3.final-ref-virus.db/
# ============================================================
REF_DIR="$WORK_DIR/3.final-ref-virus.db"
mkdir -p "$REF_DIR"

if [ -f "$PLANT_DIR/G-cluster/Plant_Virus_Ref.fasta" ]; then
    ln -sf "$PLANT_DIR/G-cluster/Plant_Virus_Ref.fasta" "$REF_DIR/Plant_Virus_Ref.fasta"
    log "✓ 软链接: Plant_Virus_Ref.fasta"
fi
if [ -f "$PLANT_DIR/G-cluster/Plant_Virus_Ref.Info.tsv" ]; then
    ln -sf "$PLANT_DIR/G-cluster/Plant_Virus_Ref.Info.tsv" "$REF_DIR/Plant_Virus_Ref.Info.tsv"
    log "✓ 软链接: Plant_Virus_Ref.Info.tsv"
fi
if [ -f "$PLANT_DIR/E-metadata/Plant_Virus_Full.Info.tsv" ]; then
    ln -sf "$PLANT_DIR/E-metadata/Plant_Virus_Full.Info.tsv" "$REF_DIR/Plant_Virus_Full.Info.tsv"
    log "✓ 软链接: Plant_Virus_Full.Info.tsv"
fi
if [ -f "$PLANT_DIR/D-sequences/Plant_Virus_Full.fasta" ]; then
    ln -sf "$PLANT_DIR/D-sequences/Plant_Virus_Full.fasta" "$REF_DIR/Plant_Virus_Full.fasta"
    log "✓ 软链接: Plant_Virus_Full.fasta"
fi
if [ -f "$PLANT_DIR/H-virus_genes/virus_genes_cov.tsv" ]; then
    ln -sf "$PLANT_DIR/H-virus_genes/virus_genes_cov.tsv" "$REF_DIR/virus_genes_cov.tsv"
    log "✓ 软链接: virus_genes_cov.tsv"
fi

# ============================================================
# 总结报告
# ============================================================
log "▶ 生成学术风格总结报告..."
python "$BIN_DIR/summarize_pipeline.py" --work-dir "$WORK_DIR" \
    | tee "$LOG_DIR/pipeline_summary.txt"
log "✓ 总结报告已保存 → $LOG_DIR/pipeline_summary.txt"

# ============================================================
# 产物体检 (只读, 默认 warn-only)
# ============================================================
AUDIT_FAILED=""
if [ -z "${NO_AUDIT:-}" ]; then
    # 规范层先跑（只增列），随后体检会一并核对
    CANON_INFO=""
    if [ -f "$REF_DIR/Plant_Virus_Ref.Info.tsv" ]; then CANON_INFO="$REF_DIR/Plant_Virus_Ref.Info.tsv"
    elif [ -f "$REF_DIR/final.cluster.ref_info.tsv" ]; then CANON_INFO="$REF_DIR/final.cluster.ref_info.tsv"; fi
    if [ -n "$CANON_INFO" ]; then canonicalize_ref "$CANON_INFO"; fi
    if audit_report "$WORK_DIR" "$RAW_DIR"; then
        log "✓ 产物体检完成 (无 FAIL 项)"
    else
        AUDIT_FAILED=1
        log "⚠ 产物体检发现 FAIL 项 — 详见 $AUDIT_OUT/audit_summary.md (加 --no-audit 可跳过)"
    fi
fi

# ============================================================
# 完成
# ============================================================
echo ""
echo "============================================"
echo "  Pipeline 执行完毕"
echo "============================================"
echo "最终产物:"
echo "  病毒-宿主库:   $VHOST_DIR/"
echo "  参考基因组:    $PLANT_DIR/"
echo "  最终参考库:    $WORK_DIR/3.final-ref-virus.db/"
echo "  宿主分类研究:  $WORK_DIR/4.host_classify/"
echo "  下游数据库:    $WORK_DIR/5.virus.ref.build.db/"
echo "  序列:          $PLANT_DIR/G-cluster/Plant_Virus_Ref.fasta"
echo "  覆盖度:        $PLANT_DIR/H-virus_genes/virus_genes_cov.tsv"
echo "  LCA 分布:      $PLANT_DIR/G-cluster/clusters.LCA_Distribution.png"
echo "  日志目录:      $LOG_DIR/"
if [ -n "${AUDIT_OUT:-}" ]; then echo "  体检报告:      $AUDIT_OUT/audit_summary.md"; fi
echo "============================================"

# --strict-audit 时, 体检 FAIL 影响退出码 (默认不影响)
if [ -n "${AUDIT_FAILED:-}" ] && [ -n "${STRICT_AUDIT:-}" ]; then
    exit 1
fi
