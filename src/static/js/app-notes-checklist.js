// app-notes-checklist: the show to-do checklist under the free-text notes in
// the Notes panel. project.notesChecklist = [{ id, text, done }], in order;
// a project without it has an empty list and loads unchanged.
//
// Every edit (add, tick, text, remove, reorder) writes the list onto the
// project and records one history step, so Ctrl+Z walks it like any other
// edit. The server copy and the other clients follow through ONE path:
// whenever the list drawn differs from the list last known to be on the
// server, the new list goes to PUT /api/project/notes-checklist, which
// stores it and broadcasts `notes_checklist_updated`. That catches undo,
// redo and a file load as well as the edits, without each of them knowing
// about the checklist. A broadcast from another client is adopted as the
// server's list, so it is never sent back.
//
// Rows are reconciled by id rather than rebuilt, so a row being typed in or
// clicked keeps its element (and its focus) through a redraw.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

const NOTES_CHECKLIST_MAX_TEXT = 500;

class _NotesChecklist {
    _notesChecklistItems() {
        const list = this.project && this.project.notesChecklist;
        return Array.isArray(list) ? list : [];
    }

    // One id per page, so this window can skip its own broadcast.
    _notesChecklistOrigin() {
        if (!this._notesChecklistOriginId) {
            this._notesChecklistOriginId = 'nc' + Date.now().toString(36)
                + Math.random().toString(36).slice(2, 8);
        }
        return this._notesChecklistOriginId;
    }

    _notesChecklistNewId() {
        const taken = new Set(this._notesChecklistItems().map(i => i.id));
        let id;
        do {
            id = 'ck' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
        } while (taken.has(id));
        return id;
    }

    // ---- the edits ----------------------------------------------------------

    addNotesChecklistItem(text = '') {
        if (!this.project) return null;
        const item = { id: this._notesChecklistNewId(), text: String(text).slice(0, NOTES_CHECKLIST_MAX_TEXT), done: false };
        this._notesChecklistCommit([...this._notesChecklistItems(), item], 'Add Checklist Item');
        return item;
    }

    setNotesChecklistDone(id, done) {
        const items = this._notesChecklistItems();
        const item = items.find(i => i.id === id);
        if (!item || item.done === !!done) return;
        this._notesChecklistCommit(items.map(i => (i.id === id ? { ...i, done: !!done } : i)),
            done ? 'Check Checklist Item' : 'Uncheck Checklist Item');
    }

    setNotesChecklistText(id, text) {
        const items = this._notesChecklistItems();
        const item = items.find(i => i.id === id);
        const clean = String(text == null ? '' : text).slice(0, NOTES_CHECKLIST_MAX_TEXT);
        if (!item || item.text === clean) return;
        this._notesChecklistCommit(items.map(i => (i.id === id ? { ...i, text: clean } : i)),
            'Edit Checklist Item');
    }

    removeNotesChecklistItem(id) {
        const items = this._notesChecklistItems();
        if (!items.some(i => i.id === id)) return;
        this._notesChecklistCommit(items.filter(i => i.id !== id), 'Remove Checklist Item');
    }

    // `id` lands at `index` of the list as it stands without it.
    moveNotesChecklistItem(id, index) {
        const items = this._notesChecklistItems();
        const item = items.find(i => i.id === id);
        if (!item) return;
        const rest = items.filter(i => i.id !== id);
        const at = Math.max(0, Math.min(rest.length, Number(index) || 0));
        rest.splice(at, 0, item);
        if (rest.every((i, n) => i === items[n])) return;
        this._notesChecklistCommit(rest, 'Reorder Checklist');
    }

    _notesChecklistCommit(items, action) {
        if (!this.project) return;
        this.project.notesChecklist = items;
        this._notesChecklistRender();
        if (typeof this.saveState === 'function') this.saveState(action);
        sendClientLog('notes_checklist_edit', { action, items: items.length });
    }

    // ---- the server and the other clients ----------------------------------

