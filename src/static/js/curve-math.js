// curve-math: the curve calculator's math for the Header/Footer tab's Curve.
// A wall of flat panels joined by curve locks (the header or footer bars)
// that only lock at certain angles: given the curve asked for, it works out
// which bars go where, the angle at every join between bars, what that
// actually builds (sweep, % of a circle, radius to the front face, width,
// depth) and how far it lands off the drawn arc.
//
// Plain functions, no DOM: tests/test_curve_math.py runs this file under
// node with the curve calculator's own tests (tests/js/curve_*.test.mjs),
// and the app imports it as an ES module (app-curve.js).
//
// The house rules, from the curve calculator's owner (do not reverse them):
// - A curve is how much of a full circle the wall covers, measured on the
//   front face of the LED, entered as a % or as degrees of sweep.
// - Radius is to the front face; the locks pivot in the face plane.
// - A joint can always be left flat. A joint inside a bar cannot bend.
// - The bar sizes are stock, not an order: the calculator decides where
//   each bar goes. No per-joint angle pinning.
// - "Even" is one angle at a regular spacing. Simplest is the default.
// - Everything reported is measured off the built polygon, sweep through
//   corners only; a closest match is never presented as exact.
// - SI inside (meters, degrees); imperial only at the display (Units).
// - Bad input returns errors and a zeroed result, never NaN.

// ---- Units: the only place imperial exists ---------------------------------
/**
 * The only place imperial exists. Everything upstream is meters and degrees.
 */

const M_PER_FT = 0.3048;
const M_PER_IN = 0.0254;

/** A meter value in the user's working unit, for an editable field. */
export function toDisplay(m, system) {
  return system === 'imperial' ? m / M_PER_FT : m;
}

/** Back to meters from whatever the user typed. */
export function fromDisplay(v, system) {
  return system === 'imperial' ? v * M_PER_FT : v;
}

export const lengthUnitLabel = (system) => (system === 'imperial' ? 'ft' : 'm');

/** Feet and inches to the nearest eighth, the way a tape reads. */
export function feetInches(m) {
  if (!Number.isFinite(m)) return '';
  const sign = m < 0 ? '-' : '';
  const totalIn = Math.abs(m) / M_PER_IN;
  let ft = Math.floor(totalIn / 12);
  let inches = totalIn - ft * 12;

  let whole = Math.floor(inches);
  let eighths = Math.round((inches - whole) * 8);
  if (eighths === 8) {
    eighths = 0;
    whole += 1;
  }
  if (whole === 12) {
    whole = 0;
    ft += 1;
  }

  const g = gcd(eighths, 8);
  const frac = eighths === 0 ? '' : `${eighths / g}/${8 / g}`;
  const inchPart = (n) => `${n}${frac ? ` ${frac}` : ''}"`;

  // Under a foot, read it the way a tape does: 1/2", not 0' 0 1/2". The whole
  // inches are only dropped when there are none AND a fraction to show instead.
  if (ft === 0) return `${sign}${whole === 0 && frac ? `${frac}"` : inchPart(whole)}`;
  return `${sign}${ft}' ${inchPart(whole)}`;
}

function gcd(a, b) {
  return b === 0 ? a : gcd(b, a % b);
}

/** Primary length readout in the chosen system. */
export function formatLength(m, system) {
  if (!Number.isFinite(m)) return 'straight';
  if (system === 'imperial') return feetInches(m);
  return `${m.toFixed(m < 10 ? 3 : 2)} m`;
}

/** The same value in the other system, for the small print beside it. */
export function formatLengthAlt(m, system) {
  if (!Number.isFinite(m)) return '';
  return system === 'imperial' ? `${m.toFixed(3)} m` : feetInches(m);
}

/**
 * Small distances, how far off an arc, how much a wall runs over. Millimeters
 * read better than "0.013 m" on a metric job; feet and inches on an imperial one.
 */
export function formatSmall(m, system) {
  if (!Number.isFinite(m)) return '';
  if (system === 'imperial') return feetInches(m);
  return Math.abs(m) < 1 ? formatMm(m) : `${m.toFixed(2)} m`;
}

export function formatMm(m) {
  if (!Number.isFinite(m)) return '';
  const mm = m * 1000;
  return `${Math.abs(mm) < 10 ? mm.toFixed(1) : mm.toFixed(0)} mm`;
}

/** Angles without trailing zeros: 5°, 7.5°, 2.39°. */
export function formatAngle(deg, places = 2) {
  if (!Number.isFinite(deg)) return '';
  const rounded = Number(deg.toFixed(places));
  return `${rounded}°`;
}

export function formatPercent(pct, places = 1) {
  if (!Number.isFinite(pct)) return '';
  return `${pct.toFixed(places)}%`;
}

/** Small distances as an editable number: millimeters, or inches on an imperial job. */
export const toSmallDisplay = (m, system) =>
  system === 'imperial' ? m / M_PER_IN : m * 1000;
export const fromSmallDisplay = (v, system) =>
  system === 'imperial' ? v * M_PER_IN : v / 1000;
export const smallUnitLabel = (system) => (system === 'imperial' ? 'inches' : 'mm');

/** A short length for a label: "0.5 m", "1 m", "1.5 m", or feet and inches. */
export function formatShortLength(m, system) {
  if (!Number.isFinite(m)) return '';
  if (system === 'imperial') return feetInches(m);
  return `${Number(m.toFixed(3))} m`;
}

// ---- Geometry: the wall built panel by panel, and measured -----------------


/**
 * Plan-view geometry.
 *
 * Everything the app reports is measured off a polyline that is actually built
 * panel by panel, rather than read out of an idealised arc formula. That matters
 * the moment the joints carry mixed detents: the shape is then a polygon that no
 * single radius describes, and only the built geometry tells the truth about
 * where the ends land.
 *
 * Frame: +x runs along the wall left to right, +y points at the audience. The
 * wall is centerd so its midpoint sits at the origin facing +y, which is how a
 * crew builds it, from the center out.
 */

export const rad = (deg) => (deg * Math.PI) / 180;
export const deg = (r) => (r * 180) / Math.PI;

/** Angle a panel of width `w` subtends on a circle of radius `R` through the joints. */
export function angleForChord(w, R) {
  if (!(R > 0) || !Number.isFinite(R)) return 0;
  const ratio = w / (2 * R);
  if (ratio >= 1) return 180; // Panel is wider than the circle: geometrically impossible.
  return 2 * deg(Math.asin(ratio));
}

/** Radius of the circle through the joints, given panel width and the angle per joint. */
export function radiusForAngle(w, angleDeg) {
  if (angleDeg <= 0) return Infinity;
  return w / (2 * Math.sin(rad(angleDeg) / 2));
}

/**
 * Radius to the front face of the panels, given the angle per joint, the
 * distance from the center to the middle of each tile, w / (2 tan(angle/2)).
 */
export function faceRadiusForAngle(w, angleDeg) {
  if (angleDeg <= 0) return Infinity;
  return w / (2 * Math.tan(rad(angleDeg) / 2));
}

/** Depth of a circular arc of radius R spanning `sweepDeg`. */
export function arcDepth(R, sweepDeg) {
  if (!Number.isFinite(R)) return 0;
  return R * (1 - Math.cos(rad(sweepDeg) / 2));
}

/** Straight-line chord of a circular arc of radius R spanning `sweepDeg`. */
export function arcChord(R, sweepDeg) {
  if (!Number.isFinite(R)) return 0;
  return 2 * R * Math.sin(rad(sweepDeg) / 2);
}

function rotate(p, a) {
  const c = Math.cos(a);
  const s = Math.sin(a);
  return { x: p.x * c - p.y * s, y: p.x * s + p.y * c };
}

/** Perpendicular distance from `p` to the infinite line through a and b. */
function distanceToLine(p, a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return Math.hypot(p.x - a.x, p.y - a.y);
  return Math.abs(dy * (p.x - a.x) - dx * (p.y - a.y)) / len;
}

/** Where `p` lands when dropped perpendicularly onto the line through a and b. */
function footOnLine(p, a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return a;
  const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  return { x: a.x + t * dx, y: a.y + t * dy };
}

/** Center of the circle through three points, or null when they are collinear. */
function circumcenter(a, b, c) {
  const bx = b.x - a.x;
  const by = b.y - a.y;
  const cx = c.x - a.x;
  const cy = c.y - a.y;
  const d = 2 * (bx * cy - by * cx);
  if (Math.abs(d) < 1e-15) return null;
  const b2 = bx * bx + by * by;
  const c2 = cx * cx + cy * cy;
  return { x: a.x + (cy * b2 - by * c2) / d, y: a.y + (bx * c2 - cx * b2) / d };
}

/**
 * A dragged datum, snapped to something a crew can set out from: the middle of
 * a panel (a whole number) or a joint (a half), within the wall.
 */
export function snapDatum(position, panelCount) {
  const half = Math.round(position * 2) / 2;
  return Math.min(Math.max(half, 0.5), panelCount + 0.5);
}

/** "panel 5", or "between panels 8 and 9" for a joint. */
export function datumLabel(at) {
  if (Number.isInteger(at)) return `panel ${at}`;
  const k = at - 0.5;
  return `between panels ${k} and ${k + 1}`;
}

/**
 * Walk the wall panel by panel, then sit it on its datum.
 *
 * The datum is where the wall and the drawing touch: the middle for a wall built
 * center out, or the fixed end for one built from an end. Deviation is measured
 * in this frame, so the anchor decides where drift shows up.
 *
 * Concave turns left (center of curvature in front of the screen, at +y);
 * convex turns right. Panel faces sit `pivotOffsetM` in front of the hinge
 * polyline along each panel's own normal, which is what opens the joint gap.
 */
export function buildCurve(input) {
  const { widths, joints, direction, pivotOffsetM, panelDepthM, wallHeightM } = input;
  const anchor = input.anchor ?? 'center';
  const n = widths.length;
  const turnSign = direction === 'concave' ? 1 : -1;

  // 1. Walk the hinge polyline, accumulating heading.
  const headings = [];
  const pts = [{ x: 0, y: 0 }];
  let h = 0;
  for (let i = 0; i < n; i++) {
    if (i > 0) h += turnSign * rad(joints[i - 1] ?? 0);
    headings.push(h);
    const prev = pts[i];
    pts.push({ x: prev.x + widths[i] * Math.cos(h), y: prev.y + widths[i] * Math.sin(h) });
  }

  // 2. Put the datum at the origin, facing +y. Center out, that is the middle
  //    joint (even panel count) or the middle of the center panel (odd); from an
  //    end, it is that end's corner and that panel's heading.
  let anchorPoint;
  let anchorHeading;
  if (typeof anchor === 'number') {
    const at = snapDatum(anchor, n);
    if (Number.isInteger(at)) {
      // The middle of a panel, square to the frame.
      anchorPoint = { x: (pts[at - 1].x + pts[at].x) / 2, y: (pts[at - 1].y + pts[at].y) / 2 };
      anchorHeading = headings[at - 1];
    } else {
      // A joint: the corner itself, split evenly between the panels either side.
      // At either end there is only one panel to take the heading from.
      const k = at - 0.5; // vertex index: joint between panels k and k+1
      anchorPoint = pts[k];
      anchorHeading =
        k === 0 ? headings[0] : k === n ? headings[n - 1] : (headings[k - 1] + headings[k]) / 2;
    }
  } else if (anchor === 'left') {
    anchorPoint = pts[0];
    anchorHeading = headings[0];
  } else if (anchor === 'right') {
    anchorPoint = pts[n];
    anchorHeading = headings[n - 1];
  } else if (n % 2 === 0) {
    anchorPoint = pts[n / 2];
    anchorHeading = (headings[n / 2 - 1] + headings[n / 2]) / 2;
  } else {
    const i = (n - 1) / 2;
    anchorPoint = { x: (pts[i].x + pts[i + 1].x) / 2, y: (pts[i].y + pts[i + 1].y) / 2 };
    anchorHeading = headings[i];
  }
  const spin = -anchorHeading;
  const shifted = pts.map((p) => rotate({ x: p.x - anchorPoint.x, y: p.y - anchorPoint.y }, spin));
  const finalHeadings = headings.map((a) => a + spin);

  // 3. Offset each panel face forward along its own normal. The front normal of
  //    a panel running left to right at heading a is (-sin a, cos a).
  const placements = [];
  for (let i = 0; i < n; i++) {
    const a = finalHeadings[i];
    const nx = -Math.sin(a);
    const ny = Math.cos(a);
    const face = [
      { x: shifted[i].x + pivotOffsetM * nx, y: shifted[i].y + pivotOffsetM * ny },
      { x: shifted[i + 1].x + pivotOffsetM * nx, y: shifted[i + 1].y + pivotOffsetM * ny },
];
    const rear = [
      { x: face[0].x - panelDepthM * nx, y: face[0].y - panelDepthM * ny },
      { x: face[1].x - panelDepthM * nx, y: face[1].y - panelDepthM * ny },
];
    placements.push({ index: i + 1, face, rear, heading_deg: deg(a) });
  }

  return {
    vertices: shifted,
    placements,
    measurements: measure({ vertices: shifted, placements, joints, widths, wallHeightM }),
  };
}

