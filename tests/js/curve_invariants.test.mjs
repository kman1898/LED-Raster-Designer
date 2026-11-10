// The curve calculator's invariants tests.
// Ported from the curve calculator's own tests; run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import {
  buildCurve,
  idealAngle,
  isEven,
  makeCurve,
  maxDeviation,
  solveCurve,
  usableDetents,
} from '../../src/static/js/curve-math.js';

/**
 * Rules that must hold for EVERY wall, checked on hundreds of random ones.
 *
 * Each bug found so far was found by one specific example. This throws a wide
 * spread of panel counts, footer stock, angle sets, curves, datums and goals at
 * the calculator and checks each answer against things that cannot be allowed
 * to fail, most of them re-derived here without the app's own geometry.
 */

// Deterministic, so a failure is repeatable: mulberry32.
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const ANGLE_SETS = [[2.5, 5, 7.5, 10], [5], [2, 5, 7.5, 10], [5, 10, 15], [1, 2, 3, 4, 5], [7.5], [2.5, 5]];
const STOCK = [[0.5], [1], [0.5, 1], [1.5], [0.5, 1.5], [0.5, 1, 1.5], [2.5], [1, 1.5]];
const DATUMS = ['center', 'left', 'right', 3, 5.5, 8.5];
const GOALS = ['simplest', 'even', 'tightest'];

function randomWall(r) {
  const c = makeCurve();
  const pick = (xs) => xs[Math.floor(r() * xs.length)];
  c.panel.width_m = pick([0.5, 0.5, 0.5, 0.6]);
  c.panel.count = 2 + Math.floor(r() * 39); // 2..40
  c.hardware.detents_deg = [...pick(ANGLE_SETS)];
  c.hardware.footer_widths_m = pick(STOCK).map((m) => (c.panel.width_m === 0.6 ? (m / 0.5) * 0.6 : m));
  c.direction = r() < 0.5 ? 'concave' : 'convex';
  c.build_from = pick(DATUMS);
  c.fit_goal = pick(GOALS);
  const pct = Math.round(r() * 600) / 10; // 0..60 %
  c.target = r() < 0.5
    ? { mode: 'percent_circle', value: pct, radius_ref: 'face' }
    : { mode: 'sweep_deg', value: Math.round(pct * 3.6 * 10) / 10, radius_ref: 'face' };
  return c;
}

/** Rebuild the wall from its joint angles with nothing but sin and cos. */
function rebuild(c, joints) {
  const sign = c.direction === 'concave' ? 1 : -1;
  const pts = [{ x: 0, y: 0 }];
  let h = 0;
  for (let i = 0; i < c.panel.count; i++) {
    if (i > 0) h += (sign * joints[i - 1] * Math.PI) / 180;
    const p = pts[i];
    pts.push({ x: p.x + c.panel.width_m * Math.cos(h), y: p.y + c.panel.width_m * Math.sin(h) });
  }
  const a = pts[0];
  const b = pts[pts.length - 1];
  const chord = Math.hypot(b.x - a.x, b.y - a.y);
  const depth = chord > 0
    ? Math.max(...pts.map((p) => Math.abs((b.y - a.y) * (p.x - a.x) - (b.x - a.x) * (p.y - a.y)) / chord))
    : 0;
  return { chord, depth };
}

/** Can the stock tile `n` panels exactly? */
function tiles(n, sizes) {
  const ok = [true];
  for (let i = 1; i <= n; i++) ok[i] = sizes.some((k) => i - k >= 0 && ok[i - k]);
  return ok[n];
}

const finite = (v) =>
  typeof v === 'number'
    ? !Number.isNaN(v)
    : v && typeof v === 'object'
      ? Object.values(v).every(finite)
      : true;

// 300 walls by default; CURVE_CASES=1500 runs a bigger spread once after a change to the math.
const CASES = Number(process.env.CURVE_CASES) || 300;
const walls = [];
const random = rng(20260924);
for (let i = 0; i < CASES; i++) {
  const c = randomWall(random);
  walls.push({ c, r: solveCurve(c) });
}
const ok = walls.filter((w) => !w.r.errors.length);

