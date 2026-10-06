#!/usr/bin/env bash
# ColabFold 批量预测 —— 在 GPU 服务器（Linux/WSL2，NVIDIA 显存≥16GB）执行
# 安装参考: https://github.com/sokrypton/ColabFold (mamba install -c conda-forge colabfold)
# 预计: RTX4090 单卡约 1-2 分钟/蛋白(≤300aa, MMseqs2 API MSA)，3,394 条约 2-4 GPU-天
set -euo pipefail
INPUT_DIR="batch_normal"
OUT_DIR="colabfold_results"
mkdir -p "$OUT_DIR"
# MSA 用 ColabFold 公共 MMseqs2 API（无需本地 2TB 数据库）；限速可用 --data 需自建库
colabfold_batch \
  --msa-mode mmseqs2_uniref_env \
  --num-models 3 \
  --num-recycle 3 \
  --model-type alphafold2_ptm \
  --rank plddt \
  --job-name pending_fold \
  "$INPUT_DIR" "$OUT_DIR"
