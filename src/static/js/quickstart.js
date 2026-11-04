/*
 * quickstart.js: in-app guided tours that DEMONSTRATE.
 *
 * Every step performs ONE real action, live, on a scratch demo show: a ghost
 * cursor travels to the control, the action happens through the app's own
 * handlers (a real click, a real mousedown/mousemove/mouseup drag, typed
 * characters), the result appears on the wall or in the tray, and a one-line
 * result note under the body confirms it. The user's own project is
 * snapshotted when a tour starts and put back when it ends.
 *
 *   - Quick Start: short first-run tour, auto-shows once, skippable, with a
 *     "Don't show on startup" checkbox. Reopen from Help -> Quick Start Guide.
 *   - Advanced Guide: the whole show, built step by step in front of you.
 *   - What's New: only the Advanced Guide steps added since a version (each
 *     step's `since`), each started from its own entry snapshot. The What's
 *     New window's Show me runs it (whatsnew.js, also Help -> What's New).
 *
 * Fully self-contained and offline (no CDN).
 *
 * A step is { target, place, title, body, center?, before?, after?, act?,
 * check? }. `act(t)` is the demonstration and `t` the toolkit (moveTo, hover,
 * click, type, select, drag, rightClick, pickMenu, cabinetPoint, wait, pause,
 * say, spot; `t.pace` is the timing table). `check(mem)` returns the result note when the action took, or null
 * when it did not. The tours are composed from ONE step library (STEPS)
 * so copy lives once; tests/test_tour_anchors.py drives every tour and proves
 * each step's anchor resolves AND its check returns a note.
 */
