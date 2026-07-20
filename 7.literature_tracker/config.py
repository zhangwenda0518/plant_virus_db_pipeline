#!/usr/bin/env python3
"""Central configuration for Plant Virus Literature Tracker."""
import os
from pathlib import Path

# ── Base paths ──
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
WEB_DATA_DIR = WEB_DIR / "data"

# ── Master database ──
PAPERS_JSON = DATA_DIR / "papers.json"
STATE_JSON = DATA_DIR / "pipeline_state.json"
DAILY_DIR = DATA_DIR / "daily"

# ── API keys ──
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
LLM_DELAY = float(os.environ.get("LLM_DELAY", "1.5"))

# ── NCBI rate limits ──
NCBI_EUTILS_DELAY = 0.5  # seconds between requests (0.34 without API key)
PUBMED_MAX_PER_QUERY = 200
PUBMED_DAYS_DEFAULT = 7
ELINK_BATCH_SIZE = 150
SPECIES_MAX_PER_SEARCH = 5
SPECIES_MAX_TOTAL = 300

# ── Data sources ──
DB_TSV = os.environ.get(
    "PVDB_FULL_TSV",
    os.path.join(BASE_DIR, "..", "docs", "data", "Plant_Virus_Full.Info.tsv"),
)
REF_TSV = os.environ.get(
    "PVDB_REF_TSV",
    os.path.join(BASE_DIR, "..", "docs", "data", "Plant_Virus_Ref.Info.tsv"),
)

