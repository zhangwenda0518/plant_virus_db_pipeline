import os
import dash
from dash import dcc, html, Input, Output, State, dash_table, callback, no_update
import dash_mantine_components as dmc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import hashlib
tab = '\t'
from Bio import SeqIO

# Unified project config — locate config.py (multi-level directory fallback)
import sys
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_config_paths = [
    os.path.join(_cur_dir, "config.py"),            # same directory
    os.path.join(_cur_dir, "..", "config.py"),      # parent directory
]
for _cp in _config_paths:
    _config_dir = os.path.dirname(_cp)
    if os.path.exists(_cp):
        if _config_dir not in sys.path:
            sys.path.insert(0, _config_dir)
        from config import PIPELINE_OUTPUTS as _cfg, get_version_string
        break
else:
    raise FileNotFoundError("config.py not found in " + str(_config_paths))
DATA_TSV = _cfg["full_tsv"]
DATA_FASTA = _cfg["full_fasta"]
DATA_VERSION = get_version_string()

# -----------------------------------------------------------------------------
# 1. Precision Bioinformatics Engine (Bio.Align.PairwiseAligner)
# -----------------------------------------------------------------------------

def create_mock_sequence(virus_name, length=800):
    """
    Simulate representative plant virus CP genes with species-specific hypervariable region distributions
    """
    seed_val = int(hashlib.md5(virus_name.encode()).hexdigest(), 16) % 10000
    rng = np.random.default_rng(seed_val)
    
    bases = ['A', 'T', 'G', 'C']
    consensus = rng.choice(bases, size=length)
    
    var_positions = []
    if 'spotted wilt' in virus_name.lower() or 'tswv' in virus_name.lower():
        # TSWV mutation sites (from paper Fig. 3)
        var_positions = [342, 315, 658, 732, 186, 762, 591, 376, 763, 738]
    elif 'mild mottle' in virus_name.lower() or 'pmmov' in virus_name.lower():
        # PMMoV mutation sites (from paper Fig. 3)
        var_positions = [57, 81, 99, 168, 117, 213, 276, 474, 165, 357]
    else:
        var_positions = rng.choice(range(length), size=10, replace=False).tolist()
        
    var_positions = [pos - 1 for pos in var_positions if pos <= length]
    
    seq = consensus.copy()
    for pos in range(length):
        if pos in var_positions:
            seq[pos] = np.random.choice(bases)
        else:
            if np.random.rand() < 0.02:
                seq[pos] = np.random.choice(bases)
                
    return "".join(seq)

def generate_baseline_dataset():
    """
    ⚠ 仅开发用（dev-only）演示数据：~1,700 条随机模拟记录。
    【禁止】作为生产数据加载失败时的回退 —— 生产必须 fail-fast（见下方 load 段 try/except）。
    保留本函数仅为本地无数据环境做 UI 演示。
    """
    np.random.seed(42)
    records = []
    
    countries = ['China', 'South Korea', 'Indonesia', 'Thailand', 'Japan']
    viruses = [
        'Tomato spotted wilt virus (TSWV)', 
        'Pepper mild mottle virus (PMMoV)', 
        'Cucumber mosaic virus (CMV)', 
        'Pepper yellow leaf curl Indonesia virus (PepYLCIV)',
        'Pepper yellow leaf curl virus (PepYLCV)',
        'Pepper yellow leaf curl Thailand virus (PepYLCThV)'
    ]
    
    years = list(range(2015, 2026))
    
    for year in years:
        for country in countries:
            num_records = 0
            if country == 'China':
                if year == 2015:
                    num_records = 145
                elif year == 2022:
                    num_records = 175
                else:
                    num_records = np.random.randint(45, 80)
            elif country == 'South Korea':
                if year == 2018:
                    num_records = 98
                elif year == 2024:
                    num_records = 4
                else:
                    num_records = np.random.randint(15, 35)
            elif country == 'Indonesia':
                if year == 2025:
                    num_records = 108 # PepYLCIV 2025 outbreak peak
                else:
                    num_records = np.random.randint(5, 20)
            elif country == 'Thailand':
                if year in [2017, 2020, 2025]:
                    num_records = np.random.randint(25, 45)
                else:
                    num_records = np.random.randint(5, 15)
            elif country == 'Japan':
                num_records = np.random.randint(5, 20)
                
            for i in range(num_records):
                if country == 'Indonesia' and year == 2025:
                    virus = 'Pepper yellow leaf curl Indonesia virus (PepYLCIV)'
                elif country == 'South Korea' and year == 2018:
                    virus = 'Tomato spotted wilt virus (TSWV)' if np.random.rand() < 0.75 else np.random.choice(viruses)
                elif country == 'China' and year == 2022:
                    virus = 'Tomato spotted wilt virus (TSWV)' if np.random.rand() < 0.65 else np.random.choice(viruses)
                elif country == 'China' and year == 2015:
                    virus = np.random.choice(['Pepper mild mottle virus (PMMoV)', 'Cucumber mosaic virus (CMV)'])
                else:
                    virus = np.random.choice(viruses)
                
                accession = f"GB{np.random.randint(100000, 999999)}"
                seq = create_mock_sequence(virus, length=800)
                
                records.append({
                    'Accession': accession,
                    'Definition': f"{virus} isolate CP{i} coat protein gene, complete cds",
                    'Organism': virus,
                    'Country': country,
                    'Year': year,
                    'FullSequenceLength': len(seq) + np.random.randint(-15, 15),
                    'CP_Sequence': seq
                })
                
    return pd.DataFrame(records)


def _clean_country(raw):
    """Normalize country names: strip subregion suffixes (e.g.  'China: Hainan' → 'China'), unify common variants"""
    if pd.isna(raw) or str(raw).strip() == '':
        return 'Unknown'
    s = str(raw).strip()
    # strip subregion after colon
    if ':' in s:
        s = s.split(':')[0].strip()
    # normalize common variants
    name_map = {
        'United States': 'USA', 'United States of America': 'USA',
        'Russian Federation': 'Russia',
        'Republic of Korea': 'South Korea', 'Korea': 'South Korea',
        'Viet Nam': 'Vietnam',
        'United Kingdom of Great Britain and Northern Ireland': 'United Kingdom',
    }
    return name_map.get(s, s)


def _build_country_name_map():
    """Build Geo_Location → Plotly ISO standard country name mapping"""
    return {
        'China': 'China', 'South Korea': 'South Korea',
        'Indonesia': 'Indonesia', 'Thailand': 'Thailand', 'Japan': 'Japan',
        'USA': 'United States', 'United States': 'United States',
        'India': 'India', 'Brazil': 'Brazil', 'Australia': 'Australia',
        'Germany': 'Germany', 'France': 'France', 'Italy': 'Italy',
        'Spain': 'Spain', 'United Kingdom': 'United Kingdom',
        'Netherlands': 'Netherlands', 'Canada': 'Canada', 'Mexico': 'Mexico',
        'Vietnam': 'Vietnam', 'Taiwan': 'Taiwan', 'Philippines': 'Philippines',
        'Malaysia': 'Malaysia', 'Pakistan': 'Pakistan', 'Bangladesh': 'Bangladesh',
        'Turkey': 'Turkey', 'Iran': 'Iran', 'Egypt': 'Egypt',
        'South Africa': 'South Africa', 'Kenya': 'Kenya', 'Nigeria': 'Nigeria',
        'Argentina': 'Argentina', 'Colombia': 'Colombia', 'Peru': 'Peru',
        'New Zealand': 'New Zealand', 'Belgium': 'Belgium',
        'Russia': 'Russia', 'Poland': 'Poland', 'Sweden': 'Sweden',
        'Norway': 'Norway', 'Denmark': 'Denmark', 'Finland': 'Finland',
        'Austria': 'Austria', 'Switzerland': 'Switzerland',
        'Portugal': 'Portugal', 'Greece': 'Greece', 'Ireland': 'Ireland',
        'Chile': 'Chile', 'Ecuador': 'Ecuador', 'Costa Rica': 'Costa Rica',
        'Cuba': 'Cuba', 'Venezuela': 'Venezuela', 'Bolivia': 'Bolivia',
        'Uruguay': 'Uruguay', 'Paraguay': 'Paraguay',
        'Morocco': 'Morocco', 'Tunisia': 'Tunisia', 'Ethiopia': 'Ethiopia',
        'Tanzania': 'Tanzania', 'Uganda': 'Uganda', 'Ghana': 'Ghana',
        'Benin': 'Benin', 'Cameroon': 'Cameroon', 'Madagascar': 'Madagascar',
        'Zimbabwe': 'Zimbabwe', 'Malawi': 'Malawi', 'Zambia': 'Zambia',
        'Sudan': 'Sudan', 'Senegal': 'Senegal', 'Mali': 'Mali',
        'Saudi Arabia': 'Saudi Arabia', 'Israel': 'Israel',
        'United Arab Emirates': 'United Arab Emirates',
        'Singapore': 'Singapore', 'Myanmar': 'Myanmar', 'Cambodia': 'Cambodia',
        'Laos': 'Laos', 'Nepal': 'Nepal', 'Sri Lanka': 'Sri Lanka',
        'Czech Republic': 'Czech Republic', 'Slovakia': 'Slovakia',
        'Hungary': 'Hungary', 'Romania': 'Romania', 'Bulgaria': 'Bulgaria',
        'Ukraine': 'Ukraine', 'Serbia': 'Serbia', 'Croatia': 'Croatia',
        'Slovenia': 'Slovenia', 'Lithuania': 'Lithuania', 'Latvia': 'Latvia',
        'Estonia': 'Estonia', 'Cyprus': 'Cyprus',
    }


# Table row limit (prevents browser overload when unfiltered)
TABLE_MAX_ROWS = 5000

def load_real_data():
    import pickle, time as _time
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "explorer_data.pkl")

    # Check if cache is valid (newer than source files)
    use_cache = False
    if os.path.exists(cache_file):
        cache_mtime = os.path.getmtime(cache_file)
        tsv_mtime = os.path.getmtime(DATA_TSV) if os.path.exists(DATA_TSV) else 0
        fa_mtime = os.path.getmtime(DATA_FASTA) if os.path.exists(DATA_FASTA) else 0
        if cache_mtime >= max(tsv_mtime, fa_mtime):
            use_cache = True

    if use_cache:
        t0 = _time.time()
        with open(cache_file, 'rb') as f:
            data = pickle.load(f)
        print(f"  Loaded from cache in {_time.time()-t0:.1f}s: {data['df_len']:,} records, {data['n_species']:,} species")
        return data['df'], data['n_species'], data['country_map'], data.get('top_country_n', 30)

    # Full parse (cold start)
    t0 = _time.time()
    df = pd.read_csv(DATA_TSV, sep='\t', low_memory=True, dtype={'USA': str, 'NCBI_Status': str})
    df['Year_Collection'] = df['Collection_Date'].astype(str).str.extract(r'(\d{4})')[0]
    df['Year_Collection'] = pd.to_numeric(df['Year_Collection'], errors='coerce')
    df['Year_Release'] = df['Release_Date'].astype(str).str.extract(r'(\d{4})')[0]
    df['Year_Release'] = pd.to_numeric(df['Year_Release'], errors='coerce')
    df['Has_Collection_Date'] = df['Year_Collection'].notna()
    df['Year'] = df['Year_Collection'].fillna(df['Year_Release'])
    df['Organism'] = df['Species_NCBI'].fillna(df['Species_ICTV']).fillna('Unknown')
    df['Country'] = df['Geo_Location'].apply(_clean_country)
    df['Definition'] = df['GenBank_Title'].fillna('')
    df['FullSequenceLength'] = pd.to_numeric(df['Length'], errors='coerce')
    df['Host_Name'] = df['Host'].fillna('Unknown')
    df['Category_Type'] = df['Segment'].notna().map({True: 'Segmented', False: 'NonSegmented'})
    df['Segment_Info'] = df['Segment'].fillna('N/A')
    df['Family'] = df['Family'].fillna('Unknown')
    df['Genus'] = 'Unknown'
    df['Completeness'] = df['Nuc_Completeness'].fillna('unknown')
    # 节段标准名 / 原始采集日期：Data Browser 表格列需要（旧版 TSV 无 Segment_std 时补空）
    if 'Segment_std' not in df.columns:
        df['Segment_std'] = ''
    df['Segment_std'] = df['Segment_std'].fillna('')
    df['Collection_Date'] = df['Collection_Date'].fillna('')
    df = df[df['Year'].notna()]
    df['Year'] = df['Year'].astype(int)
    df = df[df['Year'] >= 1970]

    print(f"  Loading {len(df)} sequences from FASTA ({_time.time()-t0:.1f}s for TSV)...")
    seq_dict = {}
    for rec in SeqIO.parse(DATA_FASTA, "fasta"):
        seq_dict[rec.id] = str(rec.seq).upper()
    df['Sequence'] = df['Accession'].map(seq_dict)
    df = df[df['Sequence'].notna() & (df['Sequence'] != '')]
    del seq_dict

    cols = ['Accession','Definition','Organism','Country','Geo_Location','Year','Year_Collection','Year_Release','Has_Collection_Date',
            'FullSequenceLength','Sequence','Collection_Date','Release_Date','Segment_std',
            'Category_Type','Segment_Info','Host_Name','Isolation_Source','Family','Genus','Molecule_type','Sequence_Type','Topology','Length','Completeness']
    result = df[cols]
    n_species = result['Organism'].nunique()
    country_map = _build_country_name_map()

    # Save cache
    print(f"  Full load: {len(result):,} records, {n_species:,} species in {_time.time()-t0:.1f}s. Caching...")
    with open(cache_file, 'wb') as f:
        pickle.dump({'df': result, 'df_len': len(result), 'n_species': n_species,
                     'country_map': country_map}, f, protocol=4)
    print(f"  Cache saved ({os.path.getsize(cache_file)/1024/1024:.0f}MB)")

    return result, n_species, country_map, 30


