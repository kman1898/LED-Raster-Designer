// The curve calculator's footers tests.
// Ported from the curve calculator's own tests; run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import {
  describeFooters,
  footerPlan,
  makeCurve,
  panelsUnder,
  searchLayouts,
  solveCurve,
} from '../../src/static/js/curve-math.js';

/**
 * Footers are bars under one or more panels, entered as a run that repeats
 * along the wall. Whatever a footer spans is rigid, only the joins between
 * footers can take a curve.
 */

const wall = (over) => {
  const c = makeCurve();
  over(c);
  return c;
};

describe('how many panels a footer covers', () => {
  it('counts whole panels', () => {
    expect(panelsUnder(0.5, 0.5)).toBe(1);
    expect(panelsUnder(1, 0.5)).toBe(2);
    expect(panelsUnder(1.5, 0.5)).toBe(3);
  });

  it('never drops below one, whatever it is handed', () => {
    expect(panelsUnder(0, 0.5)).toBe(1);
    expect(panelsUnder(0.5, 0)).toBe(1);
    expect(panelsUnder(NaN, 0.5)).toBe(1);
  });
});

describe('the calculator decides where the footers go', () => {
  // The owner's stock: 0.5 m and 1 m bars under 500 mm panels. Which bar goes
  // where is the calculator's job, a 1 m footer buys a rigid pair, a 0.5 m one
  // buys a joint that can bend.
  const config = wall((c) => {
    c.panel.count = 16;
    c.hardware.footer_widths_m = [0.5, 1];
  });
  const result = solveCurve(config);

  it('covers the wall exactly, with no footer hanging off the end', () => {
    expect(result.footers.reduce((s, f) => s + f.panels, 0)).toBe(16);
    expect(result.footers.every((f) => !f.part)).toBe(true);
  });

  it('uses both sizes, putting the short ones where the wall has to bend', () => {
    const sizes = new Set(result.footers.map((f) => f.width_m));
    expect(sizes.has(0.5)).toBe(true);
    expect(sizes.has(1)).toBe(true);
    // Every angle sits on a footer join.
    const free = footerPlan(config, result.footers.map((f) => f.width_m)).free;
    result.joints.forEach((j) => {
      if (j.angle_deg > 0) expect(free.has(j.index - 1)).toBe(true);
    });
  });

  it('gets closer than it could with the wide footers alone', () => {
    const wideOnly = solveCurve(wall((c) => {
      c.panel.count = 16;
      c.hardware.footer_widths_m = [1];
    }));
    expect(result.max_arc_deviation_m).toBeLessThanOrEqual(wideOnly.max_arc_deviation_m);
  });

  it('counts the layout back the way a crew would', () => {
    expect(describeFooters(result.footers, (m) => `${m} m`)).toMatch(/0\.5 m/);
  });
});

describe('the layout search', () => {
  it('only ever lays footers that fit the wall', () => {
    for (const panelCount of [7, 12, 15, 16]) {
      const found = searchLayouts({
        panelCount,
        panelWidthM: 0.5,
        sizes: [0.5, 1],
        angles: [0, 5],
        idealDeg: 4.5,
        beamWidth: 40,
        keep: 5,
      });
      expect(found.length).toBeGreaterThan(0);
      for (const c of found) {
        const panels = c.run_m.reduce((s, w) => s + panelsUnder(w, 0.5), 0);
        expect(panels).toBeGreaterThanOrEqual(panelCount);
        expect(c.joints).toHaveLength(panelCount - 1);
      }
    }
  });

  it('leaves the joints a footer spans flat', () => {
    const [best] = searchLayouts({
      panelCount: 12,
      panelWidthM: 0.5,
      sizes: [0.5, 1],
      angles: [0, 5],
      idealDeg: 4.5,
      beamWidth: 40,
      keep: 1,
    });
    let panel = 0;
    for (const w of best.run_m) {
      const k = panelsUnder(w, 0.5);
      // Joints strictly inside this footer cannot carry an angle.
      for (let j = 1; j < k; j++) expect(best.joints[panel + j - 1]).toBe(0);
      panel += k;
    }
  });
});

describe('what the footers cost the curve', () => {
  it('quotes the tightest radius off a whole footer, not one panel', () => {
    // 1 m footers at 5°: 1.0 / (2 tan 2.5°) = 11.46 m, not the 5.73 m a single
    // 500 mm panel would suggest.
    const r = solveCurve(
      wall((c) => {
        c.hardware.footer_widths_m = [1];
        c.hardware.detents_deg = [5];
        c.target.value = 40;
      }),
);
    const warning = r.warnings.find((w) => w.includes('Out of range'));
    expect(warning).toContain('11.45 m');
  });

  it('spells out the layout it chose and where the wall bends', () => {
    const r = solveCurve(wall((c) => (c.hardware.footer_widths_m = [0.5, 1])));
    const warning = r.warnings.find((w) => w.startsWith('Bars:'));
    expect(warning).toContain('laid out in the build sheet');
    expect(warning).toMatch(/bends at \d+ of its \d+ joints, after panel/);
  });

  it('leaves every joint free when there is one footer per panel', () => {
    const plan = footerPlan(wall((c) => (c.hardware.footer_widths_m = [0.5])));
    expect(plan.free.size).toBe(15);
    expect(plan.maxPanels).toBe(1);
  });
});

report();
