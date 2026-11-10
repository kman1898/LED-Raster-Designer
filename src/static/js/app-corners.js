// app-corners: the Header/Footer tab's Corners, under the Curve. A screen
// bends between two columns or down the middle of one panel, any angle up
// to 90 degrees, Interior or Exterior (owner, 2026-11-09: "being able to
// set a point and bend 90 degree angles too", a column screen six panels
// wide with a 90 degree bend in the middle of a panel). Columns only.
//
// Add corner puts a 90 degree Interior corner in the middle of each
// selected screen; each row then picks where it goes (any seam or panel
// middle), its angle and its side, and x takes it off. A small plan of the
// screen from above, as the 3D tab builds it, shows every corner and any
// curve live. The 3D tab and Export > OBJ build the corners
// (app-stage3d.js s3dBuild); a corner on a seam that also has a curve
// angle adds to it. Corners are shape only: no bar, total or pull list
// changes.
//
// Stored on the layer as riggingCorners (app-stage3d.js s3dCleanCorners
// holds its shape). Every change is one undo step. The rows show the
// current screen's corners; an edit to a row changes the corner at that
// spot on every selected screen that has one there, so twin columns edit
// together.
import { LEDRasterApp } from './app-core.js';
import { CORNER_MAX, s3dBuild, s3dCleanCorners, s3dCornersOn } from './app-stage3d.js';

const NS = 'http://www.w3.org/2000/svg';

// "Middle of panel 3", "Between panels 3 and 4"
export function cornerSpotLabel(at) {
    return Number.isInteger(at) ? `Middle of panel ${at}` : `Between panels ${at - 0.5} and ${at + 0.5}`;
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
            else if (el.matches('[data-corner-angle]')) this.setRiggingCorner(at, 'angle', el.value);
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

    // The middle of a screen, or the free spot nearest it.
    _cornerMiddle(layer, taken) {
        const cols = this._cornerCols(layer);
        const mid = (cols + 1) / 2;
        const spots = cornerSpots(cols).filter(s => !taken.has(s));
        spots.sort((a, b) => Math.abs(a - mid) - Math.abs(b - mid) || a - b);
        return spots.length ? spots[0] : null;
    }

    addRiggingCorner() {
        const screens = this._cornerTargets();
        const changed = [];
        for (const l of screens) {
            const list = this.riggingCornersOf(l);
            const at = this._cornerMiddle(l, new Set(list.map(c => c.at)));
            if (at === null) continue;
            l.riggingCorners = s3dCleanCorners([...list, { at, angle: CORNER_MAX, side: 'interior' }]);
            changed.push(l);
        }
        if (changed.length) this.updateLayers(changed, true, 'Add Corner');
        else if (screens.length) this._toast('Every panel and seam of this screen already has a corner.', true, 5000);
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
        } else if (key === 'angle') {
            const v = Number(String(raw).replace(/[°\s]/g, ''));
            if (!Number.isFinite(v) || v <= 0 || v > CORNER_MAX) {
                this._toast('Corner angle, type an angle above 0 and up to 90 degrees.', true, 5000);
                this.refreshRiggingPanel();
                return;
            }
            patch.angle = v;
        } else if (key === 'side') {
            if (raw !== 'interior' && raw !== 'exterior') return;
            patch.side = raw;
        } else {
            return;
        }
        const changed = [];
        const blocked = [];
        for (const l of screens) {
            const list = this.riggingCornersOf(l);
            const i = list.findIndex(c => c.at === at);
            if (i < 0) continue;
            if (patch.at !== undefined && patch.at !== at) {
                const cols = this._cornerCols(l);
                if (!cornerSpots(cols).includes(patch.at)) continue;
                if (list.some(c => c.at === patch.at)) { blocked.push(l); continue; }
            }
            const next = list.map((c, k) => (k === i ? { ...c, ...patch } : c));
            const clean = s3dCleanCorners(next);
            if (JSON.stringify(clean) === JSON.stringify(list)) continue;
            l.riggingCorners = clean;
            changed.push(l);
        }
        if (blocked.length) {
            this._toast(`${cornerSpotLabel(patch.at)} already has a corner on ${blocked.map(l => l.name || `Screen ${l.id}`).join(', ')}.`, true, 5000);
        }
        if (changed.length) this.updateLayers(changed, true, 'Corner');
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    removeRiggingCorner(at) {
        const changed = [];
        for (const l of this._cornerTargets()) {
            const list = this.riggingCornersOf(l);
            if (!list.some(c => c.at === at)) continue;
            l.riggingCorners = list.filter(c => c.at !== at);
            changed.push(l);
        }
        if (changed.length) this.updateLayers(changed, true, 'Remove Corner');
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
        // focus (Tab from one row's angle lands in the next control).
        const sig = JSON.stringify([primary.id, cols, list.map(c => c.at)]);
        if (host.dataset.sig !== sig) {
            host.dataset.sig = sig;
            host.innerHTML = '';
            list.forEach(c => host.appendChild(this._cornerRow(c, spots)));
        }
        const used = new Set(list.map(c => c.at));
        host.querySelectorAll('[data-corner]').forEach(row => {
            const c = list.find(x => x.at === Number(row.dataset.corner));
            if (!c) return;
            const sel = row.querySelector('[data-corner-at]');
            if (sel) {
                [...sel.options].forEach(o => { o.disabled = Number(o.value) !== c.at && used.has(Number(o.value)); });
                if (document.activeElement !== sel) sel.value = String(c.at);
            }
            const angle = row.querySelector('[data-corner-angle]');
            if (angle && document.activeElement !== angle) angle.value = String(c.angle);
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
        this._cornerDrawPlan(document.getElementById('rigging-corner-plan'), primary);
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
        const angle = document.createElement('input');
        angle.type = 'text';
        angle.autocomplete = 'off';
        angle.setAttribute('data-corner-angle', '');
        angle.style.cssText = 'width: 34px; padding: 2px 4px; font-size: 11px;';
        angle.setAttribute('data-tooltip', 'Angle, how far the screen bends here, above 0 and up to 90 degrees.');
        const deg = document.createElement('span');
        deg.textContent = '°';
        deg.style.color = '#888';
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
        bottom.append(angle, deg, side);
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
        const W = Math.max(120, (host.clientWidth || 200) - 2);
        const sig = JSON.stringify([pts.map(p => [Math.round(p.x), Math.round(p.y)]), dots.length, W]);
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
