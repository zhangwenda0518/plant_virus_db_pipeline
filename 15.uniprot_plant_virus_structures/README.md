# 15. UniProt 植物宿主病毒蛋白结构模块（PDB 实验结构 + AFDB 官方模型）

> 数据源：UniProtKB（REST，release **2026_03**，抓取日 2026-10-01）。
> 与 `14.rvpsd_structures`（RVPSD 的 AlphaFold2 第三方模型）互补：本模块是
> **UniProt 官方交叉引用指向的结构** = RCSB PDB 实验解析结构 + EBI AlphaFoldDB 现役模型
> + BFVD 簇代表结构覆盖对账。

## 一、查询口径（重要，2026-10-02 已收紧）

用户给的网页查询 `query=10239 AND (taxonomy_id:10239)` 只是"全部病毒蛋白"
（**1,109,731** 条），并不区分植物。本模块把"植物"落实为 **病毒宿主必须含陆生植物**
（Streptophyta, taxid 35493）：

```
query = (taxonomy_id:10239) AND virus_host_id:33090 AND virus_host_id:35493
```

| 层级 | 条数 |
|:--|--:|
| 全部病毒蛋白（10239） | 1,109,731 |
| Viridiplantae 宿主（初版口径，含绿藻） | 6,803 |
| **陆生植物宿主（本模块现行宇宙）** | **4,810**（reviewed 1,274） |
| ↳ 其中有 PDB 实验结构交叉引用 | 77（unique PDB 214） |
| ↳ 其中有 AlphaFoldDB 交叉引用 | 264 |

**2026-10-02 去除噬藻体/绿藻病毒**：初版用 `virus_host_id:33090`（Viridiplantae 含
绿藻门），混入 8 个绿藻病毒物种共 **1,993 条**（PBCV-NY2A 877、PBCV-1 849、
MpV-SP1 243 等，与陆生组零重叠），已整体剔除并留档
`removed_green_alga_viruses.tsv`；对应结构文件（39 个 PDB + 898 个 AF 模型）已删。
另有昆虫病毒经"实验性植物宿主"混入的个例（如 Flock house virus 经大麦注释，9 条），
**暂保留**——如需严格化可再按病毒分类学二次过滤。无宿主注释的植物病毒（GCVA 类）
与类病毒（viroids，不在 taxonomy 10239 下）仍不在本宇宙内。

## 二、产出文件

| 路径 | 说明 |
|:--|:--|
| `plant_virus_uniprot_full.tsv` | **4,810** 条全量清单（accession、蛋白名、病毒物种、宿主、长度、PDB、AlphaFoldDB） |
| `structures_index.tsv` | **蛋白级结构总索引**（每蛋白一行：PDB IDs / AFDB 模型 / RVPSD 模型 / BFVD 簇 / 来源汇总） |
| `pdb_links.tsv` | 217 条 entry↔PDB 展开链接（UniProt 交叉引用口径） |
| `pdb_links_sifts.tsv` | 2,598 条链级 SIFTS 联表（PDB, chain, accession, SP 区段） |
| `unique_pdb_ids.txt` | UniProt 交叉引用去重 **214** 个 PDB ID（基线） |
| `unique_pdb_ids_sifts_delta.txt` | SIFTS 反查新增的 **4** 个 PDB ID |
| `unique_pdb_ids_all.txt` | 并集 **218** 个（下载总清单） |
| `afdb_links.tsv` | 264 条 AFDB 交叉引用清单（UniProt 官方标注口径） |
| `afdb_links_all.tsv` | 4,810 条全量（供"逐条探测 AFDB"用，交叉引用不能当地图用） |
| `removed_green_alga_viruses.tsv` | 2026-10-02 剔除留档：1,993 条噬藻体/绿藻病毒蛋白（8 物种） |
| `structures_pdb/` | **218 个 mmCIF（554 MB）**，RCSB 非对称单元，`files.rcsb.org/download/{ID}.cif` |
| `structures_pdb/pull_manifest_pdb.tsv` | 下载清单（214 hit + 4 skip，0 fail） |
| `structures_alphafold/` | **435 个 mmCIF（182 MB）**，AFDB 现役模型（v6 时代，已解压为纯文本） |
| `structures_alphafold/pull_manifest_afdb.tsv` | 探测清单（435 hit + 4,375 miss，4,810 条全覆盖，0 fail） |
| `structures_supplementary_gcva/` | **GCVA 补充批次：6 个 AlphaFold3 模型**（见第三节末） |
| `structures_supplementary_gcva/pull_manifest_gcva.tsv` | GCVA 批次 manifest（含 pLDDT 统计） |
| `pending_prediction.tsv` | 四路皆无结构的 **365** 条蛋白（P1–P3 优先级分层，主体是多聚蛋白） |
| `pending_prediction_bfvd_only.tsv` | 仅 BFVD（同源模型级）覆盖的 3,333 条，自身折叠按需 |
| `webapp/` | **自包含静态站**：总览 dashboard + 统计面板 + 蛋白/病毒检索 + 3Dmol 查看器 |
| `webapp/data/` | 页面数据（build_data.py 从 structures_index / virus_coverage 生成，幂等） |

