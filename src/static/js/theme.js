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
    // v0.11.0: the colour picker's channel sliders paint their own inline
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
   Resizable docked panels, drag the inner edge (the one facing the canvas)
   to grow or shrink one. Size persists per panel in localStorage and is
   clamped so it can't swallow the canvas. Coexists with the existing
   collapse toggles. The four sidebars resize in x; the hardware dock is the
   same system turned on its side, resizing in y from its top edge.
   ────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  /* One row per resizable panel, deliberately the same shape as the collapse
     table in app-core.js initSidebarToggles: a reader who understands one
     understands the other, and a fifth panel is a row here rather than an
     edit to every function below.

     `dragEdge` is which edge of the PANEL its drag strip lives on - the inner
     one, facing the canvas. Deliberately not called `edge`: the collapse table
     uses that name for the side of the APP a panel docks to, and for the
     Signal and Power panels the two differ. They are middle columns that dock
     left, so they collapse leftward but are dragged from their right-hand
     edges, exactly like the left sidebar - while each keeps its own storage
     key and CSS var, so no two panels' sizes ever move together.

     `axis` is which dimension the drag changes, and each row carries its own
     clamp because the two axes measure different things. Widths share
     180-560. The dock's height runs 100 - its own header plus one unit head
     and one chip row, the smallest tray that still shows a draggable chip -
     to 420, about 2.4x its 172px default, which at a ~900px window still
     leaves the canvas well over a third of the column. */
  var PANELS = [
    { key: 'left',  sidebarId: 'left-sidebar',  toggleId: 'left-sidebar-toggle',  storageKey: 'lrd_left_w',  cssVar: '--lrd-left-w',  dragEdge: 'right', axis: 'x', min: 180, max: 560, fallback: 260 },
    { key: 'data',  sidebarId: 'data-sidebar',  toggleId: 'data-sidebar-toggle',  storageKey: 'lrd_data_w',  cssVar: '--lrd-data-w',  dragEdge: 'right', axis: 'x', min: 180, max: 560, fallback: 260 },
    { key: 'power', sidebarId: 'power-sidebar', toggleId: 'power-sidebar-toggle', storageKey: 'lrd_power_w', cssVar: '--lrd-power-w', dragEdge: 'right', axis: 'x', min: 180, max: 560, fallback: 260 },
    { key: 'right', sidebarId: 'right-sidebar', toggleId: 'right-sidebar-toggle', storageKey: 'lrd_right_w', cssVar: '--lrd-right-w', dragEdge: 'left',  axis: 'x', min: 180, max: 560, fallback: 260 },
    { key: 'dock',  sidebarId: 'hardware-dock', toggleId: 'hardware-dock-toggle', storageKey: 'lrd_dock_h',  cssVar: '--lrd-dock-h',  dragEdge: 'top',   axis: 'y', min: 100, max: 420, fallback: 172 }
  ];

  function clamp(p, v) { return Math.max(p.min, Math.min(p.max, Math.round(v))); }
  function sb(p) { return document.getElementById(p.sidebarId); }
  function setSize(p, v) { document.documentElement.style.setProperty(p.cssVar, clamp(p, v) + 'px'); }
  function applySaved() {
    PANELS.forEach(function (p) {
      try { var v = parseInt(localStorage.getItem(p.storageKey), 10); if (v) setSize(p, v); } catch (e) { /* ignore */ }
    });
  }

  /* Changing a panel's width changes the width the canvas has to fill, and the
     canvas keeps its old pixel size until something re-measures it. app-core.js
     already owns that job for collapse and for view switching, so the drag path
     calls the same two entry points instead of growing a second mechanism. */
  function remeasure() { if (window.app && window.app.remeasureCanvas) window.app.remeasureCanvas(); }
  function settle() { if (window.app && window.app.settleLayout) window.app.settleLayout(); }

  var handles = {}, raf;
  function reposition() {
    PANELS.forEach(function (p) {
      var h = handles[p.key], s = sb(p); if (!h || !s) return;
      /* offset size 0 covers both a collapsed panel and one that has left
         layout altogether - the middle panels and the dock are display:none
         outside their own views, and a fixed strip left floating over the
         canvas there would be a live bug, not a cosmetic one. */
      var size = p.axis === 'y' ? s.offsetHeight : s.offsetWidth;
      if (s.classList.contains('collapsed') || size <= 1) { h.style.display = 'none'; return; }
      var r = s.getBoundingClientRect();
      h.style.display = 'block';
      if (p.axis === 'y') {
        /* the dock's strip lies along its top edge, spanning its width */
        h.style.left = r.left + 'px';
        h.style.width = r.width + 'px';
        h.style.top = (r.top - 3) + 'px';
        h.style.height = '';
      } else {
        h.style.top = r.top + 'px';
        h.style.height = r.height + 'px';
        h.style.left = (p.dragEdge === 'right' ? r.right - 3 : r.left - 4) + 'px';
        h.style.width = '';
      }
    });
  }
  function repaint() { if (raf) cancelAnimationFrame(raf); raf = requestAnimationFrame(reposition); }

  function startDrag(p, h) {
    return function (e) {
      e.preventDefault();
      var s = sb(p); if (!s) return;
      var app = document.getElementById('app');
      if (app) app.classList.add('lrd-resizing');
      h.classList.add('lrd-dragging');
      document.body.style.cursor = p.axis === 'y' ? 'row-resize' : 'col-resize';
      document.body.style.userSelect = 'none';
      function move(ev) {
        /* The panel's outer edge is the one that doesn't move while dragging,
           so measure from it: the pointer sets the distance to the edge being
           dragged. The dock's outer edge is its bottom - the status bar side. */
        var r = s.getBoundingClientRect();
        var v = p.axis === 'y'
          ? (r.bottom - ev.clientY)
          : (p.dragEdge === 'right' ? (ev.clientX - r.left) : (r.right - ev.clientX));
        setSize(p, v);
        /* .lrd-resizing suppresses the size transition, so the new size is
           already in layout on this frame and the canvas can be re-measured
           immediately rather than lagging a drag by a whole animation. */
        remeasure();
        repaint();
      }
      function up() {
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', up);
        h.classList.remove('lrd-dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        if (app) app.classList.remove('lrd-resizing');
        var cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue(p.cssVar), 10) || p.fallback;
        try { localStorage.setItem(p.storageKey, clamp(p, cur)); } catch (e) { /* ignore */ }
        settle();
      }
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
    };
  }

  function init() {
    if (!PANELS.some(sb)) return;
    applySaved();
    PANELS.forEach(function (p) {
      var s = sb(p);
      if (!s) return;
      var h = document.createElement('div');
      /* the -y variant swaps the strip's fixed dimension and cursor */
      h.className = 'lrd-resize-handle'
        + (p.axis === 'y' ? ' lrd-resize-handle-y' : '');
      h.dataset.lrdResize = p.key;
      h.title = 'Drag to resize panel';
      h.addEventListener('mousedown', startDrag(p, h));
      document.body.appendChild(h);
      handles[p.key] = h;
      /* Collapse toggles `class`, and leaving a panel's own view toggles it
         too (.view-hidden), so one observer covers both ways a panel can stop
         being draggable. */
      try { new MutationObserver(repaint).observe(s, { attributes: true, attributeFilter: ['class', 'style'] }); } catch (e) { /* ignore */ }
      var b = document.getElementById(p.toggleId);
      if (b) b.addEventListener('click', function () { setTimeout(reposition, 220); });
    });
    reposition();
    window.addEventListener('resize', repaint);
    window.addEventListener('scroll', repaint, true);
    setInterval(reposition, 1200);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
