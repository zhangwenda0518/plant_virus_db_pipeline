#!/usr/bin/env python3
"""
build_vector_db.py — Virus-Vector-Host 服务端预合并管线

将两个来源合并为统一的 virus_vector_merged.json，供 /vector/ 服务和
Virus Explorer 的「媒介传播」标签页直接读取：

  1. virus_vector_host.tsv (VH)  — 实验验证的 病毒×媒介×宿主 三元组，
                                    含 TaxID、受控传播方式词汇、DOI、Lineage。主干源。
  2. wur_virus_full.tsv    (WUR) — WUR 文献抓取的病毒级补充，含粗媒介标签、
                                    自由文本传播说明、参考文献。补充源（无 TaxID）。
  3. name_mapping.tsv            — ICTV/NCBI 别名·缩写映射，仅作匹配桥。

设计要点（吸取抽检教训）：
  * 合并单元 = 病毒，主键 = VH 原始病毒名（= NCBI/Explorer 用名），**不改写**，
    以保证与 Virus Explorer 的 Organism 精确 join。name_mapping 只用于 WUR↔VH 匹配。
  * WUR → VH 自动匹配仅两种（均记 high 置信）：
      ① 归一化名精确相等
      ② 双方经 name_mapping 归一到同一 ICTV 名
    **模糊匹配不自动合并**，只作为人工建议写入 review.tsv，避免把 GPV/RPV 等
    不同病毒错并。
  * VH 三元组按 (vector, host, transmission_mode) 去重。
  * 冲突仅标 family_mismatch（VH.family ≠ WUR.family），且只在高置信匹配上比较。
"""

import csv
import json
import re
import argparse
from pathlib import Path
from datetime import date
from difflib import SequenceMatcher

csv.field_size_limit(10_000_000)  # WUR refs 单元格极大

FUZZY_THRESHOLD = 0.90  # 仅用于生成人工 review 建议，不自动合并

# WUR「Modes of transmission」受控传播途径词表(与 VH 的昆虫传毒机制正交)
ROUTE_VOCAB = [
    "sap transmissible", "not sap transmissible",
    "seed borne", "not seed borne",
    "soil borne", "water borne", "vegetative propagation",
]


def parse_routes(modes_text: str) -> list:
    """WUR Modes of transmission 文本 → 受控传播途径列表。"""
    out = []
    for term in re.split(r"[;,]", modes_text or ""):
        t = term.strip().lower()
        if t in ROUTE_VOCAB and t not in out:
            out.append(t)
    return out


def parse_vector_categories(vector_org: str) -> list:
    """WUR Vector organism 文本 → 粗媒介类别列表(含非昆虫: Nematode/Fungus 等)。"""
    out = []
    for term in re.split(r"[;,]", vector_org or ""):
        t = term.strip()
        if t and t not in out:
            out.append(t)
    return out


# ── 名称归一化与映射 ────────────────────────────────────────────
def norm(s: str) -> str:
    """归一化：小写、折叠空白、去尾部标点。"""
    s = (s or "").strip().lower()
    s = " ".join(s.split())
    return s.strip(".,;")


def load_name_map(path: Path) -> dict:
    """构建 归一化键 → ICTV_Name 的映射（别名/缩写/常用名都指向 ICTV 名）。"""
    canon = {}
    if not path.exists():
        return canon
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ictv = (row.get("ICTV_Name", "") or "").strip()
            if not ictv:
                continue
            for col in ("Lookup_Key", "ICTV_Name", "Common_Name", "Abbreviation"):
                k = norm(row.get(col, ""))
                if k and k not in canon:
                    canon[k] = ictv
    return canon


def ictv_of(name: str, canon: dict) -> str:
    """返回该名字经 name_mapping 归一到的 ICTV 名（无命中则空串）。"""
    return canon.get(norm(name), "")


