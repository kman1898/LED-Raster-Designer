// The Header/Footer tab's Curve: a screen's settings in, the bars and the
// signed column-joint angles out (curve-math.js screenCurve, cleanCurve,
// parseAngles). Run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import { cleanCurve, CURVE_DEFAULTS, parseAngles, screenCurve } from '../../src/static/js/curve-math.js';

const on = (over = {}) => ({ ...CURVE_DEFAULTS, on: true, ...over });

describe('a screen of sixteen 500 mm panels at 20%, singles lit', () => {
    const out = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1], settings: on() });
    it('is the calculator headline case: nine 7.5 degree joints, six flat', () => {
        expect(out.errors).toEqual([]);
        expect(out.joints).toHaveLength(15);
        expect(out.joints.filter((a) => a === 7.5)).toHaveLength(9);
        expect(out.joints.filter((a) => a === 0)).toHaveLength(6);
        expect(out.result.max_arc_deviation_m * 1000).toBeCloseTo(13.6, 1);
    });
    it('lays a single under every panel', () => {
        expect(out.bars).toEqual(new Array(16).fill(1));
    });
    it('turns convex into negative angles, the same size', () => {
        const cx = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1], settings: on({ bend: 'convex' }) });
        expect(cx.joints).toEqual(out.joints.map((a) => (a === 0 ? 0 : -a)));
        expect(cx.result.achieved.chord_m).toBeCloseTo(out.result.achieved.chord_m, 9);
    });
    it('reads 72 degrees of sweep as the same wall', () => {
        const d = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1], settings: on({ entry: 'degrees', value: 72 }) });
        expect(d.joints).toEqual(out.joints);
    });
});

describe('the lit sizes are the stock', () => {
    it('doubles only: eight doubles, and only the joints between them bend', () => {
        const out = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [2], settings: on() });
        expect(out.bars).toEqual(new Array(8).fill(2));
        out.joints.forEach((a, i) => { if (i % 2 === 0) expect(a).toBe(0); });
        expect(out.joints.some((a) => a !== 0)).toBe(true);
    });
    it('singles and doubles: the bars tile the wall, and no bend sits inside a bar', () => {
        const out = screenCurve({ panels: 15, panelWidthM: 0.5, sizes: [1, 2], settings: on({ entry: 'degrees', value: 25, angles: [5] }) });
        expect(out.bars.reduce((s, n) => s + n, 0)).toBe(15);
        const inside = new Set();
        let at = 0;
        for (const n of out.bars) { for (let k = 1; k < n; k++) inside.add(at + k - 1); at += n; }
        out.joints.forEach((a, i) => { if (inside.has(i)) expect(a).toBe(0); });
    });
    it('none lit: an error, and nothing laid', () => {
        const out = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [], settings: on() });
        expect(out.errors).toContain('Light at least one bar size.');
        expect(out.bars).toEqual([]);
        expect(out.joints).toEqual([]);
    });
    it('a stock that cannot cover the wall keeps the last bar whole and says so', () => {
        const out = screenCurve({ panels: 15, panelWidthM: 0.5, sizes: [2], settings: on() });
        expect(out.bars.reduce((s, n) => s + n, 0)).toBe(16);
        expect(out.warnings.join(' ')).toContain('The wall runs out before the last bar is full');
    });
});

describe('errors, not garbage', () => {
    it('a one-panel screen is refused', () => {
        const out = screenCurve({ panels: 1, panelWidthM: 0.5, sizes: [1], settings: on() });
        expect(out.errors).toContain('A curve needs at least 2 panels across.');
    });
    it('a lock angle of 90 or more is refused', () => {
        const out = screenCurve({ panels: 8, panelWidthM: 0.5, sizes: [1], settings: on({ angles: [95] }) });
        expect(out.errors).toContain('Lock angles must be under 90°.');
    });
    it('a flat wall reads straight, an infinite radius', () => {
        const out = screenCurve({ panels: 8, panelWidthM: 0.5, sizes: [1], settings: on({ value: 0 }) });
        expect(out.result.achieved.radius_face_m).toBe(Infinity);
        expect(out.joints.every((a) => a === 0)).toBe(true);
    });
});

describe('cleanCurve and parseAngles', () => {
    it('fills every field of a missing block with the defaults, off', () => {
        expect(cleanCurve(null)).toEqual({ ...CURVE_DEFAULTS, angles: [2.5, 5, 7.5, 10] });
        expect(cleanCurve(undefined).on).toBe(false);
    });
    it('coerces junk field by field', () => {
        const c = cleanCurve({ on: 'yes', entry: 'x', value: '30', bend: 'convex', goal: 'even',
                               toleranceMm: -4, angles: [5, '2.5', 0, 'x', 5], from: 'left' });
        expect(c).toEqual({ on: false, entry: 'percent', value: 30, bend: 'convex', goal: 'even',
                            toleranceMm: 0, angles: [2.5, 5], from: 'left' });
    });
    it('reads an angle list however it is typed', () => {
        expect(parseAngles('2.5, 5, 7.5 10')).toEqual([2.5, 5, 7.5, 10]);
        expect(parseAngles('10° 5°')).toEqual([5, 10]);
        expect(parseAngles('5, x')).toBe(null);
        expect(parseAngles('')).toBe(null);
    });
});

report();
