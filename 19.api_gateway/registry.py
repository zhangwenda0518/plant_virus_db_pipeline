# -*- coding: utf-8 -*-
"""API v1 数据集注册表 —— 全平台数据资产在这里声明。

三类注册：
- DATASETS     走 SQLite 查询引擎的表（TSV/CSV/JSON 列表，支持过滤/搜索/分页）
- PASSTHROUGH  小中型结构化 JSON 文档原样透出（ETag 缓存，?pretty 可选）
- CUSTOM_ROUTES  手写端点（复合数据/详情页），仅声明元数据供目录与 OpenAPI 使用

路径均相对仓库根（服务器 = /opt/plant_virus_db/plant_virus_db_pipeline）。
filter 列支持精确过滤，search 列支持 ?q= 模糊搜索，numeric 列排序按数值。
"""
import json
import os

# ---------------------------------------------------------------------------
# 复合数据集的行生成器（format='custom'）
# ---------------------------------------------------------------------------

def _associations_pairs(root):
    """宿主-病毒关联对：pairs 三元组与 vtax/htax 分类学在构建期 join 成宽表。"""
    with open(os.path.join(root, 'docs/association/associations.json'),
              encoding='utf-8') as fh:
        doc = json.load(fh)
    vtax, htax = doc.get('vtax', {}), doc.get('htax', {})
    for virus, host, count in doc.get('pairs', []):
        v = vtax.get(virus, [None, None, None])
        h = htax.get(host, [None, None, None])
        yield {'virus': virus, 'host': host, 'pairs': count,
               'virus_order': v[0] if len(v) > 0 else None,
               'virus_family': v[1] if len(v) > 1 else None,
               'virus_genus': v[2] if len(v) > 2 else None,
               'host_group': h[0] if len(h) > 0 else None,
               'host_order': h[1] if len(h) > 1 else None,
               'host_family': h[2] if len(h) > 2 else None}


def _network_triplets(root):
    """病毒-媒介-宿主三元组（mode 序号解析为传播方式标签）。"""
    with open(os.path.join(root, 'docs/network/network.json'), encoding='utf-8') as fh:
        doc = json.load(fh)
    modes = doc.get('modes', [])
    for virus, vector, host, mode_idx, taxids in doc.get('vh', []):
        yield {'virus': virus, 'vector': vector, 'host': host,
               'mode': modes[mode_idx] if isinstance(mode_idx, int) and 0 <= mode_idx < len(modes) else mode_idx,
               'taxids': json.dumps(taxids, ensure_ascii=False)}


def _pamir_mirnas(root):
    """全量植物 miRNA（80,783 条）：dict 键即 miRNA id。"""
    with open(os.path.join(root, '12.pamirdb/data/mirna/plant_mirnas_full.json'),
              encoding='utf-8') as fh:
        data = json.load(fh)
    for mirna_id, v in data.items():
        yield {'mirna_id': mirna_id, 'sequence': v.get('sequence'),
               'species_code': v.get('species_code'), 'species_name': v.get('species_name'),
               'length': v.get('length')}


def _pamir_genomes(root):
    """病毒基因组（含基因注释统计）：列表视图不含 genes 明细。"""
    with open(os.path.join(root, '12.pamirdb/data/virus_genomes/viruses_full_annotated.json'),
              encoding='utf-8') as fh:
        data = json.load(fh)
    for acc, v in data.items():
        genes = v.get('genes') or []
        yield {'accession': acc, 'name': v.get('name'), 'family': v.get('family'),
               'genome_length': v.get('genome_length'), 'n_genes': len(genes)}


def _rvpsd_species(root):
    with open(os.path.join(root, '14.rvpsd_structures/webapp/data/structures_index.json'),
              encoding='utf-8') as fh:
        doc = json.load(fh)
    for sp in doc.get('species', []):
        yield {'name': sp.get('name'), 'family': sp.get('family'),
               'abbrev': sp.get('abbrev'), 'count': sp.get('count'),
               'n_proteins': len(sp.get('proteins') or [])}


