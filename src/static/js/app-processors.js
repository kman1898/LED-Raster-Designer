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
// name for theirs, the way XD is another's, so only actual model
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
        // The API serves the same file the server reads - one set of
        // numbers - with each device's platform wall stated beside it
        // (`platforms`, `slotPlatforms`, `platformAliases`), which the
        // pickers filter on. The rule lives in port_assignment.py only.
        fetch('/api/processor-catalog')
            .then(r => r.json())
            .then(data => {
                this._processorCatalog = data;
                this.refreshProcessors();
            })
            .catch(err => sendClientLog('processor_catalog_load_failed',
                                        { error: String(err) }));
    }

    refreshProcessors() {
        // A read that comes back after the project was swapped - an undo or
        // redo restore, a file open - describes the server BEFORE that swap
        // landed, so adopting it put an older processor tree on the page
        // than the server held: two quick redos left a box's length blank on
        // the page and 250 on the server (2026-09-24). Such a reply is
        // dropped and the tree is read again for the project now showing.
        // The same goes for a read answered while an undo or redo's restore
        // PUT is still on its way: the undo swaps the project and asks for
        // the tree before the PUT is sent, so the server can answer with
        // the tree being undone, and the restore's reply, matching its
        // snapshot, adopted nothing over it (CI, 2026-10-18: five cables on
        // the server, three on the page). Such a read waits for the restore
        // to land and reads again.
        const restoring = this._restorePutsInFlight;
        if (restoring && restoring.size) {
            return Promise.all([...restoring]).then(() => this.refreshProcessors());
        }
        const asked = this.project;
        const restoreSeq = this._restoreSeq || 0;
        return fetch('/api/processors')
            .then(r => r.json())
            .then(data => {
                if (this.project !== asked || (this._restoreSeq || 0) !== restoreSeq) {
                    return this.refreshProcessors();
                }
                return this._applyProcessorState(data);
            })
            .catch(err => sendClientLog('processor_refresh_failed',
                                        { error: String(err) }));
    }

    _applyProcessorState(data) {
        if (!data || !data.resolved) return;
        // AN OLDER ANSWER NEVER PUTS AN OLDER TREE BACK. The server numbers
        // every reply that carries the tree before reading it
        // (app.processor_state_stamp), so a lower number was read from an
        // older tree: a refresh sent before a rename and answered after the
        // rename's own reply put the old name back on the page (2026-10-30).
        // A new `boot` is a restarted server, whose numbers start again.
        const stamp = data.stateStamp;
        if (stamp && typeof stamp.n === 'number') {
            const last = this._processorStamp;
            if (last && last.boot === stamp.boot && stamp.n < last.n) {
                sendClientLog('processor_state_stale_dropped', { n: stamp.n, newest: last.n });
                return;
            }
            this._processorStamp = { boot: stamp.boot, n: stamp.n };
        }
        this._processorsResolved = data.resolved;
        this._processorsRaw = JSON.stringify(data.processors || []);
        // The connectors a data cable can be typed as, served with the
        // tree (catalog DATA_CABLE_CONNECTORS) so the sheet's select and
        // the server's refusals name one list.
        if (Array.isArray(data.dataCableConnectors)) {
            this._dataCableConnectors = data.dataCableConnectors;
        }
        // The SHOW's snakes ride the same payload (they hold sockets from
        // several devices, so they belong to no card and no box). Stamped
        // onto the project under the tree's own rule: never written onto a
        // project that has none and never had any, so a file that never
        // met the feature stays byte-for-byte what it was.
        if (Array.isArray(data.snakes) && this.project
                && (data.snakes.length || this.project.snakes)) {
            this.project.snakes = data.snakes;
        }
        // The show's fiber cables, the same way - except that an emptied
        // list leaves no key behind (the server drops it too), so the
        // project copy undo snapshots never says `fiberCables: []`.
        if (Array.isArray(data.fiberCables) && this.project) {
            if (data.fiberCables.length) this.project.fiberCables = data.fiberCables;
            else delete this.project.fiberCables;
        }
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
        // A box's beach pick changes what the BEACHES line counts.
        if (typeof this.renderBeaches === 'function') this.renderBeaches();
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
        // Removing a processor, a card (a slot cleared or re-carded) or a
        // box takes the lengths typed on it (owner, 2026-10-17), and a
        // pull-sheet edit on a row only those cables printed goes with
        // them - the rows as they print now, read before the request.
        const removes = !!action && (method === 'DELETE'
            || (method === 'PUT' && /\/slots\/\d+$/.test(url)));
        const pullBefore = removes && typeof this._pullLiveRowKeys === 'function'
            ? this._pullLiveRowKeys() : null;
        return fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body),
        })
            .then(r => r.json())
            .then(data => {
                const applied = !!(data && data.resolved);
                // A box delete on a box-fed unit (an SX40's XD, a HELIOS
                // Standard's RS12) drops the pins that pointed into the
                // box, and the server sends the pruned state back with the
                // tree. It lands on the project copy BEFORE the snapshot
                // below is taken, so undo holds the pins as they now are
                // and redo cannot hand back pins on sockets that are gone.
                if (applied && data.portAssignments && this.project) {
                    this.project.port_assignments = data.portAssignments;
                }
                this._applyProcessorState(data);
                if (applied && pullBefore) this._dropPullEditsGoneWith(pullBefore);
                if (applied && action) this.saveState(action);
                // What the edit had to say - "Removed box XD B - 3
                // ports of LEFT are unplaced again" - read where a refusal
                // would read, but not in a refusal's color: the edit did
                // exactly what it was told.
                if (applied && data.note && typeof this._toast === 'function') {
                    this._toast(data.note, false, 6000);
                }
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

    // The Processing settings the project's screens are on: every screen
    // layer on every canvas, its processorType folded through the server's
    // alias table (a stale token lands where the resolve lands it). Empty
    // when no screen carries a setting - and empty means "no filter".
    _platformsInUse() {
        const aliases = (this._processorCatalog
            && this._processorCatalog.platformAliases) || {};
        const used = new Set();
        ((this.project && this.project.layers) || []).forEach(l => {
            if (!l || (l.type || 'screen') !== 'screen') return;
            const value = l.processorType;
            if (typeof value !== 'string' || !value) return;
            used.add(aliases[value] || value);
        });
        return used;
    }

    // The devices a picker offers for the screens in the project (owner
    // ruling, 2026-09-24: "if a raster only has Brompton processing
    // selected on the whole raster then when we add processors we need to
    // make sure that only Brompton shows up"). A device stays when its wall
    // - `platforms` off the catalog route, a chassis's `slotPlatforms`
    // beside it - shares a setting with any screen; an unrestricted device
    // (both null: the drop refuses nobody on it) always stays; with no
    // screen on a setting, everything stays. The wall itself is the
    // server's: nothing here names a platform or a family.
    _devicesForPlatforms(devices, used) {
        const inUse = used || this._platformsInUse();
        if (!inUse.size) return devices;
        return devices.filter(d => {
            if (!d.platforms && !d.slotPlatforms) return true;
            const wall = [].concat(d.platforms || [], d.slotPlatforms || []);
            return wall.some(p => inUse.has(p));
        });
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
            cards.textContent = `${proc.cardsUsed} / ${proc.maxCards} ${this.unitWordFor(proc)}s`;
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
        // The backup processor, under the bar and independent of it: the
        // bar is redundancy INSIDE the unit, this is a second unit - an
        // option on this one, named here and otherwise automatic.
        wrap.appendChild(this._buildProcBackupBlock(proc));

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
            // The slot as the unit's face prints it - "OUT 1" on an SQ200 -
            // where the catalog words one.
            num.textContent = slot.name || `Slot ${slot.index + 1}`;
            const device = this._processorDevice(proc.deviceId);
            const accepts = (device && device.accepts) || [];
            // A chassis takes its own line's cards, and of those only the
            // ones a screen in the project could land on - the same wall
            // the Add picker keeps, read off each card's `platforms`.
            const cards = this._devicesForPlatforms(
                this._processorDevices('card')
                    .filter(d => accepts.includes(d.family)));
            const picker = this._buildDeviceSelect(
                cards, slot.card ? slot.card.deviceId : '', 'empty');
            picker.dataset.lrdField = `processor-slot-${proc.id}-${slot.index}`;
            // An add: a box-fed card opens its box picker after it
            // (_processorAddRequest); emptying the slot opens nothing.
            picker.addEventListener('change', () => this._processorAddRequest(
                `/api/processors/${proc.id}/slots/${slot.index}`, 'PUT',
                { deviceId: picker.value || null }, `Change Slot ${this.unitWordTitle(this.unitWordFor(proc))}`));
            row.appendChild(num);
            row.appendChild(picker);
            wrap.appendChild(row);
        });

        wrap.appendChild(this._popRemoveButton(
            'Remove processor',
            `Remove this processor. Its ${this.unitWordFor(proc) === 'processor' ? '' : `${this.unitWordFor(proc)}s, `}boxes and every port on them `
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
        if (this.cardIsUnitFace(p, c)) {
            return p.name || p.deviceName || c.deviceName;
        }
        return `${this.cardShortName(p, c) || c.name || c.unitTitle || c.deviceName} in ${p.name || p.deviceName}`;
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
    //   'backup' - this unit is consumed whole as another's 1:1 backup
    //   'fixed'  - the vendor fixes the pairing (a fact, not a level)
    //   'unit'   - a standalone unit whose one card is at 1:1, partner
    //              picked or not - "Backed up" is its level
    //   'mixed'  - a chassis whose cards disagree (some 1:1, some in a
    //              port shape), or one the user put at Mixed on purpose
    //              (the stored redundancyMixed pick)
    //   'port'   - every card is in a port shape
    //   'card'   - anything else: cards at 1:1, paired singly or not yet
    // A chassis has no whole-unit level any more (2026-09-25): a second
    // unit mirroring it whole is its backup processor, the switch under
    // the bar.
    //
    // The cards that decide are the ones with a choice of their own: a
    // card consumed as somebody's 1:1 backup is its main's return end, and
    // whatever mode it stored underneath is inert - so it never makes a
    // chassis read Mixed. Where every card is consumed the stored modes
    // are all there is, and they are read as before.
    _procRedundancyLevel(proc) {
        if (!proc.redundancy) return 'off';
        if (this._backupUnitMainId(proc)) return 'backup';
        if (this._procPairingFixed(proc)) return 'fixed';
        const cards = (proc.slots || []).map(s => s.card).filter(Boolean);
        if (proc.form !== 'chassis') {
            return cards.length && this._cardPortShaped(cards[0])
                ? 'port' : 'unit';
        }
        if (this._procMixable(proc) && proc.redundancyMixed) return 'mixed';
        const live = cards.filter(c => !c.backupFor);
        const deciding = live.length ? live : cards;
        const shaped = deciding.filter(c => this._cardPortShaped(c)).length;
        if (deciding.length && shaped === deciding.length) return 'port';
        if (shaped && this._procMixable(proc)) return 'mixed';
        return 'card';
    }

    // Whether the bar offers Mixed on this unit: a chassis with more than
    // one slot (owner, 2026-10-29: "on say H series i have 3 16 port
    // cards"). A standalone unit is its one card, so there is nothing to
    // mix; a vendor-fixed pairing never reaches here (its own bar).
    _procMixable(proc) {
        return proc.form === 'chassis' && (proc.slots || []).length > 1;
    }

    // A row's legend under the bar - one place, so the words a slot row
    // wears can change in one place. A chassis says its slot and the card
    // in it, the slot counted from one - "Slot 2 · Card 2" where nobody
    // named the card (cardShortName); a standalone unit is its one card,
    // read by its unit title.
    _redRowLegend(proc, slot, card) {
        return proc.form === 'chassis'
            ? `Slot ${slot.index + 1} · ${this.cardShortName(proc, card) || card.name || card.deviceName}`
            : this.dataUnitTitle(proc, card).title;
    }

    // The segment the bar lights: the derived level. (A remembered pick
    // between "Whole unit" and "Per card" lit a chassis's bar before the
    // backup processor had its own row; with "Whole unit" gone there is
    // nothing left to remember.)
    _procRedundancyShown(proc) {
        return this._procRedundancyLevel(proc);
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
    //   mixed - (a chassis only) no card moves: redundancy on where it
    //          was off, and the Mixed pick remembered on the processor
    //          (redundancyMixed) so the bar stays here while the cards
    //          happen to agree. Each card then picks its own kind in its
    //          row. Per card / Per port from Mixed convert every card as
    //          they always did, and the server drops the pick with them.
    _setRedundancyLevel(proc, level) {
        const cards = (proc.slots || []).map(s => s.card).filter(Boolean);
        const url = `/api/processors/${proc.id}`;
        const shown = this._procRedundancyShown(proc);
        if (level === 'off' || level === 'on') {
            if (!!proc.redundancy === (level === 'on')) return;
            this._processorRequest(url, 'PUT', { redundancy: level === 'on' },
                                   'Toggle Redundancy');
            return;
        }
        if (level === 'mixed') {
            if (shown === 'mixed') return;
            this._processorRequest(
                url, 'PUT', { redundancy: true, redundancyMixed: true },
                'Set Redundancy Mixed');
            return;
        }
        if (level === 'port') {
            // The lit segment is a no-op, whatever a consumed card stored.
            if (shown === 'port') return;
            if (proc.redundancy && cards.length
                    && cards.every(c => this._cardPortShaped(c))) {
                // Already every card in a port shape: nothing moves - the
                // bar sat at Mixed by pick, which Per port lets go of in
                // one write, the shapes left as they are.
                if (!proc.redundancyMixed) return;
                this._processorRequest(url, 'PUT', { redundancyMixed: false },
                                       'Set Redundancy Per Port');
                return;
            }
            this._processorRequest(
                url, 'PUT',
                { redundancy: true, cardsRedundancyMode: 'sequential' },
                'Set Redundancy Per Port');
            return;
        }
        const moving = !proc.redundancy || shown === 'mixed'
            || cards.some(c => this._cardPortShaped(c));
        if (!moving) return;
        this._processorRequest(
            url, 'PUT', { redundancy: true, cardsRedundancyMode: '1to1' },
            level === 'unit' ? 'Set Redundancy Backed Up'
                             : `Set Redundancy Per ${this.unitWordTitle(this.unitWordFor(proc))}`);
    }

    // An SX40's loops, each its own switch (owner, 2026-09-25: "lets put A
    // to B and C to D as options"): "A to B" and "C to D", either on
    // alone, both on the old "On", both off redundancy off. One request a
    // click - the loops the unit runs (redundancyPairs, only when a
    // subset) and the switch under them in the same body.
    _toggleRedundancyLoop(proc, mark) {
        const marks = proc.redundancyPairMarks || [];
        const on = new Set(proc.redundancy ? (proc.redundancyPairs || marks) : []);
        if (on.has(mark)) on.delete(mark);
        else on.add(mark);
        const pairs = marks.filter(m => on.has(m));
        const body = !pairs.length
            ? { redundancy: false, redundancyPairs: null }
            : { redundancy: true,
                redundancyPairs: pairs.length === marks.length ? null : pairs };
        this._processorRequest(`/api/processors/${proc.id}`, 'PUT', body,
                               'Set Redundancy Loops');
    }

    // Everything redundancy offers, behind the processor's gear. The
    // user's verdict on what shipped before (2026-09-04): "redundancy
    // toggling needs work. right now it's wayyy too busy" - a switch, a
    // level select, then per slot a caption, a four-way mode select, a
    // partner select and a hint. His pick from mocks/redundancy-mock
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

        if ((proc.redundancyPairMarks || []).length) {
            // AN SX40'S LOOPS ARE INDEPENDENT (owner, 2026-09-25: "you can
            // do A to B or C to D or A to B and C to D"): each is its own
            // switch, and the state they leave is read out under them.
            block.appendChild(this._buildLoopStrip(proc));
            if (proc.redundancy && proc.redundancyPairing) {
                const fact = document.createElement('div');
                fact.className = 'hw-pop-red-fact';
                fact.style.fontSize = '11px';
                fact.style.color = 'var(--ps-dim, #c0c0c0)';
                fact.style.lineHeight = '1.4';
                fact.style.margin = '6px 0 0';
                fact.textContent = proc.redundancyPairing.statement;
                fact.title = 'The loops this unit runs now - each is its '
                    + 'own switch above.';
                block.appendChild(fact);
            }
            return block;
        }

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
        // Mixed (owner, 2026-10-29: "i want to leave the bar. so i think
        // adding mixed makes the most sense") rides the chassis's bar only
        // where there is more than one slot to mix.
        const segments = chassis
            ? [['off', 'Off'], ['card', `Per ${this.unitWordFor(proc)}`], ['port', 'Per port']]
            : [['off', 'Off'], ['unit', 'Backed up'], ['port', 'Per port']];
        if (chassis && this._procMixable(proc)) segments.push(['mixed', 'Mixed']);
        block.appendChild(this._buildRedundancyStrip(proc, segments, shown));
        if (shown === 'off') return block;

        if (!cards.length) {
            const none = document.createElement('div');
            none.style.fontSize = '11px';
            none.style.color = 'var(--ps-dim, #c0c0c0)';
            none.style.marginTop = '6px';
            none.textContent = `No ${this.unitWordFor(proc)}s in the slots yet - put a ${this.unitWordFor(proc)} in `
                + 'a slot below and its row appears here.';
            block.appendChild(none);
            return block;
        }

        if (shown === 'unit') {
            // One row: the partner. A standalone unit is its one card, so
            // it picks that card's 1:1 partner - the second sending card.
            const pick = this._buildCardBackupPick(proc, cards[0]);
            if (pick) block.appendChild(this._buildRedRow('mirrored by', pick));
            return block;
        }

        // Per card and per port: one row per populated slot, the slot and
        // the card's name as the legend (primary text - "grey on grey is
        // hard to read"), then the one control that level offers.
        (proc.slots || []).forEach(slot => {
            const card = slot.card;
            if (!card) return;
            const legend = this._redRowLegend(proc, slot, card);
            if (shown === 'mixed') {
                block.appendChild(this._buildMixedCardRow(proc, card, legend));
                return;
            }
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
                    ? 'fixed by the device' : `not supported on this ${this.unitWordFor(proc, card)}`;
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
        // Four segments size to their words (theme.css hw-pop-seg-fit).
        bar.className = 'hw-pop-seg' + (segments.length > 3 ? ' hw-pop-seg-fit' : '');
        bar.setAttribute('role', 'radiogroup');
        bar.setAttribute('aria-label', 'Redundancy');
        bar.dataset.lrdField = `processor-redundancy-${proc.id}`;
        const word = this.unitWordFor(proc);
        const tips = {
            off: 'Redundancy off for this processor.',
            on: 'Redundancy on. The device pairs its outputs itself.',
            unit: 'Backed up: another unit mirrors this one, port for '
                + `port - ${word === 'card' ? 'the second sending card' : `a second ${word}`}. Pick it below.`,
            card: `Per ${word}: each ${word} is mirrored 1:1 by a ${word} you pick, `
                + 'one row per slot.',
            // One processor can hold copper cards and fiber cards at once,
            // so this line names no trunk: the CARD's chip does that, in
            // the word its own face prints (_portShapeSplitLabel).
            port: `Per port: ports pair inside ${word === 'processor' ? 'the processor' : `each ${word}`} - sequential, `
                + 'split, or picked by hand on each chip.',
            mixed: `Mixed: each ${word} picks its own - 1:1 onto a ${word} you pick, `
                + 'or its ports paired inside it. One row per slot.',
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

    // One slot's row under MIXED (owner, 2026-10-29: "i want card 1 and 2
    // to be primary and backup but then card 3 i want port level
    // backup"). The card picks its own kind on one chip row - 1:1 beside
    // the same Sequential / Split / Manual chips Per port draws, with the
    // same tips - and at 1:1 the same partner pick Per card draws sits
    // under it, held to the same pairing rules (the server's). Every
    // gesture writes ONLY this card, through the card's own route, one
    // request and one undo step each, and says redundancyMixed so the
    // bar stays at Mixed even where the write leaves the cards agreeing.
    // A card consumed as another card's 1:1 backup is that card's return
    // end: it says whose, gold, and offers nothing.
    _buildMixedCardRow(proc, card, legend) {
        if (card.backupFor) {
            const fact = document.createElement('span');
            fact.className = 'hw-pop-red-backupfor';
            fact.style.fontSize = '11px';
            fact.style.color = '#c8a04a';
            fact.style.minWidth = '0';
            fact.style.flex = '1 1 100%';
            fact.style.overflow = 'hidden';
            fact.style.textOverflow = 'ellipsis';
            fact.style.whiteSpace = 'nowrap';
            fact.dataset.lrdField = `processor-card-backupfor-${card.id}`;
            // The main by the same legend its own row wears where it sits
            // in this chassis (three cards of one model read apart only by
            // their slots), else by the unit it sits in.
            const mainId = card.backupFor.cardId;
            const mainSlot = (proc.slots || [])
                .find(s => s.card && s.card.id === mainId);
            const elsewhere = mainSlot ? null : this._otherCards(card.id)
                .find(x => x.card.id === mainId);
            const main = mainSlot ? this._redRowLegend(proc, mainSlot, mainSlot.card)
                : elsewhere ? this._backupUnitTitle(elsewhere.proc, elsewhere.card)
                : card.backupFor.title;
            fact.textContent = `Backup for ${main}`;
            fact.title = `${fact.textContent} - its ports carry that `
                + `${this.unitWordFor(proc, card)}’s returns. Clear the pick `
                + 'on that row to free it.';
            const row = this._buildRedRow(legend, fact);
            // legend over the line, the way a chip row wraps
            row.classList.add('hw-pop-red-row-chips');
            return row;
        }
        const chips = this._buildCardShapeChips(proc, card,
                                                { pair: true, mixed: true });
        if (!chips) {
            const none = document.createElement('span');
            none.style.fontSize = '11px';
            none.style.color = 'var(--ps-dim, #c0c0c0)';
            none.textContent = card.redundancyShape
                ? 'fixed by the device' : `not supported on this ${this.unitWordFor(proc, card)}`;
            return this._buildRedRow(legend, none);
        }
        const row = this._buildRedRow(legend, chips);
        if (card.redundancyShape.mode === '1to1') {
            const pick = this._buildCardBackupPick(proc, card,
                                                   { redundancyMixed: true });
            if (pick) row.appendChild(pick);
        }
        return row;
    }

    // The card's 1:1 partner pick. Every other card in the project is
    // offered with its port count in the text, because the count is the
    // eligibility rule - a 1:1 backup mirrors port for port, and the
    // server refuses a mismatch with both counts in the reason. Ranges
    // over the whole project because a backup unit is usually a second
    // machine, not a second slot.
    // `extra` rides in the same request body (a Mixed row's
    // redundancyMixed), so the pick stays one request and one undo step.
    _buildCardBackupPick(proc, card, extra = null) {
        const shape = card.redundancyShape;
        if (!shape || shape.forced) return null;
        const partner = document.createElement('select');
        partner.dataset.lrdField = `processor-card-backup-${card.id}`;
        partner.title = `The ${this.unitWordFor(proc, card)} that mirrors this one, port for port. `
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
            // The card's reach - on a box-fed card, what its boxes give
            // ("Follow the boxes", 2026-10-04).
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
            Object.assign({ backupCardId: partner.value }, extra || {}),
            'Change Backup Unit'));
        return partner;
    }

    // The loops strip: the REDUNDANCY caption over one switch per trunk
    // pair - "A to B", "C to D" - in the popover's chip recipe, each lit
    // (gold, the backup role's family) while its loop runs. Keyed as the
    // processor's one redundancy field, each chip carrying its pair's
    // leading letter.
    _buildLoopStrip(proc) {
        const strip = document.createElement('div');
        strip.className = 'hw-pop-red-strip';
        const cap = document.createElement('span');
        cap.className = 'hw-pop-red-cap';
        cap.textContent = 'REDUNDANCY';
        cap.title = 'Redundancy for this processor: which trunk loops run.';
        strip.appendChild(cap);
        const group = document.createElement('div');
        group.className = 'hw-pop-chips hw-pop-loops';
        group.setAttribute('role', 'group');
        group.setAttribute('aria-label', 'Redundancy loops');
        group.dataset.lrdField = `processor-redundancy-${proc.id}`;
        const marks = proc.redundancyPairMarks || [];
        const on = proc.redundancy ? (proc.redundancyPairs || marks) : [];
        marks.forEach(m => {
            const next = String.fromCharCode(m.charCodeAt(0) + 1);
            const lit = on.includes(m);
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'hw-pop-chip' + (lit ? ' hw-pop-chip-on' : '');
            chip.setAttribute('aria-pressed', lit ? 'true' : 'false');
            chip.dataset.pair = m;
            chip.textContent = `${m} to ${next}`;
            chip.title = `${m} to ${next}: the strings run out of ${m}'s box and `
                + `back into ${next}'s, and ${next} carries ${m}'s returns. `
                + (lit ? 'Click to run them as primaries.' : 'Click to loop them.');
            chip.addEventListener('click', () => this._toggleRedundancyLoop(proc, m));
            group.appendChild(chip);
        });
        strip.appendChild(group);
        return strip;
    }

    // THE BACKUP PROCESSOR (owner, 2026-09-25: "when we add backup
    // processor it's just an option on the primary and then we are
    // capable of naming but everything else is automatic"). Under the
    // bar, on every processor's ⚙: a BACKUP PROCESSOR switch, Off · On, in
    // the bar's own recipe, and - on - the backup unit's name, "<main> BU"
    // until one is typed (Enter ends the edit). Nothing else is asked: the
    // backup unit is this unit again - its model, cards, loops - each
    // output backing up this one's same output, landing on the same boxes'
    // backup inputs (X2, OPT 2, OPT 3-4), whose rows appear in each box's
    // Fiber section. Off takes the unit and those rows away; one undo
    // brings both back. One request a gesture.
    _buildProcBackupBlock(proc) {
        const block = document.createElement('div');
        block.className = 'hw-pop-red-block hw-pop-backup';
        const strip = document.createElement('div');
        strip.className = 'hw-pop-red-strip';
        const cap = document.createElement('span');
        cap.className = 'hw-pop-red-cap';
        cap.textContent = 'BACKUP PROCESSOR';
        cap.title = 'A second unit of this model feeding the same boxes’ '
            + 'backup inputs.';
        strip.appendChild(cap);
        const bar = document.createElement('div');
        bar.className = 'hw-pop-seg';
        bar.setAttribute('role', 'radiogroup');
        bar.setAttribute('aria-label', 'Backup processor');
        bar.dataset.lrdField = `processor-backup-${proc.id}`;
        const on = !!proc.backupUnit;
        [['off', 'Off', 'No backup processor.'],
         ['on', 'On', 'A second ' + (proc.deviceName || 'unit') + ' mirrors this one, '
             + 'output for output, on the boxes’ backup inputs.']].forEach(([level, text, tip]) => {
            const lit = (level === 'on') === on;
            const seg = document.createElement('button');
            seg.type = 'button';
            seg.className = 'hw-pop-seg-btn' + (lit ? ' hw-pop-seg-on' : '');
            seg.setAttribute('role', 'radio');
            seg.setAttribute('aria-checked', lit ? 'true' : 'false');
            seg.dataset.level = level;
            seg.textContent = text;
            seg.title = tip;
            seg.addEventListener('click', () => {
                if (lit) return;
                this._processorRequest(`/api/processors/${proc.id}`, 'PUT',
                    { backupUnit: level === 'on' ? {} : null },
                    level === 'on' ? 'Add Backup Processor' : 'Remove Backup Processor');
            });
            bar.appendChild(seg);
        });
        strip.appendChild(bar);
        block.appendChild(strip);
        if (!on) return block;
        const main = proc.name || proc.deviceName || 'Processor';
        const field = this._buildTextField(
            'Name', proc.backupUnit.typedName || '', `${main} BU`,
            `processor-backup-name-${proc.id}`,
            (val) => this._processorRequest(`/api/processors/${proc.id}`, 'PUT',
                { backupUnit: { name: val } }, 'Rename Backup Processor'));
        field.style.marginTop = '6px';
        field.title = `The backup unit's name - ${main} BU until one is typed.`;
        block.appendChild(field);
        return block;
    }

    // The card's gear: templates, mode, a read-only redundancy line,
    // capacity, and the breakout-box work - everything the panel's card block carried except
    // the name, which edits inline on the card's dock header.
    // The breakout boxes that FIT a card's free trunks - the gear's picker
    // and the tray's "+ Box" read this one list (reasons at the picker).
    // A box whose catalog entry documents ONE input (singleInput - the
    // CVT4K-S, owner 2026-09-26: "each one only uses one optical port")
    // still fits where fewer trunks are free than its nameplate takes, as
    // long as one is: it is offered as "CVT4K-S (1 OPT)" and goes on with
    // inputs: 1. Each fit is the catalog device, or a copy of it carrying
    // `addInputs` and its own `pickKey` - so a remembered 2-OPT pick never
    // passes for the 1-OPT offer.
    //
    // A retired box entry (catalog `legacy` - the QD-S, a card since
    // 2026-09-28) is never offered, and the card's own default box (its
    // catalog defaultCvt - the XD-S on a QD-S) leads the list.
    _cardBoxFits(card) {
        if (!card || !card.trunks) return [];
        const lead = card.defaultCvt;
        return this._processorDevices('cvt')
            .filter(d => !d.legacy)
            .sort((a, b) => (b.id === lead) - (a.id === lead))
            .filter(d => !d.trunkRate || !card.trunkRate
                         || d.trunkRate === card.trunkRate)
            .filter(d => !d.vendor || !card.vendor
                         || d.vendor === card.vendor)
            .map(d => {
                if ((d.trunksIn || 1) <= card.trunksFree) return d;
                if (d.singleInput && card.trunksFree >= 1) {
                    return Object.assign({}, d, {
                        name: `${d.name} (1 ${this._boxInputWord(d)})`,
                        addInputs: 1,
                        pickKey: `${d.id}:1`,
                    });
                }
                return null;
            })
            .filter(Boolean);
    }

    // What a box's face calls one input - 'OPT' off its linkPorts' 'OPT 1'
    // or 'OPT1' (spaced as its maker spaces it) - else 'input' (an XD's
    // 'X1' names a port, not a word to count by). The server's
    // box_input_word, for catalog devices.
    _boxInputWord(d) {
        const first = String((((d && d.linkPorts) || {}).primary || [])[0] || '');
        const hit = /^(.*\S)\s+\d+$/.exec(first) || /^([A-Za-z]{2,})\d+$/.exec(first);
        return hit ? hit[1] : 'input';
    }

    // The POST body that adds one fit from _cardBoxFits.
    _boxFitBody(fit) {
        const body = { deviceId: fit.id };
        if (fit.addInputs) body.inputs = fit.addInputs;
        return body;
    }

    _buildCardGearContent(proc, card) {
        const wrap = document.createElement('div');
        // "card" only on a card-based processor (unitWordFor)
        const word = this.unitWordFor(proc, card);
        const Word = this.unitWordTitle(word);
        // A one-box unit's card IS the unit, so its gear is headed by the
        // unit's one name; a slot card is headed by its own - "Card 2" on
        // a card-based processor where nobody named it (cardShortName).
        wrap.appendChild(this._popHeading(this.cardIsUnitFace(proc, card)
            ? this.dataUnitTitle(proc, card).title
            : (this.cardShortName(proc, card) || card.name || card.deviceName)));
        // The model stands under a card-based processor's card heading:
        // the card's own gear is where to look up which card it is.
        if (this.procIsCardBased(proc) && card.deviceName) {
            const model = document.createElement('div');
            model.className = 'hw-pop-model';
            model.textContent = card.deviceName;
            model.style.fontSize = '12px';
            model.style.color = 'var(--ps-dim, #c0c0c0)';
            model.style.margin = '0 0 8px 0';
            wrap.appendChild(model);
        }

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
                { portLabelTemplate: val }, `Edit ${Word} Label Template`)));
        // The placeholder is the rung below this one on the return ladder:
        // left blank, every return end derives from its primary, so an empty
        // box still reads as what the backups are actually called - R1-# for
        // a card named P1, SR-#R for one named SR. Rendered off the name the
        // primary actually takes (a slot card's own, else the processor's -
        // a one-box unit's card has no name of its own, see cardTypedName),
        // because the rule turns on that name's first letter. A name typed
        // on ONE port's return end still beats the template.
        names.appendChild(this._buildTextField(
            'Return', card.returnLabelTemplate,
            this._derivedReturnPlaceholder(card.portLabelTemplate,
                                           this.cardTypedName(proc, card)
                                               || proc.name),
            `processor-card-return-template-${card.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                { returnLabelTemplate: val },
                `Edit ${Word} Return Label Template`)));
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
                { mode: select.value || null }, `Change ${Word} Mode`));
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
            // And the VENDOR is part of the metal, the same way: a box only
            // hangs off its own vendor's trunks, so a Brompton box is not
            // offered on a NovaStar card. One rule, written once on the
            // server (processor_catalog.vendor_mismatch, which _fills_the_card
            // has always advised by and can_add_cvt now refuses by) and read
            // the same way here - including its no-inference half: where
            // either sheet names no vendor, nothing is filtered out.
            const fits = this._cardBoxFits(card);
            // THE PICK SURVIVES THE ADD: "i added one cvt 10 and after i
            // added it it cleared the dropdown but it shouldn't clear the
            // drop down". Adding rebuilds this whole panel, so the chosen
            // box is remembered per card and re-selected here - a second
            // identical box is then one click. Only while it still FITS:
            // once its trunks are gone the picker falls back to its
            // placeholder rather than showing something it cannot add.
            // Keyed by each fit's pickKey where it has one (a CVT4K-S on one
            // OPT), so a 2-OPT pick does not stay chosen as the 1-OPT offer.
            const picks = (this._procCvtPick = this._procCvtPick || {});
            const keyOf = d => d.pickKey || d.id;
            const held = fits.some(d => keyOf(d) === picks[card.id])
                ? picks[card.id] : '';
            const picker = this._buildDeviceSelect(
                fits.map(d => Object.assign({}, d, { id: keyOf(d) })), held,
                'Add a breakout box...');
            picker.dataset.lrdField = `processor-cvt-add-${card.id}`;
            picker.addEventListener('change', () => {
                picks[card.id] = picker.value;
            });
            const btn = document.createElement('button');
            btn.className = 'btn';
            btn.textContent = '+';
            btn.style.padding = '6px 12px';
            btn.disabled = !fits.length;
            btn.addEventListener('click', () => {
                const fit = fits.find(d => keyOf(d) === picker.value);
                if (!fit) return;
                picks[card.id] = picker.value;
                // Mirror or Backup is asked first where the box lands on a
                // copy OPT of a per-box card (app-mirror-screens.js).
                this.addBoxWithRole(proc, card, this._boxFitBody(fit),
                                    'Add Breakout Box');
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

            // Per OPT, where the card's own RJ45s are carried out on it too
            // (the MX40 Pro, the H_16xRJ45+2xfiber): all of one OPT's ports
            // at the RJ45 or at its box, in one go (app-mirror-screens.js).
            const plugRows = this._buildCardPlugRows(proc, card);
            if (plugRows) wrap.appendChild(plugRows);

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
                copy.textContent = `The OPTs copy this ${word}’s own ports. `
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
                        ? `this ${word} reaches ${s.ceiling} with `
                          + `${s.reachesWith.join(' or ')}.`
                        : `these boxes cannot reach ${s.ceiling} on this ${word}.`);
                wrap.appendChild(short);
            }

            // A box missing between boxes on a box-fed card is an error
            // (owner, 2026-10-04: "we should throw an error but only do
            // real ports beyond that"): each empty trunk said in the
            // server's words - "OPT 2 has no box - ports 11-20 are
            // missing." - in the capacity row's over-capacity red.
            (card.gaps || []).forEach(gap => {
                const line = document.createElement('div');
                line.className = 'hw-pop-gap';
                line.style.fontSize = '11px';
                line.style.color = '#d05a52';
                line.style.marginTop = '2px';
                line.style.lineHeight = '1.4';
                line.textContent = gap.message;
                wrap.appendChild(line);
            });
        }

        // A slotted card is removed by emptying its slot - the same PUT the
        // slot picker sends, offered here so a card is removable where it
        // is configured. A fixed card is the machine's own outputs and has
        // no removal; the machine's gear carries that one.
        const slot = (proc.slots || [])
            .find(s => s.card && s.card.id === card.id);
        if (slot && !card.fixed) {
            wrap.appendChild(this._popRemoveButton(
                `Remove ${word}`,
                `Empty this slot. The ${word}, its boxes and every port on `
                + 'them go with it; undo puts it back.',
                () => this._processorRequest(
                    `/api/processors/${proc.id}/slots/${slot.index}`, 'PUT',
                    { deviceId: null }, `Change Slot ${Word}`)));
        }
        return wrap;
    }

    // THE BOX'S INPUT SWITCH (owner, 2026-09-26: "A switch on the box"):
    // INPUTS, 1 OPT · 2 OPT, in the backup-processor bar's recipe - only on
    // a box whose catalog entry documents one input (the CVT4K-S). One OPT
    // carries that OPT's share, 8 of the 16 outputs; the links past it
    // (OPT 2, OPT 4) go with the same request. Going back to 2 needs a free
    // trunk, and with none the server says which card is full. One PUT,
    // one 'Set Box Inputs' entry.
    _buildBoxInputsStrip(proc, cvt) {
        const strip = document.createElement('div');
        strip.className = 'hw-pop-red-strip hw-pop-box-inputs';
        strip.style.marginTop = '6px';
        const cap = document.createElement('span');
        cap.className = 'hw-pop-red-cap';
        cap.textContent = 'INPUTS';
        cap.title = 'How many optical inputs this box runs on.';
        strip.appendChild(cap);
        const bar = document.createElement('div');
        bar.className = 'hw-pop-seg';
        bar.setAttribute('role', 'radiogroup');
        bar.setAttribute('aria-label', 'Inputs');
        bar.dataset.lrdField = `processor-cvt-inputs-${cvt.id}`;
        const word = cvt.inputWord || 'input';
        const full = cvt.inputsFull || 2;
        const now = cvt.trunksIn || full;
        [[1, `One ${word}: this box delivers only that ${word}'s ports.`],
         [full, `${full} ${word}: this box delivers all its ports.`]]
            .forEach(([n, tip]) => {
                const lit = n === now;
                const seg = document.createElement('button');
                seg.type = 'button';
                seg.className = 'hw-pop-seg-btn' + (lit ? ' hw-pop-seg-on' : '');
                seg.setAttribute('role', 'radio');
                seg.setAttribute('aria-checked', lit ? 'true' : 'false');
                seg.dataset.level = String(n);
                seg.textContent = `${n} ${word}`;
                seg.title = tip;
                seg.addEventListener('click', () => {
                    if (lit) return;
                    this._processorRequest(
                        `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                        { inputs: n }, 'Set Box Inputs');
                });
                bar.appendChild(seg);
            });
        strip.appendChild(bar);
        return strip;
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
                                           cvt.name
                                               || this.cardTypedName(proc, card)
                                               || proc.name),
            `processor-cvt-return-template-${cvt.id}`,
            (val) => this._processorRequest(
                `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                { returnLabelTemplate: val },
                'Edit Breakout Box Return Label Template')));
        names.querySelectorAll(':scope > div').forEach(cell => {
            cell.style.flex = '1 1 90px';   // a basis, so the line can wrap
        });
        wrap.appendChild(names);

        // The box's fiber - its links onto the show's TAC, MTP and
        // opticalCON cables - is set on the box's ≡ cable sheet, the Fiber
        // section above its ports (2026-09-25: "the fiber info to XD boxes
        // and whatnot should be in the cable lengths area not in the menu
        // it is now"); the gear keeps the box's place.
        //
        // Where the box sits (2026-09-07: "We need to be able to put CVT's
        // or prcessor's at beach locations so they can be accounted for
        // on the pull sheets"; 2026-09-08: "beach locations need to be
        // addable for data" - "Replace it with the picker"): the Beach
        // picker - one of the project's beaches, or a new one made right
        // here. The pull list files the box's rows - the data cables of
        // the ports it delivers, its fiber, its own "CVT4K-S EA" line -
        // under that beach. One PUT, one 'Set Box Beach' entry; the blank
        // entry clears.
        const place = document.createElement('div');
        place.style.display = 'flex';
        place.style.flexWrap = 'wrap';
        place.style.gap = '6px';
        place.style.marginTop = '4px';
        const url = `/api/processors/${proc.id}/cvts/${cvt.id}`;
        const beachField = this.buildBeachPicker({
            value: cvt.beachId,
            fieldKey: `processor-cvt-beach-${cvt.id}`,
            title: 'The beach this box sits on. Every row it produces - the '
                + 'cables of the ports it delivers, its fiber, the box itself - '
                + 'is pulled there.',
            onPick: (beachId) => this._processorRequest(
                url, 'PUT', { beachId }, 'Set Box Beach'),
        });
        place.appendChild(beachField);
        place.querySelectorAll(':scope > div').forEach(cell => {
            cell.style.flex = '1 1 110px';
        });
        wrap.appendChild(place);

        if (cvt.singleInput) wrap.appendChild(this._buildBoxInputsStrip(proc, cvt));
        // A box on a copy OPT that picks per box: Mirror or Backup.
        if (cvt.copyRoleChoice) wrap.appendChild(this._buildBoxCopyRoleStrip(proc, cvt));

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
        // a box straddling a main OPT and its copy OPT feeding a mirror
        // from its copy input (a backup says its loop below)
        if (cvt.spansCopy && cvt.copyInputRole === 'mirror') {
            info.textContent += ', its input on a copy OPT feeds a mirror screen';
        }
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
        } else if (this.boxLoopMixed(cvt)) {
            // A backup bound port by port: the ports of each primary box
            // it backs up (boxLoopText), "loop of CVT10 A 1-10, ...".
            info.style.color = '#c8a04a';
            info.textContent += `: ${this.boxLoopText(cvt, card.cvts,
                b => b.name || b.displayTitle || b.deviceName)}`;
        } else if (cvt.copyRole === 'mirror') {
            // A copy that feeds a mirror screen: sockets of its own,
            // carrying the mirror's runs.
            const primary = (card.cvts || []).find(c => c.id === cvt.mirrorOf);
            const trunk = (card.trunkTitles || [])[cvt.copiesTrunk];
            info.style.color = '#c8a04a';
            info.textContent += ` - mirrors ${primary
                ? (primary.name || primary.displayTitle || primary.deviceName)
                : (trunk || 'its primary')} for a mirror screen`;
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



    // ── data cables: snakes and port home runs ──────────────────────────
    //
    // "we need to have the same option for data homeruns. we can combine
    // ports into a snake as well as adding lengths to each if not snakes."
    // (user, 2026-09-06). Power's distro → multi (one home run) → circuit
    // cable becomes card or box → SNAKE (one name, one home run, N ports)
    // → port cable; a port outside any snake carries its own home run.
    // A port cable sits on the HARDWARE record (the resolved card for the
    // ports on its face, the resolved box for the ports it delivers):
    //     rec.portCables = { [socket]: { ft, connector } }
    // keyed by the card-wide socket number the chips and the assignment
    // run on. A SNAKE sits on the SHOW - "Any sockets, any device"
    // (2026-09-09) - and names its members:
    //     project.snakes = [{ id, name, ft, connector,
    //                         members: [{ kind, id, socket }…] }]
    // A snake's home run belongs to the socket, not the screen: a port
    // cleared from its screen KEEPS its snake. Its own port cable runs to
    // the screen, so the release forgets it (owner, 2026-10-17 - the
    // server's /unpin, processor_catalog.forget_port_cables).
    // The server validates and normalises (processor_catalog's cable
    // stores and its show-snake section); this side only reads what comes
    // back resolved and writes through one request per gesture - a device
    // PUT for a port cable, /api/snakes for a snake - so every commit is
    // ONE history entry.

    // Copper only: fiber is the breakout box's trunk (its links onto the
    // show's fiber cables, app-fiber.js, set on the Fiber section of the
    // box's ≡ sheet), never a port's or a snake's plug - "panels dont take
    // fiber" (2026-09-07).
    getDataCableConnectors() {
        return (this._dataCableConnectors || [
            { id: 'cat', name: 'Cat6' },
            { id: 'ethercon', name: 'etherCON' },
        ]).map(c => ({ id: c.id, name: c.name }));
    }

    dataCableConnectorName(id) {
        const hit = this.getDataCableConnectors().find(c => c.id === id);
        return hit ? hit.name : null;
    }

    // THE word for a data home run, on every surface that names one - the
    // pull sheet, the binder's PORTS / CABLES / Snakes & home runs, the
    // map's cable tags and the tray chips (owner, 2026-10-21): "etherCON"
    // where the box's output is etherCON, "Cat6" where it is plain RJ45 or
    // nobody documented it. A snake is "<word> Snake", its extension
    // "<word> Extension", a coupler "<word> Barrel". Fiber keeps its own
    // names (fiberCableTypeText).
    dataCableWord(id) {
        return this.dataCableConnectorName(id)
            || this.dataCableConnectorName('cat') || 'Cat6';
    }

    // The record that OWNS a socket's home run: the breakout box
    // delivering it (the port's cvtId, the one that names it -
    // resolve_card; never a backup box carrying it again), else the card
    // itself. Returns { kind: 'card'|'cvt', id, procId, cardId, rec } or
    // null for a socket nothing resolves to.
    _dataPortOwner(cardId, socket) {
        const found = this._dockFindCard(cardId);
        if (!found) return null;
        const n = parseInt(socket, 10);
        const port = (found.card.ports || []).find(p => p.number === n);
        const box = port
            ? (port.cvtId ? (found.card.cvts || []).find(c => c.id === port.cvtId) : null)
            : (found.card.cvts || []).find(c => (c.ports || []).some(p => p.number === n));
        if (box) {
            return { kind: 'cvt', id: box.id, procId: found.proc.id,
                     cardId, rec: box };
        }
        if (!(found.card.ports || []).some(p => p.number === n)) return null;
        return { kind: 'card', id: cardId, procId: found.proc.id, cardId,
                 rec: found.card };
    }

    // An owner by its own key, for the sheet and the sweep, which know
    // the record they are standing on rather than a socket.
    _dataCableOwner(kind, id) {
        if (kind === 'cvt') {
            const found = this._dockFindCvt(id);
            return found ? { kind, id, procId: found.proc.id,
                             cardId: found.card.id, rec: found.cvt } : null;
        }
        const found = this._dockFindCard(id);
        return found ? { kind: 'card', id, procId: found.proc.id,
                         cardId: id, rec: found.card } : null;
    }

    _dataCableOwnerUrl(owner) {
        return owner.kind === 'cvt'
            ? `/api/processors/${owner.procId}/cvts/${owner.id}`
            : `/api/processors/${owner.procId}/cards/${owner.id}`;
    }

    // ---- the show's snakes ---------------------------------------------
    //
    // "Any sockets, any device" (2026-09-09): one snake carries a card's
    // A-1..A-4 and its backup box's B-1..B-4 together, so it hangs on the
    // SHOW and names its members - project.snakes = [{ id, name, ft,
    // connector, members: [{ kind: 'card'|'cvt', id, socket }…] }]. The
    // server owns the rules (processor_catalog's show-snake section) and
    // re-homes every member onto the device that DELIVERS its socket, so
    // a snake typed on a card before a box was hung on it stays visible -
    // the bug that made a card's snake disappear the moment a box took
    // over its sockets.
    getShowSnakes() {
        return (this.project && this.project.snakes) || [];
    }

    getShowSnake(snakeId) {
        return this.getShowSnakes().find(s => s.id === snakeId) || null;
    }

    // The snake a socket rides on its owner, or null.
    dataPortSnake(owner, socket) {
        if (!owner) return null;
        const n = parseInt(socket, 10);
        return this.getShowSnakes().find(s => (s.members || []).some(
            m => m.kind === owner.kind && m.id === owner.id
                && m.socket === n)) || null;
    }

    // One member as a pair the routes take.
    snakeMember(owner, socket) {
        return { kind: owner.kind, id: owner.id,
                 socket: parseInt(socket, 10) };
    }

    // The members of `snake` that sit on one device, in socket order.
    snakeMembersOn(snake, owner) {
        return ((snake && snake.members) || [])
            .filter(m => m.kind === owner.kind && m.id === owner.id)
            .map(m => m.socket)
            .sort((a, b) => a - b);
    }

    // The devices a snake touches, in member order, as owners.
    snakeOwners(snake) {
        const out = [];
        const seen = new Set();
        ((snake && snake.members) || []).forEach(m => {
            const key = `${m.kind}:${m.id}`;
            if (seen.has(key)) return;
            seen.add(key);
            const owner = this._dataCableOwner(m.kind, m.id);
            if (owner) out.push(owner);
        });
        return out;
    }

    // Does this snake reach past one device? (The bracket's "↔" and the
    // sheet's "+ … on <other device>" both hang off this one question.)
    snakeSpansOwners(snake) {
        return this.snakeOwners(snake).length > 1;
    }

    // WHETHER A CARD IS ITS PROCESSOR'S FACE. A one-box unit - a NovaPro
    // UHD Jr, an S8, an MX40 Pro - carries ONE fixed card that IS
    // the unit; a chassis (the H series, the MX2000 / MX6000 - the catalog
    // says which, by `form`) holds slot cards that are parts inside it.
    // The server's card_is_unit_face, mirrored: the resolved processor's
    // form decides, and a card born fixed says the same when the form is
    // not to hand.
    cardIsUnitFace(proc, card) {
        const form = (proc || {}).form;
        if (form) return form !== 'chassis';
        return !!((card || {}).fixed);
    }

    // WHETHER A PROCESSOR'S UNITS ARE CALLED CARDS (owner, 2026-10-17:
    // "CARD" becomes "PROCESSOR" for every processor that is not card
    // based). Only the H series, the MX2000 and the MX6000 hold cards; an
    // S8, an SX40, a HELIOS, an MX40 Pro are one unit with their own
    // ports. The server's is_card_based, off the resolved processor's
    // `cardBased`; a chassis read before that field existed says chassis.
    procIsCardBased(proc) {
        if (!proc) return false;
        if (typeof proc.cardBased === 'boolean') return proc.cardBased;
        return proc.form === 'chassis';
    }

    // WHAT A SHEET, TOOLTIP OR MESSAGE CALLS THE UNIT A PORT SITS ON:
    // 'card' on a card-based processor, the catalog's own word for a card
    // that is a unit of its own ("QD" - the QD-S on an SQ200's OUT), else
    // 'processor'. One spelling for the dock, the binder and every
    // message, so a card is never called a processor or the reverse.
    unitWordFor(proc, card) {
        if (this.procIsCardBased(proc)) return 'card';
        const held = card || ((proc && proc.slots) || []).map(s => s && s.card).find(c => c && c.unitWord);
        if (held && held.unitWord) return held.unitWord;
        // an empty chassis: the word of the one kind of unit it takes
        if (!card && proc && proc.form === 'chassis' && typeof this._processorDevice === 'function') {
            const device = this._processorDevice(proc.deviceId);
            const accepts = (device && device.accepts) || [];
            const words = [...new Set(this._processorDevices('card')
                .filter(d => accepts.includes(d.family)).map(d => d.unitWord || ''))];
            if (words.length === 1 && words[0]) return words[0];
        }
        return 'processor';
    }

    // The same for text that names no one processor - a tooltip over the
    // whole tray, a count over every screen: 'card' while every processor
    // in the show is card based (and with none at all, as it always read),
    // 'processor' where none is, 'card or processor' where both are.
    showUnitWord(plural = false) {
        const procs = (this._processorsResolved || []).filter(Boolean);
        const carded = procs.filter(p => this.procIsCardBased(p)).length;
        const word = !procs.length || carded === procs.length ? 'card'
            : carded ? 'card or processor' : 'processor';
        if (!plural) return word;
        return word === 'card or processor' ? 'cards or processors' : `${word}s`;
    }

    // "card or box" said of the whole show: 'card or box' as it always
    // read, 'processor or box' where no processor holds cards, 'card,
    // processor or box' where some do and some do not.
    showUnitOrBox(plural = false) {
        const word = this.showUnitWord();
        if (word === 'card or processor') return plural ? 'cards, processors or boxes' : 'card, processor or box';
        return plural ? `${word}s or boxes` : `${word} or box`;
    }

    // The same word heading a history entry or a menu item: "Card",
    // "Processor", "QD".
    unitWordTitle(word) {
        const w = String(word || 'card');
        return w.charAt(0).toUpperCase() + w.slice(1);
    }

    // The word for the unit a card id sits on (unitWordFor), from the id.
    unitWordForCard(cardId) {
        const found = typeof this._dockFindCard === 'function' ? this._dockFindCard(cardId) : null;
        return found ? this.unitWordFor(found.proc, found.card) : 'card';
    }

    // THE NAME SOMEBODY TYPED FOR A CARD, OR '' (ruling, 2026-09-24: "the
    // H series and MX6000 and 2000 are the only card based processors. all
    // others should only have 1 name slot"). A slot card's is its own; a
    // one-box unit's face has no slot of its own and reads the unit's - the
    // processor strip is the one place that name is typed. Every sheet
    // and label placeholder reads a card's name through here, so a name a
    // 1.3 file left on a fixed card (moved up to the unit on load) can
    // never outrank the unit's again.
    cardTypedName(proc, card) {
        const rec = this.cardIsUnitFace(proc, card) ? proc : card;
        return (((rec || {}).name) || '').trim();
    }

    // "CARD 3": what a card on a card-based processor is, by the slot it
    // sits in, counted from one (owner, 2026-10-29: "we should show it as
    // Card 1, 2, 3 etc instead of H_16 which gets confusing"). The slots
    // before it may be empty - the card in slot 3 is Card 3. '' on every
    // other processor (an SX40, an S8, an SQ200's QD-S never say card) and
    // for a card in no slot. The server's card_slot_title.
    cardSlotTitle(proc, card) {
        if (!card || !this.procIsCardBased(proc)) return '';
        const slot = (((proc || {}).slots) || [])
            .find(s => s && s.card && s.card.id === card.id);
        return slot ? `Card ${(slot.index || 0) + 1}` : '';
    }

    // THE NAME A CARD GOES BY ON A CARD-BASED PROCESSOR: the name somebody
    // typed (it always wins), else Card N (cardSlotTitle) - never the
    // model, which is said only where gear is pulled (the binder's Cards
    // table and its pull page's Hardware). '' on every other processor, so
    // a caller's own reading for those stays exactly as it was:
    //     this.cardShortName(proc, card) || <the caller's old fallback>
    cardShortName(proc, card) {
        if (!card || !this.procIsCardBased(proc)) return '';
        return this.cardTypedName(proc, card) || this.cardSlotTitle(proc, card);
    }

    // THE UNIT A SOCKET SITS ON, NAMED ONCE (2026-09-09, off the live
    // show A binder: "IMAG SR IMAG SR · NovaPro UHD Jr · 16 ports").
    // A processor with no slots - a NovaPro UHD Jr, an S8 - carries
    // ONE fixed card that IS its face, so the unit has one name, the
    // processor's, and the paperwork says it once. A real slot card is a
    // part inside a processor and reads as both, "H9 SR" - but never twice
    // over, and never the model standing in for a name only for the model
    // to be printed again beside it: a title that falls back to the model
    // tells the caller so (`named` is false) and the caller drops its own
    // model column rather than saying it twice.
    dataUnitTitle(proc, card) {
        const p = (((proc || {}).name) || '').trim();
        const c = (((card || {}).name) || '').trim();
        if (!card || this.cardIsUnitFace(proc, card)) {
            const title = p || (proc || {}).deviceName
                || (card || {}).deviceName || (proc || {}).id || '';
            return { title, named: !!p };
        }
        const slot = (((proc || {}).slots) || [])
            .find(s => s && s.card && s.card.id === card.id);
        const host = p || proc.deviceName || proc.id || '';
        // A card that is a unit of its own goes by its title ("QD 1"); an
        // unnamed card on a card-based processor by its slot, "Card 3".
        const part = this.cardShortName(proc, card) || c || card.unitTitle
            || (slot ? `slot ${(slot.index || 0) + 1}` : card.deviceName || '');
        const named = !!(p || c);
        if (!host || !part) return { title: host || part, named };
        const a = host.toLowerCase(), b = part.toLowerCase();
        if (a === b || b.startsWith(a + ' ')) return { title: part, named };
        if (a.startsWith(b + ' ')) return { title: host, named };
        return { title: `${host} ${part}`, named };
    }

    // The same reading from a card id alone, for a caller holding one.
    dataUnitTitleForCard(cardId) {
        const found = typeof this._dockFindCard === 'function'
            ? this._dockFindCard(cardId) : null;
        return found ? this.dataUnitTitle(found.proc, found.card)
            : { title: cardId || '', named: false };
    }

    // What a card or a box is CALLED, the way its own header calls it: the
    // box's resolved title (trunk letter included), the card's unit title
    // (dataUnitTitle - one name for a card that IS its processor), else the
    // device name. One spelling, so a snake row and a section header never
    // name the same box two ways.
    dataOwnerTitle(owner) {
        const rec = (owner && owner.rec) || {};
        if (owner && owner.kind === 'cvt') {
            return rec.displayTitle || (rec.name || '').trim()
                || rec.deviceName || owner.id;
        }
        const unit = owner && owner.kind === 'card' && owner.id
            ? this.dataUnitTitleForCard(owner.id) : null;
        if (unit && unit.title) return unit.title;
        return (rec.name || '').trim() || rec.deviceName
            || (owner && owner.id) || '';
    }

    // One socket as the paperwork says it: its port label where it has one
    // ("SR A-1"), else the silkscreened number on its own device.
    dataSocketLabel(owner, socket) {
        const n = parseInt(socket, 10);
        const port = (((owner && owner.rec) || {}).ports || [])
            .find(p => p.number === n);
        if (port && port.label) return port.label;
        return String((port && port.localNumber) || n);
    }

    // The members of `snake` that are NOT on `owner`, grouped by the
    // device they sit on: [{ owner, sockets, text }] - what a sheet says
    // about the rest of a snake it can only show part of ("+ B-1, B-2 on
    // CVT4K-S SR B").
    snakeElsewhere(snake, owner) {
        return this.snakeOwners(snake)
            .filter(o => !(o.kind === owner.kind && o.id === owner.id))
            .map(o => {
                const sockets = this.snakeMembersOn(snake, o);
                const title = this.dataOwnerTitle(o);
                // The device is named once, at the end. Where the port
                // labels already carry its name - they are templated off
                // it, so a box called SR A gives SR A-1 - the labels drop
                // the prefix rather than saying it four more times.
                const labels = sockets.map(n => {
                    const label = this.dataSocketLabel(o, n);
                    return title && label.startsWith(title)
                        ? label.slice(title.length).replace(/^[-\s]+/, '')
                        : label;
                });
                return {
                    owner: o, sockets,
                    text: `${labels.join(', ')} on ${title}`,
                };
            });
    }

    // The connector a socket's cable FOLLOWS: the stored pick where there
    // is one, else the catalog's word for the device the port comes out of
    // (rec.portConnector - a box's own, never its card's; a card's, else
    // its processor's), else 'cat': an undocumented port reads Cat6.
    dataPortConnectorId(owner, stored) {
        if (stored && this.dataCableConnectorName(stored)) return stored;
        const follows = owner && owner.rec && owner.rec.portConnector;
        return follows && this.dataCableConnectorName(follows)
            ? follows : 'cat';
    }

    // What one socket's home run reads as: the snake it rides
    // ({ kind: 'snake', snake, owner, ext, extConnector, text: 'SNAKE A'
    // or "SNAKE A +25'" }) or its own cable ({ kind: 'cable', ft,
    // connector, id, name, text: "50' Cat6" }), or null for a socket with
    // neither. On a snaked socket `ext` is the EXTENSION from the snake's
    // fan-out to the panel (rec.portCables on that socket - the same store
    // a loose socket's home run lives in), null when none; `text` is what
    // the chip corner, the canvas tag and the paperwork print.
    dataPortCable(cardId, socket) {
        const owner = this._dataPortOwner(cardId, socket);
        if (!owner) return null;
        return this._dataPortCableOn(owner, socket);
    }

    _dataPortCableOn(owner, socket) {
        const snake = this.dataPortSnake(owner, socket);
        const rec = (owner.rec.portCables || {})[String(socket)];
        const ft = rec ? this.parseCableLength(rec.ft) : null;
        const hasFt = !!rec && Number.isFinite(ft) && ft > 0;
        if (snake) {
            const ext = hasFt ? ft : null;
            const name = snake.name || '';
            return {
                kind: 'snake', snake, owner, ext,
                extConnector: (rec && rec.connector) || null,
                text: ext != null ? `${name} +${this.cableText(ext, '', 'data')}` : name,
            };
        }
        if (!hasFt) return null;
        const id = this.dataPortConnectorId(owner, rec.connector);
        const name = this.dataCableWord(id);
        return {
            kind: 'cable', owner, ft, connector: rec.connector || null,
            id, name, text: this.cableText(ft, name, 'data'),
        };
    }

    // What a port's tag on the DATA MAP reads (owner, 2026-11-02: "just
    // list 25'"): a loose cable by its length alone ("25'", "8 m", the
    // stock pieces "100'+25'"), never its connector - on a wall of narrow
    // columns "25' etherCON" was wider than a column and the tags zig-
    // zagged over and under the discs. The binder names the connector once
    // under the screen's name instead (_bDataCableNote). A snake reads as
    // it always has ("SNAKE A", "SNAKE A +25'"): its text carries no
    // connector. The pull sheet, the binder's tables and the cable sheets
    // keep the whole cable (`text`, runText); the power map is not read
    // through here.
    dataMapTagText(cable) {
        if (!cable) return '';
        if (cable.kind === 'cable' && Number.isFinite(Number(cable.ft)) && Number(cable.ft) > 0) {
            return this.cableText(cable.ft, '', 'data');
        }
        return cable.text || '';
    }

    // One run as the papers say it, whole - the binder's home-run cell and
    // the pull list share this: a snake reads "SR Primary 150'" (its name
    // and its home run; "SR Primary · no length" without one), plus
    // " +25'" when the socket carries an extension; a loose cable reads
    // as its text ("50' Cat6"); nothing reads blank. A socket a port is
    // placed on (`at`, { cardId, port }) with no home run typed reads as
    // the pull list writes it, "etherCON no length" (owner, 2026-10-22):
    // a blank is only for a truly empty cell (no em dash, owner 2026-11-03).
    runText(cable, at = null) {
        if (!cable) {
            const owner = at && at.cardId != null && typeof this._dataPortOwner === 'function'
                ? this._dataPortOwner(at.cardId, at.port) : null;
            if (!owner || typeof this.pullDataConnectorWord !== 'function') return '';
            const rec = (owner.rec.portCables || {})[String(at.port)];
            return `${this.pullDataConnectorWord(this.dataPortConnectorId(owner, rec && rec.connector))} no length`;
        }
        if (cable.kind !== 'snake') return cable.text || '';
        const s = cable.snake || {};
        const ft = this.parseCableLength(s.ft);
        let text = (s.name || 'snake')
            + (Number.isFinite(ft) && ft > 0
                ? ` ${this.cableText(ft, '', 'data')}` : ' · no length');
        if (cable.ext != null) text += ` +${this.cableText(cable.ext, '', 'data')}`;
        return text;
    }

    // One port of a screen as the assignment pinned it - { cardId, port }
    // off the resolved assignment - or null while the port is on no card.
    _screenPortPin(layer, portNum) {
        const scr = ((this._assignment && this._assignment.screens) || [])
            .find(s => String(s.layerId) === String(layer.id));
        const port = scr && (scr.ports || [])
            .find(p => p.number === parseInt(portNum, 10));
        return port && port.cardId && port.port != null ? port : null;
    }

    // The same reading for one port of a screen, through the assignment:
    // the port's pinned socket, then the socket's owner. Null while the
    // port is on no card.
    dataPortCableForScreen(layer, portNum) {
        const port = this._screenPortPin(layer, portNum);
        return port ? this.dataPortCable(port.cardId, port.port) : null;
    }

    // The same reading for the port's BACKUP end - what the return marker
    // wears ("also redundancy extensions and snakes arent showing their
    // cable tags", 2026-09-07). The pinned socket's resolved card port
    // carries `backedBy` ({ cardId, port } - processor_catalog link()),
    // read off the tree by _pullBackedBy (app-pull-list.js: the pull list
    // walks the backup end through the same helper - one implementation),
    // then that socket's own home run: the backup box's snake, "+25'" when
    // the backup socket carries an extension, "50' Cat6" for a loose backup
    // cable. Null while the port is on no card, has no backup, or the
    // backup socket carries nothing.
    dataPortBackupCableForScreen(layer, portNum) {
        const port = this._screenPortPin(layer, portNum);
        if (!port || typeof this._pullBackedBy !== 'function') return null;
        const bb = this._pullBackedBy(port.cardId, port.port);
        return bb ? this.dataPortCable(bb.cardId, bb.port) : null;
    }

    // The snake's tag as the bracket and the sheet print it:
    // "SNAKE A · 6 channel · 100'". CHANNELS ARE THE WHOLE SNAKE - every
    // member on every device - because a snake is one loom whatever it is
    // read from: an 8 channel snake spanning a card and its backup box
    // says "8 channel" on both sheets, and each sheet names the members
    // it cannot show ("+ B-1, B-2 on CVT4K-S SR B" - snakeElsewhere) so
    // the number and the rows never disagree.
    //
    // `ways` still overrides the count for a reader that has its own
    // answer.
    snakeTagText(snake, withFt = true, ways = null) {
        if (ways == null) ways = (snake.members || []).length;
        const name = snake.name || 'snake';
        let text = `${name} · ${this.snakeSizeText(name, ways)}`;
        const ft = this.parseCableLength(snake.ft);
        if (withFt && Number.isFinite(ft) && ft > 0) {
            text += ` · ${this.cableText(ft, '', 'data')}`;
        }
        return text;
    }

    // A snake's SIZE, the one place it is worded: "4 channel snake" - "dont
    // call it 4 way. call it 4 channel snake if it is 4 channel"
    // (2026-09-12). The word snake is written once in whatever it is
    // printed beside: where `beside` (the snake's name, or whatever else
    // the reading already prints) already says it as a whole word - "SNAKE
    // A", "Snake 2", "SR snake" - the size is "4 channel" ("Snake A if
    // that's what it's named is going to have it written twice"). A word
    // that merely starts with it ("SNAKEPIT") is not the word. One channel
    // is "1 channel". Snakes only: a multi's fan and a distro's holes are
    // power sizing and never read through here.
    snakeSizeText(beside, channels) {
        const says = /(^|[^a-z0-9])snake(?![a-z0-9])/i.test(String(beside || ''));
        return `${channels} channel${says ? '' : ' snake'}`;
    }

    // ---- writes: whole stores back through one PUT each -----------------

    // One device's PORT CABLES, whole, for the PUT that stores them. The
    // snakes are not here: they are the show's, and they are written
    // through /api/snakes so one loom is one record however many devices
    // it crosses.
    _dataCableStores(owner) {
        const rec = owner.rec || {};
        return {
            portCables: JSON.parse(JSON.stringify(rec.portCables || {})),
        };
    }

    _dataCablePut(owner, stores, action) {
        return this._processorRequest(this._dataCableOwnerUrl(owner), 'PUT',
                                      stores, action);
    }

    // The members a gesture gathered, from (owner, sockets) - the shape
    // every write below takes.
    snakeMembersOf(owner, sockets) {
        return [...new Set((sockets || []).map(n => parseInt(n, 10)))]
            .filter(n => Number.isFinite(n))
            .sort((a, b) => a - b)
            .map(n => this.snakeMember(owner, n));
    }

    // Snake these members - sockets from ONE device or from several - into
    // one new snake (name defaulted server-side to the first free SNAKE
    // letter, show-wide). They leave any snake they were in first, so
    // "snake these four" always means these four and nothing else. Their
    // own cables were HOME RUNS (a loose socket's own), not extensions -
    // the snake is the home run now, so they are forgotten on purpose; an
    // extension is typed on the member row afterwards. ONE 'Snake Ports'
    // entry, whatever it crossed. Resolves to the new snake's id.
    snakePorts(members, ft = null) {
        const list = (members || []).filter(Boolean);
        if (!list.length) return Promise.resolve(null);
        const body = { members: list };
        // No length asked for: the Snake home run preference, when one is
        // set (blank as shipped - a new snake starts with no length, as
        // it always has). Read here, at creation, and nowhere else.
        if (ft == null) ft = this.defaultSnakeHomeRunFt();
        if (ft != null) body.ft = ft;
        const before = new Set(this.getShowSnakes().map(s => s.id));
        // The sockets leave their old snakes and their own home runs in
        // the same gesture; the POST that forms the snake is the entry
        // that carries it, so the clearing rides ahead of it silently.
        return this._clearForSnake(list)
            .then(() => this._processorRequest('/api/snakes', 'POST', body,
                                               'Snake Ports'))
            .then(() => {
                const made = this.getShowSnakes()
                    .find(s => !before.has(s.id));
                return made ? made.id : null;
            });
    }

    // The Pull sheet & cables preferences the data cables are made with,
    // in the show's unit (each kept per unit, app-cable-units.js): the
    // home run a new snake takes (null = none), and the length the
    // sheet's loose-port quick fill writes (100' / 30 m as shipped).
    defaultSnakeHomeRunFt() {
        const v = this.cablePref('snakeHomeRun');
        const n = Number(v);
        return v != null && Number.isFinite(n) && n > 0 ? n : null;
    }

    defaultLoosePortCableFt() {
        const n = Number(this.cablePref('loosePortCable'));
        return Number.isFinite(n) && n > 0 ? n : (this.cableUnit() === 'm' ? 30 : 100);
    }

    // Ahead of a new snake: the members leave whatever snake held them,
    // and each forgets the cable stored on it - a loose socket's home run
    // is the snake's home run now. No history entry of its own: it is half
    // of the one gesture above, so undo takes the whole of it back.
    _clearForSnake(members) {
        const riding = members.filter(m => {
            const owner = this._dataCableOwner(m.kind, m.id);
            return owner && this.dataPortSnake(owner, m.socket);
        });
        const byOwner = new Map();
        members.forEach(m => {
            const owner = this._dataCableOwner(m.kind, m.id);
            if (!owner) return;
            if (!((owner.rec.portCables || {})[String(m.socket)])) return;
            const key = `${m.kind}:${m.id}`;
            if (!byOwner.has(key)) byOwner.set(key, { owner, sockets: [] });
            byOwner.get(key).sockets.push(m.socket);
        });
        let chain = riding.length
            ? this._processorRequest('/api/snakes/loosen', 'POST',
                                     { members: riding })
            : Promise.resolve();
        byOwner.forEach(({ owner, sockets }) => {
            chain = chain.then(() => {
                const again = this._dataCableOwner(owner.kind, owner.id);
                if (!again) return null;
                const stores = this._dataCableStores(again);
                sockets.forEach(n => { delete stores.portCables[String(n)]; });
                return this._dataCablePut(again, stores);
            });
        });
        return chain;
    }

    // Unsnake members out of their snakes (a snake left empty goes) - the
    // sheet's "Unsnake" button, the opposite of "Snake" (2026-09-07:
    // "dont call it loosen"; "Unpair" is the redundancy bar's word).
    // `snakeId` alone unsnakes a whole loom, wherever its members sit. A
    // socket that leaves keeps its portCables entry: what was its
    // extension off the snake reads as its own home run again - a length
    // somebody typed is not thrown away, and the sheet shows it where it
    // can be changed. ONE 'Unsnake' entry, even across devices.
    loosenPorts(members, snakeId = null) {
        if (snakeId) {
            return this._processorRequest(`/api/snakes/${snakeId}`, 'DELETE',
                                          undefined, 'Unsnake');
        }
        const list = (members || []).filter(Boolean);
        if (!list.length) return Promise.resolve();
        return this._processorRequest('/api/snakes/loosen', 'POST',
                                      { members: list }, 'Unsnake');
    }

    // Rename / re-length / re-plug one snake. `patch` carries any of
    // name, ft, connector; `action` names the entry ('Rename Snake',
    // 'Set Snake Home Run'). One snake, wherever it is edited from - the
    // same row on every sheet that holds a member of it.
    setSnake(snakeId, patch, action) {
        const snake = this.getShowSnake(snakeId);
        if (!snake) return Promise.resolve();
        const body = {};
        if ('name' in patch) body.name = (patch.name || '').trim();
        if ('ft' in patch) {
            // read the way every typed length is (readTypedLength,
            // 2026-10-22): "30m" in a feet show converted and said, text
            // that is no length refused and said, the length kept
            if (typeof patch.ft === 'string') {
                const read = this.readTypedLength(patch.ft, 'snake');
                if (!read.ok) return Promise.resolve();
                body.ft = read.n;
            } else {
                body.ft = this.parseCableLength(patch.ft);
            }
        }
        if ('connector' in patch) {
            body.connector = patch.connector
                && this.dataCableConnectorName(patch.connector)
                ? patch.connector : null;
        }
        const same = Object.keys(body).every(k => {
            const was = snake[k] == null ? null : snake[k];
            const now = body[k] === '' ? null : body[k];
            return String(was == null ? '' : was) === String(now == null ? '' : now);
        });
        if (same) return Promise.resolve();
        return this._processorRequest(`/api/snakes/${snakeId}`, 'PUT', body,
                                      action);
    }

    // One socket's own cable: { ft, connector } - blank or zero ft with
    // no connector forgets it. On a loose socket it is the home run (ONE
    // 'Set Port Cable'); on a socket in a snake it is the EXTENSION from
    // the snake's fan-out to the panel (ONE 'Set Port Extension') - the
    // same store, the same PUT, read apart by whether the socket is
    // snaked (_dataPortCableOn).
    setPortCable(owner, socket, cable, action = null) {
        if (!action) {
            action = this.dataPortSnake(owner, socket)
                ? 'Set Port Extension' : 'Set Port Cable';
        }
        const stores = this._dataCableStores(owner);
        const key = String(parseInt(socket, 10));
        const before = JSON.stringify(stores.portCables[key] || null);
        // a length typed as text reads the way every typed length does
        // (readTypedLength): converted and said, or refused and kept
        let ft = cable ? this.parseCableLength(cable.ft) : null;
        if (cable && typeof cable.ft === 'string') {
            const read = this.readTypedLength(cable.ft, 'cable');
            if (!read.ok) return Promise.resolve();
            ft = read.n;
        }
        const connector = cable && cable.connector
            && this.dataCableConnectorName(cable.connector)
            ? cable.connector : null;
        if (!(Number.isFinite(ft) && ft > 0) && !connector) {
            delete stores.portCables[key];
        } else {
            stores.portCables[key] = {};
            if (Number.isFinite(ft) && ft > 0) stores.portCables[key].ft = ft;
            if (connector) stores.portCables[key].connector = connector;
        }
        if (JSON.stringify(stores.portCables[key] || null) === before) {
            return Promise.resolve();
        }
        return this._dataCablePut(owner, stores, action);
    }

    // Quick fill: every LOOSE socket among `ports` (the sockets the
    // owner's sheet lists - a card's are the ones no box delivers, so the
    // fill never reaches into a box's span) gets the one length (its
    // connector pick untouched), or forgets its cable; snaked sockets are
    // left alone - their run is the snake's, and an extension is typed
    // per member, never filled. ONE 'Set Port Cable'.
    fillPortCables(owner, ft, ports) {
        const stores = this._dataCableStores(owner);
        const snaked = new Set();
        this.getShowSnakes().forEach(s => (s.members || []).forEach(m => {
            if (m.kind === owner.kind && m.id === owner.id) snaked.add(m.socket);
        }));
        const before = JSON.stringify(stores.portCables);
        (ports || owner.rec.ports || []).forEach(p => {
            if (snaked.has(p.number)) return;
            const key = String(p.number);
            const cur = stores.portCables[key] || {};
            if (ft == null) {
                delete stores.portCables[key];
                return;
            }
            const next = { ft };
            if (cur.connector) next.connector = cur.connector;
            stores.portCables[key] = next;
        });
        if (JSON.stringify(stores.portCables) === before) {
            return Promise.resolve();
        }
        return this._dataCablePut(owner, stores, 'Set Port Cable');
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
            fact.textContent = `Redundancy: not supported on this ${this.unitWordFor(proc, card)}`;
            return fact;
        }
        // One name for the shape wherever it prints: the chip and this
        // line read the same words - see _portShapeSplitLabel.
        const named = shape.mode === 'halves'
            ? this._portShapeSplitLabel(card) : shape.mode;
        if (shape.forced) {
            fact.textContent = `Redundancy: ${named} - fixed by the `
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
        fact.textContent = `Redundancy: ${named}`;
        return fact;
    }

    // What the `halves` shape is CALLED on this card. "halves works but we
    // need a better name for it" (2026-09-11), and the name he reached for
    // was "OPT Split" - which is exactly what it is on the card he works in:
    // two CVT10s on a 16-port NovaStar card, one OPT carrying 1-8 and the
    // other carrying their returns on 9-16.
    //
    // OPT is a word printed on a card's face, not a word for trunks in
    // general, so the chip uses the word THIS card's sheet documents
    // (trunkWord - the same field a box's trunkTitle names its trunk by) and
    // says a plain "Split" wherever no sheet prints one: a copper-only card
    // has no trunk to name, and a Megapixel HELIOS has eight trunks that
    // nobody calls OPTs. Naming an OPT on either is the extrapolation the
    // standing rule forbids.
    //
    // The STORED id stays `halves` - this is a label, and a project saved
    // before today opens exactly as it was.
    _portShapeSplitLabel(card) {
        const word = (card && card.trunkWord || '').trim();
        return word ? `${word} Split` : 'Split';
    }

    // The word a redundancy shape wears on its chip under the processor's
    // ⚙ - "1:1", "Sequential", "OPT Split", "Manual" - one spelling for
    // the chips and every sheet that names a card's shape, never the
    // stored id ("1to1", "halves"). '' for no shape.
    _redundancyShapeLabel(card, mode) {
        if (mode === '1to1') return '1:1';
        if (mode === 'sequential') return 'Sequential';
        if (mode === 'halves') return this._portShapeSplitLabel(card);
        if (mode === 'manual') return 'Manual';
        return mode && mode !== 'off' ? String(mode) : '';
    }

    // The sentence the split's tip adds where the split really is the
    // trunks backing each other, and nothing at all where it is not.
    // Derived, never assumed: the ports fill the trunks in blocks of
    // portsPerTrunk, so the front half is whole trunks only when the half
    // divides by that block. Two trunks say it in the singular, because
    // that is the card the user is working in.
    _splitTrunkClause(card, half) {
        const word = (card && card.trunkWord || '').trim();
        const per = card && card.portsPerTrunk;
        const trunks = (card && card.trunks) || 0;
        if (!word || !per || !half || trunks < 2 || half % per) return '';
        const n = half / per;
        return n === 1
            ? ` One ${word}’s ports, backed by the other’s.`
            : ` The back ${n} ${word}s carry the returns of the front ${n}.`;
    }

    // The card's port-shape chips, in the bar's Per port zone: Sequential ·
    // Split · Manual, three raised chips with exactly one lit, replacing
    // the four-way select the user found "wayyy too busy" (2026-09-04).
    // The three port shapes are the user's own: sequential ("1 is backed
    // up by 2 on the same unit/sending card"), the split (the 2026-08-27
    // shape: "1-8 on processor 1 and 9-16 as backups") and manual ("1 is
    // backed up to whatever port you want"). 1:1 is not a chip: it is the
    // bar's own Per card level. A vendor-fixed pairing (Brompton
    // adjacent) never draws chips - it is stated under the bar instead -
    // and a card the sheet says cannot pair draws none either.
    //
    // Under MIXED (opts.pair) the trio gains a 1:1 chip in front - the
    // card's own pick between a partner card and a port shape - and every
    // chip's write carries redundancyMixed (opts.mixed) so the bar stays
    // at Mixed. Same chips, same tips, same stored ids otherwise.
    _buildCardShapeChips(proc, card, opts = {}) {
        const shape = card.redundancyShape;
        if (!shape || shape.forced) return null;
        const group = document.createElement('div');
        group.className = 'hw-pop-chips';
        group.setAttribute('role', 'radiogroup');
        group.setAttribute('aria-label', 'Port shape');
        group.dataset.lrdField = `processor-card-shape-${card.id}`;
        if (opts.pair) group.classList.add('hw-pop-chips-pair');
        const half = card.ceilingKnown && card.ceiling
            ? Math.floor(card.ceiling / 2) : null;
        const word = this.unitWordFor(proc, card);
        [...(opts.pair ? [['1to1', this._redundancyShapeLabel(card, '1to1'),
          `1:1: another ${word} mirrors this one, port for port. `
          + 'Pick it under the chips.']] : []),
         ['sequential', this._redundancyShapeLabel(card, 'sequential'),
          card.ceilingKnown && card.ceiling
              ? `1 backed by 2, 3 by 4 - ${shape.mode === 'sequential'
                  ? shape.usable : Math.ceil(card.ceiling / 2)} of `
                + `${card.ceiling} ports usable.`
              : '1 backed by 2, 3 by 4 - even ports are the returns.'],
         // The same split the server maps: mains are the front ceil(n/2),
         // returns the back floor(n/2) - port 1 comes back on 9 of 16.
         // Both spans named, because this is the one shape whose main
         // and return wear different numbers. Where the split lands on a
         // trunk boundary - and only there - it is also the trunks
         // backing each other, which is the whole reason the chip wears
         // the trunk's name: on the user's 16-port card OPT 2's ports
         // carry OPT 1's returns. On an MX20, whose two OPTs each carry
         // all six ports, the split is INSIDE one of them, and the tip
         // says nothing it cannot show.
         // A box-fed card splits the ports its boxes give, holes and all
         // (2026-10-04), so its spans are the server's (halvesSpans) -
         // "Ports 26-40 carry the returns of 1-10, 21-25." - and the
         // trunk sentence only where no box is missing between boxes.
         ['halves', this._redundancyShapeLabel(card, 'halves'), card.halvesSpans
             ? `Ports ${card.halvesSpans.backs} carry the returns of `
               + `${card.halvesSpans.mains}.`
               + ((card.gaps || []).length ? ''
                   : this._splitTrunkClause(card, half))
             : half && !card.boxFed
             ? `Ports ${card.ceiling - half + 1}-${card.ceiling} carry the `
               + `returns of 1-${half}.` + this._splitTrunkClause(card, half)
             : 'The back half of the ports are the front half’s '
               + 'returns.'],
         ['manual', this._redundancyShapeLabel(card, 'manual'),
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
                const body = { redundancyMode: id };
                if (opts.mixed) body.redundancyMixed = true;
                this._processorRequest(
                    `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                    body, 'Change Redundancy Mode');
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
