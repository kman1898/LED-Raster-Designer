/* ──────────────────────────────────────────────────────────────────────
   LED Raster Designer, "Studio" theme enhancer (cosmetic only)
   1. Swappable accent: applies the saved accent on load and exposes an
      accent picker injected into the Preferences dialog. Persisted in
      localStorage. Drives the --ps-accent* CSS variables.
   2. Chunky sliders: turns native range inputs into labeled bars (colored
      fill + value bubble), non-destructively (the <input> keeps its id,
      value, and listeners).
   Remove this file + theme.css to fully revert.
   ────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  /* ---- accent presets ---- */
  var ACCENTS = {
    red:    { label: 'Red',    accent: '#e22330', hi: '#ef3340', deep: '#8f1218' },
    blue:   { label: 'Blue',   accent: '#2f7ad6', hi: '#3d8ae6', deep: '#194f8f' },
    green:  { label: 'Green',  accent: '#2c9d4f', hi: '#36b85e', deep: '#176030' },
    amber:  { label: 'Amber',  accent: '#c8841a', hi: '#e09a2a', deep: '#7a4d08' },
    purple: { label: 'Purple', accent: '#7d4ad6', hi: '#8f5ce6', deep: '#4a268f' },
    teal:   { label: 'Teal',   accent: '#178f84', hi: '#1fa99c', deep: '#0c5048' }
  };
  var KEY = 'lrd_theme_accent';

  function currentKey() {
    try { return (localStorage.getItem(KEY) && ACCENTS[localStorage.getItem(KEY)]) ? localStorage.getItem(KEY) : 'red'; }
    catch (e) { return 'red'; }
  }
  function applyAccent(k) {
    var a = ACCENTS[k] || ACCENTS.red;
    var s = document.documentElement.style;
    s.setProperty('--ps-accent', a.accent);
    s.setProperty('--ps-accent-hi', a.hi);
    s.setProperty('--ps-accent-deep', a.deep);
    document.documentElement.setAttribute('data-ps-accent', k);
  }
  function save(k) { try { localStorage.setItem(KEY, k); } catch (e) { /* ignore */ } }
  applyAccent(currentKey());

  /* ---- chunky labeled sliders ---- */
  function enhanceSlider(r) {
    if (r.dataset.psSlider) return;
    r.dataset.psSlider = '1';
    var min = parseFloat(r.min) || 0;
    var max = parseFloat(r.max);
    if (!isFinite(max) || max === min) max = min + 100;
    var wrap = document.createElement('span');
    wrap.className = 'ps-slider-wrap';
    if (r.parentNode) { r.parentNode.insertBefore(wrap, r); wrap.appendChild(r); }
    var bubble = document.createElement('span');
    bubble.className = 'ps-slider-val';
    wrap.appendChild(bubble);
    function paint() {
      var pct = ((parseFloat(r.value) - min) / (max - min)) * 100;
      pct = Math.max(0, Math.min(100, pct));
      r.style.background = 'linear-gradient(90deg, var(--ps-accent) ' + pct + '%, var(--ps-inset) ' + pct + '%)';
      bubble.textContent = (r.value != null ? r.value : '');
    }
    r.addEventListener('input', paint);
    r.addEventListener('change', paint);
    paint();
  }

  /* ---- accent picker injected into Preferences ---- */
  function injectAccentUI() {
    var modal = document.getElementById('preferences-modal');
    if (!modal || getComputedStyle(modal).display === 'none') return;
    var content = modal.querySelector('.modal-content') || modal;
    if (content.querySelector('#ps-accent-ui')) return;

    var box = document.createElement('div');
    box.id = 'ps-accent-ui';
    box.className = 'ps-appearance';
    var h = document.createElement('div');
    h.className = 'ps-appearance-h';
    h.textContent = 'Appearance';
    box.appendChild(h);
    var row = document.createElement('div');
    row.className = 'ps-accent-row';
    var lab = document.createElement('span');
    lab.className = 'ps-accent-label';
    lab.textContent = 'Accent color';
    row.appendChild(lab);
    Object.keys(ACCENTS).forEach(function (k) {
      var a = ACCENTS[k];
      var sw = document.createElement('div');
      sw.className = 'ps-accent-sw' + (k === currentKey() ? ' selected' : '');
      sw.style.background = 'linear-gradient(' + a.hi + ',' + a.accent + ')';
      sw.title = a.label;
      sw.setAttribute('role', 'button');
      sw.setAttribute('aria-label', 'Accent color ' + a.label);
      sw.addEventListener('click', function () {
        applyAccent(k); save(k);
        row.querySelectorAll('.ps-accent-sw').forEach(function (e) { e.classList.remove('selected'); });
        sw.classList.add('selected');
      });
      row.appendChild(sw);
    });
    box.appendChild(row);
    var grid = content.querySelector('.prefs-grid');
    if (grid && grid.parentNode) grid.parentNode.insertBefore(box, grid.nextSibling);
    else content.appendChild(box);
  }

  function scan() {
    // v0.10.9: the colour picker's channel sliders paint their own inline
    // ramp (color_picker.js _trackGradient); enhancing them would repaint the
    // ramp as a flat accent fill and drop a value bubble on top of it.
    var list = document.querySelectorAll(
      'input[type="range"]:not([data-ps-slider]):not(.lrd-cw-range)');
    for (var i = 0; i < list.length; i++) enhanceSlider(list[i]);
    injectAccentUI();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scan);
  else scan();
  try { new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true }); }
  catch (e) { /* ignore */ }
})();

