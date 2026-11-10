// The Header/Footer tab's Curve: a screen's settings in, the bars and the
// signed column-joint angles out (curve-math.js screenCurve, cleanCurve,
// parseAngles). Run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import { cleanCurve, CURVE_DEFAULTS, curvePickKey, curveSides, faceRadiusForAngle, parseAngles, screenCurve, sideName, solveCurve, makeCurve, stockCovers } from '../../src/static/js/curve-math.js';

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
    it('a stock that cannot cover the wall exactly lays nothing and names the gap', () => {
        const out = screenCurve({ panels: 15, panelWidthM: 0.5, sizes: [2], settings: on() });
        expect(out.errors).toEqual(['These bar sizes leave 1 panel uncovered on a 15-panel wall. Light another size.']);
        expect(out.bars).toEqual([]);
        expect(out.joints).toEqual([]);
        expect(out.result).toBe(null);
        const big = screenCurve({ panels: 7, panelWidthM: 0.5, sizes: [4], settings: on() });
        expect(big.errors).toEqual(['These bar sizes leave 3 panels uncovered on a 7-panel wall. Light another size.']);
    });
    it('stockCovers is the most panels the sizes cover exactly', () => {
        expect(stockCovers(15, [2])).toBe(14);
        expect(stockCovers(15, [2, 3])).toBe(15);
        expect(stockCovers(5, [4])).toBe(4);
        expect(stockCovers(3, [4])).toBe(0);
    });
});

describe('the datum, anywhere along the wall', () => {
    it('a panel middle or a joint, in half steps, as the calculator snaps it', () => {
        const at = (from) => screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1], settings: on({ from }) });
        expect(at(8.5).joints).toEqual(at('center').joints);
        expect(at(0.5).joints).toEqual(at('left').joints);
        expect(at(16.5).joints).toEqual(at('right').joints);
        expect(at(4).result.datum_at).toBe(4);
        expect(at(5.5).result.datum_at).toBe(5.5);
        // the calculator's own answer for the same datum
        const c = makeCurve(); c.build_from = 4;
        expect(at(4).joints).toEqual(solveCurve(c).joints.map((j) => j.angle_deg));
    });
    it('cleanCurve keeps a datum as a half step, and a word as a word', () => {
        expect(cleanCurve({ from: 8.4 }).from).toBe(8.5);
        expect(cleanCurve({ from: 3 }).from).toBe(3);
        expect(cleanCurve({ from: 'left' }).from).toBe('left');
        expect(cleanCurve({ from: -2 }).from).toBe('center');
        expect(cleanCurve({ from: 'x' }).from).toBe('center');
    });
});

