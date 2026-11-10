// app-corners: the Header/Footer tab's Corners, under the Curve. A screen
// bends 90 degrees between two columns or down the middle of one panel,
// Interior or Exterior (owner, 2026-11-09: "being able to set a point and
// bend 90 degree angles too", a column screen six panels wide with a 90
// degree bend in the middle of a panel). Columns only. EVERY CORNER IS
// EXACTLY 90 DEGREES (owner, 2026-11-10): there is no angle to type, and
// gentler bends come from the Curve.
//
// Add corner puts an Interior corner in the middle of each selected
// screen; each row then picks where it goes (any seam or panel middle)
// and its side, and x takes it off. A small plan of the
// screen from above, as the 3D tab builds it, shows every corner and any
// curve live. The 3D tab and Export > OBJ build the corners
// (app-stage3d.js s3dBuild).
//
// The owner's rulings of 2026-11-09:
// - Interior folds the sides toward the audience, Exterior away.
// - The side at the Curve's build-from point (the middle without a
//   Curve) stays put in 3D and the rest folds away; the block says which.
// - A corner's seam carries no curve angle: the corner takes its place,
//   and the Where list and the plan say so. The stored curve is left as
//   it is, so taking the corner off brings the angle back.
// - Bars split at a corner: its "Header Bar - Corner" (or Footer) covers
//   the panels touching it (app-rigging.js). Moving, adding or taking off
//   a corner lays an Auto row again around the corners in the same step;
//   in a custom row a bar on the corner's panels makes way for the
//   corner's piece, said in a toast. Two corners whose pieces would share
//   a panel cannot both be set: those spots are grayed out.
//
// The owner's rulings of 2026-11-10:
// - A corner down a panel's middle takes a "Header Bar - Corner (1
//   panel)", one on a seam a "Header Bar - Corner (2 panel)": two parts,
//   each its own line wherever bars are counted.
// - Every corner takes its corner bar. With the Curve on, the corners
//   split the screen into sides and each side is curved as its own wall
//   (app-curve.js); any change to the corners lays the Curve again in the
//   same step.
// - "the corner itself is flat due to the edge the opposite side of the
//   90 is curvable": only the fold takes no curve angle. Each side runs
//   right up to it, the corner bar's arm on that side included, and the
//   joint where the arm meets the next bar takes the side's curve angle.
//
// Stored on the layer as riggingCorners (app-stage3d.js s3dCleanCorners
// holds its shape). Every change is one undo step. The rows show the
// current screen's corners; an edit to a row changes the corner at that
// spot on every selected screen that has one there, so twin columns edit
// together.
import { LEDRasterApp } from './app-core.js';
import { CORNER_ANGLE, s3dBuild, s3dCleanCorners, s3dCornerAnchor, s3dCornersOn } from './app-stage3d.js';

const NS = 'http://www.w3.org/2000/svg';
const KIND_WORD = { header: 'Header', footer: 'Footer' };

// "Middle of panel 3", "Between panels 3 and 4"
export function cornerSpotLabel(at) {
    return Number.isInteger(at) ? `Middle of panel ${at}` : `Between panels ${at - 0.5} and ${at + 0.5}`;
}

// "5°", "7.5°"
const degWord = (a) => `${Math.round(Math.abs(a) * 10) / 10}°`;

// Where the corners fold from, in words: "the middle", "the left end",
// "panel 3", "the seam between panels 3 and 4".
export function cornerAnchorWords(anchor, cols) {
    if (anchor === 'left' || anchor === 0.5) return 'the left end';
    if (anchor === 'right' || anchor === cols + 0.5) return 'the right end';
    if (typeof anchor === 'number') {
        return Number.isInteger(anchor) ? `panel ${anchor}` : `the seam between panels ${anchor - 0.5} and ${anchor + 0.5}`;
    }
    return 'the middle';
}

// Every spot a corner can go on a screen `cols` columns wide, left to
// right: each panel middle and each seam between two panels.
export function cornerSpots(cols) {
    const out = [];
    for (let n = 1; n <= cols; n++) {
        out.push(n);
        if (n < cols) out.push(n + 0.5);
    }
    return out;
}

