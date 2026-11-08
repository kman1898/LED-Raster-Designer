// app-dock-cable-sheets: the dock's cable sheets - a multi box or a data
// device flipped into a per-tail / per-port table where cable lengths and
// connectors are typed, the per-socket tick marks, and the localStorage
// memory of which face a box shows. Moved verbatim out of app-dock.js and
// attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { fiberStrandName, FIBER_STRAND_SUGGESTIONS, TAC_CONNECTORS, COPPER_LINK_KINDS,
         FIBER_EXTENSION_KINDS, FIBER_EXTENSION_CONNECTORS } from './app-fiber.js';

class _DockCableSheets {
    // ── the box's cable sheet ─────────────────────────────────────────────
    //
    // "we need to be able to add cables to each circuit on the distro
    // besides just soca length or l620 length etc. like say circuit 1 needs
    // a 10ft true 1 and circuit 2 needs 6ft and 3/4 need nothing and 5
    // needs 6ft and 6 needs a 10 ft. since we are going to have those pdf
    // docs we need to be able to have that info if i want to add it."
    // (user, 2026-09-06). The fact is per circuit - a length (in the show's
    // unit, feet or meters - app-cable-units.js) and a
    // connector that follows the box unless changed - stored on the holder
    // screen (powerCircuitCables, app-power.js). This is where it gets
    // typed: the box flips into a sheet, one row per tail, and Tab walks
    // the length column so six cables is one open. Which face a box shows
    // is a viewing choice, remembered per box in localStorage and never in
    // the project - the same doctrine the fold state follows.

    _cableSheetKey(distroId, n) {
        return `lrd_cable_sheet_${distroId}_${n}`;
    }

    _cableSheetOpen(distroId, n) {
        try {
            return localStorage.getItem(this._cableSheetKey(distroId, n)) === '1';
        } catch (_) {
            return false;
        }
    }

    _setCableSheetOpen(distroId, n, open) {
        try {
            if (open) localStorage.setItem(this._cableSheetKey(distroId, n), '1');
            else localStorage.removeItem(this._cableSheetKey(distroId, n));
        } catch (_) { /* no storage: the flip lasts the render */ }
    }