print("Loading real virus data (TSV + FASTA genome sequences)...")
try:
    df_global, N_SPECIES, COUNTRY_NAME_MAP, TOP_COUNTRY_N = load_real_data()
    print(f"Loaded {len(df_global)} accessions ({N_SPECIES} unique species) from database")
    _country_counts = df_global['Country'].value_counts()
    _country_counts = _country_counts[_country_counts.index != 'Unknown']
    DYNAMIC_COUNTRY_OPTIONS = [
        {"value": v, "label": f"{v} ({c})"}
        for v, c in _country_counts.items()
    ]
    DYNAMIC_COUNTRY_DEFAULTS = [v for v, _ in _country_counts.head(8).items()]
    print(f"Country map: {len(COUNTRY_NAME_MAP)} entries, all countries loaded")
except Exception as e:
    # Fail-fast（审计 P0，2026-10-03）：绝不用假数据回退。
    # 旧行为 generate_baseline_dataset() 会造 ~1,700 条随机记录充数：列结构与真实库不一致
    # （下游 'Geo_Location'/'Host_Name' 等必然 KeyError），且会让公开站点静默展示编造数据。
    # 数据加载失败 = 部署/数据故障，必须暴露：打印真实错误后退出，由 systemd (Restart=always) 拉起并留日志。
    print("FATAL: real data load failed, refusing to fall back to mock data: %s" % e)
    import traceback
    traceback.print_exc()
    raise SystemExit(1)

# 宿主筛选器选项：每个宿主标注「不同病毒种数 · 序列记录数」
# 说明：节段病毒的一个 isolate 有多个节段记录 → n_seq 会偏大，故同时给出 n_vir（去重后的病毒种数）。
try:
    _host_sub = df_global[df_global['Host_Name'] != 'Unknown']
    _host_stats = _host_sub.groupby('Host_Name').agg(
        _n_vir=('Organism', 'nunique'), _n_seq=('Organism', 'size'))
    HOST_FILTER_OPTIONS = sorted(
        [{"value": _hn,
          "label": "%s (%d viruses · %s seqs)" % (_hn, int(_r['_n_vir']), format(int(_r['_n_seq']), ","))}
         for _hn, _r in _host_stats.iterrows()],
        key=lambda x: x['label'])
except Exception as _e:
    print("Host filter options failed (%s); falling back to bare names" % _e)
    HOST_FILTER_OPTIONS = sorted(
        [{"value": v, "label": v} for v in df_global['Host_Name'].value_counts().index if v != 'Unknown'],
        key=lambda x: x['label'])


def _build_year_marks(ymin, ymax):
    """Generate dynamic year ticks: wider span → larger interval → smaller font"""
    span = ymax - ymin
    if span > 100:
        step = 50
    elif span > 50:
        step = 10
    elif span > 30:
        step = 10
    elif span > 15:
        step = 5
    else:
        step = 2
    size = "9px" if span > 30 else "11px"
    marks = {}
    start = (ymin // step) * step
    for y in range(start, ymax + 1, step):
        if y >= ymin:
            marks[y] = {"label": str(y), "style": {"fontSize": size, "whiteSpace": "nowrap"}}
    # always include start and end points
    marks[ymin] = {"label": str(ymin), "style": {"fontSize": size, "whiteSpace": "nowrap"}}
    marks[ymax] = {"label": str(ymax), "style": {"fontSize": size, "whiteSpace": "nowrap"}}
    return marks


def align_to_reference(sequences, reference_seq):
    """
    Align input sequences to reference_seq coordinate system using Bio.Align.PairwiseAligner.
    Removes insertions relative to reference; preserves deletions as gaps.
    """
    from Bio.Align import PairwiseAligner
    aligner = PairwiseAligner()
    aligner.mode = 'global'
    aligner.match_score = 2
    aligner.mismatch_score = -1
    aligner.open_gap_score = -3
    aligner.extend_gap_score = -1
    
    aligned_queries = []
    for seq in sequences:
        if not seq or len(seq) == 0:
            aligned_queries.append("-" * len(reference_seq))
            continue
        try:
            alignments = aligner.align(reference_seq, seq)
            if not alignments:
                aligned_queries.append("-" * len(reference_seq))
                continue
                
            alignment = alignments[0]
            # get aligned dual-strand text
            ref_aligned = alignment[0]
            query_aligned = alignment[1]
            
            # map Query bases back to Reference coordinate space
            mapped = []
            q_idx = 0
            for r_char in ref_aligned:
                q_char = query_aligned[q_idx]
                if r_char == '-':
                    # Gap in reference = Query insertion; skip to maintain coordinate consistency
                    q_idx += 1
                    continue
                else:
                    # map alignment results
                    mapped.append(q_char)
                    q_idx += 1
                    
            mapped_str = "".join(mapped)
            if len(mapped_str) < len(reference_seq):
                mapped_str = mapped_str.ljust(len(reference_seq), '-')
            elif len(mapped_str) > len(reference_seq):
                mapped_str = mapped_str[:len(reference_seq)]
            aligned_queries.append(mapped_str)
        except Exception as e:
            # basic padding on error
            aligned_queries.append(seq[:len(reference_seq)].ljust(len(reference_seq), '-'))
            
    return aligned_queries

def compute_alignment_matrices(sequences):
    """
    Compute base frequency matrix and local mutation rate from aligned equal-length sequences
    """
    num_seqs = len(sequences)
    if num_seqs == 0:
        return np.zeros((4, 1)), np.zeros(1)
        
    L = len(sequences[0])
    nucleotides = ['A', 'T', 'G', 'C']
    matrix = np.zeros((4, L))
    
    for col in range(L):
        chars = [seq[col].upper() for seq in sequences]
        for idx, nt in enumerate(nucleotides):
            matrix[idx, col] = chars.count(nt)
            
    col_sums = matrix.sum(axis=0)
    col_sums[col_sums == 0] = 1
    frequency_matrix = matrix / col_sums
    
    # Mutation rate = 1 - max base probability (0 at fully conserved sites, ~0.75 at fully dispersed sites)
    variation_rates = 1.0 - frequency_matrix.max(axis=0)
    return frequency_matrix, variation_rates

# -----------------------------------------------------------------------------
# 2. Enhanced System UI Layout
# -----------------------------------------------------------------------------

DASH_PREFIX = os.environ.get("DASH_URL_PREFIX", "/")
try:  # 合并部署（wsgi_merged）：两个 Dash 挂同一 Flask；独立部署时为 None，走 Dash 默认
    from shared_server import SERVER as _MERGED_SERVER
except ImportError:
    _MERGED_SERVER = None
_DASH_KW = dict(update_title=None,
    requests_pathname_prefix=DASH_PREFIX,
    routes_pathname_prefix=DASH_PREFIX,
    external_stylesheets=[
])
if _MERGED_SERVER is not None:
    _DASH_KW['server'] = _MERGED_SERVER  # 注意：显式传 server=None 会让 Dash 跳过路由注册
app = dash.Dash(__name__, **_DASH_KW)
app._favicon = None
server = app.server
app.title = "Plant Virus Explorer"


app.index_string = '''<!DOCTYPE html>
<html>
<head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
</style>
</head>
<body><script src="/lib/site-nav.js?v=2"></script>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer>
<script src="/lib/ai-assistant.js?v=2" data-context="explorer" defer></script>
<script src="/reference/i18n.js"></script>
<script>setTimeout(function(){PVDB_i18n.init({navSelector:"nav"});},800);</script>
</body>
</html>'''

# Load name mapping into memory (shared cache)
import csv
from collections import Counter, defaultdict
NAME_MAP_CACHE = {}
_map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "data", "name_mapping.tsv")
if os.path.exists(_map_path):
    with open(_map_path, encoding='utf-8') as _mf:
        for _row in csv.DictReader(_mf, delimiter='\t'):
            NAME_MAP_CACHE[_row.get('Lookup_Key', '')] = _row
    print(f"Name mapping cache: {len(NAME_MAP_CACHE)} entries")

def _lookup_names(query):
    """Return [query, ICTV name, common name, abbreviation]"""
    result = {query.lower()}
    m = NAME_MAP_CACHE.get(query.lower(), {})
    for k in ('ICTV_Name', 'Common_Name', 'Abbreviation'):
        v = m.get(k, '').strip()
        if v: result.add(v.lower())
    return result

# ── Vector Transmission data (virus_vector_merged.json, generated by 8.plant-insect/build_vector_db.py) ──
import json as _json
VECTOR_DB = {}      # canonical_name -> merged virus record
VECTOR_INDEX = {}   # normalized name -> canonical_name (join key)

def _vnorm(s):
    return " ".join((s or "").strip().lower().split()).strip(".,;")

_vec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "8.plant-insect", "virus_vector_merged.json")
if os.path.exists(_vec_path):
    try:
        with open(_vec_path, encoding='utf-8') as _vf:
            _vraw = _json.load(_vf)
        for _v in _vraw.get("viruses", []):
            cname = _v["canonical_name"]
            VECTOR_DB[cname] = _v
            for _nm in [cname, _v.get("ictv_name", "")] + _v.get("matched_names", []):
                k = _vnorm(_nm)
                if k and k not in VECTOR_INDEX:
                    VECTOR_INDEX[k] = cname
        print(f"Vector DB: {len(VECTOR_DB)} viruses, {len(VECTOR_INDEX)} name keys")
    except Exception as _e:
        print(f"Vector DB load failed: {_e}")

def _vector_lookup(organism):
    """Look up vector records by Organism name and aliases (including NCBI→ICTV translation)."""
    for name in _lookup_names(organism):
        cn = VECTOR_INDEX.get(_vnorm(name))
        if cn:
            return VECTOR_DB[cn]
    # Supplement NCBI→ICTV name translation (bridge Explorer NCBI names ↔ VH ICTV names)
    ictv = _NCBI2ICTV.get(organism.strip().lower(), "")
    if ictv:
        cn = VECTOR_INDEX.get(_vnorm(ictv))
        if cn:
            return VECTOR_DB[cn]
    return None

# ── Virus Profile (integrated from 8.virus_profile as an in-Explorer Dash page) ──
import glob, re, json as _pj
import config as _cfgmod
_PROFILE_BASE = os.path.dirname(os.path.abspath(_cfgmod.__file__))
_REF_TSV = _cfg.get("cluster_info", "")
_GENOME_DIR = os.path.join(_PROFILE_BASE, "genome_annotations")
_PAPERS_JSON = os.path.join(_PROFILE_BASE, "7.literature_tracker", "papers.json")
_PRIMER_TSV = getattr(_cfgmod, "PRIMER_OUTPUTS", {}).get("reference_tsv", "")

# ── /virus/* 兼容路由（8.virus_profile 独立应用已并入 explorer，不再单独部署）──
# 下载路由：build_profile 的注释文件链接仍指向 /virus/files/，由本进程直接服务
@server.route("/virus/files/<path:filepath>")
def _vp_files(filepath):
    import flask
    # 安全（审计 S4 路径穿越，2026-10-03）：必须把原始 filepath 交给 send_from_directory，
    # 由 Werkzeug safe_join 消毒。旧写法 os.path.join(_GENOME_DIR, filepath) 会先把 ".." 规范化，
    # 再对 dirname/basename 调 send_from_directory —— 等于绕过防护，可读任意文件
    # （服务以 root 运行，/etc/shadow、.env 均在射程内）。safe_join 对 ../ 直接抛 NotFound → 404。
    return flask.send_from_directory(_GENOME_DIR, filepath)

# 深链兼容：/virus/<物种> → 跳到 explorer 的 Virus Profile 标签并选中该物种
@server.route("/virus/", defaults={"sub": ""})
@server.route("/virus/<path:sub>")
def _vp_redirect(sub):
    import flask
    from urllib.parse import quote
    if sub.startswith("files/"):
        return flask.redirect("/explorer/")
    target = "/explorer/?profile=" + quote(sub) if sub else "/explorer/"
    return flask.redirect(target)

