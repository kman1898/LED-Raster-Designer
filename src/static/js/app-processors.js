// app-processors: the Processors panel in the Signal sidebar.
//
// The panel draws a tree - processor, slot, card, CVT, ports - and every level
// of it earns its place. The CARD is where the port count comes from, so the
// same H9 is a 100-port machine with RJ45 cards and a 160-port one with fiber
// cards; and a fiber card's ports arrive at a CVT box, which is the thing a
// tech is standing in front of when they read a port label off it.
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

    _processorRequest(url, method, body) {
        return fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body),
        })
            .then(r => r.json())
            .then(data => this._applyProcessorState(data))
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
                                   { deviceId: picker.value });
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

    _buildProcessorCard(proc) {
        const box = document.createElement('div');
        box.style.border = '1px solid #333';
        box.style.borderRadius = '4px';
        box.style.padding = '8px';
        box.style.background = '#111';

        const head = document.createElement('div');
        head.style.display = 'flex';
        head.style.gap = '6px';
        head.style.alignItems = 'flex-end';
        head.appendChild(this._buildTextField(
            proc.deviceName, proc.name, 'unnamed',
            `processor-name-${proc.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}`, 'PUT', { name: val })));
        const del = document.createElement('button');
        del.className = 'btn';
        del.textContent = '×';
        del.title = 'Remove this processor';
        del.style.padding = '6px 10px';
        del.style.background = '#333';
        del.addEventListener('click', () => this._processorRequest(
            `/api/processors/${proc.id}`, 'DELETE'));
        head.appendChild(del);
        box.appendChild(head);

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
        box.appendChild(cap);

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
                `/api/processors/${proc.id}`, 'PUT', { redundancy: cb.checked }));
            label.appendChild(cb);
            // A backup port consumes a port number; it is never a hidden extra
            // one, so turning this on can only take capacity away.
            label.appendChild(document.createTextNode('Redundancy (halves usable ports)'));
            box.appendChild(label);
        }

        (proc.slots || []).forEach(slot => {
            box.appendChild(this._buildSlot(proc, slot));
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
                { deviceId: picker.value || null }));
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

        const names = document.createElement('div');
        names.style.display = 'flex';
        names.style.gap = '6px';
        names.appendChild(this._buildTextField(
            'Card name', card.name, proc.name || 'unnamed',
            `processor-card-name-${card.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                { name: val })));
        names.appendChild(this._buildTextField(
            'Label', card.portLabelTemplate, '{name}-#',
            `processor-card-template-${card.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                { portLabelTemplate: val })));
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
                { mode: select.value || null }));
            wrap.appendChild(select);
        }

        const cap = this._buildCapacityRow(
            card.defined, card.ceiling, card.ceilingKnown, card.ceilingReason);
        cap.style.marginTop = '6px';
        wrap.appendChild(cap);

        // CVTs only where ports actually reach one. A card with no OPT - an
        // H_20xRJ45 - has nothing to hang a box off, and a card whose OPTs are
        // all used has nothing left. Both are hard facts about the metal, so
        // the picker goes away rather than offering something the server will
        // refuse: "cant do 3 or 4 OPTs on a 16 port card, it only has 2".
        if (card.trunks) {
            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.gap = '6px';
            row.style.marginTop = '6px';
            // A box can take more than one OPT - a CVT4K-S is two - so what is
            // offerable is what FITS in the trunks left, not simply anything
            // while one remains.
            const fits = this._processorDevices('cvt')
                .filter(d => (d.trunksIn || 1) <= card.trunksFree);
            const picker = this._buildDeviceSelect(fits, '', 'Add a CVT...');
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
                    { deviceId: picker.value });
            });
            if (fits.length) {
                row.appendChild(picker);
                row.appendChild(btn);
            } else {
                const full = document.createElement('div');
                full.style.fontSize = '11px';
                full.style.color = '#888';
                full.textContent = card.trunksFree
                    ? `Only ${card.trunksFree} OPT left - no box fits it.`
                    : `All ${card.trunks} OPTs are used.`;
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
            wrap.appendChild(this._buildCvt(proc, cvt));
        });

        wrap.appendChild(this._buildPortList(proc, card));
        return wrap;
    }

    _buildCvt(proc, cvt) {
        const wrap = document.createElement('div');
        wrap.style.marginTop = '6px';
        wrap.style.marginLeft = '8px';
        wrap.style.paddingLeft = '8px';
        wrap.style.borderLeft = '2px solid #2a2a2a';

        const head = document.createElement('div');
        head.style.display = 'flex';
        head.style.gap = '6px';
        head.style.alignItems = 'flex-end';
        head.appendChild(this._buildTextField(
            cvt.deviceName, cvt.name, 'unnamed',
            `processor-cvt-name-${cvt.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                { name: val })));
        head.appendChild(this._buildTextField(
            'Label', cvt.portLabelTemplate, '{name}-#',
            `processor-cvt-template-${cvt.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                { portLabelTemplate: val })));
        const del = document.createElement('button');
        del.className = 'btn';
        del.textContent = '×';
        del.title = 'Remove this CVT';
        del.style.padding = '6px 10px';
        del.style.background = '#333';
        del.addEventListener('click', () => this._processorRequest(
            `/api/processors/${proc.id}/cvts/${cvt.id}`, 'DELETE'));
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
        // How many OPTs it eats is as much a fact about the box as how many
        // ports come out of it, and it is the one that decides what else will
        // go on the card.
        if (cvt.trunksIn > 1) info.textContent += `, ${cvt.trunksIn} OPTs in`;
        if (cvt.beyondTrunks) {
            // There is no trunk left to hang it on. Not refused - somebody may
            // be drawing a machine they have not built - but it is the one
            // thing that can push a card past its ceiling, so it says so.
            info.style.color = '#d05a52';
            info.textContent += ' - no trunk left for this box';
        } else if (cvt.duplicateOf) {
            // A backup or copy trunk: the same ports delivered a second time.
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
        list.style.maxHeight = '190px';
        list.style.overflow = 'auto';
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

    _buildPortRow(proc, card, port) {
        const row = document.createElement('div');
        row.style.display = 'grid';
        // Number, name, occupant. The name is an input rather than text
        // because a port is a socket someone has to be able to call what the
        // house already calls it, and since the processor now beats a screen's
        // own override for an assigned port, this box is the ONLY place left
        // to do it. Making it a mode to find would strand every port that
        // needs one.
        row.style.gridTemplateColumns = '22px minmax(0, 1fr) minmax(0, 1fr)';
        row.style.gap = '4px';
        row.style.alignItems = 'center';
        row.style.fontSize = '11px';
        row.style.fontFamily = 'monospace';

        const num = document.createElement('div');
        num.style.color = port.beyondCeiling ? '#d05a52' : '#666';
        num.textContent = String(port.number);
        row.appendChild(num);

        const name = document.createElement('input');
        name.type = 'text';
        name.value = (card.portNames || {})[String(port.number)] || '';
        // The generated label sits in the placeholder, so an empty box still
        // reads as what the port is actually called. No name anywhere upstream
        // means no processor-derived label at all, and the screen's own
        // template is still the thing doing the work - which is what "unnamed"
        // has always meant here.
        name.placeholder = port.label || 'unnamed';
        name.title = port.labelSource === 'manual'
            ? 'Named by hand. Clear the box to go back to the card’s template.'
            : 'Name this port. It beats the card’s template for this port only.';
        name.dataset.lrdField = `processor-port-name-${card.id}-${port.number}`;
        name.style.padding = '0 3px';
        name.style.background = 'transparent';
        name.style.border = '1px solid transparent';
        name.style.borderRadius = '3px';
        name.style.color = port.labelSource === 'manual' ? '#e0c98a' : '#ccc';
        name.style.fontFamily = 'monospace';
        name.style.fontSize = '11px';
        name.style.width = '100%';
        name.style.minWidth = '0';
        name.style.boxSizing = 'border-box';
        name.addEventListener('focus', () => {
            name.style.borderColor = '#3a3a3a';
            name.style.background = '#0d0d0d';
        });
        name.addEventListener('blur', () => {
            name.style.borderColor = 'transparent';
            name.style.background = 'transparent';
        });
        name.addEventListener('change', () => this._processorRequest(
            `/api/processors/${proc.id}/cards/${card.id}/ports/${port.number}`,
            'PUT', { name: name.value.trim() }));
        row.appendChild(name);

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
        return row;
    }
}

for (const k of Object.getOwnPropertyNames(_Processors.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Processors.prototype, k));
    }
}
