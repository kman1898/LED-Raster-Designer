/*
 * Moving a panel: drag its title bar to an edge, or right-click it.
 *
 * Each panel has one handle, marked data-lrd-grip: the Settings panel's
 * title bar, the Screens panel's header and the Hardware tray's header.
 * Dragging one lights up the places the panel can go - every one a
 * position in layout.js's ring list - and dropping on one moves it there:
 *
 *   down a side: full height, beside the toolbar (the Screens panel's place
 *   by default), or under the toolbar (the Settings panel's);
 *   across the top: under the toolbar;
 *   across the bottom: under the canvas only (the tray's place), or across
 *   under the side panels too;
 *   and either side of any panel already on an edge.
 *
 * Escape, or letting go away from every place, leaves the panel where it
 * was. A right-click on a handle offers Move to Left / Right / Top /
 * Bottom (each edge's usual place), Fold, Reset size and Reset Layout.
 */
(function () {
  'use strict';

  var TITLES = { settings: 'Settings', screens: 'Screens', hardware: 'Hardware' };
  var EDGE_NAMES = { left: 'Left', right: 'Right', top: 'Top', bottom: 'Bottom' };
  var THRESHOLD = 5;      // px the pointer moves before a press becomes a drag
  var REACH = 90;         // px from a place within which it lights up
  var BAND = 56;          // px depth of a place's band along its edge

  function layout() { return window.LRD_LAYOUT; }

  /* What a press on these must not turn into: the controls inside a header
     (the tray's add picker, its buttons, the fold chevron). */
  function onControl(target) {
    return !!(target && target.closest && target.closest('input, select, textarea, button, a, [contenteditable="true"]'));
  }

  /* Every place a panel can go, as the ring list it would make. Places that
     make the same list are one place; the list the panel already has is
     kept, so letting go where it is changes nothing. */
  function places(name) {
    var base = layout().rings().filter(function (r) { return r.panel !== name; });
    var at = function (bar) { for (var i = 0; i < base.length; i++) if (base[i].bar === bar) return i; return 0; };
    var out = [], seen = {};
    function add(edge, index, label) {
      var list = base.slice();
      list.splice(index, 0, { panel: name, edge: edge });
      var key = JSON.stringify(list);
      if (seen[key]) return;
      seen[key] = true;
      out.push({ edge: edge, index: index, label: label, list: list });
    }
    add('left', at('menu') + 1, 'Left, full height');
    add('left', at('tabs') + 1, 'Left, under the toolbar');
    add('right', at('menu') + 1, 'Right, full height');
    add('right', at('tabs') + 1, 'Right, under the toolbar');
    add('top', at('tabs') + 1, 'Top, under the toolbar');
    add('bottom', base.length, 'Bottom, under the canvas');
    add('bottom', at('tabs') + 1, 'Bottom, across');
    base.forEach(function (r, i) {
      if (!r.panel) return;
      add(r.edge, i, EDGE_NAMES[r.edge] + ', outside ' + TITLES[r.panel]);
      add(r.edge, i + 1, EDGE_NAMES[r.edge] + ', inside ' + TITLES[r.panel]);
    });
    return out;
  }

  /* Where a place's band is drawn: along its edge of the space the panel
     would dock into - the room inside the ring just outside it. The rings
     are nested, so in document order they run outermost first, one per
     entry of the list as it is now. */
  function bandFor(place, name) {
    var full = layout().rings();
    var ringEls = Array.prototype.slice.call(document.querySelectorAll('#app .lrd-ring'));
    var before = place.list[place.index - 1];
    var k = -1;
    for (var i = 0; i < full.length; i++) {
      if ((full[i].panel || full[i].bar) === (before.panel || before.bar)) { k = i; break; }
    }
    var ring = ringEls[k];
    if (!ring) return null;
    var room = ring.querySelector(':scope > .lrd-ring, :scope > #canvas-container');
    if (!room) return null;
    var r = room.getBoundingClientRect();
    if (place.edge === 'left') return { x: r.left, y: r.top, w: BAND, h: r.height };
    if (place.edge === 'right') return { x: r.right - BAND, y: r.top, w: BAND, h: r.height };
    if (place.edge === 'top') return { x: r.left, y: r.top, w: r.width, h: BAND - 12 };
    return { x: r.left, y: r.bottom - (BAND - 12), w: r.width, h: BAND - 12 };
  }

  var drag = null;

  function startDrag(e, grip) {
    var name = grip.dataset.lrdGrip;
    var sx = e.clientX, sy = e.clientY;
    drag = { name: name, live: false, hot: null, bands: [] };
    function move(ev) {
      if (!drag) return;
      if (!drag.live) {
        if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) < THRESHOLD) return;
        begin();
      }
      ev.preventDefault();
      drag.ghost.style.left = (ev.clientX + 14) + 'px';
      drag.ghost.style.top = (ev.clientY + 10) + 'px';
      var best = null, bestD = Infinity;
      drag.bands.forEach(function (b, i) {
        var dx = Math.max(b.x - ev.clientX, 0, ev.clientX - (b.x + b.w));
        var dy = Math.max(b.y - ev.clientY, 0, ev.clientY - (b.y + b.h));
        var d = Math.sqrt(dx * dx + dy * dy);
        if (d < bestD) { bestD = d; best = i; }
      });
      drag.hot = bestD <= REACH ? best : null;
      drag.bands.forEach(function (b, i) { b.el.classList.toggle('lrd-drop-hot', i === drag.hot); });
      /* the place is named beside the pointer, where there is room for it */
      drag.ghost.textContent = TITLES[name] + (drag.hot === null ? '' : ' → ' + drag.bands[drag.hot].place.label);
    }
    function up() { finish(drag && drag.live && drag.hot !== null); }
    function key(ev) { if (ev.key === 'Escape') { ev.preventDefault(); finish(false); } }
    function begin() {
      drag.live = true;
      document.body.classList.add('lrd-panel-dragging');
      var layer = document.createElement('div');
      layer.className = 'lrd-drop-layer';
      places(name).forEach(function (p) {
        var r = bandFor(p, name);
        if (!r || r.w < 4 || r.h < 4) return;
        var el = document.createElement('div');
        el.className = 'lrd-drop-zone';
        el.dataset.lrdPlace = p.label;
        el.style.left = r.x + 'px'; el.style.top = r.y + 'px';
        el.style.width = r.w + 'px'; el.style.height = r.h + 'px';
        layer.appendChild(el);
        drag.bands.push({ x: r.x, y: r.y, w: r.w, h: r.h, el: el, place: p });
      });
      var ghost = document.createElement('div');
      ghost.className = 'lrd-drag-ghost';
      ghost.textContent = TITLES[name];
      document.body.appendChild(layer);
      document.body.appendChild(ghost);
      drag.layer = layer;
      drag.ghost = ghost;
    }
    function finish(drop) {
      document.removeEventListener('pointermove', move, true);
      document.removeEventListener('pointerup', up, true);
      document.removeEventListener('keydown', key, true);
      if (!drag) return;
      var d = drag;
      drag = null;
      if (d.layer) d.layer.remove();
      if (d.ghost) d.ghost.remove();
      document.body.classList.remove('lrd-panel-dragging');
      if (drop) {
        var place = d.bands[d.hot].place;
        layout().apply(place.list);
        log('panel_moved', { panel: d.name, edge: place.edge, place: place.label });
      }
    }
    document.addEventListener('pointermove', move, true);
    document.addEventListener('pointerup', up, true);
    document.addEventListener('keydown', key, true);
  }

  function log(event, data) {
    if (typeof window.sendClientLog === 'function') window.sendClientLog(event, data);
  }

  /* ── the right-click menu on a handle ─────────────────────────────── */
  var menu = null;
  function closeMenu() {
    if (menu) { menu.remove(); menu = null; }
    document.removeEventListener('pointerdown', outside, true);
    document.removeEventListener('keydown', escMenu, true);
  }
  function outside(e) { if (menu && !menu.contains(e.target)) closeMenu(); }
  function escMenu(e) { if (e.key === 'Escape') closeMenu(); }

  function openMenu(name, x, y) {
    closeMenu();
    var edge = layout().edgeOf(name);
    var panel = layout().panels().filter(function (p) { return p.name === name; })[0];
    var panelEl = panel && document.getElementById(panel.sidebarId);
    var folded = panelEl && panelEl.classList.contains('collapsed');
    var items = [];
    ['left', 'right', 'top', 'bottom'].forEach(function (e) {
      items.push({ label: 'Move to ' + EDGE_NAMES[e], act: 'move-' + e, disabled: e === edge });
    });
    items.push(null);
    items.push({ label: folded ? 'Open' : 'Fold', act: 'fold' });
    items.push({ label: 'Reset size', act: 'size' });
    items.push(null);
    items.push({ label: 'Reset Layout', act: 'reset', disabled: layout().isDefault() });
    menu = document.createElement('div');
    menu.className = 'context-menu lrd-panel-menu';
    menu.dataset.lrdPanelMenu = name;
    items.forEach(function (it) {
      var row = document.createElement('div');
      if (!it) { row.className = 'menu-divider'; menu.appendChild(row); return; }
      row.className = 'menu-option' + (it.disabled ? ' menu-disabled' : '');
      row.textContent = it.label;
      row.dataset.act = it.act;
      menu.appendChild(row);
    });
    menu.addEventListener('click', function (ev) {
      var row = ev.target.closest('.menu-option');
      if (!row || row.classList.contains('menu-disabled')) return;
      var act = row.dataset.act;
      closeMenu();
      if (act.indexOf('move-') === 0) {
        layout().move(name, act.slice(5));
        log('panel_moved', { panel: name, edge: act.slice(5), place: 'menu' });
      } else if (act === 'fold') {
        var t = panel && document.getElementById(panel.toggleId);
        if (t) t.click();
      } else if (act === 'size') {
        window.dispatchEvent(new CustomEvent('lrd-reset-size', { detail: { key: panel.key } }));
      } else if (act === 'reset') {
        layout().reset();
      }
    });
    menu.style.display = 'block';
    document.body.appendChild(menu);
    var mw = menu.offsetWidth, mh = menu.offsetHeight;
    menu.style.left = Math.max(4, Math.min(x, window.innerWidth - mw - 4)) + 'px';
    menu.style.top = Math.max(4, Math.min(y, window.innerHeight - mh - 4)) + 'px';
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('keydown', escMenu, true);
  }

  /* ── View › Layouts: the named layouts every screen shares ─────────── */
  var saved = [];

  /* Two layouts are the same look when their contents match, whatever order
     their keys arrived in (the server hands them back sorted). */
  function canon(v) {
    if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
    if (v && typeof v === 'object') {
      return '{' + Object.keys(v).sort().map(function (k) { return JSON.stringify(k) + ':' + canon(v[k]); }).join(',') + '}';
    }
    return JSON.stringify(v);
  }

  function api(method, body) {
    return fetch('/api/layouts', {
      method: method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'the layout was not saved'); return d; });
    });
  }
  function say(text) {
    var s = document.getElementById('status-message');
    if (s) s.textContent = text;
  }
  function closeMenus() {
    document.querySelectorAll('.menu-dropdown').forEach(function (m) { m.style.display = 'none'; });
    document.querySelectorAll('#menu-bar .menu-item').forEach(function (m) { m.classList.remove('active'); });
  }
  function option(label, handler, opts) {
    var row = document.createElement('div');
    row.className = 'menu-option' + (opts && opts.disabled ? ' menu-disabled' : '') + (opts && opts.current ? ' lrd-layout-current' : '');
    row.textContent = label;
    if (opts && opts.name) row.dataset.lrdLayout = opts.name;
    if (opts && opts.act) row.dataset.lrdLayoutAct = opts.act;
    row.addEventListener('click', function (e) {
      e.stopPropagation();
      if (row.classList.contains('menu-disabled')) return;
      closeMenus();
      handler();
    });
    return row;
  }
  function divider() { var d = document.createElement('div'); d.className = 'menu-divider'; return d; }

  /* Fill the submenu from the server each time it is shown: another screen
     may have saved or deleted one since. The look this screen has now gets
     a tick beside the layout it matches. */
  function fillLayouts() {
    var box = document.getElementById('layouts-submenu');
    if (!box) return Promise.resolve();
    return api('GET').then(function (d) { saved = d.layouts || []; }, function () { saved = []; }).then(function () {
      var now = canon(layout().snapshot());
      box.innerHTML = '';
      if (!saved.length) {
        var none = document.createElement('div');
        none.className = 'recent-files-empty';
        none.textContent = 'No saved layouts';
        box.appendChild(none);
      }
      saved.forEach(function (item) {
        var current = canon(item.layout) === now;
        box.appendChild(option(item.name, function () {
          if (layout().restore(item.layout)) say('Layout "' + item.name + '"');
          else say('Layout "' + item.name + '" could not be opened on this screen');
        }, { name: item.name, current: current }));
      });
      box.appendChild(divider());
      box.appendChild(option('Save Current Layout…', function () { saveDialog(); }, { act: 'save' }));
      box.appendChild(option('Delete Layout…', function () { deleteDialog(); }, { act: 'delete', disabled: !saved.length }));
      box.appendChild(divider());
      box.appendChild(option('Reset Layout', function () { layout().reset(); }, { act: 'reset', disabled: layout().isDefault() }));
    });
  }

  function dialog(title) {
    var back = document.createElement('div');
    back.className = 'lrd-layout-dialog';
    var box = document.createElement('div');
    box.className = 'lrd-layout-dialog-box';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', title);
    var h = document.createElement('h3');
    h.textContent = title;
    box.appendChild(h);
    back.appendChild(box);
    document.body.appendChild(back);
    function close() { back.remove(); document.removeEventListener('keydown', esc, true); }
    function esc(e) { if (e.key === 'Escape') { e.preventDefault(); close(); } }
    document.addEventListener('keydown', esc, true);
    back.addEventListener('pointerdown', function (e) { if (e.target === back) close(); });
    return { back: back, box: box, close: close };
  }
  function button(text, primary, onClick) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn' + (primary ? ' btn-primary' : '');
    b.textContent = text;
    b.addEventListener('click', onClick);
    return b;
  }

  function saveDialog() {
    var d = dialog('Save Current Layout');
    var input = document.createElement('input');
    input.type = 'text';
    input.id = 'lrd-layout-name';
    input.maxLength = 60;
    input.placeholder = 'e.g. Show day';
    var now = canon(layout().snapshot());
    var match = saved.filter(function (s) { return canon(s.layout) === now; })[0];
    input.value = match ? match.name : '';
    var note = document.createElement('p');
    note.className = 'lrd-layout-note';
    var err = document.createElement('p');
    err.className = 'lrd-layout-error';
    function noteFor() {
      var v = input.value.trim().toLowerCase();
      var hit = saved.filter(function (s) { return s.name.toLowerCase() === v; })[0];
      note.textContent = hit ? 'Saving replaces the layout "' + hit.name + '".'
                             : 'Saved layouts are shared with every screen connected to this app.';
    }
    function save() {
      var name = input.value.trim();
      if (!name) { input.focus(); return; }
      api('PUT', { name: name, layout: layout().snapshot() }).then(function (r) {
        saved = r.layouts || saved;
        d.close();
        say('Layout "' + name + '" saved');
      }, function (e) { err.textContent = e.message; });
    }
    input.addEventListener('input', noteFor);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); save(); }
    });
    var row = document.createElement('div');
    row.className = 'lrd-layout-buttons';
    row.appendChild(button('Cancel', false, d.close));
    row.appendChild(button('Save', true, save));
    d.box.appendChild(input);
    d.box.appendChild(note);
    d.box.appendChild(err);
    d.box.appendChild(row);
    noteFor();
    input.focus();
    input.select();
  }

  function deleteDialog() {
    var d = dialog('Delete Layout');
    var list = document.createElement('div');
    list.className = 'lrd-layout-list';
    var err = document.createElement('p');
    err.className = 'lrd-layout-error';
    function render() {
      list.innerHTML = '';
      if (!saved.length) { list.textContent = 'No saved layouts.'; return; }
      saved.forEach(function (item) {
        var row = document.createElement('div');
        row.className = 'lrd-layout-row';
        var name = document.createElement('span');
        name.textContent = item.name;
        row.appendChild(name);
        row.appendChild(button('Delete', false, function () {
          api('DELETE', { name: item.name }).then(function (r) {
            saved = r.layouts || [];
            say('Layout "' + item.name + '" deleted');
            render();
          }, function (e) { err.textContent = e.message; });
        }));
        list.appendChild(row);
      });
    }
    render();
    var row = document.createElement('div');
    row.className = 'lrd-layout-buttons';
    row.appendChild(button('Done', true, d.close));
    d.box.appendChild(list);
    d.box.appendChild(err);
    d.box.appendChild(row);
  }

  function init() {
    if (!layout()) return;
    var parent = document.querySelector('#menu-view .menu-has-submenu[data-action="layouts"]');
    if (parent) parent.addEventListener('mouseenter', fillLayouts);
    var viewItem = Array.prototype.filter.call(document.querySelectorAll('#menu-bar .menu-item'), function (m) {
      return m.textContent.trim() === 'View';
    })[0];
    if (viewItem) viewItem.addEventListener('click', fillLayouts);
    document.addEventListener('pointerdown', function (e) {
      if (e.button !== 0 || drag) return;
      var grip = e.target.closest && e.target.closest('[data-lrd-grip]');
      if (!grip || onControl(e.target)) return;
      startDrag(e, grip);
    });
    document.addEventListener('contextmenu', function (e) {
      var grip = e.target.closest && e.target.closest('[data-lrd-grip]');
      if (!grip || onControl(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      // This right-click is the panel's, so the app's own menu never hears
      // it: one it left open (a chip's, say) is closed here, or the stale
      // menu would read as this click's answer.
      if (window.app && typeof window.app.hideContextMenu === 'function') window.app.hideContextMenu();
      openMenu(grip.dataset.lrdGrip, e.clientX, e.clientY);
    }, true);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
