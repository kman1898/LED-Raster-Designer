/*
 * quickstart.js: in-app guided tours.
 *   - Quick Start: short first-run tour, auto-shows once, skippable, with a
 *     "Don't show on startup" checkbox. Reopen from Help -> Quick Start Guide.
 *   - Advanced Guide: an optional full walkthrough of the whole app, offered at
 *     the end of the quick tour and from Help -> Advanced Guide.
 * Fully self-contained and offline (no CDN).
 */
(function () {
    'use strict';

    var LS_KEY = 'lrd_quickstart_disabled'; // '1' = don't auto-show on launch

    function switchView(mode) {
        var t = document.querySelector('[data-mode="' + mode + '"]');
        if (t) t.click();
    }

    // Short first-run tour.
    var QUICK_STEPS = [
        {
            title: 'Welcome to LED Raster Designer',
            body: 'Design LED walls, plan data &amp; power, and export production maps for your processor. Here&rsquo;s a quick tour, and you can skip it at any time.',
            center: true
        },
        { target: '#left-sidebar', place: 'right', title: 'Set up your wall',
          body: 'Enter one cabinet&rsquo;s pixel size (e.g. 128 &times; 128), then how many panels wide and tall your wall is under <b>Columns</b> and <b>Rows</b>.' },
        { target: 'canvas', place: 'top', title: 'Your wall',
          body: 'Your wall renders here on the <b>Pixel Map</b>, where each square is one cabinet. Scroll to zoom, <b>Space</b>+drag to pan, and <b>Fit</b> to recenter.' },
        { target: '#view-tabs', place: 'bottom', title: 'Five views',
          body: 'Switch between <b>Pixel Map</b>, <b>Cabinet ID</b>, <b>Show Look</b> (real-world stage layout), <b>Data</b> (signal &amp; ports), and <b>Power</b> (circuits).' },
        { target: '#right-sidebar', place: 'left', title: 'Screens &amp; canvases',
          body: 'Manage your screens here. Add more with <b>+ Add</b>, or add another canvas (one per processor or stage) with <b>+ Add Canvas</b>.' },
        { target: '#btn-export', place: 'bottom', title: 'Export',
          body: 'When it looks right, click <b>Export</b> to save production maps (PNG, PSD, or Resolume XML) for your processor.' },
        { target: '[data-menu="help"]', place: 'bottom', title: 'You&rsquo;re all set',
          body: 'Reopen this guide any time from <b>Help &rsaquo; Quick Start Guide</b>, or take the full walkthrough below.' }
    ];

    // Full, in-depth walkthrough of the whole app.
    var ADVANCED_STEPS = [
        { title: 'The full tour', center: true, before: function () { switchView('pixel-map'); },
          body: 'This walks through the whole app, one area at a time. Use <b>Back</b> / <b>Next</b> to move, or <b>Skip</b> to leave at any point.' },
        { target: '#project-name', place: 'bottom', title: 'Projects',
          body: 'Name your project here. <b>File &rsaquo; Save / Open</b> store your work as <b>.lrd</b> files, and recent projects appear in the File menu.' },
        { target: '#btn-preferences', place: 'bottom', title: 'Preferences',
          body: 'Set app-wide defaults here: the interface <b>accent color</b>, default panel size and hardware, units, and label font size for new screens.' },
        { target: '#left-sidebar', place: 'right', title: 'Screen Info',
          body: 'Each screen&rsquo;s core settings: cabinet pixel size, <b>Columns &times; Rows</b>, its <b>Offset</b> (position in the raster), physical panel size (mm) and weight for the totals.' },
        { target: '#screen-rotation', place: 'right', title: 'Rotation',
          body: 'Rotate a screen <b>90 / 180 / 270</b> for physically-rotated walls. The cabinets and labels rotate across every view; off-canvas content is clipped.' },
        { target: '#color1-picker', place: 'right', title: 'Colors &amp; test pattern',
          body: 'The two checkerboard colors distinguish cabinets. Below them you can pick palette patterns or overlay a gradient. Each screen keeps its own colors.' },
        { target: '#transparent-fill', place: 'right', title: 'Transparent fill',
          body: 'Render a screen with no fill (see-through) so only borders and labels draw. Pairs with the export <b>Transparent Background</b> option for overlays.' },
        { target: 'canvas', place: 'top', title: 'Per-panel editing',
          body: 'On the Pixel Map: <b>Alt+Click</b> blanks a cabinet (non-rectangular walls), <b>Alt+Shift+Click</b> makes a half-tile, and dragging a box selects many cabinets to edit at once.' },
        { target: '[data-mode="cabinet-id"]', place: 'bottom', title: 'Cabinet ID view', before: function () { switchView('cabinet-id'); },
          body: 'Numbers every cabinet for the install crew. Choose a numbering style (A1, 1&#44;1, 01&hellip;) and label position in the sidebar. Matches the Pixel Map layout.' },
        { target: '[data-mode="show-look"]', place: 'bottom', title: 'Show Look view', before: function () { switchView('show-look'); },
          body: 'Arrange screens to match the real-world stage. Shift+drag a screen to reposition it. Show Look drives the Data and Power layouts, and has its own raster size.' },
        { target: '[data-mode="data-flow"]', place: 'bottom', title: 'Data view', before: function () { switchView('data-flow'); },
          body: 'Plan signal routing. Pick your <b>processor</b>, bit depth, and frame rate to see ports required, choose a serpentine <b>flow pattern</b>, or draw a custom path.' },
        { target: '[data-mode="power"]', place: 'bottom', title: 'Power view', before: function () { switchView('power'); },
          body: 'Plan electrical distribution. Set <b>voltage</b> and per-panel watts to see circuits required and total amps (single and three phase), with color-coded circuits.' },
        { target: '#right-sidebar', place: 'left', title: 'Screens panel', before: function () { switchView('pixel-map'); },
          body: 'Every screen in the project, grouped by canvas. Rename, reorder, lock, or hide a screen, and drag to reorder. The active screen is highlighted.' },
        { target: '#btn-add-canvas', place: 'left', title: 'Multiple canvases',
          body: 'Add a canvas for each processor, stage, or tour leg. Each canvas has its own raster size and layers, and is tinted with its own identity color.' },
        { target: '#btn-fit', place: 'bottom', title: 'Zoom &amp; snap',
          body: '<b>Fit</b> frames the raster, <b>1:1</b> is actual size. The <b>Snap</b> toggle magnetically aligns screens to each other and to the raster edges as you drag.' },
        { target: '#left-sidebar-toggle', place: 'right', title: 'Panels',
          body: 'Collapse a side panel with its chevron, or drag its inner edge to resize it. Each side remembers its width, so you can reclaim space for the canvas.' },
        { target: '#btn-export', place: 'bottom', title: 'Exporting',
          body: 'The Export dialog lets you pick which <b>canvases</b> and <b>views</b> to output, the <b>format</b> (PNG, PSD, PDF, or Resolume XML), a transparent background, and a resolution scale.' },
        { target: '[data-menu="help"]', place: 'bottom', title: 'Help &amp; shortcuts',
          body: 'Under <b>Help</b> you&rsquo;ll find the full <b>Keyboard Shortcuts</b> list, this guide, the Quick Start, and update checks.' },
        { title: 'That&rsquo;s the tour', center: true,
          body: 'You&rsquo;ve seen the whole app. Reopen either guide any time from the <b>Help</b> menu. Now go build something.' }
    ];

    var activeSteps = QUICK_STEPS;
    var idx = 0;
    var els = null;

    function injectStyles() {
        if (document.getElementById('qs-styles')) return;
        var css = ''
            + '#qs-catch{position:fixed;inset:0;z-index:2000000;}'
            + '#qs-spot{position:fixed;z-index:2000001;border-radius:8px;pointer-events:none;'
            + 'box-shadow:0 0 0 3px #e22330,0 0 0 9999px rgba(10,10,12,.66);transition:all .22s cubic-bezier(.4,0,.2,1);}'
            + '#qs-callout{position:fixed;z-index:2000002;width:334px;max-width:calc(100vw - 32px);background:#2e2e2e;'
            + 'color:#f0f0f0;border:1px solid #3a3a3a;border-top:3px solid #e22330;border-radius:12px;'
            + 'box-shadow:0 14px 44px rgba(0,0,0,.55);font-family:-apple-system,"Segoe UI",system-ui,sans-serif;'
            + 'padding:16px 18px 13px;transition:all .22s cubic-bezier(.4,0,.2,1);}'
            + '#qs-callout h3{margin:0 0 7px;font-size:16px;font-weight:700;color:#fff;}'
            + '#qs-callout p{margin:0;font-size:13.5px;line-height:1.46;color:#d6d6d6;}'
            + '#qs-callout p b{color:#fff;font-weight:600;}'
            + '#qs-callout .qs-prog{margin:13px 0 11px;font-size:11px;color:#9a9a9a;letter-spacing:.02em;}'
            + '#qs-callout .qs-cta{display:block;width:100%;margin:0 0 9px;background:#3c3c3c;color:#fff;'
            + 'border:1px solid #555;border-radius:7px;padding:8px;font:600 12.5px inherit;cursor:pointer;}'
            + '#qs-callout .qs-cta:hover{background:#474747;}'
            + '#qs-callout .qs-row{display:flex;align-items:center;justify-content:space-between;gap:10px;}'
            + '#qs-callout .qs-chk{display:flex;align-items:center;gap:7px;font-size:11.5px;color:#b6b6b6;cursor:pointer;user-select:none;}'
            + '#qs-callout .qs-chk input{width:14px;height:14px;accent-color:#e22330;cursor:pointer;}'
            + '#qs-callout .qs-btns{display:flex;gap:8px;}'
            + '#qs-callout button{font:600 12.5px -apple-system,"Segoe UI",sans-serif;border-radius:7px;padding:7px 13px;cursor:pointer;border:1px solid #4a4a4a;}'
            + '#qs-callout .qs-skip{background:transparent;color:#9a9a9a;border-color:transparent;padding:7px 6px;}'
            + '#qs-callout .qs-skip:hover{color:#e0e0e0;}'
            + '#qs-callout .qs-back{background:#3c3c3c;color:#e0e0e0;}'
            + '#qs-callout .qs-next{background:#e22330;color:#fff;border-color:#8f1218;}'
            + '#qs-callout .qs-next:hover{background:#ef3340;}'
            + '#qs-callout .qs-arrow{position:absolute;width:14px;height:14px;background:#2e2e2e;border:1px solid #3a3a3a;transform:rotate(45deg);}';
        var s = document.createElement('style');
        s.id = 'qs-styles';
        s.textContent = css;
        document.head.appendChild(s);
    }

    function build() {
        injectStyles();
        var c = document.createElement('div'); c.id = 'qs-catch';
        var spot = document.createElement('div'); spot.id = 'qs-spot';
        var call = document.createElement('div'); call.id = 'qs-callout';
        document.body.appendChild(c);
        document.body.appendChild(spot);
        document.body.appendChild(call);
        c.addEventListener('click', function (e) { e.stopPropagation(); });
        els = { catch: c, spot: spot, callout: call };
        window.addEventListener('resize', reposition);
    }

    function disabled() { try { return localStorage.getItem(LS_KEY) === '1'; } catch (e) { return false; } }
    function setDisabled(v) { try { v ? localStorage.setItem(LS_KEY, '1') : localStorage.removeItem(LS_KEY); } catch (e) {} }

    function targetRect(step) {
        if (!step.target) return null;
        var el = document.querySelector(step.target);
        if (!el) return null;
        var r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return null;
        return r;
    }

    function place(step) {
        var call = els.callout, spot = els.spot;
        var r = targetRect(step);
        if (r) {
            var pad = 6;
            spot.style.display = 'block';
            spot.style.left = (r.left - pad) + 'px';
            spot.style.top = (r.top - pad) + 'px';
            spot.style.width = (r.width + pad * 2) + 'px';
            spot.style.height = (r.height + pad * 2) + 'px';
        } else {
            spot.style.display = 'block';
            spot.style.left = '50%'; spot.style.top = '50%';
            spot.style.width = '0px'; spot.style.height = '0px';
        }
        var cw = call.offsetWidth || 334, ch = call.offsetHeight || 170;
        var gap = 18, vw = window.innerWidth, vh = window.innerHeight;
        var x, y;
        var arrow = call.querySelector('.qs-arrow');
        if (arrow) arrow.style.display = 'none';
        if (!r || step.center) {
            x = (vw - cw) / 2; y = (vh - ch) / 2;
        } else {
            var p = step.place || 'bottom';
            if (p === 'right') { x = r.right + gap; y = r.top; }
            else if (p === 'left') { x = r.left - cw - gap; y = r.top; }
            else if (p === 'top') { x = r.left + r.width / 2 - cw / 2; y = r.top - ch - gap; }
            else { x = r.left + r.width / 2 - cw / 2; y = r.bottom + gap; }
            x = Math.max(12, Math.min(x, vw - cw - 12));
            y = Math.max(12, Math.min(y, vh - ch - 12));
            if (arrow) {
                arrow.style.display = 'block';
                arrow.style.borderTop = ''; arrow.style.borderLeft = ''; arrow.style.borderRight = ''; arrow.style.borderBottom = '';
                if (p === 'right') { arrow.style.left = '-8px'; arrow.style.top = Math.max(14, Math.min(r.top + r.height / 2 - y - 7, ch - 28)) + 'px'; arrow.style.borderRight = 'none'; arrow.style.borderBottom = 'none'; }
                else if (p === 'left') { arrow.style.left = (cw - 7) + 'px'; arrow.style.top = Math.max(14, Math.min(r.top + r.height / 2 - y - 7, ch - 28)) + 'px'; arrow.style.borderLeft = 'none'; arrow.style.borderTop = 'none'; }
                else if (p === 'top') { arrow.style.top = (ch - 7) + 'px'; arrow.style.left = Math.max(14, Math.min(r.left + r.width / 2 - x - 7, cw - 28)) + 'px'; arrow.style.borderLeft = 'none'; arrow.style.borderTop = 'none'; }
                else { arrow.style.top = '-8px'; arrow.style.left = Math.max(14, Math.min(r.left + r.width / 2 - x - 7, cw - 28)) + 'px'; arrow.style.borderRight = 'none'; arrow.style.borderBottom = 'none'; }
            }
        }
        call.style.left = x + 'px';
        call.style.top = y + 'px';
    }

    function reposition() { if (els && els.callout.style.display !== 'none') place(activeSteps[idx]); }

    function render() {
        var step = activeSteps[idx];
        var last = idx === activeSteps.length - 1;
        var offerFull = last && activeSteps === QUICK_STEPS;
        els.callout.innerHTML =
            '<div class="qs-arrow"></div>'
            + '<h3>' + step.title + '</h3>'
            + '<p>' + step.body + '</p>'
            + '<div class="qs-prog">Step ' + (idx + 1) + ' of ' + activeSteps.length + '</div>'
            + (offerFull ? '<button class="qs-cta" id="qs-full">Take the full walkthrough &rsaquo;</button>' : '')
            + '<div class="qs-row">'
            + '  <label class="qs-chk"><input type="checkbox" id="qs-nolaunch"' + (disabled() ? ' checked' : '') + '> Don&rsquo;t show on startup</label>'
            + '  <div class="qs-btns">'
            + '    <button class="qs-skip" id="qs-skip">Skip</button>'
            + (idx > 0 ? '    <button class="qs-back" id="qs-back">Back</button>' : '')
            + '    <button class="qs-next" id="qs-next">' + (last ? 'Done' : 'Next') + '</button>'
            + '  </div>'
            + '</div>';
        els.callout.querySelector('#qs-skip').onclick = end;
        els.callout.querySelector('#qs-next').onclick = function () { last ? end() : go(idx + 1); };
        var back = els.callout.querySelector('#qs-back'); if (back) back.onclick = function () { go(idx - 1); };
        els.callout.querySelector('#qs-nolaunch').onchange = function () { setDisabled(this.checked); };
        var full = els.callout.querySelector('#qs-full'); if (full) full.onclick = function () { show(ADVANCED_STEPS); };
        place(step);
    }

    function go(i) {
        if (i < 0 || i >= activeSteps.length) return;
        idx = i;
        var step = activeSteps[i];
        if (step.before) { try { step.before(); } catch (e) {} setTimeout(render, 260); }
        else render();
    }

    function show(list) {
        if (!els) build();
        if (list) activeSteps = list;
        els.catch.style.display = 'block';
        els.spot.style.display = 'block';
        els.callout.style.display = 'block';
        idx = -1;
        go(0);
    }

    function end() {
        if (!els) return;
        els.catch.style.display = 'none';
        els.spot.style.display = 'none';
        els.callout.style.display = 'none';
    }

    window.QuickStart = {
        start: function () { show(QUICK_STEPS); },
        startAdvanced: function () { show(ADVANCED_STEPS); },
        end: end
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
            if (document.querySelector('#view-tabs') && document.querySelector('#right-sidebar')) {
                clearInterval(t);
                setTimeout(function () { show(QUICK_STEPS); }, 400);
            } else if (tries > 40) {
                clearInterval(t);
            }
        }, 150);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', maybeAutoShow);
    } else {
        maybeAutoShow();
    }
})();
