// The curve calculator's solve tests.
// Ported from the curve calculator's own tests; run by tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import {
  datumLabel,
  detentTable,
  inputErrors,
  makeCurve,
  snapDatum,
  solveCurve,
} from '../../src/static/js/curve-math.js';

/**
 * The contract. These are the numbers the crew builds to, so a change that moves
 * one of them is wrong until the geometry says otherwise.
 */

const curve = (over = () => {}) => {
  const c = makeCurve();
  over(c);
  return c;
};

describe('the headline case: a 20 % curve on sixteen 500 mm tiles', () => {
  const result = solveCurve(curve());

  it('wants 4.5° at every joint, which no footer does', () => {
    // 20 % of a circle is 72°, shared by sixteen panels.
    expect(result.ideal_angle_deg).toBeCloseTo(4.5, 9);
    expect(result.errors).toEqual([]);
    expect(result.uniform).toBe(false);
  });

  it('picks the simplest build that fits: one angle, 7.5°, with flats between', () => {
    expect(result.chosen_option_id).toBe('7.5');
    expect(result.recommended_option_id).toBe('7.5');
    expect(result.angle_usage).toEqual([{ angle_deg: 7.5, count: 9 }]);
    expect(result.flat_joints).toBe(6);
    expect(result.choice_reason).toContain('one angle (7.5°)');
  });

  it('stays within the 25 mm tolerance, and reads as the 20 % asked for', () => {
    expect(result.max_arc_deviation_m).toBeCloseTo(0.01361, 5);
    expect(result.achieved.percent_circle).toBeCloseTo(19.796, 3);
    // Inside tolerance: the reason line says how close it is; no second warning
    // contradicting it.
    expect(result.warnings.join(' ')).not.toContain('Off the drawing');
  });

  it('reports the wall the crew has to fit in the room', () => {
    // Measured from the wall's real corners (the 7.5° joints and the ends): a
    // circle through a point in the middle of a straight run read 6.471 m.
    expect(result.achieved.radius_face_m).toBeCloseTo(6.4237, 3);
    expect(result.achieved.chord_m).toBeCloseTo(7.4956, 3);
    expect(result.achieved.depth_m).toBeCloseTo(1.2045, 3);
    expect(result.achieved.arc_length_m).toBeCloseTo(8, 9);
  });

  it('reads the same from both ends', () => {
    const angles = result.joints.map((j) => j.angle_deg);
    expect(angles).toEqual([...angles].reverse());
  });

  it('lists every other way to build it, with the tighter fit it passed over', () => {
    const ids = result.options.map((o) => o.id);
    expect(ids[0]).toBe('7.5');
    expect(ids).toContain('2.5+7.5');
    expect(ids).toContain('2.5+5');
    const tighter = result.options.find((o) => o.id === '2.5+7.5') ;
    expect(tighter.deviation_m).toBeLessThan(result.max_arc_deviation_m);
    expect(result.choice_reason).toContain('needs 2 angles');
  });
});

describe('tightest fit, the old always-mix behavior, kept as a setting', () => {
  const result = solveCurve(curve((c) => (c.fit_goal = 'tightest')));

  it('takes whatever lands closest to the drawing, however many angles it uses', () => {
    expect(result.chosen_option_id).toBe('2.5+7.5');
    expect(result.max_arc_deviation_m).toBeCloseTo(0.00916, 5);
    const closest = Math.min(...result.options.map((o) => o.deviation_m));
    expect(result.max_arc_deviation_m).toBeCloseTo(closest, 9);
    expect(result.choice_reason).toContain('Tightest fit');
  });
});

