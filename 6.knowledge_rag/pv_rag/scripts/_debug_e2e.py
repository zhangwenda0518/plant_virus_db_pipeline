"""Debug E2E: retrieve + generate + judge 3 steps independently."""
import asyncio

from neblab_rag.providers.factory import (
    build_embedding_provider,
    build_llm_provider,
    build_qdrant_repo,
    build_reranker_provider,
)
from neblab_rag.rag.generator import AnswerGenerator, _format_chunks
from neblab_rag.rag.retriever import HybridRetriever
from plant_virus_rag.config import get_composite_settings
from plant_virus_rag.rag.generator import PvAnswerGenerator

async def main() -> None:
    s = get_composite_settings()
    llm = build_llm_provider()
    embedder = build_embedding_provider()
    qdrant = build_qdrant_repo(collection=s.qdrant_collection)
    reranker = build_reranker_provider()

    query = "What is tomato yellow leaf curl virus?"

    # Step 1: retrieval
    retriever = HybridRetriever(embedder=embedder, qdrant=qdrant, reranker=reranker, bm25=None)
    chunks = await retriever.retrieve(query=query, top_k=5)
    print(f"Step 1 - retrieval: {len(chunks)} chunks")
    for c in chunks:
        print(f"  doc={c.doc_id} title={c.title[:60]}")

    # Step 2: generation (pv-specific)
    generator = PvAnswerGenerator(llm=llm)
    try:
        answer = await generator.generate(query=query, chunks=chunks)
        print(f"\nStep 2 - generation OK: {len(answer.content)} chars")
        print(f"  citations: {len(answer.citations)}")
        print(f"  content[:200]: {answer.content[:200]}")
    except Exception as e:
        print(f"\nStep 2 - generation FAILED: {type(e).__name__}: {e}")

    # Step 3: try base neblab generator too (control)
    gen2 = AnswerGenerator(llm=llm)
    answer2 = await gen2.generate(query=query, chunks=chunks)
    print(f"\nStep 3 - base generator OK: {len(answer2.content)} chars")

asyncio.run(main())
