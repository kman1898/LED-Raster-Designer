// app-cable-stock: the show's cable stock - the cable lengths it has on
// hand - as the user sets it, and the named presets of it. Owner rulings,
// 2026-10-20 ("in preferences we need to be able to set cable lengths
// available on a show and load presets"):
//
//   * The stock is the SHOW's (project.cableStock, app-cable-units.js has
//     its shape, its reading and the breakdown). Preferences > Cable stock
//     shows the open show's lists; Save gives the edited lists to the show
//     as ONE undo step ('Set Cable Stock'), persisted on the pull sheet's
//     POST queue. Cancel forgets the edit like any other.
//   * PRESETS are kept for every show (routes_cable_stock.py, a file beside
//     the presets folder, like distro presets): Load puts a preset's lists
//     in the fields (Save then gives them to the show), Save as preset and
//     Delete happen at once, as the distro presets' do.
//   * "New shows start with" is a preference (cableStockDefault, a preset's
//     name): the server stamps that preset's stock on a NEW show
//     (routes_project new_project), and the pristine startup show takes it
//     here, the way it takes the cable unit.
import { LEDRasterApp } from './app-core.js';
import { CABLE_UNITS, CABLE_STOCK_ALL, CABLE_STOCK_KINDS, CABLE_STOCK_FIBER } from './app-cable-units.js';

// The fiber lists (single mode, multimode) ride along: their rows show
// whatever the per-kind switch says (data-cable-stock-fiber, not
// data-cable-stock-list), because a fiber is never pulled from a copper list.
const STOCK_LISTS = [CABLE_STOCK_ALL, ...CABLE_STOCK_KINDS, ...CABLE_STOCK_FIBER];

class _CableStock {

    // ---- the show's stock ------------------------------------------------

    // A stock worth storing: null when no list holds a length (the show
    // then writes every length as typed, as one without a stock does).
    _storableCableStock(stock) {
        const s = this.normalizeCableStock(stock);
        if (!s) return null;
        const any = CABLE_UNITS.some(u => STOCK_LISTS.some(k => s[u][k].length));
        return any ? s : null;
    }

    // Set the show's stock: one history entry, one project POST, every
    // tag and paper redrawn. Returns true when it changed.
    setCableStock(stock, action = 'Set Cable Stock') {
        if (!this.project) return false;
        const next = this._storableCableStock(stock);
        const before = this._storableCableStock(this.project.cableStock);
        if (JSON.stringify(next) === JSON.stringify(before)) return false;
        this.project.cableStock = next;
        // Project-level state, the cable unit's doctrine: snapshot after
        // the mutation, then persist (save_project merges top-level keys).
        if (typeof this.saveState === 'function') this.saveState(action);
        this._postPullSheetState(['cableStock']);
        this.refreshCableUnitViews();
        return true;
    }

    // ---- presets ---------------------------------------------------------

    // The presets saved (server-side, shared). Cached once fetched;
    // `refresh` asks again.
    loadCableStockPresets(refresh = false) {
        if (this._cableStockPresets && !refresh) return Promise.resolve(this._cableStockPresets);
        return fetch('/api/cable-stock-presets')
            .then(r => r.ok ? r.json() : { presets: [] })
            .then(data => {
                this._cableStockPresets = Array.isArray(data.presets) ? data.presets : [];
                return this._cableStockPresets;
            })
            .catch(() => (this._cableStockPresets = this._cableStockPresets || []));
    }

    cableStockPresets() {
        return this._cableStockPresets || [];
    }

    // The preset called `name` (any case), or null.
    cableStockPreset(name) {
        const key = String(name || '').trim().toLowerCase();
        if (!key) return null;
        return this.cableStockPresets().find(p => String(p.name).toLowerCase() === key) || null;
    }

    saveCableStockPreset(name, stock) {
        const clean = String(name || '').trim();
        if (!clean) return Promise.resolve(null);
        return this._cableStockPresetRequest('PUT',
            { name: clean, stock: this.normalizeCableStock(stock) }, 'Preset not saved');
    }

    deleteCableStockPreset(name) {
        return this._cableStockPresetRequest('DELETE', { name }, 'Preset not deleted');
    }

