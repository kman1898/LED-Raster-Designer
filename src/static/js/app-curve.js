// app-curve: the Header/Footer tab's Curve. A Curve checkbox on the
// selected screens; ticked, a compact form (the curve as a % of a full
// circle or degrees of sweep, concave or convex, Simplest / Even /
// Tightest, how close is close enough, the angles the locks have, and
// where the build starts) and the result: a build sheet strip of the bars
// with the angle at every join between them, a small plan of the wall
// from above against the drawn arc, the readouts, and every way to build
// it, ranked, each with Use this.
//
// The math is the curve calculator's own (curve-math.js). The bar sizes
// are the tab's lit sizes (the stock on the truck), in panel widths; the
// panel width is the screen's own.
//
// CURVE ON MEANS THE CALCULATOR OWNS THAT SCREEN'S BARS AND JOINT ANGLES:
// it lays the screen's bars on its side (header or footer), the tab's
// real bars, so the totals, the pull list and the binder count them, and
// writes the angle at every joint between columns into the screen's 3D
// placement (stage3d.jointsCol, concave positive, flat joints written as
// 0; the Curve is the only source of joint angles). Every change is one
// undo step. While Curve is on, Custom does not lay bars on that screen
// and Auto lays the curve again. Turned off, every joint goes flat and
// the wall takes the bars Auto lays from its lit sizes, in the same undo
// step (owner, 2026-11-18: the Curve's bars stayed on a wall that no longer
// curved, and nothing after laid them again); Clear turns it off with no
// bars at all. A WALL WHOSE BARS WERE LAID BY HAND GETS THEM BACK (owner,
// 2026-11-18): Curve on keeps each screen's own bars, on its side, and its
// laid corner pieces (riggingCustomSaved, saved with the show, so undo,
// redo and a reload keep it) and lays the Curve's; Curve off puts them back
// as they were, laid by hand, and forgets them. Auto, a lit size and Curve
// by hand while the Curve is on keep them; Clear forgets them, and a wall
// that was on Auto has none and takes Auto's bars. Lit sizes that
// cannot cover the wall exactly lay nothing (owner, 2026-11-09): the tab
// names the gap and the screen's bars and joints stay as they are.
//
// THE MATH RUNS IN THE BACKGROUND (curve-worker.js), so the page never
// stops: an edit changes the settings at once, the tab says "Working",
// and the bars and angles land, with the edit, as one undo step when the
// answer comes back. A newer edit of the same screen supersedes an older
// one, and an answer for a screen that has changed since (an undo, a
// reload) is dropped, so a stale result never lands. Answers are kept by
// everything they depend on.
//
// THE DATUM: Left, Center and Right pick at once; the red mark on the plan
// drags onto any panel middle or joint, in half steps (8 is the middle of
// panel 8, 8.5 the joint between 8 and 9), snapped as the calculator snaps
// it. A build picked by hand from Ways to build it holds until anything
// the joints depend on changes, then the app picks again (curvePickKey).
//
// CORNERS (app-corners.js): every corner is 90 degrees and takes its
// corner bar, and a corner's seam carries no curve angle (owner,
// 2026-11-09); the build sheet strip marks it Corner. WITH A CORNER, THE
// CURVE'S % APPLIES TO EACH SIDE AS ITS OWN WALL (owner, 2026-11-10): the
// corners split the screen into sides at their folds (curve-math.js
// screenCurve `pieces`, curveSides). Only the fold itself is flat: each
// side runs right up to it, its corner bar's arm included (a panel for a
// seam corner, half a panel for one down a panel's middle), so the joint
// where an arm meets the next bar takes the side's curve angle. Each side
// is worked out exactly as a wall of its own width at the same settings,
// the stock laid between its arms. The readouts, Ways to build it, Use
// this and the leftover-stock refusal are each side's and say which side
// ("left side", "right side", or "side 2" with more corners). The strip
// and the plan show the whole screen. Any change to the corners lays the
// Curve again in the same step. A pick saved for a side before sides ran
// up to the fold no longer matches its key, so the app picks again.
//
// Stored on the layer as riggingCurve (curve-math.js cleanCurve holds its
// shape); a show without it has every screen off, unchanged. The reference
// table of every joint at one angle is left out to keep the tab compact.
//
// THE CURVE LAYS ONLY THE PANEL'S LOCK POSITIONS (owner, 2026-11-10): a
// fixed list of signed angles per panel (curve-math.js cleanLocks), shown
// as chips above the form with where they came from: the show's own list
// for that panel ("Set by you"), the panel library's `curve_locks` ("From
// the panel library") or the owner's list (curve-math.js OWNER_CURVE_LOCKS,
// "Owner list"), first found. Edit opens a small list editor; Save writes
// the show's list for the panel (project.panelCurveLocks, keyed by
// curveLockKey) as one undo step, and every curved screen of that panel is
// laid again from it. A panel preset carries the show's list
// (serializeLayerAsPreset `curveLocks`), and a screen made from the preset
// hands it to a show that has none for that panel. A panel with no
// positions cannot be curved: the Curve says so and its checkbox waits. A
// saved curve laid at an angle the panel's list does not have opens as it
// was, flagged, until Auto or Use this lays it again from the list. The
// typed "Lock angles" of the first 1.7.0 builds (riggingCurve.angles) are
// no longer read.
//
// CUSTOM ON A CURVE (owner, 2026-11-18: "i need to be able to do custom
// curve just like header", ruled both): with Curve on, Custom lays bars by
// hand with the same click and drag as on a plain header, and a click on
// a joint of the build sheet strip sets its angle by hand from the panel's
// lock positions (or back to Auto). A row laid by hand (riggingCustom on
// its screens) keeps its bars as they are; the Curve fits the angles to
// them, bending only where no bar runs across, every joint set by hand
// held to its angle (riggingCurve.handJoints, in the row's joints, kept
// with the show like the rest of the Curve) and the rest filled in from
// the lock positions, the 20 degree cap and Build from as ever
// (curve-math.js screenCurve `hand`). Each gesture is one undo step. The
// strip draws hand laid bars and hand set angles in blue. Auto, or Curve
// ticked on, hands the row back to the Curve: its own bars and angles, the
// hand choices cleared. A joint set to bend under a bar is refused in
// plain words, the bar gesture or the pick left undone; a saved one the
// lock positions no longer have says so in the tab until it is set again.
// A corner added or taken off lays the row from the Curve again.
//
// A GROUPED WALL TAKES ONE CURVE (owner, 2026-11-16: "groups arent
// allowing curve which is not correct"). The members of a group that
// stand edge to edge carry one row of bars (app-rigging.js riggingRow),
// and the Curve runs along that row the same way: the calculator lays one
// curve over every member's columns in wall order, the % is of the whole
// row's front face, the datum is in the row's panels, and the seam between
// two members is an ordinary joint that takes a curve angle. The group has
// one Curve setting, set from any member: an edit writes it, and the lit
// sizes of the screen the tab shows, to every screen of the group, and
// the row is laid again. A GROUP STACKED IN ROWS (one screen above
// another, or a grid) CURVES AS ONE WALL TOO (owner, 2026-11-17): the
// Curve runs along the wall's top row (a header; its bottom row for a
// footer), the only row its bars go on, and every screen of the other rows
// takes the angles of the columns it stands under, so the wall bends at
// one set of seams (_curveStack). The bars go on the
// member each starts on, as Auto lays them; each member's own joints are
// its part of the answer; in 3D the members are chained (_curveRowPlace),
// each starting where the one before ends, turned by the seam's angle,
// the other rows' screens hung on the columns over them, and the Build
// from point (Left, Center, Right, or the point dragged on the plan, along
// the whole wall) staying where it stands (owner, 2026-11-17: "choose
// where the curve starts from"). A row is refused, said in plain words,
// when its panels are different widths, when its panels share no lock
// position but flat (the Curve lays only the positions every member's
// panel locks at), when a member of the group stands beside it out of
// line, or on a stacked wall when a screen's seams do not line up with the
// bar row's, reach past its ends, or its corners differ. A locked
// group is refused with the locked error. Grouping screens that each had a
// Curve moves nothing until Auto lays the row; ungrouping leaves each
// screen standing as it is, its part of the curve kept (the tab says it is
// not that screen's own curve until Auto lays it again).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';
import {
    anglesFromQuat, quatFromPlacement, quatInv, quatMul, quatRotate, round, s3dBuild, s3dCleanCorners,
    s3dCornerSeams, s3dCornersOn, s3dCornerTurn, s3dResolve, s3dSanitize, wrap180, DEG, PIVOT,
} from './app-stage3d.js';
import {
    cleanCurve, cleanLocks, convertCurveEntry, datumLabel, formatAngle, formatLength, formatLock, formatSmall,
    hasLockPositions, ownerCurveLocks, parseLocks, screenCurve, snapDatum, toleranceField,
    CURVE_MAX_JOINT_DEG, NO_LOCKS_MESSAGE,
} from './curve-math.js';

// Where a panel's lock positions came from, as the tab says it.
const LOCK_SOURCE_WORDS = {
    user: 'Set by you',
    library: 'From the panel library',
    owner: 'Built-in list',
    group: 'Every panel of the group locks at these',
};

const CACHE_MAX = 40;
const NS = 'http://www.w3.org/2000/svg';
const WORKER_URL = '/static/js/curve-worker.js';

const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);

const listWords = (names) => (names.length <= 1 ? (names[0] || '')
    : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1]);

// ---- a grouped row in 3D (pure) ---------------------------------------------
//
// A frame is { p: [x, y, z] mm, q: quaternion }. A heading h (radians) is
// a direction along the floor in a screen's own frame, as its column
// chain walks it (app-stage3d.js s3dWalk: positive turns toward the
// audience); the frame along the wall at heading h is q times the turn
// about the upright by -h.
const yawQ = (rad) => quatFromPlacement({ pitch: 0, yaw: rad / DEG, roll: 0 });
const vAdd = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const vSub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];

// A screen's bottom edge as built with `jointsCol` (and its own corners),
// in its own frame: { len mm, cum, colLen, at(a, side) }, at(a) the point
// `a` mm along it ({ x, z }) and the heading there on that side of a
// joint ('left' the segment ending there, 'right' the one starting).
// Null for a screen with no cabinets.
function curveEdge(layer, jointsCol) {
    const b = s3dBuild(layer, { jointsCol: jointsCol || {} });
    const n = b.colLen.length, k = b.rowLen.length - 1;
    if (!n || k < 0) return null;
    const cum = [0];
    b.colLen.forEach(v => cum.push(cum[cum.length - 1] + v));
    const pt = (i, u) => { const p = b.point(i, u, k, b.rowLen[k]); return [p[0], p[2]]; };
    const at = (a, side) => {
        let i = 0;
        if (side === 'left') { while (i < n - 1 && a > cum[i + 1] + 1e-6) i++; } else { while (i < n - 1 && a >= cum[i + 1] - 1e-6) i++; }
        const len = b.colLen[i];
        const u = Math.max(0, Math.min(len, a - cum[i]));
        const f = b.foldAt(i);
        let u0 = 0, u1 = len;
        if (f !== null) {
            if (u < f - 1e-6 || (side === 'left' && u <= f + 1e-6)) u1 = f; else u0 = f;
        }
        const p = pt(i, u), p0 = pt(i, u0), p1 = pt(i, u1);
        return { x: p[0], z: p[1], h: Math.atan2(p1[1] - p0[1], p1[0] - p0[0]) };
    };
    return { len: cum[n], cum, colLen: b.colLen, at };
}

// The frame `a` mm along a row of edges, each member standing at its own
// frame: on a joint (a seam between two members too) it heads halfway
// between the two sides, as a screen's middle does (app-stage3d.js
// s3dChain).
function frameAlong(edges, frames, a) {
    const L = frameSide(edges, frames, a, 'left'), R = frameSide(edges, frames, a, 'right');
    const rel = anglesFromQuat(quatMul(quatInv(L.q), R.q)).yaw * DEG;
    return { p: L.p, q: quatMul(L.q, yawQ(rel / 2)) };
}

// The frame `a` mm along a row of edges on one side of a joint ('left' the
// segment ending there, 'right' the one starting there).
function frameSide(edges, frames, a, side) {
    const offs = [];
    let acc = 0;
    edges.forEach(e => { offs.push(acc); acc += e.len; });
    let i = 0;
    if (side === 'left') { while (i < edges.length - 1 && a > offs[i] + edges[i].len + 1e-6) i++; } else { while (i < edges.length - 1 && a >= offs[i] + edges[i].len - 1e-6) i++; }
    const e = edges[i].at(Math.max(0, Math.min(edges[i].len, a - offs[i])), side);
    const f = frames[i];
    return { p: vAdd(f.p, quatRotate(f.q, [e.x, 0, e.z])), q: quatMul(f.q, yawQ(-e.h)) };
}

// The turn in degrees from frame `from` to frame `to` along the wall.
function turnBetween(from, to) {
    return -anglesFromQuat(quatMul(quatInv(from), to)).yaw;
}

