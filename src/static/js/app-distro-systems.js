// app-distro-systems: what a distro IS electrically (1.5, owner rulings
// 2026-10-16) - its SYSTEM, its INPUT, and the OUTPUT ROWS on its face -
// and the rules that follow from them: which leg each circuit sits on,
// whether it is line-to-neutral or line-to-line, the breaker and connector
// checks, the presets, and the old {voltage, phase} record's migration.
//
// THE RULINGS, in the owner's terms:
//   * Systems in 1.5: 120/208 3φ wye, 120/240 1φ split-phase, 120 1φ,
//     230/400 3φ wye, 230 1φ. The distro picks one. US systems label their
//     legs X/Y/Z, EU systems L1/L2/L3 (display only - the stores stay
//     keyed X/Y/Z). Nothing else (220/380, 240/415, 127/220, Japan).
//   * A face is a list of OUTPUT ROWS, each a connector and a count. Rows
//     mix freely. A MULTI row (Socapex 19-pin, Harting 16E - six circuits
//     each; L21-30 - three 208V circuits each) breaks out at the screen as
//     multis always have; a DIRECT row is one circuit per connector with its
//     own cable from the distro to the screen.
//   * Coupling comes from the system plus the connector: stage pin, Edison,
//     L5-20 and a 120V Socapex (Type U) are line-to-neutral only; L6-20 is
//     line-to-line; True1, powerCON and Socapex on 120/208 can be either, so
//     the row says which; on 230/400 everything single-phase is 230V
//     line-to-neutral.
//   * Legs come from the distro, not the row: multis keep the phasing
//     schemes they always had (plus "whole multi on one leg", offered on EU
//     distros only), and direct outputs rotate X Y Z X Y Z by default.
//   * Breakers by region: US circuits stay at or under 80% of the breaker
//     (NEC 210.20(A), continuous) unless the distro says its breakers are
//     100% rated; UK/EU circuits stay at or under the breaker. Each row
//     carries its breaker, 20 A US / 16 A EU by default. Connectors carry
//     their rating by region (True1 20 A US / 16 A EU, powerCON 20A
//     20 A US / 16 A EU - classic powerCON on an EU distro like True1,
//     2026-10-18 - powerCON XX 16 A EU and US-listed only to 127V, CEE as
//     named, Schuko 16 A), and a row can override its connector's rating
//     (`connectorA`; blank is the default). Stage pin at 208V is refused
//     (ANSI E1.24).
//   * Paired rows: a row marked "paired with" another is the same circuits
//     on a second set of connectors (a UK distro's Socapex sharing the
//     True1 outputs' RCBOs). The circuits count once; a circuit can be
//     patched to either connector, never both.
//   * An old distro with no rows behaves exactly as it always did - it
//     offers every multi type, its boxes come and go with what is on them.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// A screen voltage "is" a system's line-to-neutral or line-to-line figure
// when it is one of that figure's NOMINAL names (owner, 2026-10-16: "you
// cant have 220v on 208 distro right?"): 110, 115 and 120 are 120V - so a
// 110V circuit still rides one leg of a 208V distro; 208 is 208V; 220, 230
// and 240 are 230V on an EU system and 240V line-to-line on a 120/240
// split. Anything else matches nothing and is refused, saying what the
// distro gives (a 220V screen on 120/208, a 100V screen anywhere).
const NOMINAL_NAMES = {
    120: [110, 115, 120],
    208: [208],
    230: [220, 230, 240],
    240: [220, 230, 240],
};

export const DISTRO_SYSTEMS = [
    { id: '120/208', name: '120/208V 3φ', supply: '120/208V·3φ', region: 'us',
      vln: 120, vll: 208, legs: ['X', 'Y', 'Z'], voltage: 208, phase: 3 },
    { id: '120/240', name: '120/240V 1φ split-phase', supply: '120/240V·1φ', region: 'us',
      vln: 120, vll: 240, legs: ['X', 'Y'], voltage: 240, phase: 1 },
    { id: '120', name: '120V 1φ', supply: '120V·1φ', region: 'us',
      vln: 120, vll: null, legs: [], voltage: 120, phase: 1 },
    { id: '230/400', name: '230/400V 3φ', supply: '230/400V·3φ', region: 'eu',
      vln: 230, vll: 400, legs: ['X', 'Y', 'Z'], voltage: 400, phase: 3, lnOnly: true },
    { id: '230', name: '230V 1φ', supply: '230V·1φ', region: 'eu',
      vln: 230, vll: null, legs: [], voltage: 230, phase: 1, lnOnly: true },
];

// The connectors a face can carry. `kind` multi breaks out at the screen,
// direct is one circuit with its own cable. `circuits` is per connector.
// `couple`: 'ln' line-to-neutral only, 'll' line-to-line only, 'either'
// where the row says which. `rating` is the connector's amps by region,
// absent where no ruling gives one (a multi's contacts). `cable` is how a
// pull sheet names the run off it.
export const DISTRO_CONNECTORS = [
    { id: 'soca', name: 'Socapex 19-pin', short: 'Socapex', kind: 'multi', circuits: 6,
      regions: ['us', 'eu'], couple: 'either', glyph: 'soca', cable: 'Multi' },
    { id: 'harting', name: 'Harting 16E', short: 'Harting 16E', kind: 'multi', circuits: 6,
      regions: ['eu'], couple: 'ln', glyph: 'harting', cable: 'Harting 16E' },
    { id: 'l2130', name: 'L21-30 (3 × 208V)', short: 'L21-30', kind: 'multi', circuits: 3,
      regions: ['us'], systems: ['120/208'], couple: 'll', feedLegA: 30, glyph: 'l2130',
      cable: 'L21-30' },
    { id: 'true1', name: 'True1', short: 'True1', kind: 'direct', circuits: 1,
      regions: ['us', 'eu'], couple: 'either', rating: { us: 20, eu: 16 }, glyph: 'true1',
      cable: 'True1' },
    { id: 'powercon20', name: 'powerCON 20A', short: 'powerCON 20A', kind: 'direct', circuits: 1,
      regions: ['us', 'eu'], couple: 'either', rating: { us: 20, eu: 16 }, glyph: 'powercon',
      cable: 'powerCON' },
    { id: 'powerconxx', name: 'powerCON XX', short: 'powerCON XX', kind: 'direct', circuits: 1,
      regions: ['us', 'eu'], couple: 'either', rating: { us: 20, eu: 16 }, usMaxV: 127,
      glyph: 'powercon', cable: 'powerCON XX' },
    { id: 'edison', name: 'Edison 5-20', short: 'Edison', kind: 'direct', circuits: 1,
      regions: ['us'], couple: 'ln', rating: { us: 20 }, glyph: 'edison', cable: 'Edison' },
    { id: 'l520', name: 'L5-20', short: 'L5-20', kind: 'direct', circuits: 1,
      regions: ['us'], couple: 'ln', rating: { us: 20 }, glyph: 'twist', cable: 'L5-20' },
    { id: 'l620', name: 'L6-20', short: 'L6-20', kind: 'direct', circuits: 1,
      regions: ['us'], couple: 'll', rating: { us: 20 }, glyph: 'twist', cable: 'L6-20' },
    { id: 'stagepin', name: 'Stage pin 20A', short: 'Stage pin', kind: 'direct', circuits: 1,
      regions: ['us'], couple: 'ln', rating: { us: 20 }, glyph: 'stagepin', cable: 'Stage pin' },
    { id: 'cee16', name: 'CEE 16A blue', short: 'CEE 16A', kind: 'direct', circuits: 1,
      regions: ['eu'], couple: 'ln', rating: { eu: 16 }, glyph: 'cee', cable: 'CEE 16A' },
    { id: 'cee32', name: 'CEE 32A blue', short: 'CEE 32A', kind: 'direct', circuits: 1,
      regions: ['eu'], couple: 'ln', rating: { eu: 32 }, glyph: 'cee', cable: 'CEE 32A' },
    { id: 'schuko', name: 'Schuko', short: 'Schuko', kind: 'direct', circuits: 1,
      regions: ['eu'], couple: 'ln', rating: { eu: 16 }, glyph: 'schuko', cable: 'Schuko' },
];

// What feeds the distro. `ratingA` is the per-leg figure picking it sets;
// the Rating box stays typeable, because a cam connector does not set the
// rating - the distro's main or feeder does (a 600 or 800 A distro takes
// two sets of 400 A cams). `systems` are the services the input can feed:
// the gear's Input list shows only those for the distro's system. CEE red
// is 5-pin 3φ with a neutral, CEE blue is 1φ. Ids are stored on distros
// and presets, so an id never changes.
const US_SYSTEMS = ['120/208', '120/240', '120'];
// The US nominal voltages an old record with no system can carry: one of
// them puts the record on the US continuous rule (distroMainLimit).
const US_NOMINAL_VOLTS = [110, 115, 120, 208, 240, 277, 480];
export const DISTRO_INPUTS = [
    { id: 'cam100', name: 'Cam 100 A', ratingA: 100, systems: US_SYSTEMS },
    { id: 'cam200', name: 'Cam 200 A', ratingA: 200, systems: US_SYSTEMS },
    { id: 'cam400', name: 'Cam 400 A', ratingA: 400, systems: US_SYSTEMS },
    { id: 'cam600', name: 'Cam 600 A', ratingA: 600, systems: US_SYSTEMS },
    { id: 'cam800', name: 'Cam 800 A', ratingA: 800, systems: US_SYSTEMS },
    { id: 'l2130', name: 'L21-30', ratingA: 30, systems: ['120/208'] },
    { id: 'cee16r', name: 'CEE 16 A red', ratingA: 16, systems: ['230/400'] },
    { id: 'cee32r', name: 'CEE 32 A red', ratingA: 32, systems: ['230/400'] },
    { id: 'cee63', name: 'CEE 63 A red', ratingA: 63, systems: ['230/400'] },
    { id: 'cee125r', name: 'CEE 125 A red', ratingA: 125, systems: ['230/400'] },
    { id: 'cee16b', name: 'CEE 16 A blue', ratingA: 16, systems: ['230'] },
    { id: 'cee32b', name: 'CEE 32 A blue', ratingA: 32, systems: ['230'] },
    { id: 'cee63b', name: 'CEE 63 A blue', ratingA: 63, systems: ['230'] },
    { id: 'cee125b', name: 'CEE 125 A blue', ratingA: 125, systems: ['230'] },
    { id: 'powerlock400', name: 'Powerlock 400 A', ratingA: 400, systems: ['230/400', '230'] },
    { id: 'powerlock630', name: 'Powerlock 630 A', ratingA: 630, systems: ['230/400', '230'] },
];

// The breaker a new row starts with, by region.
const DEFAULT_BREAKER = { us: 20, eu: 16 };

// The eleven presets (owner, 2026-10-16). Named plainly - what the face
// is, never who builds it. Rows reference each other by id for pairing.
const row = (id, connector, count, coupling, breakerA, pairedWith = null) =>
    ({ id, connector, count, coupling, breakerA, pairedWith });
