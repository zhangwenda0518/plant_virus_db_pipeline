# pyright: reportCallIssue=false, reportArgumentType=false
"""Retrieve + rerank pipeline.

Two retrieval modes share the same dense + sparse + RRF + reranker
pieces; they differ only in how the post-RRF candidate list is
narrowed before reranking:

  * ``HybridRetriever`` (Sprint 2.5/Sprint 1 v0.2): keeps the global
    rank order, caps to ``max_chunks_per_doc`` per doc. Lets every doc
    that has any high-scoring chunk through.

  * ``HierarchicalRetriever`` (Sprint 5 prototype): scores each doc by
    its single best chunk, keeps only the top ``top_docs`` docs, then
    pulls up to ``chunks_per_doc`` chunks from each. Forces diversity
    at the doc level so a fulltext doc with many medium-relevance
    chunks no longer dilutes a per-question abstract doc that happens
    to nail the answer in one chunk.

Payload shape (set by Sprint-2 ChunkIndexer):
  chunk_id, doc_id, chunk_index, openalex_id, title, text,
  year, topic, language

``RetrievedChunk.text`` is the chunk text (stored under payload['text']).

Why RRF (not score normalization): dense cosine and BM25 live on totally
different scales (cosine ∈ [-1,1] vs BM25 unbounded). Score fusion
requires hand-tuning weights; rank fusion is parameter-free except the
constant ``k`` (default 60 from the original RRF paper).
"""

from typing import Protocol

from pydantic import BaseModel

from neblab_rag.providers.embedding.base import EmbeddingProvider
from neblab_rag.providers.reranker.base import RerankerProvider
from neblab_rag.rag.bm25_index import BM25Index
from neblab_rag.vector import QdrantRepo, SearchHit


class RetrievedChunk(BaseModel):
    chunk_id: int
    doc_id: int
    chunk_index: int
    openalex_id: str | None
    title: str
    text: str
    score: float
    search_source: str = ""


def _rerank_doc(payload: dict[str, object]) -> str:
    """Reranker sees source-annotated title + chunk text.

    Prefixing source_type (ictv, openalex, pubmed, etc.) gives the
    cross-encoder a provenance signal it can use to weight results.
    """
    source = str(payload.get("source_type") or "")
    title = str(payload.get("title") or "")
    text = str(payload.get("text") or "")
    prefix = f"[{source}] " if source else ""
    return f"{prefix}{title}\n\n{text}" if text else f"{prefix}{title}"


RRF_K = 60  # reciprocal-rank-fusion constant from the original paper
RRF_DENSE_WEIGHT = 1.0   # weight for dense (vector) rank contribution
RRF_SPARSE_WEIGHT = 1.0  # weight for sparse (BM25) rank contribution

# Sprint 1 v0.2: a single fulltext doc can produce 100s-1000s of chunks
# and dominate the candidate pool against abstract-only docs (which produce
# 1-5 chunks each). Cap how many chunks any one doc contributes to the
# pre-rerank pool so retrieval stays diverse across docs.
DEFAULT_MAX_CHUNKS_PER_DOC = 3

def _oversample_for(_candidate_k: int, _max_per_doc: int) -> int:
    """Scale oversample so large corpora get enough candidate diversity.
    For small collections the multiplier is 1x; for the default plant virus
    corpus (~50k chunks) it is 2x.
    """
    return _candidate_k * _max_per_doc * 2  # 2x for >10k docs corpus


# Sprint 5 hierarchical defaults: keep top-N docs by their best chunk score,
# then pull up to ``chunks_per_doc`` chunks from each. ~5×3=15 candidates
# entering the reranker, which is comparable to flat cap with candidate_k=15.
DEFAULT_TOP_DOCS = 5
DEFAULT_CHUNKS_PER_DOC = 3


def _cap_per_doc(candidates: list[SearchHit], max_per_doc: int) -> list[SearchHit]:
    """Drop chunks beyond ``max_per_doc`` for each doc_id, preserving rank order.

    Operates on the post-RRF candidate list so the cap respects whichever
    chunks scored highest under the combined dense+sparse ranking.
    """
    counts: dict[int, int] = {}
    out: list[SearchHit] = []
    for c in candidates:
        doc_id = int(c.payload.get("doc_id", -1))
        if counts.get(doc_id, 0) >= max_per_doc:
            continue
        out.append(c)
        counts[doc_id] = counts.get(doc_id, 0) + 1
    return out