describe('ways to build it, and a pick by hand', () => {
    const input = (over = {}) => ({ panels: 16, panelWidthM: 0.5, sizes: [1], settings: on(over) });
    it('lists every candidate, the closest and the closest even among them', () => {
        const out = screenCurve(input());
        const ids = out.result.options.map((o) => o.id);
        expect(ids[0]).toBe('7.5');
        expect(ids).toContain('2.5+7.5');
        expect(out.result.options.some((o) => o.even)).toBe(true);
    });
    it('a pick holds while nothing the joints depend on changes', () => {
        const key = curvePickKey(input());
        const out = screenCurve(input({ pick: { id: '2.5+7.5', key } }));
        expect(out.result.chosen_option_id).toBe('2.5+7.5');
        expect(out.result.recommended_option_id).toBe('7.5');
        expect(out.result.choice_reason).toMatch(/^Your pick/);
        // the datum does not reset it, as in the calculator
        expect(screenCurve(input({ from: 'left', pick: { id: '2.5+7.5', key } })).result.chosen_option_id).toBe('2.5+7.5');
    });
    it('and goes back to the app when the curve, the stock or the wall changes', () => {
        const key = curvePickKey(input());
        const pick = { id: '2.5+7.5', key };
        expect(screenCurve(input({ value: 25, pick })).result.chosen_option_id).not.toBe('2.5+7.5');
        expect(screenCurve({ ...input({ pick }), sizes: [1, 2] }).result.config.pattern_choice).toBe('auto');
        expect(screenCurve({ ...input({ pick }), panels: 14 }).result.config.pattern_choice).toBe('auto');
        expect(screenCurve(input({ goal: 'tightest', pick })).result.config.pattern_choice).toBe('auto');
    });
    it('cleanCurve keeps a pick only in its shape', () => {
        expect(cleanCurve({ pick: { id: '5', key: 'k' } }).pick).toEqual({ id: '5', key: 'k' });
        expect(cleanCurve({ pick: '5' }).pick).toBe(null);
        expect(cleanCurve({}).pick).toBe(null);
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
        expect(cleanCurve(null).pick).toBe(null);
        expect(cleanCurve(undefined).on).toBe(false);
    });
    it('coerces junk field by field', () => {
        const c = cleanCurve({ on: 'yes', entry: 'x', value: '30', bend: 'convex', goal: 'even',
                               toleranceMm: -4, angles: [5, '2.5', 0, 'x', 5], from: 'left' });
        expect(c).toEqual({ on: false, entry: 'percent', value: 30, bend: 'convex', goal: 'even',
                            toleranceMm: 0, angles: [2.5, 5], from: 'left', pick: null });
    });
    it('reads an angle list however it is typed', () => {
        expect(parseAngles('2.5, 5, 7.5 10')).toEqual([2.5, 5, 7.5, 10]);
        expect(parseAngles('10° 5°')).toEqual([5, 10]);
        expect(parseAngles('5, x')).toEqual([5]);
        expect(parseAngles('5 deg, 10 degrees')).toEqual([5, 10]);
        expect(parseAngles('none')).toBe(null);
        expect(parseAngles('')).toBe(null);
    });
});

