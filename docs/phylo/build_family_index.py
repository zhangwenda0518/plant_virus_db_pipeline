#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Step 3 — 由已验证的 molecular_trees.json 生成「按科索引」页所需的数据。

设计约束：**不修改 molecular_trees.json**（那是已交付并线上验证过的产物），
本脚本只读它，另出一份派生的 family_index.json。

输出 docs/phylo/molecular/families/family_index.json，每个科一条：
  - 树数 / 叶数 / 内部节点数 / 严格二分叉树数
  - 支持度覆盖（有支持度标注的内部节点 / 内部节点总数）、最大枝长
  - MSL41 里该科的物种数与属数（**口径与叶数不同**，不能当「覆盖率」读）
  - 跨科共享登录号计数 —— 这是「这些树含别的科作外群」的判据
  - 每棵树的 sparkline（降采样 SVG path，viewBox 0 0 100 34）

用法:
    python build_family_index.py
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'molecular_trees.json')
MSL = os.path.join(HERE, 'data', 'MSL41_species.tsv')
OUT_DIR = os.path.join(HERE, 'molecular', 'families')
OUT = os.path.join(OUT_DIR, 'family_index.json')

# 登录号：2-3 位大写字母 + 5-6 位数字（MN123456 / NC_000001 这类下划线写法会被拆开，
# 所以用宽松匹配；命中率约 48%，故跨科计数是**下界**）
ACC_RE = re.compile(r'[A-Z]{2,3}[0-9]{5,6}')

# 叶名里的「片段长度」标记，如 PIRYV_KU178986_688_bp / StrV1_MK211271_1207_bp。
# 命中说明这棵树建在片段上，不是全长基因组 —— 和全长树不能直接比。
FRAG_RE = re.compile(r'\d+\s*_?\s*bp\b', re.I)

# ICTV 自己的「登录号查不到」占位符。**有三种写法**，必须一起匹配，
# 否则会漏掉一半以上（早期只按带空格的那种数，把 Potyviridae 的 25 个全漏了）：
#   ACCESSION NOT ON SPREADSHEET    （带空格）
#   ACCESSION_NOT_ON_SPREADSHEET    （下划线，Newick 里空格常被换成下划线）
#   ACCESSION FORMAT NOT RECOGNISED
PLACEHOLDER_RE = re.compile(
    r'ACCESSION[\s_]*(?:NOT[\s_]*ON[\s_]*SPREADSHEET|FORMAT[\s_]*NOT[\s_]*RECOGNISED)', re.I)

SPARK_W = 100.0
SPARK_H = 34.0
SPARK_PAD = 1.5
SPARK_TIPS = 48


def walk_leaves(n, out):
    ch = n.get('ch') or []
    if not ch:
        out.append(n.get('n') or '')
        return
    for c in ch:
        walk_leaves(c, out)


def leaves_of(n):
    ch = n.get('ch') or []
    if not ch:
        return 1
    return sum(leaves_of(c) for c in ch)


def spark(node):
    """把一棵树降采样成 viewBox 0 0 100 34 的 SVG path。

    用**拓扑深度**而非枝长定位 x —— sparkline 只看形状，不按比例，
    这样不同树可以并排比较。叶数超过 SPARK_TIPS 时把每个小分支塌缩成
    一根竖笔，把 path 长度控制在 O(SPARK_TIPS) 量级。
    """
    depths = []
    order = []

    def prep(n, d):
        n['_d'] = d
        depths.append(d)
        ch = n.get('ch') or []
        if not ch:
            n['_lv'] = 1
            return 1
        total = 0
        for c in ch:
            total += prep(c, d + 1)
        n['_lv'] = total
        return total

    def assign(n):
        ch = n.get('ch') or []
        if not ch:
            n['_y'] = len(order)
            order.append(n)
            return
        for c in ch:
            assign(c)
        n['_y'] = (ch[0]['_y'] + ch[-1]['_y']) / 2.0

    total = prep(node, 0)
    assign(node)
    maxd = max(depths) or 1
    sx = (SPARK_W - SPARK_PAD) / maxd
    sy = (SPARK_H - 2 * SPARK_PAD) / max(1, total - 1)
    min_lv = max(1, int(round(total / float(SPARK_TIPS))))
    seg = []

    def emit(n, px):
        x = SPARK_PAD + n['_d'] * sx
        y = SPARK_PAD + n['_y'] * sy
        ch = n.get('ch') or []
        if ch:
            seg.append('M%.1f %.1fV%.1f' % (
                x, SPARK_PAD + ch[0]['_y'] * sy, SPARK_PAD + ch[-1]['_y'] * sy))
            if n['_lv'] <= min_lv:
                if px is not None:
                    seg.append('M%.1f %.1fH%.1f' % (px, y, x))
                return
        if px is not None:
            seg.append('M%.1f %.1fH%.1f' % (px, y, x))
        for c in ch:
            emit(c, x)

    emit(node, None)
    return ''.join(seg)


def load_msl():
    """读 MSL41 主表，按科汇总物种数 / 属数 / 基因组类型。"""
    sp = collections.Counter()
    gen = collections.defaultdict(set)
    gm = collections.defaultdict(collections.Counter)
    with open(MSL, encoding='utf-8') as fh:
        hdr = fh.readline().rstrip('\n').split('\t')
        ix = {h: i for i, h in enumerate(hdr)}
        for line in fh:
            r = line.rstrip('\n').split('\t')
            if len(r) < len(hdr):
                continue
            fam = r[ix['Family']].strip()
            if not fam:
                continue
            sp[fam] += 1
            gen[fam].add(r[ix['Genus']].strip())
            gm[fam][r[ix['Genome']].strip()] += 1
    return sp, gen, gm


