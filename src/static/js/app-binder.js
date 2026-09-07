// app-binder: the binder packet - the show's power and data maps, one page
// per screen, with the pull tables under each map, laid out on the client
// as bitmaps and bound into one PDF through /api/export/pdf-from-images.
//
// The page is binder-mock.html's Type A, as the user picked it (2026-09-06):
// the screen's map across the top half or more of a landscape letter page
// ("the photo of the screen to fill it a bit more. maybe 50% or more"),
// with column and row RULERS around it (numbering "2"), a bracket outside
// the wall per BREAKOUT with its name and home run (the thing a multi's
// circuits come out of is the breakout - "Breakout", never "Box", never
// "Multi" (2026-09-07); the home run said once per breakout), then three
// columns - Circuits grouped under a band row per breakout, Cables, Facts
// ("change it to circles, cables and then facts") - and a Gangs table under
// Facts ONLY when the screen has 2fers or 3fers ("only include 2 fer and 3
// fer info if it actually has it"). Two palettes: Colour, and Printer ("a
// black and white printer friendly version as well as color") - the
// renderer's printerMode (canvas.js).
//
// The map IS the canvas renderer's own drawing in exportMode - runs,
// arrowheads, label discs sized to their text, the cable tags where the
// screen's Show Cable Tags switch is on, the gang brackets where its 2fer
// switch is on. Those switches are the user's documentation choices and
// the binder follows them; it forces nothing on. The one thing the page
// takes off the wall is the screen-name plate (hideScreenNames): the
// header already names the screen, and on a wall of circuits the plate
// landed on top of the labels ("the main label is over the circuits").
//
// A band (the breakout's row over its circuits, the card's over its
// ports) never sits at the foot of a column without at least two of its
// rows under it - an orphaned band read as a page cut off; it moves to
// the next column with its rows, and a band whose rows run on across a
// break is repeated there with "(cont.)".
//
// Pages, in order: cover; per POSITION (a screen group, else the screen
// itself - the pull list's positions) a pull page with tick boxes, then
// each screen's POWER page and DATA page; hardware pages (one per distro,
// one per processor); the show-wide pull list. A page with nothing on it
// is skipped - a screen with no circuits has no power page. A single
// screen can be exported alone from the canvas's right-click menu.
//
// Every figure is read from buildPullSheet (app-pull-list.js) and the same
// authorities the canvas reads; nothing is recomputed here.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// Landscape letter at 200 dpi. The PDF route sizes the page in points
// (`page_size`) and scales the bitmap to fill it.
const PAGE_W = 2200;
const PAGE_H = 1700;
const PAGE_PT = [792, 612];
const PAD = 42;                       // 1.9cqw of the mock
const FONT = '-apple-system, "Segoe UI", Helvetica, Arial, sans-serif';
const INK = '#111111';
const RULE = '#333333';
const FAINT = '#cccccc';
const MUTED = '#666666';
const BAND_BG = '#e9e9e9';
// Type sizes (px on the 2200-wide page; 1cqw of the mock is 22px).
const SZ = { show: 35, page: 27, h4: 25, cell: 24, th: 21, foot: 22,
             ruler: 22, bracket: 28, plate: 30, title: 96, sub: 38, meta: 30 };
const ROW_H = 38;
const BAND_H = 46;
const TH_H = 40;
const H4_H = 46;
const BLOCK_GAP = 22;
const HEADER_BOTTOM = 92;             // first content y under the header rule
const FOOTER_TOP = PAGE_H - 58;       // last content y above the footer rule
const MAP_H = 884;                    // >= 52% of the page height for the map
const MAP_GUTTER = { left: 200, right: 180, top: 74, bottom: 16 };

// Cable types print in the GEAR LIST's own vocabulary - the same words the
// workbook export writes - so the binder's Cables table and the pull sheet
// agree row for row. The word the user retired was "Multi" as the name of
// the THING the circuits come out of (that is a breakout); the multi CABLE
// keeps its shop name.
const BINDER_TYPE_WORDS = {};

// The redundancy bar's own words (app-processors.js), so the page reads
// what the tray reads: "Per card", "Whole unit → H9 BACKUP", "Off".
const REDUNDANCY_WORDS = {
    off: 'Off', port: 'Per port', card: 'Per card', unit: 'Whole unit',
    fixed: 'On', backup: 'Backed up',
};

class _Binder {

    // ---- the export dialog's Binder section ---------------------------------

    // Wired once from setupEventListeners, after the pull-sheet controls so
    // this runs after syncPullSheetControls on a format change and gets
    // the last word on which sections show.
    initBinderControls() {
        if (this._binderControlsWired) return;
        this._binderControlsWired = true;
        const fmt = document.getElementById('export-format');
        if (fmt) fmt.addEventListener('change', () => this.syncBinderControls());
        const scope = document.getElementById('export-binder-scope');
        if (scope) {
            scope.addEventListener('change', () => {
                // A single screen is that screen's pages and nothing else
                // unless asked; the whole show is the whole book.
                const single = scope.value !== 'show';
                ['export-binder-cover', 'export-binder-pull', 'export-binder-hardware']
                    .forEach(id => {
                        const el = document.getElementById(id);
                        if (el) el.checked = !single;
                    });
                if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
            });
        }
        const eng = document.getElementById('export-binder-engineer');
        if (eng) eng.addEventListener('change', () => { this.setEngineerName(eng.value); });
        const rev = document.getElementById('export-binder-rev');
        if (rev) {
            rev.addEventListener('change', () => {
                this.setPullSheetSetting('rev', rev.value, 'Set Pull Sheet Revision');
                this.syncBinderControls();
            });
        }
    }

