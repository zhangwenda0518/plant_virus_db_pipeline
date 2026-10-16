/* ============================================================
 * Plant Virus DB — i18n v4.0 (English / 中文 toggle)
 * ============================================================
 * Pages mark translatable text with:
 *   <h1 data-i18n="English text|中文翻译">English text</h1>
 *   <input data-i18n-ph="English|中文" data-i18n-title="English|中文">
 *     -> data-i18n-ph / data-i18n-title set the placeholder / title attribute
 * Language choice is persisted in localStorage (pvdb_lang).
 * A floating toggle button is injected on every page, and the
 * current module in the top nav is highlighted automatically.
 * ============================================================ */
(function () {
  'use strict';
  var KEY = 'pvdb_lang';

  function lang() {
    try { return localStorage.getItem(KEY) || 'en'; } catch (e) { return 'en'; }
  }

  function pair(v) {
    if (v == null) return null;
    var i = v.indexOf('|');
    if (i < 0) return { en: v, zh: null };
    return { en: v.slice(0, i), zh: v.slice(i + 1) };
  }

  // Only rewrite an attribute (placeholder / title) - never touches textContent.
  function applyAttr(attr, target, L) {
    var els = document.querySelectorAll("[" + attr + "]");
    for (var i = 0; i < els.length; i++) {
      var t = pair(els[i].getAttribute(attr));
      if (!t) continue;
      var v = (L === "zh" && t.zh) ? t.zh : t.en;
      if (v) els[i].setAttribute(target, v);
    }
  }

  function apply() {
    var L = lang();
    var els = document.querySelectorAll('[data-i18n]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var t = pair(el.getAttribute('data-i18n'));
      if (!t) continue;
      var txt = (L === 'zh' && t.zh) ? t.zh : t.en;
      if (txt) el.textContent = txt;
    }
    applyAttr("data-i18n-ph", "placeholder", L);
    applyAttr("data-i18n-title", "title", L);
    document.documentElement.lang = (L === 'zh') ? 'zh-CN' : 'en';
    var btn = document.getElementById('pvdb-lang-btn');
    if (btn) {
      btn.textContent = (L === 'zh') ? 'EN' : '中文';
      btn.title = (L === 'zh') ? 'Switch to English' : '切换到中文';
    }
  }

  function markActive() {
    var path = location.pathname;
    var links = document.querySelectorAll('nav a[href]');
    // 先找「完全相等」的那一项；若存在，就只高亮它，不再做前缀匹配。
    // 否则退回前缀匹配，保留「子页面高亮父导航项」的原行为。
    // 例：/reference/segmented.html 会同时前缀命中 /reference/ 与 /reference/segmented.html，
    //     旧逻辑把 Dashboard 和 Segmented 一起点亮 —— 2026-09-30 修复。
    var exact = null;
    for (var j = 0; j < links.length; j++) {
      var b = links[j];
      if (b.classList.contains('brand')) continue;
      var bh = b.getAttribute('href');
      if (!bh || bh === '#') continue;
      var bt = bh.split('?')[0].split('#')[0];
      if (bt !== '/' && path === bt) { exact = b; break; }
    }
    for (var i = 0; i < links.length; i++) {
      var a = links[i];
      var href = a.getAttribute('href');
      if (!href || href === '#') continue;
      var target = href.split('?')[0].split('#')[0];
      var isActive;
      if (target === '/') isActive = (path === '/');
      else if (exact) isActive = (a === exact);
      else isActive = path === target || path.indexOf(target) === 0;
      if (isActive && !a.classList.contains('brand')) a.classList.add('active');
    }
  }

  function setLang(L) {
    try { localStorage.setItem(KEY, L); } catch (e) {}
    apply();
    // 运行时生成的界面（如 DataTables）可注册此钩子重建自己
    if (window.PVDB_onLangChange) { try { window.PVDB_onLangChange(L); } catch (e) {} }
  }

  function injectToggle() {
    if (document.getElementById('pvdb-lang-btn')) return;
    var b = document.createElement('button');
    b.id = 'pvdb-lang-btn';
    b.textContent = (lang() === 'zh') ? 'EN' : '中文';
    b.title = (lang() === 'zh') ? 'Switch to English' : '切换到中文';
    b.style.cssText = 'position:fixed;left:18px;bottom:18px;z-index:99999;'
      + 'width:44px;height:44px;border-radius:50%;border:1px solid rgba(255,255,255,.35);'
      + 'background:linear-gradient(135deg,#1a5276,#2e86c1);color:#fff;font-size:13px;'
      + 'font-weight:600;cursor:pointer;box-shadow:0 4px 12px rgba(26,82,118,.4);font-family:inherit';
    b.onclick = function () { setLang(lang() === 'zh' ? 'en' : 'zh'); };
    document.body.appendChild(b);
  }

  function init() {
    apply();
    injectToggle();
    markActive();
  }

  window.PVDB_i18n = { init: init, apply: apply, setLang: setLang, lang: lang };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