def main():
    if not os.path.exists(SRC):
        raise SystemExit('[FATAL] 找不到 %s' % SRC)
    if not os.path.exists(MSL):
        raise SystemExit('[FATAL] 找不到 %s' % MSL)

    d = json.load(open(SRC, encoding='utf-8'))
    fams = d['families']
    msl_sp, msl_gen, msl_gm = load_msl()

    # ── 跨科共享登录号：先建 登录号 -> 出现过的科 集合 ──────────────
    fam_accs = {}
    for f in fams:
        s = set()
        for t in f['trees']:
            ls = []
            walk_leaves(t['tree'], ls)
            for name in ls:
                s |= set(ACC_RE.findall(name))
        fam_accs[f['family']] = s

    acc_fams = collections.defaultdict(set)
    for fam, accs in fam_accs.items():
        for a in accs:
            acc_fams[a].add(fam)
    shared = {a for a, fs in acc_fams.items() if len(fs) > 1}

    # ── 逐科汇总 ────────────────────────────────────────────────
    out_fams = []
    for f in sorted(fams, key=lambda x: x['family']):
        fam = f['family']
        trees = []
        for t in f['trees']:
            st = t['stats']
            ls = []
            walk_leaves(t['tree'], ls)
            tacc = set()
            for name in ls:
                tacc |= set(ACC_RE.findall(name))
            frag = sum(1 for x in ls if FRAG_RE.search(x))
            ph = sum(1 for x in ls if PLACEHOLDER_RE.search(x))
            trees.append({
                'id': t['id'],
                'fig': t.get('fig'),
                'file': t.get('file'),
                'url': t.get('url'),
                'leaves': st['leaves'],
                'internals': st['internals'],
                'binary': st['binary'],
                'polytomies': st['polytomies'],
                'supportN': st['supportN'],
                'blMax': st['blMax'],
                'accN': len(tacc),
                'crossAcc': len(tacc & shared),
                'fragN': frag,
                'phN': ph,
                'spark': spark(t['tree']),
            })

        leaves = sum(x['leaves'] for x in trees)
        internals = sum(x['internals'] for x in trees)
        sup_n = sum(x['supportN'] for x in trees)
        n_sp = msl_sp.get(fam, 0)
        out_fams.append({
            'family': fam,
            'nTrees': len(trees),
            'leaves': leaves,
            'internals': internals,
            'binaryTrees': sum(1 for x in trees if x['binary']),
            'treesWithSupport': sum(1 for x in trees if x['supportN']),
            'supportCoverage': round(sup_n / float(internals), 4) if internals else 0.0,
            'blMax': max((x['blMax'] or 0) for x in trees),
            'crossAcc': len(fam_accs[fam] & shared),
            'fragN': sum(x['fragN'] for x in trees),
            'phN': sum(x['phN'] for x in trees),
            'mslSpecies': n_sp,
            'mslGenera': len(msl_gen.get(fam, ())),
            'genomes': [g for g, _ in msl_gm.get(fam, collections.Counter()).most_common()],
            'leafToSpecies': round(leaves / float(n_sp), 3) if n_sp else None,
            'trees': trees,
        })

    total_leaves = sum(x['leaves'] for x in out_fams)
    meta = {
        'source': d.get('meta', {}).get('source', ''),
        'base': d.get('meta', {}).get('base', ''),
        'derivedFrom': 'molecular_trees.json + data/MSL41_species.tsv',
        'note': (
            '这些树是 ICTV Report 章节正文的插图（Fig1–Fig6），不是覆盖全科的物种树。'
            'leaves 是树上的叶数（叶可能是序列/株系/基因片段/蛋白），mslSpecies 是 MSL41 里'
            '该科的物种数 —— 两者口径不同，leafToSpecies 仅供参考，不能当覆盖率读。'
            'crossAcc > 0 表示该科的树里有登录号同时出现在别的科的树里，即含跨科外群。'
        ),
        'families': len(out_fams),
        'trees': sum(x['nTrees'] for x in out_fams),
        'leaves': total_leaves,
        'crossAccessions': len(shared),
        'accTotal': len(acc_fams),
        'placeholderTips': sum(x['phN'] for x in out_fams),
        'fragmentTips': sum(x['fragN'] for x in out_fams),
        'sparkBox': '0 0 %g %g' % (SPARK_W, SPARK_H),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as fo:
        json.dump({'meta': meta, 'families': out_fams}, fo,
                  ensure_ascii=False, separators=(',', ':'))

    size = os.path.getsize(OUT)
    print('[OK] %d 科 / %d 树 / %d 叶 -> %s (%.1f KB)'
          % (len(out_fams), meta['trees'], total_leaves, OUT, size / 1024.0))
    print('     跨科共享登录号: %d / %d 个可识别登录号'
          % (len(shared), len(acc_fams)))
    print('     spark path 总长: %.1f KB'
          % (sum(len(t['spark']) for x in out_fams for t in x['trees']) / 1024.0))
    print()
    print('%-22s %5s %7s %8s %7s %9s %7s %7s %6s' %
          ('family', 'trees', 'leaves', 'MSLsp', 'leaf/sp', 'supCov', 'crossAcc', 'fragN', 'phN'))
    for x in sorted(out_fams, key=lambda y: -y['leaves']):
        print('%-22s %5d %7d %8d %7s %9.2f %7d %7d %6d' % (
            x['family'], x['nTrees'], x['leaves'], x['mslSpecies'],
            ('%.3f' % x['leafToSpecies']) if x['leafToSpecies'] is not None else '-',
            x['supportCoverage'], x['crossAcc'], x['fragN'], x['phN']))


if __name__ == '__main__':
    sys.exit(main())
