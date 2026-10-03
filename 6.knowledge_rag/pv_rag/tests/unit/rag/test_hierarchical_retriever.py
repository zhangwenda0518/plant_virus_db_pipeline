from unittest.mock import AsyncMock, MagicMock

import pytest

from neblab_rag.providers.reranker.base import RerankResult
from neblab_rag.rag.bm25_index import BM25Hit
from neblab_rag.rag.retriever import HierarchicalRetriever, _hierarchical_select
from neblab_rag.vector import SearchHit


def _hit(*, chunk_id: int, doc_id: int, title: str = "T", text: str = "x", score: float):
    return SearchHit(
        id=chunk_id,
        score=score,
        payload={
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "chunk_index": 0,
            "openalex_id": f"W{doc_id}",
            "title": title,
            "text": text,
        },
    )


def test_hierarchical_select_keeps_top_docs_by_best_chunk():
    """A doc with one strong chunk beats a doc with three medium chunks."""
    candidates = [
        # doc 1: three medium chunks (cumulative-strong but each individually weak)
        _hit(chunk_id=10, doc_id=1, score=0.6),
        _hit(chunk_id=11, doc_id=1, score=0.55),
        _hit(chunk_id=12, doc_id=1, score=0.5),
        # doc 2: one excellent chunk
        _hit(chunk_id=20, doc_id=2, score=0.9),
        # doc 3: one decent chunk
        _hit(chunk_id=30, doc_id=3, score=0.7),
        # doc 4: one weak chunk — should be dropped at top_docs=3
        _hit(chunk_id=40, doc_id=4, score=0.4),
    ]
    out = _hierarchical_select(candidates, top_docs=3, chunks_per_doc=3)

    out_doc_ids = [c.payload["doc_id"] for c in out]
    # Top docs by max score: 2 (0.9), 3 (0.7), 1 (0.6); doc 4 dropped
    assert set(out_doc_ids) == {1, 2, 3}
    assert 4 not in out_doc_ids


def test_hierarchical_select_caps_chunks_per_doc():
    """Even within a kept doc, only the top ``chunks_per_doc`` chunks survive."""
    candidates = [
        _hit(chunk_id=10, doc_id=1, score=0.9),
        _hit(chunk_id=11, doc_id=1, score=0.85),
        _hit(chunk_id=12, doc_id=1, score=0.8),
        _hit(chunk_id=13, doc_id=1, score=0.75),  # 4th — must be dropped
        _hit(chunk_id=14, doc_id=1, score=0.7),  # 5th — must be dropped
    ]
    out = _hierarchical_select(candidates, top_docs=1, chunks_per_doc=3)

    assert len(out) == 3
    assert [c.payload["chunk_id"] for c in out] == [10, 11, 12]


def test_hierarchical_select_orders_output_by_doc_rank():
    """Doc-level ordering is preserved: best doc's chunks come first."""
    candidates = [
        _hit(chunk_id=10, doc_id=1, score=0.5),
        _hit(chunk_id=20, doc_id=2, score=0.95),
        _hit(chunk_id=30, doc_id=3, score=0.7),
    ]
    out = _hierarchical_select(candidates, top_docs=3, chunks_per_doc=1)

    # Doc 2 first (best chunk score), then 3, then 1
    assert [c.payload["doc_id"] for c in out] == [2, 3, 1]


def test_hierarchical_select_empty_input_returns_empty():
    assert _hierarchical_select([], top_docs=5, chunks_per_doc=3) == []


def test_hierarchical_select_handles_fewer_docs_than_top_docs():
    """If only 2 docs are present and top_docs=5, just return both."""
    candidates = [
        _hit(chunk_id=10, doc_id=1, score=0.8),
        _hit(chunk_id=20, doc_id=2, score=0.7),
    ]
    out = _hierarchical_select(candidates, top_docs=5, chunks_per_doc=3)
    assert {c.payload["doc_id"] for c in out} == {1, 2}