def _profile_species_list():
    out, seen = [], set()
    if os.path.exists(_REF_TSV):
        with open(_REF_TSV, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip()
                if sp and sp not in seen:
                    seen.add(sp); out.append(sp)
    return sorted(out)

PROFILE_SPECIES = _profile_species_list()
print(f"Profile species: {len(PROFILE_SPECIES)}")

# Full.Info.tsv has NCBI→ICTV mapping for profile lookup (Explorer uses NCBI names, Ref uses ICTV names)
_NCBI2ICTV = {}
if os.path.exists(DATA_TSV):
    with open(DATA_TSV, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ncbi = (row.get("Species_NCBI", "") or "").strip()
            ictv = (row.get("Species_ICTV", "") or "").strip()
            if ncbi and ictv and ncbi.lower() not in _NCBI2ICTV:
                _NCBI2ICTV[ncbi.lower()] = ictv

# Profile 可选物种集合：ICTV 名 ∪ NCBI 名（Explorer 用 NCBI 名，参考库用 ICTV 名）
_PROFILE_NAME_SET = {s.strip().lower() for s in PROFILE_SPECIES if s}
_PROFILE_NAME_SET |= set(_NCBI2ICTV.keys())          # _NCBI2ICTV 的 key 已是小写 NCBI 名


def _has_profile(name):
    """该物种在参考库中是否存在 Profile（NCBI 名或 ICTV 名均可命中）。"""
    return bool((name or "").strip().lower() in _PROFILE_NAME_SET)


def _profile_info(name):
    """Look up in Ref.Info.tsv by NCBI or ICTV name (via NCBI→ICTV mapping)."""
    if not os.path.exists(_REF_TSV):
        return None
    nl = name.lower().strip()
    candidates = {nl, (_NCBI2ICTV.get(nl, "") or "").lower()}
    candidates.discard("")
    with open(_REF_TSV, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip().lower()
            if sp in candidates:
                return row
    return None

def _genome_map_fig(feats, genome_len):
    """Single segment/sequence CDS map: colored arrows, top row = plus strand / bottom row = minus strand."""
    fig = go.Figure()
    if not genome_len:
        genome_len = max((f["end"] for f in feats), default=1)
    pal = px.colors.qualitative.Set2
    fig.add_shape(type="line", x0=0, x1=genome_len, y0=0, y1=0, line=dict(color="#adb5bd", width=2))
    for i, f in enumerate(feats):
        y = 0.18 if f["strand"] > 0 else -0.18
        s, e = f["start"], f["end"]
        aw = min((e - s) * 0.25, genome_len * 0.012)
        if f["strand"] > 0:
            xs, ys = [s, e - aw, e, e - aw, s, s], [y - 0.11, y - 0.11, y, y + 0.11, y + 0.11, y - 0.11]
        else:
            xs, ys = [e, s + aw, s, s + aw, e, e], [y - 0.11, y - 0.11, y, y + 0.11, y + 0.11, y - 0.11]
        fig.add_trace(go.Scatter(x=xs, y=ys, fill="toself", mode="lines",
            line=dict(width=0.5, color="#495057"), fillcolor=pal[i % len(pal)],
            hovertext="%s<br>%d..%d (%s)" % (f["label"], s, e, "+" if f["strand"] > 0 else "-"),
            hoverinfo="text", showlegend=False))
        if (e - s) > genome_len * 0.06:
            fig.add_annotation(x=(s + e) / 2, y=y, text=f["label"][:22], showarrow=False, font=dict(size=8, color="#212529"))
    fig.update_layout(height=180, margin=dict(l=8, r=8, t=6, b=26), plot_bgcolor="white",
        yaxis=dict(visible=False, range=[-0.5, 0.5], fixedrange=True),
        xaxis=dict(title="Position (nt)", rangemode="tozero", tickfont=dict(size=10)))
    return fig


def build_profile(name):
    """Build single-virus detail Dash components (downloads/maps/proteins/literature/primers)."""
    info = _profile_info(name)
    if not info:
        return dmc.Alert(f"Not found in reference database「{name}」。", color="yellow", variant="light")
    # genome_annotations dir uses Species_ICTV naming; may differ from Explorer Organism (NCBI-priority)
    canon = (info.get("Species_ICTV", "") or info.get("Species_NCBI", "") or name).strip()
    sp_safe = canon.replace("/", "_")
    sp_dir = os.path.join(_GENOME_DIR, sp_safe)

    # 1. Download links (local genome_annotations, served via /virus/files/)
    accs = []
    if os.path.isdir(sp_dir):
        for gb in sorted(glob.glob(os.path.join(sp_dir, "*.gb"))):
            ac = os.path.splitext(os.path.basename(gb))[0]
            cand = {"genome": ac + "_genome.fasta", "cds": ac + "_cds.fasta",
                    "protein": ac + "_protein.fasta", "gff3": ac + ".gff3", "gb": ac + ".gb"}
            files = {k: "/virus/files/%s/%s" % (sp_safe, fn) for k, fn in cand.items()
                     if os.path.exists(os.path.join(sp_dir, fn))}
            accs.append({"name": ac, "files": files})

    # 2. Parse structure per accession; deduplicate by (len//100, CDS product set) signature.
    #    Multiple isolates of the same segment → single plot; different segments (DNA-A/DNA-B, RNA1/2/3) → separate plots.
    acc_seg = {}
    if os.path.exists(_REF_TSV):
        with open(_REF_TSV, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                sp = (row.get("Species_ICTV", "") or row.get("Species_NCBI", "")).strip()
                # Ref.Info.tsv 用 ICTV 名，Explorer 传进来的是 NCBI 名（如 Cucumber mosaic virus
                # vs Cucumovirus CMV）→ 必须用 canon 一起匹配，否则 acc_seg 恒为空、节段标签全丢。
                if sp.lower() in (name.lower(), canon.lower()):
                    acc_seg[row.get("Accession", "").split(".")[0]] = (row.get("Segment", "") or "").strip()

    proteins = []
    groups = {}  # group_key -> {rep, seg_label, glen, feats, n}
    submitters = {}  # 提交单位 -> 记录数（从 gb 的 JOURNAL Submitted 块解析）
    for a in accs[:80]:
        gbp = os.path.join(sp_dir, a["name"] + ".gb")
        if not os.path.exists(gbp):
            continue
        txt = open(gbp, encoding="utf-8", errors="replace").read()
        for sm in re.finditer(r'JOURNAL\s+Submitted\s*\([^)]*\)\s*(.*?)(?=\n[A-Z/]|\Z)', txt, re.S):
            inst = re.sub(r'\s+', ' ', sm.group(1)).strip().rstrip(',').strip()
            if inst:
                submitters[inst] = submitters.get(inst, 0) + 1
        lm = re.search(r'^LOCUS\s+\S+\s+(\d+)\s+bp', txt, re.M)
        glen = int(lm.group(1)) if lm else 0
        cds = []
        for m in re.finditer(r'\n     CDS\s+([^\n]+)', txt):
            loc = m.group(1).strip()
            posm = re.search(r'(\d+\.\.\d+)', loc)
            seg = txt[m.end():m.end() + 1500]
            nf = re.search(r'\n     [A-Za-z]', seg)
            if nf:
                seg = seg[:nf.start()]
            prodm = re.search(r'/product="([^"]*)"', seg, re.S)
            pidm = re.search(r'/protein_id="([^"]*)"', seg)
            prod = re.sub(r"\s+", " ", prodm.group(1)) if prodm else "CDS"
            nums = re.findall(r'\d+', loc)
            cds.append({"product": prod, "position": posm.group(1) if posm else loc,
                        "protein_id": pidm.group(1) if pidm else "",
                        "start": int(nums[0]) if len(nums) >= 2 else 0,
                        "end": int(nums[-1]) if len(nums) >= 2 else 0,
                        "strand": -1 if "complement" in loc else 1})
        if not glen and cds:
            glen = max(c["end"] for c in cds)
        # group key: Segment name first (normalized), else by structure signature
        raw_seg = acc_seg.get(a["name"], "").strip().replace(" ", "").replace("-", "")
        gkey = raw_seg if raw_seg else ("L%d|%s" % (glen // 100, tuple(sorted(c["product"] for c in cds))))
        if gkey not in groups:
            feats = [{"start": c["start"], "end": c["end"], "strand": c["strand"], "label": c["product"]}
                     for c in cds if c["end"]]
            groups[gkey] = {"rep": a["name"], "seg_label": (acc_seg.get(a["name"], "") or "") if raw_seg else "",
                            "glen": glen, "feats": feats, "n": 0}
            for c in cds:
                proteins.append({"segment": acc_seg.get(a["name"], "") or a["name"], "product": c["product"],
                                 "position": c["position"], "protein_id": c["protein_id"]})
        groups[gkey]["n"] += 1
    segments = sorted(groups.values(), key=lambda g: -g["glen"])

    # 3. Related Literature
    papers = []
    if os.path.exists(_PAPERS_JSON):
        try:
            allp = _pj.load(open(_PAPERS_JSON, encoding="utf-8")).get("papers", [])
            nl, fam = name.lower(), info.get("Family", "")
            for p in allp:
                if (fam and fam in p.get("categories", [])) or nl in str(p.get("title", "")).lower():
                    papers.append(p)
            papers = papers[:20]
        except Exception:
            pass

    # 4. Primer count
    pc = 0
    if os.path.exists(_PRIMER_TSV):
        try:
            for row in csv.DictReader(open(_PRIMER_TSV, encoding="utf-8"), delimiter="\t"):
                if name.lower() in (row.get("Species", "") or "").lower():
                    pc += 1
        except Exception:
            pass

    # ── Assemble Dash components ──
    disp = info.get("Species_ICTV", "") or info.get("Species_NCBI", "") or name
    meta = " · ".join([x for x in [info.get("Family", ""), info.get("Molecule_type", ""),
                                   info.get("Topology", ""),
                                   (info.get("Length", "") + " bp") if info.get("Length", "") else "",
                                   "%d accessions" % len(accs)] if x])
    out = [dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
        dmc.Title(disp, order=3, c="#1a5276"),
        dmc.Text(meta, size="sm", c="dimmed", mt=4),
    ])]

    # Submission Sources：提交单位（紧跟头部卡片展示；vp 深链页共用本函数）
    if submitters:
        top = sorted(submitters.items(), key=lambda kv: -kv[1])[:5]
        rows = [dmc.Text("%s%s" % (inst, ("  ·  %d records" % n) if n > 1 else ""), size="sm", mb=2)
                for inst, n in top]
        if len(submitters) > 5:
            rows.append(dmc.Text("…and %d more institutions" % (len(submitters) - 5),
                                 size="xs", c="dimmed"))
        out.insert(1, dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
            dmc.Title("Submission Sources (%d unique)" % len(submitters), order=5, mb="xs"),
            *rows]))

    if accs:
        rows = []
        for a in accs:
            btns = []
            for typ, url in a["files"].items():
                col = "blue" if typ == "genome" else ("teal" if typ in ("cds", "protein") else "gray")
                btns.append(dmc.Anchor(dmc.Button("%s %s" % (a["name"], typ), size="xs",
                                                  variant="light", color=col), href=url, target="_blank"))
            rows.append(dmc.Group(gap=6, children=btns, mb=4))
        out.append(dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
            dmc.Title("Genome Annotation Downloads (%d)" % len(accs), order=5, mb="sm"),
            *rows]))

    # Genome Map: one per distinct structure (segment), deduplicated by isolate. Viroids (no CDS) show genome backbone only.
    seg_with_feats = segments
    has_any_cds = any(s["feats"] for s in segments)
    if segments:
        graphs = []
        for s in segments:
            seglab = (" · " + s["seg_label"]) if s["seg_label"] else ""
            iso = (" · %d isolates" % s["n"]) if s["n"] > 1 else ""
            graphs.append(dmc.Text("%s%s · %s bp · %d CDS%s" % (s["rep"], seglab, s["glen"] or "?", len(s["feats"]), iso),
                                   size="xs", fw=600, mt="xs"))
            if s["feats"]:
                graphs.append(dcc.Graph(figure=_genome_map_fig(s["feats"], s["glen"]),
                                        config={"displayModeBar": False}, style={"height": "180px"}))
            else:
                # No CDS (viroid etc.): circular map
                import math
                n = min(s["glen"] or 1, 2000)  # sampling for smooth circle
                r = 1
                theta = [2 * math.pi * i / n for i in range(n + 1)]
                cx, cy = [r * math.cos(t) for t in theta], [r * math.sin(t) for t in theta]
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=cx, y=cy, mode="lines", line=dict(color="#adb5bd", width=3),
                    hovertext="%s bp circular" % (s["glen"] or "?"), hoverinfo="text", showlegend=False))
                fig.add_annotation(x=0, y=0, text="Circular · %s bp<br>No CDS (viroid/non-coding)" % (s["glen"] or "?"),
                    showarrow=False, font=dict(size=9, color="#888"))
                fig.update_layout(height=220, margin=dict(l=8, r=8, t=4, b=4), plot_bgcolor="white",
                    xaxis=dict(visible=False, scaleanchor="y", scaleratio=1, fixedrange=True),
                    yaxis=dict(visible=False, fixedrange=True))
                graphs.append(dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "240px"}))
        gtitle = "Genome Map (%d segments/sequences)" % len(segments) if len(segments) > 1 else "Genome Map"
        tip = "Colored arrows = CDS, top row = plus strand / bottom row = minus strand. Hover for product and position. Multiple isolates of the same segment merged." if has_any_cds else "Viroid — no CDS features; genome backbone only."
        out.append(dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
            dmc.Title(gtitle, order=5, mb="xs"),
            dmc.Text(tip, size="xs", c="dimmed", mb="xs"),
            *graphs]))

    if proteins:
        out.append(dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
            dmc.Title("Proteins (%d)" % len(proteins), order=5, mb="sm"),
            dash_table.DataTable(
                data=proteins,
                columns=[{"name": "Segment/Sequence", "id": "segment"}, {"name": "Product", "id": "product"},
                         {"name": "Position", "id": "position"}, {"name": "Protein ID", "id": "protein_id"}],
                page_size=20, style_table={"overflowX": "auto"},
                style_cell={"fontSize": "12px", "padding": "6px", "textAlign": "left"},
                style_header={"backgroundColor": "#f1f3f5", "fontWeight": "bold"})]))

    if papers:
        items = []
        for p in papers:
            items.append(html.Div(style={"padding": "6px 0", "borderBottom": "1px solid #f0f0f0", "fontSize": "13px"}, children=[
                dmc.Badge(str(p.get("year", "")), color="green", variant="light", size="sm"),
                dcc.Link(" " + str(p.get("title", "")), href="https://pubmed.ncbi.nlm.nih.gov/%s" % p.get("pmid", ""),
                         target="_blank", style={"color": "#1a5276", "fontWeight": 600, "textDecoration": "none"}),
                html.Div("%s · %s" % (p.get("journal", ""), p.get("first_author", "")), style={"color": "#888", "fontSize": "11px"}),
            ]))
        out.append(dmc.Paper(withBorder=True, p="md", radius="md", mb="md", children=[
            dmc.Title("Related Literature (%d)" % len(papers), order=5, mb="sm"), *items]))

    from urllib.parse import quote as _q
    links = [dmc.Anchor("Vector-Host Relations (/vector/) →", href="/vector/", target="_blank", size="sm", c="blue")]
    if pc > 0:
        links.append(dmc.Anchor("Primer Database (%d records) →" % pc, href="/primers/search?q=" + _q(disp), target="_blank", size="sm", c="blue"))
    out.append(dmc.Paper(withBorder=True, p="md", radius="md", children=[
        dmc.Title("Related Resources", order=5, mb="sm"), dmc.Group(gap="lg", children=links)]))
    return out

