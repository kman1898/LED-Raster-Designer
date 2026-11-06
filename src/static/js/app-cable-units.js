// app-cable-units: the unit every cable length of a show is typed and
// printed in - feet or meters. Owner rulings, 2026-10-16:
//
//   * BOTH. Preferences > Pull sheet & cables holds "Cable lengths: Feet /
//     Meters": the unit a NEW show starts in. Each show keeps its own
//     (project.cableUnit, 'ft' or 'm'), saved with the project and changed
//     in the export dialog (Pull Sheet and Binder sections, one setting).
//     A show with none stored - every file saved before the setting - is
//     feet.
//   * 2026-10-17: the open show's unit can also be switched from the Data
//     and Power sidebars (an ft / m select beside the jumper fields), and
//     a Preferences save that changes the unit offers it to the open show
//     (offerPreferredCableUnitToShow). It is a project setting: a locked
//     screen does not hold it.
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
//
// CABLE STOCK (owner rulings, 2026-10-20: "if i have 25, 50 and 100 but on
// cable length on the show file i chose 125 then it will need to change to
// 100+25 on the pull sheet or anywhere it is written out"):
//
//   * The lengths a show has on hand live IN THE SHOW (project.cableStock),
//     saved, loaded and undone with it. A show without one - every file
//     saved before the setting - writes every length as typed, as before.
//     Preferences keep named presets of it (app-cable-stock.js).
//   * The kinds that take it: 'multi' (a multi's home run, distro to
//     screen: powerSocaLengths), 'data' (a snake's home run, a loose port
//     cable, a snaked port's extension) and 'circuit' (a circuit's own
//     cable, powerCircuitCables). Since 2026-10-21 (owner: each cable kind
//     gets its own list) also 'l2130' and 'harting' (an L21-30 or Harting
//     box's home run, which was a multi's), 'direct' (a direct output's
//     one cable - CEE, Schuko, Edison, L5-20, TRUE1, powerCON - which was
//     a circuit's) and 'feeder' (a distro's feeder, app-services.js).
//     The copper links and the jumpers do not: the jumpers keep their own
//     ladder above.
//   * FIBER (owner, 2026-11-05: "we dont need two differnt fiber lenght
//     types. MM and SM can be one box in preferences"): ONE list, 'fiber',
//     a TAC, MTP or opticalCON of either mode pulled from it
//     (app-fiber.js fiberStockKind). The mode stays on every cable, row,
//     label and refusal: only the lengths are shared. It is ALWAYS its own
//     list, whatever perKind says - a fiber is never pulled from a copper
//     list, and a show saved before it has none, so its fiber is written
//     as typed, as it always was. A cable whose boxes state no mode is
//     written as typed too. A show or preset saved with the list per mode
//     1.6.0's betas kept ('fiberSingle', 'fiberMulti') reads as one list
//     holding every length of both (normalizeCableStock; the server folds
//     the keys away, routes_cable_stock.py fold_fiber_lists).
//   * ONE list for all of them, or a list PER KIND (cableStock.perKind),
//     each kept in feet and in meters like the preferences: a show reads
//     the list in its own unit. An empty list is no breakdown for that
//     kind. A show or preset saved before a kind had its own list reads
//     that kind from the list it was pulled from then
//     (CABLE_STOCK_FALLBACK): its runs are written as they always were.
//   * A length the stock cannot make exactly takes the LEAST EXTRA
//     length, then the FEWEST pieces (breakCableLength): with 25, 50, 100,
//     125 is 100+25, 60 is 50+25, 130 is 100+50.
//   * The typed length stays as typed; it is WRITTEN as its pieces,
//     "100'+25'" ("30 m+10 m"), by cableStockText - the one formatter every
//     tag, sheet and paper reads - and the pull sheet counts the pieces.
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

// The cable kinds the show's stock covers, and the key of the one shared
// list in each unit.
export const CABLE_STOCK_KINDS = ['multi', 'data', 'circuit', 'l2130', 'harting', 'direct', 'feeder'];
export const CABLE_STOCK_ALL = 'all';
// The fiber list: both modes', never shared with copper (above).
export const CABLE_STOCK_FIBER = 'fiber';
// The list per mode a stock may have been saved with: read into the one.
const CABLE_STOCK_FIBER_RETIRED = ['fiberSingle', 'fiberMulti'];
// A kind's list where a saved per-kind stock has none at all (saved
// before the kind had one): the list its cables were pulled from then.
export const CABLE_STOCK_FALLBACK = { l2130: 'multi', harting: 'multi', direct: 'circuit' };
// The breakdown works on a grid of whole steps; past this many steps a
// length is written as typed rather than searched (a figure no show cable
// comes near).
const CABLE_STOCK_MAX_STEPS = 1000000;