    // One preset request; a refusal rejects with a sentence that says why
    // (the distro presets' rule, app-distro-systems.js).
    _cableStockPresetRequest(method, payload, failed) {
        return fetch('/api/cable-stock-presets', {
            method, headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).catch(() => {
            throw new Error(`${failed}: the app's server could not be reached.`);
        }).then(r => r.text().then(text => {
            let j = null;
            try { j = JSON.parse(text); } catch (e) { j = null; }
            if (!r.ok || !j || typeof j !== 'object') {
                const why = j && typeof j.error === 'string' && j.error
                    ? j.error : `the server said ${r.status}`;
                throw new Error(`${failed}: ${why}.`);
            }
            this._cableStockPresets = Array.isArray(j.presets) ? j.presets : [];
            return this._cableStockPresets;
        }));
    }

    // The stock a new show starts with: the default preset's, or null.
    defaultCableStock() {
        const prefs = typeof this.getPreferences === 'function' ? this.getPreferences() : {};
        const preset = this.cableStockPreset(prefs.cableStockDefault);
        return preset ? this._storableCableStock(preset.stock) : null;
    }

    // The pristine startup show follows the default preset, as it follows
    // the cable unit: its stock becomes the default's (none when no default
    // is set). Returns true when the show's stock changed; the caller's
    // POST carries it with `keep_pristine`, or `post` sends one here.
    followDefaultCableStock(post = false) {
        if (!this.project) return false;
        const next = this.defaultCableStock();
        const before = this._storableCableStock(this.project.cableStock);
        if (JSON.stringify(next) === JSON.stringify(before)) return false;
        this.project.cableStock = next;
        if (post) {
            fetch('/api/project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cableStock: next, keep_pristine: true }),
            }).catch(() => {});
        }
        return true;
    }

    // ---- the Preferences tab ---------------------------------------------

    _cableStockFieldId(list, unit) {
        return `pref-cable-stock-${list}-${unit}`;
    }

    // The fields from a stock (the show's on open, a preset's on Load).
    fillCableStockUI(stock) {
        const s = this.normalizeCableStock(stock) || this.normalizeCableStock({});
        const per = document.getElementById('pref-cable-stock-per-kind');
        if (per) per.checked = !!s.perKind;
        for (const u of CABLE_UNITS) {
            for (const k of STOCK_LISTS) {
                const el = document.getElementById(this._cableStockFieldId(k, u));
                if (el) el.value = this.jumperStockText(s[u][k]);
            }
        }
        this._syncCableStockRows();
    }

    // The stock the fields hold, each list as "25, 50, 100". A blank
    // field is an empty list; one that is not a list of lengths keeps the
    // show's own list (the jumper ladder's rule, readLadder).
    readCableStockUI() {
        const per = document.getElementById('pref-cable-stock-per-kind');
        const held = this.normalizeCableStock(this.project && this.project.cableStock)
            || this.normalizeCableStock({});
        const out = { perKind: !!(per && per.checked) };
        for (const u of CABLE_UNITS) {
            out[u] = {};
            for (const k of STOCK_LISTS) {
                const el = document.getElementById(this._cableStockFieldId(k, u));
                const text = el ? String(el.value).trim() : '';
                out[u][k] = !text ? [] : (this.parseJumperStockText(text) || held[u][k]);
            }
        }
        return this.normalizeCableStock(out);
    }

    // The fields that hold something that is not a list of lengths.
    _cableStockUnreadable() {
        const bad = [];
        for (const u of CABLE_UNITS) {
            for (const k of STOCK_LISTS) {
                const el = document.getElementById(this._cableStockFieldId(k, u));
                if (el && String(el.value).trim() && !this.parseJumperStockText(el.value)) bad.push(el);
            }
        }
        return bad;
    }

    // One shared list, or a list per kind: the rows the toggle does not
    // use are hidden (their lists are kept, and come back with it).
    _syncCableStockRows() {
        const per = document.getElementById('pref-cable-stock-per-kind');
        const perKind = !!(per && per.checked);
        document.querySelectorAll('#preferences-modal [data-cable-stock-list]').forEach(row => {
            const all = row.dataset.cableStockList === CABLE_STOCK_ALL;
            row.style.display = (all ? !perKind : perKind) ? '' : 'none';
        });
    }

    _sayCableStockStatus(msg) {
        const el = document.getElementById('pref-cable-stock-status');
        if (el) { el.textContent = msg || ''; el.style.display = msg ? '' : 'none'; }
    }