(function () {
    'use strict';

    var LS_KEY = 'lrd_quickstart_disabled'; // '1' = don't auto-show on launch

    // ── small helpers ────────────────────────────────────────────────────
    function A() { return window.app; }
    function R() { return window.canvasRenderer; }
    function $(sel, root) { return (root || document).querySelector(sel); }
    function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
        });
    }
    function j(method, url, body) {
        return fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body)
        }).then(function (r) { return r.json(); });
    }
    function sleep(ms) { return new Promise(function (res) { setTimeout(res, ms); }); }

    // Playback speed. 1 is the shipped pace (a step's act takes 3-10 s);
    // QuickStart.setSpeed(3) runs the same gestures three times faster for
    // an automated drive. Every wait scales with it.
    var speed = 1;
    // While Go to applies the steps between here and the target, every
    // pace is zero: the hand does not travel, rest or type a character at
    // a time, it just does the thing.
    // Polls for the app to respond (T.wait, a step's check) are never
    // scaled: they are how long a slow machine may take, not a pace. A
    // limit halved by the speed timed out on a CPU-starved run and the
    // step "did not take" a quarter second before it would have (1.6.0
    // QA, Clear the whole processor).
    function ms(n) { return S.jumping ? 0 : Math.max(0, Math.round(n / speed)); }

    // How long the engine waits on the app, in real milliseconds whatever
    // the speed. A step reports "did not take" only once its check has
    // been asked again and again for CHECK_LIMIT after the app settled
    // (Matt, 2026-11-03: every guide step passes first time, every time).
    var CHECK_LIMIT = 10000;   // a step's check, asked every CHECK_EVERY ms
    var CHECK_EVERY = 100;
    var SETTLE_LIMIT = 15000;  // the app's queued saves, PUTs and their echoes
    var ACT_LIMIT = 120000;    // an act that never ends fails, so the guide cannot hang

    // The pace of the ghost hand at speed 1: the pace a person works at,
    // not a script's (Matt, 2026-09-15: "make sure all the animations are
    // at a normal pace that a user might do"). Every figure goes through
    // ms(), so setSpeed scales the lot.
    var PACE = {
        travel: 450,        // px/s of cursor travel, with the easing
        travelMin: 350,     // ms: the shortest hop still reads as a move
        hover: 300,         // ms on the control, badge shown, before a press
        rest: 450,          // ms after a click, a select, a drop, a typed value
        key: 90,            // ms per typed character
        typed: 300,         // ms after the last character, before Enter/change
        dragPress: 200,     // ms held before the chip starts to move
        dragTravel: 350,    // px/s while dragging
        dragHover: 700,     // ms over the drop target, so the pending bracket reads
        dragRest: 400,      // ms after the release
        menuHold: 800,      // ms with a context menu open before the hand moves
        menuTravel: 350,    // px/s onto the menu item
        menuHover: 400,     // ms on the item before the click
        sweep: 220,         // px/s across chips or cabinets with Alt held
        sweepRest: 400,     // ms at the end of a sweep before the right-click
        view: 500,          // ms after a view tab lands
        opened: 800,        // ms after a popover, sheet, menu or dialog opens
        acted: 800          // ms after the action inside it, before the step settles
    };

    // ── live lookups (never hold references: the tray rebuilds wholesale) ──
    function screens() {
        var a = A();
        return ((a && a.project && a.project.layers) || []).filter(function (l) {
            return (l.type || 'screen') === 'screen';
        });
    }
    function wall() {
        var ls = screens();
        return ls.find(function (l) { return l.name === 'DEMO WALL'; }) || ls[0] || null;
    }
    function wall2() {
        var ls = screens();
        return ls.find(function (l) { return l.name === 'DEMO WALL 2'; }) || null;
    }
    // A screen the guide puts in for a step. initializeLayerDefaults gives
    // it the person's Preferences, and their bit depth, frame rate and Low
    // Latency change how many cabinets a port carries: a 10-bit, 50 Hz or
    // Low Latency preference cut the practice screens into other ports and
    // the steps that count them did not take (1.6.0 QA). The guide's
    // screens are always 8-bit, 60 Hz, Low Latency off. (The guide runs
    // on the shipped Preferences - guidePreferences - so this holds even
    // where that switch could not be made.)
    var PRACTICE_PROCESSING = { bitDepth: 8, frameRate: 60, lowLatency: false };
    function practiceScreen(layer) {
        A().initializeLayerDefaults(layer);
        Object.keys(PRACTICE_PROCESSING).forEach(function (k) { layer[k] = PRACTICE_PROCESSING[k]; });
        return layer;
    }
    function proc() { return ((A() && A()._processorsResolved) || [])[0] || null; }
    // The H9 the Mixed redundancy step puts beside the guide's own unit.
    function chassis() {
        return ((A() && A()._processorsResolved) || []).find(function (p) { return p.deviceId === 'novastar-h9'; }) || null;
    }
    function card() {
        var p = proc();
        var s = ((p && p.slots) || []).find(function (x) { return x && x.card; });
        return s ? s.card : null;
    }
    function distro() {
        var a = A();
        return (a && typeof a.getDistros === 'function' ? a.getDistros() : [])[0] || null;
    }
    function pins() {
        var a = A();
        return ((a && a.project && a.project.port_assignments) || {}).pins || [];
    }
    function wallPins() {
        var w = wall();
        return w ? pins().filter(function (p) { return String(p.layerId) === String(w.id); }) : [];
    }
    function owner() {
        var c = card();
        return c && A()._dataCableOwner ? A()._dataCableOwner('card', c.id) : null;
    }
    function snake() {
        var a = A();
        return (a && typeof a.getShowSnakes === 'function' ? a.getShowSnakes() : [])[0] || null;
    }
    function beach() { var a = A(); return (a && a.getBeaches ? a.getBeaches() : [])[0] || null; }
    function service() { var a = A(); return (a && a.getServices ? a.getServices() : [])[0] || null; }
    // A screen's row in the Screens panel (app-layers-panel.js renderLayers).
    function layerRow(l) { return '#layers-list .layer-item[data-layer-id="' + l.id + '"]'; }
    // The add-to-selection key: ⌘ on a Mac, Ctrl elsewhere (index.html
    // stamps the server's platform; the browser's own is the fallback).
    var IS_MAC = /^darwin/i.test(String(window.LRD_PLATFORM || '')) || (!window.LRD_PLATFORM && /Mac/i.test(navigator.platform || ''));
    var MOD_KEY = IS_MAC ? '\u2318' : 'Ctrl';
    var MOD_INIT = IS_MAC ? { metaKey: true } : { ctrlKey: true };
    // The first breakout box on the card (the resolved tree's `cvts`).
    function box() { var c = card(); return ((c && c.cvts) || [])[0] || null; }
    // What the distro's tray header prints: the load against the rating
    // ("0.0/400 A"), the supply ("208V·3φ").
    function distroUnit(d) { return d ? $('[data-lrd-distro="' + d.id + '"]') : null; }
    function distroUse(d) { var u = distroUnit(d); var e = u && u.querySelector('.hw-dock-unit-use'); return e ? e.textContent.trim() : ''; }
    function distroInfo(d) { var u = distroUnit(d); var e = u && u.querySelector('.hw-dock-unit-info'); return e ? e.textContent.trim() : ''; }
    function distroLegs(d) { var u = distroUnit(d); return !!(u && u.querySelector('.hw-dock-legs')); }
    // Where the header says the limit came from ("· 80% of 200 A"), empty
    // where the limit is the rating itself (app-dock.js _dockDistroGlance).
    function distroLim(d) { var u = distroUnit(d); var e = u && u.querySelector('.hw-dock-unit-lim'); return e ? e.textContent.trim() : ''; }
    // The circuits a screen shares through a 2fer or 3fer, as the wall
    // draws them (the canvas's own registry, the one the bracket and the
    // pill read): [{ num, ways, over, runIds }].
    function sharedCircuits(l) {
        var r = R();
        if (!l || !r || !r._nferGangs) return [];
        A()._circuitTailCache = null;
        return r._nferGangs(l).filter(function (s) { return (s.runIds || []).length > 1; });
    }
    // The connectors a distro's output rows put on its face (1.5), or 0
    // for a distro with no rows.
    function faceCount(d) { var f = d && A().distroFace ? A().distroFace(d) : null; return f ? f.boxes.length : 0; }
    // The distro's first Socapex output row, or null.
    function socaRow(d) {
        return (d && A().distroRows ? A().distroRows(d) : []).find(function (r) { return r.connector === 'soca' && !r.pairedWith; }) || null;
    }
    // The ⚙ popovers as a step's window (windowsOf): the guide's own
    // processor's, and its distro's.
    function procGearWindow() { var p = proc(); return p ? 'gear:proc-' + p.id : null; }
    function distroGearWindow() { var d = distro(); return d ? 'gear:distro-' + d.id : null; }
    // Open the distro's gear popover and ring it: the opening every gear
    // step makes before its one change (the press skipped when the step
    // before left it up for this one).
    function openDistroGear(t, d) {
        return openGear(t, 'distro-' + d.id).then(function (pop) {
            if (!pop) throw new Error('the distro\'s gear popover did not open');
            return t.spot(pop).then(function () { return t.pause(900); });
        });
    }
    // The Pixel Map's selected cabinets counted per screen, by layer id
    // (app-pixel-select.js _pixelMapSelectionHits).
    function pickedByScreen() {
        var a = A(), out = {};
        var hits = a && a._pixelMapSelectionHits ? a._pixelMapSelectionHits() : [];
        hits.forEach(function (h) { out[h.layer.id] = (out[h.layer.id] || 0) + 1; });
        return out;
    }
    // The index of a wall's cabinet at (row, col), counted from 0.
    function cabinetIndex(l, row, col) {
        var ps = (l && l.panels) || [];
        var i = ps.findIndex(function (p) { return Number(p.row) === row && Number(p.col) === col; });
        return i >= 0 ? i : row * (Number(l.columns) || 1) + col;
    }
    // The open gear popover, or null.
    function popover() { var pop = $('#hw-gear-popover'); return pop && pop.style.display === 'block' ? pop : null; }
    function mode() { var t = $('.view-tab.active[data-mode]'); return t ? t.dataset.mode : null; }
    function switchView(m) {
        if (mode() === m) return;
        var t = $('[data-mode="' + m + '"]');
        if (t) t.click();
    }
    function portsNeeded() {
        var w = wall();
        if (!w || !A().calculatePortAssignments) return 0;
        var seen = {};
        A().calculatePortAssignments(w).forEach(function (i) { seen[i.port] = 1; });
        return Object.keys(seen).length;
    }
    function lastPinnedSocket() {
        return wallPins().reduce(function (m, p) { return Math.max(m, Number(p.port) || 0); }, 0);
    }
    // The screen port (1-based) of the wall with no pin, lowest first.
    function unpinnedScreenPort() {
        var have = {};
        wallPins().forEach(function (p) { have[Number(p.index) + 1] = 1; });
        var n = portsNeeded();
        for (var i = 1; i <= n; i++) if (!have[i]) return i;
        return null;
    }
    // A spare MAIN socket from 20 up: free, and not claimed by role as
    // another socket's return (under sequential pairing the evens are).
    // The highest free socket the card actually lists - a bare MX40 Pro is
    // its 20 RJ45s (2026-09-30), so no fixed range is assumed.
    function sparePinSocket() {
        var c = card();
        if (!c) return 20;
        var prefix = 'port-' + c.id + '-';
        var nums = $$('[data-hwdock^="' + prefix + '"]')
            .map(function (f) { return Number(f.getAttribute('data-hwdock').slice(prefix.length)); })
            .filter(function (n) { return n > 0; })
            .sort(function (a, b) { return b - a; });
        for (var i = 0; i < nums.length; i++) {
            var face = $('[data-hwdock="' + prefix + nums[i] + '"]');
            var tile = face && face.closest('.lrd-tile');
            if (tile && (tile.classList.contains('lrd-tile-occupied') || tile.classList.contains('lrd-tile-gold'))) continue;
            if (/backs up/.test((face && face.textContent) || '')) continue;
            return nums[i];
        }
        return 20;
    }
    // The lowest pinned socket that is not on the snake (sockets 1-4).
    function loosePinnedSocket() {
        var sn = snake();
        var on = {};
        ((sn && sn.members) || []).forEach(function (m) { on[m.socket] = 1; });
        var list = wallPins().map(function (p) { return Number(p.port); })
            .filter(function (s) { return !on[s]; }).sort(function (a, b) { return a - b; });
        return list[0] || 5;
    }
    // The screen port pinned by hand: the wall pin on the highest socket
    // (Pin a port by hand parks one on the card's highest free socket).
    function handPinnedScreenPort() {
        var top = null;
        wallPins().forEach(function (p) { if (!top || Number(p.port) > Number(top.port)) top = p; });
        return top ? Number(top.index) + 1 : null;
    }
    function flagOk() { var f = $('#hw-dock-flag'); return !!f && f.classList.contains('hw-dock-flag-ok'); }
    function flagCount() { var b = $('#hw-dock-flag .hw-dock-flag-n'); return b ? b.textContent.trim() : ''; }
    // The Clear item's label as the open menu prints it ("Clear port SR-20",
    // "Clear SR", "Clear SL 1"): it names the thing under the cursor.
    function clearLabel() { var i = $('#context-menu [data-action="hw-clear"]'); return i ? i.textContent.trim() : ''; }
    // The circuits landed on multi `n` of distro `d`, read off its chips.
    function multiHeld(d, n) {
        if (!d) return 0;
        return $$('[data-hwdock^="tail-' + d.id + '-' + n + '-"]').filter(function (f) {
            var x = f.closest('.lrd-tile'); return x && x.classList.contains('lrd-tile-occupied');
        }).length;
    }
    function flagRows() { return $$('#hw-dock-attach .hw-dock-attach-row'); }
    function sheetButton() { return $('#hardware-dock-body .hw-dock-cablebtn-data'); }
    function sheetOpen() { return !!$('#hardware-dock-body .hw-dock-cablebtn-data.hw-dock-cablebtn-on'); }
    function openSheet() {
        var o = owner();
        if (!o || sheetOpen()) return;
        A()._setDataCableSheetOpen(o, true);
        A().renderHardwareDock();
    }
    function closeSheet() {
        var o = owner();
        if (!o) return;
        A()._setDataCableSheetOpen(o, false);
        if (mode() === 'data-flow') A().renderHardwareDock();
    }
    // The breakout box's own ≡ sheet (its Fiber section is the first block).
    function boxOwner() { var b = box(); return b ? { kind: 'cvt', id: b.id } : null; }
    function boxSheetOpen() { var b = box(); return !!(b && $('[data-lrd-fiber-row="' + b.id + '"]')); }
    function openBoxSheet() {
        var o = boxOwner();
        if (!o || boxSheetOpen()) return;
        A()._setDataCableSheetOpen(o, true);
        A().renderHardwareDock();
    }
    function closeBoxSheet() {
        var o = boxOwner();
        if (!o) return;
        A()._setDataCableSheetOpen(o, false);
        if (mode() === 'data-flow') A().renderHardwareDock();
    }
    // The box's Primary 1 link and its cable, or null.
    function boxLink() {
        var b = box(), a = A();
        var l = b && b.fiberLinks && b.fiberLinks.p1;
        var c = l && a.getFiberCable ? a.getFiberCable(l.cable) : null;
        // The link by the box's own port name - "OPT 1" on a CVT10.
        var title = a.fiberLinkTitle ? a.fiberLinkTitle('p1', b) : 'OPT 1';
        return c ? { link: l, cable: c, title: title } : null;
    }
    function boxStrandsText(bl) {
        var a = A();
        return bl.link.strands.map(function (n) { return a.fiberStrandName(n, bl.cable); }).join(' and ');
    }
    // ── a window shared from one step to the next ────────────────────────
    // A step's `window` names the windows it works in: a key, a list of
    // keys, or a function returning either (read live, so a key can carry
    // the id of the hardware the guide put in). 'export:<format>' is the
    // Export dialog on that format, 'prefs:<tab>' Preferences on that tab,
    // 'pull-sheet' the pull sheet editor, 'gear:<id>' the ⚙ popover of the
    // header whose data-hwpop is <id>, 'picker:<mode>' the panel library.
    // On Next and Back, a window both steps name stays up (S.keep, which
    // every close below reads): the step left does not close it, the step
    // entered does not open it again, and a restore between the two
    // refills it in place (refreshHeld). Matt, 2026-11-04, What's New
    // steps 11 to 15: each step "collapses the window and then reopens the
    // exact same window". A step jumped to, replayed or run on its own
    // keeps nothing and sets its window up from scratch, as before.
    function windowsOf(step) {
        var w = step && step.window;
        if (typeof w === 'function') { try { w = w(); } catch (e) { w = null; } }
        if (!w) return [];
        return (Array.isArray(w) ? w : [w]).filter(function (k) { return typeof k === 'string' && !!k; });
    }
    // The windows both steps name, in the order the step left names them.
    function sharedWindows(from, to) {
        var b = windowsOf(to);
        return windowsOf(from).filter(function (k) { return b.indexOf(k) >= 0; });
    }
    // Whether a window of this kind ('export', 'prefs', 'gear:proc-1') is
    // held open through the step change under way.
    function held(kind) {
        var keep = S.keep;
        if (!keep || !keep.length) return false;
        return keep.some(function (k) { return k === kind || k.indexOf(kind + ':') === 0; });
    }
    function prefsOpen() { var m = $('#preferences-modal'); return !!m && m.style.display === 'block'; }
    // A held window after the show under it was restored (Back, or the
    // entry snapshot a What's New step starts from): its fields read the
    // restored show, the way they would on a fresh open, without the
    // window ever leaving the screen. Each refill is the app's own open,
    // run on a window already up: it sets display to what it already is.
    function refreshHeld() {
        var a = A();
        (S.keep || []).forEach(function (k) {
            try {
                if (k.indexOf('export:') === 0) {
                    if (exportOpen()) a.openExportModal(k.slice('export:'.length));
                } else if (k.indexOf('prefs:') === 0) {
                    if (prefsOpen()) { a.openPreferencesModal(); a.showPreferencesTab(k.slice('prefs:'.length)); }
                } else if (k === 'pull-sheet') {
                    if (pullSheetOpen() && a.renderPullSheetEditor) a.renderPullSheetEditor();
                } else if (k.indexOf('gear:') === 0) {
                    if (a._hwPopoverRefresh) a._hwPopoverRefresh();
                }
            } catch (e) { console.warn('QuickStart: a shared window was not refilled', e); }
        });
    }
    // The ⚙ popover of header `id` open, the gear pressed only when it is
    // not up already: on a step that shares it with the one before, the
    // popover is there and a press would toggle it shut.
    function openGear(t, id) {
        var a = A();
        if (a && a._hwPopover && a._hwPopover.id === id && popover()) return Promise.resolve(popover());
        return t.click('[data-hwpop="' + id + '"]').then(function () { return t.wait(popover); });
    }
    function exportOpen() { var m = $('#export-modal'); return !!m && m.style.display === 'block'; }
    function openExport() {
        var a = A();
        if (!a || typeof a.openExportModal !== 'function') return;
        if (!exportOpen() || ($('#export-format') && $('#export-format').value !== 'binder')) {
            a.openExportModal('binder');
        }
    }
    function closeExport() {
        if (held('export')) return;
        var m = $('#export-modal'); if (m) m.style.display = 'none';
    }
    // The screen chooser (app-presets.js openPresetPicker), closed with its
    // library search cleared so the next person to open it sees every panel.
    // AVG_ROW is the library row the average power step reads: a panel
    // whose sheet gives both a max and an average.
    var AVG_ROW = '#panel-catalog-list .panel-catalog-row[data-name="Black Pearl BP2V2"]';
    function pickerOpen() { var m = $('#preset-picker-modal'); return !!m && m.style.display === 'block'; }
    // The library up as Add Screen opens it (not File > New's chooser).
    function addPickerOpen() { var a = A(); return pickerOpen() && !!a && (a._pickerMode || 'add') === 'add'; }
    // Add Screen pressed, the library opened: skipped when the step
    // before left it up for this one (window 'picker:add').
    function openAddPicker(t) {
        if (addPickerOpen()) return Promise.resolve();
        return t.hover('#layers-list .canvas-add-btn').then(function (p) {
            press(true); ripple(p.x, p.y);
            return t.pause(200);
        }).then(function () {
            press(false);
            A().openPresetPicker();
        });
    }
    // The start page a launch opens on (app-start-page.js).
    function startPageUp() { var m = $('#start-page-modal'); return !!m && m.style.display === 'block'; }
    function closePicker() {
        var s = $('#panel-catalog-search'), a = A();
        if (s && s.value) { s.value = ''; s.dispatchEvent(new Event('input', { bubbles: true })); }
        // Held for the next step: the search is cleared, the window stays.
        if (held('picker')) return;
        if (a && typeof a.closePresetPicker === 'function') a.closePresetPicker();
        else { var m = $('#preset-picker-modal'); if (m) m.style.display = 'none'; }
    }
    // The pull sheet editor (app-pull-sheet-editor.js), opened from the
    // Export dialog's Edit rows; closed here without the editor's own trip
    // back to the Export dialog.
    var PANEL_ROW = '#pull-sheet-board tr.pull-row[data-side="panel"]';
    function pullSheetOpen() { var m = $('#pull-sheet-modal'); return !!m && m.style.display === 'block'; }
    function closePullSheet() {
        if (held('pull-sheet')) return;
        var a = A(), m = $('#pull-sheet-modal');
        if (a) a._pullSheetReturnToExport = false;
        if (m) m.style.display = 'none';
    }
    function hideMenus() {
        $$('.menu-dropdown').forEach(function (m) { m.style.display = 'none'; });
        $$('#menu-bar .menu-item.active').forEach(function (i) { i.classList.remove('active'); });
    }
    function closePrefs() {
        if (held('prefs')) return;
        var m = $('#preferences-modal');
        if (m) m.style.display = 'none';
    }
    function closeFlag() {
        var a = A();
        if (!a || !a._dockFlagOpen) return;
        a._dockFlagOpen = false;
        if (typeof a._renderDockFlag === 'function') a._renderDockFlag(mode() || '');
        if (typeof a.settleLayout === 'function') a.settleLayout();
    }
    function closePopover() {
        var a = A();
        if (!a || !a._hwPopoverClose) return;
        if (a._hwPopover && held('gear:' + a._hwPopover.id)) return;
        a._hwPopoverClose();
    }
    function dockDropPoint() {
        // Anywhere inside the tray is the release (app-dock.js _dockHitTest
        // tests the tray's rectangle, not the element): the header bar's
        // middle is a spot no chip ever occupies. `again` re-measures it at
        // release time - revealing the chip may have grown the tray.
        var dock = $('#hardware-dock');
        var r = dock.getBoundingClientRect();
        var head = $('#hw-dock-head') || dock;
        var hr = head.getBoundingClientRect();
        return { x: r.left + r.width * 0.5, y: hr.top + Math.min(14, hr.height / 2), again: dockDropPoint };
    }

    // ── the tray, normalised for the demo ────────────────────────────────
    // The person's tray is theirs: folded to nothing, dragged to any
    // height, every unit and strip folded as they left it (Matt, 2026-09-15,
    // testing on his own machine with the tray folded and a multi strip
    // minimised: the chip the step dragged had no size, and the drag began
    // from the wrong element). The tour records that state, sets the tray
    // up for the demo - open, at a working height, every section unfolded -
    // and puts it all back on exit. Mid-tour, every gesture on a tray
    // element goes through revealInTray first, so a fold the person makes
    // while watching cannot send the hand to the wrong place either.
    var DOCK_COLLAPSE_KEY = 'ledRasterSidebarCollapsed_dock';   // app-core.js initSidebarToggles
    var DOCK_HEIGHT_KEY = 'lrd_dock_h';                          // theme.js PANELS 'dock'
    var DOCK_FOLD_PREFIX = 'ledRasterPanelCollapsed_hwdock-';   // app-core.js _setSectionCollapsed
    var DOCK_MIN = 100, DOCK_FLOOR = 120;                        // theme.js's clamp for the dock
    // The tray height the demo works at: a distro's header, LEGS and
    // OUTPUTS rows, a multi strip's header and its two rows of chips, with
    // the strip in view without a scroll.
    var TOUR_DOCK_H = 250;
    function dock() { return $('#hardware-dock'); }
    function dockCollapsed() { var d = dock(); return !!d && d.classList.contains('collapsed'); }
    function dockHeightNow() {
        return parseInt(getComputedStyle(document.documentElement).getPropertyValue('--lrd-dock-h'), 10) || 172;
    }
    function dockCeiling() {
        var d = dock(), col = d && d.parentElement;
        var h = col ? col.clientHeight : 0;
        if (!(h > 0)) h = window.innerHeight || 0;
        return Math.max(DOCK_MIN, Math.round(h - DOCK_FLOOR));
    }
    // A drag-resize's move (theme.js startDrag): the size onto the CSS var
    // under .lrd-resizing so no transition runs, then the canvas re-measured
    // at once. Nothing written to localStorage - the person's saved height
    // stays theirs.
    function setDockHeight(px) {
        var a = A(), app = $('#app'), d = dock();
        var v = Math.max(DOCK_MIN, Math.min(dockCeiling(), Math.round(px)));
        if (app) app.classList.add('lrd-resizing');
        document.documentElement.style.setProperty('--lrd-dock-h', v + 'px');
        if (d) void d.offsetHeight;   // the new height is in layout now
        if (app) app.classList.remove('lrd-resizing');
        if (a && a.remeasureCanvas) a.remeasureCanvas();
        if (a && a.settleLayout) a.settleLayout();
    }
    // The tray's own toggle (app-core.js initSidebarToggles owns the class,
    // the body class and the settle), instant: the height transition is
    // suppressed while it flips so the canvas can be re-measured now.
    function setDockCollapsed(v) {
        var a = A(), app = $('#app'), d = dock();
        if (dockCollapsed() === !!v) return;
        var btn = $('#hardware-dock-toggle');
        if (!btn) return;
        if (app) app.classList.add('lrd-resizing');
        btn.click();
        if (d) void d.offsetHeight;
        if (app) app.classList.remove('lrd-resizing');
        if (a && a.remeasureCanvas) a.remeasureCanvas();
    }
    // The node a gesture aims at, alive: the app restates a panel whenever
    // its model moves - the tray rebuilds on the page's own late
    // layer_updated echo, between any two of a step's moves - and the node
    // found before is then a detached copy. Its successor is found by the
    // stable key the app itself restores focus by: a chip's data-hwdock, a
    // field's data-lrd-field, else its id.
    function live(el) {
        if (!el || el.isConnected || !el.dataset) return el;
        var key = el.dataset.hwdock ? '[data-hwdock="' + CSS.escape(el.dataset.hwdock) + '"]'
            : (el.dataset.lrdField ? '[data-lrd-field="' + CSS.escape(el.dataset.lrdField) + '"]'
                : (el.id ? '#' + CSS.escape(el.id) : null));
        return (key && $(key)) || el;
    }
    function trayName(el) {
        if (!el) return 'nothing';
        if (el.dataset && el.dataset.hwdock) return el.dataset.hwdock;
        if (el.dataset && el.dataset.lrdField) return el.dataset.lrdField;
        if (el.id) return '#' + el.id;
        var c = String(el.className || '').split(' ')[0];
        return c ? '.' + c : el.tagName.toLowerCase();
    }
    // Before any gesture on a tray element: the tray open, tall enough,
    // every folded section above the element unfolded (the app's own fold
    // machinery, so the state it persists follows), the element scrolled
    // into the tray's view, then measured - and an element that still has
    // no size or lies outside the tray is a thrown Error naming it, never
    // a gesture aimed at whatever sized ancestor was nearest.
    function revealInTray(el) {
        var a = A(), d = dock();
        if (!a || !d || !el || !d.contains(el)) return Promise.resolve(el);
        var name = trayName(el);
        if (dockCollapsed()) setDockCollapsed(false);
        if (dockHeightNow() < TOUR_DOCK_H) setDockHeight(TOUR_DOCK_H);
        return sleep(0).then(function () {
            // A rebuild between the query and now (the flip settles the
            // layout, or a late echo restates the tray) replaces every node
            // in the tray; the element's stable key finds its successor.
            el = live(el);
            if (!el || !el.isConnected) throw new Error(name + ' is not in the tray');
            if (typeof a._dockRevealSections === 'function') a._dockRevealSections(el);
            var r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) {
                // A field inside a closed chip: the editor opens for it.
                var tile = el.closest('.lrd-tile');
                if (tile && !tile.classList.contains('lrd-tile-open') && el.closest('.lrd-tile-body')
                        && typeof a._setTileOpen === 'function') {
                    a._setTileOpen(tile, true);
                }
            }
            try { el.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) {}
            r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) throw new Error(name + ' has no size in the tray');
            var dr = d.getBoundingClientRect();
            var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
            if (cx < dr.left || cx > dr.right || cy < dr.top || cy > dr.bottom) {
                throw new Error(name + ' is outside the tray');
            }
            return el;
        });
    }
    function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
    function lsPut(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) {} }
    // The person's tray: open or folded, its height (live and saved), and
    // every unit's, box's, distro's and strip's fold.
    function captureTray() {
        return {
            collapsed: dockCollapsed(),
            collapsedSaved: lsGet(DOCK_COLLAPSE_KEY),
            height: dockHeightNow(),
            heightSaved: lsGet(DOCK_HEIGHT_KEY),
            folds: lsKeys(DOCK_FOLD_PREFIX)
        };
    }
    // The demo's tray: open, at the working height, no fold remembered for
    // any unit - the units the tour mints come up open, whatever the person
    // had folded under the same ids on their own show.
    function seedTray() {
        lsKeys(DOCK_FOLD_PREFIX).forEach(function (e) { lsPut(e.k, null); });
        if (dockCollapsed()) setDockCollapsed(false);
        if (dockHeightNow() < TOUR_DOCK_H) setDockHeight(TOUR_DOCK_H);
    }
    function restoreTray(t) {
        var a = A();
        if (!t) return;
        lsKeys(DOCK_FOLD_PREFIX).forEach(function (e) { lsPut(e.k, null); });
        (t.folds || []).forEach(function (e) { lsPut(e.k, e.v); });
        if (t.height) setDockHeight(t.height);
        lsPut(DOCK_HEIGHT_KEY, t.heightSaved);
        setDockCollapsed(!!t.collapsed);
        lsPut(DOCK_COLLAPSE_KEY, t.collapsedSaved);
        // The folds re-apply on the next build (app-core.js
        // _wireSectionCollapse reads them back).
        try { if (a && a.renderHardwareDock) a.renderHardwareDock(); } catch (e) {}
    }

    // ── the side panels, normalised for the demo ─────────────────────────
    // The same rule as the tray, for the two sidebars and the sections in
    // them (a friend of Matt's, 2026-09-16, Firefox on Windows: Screen Info
    // folded and the right panel folded away - step 3 reported
    // "#cabinet-width has no size" and the callout sat in the middle of
    // the window, because the field was display:none under its fold and
    // the callout's home in the right sidebar was not there). The tour
    // records both panels' state and every section fold, opens what a step
    // is about to use - the panel a target lives in, every fold that hides
    // it - through the app's own toggles, keeps the right sidebar open so
    // the callout's spot exists, and puts it all back on exit.
    var SIDE_COLLAPSE_KEYS = {                                  // app-core.js initSidebarToggles
        left: 'ledRasterSidebarCollapsed_left', right: 'ledRasterSidebarCollapsed_right'
    };
    var PANEL_FOLD_PREFIX = 'ledRasterPanelCollapsed_';        // app-core.js _setSectionCollapsed
    function sidebar(side) { return $('#' + side + '-sidebar'); }
    function sidebarCollapsed(side) { var s = sidebar(side); return !!s && s.classList.contains('collapsed'); }
    // The panel's own toggle (app-core.js owns the class, the body class
    // and the settle), instant: the width transition is suppressed while
    // it flips so the canvas can be re-measured now - setDockCollapsed
    // turned on its side.
    function setSidebarCollapsed(side, v) {
        var a = A(), app = $('#app'), s = sidebar(side);
        if (!s || sidebarCollapsed(side) === !!v) return;
        var btn = $('#' + side + '-sidebar-toggle');
        if (!btn) return;
        if (app) app.classList.add('lrd-resizing');
        btn.click();
        void s.offsetWidth;
        if (app) app.classList.remove('lrd-resizing');
        if (a && a.remeasureCanvas) a.remeasureCanvas();
        S.home = null;   // the sidebar's room changed; measure the spot again
    }
    function sideOf(el) {
        if (!el) return null;
        var l = sidebar('left'), r = sidebar('right');
        if (l && l.contains(el)) return 'left';
        if (r && r.contains(el)) return 'right';
        return null;
    }
    // Every fold above `el` that hides it, undone through the app's own
    // fold machinery (so the state it persists follows and the restore on
    // exit can put the person's fold back). Only a fold that hides the
    // element: a control on a folded section's header is visible folded.
    function unfoldAbove(el) {
        var a = A();
        for (var n = el && el.parentElement; n; n = n.parentElement) {
            if (!n.classList || !n.classList.contains('lrd-sec-collapsed')) continue;
            if (a && typeof a._sectionFoldHides === 'function' && !a._sectionFoldHides(n, el)) continue;
            if (a && typeof a._setSectionCollapsed === 'function') a._setSectionCollapsed(n, false);
            else n.classList.remove('lrd-sec-collapsed');
        }
    }
    // Before any gesture on, or ring around, an element in a sidebar: the
    // sidebar open, every fold that hides the element undone, the element
    // scrolled into its panel's view. Synchronous - both toggles are.
    function revealInSidebar(el) {
        var side = sideOf(el);
        if (!side) return false;
        if (sidebarCollapsed(side)) setSidebarCollapsed(side, false);
        unfoldAbove(el);
        try { el.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) {}
        return true;
    }
    // Everything a step shows: its target, every control it rings, every
    // control its act will visit (`avoid`). Revealed as the step opens, so
    // the ring measures the control where it is and the callout's spot is
    // measured against a panel that is there.
    function revealStep(step) {
        if (!step || step.center) return;
        [step.target].concat(step.ring || [], step.avoid || []).forEach(function (q) {
            if (typeof q === 'function') { try { q = q(); } catch (e) { q = null; } }
            var el = null;
            try { el = typeof q === 'string' ? $(q) : (q && q.nodeType === 1 ? q : null); } catch (e) {}
            if (el) revealInSidebar(el);
        });
    }
    // The callout's home is in the right sidebar; a tour with that sidebar
    // folded away would have the callout in the middle of the window.
    function ensureCalloutHome() {
        if (sidebarCollapsed('right')) setSidebarCollapsed('right', false);
    }
    function sidebarFoldKeys() {
        return lsKeys(PANEL_FOLD_PREFIX).filter(function (e) { return e.k.indexOf(DOCK_FOLD_PREFIX) !== 0; });
    }
    // The person's panels: each sidebar open or folded (live and saved),
    // and every section fold in either sidebar (live, and every saved key
    // outside the tray's - the tray is captureTray's).
    function capturePanels() {
        return {
            left: sidebarCollapsed('left'), leftSaved: lsGet(SIDE_COLLAPSE_KEYS.left),
            right: sidebarCollapsed('right'), rightSaved: lsGet(SIDE_COLLAPSE_KEYS.right),
            folded: $$('#left-sidebar .lrd-sec-collapsed, #right-sidebar .lrd-sec-collapsed')
                .map(function (n) { return n.dataset.lrdSecId; }).filter(Boolean),
            folds: sidebarFoldKeys()
        };
    }
    // The demo's panels: the right sidebar open with its sections unfolded
    // (the callout's spot is measured off the Screens list), the left one
    // opened as steps reach into it.
    function seedPanels() {
        ensureCalloutHome();
        $$('#right-sidebar .lrd-sec-collapsed').forEach(function (n) {
            var a = A();
            if (a && typeof a._setSectionCollapsed === 'function') a._setSectionCollapsed(n, false);
        });
    }
    // The panels where the guides expect them: a guide's steps point at the
    // default places (Screens down the right, the tray under the canvas), so
    // a person's own arrangement is set aside for the guide - not saved over,
    // the screen's saved arrangement stays as it was - and given back at the
    // end, or on the next launch if the guide never ended.
    function seedLayout() {
        var L = window.LRD_LAYOUT;
        if (L && !L.isDefault()) L.reset({ save: false });
    }
    function restoreLayout(rings) {
        var L = window.LRD_LAYOUT;
        if (L && Array.isArray(rings)) L.apply(rings);
    }
    function restorePanels(p) {
        var a = A();
        if (!p) return;
        var folded = {};
        (p.folded || []).forEach(function (id) { folded[id] = 1; });
        $$('#left-sidebar [data-lrd-sec-id], #right-sidebar [data-lrd-sec-id]').forEach(function (n) {
            var want = !!folded[n.dataset.lrdSecId];
            if (n.classList.contains('lrd-sec-collapsed') === want) return;
            if (a && typeof a._setSectionCollapsed === 'function') a._setSectionCollapsed(n, want);
            else n.classList.toggle('lrd-sec-collapsed', want);
        });
        // The saved keys exactly as they were: the fold machinery wrote its
        // own on the way, and a key that was absent goes back to absent.
        sidebarFoldKeys().forEach(function (e) { lsPut(e.k, null); });
        (p.folds || []).forEach(function (e) { lsPut(e.k, e.v); });
        setSidebarCollapsed('left', !!p.left);
        lsPut(SIDE_COLLAPSE_KEYS.left, p.leftSaved);
        setSidebarCollapsed('right', !!p.right);
        lsPut(SIDE_COLLAPSE_KEYS.right, p.rightSaved);
    }

    // ── the canvas: every drop lands on what is visible ──────────────────
    // The canvas's backing store follows #canvas-wrapper (canvas.js
    // setupCanvas), and only on a resize or a staged settle: a frame set
    // while the wrapper was taller (the tray hidden in Pixel Map, or
    // folded) centres the wall on a height the wrapper no longer has, and
    // the bottom rows end up under the tray - where a release reads as a
    // clear (app-dock.js _dockHitTest tests the tray's rectangle first).
    // Matt, 2026-09-15: "the first part of this step is to clear the
    // circuit" - the multi drop, on a shorter window with a taller tray.
    function canvasWrapper() { return $('#canvas-wrapper'); }
    function canvasFresh() {
        var r = R(), w = canvasWrapper();
        if (!r || !w || typeof r.setupCanvas !== 'function') return;
        if (r.canvas.width !== w.clientWidth || r.canvas.height !== w.clientHeight) r.setupCanvas();
    }
    function insideCanvas(p, margin) {
        var w = canvasWrapper() || (R() && R().canvas);
        if (!w || !p) return false;
        var rc = w.getBoundingClientRect();
        return p.x >= rc.left + margin && p.x <= rc.right - margin
            && p.y >= rc.top + margin && p.y <= rc.bottom - margin;
    }
    function describeEl(el) {
        if (!el) return 'nothing';
        return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
            + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/)[0] : '');
    }
    // A canvas point a gesture is about to use: inside the visible
    // wrapper, clear of the tray's tab and its resize strip, and the
    // canvas itself under it (the overlay passes through during an act).
    function guardCanvasPoint(p) {
        if (!p || typeof p.worldX !== 'number') return p;
        if (!insideCanvas(p, 24)) {
            throw new Error('the cabinet at ' + Math.round(p.x) + ',' + Math.round(p.y) + ' is off the visible canvas');
        }
        var hit = document.elementFromPoint(p.x, p.y);
        var cv = R() && R().canvas;
        if (hit !== cv) throw new Error('the canvas is covered at ' + Math.round(p.x) + ',' + Math.round(p.y) + ' by ' + describeEl(hit));
        return p;
    }
    function snapshot() {
        var a = A();
        return JSON.parse(JSON.stringify(a.project, a._snapshotReplacer));
    }

    // ── styles ───────────────────────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById('qs-styles')) return;
        var css = ''
            + '#qs-catch{position:fixed;inset:0;z-index:2000000;}'
            + '#qs-spot{position:fixed;z-index:2000001;border-radius:8px;pointer-events:none;'
            + 'box-shadow:0 0 0 3px #e22330,0 0 0 9999px rgba(10,10,12,.62);transition:all .22s cubic-bezier(.4,0,.2,1);}'
            + '#qs-cursor{position:fixed;left:0;top:0;z-index:2000002;pointer-events:none;width:22px;height:22px;'
            + 'transition:opacity .18s;opacity:0;filter:drop-shadow(0 2px 3px rgba(0,0,0,.6));}'
            + '#qs-cursor.qs-show{opacity:1;}'
            + '#qs-cursor svg{display:block;width:22px;height:22px;overflow:visible;}'
            + '#qs-cursor .qs-dot{position:absolute;left:-3px;top:-3px;width:8px;height:8px;border-radius:50%;'
            + 'background:#e22330;box-shadow:0 0 6px #e22330;display:none;}'
            + '#qs-cursor.qs-press .qs-dot{display:block;}'
            + '#qs-cursor .qs-badge{position:absolute;left:24px;top:20px;white-space:nowrap;display:none;'
            + 'font:600 11px -apple-system,"Segoe UI",system-ui,sans-serif;color:#111;background:#f4f4f4;'
            + 'border:1px solid #888;border-bottom-width:3px;border-radius:5px;padding:2px 7px;box-shadow:0 2px 6px rgba(0,0,0,.5);}'
            + '#qs-cursor .qs-badge.qs-on{display:inline-block;}'
            + '.qs-ripple{position:fixed;z-index:2000002;pointer-events:none;width:28px;height:28px;margin:-14px 0 0 -14px;'
            + 'border-radius:50%;border:2px solid #e22330;background:rgba(226,35,48,.25);animation:qs-rip .45s ease-out forwards;}'
            + '@keyframes qs-rip{from{transform:scale(.4);opacity:1;}to{transform:scale(1.6);opacity:0;}}'
            + '#qs-callout{position:fixed;z-index:2000003;width:334px;max-width:calc(100vw - 32px);background:#2e2e2e;'
            + 'color:#f0f0f0;border:1px solid #3a3a3a;border-top:3px solid #e22330;border-radius:12px;'
            + 'box-shadow:0 14px 44px rgba(0,0,0,.55);font-family:-apple-system,"Segoe UI",system-ui,sans-serif;'
            + 'padding:16px 18px 13px;transition:left .22s cubic-bezier(.4,0,.2,1),top .22s cubic-bezier(.4,0,.2,1);}'
            + '#qs-callout h3{margin:0 0 7px;font-size:16px;font-weight:700;color:#fff;}'
            + '#qs-callout p{margin:0;font-size:13.5px;line-height:1.46;color:#d6d6d6;}'
            + '#qs-callout p b{color:#fff;font-weight:600;}'
            + '#qs-callout .qs-result{margin:9px 0 0;font-size:12.5px;line-height:1.4;color:#5fd08a;min-height:0;}'
            + '#qs-callout .qs-result:empty{display:none;}'
            + '#qs-callout .qs-result.qs-result-fail{color:#f06a6a;}'
            + '#qs-callout .qs-result.qs-result-wait{color:#b6b6b6;}'
            + '#qs-callout .qs-prog{margin:13px 0 11px;font-size:11px;color:#9a9a9a;letter-spacing:.02em;display:flex;align-items:center;gap:10px;flex-wrap:wrap;white-space:nowrap;}'
            + '#qs-callout .qs-hint{color:#777;}'
            + '#qs-callout .qs-jump{margin-left:auto;display:flex;align-items:center;gap:5px;color:#9a9a9a;}'
            + '#qs-callout .qs-jump input{width:46px;background:#1f1f1f;color:#f0f0f0;border:1px solid #4a4a4a;border-radius:5px;'
            + 'padding:2px 5px;font:600 11.5px -apple-system,"Segoe UI",sans-serif;text-align:center;}'
            + '#qs-callout .qs-jump input:focus{outline:none;border-color:#e22330;}'
            // The Go-to shade: the window is covered while the steps between
            // here and the target are applied, so nothing of the run is seen
            // - the person asked to land on step N with the show as step N
            // finds it, not to watch a speed run. pointer-events:none keeps
            // it out of every elementFromPoint the gestures rely on.
            + '#qs-fast{display:none;position:fixed;inset:0;z-index:2000004;pointer-events:none;'
            + 'background:rgba(14,14,14,.86);color:#fff;font:600 15px -apple-system,"Segoe UI",system-ui,sans-serif;'
            + 'align-items:center;justify-content:center;flex-direction:column;gap:10px;}'
            + '#qs-fast .qs-fast-sub{font-size:12px;font-weight:500;color:#9a9a9a;}'
            + '#qs-fast .qs-fast-bar{width:260px;height:4px;background:#333;border-radius:2px;overflow:hidden;}'
            + '#qs-fast .qs-fast-bar i{display:block;height:100%;background:#e22330;width:0;}'
            + 'body.qs-jumping #qs-callout,body.qs-jumping #qs-spot,body.qs-jumping #qs-cursor{visibility:hidden;}'
            + '#qs-callout .qs-cta{display:block;width:100%;margin:0 0 9px;background:#3c3c3c;color:#fff;'
            + 'border:1px solid #555;border-radius:7px;padding:8px;font:600 12.5px inherit;cursor:pointer;}'
            + '#qs-callout .qs-cta:hover{background:#474747;}'
            + '#qs-callout .qs-row{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 10px;}'
            + '#qs-callout .qs-chk{display:flex;align-items:center;gap:7px;font-size:11.5px;color:#b6b6b6;cursor:pointer;user-select:none;white-space:nowrap;}'
            + '#qs-callout .qs-chk input{width:14px;height:14px;accent-color:#e22330;cursor:pointer;}'
            + '#qs-callout .qs-btns{display:flex;gap:6px;margin-left:auto;}'
            + '#qs-callout button{font:600 12.5px -apple-system,"Segoe UI",sans-serif;border-radius:7px;padding:7px 11px;cursor:pointer;border:1px solid #4a4a4a;}'
            + '#qs-callout .qs-skip{background:transparent;color:#9a9a9a;border-color:transparent;padding:7px 6px;}'
            + '#qs-callout .qs-skip:hover{color:#e0e0e0;}'
            + '#qs-callout .qs-back,#qs-callout .qs-replay{background:#3c3c3c;color:#e0e0e0;}'
            + '#qs-callout .qs-replay{padding:7px 9px;}'
            + '#qs-callout .qs-next{background:#e22330;color:#fff;border-color:#8f1218;}'
            + '#qs-callout .qs-next:hover{background:#ef3340;}'
            + '#qs-callout[data-qs-state="running"] .qs-next,#qs-callout[data-qs-state="running"] .qs-back,'
            + '#qs-callout[data-qs-state="running"] .qs-replay{opacity:.45;cursor:progress;}'
            + '#qs-callout .qs-arrow{position:absolute;width:14px;height:14px;background:#2e2e2e;border:1px solid #3a3a3a;transform:rotate(45deg);}'
            + '.qs-pass{pointer-events:none !important;}';
        var s = document.createElement('style');
        s.id = 'qs-styles';
        s.textContent = css;
        document.head.appendChild(s);
    }

    // ── the overlay, the spotlight, the callout, the ghost cursor ────────
    var els = null;
    var cur = { x: 0, y: 0, shown: false };

    function build() {
        injectStyles();
        var c = document.createElement('div'); c.id = 'qs-catch';
        var spot = document.createElement('div'); spot.id = 'qs-spot';
        var call = document.createElement('div'); call.id = 'qs-callout';
        var cursor = document.createElement('div'); cursor.id = 'qs-cursor';
        cursor.innerHTML =
            '<svg viewBox="0 0 22 22" aria-hidden="true">'
            + '<path d="M2 1.5 L2 17.5 L6.3 13.6 L9.4 20.6 L12.6 19.2 L9.6 12.4 L15.2 12.4 Z" '
            + 'fill="#ffffff" stroke="#1a1a1a" stroke-width="1.4" stroke-linejoin="round"/></svg>'
            + '<span class="qs-dot"></span><span class="qs-badge"></span>';
        document.body.appendChild(c);
        document.body.appendChild(spot);
        document.body.appendChild(cursor);
        document.body.appendChild(call);
        c.addEventListener('click', function (e) { e.stopPropagation(); });
        // A press on the callout (Next, Back, the Go to box) is the
        // guide's, never the app's click-away: the gear popover closes on
        // any document mousedown outside it, and Next would shut the
        // popover the next step shares.
        ['mousedown', 'pointerdown', 'touchstart'].forEach(function (type) {
            call.addEventListener(type, function (e) { e.stopPropagation(); });
        });
        var fast = document.createElement('div'); fast.id = 'qs-fast';
        document.body.appendChild(fast);
        els = { catch: c, spot: spot, callout: call, cursor: cursor, fast: fast };
        cur.x = window.innerWidth / 2; cur.y = window.innerHeight / 2;
        setCursor(cur.x, cur.y);
        window.addEventListener('resize', reposition);
        document.addEventListener('keydown', onKey, true);
    }

    function disabled() { try { return localStorage.getItem(LS_KEY) === '1'; } catch (e) { return false; } }
    function setDisabled(v) { try { v ? localStorage.setItem(LS_KEY, '1') : localStorage.removeItem(LS_KEY); } catch (e) {} }

    function setCursor(x, y) {
        cur.x = x; cur.y = y;
        if (els) els.cursor.style.transform = 'translate(' + Math.round(x) + 'px,' + Math.round(y) + 'px)';
    }
    function showCursor() { if (S.fast) return; if (els) els.cursor.classList.add('qs-show'); cur.shown = true; }
    function hideCursor() { if (els) els.cursor.classList.remove('qs-show'); cur.shown = false; badge(''); press(false); }
    function badge(text) {
        if (!els) return;
        var b = els.cursor.querySelector('.qs-badge');
        b.textContent = text || '';
        b.classList.toggle('qs-on', !!text);
    }
    function press(on) { if (els) els.cursor.classList.toggle('qs-press', !!on); }
    function ripple(x, y) {
        var r = document.createElement('div');
        r.className = 'qs-ripple';
        r.style.left = x + 'px'; r.style.top = y + 'px';
        document.body.appendChild(r);
        setTimeout(function () { r.remove(); }, 480);
    }
    // Eased travel at PACE.travel px/s (or `pxPerSec`), never shorter than
    // PACE.travelMin, resolved on arrival; `onFrame` sees every
    // intermediate point (a drag dispatches its mousemoves from it).
    function animateTo(x, y, onFrame, pxPerSec) {
        return new Promise(function (resolve) {
            var x0 = cur.x, y0 = cur.y;
            var dist = Math.hypot(x - x0, y - y0);
            var dur = ms(Math.max(PACE.travelMin, dist / (pxPerSec || PACE.travel) * 1000));
            var t0 = performance.now();
            function frame(now) {
                var k = dur <= 0 ? 1 : Math.min(1, (now - t0) / dur);
                var e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
                var px = x0 + (x - x0) * e, py = y0 + (y - y0) * e;
                setCursor(px, py);
                if (onFrame) { try { onFrame(px, py); } catch (err) { /* keep travelling */ } }
                if (k < 1) requestAnimationFrame(frame);
                else resolve();
            }
            requestAnimationFrame(frame);
        });
    }

    // While an act runs, nothing of the tour's may sit under a hit-test:
    // document.elementFromPoint (the tray's drop hit-test, the sweeps, every
    // context-menu builder) would otherwise return the overlay.
    function passthrough(on) {
        if (!els) return;
        [els.catch, els.spot, els.cursor, els.callout].forEach(function (el) {
            el.classList.toggle('qs-pass', !!on);
        });
    }

    // ── the input shield ─────────────────────────────────────────────────
    // While a step runs (its act, the wait on the app, its check) the
    // person's own mouse and keys never reach the app. The overlay passes
    // through during an act, so without this a hand resting on the mouse
    // moved the tray's drag (it follows every document mousemove) off its
    // target, and a second click on Next fell through the callout and shut
    // the popover or dialog the act had opened (1.6.0 QA: a dozen drag
    // steps and a dozen popover steps). Only real input is swallowed: the
    // guide's own gestures are dispatched events (isTrusted false) and go
    // through. Back, Next and the replay button do nothing while a step
    // runs; Skip and Escape end the guide once the step settles.
    // Registered on the window, capturing, when this file loads - before
    // the app's own window listeners - so nothing of the app's sees the
    // event first.
    var SHIELD_EVENTS = [
        'pointerdown', 'pointerup', 'pointermove', 'pointerover', 'pointerout',
        'pointerenter', 'pointerleave', 'pointercancel',
        'mousedown', 'mouseup', 'mousemove', 'mouseover', 'mouseout', 'mouseenter', 'mouseleave',
        'click', 'dblclick', 'auxclick', 'contextmenu', 'wheel',
        'touchstart', 'touchmove', 'touchend', 'touchcancel', 'dragstart',
        'keydown', 'keyup', 'keypress'
    ];
    function shielding() { return !!(S && S.visible && S.running); }
    function hitsEl(el, x, y) {
        if (!el) return false;
        var r = el.getBoundingClientRect();
        return r.width > 0 && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    }
    var SHIELD_KEYS = { keydown: 1, keyup: 1, keypress: 1 };
    function onShield(e) {
        if (!e.isTrusted || !S || !S.visible) return;
        if (!S.running) {
            // A settled step: the callout is the person's (its buttons, the
            // Go to box), and Enter and Escape go to onKey. Nothing else
            // reaches the app: the overlay is only the click's target, and
            // a key went straight to the app (Delete on the selected demo
            // wall broke the next step).
            if (els && e.target && e.target.nodeType === 1 && els.callout.contains(e.target)) return;
            if (SHIELD_KEYS[e.type] && (e.key === 'Enter' || e.key === 'Escape')) return;
            e.stopImmediatePropagation();
            if (e.cancelable) e.preventDefault();
            return;
        }
        if (e.type === 'keydown' && e.key === 'Escape' && !e.repeat) end();
        else if (e.type === 'click' && els && hitsEl(els.callout.querySelector('#qs-skip'), e.clientX, e.clientY)) end();
        e.stopImmediatePropagation();
        if (e.cancelable) e.preventDefault();
    }
    SHIELD_EVENTS.forEach(function (type) {
        window.addEventListener(type, onShield, { capture: true, passive: false });
    });

    // ── placement ────────────────────────────────────────────────────────
    var spotRect = null;   // the rectangle the spotlight rings right now

    function rectOf(el) {
        if (!el) return null;
        try { el.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) {}
        var r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return null;
        return r;
    }
    function stepTargetEl(step) {
        if (!step) return null;
        var sel = typeof step.target === 'function' ? step.target() : step.target;
        if (!sel) return null;
        try { return $(sel); } catch (e) { return null; }
    }
    // The ring for a step: its target's rectangle, or - when the step names
    // several controls in `ring` (the two fields of a size, the columns and
    // the rows) - the one rectangle that holds them all.
    function stepRect(step, el) {
        if (!step) return null;
        var list = (step.ring || []).map(function (q) {
            if (typeof q === 'function') { try { q = q(); } catch (e) { q = null; } }
            return typeof q === 'string' ? $(q) : q;
        }).filter(Boolean);
        if (!list.length) return rectOf(el);
        var u = null;
        list.forEach(function (e) {
            var r = rectOf(e);
            if (!r) return;
            u = u ? { left: Math.min(u.left, r.left), top: Math.min(u.top, r.top),
                      right: Math.max(u.right, r.right), bottom: Math.max(u.bottom, r.bottom) } : { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
        });
        if (!u) return rectOf(el);
        return { left: u.left, top: u.top, right: u.right, bottom: u.bottom, width: u.right - u.left, height: u.bottom - u.top };
    }
    function setSpot(r) {
        var spot = els.spot;
        spotRect = r;
        spot.style.display = 'block';
        if (r) {
            var pad = 6;
            spot.style.left = (r.left - pad) + 'px';
            spot.style.top = (r.top - pad) + 'px';
            spot.style.width = (r.width + pad * 2) + 'px';
            spot.style.height = (r.height + pad * 2) + 'px';
        } else {
            spot.style.left = '50%'; spot.style.top = '50%';
            spot.style.width = '0px'; spot.style.height = '0px';
        }
    }
    // The callout's home when it points at nothing: inside the right
    // sidebar, below its last button (Save as Preset) and above the Notes
    // panel. Null when the sidebar is folded or the room is not there.
    function dockWidth() {
        var side = $('#right-sidebar');
        if (!side) return null;
        var w = side.getBoundingClientRect().width;
        return w >= 200 ? Math.min(334, Math.round(w) - 16) : null;
    }
    // The one spot the callout keeps for the whole tour (Matt, 2026-09-15:
    // "it needs to stay in the same spot at all times"): the sidebar home,
    // measured once when the tour first leaves the intro, then held. Only
    // when that spot would cover the control a step is showing does the
    // box slide along the same column - below the control, or above it -
    // and it comes back to the spot on the next step.
    function lockedBox(cw, ch, r, keep) {
        if (!S.home) {
            var h = homeBox(cw, ch);
            // No spot because the right sidebar is folded away (the person
            // folded it mid-tour): open it - the spot is the rule.
            if (!h && sidebarCollapsed('right')) { ensureCalloutHome(); h = homeBox(cw, ch); }
            if (!h) return null;
            S.home = { x: h.x, y: h.y };
        }
        var box = { x: S.home.x, y: S.home.y, p: null };
        var blockers = (keep || []).slice();
        if (r) blockers.push(r);
        var inWay = blockers.filter(function (b) { return hits(box, cw, ch, b, 8); });
        if (!inWay.length) { box.clear = true; return box; }
        var side = $('#right-sidebar');
        var sr = side ? side.getBoundingClientRect() : { top: 12, bottom: window.innerHeight - 12 };
        var notes = $('#notes-panel');
        var floor = (notes ? notes.getBoundingClientRect().top : sr.bottom) - 10;
        var below = Math.max.apply(null, inWay.map(function (b) { return b.bottom; })) + 12;
        var above = Math.min.apply(null, inWay.map(function (b) { return b.top; })) - ch - 12;
        var tryY = function (y) {
            if (y < sr.top + 8 || y + ch > floor) return null;
            var cand = { x: box.x, y: y, p: null };
            return blockers.some(function (b) { return hits(cand, cw, ch, b, 8); }) ? null : cand;
        };
        var slid = tryY(below) || tryY(above);
        if (slid) { slid.clear = true; return slid; }
        box.clear = false;
        return box;
    }
    function homeBox(cw, ch) {
        var side = $('#right-sidebar');
        if (!side) return null;
        var sr = side.getBoundingClientRect();
        if (sr.width < 200 || sr.height < 200) return null;
        var x = Math.max(12, Math.min(sr.left + (sr.width - cw) / 2, window.innerWidth - cw - 12));
        // First choice: the room under the canvas list, above BEACHES - the
        // sidebar's open middle on a show with a few screens. Second: under
        // Save as Preset, above Notes, on a tall window.
        var list = $('#layers-list'), beaches = $('#beaches-panel');
        if (list && beaches) {
            // The list box stretches to fill the panel; its last card is
            // where the content actually ends.
            var lastCard = list.lastElementChild;
            var lt = (lastCard ? lastCard.getBoundingClientRect().bottom : list.getBoundingClientRect().top) + 14;
            var lf = beaches.getBoundingClientRect().top - 10;
            if (lf - lt >= ch) return { x: x, y: lt, p: null };
        }
        var below = $('#btn-save-preset') || $('#btn-add-canvas') || beaches;
        var notes = $('#notes-panel');
        var top = below ? below.getBoundingClientRect().bottom + 14 : sr.top + 12;
        var floor = notes ? notes.getBoundingClientRect().top - 10 : sr.bottom - 12;
        if (floor - top >= ch) return { x: x, y: top, p: null };
        // A short window (1366 x 768 is a laptop) has neither room: the
        // spot is still in this column, under the canvas list and over
        // whatever the sidebar has below - the callout is an overlay, and
        // lockedBox slides it off any control a step rings there. Never
        // null for a sidebar that is open: null sends the box to the
        // middle of the window, and the spot is the rule.
        var lt2 = list && list.lastElementChild ? list.lastElementChild.getBoundingClientRect().bottom + 14 : sr.top + 12;
        var y = Math.min(lt2, sr.bottom - ch - 12);
        return { x: x, y: Math.max(sr.top + 8, y), p: null };
    }
    function layoutFor(placement, r, cw, ch) {
        var gap = 18, vw = window.innerWidth, vh = window.innerHeight;
        var x, y;
        if (placement === 'right') { x = r.right + gap; y = r.top; }
        else if (placement === 'left') { x = r.left - cw - gap; y = r.top; }
        else if (placement === 'top') { x = r.left + r.width / 2 - cw / 2; y = r.top - ch - gap; }
        else { x = r.left + r.width / 2 - cw / 2; y = r.bottom + gap; }
        x = Math.max(12, Math.min(x, vw - cw - 12));
        y = Math.max(12, Math.min(y, vh - ch - 12));
        return { x: x, y: y, p: placement };
    }
    function hits(box, cw, ch, r, pad) {
        if (!r) return false;
        pad = pad || 0;
        return !(box.x + cw < r.left - pad || box.x > r.right + pad
            || box.y + ch < r.top - pad || box.y > r.bottom + pad);
    }
    function pointRect(p, pad) { return { left: p.x - pad, right: p.x + pad, top: p.y - pad, bottom: p.y + pad }; }

    // Everything the callout must keep clear of: the cursor's destination
    // (`avoid`, a client point) and every control the step declares in its
    // `avoid` list (selectors or points) - an act that types into two
    // fields visits both, and the callout must cover neither.
    function avoidRects(step, avoid) {
        var out = [];
        if (avoid) out.push(pointRect(avoid, 24));
        ((step && step.avoid) || []).forEach(function (a) {
            // A function computes its point or element at placement time
            // (a cabinet's client point depends on the zoom of the moment).
            if (typeof a === 'function') { try { a = a(); } catch (e) { a = null; } }
            var el = typeof a === 'string' ? $(a) : a;
            if (el && el.nodeType === 1) {
                var rr = el.getBoundingClientRect();
                if (rr.width || rr.height) out.push(rr);
            } else if (el && typeof el.x === 'number') {
                out.push(pointRect(el, 24));
            }
        });
        return out;
    }

    // Place the callout beside the spotlight, clear of every avoid rect.
    // The preferred side is tried first, then the opposite side, then the
    // rest; when nothing is clear the callout goes to the corner farthest
    // from the cursor's destination.
    // The callout is placed ONCE per step, before the cursor moves, and holds
    // still through the act: room for the result line that lands when the
    // act is done is reserved now, so the box grows in place instead of
    // being re-placed (a re-placement after every action sent it to the far
    // corner - Matt, 2026-09-14: "too much jumping after an action is done").
    var RESULT_RESERVE = 48;
    function resultEmpty() {
        var box = els && els.callout.querySelector('.qs-result');
        return !box || !box.textContent;
    }
    // `dry` computes the box and returns it without moving the callout;
    // the box carries `clear` - whether it sits clear of the ring and every
    // avoid rect - so a caller can decline to move when nothing better
    // exists (a wall that fills the screen leaves no clear corner).
    function place(step, avoid, dry) {
        var call = els.callout;
        var r = spotRect;
        // Docked in the sidebar the callout takes the sidebar's width, so
        // it never overhangs the wall; beside a control it has its own.
        var dockW = dockWidth();
        call.style.width = dockW ? dockW + 'px' : '';
        var cw = call.offsetWidth || 334, ch = call.offsetHeight || 170;
        if (step && step.act && resultEmpty()) ch += RESULT_RESERVE;
        var vw = window.innerWidth, vh = window.innerHeight;
        var arrow = call.querySelector('.qs-arrow');
        if (arrow) arrow.style.display = 'none';
        var keep = avoidRects(step, avoid);
        var clear = function (b) {
            return !keep.some(function (ar) { return hits(b, cw, ch, ar, 8); });
        };
        var corner = function (ax, ay) {
            return { x: ax < vw / 2 ? vw - cw - 12 : 12, y: ay < vh / 2 ? vh - ch - 12 : 12, p: null };
        };
        // The locked spot is measured once, for the box of its first step;
        // a taller step held there ran off the bottom of a short window
        // and took Next with it (1.6.0: the start page step on a 720 px
        // window). The box keeps the spot's column and rises only as far
        // as the window needs.
        var inWindow = function (b) {
            var y = Math.max(12, Math.min(b.y, vh - ch - 12));
            if (y === b.y) return b;
            var moved = { x: b.x, y: y, p: b.p };
            moved.clear = clear(moved) && !(r && hits(moved, cw, ch, r, 8));
            return moved;
        };
        var box;
        if (!r || step.center) {
            // The intro sits in the middle of the window; the first Next
            // moves the callout to its locked spot and it stays there. A
            // later step with nothing to ring yet (a control that appears
            // after its first click, the outro) uses the locked spot too.
            box = S.idx > 0 ? lockedBox(cw, ch, null, keep) : null;
            if (box) box = inWindow(box);
            if (!box || !clear(box)) box = { x: (vw - cw) / 2, y: (vh - ch) / 2, p: null };
            if (!clear(box)) {
                var c0 = keep[0];
                box = corner((c0.left + c0.right) / 2, (c0.top + c0.bottom) / 2);
            }
            box.clear = clear(box);
            if (dry) return box;
        } else {
            // The locked spot, for every step after the intro. The arrow
            // stays off - the ring is what points. Beside-the-control
            // placement below is only for a window whose sidebar cannot
            // hold the box at all.
            var locked = lockedBox(cw, ch, r, keep);
            if (locked) {
                locked = inWindow(locked);
                if (dry) return locked;
                call.style.left = locked.x + 'px';
                call.style.top = locked.y + 'px';
                S.boxAt = { x: locked.x, y: locked.y };
                return;
            }
            call.style.width = '';
            cw = call.offsetWidth || 334;
            var pref = step.place || 'bottom';
            var opp = { bottom: 'top', top: 'bottom', left: 'right', right: 'left' }[pref];
            var order = [pref, opp].concat(['bottom', 'top', 'right', 'left'].filter(function (p) {
                return p !== pref && p !== opp;
            }));
            // An element a step spotted itself (a popover, a menu) is still
            // growing when it is first measured; keep well clear of it so
            // its final size never reaches the callout.
            var ringPad = S.spotEl ? 56 : 4;
            for (var i = 0; i < order.length; i++) {
                var b = layoutFor(order[i], r, cw, ch);
                if (hits(b, cw, ch, r, ringPad)) continue;
                if (!clear(b)) continue;
                box = b; break;
            }
            if (!box) {
                var ax = avoid ? avoid.x : r.left + r.width / 2;
                var ay = avoid ? avoid.y : r.top + r.height / 2;
                box = corner(ax, ay);
                if (!clear(box)) box = corner(vw - ax, vh - ay);
                box.clear = clear(box) && !hits(box, cw, ch, r, 4);
            } else {
                box.clear = true;
            }
            if (dry) return box;
            if (arrow && box.p) {
                var p = box.p, x = box.x, y = box.y;
                arrow.style.display = 'block';
                arrow.style.borderTop = ''; arrow.style.borderLeft = ''; arrow.style.borderRight = ''; arrow.style.borderBottom = '';
                if (p === 'right') { arrow.style.left = '-8px'; arrow.style.top = Math.max(14, Math.min(r.top + r.height / 2 - y - 7, ch - 28)) + 'px'; arrow.style.borderRight = 'none'; arrow.style.borderBottom = 'none'; }
                else if (p === 'left') { arrow.style.left = (cw - 7) + 'px'; arrow.style.top = Math.max(14, Math.min(r.top + r.height / 2 - y - 7, ch - 28)) + 'px'; arrow.style.borderLeft = 'none'; arrow.style.borderTop = 'none'; }
                else if (p === 'top') { arrow.style.top = (ch - 7) + 'px'; arrow.style.left = Math.max(14, Math.min(r.left + r.width / 2 - x - 7, cw - 28)) + 'px'; arrow.style.borderLeft = 'none'; arrow.style.borderTop = 'none'; }
                else { arrow.style.top = '-8px'; arrow.style.left = Math.max(14, Math.min(r.left + r.width / 2 - x - 7, cw - 28)) + 'px'; arrow.style.borderRight = 'none'; arrow.style.borderBottom = 'none'; }
            }
        }
        // A trace hook for the placement tests: who moved the callout, where.
        if (window.__qsTrace) {
            var rr = function (q) { return q ? [q.left, q.top, q.right, q.bottom].map(Math.round) : null; };
            window.__qsTrace.push({ step: S.idx, x: Math.round(box.x), y: Math.round(box.y), clear: !!box.clear,
                                    spot: rr(r), avoid: keep.map(rr), size: [cw, ch],
                                    by: String(new Error().stack || '').split('\n').slice(2, 5).join(' < ') });
        }
        S.boxAt = { x: box.x, y: box.y };
        call.style.left = box.x + 'px';
        call.style.top = box.y + 'px';
    }
    // Where the callout IS or is on its way to: the box slides over 0.22 s,
    // and a check that read its rectangle mid-slide saw it covering things
    // it had already left.
    function calloutBox() {
        var c = els.callout.getBoundingClientRect();
        if (!S.boxAt) return c;
        return { left: S.boxAt.x, top: S.boxAt.y, right: S.boxAt.x + c.width, bottom: S.boxAt.y + c.height,
                 width: c.width, height: c.height };
    }
    // Ring the step's own target (or `el`) and place the callout beside it.
    // An element a step spotted itself (a popover, a menu, a dialog) stays
    // the ring for the rest of the step while it is on screen, measured
    // fresh each time - a popover grows after its first paint.
    function respot(el, avoid) {
        var step = S.list[S.idx];
        if (!step) return;
        var keep = S.spotEl && S.spotEl.isConnected && rectOf(S.spotEl) ? S.spotEl : null;
        var target = el || keep || stepTargetEl(step);
        setSpot(step.center ? null : (el || keep ? rectOf(target) : stepRect(step, target)));
        // Whether the callout was placed beside a real target: a step whose
        // target only exists after its first click (a view tab, a menu)
        // starts centred and earns ONE move beside the target when it appears.
        S.placedWithTarget = !!spotRect;
        place(step, avoid);
    }
    // The callout must never cover the point the cursor is heading for. It
    // moves only when that point is actually under the box - a near miss
    // is not interference, and every move is a jump the person watches.
    function keepClear(p) {
        if (!els || !p) return;
        var c = calloutBox();
        var pad = 2;
        if (p.x >= c.left - pad && p.x <= c.right + pad && p.y >= c.top - pad && p.y <= c.bottom + pad) {
            place(S.list[S.idx] || {}, p);
        }
    }
    // After an act (or when a step spots a popover, a menu or a dialog it
    // opened): ring the current target, measured fresh, but leave the
    // callout where it is unless it now covers the ring or has grown off
    // the screen.
    function settle() {
        var step = S.list[S.idx];
        if (!step || !els) return;
        var keep = S.spotEl && S.spotEl.isConnected && rectOf(S.spotEl) ? S.spotEl : null;
        var target = keep || stepTargetEl(step);
        var r = step.center ? null : (keep ? rectOf(target) : stepRect(step, target));
        setSpot(r);
        if (!S.placedWithTarget && r) {
            S.placedWithTarget = true;
            place(step);
            return;
        }
        var c = calloutBox();
        var off = c.right > window.innerWidth - 12 || c.bottom > window.innerHeight - 12;
        if (!off && !(r && hits({ x: c.left, y: c.top }, c.width, c.height, r, 4))) return;
        // Move only to a spot that is actually clear, and only when it is a
        // real move; when none exists the box stays put rather than trading
        // one overlap for another, and a nudge of a few pixels is not worth
        // the slide.
        var better = place(step, null, true);
        // A box past the window's edge always moves (its Next may be out of
        // reach); a box over the ring moves only to a clear spot, and only
        // for a real move.
        var inside = better.x + c.width <= window.innerWidth - 12 + 0.5 && better.y + c.height <= window.innerHeight - 12 + 0.5;
        if (off ? inside && (better.x !== c.left || better.y !== c.top)
                : better.clear && (Math.abs(better.x - c.left) > 40 || Math.abs(better.y - c.top) > 40)) place(step);
    }
    // A window resize (the app fires one after a view switch re-lays the
    // canvas out) re-measures the ring but moves the callout only if it
    // must - the same rule as after an act.
    function reposition() {
        if (!els || els.callout.style.display === 'none' || S.idx < 0) return;
        S.home = null;   // the sidebar moved with the window; measure the spot again
        settle();
    }

    // ── events the app's handlers understand ─────────────────────────────
    function mouse(type, el, x, y, init) {
        init = init || {};
        var ev = new MouseEvent(type, {
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y, screenX: x, screenY: y,
            button: init.button || 0,
            buttons: init.buttons != null ? init.buttons : (type === 'mousedown' ? 1 : 0),
            altKey: !!init.altKey, shiftKey: !!init.shiftKey,
            metaKey: !!init.metaKey, ctrlKey: !!init.ctrlKey
        });
        el.dispatchEvent(ev);
        return ev;
    }
    var KEY_CODES = { Escape: 'Escape', Enter: 'Enter', Tab: 'Tab' };
    function keyEvent(type, el, key, init) {
        init = init || {};
        var ev = new KeyboardEvent(type, {
            bubbles: true, cancelable: true, key: key, code: KEY_CODES[key] || key,
            altKey: !!init.altKey, shiftKey: !!init.shiftKey, metaKey: !!init.metaKey, ctrlKey: !!init.ctrlKey
        });
        (el || document).dispatchEvent(ev);
        return ev;
    }
    function centerOf(el) {
        var r = el.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }
    function describe(target) {
        if (!target) return 'nothing';
        if (typeof target === 'string') return target;
        if (target.nodeType === 1) return '<' + target.tagName.toLowerCase() + '>';
        return JSON.stringify(target);
    }
    function resolve(target) {
        if (!target) return null;
        if (typeof target === 'string') target = $(target);
        if (!target) return null;
        if (target.nodeType === 1) {
            try { target.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) {}
            // The element's own centre, or nothing: an element with no
            // size (folded away, hidden) is reported by moveTo, never
            // stood in for by an ancestor that happens to have one - a
            // drag begun from the wrong element is worse than no drag.
            var rr = target.getBoundingClientRect();
            var c = centerOf(target);
            return { el: target, x: c.x, y: c.y, empty: rr.width === 0 && rr.height === 0 };
        }
        if (typeof target.x === 'number' && typeof target.y === 'number') {
            return { el: target.el || null, x: target.x, y: target.y, worldX: target.worldX, worldY: target.worldY };
        }
        return null;
    }
    function setValue(el, v) {
        el.value = v;
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    // What every gesture does before it aims: a tray element is revealed
    // (revealInTray), a canvas point is guarded (guardCanvasPoint), and a
    // point that knows how to re-measure itself (`again`) is measured now.
    // A target that is not on the page yet, or not laid out yet, is waited
    // for (up to 2.5 s) before the gesture gives up: on a slow machine the
    // tray or a sheet is still being drawn when the step reaches for it.
    // Behind the shade (What's New's fallback, Go to) every pace is zero,
    // and CI's slower runners failed "<input> has no size" and "moveTo:
    // nothing at [data-lrd-field^=power-soca-length-1-]" there - the steps
    // after it then found no distro (2026-10-21).
    // An element the tray rebuilt away under the step (a save restates the
    // tray) is found again by the name it was drawn with - its field, its
    // tray tile, its popover, its id: a detached copy never gains a size,
    // so the gesture would wait on it for nothing. ("The snake's home run"
    // hovered its length field, and "Add a breakout box" moved to the new
    // box's header, just after a save redrew the tray.)
    var RELIVE_ATTRS = ['data-lrd-field', 'data-hwdock', 'data-hwpop', 'data-lrd-distro', 'data-lrd-service'];
    function relive(el) {
        if (!el || el.nodeType !== 1 || el.isConnected) return el;
        var esc = function (v) { return window.CSS && CSS.escape ? CSS.escape(v) : String(v).replace(/"/g, '\\"'); };
        for (var i = 0; i < RELIVE_ATTRS.length; i++) {
            var v = el.getAttribute(RELIVE_ATTRS[i]);
            if (v) return $('[' + RELIVE_ATTRS[i] + '="' + esc(v) + '"]') || el;
        }
        if (el.id) return document.getElementById(el.id) || el;
        return el;
    }
    function prepare(target) {
        if (!target) return Promise.resolve(null);
        if (typeof target.again === 'function') target = target.again();
        target = relive(target);
        var find = function () {
            return typeof target === 'string' ? $(target) : (target.nodeType === 1 ? target : null);
        };
        var appear = (typeof target === 'string' && !$(target)) ? T.wait(find, 2500) : Promise.resolve(find());
        return appear.then(function (el) {
            var chain;
            if (el && dock() && dock().contains(el)) chain = revealInTray(el);
            else {
                // A sidebar element: the panel opened and every fold above it
                // undone now - a fold the person made while watching cannot
                // send the hand to a field that has no size.
                if (el) revealInSidebar(el);
                chain = Promise.resolve();
            }
            return chain;
        }).then(function () {
            var p = resolve(target);
            if (p && p.el && p.empty) {
                return T.wait(function () {
                    target = relive(target);
                    var q = resolve(target);
                    return q && !q.empty ? q : null;
                }, 2500).then(function (q) {
                    if (!q) throw new Error(describe(target) + ' has no size');
                    return guardCanvasPoint(q);
                });
            }
            return guardCanvasPoint(p);
        });
    }

    // ── the toolkit a step's act(t) receives ─────────────────────────────
    var T = {
        pause: function (n) { return sleep(ms(n)); },
        // Poll a predicate until it returns something truthy (that value is
        // resolved) or the timeout passes (null). The timeout is real time
        // at every speed. A wait that runs out is not the step's verdict:
        // the step's check is polled after the act (pollCheck).
        wait: function (fn, timeout) {
            var limit = timeout == null ? 4000 : timeout;
            var t0 = Date.now();
            return new Promise(function (res) {
                (function poll() {
                    var v = null;
                    try { v = fn(); } catch (e) { v = null; }
                    if (v) return res(v);
                    if (Date.now() - t0 > limit) return res(null);
                    setTimeout(poll, 40);
                })();
            });
        },
        say: function (note) { showResult(note, null, 'wait'); },
        // Ring an element the act opened (a popover, a sheet, a dialog).
        // The ring waits a beat for the element to finish laying out - a
        // dialog measured on its first paint is a fraction of its size, and
        // a callout placed clear of that fraction is under the dialog a
        // moment later. Resolves once the ring is set; chain the next
        // gesture on it.
        spot: function (target) {
            var el = typeof target === 'string' ? $(target) : target;
            if (!el) return Promise.resolve();
            S.spotEl = el;
            // Wait until the element's rectangle has held still across two
            // measurements (a dialog fills in its sections after a fetch;
            // a popover grows past its first paint), up to about a second.
            // The step's avoid list (the controls the act will visit inside
            // the element) must have held still too, or the box is placed
            // clear of where a control was, not where it ends up.
            var step = S.list[S.idx];
            var last = null, tries = 0;
            return new Promise(function (res) {
                (function tick() {
                    var rects = [rectOf(el)].concat(avoidRects(step, null));
                    var key = rects.map(function (r) {
                        return r ? [r.left, r.top, r.width, r.height].map(Math.round).join(',') : '';
                    }).join('|');
                    if (key === last || ++tries > 8) return res();
                    last = key;
                    setTimeout(tick, ms(120));
                })();
            }).then(function () { settle(); });
        },
        mem: {},
        moveTo: function (target, o) {
            o = o || {};
            return prepare(target).then(function (p) {
                if (!p) throw new Error('moveTo: nothing at ' + describe(target));
                keepClear(p);
                showCursor();
                badge(o.badge || '');
                return animateTo(p.x, p.y, null, o.speed).then(function () { return p; });
            });
        },
        // Open the tray around an element before a gesture on it: the tray
        // expanded and tall enough, every fold above it undone, the element
        // scrolled into view. Every hover does this itself; a step that
        // reads a chip before touching it can call it first.
        reveal: function (target) {
            var el = typeof target === 'string' ? $(target) : target;
            return el ? revealInTray(el) : Promise.resolve(null);
        },
        // Arrive on the control and hold there a beat (badge shown) before
        // the press - the hover every click, select, type and drag opens
        // with. `o.hover` overrides the beat.
        hover: function (target, o) {
            o = o || {};
            return T.moveTo(target, o).then(function (p) {
                return T.pause(o.hover == null ? PACE.hover : o.hover).then(function () { return p; });
            });
        },
        // A real click: the hover, the press (mousedown/mouseup at the
        // point, so the app's mousedown-driven handlers see the gesture),
        // the click, then the rest before the next gesture. `init` carries
        // modifiers; with a modifier the click is dispatched as an event so
        // the handler reads the keys. `o.rest` overrides the rest.
        click: function (target, o) {
            o = o || {};
            return T.hover(target, o).then(function (p) {
                var el = live(p.el) || document.elementFromPoint(p.x, p.y);
                if (!el) throw new Error('click: nothing at ' + describe(target));
                press(true);
                mouse('mousedown', el, p.x, p.y, o.init);
                return T.pause(70).then(function () {
                    mouse('mouseup', el, p.x, p.y, Object.assign({}, o.init || {}, { buttons: 0 }));
                    ripple(p.x, p.y);
                    press(false);
                    if (!o.noClick) {
                        var m = o.init || {};
                        if (m.shiftKey || m.metaKey || m.altKey || m.ctrlKey) mouse('click', el, p.x, p.y, m);
                        else el.click();
                    }
                    var tab = el.matches && el.matches('.view-tab[data-mode]');
                    return T.pause(tab ? PACE.view : (o.rest == null ? PACE.rest : o.rest)).then(function () {
                        if (tab) settle();
                        return el;
                    });
                });
            });
        },
        // Focus, clear, type the characters one by one so the value visibly
        // builds, then commit with `change` (and Enter first when asked).
        type: function (target, text, o) {
            o = o || {};
            return T.hover(target).then(function (p) {
                var el = live(p.el);
                if (!el) throw new Error('type: nothing at ' + describe(target));
                ripple(p.x, p.y);
                el.focus();
                if (typeof el.select === 'function') el.select();
                setValue(el, '');
                var chars = String(text).split('');
                var i = 0;
                var typed = '';
                // Each key lands in the live field, carrying everything typed
                // so far: a rebuild between keys hands the field to its
                // successor (app-naming.js _preserveEditorFocus carries the
                // draft and the focus across), and the hand follows it.
                return new Promise(function (res) {
                    (function next() {
                        if (i >= chars.length) return res();
                        el = live(el);
                        typed += chars[i++];
                        setValue(el, typed);
                        setTimeout(next, ms(PACE.key));
                    })();
                }).then(function () {
                    return T.pause(PACE.typed);
                }).then(function () {
                    el = live(el);
                    if (o.enter) {
                        keyEvent('keydown', el, 'Enter');
                        keyEvent('keyup', el, 'Enter');
                    }
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return T.pause(PACE.rest);
                }).then(function () { return el; });
            });
        },
        select: function (target, value) {
            return T.hover(target).then(function (p) {
                var el = live(p.el);
                if (!el) throw new Error('select: nothing at ' + describe(target));
                ripple(p.x, p.y);
                el.focus();
                el.value = value;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return T.pause(PACE.rest).then(function () { return el; });
            });
        },
        // The tray's drag engine is mousedown on the chip, then mousemove /
        // mouseup on the DOCUMENT (app-dock.js _dockArmDrag): one move past
        // the 4 px threshold, then the path, then the release at the target
        // - so the app's own ghost chip, pending bracket and pill appear.
        drag: function (from, to, o) {
            o = o || {};
            if (!to) return Promise.reject(new Error('drag: no destination'));
            var dest = null;
            return T.hover(from, o).then(function (p) {
                var el = live(p.el);
                if (!el) throw new Error('drag: nothing at ' + describe(from));
                // The destination is measured AFTER the source is revealed:
                // opening the tray for the chip moves the canvas (and the
                // tray's own header) under the point.
                return prepare(to).then(function (d) {
                    dest = d;
                    if (!dest) throw new Error('drag: no destination');
                    return p;
                });
            }).then(function (p) {
                var el = live(p.el);
                press(true);
                mouse('mousedown', el, p.x, p.y, { buttons: 1 });
                return T.pause(PACE.dragPress).then(function () {
                    mouse('mousemove', document, p.x + 6, p.y + 6, { buttons: 1 });
                    keepClear(dest);
                    return animateTo(dest.x, dest.y, function (x, y) {
                        mouse('mousemove', document, x, y, { buttons: 1 });
                    }, PACE.dragTravel);
                }).then(function () {
                    // Over the target, held: the app's pending bracket and
                    // pill are what the person reads before the release.
                    mouse('mousemove', document, dest.x, dest.y, { buttons: 1 });
                    return T.pause(o.dropHover == null ? PACE.dragHover : o.dropHover);
                }).then(function () {
                    mouse('mouseup', document, dest.x, dest.y, { buttons: 0 });
                    press(false);
                    ripple(dest.x, dest.y);
                    return T.pause(PACE.dragRest);
                });
            });
        },
        // The app's own menu at the point, with the ghost parked there: the
        // hover, the press, then the menu held open long enough to read
        // before pickMenu moves onto an item.
        rightClick: function (point, o) {
            o = o || {};
            return T.hover(point, { badge: 'Right-click' }).then(function (p) {
                press(true);
                ripple(p.x, p.y);
                A().showContextMenu(p.x, p.y);
                press(false);
                return T.pause(120).then(function () {
                    badge('');
                    var m = $('#context-menu');
                    if (m && m.style.display === 'block') { S.spotEl = m; settle(); }
                    return T.pause(PACE.menuHold).then(function () { return m; });
                });
            });
        },
        pickMenu: function (action) {
            return T.wait(function () {
                var m = $('#context-menu');
                var item = m && m.querySelector('[data-action="' + action + '"]');
                return (m && m.style.display === 'block' && item && item.style.display !== 'none') ? item : null;
            }, 1500).then(function (item) {
                if (!item) throw new Error('pickMenu: ' + action + ' is not on the menu');
                return T.hover(item, { speed: PACE.menuTravel, hover: PACE.menuHover }).then(function (p) {
                    ripple(p.x, p.y);
                    item.click();
                    return T.pause(PACE.rest);
                });
            });
        },
        key: function (k, init, el) {
            keyEvent('keydown', el || document.activeElement || document, k, init);
            keyEvent('keyup', el || document.activeElement || document, k, init);
        },
        // Canvas gestures: the renderer listens for mousedown/mousemove on
        // the canvas and mouseup on the window (canvas.js setupEventListeners).
        canvasDown: function (p, init) { mouse('mousedown', R().canvas, p.x, p.y, Object.assign({ buttons: 1 }, init || {})); },
        canvasMove: function (p, init) { mouse('mousemove', R().canvas, p.x, p.y, Object.assign({ buttons: 1 }, init || {})); },
        canvasUp: function (p, init) { mouse('mouseup', R().canvas, p.x, p.y, Object.assign({ buttons: 0 }, init || {})); },
        // Travel while pressed at a drag's pace (or `pxPerSec`), dispatching
        // a canvas mousemove per frame.
        canvasGlide: function (to, init, pxPerSec) {
            keepClear(to);
            return animateTo(to.x, to.y, function (x, y) {
                mouse('mousemove', R().canvas, x, y, Object.assign({ buttons: 1 }, init || {}));
            }, pxPerSec || PACE.dragTravel);
        },
        // The pace table, for an act that dispatches its own press (a canvas
        // Alt+click, a Shift+drag) and keeps the same hover-press-rest shape.
        pace: PACE,
        // The client point of a cabinet on the wall - the same world-to-
        // client walk every canvas gesture makes (tests/test_hardware_dock.py
        // PANEL_POINT_JS). {port: n} the first cabinet of screen port n,
        // {circuit: i} the first cabinet of the i-th circuit, {index: i} the
        // i-th cabinet of the layer.
        // The point is INSIDE the visible #canvas-wrapper (with a margin) or
        // the walls are re-framed to the wrapper as it is now and the point
        // read again; a cabinet that still lies outside is a thrown Error.
        // {raw: true} skips that (a check that asks whether the wall IS in
        // view must not be answered by framing it). `again` re-measures the
        // same cabinet later - after a reveal has moved the canvas.
        cabinetPoint: function (layer, which) {
            var pt = cabinetPointRaw(layer, which);
            if (!pt || which.raw) return pt;
            if (!insideCanvas(pt, 24)) {
                canvasFresh();
                frameWalls();
                pt = cabinetPointRaw(layer, which);
                if (!pt || !insideCanvas(pt, 24)) {
                    throw new Error('the cabinet' + (pt ? ' at ' + Math.round(pt.x) + ',' + Math.round(pt.y) : '')
                        + ' is off the visible canvas');
                }
            }
            pt.again = function () { return T.cabinetPoint(layer, which); };
            return pt;
        },
        // Frame the wall (or several): zoom so the union spans ~60% of the
        // canvas width, then center it. fitToView frames the raster, and on
        // the scratch show's 5K raster the wall would be a patch in a corner.
        frame: function (layers) { frameLayers(layers); }
    };

    // The index of a wall's last cabinet - where a card or processor drop
    // lands every unplaced port (the drop grows to the cursor).
    function lastCabinet(layer) {
        var n = (layer && layer.panels || []).length;
        return n ? n - 1 : 0;
    }

    function cabinetPointRaw(layer, which) {
        var a = A(), r = R();
        if (!layer || !r) return null;
        // The LIVE layer: a commit mid-act (an override's PUT, a resize)
        // replaces the layer and its panel objects, and getPanelAt walks
        // the live project - a stale reference would miss by identity.
        layer = (a.project.layers || []).find(function (l) { return l.id === layer.id; }) || layer;
        var p = null;
        if (which.port !== undefined) {
            var items = a.calculatePortAssignments(layer);
            var it = items.find(function (i) { return i.port === which.port; });
            p = it && it.panel;
        } else if (which.circuit !== undefined) {
            var c = a.screenCircuits(layer)[which.circuit];
            // `mid`: the run's middle cabinet rather than its first, which
            // carries the label disc - a drop aimed at the disc's pixel
            // can miss the run on a dense wall.
            p = c && c.panels && c.panels[which.mid ? Math.floor(c.panels.length / 2) : 0];
        } else {
            p = (layer.panels || [])[which.index || 0];
        }
        if (!p) return null;
        var off1 = r.getLayerRenderOffset(layer);
        var off2 = r._layerCanvasOffset(layer);
        var wx = p.x + p.width / 2 + off1.dx + off2.wx;
        var wy = p.y + p.height / 2 + off1.dy + off2.wy;
        var rect = r.canvas.getBoundingClientRect();
        var pt = { x: rect.left + wx * r.zoom + r.panX, y: rect.top + wy * r.zoom + r.panY,
                   worldX: wx, worldY: wy, panel: p };
        try {
            var hit = r.getPanelAt(wx, wy);
            if (!hit || String(hit.layerId) !== String(layer.id) || hit.panel.id !== p.id) {
                console.warn('QuickStart: cabinetPoint round trip missed', which);
            }
        } catch (e) { /* the assert is advisory */ }
        return pt;
    }

    // Frames within the wrapper as it IS: the backing store is brought up
    // to the wrapper's size first, so a tray that just grew or a view that
    // just hid it cannot leave the wall centred on a stale height.
    function frameLayers(layers) {
        var a = A(), r = R();
        layers = (layers || []).filter(Boolean);
        if (!r || !layers.length) return;
        canvasFresh();
        var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        layers.forEach(function (l) {
            var b = r.getLayerBoundsInActiveView(l);
            var ws = r._layerCanvasOffset(l);
            x0 = Math.min(x0, b.x + ws.wx); y0 = Math.min(y0, b.y + ws.wy);
            x1 = Math.max(x1, b.x + ws.wx + b.width); y1 = Math.max(y1, b.y + ws.wy + b.height);
        });
        var w = Math.max(1, x1 - x0), h = Math.max(1, y1 - y0);
        r.zoom = Math.min(r.canvas.width * 0.6 / w, r.canvas.height * 0.62 / h);
        r.panX = r.canvas.width / 2 - (x0 + w / 2) * r.zoom;
        r.panY = r.canvas.height / 2 - (y0 + h / 2) * r.zoom;
        var zl = document.getElementById('zoom-level');
        if (zl && typeof r._zoomToPercent === 'function') zl.value = r._zoomToPercent(r.zoom) + '%';
        r.render();
    }
    function frameWalls() { frameLayers([wall(), wall2()]); }
    // Where a multi is dropped: the LAST circuit's middle cabinet, so the
    // span grows across the whole wall - when that cabinet can be brought
    // into the visible canvas; the first circuit's middle otherwise.
    function multiDropPoint() {
        var w = wall(), a = A();
        if (!w) return null;
        var last = Math.max(0, a.screenCircuits(w).length - 1);
        try { return T.cabinetPoint(w, { circuit: last, mid: true }); }
        catch (e) { return T.cabinetPoint(w, { circuit: 0, mid: true }); }
    }

    // ── the engine ───────────────────────────────────────────────────────
    var S = {
        name: null, list: [], idx: -1,
        running: false, pendingEnd: null,
        // The restore a guide's end is making, until it lands (show waits).
        ending: null,
        // The window keys held open through the step change under way
        // (sharedWindows), or null: set as Next or Back leaves a step,
        // cleared once the step entered has set itself up.
        keep: null,
        // Where the step on screen is: 'enter' (leaving the last, its
        // restore, its before), 'act', or 'settled'. The tests read it to
        // tell a window the act closed from one the change closed.
        phase: null,
        // Each step's UI at its entry (the view tab), beside S.snaps: Back
        // and the replay button put it back with the project.
        ui: [],
        snaps: [], saved: null, token: 0, visible: false, spotEl: null,
        // How the last Go to ahead landed: 'snapshot' (one restore of the
        // shipped entry snapshot) or 'apply' (the steps between were run).
        // On What's New, how the step on screen got its entry state.
        jumpedVia: null,
        // The step keys on screen, in order.
        keys: [],
        // What's New only: for each step, its index in the Advanced Guide
        // (whose entry snapshot it starts from), and the Advanced step
        // whose entry state the show holds right now (null: unknown).
        entries: null, entryAt: null
    };

    // Next, Back and the replay button are disabled while the step runs;
    // the input shield swallows the click anyway (onShield).
    function setState(v) {
        if (!els) return;
        els.callout.setAttribute('data-qs-state', v);
        ['#qs-next', '#qs-back', '#qs-replay'].forEach(function (sel) {
            var b = els.callout.querySelector(sel);
            if (b) b.disabled = v === 'running';
        });
    }
    function showResult(note, err, kind) {
        if (!els) return;
        var box = els.callout.querySelector('.qs-result');
        if (!box) return;
        box.classList.remove('qs-result-fail', 'qs-result-wait');
        if (kind === 'wait') { box.classList.add('qs-result-wait'); box.textContent = note || ''; return; }
        if (note) { box.textContent = note; }
        else {
            box.classList.add('qs-result-fail');
            box.textContent = 'This step did not take.' + (err ? ' (' + (err.message || err) + ')' : '');
        }
    }

    function render() {
        var step = S.list[S.idx];
        var last = S.idx === S.list.length - 1;
        var offerFull = last && S.name === 'quick';
        els.callout.innerHTML =
            '<div class="qs-arrow"></div>'
            + '<h3>' + step.title + '</h3>'
            + '<p>' + step.body + '</p>'
            + '<div class="qs-result"></div>'
            + '<div class="qs-prog"><span>Step ' + (S.idx + 1) + ' of ' + S.list.length + '</span>'
            + '<span class="qs-hint">Enter = Next</span>'
            + '<label class="qs-jump">Go to <input id="qs-jump" type="number" min="1" max="' + S.list.length
            + '" inputmode="numeric" title="Type a step number and press Enter"></label></div>'
            + (offerFull ? '<button class="qs-cta" id="qs-full">Take the full walkthrough &rsaquo;</button>' : '')
            + '<div class="qs-row">'
            + '  <label class="qs-chk"><input type="checkbox" id="qs-nolaunch"' + (disabled() ? ' checked' : '') + '> Don&rsquo;t show on startup</label>'
            + '  <div class="qs-btns">'
            + '    <button class="qs-skip" id="qs-skip">Skip</button>'
            + (S.idx > 0 ? '    <button class="qs-back" id="qs-back">Back</button>' : '')
            + (step.act ? '    <button class="qs-replay" id="qs-replay" title="Play this step again">&#8635;</button>' : '')
            + '    <button class="qs-next" id="qs-next">' + (last ? 'Done' : 'Next') + '</button>'
            + '  </div>'
            + '</div>';
        els.callout.querySelector('#qs-skip').onclick = function () { end(); };
        els.callout.querySelector('#qs-next').onclick = function () {
            // A step that is still running takes no Next: a second click
            // waits for nothing and skips nothing.
            if (S.running) return;
            last ? end() : go(S.idx + 1, { carry: true });
        };
        var back = els.callout.querySelector('#qs-back');
        if (back) back.onclick = function () { if (!S.running) goBack(); };
        var rep = els.callout.querySelector('#qs-replay');
        if (rep) rep.onclick = function () { if (!S.running) replay(); };
        els.callout.querySelector('#qs-nolaunch').onchange = function () { setDisabled(this.checked); };
        var full = els.callout.querySelector('#qs-full');
        if (full) full.onclick = function () { end().then(function () { show('advanced'); }); };
        var jump = els.callout.querySelector('#qs-jump');
        if (jump) jump.onchange = function () { jumpTo(Number(jump.value)); };
        setState(step.act ? 'pending' : 'idle');
        respot();
    }

    // ── shipped snapshots: Go to ahead in one restore ────────────────────
    // src/static/data/tour_snapshots.json (scripts/build_tour_snapshots.py)
    // holds every step's ENTRY snapshot - the scratch show as the step finds
    // it - for each tour, so a Go to ahead is one restore, exactly like Back,
    // and never a run of the steps between (Matt, 2026-09-16: "it needs to
    // just jump straight to it and when it gets there all steps before it
    // have been done ... an instant skip to step, not any waiting"). The
    // file is fetched once, on the first jump ahead, and kept in memory.
    // A tour whose steps changed since the file was built must never land
    // on a stale show: the file carries each tour's signature (see
    // signature()) and is only used when it matches; otherwise the steps
    // between are applied behind the shade (applyAhead).
    var SNAPSHOTS_URL = '/static/data/tour_snapshots.json';
    var fixture = null, fixtureLoad = null;
    function loadSnapshots() {
        if (fixture) return Promise.resolve(fixture);
        if (!fixtureLoad) {
            fixtureLoad = fetch(SNAPSHOTS_URL).then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) {
                    fixture = d && d.tours && typeof d.tours === 'object' ? d : null;
                    if (!fixture) fixtureLoad = null;
                    return fixture;
                })
                .catch(function () { fixtureLoad = null; return null; });
        }
        return fixtureLoad;
    }
    // FNV-1a over the string, as eight hex digits - small, stable across
    // engines, and the same arithmetic tests/test_tour_snapshots.py can redo.
    function fnv1a(str) {
        var h = 0x811c9dc5;
        for (var i = 0; i < str.length; i++) {
            h ^= str.charCodeAt(i);
            h = Math.imul(h, 0x01000193) >>> 0;
        }
        return ('0000000' + h.toString(16)).slice(-8);
    }
    function appVersion() {
        var m = /\bv(\d+(?:\.\d+)+)/.exec(document.title || '');
        return m ? m[1] : '?';
    }
    // 'v<app version>:<step count>:<fnv1a of "key|title" per step>' - a
    // step added, removed, renamed or reordered, or a new app version,
    // gives a new signature and retires the shipped file for that tour.
    function signature(name) {
        var tour = TOURS[name];
        if (!tour) return null;
        var lines = tour.steps.map(function (k) { var s = STEPS[k]; return k + '|' + (s ? s.title : ''); });
        return 'v' + appVersion() + ':' + tour.steps.length + ':' + fnv1a(lines.join('\n'));
    }
    // The shipped entry snapshot of step k of the current tour, or null. An
    // entry is the project itself or an integer into the tour's `unique`
    // list (identical consecutive projects are stored once).
    function shippedSnapshot(t, k) {
        var e = t && Array.isArray(t.steps) ? t.steps[k] : null;
        if (typeof e === 'number') e = Array.isArray(t.unique) ? t.unique[e] : null;
        return e && typeof e === 'object' && Array.isArray(e.layers) ? e : null;
    }
    function shippedSnapshots(name, upTo) {
        return loadSnapshots().then(function (fx) {
            var t = fx && fx.tours ? fx.tours[name] : null;
            if (!t || t.signature !== signature(name)) return null;
            var out = [];
            for (var k = 0; k <= upTo; k++) {
                var s = shippedSnapshot(t, k);
                if (!s) return null;
                out.push(s);
            }
            return out;
        });
    }

    // Go straight to step n (1-based). Back is a restore of that step's
    // entry snapshot. Ahead is the same one restore when the shipped file
    // has this tour: the entry snapshots of every step up to n are adopted
    // as if the steps had been played (so Back from there works the same
    // way), the restore PUT re-seeds the server's id counters above
    // everything in the show, and step n's own before() and act then run
    // at normal pace. Without a matching file (a changed tour, a build
    // whose file was not regenerated, no network) the steps between are
    // APPLIED behind the shade instead - see applyAhead. `opts.apply`
    // forces that path; the snapshot builder drives it.
    function jumpTo(n, opts) {
        opts = opts || {};
        if (!S.visible || S.running) return Promise.resolve();
        n = Math.round(n);
        if (!(n >= 1 && n <= S.list.length) || n === S.idx + 1) return Promise.resolve();
        var i = n - 1;
        if (i < S.idx) return go(i, { restore: S.snaps[i] });
        // A What's New step enters from its own entry state (enterStep).
        if (S.entries) return go(i);
        if (opts.apply) { S.jumpedVia = 'apply'; return applyAhead(n, i); }
        var name = S.name, tokenAt = S.token;
        S.running = true;   // Next, Back, Enter and a second Go to wait for the file
        return shippedSnapshots(name, i).catch(function () { return null; }).then(function (snaps) {
            S.running = false;
            if (!S.visible || S.token !== tokenAt || S.name !== name) return;
            if (snaps) {
                for (var k = 0; k <= i; k++) S.snaps[k] = snaps[k];
                S.jumpedVia = 'snapshot';
                return go(i, { restore: snaps[i], frame: true });
            }
            S.jumpedVia = 'apply';
            return applyAhead(n, i);
        });
    }
    // The steps between here and step n are APPLIED, not played: the
    // window is shaded, every pace is zero (ms() is 0 while S.jumping), the
    // callout, ring and hand are hidden, and only the app's own responses
    // are waited for. A step that fails on the way ends the jump there,
    // with its failure shown, so the shade never hides a broken show.
    function applyAhead(n, i) {
        var from = S.idx + 1, total = i - from;
        S.jumping = true;
        S.fast = true;
        document.body.classList.add('qs-jumping');
        hideCursor();
        var chain = Promise.resolve();
        var stopped = false;
        for (var k = from; k < i; k++) {
            (function (k) {
                chain = chain.then(function () {
                    if (!S.visible || stopped) return;
                    fastBanner('Going to step ' + n, 'applying step ' + (k + 1) + ' of ' + S.list.length, (k - from) / Math.max(1, total));
                    return go(k).then(function () {
                        if (els && els.callout.getAttribute('data-qs-state') === 'failed') stopped = true;
                    });
                });
            })(k);
        }
        return chain.then(function () {
            S.jumping = false;
            S.fast = false;
            document.body.classList.remove('qs-jumping');
            fastBanner('');
            if (!S.visible) return;
            if (stopped) { settle(); return; }   // land on the step that failed, its result showing
            return go(i);
        });
    }
    function fastBanner(text, sub, frac) {
        if (!els) return;
        els.fast.innerHTML = '';
        if (text) {
            els.fast.appendChild(document.createTextNode(text));
            var s2 = document.createElement('div'); s2.className = 'qs-fast-sub'; s2.textContent = sub || '';
            var bar = document.createElement('div'); bar.className = 'qs-fast-bar';
            var fill = document.createElement('i'); fill.style.width = Math.round(Math.max(0, Math.min(1, frac || 0)) * 100) + '%';
            bar.appendChild(fill);
            els.fast.appendChild(s2); els.fast.appendChild(bar);
        }
        els.fast.style.display = text ? 'flex' : 'none';
    }

    // ── What's New: Advanced Guide steps on their own ────────────────────
    // A What's New step runs WITHOUT the steps before it, so it starts from
    // the Advanced Guide's entry snapshot of that step in the shipped file:
    // the show exactly as the guide hands it to the step, restored the way
    // Go to restores one. Without a matching file (a changed guide, a build
    // whose file was not regenerated, no network) the Advanced steps before
    // it are applied behind the shade instead (applyEntry), as Go to does.
    function enterStep(i) {
        var k = S.entries[i];
        return shippedSnapshots('advanced', k).catch(function () { return null; }).then(function (snaps) {
            if (snaps) {
                S.jumpedVia = 'snapshot';
                return restoreProject(snaps[k], 'Tutorial Step').then(function () { S.entryAt = k; });
            }
            S.jumpedVia = 'apply';
            return applyEntry(k);
        }).catch(function (e) {
            // The step still plays; if its entry state is not there its
            // check says so. The show's state is unknown from here on.
            S.entryAt = null;
            console.warn('QuickStart: entry state failed', e);
        });
    }
    // The Advanced Guide applied up to step k's entry: from where the show
    // already is when that is at or before k (the step before took), else
    // from a fresh scratch show. Every pace is zero and only the app's own
    // responses are waited for, as in applyAhead.
    function applyEntry(k) {
        var adv = TOURS.advanced.steps;
        var from = S.entryAt != null && S.entryAt <= k ? S.entryAt : null;
        // The steps applied behind the shade open and close their own
        // windows: nothing is held through them.
        S.keep = null;
        S.jumping = true;
        S.fast = true;
        document.body.classList.add('qs-jumping');
        hideCursor();
        var done = function () {
            S.jumping = false;
            S.fast = false;
            document.body.classList.remove('qs-jumping');
            fastBanner('');
        };
        var start = from == null
            ? buildScratch(TOURS.advanced.seed).then(function () { return 0; })
            : Promise.resolve(from);
        return start.then(function (j0) {
            var chain = Promise.resolve();
            for (var j = j0; j < k; j++) {
                (function (j) {
                    chain = chain.then(function () {
                        if (!S.visible) throw new Error('the guide was closed');
                        fastBanner('Getting the step ready', 'applying Advanced Guide step ' + (j + 1) + ' of ' + adv.length,
                                   (j - j0) / Math.max(1, k - j0));
                        return applyStep(STEPS[adv[j]]);
                    });
                })(j);
            }
            return chain;
        }).then(function () { done(); S.entryAt = k; },
                function (e) { done(); S.entryAt = null; throw e; });
    }
    // One step applied, unseen: before, the act, its check, after. A step
    // whose check returns no note stops the apply.
    function applyStep(step) {
        var leave = function () {
            passthrough(false);
            if (step.after) { try { step.after(null); } catch (e) { console.warn('QuickStart after()', e); } }
        };
        // From a known state and to a polled verdict, as a played step.
        resetModes();
        return appSettled().then(function () {
            if (step.before) return step.before();
        }).then(function () {
            ensureCalloutHome();
            revealStep(step);
            if (!step.act) return 'idle';
            T.mem = {};
            passthrough(true);
            var failed = null;
            return appSettled().then(function () { return actOf(step); }).catch(function (e) {
                failed = e;
            }).then(function () {
                return appSettled();
            }).then(function () {
                return pollCheck(step, T.mem, null);
            }).then(function (note) {
                if (!note && failed) throw failed;
                return note;
            });
        }).then(function (note) {
            leave();
            if (!note) throw new Error('"' + step.title + '" did not take');
        }, function (e) { leave(); throw e; });
    }

    // "1.5.2" / "v1.5" -> [1, 5, 2] / [1, 5]; null when unparseable.
    function versionParts(v) {
        var m = /^v?(\d+(?:\.\d+)*)/.exec(String(v == null ? '' : v).trim());
        return m ? m[1].split('.').map(Number) : null;
    }
    // Like a sort comparator; a missing part reads as 0 (1.5 = 1.5.0).
    function versionCmp(a, b) {
        var n = Math.max(a.length, b.length);
        for (var i = 0; i < n; i++) {
            var d = (a[i] || 0) - (b[i] || 0);
            if (d) return d;
        }
        return 0;
    }
    // The Advanced Guide's step keys, in guide order, whose `since` is
    // newer than `after` and not newer than `upTo` (null: no bound there).
    function newSteps(after, upTo) {
        var lo = after == null ? null : versionParts(after);
        var hi = upTo == null ? null : versionParts(upTo);
        if ((after != null && !lo) || (upTo != null && !hi)) return [];
        return TOURS.advanced.steps.filter(function (k, i, all) {
            var s = versionParts(STEPS[k] && STEPS[k].since);
            return !!s && all.indexOf(k) === i
                && (!lo || versionCmp(s, lo) > 0) && (!hi || versionCmp(s, hi) <= 0);
        });
    }
    // Run Advanced Guide steps on their own, in guide order: What's New.
    function startSteps(keys) {
        var adv = TOURS.advanced.steps;
        keys = keys || [];
        var picked = adv.filter(function (k, i) { return adv.indexOf(k) === i && keys.indexOf(k) >= 0; });
        if (!picked.length) return Promise.resolve();
        // Headed by the newest feature version among them: What's New in 1.6.
        var newest = picked.reduce(function (m, k) {
            var p = versionParts(STEPS[k].since);
            return p && (!m || versionCmp(p, m) > 0) ? p : m;
        }, null);
        return show('whatsNew', {
            title: 'What&rsquo;s New' + (newest && newest.length >= 2 ? ' in ' + newest[0] + '.' + newest[1] : ''),
            seed: TOURS.advanced.seed, steps: picked,
            entries: picked.map(function (k) { return adv.indexOf(k); })
        });
    }

    function leaveCurrent(next) {
        var step = S.idx >= 0 && S.idx < S.list.length ? S.list[S.idx] : null;
        if (step && step.after) { try { step.after(next); } catch (e) { console.warn('QuickStart after()', e); } }
    }

    // ── waiting on the app ───────────────────────────────────────────────
    // `p`, or `onLimit` (a value, or an Error to reject with) once `limit`
    // real milliseconds have passed.
    function withLimit(p, limit, onLimit) {
        var timer = null;
        var cap = new Promise(function (res, rej) {
            timer = setTimeout(function () { onLimit instanceof Error ? rej(onLimit) : res(onLimit); }, limit);
        });
        return Promise.race([Promise.resolve(p), cap]).then(function (v) { clearTimeout(timer); return v; },
                                                            function (e) { clearTimeout(timer); throw e; });
    }
    // Two frames, so what the app just drew is on the page - or 100 ms,
    // where frames are not running (a hidden window).
    function painted() {
        return withLimit(new Promise(function (res) {
            requestAnimationFrame(function () { requestAnimationFrame(function () { res(); }); });
        }), 100, null);
    }
    // Until the app has done what the step asked of it: a debounced undo
    // step landed, every screen PUT and restore PUT answered (their socket
    // echoes follow them), the pull sheet's queue drained, and a frame
    // drawn. Never longer than SETTLE_LIMIT.
    function appSettled() {
        var a = A();
        if (!a) return Promise.resolve();
        try { if (a._flushPendingSaveState) a._flushPendingSaveState(); } catch (e) {}
        var p = null;
        try { p = a._layerSavesSettled ? a._layerSavesSettled() : null; } catch (e) { p = null; }
        return withLimit(Promise.resolve(p).catch(function () {}), SETTLE_LIMIT, null).then(painted);
    }
    // The step's act, held to ACT_LIMIT: an act that never ends is a step
    // that failed, never a guide that hangs with the input shield up.
    function actOf(step) {
        return withLimit(Promise.resolve().then(function () { return step.act(T); }), ACT_LIMIT,
                         new Error('the step did not finish'));
    }
    // A step's check asked every CHECK_EVERY ms until it returns its note
    // or CHECK_LIMIT passes (null: the step did not take). Asked once was
    // asked too soon on a busy machine: the check that failed at the end
    // of the act passed a quarter second later (1.6.0 QA). Stops early when
    // the guide is ending (Skip or Escape while the step ran).
    function pollCheck(step, mem, token) {
        if (!step.check) return Promise.resolve('Done.');
        var t0 = Date.now();
        return new Promise(function (res) {
            (function poll() {
                var note = null, err = null;
                try { note = step.check(mem); } catch (e) { err = e; }
                if (note) return res(note);
                var over = Date.now() - t0 >= CHECK_LIMIT;
                if (over || S.pendingEnd || !S.visible || (token != null && token !== S.token)) {
                    if (err) console.warn('QuickStart check()', err);
                    return res(null);
                }
                setTimeout(poll, CHECK_EVERY);
            })();
        });
    }

    // Whatever a step can leave ARMED, put down: the right-click menu and
    // the menu bar's menus, the hardware gear popover, a tray sweep, port
    // picks and an unfinished redraw as one, an override edit, the canvas
    // add and menu pop-ups. Dialogs, sheets and the export window are the
    // steps' own business (their before and after hooks), so a step that
    // follows on in the same dialog finds it still up.
    function resetModes() {
        var a = A(), r = R();
        if (!a) return;
        try { a.hideContextMenu(); } catch (e) {}
        hideMenus();
        closePopover();
        try { if (a._traySweepClear) a._traySweepClear(false); } catch (e) {}
        a._sweepSelection = null;
        if (r) { r._sweepPending = null; if (r._removeSweepHud) { try { r._removeSweepHud(); } catch (e) {} } }
        // Ports picked for a redraw as one, and an unfinished one: the
        // step's own snapshot (or the state the step before it handed on)
        // is what stands, so they are just dropped.
        a._portPicks = null;
        a._mergeRedraw = null;
        if (r) r._portPickPending = null;
        if (a._overrideEditing && a.endOverrideEdit) { try { a.endOverrideEdit(); } catch (e) {} }
        if (a.updateOverrideHover) { try { a.updateOverrideHover(false, 0, 0); } catch (e) {} }
        $$('.canvas-add-popup, .canvas-menu-popup').forEach(function (el) { el.remove(); });
    }

    // Enter step i: before(), the callout, the entry snapshot (Back and
    // Replay restore it), then after a beat the act and its check.
    function go(i, opts) {
        opts = opts || {};
        if (i < 0 || i >= S.list.length || S.running) return Promise.resolve();
        var step = S.list[i];
        // Next and Back (opts.carry) hold the windows the step left and
        // the step entered both work in: nothing below closes them, and
        // the step's own before() finds them up (windowsOf).
        var from = S.idx >= 0 && S.idx < S.list.length ? S.list[S.idx] : null;
        S.keep = opts.carry && from && from !== step ? sharedWindows(from, step) : null;
        if (S.keep && !S.keep.length) S.keep = null;
        S.phase = 'enter';
        leaveCurrent(step);
        S.idx = i;
        S.spotEl = null;
        S.running = true;
        setState('running');
        // Every step starts from a known state: nothing armed that a step
        // before it (or this step's own first try) left behind - a redraw
        // or a port pick, an override edit, a sweep - and no menu or
        // popover up. A redraw left armed by a step that failed made the
        // next two steps fail, and the replay button never got it back
        // (1.6.0 QA).
        resetModes();
        var ui = opts.restore ? S.ui[i] : null;
        var chain = Promise.resolve();
        var entered = false;
        if (opts.restore) {
            chain = chain.then(function () { return restoreProject(opts.restore, 'Tutorial Back'); }).then(function () {
                if (S.entries) S.entryAt = S.entries[i];
            });
        } else if (S.entries) {
            entered = true;
            chain = chain.then(function () { return enterStep(i); });
        }
        return chain.then(function () {
            return appSettled();
        }).then(function () {
            // A held window reads the show the restore put back.
            if (S.keep && (opts.restore || entered)) refreshHeld();
            // Back and the replay button put the step's view tab back with
            // its project; before() then sets what the step itself needs.
            if (ui && ui.mode && ui.mode !== mode()) switchView(ui.mode);
            if (step.before) { try { return step.before(); } catch (e) { console.warn('QuickStart before()', e); } }
        }).then(function () {
            return step.before ? sleep(ms(260)) : null;
        }).then(function () {
            // The step is set up: from here its act, and the next change,
            // close what they close.
            S.keep = null;
            // A show restored from the shipped file is framed the way the
            // steps before this one would have left it: the walls in the
            // view the step just switched to (buildScratch frames the same
            // way at the start; a Back keeps the framing the person had).
            if (opts.frame || entered) { try { frameWalls(); } catch (e) {} }
            // What this step shows is on screen before it is rung: the
            // panel its target lives in open, every fold above it undone,
            // and the right sidebar open so the callout has its spot.
            ensureCalloutHome();
            revealStep(step);
            render();
            S.snaps[i] = snapshot();
            S.ui[i] = { mode: mode() };
            if (!step.act) { S.running = false; S.phase = 'settled'; setState('idle'); hideCursor(); return afterStep(); }
            return runAct(step);
        });
    }

    function runAct(step) {
        S.running = true;
        T.mem = {};
        setState('running');
        passthrough(true);
        showCursor();
        var token = ++S.token;
        var err = null;
        return appSettled().then(function () {
            return sleep(ms(500));
        }).then(function () {
            // The canvas may have re-framed a beat after the callout was
            // placed (a view switch resizes it); ring the target where it is
            // now and move the box only if it has come to cover it - once,
            // before the cursor starts, so the act itself never shoves it.
            settle();
            S.phase = 'act';
            return actOf(step);
        }).catch(function (e) {
            err = e;
            console.warn('QuickStart: step "' + step.title + '" failed:', e);
        }).then(function () {
            if (token !== S.token) return null;   // the tour ended under us
            badge('');
            press(false);
            // The verdict waits for the app (its saves, their echoes, a
            // frame) and then asks the check until it answers or
            // CHECK_LIMIT passes: never once, at the instant the act ends.
            return appSettled().then(function () { return pollCheck(step, T.mem, token); });
        }).then(function (note) {
            if (token !== S.token) return;   // the tour ended under us
            S.running = false;
            passthrough(false);
            badge('');
            press(false);
            showResult(note, err);
            settle();
            S.phase = 'settled';
            setState(note ? 'done' : 'failed');
            // The step took on its own entry state: the show holds the next
            // Advanced step's entry. A step that took on an entry that was
            // NOT reached (applyEntry stopped on the way, the step played
            // anyway) proves nothing about the show: the next What's New
            // step must not carry on from it. It did, and "Put the distro
            // on the service" then found no distro (1.6.0 QA: the apply
            // fallback failed 3 runs in 4).
            if (S.entries) {
                var k = S.entries[S.idx];
                S.entryAt = note && S.entryAt === k ? k + 1 : null;
            }
            return afterStep();
        });
    }

    function afterStep() {
        if (S.pendingEnd) { var e = S.pendingEnd; S.pendingEnd = null; return end().then(e.resolve); }
    }

    function goBack() {
        if (S.idx <= 0) return;
        var i = S.idx - 1;
        return go(i, { restore: S.snaps[i], carry: true });
    }
    function replay() {
        return go(S.idx, { restore: S.snaps[S.idx] });
    }

    // Escape leaves the tour - only while no act is running (the app's own
    // Escape cancels drags, sweeps and popovers, and an act must never lose
    // its gesture to the tour).
    // Enter is Next once a step has settled (Done on the last step); in the
    // Go-to box it jumps to the typed step. Escape leaves the tour. Neither
    // does anything while an act runs, so an act's own Enter (typing a name
    // and committing it) is never mistaken for the person's.
    function onKey(e) {
        if (!S.visible || S.running) return;
        if (e.key === 'Enter') {
            e.preventDefault();
            e.stopPropagation();
            var jump = els && els.callout.querySelector('#qs-jump');
            if (jump && e.target === jump) {
                if (jump.value) jumpTo(Number(jump.value));
                else jump.blur();
                return;
            }
            S.idx === S.list.length - 1 ? end() : go(S.idx + 1, { carry: true });
            return;
        }
        if (e.key !== 'Escape') return;
        e.preventDefault();
        e.stopPropagation();
        end();
    }

    // ── the scratch show and the way back ────────────────────────────────
    function lsKeys(prefix) {
        var out = [];
        try {
            for (var i = 0; i < localStorage.length; i++) {
                var k = localStorage.key(i);
                if (k && k.indexOf(prefix) === 0) out.push({ k: k, v: localStorage.getItem(k) });
            }
        } catch (e) {}
        return out;
    }
    var SHEET_PREFIXES = ['lrd_data_cable_sheet_', 'lrd_cable_sheet_'];
    // While a tour runs the SERVER holds the scratch show, so the captured
    // world is also stashed here: a reload or a crash mid-tour must not cost
    // the user their project. Cleared on a clean exit; read back on boot.
    var STASH_KEY = 'lrd_tour_saved_world';

    // Preferences are shared state a step can write (the binder's title
    // block tick, screen order, sheet size are preferences), so the tour
    // carries the server's copy and the app's caches and puts them back.
    function capturePrefs() {
        var a = A();
        var local = null;
        try { local = localStorage.getItem('appPreferences'); } catch (e) {}
        return j('GET', '/api/preferences').catch(function () { return null; }).then(function (server) {
            return {
                server: server,
                cache: a._serverPreferences ? JSON.parse(JSON.stringify(a._serverPreferences)) : null,
                local: local
            };
        });
    }
    function restorePrefs(p) {
        var a = A();
        if (!p) return Promise.resolve();
        try {
            if (p.local == null) localStorage.removeItem('appPreferences');
            else localStorage.setItem('appPreferences', p.local);
        } catch (e) {}
        a._serverPreferences = p.cache ? JSON.parse(JSON.stringify(p.cache)) : a._serverPreferences;
        a._binderLogoImage = null;
        if (!p.server || typeof p.server !== 'object') return Promise.resolve();
        return j('GET', '/api/preferences').catch(function () { return null; }).then(function (now) {
            if (now && a._canonicalJson(now) === a._canonicalJson(p.server)) return null;
            return j('PUT', '/api/preferences', p.server);
        }).then(function () {
            // The cache the app reads through getPreferences() follows the
            // server's copy, whatever a step's write left in it.
            a._serverPreferences = JSON.parse(JSON.stringify(p.server));
        });
    }
    // The guide runs on the SHIPPED Preferences, never the person's. A new
    // screen (initializeLayerDefaults), service (addService), distro
    // (addDistro), a screen's breakout on the server and a new show's
    // cable stock all start from Preferences, and the guide's walls,
    // service and distros are new: a 10-bit, 50 Hz, 30 Hz or Low Latency
    // preference cut the practice screens into other ports, and a 230/400
    // distro system gave the guide's service a system its 120/208 distro
    // could not join (1.6.0 QA). One switch covers every object the guide
    // makes, by hand or through the app's own buttons. The person's own
    // were captured with the world (capturePrefs) and go back first thing
    // when the guide ends (restoreWorld) or after a reload (recoverStash).
    function guidePreferences() {
        var a = A();
        // Only what can be put back is switched: no captured copy, no switch.
        var held = S.saved && S.saved.prefs;
        if (!held || !held.server || typeof held.server !== 'object') return Promise.resolve();
        var shipped = a.getPreferencesDefaults();
        a._serverPreferences = JSON.parse(JSON.stringify(shipped));
        return j('PUT', '/api/preferences', shipped).catch(function (e) {
            console.warn('QuickStart: the shipped preferences were not set', e);
        });
    }

    function captureWorld() {
        var a = A(), r = R();
        if (a._flushPendingSaveState) a._flushPendingSaveState();
        var w = {
            project: snapshot(),
            history: a.history, historyIndex: a.historyIndex,
            mode: mode(),
            sheets: SHEET_PREFIXES.reduce(function (acc, p) { return acc.concat(lsKeys(p)); }, []),
            exportOpen: exportOpen(),
            currentLayerId: a.currentLayer ? a.currentLayer.id : null,
            zoom: r ? r.zoom : null, panX: r ? r.panX : 0, panY: r ? r.panY : 0,
            tray: captureTray(),
            panels: capturePanels(),
            layout: window.LRD_LAYOUT ? window.LRD_LAYOUT.rings() : null,
            // the Preferences tab the person had: the guide's steps open
            // other tabs, and the window reopened on the guide's last one
            prefsTab: a._prefsTab || null,
            prefs: null
        };
        return capturePrefs().then(function (p) {
            w.prefs = p;
            stashWorld(w);
            return w;
        });
    }
    function stashWorld(w) {
        try {
            localStorage.setItem(STASH_KEY, JSON.stringify({
                project: w.project, mode: w.mode, sheets: w.sheets, prefs: w.prefs,
                tray: w.tray, panels: w.panels, layout: w.layout, currentLayerId: w.currentLayerId, at: Date.now()
            }));
        } catch (e) { /* a project too big for the stash still restores on exit */ }
    }
    function clearStash() { try { localStorage.removeItem(STASH_KEY); } catch (e) {} }
    function readStash() {
        try {
            var raw = localStorage.getItem(STASH_KEY);
            var w = raw ? JSON.parse(raw) : null;
            return w && w.project && Array.isArray(w.project.layers) ? w : null;
        } catch (e) { return null; }
    }

    // Boot: a stash means a tour never ended - the server still holds its
    // scratch show. Put the user's project back before anything else.
    function recoverStash() {
        var w = readStash();
        if (!w) return Promise.resolve(false);
        var a = A();
        // The person's Preferences first: the guide ran on the shipped
        // ones (guidePreferences), and their project comes back under
        // their own.
        return restorePrefs(w.prefs).then(function () {
            return restoreProject(w.project, 'Tour Recovery');
        }).then(function () {
            try {
                SHEET_PREFIXES.forEach(function (p) { lsKeys(p).forEach(function (e) { localStorage.removeItem(e.k); }); });
                (w.sheets || []).forEach(function (e) { localStorage.setItem(e.k, e.v); });
            } catch (e) {}
            if (w.mode) switchView(w.mode);
            if (w.currentLayerId != null) {
                var l = a.project.layers.find(function (x) { return x.id === w.currentLayerId; });
                if (l) a.selectLayer(l);
            }
            restoreLayout(w.layout);
            restoreTray(w.tray);
            restorePanels(w.panels);
            a.resetHistory('Recovered');
            try { a.updateUI(); } catch (e) {}
            try { a.renderHardwareDock(); } catch (e) {}
            if (R()) { R().fitToView(); }
            clearStash();
            if (typeof a._toast === 'function') {
                a._toast('Your project was put back after an interrupted guide.', false, 6000);
            }
            return true;
        }).catch(function (e) {
            console.warn('QuickStart: recovery failed', e);
            return false;
        });
    }

    // Everything transient a step may have left standing: its armed modes
    // (resetModes) and every dialog, sheet and window.
    function closeTransients() {
        var a = A();
        if (!a) return;
        resetModes();
        a._dockFlagOpen = false;
        var bal = $('#balance-modal'); if (bal) bal.remove();
        closePrefs();
        var pp = $('#preset-picker-modal'); if (pp) pp.style.display = 'none';
        if (typeof a.closeStartPage === 'function') a.closeStartPage();
        hideMenus();
        closePullSheet();
        closeExport();
        if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    }

    // Adopt `saved` as the project, the way undo does: locally first, then
    // the restore PUT (sequenced behind in-flight layer PUTs), then the
    // hardware tree and the assignment re-read from the server.
    function restoreProject(saved, label) {
        var a = A(), r = R();
        if (a._flushPendingSaveState) a._flushPendingSaveState();
        a.project = JSON.parse(JSON.stringify(saved));
        a.dedupeProjectLayers('tutorial_restore');
        // The restored world's multi numbers are the ones in force again.
        try { if (a._resetMultiBaseline) a._resetMultiBaseline(); } catch (e) {}
        var cur = a.currentLayer ? a.project.layers.find(function (l) { return l.id === a.currentLayer.id; }) : null;
        a.currentLayer = cur || a.project.layers[0] || null;
        a.selectedLayerIds = new Set(a.currentLayer ? [a.currentLayer.id] : []);
        try { a.updateCustomFlowUI(); } catch (e) {}
        try { a.updateCustomPowerUI(); } catch (e) {}
        try { a._refreshPowerPanelsAfterRestore(); } catch (e) {}
        try { a.loadLayerToInputs(); } catch (e) {}
        try { a.syncRasterFromProject(); } catch (e) {}
        var entry = { project: a.project, action: label };
        // keepPristine: the world going back is the user's own, taken before
        // the guide touched anything. A guide run on the fresh startup
        // project (the first-run guide) must hand it back still pristine,
        // or the startup screen stops following Preferences after the guide.
        return Promise.resolve(a._syncRestoredProject(entry, label, { keepPristine: true })).then(function () {
            return a.refreshProcessors();
        }).then(function () {
            return a.refreshPortAssignment();
        }).then(function () {
            a._circuitTailCache = null;
            try { a.renderLayers(); } catch (e) {}
            try { if (a.renderBeaches) a.renderBeaches(); } catch (e) {}
            try { a.renderHardwareDock(); } catch (e) {}
            try { a.loadLayerToInputs(); } catch (e) {}
            if (r) r.render();
        });
    }

    function restoreWorld(w) {
        var a = A(), r = R();
        closeTransients();
        // The person's Preferences first: the guide ran on the shipped
        // ones (guidePreferences), and their project comes back under
        // their own.
        return restorePrefs(w.prefs).then(function () {
            return restoreProject(w.project, 'Tutorial Exit');
        }).then(function () {
            a.history = w.history;
            a.historyIndex = w.historyIndex;
            a._prefsTab = w.prefsTab || null;
            // The person's own "unsaved" again, on the server too.
            if (typeof a._noteUnsavedState === 'function') a._noteUnsavedState();
            try {
                SHEET_PREFIXES.forEach(function (p) { lsKeys(p).forEach(function (e) { localStorage.removeItem(e.k); }); });
                w.sheets.forEach(function (e) { localStorage.setItem(e.k, e.v); });
            } catch (e) {}
            if (w.mode) switchView(w.mode);
            if (w.currentLayerId != null) {
                var l = a.project.layers.find(function (x) { return x.id === w.currentLayerId; });
                if (l) a.selectLayer(l);
            }
            if (r && w.zoom) { r.zoom = w.zoom; r.panX = w.panX; r.panY = w.panY; }
            restoreLayout(w.layout);
            restoreTray(w.tray);
            restorePanels(w.panels);
            closeTransients();
            var em = $('#export-modal');
            if (em) em.style.display = w.exportOpen ? 'block' : 'none';
            try { a.updateUI(); } catch (e) {}
            try { a.renderHardwareDock(); } catch (e) {}
            if (r) r.render();
            clearStash();
        });
    }

    // The scratch show: a blank project through the real API (the PUT
    // repairs; its returned body is what the app adopts), one screen, the
    // tour's own prerequisites stamped on it, history reset.
    function buildScratch(seed) {
        var a = A(), r = R();
        seed = seed || {};
        closeTransients();
        if (a._flushPendingSaveState) a._flushPendingSaveState();
        // A cable sheet left up on the person's own multi (per distro id
        // and number, in localStorage) would come up on the demo's strip of
        // the same id - a strip with its sheet up has no chips to drag. The
        // flags are captured (SHEET_PREFIXES) and go back on exit.
        SHEET_PREFIXES.forEach(function (p) { lsKeys(p).forEach(function (e) { lsPut(e.k, null); }); });
        return j('GET', '/api/project').then(function (proj) {
            proj.name = seed.name || 'Demo Show';
            // The guides are written in feet - the lengths they type and
            // the words they say - so the scratch show is a feet show
            // whatever the person's own is (it goes back on exit).
            proj.cableUnit = 'ft';
            proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
            proj.beaches = []; proj.snakes = [];
            delete proj.services;
            delete proj.fiberCables;
            delete proj.port_assignments;
            delete proj.binder;
            delete proj.next_processor_seq;
            proj.next_group_seq = 1; proj.next_beach_seq = 1;
            // A 12 x 6 wall of 200 px cabinets beside a second one needs a
            // raster wider than 1080p; a 5K raster holds the whole show.
            proj.raster_width = 5120; proj.raster_height = 2880;
            proj.show_raster_width = 5120; proj.show_raster_height = 2880;
            // ONE canvas, the scratch show's own. The person's canvases
            // stayed in the scratch show until 1.6.0 QA: on a show with
            // four, the demo walls sat inside canvases stacked over each
            // other and "Cabinets across screens" dragged on one of the
            // person's canvases instead of the walls.
            var c1 = (proj.canvases || [])[0] || {};
            proj.canvases = [{
                id: c1.id || 'c1', name: 'Canvas 1', color: c1.color || '#4A90E2',
                workspace_x: 0, workspace_y: 0,
                raster_width: 5120, raster_height: 2880,
                show_raster_width: 5120, show_raster_height: 2880,
                data_flow_perspective: 'front', power_perspective: 'front',
                visible: true
            }];
            proj.active_canvas_id = proj.canvases[0].id;
            proj.data_flow_perspective = 'front';
            proj.power_perspective = 'front';
            return j('PUT', '/api/project', proj);
        }).then(function () {
            return j('POST', '/api/layer/add', Object.assign({
                name: 'DEMO WALL', offset_x: 0, offset_y: 0,
                columns: 8, rows: 5, cabinet_width: 128, cabinet_height: 128
            }, seed.wall || {}));
        }).then(function () {
            return j('GET', '/api/project');
        }).then(function (p) {
            a.project = p;
            a.dedupeProjectLayers('tutorial_seed');
            a.selectLayer(a.project.layers[0]);
            // The tour's prerequisites, stamped AFTER selectLayer (which
            // fills what is unset from the preferences) and written through
            // so the server holds the same screen. Its processing is the
            // practice screens' (PRACTICE_PROCESSING), not the preferences'.
            var fields = Object.assign({ powerVoltage: 208, powerAmperage: 20, panelWatts: 200 },
                                       PRACTICE_PROCESSING, seed.layer || {});
            var l = a.project.layers[0];
            Object.keys(fields).forEach(function (k) { l[k] = fields[k]; });
            // A screen always carries a breakout its voltage allows.
            if (typeof a.normalizePowerBreakout === 'function') a.normalizePowerBreakout(l);
            a.updateLayers([l]);
            return a.refreshProcessors();
        }).then(function () {
            return a.refreshPortAssignment();
        }).then(function () {
            a._circuitTailCache = null;
            try { a.syncRasterFromProject(); } catch (e) {}
            try { a.updateUI(); } catch (e) {}
            try { if (a.refreshSocaRuns) a.refreshSocaRuns(); } catch (e) {}
            try { a.renderLayers(); } catch (e) {}
            try { if (a.renderBeaches) a.renderBeaches(); } catch (e) {}
            try { a.renderHardwareDock(); } catch (e) {}
            try { a.loadLayerToInputs(); } catch (e) {}
            a.resetHistory('Tutorial');
            // The tray and the side panels for the demo, then the walls
            // framed in the canvas they leave.
            seedLayout();
            seedTray();
            seedPanels();
            try { a.renderHardwareDock(); } catch (e) {}
            frameWalls();
        });
    }

    // ── show / end ───────────────────────────────────────────────────────
    // `custom` is a tour built on the fly ({ title, seed, steps, entries }):
    // What's New (startSteps).
    function show(name, custom) {
        var tour = custom || TOURS[name];
        if (!tour) return Promise.resolve();
        // A guide started while the last one is still putting the person's
        // world back waits for it: started at once, its scratch show was
        // overwritten by that restore, and it captured the scratch show as
        // the world to put back, so leaving it lost the person's project.
        if (S.ending) return S.ending.then(function () { return show(name, custom); });
        if (!els) build();
        // The ghost cursor starts from the middle of the window, not from
        // the corner it is born in, so the first act's travel reads as a
        // hand reaching from where a person would be looking.
        if (!cur.shown) setCursor(window.innerWidth / 2, window.innerHeight / 2);
        if (S.visible) leaveCurrent(null);
        S.name = name;
        S.list = tour.steps.map(function (k) {
            var s = STEPS[k];
            if (!s) throw new Error('QuickStart: no step "' + k + '"');
            return s;
        });
        S.snaps = [];
        S.ui = [];
        S.idx = -1;
        S.home = null;
        S.jumpedVia = null;
        S.keys = tour.steps.slice();
        S.entries = tour.entries ? tour.entries.slice() : null;
        S.entryAt = null;
        S.visible = true;
        els.catch.style.display = 'block';
        els.spot.style.display = 'block';
        els.callout.style.display = 'block';
        els.callout.innerHTML = '<h3>' + tour.title + '</h3><p>Setting up a scratch show&hellip;</p>';
        setState('running');
        setSpot(null);
        place({ center: true });
        S.running = true;
        var seeded = (S.saved ? Promise.resolve(S.saved) : captureWorld()).then(function (w) {
            S.saved = w;
            return guidePreferences();
        }).then(function () {
            return buildScratch(tour.seed || {});
        });
        return seeded.catch(function (e) {
            console.warn('QuickStart: scratch show failed', e);
        }).then(function () {
            S.running = false;
            return go(0);
        });
    }

    function end() {
        if (!els || !S.visible) return Promise.resolve();
        if (S.running) {
            if (S.pendingEnd) return S.pendingEnd.promise;
            var p = {};
            p.promise = new Promise(function (res) { p.resolve = res; });
            S.pendingEnd = p;
            return p.promise;
        }
        S.token++;
        S.keep = null;
        S.phase = null;
        leaveCurrent(null);
        S.visible = false;
        S.running = true;   // no re-entry while the world goes back
        hideCursor();
        els.catch.style.display = 'none';
        els.spot.style.display = 'none';
        els.callout.style.display = 'none';
        passthrough(false);
        var saved = S.saved;
        S.saved = null;
        S.idx = -1;
        S.list = [];
        S.snaps = [];
        S.ui = [];
        S.keys = [];
        S.entries = null;
        S.entryAt = null;
        var chain = saved ? sleep(ms(300)).then(function () { return restoreWorld(saved); }) : Promise.resolve();
        var ending = chain.catch(function (e) {
            console.warn('QuickStart: restore failed', e);
        }).then(function () {
            S.running = false;
            if (S.ending === ending) S.ending = null;
        });
        S.ending = ending;
        return ending;
    }

    // ── the step library ─────────────────────────────────────────────────
    // ONE action per step. `target` is the selector the spotlight rings (a
    // function when it names hardware minted during the tour); `place` the
    // callout's side; `body` one or two sentences in the user's terms.
    // `since` names the app version that brought the feature a step shows
    // ('1.5.0', '1.5.2'); steps older than 1.5 carry none.
    var STEPS = {
        introAdvanced: {
            title: 'The full guide', center: true,
            body: 'This guide builds a small show in front of you on a scratch project. Your own project is put back when you leave.',
            before: function () { switchView('pixel-map'); }
        },
        introQuick: {
            title: 'Welcome to LED Raster Designer', center: true,
            body: 'Watch a wall get built, wired and exported on a scratch project. Your own project is put back when you leave, and you can skip at any time.',
            before: function () { switchView('pixel-map'); }
        },
        projectName: {
            target: '#project-name', place: 'bottom', title: 'Name the project',
            body: 'Type the show&rsquo;s name here. It names every export and the binder&rsquo;s title block.',
            before: function () { switchView('pixel-map'); },
            act: function (t) { return t.type('#project-name', 'Demo Show', { enter: true }); },
            check: function () { return A().project.name === 'Demo Show' ? 'The project is called Demo Show.' : null; }
        },
        cabinetSize: {
            target: '#cabinet-width', ring: ['#cabinet-width', '#cabinet-height'], place: 'right', title: 'Cabinet size',
            avoid: ['#cabinet-width', '#cabinet-height'],
            body: 'The pixel size of one cabinet, width then height. Every cabinet on the wall takes it.',
            before: function () { switchView('pixel-map'); },
            act: function (t) {
                return t.type('#cabinet-width', '200').then(function () {
                    return t.type('#cabinet-height', '200');
                }).then(function () {
                    return t.wait(function () {
                        var w = wall();
                        return w && Number(w.cabinet_width) === 200 && Number(w.cabinet_height) === 200
                            && w.panels && w.panels[0] && Number(w.panels[0].width) === 200;
                    });
                }).then(function () { frameWalls(); });
            },
            check: function () {
                var w = wall();
                return w && Number(w.cabinet_width) === 200 && Number(w.cabinet_height) === 200
                    ? 'Each cabinet is 200 × 200 px.' : null;
            }
        },
        // The panel saved on the screen (1.6.0, app-screen-info.js
        // updateLayerFromInputs, app-presets.js catalogPanelModelFields): a
        // pick from the panel library fills Screen Info's Panel field, and
        // a typed name names a panel of your own. The cabinet step just
        // typed its pixels by hand, which forgets any saved panel, so the
        // demo wall names its own here; the pull sheet's panel rows print it.
        panelName: {
            since: '1.6.0',
            target: '#panel-model-name', place: 'right', title: 'Name the panel',
            avoid: ['#panel-model-name'],
            body: 'Panel is the cabinet as the pull sheet names it. A pick from the panel library fills it in; for a panel of your own, type its name.',
            before: function () { switchView('pixel-map'); },
            act: function (t) {
                return t.type('#panel-model-name', 'Demo Panel', { enter: true }).then(function () {
                    return t.wait(function () { var w = wall(); return w && w.panelModelName === 'Demo Panel'; });
                }).then(function (ok) {
                    if (!ok) throw new Error('the screen did not take the panel name');
                    return t.pause(PACE.rest);
                });
            },
            check: function () {
                var w = wall();
                if (!w || w.panelModelName !== 'Demo Panel') return null;
                var types = A().pullPanelTypes(w);
                return (w.name || 'The screen') + ' hangs ' + types.none + ': the pull sheet counts its cabinets by that name, and a half tile as ' + types.height + '.';
            }
        },
        // The start page a launch opens on (1.6.0, app-start-page.js):
        // New project, Open file… and the Recent Files list. A recent file
        // with a known path is read from disk again (app-logs-recent.js), so
        // it opens as last saved. The step opens the page over the scratch
        // show, points at New project, and closes it with nothing chosen.
        startPage: {
            since: '1.6.0',
            target: function () { return startPageUp() ? '#start-page-modal .start-page-content' : '#btn-open'; },
            place: 'right', title: 'The start page',
            body: 'The app opens on a start page: New project, Open file&hellip;, or a show from your recent files. A recent show is read from its file, so it opens as you last saved it.',
            // Opened before the callout is placed, so the callout sits
            // beside the page rather than under it.
            before: function () {
                switchView('pixel-map');
                var a = A();
                if (a && a.openStartPage && !startPageUp()) a.openStartPage('guide');
            },
            act: function (t) {
                return t.wait(function () { return startPageUp() && $('#start-page-new'); }, 4000).then(function (btn) {
                    if (!btn) throw new Error('the start page did not open');
                    return null;
                }).then(function () {
                    return t.pause(PACE.opened);
                });
            },
            check: function () {
                var n = $('#start-page-new'), o = $('#start-page-open');
                return startPageUp() && n && o && n.textContent === 'New project'
                    ? 'New project opens the panel library, Open file… is File > Open, and Recent lists the shows you saved or opened, newest first.' : null;
            },
            after: function () { var a = A(); if (a && a.closeStartPage) a.closeStartPage(); }
        },
        // The panel a new project starts with (1.6.0, app-presets.js
        // maybeOpenStartupPicker): File > New, and New on the start page,
        // open the panel library first, and the pick makes the first
        // screen, its name in the Panel field. The step opens the same
        // chooser over the scratch show to show it, and closes it with
        // nothing changed.
        startPanel: {
            since: '1.6.0',
            target: '#btn-new', place: 'bottom', title: 'Pick a panel to start',
            body: 'A new project opens the panel library first. The panel you pick makes the first screen and names it in Panel; Cancel starts with no screens.',
            before: function () { switchView('pixel-map'); },
            act: function (t) {
                return t.hover('#btn-new').then(function (p) {
                    ripple(p.x, p.y);
                    A().openPresetPicker({ mode: 'startup' });
                    return t.wait(function () { return pickerOpen() && $('#panel-catalog-list .panel-catalog-row'); }, 6000);
                }).then(function (row) {
                    if (!row) throw new Error('the panel library did not load');
                    return t.spot($('#preset-picker-modal .modal-content')).then(function () {
                        return t.pause(PACE.opened);
                    });
                });
            },
            check: function () {
                var title = $('#preset-picker-title');
                return pickerOpen() && A()._pickerMode === 'startup' && title && title.textContent === 'Choose a panel'
                    ? 'File > New opens this: pick a panel, and Use Panel makes Screen1 of it.' : null;
            },
            after: function () { closePicker(); }
        },
        // Add Screen with nothing picked (1.6.0, app-presets.js
        // _lastScreenPanelData): the new screen hangs the last screen's
        // panel, and the line at the chooser's foot names it. The step
        // opens Add Screen over the demo wall the Panel step named and
        // closes it with nothing added.
        sameAsLast: {
            since: '1.6.0',
            target: function () { return pickerOpen() ? '#preset-picker-summary' : '#layers-list .canvas-add-btn'; },
            place: 'top', title: 'Add Screen copies the last panel',
            body: 'Add Screen with nothing picked makes a screen of the last screen&rsquo;s panel. The line at the foot says which panel that is.',
            window: 'picker:add',
            before: function () { switchView('pixel-map'); },
            act: function (t) {
                return openAddPicker(t).then(function () {
                    return t.wait(function () {
                        var s = $('#preset-picker-summary');
                        return pickerOpen() && s && /will use/.test(s.textContent) ? s : null;
                    }, 6000);
                }).then(function (s) {
                    if (!s) throw new Error('Add Screen did not offer the last screen panel');
                    return t.spot(s).then(function () { return t.pause(PACE.opened); });
                });
            },
            check: function () {
                var s = pickerOpen() ? $('#preset-picker-summary') : null;
                var m = s && /will use (.+)'s panel \((.+)\)/.exec(s.textContent);
                return m ? 'With nothing picked, the new screen hangs ' + m[2] + ', the panel on ' + m[1] + '.' : null;
            },
            after: function () { closePicker(); }
        },
        // Average power in the panel library (1.6.0, app-presets.js
        // _panelWattsText): the max every power figure is planned on, and
        // the sheet's average beside it where the sheet gives one. The step
        // opens the screen chooser, finds a panel whose sheet gives both,
        // and closes the chooser with nothing added.
        avgPower: {
            since: '1.6.0',
            target: function () { return $(AVG_ROW) ? AVG_ROW : '#layers-list .canvas-add-btn'; },
            place: 'left', title: 'Average power in the library',
            avoid: ['#panel-catalog-search'],
            body: 'The panel library shows a panel&rsquo;s average power beside its max where the spec sheet gives one. Power is still planned on the max.',
            window: 'picker:add',
            before: function () { switchView('pixel-map'); },
            act: function (t) {
                return openAddPicker(t).then(function () {
                    return t.wait(function () { return pickerOpen() && $('#panel-catalog-list .panel-catalog-row'); }, 6000);
                }).then(function (row) {
                    if (!row) throw new Error('the panel library did not load');
                    return t.type('#panel-catalog-search', 'BP2V2');
                }).then(function () {
                    return t.wait(function () { return $(AVG_ROW); }, 4000);
                }).then(function (row) {
                    if (!row) throw new Error('the library has no Black Pearl BP2V2');
                    return t.spot(row).then(function () { return t.pause(PACE.opened); });
                });
            },
            check: function () {
                var row = pickerOpen() ? $(AVG_ROW) : null;
                var m = row && /(\d+(?:\.\d+)?)W max · (\d+(?:\.\d+)?)W avg/.exec(row.textContent);
                return m ? 'The BP2V2 reads ' + m[1] + 'W max · ' + m[2] + 'W avg; a screen of them is planned at '
                    + m[1] + ' W a panel.' : null;
            },
            after: function () { closePicker(); }
        },
        gridSize: {
            target: '#screen-columns', ring: ['#screen-columns', '#screen-rows'], place: 'right', title: 'Columns and rows',
            avoid: ['#screen-columns', '#screen-rows'],
            body: 'How many cabinets wide and tall the wall is. The wall redraws as each number lands.',
            before: function () { switchView('pixel-map'); },
            act: function (t) {
                return t.type('#screen-columns', '12').then(function () {
                    return t.type('#screen-rows', '6');
                }).then(function () {
                    return t.wait(function () { var w = wall(); return w && w.panels && w.panels.length === 72; });
                }).then(function () { frameWalls(); });
            },
            check: function () {
                var w = wall();
                return w && w.panels && w.panels.length === 72 ? '12 × 6 = 72 cabinets.' : null;
            }
        },
        fit: {
            target: '#btn-fit', place: 'bottom', title: 'Fit',
            body: 'Fit frames the whole raster in the window. Scroll to zoom and Space+drag to pan from there.',
            before: function () { switchView('pixel-map'); },
            act: function (t) { return t.click('#btn-fit').then(function () { return t.pause(300); }); },
            check: function () {
                var w = wall(), r = R();
                if (!w || !r) return null;
                var a = T.cabinetPoint(w, { index: 0, raw: true });
                var b = T.cabinetPoint(w, { index: w.panels.length - 1, raw: true });
                var rect = r.canvas.getBoundingClientRect();
                var inside = function (p) { return p && p.x >= rect.left && p.x <= rect.right && p.y >= rect.top && p.y <= rect.bottom; };
                return inside(a) && inside(b) ? 'The whole wall is in view.' : null;
            }
        },
        blankCabinet: {
            target: '#main-canvas', place: 'top', title: 'Blank a cabinet',
            body: 'Alt+click a cabinet on the Pixel Map and it goes blank: a hole in the wall for a non-rectangular shape.',
            // Fit just framed the whole raster; the wall comes back to
            // working size for the steps that read its cabinets.
            before: function () { switchView('pixel-map'); frameWalls(); },
            act: function (t) {
                var w = wall();
                var pt = t.cabinetPoint(w, { index: 14 });
                return t.hover(pt, { badge: 'Alt' }).then(function () {
                    press(true);
                    t.canvasDown(pt, { altKey: true });
                    return t.pause(90);
                }).then(function () {
                    t.canvasUp(pt, { altKey: true });
                    press(false);
                    ripple(pt.x, pt.y);
                    return t.wait(function () { var l = wall(); return l && l.panels.some(function (p) { return p.hidden; }); });
                }).then(function () { return t.pause(PACE.rest); });
            },
            check: function () {
                var w = wall();
                var n = w ? w.panels.filter(function (p) { return p.hidden; }).length : 0;
                return n === 1 ? 'One cabinet is blanked; the wall keeps its numbering around it.' : null;
            }
        },
        cabinetIdStyle: {
            target: 'input[name="cabinet-id-style"][value="row-col"]', place: 'right', title: 'Cabinet ID view',
            avoid: ['[data-mode="cabinet-id"]', 'input[name="cabinet-id-style"][value="row-col"]'],
            body: 'Cabinet ID numbers every cabinet for the install crew. Pick the numbering style the crew reads.',
            act: function (t) {
                return t.click('[data-mode="cabinet-id"]').then(function () {
                    return t.click('input[name="cabinet-id-style"][value="row-col"]');
                }).then(function () {
                    return t.wait(function () { var w = wall(); return w && w.cabinetIdStyle === 'row-col'; });
                });
            },
            check: function () {
                var w = wall();
                return mode() === 'cabinet-id' && w && w.cabinetIdStyle === 'row-col'
                    ? 'Cabinets now read 1,1  1,2  1,3 across each row.' : null;
            }
        },
        showLook: {
            target: '#main-canvas', place: 'top', title: 'Show Look view',
            avoid: ['[data-mode="show-look"]'],
            body: 'Show Look is the real stage layout. Shift+drag a screen to put it where it stands; Data and Power follow this layout.',
            act: function (t) {
                return t.click('[data-mode="show-look"]').then(function () {
                    var w = wall();
                    t.mem.x = Number(w.showOffsetX != null ? w.showOffsetX : w.offset_x) || 0;
                    var pt = t.cabinetPoint(w, { index: 0 });
                    return t.hover(pt, { badge: 'Shift' }).then(function () {
                        press(true);
                        t.canvasDown(pt, { shiftKey: true });
                        return t.pause(PACE.dragPress);
                    }).then(function () {
                        return t.canvasGlide({ x: pt.x + 60, y: pt.y }, { shiftKey: true });
                    }).then(function () {
                        return t.pause(PACE.dragHover);
                    }).then(function () {
                        t.canvasUp({ x: pt.x + 60, y: pt.y }, { shiftKey: true });
                        press(false);
                        return t.wait(function () { var l = wall(); return l && Number(l.showOffsetX) !== t.mem.x; });
                    }).then(function () { return t.pause(PACE.dragRest); });
                });
            },
            check: function (mem) {
                var w = wall();
                return w && Number(w.showOffsetX) !== mem.x
                    ? 'DEMO WALL moved stage right; its Pixel Map position is untouched.' : null;
            }
        },
        processing: {
            target: '#processor-type', place: 'right', title: 'Data view and processing',
            avoid: ['[data-mode="data-flow"]', '#processor-type'],
            body: 'Data plans the signal. Processing sets the pixels a port carries and the ports required, and it is the platform wall: a screen lands only on gear it matches.',
            act: function (t) {
                return t.click('[data-mode="data-flow"]').then(function () {
                    return t.select('#processor-type', 'novastar-coex-1g');
                }).then(function () {
                    return t.wait(function () { var w = wall(); return w && w.processorType === 'novastar-coex-1g'; });
                });
            },
            check: function () {
                var w = wall();
                if (!w || w.processorType !== 'novastar-coex-1g') return null;
                var sel = $('#processor-type');
                var name = sel && sel.selectedOptions[0] ? sel.selectedOptions[0].textContent.trim() : 'NovaStar COEX 1G';
                var req = $('#ports-required') ? $('#ports-required').textContent.trim() : '?';
                return name + '. Ports required: ' + req + '.';
            }
        },
        flowPattern: {
            target: '.flow-pattern-btn[data-pattern="tl-v"]:not(.power-flow-pattern-btn)', place: 'right', title: 'Flow pattern',
            body: 'The top row of patterns are snakes: each row or column runs back the other way. This one starts top-left and runs down each column.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                return t.click('.flow-pattern-btn[data-pattern="tl-v"]:not(.power-flow-pattern-btn)').then(function () {
                    return t.wait(function () { var w = wall(); return w && w.flowPattern === 'tl-v'; });
                });
            },
            check: function () {
                var w = wall();
                return w && w.flowPattern === 'tl-v' ? 'Ports now run top-left, vertical first.' : null;
            }
        },
        // The Z patterns (tl-h-z ...), the row under the snakes. The step
        // picks the Z twin of the wall's top-left vertical snake, reads the
        // walk (every column a port moves into starts again at the top),
        // and puts the wall back on the snake so the rest of the guide runs
        // on the map it always has.
        zPattern: {
            since: '1.6.0',
            target: '.flow-pattern-btn[data-pattern="tl-v-z"]:not(.power-flow-pattern-btn)', place: 'right', title: 'Z patterns',
            body: 'The row under the snakes holds the Z patterns: every row or column starts again from the same side, the way a cable goes back to the start. This one starts top-left and reads every column from the top.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var sel = function (p) { return '.flow-pattern-btn[data-pattern="' + p + '"]:not(.power-flow-pattern-btn)'; };
                return t.click(sel('tl-v-z')).then(function () {
                    return t.wait(function () { var w = wall(); return w && w.flowPattern === 'tl-v-z'; });
                }).then(function () {
                    // Every cabinet that opens a new column inside a port is
                    // on the top row: no column ran back up.
                    var w = wall();
                    var a = (A().calculatePortAssignments(w) || []);
                    t.mem.zTop = a.every(function (x, i) {
                        var prev = a[i - 1];
                        return !prev || prev.port !== x.port || prev.panel.col === x.panel.col || x.panel.row === 0;
                    });
                    return t.click(sel('tl-v'));
                }).then(function () {
                    return t.wait(function () { var w = wall(); return w && w.flowPattern === 'tl-v'; });
                });
            },
            check: function (mem) {
                var w = wall();
                if (!mem.zTop || !w || w.flowPattern !== 'tl-v') return null;
                return 'On the Z pattern every column started at the top. The wall is back on top-left, vertical first.';
            }
        },
        // Port numbers (layer.portNumberOrder): shown only where Organized
        // cuts a row into more than one port, so the step adds a screen
        // whose rows are 8 cabinets of 512 x 256 on NovaStar Armor, 5 to a
        // port: each row is a port of 5 and a port of 3.
        portNumbers: {
            since: '1.6.0',
            target: '#port-number-order-row', place: 'right', title: 'Port numbers',
            avoid: ['#port-number-down'],
            body: 'A row too long for one port is cut into ports of whole cabinets. Port numbers sets their order: Across goes along each row, Down goes down the stacks and starts each new stack back at the first row.',
            before: function () { closePrefs(); hideMenus(); closePopover(); switchView('data-flow'); },
            act: function (t) {
                var a = A(), w = wall();
                var bottom = screens().reduce(function (m, l) {
                    return Math.max(m, (Number(l.offset_y) || 0) + (Number(l.rows) || 0) * (Number(l.cabinet_height) || 0));
                }, 0);
                var find = function () {
                    return (a.project.layers || []).find(function (x) { return x.id === t.mem.layer; }) || null;
                };
                return j('POST', '/api/layer/add', {
                    name: 'LONG ROWS', columns: 8, rows: 2,
                    cabinet_width: 512, cabinet_height: 256,
                    offset_x: (w && Number(w.offset_x)) || 0, offset_y: bottom + 200
                }).then(function (layer) {
                    practiceScreen(layer);
                    layer.processorType = 'novastar-armor';
                    layer.flowPattern = 'tl-h';
                    layer.portMappingMode = 'organized';
                    a.upsertProjectLayer(layer);
                    a.updateLayers([layer]);
                    t.mem.layer = layer.id;
                    var l = find();
                    a.selectLayer(l);
                    frameLayers([l]);
                    a.saveState('Add Layer');
                    a.updatePortCapacityDisplay();
                    return t.wait(function () {
                        var row = $('#port-number-order-row');
                        return row && row.style.display !== 'none' ? row : null;
                    });
                }).then(function (row) {
                    if (!row) throw new Error('Port numbers is not shown for LONG ROWS');
                    return t.click('#port-number-down');
                }).then(function () {
                    return t.wait(function () { var l = find(); return l && l.portNumberOrder === 'down'; });
                });
            },
            check: function (mem) {
                var a = A();
                var l = (a.project.layers || []).find(function (x) { return x.id === mem.layer; });
                if (!l || l.portNumberOrder !== 'down') return null;
                var start = (a.calculatePortAssignments(l) || []).find(function (x) { return x.port === 2 && x.isPortStart; });
                return start ? 'Port 2 now starts row ' + (start.panel.row + 1) + ' of LONG ROWS, under port 1.' : null;
            }
        },
        // Ports required is the minimum (1.6.0, app-screen-info.js
        // getLayerPortsMinimum): on a custom data path it reads the fewest
        // ports the screen needs in its Organized or Max Capacity setting,
        // never the ports drawn so far. LONG ROWS goes into custom mode,
        // which starts it empty, and the readout holds.
        portsMinimum: {
            since: '1.6.0',
            target: '#ports-required', place: 'right', title: 'Ports required is the minimum',
            avoid: ['#custom-flow-toggle'],
            body: 'Ports required is the fewest ports the screen needs in its Organized or Max Capacity setting. In custom mode it still reads that, however many ports you&rsquo;ve drawn.',
            before: function () { closePrefs(); hideMenus(); closePopover(); switchView('data-flow'); },
            act: function (t) {
                var a = A();
                var l = (a.project.layers || []).find(function (x) { return x.name === 'LONG ROWS'; });
                if (!l) throw new Error('LONG ROWS is missing');
                t.mem.layer = l.id;
                if (!a.currentLayer || a.currentLayer.id !== l.id) a.selectLayer(l);
                a.updatePortCapacityDisplay();
                t.mem.before = $('#ports-required') ? $('#ports-required').textContent.trim() : '';
                return t.click('#custom-flow-toggle').then(function () {
                    return t.wait(function () {
                        var x = (a.project.layers || []).find(function (y) { return y.id === t.mem.layer; });
                        return x && a.isCustomFlow(x);
                    });
                }).then(function (ok) {
                    if (!ok) throw new Error('LONG ROWS did not go into custom mode');
                    return t.spot($('#ports-required')).then(function () { return t.pause(PACE.rest); });
                });
            },
            check: function (mem) {
                var a = A();
                var l = (a.project.layers || []).find(function (x) { return x.id === mem.layer; });
                if (!l || !a.isCustomFlow(l)) return null;
                var paths = l.customPortPaths || {};
                var drawn = Object.keys(paths).filter(function (k) { return (paths[k] || []).length; }).length;
                var req = $('#ports-required') ? $('#ports-required').textContent.trim() : '';
                if (drawn || !req || req !== mem.before || !(Number(req) > 0)) return null;
                return 'LONG ROWS is in custom mode with no ports drawn, and Ports required still reads ' + req + '.';
            }
        },
        addProcessor: {
            target: '#hw-dock-data-controls', place: 'top', title: 'Add a processor',
            avoid: ['#processor-add-device', '#processor-add-btn'],
            body: 'Pick a model in the tray&rsquo;s header and press Add. Its ports appear in the tray, ready to drag onto screens.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                return t.select('#processor-add-device', 'novastar-mx40-pro').then(function () {
                    return t.click('#processor-add-btn');
                }).then(function () {
                    return t.wait(function () { return proc() && $('[data-hwdock^="processor-"]'); });
                });
            },
            check: function () {
                var p = proc(), c = card();
                if (!p) return null;
                var n = c && c.ports ? c.ports.length : null;
                return (p.deviceName || 'The processor') + ' is in the tray' + (n ? ' with ' + n + ' ports.' : '.');
            }
        },
        nameProcessor: {
            target: function () { var p = proc(); return p ? '[data-lrd-field="processor-name-' + p.id + '"]' : '[data-lrd-field^="processor-name-"]'; },
            place: 'top', title: 'Name it on its header',
            body: 'Every header holds its own name box. Name the processor SR and its ports read SR-1, SR-2 on the wall.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var p = proc();
                return t.type('[data-lrd-field="processor-name-' + p.id + '"]', 'SR', { enter: true }).then(function () {
                    return t.wait(function () { var q = proc(); return q && q.name === 'SR'; });
                });
            },
            check: function () { var p = proc(); return p && p.name === 'SR' ? 'Its ports now read SR-1, SR-2 …' : null; }
        },
        dropProcessor: {
            target: function () { var p = proc(); return p ? '[data-hwdock="processor-' + p.id + '"]' : '[data-hwdock^="processor-"]'; },
            place: 'top', title: 'Drag it onto the wall',
            avoid: [function () { var w = wall(); return w ? T.cabinetPoint(w, { index: lastCabinet(w) }) : null; }],
            body: 'Drag the processor onto the screen: its unplaced ports fill in order up to the port under your cursor, so a drop on the last cabinet takes them all. Nothing lands on hardware by itself.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var p = proc();
                t.mem.before = wallPins().length;
                // The drop lands the unplaced ports up to the port under the
                // cursor (2026-09-24), so the guide drops on the LAST cabinet
                // to take the whole wall the way it always did.
                return t.drag('[data-hwdock="processor-' + p.id + '"]', t.cabinetPoint(wall(), { index: lastCabinet(wall()) })).then(function () {
                    return t.wait(function () { return wallPins().length > t.mem.before; });
                });
            },
            check: function (mem) {
                var ps = wallPins();
                if (ps.length <= mem.before) return null;
                var socks = ps.map(function (p) { return Number(p.port); }).sort(function (a, b) { return a - b; });
                var name = proc() && proc().name ? proc().name : '';
                var odd = proc() && proc().redundancy && socks.every(function (s) { return s % 2 === 1; });
                return ps.length + ' ports on ' + (odd ? 'the odd sockets ' : 'sockets ') + socks[0] + ' to ' + socks[socks.length - 1]
                    + (name ? ', labeled ' + name + '-' + socks[0] + ' …' : '')
                    + (odd ? ' Their returns ride the even sockets.' : '.');
            }
        },
        releasePort: {
            target: function () {
                var c = card(); var n = lastPinnedSocket();
                return c && n ? '[data-hwdock="port-' + c.id + '-' + n + '"]' : '#hardware-dock-body .hw-dock-tile';
            },
            place: 'top', title: 'Release a port',
            body: 'Drag a port chip back onto the tray and its run comes off the socket. Nothing is ever unpinned silently.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var c = card(); var n = lastPinnedSocket();
                t.mem.socket = n;
                t.mem.before = wallPins().length;
                return t.drag('[data-hwdock="port-' + c.id + '-' + n + '"]', dockDropPoint()).then(function () {
                    return t.wait(function () { return wallPins().length < t.mem.before; });
                });
            },
            check: function (mem) {
                if (wallPins().length !== mem.before - 1) return null;
                var flag = $('#hw-dock-flag');
                var red = flag && !flag.classList.contains('hw-dock-flag-ok');
                return 'Socket ' + mem.socket + ' is free again' + (red ? '; the flag turns red: one screen not all attached.' : '.');
            }
        },
        attachmentFlag: {
            target: '#hw-dock-flag', place: 'top', title: 'The attachment flag',
            body: 'Red with a screen count while any port is off the hardware, green when everything is held. Click it to list the screens.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                return t.click('#hw-dock-flag').then(function () {
                    return t.wait(function () { return flagRows().length ? flagRows() : null; }, 2500);
                }).then(function () { return t.spot($('#hw-dock-attach')); })
                .then(function () { return t.pause(PACE.opened); });
            },
            check: function () {
                var rows = flagRows();
                if (!rows.length) return null;
                var name = rows[0].querySelector('.hw-dock-attach-name');
                var cnt = rows[0].querySelector('.hw-dock-attach-cnt');
                return (name ? name.textContent : 'One screen') + ': ' + (cnt ? cnt.textContent : 'not all attached') + '.';
            },
            after: function () { closeFlag(); }
        },
        pinPort: {
            target: function () { var c = card(); return c ? '[data-hwdock="port-' + c.id + '-' + sparePinSocket() + '"]' : '#hardware-dock-body .hw-dock-tile'; },
            place: 'top', title: 'Pin a port by hand',
            avoid: [function () { var w = wall(); return w ? T.cabinetPoint(w, { port: unpinnedScreenPort() }) : null; }],
            body: 'Drag a spare port chip onto the run that lost its port and that screen port is pinned to this socket, wherever it is on the processor.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var c = card();
                var num = unpinnedScreenPort();
                var sock = sparePinSocket();
                t.mem.num = num;
                t.mem.sock = sock;
                return t.drag('[data-hwdock="port-' + c.id + '-' + sock + '"]', t.cabinetPoint(wall(), { port: num })).then(function () {
                    return t.wait(function () { return wallPins().some(function (p) { return Number(p.port) === sock; }); });
                });
            },
            check: function (mem) {
                if (!wallPins().some(function (p) { return Number(p.port) === mem.sock; })) return null;
                var flag = $('#hw-dock-flag');
                var ok = flag && flag.classList.contains('hw-dock-flag-ok');
                return 'Screen port ' + mem.num + ' is pinned to socket ' + mem.sock + (ok ? '; the flag is green again.' : '.');
            }
        },
        // The right-click clears (Matt, 2026-09-15: "Release port also
        // needs to have a right click function in the tutorial ... clear
        // the entire breakout or breakout box or sending card/processor").
        // The app's own context menu (app-dock-menus.js _prepareClearMenu)
        // offers one Clear per target: a run on the wall clears that screen
        // port; a card or a breakout box header clears every port on it;
        // a circuit chip clears that circuit; a multi header clears the
        // multi; a distro header clears every multi on it.
        clearPortByMenu: {
            target: '#main-canvas', place: 'top', title: 'Clear a port with a right-click',
            avoid: [function () { var w = wall(), n = handPinnedScreenPort(); return w && n ? T.cabinetPoint(w, { port: n }) : null; }],
            body: 'Right-click a run on the wall and pick Clear port: that screen port comes off its socket and the flag turns red. Undo puts it back.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var w = wall(), n = handPinnedScreenPort();
                if (!n) throw new Error('no pinned port to clear');
                t.mem.num = n;
                t.mem.before = wallPins().length;
                return t.rightClick(t.cabinetPoint(w, { port: n })).then(function () {
                    t.mem.label = clearLabel();
                    return t.pickMenu('hw-clear');
                }).then(function () {
                    return t.wait(function () { return wallPins().length < t.mem.before; });
                });
            },
            check: function (mem) {
                var still = wallPins().some(function (p) { return Number(p.index) + 1 === mem.num; });
                if (still || wallPins().length !== mem.before - 1) return null;
                return (mem.label || 'Clear port') + ': screen port ' + mem.num + ' is off its socket'
                    + (flagOk() ? '.' : '; the flag is red, ' + flagCount() + ' screen not all attached.');
            }
        },
        clearCard: {
            target: function () { var c = card(); return c ? '[data-hwdock="card-' + c.id + '"]' : '[data-hwdock^="card-"]'; },
            place: 'top', title: 'Clear the whole processor',
            avoid: [function () { var c = card(); return c ? '[data-hwdock="card-' + c.id + '"]' : null; }],
            body: 'Right-click the header over the processor&rsquo;s ports and pick Clear: every port on it comes off in one undoable step, and the flag counts what is unattached.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var c = card();
                t.mem.before = wallPins().length;
                return t.rightClick('[data-hwdock="card-' + c.id + '"]').then(function () {
                    t.mem.label = clearLabel();
                    return t.pickMenu('hw-clear');
                }).then(function () {
                    return t.wait(function () { return wallPins().length === 0; });
                });
            },
            check: function (mem) {
                if (!mem.before || wallPins().length) return null;
                return (mem.label || 'Clear') + ': ' + mem.before + ' ports came off; the wall holds none'
                    + (flagOk() ? '.' : ', and the flag reads ' + flagCount() + ' screen not all attached.');
            }
        },
        snakePorts: {
            target: '#hardware-dock-body .hw-dock-grid', place: 'top', title: 'Snake the ports',
            body: 'Hold Alt and sweep across port chips, then right-click and pick Snake. Four ports ride one home run.',
            before: function () { switchView('data-flow'); closeSheet(); },
            act: function (t) {
                var c = card();
                var face = function (n) { return $('[data-hwdock="port-' + c.id + '-' + n + '"]'); };
                var last;
                // The press on the first chip, then a slow pass across the
                // next three with a mousemove per frame (app-dock-sweep.js
                // _traySweepExtend lights each chip as the cursor crosses
                // it), a rest with the four lit, then the right-click.
                return t.hover(face(1), { badge: 'Alt' }).then(function (p) {
                    press(true);
                    mouse('mousedown', face(1), p.x, p.y, { altKey: true, buttons: 1 });
                    return t.pause(PACE.dragPress);
                }).then(function () {
                    return [2, 3, 4].reduce(function (chain, n) {
                        return chain.then(function () {
                            var q = centerOf(face(n));
                            last = q;
                            return animateTo(q.x, q.y, function (x, y) {
                                mouse('mousemove', document, x, y, { altKey: true, buttons: 1 });
                            }, PACE.sweep);
                        });
                    }, Promise.resolve());
                }).then(function () {
                    mouse('mousemove', document, last.x, last.y, { altKey: true, buttons: 1 });
                    mouse('mouseup', document, last.x, last.y, { altKey: true, buttons: 0 });
                    press(false);
                    return t.pause(PACE.sweepRest);
                }).then(function () {
                    return t.rightClick(last);
                }).then(function () {
                    return t.pickMenu('hw-snake-n0');
                }).then(function () {
                    return t.wait(function () { var s = snake(); return s && s.members && s.members.length === 4 ? s : null; });
                });
            },
            check: function () {
                var s = snake();
                if (!s || !s.members || s.members.length !== 4) return null;
                var tag = A().snakeTagText ? A().snakeTagText(s, false) : (s.name || 'SNAKE A');
                return tag + ' carries four ports on one home run.';
            }
        },
        cableSheet: {
            target: '#hardware-dock-body .hw-dock-cablebtn-data', place: 'top', title: 'The cable sheet',
            body: 'The &#8801; over the processor&rsquo;s ports flips its chips into a cable sheet: tick, port, screen and home run, one row per port.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                return t.click('#hardware-dock-body .hw-dock-cablebtn-data').then(function () {
                    return t.wait(sheetOpen);
                }).then(function () { return t.spot($('#hardware-dock-body .hw-dock-cablesheet-data')); })
                .then(function () { return t.pause(PACE.opened); });
            },
            check: function () { return sheetOpen() ? 'The chips are a sheet now; the snake reads as one folded row.' : null; },
            after: function (next) { if (!next || !next.sheetStep) closeSheet(); }
        },
        snakeHomeRun: {
            sheetStep: true,
            target: function () { var o = owner(), s = snake(); return o && s ? '[data-lrd-field="data-snake-ft-' + o.id + '-' + s.id + '"]' : '[data-lrd-field^="data-snake-ft-"]'; },
            place: 'top', title: 'The snake&rsquo;s home run',
            body: 'Type the snake&rsquo;s home run on its row, in the show&rsquo;s cable unit. Tab walks down the column to the next length.',
            before: function () { switchView('data-flow'); openSheet(); },
            act: function (t) {
                var o = owner(), s = snake();
                var key = 'data-snake-ft-' + o.id + '-' + s.id;
                return t.type('[data-lrd-field="' + key + '"]', '100').then(function () {
                    return t.wait(function () { var q = snake(); return q && Number(q.ft) === 100; });
                }).then(function () {
                    return t.wait(function () { return $('[data-lrd-field="' + key + '"]'); }, 2000);
                }).then(function (el) {
                    if (!el) return;
                    el.focus();
                    return t.hover(el, { badge: 'Tab' }).then(function () {
                        t.key('Tab', {}, el);
                        return t.pause(PACE.rest);
                    });
                });
            },
            check: function () {
                var s = snake();
                return s && Number(s.ft) === 100 ? (s.name || 'SNAKE A') + ' has a 100 ft home run; Tab moved to the next length.' : null;
            }
        },
        loosePortLength: {
            sheetStep: true,
            target: function () { var o = owner(); return o ? '[data-lrd-field="data-cable-ft-' + o.id + '-' + loosePinnedSocket() + '"]' : '[data-lrd-field^="data-cable-ft-"]'; },
            place: 'top', title: 'A loose port&rsquo;s length',
            body: 'A port off the snake carries its own home run: type its length on its row and the chip wears it.',
            before: function () { switchView('data-flow'); openSheet(); },
            act: function (t) {
                var o = owner(); var n = loosePinnedSocket();
                t.mem.socket = n;
                return t.type('[data-lrd-field="data-cable-ft-' + o.id + '-' + n + '"]', '50').then(function () {
                    return t.wait(function () {
                        var q = owner(); var c = q && q.rec && q.rec.portCables && q.rec.portCables[String(n)];
                        return c && Number(c.ft) === 50;
                    });
                });
            },
            check: function (mem) {
                var q = owner(); var c = q && q.rec && q.rec.portCables && q.rec.portCables[String(mem.socket)];
                return c && Number(c.ft) === 50 ? 'Port ' + mem.socket + ' carries its own 50 ft home run.' : null;
            },
            after: function (next) { if (!next || !next.sheetStep) closeSheet(); }
        },
        dataCableTags: {
            target: '#show-data-cable-tags', place: 'right', title: 'Show Cable Tags',
            body: 'Per screen, off by default: tick it and every port prints its snake or its length beside the port on the wall and in the export.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                return t.click('#show-data-cable-tags').then(function () {
                    return t.wait(function () { var w = wall(); return w && w.showDataCableTags === true; });
                });
            },
            check: function () {
                var w = wall();
                return w && w.showDataCableTags === true ? 'The snake and the 50 ft run print as tags beside the ports.' : null;
            }
        },
        redundancy: {
            target: function () { var p = proc(); return p ? '[data-hwpop="proc-' + p.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'Redundancy, one bar',
            body: 'Behind the processor&rsquo;s &#9881; one bar under REDUNDANCY sets it. Per port pairs the sockets, 1 backed by 2, and the header wears a gold pill that reads the shape.',
            window: procGearWindow,
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var p = proc();
                return openGear(t, 'proc-' + p.id).then(function (pop) {
                    if (!pop) throw new Error('the gear popover did not open');
                    // The bar as it stands, read before anything moves.
                    return t.spot(pop).then(function () { return t.pause(1000); });
                }).then(function () {
                    var bar = '[data-lrd-field="processor-redundancy-' + p.id + '"]';
                    var seg = $(bar + ' [data-level="port"]') || $$(bar + ' [data-level]').filter(function (b) { return b.dataset.level !== 'off'; }).pop();
                    if (!seg) throw new Error('no redundancy bar on this unit');
                    t.mem.level = seg.dataset.level;
                    // Then the lit segment, the Sequential / Split / Manual
                    // chips and the gold pill, all seen before the step settles.
                    return t.click(seg, { hover: 400, rest: 1200 });
                }).then(function () {
                    return t.wait(function () { var q = proc(); return q && q.redundancy; });
                });
            },
            check: function (mem) {
                var p = proc();
                if (!p || !p.redundancy) return null;
                var pill = $('#hardware-dock-body .hw-dock-redpill');
                return 'Redundancy is on' + (mem.level === 'port' ? ', per port: the even sockets back up the odd ones' : '')
                    + (pill ? '; the pill reads ' + pill.textContent.trim() + '.' : '.');
            },
            after: function () { closePopover(); }
        },
        // The backup processor (2026-09-25): an option ON the unit, named
        // and otherwise automatic - no second unit is added to the tray.
        backupProcessor: {
            target: function () { var p = proc(); return p ? '[data-hwpop="proc-' + p.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'A backup processor',
            body: 'Under REDUNDANCY, switch BACKUP PROCESSOR on: a second unit of this model mirrors this one on the boxes&rsquo; backup inputs. Name it here; everything else follows the main.',
            window: procGearWindow,
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var p = proc();
                return openGear(t, 'proc-' + p.id).then(function (pop) {
                    if (!pop) throw new Error('the gear popover did not open');
                    var seg = $('[data-lrd-field="processor-backup-' + p.id + '"] [data-level="on"]');
                    if (!seg) throw new Error('no backup processor switch on this unit');
                    return t.click(seg, { hover: 400, rest: 1200 });
                }).then(function () {
                    return t.wait(function () { var q = proc(); return q && q.backupUnit; });
                });
            },
            check: function () {
                var p = proc();
                if (!p || !p.backupUnit) return null;
                return p.backupUnit.name + ' backs up ' + (p.name || p.deviceName) + ' output for output; the header reads Backup: ' + p.backupUnit.name + '.';
            },
            after: function () { closePopover(); }
        },
        // Mixed (owner, 2026-10-29: "on say H series i have 3 16 port
        // cards. and i want card 1 and 2 to be primary and backup but then
        // card 3 i want port level backup"). The guide's own processor is a
        // one-box unit, which has nothing to mix, so an H9 with three
        // 16-port cards goes in the tray beside it (the Add button pressed,
        // the chassis and its cards put in for you, the way the second
        // screen is), then the bar's Mixed, card 1's partner and card 3's
        // split are each pressed for real.
        mixedRedundancy: {
            since: '1.6.0',
            target: function () { var h = chassis(); return h ? '[data-hwpop="proc-' + h.id + '"]' : '#hw-dock-data-controls'; },
            place: 'top', title: 'Mixed redundancy on a chassis',
            avoid: ['#processor-add-btn'],
            body: 'On a chassis like an H9 the bar adds Mixed, and each card picks its own. Here card 1 is backed up 1:1 by card 2, and card 3 splits its own ports.',
            before: function () { switchView('data-flow'); closePopover(); },
            act: function (t) {
                var a = A(), pid = null;
                var bar = function () { return '[data-lrd-field="processor-redundancy-' + pid + '"]'; };
                var cards = function () { var h = chassis(); return h ? h.slots.filter(function (s) { return s.card; }).map(function (s) { return s.card; }) : []; };
                return t.hover('#processor-add-btn').then(function (p) {
                    press(true); ripple(p.x, p.y);
                    return t.pause(200);
                }).then(function () {
                    press(false);
                    return j('POST', '/api/processors', { deviceId: 'novastar-h9' });
                }).then(function (st) {
                    pid = st.resolved[st.resolved.length - 1].id;
                    return [0, 1, 2].reduce(function (chain, i) {
                        return chain.then(function () {
                            return j('PUT', '/api/processors/' + pid + '/slots/' + i, { deviceId: 'novastar-card-h-16xrj45-2xfiber' });
                        });
                    }, Promise.resolve());
                }).then(function () {
                    return a.refreshProcessors();
                }).then(function () {
                    a.saveState('Add Processor');
                    return t.wait(function () { return $('[data-hwpop="proc-' + pid + '"]'); });
                }).then(function (gear) {
                    if (!gear) throw new Error('the H9 did not land in the tray');
                    return t.click('[data-hwpop="proc-' + pid + '"]');
                }).then(function () {
                    return t.wait(function () { var pop = $('#hw-gear-popover'); return pop && pop.style.display === 'block' && $(bar() + ' [data-level="mixed"]'); });
                }).then(function (seg) {
                    if (!seg) throw new Error('no Mixed on the H9 bar');
                    return t.click(bar() + ' [data-level="mixed"]', { hover: 400, rest: 600 });
                }).then(function () {
                    return t.wait(function () { var h = chassis(); return h && h.redundancyMixed && $('[data-lrd-field="processor-card-backup-' + cards()[0].id + '"]'); });
                }).then(function (pick) {
                    if (!pick) throw new Error('the Mixed rows did not come up');
                    var cs = cards();
                    t.mem.cards = cs.map(function (c) { return c.id; });
                    return t.select('[data-lrd-field="processor-card-backup-' + cs[0].id + '"]', cs[1].id);
                }).then(function () {
                    return t.wait(function () { var cs = cards(); return cs[1] && cs[1].backupFor ? cs : null; });
                }).then(function (cs) {
                    if (!cs) throw new Error('card 2 did not take card 1');
                    // The chip the card's face calls OPT Split.
                    var split = $$('[data-lrd-field="processor-card-shape-' + cs[2].id + '"] [data-mode]')
                        .filter(function (c) { return /Split$/.test(c.textContent); })[0];
                    if (!split) throw new Error('no Split chip on card 3');
                    t.mem.split = split.dataset.mode;
                    return t.click(split, { hover: 400, rest: 1200 });
                }).then(function () {
                    return t.wait(function () { var cs = cards(); return cs[2] && cs[2].redundancyShape && cs[2].redundancyShape.mode === t.mem.split; });
                });
            },
            check: function () {
                var h = chassis();
                if (!h || !h.redundancyMixed) return null;
                var cs = h.slots.filter(function (s) { return s.card; }).map(function (s) { return s.card; });
                // card 3 at the split: a port shape that is neither of the others
                var mode = cs[2] && cs[2].redundancyShape ? cs[2].redundancyShape.mode : null;
                if (cs.length < 3 || cs[0].backupCardId !== cs[1].id || !cs[1].backupFor
                        || !mode || ['1to1', 'sequential', 'manual'].indexOf(mode) >= 0) return null;
                return (h.name || h.deviceName) + ' runs Mixed: card 2 backs up card 1 port for port, and card 3 brings its own returns back on ports 9 to 16.';
            },
            after: function () { closePopover(); }
        },
        // Card N (1.6.0): a card nobody named, in an H series, MX2000 or
        // MX6000, reads Card 1, Card 2, Card 3 by its slot everywhere, and
        // its model stays where gear is pulled and in its own settings. The
        // H9 the step before put in has three unnamed cards.
        cardNames: {
            since: '1.6.0',
            target: function () {
                var h = chassis();
                var s = h && (h.slots || []).find(function (x) { return x && x.card; });
                return s ? '[data-hwdock="card-' + s.card.id + '"] .hw-dock-unit-name' : '#hw-dock-data-controls';
            },
            place: 'top', title: 'Cards by slot',
            body: 'A card you haven&rsquo;t named reads Card 1, Card 2, Card 3 by its slot, in the tray, its settings and the binder. Its &#9881; still shows the model under the name.',
            before: function () { switchView('data-flow'); closePopover(); },
            act: function (t) {
                var h = chassis();
                var s = h && (h.slots || []).find(function (x) { return x && x.card; });
                if (!s) throw new Error('there is no chassis card to read');
                t.mem.card = s.card.id;
                return t.click('[data-hwpop="card-' + s.card.id + '"]').then(function () {
                    return t.wait(popover);
                }).then(function (pop) {
                    if (!pop) throw new Error('the card settings did not open');
                    return t.spot(pop).then(function () { return t.pause(PACE.opened); });
                });
            },
            check: function (mem) {
                var name = $('[data-hwdock="card-' + mem.card + '"] .hw-dock-unit-name');
                var pop = popover();
                var found = A()._dockFindCard ? A()._dockFindCard(mem.card) : null;
                var model = found ? found.card.deviceName : '';
                if (!name || name.textContent.trim() !== 'Card 1' || !pop || !model
                        || pop.textContent.indexOf(model) < 0) return null;
                return 'Slot 1 reads Card 1, and its settings name the model, ' + model + '. A name you type still wins.';
            },
            after: function () { closePopover(); }
        },
        overrideRun: {
            target: '#main-canvas', place: 'top', title: 'Take over one run',
            body: 'Hold Alt and the run under the cursor lights up. Alt+click takes that port over: click its first cabinet to start again there, then the rest in a new order, and Esc when done.',
            before: function () { switchView('data-flow'); closePopover(); },
            act: function (t) {
                var w = wall();
                var pt = t.cabinetPoint(w, { port: 2 });
                // Port 2 redrawn in a new order: a click on its first
                // cabinet cuts the run back to it, and its other cabinets
                // are clicked again as a snake row by row (column by column
                // where the walk already ran it row by row).
                var seed = A().calculatePortAssignments(w).filter(function (i) { return i.port === 2; })
                    .map(function (i) { return i.panel; });
                var snake = function (major, minor) {
                    return seed.slice(1).sort(function (a, b) {
                        if (a[major] !== b[major]) return a[major] - b[major];
                        return (a[major] - seed[0][major]) % 2 ? b[minor] - a[minor] : a[minor] - b[minor];
                    });
                };
                var key = function (p) { return p.row + ',' + p.col; };
                var rest = snake('row', 'col');
                if (rest.map(key).join(' ') === seed.slice(1).map(key).join(' ')) rest = snake('col', 'row');
                var clicks = seed.length ? [seed[0]].concat(rest) : [];
                t.mem.clicked = clicks.map(key);
                return t.moveTo(pt, { badge: 'Alt' }).then(function () {
                    A().updateOverrideHover(true, pt.worldX, pt.worldY);
                    return t.pause(PACE.hover + 150);   // the lit run, read
                }).then(function () {
                    press(true);
                    t.canvasDown(pt, { altKey: true });
                    return t.pause(80);
                }).then(function () {
                    t.canvasUp(pt, { altKey: true });
                    press(false);
                    ripple(pt.x, pt.y);
                    return t.wait(function () { return A()._overrideEditing; }, 2500);
                }).then(function () {
                    badge('');
                    return t.pause(PACE.rest);
                }).then(function () {
                    return clicks.reduce(function (chain, panel) {
                        return chain.then(function () {
                            var live = (A().project.layers || []).find(function (l) { return l.id === w.id; }) || w;
                            var q = t.cabinetPoint(live, { index: live.panels.findIndex(function (p) {
                                return p.row === panel.row && p.col === panel.col; }) });
                            if (!q) return;
                            return t.hover(q).then(function () {
                                press(true);
                                t.canvasDown(q, {});
                                return t.pause(70);
                            }).then(function () {
                                t.canvasUp(q, {});
                                press(false);
                                ripple(q.x, q.y);
                                return t.pause(PACE.rest);
                            });
                        });
                    }, Promise.resolve());
                }).then(function () {
                    t.key('Escape', {}, document);
                    return t.pause(PACE.rest);
                });
            },
            // Passes only when the clicks landed: port 2 is taken over and
            // its path is the cabinets clicked, in the order clicked.
            check: function (mem) {
                var w = wall();
                var ov = (w && w.customPortOverrides) || [];
                if (!ov.includes(2) || !mem.clicked || !mem.clicked.length) return null;
                var path = ((w.customPortPaths || {})[2] || []).map(function (e) { return e.row + ',' + e.col; });
                if (path.join(' ') !== mem.clicked.join(' ')) return null;
                return 'Port 2 is redrawn: its ' + path.length + ' cabinets run in the order they were '
                    + 'clicked, and the rest of the screen keeps its runs.';
            }
        },
        // A breakout box (Matt, 2026-09-15: "show how to set breakout
        // boxes"). Behind the CARD's gear (app-processors.js
        // _buildCardGearContent): a picker of the boxes that fit its trunks
        // and a + that adds one. On the demo MX40 Pro a CVT10 takes ports
        // 1-10 onto its own strip in the tray, so the box lands AFTER the
        // data steps that read those ports off the card - see TOURS.
        addBreakoutBox: {
            target: function () { var c = card(); return c ? '[data-hwpop="card-' + c.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'Add a breakout box',
            avoid: [function () { var c = card(); return c ? '[data-lrd-field="processor-cvt-add-' + c.id + '"]' : null; },
                    function () { var c = card(); var p = c && $('[data-lrd-field="processor-cvt-add-' + c.id + '"]'); return p ? p.nextElementSibling : null; }],
            body: 'Behind the &#9881; over the processor&rsquo;s ports the picker lists only the boxes that fit its trunks. Pick a CVT10-S and press +: the box appears in the tray with its ten sockets, numbered as its face reads.',
            before: function () { switchView('data-flow'); closePopover(); },
            act: function (t) {
                var c = card();
                var picker = '[data-lrd-field="processor-cvt-add-' + c.id + '"]';
                return t.click('[data-hwpop="card-' + c.id + '"]').then(function () {
                    return t.wait(popover);
                }).then(function (pop) {
                    if (!pop) throw new Error('the processor\'s gear popover did not open');
                    return t.spot(pop).then(function () { return t.pause(900); });
                }).then(function () {
                    var sel = $(picker);
                    if (!sel) throw new Error('no box picker on this processor');
                    t.mem.offered = Array.prototype.slice.call(sel.options).filter(function (o) { return o.value; }).length;
                    return t.select(sel, 'novastar-cvt10');
                }).then(function () {
                    return t.pause(400);
                }).then(function () {
                    var sel = $(picker);
                    var add = sel && sel.nextElementSibling;
                    if (!add) throw new Error('no + beside the picker');
                    return t.click(add);
                }).then(function () {
                    return t.wait(box, 6000);
                }).then(function (b) {
                    // The box's strip lands at the tray's fold: the hand
                    // goes to its header (moveTo scrolls it into view), the
                    // popover follows its gear, and the ring is measured
                    // again where it now stands.
                    if (!b) return;
                    var head = $('[data-hwdock="box-' + b.id + '"]');
                    if (!head) return;
                    return t.moveTo(head).then(function () {
                        if (A()._hwPopoverReflow) A()._hwPopoverReflow();
                        var pop = popover();
                        return pop ? t.spot(pop) : null;
                    });
                }).then(function () { return t.pause(1000); });
            },
            check: function (mem) {
                var b = box(), p = proc();
                if (!b) return null;
                var n = (b.ports || []).length;
                var locals = (b.ports || []).map(function (q) { return q.localNumber || q.number; });
                var span = locals.length ? Math.min.apply(null, locals) + ' to ' + Math.max.apply(null, locals) : '';
                return (b.displayTitle || b.deviceName) + ' is on ' + (p && p.name ? p.name : 'the unit') + ' with ' + n + ' sockets'
                    + (span ? ', ' + span + ' on its face' : '') + '; the picker offered ' + mem.offered + ' boxes that fit this unit.';
            },
            after: function () { closePopover(); }
        },
        // Single mode or multimode (1.6.0; owner, 2026-11-04: "We need to add
        // single mode and multi mode for the fiber ... if the M variants are
        // selected then the fiber will be multimode yes"). The CVT10 the
        // step above added is the CVT10-S; its tray header says Single mode
        // (app-dock.js _dockPlaceBoxModeTag). Nothing changes: the hand goes
        // to the tag, and the check reads the picker's order off the same
        // list the gear builds (_cardBoxFits).
        fiberMode: {
            since: '1.6.0',
            target: function () { var b = box(); return b ? '[data-lrd-field="box-fiber-mode-' + b.id + '"]' : '#hardware-dock-body .hw-dock-fiber-mode'; },
            place: 'top', title: 'Single mode or multimode',
            body: 'NovaStar makes the CVT10, CVT10 Pro and CVT4K in single mode and multimode, and the picker lists the single mode boxes first. Each box says which on its header, and the two never share a fiber cable.',
            before: function () { switchView('data-flow'); closePopover(); closeSheet(); },
            act: function (t) {
                var b = box();
                if (!b) throw new Error('no breakout box on the processor');
                var sel = '[data-lrd-field="box-fiber-mode-' + b.id + '"]';
                return t.wait(function () { return $(sel); }, 6000).then(function (tag) {
                    if (!tag) throw new Error('the box\'s header shows no fiber mode');
                    return t.moveTo(tag);
                }).then(function () { return t.pause(PACE.rest); });
            },
            check: function () {
                var b = box(), c = card(), a = A();
                if (!b || !c || a.boxFiberMode(b) !== 'single') return null;
                if (!$('[data-lrd-field="box-fiber-mode-' + b.id + '"]')) return null;
                var fits = a._cardBoxFits(c).filter(function (d) { return d.fiberMode; });
                var singles = fits.filter(function (d) { return d.fiberMode === 'single'; }).map(function (d) { return d.name; });
                var multis = fits.filter(function (d) { return d.fiberMode === 'multi'; }).map(function (d) { return d.name; });
                var order = fits.map(function (d) { return d.fiberMode; }).join(' ');
                if (!singles.length || !multis.length || order !== singles.map(function () { return 'single'; })
                        .concat(multis.map(function () { return 'multi'; })).join(' ')) return null;
                return (b.displayTitle || b.deviceName) + ' takes single mode fiber. The picker lists '
                    + singles.join(', ') + ', then ' + multis.join(', ') + '.';
            }
        },
        // Fiber to the box (2026-09-25: "after we get it all working we need
        // to add to advanced guide"): the CVT10 the step above added gets a
        // TAC through its sheet's Fiber section - New TAC, 12 strands, 1000
        // ft, ST - and the next step moves its link onto other strands.
        boxFiber: {
            target: function () { var b = box(); return b ? '[data-lrd-field="data-cable-sheet-' + b.id + '"]' : '#hardware-dock-body .hw-dock-cablebtn-data'; },
            place: 'top', title: 'Fiber to the box',
            body: 'A box&rsquo;s fiber is a TAC, an MTP or an opticalCON, set at the top of its &#8801; sheet. A TAC, MTP or opticalCON is shared by the strand: the next box that picks it takes the next free strands.',
            before: function () { switchView('data-flow'); closePopover(); closeSheet(); },
            act: function (t) {
                var b = box();
                if (!b) throw new Error('no breakout box on the processor');
                var base = 'fiber-new-' + b.id + '-p1';
                var go = function (key) {
                    return function () { return t.wait(function () { return $('[data-lrd-field="' + key + '"]'); }); };
                };
                var chain = boxSheetOpen() ? Promise.resolve()
                    : t.click('[data-lrd-field="data-cable-sheet-' + b.id + '"]').then(function () { return t.wait(boxSheetOpen); });
                return chain.then(function () {
                    return t.spot($('[data-lrd-fiber-row="' + b.id + '"]'));
                }).then(function () { return t.pause(PACE.opened); })
                .then(go('fiber-link-cable-' + b.id + '-p1'))
                .then(function () { return t.select('[data-lrd-field="fiber-link-cable-' + b.id + '-p1"]', 'new:tac'); })
                .then(go(base + '-strands-12'))
                .then(function () { return t.click('[data-lrd-field="' + base + '-strands-12"]'); })
                .then(go(base + '-ft'))
                .then(function () { return t.type('[data-lrd-field="' + base + '-ft"]', '1000', { enter: true }); })
                .then(go(base + '-conn-ST'))
                .then(function () { return t.click('[data-lrd-field="' + base + '-conn-ST"]'); })
                .then(function () { return t.wait(boxLink, 6000); });
            },
            check: function () {
                var bl = boxLink();
                if (!bl) return null;
                var c = bl.cable;
                return (c.name || 'TAC A') + ' · ' + c.strands + ' strands · ' + (c.ft ? c.ft + '\' · ' : '')
                    + (c.connector || '') + '. ' + bl.title + ' rides ' + boxStrandsText(bl) + '.';
            },
            after: function (next) { if (!next || !next.fiberStep) closeBoxSheet(); }
        },
        fiberStrands: {
            fiberStep: true,
            target: function () { var b = box(); return b ? '[data-lrd-field="fiber-strand-' + b.id + '-p1-0"]' : '#hardware-dock-body .hw-dock-fiber-strand'; },
            place: 'top', title: 'Pick the strands',
            body: 'Click a strand to move the link, here onto 3 Green and 4 Brown. Edit reads a cable by color, number or sub-unit, NovaStar and Megapixel boxes have BiDi for one strand a link, and the binder maps every strand.',
            before: function () { switchView('data-flow'); closePopover(); openBoxSheet(); },
            act: function (t) {
                var b = box();
                // The pick is the chip swapped for a select in place, not
                // app state: a tray rebuild (a late save's echo restates
                // the tray) puts the chip back and the pick is gone. The
                // Go to that lands here restores the show, and its echoes
                // rebuilt the tray just after the click: "the strand pick
                // did not open" (1.6.0 QA, 1 run in 4 under a loaded
                // machine). So the hand clicks the chip again, up to three
                // times, until the strand has moved.
                var move = function (i, to, tries) {
                    tries = tries || 1;
                    var chip = '[data-lrd-field="fiber-strand-' + b.id + '-p1-' + i + '"]';
                    var pick = '[data-lrd-field="fiber-strand-pick-' + b.id + '-p1-' + i + '"]';
                    var moved = function () { var bl = boxLink(); return bl && bl.link.strands[i] === to; };
                    return t.wait(function () { return $(chip) || $(pick); }).then(function () {
                        return $(pick) ? null : t.click(chip);
                    }).then(function () {
                        return t.wait(function () { return $(pick); }, 1500);
                    }).then(function (el) {
                        if (!el) return null;
                        return t.select(pick, String(to)).then(function () { return t.wait(moved, 3000); });
                    }).then(function (ok) {
                        if (ok || moved()) return true;
                        if (tries >= 3) throw new Error('the strand pick did not open');
                        return move(i, to, tries + 1);
                    });
                };
                return move(0, 3).then(function () { return move(1, 4); })
                    .then(function () { return t.pause(PACE.rest); });
            },
            check: function () {
                var bl = boxLink();
                if (!bl || bl.link.strands.join() !== '3,4') return null;
                return bl.title + ' rides ' + boxStrandsText(bl) + ' of ' + (bl.cable.name || 'TAC A') + '; 1 and 2 are spare for the next box.';
            },
            after: function (next) { if (!next || !next.fiberStep) closeBoxSheet(); }
        },
        // An extension at the box end (2026-11-02: "MTP cant run direct to
        // X1 for example it would need an extension beyond that ... same
        // goes for Tac cable"): + Extension on the box's OPT 1 link, which
        // starts as a fan-out from the TAC's ST to LC duplex (a TAC's first
        // pick; an MTP's is a duplex patch), then 10 ft typed. The length
        // is the guide's pick, not a fact about the box.
        fiberExtension: {
            fiberStep: true,
            since: '1.6.0',
            // the link's row: there before + Extension and after it
            target: function () { var b = box(); return b ? '[data-lrd-fiber-link="' + b.id + ':p1"]' : '#hardware-dock-body .hw-dock-cable-fiber'; },
            place: 'top', title: 'Extend a TAC or MTP',
            body: 'A TAC or MTP doesn&rsquo;t always plug straight into the box. On a link, + Extension adds a fan-out to LC duplex off a TAC or a duplex patch off an MTP; then give its length for the pull sheet and the binder.',
            before: function () { switchView('data-flow'); closePopover(); openBoxSheet(); },
            act: function (t) {
                var b = box();
                if (!b) throw new Error('no breakout box on the processor');
                var base = b.id + '-p1';
                var ext = function () { var bl = boxLink(); return bl && bl.link.extension ? bl.link.extension : null; };
                var add = '[data-lrd-field="fiber-ext-add-' + base + '"]';
                return t.wait(function () { return $(add); }).then(function () {
                    return t.click(add);
                }).then(function () {
                    // a TAC's extension starts as a fan-out to LC duplex
                    return t.wait(function () { var e = ext(); return e && e.boxEnd === 'LC duplex'; }, 6000);
                }).then(function () {
                    return t.wait(function () { return $('[data-lrd-field="fiber-ext-ft-' + base + '"]'); });
                }).then(function () {
                    return t.type('[data-lrd-field="fiber-ext-ft-' + base + '"]', '10', { enter: true });
                }).then(function () {
                    return t.wait(function () { var e = ext(); return e && Number(e.ft) === 10; }, 6000);
                }).then(function () { return t.pause(PACE.rest); });
            },
            check: function () {
                var bl = boxLink(), a = A();
                var e = bl && bl.link.extension;
                if (!e || e.boxEnd !== 'LC duplex' || Number(e.ft) !== 10) return null;
                return bl.title + ' on ' + (bl.cable.name || 'TAC A') + ' now has its extension: ' + a.fiberExtensionText(e, bl.cable) + '.';
            },
            after: function () { closeBoxSheet(); }
        },
        // Jumpers, link by link (1.3.4, app-jumpers.js): the screen's own
        // vertical and horizontal lengths on the Data sidebar, and the same
        // pair on the Power sidebar.
        dataJumpers: {
            target: '#data-jump-v', place: 'right', title: 'Jumpers, link by link',
            avoid: ['#data-jump-h'],
            body: 'The next cabinet above or below takes a vertical jumper, the one beside a horizontal one; blank means the panels link themselves. One not touching takes a long jumper, rounded up to 3, 6, 10, 15 or 25 ft, and a tag.',
            before: function () { switchView('data-flow'); closeSheet(); },
            act: function (t) {
                return t.type('#data-jump-v', '2').then(function () {
                    return t.type('#data-jump-h', '3');
                }).then(function () {
                    return t.wait(function () { var w = wall(); return w && Number(w.dataJumpV) === 2 && Number(w.dataJumpH) === 3; });
                });
            },
            check: function () {
                var w = wall();
                if (!w || Number(w.dataJumpV) !== 2 || Number(w.dataJumpH) !== 3) return null;
                return (w.name || 'The screen') + ' takes 2 ft vertical and 3 ft horizontal data jumpers.';
            }
        },
        powerJumpers: {
            target: '#power-jump-v', place: 'right', title: 'Power jumpers',
            avoid: ['#power-jump-h'],
            body: 'The same two lengths for the power runs, per screen. The defaults for a new screen live in Preferences.',
            before: function () { switchView('power'); },
            act: function (t) {
                return t.type('#power-jump-v', '2').then(function () {
                    return t.type('#power-jump-h', '3');
                }).then(function () {
                    return t.wait(function () { var w = wall(); return w && Number(w.powerJumpV) === 2 && Number(w.powerJumpH) === 3; });
                });
            },
            check: function () {
                var w = wall();
                if (!w || Number(w.powerJumpV) !== 2 || Number(w.powerJumpH) !== 3) return null;
                return (w.name || 'The screen') + ' takes 2 ft vertical and 3 ft horizontal power jumpers.';
            }
        },
        // One power jumper name per connector (1.6.0, app-pull-list.js
        // pullPowerJumpName): the show's names live in the Export dialog's
        // Pull Sheet section (project.pullSheet, one undo step each); the
        // Preferences hold the names a new show starts with. The wall is
        // TRUE1 here, so the TRUE1 name is the one its rows print.
        jumperNames: {
            since: '1.6.0',
            window: 'export:pull-sheet',
            target: '#export-pull-sheet-power-jump-name-true1', place: 'left', title: 'A name for each jumper',
            avoid: ['#export-pull-sheet-power-jump-name-true1', '#export-pull-sheet-power-jump-name-powercon'],
            body: 'The pull sheet names TRUE1 and powerCON jumpers apart. Type what your shop calls them in the Export dialog; Preferences holds the names a new show starts with.',
            before: function () {
                switchView('power');
                var a = A();
                if (!exportOpen() || ($('#export-format') && $('#export-format').value !== 'pull-sheet')) {
                    a.openExportModal('pull-sheet');
                }
            },
            act: function (t) {
                return t.type('#export-pull-sheet-power-jump-name-true1', 'TRUE1 Jumper').then(function () {
                    return t.wait(function () {
                        return A().getPullSheetSettings().powerJumpNameTrue1 === 'TRUE1 Jumper';
                    });
                }).then(function (ok) {
                    if (!ok) throw new Error('the show did not take the jumper name');
                    return t.pause(PACE.rest);
                });
            },
            check: function () {
                var s = A().getPullSheetSettings();
                if (s.powerJumpNameTrue1 !== 'TRUE1 Jumper') return null;
                return 'TRUE1 jumpers print as TRUE1 Jumper, one row per length; a powerCON screen\'s print as '
                    + s.powerJumpNamePowercon + '.';
            },
            after: function () { closeExport(); }
        },
        // Panel counts on the pull sheet (1.6.0, app-pull-list.js
        // pullPanelCounts): the Export dialog's Edit rows opens the pull
        // sheet editor, and each screen's position has a row per panel type
        // it hangs, named by the panel saved on it (the Name the panel
        // step), blank and hidden cabinets left out.
        pullPanels: {
            since: '1.6.0',
            target: function () { return pullSheetOpen() ? PANEL_ROW : '#export-pull-sheet-edit-rows'; },
            place: 'left', title: 'Panels on the pull sheet',
            avoid: ['#export-pull-sheet-edit-rows'],
            window: ['export:pull-sheet', 'pull-sheet'],
            body: 'Edit rows opens the pull sheet. Each screen gets a row for every panel type it hangs, half tiles on rows of their own, and a blank cabinet isn&rsquo;t counted.',
            before: function () {
                closePullSheet();
                var a = A();
                if (!exportOpen() || ($('#export-format') && $('#export-format').value !== 'pull-sheet')) {
                    a.openExportModal('pull-sheet');
                }
            },
            act: function (t) {
                return t.click('#export-pull-sheet-edit-rows').then(function () {
                    return t.wait(function () { return pullSheetOpen() && $(PANEL_ROW); }, 6000);
                }).then(function (row) {
                    if (!row) throw new Error('the pull sheet did not list the panels');
                    return t.spot(row).then(function () { return t.pause(PACE.opened); });
                });
            },
            check: function () {
                var w = wall(), row = pullSheetOpen() ? $(PANEL_ROW) : null;
                if (!w || !row) return null;
                var counts = A().pullPanelCounts(w);
                var full = counts[0];
                var blank = (w.panels || []).filter(function (p) { return p && (p.blank || p.hidden); }).length;
                if (!full) return null;
                return 'The pull sheet lists ' + full.qty + ' ' + full.type + ' for ' + (w.name || 'the screen')
                    + (blank ? ', the ' + (blank === 1 ? 'blank cabinet' : blank + ' blank cabinets') + ' left out' : '')
                    + ', and TOTALS adds up every screen.';
            },
            after: function () { closePullSheet(); closeExport(); }
        },
        panelWatts: {
            target: '#power-panel-watts', place: 'right', title: 'Power view and the math',
            avoid: ['[data-mode="power"]', '#power-panel-watts', '#power-amperage-usable'],
            body: 'Voltage, amperage and watts per cabinet set the cabinets a circuit carries and the circuits required. Beside Amperage you see the amps you can use, 16 A of a 20 A breaker on US power.',
            act: function (t) {
                return t.click('[data-mode="power"]').then(function () {
                    return t.type('#power-panel-watts', '150', { enter: true });
                }).then(function () {
                    return t.wait(function () { var w = wall(); return w && Number(w.panelWatts) === 150; });
                });
            },
            check: function () {
                var w = wall();
                if (!w || Number(w.panelWatts) !== 150) return null;
                var req = $('#power-circuits-required') ? $('#power-circuits-required').textContent.trim() : '?';
                var usable = $('#power-amperage-usable') ? $('#power-amperage-usable').textContent.trim() : '';
                if (!usable) return null;
                return '150 W per cabinet at 208 V, ' + usable + '. Circuits required: ' + req + '.';
            }
        },
        // The panel input (1.6.0, app-power.js panelInput): a TRUE1 or
        // powerCON breakout IS the panels' connector; an Edison or L6-20
        // one leaves it to the screen. The demo wall is 208V, so the L6-20
        // breakout is the one that offers the choice. The breakout step
        // after it puts the wall on Multi to TRUE1 for the rest of the tour.
        panelInput: {
            since: '1.6.0',
            target: '#power-breakout-type', place: 'right', title: 'The panel input',
            avoid: ['#power-breakout-type', '#power-panel-input'],
            body: 'Pick Multi to L6-20 and Panel input appears: the connector your panels take. Pick powerCON and the cables, jumpers and splitters all say powerCON.',
            before: function () { switchView('power'); },
            act: function (t) {
                return t.select('#power-breakout-type', 'soca-l620').then(function () {
                    return t.wait(function () {
                        var w = wall(), row = $('#power-panel-input-row');
                        return w && w.powerBreakoutType === 'soca-l620' && row && row.style.display !== 'none';
                    });
                }).then(function (ok) {
                    if (!ok) throw new Error('the Panel input did not come up');
                    return t.select('#power-panel-input', 'powercon');
                }).then(function () {
                    return t.wait(function () { var w = wall(); return w && w.powerPanelInput === 'powercon'; });
                }).then(function (ok) {
                    if (!ok) throw new Error('the screen did not take powerCON');
                    return t.pause(PACE.rest);
                });
            },
            check: function () {
                var w = wall();
                if (!w || w.powerBreakoutType !== 'soca-l620' || A().panelInput(w).id !== 'powercon') return null;
                return (w.name || 'The screen') + ' takes powerCON at the panels: each circuit gets an L6-20 → powerCON cable, and its jumpers and splitters are powerCON.';
            }
        },
        breakoutType: {
            target: '#power-breakout-type', place: 'right', title: 'The breakout',
            body: 'How each multi fans out to the cabinets. Multi to TRUE1 is six circuits a box; the choice drives the gear list.',
            before: function () { switchView('power'); },
            act: function (t) {
                return t.select('#power-breakout-type', 'soca-true1').then(function () {
                    return t.wait(function () { var w = wall(); return w && w.powerBreakoutType === 'soca-true1'; });
                });
            },
            check: function () {
                var w = wall();
                return w && w.powerBreakoutType === 'soca-true1' ? 'Each multi fans out to TRUE1: six circuits a box.' : null;
            }
        },
        addDistro: {
            target: '#power-distro-add', place: 'top', title: 'Add a distro',
            body: 'Add distro puts a power source in the tray. Its multis appear below it, ready to drag onto circuits.',
            before: function () { switchView('power'); },
            act: function (t) {
                return t.click('#power-distro-add').then(function () {
                    return t.wait(function () { return distro() && $('[data-hwdock^="distro-"]'); });
                });
            },
            check: function () {
                var d = distro();
                return d ? (d.name || 'The distro') + ' is in the tray: ' + d.voltage + ' V, ' + (Number(d.phase) === 3 ? '3φ' : '1φ') + ', ' + d.ratingA + ' A.' : null;
            }
        },
        nameDistro: {
            target: function () { var d = distro(); return d ? '[data-lrd-field="distro-name-' + d.id + '"]' : '[data-lrd-field^="distro-name-"]'; },
            place: 'top', title: 'Name the distro',
            body: 'Name it on its header. A distro named SL feeds SL1, SL2, and every circuit label on the wall follows.',
            before: function () { switchView('power'); },
            act: function (t) {
                var d = distro();
                return t.type('[data-lrd-field="distro-name-' + d.id + '"]', 'SL', { enter: true }).then(function () {
                    return t.wait(function () { var q = distro(); return q && q.name === 'SL'; });
                });
            },
            check: function () { var d = distro(); return d && d.name === 'SL' ? 'Its multis are SL1, SL2 …' : null; }
        },
        // The distro's gear (Matt, 2026-09-15: "setting the capacity of
        // the distro and different things like that") - app-power.js
        // _buildDistroGearContent, whose supply rows are 1.5's TYPE, SYSTEM,
        // INPUT and RATING per leg (app-distro-systems.js
        // _buildDistroSupplySection). Each step opens the gear again: one
        // action per step.
        // Input: only the inputs that can feed the distro's system are
        // listed, and picking one sets the rating per leg to its figure.
        distroRating: {
            since: '1.5.0',
            target: function () { var d = distro(); return d ? '[data-hwpop="distro-' + d.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'The distro&rsquo;s input',
            window: distroGearWindow,
            avoid: [function () { var d = distro(); return d ? '[data-lrd-field="distro-input-' + d.id + '"]' : null; }],
            body: 'Behind the distro&rsquo;s &#9881;, Input lists only what can power its System: cams by their amps, L21-30, CEE or Powerlock. Pick 200 A and Rating fills in 200 A per leg.',
            before: function () { switchView('power'); closePopover(); },
            act: function (t) {
                var d = distro();
                t.mem.before = distroUse(d);
                return openDistroGear(t, d).then(function () {
                    var sel = $('[data-lrd-field="distro-input-' + d.id + '"]');
                    if (!sel) throw new Error('the distro has no Input list');
                    // 200 A cams on a US distro; on a distro whose system no
                    // cam can feed, the first input its list offers.
                    var opts = Array.prototype.slice.call(sel.options).filter(function (o) { return o.value; });
                    var pick = opts.find(function (o) { return o.value === 'cam200'; }) || opts[0];
                    if (!pick) throw new Error('the Input list offers nothing');
                    t.mem.pick = pick.value;
                    t.mem.name = pick.textContent.trim();
                    t.mem.rating = Number((/(\d+)\s*A\b/.exec(t.mem.name) || [])[1]) || null;
                    return t.select(sel, pick.value);
                }).then(function () {
                    return t.wait(function () {
                        var q = distro();
                        if (!q || q.input !== t.mem.pick) return false;
                        if (t.mem.rating && Number(q.ratingA) !== t.mem.rating) return false;
                        var lim = A().distroMainLimit(q).limitA;
                        return new RegExp('/' + (+lim.toFixed(1)) + ' A$').test(distroUse(q));
                    });
                }).then(function () { return t.pause(PACE.acted); });
            },
            check: function (mem) {
                var d = distro();
                if (!d || !mem.pick || d.input !== mem.pick) return null;
                var use = distroUse(d);
                var lim = A().distroMainLimit(d).limitA;
                if (!new RegExp('/' + (+lim.toFixed(1)) + ' A$').test(use)) return null;
                return (d.name || 'The distro') + ' takes ' + mem.name + ': ' + d.ratingA
                    + ' A per leg, and the header read ' + mem.before + ', now ' + use + '.';
            },
            after: function () { closePopover(); }
        },
        // The main's continuous limit (1.5, 2026-10-18): a US distro's
        // busiest leg is held to 80% of its rating unless Main 100% rated
        // is ticked. Shown on the setting, not by overloading the demo:
        // ticked the header reads the full rating, unticked 80% again, so
        // the steps after find the distro as it was.
        distroMain: {
            since: '1.5.0',
            target: function () { var d = distro(); return d ? '[data-hwpop="distro-' + d.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'The 80% limit',
            window: distroGearWindow,
            avoid: [function () { var d = distro(); return d ? '[data-lrd-field="distro-main100-' + d.id + '"]' : null; }],
            body: 'A US distro is held to 80% of its rating, so 200 A reads as 160 A. Main 100% rated lifts that; over the limit the header shows a red OVER, and Accept overload turns it amber.',
            before: function () { switchView('power'); closePopover(); },
            act: function (t) {
                var d = distro();
                var box = '[data-lrd-field="distro-main100-' + d.id + '"]';
                var reads = function (pct) {
                    var q = distro();
                    if (!q) return false;
                    var lim = (Number(q.ratingA) || 0) * pct;
                    return new RegExp('/' + (+lim.toFixed(1)) + ' A$').test(distroUse(q));
                };
                t.mem.start = distroUse(d);
                t.mem.note = distroLim(d);
                return openDistroGear(t, d).then(function () {
                    var cb = $(box);
                    if (!cb) throw new Error('Main 100% rated is not on this distro');
                    if (cb.checked) throw new Error('Main 100% rated is already ticked');
                    return t.click(cb, { rest: PACE.acted });
                }).then(function () {
                    return t.wait(function () { var q = distro(); return q && q.main100 && reads(1); });
                }).then(function (on) {
                    if (!on) throw new Error('the header did not read the full rating');
                    t.mem.full = distroUse(distro());
                    // The popover was rebuilt with the change; the tick is
                    // found again by its key.
                    return t.click(box, { rest: PACE.rest });
                }).then(function () {
                    return t.wait(function () { var q = distro(); return q && !q.main100 && reads(0.8); });
                }).then(function () { return t.pause(PACE.rest); });
            },
            check: function (mem) {
                var d = distro();
                if (!d || d.main100 || !mem.full) return null;
                var use = distroUse(d);
                var lim = (Number(d.ratingA) || 0) * 0.8;
                if (!new RegExp('/' + (+lim.toFixed(1)) + ' A$').test(use)) return null;
                return 'Main 100% rated read ' + mem.full + '; unticked, ' + (d.name || 'the distro')
                    + ' is held to ' + use + (distroLim(d) ? ' ' + distroLim(d) : '') + '.';
            },
            after: function () { closePopover(); }
        },
        distroPhase: {
            since: '1.5.0',
            target: function () { var d = distro(); return d ? '[data-hwpop="distro-' + d.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'The distro\'s system',
            window: distroGearWindow,
            avoid: [function () { var d = distro(); return d ? '[data-lrd-field="distro-system-' + d.id + '"]' : null; }],
            body: 'System is the service the distro runs on, US or EU, and the header wears it. Pick 120V 1&phi; and the LEGS line and Balance leave; back on 120/208V 3&phi; they return, with the phasing row under it.',
            before: function () { switchView('power'); closePopover(); },
            act: function (t) {
                var d = distro();
                var system = '[data-lrd-field="distro-system-' + d.id + '"]';
                t.mem.start = distroInfo(d);
                return openDistroGear(t, d).then(function () {
                    return t.select(system, '120');
                }).then(function () {
                    return t.wait(function () { var q = distro(); return q && Number(q.phase) === 1 && /1φ/.test(distroInfo(q)); });
                }).then(function () {
                    return t.pause(800);
                }).then(function () {
                    // Read while the supply stands at 1φ: the header's tag,
                    // and whether the LEGS line is there.
                    var q = distro();
                    t.mem.mid = distroInfo(q);
                    t.mem.midLegs = distroLegs(q);
                    // The popover was rebuilt with the change; the select is
                    // found again by its key.
                    return t.select(system, '120/208');
                }).then(function () {
                    return t.wait(function () { var q = distro(); return q && Number(q.phase) === 3 && /3φ/.test(distroInfo(q)); });
                }).then(function () { return t.pause(800); });
            },
            check: function (mem) {
                var d = distro();
                if (!d || Number(d.phase) !== 3 || !mem.mid || !/1φ/.test(mem.mid)) return null;
                var now = distroInfo(d);
                if (!/3φ/.test(now)) return null;
                return 'At 120V 1φ the header read ' + mem.mid + (mem.midLegs ? '' : ' with no LEGS line') + '; back on 120/208V it reads ' + now
                    + (distroLegs(d) ? ' and the legs are metered again.' : '.');
            },
            after: function () { closePopover(); }
        },
        dropMulti: {
            target: function () { var d = distro(); return d ? '[data-hwdock="slot-' + d.id + '-1"]' : '[data-hwdock^="slot-"]'; },
            place: 'top', title: 'Drag a multi onto the wall',
            avoid: [function () { return multiDropPoint(); }],
            body: 'Drag multi 1 over the screen: the span starts at the first circuit and grows to the one under your cursor, capped at what is free.',
            before: function () { switchView('power'); },
            act: function (t) {
                var d = distro();
                // The circuits on multi 1, read off its chips - the count the
                // header prints (n/6) and the user sees.
                var landed = function () {
                    return $$('[data-hwdock^="tail-' + d.id + '-1-"]').filter(function (f) {
                        var x = f.closest('.lrd-tile'); return x && x.classList.contains('lrd-tile-occupied');
                    }).length;
                };
                t.mem.landed = landed;
                var onWall = function () {
                    var w = wall(); var m = (w && w.powerSocaDistro) || {};
                    return Object.keys(m).some(function (k) { return m[k] === d.id; });
                };
                t.mem.onWall = onWall;
                var slot = '[data-hwdock="slot-' + d.id + '-1"]';
                return t.drag(slot, multiDropPoint()).then(function () {
                    return t.wait(function () { return landed() > 0 || onWall(); }, 8000);
                }).then(function (ok) {
                    // A drop that did not take (a refused hit, a slow commit):
                    // once more, onto the first circuit's middle cabinet.
                    if (ok) return ok;
                    return t.drag(slot, t.cabinetPoint(wall(), { circuit: 0, mid: true })).then(function () {
                        return t.wait(function () { return landed() > 0 || onWall(); }, 8000);
                    });
                });
            },
            check: function (mem) {
                var n = mem.landed ? mem.landed() : 0;
                var d = distro();
                if (!n && mem.onWall && mem.onWall()) return (d.name || 'SL') + ' multi 1 is on the wall.';
                if (!n) return null;
                var size = A().socaBoxSize ? A().socaBoxSize(wall()) : 6;
                return (d.name || 'SL') + ' multi 1 took ' + n + ' of ' + size + ' circuits' + (n < size ? ', all the wall needs.' : '.');
            }
        },
        clearCircuit: {
            target: function () { var d = distro(); return d ? '[data-hwdock="tail-' + d.id + '-1-3"]' : '[data-hwdock^="tail-"]'; },
            place: 'top', title: 'Clear one circuit',
            body: 'Drag one circuit chip back onto the tray and that one circuit comes off; the others stay put.',
            before: function () { switchView('power'); },
            act: function (t) {
                var d = distro();
                var occupied = function () {
                    var tile = $('[data-hwdock="tail-' + d.id + '-1-3"]');
                    tile = tile && tile.closest('.lrd-tile');
                    return tile && tile.classList.contains('lrd-tile-occupied');
                };
                t.mem.wasOccupied = !!occupied();
                return t.drag('[data-hwdock="tail-' + d.id + '-1-3"]', dockDropPoint()).then(function () {
                    return t.wait(function () { return !occupied(); });
                });
            },
            check: function (mem) {
                var d = distro();
                var tile = $('[data-hwdock="tail-' + d.id + '-1-3"]');
                tile = tile && tile.closest('.lrd-tile');
                if (!mem.wasOccupied || !tile || tile.classList.contains('lrd-tile-occupied')) return null;
                var held = $$('[data-hwdock^="tail-' + d.id + '-1-"]').filter(function (f) {
                    var x = f.closest('.lrd-tile'); return x && x.classList.contains('lrd-tile-occupied');
                }).length;
                return 'Circuit 3 is free; ' + held + ' circuits stay on ' + (d.name || 'SL') + ' 1.';
            }
        },
        clearMultiByMenu: {
            target: function () { var d = distro(); return d ? '[data-hwdock="slot-' + d.id + '-1"]' : '[data-hwdock^="slot-"]'; },
            place: 'top', title: 'Clear the whole multi',
            avoid: [function () { var d = distro(); return d ? '[data-hwdock="slot-' + d.id + '-1"]' : null; }],
            body: 'Right-click the multi&rsquo;s header and pick Clear: every circuit on it comes off at once, one undoable step. The multi keeps its number and its type.',
            before: function () { switchView('power'); },
            act: function (t) {
                var d = distro();
                t.mem.before = multiHeld(d, 1);
                return t.rightClick('[data-hwdock="slot-' + d.id + '-1"]').then(function () {
                    t.mem.label = clearLabel();
                    return t.pickMenu('hw-clear');
                }).then(function () {
                    return t.wait(function () { return multiHeld(distro(), 1) === 0; });
                });
            },
            check: function (mem) {
                var d = distro();
                if (!mem.before || multiHeld(d, 1)) return null;
                return (mem.label || 'Clear') + ': ' + mem.before + ' circuits came off ' + (d.name || 'SL') + ' 1; it is free again.';
            }
        },
        multiCableSheet: {
            target: function () { var d = distro(); return d ? '[data-lrd-field="power-cable-sheet-' + d.id + '-1"]' : '#hardware-dock-body .hw-dock-cablebtn'; },
            place: 'top', title: 'The multi&rsquo;s cable sheet',
            body: 'The &#8801; on an occupied multi flips its chips into a sheet: a length and connector per circuit, Tab down the column.',
            before: function () { switchView('power'); },
            act: function (t) {
                var d = distro();
                return t.click('[data-lrd-field="power-cable-sheet-' + d.id + '-1"]').then(function () {
                    return t.wait(function () { return $('#hardware-dock-body [data-lrd-field^="power-cable-ft-"]'); });
                }).then(function (ft) {
                    if (!ft) throw new Error('the sheet did not open');
                    var m = ft.dataset.lrdField.match(/^power-cable-ft-(\d+)-(\d+)$/);
                    t.mem.circuit = m ? Number(m[2]) : null;
                    return t.spot(ft.closest('.hw-dock-cablesheet') || ft).then(function () {
                        return t.pause(PACE.opened);
                    }).then(function () { return t.type(ft, '25'); });
                }).then(function () {
                    return t.wait(function () {
                        var w = wall(); var c = w && w.powerCircuitCables && w.powerCircuitCables[t.mem.circuit];
                        return c && Number(c.ft) === 25;
                    });
                });
            },
            check: function (mem) {
                var w = wall(); var c = w && w.powerCircuitCables && w.powerCircuitCables[mem.circuit];
                if (!c || Number(c.ft) !== 25) return null;
                var text = A().powerCircuitCable ? A().powerCircuitCable(w, mem.circuit) : null;
                return 'The first circuit carries ' + (text && text.text ? text.text : 'a 25 ft cable') + '.';
            },
            after: function () {
                var d = distro();
                if (d && A()._setCableSheetOpen) { A()._setCableSheetOpen(d.id, 1, false); if (mode() === 'power') A().renderHardwareDock(); }
            }
        },
        // Feet or meters (1.5, app-cable-units.js): the Unit select beside
        // the jumper fields sets the show's one cable unit. Its own change
        // handler asks first when lengths are typed - a native confirm the
        // guide's hand cannot answer - so the act sets the unit through
        // setCableUnit(unit, false), the path an answered Yes takes. It goes
        // to m and back to ft: the steps after are written in feet.
        cableUnit: {
            since: '1.5.0',
            target: '#power-jump-unit', place: 'right', title: 'Feet or meters',
            avoid: ['#power-jump-unit'],
            body: 'Unit, under the jumper fields, switches the whole show between ft and m, and every cable length follows. Here it goes to m and back to ft.',
            before: function () { switchView('power'); },
            act: function (t) {
                var label = function () {
                    var v = $('#power-jump-v'), s = v && v.nextElementSibling;
                    return s && s.hasAttribute('data-cable-unit') ? s.textContent.trim() : '';
                };
                var pick = function (unit) {
                    return t.hover('#power-jump-unit').then(function (p) {
                        press(true);
                        ripple(p.x, p.y);
                        return t.pause(90);
                    }).then(function () {
                        press(false);
                        A().setCableUnit(unit, false);
                        return t.wait(function () {
                            var sel = $('#power-jump-unit');
                            return A().cableUnit() === unit && sel && sel.value === unit && label() === unit;
                        });
                    });
                };
                return pick('m').then(function (ok) {
                    if (!ok) throw new Error('the show did not switch to meters');
                    t.mem.mid = label();
                    return t.pause(PACE.acted);
                }).then(function () {
                    return pick('ft');
                }).then(function (ok) {
                    if (!ok) throw new Error('the show did not switch back to feet');
                    return t.pause(PACE.rest);
                });
            },
            check: function (mem) {
                var w = wall();
                if (mem.mid !== 'm' || A().cableUnit() !== 'ft' || !w) return null;
                var v = Number(w.powerJumpV), h = Number(w.powerJumpH);
                return 'In meters the power jumpers read ' + v + ' m and ' + h + ' m; back in feet they read '
                    + v + ' ft and ' + h + ' ft again.';
            }
        },
        // Cable stock (1.5.3, app-cable-stock.js): the cable lengths the
        // show has on hand, in Preferences > Cable stock. The lists are the
        // show's and Save gives them to it. The guide never stores the
        // person's preferences, so its hand presses Save and the act gives
        // the lists to the show through applyCableStockPreferences, the
        // path Save takes for them; the dialog closes on the way out.
        cableStock: {
            since: '1.5.3',
            target: '#pref-cable-stock-all-ft', place: 'bottom', title: 'Cable stock',
            avoid: ['#pref-cable-stock-all-ft', '#preferences-save'],
            body: 'In Preferences, Cable stock, type the lengths this show has on hand: 25, 50, 100. Each run is then written as the stock pieces that make it, and a preset keeps the list for the next show.',
            before: function () {
                switchView('power');
                var a = A();
                a.openPreferencesModal();
                a.showPreferencesTab('stock');
            },
            act: function (t) {
                return t.type('#pref-cable-stock-all-ft', '25, 50, 100').then(function () {
                    return t.hover('#preferences-save');
                }).then(function (p) {
                    press(true);
                    ripple(p.x, p.y);
                    return t.pause(90);
                }).then(function () {
                    press(false);
                    A().applyCableStockPreferences();
                    return t.wait(function () { return A().cableStockList('multi', 'ft').join(',') === '25,50,100'; });
                }).then(function (ok) {
                    if (!ok) throw new Error('the show did not take the cable stock');
                    return t.pause(PACE.rest);
                });
            },
            check: function () {
                if (A().cableStockList('multi', 'ft').join(',') !== '25,50,100') return null;
                return 'This show has 25, 50 and 100 ft cables on hand. A 125 ft run is written ' + A().cableStockText(125, 'multi') + '.';
            },
            after: function () { closePrefs(); }
        },
        // The breakdown (app-cable-units.js breakCableLength): the least
        // extra length, then the fewest pieces. The typed 125 stays in the
        // field; the tags, the pull sheet and the binder write 100'+25',
        // and the pull sheet counts one of each.
        cableStockPieces: {
            since: '1.5.3',
            target: function () { var w = wall(); return w ? '[data-lrd-field^="power-soca-length-' + w.id + '-"]' : '[data-lrd-field^="power-soca-length-"]'; },
            place: 'top', title: 'A run made of stock pieces',
            body: 'Type 125 as the multi&rsquo;s home run. The field keeps 125; the pull sheet and the binder write it as 100&rsquo;+25&rsquo; and count one of each.',
            before: function () { switchView('power'); closePrefs(); },
            act: function (t) {
                var w = wall();
                var sel = '[data-lrd-field^="power-soca-length-' + w.id + '-"]';
                return t.type(sel, '125').then(function () {
                    return t.wait(function () {
                        var l = wall(); var m = (l && l.powerSocaLengths) || {};
                        return Object.keys(m).some(function (k) { return Number(m[k]) === 125; });
                    });
                }).then(function (ok) {
                    if (!ok) throw new Error('the home run did not take');
                    return t.pause(PACE.rest);
                });
            },
            check: function () {
                var a = A();
                var multi = (a.buildPullSheet().totals || []).filter(function (r) { return r.type === 'Multi'; });
                var lengths = multi.map(function (r) { return r.length + ' x' + r.qty; });
                if (lengths.indexOf("100' x1") < 0 || lengths.indexOf("25' x1") < 0) return null;
                return 'The 125 ft home run is written ' + a.cableStockText(125, 'multi') + ': the pull sheet lists one 100 ft and one 25 ft multi.';
            }
        },
        // A list per kind (1.6.0, app-cable-stock.js): multis, data, power,
        // L21-30 and Harting home runs, direct-output cables and feeders.
        // The kinds' lists are kept apart from the one shared list, so the
        // multis get theirs again and the feeders a list of their own; the
        // Feeder step types a length this list makes. Save is pressed the
        // way the Cable stock step presses it.
        cableStockPerKind: {
            since: '1.6.0',
            target: '#pref-cable-stock-per-kind', place: 'bottom', title: 'A list for each kind of cable',
            avoid: ['#pref-cable-stock-per-kind', '#pref-cable-stock-multi-ft', '#pref-cable-stock-feeder-ft', '#preferences-save'],
            body: 'Tick A list for each kind of cable and each kind gets its own lengths. Here the multis keep 25, 50 and 100, and the power in cables come in 50 and 100.',
            before: function () {
                switchView('power');
                var a = A();
                a.openPreferencesModal();
                a.showPreferencesTab('stock');
            },
            act: function (t) {
                return t.click('#pref-cable-stock-per-kind').then(function () {
                    return t.wait(function () {
                        var c = $('#pref-cable-stock-per-kind'), f = $('#pref-cable-stock-feeder-ft');
                        return c && c.checked && f && f.offsetParent !== null;
                    });
                }).then(function (ok) {
                    if (!ok) throw new Error('the lists for each kind did not come up');
                    return t.type('#pref-cable-stock-multi-ft', '25, 50, 100');
                }).then(function () {
                    return t.type('#pref-cable-stock-feeder-ft', '50, 100');
                }).then(function () {
                    return t.hover('#preferences-save');
                }).then(function (p) {
                    press(true);
                    ripple(p.x, p.y);
                    return t.pause(90);
                }).then(function () {
                    press(false);
                    A().applyCableStockPreferences();
                    return t.wait(function () { return A().cableStockList('feeder', 'ft').join(',') === '50,100'; });
                }).then(function (ok) {
                    if (!ok) throw new Error('the show did not take the lists');
                    return t.pause(PACE.rest);
                });
            },
            check: function () {
                var a = A();
                if (a.cableStockList('feeder', 'ft').join(',') !== '50,100'
                        || a.cableStockList('multi', 'ft').join(',') !== '25,50,100') return null;
                return 'Multis come in 25, 50 and 100 ft, power in cables in 50 and 100 ft: a 150 ft power in cable is written ' + a.cableStockText(150, 'feeder') + '.';
            },
            after: function () { closePrefs(); }
        },
        powerCableTags: {
            target: '#show-power-cable-tags', place: 'right', title: 'Show Cable Tags (power)',
            body: 'Tick it and each circuit&rsquo;s cable prints as a gold tag beside its label on the wall and in the export.',
            before: function () { switchView('power'); },
            act: function (t) {
                return t.click('#show-power-cable-tags').then(function () {
                    return t.wait(function () { var w = wall(); return w && w.showPowerCableTags === true; });
                });
            },
            check: function () {
                var w = wall();
                if (!w || w.showPowerCableTags !== true) return null;
                var has = w.powerCircuitCables && Object.keys(w.powerCircuitCables).length;
                return has ? 'The 25 ft cable prints as a gold tag beside its circuit.' : 'Each circuit’s cable prints as a gold tag beside its label.';
            }
        },
        // 2fers and 3fers, straight through (the owner's rulings,
        // 2026-10-19). At 150 W a cabinet a row of the demo wall (1,800 W)
        // is more than half a circuit, so no two rows ever share; a column
        // (900 W) is under a third of one (a 208V / 20A circuit packs to
        // 80%, 3,328 W, 2026-10-22; the owner kept the 3fer story with
        // lighter demo panels). So the section turns the circuits down the
        // columns, shares them in automatic mode, takes one 3fer over by
        // hand (it stays a 3fer), turns custom mode on (it starts empty),
        // fills the wall as custom runs (the same 3fers as automatic) and
        // re-deals two of them as 2fers with a sweep.
        powerColumns: {
            target: '.power-flow-pattern-btn[data-pattern="tl-v"]', place: 'right', title: 'Circuits down the columns',
            avoid: ['.power-flow-pattern-btn[data-pattern="tl-v"]'],
            body: 'Under Flow Pattern, press Top-left, vertical first, so each circuit runs down whole columns. A wall cabled across shares rows the same way; on this wall a row is too much load to share.',
            before: function () { switchView('power'); },
            act: function (t) {
                return t.click('.power-flow-pattern-btn[data-pattern="tl-v"]').then(function () {
                    return t.wait(function () { var w = wall(); return w && w.powerFlowPattern === 'tl-v'; });
                });
            },
            check: function () {
                var w = wall();
                if (!w || w.powerFlowPattern !== 'tl-v') return null;
                var circuits = A().screenCircuits(w);
                if (!circuits.length) return null;
                var cols = {};
                (circuits[0].panels || []).forEach(function (p) { cols[p.col] = true; });
                return circuits.length + ' circuits now run down the columns, '
                    + Object.keys(cols).length + ' columns to a circuit.';
            }
        },
        splitters: {
            target: '#power-splitters-enabled', place: 'right', title: 'Share runs through 3fers',
            avoid: ['#power-splitters-enabled', '#main-canvas'],
            body: 'Tick Share circuits via splitters and each column, or each row on a wall cabled across, becomes a run of its own, with neighbors sharing one circuit through a 2fer or 3fer while the load fits.',
            before: function () { switchView('power'); },
            act: function (t) {
                return t.click('#power-splitters-enabled').then(function () {
                    return t.wait(function () { return A().getPowerSplitters(wall()).enabled && sharedCircuits(wall()).length; });
                });
            },
            check: function () {
                var w = wall();
                var shared = sharedCircuits(w);
                if (!w || A().isCustomPower(w) || !shared.length) return null;
                if (shared.some(function (s) { return s.over; })) return null;
                var load = A().shareLoad(w, shared[0].runIds);
                var cap = A().circuitCapacity(w);
                return shared.length + ' circuits, each a ' + shared[0].ways + 'fer of ' + shared[0].ways + ' column runs: '
                    + load.amps.toFixed(1) + ' A against ' + (+load.cap.toFixed(1)) + ' A usable on a '
                    + (+cap.breakerA.toFixed(1)) + ' A breaker.';
            }
        },
        // A take-over in automatic mode (canvas.js Alt+click): the shared
        // circuit keeps its runs, each run head after the first marked on
        // the drawn path, so it still draws, tags and counts as a 3fer.
        takeOver: {
            since: '1.5.3',
            target: '#main-canvas', place: 'top', title: 'Take over a 3fer',
            avoid: [function () { var w = wall(); return w ? T.cabinetPoint(w, { circuit: 1, mid: true, raw: true }) : null; }],
            body: 'Hold Alt and click a circuit to take it over and redraw it by hand. A 3fer you take over keeps its three runs, so it stays a 3fer.',
            before: function () { switchView('power'); },
            act: function (t) {
                var w = wall();
                var c = A().screenCircuits(w)[1];
                if (!c || (c.runIds || []).length < 2) throw new Error('the second circuit is not shared');
                t.mem.num = c.num;
                var pt = t.cabinetPoint(w, { circuit: 1, mid: true });
                return t.moveTo(pt, { badge: 'Alt' }).then(function () {
                    A().updateOverrideHover(true, pt.worldX, pt.worldY);
                    return t.pause(PACE.hover);   // the lit circuit, read
                }).then(function () {
                    press(true);
                    t.canvasDown(pt, { altKey: true });
                    t.canvasUp(pt, { altKey: true });
                    press(false);
                    ripple(pt.x, pt.y);
                    return t.wait(function () { return A()._overrideEditing && A().isRunOverridden(wall(), 'power', t.mem.num); });
                }).then(function (ok) {
                    if (!ok) throw new Error('the circuit was not taken over');
                    badge('');
                    // left open for redrawing: a take-over that ends
                    // unchanged goes back to automatic (2026-11-03), so
                    // the step reads it while it is open and `after` ends it
                    return t.pause(PACE.acted);
                });
            },
            check: function (mem) {
                var w = wall();
                if (!w || mem.num == null || !A().isRunOverridden(w, 'power', mem.num)) return null;
                var c = A().screenCircuits(w).find(function (x) { return x.num === mem.num; });
                var runs = c ? (c.runIds || []).length : 0;
                var shared = sharedCircuits(w).find(function (s) { return s.num === mem.num; });
                if (runs < 2 || !shared || shared.ways !== runs) return null;
                return 'Circuit ' + mem.num + ' is now drawn by hand and is still a ' + runs + 'fer of ' + runs + ' runs.';
            },
            after: function () {
                var a = A();
                if (a && a._overrideEditing && a.endOverrideEdit) { try { a.endOverrideEdit(); } catch (e) {} }
            }
        },
        // Custom mode ON starts empty (the owner's ruling, 2026-10-19):
        // every circuit on the screen, take-overs and typed circuit labels
        // included, is wiped in the toggle's one history entry.
        customPower: {
            since: '1.5.3',
            target: '#power-custom-toggle', place: 'right', title: 'Custom mode for power',
            body: 'Custom mode hands you the runs: turn it on and the screen starts empty. Every circuit, take-over and typed circuit label is wiped.',
            before: function () { switchView('power'); },
            act: function (t) {
                var w = wall();
                t.mem.taken = !!(w && (w.powerCustomOverrides || []).length);
                return t.click('#power-custom-toggle').then(function () {
                    return t.wait(function () { var l = wall(); return l && A().isCustomPower(l); });
                });
            },
            check: function (mem) {
                var w = wall();
                if (!w || !A().isCustomPower(w)) return null;
                var paths = w.powerCustomPaths || {};
                var drawn = Object.keys(paths).filter(function (k) { return (paths[k] || []).length; }).length;
                if (drawn || (w.powerCustomOverrides || []).length) return null;
                return mem.taken ? 'Custom mode is on and nothing is drawn: the taken-over 3fer went with the rest.'
                    : 'Custom mode is on and nothing is drawn yet.';
            }
        },
        // The fill: drag across the wall (custom mode's own drag selects
        // cabinets), press a pattern button. With sharing on the fill cuts
        // the way automatic mode does (app-custom-runs.js
        // _chunkPicksIntoShares): a run per column, neighbours on one
        // circuit while the load fits.
        customDraw: {
            since: '1.5.3',
            target: '.power-flow-pattern-btn[data-pattern="tl-v"]', place: 'right', title: 'Draw the circuits',
            avoid: ['.power-flow-pattern-btn[data-pattern="tl-v"]', '#main-canvas'],
            body: 'Drag across the cabinets, then press Top-left, vertical first. With sharing on you get what automatic mode makes: a run per column (or per row on a wall cabled across), neighbors sharing a 3fer while the load fits.',
            before: function () { switchView('power'); },
            act: function (t) {
                var w = wall();
                if (!w || !A().isCustomPower(w)) throw new Error('custom mode is not on');
                var p0 = t.cabinetPoint(w, { index: 0 });
                var p1 = t.cabinetPoint(w, { index: w.panels.length - 1 });
                return t.hover(p0).then(function () {
                    press(true);
                    t.canvasDown(p0);
                    return t.pause(PACE.dragPress);
                }).then(function () {
                    t.canvasMove({ x: p0.x + 6, y: p0.y + 6 });
                    return t.canvasGlide(p1, null, PACE.dragTravel);
                }).then(function () {
                    t.canvasMove(p1);
                    return t.pause(PACE.hover);
                }).then(function () {
                    t.canvasUp(p1);
                    press(false);
                    return t.wait(function () { return A().powerCustomSelection && A().powerCustomSelection.size > 0; }, 1500);
                }).then(function (sel) {
                    if (!sel) throw new Error('the drag selected no cabinets');
                    return t.pause(PACE.sweepRest);
                }).then(function () {
                    return t.click('.power-flow-pattern-btn[data-pattern="tl-v"]');
                }).then(function () {
                    return t.wait(function () { return A().usesCustomCircuits(wall()) && sharedCircuits(wall()).length; });
                });
            },
            check: function () {
                var w = wall();
                if (!w || !A().usesCustomCircuits(w)) return null;
                var shared = sharedCircuits(w);
                if (!shared.length || shared.some(function (s) { return s.over; })) return null;
                var runs = A().screenCircuits(w).reduce(function (n, c) { return n + ((c.runIds || []).length || 1); }, 0);
                return runs + ' column runs drawn by hand, shared as '
                    + A()._nferSizesLabel(shared.map(function (s) { return s.ways; })) + ', the same as automatic mode.';
            },
            // The fill leaves the selection standing (a person may press
            // another pattern); the app's own Esc drops it. Dropped here on
            // the way out, the way a sheet a step opened is closed, so the
            // wall the next step sweeps is not dimmed under 72 lit cabinets.
            after: function () {
                var a = A();
                if (a && a.powerCustomSelection && a.powerCustomSelection.size) {
                    a.powerCustomSelection.clear();
                    a.updateCustomPowerUI();
                    if (R()) R().render();
                }
            }
        },
        // The batch verb on runs picked by hand (canvas.js Alt+drag arms
        // the sweep, app-dock-menus.js _prepareBatchMenu deals it): it
        // works in automatic mode, in custom mode and across a group, and
        // never deals a circuit past its amps; runs that do not fit
        // together stay on circuits of their own.
        sweepShare: {
            since: '1.5.3',
            target: '#main-canvas', place: 'top', title: '2fer the runs you pick',
            avoid: [function () { var w = wall(); return w ? T.cabinetPoint(w, { circuit: 0, mid: true, raw: true }) : null; },
                    function () { var w = wall(); return w ? T.cabinetPoint(w, { circuit: 1, mid: true, raw: true }) : null; }],
            body: 'Hold Alt and drag across circuits to pick them, then right-click and pick 2fer them. It works in either mode and across a group, and runs that do not fit together stay plain.',
            before: function () { switchView('power'); },
            act: function (t) {
                var w = wall();
                var circuits = A().screenCircuits(w);
                if (circuits.length < 2) throw new Error('fewer than two circuits to sweep');
                var c0 = t.cabinetPoint(w, { circuit: 0, mid: true });
                var c1 = t.cabinetPoint(w, { circuit: 1, mid: true });
                return t.hover(c0, { badge: 'Alt' }).then(function () {
                    press(true);
                    t.canvasDown(c0, { altKey: true });
                    return t.pause(PACE.dragPress);
                }).then(function () {
                    t.canvasMove({ x: c0.x + 6, y: c0.y + 6 }, { altKey: true });
                    return t.canvasGlide(c1, { altKey: true }, PACE.sweep);
                }).then(function () {
                    t.canvasMove(c1, { altKey: true });
                    return t.pause(PACE.hover);
                }).then(function () {
                    t.canvasUp(c1, { altKey: true });
                    press(false);
                    return t.wait(function () { var s = A()._sweepSelection; return s && (s.nums || []).length >= 2; });
                }).then(function (sel) {
                    if (!sel) throw new Error('the sweep picked no circuits');
                    return t.pause(PACE.sweepRest);
                }).then(function () {
                    return t.rightClick(c1);
                }).then(function () {
                    var item = $('#context-menu [data-action="hw-batch-n0"]');
                    t.mem.label = item ? item.textContent.trim() : '';
                    if (!/^2fer them/.test(t.mem.label)) throw new Error('the menu offers no 2fer them');
                    return t.pickMenu('hw-batch-n0');
                }).then(function () {
                    return t.wait(function () {
                        return !A()._sweepSelection && sharedCircuits(wall()).some(function (s) { return s.ways === 2; });
                    });
                });
            },
            check: function (mem) {
                var w = wall();
                var shared = sharedCircuits(w);
                var pairs = shared.filter(function (s) { return s.ways === 2; });
                if (!pairs.length || shared.some(function (s) { return s.over; })) return null;
                var ids = pairs.reduce(function (all, s) { return all.concat(s.runIds); }, []);
                return (mem.label || '2fer them') + ': runs ' + Math.min.apply(null, ids) + ' to ' + Math.max.apply(null, ids)
                    + ' now share in pairs, each within its amps.';
            }
        },
        balance: {
            target: function () { var d = distro(); return d ? '[data-lrd-field="distro-balance-' + d.id + '"]' : '#hardware-dock-body .hw-dock-btn'; },
            place: 'top', title: 'Balance the legs',
            body: 'A 3-phase distro carries live leg meters. Balance proposes which breakers a short multi should land on; nothing moves until Apply.',
            before: function () { switchView('power'); },
            act: function (t) {
                var d = distro();
                return t.click('[data-lrd-field="distro-balance-' + d.id + '"]').then(function () {
                    return t.wait(function () { return $('#balance-modal'); }, 2500);
                }).then(function (m) {
                    if (!m) throw new Error('the Balance dialog did not open');
                    t.mem.opened = true;
                    t.mem.apply = !!m.querySelector('.balance-apply');
                    return t.spot(m.querySelector('.modal-content') || m).then(function () { return t.pause(1000); });
                }).then(function () {
                    var m = $('#balance-modal');
                    if (!m) return;
                    var btn = m.querySelector('.balance-apply') || $$('.balance-close', m).pop();
                    return t.click(btn, { rest: PACE.acted });
                });
            },
            check: function (mem) {
                if (!mem.opened) return null;
                return mem.apply ? 'Balance moved the short multi onto evener breakers.' : 'Balance opened; nothing to move on this distro yet, so it closed.';
            },
            after: function () { var m = $('#balance-modal'); if (m) m.remove(); }
        },
        // Services (1.5.3, app-services.js): the house power several
        // distros are fed from. One step adds the Service card, the next
        // drags the distro's header bar onto it.
        addService: {
            since: '1.5.3',
            target: '#power-service-add', place: 'top', title: 'Add a service',
            body: 'Add service puts a Service card above the distros: the house power they draw from. It starts at 400 A per leg, and its rating and system sit behind its &#9881;.',
            before: function () { switchView('power'); closePopover(); },
            act: function (t) {
                return t.click('#power-service-add').then(function () {
                    return t.wait(function () { return service() && $('[data-lrd-service]'); });
                }).then(function (ok) {
                    if (!ok) throw new Error('no Service card came up');
                    return t.pause(PACE.rest);
                });
            },
            check: function () {
                var s = service();
                return s && $('[data-lrd-service="' + s.id + '"]')
                    ? A().serviceLabel(s) + ' is in the tray, feeding nothing yet.' : null;
            }
        },
        // The house size: a service starts at 400 A, and the gear's Rating
        // makes it the 600 A the walkthrough's distros share.
        serviceRating: {
            since: '1.5.3',
            target: function () { var s = service(); return s ? '[data-hwpop="service-' + s.id + '"]' : '#power-service-add'; },
            place: 'top', title: 'Set the service size',
            avoid: [function () { var s = service(); return s ? '[data-lrd-field="service-rating-' + s.id + '"]' : null; }],
            body: 'Open the service&rsquo;s &#9881; and type the house power into Rating, in amps per leg. Make this one 600 A, enough for a 400 A and a 200 A distro to share.',
            before: function () { switchView('power'); closePopover(); },
            act: function (t) {
                var s = service();
                if (!s) throw new Error('there is no service to size');
                return t.click('[data-hwpop="service-' + s.id + '"]').then(function () {
                    return t.wait(popover);
                }).then(function (pop) {
                    if (!pop) throw new Error('the service\'s gear popover did not open');
                    return t.spot(pop).then(function () { return t.pause(900); });
                }).then(function () {
                    return t.type('[data-lrd-field="service-rating-' + s.id + '"]', '600');
                }).then(function () {
                    return t.wait(function () { var q = service(); return q && Number(q.ratingA) === 600; });
                }).then(function (ok) {
                    if (!ok) throw new Error('the service did not take 600 A');
                    return t.pause(PACE.acted);
                });
            },
            check: function () {
                var s = service();
                return s && Number(s.ratingA) === 600 ? A().serviceLabel(s) + ' is the house power now.' : null;
            },
            after: function () { closePopover(); }
        },
        serviceDistro: {
            since: '1.5.3',
            target: function () { var d = distro(); return d ? '[data-lrd-distro="' + d.id + '"] > .hw-dock-head-row' : '[data-lrd-distro] > .hw-dock-head-row'; },
            place: 'top', title: 'Put the distro on the service',
            avoid: [function () { var s = service(); return s ? '[data-lrd-service="' + s.id + '"]' : null; }],
            body: 'Drag the distro&rsquo;s header bar onto the Service card. The card adds up its distros&rsquo; leg loads against the service, held to 80% of its rating unless it is 100% rated.',
            before: function () { switchView('power'); closePopover(); },
            act: function (t) {
                var d = distro(), s = service();
                if (!d || !s) throw new Error('there is no distro or no service to put it on');
                return t.drag('[data-lrd-distro="' + d.id + '"] > .hw-dock-head-row', '[data-lrd-service="' + s.id + '"]').then(function () {
                    return t.wait(function () {
                        var q = distro();
                        return q && q.serviceId === s.id && $('[data-lrd-service="' + s.id + '"] [data-lrd-svc-distro="' + d.id + '"]');
                    });
                }).then(function (ok) {
                    if (!ok) throw new Error('the distro did not go on the service');
                    return t.pause(PACE.rest);
                });
            },
            check: function () {
                var d = distro(), s = service();
                if (!d || !s || d.serviceId !== s.id) return null;
                var u = $('[data-lrd-service="' + s.id + '"] .hw-dock-unit-use');
                return (d.name || 'The distro') + ' is on ' + (s.name || 'the service')
                    + (u ? ': its busiest leg reads ' + u.textContent.trim() + '.' : '.');
            }
        },
        // The feeder (1.6.0, app-services.js _buildDistroFeederRow): the
        // cable that powers the distro, behind its gear. A length, written
        // from the feeders' stock list, and where it is fed from: the
        // service, or thru another distro. It is always on the pull sheet,
        // "no length" until one is typed.
        feederLength: {
            since: '1.6.0',
            target: function () { var d = distro(); return d ? '[data-hwpop="distro-' + d.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'The distro&rsquo;s power in',
            avoid: [function () { var d = distro(); return d ? '[data-lrd-field="distro-feeder-ft-' + d.id + '"]' : null; },
                    function () { var d = distro(); return d ? '[data-lrd-field="distro-feeder-from-' + d.id + '"]' : null; }],
            body: 'Open the distro&rsquo;s &#9881; and type its power in length. Beside it you pick where it&rsquo;s powered from: the service, or thru another distro.',
            before: function () { switchView('power'); closePopover(); },
            act: function (t) {
                var d = distro();
                if (!d) throw new Error('there is no distro to power');
                return t.click('[data-hwpop="distro-' + d.id + '"]').then(function () {
                    return t.wait(popover);
                }).then(function (pop) {
                    if (!pop) throw new Error('the distro\'s gear popover did not open');
                    return t.spot(pop).then(function () { return t.pause(900); });
                }).then(function () {
                    return t.type('[data-lrd-field="distro-feeder-ft-' + d.id + '"]', '150');
                }).then(function () {
                    return t.wait(function () { var q = distro(); return q && q.feeder && Number(q.feeder.ft) === 150; });
                }).then(function (ok) {
                    if (!ok) throw new Error('the power in did not take 150');
                    return t.wait(function () { return $('[data-lrd-field="distro-feeder-from-' + d.id + '"]'); });
                }).then(function (sel) {
                    if (!sel) throw new Error('the powered-from choice did not come up');
                    return t.hover('[data-lrd-field="distro-feeder-from-' + d.id + '"]');
                }).then(function () {
                    return t.pause(PACE.acted);
                });
            },
            check: function () {
                var d = distro(), a = A();
                if (!d || !d.feeder || Number(d.feeder.ft) !== 150) return null;
                var f = a.distroFeeder(d);
                var from = f.from ? 'thru ' + (f.from.name || f.from.id)
                    : 'from ' + (f.service ? f.service.name || 'the service' : 'the service');
                // said once, lower case mid-sentence: "SL's power in: 150'",
                // never "SL's power in: Power in 150'" (the binder's rule)
                var text = String(a.feederText(d)).replace(/^Power in(?:,\s*|\s+)(?=\S)/, '')
                    .replace(/^(\S.*?) power in(?=,? |$)/, '$1');
                return (d.name || 'The distro') + '\'s power in: ' + text + ', powered ' + from
                    + '. The pull sheet lists it where the distro sits.';
            },
            after: function () { closePopover(); }
        },
        // Distros built from their outputs (1.5, app-distro-systems.js
        // _buildDistroOutputRows): a preset lays the system, input, rating,
        // output rows and Type on the distro in one undo step. They run
        // before the multi steps: the preset's first row is Socapex at 208V,
        // the multi every power step after drags onto the wall. A distro
        // with rows IS its face, so its type chips only read the row; the
        // guide has no type chip step.
        distroPreset: {
            since: '1.5.0',
            target: function () { var d = distro(); return d ? '[data-hwpop="distro-' + d.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'Start from a preset',
            window: distroGearWindow,
            avoid: [function () { var d = distro(); return d ? '[data-lrd-field="distro-preset-' + d.id + '"]' : null; }],
            body: 'Start from a preset&hellip; sets System, Input, Rating and the output rows in one step. It fills in Type too, the name the pull sheet lists the distro by.',
            before: function () { switchView('power'); closePopover(); },
            act: function (t) {
                var d = distro();
                var value = 'b:us-200-4soca-3dup';
                return openDistroGear(t, d).then(function () {
                    var sel = $('[data-lrd-field="distro-preset-' + d.id + '"]');
                    var opt = sel && Array.prototype.slice.call(sel.options).find(function (o) { return o.value === value; });
                    if (!opt) throw new Error('the preset is not on the list');
                    t.mem.name = opt.textContent.trim();
                    return t.select(sel, value);
                }).then(function () {
                    return t.wait(function () {
                        var q = distro();
                        return q && faceCount(q) > 0 && q.typeName === t.mem.name
                            && $('[data-lrd-field="distro-type-' + q.id + '"]');
                    });
                }).then(function (type) {
                    if (!type) throw new Error('the preset did not take');
                    return t.pause(PACE.acted);
                });
            },
            check: function (mem) {
                var d = distro(), a = A();
                if (!d || !faceCount(d) || d.typeName !== mem.name) return null;
                var rows = a.distroRows(d).map(function (r) { return r.count + ' × ' + a.distroConnector(r.connector).short; });
                return (d.name || 'The distro') + ' now has ' + rows.join(' and ') + ' on its face, and its Type reads ' + d.typeName + '.';
            },
            after: function () { closePopover(); }
        },
        distroRows: {
            since: '1.5.0',
            target: function () { var d = distro(); return d ? '[data-hwpop="distro-' + d.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'Output rows',
            window: distroGearWindow,
            avoid: [function () {
                var d = distro(), r = d ? socaRow(d) : null;
                return r ? '[data-lrd-field="distro-row-count-' + d.id + '-' + r.id + '"]' : null;
            }],
            body: 'Each output row is a connector and a count, and rows can mix on one distro. Make the Socapex row 6 and two more multis join the distro in the tray.',
            before: function () { switchView('power'); closePopover(); },
            act: function (t) {
                var d = distro();
                var r = socaRow(d);
                if (!r) throw new Error('the distro has no Socapex row');
                t.mem.before = faceCount(d);
                t.mem.row = r.id;
                return openDistroGear(t, d).then(function () {
                    return t.type('[data-lrd-field="distro-row-count-' + d.id + '-' + r.id + '"]', '6');
                }).then(function () {
                    return t.wait(function () {
                        var q = distro(), row = q && A().distroRows(q).find(function (x) { return x.id === t.mem.row; });
                        return row && Number(row.count) === 6 && faceCount(q) === t.mem.before + (6 - r.count)
                            && $('[data-hwdock="slot-' + q.id + '-6"]');
                    });
                }).then(function () { return t.pause(PACE.acted); });
            },
            check: function (mem) {
                var d = distro();
                var row = d && A().distroRows(d).find(function (x) { return x.id === mem.row; });
                if (!row || Number(row.count) !== 6 || !$('[data-hwdock="slot-' + d.id + '-6"]')) return null;
                return 'The Socapex row reads 6: ' + (d.name || 'the distro') + ' 5 and 6 are new multis in the tray, '
                    + faceCount(d) + ' outputs on its face in all.';
            },
            after: function () { closePopover(); }
        },
        addBeach: {
            target: '#beaches-panel .beaches-add', place: 'left', title: 'Beaches',
            body: 'A beach is a position the show is pulled to. Add beach asks for a name; here it is filled in as Stage Left.',
            act: function (t) {
                return t.hover('#beaches-panel .beaches-add').then(function (p) {
                    press(true); ripple(p.x, p.y);
                    return t.pause(200);
                }).then(function () {
                    press(false);
                    return A().createBeach('Stage Left');
                }).then(function () {
                    return t.wait(function () { return beach(); });
                }).then(function () { return t.pause(PACE.rest); });
            },
            check: function () {
                var b = beach();
                return b ? b.name + ' is the first beach; screens, distros and boxes can stand on it.' : null;
            }
        },
        screenBeach: {
            target: '#layer-beach', place: 'right', title: 'The screen&rsquo;s beach',
            body: 'Each screen picks its beach in Screen Info. The pull sheet groups by beach and the binder runs the screens in beach order.',
            before: function () { switchView('pixel-map'); },
            act: function (t) {
                var b = beach();
                return t.select('#layer-beach', b.id).then(function () {
                    return t.wait(function () { var w = wall(); return w && w.beachId === b.id; });
                });
            },
            check: function () {
                var w = wall(), b = beach();
                return w && b && w.beachId === b.id ? 'DEMO WALL is pulled to ' + b.name + '.' : null;
            }
        },
        addScreen: {
            target: '#layers-list .canvas-add-btn', place: 'left', title: 'A second screen',
            body: 'Add opens the screen chooser. Here a second wall, matched to the first, is added beside it for you.',
            before: function () { switchView('pixel-map'); },
            act: function (t) {
                var a = A(), w = wall();
                return t.hover('#layers-list .canvas-add-btn').then(function (p) {
                    press(true); ripple(p.x, p.y);
                    return t.pause(200);
                }).then(function () {
                    press(false);
                    return j('POST', '/api/layer/add', {
                        name: 'DEMO WALL 2', columns: w.columns, rows: w.rows,
                        cabinet_width: w.cabinet_width, cabinet_height: w.cabinet_height,
                        offset_x: (Number(w.offset_x) || 0) + w.columns * w.cabinet_width + 200,
                        offset_y: Number(w.offset_y) || 0
                    });
                }).then(function (layer) {
                    practiceScreen(layer);
                    ['processorType', 'bitDepth', 'frameRate', 'lowLatency', 'powerVoltage',
                     'powerAmperage', 'panelWatts', 'powerBreakoutType', 'flowPattern'].forEach(function (k) {
                        if (w[k] !== undefined) layer[k] = w[k];
                    });
                    a.upsertProjectLayer(layer);
                    a.updateLayers([layer]);
                    a.selectLayer(layer);
                    frameWalls();
                    a.saveState('Add Layer');
                    a.saveClientSideProperties();
                    return t.wait(function () { return wall2(); });
                }).then(function () { return t.pause(PACE.rest); });
            },
            check: function () { return wall2() ? 'DEMO WALL 2 stands beside the first: same size, same processing.' : null; }
        },
        // "Put on beach" on the right-click menu (app-beaches.js
        // _prepareBeachMenu, 2026-09-15): every selected screen onto one
        // beach in one undoable step. The submenu opens on the item's CSS
        // :hover, which the ghost hand cannot raise, so the act opens it
        // while the hand rests on the item and lets it go on the way out.
        // The selection is the real gesture (Matt, 2026-09-15: the step
        // "does not show the action of selecting multiple screens"): a
        // click on one row of the Screens panel, then a ⌘-click (Ctrl on
        // Windows - app-layers-panel.js reads metaKey || ctrlKey) on the
        // other, both rows lit, then the right-click on the wall.
        beachByMenu: {
            target: function () { var w = wall(); return w ? layerRow(w) : '#layers-list'; },
            ring: [function () { var w = wall(); return w ? layerRow(w) : null; },
                   function () { var w2 = wall2(); return w2 ? layerRow(w2) : null; }],
            place: 'left', title: 'Put screens on a beach together',
            avoid: [function () { var w = wall(); return w ? layerRow(w) : null; },
                    function () { var w2 = wall2(); return w2 ? layerRow(w2) : null; },
                    function () { var w2 = wall2(); return w2 ? T.cabinetPoint(w2, { index: 0 }) : null; }],
            body: 'Select two screens: click one row, then ' + MOD_KEY + '-click the other. Right-click a selected screen on the wall and Put on beach lands them all on one beach in a single step.',
            before: function () { switchView('pixel-map'); frameWalls(); },
            act: function (t) {
                var a = A(), w = wall(), w2 = wall2(), b = beach();
                if (!w2 || !b) throw new Error('two screens and a beach are needed');
                var sub = $('#beach-submenu');
                var letGo = function () { if (sub) sub.style.display = ''; };
                return t.click(layerRow(w)).then(function () {
                    return t.click(layerRow(w2), { init: MOD_INIT, badge: MOD_KEY });
                }).then(function () {
                    return t.wait(function () { return a.selectedLayerIds && a.selectedLayerIds.size === 2; }, 1500);
                }).then(function (both) {
                    if (!both) throw new Error('the second screen did not join the selection');
                    // Both rows lit: seen before the hand leaves the panel.
                    return t.pause(PACE.acted);
                }).then(function () {
                    return t.rightClick(t.cabinetPoint(w2, { index: 0 }));
                }).then(function () {
                    var item = $('#context-menu [data-action="beach-menu"]');
                    if (!item || item.style.display === 'none') throw new Error('Put on beach is not on the menu');
                    return t.hover(item, { speed: PACE.menuTravel, hover: 600 });
                }).then(function () {
                    if (sub) sub.style.display = 'block';
                    var rows = $$('#beach-submenu .menu-option');
                    var row = rows.find(function (r) { return r.dataset.action !== 'beach-new' && r.textContent.trim() === b.name; })
                        || $('#beach-submenu [data-action="beach-0"]');
                    if (!row) { letGo(); throw new Error('the beach is not on the submenu'); }
                    return t.hover(row, { speed: PACE.menuTravel, hover: PACE.menuHover }).then(function (p) {
                        ripple(p.x, p.y);
                        row.click();
                        return t.pause(PACE.rest);
                    });
                }).then(function () {
                    return t.wait(function () {
                        var l1 = wall(), l2 = wall2();
                        return l1 && l2 && l1.beachId === b.id && l2.beachId === b.id;
                    });
                }).then(letGo, function (e) { letGo(); throw e; });
            },
            check: function () {
                var a = A(), w = wall(), w2 = wall2(), b = beach();
                if (!w || !w2 || !b || w.beachId !== b.id || w2.beachId !== b.id) return null;
                var sel = a.selectedLayerIds;
                if (!sel || sel.size !== 2 || !sel.has(w.id) || !sel.has(w2.id)) return null;
                var cnt = $('#beaches-panel .beach-row[data-beach-id="' + b.id + '"] .beach-count');
                if (!cnt || cnt.textContent.trim() !== '2') return null;
                return w.name + ' and ' + w2.name + ' stand on ' + b.name + ', both still selected; the Beaches panel counts 2.';
            },
            after: function () { var sub = $('#beach-submenu'); if (sub) sub.style.display = ''; }
        },
        // Cabinets across screens (1.5, app-pixel-select.js): with several
        // screens selected, a Pixel Map drag that starts on any of them
        // picks cabinets on every one. The two screens are selected by the
        // step before; a Go to that lands here (a restore selects one
        // screen) selects them the same way first.
        crossScreens: {
            since: '1.5.0',
            target: '#main-canvas', place: 'top', title: 'Cabinets across screens',
            avoid: [function () { var w = wall(); return w ? T.cabinetPoint(w, { index: cabinetIndex(w, 2, w.columns - 2), raw: true }) : null; },
                    function () { var w2 = wall2(); return w2 ? T.cabinetPoint(w2, { index: cabinetIndex(w2, 3, 1), raw: true }) : null; }],
            body: 'With both screens selected, drag across them on the Pixel Map and you pick cabinets on each one. Set Blank or Set Half-tile then changes them all at once.',
            before: function () { switchView('pixel-map'); frameWalls(); },
            act: function (t) {
                var a = A(), w = wall(), w2 = wall2();
                if (!w || !w2) throw new Error('two screens are needed');
                var both = function () { return a.selectedLayerIds && a.selectedLayerIds.has(w.id) && a.selectedLayerIds.has(w2.id); };
                var select = both() ? Promise.resolve(true) : t.click(layerRow(w)).then(function () {
                    return t.click(layerRow(w2), { init: MOD_INIT, badge: MOD_KEY });
                }).then(function () {
                    return t.wait(both, 1500);
                });
                return select.then(function (ok) {
                    if (!ok) throw new Error('the two screens are not both selected');
                    // From the first wall's third row, two cabinets in from
                    // its right edge, to the second wall's fourth row, second
                    // cabinet: two rows of two cabinets on each screen.
                    var p0 = t.cabinetPoint(wall(), { index: cabinetIndex(wall(), 2, w.columns - 2) });
                    var p1 = t.cabinetPoint(wall2(), { index: cabinetIndex(wall2(), 3, 1) });
                    return t.hover(p0).then(function () {
                        press(true);
                        t.canvasDown(p0);
                        return t.pause(PACE.dragPress);
                    }).then(function () {
                        t.canvasMove({ x: p0.x + 6, y: p0.y + 6 });
                        return t.canvasGlide(p1, null, PACE.dragTravel);
                    }).then(function () {
                        t.canvasMove(p1);
                        return t.pause(PACE.hover);
                    }).then(function () {
                        t.canvasUp(p1);
                        press(false);
                        return t.wait(function () { return Object.keys(pickedByScreen()).length === 2; });
                    });
                }).then(function (ok) {
                    if (!ok) throw new Error('the drag did not pick cabinets on both screens');
                    return t.pause(PACE.acted);
                });
            },
            check: function () {
                var w = wall(), w2 = wall2(), by = pickedByScreen();
                if (!w || !w2 || !by[w.id] || !by[w2.id]) return null;
                return 'One drag picked ' + by[w.id] + ' cabinets on ' + w.name + ' and ' + by[w2.id] + ' on ' + w2.name + '.';
            },
            after: function () { var a = A(); if (a && a.clearPixelMapSelection) a.clearPixelMapSelection(); }
        },
        groupScreens: {
            target: '#layers-list', place: 'left', title: 'Group the screens',
            avoid: ['#layers-list'],
            body: 'Select both screens (Shift+click the second), right-click and pick Group Screens. A group moves and routes as one wall.',
            before: function () { switchView('pixel-map'); },
            act: function (t) {
                var rows = function () { return $$('#layers-list .layer-item'); };
                var w = wall(), w2 = wall2();
                var row = function (l) { return rows().find(function (r) { return String(r.dataset.layerId) === String(l.id); }); };
                return t.click(row(w)).then(function () {
                    return t.click(row(w2), { init: { shiftKey: true }, badge: 'Shift' });
                }).then(function () {
                    return t.wait(function () { return A().selectedLayerIds && A().selectedLayerIds.size === 2; }, 1500);
                }).then(function () {
                    return t.rightClick(t.cabinetPoint(wall(), { index: 0 }));
                }).then(function () {
                    return t.pickMenu('group-screens');
                }).then(function () {
                    return t.wait(function () { return (A().project.groups || []).length === 1; });
                });
            },
            check: function () {
                var g = (A().project.groups || [])[0];
                return g ? g.name + ': two screens that move and route as one wall.' : null;
            }
        },
        exportBinder: {
            window: 'export:binder',
            target: '#btn-export', place: 'bottom', title: 'Export the binder',
            avoid: ['#btn-export', '#export-format'],
            body: 'Export saves maps as PNG, PSD, PDF or XML, the pull sheet, or the Binder: a drawing set with a wiring sheet behind every map.',
            before: function () { closeExport(); },
            act: function (t) {
                var open = exportOpen() ? Promise.resolve() : t.click('#btn-export').then(function () {
                    return t.wait(exportOpen);
                });
                return open.then(function () {
                    var mc = $('#export-modal .modal-content');
                    return t.spot(mc).then(function () { return t.pause(PACE.opened); })
                        .then(function () { return t.select('#export-format', 'binder'); });
                }).then(function () { return t.pause(PACE.acted); });
            },
            check: function () {
                var f = $('#export-format');
                var sec = $('#export-binder-section');
                return exportOpen() && f && f.value === 'binder' && sec && sec.style.display !== 'none'
                    ? 'Binder (PDF): numbered sheets with a title block, on Tabloid by default.' : null;
            },
            after: closeExport
        },
        screenOrder: {
            window: 'export:binder',
            target: '#export-binder-screen-order', place: 'right', title: 'Screen order',
            body: 'Beaches come first, in the Beaches panel&rsquo;s order; this sorts the screens within one, and the contents follow.',
            before: openExport,
            act: function (t) {
                var sel = $('#export-binder-screen-order');
                var opts = Array.prototype.slice.call(sel.options).map(function (o) { return o.value; });
                var pick = opts.find(function (v) { return v !== sel.value; });
                t.mem.pick = pick;
                return t.select(sel, pick).then(function () {
                    return t.wait(function () { var b = A().project.binder; return b && b.screenOrder === pick; });
                });
            },
            check: function (mem) {
                var b = A().project.binder;
                if (!b || b.screenOrder !== mem.pick) return null;
                var sel = $('#export-binder-screen-order');
                var label = sel && sel.selectedOptions[0] ? sel.selectedOptions[0].textContent.trim() : mem.pick;
                return 'Screens run ' + label.toLowerCase() + ' within each beach; saved with the project.';
            },
            after: closeExport
        },
        wiringTick: {
            window: 'export:binder',
            target: '#export-binder-wiring', place: 'left', title: 'The wiring sheets',
            body: 'One Wiring tick puts a Power Wiring sheet after each Power map and a Data Wiring sheet after each Data map.',
            before: openExport,
            act: function (t) {
                var box = $('#export-binder-wiring');
                t.mem.start = box.checked;
                return (box.checked ? t.click(box).then(function () { return t.pause(500); }) : Promise.resolve()).then(function () {
                    t.mem.mid = $('#export-binder-wiring').checked;
                    return t.click('#export-binder-wiring');
                }).then(function () { return t.pause(200); });
            },
            check: function (mem) {
                var box = $('#export-binder-wiring');
                return box && box.checked && !mem.mid ? 'Wiring is on: every circuit to its breakout, every port to its socket.' : null;
            },
            after: closeExport
        },
        // The Fiber page (1.6.0, app-binder-fiber.js): one sheet after the
        // processors for a show that uses fiber - the guide's breakout box
        // took a TAC in Fiber to the box - every processor to its breakout
        // boxes, a row per link, with the strand maps and the fiber cables
        // to pull. The tick shows only on a show with fiber; it goes off
        // and on, and the set is planned until the page is in it.
        fiberPage: {
            since: '1.6.0',
            window: 'export:binder',
            target: '#export-binder-fiber-label', place: 'left', title: 'The Fiber page',
            body: 'A show with fiber gets a Fiber page after the processors: each processor to its breakout boxes, a row per link with its strands at both ends, then the strand maps and the fiber cables to pull.',
            before: openExport,
            act: function (t) {
                var box = $('#export-binder-fiber');
                if (!box) return Promise.reject(new Error('no Fiber tick'));
                return (box.checked ? t.click(box).then(function () { return t.pause(500); }) : Promise.resolve()).then(function () {
                    t.mem.mid = $('#export-binder-fiber').checked;
                    return t.click('#export-binder-fiber');
                }).then(function () {
                    return t.wait(function () {
                        var a = A();
                        if (!$('#export-binder-fiber').checked) return null;
                        var hit = a.planBinder(a.readBinderOptions()).find(function (p) { return p.kind === 'fiber'; });
                        if (hit) t.mem.number = hit.number;
                        return hit || null;
                    }, 4000);
                }).then(function (hit) {
                    if (!hit) throw new Error('the binder planned no Fiber page');
                    return t.pause(PACE.acted);
                });
            },
            check: function (mem) {
                var box = $('#export-binder-fiber');
                return box && box.checked && !mem.mid && mem.number
                    ? 'Fiber is on: the Fiber page prints as sheet ' + mem.number + ', after the processors.' : null;
            },
            after: closeExport
        },
        titleBlock: {
            window: 'export:binder',
            target: '#export-binder-title-block', place: 'left', title: 'Border and title block',
            body: 'Off, the drawing takes the whole sheet inside a small margin; on, every sheet wears its border and the title block column.',
            before: openExport,
            act: function (t) {
                // Two clicks from wherever the preference stands: the tick
                // goes over and back, and the note reads where it landed.
                t.mem.start = $('#export-binder-title-block').checked;
                return t.click('#export-binder-title-block').then(function () {
                    t.mem.mid = $('#export-binder-title-block').checked;
                    return t.pause(650);
                }).then(function () {
                    return t.click('#export-binder-title-block');
                }).then(function () { return t.pause(200); });
            },
            check: function (mem) {
                var box = $('#export-binder-title-block');
                if (!box || mem.mid === mem.start || box.checked !== mem.start) return null;
                return box.checked
                    ? 'Border and title block are back on for every sheet; remembered as a preference.'
                    : 'Border and title block are off again: the drawing takes the whole sheet; remembered as a preference.';
            },
            after: closeExport
        },
        // Every export in the File menu (1.5.2, app-menubar.js): Export
        // SVG, Export PDF and Export Resolume XML open the Export dialog
        // with that format picked. Opened and cancelled; nothing is saved.
        fileExports: {
            since: '1.5.2',
            target: '[data-menu="file"]', place: 'bottom', title: 'Exports in the File menu',
            avoid: ['#menu-file [data-action="export-svg"]', '#export-cancel'],
            body: 'Export SVG, Export PDF and Export Resolume XML sit in the File menu with the other exports. Each opens the Export dialog with that format picked; Cancel closes it.',
            before: function () { closeExport(); hideMenus(); },
            act: function (t) {
                return t.click('[data-menu="file"]').then(function () {
                    return t.wait(function () { var m = $('#menu-file'); return m && m.style.display === 'block' ? m : null; });
                }).then(function (m) {
                    if (!m) throw new Error('the File menu did not open');
                    return t.spot(m).then(function () { return t.pause(PACE.opened); });
                }).then(function () {
                    return t.click('#menu-file [data-action="export-svg"]');
                }).then(function () {
                    return t.wait(function () { var f = $('#export-format'); return exportOpen() && f && f.value === 'svg'; });
                }).then(function (ok) {
                    if (!ok) throw new Error('the Export dialog did not open on SVG');
                    t.mem.svg = true;
                    return t.spot($('#export-modal .modal-content')).then(function () { return t.pause(PACE.opened); });
                }).then(function () {
                    return t.click('#export-cancel');
                }).then(function () {
                    return t.wait(function () { return !exportOpen(); });
                });
            },
            check: function (mem) {
                return mem.svg && !exportOpen() ? 'Export SVG opened the Export dialog with SVG picked; Cancel closed it and nothing was saved.' : null;
            },
            after: function () { hideMenus(); closeExport(); }
        },
        preferences: {
            target: '#btn-preferences', place: 'bottom', title: 'Preferences',
            avoid: ['#btn-preferences', '#preferences-modal .pm-tabstrip'],
            body: 'App-wide defaults in eight tabs. The Binder tab holds the sheet size, the logo, the screen order and the title block default.',
            before: function () { closeExport(); },
            act: function (t) {
                return t.click('#btn-preferences').then(function () {
                    return t.wait(function () { var m = $('#preferences-modal'); return m && m.style.display === 'block' ? m : null; });
                }).then(function (m) {
                    if (!m) throw new Error('Preferences did not open');
                    return t.spot(m.querySelector('.modal-content') || m).then(function () {
                        return t.pause(PACE.opened);
                    }).then(function () {
                        return t.click('#preferences-modal .pm-tabstrip .view-tab[data-key="binder"]', { rest: PACE.acted });
                    });
                });
            },
            check: function () {
                var tab = $('#preferences-modal .pm-tabstrip .view-tab[data-key="binder"]');
                return tab && tab.classList.contains('active') ? 'The Binder tab: a default applies to what you create next.' : null;
            },
            after: function () { closePrefs(); }
        },
        // Mirror a screen by dragging (owner, 2026-11-01: "Mirroring is
        // driven by the card's existing Copy setting plus dragging, NOT by a
        // Screen Info picker"). NovaStar's H_4xfiber in Copy mode: "OPT 3
        // copies the output on OPT 1, while OPT 4 copies the output on OPT
        // 2". The guide's own MX40 Pro stays as the steps before left it, so
        // an H9 with an H_4xfiber in Copy and four CVT10s, and two matched
        // IMAG screens with IMAG L already on the card, are put in for you;
        // the card's drag onto IMAG R is made for real.
        mirrorScreen: {
            since: '1.6.0',
            target: function () {
                var a = A();
                var hit = null;
                (a._processorsResolved || []).some(function (p) {
                    return (p.slots || []).some(function (s) {
                        if (s && s.card && s.card.copyTrunks === 'mirror') { hit = s.card; return true; }
                        return false;
                    });
                });
                return hit ? '[data-hwdock="card-' + hit.id + '"]' : '[data-hwdock^="card-"]';
            },
            place: 'top', title: 'Mirror a screen',
            body: 'An H_4xfiber in Copy mode sends OPT 1 and 2 out again on OPT 3 and 4, and IMAG L is already on it. Drag the card onto IMAG R and IMAG R becomes its copy, with its runs off the copy boxes.',
            before: function () { closePrefs(); hideMenus(); closePopover(); switchView('data-flow'); },
            act: function (t) {
                var a = A(), w = wall(), pid = null, cid = null, left = null, right = null;
                var addImag = function (name, dx) {
                    return j('POST', '/api/layer/add', {
                        name: name, columns: 4, rows: 3,
                        cabinet_width: w.cabinet_width, cabinet_height: w.cabinet_height,
                        offset_x: (Number(w.offset_x) || 0) + dx,
                        offset_y: (Number(w.offset_y) || 0) + w.rows * w.cabinet_height + 200
                    }).then(function (layer) {
                        practiceScreen(layer);
                        layer.processorType = 'novastar-armor';
                        a.upsertProjectLayer(layer);
                        a.updateLayers([layer]);
                        return layer;
                    });
                };
                return j('POST', '/api/processors', { deviceId: 'novastar-h9' }).then(function (st) {
                    pid = st.resolved[st.resolved.length - 1].id;
                    return j('PUT', '/api/processors/' + pid + '/slots/0', { deviceId: 'novastar-card-h-4xfiber' });
                }).then(function (st) {
                    var h = st.resolved.find(function (p) { return p.id === pid; });
                    cid = h.slots[0].card.id;
                    return j('PUT', '/api/processors/' + pid + '/cards/' + cid, { mode: 'copy' });
                }).then(function () {
                    return [0, 1, 2, 3].reduce(function (chain) {
                        return chain.then(function () {
                            return j('POST', '/api/processors/' + pid + '/cards/' + cid + '/cvts', { deviceId: 'novastar-cvt10', pair: false });
                        });
                    }, Promise.resolve());
                }).then(function () {
                    return addImag('IMAG L', 0);
                }).then(function (l) {
                    left = l;
                    return addImag('IMAG R', 4 * w.cabinet_width + 200);
                }).then(function (r) {
                    right = r;
                    t.mem.left = left.id; t.mem.right = right.id; t.mem.card = cid;
                    return a.refreshProcessors();
                }).then(function () {
                    return a._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                        { layerId: String(left.id), cardId: cid }, null, 'Place Ports');
                }).then(function () {
                    frameLayers([a.project.layers.find(function (l) { return l.id === t.mem.left; }),
                                 a.project.layers.find(function (l) { return l.id === t.mem.right; })]);
                    a.saveState('Add Layer');
                    return t.wait(function () { return $('[data-hwdock="card-' + cid + '"]'); });
                }).then(function (handle) {
                    if (!handle) throw new Error('the H_4xfiber is not in the tray');
                    var r = a.project.layers.find(function (l) { return l.id === t.mem.right; });
                    return t.drag('[data-hwdock="card-' + cid + '"]', t.cabinetPoint(r, { index: lastCabinet(r) }));
                }).then(function () {
                    return t.wait(function () {
                        var scr = ((a._assignment && a._assignment.screens) || []).find(function (s) { return s.layerId === String(t.mem.right); });
                        return scr && scr.ports.length && scr.ports.every(function (p) { return p.source === 'mirror'; }) ? scr : null;
                    });
                });
            },
            check: function (mem) {
                var a = A();
                var r = (a.project.layers || []).find(function (l) { return l.id === mem.right; });
                if (!r || String(r.dataMirrorOf) !== String(mem.left)) return null;
                var scr = ((a._assignment && a._assignment.screens) || []).find(function (s) { return s.layerId === String(mem.right); });
                if (!scr || !scr.ports.length || !scr.ports.every(function (p) { return p.source === 'mirror'; })) return null;
                var found = a._dockFindCard ? a._dockFindCard(mem.card) : null;
                var box = found ? (found.card.cvts || []).find(function (b) {
                    return (b.ports || []).some(function (p) { return p.number === scr.ports[0].port; });
                }) : null;
                return 'IMAG R mirrors IMAG L: its ' + scr.ports.length + (scr.ports.length === 1 ? ' port comes' : ' ports come')
                    + ' off ' + (box ? (box.displayTitle + ' on ' + box.trunkTitle) : 'the copy box') + '.';
            },
            after: function () { closePopover(); }
        },
        // Where a port plugs in (1.6.0, app-mirror-screens.js
        // _buildCardPlugRows): on an MX40 Pro each port an OPT also carries
        // plugs in at the unit's own RJ45 or at the box, never both. The
        // CVT10 on OPT 1 is plain RJ45 and the MX40 Pro's own outputs are
        // etherCON, so a port's run is named by where it plugs in: Cat6 at
        // the box, etherCON at the unit (runText, as the pull sheet lists it).
        portPlug: {
            since: '1.6.0',
            target: function () { var c = card(); return c ? '[data-hwpop="card-' + c.id + '"]' : '#hardware-dock-body .hw-dock-gear'; },
            place: 'top', title: 'RJ45 or the box',
            avoid: [function () { var c = card(), b = box(); return c && b ? '[data-lrd-field="processor-card-plug-' + c.id + '-' + b.id + '"]' : null; }],
            body: 'A port an OPT carries plugs in at one place, the MX40 Pro&rsquo;s own RJ45 or the box. Pick it in the &#9881; and its cable is named for that connector: Cat6 at the CVT10, etherCON at the MX40 Pro.',
            before: function () { closePrefs(); hideMenus(); closePopover(); switchView('data-flow'); },
            act: function (t) {
                var a = A(), c = card(), b = box();
                if (!c || !b) throw new Error('there is no breakout box on the processor');
                var seg = '[data-lrd-field="processor-card-plug-' + c.id + '-' + b.id + '"] [data-level="card"]';
                // The first of the box's ports with no length typed and no
                // snake, at the box or on the unit's own record (the loose
                // port's 50 ft run sits there), read as the pull sheet
                // lists it before the move ("Cat6 no length").
                var own = owner();
                var kept = (own && own.rec && own.rec.portCables) || {};
                var socket = null;
                var nums = b.portNumbers || [];
                for (var i = 0; i < nums.length && !socket; i++) {
                    var n = nums[i];
                    if (!a.dataPortCable(c.id, n) && !kept[String(n)]) socket = n;
                }
                if (!socket) throw new Error('every port on ' + (b.displayTitle || 'the box') + ' has a cable');
                t.mem.socket = socket;
                t.mem.box = b.displayTitle || 'the box';
                t.mem.before = a.runText(null, { cardId: c.id, port: socket });
                return t.click('[data-hwpop="card-' + c.id + '"]').then(function () {
                    return t.wait(function () { return popover() && $(seg); });
                }).then(function (el) {
                    if (!el) throw new Error('the card has no RJ45 or box choice for ' + t.mem.box);
                    return t.click(seg, { hover: 400, rest: 1200 });
                }).then(function () {
                    return t.wait(function () {
                        var q = card();
                        var port = q && (q.ports || []).find(function (p) { return p.number === socket; });
                        return port && port.plug === 'card';
                    });
                });
            },
            check: function (mem) {
                var c = card();
                var port = c && (c.ports || []).find(function (p) { return p.number === mem.socket; });
                var now = c ? A().runText(A().dataPortCable(c.id, mem.socket), { cardId: c.id, port: mem.socket }) : '';
                if (!port || port.plug !== 'card' || !/etherCON/.test(now) || !/Cat6/.test(mem.before || '')) return null;
                return 'The ports ' + mem.box + ' carried plug in at the MX40 Pro now: port ' + mem.socket
                    + ' reads ' + now + ' on the pull sheet, where it read ' + mem.before + '.';
            },
            after: function () { closePopover(); }
        },
        // Z flow patterns for power (the owner's ruling, 2026-11-01): the
        // picker's bottom row, where every row starts again from the same
        // side. The step adds WIDE WALL under the other screens, 24 x 4 of
        // the wall's cabinets at 60 W on 208V / 20A: a circuit carries
        // 3,328 W, so two rows (2,880 W) share one, and with Top-left Z the
        // second row starts at the left again instead of running back.
        powerZPattern: {
            since: '1.6.0',
            target: '.power-flow-pattern-btn[data-pattern="tl-h-z"]', place: 'right', title: 'Z patterns for power',
            avoid: ['.power-flow-pattern-btn[data-pattern="tl-h-z"]'],
            body: 'The bottom row of Flow Pattern holds the Z patterns. Each row starts again from the same side as the first instead of running back, with a diagonal return between rows.',
            before: function () { closePrefs(); hideMenus(); closePopover(); switchView('power'); },
            act: function (t) {
                var a = A(), w = wall();
                var bottom = screens().reduce(function (m, l) {
                    return Math.max(m, (Number(l.offset_y) || 0) + (Number(l.rows) || 0) * (Number(l.cabinet_height) || 0));
                }, 0);
                var find = function () {
                    return (a.project.layers || []).find(function (x) { return x.id === t.mem.layer; }) || null;
                };
                return j('POST', '/api/layer/add', {
                    name: 'WIDE WALL', columns: 24, rows: 4,
                    cabinet_width: w.cabinet_width, cabinet_height: w.cabinet_height,
                    offset_x: (Number(w.offset_x) || 0), offset_y: bottom + 200
                }).then(function (layer) {
                    practiceScreen(layer);
                    a.setScreenVoltage(layer, 208);
                    layer.powerAmperage = 20;
                    layer.powerAmperageCustom = 20;
                    layer.panelWatts = 60;
                    layer.powerMaximize = false;
                    layer.powerOrganized = true;
                    layer.powerFlowPattern = 'tl-h';
                    a.upsertProjectLayer(layer);
                    a.updateLayers([layer]);
                    t.mem.layer = layer.id;
                    var l = find();
                    a.selectLayer(l);
                    frameLayers([l]);
                    a.saveState('Add Layer');
                    return t.click('.power-flow-pattern-btn[data-pattern="tl-h-z"]');
                }).then(function () {
                    return t.wait(function () { var l = find(); return l && l.powerFlowPattern === 'tl-h-z'; });
                });
            },
            check: function (mem) {
                var l = (A().project.layers || []).find(function (x) { return x.id === mem.layer; });
                if (!l || l.powerFlowPattern !== 'tl-h-z') return null;
                var c = (A().calculatePowerAssignments(l).circuits || [])[0] || [];
                var next = c[l.columns];
                if (!next || next.row !== 1 || next.col !== 0) return null;
                return 'Circuit 1 runs row 1 left to right, then row 2 starts again at the left.';
            }
        },
        // Circuit numbers (powerNumberOrder): shown only where Organized
        // cuts a row too long for one circuit. WIDE WALL goes to 150 W a
        // cabinet, so a row (3,600 W) is over a circuit (3,328 W) and is cut
        // into circuits of 22 and 2; Down numbers them down the stacks.
        circuitNumbers: {
            since: '1.6.0',
            target: '#power-number-order-row', place: 'right', title: 'Circuit numbers',
            avoid: ['#power-number-down'],
            body: 'A row too long for one circuit is cut into circuits of whole panels. Circuit numbers sets their order: Across goes along each row, Down goes down the stacks and starts each new stack back at the top.',
            before: function () { closePrefs(); hideMenus(); closePopover(); switchView('power'); },
            act: function (t) {
                var a = A();
                var l = (a.project.layers || []).find(function (x) { return x.name === 'WIDE WALL'; });
                if (!l) throw new Error('WIDE WALL is missing');
                t.mem.layer = l.id;
                a.selectLayer(l);
                l.panelWatts = 150;
                a.updateLayers([l]);
                a.saveState('Change Panel Watts');
                a.loadLayerToInputs();
                a.updatePowerCapacityDisplay();
                return t.wait(function () {
                    var row = $('#power-number-order-row');
                    return row && row.style.display !== 'none' ? row : null;
                }).then(function (row) {
                    if (!row) throw new Error('Circuit numbers is not shown for WIDE WALL');
                    return t.click('#power-number-down');
                }).then(function () {
                    return t.wait(function () {
                        var x = (a.project.layers || []).find(function (y) { return y.id === t.mem.layer; });
                        return x && x.powerNumberOrder === 'down';
                    });
                });
            },
            check: function (mem) {
                var l = (A().project.layers || []).find(function (x) { return x.id === mem.layer; });
                if (!l || l.powerNumberOrder !== 'down') return null;
                var c = A().calculatePowerAssignments(l).circuits || [];
                if (!c[1] || !c[1][0] || c[1][0].row !== 1) return null;
                return 'Circuit 2 now starts row 2 of WIDE WALL, under circuit 1.';
            }
        },
        // Redraw several ports as one (1.6.0, app-merge-runs.js; the owner,
        // 2026-11-02: "redraw all of those as one port"). LEFTOVERS is six
        // 512 x 256 cabinets wide on NovaStar Legacy, five to a port, so
        // every row is a port of five and a leftover of one; numbered Down,
        // the four leftovers are ports 5-8. Shift+drag picks them, the menu
        // redraws them as one, and four clicks draw it: 8 ports become 5.
        redrawAsOne: {
            since: '1.6.0',
            target: '#main-canvas', place: 'top', title: 'Redraw several ports as one',
            body: 'Shift+click runs, or Shift+drag a box across them, to pick their ports. Right-click and pick Redraw ports as one, then click the cabinets in order: the new port keeps the first number and the ports after it close up.',
            before: function () { closePrefs(); hideMenus(); closePopover(); switchView('data-flow'); },
            act: function (t) {
                var a = A(), w = wall();
                var bottom = screens().reduce(function (m, l) {
                    return Math.max(m, (Number(l.offset_y) || 0) + (Number(l.rows) || 0) * (Number(l.cabinet_height) || 0));
                }, 0);
                var find = function () {
                    return (a.project.layers || []).find(function (x) { return x.id === t.mem.layer; }) || null;
                };
                var at = function (row, col) {
                    var l = find();
                    var i = l.panels.findIndex(function (p) { return p.row === row && p.col === col; });
                    return t.cabinetPoint(l, { index: i });
                };
                return j('POST', '/api/layer/add', {
                    name: 'LEFTOVERS', columns: 6, rows: 4,
                    cabinet_width: 512, cabinet_height: 256,
                    offset_x: (w && Number(w.offset_x)) || 0, offset_y: bottom + 200
                }).then(function (layer) {
                    practiceScreen(layer);
                    layer.processorType = 'novastar-armor';
                    layer.flowPattern = 'tl-h';
                    layer.portMappingMode = 'organized';
                    layer.portNumberOrder = 'down';
                    a.upsertProjectLayer(layer);
                    a.updateLayers([layer]);
                    t.mem.layer = layer.id;
                    var l = find();
                    a.selectLayer(l);
                    frameLayers([l]);
                    a.saveState('Add Layer');
                    a.updatePortCapacityDisplay();
                    t.mem.before = a.getLayerPortsRequired(l);
                    return t.pause(PACE.rest);
                }).then(function () {
                    // Shift+drag down the leftover column: ports 5-8 light.
                    var from = at(0, 5), to = at(3, 5);
                    return t.moveTo(from, { badge: 'Shift' }).then(function () {
                        press(true);
                        t.canvasDown(from, { shiftKey: true });
                        return t.pause(PACE.dragPress);
                    }).then(function () {
                        return t.canvasGlide(to, { shiftKey: true });
                    }).then(function () {
                        t.canvasUp(to, { shiftKey: true });
                        press(false);
                        badge('');
                        return t.pause(PACE.rest);
                    });
                }).then(function () {
                    t.mem.picks = a.portPicksFor(find());
                    return t.rightClick(at(1, 5));
                }).then(function () {
                    var item = $('[data-action="ovr-merge"]');
                    t.mem.label = item ? item.textContent : '';
                    return t.pickMenu('ovr-merge');
                }).then(function () {
                    return t.wait(function () { return a._mergeRedraw && a._mergeRedraw.ready; }, 2500);
                }).then(function () {
                    return [[0, 5], [1, 5], [2, 5], [3, 5]].reduce(function (chain, rc) {
                        return chain.then(function () {
                            var q = at(rc[0], rc[1]);
                            return t.hover(q).then(function () {
                                press(true);
                                t.canvasDown(q, {});
                                return t.pause(70);
                            }).then(function () {
                                t.canvasUp(q, {});
                                press(false);
                                ripple(q.x, q.y);
                                return t.pause(PACE.rest);
                            });
                        });
                    }, Promise.resolve());
                }).then(function () {
                    return t.wait(function () { return !a._mergeRedraw; }, 2500);
                });
            },
            check: function (mem) {
                var a = A();
                var l = (a.project.layers || []).find(function (x) { return x.id === mem.layer; });
                if (!l || a._mergeRedraw || (mem.picks || []).join() !== '5,6,7,8') return null;
                var five = (a.calculatePortAssignments(l) || []).filter(function (x) { return x.port === 5; });
                var n = a.getLayerPortsRequired(l);
                if (five.length !== 4 || !five.every(function (x) { return x.panel.col === 5; }) || n !== 5) return null;
                return (mem.label || 'Redraw ports 5-8 as one') + ': port 5 runs down the last column, and LEFTOVERS needs '
                    + n + ' ports instead of ' + mem.before + '.';
            }
        },
        // Alt+drag picks ports in Data the way it picks circuits in Power
        // (1.6.0, canvas-input.js's armed Alt+press, app-merge-runs.js
        // sweepPortPicks; the owner, 2026-11-02: "Data should match
        // Power"). On LEFTOVERS after the redraw, ports 1-4 are its rows
        // and port 5 its last column, so a drag down the first column
        // crosses ports 1-3 and the right-click names them. Picking is all
        // the step does: the menu closes and the picks drop at its end.
        sweepPorts: {
            since: '1.6.0',
            target: '#main-canvas', place: 'top', title: 'Pick ports with Alt',
            body: 'Hold Alt and drag across runs to pick every port the drag crosses, then right-click to redraw them as one. Alt+click alone still redraws one port.',
            before: function () { closePrefs(); hideMenus(); closePopover(); switchView('data-flow'); },
            act: function (t) {
                var a = A();
                var l = (a.project.layers || []).find(function (x) { return x.name === 'LEFTOVERS'; });
                if (!l) throw new Error('LEFTOVERS is missing');
                t.mem.layer = l.id;
                a.selectLayer(l);
                frameLayers([l]);
                a.clearPortPicks();
                var at = function (row, col) {
                    var i = l.panels.findIndex(function (p) { return p.row === row && p.col === col; });
                    return t.cabinetPoint(l, { index: i });
                };
                var from = at(0, 0), to = at(2, 0);
                return t.hover(from, { badge: 'Alt' }).then(function () {
                    press(true);
                    t.canvasDown(from, { altKey: true });
                    return t.pause(PACE.dragPress);
                }).then(function () {
                    t.canvasMove({ x: from.x + 6, y: from.y + 6 }, { altKey: true });
                    return t.canvasGlide(to, { altKey: true }, PACE.sweep);
                }).then(function () {
                    t.canvasMove(to, { altKey: true });
                    return t.pause(PACE.hover);
                }).then(function () {
                    t.canvasUp(to, { altKey: true });
                    press(false);
                    badge('');
                    t.mem.picks = a.portPicksFor(l);
                    return t.pause(PACE.sweepRest);
                }).then(function () {
                    return t.rightClick(at(1, 0));
                }).then(function () {
                    var item = $('[data-action="ovr-merge"]');
                    t.mem.label = (item && item.style.display !== 'none') ? item.textContent : '';
                    return t.pause(PACE.rest);
                }).then(function () {
                    a.hideContextMenu();
                    a.clearPortPicks();
                });
            },
            check: function (mem) {
                if ((mem.picks || []).join() !== '1,2,3' || mem.label !== 'Redraw ports P1-P3 as one') return null;
                return 'One Alt+drag down LEFTOVERS picked ports 1-3; the menu offered ' + mem.label + '.';
            }
        },
        helpMenu: {
            target: '[data-menu="help"]', place: 'bottom', title: 'Help',
            body: 'Every guide lives under Help: Quick Start, What&rsquo;s New, the Advanced Guide and the keyboard shortcuts.',
            before: function () { closePrefs(); },
            act: function (t) {
                return t.click('[data-menu="help"]').then(function () {
                    return t.wait(function () { var m = $('#menu-help'); return m && m.style.display === 'block' ? m : null; });
                }).then(function (m) { return t.spot(m).then(function () { return t.pause(PACE.opened); }); });
            },
            check: function () {
                var m = $('#menu-help');
                return m && m.style.display === 'block' ? 'Reopen any guide from here.' : null;
            },
            after: function () { hideMenus(); }
        },
        outroAdvanced: {
            title: 'That&rsquo;s the guide', center: true,
            body: 'Done puts your own project back. Reopen any guide from Help.',
            before: function () { hideMenus(); closeExport(); closePrefs(); }
        },
        outroQuick: {
            title: 'You&rsquo;re all set', center: true,
            body: 'Done puts your own project back. Reopen this guide any time from Help &rsaquo; Quick Start Guide, or take the full walkthrough below.',
            before: function () { hideMenus(); closeExport(); closePrefs(); }
        }
    };
    // The recoveries after a clear: the same drags as the first landing,
    // told as the way back. The act is shared; the check asks for the
    // whole unit, since the clear left nothing to build on.
    STEPS.dropProcessorAgain = Object.assign({}, STEPS.dropProcessor, {
        title: 'Put it all back',
        body: 'Drag the processor onto the wall again and every port lands from the first free socket. A cleared processor is one drag from whole.',
        check: function (mem) {
            var ps = wallPins();
            if (ps.length <= mem.before || ps.length !== portsNeeded()) return null;
            var socks = ps.map(function (p) { return Number(p.port); }).sort(function (a, b) { return a - b; });
            return 'All ' + ps.length + ' ports are back on sockets ' + socks[0] + ' to ' + socks[socks.length - 1]
                + (flagOk() ? '; the flag is green.' : '.');
        }
    });
    STEPS.dropMultiAgain = Object.assign({}, STEPS.dropMulti, {
        title: 'Land it again',
        body: 'Drag multi 1 over the screen once more and its circuits fill from the first. A cleared multi is one drag from whole.',
        check: function (mem) {
            var n = mem.landed ? mem.landed() : 0;
            var d = distro();
            var size = A().socaBoxSize ? A().socaBoxSize(wall()) : 6;
            if (!n || n < Math.min(size, A().screenCircuits(wall()).length)) return null;
            return (d.name || 'SL') + ' multi 1 holds ' + n + ' of ' + size + ' circuits again.';
        }
    });

    // ── the tours: ordered step keys, plus what each seeds silently ──────
    // A tour that skips a step another depends on seeds that prerequisite
    // before it starts, so every visible step is still one action.
    var TOURS = {
        quick: {
            title: 'Quick Start',
            seed: { name: 'Demo Show' },
            steps: ['introQuick', 'cabinetSize', 'gridSize', 'processing', 'addProcessor',
                    'dropProcessor', 'addDistro', 'dropMulti', 'exportBinder', 'outroQuick']
        },
        advanced: {
            title: 'Advanced Guide',
            seed: { name: 'New Show', layer: { panelWatts: 100, powerBreakoutType: 'soca-powercon' } },
            steps: ['introAdvanced', 'projectName', 'cabinetSize', 'panelName', 'startPage', 'startPanel', 'sameAsLast', 'avgPower', 'gridSize', 'fit', 'blankCabinet',
                    'cabinetIdStyle', 'showLook', 'processing', 'flowPattern', 'zPattern', 'addProcessor',
                    'nameProcessor', 'redundancy', 'backupProcessor', 'mixedRedundancy', 'cardNames', 'dropProcessor', 'releasePort', 'attachmentFlag', 'pinPort',
                    'clearPortByMenu', 'clearCard', 'dropProcessorAgain',
                    'snakePorts', 'cableSheet', 'snakeHomeRun', 'loosePortLength', 'dataJumpers', 'dataCableTags',
                    'overrideRun', 'addBreakoutBox', 'fiberMode', 'boxFiber', 'fiberStrands', 'fiberExtension', 'panelWatts', 'panelInput', 'breakoutType',
                    'addDistro', 'nameDistro',
                    'distroPhase', 'distroRating', 'distroMain', 'distroPreset', 'distroRows',
                    'dropMulti', 'clearCircuit', 'clearMultiByMenu', 'dropMultiAgain',
                    'multiCableSheet', 'powerJumpers', 'jumperNames', 'pullPanels', 'cableUnit', 'cableStock', 'cableStockPieces',
                    'cableStockPerKind', 'powerCableTags',
                    'powerColumns', 'splitters', 'takeOver', 'customPower', 'customDraw', 'sweepShare', 'balance',
                    'addService', 'serviceRating', 'serviceDistro', 'feederLength',
                    'addBeach', 'screenBeach', 'addScreen', 'beachByMenu', 'crossScreens', 'groupScreens',
                    'exportBinder', 'screenOrder', 'wiringTick', 'fiberPage', 'titleBlock', 'fileExports', 'preferences',
                    'mirrorScreen', 'portPlug', 'portNumbers', 'portsMinimum', 'powerZPattern', 'circuitNumbers',
                    'redrawAsOne', 'sweepPorts', 'helpMenu', 'outroAdvanced']
        }
    };

    function toursAsLists() {
        var out = {};
        Object.keys(TOURS).forEach(function (name) {
            out[name] = TOURS[name].steps.map(function (k) { return STEPS[k]; });
        });
        return out;
    }

    window.QuickStart = {
        start: function () { return show('quick'); },
        startAdvanced: function () { return show('advanced'); },
        // What's New: the Advanced Guide steps whose `since` is newer than
        // `after` and not newer than `upTo` (keys, guide order), and a run
        // of just those steps, each from its own entry snapshot.
        newSteps: newSteps,
        startSteps: startSteps,
        startTour: function (name) { return TOURS[name] ? show(name) : Promise.resolve(); },
        tours: toursAsLists,
        steps: function () { return STEPS; },
        // The windows step `key` works in, read now (its `window`).
        windowsOf: function (key) { return windowsOf(STEPS[key]); },
        end: end,
        setSpeed: function (n) { speed = Math.max(0.25, Number(n) || 1); },
        // Go to step n (1-based); {apply: true} runs the steps between
        // instead of restoring the shipped snapshot.
        jumpTo: jumpTo,
        // The entry snapshots taken so far this run, by step index.
        snaps: function () { return S.snaps; },
        // The tour's signature, as the shipped snapshot file carries it.
        signature: signature,
        state: function () {
            return { tour: S.name, index: S.idx, running: S.running, visible: S.visible,
                     jumpedVia: S.jumpedVia, steps: S.keys.slice(), phase: S.phase };
        }
    };

    // The boot's own business, from load until the stash is recovered and
    // the first-run guide has either shown or decided not to. The startup
    // panel picker (app-presets.js maybeOpenStartupPicker) waits it out, so
    // the guide never opens over the picker and closes it.
    var autoPending = true;
    window.QuickStart.autoPending = function () { return autoPending; };

    function maybeAutoShow() {
        if (disabled()) { autoPending = false; return; }
        // Never auto-show inside an automated browser (Playwright/Selenium set
        // navigator.webdriver). The tour's click-catcher would otherwise block
        // E2E tests. Real users are unaffected; they can still open it manually.
        if (navigator.webdriver) { autoPending = false; return; }
        var tries = 0;
        var t = setInterval(function () {
            tries++;
            if (document.querySelector('#view-tabs') && document.querySelector('#right-sidebar')
                    && window.app && window.app.project && window.canvasRenderer) {
                clearInterval(t);
                setTimeout(function () {
                    try { show('quick'); } finally { autoPending = false; }
                }, 400);
            } else if (tries > 40) {
                clearInterval(t);
                autoPending = false;
            }
        }, 150);
    }

    // Boot order: first the stash (a tour that never ended), then - never
    // under automation - the first-run tour.
    function onReady() {
        var tries = 0;
        var t = setInterval(function () {
            tries++;
            var a = window.app;
            if (document.querySelector('#view-tabs') && a && a.project
                    && Array.isArray(a.project.layers) && window.canvasRenderer
                    && typeof a._syncRestoredProject === 'function') {
                clearInterval(t);
                recoverStash().then(function (recovered) {
                    if (!recovered) maybeAutoShow();
                    else autoPending = false;
                }, function () { autoPending = false; });
            } else if (tries > 80) {
                clearInterval(t);
                autoPending = false;
            }
        }, 150);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
