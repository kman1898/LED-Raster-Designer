/*
 * The page frame, built as rings around the canvas.
 *
 * Everything that sits on an edge of the window - the menu bar, the status
 * bar, the toolbar and view tabs, and the three panels - is one entry in a
 * ring list, outermost first. Each entry takes one edge of whatever is left
 * inside the entries before it, and the canvas fills what remains. The
 * default list is the frame as it has always been:
 *
 *   menu across the top; the Screens panel down the right, beside
 *   everything under the menu; the status bar along the bottom of the
 *   rest; the toolbar and view tabs above the Settings panel and the
 *   canvas; the Settings panel down the left; the Hardware tray under the
 *   canvas only.
 *
 * The bars stay where they are. The three panels can take any edge: the
 * list this screen last used is kept in localStorage (lrd_layout), each
 * screen keeping its own, and a damaged or incomplete one falls back to the
 * default rather than losing a panel.
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
  var BARS = {
    menu:   ['menu-bar'],
    status: ['status-bar'],
    tabs:   ['toolbar', 'view-tabs']
  };
  var EDGES = ['left', 'right', 'top', 'bottom'];

  var DEFAULT = [
    { bar: 'menu',       edge: 'top' },
    { panel: 'screens',  edge: 'right' },
    { bar: 'status',     edge: 'bottom' },
    { bar: 'tabs',       edge: 'top' },
    { panel: 'settings', edge: 'left' },
    { panel: 'hardware', edge: 'bottom' }
  ];
  /* The bars never move, and keep their own edges. */
  var BAR_EDGE = { menu: 'top', status: 'bottom', tabs: 'top' };

  var STORE = 'lrd_layout';
  var CENTER = 'canvas-container';
  var rings = null;

  function el(id) { return document.getElementById(id); }
  function copy(list) { return list.map(function (r) { return r.panel ? { panel: r.panel, edge: r.edge } : { bar: r.bar, edge: r.edge }; }); }

  /* A ring list is usable only if every bar and every panel is in it once,
     the bars on their own edges and the panels on real ones. The menu stays
     outermost: the window's menus hang from it. */
  function valid(list) {
    if (!Array.isArray(list) || !list.length) return false;
    var seen = {};
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (!r || typeof r !== 'object') return false;
      var name = r.panel || r.bar;
      if (!name || seen[name]) return false;
      seen[name] = true;
      if (r.panel ? !PANELS[r.panel] : !BARS[r.bar]) return false;
      if (EDGES.indexOf(r.edge) < 0) return false;
      if (r.bar && BAR_EDGE[r.bar] !== r.edge) return false;
    }
    if (list[0].bar !== 'menu') return false;
    return Object.keys(PANELS).every(function (k) { return seen[k]; })
      && Object.keys(BARS).every(function (k) { return seen[k]; });
  }

  function load() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORE) || 'null');
      if (saved && saved.v === 1 && valid(saved.rings)) return copy(saved.rings);
    } catch (e) { /* unreadable storage keeps the default */ }
    return copy(DEFAULT);
  }
  function save(list) {
    try {
      if (same(list, DEFAULT)) localStorage.removeItem(STORE);
      else localStorage.setItem(STORE, JSON.stringify({ v: 1, rings: copy(list) }));
    } catch (e) { /* the arrangement still applies for this session */ }
  }
  function same(a, b) { return JSON.stringify(copy(a)) === JSON.stringify(copy(b)); }

  /* Build the rings into #app. Each ring is a flex box running across its
     edge's axis: a left or right ring is a row, a top or bottom ring a
     column. Its own elements go on its edge's side, the next ring (or the
     canvas) on the other. */
  function build(list) {
    var app = el('app');
    var center = el(CENTER);
    if (!app || !center) return;
    var oldRoot = app.querySelector(':scope > .lrd-ring');
    /* Every element is looked up before anything moves: rings are assembled
       off the page and only attached at the end, and getElementById cannot
       see into a detached one - nor into the canvas container once it is
       inside one, which is where the tray starts out. */
    var found = list.map(function (r) {
      return r.panel ? { panel: el(PANELS[r.panel].el), toggle: el(PANELS[r.panel].toggle) }
                     : { bars: BARS[r.bar].map(el) };
    });
    var inner = center;
    for (var i = list.length - 1; i >= 0; i--) {
      var r = list[i];
      /* A panel's fold toggle goes just before it: the toggle is
         position:fixed and pinned by measurement, so this changes nothing
         on screen, and it keeps the keyboard's Tab order panel by panel. */
      var panelEl = r.panel ? found[i].panel : null;
      var toggleEl = r.panel ? found[i].toggle : null;
      var items = (r.panel ? [toggleEl, panelEl] : found[i].bars).filter(Boolean);
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
    if (oldRoot) oldRoot.replaceWith(inner);
    else app.insertBefore(inner, app.firstChild);
    var old = el('main-container');
    if (old && !old.firstElementChild) old.remove();
  }

  /* Re-dock at runtime. Moving a node out of the page blurs it and drops
     its scroll, so both are carried across: what had the caret keeps it,
     and a long panel stays where it was scrolled to. */
  function apply(list, opts) {
    if (!valid(list)) return false;
    var focused = document.activeElement;
    var scrolls = Object.keys(PANELS).map(function (k) {
      var p = el(PANELS[k].el);
      return p ? [p, p.scrollTop, p.scrollLeft] : null;
    }).filter(Boolean);
    rings = copy(list);
    build(rings);
    scrolls.forEach(function (s) { s[0].scrollTop = s[1]; s[0].scrollLeft = s[2]; });
    if (focused && focused !== document.body && focused.isConnected && document.activeElement !== focused) {
      try { focused.focus({ preventScroll: true }); } catch (e) { /* not focusable any more */ }
    }
    if (!opts || opts.save !== false) save(rings);
    window.dispatchEvent(new CustomEvent('lrd-layout-change', { detail: { rings: copy(rings) } }));
    return true;
  }

  function edgeOf(name) {
    for (var i = 0; i < rings.length; i++) if (rings[i].panel === name) return rings[i].edge;
    return null;
  }

  /* Where a panel goes when it takes an edge no panel holds: the place the
     default frame gives that edge - beside everything under the menu on the
     right, under the toolbar on the left and top, under the canvas only at
     the bottom. With panels already on the edge, `index` counts among them
     from the outside in (0 = outermost; past the last = innermost). */
  function move(name, edge, index) {
    if (!PANELS[name] || EDGES.indexOf(edge) < 0) return false;
    var list = rings.filter(function (r) { return r.panel !== name; });
    var entry = { panel: name, edge: edge };
    var sameEdge = [];
    list.forEach(function (r, i) { if (r.panel && r.edge === edge) sameEdge.push(i); });
    var at;
    if (sameEdge.length) {
      var k = Math.max(0, Math.min(index == null ? sameEdge.length : index, sameEdge.length));
      at = k < sameEdge.length ? sameEdge[k] : sameEdge[sameEdge.length - 1] + 1;
    } else if (edge === 'right') {
      at = indexOfBar(list, 'menu') + 1;
    } else if (edge === 'bottom') {
      at = list.length;
    } else {
      at = indexOfBar(list, 'tabs') + 1;
    }
    list.splice(at, 0, entry);
    return apply(list);
  }
  function indexOfBar(list, bar) {
    for (var i = 0; i < list.length; i++) if (list[i].bar === bar) return i;
    return 0;
  }

  /* Only the panels, with the edge each holds now. */
  function panels() {
    return Object.keys(PANELS).map(function (name) {
      var p = PANELS[name];
      return { name: name, key: p.key, sidebarId: p.el, toggleId: p.toggle, label: p.label, edge: edgeOf(name) };
    });
  }

  /* A whole look - places, sizes and folds - for a named layout (the
     server keeps those, shared by every screen). Sizes come from theme.js
     and folds from the toggles' own keys; restoring one checks the list
     before anything moves, so a layout this screen cannot read changes
     nothing. */
  function snapshot() {
    var folds = {};
    Object.keys(PANELS).forEach(function (k) {
      var key = PANELS[k].key;
      try { folds[key] = localStorage.getItem('ledRasterSidebarCollapsed_' + key) === '1'; } catch (e) { folds[key] = false; }
    });
    return { v: 1, rings: copy(rings), sizes: window.LRD_SIZES ? window.LRD_SIZES.snapshot() : {}, folds: folds };
  }
  function restore(snap) {
    if (!snap || snap.v !== 1 || !valid(snap.rings)) return false;
    apply(snap.rings);
    if (window.LRD_SIZES) window.LRD_SIZES.restore(snap.sizes || {});
    window.dispatchEvent(new CustomEvent('lrd-apply-folds', { detail: { folds: snap.folds || {} } }));
    return true;
  }

  rings = load();
  build(rings);
  window.LRD_LAYOUT = {
    snapshot: snapshot,
    restore: restore,
    panels: panels,
    edgeOf: edgeOf,
    rings: function () { return copy(rings); },
    isDefault: function () { return same(rings, DEFAULT); },
    apply: apply,
    move: move,
    /* opts.save === false sets the default look without forgetting the
       screen's own (a guide borrows the default and gives it back) */
    reset: function (opts) { return apply(copy(DEFAULT), opts); }
  };
})();