结构本体约 0.74 GB、SIFTS 源表 `pdb_chain_uniprot.tsv.gz` 均已 gitignore；
清单 / 联表 / 总索引 / 剔除留档 / manifest / README / 脚本入库。

## 三、蛋白级覆盖全景（四路结构对账，陆生植物宇宙 4,810 条，2026-10-02 终版）

4,810 条蛋白 × {PDB 实验结构, AFDB 现役模型, RVPSD AF2 模型(14 模块), **BFVD**} 对账
结果（`structures_index.tsv`，bfvd_cluster 列 + sources 列）：

| 来源组合 | 蛋白数 |
|:--|--:|
| **BFVD**（UniRef30 簇代表结构，见下） | **3,333** |
| RVPSD,BFVD | 548 |
| AFDB,RVPSD,BFVD | 258 |
| AFDB,BFVD | 158 |
| RVPSD | 57 |
| PDB,BFVD | 31 |
| PDB,RVPSD,BFVD | 30 |
| 其余（PDB / AFDB / 多源组合） | 70 |
| **四路皆无（`pending_prediction.tsv`）** | **365 (7.6%)** |

- **任一来源有结构：4,445 / 4,810（92.4%）**。物种（毒株）级：完全无结构仅 **6** 个
  （413 个中），部分覆盖 51，全覆盖 356。
- 365 条真零的构成：**304 条是多聚蛋白（>2,700 aa，中位 3,059 aa）**，整链折叠不可行
  需先做结构域切分；reviewed 31 条；无 <50 aa 极小蛋白。
- **BFVD 是最大增量**：Big Fantastic Virus Database（NAR 2025, doi:10.1093/nar/gkae1119），
  351,242 个病毒蛋白 UniRef30 簇代表的 ColabFold 结构，专补 AFDB 不含病毒。对全部
  条目经 `https://bfvd.foldseek.com/api/{accession}` 逐条查询（脚本
  `bfvd_lookup.py`），命中 4,366（90.8%）。仅 BFVD 覆盖的清单另存
  `pending_prediction_bfvd_only.tsv`（同源模型级证据，是否还需自身折叠视用途）。
- **AFDB 覆盖 ≠ 交叉引用**：UniProt 有 AFDB 交叉引用的仅 264 条（陆生宇宙）；逐条
  探测后确证现役模型 435 个——全量探测不可省。
- **SIFTS 反查**：EBI SIFTS 全量映射表按 accession 联表，比 UniProt 交叉引用多发现
  4 个 PDB 条目（RCSB Search API 的 UniProt 字段不可批量检索，SIFTS 是唯一通道）。
- **RVPSD 桥接**：14 模块文件名以 GenBank/ENA 蛋白 ID 开头，经 UniProt JSON 流的
  EMBL `ProteinId` 属性建立映射（9,122 对）；公开 idmapping 对
  `to=EMBL-GenBank-DDBJ` 实际返回空，不可用。
- 使用 BFVD 三注意：①结构是**簇代表链**的模型（UniRef30 聚类，成员与代表 ≥30% 一致性），
  对本清单蛋白属同源模型级证据；②PDB 文件是 PULCHRA 重建的 CA-trace、pLDDT 离散成
  0–9 档（文件头 REMARK 有声明）；③文件托管在 `bfvd.steineggerlab.workers.dev`，
  **本机网络 DNS 级不可达**（DoH 绕行无效），取坐标需换网络或整库下载 Foldcomp 版；
  查询接口 `bfvd.foldseek.com` 本机可达。

