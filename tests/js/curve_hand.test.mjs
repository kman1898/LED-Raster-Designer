// The Header/Footer tab's Curve laid by hand (owner, 2026-11-18: "i need
// to be able to do custom curve just like header"): bars laid with Custom
// stay as they are and the Curve fits the angles to them, bending only
// where no bar runs across; a joint set by hand keeps its angle and the
// Curve fills in the rest; a hand choice the wall cannot take is refused in
// plain words (curve-math.js screenCurve `hand`). Run by
// tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import { cleanCurve, CURVE_DEFAULTS, screenCurve } from '../../src/static/js/curve-math.js';

const on = (over = {}) => ({ ...CURVE_DEFAULTS, on: true, ...over });
const LOCKS = [-10, -7.5, -5, -2.5, 0, 2.5, 5, 7.5, 10];
const wall = (hand, over = {}, panels = 12, extra = {}) => screenCurve({
    panels, panelWidthM: 0.5, sizes: [1, 2], settings: on({ value: 10, ...over }), locks: LOCKS, hand, ...extra });
const inside = (bars, j) => bars.some((b) => b.start <= j && j + 1 < b.start + b.size);

describe('bars laid by hand', () => {
    const bars = [{ start: 0, size: 2 }, { start: 2, size: 2 }, { start: 4, size: 1 }, { start: 5, size: 2 },
                  { start: 7, size: 1 }, { start: 8, size: 2 }, { start: 10, size: 2 }];
    const out = wall({ bars, joints: {} });
    it('are laid as they are, the answer marked as laid by hand', () => {
        expect(out.errors).toEqual([]);
        expect(out.hand).toBe(true);
        expect(out.bars).toEqual(bars.map((b) => b.size));
        expect(out.starts).toEqual(bars.map((b) => b.start));
    });
    it('bend only where no bar runs across, and curve the wall', () => {
        out.joints.forEach((a, j) => { if (inside(bars, j)) expect(a).toBe(0); });
        expect(out.joints.some((a) => a > 0)).toBe(true);
        expect(out.result.achieved.sweep_deg > 0).toBe(true);
    });
    it('only at the panel\'s lock positions, never past 20 degrees', () => {
        out.joints.forEach((a) => expect([0, 2.5, 5, 7.5, 10].includes(a)).toBe(true));
    });
    it('a gap under no bar is a run of its own: its joints may bend', () => {
        const gap = [{ start: 0, size: 2 }, { start: 4, size: 2 }];
        const g = wall({ bars: gap, joints: {} }, {}, 6);
        expect(g.errors).toEqual([]);
        expect(g.starts).toEqual([0, 4]);
        expect(g.joints[0]).toBe(0);
        expect(g.joints[4]).toBe(0);
    });
    it('without a hand, the Curve lays its own bars as ever', () => {
        const own = wall(undefined);
        expect(own.hand).toBe(undefined);
        expect(own.bars.reduce((s, k) => s + k, 0)).toBe(12);
    });
    it('a convex wall bends the other way', () => {
        const cx = wall({ bars, joints: {} }, { bend: 'convex' });
        cx.joints.forEach((a) => expect(a <= 0).toBe(true));
        expect(cx.joints.some((a) => a < 0)).toBe(true);
    });
});

describe('joints set by hand', () => {
    const singles = Array.from({ length: 12 }, (_, i) => ({ start: i, size: 1 }));
    it('keep their angle and the Curve fills in the rest', () => {
        const free = wall({ bars: singles, joints: {} });
        const j = free.joints.findIndex((a) => a === 0);
        const out = wall({ bars: singles, joints: { [j]: 7.5, 0: 0 } });
        expect(out.errors).toEqual([]);
        expect(out.joints[j]).toBe(7.5);
        expect(out.joints[0]).toBe(0);
        expect(out.joints.filter((a, i) => i !== j && i !== 0 && a > 0).length > 0).toBe(true);
    });
    it('built from either end or a point, the pin holds', () => {
        for (const from of ['left', 'right', 4.5, 7]) {
            const out = wall({ bars: singles, joints: { 5: 10 } }, { from });
            expect(out.errors).toEqual([]);
            expect(out.joints[5]).toBe(10);
        }
    });
    it('are refused at an angle the panel does not lock at, in plain words', () => {
        const out = wall({ bars: singles, joints: { 3: 6 } });
        expect(out.joints).toEqual([]);
        expect(out.errors[0]).toBe('The joint after panel 4 is set by hand to +6°, and this panel does not lock there for a concave curve. Pick another angle for it, or press Auto.');
    });
    it('are refused bending the wrong way for the curve', () => {
        const out = wall({ bars: singles, joints: { 3: -5 } });
        expect(out.errors[0]).toContain('does not lock there for a concave curve');
    });
    it('are refused bending under a bar, naming the bar', () => {
        const out = wall({ bars: [{ start: 0, size: 2 }, ...singles.slice(2)], joints: { 0: 5 } });
        expect(out.errors).toEqual(['The joint after panel 1 is set by hand to +5°, but the bar over panels 1 to 2 holds it straight. Move the bar, or set the joint flat.']);
    });
    it('flat under a bar is fine', () => {
        const out = wall({ bars: [{ start: 0, size: 2 }, ...singles.slice(2)], joints: { 0: 0 } });
        expect(out.errors).toEqual([]);
    });
});

