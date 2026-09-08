// app-beaches: beaches are a list the project keeps, and everything picks
// from it (2026-09-08).
//
// "beach locations need to be addable for data" / "you can either create a
// beach or you can pick one from the drop-down of one that you created
// earlier in the project" / "Replace it with the picker" (the typed Location
// fields on the distro and box gears).
//
//   project.beaches = [{ id: 'b1', name: 'SR' }, ...]   in ORDER - the
//                     pull-sheet position order and the binder's screen order
//   layer.beachId / distro.beachId / cvt.beachId - each nullable: where that
//                     thing's gear is pulled to (app-pull-list pullPositions)
//
// The SERVER owns the list (routes_project: POST /api/beaches, PUT
// /api/beaches/<id>, DELETE /api/beaches/<id>, PUT /api/beaches/order) and
// every route answers with the whole project, adopted here the way the canvas
// routes' answers are (_applyProjectUpdate) - one truth, never a patched copy.
// The load funnel turns a typed location saved in an older file into a beach
// of that name (app.py _normalize_beaches), so nothing here reads `location`.
//
// ONE picker component serves the three places a beach is chosen: the Screen
// Info panel (#layer-beach, 'Set Beach'), the distro's gear (distro-beach-<id>,
// 'Set Distro Beach') and the box's gear (processor-cvt-beach-<id>, 'Set Box
// Beach'). It is a <select> of the project's beaches in order, a blank
// "- no beach -" entry, and a last "+ New beach..." entry that prompts for a
// name, creates the beach and selects it - one history entry for the whole
// gesture, under the picker's own action name.
//
// The beaches are managed (renamed, reordered, removed) on a BEACHES line in
// the SCREENS panel on the right, under the canvases: it is where the project's
// other organising things (canvases, groups) are already renamed by
// double-click and reordered by drag, so the idiom is the panel's own.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The picker's "make one" entry. Never a beach id (ids are b<N>).
const NEW_BEACH = '__new_beach__';

class _Beaches {

    // ---- the list -----------------------------------------------------------

    getBeaches() {
        if (!this.project) return [];
        if (!Array.isArray(this.project.beaches)) this.project.beaches = [];
        return this.project.beaches.filter(b => b && typeof b === 'object' && b.id);
    }

    beachById(id) {
        if (id == null || id === '') return null;
        return this.getBeaches().find(b => b.id === id) || null;
    }

    beachName(id) {
        const b = this.beachById(id);
        return b ? String(b.name || '') : '';
    }

    beachByName(name) {
        const norm = String(name == null ? '' : name).trim().toLowerCase();
        if (!norm) return null;
        return this.getBeaches().find(b => String(b.name || '').trim().toLowerCase() === norm) || null;
    }

    // ---- the routes ---------------------------------------------------------

