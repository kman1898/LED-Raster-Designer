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
 *   - What's New in 1.0: the surfaces that changed. Help -> What's New in
 *     1.0, and the splash's walkthrough button.
 *   - Advanced Guide: the whole show, built step by step in front of you.
 *
 * Fully self-contained and offline (no CDN).
 *
 * A step is { target, place, title, body, center?, before?, after?, act?,
 * check? }. `act(t)` is the demonstration and `t` the toolkit (moveTo, click,
 * type, select, drag, rightClick, pickMenu, cabinetPoint, wait, pause, say,
 * spot). `check(mem)` returns the result note when the action took, or null
 * when it did not. The three tours are composed from ONE step library (STEPS)
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

    // Playback speed. 1 is the shipped pace (a step's act takes 2-6 s);
    // QuickStart.setSpeed(3) runs the same gestures three times faster for
    // an automated drive. Every wait scales with it.
    var speed = 1;
    function ms(n) { return Math.max(0, Math.round(n / speed)); }

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
    function proc() { return ((A() && A()._processorsResolved) || [])[0] || null; }
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
    function sparePinSocket() {
        var c = card();
        if (!c) return 20;
        for (var n = 20; n <= 40; n++) {
            var face = $('[data-hwdock="port-' + c.id + '-' + n + '"]');
            if (!face) continue;
            var tile = face.closest('.lrd-tile');
            if (tile && (tile.classList.contains('lrd-tile-occupied') || tile.classList.contains('lrd-tile-gold'))) continue;
            if (/backs up/.test(face.textContent || '')) continue;
            return n;
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
    function exportOpen() { var m = $('#export-modal'); return !!m && m.style.display === 'block'; }
    function openExport() {
        var a = A();
        if (!a || typeof a.openExportModal !== 'function') return;
        if (!exportOpen() || ($('#export-format') && $('#export-format').value !== 'binder')) {
            a.openExportModal('binder');
        }
    }
    function closeExport() { var m = $('#export-modal'); if (m) m.style.display = 'none'; }
    function closeExportUnless(next) { if (!next || !next.exportStep) closeExport(); }
    function hideMenus() {
        $$('.menu-dropdown').forEach(function (m) { m.style.display = 'none'; });
        $$('#menu-bar .menu-item.active').forEach(function (i) { i.classList.remove('active'); });
    }
    function closePrefs() {
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
    function closePopover() { var a = A(); if (a && a._hwPopoverClose) a._hwPopoverClose(); }
    function dockDropPoint() {
        // Anywhere inside the tray is the release (app-dock.js _dockHitTest
        // tests the tray's rectangle, not the element): the header bar's
        // middle is a spot no chip ever occupies.
        var dock = $('#hardware-dock');
        var r = dock.getBoundingClientRect();
        var head = $('#hw-dock-head') || dock;
        var hr = head.getBoundingClientRect();
        return { x: r.left + r.width * 0.5, y: hr.top + Math.min(14, hr.height / 2) };
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
            + '#qs-fast{display:none;position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:2000004;'
            + 'background:#2e2e2e;color:#fff;border:1px solid #3a3a3a;border-top:3px solid #e22330;border-radius:9px;'
            + 'padding:9px 16px;font:600 13px -apple-system,"Segoe UI",system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.5);}'
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
    // Eased travel at ~700 px/s, resolved on arrival; `onFrame` sees every
    // intermediate point (a drag dispatches its mousemoves from it).
    function animateTo(x, y, onFrame) {
        return new Promise(function (resolve) {
            var x0 = cur.x, y0 = cur.y;
            var dist = Math.hypot(x - x0, y - y0);
            var dur = ms(Math.max(160, Math.min(1300, dist / 700 * 1000)));
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
        var list = (step.ring || []).map(function (q) { return typeof q === 'string' ? $(q) : q; }).filter(Boolean);
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
        if (floor - top < ch) return null;
        return { x: x, y: top, p: null };
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
        var box;
        if (!r || step.center) {
            // The intro sits in the middle of the window; the first Next
            // moves the callout to its locked spot and it stays there. A
            // later step with nothing to ring yet (a control that appears
            // after its first click, the outro) uses the locked spot too.
            box = S.idx > 0 ? lockedBox(cw, ch, null, keep) : null;
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
        if (better.clear && (Math.abs(better.x - c.left) > 40 || Math.abs(better.y - c.top) > 40)) place(step);
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
            // An element that measures zero-size (a chip's face that is
            // laid out by its tile, a hidden handle) would send the cursor
            // to the top-left corner; aim at the nearest ancestor with a
            // size instead. The events still go to the element itself.
            var sized = target;
            while (sized && sized.nodeType === 1) {
                var rr = sized.getBoundingClientRect();
                if (rr.width > 0 || rr.height > 0) break;
                sized = sized.parentElement;
            }
            var c = centerOf(sized && sized.nodeType === 1 ? sized : target);
            return { el: target, x: c.x, y: c.y };
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

    // ── the toolkit a step's act(t) receives ─────────────────────────────
    var T = {
        pause: function (n) { return sleep(ms(n)); },
        // Poll a predicate until it returns something truthy (that value is
        // resolved) or the timeout passes (null).
        wait: function (fn, timeout) {
            var limit = ms(timeout == null ? 4000 : timeout);
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
            var p = resolve(target);
            if (!p) return Promise.reject(new Error('moveTo: nothing at ' + describe(target)));
            keepClear(p);
            showCursor();
            badge(o.badge || '');
            return animateTo(p.x, p.y).then(function () { return p; });
        },
        // A real click: the press (mousedown/mouseup at the point, so the
        // app's mousedown-driven handlers see the gesture) and the click.
        // `init` carries modifiers; with a modifier the click is dispatched
        // as an event so the handler reads the keys.
        click: function (target, o) {
            o = o || {};
            return T.moveTo(target, o).then(function (p) {
                var el = p.el || document.elementFromPoint(p.x, p.y);
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
                    return T.pause(tab ? 320 : 120).then(function () {
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
            return T.moveTo(target).then(function (p) {
                var el = p.el;
                if (!el) throw new Error('type: nothing at ' + describe(target));
                ripple(p.x, p.y);
                el.focus();
                if (typeof el.select === 'function') el.select();
                setValue(el, '');
                var chars = String(text).split('');
                var i = 0;
                return new Promise(function (res) {
                    (function next() {
                        if (i >= chars.length) return res();
                        setValue(el, el.value + chars[i++]);
                        setTimeout(next, ms(45));
                    })();
                }).then(function () {
                    if (o.enter) {
                        keyEvent('keydown', el, 'Enter');
                        keyEvent('keyup', el, 'Enter');
                    }
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return T.pause(120);
                }).then(function () { return el; });
            });
        },
        select: function (target, value) {
            return T.moveTo(target).then(function (p) {
                var el = p.el;
                if (!el) throw new Error('select: nothing at ' + describe(target));
                ripple(p.x, p.y);
                el.focus();
                el.value = value;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return T.pause(160).then(function () { return el; });
            });
        },
        // The tray's drag engine is mousedown on the chip, then mousemove /
        // mouseup on the DOCUMENT (app-dock.js _dockArmDrag): one move past
        // the 4 px threshold, then the path, then the release at the target
        // - so the app's own ghost chip, pending bracket and pill appear.
        drag: function (from, to, o) {
            o = o || {};
            var dest = resolve(to);
            if (!dest) return Promise.reject(new Error('drag: no destination'));
            return T.moveTo(from, o).then(function (p) {
                var el = p.el;
                if (!el) throw new Error('drag: nothing at ' + describe(from));
                press(true);
                mouse('mousedown', el, p.x, p.y, { buttons: 1 });
                return T.pause(60).then(function () {
                    mouse('mousemove', document, p.x + 6, p.y + 6, { buttons: 1 });
                    keepClear(dest);
                    return animateTo(dest.x, dest.y, function (x, y) {
                        mouse('mousemove', document, x, y, { buttons: 1 });
                    });
                }).then(function () {
                    mouse('mousemove', document, dest.x, dest.y, { buttons: 1 });
                    return T.pause(o.hover == null ? 380 : o.hover);
                }).then(function () {
                    mouse('mouseup', document, dest.x, dest.y, { buttons: 0 });
                    press(false);
                    ripple(dest.x, dest.y);
                    return T.pause(160);
                });
            });
        },
        // The app's own menu at the point, with the ghost parked there.
        rightClick: function (point, o) {
            o = o || {};
            return T.moveTo(point, { badge: 'Right-click' }).then(function (p) {
                press(true);
                ripple(p.x, p.y);
                A().showContextMenu(p.x, p.y);
                press(false);
                return T.pause(180).then(function () {
                    badge('');
                    var m = $('#context-menu');
                    if (m && m.style.display === 'block') { S.spotEl = m; settle(); }
                    return m;
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
                return T.moveTo(item).then(function (p) {
                    ripple(p.x, p.y);
                    item.click();
                    return T.pause(180);
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
        // Travel while pressed, dispatching a canvas mousemove per frame.
        canvasGlide: function (to, init) {
            keepClear(to);
            return animateTo(to.x, to.y, function (x, y) {
                mouse('mousemove', R().canvas, x, y, Object.assign({ buttons: 1 }, init || {}));
            });
        },
        // The client point of a cabinet on the wall - the same world-to-
        // client walk every canvas gesture makes (tests/test_hardware_dock.py
        // PANEL_POINT_JS). {port: n} the first cabinet of screen port n,
        // {circuit: i} the first cabinet of the i-th circuit, {index: i} the
        // i-th cabinet of the layer.
        cabinetPoint: function (layer, which) {
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
        },
        // Frame the wall (or several): zoom so the union spans ~60% of the
        // canvas width, then center it. fitToView frames the raster, and on
        // the scratch show's 5K raster the wall would be a patch in a corner.
        frame: function (layers) { frameLayers(layers); }
    };

    function frameLayers(layers) {
        var a = A(), r = R();
        layers = (layers || []).filter(Boolean);
        if (!r || !layers.length) return;
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

    // ── the engine ───────────────────────────────────────────────────────
    var S = {
        name: null, list: [], idx: -1,
        running: false, pendingNext: false, pendingEnd: null,
        snaps: [], saved: null, token: 0, visible: false, spotEl: null
    };

    function setState(v) { if (els) els.callout.setAttribute('data-qs-state', v); }
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
            if (S.running) { S.pendingNext = true; return; }
            last ? end() : go(S.idx + 1);
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

    // Go straight to step n (1-based). A step already visited is restored
    // from its entry snapshot and replayed, the way Back does. A step ahead
    // needs everything between it and here to have happened, so the steps
    // between run first - fast, cursor hidden, a banner counting them off -
    // and the step itself then plays at normal speed.
    function jumpTo(n) {
        if (!S.visible || S.running) return Promise.resolve();
        n = Math.round(n);
        if (!(n >= 1 && n <= S.list.length) || n === S.idx + 1) return Promise.resolve();
        var i = n - 1;
        if (i < S.idx) return go(i, { restore: S.snaps[i] });
        var savedSpeed = speed;
        speed = Math.max(speed, 6);
        S.fast = true;
        hideCursor();
        var chain = Promise.resolve();
        for (var k = S.idx + 1; k < i; k++) {
            (function (k) {
                chain = chain.then(function () {
                    if (!S.visible) return;
                    fastBanner('Skipping ahead to step ' + n + '… running step ' + (k + 1) + ' of ' + S.list.length);
                    return go(k);
                });
            })(k);
        }
        return chain.then(function () {
            speed = savedSpeed;
            S.fast = false;
            fastBanner('');
            if (S.visible) return go(i);
        });
    }
    function fastBanner(text) {
        if (!els) return;
        els.fast.textContent = text;
        els.fast.style.display = text ? 'block' : 'none';
    }

    function leaveCurrent(next) {
        var step = S.idx >= 0 && S.idx < S.list.length ? S.list[S.idx] : null;
        if (step && step.after) { try { step.after(next); } catch (e) { console.warn('QuickStart after()', e); } }
    }

    // Enter step i: before(), the callout, the entry snapshot (Back and
    // Replay restore it), then after a beat the act and its check.
    function go(i, opts) {
        opts = opts || {};
        if (i < 0 || i >= S.list.length || S.running) return Promise.resolve();
        var step = S.list[i];
        leaveCurrent(step);
        S.idx = i;
        S.spotEl = null;
        S.running = true;
        setState('running');
        var chain = Promise.resolve();
        if (opts.restore) chain = chain.then(function () { return restoreProject(opts.restore, 'Tutorial Back'); });
        return chain.then(function () {
            if (step.before) { try { return step.before(); } catch (e) { console.warn('QuickStart before()', e); } }
        }).then(function () {
            return step.before ? sleep(ms(260)) : null;
        }).then(function () {
            S.running = false;
            render();
            S.snaps[i] = snapshot();
            if (!step.act) { hideCursor(); return afterStep(); }
            return runAct(step);
        });
    }

    function runAct(step) {
        S.running = true;
        S.pendingNext = false;
        T.mem = {};
        setState('running');
        passthrough(true);
        showCursor();
        var token = ++S.token;
        var err = null;
        return sleep(ms(500)).then(function () {
            // The canvas may have re-framed a beat after the callout was
            // placed (a view switch resizes it); ring the target where it is
            // now and move the box only if it has come to cover it - once,
            // before the cursor starts, so the act itself never shoves it.
            settle();
            return Promise.resolve().then(function () { return step.act(T); });
        }).catch(function (e) {
            err = e;
            console.warn('QuickStart: step "' + step.title + '" failed:', e);
        }).then(function () {
            if (token !== S.token) return;   // the tour ended under us
            var note = null;
            try { note = step.check ? step.check(T.mem) : 'Done.'; }
            catch (e) { console.warn('QuickStart check()', e); }
            S.running = false;
            passthrough(false);
            badge('');
            press(false);
            showResult(note, err);
            settle();
            setState(note ? 'done' : 'failed');
            return afterStep();
        });
    }

    function afterStep() {
        if (S.pendingEnd) { var e = S.pendingEnd; S.pendingEnd = null; return end().then(e.resolve); }
        if (S.pendingNext) {
            S.pendingNext = false;
            return S.idx === S.list.length - 1 ? end() : go(S.idx + 1);
        }
    }

    function goBack() {
        if (S.idx <= 0) return;
        var i = S.idx - 1;
        return go(i, { restore: S.snaps[i] });
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
            S.idx === S.list.length - 1 ? end() : go(S.idx + 1);
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
                currentLayerId: w.currentLayerId, at: Date.now()
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
        return restoreProject(w.project, 'Tour Recovery').then(function () {
            return restorePrefs(w.prefs);
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
            a.resetHistory('Recovered');
            try { a.updateUI(); } catch (e) {}
            try { a.renderHardwareDock(); } catch (e) {}
            if (R()) { R().fitToView(); }
            clearStash();
            if (typeof a._toast === 'function') {
                a._toast('Your project was put back after an interrupted tour.', false, 6000);
            }
            return true;
        }).catch(function (e) {
            console.warn('QuickStart: recovery failed', e);
            return false;
        });
    }

    // Everything transient a step may have left standing.
    function closeTransients() {
        var a = A(), r = R();
        if (!a) return;
        try { a.hideContextMenu(); } catch (e) {}
        closePopover();
        if (a._traySweepClear) a._traySweepClear(false);
        a._sweepSelection = null;
        if (r) { r._sweepPending = null; if (r._removeSweepHud) r._removeSweepHud(); }
        if (a._overrideEditing && a.endOverrideEdit) { try { a.endOverrideEdit(); } catch (e) {} }
        if (a.updateOverrideHover) { try { a.updateOverrideHover(false, 0, 0); } catch (e) {} }
        a._dockFlagOpen = false;
        var bal = $('#balance-modal'); if (bal) bal.remove();
        $$('.canvas-add-popup, .canvas-menu-popup').forEach(function (el) { el.remove(); });
        closePrefs();
        var pp = $('#preset-picker-modal'); if (pp) pp.style.display = 'none';
        hideMenus();
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
        var cur = a.currentLayer ? a.project.layers.find(function (l) { return l.id === a.currentLayer.id; }) : null;
        a.currentLayer = cur || a.project.layers[0] || null;
        a.selectedLayerIds = new Set(a.currentLayer ? [a.currentLayer.id] : []);
        try { a.updateCustomFlowUI(); } catch (e) {}
        try { a.updateCustomPowerUI(); } catch (e) {}
        try { a._refreshPowerPanelsAfterRestore(); } catch (e) {}
        try { a.loadLayerToInputs(); } catch (e) {}
        try { a.syncRasterFromProject(); } catch (e) {}
        var entry = { project: a.project, action: label };
        return Promise.resolve(a._syncRestoredProject(entry, label)).then(function () {
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
        return restoreProject(w.project, 'Tutorial Exit').then(function () {
            return restorePrefs(w.prefs);
        }).then(function () {
            a.history = w.history;
            a.historyIndex = w.historyIndex;
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
        return j('GET', '/api/project').then(function (proj) {
            proj.name = seed.name || 'Demo Show';
            proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
            proj.beaches = []; proj.snakes = [];
            delete proj.port_assignments;
            delete proj.binder;
            delete proj.next_processor_seq;
            proj.next_group_seq = 1; proj.next_beach_seq = 1;
            // A 12 x 6 wall of 200 px cabinets beside a second one needs a
            // raster wider than 1080p; a 5K raster holds the whole show.
            proj.raster_width = 5120; proj.raster_height = 2880;
            proj.show_raster_width = 5120; proj.show_raster_height = 2880;
            (proj.canvases || []).forEach(function (c) {
                c.raster_width = 5120; c.raster_height = 2880;
                c.show_raster_width = 5120; c.show_raster_height = 2880;
            });
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
            // so the server holds the same screen.
            var fields = Object.assign({ powerVoltage: 208, powerAmperage: 20, panelWatts: 200 }, seed.layer || {});
            var l = a.project.layers[0];
            Object.keys(fields).forEach(function (k) { l[k] = fields[k]; });
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
            frameWalls();
        });
    }

    // ── show / end ───────────────────────────────────────────────────────
    function show(name) {
        var tour = TOURS[name];
        if (!tour) return Promise.resolve();
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
        S.idx = -1;
        S.home = null;
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
        var chain = saved ? sleep(ms(300)).then(function () { return restoreWorld(saved); }) : Promise.resolve();
        return chain.catch(function (e) {
            console.warn('QuickStart: restore failed', e);
        }).then(function () { S.running = false; });
    }

    // ── the step library ─────────────────────────────────────────────────
    // ONE action per step. `target` is the selector the spotlight rings (a
    // function when it names hardware minted during the tour); `place` the
    // callout's side; `body` one or two sentences in the user's terms.
    var STEPS = {
        introAdvanced: {
            title: 'The full tour', center: true,
            body: 'This tour builds a small show in front of you on a scratch project. Your own project is put back when you leave.',
            before: function () { switchView('pixel-map'); }
        },
        introWhatsNew: {
            title: 'What&rsquo;s new in 1.0', center: true,
            body: 'The tray, drag-to-wire, snakes, cable sheets, redundancy in one bar and the binder, each shown live on a scratch show. Your own project is put back when you leave.',
            before: function () { switchView('data-flow'); }
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
                var a = T.cabinetPoint(w, { index: 0 });
                var b = T.cabinetPoint(w, { index: w.panels.length - 1 });
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
                return t.moveTo(pt, { badge: 'Alt' }).then(function () {
                    press(true);
                    t.canvasDown(pt, { altKey: true });
                    return t.pause(90);
                }).then(function () {
                    t.canvasUp(pt, { altKey: true });
                    press(false);
                    ripple(pt.x, pt.y);
                    return t.wait(function () { var l = wall(); return l && l.panels.some(function (p) { return p.hidden; }); });
                });
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
                    return t.moveTo(pt, { badge: 'Shift' }).then(function () {
                        press(true);
                        t.canvasDown(pt, { shiftKey: true });
                        return t.pause(80);
                    }).then(function () {
                        return t.canvasGlide({ x: pt.x + 60, y: pt.y }, { shiftKey: true });
                    }).then(function () {
                        return t.pause(120);
                    }).then(function () {
                        t.canvasUp({ x: pt.x + 60, y: pt.y }, { shiftKey: true });
                        press(false);
                        return t.wait(function () { var l = wall(); return l && Number(l.showOffsetX) !== t.mem.x; });
                    });
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
            body: 'The eight patterns pick the serpentine the ports follow. This one starts top-left and runs down each column.',
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
            avoid: [function () { var w = wall(); return w ? T.cabinetPoint(w, { index: 0 }) : null; }],
            body: 'Drag the processor onto the screen and its ports fill in order from the first free socket. Nothing lands on hardware by itself.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var p = proc();
                t.mem.before = wallPins().length;
                return t.drag('[data-hwdock="processor-' + p.id + '"]', t.cabinetPoint(wall(), { index: 0 })).then(function () {
                    return t.wait(function () { return wallPins().length > t.mem.before; });
                });
            },
            check: function (mem) {
                var ps = wallPins();
                if (ps.length <= mem.before) return null;
                var socks = ps.map(function (p) { return Number(p.port); }).sort(function (a, b) { return a - b; });
                var name = proc() && proc().name ? proc().name : '';
                var odd = proc() && proc().redundancy && socks.every(function (s) { return s % 2 === 1; });
                return ps.length + ' ports on ' + (odd ? 'the odd sockets ' : 'sockets ') + socks[0] + '–' + socks[socks.length - 1]
                    + (name ? ', labelled ' + name + '-' + socks[0] + ' …' : '')
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
                }).then(function () { return t.spot($('#hw-dock-attach')); });
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
            body: 'Drag a spare port chip onto the run that lost its port and that screen port is pinned to this socket, wherever it is on the card.',
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
        snakePorts: {
            target: '#hardware-dock-body .hw-dock-grid', place: 'top', title: 'Snake the ports',
            body: 'Hold Alt and sweep across port chips, then right-click and pick Snake. Four ports ride one home run.',
            before: function () { switchView('data-flow'); closeSheet(); },
            act: function (t) {
                var c = card();
                var face = function (n) { return $('[data-hwdock="port-' + c.id + '-' + n + '"]'); };
                var last;
                return t.moveTo(face(1), { badge: 'Alt' }).then(function (p) {
                    press(true);
                    mouse('mousedown', face(1), p.x, p.y, { altKey: true, buttons: 1 });
                    return [2, 3, 4].reduce(function (chain, n) {
                        return chain.then(function () {
                            var q = centerOf(face(n));
                            last = q;
                            return animateTo(q.x, q.y, function (x, y) {
                                mouse('mousemove', document, x, y, { altKey: true, buttons: 1 });
                            }).then(function () { return t.pause(120); });
                        });
                    }, Promise.resolve());
                }).then(function () {
                    mouse('mousemove', document, last.x, last.y, { altKey: true, buttons: 1 });
                    mouse('mouseup', document, last.x, last.y, { altKey: true, buttons: 0 });
                    press(false);
                    return t.pause(250);
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
                return tag + ' — one home run for four ports.';
            }
        },
        cableSheet: {
            target: '#hardware-dock-body .hw-dock-cablebtn-data', place: 'top', title: 'The cable sheet',
            body: 'The &#8801; on a card flips its chips into a cable sheet: tick, port, screen and home run, one row per port.',
            before: function () { switchView('data-flow'); },
            act: function (t) {
                return t.click('#hardware-dock-body .hw-dock-cablebtn-data').then(function () {
                    return t.wait(sheetOpen);
                }).then(function () { return t.spot($('#hardware-dock-body .hw-dock-cablesheet-data')); });
            },
            check: function () { return sheetOpen() ? 'The chips are a sheet now; the snake reads as one folded row.' : null; },
            after: function (next) { if (!next || !next.sheetStep) closeSheet(); }
        },
        snakeHomeRun: {
            sheetStep: true,
            target: function () { var o = owner(), s = snake(); return o && s ? '[data-lrd-field="data-snake-ft-' + o.id + '-' + s.id + '"]' : '[data-lrd-field^="data-snake-ft-"]'; },
            place: 'top', title: 'The snake&rsquo;s home run',
            body: 'Type the snake&rsquo;s home run in feet on its row. Tab walks down the column to the next length.',
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
                    return t.moveTo(el, { badge: 'Tab' }).then(function () {
                        t.key('Tab', {}, el);
                        return t.pause(350);
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
            before: function () { switchView('data-flow'); },
            act: function (t) {
                var p = proc();
                return t.click('[data-hwpop="proc-' + p.id + '"]').then(function () {
                    return t.wait(function () { var pop = $('#hw-gear-popover'); return pop && pop.style.display === 'block' ? pop : null; });
                }).then(function (pop) {
                    if (!pop) throw new Error('the gear popover did not open');
                    return t.spot(pop);
                }).then(function () {
                    var bar = '[data-lrd-field="processor-redundancy-' + p.id + '"]';
                    var seg = $(bar + ' [data-level="port"]') || $$(bar + ' [data-level]').filter(function (b) { return b.dataset.level !== 'off'; }).pop();
                    if (!seg) throw new Error('no redundancy bar on this unit');
                    t.mem.level = seg.dataset.level;
                    return t.click(seg);
                }).then(function () {
                    return t.wait(function () { var q = proc(); return q && q.redundancy; });
                }).then(function () { return t.pause(300); });
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
        overrideRun: {
            target: '#main-canvas', place: 'top', title: 'Take over one run',
            body: 'Hold Alt and the run under the cursor lights up. Alt+click takes over just that port: click cabinets to redraw it, Esc when done.',
            before: function () { switchView('data-flow'); closePopover(); },
            act: function (t) {
                var w = wall();
                var pt = t.cabinetPoint(w, { port: 2 });
                var others = A().calculatePortAssignments(w).filter(function (i) { return i.port === 3; }).slice(0, 2);
                return t.moveTo(pt, { badge: 'Alt' }).then(function () {
                    A().updateOverrideHover(true, pt.worldX, pt.worldY);
                    return t.pause(450);
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
                    return others.reduce(function (chain, it) {
                        return chain.then(function () {
                            var q = t.cabinetPoint(w, { index: w.panels.indexOf(it.panel) });
                            if (!q) return;
                            return t.moveTo(q).then(function () {
                                press(true);
                                t.canvasDown(q, {});
                                return t.pause(70);
                            }).then(function () {
                                t.canvasUp(q, {});
                                press(false);
                                ripple(q.x, q.y);
                                return t.pause(320);
                            });
                        });
                    }, Promise.resolve());
                }).then(function () {
                    t.key('Escape', {}, document);
                    return t.pause(250);
                });
            },
            check: function () {
                var w = wall();
                var ov = (w && w.customPortOverrides) || [];
                if (!ov.includes(2)) return null;
                var path = (w.customPortPaths || {})[2] || [];
                return 'Port 2 is hand-drawn (' + path.length + ' cabinets); the rest of the screen re-flows around it.';
            }
        },
        panelWatts: {
            target: '#power-panel-watts', place: 'right', title: 'Power view and the math',
            avoid: ['[data-mode="power"]', '#power-panel-watts'],
            body: 'Power plans the electrical. Voltage, amperage and watts per cabinet set the cabinets a circuit carries and the circuits required.',
            act: function (t) {
                return t.click('[data-mode="power"]').then(function () {
                    return t.type('#power-panel-watts', '200', { enter: true });
                }).then(function () {
                    return t.wait(function () { var w = wall(); return w && Number(w.panelWatts) === 200; });
                });
            },
            check: function () {
                var w = wall();
                if (!w || Number(w.panelWatts) !== 200) return null;
                var req = $('#power-circuits-required') ? $('#power-circuits-required').textContent.trim() : '?';
                return '200 W per cabinet at 208 V, 20 A. Circuits required: ' + req + '.';
            }
        },
        breakoutType: {
            target: '#power-breakout-type', place: 'right', title: 'The breakout',
            body: 'How each multi fans out to the cabinets. Multi to True1 is six circuits a box; the choice drives the gear list.',
            before: function () { switchView('power'); },
            act: function (t) {
                return t.select('#power-breakout-type', 'soca-true1').then(function () {
                    return t.wait(function () { var w = wall(); return w && w.powerBreakoutType === 'soca-true1'; });
                });
            },
            check: function () {
                var w = wall();
                return w && w.powerBreakoutType === 'soca-true1' ? 'Each multi fans out to True1: six circuits a box.' : null;
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
        dropMulti: {
            target: function () { var d = distro(); return d ? '[data-hwdock="slot-' + d.id + '-1"]' : '[data-hwdock^="slot-"]'; },
            place: 'top', title: 'Drag a multi onto the wall',
            avoid: [function () {
                var w = wall(); if (!w) return null;
                var last = A().screenCircuits(w).length - 1;
                return T.cabinetPoint(w, { circuit: Math.max(0, last), mid: true });
            }],
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
                var last = A().screenCircuits(wall()).length - 1;
                var onWall = function () {
                    var w = wall(); var m = (w && w.powerSocaDistro) || {};
                    return Object.keys(m).some(function (k) { return m[k] === d.id; });
                };
                t.mem.onWall = onWall;
                var slot = '[data-hwdock="slot-' + d.id + '-1"]';
                return t.drag(slot, t.cabinetPoint(wall(), { circuit: Math.max(0, last), mid: true })).then(function () {
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
                return (d.name || 'SL') + ' multi 1 took ' + n + ' of ' + size + ' circuits' + (n < size ? ' — the wall needs no more.' : '.');
            }
        },
        typeChip: {
            target: function () { var d = distro(); return d ? '[data-lrd-field="distro-box-type-' + d.id + '-2"]' : '.hw-dock-typechip'; },
            place: 'top', title: 'The type chip',
            body: 'Every number wears its connector as a chip. On the spare number the chip is the picker: click it to cycle the types the distro offers.',
            before: function () { switchView('power'); },
            act: function (t) {
                var d = distro();
                t.mem.before = A().distroBoxType(d, 2).type.id;
                return t.click('[data-lrd-field="distro-box-type-' + d.id + '-2"]').then(function () {
                    return t.wait(function () { return A().distroBoxType(distro(), 2).type.id !== t.mem.before; });
                });
            },
            check: function (mem) {
                var d = distro();
                var ty = A().distroBoxType(d, 2).type;
                return ty.id !== mem.before ? (d.name || 'SL') + ' 2 is now a ' + ty.name + '.' : null;
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
                    return t.spot(ft.closest('.hw-dock-cablesheet') || ft).then(function () { return t.type(ft, '25'); });
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
        splitters: {
            target: '#power-splitters-enabled', place: 'right', title: 'Share two runs through a 2fer',
            avoid: ['#power-splitters-enabled', '#main-canvas'],
            body: 'Turn sharing on, then hold Alt, sweep across two circuits on the wall and right-click 2fer them: two runs on one circuit.',
            before: function () { switchView('power'); },
            act: function (t) {
                var w = wall();
                return t.click('#power-splitters-enabled').then(function () {
                    return t.wait(function () { return A().getPowerSplitters(wall()).enabled; });
                }).then(function () {
                    return t.pause(250);
                }).then(function () {
                    w = wall();
                    var circuits = A().screenCircuits(w);
                    if (circuits.length < 2) throw new Error('fewer than two circuits to sweep');
                    var c0 = t.cabinetPoint(w, { circuit: 0 });
                    var c1 = t.cabinetPoint(w, { circuit: 1 });
                    t.mem.nums = [circuits[0].num, circuits[1].num];
                    return t.moveTo(c0, { badge: 'Alt' }).then(function () {
                        press(true);
                        t.canvasDown(c0, { altKey: true });
                        return t.pause(80);
                    }).then(function () {
                        t.canvasMove({ x: c0.x + 6, y: c0.y + 6 }, { altKey: true });
                        return t.canvasGlide(c1, { altKey: true });
                    }).then(function () {
                        t.canvasMove(c1, { altKey: true });
                        return t.pause(200);
                    }).then(function () {
                        t.canvasUp(c1, { altKey: true });
                        press(false);
                        if (!A()._sweepSelection) {
                            // The sweep did not arm; the selection is set by
                            // hand so the deal can still be shown.
                            t.mem.fallback = true;
                            A()._sweepSelection = { layerId: w.id, nums: t.mem.nums.slice() };
                            R().render();
                        }
                        return t.pause(250);
                    }).then(function () {
                        return t.rightClick(c1);
                    }).then(function () {
                        return t.pickMenu('hw-batch-n0');
                    }).then(function () {
                        return t.wait(function () {
                            var l = wall(); var sp = l && l.powerSplitters;
                            return sp && sp.manual && Array.isArray(sp.manual.merge) && sp.manual.merge.length;
                        });
                    });
                });
            },
            check: function (mem) {
                var w = wall(); var sp = w && w.powerSplitters;
                var merge = sp && sp.manual && sp.manual.merge;
                if (!merge || !merge.length) return null;
                return 'Circuits ' + merge[0].join(' and ') + ' share one circuit through a 2fer.';
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
                    return t.spot(m.querySelector('.modal-content') || m).then(function () { return t.pause(900); });
                }).then(function () {
                    var m = $('#balance-modal');
                    if (!m) return;
                    var btn = m.querySelector('.balance-apply') || $$('.balance-close', m).pop();
                    return t.click(btn);
                });
            },
            check: function (mem) {
                if (!mem.opened) return null;
                return mem.apply ? 'Balance moved the short multi onto evener breakers.' : 'Balance opened; nothing to move on this distro yet, so it closed.';
            },
            after: function () { var m = $('#balance-modal'); if (m) m.remove(); }
        },
        addBeach: {
            target: '#beaches-panel .beaches-add', place: 'left', title: 'Beaches',
            body: 'A beach is a position the show is pulled to. Add beach asks for a name; here it is filled in as Stage Left.',
            act: function (t) {
                return t.moveTo('#beaches-panel .beaches-add').then(function (p) {
                    press(true); ripple(p.x, p.y);
                    return t.pause(200);
                }).then(function () {
                    press(false);
                    return A().createBeach('Stage Left');
                }).then(function () {
                    return t.wait(function () { return beach(); });
                });
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
                return t.moveTo('#layers-list .canvas-add-btn').then(function (p) {
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
                    a.initializeLayerDefaults(layer);
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
                });
            },
            check: function () { return wall2() ? 'DEMO WALL 2 stands beside the first: same size, same processing.' : null; }
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
            exportStep: true,
            target: '#btn-export', place: 'bottom', title: 'Export the binder',
            avoid: ['#btn-export', '#export-format'],
            body: 'Export saves maps as PNG, PSD, PDF or XML, the pull sheet, or the Binder: a drawing set with a wiring sheet behind every map.',
            before: function () { closeExport(); },
            act: function (t) {
                return t.click('#btn-export').then(function () {
                    return t.wait(exportOpen);
                }).then(function () {
                    var mc = $('#export-modal .modal-content');
                    return t.spot(mc).then(function () { return t.select('#export-format', 'binder'); });
                }).then(function () { return t.pause(250); });
            },
            check: function () {
                var f = $('#export-format');
                var sec = $('#export-binder-section');
                return exportOpen() && f && f.value === 'binder' && sec && sec.style.display !== 'none'
                    ? 'Binder (PDF): numbered sheets with a title block, on Tabloid by default.' : null;
            },
            after: closeExportUnless
        },
        screenOrder: {
            exportStep: true,
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
            after: closeExportUnless
        },
        wiringTick: {
            exportStep: true,
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
            after: closeExportUnless
        },
        titleBlock: {
            exportStep: true,
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
            after: closeExportUnless
        },
        preferences: {
            target: '#btn-preferences', place: 'bottom', title: 'Preferences',
            avoid: ['#btn-preferences', '#preferences-modal .pm-tabstrip'],
            body: 'App-wide defaults in seven tabs. The Binder tab holds the sheet size, the logo, the screen order and the title block default.',
            before: function () { closeExport(); },
            act: function (t) {
                return t.click('#btn-preferences').then(function () {
                    return t.wait(function () { var m = $('#preferences-modal'); return m && m.style.display === 'block' ? m : null; });
                }).then(function (m) {
                    if (!m) throw new Error('Preferences did not open');
                    return t.spot(m.querySelector('.modal-content') || m).then(function () {
                        return t.click('#preferences-modal .pm-tabstrip .view-tab[data-key="binder"]');
                    });
                }).then(function () { return t.pause(250); });
            },
            check: function () {
                var tab = $('#preferences-modal .pm-tabstrip .view-tab[data-key="binder"]');
                return tab && tab.classList.contains('active') ? 'The Binder tab: a default applies to what you create next.' : null;
            },
            after: function () { closePrefs(); }
        },
        helpMenu: {
            target: '[data-menu="help"]', place: 'bottom', title: 'Help',
            body: 'Every guide lives under Help: Quick Start, What&rsquo;s New in 1.0, the Advanced Guide and the keyboard shortcuts.',
            before: function () { closePrefs(); },
            act: function (t) {
                return t.click('[data-menu="help"]').then(function () {
                    return t.wait(function () { var m = $('#menu-help'); return m && m.style.display === 'block' ? m : null; });
                }).then(function (m) { return t.spot(m).then(function () { return t.pause(200); }); });
            },
            check: function () {
                var m = $('#menu-help');
                return m && m.style.display === 'block' ? 'Reopen any tour from here.' : null;
            },
            after: function () { hideMenus(); }
        },
        outroAdvanced: {
            title: 'That&rsquo;s the tour', center: true,
            body: 'Done puts your own project back. Reopen any guide from Help.',
            before: function () { hideMenus(); closeExport(); closePrefs(); }
        },
        outroWhatsNew: {
            title: 'That&rsquo;s 1.0', center: true,
            body: 'Done puts your own project back. Reopen this from Help &rsaquo; What&rsquo;s New in 1.0, or take the Advanced Guide for the whole app.',
            before: function () { hideMenus(); closeExport(); closePrefs(); }
        },
        outroQuick: {
            title: 'You&rsquo;re all set', center: true,
            body: 'Done puts your own project back. Reopen this guide any time from Help &rsaquo; Quick Start Guide, or take the full walkthrough below.',
            before: function () { hideMenus(); closeExport(); closePrefs(); }
        }
    };

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
        whatsNew: {
            title: 'What’s New in 1.0',
            seed: {
                name: 'Demo Show',
                wall: { columns: 12, rows: 6, cabinet_width: 200, cabinet_height: 200 },
                layer: { processorType: 'novastar-coex-1g', panelWatts: 100 }
            },
            steps: ['introWhatsNew', 'addProcessor', 'nameProcessor', 'redundancy', 'dropProcessor', 'releasePort',
                    'attachmentFlag', 'pinPort', 'snakePorts', 'cableSheet', 'snakeHomeRun',
                    'dataCableTags', 'panelWatts', 'addDistro', 'dropMulti', 'typeChip',
                    'clearCircuit', 'multiCableSheet', 'powerCableTags', 'splitters', 'addBeach',
                    'exportBinder', 'wiringTick', 'titleBlock', 'outroWhatsNew']
        },
        advanced: {
            title: 'Advanced Guide',
            seed: { name: 'New Show', layer: { panelWatts: 100, powerBreakoutType: 'soca-powercon' } },
            steps: ['introAdvanced', 'projectName', 'cabinetSize', 'gridSize', 'fit', 'blankCabinet',
                    'cabinetIdStyle', 'showLook', 'processing', 'flowPattern', 'addProcessor',
                    'nameProcessor', 'redundancy', 'dropProcessor', 'releasePort', 'attachmentFlag', 'pinPort',
                    'snakePorts', 'cableSheet', 'snakeHomeRun', 'loosePortLength', 'dataCableTags',
                    'overrideRun', 'panelWatts', 'breakoutType', 'addDistro', 'nameDistro',
                    'dropMulti', 'typeChip', 'clearCircuit', 'multiCableSheet', 'powerCableTags',
                    'splitters', 'balance', 'addBeach', 'screenBeach', 'addScreen', 'groupScreens',
                    'exportBinder', 'screenOrder', 'wiringTick', 'titleBlock', 'preferences',
                    'helpMenu', 'outroAdvanced']
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
        startWhatsNew: function () { return show('whatsNew'); },
        startAdvanced: function () { return show('advanced'); },
        startTour: function (name) { return TOURS[name] ? show(name) : Promise.resolve(); },
        tours: toursAsLists,
        steps: function () { return STEPS; },
        end: end,
        setSpeed: function (n) { speed = Math.max(0.25, Number(n) || 1); },
        state: function () {
            return { tour: S.name, index: S.idx, running: S.running, visible: S.visible };
        }
    };

    function maybeAutoShow() {
        if (disabled()) return;
        // Never auto-show inside an automated browser (Playwright/Selenium set
        // navigator.webdriver). The tour's click-catcher would otherwise block
        // E2E tests. Real users are unaffected; they can still open it manually.
        if (navigator.webdriver) return;
        var tries = 0;
        var t = setInterval(function () {
            tries++;
            if (document.querySelector('#view-tabs') && document.querySelector('#right-sidebar')
                    && window.app && window.app.project && window.canvasRenderer) {
                clearInterval(t);
                setTimeout(function () { show('quick'); }, 400);
            } else if (tries > 40) {
                clearInterval(t);
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
                });
            } else if (tries > 80) {
                clearInterval(t);
            }
        }, 150);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