app.layout = dmc.MantineProvider(
    theme={
        "fontFamily": "Inter, sans-serif",
        "primaryColor": "blue",
    },
    children=dmc.AppShell(
        padding="md",
        children=[
            dcc.Location(id="url", refresh=False),
            # 全量筛选结果（不受 DataTable 5000 行截断影响），供各分析面板使用：
            #   filtered-virus-counts = [[物种, 记录数], ...]（按记录数降序）
            #   filtered-trends-agg   = {物种: {"y": {年: 数}, "c": {国家: 数}}}
            dcc.Store(id="filtered-virus-counts"),
            dcc.Store(id="filtered-trends-agg"),

            # Analysis Dashboard
            html.Div(
                dmc.Group(
                    justify="flex-end", gap="xs",
                    children=[
                        dmc.Badge(str(N_SPECIES) + " species", color="gray", variant="filled"),
                        dmc.Badge(str(len(df_global)) + " sequences", color="blue", variant="filled"),
                        dmc.Badge(DATA_VERSION.split(" | ")[0] if " | " in DATA_VERSION else DATA_VERSION, color="green", variant="light")
                    ]
                ),
                style={"padding": "2px 6px 8px 0"},
            ),
            dmc.AppShellMain(
                children=dmc.Grid(
                    gutter="md",
                    children=[
                        # Sidebar: Advanced Control Panel
                        dmc.GridCol(
                            span={"base": 12, "md": 3},
                            children=dmc.Paper(
                                withBorder=True,
                                shadow="sm",
                                p="md",
                                radius="md",
                                children=[
                                    dmc.Title("Search & Multi-Sequence Alignment Controls", order=4, mb="md", style={"color": "#2c2e33"}),

                                    # ── 常用筛选（外露）──
                                    dmc.MultiSelect(
                                        id="virus-filter",
                                        label="Target Virus Species",
                                        placeholder="All Species (searchable)",
                                        data=[{"value": "Potato spindle tuber viroid", "label": "Potato spindle tuber viroid (PSTVd)"}],
                                        value=["Potato spindle tuber viroid"],
                                        searchable=True,
                                        clearable=True,
                                        mb="md"
                                    ),

                                    dmc.MultiSelect(
                                        id="host-filter",
                                        label="Filter by Host Species",
                                        placeholder="All Hosts (searchable)",
                                        data=HOST_FILTER_OPTIONS,
                                        searchable=True,
                                        clearable=True,
                                        mb="md"
                                    ),

                                    dmc.MultiSelect(
                                        id="country-select",
                                        label="Filter by Country/Region",
                                        placeholder="Select Region (searchable)",
                                        data=DYNAMIC_COUNTRY_OPTIONS,
                                        value=DYNAMIC_COUNTRY_DEFAULTS,
                                        searchable=True,
                                        clearable=True,
                                        mb="md"
                                    ),

                                    # ── 年份（常用，外露）──
                                    dmc.Text("Year Range", size="sm", style={"fontWeight": 600}, mb="xs"),
                                    dmc.Text("Drag the slider handles to select start and end year", size="xs", c="dimmed", mb="md"),
                                    html.Div(
                                        dcc.RangeSlider(
                                            id="year-slider",
                                            min=int(df_global['Year'].min()),
                                            max=int(df_global['Year'].max()),
                                            step=1,
                                            value=[int(df_global['Year'].min()), int(df_global['Year'].max())],
                                            marks=_build_year_marks(
                                                int(df_global['Year'].min()),
                                                int(df_global['Year'].max())
                                            ),
                                            allowCross=False,
                                            tooltip={"placement": "bottom", "always_visible": True}
                                        ),
                                        style={"padding": "0 30px 10px 10px", "marginTop": "4px"}
                                    ),
                                    dmc.Space(h="md"),

                                    dmc.Text("Year Data Source", size="sm", style={"fontWeight": 600}, mb="xs"),
                                    dmc.SegmentedControl(
                                        id="year-source",
                                        value="auto",
                                        data=[
                                            {"value": "auto", "label": "Auto (Collection > Submission)"},
                                            {"value": "collection", "label": "Collection Year Only"},
                                            {"value": "release", "label": "Submission Year Only"}
                                        ],
                                        fullWidth=True,
                                        mb="md"
                                    ),

                                    dmc.Switch(
                                        id="filter-na",
                                        label="Exclude Records w/o Collection Date (NA)",
                                        checked=True,
                                        mb="md"
                                    ),

                                    # ── 更多筛选（默认折叠：结构/科/完整性）──
                                    dmc.Accordion(
                                        multiple=True,
                                        value=[],
                                        mb="md",
                                        children=[
                                            dmc.AccordionItem(
                                                value="advanced",
                                                children=[
                                                    dmc.AccordionControl(
                                                        "More Filters (structure · family · completeness)",
                                                        style={"fontSize": "13px"}
                                                    ),
                                                    dmc.AccordionPanel(
                                                        children=[
                                                            dmc.MultiSelect(
                                                                id="category-filter",
                                                                label="Genome Structure (Segmented / Non-Segmented)",
                                                                placeholder="All Types",
                                                                data=[{"value": "Segmented", "label": f"Segmented  (Segmented) ({int(df_global['Category_Type'].value_counts().get('Segmented', 0)):,})"},
                                                                      {"value": "NonSegmented", "label": f"Non‑Segmented  (Non-Segmented) ({int(df_global['Category_Type'].value_counts().get('NonSegmented', 0)):,})"}],
                                                                value=["Segmented", "NonSegmented"],
                                                                mb="md"
                                                            ),

                                                            # 科：单选（选中后物种候选自动收窄，见 update_virus_options）
                                                            dmc.Select(
                                                                id="family-filter",
                                                                label="Virus Family",
                                                                placeholder="All Families (selectable)",
                                                                data=sorted(
                                                                    [{"value": v, "label": f"{v} ({int(c):,})"}
                                                                     for v, c in df_global['Family'].value_counts().items() if v != 'Unknown'],
                                                                    key=lambda x: x['value']
                                                                ),
                                                                searchable=True,
                                                                clearable=True,
                                                                mb="md"
                                                            ),

                                                            dmc.MultiSelect(
                                                                id="completeness-filter",
                                                                label="Sequence Completeness",
                                                                placeholder="All",
                                                                data=[
                                                                    {"value": "complete", "label": f"Complete  (Complete) ({int(df_global['Completeness'].value_counts().get('complete', 0)):,})"},
                                                                    {"value": "partial", "label": f"Partial  (Partial) ({int(df_global['Completeness'].value_counts().get('partial', 0)):,})"}
                                                                ],
                                                                value=["complete", "partial"],
                                                                mb="md"
                                                            ),
                                                        ]
                                                    )
                                                ]
                                            )
                                        ]
                                    ),

                                    dmc.Divider(my="md"),

                                    dmc.Button(
                                        "Apply Filters & Refresh Charts",
                                        id="query-btn",
                                        color="teal",
                                        fullWidth=True,
                                        radius="md",
                                        size="md",
                                        leftSection="🧬"
                                    )
                                ]
                            )
                        ),
                        
                        # Main Panel: In-Depth Visualization
                        dmc.GridCol(
                            span={"base": 12, "md": 9},
                            children=dmc.Paper(
                                withBorder=True,
                                shadow="sm",
                                p="md",
                                radius="md",
                                children=[
                                    dmc.Tabs(
                                        id="main-tabs",
                                        value="profile",
                                        children=[
                                            dmc.TabsList(
                                                mb="md",
                                                children=[
                                                    dmc.TabsTab("Virus Profile", value="profile", leftSection="🦠"),
                                                    dmc.TabsTab("Data Browser", value="table", leftSection="📋"),
                                                    dmc.TabsTab("Spatiotemporal Trends", value="trends", leftSection="📊"),
                                                    dmc.TabsTab("Genome-Wide Variation", value="mutation", leftSection="🧬"),
                                                    dmc.TabsTab("Primer Database", value="primers", leftSection="🧪"),
                                                    dmc.TabsTab("Host Range", value="host", leftSection="🌿"),
                                                    dmc.TabsTab("Vector Transmission", value="vector", leftSection="🐛")
                                                ]
                                            ),
                                            
                                            # Spatiotemporal Trends Panel
                                            dmc.TabsPanel(
                                                value="trends",
                                                children=[
                                                    dmc.Group(
                                                        justify="space-between",
                                                        mb="md",
                                                        children=[
                                                            dmc.Title("Spatiotemporal & Geographic Distribution", order=3),
                                                            dmc.Badge("Stacked + Map", color="gray")
                                                        ]
                                                    ),
                                                    dmc.MultiSelect(
                                                        id="trends-virus-select",
                                                        label="Display Virus Species (charts show only the selected; defaults to the most abundant)",
                                                        placeholder="All filtered species (pick one or more to narrow the charts)",
                                                        data=[],
                                                        value=[],
                                                        searchable=True,
                                                        clearable=True,
                                                        mb="md",
                                                        style={"maxWidth": 820}
                                                    ),
                                                    dcc.Loading(
                                                        type="cube", color="#12b886",
                                                        children=[
                                                            dmc.Title("(1) Temporal Distribution (Line Chart)", order=4, mb="xs"),
                                                            dmc.Text("X=Year, Y=Sequence Count, Color=Virus Species, Dots=Data Points", size="xs", c="dimmed", mb="xs"),
                                                            dcc.Graph(id="chart-time-stacked", style={"height": "350px"}),
                                                            dmc.Space(h="md"),
                                                            dmc.Title("(2) Geographic Distribution (Horizontal Bar Chart)", order=4, mb="xs"),
                                                            dmc.Text("Y=Country, X=Sequence Count, Color=Virus Species, [Unlabeled] = Missing Geo Info", size="xs", c="dimmed", mb="xs"),
                                                            dcc.Graph(id="chart-country-stacked", style={"height": "350px"}),
                                                            dmc.Space(h="md"),
                                                            dmc.Title("(3) Geographic Map (Shading=Total | Dots=Virus Composition & Count)", order=4, mb="xs"),
                                                            dcc.Graph(id="geo-map", style={"height": "380px"}),
                                                            dmc.Space(h="md"),
                                                            dmc.Grid(
                                                                gutter="md",
                                                                children=[
                                                                    dmc.GridCol(
                                                                        span=3,
                                                                        children=dmc.Card(
                                                                            withBorder=True,
                                                                            shadow="xs",
                                                                            p="sm",
                                                                            radius="md",
                                                                            children=[
                                                                                dmc.Text("Filtered Sequences (Accessions)", size="xs", c="dimmed"),
                                                                                dmc.Title(id="stat-total-seqs", order=3, c="teal")
                                                                            ]
                                                                        )
                                                                    ),
                                                                    dmc.GridCol(
                                                                        span=3,
                                                                        children=dmc.Card(
                                                                            withBorder=True,
                                                                            shadow="xs",
                                                                            p="sm",
                                                                            radius="md",
                                                                            children=[
                                                                                dmc.Text("Unique Species", size="xs", c="dimmed"),
                                                                                dmc.Title(id="stat-n-species", order=3, c="green")
                                                                            ]
                                                                        )
                                                                    ),
                                                                    dmc.GridCol(
                                                                        span=3,
                                                                        children=dmc.Card(
                                                                            withBorder=True,
                                                                            shadow="xs",
                                                                            p="sm",
                                                                            radius="md",
                                                                            children=[
                                                                                dmc.Text("Most Abundant Virus", size="xs", c="dimmed"),
                                                                                dmc.Title(id="stat-common-virus", order=4, c="indigo", style={"whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"})
                                                                            ]
                                                                        )
                                                                    ),
                                                                    dmc.GridCol(
                                                                        span=3,
                                                                        children=dmc.Card(
                                                                            withBorder=True,
                                                                            shadow="xs",
                                                                            p="sm",
                                                                            radius="md",
                                                                            children=[
                                                                                dmc.Text("Top Contributing Region", size="xs", c="dimmed"),
                                                                                dmc.Title(id="stat-top-country", order=3, c="orange")
                                                                            ]
                                                                        )
                                                                    )
                                                                ]
                                                            )
                                                        ]
                                                    )
                                                ]
                                            ),
                                            
                                            # Genome-Wide Alignment & Variation
                                            dmc.TabsPanel(
                                                value="mutation",
                                                children=[
                                                    dmc.Group(
                                                        justify="space-between",
                                                        mb="md",
                                                        children=[
                                                            dmc.Title("Alignment Matrix & Mutation Rate Curve", order=3),
                                                            dmc.Select(
                                                                id="mutation-virus-select",
                                                                label="Select Target Species for MSA",
                                                                data=[],
                                                                value="",
                                                                style={"width": 380}
                                                            )
                                                        ]
                                                    ),
                                                    dmc.Text(
                                                        "Based on real GenBank full-genome sequences. Global pairwise alignment maps multiple "
                                                        "sequences of the same species onto a reference coordinate system. "
                                                        "Base frequencies (A/T/G/C) and polymorphism rates are computed per site. "
                                                        "Drag to zoom, double-click to reset. Capped at 100 sequences for interactive performance.",
                                                        size="sm",
                                                        c="dimmed",
                                                        mb="lg"
                                                    ),
                                                    dcc.Loading(
                                                        type="cube", color="#12b886",
                                                        children=[
                                                            dmc.Title("Per-Site Base Abundance (A/T/G/C Heatmap)", order=5, mb="xs"),
                                                            dcc.Graph(id="alignment-heatmap", style={"height": "320px"}),
                                                            dmc.Space(h="md"),
                                                            dmc.Title("Nucleotide Mutation Rate & Top 10 Hotspot Legend", order=5, mb="xs"),
                                                            dcc.Graph(id="variation-line-chart", style={"height": "350px"})
                                                        ]
                                                    )
                                                ]
                                            ),
                                            
                                            # Data Browser
                                            dmc.TabsPanel(
                                                value="table",
                                                children=[
                                                    dmc.Group(
                                                        justify="space-between",
                                                        mb="md",
                                                        children=[
                                                            dmc.Title("SeqIO Processed Dataset Archive", order=3),
                                                            dmc.Button("Export CSV (Metadata)", id="export-btn", size="xs", color="teal", variant="light"),
                                                            dmc.Button("Export FASTA (Sequences)", id="export-fasta-btn", size="xs", color="green", variant="light"),
                                                            # 导出截断提示位（审计 P1 CSV 静默截断）：由 export_table_csv 回调填充
                                                            html.Div(id="export-note", style={"fontSize": "12px", "color": "#e8590c", "maxWidth": "460px", "textAlign": "right"})
                                                        ]
                                                    ),
                                                    dcc.Download(id="download-dataframe-csv"),
                                                    dcc.Download(id="download-fasta"),
                                                    dash_table.DataTable(
                                                        id='records-table',
                                                        columns=[
                                                            {"name": "Accession", "id": "Accession_md", "presentation": "markdown"},
                                                            {"name": "Species", "id": "Organism"},
                                                            {"name": "Family", "id": "Family"},
                                                            {"name": "Segment", "id": "Segment"},
                                                            {"name": "Segment (std)", "id": "Segment_std"},
                                                            {"name": "Molecule", "id": "Molecule_type"},
                                                            {"name": "Length", "id": "FullSequenceLength"},
                                                            {"name": "Completeness", "id": "Completeness"},
                                                            {"name": "Country", "id": "Country"},
                                                            {"name": "Geo_Location", "id": "Geo_Location"},
                                                            {"name": "Host", "id": "Host_Name"},
                                                            {"name": "Isolation Source", "id": "Isolation_Source"},
                                                            {"name": "Collection Date", "id": "Collection_Date"},
                                                            {"name": "Release Date", "id": "Release_Date"},
                                                            {"name": "Year", "id": "Year"},
                                                            {"name": "Definition", "id": "Definition"}
                                                        ],
                                                        data=[],
                                                        page_size=12,
                                                        style_table={'overflowX': 'auto'},
                                                        style_cell={
                                                            'fontFamily': 'Inter, sans-serif',
                                                            'fontSize': '13px',
                                                            'textAlign': 'left',
                                                            'padding': '10px'
                                                        },
                                                        style_header={
                                                            'backgroundColor': '#f1f3f5',
                                                            'fontWeight': 'bold',
                                                            'borderBottom': '2px solid #dee2e6'
                                                        },
                                                        style_cell_conditional=[
                                                            {'if': {'column_id': 'Definition'}, 'maxWidth': '340px', 'whiteSpace': 'normal'},
                                                            {'if': {'column_id': 'Geo_Location'}, 'minWidth': '150px'},
                                                            {'if': {'column_id': 'Isolation_Source'}, 'maxWidth': '160px', 'whiteSpace': 'normal'},
                                                            {'if': {'column_id': 'Accession_md'}, 'whiteSpace': 'nowrap'},
                                                        ]
                                                    )
                                                ]
                                            ),
                                            
                                            # Primer Database
                                            dmc.TabsPanel(
                                                value="primers",
                                                id="primers-panel",
                                                children=[
                                                    dmc.Title("Virus Primer Design Results", order=3, mb="md"),
                                                    dmc.Text(
                                                        "Primer data generated by the primer design pipeline. Sync primer_reference.tsv to docs/data/primers/ to display.",
                                                        size="sm", c="dimmed", mb="md"
                                                    ),
                                                    html.Div(id="primers-content", children=[
                                                        dmc.Text("Loading primer data...", size="sm", c="dimmed")
                                                    ])
                                                ]
                                            ),

                                            # Host Range
                                            dmc.TabsPanel(
                                                value="host",
                                                id="host-panel",
                                                children=[
                                                    dmc.Title("Virus Host Range Analysis", order=3, mb="md"),
                                                    dmc.MultiSelect(
                                                        id="host-virus-select",
                                                        label="Display Virus Species (defaults to the most abundant; pick one or more)",
                                                        placeholder="All filtered species",
                                                        data=[], value=[],
                                                        searchable=True, clearable=True, mb="md",
                                                        style={"maxWidth": 820}
                                                    ),
                                                    html.Div(id="host-content", children=[
                                                        dmc.Text("Loading host data...", size="sm", c="dimmed")
                                                    ])
                                                ]
                                            ),

                                            # Vector Transmission
                                            dmc.TabsPanel(
                                                value="vector",
                                                id="vector-panel",
                                                children=[
                                                    dmc.Title("Vector Transmission Analysis", order=3, mb="xs"),
                                                    dmc.Text(
                                                        "Experimentally validated virus×vector×host relationships (VH) plus WUR literature supplement. Follows left-side filters.",
                                                        size="sm", c="dimmed", mb="md"
                                                    ),
                                                    dmc.MultiSelect(
                                                        id="vector-virus-select",
                                                        label="Display Virus Species (defaults to the most abundant; pick one or more)",
                                                        placeholder="All filtered species",
                                                        data=[], value=[],
                                                        searchable=True, clearable=True, mb="md",
                                                        style={"maxWidth": 820}
                                                    ),
                                                    html.Div(id="vector-content", children=[
                                                        dmc.Text("Loading vector data...", size="sm", c="dimmed")
                                                    ])
                                                ]
                                            ),

                                            # Virus Profile
                                            dmc.TabsPanel(
                                                value="profile",
                                                children=[
                                                    dmc.Title("Virus Profile", order=3, mb="xs"),
                                                    dmc.Text("Defaults to the most abundant species in the current filter (and follows the filter when it narrows to exactly one). Pick one or more to stack several profiles. Covers genome maps, annotation downloads, proteins, literature, and primers.",
                                                             size="sm", c="dimmed", mb="md"),
                                                    dmc.MultiSelect(
                                                        id="profile-select",
                                                        label="Display virus species (defaults to the most abundant; pick one or more to compare)",
                                                        placeholder="Search species name...",
                                                        data=[],
                                                        value=[],
                                                        searchable=True, clearable=True, mb="md",
                                                        style={"maxWidth": 620}
                                                    ),
                                                    html.Div(id="profile-content", children=[
                                                        dmc.Text("Please select a virus species above.", size="sm", c="dimmed")
                                                    ])
                                                ]
                                            )
                                        ]
                                    )
                                ]
                            )
                        )
                    ]
                )
            )
        ]
    )
)