def _rvpsd_proteins(root):
    with open(os.path.join(root, '14.rvpsd_structures/webapp/data/structures_index.json'),
              encoding='utf-8') as fh:
        doc = json.load(fh)
    for sp in doc.get('species', []):
        for p in sp.get('proteins', []):
            yield {'acc': p.get('acc'), 'species': sp.get('name'),
                   'family': sp.get('family'), 'product': p.get('product'),
                   'plddt': p.get('plddt'), 'host': p.get('host'), 'fas': p.get('fas')}


def _vad_species(root):
    with open(os.path.join(root, '14.rvpsd_structures/webapp/data/vad_index.json'),
              encoding='utf-8') as fh:
        doc = json.load(fh)
    for sp in doc.get('species', []):
        yield {'key': sp.get('key'), 'name': sp.get('name'), 'taxid': sp.get('taxid'),
               'clade': sp.get('clade'), 'host': sp.get('host'),
               'n_proteins': len(sp.get('proteins') or [])}


def _uniprot_proteins(root):
    """UniProt 结构条目：短键名展开为可读列。"""
    with open(os.path.join(root, '15.uniprot_plant_virus_structures/webapp/data/proteins.json'),
              encoding='utf-8') as fh:
        items = json.load(fh)
    for p in items:
        yield {'accession': p.get('a'), 'entry': p.get('e'),
               'organism': p.get('o'), 'length': p.get('L'),
               'rvpsd_model': p.get('rv'), 'afdb': p.get('af'),
               'selffold': p.get('sf'), 'bfvd': p.get('bf'),
               'sources': json.dumps(p.get('s') or [], ensure_ascii=False),
               'pdb_ids': json.dumps(p.get('p') or [], ensure_ascii=False)}


def _uniprot_reps(root):
    with open(os.path.join(root, '15.uniprot_plant_virus_structures/webapp/data/genome.json'),
              encoding='utf-8') as fh:
        doc = json.load(fh)
    for r in doc.get('reps', []):
        yield {'rep_id': r.get('a'), 'virus': r.get('v'), 'protein_id': r.get('p'),
               'length': r.get('L'), 'sources': json.dumps(r.get('s') or [], ensure_ascii=False),
               'n_models': len(r.get('m') or [])}


def _compounds(root):
    with open(os.path.join(root, 'docs/data/antivirals.json'), encoding='utf-8') as fh:
        doc = json.load(fh)
    for c in doc.get('compounds') or []:
        yield {'name': c.get('name'),
               'n_viruses': c.get('n_viruses'), 'n_pairs': c.get('n_pairs'),
               'n_papers': c.get('n_papers')}


# ---------------------------------------------------------------------------
# DATASETS —— 查询引擎表
# 字段：id 全局唯一；path 相对仓库根；filter 精确过滤列；search ?q= 列；
#       numeric 数值排序列；pk 单条详情路由列；default_exclude 默认不返回的大字段
# ---------------------------------------------------------------------------