describe('picking a build by hand', () => {
  it('builds the pattern the user chose and says the app would have picked another', () => {
    const result = solveCurve(curve((c) => (c.pattern_choice = '2.5+5')));
    expect(result.chosen_option_id).toBe('2.5+5');
    expect(result.recommended_option_id).toBe('7.5');
    expect(new Set(result.joints.map((j) => j.angle_deg))).toEqual(new Set([2.5, 5]));
    expect(result.choice_reason).toMatch(/^Your pick/);
  });

  it('falls back to the app\'s pick when the chosen pattern no longer exists', () => {
    // e.g. the user removed 2.5° from the footer list after picking it.
    const result = solveCurve(
      curve((c) => {
        c.pattern_choice = '2.5+5';
        c.hardware.detents_deg = [5, 7.5, 10];
      }),
);
    expect(result.chosen_option_id).toBe(result.recommended_option_id);
  });
});

describe('when nothing is close enough', () => {
  it('builds the closest it can and says so', () => {
    const result = solveCurve(curve((c) => (c.tolerance_m = 0.005)));
    expect(result.options.every((o) => !o.within_tolerance)).toBe(true);
    const closest = Math.min(...result.options.map((o) => o.deviation_m));
    expect(result.max_arc_deviation_m).toBeCloseTo(closest, 9);
    expect(result.choice_reason).toContain('Nothing these angles can build gets within 5.0 mm');
  });
});

describe('sweep is read off the shape, not the sum of the joints', () => {
  it('reads a 30 % wall built from 7.5° and flat joints as 30 %, not 27 %', () => {
    // The first cut summed the joints; with flat joints at both ends that read
    // 97.5° (27 %) for a wall sitting 15 mm off the drawn 30 % arc.
    const result = solveCurve(
      curve((c) => {
        c.panel.count = 24;
        c.target = { mode: 'percent_circle', value: 30, radius_ref: 'face' };
      }),
);
    expect(result.chosen_option_id).toBe('7.5');
    expect(result.joints[0].angle_deg).toBe(0);
    expect(result.achieved.percent_circle).toBeCloseTo(29.87, 1);
    expect(result.max_arc_deviation_m).toBeLessThan(0.025);
  });
});

describe('when the curve lands exactly on a detent', () => {
  const result = solveCurve(curve((c) => (c.target = { mode: 'angle_per_joint', value: 5, radius_ref: 'face' })));

  it('sets every joint the same and says nothing about closest matches', () => {
    expect(result.uniform).toBe(true);
    expect(result.pattern).toEqual([{ angle_deg: 5, count: 15, from: 1, to: 15 }]);
    expect(result.max_arc_deviation_m).toBeCloseTo(0, 9);
    expect(result.warnings.join(' ')).not.toContain('Closest match');
    expect(result.warnings.join(' ')).not.toContain('not all the same angle');
  });

  it('agrees with the hand-worked reference wall', () => {
    expect(result.achieved.radius_joints_m).toBeCloseTo(5.731396407, 7);
    expect(result.achieved.chord_m).toBeCloseTo(7.368141193, 7);
    expect(result.achieved.depth_m).toBeCloseTo(1.340892038, 7);
  });
});

describe('curves the hardware cannot build', () => {
  const result = solveCurve(
    curve((c) => {
      c.target = { mode: 'radius', value: 1.5, radius_ref: 'joints' };
    }),
);

  it('pins every joint at maximum rather than inventing an angle', () => {
    expect(result.joints.every((j) => j.angle_deg === 10)).toBe(true);
  });

  it('says how tight the panels can actually go', () => {
    const warning = result.warnings.find((w) => w.includes('Out of range'));
    expect(warning).toBeDefined();
    // To the front face, like every other radius on screen: 0.5 / (2 tan 5°) = 2.8575 m.
    // It used to quote the joint radius, 2.868 m, looser than the wall it built.
    expect(warning).toContain('2.858 m');
    expect(warning).toContain('Every joint is at 10°');
  });

  it('quotes that radius in whatever unit the user is working in', () => {
    const imperial = solveCurve(
      curve((c) => {
        c.target = { mode: 'radius', value: 1.5, radius_ref: 'joints' };
      }),
      'imperial',
);
    const warning = imperial.warnings.find((w) => w.includes('Out of range'));
    expect(warning).toContain(`9' 4 1/2"`);
    expect(warning).not.toContain(' m.');
  });
});