# -----------------------------------------------------------------------------
# 3. Web Callback Management
# -----------------------------------------------------------------------------

def _safe_int(value, default):
    """安全整数解析（审计 P2，2026-10-03）：URL 参数/界面文案可被任意篡改（非数字/空串/NaN/inf/小数/
    千分位逗号），非法值一律回退 default，避免 int() 抛 ValueError/OverflowError 导致回调 500。"""
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError, OverflowError):
        return default


@callback(
    [Output("host-filter", "value"),
     Output("country-select", "value"),
     Output("category-filter", "value"),
     Output("family-filter", "value"),
     Output("year-slider", "value")],
    Input("url", "search")
)
def parse_url_params(search):
    """Pre-populate filters from URL query parameters"""
    from urllib.parse import parse_qs
    _y_lo, _y_hi = int(df_global["Year"].min()), int(df_global["Year"].max())
    defaults = [None, [], ["Segmented", "NonSegmented"], None, [_y_lo, _y_hi]]
    if not search:
        return defaults
    params = parse_qs(search.lstrip("?"))
    host = params.get("host", [None])[0] or None
    country = params.get("country", [""])[0]
    country_vals = [c.strip() for c in country.split(",") if c.strip()] if country else []
    category = params.get("category", [""])[0]
    cat_vals = [c.strip() for c in category.split(",") if c.strip()] if category else ["Segmented", "NonSegmented"]
    family = params.get("family", [""])[0]
    fam = family.strip() or None  # 科已改单选（Select），值为字符串或 None
    ymin = _safe_int(params.get("year_min", [None])[0], _y_lo)
    ymax = _safe_int(params.get("year_max", [None])[0], _y_hi)
    # 越界/倒序一律夹回数据实际范围，避免 RangeSlider 收到非法区间
    ymin, ymax = max(_y_lo, min(ymin, _y_hi)), max(_y_lo, min(ymax, _y_hi))
    if ymin > ymax:
        ymin, ymax = ymax, ymin
    return host, country_vals or None, cat_vals, fam, [ymin, ymax]

@callback(
    [Output("virus-filter", "data"),
     Output("virus-filter", "value")],
    [Input("family-filter", "value"),
     Input("category-filter", "value")],
    [State("virus-filter", "value")]
)
def update_virus_options(selected_families, selected_categories, current_viruses):
    df = df_global.copy()
    if 'Category_Type' in df.columns and selected_categories:
        df = df[df['Category_Type'].isin(selected_categories)]
    fams = [selected_families] if isinstance(selected_families, str) else (selected_families or [])
    if 'Family' in df.columns and fams:
        df = df[df['Family'].isin(fams)]

    counts = df['Organism'].value_counts()
    virus_list = sorted(counts.index)
    options = [{"value": v, "label": f"{v} ({int(counts[v]):,})"} for v in virus_list]
    # 换科时优先保留仍在新候选里的已选物种（不粗暴重置成 PSTVd）
    keep = [v for v in (current_viruses or []) if v in virus_list]
    if keep:
        return options, keep
    # Default to PSTVd on first load
    default_val = ["Potato spindle tuber viroid"] if "Potato spindle tuber viroid" in virus_list else []
    return options, default_val


