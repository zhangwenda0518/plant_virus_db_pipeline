"""Assemble the plant virus RAG query pipeline.

Reuses neblab_rag infrastructure entirely — only the generator prompt
and Qdrant collection differ.
"""

import os
from pathlib import Path

from neblab_rag.providers.factory import (
    build_embedding_provider,
    build_llm_provider,
    build_qdrant_repo,
    build_reranker_provider,
)
from neblab_rag.rag.bm25_index import BM25Index
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.retriever import HierarchicalRetriever, HybridRetriever
from plant_virus_rag.config import get_composite_settings
from plant_virus_rag.db.models import PvChunk
from plant_virus_rag.db.engine import get_pv_session
from plant_virus_rag.rag.generator import PvAnswerGenerator
from plant_virus_rag.rag.query_rewriter import PvQueryRewriter
from plant_virus_rag.rag.router import PvRouter
from plant_virus_rag.rag.system_info import PvPostgresSystemInfoProvider, PvSystemInfoProvider


# BM25S 缓存目录：旧版是 "./bm25s_cache"（相对启动时 cwd）——从别的目录启
# uvicorn 会静默读写不同缓存甚至重建；现改为基于模块定位的绝对路径
# （<pv_rag>/bm25s_cache，与从 pv_rag 目录启动时的旧行为一致），
# 并支持环境变量 PV_BM25S_CACHE_DIR 覆盖。
BM25S_CACHE_DIR = os.environ.get(
    "PV_BM25S_CACHE_DIR",
    str(Path(__file__).resolve().parents[3] / "bm25s_cache"),
)


def build_pv_bm25_index(*, use_cache: bool = True) -> BM25Index:
    """Snapshot current pv_chunks. Rebuild after re-indexing.

    With ``use_cache=True`` (default), tries to load a persisted BM25S index
    from disk first; the cache is validated against the live ``pv_chunks``
    row count and rejected (→ rebuild) when it is stale.  Falls back to
    rebuilding from Postgres if cache is missing/unusable.
    Use ``pv-ingest bm25-rebuild`` to refresh the cache after re-indexing.
    """
    if use_cache:
        # 与 DB 对账：缓存元数据里的 chunk 数必须等于 pv_chunks 当前行数；
        # 拿不到 DB session 时不做校验（load 内退化为只读缓存）。
        expected_chunks: int | None = None
        try:
            with get_pv_session() as session:
                expected_chunks = int(session.query(PvChunk.id).count())
        except Exception:
            expected_chunks = None
        cached = BM25Index.load(BM25S_CACHE_DIR, expected_chunks=expected_chunks)
        if cached is not None:
            return cached
    with get_pv_session() as session:
        rows = session.query(PvChunk.id, PvChunk.text).all()
    index = BM25Index.from_chunks([(int(r[0]), str(r[1])) for r in rows])
    if use_cache:
        try:
            index.save(BM25S_CACHE_DIR)
        except Exception:
            pass  # cache write failure shouldn't block
    return index


def build_pv_pipeline(
    *,
    with_rewriter: bool = True,
    with_bm25: bool = True,
    hierarchical: bool = False,
) -> RAGPipeline:
    settings = get_composite_settings()
    llm = build_llm_provider()
    embedder = build_embedding_provider()
    qdrant = build_qdrant_repo(collection=settings.qdrant_collection)
    reranker = build_reranker_provider()
    bm25 = build_pv_bm25_index() if with_bm25 else None

    if hierarchical:
        retriever = HierarchicalRetriever(
            embedder=embedder, qdrant=qdrant, reranker=reranker, bm25=bm25,
        )
    else:
        retriever = HybridRetriever(
            embedder=embedder, qdrant=qdrant, reranker=reranker, bm25=bm25,
        )

    return RAGPipeline(
        retriever=retriever,
        generator=PvAnswerGenerator(llm=llm),
        query_rewriter=PvQueryRewriter(llm=llm) if with_rewriter else None,
    )


def build_pv_router(
    *,
    with_rewriter: bool = True,
    with_bm25: bool = True,
    hierarchical: bool = False,
    info_provider: PvSystemInfoProvider | None = None,
) -> PvRouter:
    """Build a PvRouter that classifies queries and dispatches META/QA/PLANNING.

    The router wraps the standard RAG pipeline; META queries skip
    retrieval entirely and return canned system_info answers.
    """
    pipeline = build_pv_pipeline(
        with_rewriter=with_rewriter,
        with_bm25=with_bm25,
        hierarchical=hierarchical,
    )
    if info_provider is None:
        info_provider = PvPostgresSystemInfoProvider()
    return PvRouter(pipeline=pipeline, info_provider=info_provider)
