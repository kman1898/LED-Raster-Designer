// Shared top-level helpers (extracted from the old monolithic app.js).
// Utility function to evaluate math expressions in input fields
function evaluateMathExpression(value) {
    if (typeof value === 'number') {
        return value;
    }
    
    const str = String(value).trim();
    
    // If it's already a simple number, return it
    if (!isNaN(str) && str !== '') {
        return parseFloat(str);
    }
    
    // Check if the string contains math operators
    if (!/[\+\-\*\/\(\)]/.test(str)) {
        return parseFloat(str) || 0;
    }
    
    // Sanitize the expression - only allow numbers, operators, spaces, and decimal points
    const sanitized = str.replace(/[^0-9\+\-\*\/\(\)\.\s]/g, '');
    
    try {
        // Use Function constructor for safe evaluation (safer than eval)
        // This creates a function that returns the result of the expression
        const result = new Function('return ' + sanitized)();
        
        // Check if result is a valid number
        if (typeof result === 'number' && !isNaN(result) && isFinite(result)) {
            return result;
        }
        
        // If invalid, return 0
        return 0;
    } catch (e) {
        // If evaluation fails, try to parse as a simple number
        const fallback = parseFloat(str);
        return isNaN(fallback) ? 0 : fallback;
    }
}

function isMacOS() {
    return /Mac/i.test(navigator.platform) || /Mac/i.test(navigator.userAgent);
}

if (isMacOS()) {
    document.documentElement.classList.add('macos');
}

function sendClientLog(action, details = {}) {
    try {
        const payload = {
            action,
            details: {
                clientTime: new Date().toISOString(),
                url: window.location.href,
                ...details
            }
        };
        const body = JSON.stringify(payload);
        if (navigator.sendBeacon) {
            const blob = new Blob([body], { type: 'application/json' });
            navigator.sendBeacon('/api/log', blob);
            return;
        }
        fetch('/api/log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body,
            keepalive: true
        }).catch(() => {});
    } catch (e) {
    }
}

// The field an element is known by in the log: its id, else the
// data-lrd-field every generated control carries (most tray and popover
// fields have no id, so a bare id logged "" for them).
function clientLogField(el) {
    if (!el || !el.getAttribute) return '';
    return el.id || el.getAttribute('data-lrd-field') || '';
}

// An error the browser hid from the page: "Script error." with no file, no
// line, no column and no error object. A browser gives a page that bare
// form only for a throw in a script from ANOTHER origin, which in this app
// means a browser extension's content script or a script the browser put
// in the page itself. Every script of the app is served from the page's
// own origin, so a throw in the app's code always arrives with its file,
// line and stack. The opaque one is still logged, tagged so nobody chases
// it as the app's. 2026-11-04 (Backspace in a box's port cable lengths,
// owner's Mac) had this form, and the same gesture in Chromium, through
// every one of the app's own key, input and change handlers on the path,
// threw nothing (tests/test_cable_length_delete.py); 2026-09-25 (typing
// processor names) had it too.
function isOpaqueScriptError(event) {
    if (!event || event.error) return false;
    if (event.filename || event.lineno || event.colno) return false;
    return /^Script error\.?$/.test(String(event.message || '').trim());
}

