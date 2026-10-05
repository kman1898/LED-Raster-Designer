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
     uses that name for the side of the APP a panel docks to, and the two can
     differ. Each row keeps its own storage key and CSS var, so no two
     panels' sizes ever move together.

     `axis` is which dimension the drag changes, and each row carries its own
     clamp because the two axes measure different things. Widths share a
     constant 180-560. The dock's height runs from 100 - its own header plus
     one unit head and one chip row, the smallest tray that still shows a
     draggable chip - up to a ceiling MEASURED when it matters (ceilingOf):
     the height of the column the tray sits in (#canvas-container - the
     raster toolbar, the canvas, the tray) minus DOCK_FLOOR. "the hardware
     screen needs to be able to drag all the way up to give more room to
     work" (2026-09-07) retired the old constant 420, which at a tall window
     left most of the column to a canvas nobody was looking at. */
  /* Each panel's sizes: a width (`x`) for down a side and a height (`y`) for
     across the top or bottom, each with its own storage key and CSS var, so
     no two panels' sizes ever move together and a panel moved back finds the
     size it had there. The keys the three panels have always used are kept,
     so nobody's saved sizes move. A height has no constant `max`: it is
     measured (ceilingOf). The tray down a side may run to 930px: two of its
     440px tracks and their gap, with its padding, border and a scrollbar. */
  var SIZES = {
    left:  { x: { storageKey: 'lrd_left_w',     cssVar: '--lrd-left-w',     min: 180, max: 560, fallback: 260 },
             y: { storageKey: 'lrd_settings_h', cssVar: '--lrd-settings-h', min: 100, fallback: 220 } },
    right: { x: { storageKey: 'lrd_right_w',    cssVar: '--lrd-right-w',    min: 180, max: 560, fallback: 260 },
             y: { storageKey: 'lrd_screens_h',  cssVar: '--lrd-screens-h',  min: 100, fallback: 200 } },
    dock:  { x: { storageKey: 'lrd_hardware_w', cssVar: '--lrd-hardware-w', min: 180, max: 930, fallback: 460 },
             y: { storageKey: 'lrd_dock_h',     cssVar: '--lrd-dock-h',     min: 100, fallback: 172 } }
  };
  /* Where a panel docks decides its strip's edge and the axis it resizes
     along: the strip is on the inner edge, the one facing the canvas. The
     edge itself comes from the frame's one table (layout.js), read fresh
     each time - a panel can move. */
  var BY_EDGE = {
    left:   { dragEdge: 'right',  axis: 'x' },
    right:  { dragEdge: 'left',   axis: 'x' },
    bottom: { dragEdge: 'top',    axis: 'y' },
    top:    { dragEdge: 'bottom', axis: 'y' }
  };
  function panels() {
    return (window.LRD_LAYOUT ? window.LRD_LAYOUT.panels() : []).map(function (p) {
      var g = BY_EDGE[p.edge];
      return Object.assign({ key: p.key, sidebarId: p.sidebarId, toggleId: p.toggleId }, g, SIZES[p.key][g.axis]);
    });
  }
  function panelFor(key) {
    return panels().filter(function (p) { return p.key === key; })[0] || null;
  }

  /* What the tray must leave of its column: the raster toolbar
     (#canvas-controls, ~30px of inputs and padding) stays reachable and a
     sliver of canvas (~90px) stays visible so the drawing never vanishes
     behind the tray - 120px covers both. Below 100 + 120 = 220px of column
     the floor yields to the tray's own minimum. */
  var DOCK_FLOOR = 120;

  /* A panel's ceiling: the constant for a width; for the dock, its column's
     height minus the floor, read fresh on every clamp so a drag, the saved
     value on boot and a window shrink all respect the column as it is now.
     With nothing to measure (the column not in layout yet) the window's own
     height stands in, so no early clamp can swallow the column either. */
  function ceilingOf(p) {
    if (p.axis !== 'y') return p.max;
    var s = sb(p), col = s && s.parentElement;
    var h = col ? col.clientHeight : 0;
    if (!(h > 0)) h = window.innerHeight || 0;
    return Math.max(p.min, Math.round(h - DOCK_FLOOR));
  }
  function clamp(p, v) { return Math.max(p.min, Math.min(ceilingOf(p), Math.round(v))); }
  function sb(p) { return document.getElementById(p.sidebarId); }
  function setSize(p, v) { document.documentElement.style.setProperty(p.cssVar, clamp(p, v) + 'px'); }
  function currentSize(p) {
    return parseInt(getComputedStyle(document.documentElement).getPropertyValue(p.cssVar), 10) || p.fallback;
  }
  /* Both of every panel's sizes, whichever direction it is in now: the
     other is waiting for the day it moves. */
  function applySaved() {
    panels().forEach(function (p) {
      ['x', 'y'].forEach(function (axis) {
        var size = Object.assign({ sidebarId: p.sidebarId, axis: axis }, SIZES[p.key][axis]);
        try { var v = parseInt(localStorage.getItem(size.storageKey), 10); if (v) setSize(size, v); } catch (e) { /* ignore */ }
      });
    });
  }
  /* The measured ceiling moves with the window: a 900px tray saved on a
     tall display must not swallow the column when the window comes back at
     600px, so every y-panel is re-clamped against its column on resize.
     The tray's height transitions (no drag, so nothing suppresses it), and
     the canvas is re-measured by the staged settle - the window's own
     resize pass has already measured it mid-transition. */
  function reclamp() {
    var moved = false;
    panels().forEach(function (p) {
      if (p.axis !== 'y') return;
      var cur = currentSize(p), want = clamp(p, cur);
      if (want !== cur) { setSize(p, want); moved = true; }
    });
    if (moved) settle();
  }

  /* Changing a panel's width changes the width the canvas has to fill, and the
     canvas keeps its old pixel size until something re-measures it. app-core.js
     already owns that job for collapse and for view switching, so the drag path
     calls the same two entry points instead of growing a second mechanism. */
  function remeasure() { if (window.app && window.app.remeasureCanvas) window.app.remeasureCanvas(); }
  function settle() { if (window.app && window.app.settleLayout) window.app.settleLayout(); }

  var handles = {}, raf;
  function reposition() {
    panels().forEach(function (p) {
      var h = handles[p.key], s = sb(p); if (!h || !s) return;
      /* the -y variant swaps the strip's fixed dimension and cursor */
      h.classList.toggle('lrd-resize-handle-y', p.axis === 'y');
      /* offset size 0 covers both a collapsed panel and one that has left
         layout altogether - the dock is display:none outside its own views,
         and a fixed strip left floating over the canvas there would be a
         live bug, not a cosmetic one. */
      var size = p.axis === 'y' ? s.offsetHeight : s.offsetWidth;
      if (s.classList.contains('collapsed') || size <= 1) { h.style.display = 'none'; return; }
      var r = s.getBoundingClientRect();
      h.style.display = 'block';
      if (p.axis === 'y') {
        /* across the top or bottom the strip lies along the panel's inner
           edge - its top at the bottom, its bottom at the top - spanning
           its width */
        h.style.left = r.left + 'px';
        h.style.width = r.width + 'px';
        h.style.top = (p.dragEdge === 'top' ? r.top - 3 : r.bottom - 4) + 'px';
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

  function startDrag(key, h) {
    return function (e) {
      e.preventDefault();
      /* the panel as it is docked now - it may have moved since the strip
         was made */
      var p = panelFor(key);
      var s = p && sb(p); if (!s) return;
      var app = document.getElementById('app');
      if (app) app.classList.add('lrd-resizing');
      h.classList.add('lrd-dragging');
      document.body.style.cursor = p.axis === 'y' ? 'row-resize' : 'col-resize';
      document.body.style.userSelect = 'none';
      function move(ev) {
        /* The panel's outer edge is the one that doesn't move while dragging,
           so measure from it: the pointer sets the distance to the edge being
           dragged. Along the bottom the outer edge is the panel's bottom (the
           status bar side), along the top its top. */
        var r = s.getBoundingClientRect();
        var v = p.axis === 'y'
          ? (p.dragEdge === 'top' ? (r.bottom - ev.clientY) : (ev.clientY - r.top))
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
        var cur = currentSize(p);
        try { localStorage.setItem(p.storageKey, clamp(p, cur)); } catch (e) { /* ignore */ }
        settle();
      }
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
    };
  }

  function init() {
    if (!panels().some(sb)) return;
    applySaved();
    panels().forEach(function (p) {
      var s = sb(p);
      if (!s) return;
      var h = document.createElement('div');
      h.className = 'lrd-resize-handle'
        + (p.axis === 'y' ? ' lrd-resize-handle-y' : '');
      h.dataset.lrdResize = p.key;
      h.title = 'Drag to resize panel';
      h.addEventListener('mousedown', startDrag(p.key, h));
      document.body.appendChild(h);
      handles[p.key] = h;
      /* Collapse toggles `class`, and leaving a panel's own view toggles it
         too (.view-hidden), so one observer covers both ways a panel can stop
         being draggable. */
      try { new MutationObserver(repaint).observe(s, { attributes: true, attributeFilter: ['class', 'style'] }); } catch (e) { /* ignore */ }
      /* A fold animates the panel's size, and the strips sit on its edges.
         They were placed 220 ms after the toggle and swept every 1.2 s - a
         guess at when the fold ends, wrong on a machine that paints slowly,
         where a strip went missing or sat mid-panel for a second. Every size
         the panel passes through, the last included, now places them. */
      if (typeof ResizeObserver === 'function') {
        try { new ResizeObserver(repaint).observe(s); } catch (e) { /* ignore */ }
      }
      var b = document.getElementById(p.toggleId);
      if (b) b.addEventListener('click', function () { setTimeout(reposition, 220); });
    });
    reposition();
    reclamp();
    window.addEventListener('resize', function () { reclamp(); repaint(); });
    /* a panel took another edge: its size and its strip follow it */
    window.addEventListener('lrd-layout-change', function () { reclamp(); repaint(); });
    /* A named layout carries every panel's saved sizes (null = never
       resized, the default): snapshot reads them, restore puts them back
       - clamped like any other size - or forgets them. */
    window.LRD_SIZES = {
      snapshot: function () {
        var out = {};
        Object.keys(SIZES).forEach(function (key) {
          ['x', 'y'].forEach(function (axis) {
            var k = SIZES[key][axis].storageKey, v = null;
            try { v = parseInt(localStorage.getItem(k), 10) || null; } catch (e) { /* ignore */ }
            out[k] = v;
          });
        });
        return out;
      },
      restore: function (map) {
        map = map || {};
        panels().forEach(function (p) {
          ['x', 'y'].forEach(function (axis) {
            var size = Object.assign({ sidebarId: p.sidebarId, axis: axis }, SIZES[p.key][axis]);
            if (!(size.storageKey in map)) return;
            var v = parseInt(map[size.storageKey], 10);
            try {
              if (v > 0) { setSize(size, v); localStorage.setItem(size.storageKey, clamp(size, v)); }
              else { localStorage.removeItem(size.storageKey); document.documentElement.style.removeProperty(size.cssVar); }
            } catch (e) { /* the sizes still apply for this session */ }
          });
        });
        reclamp(); repaint(); settle();
      }
    };
    /* Reset size (a panel's right-click menu): both of its saved sizes are
       forgotten, so it is back to its default width and height */
    window.addEventListener('lrd-reset-size', function (e) {
      var sizes = SIZES[e.detail && e.detail.key];
      if (!sizes) return;
      ['x', 'y'].forEach(function (axis) {
        try { localStorage.removeItem(sizes[axis].storageKey); } catch (err) { /* ignore */ }
        document.documentElement.style.removeProperty(sizes[axis].cssVar);
      });
      reclamp(); repaint(); settle();
    });
    window.addEventListener('scroll', repaint, true);
    setInterval(reposition, 1200);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
