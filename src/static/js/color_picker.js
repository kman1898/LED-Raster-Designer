/* ──────────────────────────────────────────────────────────────────────
   LRD Color Picker, a replica of the macOS Color popover for Windows.

   On macOS the native <input type="color"> already opens the native OS
   picker, so we leave it alone. On Windows the native control opens the
   (very different) OS picker, so we intercept it and show this replica.

   Phase 1: the compact swatch popover (vivid row, gray row, spectrum grid)
   plus a "Show Colors…" button. The full tabbed Colors window (wheel,
   slider modes, palettes, image, pencils) is built in later phases.

   Dev/testing on macOS: append ?colorpicker=force to the URL, or run
   LRDColorPicker.forceEnable() in the console, to exercise it here.
   ────────────────────────────────────────────────────────────────────── */
(function () {
    'use strict';

    function isClientMac() {
        // Detect the BROWSER's OS, not the server's. A Windows browser hitting a
        // Mac-hosted server must still get the custom picker; a Mac browser keeps
        // the native OS picker. navigator.userAgentData is most reliable
        // where available, falling back to platform/userAgent sniffing.
        try {
            const uaPlat = navigator.userAgentData && navigator.userAgentData.platform;
            if (uaPlat) return /mac/i.test(uaPlat);
        } catch (e) { /* ignore */ }
        const plat = (navigator.platform || '') + ' ' + (navigator.userAgent || '');
        return /Mac|iPhone|iPad|iPod/i.test(plat);
    }

    function isEnabled() {
        if (/[?&]colorpicker=force/.test(location.search)) return true;
        try { if (localStorage.getItem('lrd_force_color_picker') === '1') return true; } catch (e) { /* ignore */ }
        // Enable on every non-macOS client (Windows, Linux, ChromeOS). macOS
        // clients keep their native picker. Gating on the client, not the
        // server's window.LRD_PLATFORM, is what makes the LAN case work: a
        // Windows browser on a Mac-hosted server now correctly gets the picker.
        return !isClientMac();
    }

    // ── Color helpers ──────────────────────────────────────────────────
    function clamp(n, lo, hi) { return Math.min(hi, Math.max(lo, n)); }

    function toHex(r, g, b) {
        const h = (v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, '0');
        return ('#' + h(r) + h(g) + h(b)).toUpperCase();
    }

    function normalizeHex(str) {
        if (!str) return null;
        let s = String(str).trim().replace(/^#/, '');
        if (/^[0-9a-fA-F]{3}$/.test(s)) s = s.split('').map(c => c + c).join('');
        if (!/^[0-9a-fA-F]{6}$/.test(s)) return null;
        return ('#' + s).toUpperCase();
    }

    // HSL → hex, used to generate the swatch grid.
    function hslToHex(h, s, l) {
        s /= 100; l /= 100;
        const k = (n) => (n + h / 30) % 12;
        const a = s * Math.min(l, 1 - l);
        const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
        return toHex(255 * f(0), 255 * f(8), 255 * f(4));
    }

    function hexToRgb(hex) {
        const n = normalizeHex(hex) || '#000000';
        return { r: parseInt(n.slice(1, 3), 16), g: parseInt(n.slice(3, 5), 16), b: parseInt(n.slice(5, 7), 16) };
    }
    function rgbToHsv(r, g, b) {
        r /= 255; g /= 255; b /= 255;
        const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
        let h = 0;
        if (d) {
            if (max === r) h = ((g - b) / d) % 6;
            else if (max === g) h = (b - r) / d + 2;
            else h = (r - g) / d + 4;
            h *= 60; if (h < 0) h += 360;
        }
        return { h, s: (max === 0 ? 0 : d / max) * 100, v: max * 100 };
    }
    function hsvToRgb(h, s, v) {
        s /= 100; v /= 100;
        h = ((h % 360) + 360) % 360;
        const c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c;
        let r = 0, g = 0, b = 0;
        if (h < 60) { r = c; g = x; } else if (h < 120) { r = x; g = c; }
        else if (h < 180) { g = c; b = x; } else if (h < 240) { g = x; b = c; }
        else if (h < 300) { r = x; b = c; } else { r = c; b = x; }
        return { r: Math.round((r + m) * 255), g: Math.round((g + m) * 255), b: Math.round((b + m) * 255) };
    }
    function rgbToCmyk(r, g, b) {
        r /= 255; g /= 255; b /= 255;
        const k = 1 - Math.max(r, g, b);
        if (k >= 1) return { c: 0, m: 0, y: 0, k: 100 };
        return {
            c: (1 - r - k) / (1 - k) * 100,
            m: (1 - g - k) / (1 - k) * 100,
            y: (1 - b - k) / (1 - k) * 100,
            k: k * 100
        };
    }
    function cmykToRgb(c, m, y, k) {
        c /= 100; m /= 100; y /= 100; k /= 100;
        return {
            r: Math.round(255 * (1 - c) * (1 - k)),
            g: Math.round(255 * (1 - m) * (1 - k)),
            b: Math.round(255 * (1 - y) * (1 - k))
        };
    }
    function rgbStr(o) { return 'rgb(' + o.r + ',' + o.g + ',' + o.b + ')'; }

    // ── Palettes ───────────────────────────────────────────────────────
    // Top vivid row, the saturated basics.
    const VIVID = [
        '#FF2D2D', '#FF9500', '#FFF500', '#4CD916', '#00E5E0', '#0A60FF',
        '#9B30FF', '#C42BD6', '#AA7942', '#FFFFFF', '#919191', '#000000'
    ];

    // Gray ramp (first cell is the decorative "none" slash, still selectable).
    const GRAYS = (function () {
        const out = ['none'];
        for (let i = 1; i < 12; i++) {
            const l = Math.round(100 - (i - 1) * (100 / 10));
            out.push(hslToHex(0, 0, clamp(l, 0, 100)));
        }
        return out;
    })();

    // The big spectrum matrix: 12 hue columns × 10 lightness rows.
    const GRID_COLS = 12, GRID_ROWS = 10;
    const GRID = (function () {
        const cells = [];
        for (let r = 0; r < GRID_ROWS; r++) {
            const l = 44 + r * ((94 - 44) / (GRID_ROWS - 1)); // deep → pale top→bottom
            for (let c = 0; c < GRID_COLS; c++) {
                const h = (185 + c * (360 / GRID_COLS)) % 360;   // start ~teal, wrap
                cells.push(hslToHex(h, 85, l));
            }
        }
        return cells;
    })();

    // ── Tab icons for the full Colors window ───────────────────────────
    const TAB_ICONS = {
        wheel: '<span style="width:20px;height:20px;border-radius:50%;display:block;background:conic-gradient(from -90deg,#ff0000,#ffff00,#00ff00,#00ffff,#0000ff,#ff00ff,#ff0000);box-shadow:0 0 0 0.5px rgba(0,0,0,.5) inset;"></span>',
        sliders: '<svg viewBox="0 0 22 22" fill="none"><g stroke="#cfcfd2" stroke-width="1.6" stroke-linecap="round"><line x1="3" y1="6" x2="19" y2="6"/><line x1="3" y1="11" x2="19" y2="11"/><line x1="3" y1="16" x2="19" y2="16"/></g><g fill="#cfcfd2"><circle cx="14" cy="6" r="2.4"/><circle cx="7" cy="11" r="2.4"/><circle cx="15" cy="16" r="2.4"/></g></svg>',
        palettes: '<svg viewBox="0 0 22 22"><rect x="3" y="3" width="7" height="7" rx="1" fill="#ff5a5a"/><rect x="12" y="3" width="7" height="7" rx="1" fill="#ffce4a"/><rect x="3" y="12" width="7" height="7" rx="1" fill="#4ab1ff"/><rect x="12" y="12" width="7" height="7" rx="1" fill="#5ad06a"/></svg>',
        image: '<svg viewBox="0 0 22 22"><rect x="2.5" y="4" width="17" height="14" rx="2" fill="none" stroke="#cfcfd2" stroke-width="1.4"/><circle cx="7.5" cy="9" r="1.7" fill="#ffce4a"/><path d="M4 16l4.5-5 3 3 3-3.5L18 16z" fill="#7fb6ff"/></svg>',
        pencils: '<svg viewBox="0 0 22 22"><g stroke-width="0"><path d="M5 19l2-9 2 0 2 9z" fill="#ff6b6b"/><path d="M10 19l2-11 2 0 2 11z" fill="#4ab1ff"/><path d="M15 19l1.6-7 1.6 0 1.6 7z" fill="#5ad06a"/></g><g fill="#2c2c2e"><path d="M7 10l1-1.5 1 1.5z"/><path d="M12 8l1-1.5 1 1.5z"/></g></svg>'
    };

    // a crayon-style set (48) for the Pencils tab.
    const CRAYONS = [
        { name: 'Licorice', hex: '#000000' }, { name: 'Lead', hex: '#191919' }, { name: 'Tungsten', hex: '#333333' },
        { name: 'Iron', hex: '#4C4C4C' }, { name: 'Steel', hex: '#666666' }, { name: 'Tin', hex: '#7F7F7F' },
        { name: 'Nickel', hex: '#808080' }, { name: 'Aluminum', hex: '#999999' }, { name: 'Magnesium', hex: '#B3B3B3' },
        { name: 'Silver', hex: '#CCCCCC' }, { name: 'Mercury', hex: '#E6E6E6' }, { name: 'Snow', hex: '#FFFFFF' },
        { name: 'Cayenne', hex: '#941100' }, { name: 'Mocha', hex: '#945200' }, { name: 'Asparagus', hex: '#929000' },
        { name: 'Fern', hex: '#4F8F00' }, { name: 'Clover', hex: '#008F00' }, { name: 'Moss', hex: '#009051' },
        { name: 'Teal', hex: '#009193' }, { name: 'Ocean', hex: '#005493' }, { name: 'Midnight', hex: '#011993' },
        { name: 'Eggplant', hex: '#531A93' }, { name: 'Plum', hex: '#942193' }, { name: 'Maroon', hex: '#941751' },
        { name: 'Maraschino', hex: '#FF2600' }, { name: 'Tangerine', hex: '#FF9300' }, { name: 'Lemon', hex: '#FFFB00' },
        { name: 'Lime', hex: '#8EFA00' }, { name: 'Spring', hex: '#00F900' }, { name: 'Sea Foam', hex: '#00FA92' },
        { name: 'Turquoise', hex: '#00FDFF' }, { name: 'Aqua', hex: '#0096FF' }, { name: 'Blueberry', hex: '#0433FF' },
        { name: 'Grape', hex: '#9437FF' }, { name: 'Magenta', hex: '#FF40FF' }, { name: 'Strawberry', hex: '#FF2F92' },
        { name: 'Salmon', hex: '#FF7E79' }, { name: 'Cantaloupe', hex: '#FFD479' }, { name: 'Banana', hex: '#FFFC79' },
        { name: 'Honeydew', hex: '#D4FB79' }, { name: 'Flora', hex: '#73FA79' }, { name: 'Spindrift', hex: '#73FCD6' },
        { name: 'Ice', hex: '#73FDFF' }, { name: 'Sky', hex: '#76D6FF' }, { name: 'Orchid', hex: '#7A81FF' },
        { name: 'Lavender', hex: '#D783FF' }, { name: 'Bubblegum', hex: '#FF85FF' }, { name: 'Carnation', hex: '#FF8AD8' }
    ];

    // The named colors in the system palette (Color Palettes tab).
    const SYSTEM_PALETTE = [
        { name: 'Cayenne', hex: '#941100' }, { name: 'Maraschino', hex: '#FF2600' }, { name: 'Salmon', hex: '#FF7E79' },
        { name: 'Mocha', hex: '#945200' }, { name: 'Tangerine', hex: '#FF9300' }, { name: 'Cantaloupe', hex: '#FFD479' },
        { name: 'Asparagus', hex: '#929000' }, { name: 'Lemon', hex: '#FFFB00' }, { name: 'Banana', hex: '#FFFC79' },
        { name: 'Fern', hex: '#4F8F00' }, { name: 'Lime', hex: '#8EFA00' }, { name: 'Honeydew', hex: '#D4FB79' },
        { name: 'Clover', hex: '#008F00' }, { name: 'Spring', hex: '#00F900' }, { name: 'Flora', hex: '#73FA79' },
        { name: 'Moss', hex: '#009051' }, { name: 'Sea Foam', hex: '#00FA92' }, { name: 'Spindrift', hex: '#73FCD6' },
        { name: 'Teal', hex: '#009193' }, { name: 'Turquoise', hex: '#00FDFF' }, { name: 'Ice', hex: '#73FDFF' },
        { name: 'Ocean', hex: '#005493' }, { name: 'Aqua', hex: '#0096FF' }, { name: 'Sky', hex: '#76D6FF' },
        { name: 'Midnight', hex: '#011993' }, { name: 'Blueberry', hex: '#0433FF' }, { name: 'Orchid', hex: '#7A81FF' },
        { name: 'Eggplant', hex: '#531A93' }, { name: 'Grape', hex: '#9437FF' }, { name: 'Lavender', hex: '#D783FF' },
        { name: 'Plum', hex: '#942193' }, { name: 'Magenta', hex: '#FF40FF' }, { name: 'Bubblegum', hex: '#FF85FF' },
        { name: 'Maroon', hex: '#941751' }, { name: 'Strawberry', hex: '#FF2F92' }, { name: 'Carnation', hex: '#FF8AD8' },
        { name: 'Licorice', hex: '#000000' }, { name: 'Tungsten', hex: '#333333' }, { name: 'Steel', hex: '#666666' },
        { name: 'Aluminum', hex: '#999999' }, { name: 'Silver', hex: '#CCCCCC' }, { name: 'Snow', hex: '#FFFFFF' }
    ];

    // ── The full Colors window (Sliders tab) ───────────────────────────
    const FullPanel = {
        el: null, target: null,
        tab: 'wheel', mode: 'rgb',
        rgb: { r: 0, g: 0, b: 0 },
        hsv: { h: 0, s: 0, v: 0 },
        cmyk: { c: 0, m: 0, y: 0, k: 0 },
        _controls: [],
        _hexField: null,

        MODES: [
            { key: 'gray', label: 'Grayscale Slider' },
            { key: 'rgb', label: 'RGB Sliders' },
            { key: 'cmyk', label: 'CMYK Sliders' },
            { key: 'hsb', label: 'HSB Sliders' }
        ],

        ensureBuilt() {
            if (this.el) return;
            const win = document.createElement('div');
            win.className = 'lrd-cw-window';
            win.setAttribute('hidden', '');

            // Title bar
            const bar = document.createElement('div');
            bar.className = 'lrd-cw-titlebar';
            const lights = document.createElement('div');
            lights.className = 'lrd-cw-lights';
            // Single red close button (desktop style, no mac minimize/maximize).
            ['red'].forEach(c => {
                const d = document.createElement('span');
                d.className = 'lrd-cw-light ' + c;
                d.title = 'Close';
                d.addEventListener('click', () => this.close());
                lights.appendChild(d);
            });
            const title = document.createElement('div');
            title.className = 'lrd-cw-title'; title.textContent = 'Colors';
            bar.appendChild(lights); bar.appendChild(title);
            this._wireDrag(bar, win);

            // Tabs
            const tabs = document.createElement('div');
            tabs.className = 'lrd-cw-tabs';
            this._tabBtns = {};
            ['wheel', 'sliders', 'palettes', 'image', 'pencils'].forEach(key => {
                const b = document.createElement('button');
                b.type = 'button'; b.className = 'lrd-cw-tab' + (key === this.tab ? ' active' : '');
                b.innerHTML = TAB_ICONS[key];
                b.title = key.charAt(0).toUpperCase() + key.slice(1);
                b.addEventListener('click', () => this.selectTab(key));
                tabs.appendChild(b); this._tabBtns[key] = b;
            });

            // Body (content swaps per tab)
            const body = document.createElement('div');
            body.className = 'lrd-cw-body';
            this._body = body;

            // Footer: current-color well + eyedropper + saved swatches
            const footer = document.createElement('div');
            footer.className = 'lrd-cw-footer';
            const well = document.createElement('div'); well.className = 'lrd-cw-well';
            const dropper = document.createElement('button');
            dropper.type = 'button'; dropper.className = 'lrd-cw-dropper';
            dropper.title = 'Pick a color from the screen';
            dropper.innerHTML = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13.5 3.5a2 2 0 0 1 3 3L9 14l-4 1 1-4z"/><path d="M12 5l3 3"/></svg>';
            if (!window.EyeDropper) dropper.setAttribute('hidden', '');
            dropper.addEventListener('click', () => this._useEyedropper());
            const swatches = document.createElement('div'); swatches.className = 'lrd-cw-swatches';
            footer.appendChild(well); footer.appendChild(dropper); footer.appendChild(swatches);
            this._well = well; this._swatchesEl = swatches;

            win.appendChild(bar); win.appendChild(tabs); win.appendChild(body); win.appendChild(footer);
            document.body.appendChild(win);
            this.el = win;
            this._buildSwatches();

            // Escape closes; clicks inside don't bubble to the compact-picker closer.
            win.addEventListener('mousedown', (e) => e.stopPropagation());
            document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && this.isOpen()) this.close(); });
        },

        _wireDrag(handle, win) {
            handle.addEventListener('mousedown', (e) => {
                if (e.target.classList.contains('lrd-cw-light')) return;
                e.preventDefault();
                const r = win.getBoundingClientRect();
                const ox = e.clientX - r.left, oy = e.clientY - r.top;
                const move = (ev) => {
                    let left = clamp(ev.clientX - ox, 4, window.innerWidth - r.width - 4);
                    let top = clamp(ev.clientY - oy, 4, window.innerHeight - 40);
                    win.style.left = left + 'px'; win.style.top = top + 'px';
                };
                const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
                document.addEventListener('mousemove', move);
                document.addEventListener('mouseup', up);
            });
        },

        open(target, hex) {
            this.ensureBuilt();
            this.target = target;
            const rgb = hexToRgb(hex || (target && target.value) || '#000000');
            this.rgb = rgb;
            this.hsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
            this.cmyk = rgbToCmyk(rgb.r, rgb.g, rgb.b);
            this.selectTab(this.tab, true);
            this.el.removeAttribute('hidden');
            if (!this.el.style.top) {
                // Default placement: lower-left, like the macOS panel screenshots.
                this.el.style.left = '24px';
                this.el.style.top = Math.max(40, window.innerHeight - this.el.offsetHeight - 40) + 'px';
            }
            this.updateFooter();
        },

        selectTab(key, force) {
            if (!force && this.tab === key) return;
            this.tab = key;
            Object.keys(this._tabBtns).forEach(k => this._tabBtns[k].classList.toggle('active', k === key));
            if (key === 'sliders') this._renderSliders();
            else if (key === 'wheel') this._renderWheel();
            else if (key === 'palettes') this._renderPalettes();
            else if (key === 'image') this._renderImage();
            else if (key === 'pencils') this._renderPencils();
            else this._renderPlaceholder(key);
        },

        _renderPlaceholder(key) {
            this._controls = [];
            this._wheel = null;
            const names = { wheel: 'Color Wheel', palettes: 'Color Palettes', image: 'Image Palettes', pencils: 'Pencils' };
            this._body.innerHTML = '<div class="lrd-cw-placeholder">' + (names[key] || key) +
                '<br>coming in a later update.</div>';
        },

        // ── Sliders tab ────────────────────────────────────────────────
        _renderSliders() {
            this._wheel = null;
            this._body.innerHTML = '';
            // Mode row
            const moderow = document.createElement('div');
            moderow.className = 'lrd-cw-moderow';
            const sel = document.createElement('select');
            sel.className = 'lrd-cw-mode';
            this.MODES.forEach(m => {
                const o = document.createElement('option'); o.value = m.key; o.textContent = m.label;
                sel.appendChild(o);
            });
            sel.value = this.mode;
            sel.addEventListener('change', () => { this.mode = sel.value; this._renderSliders(); });
            const opts = document.createElement('button');
            opts.type = 'button'; opts.className = 'lrd-cw-opts'; opts.textContent = '⋯';
            opts.title = 'Options';
            moderow.appendChild(sel); moderow.appendChild(opts);
            this._body.appendChild(moderow);

            // Slider list
            const list = document.createElement('div');
            this._body.appendChild(list);
            this._controls = [];
            this._hexField = null;

            const chans = this._getChannels(this.mode);
            chans.forEach((ch, idx) => {
                const wrap = document.createElement('div'); wrap.className = 'lrd-cw-slider';
                const lab = document.createElement('div'); lab.className = 'lrd-cw-slabel'; lab.textContent = ch.label;
                const srow = document.createElement('div'); srow.className = 'lrd-cw-srow';
                const range = document.createElement('input');
                range.type = 'range'; range.className = 'lrd-cw-range';
                range.min = ch.min; range.max = ch.max; range.value = ch.val;
                range.style.background = this._trackGradient(this.mode, idx);
                const num = document.createElement('input');
                num.type = 'number'; num.className = 'lrd-cw-num';
                num.min = ch.min; num.max = ch.max; num.value = ch.val;
                range.addEventListener('input', () => this._setChannel(this.mode, idx, Number(range.value)));
                num.addEventListener('input', () => { const v = Number(num.value); if (Number.isFinite(v)) this._setChannel(this.mode, idx, v); });
                srow.appendChild(range); srow.appendChild(num);
                wrap.appendChild(lab); wrap.appendChild(srow); list.appendChild(wrap);
                this._controls.push({ idx, range, number: num });
            });

            // Mode extras
            if (this.mode === 'gray') {
                const grays = document.createElement('div'); grays.className = 'lrd-cw-grays';
                [0, 25, 50, 75, 100].forEach(p => {
                    const g = Math.round(p / 100 * 255);
                    const cell = document.createElement('div'); cell.className = 'lrd-cw-gray';
                    cell.style.background = rgbStr({ r: g, g: g, b: g });
                    cell.addEventListener('click', () => this._setChannel('gray', 0, p));
                    grays.appendChild(cell);
                });
                this._body.appendChild(grays);
            }
            if (this.mode === 'rgb') {
                const hexrow = document.createElement('div'); hexrow.className = 'lrd-cw-hexrow';
                const hl = document.createElement('span'); hl.className = 'lrd-cw-hexlabel'; hl.textContent = 'Hex Color #';
                const hf = document.createElement('input'); hf.type = 'text'; hf.className = 'lrd-cw-hexfield'; hf.spellcheck = false; hf.maxLength = 7;
                const applyHex = () => {
                    const n = normalizeHex(hf.value);
                    if (n) { const c = hexToRgb(n); this.rgb = c; this._afterRgbChange(); }
                };
                hf.addEventListener('keydown', (e) => { if (e.key === 'Enter') { applyHex(); e.preventDefault(); } });
                hf.addEventListener('blur', applyHex);
                hexrow.appendChild(hl); hexrow.appendChild(hf);
                this._body.appendChild(hexrow);
                this._hexField = hf;
            }
            this._syncUI();
        },

        _getChannels(mode) {
            if (mode === 'rgb') return [
                { label: 'Red', min: 0, max: 255, val: this.rgb.r },
                { label: 'Green', min: 0, max: 255, val: this.rgb.g },
                { label: 'Blue', min: 0, max: 255, val: this.rgb.b }
            ];
            if (mode === 'gray') {
                const g = Math.round((this.rgb.r + this.rgb.g + this.rgb.b) / 3 / 255 * 100);
                return [{ label: 'Brightness', min: 0, max: 100, val: g }];
            }
            if (mode === 'cmyk') return [
                { label: 'Cyan', min: 0, max: 100, val: Math.round(this.cmyk.c) },
                { label: 'Magenta', min: 0, max: 100, val: Math.round(this.cmyk.m) },
                { label: 'Yellow', min: 0, max: 100, val: Math.round(this.cmyk.y) },
                { label: 'Black', min: 0, max: 100, val: Math.round(this.cmyk.k) }
            ];
            // hsb
            return [
                { label: 'Hue', min: 0, max: 360, val: Math.round(this.hsv.h) },
                { label: 'Saturation', min: 0, max: 100, val: Math.round(this.hsv.s) },
                { label: 'Brightness', min: 0, max: 100, val: Math.round(this.hsv.v) }
            ];
        },

        _setChannel(mode, idx, val) {
            if (mode === 'rgb') {
                const k = ['r', 'g', 'b'][idx];
                this.rgb[k] = clamp(Math.round(val), 0, 255);
                this._afterRgbChange();
            } else if (mode === 'gray') {
                const g = clamp(Math.round(val / 100 * 255), 0, 255);
                this.rgb = { r: g, g: g, b: g };
                this._afterRgbChange();
            } else if (mode === 'cmyk') {
                const k = ['c', 'm', 'y', 'k'][idx];
                this.cmyk[k] = clamp(val, 0, 100);
                this.rgb = cmykToRgb(this.cmyk.c, this.cmyk.m, this.cmyk.y, this.cmyk.k);
                this._afterRgbChange({ keepCmyk: true });
            } else { // hsb
                const k = ['h', 's', 'v'][idx];
                this.hsv[k] = clamp(val, 0, idx === 0 ? 360 : 100);
                this.rgb = hsvToRgb(this.hsv.h, this.hsv.s, this.hsv.v);
                this._afterRgbChange({ keepHsv: true });
            }
        },

        _afterRgbChange(opts) {
            opts = opts || {};
            if (!opts.keepHsv) {
                const nh = rgbToHsv(this.rgb.r, this.rgb.g, this.rgb.b);
                if (nh.s === 0 && this.hsv) nh.h = this.hsv.h;   // preserve hue at gray
                if (nh.v === 0 && this.hsv) nh.h = this.hsv.h;
                this.hsv = nh;
            }
            if (!opts.keepCmyk) this.cmyk = rgbToCmyk(this.rgb.r, this.rgb.g, this.rgb.b);
            this._syncUI();
            this._syncWheel();
            this.updateFooter();
            this.commit();
        },

        // ── Color Wheel tab ────────────────────────────────────────────
        _renderWheel() {
            this._controls = [];
            this._body.innerHTML = '';
            const D = 196;
            const wrap = document.createElement('div');
            wrap.className = 'lrd-cw-wheelwrap';
            const wheel = document.createElement('div');
            wheel.className = 'lrd-cw-wheel';
            wheel.style.width = D + 'px';
            wheel.style.height = D + 'px';
            const canvas = document.createElement('canvas');
            canvas.width = D; canvas.height = D;
            canvas.className = 'lrd-cw-wheel-canvas';
            this._drawWheel(canvas, D);
            const darken = document.createElement('div');
            darken.className = 'lrd-cw-wheel-darken';
            const marker = document.createElement('div');
            marker.className = 'lrd-cw-wheel-marker';
            wheel.appendChild(canvas);
            wheel.appendChild(darken);
            wheel.appendChild(marker);
            wrap.appendChild(wheel);

            // Brightness slider (the wheel shows hue/saturation at full value;
            // this controls value/brightness).
            const brow = document.createElement('div');
            brow.className = 'lrd-cw-slider';
            const blab = document.createElement('div');
            blab.className = 'lrd-cw-slabel'; blab.textContent = 'Brightness';
            const srow = document.createElement('div'); srow.className = 'lrd-cw-srow';
            const range = document.createElement('input');
            range.type = 'range'; range.className = 'lrd-cw-range'; range.min = 0; range.max = 100;
            const num = document.createElement('input');
            num.type = 'number'; num.className = 'lrd-cw-num'; num.min = 0; num.max = 100;
            srow.appendChild(range); srow.appendChild(num);
            brow.appendChild(blab); brow.appendChild(srow);
            wrap.appendChild(brow);
            this._body.appendChild(wrap);

            this._wheel = { wheel, canvas, darken, marker, range, num, D };

            const pick = (e) => {
                const rect = canvas.getBoundingClientRect();
                const r = D / 2;
                let dx = (e.clientX - rect.left) - r;
                let dy = (e.clientY - rect.top) - r;
                const dist = Math.hypot(dx, dy);
                if (dist > r && dist > 0) { dx *= r / dist; dy *= r / dist; }
                const hue = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
                const sat = Math.min(100, Math.hypot(dx, dy) / r * 100);
                this.hsv.h = hue; this.hsv.s = sat;
                this.rgb = hsvToRgb(this.hsv.h, this.hsv.s, this.hsv.v);
                this._afterRgbChange({ keepHsv: true });
            };
            wheel.addEventListener('mousedown', (e) => {
                e.preventDefault(); pick(e);
                const mm = (ev) => pick(ev);
                const mu = () => { document.removeEventListener('mousemove', mm); document.removeEventListener('mouseup', mu); };
                document.addEventListener('mousemove', mm);
                document.addEventListener('mouseup', mu);
            });
            const setV = (v) => {
                if (!Number.isFinite(v)) return;
                this.hsv.v = clamp(v, 0, 100);
                this.rgb = hsvToRgb(this.hsv.h, this.hsv.s, this.hsv.v);
                this._afterRgbChange({ keepHsv: true });
            };
            range.addEventListener('input', () => setV(Number(range.value)));
            num.addEventListener('input', () => setV(Number(num.value)));

            this._syncWheel();
        },

        // Paint the hue/saturation wheel at full brightness once; the darken
        // overlay applies the current value, so brightness changes don't redraw.
        _drawWheel(canvas, D) {
            const ctx = canvas.getContext('2d');
            const r = D / 2;
            const img = ctx.createImageData(D, D);
            const data = img.data;
            for (let y = 0; y < D; y++) {
                for (let x = 0; x < D; x++) {
                    const dx = x - r, dy = y - r;
                    const dist = Math.hypot(dx, dy);
                    const i = (y * D + x) * 4;
                    if (dist > r) { data[i + 3] = 0; continue; }
                    const hue = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
                    const c = hsvToRgb(hue, Math.min(1, dist / r) * 100, 100);
                    data[i] = c.r; data[i + 1] = c.g; data[i + 2] = c.b;
                    // Soften the outer edge by a pixel to avoid a jagged rim.
                    data[i + 3] = dist > r - 1 ? Math.round(255 * (r - dist)) : 255;
                }
            }
            ctx.putImageData(img, 0, 0);
        },

        _syncWheel() {
            const w = this._wheel;
            if (!w) return;
            const r = w.D / 2;
            w.darken.style.opacity = String(1 - this.hsv.v / 100);
            const rad = this.hsv.h * Math.PI / 180;
            const dist = this.hsv.s / 100 * r;
            w.marker.style.left = (r + dist * Math.cos(rad)) + 'px';
            w.marker.style.top = (r + dist * Math.sin(rad)) + 'px';
            w.range.style.background = 'linear-gradient(to right, #000, ' + rgbStr(hsvToRgb(this.hsv.h, this.hsv.s, 100)) + ')';
            if (document.activeElement !== w.range) w.range.value = Math.round(this.hsv.v);
            if (document.activeElement !== w.num) w.num.value = Math.round(this.hsv.v);
        },

        // ── Color Palettes tab ─────────────────────────────────────────
        _renderPalettes() {
            this._wheel = null; this._controls = [];
            this._body.innerHTML = '';
            const row = document.createElement('div');
            row.className = 'lrd-cw-moderow';
            const sel = document.createElement('select');
            sel.className = 'lrd-cw-mode';
            const palettes = ['System', 'Web Safe Colors', 'Custom'];
            palettes.forEach(p => { const o = document.createElement('option'); o.value = p; o.textContent = p; sel.appendChild(o); });
            sel.value = this._paletteName || 'System';
            const addBtn = document.createElement('button');
            addBtn.type = 'button'; addBtn.className = 'lrd-cw-opts'; addBtn.textContent = '+';
            addBtn.title = 'Add the current color to the Custom palette';
            row.appendChild(sel); row.appendChild(addBtn);
            this._body.appendChild(row);

            const list = document.createElement('div');
            list.className = 'lrd-cw-palettelist';
            this._body.appendChild(list);

            const fill = () => {
                this._paletteName = sel.value;
                list.innerHTML = '';
                const items = this._paletteItems(sel.value);
                if (!items.length) {
                    const e = document.createElement('div');
                    e.className = 'lrd-cw-placeholder'; e.style.padding = '20px 8px';
                    e.textContent = 'No colors yet, click + to add the current color.';
                    list.appendChild(e); return;
                }
                items.forEach(it => {
                    const r2 = document.createElement('div');
                    r2.className = 'lrd-cw-paletterow';
                    const sw = document.createElement('span'); sw.className = 'lrd-cw-paletteswatch'; sw.style.background = it.hex;
                    const nm = document.createElement('span'); nm.className = 'lrd-cw-palettename'; nm.textContent = it.name;
                    r2.appendChild(sw); r2.appendChild(nm);
                    r2.addEventListener('click', () => { this.rgb = hexToRgb(it.hex); this._afterRgbChange(); });
                    list.appendChild(r2);
                });
            };
            sel.addEventListener('change', fill);
            addBtn.addEventListener('click', () => {
                const cur = this._loadCustomPalette();
                cur.push({ name: toHex(this.rgb.r, this.rgb.g, this.rgb.b), hex: toHex(this.rgb.r, this.rgb.g, this.rgb.b) });
                this._saveCustomPalette(cur);
                sel.value = 'Custom'; fill();
            });
            fill();
        },
        _paletteItems(name) {
            if (name === 'System') return SYSTEM_PALETTE;
            if (name === 'Custom') return this._loadCustomPalette();
            // Web Safe: 216 colors (00,33,66,99,CC,FF per channel)
            const out = []; const steps = ['00', '33', '66', '99', 'CC', 'FF'];
            steps.forEach(r => steps.forEach(g => steps.forEach(b => {
                const hex = ('#' + r + g + b).toUpperCase(); out.push({ name: hex, hex });
            })));
            return out;
        },
        _loadCustomPalette() { try { return JSON.parse(localStorage.getItem('lrd_cp_palette') || '[]'); } catch (e) { return []; } },
        _saveCustomPalette(a) { try { localStorage.setItem('lrd_cp_palette', JSON.stringify(a.slice(0, 200))); } catch (e) { /* ignore */ } },

        // ── Image Palettes tab (spectrum) ──────────────────────────────
        _renderImage() {
            this._wheel = null; this._controls = [];
            this._body.innerHTML = '';
            const row = document.createElement('div'); row.className = 'lrd-cw-moderow';
            const sel = document.createElement('select'); sel.className = 'lrd-cw-mode';
            const o = document.createElement('option'); o.textContent = 'Spectrum'; sel.appendChild(o);
            row.appendChild(sel); this._body.appendChild(row);

            const W = 222, H = 150;
            const canvas = document.createElement('canvas');
            canvas.width = W; canvas.height = H; canvas.className = 'lrd-cw-spectrum';
            const ctx = canvas.getContext('2d');
            const img = ctx.createImageData(W, H);
            const d = img.data;
            for (let y = 0; y < H; y++) {
                for (let x = 0; x < W; x++) {
                    const hue = x / (W - 1) * 360;
                    const t = y / (H - 1);                 // 0 (top) → 1 (bottom)
                    const sat = t < 0.5 ? t / 0.5 : 1;     // white → saturated
                    const val = t < 0.5 ? 1 : 1 - (t - 0.5) / 0.5; // saturated → black
                    const c = hsvToRgb(hue, sat * 100, val * 100);
                    const i = (y * W + x) * 4;
                    d[i] = c.r; d[i + 1] = c.g; d[i + 2] = c.b; d[i + 3] = 255;
                }
            }
            ctx.putImageData(img, 0, 0);
            this._body.appendChild(canvas);

            const pick = (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = clamp(Math.round((e.clientX - rect.left) / rect.width * W), 0, W - 1);
                const y = clamp(Math.round((e.clientY - rect.top) / rect.height * H), 0, H - 1);
                const p = ctx.getImageData(x, y, 1, 1).data;
                this.rgb = { r: p[0], g: p[1], b: p[2] };
                this._afterRgbChange();
            };
            canvas.addEventListener('mousedown', (e) => {
                e.preventDefault(); pick(e);
                const mm = (ev) => pick(ev);
                const mu = () => { document.removeEventListener('mousemove', mm); document.removeEventListener('mouseup', mu); };
                document.addEventListener('mousemove', mm); document.addEventListener('mouseup', mu);
            });
        },

        // ── Pencils tab ──────────────────────────────────────
        _renderPencils() {
            this._wheel = null; this._controls = [];
            this._body.innerHTML = '';
            const grid = document.createElement('div'); grid.className = 'lrd-cw-pencils';
            const nameEl = document.createElement('div'); nameEl.className = 'lrd-cw-pencilname';
            CRAYONS.forEach(c => {
                const cell = document.createElement('div');
                cell.className = 'lrd-cw-pencil'; cell.style.background = c.hex; cell.title = c.name;
                cell.addEventListener('click', () => {
                    nameEl.textContent = c.name;
                    this.rgb = hexToRgb(c.hex); this._afterRgbChange();
                });
                cell.addEventListener('mouseenter', () => { nameEl.textContent = c.name; });
                grid.appendChild(cell);
            });
            this._body.appendChild(grid);
            this._body.appendChild(nameEl);
            const cur = toHex(this.rgb.r, this.rgb.g, this.rgb.b);
            const match = CRAYONS.find(c => c.hex.toUpperCase() === cur);
            nameEl.textContent = match ? match.name : 'Pick a crayon';
        },

        // Push current state into the visible controls without disturbing the
        // control the user is actively editing.
        _syncUI() {
            const chans = this._getChannels(this.mode);
            this._controls.forEach((c) => {
                const ch = chans[c.idx];
                if (document.activeElement !== c.range) c.range.value = ch.val;
                if (document.activeElement !== c.number) c.number.value = ch.val;
                c.range.style.background = this._trackGradient(this.mode, c.idx);
            });
            if (this._hexField && document.activeElement !== this._hexField) {
                this._hexField.value = toHex(this.rgb.r, this.rgb.g, this.rgb.b).slice(1);
            }
        },

        _trackGradient(mode, idx) {
            const r = this.rgb.r, g = this.rgb.g, b = this.rgb.b;
            if (mode === 'rgb') {
                if (idx === 0) return 'linear-gradient(to right, rgb(0,' + g + ',' + b + '), rgb(255,' + g + ',' + b + '))';
                if (idx === 1) return 'linear-gradient(to right, rgb(' + r + ',0,' + b + '), rgb(' + r + ',255,' + b + '))';
                return 'linear-gradient(to right, rgb(' + r + ',' + g + ',0), rgb(' + r + ',' + g + ',255))';
            }
            if (mode === 'gray') return 'linear-gradient(to right, #000, #fff)';
            if (mode === 'cmyk') {
                const key = ['c', 'm', 'y', 'k'][idx];
                const a = Object.assign({}, this.cmyk); a[key] = 0;
                const z = Object.assign({}, this.cmyk); z[key] = 100;
                return 'linear-gradient(to right, ' + rgbStr(cmykToRgb(a.c, a.m, a.y, a.k)) + ', ' + rgbStr(cmykToRgb(z.c, z.m, z.y, z.k)) + ')';
            }
            // hsb
            if (idx === 0) return 'linear-gradient(to right,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00)';
            if (idx === 1) return 'linear-gradient(to right, ' + rgbStr(hsvToRgb(this.hsv.h, 0, this.hsv.v)) + ', ' + rgbStr(hsvToRgb(this.hsv.h, 100, this.hsv.v)) + ')';
            return 'linear-gradient(to right, #000, ' + rgbStr(hsvToRgb(this.hsv.h, this.hsv.s, 100)) + ')';
        },

        updateFooter() {
            if (this._well) this._well.style.background = toHex(this.rgb.r, this.rgb.g, this.rgb.b);
        },

        commit() {
            if (!this.target) return;
            const hex = toHex(this.rgb.r, this.rgb.g, this.rgb.b);
            this.target.value = hex.toLowerCase();
            this.target.dispatchEvent(new Event('input', { bubbles: true }));
            this.target.dispatchEvent(new Event('change', { bubbles: true }));
        },

        // ── Saved swatches (persisted) ─────────────────────────────────
        _loadSwatches() {
            try { return JSON.parse(localStorage.getItem('lrd_cp_swatches') || '[]'); } catch (e) { return []; }
        },
        _saveSwatches(arr) {
            try { localStorage.setItem('lrd_cp_swatches', JSON.stringify(arr.slice(0, 24))); } catch (e) { /* ignore */ }
        },
        _buildSwatches() {
            const saved = this._loadSwatches();
            this._swatchesEl.innerHTML = '';
            for (let i = 0; i < 24; i++) {
                const cell = document.createElement('div');
                cell.className = 'lrd-cw-swatch';
                const hex = saved[i];
                if (hex) { cell.classList.add('filled'); cell.style.background = hex; cell.title = hex; }
                cell.addEventListener('click', () => {
                    const cur = this._loadSwatches();
                    if (cur[i]) {                      // recall
                        this.rgb = hexToRgb(cur[i]); this._afterRgbChange();
                    } else {                            // store current
                        cur[i] = toHex(this.rgb.r, this.rgb.g, this.rgb.b);
                        this._saveSwatches(cur); this._buildSwatches();
                    }
                });
                cell.addEventListener('contextmenu', (e) => {  // clear
                    e.preventDefault();
                    const cur = this._loadSwatches();
                    if (cur[i]) { cur[i] = null; this._saveSwatches(cur); this._buildSwatches(); }
                });
                this._swatchesEl.appendChild(cell);
            }
        },

        _useEyedropper() {
            if (!window.EyeDropper) return;
            const ed = new window.EyeDropper();
            ed.open().then(res => {
                if (res && res.sRGBHex) { this.rgb = hexToRgb(res.sRGBHex); this._afterRgbChange(); }
            }).catch(() => { /* user cancelled */ });
        },

        isOpen() { return this.el && !this.el.hasAttribute('hidden'); },
        close() { if (this.el) this.el.setAttribute('hidden', ''); }
    };
    window.LRDColorWindow = FullPanel;

    // ── The picker (single shared instance) ────────────────────────────
    const ColorPicker = {
        el: null,
        target: null,        // the <input type=color> currently being edited
        _wired: false,

        ensureBuilt() {
            if (this.el) return;
            const pop = document.createElement('div');
            pop.className = 'lrd-cp-popover';
            pop.setAttribute('hidden', '');

            const rowVivid = this._buildRow(VIVID);
            const rowGray = this._buildRow(GRAYS, true);
            const divider = document.createElement('div');
            divider.className = 'lrd-cp-divider';
            const grid = this._buildGrid();

            const showBtn = document.createElement('button');
            showBtn.type = 'button';
            showBtn.className = 'lrd-cp-show';
            showBtn.textContent = 'Show Colors…';

            pop.appendChild(rowVivid);
            pop.appendChild(rowGray);
            pop.appendChild(divider);
            pop.appendChild(grid);
            pop.appendChild(showBtn);
            document.body.appendChild(pop);

            this.el = pop;

            // "Show Colors…" opens the full Colors window for the same target.
            showBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const t = this.target;
                this.close();
                FullPanel.open(t, t ? t.value : '#000000');
            });

            // Clicks inside the popover shouldn't bubble to the outside-close handler.
            pop.addEventListener('mousedown', (e) => e.stopPropagation());
        },

        _buildRow(colors, isGray) {
            const row = document.createElement('div');
            row.className = 'lrd-cp-row' + (isGray ? ' lrd-cp-gray-row' : '');
            colors.forEach((hex) => {
                const cell = document.createElement('div');
                cell.className = 'lrd-cp-cell';
                if (hex === 'none') {
                    cell.classList.add('lrd-cp-none');
                    cell.dataset.color = '#FFFFFF';
                    cell.title = 'White';
                } else {
                    cell.style.background = hex;
                    cell.dataset.color = hex;
                    cell.title = hex;
                }
                cell.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.commit(cell.dataset.color);
                    this.close();
                });
                row.appendChild(cell);
            });
            return row;
        },

        _buildGrid() {
            const grid = document.createElement('div');
            grid.className = 'lrd-cp-grid';
            GRID.forEach((hex) => {
                const cell = document.createElement('div');
                cell.className = 'lrd-cp-gcell';
                cell.style.background = hex;
                cell.dataset.color = hex;
                cell.title = hex;
                cell.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.commit(hex);
                    this.close();
                });
                grid.appendChild(cell);
            });
            return grid;
        },

        // Push the chosen color into the target input and fire the events the
        // app's existing handlers listen for.
        commit(hex) {
            const norm = normalizeHex(hex) || '#000000';
            if (!this.target) return;
            this.target.value = norm.toLowerCase();
            this.target.dispatchEvent(new Event('input', { bubbles: true }));
            this.target.dispatchEvent(new Event('change', { bubbles: true }));
        },

        openFor(input) {
            this.ensureBuilt();
            this.target = input;
            // Highlight the currently-matching swatch, if any.
            const cur = normalizeHex(input.value);
            this.el.querySelectorAll('.lrd-cp-selected').forEach(n => n.classList.remove('lrd-cp-selected'));
            if (cur) {
                this.el.querySelectorAll('[data-color]').forEach((n) => {
                    if ((n.dataset.color || '').toUpperCase() === cur) n.classList.add('lrd-cp-selected');
                });
            }
            this.el.removeAttribute('hidden');
            this._position(input);
        },

        _position(input) {
            const r = input.getBoundingClientRect();
            const pop = this.el;
            const pw = pop.offsetWidth || 234;
            const ph = pop.offsetHeight || 320;
            const margin = 6;
            let left = r.left;
            let top = r.bottom + margin;
            if (left + pw > window.innerWidth - 8) left = window.innerWidth - pw - 8;
            if (left < 8) left = 8;
            if (top + ph > window.innerHeight - 8) top = r.top - ph - margin; // flip above
            if (top < 8) top = 8;
            pop.style.left = Math.round(left) + 'px';
            pop.style.top = Math.round(top) + 'px';
        },

        close() {
            if (this.el) this.el.setAttribute('hidden', '');
            this.target = null;
        },

        isOpen() { return this.el && !this.el.hasAttribute('hidden'); },

        wire() {
            if (this._wired) return;
            this._wired = true;
            // Intercept clicks on any color input (delegated → covers dynamic ones).
            document.addEventListener('click', (e) => {
                if (!isEnabled()) return;
                const t = e.target;
                if (t && t.matches && t.matches('input[type="color"]')) {
                    e.preventDefault();
                    e.stopPropagation();
                    // Open the full Colors window directly (defaults to the wheel
                    // tab) so a color wheel pops up on the first click, instead of
                    // the compact swatch popover.
                    FullPanel.open(t, t.value);
                }
            }, true);
            // Close on outside click / Escape / scroll / resize.
            document.addEventListener('mousedown', () => { if (this.isOpen()) this.close(); });
            document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && this.isOpen()) this.close(); });
            window.addEventListener('resize', () => this.close());
            window.addEventListener('scroll', () => { if (this.isOpen()) this.close(); }, true);
        }
    };

    // Public handle (also used for forcing it on during dev).
    window.LRDColorPicker = {
        instance: ColorPicker,
        isEnabled,
        forceEnable() { try { localStorage.setItem('lrd_force_color_picker', '1'); } catch (e) { /* ignore */ } ColorPicker.wire(); },
        forceDisable() { try { localStorage.removeItem('lrd_force_color_picker'); } catch (e) { /* ignore */ } }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => ColorPicker.wire());
    } else {
        ColorPicker.wire();
    }
})();
