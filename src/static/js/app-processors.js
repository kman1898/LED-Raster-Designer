// app-processors: the processor device tree and its editors, all of which
// live on the hardware dock now (the Signal sidebar this used to panel in
// is retired).
//
// The tree is processor -> slot -> card -> breakout box -> port, and every
// level of it earns its place. The CARD is where the port count comes
// from, so the same H9 is a 100-port machine with RJ45 cards and a
// 160-port one with fiber cards; and a fiber card's ports arrive at a
// breakout box, which is the thing a tech is standing in front of when they
// read a port label off it. ("cvt" in ids and endpoints is the stored key,
// kept stable; the generic DEVICE is a breakout box - CVT is one vendor's
// name for theirs, the way Tessera XD is another's, so only actual model
// names say it.)
//
// What this module owns is the STATE side - the catalog, the resolve
// round-trips, the request/refusal/undo discipline - plus the content of
// each level's ⚙ gear popover (templates, modes, redundancy, capacity,
// boxes, removal). The dock (app-dock.js) draws the tree itself: section
// headers carry the names inline, chips carry the ports.
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
            // The counter travels with the tree it numbers, so undo
            // snapshots carry it and the restore PUT cannot reset it - a
            // dropped counter handed retired ids back out (see _state's
            // note in routes_processors.py). Guarded the same way as the
            // tree itself: never stamped onto a project with no processors.
            if (data.next_processor_seq != null) {
                this.project.next_processor_seq = data.next_processor_seq;
            }
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

    // The Processors panel died with the Signal sidebar. The dock is the
    // one processor surface now - the header bar carries the add picker,
    // the section headers carry the names inline, and each level's gear
    // popover carries the configuration this panel used to draw - so a
    // processor render IS a dock render. Kept under its old name because
    // every "the tree changed" path already calls it.
    renderProcessorPanel() {
        if (typeof this.renderHardwareDock === 'function') {
            this.renderHardwareDock();
        }
    }

    // ── builders ──────────────────────────────────────────────────────────

    // Fill a select with the device list, grouped by vendor because the
    // list spans three of them and a flat list of forty devices is
    // unreadable at popover width. Shared by the dock header's add picker
    // (a static element refilled in place) and the popovers' own selects.
    _fillDeviceSelect(select, devices, selectedId, placeholder) {
        select.innerHTML = '';
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = placeholder;
        select.appendChild(blank);
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

    _buildDeviceSelect(devices, selectedId, placeholder) {
        const select = document.createElement('select');
        select.style.flex = '1';
        select.style.minWidth = '0';
        return this._fillDeviceSelect(select, devices, selectedId,
                                      placeholder);
    }

    _buildTextField(label, value, placeholder, fieldKey, onCommit) {
        const wrap = document.createElement('div');
        wrap.style.flex = '1';
        wrap.style.minWidth = '0';
        const cap = document.createElement('label');
        cap.style.fontSize = '10px';
        cap.style.color = 'var(--ps-dim, #c0c0c0)';
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
        row.style.color = over ? '#d05a52' : 'var(--ps-dim, #c0c0c0)';
        row.textContent = `${used} / ${ceiling} ports`;
        if (over) row.textContent += ' - over capacity';
        return row;
    }

    // ── the gear popovers ─────────────────────────────────────────────────
    //
    // What the retired panel's cards carried, re-hosted behind each dock
    // header's ⚙ (app-dock.js owns the popover shell and its open/close
    // idiom; these only build the content). Same fields, same
    // data-lrd-field keys, same requests and history actions - the popover
    // is presentation over the same state, and _preserveEditorFocus finds
    // the keys wherever the popover is anchored. The NAMES are not here:
    // they edit inline on the dock headers themselves.

    _popHeading(text) {
        const h = document.createElement('div');
        h.className = 'hw-pop-heading';
        h.textContent = text;
        return h;
    }

    _popRemoveButton(label, title, onRun) {
        const btn = document.createElement('button');
        btn.className = 'btn hw-pop-remove';
        btn.textContent = label;
        btn.title = title;
        btn.addEventListener('click', () => {
            // The thing the popover describes is about to stop existing,
            // so the popover goes first - a panel over a ghost would
            // re-render into nothing.
            if (typeof this._hwPopoverClose === 'function') {
                this._hwPopoverClose();
            }
            onRun();
        });
        return btn;
    }

    // The processor's gear: the machine-level facts and switches - capacity,
    // the redundancy toggle with its vendor-fixed pairing statement, the
    // chassis slots' card pickers, and the remove.
    _buildProcGearContent(proc) {
        const wrap = document.createElement('div');
        wrap.appendChild(this._popHeading(proc.name || proc.deviceName));

        const cap = document.createElement('div');
        cap.style.display = 'flex';
        cap.style.justifyContent = 'space-between';
        cap.style.gap = '8px';
        cap.appendChild(this._buildCapacityRow(
            proc.defined, proc.ceiling, proc.ceilingKnown, proc.note));
        if (proc.maxCards !== null && proc.maxCards !== undefined
                && proc.form === 'chassis') {
            const cards = document.createElement('div');
            cards.style.fontSize = '11px';
            cards.style.fontFamily = 'monospace';
            cards.style.color = proc.cardsOver ? '#d05a52' : 'var(--ps-dim, #c0c0c0)';
            cards.textContent = `${proc.cardsUsed} / ${proc.maxCards} cards`;
            // Documented as max output cards, never as physical slots, and
            // the H9 Enhanced's limit moves with what is in it.
            cards.title = proc.note || '';
            cap.appendChild(cards);
        }
        wrap.appendChild(cap);

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
            wrap.appendChild(label);

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
                fact.style.color = 'var(--ps-dim, #c0c0c0)';
                fact.style.lineHeight = '1.4';
                fact.style.margin = '2px 0 0 20px';
                fact.textContent = proc.redundancyPairing.statement;
                fact.title = 'Fixed pairing. This is how the device runs '
                    + 'redundancy; it is not a setting.';
                wrap.appendChild(fact);
            }
        }

        // The chassis's slots: which card sits in each. A fixed card (an
        // all-in-one's own outputs) is a fact, not a pick, so it draws no
        // row - its configuration lives behind the card's own gear.
        (proc.slots || []).forEach(slot => {
            if (slot.card && slot.card.fixed) return;
            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.gap = '6px';
            row.style.alignItems = 'center';
            row.style.marginTop = '6px';
            const num = document.createElement('div');
            num.style.fontSize = '11px';
            num.style.color = 'var(--ps-dim, #c0c0c0)';
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
        });

        wrap.appendChild(this._popRemoveButton(
            'Remove processor',
            'Remove this processor. Its cards, boxes and every port on them '
            + 'go with it; undo puts it back.',
            () => this._processorRequest(
                `/api/processors/${proc.id}`, 'DELETE', undefined,
                'Remove Processor')
                .then(() => {
                    // The machine is gone and its id never comes back, so
                    // its fold keys go with it - the dock's card and box
                    // sections fold under their own ids, which die with the
                    // machine too. The other ways a processor leaves (undo
                    // of an add, another project loading over this one)
                    // just orphan their keys, harmlessly: no later
                    // processor in this project can inherit one.
                    try {
                        (proc.slots || []).forEach(slot => {
                            const card = slot.card;
                            if (!card) return;
                            localStorage.removeItem(
                                'ledRasterPanelCollapsed_hwdock-card-'
                                + card.id);
                            (card.cvts || []).forEach(cvt => {
                                localStorage.removeItem(
                                    'ledRasterPanelCollapsed_hwdock-box-'
                                    + cvt.id);
                            });
                        });
                    } catch (_) { /* blocked storage never held the keys */ }
                })));
        return wrap;
    }

    // The card's gear: templates, mode, redundancy shape, capacity, and the
    // breakout-box work - everything the panel's card block carried except
    // the name, which edits inline on the card's dock header.
    _buildCardGearContent(proc, card) {
        const wrap = document.createElement('div');
        wrap.appendChild(this._popHeading(card.name || card.deviceName));

        // The two template fields share a wrapping line, the same reason
        // the old panel wrapped them: at popover width two fields fit
        // abreast and a third would sliver all of them.
        const names = document.createElement('div');
        names.style.display = 'flex';
        names.style.flexWrap = 'wrap';
        names.style.gap = '6px';
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
            cell.style.flex = '1 1 90px';   // a basis, so the line can wrap
        });
        wrap.appendChild(names);

        // Only offered where the device actually has one. A mode here is a
        // documented output mode - independent vs copy/backup, 20-port vs
        // 40-port - or, on the HELIOS Standard 4K, which document the count
        // came from, because the sources disagree and were not adjudicated.
        if ((card.modes || []).length > 1) {
            const select = document.createElement('select');
            select.style.marginTop = '6px';
            select.style.width = '100%';
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
                full.style.color = 'var(--ps-dim, #c0c0c0)';
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
            trunks.style.color = card.trunksUsed > card.trunks ? '#d05a52' : 'var(--ps-dim, #c0c0c0)';
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

        // A slotted card is removed by emptying its slot - the same PUT the
        // slot picker sends, offered here so a card is removable where it
        // is configured. A fixed card is the machine's own outputs and has
        // no removal; the machine's gear carries that one.
        const slot = (proc.slots || [])
            .find(s => s.card && s.card.id === card.id);
        if (slot && !card.fixed) {
            wrap.appendChild(this._popRemoveButton(
                'Remove card',
                'Empty this slot. The card, its boxes and every port on '
                + 'them go with it; undo puts it back.',
                () => this._processorRequest(
                    `/api/processors/${proc.id}/slots/${slot.index}`, 'PUT',
                    { deviceId: null }, 'Change Slot Card')));
        }
        return wrap;
    }

    // The breakout box's gear: its templates, its facts, its removal. The
    // name edits inline on the box's dock header.
    _buildBoxGearContent(proc, card, cvt) {
        const wrap = document.createElement('div');
        wrap.appendChild(this._popHeading(
            cvt.displayTitle || cvt.name || cvt.deviceName));

        const names = document.createElement('div');
        names.style.display = 'flex';
        names.style.flexWrap = 'wrap';
        names.style.gap = '6px';
        names.appendChild(this._buildTextField(
            'Label', cvt.portLabelTemplate, '{name}-#',
            `processor-cvt-template-${cvt.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                { portLabelTemplate: val },
                'Edit Breakout Box Label Template')));
        // The box's own backup template, one register up from the per-port
        // Return boxes: a box in front of the card names the ports, so it
        // gets the same return-side template spot the card has.
        names.appendChild(this._buildTextField(
            'Return', cvt.returnLabelTemplate,
            this._derivedReturnPlaceholder(cvt.portLabelTemplate,
                                           cvt.name || card.name || proc.name),
            `processor-cvt-return-template-${cvt.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                { returnLabelTemplate: val },
                'Edit Breakout Box Return Label Template')));
        names.querySelectorAll(':scope > div').forEach(cell => {
            cell.style.flex = '1 1 90px';   // a basis, so the line can wrap
        });
        wrap.appendChild(names);

        const info = document.createElement('div');
        info.style.fontSize = '11px';
        info.style.fontFamily = 'monospace';
        info.style.color = 'var(--ps-dim, #c0c0c0)';
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

        wrap.appendChild(this._popRemoveButton(
            'Remove box',
            'Remove this breakout box. Its sockets go with it; undo puts '
            + 'it back.',
            () => this._processorRequest(
                `/api/processors/${proc.id}/cvts/${cvt.id}`, 'DELETE',
                undefined, 'Remove Breakout Box')
                .then(() => {
                    try {
                        localStorage.removeItem(
                            `ledRasterPanelCollapsed_hwdock-box-${cvt.id}`);
                    } catch (_) { /* blocked storage never held the key */ }
                })));
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
                hint.style.color = 'var(--ps-dim, #c0c0c0)';
                hint.style.marginTop = '2px';
                hint.textContent = 'No backup unit picked - nothing is '
                    + 'backed up yet.';
                wrap.appendChild(hint);
            }
        } else if (shape.mode === 'sequential') {
            const info = document.createElement('div');
            info.style.fontSize = '11px';
            info.style.color = 'var(--ps-dim, #c0c0c0)';
            info.style.marginTop = '2px';
            info.textContent = card.ceilingKnown && card.ceiling
                ? `1 backed by 2, 3 by 4 - ${shape.usable} of `
                    + `${card.ceiling} ports usable.`
                : '1 backed by 2, 3 by 4 - even ports are the returns.';
            wrap.appendChild(info);
        } else if (shape.mode === 'halves') {
            const info = document.createElement('div');
            info.style.fontSize = '11px';
            info.style.color = 'var(--ps-dim, #c0c0c0)';
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
            info.style.color = 'var(--ps-dim, #c0c0c0)';
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