describe('errors stop the maths rather than poisoning it', () => {
  it('zeroes everything and explains why', () => {
    const result = solveCurve(curve((c) => (c.panel.count = 1)));
    expect(result.errors).toEqual(['A curve needs at least 2 panels across.']);
    expect(result.achieved.radius_face_m).toBe(0);
    expect(result.joints).toEqual([]);
    expect(result.warnings).toEqual([]);
  });

  it('refuses a straight-line width wider than the panels can make', () => {
    const result = solveCurve(curve((c) => (c.target = { mode: 'chord', value: 20, radius_ref: 'face' })));
    expect(result.errors.join(' ')).toContain('8.00 m wide');
  });

  it('never returns NaN, whatever is thrown at it', () => {
    const result = solveCurve(curve((c) => (c.panel.width_m = 0)));
    const finite = (v) =>
      typeof v === 'number'
        ? Number.isFinite(v)
        : typeof v === 'object' && v !== null
          ? Object.values(v).every(finite)
          : true;
    expect(finite(result.achieved)).toBe(true);
    expect(finite(result.target)).toBe(true);
  });
});

describe('direction', () => {
  const concave = solveCurve(curve((c) => (c.direction = 'concave')));
  const convex = solveCurve(curve((c) => (c.direction = 'convex')));

  it('builds the same size of curve either way', () => {
    expect(convex.achieved.chord_m).toBeCloseTo(concave.achieved.chord_m, 9);
    expect(convex.achieved.depth_m).toBeCloseTo(concave.achieved.depth_m, 9);
  });

  it('flips which way the wall bows in plan', () => {
    expect(concave.vertices[0].y).toBeGreaterThan(0);
    expect(convex.vertices[0].y).toBeLessThan(0);
  });
});

describe('the detent quick-reference table', () => {
  const rows = detentTable(curve());

  it('gives one row per angle the hardware offers, flat included', () => {
    expect(rows.map((r) => r.angle_deg)).toEqual([0, 2.5, 5, 7.5, 10]);
  });

  it('reports a flat wall as an infinite radius, not a huge number', () => {
    expect(rows[0].radius_m).toBe(Infinity);
    expect(rows[0].depth_m).toBeCloseTo(0, 9);
  });

  it('halves the radius as the angle doubles', () => {
    const at2p5 = rows[1].radius_m;
    const at5 = rows[2].radius_m;
    const at10 = rows[4].radius_m;
    expect(at2p5).toBeCloseTo(11.46, 2);
    expect(at5 / at2p5).toBeCloseTo(0.5, 2);
    expect(at10 / at5).toBeCloseTo(0.5, 2);
  });

  it('shows what share of a circle each angle wraps', () => {
    expect(rows[2].percent_circle).toBeCloseTo(22.222, 3);
    expect(rows[4].percent_circle).toBeCloseTo(44.444, 3);
  });
});

describe('the reference table reports the radius to the front face', () => {
  it('matches the face radius of a wall built at that angle', () => {
    // Sixteen 500 mm tiles at 5°: 5.725941387 m to the face, independently derived.
    const row = detentTable(curve()).find((r) => r.angle_deg === 5) ;
    expect(row.radius_m).toBeCloseTo(5.725941387, 8);
    const built = solveCurve(curve((c) => (c.target = { mode: 'angle_per_joint', value: 5, radius_ref: 'face' })));
    expect(row.radius_m).toBeCloseTo(built.achieved.radius_face_m, 8);
  });
});

