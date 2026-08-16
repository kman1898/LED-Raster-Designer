// app-processors: the Processors panel in the Signal sidebar.
//
// The panel draws a tree - processor, slot, card, breakout box, ports - and
// every level of it earns its place. The CARD is where the port count comes
// from, so the same H9 is a 100-port machine with RJ45 cards and a 160-port
// one with fiber cards; and a fiber card's ports arrive at a breakout box,
// which is the thing a tech is standing in front of when they read a port
// label off it. ("cvt" in ids and endpoints is the stored key, kept stable;
// the generic DEVICE is a breakout box - CVT is one vendor's name for
// theirs, the way Tessera XD is another's, so only actual model names say
// it.)
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

    renderProcessorPanel() {
        const list = document.getElementById('processor-list');
        const addRow = document.getElementById('processor-add-row');
        const note = document.getElementById('processor-empty-note');
        if (!list || !addRow) return;
        this._preserveEditorFocus();
        list.innerHTML = '';
        addRow.innerHTML = '';

        (this._processorsResolved || []).forEach(proc => {
            list.appendChild(this._buildProcessorCard(proc));
        });
        // Every card folds by the section machinery (app-core.js). The
        // rebuild just wiped the wired nodes, so wire the fresh ones and
        // re-apply each machine's stored state - the same call the Power
        // panel's generated headings make after every rebuild.
        if (typeof this._wireSectionCollapse === 'function') {
            this._wireSectionCollapse(list);
        }
        // The set/place chooser acts into a port row. Opened under a folded
        // processor it would sit display:none and the click would look like
        // nothing happened - the stated rule for anything that acts into a
        // hidden place is that the place opens first, same as the distro
        // list's + Add.
        if (this._assigningPort
                && typeof this._expandSectionsFor === 'function') {
            const open = list.querySelector(
                '[data-lrd-field="processor-port-assign-'
                + `${this._assigningPort.cardId}-${this._assigningPort.port}"]`);
            if (open) this._expandSectionsFor(open);
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
            // A backup port consumes a port number; it is never a hidden extra
            // one, so turning this on can only take capacity away.
            label.appendChild(document.createTextNode('Redundancy (halves usable ports)'));
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
        // left blank, every return end is the primary with an R after it, so
        // an empty box still reads as what the backups are actually called.
        // A name typed on ONE port's return end still beats the template.
        names.appendChild(this._buildTextField(
            'Return', card.returnLabelTemplate,
            `${card.portLabelTemplate || '{name}-#'}R`,
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
            // anything while one remains.
            const fits = this._processorDevices('cvt')
                .filter(d => (d.trunksIn || 1) <= card.trunksFree);
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

        (card.cvts || []).forEach(cvt => {
            wrap.appendChild(this._buildCvt(proc, card, cvt));
        });

        wrap.appendChild(this._buildPortList(proc, card));
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
            `${cvt.portLabelTemplate || '{name}-#'}R`,
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
        info.textContent = `ports ${cvt.firstPort}-`
            + `${cvt.firstPort + (cvt.portCount || 0) - 1}`;
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

    _buildPortList(proc, card) {
        const list = document.createElement('div');
        list.style.marginTop = '6px';
        // No height cap and no scrollbar of its own: the SIDEBAR is the one
        // scroll context. A 190px scrollbox here showed two and a half ports
        // of twenty and made every read a scroll-within-a-scroll; the section
        // header folds the whole panel away when the length is unwanted.
        list.style.background = '#0d0d0d';
        list.style.border = '1px solid #262626';
        list.style.borderRadius = '4px';
        list.style.padding = '4px';
        if (!(card.ports || []).length) {
            const empty = document.createElement('div');
            empty.style.fontSize = '11px';
            empty.style.color = '#888';
            empty.textContent = card.ceilingKnown
                ? 'No ports.'
                : 'Port count unknown for this device.';
            list.appendChild(empty);
            return list;
        }
        card.ports.forEach(port => {
            list.appendChild(this._buildPortRow(proc, card, port));
        });
        return list;
    }

    // One of a port row's two name boxes, captioned the way the soca rows'
    // fields are: an unlabeled box beside another unlabeled box reads as
    // noise, and these two hold different ends of the same cable. The
    // resolved label sits in the placeholder, so an empty box still reads as
    // what that end is actually called.
    _buildPortNameField(caption, fieldKey, value, placeholder, manual,
                        titles, onCommit) {
        const cell = document.createElement('div');
        cell.style.flex = '1 1 70px';
        cell.style.minWidth = '0';
        const cap = document.createElement('label');
        cap.style.display = 'block';
        cap.style.fontSize = '10px';
        cap.style.color = '#888';
        cap.textContent = caption;
        cell.appendChild(cap);

        const input = document.createElement('input');
        input.type = 'text';
        input.value = value || '';
        input.placeholder = placeholder || 'unnamed';
        input.title = manual ? titles.named : titles.unnamed;
        input.dataset.lrdField = fieldKey;
        input.style.padding = '0 3px';
        input.style.background = 'transparent';
        input.style.border = '1px solid transparent';
        input.style.borderRadius = '3px';
        input.style.color = manual ? '#e0c98a' : '#ccc';
        input.style.fontFamily = 'monospace';
        input.style.fontSize = '11px';
        input.style.width = '100%';
        input.style.minWidth = '0';
        input.style.boxSizing = 'border-box';
        input.addEventListener('focus', () => {
            input.style.borderColor = '#3a3a3a';
            input.style.background = '#0d0d0d';
        });
        input.addEventListener('blur', () => {
            input.style.borderColor = 'transparent';
            input.style.background = 'transparent';
        });
        input.addEventListener('change', () => onCommit(input.value.trim()));
        cell.appendChild(input);
        return cell;
    }

    _buildPortRow(proc, card, port) {
        const wrap = document.createElement('div');
        const row = document.createElement('div');
        row.style.display = 'grid';
        // Number, occupant, and the button that sets the occupant on the
        // first line; the two name boxes on their own line beneath. The
        // names are inputs rather than text because a port is a socket
        // someone has to be able to call what the house already calls it,
        // and since the processor now beats a screen's own override for an
        // assigned port, these boxes are the ONLY place left to do it.
        // Making it a mode to find would strand every port that needs one.
        row.style.gridTemplateColumns = '22px minmax(0, 1fr) auto';
        row.style.gap = '4px';
        row.style.alignItems = 'center';
        row.style.fontSize = '11px';
        row.style.fontFamily = 'monospace';

        const num = document.createElement('div');
        num.style.color = port.beyondCeiling ? '#d05a52' : '#666';
        num.textContent = String(port.number);
        row.appendChild(num);

        const rename = (body, action) => this._processorRequest(
            `/api/processors/${proc.id}/cards/${card.id}/ports/${port.number}`,
            'PUT', body, action);

        // Two ends of one socket, named side by side. The fields share a
        // wrapping line of their own: two 70px boxes fit abreast at the
        // panel's usual width and stack at its 180px clamp, exactly as the
        // soca rows' captioned fields do. Full row width, not indented under
        // the number column - the nested tree has already spent ~60px of the
        // panel by here, and an indent is the difference between abreast and
        // stacked at every width.
        const names = document.createElement('div');
        names.style.display = 'flex';
        names.style.flexWrap = 'wrap';
        names.style.gap = '4px';
        names.style.margin = '0 0 6px 0';
        names.appendChild(this._buildPortNameField(
            'Name',
            `processor-port-name-${card.id}-${port.number}`,
            (card.portNames || {})[String(port.number)],
            // No name anywhere upstream means no processor-derived label at
            // all, and the screen's own template is still the thing doing
            // the work - which is what "unnamed" has always meant here.
            port.label,
            port.labelSource === 'manual',
            {
                named: 'Named by hand. Clear the box to go back to the '
                    + 'card’s template.',
                unnamed: 'Name this port. It beats the card’s template for '
                    + 'this port only.',
            },
            (val) => rename({ name: val }, 'Rename Processor Port')));
        names.appendChild(this._buildPortNameField(
            'Return',
            `processor-port-return-${card.id}-${port.number}`,
            (card.returnPortNames || {})[String(port.number)],
            port.returnLabel,
            port.returnLabelSource === 'manual',
            {
                named: 'Named by hand. Clear the box to go back to the '
                    + 'primary’s name with an R after it.',
                unnamed: 'Name this port’s redundancy run. Left blank it is '
                    + 'the primary’s name with an R after it.',
            },
            (val) => rename({ returnName: val },
                            'Rename Processor Port Return')));

        const who = document.createElement('div');
        who.style.overflow = 'hidden';
        who.style.textOverflow = 'ellipsis';
        who.style.whiteSpace = 'nowrap';
        const occupants = this._portOccupants(card.id, port.number);
        if (!occupants.length) {
            // A port with nothing on it says so. The panel used to show the
            // label and nothing else, which reads as if no screen were ever on
            // the machine even when six of them are.
            who.style.color = '#4a4a4a';
            who.textContent = 'free';
            who.title = 'No screen is on this port.';
        } else {
            const parts = occupants.map(o => `${o.name} p${o.number}`);
            who.style.color = occupants.length > 1 ? '#d05a52' : '#888';
            who.textContent = parts.join(', ')
                + (occupants.length > 1 ? ' - clash' : '');
            who.title = occupants.length > 1
                ? `${parts.join(' and ')} both claim this port. Nothing has `
                  + 'been renumbered - see Port Assignment.'
                : `${occupants[0].name}, its port ${occupants[0].number}`;
        }
        row.appendChild(who);
        row.appendChild(this._buildPortClaimControl(card, port));
        wrap.appendChild(row);
        wrap.appendChild(names);

        // The chooser opens under its own row, where the ports either side of
        // it are still readable. Which socket is free is decided by looking at
        // the neighbours, and a dialog over the top hides them.
        const open = this._assigningPort;
        if (open && open.cardId === card.id && open.port === port.number) {
            wrap.appendChild(this._buildPortClaimPicker(card, port));
        }
        return wrap;
    }

    // Point at a socket and say what plugs into it.
    //
    // The Port Assignment panel asks the same question from the screen's end -
    // "where did my ports go" - and that was the only end it could be answered
    // from. Anyone holding a patch sheet reads it the other way round: this
    // socket, that wall. It posts the same request the screen-side move does,
    // because it is the same decision written from the far end of one cable.
    _buildPortClaimControl(card, port) {
        const btn = document.createElement('button');
        btn.className = 'btn';
        btn.style.padding = '0 5px';
        btn.style.fontSize = '10px';
        btn.style.background = '#2a2a2a';
        const open = !!(this._assigningPort
            && this._assigningPort.cardId === card.id
            && this._assigningPort.port === port.number);
        btn.textContent = open ? 'close' : 'set';
        const screens = (this._assignment && this._assignment.screens) || [];
        btn.disabled = !screens.length;
        btn.title = screens.length
            ? 'Put a screen’s port on this one. It is held here afterwards, '
              + 'the same as pinning it from the Port Assignment panel.'
            : 'No screen in this project needs a port yet.';
        btn.addEventListener('click', () => {
            this._assigningPort = open
                ? null : { cardId: card.id, port: port.number };
            this.renderProcessorPanel();
        });
        return btn;
    }

    _buildPortClaimPicker(card, port) {
        const box = document.createElement('div');
        box.style.margin = '2px 0 4px 26px';
        box.style.padding = '6px';
        box.style.border = '1px solid #333';
        box.style.borderRadius = '4px';
        box.style.background = '#111';
        box.style.display = 'grid';
        box.style.gap = '4px';

        // One control, grouped by screen: picking the screen and picking which
        // of its ports is one decision, and two selects in a 260px sidebar
        // would be two-thirds chrome. Same reason the device picker groups by
        // vendor rather than asking for the vendor first.
        const choices = [];
        const select = document.createElement('select');
        select.style.fontSize = '10px';
        select.style.width = '100%';
        select.dataset.lrdField =
            `processor-port-assign-${card.id}-${port.number}`;
        ((this._assignment && this._assignment.screens) || []).forEach(scr => {
            const group = document.createElement('optgroup');
            group.label = scr.name;
            (scr.ports || []).forEach(p => {
                const opt = document.createElement('option');
                opt.value = String(choices.length);
                choices.push({ layerId: scr.layerId, index: p.index });
                // Where each port sits now, so nobody has to read the other
                // panel to find out what this would take away from. The
                // derived label already carries the card's name - it is built
                // out of it - so naming the card in front of it would read
                // "SR SR-1"; the card is only spelt out where nothing named
                // the port at all.
                opt.textContent = `p${p.number} - ` + (p.cardId
                    ? `on ${p.label || `${p.cardName} port ${p.port}`}`
                    : 'no card');
                if (p.cardId === card.id && p.port === port.number) {
                    opt.selected = true;
                }
                group.appendChild(opt);
            });
            select.appendChild(group);
        });
        box.appendChild(select);

        const buttons = document.createElement('div');
        buttons.style.display = 'flex';
        buttons.style.gap = '4px';
        const go = document.createElement('button');
        go.className = 'btn';
        go.style.padding = '2px 8px';
        go.style.fontSize = '10px';
        go.textContent = 'Place';
        go.addEventListener('click', () => {
            const pick = choices[parseInt(select.value, 10)];
            // Closed before the request rather than after it: a placement onto
            // an occupied socket comes back as a question, and a chooser still
            // sitting open behind the answer reads as though nothing was sent.
            this._assigningPort = null;
            this.renderProcessorPanel();
            if (pick) {
                this._placePort({ layerId: pick.layerId, index: pick.index,
                                  cardId: card.id, port: port.number });
            }
        });
        const cancel = document.createElement('button');
        cancel.className = 'btn';
        cancel.style.padding = '2px 8px';
        cancel.style.fontSize = '10px';
        cancel.style.background = '#2a2a2a';
        cancel.textContent = 'Cancel';
        cancel.addEventListener('click', () => {
            this._assigningPort = null;
            this.renderProcessorPanel();
        });
        buttons.appendChild(go);
        buttons.appendChild(cancel);
        box.appendChild(buttons);
        return box;
    }
}

for (const k of Object.getOwnPropertyNames(_Processors.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Processors.prototype, k));
    }
}