    // The preset picker and the "New shows start with" picker, from the
    // cached presets; `pick` / `def` choose what they show.
    _fillCableStockPresetPickers(pick, def) {
        const presets = this.cableStockPresets();
        const sel = document.getElementById('pref-cable-stock-preset');
        if (sel) {
            const keep = pick !== undefined ? pick : sel.value;
            sel.innerHTML = '';
            const head = document.createElement('option');
            head.value = '';
            head.textContent = presets.length ? 'Pick a preset' : 'No presets saved';
            sel.appendChild(head);
            presets.forEach(p => {
                const o = document.createElement('option');
                o.value = p.name;
                o.textContent = p.name;
                sel.appendChild(o);
            });
            sel.value = presets.some(p => p.name === keep) ? keep : '';
        }
        const dsel = document.getElementById('pref-cable-stock-default');
        if (dsel) {
            const want = def !== undefined ? def : dsel.value;
            dsel.innerHTML = '';
            const none = document.createElement('option');
            none.value = '';
            none.textContent = 'No stock';
            dsel.appendChild(none);
            presets.forEach(p => {
                const o = document.createElement('option');
                o.value = p.name;
                o.textContent = p.name;
                dsel.appendChild(o);
            });
            // A default whose preset is gone still shows, so a Save does
            // not drop it unasked; the server stamps nothing for it.
            if (want && !presets.some(p => p.name === want)) {
                const o = document.createElement('option');
                o.value = want;
                o.textContent = `${want} (not saved)`;
                dsel.appendChild(o);
            }
            dsel.value = want || '';
        }
        this._syncCableStockButtons();
    }

    _syncCableStockButtons() {
        const sel = document.getElementById('pref-cable-stock-preset');
        const picked = !!(sel && sel.value);
        ['pref-cable-stock-load', 'pref-cable-stock-delete'].forEach(id => {
            const b = document.getElementById(id);
            if (b) b.disabled = !picked;
        });
    }

    // Opened with the dialog: the open show's lists, the presets, and the
    // default the preferences hold.
    openCableStockPreferences(prefs) {
        const p = prefs || this.getPreferences();
        this._sayCableStockStatus('');
        this.fillCableStockUI(this.project && this.project.cableStock);
        this._prefsCableStockAtOpen = JSON.stringify(this.readCableStockUI());
        this._fillCableStockPresetPickers('', p.cableStockDefault || '');
        this.loadCableStockPresets(true).then(() => {
            this._fillCableStockPresetPickers(undefined, undefined);
        });
    }

    // On Save: the edited lists go to the open show (one undo step). Lists
    // the dialog opened with and nobody changed leave the show alone, so a
    // Save made for another tab never writes the stock. Returns true when
    // the show's stock changed.
    applyCableStockPreferences() {
        if (this._prefsCableStockAtOpen === undefined) return false;
        const now = this.readCableStockUI();
        const at = this._prefsCableStockAtOpen;
        this._prefsCableStockAtOpen = undefined;
        if (JSON.stringify(now) === at) return false;
        return this.setCableStock(now);
    }

    // Wired once, from setupPreferences.
    setupCableStockPreferences() {
        const per = document.getElementById('pref-cable-stock-per-kind');
        if (per) per.addEventListener('change', () => this._syncCableStockRows());
        const sel = document.getElementById('pref-cable-stock-preset');
        if (sel) sel.addEventListener('change', () => this._syncCableStockButtons());
        const load = document.getElementById('pref-cable-stock-load');
        if (load) {
            load.addEventListener('click', () => {
                const preset = this.cableStockPreset(sel && sel.value);
                if (!preset) return;
                this.fillCableStockUI(preset.stock);
                this._sayCableStockStatus(`Loaded "${preset.name}". Save gives its lengths to this show.`);
            });
        }
        const save = document.getElementById('pref-cable-stock-save-preset');
        if (save) {
            save.addEventListener('click', async () => {
                const bad = this._cableStockUnreadable();
                if (bad.length) {
                    this._sayCableStockStatus('Type each list as lengths with commas between, like 25, 50, 100.');
                    bad[0].focus();
                    return;
                }
                const name = await this.appPrompt('Name this preset', (sel && sel.value) || '',
                    { id: 'cable-stock-preset-name-modal', title: 'Save preset', okLabel: 'Save' });
                if (!name || !name.trim()) return;
                this.saveCableStockPreset(name, this.readCableStockUI()).then(() => {
                    this._fillCableStockPresetPickers(name.trim().replace(/\s+/g, ' '), undefined);
                    this._sayCableStockStatus(`Saved preset "${name.trim()}".`);
                }).catch(err => this._sayCableStockStatus(String(err.message || err)));
            });
        }
        const del = document.getElementById('pref-cable-stock-delete');
        if (del) {
            del.addEventListener('click', async () => {
                const name = sel && sel.value;
                if (!name) return;
                if (!(await this.appConfirm(`Delete the preset "${name}"? `
                        + 'Shows already using its lengths keep them.',
                        { id: 'cable-stock-preset-delete-modal', title: 'Delete preset', okLabel: 'Delete', danger: true }))) return;
                this.deleteCableStockPreset(name).then(() => {
                    this._fillCableStockPresetPickers('', undefined);
                    this._sayCableStockStatus(`Deleted preset "${name}".`);
                }).catch(err => this._sayCableStockStatus(String(err.message || err)));
            });
        }
    }
}

for (const k of Object.getOwnPropertyNames(_CableStock.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_CableStock.prototype, k));
    }
}
