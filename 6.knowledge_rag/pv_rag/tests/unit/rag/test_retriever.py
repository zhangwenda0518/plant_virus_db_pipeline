from unittest.mock import AsyncMock, MagicMock

import pytest

from neblab_rag.providers.reranker.base import RerankResult
from neblab_rag.rag.retriever import HybridRetriever
from neblab_rag.vector import SearchHit


def _hit(
    *,
    chunk_id: int,
    doc_id: int,
    chunk_index: int = 0,
    title: str,
    text: str,
    oa_id: str,
    score: float,
) -> SearchHit:
    return SearchHit(
        id=chunk_id,
        score=score,
        payload={
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "chunk_index": chunk_index,
            "openalex_id": oa_id,
            "title": title,
            "text": text,
        },
    )


@pytest.mark.asyncio
async def test_retrieve_calls_embed_then_search_then_rerank():
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])

    qdrant = MagicMock()
    qdrant.search.return_value = [
        _hit(chunk_id=10, doc_id=1, title="A", text="abs A", oa_id="W1", score=0.7),
        _hit(chunk_id=20, doc_id=2, title="B", text="abs B", oa_id="W2", score=0.6),
        _hit(chunk_id=30, doc_id=3, title="C", text="abs C", oa_id="W3", score=0.5),
    ]

    rr = MagicMock()
    rr.rerank = AsyncMock(
        return_value=[
            RerankResult(index=2, score=0.95),
            RerankResult(index=0, score=0.8),
        ]
    )

    retriever = HybridRetriever(embedder=embed, qdrant=qdrant, reranker=rr)
    chunks = await retriever.retrieve(query="sand control", top_k=2, candidate_k=3)

    assert len(chunks) == 2
    assert chunks[0].title == "C"  # reranker put index 2 first
    assert chunks[1].title == "A"
    assert chunks[0].chunk_id == 30 and chunks[1].chunk_id == 10

    # Generator needs the chunk text, not just the title.
    assert chunks[0].text == "abs C"
    assert chunks[1].text == "abs A"

    # Reranker should see both title + text so it scores against the
    # actual content, matching what was embedded into Qdrant.
    rr_docs = rr.rerank.call_args.kwargs["documents"]
    assert "A" in rr_docs[0] and "abs A" in rr_docs[0]


@pytest.mark.asyncio
async def test_retrieve_falls_back_to_title_when_text_missing():
    """Defensive: a payload that somehow lacks 'text' still yields a usable
    chunk by falling back to the title (rather than an empty string)."""
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])

    qdrant = MagicMock()
    qdrant.search.return_value = [
        SearchHit(
            id=1,
            score=0.7,
            payload={
                "chunk_id": 1,
                "doc_id": 1,
                "chunk_index": 0,
                "openalex_id": "W1",
                "title": "Only Title Here",
            },
        ),
    ]

    rr = MagicMock()
    rr.rerank = AsyncMock(return_value=[RerankResult(index=0, score=0.9)])

    retriever = HybridRetriever(embedder=embed, qdrant=qdrant, reranker=rr)
    chunks = await retriever.retrieve(query="q", top_k=1, candidate_k=1)

    assert chunks[0].text == "Only Title Here"


@pytest.mark.asyncio
async def test_retrieve_with_bm25_promotes_keyword_match_to_reranker():
    """Sprint 2.5: BM25's exact-keyword hit on a chunk that dense ranked
    last should bubble it up past the dense-favored chunks via RRF."""
    from neblab_rag.rag.bm25_index import BM25Hit

    # Dense ranking: 10 (best), 20, 30 (last)
    dense = [
        _hit(chunk_id=10, doc_id=1, title="A", text="abs A", oa_id="W1", score=0.7),
        _hit(chunk_id=20, doc_id=2, title="B", text="abs B", oa_id="W2", score=0.6),
        _hit(chunk_id=30, doc_id=3, title="C", text="abs C", oa_id="W3", score=0.5),
    ]
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])
    qdrant = MagicMock()
    qdrant.search.return_value = dense

    # BM25 only ranks chunk 30 (the dense laggard) — gives it a sole rank-1 boost
    bm25 = MagicMock()
    bm25.search.return_value = [BM25Hit(chunk_id=30, score=12.0)]

    rr = MagicMock()
    rr.rerank = AsyncMock(return_value=[RerankResult(index=0, score=0.99)])

    retriever = HybridRetriever(embedder=embed, qdrant=qdrant, reranker=rr, bm25=bm25)
    chunks = await retriever.retrieve(query="connectivity hypothesis", top_k=1, candidate_k=3)

    # Sprint 1 v0.2: retriever oversamples (candidate_k × max_chunks_per_doc)
    # so per-doc cap doesn't starve the candidate pool. Default cap=3 → 3×3=9.
    bm25.search.assert_called_once_with("connectivity hypothesis", top_k=9)
    # RRF: 10 gets 1/61, 20 gets 1/62, 30 gets 1/63 + 1/61 ≈ 0.0323 (highest)
    candidate_texts = rr.rerank.call_args.kwargs["documents"]
    assert "C" in candidate_texts[0] and "abs C" in candidate_texts[0]
    assert chunks[0].chunk_id == 30


