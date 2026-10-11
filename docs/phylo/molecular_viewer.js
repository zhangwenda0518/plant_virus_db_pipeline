/* molecular_viewer.js —— 「ICTV 分子进化树」视图脚本。
   原先是 /phylo/molecular/index.html 的内联脚本；2026-10-11 该页并入 /phylo/ 单页
   （顶栏「分类树 / 分子树」标签页切换）后抽出为本文件，由 /phylo/index.html 加载。
   与原版相比的差异（其余逻辑逐行未动，历史注释保留）：
     1. $() 统一加 m 前缀 —— 本视图元素 id 为 mchart/mdetail/…，避免与分类树视图冲突；
     2. 数据路径改为相对 /phylo/：molecular_trees.json 与 molecular/genus_map.json；
     3. 原 boot() 拆成 prepare()（填选择器/统计/URL 参数）与 startChart()
        （echarts.init + 首次渲染），后者延迟到标签页首次激活（见文末 PV.molStart）——
        对 display:none 的容器 echarts.init 拿到的是 0 尺寸，必须等视图可见；
     4. 布局切换按钮 id 从 mPhylo/mRadial 改为 mModePhylo/mModeRadial（同样避撞）。 */

(function () {
'use strict';

var DATA = null, CHART = null, HIT = null;
var state = {fam:'', treeId:'', mode:'phylo', support:0, useBL:true, showSup:true, showTip:true, colorGenus:true, q:''};

var SUP_COLOR = function (s) {
  if (s == null) return '#7c8b9a';
  if (s >= 0.95) return '#1e8449';
  if (s >= 0.80) return '#7dcea0';
  if (s >= 0.60) return '#d4ac0d';
  return '#cb4335';
};

/* ---- 按属着色 -----------------------------------------------------------
   genus_map.json 是 build_genus_map.py 产出的**派生**文件（只读 molecular_trees.json，
   后者 MD5 保持不变）。ICTV 的树文件叶子上没有分类阶元，这里的属是按 MSL41 的
   「缩写 + GENBANK accession」两列、**按科约束**映射出来的 —— 不是 ICTV 的原始标注。
   映射不到的叶显式标灰（UNMAPPED_COLOR），不做任何猜测。
   24 色定性调色板；同屏属数超过 24 时颜色循环，图例会标注这一点。 */
var GEN = null, PAL = {}, LAST = {t: null, root: null};
var PALETTE = (function () {
  var a = [];
  // 色相必须按 24 等分（i*15）而不是 i*30 —— i*30 每 12 步就绕回同一色相，
  // 24 个槽位实际只有 12 种颜色（踩过：Rhabdoviridae Fig4 的 60 个属只出 12 色）。
  // 明度奇偶交替，进一步把相邻色相拉开。
  for (var i = 0; i < 24; i++) a.push('hsl(' + (i * 15) + ',62%,' + (i % 2 ? 55 : 38) + '%)');
  return a;
})();
var UNMAPPED_COLOR = '#b9c4cf';
var REASON_EN = {
  'acc-not-in-msl41': 'accession not in MSL41',
  'name-not-in-msl41': 'name/abbreviation not in MSL41',
  'element-name': 'element name, no matching virus species'
};
var REASON_ZH = {
  'acc-not-in-msl41': '登录号不在 MSL41',
  'name-not-in-msl41': '毒名/缩写不在 MSL41',
  'element-name': '元件名，无对应病毒种'
};

function isZh() {
  return (document.documentElement.lang || '').indexOf('zh') === 0
    || document.body.getAttribute('data-lang') === 'zh';
}
function T(en, zh) { return isZh() ? zh : en; }

function treeGenus() {
  if (!GEN || !GEN.trees) return null;
  // 防御：state.treeId 历史上出现过被赋成**对象**的情况（见 prepare() 里的修复说明），
  // 一旦类型不对，查表会静默落空、整棵树变灰 —— 这里统一归一成 id 字符串。
  var tid = state.treeId;
  if (tid && typeof tid === 'object') tid = tid.id || '';
  return GEN.trees[tid || ''] || null;
}
function leafGenus(name) {
  var tg = treeGenus();
  if (!tg || !tg.genus || !name) return null;
  return tg.genus[name] || null;
}
/* 颜色按「该树出现的属名排序后依次取色」—— 同一视图内互不重复。
   实测 38 棵树里 35 棵 ≤12 个属、中位数只有 4 个属，所以这条策略在绝大多数树上
   都能真正把属分开；只有 Rhabdoviridae Fig4（60 属）会用到循环。 */
function buildPalette() {
  var out = {}, tg = treeGenus();
  if (!tg || !tg.genus) return out;
  var seen = {}, names = [];
  for (var k in tg.genus) {
    var g = tg.genus[k];
    if (!seen[g]) { seen[g] = 1; names.push(g); }
  }
  names.sort();
  for (var i = 0; i < names.length; i++) out[names[i]] = PALETTE[i % PALETTE.length];
  return out;
}
/* 末端基准色（不含搜索高亮/变暗，那两种语义各自保留在原处）。 */
function leafBaseColor(name) {
  if (!state.colorGenus || !GEN) return '#2e86c1';
  var g = leafGenus(name);
  if (!g) return UNMAPPED_COLOR;
  return PAL[g] || UNMAPPED_COLOR;
}
/* tooltip 里的「属」那一行 */
function genusRow(name) {
  if (!state.colorGenus || !GEN) return '';
  var g = leafGenus(name);
  if (g) return '<br>genus: <b style="color:' + (PAL[g] || '#1a5276') + '">' + esc(g) + '</b>';
  return '<br>genus: <span style="color:#95a5b5">' + T('not mapped', '未映射') + '</span>';
}
/* 属图例：只列**当前视图**（已按支持度合并后）里出现的属，按叶数降序。 */
function renderGenusLegend(t, root) {
  var el = $('genusLegend');
  if (!el) return;
  if (!state.colorGenus || !GEN || !treeGenus()) {
    el.style.display = 'none'; el.innerHTML = ''; return;
  }
  var leaves = [];
  if (root) collectLeaves(root, leaves, []);
  var cnt = {}, order = [], unmapped = 0;
  for (var i = 0; i < leaves.length; i++) {
    var g = leafGenus(leaves[i].node.n || '');
    if (!g) { unmapped++; continue; }
    if (!(g in cnt)) order.push(g);
    cnt[g] = (cnt[g] || 0) + 1;
  }
  order.sort(function (a, b) { return cnt[b] - cnt[a] || (a < b ? -1 : 1); });
  var h = '';
  for (var j = 0; j < order.length; j++) {
    var gg = order[j];
    h += '<span class="gi"><span class="sw" style="background:' + (PAL[gg] || UNMAPPED_COLOR) + '"></span>'
      + '<b>' + esc(gg) + '</b> <i>' + cnt[gg] + '</i></span>';
  }
  if (unmapped) {
    h += '<span class="gi"><span class="sw" style="background:' + UNMAPPED_COLOR + '"></span>'
      + '<span style="color:#8a99a8">' + T('not mapped', '未映射') + '</span> <i>' + unmapped + '</i></span>';
  }
  var notes = [T('Genus is mapped from ICTV MSL41 (family-constrained) — the tree files carry no taxonomic ranks.',
                 '属由 ICTV MSL41 按科约束映射得到 —— 树文件本身不带分类阶元。')];
  if (order.length > PALETTE.length) {
    notes.push(T('More than ' + PALETTE.length + ' genera — colours repeat.',
                 '属数超过 ' + PALETTE.length + '，颜色循环使用。'));
  }
  var tg = treeGenus();
  if (unmapped && tg && tg.unmappedReasons) {
    var top = null;
    for (var k in tg.unmappedReasons)
      if (!top || tg.unmappedReasons[k] > tg.unmappedReasons[top]) top = k;
    if (top) notes.push(T('main reason (whole tree): ' + REASON_EN[top],
                          '主要原因（整棵树）：' + REASON_ZH[top]));
  }
  h += '<span class="gsep"></span><span class="gnote">' + notes.join(' · ') + '</span>';
  el.innerHTML = h;
  el.style.display = '';
}

/* 元素 id 一律带 m 前缀（见文件头注释），$ 统一补前缀，调用点保持原名。 */
function $(id) { return document.getElementById('m' + id); }

function splitLeaf(name) {
  var s = String(name);
  var m = /^([A-Za-z]{1,4}_?\d{4,9}(?:\.\d+)?)[\s_-]+(.*)$/.exec(s);
  if (m) return {acc:m[1], sp:cleanSp(m[2])};
  return {acc:'', sp:cleanSp(s)};
}

/* ICTV 树文件的叶名是「登录号 + 基因/基因组描述」，含大量对读图无用的噪声词。
   这里只清洗**显示用**的短标签；tooltip 与详情面板始终给出原始全名。 */
function cleanSp(s) {
  var out = ' ' + String(s).replace(/_/g, ' ') + ' ';
  var prev;
  do {
    prev = out;
    out = out
      .replace(/\b(?:complete|full)\s+(?:genome|cds|sequence|length)\b/gi, ' ')
      .replace(/\bisolate\s+\S+/gi, ' ')
      .replace(/\bstrain\s+\S+/gi, ' ')
      .replace(/\bsegment\s+\S+/gi, ' ')
      .replace(/\bRNA[-\s]dependent\s+RNA\s+polymerase\b/gi, ' ')
      .replace(/\bRdRp\b/gi, ' ')
      .replace(/\btriple\s+gene\s+block\s+protein\s*\d*/gi, ' ')
      .replace(/\s*\([^)]*\)\s*/g, ' ');
  } while (out !== prev);
  out = out.replace(/^[\s_\-–—]+/, '');
  out = out.replace(/^(?:replicase|coat\s+protein|polyprotein|movement\s+protein|helicase|nucleoprotein|polymerase)\b[\s_\-–—]*/i, '');
  return out.replace(/\s+/g, ' ').trim() || String(s).replace(/_/g, ' ');
}

function countLeaves(n) {
  if (!n.ch || !n.ch.length) return 1;
  var t = 0;
  for (var i = 0; i < n.ch.length; i++) t += countLeaves(n.ch[i]);
  return t;
}

function collapse(node, thr, isRoot) {
  var ch = node.ch || [];
  var o = {};
  if (node.n) o.n = node.n;
  if (node.bl != null) o.bl = node.bl;
  if (node.s != null) o.s = node.s;
  if (!ch.length) return o;
  if (!isRoot && node.s != null && node.s < thr) {
    o.collapsed = countLeaves(node);
    return o;
  }
  o.ch = [];
  for (var i = 0; i < ch.length; i++) o.ch.push(collapse(ch[i], thr, false));
  return o;
}

function currentFamily() {
  for (var i = 0; i < DATA.families.length; i++)
    if (DATA.families[i].family === state.fam) return DATA.families[i];
  return null;
}
function currentTree() {
  var f = currentFamily();
  if (!f) return null;
  for (var i = 0; i < f.trees.length; i++)
    if (f.trees[i].id === state.treeId) return f.trees[i];
  return f.trees[0] || null;
}

function pruneEmpty(node) {
  if (!node.ch) return node;
  var keep = [];
  for (var i = 0; i < node.ch.length; i++) keep.push(pruneEmpty(node.ch[i]));
  node.ch = keep;
  return node;
}

function collectLeaves(node, out, path) {
  if (!node.ch || !node.ch.length) { out.push({node:node, path:path}); return; }
  for (var i = 0; i < node.ch.length; i++)
    collectLeaves(node.ch[i], out, path.concat([node]));
  return out;
}

function markHits(node, q) {
  var n = 0;
  if (node.ch && node.ch.length) {
    for (var i = 0; i < node.ch.length; i++) n += markHits(node.ch[i], q);
    node.hit = n > 0;
    node.hitN = n;
  } else {
    node.hit = q && String(node.n || '').toLowerCase().indexOf(q) >= 0;
    node.hitN = node.hit ? 1 : 0;
    n = node.hitN;
  }
  return n;
}

function leafGap(n) { return n > 400 ? 11 : (n > 220 ? 12 : (n > 120 ? 13 : 15)); }

function autoHeight(leafCount, radial) {
  var el = $('chart');
  var base = Math.max(520, window.innerHeight - 235);
  var h;
  if (radial) h = Math.max(620, base);
  else h = Math.min(Math.max(base, leafCount * leafGap(leafCount) + 56), 16000);
  if (el.style.height !== h + 'px') { el.style.height = h + 'px'; if (CHART) CHART.resize(); }
}

function render() {
  var t = currentTree();
  if (!t) return;
  var root = collapse(t.tree, state.support / 100, true);
  pruneEmpty(root);

  var leaves = [];
  collectLeaves(root, leaves, []);
  var leafN = leaves.length;

  if (state.q) markHits(root, state.q); else clearHits(root);

  PAL = (state.colorGenus && GEN) ? buildPalette() : {};
  LAST.t = t; LAST.root = root;

  $('chartTitle').textContent = t.id + (t.fig ? ' · Figure ' + t.fig : '');
  autoHeight(leafN, state.mode === 'radial');
  if (state.mode === 'radial') drawRadial(root, leafN, t);
  else drawPhylogram(root, leafN, t);
  updateDetail(t, root, leafN);
  renderGenusLegend(t, root);
}

function clearHits(node) {
  delete node.hit; delete node.hitN;
  if (node.ch) for (var i = 0; i < node.ch.length; i++) clearHits(node.ch[i]);
}

function dist2node(root, key, val, depth, cum) {
  root['_' + key] = val;
  var ch = root.ch || [];
  for (var i = 0; i < ch.length; i++) {
    dist2node(ch[i], key, val, depth, cum);
  }
}

function drawPhylogram(root, leafN, t) {
  var el = $('chart');
  var W = el.clientWidth || 900;
  var gap = leafGap(leafN);
  var padT = 26, padB = 26, padL = 14;
  var labelW = Math.min(300, Math.max(150, Math.round(W * 0.26)));
  var plotW = Math.max(160, W - padL - labelW);
  var H = leafN * gap + padT + padB;

  var useBL = state.useBL && t.stats.hasBranchLengths;

  (function setD(n, cum, depth) {
    n._d = useBL ? cum : depth;
    var ch = n.ch || [];
    for (var i = 0; i < ch.length; i++) setD(ch[i], cum + (ch[i].bl || 0), depth + 1);
  })(root, 0, 0);

  var yi = 0, maxD = 0;
  (function setY(n) {
    var ch = n.ch || [];
    if (!ch.length) {
      n._y = padT + yi * gap; yi++;
      if (n._d > maxD) maxD = n._d;
      return n._y;
    }
    var first = null, last = null;
    for (var i = 0; i < ch.length; i++) {
      var y = setY(ch[i]);
      if (first === null) first = y;
      last = y;
    }
    n._y = (first + last) / 2;
    return n._y;
  })(root);

  var scale = maxD > 0 ? plotW / maxD : 0;
  (function setX(n) {
    n._x = padL + n._d * scale;
    var ch = n.ch || [];
    for (var i = 0; i < ch.length; i++) setX(ch[i]);
  })(root);

  var lineData = [], ptData = [], supData = [];
  (function walk(n) {
    var ch = n.ch || [];
    if (!ch.length) {
      var sp = splitLeaf(n.n || '');
      var lbl = sp.sp.length > 46 ? sp.sp.slice(0, 45) + '…' : sp.sp;
      var item = {
        value: [n._x, n._y],
        symbolSize: n.hit ? 7 : 4,
        itemStyle: {color: n.hit ? '#e67e22' : (HIT ? '#b9c4cf' : leafBaseColor(n.n || ''))},
        _leaf: true,
        _name: n.n || '', _sp: sp.sp, _acc: sp.acc
      };
      if (state.showTip) {
        item.label = {
          show: true, position: 'right', distance: 5, fontSize: 11,
          color: n.hit ? '#c0392b' : '#3c4b5b',
          fontWeight: n.hit ? 'bold' : 'normal',
          formatter: lbl
        };
      }
      ptData.push(item);
      return;
    }
    ptData.push({
      value: [n._x, n._y],
      symbolSize: n.collapsed ? 8 : 3.5,
      itemStyle: {color: n.collapsed ? '#7d3c98' : SUP_COLOR(n.s)},
      _internal: true,
      _name: n.n || '', _s: n.s == null ? null : n.s,
      _collapsed: n.collapsed || 0,
      _leafN: countLeaves(n)
    });
    if (n.collapsed) {
      ptData[ptData.length - 1].label = {
        show: true, position: 'right', distance: 6, fontSize: 11,
        color: '#7d3c98', fontWeight: 'bold',
        formatter: '[' + n.collapsed + ' sequences]'
      };
    } else if (state.showSup && n.s != null) {
      supData.push({
        value: [n._x, n._y - 5],
        label: {
          show: true, position: 'top', fontSize: 9.5,
          color: SUP_COLOR(n.s),
          formatter: n.s.toFixed(2).replace(/0$/, '')
        },
        symbolSize: 0
      });
    }
    for (var i = 0; i < ch.length; i++) {
      var c = ch[i];
      // 折点顺序要紧：**竖线画在父节点的 x 上**，横线才落在子节点的 y 上，横线长度正好等于枝长。
      // 若写成 [[px,py],[cx,py],[cx,cy]]（横线画在父节点的 y 上），在等距 cladogram（枝长全等）里
      // 看不出问题；但本页默认按**真实枝长**定 x（state.useBL），长枝的横线会一路横扫并穿过
      // 沿途其它枝条的竖线 —— 实测 38 棵树共 1,397 处交叉、3,351 处共线重叠（Alphaflexiviridae Fig3 是 45 处）。
      lineData.push({coords: [[n._x, n._y], [n._x, c._y], [c._x, c._y]]});
      walk(c);
    }
  })(root);

  var opt = {
    animation: false,
    grid: {left: 0, right: 0, top: 0, bottom: 0, containLabel: false},
    xAxis: {type: 'value', min: 0, max: W, show: false},
    yAxis: {type: 'value', min: 0, max: H, inverse: true, show: false},
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,.97)',
      borderColor: '#dfe7ee', borderWidth: 1,
      textStyle: {color: '#2c3e50', fontSize: 12},
      formatter: function (p) {
        var d = p.data;
        if (!d || !d._leaf && !d._internal) return '';
        var rows = [];
        if (d._leaf) {
          rows.push('<b>' + esc(d._sp) + '</b>');
          if (d._acc) rows.push('<span style="color:#95a5b5">' + esc(d._acc) + '</span>');
          var gr = genusRow(d._name);
          if (gr) rows.push(gr.replace(/^<br>/, ''));
          rows.push('branch length: ' + (d.value[0] - padL > 0 ? '' : '') + fmtBL(d));
        } else {
          rows.push('<b>' + (d._collapsed ? '已合并分支' : '内部分支') + '</b>');
          rows.push('支持度 support: ' + (d._s == null ? '—' : d._s.toFixed(4)));
          rows.push('末端序列 tips: ' + d._leafN);
        }
        return rows.join('<br>');
      }
    },
    series: [
      {
        type: 'lines', coordinateSystem: 'cartesian2d', polyline: true, silent: true,
        data: lineData,
        lineStyle: {color: '#9fb0c0', width: 1, opacity: 1},
        z: 2
      },
      {
        type: 'scatter', coordinateSystem: 'cartesian2d', data: ptData,
        symbol: 'circle', z: 3, cursor: 'pointer',
        emphasis: {scale: 1.6}
      },
      {
        type: 'scatter', coordinateSystem: 'cartesian2d', data: supData,
        symbol: 'circle', silent: true, z: 4
      }
    ]
  };
  CHART.setOption(opt, true);
  CHART.off('click');
  CHART.on('click', function (p) { onNodeClick(p); });
}