function registerGlobalClientLogging() {
    // The last thing the person did, for an error that arrives with no
    // file or line (isOpaqueScriptError). Recording the last key and field
    // beside each error is the evidence the next one needs.
    let lastInput = null;
    const noteInput = (event) => {
        lastInput = {
            type: event.type,
            key: event.key && event.key.length === 1 ? 'char' : (event.key || ''),
            meta: !!(event.metaKey || event.ctrlKey),
            field: clientLogField(event.target),
            at: Date.now()
        };
    };
    document.addEventListener('keydown', noteInput, true);
    document.addEventListener('focusout', noteInput, true);
    document.addEventListener('mousedown', noteInput, true);
    window.addEventListener('error', (event) => {
        const opaque = isOpaqueScriptError(event);
        sendClientLog('client_error', {
            ...(opaque ? {
                opaque: true,
                actionable: false,
                origin: 'outside the app (a browser extension or the browser itself); the browser hides its details',
            } : {}),
            message: event.message,
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno,
            stack: event.error ? String(event.error.stack || event.error) : '',
            lastInput: lastInput
                ? Object.assign({}, lastInput, { msAgo: Date.now() - lastInput.at, at: undefined })
                : null,
            activeField: clientLogField(document.activeElement)
        });
    });

    window.addEventListener('unhandledrejection', (event) => {
        sendClientLog('client_unhandled_rejection', {
            reason: event.reason ? String(event.reason.stack || event.reason) : ''
        });
    });

    document.addEventListener('change', (event) => {
        const target = event.target;
        if (!target) return;
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') {
            sendClientLog('ui_change', {
                id: clientLogField(target),
                type: target.type || '',
                value: target.type === 'checkbox' ? target.checked : target.value
            });
        }
    });

    document.addEventListener('click', (event) => {
        const button = event.target ? event.target.closest('button') : null;
        if (!button) return;
        // A button with no id and no text (the pattern tiles are icons)
        // names itself by its data attribute and its tooltip, so the log
        // says which one was pressed.
        const data = button.getAttribute('data-pattern') || button.getAttribute('data-action') || '';
        const entry = {
            id: button.id || '',
            text: (button.textContent || '').trim() || button.getAttribute('aria-label') || button.title || ''
        };
        if (data) entry.data = data;
        sendClientLog('ui_click', entry);
    });
}

// Helper function to set up custom color picker with hex input sync (macOS-style)
function setupColorPickerWithHex(pickerId, hexId, onChangeCallback) {
    const picker = document.getElementById(pickerId);
    const hex = document.getElementById(hexId);
    const swatch = document.getElementById(`${pickerId}-swatch`);

    if (!picker || !hex) return;

    // The visible control is always the native <input type="color">, on every
    // platform. On Windows, color_picker.js intercepts clicks on it and shows
    // the custom macOS-style picker; on macOS the OS picker opens. This is the
    // single color-picker path, there is no separate swatch/popover anymore.
    const setColor = (val, isFinal = false) => {
        const normalized = normalizeHex(val);
        if (!normalized) return;
        picker.value = normalized;
        hex.value = normalized.toUpperCase();
        if (onChangeCallback) onChangeCallback(normalized, isFinal);
    };

    picker.type = 'color';
    picker.style.display = 'inline-block';
    picker.classList.add('native-color-input');
    // Hide the legacy swatch element if the template still has one.
    if (swatch) { swatch.style.display = 'none'; swatch.setAttribute('hidden', 'true'); }
    picker.addEventListener('input', (e) => setColor(e.target.value, false));
    picker.addEventListener('change', (e) => setColor(e.target.value, true));
    hex.addEventListener('change', () => setColor(hex.value, true));
    // v0.10.7.2: initialize the DISPLAY only (isFinal=false). Passing true here
    // made every picker simulate a user commit during setup - running
    // updateLayers()/debouncedSaveState() before the history system is even
    // initialized (resetHistory() runs after setupEventListeners). The first
    // picker whose init-commit flushed a prior pending save called saveState()
    // while this.history was still undefined, throwing and aborting the rest of
    // setupEventListeners - leaving every later color picker unwired. isFinal=false
    // is the same path every 'input' event takes, so all callbacks handle it safely.
    setColor(picker.value || hex.value || '#ffffff', false);
}

