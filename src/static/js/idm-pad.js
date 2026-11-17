// idm-pad: the game controller map for the IDM Locator, one table for the
// computer (app-idm-gamepad.js) and the phone page (idm-phone.js). No
// imports and nothing on the page: both load it as it is.
//
// The browser's Gamepad API reads a PlayStation or Xbox pad in its
// "standard" layout, the same button numbers for both makes. PAD_MAP below
// says what each button does; a host (the computer's tab, the phone page)
// gives each action its own code, and idmPadDispatch runs the one a press
// asks for. To give a button a job, add a row to PAD_MAP (and, for a new
// job, its name to PAD_ACTIONS and its code to each host): the panel's
// button list and the phone's are built from the table.
//
//   D-pad, left stick      move one module (held: a short wait, then a
//                          steady repeat); with LB / L1 or RB / R1 held,
//                          one cabinet
//   A / Cross              mark or clear the highlighted module; held while
//                          moving, every module passed takes the first
//                          module's change (mark or clear, never both)
//   B / Circle             undo
//   X / Square             the next field color
//   Y / Triangle           the next screen on this canvas
//   View / Share           the next canvas
//
// Moves stay on the canvas the highlight is on (owner, 2026-11-17); only
// the next-canvas button takes it to another one.

// The standard layout's button numbers.
export const PAD_BUTTONS = {
    A: 0, B: 1, X: 2, Y: 3, LB: 4, RB: 5, LT: 6, RT: 7, VIEW: 8, MENU: 9,
    LS: 10, RS: 11, UP: 12, DOWN: 13, LEFT: 14, RIGHT: 15, HOME: 16,
};
// A held direction: the first step at once, the next after REPEAT_DELAY_MS,
// then one every REPEAT_EVERY_MS. The stick counts past DEADZONE.
export const REPEAT_DELAY_MS = 350;
export const REPEAT_EVERY_MS = 90;
export const DEADZONE = 0.5;
// X / Square walks the field through the quick colors.
export const FIELD_CYCLE = ['#ffffff', '#ff0000', '#00ff00', '#0000ff', '#000000'];

// Every job a button can be given, with the words the button list shows.
// One that no row of PAD_MAP names is built and waits for a button.
export const PAD_ACTIONS = {
    mark: 'Mark or clear; hold and move to paint',
    undo: 'Undo',
    fieldColor: 'Next field color',
    nextScreen: 'Next screen on this canvas',
    nextCanvas: 'Next canvas',
    clearHighlight: 'Clear the highlight',
};

// Which button does which job: {button: a PAD_BUTTONS name, label: how the
// button list names it, action: a PAD_ACTIONS name}.
export const PAD_MAP = [
    { button: 'A', label: 'A / Cross', action: 'mark' },
    { button: 'B', label: 'B / Circle', action: 'undo' },
    { button: 'X', label: 'X / Square', action: 'fieldColor' },
    { button: 'Y', label: 'Y / Triangle', action: 'nextScreen' },
    { button: 'VIEW', label: 'View / Share', action: 'nextCanvas' },
];

// The moves, which no table row changes: the list shows them first.
const MOVE_ROWS = [
    { label: 'D-pad, left stick', text: 'Move one module' },
    { label: 'Hold LB / L1 or RB / R1', text: 'Move one cabinet' },
];

// The button list as the panel and the phone show it: [{label, text}].
export function idmPadHelpRows() {
    return MOVE_ROWS.concat(PAD_MAP.map(row => ({ label: row.label, text: PAD_ACTIONS[row.action] || row.action })));
}

// The job a button number has, or null.
export function idmPadActionOf(button) {
    const row = PAD_MAP.find(r => PAD_BUTTONS[r.button] === button);
    return row ? row.action : null;
}

function pressed(pad, i) {
    const b = pad && pad.buttons ? pad.buttons[i] : null;
    if (!b) return false;
    return typeof b === 'object' ? !!b.pressed || Number(b.value) > 0.5 : Number(b) > 0.5;
}

