"""Pre-eval sanity: LLM + Qdrant connect, then run 20-case eval."""
import asyncio
import os

# 明文 key 已移除 (2026-10-03)；请从环境变量读取
if not os.environ.get("LLM_API_KEY"):
    raise SystemExit("Set LLM_API_KEY env var first")
os.environ["LLM_DEFAULT_MODEL"] = "deepseek-v4-pro"

import neblab_rag.config

neblab_rag.config.get_settings.cache_clear()

from neblab_rag.providers.factory import build_llm_provider, build_qdrant_repo
from neblab_rag.providers.llm.base import ChatMessage, ChatRequest
from plant_virus_rag.config import get_composite_settings

s = get_composite_settings()
print(f"LLM: model={s.llm.default_model}")
print(f"Qdrant: collection={s.qdrant_collection}")

# Qdrant
repo = build_qdrant_repo(collection=s.qdrant_collection)
repo.ensure_collection()
print("Qdrant: OK")

# LLM
async def test_llm():
    p = build_llm_provider()
    r = await p.chat(
        ChatRequest(
            messages=[ChatMessage(role="user", content="Reply with a single word: ok")],
            temperature=0,
        )
    )
    print(f"LLM: OK -> {r.content[:40].strip()}")

asyncio.run(test_llm())
print("All ready. Run:\n  python -m plant_virus_rag.eval --questions evals/pv_v1/questions.json --label pv-baseline-v4-pro --judge --no-rewriter")
