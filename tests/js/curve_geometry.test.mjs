// The curve calculator's geometry tests.
// Ported from the curve calculator's own tests; run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import {
  angleForChord,
  arcChord,
  arcDepth,
  buildCurve,
  faceGap,
  radiusForAngle,
} from '../../src/static/js/curve-math.js';

/**
 * The reference case throughout: sixteen 500 mm tiles, every joint at 5°.
 *
 * These constants were derived independently of the code, by the law of cosines
 * (R = c / sqrt(2(1 - cos t))) and then by measuring 17 explicit vertices placed
 * round a circle, deliberately not the half-angle identity the app uses, so the
 * test checks the implementation rather than restating it. Sweep is 80°: sixteen
 * panels each subtend 5°, across seventeen vertices and fifteen joints.
 */
const W = 0.5;
const N = 16;
const REF_R = 5.731396407;
const REF_FACE_R = 5.725941387;
const REF_CHORD = 7.368141193;
const REF_DEPTH = 1.340892038;

const base = {
  widths: new Array(N).fill(W),
  joints: new Array(N - 1).fill(5),
  direction: 'concave',
  pivotOffsetM: 0,
  panelDepthM: 0.085,
  wallHeightM: 6,
};

describe('arc primitives', () => {
  it('converts between chord angle and radius both ways', () => {
    expect(radiusForAngle(W, 5)).toBeCloseTo(REF_R, 8);
    expect(angleForChord(W, REF_R)).toBeCloseTo(5, 6);
  });

  it('reports a flat wall as an infinite radius rather than a huge number', () => {
    expect(radiusForAngle(W, 0)).toBe(Infinity);
    expect(arcDepth(Infinity, 0)).toBe(0);
    expect(arcChord(Infinity, 0)).toBe(0);
  });

  it('matches the hand-worked chord and depth', () => {
    expect(arcChord(REF_R, 80)).toBeCloseTo(REF_CHORD, 8);
    expect(arcDepth(REF_R, 80)).toBeCloseTo(REF_DEPTH, 8);
  });

  it('refuses a panel wider than the circle instead of returning NaN', () => {
    expect(angleForChord(10, 1)).toBe(180);
    expect(Number.isNaN(angleForChord(10, 1))).toBe(false);
  });
});

describe('built geometry', () => {
  const built = buildCurve(base);

  it('measures the reference wall off the polyline, not a formula', () => {
    const m = built.measurements;
    expect(m.sweep_deg).toBeCloseTo(80, 6);
    expect(m.percent_circle).toBeCloseTo(22.222, 3);
    expect(m.total_turn_deg).toBeCloseTo(75, 6);
    expect(m.radius_joints_m).toBeCloseTo(REF_R, 8);
    expect(m.chord_m).toBeCloseTo(REF_CHORD, 8);
    expect(m.depth_m).toBeCloseTo(REF_DEPTH, 8);
    expect(m.arc_length_m).toBeCloseTo(8, 9);
  });

  it('puts the radius to the panel faces inside the joint circle', () => {
    // Face centers sit on the apothem, R cos(angle/2), independently measured.
    expect(built.measurements.radius_face_m).toBeCloseTo(REF_FACE_R, 8);
    expect(built.measurements.radius_face_m).toBeLessThan(built.measurements.radius_joints_m);
  });

  it('centers the wall on the origin facing the audience', () => {
    const mid = built.vertices[N / 2];
    expect(mid.x).toBeCloseTo(0, 9);
    expect(mid.y).toBeCloseTo(0, 9);
    // Concave: both ends come forward, toward +y.
    expect(built.vertices[0].y).toBeGreaterThan(0);
    expect(built.vertices[N].y).toBeGreaterThan(0);
    expect(built.vertices[0].x).toBeCloseTo(-built.vertices[N].x, 9);
  });

  it('mirrors concave to convex without changing the size of the curve', () => {
    const convex = buildCurve({ ...base, direction: 'convex' });
    expect(convex.measurements.chord_m).toBeCloseTo(built.measurements.chord_m, 9);
    expect(convex.measurements.depth_m).toBeCloseTo(built.measurements.depth_m, 9);
    expect(convex.vertices[0].y).toBeLessThan(0);
  });

  it('reports a straight wall when no joint is set', () => {
    const flat = buildCurve({ ...base, joints: new Array(N - 1).fill(0) });
    expect(flat.measurements.radius_joints_m).toBe(Infinity);
    expect(flat.measurements.chord_m).toBeCloseTo(8, 9);
    expect(flat.measurements.depth_m).toBeCloseTo(0, 9);
    expect(flat.measurements.sweep_deg).toBe(0);
  });

  it('handles an odd panel count by centering on the middle panel', () => {
    const odd = buildCurve({ ...base, widths: new Array(15).fill(W), joints: new Array(14).fill(5) });
    expect(odd.measurements.sweep_deg).toBeCloseTo(75, 6);
    const left = odd.vertices[0];
    const right = odd.vertices[15];
    expect(left.x).toBeCloseTo(-right.x, 9);
    expect(left.y).toBeCloseTo(right.y, 9);
  });

  it('counts the panel depth into the footprint but not the screen size', () => {
    const m = built.measurements;
    expect(m.footprint_d_m).toBeGreaterThan(m.depth_m);
    expect(m.footprint_d_m).toBeCloseTo(m.depth_m + base.panelDepthM, 3);
    expect(m.wall_height_m).toBe(6);
  });

  it('takes a mixed-detent pattern without pretending it is a perfect arc', () => {
    const mixed = buildCurve({
      ...base,
      joints: [5, 2.5, 5, 2.5, 5, 2.5, 5, 2.5, 5, 2.5, 5, 2.5, 5, 2.5, 5],
    });
    // Average 3.9°, so it lands between the 2.5° and 5° uniform walls.
    const tight = buildCurve({ ...base, joints: new Array(N - 1).fill(5) });
    const loose = buildCurve({ ...base, joints: new Array(N - 1).fill(2.5) });
    expect(mixed.measurements.depth_m).toBeLessThan(tight.measurements.depth_m);
    expect(mixed.measurements.depth_m).toBeGreaterThan(loose.measurements.depth_m);
  });
});