// The direction the pad holds: the D-pad first, then the left stick past
// the deadzone along its stronger axis. 'up' | 'down' | 'left' | 'right' |
// null.
export function idmPadDirection(pad) {
    if (!pad) return null;
    if (pressed(pad, PAD_BUTTONS.UP)) return 'up';
    if (pressed(pad, PAD_BUTTONS.DOWN)) return 'down';
    if (pressed(pad, PAD_BUTTONS.LEFT)) return 'left';
    if (pressed(pad, PAD_BUTTONS.RIGHT)) return 'right';
    const axes = pad.axes || [];
    const x = Number(axes[0]) || 0, y = Number(axes[1]) || 0;
    if (Math.max(Math.abs(x), Math.abs(y)) < DEADZONE) return null;
    if (Math.abs(x) >= Math.abs(y)) return x > 0 ? 'right' : 'left';
    return y > 0 ? 'down' : 'up';
}

// One frame of one pad: what it asks for, from what it held last frame
// (`prev`, {buttons: [bool], dir, nextAt} or null) and the time `now` in
// ms. Returns {state, actions}; each action is {type: 'move', dir, cabinet}
// or {type: 'press' | 'release', button}. Pure, so the repeat and the
// button edges are tested apart from the app.
export function idmPadFrame(prev, pad, now) {
    const was = prev || { buttons: [], dir: null, nextAt: 0 };
    const buttons = [];
    const n = Math.max((pad && pad.buttons ? pad.buttons.length : 0), was.buttons.length);
    for (let i = 0; i < n; i++) buttons.push(pressed(pad, i));
    const actions = [];
    // Presses and releases first, so A pressed with a move this frame marks
    // the module it started on, then paints the next.
    for (let i = 0; i < buttons.length; i++) {
        if (i >= PAD_BUTTONS.UP && i <= PAD_BUTTONS.RIGHT) continue;
        if (buttons[i] && !was.buttons[i]) actions.push({ type: 'press', button: i });
        else if (!buttons[i] && was.buttons[i]) actions.push({ type: 'release', button: i });
    }
    const dir = idmPadDirection(pad);
    const cabinet = buttons[PAD_BUTTONS.LB] || buttons[PAD_BUTTONS.RB];
    let nextAt = was.nextAt;
    if (dir && dir !== was.dir) {
        actions.push({ type: 'move', dir, cabinet });
        nextAt = now + REPEAT_DELAY_MS;
    } else if (dir && now >= was.nextAt) {
        actions.push({ type: 'move', dir, cabinet });
        // a late frame never fires a burst: the next step is a beat on
        nextAt = Math.max(was.nextAt + REPEAT_EVERY_MS, now + REPEAT_EVERY_MS / 2);
    }
    return { state: { buttons, dir, nextAt: dir ? nextAt : 0 }, actions };
}

// One action from idmPadFrame run on a host: `host.move(dir, cabinet)` for
// a move, `host[job].press()` / `.release()` (or `host[job]()` for a press)
// for a button with a job. A job the host has no code for does nothing.
export function idmPadDispatch(host, a) {
    if (!host || !a) return;
    if (a.type === 'move') {
        if (typeof host.move === 'function') host.move(a.dir, !!a.cabinet);
        return;
    }
    const job = idmPadActionOf(a.button);
    const fn = job ? host[job] : null;
    if (!fn) return;
    if (typeof fn === 'function') {
        if (a.type === 'press') fn.call(host);
        return;
    }
    const step = a.type === 'press' ? fn.press : fn.release;
    if (typeof step === 'function') step.call(fn);
}

// The pad's name without the browser's vendor and product tail.
export function idmPadName(id) {
    const text = String(id || '').trim();
    const cut = text.search(/\s*\((?:STANDARD GAMEPAD|Vendor|vendor)/);
    const name = (cut > 0 ? text.slice(0, cut) : text).trim();
    return name || 'Controller';
}

// Builds the button list into `dl` (a <dl>): one <dt>/<dd> per row.
export function idmPadFillHelp(dl) {
    if (!dl) return;
    dl.innerHTML = '';
    idmPadHelpRows().forEach(row => {
        const dt = document.createElement('dt');
        dt.textContent = row.label;
        const dd = document.createElement('dd');
        dd.textContent = row.text;
        dl.appendChild(dt);
        dl.appendChild(dd);
    });
}
