# -*- coding: utf-8 -*-
"""
/eve/ Cases & QC 视图布局探针（只读线上页面，不改仓库任何文件）。

用途：
  1) 量取多 grid 视图的真实几何：每块 grid 的像素矩形、band（= 高/类目数）、
     块间距、画布空白占比 —— 用来判「留白是不是异常」。
  2) 把候选 grid 布局注入线上页面并截图，用于选型，不必先改源码。

用法：
  python probe_qc_layout.py measure          # 遍历全部视图，打印几何表
  python probe_qc_layout.py compare          # 渲染 现状 / A2 / B 并出对照图

依赖：playwright 只在 C:\\Python312\\python.exe 下可用；PIL 用于拼对照图。

踩坑（必读）：
  ECharts 的 setOption 只把组件标脏，真正渲染发生在下一帧。注入布局后立刻截图
  会截到【旧位图】，而几何读的是 model（已是新值）→ 会误判成「改了没生效」。
  注入后必须等一帧，或显式 inst.getZr().refresh()，再截图。
"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = "http://39.106.101.94/eve/"
VIEWS = ['virus', 'host', 'dnarna', 'matrix', 'past', 'amp', 'tree', 'qc']

MEASURE_JS = """() => {
  const el = document.getElementById('chart');
  const inst = echarts.getInstanceByDom(el);
  const opt = inst.getOption(); const H = el.clientHeight;
  const rows = (opt.grid || []).map((g, i) => {
    const r = inst.getModel().getComponent('grid', i).coordinateSystem.getRect();
    const n = (opt.yAxis && opt.yAxis[i] && opt.yAxis[i].data) ? opt.yAxis[i].data.length : null;
    return { i, topDecl: g.top, hDecl: g.height, y: +r.y.toFixed(1), h: +r.height.toFixed(1),
             bottom: +(r.y + r.height).toFixed(1), cats: n, band: n ? +(r.height / n).toFixed(1) : null };
  });
  const gaps = [];
  for (let i = 1; i < rows.length; i++) gaps.push(+(rows[i].y - rows[i - 1].bottom).toFixed(1));
  const content = rows.reduce((s, r) => s + r.h, 0);
  return { H, nGrid: rows.length, rows, gaps,
           tail: rows.length ? +(H - rows[rows.length - 1].bottom).toFixed(1) : null,
           blankPx: +(H - content).toFixed(1), blankPct: +(100 * (H - content) / H).toFixed(1) };
}"""

# 候选布局：key = 标签，chartH = 覆盖画布高度（None = 不动）
CAND = {
    "A2_uniform_band_685": {
        "chartH": None,
        "bar2": 20,   # 第二块 8 根柱在 48.6px 的 band 里，11px 会显得过细
        "grid": [
            {"left": 150, "right": 90, "top": "3%", "height": "14.2%"},
            {"left": 150, "right": 90, "top": "21.2%", "height": "56.7%"},
            {"left": 150, "right": 90, "top": "81.9%", "height": "14.2%"},
        ],
    },
    "B_compact_470": {
        "chartH": 470,
        "bar2": None,
        "grid": [
            {"left": 150, "right": 90, "top": "4.7%", "height": "17.9%"},
            {"left": 150, "right": 90, "top": "28.9%", "height": "40.9%"},
            {"left": 150, "right": 90, "top": "76.2%", "height": "17.9%"},
        ],
    },
}

APPLY_JS = """(cfg) => {
  const el = document.getElementById('chart');
  const inst = echarts.getInstanceByDom(el);
  if (cfg.chartH) { el.style.height = cfg.chartH + 'px'; }
  window.dispatchEvent(new Event('resize'));
  const patch = { grid: cfg.grid };
  if (cfg.bar2) patch.series = [{}, { barMaxWidth: cfg.bar2 }, {}];
  inst.setOption(patch);
  inst.getZr().refresh();
  return 1;
}"""


def measure():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1600, "height": 950})
        for v in VIEWS:
            pg.goto(BASE + "?view=" + v, wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(2500)
            try:
                g = pg.evaluate(MEASURE_JS)
            except Exception as e:                      # tree 视图没有 grid，会抛错
                print("%-8s n/a (%s)" % (v, str(e)[:60]))
                continue
            print("### %-8s H=%s nGrid=%s blank=%s%%" % (v, g["H"], g["nGrid"], g["blankPct"]))
            for r in g["rows"]:
                print("    grid%s decl(top=%s,h=%s) -> y=%s h=%s bottom=%s cats=%s band=%s"
                      % (r["i"], r["topDecl"], r["hDecl"], r["y"], r["h"], r["bottom"],
                         r["cats"], r["band"]))
            print("    gaps=%s tail=%s blankPx=%s" % (g["gaps"], g["tail"], g["blankPx"]))
        b.close()


def compare():
    shots = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        # 现状
        pg = b.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=2)
        pg.goto(BASE + "?view=qc", wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(2500)
        print("current:", json.dumps(pg.evaluate(MEASURE_JS), ensure_ascii=False))
        pg.locator("#chart").screenshot(path="shot_current.png")
        shots.append(("shot_current.png", "CURRENT  grid 30% / 18% / 18%"))
        pg.close()

        for name, cfg in CAND.items():
            pg = b.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=2)
            pg.goto(BASE + "?view=qc", wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(2000)
            pg.evaluate(APPLY_JS, cfg)
            print(name, ":", json.dumps(pg.evaluate(MEASURE_JS), ensure_ascii=False))
            pg.wait_for_timeout(800)                    # 等渲染帧，否则截到旧位图
            pg.locator("#chart").screenshot(path="shot_%s.png" % name)
            shots.append(("shot_%s.png" % name, name))
            pg.close()
        b.close()

    from PIL import Image, ImageDraw, ImageFont
    W, PAD, LH = 1180, 18, 30
    try:
        F = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 19)
    except Exception:
        F = ImageFont.load_default()
    ims = []
    for path, label in shots:
        im = Image.open(path).convert("RGB")
        im = im.resize((W, int(im.height * W / im.width)), Image.LANCZOS)
        ims.append((im, label))
    canvas = Image.new("RGB", (W + 2 * PAD, PAD + sum(i.height + LH + PAD for i, _ in ims)),
                       (245, 247, 250))
    d = ImageDraw.Draw(canvas)
    y = PAD
    for im, label in ims:
        d.text((PAD, y), label, font=F, fill=(19, 78, 111))
        y += LH
        canvas.paste(im, (PAD, y))
        d.rectangle([PAD - 1, y - 1, PAD + im.width, y + im.height], outline=(210, 220, 230))
        y += im.height + PAD
    canvas.save("QC_LAYOUT_COMPARE.png")
    print("saved QC_LAYOUT_COMPARE.png", canvas.size)


if __name__ == "__main__":
    (compare if (len(sys.argv) > 1 and sys.argv[1] == "compare") else measure)()