    // Every beach route answers with the whole project; adopt it, re-render
    // what lists beaches (the Screens panel, the Screen Info picker, the
    // tray's gear popovers), and take ONE history entry under `action` when
    // the caller asked for one (null: the caller owns the entry - the "+ New
    // beach..." gesture snapshots once, after the pick lands).
    async _beachRequest(url, method, body, action) {
        let data = null;
        try {
            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: body === undefined ? undefined : JSON.stringify(body),
            });
            data = await res.json();
        } catch (err) {
            sendClientLog('beach_request_failed', { url, method, error: String(err) });
            return null;
        }
        if (data && data.error) {
            if (typeof this._toast === 'function') this._toast(data.error, true, 6000);
            this.renderBeaches();
            return data;
        }
        if (data && data.project && typeof this._applyProjectUpdate === 'function') {
            this._applyProjectUpdate(data.project);
        }
        if (typeof this.loadLayerToInputs === 'function') {
            try { this.loadLayerToInputs(); } catch (_) { /* inputs are optional here */ }
        }
        if (typeof this.renderHardwareDock === 'function') this.renderHardwareDock();
        this._circuitTailCache = null;
        if (action) this.saveState(action);
        return data;
    }

    // The beach called `name`: the one the project already has (case-blind)
    // or a new one at the end of the list. Resolves to the beach, or null.
    async createBeach(name, action = 'Add Beach') {
        const text = String(name == null ? '' : name).trim();
        if (!text) return null;
        const data = await this._beachRequest('/api/beaches', 'POST', { name: text }, action);
        return data && data.beach ? data.beach : null;
    }

    async renameBeach(id, name, action = 'Rename Beach') {
        const text = String(name == null ? '' : name).trim();
        if (!text || !this.beachById(id)) return null;
        const data = await this._beachRequest(`/api/beaches/${id}`, 'PUT', { name: text }, action);
        return data && data.beach ? data.beach : null;
    }

    async removeBeach(id, action = 'Remove Beach') {
        if (!this.beachById(id)) return false;
        const data = await this._beachRequest(`/api/beaches/${id}`, 'DELETE', undefined, action);
        return !!(data && data.project);
    }

    async reorderBeaches(ids, action = 'Reorder Beaches') {
        const data = await this._beachRequest('/api/beaches/order', 'PUT', { ids }, action);
        return !!(data && data.project);
    }

    // ---- the picker ---------------------------------------------------------

    // Fill `select` with the project's beaches in order: blank first, the
    // beaches, "+ New beach..." last. `value` is the beachId to show; null or
    // an id no beach answers to shows the blank; `mixed` (a multi-selection
    // that disagrees) shows a dash and selects nothing.
    fillBeachPicker(select, value, mixed = false) {
        if (!select) return select;
        select.innerHTML = '';
        const opt = (v, text) => {
            const o = document.createElement('option');
            o.value = v;
            o.textContent = text;
            select.appendChild(o);
            return o;
        };
        opt('', mixed ? '-' : '— no beach —');
        for (const b of this.getBeaches()) opt(b.id, b.name || b.id);
        opt(NEW_BEACH, '+ New beach…');
        const known = value != null && value !== '' && !!this.beachById(value);
        select.value = known && !mixed ? value : '';
        select.dataset.beachValue = known && !mixed ? value : '';
        return select;
    }

    // Wire a filled picker: a pick calls `onPick(beachId | null)`; the last
    // entry prompts for a name, makes the beach (no entry of its own) and
    // picks it. `onPick` owns the history entry, so a create-and-pick is one
    // undo. A cancelled or blank prompt puts the select back.
    wireBeachPicker(select, onPick) {
        if (!select) return select;
        select.addEventListener('change', async () => {
            const chosen = select.value;
            if (chosen !== NEW_BEACH) {
                select.dataset.beachValue = chosen;
                onPick(chosen || null);
                return;
            }
            const name = (window.prompt('New beach name:') || '').trim();
            if (!name) {
                select.value = select.dataset.beachValue || '';
                return;
            }
            const beach = await this.createBeach(name, null);
            if (!beach) {
                select.value = select.dataset.beachValue || '';
                return;
            }
            // The adoption above may have rebuilt the picker's host; refresh
            // this one too in case it is still on screen.
            if (select.isConnected) this.fillBeachPicker(select, beach.id);
            onPick(beach.id);
        });
        return select;
    }

    // A ready picker for a gear popover: caption + select, the select keyed
    // `fieldKey` (data-lrd-field, the focus-preservation key every popover
    // field carries), selected on `value`.
    buildBeachPicker({ value, fieldKey, onPick, title } = {}) {
        const wrap = document.createElement('div');
        wrap.style.flex = '1';
        wrap.style.minWidth = '0';
        const cap = document.createElement('label');
        cap.style.fontSize = '10px';
        cap.style.color = 'var(--ps-dim, #c0c0c0)';
        cap.textContent = 'Beach';
        const select = document.createElement('select');
        select.style.width = '100%';
        select.style.boxSizing = 'border-box';
        select.style.fontFamily = 'monospace';
        if (fieldKey) select.dataset.lrdField = fieldKey;
        select.title = title || 'Where this sits - pick one of the project\'s beaches, '
            + 'or make one. Every row it produces is pulled there.';
        this.fillBeachPicker(select, value);
        this.wireBeachPicker(select, onPick || (() => {}));
        wrap.appendChild(cap);
        wrap.appendChild(select);
        return wrap;
    }

    // ---- the Screen Info picker (#layer-beach) ------------------------------

    // Called from setupEventListeners: a pick stamps every selected screen
    // and takes one 'Set Beach' entry.
    setupBeachPicker() {
        const select = document.getElementById('layer-beach');
        if (!select || select.dataset.beachWired) return;
        select.dataset.beachWired = '1';
        this.fillBeachPicker(select, null);
        this.wireBeachPicker(select, (beachId) => {
            this.applyToSelectedLayers(layer => { layer.beachId = beachId; });
            this._circuitTailCache = null;
            this.updateLayers(this.getSelectedLayers(), true, 'Set Beach');
            this.renderLayers();
        });
    }

    // Called from loadLayerToInputs: show the selection's beach.
    loadBeachPicker(layers) {
        const select = document.getElementById('layer-beach');
        if (!select) return;
        const list = Array.isArray(layers) ? layers : [];
        const first = list.length ? (list[0].beachId || null) : null;
        const mixed = list.some(l => (l.beachId || null) !== first);
        this.fillBeachPicker(select, first, mixed);
    }

    // ---- the BEACHES line in the Screens panel ------------------------------

    // One row per beach in order: a drag handle to reorder, the name
    // (double-click to rename, the panel's idiom), a count of what is pulled
    // there, and an x to remove it. "+ Add beach" prompts for a name.
    renderBeaches() {
        const host = document.getElementById('beaches-panel');
        if (!host) return;
        host.innerHTML = '';
        const beaches = this.getBeaches();
        const counts = new Map();
        const bump = (id) => { if (id) counts.set(id, (counts.get(id) || 0) + 1); };
        for (const l of ((this.project && this.project.layers) || [])) bump(l && l.beachId);
        for (const d of (typeof this.getDistros === 'function' ? this.getDistros() : [])) bump(d && d.beachId);
        for (const proc of ((this.project && this.project.processors) || [])) {
            for (const slot of (proc && proc.slots) || []) {
                for (const box of (slot && slot.card && slot.card.cvts) || []) bump(box && box.beachId);
            }
        }

        const head = document.createElement('div');
        head.className = 'beaches-head';
        head.innerHTML = '<span class="beaches-title">Beaches</span>'
            + '<button type="button" class="btn btn-secondary beaches-add" '
            + 'title="Make a beach - a position the pull sheet lists and the order the binder runs the screens in">+ Add beach</button>';
        head.querySelector('.beaches-add').addEventListener('click', (e) => {
            e.stopPropagation();
            const name = (window.prompt('New beach name:') || '').trim();
            if (name) this.createBeach(name);
        });
        host.appendChild(head);

        if (!beaches.length) {
            const empty = document.createElement('div');
            empty.className = 'beaches-empty';
            empty.textContent = 'No beaches yet. Each screen is its own position until it is put on one.';
            host.appendChild(empty);
            return;
        }

        const list = document.createElement('div');
        list.className = 'beaches-list';
        beaches.forEach((beach, index) => {
            const row = document.createElement('div');
            row.className = 'beach-row';
            row.dataset.beachId = beach.id;
            row.draggable = true;
            const n = counts.get(beach.id) || 0;
            row.innerHTML = `
                <span class="canvas-drag-handle beach-drag-handle" title="Drag to reorder - the pull sheet and binder run in this order">⋮⋮</span>
                <span class="beach-order">${index + 1}</span>
                <input class="beach-name-input" type="text" value="${this._escapeAttr(beach.name || '')}" readonly title="Double-click to rename">
                <span class="beach-count" title="Screens, distros and boxes on this beach">${n ? n : ''}</span>
                <button type="button" class="layer-btn beach-remove" title="Remove this beach - whatever is on it goes back to its own position">×</button>
            `;
            this._wireBeachRow(row, beach);
            list.appendChild(row);
        });
        host.appendChild(list);
    }

    _wireBeachRow(row, beach) {
        const nameInput = row.querySelector('.beach-name-input');
        const removeBtn = row.querySelector('.beach-remove');

        nameInput.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            nameInput.readOnly = false;
            nameInput.classList.add('editing');
            nameInput.focus();
            nameInput.select();
        });
        const commitName = () => {
            if (nameInput.readOnly) return;
            nameInput.readOnly = true;
            nameInput.classList.remove('editing');
            const newName = nameInput.value.trim();
            if (newName && newName !== beach.name) {
                this.renameBeach(beach.id, newName);
            } else {
                nameInput.value = beach.name || '';
            }
        };
        nameInput.addEventListener('blur', commitName);
        nameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); nameInput.blur(); }
            else if (e.key === 'Escape') {
                nameInput.value = beach.name || '';
                nameInput.readOnly = true;
                nameInput.classList.remove('editing');
                nameInput.blur();
            }
            if (!nameInput.readOnly) e.stopPropagation();
        });

        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.removeBeach(beach.id);
        });

        // Drag a row onto another to put it BEFORE that one (moveBeachBefore
        // with a null target puts one last).
        row.addEventListener('dragstart', (e) => {
            if (!nameInput.readOnly) { e.preventDefault(); return; }
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', `beach:${beach.id}`);
            this._dragBeachId = beach.id;
            row.classList.add('dragging');
        });
        row.addEventListener('dragend', () => {
            row.classList.remove('dragging');
            this._dragBeachId = null;
            document.querySelectorAll('.beach-row.drag-target')
                .forEach(el => el.classList.remove('drag-target'));
        });
        row.addEventListener('dragover', (e) => {
            if (!this._dragBeachId || this._dragBeachId === beach.id) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            row.classList.add('drag-target');
        });
        row.addEventListener('dragleave', (e) => {
            if (!row.contains(e.relatedTarget)) row.classList.remove('drag-target');
        });
        row.addEventListener('drop', (e) => {
            row.classList.remove('drag-target');
            const dragged = this._dragBeachId;
            if (!dragged || dragged === beach.id) return;
            e.preventDefault();
            this.moveBeachBefore(dragged, beach.id);
        });
    }

    // Reorder: `id` goes just before `targetId` (null: to the end).
    moveBeachBefore(id, targetId) {
        const ids = this.getBeaches().map(b => b.id);
        if (!ids.includes(id) || (targetId != null && !ids.includes(targetId))) return false;
        const rest = ids.filter(x => x !== id);
        const at = targetId == null ? rest.length : rest.indexOf(targetId);
        rest.splice(at, 0, id);
        if (rest.join('|') === ids.join('|')) return false;
        this.reorderBeaches(rest);
        return true;
    }
}

for (const k of Object.getOwnPropertyNames(_Beaches.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Beaches.prototype, k));
    }
}
