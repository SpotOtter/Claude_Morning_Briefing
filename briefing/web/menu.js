/* Shared hamburger menu. To add a page, add one line to PAGES; every page that loads this file gets it.
   A page opts in with <script src="/menu.js"></script> and one container marked data-menu-host
   (position: relative). Optional colors: --menu-ink and --menu-line on that container. */
(function () {
  var PAGES = [
    ['Briefing', '/'],
    ['Driver sign-in', '/drivers']
  ];
  var css = '.menu-btn{position:absolute;top:12px;right:max(12px,env(safe-area-inset-right,0px));z-index:5;width:44px;height:44px;display:inline-flex;align-items:center;justify-content:center;border-radius:10px;border:1px solid var(--menu-line,currentColor);background:transparent;color:var(--menu-ink,inherit);cursor:pointer;padding:0}' +
    '.menu-btn:hover{border-color:var(--menu-ink,currentColor)}' +
    '.menu-btn:focus-visible,.menu-panel a:focus-visible{outline:3px solid var(--mark,#e8a317);outline-offset:2px}' +
    '.menu-panel{position:absolute;top:62px;right:max(12px,env(safe-area-inset-right,0px));z-index:5;min-width:200px;background:var(--surface,#fff);color:var(--ink,#1d1f1c);border:1px solid var(--line,#ddd);border-radius:12px;padding:6px;box-shadow:0 8px 24px rgba(0,0,0,.25)}' +
    '.menu-panel[hidden]{display:none}' +
    '.menu-panel a{display:block;padding:13px 14px;border-radius:8px;text-decoration:none;color:inherit;font:600 17px/1.2 var(--font-body,system-ui,sans-serif)}' +
    '.menu-panel a:hover,.menu-panel a[aria-current]{background:var(--bg,#f4f1ea)}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  function init() {
    var host = document.querySelector('[data-menu-host]');
    if (!host) return;
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'menu-btn'; b.id = 'menu-btn';
    b.setAttribute('aria-label', 'Menu'); b.setAttribute('aria-expanded', 'false'); b.setAttribute('aria-controls', 'menu-panel');
    b.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
    var p = document.createElement('nav');
    p.className = 'menu-panel'; p.id = 'menu-panel'; p.hidden = true; p.setAttribute('aria-label', 'Pages');
    var here = location.pathname.replace(/\/index\.html$/, '/').replace(/\.html$/, '').replace(/(.)\/$/, '$1');
    PAGES.forEach(function (pg) {
      var a = document.createElement('a'); a.href = pg[1]; a.textContent = pg[0];
      if (pg[1] === here) a.setAttribute('aria-current', 'page');
      p.appendChild(a);
    });
    host.appendChild(b); host.appendChild(p);
    function set(open) { p.hidden = !open; b.setAttribute('aria-expanded', open ? 'true' : 'false'); }
    b.addEventListener('click', function (e) { e.stopPropagation(); set(p.hidden); });
    document.addEventListener('click', function (e) { if (!p.hidden && !p.contains(e.target)) set(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') set(false); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