function normalizeHex(val) {
    if (!val) return null;
    let v = String(val).trim();
    if (!v.startsWith('#')) v = `#${v}`;
    if (/^#[0-9A-Fa-f]{6}$/.test(v)) return v;
    return null;
}

function refreshAllColorSwatches() {
    document.querySelectorAll('.color-swatch').forEach(btn => {
        const id = btn.id.replace('-swatch', '');
        const input = document.getElementById(id);
        if (input && input.value) {
            btn.style.background = input.value;
        }
    });
}

// LED Raster Designer - Main Application
// Version 6.1 - Cache Bust 001

// Is keyboard focus in something the person TYPES into? The one question
// every document-level shortcut asks before it fires, answered in ONE place.
//
// Found by an end-to-end pass (2026-09-23): Cmd+J did nothing while a
// sidebar CHECKBOX held focus. Tick #power-custom-toggle (focus stays on
// the box), Cmd+click a second Screens row, press Cmd+J - nothing; blur the
// box and the same key duplicates. Every guard read `tagName === 'INPUT'`,
// and a checkbox IS an INPUT, so a control that takes no text at all ate
// every shortcut - Cmd+J, Cmd+C/V, Delete, the arrow keys in custom mode,
// Tab stepping - until the next click landed somewhere else. Four copies
// of that guard had also drifted from one another: canvas-input.js counted
// contentEditable but not SELECT, app-core.js and app-dock-sweep.js counted
// SELECT but not contentEditable, app-menubar.js counted both.
//
// Typing means a text-like input (text, number, search, email, url,
// password, tel, the date and time kinds, and an input with no type - the
// DOM reads that as text), a textarea, a select (its arrow keys pick an
// option) or a contenteditable element. A checkbox, radio, range, color,
// file or button-like input is a CONTROL, not a field: no shortcut yields
// to it. The list is of the CONTROL types on purpose - an input type this
// list has not met is treated as typing, the direction that at worst
// leaves a shortcut unfired rather than eating a keystroke out of a field.
//
// Two rulings this predicate does NOT absorb, by design: a focused BUTTON
// still owns Tab (canvas-input.js handleKeyDown, user 2026-09-03), and
// Space on a focused control is the control's (it toggles the box) - the
// canvas pan yields to it there, not here.
const CONTROL_INPUT_TYPES = new Set([
    'checkbox', 'radio', 'range', 'color', 'file',
    'button', 'submit', 'reset', 'image', 'hidden',
]);

function isTypingTarget(el) {
    if (!el) return false;
    if (el.isContentEditable) return true;
    const tag = el.tagName;
    if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
    if (tag !== 'INPUT') return false;
    // el.type is the DOM's normalised type: missing or unknown reads 'text'.
    const type = String(el.type || 'text').toLowerCase();
    return !CONTROL_INPUT_TYPES.has(type);
}

// Enter ends the edit. Owner, 2026-09-24: "when I type into say the
// project name text box and finish typing, when I hit enter it doesn't
// complete the process. It doesn't until I click out of the box ... But in
// other areas if I don't hit enter I still like being able to tab to the
// next one."
//
// Enter already fired `change` in a text or number field (Chromium and
// WebKit both), so a field that commits on change had saved - but the box
// kept the caret and looked unfinished, and a field that commits on BLUR
// got nothing from Enter at all. The one rule, for every single-line field
// in the app, the ones the JS builds included: a plain Enter lets go of the
// field. Blur commits both kinds, and Tab is left exactly as it was.
//
// Document level, BUBBLE phase, so a field with its own Enter handler runs
// first and keeps its own rule: preventDefault() or stopPropagation() opts
// out (the canvas / group / beach renames, the pull sheet cells, the cable
// sheet fill boxes, the preset name, the colour window's hex box, the
// guided tour), and a handler that blurs the field itself (the Screens
// panel rename, the zoom box) leaves nothing for this rule to do. The
// release waits one tick so the change handler and any same-tick rebuild
// have run; if the field is no longer focused it already let go. Left
// alone on purpose:
//   - Shift/Ctrl/Meta/Alt+Enter, an IME composing (Enter picks the
//     candidate), a held key's repeats;
//   - a textarea (Enter is a newline), a select, contenteditable, and the
//     control inputs (checkbox, button ... - not typing, isTypingTarget);
//   - a read-only field (no edit to end - the rename fields sit read-only
//     until a double-click);
//   - a field its own change handler flagged `invalid`: the caret stays so
//     the person can fix what they typed (the watts field);
//   - a field with a `list` datalist whose suggestion the Enter picked:
//     WebKit delivers the keydown, then puts the highlighted suggestion in
//     the box (an `input`, then `change`) before the key comes up; in
//     Chromium the Enter reached the page with the value untouched (both
//     measured headed, 2026-09-24). That Enter chose an option, so the
//     field stays open; the next Enter ends it.
// A rebuild that hands focus to the SAME field's fresh node in the same
// tick (_preserveEditorFocus restores by data-lrd-field) is followed there.

// The text-like kinds isTypingTarget counts, less the date and time
// pickers (their Enter belongs to the picker). el.type reads 'text' for a
// missing or unknown type.
const SINGLE_LINE_TYPES = new Set([
    'text', 'number', 'search', 'email', 'url', 'tel', 'password',
]);

function isSingleLineField(el) {
    if (!el || el.tagName !== 'INPUT' || el.isContentEditable) return false;
    return SINGLE_LINE_TYPES.has(String(el.type || 'text').toLowerCase());
}

function _sameField(a, b) {
    if (!a || !b) return false;
    if (a === b) return true;
    if (!b.isConnected || a.tagName !== b.tagName) return false;
    const key = (el) => (el.dataset && (el.dataset.lrdField || el.dataset.hwdock)) || el.id || '';
    return !!key(a) && key(a) === key(b);
}

function installEnterEndsEdit(doc) {
    doc = doc || document;
    if (doc.__lrdEnterEndsEdit) return;
    doc.__lrdEnterEndsEdit = true;
    doc.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' || e.defaultPrevented) return;
        if (e.isComposing || e.keyCode === 229 || e.repeat) return;
        if (e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
        const el = e.target;
        if (!isSingleLineField(el) || el.readOnly || el.disabled) return;
        const release = () => {
            const now = doc.activeElement;
            if (!_sameField(el, now)) return;
            if (now.readOnly) return;
            if (now.classList.contains('invalid')
                    || now.getAttribute('aria-invalid') === 'true') return;
            now.blur();
        };
        if (!el.list) {
            setTimeout(release, 0);
            return;
        }
        // A datalist field: WebKit's pick lands as an `input` a moment
        // AFTER this tick (measured ~1 ms, always before the Enter's
        // keyup), so the call waits for the keyup - or half a second, for
        // a keyup that never comes - and stands aside if a pick arrived.
        let picked = false;
        let done = false;
        const onInput = () => { picked = true; };
        const onUp = (u) => { if (u.key === 'Enter') setTimeout(decide, 0); };
        const timer = setTimeout(() => decide(), 500);
        function decide() {
            if (done) return;
            done = true;
            clearTimeout(timer);
            el.removeEventListener('input', onInput);
            doc.removeEventListener('keyup', onUp, true);
            if (!picked) release();
        }
        el.addEventListener('input', onInput);
        doc.addEventListener('keyup', onUp, true);
    });
}

