#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Step 2 — 构建「植物病毒分类学进化关系树」数据。

输入
  data/MSL41_species.tsv   ICTV MSL41 v1 主表（export_msl41.py 产出）
  ICTV VMR 表（含 Host source 列）  —— 用于判定哪些分类单元是植物病毒

为什么需要 VMR：
  ICTV Master Species List 只发布分类层级（Realm→…→Species），**没有宿主列**。
  判定「哪些科属是植物病毒」必须借助 ICTV Virus Metadata Repository 的
  Host source 字段。本脚本沿用 1.Prepare_plant_virus_pipeline/C4_clean_all_tsvs.py
  里已经验证过的科级 / 属级黑名单，保证与数据库其它模块口径一致。

输出
  taxonomy_tree.json   完整病毒分类骨架 + 植物病毒分支（展开到种）
  plant_taxa.tsv       判定结果清单（科 / 属 / 种），供人工复核

用法
  python build_taxonomy.py \
      --msl data/MSL41_species.tsv \
      --vmr ../../oneoff_scripts/_bench_b1_20260919/vmr.tsv \
      --out taxonomy_tree.json
"""
import argparse
import collections
import csv
import json
import os
import sys

# ---------------------------------------------------------------- 主分类阶元
# Subrealm / Subkingdom / Subclass 在 MSL41 中为空；Subphylum / Suborder /
# Subfamily / Subgenus 层级过细，建树时并入父级，只保留这 8 级。
RANKS = ['Realm', 'Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Genus', 'Species']
FAMILY_IDX = RANKS.index('Family')
GENUS_IDX = RANKS.index('Genus')
SPECIES_IDX = RANKS.index('Species')

# ------------------------------------------------- 非植物病毒科级黑名单
# 与 1.Prepare_plant_virus_pipeline/C4_clean_all_tsvs.py 保持一致
FUNGAL_FAMILIES = {
    "Chrysoviridae", "Oomyviridae", "Hypoviridae", "Mitoviridae",
    "Mymonaviridae", "Gammaflexiviridae", "Deltaflexiviridae",
    "Spiciviridae", "Botryosphaeriviridae",
    "Fusariviridae", "Hadakaviridae", "Yadokariviridae",
    "Polymycoviridae", "Megabirnaviridae", "Quadriviridae", "Barnaviridae",
    # Ambiguiviridae (Tolivirales): 宿主 fungi，MSL41 仅有植物际/土壤分离来源记录，
    # 无植物感染种（与 1.Prepare_plant_virus_pipeline/C4_clean_all_tsvs.py 保持一致）。
    "Ambiguiviridae",
}
INSECT_FAMILIES = {
    "Dicistroviridae", "Iflaviridae", "Baculoviridae", "Polydnaviridae",
    "Nimaviridae", "Tetraviridae", "Nodaviridae", "Mesoniviridae",
    "Xinmoviridae", "Bidnaviridae", "Hytrosaviridae",
    "Parvoviridae", "Artoviridae",
}
PHAGE_FAMILIES = {
    "Fiersviridae", "Microviridae", "Steitzviridae", "Duinviridae",
    "Straboviridae", "Autographiviridae", "Herelleviridae",
    "Peduoviridae", "Zierdtviridae",
    # Atkinsviridae / Solspiviridae (Norzivirales): MSL41 的 RNA 噬菌体科，
    # 宿主 bacteria，仅有植物/土壤分离来源记录（与 C4 保持一致）。
    "Atkinsviridae", "Solspiviridae",
}
OOMYCETE_FAMILIES = {"Oomyviridae", "Discoviridae"}
# 环境 CRESS-DNA：泛在背景，非宿主特异 —— 但 Geminiviridae/Nanoviridae 是真植物病毒
ENVIRONMENTAL_FAMILIES = {
    "Circoviridae", "Genomoviridae", "Kanorauviridae",
    "Ouroboviridae", "Draupnirviridae", "Smacoviridae",
}
TRUE_PLANT_CRESS_FAMILIES = {"Geminiviridae", "Nanoviridae"}

BLACKLIST_FAMILIES = (
    FUNGAL_FAMILIES | INSECT_FAMILIES | PHAGE_FAMILIES | OOMYCETE_FAMILIES
    | (ENVIRONMENTAL_FAMILIES - TRUE_PLANT_CRESS_FAMILIES)
)

# ------------------------------------- 内源逆转录转座子科 / 单条检出存疑科
# - Metaviridae / Pseudoviridae：gypsy（Athila/Del1/Tat4）与 copia（Tnt1/Tto1/Tos17）
#   型内源逆转录转座子。ICTV 出于系统发生学把它们纳入病毒分类，但这些"种"整合在
#   植物基因组内，无细胞外颗粒、无水平传播，不是感染植物的病原。
# - Pestiviridae：哺乳动物病毒科（猪瘟病毒/牛病毒性腹泻病毒所在科）。唯一 plants
#   记录为苦苣菜中检出的 Sonchus virus 1（Koshovirus sonchi，BK062903.1，TPA），
#   感染植物无证据。精选表中的该条记录保留（ICTV 官方分类单元），只是不计入
#   植物病毒科基线。
NON_PATHOGEN_PLANT_ELEMENT_FAMILIES = {"Metaviridae", "Pseudoviridae", "Pestiviridae"}
BLACKLIST_FAMILIES = BLACKLIST_FAMILIES | NON_PATHOGEN_PLANT_ELEMENT_FAMILIES

# ------------------------------------------------- 为什么不做属级黑名单
# C4_clean_all_tsvs.py 里的 FUNGAL_GENERA / INSECT_EXCLUDED_GENERA 等属级名单，
# 用途是「把序列从 Plant.tsv 移到 Fungi.tsv / Insecta.tsv」，是**文件归类**规则，
# 不是「该属不是植物病毒」的判定。直接拿来过滤会误杀真实的植物病毒属：
#   Fusagravirus  -> Fusagraviridae（Fusagravirus kyu / roku = 番木瓜乳汁病毒 PMeV）
#   Totivirus     -> Orthototiviridae（Totivirus jyukyu 等 4 种）
#   Magoulivirus / Penoulivirus -> Botourmiaviridae（Magoulivirus malus 等）
#   Ourmiavirus   -> Botourmiaviridae（C4 注释亦明确其为真植物病毒属）
# 因此本脚本**只做科级黑名单**，属/种一律以 VMR 的 Host source 种级标注为准。
# 边界情形见 README「判定口径与边界情形」一节。

# VMR Host source 中代表植物宿主的取值。
# 严格口径：只取「被感染宿主」值。带 (S) 后缀的是 ICTV 的「分离来源」
# （从植物叶面/植物际/土壤里分离到，宿主实为噬菌体/真菌病毒），不算植物病毒；
# 唯一仅靠 (S) 值进入名单的 Atkinsviridae / Solspiviridae / Ambiguiviridae
# 已同时列入科级黑名单，因此收紧前后科/属/种集合完全一致。
PLANT_HOST_SOURCES = {'plants', 'invertebrates, plants'}


def load_plant_species(vmr_path):
    """从 ICTV VMR 提取植物病毒种集合。"""
    plant_species = set()
    plant_families = collections.Counter()
    plant_genera = collections.defaultdict(set)
    fam_of_species = {}
    genus_of_species = {}
    genome_of_species = {}

    # 必须用 csv.reader：VMR 里含逗号的 Host source（如 "invertebrates, plants"）
    # 带引号存储，手工 split('\t') 会把引号留在值里导致整类记录静默丢失
    # （Sedoreoviridae / Spinareoviridae / Tospoviridae 曾因此全部漏判）。
    with open(vmr_path, encoding='utf-8', errors='replace', newline='') as f:
        rd = csv.reader(f, delimiter='\t', quotechar='"')
        hdr = [h.strip() for h in next(rd)]
        ci = {h: i for i, h in enumerate(hdr)}
        need = ['Host source', 'Family', 'Genus', 'Species', 'Genome']
        miss = [c for c in need if c not in ci]
        if miss:
            raise SystemExit(f'[FATAL] VMR 缺少列 {miss}\n实际列: {hdr}')

        hs_i, fa_i, ge_i, sp_i, gm_i = (ci[c] for c in need)
        width = max(hs_i, fa_i, ge_i, sp_i, gm_i)

        for c in rd:
            if len(c) <= width:
                continue
            sp = c[sp_i].strip()
            if not sp:
                continue
            fa = c[fa_i].strip()
            ge = c[ge_i].strip()
            # 记录种 -> 科/属/基因组（首次出现即可，同种多 isolate 值一致）
            fam_of_species.setdefault(sp, fa)
            genus_of_species.setdefault(sp, ge)
            if c[gm_i].strip():
                genome_of_species.setdefault(sp, c[gm_i].strip())

            if c[hs_i].strip() not in PLANT_HOST_SOURCES:
                continue
            if fa in BLACKLIST_FAMILIES:
                continue
            plant_species.add(sp)
            if fa:
                plant_families[fa] += 1
            if ge:
                plant_genera[fa].add(ge)

    return plant_species, plant_families, plant_genera, fam_of_species, genome_of_species


def load_msl(msl_path):
    """读 MSL41 主表，返回 species 记录列表。"""
    recs = []
    with open(msl_path, encoding='utf-8') as f:
        hdr = f.readline().rstrip('\n').split('\t')
        ci = {h: i for i, h in enumerate(hdr)}
        for line in f:
            c = line.rstrip('\n').split('\t')
            if len(c) < len(hdr):
                c += [''] * (len(hdr) - len(c))
            rec = {r: c[ci[r]].strip() for r in RANKS}
            rec['Genome'] = c[ci['Genome']].strip() if 'Genome' in ci else ''
            rec['ICTV_ID'] = c[ci['ICTV_ID']].strip() if 'ICTV_ID' in ci else ''
            if rec['Species']:
                recs.append(rec)
    return recs


def build_tree(recs, plant_species, genome_of_species):
    """
    构建嵌套树。节点字段（短键名以压缩 JSON）:
      n  name           r  rank           ch children
      pc plant species count (子树内植物病毒种数)
      g  genome (仅科级)   ic ICTV_ID (仅种级)
    """
    root = {'n': 'Viruses', 'r': 'root', 'ch': []}
    nodes = {}          # (realm,...,family,genus) -> node
    stat_missing = collections.Counter()

    for rec in recs:
        parent = root
        path_key = []
        for i, rank in enumerate(RANKS):
            name = rec[rank]
            if not name:
                stat_missing[rank] += 1
                # 缺失层级直接跳过（不生成占位节点），保持树形简洁
                continue
            path_key.append(name)
            key = tuple(path_key)
            node = nodes.get(key)
            if node is None:
                node = {'n': name, 'r': rank.lower(), 'ch': []}
                if rank == 'Family':
                    node['g'] = ''
                nodes[key] = node
                parent['ch'].append(node)
            parent = node
            if rank == 'Species':
                node['ic'] = rec.get('ICTV_ID', '')
                node['p'] = 1 if name in plant_species else 0
                if not node.get('g'):
                    gm = rec.get('Genome') or genome_of_species.get(name, '')
                    if gm:
                        node['g'] = gm

    # 科级补基因组类型（用该科第一个种的 Genome，混合科以多数为准）
    fam_genome = collections.defaultdict(collections.Counter)
    for key, node in nodes.items():
        if node['r'] == 'species' and len(key) >= 6:
            fam = key[5]
            if node.get('g'):
                fam_genome[fam][node['g']] += 1
    for key, node in nodes.items():
        if node['r'] == 'family':
            c = fam_genome.get(node['n'])
            if c:
                node['g'] = c.most_common(1)[0][0]

    # 自底向上统计植物病毒种数
    def count(node):
        if node['r'] == 'species':
            node['pc'] = node.get('p', 0)
            return node['pc']
        total = sum(count(ch) for ch in node['ch'])
        node['pc'] = total
        return total

    count(root)

    # 剪枝策略（2026-09-22 按老师口径调整）：
    #   · 非植物病毒分支（pc==0）在**目级**停止展开 —— 仍以灰色节点显示它在病毒界中的位置，
    #     但不再往下铺科/属/种。若一路铺到科级，单是灰色科就有 379 个，整棵树会被撑到 7000px 以上。
    #   · **保留「与植物病毒同目」的非植物病毒科** —— 口径是「父节点是含植物病毒的目（pc>0）」。
    #     它们以灰色**叶**节点出现（下面的第一个分支会摘掉它们的 ch），能看到"这个目里还有哪些非植物病毒科"，
    #     但展不开 —— 本库没有它们的属/种。这是 2026-09-22 老师选的口径；
    #     原先这些科也被剪掉，页面上就看不到任何非植物病毒的科。
    #   · **属一级仍只保留「有植物病毒种」的**；否则混合目下的灰色属会再翻几倍。
    #   · 属以下保留全部种：混合属里既可能是植物种（彩色）也可能是非植物种（灰色）。
    #
    # 为什么限定 `node['r'] == 'order'` 而不是宽松的 `node['pc'] > 0`（实测差别很大）：
    #   MSL41 里 5,263 条记录**没有 Order**，`build_tree()` 会跳过缺失层级把科直接挂到最近的已知层 ——
    #   于是 `Caudoviricetes`（纲）下直接挂了 91 个噬菌体科、根 `Viruses` 下直接挂了 25 个古菌噬菌体科。
    #   若按 `pc > 0` 保留，那 25 个会作为灰色科出现在**域那一层**（根的其它子节点全是 realm），
    #   既不是「同目」，视觉上也会误导。所以严格限定父节点是「目」。
    #   实测：严格口径 +73 个科；宽松口径 +195 个（多出的 95 个在 pc==0 的纲/域下，25 个在根下）。
    RANK_IDX = {'root': 0, 'realm': 1, 'kingdom': 2, 'phylum': 3,
                'class': 4, 'order': 5, 'family': 6, 'genus': 7, 'species': 8}

    def prune(node):
        if node['pc'] == 0 and RANK_IDX.get(node['r'], 0) >= RANK_IDX['order']:
            node.pop('ch', None)
            return

        # 本节点是不是「含植物病毒的目」—— 只有它的 pc==0 科才保留
        mixed_order = (node['r'] == 'order' and node['pc'] > 0)

        def keep(c):
            if c.get('pc', 0) > 0:
                return True                 # 有植物病毒种：一律保留
            if c['r'] == 'genus':
                return False                # 无植物种的属：剪掉
            if c['r'] == 'family':
                return mixed_order          # 无植物种的科：只有混合目下的才保留
            return True

        kids = [c for c in node.get('ch', []) if keep(c)]
        if kids:
            node['ch'] = kids
            for c in kids:
                prune(c)
        else:
            node.pop('ch', None)

    prune(root)
    return root, nodes, stat_missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--msl', default='data/MSL41_species.tsv')
    ap.add_argument('--vmr', default='../../oneoff_scripts/_bench_b1_20260919/vmr.tsv')
    ap.add_argument('--out', default='taxonomy_tree.json')
    ap.add_argument('--plant-list', default='data/plant_taxa.tsv')
    args = ap.parse_args()

    for p in (args.msl, args.vmr):
        if not os.path.exists(p):
            raise SystemExit(f'[FATAL] 找不到 {p}')

    print('[1/4] 读取 VMR 判定植物病毒 ...')
    plant_species, plant_families, plant_genera, fam_of_species, genome_of_species = load_plant_species(args.vmr)
    print(f'      植物病毒种 {len(plant_species)} / 科 {len(plant_families)} / 属 {sum(len(v) for v in plant_genera.values())}')

    print('[2/4] 读取 MSL41 主表 ...')
    recs = load_msl(args.msl)
    print(f'      species 记录 {len(recs)}')

    print('[3/4] 构建分类树 ...')
    root, nodes, stat_missing = build_tree(recs, plant_species, genome_of_species)
    n_nodes = len(nodes)
    n_plant_species = sum(1 for k, v in nodes.items() if v['r'] == 'species' and v.get('p'))
    matched = sum(1 for k, v in nodes.items() if v['r'] == 'species' and v.get('p'))
    print(f'      节点总数 {n_nodes}，其中植物病毒种 {n_plant_species}')
    print(f'      VMR 植物种中能在 MSL41 命中的: {matched} / {len(plant_species)}')
    if stat_missing:
        print(f'      层级缺失计数: {dict(stat_missing)}')

    meta = {
        'source_msl': 'ICTV Master Species List 2025 MSL41 v1',
        'source_vmr': os.path.basename(args.vmr),
        'ranks': RANKS,
        'plant_species': n_plant_species,
        'plant_families': len(plant_families),
        'plant_genera': sum(len(v) for v in plant_genera.values()),
        'total_species': len(recs),
        'total_nodes': n_nodes,
        'vmr_plant_species': len(plant_species),
        'vmr_plant_species_matched': matched,
        'plant_family_list': sorted(plant_families),
        'plant_genus_list': sorted(g for gens in plant_genera.values() for g in gens),
    }

    print('[4/4] 写出 ...')
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump({'meta': meta, 'tree': root}, f, ensure_ascii=False, separators=(',', ':'))
    size = os.path.getsize(args.out)
    print(f'      {args.out}  {size/1024:.0f} KB')

    os.makedirs(os.path.dirname(os.path.abspath(args.plant_list)), exist_ok=True)
    with open(args.plant_list, 'w', encoding='utf-8') as f:
        f.write('rank\tfamily\tgenus\tspecies\n')
        for sp in sorted(plant_species):
            f.write(f'species\t{fam_of_species.get(sp,"")}\t\t{sp}\n')
        for fa, gens in sorted(plant_genera.items()):
            for ge in sorted(gens):
                f.write(f'genus\t{fa}\t{ge}\t\n')
    print(f'      {args.plant_list}')


if __name__ == '__main__':
    main()