    // A NEW DISTRO STARTS WITH EVERY SHEET DOWN AND EVERY SECTION OPEN,
    // the power side of _forgetHardwareViews. A multi's cable sheet and the
    // distro's folds are remembered under the distro's id, and distro ids
    // come back: a new one takes the next number after the highest
    // (addDistro), so removing DISTRO 2 and adding one hands "d2" out
    // again, and so do undo and every new show. So the memory goes with
    // the distro: every power render forgets the keys of distros not in
    // the project, an add forgets its new id's (`ids`), and another show
    // opening or File > New forgets them all (`all`). A reload keeps them.
    _forgetDistroViews({ all = false, ids = null } = {}) {
        const live = new Set();
        if (!all) {
            const fresh = new Set((ids || []).map(String));
            ((this.project && this.project.distros) || []).forEach(d => {
                if (d && !fresh.has(String(d.id))) live.add(String(d.id));
            });
        }
        const patterns = [
            /^lrd_cable_sheet_(.+)_\d+$/,
            /^ledRasterPanelCollapsed_hwdock-distro-(.+)$/,
            /^ledRasterPanelCollapsed_hwdock-multi-(.+)-\d+$/,
            /^ledRasterPanelCollapsed_hwdock-drow-([^-]+)-.+$/,
        ];
        try {
            const gone = [];
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i) || '';
                for (const re of patterns) {
                    const m = re.exec(k);
                    if (m && !live.has(m[1])) { gone.push(k); break; }
                }
            }
            gone.forEach(k => localStorage.removeItem(k));
        } catch (_) { /* no storage: nothing was remembered */ }
    }

    _dockBuildCableSheetButton(d, n) {
        const open = this._cableSheetOpen(d.id, n);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'hw-dock-cablebtn' + (open ? ' hw-dock-cablebtn-on' : '');
        btn.textContent = '≡';
        btn.title = open
            ? 'Cable sheet. Click to show the chips again.'
            : 'Cable sheet: a length and connector per circuit, for the '
                + 'paperwork. Click to flip the chips into the sheet.';
        btn.dataset.lrdField = `power-cable-sheet-${d.id}-${n}`;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            this._setCableSheetOpen(d.id, n, !open);
            this.renderHardwareDock();
        });
        return btn;
    }

    // One box's sheet: the quick fills on top, then tail · circuit ·
    // screen · ft · connector, a free tail as a dim row with no fields,
    // totals under the rows (this box's pull list: count by length and
    // connector). Each commit - one length, one connector, one quick fill
    // - is ONE 'Set Circuit Cable' entry; the DOM restates a macrotask
    // later so the Tab the change rode lands on a real element
    // (_rebuildAfterGesture). The controls sit ABOVE the rows on both
    // sheets ("move snake and quick fill to the top", 2026-09-07).
    _dockBuildCableSheet(d, n, boxSize, byTail) {
        // The sheet names the unit by its type - "this Multi 208" - the way
        // the type chip does; no generic noun (2026-09-07).
        const typeName = this.distroBoxType(d, n).type.name;
        const sheet = document.createElement('div');
        sheet.className = 'hw-dock-cablesheet';
        const table = document.createElement('table');
        const thead = document.createElement('tr');
        // NO. is the circuit's number on this unit (the header names the unit).
        ['no.', 'circuit', 'screen', 'cable', 'connector'].forEach(h => {
            const th = document.createElement('th');
            th.textContent = h;
            thead.appendChild(th);
        });
        table.appendChild(thead);
        const layerOf = (id) => (this.project.layers || [])
            .find(l => l.id === id);
        const connectors = this.getPowerCableConnectors();
        const held = [];   // {layer, circuit} - every circuit on this box
        const ftInputs = [];
        const commit = (layer, circuit, ft, connector) => {
            const changed = this.setCircuitCable(
                layer, circuit, { ft, connector: connector || null });
            if (!changed) {
                // A locked screen or a length that is no length refused it
                // (the setter said why), or "30m" converted to the figure
                // already stored: redraw so the row shows the cable kept.
                this._rebuildAfterGesture(() => this.renderHardwareDock());
                return;
            }
            this.saveClientSideProperties();
            if (window.canvasRenderer) window.canvasRenderer.render();
            this._rebuildAfterGesture(() => this.renderHardwareDock());
        };
        for (let t = 1; t <= boxSize; t++) {
            const holders = byTail.get(t) || [];
            if (!holders.length) {
                const tr = document.createElement('tr');
                tr.className = 'hw-dock-cable-free';
                const td0 = document.createElement('td');
                td0.textContent = String(t);
                tr.appendChild(td0);
                const td1 = document.createElement('td');
                td1.textContent = 'free';
                td1.colSpan = 4;
                tr.appendChild(td1);
                table.appendChild(tr);
                continue;
            }
            holders.forEach((h, hi) => {
                const layer = layerOf(h.layerId);
                if (!layer) return;
                held.push({ layer, circuit: h.circuit });
                const stored = (layer.powerCircuitCables || {})[h.circuit]
                    || null;
                const tr = document.createElement('tr');
                const td0 = document.createElement('td');
                td0.textContent = hi === 0 ? String(t) : '';
                tr.appendChild(td0);
                const td1 = document.createElement('td');
                td1.textContent = h.label;
                tr.appendChild(td1);
                const td2 = document.createElement('td');
                td2.className = 'hw-dock-cable-who';
                td2.textContent = h.who;
                tr.appendChild(td2);

                // The length: blank is no cable. Tab walks THIS column -
                // the sheet exists so six cables is one open - and the
                // connector stays a click away for the odd one.
                const td3 = document.createElement('td');
                // Text, so a length in the other unit can be typed and
                // converted ("30m" in a feet show, readTypedLength).
                const ft = document.createElement('input');
                ft.type = 'text';
                ft.inputMode = 'decimal';
                ft.placeholder = '';
                ft.className = 'hw-dock-cable-ft';
                ft.value = stored && Number(stored.ft) > 0
                    ? String(stored.ft) : '';
                ft.dataset.lrdField = `power-cable-ft-${layer.id}-${h.circuit}`;
                // The field keeps what was typed; the tooltip says how the
                // show's cable stock writes it out (cableStockHint).
                ft.title = `Length in ${this.cableUnitWord()}. Blank = no cable.`
                    + this.cableStockHint(stored && stored.ft, 'circuit');
                td3.appendChild(ft);
                td3.appendChild(document.createTextNode(` ${this.cableUnitAbbr()}`));
                tr.appendChild(td3);

                const td4 = document.createElement('td');
                const sel = document.createElement('select');
                sel.className = 'hw-dock-cable-connector';
                sel.dataset.lrdField =
                    `power-cable-connector-${layer.id}-${h.circuit}`;
                // what a blank pick prints: the box's tail connector, or on a
                // direct output the cable outlet to panel ("Edison → TRUE1")
                let follows = this.cableConnectorName(
                    this.boxTailConnector(d, n, layer)) || '';
                const direct = typeof this.faceBox === 'function' ? this.faceBox(d, n) : null;
                if (direct && direct.kind === 'direct') follows = this.directCableType(follows, layer);
                const blank = document.createElement('option');
                blank.value = '';
                // The plug first: the select is narrow, and "follows Multi
                // 208 (TRUE1)" cut the TRUE1 off, then "TRUE1 (follows
                // Socapex 208V)" cut the box off (QA 1.6.0-beta.4). The
                // plug and "default"; the title says what it follows.
                blank.textContent = follows
                    ? `${follows} (default)` : `follows ${typeName}`;
                sel.appendChild(blank);
                connectors.forEach(c => {
                    const o = document.createElement('option');
                    o.value = c.id;
                    o.textContent = c.name;
                    sel.appendChild(o);
                });
                sel.value = stored && stored.connector
                    && connectors.some(c => c.id === stored.connector)
                    ? stored.connector : '';
                sel.title = `The plug on this cable. Follows the ${typeName} `
                    + 'unless changed, so only the odd one needs picking.';
                td4.appendChild(sel);
                tr.appendChild(td4);

                ft.addEventListener('change', () => {
                    commit(layer, h.circuit, ft.value.trim(), sel.value);
                });
                sel.addEventListener('change', () => {
                    commit(layer, h.circuit, ft.value.trim(), sel.value);
                });
                ft.addEventListener('keydown', (e) => {
                    if (e.key !== 'Tab') return;
                    const i = ftInputs.indexOf(ft);
                    const next = ftInputs[e.shiftKey ? i - 1 : i + 1];
                    if (!next) return;
                    e.preventDefault();
                    next.focus();
                    if (typeof next.select === 'function') next.select();
                });
                ftInputs.push(ft);
                table.appendChild(tr);
            });
        }
        // This box's pull list, the way the packet's back page counts it:
        // by length and connector. A flat readout, not a control.
        const counts = new Map();
        held.forEach(({ layer, circuit }) => {
            const own = this.powerCircuitCable(layer, circuit);
            if (!own) return;
            // a circuit alone on a direct output: its cable is the output's
            // one cable, from the direct-output stock (directCircuitCable)
            const c = this.directCircuitCable(layer, circuit) || own;
            counts.set(c.text, (counts.get(c.text) || 0) + 1);
        });
        const tot = document.createElement('tr');
        tot.className = 'hw-dock-cable-total';
        const tl = document.createElement('td');
        tl.colSpan = 3;
        tl.textContent = `this ${typeName}`;
        tot.appendChild(tl);
        const tv = document.createElement('td');
        tv.colSpan = 2;
        tv.textContent = counts.size
            ? [...counts.entries()].map(([k, v]) => `${v} × ${k}`).join(' · ')
            : 'no cables';
        tot.appendChild(tv);
        table.appendChild(tot);
        sheet.appendChild(table);

        // Quick fill: every held circuit on THIS box gets the one length
        // (its connector pick untouched), or forgets its cable. ONE entry.
        // Above the table, the data sheet's order.
        const quick = document.createElement('div');
        quick.className = 'hw-dock-cable-quick';
        const cap = document.createElement('span');
        cap.textContent = 'Quick fill:';
        quick.appendChild(cap);
        // The one write every fill on this sheet makes - a fixed button's
        // length, the typed one's, or null to forget: every held circuit,
        // ONE updateLayers over the layers it touched.
        const apply = (ft) => {
            const touched = new Set();
            held.forEach(({ layer, circuit }) => {
                const cur = (layer.powerCircuitCables || {})[circuit];
                const changed = this.setCircuitCable(layer, circuit,
                    ft === null ? null
                        : { ft, connector: cur ? cur.connector : null },
                    false);
                if (changed) touched.add(layer);
            });
            if (!touched.size) return;
            this.saveClientSideProperties();
            this.updateLayers([...touched], true, 'Set Circuit Cable');
            if (window.canvasRenderer) window.canvasRenderer.render();
            this._rebuildAfterGesture(() => this.renderHardwareDock());
        };
        const fill = (label, ft, title) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'btn hw-dock-btn';
            b.textContent = label;
            b.title = title;
            b.dataset.lrdField =
                `power-cable-fill-${d.id}-${n}-${ft === null ? 'none' : ft}`;
            b.addEventListener('click', (e) => {
                e.stopPropagation();
                apply(ft);
            });
            return b;
        };
        // The first fill is the Power cable preference (10' as shipped),
        // read here where the cables are made; the 6' beside it stays
        // unless the preference is 6' itself. In a meters show the same
        // two in meters: the preference (3 m as shipped) and 2 m (6' to
        // the nearest meter).
        const prefFt = this.defaultPowerCableFt();
        const second = this.cableUnit() === 'm' ? 2 : 6;
        quick.appendChild(fill(`all ${this.cableLengthText(prefFt)}`, prefFt,
            `Every circuit on this ${typeName} gets a ${this.cableLengthWords(prefFt)} cable. One undo step.`));
        if (prefFt !== second) {
            quick.appendChild(fill(`all ${this.cableLengthText(second)}`, second,
                `Every circuit on this ${typeName} gets a ${this.cableLengthWords(second)} cable. One undo step.`));
        }
        quick.appendChild(fill('none', null,
            `Every circuit on this ${typeName} forgets its cable. One undo step.`));
        // ...and a length of the user's own, after the fixed ones ("adding
        // quick fill of any length I choose would be nice for cable
        // sheets", 2026-09-24): the same write as the buttons beside it.
        this._cableQuickAny(quick, `power-cable-fill-any-${d.id}-${n}`, 'all',
            `Every circuit on this ${typeName} gets the typed length. `
            + 'One undo step.', apply);
        sheet.insertBefore(quick, table);
        return sheet;
    }

    // A typed length beside a row's fixed fills - the number box and the
    // button that fires it (Enter in the box does the same). The box
    // takes what a row's own length field takes (in the show's unit), and
    // refuses what it refuses: blank, zero, a minus or text write nothing
    // and the box goes back to the last length it filled with (blank if
    // none) - `none` is the button for forgetting, so a refusal never
    // clears anything. The last accepted length rides in memory per box
    // so the rebuild after a fill shows it again, the length in force.
    _cableQuickAny(row, key, label, title, run) {
        const memo = this._cableQuickAnyFt || (this._cableQuickAnyFt = {});
        const box = document.createElement('input');
        box.type = 'text';
        box.inputMode = 'decimal';
        box.placeholder = this.cableUnitAbbr();
        box.className = 'hw-dock-cable-ft';
        box.value = memo[key] ? String(memo[key]) : '';
        box.dataset.lrdField = key;
        box.title = `A length of your own, in ${this.cableUnitWord()}. Enter, or the button `
            + 'beside it, fills with it.';
        const go = () => {
            // read the way every typed length is: "30m" in a feet show
            // fills with 98.4, said; text that is no length is refused
            const read = this.readTypedLength(box.value.trim(), 'cable');
            const ft = read.n;
            if (!read.ok || ft === null) {
                box.value = memo[key] ? String(memo[key]) : '';
                if (read.ok) this._dockSay(`Type a length in ${this.cableUnitWord()} first.`);
                return;
            }
            memo[key] = ft;
            run(ft);
        };
        box.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            e.stopPropagation();
            go();
        });
        row.appendChild(box);
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn hw-dock-btn';
        b.textContent = label;
        b.title = title;
        b.dataset.lrdField = `${key}-btn`;
        b.addEventListener('click', (e) => {
            e.stopPropagation();
            go();
        });
        row.appendChild(b);
    }


    // ── data cables: the sheet, the sweep and the brackets ───────────────
    //
    // "we need to have the same option for data homeruns. we can combine
    // ports into a snake as well as adding lengths to each if not snakes."
    // (user, 2026-09-06). Of mocks/snake-mock.html the pick was "B to
    // form it and A to type it but can be made with both": the Alt-sweep
    // across port chips (the canvas 2fer's own gesture) forms a snake by
    // right-click, and the ≡ on a card's or box's header flips its chips
    // into a cable sheet that types names, home runs and the loose ports'
    // lengths - the power sheet transposed. The stores live on the
    // hardware record (app-processors.js, the data cable model); this is
    // where they are read and typed. Which face a record shows is a
    // viewing choice, remembered per record in localStorage and never in
    // the project - the fold state's doctrine.

    _dataCableSheetKey(owner) {
        return `lrd_data_cable_sheet_${owner.kind}_${owner.id}`;
    }

    _dataCableSheetOpen(owner) {
        try {
            return localStorage.getItem(this._dataCableSheetKey(owner)) === '1';
        } catch (_) {
            return false;
        }
    }

    _setDataCableSheetOpen(owner, open) {
        try {
            if (open) localStorage.setItem(this._dataCableSheetKey(owner), '1');
            else localStorage.removeItem(this._dataCableSheetKey(owner));
        } catch (_) { /* no storage: the flip lasts the render */ }
    }

    // A NEW CARD OR BOX STARTS WITH ITS SHEET DOWN AND ITS SECTION UNFOLDED
    // (owner, beta.4: a new MX 4x10G and CVT10 came up with their cable
    // sheets open "as if leftover from another system"). Both memories are
    // keyed by the record's id, and ids are not forever: every show numbers
    // its hardware from 1, and undo rewinds the counter, so an add undone
    // and made again hands out the same id. So the memory goes with the
    // record: _applyProcessorState calls this with every tree it adopts,
    // and a key whose card or box is not in that tree goes - a removed
    // record, an add undone. `all` (another show opening, File > New)
    // forgets every card's and box's; a plain page reload keeps them.
    _forgetHardwareViews(resolved, all = false) {
        const live = new Set();
        if (!all) {
            (resolved || []).forEach(p => (p.slots || []).forEach(s => {
                // the processor's own cable list (_dockBuildProcCableSheet)
                live.add(`proc:${p.id}`);
                if (!s.card) return;
                live.add(`card:${s.card.id}`);
                (s.card.cvts || []).forEach(c => live.add(`cvt:${c.id}`));
            }));
        }
        const patterns = [
            [/^lrd_data_cable_sheet_(card|cvt|proc)_(.+)$/, m => `${m[1]}:${m[2]}`],
            [/^ledRasterPanelCollapsed_hwdock-(card|box)-(.+)$/,
             m => `${m[1] === 'box' ? 'cvt' : 'card'}:${m[2]}`],
        ];
        try {
            const gone = [];
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                for (const [re, owner] of patterns) {
                    const m = re.exec(k || '');
                    if (m && !live.has(owner(m))) gone.push(k);
                }
            }
            gone.forEach(k => localStorage.removeItem(k));
        } catch (_) { /* no storage: nothing was remembered */ }
    }

    _dockBuildDataCableSheetButton(owner) {
        const open = this._dataCableSheetOpen(owner);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'hw-dock-cablebtn hw-dock-cablebtn-data'
            + (open ? ' hw-dock-cablebtn-on' : '');
        btn.textContent = '≡';
        btn.title = open
            ? 'Cable sheet. Click to show the chips again.'
            : 'Cable sheet: snakes and home runs per port, for the '
                + 'paperwork. Click to flip into the sheet.';
        btn.dataset.lrdField = `data-cable-sheet-${owner.id}`;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            this._setDataCableSheetOpen(owner, !open);
            this.renderHardwareDock();
        });
        return btn;
    }

    // Tick state for the sheet's "With ticked" buttons - in memory, keyed
    // by owner and socket, so it rides the tray's wholesale rebuilds the
    // way the open tile does and dies with the page like every gesture.
    _cableTickKey(owner, socket) {
        return `${owner.kind}:${owner.id}:${socket}`;
    }

    _cableTicked(owner, socket) {
        return !!(this._cableTicks && this._cableTicks.has(
            this._cableTickKey(owner, socket)));
    }

    _setCableTick(owner, socket, on) {
        if (!this._cableTicks) this._cableTicks = new Set();
        const key = this._cableTickKey(owner, socket);
        if (on) this._cableTicks.add(key);
        else this._cableTicks.delete(key);
    }

    // The same tick, addressed as a snake member - a tick lives on
    // (owner, socket) and a member IS an (owner, socket), so the two are
    // the same key seen from either end.
    _cableTickedMember(member) {
        return this._cableTicked({ kind: member.kind, id: member.id },
                                 member.socket);
    }

    _setCableTickMember(member, on) {
        this._setCableTick({ kind: member.kind, id: member.id },
                           member.socket, on);
    }

    // EVERY ticked socket in the tray, on every card and every box, as
    // snake members. The ticks already live in memory keyed by owner and
    // socket, so they survive the tray's rebuilds and cross its units -
    // which is exactly what "ports 1-4 primary is snaked and backup 1-4
    // are snaked. then i have 5 and 6 that i want to snake" needs: tick
    // A-5, A-6 on one sheet and B-5, B-6 on another, press Snake on
    // either, and the four are ONE 4 channel snake. A tick on a socket that has
    // since gone (a card cleared under it) is dropped here rather than
    // sent to be refused.
    _allTickedMembers() {
        const out = [];
        (this._cableTicks || new Set()).forEach(key => {
            const at = key.lastIndexOf(':');
            const socket = parseInt(key.slice(at + 1), 10);
            const [kind, id] = [key.slice(0, key.indexOf(':')),
                                key.slice(key.indexOf(':') + 1, at)];
            const owner = this._dataCableOwner(kind, id);
            if (!owner || !Number.isFinite(socket)) return;
            if (!(owner.rec.ports || []).some(p => p.number === socket)) return;
            out.push({ kind, id, socket });
        });
        return out.sort((a, b) => (a.id === b.id
            ? a.socket - b.socket : (a.id < b.id ? -1 : 1)));
    }

    _clearAllCableTicks() {
        if (this._cableTicks) this._cableTicks.clear();
    }

    // One record's sheet: tick · port · screen · home run - FOUR columns
    // (sheet-fit-mock.html Option A, 2026-09-07: "cat is the only option
    // we have in the app", so the plug is a fact of the port and not
    // asked; the stores keep `connector`, the pull list reads it through
    // dataPortConnectorId, nothing here writes it). A snake is a folded
    // row (tick · "SNAKE A · 6 channel" · name · ft) with its members dim
    // under it carrying their extensions, a free socket dim. ABOVE the
    // rows: "With ticked: Snake / Unsnake" and the quick fills - and on a
    // box, above those, its Fiber section (_dockBuildBoxFiberSection). Each
    // commit is ONE entry ('Set Port Cable' / 'Set Snake Home Run' /
    // 'Rename Snake' / 'Snake Ports' / 'Unsnake'); the DOM restates after
    // the round-trip, and Tab walks the ft column across it.
    _dockBuildDataCableSheet(owner, ports) {
        const sheet = document.createElement('div');
        sheet.className = 'hw-dock-cablesheet hw-dock-cablesheet-data';
        sheet.dataset.lrdCableSheet = `${owner.kind}:${owner.id}`;
        const table = document.createElement('table');
        const thead = document.createElement('tr');
        ['', 'port', 'screen', 'home run'].forEach(h => {
            const th = document.createElement('th');
            th.textContent = h;
            thead.appendChild(th);
        });
        table.appendChild(thead);
        const ftInputs = [];
        const walk = (ft) => {
            ft.addEventListener('keydown', (e) => {
                if (e.key !== 'Tab') return;
                const i = ftInputs.indexOf(ft);
                const next = ftInputs[e.shiftKey ? i - 1 : i + 1];
                if (!next) return;
                e.preventDefault();
                next.focus();
                if (typeof next.select === 'function') next.select();
            });
            ftInputs.push(ft);
        };
        const after = () => {
            if (window.canvasRenderer) window.canvasRenderer.render();
        };
        const ftInput = (key, value, title) => {
            // text, so "30m" in a feet show can be typed (readTypedLength)
            const ft = document.createElement('input');
            ft.type = 'text';
            ft.inputMode = 'decimal';
            ft.placeholder = '';
            ft.className = 'hw-dock-cable-ft';
            ft.value = Number(value) > 0 ? String(value) : '';
            ft.dataset.lrdField = key;
            ft.title = title;
            return ft;
        };
        // The HOME RUN cell, the SAME three slots on every row (2026-09-09:
        // "also these columns dont line up" - the member rows' "ext" pushed
        // their inputs right of the snake rows', so the inputs and their
        // "ft" units zigzagged down the column). Fixed-width slots, because
        // each row is its own table cell and only fixed widths line up
        // across rows: [word, 30px, right-aligned] [the ft input, one
        // width for every row] ["ft"].
        const runCell = (word, ft) => {
            const td = document.createElement('td');
            const run = document.createElement('div');
            run.className = 'hw-dock-cable-run';
            const slot = document.createElement('span');
            slot.className = 'hw-dock-cable-word hw-dock-cable-dim';
            slot.textContent = word || '';
            run.appendChild(slot);
            run.appendChild(ft);
            const unit = document.createElement('span');
            unit.className = 'hw-dock-cable-unit';
            unit.textContent = this.cableUnitAbbr();
            run.appendChild(unit);
            td.appendChild(run);
            return td;
        };
        const tick = (key, on, title, onChange) => {
            const box = document.createElement('input');
            box.type = 'checkbox';
            box.className = 'hw-dock-cable-tick';
            box.checked = on;
            box.dataset.lrdField = key;
            box.title = title;
            box.addEventListener('change', () => onChange(box.checked));
            return box;
        };
        // The SCREEN cell names the screen and nothing else - a return end
        // reads "SR - MAIN" exactly as the primary does ("it can look just
        // like the primary", 2026-09-07: "SR - MAIN p1 return, SR - MAIN p2
        // return, ..." on a backup box's snake row pushed the HOME RUN and
        // CONNECTOR cells off the sheet). The "p1 return" detail rides the
        // row's title instead, read on hover. whoOf feeds the cell, whoDetail
        // the title; a snake row dedupes both across its members.
        const whoOf = (at, n) => {
            const occ = this._portOccupants(at.cardId, n);
            if (!occ.length) return '';
            return [...new Set(occ.map(o => o.name))].join(', ');
        };
        const whoDetail = (at, n) => {
            const occ = this._portOccupants(at.cardId, n);
            if (!occ.length) return '';
            return [...new Set(occ.map(o => `${o.name}${o.role === 'return'
                ? ` P${o.number} return` : ''}`))].join(', ');
        };
        // The cell wears its full text as a title too, and a row whose
        // detail says more than its cell - a return end - carries it on
        // the row. The text sits in a block of its own inside the cell:
        // style.css cuts it to an ellipsis at ~24ch, and a block's
        // max-width caps what it asks of the column, where a cap on the
        // cell itself still lets the table grow to the text's full width.
        const who = (td, tr, text, detail) => {
            td.className = 'hw-dock-cable-who';
            const span = document.createElement('span');
            span.className = 'hw-dock-cable-who-text';
            span.textContent = text;
            td.appendChild(span);
            if (detail) td.title = detail;
            if (detail && detail !== text) tr.title = detail;
        };
        const seenSnakes = new Set();
        // A snake's channel count on the sheet is the WHOLE snake (2026-09-09:
        // "Any sockets, any device"), and a sheet that can only show part
        // of one says the rest out loud: "+ 5, 6 on BOX B" under the name.
        // The number and the rows cannot disagree, because everything the
        // number counts is named on the row one way or the other.
        // A row of ANOTHER box (`sheetOwner` - a loop's far box on its
        // primary's folded sheet, _dockSheetPorts) is that box's own row:
        // its keys, its ticks, its stored entry. `sheetCaption` names the
        // box above its first row.
        const sheetOwner = owner;
        ports.forEach(port => {
            const owner = port.sheetOwner || sheetOwner;
            if (port.sheetCaption) {
                const cap = document.createElement('tr');
                cap.className = 'hw-dock-cable-caption';
                cap.dataset.lrdCableCaption = owner.id;
                const td = document.createElement('td');
                td.colSpan = 4;
                td.className = 'hw-dock-cable-dim';
                td.textContent = port.sheetCaption;
                cap.appendChild(td);
                table.appendChild(cap);
            }
            const n = port.number;
            const spoken = port.localNumber || n;
            // A box backing up its own outputs: the backup output's row
            // (boxSheetPorts' `cableKey`) is a cable of its own - its own
            // length, no snake, no tick (a snake holds the main output).
            const own = port.cableKey || null;
            const snake = own ? null : this.dataPortSnake(owner, n);
            if (snake && !seenSnakes.has(snake.id)) {
                seenSnakes.add(snake.id);
                const tr = document.createElement('tr');
                tr.className = 'hw-dock-cable-snake';
                tr.dataset.lrdSnakeRow = snake.id;
                const td0 = document.createElement('td');
                // The whole snake ticks together, members on other devices
                // included: Unsnake takes the loom apart, not the half of
                // it this sheet happens to list.
                const members = (snake.members || []);
                const all = members.every(
                    m => this._cableTickedMember(m));
                td0.appendChild(tick(
                    `data-snake-tick-${owner.id}-s-${snake.id}`, all,
                    'Tick the whole snake, wherever its sockets sit, for '
                    + 'Unsnake above.',
                    (on) => members.forEach(
                        m => this._setCableTickMember(m, on))));
                tr.appendChild(td0);
                const td1 = document.createElement('td');
                const cap = document.createElement('span');
                cap.className = 'hw-dock-cable-snake-cap';
                cap.textContent = this.snakeTagText(snake, false);
                td1.appendChild(cap);
                const name = document.createElement('input');
                name.type = 'text';
                name.className = 'hw-dock-cable-name';
                name.value = snake.name || '';
                name.placeholder = 'name';
                // Sized to its text, the header name fields' rule, so a
                // longer name grows the sheet (the mock's Option B half:
                // "if we pass a threshold then grow like option B").
                name.size = Math.max(6, (snake.name || '').length + 1);
                name.dataset.lrdField = `data-snake-name-${owner.id}-${snake.id}`;
                name.title = 'The snake’s name: what the packet and '
                    + 'the tag on the map print. Typed names win over the '
                    + 'SNAKE A default.';
                name.addEventListener('change', () => {
                    this.setSnake(snake.id, { name: name.value },
                                  'Rename Snake').then(after);
                });
                td1.appendChild(name);
                // The members this sheet cannot show, said plainly and dim
                // (2026-09-09: a snake spans devices now, and the sheet it
                // is read from must still account for every way it claims).
                const away = this.snakeElsewhere(snake, owner);
                if (away.length) {
                    const also = document.createElement('span');
                    also.className = 'hw-dock-cable-snake-away';
                    also.textContent = ` + ${away.map(a => a.text).join('; ')}`;
                    also.title = 'This snake also holds these sockets, on '
                        + `another ${this.showUnitOrBox()}. Its name and home run are `
                        + 'the same row there.';
                    td1.appendChild(also);
                }
                tr.appendChild(td1);
                const td2 = document.createElement('td');
                // The SCREEN cell speaks for the whole snake, its members
                // elsewhere included - the loom feeds what it feeds.
                const onAll = (f) => (snake.members || []).map(m => {
                    const at = this._dataCableOwner(m.kind, m.id);
                    return at ? f(at, m.socket) : '';
                });
                const uniq = (f) => [...new Set(onAll(f)
                    .filter(Boolean))].join(', ');
                who(td2, tr, uniq(whoOf), uniq(whoDetail));
                tr.appendChild(td2);
                const ft = ftInput(`data-snake-ft-${owner.id}-${snake.id}`,
                                   snake.ft,
                                   `The snake’s home run in ${this.cableUnitWord()}. `
                                   + 'Blank = no length.'
                                   + this.cableStockHint(snake.ft, 'data'));
                ft.addEventListener('change', () => {
                    this.setSnake(snake.id, { ft: ft.value.trim() },
                                  'Set Snake Home Run').then(after);
                });
                walk(ft);
                // A snake row's word slot is EMPTY - the slot still takes
                // its 30px, so the input below it starts at the same x.
                tr.appendChild(runCell('', ft));
                table.appendChild(tr);
            }
            const tr = document.createElement('tr');
            const occupied = !!this._portOccupants(owner.cardId, n).length;
            if (snake) tr.className = 'hw-dock-cable-member';
            else if (!occupied) tr.className = 'hw-dock-cable-free';
            const td0 = document.createElement('td');
            if (!own) td0.appendChild(tick(
                `data-snake-tick-${owner.id}-${n}`,
                this._cableTicked(owner, n),
                snake ? 'Tick, then Unsnake above to take this port out of '
                        + 'its snake.'
                    : 'Tick, then Snake above to form a snake of the ticked '
                        + 'ports.',
                (on) => this._setCableTick(owner, n, on)));
            tr.appendChild(td0);
            const td1 = document.createElement('td');
            // A port-by-port backup's socket: its silkscreen, then the port
            // it backs up ("1 · backs up port 11 on CVT4K-S A-B").
            const backs = port.loopOf
                ? this._dockLoopBackedName((this._dockFindCard(owner.cardId) || {}).card, port)
                : '';
            td1.textContent = backs
                ? `${spoken} · backs up ${port.label || backs}`
                : (port.label ? `${spoken} · ${port.label}` : String(spoken));
            tr.appendChild(td1);
            const td2 = document.createElement('td');
            who(td2, tr, whoOf(owner, n) || (occupied ? '' : 'free'),
                whoDetail(owner, n));
            tr.appendChild(td2);
            // The same store on both kinds of row: a loose port's entry is
            // its home run, a member's is its EXTENSION from the snake's
            // fan-out to the panel ("ext 25 ft" - the shorter cable a
            // fan-out sometimes needs, 2026-09-07); the member row stays
            // dim under its snake and still ticks for Unsnake. The entry's
            // connector, if one was stored, rides the commit untouched.
            const stored = (owner.rec.portCables || {})[own || String(n)] || null;
            const ft = ftInput(`data-cable-ft-${owner.id}-${own || n}`,
                               stored && stored.ft,
                               (snake
                                   ? 'Extension from the snake to this '
                                     + `panel, in ${this.cableUnitWord()}: the shorter cable `
                                     + 'a snake’s fan-out sometimes needs. '
                                     + 'Blank = none.'
                                   : `This port’s own home run in ${this.cableUnitWord()}. `
                                     + 'Blank = no cable.')
                               + this.cableStockHint(stored && stored.ft, 'data'));
            const commit = () => this.setPortCable(owner, own || n, {
                ft: ft.value.trim(),
                connector: (stored && stored.connector) || null,
            }).then(after);
            ft.addEventListener('change', commit);
            walk(ft);
            tr.appendChild(runCell(snake ? 'ext' : '', ft));
            table.appendChild(tr);
        });
        // The fills below write the sheet's own record only, as they always
        // have: another box's rows are typed one by one, or filled from
        // that box's own sheet.
        const ownPorts = ports.filter(p => !p.sheetOwner);

        // With ticked: Snake / Unsnake. Quick fill: all 100' / none. On
        // TOP of the sheet, before the rows ("move snake and quick fill
        // to the top instead of the bottom", 2026-09-07).
        const quick = document.createElement('div');
        quick.className = 'hw-dock-cable-quick';
        const button = (label, key, title, run) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'btn hw-dock-btn';
            b.textContent = label;
            b.title = title;
            b.dataset.lrdField = key;
            b.addEventListener('click', (e) => {
                e.stopPropagation();
                run();
            });
            return b;
        };
        // A caption and its controls is one group: the row folds BETWEEN
        // the groups on a narrow sheet, never between a length box and
        // the button that fires it.
        const group = (text) => {
            const g = document.createElement('span');
            g.className = 'hw-dock-cable-quick-group';
            const cap = document.createElement('span');
            cap.textContent = text;
            g.appendChild(cap);
            quick.appendChild(g);
            return g;
        };
        const ticked = group('With ticked:');
        // ONE snake of EVERY ticked socket in the tray - this sheet's and
        // any other's. "Any sockets, any device" (2026-09-09): the ticks
        // are the gesture, and the button they are pressed on is only
        // where the hand happened to be.
        ticked.appendChild(button('Snake', `data-cable-snake-${owner.id}`,
            `Form one snake of every ticked port, on this ${this.unitWordForCard(owner.cardId)} or box or `
            + 'any other. One name, one home run. One undo step.',
            () => {
                const members = this._allTickedMembers();
                if (members.length < 1) {
                    this._dockSay('Tick the ports first, then Snake.');
                    return;
                }
                const away = members.filter(
                    m => !(m.kind === owner.kind && m.id === owner.id)).length;
                this._clearAllCableTicks();
                this.snakePorts(members).then(() => {
                    if (away) {
                        this._dockSay(`Snaked ${members.length} ports, `
                            + `${away} of them on another ${this.showUnitOrBox()}.`);
                    }
                    after();
                });
            }));
        ticked.appendChild(button('Unsnake', `data-cable-loosen-${owner.id}`,
            `Take every ticked port out of its snake, on this ${this.unitWordForCard(owner.cardId)} or box `
            + 'or any other. One undo step.',
            () => {
                const members = this._allTickedMembers().filter(m => {
                    const at = this._dataCableOwner(m.kind, m.id);
                    return at && this.dataPortSnake(at, m.socket);
                });
                if (!members.length) {
                    this._dockSay('Tick a port that is in a snake, then '
                        + 'Unsnake.');
                    return;
                }
                this._clearAllCableTicks();
                this.loosenPorts(members).then(after);
            }));
        // ...and a length for the ticked rows only ("same with 'with
        // ticked' - adding a length for all ticked boxes only",
        // 2026-09-24): each ticked row gets what its own field would
        // take - a loose port its home run, a snaked one its extension.
        this._cableQuickAny(ticked, `data-cable-ticked-fill-${owner.id}`, 'Fill',
            `Every ticked port on this ${this.unitWordForCard(owner.cardId)} or box gets the typed length: `
            + 'a loose port as its home run, a snaked port as its extension. '
            + 'One undo step.',
            (ft) => this.fillTickedPortCables(owner, ft, ownPorts).then(after));
        const sp = document.createElement('span');
        sp.style.flex = '1';
        quick.appendChild(sp);
        const fills = group('Quick fill:');
        // The fill's length is the Loose port cable preference (100' /
        // 30 m as shipped) - read here, where the cables are made.
        const fillFt = this.defaultLoosePortCableFt();
        fills.appendChild(button(`all ${this.cableLengthText(fillFt)}`, `data-cable-fill-${owner.id}-${fillFt}`,
            `Every loose port here gets a ${this.cableLengthWords(fillFt)} home run; snakes keep `
            + 'theirs. One undo step.',
            () => this.fillPortCables(owner, fillFt, ownPorts).then(after)));
        fills.appendChild(button('none', `data-cable-fill-${owner.id}-none`,
            'Every loose port here forgets its cable; snakes keep theirs. '
            + 'One undo step.',
            () => this.fillPortCables(owner, null, ownPorts).then(after)));
        // ...and a length of the user's own, the loose ports' fill with
        // the typed length ("this should just be for extensions for
        // individual ports or circuits", 2026-09-24): snakes keep theirs,
        // as the fixed buttons leave them.
        this._cableQuickAny(fills, `data-cable-fill-any-${owner.id}`, 'all',
            'Every loose port here gets the typed length as its home run; '
            + 'snakes keep theirs. One undo step.',
            (ft) => this.fillPortCables(owner, ft, ownPorts).then(after));
        // A box's fiber is the sheet's FIRST block, above the quick fills
        // and the ports (2026-09-25) - a fact of the box, not of a port, so
        // the fills below it never reach it.
        if (owner.kind === 'cvt') sheet.appendChild(this._dockBuildBoxFiberSection(owner));
        sheet.appendChild(quick);
        sheet.appendChild(table);
        return sheet;
    }

    // THE BOX'S FIBER SECTION - the sheet's first block, above the quick
    // fills and the ports (2026-09-25). A box's trunk links each take a
    // cable of the show's (app-fiber.js): one row per link, named by the
    // box's own port - X1, OPT 1 - then the backup inputs (X2, OPT 3-4)
    // where its processor has a backup unit, tinted - each with its cable
    // select,
    // the strands it takes as swatched chips (click one to change it), and
    // Edit for the cable's own fields. "New TAC…" asks the strand count,
    // then the length, then the ends; "New MTP…" the count and the length;
    // an opticalCON its length. An XD's link may be copper instead - the
    // kind picked in the same select, then its length, with a plain
    // warning past the kind's 10G run. The BiDi switch (one strand a link)
    // shows only where the box's vendor offers it. A LOOP's two boxes (an
    // SX40's XD A and B, a NovaStar backup box and its primary) are two
    // boxes with their own links, shown as ONE section on either box's
    // sheet - "Fiber · USR A ↔ USR B (loop)", the near box's rows first,
    // each row named by its box - and drawn once where both sheets are
    // open, on the near box's. A backup bound port by port is one group
    // with every box it loops with (fiberLoopGroup): a CVT4K-S on OPT 5-6
    // behind CVT10s on OPT 1 and 2 reads "Fiber · CVT10 A, CVT10 B ↔
    // CVT4K-S E-F (loop)", drawn on the first primary's sheet where that
    // is open. A 1.3 typed fiber stays as a read-only
    // note, with Clear,
    // until a link has a cable. Every commit is ONE request and ONE history
    // entry; the server refuses with the reason. The row's element keys are
    // the tests' and focus restore's - always the box that owns the link.
    _dockBuildBoxFiberSection(owner) {
        const box = owner.rec;
        const sec = document.createElement('div');
        sec.className = 'hw-dock-cable-fiber';
        sec.dataset.lrdFiberRow = box.id;
        const button = (label, key, title, run, into) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'btn hw-dock-btn';
            b.textContent = label;
            b.title = title;
            b.dataset.lrdField = key;
            b.addEventListener('click', (e) => {
                e.stopPropagation();
                run();
            });
            if (into) into.appendChild(b);
            return b;
        };
        const line = (cls) => {
            const d = document.createElement('div');
            d.className = cls;
            sec.appendChild(d);
            return d;
        };
        const text = (cls, t) => {
            const s = document.createElement('span');
            s.className = cls;
            s.textContent = t;
            return s;
        };
        const titleOf = (b) => b.displayTitle || b.name || b.deviceName;

        const pair = this.fiberLoopGroup(box);
        const head = line('hw-dock-fiber-head');
        if (pair) {
            const lead = pair.nears[0];
            head.appendChild(text('hw-dock-cable-fiber-cap',
                `Fiber · ${pair.nears.map(titleOf).join(', ')} ↔ `
                + `${pair.fars.map(titleOf).join(', ')} (loop)`));
            sec.dataset.lrdFiberLoop = [...pair.nears, ...pair.fars].map(b => b.id).join(':');
            if (lead && box.id !== lead.id
                    && this._dataCableSheetOpen({ kind: 'cvt', id: lead.id })) {
                const row = line('hw-dock-fiber-bound');
                row.appendChild(text('hw-dock-fiber-bound-text',
                    `Set with ${titleOf(lead)} on its sheet.`));
                return sec;
            }
        } else {
            const tag = box.copyRole === 'mirror' ? ' (mirror)'
                : (box.duplicateOf && !box.backupOf && !this.boxLoopMixed(box) ? ' (copy)' : '');
            // a backup of the unit's own ports alone: which ones
            const hit = this._fiberAllBoxes().find(b => b.box.id === box.id);
            const loop = this.boxLoopText(box, hit ? hit.card.cvts : [], titleOf);
            head.appendChild(text('hw-dock-cable-fiber-cap',
                `Fiber · ${titleOf(box)}${tag}${loop ? ` (${loop})` : ''}`));
        }
        const members = pair ? [...pair.nears, ...pair.fars] : [box];
        // The fiber's mode where the boxes state one (owner, 2026-11-04):
        // "Single mode" / "Multimode" after the caption - each box's own
        // where a pair's boxes differ.
        const words = this.fiberModesText(members, titleOf);
        if (words) {
            const tag = text('hw-dock-fiber-mode', words);
            tag.dataset.lrdField = `fiber-mode-${box.id}`;
            tag.title = 'The fiber this box takes. Single mode and multimode never share a fiber cable.';
            head.appendChild(tag);
        }
        members.forEach(m => {
            if (!m.bidiAllowed) return;
            const lab = document.createElement('label');
            lab.className = 'hw-dock-fiber-bidi';
            lab.title = 'BiDi optics: each link takes ONE strand instead of '
                + 'two. Switching it re-fits this box’s links.';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = !!m.bidi;
            cb.dataset.lrdField = `fiber-bidi-${m.id}`;
            cb.addEventListener('change', () => this.setBoxFiber(
                m, { bidi: cb.checked }, 'Set BiDi'));
            lab.appendChild(cb);
            lab.appendChild(document.createTextNode(pair ? ` BiDi ${titleOf(m)}` : ' BiDi'));
            head.appendChild(lab);
        });

        // The ends a TAC is offered (typing any other is fine), for the
        // New TAC step and the cable editor below.
        const ends = document.createElement('datalist');
        ends.id = `hw-fiber-connectors-${box.id}`;
        TAC_CONNECTORS.forEach(c => {
            const o = document.createElement('option');
            o.value = c;
            ends.appendChild(o);
        });
        sec.appendChild(ends);
        members.forEach(m => {
            // The 1.3 note: read-only, with Clear, until a link has a cable.
            const note = this.fiberLegacyNote(m);
            if (note && !this.fiberBoxHasLink(m)) {
                const row = line('hw-dock-fiber-legacy');
                row.appendChild(text('hw-dock-fiber-dim', pair ? `${titleOf(m)} note: ` : 'Note: '));
                row.appendChild(text('hw-dock-fiber-legacy-text', note));
                row.title = 'What was typed on this box before fiber cables. It '
                    + 'prints on the pull sheet until a link has a cable.';
                button('Clear', `fiber-note-clear-${m.id}`,
                    'Forget the typed note. One undo step.',
                    () => this._processorRequest(this._fiberBoxUrl(m), 'PUT',
                        { fiberType: '', fiberFt: null }, 'Clear Fiber Note'), row);
            }
            for (const l of this.fiberBoxLinks(m)) {
                const row = line('hw-dock-fiber-link' + (l.backup ? ' hw-dock-fiber-link-backup' : ''));
                row.dataset.lrdFiberLink = `${m.id}:${l.key}`;
                row.appendChild(text('hw-dock-fiber-role', pair ? `${titleOf(m)} · ${l.title}` : l.title));
                row.appendChild(this._dockBuildFiberSelect(m, l));
                if (l.copper) {
                    row.appendChild(this._dockBuildCopperName(m, l));
                    row.appendChild(this._dockBuildCopperLength(m, l));
                    const over = this.copperOverText(l.copper);
                    if (over) row.appendChild(text('hw-dock-fiber-warn', over));
                } else if (l.cable) {
                    // This is the box's sheet, so a TAC's pair reads the way
                    // it plugs in here: the pair crosses between its ends, so
                    // the 1 Blue · 2 Orange stored (the processor's order) is
                    // 2 Orange · 1 Blue at the box - the binder's Fiber
                    // connections AT THE INPUT. An MTP or opticalCON crosses
                    // inside the cable and reads as stored. Each chip keeps
                    // its own index, so a pick still edits its own strand.
                    const order = (l.link.strands || []).map((st, i) => [st, i]);
                    if (l.cable.kind === 'tac') order.reverse();
                    order.forEach(([st, i]) =>
                        row.appendChild(this._dockBuildFiberStrandChip(m, l, st, i)));
                    button('Edit', `fiber-edit-${m.id}-${l.key}`,
                        `${l.cable.name}’s name, strand count, length, ends and `
                        + 'strand names.',
                        () => {
                            const open = this._fiberEdit && this._fiberEdit.boxId === m.id
                                && this._fiberEdit.key === l.key;
                            this._fiberEdit = open ? null : { boxId: m.id, key: l.key };
                            this.renderHardwareDock();
                        }, row);
                    // A TAC or an MTP may need an extension to reach the
                    // box's port (owner, 2026-11-02): "+ Extension" adds
                    // one to THIS link; its line follows the row.
                    if (this.fiberCableIsStranded(l.cable) && !this.fiberLinkExtension(l)) {
                        button('+ Extension', `fiber-ext-add-${m.id}-${l.key}`,
                            `A fan-out or patch between ${l.cable.name}’s end and `
                            + `${l.title}. One undo step.`,
                            () => this.setFiberExtension(m, l.key, {}, 'Add Fiber Extension'), row);
                    }
                }
                if (this.fiberLinkExtension(l)) sec.appendChild(this._dockBuildFiberExtension(m, l));
                const wz = this._fiberWizard;
                if (wz && wz.boxId === m.id && wz.key === l.key) {
                    sec.appendChild(this._dockBuildFiberWizard(m, l));
                }
                const ed = this._fiberEdit;
                if (l.cable && ed && ed.boxId === m.id && ed.key === l.key) {
                    sec.appendChild(this._dockBuildFiberEditor(m, l));
                }
            }
        });
        return sec;
    }

    // A link's EXTENSION, on its own line right under the link's row
    // (owner, 2026-11-02): the cable between the TAC's or MTP's end and
    // the box's port - its kind (a fan-out or a duplex patch), the
    // connector at the trunk end (blank reads the trunk's own) and at the
    // box end, each offered from the fiber connector list or typed, and
    // its length in the show's unit. Remove takes it off in one click.
    // Each commit is one request and one history entry. Nothing here says
    // which connector the box's port takes: the user's pick is recorded.
    _dockBuildFiberExtension(box, l) {
        const ext = this.fiberLinkExtension(l);
        const ends = this.fiberExtensionEnds(ext, l.cable);
        const base = `${box.id}-${l.key}`;
        const line = document.createElement('div');
        line.className = 'hw-dock-fiber-ext' + (l.backup ? ' hw-dock-fiber-link-backup' : '');
        line.dataset.lrdFiberExt = `${box.id}:${l.key}`;
        const put = (body) => this.setFiberExtension(box, l.key, body);
        const cap = document.createElement('span');
        cap.className = 'hw-dock-fiber-dim hw-dock-fiber-ext-cap';
        const mode = this.fiberModeWord(this.fiberCableMode(l.cable));
        cap.textContent = `${l.title} extension` + (mode ? ` · ${mode}` : '');
        line.appendChild(cap);
        const kind = document.createElement('select');
        kind.className = 'hw-dock-cable-connector hw-dock-fiber-select';
        kind.dataset.lrdField = `fiber-ext-kind-${base}`;
        kind.title = 'A fan-out (breakout harness) or a plain duplex patch.';
        FIBER_EXTENSION_KINDS.forEach(([v, t]) => {
            const o = document.createElement('option');
            o.value = v;
            o.textContent = t;
            kind.appendChild(o);
        });
        kind.value = ext.kind;
        kind.addEventListener('change', () => put({ kind: kind.value }));
        line.appendChild(kind);
        const listId = `hw-fiber-ext-connectors-${base}`;
        const list = document.createElement('datalist');
        list.id = listId;
        FIBER_EXTENSION_CONNECTORS.forEach(c => {
            const o = document.createElement('option');
            o.value = c;
            list.appendChild(o);
        });
        line.appendChild(list);
        const end = (key, value, title, write) => {
            const f = document.createElement('input');
            f.type = 'text';
            f.className = 'hw-dock-fiber-text hw-dock-fiber-ext-end';
            f.dataset.lrdField = key;
            f.value = value;
            f.title = title;
            f.setAttribute('list', listId);
            f.addEventListener('change', () => write(f.value.trim()));
            line.appendChild(f);
            return f;
        };
        const own = this.fiberCableEndText(l.cable);
        const trunk = end(`fiber-ext-trunk-${base}`, ends.trunk,
            `The connector at ${l.cable.name}’s end.`
            + (own ? ` Blank reads ${own}, the trunk’s own.` : ''),
            // the trunk's own connector, typed again, is stored as blank
            // so it keeps following the trunk
            (v) => put({ trunkEnd: v === own ? '' : v }));
        trunk.placeholder = own || 'trunk end';
        line.appendChild(document.createTextNode(' to '));
        end(`fiber-ext-box-${base}`, ends.box, `The connector at ${l.title}.`,
            (v) => put({ boxEnd: v })).placeholder = 'box end';
        const ft = document.createElement('input');
        ft.type = 'text';
        ft.inputMode = 'decimal';
        ft.className = 'hw-dock-cable-ft';
        ft.placeholder = this.cableUnitAbbr();
        ft.dataset.lrdField = `fiber-ext-ft-${base}`;
        const len = this.parseCableLength(ext.ft);
        ft.value = len !== null ? String(len) : '';
        ft.title = `The extension's length in ${this.cableUnitWord()}.`;
        ft.addEventListener('change', () => {
            // read the way every typed length is (readTypedLength)
            const read = this.readTypedLength(ft.value.trim(), 'extension');
            if (!read.ok) return;
            put({ ft: read.n });
        });
        line.appendChild(ft);
        line.appendChild(document.createTextNode(` ${this.cableUnitAbbr()} `));
        const rm = document.createElement('button');
        rm.type = 'button';
        rm.className = 'btn hw-dock-btn';
        rm.textContent = 'Remove';
        rm.title = 'Take this extension off the link. One undo step.';
        rm.dataset.lrdField = `fiber-ext-remove-${base}`;
        rm.addEventListener('click', (e) => {
            e.stopPropagation();
            this.setFiberExtension(box, l.key, null, 'Remove Fiber Extension');
        });
        line.appendChild(rm);
        return line;
    }

    // A copper link's NAME, its label the way a fiber cable has one (owner,
    // 2026-11-07): "Cat6A 1" until another is typed; a blank hands the
    // link its default back. Its kind and length ride the write untouched.
    // One request, one entry.
    _dockBuildCopperName(box, l) {
        const f = document.createElement('input');
        f.type = 'text';
        f.className = 'hw-dock-fiber-text hw-dock-fiber-copper-name';
        f.dataset.lrdField = `fiber-copper-name-${box.id}-${l.key}`;
        f.value = l.copper.name || '';
        f.placeholder = l.copper.copper;
        f.title = `The name this ${l.copper.copper} run is labeled by, on the box's sheet, `
            + 'the binder and the pull sheet. Blank gives it its default name back.';
        f.addEventListener('change', () => {
            const ft = l.copper.ft;
            this.setFiberLink(box, l.key, { copper: l.copper.copper, ft: ft == null ? null : ft,
                                            name: f.value.trim() }, 'Rename Copper Link');
        });
        return f;
    }

    // A copper link's length, in the show's unit: blank is no length. Its
    // kind and name ride the write untouched. One request, one entry.
    _dockBuildCopperLength(box, l) {
        const wrap = document.createElement('span');
        wrap.className = 'hw-dock-fiber-field';
        const f = document.createElement('input');
        f.type = 'text';
        f.inputMode = 'decimal';
        f.className = 'hw-dock-cable-ft';
        f.placeholder = this.cableUnitAbbr();
        f.dataset.lrdField = `fiber-copper-ft-${box.id}-${l.key}`;
        const ft = this.parseCableLength(l.copper.ft);
        f.value = ft !== null ? String(ft) : '';
        const max = this.copperLinkMax(l.copper.copper);
        f.title = `The ${l.copper.copper} run's length in ${this.cableUnitWord()}`
            + (max ? `. ${this.copperLinkMaxWords(max)} is its 10G maximum.` : '.');
        f.addEventListener('change', () => {
            // read the way every typed length is (readTypedLength): the
            // other unit converted and said, text that is no length refused
            const read = this.readTypedLength(f.value.trim(), 'cable');
            if (!read.ok) return;
            this.setFiberLink(box, l.key, { copper: l.copper.copper, ft: read.n }, 'Set Copper Length');
        });
        wrap.appendChild(f);
        wrap.appendChild(document.createTextNode(` ${this.cableUnitAbbr()}`));
        return wrap;
    }

    // One link's cable select: the show's TACs and MTPs ("TAC A · 12 ·
    // 1000' · ST"), then every opticalCON in the show with the free strands
    // this link needs - an opticalCON is shared like a TAC (owner,
    // 2026-10-08), so a QUAD made on one box is offered on the next while
    // it has strands to give; the one this link already takes is always
    // listed - the four New… entries, and None. An unset backup link lists
    // its primary link's cable first - the default the owner asked for -
    // and picking any cable takes its next free strands.
    _dockBuildFiberSelect(box, l) {
        const sel = document.createElement('select');
        sel.className = 'hw-dock-cable-connector hw-dock-fiber-select';
        sel.dataset.lrdField = `fiber-link-cable-${box.id}-${l.key}`;
        sel.title = 'The cable this link takes. Picking one takes its next '
            + 'free strands; click a strand to change it.'
            + (box.copperLinks ? ' Or run it on copper, Cat6A and under.' : '');
        const opt = (value, label) => {
            const o = document.createElement('option');
            o.value = value;
            o.textContent = label;
            sel.appendChild(o);
        };
        // A gap between the groups of the list - a disabled rule, so the
        // eye finds the cables, the New steps, copper and None apart.
        const gap = () => {
            const o = document.createElement('option');
            o.disabled = true;
            o.textContent = '──────────';
            sel.appendChild(o);
        };
        // An opticalCON is listed while it has the strands this link needs
        // (1 on a BiDi box, else 2) free of other links - or when this link
        // already takes it.
        const need = box.bidi ? 1 : 2;
        const fits = (c) => {
            if (l.link && l.link.cable === c.id) return true;
            const users = this.fiberStrandUsers(c.id);
            let free = 0;
            for (let n = 1; n <= (c.strands || 0); n++) {
                const who = users.get(n);
                if (!who || (who.box.id === box.id && who.key === l.key)) free++;
            }
            return free >= need;
        };
        const connectors = this.getFiberCables().filter(c => !this.fiberCableIsStranded(c) && fits(c));
        const stranded = this.getFiberCables().filter(c => this.fiberCableIsStranded(c));
        // A TAC or MTP with too few strands left for this link is listed
        // but cannot be picked, and says so ("· full"): a pick the server
        // would only refuse is never sent (beta.4 QA: a full TAC drew a
        // 400 and an odd toast).
        const strandedOpt = (c, label) => {
            opt(c.id, fits(c) ? label : `${label} · full`);
            if (!fits(c)) sel.options[sel.options.length - 1].disabled = true;
        };
        // An empty backup link offers its primary's cable ON TOP, named as
        // such and set off by a gap, and the full list follows in its own
        // order - "that reads as confusing ... maybe we do this with a
        // gap" (owner, 2026-09-25), where it used to reorder the list.
        if (l.backup && !l.link) {
            const pKey = `p${l.key.slice(1)}`;
            const primary = ((box.fiberLinks || {})[pKey] || {}).cable;
            const same = primary && (stranded.find(c => c.id === primary)
                || connectors.find(c => c.id === primary));
            if (same) {
                const port = (box.linkTitles || {})[pKey] || 'the primary';
                strandedOpt(same, `${this.fiberCableOptionText(same)} · same as ${port}`);
                gap();
            }
        }
        stranded.forEach(c => strandedOpt(c, this.fiberCableOptionText(c)));
        connectors.forEach(c => opt(c.id, this.fiberCableOptionText(c)));
        if (sel.options.length) gap();
        opt('new:tac', 'New TAC…');
        opt('new:mtp', 'New MTP…');
        opt('new:opticalcon-duo', 'New opticalCON DUO…');
        opt('new:opticalcon-quad', 'New opticalCON QUAD…');
        // An XD's link may run on copper instead (its etherCON beside the
        // opticalCON DUO) - the 10G kinds, Cat6A and under.
        if (box.copperLinks) {
            gap();
            // each by its kind alone (owner, 2026-11-07: "don't need to
            // add copper")
            COPPER_LINK_KINDS.forEach(([kind]) => opt(`cu:${kind}`, kind));
        }
        gap();
        opt('', 'None');
        sel.value = l.copper ? `cu:${l.copper.copper}` : (l.link ? l.link.cable : '');
        sel.addEventListener('change', () => {
            const v = sel.value;
            if (v.startsWith('cu:')) {
                const ft = l.copper ? l.copper.ft : null;
                this.setFiberLink(box, l.key, { copper: v.slice(3), ft: ft == null ? null : ft },
                                  'Set Copper Link');
                return;
            }
            if (v.startsWith('new:')) {
                this._fiberWizard = { boxId: box.id, key: l.key, kind: v.slice(4),
                                      step: v === 'new:tac' || v === 'new:mtp' ? 'strands' : 'ft',
                                      focus: true };
                this.renderHardwareDock();
                return;
            }
            if (!v) {
                this.setFiberLink(box, l.key, { cable: null }, 'Clear Fiber Link');
                return;
            }
            this.setFiberLink(box, l.key, { cable: v }, 'Set Fiber Link');
        });
        return sel;
    }

    // Which strand pick a rebuild must draw open: the one the person is
    // standing in with no choice made yet. A rebuild nobody asked for (a
    // save's late echo, a peer's edit) put the chip back under them and the
    // pick was gone before they could use it; _preserveEditorFocus then
    // hands the focus to the pick drawn in its place. A pick already
    // answered stays out: its own save closes it.
    _fiberPickOpenKey() {
        const a = document.activeElement;
        const key = a && a.dataset ? a.dataset.lrdField : null;
        return key && key.startsWith('fiber-strand-pick-')
            && !a.dataset.lrdPicked ? key : null;
    }

    // A strand as a chip: its swatch (the tracer as a stripe) and its name.
    // A click turns it into a pick of the cable's strands - the ones other
    // links hold are listed, disabled, with who holds them.
    _dockBuildFiberStrandChip(box, l, strand, i) {
        const cable = l.cable;
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'hw-dock-fiber-strand';
        chip.dataset.lrdField = `fiber-strand-${box.id}-${l.key}-${i}`;
        chip.title = `Strand ${strand} of ${cable.name}. Click to change it.`;
        chip.appendChild(this._fiberSwatch(strand, cable));
        chip.appendChild(document.createTextNode(this.fiberStrandName(strand, cable)));
        const pickKey = `fiber-strand-pick-${box.id}-${l.key}-${i}`;
        const buildPick = () => {
            const users = this.fiberStrandUsers(cable.id);
            const sel = document.createElement('select');
            sel.className = 'hw-dock-cable-connector hw-dock-fiber-select';
            sel.dataset.lrdField = pickKey;
            for (let n = 1; n <= (cable.strands || 0); n++) {
                const o = document.createElement('option');
                o.value = String(n);
                const who = users.get(n);
                const mine = who && who.box.id === box.id && who.key === l.key;
                o.textContent = this.fiberStrandName(n, cable) + (who && !mine
                    ? ` · ${who.box.displayTitle || who.box.deviceName} · ${this.fiberLinkTitle(who.key, who.box)}` : '');
                o.disabled = !!who && !mine;
                sel.appendChild(o);
            }
            sel.value = String(strand);
            let changed = false;
            sel.addEventListener('change', () => {
                changed = true;
                sel.dataset.lrdPicked = '1';
                const strands = (l.link.strands || []).slice();
                strands[i] = parseInt(sel.value, 10);
                this.setFiberLink(box, l.key, { cable: cable.id, strands }, 'Set Fiber Strands');
            });
            sel.addEventListener('blur', () => { if (!changed) sel.replaceWith(chip); });
            return sel;
        };
        chip.addEventListener('click', (e) => {
            e.stopPropagation();
            const sel = buildPick();
            chip.replaceWith(sel);
            sel.focus();
        });
        return this._fiberPickOpen === pickKey ? buildPick() : chip;
    }

    _fiberSwatch(strand, cable) {
        const sw = document.createElement('span');
        sw.className = 'hw-dock-fiber-swatch';
        const { base, tracer } = this.fiberStrandSwatch(strand, cable);
        sw.style.background = tracer
            ? `linear-gradient(135deg, ${base} 0 58%, ${tracer} 58% 100%)` : base;
        return sw;
    }

    // "New TAC…" and its siblings, one step at a time under the link's row:
    // the strand count (TAC, MTP), the length, the ends (TAC). The cable is
    // made with this link on it in ONE request - one undo step - and takes
    // strands 1..n of it. Enter moves on; Cancel drops it.
    _dockBuildFiberWizard(box, l) {
        const wz = this._fiberWizard;
        const word = this.fiberKindWord(wz.kind);
        const div = document.createElement('div');
        div.className = 'hw-dock-fiber-wizard';
        div.dataset.lrdFiberWizard = `${box.id}:${l.key}`;
        const cap = document.createElement('span');
        cap.className = 'hw-dock-fiber-dim';
        div.appendChild(cap);
        const button = (label, key, title, run) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'btn hw-dock-btn';
            b.textContent = label;
            b.title = title;
            b.dataset.lrdField = key;
            b.addEventListener('click', (e) => {
                e.stopPropagation();
                run();
            });
            div.appendChild(b);
            return b;
        };
        const field = (type, key, value, placeholder, onEnter) => {
            const f = document.createElement('input');
            f.type = type;
            f.className = type === 'number' ? 'hw-dock-cable-ft' : 'hw-dock-fiber-text';
            if (type === 'number') { f.min = '0'; f.step = 'any'; }
            f.value = value == null ? '' : String(value);
            f.placeholder = placeholder;
            f.dataset.lrdField = key;
            f.addEventListener('keydown', (e) => {
                if (e.key !== 'Enter') return;
                e.preventDefault();
                e.stopPropagation();
                onEnter();
            });
            div.appendChild(f);
            if (wz.focus) {
                wz.focus = false;
                // By the next frame the tray may have been redrawn (a socket
                // echo, the column redeal) and `f` replaced, so focus the
                // field that is there then, found by its key.
                requestAnimationFrame(() => {
                    const live = document.querySelector(`[data-lrd-field="${key}"]`);
                    (live || f).focus();
                });
            }
            return f;
        };
        const step = (next) => {
            Object.assign(wz, next, { focus: true });
            this.renderHardwareDock();
        };
        const create = () => {
            const body = { kind: wz.kind, link: { boxId: box.id, key: l.key } };
            if (wz.kind === 'tac' || wz.kind === 'mtp') body.strands = wz.strands;
            if (wz.ft) body.ft = wz.ft;
            if (wz.connector) body.connector = wz.connector;
            this._fiberWizard = null;
            this.createFiberCable(body, `New ${word}`);
        };
        const base = `fiber-new-${box.id}-${l.key}`;
        if (wz.step === 'strands') {
            cap.textContent = `New ${word} · strands:`;
            const take = (n) => {
                const v = parseInt(n, 10);
                if (!(Number.isFinite(v) && v >= 1 && String(v) === String(n).trim())) {
                    this._dockSay('Type a whole number of strands, 1 or more.');
                    return;
                }
                step({ strands: v, step: 'ft' });
            };
            FIBER_STRAND_SUGGESTIONS.forEach(n => button(String(n), `${base}-strands-${n}`,
                `A ${n}-strand ${word}.`, () => take(n)));
            const f = field('number', `${base}-strands`, wz.strands, 'n', () => take(f.value));
            f.step = '1';
            f.min = '1';
            button('Next', `${base}-strands-next`, 'On to the length.', () => take(f.value));
        } else if (wz.step === 'ft') {
            cap.textContent = `New ${word} · length:`;
            const go = () => {
                const read = this.readTypedLength(f.value.trim(), word);
                if (!read.ok) return;
                const v = read.n;
                if (wz.kind === 'tac') step({ ft: v, step: 'connector' });
                else { wz.ft = v; create(); }
            };
            // text, so "30m" in a feet show can be typed (readTypedLength)
            const f = field('text', `${base}-ft`, wz.ft, this.cableUnitAbbr(), go);
            f.className = 'hw-dock-cable-ft';
            f.inputMode = 'decimal';
            div.appendChild(document.createTextNode(` ${this.cableUnitAbbr()} `));
            button(wz.kind === 'tac' ? 'Next' : 'Create', `${base}-ft-next`,
                wz.kind === 'tac' ? 'On to the ends.' : `Make the ${word} on this link.`, go);
        } else {
            cap.textContent = `New ${word} · ends:`;
            TAC_CONNECTORS.forEach(c => button(c, `${base}-conn-${c.replace(/\s+/g, '-')}`,
                `${c} on both ends. Makes the TAC on this link.`,
                () => { wz.connector = c; create(); }));
            const f = field('text', `${base}-conn`, wz.connector, 'other', () => {
                wz.connector = f.value.trim();
                create();
            });
            f.setAttribute('list', `hw-fiber-connectors-${box.id}`);
            button('Create', `${base}-create`, 'Make the TAC on this link, ends as typed, '
                + 'or none.', () => { wz.connector = f.value.trim(); create(); });
        }
        button('Cancel', `${base}-cancel`, 'Make nothing.', () => {
            this._fiberWizard = null;
            this.renderHardwareDock();
        });
        return div;
    }

    // One cable's own fields, under the link it was opened from. Each
    // commit is one request and one history entry.
    _dockBuildFiberEditor(box, l) {
        const cable = l.cable;
        const ed = document.createElement('div');
        ed.className = 'hw-dock-fiber-editor';
        ed.dataset.lrdFiberEditor = cable.id;
        const put = (body, action) => this.setFiberCable(cable.id, body, action);
        const field = (label, el) => {
            const lab = document.createElement('label');
            lab.className = 'hw-dock-fiber-field';
            const s = document.createElement('span');
            s.className = 'hw-dock-fiber-dim';
            s.textContent = label;
            lab.appendChild(s);
            lab.appendChild(el);
            ed.appendChild(lab);
            return el;
        };
        const input = (type, key, value, cls) => {
            const f = document.createElement('input');
            f.type = type;
            f.className = cls || (type === 'number' ? 'hw-dock-cable-ft' : 'hw-dock-fiber-text');
            f.value = value == null ? '' : String(value);
            f.dataset.lrdField = key;
            return f;
        };
        const name = field('name', input('text', `fiber-cable-name-${cable.id}`, cable.name));
        name.addEventListener('change', () => put({ name: name.value }, 'Rename Fiber Cable'));
        if (this.fiberCableIsStranded(cable)) {
            const n = field('strands', input('number', `fiber-cable-strands-${cable.id}`, cable.strands));
            n.min = '1';
            n.step = '1';
            n.addEventListener('change', () => {
                const v = parseInt(n.value, 10);
                if (!(Number.isFinite(v) && v >= 1)) {
                    n.value = String(cable.strands);
                    this._dockSay('Type a whole number of strands, 1 or more.');
                    return;
                }
                put({ strands: v }, 'Set Fiber Strand Count');
            });
        }
        const ft = field(this.cableUnitAbbr(), input('text', `fiber-cable-ft-${cable.id}`,
            Number(cable.ft) > 0 ? cable.ft : '', 'hw-dock-cable-ft'));
        ft.inputMode = 'decimal';
        ft.placeholder = '';
        ft.addEventListener('change', () => {
            // read the way every typed length is (readTypedLength)
            const read = this.readTypedLength(ft.value.trim(), 'fiber');
            if (!read.ok) return;
            put({ ft: read.n }, 'Set Fiber Length');
        });
        if (cable.kind === 'tac') {
            const conn = field('ends', input('text', `fiber-cable-connector-${cable.id}`, cable.connector));
            conn.placeholder = 'ST, LC duplex …';
            conn.setAttribute('list', `hw-fiber-connectors-${box.id}`);
            conn.addEventListener('change', () => put({ connector: conn.value.trim() }, 'Set Fiber Ends'));
        }
        const labels = document.createElement('select');
        labels.className = 'hw-dock-cable-connector hw-dock-fiber-select';
        labels.dataset.lrdField = `fiber-cable-labels-${cable.id}`;
        [['colors', 'colors'], ['numbers', 'numbers']].forEach(([v, t]) => {
            const o = document.createElement('option');
            o.value = v;
            o.textContent = t;
            labels.appendChild(o);
        });
        labels.value = cable.labels === 'numbers' ? 'numbers' : 'colors';
        field('strands read', labels).addEventListener('change',
            () => put({ labels: labels.value }, 'Set Strand Labels'));
        const sub = input('checkbox', `fiber-cable-subunits-${cable.id}`, '', 'hw-dock-fiber-check');
        sub.checked = !!cable.subunits;
        field('sub-units of 12', sub).addEventListener('change',
            () => put({ subunits: sub.checked }, 'Set Strand Labels'));
        const names = document.createElement('div');
        names.className = 'hw-dock-fiber-names';
        const plain = { ...cable, strandNames: {} };
        for (let n = 1; n <= (cable.strands || 0); n++) {
            const cell = document.createElement('label');
            cell.className = 'hw-dock-fiber-name';
            cell.appendChild(this._fiberSwatch(n, cable));
            const f = input('text', `fiber-strand-name-${cable.id}-${n}`,
                (cable.strandNames || {})[String(n)] || '');
            f.placeholder = fiberStrandName(n, plain);
            f.title = `Strand ${n}'s name. Blank reads ${f.placeholder}.`;
            f.addEventListener('change', () => put(
                { strandName: { strand: n, name: f.value } }, 'Rename Strand'));
            cell.appendChild(f);
            names.appendChild(cell);
        }
        ed.appendChild(names);
        const done = document.createElement('button');
        done.type = 'button';
        done.className = 'btn hw-dock-btn';
        done.textContent = 'Done';
        done.dataset.lrdField = `fiber-edit-done-${cable.id}`;
        done.addEventListener('click', (e) => {
            e.stopPropagation();
            this._fiberEdit = null;
            this.renderHardwareDock();
        });
        ed.appendChild(done);
        return ed;
    }

    // "With ticked: Fill" - the typed length into ONLY the ticked rows of
    // this sheet, each taking what its own field takes: a loose socket's
    // entry is its home run, a snaked socket's its extension from the
    // fan-out (the same portCables store, read apart by whether the
    // socket is snaked - setPortCable's rule). A stored connector rides
    // the write untouched. Ticks on other cards or boxes are not this
    // sheet's rows - one owner, one PUT, one entry ('Set Port Cable', or
    // 'Set Port Extension' when every ticked row is a member). The ticks
    // are the gesture and the fill consumes them, as Snake does; nothing
    // ticked says so and writes nothing.
    fillTickedPortCables(owner, ft, ports) {
        const list = (ports || owner.rec.ports || [])
            .filter(p => this._cableTicked(owner, p.number));
        if (!list.length) {
            this._dockSay('Tick the ports first, then Fill.');
            return Promise.resolve();
        }
        const stores = this._dataCableStores(owner);
        const before = JSON.stringify(stores.portCables);
        let snaked = 0;
        list.forEach(p => {
            const key = String(p.number);
            const cur = stores.portCables[key] || {};
            const next = { ft };
            if (cur.connector) next.connector = cur.connector;
            stores.portCables[key] = next;
            if (this.dataPortSnake(owner, p.number)) snaked += 1;
        });
        if (JSON.stringify(stores.portCables) === before) {
            return Promise.resolve();
        }
        list.forEach(p => this._setCableTick(owner, p.number, false));
        return this._dataCablePut(owner, stores,
            snaked === list.length ? 'Set Port Extension' : 'Set Port Cable');
    }
}

for (const k of Object.getOwnPropertyNames(_DockCableSheets.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_DockCableSheets.prototype, k));
    }
}
