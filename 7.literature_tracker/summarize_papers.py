#!/usr/bin/env python3
"""AI summarization for plant virus papers — 7-field Chinese extraction via LLM."""
import json, os, sys, time, argparse
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from config import (
    PAPERS_JSON, DAILY_DIR, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_DELAY,
)

SYSTEM_PROMPT = """你是植物病毒学论文信息抽取助手。

根据给定的英文标题和摘要，提取以下字段。全部使用中文。
严格要求（非常重要）：
- 仅根据给定的标题和摘要文本提取，不得使用文本外的任何信息，不得推测
- 如果某项信息在文本中没有明确提及，则该字段填写"未提及"
- 填写尽量简洁明了

提取字段：
1. summary_zh: 一句话中文概述研究目的、方法和核心结论，不超过60字
2. innovation: 论文的主要创新点，用竖线分隔（如"创新1|创新2"），不超过3项
3. limitation: 研究局限性或不足，用竖线分隔，不超过2项
4. study_object: 研究涉及的宿主植物、病毒物种、样本类型、实验技术
5. disease: 研究的植物病害名称（如烟草花叶病、番茄黄化曲叶病等）
6. sample_size: 样本量（如明确提及数量、地块数、重复数等）
7. method_zh: 主要研究方法简述，中文，不超过80字
8. contributions: 论文的核心学术贡献，数组格式，2-3项，每项不超过30字

返回严格的 JSON 格式（不要包含 markdown 代码块标记）:
{"summary_zh":"...","innovation":"...","limitation":"...","study_object":"...","disease":"...","sample_size":"...","method_zh":"...","contributions":["...","..."]}"""


def summarize_papers(papers: list, model: str = None, base_url: str = None,
                     api_key: str = None, delay: float = None, force: bool = False):
    """Generate AI summaries for papers without ai_done=True."""
    model = model or LLM_MODEL
    base_url = base_url or LLM_BASE_URL
    api_key = api_key or LLM_API_KEY
    delay = delay or LLM_DELAY
    url = f"{base_url.rstrip('/')}/chat/completions"

    if not api_key:
        print("WARNING: No LLM_API_KEY set — summaries will be placeholders")
        for p in papers:
            if force or not p.get("ai_done"):
                p["summary_zh"] = "(pending)"
                p["innovation"] = "未提及"
                p["limitation"] = "未提及"
                p["study_object"] = "未提及"
                p["disease"] = "未提及"
                p["sample_size"] = "未提及"
                p["method_zh"] = "未提及"
                p["contributions"] = ["未提及"]
                p["ai_done"] = True
        return

    pending = [p for p in papers if force or not p.get("ai_done")]
    total = len(pending)
    print(f"Summarizing {total} papers (model={model})...")

    for i, paper in enumerate(pending):
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        pmid = paper.get("pmid", "?")
        if not abstract and not title:
            continue

        user_msg = f"标题: {title}\n\n摘要: {abstract}"
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.0,
            "max_tokens": 500,
        }).encode()

        try:
            req = Request(url, data=payload, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            })
            with urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                content = result["choices"][0]["message"]["content"]
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0]
                try:
                    ai = json.loads(content)
                except json.JSONDecodeError:
                    print(f"  Parse error PMID={pmid}: {content[:80]}...")
                    ai = {}
                paper["summary_zh"] = ai.get("summary_zh", "未提及")
                paper["innovation"] = ai.get("innovation", "未提及")
                paper["limitation"] = ai.get("limitation", "未提及")
                paper["study_object"] = ai.get("study_object", "未提及")
                paper["disease"] = ai.get("disease", "未提及")
                paper["sample_size"] = ai.get("sample_size", "未提及")
                paper["method_zh"] = ai.get("method_zh", "未提及")
                paper["contributions"] = ai.get("contributions", ["未提及"])
                paper["ai_done"] = True
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{total} ...")
        except Exception as e:
            print(f"  ERR PMID={pmid}: {e}")

        time.sleep(delay)


def main():
    p = argparse.ArgumentParser(description="Generate AI summaries for plant virus papers")
    p.add_argument("--input", default=str(PAPERS_JSON), help="Input papers.json")
    p.add_argument("--output", default=None, help="Output (defaults to input)")
    p.add_argument("--model", default=None, help="LLM model override")
    p.add_argument("--base-url", default=None, help="API base URL override")
    p.add_argument("--api-key", default=None, help="API key")
    p.add_argument("--force", action="store_true", help="Re-summarize even if ai_done=True")
    p.add_argument("--delay", type=float, default=None, help="Delay between requests")
    p.add_argument("--max-papers", type=int, default=None, help="Limit number of papers")
    p.add_argument("--pmids", nargs="+", default=None, help="Summarize specific PMIDs")
    args = p.parse_args()

    out_path = Path(args.output or args.input)
    if not Path(args.input).exists():
        print(f"No input file: {args.input}")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    papers = data.get("papers", [])
    if args.pmids:
        pmid_set = set(args.pmids)
        papers = [p for p in papers if p.get("pmid") in pmid_set]

    if args.max_papers:
        # Prioritize newest
        papers.sort(key=lambda x: x.get("year", 0) or 0, reverse=True)
        papers = papers[:args.max_papers]

    summarize_papers(papers, args.model, args.base_url, args.api_key, args.delay, args.force)
    data["papers"] = papers

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    done = sum(1 for p in papers if p.get("ai_done"))
    print(f"Done: {done}/{len(papers)} papers summarized → {out_path}")


if __name__ == "__main__":
    main()
