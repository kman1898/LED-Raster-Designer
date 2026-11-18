// app-controls: the keys and the 3D mouse as the person has set them, for
// LEDRasterApp (the owner's rulings, 2026-11-18).
//
//   controlMatches(e, id)   is this key press the action's key? Every key
//                           handler asks this instead of naming a key.
//   the Controls tab        Preferences > Controls: every rebindable action
//                           by area, each key a chip to click and record,
//                           Esc cancels a recording, a key in use asks to
//                           swap, Reset per action and Reset all, a search
//                           box, the 3D mouse presets and per action
//                           buttons, and the fixed keys listed.
//   the labels              Help > Keyboard Shortcuts, the menus' printed
//                           keys and every tooltip that names a key say
//                           the person's keys.
//
// The keys live in the Preferences record (preferences.controls), saved
// with the dialog's Save like every other tab: per person, never with the
// show. The registry, the matching and the names are controls.js.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

const C = () => window.Controls;

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g,
    ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));

// The menu items whose printed key is an action's (data-action -> id).
const MENU_CONTROLS = {
    open: 'open', save: 'save', 'export-png': 'exportPng', 'export-psd': 'exportPsd',
    preferences: 'preferences', undo: 'undo', redo: 'redo', copy: 'copy', paste: 'paste',
    duplicate: 'duplicate', 'prev-port': 'prevPort', 'next-port': 'nextPort',
    fit: 'fitToView', 'actual-size': 'zoomToSelection', 'toggle-snap': 'toggleSnap',
    delete: 'deleteScreen',
};

// A recording takes every key first: on the window, capturing, registered
// as this module loads, so ahead of every handler the app adds later
// (Esc closing Preferences, the 3D view's keys, the canvas's shortcuts).
if (typeof window !== 'undefined') {
    window.addEventListener('keydown', (e) => {
        const app = window.app;
        if (!app || !app._controlsRecording) return;
        app._controlsRecordKey(e);
    }, true);
    window.addEventListener('mousedown', (e) => {
        const app = window.app;
        const rec = app && app._controlsRecording;
        if (!rec || (rec.chip && rec.chip.contains(e.target))) return;
        app._controlsStopRecording('');
    }, true);
}

class _Controls {
    // ── reading what is set ───────────────────────────────────────────────

    // The person's controls record: read straight off the cached
    // preferences, since every key press asks.
    controlsSet() {
        const sp = this._serverPreferences;
        if (sp && Object.keys(sp).length > 0) return sp.controls || null;
        try {
            return (JSON.parse(localStorage.getItem('appPreferences') || '{}') || {}).controls || null;
        } catch (_) {
            return null;
        }
    }

    _controlsMac() {
        return typeof this._isMacPlatform === 'function' && this._isMacPlatform();
    }

    controlMatches(e, id) {
        const lib = C();
        return !!(lib && e && lib.matches(e, id, this.controlsSet(), this._controlsMac()));
    }

    controlKeys(id) {
        return C().keysFor(this.controlsSet(), id);
    }

    // The action's keys in words ('Ctrl+Z'; two keys 'Delete or
    // Backspace'; none 'no key').
    controlKeyText(id, set) {
        const keys = C().keysFor(set === undefined ? this.controlsSet() : set, id);
        if (!keys.length) return 'no key';
        return keys.map(k => C().format(k, this._controlsMac())).join(' or ');
    }

    controlMouseMap() {
        return C().mouseMap(this.controlsSet());
    }

    // ── the labels: menus, tooltips, the 3D hint ─────────────────────────

    // A tooltip written with {key:<id>} where it names a key: the
    // person's key goes in.
    controlTipText(el) {
        const tpl = el.getAttribute('data-control-tip') || '';
        return tpl.replace(/\{key:([A-Za-z0-9]+)\}/g, (m, id) => this.controlKeyText(id));
    }

    refreshControlLabels() {
        if (!C() || typeof document === 'undefined') return;
        document.querySelectorAll('[data-control-tip]').forEach(el => {
            el.setAttribute('data-tooltip', this.controlTipText(el));
        });
        if (typeof this.updateShortcutLabels === 'function') this.updateShortcutLabels();
        this._controlsRefreshHint();
    }

