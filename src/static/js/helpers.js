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

function registerGlobalClientLogging() {
    window.addEventListener('error', (event) => {
        sendClientLog('client_error', {
            message: event.message,
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno,
            stack: event.error ? String(event.error.stack || event.error) : ''
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
                id: target.id || '',
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

export { evaluateMathExpression, isMacOS, sendClientLog, registerGlobalClientLogging, setupColorPickerWithHex, normalizeHex, refreshAllColorSwatches };

// Classic (non-module) scripts call these two by name at runtime
// (canvas.js -> sendClientLog, color_picker.js -> normalizeHex).
window.sendClientLog = sendClientLog;
window.normalizeHex = normalizeHex;
