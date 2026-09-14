// app-dock-sweep: snake brackets and the tray sweep - the blue brackets
// placed under a snake's ports after layout, the press-and-drag sweep that
// gathers a run of port chips, and the snake context menu the sweep arms.
// Moved verbatim out of app-dock.js and attached to the prototype via the
// carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _DockSweep {
    // ── the brackets ─────────────────────────────────────────────────────
    //
    // A snake reads as a blue bracket under its ports with a tag "SNAKE A
    // · 6 channel · 100'" (snake-mock.html, "How a snake reads"). Placed by
    // measurement after layout: one bracket per contiguous run of the
    // snake's chips in grid order, split again where the grid wraps a run
    // to the next row, the tag on the first. A grid carrying a snake (or a
    // sweep) opens its rows up to make room. The sweep's ghost is the same
    // bracket dashed, saying what the right-click will make.
    //
    // A snake that CROSSES devices (2026-09-09) draws a bracket in every
    // unit it reaches: each spans that unit's members, and each tag says
    // the whole snake's channels with a small "↔" - the loom is one, and the
    // count on a bracket is never the half of it you happen to be looking
    // at.
    _dockPlaceSnakeBrackets(body) {
        const host = body || document.getElementById('hardware-dock-body');
        if (!host) return;
        host.querySelectorAll('.hw-dock-grid[data-lrd-snake-owner]')
            .forEach(grid => {
                grid.querySelectorAll(':scope > .hw-dock-snake')
                    .forEach(el => el.remove());
                const [kind, id] = grid.dataset.lrdSnakeOwner.split(':');
                const owner = this._dataCableOwner(kind, id);
                // The show's snakes that reach into THIS unit, each with
                // the sockets it holds here.
                const snakes = !owner ? [] : this.getShowSnakes()
                    .map(s => ({ snake: s,
                                 here: this.snakeMembersOn(s, owner) }))
                    .filter(s => s.here.length);
                const swept = this._traySweepSocketsOn(kind, id);
                const sweep = swept.length ? swept : null;
                grid.classList.toggle('hw-dock-grid-snaked',
                                      snakes.length > 0 || !!sweep);
                if (!snakes.length && !sweep) return;
                if (!grid.offsetParent) return;   // folded away: nothing to measure
                const tiles = [...grid.querySelectorAll(':scope > .lrd-tile')];
                const socketOf = (t) => parseInt(
                    (t.dataset.lrdTile || '').split('-').pop(), 10);
                const runsFor = (set) => {
                    const runs = [];
                    let cur = null;
                    tiles.forEach((t, i) => {
                        if (!set.has(socketOf(t))) { cur = null; return; }
                        if (cur && i === cur.last + 1
                                && t.offsetTop === cur.top) {
                            cur.last = i;
                            cur.tiles.push(t);
                        } else {
                            cur = { last: i, top: t.offsetTop, tiles: [t] };
                            runs.push(cur);
                        }
                    });
                    return runs;
                };
                const place = (runs, text, snake) => {
                    runs.forEach((run, i) => {
                        const first = run.tiles[0];
                        const last = run.tiles[run.tiles.length - 1];
                        const el = document.createElement('div');
                        el.className = 'hw-dock-snake'
                            + (snake ? '' : ' hw-dock-snake-ghost');
                        el.style.left = `${first.offsetLeft}px`;
                        el.style.width = `${last.offsetLeft + last.offsetWidth
                            - first.offsetLeft}px`;
                        el.style.top = `${first.offsetTop
                            + first.offsetHeight + 2}px`;
                        if (snake) {
                            el.dataset.lrdSnakeOwner = grid.dataset.lrdSnakeOwner;
                            el.dataset.lrdSnakeId = snake.id;
                        }
                        if (i === 0) {
                            const tag = document.createElement('span');
                            tag.className = 'hw-dock-snake-tag';
                            tag.textContent = text;
                            tag.title = snake
                                ? `${text}. Right-click to rename, set the `
                                    + 'home run or unsnake it.'
                                : 'Right-click the lit chips to snake them '
                                    + '(Alt+Enter).';
                            el.appendChild(tag);
                        }
                        grid.appendChild(el);
                    });
                };
                snakes.forEach(({ snake, here }) => place(
                    runsFor(new Set(here)),
                    this.snakeTagText(snake)
                    + (this.snakeSpansOwners(snake) ? ' ↔' : ''), snake));
                if (sweep) {
                    const ways = (this._traySweep.members || []).length;
                    place(runsFor(new Set(sweep)),
                          this.snakeSizeText('', ways)
                          + (ways > sweep.length ? ' ↔' : ''), null);
                }
            });
    }

    // ── the sweep ────────────────────────────────────────────────────────
    //
    // Hold Alt and drag across the port chips: the chips light, a ghost
    // bracket says "N channel snake", and a right-click (or Alt+Enter) forms
    // the snake. The selection is the CONTIGUOUS range between the anchor
    // chip and the hovered one, in the order the chips sit in the TRAY -
    // the canvas sweep's rule, on the tray's own set (_traySweep, never
    // the canvas's _sweepSelection). Since 2026-09-09 that order runs
    // across units: a sweep that starts on box A and ends on box B lights
    // both, because "Any sockets, any device" - the range is the chips
    // between the two, wherever they live. Escape, a plain click elsewhere
    // or the snake itself clears it.

    _traySweepHas(owner, socket) {
        const sw = this._traySweep;
        const n = parseInt(socket, 10);
        return !!(sw && (sw.members || []).some(
            m => m.kind === owner.kind && m.id === owner.id
                && m.socket === n));
    }

    // The lit sockets on one unit - what its bracket spans.
    _traySweepSocketsOn(kind, id) {
        const sw = this._traySweep;
        return ((sw && sw.members) || [])
            .filter(m => m.kind === kind && m.id === id)
            .map(m => m.socket);
    }

    _traySweepOwnerOf(el) {
        const grid = el && el.closest
            ? el.closest('.hw-dock-grid[data-lrd-snake-owner]') : null;
        if (!grid) return null;
        const [kind, id] = grid.dataset.lrdSnakeOwner.split(':');
        return { kind, id, grid };
    }

    // Every port chip in the tray, in the order they sit - the line a
    // sweep's range is taken along. Read at sweep start, so the tray's
    // rebuilds during the drag cannot renumber it under the mouse.
    _traySweepOrder() {
        const host = document.getElementById('hardware-dock-body');
        const out = [];
        if (!host) return out;
        host.querySelectorAll('.hw-dock-grid[data-lrd-snake-owner]')
            .forEach(grid => {
                const [kind, id] = grid.dataset.lrdSnakeOwner.split(':');
                grid.querySelectorAll(':scope > .lrd-tile').forEach(t => {
                    const socket = parseInt(
                        (t.dataset.lrdTile || '').split('-').pop(), 10);
                    if (Number.isFinite(socket)) out.push({ kind, id, socket });
                });
            });
        return out;
    }

    _traySweepIndex(order, member) {
        return order.findIndex(m => m.kind === member.kind
            && m.id === member.id && m.socket === member.socket);
    }

    _traySweepStart(e, payload, el) {
        const at = this._traySweepOwnerOf(el);
        if (!at) return;
        const anchor = { kind: at.kind, id: at.id,
                         socket: parseInt(payload.port, 10) };
        this._traySweepClear(false);
        this._traySweep = {
            anchor, members: [anchor], order: this._traySweepOrder(),
        };
        this._traySweepPaint();
        const move = (ev) => this._traySweepExtend(ev.clientX, ev.clientY);
        const up = () => {
            document.removeEventListener('mousemove', move);
            document.removeEventListener('mouseup', up);
            // The press that armed the sweep still synthesizes a click on
            // the chip face, and that click would open the chip's editor
            // nobody asked for - swallow exactly that one (the drag's own
            // trick), lifted on the next macrotask.
            const swallow = (ce) => {
                ce.stopPropagation();
                ce.preventDefault();
            };
            document.addEventListener('click', swallow, true);
            setTimeout(() => {
                document.removeEventListener('click', swallow, true);
            }, 0);
        };
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
        this._traySweepArmKeys();
    }

    _traySweepExtend(clientX, clientY) {
        const sw = this._traySweep;
        if (!sw) return;
        const el = document.elementFromPoint(clientX, clientY);
        const chip = el && el.closest ? el.closest('[data-hwdock^="port-"]') : null;
        if (!chip) return;
        const payload = this._dockChipPayload(chip);
        const at = this._traySweepOwnerOf(chip);
        if (!payload || !at) return;
        const ai = this._traySweepIndex(sw.order, sw.anchor);
        const ci = this._traySweepIndex(sw.order, {
            kind: at.kind, id: at.id, socket: parseInt(payload.port, 10) });
        if (ai < 0 || ci < 0) return;
        const lo = Math.min(ai, ci);
        const hi = Math.max(ai, ci);
        const next = sw.order.slice(lo, hi + 1);
        const same = next.length === sw.members.length
            && next.every((m, i) => m.kind === sw.members[i].kind
                && m.id === sw.members[i].id
                && m.socket === sw.members[i].socket);
        if (same) return;
        sw.members = next;
        this._traySweepPaint();
    }

    // Light the gathered chips in place and re-place the brackets, without
    // rebuilding the tray under the moving mouse.
    _traySweepPaint() {
        const body = document.getElementById('hardware-dock-body');
        if (!body) return;
        const sw = this._traySweep;
        body.querySelectorAll('.hw-dock-chip-sel')
            .forEach(t => t.classList.remove('hw-dock-chip-sel'));
        if (sw && sw.members.length) {
            // Every unit the range reaches lights its own share of it.
            body.querySelectorAll('.hw-dock-grid[data-lrd-snake-owner]')
                .forEach(grid => {
                    const [kind, id] = grid.dataset.lrdSnakeOwner.split(':');
                    const lit = new Set(this._traySweepSocketsOn(kind, id));
                    if (!lit.size) return;
                    grid.querySelectorAll(':scope > .lrd-tile').forEach(t => {
                        const n = parseInt(
                            (t.dataset.lrdTile || '').split('-').pop(), 10);
                        if (lit.has(n)) t.classList.add('hw-dock-chip-sel');
                    });
                });
        }
        this._dockPlaceSnakeBrackets(body);
    }

    _traySweepClear(paint = true) {
        if (!this._traySweep) return;
        this._traySweep = null;
        this._traySweepDisarmKeys();
        if (paint) this._traySweepPaint();
    }

    _traySweepArmKeys() {
        if (this._traySweepKeyHandler) return;
        this._traySweepKeyHandler = (e) => {
            if (!this._traySweep) return;
            const a = document.activeElement;
            const typing = a && (a.tagName === 'INPUT'
                || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT');
            if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                this._traySweepClear();
                return;
            }
            if (e.key === 'Enter' && e.altKey && !typing) {
                e.preventDefault();
                e.stopPropagation();
                this._traySweepSnake();
            }
        };
        // A plain press anywhere but on a lit chip or the menu drops the
        // selection - the canvas sweep's own rule.
        this._traySweepDownHandler = (e) => {
            if (!this._traySweep || e.button !== 0 || e.altKey) return;
            const t = e.target;
            if (t && t.closest && (t.closest('#context-menu')
                    || t.closest('.hw-dock-chip-sel'))) return;
            this._traySweepClear();
        };
        document.addEventListener('keydown', this._traySweepKeyHandler, true);
        document.addEventListener('mousedown', this._traySweepDownHandler, true);
    }

    _traySweepDisarmKeys() {
        if (this._traySweepKeyHandler) {
            document.removeEventListener('keydown', this._traySweepKeyHandler, true);
            this._traySweepKeyHandler = null;
        }
        if (this._traySweepDownHandler) {
            document.removeEventListener('mousedown', this._traySweepDownHandler, true);
            this._traySweepDownHandler = null;
        }
    }

    // Form the snake from the parked selection: ONE 'Snake Ports' entry;
    // resolves to the new snake's id.
    _traySweepSnake() {
        const sw = this._traySweep;
        if (!sw || !sw.members.length) return Promise.resolve(null);
        const members = sw.members.slice();
        this._traySweepClear(false);
        sendClientLog('data_snake_ports', {
            owners: [...new Set(members.map(m => m.id))],
            sockets: members.map(m => m.socket),
        });
        return this.snakePorts(members).then(id => {
            if (window.canvasRenderer) window.canvasRenderer.render();
            return id;
        });
    }

    // Open the owner's sheet and land focus on one of its fields (a
    // snake's ft or name) - the prompt-free "Set home run…" / "Rename".
    _dataCableFocusField(owner, key) {
        this._setDataCableSheetOpen(owner, true);
        this.renderHardwareDock();
        const el = document.querySelector(`[data-lrd-field="${key}"]`);
        if (!el) return;
        this._dockRevealSections(el);
        el.focus();
        if (typeof el.select === 'function') el.select();
    }

    // The context menu's snake entries. Armed on a lit chip (the sweep's
    // selection), on a snake's tag, or on a chip that rides a snake -
    // each entry names its own deal and runs through the model's one-PUT
    // writes. Null everywhere else.
    _prepareSnakeMenu(x, y) {
        const el = document.elementFromPoint(x, y);
        if (!el || !el.closest || !el.closest('#hardware-dock')) return null;
        const bracket = el.closest('.hw-dock-snake[data-lrd-snake-id]');
        const chip = el.closest('[data-hwdock^="port-"]');
        const sw = this._traySweep;
        const entries = [];
        const snakeEntries = (owner, snake) => {
            const name = snake.name || 'snake';
            const across = this.snakeSpansOwners(snake)
                ? ' It crosses cards or boxes; one edit reaches all of it.'
                : '';
            entries.push({
                label: `Rename ${name}`,
                title: `Open the sheet on the snake’s name.${across}`,
                run: () => this._dataCableFocusField(owner,
                    `data-snake-name-${owner.id}-${snake.id}`),
            });
            entries.push({
                label: `Set home run of ${name}…`,
                title: `Open the sheet on the snake’s length.${across}`,
                run: () => this._dataCableFocusField(owner,
                    `data-snake-ft-${owner.id}-${snake.id}`),
            });
            entries.push({
                label: `Unsnake ${name}`,
                title: `Take every port out of ${name}, wherever it sits; `
                    + 'the ports stay where they are. One undo step.',
                run: () => {
                    sendClientLog('data_loosen_snake',
                                  { owner: owner.id, snake: snake.id });
                    this._traySweepClear(false);
                    this.loosenPorts(null, snake.id).then(() => {
                        if (window.canvasRenderer) window.canvasRenderer.render();
                    });
                },
            });
        };
        if (bracket) {
            const [kind, id] = bracket.dataset.lrdSnakeOwner.split(':');
            const owner = this._dataCableOwner(kind, id);
            const snake = owner
                && this.getShowSnake(bracket.dataset.lrdSnakeId);
            if (!snake) return null;
            snakeEntries(owner, snake);
            return { entries };
        }
        if (!chip) return null;
        const at = this._traySweepOwnerOf(chip);
        const payload = this._dockChipPayload(chip);
        if (!at || !payload) return null;
        const owner = this._dataCableOwner(at.kind, at.id);
        if (!owner) return null;
        const socket = parseInt(payload.port, 10);
        // The lit range, whole - it can reach across units now, so the
        // menu speaks for every chip in it, not for this grid's share.
        const lit = this._traySweepHas(owner, socket)
            ? (sw.members || []).slice() : null;
        if (lit) {
            const n = lit.length;
            const inside = lit.map(m => {
                const at2 = this._dataCableOwner(m.kind, m.id);
                return at2 ? this.dataPortSnake(at2, m.socket) : null;
            });
            const oneSnake = inside[0] && inside.every(
                s => s && s.id === inside[0].id);
            const whole = oneSnake
                && (inside[0].members || []).length === n;
            const across = new Set(lit.map(m => `${m.kind}:${m.id}`)).size > 1;
            if (!whole) {
                entries.push({
                    label: `Snake these ${n}`,
                    shortcut: 'Alt+Enter',
                    title: `Form one snake of the ${n} lit ports`
                        + (across ? ', across the cards and boxes they sit '
                            + 'on' : '')
                        + ' - one name, one home run. Alt+Enter does the '
                        + 'same. One undo step.',
                    run: () => this._traySweepSnake(),
                });
            }
            entries.push({
                label: 'Set home run…',
                title: whole
                    ? 'Open the sheet on the snake’s length.'
                    : 'Snake the lit ports, then open the sheet on the '
                        + 'new snake’s length.',
                run: () => {
                    if (whole) {
                        this._traySweepClear(false);
                        this._dataCableFocusField(owner,
                            `data-snake-ft-${owner.id}-${inside[0].id}`);
                        return;
                    }
                    this._traySweepSnake().then(id => {
                        if (!id) return;
                        this._dataCableFocusField(owner,
                            `data-snake-ft-${owner.id}-${id}`);
                    });
                },
            });
            if (inside.some(Boolean)) {
                entries.push({
                    label: n === 1 ? 'Unsnake' : `Unsnake these ${n}`,
                    title: 'Take the lit ports out of their snakes; the '
                        + 'ports stay where they are. One undo step.',
                    run: () => {
                        this._traySweepClear(false);
                        this.loosenPorts(lit).then(() => {
                            if (window.canvasRenderer) window.canvasRenderer.render();
                        });
                    },
                });
            }
            return { entries, scope: 'selection' };
        }
        const snake = this.dataPortSnake(owner, socket);
        if (!snake) return null;
        snakeEntries(owner, snake);
        return { entries };
    }
}

for (const k of Object.getOwnPropertyNames(_DockSweep.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_DockSweep.prototype, k));
    }
}