    // The printed key of a menu item: the template's own while the action
    // keeps its shipped keys (the words the menus always printed), else
    // the person's first key. Null: the item names no action.
    controlMenuShortcut(option, isMac) {
        const id = MENU_CONTROLS[option.getAttribute('data-action')];
        const tpl = option.getAttribute(isMac ? 'data-shortcut-mac' : 'data-shortcut-win');
        if (!id || !C()) return tpl;
        const set = this.controlsSet();
        if (C().isDefault(set, id)) return tpl;
        const keys = C().keysFor(set, id);
        return keys.length ? C().format(keys[0], isMac) : null;
    }

    // The 3D view's corner hint and its tooltip say the mouse as set; the
    // Standard preset keeps the words the template has.
    _controlsRefreshHint() {
        const hint = document.getElementById('s3d-hint');
        if (!hint) return;
        if (hint.dataset.shippedText === undefined) {
            hint.dataset.shippedText = hint.textContent;
            hint.dataset.shippedTip = hint.getAttribute('data-tooltip') || '';
        }
        const map = this.controlMouseMap();
        if (map.preset === 'standard' && !map.custom) {
            hint.textContent = hint.dataset.shippedText;
            hint.setAttribute('data-tooltip', hint.dataset.shippedTip);
            return;
        }
        const g = this._controlsMouseWords(map);
        hint.textContent = `${g.orbit} orbits, ${g.pan} pans, ${g.zoom} zooms. Trackpad: two fingers orbit, pinch zooms.`;
        const mac = this._controlsMac();
        hint.setAttribute('data-tooltip', `Getting around, ${g.orbit} orbits; ${g.pan} pans; `
            + `${g.zoom} zooms, and the wheel and a trackpad pinch always zoom toward the cursor. `
            + 'On a trackpad, drag with two fingers to orbit and add Shift to pan. '
            + `${g.select} selects a screen, with Shift or ${mac ? 'Cmd' : 'Ctrl'} to add one; `
            + `${g.box} across empty space box-selects; ${g.move} on a selected screen moves it. `
            + 'Right-click, or Control+click on a Mac, opens the screen menu. The arrow keys nudge the '
            + 'selection, Page Up and Page Down raise and lower it, and Shift makes the step bigger. '
            + 'Preferences > Controls sets the mouse; Help > Keyboard Shortcuts lists every gesture.');
    }

    // Each 3D mouse action in words ('Middle-drag', 'Shift+drag', 'Wheel').
    _controlsMouseWords(map) {
        const mac = this._controlsMac();
        const out = {};
        C().MOUSE_ACTIONS.forEach(a => {
            out[a.id] = C().mouseName(map.actions[a.id], mac, a.id === 'select' ? 'click' : 'drag');
        });
        if (out.zoom !== 'Wheel' && out.zoom !== 'Not set') out.zoom = `${out.zoom} or the wheel`;
        else out.zoom = 'the wheel';
        return out;
    }

    // ── Help > Keyboard Shortcuts ─────────────────────────────────────────

    // A chord as the modal writes it: the command key in a [data-sc-mod]
    // span (the modal's rule), the rest as text.
    _controlChordHtml(chord, mac) {
        const lib = C();
        const parts = lib.format(chord, mac).split('+');
        const hasMod = chord.split('+')[0] === 'mod';
        return parts.map((p, i) => (hasMod && i === 0
            ? `<span data-sc-mod>${esc(p)}</span>` : esc(p))).join('+');
    }

