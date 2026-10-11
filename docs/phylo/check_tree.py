#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_tree.py —— 自建树的体检工具（只读，不改任何数据）。

自建树（MAFFT → IQ-TREE）跑完以后，不能凭"看起来像一棵树"就交付。这个脚本做三件事：

  1. **结构统计**：叶数 / 内部节点数 / 最大度 / 枝长范围 / 支持度分布。
     叶数必须等于输入序列数，否则比对阶段就丢了序列。

  2. **属的单系性**（主要判据）：ICTV 分类中每个属都应是单系群。
     对每个 ≥2 条的属，检查是否存在一个节点的后代叶集合**恰好等于**该属的全部叶。
     不满足的属，报告"包含它的最小枝"以及混进了哪些别的属。
     这一条是可证伪的：如果一棵树 11 个属里有 2 个单系，那它大概是噪声。

  3. **与 ICTV 已发表树对拍**（`--ref`，可选）：按登录号取交集，
     比较两棵树在共有类群上的**非平凡枝**（clade）集合。
     注意：交集通常很小（本库用 RefSeq 参考序列，ICTV 图用 GenBank 分离株），
     所以这只是弱证据；脚本会显式打印交集大小，不做过度解读。

用法:
    python check_tree.py --tree work/Caulimoviridae.trim.treefile \\
                         --manifest work/Caulimoviridae.manifest.tsv
    # 加对拍
    python check_tree.py --tree work/Caulimoviridae.trim.treefile \\
                         --manifest work/Caulimoviridae.manifest.tsv \\
                         --ref ictv_raw/Caulimoviridae/ORTD.Caulimo.Fig4..v9_treefile.txt

退出码: 0 = 全部检查通过；1 = 有检查项不通过（便于 CI / 批量脚本判断）。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_tree_svg import parse_newick, Node  # noqa: E402  复用同一个解析器，避免两套实现漂移

# 登录号：允许 NC_001343 / DQ822073 / PV235597 / MZ911846 这几种写法，可选版本号后缀。
# 早期版本漏了 `_?`，把 NC_* 全部判为不可识别（90/105 条被漏掉），交集因此算错。
ACC_RE = re.compile(r'([A-Z]{1,4}_?[0-9]{5,8})(?:\.[0-9]+)?$')
# 开头匹配用的版本：**不能用 label.split('_')[0]** —— RefSeq 登录号自带下划线，
# `NC_018616.1_Caulimovirus_xxx`.split('_')[0] 得到的是 'NC'，匹配不上，
# 于是 90/105 条叶名被判为"无登录号"，属单系性只剩 15 条可判（2026-09-22 踩过）。
ACC_HEAD_RE = re.compile(r'\s*([A-Z]{1,4}_?[0-9]{5,8})(?:\.[0-9]+)?')


def acc_of(label):
    """从叶名里抽出登录号。

    本库叶名形如 `DQ822073.1_Badnavirus_xxx`（登录号在**前**），
    ICTV 已发表树叶名形如 `Dioscorea_bacilliform_SN_virus_DQ822073`（登录号在**后**）。
    两种都支持：先在开头试，再在末尾试。
    """
    if not label:
        return None
    m = ACC_HEAD_RE.match(label)
    if m:
        return m.group(1)
    m = ACC_RE.search(label)
    return m.group(1) if m else None


def leaves(node, out=None):
    if out is None:
        out = []
    if node.ch:
        for c in node.ch:
            leaves(c, out)
    else:
        out.append(node.name)
    return out


def internals(node, out=None):
    if out is None:
        out = []
    if node.ch:
        out.append(node)
        for c in node.ch:
            internals(c, out)
    return out


def max_degree(node):
    d = len(node.ch)
    for c in node.ch:
        d = max(d, max_degree(c))
    return d


def branch_lengths(node, out=None):
    if out is None:
        out = []
    if node.bl is not None:
        out.append(node.bl)
    for c in node.ch:
        branch_lengths(c, out)
    return out


def clade_map(root):
    """返回 {frozenset(叶名): node}，只收录 ≥2 叶且不是全部叶的非平凡枝。"""
    allset = frozenset(leaves(root))
    out = {}

    def walk(n):
        if not n.ch:
            return frozenset([n.name])
        s = frozenset()
        for c in n.ch:
            s |= walk(c)
        if 2 <= len(s) < len(allset):
            out[s] = n
        return s

    walk(root)
    return out