class _Corners {
    _wireRiggingCorners() {
        const add = document.getElementById('rigging-corner-add');
        if (!add || add.dataset.wired) return;
        add.dataset.wired = '1';
        add.addEventListener('click', () => this.addRiggingCorner());
        const list = document.getElementById('rigging-corner-list');
        if (!list) return;
        list.addEventListener('change', (e) => {
            const el = e.target;
            const row = el && el.closest ? el.closest('[data-corner]') : null;
            if (!row) return;
            const at = Number(row.dataset.corner);
            if (el.matches('[data-corner-at]')) this.setRiggingCorner(at, 'at', el.value);
        });
        list.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('button') : null;
            const row = btn ? btn.closest('[data-corner]') : null;
            if (!row) return;
            const at = Number(row.dataset.corner);
            if (btn.dataset.cornerSide) this.setRiggingCorner(at, 'side', btn.dataset.cornerSide);
            else if (btn.hasAttribute('data-corner-remove')) this.removeRiggingCorner(at);
        });
    }

    // ---- what is stored ---------------------------------------------------

    riggingCornersOf(layer) {
        return s3dCleanCorners(layer && layer.riggingCorners);
    }

    // The column count corners are counted against: the screen's columns.
    _cornerCols(layer) {
        return Math.max(1, Number(layer && layer.columns) || 1);
    }

    // The selected screens (none locked) a Corners edit acts on.
    _cornerTargets() {
        return this._writableLayers(this._riggingScreens());
    }

    // Is a spot free for a corner: no corner there, and none whose bar
    // would share a panel with this one's (`others`, the other corners'
    // spots)?
    _cornerSpotFree(at, others) {
        return !others.some(o => o === at || RiggingMath.cornersClash(o, at));
    }

    // The middle of a screen, or the free spot nearest it.
    _cornerMiddle(layer, taken) {
        const cols = this._cornerCols(layer);
        const mid = (cols + 1) / 2;
        const others = [...taken];
        const spots = cornerSpots(cols).filter(s => this._cornerSpotFree(s, others));
        spots.sort((a, b) => Math.abs(a - mid) - Math.abs(b - mid) || a - b);
        return spots.length ? spots[0] : null;
    }

    // After the corners of `layers` moved, came or went: the rows of bars
    // they sit on split at the corners again, in the same undo step. An
    // Auto row is laid again around its corners with its own lit sizes
    // (one that cannot be is left as it is, and the tab says it no longer
    // fits). In a custom row a bar on a corner's panels makes way for that
    // corner's piece, and a toast says so. A curved
    // screen is handed back in `curved`: its Curve lays its bars again
    // around its corners (app-curve.js). A row with a locked screen on it
    // is left as it is. { others, curved }: `others` the other screens it
    // changed, to save with the edit.
    _cornerRelayBars(layers) {
        const out = [];
        const curved = [];
        const seen = new Set();
        let became = 0;
        let word = 'Header';
        let pieceWord = 'Corner';
        for (const l of layers || []) {
            if (typeof this.riggingRow !== 'function' || !this._riggingCornersApply(l)) continue;
            const side = this.riggingSideOf(l);
            if (side === 'both') continue;
            const row = this.riggingRow(l, side);
            if (seen.has(row.key)) continue;
            seen.add(row.key);
            if (row.layers.some(m => this._layerLocked(m))) continue;
            if (row.layers.some(m => typeof this.riggingCurveOn === 'function' && this.riggingCurveOn(m))) {
                if (row.layers.length === 1) curved.push(row.layers[0]);
                continue;
            }
            if (!row.placed.length && !row.pieces.length) continue;
            if (!row.custom) {
                if (this._riggingFitRow(row, this._riggingSizesOf(row.layers[0]))) out.push(...row.layers);
                continue;
            }
            const on = (b, s) => b.start < s.start + s.size && s.start < b.start + b.size;
            const gone = row.placed.filter(b => row.spots.some(s => on(b, s)));
            if (!gone.length) continue;
            this._riggingWriteRow(row, row.placed.filter(b => !gone.includes(b)).map(b => ({ start: b.start, size: b.size })));
            const made = row.spots.filter(s => gone.some(b => on(b, s)));
            made.forEach(s => this._riggingSetCornerBars(s.owner, [s.at], true));
            became += gone.length;
            word = KIND_WORD[row.kind] || 'Header';
            if (made.length) pieceWord = RiggingMath.cornerWord(made[0].size);
            out.push(...row.layers);
        }
        if (became) {
            this._toast(`${became === 1 ? 'A bar' : `${became} bars`} on a corner's panels made way for the ${word} Bar - ${pieceWord}. Lay the panels beside it again by hand, or press Auto.`, false, 7000);
        }
        return { others: out.filter((l, i) => out.indexOf(l) === i && !(layers || []).includes(l)), curved };
    }

    // The panels each corner bar on `layers` covers in a custom row, before
    // a Corners edit moves or takes it off: Map(id -> { layer, kind,
    // panels }). Auto rows are laid again and curved screens are the
    // Curve's, so only custom rows are kept.
    _cornerPiecesBefore(layers) {
        const out = new Map();
        for (const l of layers || []) {
            if (typeof this.riggingRow !== 'function' || !this._riggingCornersApply(l)) continue;
            const kind = this.riggingSideOf(l);
            if (kind === 'both') continue;
            const row = this.riggingRow(l, kind);
            if (!row.custom || row.layers.some(m => this._layerLocked(m))) continue;
            if (typeof this.riggingCurveOn === 'function' && this.riggingCurveOn(l)) continue;
            const panels = new Set();
            for (const pc of this.riggingCornerPiecesOf(l)) for (let k = pc.start; k < pc.start + pc.size; k++) panels.add(k);
            if (panels.size) out.set(l.id, { layer: l, kind, panels });
        }
        return out;
    }

    // After the edit: the panels a corner bar left in a custom row that no
    // bar covers now are named (QA, 2026-11-10). A custom row may have
    // gaps, so the tab's no-longer-fit box never names them; without this
    // nothing said the bars laid there by hand had gone with the corner.
    _cornerSayBare(before) {
        const lines = [];
        for (const { layer, kind, panels } of (before || new Map()).values()) {
            const covered = new Set();
            for (const b of this.riggingSliceOf(layer, kind)) for (let k = b.start; k < b.start + b.size; k++) covered.add(k);
            const bare = [...panels].filter(k => !covered.has(k)).sort((a, b) => a - b).map(k => k + 1);
            if (!bare.length) continue;
            const run = bare.length > 2 && bare[bare.length - 1] - bare[0] === bare.length - 1;
            const words = bare.length === 1 ? `Panel ${bare[0]}`
                : run ? `Panels ${bare[0]} to ${bare[bare.length - 1]}`
                    : `Panels ${bare.slice(0, -1).join(', ')} and ${bare[bare.length - 1]}`;
            const name = layer.name || `Screen ${layer.id}`;
            lines.push(`${words} of ${name} ${bare.length === 1 ? 'is' : 'are'} left without a ${kind} bar.`);
        }
        if (lines.length) this._toast(`${lines.join(' ')} Lay bars there by hand, or press Auto.`, false, 7000);
    }

    // A Corners edit saved as one undo step: the screens it changed, the
    // others its bars changed, and a curved screen's Curve laid again
    // around its corners, all together (app-curve.js riggingCurveRelayLater).
    _cornerCommit(changed, relay, action) {
        if (!changed.length) return;
        const all = changed.concat(relay ? relay.others : []);
        const curved = relay ? relay.curved : [];
        if (curved.length && typeof this.riggingCurveRelayLater === 'function'
            && this.riggingCurveRelayLater(curved, action, all)) return;
        this.updateLayers(all, true, action);
    }

    addRiggingCorner() {
        const screens = this._cornerTargets();
        const changed = [];
        for (const l of screens) {
            const list = this.riggingCornersOf(l);
            const at = this._cornerMiddle(l, new Set(list.map(c => c.at)));
            if (at === null) continue;
            l.riggingCorners = s3dCleanCorners([...list, { at, angle: CORNER_ANGLE, side: 'interior' }]);
            changed.push(l);
        }
        if (changed.length) this._cornerCommit(changed, this._cornerRelayBars(changed), 'Add Corner');
        else if (screens.length) this._toast('This screen has no room for another corner. Corners need a panel of their own for their corner bars.', true, 5000);
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // One field of the corner at `at`, on every selected screen with a
    // corner there. One undo step.
    setRiggingCorner(at, key, raw) {
        const screens = this._cornerTargets();
        const patch = {};
        if (key === 'at') {
            const n = Number(raw);
            if (!Number.isFinite(n)) return;
            patch.at = n;
        } else if (key === 'side') {
            if (raw !== 'interior' && raw !== 'exterior') return;
            patch.side = raw;
        } else {
            return;
        }
        const changed = [];
        const blocked = [];
        const before = key === 'at' ? this._cornerPiecesBefore(screens) : null;
        for (const l of screens) {
            const list = this.riggingCornersOf(l);
            const i = list.findIndex(c => c.at === at);
            if (i < 0) continue;
            if (patch.at !== undefined && patch.at !== at) {
                const cols = this._cornerCols(l);
                if (!cornerSpots(cols).includes(patch.at)) continue;
                const others = list.filter(c => c.at !== at).map(c => c.at);
                if (!this._cornerSpotFree(patch.at, others)) { blocked.push(l); continue; }
            }
            const next = list.map((c, k) => (k === i ? { ...c, ...patch } : c));
            const clean = s3dCleanCorners(next);
            if (JSON.stringify(clean) === JSON.stringify(list)) continue;
            l.riggingCorners = clean;
            changed.push(l);
        }
        if (blocked.length) {
            this._toast(`${cornerSpotLabel(patch.at)} is taken or too close to another corner on ${blocked.map(l => l.name || `Screen ${l.id}`).join(', ')}. Corners need a panel of their own for their corner bars.`, true, 6000);
        }
        // A corner that moved splits its bars somewhere else.
        const relay = patch.at !== undefined ? this._cornerRelayBars(changed) : null;
        if (before) this._cornerSayBare(new Map([...before].filter(([id]) => changed.some(l => l.id === id))));
        this._cornerCommit(changed, relay, 'Corner');
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    removeRiggingCorner(at) {
        const changed = [];
        const targets = this._cornerTargets();
        const before = this._cornerPiecesBefore(targets);
        for (const l of targets) {
            const list = this.riggingCornersOf(l);
            if (!list.some(c => c.at === at)) continue;
            l.riggingCorners = list.filter(c => c.at !== at);
            changed.push(l);
        }
        if (changed.length) {
            const relay = this._cornerRelayBars(changed);
            this._cornerSayBare(new Map([...before].filter(([id]) => changed.some(l => l.id === id))));
            this._cornerCommit(changed, relay, 'Remove Corner');
        }
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // ---- the panel --------------------------------------------------------

    refreshRiggingCorners() {
        const block = document.getElementById('rigging-corners');
        const host = document.getElementById('rigging-corner-list');
        if (!block || !host) return;
        const screens = this._riggingScreens();
        const primary = this._riggingPrimary(screens);
        block.style.display = primary ? '' : 'none';
        if (!primary) return;
        const cols = this._cornerCols(primary);
        const all = this.riggingCornersOf(primary);
        const list = s3dCornersOn(primary, cols);
        const spots = cornerSpots(cols);
        // Rebuilt only when the rows change shape; otherwise each row is
        // brought up to date in place, so a field being typed in keeps its
        // focus (Tab from one row's control lands in the next one).
        // The angle the Curve (or the 3D tab) gives each seam, as the screen
        // stands without its corners: a corner on a seam takes its place.
        const seamAngles = this._cornerSeamAngles(primary);
        const sig = JSON.stringify([primary.id, cols, list.map(c => c.at)]);
        if (host.dataset.sig !== sig) {
            host.dataset.sig = sig;
            host.innerHTML = '';
            list.forEach(c => host.appendChild(this._cornerRow(c, spots)));
        }
        const used = list.map(c => c.at);
        host.querySelectorAll('[data-corner]').forEach(row => {
            const c = list.find(x => x.at === Number(row.dataset.corner));
            if (!c) return;
            const sel = row.querySelector('[data-corner-at]');
            if (sel) {
                const others = used.filter(a => a !== c.at);
                [...sel.options].forEach(o => {
                    const v = Number(o.value);
                    o.disabled = v !== c.at && !this._cornerSpotFree(v, others);
                    // A seam the Curve bends says so: a corner there takes
                    // the place of that angle.
                    const a = Number.isInteger(v) ? 0 : (seamAngles[Math.round(v - 1.5)] || 0);
                    const text = cornerSpotLabel(v) + (a ? `, curve ${degWord(a)}` : '')
                        + (o.disabled ? (used.includes(v) ? ', has a corner' : ', too close') : '');
                    if (o.textContent !== text) o.textContent = text;
                });
                if (document.activeElement !== sel) sel.value = String(c.at);
            }
            // The seam's own curve angle, left out while the corner is there.
            let gone = row.querySelector('.rigging-corner-replaces');
            const a = Number.isInteger(c.at) ? 0 : (seamAngles[Math.round(c.at - 1.5)] || 0);
            if (a) {
                if (!gone) {
                    gone = document.createElement('div');
                    gone.className = 'rigging-corner-replaces';
                    gone.style.cssText = 'color: #aaa; font-size: 11px; margin-top: 2px;';
                    row.appendChild(gone);
                }
                gone.textContent = `This seam has no curve angle while the corner is on it. Its ${degWord(a)} comes back if the corner goes.`;
            } else if (gone) {
                gone.remove();
            }
            row.querySelectorAll('[data-corner-side]').forEach(b => {
                b.classList.toggle('active', b.dataset.cornerSide === c.side);
            });
        });
        const off = all.length - list.length;
        let note = host.querySelector('.rigging-corner-off');
        if (off > 0) {
            if (!note) {
                note = document.createElement('div');
                note.className = 'rigging-corner-off';
                note.style.cssText = 'color: #f5a623; font-size: 11px; margin-top: 2px;';
                host.appendChild(note);
            }
            note.textContent = `${off === 1 ? 'A corner is' : `${off} corners are`} past this screen's last column and not built. Add columns or remove it.`;
        } else if (note) {
            note.remove();
        }
        // Which side stays put in 3D.
        const hold = document.getElementById('rigging-corner-hold');
        if (hold) {
            hold.style.display = list.length ? '' : 'none';
            const curved = typeof this.riggingCurveOn === 'function' && this.riggingCurveOn(primary);
            const words = cornerAnchorWords(s3dCornerAnchor(primary, cols), cols);
            const text = `In 3D, ${words} stays put and the rest folds away from it`
                + (curved ? ' (the Curve\'s Build from).' : '.');
            if (hold.textContent !== text) hold.textContent = text;
        }
        this._cornerDrawPlan(document.getElementById('rigging-corner-plan'), primary);
    }

    // The angle at each seam (0-based joint) the screen has without its
    // corners: the Curve's, or the 3D tab's.
    _cornerSeamAngles(layer) {
        let placement = null;
        try { placement = this._s3dPlacementOf(layer); } catch (_) { placement = null; }
        try {
            return s3dBuild({ ...layer, riggingCorners: [] }, placement || {}).colJ;
        } catch (_) {
            return [];
        }
    }

    _cornerRow(c, spots) {
        const row = document.createElement('div');
        row.className = 'rigging-corner-row';
        row.dataset.corner = String(c.at);
        row.style.cssText = 'margin-top: 4px; padding-top: 4px; border-top: 1px solid #2a2a2a;';
        const top = document.createElement('div');
        top.style.cssText = 'display: flex; align-items: center; gap: 3px;';
        const bottom = document.createElement('div');
        bottom.style.cssText = 'display: flex; align-items: center; gap: 3px; margin-top: 3px;';
        const sel = document.createElement('select');
        sel.setAttribute('data-corner-at', '');
        sel.style.cssText = 'flex: 1; min-width: 0; padding: 2px 3px; font-size: 11px;';
        sel.setAttribute('data-tooltip', 'Where, the seam between two panels or the middle of one panel the screen bends at. Columns only.');
        spots.forEach(s => {
            const o = document.createElement('option');
            o.value = String(s);
            o.textContent = cornerSpotLabel(s);
            sel.appendChild(o);
        });
        const side = document.createElement('div');
        side.style.cssText = 'display: flex; gap: 2px; flex: 1; min-width: 0;';
        [['interior', 'Interior', 'Interior, the two sides fold toward the audience, the inside of the corner faces them.'],
            ['exterior', 'Exterior', 'Exterior, the two sides fold away from the audience, the outside of the corner faces them.']]
            .forEach(([value, text, tip]) => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'btn btn-secondary rigging-corner-btn';
                b.dataset.cornerSide = value;
                b.textContent = text;
                b.setAttribute('data-tooltip', tip);
                b.style.flex = '1';
                b.style.minWidth = '0';
                b.style.setProperty('padding', '2px 4px', 'important');
                b.style.setProperty('font-size', '11px', 'important');
                side.appendChild(b);
            });
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-secondary';
        remove.setAttribute('data-corner-remove', '');
        remove.textContent = '×';
        remove.setAttribute('aria-label', 'Remove corner');
        remove.setAttribute('data-tooltip', 'Remove corner, the screen goes straight here again.');
        remove.style.setProperty('padding', '2px 6px', 'important');
        remove.style.setProperty('font-size', '11px', 'important');
        top.append(sel, remove);
        bottom.append(side);
        row.append(top, bottom);
        return row;
    }

    // The screen from above as the 3D tab builds it (corners, curve and
    // joint angles), audience at the bottom, each corner a red dot.
    _cornerDrawPlan(host, layer) {
        if (!host) return;
        const corners = s3dCornersOn(layer, this._cornerCols(layer));
        let placement = null;
        try { placement = this._s3dPlacementOf(layer); } catch (_) { placement = null; }
        const built = s3dBuild(layer, placement || {});
        const n = built.colLen.length;
        const bent = corners.length || built.colJ.some(a => a);
        if (!n || !bent) {
            host.innerHTML = '';
            host.dataset.sig = '';
            host.style.display = 'none';
            return;
        }
        host.style.display = '';
        const at = (i, u) => { const p = built.point(i, u, 0, 0); return { x: p[0], y: p[2] }; };
        const pts = [];
        const dots = [];
        for (let i = 0; i < n; i++) {
            pts.push(at(i, 0));
            const f = built.foldAt(i);
            if (f !== null) { const p = at(i, f); pts.push(p); dots.push(p); }
        }
        pts.push(at(n - 1, built.colLen[n - 1]));
        corners.filter(c => !Number.isInteger(c.at)).forEach(c => dots.push(at(c.at - 0.5, 0)));
        // Gray: a seam the curve bends. A corner's seam is red only, with
        // no curve angle on it.
        const bends = [];
        built.colJ.forEach((a, j) => {
            if (a && !(built.cornerSeams && built.cornerSeams.has(j))) bends.push(at(j + 1, 0));
        });
        const W = Math.max(120, (host.clientWidth || 200) - 2);
        const sig = JSON.stringify([pts.map(p => [Math.round(p.x), Math.round(p.y)]), dots.length, bends.length, W]);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const p of pts) {
            x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x);
            y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y);
        }
        const pad = 8;
        const span = Math.max(1, x1 - x0, y1 - y0);
        const H = Math.max(28, Math.min(110, Math.round((y1 - y0) / span * (W - 2 * pad) + 2 * pad)));
        const k = Math.min((W - 2 * pad) / Math.max(1, x1 - x0), (H - 2 * pad) / Math.max(1, y1 - y0));
        const ox = (W - (x1 - x0) * k) / 2 - x0 * k;
        const oy = (H - (y1 - y0) * k) / 2 - y0 * k;
        const to = (p) => [p.x * k + ox, p.y * k + oy];
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('width', String(W));
        svg.setAttribute('height', String(H));
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.style.display = 'block';
        const line = document.createElementNS(NS, 'polyline');
        line.setAttribute('points', pts.map(p => to(p).map(v => v.toFixed(1)).join(',')).join(' '));
        line.setAttribute('fill', 'none');
        line.setAttribute('stroke', '#ddd');
        line.setAttribute('stroke-width', '2');
        svg.appendChild(line);
        bends.forEach(p => {
            const [cx, cy] = to(p);
            const d = document.createElementNS(NS, 'circle');
            d.setAttribute('cx', cx.toFixed(1));
            d.setAttribute('cy', cy.toFixed(1));
            d.setAttribute('r', '2.5');
            d.setAttribute('fill', '#888');
            d.setAttribute('data-curve-dot', '');
            svg.appendChild(d);
        });
        dots.forEach(p => {
            const [cx, cy] = to(p);
            const d = document.createElementNS(NS, 'circle');
            d.setAttribute('cx', cx.toFixed(1));
            d.setAttribute('cy', cy.toFixed(1));
            d.setAttribute('r', '3.5');
            d.setAttribute('fill', '#e22330');
            d.setAttribute('data-corner-dot', '');
            svg.appendChild(d);
        });
        host.appendChild(svg);
    }
}

for (const k of Object.getOwnPropertyNames(_Corners.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Corners.prototype, k));
    }
}