    // Every key cell that names actions ([data-sc-control="a b"]) says the
    // person's keys; a cell whose actions all keep their shipped keys
    // keeps the template's words. The 3D section's mouse rows follow the
    // mouse map the same way.
    fillShortcutsHelp(modal) {
        if (!modal || !C()) return;
        const set = this.controlsSet();
        const mac = this._controlsMac();
        modal.querySelectorAll('[data-sc-control]').forEach(cell => {
            if (cell.dataset.shipped === undefined) cell.dataset.shipped = cell.innerHTML;
            const ids = cell.getAttribute('data-sc-control').split(/\s+/).filter(Boolean);
            if (ids.every(id => C().isDefault(set, id))) {
                cell.innerHTML = cell.dataset.shipped;
                return;
            }
            const one = ids.length === 1;
            cell.innerHTML = ids.map(id => {
                const keys = C().keysFor(set, id);
                if (!keys.length) return 'no key';
                return keys.map(k => this._controlChordHtml(k, mac)).join(one ? ' / ' : ', ');
            }).join(' / ');
        });
        const rows = modal.querySelector('[data-sc-mouse-rows]');
        if (rows) {
            if (rows.dataset.shipped === undefined) rows.dataset.shipped = rows.innerHTML;
            const map = C().mouseMap(set);
            if (map.preset === 'standard' && !map.custom) {
                rows.innerHTML = rows.dataset.shipped;
            } else {
                const g = this._controlsMouseWords(map);
                const row = (k, v) => `<tr><td class="sc-key">${esc(k)}</td><td>${esc(v)}</td></tr>`;
                rows.innerHTML = [
                    row(g.orbit, map.actions.orbit.button === 'left' && map.actions.orbit.mod === 'none'
                        ? 'Orbit around the middle of the view (from empty space)' : 'Orbit the view'),
                    row(g.pan, 'Pan the view'),
                    row('Scroll wheel / pinch', 'Zoom toward the cursor'
                        + (map.actions.zoom.button !== 'wheel' && map.actions.zoom.button !== 'none'
                            ? `; ${g.zoom.replace(/ or the wheel$/, '')} zooms too` : '')),
                    row('Two-finger drag / Shift+two-finger drag', 'Orbit / pan on a trackpad'),
                    row(g.select + ' a screen', 'Select it; with Shift or ' + (mac ? 'Cmd' : 'Ctrl') + ' it adds or takes out'),
                    row(g.box + ' across empty space', 'Box-select the screens it touches'),
                    row(g.move + ' a selected screen', 'Move it across the floor; with Shift, up or down'),
                    row('Right-click (Control+click on a Mac)', 'Open the screen menu'),
                ].join('');
            }
        }
    }

    // ── the Controls tab ──────────────────────────────────────────────────

    // Called by fillPreferencesUI: the tab edits a copy (the draft) until
    // the dialog's Save.
    fillControlsTab(controls) {
        this._controlsDraft = C().clone(controls);
        this._controlsStopRecording('');
        this._controlsNote('');
        this._controlsRender();
    }

    // What Save stores.
    readControlsTab() {
        return C().clone(this._controlsDraft);
    }

    setupControlsTab() {
        const search = document.getElementById('pref-controls-search');
        if (search) search.addEventListener('input', () => this._controlsFilter());
        const all = document.getElementById('pref-controls-reset-all');
        if (all) all.addEventListener('click', () => this._controlsResetAll());
        const list = document.getElementById('pref-controls-list');
        if (!list) return;
        list.addEventListener('click', (e) => {
            const t = e.target.closest('button');
            if (!t || !list.contains(t)) return;
            if (t.classList.contains('pm-key-chip')) {
                this._controlsStartRecording(t.dataset.control, Number(t.dataset.index), t);
            } else if (t.classList.contains('pm-key-add')) {
                this._controlsStartRecording(t.dataset.control, -1, t);
            } else if (t.classList.contains('pm-key-remove')) {
                const id = t.dataset.control;
                const keys = C().keysFor(this._controlsDraft, id);
                keys.splice(Number(t.dataset.index), 1);
                this._controlsSet(C().withKeys(this._controlsDraft, id, keys));
                this._controlsNote('');
            } else if (t.classList.contains('pm-control-reset')) {
                this._controlsReset(t.dataset.control, t.dataset.mouse);
            }
        });
        list.addEventListener('change', (e) => {
            const t = e.target;
            if (t.id === 'pref-controls-preset') {
                this._controlsSet(C().withPreset(this._controlsDraft, t.value));
                sendClientLog('controls_preset', { preset: t.value });
                this._controlsNote('');
            } else if (t.dataset && t.dataset.mouse) {
                this._controlsMouseChange(t.dataset.mouse);
            }
        });
    }

    _controlsSet(draft) {
        this._controlsDraft = draft;
        this._controlsRender();
    }

    _controlsNote(text) {
        const el = document.getElementById('pref-controls-note');
        if (!el) return;
        el.textContent = text || '';
        el.hidden = !text;
    }

