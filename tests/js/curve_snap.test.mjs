// The curve calculator's snap tests.
// Ported from the curve calculator's own tests; run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import {
  fitJoints,
  maxAngle,
  runLength,
  searchSymmetric,
  usableDetents,
} from '../../src/static/js/curve-math.js';

const DETENTS = [0, 2.5, 5, 7.5, 10];

const hardware = (over = {}) => ({
  footer_widths_m: [0.5],
  detents_deg: [2.5, 5, 7.5, 10],
  max_concave_deg: null,
  max_convex_deg: null,
  pivot_offset_m: 0,
  ...over,
});

describe('what the hardware offers', () => {
  it('sorts, de-duplicates and adds flat', () => {
    expect(usableDetents(hardware({ detents_deg: [10, 2.5, 5, 2.5, 7.5] }), 'concave')).toEqual(DETENTS);
  });

  it('always offers flat, because not every joint has to curve', () => {
    expect(usableDetents(hardware({ detents_deg: [5] }), 'concave')).toEqual([0, 5]);
  });

  it('takes a magnitude, however the user typed it', () => {
    expect(usableDetents(hardware({ detents_deg: [-5, 5] }), 'concave')).toEqual([0, 5]);
  });

  it('honours a direction limit, because concave usually fouls first', () => {
    const h = hardware({ max_concave_deg: 5, max_convex_deg: 10 });
    expect(usableDetents(h, 'concave')).toEqual([0, 2.5, 5]);
    expect(usableDetents(h, 'convex')).toEqual(DETENTS);
    expect(maxAngle(h, 'concave')).toBe(5);
    expect(maxAngle(h, 'convex')).toBe(10);
  });

  it('reports no angle at all when there is nothing but flat', () => {
    expect(maxAngle(hardware({ detents_deg: [] }), 'concave')).toBe(0);
  });
});

describe('fitting joints onto the angles available', () => {
  it('leaves every joint the same when the curve lands on an angle exactly', () => {
    expect(fitJoints(15, 5, DETENTS, 'center')).toEqual(new Array(15).fill(5));
    expect(fitJoints(15, 5, DETENTS, 'left')).toEqual(new Array(15).fill(5));
  });

  it('mixes two angles when the curve falls between them', () => {
    const joints = fitJoints(8, 6.25, DETENTS, 'left');
    expect(new Set(joints)).toEqual(new Set([5, 7.5]));
    expect(joints.reduce((a, b) => a + b, 0) / joints.length).toBeCloseTo(6.25, 9);
  });

  it('leaves joints flat when the curve is gentler than the smallest angle', () => {
    const joints = fitJoints(20, 1, [0, 5, 10], 'center');
    expect(joints).toContain(0);
    expect(joints).toContain(5);
    expect(joints.reduce((a, b) => a + b, 0) / 20).toBeCloseTo(1, 1);
  });

  it('pins every joint at maximum when the curve is past what the hardware can do', () => {
    expect(fitJoints(6, 25, DETENTS, 'center')).toEqual(new Array(6).fill(10));
  });

  it('returns nothing for a single panel, which has no joints', () => {
    expect(fitJoints(0, 5, DETENTS, 'center')).toEqual([]);
  });

  it('beats plain rounding where rounding walks the wall off the drawing', () => {
    // 24 panels at 16 %: rounding to keep the heading right landed 62 mm off
    // where 11 mm was buildable. Measured in panel widths, on 500 mm tiles.
    const ideal = (16 / 100 * 360) / 24;
    const searched = searchSymmetric(23, ideal, () => [0, 2.5, 5, 7.5, 10]);
    const joints = fitJoints(23, ideal, [0, 2.5, 5, 7.5, 10], 'center');
    expect(joints).toEqual(searched);
  });
});

describe('where the wall is built out from', () => {
  const ideal = 4.5;

  it('center out: both halves of the pattern read the same', () => {
    const joints = fitJoints(9, 6.25, DETENTS, 'center');
    expect(joints).toEqual([...joints].reverse());
  });

  it('from an end: the pattern runs along the wall and need not mirror', () => {
    const left = fitJoints(15, ideal, DETENTS, 'left');
    expect(left).toHaveLength(15);
    expect(left.reduce((a, b) => a + b, 0) / 15).toBeCloseTo(ideal, 0);
  });

  it('building from the right is the left pattern in reverse', () => {
    expect(fitJoints(15, ideal, DETENTS, 'right')).toEqual(
      [...fitJoints(15, ideal, DETENTS, 'left')].reverse(),
);
  });

  it('keeps the joints the hardware offers, whichever end it starts from', () => {
    for (const origin of ['center', 'left', 'right'])
      expect(fitJoints(15, ideal, DETENTS, origin).every((a) => DETENTS.includes(a))).toBe(true);
  });
});

describe('build sheet runs', () => {
  it('collapses repeats into runs with joint numbers', () => {
    expect(runLength([5, 5, 5, 2.5, 5, 5])).toEqual([
      { angle_deg: 5, count: 3, from: 1, to: 3 },
      { angle_deg: 2.5, count: 1, from: 4, to: 4 },
      { angle_deg: 5, count: 2, from: 5, to: 6 },
]);
  });

  it('handles an empty wall', () => {
    expect(runLength([])).toEqual([]);
  });
});

describe('joints a footer holds rigid', () => {
  const DEG = 4.5;
  // 1 m footers on 500 mm panels: only every second joint can bend.
  const everySecond = (i) => (i + 1) % 2 === 0;

  it('leaves the joints inside a footer flat', () => {
    for (const origin of ['center', 'left', 'right']) {
      const joints = fitJoints(15, DEG, DETENTS, origin, 200, everySecond);
      joints.forEach((a, i) => {
        if (!everySecond(i)) expect(a).toBe(0);
      });
      expect(joints.some((a) => a > 0)).toBe(true);
    }
  });

  it('still carries the curve, using the joints it is allowed', () => {
    const free = fitJoints(15, DEG, DETENTS, 'left');
    const footered = fitJoints(15, DEG, DETENTS, 'left', 200, everySecond);
    const total = (j) => j.reduce((a, b) => a + b, 0);
    // Half as many joints, so each does about twice the work; the wall still
    // turns through roughly the same total.
    expect(total(footered)).toBeGreaterThan(total(free) * 0.8);
  });

  it('mirrors center out when the footer grid is symmetric', () => {
    // 16 panels on 1 m footers: 15 joints, every second one free, and each free
    // joint has a free partner across the center.
    const joints = fitJoints(15, DEG, DETENTS, 'center', 200, everySecond);
    expect(joints).toEqual([...joints].reverse());
  });

  it('still bends when the footer grid gives no symmetric pairs', () => {
    // 15 joints with 1.5 m footers: every third joint is free, and none of them
    // pairs with another across the center. Demanding a mirror left the whole
    // wall flat; fitting the halves separately builds the curve instead.
    const everyThird = (i) => (i + 1) % 3 === 0;
    const joints = fitJoints(15, DEG * 3, DETENTS, 'center', 200, everyThird);
    expect(joints.some((a) => a > 0)).toBe(true);
    joints.forEach((a, i) => {
      if (!everyThird(i)) expect(a).toBe(0);
    });
  });
});

report();
