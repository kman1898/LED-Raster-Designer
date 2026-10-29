// app-binder: the binder packet - a DRAWING SET. The show's power and data
// maps, the pull tables and the hardware, laid out on numbered SHEETS the
// way a Vectorworks drawing set reads (2026-09-08, on a client packet he
// held up: "this is a great example to base our binder off of"): every
// sheet a landscape page of one size - Tabloid 17 x 11 by default ("17x11
// i think is great . nice middle gound. but maybe have option for all
// sizes") - with a thin border, a TITLE BLOCK column down its right edge
// ("mimic whats in their drawing": the logo when one is set, REVISIONS -
// the log the exports write - the show / venue / dates, Designer, Project
// Manager, Drafter, Engineer, the SHEET TITLE, the Sheet Number, the
// drawing date)
// and the drawing area to its left holding a numbered VIEW - the map with
// its bubble ("1  OVERVIEW") - and the sheet's tables.
//
// Sheets number by SERIES, by subject ("Series by subject"), the screens
// in BEACH order (2026-09-08: "Power then data for one screen, right after
// each other … then order them by beach so SR beach screens first"):
//   1.1  Overview - the show map as view 1, POSITIONS / SHOW TOTALS / CONTENTS
//   2.n  the SCREENS: in the pull list's position order, a position's own
//        screens in the SCREEN ORDER the project keeps (project.binder
//        .screenOrder, the export dialog's "Screen order" - alphabetical
//        unless picked: "i'd want raster A first, then in alphabetical
//        order"; or the Screens panel's order either way, or by first
//        port, or by first circuit - _bOrderScreens), each screen's POWER
//        sheet (the map with rulers and brackets; CIRCUITS / CABLES THIS
//        SCREEN / FACTS / GANGS) and its POWER WIRING sheet, then its DATA
//        sheet (PORTS / CABLES / FACTS) and its DATA WIRING sheet - grouped
//        by system, each wiring sheet right behind the map it wires
//        (app-binder-wiring.js: the wall over the devices its circuits or
//        its ports land on, circuit to breakout, port to socket, one side
//        on a whole page) - a screen with only one side has only that
//        side's two sheets
//   3.n  the PULL sheets - positions side by side, each position's
//        sections flowing across the sheet in columns
//   4.n  hardware - the services, then the distros side by side, then
//        the processors with the show's pull list beside them where it fits
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
// Layout inside the drawing area - COVERAGE DECIDES (_bMapLayout, 2026-
// 09-08: "there is still a ton of wasted space … screens can enlarge and
// text can be bigger if it fills the space. only get this small when
// there is tons of info"): a map sheet is tried both ways - the map left
// and the tables right in one column (side), the map on top and the
// tables under it side by side (stack). THE WALL COMES FIRST (2026-09-20,
// "power is the size a wall of this size should be"): in each layout the
// map takes the zoom it gets with the tables at 1 (min(fit, 3x), never
// under 45 % of the width beside them, of the height over them), and the
// TABLES' type scale s, 1 to FILL_CAP, grows only while that costs the
// map nothing - so a screen's Power and Data sheets draw the same wall
// the same size however long their tables are. The layout with the
// larger wall wins; within 3 per cent, the one that covers more of the
// drawing area - the wall with its gutters plus the tables' box. The tables,
// their bands, the FACTS and the view bubble are painted at s (base
// sizes below, the context scaled, the recorder writing the scaled page
// units so the PDF matches); the map's rulers and brackets keep their
// inch sizes and the renderer's own labels grow with the wall. A sheet
// whose tables fit at 1 in neither layout is "tons of info": it stays at
// 1, the map over the tables, and continues on the next sheet. Column
// sheets (pull, hardware) spread their tables across the width and scale
// as a whole (_bFillScale; the pull sheets choose their columns to that
// end, _bPullSheets). The title block never scales.
//
// Every figure is read from buildPullSheet (app-pull-list.js) and the same
// authorities the canvas reads; nothing is recomputed here. The title
// block's fields live in project.binder (venue, dates, designer, project
// manager, drafter, revisions - the export dialog edits them, one undo
// entry per field; a revision is LOGGED ON EXPORT, 2026-09-08: an export
// at a rev no row carries yet adds a row - and, 2026-10-17, as soon as a
// new Rev is committed in the dialog) and in preferences (the sheet
// size, the logo, and the engineer's name, which prints as Engineer and
// stands in for a blank Drafter).
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
const SZ = { h4: 25, cell: 24, th: 21, foot: 22, ruler: 22, bracket: 28, group: 30,
             tbLabel: 26, tbCell: 22, tbSmall: 20, tbShow: 30, tbTitle: 32, tbNumber: 56,
             view: 26, viewNumber: 30 };
const ROW_H = 38;
// A list cell that will not fit its column wraps: up to LIST_LINES lines,
// LIST_H apart inside the row, and then it says how many more.
const LIST_H = 30;
const LIST_LINES = 3;
const BAND_H = 46;
const WRAP_WHOLE = 12;                // a wrap layout never splits a block this short (lines)
const WRAP_GAIN = 1.1;                // wrap wins only with a wall this much larger than side's or stack's
const TH_H = 40;
const H4_H = 46;
const BLOCK_GAP = 22;
// The tables' column: 3.5 in wide, a gap between columns; a view's bubble
// takes this much under its map.
const COL_W = 700;
// A fiber strand's swatch (its color, a square this big) and the room it
// takes in front of the strand's name, the gap after it included - sized
// to read across a room (2026-10-17: "bigger, bolder color").
const SWATCH = 24;
// AN INPUT AND ITS STRANDS AS ONE GROUP (owner, 2026-10-17): the input's
// label centred beside its strands, a thin outline round the lot, GROUP_GAP
// between one input's outline and the next.
const GROUP_GAP = 10;
const GROUP_PAD = 6;
const SWATCH_W = 32;
const DATA_COL_W = 1020;              // the widest the Ports table grows, its columns sized to their content
const COL_GAP = 30;
const BUBBLE_H = 96;
// The map keeps at least this share of the drawing area whatever the
// tables' scale - of the width beside them, of the height over them.
const MAP_MIN_FRAC = 0.45;
// The map's gutters: the rulers' and the brackets' room around the wall.
// TWO rulers live above the wall, not one: the map draws its own leg ruler
// and its multi band pill into the bitmap, and the binder draws its column
// ruler on the sheet over the same strip. They fought, and the binder's
// bold column number printed inside the band pill - "S1-1 - 250 - 65.8A"
// read "S1-4" on a real export. _bRulers now stands its ruler above
// whatever the map put down, rather than the gutter growing for both:
// growing it moved every map on every sheet and broke the approved fill.
const MAP_GUTTER = { left: 200, right: 180, top: 74, bottom: 16 };
// The sheet the column ruler needs above the map's own lettering:
// its tick, and its numbers over that.
const COL_RULER_H = 34;
const MAP_ZOOM_CAP = 3;               // a tiny wall never blows up past 3x
// The fill: a sheet's drawing scales up to this to fill its area.
const FILL_CAP = 2.4;
// A long table may take this much of the wall's best size to reach the foot
// of the sheet (_bMapLayout's side layout); a short one takes nothing.
const FILL_KEEP = 0.9;
// A column sheet's subject head - the position's, the distro's name over
// its tables - and the pull sheets' columns: at least PULL_COL_W (cable ·
// len · qty · label are short columns), as wide as a table needs to print
// whole up to PULL_COL_MAX (_bPullBlock).
const GROUP_H = 60;
const PULL_COL_W = 660;
const PULL_COL_MAX = 1100;
// A pull sheet whose lists all print on one line wins over a larger print
// that wraps them, down to this share of that print's size.
const PULL_WHOLE_KEEP = 0.85;

// Cable types print in the GEAR LIST's own vocabulary - the same words the
// workbook export writes - so the binder's Cables table and the pull sheet
// agree row for row. The word the user retired was "Multi" as the name of
// the THING the circuits come out of (that is named by its type); the
// multi CABLE keeps its shop name, and "Tru-1 Breakout" stays the pull
// list's CABLE item.
const BINDER_TYPE_WORDS = {};

// The redundancy bar's own words (app-processors.js), so the page reads
// what the tray reads: "Per card", "Backed up → MX20 B", "Off".
const REDUNDANCY_WORDS = {
    off: 'Off', port: 'Per port', card: 'Per card', unit: 'Backed up',
    fixed: 'On', backup: 'Backed up',
};

