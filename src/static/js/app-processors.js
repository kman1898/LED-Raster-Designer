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

    // The processor's gear: the machine-level facts and controls - capacity,
    // the redundancy bar with everything redundancy offers beneath it
    // (_buildProcRedundancyBlock), the chassis slots' card pickers, and
    // the remove.
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
            // THE ONE HOME FOR REDUNDANCY - and one calm surface. The
            // switch, the level select and the per-slot mode selects that
            // shipped before were the user's "wayyy too busy"
            // (2026-09-04); they collapsed into one segmented bar, with
            // everything redundancy offers in one zone beneath it
            // (_buildProcRedundancyBlock). Directly under the capacity
            // facts, where the switch stood.
            wrap.appendChild(this._buildProcRedundancyBlock(proc));
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

    // How a card reads in a partner list: a fixed card IS its unit, so it
    // wears the unit's name (the "second sending card" is a whole MX20, not
    // a slot in one); a slotted card wears its own name with the chassis
    // it sits in, because two chassis can each hold a card called SL.
    _backupUnitTitle(p, c) {
        if (c.fixed) return p.name || c.name || p.deviceName || c.deviceName;
        return `${c.name || c.deviceName} in ${p.name || p.deviceName}`;
    }

    // Whether the vendor fixes this unit's pairing (Brompton's adjacent
    // A-to-B). The resolved statement only arrives with redundancy ON,
    // and the bar has to know BEFORE it is on - a fixed unit's bar is
    // "Off · On", and a shape request sent to it would be refused - so
    // the catalog's own field is read here, the same field the server
    // reads (processor_catalog.redundancy_pairing). No rule is invented
    // for a device the catalog does not mark.
    _procPairingFixed(proc) {
        if (proc.redundancyPairing && proc.redundancyPairing.fixed) return true;
        const device = this._processorDevice(proc.deviceId);
        return !!(device && device.redundancy
                  && device.redundancy.pairing === 'adjacent');
    }

    // A card whose ports pair INSIDE it (sequential / halves / manual) as
    // opposed to a card paired with another card (1:1). Read off the
    // resolved shape, so a card with no shape - redundancy off, or a
    // device the sheet says cannot - is neither.
    _cardPortShaped(card) {
        const shape = card && card.redundancyShape;
        return !!(shape && shape.mode !== '1to1');
    }

    // THE DERIVED LEVEL. What the bar lights is read from what is stored,
    // never from what was clicked, so the bar can never claim a level
    // that is not there:
    //   'off'    - the processor's redundancy is off
    //   'backup' - this unit is consumed whole as another's backup
    //   'fixed'  - the vendor fixes the pairing (a fact, not a level)
    //   'unit'   - the server derives a partner mirroring this one card
    //              for card (a standalone unit: its one card is at 1:1,
    //              partner picked or not - "Backed up" is its level)
    //   'port'   - every card is in a port shape
    //   'card'   - anything else: cards at 1:1, paired singly or not yet
    _procRedundancyLevel(proc) {
        if (!proc.redundancy) return 'off';
        if (this._backupUnitMainId(proc)) return 'backup';
        if (this._procPairingFixed(proc)) return 'fixed';
        const cards = (proc.slots || []).map(s => s.card).filter(Boolean);
        if (proc.form !== 'chassis') {
            return cards.length && this._cardPortShaped(cards[0])
                ? 'port' : 'unit';
        }
        if (proc.backupProcessorId) return 'unit';
        if (cards.length && cards.every(c => this._cardPortShaped(c))) {
            return 'port';
        }
        return 'card';
    }

    // The segment the bar lights: the derived level, with one memory on
    // top of it. A whole-unit pairing IS every card's 1:1 pick, so "Per
    // card" clicked over a pairing stores nothing new and derives straight
    // back as "Whole unit"; "Whole unit" clicked before a partner is
    // picked has stored nothing at all. Both are intent, remembered per
    // processor (_procRedLevelPick) until the state moves on - and only
    // between those two: the memory never lights a segment that
    // contradicts Off or a port shape, because those are facts the bar
    // must report.
    _procRedundancyShown(proc) {
        const derived = this._procRedundancyLevel(proc);
        const pick = this._procRedLevelPick && this._procRedLevelPick[proc.id];
        if (proc.form === 'chassis' && (pick === 'unit' || pick === 'card')
                && (derived === 'unit' || derived === 'card')) {
            return pick;
        }
        return derived;
    }

    // One segment, one request, one history entry - and no request where
    // nothing would move. What a segment stores:
    //   off  - redundancy off
    //   on   - redundancy on (the vendor-fixed bar; nothing to shape)
    //   port - redundancy on and every card sequential, the plainest
    //          port shape, in one write (cardsRedundancyMode)
    //   unit / card - redundancy on and every card at 1:1, in one write,
    //          when something has to move (off, or a port shape somewhere);
    //          otherwise the click is presentation only, remembered
    //          (_procRedundancyShown) and outside history, since the two
    //          are the same stored shape read at two levels. The partner
    //          pick under either is what actually pairs.
    _setRedundancyLevel(proc, level) {
        this._procRedLevelPick = this._procRedLevelPick || {};
        const cards = (proc.slots || []).map(s => s.card).filter(Boolean);
        const url = `/api/processors/${proc.id}`;
        const refresh = () => {
            if (typeof this._hwPopoverRefresh === 'function') {
                this._hwPopoverRefresh();
            }
        };
        if (level === 'off' || level === 'on') {
            delete this._procRedLevelPick[proc.id];
            if (!!proc.redundancy === (level === 'on')) return;
            this._processorRequest(url, 'PUT', { redundancy: level === 'on' },
                                   'Toggle Redundancy');
            return;
        }
        if (level === 'port') {
            delete this._procRedLevelPick[proc.id];
            if (proc.redundancy && cards.length
                    && cards.every(c => this._cardPortShaped(c))) return;
            this._processorRequest(
                url, 'PUT',
                { redundancy: true, cardsRedundancyMode: 'sequential' },
                'Set Redundancy Per Port');
            return;
        }
        if (proc.form === 'chassis') this._procRedLevelPick[proc.id] = level;
        const moving = !proc.redundancy
            || cards.some(c => this._cardPortShaped(c));
        if (!moving) {
            refresh();
            return;
        }
        this._processorRequest(
            url, 'PUT', { redundancy: true, cardsRedundancyMode: '1to1' },
            level === 'unit' ? 'Set Redundancy Whole Unit'
                             : 'Set Redundancy Per Card');
    }

    // Everything redundancy offers, behind the processor's gear. The
    // user's verdict on what shipped before (2026-09-04): "redundancy
    // toggling needs work. right now it's wayyy too busy" - a switch, a
    // level select, then per slot a caption, a four-way mode select, a
    // partner select and a hint. His pick from src/static/redundancy-mock
    // .html is option A: ONE segmented bar - Off · Whole unit · Per card ·
    // Per port on a chassis, Off · Backed up · Per port on a standalone
    // unit, Off · On where the vendor fixes the pairing - and exactly one
    // zone under it: a partner row, a partner row per slot, or a chip
    // trio per slot. The level IS the mode, so the mode select is gone.
    // The same three levels the earlier ruling asked for ("if you need to
    // do processor redundancy i need to be able to set that. but also
    // sending card or port redundancy needs to be an option") and the
    // same server behaviour; only the surface changed. A unit consumed as
    // somebody's backup gets no bar at all, just its role.
    _buildProcRedundancyBlock(proc) {
        const block = document.createElement('div');
        block.className = 'hw-pop-red-block';
        const cards = (proc.slots || []).map(s => s.card).filter(Boolean);
        const level = this._procRedundancyLevel(proc);

        if (level === 'fixed') {
            // WHERE THE VENDOR FIXES THE PAIRING, IT IS A FACT, NOT A FIELD.
            // Brompton pairs adjacent outputs automatically - A backs up to
            // B, C backs up to D - and offers no other arrangement, so the
            // bar is Off · On and the pairing is stated under it, never
            // drawn as a control. The sentence comes from the server (the
            // one authority on the rule); no statement arrives for vendors
            // with none documented, and nothing is invented for them here.
            block.appendChild(this._buildRedundancyStrip(
                proc, [['off', 'Off'], ['on', 'On']], 'on'));
            const fact = document.createElement('div');
            fact.className = 'hw-pop-red-fact';
            fact.style.fontSize = '11px';
            fact.style.color = 'var(--ps-dim, #c0c0c0)';
            fact.style.lineHeight = '1.4';
            fact.style.margin = '6px 0 0';
            fact.textContent = proc.redundancyPairing.statement;
            fact.title = 'Fixed pairing. This is how the device runs '
                + 'redundancy; it is not a setting.';
            block.appendChild(fact);
            return block;
        }

        if (level === 'backup') {
            // A unit consumed whole as somebody's backup states its role
            // and offers nothing - no bar: its ports are the main's
            // returns, and a plan for them would be a plan for ports that
            // are spoken for.
            const main = (this._processorsResolved || [])
                .find(p => p.id === this._backupUnitMainId(proc));
            const fact = document.createElement('div');
            fact.className = 'hw-pop-red-fact';
            fact.style.marginTop = '8px';
            fact.style.fontSize = '11px';
            fact.style.color = '#c8a04a';
            fact.textContent = `Backs up ${main
                ? (main.name || main.deviceName) : 'another processor'}`
                + ' - card for card; its ports carry that unit’s returns.';
            fact.title = 'Picked as the whole-processor backup. Clear the '
                + 'pick on the main processor to free this one.';
            block.appendChild(fact);
            return block;
        }

        if (this._procPairingFixed(proc)) {
            // Off, on a fixed-pairing unit: the same two-segment bar, so
            // "On" is the one gesture and never a shape the device would
            // refuse.
            block.appendChild(this._buildRedundancyStrip(
                proc, [['off', 'Off'], ['on', 'On']], 'off'));
            return block;
        }

        const chassis = proc.form === 'chassis';
        const shown = this._procRedundancyShown(proc);
        block.appendChild(this._buildRedundancyStrip(proc, chassis
            ? [['off', 'Off'], ['unit', 'Whole unit'], ['card', 'Per card'],
               ['port', 'Per port']]
            : [['off', 'Off'], ['unit', 'Backed up'], ['port', 'Per port']],
            shown));
        if (shown === 'off') return block;

        if (!cards.length) {
            const none = document.createElement('div');
            none.style.fontSize = '11px';
            none.style.color = 'var(--ps-dim, #c0c0c0)';
            none.style.marginTop = '6px';
            none.textContent = 'No cards in the slots yet - put a card in '
                + 'a slot below and its row appears here.';
            block.appendChild(none);
            return block;
        }

        if (shown === 'unit') {
            // One row: the partner. A chassis picks the unit that mirrors
            // it card for card; a standalone unit is its one card, so it
            // picks that card's 1:1 partner - the second sending card.
            const pick = chassis
                ? this._buildProcBackupPick(proc, cards)
                : this._buildCardBackupPick(proc, cards[0]);
            block.appendChild(this._buildRedRow('mirrored by', pick));
            return block;
        }

        // Per card and per port: one row per populated slot, the slot and
        // the card's name as the legend (primary text - "grey on grey is
        // hard to read"), then the one control that level offers.
        (proc.slots || []).forEach(slot => {
            const card = slot.card;
            if (!card) return;
            const legend = chassis
                ? `Slot ${slot.index + 1} · ${card.name || card.deviceName}`
                : (card.name || card.deviceName);
            let control = shown === 'card'
                ? this._buildCardBackupPick(proc, card)
                : this._buildCardShapeChips(proc, card);
            if (!control) {
                // A card the sheet says cannot pair states so in the
                // control's place; nothing is drawn that could not act.
                control = document.createElement('span');
                control.style.fontSize = '11px';
                control.style.color = 'var(--ps-dim, #c0c0c0)';
                control.textContent = card.redundancyShape
                    ? 'fixed by the device' : 'not supported on this card';
            }
            block.appendChild(this._buildRedRow(legend, control));
        });
        return block;
    }

    // The bar itself: raised buttons in the popover's own recipe -
    // gradient ground, top light, drop shadow, a press that sinks a pixel
    // ("remember our raised formatting", 2026-09-04) - butted into one
    // segmented control, the lit segment in the accent the Balance
    // dialog's Apply wears. A radiogroup keyed as the processor's one
    // redundancy field, each segment carrying its level, so the focus
    // machinery and the tests address it the way they addressed the
    // switch it replaces.
    // The bar with its name. User (2026-09-05), on the SX40's gear:
    // "under sx 40 naming we just have off and on for redundancy it doesnt
    // say it is for redundancy." So every device's bar - the chassis's
    // four segments and the fixed-pairing pair alike - sits under a small
    // REDUNDANCY legend, the strip caption the dock wears over LEGS and
    // OUTPUTS, in primary text (never grey on grey). The bar itself is
    // unchanged and keeps its field key; the caption is a label, not a
    // control.
    _buildRedundancyStrip(proc, segments, shown) {
        const strip = document.createElement('div');
        strip.className = 'hw-pop-red-strip';
        const cap = document.createElement('span');
        cap.className = 'hw-pop-red-cap';
        cap.textContent = 'REDUNDANCY';
        cap.title = 'Redundancy for this processor.';
        strip.appendChild(cap);
        strip.appendChild(this._buildRedundancyBar(proc, segments, shown));
        return strip;
    }

    _buildRedundancyBar(proc, segments, shown) {
        const bar = document.createElement('div');
        bar.className = 'hw-pop-seg';
        bar.setAttribute('role', 'radiogroup');
        bar.setAttribute('aria-label', 'Redundancy');
        bar.dataset.lrdField = `processor-redundancy-${proc.id}`;
        const tips = {
            off: 'Redundancy off for this processor.',
            on: 'Redundancy on. The device pairs its outputs itself.',
            unit: proc.form === 'chassis'
                ? 'Whole unit: another processor mirrors this one, card '
                  + 'for card. Pick it in the row below.'
                : 'Backed up: another unit mirrors this one, port for '
                  + 'port - the second sending card. Pick it below.',
            card: 'Per card: each card is mirrored 1:1 by a card you pick, '
                + 'one row per slot.',
            port: 'Per port: ports pair inside each card - sequential, '
                + 'halves, or picked by hand on each chip.',
        };
        segments.forEach(([level, text]) => {
            const seg = document.createElement('button');
            seg.type = 'button';
            seg.className = 'hw-pop-seg-btn'
                + (level === shown ? ' hw-pop-seg-on' : '');
            seg.setAttribute('role', 'radio');
            seg.setAttribute('aria-checked', level === shown ? 'true' : 'false');
            seg.dataset.level = level;
            seg.textContent = text;
            seg.title = tips[level] || '';
            seg.addEventListener('click', () =>
                this._setRedundancyLevel(proc, level));
            bar.appendChild(seg);
        });
        return bar;
    }

    // One row under the bar: a legend and its one control. The legend is
    // primary text at the popover's monospace, never the caption grey. A
    // chip trio needs the popover's whole width to spell its three words
    // ("Sequential" beside a slot legend truncated to "Sequ…"), so that
    // row wraps: legend above, chips below; a select row stays one line.
    _buildRedRow(legend, control) {
        const row = document.createElement('div');
        row.className = 'hw-pop-red-row'
            + (control.classList && control.classList.contains('hw-pop-chips')
               ? ' hw-pop-red-row-chips' : '');
        const key = document.createElement('span');
        key.className = 'hw-pop-red-key';
        key.textContent = legend;
        key.title = legend;
        row.appendChild(key);
        row.appendChild(control);
        return row;
    }

    // The card's 1:1 partner pick. Every other card in the project is
    // offered with its port count in the text, because the count is the
    // eligibility rule - a 1:1 backup mirrors port for port, and the
    // server refuses a mismatch with both counts in the reason. Ranges
    // over the whole project because a backup unit is usually a second
    // machine, not a second slot.
    _buildCardBackupPick(proc, card) {
        const shape = card.redundancyShape;
        if (!shape || shape.forced) return null;
        const partner = document.createElement('select');
        partner.dataset.lrdField = `processor-card-backup-${card.id}`;
        partner.title = 'The card that mirrors this one, port for port. '
            + 'Nothing is backed up until one is picked.';
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = 'backed up by…';
        blank.selected = !card.backupCardId;
        partner.appendChild(blank);
        this._otherCards(card.id).forEach(({ proc: p, card: c }) => {
            const opt = document.createElement('option');
            opt.value = c.id;
            const title = this._backupUnitTitle(p, c);
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
        return partner;
    }

    // The whole-processor partner pick: every other processor, offered
    // with its card count and port total because those are the eligibility
    // rule - card for card, then port for port - and the server names the
    // slot that fails. One request carries the whole pairing, so one undo
    // takes it back.
    _buildProcBackupPick(proc, cards) {
        const partner = document.createElement('select');
        partner.dataset.lrdField = `processor-backup-${proc.id}`;
        partner.title = cards.length
            ? `The unit that mirrors this one, card for card. It needs `
              + `${cards.length} card${cards.length === 1 ? '' : 's'} with `
              + 'the same port counts, slot for slot. Nothing is backed up '
              + 'until one is picked.'
            : 'A processor with no cards has nothing to mirror.';
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = 'backed up by…';
        blank.selected = !proc.backupProcessorId;
        partner.appendChild(blank);
        (this._processorsResolved || []).forEach(p => {
            if (p.id === proc.id) return;
            const opt = document.createElement('option');
            opt.value = p.id;
            const pcards = (p.slots || []).map(s => s.card).filter(Boolean);
            const known = pcards.every(c => c.ceilingKnown);
            const ports = known
                ? pcards.reduce((n, c) => n + (c.ceiling || 0), 0) : '?';
            let note = '';
            const backsId = this._backupUnitMainId(p);
            if (backsId && backsId !== proc.id) {
                const m = (this._processorsResolved || [])
                    .find(x => x.id === backsId);
                note = ` (backs up ${m ? (m.name || m.deviceName) : 'another'})`;
            }
            opt.textContent = `${p.name || p.deviceName} - ${pcards.length} `
                + `card${pcards.length === 1 ? '' : 's'}, ${ports} ports${note}`;
            if (p.id === proc.backupProcessorId) opt.selected = true;
            partner.appendChild(opt);
        });
        partner.addEventListener('change', () => {
            // A stored answer outranks a remembered pick: once the server
            // reports the pairing (or its absence) the level derives again.
            if (this._procRedLevelPick) delete this._procRedLevelPick[proc.id];
            this._processorRequest(
                `/api/processors/${proc.id}`, 'PUT',
                { backupProcessorId: partner.value },
                'Change Backup Processor');
        });
        return partner;
    }

    // The card's gear: templates, mode, a read-only redundancy line,
    // capacity, and the breakout-box work - everything the panel's card block carried except
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

        // The card's redundancy is READ here and SET behind the processor's
        // gear: one home for the controls, so a card's gear cannot offer a
        // mode select that the processor's gear does not know about. The
        // line states the shape in force and where to change it.
        const redundancy = this._buildCardRedundancyFact(proc, card);
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

    // The card gear's one passive line: the shape in force on this card,
    // and where it is set. No control here, by design - see
    // _buildProcRedundancyBlock.
    _buildCardRedundancyFact(proc, card) {
        if (!proc.redundancySupported) return null;
        const fact = document.createElement('div');
        fact.className = 'hw-pop-red-fact';
        fact.style.marginTop = '6px';
        fact.style.fontSize = '11px';
        fact.style.color = 'var(--ps-dim, #c0c0c0)';
        fact.title = 'Set behind the processor\u2019s \u2699.';
        if (!proc.redundancy) {
            fact.textContent = 'Redundancy: off - set behind the '
                + 'processor’s ⚙';
            return fact;
        }
        if (card.backupFor) {
            fact.style.color = '#c8a04a';
            fact.textContent = `Redundancy: backs up ${card.backupFor.title}`;
            return fact;
        }
        const shape = card.redundancyShape;
        if (!shape) {
            fact.textContent = 'Redundancy: not supported on this card';
            return fact;
        }
        if (shape.forced) {
            fact.textContent = `Redundancy: ${shape.mode} - fixed by the `
                + 'device';
            return fact;
        }
        if (shape.mode === '1to1') {
            const found = card.backupCardId
                ? this._otherCards(card.id)
                    .find(x => x.card.id === card.backupCardId) : null;
            fact.textContent = found
                ? `Redundancy: 1:1, backed up by `
                  + `${this._backupUnitTitle(found.proc, found.card)}`
                : 'Redundancy: 1:1, no backup unit picked';
            return fact;
        }
        fact.textContent = `Redundancy: ${shape.mode}`;
        return fact;
    }

    // The card's port-shape chips, in the bar's Per port zone: Sequential ·
    // Halves · Manual, three raised chips with exactly one lit, replacing
    // the four-way select the user found "wayyy too busy" (2026-09-04).
    // The three port shapes are the user's own: sequential ("1 is backed
    // up by 2 on the same unit/sending card"), halves (the 2026-08-27
    // shape: "1-8 on processor 1 and 9-16 as backups") and manual ("1 is
    // backed up to whatever port you want"). 1:1 is not a chip: it is the
    // bar's own Per card level. A vendor-fixed pairing (Brompton
    // adjacent) never draws chips - it is stated under the bar instead -
    // and a card the sheet says cannot pair draws none either.
    _buildCardShapeChips(proc, card) {
        const shape = card.redundancyShape;
        if (!shape || shape.forced) return null;
        const group = document.createElement('div');
        group.className = 'hw-pop-chips';
        group.setAttribute('role', 'radiogroup');
        group.setAttribute('aria-label', 'Port shape');
        group.dataset.lrdField = `processor-card-shape-${card.id}`;
        const half = card.ceilingKnown && card.ceiling
            ? Math.floor(card.ceiling / 2) : null;
        [['sequential', 'Sequential',
          card.ceilingKnown && card.ceiling
              ? `1 backed by 2, 3 by 4 - ${shape.mode === 'sequential'
                  ? shape.usable : Math.ceil(card.ceiling / 2)} of `
                + `${card.ceiling} ports usable.`
              : '1 backed by 2, 3 by 4 - even ports are the returns.'],
         // The same split the server maps: mains are the front ceil(n/2),
         // returns the back floor(n/2) - port 1 comes back on 9 of 16.
         // Both spans named, because this is the one shape whose main
         // and return wear different numbers.
         ['halves', 'Halves', half
             ? `Ports ${card.ceiling - half + 1}-${card.ceiling} carry the `
               + `returns of 1-${half}.`
             : 'The back half of the ports are the front half’s '
               + 'returns.'],
         ['manual', 'Manual',
          'Each port picks its backup in its chip on the hardware dock. '
          + 'An unpicked port has no backup.'],
        ].forEach(([id, text, tip]) => {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'hw-pop-chip'
                + (id === shape.mode ? ' hw-pop-chip-on' : '');
            chip.setAttribute('role', 'radio');
            chip.setAttribute('aria-checked', id === shape.mode ? 'true' : 'false');
            chip.dataset.mode = id;
            chip.textContent = text;
            chip.title = tip;
            chip.addEventListener('click', () => {
                if (id === shape.mode) return;
                this._processorRequest(
                    `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                    { redundancyMode: id }, 'Change Redundancy Mode');
            });
            group.appendChild(chip);
        });
        return group;
    }

}

for (const k of Object.getOwnPropertyNames(_Processors.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Processors.prototype, k));
    }
}
