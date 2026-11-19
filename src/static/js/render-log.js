// render-log: what the app DRAWS, in the app log (2026-11-19 logging
// audit, phase 2). The owner, 2026-11-18: the log has to say what a view
// drew, not only what was saved - a 3D texture drew blue with a red corner
// while the screen's saved colours were blue, and nothing in the log said
// so. A line that read `mismatch: ["bl"]` would have.
//
// A classic script, loaded after canvas.js (templates/index.html), so the
// renderer's mixins below are on CanvasRenderer before main.js builds it;
// app-stage3d.js, app-output-display.js, app-export-io.js and app-binder.js
// use window.RenderLog for the colour reads and the line throttle.
// tests/test_render_log.py holds it to all of this.
//
// The rules every render line keeps:
//   * never per frame: a line is written when what was drawn changed (its
//     signature), at most one a target a second, and it carries `n`, the
//     repaints folded into it;
//   * colours are read 1 x 1 at a few points (getImageData), never the
//     picture: no data URL, no bytes, ever reaches the log;
//   * a cabinet read is held against CanvasRenderer._panelBaseFill, the
//     colour the screen's own settings give it, 20% in from a corner (clear
//     of the seams and the centred number); off by more than 6 a channel is
//     a mismatch and the line is a warning. A gradient, a see-through fill,
//     the printer palette or a test pattern has no one colour to hold it
//     against: the line says the check was skipped and why.
(function () {
    'use strict';

    const TOLERANCE = 6;

    const now = () => (window.performance && performance.now ? performance.now() : Date.now());

    function hex(rgb) {
        if (!rgb) return null;
        const h = (v) => Math.max(0, Math.min(255, Math.round(Number(v) || 0))).toString(16).padStart(2, '0');
        return ('#' + h(rgb[0]) + h(rgb[1]) + h(rgb[2])).toUpperCase();
    }

    // A CSS colour as the renderer writes it ('#rrggbb', '#rgb',
    // 'rgb(r, g, b)', 'rgba(...)') as [r, g, b], or null.
    function parse(fill) {
        const text = String(fill || '').trim();
        let m = /^#([0-9a-f]{6})$/i.exec(text);
        if (m) return [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16));
        m = /^#([0-9a-f]{3})$/i.exec(text);
        if (m) return [0, 1, 2].map(i => parseInt(m[1][i] + m[1][i], 16));
        m = /^rgba?\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)/i.exec(text);
        return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
    }

    // One pixel of a 2D context as [r, g, b, a], or null (off the canvas,
    // no context, a canvas the page may not read).
    function pixel(ctx, x, y) {
        try {
            if (!ctx || !ctx.canvas) return null;
            const c = ctx.canvas;
            const px = Math.floor(x), py = Math.floor(y);
            if (!(px >= 0 && py >= 0 && px < c.width && py < c.height)) return null;
            const d = ctx.getImageData(px, py, 1, 1).data;
            return [d[0], d[1], d[2], d[3]];
        } catch (_) {
            return null;
        }
    }

    // How a read pixel is written in the log: '#RRGGBB', or 'clear' where
    // nothing was drawn.
    function word(px) {
        if (!px) return null;
        return px[3] === 0 ? 'clear' : hex(px);
    }

    function off(a, b) {
        if (!a || !b) return Infinity;
        return Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]), Math.abs(a[2] - b[2]));
    }

    function near(a, b, tol = TOLERANCE) {
        return off(a, b) <= tol;
    }

    // A 3 x 3 grid of a canvas's colours: its corners, edge middles and
    // middle (at 1/6, 1/2 and 5/6 of each side), as words. Nine 1 x 1
    // reads; null for an empty canvas.
    const GRID = [['tl', 1, 1], ['t', 3, 1], ['tr', 5, 1], ['l', 1, 3], ['c', 3, 3], ['r', 5, 3],
        ['bl', 1, 5], ['b', 3, 5], ['br', 5, 5]];
    function grid(canvas, ctx) {
        try {
            if (!canvas || !canvas.width || !canvas.height) return null;
            const c2 = ctx || canvas.getContext('2d');
            if (!c2) return null;
            const out = {};
            for (const [k, fx, fy] of GRID) {
                out[k] = word(pixel(c2, canvas.width * fx / 6, canvas.height * fy / 6));
            }
            return out;
        } catch (_) {
            return null;
        }
    }

    // Why a screen's cabinets have no one colour to hold a read against,
    // or null when they do. The circle-and-X is drawn on the Pixel Map
    // only (and on by default), so it skips the check there alone.
    function skipWhy(renderer, layer, view) {
        if (!layer) return 'no screen';
        if ((layer.type || 'screen') !== 'screen') return 'not a screen';
        if (renderer && renderer.printerMode) return 'printer palette';
        if (layer.transparentFill) return 'see-through fill';
        if (layer.gradientEnabled) return 'gradient';
        if (layer.show_circle_with_x && (!view || view === 'pixel-map')) return 'test pattern';
        return null;
    }

    // The colour a cabinet of `layer` should read, as [r, g, b]: the
    // screen's own checker or palette colour (_panelBaseFill).
    function expected(renderer, panel, layer) {
        if (!renderer || typeof renderer._panelBaseFill !== 'function') return null;
        try { return parse(renderer._panelBaseFill(panel, layer)); } catch (_) { return null; }
    }

    // A screen's name as the log writes it: "STAGE LEFT (#2)".
    function screenName(layer) {
        if (!layer) return '';
        return `${layer.name || 'Screen'} (#${layer.id})`;
    }

    // Up to `max` screen names, and how many more.
    function names(layers, max = 8) {
        const list = (layers || []).map(screenName);
        return list.length > max ? [...list.slice(0, max), `+${list.length - max} more`] : list;
    }

    // A 32-bit hash of a string (FNV-1a), for a signature that would
    // otherwise keep a whole show's text.
    function hash(text) {
        let h = 0x811c9dc5;
        const s = String(text);
        for (let i = 0; i < s.length; i++) {
            h ^= s.charCodeAt(i);
            h = Math.imul(h, 0x01000193);
        }
        return (h >>> 0).toString(36);
    }

    // What a screen's drawing depends on, as one short hash: the layer as
    // it is saved (runtime caches, its 3D block and image bytes left out).
    function layerHash(layer) {
        try {
            return hash(JSON.stringify(layer, (k, v) => {
                if (k && k.charAt(0) === '_') return undefined;
                if (k === 'stage3d' || k === 'locked') return undefined;
                if (k === 'imageData' && typeof v === 'string') return v.length;
                return v;
            }));
        } catch (_) {
            return 'x';
        }
    }

    // The line throttle every target uses. `seen(info)` is called on every
    // repaint (cheap: it only keeps `info`); the line is written by
    // emit(info, n) once the repaints stop for `quietMs` (or at once with
    // `leading`, the first after a gap), never within `gapMs` of the last
    // line, and only when sig(info) differs from the last line's (no sig:
    // every one counts). `n` is the repaints since the last line.
    function watcher(opts) {
        const o = Object.assign({ quietMs: 750, gapMs: 1000, leading: false, sig: null }, opts || {});
        const w = { lastSig: undefined, lastAt: -Infinity, n: 0, info: null, timer: null };
        const fire = () => {
            w.timer = null;
            const info = w.info;
            if (!info) return;
            let sig = null;
            if (o.sig) {
                try { sig = o.sig(info); } catch (_) { sig = null; }
                if (sig === w.lastSig) return;
            }
            const n = w.n;
            w.n = 0;
            w.info = null;
            w.lastSig = sig;
            w.lastAt = now();
            try { o.emit(info, n); } catch (_) { /* logging never stops a picture */ }
        };
        w.seen = (info) => {
            w.n += 1;
            w.info = info;
            const t = now();
            if (o.leading && !w.timer && t - w.lastAt >= o.gapMs) {
                fire();
                return;
            }
            if (w.timer && o.leading) return;
            clearTimeout(w.timer);
            const wait = Math.max(o.leading ? 0 : o.quietMs, w.lastAt + o.gapMs - t);
            w.timer = setTimeout(fire, Math.max(0, wait));
        };
        w.flush = () => { if (w.timer) { clearTimeout(w.timer); fire(); } };
        w.reset = () => { clearTimeout(w.timer); w.timer = null; w.lastSig = undefined; w.lastAt = -Infinity; w.n = 0; w.info = null; };
        return w;
    }

    function send(action, details, opts) {
        try {
            if (typeof window.sendClientLog === 'function') window.sendClientLog(action, details, opts);
        } catch (_) { /* never in the way */ }
    }

    const VIEW_WORDS = {
        'pixel-map': 'Pixel Map', 'cabinet-id': 'Cabinet ID', 'show-look': 'Show Look',
        'data-flow': 'Data', power: 'Power', rigging: 'Header/Footer', idm: 'IDM Locator', '3d': '3D',
    };
    function viewWord(view) {
        return VIEW_WORDS[view] || String(view || '');
    }

    window.RenderLog = {
        TOLERANCE, hex, parse, pixel, word, off, near, grid, skipWhy, expected, screenName, names,
        hash, layerHash, watcher, send, viewWord, now,
    };

    // ── the 2D view's own lines (CanvasRenderer mixin) ──────────────────
    //
    // render() calls _rlBegin at its top and _rlEnd at its end, on a main
    // (not export, not offscreen) pass only. While the pass runs the
    // renderers note what they draw through _rlCount, _rlError and
    // _rlPanel; _rlEnd keeps it as the view's latest frame and the
    // watcher writes render_view once the view has been quiet 750 ms, if
    // its signature (the view, the canvas, its Front/Back, the screens
    // shown and each one's saved drawing) changed: zoom, pan, hover and
    // selection never write a line. The error overlays (a data port over
    // capacity, a power error, an OVER circuit) write render_overlay, a
    // warning, when the set of them in a view changes.
    const C = window.CanvasRenderer;
    if (!C || !C.prototype) return;

    const viewLine = watcher({
        quietMs: 750, gapMs: 1000,
        sig: (f) => f.renderer._rlSignature(f),
        emit: (f, n) => f.renderer._rlWriteView(f, n),
    });
    const overlayLine = watcher({
        quietMs: 300, gapMs: 1000,
        sig: (f) => f.view + '|' + f.errorKeys,
        emit: (f) => f.renderer._rlWriteOverlay(f),
    });
    const lastErrorKeys = {};

    Object.assign(C.prototype, {
        _rlBegin() {
            if (this.exportMode || this._idmPass) return 0;
            this._rlFrame = { counts: {}, errors: new Map(), samples: [], skip: null, ctx: this.ctx };
            return now() || 1;
        },

        // the frame's notes, from the renderers while the main pass runs
        _rlCount(name, by = 1) {
            const f = this._rlFrame;
            if (!f || this.exportMode) return;
            f.counts[name] = (f.counts[name] || 0) + by;
        },
        _rlError(key, text) {
            const f = this._rlFrame;
            if (!f || this.exportMode) return;
            if (!f.errors.has(key)) f.errors.set(key, String(text || key));
        },

        // A cabinet of the selected screen just filled (renderPixelMap,
        // renderCabinetID): where two of its points landed on the page,
        // for the read once the view is quiet. One cabinet of each of its
        // colours (two for a checker), each read at two points: a label
        // over one point is not a wrong colour, so a cabinet counts as
        // wrong only when both are off.
        _rlPanel(panel, layer) {
            const f = this._rlFrame;
            if (!f || this.exportMode || f.samples.length >= 2 || !panel || panel.hidden || panel.blank) return;
            const app = window.app;
            const cur = app && app.currentLayer;
            if (!cur || cur.id !== layer.id) return;
            // a one-colour screen has no second colour to find: stop looking
            // after a few cabinets, so a big wall costs nothing per frame
            f.tries = (f.tries || 0) + 1;
            if (f.tries > 64) return;
            const want = expected(this, panel, layer);
            if (!want) return;
            const key = hex(want);
            if (f.samples.some(s => s.expect === key)) return;
            let m;
            try { m = this.ctx.getTransform(); } catch (_) { return; }
            const w = Number(panel.width) || 0, h = Number(panel.height) || 0;
            // too small on the page to read clear of its borders
            if (Math.min(Math.hypot(m.a * w, m.b * w), Math.hypot(m.c * h, m.d * h)) < 12) {
                f.skip = f.skip || 'cabinets too small on screen';
                return;
            }
            const at = (fx, fy) => {
                const x = (Number(panel.x) || 0) + w * fx, y = (Number(panel.y) || 0) + h * fy;
                return [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f];
            };
            f.samples.push({ expect: key, rgb: want, row: panel.row, col: panel.col, pts: [at(0.2, 0.2), at(0.8, 0.8)] });
        },

        _rlEnd(t0, view) {
            const f = this._rlFrame;
            this._rlFrame = null;
            if (!f || !t0) return;
            f.ms = Math.round((now() - t0) * 10) / 10;
            f.view = view || this.viewMode;
            f.renderer = this;
            const app = window.app;
            const proj = app && app.project;
            f.canvasId = proj ? proj.active_canvas_id || null : null;
            f.errorKeys = [...f.errors.keys()].sort().join(',');
            const before = lastErrorKeys[f.view];
            if (before !== undefined ? before !== f.errorKeys : f.errors.size > 0) {
                lastErrorKeys[f.view] = f.errorKeys;
                overlayLine.seen(f);
            } else if (before === undefined) {
                lastErrorKeys[f.view] = f.errorKeys;
            }
            viewLine.seen(f);
        },

        // the screens the frame showed: visible, on a visible canvas
        _rlShown(f) {
            const app = window.app;
            const proj = app && app.project;
            if (!proj || !Array.isArray(proj.layers)) return [];
            const canvases = Array.isArray(proj.canvases) ? proj.canvases : [];
            const hidden = new Set(canvases.filter(c => c && c.visible === false).map(c => c.id));
            return proj.layers.filter(l => l && l.visible && (l.type || 'screen') === 'screen'
                && !hidden.has(this._effectiveLayerCanvasId ? this._effectiveLayerCanvasId(l) : l.canvas_id));
        },

        _rlPerspective(f) {
            const app = window.app;
            const proj = app && app.project;
            const c = proj && Array.isArray(proj.canvases) ? proj.canvases.find(x => x && x.id === f.canvasId) : null;
            if (f.view === 'data-flow') return (c && c.data_flow_perspective) || 'front';
            if (f.view === 'power') return (c && c.power_perspective) || 'front';
            return null;
        },

        // What the view drew depends on: never zoom, pan, hover or selection.
        _rlSignature(f) {
            const shown = this._rlShown(f);
            const app = window.app;
            const proj = app && app.project;
            const groups = proj && proj.groups ? hash(JSON.stringify(proj.groups)) : '';
            const stages = this.renderStages ? [...this.renderStages].sort().join(',') : '';
            return [f.view, f.canvasId, this._rlPerspective(f), stages, groups,
                shown.map(l => l.id + ':' + layerHash(l)).join(',')].join('|');
        },

        // The selected screen's cabinets as the page shows them now, against
        // the colours its settings give them.
        _rlColourCheck(f) {
            const app = window.app;
            const cur = app && app.currentLayer;
            if (!cur) return { skipped: 'no screen selected' };
            if (!['pixel-map', 'cabinet-id', 'show-look', 'rigging'].includes(f.view)) {
                return { skipped: 'this view draws over the cabinets' };
            }
            const why = skipWhy(this, cur, f.view) || (app.pixelMapSelection && app.pixelMapSelection.size ? 'cabinets picked' : null);
            if (why) return { screen: screenName(cur), skipped: why };
            if (!f.samples.length) return { screen: screenName(cur), skipped: f.skip || 'not on screen' };
            const out = { screen: screenName(cur), drew: {}, expect: {}, mismatch: [] };
            let read = 0;
            f.samples.forEach((s) => {
                const name = `r${s.row}c${s.col}`;
                const reads = s.pts.map(([x, y]) => pixel(f.ctx, x, y));
                const got = reads.find(p => p && near(p, s.rgb)) || reads.find(Boolean);
                if (!got) return;
                read += 1;
                out.drew[name] = word(got);
                out.expect[name] = s.expect;
                if (reads.every(p => p) && reads.every(p => !near(p, s.rgb))) out.mismatch.push(name);
            });
            return read ? out : { screen: screenName(cur), skipped: 'off the page' };
        },

        // The view's counts that are cheap to read off what was drawn.
        _rlCounts(f, shown) {
            const c = Object.assign({}, f.counts);
            if (f.view === 'power') {
                c.circuits = shown.reduce((n, l) => n + (Array.isArray(l._powerCircuits) ? l._powerCircuits.length : 0), 0);
            }
            if (f.view === 'rigging' && window.app && typeof window.app.riggingRowsOf === 'function') {
                let bars = 0;
                shown.forEach(l => {
                    try {
                        (window.app.riggingRowsOf(l) || []).forEach(row => {
                            bars += (row.placed || []).filter(b => b.owner === l).length;
                        });
                    } catch (_) { /* a wall with no bars */ }
                });
                c.bars = bars;
            }
            if (f.view === 'idm') {
                c.marked = shown.reduce((n, l) => n + ((l.idm && l.idm.marks && typeof l.idm.marks === 'object')
                    ? Object.keys(l.idm.marks).length : 0), 0);
                if (typeof this.idmFieldSpec === 'function') {
                    try { c.field = this.idmFieldSpec().color; } catch (_) { /* default field */ }
                }
            }
            if (f.errors.size) c.errors = f.errors.size;
            return c;
        },

        _rlWriteView(f, n) {
            const app = window.app;
            const proj = app && app.project;
            const shown = this._rlShown(f);
            const canvas = proj && Array.isArray(proj.canvases) ? proj.canvases.find(c => c && c.id === f.canvasId) : null;
            const counts = this._rlCounts(f, shown);
            const colours = this._rlColourCheck(f);
            const bad = colours.mismatch && colours.mismatch.length;
            const details = {
                view: f.view, canvas: canvas ? canvas.name || canvas.id : null,
                perspective: this._rlPerspective(f) || undefined,
                screens: { n: shown.length, names: names(shown) },
                counts, colours, ms: f.ms, n,
            };
            const parts = Object.entries(counts).filter(([k]) => k !== 'field' && k !== 'errors')
                .map(([k, v]) => `${v} ${k}`);
            if (counts.field) parts.push(`field ${counts.field}`);
            let msg = `${viewWord(f.view)} drew ${shown.length} screen${shown.length === 1 ? '' : 's'}`
                + (canvas ? ` on ${canvas.name || canvas.id}` : '')
                + (parts.length ? ` (${parts.join(', ')})` : '');
            if (counts.errors) msg += `, ${counts.errors} error overlay${counts.errors === 1 ? '' : 's'}`;
            if (bad) {
                const k = colours.mismatch[0];
                msg = `${viewWord(f.view)} shows ${colours.screen} in the wrong colour at ${colours.mismatch.join(', ')}: `
                    + `drew ${colours.drew[k]}, saved ${colours.expect[k]}`;
            }
            send('render_view', details, { level: bad ? 'warn' : 'info', area: 'render', msg });
        },

        _rlWriteOverlay(f) {
            const list = [...f.errors.entries()].map(([key, text]) => ({ key, text }));
            const shown = list.slice(0, 8);
            const msg = list.length
                ? `${viewWord(f.view)} shows ${list.length} error overlay${list.length === 1 ? '' : 's'}: `
                    + shown.map(e => e.text).join('; ') + (list.length > shown.length ? '; ...' : '')
                : `${viewWord(f.view)} error overlays cleared`;
            send('render_overlay', { view: f.view, errors: shown, n: list.length },
                { level: list.length ? 'warn' : 'info', area: 'render', msg });
        },
    });
})();