describe('not every joint has to curve', () => {
  // The case that caught it: a 10 % curve on twenty 500 mm tiles with only a 5°
  // footer. A true arc wants 1.8° per joint. The old build set all nineteen
  // joints to 5° and built 100° of sweep against 36° asked for.
  const result = solveCurve(
    curve((c) => {
      c.panel.count = 20;
      c.target = { mode: 'percent_circle', value: 10, radius_ref: 'face' };
      c.hardware.detents_deg = [5];
    }),
);

  it('curves only as many joints as the sweep needs and leaves the rest straight', () => {
    const curved = result.joints.filter((j) => j.angle_deg === 5).length;
    const flat = result.joints.filter((j) => j.angle_deg === 0).length;
    expect(curved + flat).toBe(19);
    // 34.2° of turn wanted across the joints = about seven 5° joints.
    expect(curved).toBeGreaterThanOrEqual(6);
    expect(curved).toBeLessThanOrEqual(8);
  });

  it('lands close to the 36° asked for, not 100°', () => {
    expect(Math.abs(result.achieved.total_turn_deg - result.target.total_turn_deg)).toBeLessThanOrEqual(5);
    expect(result.achieved.percent_circle).toBeLessThan(13);
  });

  it('spreads the curved joints along the wall rather than bunching them', () => {
    const positions = result.joints.filter((j) => j.angle_deg === 5).map((j) => j.index);
    const gaps = positions.slice(1).map((p, i) => p - positions[i]);
    expect(Math.max(...gaps) - Math.min(...gaps)).toBeLessThanOrEqual(2);
  });
});

describe('audit findings: warnings judged against the build actually chosen', () => {
  const w = (r) => r.warnings.join(' | ');

  it('flags a build over tolerance even when its sweep matches the drawing', () => {
    // 38 panels at 54 %: sweep matched to 0.003° while the old fitter sat 50 mm
    // out, and no warning fired. Whatever the fitter now finds, a build over the
    // limit must say so.
    const r = solveCurve(curve((c) => { c.panel.count = 38; c.target.value = 54; c.tolerance_m = 0.001; }));
    expect(r.options.find((o) => o.id === r.chosen_option_id) .within_tolerance).toBe(false);
    expect(w(r)).toContain('Off the drawing');
  });

  it('tells you when your own pick is far off the drawing', () => {
    const r = solveCurve(curve((c) => (c.pattern_choice = '2.5')));
    expect(r.choice_reason).toMatch(/^Your pick lands .* over your 25 mm limit/);
    expect(w(r)).toContain('Off the drawing');
    expect(w(r)).toContain('gets to');
  });

  it('names a gentler build when the pick goes past 6°', () => {
    expect(w(solveCurve(curve()))).toContain('keeps every joint at 6° or under');
  });

  it('says how many joints are sharp and how many are flat', () => {
    const text = w(solveCurve(curve()));
    expect(text).toContain('The sharpest joints are 7.5° (9 of 15 joints)');
    expect(text).toContain('6 of 15 joints are flat');
  });

  it('warns when a curve was asked for and every joint came out flat', () => {
    // 0.5 % on twenty tiles is 1.8° of sweep in total; any 30° kink is far worse
    // than leaving the wall straight.
    const r = solveCurve(curve((c) => { c.panel.count = 20; c.target.value = 0.5; c.hardware.detents_deg = [30]; c.tolerance_m = 1; }));
    expect(r.flat_joints).toBe(19);
    expect(w(r)).toContain('Every joint is left flat');
  });

  it('fires the full-ring warning, which used to be unreachable', () => {
    const r = solveCurve(curve((c) => { c.target.value = 100; c.hardware.detents_deg = [22.5]; }));
    expect(r.achieved.percent_circle).toBeCloseTo(100, 6);
    expect(w(r)).toContain('closes into a full ring');
  });

  it('reads an odd panel count past a half round correctly, target and built alike', () => {
    const r = solveCurve(curve((c) => { c.panel.count = 3; c.target.value = 55; c.hardware.detents_deg = [66]; }));
    expect(r.target.percent_circle).toBeCloseTo(55, 6);
    expect(w(r)).toContain('past a half round');
  });
});

