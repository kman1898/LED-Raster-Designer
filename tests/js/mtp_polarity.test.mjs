// An MTP's far-end legs by its polarity (mtp-polarity.js, owner
// 2026-11-18); run by tests/test_curve_math.py with every *.test.mjs here.
import { describe, it, expect, report } from './harness.mjs';
import {
  MTP_POLARITIES,
  MTP_SEE_MAP,
  mtpPolarity,
  mtpPolarityWord,
  mtpFarPosition,
  mtpMapDocumented,
  mtpLegsAtBreakout,
} from '../../src/static/js/mtp-polarity.js';

const range = (n) => Array.from({ length: n }, (_, i) => i + 1);
const map = (count, p) => range(count).map(n => mtpFarPosition(n, count, p));

describe('the polarity a cable reads', () => {
  it('is Type A where none is stored (an older show)', () => {
    expect(mtpPolarity({ kind: 'mtp', strands: 12 })).toBe('A');
    expect(mtpPolarity(null)).toBe('A');
    expect(mtpPolarity({ polarity: 'Z' })).toBe('A');
  });

  it('is its own where one is stored', () => {
    expect(mtpPolarity({ polarity: 'B' })).toBe('B');
    expect(mtpPolarity({ polarity: 'C' })).toBe('C');
  });

  it('offers A, B and C, A first, in plain words', () => {
    expect(MTP_POLARITIES).toEqual(['A', 'B', 'C']);
    expect(MTP_POLARITIES.map(mtpPolarityWord)).toEqual(['Type A', 'Type B', 'Type C']);
    expect(MTP_SEE_MAP).toBe('see cable map');
  });
});

describe('12 fiber', () => {
  it('Type A is straight: n -> n', () => {
    expect(map(12, 'A')).toEqual(range(12));
  });

  it('Type B reverses: n -> 13 - n', () => {
    expect(map(12, 'B')).toEqual([12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]);
  });

  it('Type C swaps each pair', () => {
    expect(map(12, 'C')).toEqual([2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11]);
  });
});

describe('24 fiber, two rows', () => {
  it('Type A swaps the rows: leg 1 -> leg 13, 13 -> 1', () => {
    expect(map(24, 'A')).toEqual([...range(12).map(n => n + 12), ...range(12)]);
    expect(mtpFarPosition(1, 24, 'A')).toBe(13);
    expect(mtpFarPosition(24, 24, 'A')).toBe(12);
  });

  it('Type B reverses: n -> 25 - n', () => {
    expect(map(24, 'B')).toEqual(range(24).map(n => 25 - n));
  });

  it('Type C is the row swap then the pair swap: 1 -> 14, 2 -> 13', () => {
    expect(mtpFarPosition(1, 24, 'C')).toBe(14);
    expect(mtpFarPosition(2, 24, 'C')).toBe(13);
    expect(mtpFarPosition(13, 24, 'C')).toBe(2);
    expect(mtpFarPosition(14, 24, 'C')).toBe(1);
  });

  it('every documented map is one to one', () => {
    for (const [count, p] of [[12, 'A'], [12, 'B'], [12, 'C'], [24, 'A'], [24, 'B'], [24, 'C'],
                              [16, 'B'], [32, 'B']]) {
      expect([...map(count, p)].sort((a, b) => a - b)).toEqual(range(count));
    }
  });
});

describe('16 and 32 fiber', () => {
  it('16 Type B reverses: n -> 17 - n', () => {
    expect(map(16, 'B')).toEqual(range(16).map(n => 17 - n));
  });

  it('32 Type B reverses each row of 16 on its own', () => {
    expect(map(32, 'B')).toEqual([...range(16).map(n => 17 - n), ...range(16).map(n => 33 - n)]);
    expect(mtpFarPosition(17, 32, 'B')).toBe(32);
    expect(mtpFarPosition(32, 32, 'B')).toBe(17);
  });
});

describe('nothing undocumented is guessed', () => {
  it('48, 72 and other counts have no map in any type', () => {
    for (const count of [2, 4, 6, 8, 10, 36, 48, 72, 96, 144]) {
      for (const p of MTP_POLARITIES) {
        expect(mtpFarPosition(1, count, p)).toBe(null);
        expect(mtpMapDocumented(count, p)).toBe(false);
      }
    }
  });

  it('16 and 32 have a map in Type B only', () => {
    for (const count of [16, 32]) {
      expect(mtpMapDocumented(count, 'A')).toBe(false);
      expect(mtpMapDocumented(count, 'B')).toBe(true);
      expect(mtpMapDocumented(count, 'C')).toBe(false);
    }
  });

  it('8 fiber is left to the cable map in every type, numbering untouched', () => {
    for (const p of MTP_POLARITIES) expect(mtpLegsAtBreakout([1, 2], 8, p)).toBe(null);
  });

  it('a strand off the cable has no leg', () => {
    expect(mtpFarPosition(13, 12, 'A')).toBe(null);
    expect(mtpFarPosition(0, 12, 'A')).toBe(null);
  });
});

describe('the legs as they plug in at the breakout', () => {
  it('MTP-24 Type A: the processor 1 · 2 read 14 · 13 at the breakout', () => {
    expect(mtpLegsAtBreakout([1, 2], 24, 'A')).toEqual([14, 13]);
    expect(mtpLegsAtBreakout([3, 4], 24, 'A')).toEqual([16, 15]);
  });

  it('MTP-12 Type A flips the pair the way a TAC does', () => {
    expect(mtpLegsAtBreakout([1, 2], 12, 'A')).toEqual([2, 1]);
  });

  it('a Type B trunk already crosses the pair, so no second swap', () => {
    // delivered on 12 and 11: the box takes them in the far end's order
    expect(mtpLegsAtBreakout([1, 2], 12, 'B')).toEqual([11, 12]);
    expect(mtpLegsAtBreakout([1, 2], 24, 'B')).toEqual([23, 24]);
    expect(mtpLegsAtBreakout([1, 2], 16, 'B')).toEqual([15, 16]);
    expect(mtpLegsAtBreakout([17, 18], 32, 'B')).toEqual([31, 32]);
  });

  it('a Type C trunk already crosses the pair, so no second swap', () => {
    expect(mtpLegsAtBreakout([1, 2], 12, 'C')).toEqual([1, 2]);
    expect(mtpLegsAtBreakout([1, 2], 24, 'C')).toEqual([13, 14]);
  });

  it('the box first place always takes the leg of the processor second strand', () => {
    for (const [count, p] of [[12, 'A'], [12, 'B'], [12, 'C'], [24, 'A'], [24, 'B'], [24, 'C']]) {
      const legs = mtpLegsAtBreakout([5, 6], count, p);
      expect(legs).toEqual([mtpFarPosition(6, count, p), mtpFarPosition(5, count, p)]);
    }
  });

  it('a BiDi link has its one leg', () => {
    expect(mtpLegsAtBreakout([1], 24, 'A')).toEqual([13]);
  });

  it('a pair stored the other way round flips with it', () => {
    expect(mtpLegsAtBreakout([2, 1], 24, 'A')).toEqual([13, 14]);
  });

  it('no strands, no legs; an undocumented count, no numbers at all', () => {
    expect(mtpLegsAtBreakout([], 48, 'A')).toEqual([]);
    expect(mtpLegsAtBreakout([1, 2], 48, 'A')).toBe(null);
  });
});

report();