export const DISTRO_PRESETS = [
    { id: 'us-200-4soca-3dup', name: '200A 3φ: 4 × Socapex 208V + 3 duplex',
      system: '120/208', input: 'cam200', ratingA: 200,
      rows: [row('r1', 'soca', 4, 'll', 20), row('r2', 'edison', 6, 'ln', 20)] },
    { id: 'us-200-4soca-6dup', name: '200A 3φ: 24 circuits 208V on Socapex + 6 duplex',
      system: '120/208', input: 'cam200', ratingA: 200,
      rows: [row('r1', 'soca', 4, 'll', 20), row('r2', 'edison', 12, 'ln', 20)] },
    { id: 'us-400-8soca120-8soca208', name: '400A 3φ: 8 × Socapex 120V + 8 × Socapex 208V',
      system: '120/208', input: 'cam400', ratingA: 400,
      rows: [row('r1', 'soca', 8, 'ln', 20), row('r2', 'soca', 8, 'll', 20)] },
    { id: 'us-200-6l2130-3dup', name: '200A 3φ: 6 × L21-30 + 3 duplex',
      system: '120/208', input: 'cam200', ratingA: 200,
      rows: [row('r1', 'l2130', 6, 'll', 20), row('r2', 'edison', 6, 'ln', 20)] },
    { id: 'us-l2130-3true1', name: 'L21-30 spider: 3 × True1 208V',
      system: '120/208', input: 'l2130', ratingA: 30,
      rows: [row('r1', 'true1', 3, 'll', 20)] },
    { id: 'us-l2130-3dup', name: 'L21-30 spider: 3 duplex as 6 × 120V',
      system: '120/208', input: 'l2130', ratingA: 30,
      rows: [row('r1', 'edison', 6, 'ln', 20)] },
    { id: 'us-200-6soca120-6dup', name: '200A 3φ: 6 × Socapex 120V + 6 duplex',
      system: '120/208', input: 'cam200', ratingA: 200,
      rows: [row('r1', 'soca', 6, 'ln', 20), row('r2', 'edison', 12, 'ln', 20)] },
    { id: 'eu-63-3soca-true1', name: '63A 3φ: 3 × Socapex, one per phase + 1 True1',
      system: '230/400', input: 'cee63', ratingA: 63, phasing: 'whole-ln',
      rows: [row('r1', 'soca', 3, 'ln', 16), row('r2', 'true1', 1, 'ln', 16)] },
    { id: 'eu-63-18true1', name: '63A 3φ: 18 × True1',
      system: '230/400', input: 'cee63', ratingA: 63,
      rows: [row('r1', 'true1', 18, 'ln', 16)] },
    { id: 'eu-63-2soca-9schuko', name: '63A 3φ: 2 × Socapex or 2 × Harting 16E + 9 Schuko',
      system: '230/400', input: 'cee63', ratingA: 63,
      rows: [row('r1', 'soca', 2, 'ln', 16), row('r2', 'harting', 2, 'ln', 16, 'r1'),
             row('r3', 'schuko', 9, 'ln', 16)] },
    { id: 'eu-400-6soca', name: '400A 3φ: 6 × Socapex, two per phase',
      system: '230/400', input: 'powerlock400', ratingA: 400, phasing: 'whole-ln',
      rows: [row('r1', 'soca', 6, 'ln', 16)] },
];

// The extra phasing scheme EU distros offer (ruling 4, "one Socapex per
// phase"): every circuit of a multi on ONE leg, the multis taking L1, L2,
// L3 in turn along the face.
const WHOLE_MULTI_SCHEME = {
    id: 'whole-ln', lineToLine: false, order: 'whole multi',
    pattern: 'one multi per leg',
    coupling: 'Line-to-neutral',
    name: 'Line-to-neutral, whole multi on one leg (one multi per phase)',
    where: 'UK and EU distros wired one Socapex per phase.',
};

// Old {voltage, phase} -> system (ruling 1's migration table). The
// explicit rows are the owner's; the "nearest" rows are logged when they
// fire. Anything absent is ambiguous and stays on the old arithmetic until
// somebody picks a system.
const MIGRATE_EXPLICIT = {
    '208/3': '120/208', '120/3': '120/208',
    '230/3': '230/400', '400/3': '230/400',
    '120/1': '120', '230/1': '230',
};
const MIGRATE_NEAREST = {
    '110/3': '120/208', '110/1': '120',
    '415/3': '230/400', '220/1': '230',
};
// The old Preferences voltage + phase pair -> the system a new distro
// takes (owner, 2026-10-16). Unlike a distro on the page, a preference
// always lands somewhere: anything absent here is 120/208.
const PREF_SYSTEM_FROM_OLD = {
    '120/3': '120/208', '110/3': '120/208', '208/3': '120/208',
    '120/1': '120', '110/1': '120',
    '240/1': '120/240',
    '230/3': '230/400', '400/3': '230/400', '415/3': '230/400',
    '230/1': '230', '220/1': '230',
};

class _DistroSystems {

    // ---- systems -------------------------------------------------------------

    distroSystems() { return DISTRO_SYSTEMS; }

    distroSystemById(id) {
        return DISTRO_SYSTEMS.find(s => s.id === id) || null;
    }

    // The system record an old {voltage, phase} migrates to, or null when
    // the pair is ambiguous. `how` says which table answered.
    _systemForVoltagePhase(voltage, phase) {
        const key = `${Math.round(Number(voltage) || 0)}/${Number(phase) === 1 ? 1 : 3}`;
        if (MIGRATE_EXPLICIT[key]) return { id: MIGRATE_EXPLICIT[key], how: 'table', key };
        if (MIGRATE_NEAREST[key]) return { id: MIGRATE_NEAREST[key], how: 'nearest', key };
        return { id: null, how: 'ambiguous', key };
    }

    // Migrate one distro record in place, once: a record that carries a
    // `system` key (even null - ambiguous, already looked at) is left
    // alone. A migrated record's voltage/phase follow its system, so every
    // reader of the old fields sees the service as it is (a "230V 3φ"
    // distro is 230/400: 400V line to line - bug fix 1).
    _ensureDistroSystem(d) {
        if (!d || typeof d !== 'object') return d;
        if (Object.prototype.hasOwnProperty.call(d, 'system')) {
            if (d.system && !this.distroSystemById(d.system)) d.system = null;
            // A record carrying its system but not the voltage and phase
            // that follow it (written by hand, a script, a partial
            // paste) takes them from the system - every reader of the old
            // fields, the header's amps among them, sees the service.
            const sys = d.system ? this.distroSystemById(d.system) : null;
            if (sys && (Number(d.voltage) !== sys.voltage || Number(d.phase) !== sys.phase)) {
                d.voltage = sys.voltage;
                d.phase = sys.phase;
            }
            return d;
        }
        const m = this._systemForVoltagePhase(d.voltage, d.phase);
        d.system = m.id;
        if (m.id) {
            const sys = this.distroSystemById(m.id);
            const before = `${d.voltage}V ${Number(d.phase) === 1 ? 1 : 3}φ`;
            d.voltage = sys.voltage;
            d.phase = sys.phase;
            if (m.how === 'nearest') {
                sendClientLog('distro_system_nearest', { id: d.id, from: before, to: sys.id });
            }
        } else {
            sendClientLog('distro_system_ambiguous', { id: d.id, voltage: d.voltage, phase: d.phase });
        }
        return d;
    }

    // The distro's system record, or null for an old record whose
    // {voltage, phase} names no system unambiguously.
    distroSystem(d) {
        if (!d) return null;
        this._ensureDistroSystem(d);
        return d.system ? this.distroSystemById(d.system) : null;
    }

    distroRegion(d) {
        const sys = this.distroSystem(d);
        return sys ? sys.region : null;
    }

    // THE MAIN'S CONTINUOUS LIMIT (owner, 2026-10-18): a show load is
    // continuous, so on a US system (120/208, 120/240, 120) the busiest
    // leg stays at or under 80% of the rating per leg - NEC continuous
    // load on a standard overcurrent device - unless the distro says its
    // main is 100% rated (`main100`, separate from `breakers100`, which
    // governs the circuit breakers only). An EU system stays at the
    // rating (load at or under the breaker). An old record with no
    // system takes the US rule when its voltage is a US nominal, else the
    // rating. Absent `main100` is off: an old show reads 80% and nothing
    // is written for it.
    //   { ratingA, pct (0.8 or 1), limitA, us, main100 }
    distroMainLimit(d) {
        const ratingA = Number(d && d.ratingA) || 0;
        let us = false;
        if (d) {
            const sys = this.distroSystem(d);
            us = sys ? sys.region === 'us'
                : US_NOMINAL_VOLTS.some(v => Math.abs((Number(d.voltage) || 0) - v) < 0.5);
        }
        const main100 = us && !!(d && d.main100);
        const pct = us && !main100 ? 0.8 : 1;
        return { ratingA, pct, limitA: ratingA * pct, us, main100 };
    }

    // AN L21-30 BOX'S FEED LIMIT (owner, 2026-10-18): the feed is rated
    // per leg (30 A) and its load is as continuous as the main's, so it
    // takes the main's rule - 80% of the rating per leg on a US system
    // unless the distro's main is 100% rated (`main100`), the rating
    // itself elsewhere. The same shape as distroMainLimit, so
    // distroMainLimitNote says where it came from ("80% of 30 A").
    distroFeedLimit(d, feedLegA) {
        const main = this.distroMainLimit(d);
        const ratingA = Number(feedLegA) || 0;
        return { ratingA, pct: main.pct, limitA: ratingA * main.pct, us: main.us, main100: main.main100 };
    }

    // "80% of 100 A" - how a header and a strip say the limit came from
    // the rating; empty where the limit IS the rating.
    distroMainLimitNote(rule) {
        if (!rule || rule.pct >= 1) return '';
        return `${Math.round(rule.pct * 100)}% of ${+rule.ratingA.toFixed(1)} A`;
    }

    // The legs a distro has, as the stores key them: X/Y/Z on three-phase,
    // X/Y on split-phase, none on a single hot. An old unmigrated record
    // keeps its old rule (three legs on 3φ, none on 1φ).
    distroLegNames(d) {
        if (!d) return [];
        const sys = this.distroSystem(d);
        if (sys) return sys.legs;
        return Number(d.phase) === 3 ? ['X', 'Y', 'Z'] : [];
    }

    // A leg as a person reads it: X/Y/Z in North America, L1/L2/L3 on an
    // EU distro.
    distroLegLabel(d, leg) {
        if (this.distroRegion(d) === 'eu') {
            return { X: 'L1', Y: 'L2', Z: 'L3' }[leg] || leg;
        }
        return leg;
    }

    // The header's supply tag: "120/208V·3φ", "230V·1φ"; an old record its
    // old "208V·1φ".
    distroSupplyText(d) {
        const sys = this.distroSystem(d);
        if (sys) return sys.supply;
        return `${(d && d.voltage) || '?'}V·${Number(d && d.phase) === 3 ? '3φ' : '1φ'}`;
    }

    // "120/208V 3φ" - the system as a sentence names it.
    distroSystemName(d) {
        const sys = this.distroSystem(d);
        if (sys) return sys.name;
        return `${(d && d.voltage) || '?'}V ${Number(d && d.phase) === 3 ? '3φ' : '1φ'}`;
    }

    // The line-to-line figure a LL circuit on this distro draws at: the
    // system's, or an old record's own voltage.
    distroLineVolts(d) {
        const sys = this.distroSystem(d);
        if (sys) return sys.vll || 0;
        return Number(d && d.voltage) || 0;
    }

    // The line-to-neutral figure.
    distroNeutralVolts(d) {
        const sys = this.distroSystem(d);
        if (sys && sys.legs.length === 3) return sys.vll / Math.sqrt(3);
        if (sys) return sys.vln;
        const v = Number(d && d.voltage) || 0;
        return Number(d && d.phase) === 3 ? v / Math.sqrt(3) : v;
    }

    voltsMatch(v, nominal) {
        const a = Number(v), n = Number(nominal);
        if (!(a > 0) || !(n > 0)) return false;
        return (NOMINAL_NAMES[n] || [n]).some(x => Math.abs(a - x) < 0.5);
    }

    // The figures a system gives, as a sentence says them: "120V or 208V",
    // "230V".
    _systemFigures(sys) {
        return sys.vll && !sys.lnOnly ? [sys.vln, sys.vll] : [sys.vln];
    }

    // The figure a refused screen should be set to: the one the distro
    // gives nearest the screen's own voltage.
    _nearestFigure(figures, v) {
        return figures.slice().sort((a, b) => Math.abs(a - v) - Math.abs(b - v))[0];
    }

    // Line-to-line or not, for a circuit at `circuitV` on a distro with no
    // face to say: a migrated system decides by which of its figures the
    // circuit voltage is (by nominal name) - anything matching neither
    // falls back to line-to-neutral, the old catch-all, and is refused at
    // the drop; an old unmigrated record keeps the old test (the circuit
    // voltage equal to the service voltage within a volt).
    _distroLineToLine(d, circuitV) {
        const cv = Number(circuitV) || 0;
        if (!d || !(cv > 0)) return false;
        const sys = d.system ? this.distroSystemById(d.system) : null;
        if (sys) return !!sys.vll && !sys.lnOnly && this.voltsMatch(cv, sys.vll);
        return Math.abs(cv - (Number(d.voltage) || 0)) < 1;
    }