function fmtBL(d) {
  return d && d._bl != null ? d._bl : '';
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function drawRadial(root, leafN, t) {
  var H = $('chart').clientHeight || 700;
  var sup = state.showSup;
  // 分子树的末端名很长，环形布局下 ECharts 要给标签留空间，会把树压得很小。
  // 因此只有末端很少时才默认显示标签，其余情况靠悬停 tooltip 查看。
  var RADIAL_LABELS = state.showTip && leafN <= 20;
  function conv(n) {
    var o = {};
    var sp = n.ch && n.ch.length ? null : splitLeaf(n.n || '');
    o.name = n.collapsed ? '[' + n.collapsed + ' sequences]'
      : (sp ? (sp.sp.length > 34 ? sp.sp.slice(0, 33) + '…' : sp.sp) : '');
    o._sup = n.s == null ? null : n.s;
    o._leaf = !(n.ch && n.ch.length);
    o._collapsed = n.collapsed || 0;
    o._leafN = countLeaves(n);
    o._name = n.n || '';
    if (sp) o._acc = sp.acc;
    o.hit = !!n.hit;
    // 颜色写在**数据层**：环形树是 `tree` 系列，series 级 itemStyle 回调里取不到挂在
    // 节点上的自定义字段（实测），数据层 itemStyle 才可靠（枝长树那边同理）。
    o.itemStyle = {color: n.hit ? '#e67e22' : leafBaseColor(n.n || '')};
    if (n.ch && n.ch.length) o.children = n.ch.map(conv);
    return o;
  }
  var data = conv(root);
  CHART.setOption({
    animation: false,
    tooltip: {
      trigger: 'item', triggerOn: 'mousemove',
      backgroundColor: 'rgba(255,255,255,.97)', borderColor: '#dfe7ee', borderWidth: 1,
      textStyle: {color: '#2c3e50', fontSize: 12},
      formatter: function (p) {
        var d = p.data || {};
        if (d._leaf) {
          var rows = ['<b>' + esc(d.name) + '</b>'];
          if (d._acc) rows.push('<span style="color:#95a5b5">' + esc(d._acc) + '</span>');
          var gr = genusRow(d._name);
          if (gr) rows.push(gr.replace(/^<br>/, ''));
          return rows.join('<br>');
        }
        return (d._collapsed ? '<b>已合并分支</b>' : '<b>内部分支</b>')
          + '<br>支持度 support: ' + (d._sup == null ? '—' : d._sup.toFixed(4))
          + '<br>末端序列 tips: ' + d._leafN;
      }
    },
    series: [{
      type: 'tree', layout: 'radial', roam: true, data: [data],
      initialTreeDepth: -1,
      symbol: 'circle',
      symbolSize: function (v, p) {
        var d = p.data || {};
        if (d._collapsed) return 7;
        if (!d._leaf) return 4;
        return d._sup != null ? 3 : 2.5;
      },
      itemStyle: {color: function (p) {
        var d = p.data || {};
        if (d.hit) return '#e67e22';
        if (d._leaf) return leafBaseColor(d._name);
        if (d._collapsed) return '#7d3c98';
        return SUP_COLOR(d._sup);
      }},
      lineStyle: {color: '#b8c6d2', width: 1},
      label: {
        show: sup, position: 'right', fontSize: 10.5, color: '#3c4b5b',
        formatter: function (p) {
          var d = p.data || {};
          if (d._leaf) return RADIAL_LABELS ? d.name : '';
          if (d._sup != null) return d._sup.toFixed(2);
          return '';
        }
      },
      leaves: {label: {show: RADIAL_LABELS, position: 'right', fontSize: 10.5, color: '#3c4b5b'}},
      expandAndCollapse: true,
      emphasis: {focus: 'descendant'}
    }]
  }, true);
  CHART.off('click');
  CHART.on('click', function (p) { onNodeClick(p); });
}

function onNodeClick(p) {
  var d = p && p.data;
  if (!d) return;
  $('detail').classList.add('open');
  if (d._leaf) {
    var full = d._name || d.name;
    var g = leafGenus(full);
    $('detailBody').innerHTML =
      '<div class="dt">' + esc(d._sp || d.name) + '</div>'
      + '<div class="sub">' + esc(d._acc || '') + '</div>'
      + ((state.colorGenus && GEN)
          ? '<div class="kv"><div class="c"><div class="l">' + T('GENUS', '属') + '</div>'
            + '<div class="v"' + (g ? ' style="color:' + (PAL[g] || '#1a5276') + '"' : '') + '>'
            + (g ? esc(g) : T('not mapped', '未映射')) + '</div></div></div>'
          : '')
      + '<div class="note">' + esc(full) + '</div>';
  } else {
    $('detailBody').innerHTML =
      '<div class="dt">' + (d._collapsed ? '已合并的分支' : '内部分支') + '</div>'
      + '<div class="sub">support ' + (d._s == null && d._sup == null ? '—'
        : (d._s != null ? d._s : d._sup).toFixed(4)) + '</div>'
      + '<div class="kv"><div class="c"><div class="l">TIPS</div><div class="v">'
      + (d._leafN || 0) + '</div></div></div>';
  }
}

function updateDetail(t, root, leafN) {
  var s = t.stats;
  var fam = currentFamily();
  var html = '';
  html += '<div class="dt">' + esc(t.id) + '</div>';
  html += '<div class="sub">' + esc(t.file) + '</div>';
  html += '<div class="kv">';
  html += kv('TIPS', leafN);
  html += kv('INTERNAL', s.internals);
  html += kv('BIFURCATING', s.binary ? 'yes' : 'no');
  html += kv('POLYTOMIES', s.polytomies);
  html += kv('SUPPORT MED', s.supportMed == null ? '—' : s.supportMed.toFixed(3));
  html += kv('MAX BRANCH', s.blMax == null ? '—' : s.blMax.toFixed(3));
  html += '</div>';
  html += '<div class="note" style="margin-bottom:10px">'
    + '<b>' + esc(fam ? fam.family : '') + '</b><br>'
    + 'source file: <a href="' + esc(t.url) + '" target="_blank" rel="noopener">ICTV</a>'
    + '</div>';

  if (state.q && root.hitN) {
    var leaves = [];
    collectLeaves(root, leaves, []);
    var hitList = leaves.filter(function (l) { return l.node.hit; });
    html += '<div class="ctl-title">MATCHES (' + hitList.length + ')</div>';
    html += '<div class="memlist">';
    hitList.slice(0, 300).forEach(function (l) {
      var sp = splitLeaf(l.node.n || '');
      html += '<div class="mi"><span class="acc">' + esc(sp.acc) + '</span>'
        + '<span class="sp">' + esc(sp.sp) + '</span></div>';
    });
    html += '</div>';
  } else if (state.support > 0) {
    var leaves2 = [];
    collectLeaves(root, leaves2, []);
    html += '<div class="ctl-title">COLLAPSED</div>';
    html += '<div class="note">' + leafN + ' tips remain after collapsing clades with support &lt; '
      + state.support + '%.</div>';
  }
  $('detailBody').innerHTML = html;
  if (state.q) $('detail').classList.add('open');
}

function kv(l, v) {
  return '<div class="c"><div class="l">' + l + '</div><div class="v">' + v + '</div></div>';
}

function fillFamilySelect() {
  var sel = $('famSel');
  sel.innerHTML = '';
  DATA.families.forEach(function (f) {
    var o = document.createElement('option');
    o.value = f.family;
    o.textContent = f.family + '  (' + f.trees.length + ')';
    sel.appendChild(o);
  });
}

function fillTreeSelect() {
  var f = currentFamily();
  var sel = $('treeSel');
  sel.innerHTML = '';
  if (!f) return;
  f.trees.forEach(function (t) {
    var o = document.createElement('option');
    o.value = t.id;
    var parts = [];
    if (t.fig) parts.push('Fig ' + t.fig);
    parts.push(t.stats.leaves + ' tips');
    o.textContent = parts.join(' · ') + ' — ' + t.file;
    sel.appendChild(o);
  });
  sel.value = state.treeId;
}

function prepare() {
  var fams = DATA.families;
  var totalTrees = 0, totalLeaves = 0, binary = 0;
  fams.forEach(function (f) {
    totalTrees += f.trees.length;
    f.trees.forEach(function (t) {
      totalLeaves += t.stats.leaves;
      if (t.stats.binary) binary++;
    });
  });
  $('s-fam').textContent = fams.length;
  $('s-tree').textContent = totalTrees;
  $('s-leaf').textContent = totalLeaves.toLocaleString();
  $('s-bin').textContent = binary + '/' + totalTrees;

  var q = new URLSearchParams(location.search);
  var wantFam = q.get('family');
  var wantTree = q.get('tree');
  state.mode = q.get('mode') === 'radial' ? 'radial' : 'phylo';
  if (q.get('sup')) state.support = Math.max(0, Math.min(100, parseInt(q.get('sup'), 10) || 0));
  if (q.get('bl') === '0') state.useBL = false;
  state.q = (q.get('q') || '').toLowerCase();

  fillFamilySelect();
  var f0 = null;
  for (var i = 0; i < fams.length; i++) if (fams[i].family === wantFam) f0 = fams[i];
  if (!f0) {
    // 默认挑一棵中等规模的树，避免一上来就是 578 个末端
    var best = null;
    fams.forEach(function (f) {
      f.trees.forEach(function (t) {
        var d = Math.abs(t.stats.leaves - 60);
        if (!best || d < best.d) best = {f: f, t: t, d: d};
      });
    });
    f0 = best ? best.f : fams[0];
    // 2026-09-23 修：这里原写作 `best ? best.t : f0.trees[0].id`，把**树对象**赋给了
    // state.treeId（应为 best.t.id）。currentTree() 在找不到匹配 id 时会静默回退到
    // f.trees[0]，所以平时看不出来；但它会让「挑一棵中等规模的树」这个意图失效，
    // 并让任何以 state.treeId 为键的查表（如 genus_map.json）全部落空。
    // 实测当前 best.t 恰是 best.f.trees[0]，故本修复不改变默认视图。
    state.treeId = wantTree || (best ? best.t.id : f0.trees[0].id);
  } else {
    state.treeId = wantTree || f0.trees[0].id;
  }
  state.fam = f0.family;
  if (!state.treeId) state.treeId = f0.trees[0].id;

  $('famSel').value = state.fam;
  fillTreeSelect();

  $('supRange').value = state.support;
  $('supVal').textContent = state.support;
  $('useBL').checked = state.useBL;
  $('showSup').checked = state.showSup;
  $('showTip').checked = state.showTip;
  $('colorGenus').checked = state.colorGenus;
  $('search').value = state.q;
  if (state.mode === 'radial') {
    $('ModeRadial').classList.add('on'); $('ModePhylo').classList.remove('on');
  }
}

/* startChart()：本视图首次可见后才允许调用（标签页控制器保证）。
   echarts.init 对 display:none 容器拿到 0 尺寸，不能在页面加载时就执行。 */
function startChart() {
  // 已初始化过（本次是再次切回标签页）：只需重新量尺寸 + 重绘
  if (CHART) { CHART.resize(); render(); return; }
  $('loading').style.display = 'none';
  $('chart').style.display = 'block';
  CHART = echarts.init($('chart'), null, {renderer: 'canvas'});
  render();
  // 字体/布局稳定后再量一次宽度，避免首帧 clientWidth 偏小导致树没铺满
  requestAnimationFrame(function () { if (CHART) { CHART.resize(); render(); } });

  window.addEventListener('resize', function () {
    if (CHART) { autoHeight(0, state.mode === 'radial'); CHART.resize(); render(); }
  });
}

function bindUI() {
  $('famSel').addEventListener('change', function () {
    state.fam = this.value;
    var f = currentFamily();
    state.treeId = f.trees[0].id;
    fillTreeSelect();
    render();
  });
  $('treeSel').addEventListener('change', function () {
    state.treeId = this.value;
    render();
  });
  $('supRange').addEventListener('input', function () {
    state.support = parseInt(this.value, 10) || 0;
    $('supVal').textContent = state.support;
    render();
  });
  $('useBL').addEventListener('change', function () { state.useBL = this.checked; render(); });
  $('showSup').addEventListener('change', function () { state.showSup = this.checked; render(); });
  $('showTip').addEventListener('change', function () { state.showTip = this.checked; render(); });
  $('colorGenus').addEventListener('change', function () {
    state.colorGenus = this.checked;
    // 换色属于「整棵树的样式变更」：ECharts 是增量更新，不先 clear() 会留旧色。
    if (CHART) CHART.clear();
    render();
  });
  var timer = null;
  $('search').addEventListener('input', function () {
    var v = this.value.trim().toLowerCase();
    clearTimeout(timer);
    timer = setTimeout(function () { state.q = v; render(); }, 220);
  });
  $('ModePhylo').addEventListener('click', function () {
    state.mode = 'phylo'; this.classList.add('on'); $('ModeRadial').classList.remove('on'); render();
  });
  $('ModeRadial').addEventListener('click', function () {
    state.mode = 'radial'; this.classList.add('on'); $('ModePhylo').classList.remove('on'); render();
  });
  $('btnReset').addEventListener('click', function () {
    state.support = 0; state.useBL = true; state.showSup = true; state.showTip = true;
    state.colorGenus = !!(GEN); state.q = '';
    $('supRange').value = 0; $('supVal').textContent = 0; $('search').value = '';
    $('useBL').checked = true; $('showSup').checked = true; $('showTip').checked = true;
    $('colorGenus').checked = state.colorGenus;
    if (CHART) CHART.clear();
    render();
  });
  $('btnFit').addEventListener('click', function () { render(); });
  $('btnPng').addEventListener('click', function () {
    if (!CHART) return;
    var url = CHART.getDataURL({type: 'png', pixelRatio: 2, backgroundColor: '#fff'});
    var a = document.createElement('a');
    a.href = url;
    a.download = state.treeId.replace(/[|]/g, '_') + '.png';
    a.click();
  });
}

function fixPlaceholders() {
  document.querySelectorAll('[data-i18n-ph]').forEach(function (el) {
    var parts = el.getAttribute('data-i18n-ph').split('|');
    var zh = (document.documentElement.lang || '').indexOf('zh') === 0
      || (document.body.getAttribute('data-lang') === 'zh');
    el.placeholder = zh && parts[1] ? parts[1] : parts[0];
  });
}

// 语言按钮的 id 随 i18n.js 版本变动（v3 用 pvdb-i18n-btn，v4 用 pvdb-lang-btn），
// 且按钮由 i18n.js 在运行时注入 —— 用文档级委托、两个 id 都认；
// 否则切语言后搜索框 placeholder 与属图例的说明文字仍停留在旧语言。
document.addEventListener('click', function (e) {
  var id = (e.target && e.target.id) || '';
  if (id === 'pvdb-lang-btn' || id === 'pvdb-i18n-btn') setTimeout(function () {
    fixPlaceholders();
    renderGenusLegend(LAST.t, LAST.root);   // 图例是动态生成的，i18n.js 管不到
  }, 0);
}, true);

// 两个数据源并行取。genus_map.json 是**派生**文件，取不到时页面必须与加它之前完全一致
// （此时把「按属着色」开关隐藏，不留一个点了没反应的控件）。
// 页面加载时就取数（共 ~380 KB，代价可忽略）；echarts.init 则推迟到标签页首次激活。
window.PV = window.PV || {};
var PV = window.PV;
/* 顶栏标签页控制器切到「Molecular trees」时调用。
   数据未就绪 → 只登记意愿，.then() 里数据一到立即开画；已初始化 → 重量尺寸重绘。 */
PV.molStart = function () {
  PV.molWanted = true;
  if (!DATA) return;
  startChart();
};

Promise.all([
  fetch('molecular_trees.json').then(function (r) { return r.json(); }),
  fetch('molecular/genus_map.json').then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; })
])
  .then(function (res) {
    DATA = res[0];
    GEN = res[1];
    if (!GEN) {
      state.colorGenus = false;
      var wrap = $('colorGenusWrap');
      if (wrap) wrap.style.display = 'none';
    }
    if (!DATA.families || !DATA.families.length) {
      $('loading').innerHTML = '<div class="emptyhint">No trees found.</div>';
      return;
    }
    bindUI();
    prepare();
    if (PV.molWanted) startChart();
    setTimeout(fixPlaceholders, 60);
  })
  .catch(function (e) {
    $('loading').innerHTML = '<div class="emptyhint">Failed to load molecular_trees.json<br>' + esc(e) + '</div>';
  });

})();
