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

function registerGlobalClientLogging() {
    // The last thing the person did, for an error that arrives with no
    // file or line. WebKit hands the page a bare "Script error." for a
    // throw in a script it treats as foreign (the desktop window's own
    // injected script), and on 2026-09-25 the owner's log held a run of
    // them while he typed processor names - which the app itself could
    // not reproduce in Chromium or WebKit. Recording the last key and
    // field beside each error is the evidence the next one needs.
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
        sendClientLog('client_error', {
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
        sendClientLog('ui_click', {
            id: button.id || '',
            text: (button.textContent || '').trim()
        });
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

export { evaluateMathExpression, isMacOS, sendClientLog, registerGlobalClientLogging, setupColorPickerWithHex, normalizeHex, refreshAllColorSwatches, isTypingTarget, installEnterEndsEdit };

// Classic (non-module) scripts call these by name at runtime
// (canvas.js -> sendClientLog, color_picker.js -> normalizeHex,
// canvas-input.js handleKeyDown -> isTypingTarget). This module is
// evaluated before app-core.js constructs the renderer that registers the
// keydown listener, so the alias exists before any key can reach it.
window.sendClientLog = sendClientLog;
window.normalizeHex = normalizeHex;
window.isTypingTarget = isTypingTarget;
