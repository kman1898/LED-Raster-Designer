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
// are the card headers' glance.
//
// Auto-numbering is retired (user ruling, 2026-09-03: "auto should be
// removed now"). Nothing lands on a card unless a person put it there -
// every placement is a pin, an unpinned port is "not attached" and the
// flag counts it - so there is no auto state to toggle, no auto-off row
// and no offer to turn it back on. A legacy file's auto-drawn ports are
// frozen into pins once by the server (port_assignment.retire_auto); the
// resolve that does it says `migrated`, and _assignmentRequest takes the
// returned state on that word so the client's copy carries the pins too.
//
// KNOWN GAP: with the rows gone the data side, like the power side, has no
// keyboard path for MAKING an assignment - the drag is the only gesture. The
// offer buttons below stay real buttons, so the recovery paths (resolve a
// clash, release a stranded pin) are still reachable by keyboard.
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
        // THE LINK CAP (a box behind a Brompton QD-S carries at most its
        // 10G link - port_assignment.link_cap_refusal) is held on the
        // server, off the pixels each port carries - which only the port
        // maths here knows. So where any box has a cap, every screen sends
        // its per-port pixels and the settings its capacity is read at;
        // everywhere else the payload is what it always was.
        const capped = this._linkCapsInPlay();
        // THE CANVAS (a Brompton processor's - port_assignment.
        // canvas_refusal) is held off the Pixel Map rect each port's
        // cabinets cover, so where any processor has one every screen sends
        // its portRects (and its ULL, which lowers an SX40's canvas).
        const canvas = this._canvasInPlay();
        let owners = null;
        const ownerOf = (panel) => {
            if (!owners) {
                owners = new Map();
                layers.forEach(l => (l.panels || []).forEach(p => owners.set(p, l)));
            }
            return owners.get(panel);
        };
        return layers
            .filter(l => (l.type || 'screen') === 'screen')
            .map(l => {
                const ports = (typeof this.getLayerPortsRequired === 'function'
                    ? this.getLayerPortsRequired(l) : 0) || 0;
                const scr = {
                    layerId: String(l.id),
                    name: l.name || `Screen ${l.id}`,
                    ports,
                    // The layer's Processing setting rides with the count,
                    // so the server can hold the platform wall (a Legacy
                    // screen never lands on COEX gear) in the one place the
                    // matrix lives. Which cards accept what comes BACK on
                    // each card summary's `platforms`; nothing here
                    // re-derives it.
                    platform: l.processorType || null,
                };
                if (capped && ports > 0) {
                    Object.assign(scr, this._linkCapFields(l, ports));
                }
                if (canvas && ports > 0) {
                    Object.assign(scr, this._canvasFields(l, ports, ownerOf));
                }
                return scr;
            })
            // A screen needing no ports has nothing to assign and would only
            // draw an empty row. Text layers are already gone above.
            .filter(s => s.ports > 0);
    }

    // Whether any resolved box carries a link cap (resolve_card's
    // linkCapPorts - a box on a QD-S output).
    _linkCapsInPlay() {
        return (this._processorsResolved || []).some(p => (p.slots || [])
            .some(s => s.card && (s.card.cvts || [])
                .some(b => b && b.linkCapPorts)));
    }

    // One screen's link-cap fields: the pixels each port carries (index 0
    // = port 1), scored by the canvas's own load reading
    // (getPortPixelLoad over the panels _dockRunPanels gathers - the same
    // run the chip's fill line reads), and the settings the server reads
    // the vendor's per-port capacity at.
    _linkCapFields(layer, ports) {
        const r = window.canvasRenderer;
        const pixels = [];
        for (let n = 1; n <= ports; n++) {
            const panels = typeof this._dockRunPanels === 'function'
                ? this._dockRunPanels(layer, n) : [];
            pixels.push(r && typeof r.getPortPixelLoad === 'function'
                ? Math.round(r.getPortPixelLoad(layer, panels) || 0) : 0);
        }
        return {
            portPixels: pixels,
            bitDepth: layer.bitDepth || 8,
            frameRate: layer.frameRate || 60,
            lowLatency: !!layer.lowLatency,
        };
    }

    // THE PROCESSING GUARD: a bit depth, frame rate or ULL change that would
    // push a box already carrying screens past its link cap is refused, and
    // the setting stays as it was. `apply` writes the change onto the
    // selected layers (in memory), `revert` puts them back, `commit` is the
    // handler's usual save. With no capped box in the project nothing is
    // asked and the change commits at once, exactly as it always did; with
    // one, the server is asked first (/link-check) with the screens as they
    // are and as they would be, and says why where it refuses.
    _guardLinkCaps(apply, revert, commit) {
        // The same question is asked of a processor's CANVAS: ULL lowers
        // an SX40's canvas height, and the port runs move with the bit
        // depth (port_assignment.canvas_refusal, on /link-check too).
        if (!this._linkCapsInPlay() && !this._canvasInPlay()) {
            apply();
            commit();
            return Promise.resolve(true);
        }
        const before = this._assignmentScreens();
        apply();
        // The run-panel memo is keyed by layer object for one tick, and the
        // layers just changed under it.
        this._dockRunPanelsCache = null;
        const screens = this._assignmentScreens();
        return fetch('/api/port-assignments/link-check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ before, screens }),
        })
            .then(r => r.json().then(data => ({ ok: r.ok, data })))
            .then(({ ok, data }) => {
                if (ok) {
                    commit();
                    return true;
                }
                revert();
                const why = data.error || 'That setting is refused.';
                this._assignmentError = why;
                this._assignmentNote = null;
                if (typeof this.renderPortAssignmentPanel === 'function') {
                    this.renderPortAssignmentPanel();
                }
                if (typeof this._dockSay === 'function') this._dockSay(why);
                sendClientLog('link_cap_setting_refused', { error: why });
                return false;
            })
            .catch(err => {
                revert();
                sendClientLog('link_cap_check_failed', { error: String(err) });
                return false;
            });
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
                    // A link-cap refusal also speaks where the drop was
                    // made: nothing landed, and the strip may be folded.
                    if ((data.linkCap || data.canvas)
                            && typeof this._dockSay === 'function') {
                        this._dockSay(data.error);
                    }
                    return;
                }
                // A move that worked still has something to say: which socket
                // it landed on, and the parts nobody asked for - a run that
                // now spans two cards, a socket deliberately shared. It reads
                // where an error would but not in an error's colour: a move
                // that did exactly what it was told is not a warning, and
                // colouring the two alike trains people past both.
                this._assignmentError = null;
                this._assignmentNote = (data.moved && data.moved.note) || null;
                if (data.resolution) this._assignment = data.resolution;
                // Undo audit: the server holds the read-must-not-create-the-
                // key line (_working/_store in routes_port_assignment.py),
                // and an unconditional store here once defeated it from the
                // client side - the boot-time /resolve stamped state onto a
                // project that never had the key, and every snapshot and
                // save carried it from then on. A MUTATING call (one that
                // names a history action) always stores its state; a read
                // stores it only where the key already exists to update -
                // or where the server says `migrated`: a legacy file's
                // auto-drawn ports were just frozen into pins, and the
                // client's copy (which has no key at all) has to carry
                // them or the next snapshot hands the server a project it
                // must freeze all over again.
                if (data.state && this.project
                        && (action || data.migrated
                            || this.project.port_assignments !== undefined)) {
                    this.project.port_assignments = data.state;
                    // The key names the state THIS resolution was drawn
                    // from. A mutating call (a pin, a release) changes the
                    // stored pins and gets a fresh resolution back, so the
                    // key moves with it - left where refreshPortAssignment
                    // last set it, an undo back to the pre-release pins
                    // compared EQUAL to the stale key, updateUI skipped the
                    // re-resolve, and the tray kept the released socket
                    // free while the project already held the pin
                    // (2026-09-06, found by tests/test_data_snakes.py).
                    this._assignmentKeyRaw = this._assignmentKey();
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
        // A quiet point: the edit guard's base meets a replaced project or
        // a screen it has not seen.
        if (typeof this._canvasKeepBase === 'function') this._canvasKeepBase();
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
    // lookup's own miss is the fallback: an unassigned port, or a project
    // with no processor at all, lands on the layer's own template with
    // nothing extra to check. (A card nobody named is no longer a miss: the
    // server labels its sockets with their own numbers - the 2026-09-03
    // ruling - and those arrive here like any other label.)
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

    // One issue as one slim strip row: the message and its offer buttons on
    // the same line, wrapping only when the tray is genuinely too narrow.
    // Same machinery as the old panel boxes (_buildOffer / _takeOffer are
    // untouched), re-hosted onto the dock.
    _buildIssue(issue) {
        const row = document.createElement('div');
        row.className = 'hw-dock-issue';
        // An unknown port count and a card whose boxes cannot reach its
        // ceiling are CONDITIONS - true, worth knowing, nothing to answer
        // right now. A clash, an overflow or a stranded pin is a question
        // waiting on a person. Colouring them the same would train people
        // to skim past the ones that matter.
        const mild = ['capacity-unknown',
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
        // only the rest and tear the run in two, which is the thing the
        // move exists to prevent. Other screens' pins are never touched.
        if (offer.action === 'move-block') {
            btn.title = 'Move every port of this screen to the next free run, '
                + 'in the same order, and hold them there. Every port of '
                + 'this screen comes with it, wherever it sits now.';
        } else if (offer.action === 'release') {
            btn.title = 'Take these ports off their card. They stay '
                + 'unattached until you place them again.';
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
                          lastPort: offer.lastPort || undefined,
                          // The dock's whole-unit drop names the screen
                          // port under the cursor (0-based): the fill
                          // takes the unplaced ports up to it, no further.
                          lastIndex: offer.lastIndex != null
                              ? offer.lastIndex : undefined },
                null, 'Fill Ports In Order');
        } else if (offer.action === 'release') {
            return this._assignmentRequest(
                '/api/port-assignments/unpin', 'POST',
                { layerId: offer.layerId, index: offer.index },
                null, 'Release Ports');
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

    // THE ONE n/N FOR A CARD OR A BOX: sockets taken over sockets there,
    // as { taken, of } - `of` null where nobody settled the card's
    // count - or null where nothing is known yet. Taken is every socket
    // holding a primary OR carrying a placed primary's return (owner,
    // 2026-09-24: "11 primary and 11 redundant ... it's 22/40"), counted
    // where the socket lives - port_assignment._taken_sockets says which
    // card that is in every redundancy shape. The tray's card and box
    // headers and the binder's Cards table all read this, so the three
    // cannot print three numbers. `boxId` narrows it to one breakout box.
    socketsTaken(cardId, boxId) {
        const summary = ((this._assignment && this._assignment.cards) || [])
            .find(c => c.cardId === cardId);
        if (!summary) return null;
        if (boxId != null) {
            const box = (summary.boxes || {})[boxId];
            return box && box.sockets > 0
                ? { taken: box.taken, of: box.sockets } : null;
        }
        const taken = summary.taken != null ? summary.taken : summary.used;
        return { taken,
                 of: summary.capacityKnown && summary.capacity > 0
                     ? summary.capacity : null };
    }

    // ── THE PROCESSING CANVAS ─────────────────────────────────────────────
    //
    // A Brompton processor maps every screen it drives into one canvas, and
    // all of it has to fit (owner, 2026-10-07: "refuse" / "throw an error
    // and not allow it"). A processor's SPAN is the bounding box, in Pixel
    // Map pixels, of every visible cabinet riding one of its pinned ports.
    // The server holds a MAPPING to the canvas (port_assignment.
    // canvas_refusal) off the rect each port covers, which only the port
    // maths here knows - so where a canvas is in play every screen sends
    // its portRects. A layer EDIT (columns, rows, cabinet size, a move,
    // rotation, half tiles, showing cabinets) is held here, in
    // _canvasGuardEdit, because it has to be refused before the screen's
    // PUT and its undo step: canvasFit below is the client twin of
    // processor_catalog.canvas_fit, and tests/test_brompton_canvas.py
    // holds the two to one table.

    // Whether any processor in the tray publishes a canvas.
    _canvasInPlay() {
        return (this._processorsResolved || []).some(p => p && p.canvas);
    }

    // One screen's canvas fields: the Pixel Map rect each port's visible
    // cabinets cover ([x0, y0, x1, y1], null for none; index 0 = port 1),
    // read off the same run gathering the chip fill uses (_dockRunPanels -
    // group peers' cabinets included), and the ULL setting the canvas is
    // read at. A rotated screen's cabinets are taken where they are drawn.
    _canvasFields(layer, ports, ownerOf) {
        const rects = [];
        for (let n = 1; n <= ports; n++) {
            const panels = typeof this._dockRunPanels === 'function'
                ? this._dockRunPanels(layer, n) : [];
            let box = null;
            panels.forEach(panel => {
                if (!panel || panel.hidden || panel.blank) return;
                const r = this._canvasPanelRect(ownerOf(panel) || layer, panel);
                if (!r || !(r.x1 > r.x0) || !(r.y1 > r.y0)) return;
                box = box ? [Math.min(box[0], r.x0), Math.min(box[1], r.y0),
                             Math.max(box[2], r.x1), Math.max(box[3], r.y1)]
                    : [r.x0, r.y0, r.x1, r.y1];
            });
            rects.push(box);
        }
        return { portRects: rects, lowLatency: !!layer.lowLatency };
    }

    // A cabinet's Pixel Map rect, turned with its screen's rotation the way
    // the renderer draws it (canvas.js _drawnPanelRect) but never shifted
    // by a Show Look offset - the canvas is the processor's map.
    _canvasPanelRect(layer, panel) {
        const r = window.canvasRenderer;
        const w = Number(panel.width) || 0;
        const h = Number(panel.height) || 0;
        let x = Number(panel.x) || 0;
        let y = Number(panel.y) || 0;
        let fw = w, fh = h;
        if (r && typeof r._layerDrawFrame === 'function') {
            const frame = r._layerDrawFrame(layer);
            if (frame && frame.rot) {
                const c = r._drawnPoint(frame, x + w / 2, y + h / 2);
                fw = frame.swap ? h : w;
                fh = frame.swap ? w : h;
                x = c.x - fw / 2;
                y = c.y - fh / 2;
            }
        }
        return { x0: x, y0: y, x1: x + fw, y1: y + fh };
    }

    // processor_catalog.canvas_extent's twin: a span edge in whole pixels.
    canvasExtent(value) {
        return Math.ceil((Number(value) || 0) - 1e-6);
    }

    // processor_catalog.canvas_fits's twin.
    canvasFits(spec, width, height, ull) {
        const w = this.canvasExtent(width);
        const h = this.canvasExtent(height);
        if (w <= 0 || h <= 0 || !spec) return true;
        const ullRule = ull ? spec.ull : null;
        if (!(ullRule && ullRule.presets === false)) {
            if ((spec.presets || []).some(([pw, ph]) => w <= pw && h <= ph)) return true;
        }
        const custom = spec.custom;
        if (custom) {
            const cw = custom.evenWidth ? w + (w % 2) : w;
            let maxH = custom.maxH;
            if (ullRule && ullRule.maxH != null) maxH = ullRule.maxH;
            return cw <= (custom.maxW || 0) && h <= (maxH || 0)
                && cw * h <= (custom.maxPixels || 0);
        }
        if (spec.maxW != null || spec.maxH != null) {
            return w <= (spec.maxW || 0) && h <= (spec.maxH || 0);
        }
        return false;
    }

    // processor_catalog.canvas_limit_text's twin.
    canvasLimitText(spec, ull) {
        const says = spec.says || 'This processor';
        const num = n => Number(n).toLocaleString('en-US');
        const custom = spec.custom;
        const ullRule = ull ? spec.ull : null;
        const sizes = (spec.presets || []).map(([pw, ph]) => `${pw} × ${ph}`);
        if (custom) {
            if (ullRule) {
                const maxH = ullRule.maxH != null ? ullRule.maxH : custom.maxH;
                const lead = says[0].toLowerCase() + says.slice(1);
                return `With low latency on, ${lead}'s canvas is up to `
                    + `${custom.maxW} wide and ${maxH} tall within `
                    + `${num(custom.maxPixels)} px.`;
            }
            const head = sizes.length ? `${sizes[0]}, or ` : '';
            return `${says}'s canvas is ${head}up to ${custom.maxW} wide and `
                + `${custom.maxH} tall within ${num(custom.maxPixels)} px.`;
        }
        if (sizes.length) {
            const listed = sizes.length === 1 ? sizes[0]
                : `${sizes.slice(0, -1).join(', ')} or ${sizes[sizes.length - 1]}`;
            return `${says}'s canvas is ${listed}.`;
        }
        if (spec.maxW === spec.maxH) {
            return `${says}'s canvas is up to ${num(spec.maxW)} px wide or tall.`;
        }
        return `${says}'s canvas is up to ${num(spec.maxW)} px wide and `
            + `${num(spec.maxH)} px tall.`;
    }

    // processor_catalog.canvas_fit's twin, on the device's canvas record:
    // null where the span fits, else the sentence that refuses it.
    canvasFit(spec, width, height, ull, title, present) {
        if (!spec || this.canvasFits(spec, width, height, ull)) return null;
        const verb = present ? 'span' : 'would span';
        return `${title || 'This processor'} can't take this: its screens `
            + `${verb} ${this.canvasExtent(width)} × ${this.canvasExtent(height)} px. `
            + this.canvasLimitText(spec, ull);
    }

    // port_assignment.canvas_spans's twin, over the screens as
    // _assignmentScreens sends them and the project's pins.
    _canvasSpans(screens) {
        const byLayer = new Map((screens || []).map(s => [String(s.layerId), s]));
        const procOf = new Map();
        (this._processorsResolved || []).forEach(p => (p.slots || []).forEach(s => {
            if (s && s.card) procOf.set(s.card.id, p);
        }));
        const pins = ((this.project && this.project.port_assignments) || {}).pins || [];
        const recs = new Map();
        pins.forEach(pin => {
            const proc = procOf.get(String(pin.cardId));
            const scr = byLayer.get(String(pin.layerId));
            if (!proc || !scr || !Array.isArray(scr.portRects)) return;
            const rec = recs.get(proc.id) || { box: null, ull: false };
            recs.set(proc.id, rec);
            if (scr.lowLatency) rec.ull = true;
            const r = scr.portRects[Number(pin.index)];
            if (!r) return;
            rec.box = rec.box ? [Math.min(rec.box[0], r[0]), Math.min(rec.box[1], r[1]),
                                 Math.max(rec.box[2], r[2]), Math.max(rec.box[3], r[3])]
                : r.slice();
        });
        const out = new Map();
        (this._processorsResolved || []).forEach(p => {
            const rec = recs.get(p.id);
            if (!rec || !rec.box || !p.canvas) return;
            const model = p.deviceName || p.deviceId || 'Processor';
            const name = (p.name || '').trim();
            const title = name && name !== model ? `${model} ${name}` : model;
            const width = this.canvasExtent(rec.box[2] - rec.box[0]);
            const height = this.canvasExtent(rec.box[3] - rec.box[1]);
            out.set(p.id, { proc: p, title, width, height, ull: rec.ull,
                            fits: this.canvasFits(p.canvas, width, height, rec.ull) });
        });
        return out;
    }

    // port_assignment.canvas_refusal's twin: refused where a processor
    // ends up past its canvas AND worse than it was.
    _canvasRefusalBetween(before, after) {
        for (const [id, rec] of after) {
            if (rec.fits) continue;
            const was = before.get(id);
            if (was && !was.fits && rec.width <= was.width && rec.height <= was.height
                    && (was.ull || !rec.ull)) continue;
            return this.canvasFit(rec.proc.canvas, rec.width, rec.height, rec.ull, rec.title);
        }
        return null;
    }

    // ── the edit guard ────────────────────────────────────────────────────
    //
    // Layer edits are made on the live layer first and PUT after (the
    // drag, the Screen Info fields, rotation, a half tile), and the server
    // rebuilds the panels from the grid. So the guard keeps a BASE - every
    // screen's geometry as last accepted - and at the commit compares:
    // a screen whose geometry moved has its spans measured before (the
    // base) and after (its fields now, the panels rebuilt the way the
    // server will rebuild them), both on the live objects for one
    // synchronous moment. Refused, the base goes back onto the screen and
    // nothing is PUT or recorded.

    _canvasGeomKeys() {
        return ['columns', 'rows', 'cabinet_width', 'cabinet_height',
                'offset_x', 'offset_y', 'showOffsetX', 'showOffsetY',
                'rotation', 'flowPattern', 'portMappingMode',
                'customPortPaths', 'customPortOverrides', 'sizeByDimensions',
                'targetWidth', 'targetHeight', 'targetUnit', 'panels'];
    }

    // What decides where a screen's cabinets sit and which port each
    // rides - compared, never stored on the layer.
    _canvasGeomRecord(layer) {
        return JSON.stringify([
            layer.columns, layer.rows, layer.cabinet_width, layer.cabinet_height,
            layer.offset_x, layer.offset_y, Number(layer.rotation) || 0,
            layer.flowPattern || null, layer.portMappingMode || null,
            layer.customPortPaths || null, layer.customPortOverrides || null,
            (layer.panels || []).map(p => [p.row, p.col, !!p.hidden, !!p.blank,
                                           p.halfTile || 'none']),
        ]);
    }

    _canvasFieldsOf(layer) {
        const out = {};
        this._canvasGeomKeys().forEach(k => {
            out[k] = layer[k] === undefined ? undefined
                : JSON.parse(JSON.stringify(layer[k]));
        });
        return out;
    }

    _canvasScreenLayers() {
        return ((this.project && this.project.layers) || [])
            .filter(l => l && (l.type || 'screen') === 'screen');
    }

    // The accepted geometry, every screen.
    _canvasTakeBase() {
        const layers = new Map();
        this._canvasScreenLayers().forEach(l => layers.set(l.id, {
            rec: this._canvasGeomRecord(l), fields: this._canvasFieldsOf(l) }));
        this._canvasBase = { project: this.project, layers };
    }

    // The geometry the last undo step recorded, by screen id - the base
    // where the guard's own has not met this project (an undo, a load or
    // a repaired restore swapped it in between quiet points) or this
    // screen. The step is the state before the edit being guarded: every
    // geometry commit records its step after its PUT.
    _canvasHistoryLayers() {
        const out = new Map();
        const entry = Array.isArray(this.history) ? this.history[this.historyIndex] : null;
        const layers = ((entry && entry.project && entry.project.layers) || [])
            .filter(l => l && (l.type || 'screen') === 'screen');
        // A step from ANOTHER project (one swapped in before its history
        // was reset) is no base: its screens are not these, even where
        // their ids collide. The screens must be the same set.
        const ids = (list) => JSON.stringify(list.map(l => l.id).sort());
        if (ids(layers) !== ids(this._canvasScreenLayers())) return out;
        layers.forEach(l => {
            out.set(l.id, { rec: this._canvasGeomRecord(l), fields: this._canvasFieldsOf(l) });
        });
        return out;
    }

    // At a quiet point (updateUI, a landed resolution): a replaced project
    // (load, undo, redo) is taken whole; a screen the base has not met yet
    // is added as it stands.
    _canvasKeepBase() {
        if (!this._canvasInPlay()) {
            this._canvasBase = null;
            return;
        }
        const base = this._canvasBase;
        if (!base || base.project !== this.project) {
            this._canvasTakeBase();
            return;
        }
        this._canvasScreenLayers().forEach(l => {
            if (!base.layers.has(l.id)) {
                base.layers.set(l.id, { rec: this._canvasGeomRecord(l),
                                        fields: this._canvasFieldsOf(l) });
            }
        });
    }

    // app.py _build_panels's twin: the panels the server builds from a
    // screen's grid, keeping each cabinet's hidden/blank/half-tile state by
    // its row and column.
    _canvasBuildPanels(layer) {
        const rows = parseInt(layer.rows, 10) || 0;
        const cols = parseInt(layer.columns, 10) || 0;
        const ox = Number(layer.offset_x) || 0;
        const oy = Number(layer.offset_y) || 0;
        const cw = Number(layer.cabinet_width) || 0;
        const ch = Number(layer.cabinet_height) || 0;
        const states = new Map();
        (layer.panels || []).forEach(p => {
            if (p) states.set(`${p.row || 0},${p.col || 0}`, p);
        });
        const st = (r, c) => states.get(`${r},${c}`) || {};
        const half = (r, c) => {
            const h = st(r, c).halfTile;
            return h === 'width' || h === 'height' ? h : 'none';
        };
        const pw = (r, c) => (half(r, c) === 'width' ? cw / 2 : cw);
        const ph = (r, c) => (half(r, c) === 'height' ? ch / 2 : ch);
        const colW = [];
        for (let c = 0; c < cols; c++) {
            let m = rows ? -Infinity : cw;
            for (let r = 0; r < rows; r++) m = Math.max(m, pw(r, c));
            colW.push(m);
        }
        const rowH = [];
        for (let r = 0; r < rows; r++) {
            let m = cols ? -Infinity : ch;
            for (let c = 0; c < cols; c++) m = Math.max(m, ph(r, c));
            rowH.push(m);
        }
        const colX = [];
        let xc = ox;
        for (let c = 0; c < cols; c++) { colX.push(xc); xc += colW[c]; }
        const rowY = [];
        let yc = oy;
        for (let r = 0; r < rows; r++) { rowY.push(yc); yc += rowH[r]; }
        const visible = (r, c) => r >= 0 && r < rows && c >= 0 && c < cols
            && !st(r, c).hidden;
        const panels = [];
        let num = 1;
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                const s = st(r, c);
                const ht = half(r, c);
                const w = pw(r, c);
                const h = ph(r, c);
                let x = colX[c];
                let y = rowY[r];
                if (ht === 'height' && h < rowH[r]) {
                    if (!visible(r - 1, c) && visible(r + 1, c)) y = rowY[r] + (rowH[r] - h);
                } else if (ht === 'width' && w < colW[c]) {
                    if (!visible(r, c - 1) && visible(r, c + 1)) x = colX[c] + (colW[c] - w);
                }
                panels.push({ id: num, number: num, row: r, col: c, x, y,
                              width: w, height: h, blank: !!s.blank,
                              hidden: !!s.hidden, halfTile: ht,
                              is_color1: (r + c) % 2 === 0 });
                num++;
            }
        }
        return panels;
    }

    // Every canvas processor's span with `overrides` (layer id -> fields)
    // written onto those screens - their panels rebuilt from them - for the
    // length of the measurement, then put back exactly as they were.
    _canvasSpansWith(overrides) {
        const keys = this._canvasGeomKeys();
        const saved = [];
        const layers = this._canvasScreenLayers();
        try {
            layers.forEach(l => {
                const fields = overrides.get(l.id);
                if (!fields) return;
                const had = {};
                keys.forEach(k => {
                    had[k] = [Object.prototype.hasOwnProperty.call(l, k), l[k]];
                });
                saved.push([l, had]);
                keys.forEach(k => {
                    if (fields[k] === undefined) delete l[k];
                    else l[k] = JSON.parse(JSON.stringify(fields[k]));
                });
                l.panels = this._canvasBuildPanels(l);
            });
            this._dockRunPanelsCache = null;
            return this._canvasSpans(this._assignmentScreens());
        } finally {
            saved.forEach(([l, had]) => keys.forEach(k => {
                if (had[k][0]) l[k] = had[k][1];
                else delete l[k];
            }));
            this._dockRunPanelsCache = null;
        }
    }

    // THE EDIT GUARD. Called at every layer commit (updateLayers,
    // updateLayer, the cabinet hide/half-tile gestures) after the edit is
    // on the live layers and before anything is sent or recorded. True =
    // go ahead (the base moves to this state); false = refused: the
    // screens are back as they were, the reason is said, and the caller
    // stops. A screen no canvas processor drives never changes a span,
    // so it is never refused.
    _canvasGuardEdit() {
        if (!this._canvasInPlay()) {
            this._canvasBase = null;
            return true;
        }
        let base = this._canvasBase;
        if (!base || base.project !== this.project) {
            base = { project: this.project, layers: this._canvasHistoryLayers() };
            this._canvasBase = base;
        }
        let history = null;
        const changed = [];
        this._canvasScreenLayers().forEach(l => {
            let was = base.layers.get(l.id);
            if (!was) {
                if (!history) history = this._canvasHistoryLayers();
                was = history.get(l.id);
            }
            if (was && was.rec !== this._canvasGeomRecord(l)) changed.push([l, was]);
        });
        if (!changed.length) {
            this._canvasKeepBase();
            return true;
        }
        let why = null;
        try {
            const before = this._canvasSpansWith(
                new Map(changed.map(([l, was]) => [l.id, was.fields])));
            const after = this._canvasSpansWith(
                new Map(changed.map(([l]) => [l.id, this._canvasFieldsOf(l)])));
            why = this._canvasRefusalBetween(before, after);
        } catch (err) {
            sendClientLog('canvas_guard_failed', { error: String(err) });
            why = null;
        }
        if (!why) {
            this._canvasTakeBase();
            return true;
        }
        // Refused: every moved screen goes back to the base.
        changed.forEach(([l, was]) => {
            this._canvasGeomKeys().forEach(k => {
                if (was.fields[k] === undefined) delete l[k];
                else l[k] = JSON.parse(JSON.stringify(was.fields[k]));
            });
            // The base may hold panels taken before the server's rebuild
            // landed; built from its grid they are the server's own.
            l.panels = this._canvasBuildPanels(l);
        });
        this._dockRunPanelsCache = null;
        if (this._pendingGroupPeerIds) this._pendingGroupPeerIds.clear();
        // The caller's own undo step in this same task (a drag's, Screen
        // Info's) would record the restored state as a step of its own.
        this._canvasRefusedEdit = true;
        Promise.resolve().then(() => { this._canvasRefusedEdit = false; });
        this._assignmentError = why;
        this._assignmentNote = null;
        if (typeof this.renderPortAssignmentPanel === 'function') {
            this.renderPortAssignmentPanel();
        }
        if (typeof this._dockSay === 'function') this._dockSay(why);
        if (typeof this.loadLayerToInputs === 'function' && this.currentLayer) {
            try { this.loadLayerToInputs(); } catch (_) { /* inputs only */ }
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
        sendClientLog('canvas_edit_refused', {
            error: why, layers: changed.map(([l]) => l.id) });
        return false;
    }
}

for (const k of Object.getOwnPropertyNames(_PortAssignment.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PortAssignment.prototype, k));
    }
}