    // Which of a system's figures a screen voltage is: 'ln', 'll' or null
    // (neither - refused). A blank voltage matches anything.
    systemVoltsFor(sys, voltage) {
        const v = this.voltageNumber(voltage);
        if (!sys || !(v > 0)) return 'any';
        if (this.voltsMatch(v, sys.vln)) return 'ln';
        if (sys.vll && !sys.lnOnly && this.voltsMatch(v, sys.vll)) return 'll';
        return null;
    }

    // Why a screen cannot run on this distro at all (bug fix 4): its
    // voltage is neither the system's line-to-neutral nor its line-to-line
    // figure. Null when it can, or when the distro has no system to ask.
    distroVoltageRefusal(d, layer) {
        const sys = this.distroSystem(d);
        if (!sys || !layer) return null;
        if (this.systemVoltsFor(sys, layer.powerVoltage) !== null) return null;
        const v = this.voltageNumber(layer.powerVoltage);
        const figures = this._systemFigures(sys);
        return `${layer.name} runs at ${v}V — ${d.name || d.id} gives `
            + `${figures.map(f => `${f}V`).join(' or ')}. `
            + `Set the screen to ${this._nearestFigure(figures, v)}V.`;
    }

    // ---- connectors, inputs ------------------------------------------------

    distroConnectors() { return DISTRO_CONNECTORS; }

    distroConnector(id) {
        return DISTRO_CONNECTORS.find(c => c.id === id) || null;
    }

    distroInputs() { return DISTRO_INPUTS; }

    // The couplings one connector offers on one system, as
    // [{ coupling: 'ln'|'ll', volts }] - empty where the connector is not
    // offered there at all (wrong region, L6-20 with no line-to-line
    // figure, L21-30 off 120/208).
    connectorCouplings(conn, sys) {
        if (!conn || !sys) return [];
        if (!conn.regions.includes(sys.region)) return [];
        if (conn.systems && !conn.systems.includes(sys.id)) return [];
        const ln = { coupling: 'ln', volts: sys.vln };
        const ll = sys.vll && !sys.lnOnly ? { coupling: 'll', volts: sys.vll } : null;
        if (sys.lnOnly) return conn.couple === 'll' ? [] : [ln];
        if (conn.couple === 'ln') return [ln];
        if (conn.couple === 'll') return ll ? [ll] : [];
        return ll ? [ln, ll] : [ln];
    }

    // A connector's rating where this distro is, or null where no ruling
    // gives one.
    connectorRatingA(conn, region) {
        if (!conn || !conn.rating) return null;
        const r = conn.rating[region];
        return Number.isFinite(r) ? r : null;
    }

    // The rating one face box's connector is checked at: its row's own
    // override (`connectorA`, the row's small "A" field) when one is set,
    // else the connector's default where this distro is - null where
    // neither gives one.
    faceConnectorRatingA(d, box) {
        if (!box) return null;
        const own = Number(box.row && box.row.connectorA);
        if (Number.isFinite(own) && own > 0) return own;
        return this.connectorRatingA(box.conn, this.distroRegion(d));
    }

    // ---- output rows -------------------------------------------------------

    // The rows as stored, cleaned for the system: unknown or unoffered
    // connectors dropped, counts 1..99, a coupling the connector offers
    // (the first it offers when the stored one is not), a positive breaker
    // (the region's default otherwise), a positive connector rating
    // override or none (null - the connector's default), and a pairing
    // only onto a real, unpaired row of the same circuits and coupling.
    _normalizeOutputRows(rows, sys) {
        if (!Array.isArray(rows) || !sys) return [];
        const out = [];
        const used = new Set();
        let next = 1;
        const freshId = () => {
            while (used.has(`r${next}`)) next++;
            return `r${next}`;
        };
        rows.forEach(r => {
            if (r && typeof r.id === 'string' && /^r\d+$/.test(r.id)) used.add(r.id);
        });
        const seen = new Set();
        for (const r of rows) {
            if (!r || typeof r !== 'object') continue;
            const conn = this.distroConnector(r.connector);
            const offered = this.connectorCouplings(conn, sys);
            if (!conn || !offered.length) continue;
            let id = typeof r.id === 'string' && /^r\d+$/.test(r.id) && !seen.has(r.id)
                ? r.id : freshId();
            used.add(id);
            seen.add(id);
            const count = Math.max(1, Math.min(99, parseInt(r.count, 10) || 1));
            const coupling = offered.some(o => o.coupling === r.coupling)
                ? r.coupling : offered[0].coupling;
            const b = Number(r.breakerA);
            const breakerA = Number.isFinite(b) && b > 0 ? b : DEFAULT_BREAKER[sys.region];
            const ca = r.connectorA == null || r.connectorA === '' ? NaN : Number(r.connectorA);
            const connectorA = Number.isFinite(ca) && ca > 0 && ca < 1000 ? ca : null;
            out.push({ id, connector: conn.id, count, coupling, breakerA, connectorA,
                       pairedWith: typeof r.pairedWith === 'string' ? r.pairedWith : null });
        }
        // Pairing: onto a row that is itself unpaired, carries the same
        // number of circuits and the same coupling - "same circuits, two
        // connectors" or it is not a pairing.
        const byId = new Map(out.map(r => [r.id, r]));
        const total = (r) => r.count * this.distroConnector(r.connector).circuits;
        for (const r of out) {
            if (!r.pairedWith) continue;
            const p = byId.get(r.pairedWith);
            const raw = rows.find(x => x && x.id === r.pairedWith);
            if (!p || p === r || (raw && raw.pairedWith) || total(p) !== total(r)
                    || p.coupling !== r.coupling) {
                r.pairedWith = null;
            }
        }
        for (const r of out) {
            if (r.pairedWith && byId.get(r.pairedWith).pairedWith) r.pairedWith = null;
        }
        return out;
    }

    // The distro's rows, cleaned. Empty for a distro with none - the old
    // demand-driven boxes - and for an old record with no system.
    distroRows(d) {
        const sys = this.distroSystem(d);
        if (!sys || !Array.isArray(d.outputRows) || !d.outputRows.length) return [];
        return this._normalizeOutputRows(d.outputRows, sys);
    }

    // The coupling a row's circuits run at, as volts.
    _rowVolts(sys, r) {
        return r.coupling === 'll' ? sys.vll : sys.vln;
    }

    // The FACE: every connector the rows put on the distro, numbered in row
    // order from 1 - the same numbers the multis pin to - with what each
    // one is. Null for a distro with no rows. Memoized on the record
    // against everything it reads.
    distroFace(d) {
        const rows = this.distroRows(d);
        if (!rows.length) return null;
        const sys = this.distroSystem(d);
        const sig = JSON.stringify([sys.id, rows, d.directPhasing || null]);
        if (!this._distroFaceMemo) this._distroFaceMemo = new WeakMap();
        const hit = this._distroFaceMemo.get(d);
        if (hit && hit.sig === sig) return hit.face;
        const boxes = [];
        const rowInfo = new Map();
        let n = 0, directOrd = 0, multiOrd = 0;
        for (const r of rows) {
            const conn = this.distroConnector(r.connector);
            const size = conn.circuits;
            const primary = r.pairedWith ? rows.find(x => x.id === r.pairedWith) : r;
            const info = { row: r, conn, size, first: n + 1, boxes: [],
                           circuits: r.count * size, primaryRowId: primary.id };
            rowInfo.set(r.id, info);
            for (let j = 0; j < r.count; j++) {
                n += 1;
                const box = {
                    number: n, rowId: r.id, row: r, conn, kind: conn.kind, size,
                    index: j, coupling: r.coupling, volts: this._rowVolts(sys, r),
                    breakerA: primary.breakerA, paired: !!r.pairedWith,
                    primaryRowId: primary.id,
                };
                if (!r.pairedWith) {
                    if (conn.kind === 'direct') box.directOrdinal = directOrd++;
                    else box.multiOrdinal = multiOrd++;
                }
                boxes.push(box);
                info.boxes.push(box);
            }
        }
        const face = { rows, boxes, rowInfo, sys,
                       byNumber: new Map(boxes.map(b => [b.number, b])),
                       byKey: new Map() };
        // Every physical circuit, keyed by its PRIMARY row and its place in
        // that row - a paired connector's circuit is the same key as the
        // primary's - so "is this circuit in use on the other connector"
        // has one answer.
        for (const box of boxes) {
            for (let t = 1; t <= box.size; t++) {
                const key = this._facePhysical(face, box, t).key;
                const arr = face.byKey.get(key) || [];
                arr.push({ number: box.number, tail: t });
                face.byKey.set(key, arr);
            }
        }
        this._distroFaceMemo.set(d, { sig, face });
        return face;
    }

    faceBox(d, number) {
        const face = this.distroFace(d);
        return face ? face.byNumber.get(parseInt(number, 10)) || null : null;
    }

    // A face box's tail as the PHYSICAL circuit it is: its primary row's
    // box and tail, and the key every connector of that circuit shares.
    // A tail PAST the connector's own circuits - a six-circuit multi left
    // on a one-circuit direct output, or on a three-circuit L21-30, after
    // the rows changed under it - is no circuit on this face. It keys to
    // its own connector and tail, never to the next connector's circuits
    // (index x size + tail - 1 would walk into them and read as a pairing
    // that is not there). distroChecks says it; its legs stay the
    // connector's own (_faceCircuitLegs), the way an L21-30 wraps.
    _facePhysical(face, box, tail) {
        const t = Math.max(1, parseInt(tail, 10) || 1);
        if (t > box.size) {
            const first = this._facePhysical(face, box, 1);
            return { pbox: first.pbox, ptail: t, over: true, key: `over:${box.number}:${t}` };
        }
        if (!box.paired) {
            return { pbox: box, ptail: t, key: `${box.rowId}:${box.index * box.size + t - 1}` };
        }
        const k = box.index * box.size + t - 1;
        const p = face.rowInfo.get(box.primaryRowId);
        const pbox = p.boxes[Math.floor(k / p.size)] || p.boxes[p.boxes.length - 1];
        return { pbox, ptail: (k % p.size) + 1, key: `${box.primaryRowId}:${k}` };
    }

    // The other face numbers sharing any circuit with box `number` (its
    // paired counterparts), for the auto numbering's "taken".
    _facePairedNumbers(face, number) {
        const box = face.byNumber.get(number);
        const out = new Set();
        if (!box) return out;
        for (let t = 1; t <= box.size; t++) {
            const key = this._facePhysical(face, box, t).key;
            for (const hit of face.byKey.get(key) || []) {
                if (hit.number !== number) out.add(hit.number);
            }
        }
        return out;
    }

    // Who holds box `number`'s circuits through ANOTHER connector (its
    // paired counterparts): [{ number, tail, label }]. `tail` limits the
    // question to one circuit of the box; omitted, any circuit of it.
    // "A circuit can be patched to either connector, but not both."
    _facePairedHolders(d, number, tail = null) {
        const face = this.distroFace(d);
        const box = face ? face.byNumber.get(parseInt(number, 10)) : null;
        if (!box) return [];
        const out = [];
        const numbers = this._distroMultiNumbers(d.id);
        const tails = tail != null ? [parseInt(tail, 10)] : Array.from({ length: box.size }, (_, i) => i + 1);
        for (const t of tails) {
            const key = this._facePhysical(face, box, t).key;
            for (const hit of face.byKey.get(key) || []) {
                if (hit.number === box.number) continue;
                for (const m of numbers.get(hit.number) || []) {
                    const ml = ((this.project && this.project.layers) || []).find(l => l.id === m.layerId);
                    const rec = ml ? this._powerNaming(ml).socas.get(m.soca) : null;
                    if (!rec || !Array.isArray(rec.positions)) continue;
                    const i = rec.positions.indexOf(hit.tail);
                    if (i < 0) continue;
                    out.push({ number: hit.number, tail: hit.tail,
                               label: this.getPowerCircuitLabel(ml, rec.circuits[i]) });
                }
            }
        }
        return out;
    }

