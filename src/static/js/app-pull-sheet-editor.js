// app-pull-sheet-editor: the in-app PULL SHEET editor over the engine's
// list (app-pull-list.js). Ruling (user, 2026-09-06): "edit in the app and
// then export a whole file i can share" - so the list buildPullList()
// recomputes from the show is shown as the user's workbook lays it out
// (positions side by side, Cable Type · Length · Qty · Label · Notes, a
// TOTALS block at the right), and what he changes is stored as deltas in
// project.pullSheetEdits and read back by BOTH exports through
// buildPullSheet().
//
//   * an engine row keeps its type and length (they are what the show
//     says); qty, label and notes edit inline. An edited cell wears a dot
//     and the row a reset (↺); × hides the row, and a "hidden rows" fold at
//     the foot of the position restores it.
//   * "+ Add row" appends a free row whose type and length pickers are fed
//     by the template's GEAR LIST (GET /api/pull-sheet/gear-list) plus
//     whatever the show already uses. Typing a value outside that
//     vocabulary is allowed - the cell warns, never blocks (the README's own
//     rule: the export appends it to the GEAR LIST).
//   * an override on a row the show no longer produces is listed as STALE
//     under its position: kept until forgotten, never exported.
//   * Tab walks qty → label → notes → the next row (the tool buttons are
//     out of the tab order); a commit never rebuilds the row it just left,
//     so focus survives it.
//   * the footer runs the same two exports the export dialog runs, with
//     the edits applied, and Close (from the export dialog's "Edit rows…"
//     it returns there).
//
// Opened from File > Pull Sheet… (data-action="pull-sheet") and from the
// export dialog's Pull Sheet section.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

const FIELDS = ['qty', 'label', 'notes'];

function esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

class _PullSheetEditor {

    // ---- open / close --------------------------------------------------------

