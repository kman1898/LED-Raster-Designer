// app-dock: the hardware dock, a tray under the canvas that holds the view's
// hardware and makes DRAG the way assignments are made.
//
// The dock is the ONE hardware surface now - the Signal and Power middle
// sidebars retired into it. Its header bar carries the add controls and the
// attachment flag (red with a screen count while anything is unattached,
// green when everything hardware could hold is held - its rows open under
// the header on click, closed by default); a slim strip under the header
// carries the issues and warnings with their fix buttons inline; every
// section header carries
// its thing's NAME inline and a ⚙ opening its configuration popover
// (templates, modes, redundancy, electrical setup, removal - built by
// app-processors.js and app-power.js, anchored here). Each port chip
// carries the port's own editor folded inside it (the shared _wireTiles
// machinery): click or Enter opens the per-port Name and Return boxes, the
// manual backup pick and the occupancy detail in place, and drag still
// starts on press-and-move; an occupied circuit chip opens its label
// override the same way. Data view lays out every
// processor's cards, their breakout boxes and their port tiles; Power view
// lays out every distro as a section of multi sections, each multi holding
// its six tails as circuit chips in the same register - one grammar for
// both sides, because a circuit is dragged one at a time exactly as a port
// is. Every section (card, box, distro, multi) folds by the app's one
// section machinery, its header staying the whole-unit drag handle and
// carrying a glance readout while folded. Dragging a tile onto the canvas
// assigns through exactly the operations the panels used - place, pin,
// move-block, place-overflow, setSocaDistro, setSocaNumber - so the rules,
// the refusals, the conflict question and the undo entries are the same ones,
// arrived at by pointing instead of picking from a select.
//
// Drop semantics (the user's rule, verbatim shape):
//   - a single PORT tile lands on a specific port RUN: that screen-port is
//     placed on that processor port (conflicts come back as the existing
//     question, never a silent displacement);
//   - a single multi SLOT lands on a specific CIRCUIT run: that circuit's
//     multi takes that (distro, number) - landing on an occupied slot is the
//     existing join gesture, exactly as picking the number was. Landing on a
//     circuit that is NOT the first of its multi SPLITS the multi there
//     (the drop implies the boundary the sidebar's Split select used to ask
//     for): the circuits from there to the multi's end take the box, capped
//     at its free tails, one undo entry for split and assignment together;
//   - a whole CARD or BREAKOUT BOX lands anywhere on a screen: the screen's
//     ports fill onto it in order from the first unassigned (place-overflow),
//     or the whole block moves there when nothing is unassigned (move-block,
//     windowed to the box's span for a box);
//   - a whole DISTRO lands anywhere on a screen: the screen's unassigned
//     multis take that distro, numbered automatically;
//   - an OCCUPIED port tile, multi slot or circuit chip dragged back onto the
//     dock releases that assignment (unpin / clear distro+number / take the
//     one circuit off its box), undoable like the rest.
//
// Right-click is the other way back: a drawn port run, a power circuit, a
// dock chip, a card, a box or a distro right-clicked gets a "Clear …" item on
// the app's context menu (_prepareClearMenu below arms it, showContextMenu
// draws it). Clearing runs the same release operations the drag-back runs -
// nothing is confirmed, because a clear is undoable and touches only the
// assignment, never a name or a template - and a clear that is impossible is
// offered disabled with the reason as its title, the drag-back rule spoken
// before the gesture instead of after.
//
// The drag is pointer-based, not HTML5 DnD: the canvas is not a drop zone the
// DnD model understands, page.mouse drives pointers natively in the tests,
// and the resize handles already set the document-level move/up + teardown
// pattern this follows. mouseup is bound on the document for the same reason
// canvas.js binds its own on window: a drag routinely ends over a sidebar.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _HardwareDock {

    initHardwareDock() {
        const dock = document.getElementById('hardware-dock');
        if (!dock) return;
        this._dockDrag = null;
        this._dockDropTarget = null;
        // The attachment flag's rows are VIEW state, and closed is the
        // feature: the dock stays quiet until the flag is asked. Session
        // only, never localStorage - a new load always starts folded.
        this._dockFlagOpen = false;
        // Fold and height are the sidebars' machinery transposed, not the
        // section machinery: initSidebarToggles (app-core.js) owns the
        // collapse - and settles the canvas after it - and theme.js's
        // PANELS row owns the drag-resize, so there is nothing to watch
        // here the way the old section fold needed watching.
        this._wireDockChrome();
        this._wireDockColumnRedeal();
        this.renderHardwareDock();
    }

    // How many 380px-floor distro columns the tray genuinely holds, 1..3 -
    // the count _dockRenderPower deals by, and what the resize watcher
    // below re-checks. Measured from the body's content box; unmeasurable
    // (hidden tray, no layout yet) falls back to the 3-across default and
    // the first real resize corrects it.
    _dockPickColCount() {
        const body = document.getElementById('hardware-dock-body');
        let w = 0;
        if (body && body.clientWidth > 0) {
            const cs = getComputedStyle(body);
            w = body.clientWidth - (parseFloat(cs.paddingLeft) || 0)
                - (parseFloat(cs.paddingRight) || 0);
        }
        if (w <= 0) return 3;
        const gap = 10;
        const floor = 380;
        return Math.max(1, Math.min(3,
            Math.floor((w + gap) / (floor + gap))));
    }

    // Re-deal the power columns when a tray RESIZE crosses a column-count
    // threshold (2026-08-30: a 920px body holds two 380px floors, not
    // three - the count must follow the width, and the width moves on
    // window resizes and sidebar drags that re-render nothing else).
    // Debounced, and a strict no-op while the count holds: a full
    // re-render on every pixel of a drag would fight the user
    // mid-gesture.
    _wireDockColumnRedeal() {
        const body = document.getElementById('hardware-dock-body');
        if (!body || typeof ResizeObserver !== 'function') return;
        if (this._dockColObserver) this._dockColObserver.disconnect();
        this._dockColObserver = new ResizeObserver(() => {
            clearTimeout(this._dockColRedealT);
            this._dockColRedealT = setTimeout(() => {
                const mode = window.canvasRenderer
                    ? window.canvasRenderer.viewMode : '';
                if (mode !== 'power') return;
                if (this._dockColPick == null) return;
                if (this._dockPickColCount() !== this._dockColPick) {
                    this.renderHardwareDock();
                }
            }, 120);
        });
        this._dockColObserver.observe(body);
    }

    // The dock header's own controls, wired ONCE against the static markup:
    // with the middle sidebars retired the tray is the whole hardware
    // surface, so adding a processor, adding a distro and the attachment
    // flag live on its header bar. The chevron proxies the existing fold
    // toggle - one collapse mechanism, one stored state, just reachable
    // from inside the bar the eye is already on (the hanging tab stays as
    // the way back once the tray is folded to nothing).
    _wireDockChrome() {
        const fold = document.getElementById('hw-dock-fold');
        if (fold) fold.addEventListener('click', () => {
            const toggle = document.getElementById('hardware-dock-toggle');
            if (toggle) toggle.click();
        });
        const addBtn = document.getElementById('processor-add-btn');
        const picker = document.getElementById('processor-add-device');
        if (addBtn && picker) addBtn.addEventListener('click', () => {
            if (!picker.value) return;
            sendClientLog('processor_add_clicked', { deviceId: picker.value });
            this._processorRequest('/api/processors', 'POST',
                                   { deviceId: picker.value },
                                   'Add Processor');
        });
        // The flag pill toggles its rows open and closed - view state, no
        // undo entry, no localStorage: only the session remembers, and only
        // until the next load. Opening or closing moves the canvas's bottom
        // edge, so the backing store settles the way the body render does.
        const flag = document.getElementById('hw-dock-flag');
        if (flag) flag.addEventListener('click', () => {
            this._dockFlagOpen = !this._dockFlagOpen;
            const dock = document.getElementById('hardware-dock');
            const before = dock ? dock.offsetHeight : 0;
            this._renderDockFlag(window.canvasRenderer
                ? window.canvasRenderer.viewMode : '');
            if (dock && dock.offsetHeight !== before
                    && typeof this.settleLayout === 'function') {
                this.settleLayout();
            }
        });
        const addDistro = document.getElementById('power-distro-add');
        if (addDistro) addDistro.addEventListener('click', () => {
            this.addDistro();
            this._restateNaming();
        });
        // The gear popover's teardown gestures, the menu idiom: click-away
        // and Escape, bound once at the document. A press on the popover's
        // own anchor is the toggle's business, not a dismissal.
        document.addEventListener('mousedown', (e) => {
            if (!this._hwPopover) return;
            const pop = document.getElementById('hw-gear-popover');
            if (pop && pop.contains(e.target)) return;
            const anchor = e.target && e.target.closest
                && e.target.closest('[data-hwpop]');
            if (anchor && anchor.dataset.hwpop === this._hwPopover.id) return;
            // A grab of the tray's resize strip is a resize, not a
            // dismissal: the popover stays and follows its gear.
            if (e.target && e.target.closest
                    && e.target.closest('.lrd-resize-handle')) return;
            this._hwPopoverClose();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this._hwPopover) this._hwPopoverClose();
        });
        // The popover is placed against a window and a tray that both
        // change size under it: re-place on either, so it never sits half
        // off-screen after a resize or a dock drag.
        window.addEventListener('resize', () => this._hwPopoverReflow());
        const dockEl = document.getElementById('hardware-dock');
        if (dockEl && typeof ResizeObserver !== 'undefined') {
            try {
                new ResizeObserver(() => this._hwPopoverReflow())
                    .observe(dockEl);
            } catch (e) { /* no observer: resize alone re-places */ }
        }
    }

    // ── drawing ───────────────────────────────────────────────────────────

    renderHardwareDock() {
        const dock = document.getElementById('hardware-dock');
        const body = document.getElementById('hardware-dock-body');
        if (!dock || !body) return;
        const mode = window.canvasRenderer ? window.canvasRenderer.viewMode : '';
        // The port chips carry per-port editors now, so a field mid-edit
        // rides the wipe by its data-lrd-field key - the same guard every
        // panel rebuild takes before its own innerHTML wipe.
        if (typeof this._preserveEditorFocus === 'function') {
            this._preserveEditorFocus();
        }
        // Remember which chip FACE held focus through the wipe, by its
        // stable key - the same reason the panels carry data-lrd-field.
        const focused = document.activeElement
            && document.activeElement.dataset
            && document.activeElement.dataset.hwdock;
        const before = dock.offsetHeight;
        body.innerHTML = '';
        if (mode === 'data-flow') {
            this._dockRenderData(body);
        } else if (mode === 'power') {
            this._dockRenderPower(body);
        }
        // The chips fold their editors inside them on BOTH sides now - the
        // port chips their name boxes, the occupied circuit chips their
        // label override - so the tile machinery wires them after every
        // wipe. Which chip is open rode the wipe on the app (_openTiles),
        // the way the fold state rides it in localStorage; a free circuit
        // chip has no editor and _wireTiles skips it.
        if (typeof this._wireTiles === 'function') this._wireTiles(body);
        // The header bar and the issues strip are per-view too: which add
        // cluster shows, what the strip warns about.
        this._renderDockChrome(mode);
        // Every hardware section - card, breakout box, distro, multi - folds
        // by the app's one section machinery, so "this card is done, get it
        // out of the way" is the same gesture folding a sidebar block is.
        // The wipe above threw the wired nodes away; wire the fresh ones and
        // the stored per-section state re-applies.
        if (typeof this._wireSectionCollapse === 'function') {
            this._wireSectionCollapse(body);
        }
        if (focused) {
            const again = body.querySelector(
                `[data-hwdock="${CSS.escape(focused)}"]`);
            if (again) {
                // The chip the focus is coming back to may sit inside a
                // section the user folded - the restore doctrine: a thing
                // the app is programmatically focusing must be visible.
                // SECTIONS only, deliberately not _expandSectionsFor: that
                // helper also opens the closed TILE around a field, and a
                // chip FACE is visible on a closed tile - opening the
                // editor here would open a chip nobody clicked every time
                // Tab parks focus on a face through a rebuild.
                this._dockRevealSections(again);
                again.focus();
            }
        }
        // An open gear popover describes a header the wipe just replaced:
        // rebuild its content against the fresh state, or close it when its
        // anchor stopped existing (the card was removed, the view left).
        this._hwPopoverRefresh();
        // Content growing or shrinking the tray moves the canvas's bottom
        // edge; the backing store has to follow or a strip paints stale.
        if (dock.offsetHeight !== before
                && typeof this.settleLayout === 'function') {
            this.settleLayout();
        }
    }

    // ── the header bar, the attachment flag and the issues strip ─────────
    //
    // The dock's chrome: which add cluster the header shows, what the
    // attachment flag says, and what the strip under the header warns
    // about. The strip is the refuse-and-offer surface the retired Port
    // Numbering panel was - the data side re-hosts its issue rows
    // (app-port-assignment.js renderPortAssignmentPanel), and the power
    // side fills the same rows with the clash / overflow / same-name
    // warnings its sidebar tiles used to wear. The per-screen "not
    // attached" story is the FLAG's, not the strip's: one pill instead of
    // a wall of red rows, opened only when asked.
    _renderDockChrome(mode) {
        const dataCtl = document.getElementById('hw-dock-data-controls');
        const powerCtl = document.getElementById('hw-dock-power-controls');
        const strip = document.getElementById('hw-dock-issues');
        if (dataCtl) {
            dataCtl.classList.toggle('view-hidden', mode !== 'data-flow');
        }
        if (powerCtl) {
            powerCtl.classList.toggle('view-hidden', mode !== 'power');
        }
        if (mode === 'data-flow') {
            const picker = document.getElementById('processor-add-device');
            // Refill only while nobody is standing in it: the options are
            // static per catalog, and rewriting a focused select would
            // close it under the pointer.
            if (picker && this._processorCatalog
                    && picker !== document.activeElement) {
                const devices = this._processorDevices('processor');
                if (picker.querySelectorAll('option').length
                        !== devices.length + 1) {
                    const keep = picker.value;
                    this._fillDeviceSelect(picker, devices, keep,
                                           'Add a processor…');
                }
            }
            // The strip narrates the assignment; that render owns it.
            if (typeof this.renderPortAssignmentPanel === 'function') {
                this.renderPortAssignmentPanel();
            }
        } else {
            if (strip) {
                strip.innerHTML = '';
                if (mode === 'power') this._dockPowerStrip(strip);
            }
        }
        // The flag reads both views' attachment (and hides itself anywhere
        // else), so it paints after whichever side just rendered.
        this._renderDockFlag(mode);
    }

    // The power view's warnings, as strip rows: collected during the body
    // render (the same computations the chips and headers drew from, never
    // a second derivation) plus the current screen's empty-plan reason.
    // Red rows are questions - a tail claimed twice, a box past its six
    // tails, a distro over its rating, a plan a power error emptied; amber
    // rows are conditions - two multis wearing one name on two numbers.
    _dockPowerStrip(strip) {
        (this._dockPowerWarnings || []).forEach(w => {
            const row = document.createElement('div');
            row.className = 'hw-dock-issue'
                + (w.mild ? ' hw-dock-issue-mild' : '');
            const msg = document.createElement('span');
            msg.className = 'hw-dock-issue-msg';
            msg.textContent = w.text;
            row.appendChild(msg);
            if (w.offer) {
                const btn = document.createElement('button');
                btn.className = 'btn';
                btn.style.padding = '4px 8px';
                btn.style.fontSize = '11px';
                btn.style.background = '#333';
                btn.textContent = w.offer.label;
                if (w.offer.title) btn.title = w.offer.title;
                btn.addEventListener('click', w.offer.run);
                row.appendChild(btn);
            }
            strip.appendChild(row);
        });
    }

    // ── the attachment flag ──────────────────────────────────────────────
    //
    // One pill on the header where per-screen "not attached" rows used to
    // stack: red with a SCREEN count while any screen has unattached ports
    // (Data) or circuits (Power), green once hardware exists and holds
    // everything, hidden while there is nothing to attach TO - no card
    // with a settled capacity, no distro - because no hardware is the
    // default state of a project, not a problem to nag about (the gate the
    // server's _overflow_issues keeps, read here off the same resolution).
    // Clicking the red pill opens one row per unattached screen directly
    // under the header; clicking a row centers the canvas on that screen.
    // Closed is the default and the point: the count is the always-on
    // part, and the screen-by-screen rows come out only when asked.

    // What the flag says, or null for hidden. Each side reads its own one
    // authority: the data side the server's assignment resolution
    // (per-screen unplaced/required - placement is never re-derived on the
    // client), the power side the soca plan (a multi with no distroId is
    // unattached; a screen with no circuits at all has nothing to attach
    // and does not count).
    _dockFlagState(mode) {
        if (mode === 'data-flow') {
            const res = this._assignment;
            if (!res || !res.configured
                    || !(res.cards || []).some(c => c.capacity)) {
                return null;
            }
            return {
                unit: 'ports',
                screens: (res.screens || [])
                    .filter(scr => (scr.unplaced || []).length)
                    .map(scr => ({
                        layerId: scr.layerId,
                        name: scr.name,
                        numbers: scr.unplaced.map(i => i + 1),
                        total: scr.required,
                    })),
            };
        }
        if (mode === 'power') {
            const distros = this.getDistros ? this.getDistros() : [];
            if (!distros.length) return null;
            const screens = [];
            for (const l of (this.project.layers || [])) {
                if ((l.type || 'screen') !== 'screen') continue;
                const plan = this.getSocaPlan(l);
                if (!plan.length) continue;
                const numbers = plan.filter(s => !s.distroId)
                    .flatMap(s => s.legs.map(g => g.circuit))
                    .sort((a, b) => a - b);
                if (!numbers.length) continue;
                screens.push({
                    layerId: l.id, name: l.name, numbers,
                    total: plan.reduce((n, s) => n + s.legs.length, 0),
                });
            }
            return { unit: 'circuits', screens };
        }
        return null;
    }

    _renderDockFlag(mode) {
        const flag = document.getElementById('hw-dock-flag');
        const rows = document.getElementById('hw-dock-attach');
        if (!flag || !rows) return;
        const state = this._dockFlagState(mode);
        rows.innerHTML = '';
        if (!state) {
            // Nothing to attach to: the flag has nothing to say. The open
            // state drops too, or rows left open over vanished hardware
            // would reopen unasked the moment hardware returns.
            flag.classList.add('view-hidden');
            this._dockFlagOpen = false;
            return;
        }
        flag.classList.remove('view-hidden');
        const n = state.screens.length;
        flag.classList.toggle('hw-dock-flag-ok', n === 0);
        flag.innerHTML = '';
        const mark = document.createElement('span');
        mark.textContent = n ? '⚑' : '✓';
        flag.appendChild(mark);
        const word = document.createElement('span');
        word.textContent = n ? 'not all attached' : 'all attached';
        flag.appendChild(word);
        const badge = document.createElement('span');
        badge.className = 'hw-dock-flag-n';
        badge.textContent = String(n);
        flag.appendChild(badge);
        flag.title = n
            ? `${n} screen${n === 1 ? '' : 's'} with ${state.unit} not `
                + 'attached. Click to list them; click a row to find its '
                + 'screen on the canvas.'
            : `Every screen's ${state.unit} are attached.`;
        if (!n) {
            // Green closes the book: the look is finished, so the open
            // state drops rather than lying in wait to reopen the rows
            // unasked the next time something comes unattached.
            this._dockFlagOpen = false;
            return;
        }
        if (!this._dockFlagOpen) return;
        state.screens.forEach(scr => {
            rows.appendChild(this._dockBuildFlagRow(scr, state.unit));
        });
    }

    // One unattached screen as one row: bold name, the count, the numbers
    // as small chips - a long run elided to its first three and its last,
    // the way a hand would say it ("1 2 3 … 7"). The whole row is one
    // gesture: name or chip, the click centers the canvas on the screen
    // (per-port targeting can come later; today every chip's answer is
    // "over there").
    _dockBuildFlagRow(scr, unit) {
        const row = document.createElement('div');
        row.className = 'hw-dock-attach-row';
        const name = document.createElement('span');
        name.className = 'hw-dock-attach-name';
        name.textContent = scr.name;
        row.appendChild(name);
        const cnt = document.createElement('span');
        cnt.className = 'hw-dock-attach-cnt';
        cnt.textContent = `${scr.numbers.length} of ${scr.total} ${unit}`;
        row.appendChild(cnt);
        const chips = document.createElement('span');
        chips.className = 'hw-dock-attach-chips';
        const shown = scr.numbers.length > 5
            ? [...scr.numbers.slice(0, 3), '…',
               scr.numbers[scr.numbers.length - 1]]
            : scr.numbers;
        shown.forEach(v => {
            const chip = document.createElement('span');
            chip.className = 'hw-dock-attach-chip';
            chip.textContent = String(v);
            chips.appendChild(chip);
        });
        row.appendChild(chips);
        row.title = `${scr.name} - ${scr.numbers.length} of ${scr.total} `
            + `${unit} not attached. Click to center the canvas on it.`;
        row.addEventListener('click', () => {
            this.centerCanvasOnLayer(scr.layerId);
        });
        return row;
    }

    // Pan (never zoom) so the layer's bounds sit centered in the viewport,
    // then pulse it - the flag rows' answer to "which one is that". View
    // state through and through: the pan is the pan the hand makes, so it
    // earns no undo entry, exactly as dragging the canvas earns none. The
    // walk is zoomActual's own (active-view bounds plus the layer's canvas
    // workspace offset) minus its zoom math - one coordinate pipeline, not
    // a second one.
    centerCanvasOnLayer(layerId) {
        const r = window.canvasRenderer;
        const layer = (this.project.layers || [])
            .find(l => String(l.id) === String(layerId));
        if (!r || !layer) return;
        const bounds = r.getLayerBoundsInActiveView(layer);
        const ws = r._layerCanvasOffset(layer);
        const cx = bounds.x + ws.wx + bounds.width / 2;
        const cy = bounds.y + ws.wy + bounds.height / 2;
        r.panX = r.canvas.width / 2 - cx * r.zoom;
        r.panY = r.canvas.height / 2 - cy * r.zoom;
        r.pulseLayer(layer.id);
    }

    // ── the gear popover ─────────────────────────────────────────────────
    //
    // One popover for every header's ⚙, following the app's menu idiom:
    // positioned at the gear (above it - the dock sits at the window's
    // bottom), closed by click-away or Escape (_wireDockChrome), refreshed
    // in place across the dock's wholesale rebuilds so an open panel never
    // narrates stale state. The content builders live with their owners
    // (app-processors.js for the device tree, app-power.js for distros);
    // their fields carry data-lrd-field keys, so the focus machinery treats
    // a popover field exactly like a panel field.
    _hwPopoverToggle(anchor, id, build) {
        if (this._hwPopover && this._hwPopover.id === id) {
            this._hwPopoverClose();
            return;
        }
        this._hwPopover = { id, build };
        this._hwPopoverRender(anchor);
    }

    _hwPopoverRender(anchor) {
        let pop = document.getElementById('hw-gear-popover');
        if (!pop) {
            pop = document.createElement('div');
            pop.id = 'hw-gear-popover';
            document.body.appendChild(pop);
        }
        const content = this._hwPopover && this._hwPopover.build();
        if (!content) {
            this._hwPopoverClose();
            return;
        }
        // A rebuild while open keeps the reader's place in a long body.
        const oldBody = pop.querySelector('.hw-pop-body');
        const keepScroll = oldBody ? oldBody.scrollTop : 0;
        // Two parts: the fields scroll in a body; the destructive action
        // sits in a footer pinned to the popover's bottom edge, visible no
        // matter how long the body runs or how short the window is - a
        // Remove that only exists below a scroll nobody knows about is a
        // Remove that does not exist. The builders keep appending the
        // button last as they always have; the shell lifts it out.
        pop.innerHTML = '';
        const frame = document.createElement('div');
        frame.className = 'hw-pop-frame';
        const scroller = document.createElement('div');
        scroller.className = 'hw-pop-scroll';
        content.classList.add('hw-pop-body');
        scroller.appendChild(content);
        frame.appendChild(scroller);
        const remove = Array.from(content.children)
            .find(el => el.classList.contains('hw-pop-remove'));
        if (remove) {
            const foot = document.createElement('div');
            foot.className = 'hw-pop-foot';
            foot.appendChild(remove);
            frame.appendChild(foot);
        }
        pop.appendChild(frame);
        content.addEventListener('scroll', () => this._hwPopoverFade());
        pop.style.display = 'block';
        this._hwPopoverPlace(anchor);
        content.scrollTop = keepScroll;
        this._hwPopoverFade();
    }

    // Placement: measure at natural height, then open on whichever side of
    // the gear has the room - above when it fits there (the tray hugs the
    // window's bottom edge, so that is the usual answer), below when only
    // below fits, else the roomier side with the body clamped to it. The
    // clamp lands on the frame, so the footer keeps its full height and
    // only the body gives way. Re-run on resize and dock drags: a popover
    // placed for one window must not end up half off another.
    _hwPopoverPlace(anchor) {
        const pop = document.getElementById('hw-gear-popover');
        const frame = pop && pop.querySelector('.hw-pop-frame');
        if (!pop || !frame || !anchor) return;
        const margin = 8, gap = 6;
        pop.style.visibility = 'hidden';
        frame.style.maxHeight = '';
        const r = anchor.getBoundingClientRect();
        const natural = pop.getBoundingClientRect().height;
        const roomAbove = r.top - gap - margin;
        const roomBelow = window.innerHeight - r.bottom - gap - margin;
        let above;
        if (natural <= roomAbove) above = true;
        else if (natural <= roomBelow) above = false;
        else above = roomAbove >= roomBelow;
        // A gear jammed against an edge still gets a usable panel: the
        // floor lets the popover overlap the gear rather than shrink to a
        // sliver, and the viewport clamp below keeps it on screen.
        const floor = Math.min(160, window.innerHeight - 2 * margin);
        const room = Math.max(above ? roomAbove : roomBelow, floor);
        const chrome = pop.offsetHeight - frame.offsetHeight;  // borders
        frame.style.maxHeight = `${Math.round(room - chrome)}px`;
        const pr = pop.getBoundingClientRect();
        let x = Math.min(r.left, window.innerWidth - pr.width - margin);
        x = Math.max(margin, x);
        let y = above ? r.top - gap - pr.height : r.bottom + gap;
        y = Math.min(y, window.innerHeight - pr.height - margin);
        y = Math.max(margin, y);
        pop.style.left = `${Math.round(x)}px`;
        pop.style.top = `${Math.round(y)}px`;
        pop.style.visibility = 'visible';
    }

    // The bottom fade says "there is more" only while there is: on while
    // the body has content below its fold, off once the reader reaches it.
    _hwPopoverFade() {
        const pop = document.getElementById('hw-gear-popover');
        const body = pop && pop.querySelector('.hw-pop-body');
        if (!pop || !body) return;
        pop.classList.toggle('hw-pop-scrolls',
                             body.scrollHeight > body.clientHeight + 1);
        pop.classList.toggle('hw-pop-more',
            body.scrollHeight - body.clientHeight - body.scrollTop > 2);
    }

    // Reflow in place - no rebuild, so focus and scroll survive. An anchor
    // that has left layout (the tray folded, the view left) takes the
    // popover with it, the way a removed anchor does on refresh.
    _hwPopoverReflow() {
        if (!this._hwPopover) return;
        const anchor = document.querySelector(
            `[data-hwpop="${CSS.escape(this._hwPopover.id)}"]`);
        const r = anchor && anchor.getBoundingClientRect();
        if (!r || (r.width === 0 && r.height === 0)) {
            this._hwPopoverClose();
            return;
        }
        this._hwPopoverPlace(anchor);
        this._hwPopoverFade();
    }

    _hwPopoverClose() {
        this._hwPopover = null;
        const pop = document.getElementById('hw-gear-popover');
        if (pop) pop.style.display = 'none';
    }

    _hwPopoverRefresh() {
        if (!this._hwPopover) return;
        const anchor = document.querySelector(
            `[data-hwpop="${CSS.escape(this._hwPopover.id)}"]`);
        if (!anchor) {
            // Whatever the popover described stopped existing (removed, or
            // the view left) - a panel over a ghost closes.
            this._hwPopoverClose();
            return;
        }
        this._hwPopoverRender(anchor);
    }

    _dockNote(host, text) {
        const note = document.createElement('div');
        note.className = 'hw-dock-note';
        note.textContent = text;
        host.appendChild(note);
    }

    // One resolved card off the fresh tree, for the gear builds: a popover
    // rebuilt after a round-trip must describe the state that came back,
    // never the closure's stale snapshot.
    _dockFindCard(cardId) {
        for (const proc of this._processorsResolved || []) {
            for (const slot of proc.slots || []) {
                if (slot.card && slot.card.id === cardId) {
                    return { proc, card: slot.card };
                }
            }
        }
        return null;
    }

    _dockFindCvt(cvtId) {
        for (const proc of this._processorsResolved || []) {
            for (const slot of proc.slots || []) {
                const card = slot.card;
                if (!card) continue;
                const cvt = (card.cvts || []).find(c => c.id === cvtId);
                if (cvt) return { proc, card, cvt };
            }
        }
        return null;
    }

    _dockRenderData(host) {
        const procs = this._processorsResolved || [];
        if (!procs.length) {
            this._dockNote(host,
                'No processors. Pick a model in the header above, press '
                + 'Add, and its ports appear here to drag onto screens.');
            return;
        }
        const procEls = new Map();
        const unitsByCard = new Map();
        procs.forEach(proc => {
            const wrap = document.createElement('div');
            wrap.className = 'hw-dock-proc';
            // The processor's own strip: the model as static text, the name
            // edited inline, and the machine-level configuration
            // (redundancy, slots, remove) behind its ⚙. Not a drag handle -
            // a whole processor is not a droppable thing; its cards are.
            const title = document.createElement('div');
            title.className = 'hw-dock-proc-name';
            const model = document.createElement('span');
            model.textContent = proc.deviceName;
            title.appendChild(model);
            title.appendChild(this._dockHeadName({
                value: proc.name,
                placeholder: 'unnamed',
                key: `processor-name-${proc.id}`,
                title: 'Name this processor. A card\'s ports take the '
                    + 'nearest name above them.',
                onCommit: (val) => this._processorRequest(
                    `/api/processors/${proc.id}`, 'PUT', { name: val },
                    'Rename Processor'),
            }));
            const procPill = this._dockRedundancyPill(proc, null);
            this._dockHeadAugment(title, {
                controls: procPill ? [procPill] : [],
                gear: {
                    id: `proc-${proc.id}`,
                    title: 'Configure this processor - redundancy, slots, '
                        + 'remove.',
                    build: () => {
                        const p = (this._processorsResolved || [])
                            .find(x => x.id === proc.id);
                        return p ? this._buildProcGearContent(p) : null;
                    },
                },
            });
            wrap.appendChild(title);
            (proc.slots || []).forEach(slot => {
                if (!slot.card) return;
                const unit = this._dockBuildCard(proc, slot.card);
                unitsByCard.set(slot.card.id, unit);
                wrap.appendChild(unit);
            });
            procEls.set(proc.id, wrap);
            host.appendChild(wrap);
        });
        // The pair-presentation rule the panel follows, at the tray's two
        // levels: a designated backup UNIT nests whole - name strip and
        // all - under its main's block, and a backup card inside the same
        // chassis nests under the card it mirrors. The chips inside keep
        // their own keys and drags either way.
        procs.forEach(proc => {
            (proc.slots || []).forEach(slot => {
                const card = slot.card;
                if (card && card.backupFor
                        && card.backupFor.processorId === proc.id) {
                    this._nestBackupUnder(
                        unitsByCard.get(card.backupFor.cardId),
                        unitsByCard.get(card.id));
                }
            });
            const mainId = this._backupUnitMainId(proc);
            if (mainId) {
                this._nestBackupUnder(procEls.get(mainId),
                                      procEls.get(proc.id));
            }
        });
    }

    _dockBuildCard(proc, card) {
        const unit = document.createElement('div');
        unit.className = 'hw-dock-unit';

        const summary = ((this._assignment && this._assignment.cards) || [])
            .find(c => c.cardId === card.id);
        // A unit consumed as a 1:1 backup wears the tag its box-level
        // cousin wears - dragging it is pointless (every port is refused as
        // a return end) but hiding it would hide where the returns land.
        const cardTag = card.backupFor
            ? ` (backs up ${card.backupFor.title})` : '';
        const head = this._dockBuildHandle(
            {
                type: 'card', cardId: card.id,
                title: (card.name || card.deviceName) + cardTag,
            },
            `card-${card.id}`,
            card.deviceName + cardTag,
            '',
            'Drag the whole card onto a screen: its ports fill in order from '
            + 'the first unassigned, or the whole run moves here.',
            // The header's glance: how full the card is, the retired
            // panel's per-card usage foot worn as n/N and a fill line - so
            // a card folded away because it is done reads as done (a
            // green-full line) without opening it. Counts from the same
            // assignment summary the foot printed - never re-derived.
            summary && summary.capacityKnown && summary.capacity > 0
                ? { frac: summary.used / summary.capacity,
                    over: summary.used > summary.capacity,
                    text: `${summary.used}/${summary.capacity}` }
                : null);
        // The card's NAME edits inline where it reads; everything else the
        // panel's card block carried lives behind the ⚙. The redundancy
        // pill between them is a readout, not an editor.
        const cardPill = this._dockRedundancyPill(proc, card);
        this._dockHeadAugment(head, {
            controls: cardPill ? [cardPill] : [],
            name: {
                value: card.name,
                placeholder: proc.name || 'unnamed',
                key: `processor-card-name-${card.id}`,
                title: 'Name this card. Its ports read the name - name it '
                    + 'SR and they read SR-1, SR-2.',
                onCommit: (val) => this._processorRequest(
                    `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                    { name: val }, 'Rename Card'),
            },
            gear: {
                id: `card-${card.id}`,
                title: 'Configure this card - templates, mode, breakout '
                    + 'boxes, remove. Redundancy is set behind the '
                    + 'processor\'s \u2699.',
                build: () => {
                    const found = this._dockFindCard(card.id);
                    return found ? this._buildCardGearContent(found.proc,
                                                              found.card)
                        : null;
                },
            },
        });
        unit.appendChild(head);
        // Everything under the header folds as one body - the section
        // machinery's shape, transposed onto the tray's card unit.
        const unitBody = this._dockSectionBody(unit, head,
                                               `hwdock-card-${card.id}`);

        // The ports draw grouped the way they arrive: each breakout box gets
        // its own draggable strip holding its span of the card's ports, and
        // ports no box delivers stay directly under the card. A copy/backup
        // box lists the SAME card ports again - dragging it lands on the same
        // sockets as dragging its primary, because they are the same sockets.
        const cvts = card.cvts || [];
        const covered = new Set();
        cvts.forEach(cvt => {
            (cvt.ports || []).forEach(p => covered.add(p.number));
        });
        const loose = (card.ports || []).filter(p => !covered.has(p.number));
        if (loose.length) {
            unitBody.appendChild(this._dockBuildPortGrid(proc, card, loose));
        }
        const boxEls = new Map();
        cvts.forEach(cvt => {
            const nums = (cvt.ports || []).map(p => p.number);
            if (!nums.length) return;
            const box = document.createElement('div');
            box.className = 'hw-dock-box';
            // The span reads in the BOX's own numbers - 1-10 on every XD,
            // whichever trunk it hangs on - because that is what is
            // silkscreened on its face (the 2026-08-27 ruling: "B is 1-10
            // and D is 1-10"). The card-wide first/last ride the payload
            // below untouched; they are the server's window keys, not a
            // number anyone reads off metal.
            const locals = (cvt.ports || []).map(
                p => p.localNumber || p.number);
            const span = `${Math.min(...locals)}-${Math.max(...locals)}`;
            const tag = cvt.backupOf ? ' (backup)'
                : (cvt.duplicateOf ? ' (copy)' : '');
            // Four boxes all reading "Tessera XD" are four sections nobody
            // can tell apart, so an unnamed box on a trunked card wears its
            // trunk letter - "Tessera XD A" - the letters the pairing rule
            // itself is written in ("A backs up to B"). A hand-named box is
            // already told apart by its name. The name comes RESOLVED
            // (displayTitle) since every box numbers its own sockets from 1
            // and the server's refusals must call a box exactly what this
            // section header calls it - one implementation of the letter.
            const boxTitle = (cvt.displayTitle
                || cvt.name || cvt.deviceName) + tag;
            // The folded box's glance is occupancy in sockets - "8/10" and
            // a fill line - because "this box is done" is a count of claimed
            // sockets, read from the same occupancy the chips inside wear.
            const taken = (cvt.ports || []).filter(
                p => this._portOccupants(card.id, p.number).length).length;
            const total = (cvt.ports || []).length;
            const boxHead = this._dockBuildHandle(
                {
                    type: 'box', cardId: card.id,
                    first: Math.min(...nums), last: Math.max(...nums),
                    title: boxTitle,
                    beyondTrunks: !!cvt.beyondTrunks,
                },
                `box-${cvt.id}`,
                cvt.deviceName + tag,
                `ports ${span}`,
                'Drag the whole box onto a screen: the screen\'s ports fill '
                + 'onto this box\'s sockets in order from the first '
                + 'unassigned.',
                total > 0
                    ? { frac: taken / total, over: false,
                        text: `${taken}/${total}` }
                    : null);
            // The box's name edits inline; unnamed, the placeholder speaks
            // the RESOLVED title (trunk letter included), so "Tessera XD A"
            // still reads on the header the server's refusals name.
            this._dockHeadAugment(boxHead, {
                name: {
                    value: cvt.name,
                    placeholder: cvt.displayTitle || 'unnamed',
                    key: `processor-cvt-name-${cvt.id}`,
                    title: 'Name this box. Its sockets read the name the '
                        + 'way a card\'s ports read the card\'s.',
                    onCommit: (val) => this._processorRequest(
                        `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                        { name: val }, 'Rename Breakout Box'),
                },
                gear: {
                    id: `box-${cvt.id}`,
                    title: 'Configure this box - templates, facts, remove.',
                    build: () => {
                        const found = this._dockFindCvt(cvt.id);
                        return found ? this._buildBoxGearContent(
                            found.proc, found.card, found.cvt) : null;
                    },
                },
            });
            box.appendChild(boxHead);
            const boxBody = this._dockSectionBody(box, boxHead,
                                                  `hwdock-box-${cvt.id}`);
            boxBody.appendChild(this._dockBuildPortGrid(proc, card,
                                                        cvt.ports || [],
                                                        boxTitle));
            // A redundant pair of boxes is one group here too: B nests
            // under the A it backs (the panel's rule, worn by the tray),
            // and a box with no role stays the plain strip it was.
            boxEls.set(cvt.id, box);
            const main = cvt.backupOf && boxEls.get(cvt.backupOf);
            if (main) this._nestBackupUnder(main, box);
            else unitBody.appendChild(box);
        });
        return unit;
    }

    // Turn a dock unit into one of the app's foldable sections: the header
    // becomes the section head (arrow, double-click, per-id persistence -
    // app-core's _wireSectionCollapse owns the behaviour) and everything
    // that follows lives in the returned body. The header keeps being the
    // unit's DRAG handle: _dockArmDrag's 4px threshold already splits a
    // click from a drag, so the arrow's click folds and press-and-move past
    // the threshold still drags the folded unit's whole scope.
    _dockSectionBody(container, head, secId) {
        head.classList.add('lrd-sec-head');
        head.dataset.lrdSec = secId;
        const body = document.createElement('div');
        body.className = 'lrd-sec-body';
        container.appendChild(body);
        return body;
    }

    // Expand every folded section (and a pair's folded main) above `el` -
    // the section half of _expandSectionsFor, without its open-the-tile
    // half: a chip face is already visible on a CLOSED tile, so a face
    // restore must never open the editor nobody asked for.
    _dockRevealSections(el) {
        for (let n = el && el.parentElement; n; n = n.parentElement) {
            if (!n.classList) continue;
            if (n.classList.contains('lrd-sec-collapsed')) {
                this._setSectionCollapsed(n, false);
            }
            if (n.classList.contains('lrd-red-pair')) {
                const main = n.firstElementChild;
                if (main && main.classList
                        && main.classList.contains('lrd-sec-collapsed')
                        && !main.contains(el)) {
                    this._setSectionCollapsed(main, false);
                }
            }
        }
    }

    // The trunk letter lives on the resolved box now (displayTitle, from
    // resolve_card): the server's refusals name boxes too, and two spellings
    // of "Tessera XD A" would drift. Nothing here letters anything.

    // `boxTitle` names the breakout box a grid belongs to, where it belongs
    // to one - the disambiguator now that every box numbers its own sockets
    // from 1 (two boxes both have a "3", and the box name is how they are
    // told apart).
    _dockBuildPortGrid(proc, card, ports, boxTitle) {
        const grid = document.createElement('div');
        grid.className = 'lrd-tile-grid hw-dock-grid';
        ports.forEach(port => {
            grid.appendChild(this._dockBuildPortTile(proc, card, port,
                                                     boxTitle));
        });
        return grid;
    }

    // One port as one dense cell of its grid: number, the resolved label
    // (the assignment's answer, never re-derived here), occupant, and the
    // occupied/clash ground. The chip is both the drag handle AND the
    // port's editor - the dock is the one place ports appear, so the
    // editing the panel's tiles carried lives here now: click or Enter
    // (no movement) opens the editor IN the tile through the shared
    // _wireTiles machinery, press-and-move drags. The editor is hidden,
    // never detached (style.css .lrd-tile-body), so every field keeps
    // answering the focus-restore lookup from inside a closed chip.
    _dockBuildPortTile(proc, card, port, boxTitle) {
        const tile = document.createElement('div');
        tile.className = 'lrd-tile hw-dock-tile';
        // The tile machinery's keys, so the open editor comes back by id
        // through the tray's wholesale rebuilds - one open editor per card.
        // Keyed by the card-wide number ON PURPOSE: two boxes both display
        // a "3" now, and a key that repeated would restore the wrong chip.
        tile.dataset.lrdTile = `port-${card.id}-${port.number}`;
        tile.dataset.lrdTileBox = `card-${card.id}`;
        const occupants = this._portOccupants(card.id, port.number);
        if (occupants.length > 1) tile.classList.add('lrd-tile-clash');
        else if (occupants.length) tile.classList.add('lrd-tile-occupied');

        // What the chip's face SAYS is the socket's own silkscreen - the
        // box's 1..N behind a box (the 2026-08-27 ruling), the card's
        // number elsewhere. The card-wide ordinal stays in the keys and
        // payloads above and below, where the server does its arithmetic.
        const spoken = port.localNumber || port.number;
        const face = document.createElement('div');
        face.className = 'lrd-tile-face';
        const top = document.createElement('div');
        top.className = 'lrd-tile-line';
        const num = document.createElement('span');
        num.style.color = port.beyondCeiling ? '#d05a52' : 'var(--ps-faint, #969696)';
        num.textContent = String(spoken);
        top.appendChild(num);
        if (port.label) {
            const label = document.createElement('span');
            label.style.color = port.labelSource === 'manual'
                ? '#e0c98a' : 'var(--ps-text, #f0f0f0)';
            top.appendChild(document.createTextNode(' '));
            label.textContent = port.label;
            top.appendChild(label);
        }
        face.appendChild(top);
        const who = document.createElement('div');
        who.className = 'lrd-tile-line';
        if (!occupants.length) {
            if (port.backsUp) {
                // Claimed by role: this socket is another main's return end.
                // Same gold as the backup boxes, because it is the same job.
                // The class puts the role's gold rim on the socket geometry
                // (theme.css .lrd-tile-gold) beside the gold text.
                tile.classList.add('lrd-tile-gold');
                // The bare-number fallback speaks the main's LOCAL number -
                // the one beside its socket - with its box's name in front,
                // because every box counts from 1 and "port 1" alone could
                // be this very box's own first socket.
                who.style.color = '#c8a04a';
                const bu = port.backsUp;
                who.textContent = `backs up ${bu.label
                    || `${bu.boxTitle ? `${bu.boxTitle} ` : ''}port `
                        + `${bu.localPort || bu.port}`}`;
            } else {
                who.style.color = '#6a6a6a';
                who.textContent = 'free';
            }
        } else if (occupants.length > 1) {
            who.style.color = '#d05a52';
            who.textContent = 'clash';
        } else if (occupants[0].role === 'return') {
            // Derived occupancy: the socket carries this screen-port's
            // return, following its main - the role's gold, because the
            // claim is the role's, and only the main can clear it.
            tile.classList.add('lrd-tile-gold');
            who.style.color = '#c8a04a';
            who.textContent =
                `${occupants[0].name} p${occupants[0].number} return`;
        } else {
            who.style.color = 'var(--ps-dim, #c0c0c0)';
            who.textContent = occupants[0].name;
        }
        face.appendChild(who);
        tile.appendChild(face);

        face.title = `Port ${spoken}`
            + (port.label ? ` - ${port.label}` : '')
            + (occupants.length
                ? ` - ${occupants.map(o => `${o.name} p${o.number}`
                    + (o.role === 'return' ? ' return' : '')).join(', ')}`
                : (port.backsUp
                    ? ` - backs up ${port.backsUp.label
                        || `port ${port.backsUp.localPort
                            || port.backsUp.port} on ${port.backsUp.boxTitle
                            || port.backsUp.cardTitle}`}`
                    : ' - free'))
            + (port.beyondCeiling ? ' - beyond this card’s ceiling' : '')
            + '. Click to edit'
            + (port.backsUp
                ? '. A backup port is that port\'s return end - nothing '
                    + 'else can land on it.'
                : '; drag onto a port run to place it there'
                    + (occupants.some(o => !o.role)
                        ? '; drag back onto this tray to release it.' : '.'));

        // How full the socket is, worn twice (ground meter + bottom bar),
        // scored by the canvas badge's own authority - see _dockPortFill.
        this._dockChipFill(face, this._dockPortFill(card.id, port.number));

        // The ghost's fallback names the surface the socket is ON - the box
        // where there is one, since its local number only means something
        // beside the box's name. `port` in the payload stays the card-wide
        // socket: it is what the place/pin API runs on.
        this._dockWireDraggable(face, {
            type: 'port', cardId: card.id, port: port.number,
            title: port.label
                || `${boxTitle || card.name || card.deviceName} `
                + `port ${spoken}`,
        }, `port-${card.id}-${port.number}`);

        const editor = this._buildPortRow(proc, card, port);
        editor.classList.add('lrd-tile-body');
        tile.appendChild(editor);

        if (this._tileOpenId(tile.dataset.lrdTileBox)
                === tile.dataset.lrdTile) {
            tile.classList.add('lrd-tile-open');
        }
        return tile;
    }

    // One of a port editor's two name boxes, captioned the way the soca
    // rows' fields are: an unlabeled box beside another unlabeled box reads
    // as noise, and these two hold different ends of the same cable. The
    // resolved label sits in the placeholder, so an empty box still reads
    // as what that end is actually called. (Moved here whole from the
    // Processors panel when the dock became the one port surface - the
    // data-lrd-field keys came with it, and they exist nowhere else.)
    _buildPortNameField(caption, fieldKey, value, placeholder, manual,
                        titles, onCommit) {
        const cell = document.createElement('div');
        cell.style.flex = '1 1 70px';
        cell.style.minWidth = '0';
        const cap = document.createElement('label');
        cap.style.display = 'block';
        cap.style.fontSize = '10px';
        cap.style.color = 'var(--ps-dim, #c0c0c0)';
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

    // The open chip's editor: the two name boxes on a wrapping line, then
    // the occupancy detail. Naming and reading only - putting a screen ON
    // the socket stays the chip's own drag, so no set/place control ever
    // grows here: one gesture, one set of rules.
    _buildPortRow(proc, card, port) {
        const wrap = document.createElement('div');
        const row = document.createElement('div');
        // The names are inputs rather than text because a port is a socket
        // someone has to be able to call what the house already calls it,
        // and since the processor beats a screen's own override for an
        // assigned port, these boxes are the ONLY place left to do it.
        // Making it a mode to find would strand every port that needs one.
        row.style.display = 'flex';
        row.style.flexWrap = 'wrap';
        row.style.gap = '4px';
        row.style.alignItems = 'center';
        row.style.fontSize = '11px';
        row.style.fontFamily = 'monospace';
        row.style.marginBottom = '2px';

        const rename = (body, action) => this._processorRequest(
            `/api/processors/${proc.id}/cards/${card.id}/ports/${port.number}`,
            'PUT', body, action);

        // Two ends of one socket, named side by side. The fields share a
        // wrapping line of their own: two 70px boxes fit abreast in a chip
        // opened across its grid row and stack where a narrow unit squeezes
        // them, exactly as the soca rows' captioned fields do.
        const names = document.createElement('div');
        names.style.display = 'flex';
        names.style.flexWrap = 'wrap';
        names.style.gap = '4px';
        names.style.margin = '0 0 4px 0';
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
                    + 'name derived from the primary (R1-1 for P1-1).',
                unnamed: 'Name this port’s redundancy run. Left blank it is '
                    + 'derived from the primary: its leading P becomes R '
                    + '(R1-1 for P1-1), any other name takes an R after it.',
            },
            (val) => rename({ returnName: val },
                            'Rename Processor Port Return')));

        const who = document.createElement('div');
        // the one elastic cell of its line, same shape as the assignment rows
        who.style.flex = '1 1 60px';
        who.style.minWidth = '0';
        who.style.overflow = 'hidden';
        who.style.textOverflow = 'ellipsis';
        who.style.whiteSpace = 'nowrap';
        const occupants = this._portOccupants(card.id, port.number);
        if (!occupants.length) {
            // A port with nothing on it says so. The chip face says it too,
            // but the open editor must not go silent where the face spoke.
            who.style.color = '#4a4a4a';
            who.textContent = 'free';
            who.title = 'No screen is on this port.';
        } else {
            const parts = occupants.map(o => `${o.name} p${o.number}`
                + (o.role === 'return' ? ' return' : ''));
            const derived = occupants.length === 1
                && occupants[0].role === 'return';
            who.style.color = occupants.length > 1 ? '#d05a52'
                : (derived ? '#c8a04a' : 'var(--ps-dim, #c0c0c0)');
            who.textContent = parts.join(', ')
                + (occupants.length > 1 ? ' - clash' : '');
            who.title = occupants.length > 1
                ? `${parts.join(' and ')} both claim this port. Nothing has `
                  + 'been renumbered - see Port Numbering.'
                : (derived
                    ? `${occupants[0].name} port ${occupants[0].number}'s `
                      + 'return end - it follows the main and clears with it.'
                    : `${occupants[0].name}, its port ${occupants[0].number}`);
        }
        row.appendChild(who);
        wrap.appendChild(names);

        // The port's place in the redundancy mapping, stated where its
        // labels are edited. A consumed port says whose return it carries; a
        // backed main says which physical socket its return comes back on -
        // the same socket its Return placeholder is already named after.
        if (port.backsUp) {
            const role = document.createElement('div');
            role.style.fontSize = '11px';
            role.style.color = '#c8a04a';
            role.style.margin = '0 0 4px 0';
            role.textContent = `Backs up ${port.backsUp.label
                || `port ${port.backsUp.localPort || port.backsUp.port} `
                    + `on ${port.backsUp.boxTitle || port.backsUp.cardTitle}`}`
                + ' - this socket carries its return.';
            wrap.appendChild(role);
        } else if (port.backedBy) {
            const back = document.createElement('div');
            back.style.fontSize = '11px';
            back.style.color = 'var(--ps-dim, #c0c0c0)';
            back.style.margin = '0 0 4px 0';
            back.textContent = `Return comes back on ${port.backedBy.label
                || `port ${port.backedBy.localPort || port.backedBy.port} `
                    + `on ${port.backedBy.boxTitle
                        || port.backedBy.cardTitle}`}.`;
            wrap.appendChild(back);
        }

        // Manual mode's per-port pick: which socket backs THIS one. Sparse
        // by design - a blank port number clears the pick and the main
        // simply has no backup, because manual is explicit.
        const shape = card.redundancyShape;
        if (shape && !shape.forced && shape.mode === 'manual'
                && !card.backupFor && !port.backsUp) {
            const picked = (card.backupPorts || {})[String(port.number)] || null;
            const pick = document.createElement('div');
            pick.style.display = 'flex';
            pick.style.gap = '4px';
            pick.style.alignItems = 'center';
            pick.style.margin = '0 0 4px 0';
            const cap = document.createElement('span');
            cap.style.fontSize = '10px';
            cap.style.color = 'var(--ps-dim, #c0c0c0)';
            cap.textContent = 'Backed by';
            pick.appendChild(cap);

            const cardSel = document.createElement('select');
            cardSel.dataset.lrdField =
                `processor-port-backup-card-${card.id}-${port.number}`;
            cardSel.style.flex = '1';
            cardSel.style.minWidth = '0';
            const own = document.createElement('option');
            own.value = card.id;
            own.textContent = card.name || proc.name || card.deviceName;
            cardSel.appendChild(own);
            this._otherCards(card.id).forEach(({ proc: p, card: c }) => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name || p.name || c.deviceName;
                if (picked && picked.cardId === c.id) opt.selected = true;
                cardSel.appendChild(opt);
            });

            const portBox = document.createElement('input');
            portBox.type = 'number';
            portBox.min = '1';
            portBox.dataset.lrdField =
                `processor-port-backup-port-${card.id}-${port.number}`;
            portBox.style.width = '52px';
            portBox.placeholder = 'port';
            portBox.value = picked ? String(picked.port) : '';
            portBox.title = 'The port whose socket carries this one’s '
                + 'return. Blank means no backup.';

            // Through the same PUT the name boxes use - one route, one rule
            // about what a port edit is.
            const commit = () => {
                const value = parseInt(portBox.value, 10);
                const body = portBox.value.trim() === '' || !(value >= 1)
                    ? { backup: null }
                    : { backup: { cardId: cardSel.value, port: value } };
                rename(body, 'Change Port Backup');
            };
            cardSel.addEventListener('change', commit);
            portBox.addEventListener('change', commit);
            pick.appendChild(cardSel);
            pick.appendChild(portBox);
            wrap.appendChild(pick);
        }

        wrap.appendChild(row);
        return wrap;
    }

    _dockRenderPower(host) {
        // The strip's warnings are collected DURING this render, from the
        // exact figures the chips and headers draw - a second derivation
        // could disagree with the surfaces it warns about.
        // (_renderDockChrome paints them after the body.)
        this._dockPowerWarnings = [];
        // Stamped before ANY early return, so the resize watcher always
        // compares against the pick this render actually saw.
        this._dockColPick = this._dockPickColCount();
        // A plan a POWER ERROR emptied gets the error told where the multis
        // would be - the story the retired soca panel used to tell. Every
        // legitimately-empty state stays silent (_socaPlanEmptyReason).
        const cur = this.currentLayer;
        if (cur && (cur.type || 'screen') === 'screen'
                && typeof this._socaPlanEmptyReason === 'function'
                && !(this.getSocaPlan(cur) || []).length) {
            const why = this._socaPlanEmptyReason(cur);
            if (why) {
                this._dockPowerWarnings.push({
                    text: `No circuits on ${cur.name} — ${why}`,
                });
            }
        }
        const distros = this.getDistros ? this.getDistros() : [];
        if (!distros.length) {
            this._dockNote(host,
                'No distros. Press + Add distro above and its multis appear '
                + 'here to drag onto circuits.');
            return;
        }
        // The roll-up's per-distro amps, read once for the headers' glance
        // bars - the roll-up's own figures, never re-summed here.
        const loads = typeof this.getDistroLoads === 'function'
            ? this.getDistroLoads() : [];
        // The distros deal into vertical COLUMNS (2026-08-30: a folded
        // distro in a flex-wrap row left a dead blank below its header,
        // because wrap rows are uniform-height). i % nCols keeps the deal
        // stable across re-renders - index-based, never height-based, so
        // units don't jump columns when loads change - and inside a
        // column the stack means the unit below a folded one slides
        // straight up. The COUNT is adaptive (same day, third pass: three
        // 380px floors cannot fit a 920px body, so the last column
        // WRAPPED below the stack and grew alone to the cap - "C2 ... is
        // not going to the right where it should"): as many columns as
        // the body's width genuinely holds, so every column keeps the
        // no-clip floor by construction and none ever wraps. The basis
        // is stamped inline to match; _wireDockColumnRedeal re-deals when
        // a resize crosses a count threshold (_dockColPick, stamped at
        // the top of this render, is the comparison point).
        const nCols = Math.max(1, Math.min(
            this._dockColPick, distros.length));
        const colBasis =
            `calc((100% - ${(nCols - 1) * 10}px) / ${nCols})`;
        const cols = [];
        for (let i = 0; i < nCols; i++) {
            const col = document.createElement('div');
            col.className = 'hw-dock-col';
            col.style.flexBasis = colBasis;
            cols.push(col);
            host.appendChild(col);
        }
        distros.forEach((d, i) => {
            cols[i % nCols].appendChild(this._dockBuildDistro(
                d, loads.find(x => x.id === d.id)));
        });
        // Two multis on one distro wearing one name on two numbers is one
        // box on paper and two on the patch - a label problem, not a block,
        // so it warns amber. Deduped per (distro, name): the collision is
        // symmetric and one row saying both sides is one problem stated
        // once.
        const seen = new Set();
        for (const l of (this.project.layers || [])) {
            if ((l.type || 'screen') !== 'screen') continue;
            for (const rec of this._powerNaming(l).socas.values()) {
                if (!rec.distroId || !rec.name) continue;
                const collisions = this._socaNameCollisions(l, rec.index);
                if (!collisions.length) continue;
                const key = `${rec.distroId}|${rec.name}`;
                if (seen.has(key)) continue;
                seen.add(key);
                const d = distros.find(x => x.id === rec.distroId);
                const minNo = Math.min(rec.number,
                                       ...collisions.map(c => c.number));
                this._dockPowerWarnings.push({
                    mild: true,
                    text: `${rec.name} names two multis on `
                        + `${d ? d.name : 'one distro'} — ${l.name} at `
                        + `No. ${rec.number}, ${collisions.map(c =>
                            `${c.layerName} at No. ${c.number}`).join(', ')}. `
                        + `Same box? Pin both to No. ${minNo}.`,
                });
            }
        }
    }

    _dockBuildDistro(d, load) {
        const unit = document.createElement('div');
        // hw-dock-distro is presentation only: the density pass gives the
        // power units a wider no-clip floor than the data cards need.
        unit.className = 'hw-dock-unit hw-dock-distro';
        const phase = Number(d.phase) === 3 ? '3φ' : '1φ';
        const head = this._dockBuildHandle(
            { type: 'distro', distroId: d.id, title: d.name || d.id },
            `distro-${d.id}`,
            '',
            `${d.voltage || '?'}V·${phase}`,
            'Drag the whole distro onto a screen: its unassigned multis all '
            + 'land on this distro, numbered automatically.',
            load && load.ratingA > 0
                ? { frac: load.amps / load.ratingA, over: !!load.over,
                    text: `${load.amps.toFixed(1)}/${load.ratingA} A` }
                : null);
        // An over-loaded service is a strip question, not just a red bar.
        if (load && load.over) {
            this._dockPowerWarnings.push({
                text: `${d.name || d.id} — ${load.amps.toFixed(1)} A / `
                    + `${load.ratingA} A (${Math.round(load.pct)}%) — OVER`,
            });
        }
        // Balance sits ON the header (legs never interact across services,
        // so each distro carries its own), and the electrical setup -
        // rating, voltage, phase, phasing, location, remove - lives behind
        // the ⚙. The name edits inline where the header reads it.
        // Order settled 2026-08-30, second pass: the figures read first,
        // the action sits with the gear - name · amps · bar · 208V·3φ ·
        // Balance · ⚙. (The first pass tried Balance ahead of the bar;
        // seeing it real, the user swapped it back.)
        let bal = null;
        if (Number(d.phase) === 3) {
            bal = document.createElement('button');
            bal.className = 'btn hw-dock-btn';
            bal.textContent = 'Balance';
            bal.dataset.lrdField = `distro-balance-${d.id}`;
            bal.title = 'Balance legs. Searches which set of six breakers '
                + 'each partly-filled multi on THIS distro should land on. '
                + 'A full multi balances itself, so only short ones move. '
                + 'Nothing changes until you accept it.';
            bal.addEventListener('click', (e) => {
                e.stopPropagation();
                this.showBalanceDialog(d.id);
            });
        }
        this._dockHeadAugment(head, {
            name: {
                value: d.name,
                placeholder: 'distro',
                key: `distro-name-${d.id}`,
                title: 'Name this power source. Multis on it follow the '
                    + 'name - a distro named SL feeds SL1, SL2.',
                onCommit: (val) => {
                    this.updateDistro(d.id, { name: val });
                    this._restateNaming();
                },
            },
            gear: {
                id: `distro-${d.id}`,
                title: 'Configure this distro - rating, voltage, phase, '
                    + 'phasing, location, remove.',
                build: () => {
                    const raw = this.getDistros().find(x => x.id === d.id);
                    return raw ? this._buildDistroGearContent(raw) : null;
                },
            },
        });
        if (bal) {
            // after the voltage tag, before the gear: the gear is the
            // header's last child, so inserting before it lands Balance
            // beside it (a gearless header appends, harmlessly)
            head.insertBefore(bal, head.querySelector('.hw-dock-gear'));
        }
        unit.appendChild(head);
        // The LEGS line rides between the header and the foldable body, so
        // a folded distro still reads its balance at a glance - the
        // sidebar's folded-glance bars generalized to an always-on line.
        const legs = this._dockDistroLegsLine(load);
        if (legs) unit.appendChild(legs);
        // The OUTPUTS row rides under LEGS, outside the fold too: the
        // connectors a folded distro offers are still what you reach for.
        const outs = this._dockDistroOutputsRow(d);
        if (outs) unit.appendChild(outs);
        const body = this._dockSectionBody(unit, head,
                                           `hwdock-distro-${d.id}`);

        // The multis a distro offers are demand-driven, the same unbounded
        // rule the old number select used: every occupied or pinned number,
        // plus exactly one spare on the end, so there is always a free box
        // to drag and never a wall of empty ones. Each multi is a bounded
        // SECTION of its distro - the data side's box grammar - holding its
        // six tails as individually draggable circuit chips.
        const inUse = this._distroMultiNumbers(d.id);
        const maxN = Math.max(0, ...inUse.keys()) + 1;
        for (let n = 1; n <= maxN; n++) {
            body.appendChild(this._dockBuildMulti(d, n, inUse.get(n) || []));
        }
        return unit;
    }

    // The slim LEGS line under a 3-phase distro's header: per-leg amps with
    // a mini meter each and the NEMA-style imbalance figure - the roll-up's
    // own numbers (getDistroLoads), never re-summed. Null where there is
    // nothing to say (single phase, or no load record yet).
    _dockDistroLegsLine(load) {
        if (!load || !load.legs) return null;
        const row = document.createElement('div');
        row.className = 'hw-dock-legs';
        row.title = 'Leg loading. Per-leg current is a phasor sum - '
            + 'line-to-line circuits sit 30 degrees off each leg\'s '
            + 'line-to-neutral reference, so they are not simply added. '
            + 'Imbalance is NEMA-style: max deviation from the average.';
        const tone = load.imbalancePct > 20 ? 'hw-dock-legs-bad'
            : load.imbalancePct > 10 ? 'hw-dock-legs-warn' : '';
        if (tone) row.classList.add(tone);
        const cap = document.createElement('span');
        cap.className = 'hw-dock-legs-cap';
        cap.textContent = 'LEGS';
        row.appendChild(cap);
        ['X', 'Y', 'Z'].forEach(k => {
            const amps = document.createElement('span');
            amps.textContent = `${k} ${load.legs[k].amps.toFixed(0)}A`;
            row.appendChild(amps);
            const bar = document.createElement('span');
            bar.className = 'hw-dock-legbar';
            const meat = document.createElement('i');
            if (load.legs[k].pct > 100) meat.className = 'hw-dock-bar-over';
            meat.style.width =
                `${Math.min(100, Math.round(load.legs[k].pct))}%`;
            bar.appendChild(meat);
            row.appendChild(bar);
        });
        const im = document.createElement('span');
        im.textContent = load.imbalancePct > 1
            ? `±${Math.round(load.imbalancePct)}%` : 'even';
        row.appendChild(im);
        return row;
    }

    // The slim OUTPUTS line under LEGS (user pick A, 2026-08-31): one plug
    // chip per connector type the distro offers, each a drag handle for
    // "one box of this type from this distro". The chips read as what
    // comes off this service, right where its legs are read. Absent when
    // the distro offers nothing - the whole-distro drag on the header and
    // the per-multi / per-circuit drags below stay either way; the plug
    // chip is a third handle, not a replacement.
    _dockDistroOutputsRow(d) {
        const types = this.distroOutputs(d);
        if (!types.length) return null;
        const row = document.createElement('div');
        row.className = 'hw-dock-outputs';
        const cap = document.createElement('span');
        cap.className = 'hw-dock-outputs-cap';
        cap.textContent = 'OUTPUTS';
        row.appendChild(cap);
        const name = d.name || d.id;
        types.forEach(t => {
            const chip = this._plugChip(t);
            chip.title = `${t.name} from ${name}. Drag onto a screen: the `
                + `next free multi on ${name} lands on the screen's next `
                + `unassigned circuits as a ${t.name} - the circuits it `
                + 'would feed light up under the cursor, and the box it '
                + 'makes wears the type. Refused, with the reason, when '
                + `the screen\'s breakout does not take a ${t.name}.`;
            this._dockWireDraggable(chip, {
                type: 'plug', distroId: d.id, output: t.id,
                title: `${name} · ${t.name}`,
            }, `plug-${d.id}-${t.id}`);
            row.appendChild(chip);
        });
        return row;
    }

    // One plug chip: the connector's face, its plain name, and (full size)
    // what it breaks out to. The same element rides the drag as the ghost.
    _plugChip(t, mini) {
        const el = document.createElement('span');
        el.className = 'hw-dock-plug' + (mini ? ' hw-dock-plug-mini' : '');
        el.appendChild(this.plugGlyph(t.glyph));
        const txt = document.createElement('span');
        txt.className = 'hw-dock-plug-t';
        const b = document.createElement('b');
        b.textContent = t.name;
        txt.appendChild(b);
        if (!mini) {
            const sub = document.createElement('small');
            sub.textContent = t.sub;
            txt.appendChild(sub);
        }
        el.appendChild(txt);
        return el;
    }

    // One multi as one bounded section: header = the whole-multi drag
    // handle (the old slot chip's payload and drop matrix, untouched), body
    // = six circuit chips in the port-chip register, each the tray's finest
    // drag ("power should look more like the data bars - i have to be able
    // to drag individual circuits, not just the whole multi").
    _dockBuildMulti(d, n, members) {
        const sec = document.createElement('div');
        sec.className = 'hw-dock-box hw-dock-multi';

        // Which circuit holds each tail, WITH the plan's own leg figures:
        // getSocaPlan is the one authority for a leg's tail, label and amps
        // (report table, breaker stickers and brackets all read it), so the
        // chips can never disagree with the paperwork. Circuit capacity is
        // the owner screen's amps-per-circuit figure - the same
        // powerAmperage the plan's own circuits were sized against.
        const byTail = new Map();   // tail 1..size -> [{who, label, amps, capA}]
        const memberRecs = [];      // {layer, m, s} - the header's inline fields
        let legs = 0;
        let boxAmps = 0;
        let capA = 0;               // smallest member figure: the honest bound
        // The box IS a connector type (distroBoxType, the one resolver):
        // stored on the distro by its chip or by the drop that made the
        // box, else read off its occupants' breakout (the smallest member
        // figure when they disagree, matching _resolveSharedSocas), else
        // the first type the distro offers. Its fan and its feed rating
        // follow the type exactly - six circuits on a soca, three on an
        // L21-30 at 30 A per leg - so a spare box typed L21-30 wears three
        // chips before anything lands on it.
        const typeInfo = this.distroBoxType(d, n, members);
        const boxType = typeInfo.type;
        const boxSize = boxType.boxSize;
        const feedLegA = boxType.feedLegA || 0;   // L21-30: per-leg rating
        members.forEach(m => {
            const l = (this.project.layers || []).find(x => x.id === m.layerId);
            if (!l) return;
            const s = this.getSocaPlan(l).find(x => x.soca === m.soca);
            memberRecs.push({ layer: l, m, s });
            if (s) {
                const a = parseFloat(l.powerAmperage) || 0;
                if (a > 0) capA = capA > 0 ? Math.min(capA, a) : a;
                s.legs.forEach(leg => {
                    const list = byTail.get(leg.leg) || [];
                    list.push({ who: l.name, layerId: l.id,
                                circuit: leg.circuit, label: leg.label,
                                amps: leg.amps, capA: a });
                    byTail.set(leg.leg, list);
                });
                boxAmps += s.amps;
            }
            legs += m.legs || 0;
        });
        const free = Array.from({ length: boxSize }, (_, i) => i + 1)
            .filter(t => !byTail.has(t));
        const tailClash = [...byTail.values()].some(h => h.length > 1);
        const overflow = legs > boxSize;
        if (overflow || tailClash) sec.classList.add('hw-dock-multi-clash');
        // The box's problems are strip questions too - the same states the
        // chips wear, said where a glance lands first.
        const boxName = `${d.name || d.id} ${n}`;
        if (overflow) {
            this._dockPowerWarnings.push({
                text: `${boxName} — more circuits than the `
                    + `${boxSize === 3 ? 'three' : 'six'} the box holds.`,
            });
        }
        // A stored type that contradicts what is on the box - the screen's
        // breakout changed under a typed box, or the numbers shifted - is
        // said, never silently overridden: the stored type is paperwork.
        // The fix offered is the one the read-only chip cannot make.
        if (typeInfo.clash) {
            sec.classList.add('hw-dock-multi-clash');
            this._dockPowerWarnings.push({
                text: `${boxName} is typed ${boxType.name} but holds `
                    + `${typeInfo.implied.name} circuits.`,
                offer: {
                    label: `Make it ${typeInfo.implied.name}`,
                    title: `Retype ${boxName} to follow its circuits. `
                        + 'One undoable step.',
                    run: () => {
                        this.setDistroBoxType(d.id, n, typeInfo.implied.id);
                        this.renderHardwareDock();
                    },
                },
            });
        }
        // An L21-30 box's feed is rated per leg (30 A), and the box's
        // circuits load the feed legs as phasors - the same maths the
        // distro's own LEGS line runs, scoped to this one feed. Over is a
        // strip question and reddens the box like any other clash.
        let feedOver = false;
        if (feedLegA > 0 && memberRecs.length
                && typeof this.boxFeedLegAmps === 'function') {
            const fl = this.boxFeedLegAmps(d, memberRecs.filter(r => r.s));
            const worst = Math.max(fl.X, fl.Y, fl.Z);
            if (worst > feedLegA) {
                feedOver = true;
                sec.classList.add('hw-dock-multi-clash');
                this._dockPowerWarnings.push({
                    text: `${boxName} — feed leg at ${worst.toFixed(1)} A `
                        + `of ${feedLegA} A — OVER`,
                });
            }
        }
        byTail.forEach((list, t) => {
            if (list.length > 1) {
                this._dockPowerWarnings.push({
                    text: `${boxName} circuit ${t} is claimed twice (`
                        + `${list.map(h => `${h.who} ${h.label}`).join(' + ')}`
                        + ').',
                });
            }
        });

        const tip = `${d.name || d.id} multi ${n} - `
            + (members.length
                ? `${members.map(m => m.layerName).join(' and ')}, `
                    + (free.length
                        ? `circuits ${this._fmtTails(free)} free`
                        : 'no circuits free')
                : 'free')
            + (feedLegA > 0
                ? `. L21-30 feed, ${feedLegA} A per leg` : '')
            + (overflow ? `. OVERFLOW - more circuits than the `
                + `${boxSize === 3 ? 'three' : 'six'} the box holds` : '')
            + '. Drag onto a circuit to land that circuit\'s multi here - '
            + 'the first circuit takes the whole multi, a later circuit '
            + 'splits it there and this box takes the rest'
            + (members.length
                ? '; drag back onto this tray to unassign it.' : '.');
        // A box with nothing on it drags AS ITS PLUG (2026-09-05: "when a
        // new Multi/group of circuits is where the port type should be
        // moved to"): the payload carries the type, and the drop resolves
        // through the plug gate - the same compatibility rule, refusal
        // and pill the OUTPUTS row's chips get - before the anchored-span
        // take decides which circuits. An occupied box carries no type on
        // its payload: its drop is the join/move it always was.
        const payload = {
            type: 'slot', distroId: d.id, number: n,
            title: `${d.name || d.id} ${n}`,
        };
        if (!members.length) payload.output = boxType.id;
        const head = this._dockBuildHandle(
            payload,
            `slot-${d.id}-${n}`,
            memberRecs.length ? '' : `${d.name || d.id} ${n}`,
            memberRecs.length
                ? `${legs} circuit${legs === 1 ? '' : 's'} · `
                    + `${boxAmps.toFixed(1)} A`
                : 'free',
            tip,
            // The folded glance: tails used and the box's whole-fan load
            // against its circuits' capacity - red on overflow, a
            // twice-claimed tail or an over-rated L21-30 feed leg, the
            // same states the chips wear.
            {
                frac: capA > 0 ? boxAmps / (capA * boxSize) : 0,
                over: overflow || tailClash || feedOver
                    || (capA > 0 && boxAmps > capA * boxSize),
                text: `${boxSize - free.length}/${boxSize}`,
            });
        // An occupied box's header carries its NAME and home-run LENGTH
        // inline - the fields the retired soca tiles held, on the box they
        // describe. ONE pair regardless of member count (2026-08-30, user
        // screenshot of "SR1 [100ft] SR1 [100ft] SR1 [100ft]": a multi
        // shared by N screens is ONE physical box with ONE home run, so N
        // identical pairs were N-1 too many). The fields show the FIRST
        // member's stored values and every commit writes through to ALL
        // members as one undo entry, so disagreeing legacy values converge
        // on the first edit. Keys stay the first member's, so focus-restore
        // and the key-based lookups keep a stable anchor; the other
        // members' field keys simply no longer exist in the DOM.
        // The name's placeholder is the derived name (following the
        // distro), so an unnamed box still reads as its identity; typed
        // text stops following. The fields live on a LINE of their own
        // under the glance line (density pass, 2026-08-30) - still inside
        // the header, so the fold and the drag keep their scope.
        // The TYPE CHIP rides every box header after the name (user pick,
        // 2026-09-05: "Type chip on the spare box" - "or both places
        // rather", so the OUTPUTS row stays as the second way). On a box
        // with nothing on it the chip is the picker; on an occupied box it
        // reads what the occupants make it.
        const typeChip = this._dockBuildTypeChip(d, n, typeInfo,
                                                 !members.length);
        if (!memberRecs.length) {
            const label = head.querySelector('.hw-dock-unit-name');
            head.insertBefore(typeChip, label ? label.nextSibling : null);
        }
        if (memberRecs.length) {
            const namesRow = document.createElement('span');
            namesRow.className = 'hw-dock-names';
            const first = memberRecs[0];
            const writeThrough = (setter, action, val) => {
                memberRecs.forEach(({ layer, m }) => {
                    setter.call(this, layer, m.soca, val, false);
                });
                this.updateLayers(memberRecs.map(r => r.layer), true, action);
            };
            const nameField = this._dockHeadName({
                value: (first.layer.powerSocaNames || {})[first.m.soca],
                placeholder: (first.s && first.s.name)
                    || `${d.name || d.id} ${n}`,
                key: `power-soca-name-${first.layer.id}-${first.m.soca}`,
                title: 'Name this multi by hand - all screens sharing the '
                    + 'box follow. Left blank it follows its distro - '
                    + 'multis on a distro named SL are SL1, SL2 - so '
                    + 'renaming the distro renames them all.',
                onCommit: (val) => {
                    writeThrough(this.setSocaName, 'Rename Multi', val);
                    this._restateNaming();
                },
            });
            namesRow.appendChild(nameField);
            namesRow.appendChild(typeChip);
            const len = this._dockHeadName({
                value: (first.layer.powerSocaLengths || {})[first.m.soca]
                    || (first.s && first.s.length) || '',
                placeholder: '100ft',
                key: `power-soca-length-${first.layer.id}-${first.m.soca}`,
                title: 'The box\'s home-run length - one run for every '
                    + 'screen sharing it. It flows into the gear checklist '
                    + 'and report.',
                onCommit: (val) => {
                    writeThrough(this.setSocaLength,
                                 'Set Multi Home Run', val);
                },
            });
            len.classList.add('hw-dock-name-len');
            namesRow.appendChild(len);
            head.appendChild(namesRow);
        }
        sec.appendChild(head);
        const body = this._dockSectionBody(sec, head,
                                           `hwdock-multi-${d.id}-${n}`);
        const grid = document.createElement('div');
        grid.className = 'lrd-tile-grid hw-dock-grid';
        for (let t = 1; t <= boxSize; t++) {
            grid.appendChild(this._dockBuildCircuitChip(
                d, n, t, byTail.get(t) || []));
        }
        body.appendChild(grid);
        return sec;
    }

    // The box's type chip: the connector's face and plain name in the
    // plug chips' machined-tab register. `editable` (a box with no
    // members) makes it a button whose click cycles through the types the
    // distro offers - the same list the OUTPUTS row shows - and stores the
    // pick as ONE 'Set Multi Type' entry; a button, so the header's drag
    // guard treats the press as the chip's gesture, not a pickup. An
    // occupied box's chip is a plain span: the type follows what is on
    // the box and changes by clearing it. Keyed as a field so focus
    // survives the tray's rebuild after the click.
    _dockBuildTypeChip(d, n, info, editable) {
        const t = info.type;
        const el = document.createElement(editable ? 'button' : 'span');
        if (editable) el.type = 'button';
        el.className = 'hw-dock-typechip'
            + (editable ? '' : ' hw-dock-typechip-ro')
            + (info.clash ? ' hw-dock-typechip-clash' : '');
        el.dataset.lrdField = `distro-box-type-${d.id}-${n}`;
        el.appendChild(this.plugGlyph(t.glyph));
        const name = document.createElement('b');
        name.textContent = t.name;
        el.appendChild(name);
        const boxName = `${d.name || d.id} ${n}`;
        if (editable) {
            const offered = this.distroOutputs(d);
            const list = offered.length ? offered : this.getDistroOutputTypes();
            el.title = `${boxName} is a ${t.name} box. Click to cycle - `
                + `${list.map(x => x.name).join(' → ')}. Drag the box onto `
                + `a circuit and it lands as a ${t.name}; refused, with the `
                + 'reason, when the screen\'s breakout does not take one.';
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                const i = list.findIndex(x => x.id === t.id);
                const next = list[(i + 1) % list.length];
                this.setDistroBoxType(d.id, n, next.id);
                this.renderHardwareDock();
            });
        } else {
            el.title = info.clash
                ? `${boxName} is typed ${t.name} but holds `
                    + `${info.implied.name} circuits - the strip offers the `
                    + 'fix.'
                : `${boxName} is a ${t.name} box - the type follows what `
                    + 'is on it. Clear the box to change it.';
        }
        return el;
    }

    // One tail of the fan as one chip of its multi's grid, the data port
    // chip's register: tail number, the derived circuit label, the occupant
    // screen, the occupied/clash grounds - and the chip is the drag that
    // puts ONE circuit on THIS tail (the old pip's payload and semantics,
    // now on a chip a hand can find).
    _dockBuildCircuitChip(d, n, t, holders) {
        const tile = document.createElement('div');
        tile.className = 'lrd-tile hw-dock-tile';
        if (holders.length > 1) tile.classList.add('lrd-tile-clash');
        else if (holders.length) tile.classList.add('lrd-tile-occupied');

        const face = document.createElement('div');
        face.className = 'lrd-tile-face';
        const top = document.createElement('div');
        top.className = 'lrd-tile-line';
        const num = document.createElement('span');
        num.style.color = 'var(--ps-faint, #969696)';
        num.textContent = String(t);
        top.appendChild(num);
        if (holders.length) {
            const label = document.createElement('span');
            label.style.color = 'var(--ps-text, #f0f0f0)';
            top.appendChild(document.createTextNode(' '));
            label.textContent = holders.map(h => h.label).join(' / ');
            top.appendChild(label);
        }
        face.appendChild(top);
        const who = document.createElement('div');
        who.className = 'lrd-tile-line';
        if (!holders.length) {
            who.style.color = '#6a6a6a';
            who.textContent = 'free';
        } else if (holders.length > 1) {
            who.style.color = '#d05a52';
            who.textContent = 'clash';
        } else {
            who.style.color = 'var(--ps-dim, #c0c0c0)';
            who.textContent = holders[0].who;
        }
        face.appendChild(who);
        tile.appendChild(face);

        face.title = `Circuit ${t} - ` + (holders.length
            ? holders.map(h => `${h.who} ${h.label}`).join(', ')
                + (holders.length > 1 ? ' (claimed twice)' : '')
            : 'free')
            + '. Drag onto a circuit to land that ONE circuit here'
            + (holders.length
                ? '; drag back onto this tray to clear it; click to edit '
                    + 'its label.'
                : '.');

        // An occupied chip is the circuit's editor too, the port chips'
        // grammar: click (no movement) opens the label override in place -
        // the row the retired Circuit Labels list provided, now on the
        // chip it names. A free tail has no circuit to label, so it stays
        // a plain drag handle (_wireTiles skips editor-less tiles).
        if (holders.length) {
            tile.dataset.lrdTile = `ptail-${d.id}-${n}-${t}`;
            tile.dataset.lrdTileBox = `multi-${d.id}-${n}`;
            const editor = document.createElement('div');
            editor.className = 'lrd-tile-body';
            holders.forEach(h => {
                editor.appendChild(this._buildCircuitLabelField(h));
            });
            tile.appendChild(editor);
            if (this._tileOpenId(tile.dataset.lrdTileBox)
                    === tile.dataset.lrdTile) {
                tile.classList.add('lrd-tile-open');
            }
        }

        // The circuit's load against its capacity, the plan's own leg
        // figures (amps) over the owner screen's amps-per-circuit. A tail
        // two stored sets claim carries both loads against the smaller
        // figure - the honest reading of one breaker asked twice.
        if (holders.length) {
            const amps = holders.reduce((s, h) => s + h.amps, 0);
            const cap = holders.reduce(
                (s, h) => h.capA > 0 ? (s > 0 ? Math.min(s, h.capA) : h.capA)
                    : s, 0);
            this._dockChipFill(face, cap > 0
                ? { frac: amps / cap, over: amps > cap,
                    note: ` · ${amps.toFixed(1)} A / ${+cap.toFixed(1)} A` }
                : { unknown: true });
        } else {
            this._dockChipFill(face, { frac: 0, over: false });
        }

        this._dockWireDraggable(face, {
            type: 'tail', distroId: d.id, number: n, tail: t,
            title: `${d.name || d.id} ${n} circuit ${t}`,
        }, `tail-${d.id}-${n}-${t}`);
        return tile;
    }

    // One holder's label override, in the port-name-field register: the
    // derived label is the placeholder, typed text beats it for this
    // circuit only. Writes the HOLDER's layer - the chip is unambiguous
    // about whose circuit it is, unlike the retired list, which wrote every
    // selected screen. Same override store, same history action.
    _buildCircuitLabelField(h) {
        const layer = (this.project.layers || [])
            .find(l => l.id === h.layerId);
        const override = (layer && layer.powerLabelOverrides
            && layer.powerLabelOverrides[h.circuit]) || '';
        return this._buildPortNameField(
            'Label', `power-label-${h.layerId}-${h.circuit}`,
            override, h.label, !!override,
            {
                named: 'Named by hand. Clear the box to go back to the '
                    + 'name derived from the multi.',
                unnamed: 'Name this circuit. It beats the derived label '
                    + 'for this circuit only.',
            },
            (val) => {
                if (!layer) return;
                if (!layer.powerLabelOverrides) {
                    layer.powerLabelOverrides = {};
                }
                if (val) layer.powerLabelOverrides[h.circuit] = val;
                else delete layer.powerLabelOverrides[h.circuit];
                this.saveClientSideProperties();
                this.updateLayers([layer]);
                if (window.canvasRenderer) window.canvasRenderer.render();
                this.saveState('Edit Circuit Label');
                // The chip face prints the label it just changed; the
                // rebuild waits a macrotask so the Tab this change rode
                // lands on a real element first (_rebuildAfterGesture's
                // rule).
                this._rebuildAfterGesture(() => this.renderHardwareDock());
            });
    }

    // ── the chips' load fill ──────────────────────────────────────────────
    //
    // Every dock chip wears its load twice, the user's pick of the rendered
    // options: the chip's ground fills left-to-right like a meter (visible
    // from across the room) AND a crisp bar row sits along the chip's
    // bottom (the distro cards' rack-bar, miniaturized), with the exact
    // figure on the hover title. The ground fill is a translucent layer
    // INSIDE the face, above the tile's occupied/clash ground but below the
    // text - it tints the state colour rather than replacing it, so an
    // occupied chip stays readably lit and a clash stays readably red with
    // the meter riding on top. Over-capacity turns both layers red.

    // `info` is null for "draw nothing", { unknown: true } for a chip whose
    // capacity has no figure (NO bar rather than a lying one - the hover
    // says so), else { frac, over, note }. A free chip passes frac 0: the
    // empty track renders, the ground stays untouched.
    _dockChipFill(face, info) {
        if (!info) return;
        if (info.unknown) {
            face.title += ' · load not scored - no capacity figure to '
                + 'measure against';
            return;
        }
        const w = `${Math.min(Math.max(info.frac, 0), 1) * 100}%`;
        if (info.frac > 0) {
            const ground = document.createElement('div');
            ground.className = 'hw-dock-fill'
                + (info.over ? ' hw-dock-fill-over' : '');
            ground.style.width = w;
            face.insertBefore(ground, face.firstChild);
        }
        const bar = document.createElement('div');
        bar.className = 'hw-dock-bar';
        const meat = document.createElement('i');
        if (info.over) meat.className = 'hw-dock-bar-over';
        meat.style.width = w;
        bar.appendChild(meat);
        face.appendChild(bar);
        if (info.note) face.title += info.note;
    }

    // A data port chip's load, scored by THE authority the canvas badge
    // uses: canvasRenderer.getPortLoadStats. The dock only gathers the same
    // panels the badge scores (the drawn run, claimant by claimant) and
    // never re-derives capacity arithmetic of its own. Two claimants on one
    // socket (a clash) sum their loads against the smaller capacity - one
    // physical socket cannot carry more because two screens ask.
    _dockPortFill(cardId, number) {
        const r = window.canvasRenderer;
        if (!r || typeof r.getPortLoadStats !== 'function') return null;
        const occupants = this._portOccupants(cardId, number);
        if (!occupants.length) return { frac: 0, over: false };
        let load = 0;
        let capacity = Infinity;
        let any = false;
        for (const o of occupants) {
            const layer = (this.project.layers || [])
                .find(l => String(l.id) === String(o.layerId));
            if (!layer) continue;
            const stats = r.getPortLoadStats(
                layer, this._dockRunPanels(layer, o.number));
            // One claimant without a capacity figure poisons the whole
            // reading: a bar built from the rest would understate.
            if (!stats) return { unknown: true };
            load += stats.load;
            capacity = Math.min(capacity, stats.capacity);
            any = true;
        }
        if (!any || !Number.isFinite(capacity) || !(capacity > 0)) {
            return { unknown: true };
        }
        const over = load > capacity;
        // The badge's own clamp: a port that fits never prints past 100, an
        // over one never prints under 101 - digits and colour always agree.
        const pct = over
            ? Math.max(101, Math.round((load / capacity) * 100))
            : Math.min(100, Math.round((load / capacity) * 100));
        return {
            frac: load / capacity, over,
            note: ` · ${pct}% · ${this._dockFmtPx(load)} / `
                + `${this._dockFmtPx(capacity)} px`,
        };
    }

    _dockFmtPx(n) {
        return n >= 10000 ? `${Math.round(n / 1000)}k` : String(Math.round(n));
    }

    // The panels one drawn port run carries, gathered exactly the way
    // _dockBuildDataMap gathers them (calculatePortAssignments / the drawn
    // custom paths) - the same single implementation of "which panels ride
    // this port", filtered to one run. Cached per microtask because every
    // chip of a 40-port card asks during one render, and the assignment
    // walk is proportional to the wall.
    _dockRunPanels(layer, num) {
        if (!this._dockRunPanelsCache) {
            this._dockRunPanelsCache = new Map();
            Promise.resolve().then(() => {
                this._dockRunPanelsCache = null;
            });
        }
        let byPort = this._dockRunPanelsCache.get(layer);
        if (!byPort) {
            byPort = new Map();
            if ((layer.flowPattern || 'tl-h') === 'custom'
                    && layer.customPortPaths) {
                Object.keys(layer.customPortPaths).forEach(numStr => {
                    const n = parseInt(numStr, 10);
                    byPort.set(n, (layer.customPortPaths[numStr] || [])
                        .map(pos => (layer.panels || []).find(
                            p => p.row === pos.row && p.col === pos.col))
                        .filter(p => p && !p.hidden));
                });
            } else {
                const items =
                    typeof this.calculatePortAssignments === 'function'
                        ? this.calculatePortAssignments(layer) : [];
                items.forEach(it => {
                    if (!it || !it.panel || it.panel.hidden) return;
                    const arr = byPort.get(it.port) || [];
                    arr.push(it.panel);
                    byPort.set(it.port, arr);
                });
            }
            this._dockRunPanelsCache.set(layer, byPort);
        }
        return byPort.get(num) || [];
    }

    // A unit's title strip, which is also the unit's drag handle. The grip
    // glyph is the affordance the canvas-group rows already use. `glance`
    // adds the folded header's earn-its-keep readout: an optional compact
    // count/figure and a slim fill line, so a section folded away still
    // says how full it is.
    _dockBuildHandle(payload, key, name, detail, tip, glance) {
        const head = document.createElement('div');
        head.className = 'hw-dock-head-row';
        const grip = document.createElement('span');
        grip.className = 'hw-dock-grip';
        grip.textContent = '⋮⋮';
        head.appendChild(grip);
        // An empty name means the caller puts an inline name FIELD where
        // the static text would sit (_dockHeadAugment) - a label span with
        // nothing in it would still take its gap.
        if (name) {
            const label = document.createElement('span');
            label.className = 'hw-dock-unit-name';
            label.textContent = name;
            head.appendChild(label);
        }
        if (glance) {
            if (glance.text) {
                const use = document.createElement('span');
                use.className = 'hw-dock-unit-use';
                use.textContent = glance.text;
                head.appendChild(use);
            }
            const bar = document.createElement('span');
            bar.className = 'hw-dock-headbar';
            const meat = document.createElement('i');
            if (glance.over) meat.className = 'hw-dock-bar-over';
            meat.style.width =
                `${Math.min(Math.max(glance.frac || 0, 0), 1) * 100}%`;
            bar.appendChild(meat);
            head.appendChild(bar);
        }
        if (detail) {
            const info = document.createElement('span');
            info.className = 'hw-dock-unit-info';
            info.textContent = detail;
            head.appendChild(info);
        }
        head.title = tip;
        this._dockWireDraggable(head, payload, key);
        return head;
    }

    // ── the headers' live controls ───────────────────────────────────────
    //
    // The retired sidebars' per-thing editors, re-hosted onto the section
    // headers themselves: the NAME edits inline (the dashed underline says
    // "click to type"), a ⚙ opens the thing's configuration popover, and a
    // header can carry a control of its own (Balance, a length field). The
    // drag guard in _dockWireDraggable is what keeps a press on any of
    // these the control's gesture rather than a pickup.

    // A dashed inline name field for a dock header. The value is the hand
    // name; the placeholder is what the thing is called when unnamed, so an
    // empty field still reads as its identity - the ladder every naming
    // field in this app follows.
    _dockHeadName(opts) {
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'hw-dock-name';
        input.value = opts.value || '';
        input.placeholder = opts.placeholder || 'unnamed';
        if (opts.title) input.title = opts.title;
        input.dataset.lrdField = opts.key;
        // Sized to what it holds (placeholder included), so a header reads
        // as a line of text with an underline, not a text box with slack.
        const shown = (opts.value || opts.placeholder || 'unnamed');
        input.size = Math.min(18, Math.max(4, shown.length + 1));
        input.addEventListener('change',
                               () => opts.onCommit(input.value.trim()));
        return input;
    }

    // The read-only redundancy pill on a tray header - the user's pick of
    // option D's cheap half (2026-09-04, src/static/redundancy-mock.html):
    // "a read-only state pill on each header that opens the ⚙ to the
    // redundancy section, so the tray reports the state without growing
    // a second editing surface." It states the shape in force - on a
    // processor `R → H9 BACKUP` (whole unit), `R per card`, `R per port`;
    // on a card `R 1:1 → SL in H9 BACKUP`, `R seq`, `R halves`, `R
    // manual`, `R 1:1 — no partner` - and a click opens the PROCESSOR's
    // gear, where the bar that sets it lives (a card's pill too: the
    // card's own gear only restates the fact). Nothing while redundancy
    // is off. A unit consumed whole as another's backup wears its role
    // instead - "backs up X" - and a consumed card's header already
    // carries that in its name, so it gets no pill. Gold is the backup
    // role's family everywhere in the dock; a state colour never follows
    // the accent. A button, so the drag pickup skips it.
    _dockRedundancyPill(proc, card) {
        let text;
        // The consumed role is the MAIN's doing - its picks consume this
        // unit whatever this unit's own flag says - so it is read before
        // the flag, the way the consumed cards' own headers read theirs.
        const mainId = card ? null : this._backupUnitMainId(proc);
        if (mainId) {
            const main = (this._processorsResolved || [])
                .find(p => p.id === mainId);
            text = `backs up ${main
                ? (main.name || main.deviceName) : 'another processor'}`;
        } else if (!proc.redundancy || !proc.redundancySupported) {
            return null;
        } else if (card) {
            if (card.backupFor) return null;
            const shape = card.redundancyShape;
            if (!shape) return null;
            if (shape.mode === '1to1') {
                const found = card.backupCardId
                    ? this._otherCards(card.id)
                        .find(x => x.card.id === card.backupCardId)
                    : null;
                text = found
                    ? `R 1:1 → ${this._backupUnitTitle(found.proc, found.card)}`
                    : 'R 1:1 — no partner';
            } else {
                text = `R ${shape.mode === 'sequential' ? 'seq' : shape.mode}`;
            }
        } else {
            const level = this._procRedundancyLevel(proc);
            const procs = this._processorsResolved || [];
            if (level === 'off') return null;
            if (level === 'unit') {
                const partner = procs.find(
                    p => p.id === proc.backupProcessorId);
                if (partner) {
                    text = `R → ${partner.name || partner.deviceName}`;
                } else {
                    // A standalone unit at 1:1 with no partner picked yet:
                    // its one card's own reading.
                    const one = (proc.slots || []).map(s => s.card)
                        .find(Boolean);
                    const found = one && one.backupCardId
                        ? this._otherCards(one.id)
                            .find(x => x.card.id === one.backupCardId)
                        : null;
                    text = found
                        ? `R → ${this._backupUnitTitle(found.proc, found.card)}`
                        : 'R 1:1 — no partner';
                }
            } else if (level === 'fixed') {
                text = 'R on';
            } else {
                text = `R per ${level}`;
            }
        }
        const pill = document.createElement('button');
        pill.type = 'button';
        pill.className = 'hw-dock-redpill';
        pill.textContent = text;
        pill.title = `Redundancy: ${text}. Click to open the processor’s `
            + '⚙, where it is set.';
        pill.addEventListener('click', (e) => {
            e.stopPropagation();
            this._dockOpenProcGear(proc.id);
        });
        return pill;
    }

    // Open a processor's gear popover by the same path the gear itself
    // takes - a click on that gear - so placement, the focus machinery
    // and the click-away teardown all behave exactly as for the gear.
    // The document's mousedown has already closed whatever was open (the
    // pill is nobody's anchor), so the click always lands as an open.
    _dockOpenProcGear(procId) {
        const gear = document.querySelector(
            `[data-hwpop="${CSS.escape(`proc-${procId}`)}"]`);
        if (gear) gear.click();
    }

    // Grow a drag-handle header: the inline name field goes where the
    // static label would sit (before the glance readouts), extra controls
    // and the gear go on the end. `gear.build` is re-invoked on every
    // popover refresh, so it must read live state, never a closure snapshot
    // of stale data beyond the ids it needs.
    _dockHeadAugment(head, opts) {
        if (opts.name) {
            const before = head.querySelector(
                '.hw-dock-unit-use, .hw-dock-headbar, .hw-dock-unit-info');
            head.insertBefore(this._dockHeadName(opts.name), before || null);
        }
        (opts.controls || []).forEach(c => head.appendChild(c));
        if (opts.gear) {
            const btn = document.createElement('button');
            btn.className = 'hw-dock-gear';
            btn.textContent = '⚙';
            btn.title = opts.gear.title
                || 'Configure - templates, mode, redundancy, remove.';
            btn.dataset.hwpop = opts.gear.id;
            btn.dataset.lrdField = `hwgear-${opts.gear.id}`;
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this._hwPopoverToggle(btn, opts.gear.id, opts.gear.build);
            });
            head.appendChild(btn);
        }
        return head;
    }

    // ── the drag itself ───────────────────────────────────────────────────

    _dockWireDraggable(el, payload, key) {
        el.dataset.hwdock = key;
        // The payload rides on the element too, so a right-click can know
        // what chip it landed on (_prepareClearMenu reads it back) without
        // re-deriving card ids and spans from the key string.
        el.dataset.hwdockPayload = JSON.stringify(payload);
        // A real tab stop, like the panel tiles' faces: the dock must stay
        // reachable by keyboard even though the drag gesture itself has no
        // keyboard equivalent yet.
        el.tabIndex = 0;
        el.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            // The headers carry live controls now - the inline name field,
            // the gear, Balance - and a press on one is that control's
            // gesture, not a drag pickup: preventDefault here would eat the
            // click that focuses the input or opens the popover.
            if (e.target !== el && e.target.closest
                    && e.target.closest('input, select, button, textarea')) {
                return;
            }
            e.preventDefault();
            this._dockArmDrag(e, payload, el);
        });
    }

    _dockArmDrag(e, payload, el) {
        const startX = e.clientX;
        const startY = e.clientY;
        let live = false;
        const move = (ev) => {
            if (!live) {
                // A 4px threshold keeps a plain click from twitching into a
                // drag - same latitude every drag on the canvas gives. It is
                // also the whole click-vs-open split for the openable port
                // chips: press-and-move past 4px is the drag, press released
                // inside it is the click that opens the editor.
                if (Math.abs(ev.clientX - startX) < 4
                        && Math.abs(ev.clientY - startY) < 4) return;
                live = true;
                this._dockStartDrag(payload, el);
            }
            this._dockMoveDrag(ev);
        };
        // Escape mid-drag cancels: the chip goes home, no drop, nothing
        // said - the same way out every canvas gesture offers.
        const key = (ke) => {
            if (ke.key !== 'Escape') return;
            document.removeEventListener('mousemove', move);
            document.removeEventListener('mouseup', up);
            document.removeEventListener('keydown', key, true);
            if (live) {
                this._dockDropTarget = null;
                this._dockEndDrag(ke);
            }
        };
        const up = (ev) => {
            document.removeEventListener('mousemove', move);
            document.removeEventListener('mouseup', up);
            document.removeEventListener('keydown', key, true);
            if (live) {
                // A drag that ends back over its own chip still synthesizes
                // a click after mouseup, and on an openable port chip that
                // click would open the editor the drop never asked for.
                // Swallow exactly that one click - the guard lifts on the
                // next macrotask, after the browser has dispatched (or
                // skipped) the click for THIS gesture, so the next real
                // click opens as normal.
                const swallow = (ce) => {
                    ce.stopPropagation();
                    ce.preventDefault();
                };
                document.addEventListener('click', swallow, true);
                setTimeout(() => {
                    document.removeEventListener('click', swallow, true);
                }, 0);
                this._dockEndDrag(ev);
            }
        };
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
        document.addEventListener('keydown', key, true);
    }

    _dockStartDrag(payload, el) {
        this._dockDrag = {
            payload,
            // The data view's run geometry, frozen at pickup: which panel
            // belongs to which port of which screen. The power side reads
            // the renderer's own retained circuit maps live instead.
            dataMap: (window.canvasRenderer
                && window.canvasRenderer.viewMode === 'data-flow')
                ? this._dockBuildDataMap() : null,
        };
        this._dockDropTarget = null;
        const ghost = document.createElement('div');
        ghost.id = 'hw-dock-ghost';
        ghost.textContent = payload.title || payload.type;
        if (payload.type === 'plug'
                || (payload.type === 'slot' && payload.output)) {
            // The chip itself rides the cursor - the connector is the
            // thing being carried, so the ghost wears its face. A typed
            // spare box is that plug with a number on it.
            const t = this.getDistroOutputTypes()
                .find(x => x.id === payload.output);
            if (t) {
                ghost.textContent = '';
                ghost.classList.add('hw-dock-ghost-plug');
                const chip = this._plugChip(t, true);
                if (payload.type === 'slot') {
                    chip.querySelector('b').textContent =
                        `${payload.title} · ${t.name}`;
                }
                ghost.appendChild(chip);
            }
        }
        document.body.appendChild(ghost);
        this._dockDrag.ghost = ghost;
        document.body.style.cursor = 'grabbing';
        document.body.style.userSelect = 'none';
        if (el && el.classList) el.classList.add('hw-dock-dragging');
        this._dockDrag.source = el;
        sendClientLog('dock_drag_started', { payload });
    }

    _dockMoveDrag(ev) {
        const drag = this._dockDrag;
        if (!drag) return;
        drag.ghost.style.left = `${ev.clientX + 14}px`;
        drag.ghost.style.top = `${ev.clientY + 10}px`;
        const target = this._dockHitTest(ev, drag);
        const changed = JSON.stringify(target)
            !== JSON.stringify(this._dockDropTarget);
        this._dockDropTarget = target;
        const dock = document.getElementById('hardware-dock');
        if (dock) {
            dock.classList.toggle('hw-dock-drop-target',
                !!(target && target.kind === 'dock'));
        }
        if (drag.payload.type === 'plug' || drag.payload.output) {
            this._dockPlugPill(drag, ev, target);
        }
        if (changed && window.canvasRenderer) {
            // One paint per target change, not per mousemove: the highlight
            // only moves when the run under the cursor does.
            window.canvasRenderer.render();
        }
    }

    _dockEndDrag(ev) {
        const drag = this._dockDrag;
        const target = this._dockDropTarget;
        this._dockDrag = null;
        this._dockDropTarget = null;
        if (drag) {
            if (drag.ghost) drag.ghost.remove();
            if (drag.pill) drag.pill.remove();
            if (drag.source && drag.source.classList) {
                drag.source.classList.remove('hw-dock-dragging');
            }
        }
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        const dock = document.getElementById('hardware-dock');
        if (dock) dock.classList.remove('hw-dock-drop-target');
        if (window.canvasRenderer) window.canvasRenderer.render();
        if (drag && target) this._dockPerformDrop(drag.payload, target);
    }

    // What is under the cursor, in the drop matrix's terms. Returns one of
    //   { kind: 'dock' }
    //   { kind: 'run', layerId, num, socaIndex? }   (single-item drags)
    //   { kind: 'screen', layerId }                 (whole-unit drags)
    // or null. Whole-unit drags land screen-wide by design, so a panel hit
    // normalizes to its owner screen for them.
    _dockHitTest(ev, drag) {
        const dock = document.getElementById('hardware-dock');
        if (dock && !dock.classList.contains('view-hidden')) {
            const r = dock.getBoundingClientRect();
            if (ev.clientX >= r.left && ev.clientX <= r.right
                    && ev.clientY >= r.top && ev.clientY <= r.bottom) {
                const t = drag.payload.type;
                return (t === 'port' || t === 'slot' || t === 'tail')
                    ? { kind: 'dock' } : null;
            }
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas) return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (ev.clientX < rect.left || ev.clientX > rect.right
                || ev.clientY < rect.top || ev.clientY > rect.bottom) {
            return null;
        }
        // The same client-to-world walk every canvas gesture does, mirror
        // included - a drop in the mirrored rear view must land on the panel
        // the cursor is over, not its reflection.
        const worldY = ((ev.clientY - rect.top) - renderer.panY)
            / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(
            ((ev.clientX - rect.left) - renderer.panX) / renderer.zoom,
            worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        const whole = drag.payload.type !== 'port'
            && drag.payload.type !== 'slot'
            && drag.payload.type !== 'tail';

        if (renderer.viewMode === 'data-flow') {
            if (hit && drag.dataMap && drag.dataMap.has(hit.panel)) {
                const run = drag.dataMap.get(hit.panel);
                return whole
                    ? { kind: 'screen', layerId: run.ownerId }
                    : { kind: 'run', layerId: run.ownerId, num: run.portNum };
            }
            if (whole) {
                // Any layer under the cursor is a target, screen or not: the
                // drop matrix refuses non-screens with a reason, which tells
                // the user more than a drop that silently does nothing.
                const layer = renderer.getLayerAt(worldX, worldY);
                if (layer) return { kind: 'screen', layerId: layer.id };
            }
            return null;
        }
        if (renderer.viewMode === 'power') {
            if (hit) {
                const layer = (this.project.layers || [])
                    .find(l => l.id === hit.layerId);
                const circuit = layer
                    ? renderer._powerCircuitForPanel(layer, hit.panel) : null;
                if (circuit) {
                    if (whole) {
                        return this._dockScreenTarget(circuit.owner, drag);
                    }
                    const slot = this._powerNaming(circuit.owner)
                        .slots.get(circuit.circuitNum);
                    if (slot) {
                        const target = {
                            kind: 'run', layerId: circuit.owner.id,
                            num: circuit.circuitNum, socaIndex: slot.multi,
                        };
                        // The drop's true reach rides on the target so the
                        // underlay can light everything the release will
                        // touch - the data tab's rule, where a port drop
                        // lights exactly the run it takes. A slot takes
                        // the box cell's circuits from its FIRST up to
                        // the hovered one, as many as the box has room
                        // for (user, 2026-09-05: "start at the 1st
                        // circuit regardless of naming. should just be
                        // in order") - the drop's own resolution
                        // (_socaTakePlan), so what lights is what lands,
                        // and nothing where the drop would refuse; a tail
                        // pip takes the hovered circuit alone.
                        if (drag.payload.type === 'slot'
                                && drag.payload.output) {
                            // A typed spare box: the plug gate first (a
                            // mismatch lights nothing and reddens the
                            // pill with the fix), then the same anchored
                            // take - the drop's own resolution.
                            const ordinal = this.screenCircuits(circuit.owner)
                                .findIndex(c => c.num === circuit.circuitNum)
                                + 1;
                            const plan = this._boxPlanFor(
                                drag, circuit.owner, ordinal);
                            target.nums = plan.ok ? plan.nums.slice() : [];
                            target.plug = plan.ok
                                ? { ok: true, socaIndex: plan.socaIndex,
                                    number: plan.number,
                                    boxName: plan.boxName, badge: plan.badge,
                                    glyph: plan.glyph, text: plan.text,
                                    warn: plan.warn }
                                : { ok: false, glyph: plan.glyph,
                                    message: plan.message };
                        } else if (drag.payload.type === 'slot') {
                            const ordinal = this.screenCircuits(circuit.owner)
                                .findIndex(c => c.num === circuit.circuitNum)
                                + 1;
                            const plan = this._socaTakePlan(
                                circuit.owner, ordinal,
                                drag.payload.distroId, drag.payload.number);
                            target.nums = plan.ok ? plan.nums.slice() : [];
                        } else if (drag.payload.type === 'tail') {
                            target.nums = [circuit.circuitNum];
                        }
                        return target;
                    }
                }
            }
            if (whole) {
                // Any layer under the cursor is a target, screen or not: the
                // drop matrix refuses non-screens with a reason, which tells
                // the user more than a drop that silently does nothing.
                const layer = renderer.getLayerAt(worldX, worldY);
                if (layer) return this._dockScreenTarget(layer, drag);
            }
            return null;
        }
        return null;
    }

    // A screen-wide power target, carrying the drop's true reach for a
    // DISTRO drag: the release feeds only the screen's unassigned multis,
    // so those multis' circuits are what the preview lights - a screen with
    // nothing unassigned lights nothing, which is exactly what the drop
    // would do. Every other whole-unit drag really is screen-wide and
    // carries no `nums`.
    _dockScreenTarget(layer, drag) {
        const target = { kind: 'screen', layerId: layer.id };
        if (drag.payload.type === 'distro'
                && (layer.type || 'screen') === 'screen') {
            target.nums = this.getSocaPlan(layer)
                .filter(s => !s.distroId)
                .flatMap(s => s.legs.map(g => g.circuit));
        }
        if (drag.payload.type === 'plug') {
            // A plug lights EXACTLY the circuits its drop would feed - the
            // drop's own resolution, read once per screen per drag - and
            // nothing at all where the drop would be refused. The pill and
            // the pending bracket read the same record off the target.
            const plan = this._plugPlanFor(drag, layer);
            target.nums = plan.ok ? plan.nums.slice() : [];
            target.plug = plan.ok
                ? { ok: true, socaIndex: plan.socaIndex, number: plan.number,
                    boxName: plan.boxName, badge: plan.badge,
                    glyph: plan.glyph, text: plan.text, warn: plan.warn }
                : { ok: false, glyph: plan.glyph, message: plan.message };
        }
        return target;
    }

    // ── plug drops: one box of one connector type ─────────────────────────
    //
    // The ONE resolution both the preview and the release read, so what
    // lights under the cursor is exactly what the drop assigns (user
    // ruling, 2026-08-31: preview == result). The box is the screen's next
    // unassigned multi in plan order - the split-aware segmentation, so a
    // split-off remainder is its own next box - and its number is what the
    // distro's own sequence would deal it, found by asking the naming
    // index with the assignment tried on (and taken straight back off).
    // Returns
    //   { ok: true, socaIndex, nums, number, boxName, amps, text, badge,
    //     glyph, warn }             - warn: the LEGS-past-rating sentence
    //   { ok: false, message, glyph }
    _plugDropPlan(payload, layer) {
        const gate = this._plugGate(payload, layer);
        if (!gate.ok) return gate;
        const { d, type, glyph } = gate;
        const plan = this.getSocaPlan(layer);
        const s = plan.find(x => !x.distroId);
        if (!s) {
            return { ok: false, glyph,
                     message: plan.length
                        ? `Every multi on ${layer.name} already has a `
                            + 'distro. Drag a slot onto a circuit to move '
                            + 'one, or drag it back onto the tray to '
                            + 'unassign it.'
                        : `${layer.name} has no circuits to feed.` };
        }
        // Dry run: the number this box would get, and where the distro's
        // legs would land with it on - read off the real naming index and
        // the real roll-up with the assignment tried on, then put back
        // exactly as found. The cache is dropped on both sides so no
        // frame reads the trial.
        const map = layer.powerSocaDistro || (layer.powerSocaDistro = {});
        const had = Object.prototype.hasOwnProperty.call(map, s.soca);
        const prev = map[s.soca];
        map[s.soca] = d.id;
        this._circuitTailCache = null;
        let number = null;
        let name = null;
        let warn = null;
        try {
            const rec = this._powerNaming(layer).socas.get(s.soca);
            number = rec ? rec.number : null;
            // The box's name as the wall will print it (the naming index's
            // own derivation - "PD1" - or a hand name), so the pending
            // bracket and the committed one read the same.
            name = rec ? rec.name : null;
            const load = (this.getDistroLoads() || [])
                .find(l => l.id === d.id);
            if (load && load.ratingA > 0) {
                if (load.legs) {
                    const worst = Math.max(load.legs.X.amps, load.legs.Y.amps,
                                           load.legs.Z.amps);
                    if (worst > load.ratingA) {
                        warn = `${d.name || d.id} legs to `
                            + `${worst.toFixed(0)} A of ${load.ratingA} A`;
                    }
                } else if (load.amps > load.ratingA) {
                    warn = `${d.name || d.id} to ${load.amps.toFixed(0)} A `
                        + `of ${load.ratingA} A`;
                }
            }
        } finally {
            if (had) map[s.soca] = prev; else delete map[s.soca];
            this._circuitTailCache = null;
        }
        const nums = s.legs.map(g => g.circuit);
        const boxName = name
            || `${d.name || d.id}${number != null ? ` ${number}` : ''}`;
        return {
            ok: true, glyph, socaIndex: s.soca, nums, number, boxName,
            amps: s.amps, badge: type.badge, warn,
            text: `${boxName} → circuit${nums.length === 1 ? '' : 's'} `
                + `${this._fmtTails(nums).replace(/-/g, '–')} · `
                + `${Math.round(s.amps)} A`,
        };
    }

    // The gate every plug-shaped drop passes first - the OUTPUTS chip and
    // the typed spare box alike (ONE rule, so preview == drop for both):
    // the output and distro still exist, the layer draws power, and the
    // connector matches the screen's effective breakout. The screen
    // always has one (getPowerBreakout defaults a 110V screen to Edison,
    // everything else to True1), so the match is always against something
    // real; a mismatch names the screen and the fix and never re-types
    // the screen. Returns { ok: true, d, type, glyph } or the refusal
    // { ok: false, glyph, message }.
    _plugGate(payload, layer) {
        const d = this.getDistros().find(x => x.id === payload.distroId);
        const type = this.getDistroOutputTypes()
            .find(t => t.id === payload.output);
        const glyph = type ? type.glyph : 'soca';
        if (!d || !type) {
            return { ok: false, glyph, message: 'That output no longer exists.' };
        }
        if (!layer || (layer.type || 'screen') !== 'screen') {
            return { ok: false, glyph,
                     message: `${(layer && layer.name) || 'That layer'} `
                        + 'draws no power.' };
        }
        const bt = this.getPowerBreakout(layer);
        if (!type.breakouts.includes(bt.id)) {
            return { ok: false, glyph,
                     message: `${layer.name} is set to `
                        + `${this._breakoutShortName(bt)} — change its `
                        + 'breakout first' };
        }
        return { ok: true, d, type, glyph };
    }

    // A typed spare box dropped on a specific circuit: the plug gate, then
    // the anchored take (_socaTakePlan, the 2026-09-05 rule - the box
    // takes its cell's circuits from the FIRST up to the dropped one, as
    // many as it has free). The pill and the underlay read this; the
    // release runs it again and takes exactly this. `socaIndex` names the
    // multi for the pending bracket only when the take is that whole
    // multi - a partial take has no committed shape to preview yet.
    // Returns the plug plan's shape: { ok, glyph, socaIndex, nums, number,
    // boxName, amps, badge, warn, text } or { ok: false, glyph, message }.
    _boxDropPlan(payload, layer, ordinal) {
        const gate = this._plugGate(payload, layer);
        if (!gate.ok) return gate;
        const { d, type, glyph } = gate;
        const plan = this._socaTakePlan(layer, ordinal, payload.distroId,
                                        payload.number);
        if (!plan.ok) {
            const c = this.screenCircuits(layer)[ordinal - 1];
            const label = c ? this.getPowerCircuitLabel(layer, c.num) : '';
            return { ok: false, glyph,
                     message: this._takeRefusalText(payload, plan, label) };
        }
        const nums = plan.nums;
        const amps = this.getSocaPlan(layer)
            .flatMap(s => s.legs)
            .filter(g => nums.includes(g.circuit))
            .reduce((t, g) => t + (g.amps || 0), 0);
        const boxName = `${d.name || d.id} ${plan.number}`;
        const whole = plan.seg && plan.spanStart === plan.seg.start
            && plan.spanEnd === plan.seg.end;
        return {
            ok: true, glyph, socaIndex: whole ? plan.seg.index : null,
            nums, number: plan.number, boxName, amps, badge: type.badge,
            warn: null,
            text: `${boxName} → circuit${nums.length === 1 ? '' : 's'} `
                + `${this._fmtTails(nums).replace(/-/g, '–')} · `
                + `${Math.round(amps)} A`,
        };
    }

    // The take's refusals in one voice, for the pill and the strip alike.
    _takeRefusalText(payload, r, label) {
        if (r.why === 'other-box') {
            // A circuit on another box is somebody's feed: the drop never
            // pulls it off. Clear it first.
            return `${label} is already on a box - clear it first; `
                + `${payload.title} never pulls a circuit off another box.`;
        }
        // The place-overflow refusal, in circuits: a box with no free
        // circuit takes nothing, and no cut happens for nothing.
        const len = r.tailLen != null ? r.tailLen : r.remaining;
        return `${payload.title} has no free circuits - the ${len} circuit`
            + `${len === 1 ? '' : 's'} up to ${label} stay where they are.`;
    }

    // The box plan per (screen, circuit), once per drag - the hit test
    // runs per mousemove and the state cannot change mid-drag.
    _boxPlanFor(drag, layer, ordinal) {
        if (!drag.plans) drag.plans = new Map();
        const key = `${layer.id}:${ordinal}`;
        if (!drag.plans.has(key)) {
            drag.plans.set(key, this._boxDropPlan(drag.payload, layer, ordinal));
        }
        return drag.plans.get(key);
    }

    // The plan for one screen, once per drag: the state cannot change
    // mid-drag, and the hit test runs per mousemove.
    _plugPlanFor(drag, layer) {
        if (!drag.plans) drag.plans = new Map();
        if (!drag.plans.has(layer.id)) {
            drag.plans.set(layer.id, this._plugDropPlan(drag.payload, layer));
        }
        return drag.plans.get(layer.id);
    }

    // The cursor pill of a plug drag: what the release will do ("SL 3 →
    // circuits 7–12 · 81 A"), amber when the box would push the distro's
    // legs past its rating (allowed, said), red with the reason where the
    // drop is refused. Hidden over nothing.
    _dockPlugPill(drag, ev, target) {
        let pill = drag.pill;
        if (!pill) {
            pill = document.createElement('div');
            pill.id = 'hw-dock-pill';
            document.body.appendChild(pill);
            drag.pill = pill;
        }
        const p = target && target.plug;
        if (!p) {
            pill.style.display = 'none';
            return;
        }
        const key = JSON.stringify(p);
        if (drag.pillKey !== key) {
            drag.pillKey = key;
            pill.innerHTML = '';
            pill.className = p.ok
                ? (p.warn ? 'hw-dock-pill-warn' : '') : 'hw-dock-pill-bad';
            pill.appendChild(this.plugGlyph(p.glyph));
            const t = document.createElement('span');
            t.textContent = p.ok
                ? p.text + (p.warn ? ` — ${p.warn}` : '') : p.message;
            pill.appendChild(t);
        }
        pill.style.display = '';
        const w = pill.offsetWidth;
        pill.style.left = `${Math.max(8, Math.min(ev.clientX + 16,
            window.innerWidth - w - 8))}px`;
        pill.style.top = `${Math.max(8, ev.clientY - 30)}px`;
    }

    // The release: the same resolution the preview showed, then the
    // existing setter, one 'Assign Multi Distro' entry - the distro drop's
    // own undo name, for one box instead of all of them. A refusal is said
    // on the strip and changes nothing.
    _dockDropPlug(payload, target) {
        if (!target || target.kind !== 'screen') return;
        const layer = (this.project.layers || [])
            .find(l => l.id === target.layerId);
        if (!layer) return;
        const plan = this._plugDropPlan(payload, layer);
        if (!plan.ok) {
            this._dockSay(plan.message);
            return;
        }
        // The box this makes wears the type it was dragged as - stamped
        // before the assignment's entry, so the gesture stays one step.
        if (plan.number != null) {
            this._stampBoxType(payload.distroId, plan.number, payload.output);
        }
        const touched = this.setSocaDistro(layer, plan.socaIndex,
                                           payload.distroId, false);
        this.updateLayers([...new Set(touched)], true, 'Assign Multi Distro');
        this._restateNaming();
        if (plan.warn) {
            this._dockSay(`${plan.boxName} landed on ${layer.name} — `
                + `${plan.warn}.`);
        }
    }

    // The click path (user pick C-as-submenu, 2026-08-31): right-click a
    // screen in the power view - its cabinets on the canvas, or its
    // circuit chips in the tray - and "Add <type> from…" lists every
    // distro: the ones offering the screen's connector with their load,
    // the rest greyed with the reason. Picking one is the plug drop,
    // verbatim - same resolution, same setter, same undo entry. The type
    // is the screen's own: its effective breakout decides what it can
    // take, so an L21-30 screen asks for an L21-30 and an Edison screen
    // for a Soca 120. A screen whose breakout no type names offers
    // nothing here, exactly as its drops would refuse.
    _prepareOutputsMenu(x, y) {
        const layer = this._outputsMenuLayer(x, y);
        if (!layer) return null;
        const distros = this.getDistros();
        if (!distros.length) return null;
        const type = this.outputTypeForBreakout(this.getPowerBreakout(layer));
        if (!type) return null;
        const loads = (typeof this.getDistroLoads === 'function'
            && this.getDistroLoads()) || [];
        const entries = distros.map(d => {
            const name = d.name || d.id;
            if (!this.distroOffers(d, type.id)) {
                return {
                    label: `${name} — does not offer ${type.name.toLowerCase()}`,
                    disabled: true,
                    title: `Tick ${type.name} under ${name}'s ⚙ Outputs to `
                        + 'offer it.',
                };
            }
            const load = loads.find(l => l.id === d.id);
            const fig = load && load.ratingA > 0
                ? ` ${load.amps.toFixed(0)}/${load.ratingA} A` : '';
            const payload = { type: 'plug', distroId: d.id, output: type.id,
                              title: `${name} · ${type.name}` };
            const plan = this._plugDropPlan(payload, layer);
            return {
                label: `${name}${fig}`,
                disabled: !plan.ok,
                title: plan.ok
                    ? `${plan.text}${plan.warn ? ` — ${plan.warn}` : ''}. `
                        + 'One undoable step.'
                    : plan.message,
                run: () => {
                    sendClientLog('dock_output_pick',
                                  { payload, layerId: layer.id });
                    this._dockDropPlug(payload,
                                       { kind: 'screen', layerId: layer.id });
                },
            };
        });
        return { label: `Add ${type.name} from…`, type: type.id, entries };
    }

    // The screen a right-click names, for the outputs submenu: a circuit
    // chip in the tray speaks for the screen holding that circuit; on the
    // canvas, in the power view, the circuit under the cursor names its
    // owner (a group peer's cabinet lands on the owner's run), and a
    // cabinet on no drawn circuit still names its screen.
    _outputsMenuLayer(x, y) {
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('[data-hwdock-payload]')) {
            const payload = this._dockChipPayload(el);
            if (!payload || payload.type !== 'tail') return null;
            const held = this._dockTailHolder(
                payload.distroId, parseInt(payload.number, 10), payload.tail);
            return held ? held.layer : null;
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas
                || renderer.viewMode !== 'power') return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right
                || y < rect.top || y > rect.bottom) {
            return null;
        }
        const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(
            ((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        if (!hit) return null;
        const under = (this.project.layers || [])
            .find(l => l.id === hit.layerId);
        if (!under) return null;
        const circuit = renderer._powerCircuitForPanel(under, hit.panel);
        const layer = circuit ? circuit.owner : under;
        return (layer.type || 'screen') === 'screen' ? layer : null;
    }

    // Which panel belongs to which port of which screen, frozen at pickup.
    // The data view recomputes its runs every frame and retains nothing, so
    // the dock derives the same picture once per drag from the same single
    // implementation (calculatePortAssignments / the drawn custom paths) and
    // keys it by panel identity - group peers' cabinets arrive as the
    // owner's own items, so a drop on a peer lands on the owner's run.
    _dockBuildDataMap() {
        const map = new Map();
        for (const layer of (this.project.layers || [])) {
            if ((layer.type || 'screen') !== 'screen') continue;
            if (layer.visible === false) continue;
            if ((layer.flowPattern || 'tl-h') === 'custom'
                    && layer.customPortPaths) {
                Object.keys(layer.customPortPaths).forEach(numStr => {
                    const num = parseInt(numStr, 10);
                    (layer.customPortPaths[numStr] || []).forEach(pos => {
                        const panel = (layer.panels || []).find(
                            p => p.row === pos.row && p.col === pos.col);
                        if (panel && !panel.hidden) {
                            map.set(panel,
                                    { ownerId: layer.id, portNum: num });
                        }
                    });
                });
                continue;
            }
            const items = typeof this.calculatePortAssignments === 'function'
                ? this.calculatePortAssignments(layer) : [];
            items.forEach(item => {
                if (item && item.panel && !item.panel.hidden) {
                    map.set(item.panel,
                            { ownerId: layer.id, portNum: item.port });
                }
            });
        }
        return map;
    }

    // ── the drop matrix ───────────────────────────────────────────────────

    _dockPerformDrop(payload, target) {
        sendClientLog('dock_drop', { payload, target });
        if (payload.type === 'port') return this._dockDropPort(payload, target);
        if (payload.type === 'card' || payload.type === 'box') {
            return this._dockDropCardOrBox(payload, target);
        }
        if (payload.type === 'slot') return this._dockDropSlot(payload, target);
        if (payload.type === 'tail') return this._dockDropTail(payload, target);
        if (payload.type === 'distro') {
            return this._dockDropDistro(payload, target);
        }
        if (payload.type === 'plug') return this._dockDropPlug(payload, target);
    }

    _dockDropPort(payload, target) {
        if (target.kind === 'run') {
            // The same request, question and undo entry the panels' Place
            // buttons sent: this plugs in there.
            return this._placePort({
                layerId: String(target.layerId),
                index: target.num - 1,
                cardId: payload.cardId,
                port: payload.port,
            });
        }
        if (target.kind === 'dock') {
            const all = this._portOccupants(payload.cardId, payload.port);
            // A mirrored return is not a claim of its own: it follows the
            // main, so the release is refused HERE, pointed at the socket
            // where clearing actually lands.
            const occupants = all.filter(o => !o.role);
            if (!occupants.length) {
                const back = all.find(o => o.role === 'return');
                if (back) this._dockSay(this._returnFollowsNote(payload, back));
                return;
            }
            // Every claim on a socket is a pin - nothing lands any other
            // way - so every claimant is released. One release per
            // claimant, one history entry for the gesture: the snapshot is
            // taken after the last request lands, so a single Ctrl+Z
            // empties the socket back to how it was.
            let chain = Promise.resolve();
            occupants.forEach((o, i) => {
                chain = chain.then(() => this._assignmentRequest(
                    '/api/port-assignments/unpin', 'POST',
                    { layerId: o.layerId, index: o.number - 1 },
                    null, i === occupants.length - 1 ? 'Release Port' : null));
            });
            return chain;
        }
    }

    _dockDropCardOrBox(payload, target) {
        if (target.kind !== 'screen') return;
        if (payload.type === 'box' && payload.beyondTrunks) {
            // The same fact the Processors panel prints on the box's info
            // line: with no trunk feeding it, its ports are not delivered.
            this._dockSay(`${payload.title} has no trunk on its card - its `
                + 'ports are not delivered, so nothing can land on them.');
            return;
        }
        const scr = ((this._assignment && this._assignment.screens) || [])
            .find(s => s.layerId === String(target.layerId));
        if (!scr) {
            this._dockSay('That screen needs no ports.');
            return;
        }
        const window_ = payload.type === 'box'
            ? { firstPort: payload.first, lastPort: payload.last } : {};
        if (scr.unplaced.length) {
            // "In order from the first unassigned" - the existing overflow
            // fill: spare screen ports, in order, onto the lowest free
            // sockets (of the box's span, for a box).
            return this._takeOffer(Object.assign({
                action: 'place-overflow', layerId: scr.layerId,
                cardId: payload.cardId,
            }, window_));
        }
        // Nothing unassigned: the gesture means "this screen goes on this
        // hardware", which is the existing whole-block move.
        return this._takeOffer(Object.assign({
            action: 'move-block', layerId: scr.layerId,
            cardId: payload.cardId,
        }, window_));
    }

    _dockDropSlot(payload, target) {
        if (target.kind === 'run') {
            const layer = (this.project.layers || [])
                .find(l => l.id === target.layerId);
            if (!layer) return;
            // ONE rule for the whole-multi drop and the mid-multi drop
            // (user, 2026-09-04: "drag multi 2 onto 6 ports it only lets
            // me do 1 ... it should allow me to do up to 6"; 2026-09-05:
            // "i need it to start at 1-1 instead and increase to 1-6"):
            // the box takes its cell's circuits from the FIRST up to the
            // dropped one, as many as it has free - absorbing the
            // one-circuit leftovers a run of pip drops left behind,
            // skipping the head circuits already on another box, never
            // crossing the grid line. takeSocaOnto resegments, re-keys
            // and assigns in ONE history entry; the tray talks.
            const rec = this._powerNaming(layer).socas.get(target.socaIndex);
            const at = rec ? rec.circuits.indexOf(target.num) : -1;
            const ordinal = this.screenCircuits(layer)
                .findIndex(c => c.num === target.num) + 1;
            if (!rec || at < 0 || ordinal < 1) return;
            const label = this.getPowerCircuitLabel(layer, target.num);
            if (payload.output) {
                // A typed spare box: the plug gate and the take, exactly
                // as the preview resolved them (_boxDropPlan); a refusal
                // is said and changes nothing. The box wears its type
                // from the drop on - stamped before the take's own entry.
                const plan = this._boxDropPlan(payload, layer, ordinal);
                if (!plan.ok) {
                    this._dockSay(plan.message);
                    return;
                }
                this._stampBoxType(payload.distroId, payload.number,
                                   payload.output);
            }
            const r = this.takeSocaOnto(layer, ordinal, payload.distroId,
                                        payload.number, 'Assign Multi Distro');
            if (!r.ok) {
                this._dockSay(this._takeRefusalText(payload, r, label));
                return;
            }
            if (r.took < r.tailLen) {
                // Take-what-fits, said out loud - the same convention
                // place-overflow follows with spare ports: the FIRST
                // circuits land, the rest wait.
                this._dockSay(`${payload.title} had ${r.free} free `
                    + `circuit${r.free === 1 ? '' : 's'} - took ${r.took} `
                    + `of the ${r.tailLen} circuits up to ${label}; `
                    + 'the rest stay as their own unassigned multi.');
            }
            this._restateNaming();
            return;
        }
        if (target.kind === 'dock') {
            const members = this._distroMultiNumbers(payload.distroId)
                .get(payload.number) || [];
            if (!members.length) return;
            // Clear every multi the chip names - the chip is the box, and
            // pulling the box off the wall pulls all its feeds. The SAME
            // clear the right-click of this very chip runs (_clearMultis):
            // one gesture, one 'Clear Multi' entry, and the stored
            // programming is forgotten with the assignment - two gestures
            // wearing one history name must not keep different paperwork.
            this._clearMultis(
                members.map(m => ({ layerId: m.layerId, soca: m.soca })),
                'Clear Multi');
        }
    }

    // A tail pip lands on ONE circuit: that circuit alone goes to this
    // box's tail N - the tray's finest grain, for the wall where no whole
    // multi is wanted. Composed entirely from the machinery the other drops
    // already run: the drop-implied split isolates the circuit where it is
    // not a multi of its own (one cut before it, one after the remainder),
    // the incumbents on the box freeze exactly as every join freezes them,
    // and the stored tail set [N] is how a one-circuit multi lands on pip N
    // under the wall-order rule - a set of one has nothing to reorder. ONE
    // history entry for the whole gesture, like the split-drop above.
    _dockDropTail(payload, target) {
        if (target.kind === 'dock') {
            // The drag-back: the chip is the circuit, and pulling it off
            // the wall takes that one circuit off its box - the SAME clear
            // the right-click of this very chip runs (_clearCircuitChip),
            // one gesture, one 'Clear Circuit' entry. A free chip has
            // nothing to release.
            const held = this._dockTailHolder(
                payload.distroId, parseInt(payload.number, 10), payload.tail);
            if (!held) return;
            return this._clearCircuitChip(held.layer, held.rec.index,
                                          held.circuit);
        }
        if (target.kind !== 'run') return;
        const layer = (this.project.layers || [])
            .find(l => l.id === target.layerId);
        if (!layer) return;
        const nm = this._powerNaming(layer);
        const slot = nm.slots.get(target.num);
        const rec = slot ? nm.socas.get(slot.multi) : null;
        if (!rec) return;
        const label = this.getPowerCircuitLabel(layer, target.num);
        const n = parseInt(payload.number, 10);
        if (rec.pinned && rec.distroId === payload.distroId
                && rec.number === n && slot.tail === payload.tail) {
            // Already exactly there - a no-op said out loud, not a refusal.
            this._dockSay(`${label} is already on ${payload.title}.`);
            return;
        }
        // The pips' own occupancy convention: a tail a PINNED member holds
        // is taken (an auto at this number re-deals and defends nothing,
        // the rule every join follows). The dragged circuit's own seat is
        // not in its way - landing there is the no-op above.
        for (const m of (this._distroMultiNumbers(payload.distroId)
                .get(n) || [])) {
            if (!m.pinned) continue;
            const ml = (this.project.layers || [])
                .find(l => l.id === m.layerId);
            const mr = ml && this._powerNaming(ml).socas.get(m.soca);
            if (!mr || !Array.isArray(mr.positions)) continue;
            const i = mr.positions.indexOf(payload.tail);
            if (i < 0) continue;
            if (ml === layer && m.soca === rec.index
                    && mr.circuits[i] === target.num) continue;
            this._dockSay(`Circuit ${payload.tail} is held by ${ml.name} `
                + `${this.getPowerCircuitLabel(ml, mr.circuits[i])} - `
                + 'clear it first, or drop on a free pip.');
            return;
        }
        const at = rec.circuits.indexOf(target.num);
        if (at < 0) return;
        const touched = new Set([layer]);
        let idx = rec.index;
        if (at > 0) {
            // Cut BEFORE the circuit: it becomes the head of the next part.
            const stamped = this._splitSocaApply(layer, idx, at);
            if (!stamped) return;
            stamped.forEach(l => touched.add(l));
            idx += 1;
        }
        if (rec.circuits.length - at > 1) {
            // Cut AFTER it: the remainder stays behind as its own multi
            // (unassigned, the split rule), and the moving part is exactly
            // the one circuit the pip was aimed at.
            const stamped = this._splitSocaApply(layer, idx, 1);
            if (!stamped) return;
            stamped.forEach(l => touched.add(l));
        }
        this._materializeSocaBox(payload.distroId, n, layer, idx)
            .forEach(l => touched.add(l));
        (layer.powerSocaDistro || (layer.powerSocaDistro = {}))[idx]
            = payload.distroId;
        (layer.powerSocaNumber || (layer.powerSocaNumber = {}))[idx] = n;
        (layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {}))[idx]
            = [payload.tail];
        this._circuitTailCache = null;
        this.updateLayers([...touched], true, 'Assign Circuit');
        this._restateNaming();
    }

    _dockDropDistro(payload, target) {
        if (target.kind !== 'screen') return;
        const layer = (this.project.layers || [])
            .find(l => l.id === target.layerId);
        if (!layer) return;
        if ((layer.type || 'screen') !== 'screen') {
            this._dockSay(`${layer.name || 'That layer'} draws no power.`);
            return;
        }
        const plan = this.getSocaPlan(layer);
        const unassigned = plan.filter(s => !s.distroId);
        if (!unassigned.length) {
            this._dockSay(plan.length
                ? `Every multi on ${layer.name} already has a distro. Drag a `
                    + 'slot onto a circuit to move one, or drag it back onto '
                    + 'the tray to unassign it.'
                : `${layer.name} has no circuits to feed.`);
            return;
        }
        // The existing per-multi assignment, once per unassigned multi, in
        // plan order - the numbers fall out of the distro's own sequence.
        // Undo audit: one drag, one entry. The handle's own tooltip calls
        // this one act ("its unassigned multis ALL land on this distro");
        // recorded per-multi it cost N Ctrl+Z presses through half-cabled
        // intermediate walls.
        const touched = new Set();
        unassigned.forEach(s => {
            this.setSocaDistro(layer, s.soca, payload.distroId, false)
                .forEach(l => touched.add(l));
        });
        this.updateLayers([...touched], true, 'Assign Multi Distro');
        this._restateNaming();
    }

    // ── the right-click clears ────────────────────────────────────────────
    //
    // What the context menu's "Clear …" item should be for the point that was
    // right-clicked, or null when the click landed on nothing clearable (the
    // item then stays off the menu entirely). Returns { label, title, run }
    // for a clear that can happen, { label, title, disabled: true } for one
    // that cannot - disabled WITH the reason as the title, because "greyed
    // out and silent" teaches nothing.
    //
    // Every clear here runs the release operations the dock's drag-back runs,
    // and confirms nothing: clearing is undoable and touches only the
    // assignment - names, templates and the hardware itself stay.
    // The payload of the chip under an element, for the right-click
    // surfaces. A circuit chip speaks for ITSELF now that it is a real chip
    // (its clear and merge are the drawn circuit run's own items, re-aimed
    // from the hardware end); the multi header answers as the slot and the
    // distro header as the distro. A chip whose payload cannot be read arms
    // nothing, as before.
    _dockChipPayload(el) {
        const chip = el && el.closest
            ? el.closest('[data-hwdock-payload]') : null;
        if (!chip) return null;
        try {
            return JSON.parse(chip.dataset.hwdockPayload) || null;
        } catch (_) {
            return null;
        }
    }

    // Which circuit holds one tail of box (distroId, number), read off the
    // naming index's rendered positions - the same map the chips drew from.
    // Returns { layer, rec, circuit } for the first claimant, or null for a
    // free tail.
    _dockTailHolder(distroId, number, tail) {
        for (const m of (this._distroMultiNumbers(distroId)
                .get(number) || [])) {
            const l = (this.project.layers || [])
                .find(x => x.id === m.layerId);
            const rec = l && this._powerNaming(l).socas.get(m.soca);
            if (!rec || !Array.isArray(rec.positions)) continue;
            const i = rec.positions.indexOf(tail);
            if (i >= 0) return { layer: l, rec, circuit: rec.circuits[i] };
        }
        return null;
    }

    _prepareClearMenu(x, y) {
        // The dock chip under the cursor first: chips carry their payload on
        // the element, and the tray sits outside the canvas so the two tests
        // cannot both hit.
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('[data-hwdock-payload]')) {
            const payload = this._dockChipPayload(el);
            return payload ? this._clearMenuForDock(payload) : null;
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas) return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right
                || y < rect.top || y > rect.bottom) {
            return null;
        }
        // The same client-to-world walk every canvas gesture does, mirror
        // included - the clear must land on the run under the cursor, not
        // its reflection.
        const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(
            ((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        if (!hit) return null;
        if (renderer.viewMode === 'data-flow') {
            return this._clearMenuForDataRun(hit);
        }
        if (renderer.viewMode === 'power') {
            return this._clearMenuForCircuit(hit);
        }
        return null;
    }

    // A drawn port run in Data view: clear = release that screen-port's pin,
    // the same unpin the strip's release buttons and the drag-back send. A
    // port on a card is always a pin (auto-numbering is retired - user
    // ruling, 2026-09-03), so the clear is offered live whenever the port
    // is attached and disabled only when it is not.
    _clearMenuForDataRun(hit) {
        const run = this._dockBuildDataMap().get(hit.panel);
        if (!run) return null;
        const layer = (this.project.layers || [])
            .find(l => l.id === run.ownerId);
        // The label the run is drawn with, so the menu names what the user
        // is looking at - SR-3 when a card names it, P3 off the template.
        const label = (layer && typeof this.getPortLabelText === 'function'
            && this.getPortLabelText(layer, run.portNum))
            || `port ${run.portNum}`;
        const scr = ((this._assignment && this._assignment.screens) || [])
            .find(s => s.layerId === String(run.ownerId));
        const port = scr
            && (scr.ports || []).find(p => p.number === run.portNum);
        if (!port || !port.cardId) {
            return {
                label: `Clear port ${label}`, disabled: true,
                title: `${label} is not attached to a sending card - there `
                    + 'is nothing to clear.',
            };
        }
        return {
            label: `Clear port ${label}`,
            title: 'Take this port off its card; it stays unattached until '
                + 'you place it again. Names and templates are untouched, '
                + 'and undo puts it back.',
            run: () => {
                sendClientLog('dock_clear', { kind: 'run',
                    layerId: scr.layerId, index: port.index });
                return this._assignmentRequest(
                    '/api/port-assignments/unpin', 'POST',
                    { layerId: scr.layerId, index: port.index },
                    null, 'Release Port');
            },
        };
    }

    // A drawn circuit run in Power view: clear = un-assign that circuit's
    // multi, number then distro, the drag-back semantics in one gesture.
    _clearMenuForCircuit(hit) {
        const under = (this.project.layers || [])
            .find(l => l.id === hit.layerId);
        const circuit = under && window.canvasRenderer
            ? window.canvasRenderer._powerCircuitForPanel(under, hit.panel)
            : null;
        if (!circuit) return null;
        const owner = circuit.owner;
        const nm = this._powerNaming(owner);
        const slot = nm.slots.get(circuit.circuitNum);
        const rec = slot ? nm.socas.get(slot.multi) : null;
        if (!rec) return null;
        const name = rec.name || `multi ${rec.number}`;
        if (!rec.distroId) {
            return {
                label: `Clear multi ${name}`, disabled: true,
                title: `${name} is not on a distro - there is nothing to `
                    + 'clear.',
            };
        }
        return {
            label: `Clear multi ${name}`,
            title: 'Clear this multi - its distro, number, stored '
                + 'positions, typed name, home-run length and label '
                + 'overrides are all forgotten. One undo puts everything '
                + 'back.',
            run: () => this._clearMultis(
                [{ layerId: owner.id, soca: rec.index }], 'Clear Multi'),
        };
    }

    // ── the right-click merge-back ────────────────────────────────────────
    //
    // The reverse of the drop-implied split. With the sidebar's Un-split
    // button gone, the way back is the same surface the split now lives on:
    // right-click the circuit run (or the slot chip holding the split-off
    // part) and "Merge back into <name>" removes the stored boundary
    // through the existing un-split - undoable, like every clear above.
    // Unlike the clear there is no disabled state: a multi with no stored
    // boundary simply has nothing to merge, which is its ordinary condition,
    // not a refused gesture - so the item stays off the menu entirely.
    _prepareMergeMenu(x, y) {
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('[data-hwdock-payload]')) {
            const payload = this._dockChipPayload(el);
            if (!payload) return null;
            if (payload.type === 'tail') {
                // A circuit chip merges as the drawn circuit run does: both
                // sides of a boundary touching its holder's multi.
                const held = this._dockTailHolder(
                    payload.distroId, parseInt(payload.number, 10),
                    payload.tail);
                return held
                    ? this._mergeMenuForMulti(held.layer, held.rec.index,
                                              false)
                    : null;
            }
            if (payload.type !== 'slot') return null;
            // The chip is the box, so it offers to hand back only a
            // SPLIT-OFF part it holds - a head member whose tail lives on
            // another box is that other surface's merge, not this chip's.
            for (const m of (this._distroMultiNumbers(payload.distroId)
                    .get(payload.number) || [])) {
                const layer = (this.project.layers || [])
                    .find(l => l.id === m.layerId);
                if (!layer) continue;
                const offer = this._mergeMenuForMulti(layer, m.soca, true);
                if (offer) return offer;
            }
            return null;
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas
                || renderer.viewMode !== 'power') return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right
                || y < rect.top || y > rect.bottom) {
            return null;
        }
        // The same client-to-world walk _prepareClearMenu makes, mirror
        // included, for the same reason.
        const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(
            ((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        if (!hit) return null;
        const under = (this.project.layers || [])
            .find(l => l.id === hit.layerId);
        const circuit = under
            ? renderer._powerCircuitForPanel(under, hit.panel) : null;
        if (!circuit) return null;
        const slot = this._powerNaming(circuit.owner)
            .slots.get(circuit.circuitNum);
        return slot
            ? this._mergeMenuForMulti(circuit.owner, slot.multi, false)
            : null;
    }

    // The merge offer for one multi, or null when no stored boundary
    // touches it. The clicked part can sit on either side of the boundary:
    // the split-off TAIL merges back into the part before it, and the HEAD
    // takes its split-off tail back - the surviving multi is the head
    // either way (unsplitSocaAfter's rule), so the label names it.
    // `tailOnly` restricts to the tail side, for surfaces that hold the
    // split-off part specifically (the slot chip).
    _mergeMenuForMulti(layer, socaIndex, tailOnly) {
        const count = this.screenCircuits(layer).length;
        const segs = this._socaSegments(layer, count);
        const idx = Number(socaIndex);
        const seg = segs.find(s => s.index === idx);
        if (!seg) return null;
        const prev = segs.find(s => s.index === idx - 1);
        const headIdx = (prev && prev.userEnd) ? prev.index
            : (!tailOnly && seg.userEnd ? seg.index : null);
        if (headIdx == null) return null;
        const head = this._powerNaming(layer).socas.get(headIdx);
        const name = (head && head.name) || `multi ${headIdx}`;
        return {
            label: `Merge back into ${name}`,
            title: 'Remove the split boundary: the circuits fall back into '
                + `one multi under ${name}, and the split-off part's `
                + 'assignment goes with its identity. Undo puts the split '
                + 'back.',
            run: () => {
                sendClientLog('dock_merge',
                              { layerId: layer.id, soca: headIdx });
                this.unsplitSocaAfter(layer, headIdx);
                this._restateNaming();
            },
        };
    }

    // ── the right-click circuit sharing ──────────────────────────────────
    //
    // The manual 2fer lever the retired Splitters panel rows carried, on
    // the surfaces the circuit actually lives on: right-click a drawn
    // circuit run or its chip and "Share with next run via 2fer" gangs it
    // with the run after it (mergeSplitterCircuits), "Un-share" un-gangs a
    // shared one (splitSplitterCircuits) - the existing ops, the existing
    // undo entries. Gated exactly as the panel rows were: packed auto
    // circuits (splitters on), or drawn custom circuits (merge-only by the
    // ops' own rule). Off the gate, or off a circuit, neither item appears
    // - like the merge-back, absence is the ordinary condition, not a
    // refusal.

    // The circuit under a point, for the share menu: a dock circuit chip
    // (its holder names the circuit), or a drawn circuit run on the canvas
    // - the same two surfaces every circuit gesture reads.
    _dockCircuitAt(x, y) {
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('[data-hwdock-payload]')) {
            const payload = this._dockChipPayload(el);
            if (!payload || payload.type !== 'tail') return null;
            const held = this._dockTailHolder(
                payload.distroId, parseInt(payload.number, 10), payload.tail);
            if (!held) return null;
            return { layer: held.layer, num: held.circuit };
        }
        const renderer = window.canvasRenderer;
        if (!renderer || !renderer.canvas
                || renderer.viewMode !== 'power') return null;
        const rect = renderer.canvas.getBoundingClientRect();
        if (x < rect.left || x > rect.right
                || y < rect.top || y > rect.bottom) {
            return null;
        }
        const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
        const worldX = renderer._unmirrorWorldX(
            ((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
        const hit = renderer.getPanelAt(worldX, worldY);
        if (!hit) return null;
        const under = (this.project.layers || [])
            .find(l => l.id === hit.layerId);
        const circuit = under
            ? renderer._powerCircuitForPanel(under, hit.panel) : null;
        return circuit
            ? { layer: circuit.owner, num: circuit.circuitNum } : null;
    }

    _prepareShareMenus(x, y) {
        const none = { share: null, unshare: null };
        if (!window.canvasRenderer
                || window.canvasRenderer.viewMode !== 'power') return none;
        // With a sweep selection armed, the batch entries ARE the sharing
        // story for this opening - a single-run "Share with next" beside
        // "3fer them" would be two grammars for one gesture.
        if (this._sweepSelection && this._sweepSelection.nums
                && this._sweepSelection.nums.length) return none;
        const at = this._dockCircuitAt(x, y);
        if (!at) return none;
        const { layer, num } = at;
        const sp = this.getPowerSplitters(layer);
        const custom = this.usesCustomCircuits(layer);
        if (!sp.enabled && !custom) return none;
        const circuits = this.screenCircuits(layer);
        const idx = circuits.findIndex(c => c.num === num);
        if (idx < 0) return none;
        const c = circuits[idx];
        const label = this.getPowerCircuitLabel(layer, c.num);
        const out = { share: null, unshare: null };
        const next = circuits[idx + 1];
        if (next) {
            // The splitter the merge would need: every run already ganged
            // on either side, plus the join.
            const ways = (c.runIds || [c.num]).length
                + (next.runIds || [next.num]).length;
            out.share = {
                label: `Share with next run via ${ways}fer`,
                title: `Gang ${label} and `
                    + `${this.getPowerCircuitLabel(layer, next.num)} onto `
                    + 'one circuit through a splitter. Honored even over '
                    + 'capacity - the chip flags OVER. Undo un-gangs it.',
                run: () => {
                    sendClientLog('dock_share',
                                  { layerId: layer.id, num: c.num });
                    this.mergeSplitterCircuits(layer, [c.num, next.num]);
                },
            };
        }
        if ((c.runIds || []).length > 1) {
            out.unshare = {
                label: 'Un-share',
                title: `Un-gang ${label}'s runs back onto circuits of `
                    + 'their own, and pin them out of auto packing. Undo '
                    + 'restores the share.',
                run: () => {
                    sendClientLog('dock_unshare',
                                  { layerId: layer.id, num: c.num });
                    this.splitSplitterCircuits(layer, [c.num]);
                },
            };
        }
        return out;
    }

    // ── the batch verb: sweep → right-click → "3fer them" ────────────────
    //
    // 2026-08-30, user pick ("lets go for B and then right click"): the
    // sweep (canvas.js Alt+drag) arms a contiguous run selection, and the
    // right-click menu deals it as Nfers - "3fer them (6 × 3fer)", the
    // group math in the label so the deal reads before it is taken. With
    // NO selection the same entries act on the whole screen under the
    // cursor ("one run per column, 3 columns - right click the whole wall,
    // it makes those 3 columns a 3fer"). Gated exactly as the single-run
    // share items are (splitters on, or custom circuits) - but the batch
    // entries stay ON the menu disabled with the reason, because a gesture
    // nobody can find teaches nothing.
    _prepareBatchMenu(x, y) {
        const renderer = window.canvasRenderer;
        if (!renderer || renderer.viewMode !== 'power'
                || !renderer.canvas) return null;
        const el = document.elementFromPoint(x, y);
        if (el && el.closest && el.closest('#hardware-dock')) return null;
        const sel = this._sweepSelection;
        let layer = null;
        let nums = null;
        let scope = null;
        if (sel && Array.isArray(sel.nums) && sel.nums.length) {
            layer = (this.project.layers || [])
                .find(l => l.id === sel.layerId);
            if (!layer) return null;
            // Degrade-on-read: circuits the plan no longer produces fall
            // out of the selection instead of poisoning the deal.
            const have = new Set(this.screenCircuits(layer).map(c => c.num));
            nums = sel.nums.filter(n => have.has(n));
            scope = 'selection';
        } else {
            const rect = renderer.canvas.getBoundingClientRect();
            if (x < rect.left || x > rect.right
                    || y < rect.top || y > rect.bottom) return null;
            const worldY = ((y - rect.top) - renderer.panY) / renderer.zoom;
            const worldX = renderer._unmirrorWorldX(
                ((x - rect.left) - renderer.panX) / renderer.zoom, worldY);
            const hit = renderer.getPanelAt(worldX, worldY);
            if (!hit) return null;
            const under = (this.project.layers || [])
                .find(l => l.id === hit.layerId);
            const circuit = under
                ? renderer._powerCircuitForPanel(under, hit.panel) : null;
            if (!circuit) return null;
            layer = circuit.owner;
            nums = this.screenCircuits(layer).map(c => c.num);
            scope = 'screen';
        }
        if (!layer || !nums || nums.length < 2) return null;
        // The deal is at RUN grain, so existing gangs inside the batch
        // re-deal with everything else - count the runs, not the circuits.
        const chosen = new Set(nums);
        let runCount = 0;
        let hasGang = false;
        this.screenCircuits(layer).forEach(c => {
            if (!chosen.has(c.num)) return;
            const ids = c.runIds || [c.num];
            runCount += ids.length;
            if (ids.length > 1) hasGang = true;
        });
        if (runCount < 2) return null;
        const sp = this.getPowerSplitters(layer);
        const custom = this.usesCustomCircuits(layer);
        const gated = !sp.enabled && !custom;
        const verb = scope === 'screen' ? 'this screen' : 'them';
        const entries = [];
        [2, 3, 4].forEach(n => {
            if (runCount < n) return;
            // A size whose deal produces none of itself is another size's
            // entry wearing the wrong name - "4fer them" over five runs
            // deals 3+2, which IS the 3fer entry. Offer only honest sizes.
            if (!this.batchNferGroups(runCount, n).includes(n)) return;
            const label = `${n}fer ${verb} `
                + `(${this.batchNferLabel(runCount, n)})`;
            if (gated) {
                entries.push({
                    label, disabled: true,
                    title: `Sharing is off for ${layer.name} - turn on `
                        + '"Share circuits via splitters" in Power Settings '
                        + '(or route its circuits custom) to gang runs.',
                });
                return;
            }
            entries.push({
                label,
                title: `Deal ${runCount} run${runCount === 1 ? '' : 's'} `
                    + `left to right as ${this.batchNferLabel(runCount, n)} `
                    + '- adjacent groups, each its own circuit. Honored '
                    + 'even over capacity - a heavy gang flags OVER. One '
                    + 'undoable step.',
                run: () => {
                    sendClientLog('power_batch_nfer',
                                  { layerId: layer.id, n, scope,
                                    runs: runCount });
                    this.batchShareCircuits(layer, nums, n,
                        `${n}fer ${scope === 'screen'
                            ? 'Screen' : 'Selection'}`);
                    this._sweepSelection = null;
                },
            });
        });
        if (!entries.length) return null;
        const out = { entries, scope };
        if (hasGang && !gated) {
            out.unshare = {
                label: scope === 'screen'
                    ? 'Un-share this screen' : 'Un-share all',
                title: 'Un-gang every shared circuit '
                    + (scope === 'screen'
                        ? 'on this screen' : 'in the selection')
                    + ' back onto runs of their own. One undoable step.',
                run: () => {
                    sendClientLog('power_batch_unshare',
                                  { layerId: layer.id, scope });
                    this.splitSplitterCircuits(layer, nums,
                        scope === 'screen'
                            ? 'Un-share Screen' : 'Un-share Selection');
                    this._sweepSelection = null;
                },
            };
        }
        return out;
    }

    // A dock chip: the same clears, from the hardware end of the cable.
    _clearMenuForDock(payload) {
        if (payload.type === 'port') {
            const label = `Clear ${payload.title}`;
            const all = this._portOccupants(payload.cardId, payload.port);
            const occupants = all.filter(o => !o.role);
            // The port's hand-picked backup (manual redundancy), part of
            // this socket's programming: the clear forgets it with the
            // claim. Typed port names stay - they are hardware naming,
            // not programming.
            const found = this._dockCardById(payload.cardId);
            const pick = found
                && (found.card.backupPorts || {})[String(payload.port)];
            // The pick-only offer, for a socket with no claim to release
            // but a stored pick to forget. Sits BELOW the role refusals: a
            // socket that is itself a backup end answers by its role.
            const pickOnly = () => ({
                label,
                title: `${payload.title} holds no claim, but it picks `
                    + 'a backup port - clear that pick. Undo puts it '
                    + 'back.',
                run: () => {
                    sendClientLog('dock_clear',
                                  { kind: 'port-pick', payload });
                    return this._dockClearPortPicks(
                        found, [payload.port], 'Clear Port');
                },
            });
            if (!occupants.length) {
                // A backup socket carrying a mirrored return refuses by the
                // role, naming the screen and the main the display follows
                // - "free" would deny exactly what the tile shows.
                const back = all.find(o => o.role === 'return');
                if (back) {
                    return {
                        label, disabled: true,
                        title: this._returnFollowsNote(payload, back),
                    };
                }
                // An idle backup socket is not "free" either - it is
                // role-claimed and just carrying no return yet, and its
                // own tile says so; the menu must not contradict it.
                const rp = this._dockResolvedPort(payload.cardId,
                                                  payload.port);
                if (rp && rp.backsUp) {
                    return {
                        label, disabled: true,
                        title: `${payload.title} backs up ${rp.backsUp.label
                            || `${rp.backsUp.boxTitle
                                ? `${rp.backsUp.boxTitle} ` : ''}port `
                                + `${rp.backsUp.localPort
                                    || rp.backsUp.port}`} - it is that `
                            + 'port\'s return end and holds no claim of '
                            + 'its own.',
                    };
                }
                if (pick) return pickOnly();
                return {
                    label, disabled: true,
                    title: `${payload.title} is free - there is nothing to `
                        + 'clear.',
                };
            }
            // Every claim is a pin (nothing lands any other way), so an
            // occupied socket always clears: every claimant comes off.
            return {
                label,
                title: 'Take the screen port off this socket - it stays '
                    + 'unattached until placed again'
                    + (pick ? ', and clear the socket\'s hand-picked '
                        + 'backup port'
                        : '')
                    + '. Undo puts it back.',
                run: () => {
                    sendClientLog('dock_clear', { kind: 'port', payload });
                    const release = this._dockReleasePins(
                        occupants.map(o => ({ layerId: o.layerId,
                                              index: o.number - 1 })),
                        pick ? null : 'Release Port');
                    // The pick clear rides the same gesture: the snapshot
                    // moves to the LAST request, so the whole clear stays
                    // one history entry.
                    return pick
                        ? release.then(() => this._dockClearPortPicks(
                            found, [payload.port], 'Clear Port'))
                        : release;
                },
            };
        }
        if (payload.type === 'card' || payload.type === 'box') {
            const label = `Clear ${payload.title}`;
            const first = payload.type === 'box' ? payload.first : -Infinity;
            const last = payload.type === 'box' ? payload.last : Infinity;
            // Every screen port on the card (or inside the box's span) is a
            // pin - there is no other way onto a card - and the clear takes
            // all of them off.
            const pins = [];
            ((this._assignment && this._assignment.screens) || [])
                .forEach(scr => (scr.ports || []).forEach(p => {
                    if (p.cardId === payload.cardId
                            && p.port >= first && p.port <= last) {
                        pins.push({ layerId: scr.layerId, index: p.index });
                    }
                }));
            // The card's per-port backup picks in this range are its
            // programming too, and the clear forgets them with the pins.
            // Typed port names stay - hardware naming, not programming.
            const found = this._dockCardById(payload.cardId);
            const picks = [];
            if (found) {
                Object.keys(found.card.backupPorts || {}).forEach(k => {
                    const pn = parseInt(k, 10);
                    if (Number.isFinite(pn) && pn >= first && pn <= last) {
                        picks.push(pn);
                    }
                });
            }
            if (!pins.length && !picks.length) {
                return {
                    label, disabled: true,
                    title: `Nothing is attached to ${payload.title} and it `
                        + 'holds no per-port backup picks - there is '
                        + 'nothing to clear.',
                };
            }
            return {
                label,
                title: `Take every screen port off ${payload.title} - they `
                    + 'stay unattached until placed again'
                    + (picks.length
                        ? ' - and clear its per-port backup picks' : '')
                    + ', as one undoable step.',
                run: () => {
                    sendClientLog('dock_clear',
                                  { kind: payload.type, payload,
                                    count: pins.length,
                                    picks: picks.length });
                    const release = pins.length
                        ? this._dockReleasePins(
                            pins, picks.length ? null : 'Release Ports')
                        : Promise.resolve();
                    // The picks ride the same gesture; the snapshot moves
                    // to the last request so one Ctrl+Z restores pins and
                    // picks together.
                    return picks.length
                        ? release.then(() => this._dockClearPortPicks(
                            found, picks, 'Clear Card'))
                        : release;
                },
            };
        }
        if (payload.type === 'tail') {
            // The circuit chip's clear, re-aimed from the hardware end -
            // the finest grain of the tray's three clears: the CHIP is the
            // circuit (this item), the multi header is the BOX ('Clear
            // multi', the slot branch below) and the distro header is
            // EVERYTHING on it ('Clear <distro>'). A free chip states its
            // freedom. A held chip clears at circuit scope whatever its
            // multi holds (user, 2026-09-05: "i want to delete the 6th
            // circuit from the distro ... can only clear the whole
            // multi"): the circuit comes off the box and forgets how it
            // was programmed - its position, its label override, its
            // manual splitter entries - and the multi's other circuits
            // stay exactly where the wall showed them, the multi's name
            // and home-run length with them (_clearCircuitChip).
            const held = this._dockTailHolder(
                payload.distroId, parseInt(payload.number, 10), payload.tail);
            if (!held) {
                return {
                    label: `Clear ${payload.title}`, disabled: true,
                    title: `${payload.title} is free - there is nothing to `
                        + 'clear.',
                };
            }
            const label = this.getPowerCircuitLabel(held.layer,
                                                    held.circuit);
            const rest = held.rec.circuits.length - 1;
            return {
                label: `Clear circuit ${label}`,
                title: 'Take this circuit off the box and forget how it '
                    + 'was programmed - its stored position and its '
                    + 'label override go with the assignment'
                    + (rest
                        ? `; the multi's other ${rest} circuit`
                            + `${rest === 1 ? ' stays' : 's stay'} where `
                            + `${rest === 1 ? 'it is' : 'they are'}`
                        : '')
                    + '. One undo puts it all back.',
                run: () => this._clearCircuitChip(
                    held.layer, held.rec.index, held.circuit),
            };
        }
        if (payload.type === 'slot') {
            const label = `Clear ${payload.title}`;
            const members = this._distroMultiNumbers(payload.distroId)
                .get(payload.number) || [];
            if (!members.length) {
                return {
                    label, disabled: true,
                    title: `${payload.title} is free - there is nothing to `
                        + 'clear.',
                };
            }
            return {
                label,
                title: 'Clear every multi on this slot - the chip is the '
                    + 'box, and clearing the box takes all its feeds and '
                    + 'forgets how they were programmed: stored positions, '
                    + 'typed names, home-run lengths and label overrides. '
                    + 'One undoable step.',
                run: () => this._clearMultis(
                    members.map(m => ({ layerId: m.layerId, soca: m.soca })),
                    'Clear Multi'),
            };
        }
        if (payload.type === 'distro') {
            const label = `Clear ${payload.title}`;
            const members = [];
            for (const l of (this.project.layers || [])) {
                if ((l.type || 'screen') !== 'screen') continue;
                for (const rec of this._powerNaming(l).socas.values()) {
                    if (rec.distroId === payload.distroId) {
                        members.push({ layerId: l.id, soca: rec.index });
                    }
                }
            }
            if (!members.length) {
                return {
                    label, disabled: true,
                    title: `No multis are assigned to ${payload.title} - `
                        + 'there is nothing to clear.',
                };
            }
            return {
                label,
                title: `Clear every multi on ${payload.title} - the `
                    + 'assignments and the stored programming (positions, '
                    + 'typed names, home-run lengths, label overrides) - '
                    + `as one undoable step. ${payload.title} itself keeps `
                    + 'its name and electrical setup.',
                run: () => this._clearMultis(members, 'Clear Distro'),
            };
        }
        return null;
    }

    // One release per pin, ONE history entry for the gesture - the snapshot
    // rides the last request the way the drag-back's does, so a single
    // Ctrl+Z puts the whole card back.
    _dockReleasePins(pins, action) {
        let chain = Promise.resolve();
        pins.forEach((p, i) => {
            chain = chain.then(() => this._assignmentRequest(
                '/api/port-assignments/unpin', 'POST',
                { layerId: p.layerId, index: p.index },
                null, i === pins.length - 1 ? action : null));
        });
        return chain;
    }

    // Clear a set of multis as ONE gesture with ONE history entry: a
    // distro-level clear is one decision, and Ctrl+Z must put every feed
    // back at once. A clear FORGETS the multi's stored programming, not
    // just its assignment (user ruling, 2026-08-30: clearing must not
    // remember "how i had it programmed before with balancing etc"):
    // distro, number, the stored tail set and breaker offset, the typed
    // name and home-run length, the circuits' label overrides, and the
    // manual share/split entries covering those circuits - see
    // _wipeSocaProgramming. The cuts at the cleared multis' edges go too,
    // and with them every cut left between two multis nobody is feeding
    // on the touched layers (user ruling, 2026-09-04, extending the
    // above: after a clear the one-circuit multis a run of pip drops left
    // behind still read S1[1-6] S2[7] S3[8] ..., "the numbering is all
    // wrong"), so the cleared circuits AND the unassigned leftovers fall
    // back onto the natural box grid - _socaClearSplitPoints decides
    // which points, _resegmentSocaStores re-keys every multi that was NOT
    // cleared so it keeps its name, distro, number and length under its
    // new index. Still ONE history entry.
    _clearMultis(members, action) {
        sendClientLog('dock_clear', { kind: 'multis', action,
                                      count: members.length });
        // Every member's circuits and run ids are read BEFORE any store
        // moves - the wipe itself renumbers the wall it would otherwise
        // be reading.
        const jobs = [];
        members.forEach(m => {
            const layer = (this.project.layers || [])
                .find(l => l.id === m.layerId);
            if (!layer) return;
            jobs.push({ layer, soca: m.soca,
                        targets: this._socaClearTargets(layer, m.soca) });
        });
        if (!jobs.length) return;
        jobs.forEach(j =>
            this._wipeSocaProgramming(j.layer, j.soca, j.targets));
        // The wipe deleted the cleared multis' entries under their OLD
        // indexes; now the cuts go and the survivors move to their new
        // ones - per layer, every cleared multi of that layer at once.
        const byLayer = new Map();
        jobs.forEach(j => {
            const arr = byLayer.get(j.layer) || [];
            arr.push(j.soca);
            byLayer.set(j.layer, arr);
        });
        for (const [layer, socas] of byLayer) {
            this._resegmentSocaStores(
                layer, this._socaClearSplitPoints(layer, socas));
        }
        // The clear renumbers both buckets it touches, so every label
        // on the show can move - same cache drop the setters make.
        this._circuitTailCache = null;
        this.updateLayers([...new Set(jobs.map(j => j.layer))], true,
                          action);
        this._restateNaming();
    }

    // One circuit chip's clear - the chip is the circuit, so ONE circuit
    // comes off the box: the assignment goes AND the programming the
    // gesture stored - the position on the box, the label override, any
    // manual share entries - so re-assigning deals naturally instead of
    // resurrecting the old seat. The multi's typed name and home-run
    // length are identity, not programming, and stay at this scope (the
    // multi's own clear forgets those).
    //
    // Where the holder is a multi of ONE circuit (the pip drop's product)
    // the multi IS the circuit: the two cuts the pip drop made around it
    // go with it, and so does every cut between the unassigned leftovers
    // its neighbours were chopped into (user ruling, 2026-09-04), so the
    // whole run falls back into the natural box - _socaClearSplitPoints,
    // the same rule the multi clear runs. Where the holder has MORE
    // circuits (user, 2026-09-05: "delete the 6th circuit from the
    // distro"), the circuit is cut out on its own and the rest of the
    // multi stays put - head and tail parts on the same box, holding the
    // tails they showed (_socaReleaseCircuit); the freed circuit is then
    // a one-circuit unassigned leftover, and the NEXT clear beside it
    // welds it by the 2026-09-04 rule, the next drop absorbs it by the
    // take rule. The removed circuit's own paperwork is forgotten AFTER
    // the cut, which read the wall as shown - the tails held are the
    // tails the user saw. ONE history entry either way.
    _clearCircuitChip(layer, socaIndex, circuitNum) {
        sendClientLog('dock_clear', { kind: 'circuit', layerId: layer.id,
                                      soca: socaIndex, circuit: circuitNum });
        const idx = Number(socaIndex);
        const runIds = [];
        this.screenCircuits(layer).forEach(c => {
            if (c.num !== circuitNum) return;
            (c.runIds || [c.num]).forEach(id => runIds.push(id));
        });
        const rec = this._powerNaming(layer).socas.get(idx);
        if (rec && rec.circuits.length > 1) {
            const r = this._socaReleaseCircuit(layer, idx, circuitNum);
            if (!r) return;
            if (layer.powerLabelOverrides) {
                delete layer.powerLabelOverrides[circuitNum];
            }
            this._wipeSplitterManualFor(layer, runIds);
            this._circuitTailCache = null;
            this.updateLayers(r.touched, true, 'Clear Circuit');
            this._restateNaming();
            return;
        }
        for (const field of ['powerSocaNumber', 'powerSocaDistro',
                             'powerSocaPhasePos', 'powerSocaPhaseOffset']) {
            if (layer[field]) delete layer[field][idx];
        }
        if (layer.powerLabelOverrides) {
            delete layer.powerLabelOverrides[circuitNum];
        }
        this._wipeSplitterManualFor(layer, runIds);
        this._resegmentSocaStores(
            layer, this._socaClearSplitPoints(layer, [idx]));
        this._circuitTailCache = null;
        this.updateLayers([layer], true, 'Clear Circuit');
        this._restateNaming();
    }

    // One resolved card (with its processor, for the routes that key on
    // both) off the same tree the tiles drew.
    _dockCardById(cardId) {
        for (const proc of this._processorsResolved || []) {
            for (const slot of proc.slots || []) {
                if (slot.card && slot.card.id === cardId) {
                    return { proc, card: slot.card };
                }
            }
        }
        return null;
    }

    // Clear the hand-picked backup on each named port of one card - one
    // PUT per port through the same route the chip's Backed-by fields use,
    // the snapshot riding the LAST request so the whole gesture is one
    // history entry (the _dockReleasePins convention).
    _dockClearPortPicks(found, ports, action) {
        let chain = Promise.resolve();
        ports.forEach((pn, i) => {
            chain = chain.then(() => this._processorRequest(
                `/api/processors/${found.proc.id}/cards/${found.card.id}`
                    + `/ports/${pn}`,
                'PUT', { backup: null },
                i === ports.length - 1 ? action : null));
        });
        return chain;
    }

    // One resolved port off the same tree the tiles drew, so a menu can
    // read the role facts (backsUp) the occupancy alone cannot carry.
    _dockResolvedPort(cardId, number) {
        for (const proc of this._processorsResolved || []) {
            for (const slot of proc.slots || []) {
                const card = slot.card;
                if (card && card.id === cardId) {
                    return (card.ports || [])
                        .find(p => p.number === number) || null;
                }
            }
        }
        return null;
    }

    // The one sentence every refusal on a mirrored backup socket says:
    // whose return the socket carries, and where the clear actually lands.
    // The display is derived - it follows the main through the backup link
    // - so the main is the only thing there is to clear.
    _returnFollowsNote(payload, occupant) {
        const main = occupant.main || {};
        const mainName = main.label
            || (main.port
                ? `${main.boxTitle ? `${main.boxTitle} ` : ''}port `
                    + `${main.localPort || main.port}`
                : 'its main port');
        return `${payload.title} carries ${occupant.name} `
            + `p${occupant.number}'s return - it follows ${mainName}; `
            + 'clear that port to clear both ends.';
    }

    // A refusal the server never saw still deserves a sentence somewhere
    // visible; the status bar is the one strip that exists in every view.
    _dockSay(text) {
        const el = document.getElementById('status-message');
        if (!el) return;
        el.textContent = text;
        clearTimeout(this._dockSayTimer);
        this._dockSayTimer = setTimeout(() => {
            el.textContent = 'Ready';
        }, 6000);
    }
}

for (const k of Object.getOwnPropertyNames(_HardwareDock.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_HardwareDock.prototype, k));
    }
}