# ── 9 Plant Virus Search Categories (theme-based, not family-based) ──
QUERY_CATEGORIES = {
    "New_Virus": [
        # 新病毒发现（综合）
        '("novel virus"[Title/Abstract] OR "new virus"[Title/Abstract] OR "virus discovery"[Title/Abstract]) AND ("plant virus"[Title/Abstract] OR phytovirus[Title/Abstract] OR "plant viroid"[Title/Abstract])',
        '("first report"[Title] OR "recently identified"[Title/Abstract] OR "newly identified"[Title/Abstract] OR "previously unknown"[Title/Abstract]) AND virus[Title] AND (plant[Title/Abstract] OR crop[Title/Abstract])',
        '("uncharacterized virus"[Title/Abstract] OR "unclassified virus"[Title/Abstract]) AND ("plant virus"[Title/Abstract] OR phytovirus[Title/Abstract])',
        '("complete genome"[Title] AND "novel"[Title]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract] OR plant viroid[Title/Abstract])',
        '("novel viroid"[Title/Abstract] OR "new viroid"[Title/Abstract] OR "viroid discovery"[Title/Abstract] OR ("viroid"[Title/Abstract] AND ("first report"[Title] OR "novel"[Title/Abstract] OR "new species"[Title/Abstract])))',
    ],
    "Molecular_Characterization": [
        # 基因组/分子特征（合并所有科的基因组+进化+系统发育）
        '("complete genome"[Title/Abstract] OR "full genome"[Title/Abstract] OR "genome sequence"[Title/Abstract] OR "genomic characterization"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract] OR plant viroid[Title/Abstract] OR "Geminiviridae"[Title/Abstract] OR "Potyviridae"[Title/Abstract] OR "Tospoviridae"[Title/Abstract] OR "Closteroviridae"[Title/Abstract])',
        '("phylogenetic"[Title/Abstract] OR "molecular characterization"[Title/Abstract] OR "sequence analysis"[Title/Abstract]) AND (plant virus[Title/Abstract] OR plant viroid[Title/Abstract])',
        '("RNA-dependent RNA polymerase"[Title/Abstract] OR "coat protein"[Title/Abstract] OR "movement protein"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
        '("recombination"[Title/Abstract] OR "reassortment"[Title/Abstract] OR "mixed infection"[Title/Abstract]) AND plant virus[Title/Abstract]',
    ],
    "Detection_Methods": [
        # 检测与诊断（PCR/ELISA/LAMP/HTS/CRISPR）
        '("detection"[Title/Abstract] OR "diagnosis"[Title/Abstract] OR "diagnostic"[Title/Abstract]) AND (plant virus[Title/Abstract] OR plant viroid[Title/Abstract] OR phytovirus[Title/Abstract])',
        '("RT-PCR"[Title/Abstract] OR "qPCR"[Title/Abstract] OR "LAMP"[Title/Abstract] OR "RPA"[Title/Abstract] OR "isothermal amplification"[Title/Abstract]) AND plant virus[Title/Abstract]',
        '("ELISA"[Title/Abstract] OR "immunoassay"[Title/Abstract] OR "serological"[Title/Abstract]) AND plant virus[Title/Abstract]',
        '("CRISPR"[Title/Abstract] AND ("virus"[Title/Abstract] OR "viroid"[Title/Abstract])) AND (plant[Title/Abstract] OR crop[Title/Abstract])',
        '("field-deployable"[Title/Abstract] OR "on-site detection"[Title/Abstract] OR "point-of-care"[Title/Abstract] OR "rapid detection"[Title/Abstract]) AND plant virus[Title/Abstract]',
    ],
    "Host_Virus_Interactions": [
        # 宿主-病毒互作（抗性/RNAi/症状/病理）
        '("plant virus resistance"[Title/Abstract] OR "virus resistance"[Title/Abstract] OR "antiviral defense"[Title/Abstract]) AND (plant[Title/Abstract] OR crop[Title/Abstract])',
        '("RNA silencing"[Title/Abstract] OR "RNA interference"[Title/Abstract] OR "siRNA"[Title/Abstract] OR "viral suppressor"[Title/Abstract]) AND plant virus[Title/Abstract]',
        '("hypersensitive response"[Title/Abstract] OR "programmed cell death"[Title/Abstract] OR "symptom development"[Title/Abstract] OR "pathogenesis"[Title/Abstract]) AND plant virus[Title/Abstract]',
        '("susceptibility gene"[Title/Abstract] OR "recessive resistance"[Title/Abstract] OR "dominant resistance"[Title/Abstract] OR "R gene"[Title/Abstract]) AND plant virus[Title/Abstract]',
    ],
    "Antiviral_Resistance_Genes": [
        # 植物抗病毒基因与抗性机制
        '("plant antiviral"[Title/Abstract] OR "antiviral gene"[Title/Abstract] OR "antiviral mechanism"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
        '("NBS-LRR"[Title/Abstract] OR "NB-LRR"[Title/Abstract] OR "NLR gene"[Title/Abstract] OR "NLR protein"[Title/Abstract] OR "immune receptor"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
        '("antiviral defense"[Title/Abstract] OR "innate immunity"[Title/Abstract] OR "pattern-triggered immunity"[Title/Abstract] OR "effector-triggered immunity"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
        '("autophagy"[Title/Abstract] OR "ubiquitin"[Title/Abstract] OR "proteasome"[Title/Abstract] OR "autophagic"[Title/Abstract]) AND (plant virus[Title/Abstract] OR "plant antiviral"[Title/Abstract])',
        '("translation initiation factor"[Title/Abstract] OR "eIF4E"[Title/Abstract] OR "eIF4G"[Title/Abstract] OR "eIF(iso)4E"[Title/Abstract]) AND (plant virus[Title/Abstract] OR potyvirus[Title/Abstract])',
        '("N gene"[Title/Abstract] OR "Rx gene"[Title/Abstract] OR "Sw-5"[Title/Abstract] OR "Tm-2"[Title/Abstract] OR "Ty-1"[Title/Abstract] OR "L locus"[Title/Abstract]) AND (plant virus[Title/Abstract] OR tobamovirus[Title/Abstract] OR tospovirus[Title/Abstract] OR geminivirus[Title/Abstract])',
        '("nucleotide-binding"[Title/Abstract] OR "leucine-rich repeat"[Title/Abstract] OR "coiled-coil"[Title/Abstract] OR "TIR domain"[Title/Abstract]) AND plant virus[Title/Abstract]',
        '("salicylic acid"[Title/Abstract] OR "jasmonic acid"[Title/Abstract] OR "ethylene signaling"[Title/Abstract] OR "systemic acquired resistance"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
    ],
    "Transmission_Epidemiology": [
        # 传播与流行病学
        '("plant virus transmission"[Title/Abstract] OR "virus vector"[Title/Abstract] OR "insect vector"[Title/Abstract]) AND (plant[Title/Abstract] OR crop[Title/Abstract])',
        '("aphid"[Title/Abstract] OR "whitefly"[Title/Abstract] OR "thrips"[Title/Abstract] OR "leafhopper"[Title/Abstract] OR "planthopper"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
        '("seed transmission"[Title/Abstract] OR "pollen transmission"[Title/Abstract] OR "mechanical transmission"[Title/Abstract] OR "graft transmission"[Title/Abstract]) AND plant virus[Title/Abstract]',
        '("epidemiology"[Title/Abstract] OR "disease spread"[Title/Abstract] OR "outbreak"[Title/Abstract] OR "incidence"[Title/Abstract]) AND plant virus[Title/Abstract]',
    ],
    "Control_Management": [
        # 防控与管理
        '("plant virus management"[Title/Abstract] OR "virus disease management"[Title/Abstract]) AND (plant[Title/Abstract] OR crop[Title/Abstract])',
        '("cross-protection"[Title/Abstract] OR "mild strain"[Title/Abstract] OR "attenuated virus"[Title/Abstract]) AND plant virus[Title/Abstract]',
        '("biocontrol"[Title/Abstract] OR "biological control"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
        '("resistant variety"[Title/Abstract] OR "resistant cultivar"[Title/Abstract] OR "breeding"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
    ],
    "Viral_Diversity_Ecology": [
        # 病毒多样性与生态学
        '("viral metagenomics"[Title/Abstract] OR "virome"[Title/Abstract] OR "virus diversity"[Title/Abstract]) AND (plant[Title/Abstract] OR crop[Title/Abstract] OR agroecosystem[Title/Abstract])',
        '("high-throughput sequencing"[Title/Abstract] OR "next-generation sequencing"[Title/Abstract] OR "nanopore sequencing"[Title/Abstract]) AND (plant virus[Title/Abstract] OR plant virome[Title/Abstract])',
        '("small RNA sequencing"[Title/Abstract] OR "sRNA-seq"[Title/Abstract] OR "degradome"[Title/Abstract]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
        '("virus evolution"[Title/Abstract] OR "molecular evolution"[Title/Abstract] OR "population genetics"[Title/Abstract]) AND plant virus[Title/Abstract]',
        '("virus ecology"[Title/Abstract] OR "wild plant"[Title/Abstract] OR "natural ecosystem"[Title/Abstract] OR "weed"[Title/Abstract]) AND virus[Title/Abstract]',
    ],
    "Biotechnology_Applications": [
        # 生物技术应用（VIGS/载体/纳米）
        '("VIGS"[Title/Abstract] OR "virus-induced gene silencing"[Title/Abstract] OR "gene silencing vector"[Title/Abstract]) AND plant[Title/Abstract]',
        '("plant viral vector"[Title/Abstract] OR "plant virus vector"[Title/Abstract] OR ("virus-like particle"[Title/Abstract] AND plant virus[Title/Abstract]))',
        '("plant virus"[Title/Abstract] AND ("nanotechnology"[Title/Abstract] OR "nanoparticle"[Title/Abstract] OR "drug delivery"[Title/Abstract] OR "biotechnology"[Title/Abstract]))',
        '("recombinant protein"[Title/Abstract] OR "transient expression"[Title/Abstract] OR "agroinfiltration"[Title/Abstract]) AND ("plant virus"[Title/Abstract] OR "viral vector"[Title/Abstract])',
    ],
}