@callback(
    [Output("records-table", "data"),
     Output("mutation-virus-select", "data"),
     Output("mutation-virus-select", "value"),
     Output("stat-total-seqs", "children"),
     Output("stat-n-species", "children"),
     Output("stat-common-virus", "children"),
     Output("stat-top-country", "children"),
     Output("filtered-virus-counts", "data"),
     Output("filtered-trends-agg", "data")],
    [Input("query-btn", "n_clicks"),
     Input("url", "pathname")],
    [State("host-filter", "value"),
     State("country-select", "value"),
     State("category-filter", "value"),
     State("family-filter", "value"),
     State("virus-filter", "value"),
     State("completeness-filter", "value"),
     State("year-slider", "value"),
     State("year-source", "value"),
     State("filter-na", "checked"),
     ]
)
def update_data_pipeline(n_clicks, pathname, host, selected_countries, selected_categories, selected_families, selected_viruses, selected_completeness, year_range, year_source, filter_na):
    df = df_global.copy()


    # Exclude records without collection date (NA filter)
    if filter_na:
        df = df[df['Has_Collection_Date'] == True]

    # Recalculate Year based on selected data source
    if year_source == 'collection':
        df = df[df['Year_Collection'].notna()]
        df['Year'] = df['Year_Collection'].astype(int)
    elif year_source == 'release':
        df = df[df['Year_Release'].notna()]
        df['Year'] = df['Year_Release'].astype(int)
    # auto: keep default Year (collection priority, fallback to submission)

    # Host filter
    if 'Host_Name' in df.columns and host:
        df = df[df['Host_Name'].isin(host)]
    # Category filter (segmented/non-segmented)
    if 'Category_Type' in df.columns and selected_categories:
        df = df[df['Category_Type'].isin(selected_categories)]
    # Family filter（科为单选 Select：字符串；兼容旧 MultiSelect 的列表值）
    fams = [selected_families] if isinstance(selected_families, str) else (selected_families or [])
    if 'Family' in df.columns and fams:
        df = df[df['Family'].isin(fams)]
    # Completeness filter
    if 'Completeness' in df.columns and selected_completeness:
        df = df[df['Completeness'].isin(selected_completeness)]

    # Virus filter (empty = all)
    if selected_viruses:
        df = df[df['Organism'].isin(selected_viruses)]
        # When a specific virus is selected, skip country filter (avoids filtering out all records due to missing country)
        skip_country_filter = True
    else:
        skip_country_filter = False

    # Country filter (empty = all; skipped when virus is selected)
    if selected_countries and not skip_country_filter:
        df = df[df['Country'].isin(selected_countries)]

    df_filtered = df[
        (df['Year'] >= year_range[0]) &
        (df['Year'] <= year_range[1])
    ]

    if df_filtered.empty:
        return [], [], "", "0", "0", "No valid records", "None", [], {}

    total_seqs = f"{len(df_filtered):,}"
    n_species = f"{df_filtered['Organism'].nunique():,}"
    common_virus = df_filtered['Organism'].mode()[0] if not df_filtered.empty else "N/A"
    top_country = df_filtered['Country'].mode()[0] if not df_filtered.empty else "N/A"

    virus_options = [{"value": v, "label": v} for v in df_filtered['Organism'].unique()]
    # 默认物种 = 最丰富（记录数最多）的一个，而非 df 顺序里的第一个
    default_virus = df_filtered['Organism'].value_counts().index[0] if len(virus_options) > 0 else ""

    # ── 全量筛选结果的两种轻量视图（不受 DataTable 5000 行截断影响）──
    # ① [[物种, 记录数], ...] 按记录数降序 → 各展示选择器的候选与「最丰富」默认值
    _vc = df_filtered['Organism'].value_counts()
    virus_counts = [[str(_k), int(_v)]
                    for _k, _v in sorted(_vc.items(), key=lambda kv: (-kv[1], str(kv[0])))]
    # ② {物种: {"y": {年: 数}, "c": {国家: 数}}} → Spatiotemporal 三张图直接由它构建
    #    （一次 groupby 展开，避免按物种逐个 value_counts 的 Python 开销）
    trends_agg = {}
    for (_org, _y), _n in df_filtered.groupby(['Organism', 'Year'], sort=False).size().items():
        trends_agg.setdefault(str(_org), {"y": {}, "c": {}})["y"][str(int(_y))] = int(_n)
    for (_org, _c), _n in df_filtered.groupby(['Organism', 'Country'], sort=False).size().items():
        trends_agg.setdefault(str(_org), {"y": {}, "c": {}})["c"][str(_c)] = int(_n)

    table_data = df_filtered.drop(columns=['Sequence'], errors='ignore').to_dict('records')
    # Table row cap: prevent browser from processing 190K records when unfiltered
    if len(table_data) > TABLE_MAX_ROWS:
        table_data = table_data[:TABLE_MAX_ROWS]
    # NCBI 跳转：Accession_md 渲染列（表格内 markdown 链接）；纯文本 Accession
    # 保留给 MSA/导出等回调使用，避免 markdown 串污染下游。旧数据缺节段列补空。
    for r in table_data:
        acc = str(r.get('Accession', ''))
        r['Accession_md'] = '[%s](https://www.ncbi.nlm.nih.gov/nuccore/%s)' % (acc, acc)
        seg = r.get('Segment_Info', '')
        r['Segment'] = '' if seg in ('', 'N/A', None) else seg
        r['Segment_std'] = r.get('Segment_std', '') or ''
    return (table_data, virus_options, default_virus, total_seqs, n_species, common_virus, top_country,
            virus_counts, trends_agg)

@callback(
    [Output("chart-time-stacked", "figure"),
     Output("chart-country-stacked", "figure"),
     Output("geo-map", "figure")],
    [Input("filtered-trends-agg", "data"),
     Input("trends-virus-select", "value")]
)
def render_spatiotemporal_chart(trends_agg, selected_viruses):
    if not trends_agg:
        return go.Figure(), go.Figure(), go.Figure()

    # 只画被选中的物种（多选）。空选 = 不过滤（展示全部），避免清空后图表变空白。
    if selected_viruses:
        sel = [v for v in selected_viruses if v in trends_agg]
    else:
        sel = sorted(trends_agg.keys())
    if not sel:
        return go.Figure(), go.Figure(), go.Figure()

    try:
        # (1) Temporal distribution — line chart + scatter markers
        time_df = pd.DataFrame(
            [{"Year": int(_y), "Organism": _v, "Count": int(_n)}
             for _v in sel for _y, _n in trends_agg[_v].get("y", {}).items()])
        if time_df.empty:
            return go.Figure(), go.Figure(), go.Figure()
        fig_time = px.line(
            time_df, x='Year', y='Count', color='Organism',
            markers=True,
            labels={'Count': 'Sequence Count', 'Year': 'Year'},
            color_discrete_sequence=px.colors.qualitative.G10,
            height=330
        )
        fig_time.update_layout(
            plot_bgcolor='white', paper_bgcolor='white',
            legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
            margin=dict(l=45, r=20, t=20, b=80),
            font=dict(family="Inter, sans-serif", size=11),
            xaxis=dict(tickmode='linear', dtick=5)
        )
        fig_time.update_yaxes(showgrid=True, gridcolor='#f1f3f5')
        fig_time.update_traces(line=dict(width=2.5), marker=dict(size=8))

        # (2) Geographic distribution — horizontal bar chart (with Unknown labels)
        country_df = pd.DataFrame(
            [{"Country": _c, "Organism": _v, "Count": int(_n)}
             for _v in sel for _c, _n in trends_agg[_v].get("c", {}).items()])
        if country_df.empty:
            return fig_time, go.Figure(), go.Figure()
        # Rename Unknown to "Unlabeled" for chart readability
        country_df['Country'] = country_df['Country'].replace('Unknown', 'Unlabeled')
        country_order = country_df.groupby('Country')['Count'].sum().sort_values(ascending=True).index.tolist()
        fig_country = px.bar(
            country_df, y='Country', x='Count', color='Organism',
            orientation='h',
            category_orders={'Country': country_order},
            labels={'Count': 'Sequence Count', 'Country': 'Country'},
            color_discrete_sequence=px.colors.qualitative.G10,
            height=330
        )
        fig_country.update_layout(
            barmode='stack',
            plot_bgcolor='white', paper_bgcolor='white',
            legend=dict(orientation="h", yanchor="bottom", y=-0.38, xanchor="center", x=0.5),
            margin=dict(l=100, r=20, t=20, b=80),
            font=dict(family="Inter, sans-serif", size=11)
        )
        fig_country.update_yaxes(showgrid=False, gridcolor='#f1f3f5')
        fig_country.update_xaxes(showgrid=True, gridcolor='#f1f3f5')

        # (3) Geographic map — choropleth + scatter
        geo_detail = country_df[country_df['Country'] != 'Unlabeled'].copy()
        geo_detail['Country_ISO'] = geo_detail['Country'].map(COUNTRY_NAME_MAP).fillna(geo_detail['Country'])
        country_total = geo_detail.groupby('Country_ISO')['Count'].sum().reset_index(name='Total')

        all_viruses = sorted(sel)
        color_palette = px.colors.qualitative.G10 + px.colors.qualitative.Set3
        virus_colors = {v: color_palette[i % len(color_palette)] for i, v in enumerate(all_viruses)}

        fig_map = go.Figure()
        fig_map.add_trace(go.Choropleth(
            locations=country_total['Country_ISO'], locationmode='country names',
            z=country_total['Total'], colorscale='OrRd',
            colorbar=dict(title='Total Reports', thickness=15, len=0.55, x=0.87),
            marker_line_color='white', marker_line_width=0.5,
            hovertemplate='%{location}: %{z} sequences<extra></extra>',
            name='Total (Shading)'
        ))

        virus_order = geo_detail.groupby('Organism')['Count'].sum().sort_values(ascending=True).index.tolist()
        for virus_name in virus_order:
            vdf = geo_detail[geo_detail['Organism'] == virus_name].copy()
            if vdf.empty:
                continue
            marker_sizes = vdf['Count'].clip(lower=1).apply(lambda x: max(8, min(55, x ** 0.5 * 4)))
            hover_texts = []
            for _, r in vdf.iterrows():
                ctotal = country_total.set_index('Country_ISO').loc[r['Country_ISO'], 'Total']
                pct = r['Count'] / ctotal * 100 if ctotal > 0 else 0
                hover_texts.append(
                    f"<b>{r['Country_ISO']}</b><br>Total: {ctotal}<br>"
                    f"{virus_name[:45]}: {r['Count']} ({pct:.1f}%)"
                )
            fig_map.add_trace(go.Scattergeo(
                locations=vdf['Country_ISO'], locationmode='country names',
                marker=dict(
                    size=marker_sizes,
                    color=virus_colors[virus_name],
                    line=dict(color='white', width=1.5),
                    sizemode='diameter', opacity=0.75
                ),
                text=hover_texts, hoverinfo='text',
                mode='markers', name=virus_name[:48]
            ))

        fig_map.update_layout(
            margin=dict(l=5, r=5, t=5, b=5),
            geo=dict(
                showframe=False, showcoastlines=True,
                projection_type='natural earth',
                showcountries=True, countrycolor='#ccc',
                showland=True, landcolor='#f8f9fa',
                showocean=True, oceancolor='#e8f0fe'
            ),
            legend=dict(
                title=dict(text='<b>Virus Species</b>', font=dict(size=11)),
                orientation='v', yanchor='top', y=0.98, xanchor='left', x=0.01,
                bgcolor='rgba(255,255,255,0.9)', bordercolor='#ddd', borderwidth=1,
                font=dict(size=8.5), itemsizing='constant'
            ),
            font=dict(family="Inter, sans-serif", size=10)
        )

        return fig_time, fig_country, fig_map
    except Exception as e:
        import traceback
        print(f"[ERROR] render_spatiotemporal_chart: {e}")
        traceback.print_exc()
        return go.Figure(), go.Figure(), go.Figure()

# Genome alignment visualization parameters
# DoS 约束（审计 S5，2026-10-03）：本服务公网可达且无鉴权（nginx → :8050，gunicorn 单 worker）。
# 变异面板做全局两两比对 O(n²)，实测单条 ~19 kb 基因组 ~5.3 s；100 条 × 全局比对时单请求可吃满
# 单核数十秒，2 个并发即 504 排队。上限收紧为 30 条 / 20 kb，把单请求算力预算压进可接受范围。
MAX_ALIGN_SEQS = 30        # max sequences to align (was 100; DoS cap, audit S5)
MAX_DISPLAY_BP = 20000     # Safety cap for extremely long genomes; normally displays full length; use Plotly zoom for details (was 30000; DoS cap, audit S5)