describe('audit findings: input the maths cannot use', () => {
  const errs = (f) => inputErrors(curve(f));

  it('refuses an empty angle list with a clear message', () => {
    expect(errs((c) => (c.hardware.detents_deg = []))).toContain('Add at least one angle the hardware can lock to.');
  });

  it('refuses a direction limit that rules out every angle', () => {
    expect(errs((c) => (c.hardware.max_concave_deg = 1)).join(' ')).toContain('No angle on your list is within the 1° concave limit');
  });

  it('refuses angles of 90° or more', () => {
    expect(errs((c) => (c.hardware.detents_deg = [180]))).toContain('Lock angles must be under 90°.');
  });

  it('caps the panel count, which used to crash the page', () => {
    expect(errs((c) => (c.panel.count = 100000))).toContain('Up to 500 panels across.');
  });

  it('says a fractional panel count must be whole, not that it is under 2', () => {
    expect(errs((c) => (c.panel.count = 2.5))).toContain('Panels across must be a whole number.');
  });

  it('refuses a negative direction limit', () => {
    expect(errs((c) => (c.hardware.max_convex_deg = -5)).join(' ')).toContain('convex limit must be a number, 0 or more');
  });
});

describe('building from the center, or from one end', () => {
  const at = (build_from) => solveCurve(curve((c) => (c.build_from = build_from)));

  it('center out mirrors the pattern about the middle', () => {
    const angles = at('center').joints.map((j) => j.angle_deg);
    expect(angles).toEqual([...angles].reverse());
  });

  it('pins the wall to the drawing at the datum it is built from', () => {
    // The datum is where wall and drawing touch, so their first/middle/last
    // vertex coincides there and the drift lands away from it.
    const left = at('left');
    expect(left.vertices[0].x).toBeCloseTo(left.target_vertices[0].x, 9);
    expect(left.vertices[0].y).toBeCloseTo(left.target_vertices[0].y, 9);
    const right = at('right');
    const last = right.vertices.length - 1;
    expect(right.vertices[last].x).toBeCloseTo(right.target_vertices[last].x, 9);
  });

  it('builds the right-hand datum as the mirror of the left-hand one', () => {
    expect(at('right').joints.map((j) => j.angle_deg)).toEqual(
      [...at('left').joints.map((j) => j.angle_deg)].reverse(),
);
  });

  it('builds the same curve whichever end it starts from', () => {
    for (const origin of ['left', 'right']) {
      expect(at(origin).achieved.percent_circle).toBeCloseTo(at('left').achieved.percent_circle, 6);
      expect(at(origin).achieved.arc_length_m).toBeCloseTo(8, 9);
    }
  });
});