describe('joint gap from the hinge position', () => {
  it('closes up perfectly when the hardware pivots in the face', () => {
    expect(faceGap(10, 0, 'convex')).toBe(0);
  });

  it('opens on a convex bend and interferes on a concave one', () => {
    // 2 * 85 mm * sin 5° = 14.816 mm
    expect(faceGap(10, 0.085, 'convex')).toBeCloseTo(0.014816476, 9);
    expect(faceGap(10, 0.085, 'concave')).toBeCloseTo(-0.014816476, 9);
  });

  it('shows up in the built geometry as a break between panel faces', () => {
    const offset = buildCurve({ ...base, pivotOffsetM: 0.085, direction: 'convex' });
    const a = offset.placements[0].face[1];
    const b = offset.placements[1].face[0];
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeCloseTo(Math.abs(faceGap(5, 0.085, 'convex')), 6);
  });
});

describe('the depth dimension', () => {
  it('marks the middle of the wall, not the end that swings furthest from center', () => {
    // The frame is centerd on the middle of the wall, so a concave wall's ends
    // carry the biggest y. Taking the largest |y| would dimension the wrong point.
    const built = buildCurve(base);
    const ends = [built.placements[0].face[0], built.placements[N - 1].face[1]];
    expect(Math.abs(built.measurements.depth_apex.x)).toBeLessThan(0.3);
    expect(ends.every((e) => Math.abs(e.y) > Math.abs(built.measurements.depth_apex.y))).toBe(true);
  });

  it('drops the dimension onto the chord, square to it', () => {
    const { depth_apex, depth_foot, depth_m } = buildCurve(base).measurements;
    expect(Math.hypot(depth_apex.x - depth_foot.x, depth_apex.y - depth_foot.y)).toBeCloseTo(depth_m, 9);
  });

  it('puts the foot half way along a symmetric wall', () => {
    const { depth_foot } = buildCurve(base).measurements;
    expect(depth_foot.x).toBeCloseTo(0, 6);
  });
});