// No autofill reaches a show. Owner, 2026-11-05: "i just had autofill
// change a bunch of stuff. this cannot happen." With the Export window
// open, the browser's contact AutoFill filled the Project Manager field
// being typed in, then a multi name in the folded tray and the Designer
// and phone fields, all inside a second: eight Rename Multi steps and a
// name written across screens, undone by hand.
//
// One rule for every field the app has or ever builds, in two halves.
//
// Asking the browser not to (the hints). `autocomplete="off"` and the
// ignore hints that extension fillers read go on each text-like field,
// textarea and select as it appears (a MutationObserver), so no field sets
// them for itself. They are a request only: contact AutoFill is known to
// pass over `autocomplete="off"` on a field that reads like a name or a
// phone, so nothing depends on them.
//
// Not trusting the browser (the guard). WebKit's fill writes the value in
// native code and then fires `input` and `change`, focused or not, so the
// app's listeners cannot tell it from an edit by the events alone. What
// the guard knows instead is every value that is supposed to be there:
//   - page script writes through the value setters, which are watched, so
//     the app's own code, undo and the guides need no marking at all;
//   - the person's edits arrive as trusted InputEvents and are noted.
// A value that came by neither road was written from outside the page.
// When such a value turns up in an `input` or `change`, one capture
// listener on the window, ahead of every listener in the app, puts the
// field back, stops the event dead and logs `autofill_refused` with the
// field and no value. Nothing reaches a handler, a history step or a save.
//
// A value the page does not know is still the person's when:
//   - the field has focus and the browser says it was typed (a trusted
//     InputEvent: keys, paste, cut, IME, dictation, spelling, Cmd+Z);
//   - it is a select, or a number or date kind (stepper, wheel, picker,
//     which fire plain events), that has focus or was the last thing
//     pressed: WebKit on the Mac gives a select no focus on a click;
//   - it is a pick from the field's own datalist (a plain event too);
//   - it is an undo, redo or drag of text, which can land on a field that
//     has lost the focus.
//
// The field being typed in. WebKit's fill does not look like typing even
// there: a plain `input` event, not an InputEvent, and the browser's own
// autofill mark on the field, so it is refused and the text typed so far
// stays. Only a filler that writes through the text input system (a
// multi-character insertText, which is also what dictation and scripted
// typing look like) would pass, and it could reach that one field only.
const FIELD_NO_FILL_HINTS = [
    ['autocomplete', 'off'],
    ['data-form-type', 'other'],
    ['data-lpignore', 'true'],
    ['data-1p-ignore', 'true'],
    ['data-bwignore', 'true'],
];