    initPullSheetEditor() {
        if (this._pullSheetEditorWired) return;
        this._pullSheetEditorWired = true;
        const modal = document.getElementById('pull-sheet-modal');
        if (!modal) return;
        const on = (id, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', fn);
        };
        on('pull-sheet-close', () => this.closePullSheetEditor());
        on('pull-sheet-export-xlsx', () => this._pullSheetRunExport('pull-sheet'));
        on('pull-sheet-export-binder', () => this._pullSheetRunExport('binder'));
        on('export-pull-sheet-edit-rows', () => {
            const ex = document.getElementById('export-modal');
            if (ex) ex.style.display = 'none';
            this.openPullSheetEditor({ fromExport: true });
        });
        // The board: one delegated listener for every cell and button.
        const board = document.getElementById('pull-sheet-board');
        if (board) {
            board.addEventListener('change', (e) => this._pullSheetOnChange(e));
            board.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT') {
                    e.preventDefault();
                    e.target.blur();
                }
            });
            board.addEventListener('click', (e) => this._pullSheetOnClick(e));
        }
        // Undo / redo while the editor is up: the store moved under the
        // board, so redraw it from the restored project.
        document.addEventListener('keydown', (e) => {
            if (!this.isPullSheetEditorOpen()) return;
            if ((e.metaKey || e.ctrlKey) && String(e.key).toLowerCase() === 'z') {
                setTimeout(() => { if (this.isPullSheetEditorOpen()) this.renderPullSheetEditor(); }, 60);
            }
        });
        modal.addEventListener('click', (e) => {
            if (e.target === modal) this.closePullSheetEditor();
        });
    }

    isPullSheetEditorOpen() {
        const modal = document.getElementById('pull-sheet-modal');
        return !!modal && modal.style.display !== 'none' && modal.style.display !== '';
    }

    async openPullSheetEditor(opts) {
        const modal = document.getElementById('pull-sheet-modal');
        if (!modal || !this.project) return;
        this._pullSheetReturnToExport = !!(opts && opts.fromExport);
        modal.style.display = 'block';
        sendClientLog('pull_sheet_editor_open', { fromExport: this._pullSheetReturnToExport });
        if (typeof this.refreshPortAssignment === 'function') {
            try { await this.refreshPortAssignment(); } catch (_) {}
        }
        this._pullSheetLoadVocab();
        this.renderPullSheetEditor();
    }

    closePullSheetEditor() {
        const modal = document.getElementById('pull-sheet-modal');
        if (modal) modal.style.display = 'none';
        if (this._pullSheetReturnToExport) {
            this._pullSheetReturnToExport = false;
            if (typeof this.openExportModal === 'function') this.openExportModal('pull-sheet');
        }
    }

    // ---- the vocabulary ------------------------------------------------------

    // The template's GEAR LIST, fetched once; the datalists are filled from
    // it plus what the show's own rows say.
    _pullSheetLoadVocab() {
        if (this._pullSheetVocab || this._pullSheetVocabLoading) return;
        this._pullSheetVocabLoading = fetch('/api/pull-sheet/gear-list')
            .then(r => (r.ok ? r.json() : { types: [], lengths: [] }))
            .catch(() => ({ types: [], lengths: [] }))
            .then(v => {
                this._pullSheetVocab = {
                    types: Array.isArray(v.types) ? v.types : [],
                    lengths: Array.isArray(v.lengths) ? v.lengths : [],
                };
                this._pullSheetVocabLoading = null;
                if (this.isPullSheetEditorOpen()) this._pullSheetFillDatalists(this._pullSheetLastList);
            });
    }

    pullSheetVocabulary(list) {
        const v = this._pullSheetVocab || { types: [], lengths: [] };
        const types = [...v.types];
        const lengths = [...v.lengths];
        for (const pos of (list && list.positions) || []) {
            for (const r of pos.rows || []) {
                if (r.type && !types.includes(r.type)) types.push(r.type);
                if (r.length && !lengths.includes(r.length)) lengths.push(r.length);
            }
        }
        return { types, lengths, loaded: !!this._pullSheetVocab };
    }

    _pullSheetFillDatalists(list) {
        const vocab = this.pullSheetVocabulary(list);
        const fill = (id, values) => {
            const dl = document.getElementById(id);
            if (dl) dl.innerHTML = values.map(v => `<option value="${esc(v)}"></option>`).join('');
        };
        fill('pull-sheet-types', vocab.types);
        fill('pull-sheet-lengths', vocab.lengths);
        return vocab;
    }

    // ---- render --------------------------------------------------------------

    renderPullSheetEditor() {
        const board = document.getElementById('pull-sheet-board');
        if (!board || !this.project) return;
        this._circuitTailCache = null;
        const engine = this.buildPullList();
        const sheet = this.applyPullSheetEdits(engine);
        this._pullSheetLastList = engine;
        const vocab = this._pullSheetFillDatalists(engine);
        const edits = this.getPullSheetEdits();
        const stale = this.pullSheetStaleEdits(engine);
        const show = document.getElementById('pull-sheet-show');
        if (show) show.textContent = this.project.name || 'Untitled Project';
        const layers = new Map((this.project.layers || []).map(l => [String(l.id), l]));

        const html = [];
        engine.positions.forEach((pos, i) => {
            const key = this.pullPositionKey(pos);
            const pe = edits.positions[key] || { rows: [], added: [] };
            const edited = sheet.positions[i];
            const screens = (pos.layerIds || []).map(id => (layers.get(String(id)) || {}).name || '').filter(Boolean);
            // A loose screen is its own position: saying its name twice adds nothing.
            const screensText = (screens.length === 1 && screens[0] === pos.name) ? '' : screens.join(', ');
            html.push(`<div class="pull-pos" data-pos="${esc(key)}">`);
            html.push(`<div class="pull-pos-head"><div class="pull-pos-name">${esc(pos.name)}</div>`
                + `<div class="pull-pos-screens">${esc(screensText)}</div></div>`);
            html.push('<table class="pull-table"><thead><tr><th>Cable Type</th><th>Length</th>'
                + '<th class="pull-th-qty">Qty</th><th>Label</th><th>Notes</th><th></th></tr></thead><tbody>');
            const hidden = [];
            for (const r of pos.rows) {
                const rk = this.pullRowKey(r);
                const e = pe.rows.find(x => x.key === rk) || null;
                if (e && e.removed) { hidden.push(r); continue; }
                html.push(this._pullSheetEngineRowHtml(r, e));
            }
            (pe.added || []).forEach((a, idx) => {
                html.push(this._pullSheetAddedRowHtml(a, idx, vocab));
            });
            if (!pos.rows.length && !(pe.added || []).length) {
                html.push('<tr class="pull-empty"><td colspan="6">No cable on this position.</td></tr>');
            }
            html.push('</tbody></table>');
            html.push(`<div class="pull-pos-foot"><button type="button" class="btn pull-add" tabindex="-1">+ Add row</button>`
                + `<span class="pull-pos-count">${edited ? edited.rows.length : 0} rows</span></div>`);
            if (hidden.length) {
                html.push(`<details class="pull-hidden"><summary>Hidden rows (${hidden.length})</summary>`);
                for (const r of hidden) {
                    html.push(`<div class="pull-hidden-row" data-key="${esc(this.pullRowKey(r))}">`
                        + `<span class="pull-hidden-text">${esc(r.type)} · ${esc(r.length || 'EA')} · ${esc(r.qty)}</span>`
                        + '<button type="button" class="btn pull-restore" tabindex="-1">Restore</button></div>');
                }
                html.push('</details>');
            }
            const mine = stale.filter(s => s.positionKey === key);
            if (mine.length) {
                html.push('<div class="pull-stale-list">');
                for (const s of mine) {
                    const [t, l] = s.key.split('|');
                    const what = s.edit.removed ? 'hidden' : FIELDS.filter(f => s.edit[f] !== undefined)
                        .map(f => `${f} ${JSON.stringify(String(s.edit[f]))}`).join(', ');
                    html.push(`<div class="pull-stale" data-key="${esc(s.key)}" title="The show no longer produces this row; the edit is kept but not exported.">`
                        + `<span class="pull-stale-tag">STALE</span><span class="pull-stale-text">${esc(t)} ${esc(l)} · ${esc(what)}</span>`
                        + '<button type="button" class="btn pull-forget" tabindex="-1">Forget</button></div>');
                }
                html.push('</div>');
            }
            html.push('</div>');
        });
        // Stale entries whose whole position is gone (a group dissolved, a
        // screen deleted) still need a home to be forgotten from.
        const orphan = stale.filter(s => !engine.positions.some(p => this.pullPositionKey(p) === s.positionKey));
        if (orphan.length) {
            html.push('<div class="pull-pos pull-pos-orphan" data-pos="">'
                + '<div class="pull-pos-head"><div class="pull-pos-name">Positions no longer in the show</div></div><div class="pull-stale-list">');
            for (const s of orphan) {
                const [t, l] = s.key.split('|');
                html.push(`<div class="pull-stale" data-pos="${esc(s.positionKey)}" data-key="${esc(s.key)}">`
                    + `<span class="pull-stale-tag">STALE</span><span class="pull-stale-text">${esc(t)} ${esc(l)}</span>`
                    + '<button type="button" class="btn pull-forget" tabindex="-1">Forget</button></div>');
            }
            html.push('</div></div>');
        }
        html.push('<div class="pull-pos pull-totals" id="pull-sheet-totals"></div>');
        board.innerHTML = html.join('');
        this.renderPullSheetEditorTotals(sheet);
    }

    _pullSheetEngineRowHtml(r, e) {
        const has = f => !!e && e[f] !== undefined && e[f] !== null;
        const edited = FIELDS.some(has);
        const cell = (f, cls) => {
            // The cell shows the stored override where there is one, the
            // show's own reading otherwise (kept on data-engine for reset).
            const v = has(f) ? e[f] : r[f];
            return `<td class="${has(f) ? 'pull-edited' : ''}">`
                + `<input type="text" class="pull-cell ${cls}" data-field="${f}" value="${esc(v)}"`
                + (f === 'qty' ? ' inputmode="numeric"' : '')
                + ` data-engine="${esc(r[f])}" title="${has(f) ? `The show says ${esc(r[f] === '' ? 'nothing' : r[f])}` : esc(v)}">`
                + '<span class="pull-dot" aria-hidden="true"></span></td>';
        };
        return `<tr class="pull-row${edited ? ' pull-row-edited' : ''}" data-key="${esc(this.pullRowKey(r))}" data-side="${esc(r.side || 'power')}">`
            + `<td class="pull-ro pull-type">${esc(r.type)}</td>`
            + `<td class="pull-ro pull-len">${esc(r.length || '')}</td>`
            + cell('qty', 'pull-qty') + cell('label', 'pull-label') + cell('notes', 'pull-notes')
            + '<td class="pull-tools">'
            + `<button type="button" class="pull-reset" tabindex="-1" title="Reset this row to the show's reading">↺</button>`
            + `<button type="button" class="pull-hide" tabindex="-1" title="Hide this row from the pull sheet">×</button>`
            + '</td></tr>';
    }

    _pullSheetAddedRowHtml(a, idx, vocab) {
        const warnT = vocab.loaded && a.type && !vocab.types.includes(a.type);
        const warnL = vocab.loaded && a.length && !vocab.lengths.includes(a.length);
        const pick = (f, list, v, warn, cls) =>
            `<td class="${warn ? 'pull-warn' : ''}"><input type="text" class="pull-cell ${cls}" data-field="${f}" list="${list}" value="${esc(v)}"`
            + ` title="${warn ? 'Not in the GEAR LIST - the export adds it to the dropdown' : ''}">`
            + '<span class="pull-warn-mark" aria-hidden="true">!</span></td>';
        const cell = (f, cls) => `<td><input type="text" class="pull-cell ${cls}" data-field="${f}" value="${esc(a[f])}"`
            + (f === 'qty' ? ' inputmode="numeric"' : '') + '></td>';
        return `<tr class="pull-row pull-added" data-added-index="${idx}">`
            + pick('type', 'pull-sheet-types', a.type, warnT, 'pull-type-pick')
            + pick('length', 'pull-sheet-lengths', a.length, warnL, 'pull-len-pick')
            + cell('qty', 'pull-qty') + cell('label', 'pull-label') + cell('notes', 'pull-notes')
            + '<td class="pull-tools">'
            + `<button type="button" class="pull-hide" tabindex="-1" title="Remove this added row">×</button>`
            + '</td></tr>';
    }

    // The TOTALS block alone - redrawn after every commit so a qty edit
    // shows its sum at once without rebuilding the row that was edited.
    renderPullSheetEditorTotals(sheet) {
        const el = document.getElementById('pull-sheet-totals');
        if (!el || !this.isPullSheetEditorOpen()) return;
        const list = sheet || this.buildPullSheet();
        const rows = list.totals || [];
        const html = ['<div class="pull-pos-head"><div class="pull-pos-name">TOTALS</div>'
            + `<div class="pull-pos-screens">${list.positions.length} ${list.positions.length === 1 ? 'position' : 'positions'}</div></div>`];
        html.push('<table class="pull-table pull-table-ro"><thead><tr><th>Cable Type</th><th>Length</th>'
            + '<th class="pull-th-qty">Qty</th><th>Label</th></tr></thead><tbody>');
        for (const r of rows) {
            html.push(`<tr><td class="pull-ro pull-type">${esc(r.type)}</td><td class="pull-ro pull-len">${esc(r.length || '')}</td>`
                + `<td class="pull-ro pull-qty-ro">${esc(r.qty)}</td><td class="pull-ro pull-label-ro">${esc(r.label)}</td></tr>`);
        }
        if (!rows.length) html.push('<tr class="pull-empty"><td colspan="4">Nothing to pull.</td></tr>');
        html.push('</tbody></table>');
        const n = rows.reduce((s, r) => s + (Number(r.qty) || 0), 0);
        html.push(`<div class="pull-pos-foot"><span class="pull-pos-count">${rows.length} rows · ${n} pieces</span></div>`);
        el.innerHTML = html.join('');
    }

    // ---- events --------------------------------------------------------------

    _pullSheetRowContext(el) {
        const tr = el.closest('tr.pull-row');
        const posEl = el.closest('.pull-pos');
        return { tr, positionKey: posEl ? posEl.dataset.pos : '' };
    }

    _pullSheetOnChange(e) {
        const input = e.target;
        if (!input || input.tagName !== 'INPUT') return;
        const { tr, positionKey } = this._pullSheetRowContext(input);
        if (!tr || !positionKey) return;
        const field = input.dataset.field;
        if (tr.classList.contains('pull-added')) {
            const idx = parseInt(tr.dataset.addedIndex, 10);
            const patch = {}; patch[field] = input.value;
            this.updatePullSheetAddedRow(positionKey, idx, patch);
            // The store may have normalised the value (a blank qty is 1).
            const pe = this.getPullSheetEdits().positions[positionKey];
            const a = pe && pe.added[idx];
            if (a) {
                input.value = a[field] == null ? '' : a[field];
                if (field === 'type' || field === 'length') {
                    const vocab = this.pullSheetVocabulary(this._pullSheetLastList);
                    const ok = !a[field] || !vocab.loaded
                        || (field === 'type' ? vocab.types : vocab.lengths).includes(a[field]);
                    input.closest('td').classList.toggle('pull-warn', !ok);
                    input.title = ok ? '' : 'Not in the GEAR LIST - the export adds it to the dropdown';
                }
            }
            return;
        }
        const key = tr.dataset.key;
        const engineRow = this._pullSheetEngineRow(positionKey, key);
        const patch = {}; patch[field] = input.value;
        this.setPullSheetRowEdit(positionKey, key, patch, engineRow);
        // Reflect the stored truth back into this row without rebuilding it.
        const pe = this.getPullSheetEdits().positions[positionKey];
        const ed = pe ? pe.rows.find(x => x.key === key) : null;
        for (const f of FIELDS) {
            const cellInput = tr.querySelector(`input[data-field="${f}"]`);
            if (!cellInput) continue;
            const has = !!ed && ed[f] !== undefined && ed[f] !== null;
            cellInput.closest('td').classList.toggle('pull-edited', has);
            const engineV = engineRow ? engineRow[f] : cellInput.dataset.engine;
            cellInput.value = has ? ed[f] : (engineV == null ? '' : engineV);
            cellInput.title = has ? `The show says ${engineV === '' ? 'nothing' : engineV}` : String(cellInput.value || '');
        }
        tr.classList.toggle('pull-row-edited', !!ed && FIELDS.some(f => ed[f] !== undefined && ed[f] !== null));
    }

    _pullSheetEngineRow(positionKey, key) {
        const list = this._pullSheetLastList || this.buildPullList();
        const pos = (list.positions || []).find(p => this.pullPositionKey(p) === positionKey);
        return pos ? (pos.rows.find(r => this.pullRowKey(r) === key) || null) : null;
    }

    _pullSheetOnClick(e) {
        const btn = e.target && e.target.closest('button');
        if (!btn) return;
        const posEl = btn.closest('.pull-pos');
        const positionKey = posEl ? posEl.dataset.pos : '';
        if (btn.classList.contains('pull-add')) {
            if (!positionKey) return;
            const idx = this.addPullSheetRow(positionKey, { type: '', length: '', qty: 1, label: '', notes: '' });
            this.renderPullSheetEditor();
            const row = [...document.querySelectorAll(`.pull-pos[data-pos="${positionKey.replace(/"/g, '\\"')}"] tr.pull-added`)]
                .find(tr => parseInt(tr.dataset.addedIndex, 10) === idx);
            const first = row && row.querySelector('input[data-field="type"]');
            if (first) first.focus();
            return;
        }
        const tr = btn.closest('tr.pull-row');
        if (btn.classList.contains('pull-hide') && tr) {
            if (tr.classList.contains('pull-added')) {
                this.removePullSheetAddedRow(positionKey, parseInt(tr.dataset.addedIndex, 10));
            } else {
                this.removePullSheetRow(positionKey, tr.dataset.key);
            }
            this.renderPullSheetEditor();
            return;
        }
        if (btn.classList.contains('pull-reset') && tr) {
            this.resetPullSheetRow(positionKey, tr.dataset.key);
            this.renderPullSheetEditor();
            return;
        }
        if (btn.classList.contains('pull-restore')) {
            const row = btn.closest('.pull-hidden-row');
            if (row) this.restorePullSheetRow(positionKey, row.dataset.key);
            this.renderPullSheetEditor();
            return;
        }
        if (btn.classList.contains('pull-forget')) {
            const row = btn.closest('.pull-stale');
            const pk = (row && row.dataset.pos) || positionKey;
            if (row) this.resetPullSheetRow(pk, row.dataset.key);
            this.renderPullSheetEditor();
        }
    }

    // ---- the exports ---------------------------------------------------------

    // The same two exports the dialog's confirm button runs, edits applied
    // (they read buildPullSheet). The editor stays up: export, keep editing.
    async _pullSheetRunExport(kind) {
        const status = document.getElementById('status-message');
        const name = (this.project && this.project.name) || 'Project';
        const label = kind === 'binder' ? 'binder' : 'pull sheet';
        if (status) status.textContent = `Exporting ${label}...`;
        try {
            if (kind === 'binder') await this.exportBinder(name);
            else await this.exportPullSheet(name);
            if (status) {
                status.textContent = 'Export complete!';
                setTimeout(() => { status.textContent = 'Ready'; }, 3000);
            }
        } catch (error) {
            console.error(`${label} export error:`, error);
            if (status) status.textContent = 'Export failed!';
            sendClientLog('export_failed', { message: error.message, format: kind, from: 'pull-sheet-editor' });
            if (typeof this._toast === 'function') this._toast(error.message, true, 6000);
        }
    }
}

for (const k of Object.getOwnPropertyNames(_PullSheetEditor.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PullSheetEditor.prototype, k));
    }
}