    // The section shown only for the binder format, the picture sections
    // hidden then (a book of pages has no canvas list or view ticks), the
    // scope list rebuilt from the screens as they stand.
    syncBinderControls() {
        const fmt = document.getElementById('export-format');
        const on = !!fmt && fmt.value === 'binder';
        const show = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.style.display = v ? '' : 'none';
        };
        show('export-binder-section', on);
        if (!on) return;
        show('export-canvases-section', false);
        show('export-views-section', false);
        show('export-options-section', false);
        show('export-pull-sheet-section', false);
        const scope = document.getElementById('export-binder-scope');
        if (scope) {
            const want = this._binderPresetScope != null
                ? `screen:${this._binderPresetScope}` : (scope.value || 'show');
            this._binderPresetScope = null;
            scope.innerHTML = '';
            const opt = (value, text) => {
                const o = document.createElement('option');
                o.value = value; o.textContent = text;
                scope.appendChild(o);
            };
            opt('show', 'Whole show');
            for (const l of this._pullScreens()) opt(`screen:${l.id}`, `Screen: ${l.name || l.id}`);
            scope.value = [...scope.options].some(o => o.value === want) ? want : 'show';
            if (want !== 'show' && scope.value === want) {
                ['export-binder-cover', 'export-binder-pull', 'export-binder-hardware']
                    .forEach(id => {
                        const el = document.getElementById(id);
                        if (el) el.checked = false;
                    });
            }
        }
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        set('export-binder-engineer', this.getEngineerName());
        set('export-binder-rev', this.getPullSheetSettings().rev);
    }

    // What the dialog says, as the book reads it.
    readBinderOptions() {
        const val = (id) => { const el = document.getElementById(id); return el ? el.value : null; };
        const on = (id, dflt) => { const el = document.getElementById(id); return el ? !!el.checked : dflt; };
        const scopeRaw = val('export-binder-scope') || 'show';
        const scope = scopeRaw.startsWith('screen:')
            ? { kind: 'screen', layerId: scopeRaw.slice('screen:'.length) }
            : { kind: 'show' };
        const printer = on('export-binder-printer', false);
        const side = on('export-binder-side-power', false) ? 'power'
            : on('export-binder-side-data', false) ? 'data' : 'both';
        return {
            palette: printer ? 'printer' : 'colour',
            sides: { power: side !== 'data', data: side !== 'power' },
            scope,
            cover: on('export-binder-cover', scope.kind === 'show'),
            pull: on('export-binder-pull', scope.kind === 'show'),
            hardware: on('export-binder-hardware', scope.kind === 'show'),
        };
    }

    // The canvas's right-click: "Export this screen..." opens the same
    // dialog preset to the binder with only that screen's pages ticked.
    openScreenBinderExport(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return;
        this._binderPresetScope = layer.id;
        this.openExportModal('binder');
        if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
        sendClientLog('binder_screen_export_opened', { layerId: layer.id });
    }

    // The screen the right-click landed on, for the menu item above:
    // hit-tested where the cursor is (the wiring views do not select on
    // right-click), else the selected screen.
    _prepareBinderMenu(x, y) {
        const r = window.canvasRenderer;
        let layer = null;
        if (r && r.canvas) {
            const under = document.elementFromPoint(x, y);
            if (under === r.canvas) {
                const rect = r.canvas.getBoundingClientRect();
                const worldY = ((y - rect.top) - r.panY) / r.zoom;
                const worldX = r._unmirrorWorldX(((x - rect.left) - r.panX) / r.zoom, worldY);
                const hit = r.getLayerAt(worldX, worldY);
                if (hit && (hit.type || 'screen') === 'screen') layer = hit;
            }
        }
        if (!layer && this.currentLayer && (this.currentLayer.type || 'screen') === 'screen') {
            layer = this.currentLayer;
        }
        return layer;
    }

    // The file the dialog's preview names.
    binderFileName(projectName) {
        const opts = this.readBinderOptions();
        const name = projectName || (this.project && this.project.name) || 'Project';
        if (opts.scope.kind === 'screen') {
            const layer = (this.project.layers || []).find(l => String(l.id) === String(opts.scope.layerId));
            if (layer) return `${name} - ${layer.name || layer.id} - binder.pdf`;
        }
        return `${name} - binder.pdf`;
    }

    // ---- the export ---------------------------------------------------------

    // Pages rendered, one PDF back, saved straight to disk through the same
    // picker path every export takes - no window, no print dialog.
    async exportBinder(projectName) {
        const name = projectName || (this.project && this.project.name) || 'Project';
        const opts = this.readBinderOptions();
        if (typeof this.refreshPortAssignment === 'function') {
            try { await this.refreshPortAssignment(); } catch (_) {}
        }
        const images = this.renderBinderPages(opts);
        if (!images.length) throw new Error('Nothing to bind: no screen has circuits or ports');
        sendClientLog('export_binder_start', {
            pages: images.length, palette: opts.palette, scope: opts.scope.kind,
        });
        const response = await fetch('/api/export/pdf-from-images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: name,
                labels: false,
                images: images.map(i => ({
                    name: i.name, data: i.dataUrl,
                    width: PAGE_W, height: PAGE_H, page_size: PAGE_PT,
                })),
                width: PAGE_W, height: PAGE_H,
            }),
        });
        if (!response.ok) {
            let msg = 'Failed to build the binder';
            try { msg = (await response.json()).error || msg; } catch (_) {}
            throw new Error(msg);
        }
        const blob = await response.blob();
        await this.saveBlobWithPicker(blob, this.binderFileName(name), 'application/pdf');
        return { pages: images.length };
    }

    // The page list, without drawing anything: [{ kind, title, layerId }].
    planBinder(opts) {
        const book = this._binderBook(opts || this.readBinderOptions(), { dry: true });
        return book.pages.map(p => ({ kind: p.kind, title: p.title, layerId: p.layerId || null,
                                      subject: p.subject || null }));
    }

    // Every page as a PNG data URL, in order.
    renderBinderPages(opts) {
        const o = opts || this.readBinderOptions();
        const total = this._binderBook(o, { dry: true }).pages.length;
        const book = this._binderBook(o, { dry: false, total });
        return book.images;
    }

    // One page painted for a look (tests, previews): the page's canvas plus
    // every text the page and its map drew and every dash the map set.
    renderBinderPage(opts, index) {
        const o = opts || this.readBinderOptions();
        const plan = this._binderBook(o, { dry: true });
        const log = { texts: [], textInfo: [], mapTexts: [], dashes: [] };
        const book = this._binderBook(o, { dry: false, total: plan.pages.length, only: index, log });
        this._binderLastCanvas = book.canvas;
        return { canvas: book.canvas, texts: log.texts, textInfo: log.textInfo, mapTexts: log.mapTexts,
                 dashes: log.dashes, page: plan.pages[index] || null, pages: plan.pages.length };
    }

    // ---- the book -----------------------------------------------------------

    _binderBook(opts, run) {
        // The edited list: the pull pages and the totals page print what
        // the user's pull-sheet edits say; the per-screen readings
        // (byScreen, hardware) are the show's own.
        const list = this.buildPullSheet();
        const settings = list.settings || this.getPullSheetSettings();
        const layers = new Map((this.project.layers || []).map(l => [String(l.id), l]));
        const meta = {
            show: (this.project && this.project.name) || 'Untitled Project',
            date: this._pullSheetDate().date,
            rev: settings.rev,
            engineer: this.getEngineerName(),
            palette: opts.palette === 'printer' ? 'printer' : 'colour',
        };
        const canvas = run.dry ? null : (this._binderCanvas || (this._binderCanvas = document.createElement('canvas')));
        if (canvas) { canvas.width = PAGE_W; canvas.height = PAGE_H; }
        const realCtx = canvas ? canvas.getContext('2d') : null;
        // Measuring needs a real context even on the dry pass.
        const measureCtx = realCtx || (this._binderMeasureCtx
            || (this._binderMeasureCtx = document.createElement('canvas').getContext('2d')));
        const book = {
            opts, list, meta, layers, run,
            dry: !!run.dry, total: run.total || 0, only: run.only,
            log: run.log || null,
            pages: [], images: [], canvas, realCtx, measureCtx, ctx: null, page: null,
        };
        const scopeLayer = opts.scope && opts.scope.kind === 'screen'
            ? layers.get(String(opts.scope.layerId)) || null : null;
        if (opts.scope && opts.scope.kind === 'screen' && !scopeLayer) return this._binderFinish(book);

        if (opts.cover) this._bCoverPage(book);
        for (const pos of list.positions) {
            const members = pos.layerIds.map(id => layers.get(String(id))).filter(Boolean);
            const mine = scopeLayer ? members.filter(l => l.id === scopeLayer.id) : members;
            if (!mine.length) continue;
            if (opts.pull) this._bPullPage(book, pos, members);
            for (const layer of mine) {
                const scr = list.byScreen[layer.id];
                if (!scr) continue;
                if (opts.sides.power && this._bHasPower(layer, scr)) {
                    this._bScreenPage(book, layer, pos, 'power');
                }
                if (opts.sides.data && this._bHasData(layer, scr)) {
                    this._bScreenPage(book, layer, pos, 'data');
                }
            }
        }
        if (opts.hardware) {
            for (const d of (typeof this.getDistros === 'function' ? this.getDistros() : [])) {
                this._bDistroPage(book, d);
            }
            for (const proc of (this._processorsResolved || [])) this._bProcessorPage(book, proc);
        }
        if (opts.pull) this._bTotalsPage(book);
        return this._binderFinish(book);
    }

    _binderFinish(book) {
        this._bClosePage(book);
        return book;
    }

    _bHasPower(layer, scr) {
        return (scr.boxes || []).some(b => (b.circuits || []).length > 0)
            || (typeof this.screenCircuits === 'function' && this.screenCircuits(layer).length > 0);
    }

    _bHasData(layer, scr) {
        return (scr.ports || []).length > 0;
    }

    // ---- pages: open, header, footer, close ---------------------------------

    // A new page. `header` is { left, right } for the band under the top
    // rule; the cover passes none. Drawing goes through book.ctx, which is
    // the real context only on a painting pass and only for the page being
    // painted - otherwise a proxy that measures text and draws nothing.
    _bNewPage(book, kind, title, header, extra) {
        this._bClosePage(book);
        const index = book.pages.length;
        const page = { index, kind, title, header, ...(extra || {}) };
        book.pages.push(page);
        book.page = page;
        const painting = !book.dry && book.realCtx
            && (book.only == null || book.only === index);
        page.painting = painting;
        book.ctx = painting ? book.realCtx : this._bDryCtx(book.measureCtx);
        const ctx = book.ctx;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, PAGE_W, PAGE_H);
        if (header) {
            this._bText(book, header.left, PAD, 60, { size: SZ.show, weight: 800, upper: true });
            const right = `${header.right} · page ${index + 1} of ${book.total || '?'}`;
            this._bText(book, right, PAGE_W - PAD, 60, { size: SZ.page, align: 'right' });
            ctx.fillStyle = INK;
            ctx.fillRect(PAD, 70, PAGE_W - PAD * 2, 6);
        }
        // Footer: the app, the show, the revision; the page's subject and
        // the date.
        ctx.fillStyle = '#bbbbbb';
        ctx.fillRect(PAD, FOOTER_TOP + 8, PAGE_W - PAD * 2, 2);
        this._bText(book, `LED Raster Designer · ${book.meta.show} · rev ${book.meta.rev}`,
                    PAD, PAGE_H - 22, { size: SZ.foot, color: MUTED });
        const foot = [page.footer || title, book.meta.date].filter(Boolean).join(' · ');
        this._bText(book, foot, PAGE_W - PAD, PAGE_H - 22, { size: SZ.foot, color: MUTED, align: 'right' });
        return page;
    }

    _bClosePage(book) {
        const page = book.page;
        if (!page) return;
        if (page.painting && book.canvas && book.only == null) {
            book.images.push({ name: page.title, dataUrl: book.canvas.toDataURL('image/png'),
                               width: PAGE_W, height: PAGE_H });
        }
        book.page = null;
        book.ctx = null;
    }

    // A context that measures and does nothing else.
    _bDryCtx(measureCtx) {
        if (!this._binderDryProxy || this._binderDryProxyTarget !== measureCtx) {
            this._binderDryProxyTarget = measureCtx;
            this._binderDryProxy = new Proxy(measureCtx, {
                get(t, k) {
                    if (k === 'measureText') return t.measureText.bind(t);
                    const v = t[k];
                    return typeof v === 'function' ? () => {} : v;
                },
                set(t, k, v) { t[k] = v; return true; },
            });
        }
        return this._binderDryProxy;
    }

    // ---- text ---------------------------------------------------------------

    _bFont(size, weight) {
        return `${weight || 400} ${size}px ${FONT}`;
    }

    _bText(book, text, x, y, o) {
        const ctx = book.ctx;
        const opts = o || {};
        let t = String(text == null ? '' : text);
        if (opts.upper) t = t.toUpperCase();
        let size = opts.size || SZ.cell;
        ctx.font = this._bFont(size, opts.weight);
        // A heading shrinks a little before it is cut: "PANELS" in a narrow
        // column is still "PANELS".
        if (opts.shrink && opts.maxWidth) {
            while (size > 14 && ctx.measureText(t).width > opts.maxWidth) {
                size -= 1;
                ctx.font = this._bFont(size, opts.weight);
            }
        }
        if (opts.maxWidth) t = this._bFit(ctx, t, opts.maxWidth);
        ctx.fillStyle = opts.color || INK;
        ctx.textAlign = opts.align || 'left';
        ctx.textBaseline = opts.baseline || 'alphabetic';
        ctx.fillText(t, x, y);
        if (book.log && book.page && book.page.painting) {
            book.log.texts.push(t);
            if (book.log.textInfo) book.log.textInfo.push({ text: t, size, weight: opts.weight || 400 });
        }
        return t;
    }

    _bFit(ctx, text, maxWidth) {
        if (ctx.measureText(text).width <= maxWidth) return text;
        let t = text;
        while (t.length > 1 && ctx.measureText(t + '…').width > maxWidth) t = t.slice(0, -1);
        return t + '…';
    }

    _bType(type) {
        const t = String(type || '');
        return BINDER_TYPE_WORDS[t] || t;
    }

    _bNum(n, digits) {
        const v = Number(n);
        if (!Number.isFinite(v)) return '—';
        return digits === 0 ? Math.round(v).toLocaleString('en-US') : v.toFixed(digits);
    }

    _bPlural(n, word) {
        return `${n} ${word}${n === 1 ? '' : 's'}`;
    }

    // ---- tables: lines and the column filler --------------------------------

    // A table as a list of LINES - a title, a heading, then bands and rows -
    // each knowing its height and how to draw itself at (x, y, w). The
    // filler below lays lines into columns and repeats the head lines when a
    // table continues in the next column or on the next page.
    //   spec = { title, cols: [{ title, w, align, tick }], rows: [
    //             { band: 'text' } | { cells: [...], bold? } ] }
    _bTableLines(book, spec) {
        const cols = spec.cols || [];
        const fr = cols.reduce((s, c) => s + (c.w || 1), 0);
        const layout = (w) => {
            let x = 0;
            return cols.map(c => {
                const cw = (c.w || 1) / fr * w;
                const out = { x, w: cw, align: c.align || 'left', tick: !!c.tick };
                x += cw;
                return out;
            });
        };
        const padX = 12;
        const lines = [];
        if (spec.title) {
            lines.push({ h: H4_H, head: true, draw: (ctx, x, y, w, cont) => {
                this._bText(book, spec.title + (cont ? ' (cont.)' : ''), x, y + 30,
                            { size: SZ.h4, weight: 700, upper: true, maxWidth: w });
                ctx.fillStyle = RULE;
                ctx.fillRect(x, y + H4_H - 6, w, 2);
            } });
        }
        lines.push({ h: TH_H, head: true, draw: (ctx, x, y, w) => {
            const L = layout(w);
            cols.forEach((c, i) => {
                if (c.tick) return;
                const ax = L[i].align === 'right' ? x + L[i].x + L[i].w - padX : x + L[i].x + padX;
                this._bText(book, c.title || '', ax, y + 28,
                            { size: SZ.th, weight: 700, upper: true, align: L[i].align,
                              maxWidth: L[i].w - padX * 2, shrink: true });
            });
            ctx.fillStyle = RULE;
            ctx.fillRect(x, y + TH_H - 4, w, 4);
        } });
        for (const r of spec.rows || []) {
            if (r.band !== undefined) {
                lines.push({ h: BAND_H, band: true, draw: (ctx, x, y, w, cont) => {
                    if (book.meta.palette === 'printer') {
                        ctx.fillStyle = INK;
                        ctx.fillRect(x, y + 2, w, 3);
                    } else {
                        ctx.fillStyle = BAND_BG;
                        ctx.fillRect(x, y, w, BAND_H - 4);
                    }
                    this._bText(book, r.band + (cont ? ' (cont.)' : ''), x + padX, y + 31,
                                { size: SZ.cell, weight: 700, maxWidth: w - padX * 2 });
                    ctx.fillStyle = RULE;
                    ctx.fillRect(x, y + BAND_H - 4, w, 4);
                } });
                continue;
            }
            lines.push({ h: ROW_H, draw: (ctx, x, y, w) => {
                const L = layout(w);
                if (r.bold) { ctx.fillStyle = RULE; ctx.fillRect(x, y, w, 3); }
                (r.cells || []).forEach((cell, i) => {
                    if (!L[i]) return;
                    if (L[i].tick) {
                        ctx.strokeStyle = INK;
                        ctx.lineWidth = 2;
                        ctx.strokeRect(x + L[i].x + padX, y + 7, 24, 24);
                        return;
                    }
                    const ax = L[i].align === 'right' ? x + L[i].x + L[i].w - padX : x + L[i].x + padX;
                    // A table that carries whole names in its cells (the
                    // data page's PRIMARY / BACKUP) shrinks a long one a
                    // little before it is cut, the way a heading does.
                    this._bText(book, cell, ax, y + 27,
                                { size: SZ.cell, weight: r.bold ? 700 : 400, align: L[i].align,
                                  maxWidth: L[i].w - padX * 2, shrink: !!spec.shrink });
                });
                if (!r.bold) { ctx.fillStyle = FAINT; ctx.fillRect(x, y + ROW_H - 2, w, 2); }
            } });
        }
        return lines;
    }

    // A key/value block (the Facts) as lines.
    _bKvLines(book, title, pairs) {
        const lines = [];
        lines.push({ h: H4_H, head: true, draw: (ctx, x, y, w, cont) => {
            this._bText(book, title + (cont ? ' (cont.)' : ''), x, y + 30,
                        { size: SZ.h4, weight: 700, upper: true, maxWidth: w });
            ctx.fillStyle = RULE;
            ctx.fillRect(x, y + H4_H - 6, w, 2);
        } });
        const keyW = 150;
        for (const [k, v] of pairs) {
            // Values wrap onto as many lines as they need.
            const words = String(v == null ? '' : v).split(' ');
            const ctxM = book.measureCtx;
            ctxM.font = this._bFont(SZ.cell, 400);
            const rowsOf = (w) => {
                const maxW = w - keyW - 8;
                const out = [];
                let cur = '';
                for (const word of words) {
                    const test = cur ? cur + ' ' + word : word;
                    if (cur && ctxM.measureText(test).width > maxW) { out.push(cur); cur = word; }
                    else cur = test;
                }
                if (cur) out.push(cur);
                return out.length ? out : [''];
            };
            // Height is measured against the widest column the block can
            // land in; a narrower one wraps a little tighter and clips
            // nothing - the row keeps its measured height.
            const n = rowsOf(600).length;
            lines.push({ h: ROW_H * n, draw: (ctx, x, y, w) => {
                this._bText(book, k, x, y + 27, { size: SZ.cell, weight: 700 });
                rowsOf(w).forEach((t, i) => {
                    this._bText(book, t, x + keyW, y + 27 + i * ROW_H, { size: SZ.cell, maxWidth: w - keyW });
                });
            } });
        }
        return lines;
    }

    // Column geometry across the page for the given fractions.
    _bCols(fractions, gap) {
        const g = gap == null ? 25 : gap;
        const total = PAGE_W - PAD * 2 - g * (fractions.length - 1);
        const fr = fractions.reduce((s, f) => s + f, 0);
        let x = PAD;
        return fractions.map(f => {
            const w = f / fr * total;
            const c = { x, w };
            x += w + g;
            return c;
        });
    }

    // THE FILLER. Blocks in order; a block starts a fresh column when one is
    // free and stacks under the previous block when none is (so Circuits |
    // Cables | Facts+Gangs on a short screen, Circuits | Circuits |
    // Cables+Facts+Gangs on a long one); a column that fills continues in
    // the next, and the last column of a page continues on a continuation
    // page (`onNewPage` returns its top/bottom/cols), repeating the block's
    // head lines wherever it resumes.
    //
    // The band rule (2026-09-07, "the page gets cut off"): a band is laid
    // only where it and its first two rows (or its one row, when it has
    // one) fit above the foot; otherwise it moves to the next column with
    // its rows. Rows that run on past a break get their band again, with
    // "(cont.)", under the repeated head lines.
    _bFlow(book, blocks, frame, onNewPage) {
        let { top, bottom, cols } = frame;
        let ci = 0;
        let y = top;
        let used = false;
        const ctxOf = () => book.ctx;
        for (const block of blocks) {
            const lines = block.lines || [];
            if (!lines.length) continue;
            const heads = lines.filter(l => l.head);
            if (used && ci < cols.length - 1) { ci++; y = top; used = false; }
            else if (used) { y += BLOCK_GAP; }
            let i = 0;
            let guard = 0;
            let band = null;              // the band the rows being laid sit under
            while (i < lines.length) {
                const l = lines[i];
                let need = l.h;
                if (l.band) {
                    for (let k = i + 1, n = 0; k < lines.length && n < 2; k++, n++) {
                        if (lines[k].band || lines[k].head) break;
                        need += lines[k].h;
                    }
                }
                if (y + need > bottom && (used || y !== top)) {
                    if (ci < cols.length - 1) { ci++; }
                    else {
                        const f = onNewPage();
                        top = f.top; bottom = f.bottom; cols = f.cols; ci = 0;
                    }
                    y = top; used = false;
                    if (!l.head) {
                        for (const h of heads) { h.draw(ctxOf(), cols[ci].x, y, cols[ci].w, true); y += h.h; }
                        if (band && !l.band) { band.draw(ctxOf(), cols[ci].x, y, cols[ci].w, true); y += band.h; }
                    }
                    if (++guard > 500) break;
                    continue;
                }
                l.draw(ctxOf(), cols[ci].x, y, cols[ci].w, false);
                y += l.h;
                used = true;
                i++;
                if (l.band) band = l;
            }
        }
    }

    // A continuation page for a flow: same header, "(cont.)" on the subject,
    // three full-height columns.
    _bContinuation(book, kind, title, header, extra) {
        return () => {
            this._bNewPage(book, kind, `${title} (cont.)`,
                           { left: header.left, right: `${header.right} (cont.)` }, extra);
            return { top: HEADER_BOTTOM + 8, bottom: FOOTER_TOP,
                     cols: this._bCols([1.15, 1, 0.9]) };
        };
    }

    // ---- the map ------------------------------------------------------------

    // The screen's map through the canvas renderer, in exportMode, in the
    // binder's palette, with the screen-name plate off (the header names
    // the screen; the plate sat over the circuit labels), onto an offscreen
    // canvas that is then laid into the page's map area. Returns the page
    // geometry - where a processor-coord rect of this layer lands on the
    // page - so the rulers and the breakout brackets can be drawn around it
    // in page space.
    _bMap(book, layer, view, area) {
        const r = window.canvasRenderer;
        const canvases = (this.project && Array.isArray(this.project.canvases)) ? this.project.canvases : [];
        const saved = {
            canvas: r.canvas, ctx: r.ctx, exportMode: r.exportMode, transparent: r.exportTransparentBg,
            printer: r.printerMode, viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
            hideNames: r.hideScreenNames,
            active: this.project ? this.project.active_canvas_id : null,
            canvasVis: canvases.map(c => [c, c.visible]),
            layerVis: (this.project.layers || []).map(l => [l, l.visible]),
        };
        const inner = {
            x: area.x + MAP_GUTTER.left, y: area.y + MAP_GUTTER.top,
            w: area.w - MAP_GUTTER.left - MAP_GUTTER.right,
            h: area.h - MAP_GUTTER.top - MAP_GUTTER.bottom,
        };
        let geo = null;
        try {
            r.viewMode = view;
            const cid = (layer.show_canvas_id || layer.canvas_id) || null;
            const canvas = canvases.find(c => c && c.id === cid) || null;
            canvases.forEach(c => { c.visible = (canvas ? c.id === canvas.id : true); });
            if (canvas && this.project) this.project.active_canvas_id = canvas.id;
            (this.project.layers || []).forEach(l => { if (l !== layer) l.visible = false; });
            layer.visible = true;
            const b = r.getLayerBounds(layer);
            const { dx, dy } = r.getLayerRenderOffset(layer);
            const ws = r._canvasWorkspace(canvas);
            const mirrored = !!(canvas && r._isCanvasMirrored(canvas));
            const crw = canvas ? ((canvas.show_raster_width) || canvas.raster_width || 0) : 0;
            // A processor-coord rect of this layer, in the canvas's drawn
            // frame (mirrored around the raster's right edge on a Back view).
            const local = (px, py, pw, ph) => ({
                x: mirrored ? crw - (px + dx + pw) : px + dx, y: py + dy, w: pw, h: ph,
            });
            const wall = local(b.x, b.y, b.width, b.height);
            const zoom = Math.min(inner.w / Math.max(1, wall.w), inner.h / Math.max(1, wall.h), 3);
            const drawW = wall.w * zoom, drawH = wall.h * zoom;
            const ox = inner.x + (inner.w - drawW) / 2;      // wall's page origin
            const oy = inner.y + (inner.h - drawH) / 2;
            const toPage = (lx, ly) => ({ x: ox + (lx - wall.x) * zoom, y: oy + (ly - wall.y) * zoom });
            geo = {
                zoom, wall: { x: ox, y: oy, w: drawW, h: drawH }, mirrored,
                rect: (px, py, pw, ph) => {
                    const l = local(px, py, pw, ph);
                    const p = toPage(l.x, l.y);
                    return { x: p.x, y: p.y, w: l.w * zoom, h: l.h * zoom };
                },
            };
            if (book.page && book.page.painting) {
                const off = this._binderMapCanvas || (this._binderMapCanvas = document.createElement('canvas'));
                off.width = Math.max(1, Math.round(area.w));
                off.height = Math.max(1, Math.round(area.h));
                const offCtx = off.getContext('2d', { alpha: true });
                if (book.log) {
                    const oT = offCtx.fillText.bind(offCtx), oD = offCtx.setLineDash.bind(offCtx);
                    offCtx.fillText = (t, x, y, w) => { book.log.mapTexts.push(String(t)); return oT(t, x, y, w); };
                    offCtx.setLineDash = (d) => { book.log.dashes.push(Array.from(d || [])); return oD(d); };
                }
                r.canvas = off;
                r.ctx = offCtx;
                r.exportMode = true;
                r.exportTransparentBg = true;
                r.hideScreenNames = true;
                r.printerMode = book.meta.palette === 'printer';
                r.zoom = zoom;
                // The wall's local origin lands at (ox - area.x, oy - area.y)
                // on the offscreen canvas.
                r.panX = (ox - area.x) - (ws.wx + wall.x) * zoom;
                r.panY = (oy - area.y) - (ws.wy + wall.y) * zoom;
                r.render();
                book.ctx.drawImage(off, area.x, area.y);
            }
        } finally {
            saved.canvasVis.forEach(([c, v]) => { c.visible = v; });
            saved.layerVis.forEach(([l, v]) => { l.visible = v; });
            if (this.project) this.project.active_canvas_id = saved.active;
            r.canvas = saved.canvas;
            r.ctx = saved.ctx;
            r.exportMode = saved.exportMode;
            r.exportTransparentBg = saved.transparent;
            r.hideScreenNames = saved.hideNames;
            r.printerMode = saved.printer;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom;
            r.panX = saved.panX;
            r.panY = saved.panY;
        }
        return geo;
    }

    // The rulers (numbering "2"): every column ticked above the wall, every
    // fifth and the two ends numbered bold; every row numbered bold down
    // the left. Positions come from the cabinets themselves, so a half
    // tile or a rotated member is numbered where it draws.
    _bRulers(book, layer, geo) {
        const ctx = book.ctx;
        const panels = (layer.panels || []).filter(p => p && !p.hidden);
        if (!panels.length) return;
        const cols = new Map(), rows = new Map();
        for (const p of panels) {
            const rc = geo.rect(p.x, p.y, p.width, p.height);
            const c = cols.get(p.col);
            if (!c) cols.set(p.col, { x1: rc.x, x2: rc.x + rc.w });
            else { c.x1 = Math.min(c.x1, rc.x); c.x2 = Math.max(c.x2, rc.x + rc.w); }
            const rr = rows.get(p.row);
            if (!rr) rows.set(p.row, { y1: rc.y, y2: rc.y + rc.h });
            else { rr.y1 = Math.min(rr.y1, rc.y); rr.y2 = Math.max(rr.y2, rc.y + rc.h); }
        }
        const colKeys = [...cols.keys()].sort((a, b) => a - b);
        const rowKeys = [...rows.keys()].sort((a, b) => a - b);
        const top = geo.wall.y;
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        colKeys.forEach((k, i) => {
            const c = cols.get(k);
            const cx = (c.x1 + c.x2) / 2;
            const bold = (k + 1) % 5 === 0 || i === 0 || i === colKeys.length - 1;
            ctx.beginPath();
            ctx.moveTo(cx, top - 6);
            ctx.lineTo(cx, top - (bold ? 22 : 14));
            ctx.stroke();
            if (bold) {
                this._bText(book, String(k + 1), cx, top - 30,
                            { size: SZ.ruler, weight: 700, align: 'center' });
            }
        });
        // A thin baseline over the wall ties the ticks together.
        ctx.beginPath();
        ctx.moveTo(geo.wall.x, top - 6);
        ctx.lineTo(geo.wall.x + geo.wall.w, top - 6);
        ctx.stroke();
        const left = geo.wall.x;
        rowKeys.forEach(k => {
            const rr = rows.get(k);
            const cy = (rr.y1 + rr.y2) / 2;
            ctx.beginPath();
            ctx.moveTo(left - 6, cy);
            ctx.lineTo(left - 14, cy);
            ctx.stroke();
            this._bText(book, String(k + 1), left - 20, cy + 8,
                        { size: SZ.ruler, weight: 700, align: 'right' });
        });
        // The wall's own outline, so the map reads as one thing on paper.
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2;
        ctx.strokeRect(geo.wall.x, geo.wall.y, geo.wall.w, geo.wall.h);
    }

    // The breakout brackets outside the wall: one per breakout, spanning
    // the rows its circuits feed, on the side its circuits live, labelled
    // "SR 1 · 125'".
    // Brackets that overlap on a side stack outward.
    _bBoxBrackets(book, layer, scr, geo) {
        const ctx = book.ctx;
        const circuits = (typeof this.screenCircuits === 'function') ? this.screenCircuits(layer) : [];
        const byNum = new Map(circuits.map(c => [c.num, c]));
        const own = (c) => (c.layers
            ? c.panels.filter((p, i) => !c.layers[i] || c.layers[i] === layer || c.layers[i].id === layer.id)
            : c.panels).filter(p => p && !p.hidden);
        const wallCx = geo.wall.x + geo.wall.w / 2;
        const placed = { L: [], R: [] };
        for (const box of scr.boxes || []) {
            let x1 = Infinity, x2 = -Infinity, y1 = Infinity, y2 = -Infinity;
            for (const c of box.circuits || []) {
                const circuit = byNum.get(c.num);
                if (!circuit) continue;
                for (const p of own(circuit)) {
                    const rc = geo.rect(p.x, p.y, p.width, p.height);
                    x1 = Math.min(x1, rc.x); x2 = Math.max(x2, rc.x + rc.w);
                    y1 = Math.min(y1, rc.y); y2 = Math.max(y2, rc.y + rc.h);
                }
            }
            if (!Number.isFinite(x1) || !Number.isFinite(y1)) continue;
            const side = (x1 + x2) / 2 >= wallCx ? 'R' : 'L';
            const stack = placed[side];
            const depth = stack.filter(([a, b]) => !(y2 + 4 < a || y1 - 4 > b)).length;
            stack.push([y1, y2]);
            const dir = side === 'R' ? 1 : -1;
            const x = side === 'R'
                ? geo.wall.x + geo.wall.w + 44 + depth * 78
                : geo.wall.x - 74 - depth * 78;
            const ya = y1 + 3, yb = y2 - 3;
            ctx.strokeStyle = INK;
            ctx.lineWidth = 3;
            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.moveTo(x - dir * 14, ya);
            ctx.lineTo(x, ya);
            ctx.lineTo(x, yb);
            ctx.lineTo(x - dir * 14, yb);
            ctx.stroke();
            const label = box.homeRun
                ? `${box.name} · ${this.pullLengthText(box.homeRun)}` : `${box.name}`;
            ctx.save();
            ctx.translate(x + dir * 24, (ya + yb) / 2);
            ctx.rotate(dir > 0 ? Math.PI / 2 : -Math.PI / 2);
            this._bText(book, label, 0, 9, { size: SZ.bracket, weight: 700, align: 'center',
                                              maxWidth: Math.max(80, yb - ya) });
            ctx.restore();
        }
    }

    // ---- the screen page ----------------------------------------------------

    _bScreenPage(book, layer, pos, view) {
        const scr = book.list.byScreen[layer.id];
        const word = view === 'power' ? 'POWER' : 'DATA';
        const header = { left: `${book.meta.show} · ${word}`,
                         right: pos.name === layer.name ? layer.name : `${layer.name} · ${pos.name}` };
        const title = `${layer.name} - ${view === 'power' ? 'Power' : 'Data'}`;
        const extra = { layerId: layer.id, subject: layer.name, footer: `${word[0]}${word.slice(1).toLowerCase()} · ${layer.name}` };
        this._bNewPage(book, view, title, header, extra);
        const area = { x: PAD, y: HEADER_BOTTOM, w: PAGE_W - PAD * 2, h: MAP_H };
        const geo = this._bMap(book, layer, view === 'power' ? 'power' : 'data-flow', area);
        if (geo && book.page.painting) {
            this._bRulers(book, layer, geo);
            if (view === 'power') this._bBoxBrackets(book, layer, scr, geo);
        }
        const blocks = view === 'power'
            ? this._bPowerBlocks(book, layer, scr)
            : this._bDataBlocks(book, layer, scr);
        const frame = { top: area.y + area.h + 8, bottom: FOOTER_TOP, cols: this._bCols([1.15, 1, 0.9]) };
        this._bFlow(book, blocks, frame, this._bContinuation(book, view, title, header, extra));
    }

    // The band over a breakout's circuits: "SR 1 · Soca 208 · 125' home run
    // · 6 circuits", plus the tails on it that belong to another screen.
    _bBoxBand(book, layer, box) {
        const n = (box.circuits || []).length;
        const parts = [box.name, box.type || 'no distro',
                       box.homeRun ? `${this.pullLengthText(box.homeRun)} home run` : 'no home run',
                       this._bPlural(n, 'circuit')];
        for (const [id, other] of Object.entries(book.list.byScreen)) {
            if (String(id) === String(layer.id)) continue;
            for (const ob of other.boxes || []) {
                if (ob.key !== box.key || !box.distroId) continue;
                const legs = (ob.circuits || []).map(c => c.tail);
                if (!legs.length) continue;
                parts.push(`tail ${this._fmtTails(legs)} · ${other.name}`);
            }
        }
        return parts.join(' · ');
    }

    _bScreenFacts(layer) {
        const active = (layer.panels || []).filter(p => p && !p.blank && !p.hidden);
        const equivalent = active.reduce((s, p) => s + (typeof this.getPanelLoadFactor === 'function'
            ? this.getPanelLoadFactor(layer, p) : 1), 0);
        const bounds = window.canvasRenderer ? window.canvasRenderer.getLayerBounds(layer)
            : { width: 0, height: 0 };
        const watts = (parseFloat(layer.panelWatts) || 0) * equivalent;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        return {
            active: active.length, equivalent, watts, voltage,
            amps1: voltage > 0 ? watts / voltage : 0,
            amps3: voltage > 0 ? watts / (voltage * 1.73) : 0,
            pixels: active.reduce((s, p) => s + this.getPanelPixelArea(p), 0),
            width: bounds.width, height: bounds.height,
            screenText: `${layer.columns} × ${layer.rows} · ${this._bPlural(active.length, 'panel')}`
                + ` · ${layer.cabinet_width}×${layer.cabinet_height} px`,
        };
    }

    _bPowerBlocks(book, layer, scr) {
        const blocks = [];
        // Circuits, banded per breakout.
        const rows = [];
        for (const box of scr.boxes || []) {
            rows.push({ band: this._bBoxBand(book, layer, box) });
            for (const c of box.circuits || []) {
                rows.push({ cells: [c.label, String(c.tail), this._bNum(c.tiles, 0),
                                    this._bNum(c.amps, 1), c.cable || '—'] });
            }
        }
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Circuits',
            cols: [{ title: 'circuit', w: 1.5 }, { title: 'tail', w: 0.6, align: 'right' },
                   { title: 'panels', w: 0.8, align: 'right' }, { title: 'amps', w: 0.8, align: 'right' },
                   { title: 'cable', w: 1.4 }],
            rows,
        }) });
        // Cables this screen (power side).
        const cables = (scr.rows || []).filter(r => (r.side || 'power') === 'power');
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Cables this screen',
            cols: [{ title: 'cable', w: 1.7 }, { title: 'len', w: 0.7 }, { title: 'qty', w: 0.6, align: 'right' }],
            rows: cables.length ? cables.map(r => ({ cells: [this._bType(r.type), r.length || '—', String(r.qty)] }))
                : [{ cells: ['no cables typed', '', ''] }],
        }) });
        // Facts.
        const f = this._bScreenFacts(layer);
        const circuits = (scr.boxes || []).flatMap(b => b.circuits || []);
        const tiles = circuits.map(c => Number(c.tiles) || 0);
        const tMin = tiles.length ? Math.min(...tiles) : 0, tMax = tiles.length ? Math.max(...tiles) : 0;
        const each = tiles.length ? (tMin === tMax ? `${tMin} panels each` : `${tMin}–${tMax} panels each`) : '';
        const distroIds = [...new Set((scr.boxes || []).map(b => b.distroId).filter(Boolean))];
        const loads = (typeof this.getDistroLoads === 'function') ? this.getDistroLoads() : [];
        const fed = distroIds.map(id => {
            const d = loads.find(x => x.id === id);
            if (!d) return null;
            let s = `${d.name} · ${d.ratingA} A ${d.voltage} V ${d.phase === 3 ? '3φ' : '1φ'}`;
            if (d.legs) {
                s += ` · legs X ${this._bNum(d.legs.X.amps, 1)} Y ${this._bNum(d.legs.Y.amps, 1)}`
                    + ` Z ${this._bNum(d.legs.Z.amps, 1)} A`;
            }
            return s;
        }).filter(Boolean);
        blocks.push({ lines: this._bKvLines(book, 'Facts', [
            ['Screen', f.screenText],
            ['Load', `${this._bNum(f.amps1, 1)} A 1φ · ${this._bNum(f.amps3, 1)} A 3φ · ${this._bNum(f.watts / 1000, 1)} kW`],
            ['Circuits', [`${circuits.length} at ${f.voltage} V / ${parseFloat(layer.powerAmperage) || 0} A`, each]
                .filter(Boolean).join(' · ')],
            ['Fed by', fed.length ? fed.join(' · ') : 'no distro'],
        ]) });
        // Gangs, only when the screen has any.
        const gangs = scr.gangs || { twofer: 0, threefer: 0 };
        if ((gangs.twofer || 0) + (gangs.threefer || 0) > 0 && typeof this.screenCircuits === 'function') {
            const amps = new Map(circuits.map(c => [c.num, c.amps]));
            const shared = this.screenCircuits(layer).filter(c => Array.isArray(c.runIds) && c.runIds.length > 1);
            blocks.push({ lines: this._bTableLines(book, {
                title: 'Gangs',
                cols: [{ title: 'circuit', w: 1.3 }, { title: 'gang', w: 0.8 }, { title: 'amps', w: 0.8, align: 'right' }],
                rows: shared.map(c => ({ cells: [this.getPowerCircuitLabel(layer, c.num),
                                                 `${c.runIds.length}fer`, this._bNum(amps.get(c.num), 1)] })),
            }) });
        }
        return blocks;
    }

    // The return end of a port, as the tray states it: the backup port's
    // label ("SR-1R") and where it lands - the breakout box's title where
    // one delivers it, else the backup card's name (or its slot on its
    // processor) - and the socket, "SR-1R · H9 BACKUP · 1".
    _bBackupText(layer, portNum, bb) {
        const label = (typeof this.getPortLabelText === 'function')
            ? this.getPortLabelText(layer, portNum, 'return') : '';
        const home = this._bPortHome(bb.cardId, bb.port);
        let where = home && home.box ? this._bBoxTitle(home.box) : (bb.boxTitle || '');
        if (!where) {
            where = home ? `${home.procTitle} ${home.cardTitle}` : (bb.cardTitle || this._bCardShort(bb.cardId));
        }
        const socket = bb.localPort != null ? bb.localPort : bb.port;
        return [label, `${where} · ${socket}`].filter(Boolean).join(' · ');
    }

    // What a page calls a breakout box: "CVT4K-S SR" - the model and the
    // name typed on it, the way a card reads "H9 SR"; unnamed, the title
    // the dock wears ("CVT4K-S A"). One implementation, the pull list's.
    _bBoxTitle(box) {
        return (typeof this.pullBoxTitle === 'function')
            ? this.pullBoxTitle(box) : (box.displayTitle || box.name || box.deviceName);
    }

    // The band over a box's ports: "CVT4K-S SR · OPT 1-2 · 16 ports · 12
    // Tac Fiber 250'" - the trunk it hangs on as the card's face prints
    // it, the sockets it delivers, and its fiber trunk (or that it has no
    // length yet).
    _bBoxBandText(box) {
        const fiber = (typeof this.pullBoxFiberText === 'function') ? this.pullBoxFiberText(box) : '';
        return [this._bBoxTitle(box), box.trunkTitle || '',
                this._bPlural(box.portCount || (box.ports || []).length, 'port'),
                fiber || 'no fiber length'].filter(Boolean).join(' · ');
    }

    // The redundancy bar's reading for a processor: "Per card", "Per port",
    // "Whole unit → H9 BACKUP" (the partner the unit mirrors onto), "Off".
    _bRedundancyText(proc) {
        const level = (typeof this._procRedundancyLevel === 'function') ? this._procRedundancyLevel(proc) : 'off';
        let text = REDUNDANCY_WORDS[level] || level;
        if (level === 'unit') {
            const procs = this._processorsResolved || [];
            const partner = procs.find(p => p.id === proc.backupProcessorId);
            if (partner) text += ` → ${partner.name || partner.deviceName}`;
            else {
                const one = (proc.slots || []).map(s => s.card).find(Boolean);
                const found = one && one.backupCardId && typeof this._otherCards === 'function'
                    ? this._otherCards(one.id).find(x => x.card.id === one.backupCardId) : null;
                if (found && typeof this._backupUnitTitle === 'function') {
                    text += ` → ${this._backupUnitTitle(found.proc, found.card)}`;
                }
            }
        }
        return text;
    }

    // The processor and card a socket sits on, for the data page's bands.
    _bPortHome(cardId, socket) {
        const found = (typeof this._dockFindCard === 'function') ? this._dockFindCard(cardId) : null;
        if (!found) return null;
        const { proc, card } = found;
        const procTitle = proc.name || proc.deviceName || proc.id;
        const slot = (proc.slots || []).find(s => s.card && s.card.id === card.id);
        const cardTitle = card.name || (slot ? `slot ${(slot.index || 0) + 1}` : card.deviceName);
        const n = parseInt(socket, 10);
        const box = (card.cvts || []).find(c => (c.ports || []).some(p => p.number === n)) || null;
        const port = (card.ports || []).find(p => p.number === n) || null;
        return { proc, card, procTitle, cardTitle, box, port };
    }

    // A card by id as a page names it: the name somebody typed, else its
    // slot on its processor - never the device's long model string.
    _bCardShort(cardId) {
        const found = (typeof this._dockFindCard === 'function') ? this._dockFindCard(cardId) : null;
        if (!found) return cardId || '—';
        if (found.card.name) return found.card.name;
        const slot = (found.proc.slots || []).find(s => s.card && s.card.id === found.card.id);
        return slot ? `slot ${(slot.index || 0) + 1}` : found.card.deviceName;
    }

    _bDataBlocks(book, layer, scr) {
        const blocks = [];
        const asg = ((this._assignment && this._assignment.screens) || [])
            .find(s => String(s.layerId) === String(layer.id));
        const runs = this._pullPortRuns(layer);
        const bands = new Map();      // key -> { text, rows }
        const band = (key, text) => {
            let b = bands.get(key);
            if (!b) { b = { text, rows: [] }; bands.set(key, b); }
            return b;
        };
        let procs = new Map();
        for (const run of runs) {
            const placed = asg && (asg.ports || []).find(p => p.number === run.num);
            const home = placed && placed.cardId ? this._bPortHome(placed.cardId, placed.port) : null;
            const cable = (typeof this.dataPortCableForScreen === 'function')
                ? this.dataPortCableForScreen(layer, run.num) : null;
            const px = (run.panels || []).reduce((s, p) => s + this.getPanelPixelArea(p), 0);
            // PRIMARY is where the port lands - the sending card ("H9 SR ·
            // 1") or, where a breakout box delivers it, the BOX instead
            // ("CVT4K-S SR · 3", its own silkscreen number); BACKUP is the
            // return end the same way (2026-09-07: "list the sending card
            // order on primary and backup … if cvt's are used then we will
            // list those instead of sending card").
            let primary = '—', backup = '—', b;
            if (home) {
                procs.set(home.proc.id, home.proc);
                const socket = String(home.port && home.port.localNumber != null ? home.port.localNumber : placed.port);
                if (home.box) {
                    b = band(`box:${home.box.id}`, this._bBoxBandText(home.box));
                    primary = `${this._bBoxTitle(home.box)} · ${socket}`;
                } else {
                    b = band(`card:${home.card.id}`,
                             `${home.procTitle} ${home.cardTitle} · ${home.card.deviceName}`
                             + ` · ${this._bPlural(home.card.ceiling || (home.card.ports || []).length, 'port')}`);
                    primary = `${home.procTitle} ${home.cardTitle} · ${socket}`;
                }
                const bb = home.port && home.port.backedBy;
                if (bb) backup = this._bBackupText(layer, run.num, bb);
            } else {
                b = band('none', 'Not placed');
            }
            b.rows.push({ cells: [run.label, primary, backup, this._bNum((run.panels || []).length, 0),
                                  this._bNum(px, 0), cable && cable.text ? cable.text : '—'] });
        }
        const rows = [];
        for (const b of bands.values()) { rows.push({ band: b.text }); rows.push(...b.rows); }
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Ports',
            // PRIMARY and BACKUP carry whole names - "SR-1R · H9 BACKUP SR ·
            // 1" - so they take most of the width and shrink before they cut.
            cols: [{ title: 'port', w: 0.7 }, { title: 'primary', w: 1.7 }, { title: 'backup', w: 2.25 },
                   { title: 'panels', w: 0.8, align: 'right' }, { title: 'px', w: 1.0, align: 'right' },
                   { title: 'home run', w: 1.05 }],
            rows,
            shrink: true,
        }) });
        const cables = (scr.rows || []).filter(r => r.side === 'data');
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Cables this screen',
            cols: [{ title: 'cable', w: 1.7 }, { title: 'len', w: 0.7 }, { title: 'qty', w: 0.6, align: 'right' }],
            rows: cables.length ? cables.map(r => ({ cells: [this._bType(r.type), r.length || '—', String(r.qty)] }))
                : [{ cells: ['no cables typed', '', ''] }],
        }) });
        const f = this._bScreenFacts(layer);
        // The port count alone - "we dont need port max" (2026-09-07).
        const pairs = [
            ['Screen', f.screenText],
            ['Pixels', `${f.width} × ${f.height} · ${this._bNum(f.pixels, 0)} px`],
            ['Ports', this._bPlural(runs.length, 'port')],
        ];
        for (const proc of procs.values()) {
            const procName = proc.name || proc.deviceName || proc.id;
            pairs.push(['Processor', procName === proc.deviceName || !proc.deviceName
                ? procName : `${procName} · ${proc.deviceName}`]);
            pairs.push(['Redundancy', this._bRedundancyText(proc)]);
        }
        if (!procs.size) pairs.push(['Processor', 'not placed']);
        blocks.push({ lines: this._bKvLines(book, 'Facts', pairs) });
        return blocks;
    }

    // ---- the cover ----------------------------------------------------------

    _bCoverPage(book) {
        const page = this._bNewPage(book, 'cover', 'Cover', null, { subject: book.meta.show, footer: 'Cover' });
        const ctx = book.ctx;
        this._bText(book, book.meta.show, PAD, 300, { size: SZ.title, weight: 800, maxWidth: PAGE_W - PAD * 2 });
        this._bText(book, 'POWER · DATA BINDER', PAD, 360, { size: SZ.sub, weight: 600, color: RULE });
        ctx.fillStyle = INK;
        ctx.fillRect(PAD, 390, PAGE_W - PAD * 2, 6);
        const metaLines = [`Date ${book.meta.date}`, `Rev ${book.meta.rev}`];
        if (book.meta.engineer) metaLines.push(`Engineer ${book.meta.engineer}`);
        metaLines.push(`Palette ${book.meta.palette === 'printer' ? 'Printer' : 'Colour'}`);
        metaLines.forEach((t, i) => this._bText(book, t, PAD, 450 + i * 42, { size: SZ.meta }));
        // Positions and their screens.
        const list = book.list;
        const rows = list.positions.map(pos => {
            const members = pos.layerIds.map(id => book.layers.get(String(id))).filter(Boolean);
            const scrs = pos.layerIds.map(id => list.byScreen[id]).filter(Boolean);
            const circuits = scrs.reduce((s, x) => s + (x.boxes || []).reduce((a, b) => a + (b.circuits || []).length, 0), 0);
            const ports = scrs.reduce((s, x) => s + (x.ports || []).length, 0);
            return { cells: [pos.name, members.map(l => l.name).join(', '), String(circuits), String(ports)] };
        });
        const cols = this._bCols([1, 1], 60);
        const lines = this._bTableLines(book, {
            title: 'Positions',
            cols: [{ title: 'position', w: 1 }, { title: 'screens', w: 1.6 },
                   { title: 'circuits', w: 0.6, align: 'right' }, { title: 'ports', w: 0.5, align: 'right' }],
            rows,
        });
        this._bFlow(book, [{ lines }], { top: 640, bottom: FOOTER_TOP, cols: [cols[0]] },
                    this._bContinuation(book, 'cover', 'Positions',
                                        { left: book.meta.show, right: 'Positions' }, { footer: 'Positions' }));
        // The whole raster, small, on the right.
        const thumb = { x: cols[1].x, y: 450, w: cols[1].w, h: FOOTER_TOP - 470 };
        if (page.painting) this._bThumbnail(book, thumb);
    }

    // The show at a glance: every visible canvas's pixel map, fitted into
    // the box, through the renderer in exportMode.
    _bThumbnail(book, box) {
        const r = window.canvasRenderer;
        const canvases = (this.project && Array.isArray(this.project.canvases)) ? this.project.canvases : [];
        const shown = canvases.filter(c => c && c.visible !== false);
        const saved = { canvas: r.canvas, ctx: r.ctx, exportMode: r.exportMode, transparent: r.exportTransparentBg,
                        printer: r.printerMode, viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY };
        try {
            r.viewMode = 'pixel-map';
            let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
            if (shown.length) {
                for (const c of shown) {
                    const ws = r._canvasWorkspace(c);
                    x1 = Math.min(x1, ws.wx); y1 = Math.min(y1, ws.wy);
                    x2 = Math.max(x2, ws.wx + (c.raster_width || 0)); y2 = Math.max(y2, ws.wy + (c.raster_height || 0));
                }
            } else {
                x1 = 0; y1 = 0; x2 = r.rasterWidth || 1920; y2 = r.rasterHeight || 1080;
            }
            const w = Math.max(1, x2 - x1), h = Math.max(1, y2 - y1);
            const zoom = Math.min(box.w / w, box.h / h);
            const off = this._binderMapCanvas || (this._binderMapCanvas = document.createElement('canvas'));
            off.width = Math.max(1, Math.round(w * zoom));
            off.height = Math.max(1, Math.round(h * zoom));
            r.canvas = off;
            r.ctx = off.getContext('2d', { alpha: true });
            r.exportMode = true;
            r.exportTransparentBg = true;
            r.printerMode = book.meta.palette === 'printer';
            r.zoom = zoom;
            r.panX = -x1 * zoom;
            r.panY = -y1 * zoom;
            r.render();
            const dx = box.x + (box.w - off.width) / 2, dy = box.y + (box.h - off.height) / 2;
            book.ctx.fillStyle = '#f4f4f4';
            book.ctx.fillRect(dx, dy, off.width, off.height);
            book.ctx.drawImage(off, dx, dy);
            book.ctx.strokeStyle = RULE;
            book.ctx.lineWidth = 2;
            book.ctx.strokeRect(dx, dy, off.width, off.height);
        } finally {
            r.canvas = saved.canvas; r.ctx = saved.ctx; r.exportMode = saved.exportMode;
            r.exportTransparentBg = saved.transparent; r.printerMode = saved.printer;
            r.viewMode = saved.viewMode; r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
        }
    }

    // ---- the position pull page ---------------------------------------------

    _bPullPage(book, pos, members) {
        const header = { left: `${book.meta.show} · PULL`, right: pos.name };
        const title = `${pos.name} - Pull`;
        const extra = { subject: pos.name, footer: `Pull · ${pos.name}` };
        this._bNewPage(book, 'pull', title, header, extra);
        const list = book.list;
        const tick = { title: '', w: 0.28, tick: true };
        const cableCols = [tick, { title: 'cable', w: 1.5 }, { title: 'len', w: 0.6 },
                           { title: 'qty', w: 0.5, align: 'right' }, { title: 'label', w: 1.4 }];
        const cableRows = (side) => (pos.rows || []).filter(r => (r.side || 'power') === side)
            .map(r => ({ cells: ['', this._bType(r.type), r.length || '—', String(r.qty), r.label || ''] }));
        const blocks = [];
        const power = cableRows('power');
        blocks.push({ lines: this._bTableLines(book, { title: 'Power cables', cols: cableCols,
            rows: power.length ? power : [{ cells: ['', 'none', '', '', ''] }] }) });
        const data = cableRows('data');
        blocks.push({ lines: this._bTableLines(book, { title: 'Data cables', cols: cableCols,
            rows: data.length ? data : [{ cells: ['', 'none', '', '', ''] }] }) });
        // Hardware: the breakouts, the distros, the cards these screens hang on.
        const hw = [];
        const seenBox = new Set(), seenDistro = new Set(), seenCard = new Set();
        for (const layer of members) {
            const scr = list.byScreen[layer.id];
            for (const box of (scr && scr.boxes) || []) {
                if (seenBox.has(box.key)) continue;
                seenBox.add(box.key);
                hw.push({ cells: ['', box.name, [box.type || 'no distro',
                    box.homeRun ? `${this.pullLengthText(box.homeRun)} home run` : 'no home run'].join(' · ')] });
                if (box.distroId && !seenDistro.has(box.distroId)) {
                    seenDistro.add(box.distroId);
                    const d = (this.getDistros ? this.getDistros() : []).find(x => x.id === box.distroId);
                    if (d) hw.push({ cells: ['', d.name, `distro · ${d.ratingA} A ${d.voltage} V ${d.phase === 3 ? '3φ' : '1φ'}`] });
                }
            }
            const asg = ((this._assignment && this._assignment.screens) || [])
                .find(s => String(s.layerId) === String(layer.id));
            for (const cid of (asg && asg.cardIds) || []) {
                if (seenCard.has(cid)) continue;
                seenCard.add(cid);
                const home = this._bPortHome(cid, 0);
                if (home) hw.push({ cells: ['', `${home.procTitle} ${home.cardTitle}`, home.card.deviceName] });
            }
        }
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Hardware',
            cols: [tick, { title: 'item', w: 1.2 }, { title: 'detail', w: 2 }],
            rows: hw.length ? hw : [{ cells: ['', 'none', ''] }],
        }) });
        // Screens with their gang counts.
        const screens = members.map(layer => {
            const scr = list.byScreen[layer.id] || { boxes: [], ports: [], gangs: {} };
            const circuits = (scr.boxes || []).reduce((a, b) => a + (b.circuits || []).length, 0);
            const g = scr.gangs || {};
            const gangs = [g.twofer ? `${g.twofer}× 2fer` : '', g.threefer ? `${g.threefer}× 3fer` : '']
                .filter(Boolean).join(', ') || '—';
            const panels = (layer.panels || []).filter(p => p && !p.blank && !p.hidden).length;
            return { cells: ['', layer.name, `${layer.columns} × ${layer.rows}`, String(panels),
                             String(circuits), String((scr.ports || []).length), gangs] };
        });
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Screens',
            cols: [tick, { title: 'screen', w: 1.3 }, { title: 'size', w: 0.7 },
                   { title: 'panels', w: 0.6, align: 'right' }, { title: 'circuits', w: 0.6, align: 'right' },
                   { title: 'ports', w: 0.5, align: 'right' }, { title: 'gangs', w: 0.9 }],
            rows: screens,
        }) });
        const frame = { top: HEADER_BOTTOM + 8, bottom: FOOTER_TOP, cols: this._bCols([1.15, 1, 0.9]) };
        this._bFlow(book, blocks, frame, this._bContinuation(book, 'pull', title, header, extra));
    }

    // ---- hardware pages -----------------------------------------------------

    _bDistroPage(book, d) {
        const header = { left: `${book.meta.show} · HARDWARE`, right: d.name };
        const title = `${d.name} - Distro`;
        const extra = { subject: d.name, footer: `Distro · ${d.name}` };
        const load = (typeof this.getDistroLoads === 'function')
            ? this.getDistroLoads().find(x => x.id === d.id) : null;
        const numbers = (typeof this._distroMultiNumbers === 'function') ? this._distroMultiNumbers(d.id) : new Map();
        const boxes = [];
        for (const number of [...numbers.keys()].sort((a, b) => a - b)) {
            const members = numbers.get(number) || [];
            const typed = this.distroBoxType(d, number, members).type;
            let homeRun = null, circuits = 0, amps = 0;
            const names = [];
            for (const m of members) {
                const layer = book.layers.get(String(m.layerId));
                if (!layer) continue;
                names.push(layer.name);
                const s = this.getSocaPlan(layer).find(x => x.soca === m.soca);
                if (!s) continue;
                if (!homeRun && s.length) homeRun = s.length;
                circuits += (s.legs || []).length;
                amps += (s.legs || []).reduce((a, l) => a + (Number(l.amps) || 0), 0);
            }
            boxes.push({ cells: [`${d.name} ${number}`, typed ? typed.name : '—',
                                 homeRun ? this.pullLengthText(homeRun) : 'no length',
                                 names.join(' + '), String(circuits), this._bNum(amps, 1)] });
        }
        if (!boxes.length && !load) return;
        this._bNewPage(book, 'distro', title, header, extra);
        const blocks = [];
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Breakouts',
            cols: [{ title: 'breakout', w: 0.8 }, { title: 'type', w: 0.9 }, { title: 'home run', w: 0.8 },
                   { title: 'screens', w: 1.6 }, { title: 'circuits', w: 0.7, align: 'right' },
                   { title: 'amps', w: 0.7, align: 'right' }],
            rows: boxes.length ? boxes : [{ cells: ['none', '', '', '', '', ''] }],
        }) });
        const pairs = [['Rating', `${d.ratingA} A ${d.voltage} V ${d.phase === 3 ? '3φ' : '1φ'}`]];
        if (load) {
            pairs.push(['Load', `${this._bNum(load.amps, 1)} A · ${this._bNum(load.pct, 0)}% · ${this._bNum(load.watts / 1000, 1)} kW`
                + (load.over ? ' · OVER' : '')]);
            if (load.legs) {
                pairs.push(['Legs', `X ${this._bNum(load.legs.X.amps, 1)} · Y ${this._bNum(load.legs.Y.amps, 1)}`
                    + ` · Z ${this._bNum(load.legs.Z.amps, 1)} A`]);
                pairs.push(['Imbalance', `${this._bNum(load.imbalancePct, 1)}%`]);
            }
        }
        pairs.push(['Breakouts', this._bPlural(boxes.length, 'breakout')]);
        blocks.push({ lines: this._bKvLines(book, 'Service', pairs) });
        const hw = (book.list.hardware || []).find(h => h.kind === 'distro' && h.id === d.id);
        blocks.push({ lines: this._bPullLines(book, 'Pull list', (hw && hw.rows) || []) });
        const frame = { top: HEADER_BOTTOM + 8, bottom: FOOTER_TOP, cols: this._bCols([1.15, 1, 0.9]) };
        this._bFlow(book, blocks, frame, this._bContinuation(book, 'distro', title, header, extra));
    }

    _bPullLines(book, title, rows) {
        const tick = { title: '', w: 0.28, tick: true };
        return this._bTableLines(book, {
            title,
            cols: [tick, { title: 'cable', w: 1.5 }, { title: 'len', w: 0.6 },
                   { title: 'qty', w: 0.5, align: 'right' }, { title: 'label', w: 1.4 }],
            rows: rows.length ? rows.map(r => ({ cells: ['', this._bType(r.type), r.length || '—', String(r.qty), r.label || ''] }))
                : [{ cells: ['', 'none', '', '', ''] }],
        });
    }

    _bProcessorPage(book, proc) {
        const procTitle = proc.name || proc.deviceName || proc.id;
        const header = { left: `${book.meta.show} · HARDWARE`, right: procTitle };
        const title = `${procTitle} - Processor`;
        const extra = { subject: procTitle, footer: `Processor · ${procTitle}` };
        const cards = (proc.slots || []).filter(s => s && s.card).map(s => ({ slot: s.index, card: s.card }));
        if (!cards.length) return;
        this._bNewPage(book, 'processor', title, header, extra);
        const screens = (this._assignment && this._assignment.screens) || [];
        const used = (cardId) => {
            const set = new Set();
            screens.forEach(s => (s.ports || []).forEach(p => { if (p.cardId === cardId && p.port != null) set.add(p.port); }));
            return set.size;
        };
        const nameOf = (cardId) => {
            const hit = cards.find(c => c.card.id === cardId);
            return hit ? (hit.card.name || `slot ${(hit.slot || 0) + 1}`) : (cardId || '—');
        };
        const rows = cards.map(({ slot, card }) => {
            const shape = card.redundancyShape && card.redundancyShape.mode;
            const backup = card.backupCardId ? nameOf(card.backupCardId)
                : (shape && shape !== 'off' ? shape : '—');
            return { cells: [String((slot || 0) + 1), card.name || '—', card.deviceName,
                             `${used(card.id)} / ${card.ceiling != null ? card.ceiling : '?'}`, backup] };
        });
        const blocks = [];
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Cards',
            cols: [{ title: 'slot', w: 0.5, align: 'right' }, { title: 'card', w: 1 }, { title: 'device', w: 1.6 },
                   { title: 'ports', w: 0.8, align: 'right' }, { title: 'backup', w: 1 }],
            rows,
        }) });
        // The breakout boxes hanging off the cards, each with the trunk it
        // takes, the sockets it delivers and its fiber trunk (2026-09-07).
        const boxRows = [];
        for (const { card } of cards) {
            for (const box of (card.cvts || [])) {
                const fiber = (typeof this.pullBoxFiberText === 'function') ? this.pullBoxFiberText(box) : '';
                boxRows.push({ cells: [this._bBoxTitle(box), card.name || nameOf(card.id), box.trunkTitle || '—',
                                       String(box.portCount || (box.ports || []).length),
                                       fiber || 'no fiber length'] });
            }
        }
        if (boxRows.length) {
            blocks.push({ lines: this._bTableLines(book, {
                title: 'Breakout boxes',
                cols: [{ title: 'breakout box', w: 1.3 }, { title: 'card', w: 0.7 }, { title: 'trunk', w: 0.7 },
                       { title: 'ports', w: 0.65, align: 'right' }, { title: 'fiber', w: 1.4 }],
                rows: boxRows,
                shrink: true,
            }) });
        }
        blocks.push({ lines: this._bKvLines(book, 'Redundancy', [
            ['Device', proc.deviceName || proc.deviceId || ''],
            ['Redundancy', this._bRedundancyText(proc)],
        ]) });
        // Snakes and home runs on every card and breakout box of this processor.
        const runs = [];
        for (const { card } of cards) {
            const owners = [{ title: card.name || card.deviceName, rec: card }]
                .concat((card.cvts || []).map(c => ({ title: this._bBoxTitle(c), rec: c })));
            for (const o of owners) {
                for (const s of (o.rec.snakes || [])) {
                    const connId = this.dataPortConnectorId({ rec: o.rec }, s.connector);
                    runs.push({ cells: [s.name || 'snake', `${(s.ports || []).length}-way`,
                                        s.ft ? this.pullLengthText(s.ft) : 'no length',
                                        `${o.title} ${this._fmtTails(s.ports || [])}`
                                        + (connId ? ` · ${this.dataCableConnectorName(connId)}` : '')] });
                }
                for (const [socket, c] of Object.entries(o.rec.portCables || {})) {
                    const ft = Number(c && c.ft);
                    if (!Number.isFinite(ft) || ft <= 0) continue;
                    const connId = this.dataPortConnectorId({ rec: o.rec }, c.connector);
                    runs.push({ cells: [`${o.title} ${socket}`, 'cable', this.pullLengthText(ft),
                                        connId ? this.dataCableConnectorName(connId) : ''] });
                }
            }
        }
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Snakes & home runs',
            cols: [{ title: 'run', w: 1 }, { title: 'ways', w: 0.6 }, { title: 'home run', w: 0.8 }, { title: 'ports', w: 1.6 }],
            rows: runs.length ? runs : [{ cells: ['none', '', '', ''] }],
        }) });
        const hw = (book.list.hardware || []).find(h => h.kind === 'processor' && h.id === proc.id);
        blocks.push({ lines: this._bPullLines(book, 'Pull list', (hw && hw.rows) || []) });
        const frame = { top: HEADER_BOTTOM + 8, bottom: FOOTER_TOP, cols: this._bCols([1.15, 1, 0.9]) };
        this._bFlow(book, blocks, frame, this._bContinuation(book, 'processor', title, header, extra));
    }

    // ---- the totals page ----------------------------------------------------

    _bTotalsPage(book) {
        const header = { left: `${book.meta.show} · PULL`, right: 'All positions' };
        const title = 'Pull list - all positions';
        const extra = { subject: 'All positions', footer: 'Pull · all positions' };
        this._bNewPage(book, 'totals', title, header, extra);
        const blocks = [{ lines: this._bPullLines(book, 'Pull list', book.list.totals || []) }];
        const notes = (book.list.unmodelled || []).map(t => ({ cells: [t] }));
        if (notes.length) {
            blocks.push({ lines: this._bTableLines(book, { title: 'Notes', cols: [{ title: '', w: 1 }], rows: notes }) });
        }
        const frame = { top: HEADER_BOTTOM + 8, bottom: FOOTER_TOP, cols: this._bCols([1, 1, 1]) };
        this._bFlow(book, blocks, frame, this._bContinuation(book, 'totals', title, header, extra));
    }
}

for (const k of Object.getOwnPropertyNames(_Binder.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Binder.prototype, k));
    }
}