// Fields only keys and paste can edit: a plain event in one is never the
// person. (el.type reads 'textarea' on a textarea.)
const FREE_TEXT_TYPES = new Set(['text', 'email', 'url', 'tel', 'password', 'textarea']);

const INPUT_FROM_ANYWHERE = /^(historyUndo|historyRedo|insertFromDrop|deleteByDrag)$/;

// A fill fires `input` and `change` back to back. The field is back to its
// old value by the `change`, which would run its handler with that value.
const REFUSED_PAIR_MS = 1000;

function isFillableField(el) {
    if (!el || el.isContentEditable) return false;
    const tag = el.tagName;
    if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
    return tag === 'INPUT' && isTypingTarget(el);
}

function browserMarkedFilled(el) {
    return [':autofill', ':-webkit-autofill'].some((mark) => {
        try { return el.matches(mark); } catch (e) { return false; }
    });
}

function installFieldGuard(doc) {
    doc = doc || document;
    if (doc.__lrdFieldGuard) return;
    doc.__lrdFieldGuard = true;
    const win = doc.defaultView || window;
    const known = new WeakMap();     // field -> the value that belongs there
    const refusedAt = new WeakMap(); // field -> when a fill of it was refused
    let pressed = null;

    // Every script write, read back so a number box's clean-up is what is
    // remembered. An option's `selected` lands on its select.
    [[win.HTMLInputElement, 'value'], [win.HTMLTextAreaElement, 'value'],
        [win.HTMLSelectElement, 'value'], [win.HTMLSelectElement, 'selectedIndex'],
        [win.HTMLOptionElement, 'selected']].forEach(([type, prop]) => {
        const native = Object.getOwnPropertyDescriptor(type.prototype, prop);
        Object.defineProperty(type.prototype, prop, {
            ...native,
            set(v) {
                native.set.call(this, v);
                const field = this.tagName === 'OPTION' ? this.closest('select') : this;
                if (!isFillableField(field)) return;
                known.set(field, field.value);
                refusedAt.delete(field);
            },
        });
    });

    const stamp = (el) => {
        FIELD_NO_FILL_HINTS.forEach(([name, value]) => {
            if (el.getAttribute(name) !== value) el.setAttribute(name, value);
        });
        if (!known.has(el)) known.set(el, el.value);
    };
    const sweep = (root) => {
        if (isFillableField(root)) stamp(root);
        root.querySelectorAll('input, textarea, select').forEach((el) => {
            if (isFillableField(el)) stamp(el);
        });
    };
    // A select given new options, or a textarea new default text, changes
    // value with no setter involved.
    const readMutations = (records) => records.forEach((record) => {
        record.addedNodes.forEach((node) => { if (node.nodeType === 1) sweep(node); });
        const owner = record.target.closest && record.target.closest('select, textarea');
        if (owner) known.set(owner, owner.value);
    });
    const observer = new win.MutationObserver(readMutations);
    observer.observe(doc.documentElement, { childList: true, subtree: true });
    sweep(doc.documentElement);

    const whyRefused = (e, el) => {
        // Trusted, so a filler's script cannot claim to be typing. A plain
        // Event has no inputType, and Firefox's own fill says
        // insertReplacementText, as a spelling fix does, so its mark decides.
        const inputType = e.isTrusted && e.type === 'input' ? (e.inputType || '') : '';
        if (browserMarkedFilled(el) && (!inputType || inputType === 'insertReplacementText')) {
            return 'marked_autofilled';
        }
        if (INPUT_FROM_ANYWHERE.test(inputType)) return '';
        // An automated browser's select_option writes from a script world
        // of its own, past the setters. Same rule as the first-run windows:
        // a test that wants the real thing says so.
        if (el.tagName === 'SELECT' && !e.isTrusted && win.navigator.webdriver
            && !win.__lrdFieldGuardLive) return '';
        if (doc.activeElement !== el && pressed !== el) return 'not_focused';
        if (inputType || !FREE_TEXT_TYPES.has(el.type)) return '';
        if (el.list && [...el.list.options].some(o => o.value === el.value)) return '';
        return 'not_typed';
    };

    const guard = (e) => {
        const el = e.target;
        if (!isFillableField(el)) return;
        readMutations(observer.takeRecords());
        if (!known.has(el)) stamp(el);
        if (el.value === known.get(el)) {
            const at = refusedAt.get(el);
            refusedAt.delete(el);
            if (at !== undefined && Date.now() - at < REFUSED_PAIR_MS) e.stopImmediatePropagation();
            return;
        }
        const reason = whyRefused(e, el);
        if (!reason) {
            known.set(el, el.value);
            refusedAt.delete(el);
            return;
        }
        e.stopImmediatePropagation();
        el.value = known.get(el);
        refusedAt.set(el, Date.now());
        sendClientLog('autofill_refused', {
            id: clientLogField(el),
            event: e.type,
            reason,
            trusted: e.isTrusted,
            focused: doc.activeElement === el,
        });
    };
    win.addEventListener('input', guard, true);
    win.addEventListener('change', guard, true);

    const press = (e) => {
        const target = e.target;
        pressed = target && target.closest ? target.closest('input, textarea, select') : null;
    };
    win.addEventListener('pointerdown', press, true);
    win.addEventListener('mousedown', press, true);
    win.addEventListener('keydown', () => { pressed = null; }, true);
}