def prune(root, keep):
    """把树剪到只剩 keep 里的叶，保留拓扑。

    为什么必须剪：判"属是否单系"只能在**有属名**的叶之间判。
    若树里混着没有分类归属的叶，它们可能恰好属于同一个属，
    直接判就会把本来单系的属误判成不单系（本脚本第一版就犯了这个错：
    拿 ICTV 图（96/108 条无属名）去测，Badnavirus 被误报"最小包含枝多 61 条"）。

    注意：单子节点会被折叠，折叠时父枝长丢失 —— 本函数只用于拓扑判定，
    不用它算枝长。
    """
    def walk(n):
        if not n.ch:
            return None if n.name not in keep else n
        kids = [k for k in (walk(c) for c in n.ch) if k is not None]
        if not kids:
            return None
        if len(kids) == 1:
            return kids[0]
        nn = Node()
        nn.ch = kids
        nn.sup = n.sup
        nn.bl = n.bl
        return nn

    return walk(root)


def read_manifest(path):
    """读 build_own_trees.py 的 manifest，返回 {登录号: 属}。跳过 # 注释块。"""
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
            a = acc_of(parts[0]) or parts[0]
            out[a] = parts[3]      # genus 在第 4 列
    return out


def check_monophyly(root, acc2genus):
    """逐属检查单系性。

    先在**有属名**的叶构成的子树上判（见 prune 的说明），返回
    (结果列表, 单系属数, 可检验属数, 无属名的叶, 全部叶数, 参与判定的叶数)。
    """
    lv = leaves(root)
    name2genus = {}
    unknown = []
    for name in lv:
        a = acc_of(name)
        g = acc2genus.get(a) if a else None
        if g:
            name2genus[name] = g
        else:
            unknown.append(name)

    sub = prune(root, set(name2genus))
    if sub is None:
        return [], 0, 0, unknown, len(lv), 0
    sub_leaves = leaves(sub)

    by_genus = {}
    for name in sub_leaves:
        by_genus.setdefault(name2genus[name], set()).add(name)

    cmap = clade_map(sub)
    sub_all = frozenset(sub_leaves)

    results = []
    for g in sorted(by_genus, key=lambda k: (-len(by_genus[k]), k)):
        tips = by_genus[g]
        if len(tips) < 2:
            results.append((g, len(tips), None, None, []))
            continue
        key = frozenset(tips)
        if key in cmap or key == sub_all:
            results.append((g, len(tips), True, 0, []))
            continue
        # 不单系：找包含该属全部叶的**最小**枝（没有更小的就退回整棵子树）
        best = None
        for s in cmap:
            if tips <= s and (best is None or len(s) < len(best)):
                best = s
        if best is None:
            best = sub_all
        foreign = {}
        for name in best:
            fg = name2genus.get(name)
            if fg != g:
                foreign[fg or '(未知)'] = foreign.get(fg or '(未知)', 0) + 1
        results.append((g, len(tips), False, len(best) - len(tips),
                        sorted(foreign.items(), key=lambda kv: -kv[1])))

    n_chk = sum(1 for r in results if r[1] >= 2)
    n_mono = sum(1 for r in results if r[2] is True)
    return results, n_mono, n_chk, unknown, len(lv), len(sub_leaves)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--manifest', help='build_own_trees.py 的 manifest，用于取属名')
    ap.add_argument('--ref', help='ICTV 已发表树，用于对拍（可选）')
    ap.add_argument('--quiet', action='store_true', help='只打印结论，不打印明细')
    args = ap.parse_args()

    raw = open(args.tree, encoding='utf-8').read()
    root = parse_newick(raw)
    lv = leaves(root)
    iv = internals(root)

    print('=' * 74)
    print('树体检：%s' % args.tree)
    print('=' * 74)
    print('[结构]')
    print('  叶数            : %d' % len(lv))
    print('  内部节点数      : %d' % len(iv))
    print('  最大度          : %d   （=2 为严格二分叉；>2 为多分叉）' % max_degree(root))
    bls = branch_lengths(root)
    if bls:
        bls_s = sorted(bls)
        print('  枝长            : n=%d  min=%.6g  中位=%.6g  max=%.6g' %
              (len(bls), bls_s[0], bls_s[len(bls_s) // 2], bls_s[-1]))
        neg = [b for b in bls if b < 0]
        print('  负枝长          : %d %s' % (len(neg), '(异常！)' if neg else ''))
    sups = [n.sup for n in iv if n.sup is not None]
    print('  支持度          : %d 个内部节点有值' % len(sups))
    if sups:
        scaled = [s if s > 1 else s * 100 for s in sups]
        low = [s for s in scaled if s < 95]
        print('    <95 的         : %d 个 (%.1f%%)' % (len(low), 100.0 * len(low) / len(scaled)))
        print('    中位支持度     : %.1f' % sorted(scaled)[len(scaled) // 2])

    if not args.manifest:
        print('\n(未给 --manifest，跳过属单系性检查)')
        return 0

    acc2genus = read_manifest(args.manifest)
    print('\n[属的单系性]   manifest: %s' % args.manifest)
    results, n_mono, n_chk, unknown, n_all, n_sub = check_monophyly(root, acc2genus)
    print('  参与判定的叶: %d / %d' % (n_sub, n_all))
    if unknown:
        print('  无属名被剔除: %d 条%s' % (len(unknown),
                                        '' if args.quiet else '  例: ' + ', '.join(unknown[:3])))
        print('  （判单系性只在有属名的叶之间做；混入无归属的叶会把单系的属误判为不单系）')
    print('  %-18s %5s  %s' % ('属', '叶数', '判定'))
    print('  ' + '-' * 60)
    for g, n, mono, extra, foreign in results:
        if n < 2:
            verdict = '— (仅 1 条，单系性不可检验)'
        elif mono:
            verdict = '单系 ✓'
        else:
            verdict = '不单系 ✗  最小包含枝多 %s 条' % ('?' if extra is None else extra)
        print('  %-18s %5d  %s' % (g, n, verdict))
        if not mono and n >= 2 and foreign and not args.quiet:
            print('        混入: %s' % ', '.join('%s×%d' % (k, v) for k, v in foreign))
    print('  ' + '-' * 60)
    pct = (100.0 * n_mono / n_chk) if n_chk else 0.0
    print('  可检验属 %d 个，单系 %d 个 → %.1f%%' % (n_chk, n_mono, pct))
    print('  注：ICTV 分类假定每个属都是单系群，所以单系率是"树可不可信"的检验量。')
    print('      但下面那条 60% 的线是**本脚本自定的参考线，不是权威标准**，')
    print('      只用来把"明显是噪声"和"需要人工看"分开；判定口径应由老师定。')

    rc = 0
    map_ratio = (float(n_sub) / n_all) if n_all else 0.0
    if n_all and map_ratio < 0.5:
        print('  ** 只有 %.0f%% 的叶有属名，单系率不具代表性 —— 本条不作判据 **'
              % (100.0 * map_ratio))
    elif n_chk and pct < 60.0:
        print('  ** 单系率 < 60%%，树的可信度存疑（比对/修剪/模型需要复核）**')
        rc = 1

    if args.ref and os.path.exists(args.ref):
        print('\n[与 ICTV 已发表树对拍]   %s' % args.ref)
        ref = parse_newick(open(args.ref, encoding='utf-8').read())
        rl = leaves(ref)
        # 把两棵树的叶名统一成登录号
        def to_acc(names):
            m = {}
            for n in names:
                a = acc_of(n)
                if a and a not in m:
                    m[a] = n
            return m
        ma, mb = to_acc(lv), to_acc(rl)
        shared = sorted(set(ma) & set(mb))
        print('  本树叶数 %d（可识别 %d） / ICTV 树 %d（可识别 %d）' % (len(lv), len(ma), len(rl), len(mb)))
        print('  登录号交集: %d 条  (%.1f%% 的本树序列)' %
              (len(shared), 100.0 * len(shared) / max(1, len(ma))))
        if len(shared) < 4:
            print('  交集过小，不足以比较拓扑 —— 本条不作为判据。')
        else:
            keep_a = set(ma[a] for a in shared)
            keep_b = set(mb[a] for a in shared)

            def restricted(root_, keep):
                """剪到 keep 集合，并把叶名统一成登录号（复用 prune，避免两套剪枝实现）。"""
                r = prune(root_, keep)
                if r is None:
                    return None

                def relabel(n):
                    if not n.ch:
                        n.name = acc_of(n.name) or n.name
                    else:
                        for c in n.ch:
                            relabel(c)
                relabel(r)
                return r

            ta, tb = restricted(root, keep_a), restricted(ref, keep_b)
            if ta is None or tb is None:
                print('  剪枝后为空，跳过对拍。')
                ca = cb = {}
                ta = tb = None
            else:
                ca, cb = clade_map(ta), clade_map(tb)
            only_a = set(ca) - set(cb)
            only_b = set(cb) - set(ca)
            same = set(ca) & set(cb)
            print('  非平凡枝: 本树 %d / ICTV %d / 共有 %d' % (len(ca), len(cb), len(same)))
            print('  仅本树有 %d，仅 ICTV 有 %d' % (len(only_a), len(only_b)))
            if ca or cb:
                agree = 100.0 * len(same) / max(1, len(set(ca) | set(cb)))
                print('  枝集合一致率（Jaccard）: %.1f%%' % agree)
            print('  注意：交集只有 %d 条，且两棵树用的不是同一批分离株 ——' % len(shared))
            print('        这是**弱证据**，不能单独作为"树对不对"的判据。')
            if only_a and not args.quiet:
                for s in list(only_a)[:5]:
                    print('    仅本树: %s' % ', '.join(sorted(s)[:6]))
            if only_b and not args.quiet:
                for s in list(only_b)[:5]:
                    print('    仅ICTV: %s' % ', '.join(sorted(s)[:6]))

    print('\n结论: %s' % ('通过' if rc == 0 else '有检查项不通过'))
    return rc


if __name__ == '__main__':
    sys.exit(main())
