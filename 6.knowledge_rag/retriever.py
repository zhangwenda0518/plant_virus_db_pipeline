#!/usr/bin/env python3
"""Plant Virus Knowledge Base Retriever — v5 BM25 passage-level retrieval.

Upgrades over the previous keyword-overlap matcher:
  * Documents are split into passages (~1100 chars) so the LLM context
    contains focused excerpts instead of whole-page dumps.
  * BM25 ranking (IDF-weighted, length-normalised) over full doc text,
    not just the first 3000 characters.
  * Acronym awareness: DPV "Species ... | Acronym: XXV" lines build an
    acronym -> species index, so queries like "CaMV" / "TYLCV" retrieve
    the right document directly.
  * Chinese query support: a built-in zh->en plant-virology term map
    expands the query before BM25 (the corpus itself is English).
  * Same-title passages are capped per document to keep context diverse.
"""

import os
import re
import json
import math
from pathlib import Path
from typing import Optional
from collections import Counter, defaultdict

# ---- tokenisation ----------------------------------------------------------

STOPWORDS = set("""
a an and are as at be been being but by can could did do does doing for from
had has have having he her here hers him his how i if in into is it its itself
just me more most my no nor not of on or our ours out over own she should so
some such than that the their theirs them then there these they this those
through to too under until up very was we were what when where which while
who whom why will with would you your yours about after again against all
also any because before below between both during each few further having
itself once only other same s t don now get got give given
""".split())

TOKEN_RE = re.compile(r"[a-z0-9]{2,}")

# zh -> en term map for query expansion (corpus is English)
ZH_TERM_MAP = {
    "烟草花叶病毒": "tobacco mosaic virus", "番茄黄化曲叶病毒": "tomato yellow leaf curl virus",
    "黄瓜花叶病毒": "cucumber mosaic virus", "花椰菜花叶病毒": "cauliflower mosaic virus",
    "马铃薯": "potato", "番茄": "tomato", "烟草": "tobacco", "水稻": "rice",
    "柑橘": "citrus", "苹果": "apple", "葡萄": "grape", "玉米": "maize",
    "小麦": "wheat", "大麦": "barley", "黄瓜": "cucumber", "南瓜": "squash",
    "大豆": "soybean", "辣椒": "pepper", "十字花科": "crucifer",
    "传播方式": "transmission", "传播途径": "transmission", "传播": "transmission",
    "介体": "vector", "媒介": "vector", "昆虫介体": "insect vector",
    "蚜虫": "aphid", "飞虱": "planthopper", "叶蝉": "leafhopper", "粉虱": "whitefly",
    "蓟马": "thrips", "线虫": "nematode", "真菌": "fungus", "螨": "mite",
    "种子传播": "seed transmission", "机械传播": "mechanical transmission",
    "嫁接": "grafting", "寄主范围": "host range", "宿主范围": "host range",
    "寄主": "host", "宿主": "host", "症状": "symptom", "病害": "disease",
    "基因组": "genome", "基因组结构": "genome organization", "复制": "replication",
    "衣壳": "capsid", "外壳蛋白": "coat protein", "编码": "encode",
    "蛋白": "protein", "多聚蛋白": "polyprotein", "亚基因组": "subgenomic",
    "卫星": "satellite", "类病毒": "viroid", "病毒": "virus",
    "正链": "positive-sense", "负链": "negative-sense", "单链": "single-stranded",
    "双链": "double-stranded", "环状": "circular", "线状": "filamentous",
    "杆状": "rod-shaped", "球形": "isometric", "分类": "taxonomy",
    "分类地位": "taxonomy", "属": "genus", "科": "family", "种": "species",
    "血清学": "serology", "检测": "detection", "诊断": "diagnosis",
    "防治": "control", "抗性": "resistance", "流行": "epidemiology",
    "地理分布": "geographical distribution", "序列": "sequence",
    "重组": "recombination", "变异": "variability", "株系": "strain",
    "分离物": "isolate", "汁液": "sap", "稳定": "stability",
    "纯化": "purification", "致死温度": "thermal inactivation point",
}


def _tokens(text):
    return [w for w in TOKEN_RE.findall(text.lower()) if w not in STOPWORDS]


def _zh_segments(text):
    return re.findall(r"[\u4e00-\u9fff]+", text)


def _expand_zh(query):
    """把查询里的中文词映射为英文术语（供 BM25 使用）。"""
    extra = []
    for zh, en in ZH_TERM_MAP.items():
        if zh in query:
            extra.append(en)
    return extra