// A press on a dialog's action button commits the field being typed in
// first. Owner QA, 2026-11-03: Export clicked straight after typing a new
// Rev did nothing. The field's blur on mouse-down committed the Rev, the
// new REVISIONS row it logs grew the dialog, and the button moved out from
// under the pointer before the mouse came up, so the click never landed.
// Here mouse-down on the button keeps the focus where it is (nothing moves
// yet), and the click lets go of the field first, so its change commits
// (as a blur always did) before the button's own handler reads it. Call
// it before the button's click handler is added.
function commitEditOnPress(button) {
    if (!button || button.__lrdCommitOnPress) return;
    button.__lrdCommitOnPress = true;
    button.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        const el = document.activeElement;
        if (el !== button && isSingleLineField(el) && !el.readOnly) e.preventDefault();
    });
    button.addEventListener('click', () => {
        const el = document.activeElement;
        if (el && el !== button && isSingleLineField(el)) el.blur();
    }, true);
}

// The data flow patterns (the owner's rulings, 2026-11-01). A code is
// `<corner>-<h|v>` for a SNAKE, where every row (horizontal first) or
// column (vertical first) runs back the opposite way, and the same code
// with `-z` on the end for its Z twin, where every row or column starts
// again from the same side as the first, the way a cable goes back to the
// left edge before each new row. Corner and first direction are the
// snake's. The picker shows the snakes on top and the Z twins under them,
// both rows in this order. Any other code (an old show's) walks as it
// always did: it is not a Z, so it snakes.
const FLOW_SNAKE_PATTERNS = ['tl-h', 'tr-h', 'bl-h', 'br-h', 'tl-v', 'tr-v', 'bl-v', 'br-v'];
const FLOW_Z_PATTERNS = FLOW_SNAKE_PATTERNS.map(p => `${p}-z`);
const FLOW_AUTO_PATTERNS = FLOW_SNAKE_PATTERNS.concat(FLOW_Z_PATTERNS);

function isZFlowPattern(pattern) {
    return FLOW_Z_PATTERNS.includes(String(pattern || ''));
}

// Vertical first: the code's second part is `v` (tl-v, tl-v-z).
function isVerticalFlowPattern(pattern) {
    return String(pattern || '').split('-')[1] === 'v';
}

// A name being edited in a list row must not sit under anything draggable.
// WebKit (Safari, and the Mac app's window) starts the ROW's drag when the
// mouse is pressed and dragged inside a text field whose ancestor is
// draggable, so a drag meant to select part of the name moved the screen
// instead (owner's report, 1.6.0 beta.5). Turns `draggable` off on every
// element given that has it on and returns the undo, which turns those
// back on. The rows are rebuilt whole by their list, so an edit that ends
// with the rebuild (no blur, no undo) leaves only detached nodes off.
function holdDragOff(...els) {
    const held = els.filter(el => el && el.draggable === true);
    held.forEach(el => { el.draggable = false; });
    return () => held.forEach(el => { el.draggable = true; });
}