describe('a wall with a corner, laid by hand', () => {
    const pieces = [{ start: 5, size: 2 }];
    const bars = [{ start: 0, size: 2 }, { start: 2, size: 2 }, { start: 4, size: 1 },
                  { start: 7, size: 1 }, { start: 8, size: 2 }, { start: 10, size: 2 }];
    it('keeps the hand\'s bars beside the corner and its pins', () => {
        const out = wall({ bars, joints: { 1: 5 } }, {}, 12, { pieces });
        expect(out.errors).toEqual([]);
        expect(out.hand).toBe(true);
        expect(out.placed.filter((b) => !b.corner).map((b) => [b.start, b.size])).toEqual(bars.map((b) => [b.start, b.size]));
        expect(out.joints[1]).toBe(5);
        expect(out.joints[0]).toBe(0);
    });
    it('refuses a hand bar on the corner\'s panels', () => {
        const out = wall({ bars: [...bars.slice(0, 2), { start: 4, size: 2 }, ...bars.slice(3)], joints: {} }, {}, 12, { pieces });
        expect(out.errors).toEqual(['The bar over panels 5 to 6 runs onto a corner\'s panels. Move it off the corner, or press Auto.']);
    });
});

describe('the joints set by hand are kept with the Curve', () => {
    it('cleanCurve keeps them, signed, and drops what is not a joint', () => {
        const c = cleanCurve({ on: true, handJoints: { 3: 5, 10: -2.5, x: 5, 4: 'a', 5: 99, 6: true } });
        expect(c.handJoints).toEqual({ 3: 5, 10: -2.5 });
    });
    it('none, none kept', () => {
        expect('handJoints' in cleanCurve({ on: true, handJoints: {} })).toBe(false);
        expect('handJoints' in cleanCurve({ on: true })).toBe(false);
    });
});

describe('a joint set by hand: every build in Ways to build it has its own id', () => {
    // (review, 2026-11-24) the 5 degree build took the hand joint's 2.5
    // and was named "2.5+5" like the build that uses both, and the tab
    // said "in use" on both rows.
    const bars = Array.from({ length: 16 }, (_, i) => ({ start: i, size: 1 }));
    const out = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1, 2], locks: [-5, -2.5, 0, 2.5, 5],
                              settings: on({ value: 20, handJoints: { 3: 2.5 } }), hand: { bars, joints: { 3: 2.5 } } });
    const ids = out.result.options.map((o) => o.id);
    it('names no two builds alike', () => {
        expect(out.errors).toEqual([]);
        expect(new Set(ids).size).toBe(ids.length);
    });
    it('marks exactly one build as the one laid, and it is the one laid', () => {
        const used = out.result.options.filter((o) => o.id === out.result.chosen_option_id);
        expect(used).toHaveLength(1);
        expect(used[0].joints).toEqual(out.result.joints.map((j) => j.angle_deg));
    });
    it('keeps the name for the best of two builds using the same angles, the other numbered', () => {
        const same = out.result.options.filter((o) => o.used_angles_deg.join('+') === '2.5+5');
        expect(same.length >= 2).toBe(true);
        expect(same[0].id).toBe('2.5+5');
        expect(same[1].id).toBe('2.5+5 #2');
    });
    it('a pick of the numbered build lays it', () => {
        const other = out.result.options.find((o) => o.id === '2.5+5 #2');
        const key = out.pickKey;
        const picked = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1, 2], locks: [-5, -2.5, 0, 2.5, 5],
                                     settings: on({ value: 20, handJoints: { 3: 2.5 }, pick: { id: other.id, key } }),
                                     hand: { bars, joints: { 3: 2.5 } } });
        expect(picked.result.chosen_option_id).toBe('2.5+5 #2');
        expect(picked.joints).toEqual(other.joints);
    });
});

report();
