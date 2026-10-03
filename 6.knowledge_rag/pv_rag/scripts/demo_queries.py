"""Demo: QA + PLANNING + META routing with real queries."""
import asyncio
import time

from plant_virus_rag.rag.pipeline import build_pv_router


async def main() -> None:
    router = build_pv_router(with_rewriter=False, with_bm25=True)

    tests = [
        ("META", "数据库收录了多少病毒？"),
        ("META", "你是谁？"),
        ("QA", "What is the transmission mode of tomato yellow leaf curl virus?"),
        ("QA", "potyvirus genome organization and replication strategy"),
        ("PLANNING", "设计一个番茄黄化曲叶病毒的田间防控方案"),
        ("PLANNING", "How to control whitefly-transmitted geminiviruses in crops?"),
    ]

    for expected, query in tests:
        task = router.classify(query)
        status = "OK" if task.value == expected.lower() else f"WRONG(expected {expected})"

        t0 = time.time()
        text, chunks, answer, ttype = await router.answer(query, top_k=5)
        dt = time.time() - t0

        llm_calls = 0 if ttype.value == "meta" else 1
        print(
            f"[{status}] [{ttype.value.upper():8s}] {dt:.1f}s | "
            f"chunks={len(chunks)} | LLM={llm_calls}x"
        )
        print(f"  Q: {query}")
        preview = text[:150].replace("\n", " ").strip()
        print(f"  A: {preview}...")
        print()


asyncio.run(main())
