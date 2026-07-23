/* ============================================================
 * Plant Virus DB — i18n v3.0 (data-i18n attribute-based)
 * ============================================================
 * Lightweight language toggle using data-i18n="EN|ZH" attributes.
 * Only UI elements (nav, titles, cards) are translated.
 * Body paragraphs and data content remain in English.
 *
 * Usage:
 *   <script src="/i18n.js"></script>
 *   <!-- Elements with i18n support -->
 *   <a data-i18n="Reference|参考库" href="/reference/">Reference</a>
 *   <h1 data-i18n="Plant Virus DB|植物病毒数据库">Plant Virus DB</h1>
 *
 * State: localStorage 'pvdb_lang' = 'en' (default) | 'zh'
 * ============================================================ */
(function () {
  'use strict';

  var LANG_KEY = 'pvdb_lang';
  var lang = localStorage.getItem(LANG_KEY) || 'en';

  // ── Core: swap all data-i18n elements ────────────────────
  function swapLanguage(targetLang) {
    lang = targetLang;
    localStorage.setItem(LANG_KEY, lang);
    var idx = lang === 'en' ? 0 : 1;
    var els = document.querySelectorAll('[data-i18n]');
    els.forEach(function (el) {
      var parts = el.getAttribute('data-i18n').split('|');
      if (parts[idx] !== undefined && parts[idx].trim()) {
        el.textContent = parts[idx].trim();
      }
    });
    updateButtons();
  }

  // ── Toggle ──────────────────────────────────────────────
  function toggle() {
    swapLanguage(lang === 'en' ? 'zh' : 'en');
  }

  // ── Button injection ────────────────────────────────────
  function updateButtons() {
    var buttons = document.querySelectorAll('#pvdb-i18n-btn');
    buttons.forEach(function (btn) {
      btn.textContent = lang === 'en' ? '中' : 'EN';
    });
  }

  function injectButtons(container) {
    if (!container || container.querySelector('#pvdb-i18n-btn')) return;
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
    btn.textContent = lang === 'en' ? '中' : 'EN';
    btn.addEventListener('click', toggle);
    container.appendChild(btn);
  }

  // ── Init ────────────────────────────────────────────────
  function init() {
    // If saved lang is zh, apply Chinese text
    if (lang === 'zh') swapLanguage('zh');

    // Inject button into nav bars
    var navs = document.querySelectorAll('nav, .bar, .navbar');
    if (navs.length === 0) {
      var fb = document.createElement('div');
      fb.style.cssText = 'position:fixed;top:12px;right:12px;z-index:99999';
      document.body.appendChild(fb);
      injectButtons(fb);
    } else {
      navs.forEach(function (nav) { injectButtons(nav); });
    }
  }

  // ── Public API ──────────────────────────────────────────
  window.PVDB_i18n = { init: init, toggle: toggle, swap: swapLanguage, lang: function () { return lang; } };

  // Auto-init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