    // A face box as a box TYPE - the record the dock, the pull list and the
    // binder already read off distroBoxType (name, glyph, boxSize, feedLegA,
    // breakouts, badge) - so a face box prints through the same paths a
    // typed multi does.
    faceBoxType(d, box) {
        const sys = this.distroSystem(d);
        const conn = box.conn;
        const offered = this.connectorCouplings(conn, sys);
        const volts = this._rowVolts(sys, box.row);
        // The volts go in the name where the connector could be either -
        // "Socapex 208V", "True1 120V" - never where it cannot.
        const withVolts = offered.length > 1 || conn.kind === 'multi';
        const name = withVolts ? `${conn.short} ${volts}V` : conn.short;
        let breakouts = [];
        if (conn.kind === 'multi') {
            if (conn.id === 'l2130') breakouts = ['l2130-true1', 'l2130-powercon'];
            else if (box.coupling === 'll') breakouts = ['soca-true1', 'soca-powercon'];
            else breakouts = ['soca-edison', 'soca-true1', 'soca-powercon'];
        }
        return {
            id: `face:${box.rowId}`, name, sub: conn.kind === 'direct' ? 'direct' : conn.name,
            glyph: conn.glyph, faces: [], volts: [volts], breakouts,
            badge: name.toUpperCase(), boxSize: box.size, feedLegA: conn.feedLegA || 0,
            face: true, kind: conn.kind, connectorId: conn.id, coupling: box.coupling,
            rowId: box.rowId, cable: conn.cable,
        };
    }

    // The row a plug payload names on a face distro ('face:r2'), or null.
    _faceRowFor(d, output) {
        const m = /^face:(r\d+)$/.exec(String(output || ''));
        if (!m) return null;
        const face = this.distroFace(d);
        return face && face.rowInfo.get(m[1]) ? face.rowInfo.get(m[1]) : null;
    }

    _isDirectBox(distroId, number) {
        const d = this.getDistros().find(x => x.id === distroId);
        const box = d ? this.faceBox(d, number) : null;
        return !!(box && box.kind === 'direct');
    }

    // Whether a screen's multi can land on a face box, and why not:
    // voltage first (bug fix 4 - the box's circuit voltage by its nominal
    // names; stage pin at 208V names ANSI E1.24), then the screen's
    // breakout for a multi connector (a Socapex breaks out to six True1 /
    // powerCON / Edison tails, an L21-30 to three).
    faceBoxEligible(d, box, layer) {
        if (!box || !layer) return { ok: false, why: 'no output' };
        const v = this.voltageNumber(layer.powerVoltage);
        const type = this.faceBoxType(d, box);
        if (v > 0 && !this.voltsMatch(v, box.volts)) {
            const sys = this.distroSystem(d);
            if (box.conn.id === 'stagepin' && sys.vll && this.voltsMatch(v, sys.vll)) {
                return { ok: false, why: `${layer.name} runs at ${v}V — stage pin is never `
                    + `${sys.vll}V (ANSI E1.24)` };
            }
            return { ok: false, why: `${layer.name} runs at ${v}V — `
                + `${d.name || d.id} ${box.number} (${type.name}) gives ${box.volts}V. `
                + `Set the screen to ${box.volts}V.` };
        }
        if (box.kind === 'multi') {
            const bt = this.getPowerBreakout(layer);
            if (!type.breakouts.includes(bt.id)) {
                return { ok: false, why: `${layer.name} is set to `
                    + `${this._breakoutShortName(bt)} — a ${type.name} breaks out to `
                    + `${box.conn.id === 'l2130' ? 'an L21-30 box' : 'a six-circuit multi'}; `
                    + 'change its breakout first' };
            }
        }
        return { ok: true };
    }

    // The number an AUTO multi (no pin) takes on a face distro: the first
    // face box nobody holds - no pin, no earlier auto, no paired
    // counterpart of either - that the multi can land on. Autos never land
    // on a direct output or a paired second connector; those are reached
    // by dragging onto them, which pins. Past the face when nothing on it
    // fits, so the overflow is visible rather than silent. `issued` is the
    // naming pass's per-distro set of autos dealt so far.
    _faceAutoNumber(d, face, layer, pinned, issued) {
        const busy = new Set([...(pinned || []), ...(issued || [])]);
        for (const n of [...busy]) {
            for (const m of this._facePairedNumbers(face, n)) busy.add(m);
        }
        for (const box of face.boxes) {
            if (busy.has(box.number) || box.kind !== 'multi' || box.paired) continue;
            if (!this.faceBoxEligible(d, box, layer).ok) continue;
            if (issued) issued.add(box.number);
            return box.number;
        }
        let n = face.boxes.length;
        do { n += 1; } while (busy.has(n));
        if (issued) issued.add(n);
        return n;
    }

    // The cable a circuit on a DIRECT output runs on, distro to screen:
    // the output's home-run length in the show's unit and its connector -
    // { ft, name, text } ("25' True1", "8 m Schuko") - or null where the
    // circuit is not on a direct output or no length is typed. What the
    // map's cable tag prints for it.
    directOutputCable(layer, circuitNum) {
        if (!layer) return null;
        const box = this._circuitBox(layer, circuitNum);
        if (!box.d || box.idx == null) return null;
        const fbox = this.faceBox(box.d, box.number);
        if (!fbox || fbox.kind !== 'direct') return null;
        const ft = this.parseCableLength((layer.powerSocaLengths || {})[box.idx]);
        if (ft === null) return null;
        const name = fbox.conn.cable;
        return { ft, name, text: this.cableText(ft, name) };
    }

    // How many circuits sit on the DIRECT output that circuit `circuitNum`
    // is on - its own multi's, plus any other screen's pinned to the same
    // output - or 0 where the circuit is not on a direct output. One is the
    // legal case; more is a multi left on a one-circuit output (the rows
    // changed under it), the state distroChecks flags.
    directOutputCircuitCount(layer, circuitNum) {
        if (!layer) return 0;
        const box = this._circuitBox(layer, circuitNum);
        if (!box.d || box.idx == null) return 0;
        const fbox = this.faceBox(box.d, box.number);
        if (!fbox || fbox.kind !== 'direct') return 0;
        const rec = this._powerNaming(layer).socas.get(box.idx);
        if (!rec) return 1;
        if (rec.share) return rec.share.members.reduce((t, m) => t + (Number(m.legs) || 0), 0);
        return rec.circuits.length;
    }

    // THE one cable of a circuit alone on a DIRECT output, distro to screen:
    // the circuit's own cable when one is typed (it wins over the output's
    // home run), else the output's home run - { ft, name, text }. Null when
    // the circuit is not on a direct output, when nothing is typed, or when
    // the output carries more than one circuit (the flagged error state):
    // then no circuit's cable is the output's one cable, and each circuit's
    // cable and the home run are their own cables. The map's cable tag, the
    // pull sheet, the binder's captions and its Distro page all read this.
    directCircuitCable(layer, circuitNum) {
        if (this.directOutputCircuitCount(layer, circuitNum) !== 1) return null;
        return this.powerCircuitCable(layer, circuitNum)
            || this.directOutputCable(layer, circuitNum);
    }

    // ---- legs ------------------------------------------------------------

    // THE one answer to "which legs does this circuit sit on, and is it
    // line-to-line": the leg roll-up, the box feed check, the balancer and
    // the binder all read it. `s` is the multi's soca-plan record (its
    // number is the box on `d`), `li` the circuit's index in it, `pos` its
    // tails. A face box answers from its row (coupling) and the distro
    // (legs); everything else - an old distro, a number past the face -
    // answers from the circuit's own voltage and the distro's phasing, the
    // way it always has. Returns { legs, ll, scheme? }.
    distroCircuitLegs(d, layer, s, li, pos) {
        const names = this.distroLegNames(d);
        if (!names.length) return { legs: [], ll: false };
        const box = this.faceBox(d, s.number);
        const tail = (pos && pos[li]) || li + 1;
        if (box) return this._faceCircuitLegs(d, box, tail);
        const circuitV = parseFloat(layer.powerVoltage) || 0;
        const scheme = this._circuitSchemeFor(d, circuitV);
        if (names.length === 2) {
            if (scheme.lineToLine) return { legs: ['X', 'Y'], ll: true, scheme };
            const step = scheme.id === 'paired-ln' ? Math.floor((tail - 1) / 2) : tail - 1;
            return { legs: [['X', 'Y'][((step % 2) + 2) % 2]], ll: false, scheme };
        }
        if (scheme.id === 'whole-ln') {
            const n = Math.max(1, parseInt(s.number, 10) || 1);
            return { legs: [['X', 'Y', 'Z'][(n - 1) % 3]], ll: false, scheme };
        }
        const legs = this._circuitLegs(tail, scheme.id, 0, this.socaBoxSize(layer));
        return { legs, ll: legs.length === 2, scheme };
    }

    _faceCircuitLegs(d, box, tail) {
        const face = this.distroFace(d);
        const sys = face.sys;
        const names = sys.legs;
        const ll = box.coupling === 'll';
        if (!names.length) return { legs: [], ll };
        const { pbox, ptail } = this._facePhysical(face, box, tail);
        if (pbox.kind === 'direct') {
            const ord = pbox.directOrdinal || 0;
            const step = d.directPhasing === 'paired' ? Math.floor(ord / 2) : ord;
            if (names.length === 2) return { legs: ll ? ['X', 'Y'] : [['X', 'Y'][step % 2]], ll };
            return { legs: ll ? [['X', 'Y'], ['Y', 'Z'], ['Z', 'X']][step % 3]
                                : [['X', 'Y', 'Z'][step % 3]], ll };
        }
        if (pbox.conn.id === 'l2130') {
            return { legs: this._circuitLegs(ptail, 'paired-ll', 0, 3), ll: true };
        }
        const scheme = this._circuitSchemeFor(d, ll ? sys.vll : sys.vln);
        if (names.length === 2) {
            if (ll) return { legs: ['X', 'Y'], ll, scheme };
            const step = scheme.id === 'paired-ln' ? Math.floor((ptail - 1) / 2) : ptail - 1;
            return { legs: [['X', 'Y'][step % 2]], ll, scheme };
        }
        if (scheme.id === 'whole-ln') {
            return { legs: [['X', 'Y', 'Z'][(pbox.multiOrdinal || 0) % 3]], ll: false, scheme };
        }
        return { legs: this._circuitLegs(ptail, scheme.id, 0, 6), ll, scheme };
    }

    // Book one circuit's watts onto a leg store ({legWatts, legPhasor,
    // pairWatts}). Three-phase: line-to-neutral is full current on one leg
    // at 0 deg; line-to-line is the SAME current in both legs, +30 deg on
    // the first of the cyclic pair and -30 on the second. Split-phase: the
    // two hots are 180 deg apart, so referred to each leg's own neutral a
    // 240V circuit is in phase on both - full current on each, at 0 deg.
    // Line-to-neutral amps are the circuit's own voltage (a 110V circuit
    // draws its watts at 110, ruling 2026-08-28); line-to-line amps are the
    // distro's line figure.
    _bookCircuitOnLegs(store, d, info, watts, circuitV) {
        const legs = info.legs || [];
        if (!legs.length) return;
        const names = this.distroLegNames(d);
        if (legs.length === 1) {
            // A blank circuit voltage reads the service's line-to-neutral -
            // on three-phase the line figure over root three, the figure
            // this roll-up has always used.
            const vln = names.length === 3
                ? this.distroLineVolts(d) / Math.sqrt(3) : this.distroNeutralVolts(d);
            store.legWatts[legs[0]] += watts;
            this._addLegPhasor(store.legPhasor, legs[0],
                watts / (circuitV > 0 ? circuitV : vln), 0);
            return;
        }
        const vll = this.distroLineVolts(d) || 1;
        if (names.length === 2) {
            // Single-phase reads the way its circuits read (audit, 1.5):
            // a 240V circuit draws its watts at the circuit's own voltage,
            // so the legs and the header agree with the circuit lines.
            const amps = watts / (circuitV > 0 ? circuitV : vll);
            this._addLegPhasor(store.legPhasor, legs[0], amps, 0);
            this._addLegPhasor(store.legPhasor, legs[1], amps, 0);
            store.legWatts[legs[0]] += watts / 2;
            store.legWatts[legs[1]] += watts / 2;
            store.pairWatts.XY = (store.pairWatts.XY || 0) + watts;
            return;
        }
        // Three-phase line-to-line stays on the distro's line figure
        // (bug fix 3).
        const amps = watts / vll;
        const [first, second] = this._cyclicPair(legs[0], legs[1]);
        this._addLegPhasor(store.legPhasor, first, amps, 30);
        this._addLegPhasor(store.legPhasor, second, amps, -30);
        store.legWatts[first] += watts / 2;
        store.legWatts[second] += watts / 2;
        const key = [first, second].join('');
        store.pairWatts[key] = (store.pairWatts[key] || 0) + watts;
    }