describe('an even curve, or the closest one', () => {
  // 40 panels on 2.5 m footers (five panels each) with only a 5° lock. A true
  // 10 % arc wants 4.5° at each of the seven footer joints.
  const forty = (f = () => {}) =>
    curve((c) => {
      c.panel.count = 40;
      c.hardware.footer_widths_m = [2.5];
      c.hardware.detents_deg = [5];
      c.target = { mode: 'percent_circle', value: 10, radius_ref: 'face' };
      f(c);
    });

  it('defaults to the closest wall, which leaves two joints flat', () => {
    const r = solveCurve(forty());
    expect(r.joints.filter((j) => j.angle_deg > 0)).toHaveLength(5);
    expect(r.achieved.percent_circle).toBeCloseTo(9.72, 1);
  });

  it('builds an even curve when asked, and says what it costs', () => {
    const r = solveCurve(forty((c) => (c.fit_goal = 'even')));
    expect(r.joints.filter((j) => j.angle_deg > 0)).toHaveLength(7);
    expect(r.achieved.percent_circle).toBeCloseTo(11.11, 2);
    expect(r.choice_reason).toContain('a 5° bend after every 5 panels');
    expect(r.choice_reason).toContain('would not be even');
  });

  it('offers both, whichever is being used', () => {
    for (const goal of ['simplest', 'even', 'tightest']) {
      const options = solveCurve(forty((c) => (c.fit_goal = goal))).options;
      expect(options.some((o) => o.even && o.curved_joints === 7)).toBe(true);
      expect(options.some((o) => !o.even && o.curved_joints === 5)).toBe(true);
    }
  });

  it('leaves the wall straight rather than forcing a kink into every joint', () => {
    // A 0.5 % curve is gentler than one 5° joint. "Even" has to include a
    // straight wall, or it builds 11 % for an 0.5 % ask.
    const r = solveCurve(
      forty((c) => {
        c.fit_goal = 'even';
        c.target.value = 0.5;
      }),
);
    expect(r.joints.every((j) => j.angle_deg === 0)).toBe(true);
    expect(r.achieved.percent_circle).toBe(0);
  });

  it('measures 5° every five panels over forty panels as an 11.1 % curve', () => {
    // The owner's worked example, as a build rather than a target.
    const r = solveCurve(forty((c) => (c.target.value = 11.111)));
    expect(r.joints.filter((j) => j.angle_deg === 5)).toHaveLength(7);
    expect(r.achieved.percent_circle).toBeCloseTo(11.11, 2);
    expect(r.achieved.sweep_deg).toBeCloseTo(40, 6);
    // Exact now: 2.5 m runs at 5°, so 2.5 / (2 tan 2.5°) = 28.630 m. The circle
    // used to pass through a point mid-run and read 28.647 m.
    expect(r.achieved.radius_face_m).toBeCloseTo(2.5 / (2 * Math.tan((2.5 * Math.PI) / 180)), 6);
    expect(r.achieved.chord_m).toBeCloseTo(19.603, 2);
    expect(r.achieved.depth_m).toBeCloseTo(1.728, 2);
  });
});

describe('the plan is drawn level, whatever datum the maths used', () => {
  it('lays the wall flat on screen from any datum', () => {
    // Anchored at an end, that end sits square to the frame and the rest sweeps
    // away, on screen the whole wall looked tilted. Rotation is rigid, so it
    // changes nothing that was measured.
    for (const build_from of ['center', 'left', 'right']) {
      const r = solveCurve(curve((c) => (c.build_from = build_from)));
      const first = r.placements[0].face[0];
      const last = r.placements[r.placements.length - 1].face[1];
      expect(last.y - first.y).toBeCloseTo(0, 9);
    }
  });

  it('keeps the drawn arc lined up with the wall after leveling', () => {
    const r = solveCurve(curve((c) => (c.build_from = 'right')));
    const last = r.vertices.length - 1;
    // Right datum: wall and drawing still touch at the right-hand end.
    expect(r.vertices[last].x).toBeCloseTo(r.target_vertices[last].x, 9);
    expect(r.vertices[last].y).toBeCloseTo(r.target_vertices[last].y, 9);
  });

  it('leaves a center-built wall exactly where it was', () => {
    const r = solveCurve(curve());
    expect(r.vertices[8].x).toBeCloseTo(0, 9);
    expect(r.vertices[8].y).toBeCloseTo(0, 9);
  });

  it('puts the depth dimension on the leveled wall, not the old frame', () => {
    const r = solveCurve(curve((c) => (c.build_from = 'left')));
    const { depth_apex, depth_foot, depth_m } = r.achieved;
    expect(Math.hypot(depth_apex.x - depth_foot.x, depth_apex.y - depth_foot.y)).toBeCloseTo(depth_m, 9);
    // Square to a level chord means the dimension is vertical on screen.
    expect(depth_apex.x).toBeCloseTo(depth_foot.x, 6);
  });
});

