# pyright: reportUnknownMemberType=false, reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""In-memory BM25 sparse index over chunk text.

Switched from ``rank_bm25.BM25Okapi`` to ``bm25s`` (scipy-based) for
~5x faster query time on the 229K-chunk plant virus corpus (33K papers).
Supports disk persistence via ``save()`` / ``load()`` to avoid 30s
rebuild on every pipeline init.
"""

import hashlib
import json
import re
from pathlib import Path

import bm25s
from pydantic import BaseModel

from neblab_rag.logging_config import get_logger

log = get_logger(__name__)


class BM25Hit(BaseModel):
    chunk_id: int
    score: float


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    parts = re.findall(r"[\w]+", text.lower(), flags=re.UNICODE)
    for part in parts:
        buf = ""
        for ch in part:
            if 0x4E00 <= ord(ch) <= 0x9FFF:
                if buf:
                    tokens.append(buf)
                    buf = ""
                tokens.append(ch)
            else:
                buf += ch
        if buf:
            tokens.append(buf)
    return tokens


class BM25Index:
    """Build once, query many. Supports disk persistence via save/load."""

    def __init__(self, corpus_texts: list[str] | None, chunk_ids: list[int]):
        self._corpus_texts = corpus_texts
        self._chunk_ids = chunk_ids
        self._index = None  # bm25s.BM25, lazily built

    @classmethod
    def from_chunks(cls, chunks: list[tuple[int, str]]) -> "BM25Index":
        if not chunks:
            return cls(corpus_texts=None, chunk_ids=[])
        chunk_ids = [c[0] for c in chunks]
        corpus_texts = [c[1] for c in chunks]
        return cls(corpus_texts=corpus_texts, chunk_ids=chunk_ids)

    @classmethod
    def load(
        cls, cache_dir: str | Path, *, expected_chunks: int | None = None
    ) -> "BM25Index | None":
        """Load a persisted BM25S index from disk.

        Returns None if the cache is missing, unreadable, or stale (the caller
        should rebuild via ``from_chunks`` + ``save``).

        Cache invalidation (2026-10-03 audit P1: "缓存永不失效"): ``save()``
        records the corpus size in ``meta.json``; pass ``expected_chunks`` (the
        live ``pv_chunks`` row count, when a DB session is reachable) and a
        cache whose recorded chunk count does not match is rejected here.  A
        re-index that changes the chunk count therefore triggers a rebuild
        instead of silently answering from a stale BM25 snapshot.
        """
        cache_dir = Path(cache_dir)
        meta_path = cache_dir / "meta.json"
        index_dir = cache_dir / "bm25s_index"
        if not meta_path.exists() or not index_dir.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            chunk_ids = meta["chunk_ids"]
            cached_count = meta.get("n_docs")
            if cached_count is None:
                cached_count = len(chunk_ids)
            if expected_chunks is not None and int(cached_count) != int(expected_chunks):
                log.warning(
                    "bm25_cache_stale",
                    cached_chunks=int(cached_count),
                    db_chunks=int(expected_chunks),
                    cache_dir=str(cache_dir),
                )
                return None
            # NOTE(2026-10-03): ``BM25.load`` is a *classmethod* that returns the
            # loaded object (bm25s >= 0.2). The previous `inst = BM25();
            # inst.load(...)` form silently discarded the loaded state with
            # bm25s 0.3.x and every subsequent search raised
            # "AttributeError: 'BM25' object has no attribute 'scores'".
            index = bm25s.BM25.load(str(index_dir), load_corpus=False)
            obj = cls(corpus_texts=None, chunk_ids=chunk_ids)
            obj._index = index
            return obj
        except Exception:
            return None

    def save(self, cache_dir: str | Path) -> None:
        """Persist the BM25S index + chunk_ids to disk for fast reload."""
        if self._index is None:
            # Force build first
            self._ensure_index()
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        index_dir = cache_dir / "bm25s_index"
        self._index.save(str(index_dir))
        meta = {"chunk_ids": self._chunk_ids, "n_docs": len(self._chunk_ids)}
        (cache_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )

    def _ensure_index(self) -> None:
        """Lazily build the index on first search."""
        if self._index is not None or self._corpus_texts is None:
            return
        corpus_tokens = bm25s.tokenization.tokenize(self._corpus_texts)
        self._index = bm25s.BM25()
        self._index.index(corpus_tokens)

    def search(self, query: str, *, top_k: int = 30) -> list[BM25Hit]:
        if self._index is None and self._corpus_texts is None:
            return []
        if not query.strip():
            return []
        self._ensure_index()
        query_tokens = bm25s.tokenization.tokenize([query])
        results, scores = self._index.retrieve(
            query_tokens, k=min(top_k, len(self._chunk_ids)), return_as="tuple"
        )
        hits: list[BM25Hit] = []
        if results.size == 0:
            return hits
        for doc_idx, score in zip(results[0], scores[0]):
            if doc_idx < len(self._chunk_ids) and float(score) > 0:
                hits.append(
                    BM25Hit(chunk_id=self._chunk_ids[doc_idx], score=float(score))
                )
        return hits
