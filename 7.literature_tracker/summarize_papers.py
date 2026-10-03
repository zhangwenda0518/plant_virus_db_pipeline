#!/usr/bin/env python3
"""AI summarization for plant virus papers — 7-field Chinese extraction via LLM."""
import json, os, sys, time, argparse
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from config import (
    PAPERS_JSON, DAILY_DIR, DATA_DIR, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_DELAY,
)

# The 13 extraction fields (single source of truth for the write-back loops).
AI_FIELDS = ("virus_name", "taxonomy", "symptoms", "host_plant", "location",
             "sample_date", "vector", "transmission", "overview", "methods",
             "results", "discussion", "is_review")

# Failed summarization attempts are appended here (never silently swallowed).
FAILURES_TSV = DATA_DIR / "ai_failures.tsv"


def is_pending_for_ai(p: dict) -> bool:
    """A paper that still needs AI extraction: not done, has an abstract, has a PMID.

    Selection is deliberately driven by the *pending state* only. `year` must never
    drive selection (display ordering only): the old "newest N papers" truncation
    swept in already-summarized papers, so the weekly auto run summarized 0 papers
    out of hundreds of pending ones (audit D4, 2026-10-03).
    """
    return (
        not p.get("ai_done")
        and bool((p.get("abstract") or "").strip())
        and bool((p.get("pmid") or "").strip())
    )


def select_pending_papers(papers: list, limit: int = None) -> list:
    """Pending papers (see `is_pending_for_ai`), newest first, capped at `limit`.

    The sort is for display/processing order only — it cannot admit an
    already-summarized paper into the selection.
    """
    pending = [p for p in papers if is_pending_for_ai(p)]
    pending.sort(key=lambda x: (x.get("year", 0) or 0, x.get("pub_date", "") or ""),
                 reverse=True)
    if limit is not None:
        pending = pending[:limit]
    return pending

SYSTEM_PROMPT = """你是植物病毒学论文信息抽取助手。

根据给定的英文标题和摘要，提取以下字段。全部使用中文（病毒名/物种拉丁名/缩写可保留英文）。
严格要求（非常重要）：
- 仅根据给定的标题和摘要文本提取，不得使用文本外的任何信息，不得推测
- 如果某项信息在文本中没有明确提及，则该字段填写"未提及"
- 填写尽量简洁准确

提取字段（重点关注新病毒发现的关键信息）：
1. virus_name: 研究涉及的病毒名称（若为新病毒，给出其命名/暂定名，含缩写）
2. taxonomy: 病毒分类地位（目/科/属/种，如 Geminiviridae, Begomovirus）
3. symptoms: 植物表现的症状（如黄化、曲叶、花叶、坏死、矮化等）
4. host_plant: 宿主植物（学名或俗名）
5. location: 采样/发现的地理位置（国家、地区）
6. sample_date: 采样时间或年份
7. vector: 传播媒介生物（如烟粉虱、蚜虫、蓟马等），无则填"未提及"
8. transmission: 传播方式（介体传播、种传、机械传播、嫁接等）
9. overview: 研究概况与背景介绍，不超过80字
10. methods: 主要研究方法（如高通量测序、RT-PCR、系统发育分析等），不超过60字
11. results: 主要研究结果与发现，不超过100字
12. discussion: 讨论要点、意义或结论，不超过80字
13. is_review: 判断该论文是否为综述（review article）。根据标题和摘要中是否包含"review"、"overview"、"survey"、"meta-analysis"、"systematic review"等词汇，或内容是否以文献综述为主。返回"综述"或"研究论文"

返回严格的 JSON 格式（不要包含 markdown 代码块标记）:
{"virus_name":"...","taxonomy":"...","symptoms":"...","host_plant":"...","location":"...","sample_date":"...","vector":"...","transmission":"...","overview":"...","methods":"...","results":"...","discussion":"...","is_review":"..."}"""


DIGEST_PROMPT = """你是植物病毒学领域的文献分析专家。

根据给定的这一{period}内的植物病毒论文标题列表，撰写一篇详细的中文研究动态综述（300-500字）。
要求：
- 按主题归类（如：新病毒发现、检测方法、病毒-宿主互作、抗性基因、传播与流行病学、生防与治理等），每个主题一段
- 每段引用 2-3 篇具体论文（用"[标题]"格式引用），简述其核心发现
- 特别关注新病毒/新物种报道、重要抗性/检测方法进展
- 提炼 2-3 个值得关注的研究趋势作为结尾
- 语言专业、客观，信息密度高，避免空洞泛泛而谈
- 直接输出综述段落，不需要整体标题、不要 markdown 标记

论文列表："""


