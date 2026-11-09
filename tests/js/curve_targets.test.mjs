// The curve calculator's targets tests.
// Ported from the curve calculator's own tests; run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import {
  convertCurveEntry,
  idealAngle,
} from '../../src/static/js/curve-math.js';

/**
 * Every mode has to describe the SAME curve when handed the equivalent number.
 * The reference wall is sixteen 500 mm tiles at 5° per joint: 80° of sweep,
 * 5.731396 m to the joints, 7.368141 m chord, 1.340892 m deep. Each case below
 * feeds one of those readings in and expects 5° back out.
 */
const ctx = {
  widthM: 0.5,
  count: 16,
  maxAngleDeg: 10,
  pivotOffsetM: 0,
  direction: 'concave',
};

const t = (mode, value, ref = 'joints') => ({
  mode,
  value,
  radius_ref: ref,
});

describe('every way of saying the same curve', () => {
  it('sweep in degrees', () => {
    expect(idealAngle(t('sweep_deg', 80), ctx)).toBeCloseTo(5, 9);
  });

  it('percent of a full circle', () => {
    // 80 / 360 = 22.2222 %
    expect(idealAngle(t('percent_circle', 22.222222), ctx)).toBeCloseTo(5, 6);
  });

  it('radius to the joints', () => {
    expect(idealAngle(t('radius', 5.731396407), ctx)).toBeCloseTo(5, 7);
  });

  it('radius to the panel face', () => {
    expect(idealAngle(t('radius', 5.725941387, 'face'), ctx)).toBeCloseTo(5, 7);
  });

  it('depth of the bow', () => {
    expect(idealAngle(t('depth', 1.340892038), ctx)).toBeCloseTo(5, 6);
  });

  it('straight-line width', () => {
    expect(idealAngle(t('chord', 7.368141193), ctx)).toBeCloseTo(5, 6);
  });

  it('angle per joint, straight through', () => {
    expect(idealAngle(t('angle_per_joint', 5), ctx)).toBe(5);
  });

  it('percent of what the hardware can do', () => {
    expect(idealAngle(t('percent_max_angle', 50), ctx)).toBeCloseTo(5, 9);
  });
});

describe('percent of a circle', () => {
  it('reads 0 % as a straight line', () => {
    expect(idealAngle(t('percent_circle', 0), ctx)).toBe(0);
  });

  it('reads 100 % as a closed ring, whatever the panel count', () => {
    expect(idealAngle(t('percent_circle', 100), ctx)).toBeCloseTo(360 / 16, 9);
    expect(idealAngle(t('percent_circle', 100), { ...ctx, count: 40 })).toBeCloseTo(9, 9);
  });

  it('does not care how many panels are in the wall', () => {
    // 20 % is 72° of arc whether that is shared by 10 joints or 60.
    const a = idealAngle(t('percent_circle', 20), { ...ctx, count: 10 });
    const b = idealAngle(t('percent_circle', 20), { ...ctx, count: 60 });
    expect(a * 10).toBeCloseTo(72, 9);
    expect(b * 60).toBeCloseTo(72, 9);
  });
});

describe('depth as a percent of width', () => {
  it('reads 50 % as a half round', () => {
    // A semicircle is R deep across a 2R chord, so depth/chord is exactly 0.5.
    expect(idealAngle(t('depth_ratio', 50), ctx) * 16).toBeCloseTo(180, 6);
  });

  it('reads 0 % as a straight line', () => {
    expect(idealAngle(t('depth_ratio', 0), ctx)).toBe(0);
  });
});

describe('the face radius moves with the hinge position', () => {
  it('needs a tighter joint angle on a concave bend when the hinge is behind the face', () => {
    // Face 5 m from the center, hinge 85 mm behind it, so the hinge circle is
    // 5.085 m on a concave bend and 4.915 m on a convex one.
    const concave = idealAngle(t('radius', 5, 'face'), { ...ctx, pivotOffsetM: 0.085 });
    const convex = idealAngle(t('radius', 5, 'face'), {
      ...ctx,
      pivotOffsetM: 0.085,
      direction: 'convex',
    });
    expect(concave).toBeLessThan(convex);
    expect(concave).toBeCloseTo(2 * (180 / Math.PI) * Math.atan(0.5 / (2 * 5.085)), 9);
  });
});

describe('degenerate input', () => {
  it('returns a straight line rather than NaN for a one-panel wall', () => {
    expect(idealAngle(t('percent_circle', 20), { ...ctx, count: 1 })).toBe(0);
    expect(idealAngle(t('radius', 5), { ...ctx, widthM: 0 })).toBe(0);
  });

  it('never asks for more than a closed circle', () => {
    expect(idealAngle(t('sweep_deg', 720), ctx)).toBeCloseTo(360 / 16, 9);
    expect(idealAngle(t('depth', 999), ctx) * 16).toBeLessThanOrEqual(360.0001);
  });
});

describe('switching between % and degrees', () => {
  it('converts both ways without changing the curve', () => {
    expect(convertCurveEntry(20, 'percent_circle', 'sweep_deg')).toBeCloseTo(72, 9);
    expect(convertCurveEntry(72, 'sweep_deg', 'percent_circle')).toBeCloseTo(20, 9);
    expect(convertCurveEntry(11.111, 'percent_circle', 'sweep_deg')).toBeCloseTo(40, 2);
    expect(convertCurveEntry(35, 'sweep_deg', 'sweep_deg')).toBe(35);
  });
});

report();