# ── arXiv/bioRxiv keywords for preprint search ──
PREPRINT_KEYWORDS = [
    "plant virus", "phytovirus", "plant viroid", "Geminiviridae", "begomovirus",
    "Potyviridae", "potyvirus", "tobamovirus", "tospovirus", "orthotospovirus",
    "tomato yellow leaf curl virus", "tomato spotted wilt virus", "tobacco mosaic virus",
    "cucumber mosaic virus", "potato virus Y", "citrus tristeza virus",
    "rice stripe virus", "banana bunchy top virus", "cassava mosaic virus",
    "plant virus resistance", "plant virus detection", "plant virus CRISPR",
    "plant virus evolution", "plant virus transmission", "plant virus vector",
]

BIOXIV_KEYWORDS = [
    "plant AND virus", "plant AND viroid", "Geminiviridae", "begomovirus",
    "potyvirus", "tobamovirus", "tospovirus",
]

# ── Journal quality ──
JOURNAL_INFO_TSV = BASE_DIR / "meta.seubiomed.com" / "journal_info.tsv"
TOP_JOURNALS = [
    "annu rev virol", "proc natl acad sci", "front plant sci", "plos pathog",
    "mol plant pathol", "j virol", "virology", "virus res",
]
MID_JOURNALS = [
    "arch virol", "plant dis", "viruses", "front microbiol",
    "j gen virol", "virol j", "phytopathology",
]