# ── 传播方式简化分类（供 Explorer 画图） ────────────────────────
def transmission_category(mode: str) -> str:
    m = (mode or "").lower()
    if not m or m == "na":
        return "Unknown"
    if "non-persistent" in m or "non persistent" in m:
        return "Non-Persistent"
    if "semi-persistent" in m or "semi persistent" in m:
        return "Semi-Persistent"
    if "propagative" in m and "non-propagative" not in m and "non propagative" not in m:
        return "Persistent-Propagative"
    if "non-propagative" in m or "non propagative" in m:
        return "Persistent Non-Propagative"
    if "circulative" in m or "persistent" in m:
        return "Persistent (circulative)"
    return "Other"


# ── 数据加载 ────────────────────────────────────────────────────
def load_vh(path: Path, canon: dict) -> dict:
    """按 VH 原始病毒名聚合三元组（去重）。返回 病毒名 -> 记录。"""
    viruses = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            name = (row.get("Virus Name", "") or "").strip()
            if not name:
                continue
            v = viruses.setdefault(name, {
                "name": name,
                "ictv_name": ictv_of(name, canon),
                "matched_names": {name},
                "taxid": (row.get("Virus TaxID", "") or "").strip(),
                "family": (row.get("Virus Family", "") or "").strip(),
                "genus": (row.get("Virus Genus", "") or "").strip(),
                "lineage": (row.get("Lineage", "") or "").strip(),
                "relationships": [],
                "_rel_seen": set(),
            })
            vector = (row.get("Vector", "") or "").strip()
            host = (row.get("Virus Host", "") or "").strip()
            mode = (row.get("Virus Transmission Mode", "") or "").strip()
            key = (vector, host, mode)
            if key in v["_rel_seen"]:
                continue
            v["_rel_seen"].add(key)
            v["relationships"].append({
                "vector": vector,
                "vector_order": (row.get("Vector Order", "") or "").strip(),
                "vector_family": (row.get("Vector Family", "") or "").strip(),
                "vector_genus": (row.get("Vector Genus", "") or "").strip(),
                "vector_taxid": (row.get("Vector TaxID", "") or "").strip(),
                "host": host,
                "host_taxid": (row.get("Host TaxID", "") or "").strip(),
                "transmission_mode": mode,
                "transmission_category": transmission_category(mode),
                "doi_insect": (row.get("DOI for Validation Virus-Insect Relationships", "") or "").strip(),
                "doi_transmission": (row.get("DOI for Validation Virus Transmission Mode", "") or "").strip(),
            })
    return viruses


def parse_refs(refs_blob: str, limit: int = 10) -> list:
    """解析 WUR refs（scrape_wur.py 输出的 JSON 数组），返回结构化参考列表:
    [{title, authors, citation, means, doi}, ...]。兼容旧的纯字符串格式(退化为仅 title)。"""
    blob = (refs_blob or "").strip()
    if not blob:
        return []
    if blob.startswith("["):
        try:
            arr = json.loads(blob)
            out = []
            for r in arr[:limit]:
                if isinstance(r, dict) and r.get("title"):
                    out.append({
                        "title": (r.get("title", "") or "")[:300],
                        "authors": (r.get("authors", "") or "")[:200],
                        "citation": (r.get("citation", "") or "")[:200],
                        "means": (r.get("means", "") or "")[:200],
                        "doi": (r.get("doi", "") or "")[:200],
                    })
            return out
        except (ValueError, TypeError):
            pass
    # 旧格式回退: " || " / " | " 字符串，只保留 title
    out = []
    for chunk in blob.split(" || "):
        chunk = chunk.strip()
        if chunk:
            out.append({"title": chunk.split(" | ", 1)[0].strip()[:300],
                        "authors": "", "citation": "", "means": "", "doi": ""})
        if len(out) >= limit:
            break
    return out


def load_wur(path: Path) -> list:
    """加载 WUR 病毒级补充记录。"""
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            name = (row.get("name", "") or "").strip()
            if not name:
                continue
            try:
                ref_count = int((row.get("ref_count", "") or "0").strip() or 0)
            except ValueError:
                ref_count = 0
            rows.append({
                "name": name,
                "family": (row.get("family", "") or "").strip(),
                "genus": (row.get("genus", "") or "").strip(),
                "vector_label": (row.get("vector_org", "") or "").strip(),
                "transmission_notes": (row.get("transmission", "") or "").strip(),
                "routes": parse_routes(row.get("modes", "")),
                "vector_categories": parse_vector_categories(row.get("vector_org", "")),
                "ref_count": ref_count,
                "refs": parse_refs(row.get("refs", "")),
            })
    return rows