DATASETS = [
    # ============ reference 参考序列库 ============
    dict(id='reference.sequences', path='docs/data/Plant_Virus_Full.Info.tsv', format='tsv',
         description='All 211,132 plant-virus GenBank sequence records with taxonomy, host and metadata (main table).',
         pk='Accession', filter=['Family', 'Species_NCBI', 'Species_ICTV', 'Host', 'Molecule_type',
                                 'Sequence_Type', 'Segment', 'Nuc_Completeness', 'NCBI_Status', 'Segment_std'],
         search=['Accession', 'Species_NCBI', 'GenBank_Title', 'Host'], numeric=['Length', 'Taxid']),
    dict(id='reference.refseqs', path='docs/data/Plant_Virus_Ref.Info.tsv', format='tsv',
         description='9,022 curated reference-sequence records cross-referenced with ICTV VMR MSL41.',
         pk='Accession', filter=['Family', 'Species_NCBI', 'Species_ICTV', 'Category', 'Sequence_Type',
                                 'VMR_Species', 'VMR_Family', 'VMR_Genus', 'Segment_std', 'Nuc_Completeness'],
         search=['Accession', 'Species_NCBI', 'Virus name(s)'], numeric=['Length', 'Taxid']),
    dict(id='reference.clusters', path='docs/data/final.cluster.ref_info.tsv', format='tsv',
         description='8,465 species-level clustering representative sequences (vsearch 99%).',
         pk='Accession', filter=['Family', 'Species_NCBI', 'VMR_Family', 'VMR_Genus'],
         search=['Accession', 'Species_NCBI'], numeric=['Length']),
    dict(id='reference.complete', path='docs/data/Plant_Virus.complete_ref_info.tsv', format='tsv',
         description='5,773 complete reference genomes.',
         pk='Accession', filter=['Family', 'Species_NCBI', 'VMR_Family', 'VMR_Genus'],
         search=['Accession', 'Species_NCBI'], numeric=['Length']),
    dict(id='reference.names', path='docs/data/name_mapping.tsv', format='tsv',
         description='49,304 virus name mappings: lookup key, ICTV name, common name, abbreviation.',
         pk='Lookup_Key', filter=[], search=['Lookup_Key', 'ICTV_Name', 'Common_Name', 'Abbreviation']),
    dict(id='reference.species-canonical', path='docs/data/species_canonical.tsv', format='tsv',
         description='Accession to canonical species assignment with the rule that decided it.',
         pk='Accession', filter=['canonical', 'by'], search=['Accession', 'canonical']),
    dict(id='reference.species-crosswalk', path='docs/data/species_crosswalk.tsv', format='tsv',
         description='ICTV species crosswalk across modules: primer/vector/photo/symptom DB membership and counts.',
         pk='ictv_name', filter=['origin', 'in_primer_taxonomy', 'in_vector_db', 'in_photo_db', 'in_symptom_db'],
         search=['ictv_name', 'ncbi_names'], numeric=['ref_records', 'ref_complete', 'primers_count']),
    dict(id='reference.segments', path='docs/data/segment_canonical.tsv', format='tsv',
         description='Accession to standardized segment naming with style and source.',
         pk='Accession', filter=['Segment_Std2', 'Style', 'Source'], search=['Accession']),

    # ============ taxonomy 分类 ============
    dict(id='taxonomy.vmr', path='docs/data/VMR_MSL41.txt', format='tsv',
         description='ICTV Virus Metadata Resource MSL41: 19,271 isolates with full realm-to-species lineage and hosts.',
         filter=['Realm', 'Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Subfamily', 'Genus',
                 'Species', 'Exemplar or additional isolate', 'Host source'],
         search=['Species', 'Virus name(s)', 'Isolate ID'], numeric=['Species Sort']),
    dict(id='taxonomy.species', path='docs/phylo/data/MSL41_species.tsv', format='tsv',
         description='17,554 ICTV MSL41 virus species with full lineage and genome type.',
         pk='Species', filter=['Realm', 'Phylum', 'Class', 'Order', 'Family', 'Subfamily', 'Genus', 'Genome'],
         search=['Species', 'ICTV_ID']),
    dict(id='taxonomy.plant-taxa', path='docs/phylo/data/plant_taxa.tsv', format='tsv',
         description='2,837 plant taxa (42 families / 200 genera / 2,637 species, ICTV MSL41 strict plant-host baseline).',
         filter=['rank', 'family', 'genus'], search=['species', 'family', 'genus']),
    dict(id='taxonomy.plant-crosswalk', path='docs/data/plant_virus_taxonomy_crosswalk.tsv', format='tsv',
         description='ICTV↔NCBI crosswalk for the 42 plant-virus families: 3,632 species with ICTV_ID, genome type, '
                     'VMR host source, NCBI taxids/names and full/ref record coverage (2,637 strict-baseline + '
                     '995 family-associated species).',
         pk='Species_ICTV', filter=['Family', 'Genus', 'Genome', 'VMR_Host_source', 'In_strict_baseline'],
         search=['Species_ICTV', 'NCBI_Names', 'ICTV_ID'], numeric=['Full_records', 'Ref_records', 'Complete_records']),

    # ============ hosts 宿主分析 ============
    dict(id='hosts.range', path='docs/data/host_analysis/virus_host_range.tsv', format='tsv',
         description='Host range per virus species: number of host plants and the full host list.',
         pk='Species', filter=['Family', 'Host_Range'], search=['Species', 'Host_List'], numeric=['Num_Hosts']),
    dict(id='hosts.range-summary', path='docs/data/host_analysis/virus_host_range_summary.tsv', format='tsv',
         description='Host-range aggregate per virus family (46 families).',
         pk='Family', filter=[], search=['Family'], numeric=['Num_Species', 'Total_Hosts']),
    dict(id='hosts.frequency', path='docs/data/host_analysis/host_frequency.tsv', format='tsv',
         description='Host plant frequency across all virus records (200 hosts).',
         pk='Host', filter=[], search=['Host'], numeric=['Count', 'Percentage']),

    # ============ primers 引物库 ============
    dict(id='primers.catalog', path='docs/data/primers/primer_reference.tsv', format='tsv',
         description='103,642 designed PCR/qPCR primer pairs with Tm, GC, degeneracy, tiling and method.',
         pk='Pair_ID', filter=['Species', 'Type', 'Segment', 'Family', 'Genus', 'Method'],
         search=['Species', 'Pair_ID', 'Fwd_Seq', 'Rev_Seq'], numeric=['Num_Seqs', 'Total_Degeneracy', 'Product']),
    dict(id='primers.top-species', path='docs/data/primers/primer_top_species.tsv', format='tsv',
         description='Top 20 species by primer count.',
         pk='Species', filter=[], search=['Species', 'Family'], numeric=['Num_Primers']),
    dict(id='primers.stats', path='docs/data/primers/primer_summary.tsv', format='tsv',
         description='Primer collection summary metrics.',
         pk='Metric', filter=[], search=['Metric', 'Value']),

    # ============ gallery 症状图库 ============
    dict(id='gallery.photos', path='docs/data/unified_gallery.json', format='json_list',
         description='2,975 curated symptom photos (DPV/EPPO/Book/PDF/Open-i). List fields are JSON arrays; filter them with q=.',
         pk='code', filter=['source'], search=['virus', 'virus_latin', 'virus_ictv', 'caption',
                                               'hosts', 'hosts_latin', 'symptoms', 'symptoms_std']),
    dict(id='symptoms.table', path='docs/data/symptom_table.json', format='json_list',
         description='3,818 virus-host symptom records with standardized symptom and tissue vocabularies.',
         filter=['source', 'family'], search=['virus', 'host_cn', 'host_latin', 'symptoms', 'symptoms_std', 'parts_std']),

    # ============ compounds 抗病毒化合物 ============
    # 列表与详情走手写端点 /api/v1/compounds、/api/v1/compounds/{name}（app.py），
    # 因为 /api/v1/compounds/<x> 会被详情路由优先匹配，无法再挂通用数据集路由。
    # _compounds() 生成器同时被手写端点复用。

    # ============ eve 内源性病毒 ============
    dict(id='eve.audit.host-families', path='docs/eve/data/_audit/host_families.tsv', format='tsv',
         description='EVE loci/genomes per 284 host families with plant group and top virus families.',
         pk='host_family', filter=['plant_group', 'order'], search=['host_family'], numeric=['loci', 'genomes', 'rna_loci', 'cauli_loci']),
    dict(id='eve.audit.matrix', path='docs/eve/data/_audit/matrix_host_virus.tsv', format='tsv',
         description='Host-family x virus-family EVE loci matrix (390 non-zero cells).',
         filter=['host_family', 'virus_family'], search=['host_family', 'virus_family'], numeric=['loci']),
    dict(id='eve.audit.virus-taxa', path='docs/eve/data/_audit/virus_taxa.tsv', format='tsv',
         description='EVE loci/genomes per 25 viral families with genome type and top hosts.',
         pk='viral_family', filter=['genome_type'], search=['viral_family', 'top_hosts'], numeric=['loci', 'genomes', 'host_families']),
    dict(id='eve.audit.unmapped-genomes', path='docs/eve/data/_audit/unmapped_genomes.tsv', format='tsv',
         description='Genomes without taxonomy mapping in the EVE audit.',
         pk='genome', filter=[], search=['genome'], numeric=['viral_supported_loci']),

    # ============ genes 抗病基因 ============
    dict(id='genes.master', path='docs/genes/data/plant_antiviral_genes_master.tsv', format='tsv',
         description='12,606 plant antiviral-related genes (master table: NLR, sRNA pathway, UPS, miRNA genes).',
         pk='GeneID', filter=['Family', 'GeneType', 'Species'],
         search=['Symbol', 'FullName', 'Species'], ),
    dict(id='genes.srna', path='docs/genes/data/sRNA_all_genes.tsv', format='tsv',
         description='11,781 RNA-silencing pathway genes (AGO/DCL/RDR/DRB/HEN1/SGS3/SE/Other).',
         pk='GeneID', filter=['Family', 'Species', 'Chromosome'],
         search=['Symbol', 'FullName', 'OtherAliases']),
    dict(id='genes.ups', path='docs/genes/data/UPS_all_genes.tsv', format='tsv',
         description='3,996 ubiquitin-proteasome system genes.',
         pk='GeneID', filter=['Family', 'Species'], search=['Symbol', 'FullName']),
    dict(id='genes.nlr', path='docs/genes/data/NLR_all_genes.tsv', format='tsv',
         description='NLR immune receptor genes with domain type and validation status.',
         pk='GeneID', filter=['DomainType', 'Validated', 'Species'], search=['Symbol', 'FullName']),
    dict(id='genes.mirna', path='docs/genes/data/miRNA_genes.tsv', format='tsv',
         description='337 miRNA genes.',
         pk='GeneID', filter=['Species'], search=['Symbol', 'FullName']),
    dict(id='genes.vsirna', path='docs/genes/data/pvsirnadb_vsirna.tsv', format='tsv',
         description='322,214 virus-derived siRNAs from PVsiRNAdb: plant, virus, tissue and sequence.',
         pk='PVsiRNA_ID', filter=['Plant_Common', 'Plant_Scientific', 'Virus_Abbr', 'Virus_Name', 'Tissue'],
         search=['Virus_Name', 'Virus_Abbr', 'Plant_Scientific', 'Sequence']),
    dict(id='genes.mirna-targets', path='docs/genes/data/plantrg_mirna_targets.tsv', format='tsv',
         description='128,925 plant miRNA-to-viral-target predictions with alignment and score.',
         filter=['Species'], search=['miRNA_ID', 'Target_Gene', 'miRNA_Sequence'], numeric=['Score']),

    # ============ associations 宿主-病毒关联 ============
    dict(id='associations.pairs', path=None, format='custom', records=_associations_pairs,
         description='15,197 host-virus association pairs with full taxonomy on both sides (source: 208,477 GenBank records).',
         filter=['virus_family', 'virus_genus', 'virus_order', 'host_family', 'host_genus',
                 'host_order', 'host_group'],
         search=['virus', 'host'], numeric=['pairs']),

    # ============ network 关系网络 ============
    dict(id='network.triplets', path=None, format='custom', records=_network_triplets,
         description='1,375 virus-vector-host transmission triplets with resolved transmission mode.',
         filter=['mode'], search=['virus', 'vector', 'host']),

    # ============ vectors 媒介库（8.plant-insect）============
    dict(id='vectors.triplets', path='8.plant-insect/virus_vector_host.tsv', format='tsv',
         description='1,375 validated virus-vector-host records with DOI evidence and transmission mode.',
         filter=['Virus Family', 'Virus Genus', 'Vector Order', 'Vector Family', 'Vector Genus',
                 'Vector', 'Virus Transmission Mode'],
         search=['Virus Name', 'Vector', 'Virus Host'],
         default_exclude=['DOI for Validation Virus-Insect Relationships',
                          'DOI for Validation Virus Transmission Mode', 'Lineage']),
    dict(id='vectors.wur', path='8.plant-insect/wur_virus_full.tsv', format='tsv',
         # 2026-10-26: scrape_wur.py 重建后新增两列 —— modes(受控词表, 72% 非空) 与
         # duplicated(重名标记)。transmission 保留为原文全量文本(97% 非空)，语义未变。
         description='1,654 Rothamsted WUR virus-vector records: vector organism, transmission, references.',
         filter=['family', 'genus', 'transmission', 'modes', 'duplicated'],
         search=['name', 'vector_org', 'modes'],
         default_exclude=['refs']),

    # ============ pamir 植物 miRNA ============
    dict(id='pamir.mirnas', path=None, format='custom', records=_pamir_mirnas,
         description='80,783 plant mature miRNAs (full library; the /pamirdb/ demo subset is only 134).',
         pk='mirna_id', filter=['species_code', 'species_name'], search=['mirna_id'], numeric=['length']),
    dict(id='pamir.predictions', path='12.pamirdb/data/predictions_v7_annotated.json', format='json_list',
         record_path=['results'],
         description='11,006 miRNA-to-viral-genome consensus predictions (v7): algorithms, seed quality, alignment, gene annotation.',
         pk=None, filter=['consensus_level', 'target_virus_family', 'targeting_status', 'targeting_category', 'num_algorithms'],
         search=['mirna_id', 'target_virus_name', 'target_gene'],
         numeric=['num_algorithms', 'best_energy', 'seed_quality_score', 'alignment_length'],
         default_exclude=['consensus_detail', 'miranda_detail', 'psrnatab_detail', 'rnahybrid_detail']),
    dict(id='pamir.virus-hosts', path='12.pamirdb/data/virus_host/virus_host.csv', format='csv',
         description='22 virus-host curated pairs used by PAmiRDB.',
         pk='virus_id', filter=[], search=['virus_name', 'host_species', 'host_common_name']),

    # ============ literature 文献 ============
    dict(id='literature.papers', path='7.literature_tracker/data/papers.json', format='json_list',
         record_path=['papers'],
         description='33,325 tracked plant-virus papers (PubMed daily harvest). Full record: fields=abstract.',
         pk='pmid', filter=['year', 'relevant', 'ai_done', 'journal'],
         search=['title', 'first_author', 'doi'], numeric=['year'],
         default_exclude=['abstract', 'authors', 'categories']),
    dict(id='literature.curated', path='7.literature_tracker/web/data/data.json', format='json_list',
         description='6,525 AI deep-read papers: extracted virus, taxonomy, host, vector, methods, results.',
         pk='pmid', filter=['year', 'journal', 'source', 'source_strategy'],
         search=['title', 'virus_name', 'host_plant', 'first_author'], numeric=['year'],
         default_exclude=['abstract', 'overview', 'methods', 'results', 'discussion', 'authors', 'categories']),

    # ============ structures 结构 ============
    dict(id='structures.rvpsd.species', path=None, format='custom', records=_rvpsd_species,
         description='2,603 virus species in the RVPSD model atlas (protein count per species). Detail: /api/v1/structures/rvpsd/species/{name}.',
         pk='name', filter=['family'], search=['name'], numeric=['count', 'n_proteins']),
    dict(id='structures.rvpsd.proteins', path=None, format='custom', records=_rvpsd_proteins,
         description='20,950 predicted protein models with pLDDT and source (RVPSD/vpSAT/AFDB).',
         pk='acc', filter=['species', 'family', 'host'], search=['acc', 'product'], numeric=['plddt']),
    dict(id='structures.vad.species', path=None, format='custom', records=_vad_species,
         description='328 virus-associated domain (VAD) species with 2,033 proteins.',
         pk='key', filter=['clade', 'host'], search=['name'], numeric=['taxid', 'n_proteins']),
    dict(id='structures.uniprot.proteins', path=None, format='custom', records=_uniprot_proteins,
         description='4,810 UniProt plant-virus proteins with all structure sources (PDB/AFDB/BFVD/RVPSD/SelfFold).',
         pk='accession', filter=[], search=['accession', 'entry', 'organism'], numeric=['length']),
    dict(id='structures.uniprot.reps', path=None, format='custom', records=_uniprot_reps,
         description='11,017 representative protein clusters across 9,022 reference genomes.',
         pk='rep_id', filter=[], search=['rep_id', 'virus', 'protein_id'], numeric=['length', 'n_models']),
    dict(id='structures.uniprot.coverage', path='15.uniprot_plant_virus_structures/webapp/data/virus_coverage.json',
         format='json_list',
         description='Per-organism structure coverage (413 organisms): PDB/AFDB/RVPSD/BFVD counts and percentages.',
         pk='organism', filter=[], search=['organism'],
         numeric=['n_proteins', 'n_pdb', 'n_afdb', 'n_rvpsd', 'own_pct', 'any_pct']),

    # ============ proteomes 基因组/蛋白组 ============
    dict(id='proteomes.coverage', path='17.genome_proteome/coverage_report.tsv', format='tsv',
         description='11,017 representative proteins with structure-source coverage flags.',
         pk='rep_id', filter=['covered', 'rvpsd', 'pdb', 'afdb', 'bfvd'],
         search=['rep_id', 'protein_id', 'uniprot']),
    dict(id='proteomes.reps', path='17.genome_proteome/reps50_with_pid.tsv', format='tsv',
         description='50%-identity representative sequences with RVPSD hit flag.',
         pk='protein_id', filter=['rvpsd_hit'], search=['rep_header', 'protein_id']),
]

