/* 15 webapp 公共小工具：HTML 转义 + 页面级错误横幅。
   由 index.html / viewer.html 共用（viewer 曾因本地未定义 esc 整页脚本中断，
   统一从这里取，避免各页复制漂移）。stats.html 已于 2026-10-08 并入 index.html。 */
'use strict';
window.esc = function (s) {
  return String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
};
window.fatal = function (msg) {
  let bar = document.getElementById('app-error');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'app-error';
    bar.setAttribute('role', 'alert');
    bar.style.cssText = 'background:#fdecea;border:1px solid #f5c6c0;color:#9c1f16;' +
      'border-radius:8px;padding:10px 14px;font-size:13px;margin:14px 16px';
    document.body.prepend(bar);
  }
  bar.textContent = '⚠ ' + msg;
};
window.loadJSON = async function (urls) {
  try {
    return await Promise.all(urls.map(u => fetch(u).then(r => {
      if (!r.ok) throw new Error(u + ' → HTTP ' + r.status);
      return r.json();
    })));
  } catch (e) {
    fatal('数据加载失败：' + e.message + '（请确认从模块根目录起服务，且 webapp/data/ 存在）');
    throw e;
  }
};
