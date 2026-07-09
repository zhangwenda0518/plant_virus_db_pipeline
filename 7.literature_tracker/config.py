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
PUBMED_MAX_PER_QUERY = 30
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

# ── 14 Plant Virus Search Categories ──
QUERY_CATEGORIES = {
    "General": [
        '"plant virus"[Title/Abstract] OR "plant viroid"[Title/Abstract] OR "phytovirus"[Title/Abstract]',
        '"plant RNA virus"[Title/Abstract] OR "plant DNA virus"[Title/Abstract]',
        '"viroid"[Title/Abstract]',
    ],
    "Gemini_Begomo": [
        '"Geminiviridae"[Title/Abstract] OR "begomovirus"[Title/Abstract] OR "mastrevirus"[Title/Abstract] OR "curtovirus"[Title/Abstract] OR "topocuvirus"[Title/Abstract]',
        '"tomato yellow leaf curl virus"[Title/Abstract] OR "Begomovirus coheni"[Title/Abstract]',
        '"cassava mosaic virus"[Title/Abstract] OR "maize streak virus"[Title/Abstract] OR "Mastrevirus maydis"[Title/Abstract]',
        '"cotton leaf curl virus"[Title/Abstract] OR "chilli leaf curl virus"[Title/Abstract] OR "okra yellow vein mosaic virus"[Title/Abstract]',
    ],
    "Potyviridae": [
        '"Potyviridae"[Title/Abstract] OR "potyvirus"[Title/Abstract] OR "ipomovirus"[Title/Abstract] OR "macluravirus"[Title/Abstract] OR "tritimovirus"[Title/Abstract] OR "bymovirus"[Title/Abstract] OR "rymovirus"[Title/Abstract]',
        '"potato virus Y"[Title/Abstract] OR "Potyvirus yituberosi"[Title/Abstract] OR "plum pox virus"[Title/Abstract] OR "Potyvirus plumpoxi"[Title/Abstract]',
        '"turnip mosaic virus"[Title/Abstract] OR "Potyvirus rapae"[Title/Abstract] OR "lettuce mosaic virus"[Title/Abstract]',
        '"papaya ringspot virus"[Title/Abstract] OR "Potyvirus papayanuli"[Title/Abstract] OR "watermelon mosaic virus"[Title/Abstract]',
    ],
    "Tobamo_Virga": [
        '"Virgaviridae"[Title/Abstract] OR "tobamovirus"[Title/Abstract] OR "furovirus"[Title/Abstract] OR "hordeivirus"[Title/Abstract] OR "pomovirus"[Title/Abstract]',
        '"tobacco mosaic virus"[Title/Abstract] OR "Tobamovirus tabaci"[Title/Abstract] OR "cucumber green mottle mosaic virus"[Title/Abstract]',
        '"pepino mosaic virus"[Title/Abstract] OR "Potexvirus pepini"[Title/Abstract]',
    ],
    "Tospo_Bunya": [
        '"Tospoviridae"[Title/Abstract] OR "tospovirus"[Title/Abstract] OR "Orthotospovirus"[Title/Abstract]',
        '"tomato spotted wilt virus"[Title/Abstract] OR "Orthotospovirus tomatomaculae"[Title/Abstract]',
        '"groundnut bud necrosis virus"[Title/Abstract]',
    ],
    "Luteo_Solemo": [
        '"Luteoviridae"[Title/Abstract] OR "Solemoviridae"[Title/Abstract] OR "luteovirus"[Title/Abstract] OR "polerovirus"[Title/Abstract]',
        '"barley yellow dwarf virus"[Title/Abstract] OR "Luteovirus hordei"[Title/Abstract] OR "potato leafroll virus"[Title/Abstract]',
    ],
    "Clostero_Beta": [
        '"Closteroviridae"[Title/Abstract] OR "Betaflexiviridae"[Title/Abstract] OR "closterovirus"[Title/Abstract] OR "crinivirus"[Title/Abstract]',
        '"citrus tristeza virus"[Title/Abstract] OR "Closterovirus tristezae"[Title/Abstract]',
    ],
    "Seco_Bromo_Tombus": [
        '"Secoviridae"[Title/Abstract] OR "Bromoviridae"[Title/Abstract] OR "Tombusviridae"[Title/Abstract]',
        '"nepovirus"[Title/Abstract] OR "comovirus"[Title/Abstract] OR "fabavirus"[Title/Abstract]',
        '"grapevine fanleaf virus"[Title/Abstract] OR "Nepovirus vitis"[Title/Abstract] OR "cucumber mosaic virus"[Title/Abstract] OR "Cucumovirus CMV"[Title/Abstract]',
        '"cowpea mosaic virus"[Title/Abstract] OR "Comovirus vignae"[Title/Abstract]',
    ],
    "Rhabdo_Reo_Fiji_Tenu": [
        '"Rhabdoviridae"[Title/Abstract] OR "Reoviridae"[Title/Abstract]',
        '"cytorhabdovirus"[Title/Abstract] OR "nucleorhabdovirus"[Title/Abstract] OR "fijivirus"[Title/Abstract] OR "oryzavirus"[Title/Abstract] OR "tenuivirus"[Title/Abstract]',
        '"rice stripe virus"[Title/Abstract] OR "Tenuivirus oryzae"[Title/Abstract] OR "rice dwarf virus"[Title/Abstract] OR "southern rice black-streaked dwarf virus"[Title/Abstract]',
    ],
    "Nanoviridae": [
        '"Nanoviridae"[Title/Abstract] OR "babuvirus"[Title/Abstract]',
        '"banana bunchy top virus"[Title/Abstract] OR "Babuvirus musae"[Title/Abstract]',
    ],
    "Caulimo_Badna_Tungro": [
        '"Caulimoviridae"[Title/Abstract] OR "caulimovirus"[Title/Abstract] OR "badnavirus"[Title/Abstract]',
        '"rice tungro bacilliform virus"[Title/Abstract] OR "rice tungro spherical virus"[Title/Abstract]',
    ],
    "Endorna_Parti_Amalga": [
        '"Endornaviridae"[Title/Abstract] OR "Partitiviridae"[Title/Abstract] OR "Amalgaviridae"[Title/Abstract]',
    ],
    "Viroid": [
        '"Pospiviroidae"[Title/Abstract] OR "Avsunviroidae"[Title/Abstract]',
        '"potato spindle tuber viroid"[Title/Abstract] OR "Pospiviroid fusituberis"[Title/Abstract]',
        '"citrus exocortis viroid"[Title/Abstract] OR "chrysanthemum stunt viroid"[Title/Abstract]',
        '"hop stunt viroid"[Title/Abstract] OR "Hostuviroid impedihumuli"[Title/Abstract]',
    ],
    "Methods_Resistance": [
        '"plant virus resistance"[Title/Abstract] OR "plant virus detection"[Title/Abstract]',
        '"plant virus CRISPR"[Title/Abstract] OR "plant virus RNAi"[Title/Abstract] OR "plant virus siRNA"[Title/Abstract]',
    ],
    "Methods_Omics": [
        '"plant virus genome"[Title/Abstract] OR "plant virus evolution"[Title/Abstract] OR "plant virus phylogeny"[Title/Abstract]',
        '"plant virus metagenomics"[Title/Abstract] OR "plant virus proteomics"[Title/Abstract] OR "plant virus NGS"[Title/Abstract]',
    ],
    "Transmission_Epi": [
        '"plant virus transmission"[Title/Abstract] OR "plant virus vector"[Title/Abstract] OR "plant virus epidemiology"[Title/Abstract]',
    ],
    "New_Virus": [
        '("novel virus"[Title/Abstract] OR "new virus"[Title/Abstract] OR "virus discovery"[Title/Abstract]) AND (plant[Title/Abstract] OR crop[Title/Abstract])',
        '("first report"[Title] OR "recently identified"[Title/Abstract] OR "newly identified"[Title/Abstract] OR "previously unknown"[Title/Abstract]) AND virus[Title] AND plant[Title/Abstract]',
        '("uncharacterized virus"[Title/Abstract] OR "unclassified virus"[Title/Abstract] OR "new species"[Title/Abstract]) AND (Viridiplantae[Organism] OR plant[Title/Abstract])',
        '("viral metagenomics"[Title/Abstract] OR "virome"[Title/Abstract] OR "high-throughput sequencing"[Title/Abstract] OR "small RNA sequencing"[Title/Abstract]) AND (plant virus[Title/Abstract] OR novel virus[Title/Abstract])',
        '("novel Geminiviridae"[Title/Abstract] OR "new begomovirus"[Title/Abstract] OR "novel Potyviridae"[Title/Abstract] OR "novel tospovirus"[Title/Abstract] OR "novel RNA virus"[Title/Abstract] OR "novel DNA virus"[Title/Abstract]) AND plant[Title/Abstract]',
        '("complete genome"[Title] AND "novel"[Title]) AND (plant virus[Title/Abstract] OR phytovirus[Title/Abstract])',
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
