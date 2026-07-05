import os
import dash
from dash import dcc, html, Input, Output, State, dash_table, callback
import dash_mantine_components as dmc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import hashlib
tab = '\t'
from Bio import SeqIO

# 统一项目配置 — 查找 config.py（支持多级目录回退）
import sys
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_config_paths = [
    os.path.join(_cur_dir, "config.py"),            # 同目录
    os.path.join(_cur_dir, "..", "config.py"),      # 上级目录
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
# 1. 精密生物信息计算引擎（基于 Bio.Align.PairwiseAligner）
# -----------------------------------------------------------------------------

def create_mock_sequence(virus_name, length=800):
    """
    模拟生成代表性变异区间的植物病毒 CP 基因，保持各物种特定的高变异坐标分布
    """
    seed_val = int(hashlib.md5(virus_name.encode()).hexdigest(), 16) % 10000
    rng = np.random.default_rng(seed_val)
    
    bases = ['A', 'T', 'G', 'C']
    consensus = rng.choice(bases, size=length)
    
    var_positions = []
    if 'spotted wilt' in virus_name.lower() or 'tswv' in virus_name.lower():
        # TSWV 突变位点 (来自论文第3图结果)
        var_positions = [342, 315, 658, 732, 186, 762, 591, 376, 763, 738]
    elif 'mild mottle' in virus_name.lower() or 'pmmov' in virus_name.lower():
        # PMMoV 突变位点 (来自论文第3图结果)
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
    预置包含约 1700 条模拟真实记录的本地缓存数据库
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
                    num_records = 108 # PepYLCIV 2025 异常暴发峰值
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
    """清洗国家名：剥离子区域后缀（如 'China: Hainan' → 'China'），统一常见变体"""
    if pd.isna(raw) or str(raw).strip() == '':
        return 'Unknown'
    s = str(raw).strip()
    # 剥离冒号后的子区域
    if ':' in s:
        s = s.split(':')[0].strip()
    # 常见变体标准化
    name_map = {
        'United States': 'USA', 'United States of America': 'USA',
        'Russian Federation': 'Russia',
        'Republic of Korea': 'South Korea', 'Korea': 'South Korea',
        'Viet Nam': 'Vietnam',
        'United Kingdom of Great Britain and Northern Ireland': 'United Kingdom',
    }
    return name_map.get(s, s)


def _build_country_name_map():
    """构建 Geo_Location → Plotly ISO 标准国家名的映射表"""
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


# 表格展示上限（防止未筛选时浏览器过载）
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

    cols = ['Accession','Definition','Organism','Country','Year','Year_Collection','Year_Release','Has_Collection_Date',
            'FullSequenceLength','Sequence',
            'Category_Type','Segment_Info','Host_Name','Family','Genus','Molecule_type','Topology','Length','Completeness']
    result = df[cols]
    n_species = result['Organism'].nunique()
    country_map = _build_country_name_map()

    # Save cache
    print(f"  Full load: {len(result):,} records, {n_species:,} species in {_time.time()-t0:.1f}s. Caching...")
    with open(cache_file, 'wb') as f:
        pickle.dump({'df': result, 'df_len': len(result), 'n_species': n_species,
                     'country_map': country_map, 'top_country_n': 30}, f, protocol=4)
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
        for v, c in _country_counts.head(TOP_COUNTRY_N).items()
    ]
    DYNAMIC_COUNTRY_DEFAULTS = [v for v, _ in _country_counts.head(8).items()]
    print(f"Country map: {len(COUNTRY_NAME_MAP)} entries, Top-{TOP_COUNTRY_N} dynamic options")
except Exception as e:
    print(f"Data load failed ({e}), falling back to mock data")
    df_global = generate_baseline_dataset()
    N_SPECIES = df_global['Organism'].nunique()
    # 回退地理映射
    COUNTRY_NAME_MAP = _build_country_name_map()
    DYNAMIC_COUNTRY_OPTIONS = [
        {"value": c, "label": c} for c in sorted(df_global['Country'].unique())
    ]
    DYNAMIC_COUNTRY_DEFAULTS = ["China", "South Korea", "Indonesia", "Thailand", "Japan"]


def _build_year_marks(ymin, ymax):
    """动态生成年份刻度：跨度越大，间隔越宽，字体越小"""
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
    # 始终包含起止端点
    marks[ymin] = {"label": str(ymin), "style": {"fontSize": size, "whiteSpace": "nowrap"}}
    marks[ymax] = {"label": str(ymax), "style": {"fontSize": size, "whiteSpace": "nowrap"}}
    return marks


