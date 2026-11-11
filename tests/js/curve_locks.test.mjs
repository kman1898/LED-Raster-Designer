// A panel's lock positions (owner, 2026-11-10): the Curve lays only the
// angles the panel's curve locks set at, a fixed list per panel, never a
// range. curve-math.js cleanLocks, locksForBend, parseLocks, formatLock,
// ownerCurveLocks and screenCurve's `locks`. Run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import {
    cleanLocks, CURVE_DEFAULTS, formatLock, hasLockPositions, locksForBend, NO_LOCKS_MESSAGE,
    ownerCurveLocks, parseLocks, screenCurve,
} from '../../src/static/js/curve-math.js';

const on = (over = {}) => ({ ...CURVE_DEFAULTS, on: true, ...over });
const GRAPHITE = [-5, 0, 5];

describe('a list of lock positions', () => {
    it('is held to its shape: sorted, each once, flat always on it', () => {
        expect(cleanLocks([5, -5, 5, '2.5'])).toEqual([-5, 0, 2.5, 5]);
        expect(cleanLocks([])).toEqual([0]);
        expect(cleanLocks(null)).toBe(null);
        expect(cleanLocks('5')).toBe(null);
    });
    it('drops anything past 20 degrees either way, and anything not a number', () => {
        expect(cleanLocks([25, -21, 20, -20, 'x', null, true, NaN])).toEqual([-20, 0, 20]);
    });
    it('flat alone curves nothing', () => {
        expect(hasLockPositions([0])).toBe(false);
        expect(hasLockPositions(GRAPHITE)).toBe(true);
        expect(hasLockPositions(null)).toBe(false);
    });
    it('splits by bend: concave the positive ones, convex the negative, as sizes', () => {
        expect(locksForBend([-7.5, -5, 0, 2.5, 5], 'concave')).toEqual([2.5, 5]);
        expect(locksForBend([-7.5, -5, 0, 2.5, 5], 'convex')).toEqual([5, 7.5]);
        expect(locksForBend([0, 5], 'convex')).toEqual([]);
    });
    it('reads typed positions, signs kept', () => {
        expect(parseLocks('-5, 0, +5')).toEqual([-5, 0, 5]);
        expect(parseLocks('−2.5 7.5')).toEqual([-2.5, 7.5]);
        expect(parseLocks('none')).toBe(null);
    });
    it('reads as chips: -5°, 0°, +5°', () => {
        expect(GRAPHITE.map(formatLock)).toEqual(['-5°', '0°', '+5°']);
    });
});

describe('the owner list', () => {
    it('gives every ROE Graphite full and half tile -5, 0 and +5', () => {
        for (const name of ['Graphite GP2.6 (4 in 1) Full Tile', 'Graphite GP2.6 (4 in 1) Half Tile',
                            'Graphite GP3.9 Full Tile', 'Graphite GP1.9 (4 in 1) Half Tile']) {
            expect(ownerCurveLocks('ROE', name)).toEqual(GRAPHITE);
        }
    });
    it('gives nothing to another maker, another ROE panel, or a Graphite corner', () => {
        expect(ownerCurveLocks('Absen', 'Graphite GP2.6 Full Tile')).toBe(null);
        expect(ownerCurveLocks('ROE', 'Black Pearl BP2V2')).toBe(null);
        expect(ownerCurveLocks('ROE', 'Graphite GP2.6 Right Angle')).toBe(null);
    });
});