// A drag inside a list name being edited selects text, the first drag too.
// Opening the edit selects the whole name, so the next press lands on
// selected text, and a browser takes that for a text drag: the app's own
// dragstart handlers cancelled it and the highlight fell to a caret (screen,
// canvas, beach), or the text itself was dragged (group, which has none).
// holdDragOff above cannot help, it covers the rows' drag and not this one.
// Letting go of the selection before the browser reads the press makes it an
// ordinary press in the field: the caret lands under it and the drag selects.
// Any selection counts, whole name or one word: what a double-click leaves
// differs by system. A press of a double or triple click is left to pick its
// word or the line, and Shift to extend the selection.
//
// Then the drag itself. Chromium loses a drag's start when the press lands
// close to the middle of a letter and off a whole CSS pixel, in any text field
// with none of this code on the page: the caret follows the mouse and nothing
// is selected. Which presses depends on the font and the field's position
// (CI, Linux, beach name, 2026-11-05); on a scaled screen about 1 press in 20
// did it in Chromium's emulation. So the place the press put the caret is kept,
// and a caret that has left it while the button is held goes back to being a
// selection from there. In a drag that works the selection is never a caret
// anywhere else, so this does nothing.
//
// And its end. Let go past the end of the name and the browser clicks whatever
// holds both ends of the drag, the row: a group's header took that as a click
// on the group, rebuilt the list and ended the rename. That click is the
// drag's, so it stops here.
const LIST_NAME_FIELDS = '.layer-name-input, .canvas-name-input, .screen-group-name-input, .beach-name-input';

function installNameDragSelects(doc) {
    doc = doc || document;
    if (doc.__lrdNameDragSelects) return;
    doc.__lrdNameDragSelects = true;
    // The field being pressed, and where the press put its caret.
    let held = null;
    let anchor = null;
    let dragsClick = false;
    const keepTheStart = () => {
        if (!held || anchor === null || doc.activeElement !== held) return;
        const at = held.selectionStart;
        if (at === held.selectionEnd && at !== anchor) {
            held.setSelectionRange(Math.min(at, anchor), Math.max(at, anchor), at < anchor ? 'backward' : 'forward');
        }
    };
    doc.addEventListener('mousedown', (e) => {
        held = null;
        anchor = null;
        dragsClick = false;
        if (e.button !== 0 || e.detail > 1 || e.shiftKey) return;
        const el = e.target;
        if (!el || !el.matches || !el.matches(LIST_NAME_FIELDS) || el.readOnly) return;
        if (el.selectionStart !== el.selectionEnd) el.setSelectionRange(el.selectionEnd, el.selectionEnd);
        held = el;
    }, true);
    doc.addEventListener('mousemove', (e) => {
        if (!held) return;
        if (!(e.buttons & 1)) held = null;
        else if (anchor === null) anchor = held.selectionStart;   // the press has landed by now
    }, true);
    doc.addEventListener('selectionchange', keepTheStart);
    doc.addEventListener('mouseup', (e) => {
        keepTheStart();
        dragsClick = !!held && e.target !== held;
        held = null;
    }, true);
    doc.addEventListener('click', (e) => {
        if (!dragsClick) return;
        dragsClick = false;
        e.stopPropagation();
        e.preventDefault();
    }, true);
}

export { evaluateMathExpression, isMacOS, sendClientLog, registerGlobalClientLogging, setupColorPickerWithHex, normalizeHex, refreshAllColorSwatches, isTypingTarget, installEnterEndsEdit, installNameDragSelects, installFieldGuard, commitEditOnPress,
    FLOW_SNAKE_PATTERNS, FLOW_Z_PATTERNS, FLOW_AUTO_PATTERNS, isZFlowPattern, isVerticalFlowPattern, holdDragOff };

// Classic (non-module) scripts call these by name at runtime
// (canvas.js -> sendClientLog, color_picker.js -> normalizeHex,
// canvas-input.js handleKeyDown -> isTypingTarget). This module is
// evaluated before app-core.js constructs the renderer that registers the
// keydown listener, so the alias exists before any key can reach it.
window.sendClientLog = sendClientLog;
window.normalizeHex = normalizeHex;
window.isTypingTarget = isTypingTarget;