    _controlsRender() {
        const list = document.getElementById('pref-controls-list');
        if (!list || !C()) return;
        const lib = C();
        const draft = this._controlsDraft || lib.empty();
        const mac = this._controlsMac();
        const scroll = list.scrollTop;
        const html = [];
        lib.AREAS.forEach(area => {
            const acts = lib.ACTIONS.filter(a => a.area === area);
            if (!acts.length) return;
            html.push(`<div class="pm-controls-area" data-area="${esc(area)}"><h4>${esc(area)}</h4>`);
            acts.forEach(a => {
                const keys = lib.keysFor(draft, a.id);
                const chips = keys.map((k, i) => {
                    const name = lib.format(k, mac);
                    return `<span class="pm-key"><button type="button" class="pm-key-chip" data-control="${a.id}" data-index="${i}" `
                        + `title="Click, then press the new key for ${esc(a.label)}">${esc(name)}</button>`
                        + `<button type="button" class="pm-key-remove" data-control="${a.id}" data-index="${i}" `
                        + `aria-label="Remove ${esc(name)} from ${esc(a.label)}" title="Remove ${esc(name)}">&times;</button></span>`;
                }).join('');
                const none = keys.length ? '' : '<span class="pm-key-none">No key</span>';
                const shipped = lib.formatList(a.keys, mac);
                const dflt = lib.isDefault(draft, a.id);
                html.push(`<div class="pm-control-row" data-control="${a.id}" data-search="${esc((a.label + ' ' + area + ' ' + keys.map(k => lib.format(k, mac)).join(' ')).toLowerCase())}">`
                    + `<span class="pm-control-label">${esc(a.label)}</span>`
                    + `<span class="pm-control-keys">${chips}${none}`
                    + `<button type="button" class="pm-key-add" data-control="${a.id}" aria-label="Add a key for ${esc(a.label)}" title="Add another key">+</button></span>`
                    + `<button type="button" class="btn pm-control-reset" data-control="${a.id}"${dflt ? ' disabled' : ''} `
                    + `title="Back to ${esc(shipped || 'no key')}">Reset</button></div>`);
            });
            html.push('</div>');
        });
        // The 3D mouse and trackpad: a preset, then each action.
        const map = lib.mouseMap(draft);
        const names = lib.modNames(mac);
        const presetOpts = Object.keys(lib.PRESETS).map(k =>
            `<option value="${k}"${map.preset === k ? ' selected' : ''}>${esc(lib.PRESETS[k].label)}</option>`).join('');
        html.push('<div class="pm-controls-area" data-area="3D mouse"><h4>3D mouse and trackpad</h4>');
        html.push('<div class="pm-control-row" data-search="3d mouse trackpad preset standard orbit first">'
            + '<span class="pm-control-label">Preset</span><span class="pm-control-keys">'
            + `<select id="pref-controls-preset" aria-label="3D mouse preset">${presetOpts}</select>`
            + `<span class="pm-controls-hint">${map.preset === 'orbitFirst'
                ? 'A drag on empty space orbits; Shift+drag draws the box.'
                : 'Middle-drag orbits, right-drag pans, a left drag draws the box.'}</span>`
            + '</span><span></span></div>');
        lib.MOUSE_ACTIONS.forEach(a => {
            const v = map.actions[a.id];
            const buttons = (a.id === 'zoom' ? ['wheel'] : []).concat(['left', 'middle', 'right', 'none']);
            const bLabel = { wheel: 'Wheel', left: 'Left button', middle: 'Middle button', right: 'Right button', none: 'Not set' };
            const bOpts = buttons.map(x => `<option value="${x}"${v.button === x ? ' selected' : ''}>${bLabel[x]}</option>`).join('');
            const mLabel = { none: 'No key', shift: names.shift, alt: names.alt, mod: names.mod };
            const mOpts = lib.MODS.map(x => `<option value="${x}"${v.mod === x ? ' selected' : ''}>${esc(mLabel[x])}</option>`).join('');
            const pv = lib.PRESETS[map.preset].actions[a.id];
            const dflt = pv.button === v.button && pv.mod === v.mod;
            const words = lib.mouseName(v, mac, a.id === 'select' ? 'click' : 'drag');
            html.push(`<div class="pm-control-row" data-mouse-row="${a.id}" data-search="${esc(('3d mouse ' + a.label + ' ' + words).toLowerCase())}">`
                + `<span class="pm-control-label">${esc(a.label)}</span><span class="pm-control-keys">`
                + `<select data-mouse="${a.id}" data-part="button" aria-label="${esc(a.label)} button">${bOpts}</select>`
                + `<select data-mouse="${a.id}" data-part="mod" aria-label="${esc(a.label)} key"${v.button === 'wheel' || v.button === 'none' ? ' disabled' : ''}>${mOpts}</select>`
                + '</span>'
                + `<button type="button" class="btn pm-control-reset" data-mouse="${a.id}"${dflt ? ' disabled' : ''} `
                + `title="Back to the preset: ${esc(lib.mouseName(pv, mac, a.id === 'select' ? 'click' : 'drag'))}">Reset</button></div>`);
        });
        html.push('<div class="pm-controls-fine">The wheel and a trackpad pinch always zoom, and two fingers on a trackpad orbit. A tablet or phone keeps its touch gestures.</div>');
        html.push('</div>');
        // The fixed keys, so nobody looks for them here in vain.
        html.push('<div class="pm-controls-area" data-area="Fixed"><h4>Fixed keys</h4>'
            + '<div class="pm-controls-fine">These work the same everywhere and are not changed here.</div>');
        lib.FIXED.forEach(f => {
            html.push(`<div class="pm-control-row pm-control-fixed" data-search="${esc(('fixed ' + f.keys + ' ' + f.what).toLowerCase())}">`
                + `<span class="pm-control-label">${esc(f.what)}</span>`
                + `<span class="pm-control-keys"><span class="pm-key-fixed">${esc(f.keys)}</span></span><span></span></div>`);
        });
        html.push('</div>');
        list.innerHTML = html.join('');
        list.scrollTop = scroll;
        this._controlsFilter();
    }