    // The schemes a distro's phasing select can name, beyond the five
    // documented North American ones: "whole multi on one leg" on an EU
    // distro (ruling 4 - offered there only).
    _distroExtraSchemes(d) {
        return this.distroRegion(d) === 'eu' ? [WHOLE_MULTI_SCHEME] : [];
    }

    _wholeMultiScheme() { return WHOLE_MULTI_SCHEME; }

    // A phasing scheme's name as this distro reads its legs: an EU distro
    // says "L1 L2 L3 L1 L2 L3" where a US one says "X Y Z X Y Z" (the
    // direct-outputs select already did).
    distroSchemeName(d, sc) {
        if (!sc || !sc.name) return '';
        if (this.distroRegion(d) !== 'eu' || !sc.pattern) return sc.name;
        const L = { X: 'L1', Y: 'L2', Z: 'L3' };
        const pattern = sc.pattern.split(' ').map(w => (/^[XYZ]+$/.test(w)
            ? w.split('').map(k => L[k]).join('-') : w)).join(' ');
        return sc.name.split(`(${sc.pattern})`).join(`(${pattern})`);
    }

    // The amps one multi draws on a SINGLE-HOT distro (120V, 230V): its
    // watts at the circuits' own voltage, the way its circuit lines read
    // them, so an old 110V show keeps its figure after its distro became
    // 120V. Null where the header keeps its own arithmetic: a distro
    // with legs, or an old record with no system.
    _singleHotAmps(d, watts, circuitV) {
        const sys = this.distroSystem(d);
        if (!sys || sys.legs.length) return null;
        return watts / (circuitV > 0 ? circuitV : sys.vln);
    }

    // An L21-30 box's feed legs on an old single-phase record with no
    // system (a 208V 1φ distro from an older show): the 1.4.1 walk, which
    // read every box as three legs whatever the distro's phase, so the
    // 30 A/leg check keeps the figure it had. Null for any other distro.
    _legacyBoxFeedLegAmps(distro, members) {
        if (!distro || this.distroSystem(distro) || this.distroLegNames(distro).length) return null;
        const phasor = { X: { re: 0, im: 0 }, Y: { re: 0, im: 0 }, Z: { re: 0, im: 0 } };
        const vln = (Number(distro.voltage) || 0) / Math.sqrt(3);
        for (const m of (members || [])) {
            if (!m || !m.layer || !m.s) continue;
            const circuitV = parseFloat(m.layer.powerVoltage) || 0;
            const scheme = this._circuitSchemeFor(distro, circuitV);
            const boxSize = this.socaBoxSize(m.layer);
            const pos = this.socaCircuitPositions(m.layer, m.s.soca, m.s.legs.length);
            for (let li = 0; li < m.s.legs.length; li++) {
                const leg = m.s.legs[li];
                const legs = this._circuitLegs(pos[li], scheme.id, 0, boxSize);
                if (legs.length === 1) {
                    this._addLegPhasor(phasor, legs[0],
                        leg.watts / (circuitV > 0 ? circuitV : vln), 0);
                } else {
                    const [first, second] = this._cyclicPair(legs[0], legs[1]);
                    const amps = leg.watts / (Number(distro.voltage) || 1);
                    this._addLegPhasor(phasor, first, amps, 30);
                    this._addLegPhasor(phasor, second, amps, -30);
                }
            }
        }
        const mag = (p) => Math.sqrt(p.re * p.re + p.im * p.im);
        return { X: mag(phasor.X), Y: mag(phasor.Y), Z: mag(phasor.Z) };
    }

    // The system a new distro takes from Preferences: the stored system,
    // else the old voltage + phase pair the Preferences used to keep,
    // mapped (owner, 2026-10-16), else 120/208.
    preferenceDistroSystem(prefs) {
        const p = prefs || {};
        if (this.distroSystemById(p.distroSystem)) return p.distroSystem;
        if (p.distroVoltage == null && p.distroPhase == null) return '120/208';
        const key = `${Math.round(Number(p.distroVoltage) || 0)}/${Number(p.distroPhase) === 1 ? 1 : 3}`;
        return PREF_SYSTEM_FROM_OLD[key] || '120/208';
    }

    // ---- the screen's three-phase figure (bug fix 3) -------------------

    // The line-to-line voltage a screen's balanced 3φ figure divides by:
    // the service's, never the screen's own voltage read as if it were
    // line-to-line (a 120V screen on 120/208 is W / (208 x 1.73), not
    // W / (120 x 1.73)). The distros its multis are on decide when they
    // agree; otherwise the system its voltage belongs to (120 or 208 -
    // 120/208, 230 or 400 - 230/400); otherwise the old reading.
    // A bare voltage (a project total per voltage) is read the same way,
    // with no distros to ask.
    threePhaseLineVoltage(layer) {
        const bare = typeof layer === 'number' || typeof layer === 'string';
        const v = this.voltageNumber(bare ? layer : (layer && layer.powerVoltage));
        const seen = new Set();
        if (!bare && layer && (layer.type || 'screen') === 'screen') {
            const assign = layer.powerSocaDistro || {};
            const ids = new Set(Object.values(assign).filter(Boolean));
            for (const d of this.getDistros()) {
                if (!ids.has(d.id)) continue;
                const legs = this.distroLegNames(d);
                if (legs.length === 3) seen.add(this.distroLineVolts(d));
            }
        }
        if (seen.size === 1) return [...seen][0];
        for (const sys of DISTRO_SYSTEMS) {
            if (sys.legs.length !== 3) continue;
            if (this.voltsMatch(v, sys.vln) || this.voltsMatch(v, sys.vll)) return sys.vll;
        }
        return v;
    }

    // ---- checks (rulings 5 and 6) -----------------------------------------

    // Every circuit on a distro, resolved: [{ layer, s, leg, box, info,
    // amps, label }]. `box` is the face box (null off the face or on an
    // old distro).
    _distroCircuitsOn(d) {
        const out = [];
        for (const layer of (this.project && this.project.layers) || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            for (const s of this.getSocaPlan(layer)) {
                if (assign[s.soca] !== d.id) continue;
                const pos = this.socaCircuitPositions(layer, s.soca, s.legs.length);
                s.legs.forEach((leg, li) => {
                    out.push({ layer, s, leg, tail: pos[li], box: this.faceBox(d, s.number) });
                });
            }
        }
        return out;
    }

    // What the dock's strip says about one distro beyond its OVER: each a
    // { text, mild }. The voltage refusals, the breaker and connector
    // checks, XX at 208V, a paired circuit patched twice, a multi past
    // the face.
    distroChecks(d) {
        const out = [];
        if (!d) return out;
        const sys = this.distroSystem(d);
        const name = d.name || d.id;
        if (!sys) {
            out.push({ mild: true,
                       text: `${name} is ${this.distroSystemName(d)} — pick its system `
                           + '(120/208V, 120/240V, 120V, 230/400V or 230V) behind its ⚙.' });
            return out;
        }
        const face = this.distroFace(d);
        const circuits = this._distroCircuitsOn(d);
        const said = new Set();
        const say = (key, text, mild = false) => {
            if (said.has(key)) return;
            said.add(key);
            out.push({ text, mild });
        };
        // A screen whose voltage the system does not have (bug fix 4).
        for (const c of circuits) {
            if (c.box) continue;
            const why = this.distroVoltageRefusal(d, c.layer);
            if (why) say(`v:${c.layer.id}`, why);
        }
        if (face) {
            // XX at 208V (ruling 6): warned, not refused.
            for (const r of face.rows) {
                if (r.connector === 'powerconxx' && sys.region === 'us'
                        && r.coupling === 'll' && sys.vll > 127) {
                    say(`xx:${r.id}`, `powerCON XX is only US-listed to 127V — ${name}'s `
                        + `${r.count} powerCON XX output${r.count === 1 ? '' : 's'} run at ${sys.vll}V.`);
                }
            }
            const physical = new Map();     // key -> [{c, label}]
            const limitOf = (box) => {
                const pct = sys.region === 'us' && !d.breakers100 ? 0.8 : 1;
                return { amps: box.breakerA * pct, pct };
            };
            for (const c of circuits) {
                if (!c.box) {
                    say(`past:${c.s.number}`, `${name} ${c.s.number} is not on ${name}'s face — `
                        + `it has ${face.boxes.length} output${face.boxes.length === 1 ? '' : 's'}.`);
                    continue;
                }
                // A multi of several circuits on a one-circuit direct
                // output (the rows changed under it). A multi past a
                // smaller multi's circuits is the box's own strip line
                // (the dock's "more circuits than the three ...").
                if (c.box.kind === 'direct' && c.s.legs.length > c.box.size) {
                    const conn = c.box.conn.short;
                    const an = /^(?:[aeiou]|L\d)/i.test(conn) ? 'an' : 'a';
                    say(`dir:${c.layer.id}:${c.s.soca}`, `${c.layer.name}'s ${c.s.legs.length} `
                        + `circuits are on ${c.s.name || `${name} ${c.box.number}`}, ${an} ${conn} `
                        + '— one circuit only. Move it to a multi output.');
                }
                const elig = this.faceBoxEligible(d, c.box, c.layer);
                if (!elig.ok && !/breakout/.test(elig.why)) say(`fv:${c.layer.id}:${c.box.number}`, elig.why);
                const key = this._facePhysical(face, c.box, c.tail).key;
                const arr = physical.get(key) || [];
                arr.push(c);
                physical.set(key, arr);
            }
            for (const [key, list] of physical) {
                const box = list[0].box;
                const amps = list.reduce((t, c) => t + (Number(c.leg.amps) || 0), 0);
                const label = list.map(c => c.leg.label).join(' + ');
                const numbers = new Set(list.map(c => c.box.number));
                if (numbers.size > 1) {
                    say(`pair:${key}`, `${label} are one circuit on two connectors (paired) — `
                        + 'patch it to one or the other.');
                }
                const lim = limitOf(box);
                if (amps > lim.amps + 1e-9) {
                    say(`brk:${key}`, sys.region === 'us' && lim.pct < 1
                        ? `${label} draws ${amps.toFixed(1)} A on a ${box.breakerA} A breaker — `
                            + `over the 80% continuous limit (${+lim.amps.toFixed(1)} A)`
                        : `${label} draws ${amps.toFixed(1)} A on a ${box.breakerA} A breaker — OVER`);
                }
                for (const c of list) {
                    const rating = this.faceConnectorRatingA(d, c.box);
                    if (rating != null && amps > rating + 1e-9 && c.box.kind === 'direct') {
                        say(`conn:${key}:${c.box.number}`, `${label} draws ${amps.toFixed(1)} A — `
                            + `a ${c.box.conn.short} is rated ${rating} A here`);
                    }
                }
            }
            // A multi left on a one-circuit output (a show already in that
            // state) says the output's whole load against what it can
            // carry - its breaker and its connector's rating, the row's
            // override included (2026-10-18, "it should show over capacity").
            for (const cr of this._faceCrowding(d)) {
                const text = this._crowdCapacityText(d, cr);
                if (text) say(`cap:${cr.number}`, text);
            }
        }
        return out;
    }