function measure(input) {
  const { vertices, placements, joints, widths, wallHeightM } = input;

  const facePts = placements.flatMap((p) => [p.face[0], p.face[1]]);
  const start = facePts[0];
  const end = facePts[facePts.length - 1];

  const chord = Math.hypot(end.x - start.x, end.y - start.y);
  const faceMids = placements.map((p) => ({
    x: (p.face[0].x + p.face[1].x) / 2,
    y: (p.face[0].y + p.face[1].y) / 2,
  }));

  // The deepest point is the one furthest from the chord line, which on a
  // concave wall is the middle, NOT the point furthest from the origin, since
  // the frame is centerd on the middle and it is the ends that swing out. Panel
  // midpoints are candidates too: on an odd panel count the center panel is
  // parallel to the chord, and its midpoint, not a corner, is where the depth
  // dimension belongs. Ties go to the point nearest the middle of the chord.
  const chordMid = { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
  let depth = 0;
  let apex = chordMid;
  let apexOffset = Infinity;
  for (const p of [...facePts, ...faceMids]) {
    const d = distanceToLine(p, start, end);
    const off = Math.hypot(p.x - chordMid.x, p.y - chordMid.y);
    if (d > depth + 1e-9 || (Math.abs(d - depth) <= 1e-9 && off < apexOffset)) {
      depth = Math.max(depth, d);
      apex = p;
      apexOffset = off;
    }
  }

  const totalTurn = joints.reduce((s, a) => s + a, 0);

  // Effective radius through first / middle / last, which is exact for a true
  // arc and a fair summary of a mixed-detent polygon.
  // The wall's shape is set by its CORNERS, the ends and every joint that
  // actually bends. A vertex inside a straight run (a flat joint, or the joints
  // a wide footer holds rigid) lies on a chord, not on the curve, so a circle
  // through one of those reads the wall wrong: five 3-panel runs at 5° a joint
  // read 24.1° of sweep instead of 25°. Fit the circle through corners only.
  const corners = [0];
  joints.forEach((a, i) => {
    if (a !== 0) corners.push(i + 1);
  });
  corners.push(vertices.length - 1);

  const first = vertices[0];
  const last = vertices[vertices.length - 1];
  const span = widths.reduce((s, w) => s + w, 0);
  // A closed ring puts both ends on the same point, and a circle through
  // first / middle / last is then undefined. Detect it and read the circle off
  // corners a third of the way round instead.
  const closed = Math.hypot(last.x - first.x, last.y - first.y) < span * 1e-9 && totalTurn > 0;

  // The corner nearest the middle of the wall, by panel count.
  const mid = vertices.length / 2;
  const midCorner = corners.slice(1, -1).reduce(
    (best, c) => (Math.abs(c - mid) < Math.abs(best - mid) ? c : best),
    corners.length > 2 ? corners[1] : Math.floor(mid),
);
  const [a, b, c] = closed
    ? [first, vertices[corners[Math.floor(corners.length / 3)]], vertices[corners[Math.floor((2 * corners.length) / 3)]]]
    : [first, vertices[midCorner], last];
  const center = circumcenter(a, b, c);

  // Radius through the corners, exact for an even curve, and a fair summary of
  // a mixed one, because every point used is a real corner of the wall.
  const radiusJoints = center ? Math.hypot(a.x - center.x, a.y - center.y) : Infinity;

  // Sweep is the arc the wall's actual shape covers, from the same circle.
  // Summing the joint angles instead goes wrong as soon as the end joints are
  // left flat, a 30 % wall built from 7.5° joints read 27 % while sitting 15 mm
  // off the drawn 30 % arc.
  const sweep = closed ? 360 : center ? sweepThrough(first, vertices[midCorner], last) : 0;

  // Radius to the face: from that center to the middle of each straight run
  // between corners, averaged. For an even curve every run sits the same
  // distance out, so this is exact, one panel per run or five.
  let radiusFace = Infinity;
  if (center && corners.length > 2) {
    let total = 0;
    let runs = 0;
    for (let i = 0; i + 1 < corners.length; i++) {
      const from = placements[corners[i]].face[0];
      const to = placements[corners[i + 1] - 1].face[1];
      total += Math.hypot((from.x + to.x) / 2 - center.x, (from.y + to.y) / 2 - center.y);
      runs += 1;
    }
    radiusFace = total / runs;
  }

  // Footprint is the deck space the wall eats: width across by depth back. That
  // has to be measured square to the wall's own chord, not to whatever frame the
  // datum put it in, anchored at an end, the chord runs off at an angle and the
  // box read 6.3 m × 4.2 m for a wall 7.5 m wide and 1.2 m deep.
  const chordAngle = chord > 0 ? Math.atan2(end.y - start.y, end.x - start.x) : 0;
  const cos = Math.cos(-chordAngle);
  const sin = Math.sin(-chordAngle);
  // Loops, not Math.max(...spread): a spread of a few tens of thousands of
  // points overflows the call stack and took the whole page down.
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const pl of placements)
    for (const p of [...pl.face, ...pl.rear]) {
      const x = p.x * cos - p.y * sin;
      const y = p.x * sin + p.y * cos;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }

  return {
    sweep_deg: sweep,
    percent_circle: (sweep / 360) * 100,
    total_turn_deg: totalTurn,
    radius_joints_m: radiusJoints,
    radius_face_m: radiusFace,
    chord_m: chord,
    depth_m: depth,
    depth_apex: apex,
    depth_foot: footOnLine(apex, start, end),
    // Depth over width stops meaning anything once the ends curl back toward
    // each other; past a half round the UI says so instead of printing it.
    depth_ratio_pct: sweep <= 180 && chord > 0 ? (depth / chord) * 100 : 0,
    arc_length_m: span,
    footprint_w_m: maxX - minX,
    footprint_d_m: maxY - minY,
    wall_height_m: wallHeightM,
  };
}

/**
 * Arc, in degrees, from `a` to `c` on the circle through a, b and c, going the
 * way that passes b.
 *
 * Past a half round the chord alone is ambiguous. This used to decide it by
 * whether b sat more than R off the chord, wrong on odd panel counts, where b
 * is half a panel off the apex: three panels at 55 % read as 45 %. The circle's
 * center settles it: the arc is the long way round exactly when the center is
 * on the same side of the chord as the wall.
 */
function sweepThrough(a, b, c) {
  const bx = b.x - a.x;
  const by = b.y - a.y;
  const cx = c.x - a.x;
  const cy = c.y - a.y;
  const d = 2 * (bx * cy - by * cx);
  if (Math.abs(d) < 1e-15) return 0; // Collinear: a straight wall.
  const b2 = bx * bx + by * by;
  const c2 = cx * cx + cy * cy;
  // Circle center, relative to a.
  const ox = (cy * b2 - by * c2) / d;
  const oy = (bx * c2 - cx * b2) / d;
  const R = Math.hypot(ox, oy);
  const chord = Math.hypot(cx, cy);
  const minor = 2 * deg(Math.asin(Math.min(1, chord / (2 * R))));
  const side = (px, py) => cx * py - cy * px; // sign: which side of a→c
  const centerSide = side(ox, oy);
  if (Math.abs(centerSide) < 1e-12 * chord * R) return 180;
  return Math.sign(centerSide) === Math.sign(side(bx, by)) ? 360 - minor : minor;
}

/**
 * Turn the wall level for drawing: chord horizontal, bow toward the audience.
 *
 * The datum decides how the wall is CALCULATED, anchored at an end, that end
 * sits square to the frame and the rest of the wall sweeps away from it, which
 * on screen reads as the whole wall tilted over. Rotation is rigid, so it
 * changes no distance and no deviation; it is purely how the thing is looked at.
 * Both the built wall and the drawn arc must take the SAME rotation or they stop
 * lining up at the datum.
 */
export function levelAngle(placements) {
  if (placements.length === 0) return 0;
  const start = placements[0].face[0];
  const end = placements[placements.length - 1].face[1];
  return Math.atan2(end.y - start.y, end.x - start.x);
}

export function rotatePoints(points, angle) {
  const c = Math.cos(-angle);
  const s = Math.sin(-angle);
  return points.map((p) => ({ ...p, x: p.x * c - p.y * s, y: p.x * s + p.y * c }));
}

export function rotatePlacements(placements, angle) {
  return placements.map((p) => ({
    ...p,
    face: rotatePoints(p.face, angle),
    rear: rotatePoints(p.rear, angle),
    heading_deg: p.heading_deg - (angle * 180) / Math.PI,
  }));
}

/** Worst gap between corresponding points of two walls built the same way. */
export function maxDeviation(a, b) {
  const n = Math.min(a.length, b.length);
  let worst = 0;
  for (let i = 0; i < n; i++) worst = Math.max(worst, Math.hypot(a[i].x - b[i].x, a[i].y - b[i].y));
  return worst;
}

/**
 * Offset between the two panel faces meeting at a joint, meters.
 *
 * Rotating about a hinge that sits behind the face swings the front edges apart
 * on a convex bend and into each other on a concave one. Zero when the hardware
 * pivots in the plane of the face, which is why good curve locks do.
 */
export function faceGap(angleDeg, pivotOffsetM, direction) {
  const magnitude = 2 * pivotOffsetM * Math.sin(rad(angleDeg) / 2);
  return direction === 'concave' ? -magnitude : magnitude;
}

// ---- Targets: the curve asked for, as one angle per joint ------------------

/**
 * Turning a curve spec into one number: the angle a perfect arc wants at every
 * joint.
 *
 * There is no standard meaning for a "% curve" in LED, manufacturers and every
 * published calculator spec radius, sweep, chord, sagitta and cabinet-to-cabinet
 * angle instead. So rather than pick a house definition and bury it, each way of
 * saying it is a mode here, and the solver reports the curve in all of them.
 */

/** Largest sweep a wall of `count` panels can have before it closes on itself. */
const MAX_SWEEP_DEG = 360;

function bisect(f, lo, hi) {
  // f must be monotonic on [lo, hi]. 60 halvings is well past double precision
  // on any angle we care about and costs nothing.
  let a = lo;
  let b = hi;
  const fa = f(a);
  const fb = f(b);
  if (fa === 0) return a;
  if (fb === 0) return b;
  if (fa > 0 === fb > 0) return fa * fa < fb * fb ? a : b; // No sign change: clamp to the closer end.
  for (let i = 0; i < 60; i++) {
    const m = (a + b) / 2;
    if (f(a) > 0 === f(m) > 0) a = m;
    else b = m;
  }
  return (a + b) / 2;
}

/**
 * The per-joint angle a true arc wants, degrees.
 *
 * A wall of n panels spans n * angle of arc: there are only n-1 joints, but the
 * arc runs half a panel past the outermost joint at each end.
 */