describe('audit findings: shapes the three-point circle used to misread', () => {
  const wall = (n, angle) =>
    buildCurve({ ...base, widths: new Array(n).fill(W), joints: new Array(n - 1).fill(angle) });

  it('reads a closed ring as 360°, not a straight wall', () => {
    // Sixteen panels at 22.5° close exactly. Both ends land on the same point.
    const m = wall(16, 22.5).measurements;
    expect(m.sweep_deg).toBe(360);
    expect(m.percent_circle).toBe(100);
    // w / (2 sin 11.25°) and w / (2 tan 11.25°)
    expect(m.radius_joints_m).toBeCloseTo(0.5 / (2 * Math.sin((11.25 * Math.PI) / 180)), 6);
    expect(m.radius_face_m).toBeCloseTo(0.5 / (2 * Math.tan((11.25 * Math.PI) / 180)), 6);
    expect(Number.isFinite(m.depth_ratio_pct)).toBe(true);
  });

  it('reads an odd panel count just past a half round as past it', () => {
    // Three panels at 66° each: 198° of sweep, which used to read as 162°.
    expect(wall(3, 66).measurements.sweep_deg).toBeCloseTo(198, 6);
    // Five panels at 36.5°: 182.5°.
    expect(wall(5, 36.5).measurements.sweep_deg).toBeCloseTo(182.5, 6);
  });

  it('keeps reading an exact half round as 180°', () => {
    expect(wall(4, 45).measurements.sweep_deg).toBeCloseTo(180, 6);
    expect(wall(3, 60).measurements.sweep_deg).toBeCloseTo(180, 6);
  });

  it('gives a two-panel wall its face radius, not the joint radius', () => {
    // One joint at 36°: face radius 0.5 / (2 tan 18°) = 0.7694 m.
    expect(wall(2, 36).measurements.radius_face_m).toBeCloseTo(0.5 / (2 * Math.tan((18 * Math.PI) / 180)), 6);
  });

  it('puts the depth dimension in the middle of an odd panel count, not on a corner', () => {
    expect(wall(15, 5).measurements.depth_apex.x).toBeCloseTo(0, 9);
  });

  it('stops quoting depth as a share of width once the wall wraps past a half round', () => {
    expect(wall(16, 15).measurements.depth_ratio_pct).toBe(0);
  });

  it('measures a very long wall without overflowing the call stack', () => {
    // Math.max(...spread) threw at around 30,000 panels and blanked the page.
    const m = wall(40000, 0.001).measurements;
    expect(Number.isFinite(m.footprint_w_m)).toBe(true);
  });
});

describe('the wall sits on the datum it is built from', () => {
  const at = (anchor) => buildCurve({ ...base, anchor });

  it('center out: the middle of the wall is the origin', () => {
    const v = at('center').vertices;
    expect(v[N / 2].x).toBeCloseTo(0, 9);
    expect(v[N / 2].y).toBeCloseTo(0, 9);
  });

  it('from the left: the left corner is the origin and the first panel runs along +x', () => {
    const v = at('left').vertices;
    expect(v[0].x).toBeCloseTo(0, 9);
    expect(v[0].y).toBeCloseTo(0, 9);
    expect(v[1].x).toBeCloseTo(W, 9);
    expect(v[1].y).toBeCloseTo(0, 9);
  });

  it('from the right: the right corner is the origin and the last panel runs along +x', () => {
    const v = at('right').vertices;
    expect(v[N].x).toBeCloseTo(0, 9);
    expect(v[N].y).toBeCloseTo(0, 9);
    expect(v[N - 1].x).toBeCloseTo(-W, 9);
    expect(v[N - 1].y).toBeCloseTo(0, 9);
  });

  it('is the same wall whichever datum it sits on', () => {
    for (const anchor of ['left', 'right']) {
      const m = at(anchor).measurements;
      expect(m.chord_m).toBeCloseTo(at('center').measurements.chord_m, 9);
      expect(m.depth_m).toBeCloseTo(at('center').measurements.depth_m, 9);
      expect(m.sweep_deg).toBeCloseTo(at('center').measurements.sweep_deg, 6);
    }
  });
});

describe('footprint is measured square to the wall, not to the datum', () => {
  it('gives the same deck space whichever end the wall is built from', () => {
    // Anchored at an end the chord runs off at an angle; measuring the bounding
    // box in that frame read 6.3 m × 4.2 m for a wall 7.5 m wide and 1.2 m deep.
    const center = buildCurve({ ...base, anchor: 'center' }).measurements;
    for (const anchor of ['left', 'right']) {
      const m = buildCurve({ ...base, anchor }).measurements;
      expect(m.footprint_w_m).toBeCloseTo(center.footprint_w_m, 9);
      expect(m.footprint_d_m).toBeCloseTo(center.footprint_d_m, 9);
    }
    // A shade wider than the chord: the end panels' back corners sit outside it.
    expect(center.footprint_w_m).toBeGreaterThanOrEqual(REF_CHORD);
    expect(center.footprint_w_m).toBeLessThan(REF_CHORD + 2 * base.panelDepthM);
    expect(center.footprint_d_m).toBeCloseTo(REF_DEPTH + base.panelDepthM, 2);
  });
});

report();