// A screen's corners (owner, 2026-11-10): every corner is 90 degrees and
// takes its corner bar, and the Curve's % applies to each side as its own
// wall. "the corner itself is flat due to the edge the opposite side of
// the 90 is curvable": only the fold takes no curve angle. A side runs
// right up to the fold, its corner bar's arm included (a panel of a 2
// panel bar, half a panel of a 1 panel bar), and the joint where the arm
// meets the next bar is a bar joint with the side's curve angle.
describe('a curved screen with corners, curved side by side up to each fold', () => {
    const covers = (placed, n) => {
        let at = 0;
        for (const b of placed) { if (b.start !== at) return false; at += b.size; }
        return at === n;
    };
    // curve-math's own answer for one wall `panels` wide (whole or half
    // panels), its arms `armL` and `armR` fixed bars at its ends and the
    // stock between them, built here straight from the calculator.
    const wall = (panels, armL, armR, over = {}, sizes = [1, 2]) => {
        const s = cleanCurve(on(over));
        const unit = Number.isInteger(armL) && Number.isInteger(armR) ? 1 : 0.5;
        const n = Math.round(panels / unit);
        const config = makeCurve('Side');
        config.panel.count = n;
        config.panel.width_m = 0.5 * unit;
        config.hardware.footer_widths_m = sizes.map((k) => k * 0.5);
        config.hardware.detents_deg = [...s.angles];
        config.target = s.entry === 'degrees' ? { mode: 'sweep_deg', value: s.value, radius_ref: 'face' }
            : { mode: 'percent_circle', value: s.value, radius_ref: 'face' };
        config.direction = s.bend;
        config.build_from = s.from;
        config.fit_goal = s.goal;
        config.tolerance_m = s.toleranceMm / 1000;
        config.layout_constraints = { pieces: [
            ...(armL ? [{ start: 0, size: armL / unit }] : []),
            ...(armR ? [{ start: n - armR / unit, size: armR / unit }] : [])] };
        // the seams: every joint in whole panels, every other in halves
        const seams = [];
        for (let j = 0; j < n - 1; j++) if (Number.isInteger((j + 1) * unit + (armL === 0.5 ? 0.5 : 0))) seams.push(j);
        if (unit < 1) config.seam_joints = seams;
        const r = solveCurve(config);
        const sign = s.bend === 'concave' ? 1 : -1;
        const signed = r.joints.map((j) => (j.angle_deg ? sign * j.angle_deg : 0));
        return { r, joints: unit < 1 ? seams.map((j) => signed[j]) : signed };
    };
    it('the sides run from fold to fold, the corner bars\' arms included', () => {
        expect(curveSides(12, [{ start: 5, size: 2 }])).toEqual([
            { start: 0, panels: 6, armL: 0, armR: 1 }, { start: 6, panels: 6, armL: 1, armR: 0 }]);
        expect(curveSides(12, [{ start: 2, size: 1 }])).toEqual([
            { start: 0, panels: 2.5, armL: 0, armR: 0.5 }, { start: 2.5, panels: 9.5, armL: 0.5, armR: 0 }]);
        expect(curveSides(14, [{ start: 9, size: 1 }, { start: 3, size: 2 }])).toEqual([
            { start: 0, panels: 4, armL: 0, armR: 1 }, { start: 4, panels: 5.5, armL: 1, armR: 0.5 },
            { start: 9.5, panels: 4.5, armL: 0.5, armR: 0 }]);
        expect(curveSides(8, [{ start: 0, size: 1 }])).toEqual([
            { start: 0, panels: 0.5, armL: 0, armR: 0.5 }, { start: 0.5, panels: 7.5, armL: 0.5, armR: 0 }]);
        expect(curveSides(8, [])).toEqual([{ start: 0, panels: 8, armL: 0, armR: 0 }]);
        // junk pieces are dropped: not 1 or 2 panels, off the screen, sharing a panel
        expect(curveSides(8, [{ start: 2, size: 3 }, { start: 7, size: 2 }, { start: 3, size: 2 }, { start: 4, size: 1 }]))
            .toEqual([{ start: 0, panels: 4, armL: 0, armR: 1 }, { start: 4, panels: 4, armL: 1, armR: 0 }]);
        expect([sideName(0, 2), sideName(1, 2), sideName(0, 3), sideName(2, 3)])
            .toEqual(['left side', 'right side', 'side 1', 'side 3']);
    });
    it('a seam corner on 6|7 of 12: the seam is flat, 5|6 and 7|8 bend, each side a six panel wall', () => {
        const out = screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [1, 2], settings: on(), pieces: [{ start: 5, size: 2 }] });
        expect(out.errors).toEqual([]);
        expect(out.result).toBe(null);
        expect(out.sides.map((s) => [s.name, s.start, s.panels])).toEqual([['left side', 0, 6], ['right side', 6, 6]]);
        expect(out.sides.map((s) => s.seams)).toEqual([[0, 1, 2, 3, 4], [6, 7, 8, 9, 10]]);
        // the corner's own seam, 6|7, has no curve angle
        expect(out.joints[5]).toBe(0);
        // the far joints of the corner bar, 5|6 and 7|8, carry their side's angle
        expect(out.joints[4]).not.toBe(0);
        expect(out.joints[6]).not.toBe(0);
        // each side is curve-math's wall of six panels, its arm the sixth
        const left = wall(6, 0, 1);
        const right = wall(6, 1, 0);
        expect(out.joints.slice(0, 5)).toEqual(left.joints);
        expect(out.joints.slice(6)).toEqual(right.joints);
        expect(out.sides[0].out.result.achieved.radius_face_m).toBeCloseTo(left.r.achieved.radius_face_m, 9);
        expect(out.sides[0].out.result.ideal_angle_deg).toBeCloseTo(left.r.ideal_angle_deg, 9);
        // the arm is a bar: the joint after it is a bar joint
        expect(out.sides[0].out.result.footers.map((f) => f.panels).slice(-1)).toEqual([1]);
        expect(covers(out.placed, 12)).toBe(true);
        expect(out.placed.filter((b) => b.corner)).toEqual([{ start: 5, size: 2, corner: true }]);
        expect(out.placed.filter((b) => !b.corner).every((b) => b.start + b.size <= 5 || b.start >= 7)).toBe(true);
    });
    it('a corner down panel 3: 2|3 and 3|4 bend, the half panels count on each side', () => {
        const over = { entry: 'degrees', value: 12.5, angles: [3.75, 5], goal: 'tightest' };
        const out = screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [1], settings: on(over), pieces: [{ start: 2, size: 1 }] });
        expect(out.errors).toEqual([]);
        expect(out.sides.map((s) => [s.name, s.start, s.panels, s.seams])).toEqual([
            ['left side', 0, 2.5, [0, 1]], ['right side', 2.5, 9.5, [2, 3, 4, 5, 6, 7, 8, 9, 10]]]);
        // the panel's own seams are on their sides' arcs
        expect(out.joints[1]).not.toBe(0);
        expect(out.joints[2]).not.toBe(0);
        const left = wall(2.5, 0, 0.5, over, [1]);
        const right = wall(9.5, 0.5, 0, over, [1]);
        expect(out.joints.slice(0, 2)).toEqual(left.joints);
        expect(out.joints.slice(2)).toEqual(right.joints);
        // 2.5 panels across, worked in halves: five steps, 12.5 degrees of sweep
        expect(out.sides[0].out.result.config.panel.count).toBe(5);
        expect(out.sides[0].out.result.achieved.chord_m).toBeCloseTo(left.r.achieved.chord_m, 9);
        // the counts are the side's seams: two on the left
        expect(out.sides[0].out.result.options.every((o) => o.curved_joints + o.flat_joints === 2)).toBe(true);
        expect(out.sides[1].out.result.options.every((o) => o.curved_joints + o.flat_joints === 9)).toBe(true);
        expect(out.placed.filter((b) => b.corner)).toEqual([{ start: 2, size: 1, corner: true }]);
        expect(covers(out.placed, 12)).toBe(true);
        expect(out.warnings.some((w) => /Bars:/.test(w))).toBe(false);
    });
    it('built from the fold, each side is a true arc: half a panel takes three quarters of a panel\'s angle', () => {
        // eleven panels, a corner down panel 5: 4.5 panels left, 6.5 right,
        // 23.4 degrees of sweep each (2.6 and 1.8 degrees a half panel)
        const over = { entry: 'degrees', value: 23.4, angles: [2.7, 3.6, 3.9, 5.2], goal: 'tightest', from: 5 };
        const out = screenCurve({ panels: 11, panelWidthM: 0.5, sizes: [1], settings: on(over), pieces: [{ start: 4, size: 1 }] });
        expect(out.joints).toEqual([5.2, 5.2, 5.2, 3.9, 2.7, 3.6, 3.6, 3.6, 3.6, 3.6]);
        expect(out.sides.map((s) => s.out.result.config.build_from)).toEqual(['right', 'left']);
        expect(out.sides[0].out.result.achieved.sweep_deg).toBeCloseTo(23.4, 2);
        expect(out.sides[1].out.result.achieved.sweep_deg).toBeCloseTo(23.4, 2);
    });
    it('sides of different widths each take the same % at their own radius', () => {
        // ten panels, a corner on the seam between 4 and 5: four panels on
        // the left, six on the right, 30 degrees of sweep each
        const settings = { entry: 'degrees', value: 30, angles: [5, 7.5] };
        const out = screenCurve({ panels: 10, panelWidthM: 0.5, sizes: [1], settings: on(settings), pieces: [{ start: 3, size: 2 }] });
        expect(out.errors).toEqual([]);
        expect(out.joints).toEqual([7.5, 7.5, 7.5, 0, 5, 5, 5, 5, 5]);
        expect(out.sides[0].out.result.achieved.sweep_deg).toBeCloseTo(30, 6);
        expect(out.sides[1].out.result.achieved.sweep_deg).toBeCloseTo(30, 6);
        expect(out.sides[0].out.result.achieved.radius_face_m).toBeCloseTo(faceRadiusForAngle(0.5, 7.5), 9);
        expect(out.sides[1].out.result.achieved.radius_face_m).toBeCloseTo(faceRadiusForAngle(0.5, 5), 9);
    });
    it('two corners make three sides, each its own wall', () => {
        const pieces = [{ start: 3, size: 2 }, { start: 9, size: 1 }];
        const out = screenCurve({ panels: 14, panelWidthM: 0.5, sizes: [1, 2], settings: on(), pieces });
        expect(out.errors).toEqual([]);
        expect(out.sides.map((s) => [s.name, s.start, s.panels])).toEqual([['side 1', 0, 4], ['side 2', 4, 5.5], ['side 3', 9.5, 4.5]]);
        expect(out.joints).toEqual([...wall(4, 0, 1).joints, 0, ...wall(5.5, 1, 0.5).joints, ...wall(4.5, 0.5, 0).joints]);
        expect(covers(out.placed, 14)).toBe(true);
    });
    it('a convex curve, degrees of sweep and every goal hold side by side', () => {
        for (const over of [{ bend: 'convex' }, { entry: 'degrees', value: 45 }, { goal: 'even' }, { goal: 'tightest' }]) {
            const out = screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [1, 2], settings: on(over), pieces: [{ start: 5, size: 1 }] });
            expect(out.joints).toEqual([...wall(5.5, 0, 0.5, over).joints, ...wall(6.5, 0.5, 0, over).joints]);
            const seam = screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [1, 2], settings: on(over), pieces: [{ start: 5, size: 2 }] });
            expect(seam.joints).toEqual([...wall(6, 0, 1, over).joints, 0, ...wall(6, 1, 0, over).joints]);
        }
    });
    it('a side that is only its corner bar\'s arm has no joint, and nothing to cover', () => {
        const half = screenCurve({ panels: 8, panelWidthM: 0.5, sizes: [1, 2], settings: on(), pieces: [{ start: 0, size: 1 }] });
        expect(half.errors).toEqual([]);
        expect(half.sides[0].out.result).toBe(null);
        expect(half.placed[0]).toEqual({ start: 0, size: 1, corner: true });
        expect(half.joints).toEqual(wall(7.5, 0.5, 0).joints);
        const one = screenCurve({ panels: 8, panelWidthM: 0.5, sizes: [1, 2], settings: on(), pieces: [{ start: 0, size: 2 }] });
        expect(one.errors).toEqual([]);
        expect(one.joints[0]).toBe(0);
        expect(one.joints.slice(1)).toEqual(wall(7, 1, 0).joints);
    });
    it('leftover stock is refused for each side, said by name, and nothing is laid', () => {
        // a corner down panel 6 of 12, doubles only: five panels between
        // the screen's end and the arm on the left
        const out = screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [2], settings: on(), pieces: [{ start: 5, size: 1 }] });
        expect(out.errors).toEqual(['These bar sizes leave 1 panel uncovered on the left side (5.5 panels). Light another size.']);
        expect(out.bars).toEqual([]);
        expect(out.placed).toEqual([]);
        // the whole wall alone is covered by doubles: no refusal there
        expect(screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [2], settings: on() }).errors).toEqual([]);
        // a seam corner's arms leave four panels each side: covered
        expect(screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [2], settings: on(), pieces: [{ start: 4, size: 2 }] }).errors).toEqual([]);
        const three = screenCurve({ panels: 14, panelWidthM: 0.5, sizes: [2], settings: on(), pieces: [{ start: 3, size: 2 }, { start: 9, size: 1 }] });
        expect(three.errors).toEqual(['These bar sizes leave 1 panel uncovered on side 1 (4 panels). Light another size.']);
        // an error every side has is said once
        const bad = screenCurve({ panels: 12, panelWidthM: 0.5, sizes: [1], settings: on({ angles: [95] }), pieces: [{ start: 5, size: 2 }] });
        expect(bad.errors).toEqual(['Lock angles must be under 90°.']);
    });
    it('Ways to build it and a pick are each side\'s own', () => {
        const args = { panels: 12, panelWidthM: 0.5, sizes: [1, 2], pieces: [{ start: 5, size: 2 }] };
        const out = screenCurve({ ...args, settings: on() });
        expect(out.sides.every((s) => s.out.result.options.length > 0)).toBe(true);
        const right = out.sides[1].out;
        const other = right.result.options.find((o) => o.id !== right.result.chosen_option_id);
        expect(!!other).toBe(true);
        const picked = screenCurve({ ...args, settings: on({ sidePicks: [null, { id: other.id, key: right.pickKey }] }) });
        expect(picked.sides[1].out.result.chosen_option_id).toBe(other.id);
        expect(picked.sides[0].out.result.chosen_option_id).toBe(out.sides[0].out.result.chosen_option_id);
        expect(picked.joints.slice(0, 6)).toEqual(out.joints.slice(0, 6));
        expect(picked.placed.filter((b) => b.corner)).toEqual([{ start: 5, size: 2, corner: true }]);
        // a pick is one side's: the left side and the whole wall have keys of their own
        expect(new Set([out.sides[0].out.pickKey, right.pickKey,
                        screenCurve({ ...args, pieces: undefined, settings: on() }).pickKey]).size).toBe(3);
        // a pick for one side does not hold once the corner moves
        const moved = screenCurve({ ...args, pieces: [{ start: 4, size: 2 }], settings: on({ sidePicks: [null, { id: other.id, key: right.pickKey }] }) });
        expect(moved.sides[1].out.result.config.pattern_choice).toBe('auto');
        // a pick saved when a side stopped at the corner bar (its key named
        // the side by index, count and start only) goes back to the app's pick
        const key = JSON.parse(right.pickKey);
        key[key.length - 1] = ['side', 1, 2, 7];
        key[0] = 5;
        const old = screenCurve({ ...args, settings: on({ sidePicks: [null, { id: other.id, key: JSON.stringify(key) }] }) });
        expect(old.errors).toEqual([]);
        expect(old.sides[1].out.result.config.pattern_choice).toBe('auto');
        expect(old.joints).toEqual(out.joints);
    });
    it('Build from: Left, Center and Right are each side\'s own, a spot is on its side', () => {
        const args = { panels: 12, panelWidthM: 0.5, sizes: [1, 2], pieces: [{ start: 5, size: 2 }] };
        const froms = (from, a = args) => screenCurve({ ...a, settings: on({ from }) }).sides.map((s) => s.out.result.config.build_from);
        expect(froms('left')).toEqual(['left', 'left']);
        expect(froms('center')).toEqual(['center', 'center']);
        // panel 10 is the fourth panel of the right side (panels 7 to 12);
        // the left side builds from its end nearest it
        expect(froms(10)).toEqual(['right', 4]);
        expect(froms(2)).toEqual([2, 'left']);
        // panel 6 is the left side's arm; the seam is both sides' end
        expect(froms(6)).toEqual([6, 'left']);
        expect(froms(6.5)).toEqual(['right', 'left']);
        expect(screenCurve({ ...args, settings: on({ from: 10 }) }).datum_at).toBe(10);
        // a corner down panel 3: the sides count in half panels
        const mid = { ...args, sizes: [1], pieces: [{ start: 2, size: 1 }] };
        expect(froms(2, mid)).toEqual([3.5, 'left']);
        expect(froms(3, mid)).toEqual(['right', 'left']);
        expect(froms(7, mid)).toEqual(['right', 8.5]);
    });
    it('cleanCurve keeps each side\'s pick, and a screen without one keeps its shape', () => {
        expect(cleanCurve({ sidePicks: [null, { id: '5', key: 'k' }, 'junk'] }).sidePicks).toEqual([null, { id: '5', key: 'k' }]);
        expect('sidePicks' in cleanCurve({ sidePicks: [null, 'junk'] })).toBe(false);
        expect('sidePicks' in cleanCurve({})).toBe(false);
    });
    it('a screen without corners asks and answers exactly as before', () => {
        const a = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1, 2], settings: on() });
        const b = screenCurve({ panels: 16, panelWidthM: 0.5, sizes: [1, 2], settings: on(), pieces: [] });
        expect(b.pickKey).toBe(a.pickKey);
        expect(a.pickKey).toBe(curvePickKey({ panels: 16, panelWidthM: 0.5, sizes: [1, 2], settings: on() }));
        expect(b.bars).toEqual(a.bars);
        expect(b.joints).toEqual(a.joints);
        expect(a.sides).toBe(undefined);
        expect(a.errors).toEqual([]);
        expect(screenCurve({ panels: 15, panelWidthM: 0.5, sizes: [2], settings: on() }).errors)
            .toEqual(['These bar sizes leave 1 panel uncovered on a 15-panel wall. Light another size.']);
    });
});

report();