    // The search box: rows whose action, area or key holds every word.
    _controlsFilter() {
        const box = document.getElementById('pref-controls-search');
        const list = document.getElementById('pref-controls-list');
        if (!list) return;
        const words = String(box ? box.value : '').toLowerCase().split(/\s+/).filter(Boolean);
        let shown = 0;
        list.querySelectorAll('.pm-controls-area').forEach(area => {
            let any = false;
            area.querySelectorAll('.pm-control-row').forEach(row => {
                const hay = row.getAttribute('data-search') || '';
                const ok = words.every(w => hay.includes(w));
                row.hidden = !ok;
                if (ok) any = true;
            });
            area.hidden = !any;
            if (any) shown++;
        });
        let empty = list.querySelector('.pm-controls-empty');
        if (!shown) {
            if (!empty) {
                empty = document.createElement('div');
                empty.className = 'pm-controls-empty';
                list.appendChild(empty);
            }
            empty.textContent = 'Nothing matches. Try another word or a key, like Ctrl.';
        } else if (empty) {
            empty.remove();
        }
    }

    // ── recording a key ───────────────────────────────────────────────────

    _controlsStartRecording(id, index, chip) {
        if (!C().action(id)) return;
        this._controlsStopRecording('');
        this._controlsRecording = { id, index, chip };
        chip.classList.add('recording');
        chip.dataset.was = chip.textContent;
        chip.textContent = 'Press a key';
        chip.focus();
        this._controlsNote(`Press the new key for ${C().action(id).label}. Esc cancels.`);
    }

    _controlsStopRecording(note) {
        const rec = this._controlsRecording;
        this._controlsRecording = null;
        if (rec && rec.chip && rec.chip.isConnected) {
            rec.chip.classList.remove('recording');
            if (rec.chip.dataset.was !== undefined) rec.chip.textContent = rec.chip.dataset.was;
        }
        if (note !== undefined && rec) this._controlsNote(note);
    }

