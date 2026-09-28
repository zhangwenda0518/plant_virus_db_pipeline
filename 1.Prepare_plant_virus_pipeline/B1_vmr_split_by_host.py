#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import polars as pl
import argparse
import time
import os
import subprocess

def get_plant_taxids(taxonkit="taxonkit", root_taxid="33090"):
    """用 taxonkit 展开 Viridiplantae (TaxID 33090) 的全部子 TaxID 集合。

    返回 set[int]；taxonkit 不可用时返回空 set（调用方跳过校验）。
    """
    try:
        r = subprocess.run(
            [taxonkit, "list", "--ids", root_taxid, "--indent", ""],
            capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            return {int(x) for x in r.stdout.strip().split("\n") if x.strip().isdigit()}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return set()

def parse_args():
    parser = argparse.ArgumentParser(description="根据 ICTV 拆分 VMR，并利用多维度 NCBI 谱系深度抢救暗物质")
    parser.add_argument("-v", "--vmr", default="VMR_MSL40.tsv", help="ICTV 的官方 VMR 表格")
    parser.add_argument("-m", "--vhost", default="VHostMetadata.lineage.parquet", help="本地 VHostMetadata 数据 (Parquet或TSV)")
    parser.add_argument("-o", "--out_dir", default="VMR_Split_By_Host", help="拆分后的结果输出目录")
    return parser.parse_args()

def apply_ncbi_host_classification(df: pl.DataFrame, lineage_col: str) -> pl.DataFrame:
    """NCBI 谱系分类漏斗（2026-09-16 修正版）。

    ⚠ 关键修正：Plant 检查必须在 Animal 之前——
    TSWV 等由蓟马（Arthropoda）传播的植物病毒，Host_lineage 同时含
    Viridiplantae（植物宿主）和 Arthropoda（媒介昆虫）。旧版 Animal
    先于 Plant 检查，导致这些病毒被误归为 Animal 而从植物库中丢失。

    分类优先级（自上而下首次命中即停）：
      1. Human（人类，最特异，不受多宿主影响）
      2. Plant（Viridiplantae——植物病毒的主要宿主域，优先于动物载体）
      3. Animal（非植物宿主的动物病毒）
      4. Fungi → 5. Protist → 6. Bacteria → 7. Archaea
      8. Environmental → 兜底 Unknown
    """
    return df.with_columns(
        # 1. 人类优先 (Homo sapiens) —— 2026-09-19 加词边界, 防止 Homona(螟蛾属) 等子串误配
        pl.when(pl.col(lineage_col).str.contains(r"(?i)\bHomo sapiens\b|\bHomo\b|\bHuman\b"))
        .then(pl.lit("Human"))

        # 2. 植物 —— 必须在 Animal 之前：由昆虫媒介传播的植物病毒
        #    （TSWV、BYSV、GYVV 等）的 Host_lineage 同时含 Viridiplantae
        #    和 Arthropoda，Plant 先检可防止被 Animal 条件劫持。
        .when(pl.col(lineage_col).str.contains("(?i)Viridiplantae|Plant|Embryophyta|algae|Rhodophyta|Streptophyta|Chlorophyta|Tracheophyta|Magnoliophyta|Solanales|Cucurbitales|Fabales"))
        .then(pl.lit("Plant"))

        # 3. 动物 (Metazoa 后生动物门, Chordata 脊索动物, Arthropoda 节肢动物, Nematoda 线虫等)
        .when(pl.col(lineage_col).str.contains("(?i)Metazoa|Animalia|Bos taurus|Sus scrofa|Macaca|vertebrate|invertebrate|Chordata|Arthropoda|Nematoda|Platyhelminthes"))
        .then(pl.lit("Animal"))

        # 4. 真菌与卵菌 (Fungi 真菌界, Oomycota 卵菌门, Peronosporomycetes 霜霉纲, Ascomycota 子囊菌, Basidiomycota 担子菌)
        .when(pl.col(lineage_col).str.contains("(?i)Fungi|oomycetes|Oomycota|Peronosporomycetes|Ascomycota|Basidiomycota|Chytridiomycota|Mucoromycota"))
        .then(pl.lit("Fungi"))

        # 5. 原生生物 (Sar 超类群, Stramenopiles 不等鞭毛类, Alveolata 囊泡虫, Amoebozoa 变形虫, Excavata 挖掘虫)
        #    2026-09-19: Sar 加词边界 —— 无边界时 Sarcina(细菌属, Protist 检查先于 Bacteria) 会被劫持成 Protist
        .when(pl.col(lineage_col).str.contains(r"(?i)\bSar\b|Stramenopiles|Alveolata|Rhizaria|Amoebozoa|Excavata|protist|Ciliophora|Apicomplexa"))
        .then(pl.lit("Protist"))

        # 6. 细菌 (Bacteria, Pseudomonadota 变形菌门, Firmicutes 厚壁菌门, Actinomycetota 放线菌门, Bacteroidota 拟杆菌门)
        .when(pl.col(lineage_col).str.contains("(?i)Bacteria|Escherichia|Pseudomonadota|Firmicutes|Actinomycetota|Bacteroidota|Cyanobacteria|Proteobacteria"))
        .then(pl.lit("Bacteria"))

        # 7. 古菌 (Archaea, Euryarchaeota 广古菌门, Crenarchaeota 泉古菌门)
        .when(pl.col(lineage_col).str.contains("(?i)Archaea|Euryarchaeota|Crenarchaeota|Thermoproteota"))
        .then(pl.lit("Archaea"))

        # 8. 环境无用词汇隔离 (防止被误判为生物)
        .when(pl.col(lineage_col).str.contains("(?i)environmental|uncultured|metagenome|soil|water|marine|sewage|sludge"))
        .then(pl.lit("Environmental_NCBI"))

        # 兜底：纯粹的空值或极其冷门的分类
        .otherwise(pl.lit("Unknown"))
        .alias("Rescued_Category")
    )

def main():
    args = parse_args()
    start_time = time.time()
    os.makedirs(args.out_dir, exist_ok=True)
    
    print("==================================================================")
    print("👑 启动 ICTV VMR 精准拆分与暗物质深度抢救引擎")
    print("==================================================================")

    # ==========================================
    # 1. 读取并解析 VMR 原生环境与宿主标签
    # ==========================================
    print(f"\n⏳ 1. 正在加载并解析 ICTV VMR 数据 ({args.vmr})...")
    vmr_df = pl.read_csv(args.vmr, separator="\t", ignore_errors=True)
    
    vmr_df = vmr_df.with_columns(
        # 2026-09-19 修复: VMR 的 accession 单元格可能含多条记录 (";" 或 "," 分隔,
        # 分段病毒常见), 原先只切版本号点号, 多 accession 时 join 不上 → 抢救漏。
        # 现取第一条 accession 再去版本号, 与 A2 的 Acc_NoVersion 口径对齐。
        pl.col("Virus GENBANK accession").cast(pl.Utf8).fill_null("")
        .str.split(";").list.first()
        .str.split(",").list.first()
        .str.split(".").list.first()
        .str.strip_chars().alias("Base_Accession"),
        pl.col("Host source").fill_null("unknown").str.to_lowercase().alias("host_lower")
    )

    # 互斥逻辑：是 Unknown 就不能是 Environmental，防止两边跑
    # Plant 正则已扩展：除 "plant(s)" 外还包括常见植物宿主属/种名
    # （TSWV 的 Host source 写的是 "tomato/tobacco" 等具体名而非泛称 "plant"，
    #   旧正则只匹配 \bplants?\b 导致 is_Plant=False → 进 rescue → 被 Arthropoda 劫持）
    vmr_df = vmr_df.with_columns(
        pl.col("host_lower").str.contains(
            r"(?i)\bplants?\b|\balgae\b|\bphytobiome\b"
            r"|\btomato\b|\btobacco\b|\bnicotiana\b|\barabidopsis\b"
            r"|\brice\b|\boryza\b|\bmaize\b|\bzea\b|\bwheat\b|\btriticum\b|\bbarley\b|\bhordeum\b"
            r"|\bpotato\b|\bsolanum\b|\bcassava\b|\bmanihot\b|\bcitrus\b"
            r"|\bgrapevine\b|\bvitis\b|\bprunus\b|\bmalus\b|\bpyrus\b"
            r"|\bcucurbita\b|\bcucumis\b|\bpepper\b|\bcapsicum\b"
            r"|\bsoybean\b|\bglycine\b|\bchrysanthemum\b|\blilium\b|\bpelargonium\b|\bimpatiens\b"
            r"|\bchenopodium\b|\barachis\b|\bpisum\b|\bmedicago\b|\bdatura\b"
        ).alias("is_Plant"),
        pl.col("host_lower").str.contains(r"(?i)\bvertebrates?\b|\binvertebrates?\b").alias("is_Animal"),
        pl.col("host_lower").str.contains(r"(?i)\bbacteria\b").alias("is_Bacteria"),
        pl.col("host_lower").str.contains(r"(?i)\barchaea\b").alias("is_Archaea"),
        pl.col("host_lower").str.contains(r"(?i)\bfungi\b|oomycetes").alias("is_Fungi"),
        pl.col("host_lower").str.contains(r"(?i)\bprotists?\b").alias("is_Protist"),
        pl.col("host_lower").str.contains(r"(?i)\bunknown\b|\bother\b|^$").alias("is_Unknown")
    )
    
    # Environmental 前提是不能是 Unknown
    vmr_df = vmr_df.with_columns(
        pl.when(pl.col("is_Unknown")).then(False).otherwise(
            pl.col("host_lower").str.contains(r"(?i)\bair\b|\bfreshwater\b|\bmarine\b|\bsewage\b|\bsoil\b|\(s\)")
        ).alias("is_Environmental")
    )

    vmr_df = vmr_df.with_columns(
        (pl.col("is_Plant") | pl.col("is_Animal") | pl.col("is_Bacteria") | 
         pl.col("is_Archaea") | pl.col("is_Fungi") | pl.col("is_Protist")).alias("has_Bio_Host")
    )

    has_host_df = vmr_df.filter(pl.col("has_Bio_Host"))
    needs_rescue_df = vmr_df.filter(~pl.col("has_Bio_Host"))

    print(f"   -> 明确拥有生物宿主的记录 : {has_host_df.height} 条 (原生ICTv数据)")
    print(f"   -> 仅有环境来源或完全未知 : {needs_rescue_df.height} 条 (即将进入抢救流)")

    # ==========================================
    # 2. 从 VHostMetadata 抢救并保留原文本用于诊断
    # ==========================================
    success_rescue = pl.DataFrame()
    still_unknown = needs_rescue_df.with_columns(pl.lit("Not_Found_in_NCBI").alias("NCBI_Raw_Host"))

    if needs_rescue_df.height > 0:
        print(f"\n⏳ 2. 正在加载本地宿主库 ({args.vhost}) 进行系统发育学文本扫描...")
        
        if args.vhost.endswith(".parquet"):
            vhost_lf = pl.scan_parquet(args.vhost)
        else:
            vhost_lf = pl.scan_csv(args.vhost, separator="\t", ignore_errors=True)
            
        vhost_df = (
            vhost_lf.select(["Accession", "Host_lineage"])
            .drop_nulls(subset=["Accession"])
            .with_columns(
                pl.col("Accession").cast(pl.Utf8).str.split(".").list.first().alias("Base_Accession"),
                pl.col("Host_lineage").fill_null("")
            )
            .unique(subset=["Base_Accession"], keep="first")
            .collect()
        )
        
        rescued_df = needs_rescue_df.join(
            vhost_df.select(["Base_Accession", "Host_lineage"]), 
            on="Base_Accession", 
            how="left"
        )
        
        # 保留 NCBI 的原始文本，无论抢救成功还是失败，供诊断使用
        rescued_df = rescued_df.with_columns(pl.col("Host_lineage").alias("NCBI_Raw_Host"))
        
        # 运行全面升级版的拉丁文分类器
        rescued_df = apply_ncbi_host_classification(rescued_df, "Host_lineage")
        
        # 成功抢救的生物宿主 (排除了 Unknown 和 Environmental)
        success_rescue = rescued_df.filter(
            (pl.col("Rescued_Category") != "Unknown") & 
            (pl.col("Rescued_Category") != "Environmental_NCBI")
        ).with_columns(
            (pl.col("Rescued_Category") == "Plant").alias("is_Plant"),
            (pl.col("Rescued_Category") == "Animal").alias("is_Animal"),
            (pl.col("Rescued_Category") == "Bacteria").alias("is_Bacteria"),
            (pl.col("Rescued_Category") == "Archaea").alias("is_Archaea"),
            (pl.col("Rescued_Category") == "Fungi").alias("is_Fungi"),
            (pl.col("Rescued_Category") == "Protist").alias("is_Protist"),
            pl.lit(False).alias("is_Unknown"),
            pl.lit(False).alias("is_Environmental")
        ).drop(["Host_lineage", "Rescued_Category", "NCBI_Raw_Host"])

        # 依然无法抢救的（由于在 NCBI 中没找到，或者 NCBI 里的文本就是环境废话）
        still_unknown = rescued_df.filter(
            (pl.col("Rescued_Category") == "Unknown") | 
            (pl.col("Rescued_Category") == "Environmental_NCBI")
        ).drop(["Host_lineage", "Rescued_Category"])
        
        print(f"   ⚡ 抢救完毕！由于扩大了生物学词典，成功找回 {success_rescue.height} 条隐藏记录！")

    # ==========================================
    # 3. 数据组合与多类分发输出
    # ==========================================
    print("\n⏳ 3. 正在合并数据并按宿主交叉分发输出...")
    
    # 组合所有处理过的数据 (still_unknown 去掉多余的诊断列以对齐主表)
    final_df = pl.concat([has_host_df, success_rescue, still_unknown.drop("NCBI_Raw_Host")], how="diagonal")
    
    categories = ["Plant", "Animal", "Bacteria", "Archaea", "Fungi", "Protist", "Environmental", "Unknown"]
    
    print("\n========== VMR 宿主精准拆分统计 ==========")
    for cat in categories:
        col_name = f"is_{cat}"
        cat_df = final_df.filter(pl.col(col_name))
        count = cat_df.height
        
        if count > 0:
            # 清理布尔辅助列和内部拼接列，保持与原 VMR 一样的整洁度
            clean_df = cat_df.drop(["host_lower", "has_Bio_Host", "Base_Accession"] + [f"is_{c}" for c in categories])
            out_file = os.path.join(args.out_dir, f"VMR_{cat}.tsv")
            clean_df.write_csv(out_file, separator="\t")
            print(f" - {cat:<15} : {count:>8,} 条 -> {out_file}")

    print("==========================================\n")

    # ==========================================
    # 4. 导出失败诊断报告
    # ==========================================
    if still_unknown.height > 0:
        diag_file = os.path.join(args.out_dir, "Rescue_Failed_Details.tsv")
        diag_df = still_unknown.select([
            "Virus GENBANK accession", "Virus name(s)", "Host source", "NCBI_Raw_Host"
        ])
        diag_df.write_csv(diag_file, separator="\t")
        print(f"💡 关键提示：剩余的真·孤儿病毒诊断报告已生成: {diag_file}")
        print(f"   (请查看 NCBI_Raw_Host 列，它们通常在 NCBI 中也是彻底的空值或无意义词汇)")

    print(f"\n✅ 全部任务完成！生成文件存放于: ./{args.out_dir}/")
    print(f"⏱️ 耗时: {time.time() - start_time:.2f} 秒")

if __name__ == "__main__":
    main()
