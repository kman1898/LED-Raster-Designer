// app-port-assignment: the Port Assignment panel in the Signal sidebar.
//
// It answers one question per screen - which sending-card port does each of my
// ports sit on - and it answers it without ever changing the answer by itself.
// Looms are made up and labelled off the drawing days before anything is hung,
// so a numbering that shifted on its own would hand back a drawing that no
// longer matches what is in the truck. Every problem is drawn as a line of
// text with a button beside it, and the button is the only thing that moves
// anything.
//
// It derives nothing. The allocation order, the clashes, the overflow and the
// port labels all come back from /api/port-assignments, which resolves them in
// port_assignment.py on top of processor_catalog.py. A second implementation
// here would agree in the office and disagree on the card with a conditional
// count, which is the class of bug that ends up on site.
//
// The one thing it does own is the port REQUIREMENT it sends up. That number
// falls out of the cabinet grid, the flow pattern, any custom path drawn on
// the wall and ports that cross into a group peer, and getLayerPortsRequired
// is the single implementation of it (v0.11.0 collapsed three copies into one
// after they printed three different numbers at the user). Sending its answer
// keeps it the single implementation.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _PortAssignment {

    initPortAssignmentPanel() {
        this._assignment = null;
        this._assignmentKeyRaw = '';
        // Empty, not absent: getPortLabelText reads it on every frame from the
        // first render, which happens long before this endpoint answers.
        this._processorPortLabels = {};
        this._occupancyRaw = '';
        this.refreshPortAssignment();
    }

    // What the panel is a picture of: the cards it allocates onto and the
    // screens it allocates for. Both sides have to be in the comparison or
    // adding a processor to an unchanged set of screens would leave the panel
    // drawn as if there were still nothing to assign to.
    _assignmentKey(screens) {
        return JSON.stringify([
            (this.project && this.project.processors) || [],
            screens || this._assignmentScreens(),
        ]);
    }

    // The screens, in the order they are to be numbered. Project layer order,
    // untouched: it IS the allocation order, so sorting it here - by name, by
    // size, by anything - would renumber a show behind the user's back.
    _assignmentScreens() {
        const layers = (this.project && this.project.layers) || [];
        return layers
            .filter(l => (l.type || 'screen') === 'screen')
            .map(l => ({
                layerId: String(l.id),
                name: l.name || `Screen ${l.id}`,
                ports: (typeof this.getLayerPortsRequired === 'function'
                    ? this.getLayerPortsRequired(l) : 0) || 0,
            }))
            // A screen needing no ports has nothing to assign and would only
            // draw an empty row. Text layers are already gone above.
            .filter(s => s.ports > 0);
    }

    refreshPortAssignment() {
        const screens = this._assignmentScreens();
        this._assignmentKeyRaw = this._assignmentKey(screens);
        return this._assignmentRequest('/api/port-assignments/resolve', 'POST',
                                       { screens });
    }

    _assignmentRequest(url, method, body) {
        const payload = Object.assign({ screens: this._assignmentScreens() },
                                      body || {});
        return fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then(r => r.json().then(data => ({ ok: r.ok, data })))
            .then(({ ok, data }) => {
                if (!ok) {
                    // A refused move is not a failure to hide. It is usually
                    // "there is no run that long free", which is the thing the
                    // user needs to read.
                    this._assignmentError = data.error || 'That move is not possible.';
                    this.renderPortAssignmentPanel();
                    return;
                }
                // A move can succeed and still not do everything asked - a
                // card that took nine of the twelve overflow ports. That is
                // not an error, but it is the one thing the user needs to
                // read, so it goes in the same place an error would.
                this._assignmentError = (data.moved && data.moved.note) || null;
                if (data.resolution) this._assignment = data.resolution;
                if (data.state && this.project) {
                    this.project.port_assignments = data.state;
                }
                this._applyAssignmentResolution();
            })
            .catch(err => sendClientLog('port_assignment_request_failed',
                                        { url, method, error: String(err) }));
    }

    // Everything that has to happen when a new resolution lands, in one place
    // so no caller can update the panel and leave the drawing behind.
    //
    // A resolution is not just a picture of a sidebar: it is where the port
    // labels on the drawing come from, and it is what the Processors panel
    // reads to say which screen is sitting on each of its ports. All three
    // move together or the app shows three different answers at once.
    _applyAssignmentResolution() {
        this._indexAssignmentLabels();
        this.renderPortAssignmentPanel();
        // The Processors panel only needs redrawing when what is ON its ports
        // changed, which is why this is compared rather than simply redrawn.
        // That panel is rebuilt wholesale, so redrawing it on every resolve
        // would throw away whatever somebody was halfway through typing into a
        // card name each time a screen was resized on the other side of the
        // app. Comparing a small blob beats losing an edit.
        const occupancy = JSON.stringify(
            (this._assignment && this._assignment.occupancy) || {});
        if (occupancy !== this._occupancyRaw) {
            this._occupancyRaw = occupancy;
            if (typeof this.renderProcessorPanel === 'function') {
                this.renderProcessorPanel();
            }
        }
        // The labels on the drawing just changed, or just stopped changing.
        // Nothing else redraws the canvas on this path - the panel's own
        // render only touches the sidebar.
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Flatten the resolution into layerId -> portNumber -> label, once.
    //
    // getPortLabelText is called for every port of every screen on every
    // frame, and the resolution it would otherwise have to search is a list of
    // screens each holding a list of ports. Two object lookups instead of two
    // nested scans is the difference between a label rule and a frame-rate
    // problem on a wall with thirty screens.
    //
    // A port with no label is left OUT rather than stored as null, so the
    // lookup's own miss is the fallback: an unassigned port, a card nobody
    // named, or a project with no processor at all all land on the layer's own
    // template with nothing extra to check.
    _indexAssignmentLabels() {
        const map = {};
        const res = this._assignment;
        ((res && res.screens) || []).forEach(scr => {
            const byPort = {};
            let any = false;
            (scr.ports || []).forEach(port => {
                if (!port.label) return;
                byPort[port.number] = port.label;
                any = true;
            });
            if (any) map[String(scr.layerId)] = byPort;
        });
        this._processorPortLabels = map;
    }

    // ── drawing ───────────────────────────────────────────────────────────

    renderPortAssignmentPanel() {
        const list = document.getElementById('port-assignment-list');
        const issues = document.getElementById('port-assignment-issues');
        const foot = document.getElementById('port-assignment-foot');
        const note = document.getElementById('port-assignment-empty-note');
        if (!list || !issues || !foot) return;
        this._preserveEditorFocus();
        list.innerHTML = '';
        issues.innerHTML = '';
        foot.innerHTML = '';

        const res = this._assignment;
        if (note) {
            note.style.display = (res && res.configured) ? 'none' : '';
        }
        if (!res || !res.configured) return;

        if (this._assignmentError) {
            issues.appendChild(this._buildAssignmentNote(
                this._assignmentError, '#d05a52'));
        }
        (res.issues || []).forEach(issue => {
            issues.appendChild(this._buildIssue(issue));
        });
        (res.screens || []).forEach(scr => {
            list.appendChild(this._buildAssignmentScreen(scr, res));
        });
        foot.appendChild(this._buildAssignmentFoot(res));
    }

    _buildAssignmentNote(text, color) {
        const row = document.createElement('div');
        row.style.fontSize = '11px';
        row.style.lineHeight = '1.4';
        row.style.color = color || '#888';
        row.textContent = text;
        return row;
    }

    _buildIssue(issue) {
        const box = document.createElement('div');
        box.style.border = '1px solid #3a2a28';
        box.style.borderRadius = '4px';
        box.style.padding = '6px 8px';
        // An unknown port count, auto being off, and a card whose boxes cannot
        // reach its ceiling are all CONDITIONS - true, worth knowing, nothing
        // to answer right now. A clash, an overflow or a stranded pin is a
        // question waiting on a person. Colouring them the same would train
        // people to skim past the ones that matter.
        const mild = ['capacity-unknown', 'auto-off',
                      'card-short-of-its-ceiling'].includes(issue.kind);
        box.style.background = mild ? '#14120c' : '#1a1010';
        box.style.borderColor = mild ? '#3a3320' : '#3a2a28';
        box.appendChild(this._buildAssignmentNote(
            issue.message, mild ? '#c8a04a' : '#d08a82'));

        const offers = issue.offers || [];
        if (offers.length) {
            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.flexWrap = 'wrap';
            row.style.gap = '4px';
            row.style.marginTop = '6px';
            offers.forEach(offer => row.appendChild(this._buildOffer(offer)));
            box.appendChild(row);
        }
        return box;
    }

    _buildOffer(offer) {
        const btn = document.createElement('button');
        btn.className = 'btn';
        btn.style.padding = '4px 8px';
        btn.style.fontSize = '11px';
        btn.style.background = '#333';
        btn.textContent = offer.label || offer.action;
        // A block move re-pins the WHOLE run, this screen's existing pins
        // included. That is a real decision and the button should say so
        // before it is pressed, not after: honouring the old pins would move
        // only the auto ports and tear the run in two, which is the thing the
        // move exists to prevent. Other screens' pins are never touched.
        if (offer.action === 'move-block') {
            btn.title = 'Move every port of this screen to the next free run, '
                + 'in the same order, and hold them there. Any port of this '
                + 'screen pinned elsewhere comes with it.';
        } else if (offer.action === 'release') {
            btn.title = 'Hand these ports back to auto-numbering.';
        }
        btn.addEventListener('click', () => this._takeOffer(offer));
        return btn;
    }

    // Nothing in this panel moves a port except this function, which is the
    // whole design: every path from "the app noticed something" to "the
    // numbering changed" goes through a button somebody pressed.
    _takeOffer(offer) {
        sendClientLog('port_assignment_offer_taken', offer);
        if (offer.action === 'move-block') {
            this._assignmentRequest('/api/port-assignments/move-block', 'POST',
                                    { layerId: offer.layerId,
                                      cardId: offer.cardId || undefined });
        } else if (offer.action === 'place-overflow') {
            this._assignmentRequest('/api/port-assignments/place-overflow',
                                    'POST', { layerId: offer.layerId,
                                              cardId: offer.cardId });
        } else if (offer.action === 'release') {
            this._assignmentRequest('/api/port-assignments/unpin', 'POST',
                                    { layerId: offer.layerId,
                                      index: offer.index });
        } else if (offer.action === 'auto-on') {
            this._assignmentRequest('/api/port-assignments', 'PUT',
                                    { auto: true });
        }
    }

    _buildAssignmentScreen(scr, res) {
        const box = document.createElement('div');
        box.style.border = '1px solid #333';
        box.style.borderRadius = '4px';
        box.style.padding = '8px';
        box.style.background = '#111';

        const head = document.createElement('div');
        head.style.display = 'flex';
        head.style.justifyContent = 'space-between';
        head.style.alignItems = 'center';
        head.style.gap = '6px';
        const title = document.createElement('div');
        title.style.fontSize = '12px';
        title.style.color = '#ccc';
        title.textContent = scr.name;
        const count = document.createElement('div');
        count.style.fontSize = '11px';
        count.style.fontFamily = 'monospace';
        count.style.color = scr.unplaced.length ? '#d05a52' : '#888';
        count.textContent = `${scr.required - scr.unplaced.length}`
            + `/${scr.required} ports`;
        head.appendChild(title);
        head.appendChild(count);
        box.appendChild(head);

        if (scr.split) {
            // Worth calling out rather than leaving to be spotted: a screen on
            // two cards is two trunks to one wall, which is a real thing on
            // site and never something the app did on its own.
            box.appendChild(this._buildAssignmentNote(
                'This screen spans two cards.', '#c8a04a'));
        }

        const grid = document.createElement('div');
        grid.style.marginTop = '6px';
        grid.style.display = 'grid';
        grid.style.gap = '2px';
        scr.ports.forEach(port => {
            grid.appendChild(this._buildAssignmentPort(scr, port, res));
        });
        box.appendChild(grid);

        const tools = document.createElement('div');
        tools.style.display = 'flex';
        tools.style.gap = '4px';
        tools.style.marginTop = '6px';
        tools.appendChild(this._buildOffer({
            action: 'move-block', layerId: scr.layerId,
            label: 'Move whole block',
        }));
        if (scr.ports.some(p => p.source === 'pin')) {
            tools.appendChild(this._buildOffer({
                action: 'release', layerId: scr.layerId,
                label: 'Release all pins',
            }));
        }
        box.appendChild(tools);
        return box;
    }

    _buildAssignmentPort(scr, port, res) {
        const row = document.createElement('div');
        row.style.display = 'grid';
        row.style.gridTemplateColumns = '22px 1fr auto auto';
        row.style.gap = '4px';
        row.style.alignItems = 'center';
        row.style.fontSize = '11px';
        row.style.fontFamily = 'monospace';

        const own = document.createElement('div');
        own.style.color = '#666';
        own.textContent = String(port.number);
        row.appendChild(own);

        const where = document.createElement('div');
        where.style.overflow = 'hidden';
        where.style.textOverflow = 'ellipsis';
        where.style.whiteSpace = 'nowrap';
        if (!port.cardId) {
            where.style.color = '#d05a52';
            where.textContent = 'no card';
        } else {
            where.style.color = port.overlap ? '#d05a52' : '#ccc';
            // The label the catalog derived wins the space when there is one,
            // because it is what is silkscreened on the box the tech is
            // standing in front of. The raw number is still there behind it.
            where.textContent = port.label
                ? `${port.cardName} ${port.label}`
                : `${port.cardName} port ${port.port}`;
            if (port.overlap) where.textContent += ' - clash';
        }
        row.appendChild(where);

        // Pinned and auto have to be told apart at a glance: one of them is a
        // decision somebody made and the other is the app's arithmetic, and
        // they look identical once they are numbers on a page.
        const mark = document.createElement('div');
        mark.style.fontSize = '10px';
        mark.style.color = port.source === 'pin' ? '#c8a04a' : '#555';
        mark.textContent = port.source === 'pin' ? 'PINNED' : 'auto';
        mark.title = port.source === 'pin'
            ? 'Held here by hand. Auto-numbering will not move it.'
            : 'Numbered automatically. Will re-pack as screens change.';
        row.appendChild(mark);

        if (port.source === 'pin') {
            const act = document.createElement('button');
            act.className = 'btn';
            act.style.padding = '1px 6px';
            act.style.fontSize = '10px';
            act.style.background = '#2a2a2a';
            act.textContent = 'release';
            act.title = 'Hand this port back to auto-numbering';
            act.addEventListener('click', () => this._assignmentRequest(
                '/api/port-assignments/unpin', 'POST',
                { layerId: scr.layerId, index: port.index }));
            row.appendChild(act);
        } else {
            row.appendChild(this._buildPinControl(scr, port, res));
        }
        return row;
    }

    // ANY port of ANY screen, onto a card the user names. With one card in the
    // project that is just "hold it where it is", so it stays a button; with
    // more, the card has to be choosable, because the whole point of a pin is
    // that the app's choice was not the right one.
    //
    // Which free NUMBER it lands on is left to the server. Working it out here
    // would be a second implementation of "which ports are free", and it gets
    // it wrong the first time a pin leaves a hole in the middle of a card.
    _buildPinControl(scr, port, res) {
        const cards = res.cards || [];
        const pin = (cardId) => this._assignmentRequest(
            '/api/port-assignments/pin', 'POST',
            { layerId: scr.layerId, index: port.index, cardId,
              // Pinning a port that already has a number holds THAT number.
              // The common case is not "move this", it is "the numbering is
              // right, stop it moving when the next screen arrives".
              port: (port.cardId === cardId && port.port) || undefined });

        if (cards.length < 2) {
            const act = document.createElement('button');
            act.className = 'btn';
            act.style.padding = '1px 6px';
            act.style.fontSize = '10px';
            act.style.background = '#2a2a2a';
            act.textContent = 'pin';
            act.title = port.cardId
                ? 'Hold this port where it is'
                : 'Pin this port to the card by hand';
            act.disabled = !cards.length;
            act.addEventListener('click', () => {
                if (cards.length) pin(port.cardId || cards[0].cardId);
            });
            return act;
        }

        const select = document.createElement('select');
        select.style.fontSize = '10px';
        select.style.padding = '0 2px';
        select.style.maxWidth = '92px';
        select.title = 'Pin this port to a card and hold it there';
        select.dataset.lrdField = `port-pin-${scr.layerId}-${port.index}`;
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = 'pin…';
        select.appendChild(blank);
        if (port.cardId) {
            const here = document.createElement('option');
            here.value = port.cardId;
            here.textContent = `here (${port.cardName} ${port.port})`;
            select.appendChild(here);
        }
        cards.filter(c => c.cardId !== port.cardId).forEach(card => {
            const opt = document.createElement('option');
            opt.value = card.cardId;
            opt.textContent = card.free === 0
                ? `${card.title} (full)` : card.title;
            opt.disabled = card.free === 0;
            select.appendChild(opt);
        });
        select.addEventListener('change', () => {
            if (select.value) pin(select.value);
        });
        return select;
    }

    _buildAssignmentFoot(res) {
        const wrap = document.createElement('div');

        const cards = document.createElement('div');
        cards.style.display = 'grid';
        cards.style.gap = '2px';
        (res.cards || []).forEach(card => {
            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.justifyContent = 'space-between';
            row.style.fontSize = '11px';
            row.style.fontFamily = 'monospace';
            row.style.color = card.free === 0 ? '#c8a04a' : '#888';
            const name = document.createElement('span');
            name.textContent = card.title;
            const use = document.createElement('span');
            use.textContent = card.capacityKnown
                ? `${card.used} / ${card.capacity}`
                : `${card.used} / unknown`;
            row.appendChild(name);
            row.appendChild(use);
            cards.appendChild(row);
        });
        wrap.appendChild(cards);

        const toggle = document.createElement('label');
        toggle.style.display = 'flex';
        toggle.style.alignItems = 'center';
        toggle.style.gap = '6px';
        toggle.style.fontSize = '11px';
        toggle.style.color = '#ccc';
        toggle.style.marginTop = '8px';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = !!res.auto;
        cb.dataset.lrdField = 'port-assignment-auto';
        cb.addEventListener('change', () => this._assignmentRequest(
            '/api/port-assignments', 'PUT', { auto: cb.checked }));
        toggle.appendChild(cb);
        toggle.appendChild(document.createTextNode(
            'Number unpinned ports automatically'));
        wrap.appendChild(toggle);
        return wrap;
    }
}

for (const k of Object.getOwnPropertyNames(_PortAssignment.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PortAssignment.prototype, k));
    }
}