export function idealAngle(target, ctx) {
  const { widthM: w, count: n, maxAngleDeg, pivotOffsetM: p, direction } = ctx;
  if (n < 2 || !(w > 0)) return 0;

  const fromSweep = (sweepDeg) => Math.max(0, Math.min(MAX_SWEEP_DEG, sweepDeg)) / n;
  const v = target.value;

  switch (target.mode) {
    case 'percent_circle':
      return fromSweep(sweepForPercent(v));

    case 'sweep_deg':
      return fromSweep(v);

    case 'angle_per_joint':
      return Math.max(0, v);

    case 'percent_max_angle':
      return Math.max(0, (v / 100) * maxAngleDeg);

    case 'radius': {
      if (!(v > 0)) return 0;
      if (target.radius_ref === 'joints') return angleForChord(w, v);
      // Face radius = w / (2 tan(angle/2)) offset by the hinge depth: the face
      // sits inboard of the hinge circle on a concave bend, outboard on convex.
      const apothem = direction === 'concave' ? v + p : v - p;
      if (!(apothem > 0)) return 180;
      return 2 * (180 / Math.PI) * Math.atan(w / (2 * apothem));
    }

    case 'depth_ratio': {
      // depth/chord = tan(halfSweep/2)/2 for a circular arc, so it inverts cleanly.
      const ratio = v / 100;
      if (!(ratio > 0)) return 0;
      const halfSweep = 2 * Math.atan(2 * ratio);
      return fromSweep((2 * halfSweep * 180) / Math.PI);
    }

    case 'depth': {
      if (!(v > 0)) return 0;
      // Depth grows monotonically with the joint angle until the wall closes.
      const depthAt = (angle) =>
        arcDepth(radiusForAngle(w, angle), Math.min(MAX_SWEEP_DEG, angle * n)) - v;
      return bisect(depthAt, 1e-6, MAX_SWEEP_DEG / n);
    }

    case 'chord': {
      if (!(v > 0)) return 0;
      // Chord shrinks from n*w as the wall wraps, so the sign convention flips.
      const chordAt = (angle) =>
        v - arcChord(radiusForAngle(w, angle), Math.min(MAX_SWEEP_DEG, angle * n));
      return bisect(chordAt, 1e-6, MAX_SWEEP_DEG / n);
    }
  }
}

/** A curve percentage as degrees of sweep: 20 % of a circle is 72°. */
export function sweepForPercent(pct) {
  return (pct / 100) * 360;
}

/** Degrees of sweep as a curve percentage: 72° is 20 % of a circle. */
export function percentForSweep(deg) {
  return (deg / 360) * 100;
}

/**
 * The two ways a curve is entered. Both are the same thing, how much of a
 * circle the wall covers, said in the unit the drawing or the designer used.
 */

/** The curve as the other entry would say it, so switching never changes the wall. */
export function convertCurveEntry(value, from, to) {
  if (from === to) return value;
  return to === 'sweep_deg' ? sweepForPercent(value) : percentForSweep(value);
}

/** Radius through the joints implied by an ideal angle, meters. */
export function targetRadius(angleDeg, widthM) {
  return radiusForAngle(widthM, angleDeg);
}

// ---- Fitting: the wanted angle onto the angles the hardware has ------------

/**
 * Fitting a wanted angle onto the angles the hardware actually has.
 *
 * A perfect arc almost never lands on a detent. With 500 mm tiles on a 12 m
 * radius the joints want 2.39°, and a footer that does 2 / 5 / 7.5 / 10 cannot
 * do that. So the angle gets dithered across the joints: run the running error
 * forward and take whichever detent keeps the accumulated heading closest to
 * the arc. That beats rounding every joint the same way, which walks the ends of
 * the wall a long way off the drawing.
 */

/**
 * Clean a user-entered detent list: positive, sorted, de-duplicated, plus 0.
 *
 * Flat is always on the list. Leaving it off once forced every joint of a 10 %
 * curve onto a 5° footer and built 100° instead of 36°, the right answer there
 * is a handful of curved joints and the rest straight.
 */
export function usableDetents(hardware, direction) {
  const limit =
    direction === 'concave' ? hardware.max_concave_deg : hardware.max_convex_deg;
  const set = new Set        ([0]);
  for (const d of hardware.detents_deg) {
    const v = Math.abs(d);
    if (!Number.isFinite(v) || v === 0) continue;
    if (limit !== null && v > limit + 1e-9) continue;
    set.add(v);
  }
  return [...set].sort((a, b) => a - b);
}

/** The biggest angle this hardware can be locked to in this direction. */
export function maxAngle(hardware, direction) {
  const usable = usableDetents(hardware, direction).filter((d) => d > 0);
  return usable.length ? usable[usable.length - 1] : 0;
}

function nearest(value, options) {
  let best = options[0] ?? 0;
  let bestErr = Math.abs(value - best);
  for (const o of options) {
    const err = Math.abs(value - o);
    if (err < bestErr - 1e-12) {
      best = o;
      bestErr = err;
    }
  }
  return best;
}

/**
 * Pick an angle for every joint, working out from the wall's datum.
 *
 * `center` mirrors about the middle, so both ends read the same on a build sheet
 * and the drift is shared between them. `left` / `right` walk from that end,
 * which is what a crew building off a fixed edge actually does, and then all
 * the drift lands at the far end, which is the honest picture.
 *
 * Both routes score candidate patterns on real distance from the drawn arc in
 * the same frame the wall is anchored in.
 */
export function fitJoints(
  jointCount,
  idealDeg,
  detents,
  origin = 'center',
  beamWidth = DEFAULT_BEAM,
  /**
   * Which joints are free to bend. A joint in the middle of a footer is not:
   * a 1 m footer under 500 mm panels spans two of them and holds that joint
   * rigid, so the wall is really a chain of 1 m segments.
   */
  canCurve = () => true,
  /**
   * Keep an evenly spread pattern unless the search beats it by more than 1 %
   * of a panel width. True for the simplest and even goals; false for tightest,
   * which promises the closest wall and nothing else.
   */
  preferEven = true,
) {
  if (jointCount <= 0) return [];
  const margin = preferEven ? WORTH_IT : 1e-12;
  const options = detents.length ? detents : [0];
  const FLAT = [0];

  if (typeof origin === 'number') {
    // A datum along the wall: work outward from it both ways. No mirroring, the
    // two sides are different lengths and the footers under them differ too.
    const at = snapDatum(origin, jointCount + 1);
    if (Number.isInteger(at)) return fitOutward(jointCount, idealDeg, options, canCurve, beamWidth, at - 1);
    const k = at - 0.5; // the datum is the corner after panel k
    if (k <= 0) return fitJoints(jointCount, idealDeg, options, 'left', beamWidth, canCurve, preferEven);
    if (k >= jointCount + 1) return fitJoints(jointCount, idealDeg, options, 'right', beamWidth, canCurve, preferEven);
    return fitAtJoint(jointCount, idealDeg, options, canCurve, beamWidth, k - 1);
  }

  if (origin === 'center') {
    // A mirrored pattern needs both joints of every pair to be free. With a
    // footer grid that does not divide evenly they are not, every third joint
    // on a 15-joint wall gives no symmetric pair at all, and demanding a mirror
    // left the whole wall flat. Fit the two halves separately in that case.
    const symmetric = Array.from({ length: jointCount }, (_, i) => i).every(
      (i) => canCurve(i) === canCurve(jointCount - 1 - i),
);
    if (!symmetric) return fitHalves(jointCount, idealDeg, options, canCurve, beamWidth);
    const at = (step) => (canCurve(centerJointIndex(jointCount, step)) ? options : FLAT);
    // The rounding pass spreads curved joints evenly, which reads best; the
    // search finds the builds rounding misses by a long way. Only trade the even
    // spacing for a real gain, more than 1 % of a panel width (5 mm on 500 mm
    // tiles). A 0.9 mm win once bunched two 5° kinks side by side.
    const rounded = diffuseFromCenter(jointCount, idealDeg, at);
    const searched = searchSymmetric(jointCount, idealDeg, at, beamWidth);
    return deviationFromCenter(searched, idealDeg) < deviationFromCenter(rounded, idealDeg) - margin
      ? searched
      : rounded;
  }

  // Building from the right walks the joints in reverse, so step 0 is the last joint.
  const at = (step) => (canCurve(origin === 'right' ? jointCount - 1 - step : step) ? options : FLAT);
  const rounded = diffuseFromEnd(jointCount, idealDeg, at);
  const searched = searchFromEnd(jointCount, idealDeg, at, beamWidth);
  const best =
    deviationFromEnd(searched, idealDeg) < deviationFromEnd(rounded, idealDeg) - margin
      ? searched
      : rounded;
  // Joints are always numbered from the left end; building from the right just
  // reverses the order they are worked out in.
  return origin === 'right' ? [...best].reverse() : best;
}

/** Improvement, in panel widths, that justifies giving up an evenly spread pattern. */
const WORTH_IT = 0.01;

export const DEFAULT_BEAM = 200;

/**
 * Center out with a footer grid that is not symmetric: fit the right half and
 * the left half independently, both walked from the center in the frame the
 * wall is measured in. The pattern will not mirror, it cannot, but each end
 * lands as close to the drawing as its own joints allow.
 */
function fitHalves(
  jointCount,
  idealDeg,
  options,
  canCurve,
  beamWidth,
) {
  const FLAT = [0];
  const odd = jointCount % 2 === 1;
  const mid = Math.floor(jointCount / 2);
  const outward = odd ? (jointCount - 1) / 2 : jointCount / 2;
  // Right half runs mid(+1) outward; left half runs mid-1 inward-to-outward.
  const rightIndex = (step) => (odd ? mid + step : mid + step);
  const leftIndex = (step) => (odd ? mid - step : mid - 1 - step);
  const atSide = (index) => (step) =>
    canCurve(index(step)) ? options : FLAT;

  const best = { dev: Infinity, center: 0, right: [], left: []             };
  // An odd joint count has a joint ON the center line, shared by both halves.
  for (const center of odd ? (canCurve(mid) ? options : FLAT) : [0]) {
    const seed = startCenter(jointCount, odd ? center : null);
    const track = idealTrack(outward, idealDeg, startCenter(jointCount, odd ? idealDeg : null));
    const right = searchBest([seed], track, atSide(rightIndex), beamWidth, odd ? 1 : 0);
    const left = searchBest([seed], track, atSide(leftIndex), beamWidth, odd ? 1 : 0);
    const dev = Math.max(right.dev, left.dev);
    if (dev < best.dev) {
      best.dev = dev;
      best.center = center;
      // With a joint on the center line the seed already carries it as picks[0];
      // the outward joints are what follows.
      best.right = odd ? right.picks.slice(1) : right.picks;
      best.left = odd ? left.picks.slice(1) : left.picks;
    }
  }

  const out = new Array        (jointCount).fill(0);
  if (odd) out[mid] = best.center;
  best.right.forEach((a, i) => (out[odd ? mid + 1 + i : mid + i] = a));
  best.left.forEach((a, i) => (out[odd ? mid - 1 - i : mid - 1 - i] = a));
  return out;
}

/**
 * Fit outward from a datum joint. The joint itself can bend, and half its turn
 * falls on each side, the same as the center joint of an even panel count, but
 * anywhere along the wall. `d` is its 0-based index.
 */
function fitAtJoint(
  jointCount,
  idealDeg,
  options,
  canCurve,
  beamWidth,
  d,
) {
  const FLAT = [0];
  const best = { dev: Infinity, center: 0, right: [], left: []             };
  const atJoint = (c) => {
    const h = (c * Math.PI) / 360;
    return { picks: [], x: Math.cos(h), y: Math.sin(h), h, dev: 0 };
  };
  const side = (count, seed, ideal, index) =>
    count > 0
      ? searchBest([seed], idealTrack(count, idealDeg, ideal), (s) => (canCurve(index(s)) ? options : FLAT), beamWidth, 0)
      : { ...seed, dev: Math.hypot(seed.x - ideal.x, seed.y - ideal.y) };

  for (const center of canCurve(d) ? options : FLAT) {
    const seed = atJoint(center);
    const ideal = atJoint(idealDeg);
    const right = side(jointCount - 1 - d, seed, ideal, (s) => d + 1 + s);
    const left = side(d, seed, ideal, (s) => d - 1 - s);
    const dev = Math.max(right.dev, left.dev);
    if (dev < best.dev) Object.assign(best, { dev, center, right: right.picks, left: left.picks });
  }

  const out = new Array        (jointCount).fill(0);
  out[d] = best.center;
  best.right.forEach((a, i) => (out[d + 1 + i] = a));
  best.left.forEach((a, i) => (out[d - 1 - i] = a));
  return out;
}

/** The datum is the middle of a panel: half a panel to the first vertex. */
const startPanel = () => ({ picks: [], x: 0.5, y: 0, h: 0, dev: 0 });

/**
 * Fit outward from a datum panel, each side on its own. `firstRight` is the
 * 0-based index of the first joint to the right of the datum.
 */