### GCVA 补充批次（模块宇宙之外的蛋白，2026-10-01 并入）

**GCVA = Cytorhabdovirus sp. 'lycii' isolate Goji**（OR489165.1，14,812 bp，
宿主枸杞 *Lycium barbarum*，药用植物病毒组项目），UniProt 全无收录（蛋白
WRO64935–WRO64940 与物种条目均为 0），故不在 `structures_index.tsv` 的
6,803 蛋白宇宙内，单独立批：`structures_supplementary_gcva/`，6 个蛋白的
AlphaFold3 model_0（本地 alphafoldserver 输出，原始 5 模型 + PAE JSON 留在
用户目录不动）：

| 基因 | 蛋白 | 产物 | mean pLDDT | ≥90 | <50 |
|:--|:--|:--|--:|--:|--:|
| N | WRO64935.1 | nucleocapsid | **80.8** | 33.0% | 5.7% |
| P | WRO64936.1 | phosphoprotein | 55.0 | 8.4% | 47.2% |
| P4 | WRO64937.1 | P4 protein | 49.8 | 0% | 52.1% |
| M | WRO64938.1 | matrix protein | 37.8 | 0% | 81.5% |
| G | WRO64939.1 | glycoprotein | 47.4 | 0% | 64.7% |
| L | WRO64940.1 | polymerase | **77.3** | 22.7% | 8.4% |

pLDDT 分布符合弹状病毒预期（N/L 折叠良好；P/M 天然无序度高，G 缺糖基化与膜
上下文）。注意 AF3 输出 cif 首行是 `#` 许可注释，校验需先剥注释再验 `data_`。

## 四、下载脚本与再生成

脚本：`../oneoff_scripts/uniprot_pdb_fetch/uniprot_structure_fetch.py`
（纯标准库；断点续跑：已有文件/manifest 中 hit、skip 状态自动跳过，fail 可重跑补齐）

```bash
# 1. 刷新全量清单（如需；现行口径 = 宿主必须含陆生植物 Streptophyta）：
curl -s --compressed -o plant_virus_uniprot_full.tsv \
  "https://rest.uniprot.org/uniprotkb/stream?query=(taxonomy_id:10239)%20AND%20virus_host_id:33090%20AND%20virus_host_id:35493&format=tsv&fields=accession,id,reviewed,protein_name,organism_name,organism_id,length,virus_hosts,xref_pdb,xref_alphafolddb"
# 2. 拆清单 + 下载（按 README 第四节顺序执行）
python uniprot_structure_fetch.py pdb   # PDB mmCIF（按 unique_pdb_ids 基线）
python uniprot_structure_fetch.py af    # 全部条目逐条探测 AFDB，有模型即下
# 3. SIFTS 反查补 UniProt 交叉引用滞后（联表 → --download 下载增量）
curl -s -o pdb_chain_uniprot.tsv.gz -C - \
  "https://ftp.ebi.ac.uk/pub/databases/msd/sifts/flatfiles/tsv/pdb_chain_uniprot.tsv.gz"
python sifts_sweep.py --download
# 4. 蛋白级总索引（含 RVPSD 桥接对账）
python build_structures_index.py
# 5. BFVD 覆盖查询（回写 structures_index 的 bfvd_cluster / sources 列）
python bfvd_lookup.py
```

## 五、2026-10-01 抓取实录（踩坑记录）

1. **`xref:pdb` 不是合法查询字段**（静默返回 0 条）——结构覆盖统计改由全量 TSV 的
   `xref_pdb` 列本地过滤得出。
2. **AFDB 文件命名已换代**：`model_v4.cif` / `.cif.gz` 全部 404，现役为
   `AF-{acc}-F1-model_v6.cif`；且该"`.cif`"URL 实际回传 **gzip 流**，脚本落盘前统一
   解压并校验（`data_` 头 + `_atom_site.` 段）。
3. **AFDB 交叉引用 ≠ AFDB 覆盖**：只按 1,093 条交叉引用下载会漏掉 262 个模型；
   全量逐条探测后模型总数 1,333（见第三节口径）。