def _hierarchical_select(
    candidates: list[SearchHit],
    *,
    top_docs: int,
    chunks_per_doc: int,
) -> list[SearchHit]:
    """Two-stage doc-then-chunk selection.

    Stage 1: score each doc by its best chunk's RRF score.
    Stage 2: keep top ``top_docs`` docs (ranked by stage-1 score), then
             from each of those docs take up to ``chunks_per_doc`` chunks
             ordered by score within the doc.

    Order of the output preserves stage-1 doc ranking (best doc first),
    with that doc's chunks consecutive — gives the reranker a structured
    candidate set that's easier to reason about in logs.
    """
    by_doc: dict[int, list[SearchHit]] = {}
    for c in candidates:
        doc_id = int(c.payload.get("doc_id", -1))
        by_doc.setdefault(doc_id, []).append(c)

    # Stage 1: doc score = max chunk score within that doc
    doc_best: list[tuple[int, float]] = sorted(
        ((doc_id, max(h.score for h in hits)) for doc_id, hits in by_doc.items()),
        key=lambda x: -x[1],
    )

    # Stage 2: walk the kept docs, keep their best chunks_per_doc chunks
    out: list[SearchHit] = []
    for doc_id, _ in doc_best[:top_docs]:
        hits = sorted(by_doc[doc_id], key=lambda h: -h.score)[:chunks_per_doc]
        out.extend(hits)
    return out


def _merge_rrf(
    dense: list[SearchHit],
    sparse_chunk_ids: list[int],
    *,
    payloads_by_id: dict[int, dict[str, object]],
) -> list[SearchHit]:
    """Reciprocal rank fusion of dense + sparse rankings.

    sparse_chunk_ids is just the BM25 ranking — the corresponding payloads
    are looked up from ``payloads_by_id`` (which dense already populated;
    chunks unique to BM25 won't have payloads here, so we skip them rather
    than do a second Qdrant fetch — they'll get re-included when the next
    query happens to also retrieve them densely. Acceptable lossiness for
    Sprint-2.5 v0.1.)
    """
    rrf_scores: dict[int, float] = {}
    w_dense = RRF_DENSE_WEIGHT
    w_sparse = RRF_SPARSE_WEIGHT
    for rank, hit in enumerate(dense, start=1):
        rrf_scores[hit.id] = rrf_scores.get(hit.id, 0.0) + w_dense / (RRF_K + rank)
    for rank, cid in enumerate(sparse_chunk_ids, start=1):
        if cid not in payloads_by_id:
            continue  # backfill not done -- skip gracefully
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + w_sparse / (RRF_K + rank)

    sorted_ids = sorted(rrf_scores, key=lambda i: -rrf_scores[i])
    return [
        SearchHit(id=cid, score=rrf_scores[cid], payload=payloads_by_id[cid]) for cid in sorted_ids
    ]


async def _generate_candidates(
    *,
    query: str,
    embedder: EmbeddingProvider,
    qdrant: QdrantRepo,
    bm25: BM25Index | None,
    oversample: int,
) -> list[SearchHit]:
    """Embed query, run dense (Qdrant) + optional sparse (BM25), RRF-merge."""
    [query_vec] = await embedder.embed([query])
    dense_hits = qdrant.search(query_vec, top_k=oversample)
    if bm25 is None:
        return dense_hits
    sparse_hits = bm25.search(query, top_k=oversample)
    sparse_ids = [h.chunk_id for h in sparse_hits]
    payloads_by_id: dict[int, dict[str, object]] = {
        int(h.id): h.payload for h in dense_hits if isinstance(h.id, int)
    }
    # Backfill BM25-only chunk IDs not in dense payload cache
    missing_ids = [cid for cid in sparse_ids if cid not in payloads_by_id]
    if missing_ids:
        fetched = qdrant.fetch_by_ids(missing_ids)
        for fid, fpayload in fetched.items():
            payloads_by_id[fid] = fpayload
    return _merge_rrf(dense_hits, sparse_ids, payloads_by_id=payloads_by_id)


def _to_retrieved_chunk(hit: SearchHit, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=hit.payload.get("chunk_id", -1),
        doc_id=hit.payload.get("doc_id", -1),
        chunk_index=hit.payload.get("chunk_index", 0),
        openalex_id=hit.payload.get("openalex_id"),
        title=hit.payload.get("title", ""),
        text=hit.payload.get("text") or hit.payload.get("title", ""),
        score=score,
        search_source=str(hit.payload.get("source_type", "")),
    )


async def _rerank_to_chunks(
    *,
    query: str,
    candidates: list[SearchHit],
    reranker: RerankerProvider,
    top_k: int,
) -> list[RetrievedChunk]:
    if not candidates:
        return []
    candidate_texts = [_rerank_doc(h.payload) for h in candidates]
    rerank_results = await reranker.rerank(query=query, documents=candidate_texts, top_k=top_k)
    return [_to_retrieved_chunk(candidates[r.index], r.score) for r in rerank_results]