function fitOutward(
  jointCount,
  idealDeg,
  options,
  canCurve,
  beamWidth,
  firstRight,
) {
  const FLAT = [0];
  const out = new Array        (jointCount).fill(0);
  const seed = startPanel();
  const side = (count, index) =>
    count > 0
      ? searchBest(
          [seed],
          idealTrack(count, idealDeg, seed),
          (step) => (canCurve(index(step)) ? options : FLAT),
          beamWidth,
          0,
).picks
      : [];

  side(jointCount - firstRight, (step) => firstRight + step).forEach((a, i) => (out[firstRight + i] = a));
  side(firstRight, (step) => firstRight - 1 - step).forEach((a, i) => (out[firstRight - 1 - i] = a));
  return out;
}

/** The joint a center-out `step` lands on: step 0 is the center one, then outward. */
function centerJointIndex(jointCount, step) {
  const mid = Math.floor(jointCount / 2);
  return jointCount % 2 === 1 ? mid + step : mid + step;
}

/** Options available at each step, e.g. flat only where a footer spans the joint. */

/** Round joint by joint from one end, keeping the running heading on the arc. */
function diffuseFromEnd(jointCount, idealDeg, at) {
  const out = [];
  let running = 0;
  for (let i = 1; i <= jointCount; i++) {
    const pick = nearest(idealDeg * i - running, at(i - 1)); // where a true arc has turned to by here
    out.push(pick);
    running += pick;
  }
  return out;
}

/**
 * Round joint by joint from the center outward, keeping the running HEADING
 * within half a detent step of a true arc, then mirror.
 */
function diffuseFromCenter(jointCount, idealDeg, at) {
  const out = new Array        (jointCount);
  let running = 0;
  let first = Math.floor(jointCount / 2);
  let offset = 1; // ideal turn from the center after the first outward joint, in joints
  let step = 0;

  if (jointCount % 2 === 1) {
    // Odd joint count: a joint sits on the center line and only half of its turn
    // falls on each side.
    const center = nearest(idealDeg, at(0));
    out[first] = center;
    running = center / 2;
    first += 1;
    offset = 1.5;
    step = 1;
  }

  for (let i = first, t = 0; i < jointCount; i++, t++, step++) {
    const pick = nearest(idealDeg * (t + offset) - running, at(step));
    out[i] = pick;
    out[jointCount - 1 - i] = pick;
    running += pick;
  }
  return out;
}

/**
 * A wall walked out from its datum with unit panel width. Deviation scales with
 * panel width, so the ranking of patterns does not depend on it.
 *
 * From an end: the datum corner is the origin and the first panel runs along +x.
 * Center out, even panel count (odd joints): the center joint sits at the origin
 * and half its turn falls each side. Odd panel count: the center panel straddles
 * the origin and the first outward vertex is half a panel along it.
 */

function startCenter(jointCount, center) {
  if (jointCount % 2 === 1) {
    const h = ((center ?? 0) * Math.PI) / 360;
    return { picks: [center ?? 0], x: Math.cos(h), y: Math.sin(h), h, dev: 0 };
  }
  return { picks: [], x: 0.5, y: 0, h: 0, dev: 0 };
}

const startEnd = () => ({ picks: [], x: 1, y: 0, h: 0, dev: 0 });

function step(s, angle, ideal) {
  const h = s.h + (angle * Math.PI) / 180;
  const x = s.x + Math.cos(h);
  const y = s.y + Math.sin(h);
  return { picks: [...s.picks, angle], x, y, h, dev: Math.max(s.dev, Math.hypot(x - ideal.x, y - ideal.y)) };
}

/** Where a true arc puts each vertex from the datum, in the same unit-width frame. */
function idealTrack(steps, idealDeg, from) {
  const out = [{ x: from.x, y: from.y, h: from.h }];
  let { x, y, h } = from;
  for (let i = 0; i < steps; i++) {
    h += (idealDeg * Math.PI) / 180;
    x += Math.cos(h);
    y += Math.sin(h);
    out.push({ x, y, h });
  }
  return out;
}

function walk(joints, track, from, firstJoint) {
  let s = { ...from, dev: Math.hypot(from.x - track[0].x, from.y - track[0].y) };
  for (let i = firstJoint, t = 1; i < joints.length; i++, t++) s = step(s, joints[i], track[t]);
  return s.dev;
}

/** Worst distance from the drawn arc of a full symmetric pattern, unit width. */
function deviationFromCenter(joints, idealDeg) {
  const n = joints.length;
  const odd = n % 2 === 1;
  const from = startCenter(n, odd ? joints[Math.floor(n / 2)] : null);
  const track = idealTrack(odd ? (n - 1) / 2 : n / 2, idealDeg, startCenter(n, odd ? idealDeg : null));
  return walk(joints, track, from, Math.floor(n / 2) + (odd ? 1 : 0));
}

/** The same, for a wall anchored at one end. */
function deviationFromEnd(joints, idealDeg) {
  return walk(joints, idealTrack(joints.length, idealDeg, startEnd()), startEnd(), 0);
}

function searchBest(
  seeds,
  track,
  at,
  beamWidth,
  firstStep,
) {
  let beam = seeds.map((s) => ({ ...s, dev: Math.hypot(s.x - track[0].x, s.y - track[0].y) }));
  for (let t = 1; t < track.length; t++) {
    const next = [];
    for (const s of beam) for (const a of at(firstStep + t - 1)) next.push(step(s, a, track[t]));
    const ih = track[t].h;
    next.sort((a, b) => a.dev - b.dev || Math.abs(a.h - ih) - Math.abs(b.h - ih));
    beam = next.slice(0, Math.max(1, beamWidth));
  }
  return beam[0];
}

/**
 * Beam search for the pattern closest to the drawn arc.
 *
 * Rounding each joint to keep the heading on the arc looks right joint by joint
 * but lets position error pile up along a long arm, on a 24-panel 16 % wall it
 * landed 62 mm off when 11 mm was buildable. This scores partial patterns by the
 * real measure, worst vertex distance from the arc so far, and keeps the best
 * `beamWidth` at every step, breaking ties on how far the heading has drifted.
 */
export function searchSymmetric(
  jointCount,
  idealDeg,
  at,
  beamWidth = DEFAULT_BEAM,
) {
  if (jointCount <= 0) return [];
  const odd = jointCount % 2 === 1;
  const track = idealTrack(odd ? (jointCount - 1) / 2 : jointCount / 2, idealDeg, startCenter(jointCount, odd ? idealDeg : null));
  const best = searchBest(
    (odd ? at(0) : [null]).map((c) => startCenter(jointCount, c)),
    track,
    at,
    beamWidth,
    odd ? 1 : 0,
);

  const out = new Array        (jointCount);
  const mid = Math.floor(jointCount / 2);
  if (odd) {
    out[mid] = best.picks[0];
    best.picks.slice(1).forEach((a, i) => {
      out[mid + 1 + i] = a;
      out[mid - 1 - i] = a;
    });
  } else {
    best.picks.forEach((a, i) => {
      out[mid + i] = a;
      out[mid - 1 - i] = a;
    });
  }
  return out;
}

/** The same search, for a wall anchored at one end and built along its length. */
export function searchFromEnd(
  jointCount,
  idealDeg,
  at,
  beamWidth = DEFAULT_BEAM,
) {
  if (jointCount <= 0) return [];
  return searchBest([startEnd()], idealTrack(jointCount, idealDeg, startEnd()), at, beamWidth, 0).picks;
}

/** Collapse consecutive equal angles so the build sheet reads as runs, not a list. */
export function runLength(joints) {
  const runs = [];
  for (let i = 0; i < joints.length; i++) {
    const last = runs[runs.length - 1];
    if (last && Math.abs(last.angle_deg - joints[i]) < 1e-9) {
      last.count += 1;
      last.to = i + 1;
    } else {
      runs.push({ angle_deg: joints[i], count: 1, from: i + 1, to: i + 1 });
    }
  }
  return runs;
}

// ---- Bars: where they go, and so which joints can bend ---------------------


/**
 * Where the footers fall, and therefore which joints can bend.
 *
 * A footer is a bar under (or over) one or more panels. Anything it spans is
 * rigid: a 1 m footer on 500 mm panels holds the joint between its two panels
 * straight. Only the joins BETWEEN footers can take a curve.
 *
 * Footer sizes are entered as a repeating run, "1, 1, 0.5" is the five-panel
 * group a lot of rigs are built from, and the run repeats along the wall. The
 * last footer is cut short if the wall runs out mid-run.
 */

