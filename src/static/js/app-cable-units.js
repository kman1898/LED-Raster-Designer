// app-cable-units: the unit every cable length of a show is typed and
// printed in - feet or meters. Owner rulings, 2026-10-16:
//
//   * BOTH. Preferences > Pull sheet & cables holds "Cable lengths: Feet /
//     Meters": the unit a NEW show starts in. Each show keeps its own
//     (project.cableUnit, 'ft' or 'm'), saved with the project and changed
//     in the export dialog (Pull Sheet and Binder sections, one setting).
//     A show with none stored - every file saved before the setting - is
//     feet.
//   * EVERY length follows the show's unit: multi home runs, circuit
//     cables, data home runs, extensions and snakes, the per-screen V / H
//     jumpers, long jumpers, box fiber, processor-to-box cables, the box
//     cable sheet, the cable tags on the maps, the binder, the pull sheet.
//   * STORAGE: a length is stored as the number typed, in the show's unit.
//     A typed cable is a stock cable - 25 ft is not 7.62 m of anything - so
//     changing a show's unit converts nothing: every typed length keeps its
//     number and reads in the new unit (the change asks first when the show
//     holds any, and says so). Only what the app MEASURES follows the unit:
//     the long jumpers, measured again from the panels.
//   * LABELS: feet keep the app's own ' ("Data Jump 2'", "100'"); meters
//     print the figure, a space and m ("Data Jump 2 m", "30 m"). Fields say
//     "ft" or "m" beside them.
//   * ROUNDING is the long jumper's alone (app-jumpers.js): center to
//     center along the panels, plus slack - 1 ft, or 0.3 m (the foot to the
//     nearest tenth of a meter) - rounded UP to the stock ladder, past its
//     top up to the next 5 of the unit. The two ladders are Preferences:
//     3, 6, 10, 15, 25 ft and 1, 2, 3, 5, 10 m as shipped.
//   * The Preferences' cable LENGTHS (the jumpers, the snake home run, the
//     loose port cable, the power cable) are kept per unit, a feet set and
//     a meters set; a show takes the set in its own unit. The meters set
//     ships as the feet figures to the nearest whole meter (6' -> 2 m,
//     10' -> 3 m, 100' -> 30 m).
import { LEDRasterApp } from './app-core.js';

export const CABLE_UNITS = ['ft', 'm'];
// Millimeters in one of each unit: what a measured distance divides by.
const MM_PER_UNIT = { ft: 304.8, m: 1000 };
// The long jumper's slack and stock ladders as shipped.
const JUMPER_SLACK = { ft: 1, m: 0.3 };
export const JUMPER_STOCK_SHIPPED = { ft: [3, 6, 10, 15, 25], m: [1, 2, 3, 5, 10] };
// Past the ladder's top a long jumper rounds up to the next multiple of
// this, in the show's unit (26 ft -> 30 ft; 11 m -> 15 m).
const JUMPER_PAST_STOCK_STEP = 5;
// The preference key of each cable length, per unit: the feet key is the
// one the app has always had; the meters twin sits beside it.
export const CABLE_PREF_KEYS = {
    dataJumpLength: { ft: 'dataJumpLength', m: 'dataJumpLengthM' },
    dataJumpLengthH: { ft: 'dataJumpLengthH', m: 'dataJumpLengthHM' },
    powerJumpLength: { ft: 'powerJumpLength', m: 'powerJumpLengthM' },
    powerJumpLengthH: { ft: 'powerJumpLengthH', m: 'powerJumpLengthHM' },
    snakeHomeRun: { ft: 'snakeHomeRunFt', m: 'snakeHomeRunM' },
    loosePortCable: { ft: 'loosePortCableFt', m: 'loosePortCableM' },
    powerCable: { ft: 'powerCableFt', m: 'powerCableM' },
    jumperStock: { ft: 'jumperStockFt', m: 'jumperStockM' },
};
// What may follow a typed length's number, per unit: nothing, or the
// show's own unit ("30m", "30 m"; "100ft", "100 ft", "100'"). The other
// unit's suffix is not on the list: "30m" in a feet show is unreadable -
// no length, flagged as one - never 30 ft.
const LENGTH_SUFFIXES = {
    ft: new Set(['', "'", '\u2019', 'ft', 'ft.', 'feet', 'foot']),
    m: new Set(['', 'm', 'meter', 'meters', 'metre', 'metres']),
};
// The project keys that hold a typed length somewhere in the show - what
// a unit change counts before it asks. `ft` / `ext` / `homeRun` /
// `fiberFt` are the hardware and cable records' own; the four jumper
// fields and the multi home runs are the screens'. A jumper field is only
// there when somebody typed it: a screen that never had one reads the
// Preferences (app-jumpers.js screenJumperLengths).
const TYPED_LENGTH_KEYS = new Set(['ft', 'ext', 'homeRun', 'fiberFt',
    'dataJumpV', 'dataJumpH', 'powerJumpV', 'powerJumpH']);