@pytest.mark.asyncio
async def test_retrieve_caps_chunks_per_doc_in_candidate_pool():
    """Sprint 1 v0.2: a single fulltext doc that produces 100s of chunks
    must not crowd out smaller docs. Cap = 2 → reranker sees max 2 chunks
    from any single doc_id."""
    # Dense returns 5 chunks all from doc_id=1 (mimics dominant fulltext doc),
    # plus 1 chunk each from docs 2, 3, 4
    dense = [
        _hit(chunk_id=10, doc_id=1, title="A1", text="x", oa_id="W1", score=0.9),
        _hit(chunk_id=11, doc_id=1, title="A2", text="x", oa_id="W1", score=0.85),
        _hit(chunk_id=12, doc_id=1, title="A3", text="x", oa_id="W1", score=0.8),
        _hit(chunk_id=13, doc_id=1, title="A4", text="x", oa_id="W1", score=0.75),
        _hit(chunk_id=14, doc_id=1, title="A5", text="x", oa_id="W1", score=0.7),
        _hit(chunk_id=20, doc_id=2, title="B", text="y", oa_id="W2", score=0.65),
        _hit(chunk_id=30, doc_id=3, title="C", text="z", oa_id="W3", score=0.6),
        _hit(chunk_id=40, doc_id=4, title="D", text="w", oa_id="W4", score=0.55),
    ]
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])
    qdrant = MagicMock()
    qdrant.search.return_value = dense
    rr = MagicMock()
    rr.rerank = AsyncMock(return_value=[RerankResult(index=0, score=0.99)])

    retriever = HybridRetriever(embedder=embed, qdrant=qdrant, reranker=rr, max_chunks_per_doc=2)
    await retriever.retrieve(query="q", top_k=1, candidate_k=8)

    candidate_texts = rr.rerank.call_args.kwargs["documents"]
    # After cap=2: doc 1 contributes A1+A2 (top 2 by score), then 2/3/4 each get 1
    # = 5 candidates total instead of 8
    assert len(candidate_texts) == 5
    # docs 2, 3, 4 must all appear (no longer crowded out)
    joined = "\n".join(candidate_texts)
    assert "B" in joined and "C" in joined and "D" in joined
    # Doc 1 must contribute exactly 2 chunks (A1 + A2, NOT A3/A4/A5)
    assert joined.count("A1") == 1
    assert joined.count("A2") == 1
    assert "A3" not in joined and "A4" not in joined and "A5" not in joined


@pytest.mark.asyncio
async def test_retrieve_without_bm25_keeps_dense_only_path():
    """Backward compat: omitting bm25 keeps Sprint-2 behavior unchanged."""
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])
    qdrant = MagicMock()
    qdrant.search.return_value = [
        _hit(chunk_id=1, doc_id=1, title="A", text="x", oa_id="W1", score=0.9)
    ]
    rr = MagicMock()
    rr.rerank = AsyncMock(return_value=[RerankResult(index=0, score=0.9)])

    # No bm25 keyword-arg
    retriever = HybridRetriever(embedder=embed, qdrant=qdrant, reranker=rr)
    chunks = await retriever.retrieve(query="q", top_k=1, candidate_k=1)
    assert chunks[0].chunk_id == 1