# ---------------------------------------------------------------------------
# PASSTHROUGH —— 结构化 JSON 文档原样透出（支持 ?pretty，ETag 协商缓存）
# ---------------------------------------------------------------------------

PASSTHROUGH = {
    'stats': {
        'platform': ('docs/data/platform_stats.json', '17 platform-level headline stats (monthly refresh).'),
        'dashboard': ('docs/data/dashboard_stats.json', 'Reference DB KPIs and distributions (full vs ref).'),
        'charts': ('docs/data/chart_data.json', 'Lightweight chart aggregates for the portal.'),
        'site': ('docs/data/site_stats.json', 'Legacy 7-item site stats.'),
        'visitors': ('docs/data/visitor_map.json', 'Visitor countries (privacy-light aggregate).'),
        'ingest': ('docs/data/incremental_status.json', 'NCBI monthly incremental ingest status.'),
    },
    'geo': {
        'world': ('docs/data/world.json', 'World GeoJSON used by the map views (1 MB).'),
    },
    'eve': {
        'landscape': ('docs/eve/data/eve_landscape.json', 'EVE overview: 150,136 loci, taxa, host families, matrices.'),
        'phylo': ('docs/eve/data/eve_phylo.json', 'EVE RT phylogeny: Newick tree and nearest-reference analysis.'),
        'dynamics': ('docs/eve/data/eve_dynamics.json', 'EVE past/present quadrants, amplification and rarefaction.'),
    },
    'genes': {
        'classified': ('docs/genes/data/all_genes_classified.json', 'All classified genes: nlr/srna/ups/mirna arrays.'),
        'refplant': ('docs/genes/data/refplant_nlr_data.json', 'RefPlantNLR 415 genes with domains, exons and structure.'),
        'nlr-validated': ('docs/genes/data/antiviral_nlr_validated.json', '59 experimentally validated antiviral NLRs.'),
        'uniprot-refs': ('docs/genes/data/nlr_uniprot_refs.json', 'UniProt NLR entries with PMID references.'),
        'ups-references': ('docs/genes/data/ups_references.json', 'UPS family definitions and key references.'),
        'manifest': ('docs/genes/data/files_manifest.json', 'Download manifest of all gene-module files.'),
    },
    'associations': {
        'stats': ('docs/association/associations.json', 'Full association document: meta/stats, vtax, htax, pairs. '
                  'For queryable pairs use dataset associations.pairs.'),
    },
    'network': {
        'graph': ('docs/network/network.json', 'Full network document: triplets, taxonomies, aliases, DOIs, links.'),
    },
    'phylo': {
        'taxonomy': ('docs/phylo/taxonomy_tree.json', 'ICTV taxonomy tree: 22,328 nodes, 17,554 species.'),
        'molecular': ('docs/phylo/molecular_trees.json', '38 molecular trees across 25 families (Newick + stats).'),
        'families': ('docs/phylo/molecular/families/family_index.json', 'Per-family tree index with coverage stats.'),
        'genus-map': ('docs/phylo/molecular/genus_map.json', 'Leaf-label to genus mapping for all molecular trees.'),
        'ictv-manifest': ('docs/phylo/ictv_raw/manifest.json', 'Local mirror manifest of ICTV alignments/trees.'),
    },
    'pamir': {
        'stats': ('12.pamirdb/data/mirna/plant_mirnas_full_stats.json', 'miRNA library totals.'),
        'viral-mirnas': ('12.pamirdb/data/viral_mirnas.json', 'Known viral miRNAs by virus.'),
    },
    'literature': {
        'years': ('7.literature_tracker/web/data/index.json', 'Per-year curated paper counts and files.'),
        'stats': ('7.literature_tracker/web/data/stats.json', 'Curated vs master corpus totals and by-year counts.'),
        'trends': ('7.literature_tracker/web/data/trend_milestones.json', 'Research-trend milestones extracted by AI.'),
    },
    'structures': {
        'uniprot-stats': ('15.uniprot_plant_virus_structures/webapp/data/stats.json', 'UniProt atlas build stats.'),
        'fullatom-map': ('14.rvpsd_structures/webapp/data/fullatom_map.json', 'Protein to full-atom model directory map (25,743 entries).'),
    },
}