describe('a datum panel picked off the plan', () => {
  const atPanel = (panel) => solveCurve(curve((c) => (c.build_from = panel)));

  it('pins the wall to the drawing at that panel', () => {
    const r = atPanel(4);
    // Panel 4's middle is the datum, so wall and drawing touch there.
    const wallMid = {
      x: (r.placements[3].face[0].x + r.placements[3].face[1].x) / 2,
      y: (r.placements[3].face[0].y + r.placements[3].face[1].y) / 2,
    };
    const drawnMid = { x: (r.target_vertices[3].x + r.target_vertices[4].x) / 2, y: (r.target_vertices[3].y + r.target_vertices[4].y) / 2 };
    expect(Math.hypot(wallMid.x - drawnMid.x, wallMid.y - drawnMid.y)).toBeLessThan(0.001);
  });

  it('builds the same curve wherever the datum sits', () => {
    for (const panel of [1, 4, 8, 13, 16]) {
      expect(atPanel(panel).achieved.percent_circle).toBeCloseTo(atPanel(8).achieved.percent_circle, 0);
      expect(atPanel(panel).achieved.arc_length_m).toBeCloseTo(8, 9);
    }
  });

  it('still draws level', () => {
    const r = atPanel(3);
    expect(r.placements[r.placements.length - 1].face[1].y - r.placements[0].face[0].y).toBeCloseTo(0, 9);
  });

  it('takes a panel outside the wall without breaking', () => {
    for (const panel of [0, -5, 999]) {
      const r = atPanel(panel);
      expect(r.errors).toEqual([]);
      expect(r.joints).toHaveLength(15);
      expect(Number.isFinite(r.max_arc_deviation_m)).toBe(true);
    }
  });
});

describe('a curve given in degrees', () => {
  it('builds exactly the same wall as the same curve in %', () => {
    const pct = solveCurve(curve());
    const deg = solveCurve(curve((c) => (c.target = { mode: 'sweep_deg', value: 72, radius_ref: 'face' })));
    expect(deg.ideal_angle_deg).toBeCloseTo(pct.ideal_angle_deg, 9);
    expect(deg.joints.map((j) => j.angle_deg)).toEqual(pct.joints.map((j) => j.angle_deg));
    expect(deg.achieved.percent_circle).toBeCloseTo(pct.achieved.percent_circle, 9);
  });

  it('refuses more than a full circle', () => {
    expect(inputErrors(curve((c) => (c.target = { mode: 'sweep_deg', value: 400, radius_ref: 'face' })))).toContain(
      'Total sweep must be between 0° and 360°.',
);
  });
});

describe('straight runs between bends are measured from the corners', () => {
  // Three panels, then a 5° bend, five times: fifteen 500 mm panels, four bends.
  // Five equal 1.5 m runs on one circle, each covering 5° of it.
  const runs = (count) =>
    solveCurve(
      curve((c) => {
        c.panel.count = count * 3;
        c.hardware.footer_widths_m = [1.5];
        c.hardware.detents_deg = [5];
        c.fit_goal = 'even';
        c.target = { mode: 'sweep_deg', value: count * 5, radius_ref: 'face' };
      }),
);

  it('reads five 3-panel runs at 5° as 25°, not 24.1°', () => {
    // With an odd number of runs the middle vertex sits inside a straight run,
    // and a circle through it read 24.11°.
    const r = runs(5);
    expect(r.joints.filter((j) => j.angle_deg === 5)).toHaveLength(4);
    expect(r.achieved.sweep_deg).toBeCloseTo(25, 6);
    expect(r.achieved.percent_circle).toBeCloseTo(6.944, 3);
  });

  it('gives every run the same radius to the face, odd count or even', () => {
    const hand = 1.5 / (2 * Math.tan((2.5 * Math.PI) / 180)); // 17.178 m
    expect(runs(5).achieved.radius_face_m).toBeCloseTo(hand, 6);
    expect(runs(4).achieved.radius_face_m).toBeCloseTo(hand, 6);
  });

  it('reads four runs as 20°', () => {
    expect(runs(4).achieved.sweep_deg).toBeCloseTo(20, 6);
    expect(runs(4).achieved.percent_circle).toBeCloseTo(5.556, 3);
  });
});