    // ---- crowded outputs (owner, 2026-10-18) -------------------------------
    //
    // "you cannot put a 6 circuit multi on tru 1 ... if you change then throw
    // an error and ask for a fix. dont let it go unchanged." A DIRECT output
    // carries one circuit; a multi pinned to it with more is never made by
    // an edit: the row edit, preset or removal that would make it asks
    // first (take the multi off, or cancel), and a pin or a carried pin
    // onto one is refused. A show already in that state keeps its flag and
    // opens unchanged - and says the output's load against its capacity.

    // The direct outputs on `d`'s face (d may be a prospective copy) whose
    // PINNED multis carry more circuits than the output has:
    // [{ number, box, circuits, amps, members: [{ layer, soca, legs, amps,
    // name }] }]. Autos never land on a direct output, so pins are all of it.
    _faceCrowding(d) {
        const face = d ? this.distroFace(d) : null;
        if (!face) return [];
        const by = new Map();
        for (const layer of (this.project && this.project.layers) || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const pins = layer.powerSocaNumber || {};
            for (const s of this.getSocaPlan(layer)) {
                if (assign[s.soca] !== d.id) continue;
                const n = parseInt(pins[s.soca], 10);
                if (!Number.isFinite(n) || n < 1) continue;
                const box = face.byNumber.get(n);
                if (!box || box.kind !== 'direct') continue;
                const amps = (s.legs || []).reduce((t, g) => t + (Number(g.amps) || 0), 0);
                const rec = by.get(n) || { number: n, box, circuits: 0, amps: 0, members: [] };
                rec.circuits += s.legs.length;
                rec.amps += amps;
                rec.members.push({ layer, soca: s.soca, legs: s.legs.length, amps, name: s.name });
                by.set(n, rec);
            }
        }
        // `where` is the output as the labels name it ("PD4" - the name the
        // multis on it wear), else the distro and number.
        return [...by.values()].filter(r => r.circuits > r.box.size)
            .map(r => ({ ...r, where: (r.members[0] && r.members[0].name)
                || `${d.name || d.id} ${r.number}` }))
            .sort((a, b) => a.number - b.number);
    }

    // What one crowded output can carry: the smaller of its breaker and
    // its connector's rating (the row's override when set) - null where
    // neither gives a figure.
    _crowdCapacityA(d, box) {
        const figs = [Number(box.breakerA), this.faceConnectorRatingA(d, box)]
            .filter(x => Number.isFinite(x) && x > 0);
        return figs.length ? Math.min(...figs) : null;
    }

    // "PD4 True1 at 92.3 A of 20 A — over capacity", or null under it.
    _crowdCapacityText(d, cr) {
        const cap = this._crowdCapacityA(d, cr.box);
        if (cap == null || !(cr.amps > cap + 1e-9)) return null;
        return `${cr.where} ${cr.box.conn.short} at `
            + `${cr.amps.toFixed(1)} A of ${+cap.toFixed(1)} A — over capacity`;
    }

    // The distro a patch would make, for asking - never stored: its system
    // and its rows as the patch leaves them.
    _distroAfterPatch(d, patch) {
        const t = JSON.parse(JSON.stringify(d));
        if (patch.system !== undefined) {
            const sys = this.distroSystemById(patch.system);
            if (sys) { t.system = sys.id; t.voltage = sys.voltage; t.phase = sys.phase; }
        }
        if (patch.outputRows !== undefined) {
            if (Array.isArray(patch.outputRows) && patch.outputRows.length) {
                t.outputRows = patch.outputRows.map(r => ({ ...r }));
            } else {
                delete t.outputRows;
            }
        }
        return t;
    }

    // The crowding a patch would MAKE: entries of the patched face holding
    // a multi that is not already crowded there today.
    _crowdingMadeBy(d, patch) {
        if (!d || (patch.outputRows === undefined && patch.system === undefined)) return [];
        const key = (m, n) => `${m.layer.id}:${m.soca}@${n}`;
        const before = new Set();
        this._faceCrowding(d).forEach(cr => cr.members.forEach(m => before.add(key(m, cr.number))));
        return this._faceCrowding(this._distroAfterPatch(d, patch))
            .filter(cr => cr.members.some(m => !before.has(key(m, cr.number))));
    }

    // "WALL A's 6-circuit multi" / "WALL A's and WALL B's multis".
    _crowdWho(members) {
        const names = [...new Set(members.map(m => m.layer.name))];
        if (members.length === 1) {
            return `${names[0]}'s ${members[0].legs}-circuit multi`;
        }
        const list = names.length === 1 ? `${names[0]}'s`
            : names.slice(0, -1).map(n => `${n}'s`).join(', ') + ` and ${names[names.length - 1]}'s`;
        return `${list} multis`;
    }

    _circuitsWord(n) {
        return ({ 1: 'one circuit', 3: 'three circuits', 6: 'six circuits' })[n] || `${n} circuits`;
    }

    // The ask: which multis sit where, what the output would become, and
    // the two ways out - take them off and apply, or cancel. A locked
    // screen's multi cannot come off: then Cancel alone, the lock named.
    // `apply` runs the change; resolves true when it was applied.
    _askCrowding(d, made, apply) {
        const ID = 'crowd-modal';
        document.getElementById(ID)?.remove();
        const esc = (x) => String(x).replace(/[&<>"]/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
        const name = d.name || d.id;
        const members = made.flatMap(cr => cr.members.map(m => ({ ...m, cr })));
        const locked = [...new Set(members.filter(m => m.layer.locked).map(m => m.layer))];
        const lines = made.map(cr => {
            const where = cr.where;
            const cap = this._crowdCapacityText(d, cr);
            return `<p style="margin:0 0 8px;">${esc(this._crowdWho(cr.members))} `
                + `${cr.members.length === 1 ? 'is' : 'are'} on ${esc(where)}. ${esc(where)} would become `
                + `a ${esc(cr.box.conn.short)}, which carries ${this._circuitsWord(cr.box.size)}.</p>`
                + (cap ? `<p class="crowd-cap" style="margin:0 0 8px; color:#e05050;">${esc(cap)}</p>` : '');
        }).join('');
        const where = [...new Set(made.map(cr => cr.where))].join(', ');
        const who = this._crowdWho(members);
        const lockNote = locked.length
            ? `<p class="crowd-locked" style="margin:8px 0 0; color:#dcb968;">${esc(locked.map(l => l.name).join(', '))} `
                + `${locked.length === 1 ? 'is' : 'are'} locked, so ${locked.length === 1 ? 'its multi' : 'their multis'} `
                + 'cannot come off. Unlock to take it off, or cancel the change.</p>'
            : '';
        const el = document.createElement('div');
        el.id = ID;
        el.className = 'modal';
        el.style.display = 'block';
        el.innerHTML = `
<div class="modal-content" style="background:#252525; border-radius:8px; padding:0; width:520px; max-width:94vw; margin:100px auto; border:1px solid #6a2c2c; overflow:hidden;">
  <div style="padding:14px 20px; border-bottom:1px solid #3a3a3a;">
    <h2 style="margin:0; font-size:15px; letter-spacing:0.5px; color:#ff9a9a;">A MULTI WOULD SIT ON A ONE-CIRCUIT OUTPUT</h2>
  </div>
  <div style="padding:16px 20px; font-size:12px; line-height:1.55; color:#d8d8d8;">${lines}${lockNote}</div>
  <div style="display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end; padding:0 20px 16px;">
    <button class="btn btn-secondary crowd-cancel">Cancel the change</button>
    ${locked.length ? '' : `<button class="btn crowd-take">Take ${esc(who)} off ${esc(where)} and apply the change</button>`}
  </div>
</div>`;
        document.body.appendChild(el);
        sendClientLog('distro_crowding_asked', { distroId: d.id, outputs: made.map(cr => cr.number),
                                                 locked: locked.map(l => l.id) });
        return new Promise(resolve => {
            const close = (applied) => {
                el.remove();
                document.removeEventListener('keydown', onKey, true);
                resolve(applied);
            };
            const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(false); } };
            document.addEventListener('keydown', onKey, true);
            el.querySelector('.crowd-cancel').addEventListener('click', () => {
                sendClientLog('distro_crowding_cancelled', { distroId: d.id });
                close(false);
            });
            const take = el.querySelector('.crowd-take');
            if (take) take.addEventListener('click', () => {
                this._takeCrowdedOff(members);
                apply();
                sendClientLog('distro_crowding_taken_off', { distroId: d.id,
                    multis: members.map(m => ({ layerId: m.layer.id, soca: m.soca, number: m.cr.number })) });
                close(true);
            });
        });
    }

    // Take each multi off the output it is pinned to: the pin goes (it is
    // an auto on its distro again, dealt to a free multi output) and the
    // feed's typed lengths go with it - the home run and its circuits'
    // cables were that output's (the feed-lengths rule). No history entry:
    // the change that follows takes the one entry for both.
    _takeCrowdedOff(members) {
        const touched = new Set();
        for (const m of members) {
            const circuits = this._socaClearTargets(m.layer, m.soca).circuits;
            this._forgetFeedLengths(m.layer, m.soca, circuits);
            const pins = m.layer.powerSocaNumber || (m.layer.powerSocaNumber = {});
            delete pins[m.soca];
            touched.add(m.layer);
        }
        this._circuitTailCache = null;
        if (touched.size) this.updateLayers([...touched], false);
    }

    // Why multi `socaIndex` of `layer` cannot be pinned to (distroId,
    // number), or null: a direct output carries one circuit.
    _crowdRefusal(layer, socaIndex, distroId, number) {
        const d = distroId ? this.getDistros().find(x => x.id === distroId) : null;
        const n = parseInt(number, 10);
        const box = d && Number.isFinite(n) ? this.faceBox(d, n) : null;
        if (!box || box.kind !== 'direct') return null;
        const s = this.getSocaPlan(layer).find(x => x.soca === Number(socaIndex));
        if (!s) return null;
        let others = 0;
        for (const l of (this.project && this.project.layers) || []) {
            if ((l.type || 'screen') !== 'screen') continue;
            const assign = l.powerSocaDistro || {};
            const pins = l.powerSocaNumber || {};
            for (const o of this.getSocaPlan(l)) {
                if (l === layer && o.soca === s.soca) continue;
                if (assign[o.soca] === d.id && parseInt(pins[o.soca], 10) === n) others += o.legs.length;
            }
        }
        if (s.legs.length + others <= box.size) return null;
        const where = `${d.name || d.id} ${n}`;
        return s.legs.length > box.size
            ? `${layer.name}'s ${s.legs.length}-circuit multi cannot go on ${where} — `
                + `a ${box.conn.short} carries ${this._circuitsWord(box.size)}. Use a multi output.`
            : `${where} already carries its ${this._circuitsWord(box.size)} — `
                + `a ${box.conn.short} takes no more.`;
    }

    _sayCrowdRefusal(text) {
        if (typeof this._toast === 'function') this._toast(text, true);
        if (typeof this._dockSay === 'function') this._dockSay(text);
        sendClientLog('distro_crowding_refused', { text });
    }

    // ---- presets ---------------------------------------------------------

    builtInDistroPresets() { return DISTRO_PRESETS; }

    // The presets people saved (server-side, shared like named layouts).
    // Cached once fetched; `refresh` asks again.
    loadCustomDistroPresets(refresh = false) {
        if (this._customDistroPresets && !refresh) {
            return Promise.resolve(this._customDistroPresets);
        }
        return fetch('/api/distro-presets')
            .then(r => r.ok ? r.json() : { presets: [] })
            .then(data => {
                this._customDistroPresets = Array.isArray(data.presets) ? data.presets : [];
                return this._customDistroPresets;
            })
            .catch(() => (this._customDistroPresets = this._customDistroPresets || []));
    }

