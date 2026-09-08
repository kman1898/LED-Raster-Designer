// app-binder: the binder packet - a DRAWING SET. The show's power and data
// maps, the pull tables and the hardware, laid out on numbered SHEETS the
// way a Vectorworks drawing set reads (2026-09-08, on the NCMF packet he
// held up: "this is a great example to base our binder off of"): every
// sheet a landscape page of one size - Tabloid 17 x 11 by default ("17x11
// i think is great . nice middle gound. but maybe have option for all
// sizes") - with a thin border, a TITLE BLOCK column down its right edge
// ("mimic whats in their drawing": the logo when one is set, REVISIONS -
// the log the exports write - the show / venue / dates, Designer, Project
// Manager, Drafter, the SHEET TITLE, the Sheet Number, the drawing date)
// and the drawing area to its left holding a numbered VIEW - the map with
// its bubble ("1  OVERVIEW") - and the sheet's tables.
//
// Sheets number by SERIES, by subject ("Series by subject"):
//   1.1  Overview - the show map as view 1, POSITIONS / SHOW TOTALS / CONTENTS
//   2.n  one POWER sheet per screen with circuits (the map with rulers and
//        brackets; CIRCUITS / CABLES THIS SCREEN / FACTS / GANGS)
//   3.n  one DATA sheet per screen with ports
//   4.n  one PULL sheet per position
//   5.n  hardware - one per distro, one per processor, then the totals
// A sheet whose tables do not fit continues on the next number of its
// series, "(cont.)"; the map never splits.
//
// Every sheet is painted onto the book canvas (the tests and any preview
// read its pixels) and RECORDED as a display list - rects, lines, text and
// the map bitmaps, in page units at 200 px/in - which /api/export/pdf-from-
// pages replays in points (inches x 72), the text set in Helvetica as real
// PDF text ("so all the text seems low res still" - the packet he held up
// has real vector text). Type sizes are in INCHES: a bigger sheet holds
// more, it does not print bigger type.
//
// The map IS the canvas renderer's own drawing in exportMode - runs,
// arrowheads, label discs sized to their text, the cable tags where the
// screen's Show Cable Tags switch is on, the gang brackets where its 2fer
// switch is on. Those switches are the user's documentation choices and
// the binder follows them; it forces nothing on. The one thing the sheet
// takes off the wall is the screen-name plate (hideScreenNames): the title
// block names the screen, and on a wall of circuits the plate landed on
// top of the labels ("the main label is over the circuits").
//
// Layout inside the drawing area: the map takes the width the tables
// leave. Map-left / tables-right in as few columns as hold the tables
// whole; where the tables need more than half the drawing area's width,
// the map goes on top at full width and the tables below it in columns;
// what still does not fit continues on the next sheet. The map's zoom is
// min(fit, 3x).
//
// Every figure is read from buildPullSheet (app-pull-list.js) and the same
// authorities the canvas reads; nothing is recomputed here. The title
// block's fields live in project.binder (venue, dates, designer, project
// manager, drafter, revisions - the export dialog edits them, one undo
// entry per field; a revision is LOGGED ON EXPORT, 2026-09-08: an export
// at a rev no row carries yet adds a row) and in two preferences (the
// sheet size, the logo).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// Page units: 200 px per inch. A sheet's pixel size is its inches x 200,
// its PDF page its inches x 72 points; every constant below is in page
// pixels and so in inches, whatever the sheet.
const PX_PER_IN = 200;
const SHEETS = {
    letter:  { name: 'Letter 11 × 8.5',  w: 11,    h: 8.5 },
    tabloid: { name: 'Tabloid 17 × 11',  w: 17,    h: 11 },
    archc:   { name: 'ARCH C 24 × 18',   w: 24,    h: 18 },
    archd:   { name: 'ARCH D 36 × 24',   w: 36,    h: 24 },
    a4:      { name: 'A4 11.69 × 8.27',  w: 11.69, h: 8.27 },
    a3:      { name: 'A3 16.54 × 11.69', w: 16.54, h: 11.69 },
};
const DEFAULT_SHEET = 'tabloid';
export function binderSheet(key) {
    const k = SHEETS[key] ? key : DEFAULT_SHEET;
    const s = SHEETS[k];
    return { key: k, name: s.name, inches: [s.w, s.h],
             w: Math.round(s.w * PX_PER_IN), h: Math.round(s.h * PX_PER_IN),
             pt: [Math.round(s.w * 72 * 100) / 100, Math.round(s.h * 72 * 100) / 100] };
}
export const BINDER_SHEETS = Object.keys(SHEETS).map(k => ({ key: k, name: SHEETS[k].name }));

// The sheet's frame: the border a quarter inch in from the edge, the
// title block column 2.4 in wide inside it on the right, the drawing area
// to its left with its own small margin.
const PAD = 50;
const TB_W = 480;
const DA_PAD = 30;
// The book canvas is painted at PAGE_SCALE x (400 px/in) up to a Tabloid /
// A3 sheet; the ARCH sheets, four times the pixels, paint at 1x - the
// canvas is a look, the PDF is vector either way.
const SCALE_PX_BUDGET = 8_000_000;
// Helvetica first: the PDF route draws the page's text in reportlab's
// Helvetica, so the canvas measures with a Helvetica-metric face (Arial is
// metric-compatible where Helvetica is missing) and the vector page lays
// out as measured - a cell that fits here fits on paper.
const FONT = 'Helvetica, Arial, sans-serif';
const INK = '#111111';
const RULE = '#333333';
const FAINT = '#cccccc';
const MUTED = '#666666';
const BAND_BG = '#e9e9e9';
// Type sizes, in px at 200 px/in - so in inches; they do not scale with
// the sheet.
const SZ = { h4: 25, cell: 24, th: 21, foot: 22, ruler: 22, bracket: 28,
             tbLabel: 26, tbCell: 22, tbSmall: 20, tbShow: 30, tbTitle: 32, tbNumber: 56,
             view: 26, viewNumber: 30 };
const ROW_H = 38;
const BAND_H = 46;
const TH_H = 40;
const H4_H = 46;
const BLOCK_GAP = 22;
// The tables' column: 3.5 in wide, a gap between columns; a view's bubble
// takes this much under its map.
const COL_W = 700;
const DATA_COL_W = 1020;              // the Ports table's six columns of whole names
const COL_GAP = 30;
const BUBBLE_H = 96;
// In a stacked layout (map over tables) the map keeps at least this share
// of the drawing area's height; the tables take the rest and continue.
const MAP_MIN_FRAC = 0.45;
// The map's gutters: the rulers' and the brackets' room around the wall.
const MAP_GUTTER = { left: 200, right: 180, top: 74, bottom: 16 };
const MAP_ZOOM_CAP = 3;               // a tiny wall never blows up past 3x

// Cable types print in the GEAR LIST's own vocabulary - the same words the
// workbook export writes - so the binder's Cables table and the pull sheet
// agree row for row. The word the user retired was "Multi" as the name of
// the THING the circuits come out of (that is named by its type); the
// multi CABLE keeps its shop name, and "Tru-1 Breakout" stays the pull
// list's CABLE item.
const BINDER_TYPE_WORDS = {};

// The redundancy bar's own words (app-processors.js), so the page reads
// what the tray reads: "Per card", "Whole unit → H9 BACKUP", "Off".
const REDUNDANCY_WORDS = {
    off: 'Off', port: 'Per port', card: 'Per card', unit: 'Whole unit',
    fixed: 'On', backup: 'Backed up',
};

