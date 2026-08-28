// app-port-assignment: the port numbering resolution, narrated on the
// hardware dock (the Signal sidebar it used to panel in is retired).
//
// Since the hardware dock became the assignment gesture there are no
// per-port pin/move/release rows - pointing a socket at a screen is a
// drag, and taking an assignment back is a drag to the tray or a right-click
// on the run or the chip. What stays here is the part a drag cannot replace:
// the REPORTING. Looms are made up and labelled off the drawing days before
// anything is hung, so a numbering that shifted on its own would hand back a
// drawing that no longer matches what is in the truck. Every problem - a
// clash, a pin whose card is gone - is drawn as a slim strip row under the
// dock's header with a button beside it, and the button is the only thing
// that moves anything. The per-screen OVERFLOW story lives under the dock
// header's attachment flag now (app-dock.js _renderDockFlag), not in the
// strip: one pill with a screen count instead of a wall of red rows, so
// the strip filters kind 'overflow' out below. The per-card usage counts
// are the card headers' glance. There is no auto toggle in the UI any
// more; the server keeps its auto state, and the amber auto-off strip row
// (with its turn-back-on offer) stays as the recovery path for a legacy
// project saved with auto off.
//
// KNOWN GAP: with the rows gone the data side, like the power side, has no
// keyboard path for MAKING an assignment - the drag is the only gesture. The
// offer buttons below stay real buttons, so the recovery paths (resolve a
// clash, place an overflow, release a stranded pin, turn auto back on) are
// still reachable by keyboard.
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
        // Empty, not absent: getPortLabelText reads them on every frame from
        // the first render, which happens long before this endpoint answers.
        this._processorPortLabels = {};
        this._processorPortReturnLabels = {};
        this._occupancyRaw = '';
        this._assignmentError = null;
        this._assignmentNote = null;
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
            // The stored pins are part of the picture too: undo/redo swaps
            // the whole project - pins included - under an unchanged set of
            // processors and screens, and without this term updateUI's
            // compare would skip the re-resolve and the panel would keep
            // narrating the pre-undo numbering.
            (this.project && this.project.port_assignments) || null,
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
                // The layer's Processing setting rides with the count, so
                // the server can hold the platform wall (a Legacy screen
                // never lands on COEX gear) in the one place the matrix
                // lives. Which cards accept what comes BACK on each card
                // summary's `platforms`; nothing here re-derives it.
                platform: l.processorType || null,
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

    // onRefused sees a 409 first and returns true when it has dealt with it.
    // Only one caller needs it - a placement can be refused with a QUESTION
    // rather than a fact ("Side port 2 is already there") and the answer is a
    // person, not a retry - and the alternative was a second request path that
    // did not go through _applyAssignmentResolution on the way back.
    //
    // `action` names the history entry a MUTATING call earns, the same
    // post-mutation snapshot _processorRequest takes: the new state has
    // already been folded into this.project by the time it runs, so redo can
    // re-apply it. Reads pass no action, and a refused edit changed nothing
    // and earns no entry - Ctrl+Z must never grow no-op steps.
    _assignmentRequest(url, method, body, onRefused, action) {
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
                    if (onRefused && onRefused(data)) return;
                    // A refused move is not a failure to hide. It is usually
                    // "there is no run that long free", which is the thing the
                    // user needs to read.
                    this._assignmentError = data.error || 'That move is not possible.';
                    this._assignmentNote = null;
                    this.renderPortAssignmentPanel();
                    return;
                }
                // A move that worked still has something to say: which socket
                // it landed on, what it held to get there, and the parts
                // nobody asked for - another screen's auto ports packing into
                // the room it left, a run that now spans two cards. It reads
                // where an error would but not in an error's colour: a move
                // that did exactly what it was told is not a warning, and
                // colouring the two alike trains people past both.
                this._assignmentError = null;
                this._assignmentNote = (data.moved && data.moved.note) || null;
                if (data.resolution) this._assignment = data.resolution;
                if (data.state && this.project) {
                    this.project.port_assignments = data.state;
                }
                this._applyAssignmentResolution();
                if (action && typeof this.saveState === 'function') {
                    this.saveState(action);
                }
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
        // The dock's port tiles are a picture of the same occupancy the
        // Processors panel reads, so a new resolution redraws them too.
        if (typeof this.renderHardwareDock === 'function') {
            this.renderHardwareDock();
        }
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
    //
    // The return ends get a map of their own, built from the same resolution
    // in the same pass. Two maps rather than one holding pairs, because the
    // per-frame reader looks up exactly one end at a time and should never
    // unpack an object to get it.
    _indexAssignmentLabels() {
        const map = {};
        const returnMap = {};
        const res = this._assignment;
        ((res && res.screens) || []).forEach(scr => {
            const byPort = {};
            const returnsByPort = {};
            let any = false;
            let anyReturn = false;
            (scr.ports || []).forEach(port => {
                if (port.label) {
                    byPort[port.number] = port.label;
                    any = true;
                }
                if (port.returnLabel) {
                    returnsByPort[port.number] = port.returnLabel;
                    anyReturn = true;
                }
            });
            if (any) map[String(scr.layerId)] = byPort;
            if (anyReturn) returnMap[String(scr.layerId)] = returnsByPort;
        });
        this._processorPortLabels = map;
        this._processorPortReturnLabels = returnMap;
    }

    // ── drawing ───────────────────────────────────────────────────────────
    //
    // The Port Numbering panel died with the Signal sidebar; the reporting
    // re-hosted onto the hardware dock. The refuse-and-offer boxes became
    // the slim strip under the dock's header (#hw-dock-issues, one row per
    // issue with its buttons inline) and the per-card usage foot became
    // the card headers' n/N + fill glance - so this render touches the
    // strip, and the chips redraw on their own paths.

    renderPortAssignmentPanel() {
        const strip = document.getElementById('hw-dock-issues');
        if (!strip) return;
        // Only the Data view's strip is this panel's to write: the Power
        // view fills the same strip with its own warnings from the dock
        // render, and anywhere else the dock is out of layout anyway.
        const mode = window.canvasRenderer
            ? window.canvasRenderer.viewMode : '';
        if (mode !== 'data-flow') return;
        this._preserveEditorFocus();
        strip.innerHTML = '';

        const res = this._assignment;
        if (!res || !res.configured) return;

        if (this._assignmentError) {
            strip.appendChild(this._buildIssue(
                { message: this._assignmentError }));
        }
        if (this._assignmentNote) {
            // A note is not a warning; it keeps its own quiet blue row.
            const row = this._buildIssue({ message: this._assignmentNote });
            row.classList.add('hw-dock-issue-note');
            strip.appendChild(row);
        }
        // The overflow rows moved under the header's attachment flag
        // (app-dock.js _renderDockFlag reads the same resolution's
        // per-screen unplaced) - the strip repeating them would be the
        // wall of red the flag exists to fold away. Every other kind
        // stays a strip row, offers and all.
        (res.issues || []).filter(i => i.kind !== 'overflow')
            .forEach(issue => {
                strip.appendChild(this._buildIssue(issue));
            });
    }

    _buildAssignmentNote(text, color) {
        const row = document.createElement('div');
        row.style.fontSize = '11px';
        row.style.lineHeight = '1.4';
        row.style.color = color || '#888';
        row.textContent = text;
        return row;
    }

    // One issue as one slim strip row: the message and its offer buttons on
    // the same line, wrapping only when the tray is genuinely too narrow.
    // Same machinery as the old panel boxes (_buildOffer / _takeOffer are
    // untouched), re-hosted onto the dock.
    _buildIssue(issue) {
        const row = document.createElement('div');
        row.className = 'hw-dock-issue';
        // An unknown port count, auto being off, and a card whose boxes cannot
        // reach its ceiling are all CONDITIONS - true, worth knowing, nothing
        // to answer right now. A clash, an overflow or a stranded pin is a
        // question waiting on a person. Colouring them the same would train
        // people to skim past the ones that matter.
        const mild = ['capacity-unknown', 'auto-off',
                      'card-short-of-its-ceiling'].includes(issue.kind);
        if (mild) row.classList.add('hw-dock-issue-mild');
        const msg = document.createElement('span');
        msg.className = 'hw-dock-issue-msg';
        msg.textContent = issue.message;
        row.appendChild(msg);
        (issue.offers || []).forEach(offer => {
            row.appendChild(this._buildOffer(offer));
        });
        return row;
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
            return this._assignmentRequest(
                '/api/port-assignments/move-block', 'POST',
                { layerId: offer.layerId,
                  cardId: offer.cardId || undefined,
                  // The dock's box drops bound the move to the box's span of
                  // card ports; panel offers never carry a window.
                  firstPort: offer.firstPort || undefined,
                  lastPort: offer.lastPort || undefined },
                null, 'Move Port Block');
        } else if (offer.action === 'place-overflow') {
            return this._assignmentRequest(
                '/api/port-assignments/place-overflow',
                'POST', { layerId: offer.layerId,
                          cardId: offer.cardId,
                          firstPort: offer.firstPort || undefined,
                          lastPort: offer.lastPort || undefined },
                null, 'Fill Ports In Order');
        } else if (offer.action === 'release') {
            return this._assignmentRequest(
                '/api/port-assignments/unpin', 'POST',
                { layerId: offer.layerId, index: offer.index },
                null, 'Release Ports');
        } else if (offer.action === 'auto-on') {
            return this._assignmentRequest('/api/port-assignments', 'PUT',
                                           { auto: true }, null,
                                           'Toggle Auto Numbering');
        }
    }

    // One port of one screen onto one card port, from either end of the cable:
    // the row in this panel, and the port row in the Processors panel. Both
    // send the same request because they are the same decision - "this plugs
    // in there" - and a second implementation of it would be a second set of
    // rules about what is allowed to land on an occupied socket.
    //
    // The refusal is the interesting half. The server names who is already on
    // the port and what happens if this lands on it as well, and nothing has
    // moved at that point; confirming re-sends the identical request with the
    // answer attached. Placing first and reporting after would be the silent
    // rearrangement this whole feature is built not to do.
    _placePort(spot, confirmed) {
        return this._assignmentRequest(
            '/api/port-assignments/place', 'POST',
            Object.assign({ confirm: !!confirmed }, spot),
            (data) => {
                if (confirmed || !data.conflict) return false;
                sendClientLog('port_assignment_place_conflict', data.conflict);
                if (window.confirm(`${data.error}\n\nPlace it here anyway?`)) {
                    this._placePort(spot, true);
                } else {
                    // Backed out. Clear whatever the last move left on the
                    // panel: a note still reading "X is now on SR-7" beside a
                    // numbering that did not change looks like an answer to
                    // the question just declined.
                    this._assignmentError = null;
                    this._assignmentNote = null;
                    this.renderPortAssignmentPanel();
                }
                return true;
            }, 'Place Port');
    }

    // The per-card usage foot the old panel drew is the card headers'
    // n/N + fill glance now (app-dock.js _dockBuildCard reads the same
    // assignment summary). Nothing is left for a foot builder to build.
    // The auto-on offer above is the ONLY auto lever in the UI: the PUT
    // endpoint still takes auto either way, but nothing here ever turns
    // auto OFF - the amber strip row exists to recover a legacy project
    // saved that way, not to offer the trip.
}

for (const k of Object.getOwnPropertyNames(_PortAssignment.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PortAssignment.prototype, k));
    }
}