# ── WUR → VH 匹配 ──────────────────────────────────────────────
def build_vh_index(viruses: dict, canon: dict) -> dict:
    """归一化名 / ICTV 名 → VH 病毒主键。用于 WUR 匹配。"""
    idx = {}
    for key, v in viruses.items():
        idx.setdefault(norm(key), key)
        ic = v.get("ictv_name") or ""
        if ic:
            idx.setdefault(norm(ic), key)
    return idx


def match_wur(wur_rows, viruses, vh_index, canon):
    """把 WUR 挂到 VH 病毒（仅精确/mapping 自动合并）。返回 review 建议列表。

    未自动命中的 WUR 记录作为 WUR-only 病毒加入；若模糊相似度达阈值，
    额外写一条人工 review 建议（不自动应用）。
    """
    review = []
    vh_norm_keys = list(vh_index.keys())

    for w in wur_rows:
        nk = norm(w["name"])
        # ① 归一名精确
        target = vh_index.get(nk)
        # ② WUR 名经 mapping 归一到 ICTV 名，再查 VH 索引
        if not target:
            ic = ictv_of(w["name"], canon)
            if ic:
                target = vh_index.get(norm(ic))

        if target:
            _attach_wur(viruses[target], w, "high")
            continue

        # 未自动命中：模糊相似度给出人工建议（不合并）
        best, best_ratio = None, 0.0
        for k in vh_norm_keys:
            r = SequenceMatcher(None, nk, k).ratio()
            if r > best_ratio:
                best, best_ratio = vh_index[k], r
        if best is not None and best_ratio >= FUZZY_THRESHOLD:
            review.append({
                "wur_name": w["name"],
                "suggested_virus": best,
                "ratio": round(best_ratio, 3),
            })

        # 作为 WUR-only 病毒加入（键 = WUR 名；罕见撞名则并入）
        key = w["name"]
        if key in viruses:
            _attach_wur(viruses[key], w, "high")
        else:
            viruses[key] = {
                "name": key,
                "ictv_name": ictv_of(key, canon),
                "matched_names": {key},
                "taxid": "",
                "family": w["family"],
                "genus": w["genus"],
                "lineage": "",
                "relationships": [],
                "_rel_seen": set(),
                "_wur_only": True,
            }
            _attach_wur(viruses[key], w, "high")
            vh_index.setdefault(norm(key), key)
    return review


def _attach_wur(v: dict, w: dict, confidence: str):
    """挂 WUR 补充信息，计算 family_mismatch 冲突。"""
    v["matched_names"].add(w["name"])
    v["wur"] = {
        "vector_label": w["vector_label"],
        "transmission_notes": w["transmission_notes"],
        "ref_count": w["ref_count"],
        "refs": w["refs"],
        "match_confidence": confidence,
    }
    # WUR 独有的两个正交维度: 传播途径 + 粗媒介类别
    v["transmission_routes"] = w.get("routes", [])
    v["vector_categories"] = w.get("vector_categories", [])
    if v.get("family") and w["family"] and norm(v["family"]) != norm(w["family"]):
        flags = set(v.get("conflict_flags", []))
        flags.add("family_mismatch")
        v["conflict_flags"] = sorted(flags)


