// app-processors: the Processors panel in the Signal sidebar.
//
// The panel draws the DEVICE tree - processor, slot, card, breakout box -
// and every level of it earns its place. The CARD is where the port count
// comes from, so the same H9 is a 100-port machine with RJ45 cards and a
// 160-port one with fiber cards; and a fiber card's ports arrive at a
// breakout box, which is the thing a tech is standing in front of when they
// read a port label off it. ("cvt" in ids and endpoints is the stored key,
// kept stable; the generic DEVICE is a breakout box - CVT is one vendor's
// name for theirs, the way Tessera XD is another's, so only actual model
// names say it.)
//
// The PORTS themselves do not draw here. The hardware dock is the one place
// ports appear - the same data twice was two surfaces to read apart - so the
// per-port tiles and their editors live in app-dock.js, and this panel stops
// at the card and its boxes: names, templates, modes, redundancy, capacity.
//
// It deliberately derives nothing. Counts, labels and over-capacity flags all
// come back from /api/processors, which resolves them in processor_catalog.py.
// A second implementation here would agree in the office and disagree on a
// device with a conditional count - H_4xfiber is 32 or 16 by mode, MX40 Pro is
// 40 or 20, a redundant Brompton is half its datasheet - which is exactly the
// class of bug that ends up on site.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _Processors {

    initProcessorPanel() {
        this._processorCatalog = null;
        this._processorsResolved = [];
        this._processorsRaw = '[]';
        // Static asset, not an endpoint: the browser reads the same file the
        // server does, so there is only ever one set of numbers.
        fetch('/static/data/processor_catalog.json')
            .then(r => r.json())
            .then(data => {
                this._processorCatalog = data;
                this.refreshProcessors();
            })
            .catch(err => sendClientLog('processor_catalog_load_failed',
                                        { error: String(err) }));
    }

    refreshProcessors() {
        return fetch('/api/processors')
            .then(r => r.json())
            .then(data => this._applyProcessorState(data))
            .catch(err => sendClientLog('processor_refresh_failed',
                                        { error: String(err) }));
    }

    _applyProcessorState(data) {
        if (!data || !data.resolved) return;
        this._processorsResolved = data.resolved;
        this._processorsRaw = JSON.stringify(data.processors || []);
        // Only stamp the key onto the project once there is something to
        // store. Writing an empty array here would put `processors: []` into
        // every saved file of every user who never opens this panel, and the
        // next save would carry it to the server too.
        if (this.project
                && ((data.processors || []).length || this.project.processors)) {
            this.project.processors = data.processors || [];
        }
        this.renderProcessorPanel();
        // A PROCESSOR EDIT IS A LABEL EDIT. The drawing's port labels come out
        // of the port assignment, and the assignment is resolved against this
        // tree, so naming a card "SR" only reaches the canvas once it has been
        // re-resolved. Doing it here is also what clears the labels when the
        // last processor is deleted - the guard in updateUIFromProject skips
        // the walk for a project with no processors, which is right for every
        // other reason and would leave a deleted machine's names on the wall.
        if (typeof this.refreshPortAssignment === 'function') {
            this.refreshPortAssignment();
        }
    }

    // `action` names the history entry a mutating call earns. Processor edits
    // land on the server first and on this.project.processors only when the
    // response comes back, so the snapshot is taken HERE, after
    // _applyProcessorState has folded the new tree in - the same
    // post-mutation snapshot every other action takes. Taken at the call
    // site it would hold the OLD tree and redo could never re-apply the
    // edit. Reads pass no action; a refused edit changed nothing and gets
    // no entry, or Ctrl+Z would grow no-op steps.
    _processorRequest(url, method, body, action) {
        return fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body),
        })
            .then(r => r.json())
            .then(data => {
                const applied = !!(data && data.resolved);
                this._applyProcessorState(data);
                if (applied && action) this.saveState(action);
                // A refusal carries its reason - a backup unit with the
                // wrong port count, a port that already backs something -
                // and the reason is the answer, so it is shown rather than
                // swallowed. The panel re-renders from its cached state
                // either way, which snaps a refused control back to what is
                // actually stored.
                if (!applied && data && data.error) {
                    if (typeof this._toast === 'function') {
                        this._toast(data.error, true, 6000);
                    }
                    this.renderProcessorPanel();
                }
            })
            .catch(err => sendClientLog('processor_request_failed',
                                        { url, method, error: String(err) }));
    }

    // The panel is rebuilt wholesale on every change, so any field the user is
    // mid-edit in is destroyed under their fingers exactly the way the port
    // label editor's was. Same fix, same keys - see _preserveEditorFocus.
    _processorDevices(kind) {
        const all = (this._processorCatalog && this._processorCatalog.devices) || [];
        return kind ? all.filter(d => d.kind === kind) : all;
    }

    _processorDevice(deviceId) {
        return this._processorDevices().find(d => d.id === deviceId) || null;
    }

    // One presentation rule for "X backs up Y", at whatever level states
    // it: the backup's element joins its main inside one pair wrapper,
    // indented under the role's gold edge, instead of standing as a
    // sibling box - a redundant pair is ONE loom, and four sibling boxes
    // read as four looms. Layout only: the fold and tile machinery inside
    // either element is untouched, and a degenerate file whose "main" sits
    // inside its own backup nests nothing rather than inverting.
    _nestBackupUnder(mainEl, backupEl) {
        if (!mainEl || !backupEl || mainEl === backupEl
                || backupEl.contains(mainEl)) return;
        let pair = mainEl.parentElement;
        if (!pair || !pair.classList.contains('lrd-red-pair')) {
            pair = document.createElement('div');
            pair.className = 'lrd-red-pair';
            mainEl.replaceWith(pair);
            pair.appendChild(mainEl);
        }
        backupEl.classList.add('lrd-red-backup');
        pair.appendChild(backupEl);
    }

    // The unit-level reading of the card-level facts: a processor whose
    // every card is consumed backing cards of ONE other processor is that
    // processor's designated backup unit - the "second sending card"
    // bought to mirror the first - and the pair presents as one group. A
    // unit with any main of its own keeps its own place in the row; its
    // consumed cards still state their role on their own line.
    _backupUnitMainId(proc) {
        const cards = (proc.slots || []).map(s => s.card).filter(Boolean);
        if (!cards.length || !cards.every(c => c.backupFor)) return null;
        const mainId = cards[0].backupFor.processorId;
        if (cards.some(c => c.backupFor.processorId !== mainId)) return null;
        return mainId !== proc.id ? mainId : null;
    }

    renderProcessorPanel() {
        const list = document.getElementById('processor-list');
        const addRow = document.getElementById('processor-add-row');
        const note = document.getElementById('processor-empty-note');
        if (!list || !addRow) return;
        this._preserveEditorFocus();
        list.innerHTML = '';
        addRow.innerHTML = '';

        const procEls = new Map();
        (this._processorsResolved || []).forEach(proc => {
            const el = this._buildProcessorCard(proc);
            procEls.set(proc.id, el);
            list.appendChild(el);
        });
        // A designated backup unit groups under its main - the same
        // presentation the SX40's fixed box pairs get inside a card, one
        // level up. Within a chassis the pairing stays on the cards' own
        // fact lines instead: the slots read in slot order because that IS
        // the allocation order, and regrouping them would make the
        // numbering appear to come from nowhere.
        (this._processorsResolved || []).forEach(proc => {
            const mainId = this._backupUnitMainId(proc);
            if (mainId) {
                this._nestBackupUnder(procEls.get(mainId),
                                      procEls.get(proc.id));
            }
        });
        // Every card folds by the section machinery (app-core.js). The
        // rebuild just wiped the wired nodes, so wire the fresh ones and
        // re-apply each machine's stored state - the same call the Power
        // panel's generated headings make after every rebuild.
        if (typeof this._wireSectionCollapse === 'function') {
            this._wireSectionCollapse(list);
        }
        const picker = this._buildDeviceSelect(
            this._processorDevices('processor'), '', 'Add a processor...');
        picker.dataset.lrdField = 'processor-add-device';
        const addBtn = document.createElement('button');
        addBtn.className = 'btn';
        addBtn.textContent = 'Add';
        addBtn.style.padding = '6px 12px';
        addBtn.addEventListener('click', () => {
            if (!picker.value) return;
            sendClientLog('processor_add_clicked', { deviceId: picker.value });
            this._processorRequest('/api/processors', 'POST',
                                   { deviceId: picker.value },
                                   'Add Processor');
        });
        addRow.appendChild(picker);
        addRow.appendChild(addBtn);

        if (note) {
            note.style.display = (this._processorsResolved || []).length ? 'none' : '';
        }
    }

    // ── builders ──────────────────────────────────────────────────────────

    _buildDeviceSelect(devices, selectedId, placeholder) {
        const select = document.createElement('select');
        select.style.flex = '1';
        select.style.minWidth = '0';
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = placeholder;
        select.appendChild(blank);
        // Grouped by vendor because the list spans three of them and a flat
        // list of forty devices is unreadable in a 260px sidebar.
        const vendors = [];
        devices.forEach(d => {
            if (!vendors.includes(d.vendor)) vendors.push(d.vendor);
        });
        vendors.forEach(vendor => {
            const group = document.createElement('optgroup');
            group.label = vendor;
            devices.filter(d => d.vendor === vendor).forEach(d => {
                const opt = document.createElement('option');
                opt.value = d.id;
                opt.textContent = d.name;
                if (d.id === selectedId) opt.selected = true;
                group.appendChild(opt);
            });
            select.appendChild(group);
        });
        return select;
    }

    _buildTextField(label, value, placeholder, fieldKey, onCommit) {
        const wrap = document.createElement('div');
        wrap.style.flex = '1';
        wrap.style.minWidth = '0';
        const cap = document.createElement('label');
        cap.style.fontSize = '10px';
        cap.style.color = '#888';
        cap.textContent = label;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = value || '';
        input.placeholder = placeholder || '';
        input.dataset.lrdField = fieldKey;
        input.style.fontFamily = 'monospace';
        input.style.boxSizing = 'border-box';
        input.addEventListener('change', () => onCommit(input.value.trim()));
        wrap.appendChild(cap);
        wrap.appendChild(input);
        return wrap;
    }

    // What the Return template box falls back to when left blank, as the
    // rule would print it with # standing for the port number: the primary
    // template rendered with the name the ports actually take, then put
    // through deriveReturnLabel - R1-# for P1, SR-#R for SR, PORT-#R for
    // PORT. With no name anywhere upstream no port derives a label at all,
    // so the template is shown as written ({name}-#R), which is what the
    // rule makes of a primary with no P-prefix.
    _derivedReturnPlaceholder(template, name) {
        const primary = (template || '{name}-#')
            .replace('{name}', (name || '').trim() || '{name}');
        return this.deriveReturnLabel(primary);
    }

    _buildCapacityRow(used, ceiling, known, reason) {
        const row = document.createElement('div');
        row.style.fontSize = '11px';
        row.style.fontFamily = 'monospace';
        if (!known) {
            // A device whose count the sources never settled stays selectable
            // and says so. Substituting a sibling's number here would silently
            // cap a wall, which is the one failure this panel must not have.
            row.style.color = '#c8a04a';
            row.textContent = `${used} ports / ceiling unknown`;
            if (reason) row.title = reason;
            return row;
        }
        const over = used > ceiling;
        row.style.color = over ? '#d05a52' : '#888';
        row.textContent = `${used} / ${ceiling} ports`;
        if (over) row.textContent += ' - over capacity';
        return row;
    }

    // The one line a folded processor is: model, name, and the figures a
    // tech reads at a glance - ports and the redundancy flag. Every number
    // is the resolve's answer, read off the same fields the capacity row
    // prints; deriving a second count here is the class of bug the panel's
    // header comment forbids. Plain text that wraps at the 180px clamp, the
    // way the soca headings do - never a sideways scroll.
    _buildProcessorSummary(proc) {
        const sum = document.createElement('div');
        sum.className = 'lrd-proc-summary';
        const parts = [proc.deviceName];
        if (proc.name) parts.push(proc.name);
        // What the machine DRIVES, read off the same occupancy the port
        // rows print. One processor is often a whole show's worth of
        // screens - an H series most of all - so the mapping is stated,
        // never assumed one-to-one. Two names at most: the folded line
        // wraps at the 180px clamp rather than clipping, and two names is
        // the most that still reads as a glance line there; three or more
        // become a count. A machine with nothing on it says so - an unused
        // box in the rack list is a fact worth seeing.
        const occ = (this._assignment && this._assignment.occupancy) || {};
        const screens = [];
        (proc.slots || []).forEach(slot => {
            if (!slot.card) return;
            Object.values(occ[slot.card.id] || {}).forEach(list => {
                (list || []).forEach(o => {
                    if (!screens.includes(o.name)) screens.push(o.name);
                });
            });
        });
        parts.push(!screens.length ? 'no screens'
            : screens.length <= 2 ? screens.join(', ')
                : `${screens.length} screens`);
        parts.push(proc.ceilingKnown
            ? `${proc.defined}/${proc.ceiling} ports`
            : `${proc.defined} ports`);
        if (proc.redundancy) parts.push('redundant');
        sum.textContent = parts.join(' · ');
        // The capacity row's own comparison: an over-capacity machine may
        // not read as fine just because it is folded.
        if (proc.ceilingKnown && proc.defined > proc.ceiling) {
            sum.style.color = '#d05a52';
            sum.title = 'Over capacity - open the processor for the figures.';
        }
        return sum;
    }

    _buildProcessorCard(proc) {
        const box = document.createElement('div');
        box.style.border = '1px solid #333';
        box.style.borderRadius = '4px';
        box.style.padding = '8px';
        box.style.background = '#111';

        // The head is the fold handle (.lrd-sec-head, wired by
        // _wireSectionCollapse after the render): single click on the arrow,
        // double-click on the head. It also holds the name field, so single
        // clicks stay inert and a double-click landing on the input is the
        // input's - both already the machinery's rules. Folded, the editors
        // give way to the summary line (style.css .lrd-proc-live /
        // .lrd-proc-summary) - hidden, never detached, so the focus-restore
        // keys keep resolving into a folded card.
        const head = document.createElement('div');
        head.className = 'lrd-sec-head';
        // What the fold persists under (ledRasterPanelCollapsed_processor-
        // <id>). Ids never recur within a project, so a machine keeps its
        // state for as long as it exists, and a NEW machine - no key yet -
        // arrives open, which is right: it is about to be configured.
        head.dataset.lrdSec = `processor-${proc.id}`;
        head.style.display = 'flex';
        head.style.gap = '6px';
        head.style.alignItems = 'flex-end';
        const name = this._buildTextField(
            proc.deviceName, proc.name, 'unnamed',
            `processor-name-${proc.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}`, 'PUT', { name: val },
                'Rename Processor'));
        name.classList.add('lrd-proc-live');
        head.appendChild(name);
        const del = document.createElement('button');
        del.className = 'btn lrd-proc-live';
        del.textContent = '×';
        del.title = 'Remove this processor';
        del.style.padding = '6px 10px';
        del.style.background = '#333';
        del.addEventListener('click', () => this._processorRequest(
            `/api/processors/${proc.id}`, 'DELETE', undefined,
            'Remove Processor')
            .then(() => {
                // The machine is gone and its id never comes back, so its
                // fold key goes with it. The other ways a processor leaves
                // (undo of an add, another project loading over this one)
                // just orphan their keys, harmlessly: no later processor in
                // this project can inherit one.
                try {
                    localStorage.removeItem(
                        `ledRasterPanelCollapsed_processor-${proc.id}`);
                } catch (_) { /* blocked storage never held the key */ }
            }));
        head.appendChild(del);
        head.appendChild(this._buildProcessorSummary(proc));
        box.appendChild(head);

        // Everything below the head folds as one body.
        const bodyWrap = document.createElement('div');
        bodyWrap.className = 'lrd-sec-body';
        box.appendChild(bodyWrap);

        const cap = document.createElement('div');
        cap.style.display = 'flex';
        cap.style.justifyContent = 'space-between';
        cap.style.marginTop = '6px';
        cap.appendChild(this._buildCapacityRow(
            proc.defined, proc.ceiling, proc.ceilingKnown, proc.note));
        if (proc.maxCards !== null && proc.maxCards !== undefined
                && proc.form === 'chassis') {
            const cards = document.createElement('div');
            cards.style.fontSize = '11px';
            cards.style.fontFamily = 'monospace';
            cards.style.color = proc.cardsOver ? '#d05a52' : '#888';
            cards.textContent = `${proc.cardsUsed} / ${proc.maxCards} cards`;
            // Documented as max output cards, never as physical slots, and
            // the H9 Enhanced's limit moves with what is in it.
            cards.title = proc.note || '';
            cap.appendChild(cards);
        }
        bodyWrap.appendChild(cap);

        if (proc.redundancySupported) {
            const label = document.createElement('label');
            label.style.display = 'flex';
            label.style.alignItems = 'center';
            label.style.gap = '6px';
            label.style.fontSize = '11px';
            label.style.color = '#ccc';
            label.style.marginTop = '6px';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = !!proc.redundancy;
            cb.dataset.lrdField = `processor-redundancy-${proc.id}`;
            cb.addEventListener('change', () => this._processorRequest(
                `/api/processors/${proc.id}`, 'PUT',
                { redundancy: cb.checked }, 'Toggle Redundancy'));
            label.appendChild(cb);
            // No parenthetical about halving any more: what redundancy costs
            // now depends on the card's mode - 1:1 consumes the backup unit,
            // sequential halves this one, manual takes only what is picked -
            // and each mode states its own cost where it is chosen.
            label.appendChild(document.createTextNode('Redundancy'));
            bodyWrap.appendChild(label);

            // WHERE THE VENDOR FIXES THE PAIRING, IT IS A FACT, NOT A FIELD.
            // Brompton pairs adjacent outputs automatically - A backs up to
            // B, C backs up to D - and offers no other arrangement, so the
            // pairing is stated under the switch and never drawn as a
            // control. The sentence comes from the server (the one authority
            // on the rule); no statement arrives for vendors with none
            // documented, and nothing is invented for them here.
            if (proc.redundancy && proc.redundancyPairing
                    && proc.redundancyPairing.fixed) {
                const fact = document.createElement('div');
                fact.style.fontSize = '11px';
                fact.style.color = '#888';
                fact.style.lineHeight = '1.4';
                fact.style.margin = '2px 0 0 20px';
                fact.textContent = proc.redundancyPairing.statement;
                fact.title = 'Fixed pairing. This is how the device runs '
                    + 'redundancy; it is not a setting.';
                bodyWrap.appendChild(fact);
            }
        }

        (proc.slots || []).forEach(slot => {
            bodyWrap.appendChild(this._buildSlot(proc, slot));
        });
        return box;
    }

    _buildSlot(proc, slot) {
        const wrap = document.createElement('div');
        wrap.style.marginTop = '8px';
        wrap.style.paddingTop = '8px';
        wrap.style.borderTop = '1px solid #262626';

        const isFixed = !!(slot.card && slot.card.fixed);
        if (!isFixed) {
            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.gap = '6px';
            row.style.alignItems = 'center';
            const num = document.createElement('div');
            num.style.fontSize = '11px';
            num.style.color = '#888';
            num.style.fontFamily = 'monospace';
            num.style.minWidth = '38px';
            num.textContent = `Slot ${slot.index + 1}`;
            const device = this._processorDevice(proc.deviceId);
            const accepts = (device && device.accepts) || [];
            const cards = this._processorDevices('card')
                .filter(d => accepts.includes(d.family));
            const picker = this._buildDeviceSelect(
                cards, slot.card ? slot.card.deviceId : '', 'empty');
            picker.dataset.lrdField = `processor-slot-${proc.id}-${slot.index}`;
            picker.addEventListener('change', () => this._processorRequest(
                `/api/processors/${proc.id}/slots/${slot.index}`, 'PUT',
                { deviceId: picker.value || null }, 'Change Slot Card'));
            row.appendChild(num);
            row.appendChild(picker);
            wrap.appendChild(row);
        }
        if (slot.card) wrap.appendChild(this._buildCard(proc, slot.card));
        return wrap;
    }

    _buildCard(proc, card) {
        const wrap = document.createElement('div');
        wrap.style.marginTop = '6px';
        wrap.style.paddingLeft = '8px';
        wrap.style.borderLeft = '2px solid #2a2a2a';

        // Three captioned fields share a wrapping line: the card's name, the
        // primary template, and the RETURN template - "a template spot for
        // naming all backups the same way we do for primary". The wrap is
        // what keeps all three usable at the panel's 180px clamp, exactly as
        // the port rows' name fields wrap below.
        const names = document.createElement('div');
        names.style.display = 'flex';
        names.style.flexWrap = 'wrap';
        names.style.gap = '6px';
        names.appendChild(this._buildTextField(
            'Card name', card.name, proc.name || 'unnamed',
            `processor-card-name-${card.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                { name: val }, 'Rename Card')));
        names.appendChild(this._buildTextField(
            'Label', card.portLabelTemplate, '{name}-#',
            `processor-card-template-${card.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                { portLabelTemplate: val }, 'Edit Card Label Template')));
        // The placeholder is the rung below this one on the return ladder:
        // left blank, every return end derives from its primary, so an empty
        // box still reads as what the backups are actually called - R1-# for
        // a card named P1, SR-#R for one named SR. Rendered off the name the
        // primary actually takes (the card's, or the processor's on loan),
        // because the rule turns on that name's first letter. A name typed
        // on ONE port's return end still beats the template.
        names.appendChild(this._buildTextField(
            'Return', card.returnLabelTemplate,
            this._derivedReturnPlaceholder(card.portLabelTemplate,
                                           card.name || proc.name),
            `processor-card-return-template-${card.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                { returnLabelTemplate: val },
                'Edit Card Return Label Template')));
        names.querySelectorAll(':scope > div').forEach(cell => {
            // A basis, not a bare grow: flex '1' never wraps its line, it
            // only squeezes, and three squeezed fields at 180px are three
            // unusable slivers.
            cell.style.flex = '1 1 90px';
        });
        wrap.appendChild(names);

        // Only offered where the device actually has one. A mode here is a
        // documented output mode - independent vs copy/backup, 20-port vs
        // 40-port - or, on the HELIOS Standard 4K, which document the count
        // came from, because the sources disagree and were not adjudicated.
        if ((card.modes || []).length > 1) {
            const select = document.createElement('select');
            select.style.marginTop = '6px';
            select.dataset.lrdField = `processor-card-mode-${card.id}`;
            const device = this._processorDevice(card.deviceId);
            const conflict = !!(device && device.ports && device.ports.conflict);
            if (conflict) {
                const blank = document.createElement('option');
                blank.value = '';
                blank.textContent = 'sources disagree - pick one';
                blank.selected = !card.mode;
                select.appendChild(blank);
            }
            card.modes.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.count === null
                    ? m.label : `${m.label} - ${m.count} ports`;
                if (m.id === card.mode) opt.selected = true;
                select.appendChild(opt);
            });
            select.addEventListener('change', () => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                { mode: select.value || null }, 'Change Card Mode'));
            wrap.appendChild(select);
        }

        const redundancy = this._buildCardRedundancyRow(proc, card);
        if (redundancy) wrap.appendChild(redundancy);

        const cap = this._buildCapacityRow(
            card.defined, card.ceiling, card.ceilingKnown, card.ceilingReason);
        cap.style.marginTop = '6px';
        wrap.appendChild(cap);

        // Breakout boxes only where ports actually reach one. A card with no
        // trunk - an H_20xRJ45 - has nothing to hang a box off, and a card
        // whose trunks are all used has nothing left. Both are hard facts
        // about the metal, so the picker goes away rather than offering
        // something the server will refuse: "cant do 3 or 4 OPTs on a 16
        // port card, it only has 2".
        if (card.trunks) {
            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.gap = '6px';
            row.style.marginTop = '6px';
            // A box can take more than one trunk - a CVT4K-S is two - so what
            // is offerable is what FITS in the trunks left, not simply
            // anything while one remains. And the trunk's line rate is part
            // of the metal too: a 40G OPT takes the CVT8-5G and nothing
            // else, and the 10G boxes stay off it - so where both rates are
            // documented, only the matching boxes are offered. The server
            // refuses the same mismatch; the picker just stops asking.
            const fits = this._processorDevices('cvt')
                .filter(d => (d.trunksIn || 1) <= card.trunksFree)
                .filter(d => !d.trunkRate || !card.trunkRate
                             || d.trunkRate === card.trunkRate);
            const picker = this._buildDeviceSelect(fits, '',
                                                   'Add a breakout box...');
            picker.dataset.lrdField = `processor-cvt-add-${card.id}`;
            const btn = document.createElement('button');
            btn.className = 'btn';
            btn.textContent = '+';
            btn.style.padding = '6px 12px';
            btn.disabled = !fits.length;
            btn.addEventListener('click', () => {
                if (!picker.value) return;
                this._processorRequest(
                    `/api/processors/${proc.id}/cards/${card.id}/cvts`, 'POST',
                    { deviceId: picker.value }, 'Add Breakout Box');
            });
            if (fits.length) {
                row.appendChild(picker);
                row.appendChild(btn);
            } else {
                const full = document.createElement('div');
                full.style.fontSize = '11px';
                full.style.color = '#888';
                full.textContent = card.trunksFree
                    ? `Only ${card.trunksFree} trunk left - no box fits it.`
                    : `All ${card.trunks} trunks are used.`;
                row.appendChild(full);
            }
            wrap.appendChild(row);

            const trunks = document.createElement('div');
            trunks.style.fontSize = '11px';
            trunks.style.fontFamily = 'monospace';
            trunks.style.marginTop = '4px';
            trunks.style.color = card.trunksUsed > card.trunks ? '#d05a52' : '#888';
            trunks.textContent =
                `${card.trunksUsed} / ${card.trunks} trunks, `
                + `${card.portsPerTrunk} ports each`;
            wrap.appendChild(trunks);

            // "16x RJ45 + 2x fiber, plus a breakout box" reads as if the ports
            // add up. They do not: the OPTs copy Ethernet 1-8 and 9-16, so a
            // box is another place to plug into the same sixteen. Left unsaid,
            // the obvious reading is the wrong one, and it is wrong in the
            // direction that leaves cabinets with nothing to plug into.
            if (card.trunksCopyOwnPorts) {
                const copy = document.createElement('div');
                copy.style.fontSize = '11px';
                copy.style.color = '#c8a04a';
                copy.style.marginTop = '2px';
                copy.style.lineHeight = '1.4';
                copy.textContent = 'The OPTs copy this card’s own ports. '
                    + 'A box on one is another place to plug into them, not '
                    + 'more ports.';
                wrap.appendChild(copy);
            }

            // The BOX decides whether a card reaches its own ceiling, not just
            // the card. Two CVT4K-S boxes eat all four OPTs of an enhanced
            // H_4xfiber and deliver 32 of its 40, because each is 16 out on
            // two OPTs that were carrying 20 - while the identical box is
            // exactly right on a plain H_4xfiber. Left as a bare 32, anyone
            // who knows the card is a 40 assumes the app is wrong. Told why,
            // they change the box; nothing is clamped or swapped for them.
            if (card.shortfall) {
                const short = document.createElement('div');
                short.style.fontSize = '11px';
                short.style.color = '#c8a04a';
                short.style.marginTop = '2px';
                short.style.lineHeight = '1.4';
                const s = card.shortfall;
                short.textContent = `${s.delivered} of ${s.ceiling} ports - `
                    + (s.reachesWith.length
                        ? `this card reaches ${s.ceiling} with `
                          + `${s.reachesWith.join(' or ')}.`
                        : `these boxes cannot reach ${s.ceiling} on this card.`);
                wrap.appendChild(short);
            }
        }

        // A redundant pair of boxes is one group: the backup nests under
        // the box it backs (A with B, C with D on a redundant SX40, and a
        // NovaStar pair likewise) through the same rule the processor list
        // uses for a designated backup unit. Boxes with no role stay the
        // plain siblings they are.
        const cvtEls = new Map();
        (card.cvts || []).forEach(cvt => {
            const el = this._buildCvt(proc, card, cvt);
            cvtEls.set(cvt.id, el);
            const main = cvt.backupOf && cvtEls.get(cvt.backupOf);
            if (main) this._nestBackupUnder(main, el);
            else wrap.appendChild(el);
        });
        // No port grid: the dock is the one place ports appear, editors
        // included (app-dock.js). A second grid here was the same data
        // twice, and the panel's copy is the one that went.
        return wrap;
    }

    _buildCvt(proc, card, cvt) {
        const wrap = document.createElement('div');
        wrap.style.marginTop = '6px';
        wrap.style.marginLeft = '8px';
        wrap.style.paddingLeft = '8px';
        wrap.style.borderLeft = '2px solid #2a2a2a';

        const head = document.createElement('div');
        head.style.display = 'flex';
        head.style.flexWrap = 'wrap';
        head.style.gap = '6px';
        head.style.alignItems = 'flex-end';
        head.appendChild(this._buildTextField(
            cvt.deviceName, cvt.name, 'unnamed',
            `processor-cvt-name-${cvt.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                { name: val }, 'Rename Breakout Box')));
        head.appendChild(this._buildTextField(
            'Label', cvt.portLabelTemplate, '{name}-#',
            `processor-cvt-template-${cvt.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                { portLabelTemplate: val }, 'Edit Breakout Box Label Template')));
        // The box's own backup template, one register up from the per-port
        // Return boxes: a box in front of the card names the ports, so it
        // gets the same return-side template spot the card has.
        head.appendChild(this._buildTextField(
            'Return', cvt.returnLabelTemplate,
            this._derivedReturnPlaceholder(cvt.portLabelTemplate,
                                           cvt.name || card.name || proc.name),
            `processor-cvt-return-template-${cvt.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                { returnLabelTemplate: val },
                'Edit Breakout Box Return Label Template')));
        head.querySelectorAll(':scope > div').forEach(cell => {
            cell.style.flex = '1 1 90px';  // a basis, so the line can wrap
        });
        const del = document.createElement('button');
        del.className = 'btn';
        del.textContent = '×';
        del.title = 'Remove this breakout box';
        del.style.padding = '6px 10px';
        del.style.background = '#333';
        del.addEventListener('click', () => this._processorRequest(
            `/api/processors/${proc.id}/cvts/${cvt.id}`, 'DELETE', undefined,
            'Remove Breakout Box'));
        head.appendChild(del);
        wrap.appendChild(head);

        const info = document.createElement('div');
        info.style.fontSize = '11px';
        info.style.fontFamily = 'monospace';
        info.style.color = '#888';
        info.style.marginTop = '4px';
        // The box's own port count is a maximum, not a promise: it fans out
        // whatever the trunk carries, which is why a CVT10 gives 8 behind an
        // 8B/10B card and why only the first 10 of an XD-S work behind an SX40.
        // The span reads in the box's OWN numbers - every box's face is
        // silkscreened from 1, whichever trunk it hangs on (the 2026-08-27
        // ruling: "all cvt's are 1-10 or 1-16") - so the line says how many
        // sockets work, never where the card's internal ordinals fall.
        info.textContent = cvt.portCount
            ? `ports 1-${cvt.portCount}` : 'no ports delivered';
        // How many trunks it eats is as much a fact about the box as how many
        // ports come out of it, and it is the one that decides what else will
        // go on the card.
        if (cvt.trunksIn > 1) info.textContent += `, ${cvt.trunksIn} trunks in`;
        const backupOfId = cvt.backupOf
            || (card.redundancyPairing ? cvt.duplicateOf : null);
        if (cvt.beyondTrunks) {
            // There is no trunk left to hang it on. Not refused - somebody may
            // be drawing a machine they have not built - but it is the one
            // thing that can push a card past its ceiling, so it says so.
            info.style.color = '#d05a52';
            info.textContent += ' - no trunk left for this box';
        } else if (backupOfId) {
            // A BACKUP UNIT, SAID AS SUCH. Two ways a box earns the line: it
            // was created as a NovaStar primary's backup (backupOf, delete it
            // to decline the default), or it sits on the backup half of a
            // fixed Brompton pair, where being the earlier box's backup is
            // the only thing a second box can be.
            const primary = (card.cvts || [])
                .find(c => c.id === backupOfId);
            const who = primary
                ? (primary.name || primary.deviceName) : 'the primary box';
            info.style.color = '#c8a04a';
            info.textContent += ` - backs up ${who}`;
        } else if (cvt.duplicateOf) {
            // A copy trunk outside any backup pairing: the same ports
            // delivered a second time.
            info.style.color = '#c8a04a';
            info.textContent += ' again (copy)';
        }
        wrap.appendChild(info);
        return wrap;
    }

    // Who is sitting on one card port, as the assignment last resolved it.
    // Read from the resolution rather than worked out here, for the same
    // reason nothing else in this panel is derived: the allocation order and
    // the clashes are port_assignment.py's answer, not a second one.
    _portOccupants(cardId, number) {
        const occ = (this._assignment && this._assignment.occupancy) || {};
        return (occ[cardId] && occ[cardId][String(number)]) || [];
    }

    // Every card of the project except this one, flattened in panel order -
    // the 1:1 partner pick ranges over the whole project because a backup
    // unit is usually a second machine, not a second slot.
    _otherCards(cardId) {
        const out = [];
        (this._processorsResolved || []).forEach(p => {
            (p.slots || []).forEach(slot => {
                const c = slot.card;
                if (c && c.id !== cardId) out.push({ proc: p, card: c });
            });
        });
        return out;
    }

    // The card's data-redundancy row, where redundancy is on and the vendor
    // does not fix the shape. Four modes, the user's design: 1:1 to a
    // designated backup unit (the default - "the way brompton does it and
    // novastar when using a second sending card"), sequential within the
    // unit ("1 is backed up by 2 on the same unit/sending card"), halves
    // within the unit (the 2026-08-27 shape: "1-8 on processor 1 and 9-16
    // as backups"), and manual per port ("1 is backed up to whatever port
    // you want"). A vendor-fixed pairing (Brompton adjacent) renders as the
    // statement under the switch instead, and never as this select.
    _buildCardRedundancyRow(proc, card) {
        // A unit consumed as somebody's 1:1 backup states its role and
        // offers no choices of its own: its ports are the mains' returns,
        // so a mode select here would be a plan for ports that are spoken
        // for. The card itself stays editable - name, templates, boxes -
        // exactly as a NovaStar backup box does.
        if (card.backupFor) {
            const fact = document.createElement('div');
            fact.style.marginTop = '6px';
            fact.style.fontSize = '11px';
            fact.style.color = '#c8a04a';
            fact.textContent = `Backs up ${card.backupFor.title} - its ports `
                + 'carry that unit’s returns.';
            fact.title = 'Picked as the 1:1 backup. Clear the pick on the '
                + 'main unit to free this one.';
            return fact;
        }
        const shape = card.redundancyShape;
        if (!shape || shape.forced) return null;

        const wrap = document.createElement('div');
        wrap.style.marginTop = '6px';

        const select = document.createElement('select');
        select.dataset.lrdField = `processor-card-redundancy-${card.id}`;
        select.style.width = '100%';
        [['1to1', '1:1 - mirrored by a backup unit'],
         ['sequential', 'Sequential - 1 backed by 2, 3 by 4'],
         // The 2026-08-27 arrangement, in the user's own shape: "1-8 on
         // processor 1 and 9-16 as backups" - one gesture, not a manual
         // pick per port.
         ['halves', 'Halves - back half backs the front half'],
         ['manual', 'Manual - backup picked per port'],
        ].forEach(([id, text]) => {
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = text;
            if (id === shape.mode) opt.selected = true;
            select.appendChild(opt);
        });
        select.addEventListener('change', () => this._processorRequest(
            `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
            { redundancyMode: select.value }, 'Change Redundancy Mode'));
        wrap.appendChild(select);

        if (shape.mode === '1to1') {
            // The partner pick. Every other card is offered with its port
            // count in the text, because the count is the eligibility rule -
            // a 1:1 backup mirrors port for port, and the server refuses a
            // mismatch with both counts in the reason.
            const partner = document.createElement('select');
            partner.dataset.lrdField = `processor-card-backup-${card.id}`;
            partner.style.width = '100%';
            partner.style.marginTop = '4px';
            const blank = document.createElement('option');
            blank.value = '';
            blank.textContent = 'backed up by…';
            blank.selected = !card.backupCardId;
            partner.appendChild(blank);
            this._otherCards(card.id).forEach(({ proc: p, card: c }) => {
                const opt = document.createElement('option');
                opt.value = c.id;
                const title = c.name || p.name || c.deviceName;
                const count = c.ceilingKnown ? `${c.ceiling}` : '?';
                let note = '';
                if (c.backupFor && c.id !== card.backupCardId) {
                    note = ` (backs up ${c.backupFor.title})`;
                }
                opt.textContent = `${title} - ${count} ports${note}`;
                if (c.id === card.backupCardId) opt.selected = true;
                partner.appendChild(opt);
            });
            partner.addEventListener('change', () => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                { backupCardId: partner.value }, 'Change Backup Unit'));
            wrap.appendChild(partner);
            if (!card.backupCardId) {
                const hint = document.createElement('div');
                hint.style.fontSize = '11px';
                hint.style.color = '#888';
                hint.style.marginTop = '2px';
                hint.textContent = 'No backup unit picked - nothing is '
                    + 'backed up yet.';
                wrap.appendChild(hint);
            }
        } else if (shape.mode === 'sequential') {
            const info = document.createElement('div');
            info.style.fontSize = '11px';
            info.style.color = '#888';
            info.style.marginTop = '2px';
            info.textContent = card.ceilingKnown && card.ceiling
                ? `1 backed by 2, 3 by 4 - ${shape.usable} of `
                    + `${card.ceiling} ports usable.`
                : '1 backed by 2, 3 by 4 - even ports are the returns.';
            wrap.appendChild(info);
        } else if (shape.mode === 'halves') {
            const info = document.createElement('div');
            info.style.fontSize = '11px';
            info.style.color = '#888';
            info.style.marginTop = '2px';
            if (card.ceilingKnown && card.ceiling) {
                // The same split the server maps: mains are the front
                // ceil(n/2), returns the back floor(n/2) - port 1 comes
                // back on 9 of 16. Both spans named, because this is the
                // one mode whose main and return wear different numbers.
                const mains = card.ceiling - Math.floor(card.ceiling / 2);
                info.textContent = `Ports ${mains + 1}-${card.ceiling} carry `
                    + `the returns of 1-${Math.floor(card.ceiling / 2)} - `
                    + `${shape.usable} of ${card.ceiling} ports usable.`;
            } else {
                info.textContent = 'The back half of the ports are the '
                    + 'front half\'s returns.';
            }
            wrap.appendChild(info);
        } else if (shape.mode === 'manual') {
            const info = document.createElement('div');
            info.style.fontSize = '11px';
            info.style.color = '#888';
            info.style.marginTop = '2px';
            info.textContent = 'Each port picks its backup in its chip on '
                + 'the hardware dock. An unpicked port has no backup.';
            wrap.appendChild(info);
        }
        return wrap;
    }

}

for (const k of Object.getOwnPropertyNames(_Processors.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Processors.prototype, k));
    }
}