/** How many panels a footer of this width covers. At least one. */
export function panelsUnder(footerWidthM, panelWidthM) {
  const n = Math.round(footerWidthM / panelWidthM);
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

/**
 * Lay the footers out along the wall.
 *
 * `runOverride` is the layout the calculator chose; without one the sizes are
 * taken in order and repeated, which is only the right answer when there is no
 * choice to make (one size that divides the wall).
 */
export function footerPlan(config, runOverride) {
  const { panel, hardware } = config;
  const source = runOverride?.length ? runOverride : hardware.footer_widths_m;
  const run = source.length ? source : [panel.width_m];
  const footers = [];
  const free = new Set        ();
  let placed = 0;
  let exact = true;

  // Guard against a run that cannot advance, which would spin forever.
  for (let i = 0; placed < panel.count && i < panel.count * 2 + 8; i++) {
    const width = run[i % run.length];
    const want = panelsUnder(width, panel.width_m);
    const panels = Math.min(want, panel.count - placed);
    if (panels < want) exact = false;
    footers.push({
      index: footers.length + 1,
      width_m: width,
      panels,
      from: placed + 1,
      to: placed + panels,
      part: panels < want,
    });
    placed += panels;
    // The joint after this footer's last panel is a footer join, unless the
    // wall ends there.
    if (placed < panel.count) free.add(placed - 1);
  }

  return {
    footers,
    free,
    maxPanels: footers.reduce((m, f) => Math.max(m, f.panels), 1),
    exact,
  };
}

/** What a layout uses, as a crew would count it: "0.5 m × 4 + 1 m × 6". */
export function describeFooters(footers, fmt) {
  const tally = new Map                ();
  for (const f of footers) tally.set(f.width_m, (tally.get(f.width_m) ?? 0) + 1);
  return [...tally.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([w, n]) => (n > 1 ? `${fmt(w)} × ${n}` : fmt(w)))
    .join(' + ');
}

/** The sizes on hand, listed: "0.5 m and 1 m". */
export function describeStock(config, fmt) {
  const sizes = [...new Set(config.hardware.footer_widths_m)].sort((a, b) => a - b).map(fmt);
  if (sizes.length <= 1) return sizes.join('');
  return `${sizes.slice(0, -1).join(', ')} and ${sizes[sizes.length - 1]}`;
}

/**
 * Working out WHERE the footers go.
 *
 * The footer sizes are stock, not an order: given 0.5 m and 1 m bars, the job is
 * to decide which bar goes where so the wall lands on the curve. A 1 m footer
 * buys a rigid pair of panels; a 0.5 m footer buys a joint that can bend. Put
 * them in the wrong places and the curve either cannot be reached or wastes
 * joints where it does not need them.
 *
 * So layout and angles are searched together: walk the wall, and at every step
 * choose a footer size AND the angle of the joint after it, scoring candidates
 * on how far the panels stray from the drawn arc. Scoring runs in a left-anchored
 * frame with unit panel width; the caller re-measures the survivors in the
 * wall's real datum frame, which is why several are returned rather than one.
 */

export function searchLayouts(input) {
  const { panelCount: n, panelWidthM, sizes, angles, idealDeg, beamWidth, keep } = input;
  if (n < 2) return [{ run_m: sizes.length ? [sizes[0]] : [panelWidthM], joints: [], rough_dev: 0 }];

  // A screen's corners (the Header/Footer tab's Corners): `fixed` are the
  // corner bars, each its own footer at its own panels whatever the stock
  // ({ start, size } in panels from the left); `breaks` are panel edges no
  // footer runs across; `flat` are joints that never bend. Without them
  // the search is the calculator's own.
  const fixed = input.fixed || [];
  const breaks = input.breaks || [];
  const flatJoints = new Set(input.flat || []);
  const constrained = fixed.length > 0 || breaks.length > 0;
  const fixedAt = new Map(fixed.map((p) => [p.start, p.size]));
  const stops = [...new Set([...fixed.flatMap((p) => [p.start, p.start + p.size]), ...breaks, n])]
    .filter((x) => x > 0 && x <= n)
    .sort((a, b) => a - b);
  const stopAfter = (at) => stops.find((x) => x > at) ?? n;

  // Where a true arc puts each panel corner, walking from the left end.
  const track = [{ x: 0, y: 0 }];
  let th = 0;
  let tx = 0;
  let ty = 0;
  for (let i = 0; i < n; i++) {
    if (i > 0) th += (idealDeg * Math.PI) / 180;
    tx += Math.cos(th);
    ty += Math.sin(th);
    track.push({ x: tx, y: ty });
  }

  const inPanels = [...new Set(sizes.map((w) => Math.max(1, panelsUnder(w, panelWidthM))))].sort((a, b) => a - b);
  const bySize = new Map(inPanels.map((k) => [k, sizes.find((w) => panelsUnder(w, panelWidthM) === k) ]));

  // Which remainders the stock can fill exactly. Choosing footers one at a time
  // without this laid 2 + 2 on a 5-panel wall and left a single panel no bar
  // fits, when 2 + 3 covers it exactly.
  const fills = [true];
  for (let r = 1; r <= n; r++) fills[r] = inPanels.some((k) => r - k >= 0 && fills[r - k]);
  const exact = fills[n];

  let live = [{ placed: 0, x: 0, y: 0, h: 0, dev: 0, run: [], joints: [] }];
  const done = [];

  while (live.length) {
    const next = [];
    for (const s of live) {
      // A corner bar starts here: it is the only footer that can.
      const piece = fixedAt.get(s.placed);
      // Up to the next corner or break, or the wall's end.
      const remaining = piece || stopAfter(s.placed) - s.placed;
      // Only footers that leave a remainder the stock can still fill. When the
      // stock cannot tile the wall at all, a part footer at the end is the only
      // way out, and that is flagged downstream.
      const exactHere = constrained ? fills[remaining] : exact;
      const fits = piece ? [piece] : inPanels.filter((k) => k <= remaining && (!exactHere || fills[remaining - k]));
      const usable = fits.length ? fits : [inPanels.find((k) => k >= remaining) ?? inPanels[inPanels.length - 1]];

      for (const k of usable) {
        const panels = Math.min(k, remaining);
        // Panels under one footer are a straight run: walk them, scoring each corner.
        let { x, y, dev } = s;
        const h = s.h;
        for (let j = 0; j < panels; j++) {
          x += Math.cos(h);
          y += Math.sin(h);
          const t = track[s.placed + j + 1];
          dev = Math.max(dev, Math.hypot(x - t.x, y - t.y));
        }
        const placed = s.placed + panels;
        const run = [...s.run, piece ? piece * panelWidthM : bySize.get(k)];
        const joints = [...s.joints, ...new Array(panels - 1).fill(0)];

        if (placed >= n) {
          done.push({ ...s, placed, x, y, dev, run, joints });
          continue;
        }
        // The joint after this footer is the one that can bend, unless a
        // corner holds it flat.
        for (const a of flatJoints.has(placed - 1) ? [0] : angles) {
          next.push({
            placed,
            x,
            y,
            h: h + (a * Math.PI) / 180,
            dev,
            run,
            joints: [...joints, a],
          });
        }
      }
    }
    next.sort((a, b) => a.dev - b.dev);
    live = next.slice(0, Math.max(1, beamWidth));
  }

  done.sort((a, b) => a.dev - b.dev);
  return done.slice(0, Math.max(1, keep)).map((s) => ({
    run_m: s.run,
    joints: s.joints.slice(0, n - 1),
    rough_dev: s.dev,
  }));
}

// ---- Ways to build it, and which one to use --------------------------------

/**
 * Deciding HOW to build a curve when the hardware offers more than one angle.
 *
 * Fitting against every angle at once gives the tightest match to the drawing,
 * but that is not always the best build: a curve that one angle plus some flat
 * joints can hit just as well is simpler to set and harder to get wrong. So the
 * fitter is run against every subset of the angles, and the results are ranked:
 *
 *   1. within tolerance of the drawn arc
 *   2. fewest different angles to set
 *   3. gentlest largest angle, smaller facets read as a smoother curve
 *   4. closest to the drawing
 *
 * If nothing is within tolerance, closest to the drawing wins outright.
 */

/** Two deviations closer than this are the same for ranking purposes. */
const SAME_M = 1e-6;

/**
 * An even curve, the way a crew means it: the same bend at a regular spacing , 
 * "5° after every third panel". Every straight run between bends (the end runs
 * included) is the same number of panels, and every bend is the same angle.
 * A straight wall is even too, or an 0.5 % ask forces a kink into every joint.
 *
 * It used to mean "every joint that could bend is set the same", which fell over
 * on 1 m + 0.5 m footers: the join between the two footers in each run could
 * bend, so an even wall had to bend there too, and the only even answers were
 * 45° or flat.
 */
export function isEven(joints) {
  const bends = joints.map((a, i) => (a !== 0 ? i + 1 : 0)).filter((p) => p > 0);
  if (!bends.length) return true;
  if (new Set(bends.map((p) => joints[p - 1])).size > 1) return false;
  const edges = [0, ...bends, joints.length + 1];
  const runs = edges.slice(1).map((p, i) => p - edges[i]);
  return runs.every((r) => r === runs[0]);
}

/** Panels in each straight run of an even wall, or null when it is not even. */
export function evenRun(joints) {
  if (!isEven(joints)) return null;
  const bends = joints.filter((a) => a !== 0).length;
  return (joints.length + 1) / (bends + 1);
}

export function optionId(used) {
  return used.length ? used.join('+') : 'flat';
}

/**
 * Every non-empty subset of the angles. Past eight angles (a 1°-step preset is
 * ten) that is hundreds of fits, so the search narrows to singles, pairs,
 * triples and the full set. Triples matter: on the 1°-step preset a 1/3/4° build
 * sat 15 mm off where the best pair was 46 mm.
 */
function subsets(angles) {
  if (angles.length === 0) return [[]];
  if (angles.length > 8) {
    const out = angles.map((a) => [a]);
    for (let i = 0; i < angles.length; i++)
      for (let j = i + 1; j < angles.length; j++) {
        out.push([angles[i], angles[j]]);
        for (let k = j + 1; k < angles.length; k++) out.push([angles[i], angles[j], angles[k]]);
      }
    out.push([...angles]);
    return out;
  }
  const out = [];
  for (let mask = 1; mask < 1 << angles.length; mask++)
    out.push(angles.filter((_, i) => mask & (1 << i)));
  return out;
}

export function buildOptions(input) {
  const seen = new Set        ();
  const out = [];

  for (const subset of subsets(input.angles)) {
    // Measure every candidate in the wall's real datum frame, the layout search
    // scores from the left end, which ranks well but is not the frame the wall is
    // built to.
    const scored = input.candidates(subset).map((candidate) => {
      const built = buildCurve({ ...input.build, joints: candidate.joints });
      const used = [...new Set(candidate.joints.filter((a) => a > 0))].sort((a, b) => a - b);
      return {
        ...candidate,
        built,
        used,
        even: isEven(candidate.joints),
        deviation: maxDeviation(built.vertices, input.wanted),
      };
    });
    if (!scored.length) continue;

    // Keep the closest build, and the closest EVEN build alongside it. They are
    // different answers to the same question: an even curve that overshoots the
    // percentage is a legitimate way to rig a wall, and collapsing to whichever
    // is nearer the drawing hid it entirely.
    const closest = scored.reduce((b, c) => (c.deviation < b.deviation ? c : b));
    const evenBest = scored.filter((c) => c.even).sort((a, b) => a.deviation - b.deviation)[0];

    for (const candidate of evenBest && evenBest !== closest ? [closest, evenBest] : [closest]) {
      const { joints, run_m, used, built, even, deviation } = candidate;
      // Offering more angles often changes nothing, the fitter never reaches for
      // the extra one. Identical walls are one option, not several.
      const key = `${joints.join(',')}|${run_m.join(',')}`;
      if (seen.has(key)) continue;
      seen.add(key);

      const curved = joints.filter((a) => a > 0).length;
      out.push({
        id: optionId(used) + (even && evenBest === candidate && closest !== candidate ? ' even' : ''),
        run_m,
        used_angles_deg: used,
        joints,
        curved_joints: curved,
        flat_joints: joints.length - curved,
        max_angle_deg: used.length ? used[used.length - 1] : 0,
        even,
        deviation_m: deviation,
        sweep_deg: built.measurements.sweep_deg,
        percent_circle: built.measurements.percent_circle,
        within_tolerance: deviation <= input.toleranceM + SAME_M,
      });
    }
  }
  return out;
}

const byAccuracy = (a, b) =>
  Math.abs(a.deviation_m - b.deviation_m) > SAME_M
    ? a.deviation_m - b.deviation_m
    : a.used_angles_deg.length - b.used_angles_deg.length || a.max_angle_deg - b.max_angle_deg;

const bySimplicity = (a, b) =>
  a.used_angles_deg.length - b.used_angles_deg.length ||
  a.max_angle_deg - b.max_angle_deg ||
  a.deviation_m - b.deviation_m;

/**
 * Best first.
 * `simplest`: in-tolerance options by simplicity, then the rest by accuracy.
 * `tightest`: everything by accuracy, the old always-mix behavior, except that
 * a subset which happens to fit better than the full mix is allowed to win.
 */
export function rankOptions(options, goal = 'simplest') {
  if (goal === 'tightest') return [...options].sort(byAccuracy);
  if (goal === 'even') {
    // An even curve first, then whichever of those lands closest. If nothing is
    // even, fall back to accuracy rather than refusing to answer.
    const even = options.filter((o) => o.even).sort(byAccuracy);
    return [...even, ...options.filter((o) => !o.even).sort(byAccuracy)];
  }
  const ok = options.filter((o) => o.within_tolerance).sort(bySimplicity);
  const rest = options.filter((o) => !o.within_tolerance).sort(byAccuracy);
  return [...ok, ...rest];
}

export function describeAngles(o) {
  if (!o.used_angles_deg.length) return 'no curved joints';
  const list = o.used_angles_deg.map((a) => formatAngle(a, 2)).join(' and ');
  return o.used_angles_deg.length === 1 ? `one angle (${list})` : `${o.used_angles_deg.length} angles (${list})`;
}

export function explainChoice(
  chosen,
  ranked,
  toleranceM,
  manual,
  system,
  goal = 'simplest',
) {
  const recommended = ranked[0];
  const tol = formatSmall(toleranceM, system);
  if (manual && chosen.id !== recommended.id) {
    // Say how far off the pick itself is, a pick 22 times over tolerance used
    // to be described only by what the app would have done instead.
    const own = chosen.within_tolerance
      ? `lands ${formatSmall(chosen.deviation_m, system)} off the drawing`
      : `lands ${formatSmall(chosen.deviation_m, system)} off the drawing, over your ${tol} limit`;
    return `Your pick ${own}. On its own the app would use ${describeAngles(recommended)}, ${formatSmall(recommended.deviation_m, system)} off.`;
  }

  if (!chosen.used_angles_deg.length && chosen.within_tolerance) {
    return 'A straight wall: every joint flat.';
  }

  if (goal === 'tightest') {
    return `Tightest fit: uses ${describeAngles(chosen)} to land ${formatSmall(chosen.deviation_m, system)} off the drawing, the closest these angles can get.`;
  }

  if (goal === 'even') {
    const closest = [...ranked].sort(byAccuracy)[0];
    if (!chosen.even) {
      return `No even build is possible with these angles: none of them bends every joint the same. This is the closest instead, ${formatSmall(chosen.deviation_m, system)} off the drawing.`;
    }
    const run = evenRun(chosen.joints);
    const spacing =
      !chosen.used_angles_deg.length || run === null
        ? 'a straight wall'
        : run === 1
          ? `${formatAngle(chosen.max_angle_deg, 2)} at every joint`
          : `a ${formatAngle(chosen.max_angle_deg, 2)} bend after every ${run} panels`;
    return (
      `Even curve: ${spacing}, which builds ${chosen.percent_circle.toFixed(1)}%. ` +
      (closest.id !== chosen.id
        ? `Leaving some joints flat would land closer to the drawing (${formatSmall(closest.deviation_m, system)} against ${formatSmall(chosen.deviation_m, system)}), but the curve would not be even.`
        : `It is also the closest fit, ${formatSmall(chosen.deviation_m, system)} off the drawing.`)
);
  }

  if (!chosen.within_tolerance) {
    return `Nothing these angles can build gets within ${tol} of the drawing, so this is the closest the hardware can get.`;
  }

  const closest = [...ranked].sort(byAccuracy)[0];
  const off = formatSmall(chosen.deviation_m, system);
  if (closest.id === chosen.id) {
    return `Uses ${describeAngles(chosen)} and is the closest fit to the drawing (${off} off). Nothing simpler gets within ${tol}.`;
  }
  // The closer fit costs either more angles or a sharper one, say which, or a
  // one-angle pick reads as if it were passed over for another one-angle build.
  const cost =
    closest.used_angles_deg.length > chosen.used_angles_deg.length
      ? `needs ${describeAngles(closest)}`
      : `needs a sharper angle (${formatAngle(closest.max_angle_deg, 2)})`;
  return (
    `Uses ${describeAngles(chosen)} and stays within ${off} of the drawing. ` +
    `The closest possible fit is ${formatSmall(closest.deviation_m, system)} off but ${cost}.`
);
}

// ---- Errors and warnings ---------------------------------------------------

/** Past this, a wall is a stadium ring, not a screen, and the page slows down. */
export const MAX_PANELS = 500;

/**
 * Two kinds of feedback, kept apart on purpose.
 *
 * `inputErrors` means the geometry could not be worked out and every number the
 * app would show is meaningless, the result comes back zeroed.
 * `warnings` means it computed fine, and the crew still needs to be told
 * something before they build it.
 */

export function inputErrors(config, system = 'metric') {
  const errors = [];
  const { panel, hardware, target } = config;

  if (!(panel.width_m > 0)) errors.push('Panel width must be greater than zero.');
  if (!(panel.height_m > 0)) errors.push('Panel height must be greater than zero.');
  if (!(panel.depth_m >= 0)) errors.push('Panel depth must be 0 or more.');
  if (!Number.isInteger(panel.count)) errors.push('Panels across must be a whole number.');
  else if (panel.count < 2) errors.push('A curve needs at least 2 panels across.');
  else if (panel.count > MAX_PANELS) errors.push(`Up to ${MAX_PANELS} panels across.`);
  if (!Number.isInteger(panel.rows) || panel.rows < 1)
    errors.push('Panels tall must be a whole number, 1 or more.');
  if (hardware.pivot_offset_m < 0) errors.push('Hinge offset cannot be negative.');
  if (!(config.tolerance_m >= 0)) errors.push('Close enough to the drawing must be a number, 0 or more.');

  // Footers. A footer narrower than a panel cannot hold it; one that is not a
  // whole number of panels wide would straddle a joint by a fraction, which no
  // rigging does and the maths cannot represent.
  const run = hardware.footer_widths_m;
  if (!run.length) errors.push('Light at least one bar size.');
  if (run.some((w) => !(w > 0))) errors.push('Bar widths must be greater than zero.');
  else if (panel.width_m > 0) {
    for (const w of run) {
      const per = w / panel.width_m;
      if (per < 1 - 1e-9) {
        errors.push(
          `A bar cannot be narrower than a panel: ${formatLength(w, system)} against ${formatLength(panel.width_m, system)}.`,
);
        break;
      }
      if (Math.abs(per - Math.round(per)) > 1e-6) {
        errors.push(
          `A bar has to be a whole number of panels wide. ${formatLength(w, system)} is ${per.toFixed(2)} panels.`,
);
        break;
      }
    }
  }

  // Footer angles.
  const listed = hardware.detents_deg.filter((d) => Number.isFinite(d) && Math.abs(d) > 0);
  if (!listed.length) errors.push('Add at least one angle the hardware can lock to.');
  if (listed.some((d) => Math.abs(d) >= 90)) errors.push('Lock angles must be under 90°.');
  for (const [limit, side] of [
    [hardware.max_concave_deg, 'concave'],
    [hardware.max_convex_deg, 'convex'],
]) {
    if (limit !== null && !(limit >= 0)) errors.push(`The ${side} limit must be a number, 0 or more.`);
  }
  if (listed.length && !errors.length && !usableDetents(hardware, config.direction).some((d) => d > 0)) {
    const limit = config.direction === 'concave' ? hardware.max_concave_deg : hardware.max_convex_deg;
    errors.push(
      `No angle on your list is within the ${formatAngle(limit ?? 0)} ${config.direction} limit, so nothing can curve.`,
);
  }

  const v = target.value;
  if (!Number.isFinite(v)) errors.push('Curve target must be a number.');
  else
    switch (target.mode) {
      case 'percent_circle':
        if (v < 0 || v > 100) errors.push('Percent of a circle must be between 0 and 100.');
        break;
      case 'sweep_deg':
        if (v < 0 || v > 360) errors.push('Total sweep must be between 0° and 360°.');
        break;
      case 'radius':
        if (!(v > 0)) errors.push('Radius must be greater than zero.');
        break;
      case 'depth_ratio':
        if (v < 0) errors.push('Depth as a percent of width cannot be negative.');
        break;
      case 'depth':
        if (v < 0) errors.push('Depth cannot be negative.');
        break;
      case 'chord':
        if (!(v > 0)) errors.push('Straight-line width must be greater than zero.');
        else if (v > panel.width_m * panel.count + 1e-9)
          errors.push(
            `A straight wall of ${panel.count} panels is only ${(panel.width_m * panel.count).toFixed(2)} m wide, and curving it can only make it narrower.`,
);
        break;
      case 'angle_per_joint':
        if (v < 0 || v > 90) errors.push('Angle per joint must be between 0° and 90°.');
        break;
      case 'percent_max_angle':
        if (v < 0 || v > 100) errors.push('Percent of hardware maximum must be between 0 and 100.');
        break;
    }

  return errors;
}

/**
 * Everything here is judged against the build actually chosen, not the
 * hardware's full list, an earlier cut quoted the hardware's smallest angle
 * while the build used another, and fired "closest match" on builds that were
 * well inside tolerance while missing ones that were 50 mm out.
 */
/** "panels 2, 4 and 5", or "panels 2, 4, 5 and 8 more" once the list gets long. */
function listJoints(panels) {
  const shown = panels.slice(0, 4).map((n) => `panel ${n}`);
  const rest = panels.length - shown.length;
  const list = shown.join(', ');
  return rest > 0 ? `${list} and ${rest} more` : list.replace(/, ([^,]*)$/, ' and $1');
}

/** "second", "third", "fourth"… for how often a joint can bend. */
export function ordinal(n) {
  return (
    ['zeroth', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth'][n] ??
    `${n}th`
);
}

export function warnings(ctx) {
  const out = [];
  const { config, idealAngleDeg, maxHardwareAngleDeg, achieved, target, chosen, system } = ctx;
  const { panel } = config;
  const joints = chosen.joints;
  const tol = formatSmall(config.tolerance_m, system);

  // 1. Can the hardware physically get there?
  if (idealAngleDeg > maxHardwareAngleDeg + 1e-9) {
    // The chord is a whole footer, not a panel: on 1 m footers the tightest
    // radius is twice what a 500 mm panel would suggest.
    const tightest = faceRadiusForAngle(panel.width_m * ctx.plan.maxPanels, maxHardwareAngleDeg);
    const allAtMax = joints.every((a) => Math.abs(a - maxHardwareAngleDeg) < 1e-9);
    out.push(
      `Out of range: this curve wants ${formatAngle(idealAngleDeg)} per joint and the hardware tops out at ${formatAngle(maxHardwareAngleDeg)}. ` +
        `The tightest radius these panels can reach is ${formatLength(tightest, system)} to the front face. ` +
        (allAtMax
          ? `Every joint is at ${formatAngle(maxHardwareAngleDeg)} and the wall still falls short of the drawing.`
          : 'The wall will fall short of the drawing.'),
);
  }

  // 2. Off the drawing: only when the chosen build is over the user's limit.
  //    Within the limit, the reason line under the headline already says how
  //    close it is, and a second "not exact" warning just contradicted it.
  if (!chosen.within_tolerance) {
    const closest = ctx.options.reduce((b, o) => (o.deviation_m < b.deviation_m ? o : b), chosen);
    const isClosest = closest.id === chosen.id;
    out.push(
      `Off the drawing: this build lands up to ${formatSmall(chosen.deviation_m, system)} from the drawn arc, over your ${tol} limit. ` +
        `It builds ${formatPercent(achieved.percent_circle)} against ${formatPercent(target.percent_circle)} asked for.` +
        (isClosest
          ? ' This is the closest these angles can get.'
          : ` Tightest uses ${describeAngles(closest)} and gets to ${formatSmall(closest.deviation_m, system)}.`),
);
  }

  // 3. Footers wider than a panel: fewer joints, each doing more work.
  const { plan } = ctx;
  const fmt = (m) => formatLength(m, system);
  if (plan.maxPanels > 1) {
    const part = plan.footers.find((f) => f.part);
    out.push(
      `Bars: ${describeFooters(plan.footers, fmt)}, laid out in the build sheet. ` +
        `They span up to ${plan.maxPanels} panels, so the wall bends at ${plan.free.size} of its ${joints.length} joints, after ${listJoints([...plan.free].map((i) => i + 1))}. ` +
        `The joints inside a bar stay straight, so where the wider bars go decides where the wall can bend.` +
        (part
          ? ` The wall runs out before the last bar is full: it carries ${part.panels} of its ${panelsUnder(part.width_m, panel.width_m)} panels.`
          : ''),
);
  }

  // 4. What the facets look like. Industry guidance: under 3° cabinet to
  //    cabinet reads as a curve, 3 to 6° depends on content, past 6° the faceting
  //    and off-axis color shift show.
  const curved = joints.filter((a) => a > 0);
  const sharpest = curved.length ? Math.max(...curved) : 0;
  const atSharpest = curved.filter((a) => a === sharpest).length;
  const flats = joints.length - curved.length;
  const flatNote = flats && curved.length ? ` ${flats} of ${joints.length} joints are flat, so the curve is carried by the kinks rather than spread evenly.` : '';
  const counts = `(${atSharpest} of ${joints.length} joints)`;
  if (sharpest > 6) {
    const gentler = ctx.options.find(
      (o) => o.within_tolerance && o.max_angle_deg <= 6 && o.used_angles_deg.length > 0,
);
    out.push(
      `The sharpest joints are ${formatAngle(sharpest)} ${counts}. Past about 6° the facets and off-axis color shift are visible. This is where a flexible or purpose-curved product is normally used.` +
        flatNote +
        (gentler
          ? ` ${gentler.used_angles_deg.map((a) => formatAngle(a)).join(' + ')} also fits within ${tol} and keeps every joint at 6° or under.`
          : ''),
);
  } else if (sharpest > 3) {
    out.push(
      `The sharpest joints are ${formatAngle(sharpest)} ${counts}. Between 3° and 6° reads well on most content but can show on wide flat gradients and from steep angles.` +
        flatNote,
);
  }

  // 5. Nothing curved at all, although a curve was asked for.
  if (!curved.length && target.sweep_deg > 0) {
    out.push(
      `Every joint is left flat: at ${formatPercent(target.percent_circle)} the curve is too gentle for these angles to improve on a straight wall.`,
);
  }

  // 6. Shapes that stop being walls.
  if (achieved.sweep_deg >= 359) {
    out.push('The wall closes into a full ring. Check the last joint physically lands on the first panel.');
  } else if (achieved.sweep_deg > 180) {
    out.push(
      `At ${formatAngle(achieved.sweep_deg, 1)} of sweep the wall wraps past a half round: the ends face each other and the footprint, not the width, is what has to fit the venue.`,
);
  }

  return out;
}

// ---- The solver ------------------------------------------------------------

/**
 * The only orchestrator. Everything the UI shows comes from here, so any number
 * on screen can be pinned by a test without a browser.
 *
 * Order matters: resolve the target to one ideal angle, snap that onto the
 * detents the hardware actually has, build the wall that results, and measure
 * the built wall rather than the arc that was asked for.
 */

const ZERO = {
  sweep_deg: 0,
  percent_circle: 0,
  total_turn_deg: 0,
  radius_joints_m: 0,
  radius_face_m: 0,
  chord_m: 0,
  depth_m: 0,
  depth_apex: { x: 0, y: 0 },
  depth_foot: { x: 0, y: 0 },
  depth_ratio_pct: 0,
  arc_length_m: 0,
  footprint_w_m: 0,
  footprint_d_m: 0,
  wall_height_m: 0,
};

function zeroed(config, errors) {
  return {
    config,
    errors,
    warnings: [],
    ideal_angle_deg: 0,
    target_radius_m: 0,
    target: ZERO,
    achieved: ZERO,
    joints: [],
    pattern: [],
    placements: [],
    vertices: [],
    target_vertices: [],
    max_arc_deviation_m: 0,
    uniform: true,
    footers: [],
    datum_at: 0,
    options: [],
    chosen_option_id: 'flat',
    recommended_option_id: 'flat',
    choice_reason: '',
    angle_usage: [],
    flat_joints: 0,
  };
}

/**
 * Every even wall the stock can build: a run length that divides the wall, the
 * same bend after every run, and each run tiled with footers from stock. The
 * joins between footers INSIDE a run stay flat, a 1 m and a 0.5 m footer make a
 * 3-panel run just as well as one 1.5 m bar. Rounding the wanted angle to the
 * nearest detent is what a crew does by hand; this is that, done properly.
 */
function evenBuilds(
  subset,
  panelCount,
  stockPanels,
  panelToMeters,
) {
  const out = [];
  for (let run = 1; run <= panelCount; run++) {
    if (panelCount % run !== 0) continue;
    const tiling = tile(run, stockPanels);
    if (!tiling) continue;
    const run_m = Array.from({ length: panelCount / run }, () => tiling.map(panelToMeters)).flat();
    const free = new Set        ();
    let at = 0;
    for (const k of run_m.map((m) => stockPanels.find((p) => panelToMeters(p) === m) ?? 1)) {
      at += k;
      if (at < panelCount) free.add(at - 1);
    }
    // A straight wall once (the longest run), then each angle at this spacing.
    for (const angle of run === panelCount ? [0] : subset) {
      out.push({
        joints: Array.from({ length: panelCount - 1 }, (_, i) => ((i + 1) % run === 0 ? angle : 0)),
        run_m,
        free,
      });
    }
  }
  return out;
}

/** Footer sizes, in panels, that add up to exactly `run`, fewest bars first. */
function tile(run, sizes) {
  const best = [[]];
  for (let n = 1; n <= run; n++) {
    best[n] = null;
    for (const k of sizes) {
      const rest = n - k >= 0 ? best[n - k] : null;
      if (rest && (!best[n] || rest.length + 1 < best[n] .length)) best[n] = [k, ...rest];
    }
  }
  return best[run] ?? null;
}

/** The datum as a position along the wall, in half-panel steps. */
function datumPosition(origin, panelCount) {
  if (typeof origin === 'number') return snapDatum(origin, panelCount);
  if (origin === 'left') return 0.5;
  if (origin === 'right') return panelCount + 0.5;
  return (panelCount + 1) / 2;
}

/** Beam width when re-fitting angles for each shortlisted layout. */
const LAYOUT_BEAM = 80;

export function solveCurve(config, system = 'metric') {
  const errors = inputErrors(config, system);
  if (errors.length) return zeroed(config, errors);

  const { panel, hardware, direction, target, build_from } = config;
  const detents = usableDetents(hardware, direction);
  const maxHardware = maxAngle(hardware, direction);
  const positiveDetents = detents.filter((d) => d > 0);

  // Footers wider than a panel hold the joints inside them rigid, so the wall
  // bends as a chain of footer-wide segments: the arc is shared out over the
  // joints BETWEEN footers, not over every joint.
  const plan = footerPlan(config);
  const ideal = idealAngle(target, {
    widthM: panel.width_m,
    count: panel.count,
    maxAngleDeg: maxHardware,
    pivotOffsetM: hardware.pivot_offset_m,
    direction,
  });
  // The drawn arc is the same circle whatever the footers: resolve it at panel
  // resolution, then give one footer joint the work of the panels it spans. A
  // segment chord cuts across the arc, and that shortfall is real and belongs in
  // the deviation figure. (Deriving the arc from a rounded segment count instead
  // compared a 20 % wall against a 17.8 % arc.)
  //
  // With a mixed run the footers do not all carry the same share, so the angle
  // quoted is what the widest footer joint has to do, the one that runs out of
  // hardware first.
  const idealPerSegment = ideal * plan.maxPanels;

  const widths = new Array(panel.count).fill(panel.width_m);
  const jointCount = panel.count - 1;
  // Only the joins between footers can bend. When the footer sizes leave a real
  // choice about WHERE they go, that choice is part of what gets solved.
  // Stock, not an order: the same size twice is still one size.
  const sizes = hardware.footer_widths_m.length
    ? [...new Set(hardware.footer_widths_m)].sort((a, b) => a - b)
    : [panel.width_m];
  const onlySize = sizes.length === 1 ? panelsUnder(sizes[0], panel.width_m) : null;
  // A screen's corners (screenCurve): the corner bars sit where they sit,
  // no footer runs across a break, and a corner's seam stays flat. Every
  // build is searched around them, and any that ignores them is left out.
  const corners = config.layout_constraints || null;
  const fixed = corners ? corners.pieces : [];
  const breaks = corners ? corners.breaks : [];
  const flatJoints = new Set(corners ? corners.flat : []);
  const layoutIsForced = !corners && onlySize !== null && panel.count % onlySize === 0;
  const respects = (candidate) => {
    if (!corners) return true;
    const starts = new Map();
    let at = 0;
    for (const w of candidate.run_m) {
      const k = panelsUnder(w, panel.width_m);
      starts.set(at, k);
      at += k;
    }
    return fixed.every((p) => starts.get(p.start) === p.size)
      && breaks.every((b) => starts.has(b))
      && [...flatJoints].every((j) => !candidate.joints[j]);
  };

  // Tightest fit means the closest wall; the others will give up a few mm for
  // an evenly spread pattern.
  const preferEven = config.fit_goal !== 'tightest';
  const stockPanels = [...new Set(sizes.map((w) => panelsUnder(w, panel.width_m)))].sort((a, b) => b - a);
  const panelToMeters = (k) => sizes.find((w) => panelsUnder(w, panel.width_m) === k) ?? panel.width_m;

  const candidates = (subset) => [
    ...fitted(subset).filter(respects),
    // Even walls are built directly, a regular spacing is not something the
    // fitter aims for, and the crew's "5° every third panel" should always be
    // on the table.
    ...evenBuilds(subset, panel.count, stockPanels, panelToMeters).filter(respects),
];

  const fitted = (subset) => {
    const angles = [0, ...subset];
    if (layoutIsForced) {
      return [
        {
          joints: fitJoints(jointCount, ideal, angles, build_from, DEFAULT_BEAM, (i) => plan.free.has(i), preferEven),
          run_m: plan.footers.map((f) => f.width_m),
          free: plan.free,
        },
];
    }
    // Shortlist layouts, then fit the angles properly for each: the layout
    // search scores from the left end, and a wall built center out wants its
    // angles worked out from the center. Layouts that free up the same joints
    // fit identically, so only one of each is worth the work.
    const seenMasks = new Set        ();
    const shortlist = [];
    for (const layout of searchLayouts({
      panelCount: panel.count,
      panelWidthM: panel.width_m,
      sizes,
      angles,
      idealDeg: ideal,
      beamWidth: 160,
      keep: 24,
      fixed,
      breaks,
      flat: [...flatJoints],
    })) {
      const free = footerPlan(config, layout.run_m).free;
      const mask = [...free].sort((a, b) => a - b).join(',');
      if (seenMasks.has(mask)) continue;
      seenMasks.add(mask);
      shortlist.push({
        joints: fitJoints(jointCount, ideal, angles, build_from, LAYOUT_BEAM, (i) => free.has(i) && !flatJoints.has(i), preferEven),
        run_m: layout.run_m,
        free,
      });
      if (shortlist.length >= 8) break;
    }
    return shortlist;
  };

  const common = {
    widths,
    direction,
    // The wall sits on its datum: deviation is measured from where the build
    // starts, so drift shows up where it really lands.
    anchor: build_from,
    pivotOffsetM: hardware.pivot_offset_m,
    panelDepthM: panel.depth_m,
    wallHeightM: panel.rows * panel.height_m,
  };
  const wanted = buildCurve({ ...common, joints: new Array(jointCount).fill(ideal) });

  // Try every subset of the angles, rank them, and build the winner, or the
  // user's own pick, if they made one and it still exists.
  const ranked = rankOptions(
    buildOptions({
      angles: positiveDetents,
      jointCount,
      idealDeg: ideal,
      origin: build_from,
      candidates,
      build: common,
      wanted: wanted.vertices,
      toleranceM: config.tolerance_m,
    }),
    config.fit_goal,
);
  // Nothing builds around the corners (the stock was checked first, so
  // this is a guard, not a case anyone meets).
  if (!ranked.length) return zeroed(config, ['These bar sizes cannot be laid around the corners. Light another size.']);
  const recommended = ranked[0];
  const manualPick =
    config.pattern_choice !== 'auto' ? ranked.find((o) => o.id === config.pattern_choice) : undefined;
  const chosen = manualPick ?? recommended;
  const angles = chosen.joints;
  const chosenPlan = footerPlan(config, chosen.run_m);
  const built = buildCurve({ ...common, joints: angles });
  const level = levelAngle(built.placements);
  // The depth dimension's two ends are drawing aids, so they travel with the
  // leveled view. The depth itself is a distance and does not change.
  const [apex, foot] = rotatePoints([built.measurements.depth_apex, built.measurements.depth_foot], level);
  const achieved = { ...built.measurements, depth_apex: apex, depth_foot: foot };

  const joints = angles.map((angle, i) => ({
    index: i + 1,
    angle_deg: angle,
    ideal_deg: ideal,
  }));

  const deviation = chosen.deviation_m;
  const uniform = angles.every((a) => Math.abs(a - angles[0]) < 1e-9);

  return {
    config,
    errors: [],
    warnings: warnings({
      config,
      idealAngleDeg: idealPerSegment,
      maxHardwareAngleDeg: maxHardware,
      plan: chosenPlan,
      achieved: built.measurements,
      target: wanted.measurements,
      chosen,
      options: ranked,
      manual: Boolean(manualPick),
      system,
    }),
    ideal_angle_deg: idealPerSegment,
    target_radius_m: radiusForAngle(panel.width_m, ideal),
    target: wanted.measurements,
    achieved,
    joints,
    pattern: runLength(angles),
    // Drawn level, whatever datum the maths used: deviation was measured above,
    // and a rigid rotation cannot change it.
    placements: rotatePlacements(built.placements, level),
    vertices: rotatePoints(built.vertices, level),
    target_vertices: rotatePoints(wanted.vertices, level),
    max_arc_deviation_m: deviation,
    uniform,
    footers: chosenPlan.footers,
    datum_at: datumPosition(build_from, panel.count),
    options: ranked,
    chosen_option_id: chosen.id,
    recommended_option_id: recommended.id,
    choice_reason: explainChoice(chosen, ranked, config.tolerance_m, Boolean(manualPick), system, config.fit_goal),
    angle_usage: chosen.used_angles_deg
      .map((a) => ({ angle_deg: a, count: angles.filter((x) => x === a).length }))
      .sort((a, b) => b.count - a.count),
    flat_joints: chosen.flat_joints,
  };
}

/**
 * What every angle this hardware offers would give on this wall, if all the
 * joints were set the same. The quick reference a crew actually wants: "5° gets
 * you a 5.7 m radius, is that the one?"
 *
 * Every joint equal makes this a true arc, so sweep is exact from the closed
 * form (n panels × angle) rather than measured, measuring can't see past 360°.
 */
export function detentTable(config) {
  if (inputErrors(config).length) return [];
  const { panel, hardware, direction } = config;
  const common = {
    widths: new Array(panel.count).fill(panel.width_m),
    direction,
    anchor: config.build_from,
    pivotOffsetM: hardware.pivot_offset_m,
    panelDepthM: panel.depth_m,
    wallHeightM: panel.rows * panel.height_m,
  };

  const plan = footerPlan(config);
  const bends = plan.free.size;

  return usableDetents(hardware, direction).map((angle) => {
    // Every footer joint at this angle: the wall turns once per footer join, and
    // spans one more chord than that.
    const sweep = angle * (bends + 1);
    const wraps = sweep > 360 + 1e-9 ? 'overlaps' : sweep >= 360 - 1e-9 ? 'ring' : 'no';
    const m =
      wraps === 'no'
        ? buildCurve({
            ...common,
            joints: Array.from({ length: panel.count - 1 }, (_, i) => (plan.free.has(i) ? angle : 0)),
          }).measurements
        : null;
    return {
      angle_deg: angle,
      // Mixed footers give no single chord, so read the radius off the built wall.
      radius_m: m && angle > 0 ? m.radius_face_m : faceRadiusForAngle(panel.width_m * plan.maxPanels, angle),
      sweep_deg: m ? m.sweep_deg : sweep,
      percent_circle: m ? m.percent_circle : (sweep / 360) * 100,
      chord_m: m ? m.chord_m : 0,
      depth_m: m ? m.depth_m : 0,
      wraps,
    };
  });
}

// ---- Starting values -------------------------------------------------------


/**
 * Starting values, not a vendor spec.
 *
 * 500 mm tiles and a 2.5 / 5 / 7.5 / 10 detent set are the most common rental
 * shape, but every number here is meant to be typed over, which is the whole
 * point of keeping a hardware registry out of this app.
 */
export const DEFAULT_DETENTS = [2.5, 5, 7.5, 10];

/** 25 mm, about an inch: close enough to the drawing that nobody on a deck will see it. */
export const DEFAULT_TOLERANCE_M = 0.025;

let seq = 0;
const nextId = () => `curve-${Date.now().toString(36)}-${(seq++).toString(36)}`;

export function makeCurve(name = 'Curve 1') {
  return {
    id: nextId(),
    name,
    panel: {
      width_m: 0.5,
      height_m: 1.0,
      depth_m: 0.085,
      count: 16,
      rows: 6,
    },
    hardware: {
      // One footer per panel unless the user says otherwise.
      footer_widths_m: [0.5],
      detents_deg: [...DEFAULT_DETENTS],
      max_concave_deg: null,
      max_convex_deg: null,
      pivot_offset_m: 0,
    },
    target: {
      mode: 'percent_circle',
      value: 20,
      // Always the front face: the house convention, and the only one the UI offers.
      radius_ref: 'face',
    },
    direction: 'concave',
    build_from: 'center',
    tolerance_m: DEFAULT_TOLERANCE_M,
    pattern_choice: 'auto',
    fit_goal: 'simplest',
  };
}

// ---- The Header/Footer tab's Curve ---------------------------------------
//
// A screen's Curve settings (layer.riggingCurve) and the screen they are
// laid on, turned into the calculator's own terms and back: the bar sizes
// are the tab's lit sizes in panels (the stock), the panel width is the
// screen's own, and what comes back is the bars left to right in panels
// and the angle at every joint between columns, signed the way the 3D
// stage turns them (a concave bend, ends toward the audience, is positive).

export const CURVE_DEFAULTS = Object.freeze({
  on: false,
  entry: 'percent',      // 'percent' of a full circle, or 'degrees' of sweep
  value: 20,             // in the entry's unit
  bend: 'concave',       // 'concave' | 'convex'
  goal: 'simplest',      // 'simplest' | 'even' | 'tightest'
  toleranceMm: 25,       // close enough to the drawing
  angles: [2.5, 5, 7.5, 10],
  from: 'center',        // the datum: 'center' | 'left' | 'right', or a spot
                         // along the wall in half panels (8 = the middle of
                         // panel 8, 8.5 = the joint between panels 8 and 9)
  pick: null,            // a build picked by hand: { id, key } (curvePickKey)
});

const finiteOr = (v, fallback) => {
  if (typeof v === 'boolean' || v === null || v === undefined || v === '') return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};

/** A screen's Curve settings held to their shape, field by field. */
export function cleanCurve(raw) {
  const src = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  const pick = (v, options, fallback) => (options.includes(v) ? v : fallback);
  const angles = Array.isArray(src.angles)
    ? [...new Set(src.angles.map((a) => Math.abs(finiteOr(a, 0))).filter((a) => a > 0))].sort((a, b) => a - b)
    : [...CURVE_DEFAULTS.angles];
  return {
    on: src.on === true,
    entry: pick(src.entry, ['percent', 'degrees'], CURVE_DEFAULTS.entry),
    value: Math.max(0, finiteOr(src.value, CURVE_DEFAULTS.value)),
    bend: pick(src.bend, ['concave', 'convex'], CURVE_DEFAULTS.bend),
    goal: pick(src.goal, ['simplest', 'even', 'tightest'], CURVE_DEFAULTS.goal),
    toleranceMm: Math.max(0, finiteOr(src.toleranceMm, CURVE_DEFAULTS.toleranceMm)),
    angles,
    from: typeof src.from === 'number' && Number.isFinite(src.from) && src.from > 0
      ? Math.round(src.from * 2) / 2
      : pick(src.from, ['center', 'left', 'right'], CURVE_DEFAULTS.from),
    pick: src.pick && typeof src.pick === 'object' && typeof src.pick.id === 'string' && typeof src.pick.key === 'string'
      ? { id: src.pick.id, key: src.pick.key } : null,
  };
}

/**
 * What a hand-picked build was picked against: everything the joints
 * depend on. Change any of it and the pick goes back to the app's own, as
 * in the curve calculator (where the datum does not reset it either).
 */
export function curvePickKey({ panels, panelWidthM, sizes, settings, corners = null }) {
  const s = cleanCurve(settings);
  const stock = [...new Set((sizes || []).map((n) => Math.round(finiteOr(n, 0))).filter((n) => n >= 1))].sort((a, b) => a - b);
  const key = [Math.round(finiteOr(panels, 0)), finiteOr(panelWidthM, 0), stock,
    s.entry, s.value, s.bend, s.goal, s.toleranceMm, s.angles];
  // A screen's corners change where the bars can go (a screen without
  // them keeps the key it always had).
  if (corners) key.push([corners.pieces.map((p) => [p.start, p.size]), corners.breaks, corners.flat]);
  return JSON.stringify(key);
}

/**
 * A screen's corners in the calculator's terms, or null when it has none
 * on a wall `count` panels wide: `pieces` the corner bars ({ start, size }
 * in panels from the left, 1 or 2 panels), `breaks` the panel edges the
 * bars split at for a corner under 90 degrees, `flat` the joints (0-based)
 * a corner's seam holds flat.
 */
export function curveCorners(count, pieces, breaks, flat) {
  const n = Math.round(finiteOr(count, 0));
  const whole = (v) => Number.isInteger(v);
  const p = [];
  for (const raw of Array.isArray(pieces) ? pieces : []) {
    const start = raw && finiteOr(raw.start, NaN);
    const size = raw && finiteOr(raw.size, NaN);
    if (!whole(start) || !whole(size) || size < 1 || start < 0 || start + size > n) continue;
    if (p.some((q) => start < q.start + q.size && q.start < start + size)) continue;
    p.push({ start, size });
  }
  p.sort((a, b) => a.start - b.start);
  const b = [...new Set((Array.isArray(breaks) ? breaks : []).filter((v) => whole(v) && v > 0 && v < n))].sort((x, y) => x - y);
  const f = [...new Set((Array.isArray(flat) ? flat : []).filter((v) => whole(v) && v >= 0 && v < n - 1))].sort((x, y) => x - y);
  return p.length || b.length || f.length ? { pieces: p, breaks: b, flat: f } : null;
}

/** The runs of panels between a screen's corner bars and breaks, as lengths. */
export function cornerRuns(count, corners) {
  const n = Math.round(finiteOr(count, 0));
  if (!corners) return n > 0 ? [n] : [];
  const blocked = (i) => corners.pieces.some((q) => i >= q.start && i < q.start + q.size);
  const cut = new Set(corners.breaks);
  const out = [];
  let from = null;
  for (let i = 0; i <= n; i++) {
    const free = i < n && !blocked(i);
    if (from !== null && (!free || cut.has(i))) { out.push(i - from); from = null; }
    if (free && from === null) from = i;
  }
  return out;
}

/**
 * How the stock covers the wall: the most panels the sizes can cover
 * exactly without passing the wall's edge. Equal to `panels` when they
 * tile it.
 */
export function stockCovers(panels, sizes) {
  const n = Math.max(0, Math.round(finiteOr(panels, 0)));
  const stock = (sizes || []).map((k) => Math.round(finiteOr(k, 0))).filter((k) => k >= 1);
  const fills = [true];
  let best = 0;
  for (let r = 1; r <= n; r++) {
    fills[r] = stock.some((k) => r - k >= 0 && fills[r - k]);
    if (fills[r]) best = r;
  }
  return best;
}

/**
 * The angle list as typed, every number in it: "2.5, 5, 7.5 10" and
 * "5 deg 10°" both read; null when there is no number at all.
 */
export function parseAngles(text) {
  const out = (String(text == null ? '' : text).match(/\d+(?:\.\d+)?|\.\d+/g) || []).map(Number);
  const list = [...new Set(out.filter((n) => Number.isFinite(n) && n > 0))].sort((a, b) => a - b);
  return list.length ? list : null;
}

/**
 * The calculator's answer for one screen.
 * `panels` across, `panelWidthM`, `sizes` (the lit bar sizes, in panels),
 * `settings` (cleanCurve's shape), `system` ('metric' | 'imperial').
 * { errors, warnings, result, bars: [panels...], joints: [signed degrees] }:
 * on an error, bars and joints are empty and the result is the zeroed one.
 */
export function screenCurve({ panels, panelWidthM, sizes, settings, system = 'metric', pieces, breaks, flat }) {
  const s = cleanCurve(settings);
  const count = Math.round(finiteOr(panels, 0));
  // The screen's corners (owner, 2026-11-10): a 90 degree corner keeps its
  // corner bar and the Curve lays its bars on each side up to it.
  const corners = curveCorners(count, pieces, breaks, flat);
  const pickKey = curvePickKey({ panels, panelWidthM, sizes, settings: s, corners });
  // Leftover stock is refused, never hung past the edge (owner, 2026-11-09):
  // a wall the lit sizes cannot cover exactly lays nothing. With corners,
  // each side of every corner has to be covered exactly.
  const lit = (sizes || []).filter((k) => Math.round(finiteOr(k, 0)) >= 1);
  if (count >= 2 && lit.length) {
    const gap = cornerRuns(count, corners).reduce((t, run) => t + run - stockCovers(run, lit), 0);
    if (gap > 0) {
      const where = corners ? ' beside the corners' : '';
      return {
        errors: [`These bar sizes leave ${gap} panel${gap === 1 ? '' : 's'} uncovered${where} on a ${count}-panel wall. Light another size.`],
        warnings: [], result: null, bars: [], joints: [], placed: [], pickKey,
      };
    }
  }
  const config = makeCurve('Screen');
  config.panel.count = Math.round(finiteOr(panels, 0));
  config.panel.width_m = finiteOr(panelWidthM, 0);
  const stock = [...new Set((sizes || []).map((n) => Math.round(finiteOr(n, 0))).filter((n) => n >= 1))].sort((a, b) => a - b);
  config.hardware.footer_widths_m = stock.map((n) => n * config.panel.width_m);
  config.hardware.detents_deg = [...s.angles];
  config.target = s.entry === 'degrees'
    ? { mode: 'sweep_deg', value: s.value, radius_ref: 'face' }
    : { mode: 'percent_circle', value: s.value, radius_ref: 'face' };
  config.direction = s.bend;
  config.build_from = typeof s.from === 'number' ? snapDatum(s.from, config.panel.count) : s.from;
  config.fit_goal = s.goal;
  config.tolerance_m = s.toleranceMm / 1000;
  // A build picked by hand holds while nothing the joints depend on changed.
  config.pattern_choice = s.pick && s.pick.key === pickKey ? s.pick.id : 'auto';
  if (corners) config.layout_constraints = corners;
  const result = solveCurve(config, system);
  if (result.errors.length) {
    return { errors: result.errors, warnings: [], result, bars: [], joints: [], placed: [], pickKey };
  }
  const bars = result.footers.map((f) => f.panels);
  // Each bar where it sits, the corner bars marked.
  const placed = result.footers.map((f) => ({
    start: f.from - 1, size: f.panels,
    corner: !!corners && corners.pieces.some((p) => p.start === f.from - 1 && p.size === f.panels),
  }));
  const sign = s.bend === 'concave' ? 1 : -1;
  const joints = result.joints.map((j) => (j.angle_deg === 0 ? 0 : sign * j.angle_deg));
  return { errors: [], warnings: result.warnings, result, bars, joints, placed, pickKey };
}