@callback(
    [Output("alignment-heatmap", "figure"),
     Output("variation-line-chart", "figure")],
    [Input("records-table", "data"),
     Input("mutation-virus-select", "value")]
)
def render_genomic_plots(table_data, selected_virus):
    if not selected_virus:
        return go.Figure(), go.Figure()

    # 表格被截断到 TABLE_MAX_ROWS 行：若目标物种恰好不在截断表里，直接按物种名
    # 从全量数据取序列（回退），避免选了物种却出空图。
    df_virus_accs = set()
    if table_data:
        df_table = pd.DataFrame(table_data)
        df_virus_accs = set(df_table[df_table['Organism'] == selected_virus]['Accession'].tolist())

    # Fetch real sequences from df_global by Accession; avoid passing large sequence data in table_data
    if df_virus_accs:
        df_seq = df_global[df_global['Accession'].isin(df_virus_accs)]
    else:
        df_seq = df_global[df_global['Organism'] == selected_virus]
    sequences = df_seq['Sequence'].tolist()
    sequences = [seq for seq in sequences if seq and len(seq) > 0]
    
    if len(sequences) == 0:
        return go.Figure(), go.Figure()

    # limit aligned sequences for rendering performance
    if len(sequences) > MAX_ALIGN_SEQS:
        sequences = sequences[:MAX_ALIGN_SEQS]

    # Use first molecule as coordinate reference; apply Bio.Align coordinate mapping
    reference = sequences[0]
    aligned_seqs = align_to_reference(sequences, reference)
    
    # Frequency and mutation entropy calculation
    freq_matrix, variation_rates = compute_alignment_matrices(aligned_seqs)
    
    # Dynamic coordinate range: default to full reference length (safety truncation for extreme cases)
    ref_len = len(reference)
    display_len = min(ref_len, MAX_DISPLAY_BP)
    positions = list(range(1, display_len + 1))

    # Slice matrix and mutation rate to display range
    freq_display = freq_matrix[:, :display_len]
    var_display = variation_rates[:display_len]

    # 1. Base abundance heatmap (Plasma colormap distinguishes single-base from heterozygous sites)
    nucleotides = ['A', 'T', 'G', 'C']
    x_label = f"Alignment Reference Coordinate (nt, full length {ref_len} bp — drag to zoom)" if ref_len <= MAX_DISPLAY_BP else f"Alignment Reference Coordinate (first {MAX_DISPLAY_BP} / {ref_len} bp)"
    fig_heatmap = px.imshow(
        freq_display,
        y=nucleotides,
        x=positions,
        color_continuous_scale="Plasma",
        labels=dict(x=x_label, y="Base", color="Frequency"),
        aspect="auto"
    )
    fig_heatmap.update_layout(
        coloraxis_showscale=True,
        margin=dict(l=45, r=20, t=15, b=40),
        height=280,
        font=dict(family="Inter, sans-serif", size=10)
    )
    
    # 2. Mutation rate curve with Top 10 hotspot annotation
    sorted_indices = np.argsort(var_display)[::-1]
    top_n = min(10, len(sorted_indices))
    top_pos = sorted_indices[:top_n]
    top_rates = var_display[top_pos]
    
    fig_line = go.Figure()
    
    fig_line.add_trace(go.Scatter(
        x=positions,
        y=var_display,
        mode='lines',
        name='Polymorphism Rate',
        line=dict(color='#a01a1a', width=1.5)
    ))
    
    fig_line.add_trace(go.Scatter(
        x=top_pos + 1,
        y=top_rates,
        mode='markers',
        name=f'Key Hotspots (Top {top_n})',
        marker=dict(color='#fd7e14', size=8, symbol='triangle-down', line=dict(color='black', width=1))
    ))
    
    # Insert high-precision annotation arrows into chart
    for idx, pos in enumerate(top_pos):
        fig_line.add_annotation(
            x=pos + 1,
            y=top_rates[idx],
            text=f"{pos+1}nt",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-25,
            arrowcolor='black',
            font=dict(size=9, color='black', family="Inter, sans-serif")
        )
    
    info_text = f"{selected_virus[:40]}  |  {len(aligned_seqs)} sequences aligned  |  Reference {ref_len} bp"
    fig_line.update_layout(
        title=dict(text=info_text, font=dict(size=10, color='#555')),
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=45, r=20, t=35, b=40),
        height=350,
        showlegend=True,
        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
        font=dict(family="Inter, sans-serif", size=10)
    )
    fig_line.update_yaxes(range=[-0.05, 1.15], showgrid=True, gridcolor='#f1f3f5', linecolor='#ced4da')
    fig_line.update_xaxes(showgrid=True, gridcolor='#f1f3f5', linecolor='#ced4da')
    
    return fig_heatmap, fig_line

@callback(
    [Output("download-dataframe-csv", "data"),
     Output("export-note", "children")],
    Input("export-btn", "n_clicks"),
    State("records-table", "data"),
    State("stat-total-seqs", "children"),
    prevent_initial_call=True
)
def export_table_csv(n_clicks, table_data, total_seqs_text):
    if not table_data:
        return None, no_update
    df = pd.DataFrame(table_data)
    if 'Sequence' in df.columns:
        df = df.drop(columns=['Sequence'])
    # 渲染用列不进导出（纯 Accession 列保留，NCBI URL 即 nuccore/<accession>）
    if 'Accession_md' in df.columns:
        df = df.drop(columns=['Accession_md'])
    # 截断检测（审计 P1，2026-10-03）：records-table 数据在 update_data_pipeline 里被切成
    # TABLE_MAX_ROWS 行，导出只能拿到截断后的行 → 旧行为静默只导出前 5000 行、用户无感知。
    # 用统计面板「总条数」对比实际导出行数判断；总数字段不可用时退化为「打满上限即视为截断」。
    _total = _safe_int(total_seqs_text, None) if total_seqs_text else None
    truncated = (_total > len(df)) if _total is not None else (len(df) >= TABLE_MAX_ROWS)
    if truncated:
        fname = "plantvirus_alignment_metadata_first%d.csv" % TABLE_MAX_ROWS
        note = ("⚠ 导出已截断：仅导出前 %s 行%s；全量请用数据下载入口（docs/data/）。"
                % (format(TABLE_MAX_ROWS, ","),
                   "（当前筛选共 %s 行）" % format(_total, ",") if _total else ""))
        return dcc.send_data_frame(df.to_csv, fname, index=False), note
    return dcc.send_data_frame(df.to_csv, "plantvirus_alignment_metadata.csv", index=False), ""

@callback(
    Output("download-fasta", "data"),
    Input("export-fasta-btn", "n_clicks"),
    State("records-table", "data"),
    prevent_initial_call=True
)
def export_table_fasta(n_clicks, table_data):
    if not table_data:
        return None
    accessions = {row["Accession"] for row in table_data if row.get("Accession")}
    if not accessions:
        return None
    import io
    fasta_io = io.StringIO()
    count = 0
    for rec in SeqIO.parse(DATA_FASTA, "fasta"):
        if rec.id in accessions:
            desc = rec.description.split(" ", 1)[1] if " " in rec.description else ""
            header = f">{rec.id} {desc}".strip()
            fasta_io.write(header + "\n")
            seq_str = str(rec.seq)
            for i in range(0, len(seq_str), 80):
                fasta_io.write(seq_str[i:i+80] + "\n")
            count += 1
            if count >= len(accessions):
                break
    fasta_io.seek(0)
    return dcc.send_string(fasta_io.getvalue(), "plantvirus_sequences.fasta")



# ── Primer Database Panel ──────────────────────────────────────
@callback(
    Output("primers-content", "children"),
    Input("mutation-virus-select", "value"),
)
def load_primers_panel(selected_virus):
    import config
    primer_path = config.PRIMER_OUTPUTS.get("reference_tsv", "")
    if not primer_path or not os.path.exists(primer_path):
        return dmc.Alert("Primer data has not been synced yet.", color="yellow", variant="light", mb="md")
    try:
        if selected_virus:
            search_terms = _lookup_names(selected_virus)
            matched = []
            with open(primer_path, encoding='utf-8') as f:
                for row in csv.DictReader(f, delimiter='\t'):
                    if any(t in str(row.values()).lower() for t in search_terms):
                        matched.append(row)
            if not matched:
                return dmc.Text(f"No records found for {selected_virus} primer records (searched all)", c="dimmed")
            primer_df = pd.DataFrame(matched)
        else:
            primer_df = pd.read_csv(primer_path, sep='\t', nrows=500)

        from urllib.parse import quote
        ictv_name = primer_df.iloc[0].get('Species', selected_virus or '')
        embed_url = f"/species/{quote(ictv_name)}" if ictv_name else None
        return [
            dmc.Text(f"{len(primer_df)} primer pairs — {ictv_name}" if selected_virus else f"Primer Data Table (first 500 rows)", fw=600, mb="sm"),
            dash_table.DataTable(
                data=primer_df.head(100).to_dict('records'),
                columns=[{"name": c, "id": c} for c in primer_df.columns],
                page_size=10,
                style_table={'overflowX': 'auto'},
                style_cell={'fontSize': '12px', 'padding': '6px'},
                style_header={'backgroundColor': '#f1f3f5', 'fontWeight': 'bold'}
            ),
            dmc.Anchor("View Full Primer Details →", href=embed_url, target="_blank", size="sm", c="blue", mt="md") if selected_virus else None
        ]
    except Exception as e:
        return dmc.Alert(f"Primer data failed to load: {e}", color="red", variant="light")