describe('a datum on a joint between two panels', () => {
  const at = (build_from) => solveCurve(curve((c) => (c.build_from = build_from)));

  it('between panels 8 and 9 on sixteen panels is the center', () => {
    const joint = at(8.5);
    const center = at('center');
    expect(joint.joints.map((j) => j.angle_deg)).toEqual(center.joints.map((j) => j.angle_deg));
    expect(joint.max_arc_deviation_m).toBeCloseTo(center.max_arc_deviation_m, 9);
  });

  it('touches the drawing at that joint', () => {
    const r = at(5.5); // between panels 5 and 6: vertex 5
    expect(Math.hypot(r.vertices[5].x - r.target_vertices[5].x, r.vertices[5].y - r.target_vertices[5].y)).toBeLessThan(1e-9);
  });

  it('treats the joints at the very ends as the ends', () => {
    expect(at(0.5).joints.map((j) => j.angle_deg)).toEqual(at('left').joints.map((j) => j.angle_deg));
    expect(at(16.5).joints.map((j) => j.angle_deg)).toEqual(at('right').joints.map((j) => j.angle_deg));
  });

  it('snaps anything in between to the nearest panel middle or joint', () => {
    expect(snapDatum(8.4, 16)).toBe(8.5);
    expect(snapDatum(8.2, 16)).toBe(8);
    expect(snapDatum(-3, 16)).toBe(0.5);
    expect(snapDatum(99, 16)).toBe(16.5);
    expect(datumLabel(8.5)).toBe('between panels 8 and 9');
    expect(datumLabel(5)).toBe('panel 5');
  });

  it('still draws level', () => {
    const r = at(3.5);
    expect(r.placements[r.placements.length - 1].face[1].y - r.placements[0].face[0].y).toBeCloseTo(0, 9);
  });
});

describe('an even curve on mixed footer stock', () => {
  // The owner's case: fifteen 500 mm panels, 1 m and 0.5 m footers, 5° locks,
  // and a 5° bend after every third panel. Each 3-panel run is a 1 m plus a
  // 0.5 m footer, and the join between those two stays flat.
  const wall = (fit_goal) =>
    solveCurve(
      curve((c) => {
        c.panel.count = 15;
        c.hardware.footer_widths_m = [0.5, 1];
        c.hardware.detents_deg = [5];
        c.target = { mode: 'sweep_deg', value: 25, radius_ref: 'face' };
        c.fit_goal = fit_goal;
      }),
);

  it('bends after every third panel, whichever goal is picked', () => {
    for (const goal of ['simplest', 'even', 'tightest']) {
      const r = wall(goal);
      expect(r.joints.filter((j) => j.angle_deg > 0).map((j) => j.index)).toEqual([3, 6, 9, 12]);
      expect(r.achieved.sweep_deg).toBeCloseTo(25, 6);
    }
  });

  it('builds each run from a 1 m and a 0.5 m footer', () => {
    const r = wall('even');
    expect(r.footers.reduce((s, f) => s + f.panels, 0)).toBe(15);
    expect(new Set(r.footers.map((f) => f.width_m))).toEqual(new Set([0.5, 1]));
  });

  it('calls it what a crew would', () => {
    expect(wall('even').choice_reason).toContain('a 5° bend after every 3 panels');
  });

  it('used to find no even wall at all here', () => {
    // "Even" once meant every joint that COULD bend, including the join inside
    // each run, so the only even answers were 45° or flat, and it picked flat.
    expect(wall('even').achieved.percent_circle).toBeGreaterThan(6);
  });
});

report();
