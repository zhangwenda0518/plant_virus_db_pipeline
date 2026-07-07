#!/usr/bin/env python3
"""Plant Virus Knowledge Base Retriever — 轻量级关键词检索 + 文本匹配"""

import os
import re
import json
from pathlib import Path
from typing import Optional
from collections import defaultdict


class PlantVirusKnowledgeBase:
    """植物病毒知识库检索器。

    从 Markdown/JSON 文件构建内存索引，支持关键词搜索和语义匹配。
    """

    def __init__(self, kb_dir: Optional[str] = None):
        self.kb_dir = Path(kb_dir or os.path.dirname(os.path.abspath(__file__)))
        self._index: dict = {}  # keyword -> [{path, title, text, score}]
        self._docs: list = []  # all documents
        self._loaded = False

    # ---- Data Loading ----

    def load_all(self, base_dir: Optional[str] = None):
        """加载全部知识库。"""
        base = Path(base_dir) if base_dir else self.kb_dir
        self._load_ictv(base / "databases" / "ictv_md")
        self._load_dpv(base / "databases" / "dpv_md")
        self._load_viroid(base / "databases" / "viroiddb.json")
        self._build_index()
        self._loaded = True
        print(f"Knowledge base: {len(self._docs)} documents indexed")

    def _load_ictv(self, path: Path):
        if not path.exists():
            print(f"  ICTV not found: {path}")
            return
        for f in sorted(path.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            title = f.stem
            # Extract first meaningful line as summary
            lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("#")]
            summary = lines[0][:200] if lines else ""
            self._docs.append({
                "source": "ICTV",
                "path": str(f),
                "title": title,
                "summary": summary,
                "text": text[:8000],  # truncate very long docs
                "type": "taxonomy"
            })
        print(f"  ICTV: {len(self._docs)} docs")

    def _load_dpv(self, path: Path):
        if not path.exists():
            print(f"  DPV not found: {path}")
            return
        for f in sorted(path.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            title = f.stem.replace("_", " ")
            lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("#")]
            summary = lines[0][:200] if lines else ""
            self._docs.append({
                "source": "DPV",
                "path": str(f),
                "title": title,
                "summary": summary,
                "text": text[:8000],
                "type": "plant_virus"
            })
        print(f"  DPV: loaded")

    def _load_viroid(self, path: Path):
        if not path.exists():
            print(f"  ViroidDB not found: {path}")
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    name = item.get("name", item.get("species", ""))
                    text = json.dumps(item, ensure_ascii=False, indent=2)
                    self._docs.append({
                        "source": "ViroidDB",
                        "title": str(name),
                        "text": text[:8000],
                        "type": "viroid"
                    })
            elif isinstance(data, dict):
                for key, val in data.items():
                    text = json.dumps(val, ensure_ascii=False, indent=2)
                    self._docs.append({
                        "source": "ViroidDB",
                        "title": str(key),
                        "text": text[:8000],
                        "type": "viroid"
                    })
            print(f"  ViroidDB: loaded")
        except Exception as e:
            print(f"  ViroidDB error: {e}")

    # ---- Index Building ----

    def _build_index(self):
        """构建关键词倒排索引。"""
        self._index = defaultdict(list)
        for i, doc in enumerate(self._docs):
            text = f"{doc['title']} {doc.get('summary','')} {doc['text'][:3000]}".lower()
            words = set(re.findall(r"[a-zA-Z]{3,}|\d+", text))
            for w in words:
                self._index[w].append({"doc_id": i, "title": doc["title"]})

    # ---- Text Cleaning ----

    @staticmethod
    def _clean_text(text):
        """清理 Markdown，提取结构信息。"""
        # Strip DPV boilerplate header
        text = re.sub(r'^## Details of DPV[^#]*', '', text, flags=re.DOTALL)
        text = re.sub(r'\*\*[^*]+\*\*', '', text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Extract key fields
        fields = {}
        for pattern, name in [
            (r'Family:\s*(\S[^\n]*)', 'Family'),
            (r'Genus:\s*(\S[^\n]*)', 'Genus'),
            (r'Species:\s*(\S[^\n]*)', 'Species'),
            (r'Acronym:\s*(\S[^\n]*)', 'Acronym'),
        ]:
            m = re.search(pattern, text)
            if m and name not in fields:
                fields[name] = m.group(1).strip()
        return text.strip(), fields

    # ---- Retrieval ----

    def search(self, query: str, top_k: int = 5) -> list:
        """关键词搜索，返回 top_k 相关文档。"""
        if not self._loaded:
            return []

        query_lower = query.lower()
        query_words = set(re.findall(r"[a-z0-9]{2,}", query_lower))

        # Score by keyword overlap
        scores: dict[int, float] = defaultdict(float)
        for w in query_words:
            if w in self._index:
                for entry in self._index[w]:
                    scores[entry["doc_id"]] += 1.0 / len(query_words)

        # Boost by title match
        for i, doc in enumerate(self._docs):
            title_lower = doc["title"].lower()
            for w in query_words:
                if w in title_lower.replace("_", " "):
                    scores[i] += 2.0 / len(query_words)

        # Also check Chinese characters
        chinese_chars = re.findall(r"[\u4e00-\u9fff]+", query)
        if chinese_chars:
            for i, doc in enumerate(self._docs):
                for ch in chinese_chars:
                    if ch in doc.get("text", ""):
                        scores[i] += 0.5

        # Sort and return top_k
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k * 2]
        results = []
        seen = set()
        for doc_id, score in ranked:
            doc = self._docs[doc_id]
            key = doc["title"]
            if key not in seen:
                seen.add(key)
                clean_text, fields = self._clean_text(doc["text"][:3000])
                results.append({
                    "title": doc["title"],
                    "source": doc["source"],
                    "text": clean_text[:2000],
                    "fields": fields,
                    "score": round(score, 2),
                })
            if len(results) >= top_k:
                break
        return results

    def search_full_text(self, query: str, top_k: int = 3) -> list:
        """全文模糊搜索——直接在全部文档文本中 grep。"""
        results = []
        query_lower = query.lower()
        for doc in self._docs:
            text_lower = doc["text"].lower()
            count = text_lower.count(query_lower)
            if count > 0:
                results.append({
                    "title": doc["title"],
                    "source": doc["source"],
                    "text": doc["text"][:3000],
                    "matches": count,
                })
        results.sort(key=lambda x: (-x["matches"], x["title"]))
        return results[:top_k]


# ---- Module-level singleton ----
_kb: Optional[PlantVirusKnowledgeBase] = None


def get_kb(base_dir: Optional[str] = None) -> PlantVirusKnowledgeBase:
    global _kb
    if _kb is None:
        _kb = PlantVirusKnowledgeBase()
        _kb.load_all(base_dir)
    return _kb