    // Sends the list drawn now when it is not what the server last had.
    // Sends run one at a time and each reads the list when it goes, so two
    // quick edits can never land on the server in the wrong order.
    _notesChecklistSync() {
        if (!this.project) return;
        const now = JSON.stringify(this._notesChecklistItems());
        if (this._notesChecklistServer === undefined) {
            // First draw after boot: the list came from the server.
            this._notesChecklistServer = now;
            return;
        }
        if (now === this._notesChecklistServer) return;
        this._notesChecklistServer = now;
        const send = () => {
            const body = JSON.stringify({
                items: this._notesChecklistItems(),
                origin: this._notesChecklistOrigin(),
            });
            return fetch('/api/project/notes-checklist', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body,
            }).catch(err => {
                sendClientLog('notes_checklist_sync_failed', { message: String(err && err.message || err) });
            });
        };
        this._notesChecklistChain = (this._notesChecklistChain || Promise.resolve()).then(send, send);
    }

    _notesChecklistAdopt(data) {
        if (!data || !this.project) return;
        if (data.origin && data.origin === this._notesChecklistOrigin()) return;
        const items = Array.isArray(data.items) ? data.items : [];
        this.project.notesChecklist = items;
        this._notesChecklistServer = JSON.stringify(items);
        this._notesChecklistRender();
    }

    // ---- the panel ----------------------------------------------------------

    // Bound once, from _wireProjectChrome (app-wiring.js).
    _notesChecklistWire() {
        if (this._notesChecklistWired) return;
        const host = document.getElementById('notes-checklist-list');
        const addBtn = document.getElementById('notes-checklist-add');
        if (!host || !addBtn) return;
        this._notesChecklistWired = true;

        addBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const item = this.addNotesChecklistItem('');
            if (!item) return;
            const input = host.querySelector(`.notes-checklist-row[data-item-id="${item.id}"] .notes-checklist-text`);
            if (input) input.focus();
        });

        host.addEventListener('change', (e) => {
            const row = e.target.closest('.notes-checklist-row');
            if (!row) return;
            const id = row.dataset.itemId;
            if (e.target.classList.contains('notes-checklist-done')) {
                this.setNotesChecklistDone(id, e.target.checked);
            } else if (e.target.classList.contains('notes-checklist-text')) {
                this.setNotesChecklistText(id, e.target.value.trim());
            }
        });
        host.addEventListener('keydown', (e) => {
            // Esc puts the text back the way it was and lets go. Enter is the
            // app's one rule (helpers.js installEnterEndsEdit): it commits and
            // lets go, and adds no row.
            if (e.key !== 'Escape' || !e.target.classList.contains('notes-checklist-text')) return;
            const row = e.target.closest('.notes-checklist-row');
            const item = row && this._notesChecklistItems().find(i => i.id === row.dataset.itemId);
            if (item) e.target.value = item.text;
            e.target.blur();
        });
        host.addEventListener('click', (e) => {
            const btn = e.target.closest('.notes-checklist-remove');
            if (!btn) return;
            const row = btn.closest('.notes-checklist-row');
            if (row) this.removeNotesChecklistItem(row.dataset.itemId);
        });
        // A focused row skipped a value update while it was being typed in;
        // once it lets go, the list is drawn again.
        host.addEventListener('focusout', () => {
            setTimeout(() => this._notesChecklistRender(), 0);
        });
        this._notesChecklistWireDrag(host);

        if (this.socket && typeof this.socket.on === 'function') {
            this.socket.on('notes_checklist_updated', (data) => this._notesChecklistAdopt(data));
        }
        this._notesChecklistRender();
    }

    // Drag a row by its handle; it drops before or after the row under the
    // pointer, by which half the pointer is in. The row is draggable only
    // while its handle is held, so dragging across the text still selects.
    _notesChecklistWireDrag(host) {
        const clearMarks = () => host.querySelectorAll('.drop-before, .drop-after')
            .forEach(el => el.classList.remove('drop-before', 'drop-after'));
        host.addEventListener('mousedown', (e) => {
            const handle = e.target.closest('.notes-checklist-handle');
            if (!handle) return;
            const row = handle.closest('.notes-checklist-row');
            if (row) row.draggable = true;
        });
        host.addEventListener('mouseup', (e) => {
            const row = e.target.closest('.notes-checklist-row');
            if (row && !this._notesChecklistDragId) row.draggable = false;
        });
        host.addEventListener('dragstart', (e) => {
            const row = e.target.closest && e.target.closest('.notes-checklist-row');
            if (!row || !row.draggable) return;
            this._notesChecklistDragId = row.dataset.itemId;
            row.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', `checklist:${row.dataset.itemId}`);
        });
        host.addEventListener('dragover', (e) => {
            if (!this._notesChecklistDragId) return;
            const row = e.target.closest('.notes-checklist-row');
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            clearMarks();
            if (!row || row.dataset.itemId === this._notesChecklistDragId) return;
            const r = row.getBoundingClientRect();
            row.classList.add(e.clientY < r.top + r.height / 2 ? 'drop-before' : 'drop-after');
        });
        host.addEventListener('dragleave', (e) => {
            if (!host.contains(e.relatedTarget)) clearMarks();
        });
        host.addEventListener('drop', (e) => {
            const dragged = this._notesChecklistDragId;
            if (!dragged) return;
            e.preventDefault();
            const row = e.target.closest('.notes-checklist-row');
            clearMarks();
            if (!row || row.dataset.itemId === dragged) return;
            const r = row.getBoundingClientRect();
            const after = e.clientY >= r.top + r.height / 2;
            const rest = this._notesChecklistItems().filter(i => i.id !== dragged);
            const at = rest.findIndex(i => i.id === row.dataset.itemId);
            if (at < 0) return;
            this.moveNotesChecklistItem(dragged, after ? at + 1 : at);
        });
        host.addEventListener('dragend', () => {
            this._notesChecklistDragId = null;
            clearMarks();
            host.querySelectorAll('.notes-checklist-row').forEach(row => {
                row.draggable = false;
                row.classList.remove('dragging');
            });
        });
    }

    _notesChecklistRow(item) {
        const row = document.createElement('div');
        row.className = 'notes-checklist-row';
        row.dataset.itemId = item.id;
        const handle = document.createElement('span');
        handle.className = 'notes-checklist-handle';
        handle.title = 'Drag to reorder';
        handle.textContent = '⋮⋮';
        const box = document.createElement('input');
        box.type = 'checkbox';
        box.className = 'notes-checklist-done';
        box.title = 'Done';
        const text = document.createElement('input');
        text.type = 'text';
        text.className = 'notes-checklist-text';
        text.placeholder = 'To do';
        text.maxLength = NOTES_CHECKLIST_MAX_TEXT;
        text.dataset.lrdField = `notes-checklist-${item.id}`;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'notes-checklist-remove';
        remove.title = 'Remove this item';
        remove.textContent = '×';
        row.append(handle, box, text, remove);
        return row;
    }

    // Draws the list from the project (updateUI calls this on every load,
    // undo and redo), then sends it on if the server does not have it yet.
    _notesChecklistRender() {
        const host = document.getElementById('notes-checklist-list');
        if (!host) return;
        const items = this._notesChecklistItems();
        const existing = new Map();
        host.querySelectorAll(':scope > .notes-checklist-row').forEach(row => existing.set(row.dataset.itemId, row));
        const keep = new Set();
        items.forEach((item, index) => {
            let row = existing.get(item.id);
            if (!row) row = this._notesChecklistRow(item);
            keep.add(row);
            const box = row.querySelector('.notes-checklist-done');
            const text = row.querySelector('.notes-checklist-text');
            box.checked = !!item.done;
            // Never pull the text out from under the person typing it.
            if (document.activeElement !== text && text.value !== item.text) text.value = item.text || '';
            row.classList.toggle('done', !!item.done);
            // Move a row only when it is out of place: moving the focused
            // row would take the focus away.
            if (host.children[index] !== row) host.insertBefore(row, host.children[index] || null);
        });
        Array.from(host.children).forEach(el => { if (!keep.has(el)) el.remove(); });
        const title = document.querySelector('#notes-checklist .notes-checklist-title');
        if (title) {
            const done = items.filter(i => i.done).length;
            title.textContent = items.length ? `Checklist ${done}/${items.length}` : 'Checklist';
        }
        this._notesChecklistSync();
    }
}

for (const k of Object.getOwnPropertyNames(_NotesChecklist.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_NotesChecklist.prototype, k));
    }
}
