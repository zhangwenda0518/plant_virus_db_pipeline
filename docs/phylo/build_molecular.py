#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析 ICTV 官方 Newick 树，产出前端可用的 molecular_trees.json。

Newick 格式的坑（都在这处理了）：
  - 引号标签：'Potato virus Y'，内部双写单引号表示转义 ''
  - 节点注释：[&R] / [&U] 前缀，以及任意位置的 [comment]
  - 内部节点名字通常是支持度（bootstrap / posterior），可能是 0-1 或 0-100
  - 枝长可选，可能带科学计数法
  - 文件名里带空格（ICTV 有些文件就这么命名）

用法：
    python build_molecular.py
    python build_molecular.py --min-leaves 5
"""

import argparse
import json
import math
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "ictv_raw")
MANIFEST = os.path.join(RAW_DIR, "manifest.json")
OUT = os.path.join(HERE, "molecular_trees.json")

DEFAULT_MAX_LEAVES = 1200


class NewickError(ValueError):
    pass


class NewickParser:
    """递归下降解析 Newick。只取第一个树（分号前）。"""

    def __init__(self, text):
        self.s = text
        self.i = 0
        self.n = len(text)

    # ---------- 基础 ----------
    def _skip_ws(self):
        while self.i < self.n and self.s[self.i] in " \t\r\n":
            self.i += 1

    def _skip_comment(self):
        """跳过一层 [ ... ]（ICTV 树里不嵌套）。"""
        depth = 0
        while self.i < self.n:
            c = self.s[self.i]
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    self.i += 1
                    return
            self.i += 1

    # ---------- 读取 ----------
    def _read_label(self):
        self._skip_ws()
        if self.i >= self.n:
            return ""
        if self.s[self.i] == "'":
            self.i += 1
            buf = []
            while self.i < self.n:
                c = self.s[self.i]
                if c == "'":
                    if self.i + 1 < self.n and self.s[self.i + 1] == "'":
                        buf.append("'")
                        self.i += 2
                        continue
                    self.i += 1
                    break
                buf.append(c)
                self.i += 1
            return "".join(buf)
        buf = []
        while self.i < self.n and self.s[self.i] not in "(),:;[]":
            buf.append(self.s[self.i])
            self.i += 1
        return "".join(buf).strip()

    def _read_length(self):
        self._skip_ws()
        if self.i < self.n and self.s[self.i] == ":":
            self.i += 1
            buf = []
            while self.i < self.n and self.s[self.i] not in "(),;[]":
                buf.append(self.s[self.i])
                self.i += 1
            t = "".join(buf).strip()
            try:
                return float(t)
            except ValueError:
                return None
        return None

    def _read_label_parts(self):
        """读内部节点的全部标签 token。

        ICTV 有些树把「类群名 + 支持度」连写在一起，中间没有分隔符：
            )'Tymovirales'0.9980:0.43303016
        标准 Newick 只允许一个标签，所以这里必须把连续的 token 都读出来，
        再由 split_name_support() 决定哪个是名字、哪个是支持度。
        """
        parts = []
        while True:
            self._skip_ws()
            if self.i >= self.n:
                break
            if self.s[self.i] in ",):;[":
                break
            tok = self._read_label()
            if not tok:
                break
            parts.append(tok)
        return parts

    # ---------- 语法 ----------
    def _subtree(self):
        self._skip_ws()
        node = {"ch": []}
        if self.i < self.n and self.s[self.i] == "(":
            self.i += 1
            while True:
                node["ch"].append(self._subtree())
                self._skip_ws()
                if self.i >= self.n:
                    break
                c = self.s[self.i]
                if c == ",":
                    self.i += 1
                    continue
                if c == ")":
                    self.i += 1
                    break
                if c == "[":
                    # 方括号是注释。ICTV 有几个科的树把支持度写在方括号里：
                    #     ) :0.11091[1000] ,
                    # _read_length() 读到 '[' 就停，于是父节点的子循环会看到这个 '['。
                    #
                    # 早期版本这里直接 `continue` 回到循环开头，等于**又解析了一个子树**；
                    # 而此刻光标停在 ',' 上，_read_label() 读出空串，于是凭空多出一个
                    # 无名、无枝长的空叶。三个科因此被污染：
                    #     Metaviridae    +207 个空叶（叶数 210 -> 417）
                    #     Pseudoviridae  +207 个空叶（叶数 210 -> 417）
                    #     Phenuiviridae  +149 个空叶
                    # 空叶数恰好等于该文件里 '[' 的个数，就是这条路径造成的。
                    #
                    # 正确做法：跳完注释后**重新判断**分隔符，不要再造子节点。
                    self._skip_comment()
                    self._skip_ws()
                    if self.i >= self.n:
                        break
                    c = self.s[self.i]
                    if c == ",":
                        self.i += 1
                        continue
                    if c == ")":
                        self.i += 1
                        break
                raise NewickError("位置 %d 出现意外字符 %r" % (self.i, c))
            name, sup = split_name_support(self._read_label_parts())
            node["n"] = name or ""
            node["sup"] = sup
            node["bl"] = self._read_length()
        else:
            node["n"] = self._read_label()
            node["sup"] = None
            node["bl"] = self._read_length()
        return node

    def parse(self):
        self._skip_ws()
        while self.i < self.n and self.s[self.i] == "[":
            self._skip_comment()
            self._skip_ws()
        if self.i >= self.n:
            raise NewickError("空内容")
        root = self._subtree()
        self._skip_ws()
        if self.i < self.n and self.s[self.i] == ";":
            self.i += 1
        return root


def parse_newick(text):
    """解析 Newick 文本；失败抛 NewickError。"""
    if not text or not text.strip():
        raise NewickError("空文件")
    return NewickParser(text).parse()


def as_support(label):
    """内部节点标签若是 0-1 或 0-100 的数值，视为支持度。"""
    if not label:
        return None
    t = label.strip().rstrip("%")
    try:
        v = float(t)
    except ValueError:
        return None
    if 0.0 <= v <= 1.0:
        return v
    if 1.0 < v <= 100.0:
        return v / 100.0
    return None


def split_name_support(parts):
    """把内部节点的若干标签 token 拆成 (类群名, 支持度)。

    出现顺序不固定，ICTV 里有三种：
        ['0.9950']                    -> (None, 0.995)
        ['Tymovirales']               -> ('Tymovirales', None)
        ['Tymovirales', '0.9980']     -> ('Tymovirales', 0.998)
    """
    name = None
    sup = None
    for p in parts:
        v = as_support(p)
        if v is not None and sup is None:
            sup = v
        elif name is None:
            name = p
        else:
            name += " " + p          # 极少数情况，兜底
    return name, sup


def walk(node, depth=0, dist=0.0, acc=None):
    """深度遍历，回调 acc(node, depth, cumdist)。"""
    bl = node.get("bl")
    d = dist + (bl if isinstance(bl, float) else 0.0)
    acc(node, depth, d)
    for c in node.get("ch", []):
        walk(c, depth + 1, d, acc)


def stats(root):
    """统计一棵树的结构与支撑度。"""
    leaves = []
    internals = []
    rtt = []

    def acc(node, depth, dist):
        ch = node.get("ch", [])
        if ch:
            internals.append(node)
        else:
            leaves.append(node)
            rtt.append(dist)

    walk(root, 0, 0.0, acc)

    degs = [len(n["ch"]) for n in internals]
    root_deg = len(root.get("ch", []))
    # 根部的三分叉是「无根树」的标准画法，不算真实多分叉
    inner_degs = degs[1:] if degs else []
    polytomies = sum(1 for d in inner_degs if d >= 3)
    sups = [n["sup"] for n in internals if n.get("sup") is not None]
    bls = []
    walk(root, 0, 0.0, lambda n, d, x: bls.append(n["bl"])
         if isinstance(n.get("bl"), float) else None)
    has_bl = bool(bls)

    return {
        "leaves": len(leaves),
        "internals": len(internals),
        "binary": polytomies == 0 and all(d == 2 for d in inner_degs),
        "polytomies": polytomies,
        "rootDegree": root_deg,
        "maxDegree": max(degs) if degs else 0,
        "hasBranchLengths": has_bl,
        "blMax": round(max(bls), 6) if bls else None,
        "supportN": len(sups),
        "supportMin": round(min(sups), 4) if sups else None,
        "supportMed": round(statistics.median(sups), 4) if sups else None,
        "supportMax": round(max(sups), 4) if sups else None,
        "rttMax": round(max(rtt), 6) if rtt else None,
        "rttMed": round(statistics.median(rtt), 6) if rtt else None,
    }


def to_frontend(node, is_root=True):
    """转成紧凑的前端节点：{n 名, s 支持度, bl 枝长, ch 子节点}。"""
    out = {}
    name = node.get("n") or ""
    ch = node.get("ch", [])
    if name:
        out["n"] = name
    elif is_root:
        out["n"] = "root"
    if isinstance(node.get("bl"), float):
        out["bl"] = round(node["bl"], 6)
    if ch:
        sup = node.get("sup")
        if sup is not None:
            out["s"] = round(sup, 4)
        out["ch"] = [to_frontend(c, False) for c in ch]
    return out


def looks_like_newick(path):
    """文件可能不是树（例如误判），做个廉价校验。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096).decode("utf-8", "replace")
    except OSError:
        return False
    return head.lstrip().startswith("(") or head.lstrip().startswith("[&")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--min-leaves", type=int, default=3,
                    help="少于此叶子数的树跳过")
    ap.add_argument("--max-leaves", type=int, default=DEFAULT_MAX_LEAVES,
                    help="多于此叶子数的树跳过（前端渲染不动）")
    a = ap.parse_args()

    with open(a.manifest, encoding="utf-8") as fh:
        man = json.load(fh)

    out = {
        "meta": {
            "source": "ICTV Report chapter resources (official maximum-likelihood trees)",
            "base": man.get("base", "https://ictv.global"),
            "note": ("ICTV 官方发布的分子系统发育树，Newick 格式。"
                     "与 taxonomy_tree.json 的分类学树不是一回事："
                     "这里是按序列推断的二分叉树，带枝长与支持度。"),
        },
        "families": [],
    }

    n_ok = n_skip = n_fail = 0
    for entry in man["families"]:
        fam = entry["family"]
        trees = []
        for f in entry["files"]:
            if f["kind"] != "tree":
                continue
            rel = f.get("local")
            if not rel:
                continue
            path = os.path.join(HERE, rel)
            if not os.path.exists(path):
                continue
            if not looks_like_newick(path):
                n_fail += 1
                print("  SKIP(非树) %-20s %s" % (fam, f["name"]))
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                root = parse_newick(text)
                st = stats(root)
            except Exception as e:                       # noqa: BLE001
                n_fail += 1
                print("  FAIL %-20s %-44s %s" % (fam, f["name"], e))
                continue
            if st["leaves"] < a.min_leaves:
                n_skip += 1
                print("  SKIP(叶少 %d) %-20s %s" % (st["leaves"], fam, f["name"]))
                continue
            if st["leaves"] > a.max_leaves:
                n_skip += 1
                print("  SKIP(叶多 %d) %-20s %s" % (st["leaves"], fam, f["name"]))
                continue

            tid = "%s|Fig%s" % (fam, f.get("fig") or "?")
            if any(t["id"] == tid for t in trees):
                tid += "b"
            trees.append({
                "id": tid,
                "fig": f.get("fig") or "",
                "file": f["name"],
                "url": f["url"],
                "bytes": f.get("bytes"),
                "stats": st,
                "tree": to_frontend(root),
            })
            n_ok += 1
            print("  ok   %-20s %-44s leaves=%-5d binary=%-5s sup=%s"
                  % (fam, f["name"], st["leaves"], st["binary"],
                     st["supportMed"]))

        if trees:
            trees.sort(key=lambda t: (t["fig"] or "", t["file"]))
            out["families"].append({"family": fam, "trees": trees})

    out["meta"]["familiesWithTrees"] = len(out["families"])
    out["meta"]["trees"] = sum(len(f["trees"]) for f in out["families"])
    out["meta"]["leavesTotal"] = sum(t["stats"]["leaves"]
                                     for f in out["families"] for t in f["trees"])

    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(a.out)
    print("\n解析成功 %d 棵，跳过 %d，失败 %d" % (n_ok, n_skip, n_fail))
    print("覆盖 %d 个科，合计 %d 个末端序列" % (out["meta"]["familiesWithTrees"],
                                              out["meta"]["leavesTotal"]))
    print("输出 %s (%.1f KB)" % (a.out, size / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
