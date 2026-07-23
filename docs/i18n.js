/* ============================================================
 * Plant Virus DB — 中英文切换 i18n (language toggle) v2.0
 * ============================================================
 * v2.0 修复: 扩充字典覆盖所有页面可见文本, 实现真正的全局双向切换。
 * 设计原则: 只增不改。不修改任何已有 HTML 文本/结构。
 * 仅在 nav 注入一个 [中/EN] 按钮，切换时按字典替换文本节点。
 * 回滚: 删除页面里 <script src="/reference/i18n.js"> 即可。
 *
 * 用法 (每个页面 </body> 前):
 *   <script src="/reference/i18n.js"></script>
 *   <script>PVDB_i18n.init({navSelector:'nav,.bar'});</script>
 *
 * 状态保存: localStorage 'pvdb_lang' = 'zh' | 'en'
 * 默认语言: 'zh'
 * ============================================================ */
(function (global) {
  'use strict';

  // ── 翻译字典 ────────────────────────────────────────────
  // ZH2EN: 中文→英文 (切到英文时用)
  // 收录所有页面中的中文文本节点
  var ZH2EN = {
    '参考库': 'Reference',
    '浏览器': 'Explorer',
    '病毒详情': 'Virus',
    '引物': 'Primers',
    '媒介': 'Vector',
    '文献': 'Literature',
    '知识': 'Knowledge',
    '首页': 'Home',
    '浏览': 'Browse',
    '下载': 'Download',
    '病毒宿主类型': 'Virus Host Type',
    '分节段vs非分节段': 'Segmented vs Non-segmented',
    '保存': 'Save',
    '基因组结构 (Category)': 'Genome Structure (Category)',
    '病毒科 (Family)': 'Virus Family',
    '检索宿主物种 (Host)': 'Search Host Species',
    '分析目标国家/地区 (Country)': 'Target Country/Region',
    '目标病毒物种 (Virus Species)': 'Target Virus Species',
    '数据报告年度跨度': 'Report Year Span',
    '植物病毒引物数据库': 'Plant Virus Primer Database',
    '搜索引物': 'Search Primers',
    '病毒物种': 'Virus Species',
    '推荐引物': 'Recommended Primers',
    'qPCR 荧光定量': 'qPCR Quantitative',
    '全基因组平铺': 'Whole Genome Tiling',
    '可用 (60-79分)': 'Usable (60-79)',
    '数据下载': 'Data Download',
    '下载页面': 'Download Page',
    '导出全部 CSV': 'Export All CSV',
    '引物类型分布': 'Primer Type Distribution',
    '各类型评分最高物种 TOP5': 'Top 5 Species by Score per Type',
    '病毒名称/物种': 'Virus Name/Species',
    '引物类型': 'Primer Type',
    '全部': 'All',
    '设计工具': 'Design Tool',
    '推荐级别': 'Recommendation Level',
    '找到': 'Found',
    '物种': 'Species',
    '类型': 'Type',
    '产物': 'Product',
    '评分': 'Score',
    '操作': 'Action',
    '详情': 'Details',
    '未找到匹配的引物': 'No matching primers found',
    '基因组长度 (bp)': 'Genome Length (bp)',
    '导出 FASTA': 'Export FASTA',
    '导出 CSV': 'Export CSV',
    '引物详情': 'Primer Details',
    '基本信息': 'Basic Info',
    '对号': 'Pair No.',
    '设计方法': 'Design Method',
    '引物位置': 'Primer Position',
    '产物大小': 'Product Size',
    '引物序列': 'Primer Sequences',
    '复制': 'Copy',
    'TaqMan 探针': 'TaqMan Probe',
    '验证结果': 'Validation Results',
    '自身二聚体 (Fwd)': 'Self-Dimer (Fwd)',
    '自身二聚体 (Rev)': 'Self-Dimer (Rev)',
    '探针验证 (qPCR)': 'Probe Validation (qPCR)',
    '探针发夹 Tm': 'Probe Hairpin Tm',
    '探针自二聚体 ΔG': 'Probe Self-Dimer ΔG',
    '浏览物种': 'Browse Species',
    'PrimerDB AI助手': 'PrimerDB AI Assistant',
    'TSWV最佳PCR引物': 'Best PCR Primers for TSWV',
    'TMV的qPCR引物': 'qPCR Primers for TMV',
    'PCR vs qPCR对比': 'PCR vs qPCR Comparison',
    '引物评分说明': 'Primer Score Explanation',
    '已复制!': 'Copied!',
    '输入问题...': 'Type a question...',
    '发送': 'Send',
    '设置': 'Settings',
    '请求失败: ': 'Request failed: ',
    '你好！我是PrimerDB AI助手。可以直接点下方预设问题，或输入你的问题。': 'Hello! I am the PrimerDB AI Assistant. Click a preset question below or type your own.',
    'Quick fill (全长基因组):': 'Quick fill (full genome):',
    '病毒序列分类结果': 'Virus Sequence Classification',
    '病毒序列 (FASTA)': 'Virus Sequences (FASTA)',
    '病毒分类表 (TSV)': 'Virus Classification (TSV)',
    '显示 unclassified 结果': 'Show unclassified results',
    '每属仅展示前 5 个种（避免种级节点过多）': 'Only top 5 species per genus shown (to avoid too many species nodes)',
    '(被分类为病毒的 contig)': '(contigs classified as virus)',
    '个 contig，其中': ' contigs, of which',
    '图表概览（随筛选联动）': 'Charts Overview (linked to filters)',
    '预合并数据库': 'Merged Database',
    '个病毒': ' viruses',
    '两源都有': ' in both sources',
    '仅 VH': 'VH only',
    '仅 WUR': 'WUR only',
    'family 冲突': 'family conflicts',
    '全部传播途径 (WUR)': 'All Transmission Routes (WUR)',
    '全部媒介类别 (WUR)': 'All Vector Categories (WUR)',
    '全部昆虫机制 (VIP)': 'All Insect Mechanisms (VIP)',
    '来源': 'Source',
    '媒介-宿主关系': 'Vector-Host Relations',
    'WUR 媒介:': 'WUR Vector:',
    '参考文献': 'References',
    '文献 & 各自传播方式:': 'Literature & Transmission Modes:',
    '其余': 'remaining',
    '条见明细': 'records see details',
    '文献追踪': 'Literature Tracker',
    '精选论文 (AI 验证)': 'Curated Papers (AI Verified)',
    'Chunks': 'Chunks',
    'Qdrant Vectors': 'Qdrant Vectors',
    'RAG Knowledge Base Q&A': 'RAG Knowledge Base Q&A',
    'RAG Knowledge Base': 'RAG Knowledge Base',
    'Bare LLM': 'Bare LLM',
    'Hybrid (RAG+LLM)': 'Hybrid (RAG+LLM)',
    'Manual Literature Search': 'Manual Literature Search',
    'Keywords (PubMed syntax)': 'Keywords (PubMed syntax)',
    'Date From': 'Date From',
    'Date To': 'Date To',
    'Max Results': 'Max Results',
    'Search Literature': 'Search Literature',
    'Search Results': 'Search Results',
    '概要': 'Overview',
    'AI 综述': 'AI Summary',
    'AI 月度综述': 'AI Monthly Summary',
    '数据库统计': 'Database Stats',
    '你是谁?': 'Who are you?',
    '监测方案': 'Monitoring Plan',
    'AI 知识助手': 'AI Knowledge Assistant',
    'Plant Virus Knowledge Base': 'Plant Virus Knowledge Base',
    'Ask anything about plant viruses...': 'Ask anything about plant viruses...',
    'Loading...': 'Loading...',
    'Search': 'Search',
    'Ask': 'Ask',
    'AI助手': 'AI Assistant',
    'Explorer AI助手——植物病毒探索器': 'Explorer AI Assistant',
    'Vector AI助手——媒介-宿主关系': 'Vector AI Assistant',
    'Metabuli AI助手——序列分类': 'Metabuli AI Assistant',
    'Literature AI助手——文献追踪': 'Literature AI Assistant',
    'RefDB AI助手——参考数据库': 'RefDB AI Assistant',
    '探索器功能介绍': 'Explorer Features Guide',
    'CP变异分析解读': 'CP Variation Analysis',
    '全球分布特点': 'Global Distribution',
    '数据筛选方法': 'Data Filtering Methods',
    '植物病毒有多少个科？哪些科最大？': 'How many plant virus families? Largest ones?',
    '分节段病毒和非分节段病毒有什么区别？': 'Segmented vs non-segmented viruses: differences?',
    '植物病毒的主要宿主类型有哪些？': 'Main host types of plant viruses?',
    'dsDNA和ssRNA病毒在植物中各占多少？': 'dsDNA vs ssRNA proportions in plants?',
    '这个探索器有哪些功能？怎么使用？': 'Explorer features and how to use?',
    'CP基因变异分析图怎么看？': 'How to read CP gene variation charts?',
    '植物病毒在全球的分布有什么特点？': 'Global plant virus distribution patterns?',
    '如何筛选特定国家的病毒数据？': 'How to filter virus data by country?',
    '设计一个水稻条纹病毒的监测方案': 'Design Rice Stripe Virus monitoring plan',
    '请设计一个水稻条纹病毒的监测方案': 'Design a Rice Stripe Virus monitoring plan',
    '数据库有多少病毒记录': 'How many virus records are in the database?',
    '病毒科': 'Virus Families',
    '引物对': 'Primer Pairs',
    '输入病毒名称搜索...': 'Enter virus name to search...',
    '全来源': 'All Sources',
    '有冲突': 'Has Conflict',
    '全传播途径': 'All Transmission',
    '全媒介类别': 'All Vector Types',
    '高级筛选选项': 'Advanced Filters',
    '昆虫机制': 'Insect Mechanisms',
    '验证中': 'Verifying',
    '已验证': 'Verified',
    '结构化记录': 'Structured Records',
    '未提及': 'Not Mentioned',
    '全序列输入': 'Full Sequence Input',
    '全球参考病毒序列示例': 'Global Reference Sequence Examples',
    '示例用于快速体验Metabuli分析流程': 'Examples for quick Metabuli testing',
    '提供完整序列或部分序列均可，接受FASTA格式': 'Complete or partial sequences, FASTA format',
    '精选论文': 'Curated Papers',
    'ICTV / NCBI / ViralZone': 'ICTV / NCBI / ViralZone',
    '植物病毒文献中心 · 检索与追踪': 'Plant Virus Literature Hub',
    '文献挖掘与追踪': 'Literature Mining & Tracking',
    '论文追踪': 'Paper Tracker',
    '总计论文': 'Total Papers',
    '基因组结构 (分段 / 非分段)': 'Genome Structure (Segmented / Non-Segmented)',
    '序列完整性': 'Sequence Completeness',
    '年份数据源': 'Year Data Source',
    '过滤无采集日期记录 (NA)': 'Filter records without collection date (NA)',
    '重算数据流并生成图表': 'Recalculate & Generate Charts',
    '时空演变趋势图': 'Temporal Trends',
    '全基因组变异分析': 'Genome Variation Analysis',
    '高稳健序列数据库': 'Sequence Database',
    '宿主范围': 'Host Range',
    '媒介传播': 'Vector Transmission',
    '病毒档案': 'Virus Profile',
    '选择目标地区 → 可搜索': 'Select region → searchable',
    '全部物种 → 可搜索': 'All species → searchable',
    '全部科 → 可选': 'All families → selectable',
    '全部宿主 → 可搜索': 'All hosts → searchable',
    '全部类型': 'All Types',
    '拖动两端滑块选择起止年份': 'Drag slider to select year range',
    '请在上方选择一个病毒物种。': 'Please select a virus species above.',
    '请在上方选择一个病毒物种（下拉已跟随左侧筛选结果）。': 'Select a virus species above (dropdown follows filter results).',
    '请在左侧设置筛选并点击『重算数据流并生成图表』。': 'Set filters on the left and click Recalculate.',
    '请求失败:': 'Request failed:',
    '病毒筛选器': 'Virus Filter',
    '下拉选择病毒物种（跟随左侧筛选器结果）': 'Select virus species (follows filter results)',
    '输入物种名…如 Tomato mosaic virus': 'Type species name... e.g. Tomato mosaic virus',
    '输入物种名直达详情，或用下方下拉（跟随左侧筛选结果）。': 'Type species name to jump to details, or use dropdown below.',
    '采集年份': 'Collection Year',
    '主要宿主': 'Primary Host',
    '无足够年份数据绘制趋势。': 'Insufficient year data for trend chart.',
    '该物种暂无宿主数据。': 'No host data for this species.',
    '该物种暂无地理数据。': 'No geographic data for this species.',
    '该物种暂无引物数据。': 'No primer data for this species.',
    '未找到该病毒的媒介-宿主记录。': 'No vector-host records found for this virus.',
    '无数据': 'No Data',
    '自动 (采集>提交)': 'Auto (Collection > Release)',
    '仅采集年': 'Collection Year Only',
    '仅提交年': 'Release Year Only',
    '分段': 'Segmented',
    '非分段': 'Non-Segmented',
    '完整': 'Complete',
    '部分': 'Partial',
    '序列数': 'Sequences',
    '条序列': 'sequences',
    'No input selected': 'No input selected',
    'Start Classification': 'Start Classification',
    '1. Input Sequence': '1. Input Sequence',
    '2. Classify': '2. Classify',
    '3. Results': '3. Results',
    'Or paste FASTA sequence(s) here...': 'Or paste FASTA sequence(s) here...',
    'Results': 'Results',
    'No results': 'No results',
    '助手': 'Assistant',
    '植物病毒科分类': 'Plant Virus Family Classification',
    
    
    '和': 'and',
    '病毒在植物中各占多少？': 'Proportions in plants?',
    '基因组类型分布': 'Genome Type Distribution',
    '你好！你好！我是': 'Hello! I am',
    '助手。可以直接点下方预设问题，或输入你的问题。': 'You can click preset questions below or type your own.',
    
    '为': 'for',
    '种植物病毒设计了': 'plant virus species designed',
    '对': 'pairs',
    '引物，': 'primers,',
    '覆盖植物病毒主要科属，支持保守区检测、简并引物和多重平铺扩增。': 'Covering major plant virus families, supporting conserved region detection, degenerate primers, and multiplex tiling amplification.',
    
    '例如': 'e.g.',
    '快速入口': 'Quick Links',
    '按引物类型': 'By Primer Type',
    '常规检测': 'Conventional Detection',
    '仅': 'Only',
    '冲突': 'Conflict',
    '全部传播途径': 'All Transmission Routes',
    '全部媒介类别': 'All Vector Categories',
    '全部昆虫机制': 'All Insect Mechanisms',
    '图表概览': 'Chart Overview',
    '验证': 'Verify',
    '基因变异分析图怎么看？': 'How to read gene variation charts?',
    '变异分析解读': 'Variation Analysis Guide',
    
    '基因组结构': 'Genome Structure',
    '分析目标国家': 'Target Country',
    '地区': 'Region',
    '目标病毒物种': 'Target Virus Species',
    '你是谁': 'Who are you?',
    '搜索': 'Search',
    '荧光定量': 'qPCR Quantitative',
    '简并引物': 'Degenerate Primers',
    '按评分': 'By Score',
    '推荐使用': 'Recommended',
    '分': 'pts',
    '可用': 'Usable',
    '导出全部': 'Export All',
    '各类型评分最高物种': 'Top Species by Score',
    '的最佳': 'best',
    '分节段': 'Segmented Type',
    '非分节段': 'Non-Segmented Type',
    '输入问题': 'Type question...',
    '检索宿主种类': 'Search Host Species',
    '你好！我是': 'Hello! I am',
    '引物有哪些？': 'primers are available?',
    '最佳': 'best',
    '推荐检测': 'recommended for detection',
    '比较': 'compare',
    '引物的优缺点': 'primer pros and cons',
    '对比': 'comparison',
    '引物评分': 'primer score',
    '是什么意思？': 'what does it mean?',
    '输入病毒名称搜索': 'Enter virus name to search',
  };

  // EN2ZH: 英文→中文 (自动从 ZH2EN 反向生成, 确保无冲突)
  var EN2ZH = {};
  Object.keys(ZH2EN).forEach(function (zh) {
    var en = ZH2EN[zh];
    // 只收录: 值非空、不等于 key、key 含中文的条目
    if (en && en !== zh && /[\u4e00-\u9fff]/.test(zh)) {
      EN2ZH[en] = zh;
    }
  });

  // ── 工具: 文本节点遍历替换 ──────────────────────────────
  function replaceText(root, dict) {
    if (!root) return 0;
    var count = 0;
    var walker = document.createTreeWalker(
      root, NodeFilter.SHOW_TEXT, null, false
    );
    var nodes = [];
    var n;
    while ((n = walker.nextNode())) {
      var p = n.parentNode;
      if (!p) continue;
      var tag = p.nodeName;
      if (tag === 'SCRIPT' || tag === 'STYLE') continue;
      nodes.push(n);
    }
    nodes.forEach(function (node) {
      var raw = node.nodeValue;
      var key = raw.trim();
      if (!key) return;
      // 仅精确匹配 (不做子串替换, 避免动态标签双重替换)
      if (Object.prototype.hasOwnProperty.call(dict, key)) {
        var lead = raw.match(/^\s*/)[0];
        var trail = raw.match(/\s*$/)[0];
        var newVal = lead + dict[key] + trail;
        if (newVal !== raw) {
          node.nodeValue = newVal;
          count++;
        }
      }
    });
    return count;
  }

  // ── 按钮注入 ────────────────────────────────────────────
  function injectButton(navEl, lang, onToggle) {
    if (!navEl || navEl.querySelector('#pvdb-i18n-btn')) return;
    var btn = document.createElement('button');
    btn.id = 'pvdb-i18n-btn';
    btn.type = 'button';
    btn.title = 'Switch language / 切换语言';
    btn.style.cssText = [
      'margin-left:auto',
      'background:rgba(255,255,255,.15)',
      'color:#fff',
      'border:1px solid rgba(255,255,255,.4)',
      'border-radius:6px',
      'padding:4px 10px',
      'font-size:12px',
      'font-weight:600',
      'cursor:pointer',
      'white-space:nowrap',
      'flex-shrink:0'
    ].join(';');
    function label() { return lang === 'zh' ? 'EN' : '中'; }
    btn.textContent = label();
    btn.addEventListener('click', function () {
      lang = lang === 'zh' ? 'en' : 'zh';
      localStorage.setItem('pvdb_lang', lang);
      btn.textContent = label();
      onToggle(lang);
    });
    navEl.appendChild(btn);
  }

  // ── 字体缩放 ────────────────────────────────────────────
  // 全局字体大小调整: 注入 CSS 用 --pvdb-fz 系数对所有常见文本元素按比例缩放
  // 三档: 小(0.9) / 标准(1) / 大(1.15)，存 localStorage 'pvdb_fz'
  var FZ_LEVELS = [0.9, 1, 1.15];
  var FZ_DEFAULT = 1.08;  // 默认略大，提升可读性
  var FZ_STYLE_ID = 'pvdb-font-scale-style';

  function ensureFontStyle() {
    if (document.getElementById(FZ_STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = FZ_STYLE_ID;
    // 对常见文本元素按系数缩放; 用 !important 覆盖页面内联 px
    // 系数通过 --pvdb-fz 控制 (0.9/1/1.15)
    s.textContent = [
      ':root{--pvdb-fz:' + FZ_DEFAULT + '}',
      'body{font-size:calc(15px * var(--pvdb-fz))!important}',
      'nav,nav a,nav .brand,.bar,.bar a,.navbar{font-size:calc(14px * var(--pvdb-fz))!important}',
      'h1{font-size:calc(26px * var(--pvdb-fz))!important}',
      'h2{font-size:calc(20px * var(--pvdb-fz))!important}',
      'h3{font-size:calc(16px * var(--pvdb-fz))!important}',
      'h4,h5{font-size:calc(14px * var(--pvdb-fz))!important}',
      'p,.card p,.intro p,.hero p{font-size:calc(13.5px * var(--pvdb-fz))!important}',
      'button,input,select,textarea{font-size:calc(14px * var(--pvdb-fz))!important}',
      'table,table td,table th{font-size:calc(13px * var(--pvdb-fz))!important}',
      '.kpi .val{font-size:calc(26px * var(--pvdb-fz))!important}',
      '.kpi .lbl,.stat .lbl{font-size:calc(11px * var(--pvdb-fz))!important}',
      '.stat .val{font-size:calc(22px * var(--pvdb-fz))!important}',
      '.card h3,.c h3,.section h2{font-size:calc(15px * var(--pvdb-fz))!important}',
      '.r-title,.vname{font-size:calc(15px * var(--pvdb-fz))!important}',
      '.r-text,.vdetail,.r-meta span,.badge,.tag{font-size:calc(13px * var(--pvdb-fz))!important}',
      '.hero h1{font-size:calc(24px * var(--pvdb-fz))!important}',
      '.section-title{font-size:calc(18px * var(--pvdb-fz))!important}',
      'footer,.footer{font-size:calc(12px * var(--pvdb-fz))!important}',
      '.examples a,.preset-q{font-size:calc(12px * var(--pvdb-fz))!important}',
      '.ai-out,#answer,#citations{font-size:calc(13px * var(--pvdb-fz))!important}'
    ].join('\n');
    document.head.appendChild(s);
  }

  function applyFontScale(fz) {
    document.documentElement.style.setProperty('--pvdb-fz', fz);
    localStorage.setItem('pvdb_fz', fz);
  }

  function injectFontButtons(navEl) {
    if (!navEl || navEl.querySelector('#pvdb-font-group')) return;
    var saved = parseFloat(localStorage.getItem('pvdb_fz'));
    if (!saved || isNaN(saved)) saved = FZ_DEFAULT;
    var group = document.createElement('div');
    group.id = 'pvdb-font-group';
    group.style.cssText = 'display:flex;gap:2px;margin-left:6px;flex-shrink:0';
    var btnStyle = 'background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.4);border-radius:6px;padding:4px 8px;cursor:pointer;font-weight:700;white-space:nowrap;line-height:1';
    var labels = { '0.9': 'A⁻', '1': 'A', '1.15': 'A⁺' };
    FZ_LEVELS.forEach(function (lvl) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = labels[String(lvl)];
      b.title = lvl === 0.9 ? '较小' : (lvl === 1 ? '标准' : '较大');
      b.dataset.fz = lvl;
      b.style.cssText = btnStyle;
      // 高亮当前档
      if (Math.abs(saved - lvl) < 0.01) {
        b.style.background = 'rgba(255,255,255,.35)';
      }
      b.addEventListener('click', function () {
        applyFontScale(lvl);
        group.querySelectorAll('button').forEach(function (x) {
          x.style.background = 'rgba(255,255,255,.15)';
        });
        b.style.background = 'rgba(255,255,255,.35)';
      });
      group.appendChild(b);
    });
    navEl.appendChild(group);
  }

  // ── 公共 API ────────────────────────────────────────────
  var PVDB_i18n = {
    version: '2.0.0',
    lang: 'en',

    init: function (opts) {
      opts = opts || {};
      var navSelector = opts.navSelector || 'nav, .bar, .navbar';
      var saved = localStorage.getItem('pvdb_lang');
      if (saved === 'en' || saved === 'zh') this.lang = saved;

      var self = this;
      function apply(lang) {
        self.lang = lang;
        var dict = lang === 'en' ? ZH2EN : EN2ZH;
        replaceText(document.body, dict);
      }
      // 首次应用: 若用户上次选 zh, 则把英文翻成中文; 默认 en, 把中文翻成英文(全站统一英文)
      // 默认 en: 应用 ZH2EN 让所有中文变英文
      apply(this.lang);

      // 注入按钮
      var navs = document.querySelectorAll(navSelector);
      if (navs.length === 0) {
        var fb = document.createElement('div');
        fb.style.cssText = 'position:fixed;top:12px;right:12px;z-index:99999';
        document.body.appendChild(fb);
        injectButton(fb, this.lang, apply);
        injectFontButtons(fb);
      } else {
        navs.forEach(function (nav) { injectButton(nav, self.lang, apply); injectFontButtons(nav); });
      }

      // 字体缩放: 注入全局 CSS + 应用上次选择
      ensureFontStyle();
      var savedFz = parseFloat(localStorage.getItem('pvdb_fz'));
      if (!savedFz || isNaN(savedFz)) savedFz = FZ_DEFAULT;
      applyFontScale(savedFz);

      // 监听动态插入的 DOM 自动翻译 (debounce 500ms, 避免数据密集页面卡顿)
      if ('MutationObserver' in global) {
        var pendingNodes = [];
        var moTimer = null;
        var mo = new MutationObserver(function (muts) {
          muts.forEach(function (m) {
            m.addedNodes.forEach(function (node) {
              if (node.nodeType === 1) pendingNodes.push(node);
            });
          });
          if (moTimer) clearTimeout(moTimer);
          moTimer = setTimeout(function () {
            var dict = self.lang === 'en' ? ZH2EN : EN2ZH;
            pendingNodes.forEach(function (node) { replaceText(node, dict); });
            pendingNodes = [];
            moTimer = null;
          }, 500);
        });
        mo.observe(document.body, { childList: true, subtree: true });
      }
    },

    toggle: function () {
      var btn = document.getElementById('pvdb-i18n-btn');
      if (btn) btn.click();
    },

    dict: { zh2en: ZH2EN, en2zh: EN2ZH }
  };

  global.PVDB_i18n = PVDB_i18n;
})(window);