@pytest.mark.asyncio
async def test_retrieve_uses_hierarchical_selection_over_flat_cap():
    """Critical scenario: a fulltext doc (id=1) has 5 medium chunks at the
    top of dense ranking; an abstract doc (id=2) has one stronger chunk
    further down. Flat cap=3 would let doc 1 contribute 3 chunks before
    doc 2 even appears; hierarchical with top_docs=2 ensures doc 2 gets
    representation."""
    dense = [
        # Doc 1 (fulltext): 5 medium-strong chunks
        _hit(chunk_id=10, doc_id=1, title="Full", text="m1", score=0.8),
        _hit(chunk_id=11, doc_id=1, title="Full", text="m2", score=0.78),
        _hit(chunk_id=12, doc_id=1, title="Full", text="m3", score=0.76),
        _hit(chunk_id=13, doc_id=1, title="Full", text="m4", score=0.74),
        _hit(chunk_id=14, doc_id=1, title="Full", text="m5", score=0.72),
        # Doc 2 (abstract): 1 chunk that's very strong
        _hit(chunk_id=20, doc_id=2, title="Abs", text="great", score=0.9),
        # Doc 3 (abstract): 1 weaker chunk
        _hit(chunk_id=30, doc_id=3, title="AbsC", text="ok", score=0.65),
    ]
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])
    qdrant = MagicMock()
    qdrant.search.return_value = dense
    rr = MagicMock()
    rr.rerank = AsyncMock(return_value=[RerankResult(index=0, score=0.99)])

    retriever = HierarchicalRetriever(
        embedder=embed,
        qdrant=qdrant,
        reranker=rr,
        top_docs=2,
        chunks_per_doc=3,
    )
    await retriever.retrieve(query="q", top_k=1, candidate_k=10)

    candidate_texts = rr.rerank.call_args.kwargs["documents"]
    joined = "\n".join(candidate_texts)
    # Top docs by best chunk: doc 2 (0.9), doc 1 (0.8). Doc 3 (0.65) drops.
    assert "great" in joined  # doc 2's only chunk
    assert "m1" in joined and "m2" in joined and "m3" in joined  # doc 1's top 3
    assert "ok" not in joined  # doc 3 was edged out by hierarchical selection


@pytest.mark.asyncio
async def test_retrieve_with_bm25_propagates_through_hierarchical():
    """BM25 ranking flows through RRF, then hierarchical_select operates
    on the merged candidates — this verifies the wiring is intact."""
    dense = [
        _hit(chunk_id=10, doc_id=1, title="A", text="abs A", score=0.7),
        _hit(chunk_id=20, doc_id=2, title="B", text="abs B", score=0.6),
        _hit(chunk_id=30, doc_id=3, title="C", text="abs C", score=0.5),
    ]
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])
    qdrant = MagicMock()
    qdrant.search.return_value = dense

    bm25 = MagicMock()
    bm25.search.return_value = [BM25Hit(chunk_id=30, score=12.0)]  # boost C

    rr = MagicMock()
    rr.rerank = AsyncMock(return_value=[RerankResult(index=0, score=0.99)])

    retriever = HierarchicalRetriever(
        embedder=embed, qdrant=qdrant, reranker=rr, bm25=bm25, top_docs=2, chunks_per_doc=1
    )
    await retriever.retrieve(query="connectivity", top_k=1, candidate_k=3)

    # After RRF: chunk 30 (sole BM25 winner) climbs to top.
    # Hierarchical with top_docs=2: docs 3 and one other (the next-best by RRF).
    candidate_texts = rr.rerank.call_args.kwargs["documents"]
    joined = "\n".join(candidate_texts)
    assert "C" in joined  # doc 3 (chunk 30) made it through


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_qdrant_empty():
    """Defensive: empty Qdrant + no BM25 should return [] without calling reranker."""
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])
    qdrant = MagicMock()
    qdrant.search.return_value = []
    rr = MagicMock()
    rr.rerank = AsyncMock()

    retriever = HierarchicalRetriever(embedder=embed, qdrant=qdrant, reranker=rr)
    chunks = await retriever.retrieve(query="q")
    assert chunks == []
    rr.rerank.assert_not_called()
