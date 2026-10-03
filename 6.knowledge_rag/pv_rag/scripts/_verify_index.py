import asyncio

from neblab_rag.providers.factory import build_embedding_provider, build_qdrant_repo
from plant_virus_rag.config import get_composite_settings


async def main() -> None:
    s = get_composite_settings()
    repo = build_qdrant_repo(collection=s.qdrant_collection)
    embedder = build_embedding_provider()

    queries = [
        "tomato yellow leaf curl virus transmission",
        "水稻条纹病毒",
        "citrus tristeza virus host range",
    ]
    for q in queries:
        vecs = await embedder.embed([q])
        hits = repo.search(vecs[0], top_k=3)
        print(f"\n[{q}] -> {len(hits)} hits")
        for h in hits:
            print(f"  score={h.score:.4f}  {str(h.payload.get('virus_name',''))[:50]}")


asyncio.run(main())