    // Every key goes here while recording, and no further: Esc cancels, a
    // modifier on its own waits for the key, a key the browser or the app
    // keeps is refused with a note, a key in use asks to swap.
    _controlsRecordKey(e) {
        e.preventDefault();
        e.stopImmediatePropagation();
        if (e.repeat || e.isComposing) return;
        const rec = this._controlsRecording;
        const lib = C();
        const mac = this._controlsMac();
        if (e.key === 'Escape' || e.code === 'Escape') {
            if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                this._controlsStopRecording('');
                return;
            }
        }
        const chord = lib.fromEvent(e, mac);
        if (!chord) return;   // a modifier on its own: wait for the key
        const why = lib.refusal(chord, mac);
        if (why) {
            sendClientLog('controls_refused', { id: rec.id, chord });
            this._controlsStopRecording(why);
            return;
        }
        this._controlsStopRecording('');
        this._controlsAssign(rec.id, rec.index, chord);
    }

    // Put `chord` on action `id` (in place of key `index`, or added when
    // -1). A key another action has asks first, in the app's own dialog:
    // Yes moves it (the other action loses it), No changes nothing.
    async _controlsAssign(id, index, chord) {
        const lib = C();
        const mac = this._controlsMac();
        const draft = this._controlsDraft;
        const mine = lib.keysFor(draft, id);
        if (mine.includes(chord)) {
            this._controlsNote(`${lib.format(chord, mac)} is already ${lib.action(id).label}.`);
            return;
        }
        let next = draft;
        const taken = lib.conflicts(draft, id, chord);
        if (taken.length) {
            const others = taken.map(t => lib.action(t).label).join(' and ');
            const yes = await this.appConfirm(
                `${lib.format(chord, mac)} is already ${others}. Use it here and clear ${others}?`,
                { id: 'controls-swap-modal', title: 'Key in use', okLabel: 'Yes', cancelLabel: 'No' });
            sendClientLog('controls_swap', { id, chord, taken, yes });
            if (!yes) {
                this._controlsNote('');
                return;
            }
            taken.forEach(t => {
                next = lib.withKeys(next, t, lib.keysFor(next, t).filter(k => k !== chord));
            });
        }
        const keys = lib.keysFor(next, id);
        if (index >= 0 && index < keys.length) keys[index] = chord;
        else keys.push(chord);
        next = lib.withKeys(next, id, keys);
        sendClientLog('controls_set', { id, chord });
        this._controlsSet(next);
        this._controlsNote(`${lib.action(id).label}: ${lib.formatList(lib.keysFor(next, id), mac)}. Save keeps it.`);
    }

    _controlsReset(id, mouseId) {
        const lib = C();
        if (mouseId) {
            this._controlsSet(lib.withMouse(this._controlsDraft, mouseId, null));
            this._controlsNote('');
            return;
        }
        const a = lib.action(id);
        if (!a) return;
        // Its shipped keys come back: any other action holding one of them
        // where this one acts lets it go, so no key ends up doing two things.
        let next = this._controlsDraft;
        a.keys.forEach(k => {
            lib.conflicts(next, id, k).forEach(t => {
                next = lib.withKeys(next, t, lib.keysFor(next, t).filter(x => x !== k));
            });
        });
        next = lib.withKeys(next, id, null);
        this._controlsSet(next);
        this._controlsNote(`${a.label} is back to ${lib.formatList(a.keys, this._controlsMac())}.`);
    }

    async _controlsResetAll() {
        const yes = await this.appConfirm('Put every key and the 3D mouse back to their defaults?',
            { id: 'controls-reset-all-modal', title: 'Reset all controls', okLabel: 'Reset all' });
        if (!yes) return;
        this._controlsSet(C().empty());
        this._controlsNote('Every control is back to its default. Save keeps it.');
        sendClientLog('controls_reset_all', {});
    }

    async _controlsMouseChange(id) {
        const lib = C();
        const list = document.getElementById('pref-controls-list');
        const sel = (part) => list.querySelector(`select[data-mouse="${id}"][data-part="${part}"]`);
        const button = sel('button').value;
        const mod = button === 'wheel' || button === 'none' ? 'none' : sel('mod').value;
        const binding = { button, mod };
        const mac = this._controlsMac();
        let next = this._controlsDraft;
        const taken = lib.mouseConflicts(next, id, binding);
        if (taken.length) {
            const label = (x) => lib.MOUSE_ACTIONS.find(a => a.id === x).label;
            const others = taken.map(label).join(' and ');
            const yes = await this.appConfirm(
                `${lib.mouseName(binding, mac, 'drag')} is already ${others}. Use it here and clear ${others}?`,
                { id: 'controls-swap-modal', title: 'Already in use', okLabel: 'Yes', cancelLabel: 'No' });
            if (!yes) {
                this._controlsRender();
                return;
            }
            taken.forEach(t => { next = lib.withMouse(next, t, { button: 'none', mod: 'none' }); });
        }
        sendClientLog('controls_mouse', { id, binding });
        this._controlsSet(lib.withMouse(next, id, binding));
        this._controlsNote('');
    }
}

for (const k of Object.getOwnPropertyNames(_Controls.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Controls.prototype, k));
    }
}