// The title block's fields, as project.binder stores them.
const BINDER_DEFAULTS = {
    venue: '', dates: '', designer: '',
    projectManager: { name: '', phone: '', email: '' },
    drafter: '', revisions: [],
};
// The logo is stored no larger than this on its long side.
const LOGO_MAX_PX = 1200;
const SERIES = { overview: 1, power: 2, data: 3, pull: 4, distro: 5, processor: 5, totals: 5 };

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
                // A single screen is that screen's sheets and nothing else
                // unless asked; the whole show is the whole set.
                const single = scope.value !== 'show';
                ['export-binder-cover', 'export-binder-pull', 'export-binder-hardware']
                    .forEach(id => {
                        const el = document.getElementById(id);
                        if (el) el.checked = !single;
                    });
                if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
            });
        }
        const sheet = document.getElementById('export-binder-sheet');
        if (sheet) {
            sheet.innerHTML = '';
            for (const s of BINDER_SHEETS) {
                const o = document.createElement('option');
                o.value = s.key; o.textContent = s.name;
                sheet.appendChild(o);
            }
            sheet.addEventListener('change', () => { this.setBinderSheet(sheet.value); });
        }
        const eng = document.getElementById('export-binder-engineer');
        if (eng) eng.addEventListener('change', () => { this.setEngineerName(eng.value); this.syncBinderControls(); });
        const rev = document.getElementById('export-binder-rev');
        if (rev) {
            rev.addEventListener('change', () => {
                this.setPullSheetSetting('rev', rev.value, 'Set Pull Sheet Revision');
                this.syncBinderControls();
                if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
            });
        }
        // The logo: a preference read from a PNG / JPEG file.
        const logo = document.getElementById('export-binder-logo');
        if (logo) {
            logo.addEventListener('change', () => {
                const file = logo.files && logo.files[0];
                logo.value = '';
                if (file) this.readBinderLogoFile(file);
            });
        }
        const logoRemove = document.getElementById('export-binder-logo-remove');
        if (logoRemove) {
            logoRemove.addEventListener('click', () => {
                this.setBinderLogo('').then(() => this.syncBinderControls());
                this.syncBinderControls();
            });
        }
        // The title block's project fields: one undo entry per commit.
        const field = (id, path, action) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('change', () => { this.setBinderField(path, el.value, action); });
        };
        field('export-binder-venue', 'venue', 'Set Binder Venue');
        field('export-binder-dates', 'dates', 'Set Binder Dates');
        field('export-binder-designer', 'designer', 'Set Binder Designer');
        field('export-binder-pm-name', 'projectManager.name', 'Set Binder Project Manager');
        field('export-binder-pm-phone', 'projectManager.phone', 'Set Binder Project Manager Phone');
        field('export-binder-pm-email', 'projectManager.email', 'Set Binder Project Manager Email');
        field('export-binder-drafter', 'drafter', 'Set Binder Drafter');
        // The revision log's rows: a field edits its row in place, × removes
        // the row and the rows after it renumber.
        const revs = document.getElementById('export-binder-revisions');
        if (revs) {
            revs.addEventListener('change', (e) => {
                const el = e.target;
                const row = el && el.closest ? el.closest('[data-index]') : null;
                if (!row || !el.dataset || !el.dataset.field) return;
                this.editBinderRevision(+row.dataset.index, el.dataset.field, el.value);
            });
            revs.addEventListener('click', (e) => {
                const btn = e.target && e.target.closest ? e.target.closest('.binder-rev-remove') : null;
                const row = btn ? btn.closest('[data-index]') : null;
                if (row) this.removeBinderRevision(+row.dataset.index);
            });
        }
    }

    // The section shown only for the binder format, the picture sections
    // hidden then (a set of sheets has no canvas list or view ticks), the
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
        set('export-binder-sheet', this.getBinderSheet());
        set('export-binder-engineer', this.getEngineerName());
        set('export-binder-rev', this.getPullSheetSettings().rev);
        this._syncBinderLogoControls();
        const info = this.getBinderInfo();
        set('export-binder-venue', info.venue);
        set('export-binder-dates', info.dates);
        set('export-binder-designer', info.designer);
        set('export-binder-pm-name', info.projectManager.name);
        set('export-binder-pm-phone', info.projectManager.phone);
        set('export-binder-pm-email', info.projectManager.email);
        set('export-binder-drafter', info.drafter);
        const drafter = document.getElementById('export-binder-drafter');
        if (drafter) drafter.placeholder = this.getEngineerName() || 'Name';
        // the Revision note is this export's and stays as typed
        this._renderBinderRevisionRows();
    }

    // The logo row: the preview and Remove when one is set, "None" when not.
    _syncBinderLogoControls() {
        const src = this.getBinderLogo();
        const show = (id, v) => { const el = document.getElementById(id); if (el) el.style.display = v ? '' : 'none'; };
        const prev = document.getElementById('export-binder-logo-preview');
        if (prev && prev.getAttribute('src') !== (src || '')) prev.src = src || '';
        show('export-binder-logo-preview', !!src);
        show('export-binder-logo-remove', !!src);
        show('export-binder-logo-none', !src);
    }

    // The revision log as the dialog shows it: one row per stored
    // revision - No. (its position), date, by, description, × - built
    // from the stored values as text, never as markup.
    _renderBinderRevisionRows() {
        const box = document.getElementById('export-binder-revisions');
        if (!box) return;
        const rows = this.getBinderInfo().revisions;
        box.innerHTML = '';
        if (!rows.length) {
            const empty = document.createElement('div');
            empty.className = 'binder-rev-empty';
            empty.textContent = 'Nothing logged yet. An export at a new Rev adds a row.';
            box.appendChild(empty);
            return;
        }
        rows.forEach((r, i) => {
            const row = document.createElement('div');
            row.className = 'binder-rev-row';
            row.dataset.index = String(i);
            const no = document.createElement('span');
            no.className = 'binder-rev-no';
            no.textContent = String(r.no);
            row.appendChild(no);
            const input = (field, value, placeholder, tip) => {
                const el = document.createElement('input');
                el.type = 'text';
                el.value = value;
                el.placeholder = placeholder;
                el.dataset.field = field;
                el.className = 'binder-rev-' + field;
                el.setAttribute('data-tooltip', tip);
                row.appendChild(el);
            };
            input('date', r.date, 'M/D/YY', 'The date this revision went out.');
            input('by', r.by, 'By', 'Who issued it - initials.');
            input('description', r.description, 'Description',
                  r.rev ? `What changed in rev ${r.rev}.` : 'What changed.');
            const x = document.createElement('button');
            x.type = 'button';
            x.className = 'binder-rev-remove';
            x.textContent = '×';
            x.setAttribute('data-tooltip', 'Remove this revision; the rows after it renumber.');
            row.appendChild(x);
            box.appendChild(row);
        });
    }

    // What the dialog says, as the set reads it.
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
            sheet: val('export-binder-sheet') || this.getBinderSheet(),
            palette: printer ? 'printer' : 'colour',
            sides: { power: side !== 'data', data: side !== 'power' },
            scope,
            cover: on('export-binder-cover', scope.kind === 'show'),
            pull: on('export-binder-pull', scope.kind === 'show'),
            hardware: on('export-binder-hardware', scope.kind === 'show'),
        };
    }

    // The canvas's right-click: "Export this screen..." opens the same
    // dialog preset to the binder with only that screen's sheets ticked.
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

    // The file the dialog's preview names: the show, the scope, the rev.
    binderFileName(projectName) {
        const opts = this.readBinderOptions();
        const name = projectName || (this.project && this.project.name) || 'Project';
        const rev = this.getPullSheetSettings().rev;
        if (opts.scope.kind === 'screen') {
            const layer = (this.project.layers || []).find(l => String(l.id) === String(opts.scope.layerId));
            if (layer) return `${name} - ${layer.name || layer.id} - binder rev ${rev}.pdf`;
        }
        return `${name} - binder rev ${rev}.pdf`;
    }

    // ---- the title block's fields: project.binder, two preferences ----------

    // The stored fields, defaults filled. Never the stored object itself:
    // readers must not mutate the project.
    getBinderInfo() {
        const s = (v) => String(v == null ? '' : v);
        const stored = (this.project && this.project.binder && typeof this.project.binder === 'object')
            ? this.project.binder : {};
        const pm = (stored.projectManager && typeof stored.projectManager === 'object') ? stored.projectManager : {};
        return {
            venue: s(stored.venue), dates: s(stored.dates), designer: s(stored.designer),
            projectManager: { name: s(pm.name), phone: s(pm.phone), email: s(pm.email) },
            drafter: s(stored.drafter),
            // the log: No. is the row's position; `rev` the number the
            // export wore, so the same rev exported again logs nothing
            revisions: Array.isArray(stored.revisions)
                ? stored.revisions.filter(r => r && typeof r === 'object')
                    .map((r, i) => ({ no: i + 1, rev: s(r.rev), date: s(r.date), by: s(r.by), description: s(r.description) }))
                : [],
        };
    }

    // One field ('venue', 'projectManager.phone', 'revisions'), one history
    // entry, one project POST. Returns true when something changed.
    setBinderField(path, value, action = 'Edit Binder Title Block') {
        if (!this.project) return false;
        const [a, b] = String(path).split('.');
        if (!(a in BINDER_DEFAULTS)) return false;
        const info = this.getBinderInfo();
        const current = b ? info[a][b] : info[a];
        const v = Array.isArray(value) ? value : String(value == null ? '' : value).trim();
        if (JSON.stringify(current) === JSON.stringify(v)) return false;
        if (!this.project.binder || typeof this.project.binder !== 'object') this.project.binder = {};
        if (b) {
            if (!this.project.binder[a] || typeof this.project.binder[a] !== 'object') this.project.binder[a] = {};
            this.project.binder[a][b] = v;
        } else {
            this.project.binder[a] = v;
        }
        // Project-level state, same doctrine as the pull-sheet settings:
        // snapshot after the mutation, then persist. save_project merges
        // top-level keys and restore_project keeps whatever the file
        // carries, so the block rides the project through undo, save and
        // reload.
        this.saveState(action);
        this._persistBinderInfo();
        return true;
    }

    _persistBinderInfo() {
        const send = () => fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ binder: this.project.binder || {} }),
        }).catch(() => {});
        this._binderPushQueue = (this._binderPushQueue || Promise.resolve()).then(send);
        return this._binderPushQueue;
    }

    // ---- the revision log ---------------------------------------------------

    // Logged on export ("Logged on export", 2026-09-08): the rev the
    // dialog names, when no row carries it yet, becomes a row - today's
    // date as M/D/YY, the engineer's initials, the Revision note - with
    // one undo entry, persisted like every other field. The same rev
    // exported again logs nothing. Returns the row it added, or null.
    logBinderRevision(rev, note) {
        if (!this.project) return null;
        const r = String(rev == null ? '' : rev).trim();
        const list = this.getBinderInfo().revisions;
        if (list.some(x => x.rev === r)) return null;
        const row = { no: list.length + 1, rev: r, date: this._binderToday(),
                      by: this.binderInitials(this.getEngineerName()),
                      description: String(note == null ? '' : note).trim() };
        this.setBinderField('revisions', [...list, row], 'Log Revision');
        this._renderBinderRevisionRows();
        sendClientLog('binder_revision_logged', { rev: r, no: row.no, by: row.by });
        return row;
    }

    // One row's field edited in the dialog.
    editBinderRevision(index, field, value) {
        const list = this.getBinderInfo().revisions;
        if (!list[index] || !['date', 'by', 'description'].includes(field)) return false;
        list[index][field] = String(value == null ? '' : value).trim();
        const changed = this.setBinderField('revisions', list, 'Edit Revision');
        this._renderBinderRevisionRows();
        return changed;
    }

    // A row removed; the rows after it renumber.
    removeBinderRevision(index) {
        const list = this.getBinderInfo().revisions;
        if (!(index >= 0 && index < list.length)) return false;
        list.splice(index, 1);
        const changed = this.setBinderField('revisions', list.map((r, i) => ({ ...r, no: i + 1 })), 'Remove Revision');
        this._renderBinderRevisionRows();
        return changed;
    }

    // Today as M/D/YY, the way the log's dates read.
    _binderToday() {
        const d = new Date();
        return `${d.getMonth() + 1}/${d.getDate()}/${String(d.getFullYear()).slice(-2)}`;
    }

    // The first letter of each word of a name, upper-case: "Matt Knotts"
    // is MK; a blank name is ''.
    binderInitials(name) {
        return String(name == null ? '' : name).trim().split(/\s+/)
            .filter(Boolean).map(w => w[0].toUpperCase()).join('');
    }

    // ---- the preferences: the sheet size, the logo ---------------------------

    // The sheet size and the logo are preferences (the same shop show
    // after show), like the engineer's name.
    getBinderSheet() {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        return SHEETS[prefs.binderSheet] ? prefs.binderSheet : DEFAULT_SHEET;
    }

    setBinderSheet(key) {
        return this._setBinderPreference('binderSheet', SHEETS[key] ? key : DEFAULT_SHEET);
    }

    // The logo as stored: a PNG / JPEG data URL, or ''.
    getBinderLogo() {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        return typeof prefs.binderLogo === 'string' && /^data:image\/(png|jpeg);base64,/.test(prefs.binderLogo)
            ? prefs.binderLogo : '';
    }

    // Stores the logo ('' removes it) and has it decoded before resolving,
    // so the next sheet drawn carries it.
    setBinderLogo(dataUrl) {
        const v = String(dataUrl == null ? '' : dataUrl);
        this._binderLogoImage = null;
        return Promise.resolve(this._setBinderPreference('binderLogo', v))
            .then(() => this._ensureBinderLogo())
            .then(() => true);
    }

    // A file from the dialog: PNG or JPEG only - an SVG is refused with a
    // message, since the PDF route draws bitmaps - downscaled to
    // LOGO_MAX_PX on its long side before it is stored.
    async readBinderLogoFile(file) {
        const status = (msg) => {
            const el = document.getElementById('export-binder-logo-status');
            if (el) { el.textContent = msg; el.style.display = msg ? '' : 'none'; }
        };
        const type = String(file && file.type || '').toLowerCase();
        const name = String(file && file.name || '');
        if (type === 'image/svg+xml' || /\.svg$/i.test(name)) {
            status('SVG is not accepted: the PDF draws bitmaps. Save the logo as a PNG or JPEG.');
            return false;
        }
        if (type !== 'image/png' && type !== 'image/jpeg') {
            status('Pick a PNG or JPEG.');
            return false;
        }
        let img;
        try {
            const dataUrl = await new Promise((resolve, reject) => {
                const fr = new FileReader();
                fr.onload = () => resolve(String(fr.result));
                fr.onerror = () => reject(new Error('unreadable'));
                fr.readAsDataURL(file);
            });
            img = await this._binderLoadImage(dataUrl);
        } catch (_) {
            status('That file could not be read as an image.');
            return false;
        }
        const scaled = this._binderScaleLogo(img, type);
        await this.setBinderLogo(scaled);
        status('');
        this.syncBinderControls();
        sendClientLog('binder_logo_set', { type, w: img.naturalWidth, h: img.naturalHeight, bytes: scaled.length });
        return true;
    }

    _binderScaleLogo(img, type) {
        const w0 = img.naturalWidth || img.width, h0 = img.naturalHeight || img.height;
        const k = Math.min(1, LOGO_MAX_PX / Math.max(w0, h0, 1));
        const w = Math.max(1, Math.round(w0 * k)), h = Math.max(1, Math.round(h0 * k));
        const c = document.createElement('canvas');
        c.width = w; c.height = h;
        c.getContext('2d').drawImage(img, 0, 0, w, h);
        return type === 'image/jpeg' ? c.toDataURL('image/jpeg', 0.9) : c.toDataURL('image/png');
    }

    _binderLoadImage(src) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error('not an image'));
            img.src = src;
        });
    }

    // The logo decoded onto its own canvas, ready for the recorder (which
    // takes a bitmap by toDataURL - an HTMLImageElement has none; the
    // canvas carries its PNG once so seventeen sheets do not encode it
    // seventeen times). null when none is set or it will not decode.
    async _ensureBinderLogo() {
        const src = this.getBinderLogo();
        if (!src) { this._binderLogoImage = null; return null; }
        const have = this._binderLogoImage;
        if (have && have.src === src) return have.canvas;
        const pending = this._binderLogoImage = { src, canvas: null, loading: true };
        try {
            const img = await this._binderLoadImage(src);
            const c = document.createElement('canvas');
            c.width = img.naturalWidth; c.height = img.naturalHeight;
            c.getContext('2d').drawImage(img, 0, 0);
            c._binderDataUrl = c.toDataURL('image/png');
            pending.canvas = c;
        } catch (_) {
            pending.canvas = null;
        }
        pending.loading = false;
        return pending.canvas;
    }

    // The logo as a sheet drawn NOW can carry it: the decoded bitmap, or
    // null - with the decode started for the next look. exportBinder
    // awaits _ensureBinderLogo first, so the PDF never misses it.
    _binderLogoNow() {
        const src = this.getBinderLogo();
        if (!src) return null;
        const have = this._binderLogoImage;
        if (have && have.src === src) return have.canvas;
        this._ensureBinderLogo();
        return null;
    }

    _setBinderPreference(key, value) {
        const prefs = { ...(typeof this.getPreferences === 'function' ? this.getPreferences() : {}) };
        if (prefs[key] === value) return false;
        prefs[key] = value;
        this._serverPreferences = prefs;
        try { localStorage.setItem('appPreferences', JSON.stringify(prefs)); } catch (_) {}
        return fetch('/api/preferences', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs),
        }).then(() => true).catch(() => false);
    }

    // ---- the export ---------------------------------------------------------

    // Sheets rendered, one PDF back, saved straight to disk through the
    // same picker path every export takes - no window, no print dialog.
    async exportBinder(projectName) {
        const name = projectName || (this.project && this.project.name) || 'Project';
        const opts = this.readBinderOptions();
        if (typeof this.refreshPortAssignment === 'function') {
            try { await this.refreshPortAssignment(); } catch (_) {}
        }
        await this._ensureBinderLogo();
        // The revision this export wears is logged before the sheets
        // render, so the REVISIONS table on every sheet carries it.
        const noteEl = document.getElementById('export-binder-revision-note');
        const logged = this.logBinderRevision(this.getPullSheetSettings().rev, noteEl ? noteEl.value : '');
        if (logged && noteEl) noteEl.value = '';
        // The sheets as display lists - no bitmaps of the sheets themselves
        // (encoding seventeen 6800-px PNGs nobody reads is seconds of
        // work); the maps ride along as images inside each record.
        const pages = this.renderBinderPages(opts, { bitmaps: false });
        if (!pages.length) throw new Error('Nothing to bind: no screen has circuits or ports');
        sendClientLog('export_binder_start', {
            pages: pages.length, palette: opts.palette, scope: opts.scope.kind, sheet: opts.sheet,
        });
        const response = await fetch('/api/export/pdf-from-pages', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: name,
                // Each sheet: its size in page units and in points, its
                // ops in page units, its bitmaps by id.
                pages: pages.map(p => ({
                    name: p.name, width: p.width, height: p.height, page_size: p.page_size,
                    ops: p.ops, images: p.images,
                })),
            }),
        });
        if (!response.ok) {
            let msg = 'Failed to build the binder';
            try { msg = (await response.json()).error || msg; } catch (_) {}
            throw new Error(msg);
        }
        const blob = await response.blob();
        await this.saveBlobWithPicker(blob, this.binderFileName(name), 'application/pdf');
        return { pages: pages.length };
    }

    // The sheet list, without drawing anything: [{ kind, number, title,
    // sheetTitle, layerId, subject, layout, cols, w, h }] - w, h the
    // sheet in page pixels.
    planBinder(opts) {
        const book = this._binderBook(opts || this.readBinderOptions(), { dry: true });
        return book.pages.map(p => this._bPlanEntry(book, p));
    }

    _bPlanEntry(book, p) {
        return { kind: p.kind, number: p.number, title: p.title, sheetTitle: p.sheetTitle,
                 view: p.view || null, layerId: p.layerId || null, subject: p.subject || null,
                 layout: p.layout, cols: p.cols || 0, w: book.sheet.w, h: book.sheet.h,
                 sheet: book.sheet.key };
    }

    // Every sheet's record, in order: { name, width, height, page_size,
    // ops, images } (see _bClosePage), plus `dataUrl` - the painted sheet
    // as a PNG - when `run.bitmaps` is on (the default; the export turns
    // it off, having no use for it).
    renderBinderPages(opts, run) {
        const o = opts || this.readBinderOptions();
        const dry = this._binderBook(o, { dry: true });
        const plan = dry.pages.map(p => this._bPlanEntry(dry, p));
        const bitmaps = !run || run.bitmaps !== false;
        const book = this._binderBook(o, { dry: false, total: plan.length, plan, bitmaps });
        return book.records;
    }

    // One sheet painted for a look (tests, previews): the sheet's canvas,
    // its record (the display list), plus every text the sheet and its map
    // drew, every dash the map set, the map's place and the view bubble.
    renderBinderPage(opts, index, run) {
        const o = opts || this.readBinderOptions();
        const dry = this._binderBook(o, { dry: true });
        const plan = dry.pages.map(p => this._bPlanEntry(dry, p));
        const log = { texts: [], textInfo: [], mapTexts: [], dashes: [] };
        const bitmaps = !!(run && run.bitmaps);
        const book = this._binderBook(o, { dry: false, total: plan.length, plan, only: index, log, bitmaps });
        this._binderLastCanvas = book.canvas;
        return { canvas: book.canvas, record: book.records[0] || null,
                 texts: log.texts, textInfo: log.textInfo, mapTexts: log.mapTexts,
                 dashes: log.dashes, map: log.map || null, brackets: log.brackets || [],
                 bubble: log.bubble || null, titleBlock: log.titleBlock || null,
                 logo: log.logo || null,
                 page: plan[index] || null, pages: plan.length, sheet: book.sheet };
    }

    // ---- the book -----------------------------------------------------------

    _binderBook(opts, run) {
        // The edited list: the pull sheets and the totals sheet print what
        // the user's pull-sheet edits say; the per-screen readings
        // (byScreen, hardware) are the show's own.
        const list = this.buildPullSheet();
        const settings = list.settings || this.getPullSheetSettings();
        const layers = new Map((this.project.layers || []).map(l => [String(l.id), l]));
        const engineer = this.getEngineerName();
        const info = this.getBinderInfo();
        const meta = {
            show: (this.project && this.project.name) || 'Untitled Project',
            date: this._pullSheetDate().date,
            rev: settings.rev,
            engineer,
            palette: opts.palette === 'printer' ? 'printer' : 'colour',
            logo: this._binderLogoNow(),
            binder: { ...info, drafter: info.drafter || engineer },
        };
        const sheet = binderSheet(opts.sheet || this.getBinderSheet());
        const canvas = run.dry ? null : (this._binderCanvas || (this._binderCanvas = document.createElement('canvas')));
        const realCtx = canvas ? canvas.getContext('2d') : null;
        // Measuring needs a real context even on the dry pass.
        const measureCtx = realCtx || (this._binderMeasureCtx
            || (this._binderMeasureCtx = document.createElement('canvas').getContext('2d')));
        const book = {
            opts, list, meta, layers, run, sheet,
            geo: this._bGeo(sheet),
            scale: sheet.w * sheet.h > SCALE_PX_BUDGET ? 1 : 2,
            dry: !!run.dry, total: run.total || 0, only: run.only, plan: run.plan || null,
            log: run.log || null, bitmaps: !!run.bitmaps,
            series: {}, views: 0,
            pages: [], records: [], canvas, realCtx, measureCtx, ctx: null, page: null,
        };
        const scopeLayer = opts.scope && opts.scope.kind === 'screen'
            ? layers.get(String(opts.scope.layerId)) || null : null;
        if (opts.scope && opts.scope.kind === 'screen' && !scopeLayer) return this._binderFinish(book);

        // The positions, each with the screens whose OWN position it is
        // (memberIds; a device-only position - a beach a distro or box sits
        // on - prints no map sheet) and every screen with rows on it
        // (layerIds - the pull sheet lists them all).
        const positions = [];
        for (const pos of list.positions) {
            const members = pos.layerIds.map(id => layers.get(String(id))).filter(Boolean);
            const own = (pos.memberIds || pos.layerIds).map(id => layers.get(String(id))).filter(Boolean);
            const mine = scopeLayer ? members.filter(l => l.id === scopeLayer.id) : members;
            if (!mine.length) continue;
            positions.push({ pos, members, own: scopeLayer ? own.filter(l => l.id === scopeLayer.id) : own });
        }
        // Series by subject: 1 overview, 2 power, 3 data, 4 pull, 5 hardware.
        if (opts.cover) this._bOverviewPage(book);
        for (const view of ['power', 'data']) {
            if (!opts.sides[view]) continue;
            for (const { pos, own } of positions) {
                for (const layer of own) {
                    const scr = list.byScreen[layer.id];
                    if (!scr) continue;
                    if (view === 'power' ? this._bHasPower(layer, scr) : this._bHasData(layer, scr)) {
                        this._bScreenPage(book, layer, pos, view);
                    }
                }
            }
        }
        if (opts.pull) {
            for (const { pos, members } of positions) this._bPullPage(book, pos, members);
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

    // The sheet's frame in page pixels: the border, the title block, the
    // drawing area.
    _bGeo(sheet) {
        const W = sheet.w, H = sheet.h;
        const border = { x: PAD, y: PAD, w: W - PAD * 2, h: H - PAD * 2 };
        const tb = { x: W - PAD - TB_W, y: PAD, w: TB_W, h: H - PAD * 2 };
        const da = { x: PAD + DA_PAD, y: PAD + DA_PAD, w: tb.x - PAD - DA_PAD * 2, h: H - PAD * 2 - DA_PAD * 2 };
        return { W, H, border, tb, da };
    }

    // ---- sheets: number, paint, frame, close --------------------------------

    // A sheet. `spec` names it ({ kind, title, sheetTitle, view?, layerId,
    // subject, layout, cols }); `body(page)` draws its drawing area
    // through book.ctx - on a painting pass, for the sheet being painted:
    // the book canvas sized to the sheet at book.scale, the frame (border,
    // title block) drawn, then the body - through the recording context,
    // so the sheet's display list is written as the canvas is painted.
    // The plan (dry) and the sheets not being painted only take their
    // number.
    _bPage(book, spec, body) {
        this._bClosePage(book);
        const index = book.pages.length;
        const series = SERIES[spec.kind] || 5;
        book.series[series] = (book.series[series] || 0) + 1;
        // the sheet title in caps, as the block and the contents print it
        const page = { index, number: `${series}.${book.series[series]}`, painting: false, ...spec,
                       sheetTitle: String(spec.sheetTitle || spec.title || '').toUpperCase() };
        book.pages.push(page);
        book.page = page;
        const painting = !book.dry && book.realCtx && (book.only == null || book.only === index);
        if (painting) {
            page.painting = true;
            book.canvas.width = book.geo.W * book.scale;
            book.canvas.height = book.geo.H * book.scale;
            page.ops = [];
            page.images = {};
            book.ctx = this._bRecCtx(book, page);
            this._bPageFrame(book, page);
            body(page);
        } else {
            book.ctx = this._bDryCtx(book.measureCtx);
        }
        this._bClosePage(book);
        return page;
    }

    // The sheet's white, its border, the title block, the rev in the
    // corner.
    _bPageFrame(book, page) {
        const ctx = book.ctx;
        const { W, H, border, da } = book.geo;
        ctx.setTransform(book.scale, 0, 0, book.scale, 0, 0);
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = INK;
        ctx.lineWidth = 3;
        ctx.setLineDash([]);
        ctx.strokeRect(border.x, border.y, border.w, border.h);
        this._bTitleBlock(book, page);
        // The revision in the sheet's corner (the title block's REVISIONS
        // are the history; this is the number the file wears).
        this._bText(book, `rev ${book.meta.rev}`, da.x, border.y + border.h - 9,
                    { size: SZ.foot, color: MUTED });
    }

    // The painted sheet as its record - what the PDF route replays:
    //   { name, width, height,                        the sheet in page units
    //     page_size: [in x 72, in x 72],              the PDF page in points
    //     ops: [...],                                 the display list (_bRecCtx)
    //     images: { id: 'data:image/png;base64,…' } } the bitmaps its image ops name
    // plus `dataUrl`, the painted canvas as a PNG, when the book asked for
    // bitmaps (encoding a 6800-px sheet is real work, so only a caller
    // that reads it pays for it).
    _bClosePage(book) {
        const page = book.page;
        if (!page) return;
        if (page.painting && book.canvas) {
            const rec = {
                name: page.title, width: book.geo.W, height: book.geo.H,
                page_size: [book.sheet.pt[0], book.sheet.pt[1]],
                ops: page.ops || [], images: page.images || {},
            };
            if (book.bitmaps) rec.dataUrl = book.canvas.toDataURL('image/png');
            book.records.push(rec);
        }
        book.page = null;
        book.ctx = null;
    }

    // ---- the title block ----------------------------------------------------

    // The column down the sheet's right edge, top to bottom: the logo
    // (only when one is set - without one the box does not exist),
    // REVISIONS, the show block, the people, the sheet title, the sheet
    // number and the date. Every section a fixed height in inches but
    // REVISIONS, which takes what the sheet leaves - the tall box. A blank
    // field prints its label and nothing else.
    _bTitleBlock(book, page) {
        const ctx = book.ctx;
        const { tb } = book.geo;
        const m = book.meta;
        const b = m.binder;
        const pad = 18;
        const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
        const logo = m.logo && m.logo.width > 0 && m.logo.height > 0 ? m.logo : null;
        const hLogo = logo ? clamp(Math.round(tb.h * 0.16), 220, 360) : 0;
        const hShow = 170, hPeople = 330, hTitle = 90, hNumber = 150;
        const hRev = Math.max(120, tb.h - (hLogo + hShow + hPeople + hTitle + hNumber));
        const rule = (y) => { ctx.fillStyle = INK; ctx.fillRect(tb.x, y - 1, tb.w, 3); };
        // the column's own left edge
        ctx.fillStyle = INK;
        ctx.fillRect(tb.x - 1, tb.y, 3, tb.h);
        const x = tb.x, w = tb.w;
        const inner = w - pad * 2;
        let y = tb.y;
        const sections = {};

        // 1. the logo, fitted inside its box and centred
        if (logo) {
            this._bLogo(book, logo, { x, y, w, h: hLogo }, pad);
            sections.logo = { y, h: hLogo };
            y += hLogo; rule(y);
        }

        // 2. REVISIONS: No · Date · By · Description, the log in order
        this._bText(book, 'Revisions:', x + pad, y + 32, { size: SZ.tbLabel, weight: 700 });
        const cols = [[0, 'No.'], [0.13, 'Date'], [0.38, 'By'], [0.56, 'Description']];
        const cx = (f) => x + pad + f * inner;
        cols.forEach(([f, t]) => this._bText(book, t, cx(f) + 4, y + 62, { size: SZ.tbSmall, weight: 400 }));
        ctx.fillStyle = RULE;
        ctx.fillRect(x + pad, y + 68, inner, 2);
        ctx.strokeStyle = RULE;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
        for (const [f] of cols.slice(1)) {
            ctx.beginPath();
            ctx.moveTo(cx(f), y + 44);
            ctx.lineTo(cx(f), y + hRev - pad);
            ctx.stroke();
        }
        const revRows = Math.max(0, Math.floor((hRev - 96 - 4) / 30));
        b.revisions.slice(0, revRows).forEach((r, i) => {
            const ry = y + 96 + i * 30;
            this._bText(book, String(r.no || i + 1), cx(0) + 4, ry, { size: SZ.tbSmall, maxWidth: 0.13 * inner - 8 });
            this._bText(book, r.date, cx(0.13) + 4, ry, { size: SZ.tbSmall, maxWidth: 0.25 * inner - 8 });
            this._bText(book, r.by, cx(0.38) + 4, ry, { size: SZ.tbSmall, maxWidth: 0.18 * inner - 8 });
            this._bText(book, r.description, cx(0.56) + 4, ry, { size: SZ.tbSmall, maxWidth: 0.44 * inner - 8 });
        });
        sections.revisions = { y, h: hRev, rows: Math.min(b.revisions.length, revRows) };
        y += hRev; rule(y);

        // 3. the show: name, VENUE, dates
        this._bText(book, m.show, x + w / 2, y + 50, { size: SZ.tbShow, weight: 700, align: 'center', maxWidth: inner, shrink: true });
        this._bText(book, b.venue, x + w / 2, y + 88, { size: SZ.tbCell, upper: true, align: 'center', maxWidth: inner, shrink: true });
        ctx.fillStyle = RULE;
        ctx.fillRect(x, y + 108, w, 2);
        this._bText(book, b.dates, x + w / 2, y + 146, { size: SZ.tbCell, align: 'center', maxWidth: inner });
        sections.show = { y, h: hShow };
        y += hShow; rule(y);

        // 4. the people
        this._bText(book, 'Designer:', x + pad, y + 34, { size: SZ.tbLabel, weight: 700 });
        this._bText(book, b.designer, x + pad + 40, y + 64, { size: SZ.tbCell, maxWidth: inner - 40 });
        this._bText(book, 'Project Manager:', x + pad, y + 112, { size: SZ.tbLabel, weight: 700 });
        this._bText(book, b.projectManager.name, x + pad + 40, y + 142, { size: SZ.tbCell, maxWidth: inner - 40 });
        this._bText(book, b.projectManager.phone, x + pad + 40, y + 170, { size: SZ.tbCell, maxWidth: inner - 40 });
        this._bText(book, b.projectManager.email, x + pad + 40, y + 198, { size: SZ.tbCell, maxWidth: inner - 40 });
        this._bText(book, 'Drafter:', x + pad, y + 246, { size: SZ.tbLabel, weight: 700 });
        this._bText(book, b.drafter, x + pad + 40, y + 276, { size: SZ.tbCell, maxWidth: inner - 40 });
        sections.people = { y, h: hPeople };
        y += hPeople; rule(y);

        // 5. the sheet title
        this._bText(book, page.sheetTitle || page.title, x + w / 2, y + 58,
                    { size: SZ.tbTitle, weight: 700, upper: true, align: 'center', maxWidth: inner, shrink: true });
        sections.title = { y, h: hTitle };
        y += hTitle; rule(y);

        // 6. the sheet number and the drawing date, either side of the
        //    diagonal
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(x, y + hNumber);
        ctx.lineTo(x + w, y);
        ctx.stroke();
        this._bText(book, 'Sheet Number', x + pad, y + 34, { size: SZ.tbCell });
        this._bText(book, page.number, x + pad, y + 108, { size: SZ.tbNumber, weight: 800 });
        this._bText(book, m.date, x + w - pad, y + hNumber - 40, { size: SZ.tbSmall, weight: 700, align: 'right' });
        this._bText(book, 'Drawing Date', x + w - pad, y + hNumber - 14, { size: SZ.tbSmall, align: 'right' });
        sections.number = { y, h: hNumber };
        if (book.log && page.painting) book.log.titleBlock = { ...tb, sections };
    }

    // The logo fitted inside its box, centred, through the recorder's
    // image op so it reaches the PDF (mask='auto' there keeps a
    // transparent PNG clean).
    _bLogo(book, logo, box, pad) {
        const iw = logo.width, ih = logo.height;
        const k = Math.min((box.w - pad * 2) / iw, (box.h - pad * 2) / ih);
        const w = Math.max(1, Math.round(iw * k)), h = Math.max(1, Math.round(ih * k));
        const x = Math.round(box.x + (box.w - w) / 2), y = Math.round(box.y + (box.h - h) / 2);
        book.ctx.drawImage(logo, x, y, w, h);
        if (book.log && book.page && book.page.painting) book.log.logo = { x, y, w, h };
    }

    // ---- the recording context ----------------------------------------------

    // A context that paints AND writes down what it painted. It wraps the
    // book's real context - every call and property goes through, so the
    // canvas is painted exactly as before (the tests and any preview read
    // its pixels) - and records each drawing op as an entry of the sheet's
    // display list, in PAGE units (book.scale undone) with colours as hex:
    //   { op: 'rect', x, y, w, h, fill }                 fillRect
    //   { op: 'rect', x, y, w, h, stroke, width }        strokeRect
    //   { op: 'line', points: [[x, y]…], width, dash, stroke }
    //                                     one per subpath of beginPath … stroke
    //   { op: 'text', text, x, y, size, weight, align, baseline, color, rotate }
    //                                     rotate in radians; x, y the anchor
    //                                     where the text is drawn, already
    //                                     through the translate / rotate pair
    //                                     the brackets' labels use - the list
    //                                     carries no raw transforms
    //   { op: 'image', id, x, y, w, h }   the bitmap once in page.images[id]
    //                                     (a canvas carrying _binderDataUrl -
    //                                     the logo - gives its PNG as is)
    // The transform is tracked in page space: setTransform(scale, …) is the
    // sheet's identity, translate and rotate compose onto it, save and
    // restore stack it. Nothing else the binder draws with needs tracking
    // (grep `ctx\.` here: no scale, no arcs - the view bubble's circle is a
    // polyline - no fills of paths).
    _bRecCtx(book, page) {
        const t = book.realCtx;
        const ops = page.ops;
        const images = page.images;
        const S = book.scale;
        // the current transform in page units, and its stack
        let xf = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };
        const stack = [];
        const map = (x, y) => [xf.a * x + xf.c * y + xf.e, xf.b * x + xf.d * y + xf.f];
        const mul = (m, n) => ({
            a: m.a * n.a + m.c * n.b, b: m.b * n.a + m.d * n.b,
            c: m.a * n.c + m.c * n.d, d: m.b * n.c + m.d * n.d,
            e: m.a * n.e + m.c * n.f + m.e, f: m.b * n.e + m.d * n.f + m.f,
        });
        const rotation = () => {
            const r = Math.atan2(xf.b, xf.a);
            return Math.abs(r) < 1e-9 ? 0 : r;
        };
        const round = (v) => Math.round(v * 100) / 100;
        // a colour as #rrggbb: the binder sets hex; anything else is read
        // back from the real context, which serialises opaque colours as
        // hex and the rest as rgb(a)
        const hex = (v) => {
            let s = String(v == null ? '' : v).trim();
            if (/^#[0-9a-f]{6}$/i.test(s)) return s.toLowerCase();
            if (/^#[0-9a-f]{3}$/i.test(s)) return ('#' + s[1] + s[1] + s[2] + s[2] + s[3] + s[3]).toLowerCase();
            const m = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/.exec(s);
            if (m) {
                return '#' + [m[1], m[2], m[3]].map(n => Math.max(0, Math.min(255, +n)).toString(16).padStart(2, '0')).join('');
            }
            return '#000000';
        };
        const fillHex = () => hex(t.fillStyle);
        const strokeHex = () => hex(t.strokeStyle);
        // the font the real context holds, as it serialises it: "bold 24px
        // …", "800 24px …", "24px …"
        const font = () => {
            const f = String(t.font || '');
            const m = /(?:^|\s)(bold|bolder|normal|\d{3})\s+(\d+(?:\.\d+)?)px/.exec(f)
                || /(\d+(?:\.\d+)?)px/.exec(f);
            if (!m) return { size: SZ.cell, weight: 400 };
            if (m.length === 2) return { size: parseFloat(m[1]), weight: 400 };
            const w = m[1] === 'bold' ? 700 : m[1] === 'bolder' ? 900 : m[1] === 'normal' ? 400 : parseInt(m[1], 10);
            return { size: parseFloat(m[2]), weight: w };
        };
        let subpaths = [];
        let imageSeq = 0;
        const methods = {
            setTransform(a, b, c, d, e, f) {
                xf = { a: a / S, b: b / S, c: c / S, d: d / S, e: e / S, f: f / S };
                return t.setTransform(a, b, c, d, e, f);
            },
            translate(x, y) {
                xf = mul(xf, { a: 1, b: 0, c: 0, d: 1, e: x, f: y });
                return t.translate(x, y);
            },
            rotate(r) {
                const cs = Math.cos(r), sn = Math.sin(r);
                xf = mul(xf, { a: cs, b: sn, c: -sn, d: cs, e: 0, f: 0 });
                return t.rotate(r);
            },
            save() { stack.push({ ...xf }); return t.save(); },
            restore() { if (stack.length) xf = stack.pop(); return t.restore(); },
            fillRect(x, y, w, h) {
                const [px, py] = map(x, y);
                ops.push({ op: 'rect', x: round(px), y: round(py), w: round(w), h: round(h), fill: fillHex() });
                return t.fillRect(x, y, w, h);
            },
            strokeRect(x, y, w, h) {
                const [px, py] = map(x, y);
                ops.push({ op: 'rect', x: round(px), y: round(py), w: round(w), h: round(h),
                           stroke: strokeHex(), width: round(t.lineWidth) });
                return t.strokeRect(x, y, w, h);
            },
            beginPath() { subpaths = []; return t.beginPath(); },
            moveTo(x, y) { subpaths.push([map(x, y).map(round)]); return t.moveTo(x, y); },
            lineTo(x, y) {
                if (!subpaths.length) subpaths.push([]);
                subpaths[subpaths.length - 1].push(map(x, y).map(round));
                return t.lineTo(x, y);
            },
            stroke() {
                const width = round(t.lineWidth), dash = Array.from(t.getLineDash() || []).map(round);
                const stroke = strokeHex();
                for (const points of subpaths) {
                    if (points.length >= 2) ops.push({ op: 'line', points, width, dash, stroke });
                }
                return t.stroke();
            },
            fillText(text, x, y, maxWidth) {
                const [px, py] = map(x, y);
                const f = font();
                ops.push({ op: 'text', text: String(text), x: round(px), y: round(py),
                           size: f.size, weight: f.weight,
                           align: t.textAlign || 'left', baseline: t.textBaseline || 'alphabetic',
                           color: fillHex(), rotate: rotation() });
                return maxWidth === undefined ? t.fillText(text, x, y) : t.fillText(text, x, y, maxWidth);
            },
            drawImage(img, ...args) {
                // the binder draws (img, x, y, w, h); the bitmap is taken
                // now, as the offscreen canvas is reused for the next map
                const [x, y, w, h] = args.length >= 5 ? args.slice(4) : args;
                const [px, py] = map(x, y);
                const id = `img${++imageSeq}`;
                let data = null;
                try {
                    data = typeof img._binderDataUrl === 'string' ? img._binderDataUrl
                        : typeof img.toDataURL === 'function' ? img.toDataURL('image/png') : null;
                } catch (_) {}
                if (data) {
                    images[id] = data;
                    ops.push({ op: 'image', id, x: round(px), y: round(py), w: round(w), h: round(h) });
                }
                return t.drawImage(img, ...args);
            },
        };
        return new Proxy(t, {
            get(target, k) {
                if (Object.prototype.hasOwnProperty.call(methods, k)) return methods[k];
                const v = target[k];
                return typeof v === 'function' ? v.bind(target) : v;
            },
            set(target, k, v) { target[k] = v; return true; },
        });
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
        if (book.log && book.page && book.page.painting && opts.log !== false) {
            book.log.texts.push(t);
            if (book.log.textInfo) book.log.textInfo.push({ text: t, size, weight: opts.weight || 400 });
        }
        return t;
    }

    // Does `text` fit `maxWidth` at `size`, shrinking as _bText would?
    _bTextFits(book, text, size, weight, maxWidth) {
        const ctx = book.ctx;
        let s = size;
        ctx.font = this._bFont(s, weight);
        while (s > 14 && ctx.measureText(text).width > maxWidth) {
            s -= 1;
            ctx.font = this._bFont(s, weight);
        }
        return ctx.measureText(text).width <= maxWidth;
    }

    // A cell that says two things - the data sheet's HOME RUN, "SR Primary
    // 150' / SR Backup 150'" - is drawn on ONE line where it fits after
    // shrinking, else as two lines inside the same row (the primary over
    // the backup), each shrinking on its own, so a run is never cut to
    // "…". Logged as one text, the whole cell, so a reader of the sheet's
    // texts still sees one entry per cell.
    _bTextTwoLines(book, text, x, y, o) {
        const opts = o || {};
        const parts = String(text).split(' / ');
        if (parts.length !== 2
                || this._bTextFits(book, text, opts.size || SZ.cell, opts.weight, opts.maxWidth)) {
            return this._bText(book, text, x, y, opts);
        }
        const size = 16;
        const drawn = parts.map((p, k) => this._bText(book, p, x, y - 12 + k * 17,
            { ...opts, size, shrink: true, log: false }));
        const t = drawn.join(' / ');
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

    // ---- tables: lines, the packer, the layout ------------------------------

    // A table as a list of LINES - a title, a heading, then bands and rows -
    // each knowing its height and how to draw itself at (x, y, w). The
    // packer below lays a block's lines into columns, the head lines
    // repeated wherever a block continues.
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
            lines.push({ h: H4_H, head: true, draw: (ctx, x, y, w) => {
                this._bText(book, spec.title, x, y + 30,
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
                lines.push({ h: BAND_H, band: true, draw: (ctx, x, y, w) => {
                    if (book.meta.palette === 'printer') {
                        ctx.fillStyle = INK;
                        ctx.fillRect(x, y + 2, w, 3);
                    } else {
                        ctx.fillStyle = BAND_BG;
                        ctx.fillRect(x, y, w, BAND_H - 4);
                    }
                    this._bText(book, r.band, x + padX, y + 31,
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
                    // data sheet's PRIMARY / BACKUP) shrinks a long one a
                    // little before it is cut, the way a heading does; a
                    // cell saying two things ("A / B" - HOME RUN with a
                    // backup end) goes to two lines rather than being cut.
                    const o = { size: SZ.cell, weight: r.bold ? 700 : 400, align: L[i].align,
                                maxWidth: L[i].w - padX * 2, shrink: !!spec.shrink };
                    if (spec.shrink) this._bTextTwoLines(book, cell, ax, y + 27, o);
                    else this._bText(book, cell, ax, y + 27, o);
                });
                if (!r.bold) { ctx.fillStyle = FAINT; ctx.fillRect(x, y + ROW_H - 2, w, 2); }
            } });
        }
        return lines;
    }

    // A key/value block (the Facts) as lines.
    _bKvLines(book, title, pairs) {
        const lines = [];
        lines.push({ h: H4_H, head: true, draw: (ctx, x, y, w) => {
            this._bText(book, title, x, y + 30,
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
            // Height is measured against the tables' own column width; a
            // wider column wraps a little looser and clips nothing - the
            // row keeps its measured height.
            const n = rowsOf(COL_W).length;
            lines.push({ h: ROW_H * n, draw: (ctx, x, y, w) => {
                this._bText(book, k, x, y + 27, { size: SZ.cell, weight: 700 });
                rowsOf(w).forEach((t, i) => {
                    this._bText(book, t, x + keyW, y + 27 + i * ROW_H, { size: SZ.cell, maxWidth: w - keyW });
                });
            } });
        }
        return lines;
    }

    // THE PACKER. Blocks in order into up to `maxCols` columns of height
    // `colH`: a block follows the one before it in the same column (a gap
    // between), moves whole to the next column where it would fit there
    // whole but not here, and is SPLIT at a line where it is taller than a
    // column - its head lines (the title, the heading row) repeated where
    // it continues, a band never left as the last line over nothing. What
    // no column holds comes back as `rest`, blocks again (the split
    // block's remainder headed), for the next sheet.
    //   { cols: [{ h, items: [{ line, y }] }], rest: [{ lines }] }
    _bPack(blocks, colH, maxCols) {
        const cols = [];
        let col = null;
        const open = () => {
            if (cols.length >= maxCols) return false;
            col = { h: 0, items: [] };
            cols.push(col);
            return true;
        };
        const rest = [];
        const queue = blocks.filter(b => b && (b.lines || []).length).map(b => ({ lines: b.lines.slice() }));
        while (queue.length) {
            const block = queue[0];
            const heads = block.lines.filter(l => l.head);
            const total = block.lines.reduce((s, l) => s + l.h, 0);
            if (!col && !open()) break;
            let y = col.items.length ? col.h + BLOCK_GAP : 0;
            if (col.items.length && y + total > colH && total <= colH) {
                // whole in the next column rather than split here
                if (!open()) break;
                y = 0;
            }
            // how many lines fit from here
            let n = 0, fitH = 0;
            for (const l of block.lines) {
                if (y + fitH + l.h > colH) break;
                fitH += l.h; n++;
            }
            while (n > 0 && block.lines[n - 1].band) n--;
            const useful = block.lines.slice(0, n).some(l => !l.head);
            if (!useful) {
                if (col.items.length) {
                    // this column is done; try the next
                    if (!open()) break;
                    continue;
                }
                // an empty column cannot hold even one row: force the
                // heads and the first row, so nothing loops forever
                n = Math.min(block.lines.length, heads.length + 1);
                while (n < block.lines.length && block.lines[n - 1].band) n++;
            }
            for (const l of block.lines.slice(0, n)) {
                col.items.push({ line: l, y });
                y += l.h;
            }
            col.h = y;
            const remaining = block.lines.slice(n);
            if (remaining.length) {
                // the block continues: its heads again over what is left,
                // in a fresh column
                block.lines = heads.concat(remaining);
                col = null;
                if (cols.length >= maxCols) break;
            } else {
                queue.shift();
            }
        }
        for (const b of queue) rest.push({ lines: b.lines });
        return { cols, rest };
    }

    // The layout of one sheet's drawing area for `blocks`, with a map or
    // without:
    //   tables  - no map: the tables across the whole area in as many
    //             columns as fit its width (widened to share it)
    //   side    - map left, tables right in the fewest columns of COL_W
    //             that hold them whole, never past half the width
    //   stack   - the map on top at full width (at least MAP_MIN_FRAC of
    //             the height), the tables under it across the width
    // Whatever the sheet cannot hold is `pack.rest`, for a continuation.
    // A block may ask for a wider column (`minW` - the data sheet's Ports
    // table, six columns of whole names); every column on the sheet is
    // then that wide.
    _bLayout(book, blocks, withMap) {
        const da = book.geo.da;
        const colW = Math.max(COL_W, ...blocks.map(b => (b && b.minW) || 0));
        const across = Math.max(1, Math.floor((da.w + COL_GAP) / (colW + COL_GAP)));
        const wide = (da.w - (across - 1) * COL_GAP) / across;
        if (!withMap) {
            const pack = this._bPack(blocks, da.h, across);
            return { kind: 'tables', cols: across, colW: wide, top: da.y, pack,
                     colX: (i) => da.x + i * (wide + COL_GAP), mapArea: null };
        }
        const kmax = Math.floor((da.w / 2 + COL_GAP) / (colW + COL_GAP));
        for (let k = 1; k <= kmax; k++) {
            const pack = this._bPack(blocks, da.h, k);
            if (pack.rest.length) continue;
            const tablesW = k * colW + (k - 1) * COL_GAP;
            const mapArea = { x: da.x, y: da.y, w: da.w - tablesW - COL_GAP, h: da.h - BUBBLE_H };
            return { kind: 'side', cols: k, colW, top: da.y, pack, mapArea,
                     colX: (i) => da.x + mapArea.w + COL_GAP + i * (colW + COL_GAP) };
        }
        const colH = Math.floor(da.h - BUBBLE_H - COL_GAP - Math.round(da.h * MAP_MIN_FRAC));
        const pack = this._bPack(blocks, colH, across);
        const tablesH = pack.cols.reduce((m, c) => Math.max(m, c.h), 0);
        const mapArea = { x: da.x, y: da.y, w: da.w, h: da.h - BUBBLE_H - COL_GAP - tablesH };
        return { kind: 'stack', cols: across, colW: wide, top: mapArea.y + mapArea.h + BUBBLE_H + COL_GAP,
                 pack, mapArea, colX: (i) => da.x + i * (wide + COL_GAP) };
    }

    // The packed columns drawn where the layout put them.
    _bDrawLayout(book, L) {
        L.pack.cols.forEach((col, i) => {
            const x = L.colX(i);
            for (const it of col.items) it.line.draw(book.ctx, x, L.top + it.y, L.colW);
        });
    }

    // A subject's sheets from its blocks: tables only, continuing
    // "(cont.)" on the next number of the series while any remain.
    _bTableSheets(book, spec, blocks) {
        let rest = blocks;
        let first = true;
        do {
            const L = this._bLayout(book, rest, false);
            const cont = first ? {} : { title: `${spec.title} (cont.)`, sheetTitle: `${spec.sheetTitle} (CONT.)` };
            this._bPage(book, { ...spec, ...cont, layout: L.kind, cols: L.cols },
                        () => this._bDrawLayout(book, L));
            rest = L.pack.rest;
            first = false;
        } while (rest.length);
    }

    // A map sheet: the map as a numbered view, the tables beside or under
    // it, the rest continuing on table-only sheets. `spec.draw(area)`
    // paints the map into the area and returns the rect it used.
    _bMapSheets(book, spec, blocks) {
        const L = this._bLayout(book, blocks, true);
        const view = ++book.views;
        this._bPage(book, { ...spec, view, layout: L.kind, cols: L.cols }, (page) => {
            const used = spec.draw(L.mapArea) || L.mapArea;
            this._bViewBubble(book, view, spec.viewName, L.mapArea.x + 20, used.y + used.h + 8);
            this._bDrawLayout(book, L);
        });
        let rest = L.pack.rest;
        while (rest.length) {
            const C = this._bLayout(book, rest, false);
            this._bPage(book, { ...spec, title: `${spec.title} (cont.)`, sheetTitle: `${spec.sheetTitle} (CONT.)`,
                                layout: C.kind, cols: C.cols },
                        () => this._bDrawLayout(book, C));
            rest = C.pack.rest;
        }
    }

    // The view's bubble under its map: a circle with the number, the name
    // in caps over a short rule beside it.
    _bViewBubble(book, number, name, x, y) {
        const ctx = book.ctx;
        const r = 34;
        const cx = x + r, cy = y + r + 4;
        ctx.strokeStyle = INK;
        ctx.lineWidth = 3;
        ctx.setLineDash([]);
        ctx.beginPath();
        for (let i = 0; i <= 36; i++) {
            const a = i / 36 * Math.PI * 2;
            const px = cx + r * Math.cos(a), py = cy + r * Math.sin(a);
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.stroke();
        this._bText(book, String(number), cx, cy + 11, { size: SZ.viewNumber, weight: 700, align: 'center' });
        const nx = cx + r + 22;
        const label = this._bText(book, name, nx, cy + 2, { size: SZ.view, weight: 700, upper: true });
        const ctxM = book.measureCtx;
        ctxM.font = this._bFont(SZ.view, 700);
        const ruleW = Math.max(240, Math.ceil(ctxM.measureText(label).width) + 40);
        ctx.fillStyle = INK;
        ctx.fillRect(nx, cy + 12, ruleW, 3);
        if (book.log && book.page && book.page.painting) {
            book.log.bubble = { number, name: label, x: cx, y: cy, r };
        }
    }

    // ---- the map ------------------------------------------------------------

    // The screen's map through the canvas renderer, in exportMode, in the
    // binder's palette, with the screen-name plate off (the title block
    // names the screen; the plate sat over the circuit labels), onto an
    // offscreen canvas that is then laid into the sheet's map area.
    // Returns the sheet geometry - where a processor-coord rect of this
    // layer lands on the sheet - so the rulers and the brackets can be
    // drawn around it in sheet space. `area` is { x, y, w, h }: the wall
    // scales uniformly to fit it between the gutters (capped at
    // MAP_ZOOM_CAP) and the area actually used comes back as geo.area.
    //
    // Print density: the offscreen canvas is book.scale times the map's
    // sheet size and the renderer draws at book.scale times the zoom, so
    // the wall's text and lines come out sharp when the bitmap is laid
    // onto the scaled sheet - not upscaled from a 1x render.
    _bMap(book, layer, view, area) {
        const r = window.canvasRenderer;
        const S = book.scale || 2;
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
            h: (Number.isFinite(area.h) ? area.h : Infinity) - MAP_GUTTER.top - MAP_GUTTER.bottom,
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
            const ww = Math.max(1, wall.w), wh = Math.max(1, wall.h);
            // One zoom for both axes - the wall is never scaled
            // non-uniformly: it fits the area, and never past the cap.
            const zoom = Math.min(inner.w / ww, inner.h / wh, MAP_ZOOM_CAP);
            const drawW = wall.w * zoom, drawH = wall.h * zoom;
            const used = { x: area.x, y: area.y, w: area.w,
                           h: Math.round(drawH + MAP_GUTTER.top + MAP_GUTTER.bottom) };
            const ox = inner.x + (inner.w - drawW) / 2;      // wall's sheet origin
            const oy = inner.y;
            const toPage = (lx, ly) => ({ x: ox + (lx - wall.x) * zoom, y: oy + (ly - wall.y) * zoom });
            geo = {
                zoom, wall: { x: ox, y: oy, w: drawW, h: drawH }, mirrored, area: used,
                rect: (px, py, pw, ph) => {
                    const l = local(px, py, pw, ph);
                    const p = toPage(l.x, l.y);
                    return { x: p.x, y: p.y, w: l.w * zoom, h: l.h * zoom };
                },
            };
            if (book.page && book.page.painting) {
                if (book.log) book.log.map = { ...geo.wall, zoom, area: { ...used } };
                const off = this._binderMapCanvas || (this._binderMapCanvas = document.createElement('canvas'));
                off.width = Math.max(1, Math.round(used.w * S));
                off.height = Math.max(1, Math.round(used.h * S));
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
                // The renderer draws at S times the sheet zoom (its world
                // transform is zoom and pan alone, so a scaled context
                // would not survive it); the wall's local origin lands at
                // (ox - area.x, oy - area.y) in sheet units.
                r.zoom = zoom * S;
                r.panX = ((ox - area.x) - (ws.wx + wall.x) * zoom) * S;
                r.panY = ((oy - area.y) - (ws.wy + wall.y) * zoom) * S;
                r.render();
                // Laid at the map's sheet size: on the scaled sheet that is
                // one offscreen pixel per sheet pixel.
                book.ctx.drawImage(off, area.x, area.y, used.w, used.h);
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

    // The brackets outside the wall: one per soca / L21-30 on the screen,
    // spanning the rows its circuits feed, on the side its circuits live,
    // labelled "SR1 · 125'" (the name and the home run - the band over the
    // circuits says the type).
    //
    // One bracket distance per side (2026-09-07, "why the socas on the
    // sides are offset"): a bracket steps out only when its row span truly
    // overlaps another's on the same side - two brackets that share an
    // edge (rows 1-6 over rows 7-11) sit at the same distance. A stepped
    // bracket takes the nearest free level. The text stays vertical,
    // centred on the span.
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
            // A real overlap is more than a shared edge: the spans must
            // cross by more than a hairline.
            const crosses = (a, b) => Math.min(y2, b) - Math.max(y1, a) > 4;
            let depth = 0;
            while (stack.some(s => s.depth === depth && crosses(s.y1, s.y2))) depth++;
            stack.push({ y1, y2, depth });
            const dir = side === 'R' ? 1 : -1;
            const x = side === 'R'
                ? geo.wall.x + geo.wall.w + 44 + depth * 78
                : geo.wall.x - 74 - depth * 78;
            const ya = y1 + 3, yb = y2 - 3;
            if (book.log && book.page && book.page.painting) {
                (book.log.brackets || (book.log.brackets = []))
                    .push({ name: box.name, side, depth, x, y1, y2 });
            }
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

    // ---- the screen sheets --------------------------------------------------

    _bScreenPage(book, layer, pos, view) {
        const scr = book.list.byScreen[layer.id];
        const word = view === 'power' ? 'POWER' : 'DATA';
        const title = `${layer.name} - ${view === 'power' ? 'Power' : 'Data'}`;
        const sheetTitle = `${layer.name} · ${word}`;
        const blocks = view === 'power'
            ? this._bPowerBlocks(book, layer, scr)
            : this._bDataBlocks(book, layer, scr);
        this._bMapSheets(book, {
            kind: view, title, sheetTitle, viewName: sheetTitle,
            layerId: layer.id, subject: layer.name, position: pos.name,
            draw: (area) => {
                const geo = this._bMap(book, layer, view === 'power' ? 'power' : 'data-flow', area);
                if (!geo) return null;
                this._bRulers(book, layer, geo);
                if (view === 'power') this._bBoxBrackets(book, layer, scr, geo);
                return geo.area;
            },
        }, blocks);
    }

    // The band over a soca's circuits: "SR 1 · Soca 208 · 125' home run
    // · 6 circuits", plus the circuits on it that belong to another screen.
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
                parts.push(`circuits ${this._fmtTails(legs)} · ${other.name}`);
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
        // Circuits, banded per soca / L21-30; NO. is the circuit's number
        // on its unit (the band says which).
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
            cols: [{ title: 'circuit', w: 1.5 }, { title: 'no.', w: 0.6, align: 'right' },
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

    // What a sheet calls a breakout box: "CVT4K-S SR" - the model and the
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

    // The processor and card a socket sits on, for the data sheet's bands.
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

    // A card by id as a sheet names it: the name somebody typed, else its
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
            let primary = '—', backup = '—', b, bb = null;
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
                bb = (home.port && home.port.backedBy) || null;
                if (bb) backup = this._bBackupText(layer, run.num, bb);
            } else {
                b = band('none', 'Not placed');
            }
            // HOME RUN says both ends where there are two: the primary's
            // run, then the backup's, as the backup card's or box's own ≡
            // sheet typed it ("SR Primary 150' / SR Backup 150'"; a side
            // with nothing reads "—"). One end alone reads alone.
            const backupCable = bb && typeof this.dataPortCable === 'function'
                ? this.dataPortCable(bb.cardId, bb.port) : null;
            const homeRun = bb
                ? `${this.runText(cable)} / ${this.runText(backupCable)}`
                : this.runText(cable);
            b.rows.push({ cells: [run.label, primary, backup, this._bNum((run.panels || []).length, 0),
                                  this._bNum(px, 0), homeRun] });
        }
        const rows = [];
        for (const b of bands.values()) { rows.push({ band: b.text }); rows.push(...b.rows); }
        // PORT takes the width its longest label needs, whole - "SR A-1"
        // was cut to "SR A…" at a fixed share (2026-09-07) - measured
        // against the tables' column, and never under its old share; the
        // other columns divide the rest.
        const otherW = 1.6 + 2.0 + 0.9 + 0.9 + 2.0;
        const colW = DATA_COL_W;
        const ctxM = book.measureCtx;
        ctxM.font = this._bFont(SZ.cell, 400);
        const labelW = runs.reduce((m, run) => Math.max(m, ctxM.measureText(String(run.label || '')).width), 0);
        const needW = Math.ceil(labelW) + 12 * 2 + 4;
        const portW = Math.max(0.7, needW < colW ? needW * otherW / (colW - needW) : 0.7);
        blocks.push({ minW: DATA_COL_W, lines: this._bTableLines(book, {
            title: 'Ports',
            // PRIMARY and BACKUP carry whole names - "SR-1R · H9 BACKUP SR ·
            // 1" - and HOME RUN both ends' runs - "SR Primary 150' / SR
            // Backup 150'" - so they take most of the width and shrink
            // before they cut.
            cols: [{ title: 'port', w: portW }, { title: 'primary', w: 1.6 }, { title: 'backup', w: 2.0 },
                   { title: 'panels', w: 0.9, align: 'right' }, { title: 'px', w: 0.9, align: 'right' },
                   { title: 'home run', w: 2.0 }],
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

    // ---- the overview (1.1) -------------------------------------------------

    // The show map as view 1 across the drawing area's width, the
    // POSITIONS, SHOW TOTALS and CONTENTS tables in the top-left over it
    // the way their inventory tables sit. The tables take at most half the
    // height (what does not fit is cut - the overview never continues,
    // the contents naming every sheet must stay on it).
    _bOverviewPage(book) {
        const list = book.list;
        const rows = list.positions.map(pos => {
            // A position's own screens with their counts; a device-only
            // position (a beach a distro or box sits on, no screen of its
            // own) names the screens whose gear was pulled onto it.
            const ownIds = pos.memberIds || pos.layerIds;
            const members = ownIds.map(id => book.layers.get(String(id))).filter(Boolean);
            const pulled = pos.layerIds.filter(id => !ownIds.includes(id))
                .map(id => book.layers.get(String(id))).filter(Boolean);
            const scrs = ownIds.map(id => list.byScreen[id]).filter(Boolean);
            const circuits = scrs.reduce((s, x) => s + (x.boxes || []).reduce((a, b) => a + (b.circuits || []).length, 0), 0);
            const ports = scrs.reduce((s, x) => s + (x.ports || []).length, 0);
            const screens = members.length ? members.map(l => l.name).join(', ')
                : (pulled.length ? `gear for ${pulled.map(l => l.name).join(', ')}` : 'no screens');
            return { cells: [pos.name, screens, members.length ? String(circuits) : '—',
                             members.length ? String(ports) : '—'] };
        });
        const blocks = [];
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Positions',
            cols: [{ title: 'position', w: 1 }, { title: 'screens', w: 1.6 },
                   { title: 'circuits', w: 0.6, align: 'right' }, { title: 'ports', w: 0.5, align: 'right' }],
            rows,
        }) });
        // The show's totals.
        const screens = (this.project.layers || []).filter(l => (l.type || 'screen') === 'screen');
        let panels = 0, watts = 0, circuits = 0, ports = 0;
        for (const l of screens) {
            const f = this._bScreenFacts(l);
            panels += f.active; watts += f.watts;
            const scr = list.byScreen[l.id];
            if (scr) {
                circuits += (scr.boxes || []).reduce((a, b) => a + (b.circuits || []).length, 0);
                ports += (scr.ports || []).length;
            }
        }
        const distros = (typeof this.getDistros === 'function') ? this.getDistros() : [];
        const procs = this._processorsResolved || [];
        blocks.push({ lines: this._bKvLines(book, 'Show totals', [
            ['Screens', String(screens.length)],
            ['Panels', this._bNum(panels, 0)],
            ['Circuits', String(circuits)],
            ['Ports', String(ports)],
            ['Load', `${this._bNum(watts / 1000, 1)} kW`],
            ['Distros', String(distros.length)],
            ['Processors', String(procs.length)],
        ]) });
        // The contents: every sheet of the set, from the plan the dry pass
        // made (a dry pass has none yet and lists nothing).
        const contents = (book.plan || []).map(p => ({ cells: [p.number, p.sheetTitle] }));
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Contents',
            cols: [{ title: 'sheet', w: 0.4 }, { title: 'title', w: 1.6 }],
            rows: contents.length ? contents : [{ cells: ['', ''] }],
        }) });
        const da = book.geo.da;
        const across = Math.max(1, Math.floor((da.w + COL_GAP) / (COL_W + COL_GAP)));
        const wide = (da.w - (across - 1) * COL_GAP) / across;
        // The tables take half the height - up to 65% where the contents
        // is long - and, where the sheet has a column for each, sit side
        // by side the way their inventory tables do; on a narrower sheet
        // they pack as they fit.
        const contentsH = blocks[2].lines.reduce((s, l) => s + l.h, 0);
        const colH = Math.min(Math.max(Math.floor(da.h * 0.5), contentsH), Math.floor(da.h * 0.65));
        const pack = across >= blocks.length
            ? { cols: blocks.map(b => this._bPack([b], colH, 1).cols[0]).filter(Boolean), rest: [] }
            : this._bPack(blocks, colH, across);
        const tablesH = pack.cols.reduce((m, c) => Math.max(m, c.h), 0);
        const L = { kind: 'overview', cols: across, colW: wide, top: da.y, pack,
                    colX: (i) => da.x + i * (wide + COL_GAP) };
        const mapArea = { x: da.x, y: da.y + tablesH + (tablesH ? COL_GAP : 0), w: da.w,
                          h: da.h - tablesH - (tablesH ? COL_GAP : 0) - BUBBLE_H };
        const view = ++book.views;
        this._bPage(book, { kind: 'overview', title: 'Overview', sheetTitle: 'OVERVIEW', viewName: 'OVERVIEW',
                            subject: book.meta.show, view, layout: 'overview', cols: across }, () => {
            this._bDrawLayout(book, L);
            const used = this._bShowMap(book, mapArea) || mapArea;
            this._bViewBubble(book, view, 'OVERVIEW', mapArea.x + 20, used.y + used.h + 8);
        });
    }

    // The show at a glance: the Show Look, cropped to the SCREENS' bounds
    // (every screen on a visible canvas), fitted into the area at
    // min(fit, 3x) - through the renderer in exportMode, at book.scale
    // like the maps, so it prints sharp. Returns the rect it used.
    _bShowMap(book, area) {
        const r = window.canvasRenderer;
        const S = book.scale || 2;
        const canvases = (this.project && Array.isArray(this.project.canvases)) ? this.project.canvases : [];
        const shown = canvases.filter(c => c && c.visible !== false);
        const saved = { canvas: r.canvas, ctx: r.ctx, exportMode: r.exportMode, transparent: r.exportTransparentBg,
                        printer: r.printerMode, viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY };
        let used = null;
        try {
            r.viewMode = 'show-look';
            let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
            const screens = (this.project.layers || []).filter(l => (l.type || 'screen') === 'screen' && l.visible !== false);
            for (const layer of screens) {
                const cid = (layer.show_canvas_id || layer.canvas_id) || null;
                const canvas = canvases.find(c => c && c.id === cid) || null;
                if (canvases.length && (!canvas || canvas.visible === false)) continue;
                const ws = r._canvasWorkspace(canvas);
                const b = r.getLayerBounds(layer);
                const { dx, dy } = r.getLayerRenderOffset(layer);
                x1 = Math.min(x1, ws.wx + b.x + dx); y1 = Math.min(y1, ws.wy + b.y + dy);
                x2 = Math.max(x2, ws.wx + b.x + dx + b.width); y2 = Math.max(y2, ws.wy + b.y + dy + b.height);
            }
            if (!Number.isFinite(x1)) {
                if (shown.length) {
                    for (const c of shown) {
                        const ws = r._canvasWorkspace(c);
                        x1 = Math.min(x1, ws.wx); y1 = Math.min(y1, ws.wy);
                        x2 = Math.max(x2, ws.wx + (c.show_raster_width || c.raster_width || 0));
                        y2 = Math.max(y2, ws.wy + (c.show_raster_height || c.raster_height || 0));
                    }
                } else {
                    x1 = 0; y1 = 0; x2 = r.rasterWidth || 1920; y2 = r.rasterHeight || 1080;
                }
            }
            // a little air around the screens
            const air = Math.max(8, 0.02 * Math.max(x2 - x1, y2 - y1));
            x1 -= air; y1 -= air; x2 += air; y2 += air;
            const w = Math.max(1, x2 - x1), h = Math.max(1, y2 - y1);
            const zoom = Math.min(area.w / w, area.h / h, MAP_ZOOM_CAP);
            const drawW = Math.max(1, Math.round(w * zoom)), drawH = Math.max(1, Math.round(h * zoom));
            const dx = area.x + (area.w - drawW) / 2, dy = area.y;
            used = { x: dx, y: dy, w: drawW, h: drawH, zoom };
            if (book.log) book.log.map = { x: dx, y: dy, w: drawW, h: drawH, zoom, area: { ...area } };
            if (!(book.page && book.page.painting)) return used;
            const off = this._binderMapCanvas || (this._binderMapCanvas = document.createElement('canvas'));
            off.width = drawW * S;
            off.height = drawH * S;
            r.canvas = off;
            r.ctx = off.getContext('2d', { alpha: true });
            r.exportMode = true;
            r.exportTransparentBg = true;
            r.printerMode = book.meta.palette === 'printer';
            r.zoom = zoom * S;
            r.panX = -x1 * zoom * S;
            r.panY = -y1 * zoom * S;
            r.render();
            book.ctx.fillStyle = '#f4f4f4';
            book.ctx.fillRect(dx, dy, drawW, drawH);
            book.ctx.drawImage(off, dx, dy, drawW, drawH);
            book.ctx.strokeStyle = RULE;
            book.ctx.lineWidth = 2;
            book.ctx.setLineDash([]);
            book.ctx.strokeRect(dx, dy, drawW, drawH);
        } finally {
            r.canvas = saved.canvas; r.ctx = saved.ctx; r.exportMode = saved.exportMode;
            r.exportTransparentBg = saved.transparent; r.printerMode = saved.printer;
            r.viewMode = saved.viewMode; r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
        }
        return used;
    }

    // ---- the position pull sheets (4.n) -------------------------------------

    _bPullPage(book, pos, members) {
        const title = `${pos.name} - Pull`;
        this._bTableSheets(book, { kind: 'pull', title, sheetTitle: `${pos.name} · PULL`, subject: pos.name },
                           this._bPullBlocks(book, pos, members));
    }

    _bPullBlocks(book, pos, members) {
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
        // Hardware: the socas, the distros, the cards these screens hang on.
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
        return blocks;
    }

    // ---- hardware sheets (5.n) ----------------------------------------------

    _bDistroPage(book, d) {
        const title = `${d.name} - Distro`;
        const load = (typeof this.getDistroLoads === 'function')
            ? this.getDistroLoads().find(x => x.id === d.id) : null;
        const numbers = (typeof this._distroMultiNumbers === 'function') ? this._distroMultiNumbers(d.id) : new Map();
        const boxes = [];
        const byType = new Map();       // type name -> how many on this distro
        let allCircuits = 0;
        for (const number of [...numbers.keys()].sort((a, b) => a - b)) {
            const members = numbers.get(number) || [];
            const typed = this.distroBoxType(d, number, members).type;
            if (typed) byType.set(typed.name, (byType.get(typed.name) || 0) + 1);
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
            allCircuits += circuits;
            boxes.push({ cells: [`${d.name} ${number}`, typed ? typed.name : '—',
                                 homeRun ? this.pullLengthText(homeRun) : 'no length',
                                 names.join(' + '), String(circuits), this._bNum(amps, 1)] });
        }
        // The table is named by what it lists - "4 Soca 208 · 1 L21-30" -
        // the units by their types, no generic noun (2026-09-07, "no need
        // to call it a breakout").
        const counts = [...byType.entries()].map(([name, n]) => `${n} ${name}`).join(' · ')
            || 'nothing on this distro';
        if (!boxes.length && !load) return;
        this._bTableSheets(book, { kind: 'distro', title, sheetTitle: `${d.name} · DISTRO`, subject: d.name },
                           this._bDistroBlocks(book, d, load, boxes, counts, allCircuits));
    }

    _bDistroBlocks(book, d, load, boxes, counts, allCircuits) {
        const blocks = [];
        blocks.push({ lines: this._bTableLines(book, {
            title: counts,
            cols: [{ title: 'name', w: 0.8 }, { title: 'type', w: 0.9 }, { title: 'home run', w: 0.8 },
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
        pairs.push(['Circuits', boxes.length ? `${allCircuits} on ${counts}` : 'none']);
        blocks.push({ lines: this._bKvLines(book, 'Service', pairs) });
        const hw = (book.list.hardware || []).find(h => h.kind === 'distro' && h.id === d.id);
        blocks.push({ lines: this._bPullLines(book, 'Pull list', (hw && hw.rows) || []) });
        return blocks;
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
        const title = `${procTitle} - Processor`;
        const cards = (proc.slots || []).filter(s => s && s.card).map(s => ({ slot: s.index, card: s.card }));
        if (!cards.length) return;
        this._bTableSheets(book, { kind: 'processor', title, sheetTitle: `${procTitle} · PROCESSOR`, subject: procTitle },
                           this._bProcessorBlocks(book, proc, cards));
    }

    _bProcessorBlocks(book, proc, cards) {
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
                // A socket's own entry: its home run where it is loose
                // ('cable'), its EXTENSION off the snake it rides where it
                // is snaked ('ext', the snake's name in the last column).
                for (const [socket, c] of Object.entries(o.rec.portCables || {})) {
                    const ft = Number(c && c.ft);
                    if (!Number.isFinite(ft) || ft <= 0) continue;
                    const connId = this.dataPortConnectorId({ rec: o.rec }, c.connector);
                    const snake = (o.rec.snakes || []).find(s => (s.ports || []).includes(parseInt(socket, 10)));
                    if (snake) {
                        runs.push({ cells: [`${o.title} ${socket}`, 'ext', this.pullLengthText(ft),
                                            snake.name || 'snake'] });
                        continue;
                    }
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
        return blocks;
    }

    // ---- the totals sheet (5.last) ------------------------------------------

    _bTotalsPage(book) {
        const blocks = [{ lines: this._bPullLines(book, 'Pull list', book.list.totals || []) }];
        const notes = (book.list.unmodelled || []).map(t => ({ cells: [t] }));
        if (notes.length) {
            blocks.push({ lines: this._bTableLines(book, { title: 'Notes', cols: [{ title: '', w: 1 }], rows: notes }) });
        }
        this._bTableSheets(book, { kind: 'totals', title: 'Pull list - all positions',
                                   sheetTitle: 'PULL LIST · ALL POSITIONS', subject: 'All positions' }, blocks);
    }
}

for (const k of Object.getOwnPropertyNames(_Binder.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Binder.prototype, k));
    }
}
