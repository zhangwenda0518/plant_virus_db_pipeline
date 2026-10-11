#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 Newick 树渲染成独立 SVG（矩形枝长树 phylogram）。

用途：自建树（见 build_own_trees.py）跑完后要能直接看、直接进图，不必起浏览器。
无第三方依赖，纯标准库。

布局口径：
  - x = **累积枝长**（真实的系统发育树按替换率/site 定位，不是等距拓扑图）
  - y = 叶的 DFS 序，内部节点取首末子节点的中点
  - 叶数多时按叶数自动加高画布

用法:
    python render_tree_svg.py --tree work/Caulimoviridae.treefile --out work/Caulimoviridae.svg
    # 按属着色（需要 build_own_trees.py 产出的 manifest）
    python render_tree_svg.py --tree X.treefile --out X.svg --manifest work/X.manifest.tsv
"""
import argparse
import os
import re
import sys

PALETTE = [
    '#2e86c1', '#e67e22', '#27ae60', '#8e44ad', '#c0392b', '#16a085',
    '#d4ac0d', '#7f8c8d', '#2980b9', '#a04000', '#1e8449', '#6c3483',
]


class Node(object):
    # d = 累积枝长（画布 x），y = 叶序（画布 y），由布局阶段写入，故一并放进 slots
    __slots__ = ('name', 'sup', 'bl', 'ch', 'd', 'y')

    def __init__(self):
        self.name = None
        self.sup = None
        self.bl = None
        self.ch = []
        self.d = 0.0
        self.y = 0.0


def parse_newick(s):
    """紧凑的 Newick 解析器。

    处理本项目遇到过的非标准写法（见 docs/phylo/README.md M3）：
    引号标签（支持 '' 转义）、[comment] 节点注释、
    **类群名与支持度连写**（如 )'Tymovirales'0.9980:0.43）。
    """
    i = 0
    n = len(s)

    def skip():
        nonlocal i
        while i < n:
            c = s[i]
            if c in ' \t\r\n':
                i += 1
            elif c == '[':
                j = s.find(']', i)
                i = n if j < 0 else j + 1
            else:
                break

    def read_tokens():
        """读到分隔符为止的全部标签 token（名字与支持度可能连写）。"""
        # 注意：i 由本函数与 sub()/skip() 共同推进，三处都必须声明 nonlocal，
        # 否则 Python 会把它当成本函数的局部变量，读到未赋值即报 UnboundLocalError。
        nonlocal i
        out = []
        while True:
            skip()
            if i >= n or s[i] in ',):;':
                break
            if s[i] == "'":
                i += 1
                buf = []
                while i < n:
                    if s[i] == "'":
                        if i + 1 < n and s[i + 1] == "'":
                            buf.append("'")
                            i += 2
                            continue
                        i += 1
                        break
                    buf.append(s[i])
                    i += 1
                out.append(''.join(buf))
            else:
                j = i
                while i < n and s[i] not in ',):;[' and s[i] not in ' \t\r\n':
                    i += 1
                out.append(s[j:i])
        return out

    def as_support(tok):
        try:
            v = float(tok)
        except ValueError:
            return None
        return v

    def split_parts(parts, is_leaf):
        """把标签 token 拆成 (名字, 支持度)。

        **叶与内部节点必须分开处理**：只有内部节点的标签才可能是支持度。
        ICTV 的树里存在纯数字的**叶名** —— Metaviridae / Pseudoviridae 有
        `297`、`17.6`、`1731`、`412`，Potyviridae 有 `0.16690164`。
        早期版本对叶也做数值判定，于是这些叶名被当成支持度吞掉，
        `name` 变成 None（实测 4+4+1 条丢失）。
        """
        if is_leaf:
            return (' '.join(parts) if parts else None), None
        name, sup = None, None
        for p in parts:
            v = as_support(p)
            if v is not None and sup is None:
                sup = v
            elif name is None:
                name = p
            else:
                name = name + ' ' + p
        return name, sup

    def sub():
        nonlocal i
        node = Node()
        skip()
        if i < n and s[i] == '(':
            i += 1
            while True:
                node.ch.append(sub())
                skip()
                if i < n and s[i] == ',':
                    i += 1
                    continue
                if i < n and s[i] == ')':
                    i += 1
                    break
                break
            parts = read_tokens()
            node.name, node.sup = split_parts(parts, is_leaf=False)
        else:
            parts = read_tokens()
            node.name, node.sup = split_parts(parts, is_leaf=True)
        skip()
        if i < n and s[i] == ':':
            i += 1
            skip()
            j = i
            while i < n and s[i] not in ',);':
                i += 1
            try:
                node.bl = float(s[j:i])
            except ValueError:
                node.bl = None
        return node

    skip()
    root = sub()
    return root


def load_manifest(path):
    """读 build_own_trees.py 的 manifest，返回 {accession: genus}。"""
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding='utf-8') as fh:
        hdr = None
        for line in fh:
            if line.startswith('#'):
                continue
            parts = line.rstrip('\n').split('\t')
            if hdr is None:
                hdr = parts
                continue
            if len(parts) < len(hdr):
                continue
            out[parts[0]] = parts[3]
    return out


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True, help='Newick 文件（IQ-TREE 的 .treefile 即可）')
    ap.add_argument('--out', required=True)
    ap.add_argument('--manifest', help='build_own_trees.py 的 manifest，用于按属着色')
    ap.add_argument('--title')
    ap.add_argument('--label-gap', type=int, default=14, help='叶间距（px），默认 14')
    ap.add_argument('--width', type=int, default=1500)
    args = ap.parse_args()

    raw = open(args.tree, encoding='utf-8').read()
    m = re.search(r'\(.*\)', raw, re.S)
    if not m:
        raise SystemExit('[FATAL] 文件里没找到 Newick 结构')
    root = parse_newick(m.group(0))

    # 叶序 + 累积枝长
    order = []

    def setd(node, d):
        node.d = d + (node.bl or 0.0)
        if node.ch:
            for c in node.ch:
                setd(c, node.d)
        else:
            node.y = len(order)
            order.append(node)

    def sety(node):
        if node.ch:
            for c in node.ch:
                sety(c)
            node.y = (node.ch[0].y + node.ch[-1].y) / 2.0

    setd(root, 0.0)
    sety(root)

    n_leaf = len(order)
    maxd = max(n.d for n in order) or 1.0
    gap = args.label_gap
    pad_top, pad_bot, pad_left = 24, 24, 16
    label_w = 460
    plot_w = args.width - pad_left - label_w - 20
    h = pad_top + pad_bot + max(1, n_leaf - 1) * gap
    sx = plot_w / maxd

    genus_of = load_manifest(args.manifest)
    genus_color = {}

    def color_for(leaf):
        g = genus_of.get((leaf.name or '').split('_')[0])
        if not g:
            return '#2e86c1'
        if g not in genus_color:
            genus_color[g] = PALETTE[len(genus_color) % len(PALETTE)]
        return genus_color[g]

    def X(node):
        return pad_left + node.d * sx

    def Y(node):
        return pad_top + node.y * gap

    seg = []

    def draw(node):
        if node.ch:
            x = X(node)
            y0 = Y(node.ch[0])
            y1 = Y(node.ch[-1])
            seg.append('<path d="M%.1f %.1fV%.1f" stroke="#9fb3c4" stroke-width="1" fill="none"/>'
                       % (x, y0, y1))
            for c in node.ch:
                seg.append('<path d="M%.1f %.1fH%.1f" stroke="#9fb3c4" stroke-width="1" fill="none"/>'
                           % (x, Y(c), X(c)))
                if c.sup is not None:
                    v = c.sup if c.sup > 1 else c.sup * 100
                    if v < 95:
                        seg.append('<text x="%.1f" y="%.1f" font-size="9" fill="#c0392b" '
                                   'text-anchor="start">%.0f</text>' % (X(c) + 3, Y(c) - 3, v))
                draw(c)
        else:
            seg.append('<circle cx="%.1f" cy="%.1f" r="2.2" fill="%s"/>'
                       % (X(node), Y(node), color_for(node)))
            seg.append('<text x="%.1f" y="%.1f" font-size="10.5" fill="#2c3e50">%s</text>'
                       % (X(node) + 8, Y(node) + 3.5, esc(node.name or '')))

    draw(root)

    legend = ''
    if genus_color:
        items = sorted(genus_color.items())
        legend = '<g transform="translate(%d,%d)">' % (pad_left, 6)
        for k, (g, col) in enumerate(items):
            xx = k * 150
            legend += ('<rect x="%d" y="-7" width="9" height="9" rx="2" fill="%s"/>'
                       '<text x="%d" y="1" font-size="10.5" fill="#5d6d7e">%s</text>'
                       % (xx, col, xx + 13, esc(g)))
        legend += '</g>'

    title = ('<text x="%d" y="%d" font-size="13" font-weight="700" fill="#1a5276">%s</text>'
             % (pad_left, h + 16, esc(args.title))) if args.title else ''

    svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d" font-family="-apple-system,Segoe UI,Roboto,PingFang SC,sans-serif">\n'
           '<rect width="100%%" height="100%%" fill="#ffffff"/>\n'
           '<text x="%d" y="%d" font-size="10" fill="#95a5b5">枝长按比例 · %d 末端 · '
           'x 轴 = 累积枝长（替换率/site）</text>\n%s\n%s\n%s\n</svg>\n'
           % (args.width, h + 34, args.width, h + 34,
              pad_left, 16, n_leaf, legend, ''.join(seg), title))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(svg)

    print('[OK] %s' % args.out)
    print('     末端: %d   最大累积枝长: %.4f   画布: %dx%d' % (n_leaf, maxd, args.width, h + 34))
    if genus_color:
        print('     属着色: %d 个（%s）' % (len(genus_color), ', '.join(sorted(genus_color))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