class Retriever(Protocol):
    """Structural type for any retriever the RAGPipeline can use.

    Both ``HybridRetriever`` and ``HierarchicalRetriever`` satisfy it.
    Letting the pipeline depend on this Protocol keeps it open to future
    retrieval strategies without widening its imports.
    """

    async def retrieve(
        self, *, query: str, top_k: int = 12, candidate_k: int = 30
    ) -> list[RetrievedChunk]: ...


class HybridRetriever:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        qdrant: QdrantRepo,
        reranker: RerankerProvider,
        *,
        bm25: BM25Index | None = None,
        max_chunks_per_doc: int = DEFAULT_MAX_CHUNKS_PER_DOC,
    ):
        self._embedder = embedder
        self._qdrant = qdrant
        self._reranker = reranker
        self._bm25 = bm25
        self._max_chunks_per_doc = max_chunks_per_doc

    async def retrieve(
        self, *, query: str, top_k: int = 12, candidate_k: int = 30
    ) -> list[RetrievedChunk]:
        # Pull more dense/sparse candidates than we'll keep — the per-doc cap
        # will prune them down. Without the inflate, after capping 30→~12,
        # we'd starve the reranker of diverse-doc options.
        oversample = _oversample_for(candidate_k, self._max_chunks_per_doc)
        candidates = await _generate_candidates(
            query=query,
            embedder=self._embedder,
            qdrant=self._qdrant,
            bm25=self._bm25,
            oversample=oversample,
        )
        candidates = _cap_per_doc(candidates, self._max_chunks_per_doc)[:candidate_k]
        return await _rerank_to_chunks(
            query=query, candidates=candidates, reranker=self._reranker, top_k=top_k
        )


class HierarchicalRetriever:
    """Doc-level then chunk-level retrieval (Sprint 5 prototype).

    Same dense+sparse+RRF candidate generation as ``HybridRetriever``,
    but the cap step is replaced by a two-stage selector:
      1. Score each doc by its best chunk's RRF score.
      2. Keep top-``top_docs`` docs, then up to ``chunks_per_doc`` chunks
         per kept doc.

    Why this might beat flat cap on a fulltext-heavy corpus: a doc with
    one strong chunk (e.g. a precise abstract) competes on equal footing
    with a doc that has many medium-strong chunks (e.g. mid-paragraph
    fulltext fragments). The flat cap preserves global rank order, which
    can let a fulltext doc with 3 medium chunks edge out an abstract doc
    with 1 great chunk; hierarchical gives the abstract doc its own slot.

    Set ``oversample_factor`` higher than for flat cap because we need
    enough candidates to cover ``top_docs`` × ``chunks_per_doc`` AND
    have enough docs represented at all (a query that returns 50 chunks
    all from the same fulltext doc would otherwise leave hierarchical
    with only 1 doc to pick from).
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        qdrant: QdrantRepo,
        reranker: RerankerProvider,
        *,
        bm25: BM25Index | None = None,
        top_docs: int = DEFAULT_TOP_DOCS,
        chunks_per_doc: int = DEFAULT_CHUNKS_PER_DOC,
        oversample_factor: int = 6,
    ):
        self._embedder = embedder
        self._qdrant = qdrant
        self._reranker = reranker
        self._bm25 = bm25
        self._top_docs = top_docs
        self._chunks_per_doc = chunks_per_doc
        self._oversample_factor = oversample_factor

    async def retrieve(
        self, *, query: str, top_k: int = 12, candidate_k: int = 30
    ) -> list[RetrievedChunk]:
        # candidate_k is interpreted as "chunks the reranker should see".
        # Hierarchical pulls top_docs × chunks_per_doc into rerank, but
        # we still need a wide candidate pool to find ``top_docs`` distinct
        # docs (one fulltext doc can dominate the top-50 hits otherwise).
        base = _oversample_for(candidate_k, self._chunks_per_doc)
        oversample = max(base * self._oversample_factor, self._top_docs * 20)
        candidates = await _generate_candidates(
            query=query,
            embedder=self._embedder,
            qdrant=self._qdrant,
            bm25=self._bm25,
            oversample=oversample,
        )
        candidates = _hierarchical_select(
            candidates,
            top_docs=self._top_docs,
            chunks_per_doc=self._chunks_per_doc,
        )
        return await _rerank_to_chunks(
            query=query, candidates=candidates, reranker=self._reranker, top_k=top_k
        )
