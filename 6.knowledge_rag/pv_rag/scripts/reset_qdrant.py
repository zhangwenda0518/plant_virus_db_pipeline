"""One-shot: drop Qdrant collection so reindex starts clean."""

from qdrant_client import QdrantClient

from neblab_rag.config import get_settings


def main() -> None:
    s = get_settings()
    client = QdrantClient(url=s.qdrant.url, api_key=s.qdrant.api_key or None, timeout=60)
    name = s.qdrant.collection
    if client.collection_exists(name):
        client.delete_collection(name)
        print(f"deleted: {name}")
    else:
        print(f"absent (no-op): {name}")


if __name__ == "__main__":
    main()