class _CableUnits {

    // ---- the unit --------------------------------------------------------

    // 'ft' or 'm': anything that is not 'm' is feet (a show saved before
    // the setting, a stray value).
    normalizeCableUnit(unit) {
        return unit === 'm' ? 'm' : 'ft';
    }

    // The show's unit.
    cableUnit() {
        return this.normalizeCableUnit(this.project && this.project.cableUnit);
    }

    // The unit a new show starts in (the Preferences setting).
    preferredCableUnit() {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        return this.normalizeCableUnit(prefs.cableUnit);
    }

    // "ft" / "m" - what a field says beside it.
    cableUnitAbbr(unit) {
        return this.normalizeCableUnit(unit === undefined ? this.cableUnit() : unit);
    }

    // "feet" / "meters" - what a sentence says.
    cableUnitWord(unit) {
        return this.cableUnitAbbr(unit) === 'm' ? 'meters' : 'feet';
    }

    // A figure as text: whole numbers bare, else to one decimal in feet
    // and two in meters (0.3 m of slack, a typed 7.62 m) - never rounded
    // past what a person typed to the tenth or the centimeter.
    cableFigure(n, unit) {
        const v = Number(n);
        if (!Number.isFinite(v)) return '';
        if (Number.isInteger(v)) return String(v);
        return String(+v.toFixed(this.cableUnitAbbr(unit) === 'm' ? 2 : 1));
    }