/* ──────────────────────────────────────────────────────────────────────
   Resizable sidebars, drag the inner edge of either sidebar to widen or
   narrow it. Width persists per side in localStorage and is clamped so it
   can't swallow the canvas. Coexists with the existing collapse toggle.
   ────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  var MIN = 180, MAX = 560, KEY = { left: 'lrd_left_w', right: 'lrd_right_w' };
  function clamp(w) { return Math.max(MIN, Math.min(MAX, Math.round(w))); }
  function sb(side) { return document.getElementById(side === 'left' ? 'left-sidebar' : 'right-sidebar'); }
  function cssVar(side) { return side === 'left' ? '--lrd-left-w' : '--lrd-right-w'; }
  function setW(side, w) { document.documentElement.style.setProperty(cssVar(side), clamp(w) + 'px'); }
  function applySaved() {
    ['left', 'right'].forEach(function (side) {
      try { var v = parseInt(localStorage.getItem(KEY[side]), 10); if (v) setW(side, v); } catch (e) { /* ignore */ }
    });
  }

  var handles = {}, raf;
  function reposition() {
    ['left', 'right'].forEach(function (side) {
      var h = handles[side], s = sb(side); if (!h || !s) return;
      if (s.classList.contains('collapsed') || s.offsetWidth <= 1) { h.style.display = 'none'; return; }
      var r = s.getBoundingClientRect();
      h.style.display = 'block';
      h.style.top = r.top + 'px';
      h.style.height = r.height + 'px';
      h.style.left = (side === 'left' ? r.right - 3 : r.left - 4) + 'px';
    });
  }
  function repaint() { if (raf) cancelAnimationFrame(raf); raf = requestAnimationFrame(reposition); }

  function startDrag(side, h) {
    return function (e) {
      e.preventDefault();
      var s = sb(side); if (!s) return;
      var app = document.getElementById('app');
      if (app) app.classList.add('lrd-resizing');
      h.classList.add('lrd-dragging');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      function move(ev) {
        var r = s.getBoundingClientRect();
        var w = side === 'left' ? (ev.clientX - r.left) : (window.innerWidth - ev.clientX);
        setW(side, w); repaint();
      }
      function up() {
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', up);
        h.classList.remove('lrd-dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        if (app) app.classList.remove('lrd-resizing');
        var cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue(cssVar(side)), 10) || 260;
        try { localStorage.setItem(KEY[side], clamp(cur)); } catch (e) { /* ignore */ }
      }
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
    };
  }

  function init() {
    if (!sb('left') && !sb('right')) return;
    applySaved();
    ['left', 'right'].forEach(function (side) {
      var h = document.createElement('div');
      h.className = 'lrd-resize-handle';
      h.title = 'Drag to resize panel';
      h.addEventListener('mousedown', startDrag(side, h));
      document.body.appendChild(h);
      handles[side] = h;
      var s = sb(side);
      if (s) { try { new MutationObserver(repaint).observe(s, { attributes: true, attributeFilter: ['class', 'style'] }); } catch (e) { /* ignore */ } }
    });
    reposition();
    window.addEventListener('resize', repaint);
    window.addEventListener('scroll', repaint, true);
    ['left-sidebar-toggle', 'right-sidebar-toggle'].forEach(function (id) {
      var b = document.getElementById(id);
      if (b) b.addEventListener('click', function () { setTimeout(reposition, 220); });
    });
    setInterval(reposition, 1200);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