class _Curve {
    _wireRiggingCurve() {
        const box = document.getElementById('rigging-curve-on');
        if (!box || box.dataset.wired) return;
        box.dataset.wired = '1';
        box.addEventListener('change', () => this.setRiggingCurveOn(box.checked));
        const group = (sel, key) => document.querySelectorAll(sel).forEach(btn => {
            btn.addEventListener('click', () => this.setRiggingCurveField(key, btn.dataset.value));
        });
        group('#rigging-curve-entry .rigging-curve-btn', 'entry');
        group('#rigging-curve-bend .rigging-curve-btn', 'bend');
        group('#rigging-curve-goal .rigging-curve-btn', 'goal');
        group('#rigging-curve-from .rigging-curve-btn', 'from');
        const field = (id, key) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', () => this.setRiggingCurveField(key, el.value));
        };
        field('rigging-curve-value', 'value');
        field('rigging-curve-tol', 'tolerance');
        this._wireCurveLockEditor();
        const ways = document.getElementById('rigging-curve-ways');
        if (ways) ways.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('[data-pick]') : null;
            if (!btn) return;
            // a side's own Ways to build it on a screen with corners
            const side = btn.closest('[data-side]');
            this.setRiggingCurveField('pick', btn.dataset.pick, side ? Number(side.dataset.side) : null);
        });
        this._wireCurvePlanDrag(document.getElementById('rigging-curve-plan'));
        // A click on a joint of the strip opens its angles below it; a
        // click on one of them sets it (Auto hands it back).
        const sheet = document.getElementById('rigging-curve-sheet');
        if (sheet) sheet.addEventListener('click', (e) => {
            const hit = e.target && e.target.closest ? e.target.closest('[data-joint]') : null;
            if (!hit) return;
            const primary = this._riggingPrimary(this._riggingScreens());
            const row = primary ? this._curveRow(primary) : null;
            if (!row) return;
            this._curveJointPick = { key: row.key, j: Number(hit.getAttribute('data-joint')) };
            this.refreshRiggingCurve();
        });
        const pick = document.getElementById('rigging-curve-joint');
        if (pick) pick.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('[data-joint-angle]') : null;
            const p = this._curveJointPick;
            if (!btn || !p) return;
            const v = btn.dataset.jointAngle;
            this.setRiggingCurveJoint(p.j, v === 'auto' ? null : Number(v));
        });
    }

    // ---- what is stored ---------------------------------------------------

    riggingCurveOf(layer) {
        return cleanCurve(layer && layer.riggingCurve);
    }

    riggingCurveOn(layer) {
        return !!layer && (layer.type || 'screen') === 'screen' && this.riggingCurveOf(layer).on;
    }

    // Readouts in the show's own unit: meters on a meter show, feet and
    // inches otherwise.
    _curveSystem() {
        return (typeof this.cableUnit === 'function' && this.cableUnit() === 'm') ? 'metric' : 'imperial';
    }

    // ---- the panel's lock positions ----------------------------------------

    // Which panel a screen is, for its lock positions: the library model it
    // saved ("ROE|Graphite GP2.6 Full Tile"), else the name typed for it,
    // else its cabinet's size in mm and pixels. Every screen with the same
    // key shares one list in the show.
    curveLockKey(layer) {
        const id = String((layer && layer.panelModelId) || '').trim();
        if (id) return id;
        const name = String((layer && layer.panelModelName) || '').trim();
        if (name) return `name:${name}`;
        const n = (v) => Number(v) || 0;
        return `cabinet:${n(layer && layer.panel_width_mm)}x${n(layer && layer.panel_height_mm)}mm:`
            + `${n(layer && layer.cabinet_width)}x${n(layer && layer.cabinet_height)}px`;
    }

    // The show's own lists, by curveLockKey.
    _curveShowLocks() {
        const m = this.project && this.project.panelCurveLocks;
        return m && typeof m === 'object' && !Array.isArray(m) ? m : {};
    }

    // The panel's list without the show's own: the library's curve_locks
    // where it has some for this model, else the owner's list; null when
    // neither speaks for it. Only a library model (panelModelId) has one.
    _curveBaseLocks(layer) {
        const id = String((layer && layer.panelModelId) || '');
        const cut = id.indexOf('|');
        if (cut < 0) return null;
        const saved = typeof this._catalogSavedPanel === 'function' ? this._catalogSavedPanel(layer) : undefined;
        const F = saved && saved.F;
        const lib = F ? cleanLocks(F.curve_locks) : null;
        if (hasLockPositions(lib)) {
            return { list: lib, source: 'library', note: typeof F.curve_locks_source === 'string' ? F.curve_locks_source : '' };
        }
        const own = ownerCurveLocks(id.slice(0, cut), id.slice(cut + 1));
        return own ? { list: cleanLocks(own), source: 'owner', note: '' } : null;
    }

    // A screen's lock positions: { key, list, source, note, base }, `list`
    // null and `source` null when its panel has none. `base` is what the
    // panel would have without the show's own list.
    curveLocksOf(layer) {
        const key = this.curveLockKey(layer);
        const base = this._curveBaseLocks(layer);
        const mine = cleanLocks(this._curveShowLocks()[key]);
        if (mine) return { key, list: mine, source: 'user', note: '', base };
        return base ? { key, ...base, base } : { key, list: null, source: null, note: '', base: null };
    }

    // The angles a curved screen stands at that its panel's list does not
    // have, signed, each once ([] when every one is on it).
    _curveOffList(layer, list) {
        const row = this._curveRow(layer);
        const tables = (this._curveMulti(row) ? this._curveAll(row) : [layer])
            .map(l => (l && l.stage3d && l.stage3d.jointsCol) || {});
        const have = new Set((list || []).map(a => Math.round(a * 1000)));
        const off = new Set();
        tables.forEach(table => Object.values(table).forEach(v => {
            const a = Number(v);
            if (Number.isFinite(a) && a !== 0 && !have.has(Math.round(a * 1000))) off.add(a);
        }));
        return [...off].sort((a, b) => a - b);
    }

    // Save the show's list for one panel (null takes it away, and the
    // panel's library or owner list applies again). One undo step: every
    // curved screen of that panel is laid again from it in the same step.
    setPanelCurveLocks(key, list, action = 'Curve Lock Positions') {
        if (!this.project || !key) return false;
        const now = this._curveShowLocks();
        const map = { ...now };
        if (list === null) delete map[key];
        else {
            const clean = cleanLocks(list);
            if (!hasLockPositions(clean)) return false;
            map[key] = clean;
        }
        if (JSON.stringify(map) === JSON.stringify(now)) return false;
        this.project.panelCurveLocks = map;
        this._curveSendShowLocks();
        const curved = (this.project.layers || []).filter(l => (l.type || 'screen') === 'screen'
            && this.curveLockKey(l) === key && this.riggingCurveOn(l) && !this._curveCannot(l)
            && !(typeof this._layerLocked === 'function' && this._layerLocked(l)));
        // (a grouped row lays again whole, its other screens with it)
        if (!(curved.length && this.riggingCurveRelayLater(curved, action, curved))) this.saveState(action);
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
        return true;
    }

    // The show's lists to the server, in order with the screens' saves.
    _curveSendShowLocks() {
        const body = JSON.stringify({ panelCurveLocks: this._curveShowLocks() });
        const p = fetch('/api/project', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
        if (typeof this._trackProjectSync === 'function') this._trackProjectSync(p);
        return p;
    }

    // A screen made from (or changed to) a panel preset that carries a list
    // of its own: the show takes it for that panel when it has none, and
    // keeps its own when it does. Rides the caller's undo step.
    _curveAdoptPresetLocks(layer, raw) {
        if (!this.project || !layer || !Array.isArray(raw)) return false;
        const clean = cleanLocks(raw);
        if (!hasLockPositions(clean)) return false;
        const key = this.curveLockKey(layer);
        const now = this._curveShowLocks();
        if (now[key]) return false;
        this.project.panelCurveLocks = { ...now, [key]: clean };
        this._curveSendShowLocks();
        return true;
    }

    // ---- the list editor -------------------------------------------------

    _wireCurveLockEditor() {
        const on = (id, ev, fn) => { const el = document.getElementById(id); if (el) el.addEventListener(ev, fn); };
        on('rigging-curve-lock-edit', 'click', () => this.openCurveLockEditor());
        on('rigging-curve-lock-add', 'click', () => this.addCurveLockDraft());
        on('rigging-curve-lock-save', 'click', () => this.saveCurveLockDraft());
        on('rigging-curve-lock-cancel', 'click', () => this.closeCurveLockEditor());
        on('rigging-curve-lock-reset', 'click', () => {
            const ed = this._curveLockEdit;
            this.closeCurveLockEditor();
            if (ed) this.setPanelCurveLocks(ed.key, null);
        });
        // Enter adds what is typed (and keeps the editor open).
        on('rigging-curve-lock-input', 'keydown', (e) => {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            this.addCurveLockDraft();
        });
        on('rigging-curve-lock-draft', 'click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('[data-remove-lock]') : null;
            if (btn) this.removeCurveLockDraft(Number(btn.dataset.removeLock));
        });
    }

    // Edit: the primary screen's panel list, ready to change.
    openCurveLockEditor() {
        const primary = this._riggingPrimary(this._riggingScreens());
        if (!primary) return;
        const locks = this.curveLocksOf(primary);
        this._curveLockEdit = { key: locks.key, draft: [...(locks.list || [0])] };
        const input = document.getElementById('rigging-curve-lock-input');
        if (input) input.value = '';
        this.refreshRiggingCurve();
        if (input) input.focus();
    }

    closeCurveLockEditor() {
        this._curveLockEdit = null;
        this.refreshRiggingCurve();
    }

    // Add what is typed: every number in it, each within 20 degrees either
    // way. One past that is refused and the box keeps what was typed.
    addCurveLockDraft(text = null) {
        const ed = this._curveLockEdit;
        if (!ed) return false;
        const input = document.getElementById('rigging-curve-lock-input');
        const raw = text !== null ? text : (input ? input.value : '');
        const list = parseLocks(raw);
        if (!list) {
            this._toast('Lock positions, type angles in degrees, like -5, 5.', true, 5000);
            return false;
        }
        const over = list.filter(a => Math.abs(a) > CURVE_MAX_JOINT_DEG + 1e-9);
        if (over.length) {
            this._toast(`Lock positions, ${over.map(a => formatLock(a)).join(' and ')} is past the ${CURVE_MAX_JOINT_DEG}° a curve lock bends. Type positions from -${CURVE_MAX_JOINT_DEG}° to +${CURVE_MAX_JOINT_DEG}°.`, true, 6000);
            return false;
        }
        ed.draft = cleanLocks([...ed.draft, ...list]);
        if (input && text === null) input.value = '';
        this.refreshRiggingCurve();
        return true;
    }

    removeCurveLockDraft(a) {
        const ed = this._curveLockEdit;
        if (!ed || !Number.isFinite(a) || a === 0) return;
        ed.draft = cleanLocks(ed.draft.filter(x => x !== a));
        this.refreshRiggingCurve();
    }

    // Save: anything still typed is added first. A list with no position
    // but flat is refused.
    saveCurveLockDraft() {
        const ed = this._curveLockEdit;
        if (!ed) return false;
        const input = document.getElementById('rigging-curve-lock-input');
        if (input && input.value.trim() && !this.addCurveLockDraft()) return false;
        if (!hasLockPositions(ed.draft)) {
            this._toast('Lock positions, add at least one angle besides flat, like -5, 5.', true, 5000);
            return false;
        }
        const { key, draft } = ed;
        this._curveLockEdit = null;
        if (!this.setPanelCurveLocks(key, draft)) this.refreshRiggingCurve();
        return true;
    }

    // The chips, where they came from, and the editor when it is open.
    _curveDrawLocks(primary, locks) {
        const chip = (text, extra = '') => `<span class="rigging-curve-lock" style="display: inline-flex; align-items: center; justify-content: center; gap: 3px; padding: 1px 6px; border: 1px solid #4a4a4a; border-radius: 9px; background: #1d1d1d; color: #ddd; font-size: 11px;"${extra}>${text}</span>`;
        const chipsEl = document.getElementById('rigging-curve-lock-chips');
        const srcEl = document.getElementById('rigging-curve-lock-source');
        const noneEl = document.getElementById('rigging-curve-lock-none');
        const has = hasLockPositions(locks.list);
        if (chipsEl) {
            const html = has ? locks.list.map(a => chip(formatLock(a), ` data-lock="${a}"`)).join('') : '';
            if (chipsEl.innerHTML !== html) chipsEl.innerHTML = html;
        }
        if (srcEl) {
            srcEl.style.display = has ? '' : 'none';
            srcEl.textContent = has ? LOCK_SOURCE_WORDS[locks.source] || '' : '';
            srcEl.title = locks.note || '';
            srcEl.dataset.source = locks.source || '';
        }
        if (noneEl) {
            noneEl.style.display = has ? 'none' : '';
            noneEl.textContent = has ? '' : NO_LOCKS_MESSAGE;
        }
        // The editor belongs to one panel: another screen's panel closes it.
        const ed = this._curveLockEdit && this._curveLockEdit.key === locks.key ? this._curveLockEdit : null;
        if (!ed) this._curveLockEdit = null;
        const editor = document.getElementById('rigging-curve-lock-editor');
        if (editor) editor.style.display = ed ? '' : 'none';
        const editBtn = document.getElementById('rigging-curve-lock-edit');
        if (editBtn) editBtn.style.display = ed ? 'none' : '';
        if (!ed) return;
        const draftEl = document.getElementById('rigging-curve-lock-draft');
        if (draftEl) {
            const html = ed.draft.map(a => (a === 0
                ? chip(formatLock(a), ' data-draft-lock="0" data-tooltip="Flat is always a position."')
                : chip(`${formatLock(a)}<button type="button" data-remove-lock="${a}" aria-label="Remove ${formatLock(a)}" style="border: none; background: none; color: #aaa; cursor: pointer; padding: 0; font-size: 11px; line-height: 1;">×</button>`,
                    ` data-draft-lock="${a}"`))).join('');
            if (draftEl.innerHTML !== html) draftEl.innerHTML = html;
        }
        const reset = document.getElementById('rigging-curve-lock-reset');
        if (reset) {
            const mine = locks.source === 'user';
            reset.style.display = mine ? '' : 'none';
            reset.textContent = !mine ? '' : locks.base
                ? (locks.base.source === 'library' ? 'Use the panel library list' : 'Use the built-in list')
                : 'Clear';
        }
    }

    // ---- the row a curve runs along -----------------------------------------

    // The row of bars a screen's Curve runs along (app-rigging.js
    // riggingRow): the screen alone, or the members of its group standing
    // edge to edge with it. Null on a screen with a header and a footer.
    // A screen of a group whose screens stand in more than one row (stacked,
    // or a grid) is on the whole wall's row (_curveStack).
    _curveRow(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return null;
        const side = this.riggingSideOf(layer);
        if (side === 'both') return null;
        return this._curveStack(layer, side) || this.riggingRow(layer, side);
    }

    // Every screen a row's Curve lays: the row's, and on a stacked wall the
    // screens below (or above) its bar row too.
    _curveAll(row) {
        return (row && row.all) || (row ? row.layers : []);
    }

    _curveAllIds(row) {
        return this._curveAll(row).map(l => l.id);
    }

    // Where a stacked wall's other screens stand on it, for telling a wall
    // changed since a request was made.
    _curveShape(row) {
        return JSON.stringify([(row && row.below || []).map(b => [b.layer.id, b.at, b.panels]), (row && row.why) || '']);
    }

    _curveMulti(row) {
        return !!row && this._curveAll(row).length > 1;
    }

    // A row's name in a message: its screen, or its screens.
    _curveRowWords(row) {
        return listWords(this._curveAll(row).map(l => l.name || `Screen ${l.id}`));
    }

    // A wall's name: its screen, or its group (else its screens).
    _curveWallName(row) {
        const all = this._curveAll(row);
        if (all.length < 2) return this._riggingRowName(row);
        const g = typeof this.getGroupOfLayer === 'function' ? this.getGroupOfLayer(all[0]) : null;
        return g && g.name ? g.name : this._curveRowWords(row);
    }

    // THE WHOLE WALL OF A GROUP (owner, 2026-11-17: "we need to curve
    // through the whole group"). The screens of a group that touch, edge to
    // edge or one above another, are one wall when they stand in more than
    // one row: one set of column joints across the wall's full width, every
    // screen in a column taking the same angles. The bars run along the
    // wall's top row (a header) or its bottom row (a footer) only: that row
    // (riggingRow) is what the calculator lays, its width the wall's, and
    // each other screen (`below`) takes the joints over its own columns,
    // `at` the wall column it starts on. Null when the screen's group
    // stands in one row (or not at all): the row is then riggingRow's, as
    // it always was. `why` says, in plain words, why the wall cannot take
    // one Curve: a screen's seams do not line up with the bar row's, a
    // screen reaches past its ends, the bar row has a gap, their corners
    // differ, a Pixel Map rotation, or bars on the other side.
    _curveStack(layer, side) {
        const members = typeof this.groupMembersOf === 'function' ? this.groupMembersOf(layer) : [];
        if (members.length < 2 || !members.includes(layer)) return null;
        const rects = new Map(members.map(m => [m.id, this._riggingRect(m)]));
        const touch = (a, b) => {
            const beside = (Math.abs(a.x + a.w - b.x) <= 1 || Math.abs(b.x + b.w - a.x) <= 1)
                && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1;
            const over = (Math.abs(a.y + a.h - b.y) <= 1 || Math.abs(b.y + b.h - a.y) <= 1)
                && a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1;
            return beside || over;
        };
        // the screens touching this one, the ones touching those, and on
        const wall = [layer];
        for (let k = 0; k < wall.length; k++) {
            const r = rects.get(wall[k].id);
            members.forEach(m => { if (!wall.includes(m) && touch(r, rects.get(m.id))) wall.push(m); });
        }
        if (wall.length < 2) return null;
        // one row is the row itself, as it always was
        const own = this.riggingRow(layer, side);
        if (wall.every(m => own.ids.includes(m.id))) return null;
        wall.sort((a, b) => rects.get(a.id).y - rects.get(b.id).y || rects.get(a.id).x - rects.get(b.id).x);
        const ids = wall.map(m => m.id);
        const name = (l) => l.name || `Screen ${l.id}`;
        const sides = wall.map(m => this.riggingSideOf(m));
        // the wall's side: the side its bars are on (a screen with none is
        // on whichever side it was last set to, and takes the wall's)
        const barred = (m) => this.riggingBarsOf(m, 'header').length > 0 || this.riggingBarsOf(m, 'footer').length > 0;
        const kind = sides.find((s, i) => s !== 'both' && barred(wall[i])) || sides.find(s => s !== 'both') || side;
        const base = { key: `wall:${kind}:${ids.join(',')}`, all: wall, allIds: ids, below: [] };
        const refuse = (why) => ({ ...own, ...base, why });
        const top = kind === 'footer' ? 'bottom' : 'top';
        const plural = (list, one, many) => (list.length === 1 ? one : many);
        if (sides.includes('both')) return refuse('');
        const turned = wall.filter(m => this.riggingTurned(m));
        if (turned.length) return refuse(`a Pixel Map rotation turns ${listWords(turned.map(name))}, so one curve cannot run across them`);
        // The bar row: the screens along the wall's top (or bottom) edge.
        const edgeY = (m) => { const r = rects.get(m.id); return kind === 'footer' ? r.y + r.h : r.y; };
        const extreme = kind === 'footer' ? Math.max(...wall.map(edgeY)) : Math.min(...wall.map(edgeY));
        const along = wall.filter(m => Math.abs(edgeY(m) - extreme) <= 1);
        // every screen with bars, and every one along the bar row, on the
        // wall's side
        const other = wall.filter((m, i) => sides[i] !== kind && (barred(m) || along.includes(m)));
        if (other.length) {
            return refuse(`${listWords(other.map(name))} ${plural(other, 'is', 'are')} set to the ${kind === 'header' ? 'footer' : 'header'}, and one curve runs along one side of the wall`);
        }
        const row = this.riggingRow(along[0], kind);
        const strays = along.filter(m => !row.ids.includes(m.id));
        if (strays.length) {
            return { ...row, ...base, why: `${listWords(along.map(name))} along the ${top} of the wall are not edge to edge, and its bars run along one unbroken row` };
        }
        const r0 = rects.get(row.layers[0].id);
        const unit = r0.w / Math.max(1, r0.panels);
        const below = [];
        const off = [];
        const past = [];
        for (const m of wall) {
            if (row.ids.includes(m.id)) continue;
            const r = rects.get(m.id);
            const panels = Math.max(0, Number(m.columns) || 0);
            const at = (r.x - r0.x) / unit;
            if (Math.abs(r.w / Math.max(1, r.panels) - unit) > 1 || Math.abs(at - Math.round(at)) * unit > 1) { off.push(m); continue; }
            const c = Math.round(at);
            if (c < 0 || c + panels > row.width) { past.push(m); continue; }
            below.push({ layer: m, at: c, panels });
        }
        const walled = { ...row, ...base, below };
        if (off.length) {
            return { ...walled, why: `the panel seams of ${listWords(off.map(name))} do not line up with the ${top} row's, and one curve bends every row at the same seams` };
        }
        if (past.length) {
            return { ...walled, why: `${listWords(past.map(name))} ${plural(past, 'reaches', 'reach')} past the ends of the ${top} row, and the ${kind} bars run along the ${top} row only` };
        }
        // Every screen in a column folds at the same corners.
        const cornersOf = (m, at) => s3dCornersOn(m, Number(m.columns) || 0).map(c => `${at + c.at}:${c.side}`);
        const edgeCorners = row.layers.flatMap((m, i) => cornersOf(m, row.offsets[i]));
        const folds = below.filter(b => {
            const inside = (key) => { const w = Number(key.split(':')[0]); return w > b.at + 0.75 && w < b.at + b.panels + 0.25; };
            const want = edgeCorners.filter(inside).sort();
            const have = cornersOf(b.layer, b.at).sort();
            return JSON.stringify(want) !== JSON.stringify(have);
        });
        if (folds.length) {
            return { ...walled, why: `the corners of ${listWords(folds.map(b => name(b.layer)))} do not line up with the ${top} row's, and every row of one wall folds at the same corners` };
        }
        return { ...walled, why: '' };
    }

    // The Curve a row is laid at: its first screen's with the Curve on,
    // else its first screen's. Every edit writes it to every screen of the
    // row, so they differ only on screens grouped after each was curved.
    _curveRowSettings(row) {
        const all = this._curveAll(row);
        const on = all.find(l => this.riggingCurveOf(l).on);
        return this.riggingCurveOf(on || all[0]);
    }

    // The Curve a screen shows and is laid at: its row's.
    riggingCurveFor(layer) {
        const row = this._curveRow(layer);
        return this._curveMulti(row) ? this._curveRowSettings(row) : this.riggingCurveOf(layer);
    }

    // Is a row curved: its Curve on, and one it can take.
    riggingCurveRowCurved(row) {
        return !!row && this._curveAll(row).length > 0 && this._curveRowSettings(row).on && !this._curveCannot(row.layers[0]);
    }

    // `layers` and the other screens of every curved grouped row they are
    // on: a lit size picked on one member is the whole row's stock.
    riggingCurveRowMates(layers) {
        const out = [...(layers || [])];
        for (const l of layers || []) {
            const row = this._curveRow(l);
            if (this._curveMulti(row) && this._curveRowSettings(row).on) {
                this._curveAll(row).forEach(m => { if (!out.includes(m)) out.push(m); });
            }
        }
        return out;
    }

    // The lock positions a row's Curve lays: a screen's own panel's, and
    // across a group only the positions every member's panel locks at.
    // Null when a panel has none.
    _curveRowLocks(row) {
        const lists = this._curveAll(row).map(l => this.curveLocksOf(l).list);
        if (lists.length === 1) return lists[0] || null;
        if (lists.some(x => !hasLockPositions(x))) return null;
        const has = (list, a) => list.some(b => Math.abs(b - a) < 1e-6);
        return cleanLocks(lists[0].filter(a => lists.every(x => has(x, a))));
    }

    // The lock positions the tab shows for the screen it shows: its
    // panel's, or on a grouped row whose panels differ, the ones every
    // panel of it locks at (the panel's own when they have none in common,
    // and the tab says why the group cannot curve).
    _curveLocksShown(primary, row) {
        const own = this.curveLocksOf(primary);
        if (!this._curveMulti(row)) return own;
        const list = this._curveRowLocks(row);
        if (!hasLockPositions(list)) return own;
        const same = this._curveAll(row).every(m => JSON.stringify(this.curveLocksOf(m).list) === JSON.stringify(own.list));
        return same ? own : { ...own, list, source: 'group', note: '' };
    }

    // A member of the row's group standing beside it, left or right, that
    // the row does not take in: why one curve cannot run on, or ''.
    _curveBeside(row) {
        const members = typeof this.groupMembersOf === 'function' ? this.groupMembersOf(row.layers[0]) : [];
        if (members.length < 2) return '';
        const ids = new Set(row.ids);
        const rects = row.layers.map(l => this._riggingRect(l));
        const unit = (r) => r.w / Math.max(1, r.panels);
        for (const m of members) {
            if (ids.has(m.id)) continue;
            const r = this._riggingRect(m);
            const touch = rects.some(q => (Math.abs(q.x + q.w - r.x) <= 1 || Math.abs(r.x + r.w - q.x) <= 1)
                && q.y < r.y + r.h - 1 && r.y < q.y + q.h - 1);
            if (!touch) continue;
            let why;
            if (this.riggingTurned(m) || row.layers.some(l => this.riggingTurned(l))) {
                why = 'a Pixel Map rotation turns one of them';
            } else if (!this._riggingKindsOf(m).includes(row.kind)) {
                why = `its bars are on the ${row.kind === 'header' ? 'footer' : 'header'}`;
            } else if (Math.abs(unit(r) - unit(rects[0])) > 1) {
                why = 'its panels are a different size';
            } else {
                why = `their ${row.kind === 'footer' ? 'bottom' : 'top'} edges do not line up`;
            }
            return `${m.name || `Screen ${m.id}`} stands beside ${row.layers.length > 1 ? 'them' : 'it'} in the group but ${why}, so one curve cannot run across them`;
        }
        return '';
    }

    // Why a screen cannot take a Curve, or '' when it can.
    // A Pixel Map rotation is no reason: it turns only the picture, and the
    // bars and the joints stay the wall's own columns (owner, 2026-11-10).
    // A grouped row curves as one wall (owner, 2026-11-16) unless its
    // panels differ in width, share no lock position but flat, or a member
    // of the group stands beside it out of line. Panels of different
    // heights are no reason: a curve bends the columns only.
    _curveCannot(layer) {
        if (this.riggingSideOf(layer) === 'both') return 'it has a header and a footer';
        const row = this._curveRow(layer);
        if (!row) return '';
        const name = (l) => l.name || `Screen ${l.id}`;
        const all = this._curveAll(row);
        const both = all.filter(l => this.riggingSideOf(l) === 'both');
        if (both.length) return `${listWords(both.map(name))} ${both.length === 1 ? 'has' : 'have'} a header and a footer`;
        const beside = this._curveBeside(row);
        if (beside) return beside;
        if (all.length < 2) return '';
        const mm = (l) => Number(l.panel_width_mm) || 500;
        if (new Set(all.map(mm)).size > 1) {
            return `their panels are different widths (${all.map(l => `${name(l)} ${mm(l)} mm`).join(', ')}), and one curve needs one panel width`;
        }
        // a stacked wall whose rows cannot share one set of joints
        if (row.why) return row.why;
        const lists = all.map(l => this.curveLocksOf(l).list);
        const without = all.filter((l, i) => !hasLockPositions(lists[i]));
        if (without.length && without.length < all.length) {
            const one = without.length === 1;
            return `${listWords(without.map(name))} ${one ? 'has' : 'have'} no curve lock positions for ${one ? 'its' : 'their'} panel yet. Select ${one ? 'it' : 'them'} to set them`;
        }
        if (!without.length && !hasLockPositions(this._curveRowLocks(row))) {
            return 'their panels share no lock position besides flat, and the Curve lays only positions every panel locks at';
        }
        return '';
    }

    // The name a refusal goes by: the screen, or a grouped row's screens.
    _curveWho(layer) {
        const row = this._curveRow(layer);
        return this._curveMulti(row) ? this._curveRowWords(row) : (layer.name || `Screen ${layer.id}`);
    }

    // What the calculator is asked for a screen as it stands: its corners
    // too, when it has any (a screen without keeps the input it always had).
    // On a grouped row, the row: every member's columns in wall order, the
    // first member's panel width and lit sizes (a Curve edit gives every
    // member the same), the lock positions every panel has, the corners
    // along it.
    _curveInput(layer, settings = null) {
        const row = this._curveRow(layer);
        const hand = this._curveHand(row);
        if (this._curveMulti(row)) {
            const lead = row.layers[0];
            const pieces = (row.spots || []).map(sp => ({ start: sp.start, size: sp.size }));
            return {
                panels: row.width,
                panelWidthM: (Number(lead.panel_width_mm) || 500) / 1000,
                sizes: this._riggingSizesOf(lead),
                settings: { ...(settings || this._curveRowSettings(row)), on: true },
                system: this._curveSystem(),
                locks: this._curveRowLocks(row),
                ...(pieces.length ? { pieces } : {}),
                ...(hand ? { hand } : {}),
            };
        }
        const s = settings || this.riggingCurveOf(layer);
        return {
            panels: Number(layer.columns) || 0,
            panelWidthM: (Number(layer.panel_width_mm) || 500) / 1000,
            sizes: this._riggingSizesOf(layer),
            settings: { ...s, on: true },
            system: this._curveSystem(),
            // the panel's lock positions, the only angles the Curve lays
            locks: this.curveLocksOf(layer).list || null,
            ...(this._curveCornersOf(layer) || {}),
            ...(hand ? { hand } : {}),
        };
    }

    // A row laid by hand (Custom on a curved row): its bars as they stand,
    // in the row's panels, and the joints set by hand. Null when the Curve
    // lays the row's bars.
    _curveHand(row) {
        if (!row || !row.layers || !row.layers.some(m => m.riggingCustom === true)) return null;
        const s = this._curveRowSettings(row);
        return {
            bars: (row.placed || []).map(b => ({ start: b.start, size: b.size })),
            joints: { ...(s.handJoints || {}) },
        };
    }

    // The row of `layers` handed back to the Curve: its bars and angles the
    // Curve's again, the hand choices cleared (Auto, Curve on, a corner).
    riggingCurveHandOff(layers) {
        for (const l of layers || []) {
            const row = this._curveRow(l);
            const all = row ? this._curveAll(row) : [l];
            all.forEach(m => {
                if (m.riggingCustom === true) m.riggingCustom = false;
                if (m.riggingCurve && m.riggingCurve.handJoints) {
                    const next = { ...m.riggingCurve };
                    delete next.handJoints;
                    m.riggingCurve = next;
                }
            });
        }
    }

    // A screen's corner bars in the calculator's terms, in its own bar
    // panels: { pieces }, or null when it has no corners.
    _curveCornersOf(layer) {
        if (typeof this.riggingCornerSpots !== 'function') return null;
        const pieces = this.riggingCornerSpots(layer).map(sp => ({ start: sp.start, size: sp.size }));
        return pieces.length ? { pieces } : null;
    }

    // An answer's joints, in the screen's own column order: its bars and
    // corner bars are in that order whatever its Pixel Map rotation.
    _curveJoints(layer, out) {
        return out.joints;
    }

    // ---- the background calculator -----------------------------------------

    _curveKeep(key, out) {
        if (!this._curveCache) this._curveCache = new Map();
        if (this._curveCache.size >= CACHE_MAX) this._curveCache.delete(this._curveCache.keys().next().value);
        this._curveCache.set(key, out);
    }

    // The answer already worked out for a screen as it stands, or null.
    riggingCurveCached(layer) {
        const key = JSON.stringify(this._curveInput(layer));
        return (this._curveCache && this._curveCache.get(key)) || null;
    }

    // The calculator's answer on this thread, for the tests and for a
    // browser with no workers. Kept like any other answer.
    riggingCurveSolve(layer, settings = null) {
        const input = this._curveInput(layer, settings);
        const key = JSON.stringify(input);
        const hit = this._curveCache && this._curveCache.get(key);
        if (hit) return hit;
        const out = screenCurve(input);
        this._curveKeep(key, out);
        return out;
    }

    _curveWorker() {
        if (this._curveWorkerBroken) return null;
        if (this._curveWorkerObj) return this._curveWorkerObj;
        try {
            if (typeof Worker !== 'function') throw new Error('no workers');
            const w = new Worker(WORKER_URL, { type: 'module' });
            w.onmessage = (e) => {
                const { id, out, error } = e.data || {};
                const job = this._curveJobs && this._curveJobs.get(id);
                if (!job) return;
                this._curveJobs.delete(id);
                if (error) job.resolve(screenCurve(job.input));
                else job.resolve(out);
            };
            w.onerror = () => {
                // The worker could not start or died: every job still
                // waiting is answered here, and the page works on alone.
                this._curveWorkerBroken = true;
                const jobs = [...((this._curveJobs && this._curveJobs.values()) || [])];
                if (this._curveJobs) this._curveJobs.clear();
                jobs.forEach(job => job.resolve(screenCurve(job.input)));
            };
            this._curveWorkerObj = w;
            return w;
        } catch (_) {
            this._curveWorkerBroken = true;
            return null;
        }
    }

    // A promise of the calculator's answer for `input`: kept, shared by
    // everyone who asks while it runs, worked out in the background.
    riggingCurveRequest(input) {
        const key = JSON.stringify(input);
        const hit = this._curveCache && this._curveCache.get(key);
        if (hit) return Promise.resolve(hit);
        if (!this._curvePending) this._curvePending = new Map();
        const pending = this._curvePending.get(key);
        if (pending) return pending;
        const w = this._curveWorker();
        const p = new Promise(resolve => {
            if (!w) {
                setTimeout(() => resolve(screenCurve(input)), 0);
                return;
            }
            if (!this._curveJobs) this._curveJobs = new Map();
            this._curveJobSeq = (this._curveJobSeq || 0) + 1;
            this._curveJobs.set(this._curveJobSeq, { input, resolve });
            w.postMessage({ id: this._curveJobSeq, input });
        }).then(out => {
            this._curvePending.delete(key);
            this._curveKeep(key, out);
            return out;
        });
        this._curvePending.set(key, p);
        return p;
    }

    // The log's line for one answer of the calculator as it lands on a wall
    // (2026-11-19): the settings it was asked with, the bars, how many
    // joints bend, the biggest, how many sit at the lock limit, the sweep
    // reached and how far off the drawn arc, and every warning or refusal.
    _curveLogOut(name, action, input, out) {
        const s = (input && input.settings) || {};
        const joints = Array.isArray(out && out.joints) ? out.joints.map(Number) : [];
        const bent = joints.filter(a => Math.abs(a) > 1e-9);
        const most = bent.reduce((m, a) => Math.max(m, Math.abs(a)), 0);
        const atLimit = bent.filter(a => Math.abs(a) >= CURVE_MAX_JOINT_DEG - 1e-6).length;
        const errors = (out && out.errors) || [];
        const warnings = (out && out.warnings) || [];
        const r = out && out.result;
        const a = r && r.achieved;
        const sides = Array.isArray(out && out.sides) ? out.sides.length : 0;
        const asked = `${s.value}${s.entry === 'degrees' ? ' deg' : '%'} ${s.bend || ''}, ${s.goal || ''}`;
        const details = {
            name, action, asked: { entry: s.entry, value: s.value, bend: s.bend, goal: s.goal, from: s.from },
            panels: input && input.panels, sizes: input && input.sizes,
            bars: ((out && out.bars) || []).slice(0, 40), joints: bent.length, maxJoint: Math.round(most * 100) / 100,
            atLimit, limit: CURVE_MAX_JOINT_DEG,
            ...(a ? { sweep: Math.round(a.sweep_deg * 10) / 10, percent: Math.round(a.percent_circle * 10) / 10 } : {}),
            ...(r && Number.isFinite(r.max_arc_deviation_m) ? { offMm: Math.round(r.max_arc_deviation_m * 1000) } : {}),
            ...(sides ? { sides } : {}), ...(out && out.hand ? { hand: true } : {}),
            ...(warnings.length ? { warnings: warnings.slice(0, 4) } : {}),
            ...(errors.length ? { errors: errors.slice(0, 4) } : {}),
        };
        const msg = errors.length
            ? `Curve on ${name} (${asked}) not laid: ${errors.slice(0, 2).join(' ')}`
            : `Curve on ${name} (${asked}): ${details.bars.length} bars (${details.bars.join(', ')}), `
                + `${bent.length} joints bend, biggest ${details.maxJoint} deg`
                + (atLimit ? `, ${atLimit} at the ${CURVE_MAX_JOINT_DEG} deg limit` : '')
                + (a ? `, sweep ${details.sweep} deg (${details.percent}% of a circle)` : '')
                + (details.offMm != null ? `, ${details.offMm} mm off the drawn arc at worst` : '')
                + (sides ? `, ${sides} sides` : '')
                + (warnings.length ? `; ${warnings.slice(0, 2).join(' ')}` : '');
        sendClientLog(errors.length ? 'curve_refused' : 'curve_solved', details,
            { area: 'rigging', level: errors.length ? 'warn' : 'info', msg });
    }

    // True while the calculator is working for the tab.
    riggingCurveBusy() {
        return (this._curveBusy || 0) > 0 || !!(this._curvePending && this._curvePending.size);
    }

    // ---- laying it --------------------------------------------------------

    // Each bar of an answer where it sits, its corner bars marked.
    _curvePlaced(out) {
        if (Array.isArray(out.placed) && out.placed.length) return out.placed;
        // where each bar starts: bars laid by hand may have gaps
        if (Array.isArray(out.starts) && out.starts.length === out.bars.length) {
            return out.bars.map((size, i) => ({ start: out.starts[i], size, corner: false }));
        }
        let at = 0;
        return out.bars.map(size => { const b = { start: at, size, corner: false }; at += size; return b; });
    }

    // The answer written onto the screen: its bars on its side, its
    // corners' corner bars, and the angle at every column joint. On a
    // grouped row, onto the row (_curveWriteRow). Returns the screens.
    _curveWrite(layer, out) {
        const row = this._curveRow(layer);
        if (this._curveMulti(row)) return this._curveWriteRow(row, out);
        const side = this.riggingSideOf(layer) === 'footer' ? 'footer' : 'header';
        this._riggingWrite(layer, side, this._curvePlaced(out).filter(b => !b.corner).map(b => ({ start: b.start, size: b.size })));
        const ats = typeof this.riggingCornerSpots === 'function' ? this.riggingCornerSpots(layer).map(sp => sp.at) : [];
        if (ats.length) this._riggingSetCornerBars(layer, ats, true);
        layer.riggingCustom = !!out.hand;
        const jointsCol = {};
        this._curveJoints(layer, out).forEach((a, j) => { jointsCol[String(j)] = a; });
        const prev = this._s3dPlacementOf(layer);
        layer.stage3d = s3dSanitize({ ...prev, jointsCol });
        return [layer];
    }

    // The answer written onto a grouped row: its bars across the row, each
    // on the member it starts on (as Auto lays them), the corner bars on
    // their members, the row's Curve on every member, each member's own
    // joints its part of the answer, and the members chained in 3D.
    _curveWriteRow(row, out) {
        const s = this._curveRowSettings(row);
        const placed = this._curvePlaced(out);
        this._riggingWriteRow(row, placed.filter(b => !b.corner).map(b => ({ start: b.start, size: b.size })));
        row.layers.forEach(m => {
            m.riggingCustom = !!out.hand;
            m.riggingCurve = { ...s };
            const ats = (row.spots || []).filter(sp => sp.owner === m).map(sp => sp.at);
            if (ats.length) this._riggingSetCornerBars(m, ats, true);
        });
        // A stacked wall's other screens: the bars belong on its top (or
        // bottom) row only, so theirs on that side come off, corner pieces
        // too; each takes the Curve and the joints over its own columns.
        (row.below || []).forEach(b => {
            const m = b.layer;
            m.riggingCustom = false;
            m.riggingCurve = { ...s };
            this._riggingWrite(m, row.kind, []);
            const ats = this.riggingCornerSpots(m).map(sp => sp.at);
            if (ats.length) this._riggingSetCornerBars(m, ats, false);
        });
        const list = this._curveJoints(row.layers[0], out);
        const { joints, seams } = this._curveSplit(row, list);
        this._curveRowPlace(row, joints, seams, {}, this._curveBelowJoints(row, list));
        return this._curveAll(row);
    }

    // A row's joints (0-based, across the row) as each member's own and the
    // seams between members: { joints: [[...] per member], seams: [...] }.
    _curveSplit(row, list) {
        const joints = row.layers.map((m, i) => Array.from({ length: Math.max(0, row.panels[i] - 1) },
            (_, j) => Number(list[row.offsets[i] + j]) || 0));
        const seams = row.layers.slice(0, -1).map((m, i) => Number(list[row.offsets[i] + row.panels[i] - 1]) || 0);
        return { joints, seams };
    }

    // The joints of a stacked wall's other screens (row.below), each the
    // wall's joints over its own columns: [[...] per screen].
    _curveBelowJoints(row, list) {
        return (row.below || []).map(b => Array.from({ length: Math.max(0, b.panels - 1) },
            (_, j) => Number(list[b.at + j]) || 0));
    }

    // Where the row's members stand in 3D, now, each { p, q } with the
    // joints it is built with (`flat`: as if every joint were flat).
    // `layers` in place of the row's own members.
    _curveRowNow(row, flat = false, layers = null) {
        const lay = typeof this._s3dLayout === 'function' ? this._s3dLayout() : undefined;
        return (layers || row.layers).map(m => {
            const p = this._s3dPlacementOf(m, lay);
            return { p: [p.x, p.y, p.z], q: quatFromPlacement(p), edge: curveEdge(m, flat ? {} : p.jointsCol) };
        });
    }

    // The angle at each seam of a grouped row as it stands in 3D, in
    // degrees, read off where its members stand; null when one has no
    // cabinets.
    _curveRowSeams(row) {
        const now = this._curveRowNow(row);
        if (now.some(n => !n.edge)) return null;
        return now.slice(0, -1).map((n, i) => {
            const e = n.edge.at(n.edge.len, 'left');
            const s = now[i + 1].edge.at(0, 'right');
            const a = turnBetween(quatMul(n.q, yawQ(-e.h)), quatMul(now[i + 1].q, yawQ(-s.h)));
            return Math.round(a * 1000) / 1000;
        });
    }

    // How far along a grouped row (mm, as `edges` build it) its members
    // stand put from: the Curve's Build from point, along the whole wall
    // (owner, 2026-11-17: a group builds from the point picked, as a screen
    // does): Left its left end, Right its right end, Center its middle, a
    // dragged point the middle of that panel or that joint. With a corner
    // along it, the side there stays put as on a screen (app-stage3d.js
    // s3dCornerAnchor).
    _curveRowAnchor(row, edges) {
        const total = edges.reduce((t, e) => t + e.len, 0);
        const from = this._curveRowSettings(row).from;
        if (from === 'left') return 0;
        if (from === 'right') return total;
        if (typeof from !== 'number') return total / 2;
        const half = snapDatum(from, row.width);
        if (Number.isInteger(half)) { const s = this._curveRowMm(row, edges, half - 1); return s.at + s.len / 2; }
        return this._curveRowMm(row, edges, half - 0.5).at;
    }

    // Where row panel `p` (0-based, across the row) starts along `edges`,
    // in mm, and how wide it is: { at, len }. `p` at the row's width is its
    // right end.
    _curveRowMm(row, edges, p) {
        let i = 0;
        while (i < row.layers.length - 1 && p >= row.offsets[i] + row.panels[i]) i++;
        const before = edges.slice(0, i).reduce((t, e) => t + e.len, 0);
        const c = Math.max(0, Math.min(edges[i].colLen.length, p - row.offsets[i]));
        return { at: before + edges[i].cum[c], len: edges[i].colLen[c] || 0 };
    }

    // Where each member of a grouped row stands in 3D for `joints` (each
    // member's own) and `seams`: one chain across the row, each member's
    // columns bent by its joints and its corners, the next member starting
    // where it ends, turned by the seam's angle. On a stacked wall each
    // screen below (or above) the row, bent by its own joints (`lower`, one
    // list per row.below), stands with its first column on the row's column
    // over it, so every row of the wall bends at the same seams, each at
    // the height it stands at. The row's anchor (_curveRowAnchor, the
    // Build from point) stays where it stands now, facing the same way;
    // `opts.flat` reads where it stands as if the row were flat (after a
    // reset to Show Look). Each member's footer that came or went since the
    // last step raises or lowers it, as a placed screen's does
    // (app-stage3d.js _s3dFollowFooters). `opts.off` stores no joints.
    _curveRowPlace(row, joints, seams, opts = {}, lower = null) {
        const ms = row.layers;
        const below = row.below || [];
        if (ms.length + below.length < 2 || typeof this._s3dPlacementOf !== 'function') return;
        const table = (list) => Object.fromEntries((list || []).map((a, j) => [String(j), a]));
        const lowJ = below.map((b, i) => (lower && lower[i]) || new Array(Math.max(0, b.panels - 1)).fill(0));
        const now = this._curveRowNow(row, !!opts.flat);
        const nowLow = this._curveRowNow(row, !!opts.flat, below.map(b => b.layer));
        const edges = ms.map((m, i) => curveEdge(m, table(joints[i])));
        const lowEdges = below.map((b, i) => curveEdge(b.layer, table(lowJ[i])));
        if (now.some(n => !n.edge) || edges.some(e => !e) || nowLow.some(n => !n.edge) || lowEdges.some(e => !e)) return;
        const anchor = this._curveRowAnchor(row, edges);
        const here = frameAlong(now.map(n => n.edge), now, anchor);
        // the new chain in the first member's frame, each member at the
        // height it stands at against the first
        const q0 = quatInv(now[0].q);
        const local = [{ p: [0, 0, 0], q: yawQ(0), psi: 0 }];
        for (let i = 1; i < ms.length; i++) {
            const prev = local[i - 1];
            const e = edges[i - 1].at(edges[i - 1].len, 'left');
            const s = edges[i].at(0, 'right');
            const psi = s.h - (e.h - prev.psi + (Number(seams[i - 1]) || 0) * DEG);
            const end = vAdd(prev.p, quatRotate(prev.q, [e.x, 0, e.z]));
            const q = yawQ(psi);
            const start = quatRotate(q, [s.x, 0, s.z]);
            const dy = quatRotate(q0, vSub(now[i].p, now[0].p))[1];
            local.push({ p: [end[0] - start[0], dy, end[2] - start[2]], q, psi });
        }
        // each screen of the wall's other rows: its first column on the
        // row's column `at`, heading the way that column heads
        const lowLocal = below.map((b, i) => {
            const w = frameSide(edges, local, this._curveRowMm(row, edges, b.at).at, 'right');
            const s = lowEdges[i].at(0, 'right');
            const q = quatMul(w.q, yawQ(s.h));
            const start = quatRotate(q, [s.x, 0, s.z]);
            const dy = quatRotate(q0, vSub(nowLow[i].p, now[0].p))[1];
            return { p: [w.p[0] - start[0], dy, w.p[2] - start[2]], q };
        });
        const there = frameAlong(edges, local, anchor);
        const qG = quatMul(here.q, quatInv(there.q));
        const pG = vSub(here.p, quatRotate(qG, there.p));
        const all = [...ms, ...below.map(b => b.layer)];
        const frames = [...local, ...lowLocal];
        const tables = [...joints, ...lowJ];
        const lifts = this._curveFooterLifts(all);
        all.forEach((m, i) => {
            const p = vAdd(vAdd(pG, quatRotate(qG, frames[i].p)), quatRotate(qG, [0, lifts[i], 0]));
            const a = anglesFromQuat(quatMul(qG, frames[i].q));
            m.stage3d = s3dSanitize({
                x: round(p[0], 3), y: round(p[1], 3), z: round(p[2], 3),
                pitch: round(wrap180(a.pitch), 6), yaw: round(wrap180(a.yaw), 6), roll: round(wrap180(a.roll), 6),
                pivot: PIVOT, jointsCol: opts.off ? {} : table(tables[i]),
            });
        });
    }

    // How far each of `layers` rises (mm) for a footer that came since the
    // last undo step, or falls for one that went: placed screens only, as
    // app-stage3d.js _s3dFollowFooters moves them.
    _curveFooterLifts(layers) {
        const entry = Array.isArray(this.history) ? this.history[this.historyIndex] : null;
        if (!entry || !entry.project || typeof this._s3dFootersIn !== 'function') return layers.map(() => 0);
        let before;
        try { before = this._s3dFootersIn(entry.project); } catch (_) { return layers.map(() => 0); }
        return layers.map(m => (before.has(m.id) ? this._s3dFooterMm(m) - before.get(m.id) : 0));
    }

    // Curve off on `layers` and the rest of their rows: every joint flat,
    // and a grouped row (a stacked wall's every row) stands in one straight
    // line again, its Build from point where it stood. A stacked wall that
    // cannot take one Curve goes flat screen by screen. Returns every
    // screen it changed.
    riggingCurveOff(layers) {
        const out = [];
        const seen = new Set();
        for (const l of layers || []) {
            const row = this._curveRow(l) || { key: `one:${l.id}`, layers: [l], panels: [Number(l.columns) || 0] };
            if (seen.has(row.key)) continue;
            seen.add(row.key);
            const all = this._curveAll(row);
            if (!all.some(m => this.riggingCurveOf(m).on)) continue;
            const chain = this._curveMulti(row) && !row.why;
            if (chain) {
                const flat = row.layers.map((m, i) => new Array(Math.max(0, row.panels[i] - 1)).fill(0));
                this._curveRowPlace(row, flat, new Array(row.layers.length - 1).fill(0), { off: true });
            }
            all.forEach(m => {
                const s = this.riggingCurveOf(m);
                if (s.on) m.riggingCurve = { ...s, on: false };
                if (!chain) this._curveUnlay(m);
            });
            all.forEach(m => { if (!out.includes(m)) out.push(m); });
        }
        return out;
    }

    // A reset to Show Look on the 3D tab (app-stage3d.js _s3dReset) of
    // `layers`: `apply` puts each back at its Show Look place, then each
    // curved grouped row among them is chained again from there, still
    // curved, its Build from point where it stands on the flat wall.
    // Returns the screens it placed.
    riggingCurveResetRows(layers, apply) {
        const keep = [];
        const seen = new Set();
        const own = (m, n) => {
            const t = (s3dSanitize(m.stage3d) || {}).jointsCol || {};
            return Array.from({ length: Math.max(0, n - 1) }, (_, j) => Number(t[String(j)]) || 0);
        };
        for (const l of layers || []) {
            const row = this._curveRow(l);
            if (!this._curveMulti(row) || row.why || seen.has(row.key)) continue;
            seen.add(row.key);
            if (!this._curveRowSettings(row).on) continue;
            const seams = this._curveRowSeams(row);
            if (!seams) continue;
            const joints = row.layers.map((m, i) => own(m, row.panels[i]));
            const lower = (row.below || []).map(b => own(b.layer, b.panels));
            keep.push({ row, joints, seams, lower });
        }
        apply();
        keep.forEach(({ row, joints, seams, lower }) => this._curveRowPlace(row, joints, seams, { flat: true }, lower));
        return keep.flatMap(k => this._curveAll(k.row));
    }

    // The angles a grouped row stands at, for the 3D panel: every joint
    // across it (each member's own but its corners' seams, and the seams
    // between members), and the wall's name. A stacked wall's every row
    // bends at these. Null for a screen alone.
    riggingCurveAcross(layer) {
        const row = this._curveRow(layer);
        if (!this._curveMulti(row) || !this._curveRowSettings(row).on) return null;
        const seams = this._curveRowSeams(row) || [];
        const angles = [];
        row.layers.forEach((m, i) => {
            const cols = row.panels[i];
            const corners = s3dCornerSeams(m, cols);
            const t = (s3dResolve(m, m.stage3d) || {}).jointsCol || {};
            for (let j = 0; j < cols - 1; j++) if (!corners.has(j)) angles.push(Number(t[String(j)]) || 0);
            if (i < seams.length) angles.push(seams[i]);
        });
        return { angles, name: this._curveWallName(row) };
    }

    // True when the screen carries exactly this answer's bars and angles
    // (a grouped row: every member, and its seams as they stand in 3D).
    _curveLaidMatches(layer, out) {
        const row = this._curveRow(layer);
        if (this._curveMulti(row)) {
            const want = this._curvePlaced(out).filter(b => !b.corner);
            if (JSON.stringify(row.placed.map(b => [b.start, b.size])) !== JSON.stringify(want.map(b => [b.start, b.size]))) return false;
            if ((row.spots || []).some(sp => !sp.bar)) return false;
            const list = this._curveJoints(layer, out);
            const { joints, seams } = this._curveSplit(row, list);
            const same = (m, own) => {
                const table = (m.stage3d && m.stage3d.jointsCol) || {};
                const placed = s3dSanitize({ jointsCol: Object.fromEntries(own.map((a, j) => [String(j), a])) }).jointsCol;
                return own.every((_, j) => table[String(j)] === placed[String(j)]);
            };
            if (!row.layers.every((m, i) => same(m, joints[i]))) return false;
            // a stacked wall's other rows: no bars on its side, its joints
            const lower = this._curveBelowJoints(row, list);
            if (!(row.below || []).every((b, i) => !this.riggingPlaced(b.layer, row.kind).length
                && !this.riggingCornerPiecesOf(b.layer).length && same(b.layer, lower[i]))) return false;
            const got = this._curveRowSeams(row);
            return !!got && seams.every((a, i) => Math.abs(got[i] - a) < 0.01);
        }
        const side = this.riggingSideOf(layer) === 'footer' ? 'footer' : 'header';
        const bars = this.riggingPlaced(layer, side);
        const want = this._curvePlaced(out).filter(b => !b.corner);
        if (JSON.stringify(bars.map(b => [b.start, b.size])) !== JSON.stringify(want.map(b => [b.start, b.size]))) return false;
        if (typeof this.riggingCornerSpots === 'function' && this.riggingCornerSpots(layer).some(sp => !sp.bar)) return false;
        const table = (layer.stage3d && layer.stage3d.jointsCol) || {};
        const joints = this._curveJoints(layer, out);
        const placed = s3dSanitize({ jointsCol: Object.fromEntries(joints.map((a, j) => [String(j), a])) }).jointsCol;
        return joints.every((_, j) => table[String(j)] === placed[String(j)]);
    }

    // Curve off: every column joint goes flat. An
    // old centre block is moved to the bottom middle first (s3dResolve), so
    // the block written back stands where it stood.
    // The stored angles are read off the block as saved: a screen whose
    // Curve is already off reads none (s3dResolve), but they are still
    // there to take away.
    _curveUnlay(layer) {
        const raw = layer.stage3d && layer.stage3d.jointsCol;
        if (!raw || typeof raw !== 'object' || !Object.keys(raw).length) return;
        const prev = s3dResolve(layer, layer.stage3d);
        if (prev) layer.stage3d = { ...prev, jointsCol: {} };
    }

    // The curved screens among `layers` laid again from their settings as
    // they now stand, in the background; when the answers are in, those
    // screens and `others` (whose edit rides in the same step) are saved as
    // one undo step named `action`. False, with nothing scheduled, when
    // none of `layers` is curved. `opts.misses` are rows the caller could
    // not fit, said with any the Curve could not lay. A screen on a grouped
    // row lays the whole row, one answer for all of its screens.
    riggingCurveRelayLater(layers, action, others = [], opts = {}) {
        const rows = [];
        const seen = new Set();
        for (const l of layers || []) {
            const row = this._curveRow(l);
            if (!row || seen.has(row.key)) continue;
            seen.add(row.key);
            if (this.riggingCurveRowCurved(row)) rows.push(row);
        }
        if (!rows.length) return false;
        const curved = rows.flatMap(r => this._curveAll(r));
        const project = this.project;
        this._curveSeq = (this._curveSeq || 0) + 1;
        const seq = this._curveSeq;
        if (!this._curveLatest) this._curveLatest = new Map();
        const jobs = rows.map(row => {
            const lead = row.layers[0];
            const input = this._curveInput(lead);
            this._curveAll(row).forEach(m => this._curveLatest.set(m.id, seq));
            return { id: lead.id, ids: this._curveAllIds(row), key: JSON.stringify(input), shape: this._curveShape(row), input,
                     name: this._curveMulti(row) ? this._curveWallName(row) : (lead.name || `Screen ${lead.id}`),
                     p: this.riggingCurveRequest(input) };
        });
        const otherIds = [...new Set((others || []).map(l => l.id))];
        // The edit itself is an undo step at once, so an undo pressed while
        // the answer is on its way takes back this edit, not the one
        // before it. The answer, when it lands, joins that same step.
        // An edit made while the one before is still being worked out
        // joins its step: two quick clicks are one undo step.
        const open = this._curveOpenEntry;
        if (open && Array.isArray(this.history) && this.history[this.historyIndex] === open
            && this.historyIndex === this.history.length - 1) {
            this.history.pop();
            this.historyIndex -= 1;
        }
        const before = Array.isArray(this.history) ? this.history[this.historyIndex] : null;
        const commit = [...new Set([...curved, ...(others || [])])];
        // Their bars are checked when the answer lands (app-rigging.js
        // riggingFitCheck): until then they are the bars before the edit.
        if (!this._curveRelaying) this._curveRelaying = new Set();
        curved.forEach(l => this._curveRelaying.add(l.id));
        this.updateLayers(commit, true, action);
        const entry = Array.isArray(this.history) ? this.history[this.historyIndex] : null;
        const own = entry && entry !== before ? entry : null;
        this._curveOpenEntry = own;
        this._curveBusy = (this._curveBusy || 0) + 1;
        this.refreshRiggingCurve();
        const done = Promise.all(jobs.map(j => j.p)).then(outs => {
            this._curveBusy -= 1;
            // This answer is the newest for these screens: their bars are
            // checked again from here (a newer one on its way keeps them).
            const newest = (j) => j.ids.every(id => this._curveLatest.get(id) === seq);
            const settled = jobs.filter(newest).flatMap(j => j.ids);
            settled.forEach(id => this._curveRelaying.delete(id));
            // An undo, a redo or a reload since: this answer belongs to a
            // show that is gone.
            if (this.project !== project) { this.refreshRiggingPanel(); return; }
            const byId = (id) => (this.project.layers || []).find(l => l.id === id);
            const changed = [];
            const stale = new Set();
            const misses = [...(opts.misses || [])];
            jobs.forEach((j, i) => {
                // a newer edit of this screen is on its way (it carries this
                // one's change too), or the screen (or its row) is no longer
                // what was asked about: nothing of this request lands on it
                const live = byId(j.id);
                const row = live ? this._curveRow(live) : null;
                // (its Curve turned off since is one of those)
                if (!newest(j) || !live || !row || this._curveAllIds(row).join(',') !== j.ids.join(',')
                    || this._curveShape(row) !== j.shape
                    || !this._curveRowSettings(row).on || JSON.stringify(this._curveInput(live)) !== j.key) {
                    j.ids.forEach(id => stale.add(id));
                    return;
                }
                if (outs[i].errors.length) misses.push(j.name);
                else this._curveWrite(live, outs[i]);
                try { this._curveLogOut(j.name, action, j.input, outs[i]); } catch (e) { /* the log never stops a curve */ }
                this._curveAll(row).forEach(m => { if (!changed.includes(m)) changed.push(m); });
            });
            const laid = changed.length > 0;
            otherIds.forEach(id => {
                const live = byId(id);
                if (live && !stale.has(id) && !changed.includes(live)) changed.push(live);
            });
            if (laid) {
                // The edit's own step is still the newest: the answer takes
                // its place, edit and answer as one step. A step made since
                // (another edit) leaves this one its own.
                if (own && this.history[this.historyIndex] === own && this.historyIndex === this.history.length - 1) {
                    this.history.pop();
                    this.historyIndex -= 1;
                }
                this.updateLayers(changed, true, action);
            } else if (settled.length && typeof this.riggingFitCheck === 'function') {
                // nothing laid (the Curve could not, said below): the bars
                // the edit left are checked as they stand
                this.riggingFitCheck(settled.map(byId).filter(Boolean));
            }
            if (this._curveOpenEntry === own) this._curveOpenEntry = null;
            this.refreshRiggingPanel(misses.length ? misses : undefined);
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
        this._curveLast = done;
        return true;
    }

    // The rows a Curve edit acts on: the selected screens and the rest of
    // their groups (a group has one Curve setting, set from any member,
    // like its bars), each row once. A row with a locked screen on it is
    // left whole and its locked screens named. A screen with a header and
    // a footer stands as a row of its own.
    _curveTargetRows() {
        const rows = [];
        const seen = new Set();
        const locked = [];
        for (const l of this._riggingWithGroups(this._riggingScreens())) {
            const row = this._curveRow(l) || { key: `both:${l.id}`, kind: 'both', layers: [l], ids: [l.id],
                                               offsets: [0], panels: [Number(l.columns) || 0], width: Number(l.columns) || 0 };
            if (seen.has(row.key)) continue;
            seen.add(row.key);
            const held = this._curveAll(row).filter(m => this._layerLocked(m));
            if (held.length) { held.forEach(m => { if (!locked.includes(m)) locked.push(m); }); continue; }
            rows.push(row);
        }
        if (locked.length) this._showLockedError(locked);
        return rows;
    }

    // A group's stock is one: every screen of `row` takes the lit sizes of
    // the screen the tab shows when that screen is on the row or in its
    // group (as Auto gives a row the sizes the tab shows), else of the
    // row's first screen. True when any changed.
    _curveSyncSizes(row, primary) {
        const lead = row.layers[0];
        const mate = primary && (this._curveAll(row).includes(primary) || (primary.group_id && primary.group_id === lead.group_id));
        const want = this._riggingSizesOf(mate ? primary : lead);
        let moved = false;
        this._curveAll(row).forEach(m => {
            if (JSON.stringify(this._riggingSizesOf(m)) === JSON.stringify(want)) return;
            m.riggingSizes = [...want];
            moved = true;
        });
        return moved;
    }

    setRiggingCurveOn(on) {
        const primary = this._riggingPrimary(this._riggingScreens());
        const rows = this._curveTargetRows();
        const changed = [];
        const refused = [];
        const noLocks = [];
        const misses = [];
        for (const row of rows) {
            const lead = row.layers[0];
            const s = row.kind === 'both' ? this.riggingCurveOf(lead) : this._curveRowSettings(row);
            if (on) {
                const why = this._curveCannot(lead);
                if (why) { refused.push([row, why]); continue; }
                if (this._curveAll(row).every(m => this.riggingCurveOf(m).on)) continue;
                // No positions, no curve: it waits until they are set.
                if (!hasLockPositions(this._curveRowLocks(row))) { noLocks.push(row); continue; }
                const fresh = { ...s, on: true };
                delete fresh.handJoints;
                // a wall laid by hand: its bars are kept for Curve off
                this._curveKeepHand(this._curveAll(row));
                this._curveAll(row).forEach(m => { m.riggingCurve = { ...fresh }; m.riggingCustom = false; });
                this._curveSyncSizes(row, primary);
            } else {
                if (!this._curveAll(row).some(m => this.riggingCurveOf(m).on)) continue;
                this.riggingCurveOff(this._curveAll(row));
                // The Curve's bars give way to the ones the wall had laid by
                // hand before it, or to the ones Auto lays from the row's lit
                // sizes (riggingFitRow, corners and all).
                if (this._curveAll(row).some(m => this._curveKept(m))) {
                    this._curveGiveBackHand(this._curveAll(row));
                } else if (row.kind !== 'both' && !row.layers.some(m => m.riggingCustom === true)) {
                    const plain = this.riggingRow(row.layers[0], row.kind);
                    if (!this._riggingFitRow(plain, this._riggingSizesOf(row.layers[0]))) misses.push(this._riggingRowName(plain));
                }
            }
            this._curveAll(row).forEach(m => { if (!changed.includes(m)) changed.push(m); });
        }
        if (changed.length || refused.length || noLocks.length) {
            sendClientLog('curve_set', {
                on, screens: changed.map(l => l.name),
                ...(refused.length ? { refused: refused.map(([row, why]) => `${this._curveRowWords(row)}: ${why}`) } : {}),
                ...(noLocks.length ? { noLockPositions: noLocks.map(r => this._curveRowWords(r)) } : {}),
                ...(misses.length ? { misses } : {}),
            }, {
                area: 'rigging', level: refused.length || noLocks.length ? 'warn' : 'info',
                msg: `Curve ${on ? 'on' : 'off'}${changed.length ? ` for ${changed.map(l => l.name).slice(0, 6).join(', ')}` : ''}`
                    + (refused.length ? `; refused: ${refused.map(([row, why]) => `${this._curveRowWords(row)}, ${why}`).join('; ')}` : '')
                    + (noLocks.length ? `; no lock positions: ${noLocks.map(r => this._curveRowWords(r)).join(', ')}` : '')
                    + (misses.length ? `; Auto bars cannot cover ${misses.join(', ')}` : ''),
            });
        }
        if (refused.length || noLocks.length) {
            const lines = refused.map(([row, why]) => `${this._curveRowWords(row)} cannot take a Curve: ${why}.`);
            if (noLocks.length) {
                const lone = noLocks.length === 1 && this._curveAll(noLocks[0]).length === 1;
                lines.push(rows.length === 1 && lone ? NO_LOCKS_MESSAGE
                    : `${listWords(noLocks.map(r => this._curveRowWords(r)))}: ${NO_LOCKS_MESSAGE.replace('this screen', lone ? 'it' : 'them')}`);
            }
            this._toast(lines.join(' '), true, 7000);
        }
        if (changed.length) {
            if (!on || !this.riggingCurveRelayLater(changed, 'Curve On', changed)) {
                this.updateLayers(changed, true, on ? 'Curve On' : 'Curve Off');
            }
        }
        this.refreshRiggingPanel(misses.length ? misses : undefined);
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // One field of the form, on every selected screen with its Curve on,
    // laid again. One undo step. A pick on a screen with corners is one
    // side's (`side`, its index left to right).
    setRiggingCurveField(key, raw, side = null) {
        // Every selected screen: a curve that is off keeps its settings for
        // when it is ticked, one that is on is laid again.
        const rows = this._curveTargetRows();
        if (!rows.length) { this.refreshRiggingPanel(); return; }
        const primary = this._riggingPrimary(this._riggingScreens()) || rows[0].layers[0];
        const base = this.riggingCurveFor(primary);
        const patch = {};
        if (key === 'entry') {
            if (raw !== 'percent' && raw !== 'degrees') return;
            patch.entry = raw;
        } else if (key === 'bend') {
            if (raw !== 'concave' && raw !== 'convex') return;
            patch.bend = raw;
        } else if (key === 'goal') {
            if (!['simplest', 'even', 'tightest'].includes(raw)) return;
            patch.goal = raw;
        } else if (key === 'from') {
            const n = typeof raw === 'number' ? raw : (/^\d+(\.\d+)?$/.test(String(raw)) ? Number(raw) : null);
            if (n !== null) patch.from = n;
            else if (['center', 'left', 'right'].includes(raw)) patch.from = raw;
            else return;
        } else if (key === 'pick') {
            if (!base.on) return;
            const whole = this.riggingCurveCached(primary);
            const out = side === null ? whole : (whole && whole.sides && whole.sides[side] ? whole.sides[side].out : null);
            let pick = null;
            if (raw !== 'auto') {
                if (!out || !out.result || !out.result.options.some(o => o.id === raw)) return;
                pick = { id: String(raw), key: out.pickKey };
            }
            if (side === null) {
                patch.pick = pick;
            } else {
                const list = (base.sidePicks || []).slice();
                while (list.length <= side) list.push(null);
                list[side] = pick;
                patch.sidePicks = list;
            }
        } else if (key === 'value') {
            const v = Number(String(raw).replace(/[%°\s]/g, ''));
            const max = base.entry === 'degrees' ? 360 : 100;
            if (!Number.isFinite(v) || v < 0 || v > max) {
                sendClientLog('curve_field_refused', { key, value: String(raw).slice(0, 20), why: `outside 0 to ${max}` },
                    { area: 'rigging', level: 'warn', msg: `Curve ${base.entry === 'degrees' ? 'sweep' : '%'} ${String(raw).slice(0, 20)} refused: type 0 to ${max}` });
                this._toast(base.entry === 'degrees' ? 'Curve, type degrees of sweep from 0 to 360.' : 'Curve, type a % of a full circle from 0 to 100.', true, 5000);
                this.refreshRiggingPanel();
                return;
            }
            patch.value = v;
        } else if (key === 'tolerance') {
            const v = Number(String(raw).replace(/[a-z"\s]/gi, ''));
            if (!Number.isFinite(v) || v < 0) { this.refreshRiggingPanel(); return; }
            patch.toleranceMm = this._curveSystem() === 'metric' ? v : v * 25.4;
        } else {
            return;
        }
        const changed = [];
        for (const row of rows) {
            const s = row.kind === 'both' ? this.riggingCurveOf(row.layers[0]) : this._curveRowSettings(row);
            const next = cleanCurve({ ...s, ...patch });
            // the datum is in the row's panels: a group's spans its screens
            if (typeof next.from === 'number') next.from = snapDatum(next.from, row.width || 1);
            // Switching % and degrees says the same curve the other way:
            // the wall does not change.
            if (patch.entry && patch.entry !== s.entry) {
                next.value = Math.round(convertCurveEntry(s.value,
                    s.entry === 'degrees' ? 'sweep_deg' : 'percent_circle',
                    patch.entry === 'degrees' ? 'sweep_deg' : 'percent_circle') * 1e6) / 1e6;
            }
            const sized = row.kind !== 'both' && this._curveSyncSizes(row, primary);
            if (!sized && this._curveAll(row).every(m => JSON.stringify(next) === JSON.stringify(this.riggingCurveOf(m)))) continue;
            this._curveAll(row).forEach(m => { m.riggingCurve = { ...next }; });
            this._curveAll(row).forEach(m => { if (!changed.includes(m)) changed.push(m); });
        }
        if (changed.length) {
            sendClientLog('curve_field_set', { key, patch, screens: changed.map(l => l.name) }, {
                area: 'rigging',
                msg: `Curve ${key} set to ${JSON.stringify(patch[key] !== undefined ? patch[key] : patch)} on ${changed.map(l => l.name).slice(0, 6).join(', ')}`,
            });
        }
        if (changed.length && !this.riggingCurveRelayLater(changed, 'Curve', changed)) {
            this.updateLayers(changed, true, 'Curve');
        }
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The bars a screen had laid by hand when its Curve went on, held to
    // their shape: { side, bars, starts, corners, seen } (starts in its own
    // panels, corners the ats of its laid corner pieces, seen the ats of
    // every corner it had), or null.
    _curveKept(layer) {
        const k = layer && layer.riggingCustomSaved;
        if (!k || typeof k !== 'object' || !Array.isArray(k.bars)) return null;
        const bars = k.bars.map(Number);
        const starts = Array.isArray(k.starts) && k.starts.length === bars.length ? k.starts.map(Number) : null;
        if (!starts || ![...bars, ...starts].every(n => Number.isInteger(n) && n >= 0)) return null;
        const ats = (list) => (Array.isArray(list) ? list.map(Number).filter(Number.isFinite) : []);
        return { side: k.side === 'footer' ? 'footer' : 'header', bars, starts, corners: ats(k.corners), seen: ats(k.seen) };
    }

    // Curve on over a wall laid by hand (any of its screens): every screen
    // keeps its bars and laid corner pieces for Curve off. A wall on Auto
    // keeps none.
    _curveKeepHand(all) {
        const hand = all.some(m => m.riggingCustom === true);
        all.forEach(m => {
            if (!hand) { if (m.riggingCustomSaved) m.riggingCustomSaved = null; return; }
            const side = this.riggingSideOf(m) === 'footer' ? 'footer' : 'header';
            const placed = this.riggingPlaced(m, side);
            m.riggingCustomSaved = {
                side, bars: placed.map(b => b.size), starts: placed.map(b => b.start),
                corners: s3dCleanCorners(m.riggingCorners).filter(c => c.bar).map(c => c.at),
                seen: s3dCleanCorners(m.riggingCorners).map(c => c.at),
            };
        });
    }

    // Curve off over a wall that was laid by hand: each screen's bars as
    // they were kept, on its side, its corner pieces as they were (a corner
    // added since takes its piece), laid by hand again; then forgotten.
    _curveGiveBackHand(all) {
        all.forEach(m => {
            const k = this._curveKept(m);
            m.riggingCustomSaved = null;
            if (!k) return;
            const side = this.riggingSideOf(m) === 'footer' ? 'footer' : 'header';
            this._riggingWrite(m, side, k.bars.map((size, i) => ({ start: k.starts[i], size })));
            m.riggingCustom = true;
            // a corner it had keeps its piece as it was; one added since
            // lays its piece
            const ats = this.riggingCornerSpots(m).map(sp => sp.at);
            const off = ats.filter(a => k.seen.includes(a) && !k.corners.includes(a));
            this._riggingSetCornerBars(m, ats.filter(a => !off.includes(a)), true);
            this._riggingSetCornerBars(m, off, false);
        });
    }

    // A Custom gesture on a curved screen (owner, 2026-11-18): refused, said
    // in one line, only on a stacked wall's screen off its bar row (its
    // bars run along the wall's top or bottom row). True when refused.
    riggingCurveRefusesHand(layers) {
        for (const l of layers || []) {
            if (!this.riggingCurveOn(l)) continue;
            const row = this._curveRow(l);
            if (row && row.below && row.below.some(b => b.layer === l)) {
                const top = row.kind === 'footer' ? 'bottom' : 'top';
                this._toast(`${l.name || `Screen ${l.id}`} is curved with ${this._curveWallName(row)}, whose ${row.kind} bars run along its ${top} row. Lay them there.`, true, 6000);
                return true;
            }
        }
        return false;
    }

    // Bars a Custom gesture leaves on a curved row (`placed`, in the row's
    // panels): refused, said in one line, when one runs across a joint set
    // by hand to bend. True when refused.
    riggingCurveHandCovers(layer, placed) {
        if (!this.riggingCurveOn(layer)) return false;
        const row = this._curveRow(layer);
        if (!row) return false;
        const hand = this._curveRowSettings(row).handJoints || {};
        for (const [k, a] of Object.entries(hand)) {
            const j = Number(k);
            if (!a) continue;
            const over = (placed || []).find(b => b.start <= j && j + 1 < b.start + b.size);
            if (over) {
                this._toast(`That bar would run across the joint after panel ${j + 1}, set by hand to ${formatAngle(Math.abs(a))}, and a bar holds its joint straight. Set that joint flat or to Auto first.`, true, 6000);
                return true;
            }
        }
        return false;
    }

    // A Custom gesture on a curved row, done (app-rigging.js): the row is
    // laid by hand now, and the Curve fits its angles to the bars, one
    // undo step with the gesture. False when the row is not curved.
    riggingCurveHandLaid(layers, action) {
        const curved = (layers || []).filter(l => this.riggingCurveOn(l));
        if (!curved.length) return false;
        (layers || []).forEach(m => { m.riggingCustom = true; });
        const all = [...new Set([...(layers || []), ...curved.flatMap(l => { const row = this._curveRow(l); return row ? this._curveAll(row) : [l]; })])];
        if (!this.riggingCurveRelayLater(curved, action, all)) this.updateLayers(all, true, action);
        return true;
    }

    // The angles a joint can be set to by hand on `row`: flat and the
    // lock positions the row's panels share for the way it bends, signed.
    _curveJointChoices(row) {
        const s = this._curveRowSettings(row);
        const list = this._curveRowLocks(row) || [];
        const way = list.filter(a => (s.bend === 'convex' ? a < 0 : a > 0));
        return [0, ...way.sort((a, b) => Math.abs(a) - Math.abs(b))];
    }

    // Why joint `j` (0-based, in the row's joints) cannot be set by hand to
    // bend `a`, or '' when it can: a bar runs across it, or a corner's seam.
    _curveJointRefusal(row, j, a) {
        const bars = [...(row.placed || []), ...(row.pieces || [])];
        const corner = (row.spots || []).find(sp => sp.start <= j && j + 1 < sp.start + sp.size);
        if (corner) return `The joint after panel ${j + 1} is a corner's, and a corner takes no curve angle.`;
        if (!a) return '';
        if (!this._curveJointChoices(row).some(x => Math.abs(x - a) < 1e-6)) {
            return `This panel does not lock at ${formatLock(a)} for a ${this._curveRowSettings(row).bend} curve. Pick one of its lock positions.`;
        }
        const over = bars.find(b => b.start <= j && j + 1 < b.start + b.size);
        if (over) {
            return `The bar over panels ${over.start + 1} to ${over.start + over.size} runs across the joint after panel ${j + 1} and holds it straight. Move the bar with Custom to bend it there.`;
        }
        return '';
    }

    // Joint `j` (0-based, across the row) of the screen the tab shows set
    // by hand to `angle` (signed degrees, 0 flat), or back to the Curve's
    // own pick (null). The row is laid by hand from then on: its bars stay
    // as they are and the Curve fits the other joints. One undo step.
    setRiggingCurveJoint(j, angle) {
        const primary = this._riggingPrimary(this._riggingScreens());
        const row = primary ? this._curveRow(primary) : null;
        if (!row || !this.riggingCurveRowCurved(row)) return false;
        const all = this._curveAll(row);
        const locked = all.filter(m => this._layerLocked(m));
        if (locked.length) { this._showLockedError(locked); return false; }
        const width = row.width || Number(primary.columns) || 0;
        if (!Number.isInteger(j) || j < 0 || j > width - 2) return false;
        const s = this._curveRowSettings(row);
        const hand = { ...(s.handJoints || {}) };
        if (angle === null) {
            if (!(String(j) in hand)) return false;
            delete hand[String(j)];
        } else {
            const a = Number(angle);
            if (!Number.isFinite(a)) return false;
            const why = this._curveJointRefusal(row, j, a);
            if (why) {
                sendClientLog('curve_joint_refused', { joint: j + 1, angle: a, why },
                    { area: 'rigging', level: 'warn', msg: `Curve joint after panel ${j + 1} to ${a} deg refused: ${why}` });
                this._toast(why, true, 6000);
                return false;
            }
            if (hand[String(j)] === a && row.layers.every(m => m.riggingCustom === true)) return false;
            hand[String(j)] = a;
        }
        const next = cleanCurve({ ...s, handJoints: hand });
        all.forEach(m => { m.riggingCurve = { ...next }; });
        row.layers.forEach(m => { m.riggingCustom = true; });
        const action = angle === null ? 'Curve Joint Auto' : 'Curve Joint';
        sendClientLog('curve_joint_set', { joint: j + 1, angle, screens: all.map(l => l.name) }, {
            area: 'rigging', msg: `Curve joint after panel ${j + 1} ${angle === null ? 'back to Auto' : `set by hand to ${angle} deg`}`,
        });
        if (!this.riggingCurveRelayLater(all, action, all)) this.updateLayers(all, true, action);
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
        return true;
    }

    // The joint picked on the strip, for the screen the tab shows: its
    // index, or null.
    _curvePickedJoint(primary, row) {
        const p = this._curveJointPick;
        if (!p || !primary || !row) return null;
        const width = row.width || Number(primary.columns) || 0;
        return p.key === row.key && p.j <= width - 2 ? p.j : null;
    }

    // The strip's joint pick: the joint's angles to pick from, the one it
    // has marked, Auto when set by hand.
    _curveDrawJointPick(host, primary, row, out) {
        if (!host) return;
        const j = this._curvePickedJoint(primary, row);
        if (j === null || !out || !out.joints || j >= out.joints.length) {
            host.style.display = 'none';
            host.innerHTML = '';
            host.dataset.sig = '';
            return;
        }
        const hand = this._curveRowSettings(row).handJoints || {};
        const set = String(j) in hand;
        const now = Number(out.joints[j]) || 0;
        const choices = this._curveJointChoices(row);
        const sig = JSON.stringify([j, set, now, choices]);
        host.style.display = '';
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        const words = document.createElement('div');
        words.style.cssText = 'color: #aaa; font-size: 11px; margin-bottom: 3px;';
        words.textContent = `Joint after panel ${j + 1}: ${set ? 'set by hand' : 'set by the Curve'}.`;
        host.appendChild(words);
        const line = document.createElement('div');
        line.style.cssText = 'display: flex; flex-wrap: wrap; gap: 4px;';
        const button = (value, text, on, tip) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'btn btn-secondary rigging-curve-btn' + (on ? ' active' : '');
            b.dataset.jointAngle = value;
            b.textContent = text;
            b.setAttribute('data-tooltip', tip);
            b.style.setProperty('padding', '2px 6px', 'important');
            b.style.setProperty('font-size', '11px', 'important');
            line.appendChild(b);
        };
        button('auto', 'Auto', !set, 'Let the Curve set this joint.');
        choices.forEach(a => button(String(a), a ? formatAngle(Math.abs(a)) : 'Flat', set && Math.abs(now - a) < 1e-6,
            a ? `Set this joint to ${formatAngle(Math.abs(a))} by hand.` : 'Set this joint flat by hand.'));
        host.appendChild(line);
    }

    // ---- the panel --------------------------------------------------------

    refreshRiggingCurve() {
        const block = document.getElementById('rigging-curve');
        const box = document.getElementById('rigging-curve-on');
        if (!block || !box) return;
        const screens = this._riggingScreens();
        const primary = this._riggingPrimary(screens);
        block.style.display = primary ? '' : 'none';
        if (!primary) return;
        // A grouped row shows its one Curve (the row's), the lock
        // positions every panel of it has, and why it cannot curve when it
        // cannot.
        const row = this._curveRow(primary);
        const multi = this._curveMulti(row);
        const s = this.riggingCurveFor(primary);
        const cannot = this._curveCannot(primary);
        const onCount = screens.filter(l => this.riggingCurveOn(l)).length;
        box.checked = s.on;
        box.indeterminate = onCount > 0 && onCount < screens.length;
        // The panel's lock positions: none, and the Curve waits for them.
        // A library model reads the library's list once it has loaded.
        if (primary.panelModelId && !this._panelCatalog && typeof this._ensurePanelCatalogData === 'function'
            && !this._curveCatalogAsked) {
            this._curveCatalogAsked = true;
            this._ensurePanelCatalogData().then(() => this.refreshRiggingCurve(), () => {});
        }
        const locks = this._curveLocksShown(primary, row);
        const hasLocks = hasLockPositions(locks.list);
        box.disabled = !s.on && onCount === 0 && !hasLocks;
        this._curveDrawLocks(primary, locks);
        // The settings always show and always save, Curve on or off: set
        // the curve up, then tick Curve to lay it.
        const fields = document.getElementById('rigging-curve-fields');
        if (fields) fields.style.display = '';
        const note = document.getElementById('rigging-curve-note');
        // "Group 1's 3 screens": the wall a grouped row's curve runs across
        const across = multi ? `${this._curveWallName(row)}'s ${this._curveAll(row).length} screens` : '';
        if (note) {
            note.style.display = '';
            note.textContent = cannot
                ? `${this._curveWho(primary)} cannot take a Curve: ${cannot}.`
                : !s.on
                    ? (hasLocks ? (multi ? `Tick Curve to lay these bars and angles across ${across} as one wall.` : 'Tick Curve to lay these bars and angles on the screen.')
                        : 'Set this panel\'s lock positions below, then tick Curve.')
                    : !hasLocks
                        ? 'This screen keeps the angles it was laid at until its panel\'s lock positions are set.'
                        : this._riggingToolNow() === 'custom'
                            ? 'Custom: lay bars by hand and the Curve sets the angles where they meet. Click a joint on the build sheet to set it yourself.'
                            : multi
                                ? `The Curve lays the bars across ${across} from the lit sizes, as one wall. Auto lays it again.`
                                : 'The Curve lays this screen\'s bars from the lit sizes. Auto lays it again.';
        }
        // A saved curve laid at angles its panel does not lock at opens as
        // it was, flagged, until Auto or Use this lays it from the list.
        const offList = s.on && hasLocks && !cannot ? this._curveOffList(primary, locks.list) : [];
        if (note && offList.length) {
            note.textContent = `This screen is laid at ${listWords(offList.map(a => formatLock(a)))}, which this panel does not lock at. Press Auto to lay it again from its lock positions.`;
        }
        if (note) note.dataset.offList = offList.length ? '1' : '';
        const working = document.getElementById('rigging-curve-working');

        const lit = (sel, value) => document.querySelectorAll(sel).forEach(btn => {
            btn.classList.toggle('active', btn.dataset.value === value);
        });
        lit('#rigging-curve-entry .rigging-curve-btn', s.entry);
        lit('#rigging-curve-bend .rigging-curve-btn', s.bend);
        lit('#rigging-curve-goal .rigging-curve-btn', s.goal);
        lit('#rigging-curve-from .rigging-curve-btn', typeof s.from === 'string' ? s.from : '');
        const fromLabel = document.getElementById('rigging-curve-from-label');
        if (fromLabel) {
            fromLabel.textContent = typeof s.from === 'number'
                ? `From ${datumLabel(snapDatum(s.from, (multi ? row.width : Number(primary.columns)) || 1))}. Drag the red dot on the plan to move it.`
                : 'Or drag the red dot on the plan onto any panel or joint.';
        }
        const system = this._curveSystem();
        const set = (id, value) => {
            const el = document.getElementById(id);
            if (el && document.activeElement !== el && el.value !== value) el.value = value;
        };
        set('rigging-curve-value', String(Math.round(s.value * 1000) / 1000));
        set('rigging-curve-tol', toleranceField(s.toleranceMm, system));
        const tolUnit = document.getElementById('rigging-curve-tol-unit');
        if (tolUnit) tolUnit.textContent = system === 'metric' ? 'mm' : 'in';
        const valueUnit = document.getElementById('rigging-curve-value-unit');
        if (valueUnit) valueUnit.textContent = s.entry === 'degrees' ? 'degrees of sweep' : '% of a circle';
        if (!s.on || cannot) {
            ['rigging-curve-working', 'rigging-curve-errors', 'rigging-curve-result'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.style.display = 'none';
            });
            return;
        }

        // The answer for the screen as it stands: kept, or asked for in the
        // background and drawn when it comes.
        let out = this.riggingCurveCached(primary);
        if (!out) {
            const input = this._curveInput(primary);
            this.riggingCurveRequest(input).then(() => this.refreshRiggingCurve());
        }
        if (working) working.style.display = (!out || this.riggingCurveBusy()) ? '' : 'none';
        const errorsEl = document.getElementById('rigging-curve-errors');
        const result = document.getElementById('rigging-curve-result');
        if (!out) {
            if (errorsEl) errorsEl.style.display = 'none';
            return;
        }
        if (errorsEl) {
            // (no lock positions is said once, by the lock positions row)
            const said = out.errors.filter(e => e !== NO_LOCKS_MESSAGE);
            errorsEl.style.display = said.length ? '' : 'none';
            errorsEl.textContent = said.join('\n');
        }
        if (result) result.style.display = out.errors.length ? 'none' : '';
        if (out.errors.length) return;
        // A row laid by hand: say so, and that Auto hands it back.
        if (note && out.hand && !offList.length) {
            note.textContent = this._riggingToolNow() === 'custom'
                ? 'Laid by hand (blue): lay bars with Custom and the Curve sets the angles where they meet. Click a joint on the build sheet to set it yourself. Auto hands it all back to the Curve.'
                : 'Laid by hand (blue): the Curve sets the angles where the bars meet. Click a joint on the build sheet to set it yourself. Auto hands it all back to the Curve.';
        }
        // A redo can bring back an edit whose answer never landed: say so
        // rather than show a curve the screen does not carry.
        if (note && !offList.length && !this.riggingCurveBusy() && !this._curveLaidMatches(primary, out)) {
            note.textContent = 'These bars and angles are not this curve\'s yet. Press Auto to lay it.';
        }
        // The seams a corner takes over (app-corners.js): no curve angle.
        // Across a group, the row's joints: a seam corner's piece starts on
        // the panel left of its seam.
        const cornerSeams = multi
            ? new Map((row.spots || []).filter(sp => sp.size === 2).map(sp => [sp.start, sp]))
            : s3dCornerSeams(primary, Number(primary.columns) || 0);
        const picked = this._curvePickedJoint(primary, row);
        this._curveDrawSheet(document.getElementById('rigging-curve-sheet'), out, cornerSeams, s.handJoints || {}, picked);
        this._curveDrawJointPick(document.getElementById('rigging-curve-joint'), primary, row, out);
        if (out.sides) this._curveDrawCornerPlan(document.getElementById('rigging-curve-plan'), this._curveWallOf(primary, row), out);
        else this._curveDrawPlan(document.getElementById('rigging-curve-plan'), out);
        // One group per side on a screen with corners, each named; the
        // screen itself without.
        const groups = out.sides
            ? out.sides.map((sd, i) => ({ side: i, name: cap(sd.name), panels: sd.panels, r: sd.out.result }))
            : [{ side: null, name: '', panels: 0, r: out.result }];
        const named = (g, text) => (g.name ? `${g.name}: ${text}` : text);
        const head = document.getElementById('rigging-curve-head');
        // (a side that is only its corner bar's arm has no joint to bend)
        if (head) head.textContent = groups.map(g => named(g, g.r ? this._curveHeadline(g.r) : 'only the corner bar, flat')).join('\n');
        const len = (m) => formatLength(m, system);
        const rows = [];
        groups.forEach(g => {
            if (g.name) rows.push([`${g.name}, ${g.panels} panel${g.panels === 1 ? '' : 's'}`, g.r ? '' : 'flat', true]);
            if (!g.r) return;
            const a = g.r.achieved;
            rows.push(['Sweep', `${formatAngle(a.sweep_deg, 1)}, ${a.percent_circle.toFixed(1)}% of a circle`]);
            rows.push(['Radius', Number.isFinite(a.radius_face_m) ? `${len(a.radius_face_m)} to the face` : 'straight']);
            rows.push(['Width', len(a.chord_m)]);
            rows.push(['Depth', len(a.depth_m)]);
            rows.push(['Off the drawing', `${formatSmall(g.r.max_arc_deviation_m, system)} at worst`]);
        });
        const read = document.getElementById('rigging-curve-readouts');
        if (read) {
            const sig = JSON.stringify(rows);
            if (read.dataset.sig !== sig) {
                read.dataset.sig = sig;
                read.innerHTML = '';
                rows.forEach(([k, v, title]) => {
                    const row = document.createElement('div');
                    row.style.cssText = `display: flex; justify-content: space-between; gap: 8px;${title ? ' margin-top: 4px;' : ''}`;
                    const kEl = document.createElement('span');
                    kEl.style.cssText = title ? 'color: #fff; font-weight: 600;' : 'color: #aaa;';
                    kEl.textContent = k;
                    const vEl = document.createElement('span');
                    vEl.textContent = v;
                    vEl.style.textAlign = 'right';
                    row.append(kEl, vEl);
                    read.appendChild(row);
                });
            }
        }
        const reason = document.getElementById('rigging-curve-reason');
        if (reason) reason.textContent = groups.filter(g => g.r).map(g => named(g, g.r.choice_reason)).join('\n');
        const warn = document.getElementById('rigging-curve-warnings');
        if (warn) {
            // The bars warning restates the build sheet strip above it.
            const shown = out.warnings.filter(w => !/^([A-Z][a-z]* side: |Side \d+: )?Bars:/.test(w));
            warn.style.display = shown.length ? '' : 'none';
            warn.textContent = shown.join('\n\n');
        }
        this._curveDrawWays(document.getElementById('rigging-curve-ways'), groups.filter(g => g.r), system);
    }

    // "7.5° at 9 joints, 6 flat"
    _curveHeadline(r) {
        if (!r.angle_usage.length) return 'Every joint flat: a straight wall';
        const parts = r.angle_usage.map(u => `${formatAngle(u.angle_deg)} at ${u.count} joint${u.count === 1 ? '' : 's'}`);
        if (r.flat_joints) parts.push(`${r.flat_joints} flat`);
        return parts.join(', ');
    }

    // Ways to build it: every candidate build, ranked as the calculator
    // ranks them (the closest and the closest even always among them),
    // the one in use marked, every other with Use this. `groups` are
    // { side, name, r }: the screen alone (side null, no name), or each
    // side of a screen with corners, its list headed with its name.
    _curveDrawWays(host, groups, system) {
        if (!host) return;
        const lists = groups.map(g => {
            const r = g.r;
            return {
                side: g.side, name: g.name,
                manual: r.config.pattern_choice !== 'auto' && r.chosen_option_id !== r.recommended_option_id,
                rows: r.options.map(o => ({
                    id: o.id,
                    angles: o.used_angles_deg.length ? o.used_angles_deg.map(a => formatAngle(a)).join(' + ') : 'All flat',
                    even: o.even && o.used_angles_deg.length > 0,
                    joints: `${o.curved_joints} bent, ${o.flat_joints} flat`,
                    builds: `${o.percent_circle.toFixed(1)}%`,
                    off: `${formatSmall(o.deviation_m, system)} off${o.within_tolerance ? '' : ', over'}`,
                    over: !o.within_tolerance,
                    chosen: o.id === r.chosen_option_id,
                    app: o.id === r.recommended_option_id,
                })),
            };
        });
        const sig = JSON.stringify(lists);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        lists.forEach(list => {
            const box = document.createElement('div');
            if (list.side !== null) box.dataset.side = String(list.side);
            const title = document.createElement('div');
            title.style.cssText = 'font-weight: 600; color: #fff; margin: 6px 0 2px;';
            title.textContent = list.name ? `Ways to build it, ${list.name.toLowerCase()}` : 'Ways to build it';
            box.appendChild(title);
            if (list.manual) {
                const line = document.createElement('div');
                line.style.cssText = 'display: flex; align-items: center; gap: 6px; color: #aaa; font-size: 11px; margin-bottom: 2px;';
                const words = document.createElement('span');
                words.textContent = 'You picked this one by hand.';
                const back = document.createElement('button');
                back.type = 'button';
                back.className = 'btn btn-secondary';
                back.dataset.pick = 'auto';
                back.textContent = 'Let the app pick';
                back.style.setProperty('padding', '1px 6px', 'important');
                back.style.setProperty('font-size', '11px', 'important');
                line.append(words, back);
                box.appendChild(line);
            }
            list.rows.forEach(row => {
                const el = document.createElement('div');
                el.className = 'rigging-curve-way';
                el.dataset.way = row.id;
                el.style.cssText = `display: flex; align-items: center; gap: 6px; padding: 3px 0; border-top: 1px solid #2a2a2a; font-size: 11px; color: ${row.chosen ? '#fff' : '#bbb'};`;
                const text = document.createElement('div');
                text.style.cssText = 'flex: 1; min-width: 0;';
                const top = document.createElement('div');
                top.style.cssText = 'font-weight: 600;';
                top.textContent = row.angles + (row.even ? ', even' : '') + (row.chosen ? ', in use' : (row.app ? ', the app\'s pick' : ''));
                const bottom = document.createElement('div');
                bottom.style.color = row.over ? '#f5a623' : '#999';
                bottom.textContent = `${row.joints}, ${row.builds}, ${row.off}`;
                text.append(top, bottom);
                el.appendChild(text);
                if (!row.chosen) {
                    const use = document.createElement('button');
                    use.type = 'button';
                    use.className = 'btn btn-secondary';
                    use.dataset.pick = row.id;
                    use.textContent = 'Use this';
                    use.style.setProperty('padding', '2px 6px', 'important');
                    use.style.setProperty('font-size', '11px', 'important');
                    use.style.flex = 'none';
                    const what = row.angles === 'All flat' ? 'every joint flat' : row.angles;
                    use.setAttribute('data-tooltip', list.name
                        ? `Use this, build the ${list.name.toLowerCase()} with ${what}. It holds until the curve, the bars or the corners change.`
                        : `Use this, build the wall with ${what}. It holds until the curve, the bars or the wall change.`);
                    el.appendChild(use);
                }
                box.appendChild(el);
            });
            host.appendChild(box);
        });
    }

    // The build sheet strip: the bars left to right, sized to their panels
    // and marked with their size, a tag with the angle on every join that
    // bends, and the datum marked under the strip.
    _curveDrawSheet(host, out, cornerSeams = new Map(), handJoints = {}, picked = null) {
        if (!host) return;
        const bars = out.bars;
        const joints = out.joints;
        const panels = joints.length + 1;
        const datum = out.result ? out.result.datum_at : out.datum_at;
        const room = Math.max(120, (host.clientWidth || 200) - 2);
        // where each bar starts: a row laid by hand may have gaps
        const starts = Array.isArray(out.placed) && out.placed.length === bars.length ? out.placed.map(b => b.start)
            : Array.isArray(out.starts) && out.starts.length === bars.length ? out.starts
                : bars.map((n, i) => bars.slice(0, i).reduce((t, k) => t + k, 0));
        const hand = !!out.hand;
        const sig = JSON.stringify([bars, starts, joints, datum, room, [...cornerSeams.keys()], (out.placed || []).map(b => !!b.corner),
                                    hand, handJoints, picked]);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        // The strip fits the panel; past 14 px a panel it scrolls instead.
        const slots = Math.max(panels, ...bars.map((n, i) => starts[i] + n));
        const W = Math.max(room, Math.round(14 * slots));
        const H = 52;
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('width', String(W));
        svg.setAttribute('height', String(H));
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.style.display = 'block';
        const px = W / slots;
        const add = (tag, attrs, text) => {
            const el = document.createElementNS(NS, tag);
            Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, String(v)));
            if (text != null) el.textContent = text;
            svg.appendChild(el);
            return el;
        };
        const barTop = 22, barH = 16;
        const HAND = '#4fc3f7';
        bars.forEach((n, i) => {
            const x = starts[i] * px;
            // a corner bar: "Corner" where it fits, its size where not; a
            // bar laid by hand in blue
            const corner = !!(Array.isArray(out.placed) && out.placed[i] && out.placed[i].corner);
            add('rect', { x: x + 0.5, y: barTop, width: Math.max(1, n * px - 1), height: barH, fill: '#2a2a2a',
                          stroke: corner ? '#f5a623' : (hand ? HAND : '#888'), 'stroke-width': 1, 'data-bar': i,
                          ...(corner ? { 'data-corner-bar': i } : {}), ...(hand && !corner ? { 'data-hand-bar': i } : {}) });
            add('text', { x: x + n * px / 2, y: barTop + 12, 'text-anchor': 'middle', 'font-size': corner ? 9 : 10, fill: corner ? '#f5a623' : '#ddd' },
                corner && n * px >= 34 ? 'Corner' : String(n));
        });
        // The tags: the angle at each join that bends, over its seam, on a
        // second line where it would run into the one before.
        const ends = [-Infinity, -Infinity];
        joints.forEach((a, j) => {
            // A corner's seam: "Corner", no curve angle on it. A joint set
            // by hand: its angle in blue, flat too.
            const corner = cornerSeams.has(j);
            const byHand = !corner && String(j) in handJoints;
            const x = (j + 1) * px;
            if (picked === j) add('rect', { x: x - 4, y: barTop - 4, width: 8, height: barH + 8, fill: 'none', stroke: HAND, 'stroke-width': 1, 'data-picked-joint': j });
            if (!a && !corner && !byHand) return;
            const text = corner ? 'Corner' : formatAngle(Math.abs(a));
            const half = text.length * 2.7 + 1;
            const line = x - half > ends[0] ? 0 : (x - half > ends[1] ? 1 : 0);
            ends[line] = x + half;
            add('line', { x1: x, y1: line ? 11 : barTop - 3, x2: x, y2: barTop + barH, stroke: byHand ? HAND : '#e22330', 'stroke-width': 1.5 });
            add('text', { x, y: line ? 19 : 9, 'text-anchor': 'middle', 'font-size': 9, fill: corner ? '#f5a623' : (byHand ? HAND : '#f0f0f0'),
                [corner ? 'data-corner-seam' : 'data-angle']: j, ...(byHand ? { 'data-hand-angle': j } : {}) }, text);
        });
        // Every joint but a corner's is a click target: it opens the joint's
        // angles below the strip.
        joints.forEach((a, j) => {
            if (cornerSeams.has(j)) return;
            const x = (j + 1) * px;
            const hit = add('rect', { x: x - Math.max(3, px / 2), y: 0, width: Math.max(6, px), height: barTop + barH, fill: 'transparent',
                                      'data-joint': j, style: 'cursor: pointer;' });
            const tip = document.createElementNS(NS, 'title');
            tip.textContent = `Joint after panel ${j + 1}: click to set its angle by hand`;
            hit.appendChild(tip);
        });
        // The datum: where the crew sets out from (0.5 is the left end).
        const dx = (datum - 0.5) * px;
        add('path', { d: `M ${dx} ${barTop + barH + 2} l -5 7 l 10 0 z`, fill: '#e22330', 'data-datum': datum });
        host.appendChild(svg);
    }

    // The wall from above, drawn level, the drawn arc dashed: audience at
    // the bottom. The red mark is the datum, dragged onto any panel middle
    // or joint (_wireCurvePlanDrag).
    _curveDrawPlan(host, out) {
        if (!host) return;
        const r = out.result;
        const face = [];
        r.placements.forEach((p, i) => { if (i === 0) face.push(p.face[0]); face.push(p.face[1]); });
        const arc = r.target_vertices;
        const sig = JSON.stringify([face, r.datum_at, host.clientWidth]);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const p of face.concat(arc)) {
            if (p.x < x0) x0 = p.x;
            if (p.x > x1) x1 = p.x;
            if (p.y < y0) y0 = p.y;
            if (p.y > y1) y1 = p.y;
        }
        const W = Math.max(120, (host.clientWidth || 200) - 2), pad = 8;
        const span = Math.max(1e-6, x1 - x0);
        const k = (W - 2 * pad) / span;
        const H = Math.max(24, Math.min(90, Math.round((y1 - y0) * k + 2 * pad)));
        const kk = Math.min(k, (H - 2 * pad) / Math.max(1e-6, y1 - y0));
        const ox = (W - span * kk) / 2 - x0 * kk;
        const oy = (H - (y1 - y0) * kk) / 2 - y0 * kk;
        const to = (p) => ({ x: p.x * kk + ox, y: p.y * kk + oy });
        const pts = (list) => list.map(p => { const q = to(p); return `${q.x.toFixed(1)},${q.y.toFixed(1)}`; }).join(' ');
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('width', String(W));
        svg.setAttribute('height', String(H));
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.style.display = 'block';
        const line = (list, attrs) => {
            const el = document.createElementNS(NS, 'polyline');
            el.setAttribute('points', pts(list));
            el.setAttribute('fill', 'none');
            Object.entries(attrs).forEach(([a, v]) => el.setAttribute(a, String(v)));
            svg.appendChild(el);
        };
        line(arc, { stroke: '#888', 'stroke-width': 1, 'stroke-dasharray': '3 3' });
        line(face, { stroke: '#e22330', 'stroke-width': 2 });
        // Every spot a crew can set out from: each joint (half steps, the
        // ends at 0.5 and n + 0.5) and each panel's middle.
        const spots = [];
        face.forEach((p, k) => spots.push({ at: k + 0.5, ...to(p) }));
        for (let i = 1; i < face.length; i++) {
            spots.push({ at: i, ...to({ x: (face[i - 1].x + face[i].x) / 2, y: (face[i - 1].y + face[i].y) / 2 }) });
        }
        const here = spots.find(s => s.at === r.datum_at) || spots[0];
        const mark = document.createElementNS(NS, 'circle');
        mark.setAttribute('cx', here.x.toFixed(1));
        mark.setAttribute('cy', here.y.toFixed(1));
        mark.setAttribute('r', '5');
        mark.setAttribute('fill', '#e22330');
        mark.setAttribute('stroke', '#fff');
        mark.setAttribute('stroke-width', '1.5');
        mark.setAttribute('data-datum', String(r.datum_at));
        mark.style.cursor = 'grab';
        svg.appendChild(mark);
        host._curvePlan = { spots, mark, svg, panels: face.length - 1, at: r.datum_at };
        host.appendChild(svg);
    }

    // A screen with corners from above as the Curve lays it, audience at
    // the bottom: each side bent by its own curve right up to its fold
    // (the corner bars' arms with it), each corner folding 90 degrees, and
    // each side's drawn arc dashed. The red mark is the datum, dragged as
    // on a plain wall.
    _curveDrawCornerPlan(host, wall, out) {
        if (!host) return;
        const n = out.joints.length + 1;
        const w = wall.w;
        const spots = wall.spots;
        const turn = (sp) => sp.turn;
        // Walk the wall left to right: concave turns left, as the
        // calculator walks it (curve-math.js buildCurve).
        let x = 0, y = 0, h = 0;
        const face = [{ x, y }];
        const edge = [{ x, y }];
        const mids = [];
        const go = (len) => { x += len * Math.cos(h); y += len * Math.sin(h); face.push({ x, y }); };
        for (let p = 0; p < n; p++) {
            const fold = spots.find(sp => sp.size === 1 && sp.start === p);
            const from = { x, y };
            if (fold) {
                go(w / 2);
                mids.push({ x, y });
                h += turn(fold);
                go(w / 2);
            } else {
                go(w);
                mids.push({ x: (from.x + x) / 2, y: (from.y + y) / 2 });
            }
            edge.push({ x, y });
            if (p < n - 1) {
                const seam = spots.find(sp => sp.size === 2 && sp.start === p);
                h += seam ? turn(seam) : (out.joints[p] || 0) * Math.PI / 180;
            }
        }
        // Each side's drawn arc, carried onto its panels: from one fold (a
        // seam, or the middle of a folded panel) or end to the next.
        const pointAt = (x) => (Number.isInteger(x) ? edge[x] : mids[Math.floor(x)]);
        const arcs = out.sides.filter(sd => sd.out.result).map(sd => {
            const r = sd.out.result;
            const own = [];
            r.placements.forEach((pl, i) => { if (i === 0) own.push(pl.face[0]); own.push(pl.face[1]); });
            const f0 = own[0], f1 = own[own.length - 1];
            const a = pointAt(sd.start), b = pointAt(sd.start + sd.panels);
            const spin = Math.atan2(b.y - a.y, b.x - a.x) - Math.atan2(f1.y - f0.y, f1.x - f0.x);
            const c = Math.cos(spin), s = Math.sin(spin);
            return r.target_vertices.map(q => ({ x: a.x + (q.x - f0.x) * c - (q.y - f0.y) * s, y: a.y + (q.x - f0.x) * s + (q.y - f0.y) * c }));
        });
        const datum = out.datum_at;
        const sig = JSON.stringify([face.map(q => [Math.round(q.x * 1000), Math.round(q.y * 1000)]), datum, host.clientWidth, arcs.length]);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const q of face.concat(...arcs)) {
            x0 = Math.min(x0, q.x); x1 = Math.max(x1, q.x);
            y0 = Math.min(y0, q.y); y1 = Math.max(y1, q.y);
        }
        const W = Math.max(120, (host.clientWidth || 200) - 2), pad = 8;
        const span = Math.max(1e-6, x1 - x0, y1 - y0);
        const H = Math.max(28, Math.min(110, Math.round((y1 - y0) / span * (W - 2 * pad) + 2 * pad)));
        const k = Math.min((W - 2 * pad) / Math.max(1e-6, x1 - x0), (H - 2 * pad) / Math.max(1e-6, y1 - y0));
        const ox = (W - (x1 - x0) * k) / 2 - x0 * k;
        const oy = (H - (y1 - y0) * k) / 2 - y0 * k;
        const to = (q) => ({ x: q.x * k + ox, y: q.y * k + oy });
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('width', String(W));
        svg.setAttribute('height', String(H));
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.style.display = 'block';
        const line = (list, attrs) => {
            const el = document.createElementNS(NS, 'polyline');
            el.setAttribute('points', list.map(q => { const t = to(q); return `${t.x.toFixed(1)},${t.y.toFixed(1)}`; }).join(' '));
            el.setAttribute('fill', 'none');
            Object.entries(attrs).forEach(([a, v]) => el.setAttribute(a, String(v)));
            svg.appendChild(el);
        };
        arcs.forEach(arc => line(arc, { stroke: '#888', 'stroke-width': 1, 'stroke-dasharray': '3 3' }));
        line(face, { stroke: '#e22330', 'stroke-width': 2 });
        // Every spot a crew can set out from: each joint and panel middle.
        const marks = [];
        edge.forEach((q, i) => marks.push({ at: i + 0.5, ...to(q) }));
        mids.forEach((q, i) => marks.push({ at: i + 1, ...to(q) }));
        const here = marks.find(m => m.at === datum) || marks[0];
        const mark = document.createElementNS(NS, 'circle');
        mark.setAttribute('cx', here.x.toFixed(1));
        mark.setAttribute('cy', here.y.toFixed(1));
        mark.setAttribute('r', '5');
        mark.setAttribute('fill', '#e22330');
        mark.setAttribute('stroke', '#fff');
        mark.setAttribute('stroke-width', '1.5');
        mark.setAttribute('data-datum', String(datum));
        mark.style.cursor = 'grab';
        svg.appendChild(mark);
        host._curvePlan = { spots: marks, mark, svg, panels: n, at: datum };
        host.appendChild(svg);
    }

    // The wall a curve runs along, for the plan of one with corners: its
    // panel width in meters and its corners, each { start, size, turn } in
    // its panels (turn in radians, interior positive). A grouped row's
    // corners are its members', in the row's panels.
    _curveWallOf(layer, row = this._curveRow(layer)) {
        const list = this._curveMulti(row) ? (row.spots || []).map(sp => [sp, sp.owner])
            : this.riggingCornerSpots(layer).map(sp => [sp, layer]);
        const spots = list.map(([sp, owner]) => {
            const c = s3dCleanCorners(owner.riggingCorners).find(k => k.at === sp.at) || {};
            return { start: sp.start, size: sp.size, turn: s3dCornerTurn(c) * Math.PI / 180 };
        });
        return { w: (Number(layer.panel_width_mm) || 500) / 1000, spots };
    }

    // The nearest spot on the plan to a client point.
    _curvePlanSpot(host, clientX, clientY) {
        const plan = host && host._curvePlan;
        if (!plan) return null;
        const box = plan.svg.getBoundingClientRect();
        const x = clientX - box.left, y = clientY - box.top;
        let best = null, bestD = Infinity;
        for (const s of plan.spots) {
            const d = Math.hypot(s.x - x, s.y - y);
            if (d < bestD) { best = s; bestD = d; }
        }
        return best;
    }

    // Drag the red mark (or press anywhere on the plan) to move the datum.
    // The mark follows the pointer from spot to spot; letting go builds
    // from there. Never selects the page's text.
    _wireCurvePlanDrag(host) {
        if (!host || host.dataset.dragWired) return;
        host.dataset.dragWired = '1';
        host.style.userSelect = 'none';
        host.style.touchAction = 'none';
        let drag = null;
        const show = (spot) => {
            const plan = host._curvePlan;
            if (!plan || !spot) return;
            plan.mark.setAttribute('cx', spot.x.toFixed(1));
            plan.mark.setAttribute('cy', spot.y.toFixed(1));
            plan.mark.setAttribute('data-datum', String(spot.at));
        };
        host.addEventListener('pointerdown', (e) => {
            if (e.button !== 0 || !host._curvePlan) return;
            e.preventDefault();
            drag = { id: e.pointerId, spot: this._curvePlanSpot(host, e.clientX, e.clientY) };
            try { host.setPointerCapture(e.pointerId); } catch (_) {}
            host._curvePlan.mark.style.cursor = 'grabbing';
            show(drag.spot);
        });
        host.addEventListener('pointermove', (e) => {
            if (!drag || e.pointerId !== drag.id) return;
            e.preventDefault();
            drag.spot = this._curvePlanSpot(host, e.clientX, e.clientY) || drag.spot;
            show(drag.spot);
        });
        const end = (e, keep) => {
            if (!drag || e.pointerId !== drag.id) return;
            const spot = drag.spot;
            drag = null;
            try { host.releasePointerCapture(e.pointerId); } catch (_) {}
            if (host._curvePlan) host._curvePlan.mark.style.cursor = 'grab';
            if (keep && spot && spot.at !== host._curvePlan.at) this.setRiggingCurveField('from', spot.at);
            else host.dataset.sig = '';
            if (!keep) this.refreshRiggingCurve();
        };
        host.addEventListener('pointerup', (e) => end(e, true));
        host.addEventListener('pointercancel', (e) => end(e, false));
        host.addEventListener('selectstart', (e) => e.preventDefault());
    }
}

for (const k of Object.getOwnPropertyNames(_Curve.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Curve.prototype, k));
    }
}
