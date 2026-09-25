// app-dock-cable-sheets: the dock's cable sheets - a multi box or a data
// device flipped into a per-tail / per-port table where cable lengths and
// connectors are typed, the per-socket tick marks, and the localStorage
// memory of which face a box shows. Moved verbatim out of app-dock.js and
// attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';

class _DockCableSheets {
    // ── the box's cable sheet ─────────────────────────────────────────────
    //
    // "we need to be able to add cables to each circuit on the distro
    // besides just soca length or l620 length etc. like say circuit 1 needs
    // a 10ft true 1 and circuit 2 needs 6ft and 3/4 need nothing and 5
    // needs 6ft and 6 needs a 10 ft. since we are going to have those pdf
    // docs we need to be able to have that info if i want to add it."
    // (user, 2026-09-06). The fact is per circuit - a length in feet and a
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

    _dockBuildCableSheetButton(d, n) {
        const open = this._cableSheetOpen(d.id, n);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'hw-dock-cablebtn' + (open ? ' hw-dock-cablebtn-on' : '');
        btn.textContent = '≡';
        btn.title = open
            ? 'Cable sheet - click to show the chips again.'
            : 'Cable sheet - a length and connector per circuit, for the '
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
            if (!changed) return;
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
                const ft = document.createElement('input');
                ft.type = 'number';
                ft.min = '0';
                ft.step = 'any';
                ft.placeholder = '—';
                ft.className = 'hw-dock-cable-ft';
                ft.value = stored && Number(stored.ft) > 0
                    ? String(stored.ft) : '';
                ft.dataset.lrdField = `power-cable-ft-${layer.id}-${h.circuit}`;
                ft.title = 'Length in feet. Blank = no cable.';
                td3.appendChild(ft);
                td3.appendChild(document.createTextNode(' ft'));
                tr.appendChild(td3);

                const td4 = document.createElement('td');
                const sel = document.createElement('select');
                sel.className = 'hw-dock-cable-connector';
                sel.dataset.lrdField =
                    `power-cable-connector-${layer.id}-${h.circuit}`;
                const follows = this.cableConnectorName(
                    this.boxTailConnector(d, n, layer)) || '';
                const blank = document.createElement('option');
                blank.value = '';
                blank.textContent = `follows ${typeName} (${follows})`;
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
                    + 'unless changed - only the odd one needs picking.';
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
            const c = this.powerCircuitCable(layer, circuit);
            if (!c) return;
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
        // unless the preference is 6' itself.
        const prefFt = this.defaultPowerCableFt();
        quick.appendChild(fill(`all ${prefFt}'`, prefFt,
            `Every circuit on this ${typeName} gets a ${prefFt} ft cable. One undo step.`));
        if (prefFt !== 6) {
            quick.appendChild(fill("all 6'", 6,
                `Every circuit on this ${typeName} gets a 6 ft cable. One undo step.`));
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
    // takes what a row's own length field takes, whole or half feet, and
    // refuses what it refuses: blank, zero, a minus or text write nothing
    // and the box goes back to the last length it filled with (blank if
    // none) - `none` is the button for forgetting, so a refusal never
    // clears anything. The last accepted length rides in memory per box
    // so the rebuild after a fill shows it again, the length in force.
    _cableQuickAny(row, key, label, title, run) {
        const memo = this._cableQuickAnyFt || (this._cableQuickAnyFt = {});
        const box = document.createElement('input');
        box.type = 'number';
        box.min = '0';
        box.step = 'any';
        box.placeholder = 'ft';
        box.className = 'hw-dock-cable-ft';
        box.value = memo[key] ? String(memo[key]) : '';
        box.dataset.lrdField = key;
        box.title = 'A length of your own, in feet. Enter, or the button '
            + 'beside it, fills with it.';
        const go = () => {
            const ft = Number(box.value.trim());
            if (!(Number.isFinite(ft) && ft > 0)) {
                box.value = memo[key] ? String(memo[key]) : '';
                this._dockSay('Type a length in feet first.');
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

    _dockBuildDataCableSheetButton(owner) {
        const open = this._dataCableSheetOpen(owner);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'hw-dock-cablebtn hw-dock-cablebtn-data'
            + (open ? ' hw-dock-cablebtn-on' : '');
        btn.textContent = '≡';
        btn.title = open
            ? 'Cable sheet - click to show the chips again.'
            : 'Cable sheet - snakes and home runs per port, for the '
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
    // box, above those, its Fiber row (_dockBuildBoxFiberRow). Each
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
            const ft = document.createElement('input');
            ft.type = 'number';
            ft.min = '0';
            ft.step = 'any';
            ft.placeholder = '—';
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
            unit.textContent = 'ft';
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
                ? ` p${o.number} return` : ''}`))].join(', ');
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
        ports.forEach(port => {
            const n = port.number;
            const spoken = port.localNumber || n;
            const snake = this.dataPortSnake(owner, n);
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
                    'Tick the whole snake, wherever its sockets sit - for '
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
                name.title = 'The snake’s name - what the packet and '
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
                        + 'another card or box. Its name and home run are '
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
                                   'The snake’s home run in feet. '
                                   + 'Blank = no length.');
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
            td0.appendChild(tick(
                `data-snake-tick-${owner.id}-${n}`,
                this._cableTicked(owner, n),
                snake ? 'Tick, then Unsnake above to take this port out of '
                        + 'its snake.'
                    : 'Tick, then Snake above to form a snake of the ticked '
                        + 'ports.',
                (on) => this._setCableTick(owner, n, on)));
            tr.appendChild(td0);
            const td1 = document.createElement('td');
            td1.textContent = port.label
                ? `${spoken} · ${port.label}` : String(spoken);
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
            const stored = (owner.rec.portCables || {})[String(n)] || null;
            const ft = ftInput(`data-cable-ft-${owner.id}-${n}`,
                               stored && stored.ft,
                               snake
                                   ? 'Extension from the snake to this '
                                     + 'panel, in feet - the shorter cable '
                                     + 'a snake’s fan-out sometimes needs. '
                                     + 'Blank = none.'
                                   : 'This port’s own home run in feet. '
                                     + 'Blank = no cable.');
            const commit = () => this.setPortCable(owner, n, {
                ft: ft.value.trim(),
                connector: (stored && stored.connector) || null,
            }).then(after);
            ft.addEventListener('change', commit);
            walk(ft);
            tr.appendChild(runCell(snake ? 'ext' : '', ft));
            table.appendChild(tr);
        });

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
            'Form one snake of every ticked port - on this card or box or '
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
                            + `${away} of them on another card or box.`);
                    }
                    after();
                });
            }));
        ticked.appendChild(button('Unsnake', `data-cable-loosen-${owner.id}`,
            'Take every ticked port out of its snake - on this card or box '
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
            'Every ticked port on this card or box gets the typed length - '
            + 'a loose port as its home run, a snaked port as its extension. '
            + 'One undo step.',
            (ft) => this.fillTickedPortCables(owner, ft, ports).then(after));
        const sp = document.createElement('span');
        sp.style.flex = '1';
        quick.appendChild(sp);
        const fills = group('Quick fill:');
        // The fill's length is the Loose port cable preference (100' as
        // shipped) - read here, where the cables are made.
        const fillFt = this.defaultLoosePortCableFt();
        fills.appendChild(button(`all ${fillFt}'`, `data-cable-fill-${owner.id}-${fillFt}`,
            `Every loose port here gets a ${fillFt} ft home run; snakes keep `
            + 'theirs. One undo step.',
            () => this.fillPortCables(owner, fillFt, ports).then(after)));
        fills.appendChild(button('none', `data-cable-fill-${owner.id}-none`,
            'Every loose port here forgets its cable; snakes keep theirs. '
            + 'One undo step.',
            () => this.fillPortCables(owner, null, ports).then(after)));
        // ...and a length of the user's own, the loose ports' fill with
        // the typed length ("this should just be for extensions for
        // individual ports or circuits", 2026-09-24): snakes keep theirs,
        // as the fixed buttons leave them.
        this._cableQuickAny(fills, `data-cable-fill-any-${owner.id}`, 'all',
            'Every loose port here gets the typed length as its home run; '
            + 'snakes keep theirs. One undo step.',
            (ft) => this.fillPortCables(owner, ft, ports).then(after));
        // A box's fiber trunk is the sheet's FIRST row, above the quick
        // fills and the ports (2026-09-25) - a fact of the box, not of a
        // port, so the fills below it never reach it.
        if (owner.kind === 'cvt') sheet.appendChild(this._dockBuildBoxFiberRow(owner));
        sheet.appendChild(quick);
        sheet.appendChild(table);
        return sheet;
    }

    // "the fiber info to XD boxes and whatnot should be in the cable
    // lengths area not in the menu it is now" (2026-09-25): the box's
    // trunk - what the fiber is and how long its home run is - typed on
    // its ≡ sheet, where the rest of its cables are, and no longer in its
    // ⚙. Every box gets the row, backup and copy boxes included, as every
    // box's ⚙ offered the fields. The type offers the GEAR LIST's
    // fiber-ish words (12 Tac Fiber, 10G Single-Mode SFP …) and takes
    // anything typed; the feet are a number, blank clears. One PUT per
    // commit, one 'Set Box Fiber' entry; the server validates and refuses.
    // The field keys are the ones the ⚙ used, so focus restore and every
    // reader of them keep working; the classes are the row's own, so no
    // reader of the port rows' fields (.hw-dock-cable-ft / -name) finds
    // these first. Neither field is on the ft column's
    // Tab walk or under a quick fill - those are for port cables.
    _dockBuildBoxFiberRow(owner) {
        const cvt = owner.rec;
        const url = this._dataCableOwnerUrl(owner);
        const row = document.createElement('div');
        row.className = 'hw-dock-cable-fiber';
        row.dataset.lrdFiberRow = cvt.id;
        const tag = cvt.backupOf ? ' (backup)'
            : (cvt.duplicateOf ? ' (copy)' : '');
        const cap = document.createElement('span');
        cap.className = 'hw-dock-cable-fiber-cap';
        cap.textContent = `Fiber · ${cvt.displayTitle || cvt.name
            || cvt.deviceName}${tag}`;
        row.appendChild(cap);

        const type = document.createElement('input');
        type.type = 'text';
        type.className = 'hw-dock-cable-fiber-type';
        type.value = cvt.fiberType || '';
        type.placeholder = 'fiber type';
        type.dataset.lrdField = `processor-cvt-fiber-type-${cvt.id}`;
        type.title = 'The fiber that feeds this box - pick from the gear '
            + 'list or type your own. Blank clears.';
        const listId = `hw-fiber-types-${cvt.id}`;
        const list = document.createElement('datalist');
        list.id = listId;
        type.setAttribute('list', listId);
        this._fiberTypeSuggestions().then(names => {
            list.innerHTML = '';
            names.forEach(n => {
                const opt = document.createElement('option');
                opt.value = n;
                list.appendChild(opt);
            });
        });
        type.addEventListener('change', () => this._processorRequest(
            url, 'PUT', { fiberType: type.value.trim() }, 'Set Box Fiber'));
        row.appendChild(type);
        row.appendChild(list);

        const run = document.createElement('span');
        run.className = 'hw-dock-cable-fiber-run';
        const ft = document.createElement('input');
        ft.type = 'number';
        ft.min = '0';
        ft.step = 'any';
        ft.placeholder = '—';
        ft.className = 'hw-dock-cable-fiber-ft';
        ft.value = cvt.fiberFt != null ? String(cvt.fiberFt) : '';
        ft.dataset.lrdField = `processor-cvt-fiber-ft-${cvt.id}`;
        ft.title = 'The fiber’s length in feet. Blank = no length.';
        ft.addEventListener('change', () => {
            const val = ft.value.trim();
            this._processorRequest(
                url, 'PUT', { fiberFt: val === '' ? null : Number(val) },
                'Set Box Fiber');
        });
        run.appendChild(ft);
        const unit = document.createElement('span');
        unit.textContent = 'ft';
        run.appendChild(unit);
        row.appendChild(run);
        return row;
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