// The title block's fields, as project.binder stores them - and the
// screen order and the VIEW, which ride the project the same way.
const BINDER_DEFAULTS = {
    venue: '', dates: '', designer: '',
    projectManager: { name: '', phone: '', email: '' },
    drafter: '', revisions: [], screenOrder: 'alpha', view: 'front',
    // a grouped wall whose tab says Both on the Names switch: the export's
    // answer per group and side, { [groupId]: { power, data } }, each
    // 'group' or 'screens' (absent = group)
    groupSheets: {},
};
// The side the set's Power and Data maps are drawn from (project.binder
// .view, the export dialog's "View"): ONE choice for the whole set, every
// screen sheet naming it - "· FRONT VIEW" / "· REAR VIEW" (owner,
// 2026-09-23: "Print both"). The overview is always the front ("the only
// screen that will show front always is the overview screen the very
// first page"). Absent = front.
const BINDER_VIEWS = ['front', 'rear'];
// The renderer's word for each: a canvas's data_flow_perspective /
// power_perspective is 'front' or 'back'.
const VIEW_PERSPECTIVE = { front: 'front', rear: 'back' };
const PERSPECTIVE_KEYS = ['data_flow_perspective', 'power_perspective'];
// The orders a beach's screens can run in (project.binder.screenOrder,
// the export dialog's "Screen order"): alphabetical by name, the Screens
// panel's order top-down or bottom-up, by first port, by first circuit.
const SCREEN_ORDERS = ['alpha', 'layers', 'layers-up', 'data', 'power'];
// The logo is stored no larger than this on its long side.
const LOGO_MAX_PX = 1200;
const SERIES = { overview: 1, power: 2, data: 2, wiring: 2, rigging: 2, pull: 3,
                 service: 4, distro: 4, processor: 4, totals: 4 };

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
        // The border and the title block column, remembered like the sheet
        // size.
        const block = document.getElementById('export-binder-title-block');
        if (block) {
            block.addEventListener('change', () => {
                this.setBinderTitleBlock(block.checked);
                if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
            });
        }
        // The screen order: project state, one undo entry, the same POST
        // as the title block's fields.
        const order = document.getElementById('export-binder-screen-order');
        if (order) {
            order.addEventListener('change', () => {
                const v = SCREEN_ORDERS.includes(order.value) ? order.value : 'alpha';
                this.setBinderField('screenOrder', v, 'Set Screen Order');
                if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
            });
        }
        // The view: project state, one undo entry, the same POST as the
        // title block's fields - the radios both commit the one field.
        for (const v of BINDER_VIEWS) {
            const radio = document.getElementById(`export-binder-view-${v}`);
            if (!radio) continue;
            radio.addEventListener('change', () => {
                if (!radio.checked) return;
                this.setBinderField('view', v, 'Set Binder View');
                if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
            });
        }
        const eng = document.getElementById('export-binder-engineer');
        if (eng) eng.addEventListener('change', () => { this.setEngineerName(eng.value); this.syncBinderControls(); });
        // The Rev commits on change (blur or Enter), never per keystroke:
        // typing "1.1" logs 1.1, not "1." on the way (commitBinderRev).
        const rev = document.getElementById('export-binder-rev');
        if (rev) {
            rev.addEventListener('change', () => {
                this.commitBinderRev(rev.value);
                this.syncBinderControls();
                if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
            });
        }
        const revNote = document.getElementById('export-binder-revision-note');
        if (revNote) revNote.addEventListener('change', () => { this.noteBinderRevision(revNote.value); });
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
        // A Both group's Group / Screens: saved as it is picked.
        const groups = document.getElementById('export-binder-groups');
        if (groups) {
            groups.addEventListener('click', (e) => {
                const btn = e.target && e.target.closest ? e.target.closest('.binder-group-btn') : null;
                const line = btn ? btn.closest('[data-group]') : null;
                if (!line) return;
                this.setBinderGroupSheet(line.dataset.group, btn.dataset.side, btn.dataset.mode);
                this._renderBinderGroupRows();
                if (typeof this.updateExportPreview === 'function') this.updateExportPreview();
            });
        }
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
        if (typeof this.syncCableUnitControls === 'function') this.syncCableUnitControls();
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
        // On open (openExportModal raises the flag): the palette, the
        // maps and the sheet ticks start from the Binder preferences, the
        // way the sheet size does. Ahead of the scope logic below, which
        // still unticks the show sheets for a single screen.
        if (this._binderSeedFromPrefs) {
            this._binderSeedFromPrefs = false;
            const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
            const tick = (id, on) => { const el = document.getElementById(id); if (el) el.checked = !!on; };
            const printer = prefs.binderPalette === 'printer';
            tick('export-binder-printer', printer);
            tick('export-binder-colour', !printer);
            const maps = prefs.binderMaps === 'power' || prefs.binderMaps === 'data' ? prefs.binderMaps : 'both';
            tick('export-binder-side-power', maps === 'power');
            tick('export-binder-side-data', maps === 'data');
            tick('export-binder-side-both', maps === 'both');
            tick('export-binder-cover', prefs.binderCover !== false);
            tick('export-binder-pull', prefs.binderPull !== false);
            tick('export-binder-hardware', prefs.binderHardware !== false);
            tick('export-binder-wiring', prefs.binderWiring !== false);
            tick('export-binder-rigging', prefs.binderRigging !== false);
        }
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
        const block = document.getElementById('export-binder-title-block');
        if (block) block.checked = this.getBinderTitleBlock();
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
        set('export-binder-screen-order', info.screenOrder);
        for (const v of BINDER_VIEWS) {
            const radio = document.getElementById(`export-binder-view-${v}`);
            if (radio) radio.checked = info.view === v;
        }
        const drafter = document.getElementById('export-binder-drafter');
        if (drafter) drafter.placeholder = this.getEngineerName() || 'Name';
        // the Revision note is this export's and stays as typed
        this._renderBinderRevisionRows();
        this._renderBinderGroupRows();
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
            empty.textContent = 'Nothing logged yet. A new Rev adds a row.';
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
            // the Wiring tick - one for both wiring sheets, each following
            // its own map through the Maps choice - is a SCREEN sheet's: on
            // whatever the scope
            wiring: on('export-binder-wiring', true),
            // the Header/Footer sheets - a screen's header and footer bars, one sheet per
            // screen that has any - on whatever the scope
            rigging: on('export-binder-rigging', true),
            // the border, the title block column and the rev line: on
            // unless the box says otherwise (a preference, so the dialog
            // opens the way it was left)
            titleBlock: on('export-binder-title-block', this.getBinderTitleBlock()),
            // a Both group's Group / Screens per side - the dialog's Groups
            // row saves each answer on the project as it is picked
            groupSheets: this.getBinderInfo().groupSheets,
        };
    }

    // The dialog's Groups row: one line per grouped wall whose Power or Data
    // tab says Both on the Names switch, routed as one on that side - "WALL
    // Data: [Group] [Screens]", both sides on the line where both ask. The
    // buttons show the saved answer, Group where there is none.
    _renderBinderGroupRows() {
        const box = document.getElementById('export-binder-groups');
        const row = document.getElementById('export-binder-groups-row');
        if (!box) return;
        box.innerHTML = '';
        const answers = this.getBinderInfo().groupSheets;
        let n = 0;
        for (const gp of this._bGroupPlans({ groupSheets: answers }).values()) {
            const sides = ['power', 'data'].filter(side => gp.asks[side]);
            if (!sides.length) continue;
            n++;
            const line = document.createElement('div');
            line.className = 'binder-group-row';
            line.dataset.group = String(gp.id);
            line.style.cssText = 'display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: center;';
            const name = document.createElement('span');
            name.className = 'binder-group-name';
            name.textContent = gp.name;
            name.style.cssText = 'flex: none; min-width: 60px; color: #ddd;';
            line.appendChild(name);
            for (const side of sides) {
                const part = document.createElement('span');
                part.style.cssText = 'display: flex; gap: 4px; align-items: center; flex: none;';
                const word = document.createElement('span');
                word.textContent = side === 'power' ? 'Power:' : 'Data:';
                part.appendChild(word);
                for (const mode of ['group', 'screens']) {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'btn btn-secondary binder-group-btn';
                    btn.dataset.side = side;
                    btn.dataset.mode = mode;
                    btn.textContent = mode === 'group' ? 'Group' : 'Screens';
                    btn.style.cssText = 'padding: 3px 8px; font-size: 11px;';
                    btn.classList.toggle('active', gp.mode[side] === mode);
                    btn.setAttribute('data-tooltip', mode === 'group'
                        ? `One ${side === 'power' ? 'Power' : 'Data'} sheet for ${gp.name}, every screen in it on one map.`
                        : `A ${side === 'power' ? 'Power' : 'Data'} sheet for each screen in ${gp.name}.`);
                    part.appendChild(btn);
                }
                line.appendChild(part);
            }
            box.appendChild(line);
        }
        if (row) row.style.display = n ? 'flex' : 'none';
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
    // The project's value wins where it has one; where it is blank the
    // PREFERENCE fills it (the Binder tab's designer, project manager,
    // drafter and screen order - the same shop show after show). The
    // venue and the dates are per show and have no preference.
    getBinderInfo() {
        const s = (v) => String(v == null ? '' : v);
        const stored = (this.project && this.project.binder && typeof this.project.binder === 'object')
            ? this.project.binder : {};
        const pm = (stored.projectManager && typeof stored.projectManager === 'object') ? stored.projectManager : {};
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        const fill = (v, pref) => s(v).trim() ? s(v) : s(pref);
        return {
            venue: s(stored.venue), dates: s(stored.dates),
            designer: fill(stored.designer, prefs.binderDesigner),
            projectManager: { name: fill(pm.name, prefs.binderPmName),
                              phone: fill(pm.phone, prefs.binderPmPhone),
                              email: fill(pm.email, prefs.binderPmEmail) },
            drafter: fill(stored.drafter, prefs.binderDrafter),
            screenOrder: SCREEN_ORDERS.includes(stored.screenOrder) ? stored.screenOrder
                : (SCREEN_ORDERS.includes(prefs.binderScreenOrder) ? prefs.binderScreenOrder : 'alpha'),
            // the set's one Front / Rear choice; absent (every project
            // before it, a new one) is front
            view: BINDER_VIEWS.includes(stored.view) ? stored.view : 'front',
            // the log: No. is the row's position; `rev` the number the
            // export wore, so the same rev exported again logs nothing
            revisions: Array.isArray(stored.revisions)
                ? stored.revisions.filter(r => r && typeof r === 'object')
                    .map((r, i) => ({ no: i + 1, rev: s(r.rev), date: s(r.date), by: s(r.by), description: s(r.description) }))
                : [],
            groupSheets: this._binderGroupSheets(stored.groupSheets),
        };
    }

    // The stored answers as the set reads them: only 'group' / 'screens'
    // per side survive, anything else is no answer.
    _binderGroupSheets(raw) {
        const out = {};
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return out;
        for (const [gid, v] of Object.entries(raw)) {
            if (!v || typeof v !== 'object') continue;
            const one = {};
            for (const side of ['power', 'data']) {
                if (v[side] === 'group' || v[side] === 'screens') one[side] = v[side];
            }
            if (Object.keys(one).length) out[gid] = one;
        }
        return out;
    }

    // The export dialog's answer for one group's side (2026-10-01: "if set
    // to both then ask per group"), saved with the project's binder
    // settings so the next export remembers it: one undo entry, the same
    // POST as the title block's fields. Returns true when it changed.
    setBinderGroupSheet(groupId, side, mode) {
        if (!this.project || !['power', 'data'].includes(side) || !['group', 'screens'].includes(mode)) return false;
        const all = this.getBinderInfo().groupSheets;
        if ((all[groupId] || {})[side] === mode) return false;
        all[groupId] = { ...(all[groupId] || {}), [side]: mode };
        if (!this.project.binder || typeof this.project.binder !== 'object') this.project.binder = {};
        this.project.binder.groupSheets = all;
        this.saveState('Set Group Sheets');
        this._persistBinderInfo();
        sendClientLog('binder_group_sheets_set', { groupId, side, mode });
        return true;
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

    // A row of the log: No., the rev it is for, today's date as M/D/YY,
    // the engineer's initials, the note.
    _binderRevisionRow(rev, note, no) {
        return { no, rev, date: this._binderToday(), by: this.binderInitials(this.getEngineerName()),
                 description: String(note == null ? '' : note).trim() };
    }

    // A NEW REV LOGS ITS ROW AS IT IS COMMITTED (2026-10-17: "when i
    // change the revision then in the revisions section a new part needs
    // to show in revisions"): the Rev field's change - blur or Enter, never
    // a keystroke - sets the rev and, where no row carries it yet, adds its
    // row (_binderRevisionRow, the Revision note as its description) in the
    // SAME undo entry, so one undo takes back the rev and its row together.
    // A rev that already has a row adds nothing; each rev is logged once.
    //
    // The note box then belongs to that row: committing the note writes it
    // into the row's description while the row is the newest and its rev
    // is still the Rev (noteBinderRevision). A note typed BEFORE the Rev is
    // committed is the new row's description; a note still mirroring the
    // previous rev's row is not carried onto the next one - the box clears
    // and the new row starts blank. Returns true when the rev changed.
    commitBinderRev(value) {
        if (!this.project) return false;
        const v = String(value == null ? '' : value).trim() || this.getPullSheetDefaults().rev;
        if (this.getPullSheetSettings().rev === v) return false;
        const list = this.getBinderInfo().revisions;
        const noteEl = document.getElementById('export-binder-revision-note');
        let note = noteEl ? String(noteEl.value || '').trim() : '';
        const open = this._binderOpenRevision();
        if (open && note && note === open.row.description) {
            note = '';
            if (noteEl) noteEl.value = '';
        }
        if (!this.project.pullSheet) this.project.pullSheet = {};
        this.project.pullSheet.rev = v;
        let row = null;
        if (!list.some(x => x.rev === v)) {
            row = this._binderRevisionRow(v, note, list.length + 1);
            if (!this.project.binder || typeof this.project.binder !== 'object') this.project.binder = {};
            this.project.binder.revisions = [...list, row];
        }
        this.saveState(row ? 'Log Revision' : 'Set Pull Sheet Revision');
        this._persistPullSheetSettings();
        if (row) {
            this._persistBinderInfo();
            this._binderRevOpen = { rev: v, project: this.project };
            this._renderBinderRevisionRows();
            sendClientLog('binder_revision_logged', { rev: v, no: row.no, by: row.by, on: 'rev' });
        }
        return true;
    }

    // The row the note box writes into: the one a Rev commit logged, while
    // it is the log's newest row, its rev is still the Rev, and the project
    // is the one it was logged in. Null otherwise.
    _binderOpenRevision() {
        const open = this._binderRevOpen;
        if (!open || open.project !== this.project) return null;
        const list = this.getBinderInfo().revisions;
        const index = list.length - 1;
        const row = list[index];
        if (!row || row.rev !== open.rev || this.getPullSheetSettings().rev !== open.rev) return null;
        return { row, index };
    }

    // The Revision note committed: into the open row's description (one
    // undo entry, as an edit in the list is). Otherwise it waits in the
    // box for the next new rev, or the export. Returns true when a row
    // changed.
    noteBinderRevision(note) {
        const open = this._binderOpenRevision();
        return open ? this.editBinderRevision(open.index, 'description', note) : false;
    }

    // Logged on export ("Logged on export", 2026-09-08): the rev the
    // dialog names, when no row carries it yet, becomes a row - today's
    // date as M/D/YY, the engineer's initials, the Revision note - with
    // one undo entry, persisted like every other field. The same rev
    // exported again logs nothing (a rev committed in the dialog already
    // has its row, commitBinderRev). Returns the row it added, or null.
    logBinderRevision(rev, note) {
        if (!this.project) return null;
        const r = String(rev == null ? '' : rev).trim();
        const list = this.getBinderInfo().revisions;
        if (list.some(x => x.rev === r)) return null;
        const row = this._binderRevisionRow(r, note, list.length + 1);
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

    // The first letter of each word of a name, upper-case: "Morgan Keller"
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

    // The border, the title block column and the rev line: a preference
    // too - a shop that prints plain sheets prints them every show. ON
    // unless it was stored off, so an app that has never seen the switch
    // keeps the sheet it has always had.
    getBinderTitleBlock() {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        return prefs.binderTitleBlock !== false;
    }

    setBinderTitleBlock(on) {
        return this._setBinderPreference('binderTitleBlock', on !== false);
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
        const r = await this.readBinderLogoDataUrl(file);
        if (r.error) {
            status(r.error);
            return false;
        }
        await this.setBinderLogo(r.dataUrl);
        status('');
        this.syncBinderControls();
        sendClientLog('binder_logo_set', { type: r.type, w: r.width, h: r.height, bytes: r.dataUrl.length });
        return true;
    }

    // The file read, checked and downscaled - what the export dialog
    // stores at once and the Preferences dialog holds until Save. Resolves
    // to { dataUrl, type, width, height } or { error }.
    async readBinderLogoDataUrl(file) {
        const type = String(file && file.type || '').toLowerCase();
        const name = String(file && file.name || '');
        if (type === 'image/svg+xml' || /\.svg$/i.test(name)) {
            return { error: 'SVG is not accepted: the PDF draws bitmaps. Save the logo as a PNG or JPEG.' };
        }
        if (type !== 'image/png' && type !== 'image/jpeg') {
            return { error: 'Pick a PNG or JPEG.' };
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
            return { error: 'That file could not be read as an image.' };
        }
        return { dataUrl: this._binderScaleLogo(img, type), type,
                 width: img.naturalWidth, height: img.naturalHeight };
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
            view: this.getBinderInfo().view,
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
    // sheetTitle, layerId, subject, layout, cols, scale, extent, names,
    // w, h }] - w, h the sheet in page pixels, `scale` the fill scale the
    // drawing area is painted at, `extent` the content's base extent
    // (page units before the scale), `names` the subjects a column sheet
    // carries.
    planBinder(opts) {
        const book = this._binderBook(opts || this.readBinderOptions(), { dry: true });
        return book.pages.map(p => this._bPlanEntry(book, p));
    }

    _bPlanEntry(book, p) {
        return { kind: p.kind, number: p.number, title: p.title, sheetTitle: p.sheetTitle,
                 view: p.view || null, layerId: p.layerId || null, subject: p.subject || null,
                 layout: p.layout, cols: p.cols || 0, scale: p.scale || 1,
                 extent: p.extent ? { w: p.extent.w, h: p.extent.h } : null,
                 coverage: Number.isFinite(p.coverage) ? Math.round(p.coverage * 1000) / 1000 : null,
                 names: p.names || null, sides: p.sides || null, halves: p.halves || null,
                 w: book.sheet.w, h: book.sheet.h, sheet: book.sheet.key,
                 // a grouped wall's sheet: its group and the screens it draws
                 ...(p.groupId != null ? { groupId: p.groupId, layerIds: p.layerIds || null } : {}) };
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
                 logo: log.logo || null, wiring: log.wiring || null,
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
            // the side the maps are drawn from: the project's choice; an
            // explicit opts.view (a caller with a set in hand) overrides it
            view: BINDER_VIEWS.includes(opts.view) ? opts.view : info.view,
        };
        const sheet = binderSheet(opts.sheet || this.getBinderSheet());
        const canvas = run.dry ? null : (this._binderCanvas || (this._binderCanvas = document.createElement('canvas')));
        const realCtx = canvas ? canvas.getContext('2d') : null;
        // Measuring needs a real context even on the dry pass.
        const measureCtx = realCtx || (this._binderMeasureCtx
            || (this._binderMeasureCtx = document.createElement('canvas').getContext('2d')));
        const book = {
            opts, list, meta, layers, run, sheet,
            geo: this._bGeo(sheet, opts.titleBlock !== false),
            scale: sheet.w * sheet.h > SCALE_PX_BUDGET ? 1 : 2,
            dry: !!run.dry, total: run.total || 0, only: run.only, plan: run.plan || null,
            log: run.log || null, bitmaps: !!run.bitmaps,
            series: {}, views: 0,
            pages: [], records: [], canvas, realCtx, measureCtx, ctx: null, page: null,
        };
        book.groups = this._bGroupPlans(opts);
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
        // Series by subject: 1 the overview; 2 the screens in BEACH order -
        // the pull list's position order, a position's own screens in the
        // project's screen order (_bOrderScreens) - each screen's POWER
        // sheet and its POWER WIRING sheet, its DATA sheet and its DATA
        // WIRING sheet; 3 the pull sheets, positions side by side; 4 the hardware - the distros, the processors, the show's
        // pull list.
        if (opts.cover) this._bOverviewPage(book);
        // grouped by system: a map, then the sheet that wires it - the
        // wall wired to its breakouts or its devices, that one side on a
        // page of its own (app-binder-wiring.js). No map, no wiring sheet:
        // a screen with no circuits has neither power sheet.
        const wiring = opts.wiring !== false;
        const emit = (subject, pos, side) => {
            this._bScreenPage(book, subject, pos, side);
            if (wiring) this._bWiringPage(book, subject, pos, { power: side === 'power', data: side === 'data' });
        };
        // A GROUP ROUTED AS ONE SCREEN prints by its tab's Names switch,
        // side by side (2026-10-01, _bGroupUnits): one sheet for the group
        // or a sheet per member - never the carrier alone, which dropped
        // the member that carries nothing of its own. The group's sheets
        // stand where its first member's would.
        const sheets = this._bScreenRun(book, positions);
        const order = sheets.map(e => e.layer);
        const posOf = new Map(sheets.map(e => [e.layer, e.pos]));
        const printed = new Set();
        // The Header/Footer sheet: one per SCREEN with header or footer bars, after that
        // screen's own sheets (a group's members each get theirs, after the
        // group's sheets - the bars belong to a screen, not to a group).
        const rig = (screen, pos) => {
            if (opts.rigging !== false && this._bHasRigging(screen)) this._bRiggingPage(book, screen, pos);
        };
        for (const { layer, pos } of sheets) {
            const gp = this._bGroupPlanOf(book, layer);
            if (gp) {
                if (printed.has(gp.id)) continue;
                printed.add(gp.id);
                for (const [subject, side] of this._bGroupUnits(book, gp, order, scopeLayer)) {
                    emit(subject, (subject.anchor && posOf.get(subject.anchor)) || pos, side);
                }
                const at = (m) => { const i = order.indexOf(m); return i < 0 ? order.length : i; };
                for (const m of gp.members.slice().sort((a, b) => at(a) - at(b))) {
                    if (!scopeLayer || m === scopeLayer) rig(m, posOf.get(m) || pos);
                }
                continue;
            }
            const scr = list.byScreen[layer.id];
            if (scr) {
                if (opts.sides.power && this._bHasPower(layer, scr)) emit(layer, pos, 'power');
                if (opts.sides.data && this._bHasData(layer, scr)) emit(layer, pos, 'data');
            }
            rig(layer, pos);
        }
        if (opts.pull) this._bPullSheets(book, positions);
        const hardware = [];
        if (opts.hardware) {
            // The services first (2026-10-20): the house power, then the
            // distros it feeds. Nothing for a show with none.
            for (const s of (typeof this.getServices === 'function' ? this.getServices() : [])) {
                const g = this._bServiceGroup(book, s);
                if (g) hardware.push(g);
            }
            for (const d of (typeof this.getDistros === 'function' ? this.getDistros() : [])) {
                const g = this._bDistroGroup(book, d);
                if (g) hardware.push(g);
            }
            for (const proc of (this._processorsResolved || [])) {
                const g = this._bProcessorGroup(book, proc);
                if (g) hardware.push(g);
                const bu = g && this._bBackupUnitGroup(book, proc, g.name);
                if (bu) hardware.push(bu);
            }
        }
        if (opts.pull) hardware.push(this._bTotalsGroup(book));
        this._bHardwareSheets(book, hardware);
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

    // ---- grouped screens ----------------------------------------------------

    // A GROUP ROUTED AS ONE SCREEN keeps every port and circuit on ONE
    // member - the carrier - and its peers carry none of their own, so a
    // set made a sheet per member with something on it printed the carrier
    // alone, its map the carrier's wall alone, its tables the whole group's
    // (owner, 2026-10-01: "when i print a grouped screen it doesnt include
    // WALL SL in the binder. this is bad and needs fixing"). Such a group now
    // prints by its tab's NAMES switch, each side on its own ("say power is
    // set to label by group name then power will be by group and if data is
    // set to screens then it will be 2 different"):
    //   group    ONE sheet for the group on that side, titled by the group's
    //            name, its map every member as it sits on the canvas, its
    //            rulers numbering straight through, its tables and FACTS the
    //            group's
    //   screens  a sheet per member, titled by the member, its map that
    //            member alone, its tables what lands on its cabinets - a port
    //            or circuit crossing members listed on each, saying where the
    //            rest of it is ("also on WALL SL")
    //   both     asked per group at export ("if set to both then ask per
    //            group"): the dialog's Groups row, saved in
    //            project.binder.groupSheets, read through readBinderOptions
    // A group whose members each carry their own (not routed as one) keeps
    // its per-member sheets whatever the switch says.
    //
    // { id, name, group, members, routed: {power, data}, mode: {power, data},
    //   asks: {power, data} } per group, by id - `mode` null on a side that
    // is not routed as one, `asks` true where the tab says Both.
    _bGroupPlans(opts) {
        const out = new Map();
        const groups = (this.project && this.project.groups) || [];
        if (!groups.length || typeof this.getGroupMembers !== 'function') return out;
        const shown = new Set(this._pullScreens());
        const answers = (opts && opts.groupSheets && typeof opts.groupSheets === 'object')
            ? opts.groupSheets : this.getBinderInfo().groupSheets;
        const canvasOf = (l) => l.show_canvas_id || l.canvas_id || null;
        for (const g of groups) {
            if (!g || g.id == null) continue;
            const members = this.getGroupMembers(g).filter(m => shown.has(m));
            // A wall drawn across two canvases is no one picture, and
            // crossing never spans them (getPathScopeLayers).
            if (members.length < 2 || !members.every(m => canvasOf(m) === canvasOf(members[0]))) continue;
            const routed = { power: this._bRoutedAsOne(members, 'power'),
                             data: this._bRoutedAsOne(members, 'data') };
            if (!routed.power && !routed.data) continue;
            const mode = { power: null, data: null }, asks = { power: false, data: false };
            for (const side of ['power', 'data']) {
                if (!routed[side]) continue;
                const tab = this.groupNameDisplayFor(side === 'power' ? 'power' : 'data-flow');
                asks[side] = tab === 'both';
                const asked = (answers[g.id] || {})[side];
                mode[side] = tab === 'both' ? (asked === 'screens' ? 'screens' : 'group') : tab;
            }
            out.set(String(g.id), { id: g.id, name: g.name || String(g.id), group: g, members,
                                    routed, mode, asks });
        }
        return out;
    }

    // Is this side of the wall routed as ONE screen - does any member's port
    // or circuit land on another member's cabinets? An automatic walk across
    // the group (getAutoRoutePlan: data unless the group's "Route data as
    // one screen" is off, power where the members match) and hand-drawn runs
    // stepping onto a peer both count; members each on their own runs do not.
    _bRoutedAsOne(members, side) {
        const kind = side === 'power' ? 'power' : 'data';
        if (typeof this.isServedByPeerRouting === 'function'
                && members.some(m => this.isServedByPeerRouting(m, kind))) return true;
        const ids = new Set(members.map(m => String(m.id)));
        for (const m of members) {
            const items = side === 'power'
                ? ((typeof this.screenCircuits === 'function') ? this.screenCircuits(m) : [])
                : this._pullPortRuns(m);
            for (const it of items) {
                if ((it.layers || []).some(l => l && String(l.id) !== String(m.id) && ids.has(String(l.id)))) return true;
            }
        }
        return false;
    }

    _bGroupPlanOf(book, layer) {
        if (!book.groups || !book.groups.size || !layer || layer.group_id == null) return null;
        return book.groups.get(String(layer.group_id)) || null;
    }

    // The group's sheets, in the order the set runs them: [[subject, side]].
    // A side printed by the GROUP is one sheet; a side by SCREENS a sheet per
    // member whenever anything in the group is on that side - every member,
    // so the one carrying nothing of its own still prints (the bug); a side
    // not routed as one, a sheet per member with something of its own, as
    // before. Where neither side is the group's, each member runs Power then
    // Data the way an ungrouped screen does; otherwise the Power sheets come
    // first, then the Data. A one-screen scope prints the group's sheet that
    // holds the screen, or the screen's own.
    _bGroupUnits(book, gp, order, scopeLayer) {
        const at = (m) => { const i = order.indexOf(m); return i < 0 ? order.length : i; };
        const members = gp.members.slice().sort((a, b) => at(a) - at(b));
        const own = (m, side) => {
            const scr = book.list.byScreen[m.id];
            return !!scr && (side === 'power' ? this._bHasPower(m, scr) : this._bHasData(m, scr));
        };
        const inScope = (m) => !scopeLayer || m === scopeLayer;
        const group = this._bGroupSubject(gp);
        const member = (m) => this._bMemberSubject(gp, m);
        const units = (side) => {
            if (!book.opts.sides[side]) return [];
            const any = gp.members.some(m => own(m, side));
            if (gp.mode[side] === 'group') return any && members.some(inScope) ? [[group, side]] : [];
            if (gp.mode[side] === 'screens') return any ? members.filter(inScope).map(m => [member(m), side]) : [];
            return members.filter(m => inScope(m) && own(m, side)).map(m => [this._bSubject(m), side]);
        };
        const power = units('power'), data = units('data');
        if (gp.mode.power === 'group' || gp.mode.data === 'group') return [...power, ...data];
        const out = [];
        for (const m of members) {
            for (const u of power) if (u[0].anchor === m) out.push(u);
            for (const u of data) if (u[0].anchor === m) out.push(u);
        }
        return out;
    }

    _bGroupSubject(gp) {
        return { kind: 'group', name: gp.name, id: gp.members[0].id, groupId: gp.id,
                 layers: gp.members, carriers: gp.members, members: gp.members,
                 member: null, anchor: null };
    }

    _bMemberSubject(gp, m) {
        return { kind: 'member', name: m.name, id: m.id, groupId: gp.id,
                 layers: [m], carriers: gp.members, members: gp.members,
                 member: m, anchor: m };
    }

    // What a screen sheet is OF: a screen as before (`kind` 'layer'), a group
    // printed as one ('group') or one member of a group printed by screens
    // ('member'). `layers` are the screens its map draws, `carriers` the
    // screens whose ports and circuits it reads, `members` the group's
    // screens kept drawn while it paints (the walk across the group is only
    // the group's while every member is on the wall), `member` the screen
    // whose cabinets decide what is listed, `id` the plan's layerId.
    _bSubject(target) {
        if (target && target.kind && Array.isArray(target.layers)) return target;
        return { kind: 'layer', name: target.name, id: target.id, groupId: null,
                 layers: [target], carriers: [target], members: [target], member: null, anchor: target };
    }

    _bSameLayer(a, b) {
        return !!a && !!b && (a === b || String(a.id) === String(b.id));
    }

    // The screen each drawn cabinet of a run or circuit is on: its own entry
    // in `layers` where the item carries one (a run crossing members), else
    // the screen that owns the item.
    _bItemLayers(carrier, panels, layers) {
        const out = [];
        (panels || []).forEach((p, i) => {
            if (!p || p.hidden) return;
            out.push((layers && layers[i]) || carrier);
        });
        return out;
    }

    // Where the rest of a crossing item is, on a member's sheet: "also on
    // WALL SL" - the snake heading's "also" (snakeElsewhere) said of a
    // screen; '' where it is all on this member.
    _bAlsoOn(s, ls) {
        if (s.kind !== 'member') return '';
        const names = s.members
            .filter(m => !this._bSameLayer(m, s.member) && ls.some(l => this._bSameLayer(l, m)))
            .map(m => m.name);
        return names.length ? `also on ${names.join(', ')}` : '';
    }

    // The ports a sheet lists: [{ carrier, run, also }] - every run of its
    // carriers, on a member's sheet only those landing on its cabinets.
    _bSubjectRuns(s) {
        const out = [];
        for (const carrier of s.carriers) {
            for (const run of this._pullPortRuns(carrier)) {
                if (s.kind === 'layer') { out.push({ carrier, run, also: '' }); continue; }
                const ls = this._bItemLayers(carrier, run.panels, run.layers);
                if (s.kind === 'member' && !ls.some(l => this._bSameLayer(l, s.member))) continue;
                out.push({ carrier, run, also: this._bAlsoOn(s, ls) });
            }
        }
        return out;
    }

    // The multis a sheet lists: [{ carrier, box, also: Map(circuit -> text) }]
    // - the pull list's own units, a member's holding only the circuits that
    // land on its cabinets.
    _bSubjectBoxes(book, s) {
        const out = [];
        for (const carrier of s.carriers) {
            const scr = book.list.byScreen[carrier.id];
            if (!scr) continue;
            if (s.kind === 'layer') {
                for (const box of scr.boxes || []) out.push({ carrier, box, also: new Map() });
                continue;
            }
            const byNum = new Map(((typeof this.screenCircuits === 'function') ? this.screenCircuits(carrier) : [])
                .map(c => [c.num, c]));
            for (const box of scr.boxes || []) {
                const also = new Map();
                const circuits = (box.circuits || []).filter(c => {
                    const circuit = byNum.get(c.num);
                    const ls = circuit ? this._bItemLayers(carrier, circuit.panels, circuit.layers) : [carrier];
                    if (s.kind === 'member' && !ls.some(l => this._bSameLayer(l, s.member))) return false;
                    const text = this._bAlsoOn(s, ls);
                    if (text) also.set(c.num, text);
                    return true;
                });
                if (s.kind === 'member' && !circuits.length) continue;
                out.push({ carrier, box: s.kind === 'member' ? { ...box, circuits } : box, also });
            }
        }
        return out;
    }

    // The CABLES THIS SCREEN rows: the screen's own (the pull list's
    // attribution); the group's, every member's merged the way the pull
    // list merges; a MEMBER's, the cables landing on its own cabinets
    // (owner, 2026-10-01: "separate them. if the data or power splits then
    // mention it on both. pull sheets only account for one though not
    // double") - read off every member's rows tagged with the screens each
    // cable lands on (the pull list's `rowsOn`), a cable crossing into
    // another member listed on both with `also` saying where the rest of it
    // is. The pull list and its totals count each cable once whatever this
    // prints.
    _bSubjectRows(book, s, side) {
        const of = (l) => ((book.list.byScreen[l.id] || {}).rows || []);
        const pick = (rows) => rows.filter(r => (side === 'power' ? (r.side || 'power') === 'power' : r.side === 'data'));
        if (s.kind === 'group') return pick(this._pullMergeRows(s.members.flatMap(of)));
        if (s.kind !== 'member') return pick(of(s.layers[0]));
        const mine = String(s.member.id);
        const byAlso = new Map();          // also text -> rows
        for (const carrier of s.carriers) {
            for (const r of pick((book.list.byScreen[carrier.id] || {}).rowsOn || [])) {
                const on = (r.on || [carrier.id]).map(String);
                if (!on.includes(mine)) continue;
                const also = this._bAlsoOn(s, s.members.filter(m => on.includes(String(m.id))));
                if (!byAlso.has(also)) byAlso.set(also, []);
                byAlso.get(also).push(r);
            }
        }
        const out = [];
        for (const also of ['', ...[...byAlso.keys()].filter(Boolean)]) {
            for (const r of this._pullMergeRows(byAlso.get(also) || [])) out.push({ ...r, also });
        }
        return out;
    }

    // The CABLES THIS SCREEN table: CABLE, LENGTH, QTY - a cable crossing into
    // another member reading "Data Cable · also on WALL SL", wrapped under
    // its type.
    _bCableTable(book, s, side) {
        const rows = this._bSubjectRows(book, s, side);
        const crossing = rows.some(r => r.also);
        return this._bTableLines(book, {
            title: 'Cables this screen',
            cols: [{ title: 'cable', w: 1.7, ...(crossing ? { list: 2 } : { lend: true }) },
                   { title: 'length', w: 0.7, borrow: 'len' },
                   { title: 'qty', w: 0.6, align: 'right', lend: true }],
            rows: rows.length
                ? rows.map(r => ({ cells: [r.also ? `${this._bType(r.type)} · ${r.also}` : this._bType(r.type),
                                           r.length || '—', this._bQty(r.qty)] }))
                : [{ cells: ['no cables typed', '', ''] }],
        });
    }

    // The group's FACTS figures: _bScreenFacts across its members - every
    // panel, watt and pixel summed once, the size the union of the walls.
    _bGroupFacts(members) {
        const fs = members.map(m => this._bScreenFacts(m));
        const r = window.canvasRenderer;
        let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
        for (const m of members) {
            const b = r ? r.getLayerBounds(m) : null;
            if (!b) continue;
            x1 = Math.min(x1, b.x); y1 = Math.min(y1, b.y);
            x2 = Math.max(x2, b.x + b.width); y2 = Math.max(y2, b.y + b.height);
        }
        const sum = (k) => fs.reduce((a, f) => a + (f[k] || 0), 0);
        const voltage = fs.length ? fs[0].voltage : 0;
        const watts = sum('watts');
        const active = sum('active');
        const sizes = [...new Set(members.map(m => `${m.cabinet_width}×${m.cabinet_height}`))];
        // the service's line-to-line voltage (1.5, bug fix 3)
        const lineV = members.length ? this.threePhaseLineVoltage(members[0]) : voltage;
        return {
            active, equivalent: sum('equivalent'), watts, voltage,
            amps1: voltage > 0 ? watts / voltage : 0,
            amps3: lineV > 0 ? watts / (lineV * 1.73) : 0,
            pixels: sum('pixels'),
            width: Number.isFinite(x1) ? x2 - x1 : 0, height: Number.isFinite(y1) ? y2 - y1 : 0,
            screenText: `${members.map(m => `${m.columns} × ${m.rows}`).join(' + ')} · ${this._bPlural(active, 'panel')}`
                + ` · ${sizes.join(' / ')} px`,
        };
    }

    // ---- the screen order ---------------------------------------------------

    // The screens in the order the sheets run: the positions in their
    // order (beaches first, in the Beaches panel's order), a position's
    // own screens sorted by the project's screen order (_bOrderScreens).
    // The LOOSE screens - each its own position in the pull list, one per
    // screen in layer order - are one group here: a run of them sorts
    // together, so a show with no beaches (his buddy's seven walls) runs
    // A, B, C … and not the layer list. Each keeps its own position for
    // the sheet's name. [{ layer, pos }]
    _bScreenRun(book, positions) {
        const out = [];
        let loose = [];
        const flush = () => {
            if (!loose.length) return;
            const byId = new Map(loose.map(e => [e.layer, e.pos]));
            for (const layer of this._bOrderScreens(book, loose.map(e => e.layer))) out.push({ layer, pos: byId.get(layer) });
            loose = [];
        };
        for (const { pos, own } of positions) {
            if (String(pos.key || '').startsWith('layer:')) {
                for (const layer of own) loose.push({ layer, pos });
                continue;
            }
            flush();
            for (const layer of this._bOrderScreens(book, own)) out.push({ layer, pos });
        }
        flush();
        return out;
    }

    // A beach's screens in the order project.binder.screenOrder names
    // (2026-09-08, his buddy on seven walls "A - OffSR IMAG" … "G - E3
    // Delay": "i'd want raster A first, then in alphabetical order"):
    //   alpha      by name, natural - "A - …" before "B - …", 2 before 10
    //   layers     the Screens panel's order, top to bottom - the panel as
    //              it is actually drawn (_bPanelScreenOrder: canvases, then
    //              newest-on-top inside each, then screen groups gathered)
    //   layers-up  that list read bottom to top
    //   data       by the screen's first port: processor order, then card
    //              slot, then socket - a screen on card 1 socket 1 first;
    //              screens with no port after those, alphabetical
    //   power      by the screen's first circuit: distro order, then multi
    //              number, then circuit; screens with none after, alphabetical
    // The beaches come first either way: this sorts WITHIN a beach (and
    // the loose group). Never the array it is given.
    _bOrderScreens(book, layers) {
        const order = (book.meta.binder && book.meta.binder.screenOrder) || 'alpha';
        const name = (l) => String(l.name == null ? '' : l.name);
        const byName = (a, b) => name(a).localeCompare(name(b), undefined, { numeric: true, sensitivity: 'base' })
            || String(a.id).localeCompare(String(b.id), undefined, { numeric: true });
        if (order === 'layers' || order === 'layers-up') {
            const panel = this._bPanelScreenOrder();
            const at = (l) => { const i = panel.indexOf(l); return i < 0 ? panel.length : i; };
            const dir = order === 'layers' ? 1 : -1;
            return [...layers].sort((a, b) => (dir * (at(a) - at(b))) || byName(a, b));
        }
        if (order === 'data' || order === 'power') {
            const keys = new Map(layers.map(l => [l, order === 'data'
                ? this._bFirstPortKey(l) : this._bFirstCircuitKey(book, l)]));
            return [...layers].sort((a, b) => {
                const ka = keys.get(a), kb = keys.get(b);
                if (ka && kb) {
                    for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] - kb[i];
                    return byName(a, b);
                }
                if (ka || kb) return ka ? -1 : 1;
                return byName(a, b);
            });
        }
        return [...layers].sort(byName);
    }

    // The Screens panel's rows in the order the eye reads them, TOP FIRST
    // (2026-09-09: "top to bottom does bottom to top actually"). The panel
    // is not the layer array reversed - that was the old assumption, and it
    // inverted the moment a show had more than one canvas. It is three
    // passes, and this walks the same three over the model so 'layers'
    // follows what is on screen whatever the show is built from:
    //   1. renderLayers reverses the layer array (newest on top)
    //   2. regroupLayersByCanvas deals the rows into CANVAS groups, the
    //      canvases in their own array order, each group holding its
    //      canvas's rows in that reversed order (a Show view groups by
    //      show_canvas_id || canvas_id, the same as the sidebar)
    //   3. regroupLayersByGroup lifts a screen group's rows to sit
    //      together at the FIRST member's place - only the members sharing
    //      that member's canvas move; one on another canvas stays put
    // 'layers-up' is this list read the other way.
    _bPanelScreenOrder() {
        const all = (this.project && this.project.layers) || [];
        const reversed = [...all].reverse();
        const canvases = (this.project && this.project.canvases) || [];
        const isShow = !!(window.canvasRenderer
            && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const canvasOf = (l) => ((isShow && l.show_canvas_id)
            ? l.show_canvas_id : l.canvas_id);
        let out = [];
        if (canvases.length) {
            const placed = new Set();
            canvases.forEach(c => reversed.forEach(l => {
                if (canvasOf(l) !== c.id) return;
                out.push(l);
                placed.add(l);
            }));
            // A row whose canvas is not in the list is not drawn in any
            // group; it keeps the flat order after them rather than
            // vanishing from the plan.
            reversed.forEach(l => { if (!placed.has(l)) out.push(l); });
        } else {
            out = reversed;
        }
        for (const g of (this.project && this.project.groups) || []) {
            const ids = new Set((g && g.layer_ids) || []);
            const members = out.filter(l => ids.has(l.id));
            if (members.length < 2) continue;
            const home = canvasOf(members[0]);
            const own = members.filter(l => canvasOf(l) === home);
            if (own.length < 2) continue;
            const mine = new Set(own);
            const firstAt = out.indexOf(own[0]);
            out = [
                ...out.slice(0, firstAt).filter(l => !mine.has(l)),
                ...own,
                ...out.slice(firstAt).filter(l => !mine.has(l)),
            ];
        }
        return out;
    }

    // [processor index, card slot, socket] of the screen's first placed
    // port - the least of its ports' - or null when none is placed.
    _bFirstPortKey(layer) {
        const asg = ((this._assignment && this._assignment.screens) || [])
            .find(s => String(s.layerId) === String(layer.id));
        const procs = this._processorsResolved || [];
        let best = null;
        for (const p of (asg && asg.ports) || []) {
            if (!p || !p.cardId) continue;
            const home = this._bPortHome(p.cardId, p.port);
            if (!home) continue;
            const pi = procs.findIndex(x => x && x.id === home.proc.id);
            const slot = (home.proc.slots || []).findIndex(s => s && s.card && s.card.id === home.card.id);
            const socket = parseInt(p.port, 10);
            const k = [pi < 0 ? procs.length : pi, slot < 0 ? 0 : slot, Number.isFinite(socket) ? socket : 0];
            if (!best || this._bKeyLess(k, best)) best = k;
        }
        return best;
    }

    // [distro index, multi number, circuit] of the screen's first circuit
    // on a distro - the least of them - or null when it has none.
    _bFirstCircuitKey(book, layer) {
        const scr = book.list.byScreen[layer.id];
        const distros = (typeof this.getDistros === 'function') ? this.getDistros() : [];
        let best = null;
        for (const box of (scr && scr.boxes) || []) {
            if (!box || !box.distroId) continue;
            const di = distros.findIndex(d => d && d.id === box.distroId);
            for (const c of box.circuits || []) {
                const k = [di < 0 ? distros.length : di, Number(box.number) || 0, Number(c.tail) || 0];
                if (!best || this._bKeyLess(k, best)) best = k;
            }
        }
        return best;
    }

    _bKeyLess(a, b) {
        for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i];
        return false;
    }

    // The sheet's frame in page pixels: the border, the title block, the
    // drawing area.
    //
    // With the title block switched off ("so we need to have a way to turn
    // off the frame and extra text like overview and designer on the
    // binder. Sometime having more screen real estate is better that way
    // the screens fill the pdf", 2026-09-11) the column is not there at
    // all: `tb` has no width, and the drawing area takes the whole sheet
    // inside the same small margin - TB_W wider than before. The sheet
    // keeps its own naming at the foot (the view bubble and the subject
    // heading); nothing else of the block survives.
    _bGeo(sheet, titleBlock) {
        const W = sheet.w, H = sheet.h;
        const on = titleBlock !== false;
        const border = { x: PAD, y: PAD, w: W - PAD * 2, h: H - PAD * 2 };
        const tb = { x: W - PAD - (on ? TB_W : 0), y: PAD, w: on ? TB_W : 0, h: H - PAD * 2 };
        const da = { x: PAD + DA_PAD, y: PAD + DA_PAD, w: tb.x - PAD - DA_PAD * 2, h: H - PAD * 2 - DA_PAD * 2 };
        return { W, H, border, tb, da, titleBlock: on };
    }

    // ---- sheets: number, paint, frame, close --------------------------------

    // A sheet. `spec` names it ({ kind, title, sheetTitle, view?, layerId,
    // subject, layout, cols, scale?, extent?, coverage?, names? });
    // `body(page, scaled)` draws its drawing area through book.ctx - on a
    // painting pass, for the sheet being painted: the book canvas sized to
    // the sheet at book.scale, the frame (border, title block) drawn, then
    // the body - through the recording context, so the sheet's display
    // list is written as the canvas is painted. What the body draws inside
    // `scaled(fn)` is laid out at the base sizes and painted at spec.scale
    // (the fill, > 1): the context scaled about the drawing area's corner
    // so base coordinates land scaled on the page - and book.fill says so,
    // for the logs (_bLogXY); a map sheet paints its map outside it, in
    // page units. At 1 `scaled` is a plain call. The title block, drawn
    // before, is the same on every sheet. The plan (dry) and the sheets
    // not being painted only take their number.
    _bPage(book, spec, body) {
        this._bClosePage(book);
        const index = book.pages.length;
        const series = SERIES[spec.kind] || 5;
        book.series[series] = (book.series[series] || 0) + 1;
        // the sheet title in caps, as the block and the contents print it
        const page = { index, number: `${series}.${book.series[series]}`, painting: false, ...spec,
                       sheetTitle: this._bCaps(spec.sheetTitle || spec.title || '') };
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
            const s = page.scale || 1;
            const scaled = (fn) => {
                if (!(s > 1)) { fn(); return; }
                const da = book.geo.da;
                book.fill = { s, x: da.x, y: da.y, e: da.x - s * da.x, f: da.y - s * da.y };
                book.ctx.save();
                book.ctx.translate(da.x, da.y);
                book.ctx.scale(s, s);
                book.ctx.translate(-da.x, -da.y);
                try { fn(); } finally { book.ctx.restore(); book.fill = null; }
            };
            body(page, scaled);
        } else {
            book.ctx = this._bDryCtx(book.measureCtx);
        }
        this._bClosePage(book);
        return page;
    }

    // The sheet's white, its border, the title block, the rev in the
    // corner. With the title block off the sheet is the white and the
    // drawing alone: no border rule, no column, no rev line - the sheet
    // names itself at the foot, where its body draws the view bubble and
    // the subject heading.
    _bPageFrame(book, page) {
        const ctx = book.ctx;
        const { W, H, border, da, titleBlock } = book.geo;
        ctx.setTransform(book.scale, 0, 0, book.scale, 0, 0);
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, W, H);
        if (!titleBlock) return;
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
        // The people, top to bottom: each a label with its lines under it -
        // a name's one line always (blank prints the label alone), the
        // project manager's phone and email only where typed (a blank one
        // left a gap above Drafter, 2026-10-17), the Engineer only where
        // one is set (getEngineerName). Label to first line 30, line to
        // line 28, last line to the next label 48; the section ends 54
        // under its last line - Designer, a manager with phone and email,
        // and Drafter come to the 330 the section always was.
        const people = [
            ['Designer:', [b.designer]],
            ['Project Manager:', [b.projectManager.name,
                                  ...[b.projectManager.phone, b.projectManager.email].filter(Boolean)]],
            ['Drafter:', [b.drafter]],
            ...(m.engineer ? [['Engineer:', [m.engineer]]] : []),
        ];
        const peopleAt = [];
        let py = 34;
        for (const [label, values] of people) {
            peopleAt.push({ label, y: py, values: values.map((v, k) => ({ text: v, y: py + 30 + k * 28 })) });
            py += 30 + (values.length - 1) * 28 + 48;
        }
        const hShow = 170, hPeople = py - 48 + 54, hTitle = 90, hNumber = 150;
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
        // Every column stands on its middle, its heading and its rows
        // (owner, 2026-10-18: "center every column in every binder table").
        const cols = [[0, 'No.'], [0.13, 'Date'], [0.38, 'By'], [0.56, 'Description']];
        const cx = (f) => x + pad + f * inner;
        const ends = [...cols.slice(1).map(([f]) => f), 1];
        const mid = (j) => (cx(cols[j][0]) + cx(ends[j])) / 2;
        const room = (j) => (ends[j] - cols[j][0]) * inner - 8;
        cols.forEach(([, t], j) => this._bText(book, t, mid(j), y + 62,
                                               { size: SZ.tbSmall, weight: 400, align: 'center', maxWidth: room(j) }));
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
        // A long description wraps inside its row - up to three lines,
        // 22 apart - rather than being cut to "Logo and revision …"
        // (2026-09-08); the box is tall. Logged once, whole, like a
        // two-line cell. Rows follow as tall as they are, as many as fit.
        const descW = 0.44 * inner - 8;
        let ry = y + 96, printed = 0;
        for (const r of b.revisions) {
            const lines = this._bWrap(book, r.description, SZ.tbSmall, 400, descW, 3);
            if (ry + (lines.length - 1) * 22 > y + hRev - 4) break;
            this._bText(book, String(r.no || printed + 1), mid(0), ry, { size: SZ.tbSmall, align: 'center', maxWidth: room(0) });
            this._bText(book, r.date, mid(1), ry, { size: SZ.tbSmall, align: 'center', maxWidth: room(1) });
            this._bText(book, r.by, mid(2), ry, { size: SZ.tbSmall, align: 'center', maxWidth: room(2) });
            lines.forEach((t, k) => this._bText(book, t, mid(3), ry + k * 22,
                                                { size: SZ.tbSmall, align: 'center', log: false }));
            if (book.log && page.painting) {
                book.log.texts.push(r.description);
                if (book.log.textInfo) book.log.textInfo.push({ text: r.description, size: SZ.tbSmall, weight: 400 });
            }
            ry += 30 + (lines.length - 1) * 22;
            printed++;
        }
        sections.revisions = { y, h: hRev, rows: printed };
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
        for (const who of peopleAt) {
            this._bText(book, who.label, x + pad, y + who.y, { size: SZ.tbLabel, weight: 700 });
            for (const v of who.values) {
                this._bText(book, v.text, x + pad + 40, y + v.y, { size: SZ.tbCell, maxWidth: inner - 40 });
            }
        }
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
        // The number stands high enough in its triangle that two digits
        // after the point clear the diagonal: at y + 108 "2.10" ran its 0
        // into the line, and with a wiring sheet behind every map three
        // screens reach 2.10. Its room is the width left of the diagonal a
        // little under the baseline; a longer number than that shrinks.
        const numberY = y + 96;
        const under = numberY + SZ.tbNumber * 0.14 - y;
        const numberRoom = w * (1 - under / hNumber) - pad - 8;
        this._bText(book, page.number, x + pad, numberY,
                    { size: SZ.tbNumber, weight: 800, maxWidth: numberRoom, shrink: true });
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
    // sheet's identity, translate, rotate and scale (the fill, _bPage)
    // compose onto it, save and restore stack it - widths, heights, line
    // widths, dashes and type sizes are recorded through the scale in
    // force, so a sheet painted at the fill scale is written in the page
    // units it lands in. Nothing else the binder draws with needs tracking
    // (grep `ctx\.` here: no arcs - the view bubble's circle is a polyline
    // - no fills of paths).
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
        // the uniform scale in force (exact where nothing is turned)
        const k = () => (xf.b === 0 && xf.c === 0 ? Math.abs(xf.a) : Math.hypot(xf.a, xf.b));
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
            scale(sx, sy) {
                const y = sy == null ? sx : sy;
                xf = mul(xf, { a: sx, b: 0, c: 0, d: y, e: 0, f: 0 });
                return t.scale(sx, y);
            },
            save() { stack.push({ ...xf }); return t.save(); },
            restore() { if (stack.length) xf = stack.pop(); return t.restore(); },
            fillRect(x, y, w, h) {
                const [px, py] = map(x, y);
                const s = k();
                ops.push({ op: 'rect', x: round(px), y: round(py), w: round(w * s), h: round(h * s), fill: fillHex() });
                return t.fillRect(x, y, w, h);
            },
            strokeRect(x, y, w, h) {
                const [px, py] = map(x, y);
                const s = k();
                ops.push({ op: 'rect', x: round(px), y: round(py), w: round(w * s), h: round(h * s),
                           stroke: strokeHex(), width: round(t.lineWidth * s) });
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
                const s = k();
                const width = round(t.lineWidth * s), dash = Array.from(t.getLineDash() || []).map(d => round(d * s));
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
                           size: round(f.size * k()), weight: f.weight,
                           align: t.textAlign || 'left', baseline: t.textBaseline || 'alphabetic',
                           color: fillHex(), rotate: rotation() });
                return maxWidth === undefined ? t.fillText(text, x, y) : t.fillText(text, x, y, maxWidth);
            },
            drawImage(img, ...args) {
                // the binder draws (img, x, y, w, h); the bitmap is taken
                // now, as the offscreen canvas is reused for the next map
                const [x, y, w, h] = args.length >= 5 ? args.slice(4) : args;
                const [px, py] = map(x, y);
                const s = k();
                const id = `img${++imageSeq}`;
                let data = null;
                try {
                    data = typeof img._binderDataUrl === 'string' ? img._binderDataUrl
                        : typeof img.toDataURL === 'function' ? img.toDataURL('image/png') : null;
                } catch (_) {}
                if (data) {
                    images[id] = data;
                    ops.push({ op: 'image', id, x: round(px), y: round(py), w: round(w * s), h: round(h * s) });
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

    // Text in caps, as a heading prints it - every word but a cable
    // length's unit in a meters show: "STRAND MAP · TAC A · 100 m", never
    // "100 M" (a length reads the same on every paper, app-cable-units.js
    // cableLengthText: the figure, a space, m). A feet show is plain
    // caps - "100'" has nothing to lower.
    _bCaps(text) {
        const t = String(text == null ? '' : text);
        if (typeof this.cableUnit !== 'function' || this.cableUnit() !== 'm') return t.toUpperCase();
        const re = /(^|[^\w.])(\d+(?:\.\d+)? m)(?!\w)/g;
        let out = '', last = 0, m;
        while ((m = re.exec(t))) {
            const at = m.index + m[1].length;
            out += t.slice(last, at).toUpperCase() + m[2];
            last = at + m[2].length;
        }
        return out + t.slice(last).toUpperCase();
    }

    _bText(book, text, x, y, o) {
        const ctx = book.ctx;
        const opts = o || {};
        let t = String(text == null ? '' : text);
        if (opts.upper) t = this._bCaps(t);
        let size = opts.size || SZ.cell;
        ctx.font = this._bFont(size, opts.weight);
        // A heading shrinks a little before it is cut: "PANELS" in a narrow
        // column is still "PANELS".
        // (`minSize`: a heading that must never be cut - LENGTH in a crowded
        // table - may go smaller than that)
        if (opts.shrink && opts.maxWidth) {
            const floor = opts.minSize || 14;
            while (size > floor && ctx.measureText(t).width > opts.maxWidth) {
                size -= opts.minSize ? 0.5 : 1;
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

    // The width `text` takes drawn by _bText with these options - shrunk
    // and cut as it would be - so a piece drawn beside it (a strand's
    // swatch) can stand with it on a column's middle.
    _bTextWidth(book, text, o) {
        const ctx = book.measureCtx || book.ctx;
        const opts = o || {};
        let t = String(text == null ? '' : text);
        if (opts.upper) t = this._bCaps(t);
        let size = opts.size || SZ.cell;
        ctx.font = this._bFont(size, opts.weight);
        if (opts.shrink && opts.maxWidth) {
            while (size > 14 && ctx.measureText(t).width > opts.maxWidth) {
                size -= 1;
                ctx.font = this._bFont(size, opts.weight);
            }
        }
        if (opts.maxWidth) t = this._bFit(ctx, t, opts.maxWidth);
        return ctx.measureText(t).width;
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
    // "…". THE SEPARATOR STAYS ON THE FIRST LINE: two ends stacked with
    // the " / " dropped read as one thing said twice, which is what the
    // live show A binder's HOME RUN column did (2026-09-09). Logged as one text,
    // the whole cell, so a reader of the sheet's texts still sees one
    // entry per cell.
    _bTextTwoLines(book, text, x, y, o) {
        const opts = o || {};
        const parts = String(text).split(' / ');
        if (parts.length !== 2
                || this._bTextFits(book, text, opts.size || SZ.cell, opts.weight, opts.maxWidth)) {
            return this._bText(book, text, x, y, opts);
        }
        const size = 16;
        const drawn = [`${parts[0]} /`, parts[1]].map((p, k) => this._bText(book, p, x, y - 12 + k * 17,
            { ...opts, size, shrink: true, log: false }));
        const t = drawn.join(' ');
        if (book.log && book.page && book.page.painting) {
            book.log.texts.push(t);
            if (book.log.textInfo) book.log.textInfo.push({ text: t, size, weight: opts.weight || 400 });
        }
        return t;
    }

    // Where a base-layout point lands on the page through the sheet's
    // fill scale (book.fill, _bPage) - the very arithmetic the recorder
    // does - so a log entry matches the op it describes; identity at 1.
    _bLogXY(book, x, y) {
        const f = book.fill;
        const round = (v) => Math.round(v * 100) / 100;
        if (!f) return [round(x), round(y)];
        return [round(f.s * x + f.e), round(f.s * y + f.f)];
    }

    _bLogRect(book, r) {
        const [x, y] = this._bLogXY(book, r.x, r.y);
        const s = book.fill ? book.fill.s : 1;
        const round = (v) => Math.round(v * 100) / 100;
        return { x, y, w: round(r.w * s), h: round(r.h * s) };
    }

    // Words onto lines no wider than maxWidth, at most maxLines - the
    // last cut with … where more would follow - measured as _bText draws.
    _bWrap(book, text, size, weight, maxWidth, maxLines) {
        const ctxM = book.measureCtx;
        ctxM.font = this._bFont(size, weight);
        const words = String(text == null ? '' : text).split(/\s+/).filter(Boolean);
        const lines = [];
        let cur = '';
        for (const w of words) {
            const t = cur ? `${cur} ${w}` : w;
            if (cur && ctxM.measureText(t).width > maxWidth) { lines.push(cur); cur = w; }
            else cur = t;
        }
        if (cur) lines.push(cur);
        if (lines.length > maxLines) {
            const keep = lines.slice(0, maxLines);
            keep[maxLines - 1] = this._bFit(ctxM, lines.slice(maxLines - 1).join(' '), maxWidth);
            return keep;
        }
        return lines.length ? lines : [''];
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

    // en-US with thousands separators at any number of decimals
    // ("1,724.4"); toFixed alone printed "1724.4".
    _bNum(n, digits) {
        const v = Number(n);
        if (!Number.isFinite(v)) return '—';
        const d = Number.isInteger(digits) && digits > 0 ? digits : 0;
        return (d === 0 ? Math.round(v) : v).toLocaleString('en-US',
            { minimumFractionDigits: d, maximumFractionDigits: d });
    }

    // A pull quantity: a count with thousands separators ("1,517"),
    // anything else as it came.
    _bQty(q) {
        const v = Number(q);
        return q !== null && q !== '' && Number.isFinite(v) ? this._bNum(v, 0) : String(q);
    }

    _bPlural(n, word) {
        return `${n} ${word}${n === 1 ? '' : 's'}`;
    }

    // ---- tables: lines, the packer, the layout ------------------------------

    // A cell split at the separators it is written with - ", " between the
    // members of a list, " · " between the things a cell says - each piece
    // keeping its own separator, so a line that continues ends in the comma
    // that says so.
    // A `words` column (a cable with its kind in brackets, a copper run's
    // warning) wraps between any two words instead.
    _bCellPieces(text, words) {
        const s = String(text == null ? '' : text);
        // 'on': "X1 on XD S1 A" breaks only after its " on " - a box's
        // name is never split, and the column asks for the name whole
        if (words === 'on') {
            const m = /^(.*? on )(.+)$/.exec(s);
            return m ? [m[1], m[2]] : [s];
        }
        // never break before a " · " - its dot stays with the word it follows
        if (words) return s.split(/(?<= )(?!· )/).filter(Boolean);
        const out = [];
        let cur = '';
        for (let i = 0; i < s.length; i++) {
            cur += s[i];
            if ((s[i] === ',' || s[i] === '·') && s[i + 1] === ' ') {
                out.push(cur + ' ');
                cur = '';
                i++;
            }
        }
        if (cur) out.push(cur);
        return out;
    }

    // A LIST CELL onto lines: as many of its members per line as the column
    // holds, up to maxLines, and where more are left the last line SAYS HOW
    // MANY ("S1-3-1, S1-3-2, +14 more") - a circuit name cut in half on a
    // pull sheet is worse than useless (2026-09-09). Never returns a cut
    // string, so nothing ends in an ellipsis.
    _bCellLines(book, text, size, weight, maxWidth, maxLines, words) {
        const ctxM = book.measureCtx;
        ctxM.font = this._bFont(size, weight);
        const s = String(text == null ? '' : text).trim();
        const fits = (t) => ctxM.measureText(t).width <= maxWidth;
        if (!s || fits(s)) return [s];
        const pieces = this._bCellPieces(s, words);
        const textOf = (idx) => idx.map(i => pieces[i]).join('').trim();
        const rows = [];
        let cur = [];
        for (let i = 0; i < pieces.length; i++) {
            if (cur.length && !fits(textOf(cur.concat(i)))) { rows.push(cur); cur = [i]; }
            else cur.push(i);
        }
        if (cur.length) rows.push(cur);
        if (rows.length <= maxLines) return rows.map(textOf);
        const keep = rows.slice(0, maxLines);
        let last = keep[maxLines - 1].slice();
        let shown = keep.slice(0, -1).reduce((n, r) => n + r.length, 0) + last.length;
        while (last.length > 1 && !fits(`${textOf(last)} +${pieces.length - shown} more`)) {
            last.pop();
            shown--;
        }
        keep[maxLines - 1] = last;
        return keep.map((r, i) => i === maxLines - 1
            ? `${textOf(r)} +${pieces.length - shown} more` : textOf(r));
    }

    // The columns' widths inside the column this block is MEASURED in: the
    // declared fractions, except that a column whose heading or whose
    // widest cell would be cut takes the room its neighbours are not using
    // - "CIRCUITS" printed "CIRC…" in the Screens table's six columns while
    // SCREEN sat half empty beside it (2026-09-09). Nothing is ever taken
    // below what its own content needs, so a table that already fits is
    // laid out exactly as it was. A list column asks only for its heading:
    // its list wraps and says how many more - unless the table asks for
    // its lists `whole` and the width holds every one of them on one line
    // (the pull sheet's columns, sized to their content), when a list
    // column asks for its widest list. A `small` table (the pull sheet's
    // Screens, four positions to a Tabloid) that cannot hold its headings
    // and cells at full size asks for them at the smallest size they
    // shrink to (_bText's 14), so they shrink rather than cut ("CIRCU…").
    //
    // A column that BORROWS (`borrow`: the cable tables' LENGTH, its old
    // heading "len" the value) is laid out as it was under its old heading,
    // so every other column keeps the width - and the wrapping - it had;
    // then it takes the room its whole heading needs from the spare of
    // the columns that LEND (`lend`: CABLE and QTY, whose text never wraps
    // or changes with their width), and past what they can spare, from
    // any column's room beyond its own content - never below it, so no
    // other cell changes. Where a crowded table has no room left anywhere
    // the heading shrinks to fit (`minSize`, _bText) - smaller,
    // never cut (owner, 2026-10-18: "LEN" → "LENGTH", widened as needed so
    // it is not truncated).
    _bColWidths(book, cols, rows, width, padX, o = {}) {
        if (cols.some(c => c.borrow)) return this._bBorrowWidths(book, cols, rows, width, padX, o);
        const fr = cols.reduce((s, c) => s + (c.w || 1), 0) || 1;
        const px = cols.map(c => (c.w || 1) / fr * width);
        const sum = (a) => a.reduce((x, y) => x + y, 0);
        const full = cols.map(c => ({ ...c, headShrink: false }));
        let need = this._bColNeeds(book, cols, rows, padX);
        // headings shrink only where the table cannot hold them whole
        if (cols.some(c => c.headShrink)) {
            const whole = this._bColNeeds(book, full, rows, padX);
            if (sum(whole) <= width) need = whole;
        }
        if (o.whole) {
            const lists = this._bColNeeds(book, full, rows, padX, true);
            if (sum(lists) <= width) need = lists;
        }
        if (o.small && sum(need) > width) {
            need = this._bColNeeds(book, cols.map(c => ({ ...c, headShrink: true })), rows, padX, false, true);
        }
        const want = px.map((p, i) => Math.max(0, need[i] - p));
        const give = px.map((p, i) => Math.max(0, p - need[i]));
        const wantAll = want.reduce((a, b) => a + b, 0);
        const giveAll = give.reduce((a, b) => a + b, 0);
        if (wantAll <= 0.5 || giveAll <= 0.5) return px;
        const move = Math.min(wantAll, giveAll);
        return px.map((p, i) => p + move * (want[i] / wantAll) - move * (give[i] / giveAll));
    }

    // The columns as they were before a borrowing column's heading grew
    // (_bColWidths): its old heading in its place.
    _bUnborrowed(cols) {
        return cols.map(c => {
            if (!c.borrow) return c;
            const { borrow, ...rest } = c;
            return { ...rest, title: borrow };
        });
    }

    _bBorrowWidths(book, cols, rows, width, padX, o) {
        const was = this._bUnborrowed(cols);
        const W = this._bColWidths(book, was, rows, width, padX, o);
        // each column's content as the layout measured it: a `whole`
        // table's lists on one line where the width holds them all
        const sum = (a) => a.reduce((x, y) => x + y, 0);
        let needWas = this._bColNeeds(book, was, rows, padX);
        if (o.whole) {
            const lists = this._bColNeeds(book, was, rows, padX, true);
            if (sum(lists) <= width) needWas = lists;
        }
        const ctxM = book.measureCtx;
        cols.forEach((c, i) => {
            if (!c.borrow) return;
            const head = (size) => {
                ctxM.font = this._bFont(size, 700);
                return ctxM.measureText(this._bCaps(c.title || '')).width + padX * 2;
            };
            const take = (want, from) => {
                const spare = from.map(j => Math.max(0, W[j] - needWas[j]));
                const all = spare.reduce((a, b) => a + b, 0);
                const got = Math.min(want, all);
                if (got <= 0) return 0;
                from.forEach((j, k) => { W[j] -= got * spare[k] / all; });
                W[i] += got;
                return got;
            };
            // the lenders first, then any column's room beyond its content
            for (const from of [cols.map((d, j) => (d.lend ? j : -1)).filter(j => j >= 0),
                                cols.map((d, j) => j).filter(j => j !== i)]) {
                const want = Math.max(needWas[i], head(SZ.th)) - W[i];
                if (want > 0.5) take(want, from);
            }
        });
        return W;
    }

    // What each column needs so nothing in it is cut: its heading, its
    // widest cell - or, in a column that wraps, its widest piece (its
    // widest whole list where `whole`); a cell that is not a list at the
    // smallest size it shrinks to where `small`.
    _bColNeeds(book, cols, rows, padX, whole = false, small = false) {
        const ctxM = book.measureCtx;
        return cols.map((c, i) => {
            if (c.tick) return 24 + padX * 2;
            // a `headShrink` heading asks only for its room at the smallest
            // size a heading shrinks to before it is cut (_bText's 14)
            ctxM.font = this._bFont(c.headShrink ? 14 : SZ.th, 700);
            let n = c.title ? ctxM.measureText(this._bCaps(c.title)).width + padX * 2 : 0;
            ctxM.font = this._bFont(SZ.cell, 400);
            for (const r of rows) {
                if (r.band !== undefined) continue;
                const cell = (r.cells || [])[i];
                if (cell == null || cell === '') continue;
                // A list column asks for its WIDEST MEMBER, not for the whole
                // list: the list wraps, but a member that will not fit a line
                // has nowhere to go and would be cut ("28× 2fer" in the
                // Screens table's SHARED column).
                const groups = c.inputs && r.inputs && r.inputs[i];
                if (groups && groups.length) {
                    // an input column asks for its widest group whole:
                    // the column's label width, then the widest strand
                    n = Math.max(n, this._bInputsNeed(book, rows, i) + padX * 2);
                    continue;
                }
                const parts = c.parts && r.parts && r.parts[i];
                if (parts && parts.length) {
                    // a strand list asks for its widest strand, swatch and all
                    for (const p of this._bPartPieces(parts)) {
                        n = Math.max(n, ctxM.measureText(p.text).width + padX * 2
                            + (p.swatch ? SWATCH_W : 0));
                    }
                } else if (c.list && whole) {
                    n = Math.max(n, ctxM.measureText(String(cell).trim()).width + padX * 2);
                } else if (c.list) {
                    for (const piece of this._bCellPieces(cell, c.words)) {
                        n = Math.max(n, ctxM.measureText(piece.trim()).width + padX * 2);
                    }
                } else {
                    if (small) ctxM.font = this._bFont(14, 400);
                    n = Math.max(n, ctxM.measureText(String(cell)).width + padX * 2
                        + (c.swatch && r.swatch ? SWATCH_W : 0));
                    if (small) ctxM.font = this._bFont(SZ.cell, 400);
                }
            }
            return n;
        });
    }

    // A table as a list of LINES - a title, a heading, then bands and rows -
    // each knowing its height and how to draw itself at (x, y, w). The
    // packer below lays a block's lines into columns, the head lines
    // repeated wherever a block continues.
    //   spec = { title, note?, width, groups?, cols: [{ title, w, align, tick, list, swatch, rule }],
    //            rows: [ { band: 'text' } | { band: '', halves: [[line, ...], ...] }
    //                    | { cells: [...], bold?, swatch? } ] }
    // `groups` - [{ title, from, to }] - is a heading over a run of
    // columns (the data sheet's PRIMARY and BACKUP halves); a `rule`
    // column draws a vertical rule at its left edge, down the heading and
    // every row, so the halves read as two; a band with `halves` states
    // each group's own unit over its columns, a line each (the box, then
    // its fiber), side by side in one band.
    // A `swatch` column paints the row's swatch ({ base, tracer } - a fiber
    // strand's color and its tracer stripe) in front of its text. A `parts`
    // column paints a swatch in front of EACH strand of the cell where the
    // row carries them - `parts: { [col]: [{ text, swatch? }, ...] }`, the
    // cell's text being those texts joined with " · " - wrapping between
    // strands as a list does; a row without them reads as a list cell.
    // A `words` list column wraps between words rather than at " · "; a
    // `headShrink` column's heading shrinks before the column asks its
    // neighbours for room (_bColNeeds).
    // `titleShrink` lets a long title shrink a little rather than be cut.
    // `whole` (the pull sheet's tables) gives a list column the room for
    // its widest list on one line wherever the width holds them all, and a
    // `shrink` table's headings and cells the room to shrink rather than
    // cut where it cannot hold them at full size (_bColWidths).
    // `width` is the column the block is measured in (COL_W unless the
    // sheet's columns are another size) - a row that has to wrap knows its
    // height there, and a wider column at paint time simply wraps looser.
    // EVERY column stands its heading and its cells on its middle (owner,
    // 2026-10-18: "center every column in every binder table") - a wrapped
    // list each line, a strand list each line with its swatch, an input
    // column its outlined groups, the tick its box; a column's `align` is
    // no longer read. A band over a run of rows still reads from the
    // table's left edge: it heads the table, it is not a column.
    //
    // `fit` (the data sheet's Ports table): every column its CONTENT'S
    // width - its heading or its widest cell, and a band at least its
    // band's (_bFitColWidths) - and the table as wide as that, never
    // stretched across the column it sits in: at fixed shares OUTPUT ran
    // far wider than "S1 A · 1" and HOME RUN's "25'" sat stranded at the
    // left of a wide column (owner, 2026-10-18: "the non centered home
    // runs, and the waste of space in the same table … sizing it
    // dynamically"). Past `width` the columns share it by their needs.
    // The lines carry `naturalW`, the width the table takes.
    _bTableLines(book, spec) {
        const cols = spec.cols || [];
        const padX = 12;
        let mW = spec.width || COL_W;
        let W;
        if (spec.fit) {
            const need = this._bFitColWidths(book, spec, padX);
            const total = need.reduce((a, b) => a + b, 0);
            W = total <= mW ? need
                : this._bColWidths(book, cols.map((c, i) => ({ ...c, w: need[i] })), spec.rows || [], mW, padX);
            mW = Math.min(total, mW);
        } else {
            W = this._bColWidths(book, cols, spec.rows || [], mW, padX,
                                 { whole: !!spec.whole, small: !!spec.whole && !!spec.shrink });
        }
        // a fitted table is drawn at its own width in a wider column
        const tableW = (w) => (spec.fit ? Math.min(w, mW) : w);
        const layout = (w) => {
            const k = w / mW;
            let x = 0;
            return cols.map((c, i) => {
                const cw = W[i] * k;
                // every column stands on its middle, its heading and its
                // cells (owner, 2026-10-18: "center every column in every
                // binder table")
                const out = { x, w: cw, align: 'center', tick: !!c.tick };
                x += cw;
                return out;
            });
        };
        // where a column's text stands: its middle
        const anchor = (c, x) => x + c.x + c.w / 2;
        // A STRAND COLUMN'S ONE LEFT EDGE (owner, 2026-10-20: "i would like
        // it all to be centered but the color/number to all match in the X
        // coordinate"): the strand map's STRAND and FIBER CONNECTIONS' AT
        // THE PROCESSOR / AT THE BREAKOUT stand as one block on the column's
        // middle, as wide as the column's widest strand, and every line
        // starts at the block's left edge - the swatches (or the numbers,
        // on a cable labelled by number) in one line down the column. Each
        // line centred on its own used to set every swatch at a different x.
        const strandBlock = new Map();
        const strandBlockW = (i) => {
            if (strandBlock.has(i)) return strandBlock.get(i);
            const ctxM = book.measureCtx;
            let w = 0;
            for (const r of spec.rows || []) {
                if (r.band !== undefined) continue;
                const weight = r.bold ? 700 : 400;
                const parts = cols[i].parts && r.parts && r.parts[i];
                if (parts && parts.length) {
                    ctxM.font = this._bFont(SZ.cell, weight);
                    for (const piece of this._bPartPieces(parts)) {
                        w = Math.max(w, (piece.swatch ? SWATCH_W : 0) + ctxM.measureText(piece.text).width);
                    }
                } else if (cols[i].swatch) {
                    const cell = (r.cells || [])[i];
                    if (cell == null || cell === '') continue;
                    w = Math.max(w, (r.swatch ? SWATCH_W : 0) + this._bTextWidth(book, cell,
                        { size: SZ.cell, weight: r.swatch ? 700 : weight }));
                }
            }
            strandBlock.set(i, w);
            return w;
        };
        const lines = [];
        if (spec.title) {
            lines.push({ h: H4_H, head: true, draw: (ctx, x, y, cw) => {
                const w = tableW(cw);
                this._bText(book, spec.title, x, y + 30,
                            { size: SZ.h4, weight: 700, upper: true, maxWidth: w,
                              shrink: !!spec.titleShrink });
                ctx.fillStyle = RULE;
                ctx.fillRect(x, y + H4_H - 6, w, 2);
            } });
        }
        // `note`: one line of the table's own text under its title ("Also
        // on BK RACK"), repeated with the head where the block continues.
        if (spec.note) {
            lines.push({ h: ROW_H, head: true, draw: (ctx, x, y, cw) => {
                const w = tableW(cw);
                this._bText(book, spec.note, x, y + 27,
                            { size: SZ.cell, weight: 400, maxWidth: w });
            } });
        }
        const groups = spec.groups || [];
        const spanOf = (L, g) => ({ x: L[g.from].x, w: L[g.to].x + L[g.to].w - L[g.from].x });
        const rules = (ctx, L, x, y, h) => {
            cols.forEach((c, i) => {
                if (!c.rule || !L[i]) return;
                ctx.fillStyle = RULE;
                ctx.fillRect(x + L[i].x - 1, y, 2, h);
            });
        };
        if (groups.length) {
            lines.push({ h: TH_H, head: true, draw: (ctx, x, y, cw) => {
                const w = tableW(cw);
                const L = layout(w);
                for (const g of groups) {
                    const sp = spanOf(L, g);
                    this._bText(book, g.title, x + sp.x + sp.w / 2, y + 28,
                                { size: SZ.th, weight: 700, upper: true, align: 'center',
                                  maxWidth: sp.w - padX * 2, shrink: true });
                    ctx.fillStyle = RULE;
                    ctx.fillRect(x + sp.x + (g.from ? 6 : 0), y + TH_H - 4, sp.w - (g.from ? 6 : 0), 2);
                }
            } });
        }
        const th = { h: TH_H, head: true, draw: (ctx, x, y, cw) => {
            const w = tableW(cw);
            const L = layout(w);
            rules(ctx, L, x, y, TH_H);
            cols.forEach((c, i) => {
                if (c.tick) return;
                const ax = anchor(L[i], x);
                this._bText(book, c.title || '', ax, y + 28,
                            { size: SZ.th, weight: 700, upper: true, align: L[i].align,
                              maxWidth: L[i].w - padX * 2, shrink: true,
                              ...(c.borrow ? { minSize: 8 } : {}) });
            });
            ctx.fillStyle = RULE;
            ctx.fillRect(x, y + TH_H - 4, w, 4);
        } };
        // `bandsLead`: the band over a run of rows - the unit and its fiber,
        // the multi and its run - reads ABOVE the column headings, which
        // follow it under every band (2026-09-26: "should put XD and fiber
        // info above where it says port and home runs etc reads werid
        // otherwise" / "same with distros"). A column the table runs on
        // into starts with the headings again (`contHeads`); a band and its
        // headings are never left at the foot of a column over nothing.
        const lead = !!spec.bandsLead;
        const topBand = (r) => r.band !== undefined && !r.sub;
        const underBand = { ...th, head: false, band: true };
        if (!lead || !(spec.rows || []).length || !topBand(spec.rows[0])) lines.push(th);
        for (const r of spec.rows || []) {
            if (r.halves || r.lines) {
                // A sub-band in halves (each half's snake) keeps the
                // sub-band's look: set in, no fill, a thin rule. A band of
                // `lines` is one stack across the whole width (a unit and
                // its fiber strand by strand, on a sheet with no halves).
                const sub = !!r.sub;
                const ind = sub ? 22 : 0;
                // a group stands on its lines and its gap (_bStackLayout)
                const tall = (list) => { const L = this._bStackLayout(list); return (L.lines - 1) * LIST_H + L.extra; };
                const h = BAND_H + (r.lines ? tall(r.lines) : r.halves.reduce((m, half) => Math.max(m, tall(half)), 0));
                lines.push({ h, band: true, draw: (ctx, x, y, cw) => {
                    const w = tableW(cw);
                    const L = layout(w);
                    if (book.meta.palette === 'printer') {
                        ctx.fillStyle = INK;
                        ctx.fillRect(x + ind, y + 2, w - ind, sub ? 2 : 3);
                    } else if (!sub) {
                        ctx.fillStyle = BAND_BG;
                        ctx.fillRect(x, y, w, h - 4);
                    }
                    rules(ctx, L, x, y, h);
                    if (r.lines) this._bBandStack(book, r.lines, x + ind + padX, y + 31, w - ind - padX * 2);
                    (r.halves || []).forEach((half, j) => {
                        const g = groups[j];
                        if (!g) return;
                        const sp = spanOf(L, g);
                        this._bBandStack(book, half, x + sp.x + ind + padX, y + 31, sp.w - ind - padX * 2);
                    });
                    ctx.fillStyle = RULE;
                    ctx.fillRect(x + ind, y + h - 4, w - ind, sub ? 2 : 4);
                } });
                if (lead && topBand(r)) lines.push(underBand);
                continue;
            }
            if (r.band !== undefined) {
                // A SUB-BAND is a second level inside a band: the snake a
                // run of ports rides, named once over them (2026-09-09).
                // It is set in from the band's own edge and carries no
                // fill, so a reader sees at a glance which heading is the
                // unit and which is the loom hanging off it.
                const sub = !!r.sub;
                const ind = sub ? 22 : 0;
                lines.push({ h: BAND_H, band: true, draw: (ctx, x, y, cw) => {
                    const w = tableW(cw);
                    if (book.meta.palette === 'printer') {
                        ctx.fillStyle = INK;
                        ctx.fillRect(x + ind, y + 2, w - ind, sub ? 2 : 3);
                    } else if (!sub) {
                        ctx.fillStyle = BAND_BG;
                        ctx.fillRect(x, y, w, BAND_H - 4);
                    }
                    this._bText(book, r.band, x + ind + padX, y + 31,
                                { size: SZ.cell, weight: 700, shrink: true,
                                  maxWidth: w - ind - padX * 2 });
                    ctx.fillStyle = RULE;
                    ctx.fillRect(x + ind, y + BAND_H - 4, w - ind, sub ? 2 : 4);
                } });
                if (lead && topBand(r)) lines.push(underBand);
                continue;
            }
            // A LIST column's cell wraps rather than being cut, so the row
            // is as tall as its longest list - measured in the column the
            // block is packed into; a wider column at paint time only ever
            // needs fewer lines.
            const weight = r.bold ? 700 : 400;
            const partsOf = (i) => (cols[i].parts && r.parts && r.parts[i] && r.parts[i].length
                ? r.parts[i] : null);
            const wrapped = cols.map((c, i) => (partsOf(i)
                ? this._bPartLines(book, partsOf(i), weight, W[i] - padX * 2)
                : c.list && (r.cells || [])[i]
                    ? this._bCellLines(book, r.cells[i], SZ.cell, weight,
                                       W[i] - padX * 2, c.list === true ? LIST_LINES : c.list, c.words)
                    : null));
            // AN INPUT COLUMN (the Breakout boxes table's FIBER): each input
            // a group - its label centred beside its strands, outlined -
            // and the row as tall as its groups; every other cell of that
            // row sits centred on them rather than hanging at the top.
            const inputsAt = cols.findIndex((c, i) => c.inputs && r.inputs && r.inputs[i] && r.inputs[i].length);
            const rowLines = wrapped.reduce((m, ls, i) => (i === inputsAt ? m : Math.max(m, ls ? ls.length : 1)), 1);
            const inLay = inputsAt >= 0 ? this._bInputsLayout(r.inputs[inputsAt]) : null;
            const h = inLay ? Math.max(ROW_H + (rowLines - 1) * LIST_H, inLay.height)
                : ROW_H + (rowLines - 1) * LIST_H;
            const cellLines = (i) => (partsOf(i) ? this._bPartLines(book, partsOf(i), weight, W[i] - padX * 2).length
                : wrapped[i] ? wrapped[i].length : 1);
            lines.push({ h, draw: (ctx, x, y0, cw) => {
                const w = tableW(cw);
                const L = layout(w);
                rules(ctx, L, x, y0, h);
                if (r.bold) { ctx.fillStyle = RULE; ctx.fillRect(x, y0, w, 3); }
                (r.cells || []).forEach((cell, i) => {
                    if (!L[i]) return;
                    if (i === inputsAt) {
                        const head = this._bInputsHead(book, spec.rows, i);
                        this._bInputsCell(book, ctx, r.inputs[inputsAt], inLay, x + L[i].x + padX, y0,
                                          L[i].w - padX * 2, head, weight,
                                          this._bInputsWide(book, spec.rows, i, head));
                        return;
                    }
                    const y = inLay ? y0 + Math.max(0, (h - ROW_H - (cellLines(i) - 1) * LIST_H) / 2) : y0;
                    if (L[i].tick) {
                        ctx.strokeStyle = INK;
                        ctx.lineWidth = 2;
                        ctx.strokeRect(x + L[i].x + (L[i].w - 24) / 2, y + 7, 24, 24);
                        return;
                    }
                    const ax = anchor(L[i], x);
                    const maxWidth = L[i].w - padX * 2;
                    if (partsOf(i)) {
                        this._bPartsCell(book, ctx, this._bPartLines(book, partsOf(i), weight, maxWidth),
                                         x + L[i].x + padX, y, maxWidth, weight, true, strandBlockW(i));
                        return;
                    }
                    if (wrapped[i]) {
                        const ls = this._bCellLines(book, cell, SZ.cell, weight, maxWidth, rowLines,
                                                    cols[i].words);
                        const drawn = ls.map((t, k) => this._bText(book, t, ax, y + 27 + k * LIST_H,
                            { size: SZ.cell, weight, align: L[i].align, maxWidth,
                              shrink: true, log: false }));
                        // Logged as ONE text, the whole cell, the way a
                        // two-line cell is: a reader of the sheet's texts
                        // sees one entry per cell however it wrapped.
                        if (book.log && book.page && book.page.painting) {
                            const t = drawn.join(' ');
                            book.log.texts.push(t);
                            if (book.log.textInfo) {
                                book.log.textInfo.push({ text: t, size: SZ.cell, weight });
                            }
                        }
                        return;
                    }
                    // A table that carries whole names in its cells (the
                    // data sheet's PRIMARY / BACKUP) shrinks a long one a
                    // little before it is cut, the way a heading does; a
                    // cell saying two things ("A / B" - HOME RUN with a
                    // backup end) goes to two lines rather than being cut.
                    if (cols[i].swatch && (r.swatch || cell != null && cell !== '')) {
                        // the strand's cell tinted its own colour and its
                        // name bold; the name stays, so a black-and-white
                        // print still says which strand it is
                        if (r.swatch) {
                            ctx.fillStyle = this._bTint(r.swatch.base, 0.24);
                            ctx.fillRect(x + L[i].x + 3, y + 3, L[i].w - 6, h - 7);
                        }
                        // the column's strands stand as one block on its
                        // middle (strandBlockW), every swatch - or number -
                        // at the block's left edge, the name never past the
                        // cell
                        const lead = r.swatch ? SWATCH_W : 0;
                        const o = { size: SZ.cell, weight: r.swatch ? 700 : weight, align: 'left',
                                    maxWidth: maxWidth - lead, shrink: !!spec.shrink };
                        const sx = Math.max(x + L[i].x + padX, ax - Math.min(maxWidth, strandBlockW(i)) / 2);
                        if (r.swatch) this._bSwatch(ctx, r.swatch, sx, y + 27);
                        this._bText(book, cell, sx + lead, y + 27, o);
                        return;
                    }
                    const o = { size: SZ.cell, weight, align: L[i].align,
                                maxWidth, shrink: !!spec.shrink };
                    if (spec.shrink) this._bTextTwoLines(book, cell, ax, y + 27, o);
                    else this._bText(book, cell, ax, y + 27, o);
                });
                if (!r.bold) { ctx.fillStyle = FAINT; ctx.fillRect(x, y0 + h - 2, w, 2); }
            } });
        }
        // where the table runs on into another column, its heads again -
        // the headings included, which a band-led table otherwise prints
        // only under its bands
        if (lead) lines.contHeads = [...lines.filter(l => l.head && l !== th), th];
        if (spec.fit) lines.naturalW = mW;
        return lines;
    }

    // A fitted table's columns (`fit`, _bTableLines): each its content's
    // width (_bColNeeds), then a group of columns - PRIMARY, BACKUP - at
    // least as wide as the band standing over it (the unit's line, its
    // fiber groups, a snake's heading), a table without groups at least
    // as wide as its widest band; a band's extra spread evenly over the
    // columns under it, so a band is never shrunk to fit its columns.
    _bFitColWidths(book, spec, padX) {
        const cols = spec.cols || [];
        const groups = spec.groups || [];
        const need = this._bColNeeds(book, cols, spec.rows || [], padX).map(n => Math.ceil(n));
        const ctxM = book.measureCtx;
        // a band's stack as _bBandStack draws it: its first line bold, an
        // input group its label column and widest strand in its outline
        const stackW = (list) => {
            let w = 0;
            (list || []).forEach((t, k) => {
                if (t && typeof t === 'object') return;
                ctxM.font = this._bFont(SZ.cell, k ? 400 : 700);
                w = Math.max(w, ctxM.measureText(String(t == null ? '' : t)).width);
            });
            const gs = (list || []).filter(t => t && typeof t === 'object' && t.group).map(t => t.group);
            if (gs.length) {
                const head = this._bGroupsHead(ctxM, gs, SZ.cell);
                w = Math.max(w, this._bGroupsWide(ctxM, gs, SZ.cell, head) + GROUP_PAD * 2);
            }
            return w;
        };
        const widen = (from, to, want) => {
            const have = need.slice(from, to + 1).reduce((a, b) => a + b, 0);
            if (want <= have) return;
            const add = (want - have) / (to - from + 1);
            for (let i = from; i <= to; i++) need[i] = Math.ceil(need[i] + add);
        };
        for (const r of spec.rows || []) {
            const ind = r.sub ? 22 : 0;
            if (r.halves) {
                r.halves.forEach((half, j) => {
                    if (groups[j]) widen(groups[j].from, groups[j].to, stackW(half) + ind + padX * 2);
                });
            } else if (r.lines) {
                widen(0, cols.length - 1, stackW(r.lines) + ind + padX * 2);
            } else if (r.band) {
                widen(0, cols.length - 1, stackW([r.band]) + ind + padX * 2);
            }
        }
        return need;
    }

    // A fiber strand's swatch, SWATCH square, at x and centred on the text
    // standing on `baseline`: its color, the tracer past 12 as a stripe
    // across its middle, ringed in ink so White reads on white paper. The
    // tracer is a rect, not a filled path - the recorder writes rects and
    // lines only, and the corner triangle it used to be never reached the
    // PDF.
    _bSwatch(ctx, sw, x, baseline) {
        const S = SWATCH;
        const y = baseline - 8 - S / 2;
        ctx.fillStyle = sw.base || '#777777';
        ctx.fillRect(x, y, S, S);
        if (sw.tracer) {
            ctx.fillStyle = sw.tracer;
            ctx.fillRect(x, y + S * 0.36, S, S * 0.28);
        }
        ctx.strokeStyle = INK;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x, y, S, S);
    }

    // A colour mixed toward the paper: `k` of the colour, the rest white.
    _bTint(hex, k) {
        const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ''));
        if (!m) return '#eeeeee';
        const n = parseInt(m[1], 16);
        const ch = (v) => Math.round(255 - (255 - v) * k).toString(16).padStart(2, '0');
        return `#${ch((n >> 16) & 255)}${ch((n >> 8) & 255)}${ch(n & 255)}`;
    }

    // A band's lines stacked from `baseline`, LIST_H apart: a text line as
    // it always read (the first bold, each shrinking alone before it is
    // cut), and an input group ({ group } - _bBoxBandLines) on as many lines
    // as it needs, a GROUP_GAP ahead of it: its strands a line each, its
    // label - the input over its cable - centred beside them, the lot in a
    // thin outline (_bDrawGroup). Every group's strands stand in one column
    // and the groups shrink together where the widest will not fit.
    _bBandStack(book, lines, x, baseline, maxWidth) {
        const ctx = book.ctx;
        const groups = lines.filter(t => t && typeof t === 'object' && t.group).map(t => t.group);
        let size = SZ.cell, head = 0;
        if (groups.length) {
            const measure = (sz) => {
                head = this._bGroupsHead(ctx, groups, sz);
                return this._bGroupsWide(ctx, groups, sz, head) + GROUP_PAD * 2;
            };
            while (size > 14 && measure(size) > maxWidth) size -= 1;
            measure(size);
        }
        const lay = this._bStackLayout(lines);
        lines.forEach((t, k) => {
            const y = baseline + lay.y[k];
            if (!t || typeof t !== 'object') {
                this._bText(book, t, x, y, { size: SZ.cell, weight: k ? 400 : 700, shrink: true, maxWidth });
                return;
            }
            this._bDrawGroup(book, ctx, t.group, x + GROUP_PAD, y, head, maxWidth - GROUP_PAD * 2, size, 400);
        });
    }

    // Where each entry of a band's stack stands from its first baseline: a
    // text line one LIST_H, a group its lines (_bGroupLines) and a
    // GROUP_GAP ahead of it, so one input's outline never touches the next
    // (nor the box's line above it). `lines` is the stack's height in
    // lines and `extra` what the gaps add to it.
    _bStackLayout(entries) {
        const y = [];
        let at = 0, n = 0;
        (entries || []).forEach((t) => {
            const g = t && typeof t === 'object' && t.group;
            if (g) at += GROUP_GAP;
            y.push(at + n * LIST_H);
            n += g ? this._bGroupLines(g) : 1;
        });
        return { y, lines: Math.max(1, n), extra: at };
    }

    // The label column a set of groups needs: its widest input or cable
    // word, and the gap before the strands.
    _bGroupsHead(ctx, groups, size) {
        ctx.font = this._bFont(size, 400);
        const gap = ctx.measureText('  ').width;
        let w = 0;
        for (const g of groups) {
            if (!(g.strands && g.strands.length)) continue;
            for (const t of [g.head, g.sub]) if (t) w = Math.max(w, ctx.measureText(t).width + gap);
        }
        return w;
    }

    // The widest group: the label column, then its widest strand - a group
    // of words its words.
    _bGroupsWide(ctx, groups, size, head) {
        ctx.font = this._bFont(size, 400);
        const sw = SWATCH_W * size / SZ.cell;
        let w = 0;
        for (const g of groups) {
            if (!(g.strands && g.strands.length)) { w = Math.max(w, ctx.measureText(String(g.text || '')).width); continue; }
            for (const st of g.strands) w = Math.max(w, head + (st.swatch ? sw : 0) + ctx.measureText(st.text).width);
        }
        return w;
    }

    // ONE INPUT GROUP drawn, its first line's baseline at `top`: the
    // strands a line each in the column `head` leaves, each its swatch and
    // its name; the input over its cable centred down those lines; the
    // thin outline round the lot. A group of words alone ({ text }) is its
    // words on one line, outlined the same. Returns the texts it drew.
    // `log` false where the caller logs the cell as one text (a table's).
    // `boxW`: the outline that wide rather than the group's own (a centred
    // input column draws every group's outline alike, _bInputsCell).
    _bDrawGroup(book, ctx, g, x, top, head, maxWidth, size, weight, log = true, boxW = 0) {
        const drawn = [];
        const lines = this._bGroupLines(g);
        const bottom = top + (lines - 1) * LIST_H;
        if (!(g.strands && g.strands.length)) {
            drawn.push(this._bText(book, g.text || '', x, top, { size, weight, maxWidth, shrink: true, log }));
            ctx.font = this._bFont(size, weight);
            this._bGroupOutline(ctx, x, top, bottom,
                                boxW || Math.min(maxWidth, ctx.measureText(String(g.text || '')).width), size);
            return drawn;
        }
        const label = [g.head, g.sub].filter(Boolean);
        const mid = (top + bottom) / 2;
        label.forEach((t, k) => {
            const y = mid + (k - (label.length - 1) / 2) * LIST_H;
            drawn.push(this._bText(book, t, x, y, { size, weight, maxWidth: Math.max(1, head), shrink: true, log }));
        });
        const sw = SWATCH_W * size / SZ.cell;
        let wide = 0;
        g.strands.forEach((st, k) => {
            const y = top + k * LIST_H;
            let sx = x + head;
            if (st.swatch) { this._bSwatch(ctx, st.swatch, sx, y); sx += sw; }
            drawn.push(this._bText(book, st.text, sx, y,
                { size, weight, maxWidth: Math.max(1, x + maxWidth - sx), shrink: true, log }));
            ctx.font = this._bFont(size, weight);
            wide = Math.max(wide, (st.swatch ? sw : 0) + ctx.measureText(st.text).width);
        });
        this._bGroupOutline(ctx, x, top, bottom, boxW || Math.min(maxWidth, head + wide), size);
        return drawn;
    }

    // The widest group in an input column (_bGroupsWide over every row's
    // groups), its label column `head` included - the width a centred
    // column draws every outline at.
    _bInputsWide(book, rows, i, head) {
        return this._bGroupsWide(book.measureCtx, (rows || []).flatMap(r => (r.inputs || {})[i] || []), SZ.cell, head);
    }

    // AN INPUT COLUMN'S CELL (the Breakout boxes table's FIBER): its groups
    // (_bBoxInputGroups) from the row's top, each on its lines, a
    // GROUP_GAP between groups; the row's height to hold them.
    _bInputsLayout(groups) {
        const first = 31;
        let k = 0;
        const at = groups.map((g, gi) => {
            const n = this._bGroupLines(g);
            const from = first + k * LIST_H + gi * GROUP_GAP;
            k += n;
            return { from, to: from + (n - 1) * LIST_H };
        });
        const last = at.length ? at[at.length - 1].to : first;
        return { at, height: last + 8 + 6 };
    }

    // The widest label in an input column, so every row's strands stand
    // in one column under one another.
    _bInputsHead(book, rows, i) {
        return this._bGroupsHead(book.measureCtx, (rows || []).flatMap(r => (r.inputs || {})[i] || []), SZ.cell);
    }

    // What an input column needs: the label column, its widest strand, and
    // the outline's pad either side.
    _bInputsNeed(book, rows, i) {
        const groups = (rows || []).flatMap(r => (r.inputs || {})[i] || []);
        const head = this._bGroupsHead(book.measureCtx, groups, SZ.cell);
        return this._bGroupsWide(book.measureCtx, groups, SZ.cell, head) + GROUP_PAD * 2;
    }

    // An input column's cell drawn at (ax, y), logged as ONE text, the
    // whole cell, the way a list cell is. `wide` (a centred column): every
    // group's outline that wide - the column's widest group - and the lot
    // standing on the cell's middle, so the outlines line up one under
    // another and their labels and strands with them.
    _bInputsCell(book, ctx, groups, lay, ax, y, maxWidth, head, weight, wide = 0) {
        const drawn = [];
        const inner = maxWidth - GROUP_PAD * 2;
        const boxW = wide > 0 ? Math.min(inner, wide) : 0;
        const off = boxW ? Math.max(0, (inner - boxW) / 2) : 0;
        groups.forEach((g, gi) => {
            drawn.push(...this._bDrawGroup(book, ctx, g, ax + GROUP_PAD + off, y + lay.at[gi].from, head,
                                           inner - off, SZ.cell, weight, false, boxW));
        });
        if (book.log && book.page && book.page.painting) {
            const t = drawn.join(' ');
            book.log.texts.push(t);
            if (book.log.textInfo) book.log.textInfo.push({ text: t, size: SZ.cell, weight });
        }
    }

    // The thin outline round one input and its strands: from above the
    // first line's swatch to below the last line's text, `w` wide from x.
    _bGroupOutline(ctx, x, firstBaseline, lastBaseline, w, size = SZ.cell) {
        const S = SWATCH * size / SZ.cell;
        ctx.strokeStyle = MUTED;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x - GROUP_PAD, firstBaseline - S + 1 - GROUP_PAD / 2,
                       w + GROUP_PAD * 2, lastBaseline - firstBaseline + S + GROUP_PAD + 4);
    }

    // A `parts` cell's pieces as drawn: each strand's text with the " ·"
    // that says another follows on the same line (kept at the end of a line
    // that wraps, the way a list cell keeps its separator) - none before a
    // `brk` part, which starts a line of its own, so a strand-to-a-line
    // list reads "1 Blue" over "2 Orange" (2026-10-17) - and its swatch.
    _bPartPieces(parts) {
        return parts.map((p, j) => ({
            text: String(p.text) + (j < parts.length - 1 && !(parts[j + 1] || {}).brk ? ' ·' : ''),
            swatch: p.swatch || null, brk: !!p.brk }));
    }

    // A `parts` cell onto lines no wider than maxWidth: as many strands per
    // line as fit, a strand never split, a `brk` part on a new line. Every
    // strand is kept - a strand list is a link's two (an MTP's two and
    // "crosses inside").
    _bPartLines(book, parts, weight, maxWidth) {
        const ctxM = book.measureCtx;
        ctxM.font = this._bFont(SZ.cell, weight);
        const gap = ctxM.measureText(' ').width;
        const lines = [];
        let cur = [];
        let curW = 0;
        for (const p of this._bPartPieces(parts)) {
            const w = (p.swatch ? SWATCH_W : 0) + ctxM.measureText(p.text).width;
            if (cur.length && (p.brk || curW + gap + w > maxWidth)) {
                lines.push(cur);
                cur = [p];
                curW = w;
            } else {
                curW += (cur.length ? gap : 0) + w;
                cur.push(p);
            }
        }
        if (cur.length) lines.push(cur);
        return lines;
    }

    // A `parts` cell drawn: line by line, each strand its swatch then its
    // name, from the cell's left edge `ax` - or, `center`, as one block on
    // the cell's middle with every line starting at the block's left edge,
    // so the swatches stand in one line (2026-10-20). `blockW` is the
    // block's width - the column's widest line, so the whole column lines
    // up (_bTableLines' strandBlockW) - else this cell's widest. Logged as
    // ONE text, the whole cell, as a list cell is.
    _bPartsCell(book, ctx, lines, ax, y, maxWidth, weight, center = false, blockW = null) {
        const drawn = [];
        let left = ax;
        if (center) {
            ctx.font = this._bFont(SZ.cell, weight);
            const gap = ctx.measureText(' ').width;
            const widest = lines.reduce((m, line) => Math.max(m, line.reduce((s, p, j) => s + (j ? gap : 0)
                + (p.swatch ? SWATCH_W : 0) + ctx.measureText(p.text).width, 0)), 0);
            const bw = Math.max(widest, blockW || 0);
            left = ax + Math.max(0, (maxWidth - bw) / 2);
        }
        lines.forEach((line, k) => {
            let cx = left;
            line.forEach((p, j) => {
                if (j) {
                    ctx.font = this._bFont(SZ.cell, weight);
                    cx += ctx.measureText(' ').width;
                }
                if (p.swatch) {
                    this._bSwatch(ctx, p.swatch, cx, y + 27 + k * LIST_H);
                    cx += SWATCH_W;
                }
                const t = this._bText(book, p.text, cx, y + 27 + k * LIST_H,
                    { size: SZ.cell, weight, maxWidth: Math.max(1, ax + maxWidth - cx),
                      shrink: true, log: false });
                drawn.push(t);
                cx += ctx.measureText(t).width;
            });
        });
        if (book.log && book.page && book.page.painting) {
            const t = drawn.join(' ');
            book.log.texts.push(t);
            if (book.log.textInfo) book.log.textInfo.push({ text: t, size: SZ.cell, weight });
        }
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
        // The key column is 150 wide, and wider only where a key would
        // reach its value: "Load @ 208 V" in the cell's bold is ~157 and
        // printed its V into the amps at 150. Measured in the bold the
        // key is drawn in; a key that leaves 4 of air (Redundancy, ~144)
        // keeps the column every block has always had.
        const ctxK = book.measureCtx;
        ctxK.font = this._bFont(SZ.cell, 700);
        const widest = pairs.reduce((m, [k]) => Math.max(m, ctxK.measureText(String(k)).width), 0);
        const keyW = widest > 150 - 4 ? Math.ceil(widest) + 16 : 150;
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
    // `colH` is one height for every column, or a function of the
    // column's index for columns of different heights (the wrap layout's
    // short columns beside the map and tall ones under it).
    // `wholeUnder` (the wrap layout's) keeps every block of that many
    // lines or fewer whole - the Facts, the Cables - moving it to the next
    // column, or to `rest`, rather than splitting it: only a long table
    // runs on from one column to the next.
    //   { cols: [{ h, items: [{ line, y }] }], rest: [{ lines }] }
    _bPack(blocks, colH0, maxCols, wholeUnder = 0) {
        const heightOf = typeof colH0 === 'function' ? colH0 : () => colH0;
        const cols = [];
        let col = null, colH = 0;
        const open = () => {
            if (cols.length >= maxCols) return false;
            colH = heightOf(cols.length);
            col = { h: 0, items: [] };
            cols.push(col);
            return true;
        };
        const rest = [];
        const queue = blocks.filter(b => b && (b.lines || []).length)
            .map(b => ({ lines: b.lines.slice(), contHeads: b.contHeads || b.lines.contHeads || null,
                         minW: (b && b.minW) || 0 }));
        while (queue.length) {
            const block = queue[0];
            // the lines a continuation starts with: a table's own list
            // where it has one (a band-led table's headings), else its
            // head lines
            const heads = block.contHeads || block.lines.filter(l => l.head);
            const total = block.lines.reduce((s, l) => s + l.h, 0);
            if (!col && !open()) break;
            let y = col.items.length ? col.h + BLOCK_GAP : 0;
            if (block.lines.length <= wholeUnder && y + total > colH) {
                if (!open()) break;
                continue;
            }
            if (col.items.length && y + total > colH
                    && total <= (cols.length < maxCols ? heightOf(cols.length) : colH)) {
                // whole in the next column rather than split here - judged
                // by THAT column's height, which in a wrap layout is not
                // this one's
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
        // a block running on keeps the column it asked for (minW): a Ports
        // table on its "(cont.)" sheet was squeezed into COL_W
        for (const b of queue) rest.push({ lines: b.lines, contHeads: b.contHeads, ...(b.minW ? { minW: b.minW } : {}) });
        return { cols, rest };
    }

    // The layout of a continuation's drawing area - tables only: the
    // blocks across the whole area in as many columns as fit its width
    // (widened to share it). Whatever the sheet cannot hold is
    // `pack.rest`, for the next. A block may ask for a wider column
    // (`minW` - the data sheet's Ports table, six columns of whole
    // names); every column on the sheet is then that wide.
    _bLayout(book, blocks) {
        const da = book.geo.da;
        const colW = Math.max(COL_W, ...blocks.map(b => (b && b.minW) || 0));
        const across = Math.max(1, Math.floor((da.w + COL_GAP) / (colW + COL_GAP)));
        const wide = (da.w - (across - 1) * COL_GAP) / across;
        const pack = this._bPack(blocks, da.h, across);
        return { kind: 'tables', cols: across, colW: wide, top: da.y, pack,
                 colX: (i) => da.x + i * (wide + COL_GAP), mapArea: null };
    }

    // The fill scale for a drawing of `extent` (base page units) in the
    // drawing area: the largest uniform scale that keeps it inside, up to
    // FILL_CAP, never under 1 (a drawing that already fills stays as it
    // is). Floored to a thousandth so the scaled extent never overshoots.
    _bFillScale(book, extent) {
        const da = book.geo.da;
        const v = Math.min(FILL_CAP, da.w / Math.max(1, extent.w), da.h / Math.max(1, extent.h));
        return Math.max(1, Math.floor(v * 1000) / 1000);
    }

    // The map's geometry in `area`, at base, without painting: the sheet
    // being planned or painted is untouched (the dry context measures,
    // nothing logs).
    _bMeasureMap(book, spec, area) {
        if (typeof spec.measure !== 'function') return null;
        const savedCtx = book.ctx, savedPage = book.page;
        book.ctx = this._bDryCtx(book.measureCtx);
        book.page = null;
        try { return spec.measure(area) || null; } finally { book.ctx = savedCtx; book.page = savedPage; }
    }

    // The layout of a map sheet's drawing area for `blocks`, its fill
    // scale and its coverage. COVERAGE DECIDES (2026-09-08, on his buddy's
    // 9 x 5 IMAG walls at Tabloid: the map filled the width, the tables
    // sat at 1x in one column and the lower half of the sheet was empty;
    // on ARCH C the map was near its cap and the tables tiny under it -
    // "screens can enlarge and text can be bigger if it fills the space.
    // only get this small when there is tons of info"). Two layouts are
    // evaluated, each with the TABLES' type scale s in [1, FILL_CAP]
    // chosen for it, the map taking the room the tables leave - never the
    // other way round - and keeping at least MAP_MIN_FRAC of the area:
    //   side   - map left, tables right in k columns of their base width
    //            (the fewest that hold them whole, never past half the
    //            width): s = min(FILL_CAP, da.h / tablesH, the width the
    //            map's share leaves / (tablesW + gap)); the map fits the
    //            remaining width and the height over its bubble, zoom
    //            capped at 3x on the page
    //   stack  - map on top at full width, the tables under it side by
    //            side, one column per block (spread over the columns that
    //            fit when there are more blocks than columns, _bSpread):
    //            s = min(FILL_CAP, da.w / the row's width, the height the
    //            map's share leaves / (the tallest column + bubble +
    //            gap)); the map takes the height the row leaves
    // coverage = (the map's ink - the wall with its gutters - plus the
    // tables' box at s - their width by their tallest column) / the
    // drawing area; the larger wins, stack on a tie. A sheet whose tables fit at 1 in neither is "tons of info": it
    // stays at 1, the map over the tables in the columns that fit, the
    // rest (pack.rest) continuing on the next sheet.
    //
    // The map is painted in PAGE units (its zoom on the page; its rulers
    // and brackets at their inch sizes - the renderer's own labels grow
    // with the wall, which IS "screens can enlarge"); the tables and the
    // bubble are painted under the fill (_bPage's `scaled`) from BASE
    // coordinates, so `top`, `colW`, `colX` are base units and `toBase`
    // maps a page point into them. `mapArea` is page units.
    _bMapLayout(book, spec, blocks) {
        const da = book.geo.da;
        const colW = Math.max(COL_W, ...blocks.map(b => (b && b.minW) || 0));
        const across = Math.max(1, Math.floor((da.w + COL_GAP) / (colW + COL_GAP)));
        const GUT = spec.gutter || MAP_GUTTER;
        const gutW = GUT.left + GUT.right, gutH = GUT.top + GUT.bottom;
        const tallest = (pack) => pack.cols.reduce((m, c) => Math.max(m, c.h), 0);
        const clamp = (v) => Math.max(1, Math.min(FILL_CAP, Math.floor(v * 1000) / 1000));
        const minW = Math.round(da.w * MAP_MIN_FRAC), minH = Math.round(da.h * MAP_MIN_FRAC);
        const area = da.w * da.h;
        // The wall's own size, from one measure; then its fit in a room -
        // the very arithmetic _bMap does, so the layout's numbers are the
        // paint's.
        const probe = this._bMeasureMap(book, spec, { x: da.x, y: da.y, w: da.w, h: da.h });
        const ww = probe && probe.zoom > 0 ? probe.wall.w / probe.zoom : 0;
        const wh = probe && probe.zoom > 0 ? probe.wall.h / probe.zoom : 0;
        const fit = (roomW, roomH) => {
            if (!(ww > 0 && wh > 0)) return { zoom: 0, w: Math.min(roomW, gutW), h: gutH };
            const zoom = Math.max(0, Math.min((roomW - gutW) / ww, (roomH - gutH) / wh, MAP_ZOOM_CAP));
            return { zoom, w: Math.ceil(ww * zoom) + gutW, h: Math.round(wh * zoom + gutH) };
        };
        const identity = (x, y) => [x, y];
        const toBase = (s) => (s > 1 ? (x, y) => [da.x + (x - da.x) / s, da.y + (y - da.y) / s] : identity);
        // THE WALL COMES FIRST, THE TYPE GROWS INTO WHAT IS LEFT (2026-09-20).
        // The type used to be swept down from its largest, giving room back
        // to the map only where that filled more of the sheet's HEIGHT. A
        // short table therefore grew until it filled the height by itself
        // and the wall never got its room back: on live show B, SR - MAIN
        // DATA (8 ports) printed its table at 1.7x beside a wall a third of
        // the sheet wide, while SR - MAIN POWER (22 circuits, a table that
        // cannot grow) printed the same wall at nearly twice the size - "power
        // is the size a wall of this size should be. not sure why the text
        // is so much bigger on the data screen with less info". So the map
        // takes the zoom it gets with the tables at 1, and the type grows
        // only while that costs the map nothing (a wall stopped by the
        // sheet's height has width to spare beside it; a wall stopped by
        // the width has height to spare under it).
        // "Costs nothing" is within 2 per cent: the view bubble under the map
        // grows with the type, so every step of type costs a wall stopped by
        // the height a sliver, and a half per cent rule froze the type at
        // 1.09 beside a small tall wall with half the sheet empty.
        const FREE = 0.98;
        const grow = (sMax, zoomOf) => {
            const top = clamp(sMax);
            const z1 = zoomOf(1);
            if (!(z1 > 0)) return top;
            for (let v = Math.round(top * 100); v > 100; v--) {
                if (zoomOf(v / 100) >= z1 * FREE) return v / 100;
            }
            return 1;
        };

        // side: the fewest columns that hold the tables whole
        let side = null;
        const kmax = Math.floor((da.w / 2 + COL_GAP) / (colW + COL_GAP));
        for (let k = 1; k <= kmax && !side; k++) {
            const pack = this._bPack(blocks, da.h, k);
            if (pack.rest.length || !pack.cols.length) continue;
            const tablesW = k * colW + (k - 1) * COL_GAP, tablesH = tallest(pack);
            const sideZoom = (v) => fit(da.w - (tablesW + COL_GAP) * v, da.h - BUBBLE_H * v).zoom;
            const sideTop = Math.min(FILL_CAP, da.h / tablesH, (da.w - minW) / (tablesW + COL_GAP));
            let s = grow(sideTop, sideZoom);
            // A LONG table beside the wall may still grow to the foot of the
            // sheet: where the tables are the taller of the two, each step
            // of type fills more of the sheet, and it is taken while the
            // wall keeps FILL_KEEP of its best size. A SHORT table gains the
            // sheet nothing by growing (the wall is the taller, and only
            // gets shorter), so it stays where the wall left it - which is
            // what keeps a screen's Data wall the size of its Power wall.
            const zBest = sideZoom(1);
            for (let v = Math.round(s * 100) + 1; v <= Math.floor(clamp(sideTop) * 100); v++) {
                const t = v / 100;
                const g = fit(da.w - (tablesW + COL_GAP) * t, da.h - BUBBLE_H * t);
                if (tablesH * t <= g.h + BUBBLE_H * t) break;          // the wall is the taller: no gain
                if (!(g.zoom >= zBest * FILL_KEEP)) break;            // costs the wall too much
                s = t;
            }
            const roomW = da.w - (tablesW + COL_GAP) * s, roomH = da.h - BUBBLE_H * s;
            const m = fit(roomW, roomH);
            side = { kind: 'side', cols: k, colW, top: da.y, pack, scale: s,
                     mapArea: { x: da.x, y: da.y, w: roomW, h: roomH },
                     extent: { w: da.w, h: Math.max(m.h + BUBBLE_H * s, tablesH * s) },
                     coverage: (m.w * m.h + tablesW * tablesH * s * s) / area,
                     map: { zoom: m.zoom, w: m.w, h: m.h },
                     colX: (i) => da.x + roomW / s + COL_GAP + i * (colW + COL_GAP),
                     toBase: toBase(s) };
        }

        // stack: the blocks side by side under the map
        let stack = null;
        const spread = this._bSpread(blocks, across);
        const colH1 = da.h - minH - BUBBLE_H - COL_GAP;
        if (spread && tallest(spread) <= colH1) {
            const k = spread.cols.length;
            const rowW = k * colW + (k - 1) * COL_GAP, tablesH = tallest(spread);
            const stackZoom = (v) => fit(da.w, da.h - (tablesH + BUBBLE_H + COL_GAP) * v).zoom;
            const s = grow(Math.min(FILL_CAP, da.w / rowW,
                                    (da.h - minH) / (tablesH + BUBBLE_H + COL_GAP)), stackZoom);
            const mapH = da.h - (tablesH + BUBBLE_H + COL_GAP) * s;
            const m = fit(da.w, mapH);
            const wide = (da.w / s - (k - 1) * COL_GAP) / k;
            stack = { kind: 'stack', cols: k, colW: wide, top: da.y + m.h / s + BUBBLE_H + COL_GAP, pack: spread, scale: s,
                      mapArea: { x: da.x, y: da.y, w: da.w, h: mapH },
                      extent: { w: Math.max(m.w, da.w), h: m.h + (BUBBLE_H + COL_GAP + tablesH) * s },
                      coverage: (m.w * m.h + rowW * tablesH * s * s) / area,
                      map: { zoom: m.zoom, w: m.w, h: m.h },
                      colX: (i) => da.x + i * (wide + COL_GAP),
                      toBase: toBase(s) };
        }
        // wrap: the tables around the map (2026-09-26, "look at page 3 here
        // we are wasting tons of space due to the shape of the screen" /
        // "trim and wrap if need be"). Side and stack keep a block whole in
        // its column, so a long Ports table beside a wide, short wall held
        // the map to the width it left and emptied the sheet under it, and
        // under the wall it held the map to the height it left. Wrap splits
        // the tables across columns the packer's way: first the columns
        // BESIDE the map, as tall as the map and its bubble, then the
        // columns across the full width UNDER it. For each count of columns
        // beside (none is a stack that splits), the map's height is the
        // tallest whose leftovers still hold every table; the type grows the
        // way it does in side and stack, while it costs the map nothing.
        const wrapAt = (k1, v) => {
            const bubble = BUBBLE_H * v;
            const roomW = da.w - k1 * (colW + COL_GAP) * v;
            if (roomW < minW) return null;
            const acrossU = Math.max(1, Math.floor((da.w / v + COL_GAP) / (colW + COL_GAP)));
            const layFor = (mapH) => {
                const m = fit(roomW, mapH);
                const besideW = (da.w - m.w) / v - COL_GAP;
                const kB = k1 ? Math.max(0, Math.floor((besideW + COL_GAP) / (colW + COL_GAP))) : 0;
                const wideB = kB ? (besideW - (kB - 1) * COL_GAP) / kB : 0;
                const besideH = (m.h + bubble) / v;
                const underH = (da.h - m.h - bubble) / v - COL_GAP;
                const heights = (i) => (i < kB ? besideH : underH);
                const pack = this._bPack(blocks, heights, kB + (underH > 0 ? acrossU : 0), WRAP_WHOLE);
                return { m, kB, wideB, besideH, underH, pack };
            };
            let lo = minH, hi = da.h - bubble, best = null;
            const first = layFor(lo);
            if (first.pack.rest.length || !first.pack.cols.length) return null;
            best = first;
            for (let n = 0; n < 14 && hi - lo > 2; n++) {
                const mid = (lo + hi) / 2;
                const t = layFor(mid);
                if (!t.pack.rest.length && t.pack.cols.length) { best = t; lo = mid; } else hi = mid;
            }
            return best.m.zoom > 0 ? { ...best, k1, v } : null;
        };
        const wrapBest = (v) => {
            let b = null;
            for (let k1 = 0; k1 <= kmax; k1++) {
                const t = wrapAt(k1, v);
                if (t && (!b || t.m.zoom > b.m.zoom)) b = t;
            }
            return b;
        };
        let wrap = null;
        const w1 = wrapBest(1);
        if (w1) {
            let pick = w1;
            for (let v = Math.round(clamp(FILL_CAP) * 100); v > 100; v -= 5) {
                const t = wrapBest(v / 100);
                if (t && t.m.zoom >= w1.m.zoom * FREE) { pick = t; break; }
            }
            const { m, kB, wideB, besideH, pack, v } = pick;
            const acrossU = Math.max(1, Math.floor((da.w / v + COL_GAP) / (colW + COL_GAP)));
            const wideU = (da.w / v - (acrossU - 1) * COL_GAP) / acrossU;
            const underTop = da.y + besideH + COL_GAP;
            const inked = pack.cols.reduce((sum, c, i) => sum + c.h * (i < kB ? wideB : wideU), 0) * v * v;
            const lowest = pack.cols.reduce((mx, c, i) => Math.max(mx, (i < kB ? 0 : besideH + COL_GAP) + c.h), 0);
            wrap = { kind: 'wrap', cols: pack.cols.length, colW: wideU, top: da.y, pack, scale: v,
                     mapArea: { x: da.x, y: da.y, w: m.w, h: m.h },
                     extent: { w: da.w, h: Math.max(besideH, lowest) * v },
                     coverage: (m.w * m.h + inked) / area,
                     map: { zoom: m.zoom, w: m.w, h: m.h },
                     colX: (i) => (i < kB ? da.x + m.w / v + COL_GAP + i * (wideB + COL_GAP)
                                          : da.x + (i - kB) * (wideU + COL_GAP)),
                     colTop: (i) => (i < kB ? da.y : underTop),
                     colWOf: (i) => (i < kB ? wideB : wideU),
                     toBase: toBase(v) };
        }

        // The layout with the larger wall wins; where two walls are within
        // 3 per cent of each other, the one that covers more of the sheet
        // (stack on a tie). Wrap takes the sheet only where its wall is
        // WRAP_GAIN larger: it is for the sheet side and stack leave half
        // empty, and a sheet they already lay out well keeps its layout
        // and its larger type.
        const kept = [stack, side].filter(Boolean);
        let pick = null;
        if (side && stack) {
            const zs = side.map.zoom, zt = stack.map.zoom;
            if (zs > zt * 1.03) pick = side;
            else if (zt > zs * 1.03) pick = stack;
            else pick = stack.coverage >= side.coverage ? stack : side;
        } else if (kept.length) {
            pick = kept[0];
        }
        if (wrap && (!pick || wrap.map.zoom > pick.map.zoom * WRAP_GAIN)) return wrap;
        if (pick) return pick;

        // tons of info: neither holds the tables at 1 - the map over the
        // tables in the columns that fit, the rest continuing
        const colH = Math.floor(da.h - BUBBLE_H - COL_GAP - minH);
        const pack = this._bPack(blocks, colH, across);
        const wide = (da.w - (across - 1) * COL_GAP) / across;
        const tablesH = tallest(pack);
        const mapH = da.h - BUBBLE_H - COL_GAP - tablesH;
        const m = fit(da.w, mapH);
        return { kind: 'stack', cols: across, colW: wide, top: da.y + m.h + BUBBLE_H + COL_GAP, pack, scale: 1,
                 mapArea: { x: da.x, y: da.y, w: da.w, h: mapH },
                 extent: { w: da.w, h: m.h + BUBBLE_H + COL_GAP + tablesH },
                 coverage: (m.w * m.h + da.w * tablesH) / area,
                 map: { zoom: m.zoom, w: m.w, h: m.h },
                 colX: (i) => da.x + i * (wide + COL_GAP), toBase: identity };
    }

    // Blocks in order across up to `maxCols` columns, side by side - one
    // per block where they are few, else the consecutive split whose
    // tallest column is shortest (a stack's tables under its map). Nothing
    // splits: a block taller than the column is the caller's to refuse.
    // Null when there is nothing to lay. Same shape as _bPack's result.
    _bSpread(blocks, maxCols) {
        const items = blocks.filter(b => b && (b.lines || []).length)
            .map(b => ({ lines: b.lines, h: b.lines.reduce((s, l) => s + l.h, 0) }));
        if (!items.length) return null;
        const k = Math.min(items.length, Math.max(1, maxCols));
        const groupH = (i, j) => items.slice(i, j).reduce((s, b) => s + b.h, 0) + (j - i - 1) * BLOCK_GAP;
        let best = null;
        const walk = (start, left, cuts, worst) => {
            if (left === 1) {
                const h = Math.max(worst, groupH(start, items.length));
                if (!best || h < best.h) best = { h, cuts: cuts.slice() };
                return;
            }
            for (let end = start + 1; end <= items.length - (left - 1); end++) {
                cuts.push(end);
                walk(end, left - 1, cuts, Math.max(worst, groupH(start, end)));
                cuts.pop();
            }
        };
        walk(0, k, [], 0);
        const bounds = [0, ...best.cuts, items.length];
        const cols = [];
        for (let c = 0; c < bounds.length - 1; c++) {
            const col = { h: 0, items: [] };
            let y = 0;
            for (const b of items.slice(bounds[c], bounds[c + 1])) {
                if (col.items.length) y += BLOCK_GAP;
                for (const l of b.lines) { col.items.push({ line: l, y }); y += l.h; }
                col.h = y;
            }
            cols.push(col);
        }
        return { cols, rest: [] };
    }

    // The packed columns drawn where the layout put them.
    _bDrawLayout(book, L) {
        L.pack.cols.forEach((col, i) => {
            const x = L.colX(i);
            const top = L.colTop ? L.colTop(i) : L.top;
            const w = L.colWOf ? L.colWOf(i) : L.colW;
            for (const it of col.items) it.line.draw(book.ctx, x, top + it.y, w);
        });
    }

    // Subjects side by side on one sheet, a COLUMN each - a distro's, a
    // processor's tables under its name (the pull sheets lay their
    // positions out their own way, _bPullSheets) - as many as fit the
    // drawing area's width at base size, the next sheet taking the rest
    // ("for pulls and stuff we can combine those screens on the PDF",
    // 2026-09-08; the screens themselves stay one per sheet). A subject taller than a column takes
    // the columns it needs; taller than the sheet, it continues on the
    // next "(cont.)", its heads repeated, and leads that sheet, which
    // stays at 1. Otherwise the fill scale applies to the sheet as a
    // whole. `spec.page(groups)` names the sheet by what it carries;
    // `spec.colW` is the column (COL_W unless the subjects are narrower).
    //   groups: [{ kind, name, blocks }]
    _bColumnSheets(book, spec, groups) {
        const da = book.geo.da;
        const queue = groups.filter(g => g && (g.blocks || []).some(b => b && (b.lines || []).length))
            .map(g => ({ ...g, cont: false }));
        while (queue.length) {
            const colW = Math.max(spec.colW || COL_W,
                                  ...queue.map(g => Math.max(0, ...g.blocks.map(b => (b && b.minW) || 0))));
            const across = Math.max(1, Math.floor((da.w + COL_GAP) / (colW + COL_GAP)));
            const placed = [];          // { group, cols, first }
            let used = 0, continues = false;
            while (queue.length && used < across) {
                const g = queue[0];
                const pack = this._bPack(g.blocks, da.h - GROUP_H, across - used);
                if (!pack.cols.length) break;
                placed.push({ group: g, cols: pack.cols, first: used });
                used += pack.cols.length;
                queue.shift();
                if (pack.rest.length) {
                    queue.unshift({ ...g, blocks: pack.rest, cont: true });
                    continues = true;
                    break;
                }
            }
            if (!placed.length) break;
            const tallest = placed.reduce((m, p) => Math.max(m, ...p.cols.map(c => c.h)), 0);
            const extent = { w: used * colW + (used - 1) * COL_GAP, h: GROUP_H + tallest };
            const scale = continues ? 1 : this._bFillScale(book, extent);
            const heads = placed.map(p => p.group.name + (p.group.cont ? ' (cont.)' : ''));
            const colX = (i) => da.x + i * (colW + COL_GAP);
            this._bPage(book, { ...spec.page(placed.map(p => p.group)), layout: 'tables', cols: used, scale, extent,
                                names: heads }, (page, scaled) => scaled(() => {
                placed.forEach((p, j) => {
                    const w = p.cols.length * colW + (p.cols.length - 1) * COL_GAP;
                    this._bGroupHead(book, heads[j], colX(p.first), da.y, w);
                    p.cols.forEach((col, i) => {
                        for (const it of col.items) it.line.draw(book.ctx, colX(p.first + i), da.y + GROUP_H + it.y, colW);
                    });
                });
            }));
        }
    }

    // A column's head: the subject's name over its tables, a rule under.
    _bGroupHead(book, name, x, y, w) {
        const ctx = book.ctx;
        this._bText(book, name, x, y + 38, { size: SZ.group, weight: 700, upper: true, maxWidth: w, shrink: true });
        ctx.fillStyle = INK;
        ctx.fillRect(x, y + GROUP_H - 10, w, 3);
    }

    // A map sheet: the map as a numbered view in page units, the bubble
    // and the tables beside or under it at the sheet's fill scale
    // (_bMapLayout), the rest continuing on table-only sheets at 1.
    // `spec.draw(area)` paints the map into the area and returns the rect
    // it used; `spec.measure(area)` gives its geometry without painting.
    _bMapSheets(book, spec, blocks) {
        const L = this._bMapLayout(book, spec, blocks);
        const view = ++book.views;
        this._bPage(book, { ...spec, view, layout: L.kind, cols: L.cols, scale: L.scale, extent: L.extent,
                            coverage: L.coverage }, (page, scaled) => {
            const used = spec.draw(L.mapArea) || L.mapArea;
            scaled(() => {
                const [bx, by] = L.toBase(L.mapArea.x + 20, used.y + used.h + 8);
                this._bViewBubble(book, view, spec.viewName, bx, by);
                this._bDrawLayout(book, L);
            });
        });
        let rest = L.pack.rest;
        while (rest.length) {
            const C = this._bLayout(book, rest);
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
            const [px, py] = this._bLogXY(book, cx, cy);
            book.log.bubble = { number, name: label, x: px, y: py, r: r * (book.fill ? book.fill.s : 1) };
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
    // sheet size - times the sheet's fill scale, where the drawing is
    // painted larger (book.fill) - and the renderer draws at that times
    // the zoom, so the wall's text and lines come out sharp when the
    // bitmap is laid onto the scaled sheet - never upscaled from a
    // smaller render. geo.extent is the map's compact extent in the area:
    // the wall with its gutters, and the height used.
    _bMap(book, layer, view, area, gutter) {
        // The set's one View choice, for the length of this paint: the
        // renderer mirrors a Power or Data map when ITS canvas's
        // perspective key says 'back', so every canvas (and the project
        // root, the legacy single-canvas keys) is set to the binder's side
        // and put back afterwards - the workspace's own Front / Back
        // toggles read exactly as before, nothing is persisted. A caller
        // with a bare book (a test's) reads as front.
        const side = VIEW_PERSPECTIVE[book && book.meta && book.meta.view] || 'front';
        return this._bWithPerspective(side, () => this._bPaintMap(book, layer, view, area, gutter));
    }

    // Every canvas's two perspective keys and the project root's pair set
    // to `side` ('front' or 'back') while `fn` runs, then every value put
    // back - a key that was absent is absent again - whatever fn did or
    // threw. The renderer is the only reader; no PUT, no undo entry.
    _bWithPerspective(side, fn) {
        const proj = this.project;
        if (!proj || typeof proj !== 'object') return fn();
        const holders = [proj, ...(Array.isArray(proj.canvases) ? proj.canvases : [])]
            .filter(h => h && typeof h === 'object');
        const saved = holders.map(h => [h, PERSPECTIVE_KEYS.map(k =>
            [Object.prototype.hasOwnProperty.call(h, k), h[k]])]);
        try {
            for (const h of holders) for (const k of PERSPECTIVE_KEYS) h[k] = side;
            return fn();
        } finally {
            for (const [h, vals] of saved) {
                PERSPECTIVE_KEYS.forEach((k, i) => {
                    const [had, v] = vals[i];
                    if (had) h[k] = v; else delete h[k];
                });
            }
        }
    }

    // `target` is a screen, or a sheet subject (_bSubject): a GROUP draws
    // every member as it sits on the canvas, framed on their union; a
    // MEMBER of a group printed by screens is framed on its own wall with
    // the rest of the group still on (hidden, the walk across the group
    // would fall apart and the member would draw a routing of its own -
    // getAutoRoutePlan skips a hidden member) and everything of the other
    // members cut off the bitmap: their cabinets, and whatever stands
    // outside this member's wall and its gutters. The Names switch reads
    // the sheet's own choice while it paints - 'group' on a group sheet,
    // 'screens' on a member's.
    _bPaintMap(book, target, view, area, gutter) {
        const r = window.canvasRenderer;
        const subject = this._bSubject(target);
        const layer = subject.layers[0];
        // the gutters: the rulers' and the brackets' room by default; a
        // caller that draws neither (the wiring sheet) passes its own
        const G = gutter || MAP_GUTTER;
        const S = (book.scale || 2) * ((book.fill && book.fill.s) || 1);
        const canvases = (this.project && Array.isArray(this.project.canvases)) ? this.project.canvases : [];
        const hadBy = !!this.project && Object.prototype.hasOwnProperty.call(this.project, 'groupNameDisplayByView');
        const saved = {
            canvas: r.canvas, ctx: r.ctx, exportMode: r.exportMode, transparent: r.exportTransparentBg,
            printer: r.printerMode, viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
            hideNames: r.hideScreenNames,
            ignoreRaster: r.ignoreRasterBounds,
            rigRoom: r.riggingTopRoom, rigRoomBelow: r.riggingBottomRoom,
            active: this.project ? this.project.active_canvas_id : null,
            canvasVis: canvases.map(c => [c, c.visible]),
            layerVis: (this.project.layers || []).map(l => [l, l.visible]),
            nameBy: hadBy ? this.project.groupNameDisplayByView : undefined,
        };
        const inner = {
            x: area.x + G.left, y: area.y + G.top,
            w: area.w - G.left - G.right,
            h: (Number.isFinite(area.h) ? area.h : Infinity) - G.top - G.bottom,
        };
        let geo = null;
        try {
            r.viewMode = view;
            const cid = (layer.show_canvas_id || layer.canvas_id) || null;
            const canvas = canvases.find(c => c && c.id === cid) || null;
            canvases.forEach(c => { c.visible = (canvas ? c.id === canvas.id : true); });
            if (canvas && this.project) this.project.active_canvas_id = canvas.id;
            const on = new Set(subject.members);
            (this.project.layers || []).forEach(l => { if (!on.has(l)) l.visible = false; });
            subject.members.forEach(l => { l.visible = true; });
            if (subject.kind !== 'layer') {
                this.project.groupNameDisplayByView = { ...(saved.nameBy || {}),
                    [view]: subject.kind === 'group' ? 'group' : 'screens' };
            }
            const ws = r._canvasWorkspace(canvas);
            const mirrored = !!(canvas && r._isCanvasMirrored(canvas));
            const crw = canvas ? ((canvas.show_raster_width) || canvas.raster_width || 0) : 0;
            const offs = new Map(subject.members.map(l => [l, r.getLayerRenderOffset(l)]));
            // A processor-coord rect of a screen (this layer unless named),
            // in the canvas's drawn frame (mirrored around the raster's right
            // edge on a Back view).
            const local = (px, py, pw, ph, l = layer) => {
                const { dx, dy } = offs.get(l) || r.getLayerRenderOffset(l);
                return { x: mirrored ? crw - (px + dx + pw) : px + dx, y: py + dy, w: pw, h: ph };
            };
            const boundsOf = (l) => { const b = r.getLayerBounds(l); return local(b.x, b.y, b.width, b.height, l); };
            let wall = boundsOf(layer);
            for (const l of subject.layers.slice(1)) {
                const w = boundsOf(l);
                const x1 = Math.min(wall.x, w.x), y1 = Math.min(wall.y, w.y);
                wall = { x: x1, y: y1, w: Math.max(wall.x + wall.w, w.x + w.w) - x1,
                         h: Math.max(wall.y + wall.h, w.y + w.h) - y1 };
            }
            const ww = Math.max(1, wall.w), wh = Math.max(1, wall.h);
            // One zoom for both axes - the wall is never scaled
            // non-uniformly: it fits the area, and never past the cap.
            const zoom = Math.min(inner.w / ww, inner.h / wh, MAP_ZOOM_CAP);
            const drawW = wall.w * zoom, drawH = wall.h * zoom;
            const used = { x: area.x, y: area.y, w: area.w,
                           h: Math.round(drawH + G.top + G.bottom) };
            const ox = inner.x + (inner.w - drawW) / 2;      // wall's sheet origin
            const oy = inner.y;
            const toPage = (lx, ly) => ({ x: ox + (lx - wall.x) * zoom, y: oy + (ly - wall.y) * zoom });
            geo = {
                zoom, wall: { x: ox, y: oy, w: drawW, h: drawH }, mirrored, area: used,
                extent: { x: ox - G.left, y: area.y,
                          w: Math.ceil(drawW) + G.left + G.right, h: used.h },
                rect: (px, py, pw, ph, onLayer) => {
                    const l = local(px, py, pw, ph, onLayer || layer);
                    const p = toPage(l.x, l.y);
                    return { x: p.x, y: p.y, w: l.w * zoom, h: l.h * zoom };
                },
                // what a box of ink (sheet units) has to clear to stay on the
                // sheet: everything is kept but on a member's sheet, which
                // keeps its own wall and gutters and none of another member's
                keep: () => true,
            };
            // A member's sheet: what is cut off its bitmap - every other
            // member's wall - and the room it keeps, its own wall with the
            // gutters (a hair past them where the gutter is none).
            let cut = null;
            if (subject.kind === 'member') {
                const pad = 8;
                const keep = { x: ox - G.left - pad, y: oy - G.top - pad,
                               w: drawW + G.left + G.right + pad * 2, h: drawH + G.top + G.bottom + pad * 2 };
                const peers = subject.members.filter(l => l !== layer).map(l => {
                    const b = r.getLayerBounds(l);
                    return geo.rect(b.x, b.y, b.width, b.height, l);
                });
                const meets = (a, b) => Math.min(a.x + a.w, b.x + b.w) > Math.max(a.x, b.x)
                    && Math.min(a.y + a.h, b.y + b.h) > Math.max(a.y, b.y);
                const inside = (a, b) => a.x >= b.x - 0.5 && a.y >= b.y - 0.5
                    && a.x + a.w <= b.x + b.w + 0.5 && a.y + a.h <= b.y + b.h + 0.5;
                geo.keep = (box) => meets(box, keep) && !peers.some(pr => inside(box, pr));
                cut = { keep, peers };
            }
            if (book.page && book.page.painting) {
                if (book.log) {
                    // in page units (a map sheet paints its map outside the
                    // fill, so this is the identity; a fill on the context
                    // would carry through): the wall as it lands, its zoom
                    // on the page, the sheet's fill scale, the area the
                    // bitmap is laid in - the image op's very rect
                    const F = (book.fill && book.fill.s) || 1;
                    book.log.map = { ...this._bLogRect(book, geo.wall), zoom: zoom * F, baseZoom: zoom,
                                     scale: (book.page && book.page.scale) || 1,
                                     area: this._bLogRect(book, used) };
                }
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
                // This sheet is ONE screen on its own page: the processor's
                // raster is not what bounds it, and clipping panels to the
                // raster cut the wall wherever a screen stood further down or
                // across the canvas than the raster reaches (2026-09-11).
                r.ignoreRasterBounds = true;
                r.printerMode = book.meta.palette === 'printer';
                // The Rigging sheet's header bars take the strip above the
                // wall: the gutter's height, in canvas units at this zoom.
                r.riggingTopRoom = view === 'rigging' ? Math.max(0, G.top - 8) / zoom : null;
                r.riggingBottomRoom = view === 'rigging' ? Math.max(0, G.bottom - 8) / zoom : null;
                // The renderer draws at S times the sheet zoom (its world
                // transform is zoom and pan alone, so a scaled context
                // would not survive it); the wall's local origin lands at
                // (ox - area.x, oy - area.y) in sheet units.
                r.zoom = zoom * S;
                r.panX = ((ox - area.x) - (ws.wx + wall.x) * zoom) * S;
                r.panY = ((oy - area.y) - (ws.wy + wall.y) * zoom) * S;
                // The map draws its OWN lettering above the wall (a multi
                // band pill, its leg ruler). The binder then draws its
                // column ruler in the same strip and had been printing
                // its numbers inside the pill - "S1-1" read "S1-4" on a
                // real export. Take the map's own top ink, in sheet
                // units, so the ruler can stand clear of it.
                // Re-entrant on purpose: a caller may already be probing this
                // very render (the label-collision suite does), and taking
                // the probe away from it would leave it with nothing.
                const outerProbe = r.labelProbe;
                const outerLen = outerProbe ? outerProbe.length : 0;
                const probe = outerProbe || ((typeof r.startLabelProbe === 'function')
                    ? r.startLabelProbe() : null);
                r.render();
                if (cut) {
                    // the other members off the bitmap, then everything past
                    // this member's own room
                    const px = (rc) => [(rc.x - area.x) * S, (rc.y - area.y) * S, rc.w * S, rc.h * S];
                    offCtx.save();
                    offCtx.setTransform(1, 0, 0, 1, 0, 0);
                    offCtx.globalCompositeOperation = 'destination-out';
                    offCtx.fillStyle = '#000000';
                    // a peer's wall a little past its edge (the outline the
                    // renderer strokes round it), never into this member's
                    offCtx.save();
                    offCtx.beginPath();
                    offCtx.rect(0, 0, off.width, off.height);
                    offCtx.rect(...px(geo.wall));
                    offCtx.clip('evenodd');
                    const m = 24;
                    for (const pr of cut.peers) {
                        offCtx.fillRect(...px({ x: pr.x - m, y: pr.y - m, w: pr.w + 2 * m, h: pr.h + 2 * m }));
                    }
                    offCtx.restore();
                    offCtx.globalCompositeOperation = 'destination-in';
                    offCtx.fillRect(...px(cut.keep));
                    offCtx.restore();
                }
                if (probe) {
                    const boxes = outerProbe ? outerProbe.slice(outerLen)
                                             : r.endLabelProbe();
                    let minY = Infinity, minX = Infinity;
                    for (const b of boxes) {
                        if (!b) continue;
                        if (cut && !geo.keep({ x: area.x + b.x / S, y: area.y + b.y / S,
                                               w: (b.w || 0) / S, h: (b.h || 0) / S })) continue;
                        if (typeof b.y === 'number') minY = Math.min(minY, b.y);
                        if (typeof b.x === 'number') minX = Math.min(minX, b.x);
                    }
                    geo.mapInkTop = minY === Infinity ? null : area.y + minY / S;
                    geo.mapInkLeft = minX === Infinity ? null : area.x + minX / S;
                    geo.mapArea = { x: area.x, y: area.y, w: used.w, h: used.h };
                }
                // Laid at the map's sheet size: on the scaled sheet that is
                // one offscreen pixel per sheet pixel.
                book.ctx.drawImage(off, area.x, area.y, used.w, used.h);
            }
        } finally {
            saved.canvasVis.forEach(([c, v]) => { c.visible = v; });
            saved.layerVis.forEach(([l, v]) => { l.visible = v; });
            if (this.project) this.project.active_canvas_id = saved.active;
            if (this.project && subject.kind !== 'layer') {
                if (hadBy) this.project.groupNameDisplayByView = saved.nameBy;
                else delete this.project.groupNameDisplayByView;
            }
            r.canvas = saved.canvas;
            r.ctx = saved.ctx;
            r.exportMode = saved.exportMode;
            r.exportTransparentBg = saved.transparent;
            r.hideScreenNames = saved.hideNames;
            r.ignoreRasterBounds = saved.ignoreRaster;
            r.printerMode = saved.printer;
            r.riggingTopRoom = saved.rigRoom;
            r.riggingBottomRoom = saved.rigRoomBelow;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom;
            r.panX = saved.panX;
            r.panY = saved.panY;
        }
        return geo;
    }

    // A GROUP's rulers number straight through the wall ("both just depends
    // on label", 2026-10-01): the columns and the rows are the members'
    // cabinets as they stand on the sheet, gathered by position - a column
    // is the cabinets whose centres line up, whatever member they are on -
    // and numbered from the front's left (from the right on a Back view,
    // where the front's first column is drawn), the top row 1.
    _bRulersAcross(book, layers, geo) {
        const rects = [];
        for (const l of layers) {
            for (const p of (l.panels || [])) {
                if (p && !p.hidden) rects.push(geo.rect(p.x, p.y, p.width, p.height, l));
            }
        }
        if (!rects.length) return;
        const gather = (lo, size) => {
            const tol = Math.max(1, Math.min(...rects.map(size)) / 2);
            const sorted = rects.slice().sort((a, b) => (lo(a) + size(a) / 2) - (lo(b) + size(b) / 2));
            const out = [];
            for (const rc of sorted) {
                const c = lo(rc) + size(rc) / 2;
                const last = out[out.length - 1];
                if (last && c - last.c <= tol) {
                    last.a = Math.min(last.a, lo(rc)); last.b = Math.max(last.b, lo(rc) + size(rc));
                } else {
                    out.push({ c, a: lo(rc), b: lo(rc) + size(rc) });
                }
            }
            return out;
        };
        const xs = gather(r => r.x, r => r.w);
        if (geo.mirrored) xs.reverse();
        const cols = new Map(xs.map((c, i) => [i, { x1: c.a, x2: c.b }]));
        const rows = new Map(gather(r => r.y, r => r.h).map((c, i) => [i, { y1: c.a, y2: c.b }]));
        this._bRulersDraw(book, geo, cols, rows);
    }

    // The rulers (numbering "2"): every column ticked above the wall, every
    // fifth and the two ends numbered bold; every row numbered bold down
    // the left. Positions come from the cabinets themselves, so a half
    // tile or a rotated member is numbered where it draws.
    _bRulers(book, layer, geo) {
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
        this._bRulersDraw(book, geo, cols, rows);
    }

    // The ticks and numbers for `cols` / `rows` (index -> sheet span), the
    // index + 1 printed.
    _bRulersDraw(book, geo, cols, rows) {
        const ctx = book.ctx;
        const colKeys = [...cols.keys()].sort((a, b) => a - b);
        const rowKeys = [...rows.keys()].sort((a, b) => a - b);
        // Above the map's OWN lettering, never through it. geo.mapInkTop is
        // the highest thing the map drew, in sheet units; on a data sheet
        // nothing stands above the wall and this is the wall's top as before.
        const top = Math.min(geo.wall.y,
                             typeof geo.mapInkTop === 'number' ? geo.mapInkTop - 4
                                                               : geo.wall.y);
        // ...and inside the drawing area, never over its head rule. The
        // column ruler needs COL_RULER_H of clear sheet above whatever the
        // map drew. A power sheet's map draws a multi band and its own leg
        // ruler up there and leaves about 14 of the 74 the gutter holds, so
        // there is no room for a second ruler: the map's own names those
        // columns already, and printing ours anyway put the numbers through
        // the band pill, then through the sheet's head rule when they moved
        // clear of it. Growing the gutter to hold both was the obvious fix
        // and the wrong one - it moved every map on every sheet and broke
        // the fill. A data sheet draws nothing above its wall and keeps its
        // ruler exactly as it was.
        const areaTop = (geo.mapArea && typeof geo.mapArea.y === 'number')
            ? geo.mapArea.y : null;
        const roomForCols = areaTop === null || (top - areaTop) >= COL_RULER_H;
        ctx.strokeStyle = INK;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        if (roomForCols) colKeys.forEach((k, i) => {
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
        if (roomForCols) {
            ctx.beginPath();
            ctx.moveTo(geo.wall.x, top - 6);
            ctx.lineTo(geo.wall.x + geo.wall.w, top - 6);
            ctx.stroke();
        }
        // Beside the map's own lettering, never through it: a label disc on
        // the first column overhangs the wall's left edge, and the row ticks
        // were being drawn straight across it.
        const left = Math.min(geo.wall.x,
                              typeof geo.mapInkLeft === 'number' ? geo.mapInkLeft - 4
                                                                 : geo.wall.x);
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
    //
    // On a grouped wall's sheet (`subject`, _bSubject) the multis are the
    // sheet's own (_bSubjectBoxes) and a bracket spans their cabinets on the
    // screens the map draws - every member's on a group sheet, the member's
    // own on a member's.
    _bBoxBrackets(book, layer, scr, geo, subject) {
        const ctx = book.ctx;
        const s = subject && subject.kind !== 'layer' ? subject : null;
        const units = s ? this._bSubjectBoxes(book, s)
            : (scr.boxes || []).map(box => ({ carrier: layer, box }));
        const circuitsOf = new Map();
        const byNumOf = (carrier) => {
            if (!circuitsOf.has(carrier)) {
                const list = (typeof this.screenCircuits === 'function') ? this.screenCircuits(carrier) : [];
                circuitsOf.set(carrier, new Map(list.map(c => [c.num, c])));
            }
            return circuitsOf.get(carrier);
        };
        // [panel, the screen it is on] of a circuit's cabinets this map draws
        const drawn = (c, carrier) => {
            const out = [];
            (c.panels || []).forEach((p, i) => {
                if (!p || p.hidden) return;
                const on = (c.layers && c.layers[i]) || carrier;
                if (s ? s.layers.some(l => this._bSameLayer(l, on)) : this._bSameLayer(on, layer)) out.push([p, on]);
            });
            return out;
        };
        const wallCx = geo.wall.x + geo.wall.w / 2;
        const placed = { L: [], R: [] };
        for (const { carrier, box } of units) {
            let x1 = Infinity, x2 = -Infinity, y1 = Infinity, y2 = -Infinity;
            const byNum = byNumOf(carrier);
            for (const c of box.circuits || []) {
                const circuit = byNum.get(c.num);
                if (!circuit) continue;
                for (const [p, on] of drawn(circuit, carrier)) {
                    const rc = geo.rect(p.x, p.y, p.width, p.height, s ? on : undefined);
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
                const [lx, ly1] = this._bLogXY(book, x, y1);
                (book.log.brackets || (book.log.brackets = []))
                    .push({ name: box.name, side, depth, x: lx, y1: ly1, y2: this._bLogXY(book, x, y2)[1] });
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
                ? `${box.name} · ${this.pullLengthText(box.homeRun, this.pullHomeRunKind(box))}` : `${box.name}`;
            ctx.save();
            ctx.translate(x + dir * 24, (ya + yb) / 2);
            ctx.rotate(dir > 0 ? Math.PI / 2 : -Math.PI / 2);
            this._bText(book, label, 0, 9, { size: SZ.bracket, weight: 700, align: 'center',
                                              maxWidth: Math.max(80, yb - ya) });
            ctx.restore();
        }
    }

    // ---- the screen sheets --------------------------------------------------

    // The side the set's maps are drawn from, as a sheet names it: "Front
    // View" or "Rear View" (book.meta.view).
    _bViewName(book) {
        return book.meta.view === 'rear' ? 'Rear View' : 'Front View';
    }

    // Every screen sheet names the side its map is drawn from - the set's
    // one View choice: "WALL-A · POWER · REAR VIEW" as the view heading,
    // the title block's sheet title and the CONTENTS line alike, the plan
    // title "WALL-A - Power - Rear View". The wiring sheets, drawn from the
    // same side, name it the same way ("WALL-A · POWER WIRING · REAR
    // VIEW", app-binder-wiring.js); the overview stays OVERVIEW.
    // A group printed as one names the GROUP ("WALL · DATA · FRONT VIEW") and
    // a member printed by screens names the member; `target` is a screen or
    // a sheet subject (_bSubject).
    _bScreenPage(book, target, pos, view) {
        const s = this._bSubject(target);
        const layer = s.layers[0];
        const scr = book.list.byScreen[layer.id];
        const word = view === 'power' ? 'POWER' : 'DATA';
        const title = `${s.name} - ${view === 'power' ? 'Power' : 'Data'} - ${this._bViewName(book)}`;
        const sheetTitle = `${s.name} · ${word} · ${this._bViewName(book).toUpperCase()}`;
        const blocks = view === 'power'
            ? this._bPowerBlocks(book, s, scr)
            : this._bDataBlocks(book, s, scr);
        const mode = view === 'power' ? 'power' : 'data-flow';
        this._bMapSheets(book, {
            kind: view, title, sheetTitle, viewName: sheetTitle,
            layerId: s.id, subject: s.name, position: pos.name,
            ...(s.groupId != null ? { groupId: s.groupId, layerIds: s.layers.map(l => l.id) } : {}),
            measure: (area) => this._bMap(book, s, mode, area),
            draw: (area) => {
                const geo = this._bMap(book, s, mode, area);
                if (!geo) return null;
                // rulers straight through a group ("both just depends on
                // label"), from 1 on a screen of its own
                if (s.kind === 'group') this._bRulersAcross(book, s.layers, geo);
                else this._bRulers(book, layer, geo);
                if (view === 'power') this._bBoxBrackets(book, layer, scr, geo, s);
                return geo.area;
            },
        }, blocks);
    }

    // ---- the header/footer sheets -------------------------------------------

    _bHasRigging(layer) {
        return !!layer && (layer.type || 'screen') === 'screen'
            && ((Array.isArray(layer.riggingBars) && layer.riggingBars.length > 0)
                || (Array.isArray(layer.riggingFooterBars) && layer.riggingFooterBars.length > 0));
    }

    // The map's gutters for a header/footer sheet: the default's room above
    // the wall for the header bars, and - only on a screen that has footer
    // bars - room below it for them too.
    _bRiggingGutter(layer) {
        const footer = Array.isArray(layer.riggingFooterBars) && layer.riggingFooterBars.length > 0;
        return footer ? { ...MAP_GUTTER, bottom: MAP_GUTTER.top } : MAP_GUTTER;
    }

    // The Header/Footer sheet for ONE screen (a group's members each have
    // their own): the wall as it stands with its header bars drawn above it
    // and its footer bars below, and a table of the bars each row takes. No
    // column or row rulers - the header bars take the strip above the wall
    // the rulers use on the Power and Data sheets, and each bar says its own
    // panel count.
    _bRiggingPage(book, layer, pos) {
        const view = this._bViewName(book);
        const title = `${layer.name} - Header/Footer - ${view}`;
        const sheetTitle = `${layer.name} · HEADER/FOOTER · ${view.toUpperCase()}`;
        const gutter = this._bRiggingGutter(layer);
        this._bMapSheets(book, {
            kind: 'rigging', title, sheetTitle, viewName: sheetTitle,
            layerId: layer.id, subject: layer.name, position: pos.name,
            gutter,
            measure: (area) => this._bMap(book, layer, 'rigging', area, gutter),
            draw: (area) => {
                const geo = this._bMap(book, layer, 'rigging', area, gutter);
                return geo ? geo.area : null;
            },
        }, this._bRiggingBlocks(book, layer));
    }

    _bRiggingBlocks(book, layer) {
        const rows = [['Header', layer.riggingBars], ['Footer', layer.riggingFooterBars]]
            .map(([word, bars]) => [word, Array.isArray(bars) ? bars : []]).filter(([, bars]) => bars.length);
        const blocks = rows.map(([word, bars]) => {
            const { total, bySize } = RiggingMath.tally([bars]);
            const kind = word === 'Footer' ? 'footer' : 'header';
            const lines = Object.keys(bySize).map(Number).sort((a, b) => b - a)
                .map(size => ({ cells: [RiggingMath.barName(size, kind), String(size), this._bQty(bySize[size])] }));
            lines.push({ cells: ['Total', '', this._bQty(total)], bold: true });
            return { lines: this._bTableLines(book, {
                title: `${word} bars`,
                cols: [{ title: `${word.toLowerCase()} bar`, w: 1.7 }, { title: 'panels', w: 0.8, align: 'right' },
                       { title: 'qty', w: 0.6, align: 'right' }],
                rows: lines,
            }) };
        });
        return blocks;
    }

    // The band over a multi's circuits: "SR1 · Multi 208 · 125' · 6
    // circuits" - the type is Multi (user, 2026-09-08: "should be multi"),
    // and the length stands alone: a Multi's length IS its home run, so
    // "125' home run" said it twice ("saying home run is redundant").
    // Plus the circuits on it that belong to another screen - `sheetIds`
    // the screens the sheet already lists (a grouped wall's members), the
    // screen itself by default.
    _bBoxBand(book, layer, box, sheetIds = null) {
        const n = (box.circuits || []).length;
        const parts = [box.name, box.type || 'no distro',
                       box.homeRun ? this.pullLengthText(box.homeRun, this.pullHomeRunKind(box)) : 'no length',
                       this._bPlural(n, 'circuit')];
        for (const [id, other] of Object.entries(book.list.byScreen)) {
            if (sheetIds ? sheetIds.has(String(id)) : String(id) === String(layer.id)) continue;
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
        // the service's line-to-line voltage (1.5, bug fix 3)
        const lineV = this.threePhaseLineVoltage(layer);
        return {
            active: active.length, equivalent, watts, voltage,
            amps1: voltage > 0 ? watts / voltage : 0,
            amps3: lineV > 0 ? watts / (lineV * 1.73) : 0,
            pixels: active.reduce((s, p) => s + this.getPanelPixelArea(p), 0),
            width: bounds.width, height: bounds.height,
            screenText: `${layer.columns} × ${layer.rows} · ${this._bPlural(active.length, 'panel')}`
                + ` · ${layer.cabinet_width}×${layer.cabinet_height} px`,
        };
    }

    // This screen's amps on each leg of ONE distro: the engine's own
    // per-circuit attribution - boxFeedLegAmps, the phasor walk
    // getDistroLoads runs over a whole service - run over this screen's
    // multis on that distro only, so a 208 V circuit lands on its leg pair
    // and a 110 V circuit on its one leg exactly as the tray's LEGS line
    // counts them. Null where the tray prints no LEGS line either: a
    // single-phase distro, or one the project does not hold.
    _bScreenLegsOn(layer, distroId) {
        return this._bSubjectLegsOn([layer], distroId);
    }

    // The same reading over several screens' multis at once - a grouped
    // wall's carriers, ONE phasor walk (leg amps do not add as magnitudes) -
    // and, where `listed` names circuits ("<layerId>:<circuit>"), only
    // those carrying amps: the rest keep their slot on the multi at 0 W, so
    // every listed circuit still lands on its own leg.
    _bSubjectLegsOn(layers, distroId, listed = null) {
        const distro = (typeof this.getDistros === 'function' ? this.getDistros() : [])
            .find(d => d && d.id === distroId);
        if (!distro || this.distroLegNames(distro).length < 2
                || typeof this.boxFeedLegAmps !== 'function') return null;
        const members = [];
        for (const layer of layers) {
            const assign = layer.powerSocaDistro || {};
            for (const s of this.getSocaPlan(layer)) {
                if (assign[s.soca] !== distroId) continue;
                members.push({ layer, s: listed ? { ...s, legs: s.legs.map(l => (listed.has(`${layer.id}:${l.circuit}`)
                    ? l : { ...l, watts: 0 })) } : s });
            }
        }
        return this.boxFeedLegAmps(distro, members);
    }

    // `target` is a screen or a sheet subject (_bSubject): a group's sheet
    // lists every member's multis and reads the group's figures; a member's
    // lists the circuits on its cabinets, each crossing one saying where the
    // rest of it is, and reads its own.
    _bPowerBlocks(book, target, scr) {
        const s = this._bSubject(target);
        const layer = s.layers[0];
        const grouped = s.kind !== 'layer';
        const blocks = [];
        const units = this._bSubjectBoxes(book, s);
        const sheetIds = grouped ? new Set(s.members.map(m => String(m.id))) : null;
        // Circuits, banded per soca / L21-30; NO. is the circuit's number
        // on its unit (the band says which).
        const rows = [];
        let crossing = false;
        for (const { carrier, box, also } of units) {
            rows.push({ band: this._bBoxBand(book, carrier, box, sheetIds) });
            for (const c of box.circuits || []) {
                const where = also.get(c.num);
                if (where) crossing = true;
                rows.push({ cells: [where ? `${c.label} · ${where}` : c.label, String(c.tail), this._bNum(c.tiles, 0),
                                    this._bNum(c.amps, 1), c.cable || '—'] });
            }
        }
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Circuits',
            bandsLead: true,
            // a crossing circuit's "· also on …" wraps under its name
            cols: [{ title: 'circuit', w: 1.5, ...(crossing ? { list: 2 } : {}) }, { title: 'no.', w: 0.6, align: 'right' },
                   { title: 'panels', w: 0.8, align: 'right' }, { title: 'amps', w: 0.8, align: 'right' },
                   { title: 'cable', w: 1.4 }],
            rows,
        }) });
        // Cables this screen (power side).
        blocks.push({ lines: this._bCableTable(book, s, 'power') });
        // Facts.
        const f = s.kind === 'group' ? this._bGroupFacts(s.members) : this._bScreenFacts(s.member || layer);
        const circuits = units.flatMap(u => u.box.circuits || []);
        const tiles = circuits.map(c => Number(c.tiles) || 0);
        const tMin = tiles.length ? Math.min(...tiles) : 0, tMax = tiles.length ? Math.max(...tiles) : 0;
        const each = tiles.length ? (tMin === tMax ? `${tMin} panels each` : `${tMin}–${tMax} panels each`) : '';
        const distroIds = [...new Set(units.map(u => u.box.distroId).filter(Boolean))];
        const loads = (typeof this.getDistroLoads === 'function') ? this.getDistroLoads() : [];
        // A member's sheet reads the amps of the circuits it lists; where
        // one of them carries another member's panels too, those are the
        // circuits' amps, not the member's.
        const listed = s.kind === 'member'
            ? new Set(units.flatMap(u => (u.box.circuits || []).map(c => `${u.carrier.id}:${c.num}`))) : null;
        // What feeds the screen (the user, 2026-10-21): a SERVICE row for
        // the house power a distro is on - "VX 200 · 200 A · 120/208V 3φ",
        // once for every distro on it - then a DISTRO row for each of
        // those distros; a distro on no service names its own system
        // instead. A distro row carries THIS SCREEN's amps on each leg -
        // not the distro's whole legs, which count every screen it feeds
        // (the user, 2026-09-15, on SR - MAIN reading SR's 301/311/311 A:
        // "it should be what is calculated per screen"). The hardware
        // sheet keeps the whole distro.
        const feeds = [];
        for (const id of distroIds) {
            const d = loads.find(x => x.id === id);
            if (!d) continue;
            const rec = this.getDistros().find(x => x.id === id) || d;
            const svc = typeof this.distroService === 'function' ? this.distroService(rec) : null;
            let feed = svc && feeds.find(f => f.svc === svc);
            if (!feed) feeds.push(feed = { svc, rows: [] });
            const parts = [d.name, `${rec.ratingA} A`, svc ? null : this.distroSystemName(rec),
                           rec.breakers100 && this.distroRegion(rec) === 'us' ? '100% rated breakers' : null];
            const legs = grouped ? this._bSubjectLegsOn(s.carriers, id, listed) : this._bScreenLegsOn(layer, id);
            if (legs) {
                // a leg's letter and its figure stay on one line where
                // the row wraps (no-break spaces; the KV rows wrap at
                // plain spaces only). The letters are the region's: X/Y/Z
                // in North America, L1/L2/L3 on an EU distro (1.5). The
                // sheet is the screen's, so the legs need no "this
                // screen" (the user, 2026-10-21).
                parts.push(this.distroLegNames(rec).map(k =>
                    `${this.distroLegLabel(rec, k)} ${this._bNum(legs[k], 1)}`).join(' · ') + ' A');
            }
            feed.rows.push(['Distro', parts.filter(Boolean).join(' · ')]);
        }
        const fed = feeds.flatMap(f => [
            ...(f.svc ? [['Service', `${f.svc.name || f.svc.id} · ${this.serviceSizeText(f.svc)}`]] : []),
            ...f.rows]);
        // The sheet is titled for THIS screen, so its Load is this
        // screen's own panels. Where its circuits also carry a group
        // peer's panels (a wall routed as one, every circuit on its first
        // member) the circuits table above is the WALL's, so a Wall load
        // row follows - the load those circuits draw, every member's
        // panels counted once, naming the members - and it is the figure
        // the table's amps sum to. A group's sheet reads the group's own
        // Load and the same Wall load row; a member's, its own Load and
        // the Wall load of the circuits on its cabinets.
        const loadText = (a1, a3, w) => `${this._bNum(a1, 1)} A 1φ · ${this._bNum(a3, 1)} A 3φ · ${this._bNum(w / 1000, 1)} kW`;
        const wallOf = (carrier) => {
            const carried = (typeof this.getCarriedPowerLoad === 'function') ? this.getCarriedPowerLoad(carrier) : null;
            return carried && carried.peers.length
                ? [['Wall load', `${loadText(carried.amps1, carried.amps3, carried.watts)} · `
                    + [carrier, ...carried.peers].map(l => l.name).join(' + ')]] : [];
        };
        const wall = grouped
            ? s.carriers.filter(c => s.kind === 'group' || units.some(u => u.carrier === c)).flatMap(wallOf)
            : wallOf(layer);
        blocks.push({ lines: this._bKvLines(book, 'Facts', [
            ['Screen', f.screenText],
            ['Load', loadText(f.amps1, f.amps3, f.watts)],
            ...wall,
            ['Circuits', [`${circuits.length} at ${f.voltage} V / ${parseFloat(layer.powerAmperage) || 0} A`, each]
                .filter(Boolean).join(' · ')],
            ...(fed.length ? fed : [['Distro', 'none']]),
        ]) });
        // Gangs, only when the sheet's circuits have any.
        const shared = [];
        if (typeof this.screenCircuits === 'function') {
            for (const carrier of [...new Set(units.map(u => u.carrier))]) {
                const gangs = (book.list.byScreen[carrier.id] || {}).gangs || { twofer: 0, threefer: 0 };
                const wider = Object.values(gangs.wider || {}).reduce((a, n) => a + n, 0);
                if ((gangs.twofer || 0) + (gangs.threefer || 0) + wider <= 0) continue;
                const mine = new Map(units.filter(u => u.carrier === carrier)
                    .flatMap(u => (u.box.circuits || []).map(c => [c.num, c.amps])));
                for (const c of this.screenCircuits(carrier)) {
                    if (!(Array.isArray(c.runIds) && c.runIds.length > 1)) continue;
                    if (grouped && !mine.has(c.num)) continue;
                    shared.push({ cells: [this.getPowerCircuitLabel(carrier, c.num),
                                          `${c.runIds.length}fer`, this._bNum(mine.get(c.num), 1)] });
                }
            }
        }
        if (shared.length) {
            blocks.push({ lines: this._bTableLines(book, {
                title: 'Shared circuits',
                cols: [{ title: 'circuit', w: 1.3 }, { title: 'splitter', w: 0.8 }, { title: 'amps', w: 0.8, align: 'right' }],
                rows: shared,
            }) });
        }
        return blocks;
    }

    // The return end's parts: its label, the unit it lands on and that
    // unit's band key and band text (the key the primary's unit would
    // have, so an end on the SAME unit is known to be one), and the socket
    // as PRIMARY prints one, "CVT4K-S SR B · 1".
    _bBackupEnd(layer, portNum, bb) {
        const label = (typeof this.getPortLabelText === 'function')
            ? this.getPortLabelText(layer, portNum, 'return') : '';
        const home = this._bPortHome(bb.cardId, bb.port);
        let where = home && home.box ? this._bBoxTitle(home.box) : (bb.boxTitle || '');
        if (!where) {
            where = home ? home.unitTitle : (bb.cardTitle || this._bCardShort(bb.cardId));
        }
        const socket = bb.localPort != null ? bb.localPort : bb.port;
        const socketText = `${where} · ${socket}`;
        const shortSocket = home && home.box ? `${this._bBoxShort(home.box)} · ${socket}` : socketText;
        let key, bandParts, bandLines = null;
        if (home && home.box) {
            key = `box:${home.box.id}`; bandParts = this._bBoxBandParts(home.box);
            bandLines = this._bBoxBandLines(home.box);
        } else if (home) {
            key = `card:${home.card.id}`; bandParts = [this._bCardBandText(home)];
        } else {
            key = `card:${bb.cardId}`; bandParts = [bb.cardTitle || this._bCardShort(bb.cardId)];
        }
        return { label, socketText, shortSocket, name: label || socketText, key,
                 bandText: bandParts.join(' · '), bandParts, bandLines: bandLines || bandParts };
    }

    // What a sheet calls a breakout box: "CVT4K-S SR" - the model and the
    // name typed on it, the way a card reads "H9 SR"; unnamed, the title
    // the dock wears ("CVT4K-S A"). One implementation, the pull list's.
    _bBoxTitle(box) {
        return (typeof this.pullBoxTitle === 'function')
            ? this.pullBoxTitle(box) : (box.displayTitle || box.name || box.deviceName);
    }

    // The band over a box's ports: "CVT4K-S SR · OPT 1-2 · 16 ports · OPT
    // 1-2 TAC A (TAC 8) 1-4" - the trunk it hangs on as the card's face prints it, the
    // sockets it delivers, and its fiber (_bBoxFiberText).
    _bBoxBandText(box) {
        return this._bBoxBandParts(box).join(' · ');
    }

    // The same band as two lines, for a half-width band over the data
    // sheet's PRIMARY or BACKUP half: the box on the first, its fiber on
    // the second.
    _bBoxBandParts(box) {
        return [[this._bBoxTitle(box), box.trunkTitle || '',
                 this._bPlural(box.portCount || (box.ports || []).length, 'port')]
                    .filter(Boolean).join(' · '),
                this._bBoxFiberText(box)];
    }

    // A box as a row names it under a band that already gave it in full:
    // the name typed on it - "USR A" - else its title.
    _bBoxShort(box) {
        return String(box.name || '').trim() || this._bBoxTitle(box);
    }

    // A box's fiber as the binder says it - each input by its port, the
    // cable's name (its kind in brackets the first time) and the strands,
    // "X1 TAC A (TAC 8) 9-10 · X2 TAC B (TAC 6) 1-2", copper by its port
    // "X1 Cat6A 150'" (fiberLinkSummary). With no
    // link: the 1.3 typed note as it always read ("12 Tac Fiber 250'", "no
    // fiber length" where only a type was typed), else "no fiber".
    _bBoxFiberText(box) {
        if (!box) return 'no fiber';
        const links = typeof this.fiberLinkSummary === 'function' ? this.fiberLinkSummary(box) : '';
        if (links) return links;
        const fiber = (typeof this.pullBoxFiberText === 'function') ? this.pullBoxFiberText(box) : '';
        if (fiber) return fiber;
        return String(box.fiberType || '').trim() ? 'no fiber length' : 'no fiber';
    }

    // One strand as the binder prints it - STRAND MAP, FIBER CONNECTIONS,
    // a data sheet's band, the Breakout boxes table: its name
    // (fiberStrandName - a colour, a number, a sub-unit, a typed name) and
    // its swatch, unless the cable reads in numbers: "If it is numbers only
    // then don't use colors as they won't have colors in real life" (owner,
    // 2026-10-17) - no swatch, and no tint in the strand map, anywhere.
    _bStrandPiece(n, cable) {
        return { text: this.fiberStrandName(n, cable),
                 swatch: cable && cable.labels === 'numbers' ? null : this.fiberStrandSwatch(n, cable) };
    }

    // A box's fiber, one input at a time (fiberLinkInputs), or null where
    // no input is on a fiber cable - a box with no fiber, or copper only,
    // reads as it always did.
    _bBoxFiberInputs(box) {
        const inputs = box && typeof this.fiberLinkInputs === 'function' ? this.fiberLinkInputs(box) : [];
        return inputs.some(i => i.cable) ? inputs : null;
    }

    // A BOX'S INPUTS AS GROUPS (owner, 2026-10-17: "group each strand pair
    // with its input" - the input's label centred beside its strands, a thin
    // outline round them, each input its own): one per link in the box's
    // order (primaries, then the backup inputs), { head: 'X1', sub: 'TAC A
    // (TAC 8)', strands: [{ text, swatch }] } - the cable's kind in brackets
    // the first time this box names it, the strands in strand order (as
    // the box's one-line summary has them), named and swatched as the strand map has them
    // (_bStrandPiece). A copper link, or a cable with no strands picked, is
    // a group of its words alone, { text }; a link with neither is left
    // out. Null where no input is on a fiber cable - a box with no fiber,
    // or copper only, reads as it always did.
    _bBoxInputGroups(box, all = false) {
        const links = box && typeof this.fiberBoxLinks === 'function' ? this.fiberBoxLinks(box) : [];
        const named = !!(box && box.linkPortsDocumented);
        const linked = links.some(l => l.cable || l.copper);
        if (!links.some(l => l.cable) && !(all && named)) return null;
        // an input's name only where its maker prints one - never a
        // made-up "Link 1"
        const title = (l) => (named ? l.title : '');
        const typed = new Set();
        const out = [];
        for (const l of links) {
            if (l.copper) {
                const ft = this.parseCableLength(l.copper.ft);
                const over = this.copperOverText(l.copper);
                out.push({ text: [title(l), l.copper.copper, Number.isFinite(ft) && ft > 0 ? this.pullLengthText(ft) : '']
                    .filter(Boolean).join(' ') + (over ? ` (${over})` : '') });
                continue;
            }
            if (!l.cable) {
                if (all && named) out.push({ text: `${l.title} no fiber` });
                continue;
            }
            const cable = l.cable;
            let what = cable.name || this.fiberCableTypeText(cable);
            if (cable.name && !typed.has(cable.id)) {
                what += ` (${this.fiberCableIsStranded(cable)
                    ? `${this.fiberKindWord(cable.kind)} ${cable.strands}` : this.fiberKindWord(cable.kind)})`;
            }
            typed.add(cable.id);
            // in strand order, as the box's one-line summary lists them
            const set = [...new Set(((l.link && l.link.strands) || []).map(Number))]
                .filter(Number.isFinite).sort((x, y) => x - y);
            if (!set.length) { out.push({ text: [title(l), what].filter(Boolean).join(' ') }); continue; }
            out.push({ head: title(l), sub: what, strands: set.map(n => this._bStrandPiece(n, cable)) });
        }
        // a box with no link at all keeps its 1.3 typed note, after its inputs
        // ("no fiber length" where only a type was typed, as it always read)
        if (all && !linked) {
            const note = (typeof this.pullBoxFiberText === 'function' ? this.pullBoxFiberText(box) : '')
                || (String((box && box.fiberType) || '').trim() ? 'no fiber length' : '');
            if (note) out.push({ text: note });
        }
        return out.length ? out : null;
    }

    // How many lines a group stands on: its strands, and never fewer than
    // its label's (the input over its cable).
    _bGroupLines(g) {
        if (!(g.strands && g.strands.length)) return 1;
        return Math.max(g.strands.length, g.sub ? 2 : 1);
    }

    // THE BAND OVER A BOX'S PORTS (the data sheet): the box on the first
    // line, then each input as a group (_bBoxInputGroups) - { group } -
    // the input and its cable centred beside its strands, outlined, the way
    // the Breakout boxes table's FIBER reads (_bBandStack draws it). Null
    // where the box has no fiber: its band is _bBoxBandParts, word for word.
    _bBoxBandLines(box) {
        const groups = this._bBoxInputGroups(box);
        if (!groups) return null;
        return [this._bBoxBandParts(box)[0], ...groups.map(g => (g.strands ? { group: g } : g.text))];
    }

    // The same for the Breakout boxes table's FIBER cell, as `parts`: each
    // input's words on a line, then its strands a line each - stacked the
    // way Fiber connections stacks them. Null where the box has no fiber
    // (the cell reads its words).
    _bBoxFiberParts(box) {
        const inputs = this._bBoxFiberInputs(box);
        if (!inputs) return null;
        const out = [];
        inputs.forEach((inp, i) => {
            if (!inp.cable || !inp.strands.length) { out.push({ text: inp.text, brk: i > 0 }); return; }
            out.push({ text: inp.head, brk: i > 0 });
            inp.strands.forEach(n => out.push({ ...this._bStrandPiece(n, inp.cable), brk: true }));
        });
        return out;
    }

    // The Breakout boxes table's FIBER as input groups: one for EVERY
    // input the box takes (owner, 2026-10-17: the inputs never disappear),
    // so an input with nothing on it is a group of its name and "no fiber"
    // - and a box with no link anywhere keeps its 1.3 typed note, if any,
    // as one more group after them. Null where the box's maker names no
    // input and nothing is on a cable: the cell reads its words, as before.
    _bBoxFiberGroups(box) {
        return this._bBoxInputGroups(box, true);
    }

    // The redundancy bar's reading for a processor: "Per card", "Per port",
    // "Backed up → MX20 B" (the unit its one card mirrors onto), "A to B"
    // (an SX40 running one loop), "Off" - then its backup processor, "·
    // backed up by WALL SR BU".
    _bRedundancyText(proc) {
        const level = (typeof this._procRedundancyLevel === 'function') ? this._procRedundancyLevel(proc) : 'off';
        // "Per card" only where the units are cards (unitWordFor)
        let text = level === 'card' ? `Per ${this.unitWordFor(proc)}` : (REDUNDANCY_WORDS[level] || level);
        const procs = this._processorsResolved || [];
        if (level === 'fixed') {
            const marks = proc.redundancyPairMarks || [];
            const on = proc.redundancyPairs || marks;
            if (marks.length && on.length < marks.length) {
                text = on.map(m => `${m} to ${String.fromCharCode(m.charCodeAt(0) + 1)}`).join(', ');
            }
        }
        if (level === 'unit') {
            const one = (proc.slots || []).map(s => s.card).find(Boolean);
            const found = one && one.backupCardId && typeof this._otherCards === 'function'
                ? this._otherCards(one.id).find(x => x.card.id === one.backupCardId) : null;
            if (found && typeof this._backupUnitTitle === 'function') {
                text += ` → ${this._backupUnitTitle(found.proc, found.card)}`;
            }
        }
        if (proc.backupUnit) text += ` · backed up by ${proc.backupUnit.name}`;
        return text;
    }

    // The processor and card a socket sits on, for the data sheet's bands.
    // `unitTitle` is what the sheets PRINT - the unit named once
    // (dataUnitTitle: a NovaPro UHD Jr's card is the processor, so it is
    // "IMAG SR", not "IMAG SR IMAG SR"); `named` is false where nobody
    // typed a name and the model is standing in for one, so a band knows
    // not to print the model a second time beside it.
    _bPortHome(cardId, socket) {
        const found = (typeof this._dockFindCard === 'function') ? this._dockFindCard(cardId) : null;
        if (!found) return null;
        const { proc, card } = found;
        const procTitle = proc.name || proc.deviceName || proc.id;
        const slot = (proc.slots || []).find(s => s.card && s.card.id === card.id);
        const typed = (typeof this.cardTypedName === 'function') ? this.cardTypedName(proc, card) : card.name;
        const cardTitle = typed || (slot ? `slot ${(slot.index || 0) + 1}` : card.deviceName);
        const unit = (typeof this.dataUnitTitle === 'function')
            ? this.dataUnitTitle(proc, card) : { title: `${procTitle} ${cardTitle}`, named: true };
        const n = parseInt(socket, 10);
        const box = (card.cvts || []).find(c => (c.ports || []).some(p => p.number === n)) || null;
        const port = (card.ports || []).find(p => p.number === n) || null;
        return { proc, card, procTitle, cardTitle, box, port,
                 unitTitle: unit.title, named: unit.named };
    }

    // THE HEADING OVER A RUN OF PORTS ON A SNAKE: the loom as the bracket,
    // the tray and the pull sheet already name it - "SNAKE A · 6 channel ·
    // 100'" (snakeTagText) - once, over every port riding it. Null where
    // the end is not on a snake. Each end's loom heads its own half of the
    // data sheet's Ports table (2026-09-26), so a heading names one loom. A
    // snake reaching past this unit names the sockets it holds elsewhere,
    // so its channels and the rows under it never disagree.
    //
    // A SNAKE'S HOME RUN IS SAID ONCE ON A SHEET: a loom heading both
    // halves, or two sections, keeps its length to the first heading -
    // `said` holds the snakes already headed, in the order the sheet
    // prints - and the next names the loom and where the rest of it is.
    _bSnakeHeadText(cable, said = null) {
        if (!(cable && cable.kind === 'snake' && cable.snake)) return null;
        const again = !!(said && said.has(cable.snake.id));
        if (said) said.add(cable.snake.id);
        return this.snakeTagText(cable.snake, !again)
            + (typeof this.snakeElsewhere === 'function' && cable.owner
                ? this.snakeElsewhere(cable.snake, cable.owner)
                      .map(a => ` · also ${a.text}`).join('')
                : '');
    }

    // The band over a card's ports: the unit, its model, how many ports -
    // "IMAG SR · NovaPro UHD Jr · 16 ports". Where nobody named the unit,
    // its title IS the model and the model column is dropped rather than
    // printed twice.
    // The ports a card has for the paper: the datasheet ceiling, except on
    // a box-fed unit (SX40, HELIOS), where a port exists only inside a
    // breakout box and the count is the boxes' sockets (2026-09-24).
    _bCardPortCount(card) {
        if (!card) return null;
        if (card.boxFed) return (card.ports || []).length;
        if (card.ceiling != null) return card.ceiling;
        return (card.ports || []).length || null;
    }

    _bCardBandText(home) {
        const model = home.card.deviceName || '';
        const says = model && home.unitTitle.toLowerCase().includes(model.toLowerCase());
        return [home.unitTitle, says ? '' : model,
                this._bPlural(this._bCardPortCount(home.card), 'port')]
            .filter(Boolean).join(' · ');
    }

    // A card by id as a sheet names it: the name somebody typed (the
    // unit's, for a one-box unit's face - cardTypedName), else its slot on
    // its processor - never the device's long model string.
    _bCardShort(cardId) {
        const found = (typeof this._dockFindCard === 'function') ? this._dockFindCard(cardId) : null;
        if (!found) return cardId || '—';
        const typed = (typeof this.cardTypedName === 'function')
            ? this.cardTypedName(found.proc, found.card) : found.card.name;
        if (typed) return typed;
        // a one-box unit has no slot to name: its model ("SX40")
        if (this.cardIsUnitFace(found.proc, found.card)) return this.dataUnitTitle(found.proc, found.card).title;
        const slot = (found.proc.slots || []).find(s => s.card && s.card.id === found.card.id);
        return slot ? `slot ${(slot.index || 0) + 1}` : found.card.deviceName;
    }

    // `target` is a screen or a sheet subject (_bSubject): a group's sheet
    // lists every member's ports, a member's the ports landing on its
    // cabinets - a port crossing into another member says where the rest of
    // it is ("also on WALL SL"), under its label.
    _bDataBlocks(book, target, scr) {
        const subject = this._bSubject(target);
        const layer = subject.layers[0];
        const blocks = [];
        const asgOf = (l) => ((this._assignment && this._assignment.screens) || [])
            .find(s => String(s.layerId) === String(l.id));
        const runs = this._bSubjectRuns(subject);
        // Two levels: the UNIT a port lands on (a card or a breakout box),
        // and inside it the SNAKE a run of its ports rides - one heading
        // each, in the order the ports come.
        //
        // A PORT IS ONE ROW, ITS BACKUP END BESIDE IT (2026-09-26, on an
        // SX40 sheet whose loop ends filled half the table with "backs up
        // USR A-n": "we can fit XD A and B next to each other in the same
        // table you already put what it's backing up", then "break the
        // table up half and half the xd A and b being directly on top of
        // each other is confusing"). This retires the 2026-09-12 rule that
        // gave a backup unit its own section. Where any port on the sheet
        // has a backup end, the table is two halves under PRIMARY and
        // BACKUP: each half its own PORT, OUTPUT and HOME RUN - both runs,
        // even where they read the same ("that only shows one extension")
        // - and each unit's band stands over its own half, the unit on one
        // line and its fiber on the next. PANELS is said once, at the end.
        // A sheet with no backup end prints the one half.
        // A box with fiber also carries its band strand by strand (`lines`,
        // _bBoxBandLines), drawn in place of its words.
        const bands = new Map();      // key -> { parts, lines, groups: Map, partners: Map }
        const band = (key, parts, lines = null) => {
            let b = bands.get(key);
            if (!b) { b = { parts, lines, groups: new Map(), partners: new Map() }; bands.set(key, b); }
            return b;
        };
        // A group keeps the cables its heading is read from, and the
        // heading is worded when the sheet is laid out, in print order -
        // so a snake heading two sections states its length in the first.
        const group = (b, key, primary, backup = null) => {
            let g = b.groups.get(key);
            if (!g) { g = { primary, backup, ports: [] }; b.groups.set(key, g); }
            return g;
        };
        const snakeId = (c) => (c && c.kind === 'snake' && c.snake ? c.snake.id : '');
        // An end's run. A snake is ONE home run carrying several ports -
        // "why is the same data written multiple times under the snake
        // under a specific port number" (2026-09-09) - so under its heading
        // an end on it carries only what is the PORT'S OWN, its extension
        // from the fan-out to the panel ('—' with none); an end that is not
        // on a snake reads its whole run, because no heading said it.
        const runOf = (c, headed) => (headed
            ? (snakeId(c) ? (c.ext != null ? `+${this.cableText(c.ext, '', 'data')}` : '—') : this.runText(c))
            : this.runText(c));
        const partnered = new Set();
        let procs = new Map();
        let split = false;
        for (const { carrier, run, also } of runs) {
            const asg = asgOf(carrier);
            const placed = asg && (asg.ports || []).find(p => p.number === run.num);
            const home = placed && placed.cardId ? this._bPortHome(placed.cardId, placed.port) : null;
            const cable = (typeof this.dataPortCableForScreen === 'function')
                ? this.dataPortCableForScreen(carrier, run.num) : null;
            // PANELS only: the pixels a port carries are the processor's
            // business, not the tech's at the wall (2026-09-26: "we dont
            // need to be putting the amount of pixels each port has").
            const panelsText = this._bNum((run.panels || []).length, 0);
            if (!home) {
                group(band('none', ['Not placed']), `${snakeId(cable)}|`, cable)
                    .ports.push({ label: run.label, also, out: '—', cable, back: null, panels: panelsText });
                continue;
            }
            // OUTPUT is where the port lands - the sending card ("H9 SR ·
            // 1") or, where a breakout box delivers it, the BOX instead
            // ("USR A · 3", its own silkscreen number) (2026-09-07: "list
            // the sending card order on primary and backup … if cvt's are
            // used then we will list those instead of sending card"). The
            // band over the half names the box in full.
            procs.set(home.proc.id, home.proc);
            const socket = String(home.port && home.port.localNumber != null ? home.port.localNumber : placed.port);
            let key, out, b;
            if (home.box) {
                key = `box:${home.box.id}`;
                b = band(key, this._bBoxBandParts(home.box), this._bBoxBandLines(home.box));
                out = `${this._bBoxShort(home.box)} · ${socket}`;
            } else {
                key = `card:${home.card.id}`;
                b = band(key, [this._bCardBandText(home)]);
                out = `${home.unitTitle} · ${socket}`;
            }
            const bb = (home.port && home.port.backedBy) || null;
            const end = bb ? this._bBackupEnd(carrier, run.num, bb) : null;
            // The backup end's own run, as the backup card's or box's own ≡
            // sheet typed it.
            const backupCable = end && typeof this.dataPortCable === 'function'
                ? this.dataPortCable(bb.cardId, bb.port) : null;
            if (end) {
                split = true;
                // A return on ANOTHER unit names that unit once, over the
                // backup half of the first primary band that sends a port
                // to it.
                if (end.key !== key && !partnered.has(end.key)) {
                    partnered.add(end.key);
                    b.partners.set(end.key, end.bandLines);
                }
            }
            group(b, `${snakeId(cable)}|${snakeId(backupCable)}`, cable, backupCable).ports.push({
                label: run.label, also, out, cable, panels: panelsText,
                back: end ? { label: end.label || '—', out: end.shortSocket, cable: backupCable } : null,
            });
        }
        const said = new Set();
        const rows = [];
        for (const b of bands.values()) {
            if (split) {
                const back = [...b.partners.values()];
                rows.push({ band: '', halves: [b.lines || b.parts, back.length ? back.flat() : []] });
            } else if (b.lines) {
                rows.push({ band: '', lines: b.lines });
            } else {
                rows.push({ band: b.parts.join(' · ') });
            }
            for (const g of b.groups.values()) {
                // Each half's snake heads its own half: the primary's loom
                // over the primary's rows, the backup's over the backup's.
                if (split) {
                    const heads = [g.primary, g.backup].map(c => (snakeId(c)
                        ? this._bSnakeHeadText(c, said) : null));
                    if (heads.some(Boolean)) {
                        rows.push({ band: '', sub: true, halves: heads.map(t => (t ? [t] : [])) });
                    }
                } else {
                    const head = this._bSnakeHeadText(g.primary, said);
                    if (head) rows.push({ band: head, sub: true });
                }
                const headed = !!(snakeId(g.primary) || snakeId(g.backup));
                for (const p of g.ports) {
                    const left = [p.also ? `${p.label} · ${p.also}` : p.label, p.out, runOf(p.cable, headed)];
                    if (!split) { rows.push({ cells: [...left, p.panels] }); continue; }
                    const right = p.back ? [p.back.label, p.back.out, runOf(p.back.cable, headed)] : ['', '', ''];
                    rows.push({ cells: [...left, ...right, p.panels] });
                }
            }
        }
        // (a crossing port's "· also on …" wraps under the label, so the
        // label alone is what PORT is sized to)
        const crossing = runs.some(r => r.also);
        // OUTPUT ONLY WHERE IT SAYS SOMETHING (owner, 2026-10-18): where
        // every row of the sheet, both halves, names its output as its
        // port is named - "S1 A-1" landing on "S1 A · 1" - the column
        // repeats PORT and is left out. One output that says more (a
        // custom label, a sending card, "—" where nothing is placed) keeps
        // it, for every row. Read once, over the whole table, so a table
        // running on to its "(cont.)" sheet reads the same there.
        const named = (label, out) => {
            const key = (t) => String(t || '').split(' · also on ')[0]
                .replace(/\s*[·-]\s*/g, '-').trim();
            return !!out && out !== '—' && key(label) === key(out);
        };
        const cellRows = rows.filter(r => r.cells);
        const repeats = cellRows.length > 0 && cellRows.every(({ cells: c }) => named(c[0], c[1])
            && (!split || (c[3] === '' && c[4] === '') || named(c[3], c[4])));
        const outAt = split ? [1, 4] : [1];
        const halfCols = (rule) => [{ title: 'port', rule, ...(crossing && !rule ? { list: 2 } : {}) },
                                    ...(repeats ? [] : [{ title: 'output' }]),
                                    { title: 'home run', align: 'center' }];
        const n = repeats ? 2 : 3;      // columns a half
        const ports = this._bTableLines(book, {
            title: 'Ports',
            width: DATA_COL_W,
            fit: true,
            groups: split ? [{ title: 'primary', from: 0, to: n - 1 }, { title: 'backup', from: n, to: 2 * n - 1 }] : [],
            bandsLead: true,
            cols: [...halfCols(false), ...(split ? halfCols(true) : []),
                   { title: 'panels', align: 'center', rule: split }],
            rows: repeats ? rows.map(r => (r.cells ? { ...r, cells: r.cells.filter((c, i) => !outAt.includes(i)) } : r))
                : rows,
            shrink: true,
        });
        // the sheet's columns widen to the table, never past DATA_COL_W
        const portsW = Math.ceil(ports.naturalW);
        blocks.push(portsW > COL_W ? { minW: portsW, lines: ports } : { lines: ports });
        blocks.push({ lines: this._bCableTable(book, subject, 'data') });
        // A group's FACTS are the group's (every member's pixels and panels);
        // a member's its own.
        const f = subject.kind === 'group' ? this._bGroupFacts(subject.members)
            : this._bScreenFacts(subject.member || layer);
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
        // The show's totals. The Load reads the way a screen sheet's own
        // does - amps 1φ · amps 3φ · kW, each screen's amps the ones
        // _bScreenFacts prints on its sheet, summed. Amps never blend
        // across voltages (800 W at 110 V and 800 W at 208 V are not
        // 1600 W at either): the screens group by their voltage, one
        // voltage prints the one line, more than one prints a line per
        // voltage naming it, the way the canvas readout does (app-core.js
        // "Amps (1φ) @ 208V"), and the show's kW - the one figure that
        // does add up across voltages - keeps its own line under them. A
        // screen with no circuits draws nothing and joins no voltage.
        //
        // A group routed as one wall hands every circuit to its first
        // member: that member's circuits carry its peers' panels and the
        // peers carry none. Every screen on such a wall - the one whose
        // circuits carry a peer, and a peer any of whose panels ride
        // another screen's circuits - joins its voltage with the load ITS
        // OWN circuits carry (getCarriedPowerLoad), so the wall's panels
        // are counted once, at the voltage of the circuits that feed them:
        // never dropped with the peer that has no circuits, never counted
        // twice where a member also has circuits of its own. A screen that
        // routes alone reads its own panels, as it always has.
        const screens = (this.project.layers || []).filter(l => (l.type || 'screen') === 'screen');
        const carried = new Map();
        const riding = new Set();
        if (typeof this.getCarriedPowerLoad === 'function') {
            for (const l of screens) {
                const c = this.getCarriedPowerLoad(l);
                carried.set(String(l.id), c);
                c.peerIds.forEach(id => riding.add(String(id)));
            }
        }
        let panels = 0, watts = 0, circuits = 0, ports = 0;
        const byVoltage = new Map();
        for (const l of screens) {
            const f = this._bScreenFacts(l);
            panels += f.active; watts += f.watts;
            const scr = list.byScreen[l.id];
            let mine = 0;
            if (scr) {
                mine = (scr.boxes || []).reduce((a, b) => a + (b.circuits || []).length, 0);
                circuits += mine;
                ports += (scr.ports || []).length;
            }
            const c = carried.get(String(l.id));
            const onWall = !!c && (c.peerIds.length > 0 || riding.has(String(l.id)));
            const w = onWall ? c.watts : f.watts;
            if (!(f.voltage > 0) || (onWall ? !(w > 0) : !(mine > 0))) continue;
            const bucket = byVoltage.get(f.voltage) || { voltage: f.voltage, watts: 0, amps1: 0, amps3: 0 };
            bucket.watts += w;
            bucket.amps1 += w / f.voltage;
            bucket.amps3 += w / (this.threePhaseLineVoltage(l) * 1.73);
            byVoltage.set(f.voltage, bucket);
        }
        const loadText = (b) => `${this._bNum(b.amps1, 1)} A 1φ · ${this._bNum(b.amps3, 1)} A 3φ · ${this._bNum(b.watts / 1000, 1)} kW`;
        const loads = [];
        const one = byVoltage.size === 1 ? [...byVoltage.values()][0] : null;
        if (one && Math.abs(one.watts - watts) < 0.5) {
            loads.push(['Load', loadText(one)]);
        } else {
            // Two voltages - or a screen with watts and no circuits, whose
            // kW is the show's but whose amps are nobody's: the voltage's
            // own line, then the show's kW.
            for (const b of byVoltage.values()) loads.push([`Load @ ${b.voltage} V`, loadText(b)]);
            loads.push(['Load', `${this._bNum(watts / 1000, 1)} kW`]);
        }
        const distros = (typeof this.getDistros === 'function') ? this.getDistros() : [];
        const procs = this._processorsResolved || [];
        blocks.push({ lines: this._bKvLines(book, 'Show totals', [
            ['Screens', String(screens.length)],
            ['Panels', this._bNum(panels, 0)],
            ['Circuits', String(circuits)],
            ['Ports', String(ports)],
            ...loads,
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
    // like the maps, so it prints sharp. Returns the rect it used, with
    // `screens`: each screen's page rect.
    //
    // Every screen then wears its own OUTLINE over the bitmap - its
    // bounding rectangle stroked in INK, 3 px, through the recorder's
    // rect op so it reaches the PDF as vector - at the page position the
    // same world -> page mapping the crop used gives it. Walls that sit
    // edge to edge (his SR / SL MAINs and Returns) read as one wall in
    // the bitmap - one grey in the printer palette, the Returns one
    // colour - so the outlines tell them apart ("the screens look
    // combined on SR and SL", 2026-09-08); where two touch, the two
    // outlines coincide into one rule, which is separation enough - no
    // screen moves, no gap is added. A rotated screen is outlined by its
    // axis-aligned bounds (getLayerBounds - the box its cabinets fill),
    // not turned with it. The screen-name plates the renderer draws stay.
    _bShowMap(book, area) {
        // The overview is ALWAYS the front, whatever the set's View says
        // and whatever the workspace's toggles say.
        return this._bWithPerspective('front', () => this._bPaintShowMap(book, area));
    }

    _bPaintShowMap(book, area) {
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
            const worldRects = [];      // each screen's bounds in the show's world
            for (const layer of screens) {
                const cid = (layer.show_canvas_id || layer.canvas_id) || null;
                const canvas = canvases.find(c => c && c.id === cid) || null;
                if (canvases.length && (!canvas || canvas.visible === false)) continue;
                const ws = r._canvasWorkspace(canvas);
                const b = r.getLayerBounds(layer);
                const { dx, dy } = r.getLayerRenderOffset(layer);
                const wr = { id: layer.id, name: layer.name, x: ws.wx + b.x + dx, y: ws.wy + b.y + dy, w: b.width, h: b.height };
                worldRects.push(wr);
                x1 = Math.min(x1, wr.x); y1 = Math.min(y1, wr.y);
                x2 = Math.max(x2, wr.x + wr.w); y2 = Math.max(y2, wr.y + wr.h);
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
            // the world -> page mapping the crop uses, applied to each screen
            const round = (v) => Math.round(v * 100) / 100;
            const screenRects = worldRects.map(wr => ({
                id: wr.id, name: wr.name,
                x: round(dx + (wr.x - x1) * zoom), y: round(dy + (wr.y - y1) * zoom),
                w: round(wr.w * zoom), h: round(wr.h * zoom),
            }));
            used = { x: dx, y: dy, w: drawW, h: drawH, zoom, screens: screenRects };
            if (book.log) book.log.map = { x: dx, y: dy, w: drawW, h: drawH, zoom, area: { ...area }, screens: screenRects };
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
            // every screen's own outline, both palettes
            book.ctx.strokeStyle = INK;
            book.ctx.lineWidth = 3;
            for (const sr of screenRects) book.ctx.strokeRect(sr.x, sr.y, sr.w, sr.h);
        } finally {
            r.canvas = saved.canvas; r.ctx = saved.ctx; r.exportMode = saved.exportMode;
            r.exportTransparentBg = saved.transparent; r.printerMode = saved.printer;
            r.viewMode = saved.viewMode; r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
        }
        return used;
    }

    // ---- the pull sheets (3.n) ----------------------------------------------

    // The positions side by side, each headed with its name, as many as fit
    // a sheet; the sheet named by the positions it carries - "PULL · SR -
    // MAIN, SR - Return, …". A position's sections - POWER CABLES, DATA
    // CABLES, HARDWARE, SCREENS - FLOW ACROSS THE SHEET in columns rather
    // than down one narrow column at its left edge (2026-10-18: "we dont
    // have to have all the text vertical in a column like it is. it can
    // space out to the right"): each column as wide as its sections need
    // whole - a label list, a hardware row's details on one line, the
    // Screens table's headings in full - and the sections, kept whole and
    // in order, split into the columns that let the sheet print largest
    // (_bPullSpread). Which positions share a sheet is decided first, each
    // at its narrowest - PULL_COL_W, so a sheet carries the positions it
    // always has (four to a Tabloid) - and the room left over then goes to
    // spreading them. A position taller than a sheet in every arrangement
    // runs down columns of PULL_COL_W and continues on the next sheet,
    // "(cont.)", which stays at 1.
    _bPullSheets(book, positions) {
        const groups = positions.map(({ pos, members }) =>
            ({ kind: 'pull', name: pos.name, blocks: this._bPullBlocks(book, pos, members) }));
        const label = (gs) => gs.map(g => g.name + (g.cont ? ' (cont.)' : '')).join(', ');
        const page = (gs) => ({ kind: 'pull', title: `Pull - ${label(gs)}`, sheetTitle: `PULL · ${label(gs)}`,
                                subject: label(gs) });
        const da = book.geo.da;
        const colH = da.h - GROUP_H;
        const queue = groups.map(g => ({ ...g, cont: false,
                                         blocks: (g.blocks || []).filter(b => b && (b.lines || []).length) }))
            .filter(g => g.blocks.length);
        while (queue.length) {
            const placed = [];          // { group, options }
            let used = 0, continues = false;
            while (queue.length) {
                const g = queue[0];
                const gap = placed.length ? COL_GAP : 0;
                const options = this._bPullArrangements(g.blocks, colH, da.w - used - gap, da.w);
                if (options.length) {
                    placed.push({ group: g, options });
                    used += gap + Math.min(...options.map(o => o.w));
                    queue.shift();
                    continue;
                }
                if (placed.length) break;           // it starts the next sheet
                const cut = this._bPullCut(g.blocks, colH, da.w);
                placed.push({ group: g, options: [cut.option] });
                queue.shift();
                if (cut.rest.length) {
                    queue.unshift({ ...g, blocks: cut.rest, cont: true });
                    continues = true;
                    break;
                }
                used = cut.option.w;
            }
            if (!placed.length) break;
            const lay = continues ? null : this._bPullSpread(book, placed);
            const picks = lay ? lay.picks
                : placed.map(p => p.options.reduce((a, o) => (o.w < a.w ? o : a)));
            const extent = lay ? lay.extent
                : { w: picks.reduce((s, o) => s + o.w, 0) + (picks.length - 1) * COL_GAP,
                    h: GROUP_H + Math.max(...picks.map(o => o.h)) };
            const scale = lay ? lay.scale : 1;
            const heads = placed.map(p => p.group.name + (p.group.cont ? ' (cont.)' : ''));
            const cols = picks.reduce((n, o) => n + o.cols.length, 0);
            this._bPage(book, { ...page(placed.map(p => p.group)), layout: 'tables', cols, scale, extent,
                                names: heads }, (pg, scaled) => scaled(() => {
                let x = da.x;
                picks.forEach((o, j) => {
                    this._bGroupHead(book, heads[j], x, da.y, o.w);
                    let cx = x;
                    for (const col of o.cols) {
                        for (const it of col.items) it.line.draw(book.ctx, cx, da.y + GROUP_H + it.y, col.w);
                        cx += col.w + COL_GAP;
                    }
                    x += o.w + COL_GAP;
                });
            }));
        }
    }

    // A pull table as a block that can be laid out at any width: its lines
    // at the pull sheet's base column (`lines`), `make(w)` for its lines in
    // a column w wide, and the widths the sheet chooses between besides
    // PULL_COL_W (four positions to a Tabloid, as the sheet has always
    // held: the Screens table's headings set smaller there rather than
    // cut) - `wMin`, the narrowest that cuts and shrinks nothing (every
    // heading in full), and `wNat`, its natural width, every list on one
    // line too - each kept between PULL_COL_W and PULL_COL_MAX (a longer
    // list wraps as it did).
    _bPullBlock(book, spec) {
        const padX = 12;
        const s = { ...spec, whole: true };
        const cache = new Map();
        const make = (w) => {
            if (!cache.has(w)) cache.set(w, this._bTableLines(book, { ...s, width: w }));
            return cache.get(w);
        };
        const sum = (a) => a.reduce((x, y) => x + y, 0);
        const clamp = (v) => Math.min(PULL_COL_MAX, Math.max(PULL_COL_W, Math.ceil(v)));
        // every heading in full - LENGTH's too (_bColWidths)
        const full = s.cols.map(c => ({ ...c, headShrink: false }));
        const wMin = clamp(sum(this._bColNeeds(book, full, s.rows, padX)));
        const wNat = Math.max(wMin, clamp(sum(this._bColNeeds(book, full, s.rows, padX, true))));
        return { lines: make(PULL_COL_W), make, wTight: PULL_COL_W, wMin, wNat };
    }

    // Every way a position's blocks, whole and in order, go into columns
    // side by side no taller than colH and no wider in all than availW:
    // each split of the run into consecutive columns, each column at its
    // blocks' natural width (`tier` 2), at their narrowest with every
    // heading in full (1) and at PULL_COL_W (0). A block that cannot
    // be re-laid (a continuation's remainder) keeps the width it was laid
    // out at.
    //   [{ w, h, tier, cols: [{ w, h, items: [{ line, y }] }] }]
    _bPullArrangements(blocks, colH, availW, maxW) {
        const n = blocks.length;
        if (!n) return [];
        const widthOf = (b, key) => (b.make ? b[key] : (b.fixedW || PULL_COL_W));
        const linesAt = (b, w) => (b.make ? b.make(w) : b.lines);
        const out = [];
        const seen = new Set();
        const splits = n <= 10 ? 1 << (n - 1) : 1;
        for (let m = 0; m < splits; m++) {
            const runs = [];
            let cur = [];
            blocks.forEach((b, i) => {
                cur.push(b);
                if (i < n - 1 && ((m >> i) & 1)) { runs.push(cur); cur = []; }
            });
            runs.push(cur);
            for (const [tier, key] of [[2, 'wNat'], [1, 'wMin'], [0, 'wTight']]) {
                const widths = runs.map(run => Math.min(maxW, Math.max(...run.map(b => widthOf(b, key)))));
                const w = widths.reduce((s, x) => s + x, 0) + (runs.length - 1) * COL_GAP;
                const id = `${m}:${widths.join(',')}`;
                if (w > availW || seen.has(id)) continue;
                seen.add(id);
                const cols = runs.map((run, c) => {
                    const col = { w: widths[c], h: 0, items: [] };
                    let y = 0;
                    run.forEach((b, k) => {
                        if (k) y += BLOCK_GAP;
                        for (const line of linesAt(b, widths[c])) { col.items.push({ line, y }); y += line.h; }
                    });
                    col.h = y;
                    return col;
                });
                if (cols.some(c => c.h > colH)) continue;
                out.push({ w, h: Math.max(...cols.map(c => c.h)), cols, tier });
            }
        }
        return out;
    }

    // A position no arrangement holds: its blocks down columns of
    // PULL_COL_W, split where a column ends, as many columns as the sheet
    // has; what is left comes back as `rest` for the next sheet, laid out
    // at that width.
    _bPullCut(blocks, colH, availW) {
        const colW = Math.min(availW, Math.max(...blocks.map(b => (b.make ? b.wTight : (b.fixedW || PULL_COL_W)))));
        const across = Math.max(1, Math.floor((availW + COL_GAP) / (colW + COL_GAP)));
        const pack = this._bPack(blocks.map(b => (b.make ? { lines: b.make(colW) } : b)), colH, across);
        const cols = pack.cols.map(c => ({ w: colW, h: c.h, items: c.items }));
        return { option: { w: cols.length * colW + (cols.length - 1) * COL_GAP,
                           h: Math.max(0, ...cols.map(c => c.h)), cols },
                 rest: pack.rest.map(r => ({ ...r, fixedW: colW })) };
    }

    // The sheet's arrangement: for each height the columns might reach, every
    // position at its narrowest arrangement that stays under it; of those,
    // the one that prints largest (_bFillScale), and among any within 2 %
    // of that, the one that spreads widest across the sheet. Arrangements
    // whose columns are all at their natural width - no label list or
    // hardware detail wrapped - win wherever they print at least
    // PULL_WHOLE_KEEP of the largest any arrangement could; else ones with
    // every heading in full wherever the sheet holds them; else the
    // narrow columns.
    //   { picks: [arrangement per position], scale, extent }
    _bPullSpread(book, placed) {
        const da = book.geo.da;
        const choose = (tier) => {
            const opts = placed.map(p => p.options.filter(o => o.tier >= tier));
            if (opts.some(os => !os.length)) return null;
            const heights = [...new Set(opts.flat().map(o => o.h))].sort((a, b) => a - b);
            const cands = [];
            for (const top of heights) {
                const picks = [];
                for (const os of opts) {
                    let o = null;
                    for (const x of os) {
                        if (x.h <= top && (!o || x.w < o.w || (x.w === o.w && x.h < o.h))) o = x;
                    }
                    if (!o) break;
                    picks.push(o);
                }
                if (picks.length !== placed.length) continue;
                const w = picks.reduce((s, o) => s + o.w, 0) + (picks.length - 1) * COL_GAP;
                if (w > da.w) continue;
                const extent = { w, h: GROUP_H + Math.max(...picks.map(o => o.h)) };
                cands.push({ picks, extent, scale: this._bFillScale(book, extent) });
            }
            if (!cands.length) return null;
            const best = Math.max(...cands.map(c => c.scale));
            const span = (c) => c.extent.w * c.scale;
            return cands.filter(c => c.scale >= best / 1.02)
                .reduce((a, c) => (span(c) > span(a) + 0.5
                    || (Math.abs(span(c) - span(a)) <= 0.5 && c.scale > a.scale) ? c : a));
        };
        const any = choose(0);
        const whole = choose(2);
        if (whole && any && whole.scale >= any.scale * PULL_WHOLE_KEEP) return whole;
        return choose(1) || any;
    }

    _bPullBlocks(book, pos, members) {
        const list = book.list;
        const tick = { title: '', w: 0.28, tick: true };
        const cableCols = [tick, { title: 'cable', w: 1.5, lend: true }, { title: 'length', w: 0.6, borrow: 'len' },
                           { title: 'qty', w: 0.5, align: 'right', lend: true },
                           { title: 'label', w: 1.4, list: true }];
        const cableRows = (side) => (pos.rows || []).filter(r => (r.side || 'power') === side)
            .map(r => ({ cells: ['', this._bType(r.type), r.length || '—', this._bQty(r.qty), r.label || ''] }));
        const blocks = [];
        const power = cableRows('power');
        blocks.push(this._bPullBlock(book, { title: 'Power cables', cols: cableCols,
            rows: power.length ? power : [{ cells: ['', 'none', '', '', ''] }] }));
        const data = cableRows('data');
        blocks.push(this._bPullBlock(book, { title: 'Data cables', cols: cableCols,
            rows: data.length ? data : [{ cells: ['', 'none', '', '', ''] }] }));
        // Header and footer bars (Header/Footer tab): their own tables, and only where this
        // position has any - a show with no rigging prints exactly what it did.
        const rigging = (pos.rows || []).filter(r => r.side === 'rigging');
        for (const [title, word] of [['Header bars', 'Header'], ['Footer bars', 'Footer']]) {
            const rows = rigging.filter(r => String(r.type || '').startsWith(word))
                .map(r => ({ cells: ['', this._bType(r.type), r.length || '\u2014', this._bQty(r.qty), r.label || ''] }));
            if (rows.length) blocks.push(this._bPullBlock(book, { title, cols: cableCols, rows }));
        }
        // Hardware: the socas, the distros, the cards these screens hang on.
        const hw = [];
        const seenBox = new Set(), seenDistro = new Set(), seenCard = new Set();
        for (const layer of members) {
            const scr = list.byScreen[layer.id];
            for (const box of (scr && scr.boxes) || []) {
                if (seenBox.has(box.key)) continue;
                seenBox.add(box.key);
                hw.push({ cells: ['', box.name, [box.type || 'no distro',
                    box.homeRun ? this.pullLengthText(box.homeRun, this.pullHomeRunKind(box)) : 'no length'].join(' · ')] });
                if (box.distroId && !seenDistro.has(box.distroId)) {
                    seenDistro.add(box.distroId);
                    const d = (this.getDistros ? this.getDistros() : []).find(x => x.id === box.distroId);
                    if (d) hw.push({ cells: ['', d.name, `distro · ${this._bDistroRatingText(d)}`] });
                }
            }
            const asg = ((this._assignment && this._assignment.screens) || [])
                .find(s => String(s.layerId) === String(layer.id));
            for (const cid of (asg && asg.cardIds) || []) {
                if (seenCard.has(cid)) continue;
                seenCard.add(cid);
                const home = this._bPortHome(cid, 0);
                if (home) hw.push({ cells: ['', home.unitTitle,
                                            home.named ? home.card.deviceName : ''] });
            }
        }
        blocks.push(this._bPullBlock(book, {
            title: 'Hardware',
            cols: [tick, { title: 'item', w: 1.2 }, { title: 'detail', w: 2, list: true }],
            rows: hw.length ? hw : [{ cells: ['', 'none', ''] }],
        }));
        // Screens with their gang counts - named as the set prints them,
        // each SIDE by its own tab (owner, 2026-10-01: "Depends on if it is
        // power or data and on if grouped or screen group"). A group routed
        // as one and printed as the group on a side has ONE line carrying
        // that side's figures - the circuits and shared circuits for Power,
        // the ports for Data - every member's summed; printed by screens,
        // a line per member carrying them, each counting what its own sheet
        // lists (a crossing circuit or port on each member it touches). So
        // Power on Group with Data on Screens is one power line for the
        // group and a data line per member; Group on both, one line. The
        // group's line leaves SIZE and PANELS to the member lines where
        // there are any, so no cabinet is counted twice.
        // A side not routed as one reads each member's own.
        // 4fers and wider (a circuit split into its own columns) ride in
        // `wider`, keyed by their ways (app-pull-list.js).
        const gangText = (g) => [g.twofer ? `${g.twofer}× 2fer` : '', g.threefer ? `${g.threefer}× 3fer` : '',
            ...Object.keys(g.wider || {}).map(Number).sort((a, b) => a - b)
                .map(w => (g.wider[w] ? `${g.wider[w]}× ${w}fer` : ''))]
            .filter(Boolean).join(', ') || '—';
        const addWider = (into, from) => Object.keys((from && from.wider) || {}).forEach(w => {
            into.wider = into.wider || {};
            into.wider[w] = (into.wider[w] || 0) + from.wider[w];
        });
        const own = (layer) => {
            const scr = list.byScreen[layer.id] || { boxes: [], ports: [], gangs: {} };
            return { circuits: (scr.boxes || []).reduce((a, b) => a + (b.circuits || []).length, 0),
                     ports: (scr.ports || []).length, gangs: scr.gangs || {},
                     panels: (layer.panels || []).filter(p => p && !p.blank && !p.hidden).length };
        };
        // A member's figures on a side printed by screens: what its sheet lists.
        const listed = (gp, layer) => {
            const s = this._bMemberSubject(gp, layer);
            const units = this._bSubjectBoxes(book, s);
            const gangs = { twofer: 0, threefer: 0 };
            for (const u of units) {
                const byNum = new Map(((typeof this.screenCircuits === 'function') ? this.screenCircuits(u.carrier) : [])
                    .map(c => [c.num, c]));
                for (const c of u.box.circuits || []) {
                    const ways = ((byNum.get(c.num) || {}).runIds || []).length;
                    if (ways === 2) gangs.twofer++;
                    else if (ways === 3) gangs.threefer++;
                    else if (ways > 3) addWider(gangs, { wider: { [ways]: 1 } });
                }
            }
            return { circuits: units.reduce((a, u) => a + (u.box.circuits || []).length, 0),
                     ports: this._bSubjectRuns(s).length, gangs };
        };
        const screens = [];
        const rowed = new Set();
        for (const layer of members) {
            const gp = this._bGroupPlanOf(book, layer);
            if (!gp) {
                const f = own(layer);
                screens.push({ cells: ['', layer.name, `${layer.columns} × ${layer.rows}`, String(f.panels),
                                       String(f.circuits), String(f.ports), gangText(f.gangs)] });
                continue;
            }
            if (rowed.has(gp.id)) continue;
            rowed.add(gp.id);
            const here = gp.members.filter(m => members.includes(m));
            const fs = gp.members.map(own);
            const sum = (k) => fs.reduce((a, f) => a + f[k], 0);
            const groupGangs = { twofer: fs.reduce((a, f) => a + (f.gangs.twofer || 0), 0),
                                 threefer: fs.reduce((a, f) => a + (f.gangs.threefer || 0), 0) };
            fs.forEach(f => addWider(groupGangs, f.gangs));
            const pGroup = gp.mode.power === 'group', dGroup = gp.mode.data === 'group';
            const size = gp.members.map(m => `${m.columns} × ${m.rows}`).join(' + ');
            if (pGroup && dGroup) {
                screens.push({ cells: ['', gp.name, size, String(sum('panels')), String(sum('circuits')),
                                       String(sum('ports')), gangText(groupGangs)] });
                continue;
            }
            if (pGroup || dGroup) {
                screens.push({ cells: ['', gp.name, '—', '—',
                                       pGroup ? String(sum('circuits')) : '—',
                                       dGroup ? String(sum('ports')) : '—',
                                       pGroup ? gangText(groupGangs) : '—'] });
            }
            for (const m of here) {
                const o = own(m);
                const mine = (gp.mode.power === 'screens' || gp.mode.data === 'screens') ? listed(gp, m) : null;
                const circuits = pGroup ? '—' : String(gp.mode.power === 'screens' ? mine.circuits : o.circuits);
                const ports = dGroup ? '—' : String(gp.mode.data === 'screens' ? mine.ports : o.ports);
                const gangs = pGroup ? '—' : gangText(gp.mode.power === 'screens' ? mine.gangs : o.gangs);
                screens.push({ cells: ['', m.name, `${m.columns} × ${m.rows}`, String(o.panels),
                                       circuits, ports, gangs] });
            }
        }
        blocks.push(this._bPullBlock(book, {
            title: 'Screens',
            cols: [tick, { title: 'screen', w: 1.3 }, { title: 'size', w: 0.7 },
                   { title: 'panels', w: 0.6, align: 'right' }, { title: 'circuits', w: 0.6, align: 'right' },
                   { title: 'ports', w: 0.5, align: 'right' }, { title: 'shared', w: 0.9 }],
            rows: screens,
            // Seven columns: the sheet gives the table the width its
            // headings and cells need whole (_bPullBlock - "CIRCU…" in the
            // old narrow column, 2026-10-18); in a column narrower than
            // that the headings take the room their neighbours spare
            // (_bColWidths) and the cells shrink a little rather than cut
            // ("28× 2fer").
            shrink: true,
        }));
        return blocks;
    }

    // ---- hardware sheets (4.n) ----------------------------------------------

    // The distros side by side on their sheets, then the processors the
    // same way with the show's pull list beside them where there is room
    // (on the right), else on its own; each subject a titled column, the
    // sheet named by what it carries - "DISTROS · SR, SL", "PROCESSORS ·
    // H9 · PULL LIST", "PULL LIST · ALL POSITIONS".
    _bHardwareSheets(book, groups) {
        const list = (gs, kind) => gs.filter(g => g.kind === kind).map(g => g.name + (g.cont ? ' (cont.)' : '')).join(', ');
        const spec = {
            page: (gs) => {
                const distros = list(gs, 'distro'), procs = list(gs, 'processor');
                const services = list(gs, 'service');
                const totals = gs.some(g => g.kind === 'totals');
                if (services) {
                    const one = gs.filter(g => g.kind === 'service').length === 1;
                    return { kind: 'service', title: `${one ? 'Service' : 'Services'} - ${services}`,
                             sheetTitle: `${one ? 'SERVICE' : 'SERVICES'} · ${services}`, subject: services };
                }
                if (distros) {
                    const one = gs.filter(g => g.kind === 'distro').length === 1;
                    return { kind: 'distro', title: `${one ? 'Distro' : 'Distros'} - ${distros}`,
                             sheetTitle: `${one ? 'DISTRO' : 'DISTROS'} · ${distros}`, subject: distros };
                }
                if (procs) {
                    const one = gs.filter(g => g.kind === 'processor').length === 1;
                    const also = totals ? ' · Pull list' : '';
                    return { kind: 'processor', title: `${one ? 'Processor' : 'Processors'} - ${procs}${also}`,
                             sheetTitle: `${one ? 'PROCESSOR' : 'PROCESSORS'} · ${procs}${also.toUpperCase()}`,
                             subject: procs };
                }
                return { kind: 'totals', title: 'Pull list - all positions', sheetTitle: 'PULL LIST · ALL POSITIONS',
                         subject: 'All positions' };
            },
        };
        this._bColumnSheets(book, spec, groups.filter(g => g.kind === 'service'));
        this._bColumnSheets(book, spec, groups.filter(g => g.kind === 'distro'));
        this._bColumnSheets(book, spec, groups.filter(g => g.kind !== 'distro' && g.kind !== 'service'));
    }

    // A SERVICE's column (2026-10-20, app-services.js): its distros with
    // their ratings and their leg loads, the leg totals as the service's
    // last row, then the service's own block - its size, the ratings added
    // up against it, its load against its limit (OVER named per leg) and
    // its imbalance. House power is not pulled, so no pull list.
    _bServiceGroup(book, s) {
        const load = this.getServiceLoads().find(x => x.id === s.id);
        if (!load) return null;
        const names = load.legs ? (load.legs.names || []) : [];
        const amps = (L) => names.length
            ? names.map(k => this._bNum(L && L.legs ? L.legs[k].amps : 0, 1))
            : [this._bNum(L ? L.amps : 0, 1)];
        const rows = load.distros.map(({ distro: d, load: L }) => ({
            cells: [d.name || d.id, `${this._bNum(d.ratingA, 0)} A`, ...amps(L)],
        }));
        if (rows.length) {
            rows.push({ cells: ['total', `${this._bNum(load.ratingSum, 0)} A`,
                                ...(names.length ? names.map(k => this._bNum(load.legs[k].amps, 1))
                                    : [this._bNum(load.amps, 1)])] });
        }
        const legCols = names.length
            ? names.map(k => ({ title: this.distroLegLabel(s, k), w: 0.6, align: 'right' }))
            : [{ title: 'amps', w: 0.7, align: 'right' }];
        const blocks = [];
        blocks.push({ lines: this._bTableLines(book, {
            title: this._bPlural(load.distros.length, 'distro'),
            cols: [{ title: 'distro', w: 1.1 }, { title: 'rating', w: 0.7, align: 'right' }, ...legCols],
            rows: rows.length ? rows : [{ cells: ['none', '', ...legCols.map(() => '')] }],
            shrink: true,
        }) });
        const rule = this.distroMainLimit(s);
        const pairs = [['Rating', `${this.serviceSizeText(s)}${rule.main100 ? ' · 100% rated' : ''}`]];
        pairs.push(['Distros', `ratings ${this._bNum(load.ratingSum, 0)} A on ${this._bNum(load.ratingA, 0)} A`
            + (load.ratingsOver ? ' · past the service' : '')]);
        if (load.distros.length) {
            pairs.push(['Load', this._bDistroLoadText(s, load)]);
            if (load.legs) pairs.push(['Imbalance', `${this._bNum(load.imbalancePct, 1)}%`]);
        }
        blocks.push({ lines: this._bKvLines(book, 'Service', pairs) });
        return { kind: 'service', name: s.name || s.id, blocks };
    }

    // A distro's column: its units, SERVICE, its pull list; null where it
    // has nothing.
    _bDistroGroup(book, d) {
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
            let lone = null;    // { layer, circuit } of the last circuit seen
            const names = [];
            for (const m of members) {
                const layer = book.layers.get(String(m.layerId));
                if (!layer) continue;
                // a wall printed as its group on Power is named by the
                // group, the way its Power sheet is (2026-10-01)
                const gp = this._bGroupPlanOf(book, layer);
                if (!(gp && gp.mode.power === 'group')) names.push(layer.name);
                else if (!names.includes(gp.name)) names.push(gp.name);
                const s = this.getSocaPlan(layer).find(x => x.soca === m.soca);
                if (!s) continue;
                if (!homeRun) homeRun = this.parseCableLength(s.length);
                circuits += (s.legs || []).length;
                amps += (s.legs || []).reduce((a, l) => a + (Number(l.amps) || 0), 0);
                if ((s.legs || []).length) lone = { layer, circuit: s.legs[0].circuit };
            }
            // A DIRECT output with one circuit on it has ONE cable, distro
            // to screen - the circuit's own when typed, else the home run -
            // read through the helper the map's tag and the pull sheet use,
            // so this table never contradicts them. A crowded output (the
            // flagged error state) keeps the output's home run.
            const fbox = typeof this.faceBox === 'function' ? this.faceBox(d, number) : null;
            if (fbox && fbox.kind === 'direct' && circuits === 1 && lone) {
                const one = this.directCircuitCable(lone.layer, lone.circuit);
                homeRun = one ? one.ft : null;
            }
            allCircuits += circuits;
            boxes.push({ cells: [`${d.name} ${number}`, typed ? typed.name : '—',
                                 homeRun ? this.pullLengthText(homeRun, this.pullHomeRunKind(fbox)) : 'no length',
                                 names.join(' + '), String(circuits), this._bNum(amps, 1)] });
        }
        // The table is named by what it lists - "4 Multi 208 · 1 L21-30" -
        // the units by their types, no generic noun (2026-09-07, "no need
        // to call it a breakout").
        const counts = [...byType.entries()].map(([name, n]) => `${n} ${name}`).join(' · ')
            || 'nothing on this distro';
        if (!boxes.length && !load) return null;
        return { kind: 'distro', name: d.name, blocks: this._bDistroBlocks(book, d, load, boxes, counts, allCircuits) };
    }

    _bDistroBlocks(book, d, load, boxes, counts, allCircuits) {
        const blocks = [];
        blocks.push({ lines: this._bTableLines(book, {
            title: counts,
            // TYPE and HOME RUN hold "Multi 208" and "no length" whole; the
            // cells shrink a little before they cut
            cols: [{ title: 'name', w: 0.75 }, { title: 'type', w: 1.05 }, { title: 'home run', w: 0.95 },
                   { title: 'screens', w: 1.5 }, { title: 'circuits', w: 0.8, align: 'right' },
                   { title: 'amps', w: 0.7, align: 'right' }],
            rows: boxes.length ? boxes : [{ cells: ['none', '', '', '', '', ''] }],
            shrink: true,
        }) });
        const pairs = [['Rating', this._bDistroRatingText(d)]];
        // The service it is fed from (2026-10-20, app-services.js).
        const svc = typeof this.distroService === 'function' ? this.distroService(d) : null;
        if (svc) pairs.push(['Fed from', this.serviceLabel(svc)]);
        // The face (1.5): one line per output row, a paired row printed
        // ONCE with both connectors named.
        for (const line of this._bDistroFaceLines(d)) pairs.push(['Outputs', line]);
        if (load) {
            pairs.push(['Load', this._bDistroLoadText(d, load)]);
            if (load.legs) pairs.push(['Imbalance', `${this._bNum(load.imbalancePct, 1)}%`]);
        }
        // A multi left on a one-circuit output (a show already in that
        // state, 2026-10-18): the output's load against what it carries.
        if (typeof this._faceCrowding === 'function') {
            for (const cr of this._faceCrowding(d)) {
                const cap = this._crowdCapacityText(d, cr);
                pairs.push([cap ? 'Over capacity' : 'Crowded',
                    `${cap || `${cr.where} ${cr.box.conn.short} carries ${cr.circuits} circuits`}`
                    + ' · a multi on a one-circuit output, move it to a multi output']);
            }
        }
        pairs.push(['Circuits', boxes.length ? `${allCircuits} on ${counts}` : 'none']);
        blocks.push({ lines: this._bKvLines(book, 'Service', pairs) });
        const hw = (book.list.hardware || []).find(h => h.kind === 'distro' && h.id === d.id);
        blocks.push({ lines: this._bPullLines(book, 'Pull list', (hw && hw.rows) || []) });
        return blocks;
    }

    // THE SERVICE'S LOAD ON ONE LINE (owner, 2026-10-18): every leg's amps,
    // then on a three-phase service the total three-phase amps, the power,
    // the limit it is read against and whether it is past it -
    //   "X 87.1 · Y 81.4 · Z 81.4 A · 3φ 83.4 A · 30.0 kW · limit 80 A
    //    (80% of 100 A) · OVER on X"
    // The legs are the roll-up's own phasor figures (getDistroLoads), named
    // as the distro names them (L1/L2/L3 on an EU system); 120/240 split
    // phase prints its two legs and no three-phase figure, a single hot its
    // one figure. The three-phase total is P / (V x 1.73) at the system's
    // line-to-line voltage - 208 on 120/208, 400 on 230/400 - the formula
    // rule. The limit is 80% of the rating on a US system unless its main
    // is 100% rated, said where it is not simply the rating; OVER names
    // the leg (or legs) past it, and an accepted overload is noted beside
    // the OVER it does not hide. No percentage: the limit already says how
    // the busiest leg stands, and the rating has its own line.
    _bDistroLoadText(d, load) {
        const parts = [];
        const names = load.legs ? (load.legs.names || ['X', 'Y', 'Z']) : [];
        if (names.length) {
            parts.push(names.map(k => `${this.distroLegLabel(d, k)} ${this._bNum(load.legs[k].amps, 1)}`)
                .join(' · ') + ' A');
        } else {
            parts.push(`${this._bNum(load.amps, 1)} A`);
        }
        if (names.length === 3) {
            const sys = typeof this.distroSystem === 'function' ? this.distroSystem(d) : null;
            const vll = (sys && sys.vll) || Number(d.voltage) || 0;
            if (vll > 0) parts.push(`3φ ${this._bNum(load.watts / (vll * 1.73), 1)} A`);
        }
        parts.push(`${this._bNum(load.watts / 1000, 1)} kW`);
        const rule = this.distroMainLimit(d);
        if (rule.pct < 1) parts.push(`limit ${+load.limitA.toFixed(1)} A (${this.distroMainLimitNote(rule)})`);
        else if (rule.main100) parts.push('100% rated main');
        if (load.over) {
            const past = names.filter(k => load.legs[k].over).map(k => this.distroLegLabel(d, k));
            parts.push(past.length ? `OVER on ${past.join(', ')}` : 'OVER');
            if (load.overloadAccepted) parts.push('overload accepted');
        }
        return parts.join(' · ');
    }

    // A distro's rating as the papers print it: an old-style distro (no
    // face) exactly as it always read - "400 A 208 V 3φ"; a distro with a
    // face (1.5) by its service size first, then its system, its input and
    // its breakers (owner, 2026-10-20: "it should read the service size
    // first") - "200 A service · 120/208V 3φ · 100% rated breakers". A cam
    // input is named only where it differs from the service, by its amps -
    // "600 A service · 120/208V 3φ · 400 A input"; an L21-30, CEE or
    // Powerlock input always by its name.
    _bDistroRatingText(d) {
        if (!d) return '';
        if (!this.distroFace(d)) {
            return `${d.ratingA} A ${d.voltage} V ${Number(d.phase) === 3 ? '3φ' : '1φ'}`;
        }
        const input = this.distroInputs().find(i => i.id === d.input);
        const cam = !!(input && /^cam\d+$/.test(input.id));
        const inputText = !input ? null
            : !cam ? input.name
                : Number(input.ratingA) !== Number(d.ratingA) ? `${input.ratingA} A input` : null;
        return [`${d.ratingA} A service`, this.distroSystemName(d), inputText,
                d.breakers100 && this.distroRegion(d) === 'us' ? '100% rated breakers' : null]
            .filter(Boolean).join(' · ');
    }

    // The face's rows, one line each: "4 × Socapex 208V · 24 circuits ·
    // 20 A"; a paired row folds into its partner's line, both connectors
    // named: "2 × Socapex 230V / 2 × Harting 16E 230V (paired) · 12
    // circuits · 16 A".
    _bDistroFaceLines(d) {
        const face = this.distroFace(d);
        if (!face) return [];
        const out = [];
        const name = (x) => {
            const i = face.rowInfo.get(x.id);
            return `${x.count} × ${this.faceBoxType(d, i.boxes[0]).name}`;
        };
        for (const r of face.rows) {
            if (r.pairedWith) continue;
            const info = face.rowInfo.get(r.id);
            const partners = face.rows.filter(x => x.pairedWith === r.id);
            const lead = [r, ...partners].map(name).join(' / ')
                + (partners.length ? ' (paired)' : '');
            const noun = info.conn.kind === 'direct' ? 'direct circuit' : 'circuit';
            out.push(`${lead} · ${this._bPlural(info.circuits, noun)} · ${r.breakerA} A`);
        }
        return out;
    }

    _bPullLines(book, title, rows) {
        const tick = { title: '', w: 0.28, tick: true };
        return this._bTableLines(book, {
            title,
            cols: [tick, { title: 'cable', w: 1.5, lend: true }, { title: 'length', w: 0.6, borrow: 'len' },
                   { title: 'qty', w: 0.5, align: 'right', lend: true },
                   { title: 'label', w: 1.4, list: true }],
            rows: rows.length ? rows.map(r => ({ cells: ['', this._bType(r.type), r.length || '—', this._bQty(r.qty), r.label || ''] }))
                : [{ cells: ['', 'none', '', '', ''] }],
        });
    }

    // A processor's column: CARDS, BREAKOUT BOXES, REDUNDANCY, SNAKES &
    // HOME RUNS, its pull list; null where it holds no card.
    _bProcessorGroup(book, proc) {
        const cards = (proc.slots || []).filter(s => s && s.card).map(s => ({ slot: s.index, card: s.card }));
        if (!cards.length) return null;
        // The unit's own name heads its column: a processor nobody named
        // whose FIXED card is its own face goes by the card's name
        // ("WALL A"), not by its model twice over. A processor with slots
        // keeps its own name - a card in it is a part, not the unit.
        const unit = cards.length === 1 && cards[0].card.fixed
            && typeof this.dataUnitTitle === 'function'
            ? this.dataUnitTitle(proc, cards[0].card) : null;
        const procTitle = proc.name || (unit && unit.title) || proc.deviceName || proc.id;
        return { kind: 'processor', name: procTitle, blocks: this._bProcessorBlocks(book, proc, cards, procTitle) };
    }

    // A processor's BACKUP UNIT as its own column (owner, 2026-09-25): "WALL
    // SR BU · backup of WALL SR Main", its cards - the main's again, slot
    // for slot, each backing up the main's - the switches it keeps of its
    // own (a HELIOS's RS12s, any box with no documented backup input),
    // and its redundancy, which is the main's. null without one.
    _bBackupUnitGroup(book, proc, mainTitle) {
        const unit = proc.backupUnit;
        if (!unit) return null;
        const cards = (proc.slots || []).filter(s => s && s.card);
        const blocks = [];
        // a box-fed card counts its boxes' sockets (_bCardPortCount)
        const count = (card) => (card.ceilingKnown || card.boxFed ? String(this._bCardPortCount(card)) : '?');
        // CARDS on a card-based processor, as it always read; a one-box
        // unit's is PROCESSOR - no slot - and an SQ200's OUTPUTS, each
        // by the name its face prints (_bUnitsTable's reading)
        const carded = this.procIsCardBased(proc);
        const oneBox = !carded && cards.every(s => this.cardIsUnitFace(proc, s.card));
        const lead = carded ? [{ title: 'slot', w: 0.5, align: 'right' }]
            : oneBox ? [] : [{ title: 'output', w: 0.6 }];
        const leadCell = (s) => (carded ? [String((s.index || 0) + 1)]
            : oneBox ? [] : [s.name || String((s.index || 0) + 1)]);
        blocks.push({ lines: this._bTableLines(book, {
            title: carded ? 'Cards' : oneBox ? 'Processor' : 'Outputs',
            cols: [...lead, { title: 'device', w: 1.6 },
                   { title: 'ports', w: 0.6, align: 'right' }, { title: 'backs up', w: 1.3 }],
            rows: cards.map(s => ({ cells: [...leadCell(s), s.card.deviceName, count(s.card),
                                            this.cardTypedName(proc, s.card) || mainTitle] })),
        }) });
        if ((unit.boxes || []).length) {
            blocks.push({ lines: this._bTableLines(book, {
                title: 'Breakout boxes',
                cols: [{ title: 'breakout box', w: 1.3 }, { title: 'trunk', w: 0.7 },
                       { title: 'ports', w: 0.65, align: 'right' }, { title: 'mirrors', w: 1.2 }],
                rows: unit.boxes.map(b => ({ cells: [b.deviceName, b.trunkTitle || '—',
                                                     String(b.portCount || ''), b.displayTitle || b.deviceName] })),
                shrink: true,
            }) });
        }
        // the backup inputs it feeds are in the main's Fiber connections,
        // beside the main's own (a backup is listed with its main)
        const text = this._bRedundancyText(proc).replace(/ · backed up by .*$/, '');
        blocks.push({ lines: this._bKvLines(book, 'Redundancy', [
            ['Device', proc.deviceName || proc.deviceId || ''],
            ['Redundancy', `${text} (the main's)`],
            ['Backs up', mainTitle],
        ]) });
        return { kind: 'processor', name: `${unit.name} · backup of ${mainTitle}`, blocks };
    }

    // THE PROCESSOR PAGE'S FIRST TABLE (owner, 2026-10-17: "CARD" becomes
    // "PROCESSOR" for every processor that is not card based). A card-based
    // processor (the H series, the MX2000, the MX6000 - procIsCardBased)
    // keeps CARDS exactly as it was: SLOT, CARD, DEVICE, PORTS, BACKUP. A
    // one-box unit (an SX40, an S8, a HELIOS, an MX40 Pro) has no slot and
    // no card: PROCESSOR, its DEVICE, PORTS and BACKUP on one row. A unit
    // whose named outputs each hold a unit of its own (an SQ200: OUT 1 and
    // OUT 2, a QD-S on each) reads OUTPUTS - OUTPUT as its face prints it,
    // the unit by the catalog's word ("QD 1"), DEVICE, PORTS, BACKUP.
    _bUnitsTable(proc, cards, backupOf, taken) {
        if (this.procIsCardBased(proc)) {
            return {
                title: 'Cards',
                cols: [{ title: 'slot', w: 0.5, align: 'right' }, { title: 'card', w: 1 }, { title: 'device', w: 1.6 },
                       { title: 'ports', w: 0.8, align: 'right' }, { title: 'backup', w: 1 }],
                rows: cards.map(({ slot, card }) => ({ cells: [String((slot || 0) + 1), this.cardTypedName(proc, card) || '—',
                                                              card.deviceName, taken(card), backupOf(card)] })),
            };
        }
        if (cards.every(({ card }) => this.cardIsUnitFace(proc, card))) {
            return {
                title: 'Processor',
                cols: [{ title: 'device', w: 1.6 }, { title: 'ports', w: 0.8, align: 'right' },
                       { title: 'backup', w: 1 }],
                rows: cards.map(({ card }) => ({ cells: [card.deviceName || proc.deviceName, taken(card), backupOf(card)] })),
            };
        }
        const slotName = (i) => {
            const s = (proc.slots || []).find(x => x && x.index === i);
            return (s && s.name) || String((i || 0) + 1);
        };
        return {
            title: 'Outputs',
            cols: [{ title: 'output', w: 0.6 }, { title: this.unitWordFor(proc, cards[0].card), w: 0.9 },
                   { title: 'device', w: 1.1 }, { title: 'ports', w: 0.8, align: 'right' }, { title: 'backup', w: 1 }],
            rows: cards.map(({ slot, card }) => ({ cells: [slotName(slot),
                                                          this.cardTypedName(proc, card) || card.unitTitle || '—',
                                                          card.deviceName, taken(card), backupOf(card)] })),
        };
    }

    // The Breakout boxes table's CARD / PROCESSOR cell: on a card-based
    // processor the card by name, as it always read; on a one-box unit the
    // processor's name - its model where nobody named it - never "slot 1";
    // on an SQ200 the QD-S it hangs on, "QD 1".
    _bBoxUnitCell(proc, card, nameOf) {
        if (this.procIsCardBased(proc)) return this.cardTypedName(proc, card) || nameOf(card.id);
        if (this.cardIsUnitFace(proc, card)) return this.dataUnitTitle(proc, card).title;
        return this.cardTypedName(proc, card) || card.unitTitle || nameOf(card.id);
    }

    _bProcessorBlocks(book, proc, cards, procTitle) {
        // Sockets taken on the card - primaries AND the returns landing on
        // it - the same count the tray's card header reads (socketsTaken,
        // owner 2026-09-24: "11 primary and 11 redundant ... it's 22/40").
        const used = (cardId) => {
            const count = this.socketsTaken(cardId);
            return count ? count.taken : 0;
        };
        // A card by name: its own where it is in this processor, else the
        // unit it belongs to (a 1:1 partner in ANOTHER processor - "WALL B",
        // never the raw id the sheet used to print).
        const nameOf = (cardId) => {
            const hit = cards.find(c => c.card.id === cardId);
            if (hit) return this.cardTypedName(proc, hit.card) || `slot ${(hit.slot || 0) + 1}`;
            if (!cardId) return '—';
            return this.dataUnitTitleForCard(cardId).title || cardId;
        };
        const backupOf = (card) => {
            const shape = card.redundancyShape && card.redundancyShape.mode;
            return card.backupCardId ? nameOf(card.backupCardId)
                : (shape && shape !== 'off' ? shape : '—');
        };
        const taken = (card) => `${used(card.id)} / ${this._bCardPortCount(card) != null ? this._bCardPortCount(card) : '?'}`;
        const blocks = [];
        blocks.push({ lines: this._bTableLines(book, this._bUnitsTable(proc, cards, backupOf, taken)) });
        // The breakout boxes hanging off the cards, each with the trunk it
        // takes, the sockets it delivers and its fiber trunk (2026-09-07).
        // A LOOP's two boxes (an SX40's XD A and B) sit together, the far
        // one marked "loop of" the near one (owner, 2026-09-25: "loops are
        // seperate boxes yes but really they are paired"); each keeps its
        // own fiber.
        const boxRows = [];
        for (const { card } of cards) {
            const list = card.cvts || [];
            const fars = new Set(list.filter(b => b.backupOf && list.some(n => n.id === b.backupOf))
                .map(b => b.id));
            const ordered = [];
            list.forEach(b => {
                if (fars.has(b.id)) return;
                ordered.push(b);
                list.filter(f => fars.has(f.id) && f.backupOf === b.id).forEach(f => ordered.push(f));
            });
            for (const box of ordered) {
                const near = fars.has(box.id) ? list.find(n => n.id === box.backupOf) : null;
                const title = this._bBoxTitle(box) + (near ? ` · loop of ${this._bBoxTitle(near)}` : '');
                const fiber = this._bBoxFiberParts(box);
                const groups = this._bBoxFiberGroups(box);
                boxRows.push({ cells: [title, this._bBoxUnitCell(proc, card, nameOf), box.trunkTitle || '—',
                                       this._bBoxFiberText(box)],
                               ...(fiber ? { parts: { 3: fiber } } : {}),
                               ...(groups ? { inputs: { 3: groups } } : {}) });
            }
        }
        if (boxRows.length) {
            // NO PORTS COLUMN (owner, 2026-10-17: "in this example we've
            // put X1 twice and I don't know that's needed"): the FIBER
            // groups name every input the box takes, and the box's count
            // is on its data sheet's band. The CARD / PROCESSOR column is
            // wide enough that its heading prints at the others' size.
            const unitWord = this.unitWordFor(proc, cards[0].card);
            blocks.push({ lines: this._bTableLines(book, {
                title: 'Breakout boxes',
                // FIBER wraps at its " · " - a box with a backup link reads
                // "TAC A 9-10" over "X2 TAC B 1-2" - rather than being
                // shrunk or cut; a loop's far box wraps "loop of" the same way.
                // A box on fiber cables lists each input and its strands a
                // line each, swatched (_bBoxFiberParts), and FIBER takes the
                // larger share a strand's swatch and name need.
                cols: [{ title: 'breakout box', w: 1.3, list: 2 },
                       { title: unitWord, w: unitWord === 'processor' ? 0.95 : 0.7 },
                       { title: 'trunk', w: 0.7 },
                       { title: 'fiber', w: boxRows.some(r => r.inputs || (r.parts && r.parts[3])) ? 2.4 : 1.7,
                         list: 2, parts: true, inputs: true }],
                rows: boxRows,
                shrink: true,
            }) });
        }
        // FIBER CONNECTIONS: output by output, the cable and its strands at
        // either end (the TAC pair flipped at the box) - the rack built from
        // the page.
        const conn = this._bFiberConnectionsBlock(book, proc, procTitle || proc.name || proc.deviceName || proc.id);
        if (conn) blocks.push(conn);
        // A STRAND MAP for each fiber cable whose first link this processor
        // feeds - every strand, its box and link, "spare" where none.
        for (const map of this._bStrandMaps(proc)) blocks.push({ lines: this._bTableLines(book, map) });
        // A show past this processor's canvas is flagged on its page in the
        // tray's words (port_assignment.canvas_spans) - never changed.
        const span = ((this._assignment && this._assignment.canvas) || {})[proc.id];
        blocks.push({ lines: this._bKvLines(book, 'Redundancy', [
            ['Device', proc.deviceName || proc.deviceId || ''],
            ['Redundancy', this._bRedundancyText(proc)],
            ...(span && !span.fits && span.message ? [['Canvas', span.message]] : []),
        ]) });
        // Snakes and home runs on every card and breakout box of this
        // processor. A snake is the SHOW's since 2026-09-09 ("Any sockets,
        // any device"), so it is listed ON EACH DEVICE IT TOUCHES - the
        // channels it claims are the whole loom's, and the sockets it holds
        // somewhere else are named in the same cell ("· also on CVT4K-S SR
        // B") so the count and the sockets under it always add up.
        const runs = [];
        for (const { card } of cards) {
            const owners = [{ kind: 'card', id: card.id,
                              title: this.cardTypedName(proc, card) || this.dataUnitTitle(proc, card).title,
                              rec: card }]
                .concat((card.cvts || []).map(c => ({
                    kind: 'cvt', id: c.id, title: this._bBoxTitle(c), rec: c })));
            for (const o of owners) {
                for (const s of this.getShowSnakes()) {
                    const here = this.snakeMembersOn(s, o);
                    if (!here.length) continue;
                    const connId = this.dataPortConnectorId({ rec: o.rec }, s.connector);
                    const away = this.snakeElsewhere(s, o)
                        .map(a => ` · also on ${this.dataOwnerTitle(a.owner)}`)
                        .join('');
                    // TYPE says what the run is - snake, ext, cable - so
                    // the snake's size rides its name, "SR A · 4
                    // channel", and the word snake is not said again
                    // beside the TYPE that already says it (2026-09-12:
                    // "call it 4 channel snake", and never snake twice).
                    runs.push({ cells: [`${s.name || 'snake'} · ${this.snakeSizeText('snake', (s.members || []).length)}`,
                                        'snake',
                                        s.ft ? this.pullLengthText(s.ft, 'data') : 'no length',
                                        `${o.title} ${this._fmtTails(here)}`
                                        + (connId ? ` · ${this.dataCableConnectorName(connId)}` : '')
                                        + away] });
                }
                // A socket's own entry: its home run where it is loose
                // ('cable'), its EXTENSION off the snake it rides where it
                // is snaked ('ext', the snake's name in the last column).
                // A port cable runs to the screen on its socket, so one on a
                // socket nothing is on - a primary pin or the return it
                // carries - belongs to no feed and prints nowhere (owner,
                // 2026-10-17); an older file may still hold one.
                const occ = this._assignment && this._assignment.occupancy;
                for (const [socket, c] of Object.entries(o.rec.portCables || {})) {
                    const ft = this.parseCableLength(c && c.ft);
                    if (!Number.isFinite(ft) || ft <= 0) continue;
                    if (occ && !this._portOccupants(card.id, socket).length) continue;
                    const connId = this.dataPortConnectorId({ rec: o.rec }, c.connector);
                    const snake = this.dataPortSnake(o, socket);
                    if (snake) {
                        runs.push({ cells: [`${o.title} ${socket}`, 'ext', this.pullLengthText(ft, 'data'),
                                            snake.name || 'snake'] });
                        continue;
                    }
                    runs.push({ cells: [`${o.title} ${socket}`, 'cable', this.pullLengthText(ft, 'data'),
                                        connId ? this.dataCableConnectorName(connId) : ''] });
                }
            }
        }
        blocks.push({ lines: this._bTableLines(book, {
            title: 'Snakes & home runs',
            // RUN wraps at its " · " rather than cutting a long snake
            // name off its channels.
            cols: [{ title: 'run', w: 1, list: 2 }, { title: 'type', w: 0.6 }, { title: 'home run', w: 0.8 },
                   { title: 'ports', w: 1.6, list: true }],
            rows: runs.length ? runs : [{ cells: ['none', '', '', ''] }],
        }) });
        const hw = (book.list.hardware || []).find(h => h.kind === 'processor' && h.id === proc.id);
        blocks.push({ lines: this._bPullLines(book, 'Pull list', (hw && hw.rows) || []) });
        return blocks;
    }

    // The strand maps a processor's page carries (2026-09-25): one table per
    // fiber cable (TAC, MTP, opticalCON) whose FIRST link - tray order, a
    // box's primaries then its backup inputs - comes off this processor.
    // A cable that also feeds boxes on other processors is mapped here only,
    // a line under its header saying "Also on" them. Columns: the strand (its
    // swatch and name) and the link - the box and its port, "USR B · X1";
    // an unused strand reads "spare".
    _bStrandMaps(proc) {
        if (typeof this.getFiberCables !== 'function') return [];
        const firsts = new Map();      // cableId -> processor id of its first link
        const procsOf = new Map();     // cableId -> [processor titles]
        const uses = new Map();        // cableId -> Map(strand -> { box, key })
        for (const { box, proc: p, card } of this._fiberAllBoxes()) {
            for (const key of box.fiberLinkKeys || []) {
                const link = (box.fiberLinks || {})[key];
                if (!link || !link.cable || !this.getFiberCable(link.cable)) continue;
                if (!firsts.has(link.cable)) firsts.set(link.cable, p.id);
                const names = procsOf.get(link.cable) || [];
                const title = p.name || p.deviceName || p.id;
                if (!names.includes(title)) names.push(title);
                procsOf.set(link.cable, names);
                const m = uses.get(link.cable) || new Map();
                (link.strands || []).forEach(s => { if (!m.has(s)) m.set(s, { box, key, card }); });
                uses.set(link.cable, m);
            }
        }
        const here = proc.name || proc.deviceName || proc.id;
        const out = [];
        for (const cable of this.getFiberCables()) {
            if (firsts.get(cable.id) !== proc.id) continue;
            const ft = this.parseCableLength(cable.ft);
            const also = (procsOf.get(cable.id) || []).filter(t => t !== here);
            const title = [`Strand map · ${cable.name || this.fiberKindWord(cable.kind)}`,
                           this.fiberCableTypeText(cable),
                           Number.isFinite(ft) && ft > 0 ? this.pullLengthText(ft) : '']
                .filter(Boolean).join(' · ');
            const m = uses.get(cable.id) || new Map();
            const rows = [];
            for (let n = 1; n <= (cable.strands || 0); n++) {
                const who = m.get(n);
                const piece = this._bStrandPiece(n, cable);
                rows.push({ swatch: piece.swatch,
                            cells: [piece.text,
                                    who ? `${this._bBoxTitle(who.box)} · ${this.fiberLinkTitle(who.key, who.box)}`
                                        : 'spare',
                                    who ? this._bLinkPortsText(who.box, who.card, who.key) : ''] });
            }
            out.push({ title, note: also.length ? `Also on ${also.join(', ')}` : '',
                       cols: [{ title: 'strand', w: 1.1, swatch: true }, { title: 'link', w: 2 },
                              { title: 'box ports', w: 0.8 }],
                       rows, shrink: true });
        }
        return out;
    }

    // A link's strands in the order they plug in AT THE BOX: a TAC's duplex
    // pair flips between its ends (the box's own Fiber section reads Orange
    // · Blue); an MTP or an opticalCON crosses inside the cable, so its box
    // end reads the stored order; anything else as stored. The numbers,
    // deduplicated; FIBER CONNECTIONS' AT THE BREAKOUT and the wiring
    // sheet's box both read it.
    _bStrandsAtBox(link, cable) {
        const set = [...new Set(((link && link.strands) || []).map(Number))].filter(Number.isFinite);
        return cable && cable.kind === 'tac' ? set.reverse() : set;
    }

    // THE BOX'S OWN OUTPUT PORTS A LINK CARRIES (owner, 2026-10-17: the
    // strand map says which data ports each strand feeds), as the box's
    // face numbers them: every one of them on a box taking one trunk (an
    // XD on its X1 - and on its X2, the backup of the same trunk - the
    // loop's far box on trunk B the same, a CVT4K-S switched to one OPT);
    // on a box taking two, each input its own trunk's share at the card's
    // ports per trunk, as the resolver lays them (a CVT4K-S on an
    // H_16xRJ45+2xfiber: OPT1 1-8, OPT2 9-16). '' for a card's own link (a
    // QD-S's IN 1 carries its outputs, not data ports) or where the card
    // states no ports per trunk to split by.
    _bLinkPortsText(box, card, key) {
        if (!box || box.linkHost || !box.portCount) return '';
        const n = box.portCount;
        const k = Number(String(key || '').slice(1)) || 1;
        const takes = box.trunksIn || 1;
        let lo = 1, hi = n;
        if (takes > 1) {
            const per = card && card.portsPerTrunk;
            if (!per) return '';
            lo = (k - 1) * per + 1;
            hi = Math.min(n, k * per);
            if (lo > hi) return '';
        }
        return lo === hi ? String(lo) : `${lo}-${hi}`;
    }

    // FIBER CONNECTIONS (2026-10-06): the rack built from the binder, one row
    // per fiber output of the processor - OUTPUT (the name the card's face
    // prints, card.trunkTitles; an SQ200's slot, "OUT 1", for the QD-S IN
    // link it feeds), CABLE (its kind in brackets the first time this table
    // names it), the strands AT THE PROCESSOR, then the BREAKOUT it plugs
    // into - its input on its box, "X1 on XD A" (Matt, 2026-10-06:
    // "that needs to read X1 on whatever XD"; "call it breakout") - and the
    // strands AT THE BREAKOUT, each end's strands beside the thing they plug
    // into. A link's strands are stored in the order they plug in at the
    // processor - 1 Blue · 2 Orange as the app picks them:
    //   * a TAC's duplex pair FLIPS between its ends, so AT THE BREAKOUT reads
    //     2 Orange · 1 Blue - the order the box's own Fiber section shows
    //     (Matt, 2026-10-06: the XD shows Orange · Blue); a pair rearranged
    //     on the box flips the processor side with it. A BiDi link's one
    //     strand is the same at both;
    //   * an MTP crosses inside the cable: both ends read the stored order,
    //     and the breakout end says so; an opticalCON the same - it is
    //     shared by the strand like a TAC (owner, 2026-10-08), so each
    //     link's channels are printed, then "crosses inside" at the
    //     breakout;
    //   * copper reads its run (fiberLinkSummary's words), no strands;
    //   * a box input with no cable: "no fiber picked";
    //   * an output with no box on a card that feeds boxes: "not used".
    // A box taking two trunks (a CVT4K-S) has a row per link, each on its
    // own output - OPT 1 and OPT 2. A backup processor is listed WITH its
    // main (Matt, 2026-10-06: it backs up the primary and its redundant
    // breakouts): each breakout's rows from the main, then its backup
    // inputs (X2, OPT 2, OPT 3-4, IN 2) from the backup under the SAME
    // output names - the backup mirrors the main output for output - and
    // with a backup every output is named by its processor, "S1 · trunk A"
    // and "S1 BU · trunk A". An output with nothing on it is not used on
    // either, so it is named alone. A box the backup unit twins (an RS12)
    // has no backup input and no backup row. Cards in tray order, each
    // card's outputs in order. [] where the processor feeds no box at all.
    // Rows: { cells: [output, cable, at processor, breakout, at breakout],
    // parts: { 2: [{ text, swatch }], 4: [...] } } - the strands swatched.
    _bFiberConnectionRows(proc, mainTitle) {
        if (!proc || typeof this.fiberBoxLinks !== 'function') return [];
        const main = mainTitle || proc.name || proc.deviceName || '';
        const bu = (proc.backupUnit && proc.backupUnit.name) || '';
        const named = (who, output) => (bu ? `${who} · ${output}` : output);
        const rows = [];
        const typed = new Set();
        let linked = 0;
        const unused = (output) => ({ cells: [output, 'not used', '', '', ''] });
        // the stored order: the order at the processor
        const strands = (link) => [...new Set(((link && link.strands) || []).map(Number))]
            .filter(Number.isFinite);
        // a strand to a line, whatever fits (2026-10-17: every row reads
        // the same, never two strands side by side), swatched as
        // _bStrandPiece has it
        const swatched = (list, cable) => list.map((n, j) => ({ ...this._bStrandPiece(n, cable), brk: j > 0 }));
        const joined = (parts) => parts.map(p => p.text).join(' · ');
        const linkRow = (output, l) => {
            linked++;
            const input = `${l.title} on ${this._bBoxTitle(l.box)}`;
            if (l.copper) {
                const ft = this.parseCableLength(l.copper.ft);
                const over = this.copperOverText(l.copper);
                const run = [l.copper.copper, Number.isFinite(ft) && ft > 0 ? this.pullLengthText(ft) : '']
                    .filter(Boolean).join(' ') + (over ? ` (${over})` : '');
                return { cells: [output, run, 'copper', input, 'copper'] };
            }
            const cable = l.cable;
            if (!cable) return { cells: [output, 'no fiber picked', '', input, ''] };
            let name = cable.name || this.fiberCableTypeText(cable);
            if (cable.name && !typed.has(cable.id)) name += ` (${this.fiberCableTypeText(cable)})`;
            typed.add(cable.id);
            const set = strands(l.link);
            const atProcessor = swatched(set, cable);
            const crosses = cable.kind === 'mtp' || cable.kind === 'opticalcon-duo'
                || cable.kind === 'opticalcon-quad';
            const atInput = crosses
                ? swatched(set, cable).concat([{ text: 'crosses inside', brk: true }])
                : swatched(this._bStrandsAtBox(l.link, cable), cable);
            return { cells: [output, name, joined(atProcessor), input, joined(atInput)],
                     parts: { 2: atProcessor, 4: atInput } };
        };
        // output by output (Matt's option 1): the main's output, then the
        // backup's same output onto the same breakout - p1 then b1, p2
        // then b2 on a box taking two
        const both = (box, outputOf) => {
            const links = this.fiberBoxLinks(box);
            const nth = (l) => Number(l.key.slice(1)) || 0;
            const ks = [...new Set(links.map(nth))].sort((x, y) => x - y);
            for (const k of ks) {
                links.filter(l => l.key === `p${k}`).forEach(l => rows.push(linkRow(named(main, outputOf(l)), l)));
                if (bu) links.filter(l => l.key === `b${k}`).forEach(l => rows.push(linkRow(named(bu, outputOf(l)), l)));
            }
        };
        const slots = (proc.slots || []).filter(Boolean);
        const hosts = slots.some(s => s.card && s.card.linkHost);
        // In a chassis of several cards each card has its own OPT 1: the
        // output is named with its card as the Breakout boxes table names
        // it ("SR · OPT 1", "slot 2 · OPT 1"); a card that is a unit of its
        // own already says it ("QD 1 A").
        const several = slots.filter(s => s.card).length > 1;
        const onCard = (slot, card, output) => {
            if (!several || card.unitTitle) return output;
            const named = typeof this.cardTypedName === 'function' ? this.cardTypedName(proc, card) : '';
            return `${named || `slot ${(slot.index || 0) + 1}`} · ${output}`;
        };
        for (const slot of slots) {
            const card = slot.card;
            const slotName = slot.name || `Slot ${(slot.index || 0) + 1}`;
            if (!card) {
                // an SQ200's OUT with no QD-S on it
                if (hosts) rows.push(unused(slotName));
                continue;
            }
            // an SQ200's OUT onto the QD-S's IN 1, and the backup SQ200's
            // same OUT onto its IN 2
            if (card.linkHost) both(card, () => slotName);
            const boxes = card.cvts || [];
            if (!boxes.length) continue;
            const titles = card.trunkTitles || [];
            const outputOf = (box, l) => onCard(slot, card,
                titles[(box.trunkIndex || 0) + Number(l.key.slice(1)) - 1] || box.trunkTitle || '—');
            const onTrunk = boxes.filter(b => !b.beyondTrunks && Number.isInteger(b.trunkIndex));
            for (let t = 0; t < titles.length; t++) {
                const covering = onTrunk.find(b => b.trunkIndex <= t && t < b.trunkIndex + (b.trunksIn || 1));
                if (!covering) { rows.push(unused(onCard(slot, card, titles[t]))); continue; }
                if (covering.trunkIndex !== t) continue;
                both(covering, l => outputOf(covering, l));
            }
            // a box hanging past the card's trunks (an old file), or a card
            // that names none: by the box's own trunk, after the rest
            for (const box of boxes) {
                if (titles.length && onTrunk.includes(box) && box.trunkIndex < titles.length) continue;
                both(box, l => outputOf(box, l));
            }
        }
        return linked ? rows : [];
    }

    // The Fiber connections table, on the processor's page, its backup
    // processor's rows with it. null where there is nothing.
    _bFiberConnections(proc, title) {
        const rows = this._bFiberConnectionRows(proc, title);
        if (!rows.length) return null;
        const model = proc.deviceName || proc.deviceId || '';
        const bu = (proc.backupUnit && proc.backupUnit.name) || '';
        const who = bu ? `${title} and ${bu}` : title;
        const name = [who, model && model !== title ? model : ''].filter(Boolean).join(' · ');
        return {
            title: `Fiber connections · ${name}`,
            titleShrink: true,
            // CABLE wraps between its words, the strands between strands
            // (each swatched), BREAKOUT between its words - nothing is cut.
            // A heading may shrink rather than widen the table past the
            // sheet's column (headShrink): on a narrow sheet "AT THE
            // PROCESSOR" is the widest thing in its column.
            cols: [{ title: 'output', w: 0.55, list: 2, headShrink: true },
                   { title: 'cable', w: 1.1, list: 4, words: true, headShrink: true },
                   { title: 'at the processor', w: 1.45, list: 3, parts: true, headShrink: true },
                   { title: 'breakout', w: 1.15, list: 3, words: 'on', headShrink: true },
                   { title: 'at the breakout', w: 1.2, list: 3, parts: true, headShrink: true }],
            rows,
        };
    }

    // The table as a block in the widest column that still puts as many
    // across the sheet as COL_W's do (900 on Tabloid, three across) - its
    // five columns of strands and boxes need the room - and wider where its
    // widest output, cable word, strand or box needs more for nothing to be
    // cut, up to the data sheet's DATA_COL_W. The block widens the sheet's
    // columns (minW), the way the Ports table does. null without one.
    _bFiberConnectionsBlock(book, proc, title) {
        const spec = this._bFiberConnections(proc, title);
        if (!spec) return null;
        const need = book && book.measureCtx
            ? this._bColNeeds(book, spec.cols, spec.rows, 12).reduce((a, b) => a + b, 0) : 0;
        const da = book && book.geo && book.geo.da;
        const across = da ? Math.max(1, Math.floor((da.w + COL_GAP) / (COL_W + COL_GAP))) : 1;
        const fit = da ? Math.floor((da.w + COL_GAP) / across - COL_GAP) : COL_W;
        const width = Math.min(DATA_COL_W, Math.max(COL_W, fit, Math.ceil(need) + 2));
        const lines = this._bTableLines(book, { ...spec, width });
        return width > COL_W ? { minW: width, lines } : { lines };
    }

    // ---- the show's pull list (4.last) --------------------------------------

    _bTotalsGroup(book) {
        const blocks = [{ lines: this._bPullLines(book, 'Pull list', book.list.totals || []) }];
        const notes = (book.list.unmodelled || []).map(t => ({ cells: [t] }));
        if (notes.length) {
            blocks.push({ lines: this._bTableLines(book, { title: 'Notes', cols: [{ title: '', w: 1 }], rows: notes }) });
        }
        return { kind: 'totals', name: 'All positions', blocks };
    }
}

for (const k of Object.getOwnPropertyNames(_Binder.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Binder.prototype, k));
    }
}

// The set's vocabulary the wiring mixin (app-binder-wiring.js) draws with -
// the same inks, type sizes and fill rules - so its sheet reads as the
// rest of the set does.
export const BINDER_STYLE = { INK, RULE, FAINT, MUTED, SZ, FILL_CAP, MAP_ZOOM_CAP, MAP_MIN_FRAC, BUBBLE_H, FONT };