def _llm_call(messages, model, base_url, api_key, max_tokens=600, timeout=90):
    """Single OpenAI-compatible chat completion call."""
    base = (base_url or LLM_BASE_URL or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    payload = json.dumps({
        "model": model or LLM_MODEL or "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.3, "max_tokens": max_tokens,
    }).encode()
    req = Request(url, data=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    with urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"].strip()


def summarize_digest(papers: list, period: str = "周", model: str = None,
                     base_url: str = None, api_key: str = None) -> str:
    """Generate a narrative Chinese digest paragraph over a set of papers.

    period: '周' or '月' (used in the prompt). Returns '' if no API key or on error.
    """
    model = model or LLM_MODEL
    base_url = base_url or LLM_BASE_URL
    api_key = api_key or LLM_API_KEY

    if not api_key or not papers:
        return ""

    # Build title list (cap at 60 to control token cost)
    titles = []
    for p in papers[:60]:
        t = p.get("title", "").strip()
        cats = "/".join(p.get("categories", [])[:2])
        if t:
            titles.append(f"- [{cats}] {t}")
    if not titles:
        return ""

    user_msg = DIGEST_PROMPT.format(period=period) + "\n" + "\n".join(titles)
    try:
        return _llm_call(
            [{"role": "user", "content": user_msg}],
            model or LLM_MODEL, base_url or LLM_BASE_URL, api_key or LLM_API_KEY,
            max_tokens=1200,
        )
    except Exception as e:
        import traceback
        print(f"  Digest LLM error: {e}")
        traceback.print_exc()
        return ""


def _parse_json_lenient(content: str) -> dict:
    """Robustly parse a possibly-messy JSON object from LLM output."""
    import re
    content = content.strip()
    # Try direct parse
    try:
        return json.loads(content)
    except Exception:
        pass
    # Extract first {...} block
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        blob = content[start:end + 1]
        try:
            return json.loads(blob)
        except Exception:
            pass
        # Escape raw newlines inside the blob and retry
        try:
            fixed = blob.replace("\n", "\\n").replace("\r", "")
            return json.loads(fixed)
        except Exception:
            pass
        # Field-by-field regex extraction as last resort
        fields = ("virus_name", "taxonomy", "symptoms", "host_plant", "location",
                  "sample_date", "vector", "transmission", "overview",
                  "methods", "results", "discussion")
        result = {}
        for f in fields:
            m = re.search(r'"' + f + r'"\s*:\s*"((?:[^"\\]|\\.)*)"', blob)
            if m:
                result[f] = m.group(1).replace('\\"', '"').replace("\\n", " ")
        if result:
            return result
    return {}


def _clean_cell(value, limit: int = 300) -> str:
    """One-line, tab-safe TSV cell."""
    s = str(value if value is not None else "")
    for ch in ("\t", "\n", "\r"):
        s = s.replace(ch, " ")
    return s.strip()[:limit]


def log_ai_failures(rows: list, path=None):
    """Append failed summarization attempts to ai_failures.tsv.

    rows: (time, pmid, title, stage, reason).
    A failure must never be written back as a fake 'summarized' paper: the paper
    stays pending (ai_done falsy) and gets an `ai_error` field, so it is retried
    on the next run instead of being permanently corrupted (audit D4).
    """
    if not rows:
        return
    path = Path(path or FAILURES_TSV)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not path.exists()
        with open(path, "a", encoding="utf-8", newline="") as f:
            if new_file:
                f.write("time\tpmid\ttitle\tstage\treason\n")
            for ts, pmid, title, stage, reason in rows:
                f.write(f"{_clean_cell(ts, 32)}\t{_clean_cell(pmid, 40)}\t"
                        f"{_clean_cell(title, 120)}\t{_clean_cell(stage, 40)}\t"
                        f"{_clean_cell(reason)}\n")
        print(f"  {len(rows)} failure(s) appended to {path}")
    except Exception as e:
        print(f"  WARNING: could not write failure log {path}: {e}")


def summarize_papers(papers: list, model: str = None, base_url: str = None,
                     api_key: str = None, delay: float = None, force: bool = False,
                     save_cb=None, save_every: int = 25):
    """Generate AI summaries for papers without ai_done=True.

    Failure policy (audit D4, 2026-10-03): a paper is marked ai_done=True ONLY when
    a parseable 13-field result came back. On parse failure / exhausted API retries
    the paper keeps ai_done falsy, gets an `ai_error` field, and the attempt is
    appended to ai_failures.tsv.
    """
    model = model or LLM_MODEL
    base_url = base_url or LLM_BASE_URL
    api_key = api_key or LLM_API_KEY
    delay = delay or LLM_DELAY
    url = f"{base_url.rstrip('/')}/chat/completions"

    if not api_key:
        # Refuse to fabricate "未提及" placeholders with ai_done=True: that
        # silently marked unsummarized papers as done and was not self-healing.
        print("ERROR: LLM_API_KEY is not set — refusing to write placeholder summaries.",
              file=sys.stderr)
        print("       Export LLM_API_KEY (see config.py) and re-run.", file=sys.stderr)
        raise SystemExit(2)

    pending = [p for p in papers if force or not p.get("ai_done")]
    total = len(pending)
    print(f"Summarizing {total} papers (model={model})...")

    failures = []
    for i, paper in enumerate(pending):
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        pmid = paper.get("pmid", "?")
        if not abstract and not title:
            reason = "no title/abstract in record — nothing to extract from"
            paper["ai_error"] = reason
            failures.append((datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             pmid, title, "no_text", reason))
            print(f"  Skip PMID={pmid}: no title/abstract")
            continue

        user_msg = f"标题: {title}\n\n摘要: {abstract}"
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.0,
        }).encode()

        handled = False  # True once success or a recorded failure
        last_err = ""
        # Retry loop with exponential backoff for rate limits
        for attempt in range(5):
            try:
                req = Request(url, data=payload, headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                })
                with urlopen(req, timeout=90) as resp:
                    if resp.status == 429:
                        wait = 2 ** attempt + 1
                        print(f"  Rate-limited, waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    result = json.loads(resp.read())
                    content = result["choices"][0]["message"]["content"]
                    content = content.strip()
                    if content.startswith("```"):
                        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
                    ai = _parse_json_lenient(content)
                    if not ai:
                        # Do NOT mark done and do NOT write "未提及" placeholders.
                        reason = f"parse_failed: {_clean_cell(content, 200)}"
                        paper["ai_error"] = reason
                        failures.append((datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                         pmid, title, "parse", reason))
                        print(f"  Parse error PMID={pmid}: {_clean_cell(content, 80)}...")
                        handled = True
                        break
                    for fld in AI_FIELDS:
                        paper[fld] = ai.get(fld, "未提及")
                    paper["ai_done"] = True
                    paper.pop("ai_error", None)
                    handled = True
                    break  # success
            except Exception as e:
                last_err = f"{type(e).__name__}: {_clean_cell(e, 200)}"
                if "429" in str(e) or "Too Many" in str(e):
                    wait = 2 ** attempt + 1
                    print(f"  Rate-limited (429), waiting {wait}s...")
                    time.sleep(wait)
                elif attempt < 4:
                    time.sleep(1)
        if not handled:
            reason = f"api_error after 5 attempts: {last_err}"
            paper["ai_error"] = reason
            failures.append((datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             pmid, title, "api", reason))
            print(f"  ERR PMID={pmid}: {_clean_cell(last_err, 80)}")

        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{total} ...")

        # Periodic progress save (crash-safe for long runs)
        if save_cb and (i + 1) % save_every == 0:
            save_cb()

        time.sleep(delay)

    log_ai_failures(failures)
    if failures:
        print(f"Done: {total - len(failures)}/{total} summarized, "
              f"{len(failures)} failed (kept pending; see {FAILURES_TSV.name})")


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

    # Select subset to summarize but keep the full list intact for saving
    subset = papers
    if args.pmids:
        pmid_set = set(args.pmids)
        subset = [p for p in papers if p.get("pmid") in pmid_set]
    if args.max_papers:
        if args.force:
            subset = sorted(papers, key=lambda x: (x.get("year", 0) or 0,
                                                  x.get("pub_date", "") or ""),
                            reverse=True)[:args.max_papers]
        else:
            subset = select_pending_papers(papers, limit=args.max_papers)

    # Save-progress callback: subset items are references into `papers`,
    # so mutating them updates the master list. Persist periodically.
    def save():
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    summarize_papers(subset, args.model, args.base_url, args.api_key,
                     args.delay, args.force, save_cb=save, save_every=25)

    save()  # final save (full papers list preserved)

    done = sum(1 for p in papers if p.get("ai_done"))
    print(f"Done: {done}/{len(papers)} papers have AI summary → {out_path}")


if __name__ == "__main__":
    main()