# ── 组装输出 ────────────────────────────────────────────────────
def finalize(v: dict) -> dict:
    rels = v["relationships"]
    has_vh = not v.get("_wur_only", False)
    has_wur = "wur" in v
    sources = []
    if has_vh:
        sources.append("VH")
    if has_wur:
        sources.append("WUR")
    if not sources:
        sources = ["VH"]

    return {
        "canonical_name": v["name"],
        "ictv_name": v.get("ictv_name", ""),
        "matched_names": sorted(v["matched_names"]),
        "taxid": v["taxid"],
        "family": v["family"],
        "genus": v["genus"],
        "lineage": v["lineage"],
        "sources": sources,
        "relationships": rels,
        "vectors": sorted({r["vector"] for r in rels if r["vector"]}),
        "hosts": sorted({r["host"] for r in rels if r["host"]}),
        "vector_orders": sorted({r["vector_order"] for r in rels if r["vector_order"]}),
        "transmission_modes": sorted({r["transmission_mode"] for r in rels if r["transmission_mode"] and r["transmission_mode"] != "NA"}),
        "transmission_categories": sorted({r["transmission_category"] for r in rels if r["transmission_category"] != "Unknown"}),
        "transmission_routes": v.get("transmission_routes", []),
        "vector_categories": v.get("vector_categories", []),
        "wur": v.get("wur"),
        "conflict_flags": v.get("conflict_flags", []),
    }


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="合并 VH + WUR → virus_vector_merged.json")
    ap.add_argument("--vh", default=str(here / "virus_vector_host.tsv"))
    ap.add_argument("--wur", default=str(here / "wur_virus_full.tsv"))
    ap.add_argument("--name-map", default=str(here.parent / "docs" / "data" / "name_mapping.tsv"))
    ap.add_argument("--out", default=str(here / "virus_vector_merged.json"))
    ap.add_argument("--review", default=str(here / "vector_merge_review.tsv"))
    args = ap.parse_args()

    map_path = Path(args.name_map)
    out_path, review_path = Path(args.out), Path(args.review)

    print(f"[1/5] 加载 name_mapping: {map_path}")
    canon = load_name_map(map_path)
    print(f"      → {len(canon):,} 个归一化键")

    print(f"[2/5] 加载 VH (主干): {args.vh}")
    viruses = load_vh(Path(args.vh), canon)
    n_vh_viruses = len(viruses)
    n_vh_rel = sum(len(v["relationships"]) for v in viruses.values())
    print(f"      → {n_vh_viruses:,} 个病毒, {n_vh_rel:,} 条去重后关系")

    print(f"[3/5] 加载 WUR (补充): {args.wur}")
    wur_rows = load_wur(Path(args.wur))
    print(f"      → {len(wur_rows):,} 条 WUR 记录")

    print("[4/5] 匹配 WUR → VH (精确/mapping 自动，模糊仅建议)")
    vh_index = build_vh_index(viruses, canon)
    review = match_wur(wur_rows, viruses, vh_index, canon)

    finalized = [finalize(v) for v in viruses.values()]
    finalized.sort(key=lambda x: x["canonical_name"].lower())
    n_both = sum(1 for v in finalized if set(v["sources"]) >= {"VH", "WUR"})
    n_vh_only = sum(1 for v in finalized if v["sources"] == ["VH"])
    n_wur_only = sum(1 for v in finalized if v["sources"] == ["WUR"])
    n_conflict = sum(1 for v in finalized if v["conflict_flags"])

    out = {
        "generated": str(date.today()),
        "stats": {
            "total_viruses": len(finalized),
            "vh_viruses": n_vh_viruses,
            "wur_records": len(wur_rows),
            "vh_relationships": n_vh_rel,
            "source_both": n_both,
            "source_vh_only": n_vh_only,
            "source_wur_only": n_wur_only,
            "family_conflicts": n_conflict,
            "fuzzy_review_suggestions": len(review),
        },
        "viruses": finalized,
    }

    print(f"[5/5] 写出: {out_path}")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    with open(review_path, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["wur_name", "suggested_virus", "ratio"], delimiter="\t")
        wr.writeheader()
        wr.writerows(sorted(review, key=lambda x: -x["ratio"]))
    print(f"      review 建议: {review_path} ({len(review)} 条待人工确认)")

    size_mb = out_path.stat().st_size / 1024 / 1024
    print("\n" + "=" * 56)
    print(f"  合并完成  {out_path.name}  ({size_mb:.2f} MB)")
    print("-" * 56)
    for k, val in out["stats"].items():
        print(f"  {k:<28} {val:>10,}")
    print("=" * 56)


if __name__ == "__main__":
    main()
