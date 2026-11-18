// controls.js - the keys and the 3D mouse, as the person has set them in
// Preferences > Controls (the owner's rulings, 2026-11-18).
//
// Plain functions, no DOM: the page loads this as a classic script
// (window.Controls) before canvas-input.js, the app's modules read it
// through window.Controls, and tests/test_controls.py runs it under node.
//
// A key is written as a CHORD: the modifiers in a fixed order, then the
// key's physical code, joined by '+'. 'mod' is the platform's command key
// (Cmd on a Mac, Ctrl elsewhere), so one chord reads right on both:
// 'mod+shift+Digit1' is Cmd+Shift+1 on a Mac and Ctrl+Shift+1 on Windows.
// 'ctrl' is the Mac's Control key and 'meta' the Windows key; neither
// occurs on the other platform.
//
// What is stored (preferences.controls, the same record as every other
// preference, never the show): only what the person changed.
//   { keys: { <action id>: [chord, ...] },
//     mouse3d: { preset: 'standard' | 'orbitFirst',
//                actions: { <mouse action>: { button, mod } } } }
// An action not in `keys` has its shipped keys; an empty list is an
// action with no key at all.
const Controls = (() => {
    const AREAS = ['General', 'Pixel Map', 'Data', 'Power', 'Header/Footer', '3D', 'IDM Locator'];

    // Where an area's keys act: 'all' on every tab, else the one view
    // (canvasRenderer.viewMode, or '3d'). Two actions can share a key
    // only when they never act on the same tab.
    const SCOPE = {
        'General': 'all', 'Pixel Map': 'pixel-map', 'Data': 'data-flow', 'Power': 'power',
        'Header/Footer': 'rigging', '3D': '3d', 'IDM Locator': 'idm',
    };

    // Every rebindable action, in the order the Controls tab lists them.
    // `loose`: the command key may be either Cmd or Ctrl (these always
    // answered to both); `byKey`: the letter or digit typed counts as well
    // as the physical key (the 3D keys always read the typed letter).
    const ACTIONS = [
        { id: 'undo', area: 'General', label: 'Undo', keys: ['mod+KeyZ'], loose: true },
        { id: 'redo', area: 'General', label: 'Redo', keys: ['mod+shift+KeyZ'], loose: true },
        { id: 'copy', area: 'General', label: 'Copy', keys: ['mod+KeyC'], loose: true },
        { id: 'paste', area: 'General', label: 'Paste', keys: ['mod+KeyV'], loose: true },
        { id: 'duplicate', area: 'General', label: 'Duplicate', keys: ['mod+KeyJ'], loose: true },
        { id: 'selectAll', area: 'General', label: 'Select all', keys: ['mod+KeyA'] },
        { id: 'preferences', area: 'General', label: 'Open Preferences', keys: ['mod+Comma'], loose: true },
        { id: 'open', area: 'General', label: 'Open a project file', keys: ['mod+KeyO'] },
        { id: 'save', area: 'General', label: 'Save the project', keys: ['mod+KeyS'] },
        { id: 'exportPng', area: 'General', label: 'Export PNG', keys: ['alt+KeyS'] },
        { id: 'exportPsd', area: 'General', label: 'Export PSD', keys: ['mod+alt+KeyS'] },
        { id: 'fitToView', area: 'General', label: 'Fit to view', keys: ['mod+shift+Digit1'], loose: true },
        { id: 'zoomToSelection', area: 'General', label: 'Zoom to selection (1:1)', keys: ['mod+shift+Digit2'], loose: true },
        { id: 'toggleSnap', area: 'General', label: 'Toggle snap', keys: ['mod+shift+Quote'], loose: true },
        // `anyMods`: Delete or Backspace set with no modifier answers with
        // any held, as Delete always did on these three tabs (any other key
        // set here matches exactly).
        { id: 'deleteScreen', area: 'Pixel Map', label: 'Delete the selected screen', keys: ['Delete', 'Backspace'], anyMods: true },
        { id: 'nextPort', area: 'Data', label: 'Next port in custom mode', keys: ['Tab', 'BracketRight'] },
        { id: 'prevPort', area: 'Data', label: 'Previous port in custom mode', keys: ['shift+Tab', 'BracketLeft'] },
        { id: 'snakePorts', area: 'Data', label: 'Snake the lit ports', keys: ['alt+Enter'] },
        { id: 'nextCircuit', area: 'Power', label: 'Next circuit in custom mode', keys: ['Tab', 'BracketRight'] },
        { id: 'prevCircuit', area: 'Power', label: 'Previous circuit in custom mode', keys: ['shift+Tab', 'BracketLeft'] },
        { id: 'removeBars', area: 'Header/Footer', label: 'Take off the clicked or selected bars', keys: ['Delete', 'Backspace'], anyMods: true },
        { id: 'frame3d', area: '3D', label: 'Frame the selected screens', keys: ['KeyF'], byKey: true },
        { id: 'home3d', area: '3D', label: 'Go back to the starting view', keys: ['Home'] },
        { id: 'viewFront', area: '3D', label: 'Front view', keys: ['Digit1'], byKey: true },
        { id: 'viewBack', area: '3D', label: 'Back view', keys: ['Digit2'], byKey: true },
        { id: 'viewLeft', area: '3D', label: 'Left view', keys: ['Digit3'], byKey: true },
        { id: 'viewRight', area: '3D', label: 'Right view', keys: ['Digit4'], byKey: true },
        { id: 'viewTop', area: '3D', label: 'Top view', keys: ['Digit5'], byKey: true },
        { id: 'viewIso', area: '3D', label: 'Iso view', keys: ['Digit6'], byKey: true },
        { id: 'moveHandles', area: '3D', label: 'Move handles', keys: ['KeyW'], byKey: true },
        { id: 'rotateHandles', area: '3D', label: 'Rotate handles', keys: ['KeyE'], byKey: true },
        { id: 'grab3d', area: '3D', label: 'Move the selection with the mouse', keys: ['KeyG'], byKey: true },
        { id: 'turn3d', area: '3D', label: 'Turn the selection with the mouse', keys: ['KeyR'], byKey: true },
        { id: 'clearMark', area: 'IDM Locator', label: 'Clear the mark', keys: ['Delete', 'Backspace'], anyMods: true },
    ];
    const BY_ID = new Map(ACTIONS.map(a => [a.id, a]));

    // The keys that work the same everywhere and are never rebound: listed
    // on the Controls tab so nobody looks for them in vain.
    const FIXED = [
        { keys: 'Enter', what: 'Ends the edit in a field, keeps a redraw, next guide step' },
        { keys: 'Esc', what: 'Closes what is on top, cancels a drag or a recording' },
        { keys: 'Space', what: 'Hold to pan; on the IDM Locator a tap marks the module' },
        { keys: 'Arrow keys, Page Up, Page Down', what: 'Move in their own direction: draw a custom run, nudge in 3D, step the IDM highlight' },
        { keys: 'Tab in a field', what: 'Moves to the next field' },
        { keys: 'Hold Alt', what: 'Lights the run under the cursor in Data and Power' },
        { keys: 'X, Y, Z while moving with G or R', what: 'Lock to that axis' },
    ];

    const MODIFIER_CODES = new Set(['ShiftLeft', 'ShiftRight', 'ControlLeft', 'ControlRight',
        'AltLeft', 'AltRight', 'MetaLeft', 'MetaRight', 'OSLeft', 'OSRight', 'CapsLock', 'Fn']);
    const MOD_ORDER = ['mod', 'ctrl', 'meta', 'alt', 'shift'];

    const PUNCT = {
        ',': 'Comma', '.': 'Period', '/': 'Slash', ';': 'Semicolon', "'": 'Quote',
        '[': 'BracketLeft', ']': 'BracketRight', '\\': 'Backslash', '-': 'Minus',
        '=': 'Equal', '`': 'Backquote', ' ': 'Space',
    };
    const KEY_NAMES = {
        Comma: ',', Period: '.', Slash: '/', Semicolon: ';', Quote: "'", BracketLeft: '[',
        BracketRight: ']', Backslash: '\\', Minus: '-', Equal: '=', Backquote: '`',
        ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right',
        PageUp: 'Page Up', PageDown: 'Page Down', Escape: 'Esc', Space: 'Space',
        Delete: 'Delete', Backspace: 'Backspace', Enter: 'Enter', Tab: 'Tab', Home: 'Home',
        End: 'End', Insert: 'Insert',
    };

    // The keypad's digits are the row's digits, and its Enter is Enter.
    function normCode(code) {
        const s = String(code || '');
        const pad = /^Numpad([0-9])$/.exec(s);
        if (pad) return 'Digit' + pad[1];
        if (s === 'NumpadEnter') return 'Enter';
        return s;
    }

    // The code a typed character stands for (an event with no code, and
    // the 3D keys, which read the letter typed).
    function keyToCode(key) {
        const k = String(key || '');
        if (/^[a-z]$/i.test(k)) return 'Key' + k.toUpperCase();
        if (/^[0-9]$/.test(k)) return 'Digit' + k;
        if (PUNCT[k]) return PUNCT[k];
        if (k === 'Esc') return 'Escape';
        if (k.length > 1 && /^[A-Z]/.test(k)) return k;   // Delete, Home, F5 ...
        return '';
    }

    function parse(chord) {
        const parts = String(chord || '').split('+');
        // '+' itself is no key here, so the last part is always the code.
        const out = { mod: false, ctrl: false, meta: false, alt: false, shift: false, code: '' };
        parts.forEach((p, i) => {
            if (i === parts.length - 1) out.code = normCode(p);
            else if (MOD_ORDER.includes(p)) out[p] = true;
        });
        return out;
    }

    function join(c) {
        return MOD_ORDER.filter(m => c[m]).concat([c.code]).join('+');
    }

    // A chord as stored: modifiers in order, a known code. '' for junk.
    function normalize(chord) {
        if (typeof chord !== 'string' || !chord) return '';
        const c = parse(chord);
        if (!c.code || MODIFIER_CODES.has(c.code) || !/^[A-Za-z0-9]+$/.test(c.code)) return '';
        return join(c);
    }

    // The chord a key press makes, or null for a modifier on its own. `byKey`
    // (the 3D keys): a letter is the letter typed, whatever key makes it on
    // this keyboard's layout.
    function fromEvent(e, isMac, byKey) {
        const typed = byKey ? keyToCode(e.key) : '';
        const code = (/^Key[A-Z]$/.test(typed) ? typed : '') || normCode(e.code) || keyToCode(e.key);
        if (!code || MODIFIER_CODES.has(code) || /^(Shift|Control|Alt|Meta|OS)$/.test(code)) return null;
        return join({
            mod: !!(isMac ? e.metaKey : e.ctrlKey),
            ctrl: !!(isMac && e.ctrlKey),
            meta: !!(!isMac && e.metaKey),
            alt: !!e.altKey,
            shift: !!e.shiftKey,
            code,
        });
    }

    // Does this key press make `chord`? The modifiers must be exactly the
    // chord's. `opts.loose`: Cmd and Ctrl both count as the command key.
    // `opts.byKey`: a letter is the letter typed, never the physical key
    // (on another layout the key in the F place types something else, as
    // the 3D keys always read it); a digit is either.
    // `opts.anyMods`: Delete or Backspace with no modifier answers with any
    // held.
    function eventMatches(e, chord, isMac, opts = {}) {
        const c = parse(chord);
        if (!c.code) return false;
        let codes = [normCode(e.code)];
        if (opts.byKey && /^Key[A-Z]$/.test(c.code)) codes = [keyToCode(e.key)];
        else if (opts.byKey || !e.code) codes.push(keyToCode(e.key));
        if (!codes.includes(c.code)) return false;
        if (anyModsKey(opts, c)) return true;
        let mod = !!(isMac ? e.metaKey : e.ctrlKey);
        let ctrl = !!(isMac && e.ctrlKey);
        let meta = !!(!isMac && e.metaKey);
        if (opts.loose && !c.ctrl && !c.meta) {
            mod = !!(e.metaKey || e.ctrlKey);
            ctrl = false;
            meta = false;
        }
        return mod === c.mod && ctrl === c.ctrl && meta === c.meta
            && !!e.altKey === c.alt && !!e.shiftKey === c.shift;
    }

    // ── what the person has set ───────────────────────────────────────────

    // Each action's keys: the person's where they set them, else shipped.
    function keysFor(user, id) {
        const a = BY_ID.get(id);
        if (!a) return [];
        const set = user && user.keys && user.keys[id];
        if (Array.isArray(set)) {
            const out = [];
            set.forEach(k => { const n = normalize(k); if (n && !out.includes(n)) out.push(n); });
            return out;
        }
        return a.keys.slice();
    }

    function matches(e, id, user, isMac) {
        const a = BY_ID.get(id);
        if (!a) return false;
        return keysFor(user, id).some(k => eventMatches(e, k, isMac, a));
    }

    // A plain Delete or Backspace on an action that answers with any
    // modifier held.
    function anyModsKey(a, c) {
        return !!(a && a.anyMods) && (c.code === 'Delete' || c.code === 'Backspace')
            && !c.mod && !c.ctrl && !c.meta && !c.alt && !c.shift;
    }

    // The command key of a Cmd-or-Ctrl action read as a Mac's Control too:
    // 'ctrl+KeyZ' is that action's 'mod+KeyZ'.
    function loosened(chord) {
        const c = parse(chord);
        if (c.ctrl && !c.mod) { c.ctrl = false; c.mod = true; }
        return join(c);
    }

    // Do key `ka` of action `a` and key `kb` of action `b` answer the same
    // press? The same chord; a plain Delete that answers with any modifier
    // and any chord on Delete; a Mac's Control+key and a Cmd-or-Ctrl
    // action's key.
    function clash(a, ka, b, kb) {
        if (ka === kb) return true;
        const ca = parse(ka), cb = parse(kb);
        if (ca.code === cb.code && (anyModsKey(a, ca) || anyModsKey(b, cb))) return true;
        if (loosened(ka) === loosened(kb)) {
            // a Cmd-or-Ctrl action whose own key is the command key one
            return !!((a.loose && !ca.ctrl && !ca.meta) || (b.loose && !cb.ctrl && !cb.meta));
        }
        return false;
    }

    function overlaps(a, b) {
        const sa = SCOPE[a.area], sb = SCOPE[b.area];
        return sa === 'all' || sb === 'all' || sa === sb;
    }

    // The other actions that already answer to `chord` where `id` acts.
    function conflicts(user, id, chord) {
        const a = BY_ID.get(id);
        const n = normalize(chord);
        if (!a || !n) return [];
        return ACTIONS.filter(b => b.id !== id && overlaps(a, b)
            && keysFor(user, b.id).some(k => clash(a, n, b, k)))
            .map(b => b.id);
    }

    function isDefault(user, id) {
        const a = BY_ID.get(id);
        return !!a && JSON.stringify(keysFor(user, id)) === JSON.stringify(a.keys);
    }

    // A copy of `user` with `id` given `keys` (null: back to shipped).
    // Shipped keys are not stored.
    function withKeys(user, id, keys) {
        const out = clone(user);
        const a = BY_ID.get(id);
        if (!a) return out;
        const list = keys == null ? null : keys.map(normalize).filter(Boolean)
            .filter((k, i, all) => all.indexOf(k) === i);
        if (list === null || JSON.stringify(list) === JSON.stringify(a.keys)) delete out.keys[id];
        else out.keys[id] = list;
        return out;
    }

    // ── keys that cannot be used ─────────────────────────────────────────

    // Kept by the browser or the system: the page never sees them, or not
    // every time. Refused with a short note.
    const RESERVED_ALL = ['mod+KeyW', 'mod+KeyT', 'mod+KeyN', 'mod+shift+KeyN', 'mod+shift+KeyT',
        'mod+shift+KeyW', 'mod+Tab', 'mod+shift+Tab', 'mod+PageUp', 'mod+PageDown',
        'mod+Digit1', 'mod+Digit2', 'mod+Digit3', 'mod+Digit4', 'mod+Digit5', 'mod+Digit6',
        'mod+Digit7', 'mod+Digit8', 'mod+Digit9'];
    const RESERVED_MAC = ['mod+KeyQ', 'mod+KeyH', 'mod+KeyM', 'mod+alt+KeyH', 'mod+alt+KeyM',
        'mod+Space', 'mod+Backquote', 'mod+alt+Escape', 'mod+shift+Digit3', 'mod+shift+Digit4',
        'mod+shift+Digit5', 'ctrl+Space', 'mod+ctrl+KeyF', 'mod+ctrl+KeyQ', 'mod+shift+KeyQ'];
    const RESERVED_WIN = ['alt+F4', 'mod+F4', 'alt+Tab', 'alt+shift+Tab', 'mod+alt+Delete',
        'mod+shift+Escape', 'mod+Escape', 'alt+Space', 'alt+Escape', 'F11'];

    // '' when `chord` can be used; else the reason, in a few plain words.
    function refusal(chord, isMac) {
        const n = normalize(chord);
        if (!n) return 'That key cannot be used.';
        const c = parse(n);
        const name = format(n, isMac);
        const onlyShift = !c.mod && !c.ctrl && !c.meta && !c.alt;
        if (c.code === 'Escape') return 'Esc is fixed: it closes what is on top and cancels.';
        if (c.code === 'Enter' && onlyShift) return 'Enter is fixed: it ends an edit.';
        if (c.code === 'Space' && onlyShift) return 'Space is fixed: hold it to pan.';
        if (/^(Arrow(Up|Down|Left|Right)|PageUp|PageDown)$/.test(c.code) && onlyShift) {
            return 'The arrow keys are fixed: they move in their own direction.';
        }
        if (c.meta) return `${name} belongs to Windows, so the app can't use it.`;
        const reserved = RESERVED_ALL.concat(isMac ? RESERVED_MAC : RESERVED_WIN);
        if (reserved.includes(n)) return `${name} belongs to the browser or the system, so the app can't use it.`;
        return '';
    }

    // ── names ─────────────────────────────────────────────────────────────

    function modNames(isMac) {
        return isMac
            ? { mod: 'Cmd', ctrl: 'Control', meta: 'Win', alt: 'Option', shift: 'Shift' }
            : { mod: 'Ctrl', ctrl: 'Control', meta: 'Win', alt: 'Alt', shift: 'Shift' };
    }

    function keyName(code) {
        if (KEY_NAMES[code]) return KEY_NAMES[code];
        let m = /^Key([A-Z])$/.exec(code);
        if (m) return m[1];
        m = /^Digit([0-9])$/.exec(code);
        if (m) return m[1];
        return code;
    }

    // 'mod+shift+Digit1' -> 'Ctrl+Shift+1' (Cmd+Shift+1 on a Mac).
    function format(chord, isMac) {
        const c = parse(chord);
        const names = modNames(isMac);
        return MOD_ORDER.filter(m => c[m]).map(m => names[m]).concat([keyName(c.code)]).join('+');
    }

    function formatList(chords, isMac) {
        return chords.map(k => format(k, isMac)).join(', ');
    }

    // ── the 3D mouse and trackpad ─────────────────────────────────────────

    const MOUSE_ACTIONS = [
        { id: 'orbit', label: 'Orbit' },
        { id: 'pan', label: 'Pan' },
        { id: 'zoom', label: 'Zoom' },
        { id: 'select', label: 'Select (click)' },
        { id: 'box', label: 'Box select' },
        { id: 'move', label: 'Move a selected screen' },
    ];
    const MOUSE_IDS = MOUSE_ACTIONS.map(a => a.id);
    const CAMERA = ['orbit', 'pan', 'zoom'];
    const BUTTONS = ['left', 'middle', 'right', 'none'];
    const MODS = ['none', 'shift', 'alt', 'mod'];

    const b = (button, mod = 'none') => ({ button, mod });
    // Each preset: one button and modifier per action, and the extra
    // gestures that come with it (a mouse with no middle button, Shift on
    // the middle button). An extra steps aside for any action set to the
    // same button and modifiers.
    const PRESETS = {
        // The 11-08 ruling: left selects, box-selects or moves; middle
        // orbits; right pans; the wheel zooms.
        standard: {
            label: 'Standard',
            actions: { orbit: b('middle'), pan: b('right'), zoom: b('wheel'),
                select: b('left'), box: b('left'), move: b('left') },
            extras: [
                { action: 'pan', button: 'middle', mods: ['shift'] },
                { action: 'orbit', button: 'left', mods: ['alt'] },
                { action: 'pan', button: 'left', mods: ['alt', 'shift'] },
            ],
        },
        // A left drag on empty stage orbits round the view's centre;
        // Shift (or Cmd / Ctrl) + drag draws the box; a drag on a selected
        // screen still moves it.
        orbitFirst: {
            label: 'Orbit first',
            actions: { orbit: b('left'), pan: b('right'), zoom: b('wheel'),
                select: b('left'), box: b('left', 'shift'), move: b('left') },
            extras: [
                { action: 'orbit', button: 'middle', mods: [] },
                { action: 'pan', button: 'middle', mods: ['shift'] },
                { action: 'orbit', button: 'left', mods: ['alt'] },
                { action: 'pan', button: 'left', mods: ['alt', 'shift'] },
            ],
        },
    };

    function validMouse(id, v) {
        if (!v || typeof v !== 'object') return null;
        const buttons = id === 'zoom' ? BUTTONS.concat(['wheel']) : BUTTONS;
        if (!buttons.includes(v.button) || !MODS.includes(v.mod)) return null;
        return { button: v.button, mod: v.button === 'wheel' ? 'none' : v.mod };
    }

    const sameBinding = (x, y) => x.button === y.button && x.mod === y.mod;

    // The 3D mouse as set: the preset, each action's button and modifier,
    // the preset's extras that still stand, and whether the person changed
    // any action from the preset.
    function mouseMap(user) {
        const m = (user && user.mouse3d) || {};
        const preset = PRESETS[m.preset] ? m.preset : 'standard';
        const p = PRESETS[preset];
        const actions = {};
        let custom = false;
        MOUSE_IDS.forEach(id => {
            const own = validMouse(id, m.actions && m.actions[id]);
            actions[id] = own || { ...p.actions[id] };
            if (own && !sameBinding(own, p.actions[id])) custom = true;
        });
        const taken = MOUSE_IDS.map(id => actions[id]).filter(x => x.button !== 'none');
        const extras = p.extras.filter(x => !taken.some(t => t.button === x.button
            && (t.mod === 'none' ? [] : [t.mod]).join() === x.mods.join()));
        return { preset, actions, extras, custom };
    }

    // Two actions may share a button and modifier when they never fight
    // for the same press: a click (select), a drag from a selected screen
    // (move) and one drag from empty space (orbit, pan, zoom or box).
    function mouseConflicts(user, id, binding) {
        const v = validMouse(id, binding);
        if (!v || v.button === 'none' || v.button === 'wheel') return [];
        if (!CAMERA.includes(id) && id !== 'box') return [];
        const map = mouseMap(user);
        return ['orbit', 'pan', 'zoom', 'box'].filter(o => o !== id && sameBinding(map.actions[o], v));
    }

    function withMouse(user, id, binding) {
        const out = clone(user);
        const preset = (out.mouse3d && PRESETS[out.mouse3d.preset]) ? out.mouse3d.preset : 'standard';
        out.mouse3d = { preset, actions: { ...((out.mouse3d && out.mouse3d.actions) || {}) } };
        const v = binding == null ? null : validMouse(id, binding);
        if (!v || sameBinding(v, PRESETS[preset].actions[id])) delete out.mouse3d.actions[id];
        else out.mouse3d.actions[id] = v;
        return out;
    }

    function withPreset(user, preset) {
        const out = clone(user);
        out.mouse3d = { preset: PRESETS[preset] ? preset : 'standard', actions: {} };
        return out;
    }

    // A press of the 3D view: what it does. `ev`: { button (0 left,
    // 1 middle, 2 right), shift, alt, mod (Cmd on a Mac, Ctrl elsewhere) }.
    //   null                     nothing of the mouse map's
    //   { camera: kind }         orbit / pan / zoom at once, from anywhere
    //   { pick: true, select, move, moveMod, box, defer }
    //                            a press that waits: a click selects when
    //                            `select`; a drag from a selected screen
    //                            moves it when `move`; a drag from empty
    //                            space is the `defer` camera move, else the
    //                            box when `box`; a drag from another screen
    //                            draws the box when `box`.
    // A modifier an action asks for must be held; the action asking for
    // the most wins. Shift and Cmd / Ctrl ride along on a click, a box or a
    // move (they add, or move up and down); Alt never does.
    function resolvePress(map, ev) {
        const bn = ['left', 'middle', 'right'][ev && ev.button];
        if (!bn) return null;
        const held = (mods) => mods.every(k => !!ev[k]);
        const list = [];
        MOUSE_IDS.forEach(id => {
            const x = map.actions[id];
            if (x && x.button === bn) list.push({ id, mods: x.mod === 'none' ? [] : [x.mod], user: true });
        });
        map.extras.forEach(x => { if (x.button === bn) list.push({ id: x.action, mods: x.mods, user: false }); });
        const plain = !ev.shift && !ev.alt && !ev.mod;
        const cams = list.filter(x => CAMERA.includes(x.id) && held(x.mods)
            && (bn !== 'left' || x.mods.length || plain));
        const picks = list.filter(x => !CAMERA.includes(x.id) && held(x.mods)
            && (x.mods.includes('alt') || !ev.alt));
        const rank = (arr) => arr.slice().sort((p, q) => (q.mods.length - p.mods.length)
            || ((q.user ? 1 : 0) - (p.user ? 1 : 0)))[0] || null;
        const cam = rank(cams);
        const pickTop = picks.length ? Math.max(...picks.map(x => x.mods.length)) : -1;
        if (cam && cam.mods.length > pickTop) return { camera: cam.id };
        if (!picks.length) return null;
        const box = rank(picks.filter(x => x.id === 'box'));
        const defer = cam && !(box && box.mods.length > cam.mods.length) ? cam.id : null;
        return {
            pick: true,
            select: picks.some(x => x.id === 'select'),
            move: picks.some(x => x.id === 'move'),
            moveMod: map.actions.move.mod,
            box: !!box || map.actions.box.button === bn,
            defer,
        };
    }

    function mouseName(binding, isMac, kind) {
        const v = binding || {};
        if (v.button === 'none') return 'Not set';
        if (v.button === 'wheel') return 'Wheel';
        const names = modNames(isMac);
        const pre = v.mod && v.mod !== 'none' ? names[v.mod] + '+' : '';
        const click = kind === 'click';
        const what = v.button === 'left' ? (click ? 'click' : 'drag')
            : `${v.button}-${click ? 'click' : 'drag'}`;
        const text = pre + what;
        return text.charAt(0).toUpperCase() + text.slice(1);
    }

    // ── odds and ends ─────────────────────────────────────────────────────

    function empty() {
        return { keys: {}, mouse3d: { preset: 'standard', actions: {} } };
    }

    // A stored record made safe to read: unknown actions and bad chords go.
    function clone(user) {
        const out = empty();
        const u = user && typeof user === 'object' ? user : {};
        if (u.keys && typeof u.keys === 'object') {
            Object.keys(u.keys).forEach(id => {
                if (BY_ID.has(id) && Array.isArray(u.keys[id])) {
                    out.keys[id] = u.keys[id].map(normalize).filter(Boolean)
                        .filter((k, i, all) => all.indexOf(k) === i);
                }
            });
        }
        const m = u.mouse3d && typeof u.mouse3d === 'object' ? u.mouse3d : {};
        out.mouse3d.preset = PRESETS[m.preset] ? m.preset : 'standard';
        if (m.actions && typeof m.actions === 'object') {
            MOUSE_IDS.forEach(id => {
                const v = validMouse(id, m.actions[id]);
                if (v) out.mouse3d.actions[id] = v;
            });
        }
        return out;
    }

    return {
        AREAS, SCOPE, ACTIONS, FIXED, MOUSE_ACTIONS, PRESETS, BUTTONS, MODS,
        action: id => BY_ID.get(id) || null,
        normalize, fromEvent, eventMatches, keysFor, matches, conflicts, isDefault, withKeys,
        refusal, format, formatList, keyName, modNames,
        mouseMap, mouseConflicts, withMouse, withPreset, resolvePress, mouseName,
        empty, clone,
    };
})();

if (typeof window !== 'undefined') window.Controls = Controls;
if (typeof module !== 'undefined' && module.exports) module.exports = Controls;
