# alphafast_input — 365 条零覆盖蛋白的 AF3-dialect JSON 输入包

每个 `json/{acc}.json` 是一个独立 AF3 折叠任务（单链蛋白，seed=1，
dialect=alphafold3，version=1），可直接作为 AlphaFast 的 `--input_dir`。
`manifest.tsv` 为逐任务清单（含 priority 分层，可按列拆子集分批跑）。
生成脚本：`oneoff_scripts/uniprot_pdb_fetch/prepare_alphafast_input.py`。

## 运行模式（权重 models/af3.bin.zst 已就位）

1. **Docker（本地/单机 GPU 服务器，NVIDIA）**
   `docker pull romerolabduke/alphafast`；先跑官方 `scripts/setup_databases.sh`
   建库（强烈建议指向 NVMe），再用官方 `run_alphafast.sh` 入口挂载本目录
   （参数名以 https://github.com/RomeroLab/alphafast 官方 README 为准）。
2. **SLURM 集群（Singularity/Apptainer）**：官方示例 `alphafast.sl`；
   共享存储够快可免拷库到本地临时盘。
3. **Modal 无服务器（本机无 GPU 时的最短路径）**：基准 $0.035/输入，
   本包输入 2,000–3,471 aa，按时长上浮，365 条全套估 $30–80；
   Modal 仅支持信用卡（Stripe），不支持支付宝/微信。

## 结果回传（暂为手动）

AlphaFast 输出为 mmCIF（B-factor 即 pLDDT），与本库 viewer/入库通道兼容。
16.fold_web 的自动入库（`foldcore.find_best_model`）目前面向 ColabFold
rank_001 命名，AF3 结果暂请手动放入
`15.uniprot_plant_virus_structures/structures_selffold/{acc}.cif`，
并在 `structures_index.tsv` 的 sources 列追加 SELF、selffold_model 列填文件名；
AF3 结果自动回传通道待接。
