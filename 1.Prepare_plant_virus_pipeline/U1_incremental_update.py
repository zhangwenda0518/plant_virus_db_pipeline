#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
U1: PlantVirusDB 增量更新引擎 (v2)
====================================
解决三个核心问题:

  1. 病毒数据获取 — PDAT + MDAT 双日期覆盖 + 分类树变动检测
  2. 植物病毒分离 — 五层漏斗: 已知TaxID → NCBI宿主lineage → 祖先分类 → ICTV → 关键词
  3. 新分类病毒更新 — taxdump差分 → 新viral taxid检测 → 祖先判定 → merged/deleted处理

架构:
  ┌─────────────────────────────────────────────────────┐
  │  Phase 0: NCBI Taxonomy 同步                        │
  │    taxdump.tar.gz → 差分 → merged/delnodes/新taxid  │
  └──────────────────────┬──────────────────────────────┘
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │  Phase 1: 序列增量获取 (PDAT + MDAT)                 │
  │    esearch → accession list → efetch GenBank        │
  └──────────────────────┬──────────────────────────────┘
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │  Phase 2: 五层植物病毒判定                          │
  │    L1: 已知植物病毒 TaxID                           │
  │    L2: /host 物种 → NCBI Taxonomy lineage 查植物    │
  │    L3: 病毒 TaxID → 祖先是否已知植物病毒科/属        │
  │    L4: ICTV VMR Host source 对照                    │
  │    L5: 病毒名/定义 植物关键词 (兜底)                 │
  └──────────────────────┬──────────────────────────────┘
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │  Phase 3: 数据库合并                                │
  │    FASTA + TSV 追加 → merged 更新 → delnodes 标记   │
  │    → 新 taxid 补 lineage → watchlist 输出           │
  └─────────────────────────────────────────────────────┘