describe('a Graphite wall: sixteen 500 mm panels, singles lit', () => {
    const wall = (over, locks = GRAPHITE) => screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1], settings: on(over), locks });
    it('lays only -5, 0 and +5 at its joints', () => {
        for (const value of [5, 10, 20, 30]) {
            for (const bend of ['concave', 'convex']) {
                const out = wall({ value, bend });
                expect(out.errors).toEqual([]);
                out.joints.forEach((a) => expect(GRAPHITE).toContain(a));
            }
        }
    });
    it('concave bends +5, convex -5', () => {
        const cc = wall({ value: 20 }).joints.filter((a) => a);
        const cx = wall({ value: 20, bend: 'convex' }).joints.filter((a) => a);
        expect(cc.length > 0 && cc.every((a) => a === 5)).toBe(true);
        expect(cx.length > 0 && cx.every((a) => a === -5)).toBe(true);
    });
    it('offers only 5 degree builds in Ways to build it, whatever the settings angles say', () => {
        for (const goal of ['simplest', 'even', 'tightest']) {
            const out = wall({ value: 20, goal, angles: [2.5, 7.5, 10] });
            expect(out.result.options.length > 0).toBe(true);
            out.result.options.forEach((o) => {
                o.used_angles_deg.forEach((a) => expect(a).toBe(5));
                o.joints.forEach((a) => expect([0, 5]).toContain(a));
            });
        }
    });
    it('a curve past what +5 can reach falls short and says so, never a bigger angle', () => {
        const out = wall({ value: 40 });
        expect(out.errors).toEqual([]);
        out.joints.forEach((a) => expect([0, 5]).toContain(a));
        expect(out.warnings.some((w) => w.includes('Out of range'))).toBe(true);
    });
    it('with doubles lit, the joints a bar holds rigid stay flat and the rest are +5 or flat', () => {
        const out = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [2], settings: on({ value: 10 }), locks: GRAPHITE });
        expect(out.bars).toEqual(new Array(8).fill(2));
        out.joints.forEach((a, i) => { if (i % 2 === 0) expect(a).toBe(0); else expect([0, 5]).toContain(a); });
    });
    it('around a corner, each side lays only +5 or flat', () => {
        const out = screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [1], settings: on({ value: 10 }), locks: GRAPHITE,
                                  pieces: [{ start: 5, size: 2 }] });
        expect(out.errors).toEqual([]);
        out.joints.forEach((a) => expect([0, 5]).toContain(a));
        out.sides.forEach((sd) => (sd.out.result ? sd.out.result.options : []).forEach((o) =>
            o.used_angles_deg.forEach((a) => expect(a).toBe(5))));
    });
});

describe('a panel with no lock positions', () => {
    const solve = (locks, over = {}) => screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1], settings: on(over), locks });
    it('is refused and says so, nothing laid', () => {
        for (const locks of [null, [], [0]]) {
            const out = solve(locks);
            expect(out.errors).toEqual([NO_LOCKS_MESSAGE]);
            expect(out.bars).toEqual([]);
            expect(out.joints).toEqual([]);
            expect(out.result).toBe(null);
        }
        expect(NO_LOCKS_MESSAGE).toBe('This panel has no curve lock positions yet. Set them to curve this screen.');
    });
    it('a list that bends only one way refuses the other, saying which', () => {
        const out = solve([0, 5], { bend: 'convex' });
        expect(out.errors).toEqual(['This panel has no convex lock positions. Pick Concave, or add convex positions with Edit.']);
        expect(solve([0, 5]).errors).toEqual([]);
    });
});

describe('the list is part of what a pick was made against', () => {
    it('a pick made with one list goes back to the app\'s own when the list changes', () => {
        const a = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1], settings: on(), locks: [-5, 0, 5] });
        const b = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1], settings: on(), locks: [-7.5, -5, 0, 5, 7.5] });
        expect(a.pickKey === b.pickKey).toBe(false);
        b.joints.forEach((x) => expect([0, 5, 7.5]).toContain(x));
    });
});

// QA, 2026-11-10: twelve Graphite panels, singles and doubles lit, 10%
// concave. The Curve lays singles with two doubles, no two doubles side by
// side, and builds 10.1% against 10% asked for; the warning said the curve
// wants 6 a joint against the locks' 5 and the wall would fall short,
// reading the per-joint angle off the widest bar alone.
describe('Out of range is said only when the build falls short', () => {
    const twelve = (over) => screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [1, 2], settings: on(over),
                                           locks: GRAPHITE, system: 'imperial' });
    it('10% on twelve panels: no joint wants over 4.5, no Out of range, no "fall short"', () => {
        const out = twelve({ value: 10 });
        expect(out.errors).toEqual([]);
        // no two doubles touch, so the hardest joint is a single beside a double
        for (let i = 1; i < out.bars.length; i++) expect(out.bars[i] + out.bars[i - 1] < 4).toBe(true);
        expect(out.result.ideal_angle_deg).toBeCloseTo(4.5, 9);
        expect(out.result.achieved.sweep_deg >= out.result.target.sweep_deg - 1e-6).toBe(true);
        expect(out.warnings.some((w) => w.includes('Out of range'))).toBe(false);
        expect(out.warnings.some((w) => w.includes('fall short') || w.includes('falls short'))).toBe(false);
    });
    it('a curve past what +5 reaches still says Out of range', () => {
        const out = twelve({ value: 30 });
        expect(out.result.achieved.sweep_deg < out.result.target.sweep_deg).toBe(true);
        expect(out.warnings.some((w) => w.includes('Out of range'))).toBe(true);
    });
});

report();
