// The curve calculator's units tests.
// Ported from the curve calculator's own tests; run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import {
  feetInches,
  formatAngle,
  formatLength,
  formatSmall,
  fromDisplay,
  fromSmallDisplay,
  toDisplay,
  toSmallDisplay,
  toleranceField,
} from '../../src/static/js/curve-math.js';

describe('feet and inches, the way a tape reads', () => {
  it('converts a meter', () => {
    // 1 m = 39.3701 in = 3 ft 3.37 in, nearest eighth 3/8.
    expect(feetInches(1)).toBe(`3' 3 3/8"`);
  });

  it('drops the feet under a foot', () => {
    expect(feetInches(0.0127)).toBe(`1/2"`); // exactly half an inch
    expect(feetInches(0.1016)).toBe(`4"`); // exactly four inches
  });

  it('reads zero as zero', () => {
    expect(feetInches(0)).toBe(`0"`);
  });

  it('keeps the space when the inches are zero but there is a fraction', () => {
    // 6.411 m is 21 ft and three eighths of an inch: 21' 0 3/8", never 21' 03/8".
    expect(feetInches(6.411)).toBe(`21' 0 3/8"`);
  });

  it('rolls eight eighths up into the next inch, and twelve inches into the next foot', () => {
    expect(feetInches(0.304795)).toBe(`1' 0"`); // 11.9998 in, not 0' 12"
    expect(feetInches(0.3048)).toBe(`1' 0"`);
  });

  it('keeps a negative readable', () => {
    expect(feetInches(-0.0254)).toBe(`-1"`);
  });

  it('reduces the fraction', () => {
    expect(feetInches(0.0508)).toBe(`2"`);
    expect(feetInches(0.0635)).toBe(`2 1/2"`); // not 2 4/8"
  });
});

describe('unit conversion is lossless both ways', () => {
  it('round-trips imperial', () => {
    expect(fromDisplay(toDisplay(6.4, 'imperial'), 'imperial')).toBeCloseTo(6.4, 12);
  });

  it('leaves metric alone', () => {
    expect(toDisplay(6.4, 'metric')).toBe(6.4);
    expect(fromDisplay(6.4, 'metric')).toBe(6.4);
  });

  it('round-trips small distances in both systems', () => {
    for (const system of ['metric', 'imperial'])
      expect(fromSmallDisplay(toSmallDisplay(0.085, system), system)).toBeCloseTo(0.085, 12);
  });
});

describe('length readouts', () => {
  it('calls an infinite radius straight rather than printing Infinity', () => {
    expect(formatLength(Infinity, 'metric')).toBe('straight');
    expect(formatLength(Infinity, 'imperial')).toBe('straight');
  });

  it('gives a metric reader millimeters for the small stuff and meters for the rest', () => {
    expect(formatSmall(0.013, 'metric')).toBe('13 mm');
    expect(formatSmall(3.5, 'metric')).toBe('3.50 m');
  });

  it('gives an imperial reader inches for the same thing', () => {
    expect(formatSmall(0.013, 'imperial')).toBe(`1/2"`);
  });
});

describe('angles', () => {
  it('drops trailing zeros, because 7.50° is not how anyone says it', () => {
    expect(formatAngle(7.5)).toBe('7.5°');
    expect(formatAngle(5)).toBe('5°');
    expect(formatAngle(4.5001, 2)).toBe('4.5°');
    expect(formatAngle(2.3861, 2)).toBe('2.39°');
  });
});

// QA, 2026-11-10: the Curve's Close enough box read 0.98 in, the 25 mm
// default converted. A tape mark within half a millimeter reads as the mark.
describe('the Close enough box', () => {
  it('reads the 25 mm default as 1 in, and 25 in mm', () => {
    expect(toleranceField(25, 'imperial')).toBe('1');
    expect(toleranceField(25.4, 'imperial')).toBe('1');
    expect(toleranceField(25, 'metric')).toBe('25');
    expect(toleranceField(25.4, 'metric')).toBe('25.4');
  });
  it('reads an eighth as an eighth, and a typed hundredth as typed', () => {
    expect(toleranceField(12.7, 'imperial')).toBe('0.5');
    expect(toleranceField(3.175, 'imperial')).toBe('0.125');
    expect(toleranceField(0.3 * 25.4, 'imperial')).toBe('0.3');
    expect(toleranceField(0, 'imperial')).toBe('0');
  });
});

report();