def align_to_reference(sequences, reference_seq):
    """
    使用现代 Bio.Align.PairwiseAligner 对输入序列进行比对，
    将其强制对齐至 reference_seq 对应坐标系上 (去除相对于参考链的插入片段，保留缺失并填充 gap)。
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
            # 获取对齐后的双链对准文本
            ref_aligned = alignment[0]
            query_aligned = alignment[1]
            
            # 将 Query 碱基对应回 Reference 碱基的位置空间中
            mapped = []
            q_idx = 0
            for r_char in ref_aligned:
                q_char = query_aligned[q_idx]
                if r_char == '-':
                    # 参考链发生 Gap 代表该位置是 Query 的插入突变，跳过以维持坐标恒定
                    q_idx += 1
                    continue
                else:
                    # 映射对准结果
                    mapped.append(q_char)
                    q_idx += 1
                    
            mapped_str = "".join(mapped)
            if len(mapped_str) < len(reference_seq):
                mapped_str = mapped_str.ljust(len(reference_seq), '-')
            elif len(mapped_str) > len(reference_seq):
                mapped_str = mapped_str[:len(reference_seq)]
            aligned_queries.append(mapped_str)
        except Exception as e:
            # 异常时进行基础填充
            aligned_queries.append(seq[:len(reference_seq)].ljust(len(reference_seq), '-'))
            
    return aligned_queries

def compute_alignment_matrices(sequences):
    """
    通过对齐后的等长序列列表计算碱基概率频率矩阵及局部突变变异率
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
    
    # 变异率 = 1 - 最大碱基概率 (在完全保守位置该值为 0，完全分散位置接近 0.75)
    variation_rates = 1.0 - frequency_matrix.max(axis=0)
    return frequency_matrix, variation_rates

# -----------------------------------------------------------------------------
# 2. 增强型系统 UI 布局设计
# -----------------------------------------------------------------------------

DASH_PREFIX = os.environ.get("DASH_URL_PREFIX", "/")
app = dash.Dash(__name__, update_title=None,
    requests_pathname_prefix=DASH_PREFIX,
    routes_pathname_prefix=DASH_PREFIX,
    external_stylesheets=[
    "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
])
app._favicon = None
server = app.server
app.title = "Plant Virus Explorer"