"""

import os
import sys
import json
import time
import hashlib
import gzip
import re
import argparse
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from http.client import IncompleteRead
import xml.etree.ElementTree as ET

import polars as pl

# ── 项目路径 ────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from config import DATA_DIR, PIPELINE_OUTPUTS, VERSION_FILE

# ── 常量 ─────────────────────────────────────────────────
STATE_FILE      = os.path.join(DATA_DIR, ".incremental_state.json")
TAXONOMY_DIR    = os.path.join(DATA_DIR, "taxonomy")
TAXONOMY_CACHE  = os.path.join(TAXONOMY_DIR, "host_lineage_cache.json")
WATCHLIST_FILE  = os.path.join(DATA_DIR, "watchlist_new_taxids.tsv")

NCBI_BASE       = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_FTP_TAX    = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"
# 凭据一律走环境变量（历史明文 key 已泄露并于 2026-10-03 吊销，严禁再硬编码）
DEFAULT_EMAIL   = os.environ.get("NCBI_EMAIL", "")
DEFAULT_API_KEY = os.environ.get("NCBI_API_KEY", "")
MAX_RETRIES     = 5
REQUEST_DELAY   = 0.12
BATCH_SIZE      = 500

# ── 植物宿主判定正则 ────────────────────────────────────
PLANT_LINEAGE_PATTERN = re.compile(
    r"Viridiplantae|Streptophyta|Embryophyta|Tracheophyta|"
    r"Magnoliopsida|Liliopsida|eudicotyledons|monocots",
    re.IGNORECASE
)

# ── 已知植物病毒科/属 TaxID (用于祖先判定 L3) ────────────
# 从 ICTV VMR + NCBI Taxonomy 提取
KNOWN_PLANT_VIRUS_FAMILIES = {
    # (+)ssRNA
    39729,   # Potyviridae
    39730,   # Secoviridae
    39731,   # Tombusviridae
    39506,   # Bromoviridae
    39505,   # Closteroviridae
    39504,   # Luteoviridae
    39503,   # Tymoviridae
    39502,   # Comoviridae → now Secoviridae but keep for legacy
    675069,  # Virgaviridae
    675070,  # Benyviridae
    1986707, # Kitaviridae
    1986708, # Mayoviridae
    # (-)ssRNA
    1980417, # Aspiviridae
    1980418, # Fimoviridae
    1980419, # Tospoviridae
    1980420, # Phenuiviridae (part)
    1980421, # Rhabdoviridae (plant-infecting genera)
    # dsRNA
    39733,   # Reoviridae (plant-infecting genera)
    39732,   # Partitiviridae
    39734,   # Totiviridae (some plant)
    1922214, # Amalgaviridae
    # ssDNA
    10811,   # Geminiviridae
    10813,   # Nanoviridae
    # dsDNA (RT)
    186533,  # Caulimoviridae
    # Viroids
    12884,   # Pospiviroidae
    185752,  # Avsunviroidae
}

# 不含植物的病毒科: 过滤用
NON_PLANT_VIRUS_FAMILIES = {
    # Phages (太多了, 仅列大类)
    10699,   # Siphoviridae
    10744,   # Myoviridae
    10745,   # Podoviridae
    # Animal
    11118,   # Coronaviridae
    11308,   # Orthomyxoviridae
    11632,   # Retroviridae
    10292,   # Herpesviridae
    10295,   # Poxviridae
    11250,   # Picornaviridae
    11258,   # Flaviviridae
    11266,   # Filoviridae
    11571,   # Paramyxoviridae
}


def parse_args():
    p = argparse.ArgumentParser(description="PlantVirusDB 增量更新引擎 v2")
    p.add_argument("--since", help="起始日期 YYYY-MM-DD")
    p.add_argument("--until", help="终止日期 YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true", help="预览不写入")
    p.add_argument("--skip-taxonomy", action="store_true", help="跳过 Taxonomy 同步")
    p.add_argument("--skip-merged-check", action="store_true", help="跳过合并/deleted 处理")
    p.add_argument("--chunk-months", type=int, default=1)
    p.add_argument("--api-key", default=DEFAULT_API_KEY)
    p.add_argument("--output-dir", default=None)
    return p.parse_args()


# ═══════════════════════════════════════════════════════════
#  Phase 0: NCBI Taxonomy 同步
# ═══════════════════════════════════════════════════════════

def download_taxdump() -> str:
    """下载 taxdump.tar.gz 到本地 taxonomy 目录, 返回路径"""
    os.makedirs(TAXONOMY_DIR, exist_ok=True)
    local_path = os.path.join(TAXONOMY_DIR, "taxdump.tar.gz")

    # 检查是否已有近期下载 (24h内)
    if os.path.exists(local_path):
        age = time.time() - os.path.getmtime(local_path)
        if age < 86400:
            print(f"   📂 使用已有 taxdump ({(age/3600):.0f}h 前下载)")
            return local_path

    print(f"   📥 下载 taxdump.tar.gz (~71MB)...")
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(NCBI_FTP_TAX)
            with urlopen(req, timeout=120) as resp:
                with open(local_path, 'wb') as f:
                    f.write(resp.read())
            print(f"   ✅ 下载完成: {local_path}")
            return local_path
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"taxdump 下载失败: {e}")
    return ""


def parse_taxdump_nodes(taxdump_path: str) -> dict[str, dict]:
    """解析 nodes.dmp → {taxid: {parent_taxid, rank, ...}}"""
    nodes = {}
    import tarfile
    with tarfile.open(taxdump_path, 'r:gz') as tar:
        f = tar.extractfile('nodes.dmp')
        if f is None:
            raise FileNotFoundError("nodes.dmp not found in taxdump")
        for line in f.read().decode('utf-8').split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t|\t')
            if len(parts) >= 3:
                taxid = parts[0].strip()
                parent = parts[1].strip()
                rank = parts[2].strip()
                nodes[taxid] = {'parent_taxid': parent, 'rank': rank}
    return nodes


def parse_merged_dmp(taxdump_path: str) -> dict[str, str]:
    """解析 merged.dmp → {old_taxid: new_taxid}"""
    merged = {}
    import tarfile
    with tarfile.open(taxdump_path, 'r:gz') as tar:
        f = tar.extractfile('merged.dmp')
        if f is None:
            return merged
        for line in f.read().decode('utf-8').split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t|\t')
            if len(parts) >= 2:
                merged[parts[0].strip()] = parts[1].strip()
    return merged


def parse_delnodes_dmp(taxdump_path: str) -> set[str]:
    """解析 delnodes.dmp → {taxid, ...}"""
    deleted = set()
    import tarfile
    with tarfile.open(taxdump_path, 'r:gz') as tar:
        try:
            f = tar.extractfile('delnodes.dmp')
        except KeyError:
            return deleted
        if f is None:
            return deleted
        for line in f.read().decode('utf-8').split('\n'):
            line = line.strip()
            if line:
                parts = line.split('\t')
                deleted.add(parts[0].strip())
    return deleted


def is_descendant_of(taxid: str, ancestor: str, nodes: dict) -> bool:
    """检查 taxid 是否是 ancestor 的后代"""
    current = taxid
    visited = set()
    while current in nodes and current not in visited:
        if current == ancestor:
            return True
        visited.add(current)
        current = nodes[current].get('parent_taxid', '')
    return False


def detect_new_viral_taxids(nodes: dict, known_viral_taxids: set[str]) -> list[str]:
    """检测 nodes 中新增的病毒域 (10239) 下 taxid"""
    new_taxids = []
    for taxid in nodes:
        if taxid not in known_viral_taxids:
            if is_descendant_of(taxid, '10239', nodes):
                new_taxids.append(taxid)
    return new_taxids


def taxonomy_sync(api_key: str) -> dict:
    """Phase 0: NCBI Taxonomy 同步, 返回变更摘要"""
    print("\n" + "─" * 60)
    print("📚 Phase 0: NCBI Taxonomy 同步")
    print("─" * 60)

    # 加载状态
    state = load_state()
    known_viral = set(state.get('known_viral_taxids', []))

    # 下载
    taxdump_path = download_taxdump()
    nodes = parse_taxdump_nodes(taxdump_path)
    merged = parse_merged_dmp(taxdump_path)
    deleted = parse_delnodes_dmp(taxdump_path)

    # 检测
    new_viral = detect_new_viral_taxids(nodes, known_viral)

    result = {
        'nodes_count': len(nodes),
        'merged_count': len(merged),
        'deleted_count': len(deleted),
        'new_viral_taxids': new_viral,
        'merged': merged,
        'deleted': deleted,
        'nodes': nodes,
    }

    # 汇总
    print(f"   Taxonomy 节点总数: {len(nodes):,}")
    print(f"   新病毒域 taxid:     {len(new_viral)}")
    print(f"   被合并 taxid:      {len(merged)}")
    print(f"   已删除 taxid:      {len(deleted)}")

    # 对新增病毒 taxid, 按祖先分类初筛
    plant_candidates = []
    for tid in new_viral:
        for fam_tid in KNOWN_PLANT_VIRUS_FAMILIES:
            if is_descendant_of(tid, str(fam_tid), nodes):
                plant_candidates.append(tid)
                break

    if plant_candidates:
        print(f"   其中已知植物病毒科下: {len(plant_candidates)}")
        # 自动纳入已知植物病毒 taxid
        for tid in plant_candidates:
            known_viral.add(tid)

    if new_viral:
        # 更新状态
        all_known = known_viral | set(new_viral)
        state['known_viral_taxids'] = list(all_known)
        state['taxonomy_last_sync'] = datetime.now().strftime("%Y-%m-%d")
        save_state(state)

    return result


# ═══════════════════════════════════════════════════════════
#  Phase 1: 序列增量获取
# ═══════════════════════════════════════════════════════════

def _ncbi_request(endpoint: str, params: dict, api_key: str = "",
                  expect_xml: bool = False) -> str | ET.Element:
    """通用 NCBI E-utilities 请求, 自动处理 IncompleteRead"""
    p = dict(params)
    p.setdefault("tool", "PlantVirusDB")
    p.setdefault("email", DEFAULT_EMAIL)
    if api_key:
        p["api_key"] = api_key

    url = NCBI_BASE + "/" + endpoint + "?" + urlencode(p)

    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url)
            with urlopen(req, timeout=60) as resp:
                text = resp.read().decode('utf-8')
            return ET.fromstring(text) if expect_xml else text
        except (HTTPError, URLError, IncompleteRead) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"NCBI 请求失败 ({endpoint}): {type(e).__name__}: {e}")


def esearch_count(query: str, api_key: str = "") -> int:
    """esearch 返回结果数"""
    xml = _ncbi_request("esearch.fcgi", {
        "db": "nucleotide", "term": query, "retmax": 0, "usehistory": "n"
    }, api_key, expect_xml=True)
    el = xml.find(".//Count")
    return int(el.text) if el is not None and el.text else 0


def esearch_with_history(query: str, api_key: str = "") -> tuple[str, str, int]:
    """esearch 启用 history, 返回 (WebEnv, QueryKey, Count)"""
    xml = _ncbi_request("esearch.fcgi", {
        "db": "nucleotide", "term": query, "usehistory": "y", "retmax": 0
    }, api_key, expect_xml=True)
    webenv = xml.find(".//WebEnv").text
    qkey = xml.find(".//QueryKey").text
    count = int(xml.find(".//Count").text or "0")
    return webenv, qkey, count


def efetch_acc_list(webenv: str, qkey: str, count: int,
                    api_key: str = "", batch_size: int = 10000) -> list[str]:
    """从 history 分页拉取 accession 列表"""
    all_ids = []
    for start in range(0, count, batch_size):
        text = _ncbi_request("efetch.fcgi", {
            "db": "nucleotide", "query_key": qkey, "WebEnv": webenv,
            "retstart": start, "retmax": batch_size,
            "rettype": "acc", "retmode": "text",
        }, api_key)
        accs = [l.strip() for l in text.strip().split('\n') if l.strip()]
        all_ids.extend(accs)
        if start + batch_size < count:
            time.sleep(REQUEST_DELAY)
    return all_ids


def _efetch_post(endpoint_data: dict, api_key: str = "", timeout: int = 120) -> str:
    """efetch POST 请求 (用于 GenBank/FASTA)"""
    url = NCBI_BASE + "/efetch.fcgi"
    data = dict(endpoint_data)
    data.setdefault("tool", "PlantVirusDB")
    data.setdefault("email", DEFAULT_EMAIL)
    if api_key:
        data["api_key"] = api_key

    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, data=urlencode(data).encode())
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8')
        except (HTTPError, URLError, IncompleteRead) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"efetch POST 失败: {type(e).__name__}: {e}")
    return ""


def build_delta_query(start_iso: str, end_iso: str) -> str:
    """构建 PDAT + MDAT 双日期查询
    start_iso/end_iso: YYYY-MM-DD 格式, 内部转为 NCBI YYYY/MM/DD
    """
    s = start_iso.replace("-", "/")
    e = end_iso.replace("-", "/")
    return (
        f'viruses[filter]'
        f' AND (("{s}"[PDAT] : "{e}"[PDAT])'
        f' OR ("{s}"[MDAT] : "{e}"[MDAT]))'
    )


def sequence_delta_fetch(since: str, until: str, api_key: str,
                         chunk_months: int = 1) -> list[str]:
    """Phase 1: 获取增量病毒序列 accession 列表 (PDAT + MDAT)"""
    print("\n" + "─" * 60)
    print("🔍 Phase 1: 序列增量获取 (PDAT + MDAT)")
    print("─" * 60)

    s = datetime.strptime(since, "%Y-%m-%d")
    e = datetime.strptime(until, "%Y-%m-%d")

    all_accs = []
    current = s
    while current < e:
        y = current.year + (current.month + chunk_months - 1) // 12
        m = (current.month + chunk_months - 1) % 12 + 1
        d = min(current.day, 28)
        chunk_end = min(datetime(y, m, d), e)

        cs = current.strftime("%Y-%m-%d")
        ce = chunk_end.strftime("%Y-%m-%d")
        query = build_delta_query(cs, ce)
        count = esearch_count(query, api_key)
        print(f"   {cs} → {ce}: {count:,} 条")

        if count > 0:
            webenv, qkey, _ = esearch_with_history(query, api_key)
            accs = efetch_acc_list(webenv, qkey, count, api_key)
            all_accs.extend(accs)

        current = chunk_end + timedelta(days=1)
        time.sleep(REQUEST_DELAY)

    unique = list(dict.fromkeys(all_accs))
    print(f"   📊 去重后: {len(unique):,} 条")
    return unique


# ═══════════════════════════════════════════════════════════
#  Phase 2: 五层植物病毒判定
# ═══════════════════════════════════════════════════════════

def _parse_genbank_multi(text: str) -> list[dict]:
    """解析多记录 GenBank flat file

    GenBank 格式说明:
      DEFINITION 行可能跨多行 (后续行以 12 空格开头)
      SOURCE/ORGANISM 也有跨行 continuation (12 空格)
      关键: 12 空格 continuation 只属于紧前一个 section
    """
    records = []
    current = None
    in_features = False
    in_definition = False      # 正在解析 DEFINITION 跨行

    for line in text.split('\n'):
        # ── 新记录 ──────────────────────────────────
        if line.startswith("LOCUS"):
            if current:
                records.append(current)
            current = {"_locus_line": line}
            in_features = False
            in_definition = False
            continue

        if current is None:
            continue

        # ── DEFINITION (含跨行) ─────────────────────
        if line.startswith("DEFINITION"):
            current["definition"] = line[12:].strip()
            in_definition = True
            continue

        if in_definition and line.startswith("            "):
            # 12 空格开头 = continuation, 且不含其他关键字
            stripped = line.strip()
            if not any(stripped.startswith(kw) for kw in
                       ["ACCESSION", "VERSION", "KEYWORDS", "SOURCE",
                        "REFERENCE", "FEATURES", "ORIGIN", "CONTIG"]):
                current["definition"] = (current.get("definition", "") + " " +
                                         stripped).strip()
                continue
        in_definition = False  # 遇到非 continuation 行, 结束 DEFINITION 段

        # ── 元数据行 ────────────────────────────────
        if line.startswith("ACCESSION"):
            current["accession"] = line[12:].strip()

        elif line.startswith("VERSION"):
            current["version"] = line[12:].strip()

        elif line.strip().startswith("ORGANISM"):
            current["organism"] = line[12:].strip()

        elif line.startswith("REFERENCE"):
            in_features = False

        elif line.startswith("FEATURES"):
            in_features = True

        # ── FEATURES qualifiers ─────────────────────
        elif in_features:
            stripped = line.strip()
            if stripped.startswith('/host='):
                current["host"] = stripped.split('=')[1].strip().strip('"')
            elif stripped.startswith('/isolation_source='):
                current["isolation_source"] = stripped.split('=')[1].strip().strip('"')
            elif stripped.startswith('/country='):
                current["country"] = stripped.split('=')[1].strip().strip('"')
            elif stripped.startswith('/geo_loc_name='):
                if "country" not in current:
                    current["country"] = stripped.split('=')[1].strip().strip('"')
            elif stripped.startswith('/collection_date='):
                current["collection_date"] = stripped.split('=')[1].strip().strip('"')
            elif stripped.startswith('/segment='):
                current["segment"] = stripped.split('=')[1].strip().strip('"')
            elif 'db_xref="taxon:' in stripped:
                m = re.search(r'taxon:(\d+)', stripped)
                if m:
                    current["taxid"] = m.group(1)

    if current:
        records.append(current)
    return records


def _ncbi_taxonomy_lineage(taxid: str, api_key: str = "") -> str:
    """查 NCBI Taxonomy → 返回完整 lineage 字符串 (如 '...; Viridiplantae; ...')"""
    cache = _load_lineage_cache()
    if taxid in cache:
        return cache[taxid]

    try:
        xml_str = _efetch_post({
            "db": "taxonomy", "id": taxid, "retmode": "xml"
        }, api_key, timeout=30)
        # NCBI Taxonomy XML: <TaxaSet><Taxon><Lineage>...</Lineage></Taxon></TaxaSet>
        root = ET.fromstring(xml_str)
        lineage_el = root.find(".//Lineage")
        lineage = lineage_el.text if lineage_el is not None else ""

        cache[taxid] = lineage
        _save_lineage_cache(cache)
        return lineage
    except Exception as e:
        return ""


def _load_lineage_cache() -> dict:
    if os.path.exists(TAXONOMY_CACHE):
        try:
            with open(TAXONOMY_CACHE, encoding='utf-8') as f:
                data = f.read().strip()
                if data:
                    return json.loads(data)
        except (json.JSONDecodeError, Exception):
            pass
    return {}


def _save_lineage_cache(cache: dict):
    os.makedirs(os.path.dirname(TAXONOMY_CACHE), exist_ok=True)
    with open(TAXONOMY_CACHE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)


def _load_known_plant_taxids() -> set[str]:
    """从现有 Plant_Virus_Full.Info.tsv 加载已知植物病毒 TaxID"""
    info_path = PIPELINE_OUTPUTS["full_tsv"]
    if not os.path.exists(info_path):
        return set()
    df = pl.read_csv(info_path, separator='\t', infer_schema_length=0)
    if 'Taxid' not in df.columns:
        return set()
    return set(str(t) for t in df['Taxid'].drop_nulls().to_list() if str(t).strip())


def _is_plant_taxid_ancestor(taxid: str, taxsyn_result: dict) -> bool:
    """检查 taxid 的祖先是否有已知植物病毒科 (L3)"""
    nodes = taxsyn_result.get('nodes', {})
    if not nodes:
        return False
    for fam_tid in KNOWN_PLANT_VIRUS_FAMILIES:
        if is_descendant_of(taxid, str(fam_tid), nodes):
            return True
    return False


def _host_looks_plant(host: str) -> bool:
    """预筛选: host 名是否可能是植物 (避免为细菌/动物浪费 API 调用)"""
    host_low = host.lower()
    # 明确非植物
    non_plant = [
        'staphylococcus', 'klebsiella', 'pseudomonas', 'escherichia',
        'vibrio', 'salmonella', 'bacillus', 'clostridium', 'streptococcus',
        'enterococcus', 'listeria', 'mycobacterium', 'acinetobacter',
        'homo sapiens', 'human', 'patient', 'mus musculus', 'rattus',
        'bos taurus', 'cattle', 'sus scrofa', 'pig', 'gallus', 'chicken',
        'canis', 'dog', 'felis', 'cat', 'equus', 'horse',
        'mosquito', 'tick', 'aphid', 'whitefly', 'thrips', 'nematode',
        'cryptosporidium', 'giardia', 'plasmodium',
        'phage', 'bacteriophage', 'archaea',
    ]
    for kw in non_plant:
        if kw in host_low:
            return False
    # 植物特征 (拉丁属名或常见名)
    plant_indicators = [
        'solanum', 'nicotiana', 'arabidopsis', 'brassica', 'cucumis',
        'phaseolus', 'glycine', 'oryza', 'triticum', 'hordeum', 'zea',
        'vitis', 'prunus', 'malus', 'pyrus', 'citrus', 'fragaria',
        'capsicum', 'daucus', 'lactuca', 'spinacia', 'allium',
        'gossypium', 'manihot', 'ipomoea', 'dioscorea', 'sorghum',
        'medicago', 'populus', 'pinus', 'picea', 'quercus',
        'lycium', 'ficus', 'iris', 'cenostigma', 'theobroma',
        'cucurbita', 'raphanus', 'beta', 'helianthus', 'carthamus',
        'cocos', 'elaeis', 'phoenix', 'musa', 'ananas', 'carica',
        'mangifera', 'persea', 'olea', 'coffea', 'camellia',
        # 常见名
        'tomato', 'potato', 'tobacco', 'wheat', 'rice', 'maize',
        'barley', 'oat', 'soybean', 'grape', 'apple', 'banana',
        'citrus', 'cotton', 'sugarcane', 'sugar beet', 'beet',
        'pepper', 'bean', 'pea', 'cucumber', 'lettuce', 'spinach',
        'carrot', 'onion', 'garlic', 'papaya', 'mango', 'goji',
        'strawberry', 'blueberry', 'cherry', 'plum', 'peach',
        'clover', 'alfalfa', 'sunflower', 'rose', 'lily', 'cassava',
        'fig', 'iris', 'yam', 'sweet potato', 'cowpea', 'chickpea',
        'coconut', 'oil palm', 'date palm', 'pineapple', 'avocado',
        'poplar', 'birch', 'oak', 'pine', 'spruce', 'elm',
        # catch-all
        'viridiplantae', 'streptophyta', 'plantae',
    ]
    for kw in plant_indicators:
        if kw in host_low:
            return True
    # 不确定 → 让 NCBI Taxonomy 判定
    return True


def _resolve_hosts_batch(host_names: list) -> dict:
    """
    批量 taxonkit 宿主 lineage 查询
    一次加载 names.dmp/nodes.dmp, 处理全部宿主名
    返回 {host_name: lineage_string}
    """
    import subprocess

    cache = _load_lineage_cache()

    # 去重 + 清洗
    clean_map = {}  # clean_name → original_name
    clean_names = []
    
    # 明确的非植物宿主词 (鸟/哺乳动物/昆虫/细菌, 直接拒绝, 不查 lineage)
    ANIMAL_KEYWORDS = [
        'gull', 'duck', 'goose', 'swan', 'heron', 'egret', 'hawk', 'eagle',
        'crow', 'raven', 'sparrow', 'robin', 'finch', 'pigeon', 'dove',
        'seal', 'whale', 'dolphin', 'porpoise',
        'chicken', 'turkey', 'quail', 'pheasant',
        'goat', 'sheep', 'swine', 'cattle', 'horse', 'donkey', 'mule',
        'dog', 'cat', 'rabbit', 'mouse', 'rat', 'guinea pig', 'hamster',
        'human', 'patient', 'homo sapien',
        'monkey', 'ape', 'chimpanzee', 'gorilla', 'baboon',
        'deer', 'elk', 'moose', 'antelope', 'buffalo', 'bison',
        'camel', 'llama', 'alpaca',
        'mosquito', 'tick', 'flea', 'louse', 'mite',
        'aphid', 'whitefly', 'thrips', 'beetle', 'wasp', 'bee', 'ant',
        'nematode', 'snail', 'slug', 'oyster', 'mussel', 'clam',
        'shrimp', 'crab', 'lobster', 'crayfish',
        'fish', 'salmon', 'trout', 'carp', 'catfish', 'tilapia',
        'frog', 'toad', 'salamander', 'newt',
        'snake', 'lizard', 'turtle', 'tortoise',
        'bat', 'rodent', 'squirrel',
    ]
    
    result = {}
    
    for h in host_names:
        h = str(h).strip()
        if not h:
            continue
        # 取分号/逗号前第一段
        clean = h.split(";")[0].split(",")[0].strip()
        clean = re.sub(r'\s+[A-Z]\.', '', clean).strip()
        if clean and len(clean) >= 2 and clean not in clean_map:
            clean_map[clean] = h
            clean_names.append(clean)

    uncached = []
    for clean in clean_names:
        cache_key = f"host:{clean}"
        if cache_key in cache:
            result[clean_map[clean]] = cache[cache_key]
            result[clean] = cache[cache_key]
        else:
            uncached.append(clean)

    if not uncached:
        return result

    # 批量 name2taxid (通过临时文件, 避免管道截断)
    import tempfile
    tmpfile = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            tmpfile = f.name
            f.write('\n'.join(uncached) + '\n')

        p1 = subprocess.run(
            ["taxonkit", "name2taxid", tmpfile],
            capture_output=True, text=True, timeout=120
        )
    except Exception:
        return result
    finally:
        if tmpfile and os.path.exists(tmpfile):
            os.unlink(tmpfile)

    if p1.returncode != 0:
        return result

    # 解析 name2taxid 结果: "goat\t9925"
    name_to_taxid = {}
    for line in p1.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].strip():
            name_to_taxid[parts[0].strip()] = parts[1].strip()

    # 收集有效的 taxid
    taxids_for_lineage = []
    taxid_to_names = {}
    for clean in uncached:
        tid = name_to_taxid.get(clean, "")
        if tid:
            taxids_for_lineage.append(tid)
            taxid_to_names[tid] = clean
        else:
            result[clean] = ""
            result[clean_map.get(clean, clean)] = ""

    if not taxids_for_lineage:
        return result

    # 批量 lineage (通过临时文件)
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            tmpfile2 = f.name
            f.write('\n'.join(taxids_for_lineage) + '\n')

        p2 = subprocess.run(
            ["taxonkit", "lineage", tmpfile2],
            capture_output=True, text=True, timeout=120
        )
    except Exception:
        if tmpfile2 and os.path.exists(tmpfile2):
            os.unlink(tmpfile2)
        return result

    if tmpfile2 and os.path.exists(tmpfile2):
        os.unlink(tmpfile2)

    if p2.returncode != 0:
        return result

    # 解析 lineage: "9925\tcellular organisms;Eukaryota;..."
    tid_to_lineage = {}
    for line in p2.stdout.strip().split("\n"):
        parts = line.split("\t", 1)
        if len(parts) >= 2:
            tid_to_lineage[parts[0].strip()] = parts[1].strip()

    # 映射回宿主名并缓存
    for tid, clean in taxid_to_names.items():
        lineage = tid_to_lineage.get(tid, "")
        result[clean] = lineage
        orig = clean_map.get(clean, clean)
        result[orig] = lineage
        cache[f"host:{clean}"] = lineage
        if orig != clean:
            cache[f"host:{orig}"] = lineage

    _save_lineage_cache(cache)
    return result


def _quality_filter_reject(rec: dict) -> bool:
    """
    自动质量过滤: 返回 True 表示应排除
    1. 专利/人工构建序列
    2. 超短片段 (<200bp, 非完整基因组)

    非植物宿主已由 L2 taxonkit lineage 覆盖, 不在此重复
    """
    definition = rec.get("definition", "")

    # 1. 专利/人工序列: GenBank_Title 含特征词
    patent_kw = ["JP 20", "RECOMBINANT", "CHIMERIC ANTIGEN", "CIRCULAR RNA ENCODING"]
    if any(kw in definition for kw in patent_kw):
        return True

    # 2. 超短片段: Length < 200bp 且非 complete
    locus = rec.get("_locus_line", "")
    if locus:
        m = re.search(r'(\d+)\s+bp', locus)
        if m:
            length = int(m.group(1))
            # 从 definition 判断完整性
            def_lower = definition.lower()
            is_complete = "complete genome" in def_lower or "complete sequence" in def_lower
            if length < 200 and not is_complete:
                return True

    return False


def host_resolution(accessions: list[str], api_key: str,
                    taxsyn_result: dict) -> list[dict]:
    """Phase 2: 五层植物病毒判定"""
    print("\n" + "─" * 60)
    print("🌿 Phase 2: 五层植物病毒判定")
    print("─" * 60)

    known_taxids = _load_known_plant_taxids()
    print(f"   L1 已知植物病毒 TaxID: {len(known_taxids):,}")

    plant_records = []
    stats = {"L1_known": 0, "L2_host_lineage": 0, "L3_ancestor": 0,
             "L4_ictv": 0, "L5_keyword": 0, "non_plant": 0, "errors": 0}
    new_plant_taxids = set()

    total = len(accessions)
    for i in range(0, total, BATCH_SIZE):
        batch = accessions[i:i + BATCH_SIZE]
        try:
            records = _parse_genbank_multi(
                _efetch_post({"db": "nucleotide", "id": ",".join(batch),
                              "rettype": "gb", "retmode": "text"}, api_key)
            )
        except Exception as e:
            stats["errors"] += len(batch)
            progress = min(i + BATCH_SIZE, total)
            print(f"   [{progress}/{total}] ⚠ 批次失败, 跳过")
            time.sleep(REQUEST_DELAY)
            continue

        # 批量 taxonkit: 收集本批所有 /host 字段, 一次查完
        batch_hosts = [r.get("host", "").strip() for r in records if r.get("host", "").strip()]
        host_lineages = _resolve_hosts_batch(batch_hosts) if batch_hosts else {}

        for rec in records:
            taxid = rec.get("taxid", "").strip()
            host = rec.get("host", "").strip()
            organism = rec.get("organism", "").strip()
            definition = rec.get("definition", "").strip()
            accession = rec.get("accession", rec.get("version", "?"))

            # ── QC: 自动质量过滤 (专利序列/超短片段) ──
            if _quality_filter_reject(rec):
                stats["non_plant"] += 1
                continue

            # ── L1: 已知植物病毒 TaxID ─────────────────
            if taxid and taxid in known_taxids:
                stats["L1_known"] += 1
                plant_records.append(rec)
                continue

            # ── L2: /host 物种 → taxonkit lineage → Viridiplantae ──
            if host:
                lineage = host_lineages.get(host, "")
                if lineage and PLANT_LINEAGE_PATTERN.search(lineage):
                    stats["L2_host_lineage"] += 1
                    plant_records.append(rec)
                    if taxid:
                        new_plant_taxids.add(taxid)
                    continue

            # ── L3: 病毒 TaxID → 祖先是否已知植物病毒科 ──
            if taxid and _is_plant_taxid_ancestor(taxid, taxsyn_result):
                stats["L3_ancestor"] += 1
                plant_records.append(rec)
                new_plant_taxids.add(taxid)
                continue

            # ── L4: ICTV VMR 对照 (占位: 需要本地 VMR 库) ──
            # 这一步需要 ICTV VMR 的 taxid → host 映射, 增量脚本里暂不做
            # 保留给全量 C2 阶段的 B1 模块处理

            # ── L5: 病毒名/定义 植物关键词兜底 ──
            combined = f"{organism} {definition}".lower()
            if _keyword_plant_match(combined, host):
                stats["L5_keyword"] += 1
                plant_records.append(rec)
                if taxid:
                    new_plant_taxids.add(taxid)
                continue

            stats["non_plant"] += 1

        progress = min(i + BATCH_SIZE, total)
        total_hits = sum(stats[k] for k in stats if k.startswith("L"))
        print(f"   [{progress}/{total}] 累计植物命中: {total_hits} "
              f"(L1:{stats['L1_known']} L2:{stats['L2_host_lineage']} "
              f"L3:{stats['L3_ancestor']} L5:{stats['L5_keyword']})")
        time.sleep(REQUEST_DELAY)

    # ── 汇总 ──────────────────────────────────────────
    print(f"\n   📊 判定结果:")
    print(f"   L1 (已知TaxID):     {stats['L1_known']}")
    print(f"   L2 (宿主lineage):   {stats['L2_host_lineage']}")
    print(f"   L3 (祖先分类):      {stats['L3_ancestor']}")
    print(f"   L5 (关键词兜底):    {stats['L5_keyword']}")
    print(f"   非植物:             {stats['non_plant']}")
    if stats['errors']:
        print(f"   错误/跳过:          {stats['errors']}")
    if new_plant_taxids:
        print(f"   🆕 新发现的植物病毒 TaxID: {len(new_plant_taxids)}")

    return plant_records


def _keyword_plant_match(combined: str, host: str) -> bool:
    """L5: 植物关键词词边界匹配, 排除动物/细菌

    用 \b 词边界防止子串误判: "oat" 不应匹配 "goat"
    """
    plant_kw = [
        'wheat', 'rice', 'maize', 'barley', 'oat', 'sorghum', 'soybean',
        'tomato', 'potato', 'tobacco', 'cucumber', 'pepper', 'bean', 'pea',
        'citrus', 'grape', 'apple', 'banana', 'sugarcane', 'cotton',
        'cassava', 'yam', 'cowpea', 'chickpea', 'sugar beet', 'beet',
        'mosaic virus', 'leaf curl', 'yellow dwarf', 'chlorotic', 'necrotic',
        'leafroll', 'bunchy top', 'streak', 'blotch', 'mottle', 'stunt',
        'potyvirus', 'geminivirus', 'tobamovirus', 'tombusvirus',
        'nepovirus', 'closterovirus', 'luteovirus', 'bromovirus',
        'carlavirus', 'potexvirus', 'furovirus', 'hordeivirus',
        'solanum', 'nicotiana', 'arabidopsis', 'brassica', 'cucumis',
        'phaseolus', 'glycine', 'oryza', 'triticum', 'hordeum',
        'vitis', 'prunus', 'malus', 'citrus',
        'beet necrotic', 'beet curly', 'beet mild',
        'turnip', 'radish', 'cabbage', 'lettuce', 'spinach', 'carrot',
        'onion', 'garlic', 'papaya', 'pineapple', 'mango',
        'strawberry', 'blueberry', 'cherry', 'plum', 'peach',
        'alfalfa', 'clover', 'ryegrass', 'sugarcane',
        'poplar', 'birch', 'oak', 'pine', 'spruce',
    ]
    exclude_kw = [
        'phage', 'bacteriophage', 'staphylococcus', 'klebsiella',
        'pseudomonas', 'escherichia', 'vibrio', 'salmonella', 'bacillus',
        'clostridium', 'streptococcus', 'influenza', 'coronavirus',
        'hepatitis', 'adenovirus', 'rotavirus', 'norovirus',
        'chicken', 'avian', 'swine', 'porcine', 'bovine', 'canine',
        'feline', 'murine', 'simian', 'equine', 'bat coronavirus',
        'fish', 'shrimp', 'oyster', 'salmon', 'trout',
        'mosquito', 'tick', 'aphid', 'whitefly', 'thrips',
        'cryptosporidium', 'giardia', 'plasmodium',
        'human', 'patient', 'homo sapiens',
    ]
    has_plant = any(re.search(r'\b' + re.escape(kw) + r'\b', combined) for kw in plant_kw)
    has_exclude = any(re.search(r'\b' + re.escape(kw) + r'\b', combined) for kw in exclude_kw)
    # host 字段直接排除 (词边界)
    if host:
        host_low = host.lower()
        if any(re.search(r'\b' + re.escape(kw) + r'\b', host_low) for kw in exclude_kw):
            return False
    return has_plant and not has_exclude


# ═══════════════════════════════════════════════════════════
#  Phase 3: 数据库合并 + 元数据补全
# ═══════════════════════════════════════════════════════════

# ── LOCUS 行解析 ───────────────────────────────────────

def _parse_locus_line(locus_line: str) -> dict:
    """
    解析 GenBank LOCUS 行, 提取 Length / Molecule_type / Molecule_Type2 /
    Topology / Sequence_Type / Release_Date / Nuc_Completeness

    LOCUS 格式:
      LOCUS       AC123456             12345 bp    RNA     linear   VRL 15-JAN-2025
                  ^^^^^^^^^^^^^^^^^^^  ^^^^^^^^   ^^^^^^  ^^^^^^^  ^^^ ^^^^^^^^^^^
                  accession+len         mol_type  mol2?   topology div date
    """
    result = {}
    if not locus_line.startswith("LOCUS"):
        return result

    line = locus_line.rstrip()

    # Length: 在 "bp" 或 "aa" 之前的数字
    m_len = re.search(r'(\d+)\s+(bp|aa)', line)
    if m_len:
        result["Length"] = m_len.group(1)

    # Molecule_type + Molecule_Type2: "DNA", "RNA", "ss-RNA", "ds-DNA", "cRNA", "mRNA"
    # 常见的: "DNA", "RNA", "ss-RNA", "ds-RNA", "ss-DNA", "ds-DNA"
    # LOCUS 行的 mol type 部分在长度之后
    mol_match = re.search(
        r'\d+\s+bp\s+([A-Za-z-]+)(?:\s+([A-Za-z-]+))?\s+(linear|circular)',
        line
    )
    if mol_match:
        result["Molecule_type"] = mol_match.group(1)
        result["Molecule_Type2"] = mol_match.group(2) if mol_match.group(2) else ""
        result["Topology"] = mol_match.group(3)

    # Sequence_Type: RefSeq (NC_/AC_ accession) vs GenBank
    m_acc = re.search(r'LOCUS\s+(\S+)', line)
    if m_acc:
        acc = m_acc.group(1)
        if re.match(r'^N[CGTW]_|^A[CGP]_', acc):
            result["Sequence_Type"] = "RefSeq"
        else:
            result["Sequence_Type"] = "GenBank"

    # Release_Date: DD-MMM-YYYY at end of LOCUS line
    m_date = re.search(r'(\d{1,2}-[A-Z]{3}-\d{4})$', line)
    if m_date:
        result["Release_Date"] = m_date.group(1)

    # Nuc_Completeness: indicated by "complete" in title or definition
    # Can't reliably get from LOCUS alone; will be set from DEFINITION later

    return result


def _parse_locus_batch(text: str) -> dict[str, dict]:
    """从多记录 GenBank 文本解析所有 LOCUS 行, 返回 {accession: locus_data}"""
    result = {}
    for line in text.split('\n'):
        if line.startswith("LOCUS"):
            locus = _parse_locus_line(line)
            m = re.search(r'LOCUS\s+(\S+)', line)
            if m:
                result[m.group(1)] = locus
    return result


# ── taxonkit lineage ───────────────────────────────────

def _taxonkit_batch_lineage(taxids: list[str], taxonkit_bin: str = "taxonkit",
                            data_dir: str = "") -> dict[str, str]:
    """
    批量 taxonkit lineage 查询
    返回 {taxid: "cellular organisms;Eukaryota;Viridiplantae;..."}
    """
    import subprocess, tempfile

    taxids = [str(t).strip() for t in taxids if t and str(t).strip()]
    if not taxids:
        return {}

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        tmp_path = f.name
        f.write('\n'.join(taxids))

    try:
        cmd = [taxonkit_bin, "lineage"]
        if data_dir:
            cmd.extend(["--data-dir", data_dir])
        cmd.append(tmp_path)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        lineage_map = {}
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                lineage_map[parts[0].strip()] = parts[1].strip()
        return lineage_map
    except Exception as e:
        print(f"   ⚠ taxonkit 失败: {e}")
        return {}
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _extract_family_from_lineage(lineage: str) -> str:
    """从 lineage 字符串提取科名 (Viruses 分支下最接近物种的科级别分类)"""
    if not lineage:
        return ""
    # NCBI Taxonomy lineage: "...; Potyviridae; Potyvirus; ..."
    # 病毒科的命名特征: 以 -viridae 结尾
    parts = [p.strip() for p in lineage.split(';')]
    for part in reversed(parts):
        if part.lower().endswith('viridae') or part.lower().endswith('viroidae'):
            return part
    return ""


def _detect_nuc_completeness(definition: str, locus_data: dict) -> str:
    """推断核酸完整度

    2026-09-27 修复: 基因级标题("complete cds"、泛 "\bgene\b" 信号, 如
    "coat protein gene, complete cds"/"VP gene for virion protein")不代表基因组完整。
    NCBI 上游元数据存在同样歧义, 曾把 344 条基因级记录标成 complete 混入参考集。
    基因级一律返回 ""(未知); 标题同时声明 complete genome/sequence/segment 除外。
    """
    if not definition:
        return ""
    def_lower = definition.lower()
    if ('complete genome' in def_lower or 'complete sequence' in def_lower
            or 'complete segment' in def_lower):
        return "complete"
    if 'partial' in def_lower:
        return "partial"
    if re.search(r'complete\s+cds|complete\s+coding|complete\s+genes?\b|\bgene\b|\bgenes\b', def_lower):
        return ""
    return ""
    return ""


def _detect_usa(country: str) -> str:
    """从 /country 字段拆解 USA 标记"""
    if not country:
        return ""
    country_lower = country.lower()
    if 'usa' in country_lower or 'united states' in country_lower:
        return country.strip()
    return ""


def _read_fasta_records(fasta_path: str) -> list[tuple[str, str]]:
    records = []
    cur_h, cur_s = "", []
    with open(fasta_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            if line.startswith('>'):
                if cur_h: records.append((cur_h, ''.join(cur_s)))
                cur_h = line[1:]; cur_s = []
            else:
                cur_s.append(line)
        if cur_h: records.append((cur_h, ''.join(cur_s)))
    return records


def _build_taxid_lookup(info_path: str) -> dict[str, dict]:
    """从现有 TSV 构建 taxid → 元数据 查表"""
    if not os.path.exists(info_path):
        return {}
    try:
        df = pl.read_csv(info_path, separator='\t', infer_schema_length=0)
        # 每个 taxid 取第一条非空记录
        lookup = {}
        inherit_cols = [
            "Species_ICTV", "Family", "Segment",
            "Molecule_type", "Molecule_Type2", "Sequence_Type"
        ]
        for row in df.iter_rows(named=True):
            tid = str(row.get("Taxid", "")).strip()
            if not tid or tid in lookup:
                continue
            entry = {}
            for col in inherit_cols:
                val = str(row.get(col, "")).strip()
                if val:
                    entry[col] = val
            if entry:
                lookup[tid] = entry
        return lookup
    except Exception:
        return {}


def database_merge(plant_records: list[dict], api_key: str,
                   output_dir: str, taxsyn_result: dict) -> dict:
    """
    Phase 3: 下载序列 → LOCUS 解析 → taxid 继承 → taxonkit lineage → 追加入库
    """
    print("\n" + "─" * 60)
    print("💾 Phase 3: 数据库合并 + 元数据补全")
    print("─" * 60)

    os.makedirs(output_dir, exist_ok=True)
    full_fasta = PIPELINE_OUTPUTS["full_fasta"]
    full_info = PIPELINE_OUTPUTS["full_tsv"]

    result = {"new_fasta": 0, "new_tsv": 0, "merged_updated": 0, "deleted_marked": 0,
              "known_inherited": 0, "new_taxonkit": 0}

    # ── 下载 FASTA + GenBank (一并获取, 用于 LOCUS 解析) ──
    accessions = [r.get("accession", r.get("version", "")) for r in plant_records]
    accessions = [a for a in accessions if a]
    fasta_path = os.path.join(output_dir, "incremental_plant_viruses.fasta")

    print(f"   📥 下载 {len(accessions)} 条 FASTA + GenBank 元数据...")
    all_fasta = ""
    all_gb_text = ""
    for i in range(0, len(accessions), BATCH_SIZE):
        batch = accessions[i:i + BATCH_SIZE]
        try:
            all_fasta += _efetch_post(
                {"db": "nucleotide", "id": ",".join(batch),
                 "rettype": "fasta", "retmode": "text"}, api_key, timeout=300
            )
            all_gb_text += _efetch_post(
                {"db": "nucleotide", "id": ",".join(batch),
                 "rettype": "gb", "retmode": "text"}, api_key, timeout=300
            )
        except Exception as e:
            print(f"   ⚠ 批次 {i//BATCH_SIZE+1} 失败: {e}")
        time.sleep(REQUEST_DELAY)

    with open(fasta_path, 'w', encoding='utf-8') as f:
        f.write(all_fasta)

    # ── 解析 LOCUS 行 ──────────────────────────────────
    locus_map = _parse_locus_batch(all_gb_text)
    print(f"   📐 LOCUS 解析: {len(locus_map)} 条")

    # ── 构建 taxid 继承查表 ────────────────────────────
    taxid_lookup = _build_taxid_lookup(full_info)
    print(f"   📋 已知 taxid 继承源: {len(taxid_lookup)} 个")

    # ── 收集新病毒 taxid → taxonkit lineage ────────────
    known_taxids = _load_known_plant_taxids()
    new_taxids_for_lineage = []
    for rec in plant_records:
        tid = rec.get("taxid", "").strip()
        if tid and tid not in known_taxids and tid not in taxid_lookup:
            new_taxids_for_lineage.append(tid)

    lineage_map = {}
    if new_taxids_for_lineage:
        unique_new = list(dict.fromkeys(new_taxids_for_lineage))
        print(f"   🧬 taxonkit lineage: {len(unique_new)} 个新 taxid...")
        lineage_map = _taxonkit_batch_lineage(unique_new)
        print(f"   ✅ taxonkit 成功: {len(lineage_map)} 个")

    # ── 组装完整 TSV 行 ────────────────────────────────
    rows = []
    for rec in plant_records:
        acc = rec.get("accession", rec.get("version", ""))
        tid = rec.get("taxid", "").strip()
        locus = locus_map.get(acc, {})
        definition = rec.get("definition", "")
        country = rec.get("country", "")
        is_known = tid in known_taxids

        # LOCUS 直接解析的列
        length = locus.get("Length", "")
        mol_type = locus.get("Molecule_type", "")
        mol_type2 = locus.get("Molecule_Type2", "")
        topology = locus.get("Topology", "")
        seq_type = locus.get("Sequence_Type", "")
        release_date = locus.get("Release_Date", "")
        completeness = _detect_nuc_completeness(definition, locus)
        usa = _detect_usa(country)

        # Family / Species_ICTV / Segment: 继承 or taxonkit
        # Family / Species_ICTV / Segment: GenBank 优先 > taxid继承 > taxonkit > 留空
        family = ""
        species_ictv = ""
        segment = rec.get("segment", "")  # GenBank /segment qualifier 最优先

        if is_known and tid in taxid_lookup:
            inherited = taxid_lookup[tid]
            family = inherited.get("Family", "")
            species_ictv = inherited.get("Species_ICTV", "")
            if not segment:
                segment = inherited.get("Segment", "")
            if not mol_type:
                mol_type = inherited.get("Molecule_type", "")
            if not mol_type2:
                mol_type2 = inherited.get("Molecule_Type2", "")
            if not seq_type:
                seq_type = inherited.get("Sequence_Type", "")
            result["known_inherited"] += 1
        elif tid in lineage_map:
            family = _extract_family_from_lineage(lineage_map[tid])
            # 2026-10-03: 不再写 PENDING_VMR/PENDING_CLASSIFY 占位符(会原样暴露给
            # 网站用户), 回退 NCBI 名; 段名未知留空, 由 lib/build_segment_canonical.py 规范层补
            if not species_ictv:
                species_ictv = rec.get("organism", "") or ""
            result["new_taxonkit"] += 1
        elif tid and tid not in known_taxids:
            # taxonkit 也没拿到 → 同样回退 NCBI 名, 段留空
            species_ictv = rec.get("organism", "") or ""

        rows.append({
            "Accession": acc,
            "Taxid": tid,
            "Species_NCBI": rec.get("organism", ""),
            "Species_ICTV": species_ictv,
            "Family": family,
            "Segment": segment,
            "Topology": topology,
            "Molecule_type": mol_type,
            "Molecule_Type2": mol_type2,
            "Sequence_Type": seq_type,
            "Length": length,
            "Nuc_Completeness": completeness,
            "GenBank_Title": definition,
            "Geo_Location": country,
            "USA": usa,
            "Host": rec.get("host", ""),
            "Isolation_Source": rec.get("isolation_source", ""),
            "Collection_Date": rec.get("collection_date", ""),
            "Release_Date": release_date,
            "NCBI_Status": "",
            "Segment_std": "",   # 2026-10-03: 保持 21 列 schema, 由规范层统一计算
        })

    # 2026-10-03: None → "" (老 polars 会把 null 渲染成字面量 "None" 污染全库;
    # rec.get(key, "") 的默认值只在键缺失时生效, 键存在但值为 None 时仍返回 None)
    rows = [{k: ("" if v is None else str(v)) for k, v in r.items()} for r in rows]

    df = pl.DataFrame(rows)

    # 写入增量 TSV (归档)
    info_path = os.path.join(output_dir, "incremental_plant_viruses_info.tsv")
    df.write_csv(info_path, separator='\t')
    print(f"   📄 增量 TSV: {info_path}")

    # 统计
    filled = {col: (df[col].fill_null("").cast(pl.Utf8) != "").sum()
              for col in df.columns}
    print(f"   📊 列填充率:")
    for col in ["Family", "Length", "Topology", "Molecule_type", "Sequence_Type",
                "Segment", "Release_Date", "Nuc_Completeness"]:
        cnt = filled.get(col, 0)
        pct = cnt / len(rows) * 100 if rows else 0
        print(f"      {col:20s}: {cnt}/{len(rows)} ({pct:.0f}%)")

    # ── 去重追加 FASTA ─────────────────────────────────
    # 2026-10-03: 版本号归一去重(历史 bug: esearch 返回无版本号 accession, 与库内
    # 带版本号的同条记录互不认识 → 同一序列被重复追加 208 次)
    existing_accs = set()
    if os.path.exists(full_info):
        edf = pl.read_csv(full_info, separator='\t', infer_schema_length=0)
        existing_accs = {a.split(".")[0] for a in edf["Accession"].to_list()}

    acc_list = df["Accession"].to_list()
    acc_norm = [a.split(".")[0] for a in acc_list]
    new_accs = {n for n in acc_norm if n not in existing_accs}
    result["new_tsv"] = len(new_accs)

    if new_accs:
        fasta_records = _read_fasta_records(fasta_path)
        appended = 0
        with open(full_fasta, 'a', encoding='utf-8') as dst:
            for header, seq in fasta_records:
                if header.split()[0].split(".")[0] in new_accs:
                    dst.write(f">{header}\n")
                    for j in range(0, len(seq), 70):
                        dst.write(seq[j:j+70] + '\n')
                    appended += 1
        result["new_fasta"] = appended

        # 追加 TSV (按归一化 accession 选出真正新增的行)
        new_df = df.filter(pl.Series("keep", [n in new_accs for n in acc_norm]))
        existing_df = pl.read_csv(full_info, separator='\t', infer_schema_length=0)
        combined = pl.concat([existing_df, new_df.drop("keep")], how="diagonal")
        combined.write_csv(full_info, separator='\t')
        print(f"   ✅ FASTA +{appended} 条, TSV +{len(new_accs)} 条")
    else:
        print(f"   所有记录已存在, 无新增")

    # ── 处理 merged taxids ─────────────────────────────
    merged = taxsyn_result.get('merged', {})
    deleted = taxsyn_result.get('deleted', set())

    if merged and os.path.exists(full_info):
        # 更新现有数据中已被合并的 taxid
        merged_updates = 0
        for old_tid, new_tid in merged.items():
            if old_tid in existing_accs or old_tid in new_accs:
                # 这里需要更新 Info.tsv 中的 Taxid 列
                # 简化处理: 追加一条 merge 记录到日志
                merged_updates += 1
        result["merged_updated"] = merged_updates
        if merged_updates > 0:
            print(f"   🔄 检测到 {merged_updates} 个 taxid 被合并")

    if deleted:
        result["deleted_marked"] = len(deleted)
        print(f"   🗑 检测到 {len(deleted)} 个 taxid 被删除 (未自动修改数据库)")

    # ── fasta/info 同步护栏 ────────────────────────────
    # 2026-10-03: 曾发生 info 删行而 fasta 留序列的事故(1,747 条噬菌体孤儿序列)。
    # 每次合并后强制对账, 不同步时写 sync_check.txt 供人工处理。
    try:
        merged_accs = {a.split(".")[0] for a in
                       pl.read_csv(full_info, separator='\t', infer_schema_length=0)["Accession"].to_list()}
        fa_norms = {h.split()[0].split(".")[0] for h, _ in _read_fasta_records(full_fasta)}
        orphans = fa_norms - merged_accs
        seqless = merged_accs - fa_norms
        if orphans or seqless:
            print(f"   ⚠️ fasta/info 不同步: 孤儿序列 {len(orphans)} 条, 无序列行 {len(seqless)} 条")
            with open(os.path.join(output_dir, "sync_check.txt"), "w") as f:
                f.write("fasta_only(no info)\n" + "\n".join(sorted(orphans)) +
                        "\n\ninfo_only(no fasta)\n" + "\n".join(sorted(seqless)) + "\n")
        else:
            print("   ✅ fasta/info 完全同步")
    except Exception as e:
        print(f"   ⚠️ 同步检查失败: {type(e).__name__}: {e}")

    # ── 更新 watchlist ────────────────────────────────
    _update_watchlist(new_accs, taxsyn_result)

    return result


def _update_watchlist(new_accs: set[str], taxsyn_result: dict):
    """更新观察列表: 新 taxid 但无宿主信息"""
    # 简化实现: 对无 host 信息的记录输出日志
    watchlist_path = WATCHLIST_FILE
    # 此处可以记录无宿主信息的 taxid
    pass


# ═══════════════════════════════════════════════════════════
#  状态管理
# ═══════════════════════════════════════════════════════════

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {
        "last_sync_date": None,
        "total_runs": 0,
        "total_new_plant_accessions": 0,
        "known_viral_taxids": [],
        "taxonomy_last_sync": None,
    }


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_last_sync_date() -> str | None:
    state = load_state()
    if state.get("last_sync_date"):
        return state["last_sync_date"]
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, encoding='utf-8') as f:
            for line in f:
                if line.startswith("SOURCE_NCBI="):
                    return line.split("=", 1)[1].strip()
    return None


def update_version(new_count: int, total_records: int, sync_date: str):
    v = {}
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, encoding='utf-8') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, val = line.split('=', 1)
                    v[k.strip()] = val.strip()
    v["SOURCE_NCBI"] = sync_date
    v["RECORDS_TOTAL"] = str(total_records)
    v["LAST_INCREMENTAL"] = sync_date
    lines = ["# Plant Virus DB — 数据版本记录", f"# 最后增量: {sync_date}", ""]
    for k in sorted(v.keys()):
        lines.append(f"{k}={v[k]}")
    lines.append("")
    with open(VERSION_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


# ═══════════════════════════════════════════════════════════
#  main
# ═══════════════════════════════════════════════════════════

def main():
    args = parse_args()
    start_time = time.time()

    since = args.since or get_last_sync_date()
    if not since:
        print("❌ 无法确定上次同步日期")
        sys.exit(1)
    until = args.until or datetime.now().strftime("%Y-%m-%d")

    print("═" * 60)
    print("🔄 PlantVirusDB 增量更新引擎 v2")
    print("═" * 60)
    print(f"   时间: {since} → {until}")
    print(f"   模式: {'👁 预览' if args.dry_run else '✍ 完整更新'}")
    if args.skip_taxonomy:
        print(f"   ⚠ 跳过 Taxonomy 同步")

    output_dir = args.output_dir or os.path.join(
        DATA_DIR, "incremental_updates", datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    # ── Phase 0: Taxonomy 同步 ─────────────────────────
    if not args.skip_taxonomy:
        taxsyn_result = taxonomy_sync(args.api_key)
    else:
        taxsyn_result = {'nodes': {}, 'merged': {}, 'deleted': set(), 'new_viral_taxids': []}

    # ── Phase 1: 序列增量获取 ─────────────────────────
    accessions = sequence_delta_fetch(since, until, args.api_key, args.chunk_months)

    if not accessions:
        print("\n✅ 无新增病毒序列")
        update_version(0, -1, until)
        return

    # ── Phase 2: 植物病毒判定 ─────────────────────────
    plant_records = host_resolution(accessions, args.api_key, taxsyn_result)

    if not plant_records:
        print("\n✅ 无新增植物病毒")
        state = load_state()
        state["last_sync_date"] = until
        state["total_runs"] += 1
        save_state(state)
        update_version(0, -1, until)
        return

    # ── Phase 3: 数据库合并 ───────────────────────────
    if args.dry_run:
        print(f"\n👁 [预览] 将新增 {len(plant_records)} 条植物病毒序列")
        for rec in plant_records[:10]:
            print(f"   {rec.get('accession','?'):18s} host={rec.get('host','?')}")
        if len(plant_records) > 10:
            print(f"   ... 还有 {len(plant_records)-10} 条")
        return

    merge_result = database_merge(plant_records, args.api_key, output_dir, taxsyn_result)

    # ── 更新状态 ───────────────────────────────────────
    old_total = 0
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, encoding='utf-8') as f:
            for line in f:
                if line.startswith("RECORDS_TOTAL="):
                    try:
                        old_total = int(line.split("=", 1)[1].strip())
                    except:
                        pass

    new_total = old_total + merge_result["new_tsv"]
    update_version(merge_result["new_tsv"], new_total, until)

    state = load_state()
    state["last_sync_date"] = until
    state["total_runs"] = state.get("total_runs", 0) + 1
    state["total_new_plant_accessions"] = (
        state.get("total_new_plant_accessions", 0) + merge_result["new_tsv"]
    )
    save_state(state)

    elapsed = time.time() - start_time
    print("\n" + "═" * 60)
    print("📊 增量更新完成")
    print("═" * 60)
    print(f"   新增病毒序列:    {len(accessions):,}")
    print(f"   植物病毒命中:    {len(plant_records):,}")
    print(f"   实际写入:       {merge_result['new_fasta']} FASTA + {merge_result['new_tsv']} TSV")
    print(f"   已知继承元数据:  {merge_result.get('known_inherited', 0)}")
    print(f"   taxonkit补全:   {merge_result.get('new_taxonkit', 0)}")
    print(f"   Taxid合并:      {merge_result['merged_updated']}")
    print(f"   Taxid删除:      {merge_result['deleted_marked']}")
    print(f"   数据库总量:      {new_total:,}")
    print(f"   耗时:           {elapsed:.0f}s")
    print(f"\n💡 增量完成。触发去冗余: cd 1.Prepare_plant_virus_pipeline && bash run_all.sh --from F1   # 需在仓库内执行(该参数会强制重跑 F1 及其后步骤)")


if __name__ == "__main__":
    main()