# ── Host Range Panel ────────────────────────────────────────
def _host_section(selected_virus, host_range_path):
    """单个物种的宿主分布：属级条形图 + 属/种明细表。"""
    search_terms = _lookup_names(selected_virus)
    matched = []
    if os.path.exists(host_range_path):
        with open(host_range_path, encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                if any(t in row.get('Species','').lower() for t in search_terms):
                    matched.append(row)
    if not matched:
        return [dmc.Text(f"No records found for {selected_virus}", c="dimmed")]
    # Count ALL hosts and group by genus -> species
    genus_species = defaultdict(Counter)
    for r in matched:
        for h in r.get('Host_List','').split(';'):
            h = h.strip()
            if not h: continue
            parts = h.split()
            genus = parts[0] if parts else h
            genus_species[genus][h] += 1
    genus_totals = {g: sum(sp.values()) for g, sp in genus_species.items()}
    genera_sorted = sorted(genus_totals.items(), key=lambda x: -x[1])

    # Bar chart - ALL genera
    fig = px.bar(x=[g[0] for g in genera_sorted], y=[g[1] for g in genera_sorted],
        labels={'x':'Host Genus', 'y':'Records'}, title=f"Host Genera of {selected_virus[:40]} ({len(genera_sorted)} genera)")
    fig.update_layout(margin=dict(l=10,r=10,t=40,b=10), height=350)
    fig.update_xaxes(tickfont=dict(size=10))

    # Genus table - one row per genus, species wrapped fully
    total_spp = sum(len(v) for v in genus_species.values())
    genus_rows = []
    for genus, total in genera_sorted:
        spp = genus_species[genus]
        sp_text = '; '.join(f"{s}({c})" for s, c in spp.most_common())
        genus_rows.append({'Host Genus': genus, 'Records': total, 'Host Species': sp_text})

    return [dcc.Graph(figure=fig, config={'displayModeBar': False}),
        dmc.Text(f"Host Genus Distribution ({len(genera_sorted)} genera, {total_spp} species)", fw=600, mb="xs", mt="md"),
        dash_table.DataTable(data=genus_rows,
            columns=[{"name": "Host Genus", "id": "Host Genus"}, {"name": "Records", "id": "Records"}, {"name": "Host Species", "id": "Host Species"}],
            page_size=20, style_table={'overflowX': 'auto'},
            style_cell={'fontSize':'12px','padding':'6px','whiteSpace':'normal','height':'auto'},
            style_header={'backgroundColor':'#f1f3f5','fontWeight':'bold'}
        )]


@callback(
    Output("host-content", "children"),
    Input("host-virus-select", "value"),
)
def load_host_panel(selected_viruses):
    import config
    data_dir = os.path.dirname(config.PIPELINE_OUTPUTS.get("full_tsv", ""))
    host_range_path = os.path.join(data_dir, "host_analysis", "virus_host_range.tsv")
    host_summary_path = os.path.join(data_dir, "host_analysis", "virus_host_range_summary.tsv")
    host_freq_path = os.path.join(data_dir, "host_analysis", "host_frequency.tsv")
    if not os.path.exists(host_summary_path):
        return dmc.Alert("Host data has not been synced yet.", color="yellow", variant="light", mb="md")
    if isinstance(selected_viruses, str):
        selected_viruses = [selected_viruses]
    selected_viruses = [v for v in (selected_viruses or []) if v]
    try:
        if selected_viruses:
            out = []
            for i, sv in enumerate(selected_viruses):
                if i:
                    out.append(dmc.Divider(label=sv, labelPosition="center", my="lg"))
                out.extend(_host_section(sv, host_range_path))
            return out
        else:
            hdf = pd.read_csv(host_summary_path, sep='\t')
            # Quick stats
            stats = ""
            if os.path.exists(host_freq_path):
                ff = pd.read_csv(host_freq_path, sep='\t', nrows=3)
                stats = f"Top hosts: {ff.iloc[0]['Host']} ({ff.iloc[0]['Count']}), {ff.iloc[1]['Host']} ({ff.iloc[1]['Count']})"
            return [
                dmc.Text(stats, size="sm", c="dimmed", mb="sm") if stats else None,
                dmc.Text(f"Host Range by Family ({len(hdf)} families)", fw=600, mb="xs"),
                dash_table.DataTable(data=hdf.head(30).to_dict('records'),
                    columns=[{"name": c, "id": c} for c in hdf.columns],
                    page_size=15, style_table={'overflowX': 'auto'},
                    style_cell={'fontSize':'12px','padding':'6px','maxWidth':'350px','overflow':'hidden','textOverflow':'ellipsis'},
                    style_header={'backgroundColor':'#f1f3f5','fontWeight':'bold'})
            ]
    except Exception as e:
        return dmc.Alert(f"Host data failed to load: {e}", color="red", variant="light")


# ── Vector Transmission Panel ────────────────────────────────────────
@callback(
    Output("vector-content", "children"),
    [Input("filtered-virus-counts", "data"),
     Input("vector-virus-select", "value")],
)
def load_vector_panel(virus_counts, selected_viruses):
    if not VECTOR_DB:
        return dmc.Alert("Vector data not loaded (virus_vector_merged.json missing; run build_vector_db.py first).",
                         color="yellow", variant="light")
    if not virus_counts:
        return dmc.Text("Set filters on the left and click 'Apply Filters & Refresh Charts'.", c="dimmed")

    # 用全量筛选结果（非 5000 行截断表）取物种，避免选中物种不在截断表里时无内容
    organisms = sorted({str(v) for v, _ in virus_counts})
    # 展示层多选：只保留被选中的物种（空选 = 全部，避免清空后无内容）
    if selected_viruses:
        _sel = set(selected_viruses)
        organisms = [o for o in organisms if o in _sel]
    matched = {}
    for org in organisms:
        rec = _vector_lookup(org)
        if rec:
            matched[rec["canonical_name"]] = rec

    n_total, n_matched = len(organisms), len(matched)

    # Summary statistics (always shown)
    coverage = dmc.Group(mb="md", gap="md", children=[
        _vec_stat("Filtered Species", n_total, "gray"),
        _vec_stat("With Vector Records", n_matched, "teal"),
        _vec_stat("Relationship Triplets", sum(len(v["relationships"]) for v in matched.values()), "indigo"),
    ])

    if n_matched == 0:
        return [coverage, dmc.Alert(
            "No vector transmission records found for the current filter range "
            "(expected for viroids/non-arthropod-borne genera). "
            "Try filtering for vector-borne families (e.g. Geminiviridae, Luteoviridae, Tospoviridae) and refresh.",
            color="blue", variant="light")]

    # Expand focal relationships (detail table/transmission mode based on focal virus only)
    rels = []
    for rec in matched.values():
        for r in rec["relationships"]:
            rels.append((rec["canonical_name"], r, rec))

    if not rels:
        return [coverage, dmc.Alert(
            "No structured vector-host triplets available for matched species "
            "(WUR literature-level data may exist). Check /vector/ for literature evidence.", color="blue", variant="light")]

    focus_names = set(matched.keys())

    # Sankey context expansion: anchor on focal virus vector species, pull in other viruses transmitted by the same vector as background.
    # Focal virus highlighted. Prevents sparse graphs for single-virus cases.
    focus_vectors = {r["vector"] for _, r, _ in rels if r["vector"]}
    sankey_rels = list(rels)
    if focus_vectors:
        for cn, rec in VECTOR_DB.items():
            if cn in focus_names:
                continue
            for r in rec["relationships"]:
                if r["vector"] in focus_vectors:
                    sankey_rels.append((cn, r, rec))

    # (2) Sankey: Virus → Vector Order → Host (focal red, background blue)
    sankey = dcc.Graph(figure=_build_vector_sankey(sankey_rels, focus_names),
                       config={"displayModeBar": False}, style={"height": "480px"})

    # ① Relationship Details Table (with /virus/ links and sources)
    from urllib.parse import quote
    rows = []
    for cname, r, rec in rels:
        src = "＋".join(rec["sources"])
        rows.append({
            "virus": f"[{cname}](/virus/{quote(cname)})",
            "vector_order": r["vector_order"] or "—",
            "vector": r["vector"] or "—",
            "host": r["host"] or "—",
            "transmission": r["transmission_category"] if r["transmission_category"] != "Unknown" else (r["transmission_mode"] or "—"),
            "source": src,
        })
    rows.sort(key=lambda x: (x["virus"].lower(), x["vector_order"]))
    table = dash_table.DataTable(
        data=rows,
        columns=[
            {"name": "Virus", "id": "virus", "presentation": "markdown"},
            {"name": "Vector Order", "id": "vector_order"},
            {"name": "Vector", "id": "vector"},
            {"name": "Host", "id": "host"},
            {"name": "Transmission Mode", "id": "transmission"},
            {"name": "Source", "id": "source"},
        ],
        page_size=15, sort_action="native", filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontSize": "12px", "padding": "6px", "textAlign": "left",
                    "fontFamily": "Inter, sans-serif", "maxWidth": "260px",
                    "whiteSpace": "normal", "height": "auto"},
        style_header={"backgroundColor": "#f1f3f5", "fontWeight": "bold"},
        markdown_options={"link_target": "_blank"},
    )

    return [
        coverage,
        dmc.Group(justify="space-between", align="center", mb="xs", children=[
            dmc.Title("(1) Vector-Host Relationship Details", order=5),
            dmc.Anchor("Open Full Vector Database (/vector/) →", href="/vector/", target="_blank", size="sm", c="blue"),
        ]),
        table,
        dmc.Space(h="lg"),
        dmc.Title("(2) Transmission Network: Virus → Vector Species → Host", order=5, mb="xs"),
        dmc.Text("Focal virus (red) placed within its vector ecological network. "
                 "Other viruses sharing the same vector species shown as background (blue). "
                 "Link width = record count. Nodes truncated by abundance when too many; focal virus always preserved.",
                 size="xs", c="dimmed", mb="xs"),
        sankey,
    ]


def _vec_stat(label, value, color):
    return dmc.Card(withBorder=True, shadow="xs", p="sm", radius="md", children=[
        dmc.Text(label, size="xs", c="dimmed"),
        dmc.Title(f"{value:,}", order=3, c=color),
    ])


# ── 展示层物种选择器（Trends / Profile / Host / Vector）────────────────────────
# 左栏 Target Virus Species 负责「筛数据」；这里四个多选框只负责「显示哪些」。
# 统一行为：默认 = 当前筛选结果里最丰富（记录数最多）的物种；随 Apply 同步刷新；
# 若原选择仍在新结果里则保留，否则回落到最丰富。仅 1 个物种时自然就等于它（与 Apply 同步）。
def _ordered_organism_counts(table_data):
    """按记录数降序返回 [(species, count)]；同数按名称排序以保证确定性。
    入参兼容两种形态：表格记录列表（含 Organism 键）或 [[species, count], ...] 计数列表。"""
    if table_data and isinstance(table_data[0], (list, tuple)):
        return [(str(v), int(c)) for v, c in table_data]
    cnt = Counter(r.get("Organism", "") for r in (table_data or []) if r.get("Organism"))
    return sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))


def _pick_display_default(ordered, current=None, valid=None):
    """展示选择器的默认值 = 当前筛选结果里最丰富（记录数最多）的物种。
    每次 Apply 都重置到该默认值（与「Apply Filters & Refresh Charts」同步）；
    valid 用于 Profile：只在「参考库里有 Profile」的物种里挑最丰富的一个。"""
    for v, _ in ordered:
        if valid is None or v in valid:
            return [v]
    return []


@callback(
    [Output("trends-virus-select", "data"),
     Output("trends-virus-select", "value"),
     Output("profile-select", "data"),
     Output("profile-select", "value", allow_duplicate=True),
     Output("host-virus-select", "data"),
     Output("host-virus-select", "value"),
     Output("vector-virus-select", "data"),
     Output("vector-virus-select", "value")],
    Input("filtered-virus-counts", "data"),
    Input("url", "search"),
    prevent_initial_call=True,
)
def sync_display_virus_selectors(virus_counts, search):
    ordered = _ordered_organism_counts(virus_counts)
    if not ordered:
        return [], [], [], [], [], [], [], []
    opts = [{"value": v, "label": "%s (%s)" % (v, format(c, ","))} for v, c in ordered]
    # Profile 只列参考库里确实有 Profile 的物种（NCBI 名 / ICTV 名均可命中）
    p_opts = [o for o in opts if _has_profile(o["value"])]
    p_valid = {o["value"] for o in p_opts}
    # 深链 ?profile=<物种> 优先于「最丰富物种」默认值：selector 每次同步都检查 URL，
    # 否则首载 filter 链路完成后的这次同步会把深链物种覆盖回默认值
    from urllib.parse import parse_qs, unquote
    req = None
    if search:
        req = parse_qs(search.lstrip("?")).get("profile", [None])[0]
        if req:
            req = unquote(req)
            if not _has_profile(req):
                req = None
    if req:
        p_default = [req]
        if req not in p_valid:
            p_opts = p_opts + [{"value": req, "label": req}]
    else:
        p_default = _pick_display_default(ordered, valid=p_valid)
    return (opts, _pick_display_default(ordered),
            p_opts, p_default,
            opts, _pick_display_default(ordered),
            opts, _pick_display_default(ordered))


@callback(
    Output("profile-content", "children"),
    Input("profile-select", "value"),
)
def load_profile_panel(names):
    if isinstance(names, str):
        names = [names]
    names = [n for n in (names or []) if n]
    if not names:
        return dmc.Text("Please select a virus species above (defaults to the most abundant in the current filter).",
                        size="sm", c="dimmed")
    out = []
    for i, name in enumerate(names):
        if i:
            out.append(dmc.Divider(label=name, labelPosition="center", my="lg"))
        try:
            out.extend(build_profile(name))
        except Exception as e:
            out.append(dmc.Alert(f"Profile failed to load ({name}): {e}", color="red", variant="light"))
    return out


def _build_vector_sankey(rels, focus_names, max_viruses=22, max_hosts=25):
    """Build 3-layer Sankey: Virus → Vector Species → Host.

    focus_names viruses = focal (red highlight, priority retention, darker links);
    others = background viruses sharing same vector species (blue).
    Truncate by record count when too many nodes; focal virus always preserved.
    """
    vv = Counter()   # (virus, vector_species)
    vh = Counter()   # (vector_species, host)
    virus_tot, host_tot = Counter(), Counter()
    for cname, r, _ in rels:
        vec = r["vector"] or "Unknown"
        host = r["host"] or "Unknown"
        vv[(cname, vec)] += 1
        vh[(vec, host)] += 1
        virus_tot[cname] += 1
        host_tot[host] += 1

    # Focal viruses prioritized; remaining slots filled by background viruses by record count
    keep_v = set(sorted((v for v in virus_tot if v in focus_names),
                        key=lambda v: -virus_tot[v])[:max_viruses])
    for v, _ in virus_tot.most_common():
        if len(keep_v) >= max_viruses:
            break
        keep_v.add(v)

    vv = {k: c for k, c in vv.items() if k[0] in keep_v}
    kept_vecs = {k[1] for k in vv}                        # keep only focal vector species
    keep_h = {h for h, _ in host_tot.most_common(max_hosts)}
    vh = {k: c for k, c in vh.items() if k[0] in kept_vecs and k[1] in keep_h}

    viruses = sorted({k[0] for k in vv})
    vectors = sorted(kept_vecs | {k[0] for k in vh})
    hosts = sorted({k[1] for k in vh})
    labels = viruses + vectors + hosts
    idx = {name: i for i, name in enumerate(labels)}
    colors = ([("#e03131" if v in focus_names else "#4c6ef5") for v in viruses]
              + ["#12b886"] * len(vectors) + ["#f59f00"] * len(hosts))

    src, tgt, val, lcolor = [], [], [], []
    for (v, vec), c in vv.items():
        src.append(idx[v]); tgt.append(idx[vec]); val.append(c)
        lcolor.append("rgba(224,49,49,0.45)" if v in focus_names else "rgba(150,150,150,0.22)")
    for (vec, h), c in vh.items():
        if vec in idx and h in idx:
            src.append(idx[vec]); tgt.append(idx[h]); val.append(c)
            lcolor.append("rgba(245,159,0,0.30)")

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=labels, color=colors, pad=11, thickness=14,
                  line=dict(color="rgba(0,0,0,0.15)", width=0.5)),
        link=dict(source=src, target=tgt, value=val, color=lcolor),
    ))
    n_focus = sum(1 for v in viruses if v in focus_names)
    n_ctx = len(viruses) - n_focus
    subtitle = f"Focal virus (red) {n_focus} · Same-vector virus (blue) {n_ctx} · Vector species {len(vectors)} · Hosts {len(hosts)}"
    if len(virus_tot) > len(viruses) or len(host_tot) > max_hosts:
        subtitle += " (truncated by record count)"
    fig.update_layout(margin=dict(l=6, r=6, t=6, b=6), font=dict(size=10),
                      title=dict(text=subtitle, font=dict(size=10, color="#888")))
    return fig



# ── 深链兼容: /explorer/?profile=<物种>（/virus/<物种> 重定向而来）──
# （原「📋 Virus Profiles (filtered)」跳转按钮已删：Virus Profile 自 2026-10-11 起为默认标签，按钮冗余）
@callback(
    Output("main-tabs", "value", allow_duplicate=True),
    Output("profile-select", "value", allow_duplicate=True),
    Input("url", "search"),
    # "initial_duplicate"：首载触发（否则 ?profile= 硬加载不生效），同时满足 allow_duplicate 的约束
    prevent_initial_call="initial_duplicate",
)
def parse_profile_deeplink(search):
    from urllib.parse import parse_qs, unquote
    if not search:
        return no_update, no_update
    sp = parse_qs(search.lstrip("?")).get("profile", [None])[0]
    if not sp:
        return no_update, no_update
    sp = unquote(sp)
    if not _has_profile(sp):
        return no_update, no_update
    return "profile", [sp]


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(debug=False, host="127.0.0.1", port=port, dev_tools_ui=False)