app.index_string = '''<!DOCTYPE html>
<html>
<head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
#ai-chat-btn{position:fixed;bottom:24px;right:24px;width:48px;height:48px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:50%;font-size:20px;cursor:pointer;z-index:9999;box-shadow:0 4px 12px rgba(102,126,234,.4);transition:transform .2s}
#ai-chat-btn:hover{transform:scale(1.1)}
#ai-chat-panel{position:fixed;bottom:84px;right:24px;width:400px;max-height:520px;background:#fff;border:1px solid #dee2e6;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.15);z-index:9998;display:none;flex-direction:column;font-family:Inter,sans-serif}
.chat-header{display:flex;justify-content:space-between;align-items:center;padding:10px 16px;border-bottom:1px solid #eee;border-radius:12px 12px 0 0;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;font-weight:600;font-size:14px}
.chat-header button{background:none;border:none;color:#fff;font-size:18px;cursor:pointer}
.chat-msgs{flex:1;overflow-y:auto;padding:10px;max-height:360px}
.chat-msg{margin:4px 0;padding:8px 12px;border-radius:10px;font-size:13px;line-height:1.5;max-width:85%;word-break:break-word}
.chat-msg.user{background:#667eea;color:#fff;margin-left:auto}
.chat-msg.ai{background:#f0f0f5;color:#333}
.chat-msg.system{background:#fff3cd;color:#856404;text-align:center;max-width:100%;font-size:11px}
.chat-input-row{display:flex;gap:8px;padding:10px 12px;border-top:1px solid #eee}
.chat-input-row input{flex:1;padding:8px 12px;border:1px solid #dee2e6;border-radius:20px;font-size:13px;outline:none}
.chat-input-row button{padding:6px 16px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:20px;font-size:13px;cursor:pointer}
.ai-typing{display:flex;gap:4px;padding:8px 12px}
.ai-typing span{width:6px;height:6px;background:#999;border-radius:50%;animation:aiBounce 1.4s infinite ease-in-out}
.ai-typing span:nth-child(2){animation-delay:.2s}.ai-typing span:nth-child(3){animation-delay:.4s}
@keyframes aiBounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}
.preset-qs{display:flex;flex-wrap:wrap;gap:4px;padding:6px 10px;border-bottom:1px solid #eee;background:#fafafa}
.preset-q{background:#fff;border:1px solid #dee2e6;border-radius:14px;padding:3px 10px;font-size:11px;cursor:pointer;color:#555;white-space:nowrap;max-width:180px;overflow:hidden;text-overflow:ellipsis;transition:all .2s}
.preset-q:hover{background:#667eea;color:#fff;border-color:#667eea}
</style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer>
<button id="ai-chat-btn" onclick="toggleChat()" title="AI助手">?</button>
<div id="ai-chat-panel">
<div class="chat-header"><span>Explorer AI助手</span><div><button onclick="toggleSettings()" style="background:none;border:none;color:#fff;font-size:14px;cursor:pointer;margin-right:8px" title="设置">⚙</button><button onclick="toggleChat()">×</button></div></div>
<div id="ai-settings-inline" style="display:none;padding:10px 12px;border-bottom:1px solid #eee;background:#f8f9fa">
<div style="display:flex;gap:6px;flex-wrap:wrap">
<input id="ai-api-key" type="password" placeholder="API Key (sk-...)" style="flex:1;min-width:120px;padding:5px 8px;border:1px solid #dee2e6;border-radius:4px;font-size:11px">
<input id="ai-model" value="deepseek-chat" style="width:120px;padding:5px 8px;border:1px solid #dee2e6;border-radius:4px;font-size:11px">
<button onclick="saveAISettings()" style="padding:5px 10px;background:#667eea;color:#fff;border:none;border-radius:4px;font-size:11px;cursor:pointer">保存</button>
</div></div>
<div class="preset-qs"><button class="preset-q" onclick="askPreset('这个探索器有哪些功能？怎么使用？')">探索器功能介绍</button><button class="preset-q" onclick="askPreset('CP基因变异分析图怎么看？')">CP变异分析解读</button><button class="preset-q" onclick="askPreset('植物病毒在全球的分布有什么特点？')">全球分布特点</button><button class="preset-q" onclick="askPreset('如何筛选特定国家的病毒数据？')">数据筛选方法</button></div>
<div class="chat-msgs" id="chat-msgs"><div class="chat-msg system">你好！我是Explorer AI助手。可以直接点下方预设问题，或输入你的问题。</div></div>
<div class="chat-input-row"><input id="chat-input" placeholder="输入问题..." onkeydown="if(event.key==='Enter')sendMsg()"><button onclick="sendMsg()">发送</button></div></div>
<script>
var chatConv=[],chatOpen=false;
function askPreset(q){document.getElementById("chat-input").value=q;sendMsg()}
function toggleChat(){chatOpen=!chatOpen;document.getElementById("ai-chat-panel").style.display=chatOpen?"flex":"none"}
function toggleSettings(){var p=document.getElementById("ai-settings-inline");p.style.display=p.style.display==="none"?"block":"none"}
function saveAISettings(){localStorage.setItem("ai_api_key",document.getElementById("ai-api-key").value);localStorage.setItem("ai_model",document.getElementById("ai-model").value);document.getElementById("ai-settings-inline").style.display="none";addChatMsg("system","设置已保存")}
(function(){var k=localStorage.getItem("ai_api_key");if(k)document.getElementById("ai-api-key").value=k;var m=localStorage.getItem("ai_model");if(m)document.getElementById("ai-model").value=m})();
function addChatMsg(role,text){var d=document.createElement("div");d.className="chat-msg "+role;d.textContent=text;document.getElementById("chat-msgs").appendChild(d);document.getElementById("chat-msgs").scrollTop=document.getElementById("chat-msgs").scrollHeight}
function showTyping(){var d=document.createElement("div");d.className="ai-typing";d.id="typing-indicator";d.innerHTML="<span></span><span></span><span></span>";document.getElementById("chat-msgs").appendChild(d)}
function hideTyping(){var t=document.getElementById("typing-indicator");if(t)t.remove()}
async function sendMsg(){var inp=document.getElementById("chat-input");var msg=inp.value.trim();if(!msg)return;addChatMsg("user",msg);inp.value="";chatConv.push({role:"user",content:msg});var key=localStorage.getItem("ai_api_key")||"";showTyping();try{var resp=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg,api_key:key,api_url:"https://api.deepseek.com/v1/chat/completions",model:localStorage.getItem("ai_model")||"deepseek-chat",conversation:chatConv.slice(-8),context:"explorer"})});var data=await resp.json();hideTyping();addChatMsg("ai",data.reply);chatConv.push({role:"assistant",content:data.reply})}catch(e){hideTyping();addChatMsg("system","请求失败: "+e.message)}}
</script>
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
    """返回 [query, ICTV名, 通用名, 缩写]"""
    result = {query.lower()}
    m = NAME_MAP_CACHE.get(query.lower(), {})
    for k in ('ICTV_Name', 'Common_Name', 'Abbreviation'):
        v = m.get(k, '').strip()
        if v: result.add(v.lower())
    return result

app.layout = dmc.MantineProvider(
    theme={
        "fontFamily": "Inter, sans-serif",
        "primaryColor": "blue",
    },
    children=dmc.AppShell(
        header={"height": 52},
        padding="md",
        children=[
            dcc.Location(id="url", refresh=False),

            # 顶部学术风格导航栏
            dmc.AppShellHeader(
                px="md",
                style={"background": "#1a5276"},
                children=dmc.Group(
                    justify="space-between",
                    h="100%",
                    children=[
                        dmc.Group(gap="xs", children=[
                            dmc.Text("Plant Virus DB", fw=700, size="md", c="white"),
                            html.A("Reference DB", href="/reference/",
                                   style={"color":"rgba(255,255,255,0.8)","fontSize":"14px","textDecoration":"none","marginLeft":"8px"}),
                            html.A("Primers", href="/primers/",
                                   style={"color":"rgba(255,255,255,0.8)","fontSize":"14px","textDecoration":"none","marginLeft":"8px"})
                        ]),
                        dmc.Group(gap="xs", children=[
                            dmc.Badge(str(N_SPECIES) + " species", color="gray", variant="filled"),
                            dmc.Badge(str(len(df_global)) + " sequences", color="blue", variant="filled"),
                            dmc.Badge(DATA_VERSION.split(" | ")[0] if " | " in DATA_VERSION else DATA_VERSION, color="green", variant="light")
                        ])
                    ]
                )
            ),
            # 看板分析主体
            dmc.AppShellMain(
                children=dmc.Grid(
                    gutter="md",
                    children=[
                        # 左边栏：高级控制面板
                        dmc.GridCol(
                            span={"base": 12, "md": 3},
                            children=dmc.Paper(
                                withBorder=True,
                                shadow="sm",
                                p="md",
                                radius="md",
                                children=[
                                    dmc.Title("检索与多序列比对控制", order=4, mb="md", style={"color": "#2c2e33"}),
                                    
                                    dmc.MultiSelect(
                                        id="host-filter",
                                        label="检索宿主种类 (Top 80)",
                                        placeholder="全部宿主 → 可搜索",
                                        data=sorted(
                                            [{"value": v, "label": v}
                                             for v in df_global['Host_Name'].value_counts().head(80).index
                                             if v != 'Unknown'],
                                            key=lambda x: x['label']
                                        ),
                                        searchable=True,
                                        clearable=True,
                                        mb="md"
                                    ),

                                    dmc.MultiSelect(
                                        id="country-select",
                                        label=f"分析目标国家/地区 (Top {TOP_COUNTRY_N})",
                                        placeholder="选择目标地区 → 可搜索",
                                        data=DYNAMIC_COUNTRY_OPTIONS,
                                        value=DYNAMIC_COUNTRY_DEFAULTS,
                                        searchable=True,
                                        clearable=True,
                                        mb="md"
                                    ),

                                    dmc.MultiSelect(
                                        id="category-filter",
                                        label="基因组结构 (分段 / 非分段)",
                                        placeholder="全部类型",
                                        data=[{"value": "Segmented", "label": "Segmented (分段)"},
                                              {"value": "NonSegmented", "label": "Non‑Segmented (非分段)"}],
                                        value=["Segmented", "NonSegmented"],
                                        mb="md"
                                    ),

                                    dmc.MultiSelect(
                                        id="family-filter",
                                        label="病毒科 (Family)",
                                        placeholder="全部科 → 可选",
                                        data=sorted(
                                            [{"value": v, "label": v}
                                             for v in df_global['Family'].unique() if v != 'Unknown'],
                                            key=lambda x: x['label']
                                        ),
                                        searchable=True,
                                        clearable=True,
                                        mb="md"
                                    ),

                                    dmc.MultiSelect(
                                        id="completeness-filter",
                                        label="序列完整性",
                                        placeholder="全部",
                                        data=[
                                            {"value": "complete", "label": "Complete (完整)"},
                                            {"value": "partial", "label": "Partial (部分)"}
                                        ],
                                        value=["complete", "partial"],
                                        mb="md"
                                    ),

                                    dmc.MultiSelect(
                                        id="virus-filter",
                                        label="目标病毒物种",
                                        placeholder="全部物种 → 可搜索",
                                        data=[{"value": "Potato spindle tuber viroid", "label": "Potato spindle tuber viroid (PSTVd)"}],
                                        value=["Potato spindle tuber viroid"],
                                        searchable=True,
                                        clearable=True,
                                        mb="md"
                                    ),

                                    dmc.Text("数据报告年度跨度", size="sm", style={"fontWeight": 600}, mb="xs"),
                                    dmc.Text("拖动两端滑块选择起止年份", size="xs", c="dimmed", mb="md"),
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
                                    
                                    dmc.Text("年份数据源", size="sm", style={"fontWeight": 600}, mb="xs"),
                                    dmc.SegmentedControl(
                                        id="year-source",
                                        value="auto",
                                        data=[
                                            {"value": "auto", "label": "自动 (采集>提交)"},
                                            {"value": "collection", "label": "仅采集年"},
                                            {"value": "release", "label": "仅提交年"}
                                        ],
                                        fullWidth=True,
                                        mb="md"
                                    ),

                                    dmc.Switch(
                                        id="filter-na",
                                        label="过滤无采集日期记录 (NA)",
                                        checked=False,
                                        mb="md"
                                    ),

                                    dmc.Divider(my="md"),

                                    dmc.Button(
                                        "重算数据流并生成图表",
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
                        
                        # 右半部分：深度学术可视化分析
                        dmc.GridCol(
                            span={"base": 12, "md": 9},
                            children=dmc.Paper(
                                withBorder=True,
                                shadow="sm",
                                p="md",
                                radius="md",
                                children=[
                                    dmc.Tabs(
                                        value="trends",
                                        children=[
                                            dmc.TabsList(
                                                mb="md",
                                                children=[
                                                    dmc.TabsTab("时空演变趋势图", value="trends", leftSection="📊"),
                                                    dmc.TabsTab("全基因组变异分析", value="mutation", leftSection="🧬"),
                                                    dmc.TabsTab("高稳健序列数据库", value="table", leftSection="📋"),
                                                    dmc.TabsTab("引物数据库", value="primers", leftSection="🧪"),
                                                    dmc.TabsTab("宿主范围", value="host", leftSection="🌿")
                                                ]
                                            ),
                                            
                                            # 时空演变面板
                                            dmc.TabsPanel(
                                                value="trends",
                                                children=[
                                                    dmc.Group(
                                                        justify="space-between",
                                                        mb="md",
                                                        children=[
                                                            dmc.Title("时空与地理分布分析", order=3),
                                                            dmc.Badge("Stacked + Map", color="gray")
                                                        ]
                                                    ),
                                                    dcc.Loading(
                                                        type="cube", color="#12b886",
                                                        children=[
                                                            dmc.Title("① 病毒随时间变化 (折线图)", order=4, mb="xs"),
                                                            dmc.Text("横轴=年份，纵轴=序列数，颜色=病毒物种，圆点=数据年", size="xs", c="dimmed", mb="xs"),
                                                            dcc.Graph(id="chart-time-stacked", style={"height": "350px"}),
                                                            dmc.Space(h="md"),
                                                            dmc.Title("② 病毒在不同国家的分布 (水平条形图)", order=4, mb="xs"),
                                                            dmc.Text("纵轴=国家，横轴=序列数，颜色=病毒物种，'未标注'=缺地理信息", size="xs", c="dimmed", mb="xs"),
                                                            dcc.Graph(id="chart-country-stacked", style={"height": "350px"}),
                                                            dmc.Space(h="md"),
                                                            dmc.Title("③ 地理映射 (底色=总量 | 圆点颜色/大小=病毒组成与数量)", order=4, mb="xs"),
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
                                                                                dmc.Text("筛选序列 (Accession)", size="xs", c="dimmed"),
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
                                                                                dmc.Text("独立物种 (Species)", size="xs", c="dimmed"),
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
                                                                                dmc.Text("最高占比病毒类别", size="xs", c="dimmed"),
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
                                                                                dmc.Text("贡献最活跃源地", size="xs", c="dimmed"),
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
                                            
                                            # 全基因组比对与变异分析
                                            dmc.TabsPanel(
                                                value="mutation",
                                                children=[
                                                    dmc.Group(
                                                        justify="space-between",
                                                        mb="md",
                                                        children=[
                                                            dmc.Title("全基因组比对矩阵与变异率曲线", order=3),
                                                            dmc.Select(
                                                                id="mutation-virus-select",
                                                                label="多序列比对目标物种选择",
                                                                data=[],
                                                                value="",
                                                                style={"width": 380}
                                                            )
                                                        ]
                                                    ),
                                                    dmc.Text(
                                                        "基于真实 GenBank 全基因组序列，通过全局双序列比对（Global Pairwise Alignment）"
                                                        "将同物种内多条序列映射至参考链坐标系，逐位点计算 A/T/G/C 碱基频率与多态性变异率。"
                                                        "展示长度上限 5,000 bp，比对序列上限 100 条以保证交互流畅度。",
                                                        size="sm",
                                                        c="dimmed",
                                                        mb="lg"
                                                    ),
                                                    dcc.Loading(
                                                        type="cube", color="#12b886",
                                                        children=[
                                                            dmc.Title("单碱基坐标位点丰度映射 (A/T/G/C 分布热图)", order=5, mb="xs"),
                                                            dcc.Graph(id="alignment-heatmap", style={"height": "320px"}),
                                                            dmc.Space(h="md"),
                                                            dmc.Title("核苷酸位点突变变异率与 Top 10 热点图例", order=5, mb="xs"),
                                                            dcc.Graph(id="variation-line-chart", style={"height": "350px"})
                                                        ]
                                                    )
                                                ]
                                            ),
                                            
                                            # 数据详情
                                            dmc.TabsPanel(
                                                value="table",
                                                children=[
                                                    dmc.Group(
                                                        justify="space-between",
                                                        mb="md",
                                                        children=[
                                                            dmc.Title("SeqIO 处理数据集归档", order=3),
                                                            dmc.Button("导出 CSV 时空表格", id="export-btn", size="xs", color="teal", variant="light")
                                                        ]
                                                    ),
                                                    dcc.Download(id="download-dataframe-csv"),
                                                    dash_table.DataTable(
                                                        id='records-table',
                                                        columns=[
                                                            {"name": "Accession 注册号", "id": "Accession"},
                                                            {"name": "病毒类型 (Organism)", "id": "Organism"},
                                                            {"name": "来源国家 (Country)", "id": "Country"},
                                                            {"name": "发布年份", "id": "Year"},
                                                            {"name": "基因完整描述 (Definition)", "id": "Definition"}
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
                                                        }
                                                    )
                                                ]
                                            ),
                                            
                                            # 引物数据库
                                            dmc.TabsPanel(
                                                value="primers",
                                                id="primers-panel",
                                                children=[
                                                    dmc.Title("病毒引物设计结果", order=3, mb="md"),
                                                    dmc.Text(
                                                        "引物数据由 引物设计/ 流水线生成。同步 primer_reference.tsv 到 docs/data/primers/ 后自动展示。",
                                                        size="sm", c="dimmed", mb="md"
                                                    ),
                                                    html.Div(id="primers-content", children=[
                                                        dmc.Text("加载引物数据中...", size="sm", c="dimmed")
                                                    ])
                                                ]
                                            ),

                                            # 宿主范围
                                            dmc.TabsPanel(
                                                value="host",
                                                id="host-panel",
                                                children=[
                                                    dmc.Title("病毒宿主范围分析", order=3, mb="md"),
                                                    html.Div(id="host-content", children=[
                                                        dmc.Text("加载宿主数据中...", size="sm", c="dimmed")
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
# 3. Web 回调管理 (Callbacks)
# -----------------------------------------------------------------------------

@callback(
    [Output("host-filter", "value"),
     Output("country-select", "value"),
     Output("category-filter", "value"),
     Output("family-filter", "value"),
     Output("year-slider", "value")],
    Input("url", "search")
)
def parse_url_params(search):
    """从 URL 查询参数预填充筛选器"""
    from urllib.parse import parse_qs
    defaults = [None, [], ["Segmented", "NonSegmented"], [], [int(df_global["Year"].min()), int(df_global["Year"].max())]]
    if not search:
        return defaults
    params = parse_qs(search.lstrip("?"))
    host = params.get("host", [None])[0] or None
    country = params.get("country", [""])[0]
    country_vals = [c.strip() for c in country.split(",") if c.strip()] if country else []
    category = params.get("category", [""])[0]
    cat_vals = [c.strip() for c in category.split(",") if c.strip()] if category else ["Segmented", "NonSegmented"]
    family = params.get("family", [""])[0]
    fam_vals = [f.strip() for f in family.split(",") if f.strip()] if family else []
    ymin = int(params.get("year_min", [str(int(df_global["Year"].min()))])[0])
    ymax = int(params.get("year_max", [str(int(df_global["Year"].max()))])[0])
    return host, country_vals or None, cat_vals, fam_vals or None, [ymin, ymax]

@callback(
    [Output("virus-filter", "data"),
     Output("virus-filter", "value")],
    [Input("family-filter", "value"),
     Input("category-filter", "value")]
)
def update_virus_options(selected_families, selected_categories):
    df = df_global.copy()
    if 'Category_Type' in df.columns and selected_categories:
        df = df[df['Category_Type'].isin(selected_categories)]
    if 'Family' in df.columns and selected_families:
        df = df[df['Family'].isin(selected_families)]

    virus_list = sorted(df['Organism'].unique())
    options = [{"value": v, "label": v} for v in virus_list]
    # 首次加载时默认选中 PSTVd
    default_val = ["Potato spindle tuber viroid"] if "Potato spindle tuber viroid" in virus_list else []
    return options, default_val


@callback(
    [Output("records-table", "data"),
     Output("mutation-virus-select", "data"),
     Output("mutation-virus-select", "value"),
     Output("stat-total-seqs", "children"),
     Output("stat-n-species", "children"),
     Output("stat-common-virus", "children"),
     Output("stat-top-country", "children")],
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


    # 过滤无采集日期的记录 (NA filter)
    if filter_na:
        df = df[df['Has_Collection_Date'] == True]

    # 根据年份数据源重新计算 Year
    if year_source == 'collection':
        df = df[df['Year_Collection'].notna()]
        df['Year'] = df['Year_Collection'].astype(int)
    elif year_source == 'release':
        df = df[df['Year_Release'].notna()]
        df['Year'] = df['Year_Release'].astype(int)
    # auto: 保持默认 Year（采集优先，缺失回退提交）

    # Host 过滤
    if 'Host_Name' in df.columns and host:
        df = df[df['Host_Name'].isin(host)]
    # Category 过滤 (分段/非分段)
    if 'Category_Type' in df.columns and selected_categories:
        df = df[df['Category_Type'].isin(selected_categories)]
    # Family 过滤
    if 'Family' in df.columns and selected_families:
        df = df[df['Family'].isin(selected_families)]
    # Completeness 过滤
    if 'Completeness' in df.columns and selected_completeness:
        df = df[df['Completeness'].isin(selected_completeness)]

    # Virus 过滤 (空 = 全部)
    if selected_viruses:
        df = df[df['Organism'].isin(selected_viruses)]
        # 选定了具体病毒时，跳过国家过滤（避免因缺省国家设置导致所有记录被过滤）
        skip_country_filter = True
    else:
        skip_country_filter = False

    # Country 过滤 (空 = 全部；选定了病毒则跳过)
    if selected_countries and not skip_country_filter:
        df = df[df['Country'].isin(selected_countries)]

    df_filtered = df[
        (df['Year'] >= year_range[0]) &
        (df['Year'] <= year_range[1])
    ]

    if df_filtered.empty:
        return [], [], "", "0", "0", "无有效记录", "无"

    total_seqs = f"{len(df_filtered):,}"
    n_species = f"{df_filtered['Organism'].nunique():,}"
    common_virus = df_filtered['Organism'].mode()[0] if not df_filtered.empty else "N/A"
    top_country = df_filtered['Country'].mode()[0] if not df_filtered.empty else "N/A"

    virus_options = [{"value": v, "label": v} for v in df_filtered['Organism'].unique()]
    default_virus = df_filtered['Organism'].unique()[0] if len(virus_options) > 0 else ""

    table_data = df_filtered.drop(columns=['Sequence'], errors='ignore').to_dict('records')
    # 表格展示上限：防止未筛选时浏览器处理 19 万条记录
    if len(table_data) > TABLE_MAX_ROWS:
        table_data = table_data[:TABLE_MAX_ROWS]
    return table_data, virus_options, default_virus, total_seqs, n_species, common_virus, top_country

@callback(
    [Output("chart-time-stacked", "figure"),
     Output("chart-country-stacked", "figure"),
     Output("geo-map", "figure")],
    [Input("records-table", "data")]
)
def render_spatiotemporal_chart(table_data):
    if not table_data:
        return go.Figure(), go.Figure(), go.Figure()

    df = pd.DataFrame(table_data)

    try:
        # ① 病毒随时间变化 — 折线图 + 散点标记
        time_df = df.groupby(['Year', 'Organism']).size().reset_index(name='Count')
        fig_time = px.line(
            time_df, x='Year', y='Count', color='Organism',
            markers=True,
            labels={'Count': '序列数', 'Year': '年份'},
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

        # ② 病毒在不同国家的分布 — 水平条形图（含 Unknown 标注）
        country_df = df.groupby(['Country', 'Organism']).size().reset_index(name='Count')
        # 把 Unknown 重命名为 "未标注" 使其在图表中可读
        country_df['Country'] = country_df['Country'].replace('Unknown', '未标注')
        country_order = country_df.groupby('Country')['Count'].sum().sort_values(ascending=True).index.tolist()
        fig_country = px.bar(
            country_df, y='Country', x='Count', color='Organism',
            orientation='h',
            category_orders={'Country': country_order},
            labels={'Count': '序列数', 'Country': '国家'},
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

        # ③ 地理映射 — choropleth + scatter
        geo_detail = df.groupby(['Country', 'Organism']).size().reset_index(name='Count')
        geo_detail = geo_detail[geo_detail['Country'] != 'Unknown']
        geo_detail['Country_ISO'] = geo_detail['Country'].map(COUNTRY_NAME_MAP).fillna(geo_detail['Country'])
        country_total = geo_detail.groupby('Country_ISO')['Count'].sum().reset_index(name='Total')

        all_viruses = sorted(df['Organism'].unique())
        color_palette = px.colors.qualitative.G10 + px.colors.qualitative.Set3
        virus_colors = {v: color_palette[i % len(color_palette)] for i, v in enumerate(all_viruses)}

        fig_map = go.Figure()
        fig_map.add_trace(go.Choropleth(
            locations=country_total['Country_ISO'], locationmode='country names',
            z=country_total['Total'], colorscale='OrRd',
            colorbar=dict(title='报告总数', thickness=15, len=0.55, x=0.87),
            marker_line_color='white', marker_line_width=0.5,
            hovertemplate='%{location}: %{z} 条序列<extra></extra>',
            name='总量 (底色)'
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
                title=dict(text='<b>病毒物种</b>', font=dict(size=11)),
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

# 基因组比对可视化参数
MAX_ALIGN_SEQS = 100       # 最多比对序列数
MAX_DISPLAY_BP = 5000      # 热图 / 变异曲线最大展示碱基数

@callback(
    [Output("alignment-heatmap", "figure"),
     Output("variation-line-chart", "figure")],
    [Input("records-table", "data"),
     Input("mutation-virus-select", "value")]
)
def render_genomic_plots(table_data, selected_virus):
    if not table_data or not selected_virus:
        return go.Figure(), go.Figure()
        
    df_table = pd.DataFrame(table_data)
    df_virus_accs = set(df_table[df_table['Organism'] == selected_virus]['Accession'].tolist())

    # 从 df_global 按 Accession 取真实序列，避免在 table_data 中传递大量序列数据
    df_seq = df_global[df_global['Accession'].isin(df_virus_accs)]
    sequences = df_seq['Sequence'].tolist()
    sequences = [seq for seq in sequences if seq and len(seq) > 0]
    
    if len(sequences) == 0:
        return go.Figure(), go.Figure()

    # 限制比对序列数以保证渲染性能
    if len(sequences) > MAX_ALIGN_SEQS:
        sequences = sequences[:MAX_ALIGN_SEQS]

    # 指定第一个分子序列作为坐标空间参考链，调用 Bio.Align 坐标映射
    reference = sequences[0]
    aligned_seqs = align_to_reference(sequences, reference)
    
    # 频率与变异信息熵计算
    freq_matrix, variation_rates = compute_alignment_matrices(aligned_seqs)
    
    # 动态坐标范围：展示实际参考链长度，但截断至 MAX_DISPLAY_BP
    ref_len = len(reference)
    display_len = min(ref_len, MAX_DISPLAY_BP)
    positions = list(range(1, display_len + 1))
    
    # 截取展示区间的矩阵与变异率
    freq_display = freq_matrix[:, :display_len]
    var_display = variation_rates[:display_len]
    
    # 1. 碱基丰度热图 (Plasma 配色能够准确区分单一基质与杂合位点)
    nucleotides = ['A', 'T', 'G', 'C']
    x_label = f"对齐参考坐标 (nt, 共 {ref_len} bp)" if ref_len <= MAX_DISPLAY_BP else f"对齐参考坐标 (前 {MAX_DISPLAY_BP} / {ref_len} bp)"
    fig_heatmap = px.imshow(
        freq_display,
        y=nucleotides,
        x=positions,
        color_continuous_scale="Plasma",
        labels=dict(x=x_label, y="碱基分类", color="频率分布"),
        aspect="auto"
    )
    fig_heatmap.update_layout(
        coloraxis_showscale=True,
        margin=dict(l=45, r=20, t=15, b=40),
        height=280,
        font=dict(family="Inter, sans-serif", size=10)
    )
    
    # 2. 突变演变曲线与 Top 10 热点标注
    sorted_indices = np.argsort(var_display)[::-1]
    top_n = min(10, len(sorted_indices))
    top_pos = sorted_indices[:top_n]
    top_rates = var_display[top_pos]
    
    fig_line = go.Figure()
    
    fig_line.add_trace(go.Scatter(
        x=positions,
        y=var_display,
        mode='lines',
        name='多态性变异率',
        line=dict(color='#a01a1a', width=1.5)
    ))
    
    fig_line.add_trace(go.Scatter(
        x=top_pos + 1,
        y=top_rates,
        mode='markers',
        name=f'关键热点 (Top {top_n})',
        marker=dict(color='#fd7e14', size=8, symbol='triangle-down', line=dict(color='black', width=1))
    ))
    
    # 向图表区域插入高精度定位箭头
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
    
    info_text = f"{selected_virus[:40]}  |  {len(aligned_seqs)} 条序列比对  |  参考链 {ref_len} bp"
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
    Output("download-dataframe-csv", "data"),
    Input("export-btn", "n_clicks"),
    State("records-table", "data"),
    prevent_initial_call=True
)
def export_table_csv(n_clicks, table_data):
    if not table_data:
        return None
    df = pd.DataFrame(table_data)
    if 'Sequence' in df.columns:
        df = df.drop(columns=['Sequence'])
    return dcc.send_data_frame(df.to_csv, "plantvirus_alignment_metadata.csv", index=False)


# ── 引物数据库面板 ──────────────────────────────────────
@callback(
    Output("primers-content", "children"),
    Input("mutation-virus-select", "value"),
)
def load_primers_panel(selected_virus):
    import config
    primer_path = config.PRIMER_OUTPUTS.get("reference_tsv", "")
    if not primer_path or not os.path.exists(primer_path):
        return dmc.Alert("引物数据尚未同步。", color="yellow", variant="light", mb="md")
    try:
        if selected_virus:
            search_terms = _lookup_names(selected_virus)
            matched = []
            with open(primer_path, encoding='utf-8') as f:
                for row in csv.DictReader(f, delimiter='\t'):
                    if any(t in str(row.values()).lower() for t in search_terms):
                        matched.append(row)
            if not matched:
                return dmc.Text(f"未找到 {selected_virus} 的引物记录（已检索全部）", c="dimmed")
            primer_df = pd.DataFrame(matched)
        else:
            primer_df = pd.read_csv(primer_path, sep='\t', nrows=500)

        from urllib.parse import quote
        ictv_name = primer_df.iloc[0].get('Species', selected_virus or '')
        embed_url = f"/species/{quote(ictv_name)}" if ictv_name else None
        return [
            dmc.Text(f"共 {len(primer_df)} 条引物 — {ictv_name}" if selected_virus else f"引物数据表（前500条）", fw=600, mb="sm"),
            dash_table.DataTable(
                data=primer_df.head(100).to_dict('records'),
                columns=[{"name": c, "id": c} for c in primer_df.columns],
                page_size=10,
                style_table={'overflowX': 'auto'},
                style_cell={'fontSize': '12px', 'padding': '6px'},
                style_header={'backgroundColor': '#f1f3f5', 'fontWeight': 'bold'}
            ),
            dmc.Anchor("查看完整引物详情页 →", href=embed_url, target="_blank", size="sm", c="blue", mt="md") if selected_virus else None
        ]
    except Exception as e:
        return dmc.Alert(f"引物数据加载失败: {e}", color="red", variant="light")


# ── 宿主范围面板 ────────────────────────────────────────
@callback(
    Output("host-content", "children"),
    Input("mutation-virus-select", "value"),
)
def load_host_panel(selected_virus):
    import config
    data_dir = os.path.dirname(config.PIPELINE_OUTPUTS.get("full_tsv", ""))
    host_range_path = os.path.join(data_dir, "host_analysis", "virus_host_range.tsv")
    host_summary_path = os.path.join(data_dir, "host_analysis", "virus_host_range_summary.tsv")
    host_freq_path = os.path.join(data_dir, "host_analysis", "host_frequency.tsv")
    if not os.path.exists(host_summary_path):
        return dmc.Alert("宿主数据尚未同步。", color="yellow", variant="light", mb="md")
    try:
        if selected_virus:
            search_terms = _lookup_names(selected_virus)
            matched = []
            if os.path.exists(host_range_path):
                with open(host_range_path, encoding='utf-8') as f:
                    for row in csv.DictReader(f, delimiter='\t'):
                        if any(t in row.get('Species','').lower() for t in search_terms):
                            matched.append(row)
            if not matched:
                return dmc.Text(f"未找到 {selected_virus} 的宿主记录", c="dimmed")
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
                dmc.Text(f"宿主属分布 ({len(genera_sorted)} 属，{total_spp} 物种)", fw=600, mb="xs", mt="md"),
                dash_table.DataTable(data=genus_rows,
                    columns=[{"name": "Host Genus", "id": "Host Genus"}, {"name": "Records", "id": "Records"}, {"name": "Host Species", "id": "Host Species"}],
                    page_size=20, style_table={'overflowX': 'auto'},
                    style_cell={'fontSize':'12px','padding':'6px','whiteSpace':'normal','height':'auto'},
                    style_header={'backgroundColor':'#f1f3f5','fontWeight':'bold'}
                )]
        else:
            hdf = pd.read_csv(host_summary_path, sep='\t')
            # Quick stats
            stats = ""
            if os.path.exists(host_freq_path):
                ff = pd.read_csv(host_freq_path, sep='\t', nrows=3)
                stats = f"Top hosts: {ff.iloc[0]['Host']} ({ff.iloc[0]['Count']}), {ff.iloc[1]['Host']} ({ff.iloc[1]['Count']})"
            return [
                dmc.Text(stats, size="sm", c="dimmed", mb="sm") if stats else None,
                dmc.Text(f"按科汇总的宿主范围 ({len(hdf)} 个科)", fw=600, mb="xs"),
                dash_table.DataTable(data=hdf.head(30).to_dict('records'),
                    columns=[{"name": c, "id": c} for c in hdf.columns],
                    page_size=15, style_table={'overflowX': 'auto'},
                    style_cell={'fontSize':'12px','padding':'6px','maxWidth':'350px','overflow':'hidden','textOverflow':'ellipsis'},
                    style_header={'backgroundColor':'#f1f3f5','fontWeight':'bold'})
            ]
    except Exception as e:
        return dmc.Alert(f"宿主数据加载失败: {e}", color="red", variant="light")


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8888))
    app.run(debug=False, host="127.0.0.1", port=port, dev_tools_ui=False)