describe(`invariants across ${CASES} random walls`, () => {
  it('solves nearly all of them without an input error', () => {
    // Errors are only legitimate for impossible input (a curve past 100 %, say).
    expect(ok.length).toBeGreaterThan(CASES * 0.9);
  });

  it('never produces NaN anywhere in a result', () => {
    for (const { r } of walls) expect(finite(r)).toBe(true);
  });

  it('only ever sets an angle the hardware actually has', () => {
    for (const { c, r } of ok) {
      const allowed = new Set(usableDetents(c.hardware, c.direction));
      expect(r.joints).toHaveLength(c.panel.count - 1);
      for (const j of r.joints) expect(allowed.has(j.angle_deg)).toBe(true);
    }
  });

  it('lays footers from stock that cover the wall exactly', () => {
    for (const { c, r } of ok) {
      const stock = new Set(c.hardware.footer_widths_m);
      expect(r.footers.reduce((s, f) => s + f.panels, 0)).toBe(c.panel.count);
      for (const f of r.footers) expect(stock.has(f.width_m)).toBe(true);
      // A part footer only when the stock cannot tile the wall at all.
      const sizes = [...stock].map((m) => Math.round(m / c.panel.width_m));
      if (tiles(c.panel.count, sizes)) expect(r.footers.some((f) => f.part)).toBe(false);
    }
  });

  it('never bends a joint that a footer spans', () => {
    for (const { r } of ok) {
      const joins = new Set(r.footers.slice(0, -1).map((f) => f.to));
      for (const j of r.joints) if (j.angle_deg !== 0) expect(joins.has(j.index)).toBe(true);
    }
  });

  it('reports width across and depth that match an independent rebuild', () => {
    for (const { c, r } of ok) {
      const hand = rebuild(c, r.joints.map((j) => j.angle_deg));
      expect(r.achieved.chord_m).toBeCloseTo(hand.chord, 6);
      expect(r.achieved.depth_m).toBeCloseTo(hand.depth, 6);
    }
  });

  it('gives an even wall exactly its sweep: one bend angle times the number of runs', () => {
    for (const { c, r } of ok) {
      const angles = r.joints.map((j) => j.angle_deg);
      const bends = angles.filter((a) => a > 0);
      if (!bends.length || !isEven(angles)) continue;
      const total = bends[0] * (bends.length + 1);
      if (total >= 359) continue; // rings and overlaps are reported separately
      expect(r.achieved.sweep_deg).toBeCloseTo(total, 6);
      expect(r.achieved.percent_circle).toBeCloseTo(total / 3.6, 6);
      void c;
    }
  });

  it('asks for exactly the curve that was entered', () => {
    for (const { c, r } of ok) {
      const pct = c.target.mode === 'sweep_deg' ? c.target.value / 3.6 : c.target.value;
      if (pct >= 99.9) continue;
      expect(r.target.percent_circle).toBeCloseTo(pct, 6);
    }
  });

  it('reports the deviation it actually built', () => {
    for (const { r } of ok) {
      expect(r.max_arc_deviation_m).toBeCloseTo(maxDeviation(r.vertices, r.target_vertices), 9);
    }
  });

  it('draws every wall level', () => {
    for (const { r } of ok) {
      const first = r.placements[0].face[0];
      const last = r.placements[r.placements.length - 1].face[1];
      if (Math.hypot(last.x - first.x, last.y - first.y) < 1e-6) continue; // a closed ring has no chord
      expect(last.y - first.y).toBeCloseTo(0, 9);
    }
  });

  it('keeps its own ranking rules', () => {
    for (const { c, r } of ok) {
      if (r.config.pattern_choice !== 'auto') continue;
      const chosen = r.options.find((o) => o.id === r.chosen_option_id) ;
      const closest = Math.min(...r.options.map((o) => o.deviation_m));
      if (c.fit_goal === 'tightest') expect(chosen.deviation_m).toBeCloseTo(closest, 9);
      if (c.fit_goal === 'even' && r.options.some((o) => o.even)) expect(chosen.even).toBe(true);
      if (c.fit_goal === 'simplest' && r.options.some((o) => o.within_tolerance)) {
        expect(chosen.within_tolerance).toBe(true);
        const fewest = Math.min(...r.options.filter((o) => o.within_tolerance).map((o) => o.used_angles_deg.length));
        expect(chosen.used_angles_deg.length).toBe(fewest);
      }
    }
  });

  it('builds the same wall whatever unit it is displayed in', () => {
    for (const { c, r } of ok.slice(0, 60)) {
      expect(solveCurve(c, 'imperial').joints.map((j) => j.angle_deg)).toEqual(r.joints.map((j) => j.angle_deg));
    }
  });
});

describe('against the best possible answer, found by brute force', () => {
  // Small walls from a fixed end, one footer per panel: try EVERY pattern of
  // angles and check the tightest fit is within 1 mm of the true best.
  const random2 = rng(7);
  const trials = [];
  for (let t = 0; t < 40; t++) {
    const c = makeCurve();
    c.panel.count = 3 + Math.floor(random2() * 6); // 3..8 panels
    c.hardware.detents_deg = [[2.5, 5], [5], [5, 10], [2.5, 7.5]][t % 4];
    c.hardware.footer_widths_m = [0.5];
    c.build_from = random2() < 0.5 ? 'left' : 'right';
    c.fit_goal = 'tightest';
    c.target = { mode: 'percent_circle', value: Math.round(random2() * 400) / 10, radius_ref: 'face' };

    const n = c.panel.count;
    const options = [0, ...c.hardware.detents_deg];
    const ideal = idealAngle(c.target, { widthM: 0.5, count: n, maxAngleDeg: 90, pivotOffsetM: 0, direction: 'concave' });
    const build = (joints) =>
      buildCurve({ widths: new Array(n).fill(0.5), joints, direction: 'concave', anchor: c.build_from, pivotOffsetM: 0, panelDepthM: 0.085, wallHeightM: 6 });
    const drawn = build(new Array(n - 1).fill(ideal)).vertices;

    let best = Infinity;
    const walk = (i, joints) => {
      if (i === n - 1) {
        best = Math.min(best, maxDeviation(build(joints).vertices, drawn));
        return;
      }
      for (const a of options) walk(i + 1, [...joints, a]);
    };
    walk(0, []);
    trials.push({ c, best, got: solveCurve(c).max_arc_deviation_m });
  }

  it('the tightest fit is never more than 1 mm worse than the best that exists', () => {
    for (const { best, got } of trials) expect(got - best).toBeLessThan(0.001);
  });
});

report();