def _split_passages(text, max_len=1100):
    """按空行切段并合并到约 max_len；超长单段硬切。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    passages, cur = [], ""
    for p in paras:
        if not cur:
            cur = p
        elif len(cur) + len(p) + 2 <= max_len:
            cur = cur + "\n\n" + p
        else:
            passages.append(cur)
            cur = p
        while len(cur) > max_len * 2:
            passages.append(cur[:max_len])
            cur = cur[max_len:]
    if cur:
        passages.append(cur)
    return passages or ([text[:max_len]] if text else [])


# ---- knowledge base --------------------------------------------------------

class PlantVirusKnowledgeBase:
    """植物病毒知识库检索器（BM25 段落级）。"""

    def __init__(self, kb_dir: Optional[str] = None):
        self.kb_dir = Path(kb_dir or os.path.dirname(os.path.abspath(__file__)))
        self._docs: list = []      # {source, path, title, summary, text, type}
        self._fields: list = []    # per-doc Family/Genus/Species/Acronym
        self._passages: list = []  # {doc_id, title, source, text}
        self._tf: list = []        # per-passage Counter
        self._dl: list = []        # per-passage token length
        self._idf: dict = {}
        self._avgdl = 1.0
        self._acronym: dict = {}   # ACRONYM(upper) -> doc title(lower)
        self._titles: list = []    # doc titles, lowercase
        self._loaded = False

    # ---- data loading ----

    def load_all(self, base_dir: Optional[str] = None):
        base = Path(base_dir) if base_dir else self.kb_dir
        self._load_ictv(base / "databases" / "ictv_md")
        self._load_dpv(base / "databases" / "dpv_md")
        self._load_viroid(base / "databases" / "viroiddb.json")
        self._load_papers(base)
        self._load_antivirals(base)
        self._build_index()
        self._loaded = True
        print(f"Knowledge base: {len(self._docs)} docs, "
              f"{len(self._passages)} passages, "
              f"{len(self._acronym)} acronyms indexed")

    def _load_ictv(self, path: Path):
        if not path.exists():
            print(f"  ICTV not found: {path}")
            return
        n0 = len(self._docs)
        for f in sorted(path.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("#")]
            self._docs.append({
                "source": "ICTV", "path": str(f), "title": f.stem,
                "summary": lines[0][:200] if lines else "",
                "text": text[:12000], "type": "taxonomy",
            })
        print(f"  ICTV: {len(self._docs) - n0} docs")

    def _load_dpv(self, path: Path):
        if not path.exists():
            print(f"  DPV not found: {path}")
            return
        n0 = len(self._docs)
        for f in sorted(path.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            self._docs.append({
                "source": "DPV", "path": str(f),
                "title": f.stem.replace("_", " "),
                "summary": "", "text": text[:12000], "type": "plant_virus",
            })
        print(f"  DPV: {len(self._docs) - n0} docs")

    def _load_viroid(self, path: Path):
        if not path.exists():
            print(f"  ViroidDB not found: {path}")
            return
        n0 = len(self._docs)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            items = data.values() if isinstance(data, dict) else data
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("species") or item.get("name") or item.get("accession", "viroid")
                self._docs.append({
                    "source": "ViroidDB", "path": "", "title": str(name),
                    "summary": "", "text": self._viroid_text(item)[:6000],
                    "type": "viroid",
                })
            print(f"  ViroidDB: {len(self._docs) - n0} docs")
        except Exception as e:
            print(f"  ViroidDB error: {e}")

    def _load_papers(self, base: Path):
        """加载文献追踪模块的论文摘要（Papers 源，带 DOI/PMID/物种标注）。

        两个来源，按 PMID 去重（web/data 是周更的现行库，优先级高）：
          data_17cats/ — 2019-2026 近期文献全集备份（8.8k 篇，97% 带病毒/宿主标注）
          web/data/    — 现行文献库（1941-2026，每周更新）
        """
        lit_root = base.parent / "7.literature_tracker" / "web"
        dirs = [lit_root / "data_17cats", lit_root / "data"]
        seen_pmid = set()
        seen_key = set()
        n0 = len(self._docs)
        for dpath in dirs:
            if not dpath.exists():
                print(f"  Papers not found: {dpath}")
                continue
            added = 0
            for f in sorted(dpath.glob("*.json")):
                name = f.stem
                if dpath.name == "data" and not re.fullmatch(r"[12][09]\d\d", name):
                    continue  # 现行库只取年份文件；17cats 目录同理由 glob 限制
                if not re.fullmatch(r"[12][09]\d\d", name):
                    continue
                year = name
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                papers = d if isinstance(d, list) else d.get("papers", [])
                for p in papers:
                    if not isinstance(p, dict):
                        continue
                    pmid = str(p.get("pmid") or "").strip()
                    title = (p.get("title") or "").strip()
                    abstract = (p.get("abstract") or "").strip()
                    if not title and not abstract:
                        continue
                    key = pmid or f"t:{title.lower()[:80]}"
                    if key in seen_pmid or key in seen_key:
                        continue  # 先加载的目录优先
                    seen_key.add(key)
                    if pmid:
                        seen_pmid.add(pmid)
                    meta = []
                    for k, label in (("journal", "Journal"), ("virus_name", "Virus"),
                                     ("host_plant", "Host"), ("first_author", "First author")):
                        v = (p.get(k) or "").strip()
                        if v:
                            meta.append(f"{label}: {v}")
                    sp = (p.get("associated_species") or "").strip()
                    if sp and not (p.get("virus_name") or "").strip():
                        meta.append(f"Virus: {sp[:200]}")
                    text = "\n".join(meta + ["", (abstract or title)[:5000]])
                    self._docs.append({
                        "source": "Papers", "path": str(f),
                        "title": (title[:140] or f"Paper PMID {p.get('pmid', '?')}"),
                        "summary": "", "text": text[:6000], "type": "paper",
                        "doi": (p.get("doi") or "").strip(),
                        "pmid": pmid,
                        "year": year,
                    })
                    added += 1
            print(f"  Papers[{dpath.name}]: +{added} docs (cum {len(self._docs)-n0})")

    def _load_antivirals(self, base: Path):
        """加载抗病毒物质聚合文档（kg inhibited_by 三元组聚合，见 build_antivirals.py）。"""
        path = base.parent / "docs" / "data" / "antivirals.json"
        if not path.exists():
            print(f"  Antivirals not found: {path}")
            return
        n0 = len(self._docs)
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  Antivirals error: {e}")
            return
        for comp in d.get("compounds", []):
            if comp.get("n_viruses", 0) < 1:
                continue
            lines = [f"Antiviral compound: {comp['name']}",
                     f"Inhibits {comp['n_viruses']} plant virus species "
                     f"(from {comp['n_papers']} research papers):"]
            for v in comp.get("viruses", [])[:25]:
                src = f" doi:{v['doi']}" if v.get("doi") else (f" PMID:{v['pmid']}" if v.get("pmid") else "")
                yr = f" ({v['years'][0]})" if v.get("years") else ""
                ev = f" — \"{v['evidence']}\"" if v.get("evidence") else ""
                lines.append(f"- {v['virus']}{yr}{src}{ev}")
            self._docs.append({
                "source": "Antivirals", "path": str(path),
                "title": f"{comp['name']} (antiviral compound)",
                "summary": "", "text": "\n".join(lines)[:6000], "type": "antiviral",
            })
        print(f"  Antivirals: {len(self._docs) - n0} docs")

    @staticmethod
    def _viroid_text(item):
        """把 ViroidDB JSON 条目转成 LLM 友好的可读文本。"""
        order = ["species", "genus", "family", "host", "isolate", "country",
                 "geoLocation", "length", "moleculeType", "sequenceType",
                 "nucCompleteness", "accession", "identicalSeqs", "releaseDate",
                 "submitters", "publications"]
        lines = []
        for k in order:
            v = item.get(k)
            if v not in (None, "", []):
                lines.append(f"{k.replace('_', ' ').capitalize()}: {v}")
        for k, v in item.items():  # 其余字段（跳过序列本身）
            if k in order or k.lower() in ("sequence", "seq"):
                continue
            if v not in (None, "", []):
                lines.append(f"{k.replace('_', ' ').capitalize()}: {v}")
        seq = item.get("sequence") or item.get("seq")
        if seq:
            lines.append(f"Sequence length: {len(seq)} nt")
        return "\n".join(lines)

    # ---- index building ----

    def _build_index(self):
        # per-doc fields + acronym map
        for doc in self._docs:
            fields = {}
            m = re.search(r"#####\s*Species:\s*([^\n|]+?)(?:\s*\|\s*Acronym:\s*([A-Za-z0-9 ,-]+))?\s*$",
                          doc["text"], re.MULTILINE)
            if m:
                fields["Species"] = m.group(1).strip()
                if m.group(2):
                    fields["Acronym"] = m.group(2).strip()
            for pat, name in [(r"#####\s*Family:\s*([^\n]+)", "Family"),
                              (r"#####\s*Genus:\s*([^\n]+)", "Genus")]:
                mm = re.search(pat, doc["text"])
                if mm:
                    fields[name] = mm.group(1).strip()
            mm = re.search(r"Acronym:\s*([A-Z][A-Za-z0-9-]{1,10})", doc["text"])
            if mm and "Acronym" not in fields:
                fields["Acronym"] = mm.group(1)
            self._fields.append(fields)

        self._titles = [doc["title"].lower() for doc in self._docs]

        # passages
        for doc_id, doc in enumerate(self._docs):
            for ptext in _split_passages(doc["text"]):
                self._passages.append({
                    "doc_id": doc_id, "title": doc["title"],
                    "source": doc["source"], "text": ptext,
                })

        # BM25 statistics
        self._tf = [Counter(_tokens(p["text"])) for p in self._passages]
        self._dl = [sum(tf.values()) or 1 for tf in self._tf]
        df = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(self._passages)
        self._idf = {t: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._avgdl = (sum(self._dl) / n) if n else 1.0

        # acronym -> species title
        for doc_id, fields in enumerate(self._fields):
            acr = fields.get("Acronym", "")
            if acr:
                for a in re.split(r"[ ,;/]+", acr):
                    if 2 <= len(a) <= 10:
                        self._acronym.setdefault(a.upper(), self._titles[doc_id])
            # DPV 标题本身通常就是物种名
            sp = fields.get("Species", "")
            if sp:
                for a in re.findall(r"\b([A-Z]{2,6})\b", sp):
                    self._acronym.setdefault(a, self._titles[doc_id])

    # ---- retrieval ----

    def search(self, query: str, top_k: int = 8, per_doc_limit: int = 2) -> list:
        """BM25 段落检索，返回 top_k 个段落（同一文档最多 per_doc_limit 段）。"""
        if not self._loaded or not self._passages:
            return []

        q_tokens = set(_tokens(query))
        for en in _expand_zh(query):
            q_tokens.update(_tokens(en))

        # acronym expansion: 查询里的缩写（TMV / CaMV / TYLCV…）
        boosted_titles = set()
        for w in re.findall(r"[A-Za-z][A-Za-z0-9-]+", query):
            t = self._acronym.get(w.upper())
            if t and (w.isupper() or any(c.isupper() for c in w)):
                boosted_titles.add(t)
                q_tokens.update(_tokens(t))

        # title substring boost: 查询直接包含物种名
        ql = query.lower()
        title_hit = set()
        for i, title in enumerate(self._titles):
            if len(title) > 8 and title in ql:
                title_hit.add(i)

        k1, b = 1.5, 0.75
        scores = defaultdict(float)
        for pid, tf in enumerate(self._tf):
            dl = self._dl[pid]
            doc_id = self._passages[pid]["doc_id"]
            s = 0.0
            for term in q_tokens:
                f = tf.get(term)
                if f:
                    s += self._idf.get(term, 0.0) * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self._avgdl))
            # 实体命中加成：精确物种名 >> 缩写展开 >> 普通 BM25
            if doc_id in title_hit:
                s += 25.0
            if self._titles[doc_id] in boosted_titles:
                s += 10.0
            if s > 0:
                scores[pid] = s

        ranked = sorted(scores.items(), key=lambda x: -x[1])

        results, doc_count = [], Counter()
        for pid, score in ranked:
            p = self._passages[pid]
            if doc_count[p["doc_id"]] >= per_doc_limit:
                continue
            doc_count[p["doc_id"]] += 1
            doc = self._docs[p["doc_id"]]
            item = {
                "title": p["title"],
                "source": p["source"],
                "text": p["text"][:1800],
                "fields": self._fields[p["doc_id"]],
                "score": round(score, 2),
                "doc_id": p["doc_id"],
            }
            for extra in ("doi", "pmid", "year"):
                if doc.get(extra):
                    item[extra] = doc[extra]
            results.append(item)
            if len(results) >= top_k:
                break
        return results

    def search_full_text(self, query: str, top_k: int = 3) -> list:
        """全文模糊搜索兜底。"""
        results = []
        ql = query.lower()
        if not ql:
            return results
        for doc in self._docs:
            text_lower = doc["text"].lower()
            count = text_lower.count(ql)
            if count > 0:
                results.append({
                    "title": doc["title"], "source": doc["source"],
                    "text": doc["text"][:3000], "matches": count,
                })
        results.sort(key=lambda x: (-x["matches"], x["title"]))
        return results[:top_k]


# ---- module-level singleton ----

_kb: Optional[PlantVirusKnowledgeBase] = None


def get_kb(base_dir: Optional[str] = None) -> PlantVirusKnowledgeBase:
    global _kb
    if _kb is None:
        _kb = PlantVirusKnowledgeBase()
        _kb.load_all(base_dir)
    return _kb
