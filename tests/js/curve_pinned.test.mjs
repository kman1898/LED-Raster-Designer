// The curve calculator's worked examples (its handoff, section 6), one test
// each, at the figures it pins. Run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import { buildCurve, makeCurve, solveCurve } from '../../src/static/js/curve-math.js';

const curve = (over) => {
    const c = makeCurve();
    over(c);
    return c;
};
const bendsOf = (r) => r.joints.filter((j) => j.angle_deg > 0).map((j) => j.index);

describe('16 x 500 mm, every joint 5 degrees (the reference wall)', () => {
    const m = buildCurve({
        widths: new Array(16).fill(0.5), joints: new Array(15).fill(5), direction: 'concave',
        pivotOffsetM: 0, panelDepthM: 0.085, wallHeightM: 6,
    }).measurements;
    it('sweeps 80 degrees', () => expect(m.sweep_deg).toBeCloseTo(80, 6));
    it('joint radius 5.731396 m', () => expect(m.radius_joints_m).toBeCloseTo(5.731396, 6));
    it('face radius 5.725941 m', () => expect(m.radius_face_m).toBeCloseTo(5.725941, 6));
    it('chord 7.368141 m', () => expect(m.chord_m).toBeCloseTo(7.368141, 6));
    it('depth 1.340892 m', () => expect(m.depth_m).toBeCloseTo(1.340892, 6));
});

describe('40 x 500 mm on 2.5 m bars, 5 degrees only', () => {
    const forty = (value, goal) => solveCurve(curve((c) => {
        c.panel.count = 40;
        c.hardware.footer_widths_m = [2.5];
        c.hardware.detents_deg = [5];
        c.target = { mode: 'percent_circle', value, radius_ref: 'face' };
        c.fit_goal = goal;
    }));

    it('5 degrees after every 5th panel: 7 bends, 40 degrees = 11.11%', () => {
        const r = forty(11.111, 'even');
        expect(bendsOf(r)).toEqual([5, 10, 15, 20, 25, 30, 35]);
        expect(r.achieved.sweep_deg).toBeCloseTo(40, 6);
        expect(r.achieved.percent_circle).toBeCloseTo(11.11, 2);
        expect(r.achieved.radius_face_m).toBeCloseTo(28.630, 3);
        expect(r.achieved.chord_m).toBeCloseTo(19.603, 3);
        expect(r.achieved.depth_m).toBeCloseTo(1.728, 3);
    });

    it('asking 10%: Simplest and Tightest take 5 bends, 9.72%, 103 mm off', () => {
        for (const goal of ['simplest', 'tightest']) {
            const r = forty(10, goal);
            expect(bendsOf(r)).toHaveLength(5);
            expect(r.achieved.percent_circle).toBeCloseTo(9.72, 2);
            expect(Math.round(r.max_arc_deviation_m * 1000)).toBe(103);
        }
    });

    it('asking 10%: Even takes 7 bends, 11.11%, 174 mm off', () => {
        const r = forty(10, 'even');
        expect(bendsOf(r)).toHaveLength(7);
        expect(r.achieved.percent_circle).toBeCloseTo(11.11, 2);
        expect(Math.round(r.max_arc_deviation_m * 1000)).toBe(174);
    });

    it('both are offered whichever goal is picked', () => {
        for (const goal of ['simplest', 'even', 'tightest']) {
            const ids = forty(10, goal).options.map((o) => `${o.curved_joints}${o.even ? ' even' : ''}`);
            expect(ids).toContain('5');
            expect(ids).toContain('7 even');
        }
    });
});

describe('1.5 m bars on 500 mm panels, 5 degrees', () => {
    const runs = (count, sweep) => solveCurve(curve((c) => {
        c.panel.count = count;
        c.hardware.footer_widths_m = [1.5];
        c.hardware.detents_deg = [5];
        c.target = { mode: 'sweep_deg', value: sweep, radius_ref: 'face' };
    }));

    it('12 panels at 20 degrees: 3 bends, 5.56%, 17.18 m, 5.971 m wide, 0.261 m deep', () => {
        const r = runs(12, 20);
        expect(bendsOf(r)).toEqual([3, 6, 9]);
        expect(r.achieved.sweep_deg).toBeCloseTo(20, 6);
        expect(r.achieved.percent_circle).toBeCloseTo(5.56, 2);
        expect(r.achieved.radius_face_m).toBeCloseTo(17.18, 2);
        expect(r.achieved.chord_m).toBeCloseTo(5.971, 3);
        expect(r.achieved.depth_m).toBeCloseTo(0.261, 3);
    });

    it('15 panels at 25 degrees: 4 bends, 6.94%, 17.18 m, 7.443 m wide, 0.391 m deep', () => {
        const r = runs(15, 25);
        expect(bendsOf(r)).toEqual([3, 6, 9, 12]);
        expect(r.achieved.sweep_deg).toBeCloseTo(25, 6);
        expect(r.achieved.percent_circle).toBeCloseTo(6.94, 2);
        expect(r.achieved.radius_face_m).toBeCloseTo(17.18, 2);
        expect(r.achieved.chord_m).toBeCloseTo(7.443, 3);
        expect(r.achieved.depth_m).toBeCloseTo(0.391, 3);
    });
});

describe('15 x 500 mm on 1 m and 0.5 m stock, 5 degrees, 25 degrees', () => {
    for (const goal of ['simplest', 'even', 'tightest']) {
        it(`${goal}: bars 1, 0.5, 1, 0.5 ..., 5 degrees after panels 3, 6, 9, 12, 14.5 mm off`, () => {
            const r = solveCurve(curve((c) => {
                c.panel.count = 15;
                c.hardware.footer_widths_m = [0.5, 1];
                c.hardware.detents_deg = [5];
                c.target = { mode: 'sweep_deg', value: 25, radius_ref: 'face' };
                c.fit_goal = goal;
            }));
            expect(r.footers.map((f) => f.width_m)).toEqual([1, 0.5, 1, 0.5, 1, 0.5, 1, 0.5, 1, 0.5]);
            expect(bendsOf(r)).toEqual([3, 6, 9, 12]);
            expect(r.achieved.sweep_deg).toBeCloseTo(25, 6);
            expect(r.achieved.percent_circle).toBeCloseTo(6.94, 2);
            expect(r.max_arc_deviation_m * 1000).toBeCloseTo(14.5, 1);
            expect(r.max_arc_deviation_m).toBeLessThanOrEqual(r.config.tolerance_m);
        });
    }
});

describe('16 x 500 mm at 20%, 2.5 / 5 / 7.5 / 10 degrees, Simplest', () => {
    const r = solveCurve(makeCurve());
    it('9 x 7.5 degrees and 6 flat', () => {
        expect(r.angle_usage).toEqual([{ angle_deg: 7.5, count: 9 }]);
        expect(r.flat_joints).toBe(6);
    });
    it('builds 19.8%, about 13.6 mm off', () => {
        expect(r.achieved.percent_circle).toBeCloseTo(19.8, 1);
        expect(r.max_arc_deviation_m * 1000).toBeCloseTo(13.6, 1);
    });
});

report();