    // The part of a distro a preset carries: the gear, never the show -
    // `main100` is the main's rating, `overloadAccepted` is a call made
    // about one show's load and stays with the show.
    _distroPresetBody(d) {
        return {
            typeName: d.typeName || null,
            system: d.system, input: d.input || null, ratingA: d.ratingA,
            breakers100: !!d.breakers100, main100: !!d.main100,
            phasing: d.phasing || null,
            directPhasing: d.directPhasing || null,
            rows: this.distroRows(d).map(r => ({ ...r })),
        };
    }

    // Lay a preset on a distro: system, input, rating, breakers, main,
    // phasing and rows in ONE 'Apply Distro Preset' entry. A preset saved
    // before `main100` existed carries none, which is off. The distro's
    // Type becomes the Type the preset carries, else the preset's own name
    // (2026-10-18) - still editable after. The multis on it keep their numbers
    // and are checked against the new face like any other.
    applyDistroPreset(distroId, preset) {
        if (!preset) return null;
        const body = preset.distro || preset;
        const typeName = String(body.typeName || preset.name || '').trim();
        return this.updateDistro(distroId, {
            typeName: typeName || null,
            system: body.system, input: body.input || null,
            ratingA: body.ratingA, breakers100: !!body.breakers100,
            main100: !!body.main100,
            phasing: body.phasing || null, directPhasing: body.directPhasing || null,
            outputRows: (body.rows || []).map(r => ({ ...r })),
        }, 'Apply Distro Preset');
    }

    saveDistroPreset(distroId, name) {
        const d = this.getDistros().find(x => x.id === distroId);
        const clean = String(name || '').trim();
        if (!d || !clean) return Promise.resolve(null);
        return this._distroPresetRequest('PUT',
            { name: clean, distro: this._distroPresetBody(d) }, 'Preset not saved');
    }

    deleteDistroPreset(name) {
        return this._distroPresetRequest('DELETE', { name }, 'Preset not deleted');
    }

