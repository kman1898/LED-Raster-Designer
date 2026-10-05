/*
 * The page frame, built as rings around the canvas.
 *
 * Everything that sits on an edge of the window - the menu bar, the status
 * bar, the toolbar and view tabs, and the three panels - is one entry in
 * RINGS, outermost first. Each entry takes one edge of whatever is left
 * inside the entries before it, and the canvas fills what remains. The
 * default list below is the frame as it has always been:
 *
 *   menu across the top; the Screens panel down the right, beside
 *   everything under the menu; the status bar along the bottom of the
 *   rest; the toolbar and view tabs above the Settings panel and the
 *   canvas; the Settings panel down the left; the Hardware tray under the
 *   canvas only.
 *
 * Panels are moved, never copied: every id and data-lrd-field key keeps
 * exactly one home, so getElementById and the focus restore never race a
 * twin. Each panel and its fold toggle carry data-lrd-edge, which the CSS
 * and the fold/resize code read instead of assuming where a panel is.
 *
 * Loaded as a plain script straight after #app, so the frame is in its
 * rings before the first paint.
 */
(function () {
  'use strict';

  /* The movable panels. `key` is the name the fold and resize state have
     always been stored under (ledRasterSidebarCollapsed_<key>, and the
     size keys in theme.js), so nobody's saved sizes or folds move. */
  var PANELS = {
    settings: { key: 'left',  el: 'left-sidebar',  toggle: 'left-sidebar-toggle',  label: 'left' },
    screens:  { key: 'right', el: 'right-sidebar', toggle: 'right-sidebar-toggle', label: 'right' },
    hardware: { key: 'dock',  el: 'hardware-dock', toggle: 'hardware-dock-toggle', label: 'hardware' }
  };

  var RINGS = [
    { bar: 'menu',     edge: 'top',    els: ['menu-bar'] },
    { panel: 'screens',  edge: 'right' },
    { bar: 'status',   edge: 'bottom', els: ['status-bar'] },
    { bar: 'tabs',     edge: 'top',    els: ['toolbar', 'view-tabs'] },
    { panel: 'settings', edge: 'left' },
    { panel: 'hardware', edge: 'bottom' }
  ];

  var CENTER = 'canvas-container';

  function el(id) { return document.getElementById(id); }

  /* Build the rings into #app. Each ring is a flex box running across its
     edge's axis: a left or right ring is a row, a top or bottom ring a
     column. Its own elements go on its edge's side, the next ring (or the
     canvas) on the other. */
  function build(rings) {
    var app = el('app');
    var center = el(CENTER);
    if (!app || !center) return;
    var inner = center;
    for (var i = rings.length - 1; i >= 0; i--) {
      var r = rings[i];
      /* A panel's fold toggle goes just before it: the toggle is
         position:fixed and pinned by measurement, so this changes nothing on
         screen, and it keeps the keyboard's Tab order panel by panel. */
      /* Looked up before anything moves: a ring is assembled off the page
         and only attached at the end, and getElementById cannot see into
         it. */
      var panelEl = r.panel ? el(PANELS[r.panel].el) : null;
      var toggleEl = r.panel ? el(PANELS[r.panel].toggle) : null;
      var items = (r.panel ? [toggleEl, panelEl] : r.els.map(el)).filter(Boolean);
      var ring = document.createElement('div');
      ring.className = 'lrd-ring';
      ring.dataset.lrdRing = r.panel || r.bar;
      ring.dataset.lrdEdge = r.edge;
      var before = r.edge === 'left' || r.edge === 'top';
      if (before) { items.forEach(function (n) { ring.appendChild(n); }); ring.appendChild(inner); }
      else { ring.appendChild(inner); items.forEach(function (n) { ring.appendChild(n); }); }
      if (panelEl) { panelEl.classList.add('lrd-panel'); panelEl.dataset.lrdPanel = r.panel; panelEl.dataset.lrdEdge = r.edge; }
      if (toggleEl) toggleEl.dataset.lrdEdge = r.edge;
      inner = ring;
    }
    /* The outermost ring takes the place the frame's children had: before
       anything else left in #app (the update banner), which stays put. */
    app.insertBefore(inner, app.firstChild);
    var old = el('main-container');
    if (old && !old.firstElementChild) old.remove();
  }

  function edgeOf(name) {
    for (var i = 0; i < RINGS.length; i++) if (RINGS[i].panel === name) return RINGS[i].edge;
    return null;
  }

  /* Only the panels, in the order the fold and resize tables read them. */
  function panels() {
    return Object.keys(PANELS).map(function (name) {
      var p = PANELS[name];
      return { name: name, key: p.key, sidebarId: p.el, toggleId: p.toggle, label: p.label, edge: edgeOf(name) };
    });
  }

  build(RINGS);
  window.LRD_LAYOUT = { panels: panels, edgeOf: edgeOf };
})();