// The pieces that make `length` from `stock` (lengths, unlimited of
// each): the least extra length first, then the fewest pieces, then the
// longer pieces. Returned longest first; null when there is nothing to
// break (no length, no stock, or a length past the grid).
export function breakCableLength(length, stock) {
    const n = Number(length);
    if (!Number.isFinite(n) || n <= 0) return null;
    const sizes = [...new Set((Array.isArray(stock) ? stock : []).map(Number)
        .filter(v => Number.isFinite(v) && v > 0))].sort((a, b) => b - a);
    if (!sizes.length) return null;
    // Whole numbers: the stock to the 1/10000 at most (a typed 7.62 m).
    let scale = 1;
    while (scale < 10000 && sizes.some(v => Math.abs(v * scale - Math.round(v * scale)) > 1e-6)) {
        scale *= 10;
    }
    const whole = sizes.map(v => Math.round(v * scale));
    const gcd = (a, b) => (b ? gcd(b, a % b) : a);
    const step = whole.reduce((g, v) => gcd(g, v), 0);
    const units = whole.map(v => v / step);
    // Every sum is a whole number of steps, so the target rounds up to one.
    const target = Math.ceil(n * scale / step - 1e-6);
    // An answer past target + the longest piece always has a piece to
    // spare, so the search stops short of it.
    const top = target + units[0];
    if (top > CABLE_STOCK_MAX_STEPS) return null;
    const count = new Array(top).fill(Infinity);
    count[0] = 0;
    for (let s = 1; s < top; s++) {
        for (const u of units) {
            if (u <= s && count[s - u] + 1 < count[s]) count[s] = count[s - u] + 1;
        }
    }
    let sum = -1;
    for (let s = Math.max(target, 1); s < top; s++) {
        if (count[s] !== Infinity) { sum = s; break; }
    }
    if (sum < 0) return null;
    const pieces = [];
    while (sum > 0) {
        const i = units.findIndex(u => u <= sum && count[sum - u] === count[sum] - 1);
        pieces.push(sizes[i]);
        sum -= units[i];
    }
    return pieces.sort((a, b) => b - a);
}

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
    // No length (null, undefined, blank) prints nothing: Number(null) is
    // 0, and a missing length used to print "0". A positive length too
    // small for those decimals takes as many more as it needs to show
    // (0.04 ft -> "0.04"), so a real length never prints as 0.
    cableFigure(n, unit) {
        if (n === null || n === undefined || typeof n === 'boolean'
            || (typeof n === 'string' && !n.trim())) return '';
        const v = Number(n);
        if (!Number.isFinite(v)) return '';
        if (Number.isInteger(v)) return String(v);
        for (let d = this.cableUnitAbbr(unit) === 'm' ? 2 : 1; d <= 6; d++) {
            const r = +v.toFixed(d);
            if (r !== 0) return String(r);
        }
        return String(v);
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

    // A length TYPED INTO A FIELD, read for storing: { n, from } - `n` the
    // length in the show's unit (or `unit`), null for none; `from` the
    // other unit when the text carried that unit's suffix and was
    // converted ("30m" in a feet show is 98.4 ft, to the figure's own
    // decimals), else null. Blank is { n: null, bad: false }; text that
    // is no length in either unit is { n: null, bad: true }, so a field
    // can refuse it rather than clear what was there.
    parseTypedCableLength(value, unit) {
        const u = this.cableUnitAbbr(unit);
        // a zero is no length, as it always read
        const blank = value === null || value === undefined
            || (typeof value === 'number' && value === 0)
            || (typeof value === 'string' && /^0*\.?0*$/.test(value.trim()));
        if (blank) return { n: null, from: null, bad: false };
        const own = this.parseCableLength(value, u);
        if (own !== null) return { n: own, from: null, bad: false };
        const other = u === 'm' ? 'ft' : 'm';
        const there = typeof value === 'string' && /[a-z'’]\s*\.?\s*$/i.test(value.trim())
            ? this.parseCableLength(value, other) : null;
        if (there === null) return { n: null, from: null, bad: true };
        const n = Number(this.cableFigure(there * MM_PER_UNIT[other] / MM_PER_UNIT[u], u));
        return n > 0 ? { n, from: other, bad: false } : { n: null, from: null, bad: true };
    }

    // A length TYPED INTO ANY FIELD, read and said the one way every
    // length field says it (2026-10-22, the feeder field's rule for every
    // typed length: a multi's home run, a direct output's cable, a circuit
    // cable, a data port, a snake, a copper or fiber run): "30m" in a feet
    // show is stored as 98.4 and said; text that is no length in either
    // unit is refused, said, and the length that was there stays. `noun`
    // names what the length is of, as the refusal says it ("Type the
    // feed's length ..."). Returns { ok, n }: `ok` false for a refusal,
    // `n` the length to store in the show's unit (null for none).
    readTypedLength(value, noun = 'cable') {
        const read = this.parseTypedCableLength(value);
        const text = String(value == null ? '' : value).trim();
        if (read.bad) {
            this._sayTypedLength(`"${text}" is not a length. Type the ${noun}'s length in `
                + `${this.cableUnitWord()}, like ${this.cableUnit() === 'm' ? '30' : '100'}.`);
            return { ok: false, n: null };
        }
        if (read.from) {
            this._sayTypedLength(`${text} is ${this.cableLengthWords(read.n)} `
                + `in this ${this.cableUnitWord()} show.`);
        }
        return { ok: true, n: read.n };
    }

    // Said where the user is looking - a toast and the status bar - and
    // once: a length written through to every screen sharing a multi is
    // said for the one field that was typed in. The tray is redrawn a
    // macrotask later, so the field shows what is stored now: the length
    // that stayed, or the converted figure.
    _sayTypedLength(text) {
        const now = Date.now();
        const last = this._typedLengthSaid;
        if (!(last && last.text === text && now - last.at < 500)) {
            this._typedLengthSaid = { text, at: now };
            if (typeof this._toast === 'function') this._toast(text, true, 4000);
            if (typeof this._dockSay === 'function') this._dockSay(text);
        }
        if (typeof this.renderHardwareDock === 'function') {
            setTimeout(() => this.renderHardwareDock(), 0);
        }
    }

    // A length as every paper prints it: "100'" in feet, "30 m" in
    // meters, "" for a length nobody typed (blank, zero, not a length).
    cableLengthText(n, unit) {
        const v = this.parseCableLength(n, unit);
        if (v === null) return '';
        const u = this.cableUnitAbbr(unit);
        return u === 'm' ? `${this.cableFigure(v, u)} m` : `${this.cableFigure(v, u)}'`;
    }

    // A length as a sentence says it: "10 ft" / "3 m"; "" for no length.
    cableLengthWords(n, unit) {
        const u = this.cableUnitAbbr(unit);
        const figure = this.cableFigure(n, u);
        return figure ? `${figure} ${u}` : '';
    }

    // ---- the show's cable stock ------------------------------------------

    // A stock as stored: { perKind, ft: { all, multi, data, circuit,
    // l2130, harting, direct, feeder, fiber }, m: { ... } }, every list
    // positive lengths, ascending, once each (empty where nothing in it is
    // a length; a kind with no list at all reads its CABLE_STOCK_FALLBACK;
    // the fiber list holds every length of the retired lists per mode).
    // null for anything that is not a stock at all - a show without one.
    normalizeCableStock(stock) {
        if (!stock || typeof stock !== 'object' || Array.isArray(stock)) return null;
        const out = { perKind: stock.perKind === true };
        for (const u of CABLE_UNITS) {
            const lists = stock[u] && typeof stock[u] === 'object' ? stock[u] : {};
            out[u] = {};
            for (const k of [CABLE_STOCK_ALL, ...CABLE_STOCK_KINDS]) {
                const from = lists[k] === undefined && CABLE_STOCK_FALLBACK[k]
                    ? lists[CABLE_STOCK_FALLBACK[k]] : lists[k];
                out[u][k] = this.normalizeJumperStock(from) || [];
            }
            out[u][CABLE_STOCK_FIBER] = this.normalizeJumperStock(
                [CABLE_STOCK_FIBER, ...CABLE_STOCK_FIBER_RETIRED]
                    .flatMap(k => (Array.isArray(lists[k]) ? lists[k] : []))) || [];
        }
        return out;
    }

    // The show's stock, cleaned; null when it has none.
    cableStock() {
        return this.normalizeCableStock(this.project && this.project.cableStock);
    }

    // The lengths one kind of cable comes in, in a unit (the show's by
    // default): the shared list, or the kind's own when the show keeps a
    // list per kind. The 'fiber' kind always reads its own list. Empty
    // for no stock, an empty list, or a cable the stock does not cover
    // (no kind: a jumper, a fiber of no stated mode).
    cableStockList(kind, unit) {
        const fiber = kind === CABLE_STOCK_FIBER;
        if (!fiber && !CABLE_STOCK_KINDS.includes(kind)) return [];
        const stock = this.cableStock();
        if (!stock) return [];
        return stock[this.cableUnitAbbr(unit)][fiber || stock.perKind ? kind : CABLE_STOCK_ALL].slice();
    }

    // The stock pieces one typed length is pulled as, longest first
    // (breakCableLength), or null where the length is written as typed.
    cableStockPieces(n, kind, unit) {
        const v = this.parseCableLength(n, unit);
        if (v === null) return null;
        return breakCableLength(v, this.cableStockList(kind, unit));
    }

    // THE one way a covered cable's length is written out, everywhere:
    // its stock pieces joined by + ("100'+25'", "30 m+10 m"), else the
    // length as typed (cableLengthText). Map tags, the tray's chips, the
    // pull sheet, the binder and the wiring sheets all come through here,
    // so they cannot disagree.
    cableStockText(n, kind, unit) {
        const pieces = this.cableStockPieces(n, kind, unit);
        if (!pieces) return this.cableLengthText(n, unit);
        return pieces.map(p => this.cableLengthText(p, unit)).join('+');
    }

    // What a length field's tooltip adds when the stock changes how the
    // length is written: " Pulled as 100'+25' from this show's cable
    // stock." - '' when it is written as typed.
    cableStockHint(n, kind, unit) {
        const text = this.cableStockText(n, kind, unit);
        if (!text || text === this.cableLengthText(n, unit)) return '';
        return ` Pulled as ${text} from this show's cable stock.`;
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
        const to = this.cableUnitAbbr(unit);
        return `Change this show's cable lengths to ${this.cableUnitWord(to)}?\n\n`
            + this._typedCableLengthsNote(to, count);
    }

    // What a switch to `unit` does to the lengths already typed.
    _typedCableLengthsNote(unit, count) {
        const from = this.cableUnit();
        const to = this.cableUnitAbbr(unit);
        const lengths = count === 1 ? '1 cable length' : `${count} cable lengths`;
        return `The ${lengths} already typed keep their numbers: `
            + `25 ${from} becomes 25 ${to}. Check them after. `
            + 'Long jumpers are measured again.';
    }

    // What a Preferences save asks when its new unit is not the open
    // show's: one question, the typed lengths' note folded in.
    cableUnitPreferenceQuestion(unit, count) {
        const to = this.cableUnitAbbr(unit);
        const ask = `Also switch the open show to ${this.cableUnitWord(to)}?`;
        return count > 0 ? `${ask}\n\n${this._typedCableLengthsNote(to, count)}` : ask;
    }

    // Owner ruling, 2026-10-17: a Preferences save that changed the unit
    // a new show starts in (`previous` was the stored one) offers the
    // open show the same unit. Nothing is asked when the preference did
    // not change or the show already reads it (a pristine startup show
    // follows the Preferences on its own). Yes switches the show through
    // the export dialog's own path, without asking again; No leaves it.
    // Resolves true when the show's unit changed. The question is the
    // app's own dialog (app-dialogs.js).
    async offerPreferredCableUnitToShow(previous) {
        if (!this.project) return false;
        const to = this.preferredCableUnit();
        if (to === this.normalizeCableUnit(previous) || to === this.cableUnit()) return false;
        const count = this.typedCableLengthCount();
        const yes = await this.appConfirm(this.cableUnitPreferenceQuestion(to, count),
            { id: 'cable-unit-offer-modal', title: 'Cable lengths' });
        if (!yes) return false;
        return this.setCableUnit(to, false);
    }

    // Set the show's unit: one history entry, one project POST, every
    // label and paper redrawn. A show that holds typed lengths asks first
    // (`ask` false skips it - a caller that already asked). Returns true
    // when the unit changed; when it has to ask (the app's own dialog,
    // app-dialogs.js), a Promise of that answer.
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
        if (ask && count > 0) {
            return this.appConfirm(this.cableUnitChangeQuestion(to, count),
                { id: 'cable-unit-change-modal', title: 'Cable lengths' }).then(yes => {
                if (yes) return this._switchCableUnit(to);
                this.syncCableUnitControls();
                return false;
            });
        }
        return this._switchCableUnit(to);
    }

    // setCableUnit's change itself, once nothing is left to ask.
    _switchCableUnit(to) {
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
        // Every unit select follows, focused or not: the sidebar's stays
        // focused after a pick, and a Cmd+Z right after must still land it
        // on the restored unit.
        document.querySelectorAll('select.cable-unit-select').forEach(sel => {
            sel.value = unit;
        });
    }

    // Wired once (from initPullSheetControls): every "Cable lengths"
    // select - the export dialog's two (the Pull Sheet section's and the
    // Binder section's) and the Data and Power sidebars' ft / m beside
    // the jumper fields (2026-10-17) - commits the one show setting.
    initCableUnitControls() {
        if (this._cableUnitControlsWired) return;
        this._cableUnitControlsWired = true;
        document.querySelectorAll('select.cable-unit-select').forEach(sel => {
            sel.addEventListener('change', () => {
                // A change the user cancelled must not leave it showing
                // the unit they backed out of: the sync puts it back.
                this.setCableUnit(sel.value);
                this.syncCableUnitControls();
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