# ---------------------------------------------------------------------------
# CUSTOM_ROUTES —— 手写端点元数据（处理函数在 app.py；此处仅供目录与 OpenAPI）
# ---------------------------------------------------------------------------

CUSTOM_ROUTES = [
    ('/api/v1', 'GET', 'Endpoint catalog: every module, dataset, count and column list.'),
    ('/api/v1/health', 'GET', 'Liveness probe.'),
    ('/api/v1/search', 'GET', 'Global cross-module search over 31,568 index records. Params: q (required), type, limit.'),
    ('/api/v1/compounds', 'GET', '1,670 antiviral compounds with virus/pair/paper counts. Params: q, sort, order, page, page_size.'),
    ('/api/v1/compounds/{name}', 'GET', 'One antiviral compound with its full virus/evidence list.'),
    ('/api/v1/pamir/genomes/{accession}', 'GET', 'One viral genome with full gene annotation.'),
    ('/api/v1/structures/rvpsd/species/{name}', 'GET', 'One species with its full protein-model list.'),
    ('/api/v1/structures/vad/species/{key}', 'GET', 'One VAD species with its full protein list.'),
    ('/api/v1/phylo/molecular/{family}', 'GET', 'All molecular trees for one virus family.'),
    ('/api/v1/literature/years/{year}', 'GET', 'Curated papers for one year (e.g. 2024).'),
]

MODULE_LABELS = {
    'reference': 'Reference sequences (GenBank, curated ref, clusters)',
    'taxonomy': 'ICTV taxonomy (VMR MSL41)',
    'hosts': 'Host range analysis',
    'primers': 'PCR/qPCR primer catalog',
    'gallery': 'Symptom photo gallery',
    'compounds': 'Antiviral compounds',
    'search': 'Global search',
    'stats': 'Platform statistics',
    'geo': 'Geographic data',
    'eve': 'Endogenous viral elements (EVE)',
    'genes': 'Antiviral genes (NLR/sRNA/UPS/miRNA)',
    'associations': 'Host-virus associations',
    'network': 'Interaction networks',
    'vectors': 'Vector-virus-host database',
    'pamir': 'Plant miRNA & viral targets (PAmiRDB)',
    'literature': 'Literature tracker',
    'phylo': 'Phylogenetics',
    'structures': 'Protein structures (RVPSD/VAD/UniProt)',
    'proteomes': 'Genome/proteome clusters',
}


def datasets_by_module():
    out = {}
    for ds in DATASETS:
        out.setdefault(ds['id'].split('.', 1)[0], []).append(ds)
    return out