    // THE one reading of a typed length, everywhere a length is read: a
    // positive number in the show's unit (or `unit`), or null for no
    // length. A number is itself; text is a number alone or followed by
    // the unit's own suffix (LENGTH_SUFFIXES), any case, a space or none
    // between. Blank, zero, negative, anything else - and the OTHER unit's
    // suffix - is null. Relabelling by number on a unit change is
    // untouched: a length is still stored as the number typed.
    parseCableLength(value, unit) {
        if (value === null || value === undefined || typeof value === 'boolean') return null;
        if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? value : null;
        const m = /^(\d+(?:\.\d*)?|\.\d+)\s*(.*)$/.exec(String(value).trim());
        if (!m) return null;
        const suffix = m[2].trim().toLowerCase();
        if (!LENGTH_SUFFIXES[this.cableUnitAbbr(unit)].has(suffix)) return null;
        const n = Number(m[1]);
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    // A length as every paper prints it: "100'" in feet, "30 m" in
    // meters, "" for a length nobody typed (blank, zero, not a length).
    cableLengthText(n, unit) {
        const v = this.parseCableLength(n, unit);
        if (v === null) return '';
        const u = this.cableUnitAbbr(unit);
        return u === 'm' ? `${this.cableFigure(v, u)} m` : `${this.cableFigure(v, u)}'`;
    }

    // A length as a sentence says it: "10 ft" / "3 m".
    cableLengthWords(n, unit) {
        const u = this.cableUnitAbbr(unit);
        return `${this.cableFigure(n, u)} ${u}`;
    }

    // Millimeters in one unit of the show's (a measured distance divides
    // by it).
    mmPerCableUnit(unit) {
        return MM_PER_UNIT[this.cableUnitAbbr(unit)];
    }

    // ---- the preferences, per unit ---------------------------------------

    // The preference key of one cable length in a unit (the show's by
    // default): cablePrefKey('powerCable') is 'powerCableFt' or
    // 'powerCableM'.
    cablePrefKey(name, unit) {
        const keys = CABLE_PREF_KEYS[name];
        if (!keys) return name;
        return keys[this.cableUnitAbbr(unit)];
    }

    // That preference's value (getPreferences fills the shipped one, and
    // a horizontal jumper a record never held reads its vertical).
    cablePref(name, unit) {
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        return prefs[this.cablePrefKey(name, unit)];
    }

    // ---- the long jumper's ladder and slack ------------------------------

    jumperSlack(unit) {
        return JUMPER_SLACK[this.cableUnitAbbr(unit)];
    }

    jumperPastStockStep() {
        return JUMPER_PAST_STOCK_STEP;
    }

    // A ladder as stored: positive numbers, ascending, once each - null
    // when nothing in it is a length (the caller keeps what it had).
    normalizeJumperStock(list) {
        if (!Array.isArray(list)) return null;
        const out = [...new Set(list.map(Number)
            .filter(n => Number.isFinite(n) && n > 0)
            .map(n => Math.round(n * 1e6) / 1e6))].sort((a, b) => a - b);
        return out.length ? out : null;
    }

    // "3, 6, 10, 15, 25" back to a ladder (commas, spaces or semicolons
    // between); null when nothing in it is a length.
    parseJumperStockText(text) {
        const parts = String(text == null ? '' : text).split(/[\s,;]+/).filter(Boolean);
        if (!parts.length) return null;
        if (parts.some(p => !Number.isFinite(Number(p)) || Number(p) <= 0)) return null;
        return this.normalizeJumperStock(parts.map(Number));
    }

    // A ladder as its field shows it: every number exactly as stored, in
    // the ladder's own unit. Never cableFigure - that rounds to the open
    // show's unit, so a feet show would turn a 0.25 m rung into 0.3 and a
    // Preferences save would write the rounded ladder back.
    jumperStockText(list) {
        return (list || []).map(n => String(Number(n))).join(', ');
    }

    // The ladder a long jumper rounds up to in a unit (the show's by
    // default): the preference, else the shipped one.
    jumperStockLadder(unit) {
        const u = this.cableUnitAbbr(unit);
        return this.normalizeJumperStock(this.cablePref('jumperStock', u))
            || JUMPER_STOCK_SHIPPED[u].slice();
    }

    // ---- the show's setting ------------------------------------------------

    // How many typed lengths the show holds - what a unit change says
    // before it relabels them. A walk over the project for the record keys
    // that hold one (readable lengths only, parseCableLength), plus every
    // multi home run.
    typedCableLengthCount() {
        let n = 0;
        const positive = (v) => this.parseCableLength(v) !== null;
        const walk = (node, depth) => {
            if (!node || typeof node !== 'object' || depth > 12) return;
            if (Array.isArray(node)) { node.forEach(v => walk(v, depth + 1)); return; }
            for (const [k, v] of Object.entries(node)) {
                if (k === 'powerSocaLengths' && v && typeof v === 'object') {
                    n += Object.values(v).filter(positive).length;
                } else if (TYPED_LENGTH_KEYS.has(k) && (typeof v === 'number' || typeof v === 'string')) {
                    if (positive(v)) n += 1;
                } else if (v && typeof v === 'object') {
                    walk(v, depth + 1);
                }
            }
        };
        const p = this.project || {};
        walk({ layers: p.layers, processors: p.processors, snakes: p.snakes,
               fiberCables: p.fiberCables, distros: p.distros }, 0);
        return n;
    }

    // What the change asks when the show already holds lengths.
    cableUnitChangeQuestion(unit, count) {
        const from = this.cableUnit();
        const to = this.cableUnitAbbr(unit);
        const lengths = count === 1 ? '1 cable length' : `${count} cable lengths`;
        return `Change this show's cable lengths to ${this.cableUnitWord(to)}?\n\n`
            + `The ${lengths} already typed keep their numbers: `
            + `25 ${from} becomes 25 ${to}. Check them after. `
            + 'Long jumpers are measured again.';
    }

    // Set the show's unit: one history entry, one project POST, every
    // label and paper redrawn. A show that holds typed lengths asks first
    // (`ask` false skips it - a caller that already asked). Returns true
    // when the unit changed.
    setCableUnit(unit, ask = true) {
        if (!this.project) return false;
        const to = this.normalizeCableUnit(unit);
        if (to === this.cableUnit() && this.project.cableUnit === to) return false;
        if (to === this.cableUnit()) {
            // Same unit, only now written down (a feet show with none
            // stored): nothing to ask, nothing to redraw.
            this.project.cableUnit = to;
            this._persistCableUnit();
            return false;
        }
        const count = this.typedCableLengthCount();
        if (ask && count > 0 && !window.confirm(this.cableUnitChangeQuestion(to, count))) {
            this.syncCableUnitControls();
            return false;
        }
        const from = this.cableUnit();
        this.project.cableUnit = to;
        // The pull sheet's edits are keyed by the row's printed length
        // ("Data Jump|2'"): the numbers keep, so the keys are relabelled
        // with them and an override stays on its row.
        const relabelled = this._relabelPullSheetEdits(from, to);
        // Project-level state, the distros' doctrine: snapshot after the
        // mutation, then persist (save_project merges top-level keys).
        if (typeof this.saveState === 'function') this.saveState('Set Cable Lengths Unit');
        this._persistCableUnit(relabelled);
        this.refreshCableUnitViews();
        return true;
    }

    // The NUMBER behind a length printed in one unit ("2'" / "2 m"), or
    // null for anything else (EA, a free row's own words). The print can
    // be short of the number - feet print one decimal, so 7.62 reads
    // "7.6'" - and the first of these that prints back as `text` wins:
    // `stored` (the number an edit carries from an earlier relabel), then
    // the show's own numbers that print as `text` (`candidates`, read off
    // the pull sheet's engine), then the printed figure itself.
    _lengthNumberOf(text, from, stored, candidates) {
        const t = String(text == null ? '' : text);
        const m = from === 'm' ? /^(\d+(?:\.\d+)?) m$/.exec(t) : /^(\d+(?:\.\d+)?)'$/.exec(t);
        if (!m) return null;
        const printed = Number(m[1]);
        const s = Number(stored);
        if (stored != null && Number.isFinite(s) && this.cableLengthText(s, from) === t) return s;
        const hits = [...new Set((candidates || []).filter(n => this.cableLengthText(n, from) === t))];
        if (hits.length && !hits.includes(printed)) return hits[0];
        return printed;
    }

    // Every pull-sheet edit's row key (`type|length[|split]`) and every
    // added row's length, relabelled from one unit to the other BY NUMBER:
    // each carries its number (`lengthNum`) so a round trip (m -> ft -> m)
    // lands on the key it started from, and an engine row's key follows
    // the number the engine prints. Returns true when something changed.
    _relabelPullSheetEdits(from, to) {
        const store = this.project && this.project.pullSheetEdits;
        if (!store || !store.positions || from === to) return false;
        // The numbers the engine prints, in the new unit (the show's now).
        let candidates = [];
        if (typeof this.pullSheetLengthNumbers === 'function') {
            try { candidates = this.pullSheetLengthNumbers(); } catch (_) { candidates = []; }
        }
        const relabel = (holder, text, useEngine) => {
            const n = this._lengthNumberOf(text, from, holder.lengthNum, useEngine ? candidates : null);
            if (n === null) return text;
            holder.lengthNum = n;
            return this.cableLengthText(n, to);
        };
        let changed = false;
        for (const pos of Object.values(store.positions)) {
            if (!pos || typeof pos !== 'object') continue;
            for (const r of Array.isArray(pos.rows) ? pos.rows : []) {
                if (!r || typeof r.key !== 'string') continue;
                const parts = r.key.split('|');
                if (parts.length < 2) continue;
                const next = relabel(r, parts[1], true);
                if (next !== parts[1]) { parts[1] = next; r.key = parts.join('|'); changed = true; }
            }
            for (const a of Array.isArray(pos.added) ? pos.added : []) {
                if (!a || a.length == null) continue;
                const next = relabel(a, a.length, false);
                if (next !== a.length) { a.length = next; changed = true; }
            }
        }
        return changed;
    }

    // On the pull sheet's one POST queue (app-pull-list.js
    // _postPullSheetState): the relabelled edits and an edit made a
    // moment later must land in the order they were made.
    _persistCableUnit(withEdits = false) {
        return this._postPullSheetState(withEdits ? ['cableUnit', 'pullSheetEdits'] : ['cableUnit']);
    }

    // Everything that prints a length, redrawn after the unit changed:
    // the static labels, the sidebars' jumper rows, the tray and its cable
    // sheets, the maps, the export preview.
    refreshCableUnitViews() {
        this.syncCableUnitControls();
        if (typeof this.getSelectedLayers === 'function' && typeof this.syncJumperControls === 'function') {
            try { this.syncJumperControls(this.getSelectedLayers()); } catch (_) { /* no selection yet */ }
        }
        if (typeof this.renderHardwareDock === 'function') {
            try { this.renderHardwareDock(); } catch (_) { /* tray not built yet */ }
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
        if (typeof this.updateExportPreview === 'function') {
            const modal = document.getElementById('export-modal');
            if (modal && modal.style.display !== 'none') this.updateExportPreview();
        }
    }

    // The page's own unit words, from the show's unit: every element
    // marked data-cable-unit says "ft" / "m"; one marked
    // data-cable-unit-tip / data-cable-unit-aria / data-cable-unit-title
    // takes its template with {unit} (ft / m), {units} (feet / meters),
    // {slack} ("1 ft" / "0.3 m") and {len:FT:M} (an example length, "50'"
    // in feet, "15 m" in meters) filled in; the show's own selects show
    // the unit.
    syncCableUnitControls() {
        if (typeof document === 'undefined') return;
        const unit = this.cableUnit();
        const fill = (tpl) => String(tpl)
            .replace(/\{unit\}/g, this.cableUnitAbbr(unit))
            .replace(/\{units\}/g, this.cableUnitWord(unit))
            .replace(/\{slack\}/g, this.cableLengthWords(this.jumperSlack(unit), unit))
            .replace(/\{len:([\d.]+):([\d.]+)\}/g, (_, ft, m) => this.cableLengthText(unit === 'm' ? m : ft, unit));
        document.querySelectorAll('[data-cable-unit]').forEach(el => {
            el.textContent = this.cableUnitAbbr(unit);
        });
        document.querySelectorAll('[data-cable-unit-tip]').forEach(el => {
            el.setAttribute('data-tooltip', fill(el.getAttribute('data-cable-unit-tip')));
        });
        document.querySelectorAll('[data-cable-unit-aria]').forEach(el => {
            el.setAttribute('aria-label', fill(el.getAttribute('data-cable-unit-aria')));
        });
        document.querySelectorAll('[data-cable-unit-title]').forEach(el => {
            el.setAttribute('title', fill(el.getAttribute('data-cable-unit-title')));
        });
        document.querySelectorAll('select.cable-unit-select').forEach(sel => {
            if (document.activeElement !== sel) sel.value = unit;
        });
    }

    // Wired once (from initPullSheetControls): the export dialog's two
    // "Cable lengths" selects - the Pull Sheet section's and the Binder
    // section's - commit the one show setting.
    initCableUnitControls() {
        if (this._cableUnitControlsWired) return;
        this._cableUnitControlsWired = true;
        document.querySelectorAll('select.cable-unit-select').forEach(sel => {
            sel.addEventListener('change', () => {
                this.setCableUnit(sel.value);
                this.syncCableUnitControls();
                // The sync skips a focused select, and this one has focus:
                // a change the user cancelled must not leave it showing the
                // unit they backed out of.
                sel.value = this.cableUnit();
            });
        });
        this.syncCableUnitControls();
    }
}

for (const k of Object.getOwnPropertyNames(_CableUnits.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_CableUnits.prototype, k));
    }
}
