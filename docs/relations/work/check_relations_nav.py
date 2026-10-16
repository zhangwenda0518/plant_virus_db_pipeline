# -*- coding: utf-8 -*-
"""验收 /relations/ 外壳「一个导航栏 + 四个真子页面 + 无重复标题」这套改动。

用法（随页面部署在 /relations/work/，默认打线上）：
    C:/Python312/python.exe check_relations_nav.py <outdir>
    # 换目标：REL_BASE=http://127.0.0.1:8899/relations/ ...
    # 反向对照：REL_PRE=<改动前 HTML 的**本地**路径> ...

反向对照（证明"改动前确实有两条导航栏 / 有重复标题"）：给 REL_PRE=<原始外壳 HTML 的
**本地**路径>，脚本用 page.route 把外壳换回原始版，断言那时内嵌 nav 是**可见**的、
.tabs 是 flex、graph/tvh 的重复标题数 ≥ 2。
原始副本在服务端是 docs/relations/index.html.bak_20260930b.subpages
（20,692 B / md5 76bb5cde…，被统一归档到 /opt/plant_virus_db/_archived_baks_20260930/docs/relations/；
该文件名被 nginx 的 `\\.bak[_.]` 规则拦成 404，取不到 HTTP，需先 scp 下来）：
    scp root@39.106.101.94:/opt/plant_virus_db/_archived_baks_20260930/docs/relations/\\
        index.html.bak_20260930b.subpages .tmp_relations_nav/live/index.html

四个已知坑（都写进了脚本，不是放宽）：
  * 外壳那个 400ms 轮询会被 iframe 里的力导向图推迟 2–5 秒 → /network/ 的高度要到
    约 6 秒才收敛。探针必须**静置 SETTLE_MS** 再量，否则会把「还没量到」误判成
    「高度收不回去」—— 3.2 秒窗口下踩过，结论整个反了（把好的候选判成坏的）。
  * documentElement.scrollHeight 会被**钳在 iframe 视口高度**上（/vector/ 实测
    html=1358 而真实内容 1318）→ 内容比窗口矮时该值不含信息，据此跳过 docHeight
    判据，改用「首个内容块上移量」。
  * 上述钳制曾让 /vector/ 底部**永久**留 41px 死空白（棘轮：只增不减）。已修
    （fitFrame 改量 body.scrollHeight），所以 KNOWN_DEAD 现在为空 —— 四视图都应 ≈0。
  * /network/（graph / tvh）的 body 是 `height:100vh` 的 flex 列 → 它的文档高度由
    iframe 视口反推（自指），跨态 docHeight 差不是单一信号，**不作像素断言**；
    改用精确的「首个内容块上移量 == nav 高 + .tabs 的 margin-top」。
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get('REL_BASE', 'http://39.106.101.94/relations/')
OUT = sys.argv[1] if len(sys.argv) > 1 else '.tmp_relations_nav/shots'
PRE = os.environ.get('REL_PRE') or None
SKIP = set(x for x in (os.environ.get('REL_SKIP') or '').split(',') if x)

os.makedirs(OUT, exist_ok=True)

VIEW_KEY = {'sankey': 'association', 'graph': 'network', 'tvh': 'network', 'vector': 'vector'}
ALL_VIEWS = ['sankey', 'graph', 'tvh', 'vector']
VIEWS = [v for v in ALL_VIEWS if v not in SKIP]

# 已知死空白期望值（iframe 高度 − 内层内容底部）。
# 2026-09-30：棘轮修掉**之前** /vector/ 恒为 41（= 被藏掉的 nav 高度），
# 修掉之后四个视图都应是 0。留成显式表：一旦哪个视图重新冒出死空白，测试立刻失败。
KNOWN_DEAD = {}

# iframe 里的力导向图会把外壳的 400ms 轮询推迟 2–5 秒（实测 /network/ 6 秒才收敛），
# 所以量之前必须静置。用 3 秒量会把「还没量到」当成「收不回去」。
SETTLE_MS = 7000

# 内层 #chart 的高度下限。藏掉内嵌 .tabs 后 /network/ 少 76px，而它的
# #chart{min-height:clamp(0,100vh-228,480)} 在 iframe 里是**自指**的（100vh = iframe 高），
# 于是画布会跟着缩（实测 480→363）。外壳注入的样式把它钉在 480px。
# 期望表（改后）：视图 → (.tabs 的 display, 是否有 #chart, 重复标题数)
EXPECT = {
    'sankey': ('absent', True,  0),   # /association/ 无 .tabs；但有 #chart（实测 816px）
    'graph':  ('none',   True,  0),   # /network/ 的 .tabs 在 DOM 里但被隐藏
    'tvh':    ('none',   True,  0),
    'vector': ('absent', False, 0),   # /vector/ 无 .tabs、无 #chart
}
# 反向对照用：原始版里哪些视图本来就有重复标题（= .tabs 在 iframe 里是可见的）。
# 注意这张表与 EXPECT 第三列语义相反（那是**改后**值），别混用。
HAD_DUP = {'sankey': False, 'graph': True, 'tvh': True, 'vector': False}
CHART_MIN = 480

PROBE = """() => {
  const nav = document.querySelector('body > nav');
  const lang = document.getElementById('pvdb-lang-btn') || document.getElementById('pvdb-i18n-btn');
  let first = null;
  for (const el of document.body.children) {
    if (['SCRIPT','STYLE','LINK','NAV','NOSCRIPT'].includes(el.tagName)) continue;
    const r = el.getBoundingClientRect();
    if (r.height > 0) { first = {tag: el.tagName, cls: String(el.className).slice(0,40),
                                 top: Math.round(r.top), h: Math.round(r.height)}; break; }
  }
  // 内容底部：所有非 fixed 可见子元素的最大 bottom（用于量 iframe 底部死空白）
  let bottom = 0;
  for (const el of document.body.children) {
    const cs = getComputedStyle(el);
    if (cs.position === 'fixed') continue;
    const r = el.getBoundingClientRect();
    if (r.height > 0) bottom = Math.max(bottom, r.bottom + window.scrollY);
  }
  // body>.tabs（/network/ 的 vh/tvh 切换条）的几何量：跨态比对「上移量」要用。
  const tabs = document.querySelector('body > .tabs');
  const tcs = tabs ? getComputedStyle(tabs) : null;
  const tabsVisible = !!(tcs && tcs.display !== 'none');
  return {
    navCount: document.querySelectorAll('body > nav').length,
    navDisplay: nav ? getComputedStyle(nav).display : null,
    navH: nav ? Math.round(nav.getBoundingClientRect().height) : null,
    langDisplay: lang ? getComputedStyle(lang).display : 'absent',
    first, docHeight: document.documentElement.scrollHeight,
    // 内容比视口矮时 documentElement.scrollHeight 会被钳到视口高度
    // （/vector/ 实测 html=1358 而 body 实际只有 1318）→ 该值不含信息。
    innerH: window.innerHeight,
    bodyScrollH: document.body ? document.body.scrollHeight : null,
    contentBottom: Math.round(bottom),
    dead: Math.round(window.innerHeight - bottom),
    tabsH: tabsVisible ? Math.round(tabs.getBoundingClientRect().height) : 0,
    tabsMT: tabsVisible ? Math.round(parseFloat(tcs.marginTop) || 0) : 0,
  };
}"""

# 外壳侧探针：直接伸进 iframe 的 contentDocument（同源）量「重复标题 / .stage 空白 /
# 画布高度 / .tabs 是否只剩一个空壳」。重复标题的判据：可见、有高度、innerText 里含
# "host network"、且没有更深的子元素也含 —— 即「最内层那个标题节点」，正是肉眼看到的重复。
SHELL_PROBE = """() => {
  const f = document.querySelector('#stage iframe:not([style*="hidden"])');
  if (!f) return {error: 'no-visible-iframe'};
  let d = null;
  try { d = f.contentDocument; } catch (e) { return {error: 'cross-origin'}; }
  if (!d) return {error: 'no-contentDocument'};
  const st = document.querySelector('#stage');
  let dup = 0;
  d.querySelectorAll('body *').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    if (el.getBoundingClientRect().height < 1) return;
    const t = (el.innerText || '').replace(/\\s+/g, ' ').trim().toLowerCase();
    if (t.indexOf('host network') < 0) return;
    const deeper = Array.from(el.children).some(c =>
      (c.innerText || '').replace(/\\s+/g, ' ').trim().toLowerCase().indexOf('host network') >= 0);
    if (!deeper) dup++;
  });
  const ch = d.querySelector('#chart');
  const tabs = d.querySelector('body > .tabs');
  return {
    iframeH: Math.round(f.getBoundingClientRect().height),
    stageH: Math.round(st.getBoundingClientRect().height),
    stageBlank: Math.round(st.getBoundingClientRect().height - f.getBoundingClientRect().height),
    dup: dup,
    chartH: ch ? Math.round(ch.getBoundingClientRect().height) : null,
    tabsDisplay: tabs ? getComputedStyle(tabs).display : 'absent',
    tabVH: !!d.querySelector('#tab-vh'),
    navDisplay: (() => { const n = d.querySelector('body > nav');
                         return n ? getComputedStyle(n).display : 'no-nav'; })(),
  };
}"""

fails, passes = [], []
def check(cond, msg):
    (passes if cond else fails).append(msg)
    print(('  PASS  ' if cond else '  FAIL  ') + msg)


def inner_probe(page, expect_hidden):
    # 切换视图时旧 iframe 会被置成 visibility:hidden 留在 stage 里（最多 2 个），
    # 所以必须挑「没有 hidden 的那一个」，否则探到的是上一个视图。
    page.wait_for_selector('#stage iframe:not([style*="hidden"])')
    nframes = len(page.query_selector_all('#stage iframe'))
    f = page.query_selector('#stage iframe:not([style*="hidden"])')
    fr = f.content_frame()
    fr.wait_for_load_state('load')
    page.wait_for_timeout(SETTLE_MS)
    print('    iframes in stage = %d' % nframes)
    d = fr.evaluate(PROBE)
    tag = ('navCount=%s navDisplay=%s navH=%s langDisplay=%s first=%s docH=%s innerH=%s bodyScrollH=%s'
           % (d['navCount'], d['navDisplay'], d['navH'], d['langDisplay'], d['first'],
              d['docHeight'], d['innerH'], d['bodyScrollH']))
    print('    probe: ' + tag)
    check(d['navCount'] == 1, 'iframe 内 body>nav 恰好 1 个（选择器命中目标）')
    if expect_hidden:
        check(d['navDisplay'] == 'none', 'iframe 内 nav 已被隐藏（display:none）')
        check(d['langDisplay'] in ('none', 'absent'), 'iframe 内语言按钮已隐藏')
        # 判据不能写「首个内容块 top<=N」——.tabs 自带 margin-top，各页不同。
        # 正确判据是「nav 自身不再占高度」，以及跨态比对文档高度差 == nav 高度。
        check(d['navH'] == 0, 'nav 不再占位（navH=0）')
    else:
        check(d['navDisplay'] not in (None, 'none'),
              '【反向对照】改动前 iframe 内 nav 是可见的（display=%s）' % d['navDisplay'])
        check(d['navH'] and d['navH'] > 20,
              '【反向对照】改动前 nav 实际占位 %s px' % d['navH'])
    return d


def shell_probe(page, v, with_pre):
    d = page.evaluate(SHELL_PROBE)
    print('    shell: %s' % d)
    if 'error' in d:
        check(False, '[%s] 外壳探针失败：%s' % (v, d['error']))
        return d
    exp_tabs, has_chart, _ = EXPECT[v]

    if with_pre:
        # 反向对照：只断言「改动前确实有重复 / .tabs 确实在显示」。
        # 这里**不能**断言 navDisplay=none / stageBlank=0 —— 那些是改后才成立的。
        if HAD_DUP[v]:
            check(d['dup'] >= 2, '[%s] 【反向对照】改动前重复标题数 %d ≥ 2' % (v, d['dup']))
            check(d['tabsDisplay'] == 'flex',
                  '[%s] 【反向对照】改动前 body>.tabs 是 flex（%s）' % (v, d['tabsDisplay']))
        else:
            check(d['dup'] == 0, '[%s] 【反向对照】该视图本就无重复（dup=%d）' % (v, d['dup']))
            check(d['tabsDisplay'] == 'absent',
                  '[%s] 【反向对照】该页本就没有 .tabs（%s）' % (v, d['tabsDisplay']))
        return d

    # ── 改动后 ──
    # ① iframe 高度必须正好填满 .stage（否则 .stage{min-height} 会撑出空白条）
    check(d['stageBlank'] == 0,
          '[%s] .stage 无空白（stageH %d − iframeH %d = %d）'
          % (v, d['stageH'], d['iframeH'], d['stageBlank']))
    # ② 内层 nav 在外壳里始终不可见（与语言无关）
    check(d['navDisplay'] in ('none', 'no-nav'),
          '[%s] iframe 内 nav 在外壳里不可见（%s）' % (v, d['navDisplay']))
    # ③ 不得有重复标题
    check(d['dup'] == 0, '[%s] 无重复标题（dup=%d）' % (v, d['dup']))
    # ④ .tabs 的处理：/network/ 留在 DOM（脚本要靠它）但隐藏；其余页本就没有
    check(d['tabsDisplay'] == exp_tabs,
          '[%s] body>.tabs display=%s（期望 %s）' % (v, d['tabsDisplay'], exp_tabs))
    if exp_tabs == 'none':
        check(d['tabVH'], '[%s] #tab-vh 仍在 DOM 里（内层脚本不被打断）' % v)
    # ⑤ 画布高度不得被 .tabs 的隐藏带塌
    if has_chart:
        check(d['chartH'] is not None and d['chartH'] >= CHART_MIN,
              '[%s] 内层 #chart 高度 %s ≥ %d（不被塌陷）' % (v, d['chartH'], CHART_MIN))
    else:
        check(d['chartH'] is None, '[%s] 该页无 #chart（%s）' % (v, d['chartH']))
    return d


def run(url, prefix, expect_hidden, with_pre=False):
    errs = []
    probes, shells = {}, {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={'width': 1440, 'height': 900})
        page = ctx.new_page()
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.on('console', lambda m: errs.append('console.error: ' + m.text)
                if m.type == 'error' else None)

        if with_pre:
            pre_bytes = open(PRE, 'rb').read()

            def handler(route, request):
                route.fulfill(status=200,
                              content_type='text/html; charset=utf-8',
                              body=pre_bytes)

            page.route('**/relations/', handler)

        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_selector('#stage iframe')

        # ── 外壳自身 ──
        outer = page.evaluate("""() => {
          const lb = document.querySelector('.acts #pvdb-lang-btn, .acts #pvdb-i18n-btn');
          const tb = document.querySelector('nav.topbar');
          return {langInActs: !!lb,
                  langVisible: lb ? getComputedStyle(lb).display !== 'none' : false,
                  topbar: !!tb,
                  vtabCount: document.querySelectorAll('.strip button.vtab').length,
                  bodyNavCount: document.querySelectorAll('body > nav').length};
        }""")
        print('    outer: %s' % outer)
        check(outer['langInActs'] and outer['langVisible'],
              '外壳语言按钮已收进 .acts 且可见')
        check(outer['topbar'], '外壳自己的 nav.topbar 仍在（唯一那条导航栏）')
        check(outer['bodyNavCount'] == 1, '外壳文档里 body>nav 只有 1 个')

        # ── 逐视图 ──
        for v in VIEWS:
            print('  [%s] %s' % (v, '反向对照（改动前）' if with_pre else '改动后'))
            page.evaluate("k => { location.hash = k; }", v)
            # 先等新 iframe 建出来、旧 iframe 被隐藏；真正的收敛交给 inner_probe 的静置。
            page.wait_for_timeout(1500)
            d = inner_probe(page, expect_hidden)
            probes[v] = d
            shells[v] = shell_probe(page, v, with_pre)
            if not with_pre:
                shot = os.path.join(OUT, '%s_%s.png' % (prefix, v))
                page.screenshot(path=shot)
                print('    shot: %s' % shot)

        # ── 功能探针（只在改动后跑）──
        if not with_pre:
            # strip 切换
            page.evaluate("location.hash='sankey'")
            page.wait_for_timeout(1500)
            page.click('.strip button.vtab[data-view="graph"]')
            page.wait_for_timeout(2000)
            on = page.get_attribute('.strip button.vtab.on', 'data-view')
            check(on == 'graph', 'strip 点击后高亮切到 graph（实际 %s）' % on)
            src = page.get_attribute('#stage iframe[src*="network"]', 'src')
            check(bool(src), '切到 graph 后 iframe src 指向 /network/')

            # 语言切换：先清 localStorage 回到 en，再点
            page.evaluate("localStorage.removeItem('pvdb_lang')")
            page.reload(wait_until='domcontentloaded')
            page.wait_for_selector('#stage iframe')
            page.wait_for_timeout(1500)
            page.click('.acts button.act.langtab')
            # 力导向图占着主线程时，点击事件的派发本身会排队（实测约 2 s），
            # 所以这里轮询等，别用固定等待。
            t = ''
            for _ in range(60):
                page.wait_for_timeout(100)
                t = page.inner_text('.strip button.vtab.on .t')
                if any('\u4e00' <= c <= '\u9fff' for c in t):
                    break
            check(any('\u4e00' <= c <= '\u9fff' for c in t),
                  '外壳语言按钮切到中文后视图名变中文（实际 %r）' % t)
            inner_txt = page.evaluate("""() => {
              const f = document.querySelector('#stage iframe:not([style*="hidden"])');
              try { const d = f.contentDocument; const nav = d.querySelector('body>nav');
                    return nav ? getComputedStyle(nav).display : 'no-nav'; }
              catch (e) { return 'err'; }
            }""")
            check(inner_txt == 'none', '切语言后 iframe 内 nav 仍隐藏（%s）' % inner_txt)

            # Open standalone
            with ctx.expect_page() as pi:
                page.click('#btn-open')
            np = pi.value
            np.wait_for_load_state('domcontentloaded')
            # 2026-09-30 起按钮改文案为「在新标签打开」，打开的是本页子页面，
            # 不再开独立路由 —— 期望值随之更新。
            check('/relations/#' + on in np.url,
                  '按钮打开本页子页面 /relations/#%s（%s）' % (on, np.url))
            np.close()

        b.close()

    for e in errs:
        print('    JSERROR: %s' % e)
    check(not errs, '无 pageerror / console.error（%d 条）' % len(errs))
    return probes, shells


print('=' * 72)
print('TARGET  %s   skip=%s' % (BASE, sorted(SKIP)))
print('=' * 72)
pre_probes, pre_shells = {}, {}
if PRE:
    print('--- 反向对照：改动前的外壳 HTML ---')
    pre_probes, pre_shells = run(BASE, 'pre', expect_hidden=False, with_pre=True)
    print('--- 改动后 ---')
post_probes, post_shells = run(BASE, 'post', expect_hidden=True)

# 跨态比对。判据是「藏在首个幸存内容块上面的东西」全部消失，一个像素不多不少：
#   * 无 .tabs 的页（sankey / vector）：PRE 的首个可见块就是正文 → 上移量 == nav 高。
#   * /network/（graph / tvh）：PRE 的首个可见块是 .tabs 本身 → 上移量 == nav 高 + .tabs 的
#     margin-top（实测 55 = 43 + 12），这个仍然是**精确**判据。
# 至于 /network/ 的**文档高度**差：它的 body 是 height:100vh 的 flex 列（文档高度由 iframe
# 视口反推，自指），且本次 POST 又钉了 #chart 的 min-height → 差值是多个信号叠加
# （实测 130，而 nav + .tabs 外框 = 43 + 76 + 12 = 131）。这里**不作像素断言**，
# 只保留精确的上移量判据，数值照实打印，免得把测试拟合到答案。
for v in VIEWS:
    a, b = pre_probes.get(v), post_probes.get(v)
    if a and b:
        has_tabs = a['tabsH'] > 0
        exp_shift = a['navH'] + (a['tabsMT'] if has_tabs else 0)
        shift = a['first']['top'] - b['first']['top']
        check(shift == exp_shift,
              '[%s] 首个内容块上移 %d px == 期望 %d px（navH %d%s）'
              % (v, shift, exp_shift, a['navH'],
                 ' + .tabs margin-top %d' % a['tabsMT'] if has_tabs else ''))
        if has_tabs:
            print('    NOTE  [%s] body 为 100vh flex 列（文档高度自指）且 POST 钉了 #chart '
                  '高度 → 跳过 docHeight 逐像素判据；实测 PRE docH %d、POST docH %d、差 %d'
                  '（nav %d + .tabs 外框 %d）'
                  % (v, a['docHeight'], b['docHeight'], a['docHeight'] - b['docHeight'],
                     a['navH'], a['tabsH'] + a['tabsMT']))
        else:
            # 钳制判据必须窄：只有当 body 内容比视口**矮**时，documentElement.scrollHeight
            # 才会被顶到视口高度、从而丢掉「缩短」的信息。用 docHeight<=innerH 会误判
            # ——「内容恰好填满视口」时也成立，等于到处跳过这条断言（第一版就这么写错了）。
            clamped = (a['bodyScrollH'] < a['innerH']) or (b['bodyScrollH'] < b['innerH'])
            if clamped:
                print('    NOTE  [%s] 文档高度被 iframe 视口钳制'
                      '（innerH %s/%s，scrollH %s/%s，bodyScrollH %s/%s）'
                      '→ docHeight 判据不适用，改用上一条'
                      % (v, a['innerH'], b['innerH'], a['docHeight'], b['docHeight'],
                         a['bodyScrollH'], b['bodyScrollH']))
            else:
                delta = a['docHeight'] - b['docHeight']
                check(delta == a['navH'],
                      '[%s] 文档高度减少 %d px == 改动前 nav 高度 %d px' % (v, delta, a['navH']))
        dead, known = b['dead'], KNOWN_DEAD.get(v, 0)
        check(abs(dead - known) <= 2,
              '[%s] iframe 底部死空白 %d px == 已知值 %d px' % (v, dead, known))

print('=' * 72)
print('RESULT  %d passed, %d failed' % (len(passes), len(fails)))
for f in fails:
    print('  FAIL: ' + f)
sys.exit(1 if fails else 0)