4. **RCSB Search API 的 UniProt 字段不可批量反查**：`reference_sequence_identifiers`
   仅支持 `exists`（`in`/`exact_match` 均被拒），`uniprot_ids` 直接"search is not
   enabled"——批量 PDB 反查走 EBI SIFTS 联表（本机 python 直连 search.rcsb.org 还被
   拒，仅 curl 可达，未再深究）。
5. **UniProt 公开 idmapping 对 `to=EMBL-GenBank-DDBJ` 返回空**（作业 FINISHED 但
   results 为空，配置页却声称支持）——ProteinId 桥接改由 REST JSON 流的 EMBL 交叉
   引用直接抽取。
6. **校验结果**：structures_pdb 258/258、structures_alphafold 1,333/1,333 全部通过
   （逐文件检查，非抽样；磁盘文件数与 manifest hit 集合完全一致）；
   抽样 `structure_report`（2HWT：NMR 集合 31 模型、A 链 94 残基）解析正常。

## 六、使用注意

- PDB 下载的是**非对称单元**，未必是生物学组装体；界面/寡聚化分析请按 PDB ID 另取 assembly。
- PDB 内残基编号（auth_seq_id）与 UniProt 编号常有位移（表达标签、截断构建），对位分析须显式比对。
- AFDB 模型自带 pLDDT/B-factor 通道，**<70 区域仅作示意**；多域相对取向看 PAE 不看 pLDDT。
- 与 `14.rvpsd_structures` 的分工：定量/展示优先用本模块的**实验结构**；无实验结构的蛋白
  用 AFDB 现役模型（本模块）或 RVPSD AF2 模型（14 模块，覆盖更广：17,918 蛋白）。

## 七、webapp 页面（2026-10-03 新增；2026-10-04 修复 viewer 致命 bug + 公网路由）

```bash
# 必须从模块根目录起服务（查看器要直接读 structures_pdb/ 等）
cd 15.uniprot_plant_virus_structures
python -m http.server 8801
# 浏览器: http://127.0.0.1:8801/webapp/          （nginx 亦可整模块根挂载）
```

公网部署（nginx，已写入 `deploy/nginx_full.conf`，线上加到
`/etc/nginx/conf.d/plant-virus.conf` 即生效）：

```nginx
location = /uniprot3d { return 301 /uniprot3d/; }
location /uniprot3d/ {
    alias /opt/plant_virus_db/plant_virus_db_pipeline/15.uniprot_plant_virus_structures/;
    index webapp/index.html;      # 挂模块根：viewer 的 ../structures_* 相对路径才能通
}
location ^~ /uniprot3d/colabfold_input/ { return 404; }   # 运行期产物不暴露
location ~* ^/uniprot3d/.*\.(db|log|tmp)$ { return 404; }
```

门户入口卡片（`docs/index.html` Data Resources 区 → `/uniprot3d/webapp/`）与
帮助页（`docs/help/uniprot3d.html`）均已就位。

2026-10-04 修复：`webapp/viewer.html` 引用了未定义的 `esc()`（只在 index.html 里定义过）
导致 ReferenceError 中断脚本、**3D 查看器整页无法加载**——三页已统一改用共享
`webapp/common.js`（esc / 页面级错误横幅 / loadJSON），并补充键盘可达性
（蛋白行 Tab+Enter 打开详情、Esc 关闭）。

| 页面 | 内容 |
|:--|:--|
| `webapp/index.html` | 总览 dashboard（指标卡 + 来源组合条形图）+ 蛋白检索（点行出详情/外部链接/3D 入口）+ 病毒级覆盖表 |
| `webapp/stats.html` | **统计面板**：物种完整率环形图、来源组合与单源命中明细、待预测缺口分层、管线台账（SIFTS/AFDB/BFVD/剔除/GCVA） |
| `webapp/viewer.html` | 3Dmol 查看器（?acc=&src=pdb/af/self），AF/自建模型按 pLDDT 四段着色 |
| `webapp/common.js` | 三页公共工具：HTML 转义 / 数据加载失败横幅（2026-10-04 新增） |

数据刷新：数据源（structures_index.tsv 等）变更后重跑 `webapp/build_data.py` 即可，幂等。

外部预测通道：蛋白详情面板含 **Foldify**（免费在线 AF3/AF2/ColabFold/OmegaFold/ESMFold，
≤600aa 人工提交）直达链接；批量导出入口在 16.fold_web 平台（`/api/export/foldify`）。