    // One preset request. A refusal rejects with a sentence that says why:
    // the server's own reason when it sent one, its status when the reply
    // is not JSON (an error page), and plainly when it could not be reached.
    _distroPresetRequest(method, payload, failed) {
        return fetch('/api/distro-presets', {
            method, headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).catch(() => {
            throw new Error(`${failed} - the app's server could not be reached.`);
        }).then(r => r.text().then(text => {
            let j = null;
            try { j = JSON.parse(text); } catch (e) { j = null; }
            if (!r.ok || !j || typeof j !== 'object') {
                const why = j && typeof j.error === 'string' && j.error
                    ? j.error : `the server said ${r.status}`;
                throw new Error(`${failed} - ${why}.`);
            }
            this._customDistroPresets = Array.isArray(j.presets) ? j.presets : [];
            return this._customDistroPresets;
        }));
    }

    // ---- the gear popover's sections ---------------------------------------

    _distroGearCap(text) {
        const c = document.createElement('label');
        c.style.fontSize = '10px';
        c.style.color = 'var(--ps-dim, #c0c0c0)';
        c.style.textTransform = 'uppercase';
        c.textContent = text;
        return c;
    }

    _distroGearRow() {
        const r = document.createElement('div');
        r.style.display = 'flex';
        r.style.flexWrap = 'wrap';
        r.style.gap = '6px';
        r.style.alignItems = 'center';
        r.style.marginTop = '6px';
        return r;
    }

    // SYSTEM · INPUT · RATING per leg · 100% breakers (US). `patch` is the
    // gear's own updateDistro + restate.
    _buildDistroSupplySection(d, wrap, patch) {
        const cap = (t) => this._distroGearCap(t);
        const sys = this.distroSystem(d);
        // TYPE: what the gear is, as the pull sheet and the binder's pull
        // lists name it (2026-10-18). A preset fills it with its name.
        const r0 = this._distroGearRow();
        r0.classList.add('hw-pop-supply');
        r0.style.marginTop = '0';
        r0.appendChild(cap('Type'));
        const type = document.createElement('input');
        type.type = 'text';
        type.className = 'hw-pop-type';
        type.value = d.typeName || '';
        type.placeholder = 'Distro';
        type.maxLength = 60;
        type.style.flex = '1 1 0';
        type.style.minWidth = '0';
        type.dataset.lrdField = `distro-type-${d.id}`;
        type.title = 'What this distro is, the way the pull sheet lists it - '
            + 'e.g. "200A 24 circuits". Blank prints "Distro". Starting from a '
            + 'preset fills it with the preset\'s name.';
        type.addEventListener('change', () => patch({ typeName: type.value }));
        r0.appendChild(type);
        wrap.appendChild(r0);
        const r1 = this._distroGearRow();
        r1.classList.add('hw-pop-supply');
        r1.appendChild(cap('System'));
        const sel = document.createElement('select');
        sel.className = 'info-select';
        sel.dataset.lrdField = `distro-system-${d.id}`;
        sel.title = 'The service this distro is: its line-to-neutral and '
            + 'line-to-line voltages and how many legs it has. US distros '
            + 'label their legs X/Y/Z, EU distros L1/L2/L3.';
        if (!sys) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = `${this.distroSystemName(d)} — pick a system`;
            opt.selected = true;
            sel.appendChild(opt);
        }
        DISTRO_SYSTEMS.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.id;
            opt.textContent = s.name;
            if (sys && sys.id === s.id) opt.selected = true;
            sel.appendChild(opt);
        });
        sel.addEventListener('change', () => { if (sel.value) patch({ system: sel.value }); });
        r1.appendChild(sel);
        wrap.appendChild(r1);

        const r2 = this._distroGearRow();
        r2.classList.add('hw-pop-supply');
        r2.appendChild(cap('Input'));
        const input = document.createElement('select');
        input.className = 'info-select';
        input.dataset.lrdField = `distro-input-${d.id}`;
        input.title = 'What feeds the distro. Picking one sets the rating '
            + 'per leg to the input\'s own figure.';
        const none = document.createElement('option');
        none.value = '';
        none.textContent = '—';
        input.appendChild(none);
        // Only the inputs that can feed this system - except the one the
        // distro already has, which stays listed and selected even when it
        // no longer fits (an old record, or the system changed after it
        // was picked): nothing is dropped behind the reader's back. A
        // distro with no system yet lists them all.
        DISTRO_INPUTS.forEach(i => {
            if (sys && d.input !== i.id && !i.systems.includes(sys.id)) return;
            const opt = document.createElement('option');
            opt.value = i.id;
            opt.textContent = i.name;
            if (d.input === i.id) opt.selected = true;
            input.appendChild(opt);
        });
        input.addEventListener('change', () => {
            const pick = DISTRO_INPUTS.find(i => i.id === input.value);
            patch(pick ? { input: pick.id, ratingA: pick.ratingA } : { input: null });
        });
        r2.appendChild(input);
        r2.appendChild(cap('Rating'));
        const rate = document.createElement('input');
        rate.type = 'number';
        rate.min = '1';
        rate.value = d.ratingA;
        rate.style.width = '56px';
        rate.dataset.lrdField = `distro-rating-${d.id}`;
        rate.title = 'The rating of each leg in amps. The header reads the '
            + 'worst leg against it.';
        rate.addEventListener('change', () => patch({ ratingA: rate.value }));
        r2.appendChild(rate);
        const per = document.createElement('small');
        per.textContent = 'A per leg';
        per.style.color = 'var(--ps-faint, #969696)';
        r2.appendChild(per);
        wrap.appendChild(r2);

        // The two 100% switches sit side by side on US distros: the
        // circuits' breakers, and the distro's main (2026-10-18, a
        // separate switch). An old record with no system on a US voltage
        // takes the US main rule, so it is offered its main switch too.
        const rule = this.distroMainLimit(d);
        const check = (field, on, text, title, key) => {
            const lab = document.createElement('label');
            lab.className = 'hw-pop-check';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = !!on;
            cb.dataset.lrdField = `distro-${field}-${d.id}`;
            cb.addEventListener('change', () => patch({ [key]: cb.checked }));
            lab.appendChild(cb);
            lab.appendChild(document.createTextNode(text));
            lab.title = title;
            return lab;
        };
        if ((sys && sys.region === 'us') || (!sys && rule.us)) {
            const r3 = this._distroGearRow();
            if (sys) {
                r3.appendChild(check('breakers100', d.breakers100, '100% rated breakers',
                    'Off: every circuit is checked at 80% of its breaker '
                    + '(NEC 210.20(A), continuous load). On: at the full breaker.',
                    'breakers100'));
            }
            r3.appendChild(check('main100', d.main100, 'Main 100% rated',
                'Off: the busiest leg is held to 80% of the rating per leg. '
                + 'A show load is continuous, and a standard main breaker '
                + 'carries 80% of its rating continuously (NEC). On: the main '
                + 'is 100% rated and carries the full rating. The circuits\' '
                + 'breakers have their own switch.', 'main100'));
            wrap.appendChild(r3);
        }
        // Accept overload: offered while the busiest leg is past the
        // limit, and kept on show while ticked - an acceptance stays until
        // somebody unticks it, whatever the load does after.
        const load = typeof this.getDistroLoads === 'function'
            ? this.getDistroLoads().find(x => x.id === d.id) : null;
        if ((load && load.over) || d.overloadAccepted) {
            const r4 = this._distroGearRow();
            const why = load && load.over
                ? `busiest leg ${load.amps.toFixed(1)} A of ${+load.limitA.toFixed(1)} A`
                    + (rule.pct < 1 ? ` (${this.distroMainLimitNote(rule)})` : '')
                : 'under the limit now';
            r4.appendChild(check('overload-accepted', d.overloadAccepted,
                `Accept overload — ${why}`,
                'Accept this distro\'s overload: its error turns amber and reads '
                + 'accepted. The figures stay as they are, and the acceptance '
                + 'stays until you untick it.', 'overloadAccepted'));
            wrap.appendChild(r4);
        }
    }

    // The order direct outputs take the legs in - rotating by default
    // (ruling 4), paired as the other documented order.
    _buildDistroDirectPhasing(d, wrap, patch) {
        const face = this.distroFace(d);
        if (!face || !face.boxes.some(b => b.kind === 'direct')) return;
        if (this.distroLegNames(d).length < 2) return;
        const r = this._distroGearRow();
        r.classList.add('hw-pop-supply');
        r.appendChild(this._distroGearCap('Direct outputs'));
        const sel = document.createElement('select');
        sel.className = 'info-select';
        sel.dataset.lrdField = `distro-direct-phasing-${d.id}`;
        sel.title = 'How the direct outputs land on the legs, in face order.';
        const L = (k) => this.distroLegLabel(d, k);
        const three = this.distroLegNames(d).length === 3;
        const rot = three ? `${L('X')} ${L('Y')} ${L('Z')} ${L('X')} ${L('Y')} ${L('Z')}`
            : `${L('X')} ${L('Y')} ${L('X')} ${L('Y')}`;
        const pair = three ? `${L('X')} ${L('X')} ${L('Y')} ${L('Y')} ${L('Z')} ${L('Z')}`
            : `${L('X')} ${L('X')} ${L('Y')} ${L('Y')}`;
        [['', `Rotating (${rot})`], ['paired', `Paired (${pair})`]].forEach(([v, t]) => {
            const opt = document.createElement('option');
            opt.value = v;
            opt.textContent = t;
            if ((d.directPhasing || '') === v) opt.selected = true;
            sel.appendChild(opt);
        });
        sel.addEventListener('change', () => patch({ directPhasing: sel.value || null }));
        r.appendChild(sel);
        wrap.appendChild(r);
    }

    // OUTPUT ROWS: one line per row - connector, count, coupling where the
    // connector offers two, breaker, paired-with, remove - then Add output,
    // the presets and Save as preset. A distro with no rows keeps the old
    // multi-type checklist (the caller's), and this section offers the
    // first row and the presets under it.
    _buildDistroOutputRows(d, wrap, patch) {
        const sys = this.distroSystem(d);
        const sec = document.createElement('div');
        sec.className = 'hw-pop-outs hw-pop-rows';
        const capRow = document.createElement('div');
        capRow.className = 'hw-pop-outs-cap';
        capRow.appendChild(this._distroGearCap('Output rows'));
        const sub = document.createElement('small');
        sub.textContent = sys ? 'the connectors on this distro\'s face'
            : 'pick a system first';
        capRow.appendChild(sub);
        sec.appendChild(capRow);
        if (!sys) { wrap.appendChild(sec); return; }
        const rows = this.distroRows(d);
        const commit = (next) => patch({ outputRows: next });
        const total = (r) => r.count * this.distroConnector(r.connector).circuits;
        rows.forEach((r, i) => {
            const line = document.createElement('div');
            line.className = 'hw-pop-row';
            line.dataset.lrdRow = r.id;
            const conn = document.createElement('select');
            conn.className = 'info-select hw-pop-row-conn';
            conn.dataset.lrdField = `distro-row-conn-${d.id}-${r.id}`;
            DISTRO_CONNECTORS.forEach(c => {
                if (!this.connectorCouplings(c, sys).length) return;
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name;
                if (c.id === r.connector) opt.selected = true;
                conn.appendChild(opt);
            });
            conn.addEventListener('change', () => {
                const next = rows.map(x => ({ ...x }));
                next[i].connector = conn.value;
                commit(next);
            });
            line.appendChild(conn);
            const count = document.createElement('input');
            count.type = 'number';
            count.min = '1';
            count.max = '99';
            count.value = r.count;
            count.style.width = '44px';
            count.dataset.lrdField = `distro-row-count-${d.id}-${r.id}`;
            count.title = r.connector === 'edison'
                ? 'How many receptacles - each receptacle of a duplex is its own circuit.'
                : 'How many of this connector the face carries.';
            count.addEventListener('change', () => {
                const next = rows.map(x => ({ ...x }));
                next[i].count = count.value;
                commit(next);
            });
            line.appendChild(count);
            const offered = this.connectorCouplings(this.distroConnector(r.connector), sys);
            if (offered.length > 1) {
                const cp = document.createElement('select');
                cp.className = 'info-select';
                cp.dataset.lrdField = `distro-row-coupling-${d.id}-${r.id}`;
                cp.title = 'Line-to-neutral (one hot and the neutral) or line-to-line (two hots).';
                offered.forEach(o => {
                    const opt = document.createElement('option');
                    opt.value = o.coupling;
                    opt.textContent = `${o.volts}V`;
                    if (o.coupling === r.coupling) opt.selected = true;
                    cp.appendChild(opt);
                });
                cp.addEventListener('change', () => {
                    const next = rows.map(x => ({ ...x }));
                    next[i].coupling = cp.value;
                    commit(next);
                });
                line.appendChild(cp);
            } else {
                const v = document.createElement('small');
                v.textContent = `${offered[0].volts}V`;
                v.style.color = 'var(--ps-faint, #969696)';
                line.appendChild(v);
            }
            const brk = document.createElement('input');
            brk.type = 'number';
            brk.min = '1';
            brk.value = r.breakerA;
            brk.style.width = '44px';
            brk.dataset.lrdField = `distro-row-breaker-${d.id}-${r.id}`;
            brk.title = 'The breaker on each of this row\'s circuits, in amps.';
            brk.disabled = !!r.pairedWith;
            brk.addEventListener('change', () => {
                const next = rows.map(x => ({ ...x }));
                next[i].breakerA = brk.value;
                commit(next);
            });
            line.appendChild(brk);
            const a = document.createElement('small');
            a.textContent = 'A';
            a.style.color = 'var(--ps-faint, #969696)';
            line.appendChild(a);
            // The connector's own rating on a direct row (2026-10-18): its
            // default for the region as the placeholder, a typed figure
            // overriding it, blank back to the default. The connector check
            // reads it (faceConnectorRatingA).
            const rconn = this.distroConnector(r.connector);
            if (rconn && rconn.kind === 'direct') {
                const dflt = this.connectorRatingA(rconn, sys.region);
                const rl = document.createElement('small');
                rl.textContent = 'rated';
                rl.style.color = 'var(--ps-faint, #969696)';
                line.appendChild(rl);
                const ca = document.createElement('input');
                ca.type = 'number';
                ca.min = '1';
                ca.value = r.connectorA != null ? r.connectorA : '';
                ca.placeholder = dflt != null ? String(dflt) : '';
                ca.style.width = '44px';
                ca.dataset.lrdField = `distro-row-connector-a-${d.id}-${r.id}`;
                ca.title = `The rating of each ${rconn.short} on this row, in amps. `
                    + (dflt != null ? `Blank is the default, ${dflt} A here. ` : 'Blank is no rating. ')
                    + 'Type a figure to override it.';
                ca.addEventListener('change', () => {
                    const next = rows.map(x => ({ ...x }));
                    next[i].connectorA = ca.value === '' ? null : ca.value;
                    commit(next);
                });
                line.appendChild(ca);
                const a2 = document.createElement('small');
                a2.textContent = 'A';
                a2.style.color = 'var(--ps-faint, #969696)';
                line.appendChild(a2);
            }
            // Paired with: rows of the same circuits and coupling, unpaired.
            const partners = rows.filter(x => x.id !== r.id && !x.pairedWith
                && total(x) === total(r) && x.coupling === r.coupling
                && !rows.some(y => y.pairedWith === r.id));
            if (partners.length || r.pairedWith) {
                const pw = document.createElement('select');
                pw.className = 'info-select';
                pw.dataset.lrdField = `distro-row-paired-${d.id}-${r.id}`;
                pw.title = 'Paired: the same circuits on a second set of connectors - '
                    + 'they count once, and a circuit can be patched to either, not both.';
                const noneOpt = document.createElement('option');
                noneOpt.value = '';
                noneOpt.textContent = 'not paired';
                pw.appendChild(noneOpt);
                partners.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p.id;
                    opt.textContent = `paired with ${p.count} × ${this.distroConnector(p.connector).short}`;
                    if (r.pairedWith === p.id) opt.selected = true;
                    pw.appendChild(opt);
                });
                pw.addEventListener('change', () => {
                    const next = rows.map(x => ({ ...x }));
                    next[i].pairedWith = pw.value || null;
                    commit(next);
                });
                line.appendChild(pw);
            }
            const del = document.createElement('button');
            del.className = 'btn hw-dock-btn';
            del.textContent = '✕';
            del.title = 'Remove this row.';
            del.dataset.lrdField = `distro-row-del-${d.id}-${r.id}`;
            del.addEventListener('click', () => {
                commit(rows.filter(x => x.id !== r.id)
                    .map(x => ({ ...x, pairedWith: x.pairedWith === r.id ? null : x.pairedWith })));
            });
            line.appendChild(del);
            sec.appendChild(line);
        });
        const actions = document.createElement('div');
        actions.className = 'hw-pop-row hw-pop-row-actions';
        const add = document.createElement('button');
        add.className = 'btn hw-dock-btn';
        add.textContent = '+ Add output';
        add.dataset.lrdField = `distro-row-add-${d.id}`;
        add.title = 'Add a row of connectors to this distro\'s face.';
        add.addEventListener('click', () => {
            const first = DISTRO_CONNECTORS.find(c => this.connectorCouplings(c, sys).length);
            const offered = this.connectorCouplings(first, sys);
            const pickLL = offered.find(o => o.coupling === 'll');
            commit([...rows.map(x => ({ ...x })),
                    { connector: first.id, count: 1,
                      coupling: (pickLL || offered[0]).coupling,
                      breakerA: DEFAULT_BREAKER[sys.region] }]);
        });
        actions.appendChild(add);
        sec.appendChild(actions);

        // Presets: the eleven built in, then the saved ones; picking one
        // lays it on this distro (one undo step).
        const pr = document.createElement('div');
        pr.className = 'hw-pop-row hw-pop-row-actions';
        const ps = document.createElement('select');
        ps.className = 'info-select';
        ps.dataset.lrdField = `distro-preset-${d.id}`;
        ps.title = 'Start from a preset: it sets the system, input, rating '
            + 'and rows. One undo step.';
        const fill = (custom) => {
            ps.innerHTML = '';
            const head = document.createElement('option');
            head.value = '';
            head.textContent = 'Start from a preset…';
            ps.appendChild(head);
            const gb = document.createElement('optgroup');
            gb.label = 'Presets';
            DISTRO_PRESETS.forEach(p => {
                const opt = document.createElement('option');
                opt.value = `b:${p.id}`;
                opt.textContent = p.name;
                gb.appendChild(opt);
            });
            ps.appendChild(gb);
            if (custom && custom.length) {
                const gc = document.createElement('optgroup');
                gc.label = 'Saved';
                custom.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = `c:${p.name}`;
                    opt.textContent = p.name;
                    gc.appendChild(opt);
                });
                ps.appendChild(gc);
            }
        };
        // The popover can be rebuilt while a request is out (any dock
        // render does it); a reply then lands on the rebuilt one, which
        // reads the list just cached, not on these detached lists.
        const relist = (list) => {
            if (ps.isConnected) {
                fill(list);
                fillDelete(list);
            } else if (this._hwPopoverRefresh) {
                this._hwPopoverRefresh();
            }
        };
        fill(this._customDistroPresets || []);
        if (!this._customDistroPresets) {
            this.loadCustomDistroPresets().then(relist);
        }
        ps.addEventListener('change', () => {
            const v = ps.value;
            if (!v) return;
            const preset = v.startsWith('b:')
                ? DISTRO_PRESETS.find(p => `b:${p.id}` === v)
                : (this._customDistroPresets || []).find(p => `c:${p.name}` === v);
            if (preset) {
                this.applyDistroPreset(d.id, preset);
                this._restateNaming();
            }
        });
        pr.appendChild(ps);
        const save = document.createElement('button');
        save.className = 'btn hw-dock-btn';
        save.textContent = 'Save as preset…';
        save.dataset.lrdField = `distro-preset-save-${d.id}`;
        save.title = 'Save this distro\'s system, input, rating and rows as a preset '
            + 'everyone connected can pick.';
        save.disabled = !rows.length;
        save.addEventListener('click', () => {
            const name = window.prompt('Name this preset', d.name || '');
            if (!name || !name.trim()) return;
            this.saveDistroPreset(d.id, name).then(list => {
                relist(list);
                this._dockSay && this._dockSay(`Saved preset "${name.trim()}".`);
            }).catch(err => this._dockSay && this._dockSay(String(err.message || err)));
        });
        pr.appendChild(save);
        sec.appendChild(pr);

        // Deleting a saved preset (the built-in ones cannot be): a list of
        // the saved ones only, shown while there are any; picking one asks
        // first. Distros already laid from it keep their outputs.
        const dr = document.createElement('div');
        dr.className = 'hw-pop-row hw-pop-row-actions';
        const del = document.createElement('select');
        del.className = 'info-select';
        del.dataset.lrdField = `distro-preset-delete-${d.id}`;
        del.title = 'Delete a saved preset for everyone connected. '
            + 'Distros already set from it keep their outputs.';
        const fillDelete = (custom) => {
            del.innerHTML = '';
            const head = document.createElement('option');
            head.value = '';
            head.textContent = 'Delete a saved preset…';
            del.appendChild(head);
            (custom || []).forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.name;
                opt.textContent = p.name;
                del.appendChild(opt);
            });
            dr.style.display = custom && custom.length ? '' : 'none';
        };
        fillDelete(this._customDistroPresets || []);
        del.addEventListener('change', () => {
            const name = del.value;
            del.value = '';
            if (!name) return;
            if (!window.confirm(`Delete the preset "${name}"? `
                    + 'Distros already set from it keep their outputs.')) return;
            this.deleteDistroPreset(name).then(list => {
                relist(list);
                this._dockSay && this._dockSay(`Deleted preset "${name}".`);
            }).catch(err => this._dockSay && this._dockSay(String(err.message || err)));
        });
        dr.appendChild(del);
        sec.appendChild(dr);
        wrap.appendChild(sec);
    }
}

for (const k of Object.getOwnPropertyNames(_DistroSystems.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_DistroSystems.prototype, k));
    }
}
