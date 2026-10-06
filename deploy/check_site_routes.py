# -*- coding: utf-8 -*-
"""扫描 docs/ 下所有 HTML 引用的**根相对 URL**，逐个实测线上状态，
找出「本地有对应文件、线上却打不开（404 或落到 nginx 自带测试页）」的路由缺口。"""
import os, re, sys, urllib.request, urllib.error, collections

WS = r'D:\桌面\C-host_classify\plant_virus_db_pipeline'
DOCS = os.path.join(WS, 'docs')
BASE = 'http://39.106.101.94'
UA = {'User-Agent': 'Mozilla/5.0'}
STOCK_MARK = 'HTTP Server Test Page'   # nginx 发行版自带测试页的标志

# ---- 1. 收集根相对链接（含出现次数与来源文件）----
links = collections.defaultdict(lambda: {'n': 0, 'src': set()})
n_html = 0
for root, dirs, files in os.walk(DOCS):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for f in files:
        if not f.endswith('.html') or '.bak' in f:
            continue
        n_html += 1
        p = os.path.join(root, f)
        try:
            t = open(p, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        for m in re.finditer(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', t):
            u = m.group(1).strip()
            if not u.startswith('/') or u.startswith('//'):
                continue
            u = u.split('#')[0].split('?')[0]
            if not u:
                continue
            links[u]['n'] += 1
            if len(links[u]['src']) < 3:
                links[u]['src'].add(os.path.relpath(p, DOCS).replace(os.sep, '/'))
print('扫描 HTML %d 个，收集到根相对 URL %d 个' % (n_html, len(links)))

# ---- 2. 判断某 URL 在 docs/ 里有没有对应文件 ----
def maps_to_docs(u):
    rel = u.lstrip('/')
    if rel == '':
        return 'index.html'
    cand = os.path.join(DOCS, rel.replace('/', os.sep))
    if os.path.isfile(cand):
        return rel
    if os.path.isdir(cand):
        for idx in ('index.html', 'reference_index.html'):
            if os.path.isfile(os.path.join(cand, idx)):
                return rel.rstrip('/') + '/' + idx
    return None

# ---- 3. 实测 ----
def probe(u):
    req = urllib.request.Request(BASE + u, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            b = r.read()
            return r.status, len(b), (STOCK_MARK in b.decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        return e.code, 0, False
    except Exception as e:
        return -1, 0, False

rows = []
for u in sorted(links):
    rel = maps_to_docs(u)
    st, n, stock = probe(u)
    rows.append((u, rel, st, n, stock, links[u]['n'], sorted(links[u]['src'])))

# ---- 4. 分类输出 ----
gaps, ok_local, proxied = [], [], []
for u, rel, st, n, stock, cnt, src in rows:
    if rel:                                   # 本地有文件 → 应当 200 且不是测试页
        if st == 200 and not stock:
            ok_local.append((u, st, n, cnt))
        else:
            gaps.append((u, rel, st, n, stock, cnt, src))
    else:                                     # 本地没文件 → 应是后端路由/重定向
        proxied.append((u, st, n, stock, cnt, src))

print()
print('=== A. 本地有文件且线上正常（%d 个）===' % len(ok_local))
for u, st, n, cnt in ok_local:
    print('  200  %-52s %7d B  被引用 %d 次' % (u, n, cnt))

print()
print('=== B. **路由缺口**：本地有文件、线上却打不开（%d 个）===' % len(gaps))
for u, rel, st, n, stock, cnt, src in gaps:
    why = '落到 nginx 自带测试页' if stock else ('HTTP %d' % st if st > 0 else '取回失败')
    print('  %-46s 应→%-34s %-22s 被引用 %d 次' % (u, rel, why, cnt))
    print('        来源: %s' % ', '.join(src))

print()
print('=== C. 本地无对应文件（应为后端路由/重定向，仅供核对，%d 个）===' % len(proxied))
for u, st, n, stock, cnt, src in proxied:
    flag = '  <-- 注意：返回了自带测试页' if stock else ''
    print('  %-4s %-50s %7d B  引用 %d 次%s' % (st, u, n, cnt, flag))

print()
print('缺口数 =', len(gaps))
sys.exit(1 if gaps else 0)
