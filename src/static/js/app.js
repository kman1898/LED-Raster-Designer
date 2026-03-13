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

function rgbToHexLocal(r, g, b) {
    return (
        '#' +
        [r, g, b]
            .map((val) => {
                const hex = Math.max(0, Math.min(255, val)).toString(16);
                return hex.length === 1 ? `0${hex}` : hex;
            })
            .join('')
    ).toUpperCase();
}

function startCanvasEyedropper(onPick, currentSwatch) {
    const canvas = window.canvasRenderer && window.canvasRenderer.canvas;
    const ctx = window.canvasRenderer && window.canvasRenderer.ctx;
    if (!canvas || !ctx) return;

    const cleanup = () => {
        document.body.classList.remove('eyedropper-active');
        document.removeEventListener('click', onClick, true);
        document.removeEventListener('keydown', onKey, true);
    };

    const onKey = (e) => {
        if (e.key === 'Escape') cleanup();
    };

    const onClick = (e) => {
        const rect = canvas.getBoundingClientRect();
        const x = Math.floor(e.clientX - rect.left);
        const y = Math.floor(e.clientY - rect.top);
        if (x < 0 || y < 0 || x >= canvas.width || y >= canvas.height) {
            cleanup();
            return;
        }
        const data = ctx.getImageData(x, y, 1, 1).data;
        const hex = rgbToHexLocal(data[0], data[1], data[2]);
        onPick(hex);
        if (currentSwatch) currentSwatch.style.background = hex;
        cleanup();
        e.preventDefault();
        e.stopPropagation();
    };

    document.body.classList.add('eyedropper-active');
    document.addEventListener('click', onClick, true);
    document.addEventListener('keydown', onKey, true);
}

// Helper function to set up custom color picker with hex input sync (macOS-style)
function setupColorPickerWithHex(pickerId, hexId, onChangeCallback) {
    const picker = document.getElementById(pickerId);
    const hex = document.getElementById(hexId);
    const swatch = document.getElementById(`${pickerId}-swatch`);

    if (!picker || !hex) return;

    const setColor = (val, isFinal = false) => {
        const normalized = normalizeHex(val);
        if (!normalized) return;
        picker.value = normalized;
        hex.value = normalized.toUpperCase();
        if (swatch) swatch.style.background = normalized;
        if (onChangeCallback) onChangeCallback(normalized, isFinal);
        pushRecentColor(normalized);
    };

    if (isMacOS()) {
        picker.type = 'color';
        picker.style.display = 'inline-block';
        picker.classList.add('native-color-input');
        if (swatch) {
            swatch.classList.add('color-swatch-hidden');
            swatch.style.display = 'none';
            swatch.setAttribute('hidden', 'true');
        }
        picker.addEventListener('input', (e) => setColor(e.target.value, false));
        picker.addEventListener('change', (e) => setColor(e.target.value, true));
        hex.addEventListener('change', () => setColor(hex.value, true));
        setColor(picker.value || hex.value || '#ffffff', true);
        return;
    }

    picker.style.display = 'none';
    if (swatch) {
        swatch.classList.remove('color-swatch-hidden');
        swatch.removeAttribute('hidden');
        swatch.style.display = 'inline-block';
        swatch.addEventListener('click', (e) => {
            e.preventDefault();
            openColorPopover(swatch, (color) => setColor(color, true), () => openColorModal(setColor));
        });
    }

    hex.addEventListener('change', () => {
        setColor(hex.value, true);
    });

    // Initialize swatch
    setColor(picker.value || hex.value || '#ffffff', true);
}

// ---- Custom Color Picker UI ----
const colorPickerState = {
    popover: null,
    modalBackdrop: null,
    modal: null,
    wheelCanvas: null,
    wheelCtx: null,
    valueSlider: null,
    recent: []
};

const macSwatchRows = (() => {
    const row1 = [
        '#FF3B30', '#FF9500', '#FFCC00', '#34C759', '#5AC8FA', '#007AFF',
        '#AF52DE', '#FF2D55', '#A2845E', '#FFFFFF', '#D1D1D6', '#1C1C1E'
    ];
    const row2 = [
        null, '#FFFFFF', '#E5E5EA', '#D1D1D6', '#C7C7CC', '#AEAEB2',
        '#8E8E93', '#636366', '#48484A', '#3A3A3C', '#2C2C2E', '#1C1C1E'
    ];
    const rows = [];
    const hues = [0, 20, 40, 60, 90, 120, 160, 200, 220, 260, 300, 330];
    const vals = [0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95];
    for (let r = 0; r < vals.length; r++) {
        const row = [];
        for (let c = 0; c < hues.length; c++) {
            const rgb = hsvToRgb(hues[c], 0.9, vals[r]);
            row.push(rgbToHex(rgb.r, rgb.g, rgb.b));
        }
        rows.push(row);
    }
    return [row1, row2, ...rows];
})();

function normalizeHex(val) {
    if (!val) return null;
    let v = String(val).trim();
    if (!v.startsWith('#')) v = `#${v}`;
    if (/^#[0-9A-Fa-f]{6}$/.test(v)) return v;
    return null;
}

function pushRecentColor(hex) {
    if (!hex) return;
    const upper = hex.toUpperCase();
    colorPickerState.recent = colorPickerState.recent.filter(c => c !== upper);
    colorPickerState.recent.unshift(upper);
    colorPickerState.recent = colorPickerState.recent.slice(0, 24);
}

function openColorPopover(anchor, onPick, onShowColors) {
    if (!colorPickerState.popover) {
        const pop = document.createElement('div');
        pop.className = 'color-popover';
        const grid = document.createElement('div');
        grid.className = 'swatch-grid';
        macSwatchRows.forEach(row => {
            row.forEach(color => {
                const sw = document.createElement('div');
                sw.className = 'swatch';
                if (!color) {
                    sw.classList.add('swatch-none');
                } else {
                    sw.style.background = color;
                }
                sw.addEventListener('click', () => {
                    if (color) {
                        onPick(color);
                    }
                    closeColorPopover();
                });
                grid.appendChild(sw);
            });
        });
        const showBtn = document.createElement('button');
        showBtn.className = 'show-colors-btn';
        showBtn.textContent = 'Show Colors...';
        showBtn.addEventListener('click', () => {
            closeColorPopover();
            onShowColors();
        });
        pop.appendChild(grid);
        pop.appendChild(showBtn);
        document.body.appendChild(pop);
        colorPickerState.popover = pop;
    }

    const rect = anchor.getBoundingClientRect();
    colorPickerState.popover.style.left = `${rect.left}px`;
    colorPickerState.popover.style.top = `${rect.bottom + 6}px`;
    colorPickerState.popover.style.display = 'block';
    // Clamp inside viewport
    const pop = colorPickerState.popover;
    const margin = 8;
    const popW = pop.offsetWidth;
    const popH = pop.offsetHeight;
    let left = rect.left;
    let top = rect.bottom + 6;
    if (left + popW + margin > window.innerWidth) {
        left = Math.max(margin, window.innerWidth - popW - margin);
    }
    if (top + popH + margin > window.innerHeight) {
        const above = rect.top - popH - 6;
        top = above > margin ? above : Math.max(margin, window.innerHeight - popH - margin);
    }
    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;

    const onDocClick = (e) => {
        if (!colorPickerState.popover.contains(e.target) && e.target !== anchor) {
            closeColorPopover();
            document.removeEventListener('mousedown', onDocClick);
        }
    };
    setTimeout(() => document.addEventListener('mousedown', onDocClick), 0);
}

function closeColorPopover() {
    if (colorPickerState.popover) {
        colorPickerState.popover.style.display = 'none';
    }
}

function openColorModal(onPick) {
    if (!colorPickerState.modal) {
        const backdrop = document.createElement('div');
        backdrop.className = 'color-modal-backdrop';
        const modal = document.createElement('div');
        modal.className = 'color-modal';

        const header = document.createElement('div');
        header.className = 'modal-header';
        const title = document.createElement('div');
        title.className = 'modal-title';
        title.textContent = 'Colors';
        const close = document.createElement('button');
        close.className = 'modal-close';
        close.textContent = '×';
        close.addEventListener('click', () => closeColorModal());
        header.appendChild(title);
        header.appendChild(close);

        const modeBar = document.createElement('div');
        modeBar.className = 'color-mode-bar';
        const modeButtons = [
            { id: 'wheel', label: 'Wheel' },
            { id: 'rgb', label: 'RGB' },
            { id: 'hsb', label: 'HSB' },
            { id: 'gray', label: 'Gray' },
            { id: 'cmyk', label: 'CMYK' },
            { id: 'spectrum', label: 'Spectrum' }
        ];
        modeButtons.forEach(btn => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'color-mode-btn';
            b.dataset.mode = btn.id;
            b.textContent = btn.label;
            modeBar.appendChild(b);
        });

        const pickerArea = document.createElement('div');
        pickerArea.className = 'picker-area';
        const wheel = document.createElement('canvas');
        wheel.width = 300;
        wheel.height = 300;
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '0';
        slider.max = '100';
        slider.value = '100';
        slider.className = 'slider';

        pickerArea.appendChild(wheel);
        pickerArea.appendChild(slider);

        const spectrumArea = document.createElement('div');
        spectrumArea.className = 'spectrum-area';
        const spectrum = document.createElement('canvas');
        spectrum.width = 320;
        spectrum.height = 320;
        spectrumArea.appendChild(spectrum);

        const sliderSection = document.createElement('div');
        sliderSection.className = 'slider-section';

        const makeSliderRow = (labelText, min, max) => {
            const row = document.createElement('div');
            row.className = 'slider-row';
            const label = document.createElement('div');
            label.className = 'slider-label';
            label.textContent = labelText;
            const range = document.createElement('input');
            range.type = 'range';
            range.min = String(min);
            range.max = String(max);
            range.value = String(min);
            const val = document.createElement('input');
            val.type = 'text';
            val.className = 'slider-value';
            val.value = String(min);
            row.appendChild(label);
            row.appendChild(range);
            row.appendChild(val);
            return { row, range, val };
        };

        const rgbRows = {
            r: makeSliderRow('Red', 0, 255),
            g: makeSliderRow('Green', 0, 255),
            b: makeSliderRow('Blue', 0, 255)
        };
        const hsbRows = {
            h: makeSliderRow('Hue', 0, 360),
            s: makeSliderRow('Saturation', 0, 100),
            v: makeSliderRow('Brightness', 0, 100)
        };
        const grayRow = { k: makeSliderRow('Gray', 0, 100) };
        const cmykRows = {
            c: makeSliderRow('Cyan', 0, 100),
            m: makeSliderRow('Magenta', 0, 100),
            y: makeSliderRow('Yellow', 0, 100),
            k: makeSliderRow('Black', 0, 100)
        };

        const recent = document.createElement('div');
        recent.className = 'recent-swatches';

        const bottomRow = document.createElement('div');
        bottomRow.className = 'bottom-row';
        const currentSwatch = document.createElement('div');
        currentSwatch.className = 'current-swatch';
        const dropper = document.createElement('button');
        dropper.className = 'eyedropper-btn';
        dropper.type = 'button';
        dropper.setAttribute('aria-label', 'Pick Color');
        dropper.setAttribute('title', 'Pick Color');
        dropper.addEventListener('click', async () => {
            if ('EyeDropper' in window) {
                try {
                    const eye = new EyeDropper();
                    const result = await eye.open();
                    if (result && result.sRGBHex) {
                        onPick(result.sRGBHex);
                        currentSwatch.style.background = result.sRGBHex;
                    }
                    return;
                } catch (e) {
                    // user cancelled
                    return;
                }
            }
            startCanvasEyedropper(onPick, currentSwatch);
        });
        bottomRow.appendChild(currentSwatch);
        bottomRow.appendChild(dropper);

        modal.appendChild(header);
        modal.appendChild(modeBar);
        modal.appendChild(pickerArea);
        modal.appendChild(spectrumArea);
        modal.appendChild(sliderSection);
        modal.appendChild(recent);
        modal.appendChild(bottomRow);
        document.body.appendChild(backdrop);
        document.body.appendChild(modal);

        colorPickerState.modalBackdrop = backdrop;
        colorPickerState.modal = modal;
        colorPickerState.wheelCanvas = wheel;
        colorPickerState.wheelCtx = wheel.getContext('2d');
        colorPickerState.valueSlider = slider;
        colorPickerState.currentSwatch = currentSwatch;
        colorPickerState.mode = 'wheel';
        colorPickerState.modeButtons = modeBar.querySelectorAll('.color-mode-btn');
        colorPickerState.spectrumCanvas = spectrum;
        colorPickerState.spectrumCtx = spectrum.getContext('2d');
        colorPickerState.sliderSection = sliderSection;
        colorPickerState.sliderRows = { rgb: rgbRows, hsb: hsbRows, gray: grayRow, cmyk: cmykRows };

        drawHueWheel(colorPickerState.wheelCtx, wheel.width, wheel.height);
        drawSpectrum(colorPickerState.spectrumCtx, spectrum.width, spectrum.height);

        const setMode = (mode) => {
            colorPickerState.mode = mode;
            colorPickerState.modeButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
            pickerArea.style.display = mode === 'wheel' ? 'grid' : 'none';
            spectrumArea.style.display = mode === 'spectrum' ? 'block' : 'none';
            sliderSection.style.display = (mode === 'rgb' || mode === 'hsb' || mode === 'gray' || mode === 'cmyk') ? 'block' : 'none';
            sliderSection.innerHTML = '';
            if (mode === 'rgb') {
                sliderSection.appendChild(rgbRows.r.row);
                sliderSection.appendChild(rgbRows.g.row);
                sliderSection.appendChild(rgbRows.b.row);
            } else if (mode === 'hsb') {
                sliderSection.appendChild(hsbRows.h.row);
                sliderSection.appendChild(hsbRows.s.row);
                sliderSection.appendChild(hsbRows.v.row);
            } else if (mode === 'gray') {
                sliderSection.appendChild(grayRow.k.row);
            } else if (mode === 'cmyk') {
                sliderSection.appendChild(cmykRows.c.row);
                sliderSection.appendChild(cmykRows.m.row);
                sliderSection.appendChild(cmykRows.y.row);
                sliderSection.appendChild(cmykRows.k.row);
            }
        };

        colorPickerState.modeButtons.forEach(btn => {
            btn.addEventListener('click', () => setMode(btn.dataset.mode));
        });
        setMode('wheel');

        const setColorFromHex = (hex) => {
            if (!hex) return;
            onPick(hex);
            renderRecentSwatches(onPick);
            if (colorPickerState.currentSwatch) colorPickerState.currentSwatch.style.background = hex;
            const rgb = hexToRgbLocal(hex);
            if (!rgb) return;
            const hsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
            const cmyk = rgbToCmyk(rgb.r, rgb.g, rgb.b);
            rgbRows.r.range.value = rgb.r; rgbRows.r.val.value = rgb.r;
            rgbRows.g.range.value = rgb.g; rgbRows.g.val.value = rgb.g;
            rgbRows.b.range.value = rgb.b; rgbRows.b.val.value = rgb.b;
            hsbRows.h.range.value = hsv.h; hsbRows.h.val.value = hsv.h;
            hsbRows.s.range.value = hsv.s; hsbRows.s.val.value = hsv.s;
            hsbRows.v.range.value = hsv.v; hsbRows.v.val.value = hsv.v;
            const gray = Math.round((rgb.r + rgb.g + rgb.b) / 3 / 255 * 100);
            grayRow.k.range.value = gray; grayRow.k.val.value = gray;
            cmykRows.c.range.value = cmyk.c; cmykRows.c.val.value = cmyk.c;
            cmykRows.m.range.value = cmyk.m; cmykRows.m.val.value = cmyk.m;
            cmykRows.y.range.value = cmyk.y; cmykRows.y.val.value = cmyk.y;
            cmykRows.k.range.value = cmyk.k; cmykRows.k.val.value = cmyk.k;
        };

        const pickFromWheel = (e) => {
            const rect = wheel.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const color = getWheelColor(colorPickerState.wheelCtx, x, y, parseInt(slider.value, 10) / 100);
            if (color) {
                setColorFromHex(color);
            }
        };

        let dragging = false;
        wheel.addEventListener('mousedown', (e) => { dragging = true; pickFromWheel(e); });
        window.addEventListener('mousemove', (e) => { if (dragging) pickFromWheel(e); });
        window.addEventListener('mouseup', () => { dragging = false; });
        slider.addEventListener('input', () => {
            const hex = colorPickerState.recent[0];
            if (hex) setColorFromHex(hex);
            renderRecentSwatches(onPick);
        });

        const spectrumPick = (e) => {
            const rect = spectrum.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const color = getSpectrumColor(colorPickerState.spectrumCtx, x, y);
            if (color) setColorFromHex(color);
        };
        let spectrumDrag = false;
        spectrum.addEventListener('mousedown', (e) => { spectrumDrag = true; spectrumPick(e); });
        window.addEventListener('mousemove', (e) => { if (spectrumDrag) spectrumPick(e); });
        window.addEventListener('mouseup', () => { spectrumDrag = false; });

        const bindSlider = (row, onUpdate) => {
            row.range.addEventListener('input', () => {
                row.val.value = row.range.value;
                onUpdate();
            });
            row.val.addEventListener('change', () => {
                row.range.value = row.val.value;
                onUpdate();
            });
        };

        bindSlider(rgbRows.r, () => setColorFromHex(rgbToHex(parseInt(rgbRows.r.range.value, 10), parseInt(rgbRows.g.range.value, 10), parseInt(rgbRows.b.range.value, 10))));
        bindSlider(rgbRows.g, () => setColorFromHex(rgbToHex(parseInt(rgbRows.r.range.value, 10), parseInt(rgbRows.g.range.value, 10), parseInt(rgbRows.b.range.value, 10))));
        bindSlider(rgbRows.b, () => setColorFromHex(rgbToHex(parseInt(rgbRows.r.range.value, 10), parseInt(rgbRows.g.range.value, 10), parseInt(rgbRows.b.range.value, 10))));

        bindSlider(hsbRows.h, () => {
            const rgb = hsvToRgb(parseInt(hsbRows.h.range.value, 10), parseInt(hsbRows.s.range.value, 10) / 100, parseInt(hsbRows.v.range.value, 10) / 100);
            setColorFromHex(rgbToHex(rgb.r, rgb.g, rgb.b));
        });
        bindSlider(hsbRows.s, () => {
            const rgb = hsvToRgb(parseInt(hsbRows.h.range.value, 10), parseInt(hsbRows.s.range.value, 10) / 100, parseInt(hsbRows.v.range.value, 10) / 100);
            setColorFromHex(rgbToHex(rgb.r, rgb.g, rgb.b));
        });
        bindSlider(hsbRows.v, () => {
            const rgb = hsvToRgb(parseInt(hsbRows.h.range.value, 10), parseInt(hsbRows.s.range.value, 10) / 100, parseInt(hsbRows.v.range.value, 10) / 100);
            setColorFromHex(rgbToHex(rgb.r, rgb.g, rgb.b));
        });

        bindSlider(grayRow.k, () => {
            const v = Math.round(parseInt(grayRow.k.range.value, 10) / 100 * 255);
            setColorFromHex(rgbToHex(v, v, v));
        });

        bindSlider(cmykRows.c, () => {
            const rgb = cmykToRgb(parseInt(cmykRows.c.range.value, 10), parseInt(cmykRows.m.range.value, 10), parseInt(cmykRows.y.range.value, 10), parseInt(cmykRows.k.range.value, 10));
            setColorFromHex(rgbToHex(rgb.r, rgb.g, rgb.b));
        });
        bindSlider(cmykRows.m, () => {
            const rgb = cmykToRgb(parseInt(cmykRows.c.range.value, 10), parseInt(cmykRows.m.range.value, 10), parseInt(cmykRows.y.range.value, 10), parseInt(cmykRows.k.range.value, 10));
            setColorFromHex(rgbToHex(rgb.r, rgb.g, rgb.b));
        });
        bindSlider(cmykRows.y, () => {
            const rgb = cmykToRgb(parseInt(cmykRows.c.range.value, 10), parseInt(cmykRows.m.range.value, 10), parseInt(cmykRows.y.range.value, 10), parseInt(cmykRows.k.range.value, 10));
            setColorFromHex(rgbToHex(rgb.r, rgb.g, rgb.b));
        });
        bindSlider(cmykRows.k, () => {
            const rgb = cmykToRgb(parseInt(cmykRows.c.range.value, 10), parseInt(cmykRows.m.range.value, 10), parseInt(cmykRows.y.range.value, 10), parseInt(cmykRows.k.range.value, 10));
            setColorFromHex(rgbToHex(rgb.r, rgb.g, rgb.b));
        });
        let pointerDownInside = false;
        backdrop.addEventListener('mousedown', (e) => {
            pointerDownInside = modal.contains(e.target);
        });
        backdrop.addEventListener('mouseup', (e) => {
            if (!pointerDownInside && e.target === backdrop) {
                closeColorModal();
            }
            pointerDownInside = false;
        });
        modal.addEventListener('mousedown', (e) => e.stopPropagation());
        modal.addEventListener('click', (e) => e.stopPropagation());
        setColorFromHex(colorPickerState.recent[0] || '#FFFFFF');
    }

    renderRecentSwatches(onPick);
    if (colorPickerState.currentSwatch && colorPickerState.recent[0]) {
        colorPickerState.currentSwatch.style.background = colorPickerState.recent[0];
    }
    colorPickerState.modalBackdrop.style.display = 'block';
    colorPickerState.modal.style.display = 'block';
}

function closeColorModal() {
    if (colorPickerState.modalBackdrop) colorPickerState.modalBackdrop.style.display = 'none';
    if (colorPickerState.modal) colorPickerState.modal.style.display = 'none';
}

function drawHueWheel(ctx, w, h) {
    const image = ctx.createImageData(w, h);
    const cx = w / 2;
    const cy = h / 2;
    const r = Math.min(cx, cy) - 2;
    for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
            const dx = x - cx;
            const dy = y - cy;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const idx = (y * w + x) * 4;
            if (dist > r) {
                image.data[idx + 3] = 0;
                continue;
            }
            const hue = (Math.atan2(dy, dx) / (2 * Math.PI) + 0.5) * 360;
            const sat = dist / r;
            const rgb = hsvToRgb(hue, sat, 1);
            image.data[idx] = rgb.r;
            image.data[idx + 1] = rgb.g;
            image.data[idx + 2] = rgb.b;
            image.data[idx + 3] = 255;
        }
    }
    ctx.putImageData(image, 0, 0);
}

function drawSpectrum(ctx, w, h) {
    const image = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
            const hue = (x / (w - 1)) * 360;
            const value = 1 - (y / (h - 1));
            const rgb = hsvToRgb(hue, 1, value);
            const idx = (y * w + x) * 4;
            image.data[idx] = rgb.r;
            image.data[idx + 1] = rgb.g;
            image.data[idx + 2] = rgb.b;
            image.data[idx + 3] = 255;
        }
    }
    ctx.putImageData(image, 0, 0);
}

function getSpectrumColor(ctx, x, y) {
    const data = ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1).data;
    if (data[3] === 0) return null;
    return rgbToHex(data[0], data[1], data[2]);
}

function getWheelColor(ctx, x, y, value) {
    const data = ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1).data;
    if (data[3] === 0) return null;
    const rgb = { r: data[0], g: data[1], b: data[2] };
    const scaled = {
        r: Math.round(rgb.r * value),
        g: Math.round(rgb.g * value),
        b: Math.round(rgb.b * value)
    };
    return rgbToHex(scaled.r, scaled.g, scaled.b);
}

function hsvToRgb(h, s, v) {
    const c = v * s;
    const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    const m = v - c;
    let r = 0, g = 0, b = 0;
    if (h < 60) { r = c; g = x; b = 0; }
    else if (h < 120) { r = x; g = c; b = 0; }
    else if (h < 180) { r = 0; g = c; b = x; }
    else if (h < 240) { r = 0; g = x; b = c; }
    else if (h < 300) { r = x; g = 0; b = c; }
    else { r = c; g = 0; b = x; }
    return {
        r: Math.round((r + m) * 255),
        g: Math.round((g + m) * 255),
        b: Math.round((b + m) * 255)
    };
}

function rgbToHsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const d = max - min;
    let h = 0;
    if (d !== 0) {
        switch (max) {
            case r: h = ((g - b) / d) % 6; break;
            case g: h = (b - r) / d + 2; break;
            case b: h = (r - g) / d + 4; break;
        }
        h = Math.round(h * 60);
        if (h < 0) h += 360;
    }
    const s = max === 0 ? 0 : d / max;
    const v = max;
    return { h, s: Math.round(s * 100), v: Math.round(v * 100) };
}

function rgbToCmyk(r, g, b) {
    const rr = r / 255, gg = g / 255, bb = b / 255;
    const k = 1 - Math.max(rr, gg, bb);
    if (k === 1) return { c: 0, m: 0, y: 0, k: 100 };
    const c = (1 - rr - k) / (1 - k);
    const m = (1 - gg - k) / (1 - k);
    const y = (1 - bb - k) / (1 - k);
    return {
        c: Math.round(c * 100),
        m: Math.round(m * 100),
        y: Math.round(y * 100),
        k: Math.round(k * 100)
    };
}

function cmykToRgb(c, m, y, k) {
    c /= 100; m /= 100; y /= 100; k /= 100;
    const r = 255 * (1 - c) * (1 - k);
    const g = 255 * (1 - m) * (1 - k);
    const b = 255 * (1 - y) * (1 - k);
    return { r: Math.round(r), g: Math.round(g), b: Math.round(b) };
}

function rgbToHex(r, g, b) {
    const toHex = (v) => v.toString(16).padStart(2, '0');
    return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase();
}

function renderRecentSwatches(onPick) {
    const container = colorPickerState.modal?.querySelector('.recent-swatches');
    if (!container) return;
    container.innerHTML = '';
    colorPickerState.recent.forEach(color => {
        const sw = document.createElement('div');
        sw.className = 'recent-swatch';
        sw.style.background = color;
        sw.addEventListener('click', () => onPick(color));
        container.appendChild(sw);
    });
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

class LEDRasterApp {
    constructor() {
        this.project = null;
        this.socket = null;
        this.currentLayer = null;
        this.selectedLayerIds = new Set();
        this.lastSelectedLayerId = null;
        this.selectionAnchorLayerId = null;
        this.customSelectMode = false;
        this.customSelection = new Set();
        this.customDebug = false;
        this.powerCustomSelection = new Set();
        this.powerCustomDebug = false;
        
        // Undo/Redo system
        this.history = [];
        this.historyIndex = -1;
        this.maxHistory = 50;
        
        // Clipboard for copy/paste
        this.clipboard = null;
        
        // Prevent double-delete
        this.deletionInProgress = false;

        // Track whether the initial loadProject() has completed.
        // When true, socket project_data events are reconnects (skip preference enforcement).
        // When false, it's a cold start (allow preferences to apply).
        this._initialLoadComplete = false;

        this.init();
    }
    
    init() {
        window.canvasRenderer = new CanvasRenderer('main-canvas');
        
        // Check server session FIRST - if server restarted, clear localStorage
        this.checkServerSession().then(() => {
            this.connectWebSocket();
            this.loadProject();
            this.setupEventListeners();
            sendClientLog('app_init', { ua: navigator.userAgent });
        });
    }
    
    // Check if server has restarted - if so, clear localStorage
    async checkServerSession() {
        try {
            const response = await fetch('/api/server-session');
            const data = await response.json();
            const savedSessionId = localStorage.getItem('ledRasterServerSession');
            
            if (savedSessionId !== data.session_id) {
                // Server has restarted - clear all localStorage and use defaults
                console.log('Server restarted - clearing localStorage and using defaults');
                localStorage.removeItem('ledRasterSize');
                localStorage.removeItem('ledRasterClientProps');
                localStorage.removeItem('ledRasterPropsVersion');
                localStorage.setItem('ledRasterServerSession', data.session_id);
                // Apply preferences-based raster size after reset
                this.loadRasterSize();
            } else {
                // Same server session - load from localStorage
                console.log('Same server session - loading from localStorage');
                this.loadRasterSize();
            }
        } catch (e) {
            console.error('Error checking server session:', e);
            // On error, just load from localStorage
            this.loadRasterSize();
        }
    }
    
    connectWebSocket() {
        this.socket = io();
        this.socket.on('connect', () => {
            document.getElementById('status-message').textContent = 'Connected';
            sendClientLog('socket_connect');
        });
        this.socket.on('disconnect', () => {
            document.getElementById('status-message').textContent = 'Disconnected';
            sendClientLog('socket_disconnect');
        });
        this.socket.on('project_data', (data) => {
            console.log('WEBSOCKET project_data received');
            sendClientLog('socket_project_data', { layers: data.layers ? data.layers.length : 0 });
            
            // Preserve client-side properties when server sends project data
            const savedClientProps = {};
            if (this.project && this.project.layers) {
                this.project.layers.forEach(layer => {
                    savedClientProps[layer.id] = this.extractClientSideProps(layer);
                });
            }
            
            // On reconnect, preserve the current raster size (it may have been
            // set by preferences or user action). Only apply the server's raster
            // on cold start when no preference override will follow.
            const preserveRaster = this._initialLoadComplete;
            const prevRasterW = preserveRaster ? window.canvasRenderer.rasterWidth : null;
            const prevRasterH = preserveRaster ? window.canvasRenderer.rasterHeight : null;

            this.project = data;
            this.dedupeProjectLayers('socket_project_data');
            if (data && data.raster_width && data.raster_height) {
                window.canvasRenderer.rasterWidth = data.raster_width;
                window.canvasRenderer.rasterHeight = data.raster_height;
                const rw = document.getElementById('toolbar-raster-width');
                const rh = document.getElementById('toolbar-raster-height');
                if (rw) rw.value = data.raster_width;
                if (rh) rh.value = data.raster_height;
                this.saveRasterSize();
            }

            // On reconnect, restore the raster size we had before the server
            // overwrote it with its default.
            if (preserveRaster && prevRasterW && prevRasterH) {
                this.project.raster_width = prevRasterW;
                this.project.raster_height = prevRasterH;
                window.canvasRenderer.rasterWidth = prevRasterW;
                window.canvasRenderer.rasterHeight = prevRasterH;
                const rw = document.getElementById('toolbar-raster-width');
                const rh = document.getElementById('toolbar-raster-height');
                if (rw) rw.value = prevRasterW;
                if (rh) rh.value = prevRasterH;
            }

            // Restore client-side properties and layer defaults.
            // On reconnect (after sleep), skip preference enforcement — the project
            // already has the correct state from before the disconnect.
            this.loadClientSideProperties({ skipPreferences: this._initialLoadComplete });
            
            // Also restore any in-memory props we had
            if (this.project && this.project.layers) {
                this.project.layers.forEach(layer => {
                    const memProps = savedClientProps[layer.id];
                    if (memProps) {
                        // Only apply if the value was actually set (not undefined)
                        Object.keys(memProps).forEach(key => {
                            if (memProps[key] !== undefined) {
                                layer[key] = memProps[key];
                            }
                        });
                    }
                });
            }
            
            // Re-select current layer to sync currentLayer reference
            if (this.currentLayer) {
                const layerId = this.currentLayer.id;
                const updatedLayer = this.project.layers.find(l => l.id === layerId);
                if (updatedLayer) {
                    this.currentLayer = updatedLayer;
                }
            }
            
            this.updateUI();
        });
        this.socket.on('layer_updated', (layer) => {
            console.log('WEBSOCKET layer_updated received for layer:', layer.id);
            sendClientLog('socket_layer_updated', { id: layer.id });
            const index = this.project.layers.findIndex(l => l.id === layer.id);
            if (index >= 0) {
                // Preserve client-side properties when server sends layer update
                const clientProps = this.extractClientSideProps(this.project.layers[index]);
                this.project.layers[index] = layer;
                
                // Restore client props
                Object.keys(clientProps).forEach(key => {
                    if (clientProps[key] !== undefined) {
                        this.project.layers[index][key] = clientProps[key];
                    }
                });
                
                if (this.currentLayer && this.currentLayer.id === layer.id) {
                    this.currentLayer = this.project.layers[index];
                }
                this.dedupeProjectLayers('socket_layer_updated');
                this.updateUI();
            } else {
                this.upsertProjectLayer(layer);
                this.dedupeProjectLayers('socket_layer_updated_upsert');
                this.updateUI();
            }
        });
    }
    
    // Extract client-side only properties from a layer
    extractClientSideProps(layer) {
        return {
            dataFlowColor: layer.dataFlowColor,
            arrowColor: layer.arrowColor,
            dataFlowLabelSize: layer.dataFlowLabelSize,
            arrowLineWidth: layer.arrowLineWidth,
            primaryColor: layer.primaryColor,
            primaryTextColor: layer.primaryTextColor,
            backupColor: layer.backupColor,
            backupTextColor: layer.backupTextColor,
            randomDataColors: layer.randomDataColors,
            flowPattern: layer.flowPattern,
            bitDepth: layer.bitDepth,
            frameRate: layer.frameRate,
            processorType: layer.processorType,
            portMappingMode: layer.portMappingMode,
            portLabelTemplatePrimary: layer.portLabelTemplatePrimary,
            portLabelTemplateReturn: layer.portLabelTemplateReturn,
            portLabelOverridesPrimary: layer.portLabelOverridesPrimary,
            portLabelOverridesReturn: layer.portLabelOverridesReturn,
            customPortPaths: layer.customPortPaths,
            customPortIndex: layer.customPortIndex,
            screenNameSizeCabinet: layer.screenNameSizeCabinet,
            screenNameSizeDataFlow: layer.screenNameSizeDataFlow,
            screenNameSizePower: layer.screenNameSizePower,
            screenNameOffsetXCabinet: layer.screenNameOffsetXCabinet,
            screenNameOffsetYCabinet: layer.screenNameOffsetYCabinet,
            screenNameOffsetXDataFlow: layer.screenNameOffsetXDataFlow,
            screenNameOffsetYDataFlow: layer.screenNameOffsetYDataFlow,
            screenNameOffsetXPower: layer.screenNameOffsetXPower,
            screenNameOffsetYPower: layer.screenNameOffsetYPower,
            showDataFlowPortInfo: layer.showDataFlowPortInfo,
            showPowerCircuitInfo: layer.showPowerCircuitInfo,
            powerVoltage: layer.powerVoltage,
            powerVoltageCustom: layer.powerVoltageCustom,
            powerAmperage: layer.powerAmperage,
            powerAmperageCustom: layer.powerAmperageCustom,
            panelWatts: layer.panelWatts,
            powerMaximize: layer.powerMaximize,
            powerOrganized: layer.powerOrganized,
            powerCustomPath: layer.powerCustomPath,
            powerFlowPattern: layer.powerFlowPattern,
            powerLineWidth: layer.powerLineWidth,
            powerLineColor: layer.powerLineColor,
            powerArrowColor: layer.powerArrowColor,
            powerRandomColors: layer.powerRandomColors,
            powerColorCodedView: layer.powerColorCodedView,
            powerCircuitColors: layer.powerCircuitColors,
            powerLabelSize: layer.powerLabelSize,
            powerLabelBgColor: layer.powerLabelBgColor,
            powerLabelTextColor: layer.powerLabelTextColor,
            powerLabelTemplate: layer.powerLabelTemplate,
            powerLabelOverrides: layer.powerLabelOverrides,
            powerCustomPaths: layer.powerCustomPaths,
            powerCustomIndex: layer.powerCustomIndex,
            border_color_pixel: layer.border_color_pixel,
            border_color_cabinet: layer.border_color_cabinet,
            border_color_data: layer.border_color_data,
            border_color_power: layer.border_color_power,
            weight_unit: layer.weight_unit,
            panel_weight: layer.panel_weight,
            infoLabelSize: layer.infoLabelSize
        };
    }
    
    loadProject() {
        fetch('/api/project')
            .then(res => res.json())
            .then(data => {
                this.project = data;
                this.dedupeProjectLayers('load_project');
                if (data && data.raster_width && data.raster_height) {
                    window.canvasRenderer.rasterWidth = data.raster_width;
                    window.canvasRenderer.rasterHeight = data.raster_height;
                    const rw = document.getElementById('toolbar-raster-width');
                    const rh = document.getElementById('toolbar-raster-height');
                    if (rw) rw.value = data.raster_width;
                    if (rh) rh.value = data.raster_height;
                    this.saveRasterSize();
                }
                sendClientLog('load_project', { name: data.name, layers: data.layers ? data.layers.length : 0 });
                
                // Load client-side properties from localStorage
                this.loadClientSideProperties();
                
                // Auto-select first layer BEFORE updateUI so render has correct data
                if (this.project.layers && this.project.layers.length > 0) {
                    this.selectLayer(this.project.layers[0]);
                    // Never force-apply defaults to arbitrary loaded projects.
                    // Only apply to true startup default project when criteria match.
                    this.applyPreferencesToDefaultLayerIfMatch(false);
                }
                
                // Save initial state for undo/redo
                this.resetHistory('Initial State');

                // Mark initial load complete — subsequent socket project_data
                // events are reconnects and should not re-apply preferences.
                this._initialLoadComplete = true;

                // Default to Fit view on load
                setTimeout(() => {
                    window.canvasRenderer.fitToView();
                }, 100);
            });
    }
    
    // Load client-side properties from localStorage
    loadClientSideProperties({ skipPreferences = false } = {}) {
        if (!this.project || !this.project.layers) return;
        const prefs = this.getPreferences();
        
        const savedProps = localStorage.getItem('ledRasterClientProps');
        const savedVersion = localStorage.getItem('ledRasterPropsVersion');
        const currentVersion = '0.4.7'; // Increment to force reset of all localStorage settings
        
        // If version mismatch, clear old props and use fresh defaults
        if (savedVersion !== currentVersion) {
            console.log('Props version mismatch, resetting to new defaults');
            localStorage.removeItem('ledRasterClientProps');
            localStorage.removeItem('ledRasterSize'); // Also reset raster size
            localStorage.setItem('ledRasterPropsVersion', currentVersion);
            // Don't load from localStorage, just use defaults below
            window.canvasRenderer.rasterWidth = prefs.rasterWidth;
            window.canvasRenderer.rasterHeight = prefs.rasterHeight;
            document.getElementById('toolbar-raster-width').value = prefs.rasterWidth;
            document.getElementById('toolbar-raster-height').value = prefs.rasterHeight;
            this.saveRasterSize();
        } else if (savedProps && this.shouldUseSavedClientProps()) {
            // First, apply any saved properties from localStorage
            try {
                const propsMap = JSON.parse(savedProps);
                
                this.project.layers.forEach(layer => {
                    const layerProps = propsMap[layer.id];
                    if (layerProps) {
                        // Only set properties that are actually defined in localStorage
                        if (layerProps.dataFlowColor !== undefined) layer.dataFlowColor = layerProps.dataFlowColor;
                        if (layerProps.arrowColor !== undefined) layer.arrowColor = layerProps.arrowColor;
                        if (layerProps.dataFlowLabelSize !== undefined) layer.dataFlowLabelSize = layerProps.dataFlowLabelSize;
                        if (layerProps.arrowLineWidth !== undefined) layer.arrowLineWidth = layerProps.arrowLineWidth;
                        if (layerProps.primaryColor !== undefined) layer.primaryColor = layerProps.primaryColor;
                        if (layerProps.primaryTextColor !== undefined) layer.primaryTextColor = layerProps.primaryTextColor;
                        if (layerProps.backupColor !== undefined) layer.backupColor = layerProps.backupColor;
                        if (layerProps.backupTextColor !== undefined) layer.backupTextColor = layerProps.backupTextColor;
                        if (layerProps.randomDataColors !== undefined) layer.randomDataColors = layerProps.randomDataColors;
                        if (layerProps.flowPattern !== undefined) layer.flowPattern = layerProps.flowPattern;
                        if (layerProps.bitDepth !== undefined) layer.bitDepth = layerProps.bitDepth;
                        if (layerProps.frameRate !== undefined) layer.frameRate = layerProps.frameRate;
                        if (layerProps.processorType !== undefined) layer.processorType = layerProps.processorType;
                        if (layerProps.portMappingMode !== undefined) layer.portMappingMode = layerProps.portMappingMode;
                        if (layerProps.portLabelTemplatePrimary !== undefined) layer.portLabelTemplatePrimary = layerProps.portLabelTemplatePrimary;
                        if (layerProps.portLabelTemplateReturn !== undefined) layer.portLabelTemplateReturn = layerProps.portLabelTemplateReturn;
                        if (layerProps.portLabelOverridesPrimary !== undefined) layer.portLabelOverridesPrimary = layerProps.portLabelOverridesPrimary;
                        if (layerProps.portLabelOverridesReturn !== undefined) layer.portLabelOverridesReturn = layerProps.portLabelOverridesReturn;
                        if (layerProps.customPortPaths !== undefined) layer.customPortPaths = layerProps.customPortPaths;
                        if (layerProps.customPortIndex !== undefined) layer.customPortIndex = layerProps.customPortIndex;
                        if (layerProps.powerVoltage !== undefined) layer.powerVoltage = layerProps.powerVoltage;
                        if (layerProps.powerVoltageCustom !== undefined) layer.powerVoltageCustom = layerProps.powerVoltageCustom;
                        if (layerProps.powerAmperage !== undefined) layer.powerAmperage = layerProps.powerAmperage;
                        if (layerProps.powerAmperageCustom !== undefined) layer.powerAmperageCustom = layerProps.powerAmperageCustom;
                        if (layerProps.panelWatts !== undefined) layer.panelWatts = layerProps.panelWatts;
                        if (layerProps.powerMaximize !== undefined) layer.powerMaximize = layerProps.powerMaximize;
                        if (layerProps.powerOrganized !== undefined) layer.powerOrganized = layerProps.powerOrganized;
                        if (layerProps.powerCustomPath !== undefined) layer.powerCustomPath = layerProps.powerCustomPath;
                        if (layerProps.powerFlowPattern !== undefined) layer.powerFlowPattern = layerProps.powerFlowPattern;
                        if (layerProps.powerLineWidth !== undefined) layer.powerLineWidth = layerProps.powerLineWidth;
                        if (layerProps.powerLineColor !== undefined) layer.powerLineColor = layerProps.powerLineColor;
                        if (layerProps.powerArrowColor !== undefined) layer.powerArrowColor = layerProps.powerArrowColor;
                        if (layerProps.powerRandomColors !== undefined) layer.powerRandomColors = layerProps.powerRandomColors;
                        if (layerProps.powerColorCodedView !== undefined) layer.powerColorCodedView = layerProps.powerColorCodedView;
                        if (layerProps.powerCircuitColors !== undefined) layer.powerCircuitColors = layerProps.powerCircuitColors;
                        if (layerProps.powerLabelSize !== undefined) layer.powerLabelSize = layerProps.powerLabelSize;
                        if (layerProps.powerLabelBgColor !== undefined) layer.powerLabelBgColor = layerProps.powerLabelBgColor;
                        if (layerProps.powerLabelTextColor !== undefined) layer.powerLabelTextColor = layerProps.powerLabelTextColor;
                        if (layerProps.powerLabelTemplate !== undefined) layer.powerLabelTemplate = layerProps.powerLabelTemplate;
                        if (layerProps.powerLabelOverrides !== undefined) layer.powerLabelOverrides = layerProps.powerLabelOverrides;
                        if (layerProps.powerCustomPaths !== undefined) layer.powerCustomPaths = layerProps.powerCustomPaths;
                        if (layerProps.powerCustomIndex !== undefined) layer.powerCustomIndex = layerProps.powerCustomIndex;
                        if (layerProps.border_color_pixel !== undefined) layer.border_color_pixel = layerProps.border_color_pixel;
                        if (layerProps.border_color_cabinet !== undefined) layer.border_color_cabinet = layerProps.border_color_cabinet;
                        if (layerProps.border_color_data !== undefined) layer.border_color_data = layerProps.border_color_data;
                        if (layerProps.border_color_power !== undefined) layer.border_color_power = layerProps.border_color_power;
                        if (layerProps.weight_unit !== undefined) layer.weight_unit = layerProps.weight_unit;
                        if (layerProps.panel_weight !== undefined) layer.panel_weight = layerProps.panel_weight;
                        if (layerProps.infoLabelSize !== undefined) layer.infoLabelSize = layerProps.infoLabelSize;
                        if (layerProps.screenNameSizeCabinet !== undefined) layer.screenNameSizeCabinet = layerProps.screenNameSizeCabinet;
                        if (layerProps.screenNameSizeDataFlow !== undefined) layer.screenNameSizeDataFlow = layerProps.screenNameSizeDataFlow;
                        if (layerProps.screenNameSizePower !== undefined) layer.screenNameSizePower = layerProps.screenNameSizePower;
                        if (layerProps.showDataFlowPortInfo !== undefined) layer.showDataFlowPortInfo = layerProps.showDataFlowPortInfo;
                        if (layerProps.showPowerCircuitInfo !== undefined) layer.showPowerCircuitInfo = layerProps.showPowerCircuitInfo;
                        if (layerProps.screenNameOffsetXCabinet !== undefined) layer.screenNameOffsetXCabinet = layerProps.screenNameOffsetXCabinet;
                        if (layerProps.screenNameOffsetYCabinet !== undefined) layer.screenNameOffsetYCabinet = layerProps.screenNameOffsetYCabinet;
                        if (layerProps.screenNameOffsetXDataFlow !== undefined) layer.screenNameOffsetXDataFlow = layerProps.screenNameOffsetXDataFlow;
                        if (layerProps.screenNameOffsetYDataFlow !== undefined) layer.screenNameOffsetYDataFlow = layerProps.screenNameOffsetYDataFlow;
                        if (layerProps.screenNameOffsetXPower !== undefined) layer.screenNameOffsetXPower = layerProps.screenNameOffsetXPower;
                        if (layerProps.screenNameOffsetYPower !== undefined) layer.screenNameOffsetYPower = layerProps.screenNameOffsetYPower;
                    }
                });
            } catch (e) {
                console.error('Error loading client-side properties:', e);
            }
        } else if (savedProps) {
            // Avoid cross-project contamination from id-based local props.
            sendClientLog('skip_saved_client_props', {
                projectName: this.project && this.project.name,
                layerCount: this.project && this.project.layers ? this.project.layers.length : 0
            });
        }
        
        // Then, initialize defaults for any properties that are still undefined
        this.project.layers.forEach(layer => {
            if (layer.arrowLineWidth === undefined) layer.arrowLineWidth = 4;
            if (layer.arrowColor === undefined) layer.arrowColor = '#0042AA';
            if (layer.dataFlowColor === undefined) layer.dataFlowColor = '#FFFFFF';
            if (layer.dataFlowLabelSize === undefined) layer.dataFlowLabelSize = prefs.dataLabelSize || 30;
            if (layer.primaryColor === undefined) layer.primaryColor = '#00FF00';
            if (layer.primaryTextColor === undefined) layer.primaryTextColor = '#000000';
            if (layer.backupColor === undefined) layer.backupColor = '#FF0000';
            if (layer.backupTextColor === undefined) layer.backupTextColor = '#FFFFFF';
            if (layer.flowPattern === undefined) layer.flowPattern = prefs.flowPattern || 'tl-h';
            if (layer.bitDepth === undefined) layer.bitDepth = prefs.bitDepth;
            if (layer.frameRate === undefined) layer.frameRate = prefs.frameRate;
            if (layer.processorType === undefined) layer.processorType = prefs.processorType;
            if (layer.processorType === 'novastar-1g') layer.processorType = 'novastar-coex-1g';
            if (layer.processorType === 'novastar-armor-1g') layer.processorType = 'novastar-armor';
            if (layer.portMappingMode === undefined) layer.portMappingMode = 'organized';
            if (layer.portLabelTemplatePrimary === undefined) layer.portLabelTemplatePrimary = 'P#';
            if (layer.portLabelTemplateReturn === undefined) layer.portLabelTemplateReturn = 'R#';
            if (typeof layer.portLabelTemplatePrimary === 'string' && layer.portLabelTemplatePrimary.includes('{n}')) {
                layer.portLabelTemplatePrimary = layer.portLabelTemplatePrimary.replace('{n}', '#');
            }
            if (typeof layer.portLabelTemplateReturn === 'string' && layer.portLabelTemplateReturn.includes('{n}')) {
                layer.portLabelTemplateReturn = layer.portLabelTemplateReturn.replace('{n}', '#');
            }
            if (layer.portLabelOverridesPrimary === undefined) layer.portLabelOverridesPrimary = {};
            if (layer.portLabelOverridesReturn === undefined) layer.portLabelOverridesReturn = {};
            if (layer.customPortPaths === undefined) layer.customPortPaths = {};
            if (layer.customPortIndex === undefined) layer.customPortIndex = 1;
            if (layer.screenNameSizeCabinet === undefined) layer.screenNameSizeCabinet = 14;
            if (layer.screenNameSizeDataFlow === undefined) layer.screenNameSizeDataFlow = 14;
            if (layer.screenNameSizePower === undefined) layer.screenNameSizePower = 14;
            if (layer.powerVoltage === undefined) layer.powerVoltage = prefs.powerVoltage;
            if (layer.powerVoltageCustom === undefined) layer.powerVoltageCustom = prefs.powerVoltage;
            if (layer.powerAmperage === undefined) layer.powerAmperage = prefs.powerAmperage;
            if (layer.powerAmperageCustom === undefined) layer.powerAmperageCustom = prefs.powerAmperage;
            if (layer.panelWatts === undefined) layer.panelWatts = prefs.powerWatts;
            if (layer.powerMaximize === undefined) layer.powerMaximize = false;
            if (layer.powerOrganized === undefined) layer.powerOrganized = true;
            if (layer.powerCustomPath === undefined) layer.powerCustomPath = false;
            if (layer.powerFlowPattern === undefined || layer.powerFlowPattern === null || layer.powerFlowPattern === '') {
                layer.powerFlowPattern = layer.flowPattern || prefs.powerFlowPattern || 'tl-h';
            }
            if (layer.powerLineWidth === undefined) layer.powerLineWidth = 8;
            if (layer.powerLineColor === undefined) layer.powerLineColor = '#FF0000';
            if (layer.powerArrowColor === undefined) layer.powerArrowColor = '#0042AA';
            if (layer.powerRandomColors === undefined) layer.powerRandomColors = false;
            if (layer.powerColorCodedView === undefined) layer.powerColorCodedView = false;
            layer.powerCircuitColors = this.normalizePowerCircuitColors(layer.powerCircuitColors);
            if (layer.powerLabelSize === undefined) layer.powerLabelSize = prefs.powerLabelSize || 14;
            if (layer.powerLabelBgColor === undefined) layer.powerLabelBgColor = '#D95000';
            if (layer.powerLabelTextColor === undefined) layer.powerLabelTextColor = '#000000';
            if (layer.powerLabelTemplate === undefined) layer.powerLabelTemplate = 'S1-#';
            if (layer.powerLabelOverrides === undefined) layer.powerLabelOverrides = {};
                if (layer.powerCustomPaths === undefined) layer.powerCustomPaths = {};
            if (layer.powerCustomIndex === undefined) layer.powerCustomIndex = 1;
            if (layer.halfFirstColumn === undefined) layer.halfFirstColumn = false;
            if (layer.halfLastColumn === undefined) layer.halfLastColumn = false;
            if (layer.halfFirstRow === undefined) layer.halfFirstRow = false;
            if (layer.halfLastRow === undefined) layer.halfLastRow = false;
            if (layer.weight_unit === undefined) layer.weight_unit = prefs.weightUnit || 'kg';
            if (layer.panel_weight === undefined) layer.panel_weight = prefs.panelWeight || 20;
            if (layer.infoLabelSize === undefined) layer.infoLabelSize = 14;
            if (layer.showDataFlowPortInfo === undefined) layer.showDataFlowPortInfo = false;
            if (layer.showPowerCircuitInfo === undefined) layer.showPowerCircuitInfo = false;
        });

        // For startup factory-default project only, enforce saved preference defaults.
        // Skip if preferences were already applied this session (e.g. socket reconnect after sleep).
        // Use server-side is_pristine flag to distinguish a true fresh default project from a
        // loaded project that happens to be named "Untitled Project".
        const startupDefaultMatch =
            !skipPreferences &&
            this.project &&
            this.project.is_pristine === true &&
            this.project.name === 'Untitled Project' &&
            this.project.layers &&
            this.project.layers.length === 1;
        if (startupDefaultMatch) {
            const layer = this.project.layers[0];
            layer.processorType = prefs.processorType;
            layer.bitDepth = prefs.bitDepth;
            layer.frameRate = prefs.frameRate;
            layer.powerVoltage = prefs.powerVoltage;
            layer.powerVoltageCustom = prefs.powerVoltage;
            layer.powerAmperage = prefs.powerAmperage;
            layer.powerAmperageCustom = prefs.powerAmperage;
            layer.panelWatts = prefs.powerWatts;
            layer.dataFlowLabelSize = prefs.dataLabelSize || 30;
            layer.powerLabelSize = prefs.powerLabelSize || 14;
            layer.primaryTextColor = layer.primaryTextColor || '#000000';
            layer.backupTextColor = layer.backupTextColor || '#FFFFFF';
            layer.powerLabelBgColor = layer.powerLabelBgColor || '#D95000';
            layer.powerLabelTextColor = layer.powerLabelTextColor || '#000000';
            layer.panel_weight = prefs.panelWeight || 20;
            layer.weight_unit = prefs.weightUnit || 'kg';
            // Apply default raster on startup so app open matches Preferences
            this.project.raster_width = prefs.rasterWidth;
            this.project.raster_height = prefs.rasterHeight;
            if (window.canvasRenderer) {
                window.canvasRenderer.rasterWidth = prefs.rasterWidth;
                window.canvasRenderer.rasterHeight = prefs.rasterHeight;
            }
            const rw = document.getElementById('toolbar-raster-width');
            const rh = document.getElementById('toolbar-raster-height');
            if (rw) rw.value = prefs.rasterWidth;
            if (rh) rh.value = prefs.rasterHeight;
            this.saveRasterSize();
            // Sync raster size to server so subsequent socket project_data
            // echoes return the preference values, not the server default.
            fetch('/api/project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    raster_width: prefs.rasterWidth,
                    raster_height: prefs.rasterHeight
                })
            });
            sendClientLog('startup_preferences_enforced', {
                processorType: layer.processorType,
                bitDepth: layer.bitDepth,
                frameRate: layer.frameRate,
                powerVoltage: layer.powerVoltage,
                powerAmperage: layer.powerAmperage,
                panelWatts: layer.panelWatts,
                rasterWidth: this.project.raster_width,
                rasterHeight: this.project.raster_height
            });
        }

        console.log('LOADED CLIENT PROPS - first layer:', {
            arrowLineWidth: this.project.layers[0]?.arrowLineWidth,
            arrowColor: this.project.layers[0]?.arrowColor,
            dataFlowLabelSize: this.project.layers[0]?.dataFlowLabelSize
        });
    }
    
    // Save client-side properties to localStorage
    saveClientSideProperties() {
        if (!this.project || !this.project.layers) return;
        
        const propsMap = {};
        
        this.project.layers.forEach(layer => {
            propsMap[layer.id] = {
                // Data Flow properties
                dataFlowColor: layer.dataFlowColor,
                arrowColor: layer.arrowColor,
                dataFlowLabelSize: layer.dataFlowLabelSize,
                arrowLineWidth: layer.arrowLineWidth,
                primaryColor: layer.primaryColor,
                primaryTextColor: layer.primaryTextColor,
                backupColor: layer.backupColor,
                backupTextColor: layer.backupTextColor,
                randomDataColors: layer.randomDataColors,
                flowPattern: layer.flowPattern,
                bitDepth: layer.bitDepth,
                frameRate: layer.frameRate,
                processorType: layer.processorType,
                portMappingMode: layer.portMappingMode,
                portLabelTemplatePrimary: layer.portLabelTemplatePrimary,
                portLabelTemplateReturn: layer.portLabelTemplateReturn,
                portLabelOverridesPrimary: layer.portLabelOverridesPrimary,
                portLabelOverridesReturn: layer.portLabelOverridesReturn,
                customPortPaths: layer.customPortPaths,
                customPortIndex: layer.customPortIndex,
                screenNameSizeCabinet: layer.screenNameSizeCabinet,
                screenNameSizeDataFlow: layer.screenNameSizeDataFlow,
                screenNameSizePower: layer.screenNameSizePower,
                
                // Tab-specific screen name positions
                screenNameOffsetXCabinet: layer.screenNameOffsetXCabinet,
                screenNameOffsetYCabinet: layer.screenNameOffsetYCabinet,
                screenNameOffsetXDataFlow: layer.screenNameOffsetXDataFlow,
                screenNameOffsetYDataFlow: layer.screenNameOffsetYDataFlow,
                screenNameOffsetXPower: layer.screenNameOffsetXPower,
                screenNameOffsetYPower: layer.screenNameOffsetYPower,
                powerVoltage: layer.powerVoltage,
                powerVoltageCustom: layer.powerVoltageCustom,
                powerAmperage: layer.powerAmperage,
                powerAmperageCustom: layer.powerAmperageCustom,
                panelWatts: layer.panelWatts,
                powerMaximize: layer.powerMaximize,
                powerOrganized: layer.powerOrganized,
                powerCustomPath: layer.powerCustomPath,
                powerFlowPattern: layer.powerFlowPattern,
                powerLineWidth: layer.powerLineWidth,
                powerLineColor: layer.powerLineColor,
                powerArrowColor: layer.powerArrowColor,
                powerRandomColors: layer.powerRandomColors,
                powerColorCodedView: layer.powerColorCodedView,
                powerCircuitColors: layer.powerCircuitColors,
                powerLabelSize: layer.powerLabelSize,
                powerLabelBgColor: layer.powerLabelBgColor,
                powerLabelTextColor: layer.powerLabelTextColor,
                powerCustomPaths: layer.powerCustomPaths,
                powerCustomIndex: layer.powerCustomIndex,
                border_color_pixel: layer.border_color_pixel,
                border_color_cabinet: layer.border_color_cabinet,
                border_color_data: layer.border_color_data,
                border_color_power: layer.border_color_power,
                weight_unit: layer.weight_unit,
                panel_weight: layer.panel_weight,
                infoLabelSize: layer.infoLabelSize,
                showDataFlowPortInfo: layer.showDataFlowPortInfo,
                showPowerCircuitInfo: layer.showPowerCircuitInfo
            };
        });
        
        localStorage.setItem('ledRasterClientProps', JSON.stringify(propsMap));
    }
    
    // Save raster size to localStorage
    saveRasterSize() {
        const rasterSize = {
            width: window.canvasRenderer.rasterWidth,
            height: window.canvasRenderer.rasterHeight
        };
        localStorage.setItem('ledRasterSize', JSON.stringify(rasterSize));
    }
    
    // Load raster size from localStorage (checks version first)
    loadRasterSize() {
        // Check version first - if mismatch, clear all saved settings including raster size
        const savedVersion = localStorage.getItem('ledRasterPropsVersion');
        const currentVersion = '0.4.7'; // Must match version in loadClientSideProperties
        
        if (savedVersion !== currentVersion) {
            console.log('Version mismatch in loadRasterSize - clearing ALL localStorage');
            localStorage.removeItem('ledRasterSize');
            localStorage.removeItem('ledRasterClientProps');
            localStorage.setItem('ledRasterPropsVersion', currentVersion);
            const prefs = this.getPreferences();
            window.canvasRenderer.rasterWidth = prefs.rasterWidth;
            window.canvasRenderer.rasterHeight = prefs.rasterHeight;
            document.getElementById('toolbar-raster-width').value = prefs.rasterWidth;
            document.getElementById('toolbar-raster-height').value = prefs.rasterHeight;
            this.saveRasterSize();
            return;
        }
        
        const saved = localStorage.getItem('ledRasterSize');
        if (saved) {
            try {
                const size = JSON.parse(saved);
                if (size.width && size.height) {
                    window.canvasRenderer.rasterWidth = size.width;
                    window.canvasRenderer.rasterHeight = size.height;
                    document.getElementById('toolbar-raster-width').value = size.width;
                    document.getElementById('toolbar-raster-height').value = size.height;
                }
            } catch (e) {
                console.error('Error loading raster size:', e);
            }
        } else {
            const prefs = this.getPreferences();
            window.canvasRenderer.rasterWidth = prefs.rasterWidth;
            window.canvasRenderer.rasterHeight = prefs.rasterHeight;
            document.getElementById('toolbar-raster-width').value = prefs.rasterWidth;
            document.getElementById('toolbar-raster-height').value = prefs.rasterHeight;
            this.saveRasterSize();
        }
    }
    
    createNewProject() {
        fetch('/api/project/new', {
            method: 'POST'
        })
            .then(res => res.json())
            .then(data => {
                this.project = data;
                this.dedupeProjectLayers('new_project');
                sendClientLog('new_project');
                this.updateUI();
                
                // Auto-select first layer if available
                if (this.project.layers && this.project.layers.length > 0) {
                    this.selectLayer(this.project.layers[0]);
                    const prefs = this.getPreferences();
                    this.applyPreferencesToCurrentLayer(prefs);
                } else {
                    this.currentLayer = null;
                }
                
                // Reset raster dimensions to defaults
                const prefs = this.getPreferences();
                window.canvasRenderer.rasterWidth = prefs.rasterWidth;
                window.canvasRenderer.rasterHeight = prefs.rasterHeight;
                document.getElementById('toolbar-raster-width').value = prefs.rasterWidth;
                document.getElementById('toolbar-raster-height').value = prefs.rasterHeight;
                
                // Save the default raster size to localStorage
                // This way refresh after "New" will show defaults
                this.saveRasterSize();
                
                // Clear client props for the new project
                localStorage.removeItem('ledRasterClientProps');
                
                // Fit to view
                setTimeout(() => {
                    window.canvasRenderer.fitToView();
                }, 100);

                // New project starts a fresh undo/redo chain
                this.resetHistory('Initial State');
            });
    }

    applyPreferencesToCurrentLayer(prefs) {
        if (!this.currentLayer) return;
        this.currentLayer.columns = prefs.columns;
        this.currentLayer.rows = prefs.rows;
        this.currentLayer.cabinet_width = prefs.panelWidth;
        this.currentLayer.cabinet_height = prefs.panelHeight;
        this.currentLayer.panel_width_mm = prefs.panelWidthMM;
        this.currentLayer.panel_height_mm = prefs.panelHeightMM;
        this.currentLayer.panel_weight = prefs.panelWeight;
        this.currentLayer.weight_unit = prefs.weightUnit || 'kg';
        this.currentLayer.number_size = prefs.cabinetFontSize;
        this.currentLayer.labelsFontSize = prefs.labelFontSize;
        this.currentLayer.color1 = this.hexToRgb(prefs.color1);
        this.currentLayer.color2 = this.hexToRgb(prefs.color2);
        this.currentLayer.border_color = prefs.borderColor;
        this.currentLayer.border_color_pixel = prefs.borderColor;
        this.currentLayer.border_color_cabinet = prefs.borderColor;
        this.currentLayer.border_color_data = prefs.borderColor;
        this.currentLayer.border_color_power = prefs.borderColor;
        this.currentLayer.flowPattern = prefs.flowPattern;
        this.currentLayer.arrowLineWidth = prefs.dataLineWidth;
        this.currentLayer.dataFlowLabelSize = prefs.dataLabelSize;
        this.currentLayer.powerLineWidth = prefs.powerLineWidth;
        this.currentLayer.powerLabelSize = prefs.powerLabelSize;
        this.currentLayer.primaryTextColor = this.currentLayer.primaryTextColor || '#000000';
        this.currentLayer.backupTextColor = this.currentLayer.backupTextColor || '#FFFFFF';
        this.currentLayer.powerLabelBgColor = this.currentLayer.powerLabelBgColor || '#D95000';
        this.currentLayer.powerLabelTextColor = this.currentLayer.powerLabelTextColor || '#000000';
        this.currentLayer.processorType = prefs.processorType;
        this.currentLayer.bitDepth = prefs.bitDepth;
        this.currentLayer.frameRate = prefs.frameRate;
        this.currentLayer.powerVoltage = prefs.powerVoltage;
        this.currentLayer.powerVoltageCustom = prefs.powerVoltage;
        this.currentLayer.powerAmperage = prefs.powerAmperage;
        this.currentLayer.powerAmperageCustom = prefs.powerAmperage;
        this.currentLayer.panelWatts = prefs.powerWatts;
        this.currentLayer.powerFlowPattern = prefs.powerFlowPattern || 'tl-h';
        this.loadLayerToInputs();
        this.updateLayer();
    }

    isFactoryDefaultLayer(layer) {
        if (!layer) return false;
        return (
            (layer.name || '') === 'Screen1' &&
            (Number(layer.columns) || 0) === 8 &&
            (Number(layer.rows) || 0) === 5 &&
            (Number(layer.cabinet_width) || 0) === 128 &&
            (Number(layer.cabinet_height) || 0) === 128 &&
            (Number(layer.offset_x) || 0) === 0 &&
            (Number(layer.offset_y) || 0) === 0 &&
            !layer.halfFirstColumn &&
            !layer.halfLastColumn &&
            !layer.halfFirstRow &&
            !layer.halfLastRow
        );
    }

    shouldApplyStartupPreferences() {
        if (!this.project || !this.project.layers || this.project.layers.length !== 1) return false;
        if (!this.currentLayer) return false;
        if (this.project.is_pristine !== true) return false;
        if (this.project.name !== 'Untitled Project') return false;
        return true;
    }

    shouldUseSavedClientProps() {
        // Local client props are keyed only by layer id. Restrict use to the
        // untouched startup default project so they don't bleed into loaded files.
        if (!this.project || !this.project.layers || this.project.layers.length !== 1) return false;
        return this.project.name === 'Untitled Project';
    }

    applyPreferencesToDefaultLayerIfMatch(force = false) {
        if (!this.shouldApplyStartupPreferences()) return;
        const prefs = this.getPreferences();
        sendClientLog('apply_preferences_to_default_layer', {
            force: !!force,
            projectName: this.project.name,
            processorType: prefs.processorType,
            bitDepth: prefs.bitDepth,
            frameRate: prefs.frameRate
        });
        this.applyPreferencesToCurrentLayer(prefs);
    }
    
    updateUI() {
        
        document.getElementById('project-name').value = this.project.name;
        
        this.renderLayers();
        
        if (window.canvasRenderer) {
            if (window.canvasRenderer.viewMode === 'data-flow' && this.currentLayer) {
                this.updatePortCapacityDisplay();
                this.updatePortLabelEditor();
                this.updateCustomFlowUI();
            } else if (window.canvasRenderer.viewMode === 'power' && this.currentLayer) {
                this.updatePowerCapacityDisplay();
                this.updatePowerLabelEditor();
                this.updateCustomPowerUI();
            }
            window.canvasRenderer.render();
        }
    }
    
    setupEventListeners() {
        // Project name editing
        const projectNameInput = document.getElementById('project-name');
        if (projectNameInput) {
            projectNameInput.addEventListener('change', () => {
                if (this.project) {
                    this.project.name = projectNameInput.value.trim() || 'Untitled Project';
                    this.saveProject();
                }
            });
        }
        
        // View tabs
        document.querySelectorAll('.view-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.view-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const mode = tab.getAttribute('data-mode');
                
                // Show/hide appropriate sidebar panels
                document.querySelectorAll('.tab-panel').forEach(panel => {
                    if (panel.getAttribute('data-tab') === mode) {
                        panel.style.display = 'block';
                    } else {
                        panel.style.display = 'none';
                    }
                });
                
                window.canvasRenderer.setViewMode(mode);
                sendClientLog('tab_switch', {
                    tab: mode,
                    currentLayer: this.currentLayer ? { id: this.currentLayer.id, name: this.currentLayer.name } : null,
                    selectedLayers: this.selectedLayerIds ? [...this.selectedLayerIds] : []
                });
                this.updateLayerPanelVisibility(!!this.currentLayer && (this.currentLayer.type || 'screen') === 'image');
                this.loadLayerToInputs();
                if (mode === 'data-flow' && this.currentLayer) {
                    this.updatePortCapacityDisplay();
                    this.updatePortLabelEditor();
                    this.updateCustomFlowUI();
                    // Defer a second refresh to ensure DOM is fully painted
                    setTimeout(() => {
                        if (this.currentLayer) {
                            this.updatePortCapacityDisplay();
                            this.updatePortLabelEditor();
                        }
                    }, 50);
                } else if (mode === 'power' && this.currentLayer) {
                    this.updatePowerCapacityDisplay();
                    this.updateCustomPowerUI();
                    this.updatePowerLabelEditor();
                    setTimeout(() => {
                        if (this.currentLayer) {
                            this.updatePowerCapacityDisplay();
                            this.updatePowerLabelEditor();
                        }
                    }, 50);
                }
            });
        });
        
        document.getElementById('btn-add-layer').addEventListener('click', () => {
            this.addLayer();
        });
        const addImageBtn = document.getElementById('btn-add-image');
        const addImageInput = document.getElementById('add-image-input');
        if (addImageBtn && addImageInput) {
            addImageBtn.addEventListener('click', () => {
                this.imageFileAction = 'add';
                addImageInput.click();
            });
            addImageInput.addEventListener('change', (e) => {
                this.handleImageFileSelection(e);
            });
        }
        const replaceImageBtn = document.getElementById('btn-replace-image');
        if (replaceImageBtn && addImageInput) {
            replaceImageBtn.addEventListener('click', () => {
                if (!this.currentLayer || this.currentLayer.type !== 'image') return;
                this.imageFileAction = 'replace';
                addImageInput.click();
            });
        }

        const layerUpBtn = document.getElementById('btn-layer-up');
        const layerDownBtn = document.getElementById('btn-layer-down');
        if (layerUpBtn) {
            layerUpBtn.addEventListener('click', () => {
                if (this.currentLayer) {
                    this.moveLayerById(this.currentLayer.id, -1);
                }
            });
        }
        if (layerDownBtn) {
            layerDownBtn.addEventListener('click', () => {
                if (this.currentLayer) {
                    this.moveLayerById(this.currentLayer.id, 1);
                }
            });
        }

        const toggleLockBtn = document.getElementById('toggle-lock-selected');
        if (toggleLockBtn) {
            toggleLockBtn.addEventListener('click', () => {
                this.toggleLockOnSelected();
            });
        }
        
        document.getElementById('btn-zoom-in').addEventListener('click', () => {
            window.canvasRenderer.zoomIn();
        });
        document.getElementById('btn-zoom-out').addEventListener('click', () => {
            window.canvasRenderer.zoomOut();
        });
        document.getElementById('btn-fit').addEventListener('click', () => {
            window.canvasRenderer.fitToView();
        });
        document.getElementById('btn-zoom-actual').addEventListener('click', () => {
            window.canvasRenderer.zoomActual();
        });
        
        // Zoom level input - allow typing a percentage
        const zoomInput = document.getElementById('zoom-level');
        zoomInput.addEventListener('change', () => {
            let value = zoomInput.value.replace('%', '').trim();
            let percent = parseFloat(value);
            if (!isNaN(percent) && percent > 0) {
                window.canvasRenderer.setZoom(percent / 100);
            }
            zoomInput.value = `${Math.round(window.canvasRenderer.zoom * 100)}%`;
        });
        zoomInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                zoomInput.blur();
            }
        });
        
        // Magnetic snap toggle
        document.getElementById('magnetic-snap').addEventListener('change', (e) => {
            window.canvasRenderer.magneticSnap = e.target.checked;
        });
        
        ['offset-x', 'offset-y', 'cabinet-width', 'cabinet-height', 
         'screen-columns', 'screen-rows', 'number-size', 'panel-width-mm', 'panel-height-mm', 'panel-weight-kg', 'image-scale', 'image-scale-range'].forEach(id => {
            const input = document.getElementById(id);
            if (input) {
                input.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this._lastChangedInputId = id;
                        this.updateLayerFromInputs();
                        this._lastChangedInputId = null;
                    }
                });
            }
        });
        const imageScaleInput = document.getElementById('image-scale');
        const imageScaleRange = document.getElementById('image-scale-range');
        if (imageScaleInput && imageScaleRange) {
            const applyLiveScale = (value) => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'image') return;
                const pct = Math.max(10, Math.min(500, parseFloat(value) || 100));
                this.currentLayer.imageScale = pct / 100;
                window.canvasRenderer.render();
            };
            const commitScale = () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'image') return;
                this.updateLayers([this.currentLayer], true, 'Image Scale');
            };
            imageScaleInput.addEventListener('input', () => {
                const val = parseFloat(imageScaleInput.value);
                if (!Number.isNaN(val)) {
                    imageScaleRange.value = String(Math.max(10, Math.min(500, val)));
                    applyLiveScale(val);
                }
            });
            imageScaleInput.addEventListener('change', () => {
                commitScale();
            });
            imageScaleRange.addEventListener('input', () => {
                imageScaleInput.value = imageScaleRange.value;
                applyLiveScale(imageScaleRange.value);
            });
            imageScaleRange.addEventListener('change', () => {
                commitScale();
            });
        }
        
        const showNumbersCheck = document.getElementById('show-numbers');
        if (showNumbersCheck) {
            showNumbersCheck.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        const panelWeightUnitInput = document.getElementById('panel-weight-unit');
        if (panelWeightUnitInput) {
            panelWeightUnitInput.addEventListener('change', () => {
                if (!this.currentLayer) return;
                const oldUnit = this.currentLayer.weight_unit || 'kg';
                const newUnit = panelWeightUnitInput.value || 'kg';
                if (oldUnit !== newUnit) {
                    const weightInput = document.getElementById('panel-weight-kg');
                    const currentValue = parseFloat(weightInput?.value || this.currentLayer.panel_weight || 0) || 0;
                    const converted = (oldUnit === 'kg' && newUnit === 'lb')
                        ? (currentValue * 2.20462)
                        : (oldUnit === 'lb' && newUnit === 'kg')
                            ? (currentValue / 2.20462)
                            : currentValue;
                    if (weightInput) {
                        weightInput.value = converted.toFixed(2);
                    }
                }
                this.updateLayerFromInputs();
            });
        }

        ['half-first-column', 'half-last-column', 'half-first-row', 'half-last-row'].forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this.updateLayerFromInputs();
                    }
                });
            }
        });
        
        // Cabinet ID style radio buttons
        const cabinetIdStyleRadios = document.querySelectorAll('input[name="cabinet-id-style"]');
        cabinetIdStyleRadios.forEach(radio => {
            radio.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.cabinetIdStyle = radio.value;
                });
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        });
        
        // Cabinet ID position radio buttons
        const cabinetIdPositionRadios = document.querySelectorAll('input[name="cabinet-id-position"]');
        cabinetIdPositionRadios.forEach(radio => {
            radio.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.cabinetIdPosition = radio.value;
                });
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        });
        
        // Cabinet ID color with hex sync
        setupColorPickerWithHex('cabinet-id-color', 'cabinet-id-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.cabinetIdColor = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
            }
            window.canvasRenderer.render();
        });
        
        // Border settings (Pixel Map tab)
        const showPanelBordersCheck = document.getElementById('show-panel-borders');
        if (showPanelBordersCheck) {
            showPanelBordersCheck.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        
        const showCircleWithXCheck = document.getElementById('show-circle-with-x');
        if (showCircleWithXCheck) {
            showCircleWithXCheck.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        
        // Border color with hex sync (Pixel Map)
        setupColorPickerWithHex('border-color', 'border-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_pixel = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
            }
            window.canvasRenderer.render();
        });
        
        // Labels color with hex sync
        setupColorPickerWithHex('labels-color', 'labels-color-hex', (val, isFinal) => {
            if (isFinal) {
                this.updateLayerFromInputs();
            } else {
                this.applyToSelectedLayers(layer => {
                    layer.labelsColor = val;
                });
                window.canvasRenderer.render();
            }
        });
        
        // Tab-specific border controls - Cabinet ID
        setupColorPickerWithHex('border-color-cabinet', 'border-color-cabinet-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_cabinet = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
            }
            window.canvasRenderer.render();
        });
        
        // Tab-specific border controls - Data Flow
        setupColorPickerWithHex('border-color-data', 'border-color-data-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_data = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
            }
            window.canvasRenderer.render();
        });
        
        // Tab-specific border controls - Power
        setupColorPickerWithHex('border-color-power', 'border-color-power-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.border_color_power = val;
            });
            if (isFinal) {
                this.updateLayers(this.getSelectedLayers());
            }
            window.canvasRenderer.render();
        });
        
        // Border width is fixed at 2px - no input needed
        
        // Sync border visibility checkboxes across tabs
        ['show-panel-borders', 'show-panel-borders-cabinet', 'show-panel-borders-data', 'show-panel-borders-power'].forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        const checked = checkbox.checked;
                        // Update all border checkboxes
                        ['show-panel-borders', 'show-panel-borders-cabinet', 'show-panel-borders-data', 'show-panel-borders-power'].forEach(otherId => {
                            const other = document.getElementById(otherId);
                            if (other) other.checked = checked;
                        });
                        this.updateLayerFromInputs();
                        window.canvasRenderer.render();
                    }
                });
            }
        });
        
        // Per-layer label checkboxes
        const labelCheckboxes = ['show-label-name', 'show-label-size-px', 'show-label-size-m', 'show-label-size-ft', 'show-label-info', 'show-label-weight', 'use-fractional-inches'];
        labelCheckboxes.forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this.updateLayerFromInputs();
                        window.canvasRenderer.render();
                    }
                });
            }
        });

        const infoLabelSizeInput = document.getElementById('info-label-size');
        const infoLabelSizeValue = document.getElementById('info-label-size-value');
        if (infoLabelSizeInput) {
            const syncValue = () => {
                if (infoLabelSizeValue) infoLabelSizeValue.textContent = `${infoLabelSizeInput.value}`;
            };
            infoLabelSizeInput.addEventListener('input', () => {
                syncValue();
                this.applyToSelectedLayers(layer => {
                    layer.infoLabelSize = parseInt(infoLabelSizeInput.value, 10) || 14;
                });
                window.canvasRenderer.render();
            });
            infoLabelSizeInput.addEventListener('change', () => {
                syncValue();
                this.applyToSelectedLayers(layer => {
                    layer.infoLabelSize = parseInt(infoLabelSizeInput.value, 10) || 14;
                });
                this.updateLayers(this.getSelectedLayers());
                this.saveClientSideProperties();
                window.canvasRenderer.render();
            });
            syncValue();
        }
        
        // Per-layer offset checkboxes
        const offsetCheckboxes = ['show-offset-tl', 'show-offset-tr', 'show-offset-bl', 'show-offset-br'];
        offsetCheckboxes.forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this.updateLayerFromInputs();
                        window.canvasRenderer.render();
                    }
                });
            }
        });
        
        // Screen Name checkboxes on other tabs
        ['show-label-name-cabinet', 'show-label-name-data', 'show-label-name-power'].forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this.applyToSelectedLayers(layer => {
                            layer.showLabelName = checkbox.checked;
                        });
                        // Update all Screen Name checkboxes to match
                        document.getElementById('show-label-name').checked = checkbox.checked;
                        const others = ['show-label-name-cabinet', 'show-label-name-data', 'show-label-name-power'];
                        others.forEach(otherId => {
                            if (otherId !== id && document.getElementById(otherId)) {
                                document.getElementById(otherId).checked = checkbox.checked;
                            }
                        });
                        this.updateLayers(this.getSelectedLayers());
                        window.canvasRenderer.render();
                    }
                });
            }
        });
        
        // Processor Type, Bit Depth and Frame Rate controls for port capacity
        const processorSelect = document.getElementById('processor-type');
        const bitDepthSelect = document.getElementById('bit-depth');
        const frameRateSelect = document.getElementById('frame-rate');
        
        if (processorSelect) {
            processorSelect.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.processorType = processorSelect.value;
                });
                // Update bit depth options based on processor
                this.updateBitDepthOptions();
                this.updateFrameRateOptions();
                this.saveClientSideProperties();
                this.updatePortCapacityDisplay();
                this.updatePortLabelEditor();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        
        if (bitDepthSelect) {
            bitDepthSelect.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.bitDepth = parseInt(bitDepthSelect.value);
                });
                this.updateFrameRateOptions();
                this.saveClientSideProperties();
                this.updatePortCapacityDisplay();
                this.updatePortLabelEditor();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        
        if (frameRateSelect) {
            frameRateSelect.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.frameRate = parseFloat(frameRateSelect.value);
                });
                this.saveClientSideProperties();
                this.updatePortCapacityDisplay();
                this.updatePortLabelEditor();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        
        // Port Mapping mode buttons (Organized vs Max Capacity)
        const mappingOrganizedBtn = document.getElementById('mapping-organized');
        const mappingMaxCapBtn = document.getElementById('mapping-max-capacity');
        
        const setMappingMode = (mode) => {
            this.applyToSelectedLayers(layer => {
                layer.portMappingMode = mode;
            });
            
            // Update button styles
            if (mappingOrganizedBtn && mappingMaxCapBtn) {
                if (mode === 'organized') {
                    mappingOrganizedBtn.style.background = '#4A90E2';
                    mappingOrganizedBtn.style.color = '#fff';
                    mappingMaxCapBtn.style.background = '#333';
                    mappingMaxCapBtn.style.color = '#ccc';
                } else {
                    mappingMaxCapBtn.style.background = '#4A90E2';
                    mappingMaxCapBtn.style.color = '#fff';
                    mappingOrganizedBtn.style.background = '#333';
                    mappingOrganizedBtn.style.color = '#ccc';
                }
            }
            
            this.saveClientSideProperties();
            this.updatePortCapacityDisplay();
            this.updatePortLabelEditor();
            this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        };
        
        if (mappingOrganizedBtn) {
            mappingOrganizedBtn.addEventListener('click', () => setMappingMode('organized'));
        }
        if (mappingMaxCapBtn) {
            mappingMaxCapBtn.addEventListener('click', () => setMappingMode('max-capacity'));
        }
        
        // Flow Pattern buttons
        document.querySelectorAll('.flow-pattern-btn:not(.power-flow-pattern-btn)').forEach(btn => {
            btn.addEventListener('click', () => {
                const pattern = btn.getAttribute('data-pattern');
                if (this.currentLayer && this.isCustomFlow(this.currentLayer) && this.customSelection.size > 0) {
                    this.applyPatternToSelection(pattern);
                    return;
                }
                
                // Remove active class from all buttons
                document.querySelectorAll('.flow-pattern-btn').forEach(b => b.classList.remove('active'));
                // Add active to clicked button
                btn.classList.add('active');
                
                if (this.currentLayer) {
                    this.applyToSelectedLayers(layer => {
                        layer.flowPattern = pattern;
                    });
                    this.saveClientSideProperties();
                    this.updatePortCapacityDisplay();  // Update port calculation with new pattern
                    this.updatePortLabelEditor();
                    this.updateLayers(this.getSelectedLayers());
                    window.canvasRenderer.render();
                }
            });
        });

        // Power Flow Pattern buttons
        document.querySelectorAll('.power-flow-pattern-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const pattern = btn.getAttribute('data-pattern');
                if (this.currentLayer && this.isCustomPower(this.currentLayer) && this.powerCustomSelection.size > 0) {
                    this.applyPowerPatternToSelection(pattern);
                    return;
                }
                document.querySelectorAll('.power-flow-pattern-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                if (this.currentLayer) {
                    this.applyToSelectedLayers(layer => {
                        layer.powerFlowPattern = pattern;
                    });
                    this.saveClientSideProperties();
                    this.updatePowerCapacityDisplay();
                    this.updateCustomPowerUI();
                    this.updateLayers(this.getSelectedLayers());
                    window.canvasRenderer.render();
                }
            });
        });
        
        // Data Flow controls
        const arrowLineWidthInput = document.getElementById('arrow-line-width');
        if (arrowLineWidthInput) {
            arrowLineWidthInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.arrowLineWidth = parseInt(arrowLineWidthInput.value) || 6;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        const portTemplatePrimaryInput = document.getElementById('port-label-template-primary');
        const portTemplateReturnInput = document.getElementById('port-label-template-return');
        const portBulkPrimaryInput = document.getElementById('port-label-bulk-primary');
        const portBulkReturnInput = document.getElementById('port-label-bulk-return');
        const portApplySelectedBtn = document.getElementById('port-label-apply-selected');
        const portClearSelectedBtn = document.getElementById('port-label-clear-selected');
        const portSelectAllBtn = document.getElementById('port-label-select-all');
        const portDeselectAllBtn = document.getElementById('port-label-deselect-all');
        const customModeToggle = document.getElementById('custom-flow-toggle');
        const customPrevPortBtn = document.getElementById('custom-prev-port');
        const customNextPortBtn = document.getElementById('custom-next-port');
        const customClearPortBtn = document.getElementById('custom-clear-port');
        const customClearAllBtn = document.getElementById('custom-clear-all');
        const customClearSelectionBtn = document.getElementById('custom-clear-selection');
        const customActivePortInput = document.getElementById('custom-active-port-input');

        if (portTemplatePrimaryInput) {
            portTemplatePrimaryInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.portLabelTemplatePrimary = portTemplatePrimaryInput.value || 'P#';
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        if (portTemplateReturnInput) {
            portTemplateReturnInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.portLabelTemplateReturn = portTemplateReturnInput.value || 'R#';
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        const getSelectedPortNumbers = () => {
            const list = document.getElementById('port-label-list');
            if (!list) return [];
            const selected = [];
            list.querySelectorAll('input[type=\"checkbox\"][data-port]').forEach(cb => {
                if (cb.checked) selected.push(parseInt(cb.getAttribute('data-port'), 10));
            });
            return selected;
        };

        const setAllPortCheckboxes = (checked) => {
            const list = document.getElementById('port-label-list');
            if (!list) return;
            list.querySelectorAll('input[type=\"checkbox\"][data-port]').forEach(cb => {
                cb.checked = checked;
            });
        };

        if (portApplySelectedBtn) {
            portApplySelectedBtn.addEventListener('click', () => {
                const targetLayers = this.getSelectedLayers();
                if (targetLayers.length === 0) return;
                const selectedPorts = getSelectedPortNumbers();
                if (selectedPorts.length === 0) return;
                const orderedPorts = [...selectedPorts].sort((a, b) => a - b);

                const bulkPrimary = portBulkPrimaryInput ? portBulkPrimaryInput.value.trim() : '';
                const bulkReturn = portBulkReturnInput ? portBulkReturnInput.value.trim() : '';

                targetLayers.forEach(layer => {
                    if (!layer.portLabelOverridesPrimary) layer.portLabelOverridesPrimary = {};
                    if (!layer.portLabelOverridesReturn) layer.portLabelOverridesReturn = {};
                    orderedPorts.forEach((portNum, index) => {
                        const groupIndex = index + 1;
                        if (bulkPrimary) {
                            layer.portLabelOverridesPrimary[portNum] = bulkPrimary.replace('#', groupIndex);
                        }
                        if (bulkReturn) {
                            layer.portLabelOverridesReturn[portNum] = bulkReturn.replace('#', groupIndex);
                        }
                    });
                });

                this.saveClientSideProperties();
                this.updatePortLabelEditor();
                this.updateLayers(targetLayers);
                window.canvasRenderer.render();
            });
        }

        if (portClearSelectedBtn) {
            portClearSelectedBtn.addEventListener('click', () => {
                const targetLayers = this.getSelectedLayers();
                if (targetLayers.length === 0) return;
                const selectedPorts = getSelectedPortNumbers();
                if (selectedPorts.length === 0) return;

                targetLayers.forEach(layer => {
                    selectedPorts.forEach(portNum => {
                        if (layer.portLabelOverridesPrimary) {
                            delete layer.portLabelOverridesPrimary[portNum];
                        }
                        if (layer.portLabelOverridesReturn) {
                            delete layer.portLabelOverridesReturn[portNum];
                        }
                    });
                });

                this.saveClientSideProperties();
                this.updatePortLabelEditor();
                this.updateLayers(targetLayers);
                window.canvasRenderer.render();
            });
        }

        if (portSelectAllBtn) {
            portSelectAllBtn.addEventListener('click', () => {
                setAllPortCheckboxes(true);
            });
        }

        if (portDeselectAllBtn) {
            portDeselectAllBtn.addEventListener('click', () => {
                setAllPortCheckboxes(false);
            });
        }

        if (customModeToggle) {
            customModeToggle.addEventListener('change', () => {
                if (!this.currentLayer) return;
                this.toggleCustomFlowMode(customModeToggle.checked);
            });
        }
        if (customPrevPortBtn) {
            customPrevPortBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                this.currentLayer.customPortIndex = Math.max(1, (this.currentLayer.customPortIndex || 1) - 1);
                this.saveState('Custom Port Change');
                this.saveClientSideProperties();
                this.updateCustomFlowUI();
                this.updatePortLabelEditor();
                window.canvasRenderer.render();
            });
        }
        if (customNextPortBtn) {
            customNextPortBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                this.currentLayer.customPortIndex = (this.currentLayer.customPortIndex || 1) + 1;
                this.saveState('Custom Port Change');
                this.saveClientSideProperties();
                this.updateCustomFlowUI();
                this.updatePortLabelEditor();
                window.canvasRenderer.render();
            });
        }
        if (customClearPortBtn) {
            customClearPortBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                const portNum = this.currentLayer.customPortIndex || 1;
                this.currentLayer.customPortPaths[portNum] = [];
                this.saveState('Custom Clear Port');
                this.saveClientSideProperties();
                this.updateCustomFlowUI();
                this.updatePortLabelEditor();
                window.canvasRenderer.render();
            });
        }
        if (customClearAllBtn) {
            customClearAllBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                this.currentLayer.customPortPaths = {};
                this.currentLayer.customPortIndex = 1;
                this.customSelection.clear();
                this.saveState('Custom Clear All');
                this.saveClientSideProperties();
                this.updateCustomFlowUI();
                this.updatePortLabelEditor();
                window.canvasRenderer.render();
            });
        }
        if (customClearSelectionBtn) {
            customClearSelectionBtn.addEventListener('click', () => {
                this.customSelection.clear();
                this.updateCustomFlowUI();
                window.canvasRenderer.render();
            });
        }
        if (customActivePortInput) {
            customActivePortInput.addEventListener('change', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                const nextVal = parseInt(customActivePortInput.value, 10);
                if (Number.isFinite(nextVal) && nextVal >= 1) {
                    this.currentLayer.customPortIndex = nextVal;
                    this.saveState('Custom Port Change');
                    this.saveClientSideProperties();
                    this.updateCustomFlowUI();
                    this.updatePortLabelEditor();
                    window.canvasRenderer.render();
                }
            });
        }
        
        const arrowSizeInput = document.getElementById('arrow-size');
        if (arrowSizeInput) {
            arrowSizeInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.arrowSize = parseInt(arrowSizeInput.value) || 12;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        
        const randomColorsCheck = document.getElementById('random-colors');
        if (randomColorsCheck) {
            randomColorsCheck.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.randomDataColors = randomColorsCheck.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        // Power settings
        const powerVoltageSelect = document.getElementById('power-voltage-select');
        const powerVoltageCustomInput = document.getElementById('power-voltage-custom');
        const powerAmperageSelect = document.getElementById('power-amperage-select');
        const powerAmperageCustomInput = document.getElementById('power-amperage-custom');
        const powerPanelWattsInput = document.getElementById('power-panel-watts');
        const powerLineWidthInput = document.getElementById('power-line-width');
        const powerLabelSizeInput = document.getElementById('power-label-size');
        const powerMaximizeCheckbox = document.getElementById('power-maximize');
        const powerOrganizedCheckbox = document.getElementById('power-organized');
        const powerCustomToggle = document.getElementById('power-custom-toggle');
        const powerCustomPrev = document.getElementById('power-custom-prev');
        const powerCustomNext = document.getElementById('power-custom-next');
        const powerCustomClearCircuit = document.getElementById('power-custom-clear-circuit');
        const powerCustomClearAll = document.getElementById('power-custom-clear-all');
        const powerCustomClearSelection = document.getElementById('power-custom-clear-selection');
        const powerCustomActive = document.getElementById('power-custom-active');
        const powerRandomColorsCheckbox = document.getElementById('power-random-colors');
        const powerColorCodedViewCheckbox = document.getElementById('power-color-coded-view');
        const powerCircuitColorSection = document.getElementById('power-circuit-color-section');
        const powerCircuitColorList = document.getElementById('power-circuit-color-list');
        const powerCircuitColorPreset = document.getElementById('power-circuit-color-preset');
        const powerCircuitColorCustom = document.getElementById('power-circuit-color-custom');
        const powerCircuitColorCustomHex = document.getElementById('power-circuit-color-custom-hex');
        const powerCircuitColorApply = document.getElementById('power-circuit-color-apply');
        const powerCircuitColorSelectAll = document.getElementById('power-circuit-color-select-all');
        const powerCircuitColorDeselectAll = document.getElementById('power-circuit-color-deselect-all');
        const powerLabelTemplateInput = document.getElementById('power-label-template');
        const powerLabelBulkInput = document.getElementById('power-label-bulk');
        const powerLabelApplyBtn = document.getElementById('power-label-apply-selected');
        const powerLabelClearBtn = document.getElementById('power-label-clear-selected');
        const powerLabelSelectAllBtn = document.getElementById('power-label-select-all');
        const powerLabelDeselectAllBtn = document.getElementById('power-label-deselect-all');
        const showDataFlowPortInfoEl = document.getElementById('show-data-flow-port-info');
        const showPowerCircuitInfoEl = document.getElementById('show-power-circuit-info');

        const updatePowerVoltageUI = () => {
            if (!powerVoltageSelect || !powerVoltageCustomInput) return;
            if (powerVoltageSelect.value === 'custom') {
                powerVoltageCustomInput.style.display = 'inline-block';
            } else {
                powerVoltageCustomInput.style.display = 'none';
            }
        };

        const updatePowerAmperageUI = () => {
            if (!powerAmperageSelect || !powerAmperageCustomInput) return;
            if (powerAmperageSelect.value === 'custom') {
                powerAmperageCustomInput.style.display = 'inline-block';
            } else {
                powerAmperageCustomInput.style.display = 'none';
            }
        };

        const getSelectedPowerCircuitLetters = () => {
            if (!powerCircuitColorList) return [];
            const selected = [];
            powerCircuitColorList.querySelectorAll('input[type="checkbox"][data-circuit-letter]').forEach(cb => {
                if (cb.checked) selected.push(cb.getAttribute('data-circuit-letter'));
            });
            return selected;
        };

        const setPowerCircuitLetterSelection = (checked) => {
            if (!powerCircuitColorList) return;
            powerCircuitColorList.querySelectorAll('input[type="checkbox"][data-circuit-letter]').forEach(cb => {
                cb.checked = checked;
            });
        };

        const renderPowerCircuitColorRows = () => {
            if (!powerCircuitColorList || !this.currentLayer) return;
            const colors = this.normalizePowerCircuitColors(this.currentLayer.powerCircuitColors);
            powerCircuitColorList.innerHTML = '';
            Object.keys(colors).forEach((letter, index) => {
                const row = document.createElement('div');
                row.style.display = 'grid';
                row.style.gridTemplateColumns = '20px 26px 1fr';
                row.style.gap = '6px';
                row.style.alignItems = 'center';

                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.setAttribute('data-circuit-letter', letter);

                const swatch = document.createElement('div');
                swatch.style.width = '20px';
                swatch.style.height = '20px';
                swatch.style.borderRadius = '4px';
                swatch.style.border = '1px solid #333';
                swatch.style.background = colors[letter];

                const text = document.createElement('div');
                text.style.fontSize = '12px';
                text.style.color = '#ccc';
                text.textContent = `Circuit ${index + 1}`;

                row.appendChild(cb);
                row.appendChild(swatch);
                row.appendChild(text);
                powerCircuitColorList.appendChild(row);
            });
        };

        const updatePowerCircuitColorSection = () => {
            if (powerCircuitColorSection) {
                powerCircuitColorSection.style.display = (this.currentLayer && this.currentLayer.powerColorCodedView) ? 'block' : 'none';
            }
            renderPowerCircuitColorRows();
        };

        if (powerVoltageSelect && powerVoltageCustomInput) {
            powerVoltageSelect.addEventListener('change', () => {
                updatePowerVoltageUI();
                const val = powerVoltageSelect.value === 'custom'
                    ? parseFloat(powerVoltageCustomInput.value) || 0
                    : parseFloat(powerVoltageSelect.value) || 0;
                this.applyToSelectedLayers(layer => {
                    layer.powerVoltage = val;
                    if (powerVoltageSelect.value === 'custom') {
                        layer.powerVoltageCustom = val;
                    }
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
            powerVoltageCustomInput.addEventListener('change', () => {
                const val = parseFloat(powerVoltageCustomInput.value) || 0;
                this.applyToSelectedLayers(layer => {
                    layer.powerVoltage = val;
                    layer.powerVoltageCustom = val;
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        if (powerAmperageSelect && powerAmperageCustomInput) {
            powerAmperageSelect.addEventListener('change', () => {
                updatePowerAmperageUI();
                const val = powerAmperageSelect.value === 'custom'
                    ? parseFloat(powerAmperageCustomInput.value) || 0
                    : parseFloat(powerAmperageSelect.value) || 0;
                this.applyToSelectedLayers(layer => {
                    layer.powerAmperage = val;
                    if (powerAmperageSelect.value === 'custom') {
                        layer.powerAmperageCustom = val;
                    }
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
            powerAmperageCustomInput.addEventListener('change', () => {
                const val = parseFloat(powerAmperageCustomInput.value) || 0;
                this.applyToSelectedLayers(layer => {
                    layer.powerAmperage = val;
                    layer.powerAmperageCustom = val;
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        if (powerPanelWattsInput) {
            powerPanelWattsInput.addEventListener('change', () => {
                const val = parseFloat(powerPanelWattsInput.value) || 0;
                this.applyToSelectedLayers(layer => {
                    layer.panelWatts = val;
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        if (powerLineWidthInput) {
            powerLineWidthInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerLineWidth = parseInt(powerLineWidthInput.value, 10) || 8;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        if (powerLabelSizeInput) {
            powerLabelSizeInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerLabelSize = parseInt(powerLabelSizeInput.value, 10) || 14;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        if (powerMaximizeCheckbox) {
            powerMaximizeCheckbox.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerMaximize = powerMaximizeCheckbox.checked;
                    if (powerMaximizeCheckbox.checked) {
                        layer.powerOrganized = false;
                    }
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                if (powerOrganizedCheckbox && powerMaximizeCheckbox.checked) {
                    powerOrganizedCheckbox.checked = false;
                }
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        if (powerOrganizedCheckbox) {
            powerOrganizedCheckbox.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerOrganized = powerOrganizedCheckbox.checked;
                    if (powerOrganizedCheckbox.checked) {
                        layer.powerMaximize = false;
                    }
                });
                this.saveClientSideProperties();
                this.updatePowerCapacityDisplay();
                if (powerMaximizeCheckbox && powerOrganizedCheckbox.checked) {
                    powerMaximizeCheckbox.checked = false;
                }
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        if (powerRandomColorsCheckbox) {
            powerRandomColorsCheckbox.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerRandomColors = powerRandomColorsCheckbox.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        if (powerColorCodedViewCheckbox) {
            powerColorCodedViewCheckbox.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerColorCodedView = powerColorCodedViewCheckbox.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                updatePowerCircuitColorSection();
                window.canvasRenderer.render();
            });
        }
        if (powerCircuitColorSelectAll) {
            powerCircuitColorSelectAll.addEventListener('click', () => setPowerCircuitLetterSelection(true));
        }
        if (powerCircuitColorDeselectAll) {
            powerCircuitColorDeselectAll.addEventListener('click', () => setPowerCircuitLetterSelection(false));
        }
        if (powerCircuitColorApply) {
            powerCircuitColorApply.addEventListener('click', () => {
                const selectedLetters = getSelectedPowerCircuitLetters();
                if (!selectedLetters.length) return;
                let colorToApply = (powerCircuitColorPreset && powerCircuitColorPreset.value !== 'custom')
                    ? powerCircuitColorPreset.value
                    : (powerCircuitColorCustomHex ? powerCircuitColorCustomHex.value : '#FF0000');
                colorToApply = this.normalizeHexColor(colorToApply, '#FF0000');
                this.applyToSelectedLayers(layer => {
                    const colors = this.normalizePowerCircuitColors(layer.powerCircuitColors);
                    selectedLetters.forEach(letter => {
                        colors[letter] = colorToApply;
                    });
                    layer.powerCircuitColors = colors;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                updatePowerCircuitColorSection();
                window.canvasRenderer.render();
            });
        }
        if (powerCircuitColorPreset && powerCircuitColorCustomHex) {
            powerCircuitColorPreset.addEventListener('change', () => {
                if (powerCircuitColorPreset.value !== 'custom' && powerCircuitColorCustomHex) {
                    powerCircuitColorCustomHex.value = this.normalizeHexColor(powerCircuitColorPreset.value, '#FF0000');
                    if (powerCircuitColorCustom) powerCircuitColorCustom.value = powerCircuitColorCustomHex.value;
                }
            });
        }
        setupColorPickerWithHex('power-circuit-color-custom', 'power-circuit-color-custom-hex', () => {});
        if (showDataFlowPortInfoEl) {
            showDataFlowPortInfoEl.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.showDataFlowPortInfo = showDataFlowPortInfoEl.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        if (showPowerCircuitInfoEl) {
            showPowerCircuitInfoEl.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.showPowerCircuitInfo = showPowerCircuitInfoEl.checked;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        const getSelectedPowerCircuits = () => {
            const list = document.getElementById('power-label-list');
            if (!list) return [];
            const selected = [];
            list.querySelectorAll('input[type="checkbox"][data-circuit]').forEach(cb => {
                if (cb.checked) selected.push(parseInt(cb.getAttribute('data-circuit'), 10));
            });
            return selected;
        };

        const setAllPowerCheckboxes = (checked) => {
            const list = document.getElementById('power-label-list');
            if (!list) return;
            list.querySelectorAll('input[type="checkbox"][data-circuit]').forEach(cb => {
                cb.checked = checked;
            });
        };

        if (powerLabelTemplateInput) {
            powerLabelTemplateInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.powerLabelTemplate = powerLabelTemplateInput.value || 'S1-#';
                });
                this.saveClientSideProperties();
                this.updatePowerLabelEditor();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        if (powerLabelApplyBtn) {
            powerLabelApplyBtn.addEventListener('click', () => {
                const targetLayers = this.getSelectedLayers();
                if (targetLayers.length === 0) return;
                const selectedCircuits = getSelectedPowerCircuits();
                if (selectedCircuits.length === 0) return;
                const ordered = [...selectedCircuits].sort((a, b) => a - b);
                const bulk = powerLabelBulkInput ? powerLabelBulkInput.value.trim() : '';
                if (!bulk) return;
                targetLayers.forEach(layer => {
                    if (!layer.powerLabelOverrides) layer.powerLabelOverrides = {};
                    ordered.forEach((circuitNum, index) => {
                        const groupIndex = index + 1;
                        layer.powerLabelOverrides[circuitNum] = bulk.replace('#', groupIndex);
                    });
                });
                this.saveClientSideProperties();
                this.updatePowerLabelEditor();
                this.updateLayers(targetLayers);
                window.canvasRenderer.render();
            });
        }

        if (powerLabelClearBtn) {
            powerLabelClearBtn.addEventListener('click', () => {
                const targetLayers = this.getSelectedLayers();
                if (targetLayers.length === 0) return;
                const selectedCircuits = getSelectedPowerCircuits();
                if (selectedCircuits.length === 0) return;
                targetLayers.forEach(layer => {
                    selectedCircuits.forEach(circuitNum => {
                        if (layer.powerLabelOverrides) {
                            delete layer.powerLabelOverrides[circuitNum];
                        }
                    });
                });
                this.saveClientSideProperties();
                this.updatePowerLabelEditor();
                this.updateLayers(targetLayers);
                window.canvasRenderer.render();
            });
        }

        if (powerLabelSelectAllBtn) {
            powerLabelSelectAllBtn.addEventListener('click', () => setAllPowerCheckboxes(true));
        }
        if (powerLabelDeselectAllBtn) {
            powerLabelDeselectAllBtn.addEventListener('click', () => setAllPowerCheckboxes(false));
        }

        if (powerCustomToggle) {
            powerCustomToggle.addEventListener('change', () => {
                if (!this.currentLayer) return;
                this.toggleCustomPowerMode(powerCustomToggle.checked);
            });
        }
        if (powerCustomPrev) {
            powerCustomPrev.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                this.currentLayer.powerCustomIndex = Math.max(1, (this.currentLayer.powerCustomIndex || 1) - 1);
                this.saveState('Power Custom Circuit Change');
                this.saveClientSideProperties();
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomNext) {
            powerCustomNext.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                this.currentLayer.powerCustomIndex = (this.currentLayer.powerCustomIndex || 1) + 1;
                this.saveState('Power Custom Circuit Change');
                this.saveClientSideProperties();
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomClearCircuit) {
            powerCustomClearCircuit.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                const circuitNum = this.currentLayer.powerCustomIndex || 1;
                this.currentLayer.powerCustomPaths[circuitNum] = [];
                this.saveState('Power Custom Clear Circuit');
                this.saveClientSideProperties();
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomClearAll) {
            powerCustomClearAll.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                this.currentLayer.powerCustomPaths = {};
                this.currentLayer.powerCustomIndex = 1;
                this.powerCustomSelection.clear();
                this.saveState('Power Custom Clear All');
                this.saveClientSideProperties();
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomClearSelection) {
            powerCustomClearSelection.addEventListener('click', () => {
                this.powerCustomSelection.clear();
                this.updateCustomPowerUI();
                window.canvasRenderer.render();
            });
        }
        if (powerCustomActive) {
            powerCustomActive.addEventListener('change', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                const nextVal = parseInt(powerCustomActive.value, 10);
                if (Number.isFinite(nextVal) && nextVal >= 1) {
                    this.currentLayer.powerCustomIndex = nextVal;
                    this.saveState('Power Custom Circuit Change');
                    this.saveClientSideProperties();
                    this.updateCustomPowerUI();
                    window.canvasRenderer.render();
                }
            });
        }
        // power custom debug removed
        
        // Data Flow Color
        setupColorPickerWithHex('data-flow-color', 'data-flow-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.dataFlowColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });
        
        // Arrow Color
        setupColorPickerWithHex('arrow-color', 'arrow-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.arrowColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });
        
        // Primary Color
        setupColorPickerWithHex('primary-color', 'primary-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.primaryColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });

        // Primary Label Text Color
        setupColorPickerWithHex('primary-text-color', 'primary-text-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.primaryTextColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });
        
        // Backup/Redundant Color
        setupColorPickerWithHex('backup-color', 'backup-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.backupColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });

        // Backup/Redundant Label Text Color
        setupColorPickerWithHex('backup-text-color', 'backup-text-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.backupTextColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-line-color', 'power-line-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerLineColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-arrow-color', 'power-arrow-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerArrowColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-label-bg-color', 'power-label-bg-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerLabelBgColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });

        setupColorPickerWithHex('power-label-text-color', 'power-label-text-color-hex', (val, isFinal) => {
            this.applyToSelectedLayers(layer => {
                layer.powerLabelTextColor = val;
            });
            this.saveClientSideProperties();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
            window.canvasRenderer.render();
        });
        
        const labelSizeInput = document.getElementById('label-size');
        if (labelSizeInput) {
            labelSizeInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.dataFlowLabelSize = parseInt(labelSizeInput.value) || 12;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        
        // Screen Name Size - Data Flow tab (uses screen-name-size id)
        const screenNameSizeInput = document.getElementById('screen-name-size');
        if (screenNameSizeInput) {
            screenNameSizeInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.screenNameSizeDataFlow = parseInt(screenNameSizeInput.value) || 30;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        
        // Screen Name Size - Cabinet ID tab
        const screenNameSizeCabinetInput = document.getElementById('screen-name-size-cabinet');
        if (screenNameSizeCabinetInput) {
            screenNameSizeCabinetInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.screenNameSizeCabinet = parseInt(screenNameSizeCabinetInput.value) || 30;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        
        // Screen Name Size - Power tab
        const screenNameSizePowerInput = document.getElementById('screen-name-size-power');
        if (screenNameSizePowerInput) {
            screenNameSizePowerInput.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.screenNameSizePower = parseInt(screenNameSizePowerInput.value) || 30;
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }
        
        // Labels color and font size
        const labelsColorInput = document.getElementById('labels-color');
        if (labelsColorInput) {
            labelsColorInput.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        
        const labelsFontSizeInput = document.getElementById('labels-fontsize');
        if (labelsFontSizeInput) {
            labelsFontSizeInput.addEventListener('change', () => {
                if (this.currentLayer) {
                    this.updateLayerFromInputs();
                }
            });
        }
        
        // Color pickers with hex input sync
        setupColorPickerWithHex('color1-picker', 'color1-hex', (val, isFinal) => {
            const rgb = this.hexToRgb(val);
            this.applyToSelectedLayers(layer => {
                layer.color1 = rgb;
            });
            window.canvasRenderer.render();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
        });
        setupColorPickerWithHex('color2-picker', 'color2-hex', (val, isFinal) => {
            const rgb = this.hexToRgb(val);
            this.applyToSelectedLayers(layer => {
                layer.color2 = rgb;
            });
            window.canvasRenderer.render();
            if (isFinal) this.updateLayers(this.getSelectedLayers());
        });
        
        const rasterWidthInput = document.getElementById('toolbar-raster-width');
        const rasterHeightInput = document.getElementById('toolbar-raster-height');
        
        if (rasterWidthInput) {
            rasterWidthInput.addEventListener('change', () => {
                const width = evaluateMathExpression(rasterWidthInput.value) || 1920;
                window.canvasRenderer.rasterWidth = width;
                rasterWidthInput.value = width; // Update input with evaluated result
                if (this.project) {
                    this.project.raster_width = width;
                    this.saveProject();
                }
                this.saveRasterSize();
                if (typeof sendClientLog === 'function') {
                    sendClientLog('raster_change', { width, height: window.canvasRenderer.rasterHeight, source: 'toolbar-width' });
                }
                window.canvasRenderer.render();
            });
        }
        
        if (rasterHeightInput) {
            rasterHeightInput.addEventListener('change', () => {
                const height = evaluateMathExpression(rasterHeightInput.value) || 1080;
                window.canvasRenderer.rasterHeight = height;
                rasterHeightInput.value = height; // Update input with evaluated result
                if (this.project) {
                    this.project.raster_height = height;
                    this.saveProject();
                }
                this.saveRasterSize();
                if (typeof sendClientLog === 'function') {
                    sendClientLog('raster_change', { width: window.canvasRenderer.rasterWidth, height, source: 'toolbar-height' });
                }
                window.canvasRenderer.render();
            });
        }
        
        // Note: loadRasterSize() is called in init() before setupEventListeners
        
        document.getElementById('btn-new').addEventListener('click', () => {
            if (confirm('Create a new project? Unsaved changes will be lost.')) {
                this.createNewProject();
            }
        });
        
        document.getElementById('btn-open').addEventListener('click', () => {
            this.loadProjectFromFile();
        });
        
        document.getElementById('btn-save').addEventListener('click', () => {
            this.saveProjectToFile();
        });
        
        document.getElementById('btn-export').addEventListener('click', () => {
            // Show export modal
            document.getElementById('export-modal').style.display = 'block';
            // Set project name from current project
            document.getElementById('export-name').value = this.project.name || 'Untitled Project';
            this.loadExportSuffixesToUI();
            // Update preview
            this.updateExportPreview();
        });
        
        // Update preview when options change
        ['export-name', 'export-format', 'export-pixel-map', 'export-cabinet-id', 'export-data-flow', 'export-power',
         'export-suffix-pixel-map', 'export-suffix-cabinet-id', 'export-suffix-data-flow', 'export-suffix-power'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', () => {
                    this.saveExportSuffixesFromUI();
                    this.updateExportPreview();
                });
                el.addEventListener('input', () => {
                    this.saveExportSuffixesFromUI();
                    this.updateExportPreview();
                });
            }
        });
        
        document.getElementById('export-cancel').addEventListener('click', () => {
            document.getElementById('export-modal').style.display = 'none';
        });
        
        document.getElementById('export-confirm').addEventListener('click', async () => {
            const projectName = document.getElementById('export-name').value.trim() || 'Project';
            const format = document.getElementById('export-format').value;
            sendClientLog('export_capabilities', {
                hasSaveFilePicker: this.supportsFilePickerAPIs(),
                hasDirectoryPicker: this.supportsDirectoryPickerAPIs(),
                format
            });
            
            // Get selected views
            const views = [];
            if (document.getElementById('export-pixel-map').checked) views.push('pixel-map');
            if (document.getElementById('export-cabinet-id').checked) views.push('cabinet-id');
            if (document.getElementById('export-data-flow').checked) views.push('data-flow');
            if (document.getElementById('export-power').checked) views.push('power');
            
            if (views.length === 0) {
                alert('Please select at least one view to export.');
                return;
            }

            if (!this.supportsFilePickerAPIs() && !this.supportsDirectoryPickerAPIs() && !this._warnedNoFilePickerExport) {
                this._warnedNoFilePickerExport = true;
                sendClientLog('export_picker_apis_unavailable_warning', {});
            }
            
            document.getElementById('export-modal').style.display = 'none';
            document.getElementById('status-message').textContent = 'Exporting...';
            
            try {
                await this.performExport(projectName, format, views);
                
                document.getElementById('status-message').textContent = 'Export complete!';
                setTimeout(() => {
                    document.getElementById('status-message').textContent = 'Ready';
                }, 3000);
            } catch (error) {
                console.error('Export error:', error);
                document.getElementById('status-message').textContent = 'Export failed!';
                sendClientLog('export_failed', { message: error.message });
            }
        });
        
        // Close export modal only when press+release both happen on backdrop
        const exportModal = document.getElementById('export-modal');
        const exportModalContent = exportModal ? exportModal.querySelector('.modal-content') : null;
        let exportBackdropDown = false;
        if (exportModal) {
            exportModal.addEventListener('mousedown', (e) => {
                exportBackdropDown = e.target === exportModal;
            });
            exportModal.addEventListener('click', (e) => {
                if (e.target === exportModal && exportBackdropDown) {
                    exportModal.style.display = 'none';
                }
                exportBackdropDown = false;
            });
        }
        if (exportModalContent) {
            exportModalContent.addEventListener('mousedown', () => {
                exportBackdropDown = false;
            });
            exportModalContent.addEventListener('click', (e) => e.stopPropagation());
        }

        this.setupMenuBar();
        this.setupPreferences();
    }
    
    addLayer() {
        const prefs = this.getPreferences();
        const columns = prefs.columns;
        const rows = prefs.rows;
        const cabinetWidth = prefs.panelWidth;
        const cabinetHeight = prefs.panelHeight;
        const offsetX = 0;
        const offsetY = 0;
        const color1 = this.hexToRgb(prefs.color1);
        const color2 = this.hexToRgb(prefs.color2);
        
        this.saveState('Add Layer');
        
        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: 'Screen1',  // Always "Screen1" for new screens (duplicate increments)
                columns,
                rows,
                cabinet_width: cabinetWidth,
                cabinet_height: cabinetHeight,
                offset_x: offsetX,
                offset_y: offsetY,
                color1,
                color2,
                border_color: prefs.borderColor,
                panel_weight: prefs.panelWeight,
                weight_unit: prefs.weightUnit
            })
        })
        .then(res => res.json())
        .then(layer => {
            sendClientLog('add_layer', {
                id: layer.id, name: layer.name,
                columns: layer.columns, rows: layer.rows,
                cabinet_width: layer.cabinet_width, cabinet_height: layer.cabinet_height,
                offset_x: layer.offset_x, offset_y: layer.offset_y,
                totalLayers: this.project.layers ? this.project.layers.length + 1 : 1
            });
            // Initialize client-side defaults for new layer
            this.initializeLayerDefaults(layer);
            
            this.upsertProjectLayer(layer);
            this.selectLayer(layer);
            window.canvasRenderer.fitToView();
            
            // Save the new defaults to localStorage
            this.saveClientSideProperties();
        });
    }

    addImageLayer(imageData, imageWidth, imageHeight) {
        const name = this.getNextImageLayerName();
        this.saveState('Add Image Layer');
        fetch('/api/layer/add-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                imageData,
                imageWidth,
                imageHeight,
                offset_x: 0,
                offset_y: 0,
                imageScale: 1.0
            })
        })
        .then(res => res.json())
        .then(layer => {
            sendClientLog('add_image_layer', { id: layer.id, name: layer.name });
            this.initializeLayerDefaults(layer);
            if (layer.imageData) {
                const img = new Image();
                img.onload = () => {
                    if (layer._imageObj !== img) return;
                    window.canvasRenderer.render();
                };
                img.src = layer.imageData;
                layer._imageObj = img;
            }
            this.upsertProjectLayer(layer);
            this.selectLayer(layer);
            window.canvasRenderer.fitToView();
            window.canvasRenderer.render();
            this.saveClientSideProperties();
        });
    }

    getNextImageLayerName() {
        const base = 'Image';
        const existing = this.project.layers
            .filter(l => (l.type || 'screen') === 'image')
            .map(l => l.name || '')
            .filter(name => name.startsWith(base));
        let maxNum = 0;
        existing.forEach(name => {
            const m = name.match(/^Image\\s*(\\d+)$/i);
            if (m) maxNum = Math.max(maxNum, parseInt(m[1], 10));
        });
        return `Image ${maxNum + 1}`;
    }

    handleImageFileSelection(e) {
        const input = e.target;
        const file = input.files && input.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            const dataUrl = reader.result;
            const img = new Image();
            img.onload = () => {
                if (this.imageFileAction === 'replace' && this.currentLayer && this.currentLayer.type === 'image') {
                    this.currentLayer.imageData = dataUrl;
                    this.currentLayer.imageWidth = img.width;
                    this.currentLayer.imageHeight = img.height;
                    this.updateLayer(true, 'Replace Image');
                    window.canvasRenderer.render();
                } else {
                    this.addImageLayer(dataUrl, img.width, img.height);
                }
            };
            img.src = dataUrl;
        };
        reader.readAsDataURL(file);
        // reset input for next time
        input.value = '';
    }
    
    // Initialize default values for a layer
    initializeLayerDefaults(layer) {
        const prefs = this.getPreferences();
        if ((layer.type || 'screen') === 'image') {
            layer.imageScale = layer.imageScale || 1.0;
            return;
        }
        layer.arrowLineWidth = prefs.dataLineWidth;  // Default line width for data flow
        layer.arrowColor = '#0042AA';
        layer.dataFlowColor = '#FFFFFF';
        layer.dataFlowLabelSize = prefs.dataLabelSize;
        layer.primaryColor = '#00FF00';
        layer.primaryTextColor = '#000000';
        layer.backupColor = '#FF0000';
        layer.backupTextColor = '#FFFFFF';
        layer.flowPattern = prefs.flowPattern;
        layer.bitDepth = prefs.bitDepth;
        layer.frameRate = prefs.frameRate;
        layer.processorType = prefs.processorType;
        layer.portMappingMode = 'organized';
        layer.halfFirstColumn = !!layer.halfFirstColumn;
        layer.halfLastColumn = !!layer.halfLastColumn;
        layer.halfFirstRow = !!layer.halfFirstRow;
        layer.halfLastRow = !!layer.halfLastRow;
        layer.portLabelTemplatePrimary = 'P#';
        layer.portLabelTemplateReturn = 'R#';
        layer.portLabelOverridesPrimary = {};
        layer.portLabelOverridesReturn = {};
        layer.customPortPaths = {};
        layer.customPortIndex = 1;
        // Screen name sizes default to 30 on all tabs
        layer.screenNameSizeCabinet = 30;
        layer.screenNameSizeDataFlow = 30;
        layer.screenNameSizePower = 30;
        // Cabinet ID number size default to 30
        layer.number_size = 30;
        layer.randomDataColors = false;
        // Power defaults
        layer.powerVoltage = prefs.powerVoltage;
        layer.powerVoltageCustom = prefs.powerVoltage;
        layer.powerAmperage = prefs.powerAmperage;
        layer.powerAmperageCustom = prefs.powerAmperage;
        layer.panelWatts = prefs.powerWatts;
        layer.powerMaximize = false;
        layer.powerOrganized = true;
        layer.powerCustomPath = false;
        layer.powerFlowPattern = prefs.powerFlowPattern || 'tl-h';
        layer.powerLineWidth = prefs.powerLineWidth;
        layer.powerLineColor = '#FF0000';
        layer.powerArrowColor = '#0042AA';
        layer.powerRandomColors = false;
        layer.powerColorCodedView = false;
        layer.powerCircuitColors = this.getDefaultPowerCircuitColors();
        layer.powerLabelSize = prefs.powerLabelSize;
        layer.powerLabelBgColor = '#D95000';
        layer.powerLabelTextColor = '#000000';
        layer.powerLabelTemplate = 'S1-#';
        layer.powerLabelOverrides = {};
        layer.powerCustomPaths = {};
        layer.powerCustomIndex = 1;
        layer.border_color_pixel = layer.border_color || prefs.borderColor;
        layer.border_color_cabinet = layer.border_color || prefs.borderColor;
        layer.border_color_data = layer.border_color || prefs.borderColor;
        layer.border_color_power = layer.border_color || prefs.borderColor;
        layer.panel_weight = prefs.panelWeight;
        layer.weight_unit = prefs.weightUnit || 'kg';
    }

    getSelectedLayers() {
        if (!this.project || !this.project.layers) return [];
        this.dedupeProjectLayers('get_selected_layers');
        if (!this.selectedLayerIds || this.selectedLayerIds.size === 0) {
            return this.currentLayer ? [this.currentLayer] : [];
        }
        return this.project.layers.filter(l => this.selectedLayerIds.has(l.id));
    }

    upsertProjectLayer(layer) {
        if (!this.project || !this.project.layers || !layer) return;
        const index = this.project.layers.findIndex(l => l.id === layer.id);
        if (index >= 0) {
            this.project.layers[index] = layer;
        } else {
            this.project.layers.push(layer);
        }
    }

    dedupeProjectLayers(reason = 'unknown') {
        if (!this.project || !Array.isArray(this.project.layers)) return;
        const seen = new Set();
        const deduped = [];
        const dropped = [];
        this.project.layers.forEach(layer => {
            if (!layer || layer.id === undefined || layer.id === null) return;
            if (seen.has(layer.id)) {
                dropped.push(layer.id);
                return;
            }
            seen.add(layer.id);
            deduped.push(layer);
        });
        if (dropped.length > 0) {
            this.project.layers = deduped;
            this.selectedLayerIds = new Set([...this.selectedLayerIds].filter(id => seen.has(id)));
            if (this.currentLayer && !seen.has(this.currentLayer.id)) {
                this.currentLayer = this.project.layers.length > 0 ? this.project.layers[0] : null;
            } else if (this.currentLayer) {
                this.currentLayer = this.project.layers.find(l => l.id === this.currentLayer.id) || this.currentLayer;
            }
            if (typeof sendClientLog === 'function') {
                sendClientLog('project_layers_deduped', { reason, droppedIds: dropped });
            }
        }
    }

    applyToSelectedLayers(fn) {
        const layers = this.getSelectedLayers();
        layers.forEach(fn);
    }

    setSelectedLayersByIds(ids, primaryId = null) {
        this.selectedLayerIds = new Set(ids);
        if (primaryId && this.selectedLayerIds.has(primaryId)) {
            this.currentLayer = this.project.layers.find(l => l.id === primaryId) || this.currentLayer;
        } else if (this.selectedLayerIds.size > 0) {
            const firstId = this.selectedLayerIds.values().next().value;
            this.currentLayer = this.project.layers.find(l => l.id === firstId) || this.currentLayer;
        } else {
            this.currentLayer = null;
        }
        if (this.currentLayer) {
            this.lastSelectedLayerId = this.currentLayer.id;
            this.selectionAnchorLayerId = this.currentLayer.id;
        }
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    toggleLayerSelection(layer) {
        if (!layer) return;
        if (!this.selectedLayerIds || this.selectedLayerIds.size === 0) {
            this.selectedLayerIds = new Set([layer.id]);
            this.currentLayer = layer;
        } else if (this.selectedLayerIds.has(layer.id)) {
            this.selectedLayerIds.delete(layer.id);
            if (this.currentLayer && this.currentLayer.id === layer.id) {
                const nextId = this.selectedLayerIds.values().next().value;
                this.currentLayer = nextId ? this.project.layers.find(l => l.id === nextId) : null;
            }
        } else {
            this.selectedLayerIds.add(layer.id);
            this.currentLayer = layer;
        }
        this.lastSelectedLayerId = layer.id;
        if (!this.selectionAnchorLayerId) {
            this.selectionAnchorLayerId = layer.id;
        }
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    selectLayerRange(layer) {
        if (!layer || !this.project || !this.project.layers) return;
        const order = this.layerListOrder || [...this.project.layers].reverse().map(l => l.id);
        const anchorId = this.selectionAnchorLayerId || (this.currentLayer ? this.currentLayer.id : layer.id);
        const startIndex = order.indexOf(anchorId);
        const endIndex = order.indexOf(layer.id);
        if (startIndex === -1 || endIndex === -1) {
            this.selectLayer(layer);
            return;
        }
        const [from, to] = startIndex <= endIndex ? [startIndex, endIndex] : [endIndex, startIndex];
        const rangeIds = order.slice(from, to + 1);
        this.selectedLayerIds = new Set(rangeIds);
        this.currentLayer = layer;
        this.lastSelectedLayerId = layer.id;
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    clearLayerSelection() {
        this.selectedLayerIds = new Set();
        this.currentLayer = null;
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    getFullPanelPixels(layer) {
        if (!layer) return 0;
        return (Number(layer.cabinet_width) || 0) * (Number(layer.cabinet_height) || 0);
    }

    getPanelPixelArea(panel) {
        if (!panel) return 0;
        return (Number(panel.width) || 0) * (Number(panel.height) || 0);
    }

    getPanelLoadFactor(layer, panel) {
        const fullPixels = this.getFullPanelPixels(layer);
        const panelPixels = this.getPanelPixelArea(panel);
        if (fullPixels <= 0 || panelPixels <= 0) return 0;
        const areaRatio = panelPixels / fullPixels;
        if (areaRatio >= 0.999) return 1;
        return Math.min(1, areaRatio * 1.3);
    }

    getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, orderedUnitIndices, includeHidden = false) {
        if (!layer || !Array.isArray(layer.panels) || !Array.isArray(orderedUnitIndices)) return [];
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');
        const panelMap = new Map();
        layer.panels.forEach(panel => {
            panelMap.set(`${panel.row},${panel.col}`, panel);
        });

        const ordered = [];
        orderedUnitIndices.forEach((unitIdx, unitPos) => {
            if (isHorizontalFirst) {
                const leftToRight = startsLeft ? (unitPos % 2 === 0) : (unitPos % 2 !== 0);
                if (leftToRight) {
                    for (let col = 0; col < layer.columns; col++) {
                        const panel = panelMap.get(`${unitIdx},${col}`);
                        if (!panel) continue;
                        if (includeHidden || !panel.hidden) ordered.push(panel);
                    }
                } else {
                    for (let col = layer.columns - 1; col >= 0; col--) {
                        const panel = panelMap.get(`${unitIdx},${col}`);
                        if (!panel) continue;
                        if (includeHidden || !panel.hidden) ordered.push(panel);
                    }
                }
            } else {
                const topToBottom = startsTop ? (unitPos % 2 === 0) : (unitPos % 2 !== 0);
                if (topToBottom) {
                    for (let row = 0; row < layer.rows; row++) {
                        const panel = panelMap.get(`${row},${unitIdx}`);
                        if (!panel) continue;
                        if (includeHidden || !panel.hidden) ordered.push(panel);
                    }
                } else {
                    for (let row = layer.rows - 1; row >= 0; row--) {
                        const panel = panelMap.get(`${row},${unitIdx}`);
                        if (!panel) continue;
                        if (includeHidden || !panel.hidden) ordered.push(panel);
                    }
                }
            }
        });
        return ordered;
    }

    getOrderedPanelsByPattern(layer, pattern = 'tl-h', includeHidden = false) {
        if (!layer || !Array.isArray(layer.panels) || layer.panels.length === 0) return [];
        const cols = Number(layer.columns) || 0;
        const rows = Number(layer.rows) || 0;
        if (cols <= 0 || rows <= 0) return [];

        const panelMap = new Map();
        layer.panels.forEach(panel => {
            panelMap.set(`${panel.row},${panel.col}`, panel);
        });

        const [startCorner, direction] = pattern.split('-');
        let startRow = 0;
        let startCol = 0;
        let rowDir = 1;
        let colDir = 1;

        switch (startCorner) {
            case 'tr':
                startCol = cols - 1;
                colDir = -1;
                break;
            case 'bl':
                startRow = rows - 1;
                rowDir = -1;
                break;
            case 'br':
                startRow = rows - 1;
                startCol = cols - 1;
                rowDir = -1;
                colDir = -1;
                break;
            default:
                break;
        }

        const isVerticalFirst = direction === 'v';
        const ordered = [];

        if (isVerticalFirst) {
            for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                const colOffset = Math.abs(c - startCol);
                const reverse = colOffset % 2 === 1;
                if (reverse) {
                    for (let r = startRow + (rows - 1) * rowDir; r >= 0 && r < rows; r -= rowDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel && (includeHidden || !panel.hidden)) ordered.push(panel);
                    }
                } else {
                    for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel && (includeHidden || !panel.hidden)) ordered.push(panel);
                    }
                }
            }
        } else {
            for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                const rowOffset = Math.abs(r - startRow);
                const reverse = rowOffset % 2 === 1;
                if (reverse) {
                    for (let c = startCol + (cols - 1) * colDir; c >= 0 && c < cols; c -= colDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel && (includeHidden || !panel.hidden)) ordered.push(panel);
                    }
                } else {
                    for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                        const panel = panelMap.get(`${r},${c}`);
                        if (panel && (includeHidden || !panel.hidden)) ordered.push(panel);
                    }
                }
            }
        }

        return ordered;
    }

    getLayerBounds(layer) {
        if (layer && (layer.type || 'screen') === 'image') {
            const scale = Number(layer.imageScale) || 1;
            const width = (Number(layer.imageWidth) || 0) * scale;
            const height = (Number(layer.imageHeight) || 0) * scale;
            return {
                x1: Number(layer.offset_x) || 0,
                y1: Number(layer.offset_y) || 0,
                x2: (Number(layer.offset_x) || 0) + width,
                y2: (Number(layer.offset_y) || 0) + height
            };
        }
        if (layer && Array.isArray(layer.panels) && layer.panels.length > 0) {
            let minX = Infinity;
            let minY = Infinity;
            let maxX = -Infinity;
            let maxY = -Infinity;
            layer.panels.forEach(panel => {
                const x1 = Number(panel.x) || 0;
                const y1 = Number(panel.y) || 0;
                const x2 = x1 + (Number(panel.width) || 0);
                const y2 = y1 + (Number(panel.height) || 0);
                if (x1 < minX) minX = x1;
                if (y1 < minY) minY = y1;
                if (x2 > maxX) maxX = x2;
                if (y2 > maxY) maxY = y2;
            });
            return { x1: minX, y1: minY, x2: maxX, y2: maxY };
        }
        const width = (Number(layer.columns) || 0) * (Number(layer.cabinet_width) || 0);
        const height = (Number(layer.rows) || 0) * (Number(layer.cabinet_height) || 0);
        return {
            x1: layer.offset_x,
            y1: layer.offset_y,
            x2: layer.offset_x + width,
            y2: layer.offset_y + height
        };
    }

    selectLayersInRect(rect, toggle = false) {
        if (!this.project || !this.project.layers) return;
        const minX = Math.min(rect.x1, rect.x2);
        const maxX = Math.max(rect.x1, rect.x2);
        const minY = Math.min(rect.y1, rect.y2);
        const maxY = Math.max(rect.y1, rect.y2);

        const hits = this.project.layers.filter(layer => {
            if (layer.visible === false) return false;
            const b = this.getLayerBounds(layer);
            const intersects = b.x1 <= maxX && b.x2 >= minX && b.y1 <= maxY && b.y2 >= minY;
            return intersects;
        }).map(l => l.id);

        if (!toggle) {
            this.selectedLayerIds = new Set(hits);
        } else {
            hits.forEach(id => {
                if (this.selectedLayerIds.has(id)) {
                    this.selectedLayerIds.delete(id);
                } else {
                    this.selectedLayerIds.add(id);
                }
            });
        }
        const primaryId = hits.length > 0 ? hits[hits.length - 1] : (this.currentLayer ? this.currentLayer.id : null);
        if (primaryId && this.selectedLayerIds.has(primaryId)) {
            this.currentLayer = this.project.layers.find(l => l.id === primaryId) || this.currentLayer;
        } else if (this.selectedLayerIds.size > 0 && !this.currentLayer) {
            const firstId = this.selectedLayerIds.values().next().value;
            this.currentLayer = this.project.layers.find(l => l.id === firstId) || null;
        }
        this.lastSelectedLayerId = this.currentLayer ? this.currentLayer.id : null;
        if (!this.selectionAnchorLayerId && this.currentLayer) {
            this.selectionAnchorLayerId = this.currentLayer.id;
        }
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }
    
    selectLayer(layer) {
        // Defensive: Make sure we have a valid layer
        if (!layer || !layer.id) {
            console.error('SELECT LAYER: Invalid layer', layer);
            return;
        }
        
        this.currentLayer = layer;
        this.selectedLayerIds = new Set([layer.id]);
        this.lastSelectedLayerId = layer.id;
        this.selectionAnchorLayerId = layer.id;
        sendClientLog('select_layer_before_defaults', {
            layerId: layer.id,
            processorType: layer.processorType,
            bitDepth: layer.bitDepth,
            frameRate: layer.frameRate
        });
        
        console.log('SELECT LAYER - selected id:', this.currentLayer.id);
        
        // Initialize client-side defaults if not set
        if (this.currentLayer.arrowLineWidth === undefined) {
            this.currentLayer.arrowLineWidth = 6;
        }
        if (this.currentLayer.arrowColor === undefined) {
            this.currentLayer.arrowColor = '#0042AA';
        }
        if (this.currentLayer.dataFlowColor === undefined) {
            this.currentLayer.dataFlowColor = '#FFFFFF';
        }
        if (this.currentLayer.dataFlowLabelSize === undefined) {
            this.currentLayer.dataFlowLabelSize = 30;
        }
        if (this.currentLayer.portLabelTemplatePrimary === undefined) {
            this.currentLayer.portLabelTemplatePrimary = 'P#';
        }
        if (this.currentLayer.portLabelTemplateReturn === undefined) {
            this.currentLayer.portLabelTemplateReturn = 'R#';
        }
        if (this.currentLayer.portLabelOverridesPrimary === undefined) {
            this.currentLayer.portLabelOverridesPrimary = {};
        }
        if (this.currentLayer.portLabelOverridesReturn === undefined) {
            this.currentLayer.portLabelOverridesReturn = {};
        }
        if (this.currentLayer.customPortPaths === undefined) {
            this.currentLayer.customPortPaths = {};
        }
        if (this.currentLayer.customPortIndex === undefined) {
            this.currentLayer.customPortIndex = 1;
        }
        if (this.currentLayer.primaryColor === undefined) {
            this.currentLayer.primaryColor = '#00FF00';
        }
        if (this.currentLayer.primaryTextColor === undefined) {
            this.currentLayer.primaryTextColor = '#000000';
        }
        if (this.currentLayer.backupColor === undefined) {
            this.currentLayer.backupColor = '#FF0000';
        }
        if (this.currentLayer.backupTextColor === undefined) {
            this.currentLayer.backupTextColor = '#FFFFFF';
        }
        if (this.currentLayer.powerLabelBgColor === undefined) {
            this.currentLayer.powerLabelBgColor = '#D95000';
        }
        if (this.currentLayer.powerLabelTextColor === undefined) {
            this.currentLayer.powerLabelTextColor = '#000000';
        }
        if (this.currentLayer.flowPattern === undefined) {
            this.currentLayer.flowPattern = 'tl-h';
        }
        if (this.currentLayer.screenNameSizeCabinet === undefined) {
            this.currentLayer.screenNameSizeCabinet = 30;
        }
        if (this.currentLayer.screenNameSizeDataFlow === undefined) {
            this.currentLayer.screenNameSizeDataFlow = 30;
        }
        if (this.currentLayer.screenNameSizePower === undefined) {
            this.currentLayer.screenNameSizePower = 30;
        }
        if (this.currentLayer.showDataFlowPortInfo === undefined) {
            this.currentLayer.showDataFlowPortInfo = false;
        }
        if (this.currentLayer.showPowerCircuitInfo === undefined) {
            this.currentLayer.showPowerCircuitInfo = false;
        }
        if (this.currentLayer.number_size === undefined) {
            this.currentLayer.number_size = 30;
        }
        if (this.currentLayer.bitDepth === undefined) {
            this.currentLayer.bitDepth = this.getPreferences().bitDepth;
        }
        if (this.currentLayer.frameRate === undefined) {
            this.currentLayer.frameRate = this.getPreferences().frameRate;
        }
        if (this.currentLayer.processorType === undefined) {
            this.currentLayer.processorType = this.getPreferences().processorType;
        }
        if (!this.currentLayer.type) {
            this.currentLayer.type = 'screen';
        }

        sendClientLog('select_layer_after_defaults', {
            layerId: this.currentLayer.id,
            layerName: this.currentLayer.name,
            type: this.currentLayer.type || 'screen',
            columns: this.currentLayer.columns,
            rows: this.currentLayer.rows,
            processorType: this.currentLayer.processorType,
            bitDepth: this.currentLayer.bitDepth,
            frameRate: this.currentLayer.frameRate,
            tab: window.canvasRenderer ? window.canvasRenderer.viewMode : '?',
            selectedLayerIds: this.selectedLayerIds ? [...this.selectedLayerIds] : [],
            showLabelName: this.currentLayer.showLabelName,
            showDataFlowPortInfo: this.currentLayer.showDataFlowPortInfo,
            showPowerCircuitInfo: this.currentLayer.showPowerCircuitInfo
        });
        
        console.log('SELECT LAYER - after defaults:', {
            arrowLineWidth: this.currentLayer.arrowLineWidth,
            arrowColor: this.currentLayer.arrowColor,
            dataFlowLabelSize: this.currentLayer.dataFlowLabelSize
        });
        
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }
    
    deleteLayer(layerId) {
        if (this.project.layers.length === 1) {
            alert('Cannot delete the last layer');
            return;
        }
        
        // Check if we're deleting the currently selected layer
        const isDeletingSelected = this.currentLayer && this.currentLayer.id === layerId;
        const deletedIndex = this.project.layers.findIndex(l => l.id === layerId);
        
        // Save the current selection ID (if not deleting it)
        const keepSelectedId = isDeletingSelected ? null : this.currentLayer?.id;
        
        // Save client-side props for remaining layers BEFORE the delete
        const savedClientProps = {};
        this.project.layers.forEach(layer => {
            if (layer.id !== layerId) {
                savedClientProps[layer.id] = this.extractClientSideProps(layer);
            }
        });
        
        console.log('DELETE LAYER - deleting id:', layerId, 'isDeletingSelected:', isDeletingSelected);
        
        fetch(`/api/layer/${layerId}`, {
            method: 'DELETE'
        })
        .then(res => res.json())
        .then(project => {
            this.project = project;
            
            // Restore client-side properties to remaining layers
            this.project.layers.forEach(layer => {
                if (savedClientProps[layer.id]) {
                    Object.assign(layer, savedClientProps[layer.id]);
                }
            });
            
            // Handle selection
            if (this.project.layers.length > 0) {
                if (keepSelectedId) {
                    // Keep the same layer selected (it wasn't deleted)
                    const keepLayer = this.project.layers.find(l => l.id === keepSelectedId);
                    if (keepLayer) {
                        this.selectLayer(keepLayer);
                    }
                } else {
                    // We deleted the selected layer - select adjacent layer
                    // If deleted from bottom (index 0), select new bottom (index 0)
                    // Otherwise select the layer that's now at the deleted position (or last if at end)
                    const newIndex = Math.min(deletedIndex, this.project.layers.length - 1);
                    this.selectLayer(this.project.layers[newIndex]);
                }
            } else {
                this.currentLayer = null;
            }
            
            this.updateUI();
            
            // Save state after delete
            this.saveState('Delete Layer');
        });
    }
    
    toggleLayerVisibility(layerId) {
        const layer = this.project.layers.find(l => l.id === layerId);
        if (layer) {
            layer.visible = !layer.visible;
            sendClientLog('toggle_visibility', {
                id: layer.id,
                name: layer.name,
                visible: layer.visible
            });
            window.canvasRenderer.render();
            this.renderLayers();
        }
    }

    setLockOnSelected(locked) {
        const layers = this.getSelectedLayers();
        if (layers.length === 0) return;
        layers.forEach(layer => {
            layer.locked = locked;
            fetch(`/api/layer/${layer.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ locked })
            });
        });
        if (typeof sendClientLog === 'function') {
            sendClientLog('layer_lock_batch', { locked, layerIds: layers.map(l => l.id) });
        }
        this.renderLayers();
    }

    toggleLockOnSelected() {
        const layers = this.getSelectedLayers();
        if (layers.length === 0) return;
        const anyUnlocked = layers.some(l => !l.locked);
        this.setLockOnSelected(anyUnlocked);
    }

    toggleLayerLock(layerId) {
        const layer = this.project.layers.find(l => l.id === layerId);
        if (!layer) return;
        layer.locked = !layer.locked;
        fetch(`/api/layer/${layer.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ locked: layer.locked })
        });
        if (typeof sendClientLog === 'function') {
            sendClientLog('layer_lock_toggle', { layerId: layer.id, locked: layer.locked });
        }
        this.renderLayers();
    }
    
    togglePanelBlank(layerId, panelId) {
        fetch(`/api/layer/${layerId}/panel/${panelId}/toggle`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(panel => {
            const layer = this.project.layers.find(l => l.id === layerId);
            if (layer) {
                const panelIndex = layer.panels.findIndex(p => p.id === panelId);
                if (panelIndex >= 0) {
                    layer.panels[panelIndex] = panel;
                    window.canvasRenderer.render();
                }
            }
        });
    }
    
    togglePanelHidden(layerId, panelId) {
        fetch(`/api/layer/${layerId}/panel/${panelId}/toggle_hidden`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(panel => {
            const layer = this.project.layers.find(l => l.id === layerId);
            if (layer) {
                const panelIndex = layer.panels.findIndex(p => p.id === panelId);
                if (panelIndex >= 0) {
                    layer.panels[panelIndex] = panel;
                    sendClientLog('toggle_panel_hidden', {
                        layerId, layerName: layer.name,
                        panelId, row: panel.row, col: panel.col,
                        hidden: panel.hidden
                    });
                    window.canvasRenderer.render();
                }
            }
        });
    }
    
    updateLayer(saveHistory = false, historyAction = 'Update Layer') {
        if (!this.currentLayer) return;
        
        // Save state before update if requested
        if (saveHistory) {
            this.saveState(historyAction);
        }
        
        fetch(`/api/layer/${this.currentLayer.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.currentLayer)
        })
        .then(res => res.json())
        .then(layer => {
            const index = this.project.layers.findIndex(l => l.id === layer.id);
            if (index >= 0) {
                // Preserve client-side only properties that server might not return
                const preservedProps = {
                    screenNameOffsetX: this.currentLayer.screenNameOffsetX,
                    screenNameOffsetY: this.currentLayer.screenNameOffsetY,
                    screenNameOffsetXCabinet: this.currentLayer.screenNameOffsetXCabinet,
                    screenNameOffsetYCabinet: this.currentLayer.screenNameOffsetYCabinet,
                    screenNameOffsetXDataFlow: this.currentLayer.screenNameOffsetXDataFlow,
                    screenNameOffsetYDataFlow: this.currentLayer.screenNameOffsetYDataFlow,
                    screenNameOffsetXPower: this.currentLayer.screenNameOffsetXPower,
                    screenNameOffsetYPower: this.currentLayer.screenNameOffsetYPower,
                    screenNameSize: this.currentLayer.screenNameSize,
                    screenNameSizeCabinet: this.currentLayer.screenNameSizeCabinet,
                    screenNameSizeDataFlow: this.currentLayer.screenNameSizeDataFlow,
                    screenNameSizePower: this.currentLayer.screenNameSizePower,
                    flowPattern: this.currentLayer.flowPattern,
                    dataFlowColor: this.currentLayer.dataFlowColor,
                    dataFlowLabelSize: this.currentLayer.dataFlowLabelSize,
                    arrowLineWidth: this.currentLayer.arrowLineWidth,
                    primaryColor: this.currentLayer.primaryColor,
                    primaryTextColor: this.currentLayer.primaryTextColor,
                    backupColor: this.currentLayer.backupColor,
                    backupTextColor: this.currentLayer.backupTextColor,
                    randomDataColors: this.currentLayer.randomDataColors,
                    portLabelTemplatePrimary: this.currentLayer.portLabelTemplatePrimary,
                    portLabelTemplateReturn: this.currentLayer.portLabelTemplateReturn,
                    portLabelOverridesPrimary: this.currentLayer.portLabelOverridesPrimary,
                    portLabelOverridesReturn: this.currentLayer.portLabelOverridesReturn,
                    customPortPaths: this.currentLayer.customPortPaths,
                    customPortIndex: this.currentLayer.customPortIndex,
                    processorType: this.currentLayer.processorType,
                    bitDepth: this.currentLayer.bitDepth,
                    frameRate: this.currentLayer.frameRate,
                    portMappingMode: this.currentLayer.portMappingMode,
                    powerVoltage: this.currentLayer.powerVoltage,
                    powerVoltageCustom: this.currentLayer.powerVoltageCustom,
                    powerAmperage: this.currentLayer.powerAmperage,
                    powerAmperageCustom: this.currentLayer.powerAmperageCustom,
                    panelWatts: this.currentLayer.panelWatts,
                    powerMaximize: this.currentLayer.powerMaximize,
                    powerOrganized: this.currentLayer.powerOrganized,
                    powerCustomPath: this.currentLayer.powerCustomPath,
                    powerFlowPattern: this.currentLayer.powerFlowPattern,
                    powerLineWidth: this.currentLayer.powerLineWidth,
                    powerLineColor: this.currentLayer.powerLineColor,
                    powerArrowColor: this.currentLayer.powerArrowColor,
                    powerRandomColors: this.currentLayer.powerRandomColors,
                    powerColorCodedView: this.currentLayer.powerColorCodedView,
                    powerCircuitColors: this.currentLayer.powerCircuitColors,
                    powerLabelSize: this.currentLayer.powerLabelSize,
                    powerLabelBgColor: this.currentLayer.powerLabelBgColor,
                    powerLabelTextColor: this.currentLayer.powerLabelTextColor,
                    powerLabelTemplate: this.currentLayer.powerLabelTemplate,
                    powerLabelOverrides: this.currentLayer.powerLabelOverrides,
                    powerCustomPaths: this.currentLayer.powerCustomPaths,
                    powerCustomIndex: this.currentLayer.powerCustomIndex,
                    border_color_pixel: this.currentLayer.border_color_pixel,
                    border_color_cabinet: this.currentLayer.border_color_cabinet,
                    border_color_data: this.currentLayer.border_color_data,
                    border_color_power: this.currentLayer.border_color_power,
                    lastPowerFlowPattern: this.currentLayer.lastPowerFlowPattern,
                    showDataFlowPortInfo: this.currentLayer.showDataFlowPortInfo,
                    showPowerCircuitInfo: this.currentLayer.showPowerCircuitInfo,
                    _powerTotalAmps1: this.currentLayer._powerTotalAmps1,
                    _powerTotalAmps3: this.currentLayer._powerTotalAmps3,
                    _powerCircuitsRequired: this.currentLayer._powerCircuitsRequired,
                    panel_weight: this.currentLayer.panel_weight,
                    weight_unit: this.currentLayer.weight_unit,
                    infoLabelSize: this.currentLayer.infoLabelSize,
                    type: this.currentLayer.type,
                    imageData: this.currentLayer.imageData,
                    imageWidth: this.currentLayer.imageWidth,
                    imageHeight: this.currentLayer.imageHeight,
                    imageScale: this.currentLayer.imageScale
                };
                
                console.log('PRESERVING PROPS:', preservedProps);
                
                // Merge preserved props back into returned layer
                Object.keys(preservedProps).forEach(key => {
                    if (preservedProps[key] !== undefined) {
                        layer[key] = preservedProps[key];
                    }
                });
                
                console.log('AFTER MERGE - layer.dataFlowColor:', layer.dataFlowColor);
                console.log('AFTER MERGE - layer.screenNameSize:', layer.screenNameSize);
                console.log('AFTER MERGE - layer.screenNameOffsetX:', layer.screenNameOffsetX);
                
                this.project.layers[index] = layer;
                this.currentLayer = layer;
                this.updateUI();
            }
        });
    }

    updateLayers(layers, saveHistory = false, historyAction = 'Update Layers') {
        if (!layers || layers.length === 0) return;
        if (!this.project || !this.project.layers) return;

        if (saveHistory) {
            this.saveState(historyAction);
        }
        sendClientLog('update_layers', {
            count: layers.length,
            action: historyAction,
            tab: window.canvasRenderer ? window.canvasRenderer.viewMode : '?',
            layers: layers.map(l => ({
                id: l.id, name: l.name,
                columns: l.columns, rows: l.rows,
                offset_x: l.offset_x, offset_y: l.offset_y,
                showLabelName: l.showLabelName,
                showDataFlowPortInfo: l.showDataFlowPortInfo,
                showPowerCircuitInfo: l.showPowerCircuitInfo
            }))
        });

        const requests = layers.map(layer => {
            const preservedProps = {
                screenNameOffsetX: layer.screenNameOffsetX,
                screenNameOffsetY: layer.screenNameOffsetY,
                screenNameOffsetXCabinet: layer.screenNameOffsetXCabinet,
                screenNameOffsetYCabinet: layer.screenNameOffsetYCabinet,
                screenNameOffsetXDataFlow: layer.screenNameOffsetXDataFlow,
                screenNameOffsetYDataFlow: layer.screenNameOffsetYDataFlow,
                screenNameOffsetXPower: layer.screenNameOffsetXPower,
                screenNameOffsetYPower: layer.screenNameOffsetYPower,
                screenNameSize: layer.screenNameSize,
                screenNameSizeCabinet: layer.screenNameSizeCabinet,
                screenNameSizeDataFlow: layer.screenNameSizeDataFlow,
                screenNameSizePower: layer.screenNameSizePower,
                flowPattern: layer.flowPattern,
                dataFlowColor: layer.dataFlowColor,
                dataFlowLabelSize: layer.dataFlowLabelSize,
                arrowLineWidth: layer.arrowLineWidth,
                primaryColor: layer.primaryColor,
                primaryTextColor: layer.primaryTextColor,
                backupColor: layer.backupColor,
                backupTextColor: layer.backupTextColor,
                randomDataColors: layer.randomDataColors,
                portLabelTemplatePrimary: layer.portLabelTemplatePrimary,
                portLabelTemplateReturn: layer.portLabelTemplateReturn,
                portLabelOverridesPrimary: layer.portLabelOverridesPrimary,
                portLabelOverridesReturn: layer.portLabelOverridesReturn,
                customPortPaths: layer.customPortPaths,
                customPortIndex: layer.customPortIndex,
                processorType: layer.processorType,
                bitDepth: layer.bitDepth,
                frameRate: layer.frameRate,
                portMappingMode: layer.portMappingMode,
                powerVoltage: layer.powerVoltage,
                powerVoltageCustom: layer.powerVoltageCustom,
                powerAmperage: layer.powerAmperage,
                powerAmperageCustom: layer.powerAmperageCustom,
                panelWatts: layer.panelWatts,
                powerMaximize: layer.powerMaximize,
                powerOrganized: layer.powerOrganized,
                powerCustomPath: layer.powerCustomPath,
                powerFlowPattern: layer.powerFlowPattern,
                powerLineWidth: layer.powerLineWidth,
                powerLineColor: layer.powerLineColor,
                powerArrowColor: layer.powerArrowColor,
                powerRandomColors: layer.powerRandomColors,
                powerColorCodedView: layer.powerColorCodedView,
                powerCircuitColors: layer.powerCircuitColors,
                powerLabelSize: layer.powerLabelSize,
                powerLabelBgColor: layer.powerLabelBgColor,
                powerLabelTextColor: layer.powerLabelTextColor,
                powerLabelTemplate: layer.powerLabelTemplate,
                powerLabelOverrides: layer.powerLabelOverrides,
                powerCustomPaths: layer.powerCustomPaths,
                powerCustomIndex: layer.powerCustomIndex,
                border_color_pixel: layer.border_color_pixel,
                border_color_cabinet: layer.border_color_cabinet,
                border_color_data: layer.border_color_data,
                border_color_power: layer.border_color_power,
                lastPowerFlowPattern: layer.lastPowerFlowPattern,
                showDataFlowPortInfo: layer.showDataFlowPortInfo,
                showPowerCircuitInfo: layer.showPowerCircuitInfo,
                _powerTotalAmps1: layer._powerTotalAmps1,
                _powerTotalAmps3: layer._powerTotalAmps3,
                _powerCircuitsRequired: layer._powerCircuitsRequired,
                panel_weight: layer.panel_weight,
                weight_unit: layer.weight_unit,
                infoLabelSize: layer.infoLabelSize,
                type: layer.type,
                imageData: layer.imageData,
                imageWidth: layer.imageWidth,
                imageHeight: layer.imageHeight,
                imageScale: layer.imageScale
            };

            return fetch(`/api/layer/${layer.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(layer)
            })
            .then(res => res.json())
            .then(updated => {
                Object.keys(preservedProps).forEach(key => {
                    if (preservedProps[key] !== undefined) {
                        updated[key] = preservedProps[key];
                    }
                });
                const index = this.project.layers.findIndex(l => l.id === updated.id);
                if (index >= 0) {
                    this.project.layers[index] = updated;
                }
            });
        });

        Promise.all(requests).then(() => {
            // Keep currentLayer reference if possible
            if (this.currentLayer) {
                const refreshed = this.project.layers.find(l => l.id === this.currentLayer.id);
                if (refreshed) this.currentLayer = refreshed;
            }
            this.updateUI();
            if (window.canvasRenderer) {
                if (window.canvasRenderer.viewMode === 'power') {
                    this.updatePowerCapacityDisplay();
                    window.canvasRenderer.render();
                } else if (window.canvasRenderer.viewMode === 'data-flow') {
                    this.updatePortCapacityDisplay();
                    this.updatePortLabelEditor();
                    window.canvasRenderer.render();
                }
            }
        });
    }
    
    updateLayerFromInputs() {
        const targetLayers = this.getSelectedLayers();
        if (targetLayers.length === 0) return;
        
        // Evaluate math expressions and update the input fields with results
        const readNumber = (id) => {
            const el = document.getElementById(id);
            if (!el) return { value: null, raw: null };
            const raw = String(el.value || '').trim();
            if (raw === '') return { value: null, raw: '' };
            return { value: evaluateMathExpression(raw), raw };
        };

        const offsetXVal = readNumber('offset-x').value;
        const offsetYVal = readNumber('offset-y').value;
        
        // For multi-select: only apply the offset field that was actually changed by the user.
        // This prevents typing in Y from overwriting all layers' X values (or vice versa).
        const multiSelected = targetLayers.length > 1;
        const lastChanged = this._lastChangedInputId || null;
        const applyOffsetX = offsetXVal !== null && (!multiSelected || lastChanged === 'offset-x');
        const applyOffsetY = offsetYVal !== null && (!multiSelected || lastChanged === 'offset-y');
        const cabinetWidthVal = readNumber('cabinet-width').value;
        const cabinetHeightVal = readNumber('cabinet-height').value;
        const columnsVal = readNumber('screen-columns').value;
        const rowsVal = readNumber('screen-rows').value;
        const numberSizeVal = readNumber('number-size').value;
        const halfFirstColumnEl = document.getElementById('half-first-column');
        const halfLastColumnEl = document.getElementById('half-last-column');
        const halfFirstRowEl = document.getElementById('half-first-row');
        const halfLastRowEl = document.getElementById('half-last-row');
        const halfFirstColumnVal = halfFirstColumnEl && !halfFirstColumnEl.indeterminate ? halfFirstColumnEl.checked : null;
        const halfLastColumnVal = halfLastColumnEl && !halfLastColumnEl.indeterminate ? halfLastColumnEl.checked : null;
        const halfFirstRowVal = halfFirstRowEl && !halfFirstRowEl.indeterminate ? halfFirstRowEl.checked : null;
        const halfLastRowVal = halfLastRowEl && !halfLastRowEl.indeterminate ? halfLastRowEl.checked : null;
        
        // Panel physical dimensions
        const panelWidthMMVal = readNumber('panel-width-mm').value;
        const panelHeightMMVal = readNumber('panel-height-mm').value;
        const panelWeightVal = readNumber('panel-weight-kg').value;
        const panelWeightUnitEl = document.getElementById('panel-weight-unit');
        const panelWeightUnitVal = panelWeightUnitEl ? panelWeightUnitEl.value : null;
        const imageScaleEl = document.getElementById('image-scale');
        const imageScaleVal = imageScaleEl ? (parseFloat(imageScaleEl.value) / 100) : null;
        
        // Border settings
        const showPanelBordersEl = document.getElementById('show-panel-borders');
        const showCircleWithXEl = document.getElementById('show-circle-with-x');
        const borderColorEl = document.getElementById('border-color');
        const borderColorCabinetEl = document.getElementById('border-color-cabinet');
        const borderColorDataEl = document.getElementById('border-color-data');
        const borderColorPowerEl = document.getElementById('border-color-power');
        const primaryTextColorEl = document.getElementById('primary-text-color');
        const backupTextColorEl = document.getElementById('backup-text-color');
        const powerLabelBgColorEl = document.getElementById('power-label-bg-color');
        const powerLabelTextColorEl = document.getElementById('power-label-text-color');
        const showPanelBordersVal = showPanelBordersEl && !showPanelBordersEl.indeterminate ? showPanelBordersEl.checked : null;
        const showCircleWithXVal = showCircleWithXEl && !showCircleWithXEl.indeterminate ? showCircleWithXEl.checked : null;
        const borderColorVal = borderColorEl ? borderColorEl.value : null;
        const borderColorCabinetVal = borderColorCabinetEl ? borderColorCabinetEl.value : null;
        const borderColorDataVal = borderColorDataEl ? borderColorDataEl.value : null;
        const borderColorPowerVal = borderColorPowerEl ? borderColorPowerEl.value : null;
        const primaryTextColorVal = primaryTextColorEl ? primaryTextColorEl.value : null;
        const backupTextColorVal = backupTextColorEl ? backupTextColorEl.value : null;
        const powerLabelBgColorVal = powerLabelBgColorEl ? powerLabelBgColorEl.value : null;
        const powerLabelTextColorVal = powerLabelTextColorEl ? powerLabelTextColorEl.value : null;
        
        
        // Per-layer label settings
        const showLabelNameEl = document.getElementById('show-label-name');
        const showLabelSizePxEl = document.getElementById('show-label-size-px');
        const showLabelSizeMEl = document.getElementById('show-label-size-m');
        const showLabelSizeFtEl = document.getElementById('show-label-size-ft');
        const showLabelInfoEl = document.getElementById('show-label-info');
        const showLabelWeightEl = document.getElementById('show-label-weight');
        const labelsColorEl = document.getElementById('labels-color');
        const labelsFontSizeEl = document.getElementById('labels-fontsize');
        const useFractionalInchesEl = document.getElementById('use-fractional-inches');

        const showLabelNameVal = showLabelNameEl && !showLabelNameEl.indeterminate ? showLabelNameEl.checked : null;
        const showLabelSizePxVal = showLabelSizePxEl && !showLabelSizePxEl.indeterminate ? showLabelSizePxEl.checked : null;
        const showLabelSizeMVal = showLabelSizeMEl && !showLabelSizeMEl.indeterminate ? showLabelSizeMEl.checked : null;
        const showLabelSizeFtVal = showLabelSizeFtEl && !showLabelSizeFtEl.indeterminate ? showLabelSizeFtEl.checked : null;
        const showLabelInfoVal = showLabelInfoEl && !showLabelInfoEl.indeterminate ? showLabelInfoEl.checked : null;
        const showLabelWeightVal = showLabelWeightEl && !showLabelWeightEl.indeterminate ? showLabelWeightEl.checked : null;
        const labelsColorVal = labelsColorEl ? labelsColorEl.value : null;
        const labelsFontSizeVal = labelsFontSizeEl ? parseInt(labelsFontSizeEl.value) : null;
        const infoLabelSizeEl = document.getElementById('info-label-size');
        const infoLabelSizeVal = infoLabelSizeEl ? parseInt(infoLabelSizeEl.value, 10) : null;
        const useFractionalInchesVal = useFractionalInchesEl && !useFractionalInchesEl.indeterminate ? useFractionalInchesEl.checked : null;
        
        // Per-layer offset settings
        const showOffsetTLEl = document.getElementById('show-offset-tl');
        const showOffsetTREl = document.getElementById('show-offset-tr');
        const showOffsetBLEl = document.getElementById('show-offset-bl');
        const showOffsetBREl = document.getElementById('show-offset-br');
        const showOffsetTLVal = showOffsetTLEl && !showOffsetTLEl.indeterminate ? showOffsetTLEl.checked : null;
        const showOffsetTRVal = showOffsetTREl && !showOffsetTREl.indeterminate ? showOffsetTREl.checked : null;
        const showOffsetBLVal = showOffsetBLEl && !showOffsetBLEl.indeterminate ? showOffsetBLEl.checked : null;
        const showOffsetBRVal = showOffsetBREl && !showOffsetBREl.indeterminate ? showOffsetBREl.checked : null;
        
        const showNumbersEl = document.getElementById('show-numbers');
        const showNumbersVal = showNumbersEl && !showNumbersEl.indeterminate ? showNumbersEl.checked : null;

        // Update the layer properties for all selected layers
        targetLayers.forEach(layer => {
            const isImage = (layer.type || 'screen') === 'image';
            if (!layer.locked) {
                if (applyOffsetX) layer.offset_x = offsetXVal;
                if (applyOffsetY) layer.offset_y = offsetYVal;
            }
            if (isImage) {
                if (imageScaleVal !== null && !Number.isNaN(imageScaleVal)) {
                    layer.imageScale = Math.max(0.01, imageScaleVal);
                }
            } else {
                if (cabinetWidthVal !== null) layer.cabinet_width = cabinetWidthVal;
                if (cabinetHeightVal !== null) layer.cabinet_height = cabinetHeightVal;
                if (columnsVal !== null) layer.columns = Math.round(columnsVal);
                if (rowsVal !== null) layer.rows = Math.round(rowsVal);
                if (halfFirstColumnVal !== null) layer.halfFirstColumn = halfFirstColumnVal;
                if (halfLastColumnVal !== null) layer.halfLastColumn = halfLastColumnVal;
                if (halfFirstRowVal !== null) layer.halfFirstRow = halfFirstRowVal;
                if (halfLastRowVal !== null) layer.halfLastRow = halfLastRowVal;
                if (showNumbersVal !== null) layer.show_numbers = showNumbersVal;
                if (numberSizeVal !== null) layer.number_size = Math.round(numberSizeVal);
                if (panelWidthMMVal !== null) layer.panel_width_mm = panelWidthMMVal;
                if (panelHeightMMVal !== null) layer.panel_height_mm = panelHeightMMVal;
                if (panelWeightVal !== null) layer.panel_weight = panelWeightVal;
                if (panelWeightUnitVal !== null) layer.weight_unit = panelWeightUnitVal;
                if (showPanelBordersVal !== null) layer.show_panel_borders = showPanelBordersVal;
                if (showCircleWithXVal !== null) layer.show_circle_with_x = showCircleWithXVal;
                if (borderColorVal !== null) layer.border_color_pixel = borderColorVal;
                if (borderColorCabinetVal !== null) layer.border_color_cabinet = borderColorCabinetVal;
                if (borderColorDataVal !== null) layer.border_color_data = borderColorDataVal;
                if (borderColorPowerVal !== null) layer.border_color_power = borderColorPowerVal;
            }
            if (primaryTextColorVal !== null) layer.primaryTextColor = primaryTextColorVal;
            if (backupTextColorVal !== null) layer.backupTextColor = backupTextColorVal;
            if (powerLabelBgColorVal !== null) layer.powerLabelBgColor = powerLabelBgColorVal;
            if (powerLabelTextColorVal !== null) layer.powerLabelTextColor = powerLabelTextColorVal;

            if (showLabelNameVal !== null) layer.showLabelName = showLabelNameVal;
            if (showLabelSizePxVal !== null) layer.showLabelSizePx = showLabelSizePxVal;
            if (showLabelSizeMVal !== null) layer.showLabelSizeM = showLabelSizeMVal;
            if (showLabelSizeFtVal !== null) layer.showLabelSizeFt = showLabelSizeFtVal;
            if (showLabelInfoVal !== null) layer.showLabelInfo = showLabelInfoVal;
            if (showLabelWeightVal !== null) layer.showLabelWeight = showLabelWeightVal;
            if (labelsColorVal !== null) layer.labelsColor = labelsColorVal;
            if (labelsFontSizeVal !== null) layer.labelsFontSize = labelsFontSizeVal;
            if (infoLabelSizeVal !== null) layer.infoLabelSize = infoLabelSizeVal;
            if (useFractionalInchesVal !== null) layer.useFractionalInches = useFractionalInchesVal;

            if (showOffsetTLVal !== null) layer.showOffsetTL = showOffsetTLVal;
            if (showOffsetTRVal !== null) layer.showOffsetTR = showOffsetTRVal;
            if (showOffsetBLVal !== null) layer.showOffsetBL = showOffsetBLVal;
            if (showOffsetBRVal !== null) layer.showOffsetBR = showOffsetBRVal;
        });
        
        // Trigger immediate render so changes show up right away
        window.canvasRenderer.render();
        
        // Update input fields with evaluated results
        if (offsetXVal !== null) document.getElementById('offset-x').value = offsetXVal;
        if (offsetYVal !== null) document.getElementById('offset-y').value = offsetYVal;
        if (cabinetWidthVal !== null && document.getElementById('cabinet-width')) document.getElementById('cabinet-width').value = cabinetWidthVal;
        if (cabinetHeightVal !== null && document.getElementById('cabinet-height')) document.getElementById('cabinet-height').value = cabinetHeightVal;
        if (columnsVal !== null && document.getElementById('screen-columns')) document.getElementById('screen-columns').value = Math.round(columnsVal);
        if (rowsVal !== null && document.getElementById('screen-rows')) document.getElementById('screen-rows').value = Math.round(rowsVal);
        if (numberSizeVal !== null && document.getElementById('number-size')) document.getElementById('number-size').value = Math.round(numberSizeVal);
        if (panelWidthMMVal !== null && document.getElementById('panel-width-mm')) document.getElementById('panel-width-mm').value = panelWidthMMVal;
        if (panelHeightMMVal !== null && document.getElementById('panel-height-mm')) document.getElementById('panel-height-mm').value = panelHeightMMVal;
        if (panelWeightVal !== null && document.getElementById('panel-weight-kg')) document.getElementById('panel-weight-kg').value = panelWeightVal;
        
        // Update port capacity display when panel size changes (screen layers only)
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'screen') {
            this.updatePortCapacityDisplay();
        }
        
        this.updateLayers(targetLayers);
    }
    
    loadLayerToInputs() {
        const layers = this.getSelectedLayers();
        if (layers.length === 0) return;
        const primary = this.currentLayer || layers[0];
        const allImages = layers.every(l => (l.type || 'screen') === 'image');
        const screenGridSection = document.getElementById('screen-grid-settings');
        const imageSection = document.getElementById('image-layer-section');
        if (screenGridSection) {
            screenGridSection.style.display = allImages ? 'none' : '';
        }
        if (imageSection) {
            imageSection.style.display = allImages ? '' : 'none';
        }
        document.querySelectorAll('.screen-only').forEach(el => {
            if (el.classList.contains('tab-panel')) return;
            el.style.display = allImages ? 'none' : '';
        });
        document.querySelectorAll('.image-only').forEach(el => {
            if (el.classList.contains('tab-panel')) return;
            el.style.display = allImages ? '' : 'none';
        });
        this.updateLayerPanelVisibility(allImages);

        const getCommon = (getter) => {
            const first = getter(layers[0]);
            const mixed = layers.some(l => getter(l) !== first);
            return { mixed, value: first };
        };

        const setTextInput = (id, common) => {
            const el = document.getElementById(id);
            if (!el) return;
            if (common.mixed) {
                el.value = '';
                el.placeholder = '—';
            } else {
                el.value = common.value;
                el.placeholder = '';
            }
        };

        const setCheckbox = (id, common) => {
            const el = document.getElementById(id);
            if (!el) return;
            if (common.mixed) {
                el.indeterminate = true;
            } else {
                el.indeterminate = false;
                el.checked = !!common.value;
            }
        };

        setTextInput('offset-x', getCommon(l => l.offset_x));
        setTextInput('offset-y', getCommon(l => l.offset_y));

        // Image layer controls
        const imageScaleEl = document.getElementById('image-scale');
        const imageScaleRangeEl = document.getElementById('image-scale-range');
        const imageSizeEl = document.getElementById('image-size-display');
        if (allImages) {
            const scaleCommon = getCommon(l => Math.round((l.imageScale || 1) * 100));
            if (imageScaleEl) {
                imageScaleEl.value = scaleCommon.mixed ? '' : scaleCommon.value;
                imageScaleEl.placeholder = scaleCommon.mixed ? '—' : '';
            }
            if (imageScaleRangeEl) {
                imageScaleRangeEl.value = scaleCommon.mixed ? '100' : String(scaleCommon.value);
            }
            if (imageSizeEl) {
                const w = primary.imageWidth || 0;
                const h = primary.imageHeight || 0;
                imageSizeEl.textContent = `${w}×${h}px`;
            }
        } else {
            if (imageScaleEl) {
                imageScaleEl.value = '';
                imageScaleEl.placeholder = '';
            }
            if (imageScaleRangeEl) {
                imageScaleRangeEl.value = '100';
            }
            if (imageSizeEl) {
                imageSizeEl.textContent = '—';
            }
        }
        setTextInput('cabinet-width', getCommon(l => l.cabinet_width));
        setTextInput('cabinet-height', getCommon(l => l.cabinet_height));
        setTextInput('screen-columns', getCommon(l => l.columns));
        setTextInput('screen-rows', getCommon(l => l.rows));
        setCheckbox('half-first-column', getCommon(l => !!l.halfFirstColumn));
        setCheckbox('half-last-column', getCommon(l => !!l.halfLastColumn));
        setCheckbox('half-first-row', getCommon(l => !!l.halfFirstRow));
        setCheckbox('half-last-row', getCommon(l => !!l.halfLastRow));
        setCheckbox('show-numbers', getCommon(l => l.show_numbers !== false));
        setTextInput('number-size', getCommon(l => l.number_size || 24));
        
        // Load Cabinet ID settings
        const cabinetIdStyle = primary.cabinetIdStyle || 'column-row';
        const cabinetIdStyleRadio = document.querySelector(`input[name="cabinet-id-style"][value="${cabinetIdStyle}"]`);
        if (cabinetIdStyleRadio) cabinetIdStyleRadio.checked = true;
        
        const cabinetIdPosition = primary.cabinetIdPosition || 'center';
        const cabinetIdPositionRadio = document.querySelector(`input[name="cabinet-id-position"][value="${cabinetIdPosition}"]`);
        if (cabinetIdPositionRadio) cabinetIdPositionRadio.checked = true;
        
        const cabinetIdColor = primary.cabinetIdColor || '#ffffff';
        if (document.getElementById('cabinet-id-color')) {
            document.getElementById('cabinet-id-color').value = cabinetIdColor;
        }
        if (document.getElementById('cabinet-id-color-hex')) {
            document.getElementById('cabinet-id-color-hex').value = cabinetIdColor.toUpperCase();
        }
        
        // Load panel physical dimensions if elements exist
        setTextInput('panel-width-mm', getCommon(l => l.panel_width_mm || 500));
        setTextInput('panel-height-mm', getCommon(l => l.panel_height_mm || 500));
        setTextInput('panel-weight-kg', getCommon(l => l.panel_weight || 20));
        const weightUnitEl = document.getElementById('panel-weight-unit');
        if (weightUnitEl) {
            const unitCommon = getCommon(l => l.weight_unit || 'kg');
            if (!unitCommon.mixed) {
                weightUnitEl.value = unitCommon.value;
            }
        }
        
        // Load border settings (default to TRUE when undefined) - sync across all tabs
        const showBorders = getCommon(l => l.show_panel_borders !== undefined ? l.show_panel_borders : true);
        const borderColorPixel = getCommon(l => l.border_color_pixel || l.border_color || '#ffffff');
        const borderColorCabinet = getCommon(l => l.border_color_cabinet || l.border_color || '#ffffff');
        const borderColorData = getCommon(l => l.border_color_data || l.border_color || '#ffffff');
        const borderColorPower = getCommon(l => l.border_color_power || l.border_color || '#ffffff');
        ['show-panel-borders', 'show-panel-borders-cabinet', 'show-panel-borders-data', 'show-panel-borders-power'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            if (showBorders.mixed) {
                el.indeterminate = true;
            } else {
                el.indeterminate = false;
                el.checked = !!showBorders.value;
            }
        });
        
        const setColorControl = (pickerId, hexId, common) => {
            const picker = document.getElementById(pickerId);
            const hex = document.getElementById(hexId);
            const value = common.value || '#ffffff';
            if (picker) picker.value = value;
            if (hex) {
                if (common.mixed) {
                    hex.value = '';
                    hex.placeholder = '—';
                } else {
                    hex.value = value.toUpperCase();
                    hex.placeholder = '';
                }
            }
        };
        setColorControl('border-color', 'border-color-hex', borderColorPixel);
        setColorControl('border-color-cabinet', 'border-color-cabinet-hex', borderColorCabinet);
        setColorControl('border-color-data', 'border-color-data-hex', borderColorData);
        setColorControl('border-color-power', 'border-color-power-hex', borderColorPower);
        
        // Border width is fixed at 2px - no input to load
        
        if (document.getElementById('show-circle-with-x')) {
            const common = getCommon(l => l.show_circle_with_x !== undefined ? l.show_circle_with_x : true);
            setCheckbox('show-circle-with-x', common);
        }
        
        // Load per-layer label settings (with proper defaults)
        const showLabelName = getCommon(l => l.showLabelName !== undefined ? l.showLabelName : true);
        setCheckbox('show-label-name', showLabelName);
        setCheckbox('show-label-size-px', getCommon(l => l.showLabelSizePx || false));
        setCheckbox('show-label-size-m', getCommon(l => l.showLabelSizeM || false));
        setCheckbox('show-label-size-ft', getCommon(l => l.showLabelSizeFt || false));
        setCheckbox('show-label-info', getCommon(l => l.showLabelInfo || false));
        setCheckbox('show-label-weight', getCommon(l => l.showLabelWeight || false));
        
        const labelsColor = primary.labelsColor || '#ffffff';
        document.getElementById('labels-color').value = labelsColor;
        if (document.getElementById('labels-color-hex')) {
            document.getElementById('labels-color-hex').value = labelsColor.toUpperCase();
        }
        setTextInput('labels-fontsize', getCommon(l => l.labelsFontSize || 30));
        const infoSizeCommon = getCommon(l => l.infoLabelSize || 14);
        const infoSizeInput = document.getElementById('info-label-size');
        const infoSizeValue = document.getElementById('info-label-size-value');
        if (infoSizeInput) {
            infoSizeInput.value = infoSizeCommon.mixed ? 14 : infoSizeCommon.value;
        }
        if (infoSizeValue) {
            infoSizeValue.textContent = `${infoSizeCommon.mixed ? 14 : infoSizeCommon.value}`;
        }
        setCheckbox('use-fractional-inches', getCommon(l => l.useFractionalInches || false));
        
        // Load per-layer offset settings
        setCheckbox('show-offset-tl', getCommon(l => l.showOffsetTL || false));
        setCheckbox('show-offset-tr', getCommon(l => l.showOffsetTR || false));
        setCheckbox('show-offset-bl', getCommon(l => l.showOffsetBL || false));
        setCheckbox('show-offset-br', getCommon(l => l.showOffsetBR || false));
        
        // Update Screen Name checkboxes on all tabs
        if (document.getElementById('show-label-name-cabinet')) {
            setCheckbox('show-label-name-cabinet', showLabelName);
        }
        if (document.getElementById('show-label-name-data')) {
            setCheckbox('show-label-name-data', showLabelName);
        }
        if (document.getElementById('show-label-name-power')) {
            setCheckbox('show-label-name-power', showLabelName);
        }
        
        // Load Data Flow settings - with hex fields
        const dataFlowColor = primary.dataFlowColor || '#FFFFFF';
        if (document.getElementById('data-flow-color')) {
            document.getElementById('data-flow-color').value = dataFlowColor;
        }
        if (document.getElementById('data-flow-color-hex')) {
            document.getElementById('data-flow-color-hex').value = dataFlowColor.toUpperCase();
        }
        
        const arrowColor = primary.arrowColor || '#0042AA';
        if (document.getElementById('arrow-color')) {
            document.getElementById('arrow-color').value = arrowColor;
        }
        if (document.getElementById('arrow-color-hex')) {
            document.getElementById('arrow-color-hex').value = arrowColor.toUpperCase();
        }
        
        const primaryColor = primary.primaryColor || '#00FF00';
        if (document.getElementById('primary-color')) {
            document.getElementById('primary-color').value = primaryColor;
        }
        if (document.getElementById('primary-color-hex')) {
            document.getElementById('primary-color-hex').value = primaryColor.toUpperCase();
        }
        const primaryTextColor = primary.primaryTextColor || '#000000';
        if (document.getElementById('primary-text-color')) {
            document.getElementById('primary-text-color').value = primaryTextColor;
        }
        if (document.getElementById('primary-text-color-hex')) {
            document.getElementById('primary-text-color-hex').value = primaryTextColor.toUpperCase();
        }
        
        const backupColor = primary.backupColor || '#FF0000';
        if (document.getElementById('backup-color')) {
            document.getElementById('backup-color').value = backupColor;
        }
        if (document.getElementById('backup-color-hex')) {
            document.getElementById('backup-color-hex').value = backupColor.toUpperCase();
        }
        const backupTextColor = primary.backupTextColor || '#FFFFFF';
        if (document.getElementById('backup-text-color')) {
            document.getElementById('backup-text-color').value = backupTextColor;
        }
        if (document.getElementById('backup-text-color-hex')) {
            document.getElementById('backup-text-color-hex').value = backupTextColor.toUpperCase();
        }

        refreshAllColorSwatches();
        
        setTextInput('arrow-line-width', getCommon(l => l.arrowLineWidth || 6));
        setTextInput('label-size', getCommon(l => l.dataFlowLabelSize || 30));
        setCheckbox('random-colors', getCommon(l => l.randomDataColors || false));
        if (document.getElementById('custom-flow-toggle')) {
            document.getElementById('custom-flow-toggle').checked = this.currentLayer.flowPattern === 'custom';
        }
        this.updateCustomFlowUI();
        if (document.getElementById('port-label-template-primary')) {
            document.getElementById('port-label-template-primary').value = this.currentLayer.portLabelTemplatePrimary || 'P#';
        }
        if (document.getElementById('port-label-template-return')) {
            document.getElementById('port-label-template-return').value = this.currentLayer.portLabelTemplateReturn || 'R#';
        }
        
        // Load processor type, bit depth and frame rate
        if (document.getElementById('processor-type')) {
            const prefs = this.getPreferences();
            document.getElementById('processor-type').value = this.currentLayer.processorType || prefs.processorType || 'novastar-armor';
            this.updateBitDepthOptions();
            this.updateFrameRateOptions();
        }
        if (document.getElementById('bit-depth')) {
            document.getElementById('bit-depth').value = this.currentLayer.bitDepth || this.getPreferences().bitDepth || 8;
        }
        if (document.getElementById('frame-rate')) {
            document.getElementById('frame-rate').value = this.currentLayer.frameRate || this.getPreferences().frameRate || 60;
        }
        
        // Load port mapping mode button states
        const mappingMode = this.currentLayer.portMappingMode || 'organized';
        const mappingOrgBtn = document.getElementById('mapping-organized');
        const mappingMaxBtn = document.getElementById('mapping-max-capacity');
        if (mappingOrgBtn && mappingMaxBtn) {
            if (mappingMode === 'organized') {
                mappingOrgBtn.style.background = '#4A90E2';
                mappingOrgBtn.style.color = '#fff';
                mappingMaxBtn.style.background = '#333';
                mappingMaxBtn.style.color = '#ccc';
            } else {
                mappingMaxBtn.style.background = '#4A90E2';
                mappingMaxBtn.style.color = '#fff';
                mappingOrgBtn.style.background = '#333';
                mappingOrgBtn.style.color = '#ccc';
            }
        }
        
        // Update port capacity display
        this.updatePortCapacityDisplay();
        this.updatePortLabelEditor();
        
        // Load flow pattern selection
        const flowPattern = this.currentLayer.flowPattern || 'tl-h';
        document.querySelectorAll('.flow-pattern-btn:not(.power-flow-pattern-btn)').forEach(btn => {
            btn.classList.remove('active');
            if (btn.getAttribute('data-pattern') === flowPattern) {
                btn.classList.add('active');
            }
        });

        // Load Power settings
        const powerVoltageSelect = document.getElementById('power-voltage-select');
        const powerVoltageCustomInput = document.getElementById('power-voltage-custom');
        const powerAmperageSelect = document.getElementById('power-amperage-select');
        const powerAmperageCustomInput = document.getElementById('power-amperage-custom');
        const powerPanelWattsInput = document.getElementById('power-panel-watts');
        const powerLineWidthInput = document.getElementById('power-line-width');
        const powerLabelSizeInput = document.getElementById('power-label-size');
        const powerMaximizeCheckbox = document.getElementById('power-maximize');
        const powerOrganizedCheckbox = document.getElementById('power-organized');
        const powerCustomToggle = document.getElementById('power-custom-toggle');
        const powerRandomColorsCheckbox = document.getElementById('power-random-colors');
        const powerColorCodedViewCheckbox = document.getElementById('power-color-coded-view');

        if (powerVoltageSelect && powerVoltageCustomInput) {
            const presets = ['110', '208', '220', '230', '240'];
            const currentVoltage = String(this.currentLayer.powerVoltage ?? 110);
            if (presets.includes(currentVoltage)) {
                powerVoltageSelect.value = currentVoltage;
                powerVoltageCustomInput.style.display = 'none';
            } else {
                powerVoltageSelect.value = 'custom';
                powerVoltageCustomInput.style.display = 'inline-block';
            }
            powerVoltageCustomInput.value = this.currentLayer.powerVoltageCustom ?? this.currentLayer.powerVoltage ?? 110;
        }
        if (powerAmperageSelect && powerAmperageCustomInput) {
            const presets = ['15', '20'];
            const currentAmp = String(this.currentLayer.powerAmperage ?? 15);
            if (presets.includes(currentAmp)) {
                powerAmperageSelect.value = currentAmp;
                powerAmperageCustomInput.style.display = 'none';
            } else {
                powerAmperageSelect.value = 'custom';
                powerAmperageCustomInput.style.display = 'inline-block';
            }
            powerAmperageCustomInput.value = this.currentLayer.powerAmperageCustom ?? this.currentLayer.powerAmperage ?? 15;
        }
        if (powerPanelWattsInput) {
            powerPanelWattsInput.value = this.currentLayer.panelWatts ?? 200;
        }
        if (powerLineWidthInput) {
            powerLineWidthInput.value = this.currentLayer.powerLineWidth ?? 8;
        }
        if (powerLabelSizeInput) {
            powerLabelSizeInput.value = this.currentLayer.powerLabelSize ?? 14;
        }
        if (powerMaximizeCheckbox) {
            powerMaximizeCheckbox.checked = !!this.currentLayer.powerMaximize;
        }
        if (powerOrganizedCheckbox) {
            powerOrganizedCheckbox.checked = this.currentLayer.powerOrganized !== false;
            if (powerMaximizeCheckbox && powerMaximizeCheckbox.checked) {
                powerOrganizedCheckbox.checked = false;
            }
        }
        if (powerCustomToggle) {
            powerCustomToggle.checked = this.currentLayer.powerFlowPattern === 'custom';
        }
        if (powerRandomColorsCheckbox) {
            powerRandomColorsCheckbox.checked = !!this.currentLayer.powerRandomColors;
        }
        if (powerColorCodedViewCheckbox) {
            powerColorCodedViewCheckbox.checked = !!this.currentLayer.powerColorCodedView;
        }
        const powerCircuitColorCustomInput = document.getElementById('power-circuit-color-custom');
        const powerCircuitColorCustomHexInput = document.getElementById('power-circuit-color-custom-hex');
        const powerCircuitColorPresetInput = document.getElementById('power-circuit-color-preset');
        if (powerCircuitColorCustomInput && powerCircuitColorCustomHexInput) {
            const defaultCircuitColors = this.normalizePowerCircuitColors(this.currentLayer.powerCircuitColors);
            const firstColor = defaultCircuitColors.A || '#FF0000';
            powerCircuitColorCustomInput.value = firstColor;
            powerCircuitColorCustomHexInput.value = firstColor.toUpperCase();
        }
        if (powerCircuitColorPresetInput) {
            powerCircuitColorPresetInput.value = 'custom';
        }
        const powerCircuitColorSection = document.getElementById('power-circuit-color-section');
        if (powerCircuitColorSection) {
            powerCircuitColorSection.style.display = this.currentLayer.powerColorCodedView ? 'block' : 'none';
        }
        this.updatePowerCircuitColorEditor();
        if (document.getElementById('power-label-template')) {
            document.getElementById('power-label-template').value = this.currentLayer.powerLabelTemplate || 'S1-#';
        }
        this.updatePowerLabelEditor();
        const showDataFlowPortInfoEl = document.getElementById('show-data-flow-port-info');
        if (showDataFlowPortInfoEl) {
            showDataFlowPortInfoEl.checked = !!this.currentLayer.showDataFlowPortInfo;
        }
        const showPowerCircuitInfoEl = document.getElementById('show-power-circuit-info');
        if (showPowerCircuitInfoEl) {
            showPowerCircuitInfoEl.checked = !!this.currentLayer.showPowerCircuitInfo;
        }
        if (document.getElementById('power-line-color')) {
            document.getElementById('power-line-color').value = this.currentLayer.powerLineColor || '#FF0000';
        }
        if (document.getElementById('power-line-color-hex')) {
            document.getElementById('power-line-color-hex').value = (this.currentLayer.powerLineColor || '#FF0000').toUpperCase();
        }
        if (document.getElementById('power-arrow-color')) {
            document.getElementById('power-arrow-color').value = this.currentLayer.powerArrowColor || '#0042AA';
        }
        if (document.getElementById('power-arrow-color-hex')) {
            document.getElementById('power-arrow-color-hex').value = (this.currentLayer.powerArrowColor || '#0042AA').toUpperCase();
        }
        if (document.getElementById('power-label-bg-color')) {
            document.getElementById('power-label-bg-color').value = this.currentLayer.powerLabelBgColor || '#D95000';
        }
        if (document.getElementById('power-label-bg-color-hex')) {
            document.getElementById('power-label-bg-color-hex').value = (this.currentLayer.powerLabelBgColor || '#D95000').toUpperCase();
        }
        if (document.getElementById('power-label-text-color')) {
            document.getElementById('power-label-text-color').value = this.currentLayer.powerLabelTextColor || '#000000';
        }
        if (document.getElementById('power-label-text-color-hex')) {
            document.getElementById('power-label-text-color-hex').value = (this.currentLayer.powerLabelTextColor || '#000000').toUpperCase();
        }

        document.querySelectorAll('.power-flow-pattern-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.getAttribute('data-pattern') === (this.currentLayer.powerFlowPattern || 'tl-h')) {
                btn.classList.add('active');
            }
        });
        this.updatePowerCapacityDisplay();
        this.updateCustomPowerUI();
        
        // Load tab-specific screen name sizes
        if (document.getElementById('screen-name-size')) {
            document.getElementById('screen-name-size').value = this.currentLayer.screenNameSizeDataFlow || 30;
        }
        if (document.getElementById('screen-name-size-cabinet')) {
            document.getElementById('screen-name-size-cabinet').value = this.currentLayer.screenNameSizeCabinet || 30;
        }
        if (document.getElementById('screen-name-size-power')) {
            document.getElementById('screen-name-size-power').value = this.currentLayer.screenNameSizePower || 30;
        }
        
        const normalizeColorObject = (value, fallbackHex) => {
            const fallback = this.hexToRgb(fallbackHex);
            if (!value) return fallback;
            if (typeof value === 'string') {
                const parsed = this.hexToRgb(value);
                return parsed || fallback;
            }
            const r = Number(value.r);
            const g = Number(value.g);
            const b = Number(value.b);
            if (Number.isFinite(r) && Number.isFinite(g) && Number.isFinite(b)) {
                return { r, g, b };
            }
            return fallback;
        };
        const c1 = normalizeColorObject(this.currentLayer.color1, '#404680');
        const c2 = normalizeColorObject(this.currentLayer.color2, '#959CB8');
        const hex1 = this.rgbToHex(c1.r, c1.g, c1.b);
        const hex2 = this.rgbToHex(c2.r, c2.g, c2.b);
        document.getElementById('color1-picker').value = hex1;
        document.getElementById('color2-picker').value = hex2;
        if (document.getElementById('color1-hex')) {
            document.getElementById('color1-hex').value = hex1.toUpperCase();
        }
        if (document.getElementById('color2-hex')) {
            document.getElementById('color2-hex').value = hex2.toUpperCase();
        }
    }

    updateLayerPanelVisibility(allImages) {
        const mode = window.canvasRenderer ? window.canvasRenderer.viewMode : 'pixel-map';
        const activeTab = mode === 'data-flow' ? 'data-flow' : mode;
        document.querySelectorAll('.tab-panel').forEach(panel => {
            if (panel.getAttribute('data-tab') !== activeTab) {
                panel.style.display = 'none';
                return;
            }
            if (activeTab === 'pixel-map') {
                if (panel.classList.contains('screen-only')) {
                    panel.style.display = allImages ? 'none' : 'block';
                    return;
                }
                if (panel.classList.contains('image-only')) {
                    panel.style.display = allImages ? 'block' : 'none';
                    return;
                }
                panel.style.display = 'block';
                return;
            }
            if (panel.classList.contains('screen-only')) {
                panel.style.display = allImages ? 'none' : 'block';
                return;
            }
            if (panel.classList.contains('image-only')) {
                panel.style.display = allImages ? 'block' : 'none';
                return;
            }
            panel.style.display = 'block';
        });
    }
    
    // Port capacity lookup tables from manufacturer specs
    // Keys are frame rates, values are pixel capacities
    portCapacityTables = {
        // NovaStar Armor (MSD/MRV) legacy 1G receiving cards
        // 8-bit uses 24x; 10/12-bit use 48x (max 120 Hz)
        'novastar-armor': {
            8:  { 24:1649306, 25:1583333, 30:1319444, 50:791667, 60:659722, 120:329861 },
            10: { 24:824653,  25:791667,  30:659722,  50:395833, 60:329861, 120:164931 },
            12: { 24:824653,  25:791667,  30:659722,  50:395833, 60:329861, 120:164931 }
        },
        // NovaStar COEX 1G (A10s/A8s Pro) receiving cards
        // 8-bit uses 24x; 10-bit uses 32x; 12-bit uses 48x
        'novastar-coex-1g': {
            8:  { 24:1649306, 25:1583333, 30:1319444, 50:791667, 60:659722, 120:329861, 144:274884, 240:164931 },
            10: { 24:1236979, 25:1187500, 30:989583,  50:593750, 60:494792, 120:247396, 144:206163, 240:123698 },
            12: { 24:824653,  25:791667,  30:659722,  50:395833, 60:329861, 120:164931, 144:137442, 240:82465 }
        },
        // NovaStar COEX 5G (CX40 Pro) receiving cards
        'novastar-5g': {
            8:  { 24:6480000, 25:6220800, 30:5184000, 50:3110400, 60:2592000, 120:1296000, 144:1080864, 240:648000 },
            10: { 24:5182500, 25:4975200, 30:4146000, 50:2487600, 60:2073000, 120:1036500, 144:864441,  240:518250 },
            12: { 24:4320000, 25:4147200, 30:3456000, 50:2073600, 60:1728000, 120:864000,  144:720576,  240:432000 }
        },
        'brompton': {
            8:  { 24:1312500, 25:1260000, 30:1050000, 48:656250, 50:630000, 60:525000, 72:437500, 100:315000, 120:262500, 144:218750, 150:210000, 180:175000, 192:164063, 200:157500, 240:131250, 250:126000 },
            10: { 24:1050000, 25:1008000, 30:840000,  48:525000, 50:504000, 60:420000, 72:350000, 100:252000, 120:210000, 144:175000, 150:168000, 180:140000, 192:131250, 200:126000, 240:105000, 250:100800 },
            12: { 24:875000,  25:840000,  30:700000,   48:437500, 50:420000, 60:350000, 72:291667, 100:210000, 120:175000, 144:145833, 150:140000, 180:116667, 192:109375, 200:105000, 240:87500,  250:84000 }
        },
        'brompton-ull': {
            8:  { 24:656250,  25:630000,  30:525000,  48:328125, 50:315000, 60:262500, 72:218750, 100:157500, 120:131250, 144:109375, 150:105000, 180:87500,  192:82031,  200:78750,  240:65625,  250:63000 },
            10: { 24:525000,  25:504000,  30:420000,  48:262500, 50:252000, 60:210000, 72:175000, 100:126000, 120:105000, 144:87500,  150:84000,  180:70000,  192:65625,  200:63000,  240:52500,  250:50400 },
            12: { 24:437500,  25:420000,  30:350000,  48:218750, 50:210000, 60:175000, 72:145833, 100:105000, 120:87500,  144:72917,  150:70000,  180:58333,  192:54688,  200:52500,  240:43750,  250:42000 }
        },
        'megapixel-1g': {
            10: { 24:1275000, 25:1225000, 30:1020000, 48:635000, 50:610000, 60:510000, 120:240000, 144:195000, 180:148000, 200:128000, 240:100000 },
            12: { 24:1062500, 25:1020000, 30:850000,  48:531000, 50:510000, 60:425000, 120:200000, 144:160000, 180:126000, 200:112000, 240:90000 }
        },
        'megapixel-2.5g': {
            10: { 24:3187500, 25:3062500, 30:2550000, 48:1587500, 50:1525000, 60:1275000, 120:600000, 144:487500, 180:370000, 200:320000, 240:250000 },
            12: { 24:2656250, 25:2550000, 30:2125000, 48:1328125, 50:1275000, 60:1062500, 120:500000, 144:400000, 180:315000, 200:280000, 240:225000 }
        }
    };
    
    // Get supported bit depths for a processor
    getSupportedBitDepths(processorType) {
        const table = this.portCapacityTables[processorType];
        if (!table) return [8, 10, 12];
        return Object.keys(table).map(Number).sort((a, b) => a - b);
    }
    
    // Get supported frame rates for a processor + bit depth
    getSupportedFrameRates(processorType, bitDepth) {
        const table = this.portCapacityTables[processorType];
        if (!table || !table[bitDepth]) return [];
        return Object.keys(table[bitDepth]).map(Number).sort((a, b) => a - b);
    }
    
    // Calculate port capacity using lookup tables with interpolation
    calculatePortCapacity(bitDepth, frameRate, processorType) {
        processorType = processorType || 'novastar-armor';
        const table = this.portCapacityTables[processorType];
        
        if (!table) return 0;
        
        // Find closest bit depth
        const availableBitDepths = Object.keys(table).map(Number);
        let useBitDepth = bitDepth;
        if (!table[bitDepth]) {
            // Find closest available bit depth (prefer higher for safety)
            useBitDepth = availableBitDepths.reduce((best, bd) => 
                Math.abs(bd - bitDepth) < Math.abs(best - bitDepth) ? bd : best
            );
        }
        
        const fpsTable = table[useBitDepth];
        if (!fpsTable) return 0;
        
        // Exact match
        const exactFps = Math.round(frameRate);
        if (fpsTable[exactFps]) return fpsTable[exactFps];
        
        // Interpolate between two closest frame rates
        const fpsList = Object.keys(fpsTable).map(Number).sort((a, b) => a - b);
        
        // Find surrounding entries
        let lower = fpsList[0];
        let upper = fpsList[fpsList.length - 1];
        
        for (let i = 0; i < fpsList.length - 1; i++) {
            if (fpsList[i] <= frameRate && fpsList[i + 1] >= frameRate) {
                lower = fpsList[i];
                upper = fpsList[i + 1];
                break;
            }
        }
        
        // If frame rate is below or above all entries, use the boundary
        if (frameRate <= fpsList[0]) return fpsTable[fpsList[0]];
        if (frameRate >= fpsList[fpsList.length - 1]) return fpsTable[fpsList[fpsList.length - 1]];
        
        // Linear interpolation
        const lowerCap = fpsTable[lower];
        const upperCap = fpsTable[upper];
        const ratio = (frameRate - lower) / (upper - lower);
        return Math.floor(lowerCap + (upperCap - lowerCap) * ratio);
    }
    
    // Check if processor uses rectangle-based port assignment (NovaStar Armor only)
    usesRectangleConstraint(processorType) {
        return processorType === 'novastar-armor';
    }
    
    // Update bit depth dropdown options based on selected processor
    updateBitDepthOptions() {
        const bitDepthSelect = document.getElementById('bit-depth');
        if (!bitDepthSelect || !this.currentLayer) return;
        
        const processorType = this.currentLayer.processorType || 'novastar-armor';
        const supported = this.getSupportedBitDepths(processorType);
        const currentBitDepth = this.currentLayer.bitDepth || 8;
        
        // Update options
        bitDepthSelect.innerHTML = '';
        supported.forEach(bd => {
            const opt = document.createElement('option');
            opt.value = bd;
            opt.textContent = `${bd}-bit`;
            bitDepthSelect.appendChild(opt);
        });
        
        // If current bit depth is still valid, keep it; otherwise pick the first
        if (supported.includes(currentBitDepth)) {
            bitDepthSelect.value = currentBitDepth;
        } else {
            bitDepthSelect.value = supported[0];
            this.currentLayer.bitDepth = supported[0];
        }
    }

    updateFrameRateOptions() {
        const frameRateSelect = document.getElementById('frame-rate');
        if (!frameRateSelect || !this.currentLayer) return;

        const processorType = this.currentLayer.processorType || 'novastar-armor';
        const currentFrameRate = this.currentLayer.frameRate || 60;

        const baseRates = [
            23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60, 72, 100, 120, 144, 150, 180, 192, 200, 240, 250
        ];

        const allowedRates = processorType === 'novastar-armor'
            ? baseRates.filter(rate => rate <= 120)
            : baseRates;

        frameRateSelect.innerHTML = '';
        allowedRates.forEach(rate => {
            const opt = document.createElement('option');
            opt.value = rate;
            opt.textContent = `${rate} Hz`;
            frameRateSelect.appendChild(opt);
        });

        if (allowedRates.includes(currentFrameRate)) {
            frameRateSelect.value = currentFrameRate;
        } else if (allowedRates.includes(60)) {
            frameRateSelect.value = 60;
            this.currentLayer.frameRate = 60;
        } else {
            frameRateSelect.value = allowedRates[0];
            this.currentLayer.frameRate = allowedRates[0];
        }
    }
    
    // Calculate port assignments for panels
    calculatePortAssignments(layer) {
        if (!layer || !Array.isArray(layer.panels)) return [];

        const bitDepth = layer.bitDepth || 8;
        const frameRate = layer.frameRate || 60;
        const processorType = layer.processorType || 'novastar-armor';
        const mappingMode = layer.portMappingMode || 'organized';
        const portCapacity = this.calculatePortCapacity(bitDepth, frameRate, processorType);
        const pattern = layer.flowPattern || 'tl-h';
        const usesRectangle = this.usesRectangleConstraint(processorType);
        const isOrganized = usesRectangle ? true : (mappingMode === 'organized');
        const isHorizontalFirst = pattern.includes('-h');
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');
        const fullPanelPixels = this.getFullPanelPixels(layer);

        layer._capacityError = null;
        layer._autoPortsRequired = 0;
        if (portCapacity <= 0 || fullPanelPixels <= 0) return [];

        const orderedForCapacity = this.getOrderedPanelsByPattern(layer, pattern, usesRectangle);
        if (orderedForCapacity.length === 0) return [];

        const ports = [];

        if (isOrganized) {
            const unitIndices = isHorizontalFirst
                ? [...Array(layer.rows).keys()].map(i => (startsTop ? i : (layer.rows - 1 - i)))
                : [...Array(layer.columns).keys()].map(i => (startsLeft ? i : (layer.columns - 1 - i)));

            let current = { unitIndices: [], load: 0 };

            unitIndices.forEach(unitIdx => {
                const unitPanelsAll = orderedForCapacity.filter(p => (isHorizontalFirst ? p.row === unitIdx : p.col === unitIdx));
                const unitLoad = unitPanelsAll.reduce((sum, p) => sum + this.getPanelPixelArea(p), 0);
                if (unitLoad <= 0) return;
                if (unitLoad > portCapacity) {
                    layer._capacityError = {
                        isHorizontalFirst,
                        cols: layer.columns,
                        rows: layer.rows,
                        panelsPerPort: Math.floor(portCapacity / fullPanelPixels),
                        portCapacity,
                        panelPixels: fullPanelPixels,
                        unitType: isHorizontalFirst ? 'row' : 'column',
                        unitCount: isHorizontalFirst ? layer.columns : layer.rows
                    };
                    return;
                }
                if (current.load > 0 && current.load + unitLoad > portCapacity) {
                    ports.push(current);
                    current = { unitIndices: [], load: 0 };
                }
                current.unitIndices.push(unitIdx);
                current.load += unitLoad;
            });

            if (layer._capacityError) return [];
            if (current.load > 0 || current.unitIndices.length > 0) ports.push(current);
        } else {
            let current = { panels: [], load: 0 };
            orderedForCapacity.forEach(panel => {
                const panelLoad = this.getPanelPixelArea(panel);
                if (panelLoad <= 0) return;
                if (current.load > 0 && current.load + panelLoad > portCapacity) {
                    ports.push(current);
                    current = { panels: [], load: 0 };
                }
                if (!panel.hidden) current.panels.push(panel);
                current.load += panelLoad;
            });
            if (current.load > 0 || current.panels.length > 0) ports.push(current);
        }

        const assignments = [];
        layer._autoPortsRequired = ports.length;
        ports.forEach((port, idx) => {
            const portPanels = isOrganized
                ? this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, port.unitIndices || [], false)
                : (port.panels || []);
            let pixelIndex = 0;
            portPanels.forEach((panel, panelIdx) => {
                assignments.push({
                    panel,
                    port: idx + 1,
                    isPortStart: panelIdx === 0,
                    pixelIndex
                });
                pixelIndex += this.getPanelPixelArea(panel);
            });
        });
        return assignments;
    }
    
    // Update export filename preview
    updateExportPreview() {
        const projectName = document.getElementById('export-name').value.trim() || 'Project';
        const format = document.getElementById('export-format').value;
        
        const viewNames = this.getExportViewNames();
        const suffixes = this.getExportSuffixesFromUI();
        
        const views = [];
        if (document.getElementById('export-pixel-map').checked) views.push('pixel-map');
        if (document.getElementById('export-cabinet-id').checked) views.push('cabinet-id');
        if (document.getElementById('export-data-flow').checked) views.push('data-flow');
        if (document.getElementById('export-power').checked) views.push('power');
        
        const preview = document.getElementById('export-preview');
        
        if (views.length === 0) {
            preview.textContent = '(Select at least one view)';
            preview.style.color = '#ff6b6b';
            return;
        }
        
        preview.style.color = '#4A90E2';
        
        if (format === 'pdf') {
            // PDF combines all views
            preview.textContent = `${projectName}.pdf (${views.length} page${views.length > 1 ? 's' : ''})`;
        } else if (format === 'psd') {
            // PSD - one file per view, layers inside
            if (views.length === 1) {
                const suffix = this.getExportSuffixForView(views[0], suffixes, viewNames);
                preview.textContent = `${projectName} ${suffix}.psd`;
            } else {
                preview.innerHTML = views.map(v => {
                    const suffix = this.getExportSuffixForView(v, suffixes, viewNames);
                    return `${projectName} ${suffix}.psd`;
                }).join('<br>');
            }
        } else {
            // PNG - one file per view
            if (views.length === 1) {
                const suffix = this.getExportSuffixForView(views[0], suffixes, viewNames);
                preview.textContent = `${projectName} ${suffix}.png`;
            } else {
                preview.innerHTML = views.map(v => {
                    const suffix = this.getExportSuffixForView(v, suffixes, viewNames);
                    return `${projectName} ${suffix}.png`;
                }).join('<br>');
            }
        }
    }

    getExportViewNames() {
        return {
            'pixel-map': 'Pixel Map',
            'cabinet-id': 'Cabinet Map',
            'data-flow': 'Data Map',
            'power': 'Power Map'
        };
    }

    getExportSuffixDefaults() {
        return {
            'pixel-map': 'Pixel Map',
            'cabinet-id': 'Cabinet Map',
            'data-flow': 'Data Map',
            'power': 'Power Map'
        };
    }

    loadExportSuffixesToUI() {
        const defaults = this.getExportSuffixDefaults();
        let saved = {};
        try {
            saved = JSON.parse(localStorage.getItem('exportSuffixes') || '{}');
        } catch (e) {
            saved = {};
        }
        const apply = (id, key) => {
            const el = document.getElementById(id);
            if (!el) return;
            const val = typeof saved[key] === 'string' ? saved[key] : defaults[key];
            el.value = val || '';
        };
        apply('export-suffix-pixel-map', 'pixel-map');
        apply('export-suffix-cabinet-id', 'cabinet-id');
        apply('export-suffix-data-flow', 'data-flow');
        apply('export-suffix-power', 'power');
    }

    saveExportSuffixesFromUI() {
        const suffixes = this.getExportSuffixesFromUI();
        localStorage.setItem('exportSuffixes', JSON.stringify(suffixes));
    }

    getExportSuffixesFromUI() {
        const defaults = this.getExportSuffixDefaults();
        const read = (id, key) => {
            const el = document.getElementById(id);
            if (!el) return defaults[key];
            return (el.value || '').trim();
        };
        return {
            'pixel-map': read('export-suffix-pixel-map', 'pixel-map'),
            'cabinet-id': read('export-suffix-cabinet-id', 'cabinet-id'),
            'data-flow': read('export-suffix-data-flow', 'data-flow'),
            'power': read('export-suffix-power', 'power')
        };
    }

    getExportSuffixForView(view, suffixes, viewNames) {
        const raw = (suffixes && typeof suffixes[view] === 'string') ? suffixes[view].trim() : '';
        return raw || viewNames[view];
    }
    
    // Perform export using client-side canvas capture at 1:1 pixel scale
    async performExport(projectName, format, views) {
        const viewNames = this.getExportViewNames();
        const suffixes = this.getExportSuffixesFromUI();
        
        // Store current state
        const originalViewMode = window.canvasRenderer.viewMode;
        const originalZoom = window.canvasRenderer.zoom;
        const originalPanX = window.canvasRenderer.panX;
        const originalPanY = window.canvasRenderer.panY;
        
        // Get exact raster dimensions
        const rasterWidth = window.canvasRenderer.rasterWidth;
        const rasterHeight = window.canvasRenderer.rasterHeight;
        
        // Store original canvas reference
        const mainCanvas = window.canvasRenderer.canvas;
        const originalCtx = window.canvasRenderer.ctx;
        
        // Create a fresh offscreen canvas at exact raster size
        const exportCanvas = document.createElement('canvas');
        exportCanvas.width = rasterWidth;
        exportCanvas.height = rasterHeight;
        const exportCtx = exportCanvas.getContext('2d', { alpha: false });
        
        // Swap to export canvas
        window.canvasRenderer.canvas = exportCanvas;
        window.canvasRenderer.ctx = exportCtx;
        
        // Set zoom to exactly 1.0 and pan to 0,0 (top-left corner)
        window.canvasRenderer.zoom = 1.0;
        window.canvasRenderer.panX = 0;
        window.canvasRenderer.panY = 0;
        
        // Enable export mode (hides grid and raster boundary)
        window.canvasRenderer.exportMode = true;
        
        // Render each view and collect images
        const renderedViews = [];
        
        for (const view of views) {
            // Set view mode
            window.canvasRenderer.viewMode = view;
            
            // Render at 1:1 to the export canvas
            window.canvasRenderer.render();
            
            // Log dimensions for debugging
            console.log(`Export: ${view} - Canvas: ${exportCanvas.width}x${exportCanvas.height}, Raster: ${rasterWidth}x${rasterHeight}`);
            
            // Get image data directly from canvas
            const dataUrl = exportCanvas.toDataURL('image/png');
            const suffix = this.getExportSuffixForView(view, suffixes, viewNames);
            renderedViews.push({
                view,
                suffix,
                fileBase: `${projectName} ${suffix}`,
                dataUrl,
                width: rasterWidth,
                height: rasterHeight
            });
        }
        
        // Restore original canvas and context
        window.canvasRenderer.canvas = mainCanvas;
        window.canvasRenderer.ctx = originalCtx;
        window.canvasRenderer.exportMode = false;
        window.canvasRenderer.viewMode = originalViewMode;
        window.canvasRenderer.zoom = originalZoom;
        window.canvasRenderer.panX = originalPanX;
        window.canvasRenderer.panY = originalPanY;
        window.canvasRenderer.render();
        
        // Handle the export based on format
        if (format === 'png') {
            await this.downloadRenderedPNGs(renderedViews);
        } else if (format === 'pdf') {
            // Send to server to create PDF
            await this.downloadAsPdf(projectName, renderedViews);
        } else if (format === 'psd') {
            await this.downloadAsPsd(projectName, renderedViews);
        }
    }
    
    dataUrlToBlob(dataUrl) {
        const [meta, base64] = dataUrl.split(',');
        const contentType = meta.split(':')[1].split(';')[0];
        const byteCharacters = atob(base64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        return new Blob([new Uint8Array(byteNumbers)], { type: contentType });
    }

    downloadBlob(blob, filename) {
        const link = document.createElement('a');
        link.download = filename;
        link.href = URL.createObjectURL(blob);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    blobToDataUrl(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = (e) => reject(e);
            reader.readAsDataURL(blob);
        });
    }

    async nativeSelectSavePath(suggestedName) {
        const response = await fetch('/api/native-dialog/save-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ suggested_name: suggestedName })
        });
        if (!response.ok) return null;
        const data = await response.json();
        if (!data || !data.ok || !data.path) return null;
        return data.path;
    }

    async nativeSelectDirectory() {
        const response = await fetch('/api/native-dialog/select-directory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        if (!response.ok) return null;
        const data = await response.json();
        if (!data || !data.ok || !data.path) return null;
        return data.path;
    }

    async nativeWriteFile(path, blob) {
        const dataUrl = await this.blobToDataUrl(blob);
        const response = await fetch('/api/native-dialog/write-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, data_url: dataUrl })
        });
        if (!response.ok) return false;
        const data = await response.json();
        return !!(data && data.ok);
    }

    async saveBlobWithPicker(blob, filename, mimeType) {
        if (window.showSaveFilePicker) {
            try {
                sendClientLog('save_blob_picker_start', { filename, mimeType });
                const ext = filename.split('.').pop() || '';
                const handle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{ description: 'File', accept: { [mimeType]: [`.${ext}`] } }]
                });
                const writable = await handle.createWritable();
                await writable.write(blob);
                await writable.close();
                sendClientLog('save_blob_picker_success', { filename });
                return;
            } catch (err) {
                if (err && err.name === 'AbortError') return;
                throw err;
            }
        }
        try {
            const savePath = await this.nativeSelectSavePath(filename);
            if (!savePath) {
                sendClientLog('save_blob_native_dialog_cancelled', { filename });
                return;
            }
            sendClientLog('save_blob_native_dialog_selected', { filename, savePath });
            const ok = await this.nativeWriteFile(savePath, blob);
            if (ok) {
                sendClientLog('save_blob_native_dialog_success', { filename, savePath });
                return;
            }
            sendClientLog('save_blob_native_dialog_write_failed', { filename, savePath });
            return;
        } catch (err) {
            sendClientLog('save_blob_native_dialog_error', { filename, message: err.message });
            return;
        }
    }

    async saveMultipleFiles(files) {
        sendClientLog('save_multiple_files_start', {
            count: files.length,
            hasDirectoryPicker: !!window.showDirectoryPicker,
            hasSaveFilePicker: !!window.showSaveFilePicker
        });
        if (window.showDirectoryPicker) {
            try {
                const dirHandle = await window.showDirectoryPicker();
                for (const file of files) {
                    const handle = await dirHandle.getFileHandle(file.filename, { create: true });
                    const writable = await handle.createWritable();
                    await writable.write(file.blob);
                    await writable.close();
                }
                sendClientLog('save_multiple_files_directory_success', { count: files.length });
                return;
            } catch (err) {
                if (err && err.name === 'AbortError') return;
                throw err;
            }
        }
        if (window.showSaveFilePicker) {
            for (const file of files) {
                const mimeType = file.blob && file.blob.type ? file.blob.type : 'application/octet-stream';
                await this.saveBlobWithPicker(file.blob, file.filename, mimeType);
            }
            sendClientLog('save_multiple_files_picker_success', { count: files.length });
            return;
        }
        try {
            const targetDir = await this.nativeSelectDirectory();
            if (!targetDir) {
                sendClientLog('save_multiple_files_native_dialog_cancelled', { count: files.length });
                return;
            }
            for (const file of files) {
                const filePath = `${targetDir.replace(/[\\/]$/, '')}/${file.filename}`;
                const ok = await this.nativeWriteFile(filePath, file.blob);
                if (!ok) {
                    sendClientLog('save_multiple_files_native_dialog_write_failed', { file: file.filename, filePath });
                    throw new Error(`Native write failed for ${file.filename}`);
                }
            }
            sendClientLog('save_multiple_files_native_dialog_success', { count: files.length, directory: targetDir });
            return;
        } catch (err) {
            sendClientLog('save_multiple_files_native_dialog_error', { message: err.message });
            return;
        }
    }

    async downloadRenderedPNGs(renderedViews) {
        if (renderedViews.length === 1) {
            const blob = this.dataUrlToBlob(renderedViews[0].dataUrl);
            await this.saveBlobWithPicker(blob, `${renderedViews[0].fileBase}.png`, 'image/png');
            return;
        }
        const files = renderedViews.map(v => ({
            filename: `${v.fileBase}.png`,
            blob: this.dataUrlToBlob(v.dataUrl)
        }));
        await this.saveMultipleFiles(files);
    }
    
    async downloadAsPdf(projectName, renderedViews) {
        const response = await fetch('/api/export/pdf-from-images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                images: renderedViews.map(v => ({
                    name: v.suffix,
                    data: v.dataUrl,
                    width: v.width || window.canvasRenderer.rasterWidth,
                    height: v.height || window.canvasRenderer.rasterHeight
                })),
                width: window.canvasRenderer.rasterWidth,
                height: window.canvasRenderer.rasterHeight
            })
        });
        
        if (!response.ok) throw new Error('Failed to create PDF');
        
        const blob = await response.blob();
        await this.saveBlobWithPicker(blob, `${projectName}.pdf`, 'application/pdf');
    }
    
    async downloadAsPsd(projectName, renderedViews) {
        const files = [];
        for (const view of renderedViews) {
            const response = await fetch('/api/export/psd-from-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_name: projectName,
                    view_name: view.suffix,
                    image_data: view.dataUrl,
                    width: view.width || window.canvasRenderer.rasterWidth,
                    height: view.height || window.canvasRenderer.rasterHeight,
                    layers: this.project.layers.map(l => {
                        const b = this.getLayerBounds(l);
                        return {
                            name: l.name,
                            offset_x: b.x1,
                            offset_y: b.y1,
                            width: b.x2 - b.x1,
                            height: b.y2 - b.y1,
                            visible: l.visible
                        };
                    })
                })
            });
            if (!response.ok) throw new Error('Failed to create PSD');
            const blob = await response.blob();
            files.push({ filename: `${view.fileBase}.psd`, blob });
        }
        if (files.length === 1) {
            await this.saveBlobWithPicker(files[0].blob, files[0].filename, 'application/octet-stream');
            return;
        }
        await this.saveMultipleFiles(files);
    }

    getPreferencesDefaults() {
        return {
            rasterWidth: 1920,
            rasterHeight: 1080,
            columns: 8,
            rows: 5,
            panelWidth: 128,
            panelHeight: 128,
            panelWidthMM: 500,
            panelHeightMM: 500,
            panelWeight: 20,
            weightUnit: 'kg',
            cabinetFontSize: 30,
            labelFontSize: 30,
            dataLabelSize: 30,
            powerLabelSize: 14,
            color1: '#404680',
            color2: '#959CB8',
            borderColor: '#FFFFFF',
            flowPattern: 'tl-h',
            powerFlowPattern: 'tl-h',
            dataLineWidth: 6,
            powerLineWidth: 8,
            processorType: 'novastar-armor',
            bitDepth: 8,
            frameRate: 60,
            powerVoltage: 110,
            powerAmperage: 15,
            powerWatts: 200
        };
    }

    getPreferences() {
        const defaults = this.getPreferencesDefaults();
        let saved = {};
        try {
            saved = JSON.parse(localStorage.getItem('appPreferences') || '{}');
        } catch (e) {
            saved = {};
        }
        return { ...defaults, ...saved };
    }

    supportsFilePickerAPIs() {
        return !!window.showSaveFilePicker;
    }

    supportsDirectoryPickerAPIs() {
        return !!window.showDirectoryPicker;
    }

    getFlowPatternSvg(pattern) {
        const svgs = {
            'tl-h': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="4" cy="4" r="3" fill="#00cc00"/><path d="M 4 4 L 28 4 L 28 16 L 4 16 L 4 28 L 22 28" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="28,28 22,24 22,32" fill="#cc0000"/></svg>',
            'tl-v': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="4" cy="4" r="3" fill="#00cc00"/><path d="M 4 4 L 4 28 L 16 28 L 16 4 L 28 4 L 28 22" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="28,28 24,22 32,22" fill="#cc0000"/></svg>',
            'tr-h': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="28" cy="4" r="3" fill="#00cc00"/><path d="M 28 4 L 4 4 L 4 16 L 28 16 L 28 28 L 10 28" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="4,28 10,24 10,32" fill="#cc0000"/></svg>',
            'tr-v': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="28" cy="4" r="3" fill="#00cc00"/><path d="M 28 4 L 28 28 L 16 28 L 16 4 L 4 4 L 4 22" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="4,28 0,22 8,22" fill="#cc0000"/></svg>',
            'bl-h': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="4" cy="28" r="3" fill="#00cc00"/><path d="M 4 28 L 28 28 L 28 16 L 4 16 L 4 4 L 22 4" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="28,4 22,0 22,8" fill="#cc0000"/></svg>',
            'bl-v': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="4" cy="28" r="3" fill="#00cc00"/><path d="M 4 28 L 4 4 L 16 4 L 16 28 L 28 28 L 28 10" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="28,4 24,10 32,10" fill="#cc0000"/></svg>',
            'br-h': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="28" cy="28" r="3" fill="#00cc00"/><path d="M 28 28 L 4 28 L 4 16 L 28 16 L 28 4 L 10 4" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="4,4 10,0 10,8" fill="#cc0000"/></svg>',
            'br-v': '<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="28" cy="28" r="3" fill="#00cc00"/><path d="M 28 28 L 28 4 L 16 4 L 16 28 L 4 28 L 4 10" stroke="#888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><polygon points="4,4 0,10 8,10" fill="#cc0000"/></svg>'
        };
        return svgs[pattern] || svgs['tl-h'];
    }

    renderPreferencePatternButtons(containerId, buttonClass) {
        const container = document.getElementById(containerId);
        if (!container) return;
        if (container.children.length > 0) return;
        const patterns = ['tl-h', 'tl-v', 'tr-h', 'tr-v', 'bl-h', 'bl-v', 'br-h', 'br-v'];
        patterns.forEach(pattern => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `pref-flow-pattern-btn ${buttonClass}`;
            btn.setAttribute('data-pattern', pattern);
            btn.innerHTML = this.getFlowPatternSvg(pattern);
            container.appendChild(btn);
        });
    }

    setupPreferences() {
        this.renderPreferencePatternButtons('pref-data-flow-pattern-grid', 'pref-data-flow-pattern-btn');
        this.renderPreferencePatternButtons('pref-power-flow-pattern-grid', 'pref-power-flow-pattern-btn');
        const saveBtn = document.getElementById('preferences-save');
        const cancelBtn = document.getElementById('preferences-cancel');
        const resetBtn = document.getElementById('preferences-reset');
        const modal = document.getElementById('preferences-modal');
        const modalContent = modal ? modal.querySelector('.modal-content') : null;
        const voltageSelect = document.getElementById('pref-power-voltage-select');
        const voltageCustom = document.getElementById('pref-power-voltage-custom');
        const amperageSelect = document.getElementById('pref-power-amperage-select');
        const amperageCustom = document.getElementById('pref-power-amperage-custom');
        const prefDataPatternButtons = document.querySelectorAll('.pref-data-flow-pattern-btn');
        const prefPowerPatternButtons = document.querySelectorAll('.pref-power-flow-pattern-btn');
        let prefsBackdropDown = false;

        const syncVoltageCustom = () => {
            if (!voltageSelect || !voltageCustom) return;
            if (voltageSelect.value === 'custom') {
                voltageCustom.style.display = 'inline-block';
            } else {
                voltageCustom.style.display = 'none';
                voltageCustom.value = voltageSelect.value;
            }
        };
        const syncAmperageCustom = () => {
            if (!amperageSelect || !amperageCustom) return;
            if (amperageSelect.value === 'custom') {
                amperageCustom.style.display = 'inline-block';
            } else {
                amperageCustom.style.display = 'none';
                amperageCustom.value = amperageSelect.value;
            }
        };

        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                const prefs = this.readPreferencesFromUI();
                localStorage.setItem('appPreferences', JSON.stringify(prefs));
                sendClientLog('preferences_saved', {
                    projectName: this.project ? this.project.name : null,
                    layers: this.project && this.project.layers ? this.project.layers.length : 0,
                    appliesToCurrentProject: !!(this.project && this.project.name === 'Untitled Project' && this.project.layers && this.project.layers.length === 1)
                });
                // Preferences are defaults for future/new projects.
                // Only apply to the current project when it is the startup default untitled project.
                this.applyPreferencesToDefaultLayerIfMatch(false);
                this.saveClientSideProperties();
                modal.style.display = 'none';
            });
        }
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                modal.style.display = 'none';
            });
        }
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                const defaults = this.getPreferencesDefaults();
                localStorage.setItem('appPreferences', JSON.stringify(defaults));
                sendClientLog('preferences_reset', {
                    projectName: this.project ? this.project.name : null,
                    layers: this.project && this.project.layers ? this.project.layers.length : 0,
                    appliesToCurrentProject: !!(this.project && this.project.name === 'Untitled Project' && this.project.layers && this.project.layers.length === 1)
                });
                this.openPreferencesModal();
                this.applyPreferencesToDefaultLayerIfMatch(false);
            });
        }
        if (modal) {
            modal.addEventListener('mousedown', (e) => {
                prefsBackdropDown = (e.target === modal);
            });
            modal.addEventListener('click', (e) => {
                if (e.target === modal && prefsBackdropDown) {
                    modal.style.display = 'none';
                }
                prefsBackdropDown = false;
            });
        }
        if (modalContent) {
            modalContent.addEventListener('mousedown', () => {
                prefsBackdropDown = false;
            });
            modalContent.addEventListener('click', (e) => e.stopPropagation());
        }
        if (voltageSelect) {
            voltageSelect.addEventListener('change', syncVoltageCustom);
        }
        if (amperageSelect) {
            amperageSelect.addEventListener('change', syncAmperageCustom);
        }
        prefDataPatternButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                prefDataPatternButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
        prefPowerPatternButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                prefPowerPatternButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
        syncVoltageCustom();
        syncAmperageCustom();
    }

    openPreferencesModal() {
        const prefs = this.getPreferences();
        const setVal = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.value = value;
        };
        setVal('pref-raster-width', prefs.rasterWidth);
        setVal('pref-raster-height', prefs.rasterHeight);
        setVal('pref-columns', prefs.columns);
        setVal('pref-rows', prefs.rows);
        setVal('pref-panel-width', prefs.panelWidth);
        setVal('pref-panel-height', prefs.panelHeight);
        setVal('pref-panel-width-mm', prefs.panelWidthMM);
        setVal('pref-panel-height-mm', prefs.panelHeightMM);
        setVal('pref-panel-weight', prefs.panelWeight);
        setVal('pref-weight-unit', prefs.weightUnit || 'kg');
        setVal('pref-cabinet-font-size', prefs.cabinetFontSize);
        setVal('pref-label-font-size', prefs.labelFontSize);
        setVal('pref-data-label-size', prefs.dataLabelSize);
        setVal('pref-power-label-size', prefs.powerLabelSize);
        setVal('pref-color1', prefs.color1);
        setVal('pref-color2', prefs.color2);
        setVal('pref-border-color', prefs.borderColor);
        const prefDataPatternButtons = document.querySelectorAll('.pref-data-flow-pattern-btn');
        prefDataPatternButtons.forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-pattern') === (prefs.flowPattern || 'tl-h'));
        });
        const prefPowerPatternButtons = document.querySelectorAll('.pref-power-flow-pattern-btn');
        prefPowerPatternButtons.forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-pattern') === (prefs.powerFlowPattern || 'tl-h'));
        });
        setVal('pref-data-line-width', prefs.dataLineWidth);
        setVal('pref-power-line-width', prefs.powerLineWidth);
        setVal('pref-processor-type', prefs.processorType);
        setVal('pref-bit-depth', prefs.bitDepth);
        setVal('pref-frame-rate', prefs.frameRate);
        const voltageSelect = document.getElementById('pref-power-voltage-select');
        const voltageCustom = document.getElementById('pref-power-voltage-custom');
        const amperageSelect = document.getElementById('pref-power-amperage-select');
        const amperageCustom = document.getElementById('pref-power-amperage-custom');
        if (voltageSelect) {
            const val = String(prefs.powerVoltage);
            const option = [...voltageSelect.options].find(o => o.value === val);
            voltageSelect.value = option ? val : 'custom';
        }
        if (voltageCustom) {
            voltageCustom.value = prefs.powerVoltage;
            voltageCustom.style.display = (!voltageSelect || voltageSelect.value === 'custom') ? 'inline-block' : 'none';
        }
        if (amperageSelect) {
            const val = String(prefs.powerAmperage);
            const option = [...amperageSelect.options].find(o => o.value === val);
            amperageSelect.value = option ? val : 'custom';
        }
        if (amperageCustom) {
            amperageCustom.value = prefs.powerAmperage;
            amperageCustom.style.display = (!amperageSelect || amperageSelect.value === 'custom') ? 'inline-block' : 'none';
        }
        setVal('pref-power-watts', prefs.powerWatts);
        const modal = document.getElementById('preferences-modal');
        if (modal) modal.style.display = 'block';
    }

    readPreferencesFromUI() {
        const defaults = this.getPreferencesDefaults();
        const readNum = (id, fallback) => {
            const el = document.getElementById(id);
            if (!el) return fallback;
            const val = parseInt(el.value, 10);
            return Number.isFinite(val) && val > 0 ? val : fallback;
        };
        const readStr = (id, fallback) => {
            const el = document.getElementById(id);
            return el && el.value ? el.value : fallback;
        };
        const voltageSelect = document.getElementById('pref-power-voltage-select');
        const amperageSelect = document.getElementById('pref-power-amperage-select');
        const prefDataPatternActive = document.querySelector('.pref-data-flow-pattern-btn.active');
        const prefPowerPatternActive = document.querySelector('.pref-power-flow-pattern-btn.active');
        const voltageVal = voltageSelect && voltageSelect.value !== 'custom'
            ? parseInt(voltageSelect.value, 10)
            : readNum('pref-power-voltage-custom', defaults.powerVoltage);
        const amperageVal = amperageSelect && amperageSelect.value !== 'custom'
            ? parseInt(amperageSelect.value, 10)
            : readNum('pref-power-amperage-custom', defaults.powerAmperage);
        return {
            rasterWidth: readNum('pref-raster-width', defaults.rasterWidth),
            rasterHeight: readNum('pref-raster-height', defaults.rasterHeight),
            columns: readNum('pref-columns', defaults.columns),
            rows: readNum('pref-rows', defaults.rows),
            panelWidth: readNum('pref-panel-width', defaults.panelWidth),
            panelHeight: readNum('pref-panel-height', defaults.panelHeight),
            panelWidthMM: readNum('pref-panel-width-mm', defaults.panelWidthMM),
            panelHeightMM: readNum('pref-panel-height-mm', defaults.panelHeightMM),
            panelWeight: readNum('pref-panel-weight', defaults.panelWeight),
            weightUnit: readStr('pref-weight-unit', defaults.weightUnit),
            cabinetFontSize: readNum('pref-cabinet-font-size', defaults.cabinetFontSize),
            labelFontSize: readNum('pref-label-font-size', defaults.labelFontSize),
            dataLabelSize: readNum('pref-data-label-size', defaults.dataLabelSize),
            powerLabelSize: readNum('pref-power-label-size', defaults.powerLabelSize),
            color1: readStr('pref-color1', defaults.color1),
            color2: readStr('pref-color2', defaults.color2),
            borderColor: readStr('pref-border-color', defaults.borderColor),
            flowPattern: prefDataPatternActive ? (prefDataPatternActive.getAttribute('data-pattern') || defaults.flowPattern) : defaults.flowPattern,
            powerFlowPattern: prefPowerPatternActive ? (prefPowerPatternActive.getAttribute('data-pattern') || defaults.powerFlowPattern) : defaults.powerFlowPattern,
            dataLineWidth: readNum('pref-data-line-width', defaults.dataLineWidth),
            powerLineWidth: readNum('pref-power-line-width', defaults.powerLineWidth),
            processorType: readStr('pref-processor-type', defaults.processorType),
            bitDepth: readNum('pref-bit-depth', defaults.bitDepth),
            frameRate: readNum('pref-frame-rate', defaults.frameRate),
            powerVoltage: Number.isFinite(voltageVal) && voltageVal > 0 ? voltageVal : defaults.powerVoltage,
            powerAmperage: Number.isFinite(amperageVal) && amperageVal > 0 ? amperageVal : defaults.powerAmperage,
            powerWatts: readNum('pref-power-watts', defaults.powerWatts)
        };
    }

    applyPreferencesToRaster(prefs) {
        if (!window.canvasRenderer) return;
        window.canvasRenderer.rasterWidth = prefs.rasterWidth;
        window.canvasRenderer.rasterHeight = prefs.rasterHeight;
        const widthInput = document.getElementById('toolbar-raster-width');
        const heightInput = document.getElementById('toolbar-raster-height');
        if (widthInput) widthInput.value = prefs.rasterWidth;
        if (heightInput) heightInput.value = prefs.rasterHeight;
        if (this.project) {
            this.project.raster_width = prefs.rasterWidth;
            this.project.raster_height = prefs.rasterHeight;
            this.saveProject();
        }
        this.saveRasterSize();
        window.canvasRenderer.render();
    }

    setupMenuBar() {
        const menuItems = document.querySelectorAll('#menu-bar .menu-item');
        const menus = document.querySelectorAll('.menu-dropdown');
        const hideMenus = () => {
            menus.forEach(menu => menu.style.display = 'none');
            menuItems.forEach(item => item.classList.remove('active'));
        };

        this.updateShortcutLabels();

        menuItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                const menuId = `menu-${item.dataset.menu}`;
                const menu = document.getElementById(menuId);
                if (!menu) return;
                const rect = item.getBoundingClientRect();
                const isVisible = menu.style.display === 'block';
                hideMenus();
                if (!isVisible) {
                    menu.style.display = 'block';
                    menu.style.left = `${rect.left}px`;
                    menu.style.top = `${rect.bottom + 4}px`;
                    item.classList.add('active');
                }
            });
        });

        document.addEventListener('click', () => {
            hideMenus();
            this.hideContextMenu();
        });
        window.addEventListener('resize', () => {
            hideMenus();
            this.hideContextMenu();
        });

        const handleMenuClick = (e) => {
            const target = e.target.closest('.menu-option');
            if (!target) return;
            const action = target.dataset.action;
            if (!action) return;
            hideMenus();
            this.handleMenuAction(action);
        };
        document.querySelectorAll('.menu-dropdown').forEach(menu => {
            menu.addEventListener('click', handleMenuClick);
        });

        const contextMenu = document.getElementById('context-menu');
        if (contextMenu) {
            contextMenu.addEventListener('click', handleMenuClick);
        }

        if (!this.globalContextMenuBound) {
            const appRoot = document.getElementById('app') || document.body;
            appRoot.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this.showContextMenu(e.clientX, e.clientY);
            });
            this.globalContextMenuBound = true;
        }
    }

    updateShortcutLabels() {
        const isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform) || /Mac/.test(navigator.userAgent);
        document.querySelectorAll('.menu-option[data-label]').forEach(option => {
            const label = option.getAttribute('data-label') || '';
            const shortcut = isMac ? option.getAttribute('data-shortcut-mac') : option.getAttribute('data-shortcut-win');
            if (shortcut) {
                option.textContent = `${label} (${shortcut})`;
            } else {
                option.textContent = label;
            }
        });
    }

    handleMenuAction(action) {
        switch (action) {
            case 'new':
                this.createNewProject();
                break;
            case 'open':
                this.loadProjectFromFile();
                break;
            case 'save':
                this.saveProjectToFile();
                break;
            case 'export-png':
                this.openExportModalWithFormat('png');
                break;
            case 'export-psd':
                this.openExportModalWithFormat('psd');
                break;
            case 'preferences':
                this.openPreferencesModal();
                break;
            case 'undo':
                this.undo();
                break;
            case 'redo':
                this.redo();
                break;
            case 'copy':
                this.copyLayer();
                break;
            case 'paste':
                this.pasteLayer();
                break;
            case 'duplicate':
                if (this.currentLayer) this.duplicateLayer(this.currentLayer);
                break;
            case 'delete':
                if (this.currentLayer) this.deleteLayer(this.currentLayer.id);
                break;
            case 'next-port':
                this.stepCustomPort(1);
                break;
            case 'prev-port':
                this.stepCustomPort(-1);
                break;
            case 'fit':
                if (window.canvasRenderer) window.canvasRenderer.fitToView();
                break;
            case 'actual-size':
                if (window.canvasRenderer) {
                    window.canvasRenderer.zoom = 1;
                    window.canvasRenderer.panX = 0;
                    window.canvasRenderer.panY = 0;
                    window.canvasRenderer.render();
                }
                break;
            default:
                break;
        }
    }

    openExportModalWithFormat(format) {
        const modal = document.getElementById('export-modal');
        const formatSelect = document.getElementById('export-format');
        if (formatSelect) formatSelect.value = format;
        if (modal) {
            modal.style.display = 'block';
            document.getElementById('export-name').value = this.project.name || 'Untitled Project';
            this.loadExportSuffixesToUI();
            this.updateExportPreview();
        }
    }

    showContextMenu(x, y) {
        const menu = document.getElementById('context-menu');
        if (!menu) return;
        menu.style.visibility = 'hidden';
        menu.style.display = 'block';
        const menuRect = menu.getBoundingClientRect();
        const margin = 8;
        const maxX = window.innerWidth - menuRect.width - margin;
        const maxY = window.innerHeight - menuRect.height - margin;
        const clampedX = Math.max(margin, Math.min(x, maxX));
        const clampedY = Math.max(margin, Math.min(y, maxY));
        menu.style.left = `${clampedX}px`;
        menu.style.top = `${clampedY}px`;
        menu.style.visibility = 'visible';
    }

    hideContextMenu() {
        const menu = document.getElementById('context-menu');
        if (menu) menu.style.display = 'none';
    }

    stepCustomPort(delta) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        const view = window.canvasRenderer.viewMode;
        if (view === 'data-flow' && this.isCustomFlow(this.currentLayer)) {
            this.ensureCustomFlowState(this.currentLayer);
            this.currentLayer.customPortIndex = Math.max(1, (this.currentLayer.customPortIndex || 1) + delta);
            this.saveState('Custom Port Change');
            this.saveClientSideProperties();
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
            window.canvasRenderer.render();
        } else if (view === 'power' && this.isCustomPower(this.currentLayer)) {
            this.ensureCustomPowerState(this.currentLayer);
            this.currentLayer.powerCustomIndex = Math.max(1, (this.currentLayer.powerCustomIndex || 1) + delta);
            this.saveState('Power Custom Circuit Change');
            this.saveClientSideProperties();
            this.updateCustomPowerUI();
            window.canvasRenderer.render();
        }
    }
    
    // Update the port capacity display in the UI
    updatePortCapacityDisplay() {
        if (!this.currentLayer) {
            return;
        }
        if ((this.currentLayer.type || 'screen') === 'image') {
            const capacityEl = document.getElementById('port-capacity');
            const panelsPerPortEl = document.getElementById('panels-per-port');
            const portsRequiredEl = document.getElementById('ports-required');
            if (capacityEl) capacityEl.textContent = '—';
            if (panelsPerPortEl) panelsPerPortEl.textContent = '—';
            if (portsRequiredEl) portsRequiredEl.textContent = '—';
            return;
        }
        
        const bitDepth = this.currentLayer.bitDepth || 8;
        const frameRate = this.currentLayer.frameRate || 60;
        const processorType = this.currentLayer.processorType || 'novastar-armor';
        const mappingMode = this.currentLayer.portMappingMode || 'organized';
        const portCapacity = this.calculatePortCapacity(bitDepth, frameRate, processorType);
        
        // Update capacity display
        const capacityEl = document.getElementById('port-capacity');
        if (capacityEl) {
            if (portCapacity > 0) {
                capacityEl.textContent = portCapacity.toLocaleString();
                capacityEl.style.color = '#4A90E2';
            } else {
                capacityEl.textContent = 'N/A';
                capacityEl.style.color = '#ff6600';
            }
        }

        const panelPixels = this.getFullPanelPixels(this.currentLayer);
        const panelsPerPort = (portCapacity > 0 && panelPixels > 0) ? Math.floor(portCapacity / panelPixels) : 0;
        
        const panelsPerPortEl = document.getElementById('panels-per-port');
        if (panelsPerPortEl) {
            if (panelsPerPort < 1) {
                panelsPerPortEl.textContent = 'ERROR';
                panelsPerPortEl.style.color = '#ff0000';
            } else {
                panelsPerPortEl.textContent = panelsPerPort.toLocaleString();
                panelsPerPortEl.style.color = '#4A90E2';
            }
        }
        
        // Calculate total ports required from assignments
        const usesRectangle = this.usesRectangleConstraint(processorType);
        const isOrganized = mappingMode === 'organized';
        const visiblePanels = this.currentLayer.panels ? this.currentLayer.panels.filter(p => !p.hidden).length : 0;
        const panelCountForStatus = usesRectangle && this.currentLayer.panels ? this.currentLayer.panels.length : visiblePanels;
        const assignments = this.calculatePortAssignments(this.currentLayer);
        let portsRequired = this.currentLayer._autoPortsRequired || assignments.reduce((max, a) => Math.max(max, a.port || 0), 0);

        const basePortsRequired = portsRequired;
        if (this.isCustomFlow(this.currentLayer) && this.currentLayer.customPortPaths) {
            const customPorts = Object.keys(this.currentLayer.customPortPaths)
                .map(p => parseInt(p, 10))
                .filter(p => (this.currentLayer.customPortPaths[p] || []).length > 0);
            if (customPorts.length > 0) {
                portsRequired = Math.max(...customPorts);
            } else {
                portsRequired = basePortsRequired > 0 ? basePortsRequired : (this.currentLayer.customPortIndex || 1);
            }
        }
        this.currentLayer._portsRequired = portsRequired;
        // debug toggle removed
        const portsRequiredEl = document.getElementById('ports-required');
        if (portsRequiredEl) {
            if ((this.currentLayer._capacityError || (portsRequired === 0 && panelsPerPort > 0 && panelCountForStatus > 0))) {
                portsRequiredEl.textContent = 'ERROR';
                portsRequiredEl.style.color = '#ff0000';
            } else if (panelCountForStatus === 0) {
                portsRequiredEl.textContent = '0';
                portsRequiredEl.style.color = '#888';
            } else {
                portsRequiredEl.textContent = portsRequired;
                if (portsRequired <= 4) {
                    portsRequiredEl.style.color = '#00cc00';
                } else if (portsRequired <= 8) {
                    portsRequiredEl.style.color = '#ffcc00';
                } else {
                    portsRequiredEl.style.color = '#ff6600';
                }
            }
        }
        
        // Update mapping mode button states
        const mappingOrgBtn = document.getElementById('mapping-organized');
        const mappingMaxBtn = document.getElementById('mapping-max-capacity');
        if (mappingOrgBtn && mappingMaxBtn) {
            if (usesRectangle) {
                // NovaStar 1G/Armor: always rectangle, disable both buttons
                mappingOrgBtn.style.opacity = '0.5';
                mappingOrgBtn.style.pointerEvents = 'none';
                mappingOrgBtn.style.background = '#4A90E2';
                mappingOrgBtn.style.color = '#fff';
                mappingMaxBtn.style.opacity = '0.5';
                mappingMaxBtn.style.pointerEvents = 'none';
                mappingMaxBtn.style.background = '#333';
                mappingMaxBtn.style.color = '#ccc';
                mappingOrgBtn.title = 'NovaStar 1G/Armor always uses rectangle-based mapping';
                mappingMaxBtn.title = 'NovaStar 1G/Armor always uses rectangle-based mapping';
            } else {
                // Enable both buttons and set active state
                mappingOrgBtn.style.opacity = '1';
                mappingOrgBtn.style.pointerEvents = 'auto';
                mappingMaxBtn.style.opacity = '1';
                mappingMaxBtn.style.pointerEvents = 'auto';
                mappingOrgBtn.title = 'Ports fill complete rows or columns only';
                mappingMaxBtn.title = 'Ports fill to max pixel capacity - may split mid-row/column';
                
                if (isOrganized) {
                    mappingOrgBtn.style.background = '#4A90E2';
                    mappingOrgBtn.style.color = '#fff';
                    mappingMaxBtn.style.background = '#333';
                    mappingMaxBtn.style.color = '#ccc';
                } else {
                    mappingMaxBtn.style.background = '#4A90E2';
                    mappingMaxBtn.style.color = '#fff';
                    mappingOrgBtn.style.background = '#333';
                    mappingOrgBtn.style.color = '#ccc';
                }
            }
        }
    }

    updatePowerCapacityDisplay() {
        if (!this.currentLayer) return;
        if ((this.currentLayer.type || 'screen') === 'image') {
            const wattsEl = document.getElementById('power-watts-per-circuit');
            const panelsEl = document.getElementById('power-panels-per-circuit');
            const circuitsEl = document.getElementById('power-circuits-required');
            const amps1El = document.getElementById('power-total-amps-1ph');
            const amps3El = document.getElementById('power-total-amps-3ph');
            if (wattsEl) wattsEl.textContent = '—';
            if (panelsEl) panelsEl.textContent = '—';
            if (circuitsEl) circuitsEl.textContent = '—';
            if (amps1El) amps1El.textContent = '—';
            if (amps3El) amps3El.textContent = '—';
            return;
        }
        const layer = this.currentLayer;
        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const wattsPerCircuit = voltage * amperage;
        const panelsPerCircuit = panelWatts > 0 ? Math.floor(wattsPerCircuit / panelWatts) : 0;
        const visiblePanels = layer.panels ? layer.panels.filter(p => !p.hidden) : [];
        const equivalentPanels = visiblePanels.reduce((sum, p) => sum + this.getPanelLoadFactor(layer, p), 0);
        const totalWatts = panelWatts * equivalentPanels;
        const totalAmps1 = voltage > 0 ? totalWatts / voltage : 0;
        const totalAmps3 = voltage > 0 ? totalWatts / (voltage * 1.73) : 0;
        layer._powerTotalAmps1 = totalAmps1;
        layer._powerTotalAmps3 = totalAmps3;

        const wattsEl = document.getElementById('power-watts-per-circuit');
        const panelsEl = document.getElementById('power-panels-per-circuit');
        const circuitsEl = document.getElementById('power-circuits-required');
        const amps1El = document.getElementById('power-total-amps-1ph');
        const amps3El = document.getElementById('power-total-amps-3ph');

        if (wattsEl) wattsEl.textContent = wattsPerCircuit > 0 ? wattsPerCircuit.toLocaleString() : '0';
        if (panelsEl) panelsEl.textContent = panelsPerCircuit > 0 ? panelsPerCircuit.toLocaleString() : '0';
        const powerAssignments = this.calculatePowerAssignments(layer);
        const circuitsRequired = powerAssignments.circuits.length;
        layer._powerError = powerAssignments.error;
        layer._powerCircuits = powerAssignments.circuits;

        if (circuitsEl) circuitsEl.textContent = circuitsRequired > 0 ? circuitsRequired.toLocaleString() : '0';
        layer._powerCircuitsRequired = circuitsRequired;
        if (amps1El) amps1El.textContent = totalAmps1 ? totalAmps1.toFixed(2) + ' A' : '0';
        if (amps3El) amps3El.textContent = totalAmps3 ? totalAmps3.toFixed(2) + ' A' : '0';
    }

    calculatePowerAssignments(layer) {
        if (!layer || (layer.type || 'screen') === 'image' || !Array.isArray(layer.panels)) return { circuits: [], error: null };

        const voltage = parseFloat(layer.powerVoltage) || 0;
        const amperage = parseFloat(layer.powerAmperage) || 0;
        const panelWatts = parseFloat(layer.panelWatts) || 0;
        const wattsPerCircuit = voltage * amperage;
        const pattern = layer.powerFlowPattern || 'tl-h';
        const maximize = !!layer.powerMaximize;
        const organized = !!layer.powerOrganized && !maximize;
        const isHorizontalFirst = pattern.includes('-h');
        const startsTop = pattern.startsWith('t');
        const startsLeft = pattern.includes('l-');

        if (wattsPerCircuit <= 0 || panelWatts <= 0) {
            return { circuits: [], error: null };
        }

        const loadOf = (panel) => panelWatts * this.getPanelLoadFactor(layer, panel);
        const visibleOrdered = this.getOrderedPanelsByPattern(layer, pattern, false);
        if (visibleOrdered.length === 0) return { circuits: [], error: null };

        if (panelWatts > wattsPerCircuit) {
            return { circuits: [], error: { message: 'PANEL WATTS EXCEED CIRCUIT CAPACITY' } };
        }

        const circuits = [];
        if (organized) {
            const unitIndices = isHorizontalFirst
                ? [...Array(layer.rows).keys()].map(i => (startsTop ? i : (layer.rows - 1 - i)))
                : [...Array(layer.columns).keys()].map(i => (startsLeft ? i : (layer.columns - 1 - i)));
            let current = { unitIndices: [], load: 0 };

            for (const idx of unitIndices) {
                const unitPanels = visibleOrdered.filter(p => (isHorizontalFirst ? p.row === idx : p.col === idx));
                if (unitPanels.length === 0) continue;
                const unitLoad = unitPanels.reduce((sum, p) => sum + loadOf(p), 0);
                if (unitLoad > wattsPerCircuit) {
                    return {
                        circuits: [],
                        error: {
                            message: isHorizontalFirst ? 'CANNOT FIT COMPLETE ROW' : 'CANNOT FIT COMPLETE COLUMN',
                            unitType: isHorizontalFirst ? 'row' : 'column',
                            unitCount: isHorizontalFirst ? layer.columns : layer.rows
                        }
                    };
                }
                if (current.load > 0 && current.load + unitLoad > wattsPerCircuit) {
                    circuits.push(
                        this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, current.unitIndices || [], false)
                    );
                    current = { unitIndices: [], load: 0 };
                }
                current.unitIndices.push(idx);
                current.load += unitLoad;
            }
            if ((current.unitIndices || []).length > 0) {
                circuits.push(
                    this.getOrganizedPanelsForUnits(layer, pattern, isHorizontalFirst, current.unitIndices || [], false)
                );
            }
        } else {
            let current = [];
            let currentLoad = 0;
            visibleOrdered.forEach(panel => {
                const load = loadOf(panel);
                if (load <= 0) return;
                if (currentLoad > 0 && currentLoad + load > wattsPerCircuit) {
                    circuits.push(current);
                    current = [];
                    currentLoad = 0;
                }
                current.push(panel);
                currentLoad += load;
            });
            if (current.length > 0) circuits.push(current);
        }

        return { circuits, error: null };
    }

    getPortLabelText(layer, portNum, type) {
        const template = type === 'return' ? (layer.portLabelTemplateReturn || 'R#') : (layer.portLabelTemplatePrimary || 'P#');
        const overrides = type === 'return' ? (layer.portLabelOverridesReturn || {}) : (layer.portLabelOverridesPrimary || {});
        if (overrides && overrides[portNum]) return overrides[portNum];
        return template.replace('#', portNum);
    }

    getPowerCircuitLabel(layer, circuitNum) {
        const template = layer.powerLabelTemplate || 'S1-#';
        const overrides = layer.powerLabelOverrides || {};
        if (overrides && overrides[circuitNum]) return overrides[circuitNum];
        // Default power labeling is 6 circuits per multi:
        // S1-1 ... S1-6, then S2-1 ... S2-6, etc.
        if (template === 'S1-#') {
            const n = Math.max(1, parseInt(circuitNum, 10) || 1);
            const multi = Math.floor((n - 1) / 6) + 1;
            const circuitInMulti = ((n - 1) % 6) + 1;
            return `S${multi}-${circuitInMulti}`;
        }
        return template.replace('#', circuitNum);
    }

    getDefaultPowerCircuitColors() {
        return {
            A: '#BC382F',
            B: '#CC6B30',
            C: '#D2E94D',
            D: '#2CF82B',
            E: '#2145DC',
            F: '#7414F5'
        };
    }

    normalizeHexColor(value, fallback = '#FF0000') {
        const raw = String(value || '').trim();
        if (/^#[0-9a-fA-F]{6}$/.test(raw)) return raw.toUpperCase();
        if (/^[0-9a-fA-F]{6}$/.test(raw)) return `#${raw.toUpperCase()}`;
        return fallback;
    }

    normalizePowerCircuitColors(colors) {
        const defaults = this.getDefaultPowerCircuitColors();
        const next = { ...defaults };
        if (colors && typeof colors === 'object') {
            Object.keys(defaults).forEach(letter => {
                if (colors[letter]) {
                    next[letter] = this.normalizeHexColor(colors[letter], defaults[letter]);
                }
            });
        }
        // Migrate old default green (Circuit 4) to the new default.
        if ((next.D || '').toUpperCase() === '#79FC4C') {
            next.D = defaults.D;
        }
        return next;
    }

    getPowerCircuitLetter(circuitNum) {
        let n = Math.max(1, parseInt(circuitNum, 10) || 1);
        let out = '';
        while (n > 0) {
            n -= 1;
            out = String.fromCharCode(65 + (n % 26)) + out;
            n = Math.floor(n / 26);
        }
        return out;
    }

    getPowerCircuitColor(layer, circuitNum) {
        const colors = this.normalizePowerCircuitColors(layer && layer.powerCircuitColors);
        const n = Math.max(1, parseInt(circuitNum, 10) || 1);
        const slots = ['A', 'B', 'C', 'D', 'E', 'F'];
        const slotKey = slots[(n - 1) % slots.length];
        return colors[slotKey] || '#BC382F';
    }

    updatePortLabelEditor() {
        if (!this.currentLayer) return;
        if ((this.currentLayer.type || 'screen') === 'image') return;
        const list = document.getElementById('port-label-list');
        if (!list) return;

        let portsRequired = this.currentLayer._portsRequired || 0;
        if (portsRequired <= 0) {
            this.updatePortCapacityDisplay();
            portsRequired = this.currentLayer._portsRequired || 0;
        }
        if (this.customDebug) {
            console.log('[PortLabels] update', {
                layerId: this.currentLayer.id,
                portsRequired,
                flowPattern: this.currentLayer.flowPattern,
                bitDepth: this.currentLayer.bitDepth,
                frameRate: this.currentLayer.frameRate,
                processorType: this.currentLayer.processorType,
                panelPixels: this.currentLayer.cabinet_width * this.currentLayer.cabinet_height,
                panels: this.currentLayer.panels ? this.currentLayer.panels.length : 0
            });
        }
        list.innerHTML = '';

        if (portsRequired <= 0) {
            const empty = document.createElement('div');
            empty.style.color = '#888';
            empty.style.fontSize = '11px';
            empty.textContent = 'No ports to edit.';
            list.appendChild(empty);
            return;
        }

        for (let portNum = 1; portNum <= portsRequired; portNum++) {
            const row = document.createElement('div');
            row.style.display = 'grid';
            row.style.gridTemplateColumns = '20px 40px 1fr 1fr';
            row.style.gap = '6px';
            row.style.alignItems = 'center';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.setAttribute('data-port', String(portNum));

            const label = document.createElement('div');
            label.style.fontSize = '11px';
            label.style.color = '#ccc';
            label.textContent = `Port ${portNum}`;

            const primaryInput = document.createElement('input');
            primaryInput.type = 'text';
            primaryInput.value = (this.currentLayer.portLabelOverridesPrimary && this.currentLayer.portLabelOverridesPrimary[portNum]) || '';
            primaryInput.placeholder = this.getPortLabelText(this.currentLayer, portNum, 'primary');
            primaryInput.style.padding = '4px 6px';
            primaryInput.style.background = '#0d0d0d';
            primaryInput.style.border = '1px solid #333';
            primaryInput.style.color = '#fff';
            primaryInput.style.borderRadius = '4px';
            primaryInput.style.fontFamily = 'monospace';

            primaryInput.addEventListener('change', () => {
                const val = primaryInput.value.trim();
                this.applyToSelectedLayers(layer => {
                    if (!layer.portLabelOverridesPrimary) layer.portLabelOverridesPrimary = {};
                    if (val) {
                        layer.portLabelOverridesPrimary[portNum] = val;
                    } else {
                        delete layer.portLabelOverridesPrimary[portNum];
                    }
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });

            const returnInput = document.createElement('input');
            returnInput.type = 'text';
            returnInput.value = (this.currentLayer.portLabelOverridesReturn && this.currentLayer.portLabelOverridesReturn[portNum]) || '';
            returnInput.placeholder = this.getPortLabelText(this.currentLayer, portNum, 'return');
            returnInput.style.padding = '4px 6px';
            returnInput.style.background = '#0d0d0d';
            returnInput.style.border = '1px solid #333';
            returnInput.style.color = '#fff';
            returnInput.style.borderRadius = '4px';
            returnInput.style.fontFamily = 'monospace';

            returnInput.addEventListener('change', () => {
                const val = returnInput.value.trim();
                this.applyToSelectedLayers(layer => {
                    if (!layer.portLabelOverridesReturn) layer.portLabelOverridesReturn = {};
                    if (val) {
                        layer.portLabelOverridesReturn[portNum] = val;
                    } else {
                        delete layer.portLabelOverridesReturn[portNum];
                    }
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });

            row.appendChild(cb);
            row.appendChild(label);
            row.appendChild(primaryInput);
            row.appendChild(returnInput);
            list.appendChild(row);
        }
        // debug toggle removed
    }

    updatePowerLabelEditor() {
        if (!this.currentLayer) return;
        if ((this.currentLayer.type || 'screen') === 'image') return;
        const list = document.getElementById('power-label-list');
        if (!list) return;
        list.style.overflowX = 'hidden';

        let circuitsRequired = this.currentLayer._powerCircuitsRequired || 0;
        if (this.isCustomPower(this.currentLayer) && this.currentLayer.powerCustomPaths) {
            const customCircuits = Object.keys(this.currentLayer.powerCustomPaths)
                .map(c => parseInt(c, 10))
                .filter(c => (this.currentLayer.powerCustomPaths[c] || []).length > 0);
            if (customCircuits.length > 0) {
                circuitsRequired = Math.max(...customCircuits);
            } else {
                circuitsRequired = circuitsRequired > 0 ? circuitsRequired : (this.currentLayer.powerCustomIndex || 1);
            }
        }

        list.innerHTML = '';
        if (circuitsRequired <= 0) {
            const empty = document.createElement('div');
            empty.style.color = '#888';
            empty.style.fontSize = '11px';
            empty.textContent = 'No circuits to edit.';
            list.appendChild(empty);
            return;
        }

        for (let circuitNum = 1; circuitNum <= circuitsRequired; circuitNum++) {
            const row = document.createElement('div');
            row.style.display = 'grid';
            row.style.gridTemplateColumns = '20px 72px 1fr';
            row.style.gap = '6px';
            row.style.alignItems = 'center';
            row.style.maxWidth = '100%';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.setAttribute('data-circuit', String(circuitNum));

            const label = document.createElement('div');
            label.style.fontSize = '11px';
            label.style.color = '#ccc';
            label.textContent = `Circuit ${circuitNum}`;

            const input = document.createElement('input');
            input.type = 'text';
            input.value = (this.currentLayer.powerLabelOverrides && this.currentLayer.powerLabelOverrides[circuitNum]) || '';
            input.placeholder = this.getPowerCircuitLabel(this.currentLayer, circuitNum);
            input.style.padding = '4px 6px';
            input.style.background = '#0d0d0d';
            input.style.border = '1px solid #333';
            input.style.color = '#fff';
            input.style.borderRadius = '4px';
            input.style.fontFamily = 'monospace';
            input.style.width = '100%';
            input.style.minWidth = '0';
            input.style.boxSizing = 'border-box';

            input.addEventListener('change', () => {
                const val = input.value.trim();
                this.applyToSelectedLayers(layer => {
                    if (!layer.powerLabelOverrides) layer.powerLabelOverrides = {};
                    if (val) {
                        layer.powerLabelOverrides[circuitNum] = val;
                    } else {
                        delete layer.powerLabelOverrides[circuitNum];
                    }
                });
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });

            row.appendChild(cb);
            row.appendChild(label);
            row.appendChild(input);
            list.appendChild(row);
        }
    }

    updatePowerCircuitColorEditor() {
        if (!this.currentLayer) return;
        const section = document.getElementById('power-circuit-color-section');
        const list = document.getElementById('power-circuit-color-list');
        if (section) {
            section.style.display = this.currentLayer.powerColorCodedView ? 'block' : 'none';
        }
        if (!list) return;
        list.innerHTML = '';
        const colors = this.normalizePowerCircuitColors(this.currentLayer.powerCircuitColors);
        Object.keys(colors).forEach((letter, index) => {
            const row = document.createElement('div');
            row.style.display = 'grid';
            row.style.gridTemplateColumns = '20px 26px 1fr';
            row.style.gap = '6px';
            row.style.alignItems = 'center';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.setAttribute('data-circuit-letter', letter);

            const swatch = document.createElement('div');
            swatch.style.width = '20px';
            swatch.style.height = '20px';
            swatch.style.borderRadius = '4px';
            swatch.style.border = '1px solid #333';
            swatch.style.background = colors[letter];

            const text = document.createElement('div');
            text.style.fontSize = '12px';
            text.style.color = '#ccc';
            text.textContent = `Circuit ${index + 1}`;

            row.appendChild(cb);
            row.appendChild(swatch);
            row.appendChild(text);
            list.appendChild(row);
        });
    }

    isCustomFlow(layer) {
        return !!layer && layer.flowPattern === 'custom';
    }

    ensureCustomFlowState(layer) {
        if (!layer) return;
        if (!layer.customPortPaths) layer.customPortPaths = {};
        if (!layer.customPortIndex) layer.customPortIndex = 1;
    }

    toggleCustomFlowMode(enabled) {
        if (!this.currentLayer) return;
        if (enabled) {
            if (this.currentLayer.flowPattern && this.currentLayer.flowPattern !== 'custom') {
                this.currentLayer.lastFlowPattern = this.currentLayer.flowPattern;
            }
            this.currentLayer.flowPattern = 'custom';
            this.ensureCustomFlowState(this.currentLayer);
        } else {
            this.currentLayer.flowPattern = this.currentLayer.lastFlowPattern || 'tl-h';
            this.customSelectMode = false;
            this.customSelection.clear();
        }
        this.saveState('Custom Mode Toggle');
        this.saveClientSideProperties();
        this.updatePortCapacityDisplay();
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    updateCustomFlowUI() {
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'image') {
            const container = document.getElementById('custom-flow-controls');
            if (container) container.style.display = 'none';
            return;
        }
        const isCustom = this.currentLayer && this.currentLayer.flowPattern === 'custom';
        const container = document.getElementById('custom-flow-controls');
        const portInput = document.getElementById('custom-active-port-input');
        if (container) {
            container.style.display = isCustom ? 'block' : 'none';
        }
        if (portInput && this.currentLayer) {
            portInput.value = `${this.currentLayer.customPortIndex || 1}`;
        }
        if (window.canvasRenderer) {
            window.canvasRenderer.canvas.style.cursor = isCustom ? 'crosshair' : 'default';
        }
    }

    isCustomPower(layer) {
        return !!layer && layer.powerFlowPattern === 'custom';
    }

    ensureCustomPowerState(layer) {
        if (!layer) return;
        if (!layer.powerCustomPaths) layer.powerCustomPaths = {};
        if (!layer.powerCustomIndex) layer.powerCustomIndex = 1;
    }

    toggleCustomPowerMode(enabled) {
        if (!this.currentLayer) return;
        if (enabled) {
            if (this.currentLayer.powerFlowPattern && this.currentLayer.powerFlowPattern !== 'custom') {
                this.currentLayer.lastPowerFlowPattern = this.currentLayer.powerFlowPattern;
            }
            this.currentLayer.powerFlowPattern = 'custom';
            this.currentLayer.powerCustomPath = true;
            this.ensureCustomPowerState(this.currentLayer);
        } else {
            this.currentLayer.powerFlowPattern = this.currentLayer.lastPowerFlowPattern || 'tl-h';
            this.currentLayer.powerCustomPath = false;
            this.powerCustomSelection.clear();
        }
        this.saveState('Power Custom Mode Toggle');
        this.saveClientSideProperties();
        this.updatePowerCapacityDisplay();
        this.updateCustomPowerUI();
        window.canvasRenderer.render();
    }

    updateCustomPowerUI() {
        if (this.currentLayer && (this.currentLayer.type || 'screen') === 'image') {
            const container = document.getElementById('power-custom-controls');
            if (container) container.style.display = 'none';
            return;
        }
        const isCustom = this.currentLayer && this.currentLayer.powerFlowPattern === 'custom';
        const container = document.getElementById('power-custom-controls');
        const portInput = document.getElementById('power-custom-active');
        if (container) {
            container.style.display = isCustom ? 'block' : 'none';
        }
        if (portInput && this.currentLayer) {
            portInput.value = `${this.currentLayer.powerCustomIndex || 1}`;
        }
        if (window.canvasRenderer) {
            window.canvasRenderer.canvas.style.cursor = isCustom ? 'crosshair' : 'default';
        }
    }

    getPanelKey(panel) {
        return `${panel.row},${panel.col}`;
    }

    getPanelByRowCol(layer, row, col) {
        if (!layer || !layer.panels) return null;
        return layer.panels.find(p => p.row === row && p.col === col) || null;
    }

    togglePanelSelection(panel) {
        if (!panel) return;
        const key = this.getPanelKey(panel);
        if (this.customSelection.has(key)) {
            this.customSelection.delete(key);
        } else {
            this.customSelection.add(key);
        }
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    clearCustomSelection() {
        this.customSelection.clear();
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    selectPanelsInRect(layer, rect) {
        if (!layer) return;
        if (!this.isCustomFlow(layer)) return;
        this.customSelection.clear();
        const minX = Math.min(rect.x1, rect.x2);
        const maxX = Math.max(rect.x1, rect.x2);
        const minY = Math.min(rect.y1, rect.y2);
        const maxY = Math.max(rect.y1, rect.y2);
        layer.panels.forEach(panel => {
            if (panel.hidden) return;
            const intersects = panel.x <= maxX && (panel.x + panel.width) >= minX &&
                panel.y <= maxY && (panel.y + panel.height) >= minY;
            if (intersects) this.customSelection.add(this.getPanelKey(panel));
        });
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    selectPowerPanelsInRect(layer, rect) {
        if (!layer) return;
        if (!this.isCustomPower(layer)) return;
        this.powerCustomSelection.clear();
        const minX = Math.min(rect.x1, rect.x2);
        const maxX = Math.max(rect.x1, rect.x2);
        const minY = Math.min(rect.y1, rect.y2);
        const maxY = Math.max(rect.y1, rect.y2);
        layer.panels.forEach(panel => {
            if (panel.hidden) return;
            const intersects = panel.x <= maxX && (panel.x + panel.width) >= minX &&
                panel.y <= maxY && (panel.y + panel.height) >= minY;
            if (intersects) this.powerCustomSelection.add(this.getPanelKey(panel));
        });
        this.updateCustomPowerUI();
        window.canvasRenderer.render();
    }

    addPanelToCustomPath(panel) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomFlow(this.currentLayer)) return;
        if (this.customSelection.size > 0) return;
        this.ensureCustomFlowState(this.currentLayer);
        const portNum = this.currentLayer.customPortIndex || 1;
        if (!this.currentLayer.customPortPaths[portNum]) this.currentLayer.customPortPaths[portNum] = [];
        const key = this.getPanelKey(panel);
        const exists = this.currentLayer.customPortPaths[portNum].some(p => `${p.row},${p.col}` === key);
        if (!exists) {
            this.currentLayer.customPortPaths[portNum].push({ row: panel.row, col: panel.col });
            this.saveState('Custom Path Edit');
            this.saveClientSideProperties();
            if (this.customDebug) {
                console.log('[CustomFlow] Add panel', { portNum, row: panel.row, col: panel.col });
            }
            this.updatePortLabelEditor();
            window.canvasRenderer.render();
        }
    }

    addPanelToCustomPowerPath(panel) {
        if (!this.currentLayer || !panel || panel.hidden) return;
        if (!this.isCustomPower(this.currentLayer)) return;
        if (this.powerCustomSelection.size > 0) return;
        this.ensureCustomPowerState(this.currentLayer);
        const circuitNum = this.currentLayer.powerCustomIndex || 1;
        if (!this.currentLayer.powerCustomPaths[circuitNum]) this.currentLayer.powerCustomPaths[circuitNum] = [];
        const key = this.getPanelKey(panel);
        const exists = this.currentLayer.powerCustomPaths[circuitNum].some(p => `${p.row},${p.col}` === key);
        if (!exists) {
            this.currentLayer.powerCustomPaths[circuitNum].push({ row: panel.row, col: panel.col });
            this.saveState('Power Custom Path Edit');
            this.saveClientSideProperties();
            if (this.powerCustomDebug) {
                console.log('[CustomPower] Add panel', { circuitNum, row: panel.row, col: panel.col });
            }
            window.canvasRenderer.render();
        }
    }

    handleCustomArrowKey(e) {
        const dir = e.code;
        if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(dir)) return false;
        if (!this.currentLayer) return false;
        const isPower = window.canvasRenderer && window.canvasRenderer.viewMode === 'power';
        if (isPower) {
            if (!this.isCustomPower(this.currentLayer)) return false;
            this.ensureCustomPowerState(this.currentLayer);
            const circuitNum = this.currentLayer.powerCustomIndex || 1;
            const path = this.currentLayer.powerCustomPaths[circuitNum] || [];
            if (path.length === 0) return false;
            const last = path[path.length - 1];
            let nextRow = last.row;
            let nextCol = last.col;
            if (dir === 'ArrowUp') nextRow -= 1;
            if (dir === 'ArrowDown') nextRow += 1;
            if (dir === 'ArrowLeft') nextCol -= 1;
            if (dir === 'ArrowRight') nextCol += 1;
            const panel = this.getPanelByRowCol(this.currentLayer, nextRow, nextCol);
            if (!panel || panel.hidden) return true;
            this.addPanelToCustomPowerPath(panel);
            return true;
        }
        if (!this.isCustomFlow(this.currentLayer)) return false;
        this.ensureCustomFlowState(this.currentLayer);
        const portNum = this.currentLayer.customPortIndex || 1;
        const path = this.currentLayer.customPortPaths[portNum] || [];
        if (path.length === 0) return false;
        const last = path[path.length - 1];
        let nextRow = last.row;
        let nextCol = last.col;
        if (dir === 'ArrowUp') nextRow -= 1;
        if (dir === 'ArrowDown') nextRow += 1;
        if (dir === 'ArrowLeft') nextCol -= 1;
        if (dir === 'ArrowRight') nextCol += 1;
        const panel = this.getPanelByRowCol(this.currentLayer, nextRow, nextCol);
        if (!panel || panel.hidden) return true;
        this.addPanelToCustomPath(panel);
        return true;
    }

    applyPatternToSelection(pattern) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        if (!this.isCustomFlow(this.currentLayer)) return;
        if (this.customSelection.size === 0) return;

        this.ensureCustomFlowState(this.currentLayer);
        const selectedPanels = this.currentLayer.panels
            .filter(panel => this.customSelection.has(this.getPanelKey(panel)) && !panel.hidden);
        if (selectedPanels.length === 0) return;

        const uniqueRows = [...new Set(selectedPanels.map(p => p.row))].sort((a, b) => a - b);
        const uniqueCols = [...new Set(selectedPanels.map(p => p.col))].sort((a, b) => a - b);
        const rowIndex = new Map(uniqueRows.map((r, i) => [r, i]));
        const colIndex = new Map(uniqueCols.map((c, i) => [c, i]));

        const normalizedGrid = Array.from({ length: uniqueRows.length }, () => Array(uniqueCols.length).fill(null));
        selectedPanels.forEach(panel => {
            const r = rowIndex.get(panel.row);
            const c = colIndex.get(panel.col);
            normalizedGrid[r][c] = panel;
        });

        const ordered = this.getPatternOrderForGrid(pattern, normalizedGrid);
        if (ordered.length === 0) return;

        const portNum = this.currentLayer.customPortIndex || 1;
        this.currentLayer.customPortPaths[portNum] = ordered.map(p => ({ row: p.row, col: p.col }));
        this.saveState('Custom Pattern Apply');
        this.saveClientSideProperties();
        if (this.customDebug) {
            const first = ordered[0];
            const last = ordered[ordered.length - 1];
            console.log('[CustomFlow] Apply pattern', {
                pattern,
                portNum,
                count: ordered.length,
                gridRows: normalizedGrid.length,
                gridCols: normalizedGrid[0] ? normalizedGrid[0].length : 0,
                first: first ? { row: first.row, col: first.col } : null,
                last: last ? { row: last.row, col: last.col } : null
            });
        }
        this.updatePortLabelEditor();
        window.canvasRenderer.render();
    }

    applyPowerPatternToSelection(pattern) {
        if (!this.currentLayer || !window.canvasRenderer) return;
        if (!this.isCustomPower(this.currentLayer)) return;
        if (this.powerCustomSelection.size === 0) return;

        this.ensureCustomPowerState(this.currentLayer);
        const selectedPanels = this.currentLayer.panels
            .filter(panel => this.powerCustomSelection.has(this.getPanelKey(panel)) && !panel.hidden);
        if (selectedPanels.length === 0) return;

        const uniqueRows = [...new Set(selectedPanels.map(p => p.row))].sort((a, b) => a - b);
        const uniqueCols = [...new Set(selectedPanels.map(p => p.col))].sort((a, b) => a - b);
        const rowIndex = new Map(uniqueRows.map((r, i) => [r, i]));
        const colIndex = new Map(uniqueCols.map((c, i) => [c, i]));

        const normalizedGrid = Array.from({ length: uniqueRows.length }, () => Array(uniqueCols.length).fill(null));
        selectedPanels.forEach(panel => {
            const r = rowIndex.get(panel.row);
            const c = colIndex.get(panel.col);
            normalizedGrid[r][c] = panel;
        });

        const ordered = this.getPatternOrderForGrid(pattern, normalizedGrid);
        if (ordered.length === 0) return;

        const circuitNum = this.currentLayer.powerCustomIndex || 1;
        this.currentLayer.powerCustomPaths[circuitNum] = ordered.map(p => ({ row: p.row, col: p.col }));
        this.saveState('Power Custom Pattern Apply');
        this.saveClientSideProperties();
        if (this.powerCustomDebug) {
            const first = ordered[0];
            const last = ordered[ordered.length - 1];
            console.log('[CustomPower] Apply pattern', {
                pattern,
                circuitNum,
                count: ordered.length,
                gridRows: normalizedGrid.length,
                gridCols: normalizedGrid[0] ? normalizedGrid[0].length : 0,
                first: first ? { row: first.row, col: first.col } : null,
                last: last ? { row: last.row, col: last.col } : null
            });
        }
        window.canvasRenderer.render();
    }

    getPatternOrderForGrid(pattern, grid) {
        const rows = grid.length;
        const cols = rows > 0 ? grid[0].length : 0;
        if (rows === 0 || cols === 0) return [];

        const [startCorner, direction] = pattern.split('-');
        let startRow, startCol, rowDir, colDir;

        switch (startCorner) {
            case 'tl':
                startRow = 0; startCol = 0; rowDir = 1; colDir = 1; break;
            case 'tr':
                startRow = 0; startCol = cols - 1; rowDir = 1; colDir = -1; break;
            case 'bl':
                startRow = rows - 1; startCol = 0; rowDir = -1; colDir = 1; break;
            case 'br':
                startRow = rows - 1; startCol = cols - 1; rowDir = -1; colDir = -1; break;
            default:
                startRow = 0; startCol = 0; rowDir = 1; colDir = 1;
        }

        const ordered = [];
        const isVerticalFirst = (direction === 'v');

        if (isVerticalFirst) {
            for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                const colOffset = Math.abs(c - startCol);
                const shouldReverse = colOffset % 2 === 1;
                if (shouldReverse) {
                    for (let r = startRow + (rows - 1) * rowDir; r >= 0 && r < rows; r -= rowDir) {
                        if (grid[r] && grid[r][c]) ordered.push(grid[r][c]);
                    }
                } else {
                    for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                        if (grid[r] && grid[r][c]) ordered.push(grid[r][c]);
                    }
                }
            }
        } else {
            for (let r = startRow; r >= 0 && r < rows; r += rowDir) {
                const rowOffset = Math.abs(r - startRow);
                const shouldReverse = rowOffset % 2 === 1;
                if (shouldReverse) {
                    for (let c = startCol + (cols - 1) * colDir; c >= 0 && c < cols; c -= colDir) {
                        if (grid[r] && grid[r][c]) ordered.push(grid[r][c]);
                    }
                } else {
                    for (let c = startCol; c >= 0 && c < cols; c += colDir) {
                        if (grid[r] && grid[r][c]) ordered.push(grid[r][c]);
                    }
                }
            }
        }

        return ordered;
    }
    
    renderLayers() {
        
        const container = document.getElementById('layers-list');
        container.innerHTML = '';
        
        if (!this.project || !this.project.layers) {
            console.error('RENDER LAYERS ERROR: No project or no layers array!');
            return;
        }
        
        // Debug: Log all layer IDs to check for duplicates
        const layerIds = this.project.layers.map(l => l.id);
        const uniqueIds = [...new Set(layerIds)];
        if (layerIds.length !== uniqueIds.length) {
            console.error('RENDER LAYERS: DUPLICATE IDs DETECTED!', layerIds);
        }
        
        console.log('RENDER LAYERS: currentLayer.id =', this.currentLayer?.id, 'all ids =', layerIds);
        
        // Reverse the layers array for display - Photoshop style (newest on top)
        const reversedLayers = [...this.project.layers].reverse();
        this.layerListOrder = reversedLayers.map(l => l.id);
        
        reversedLayers.forEach(layer => {
            const layerDiv = document.createElement('div');
            layerDiv.className = 'layer-item';
            layerDiv.dataset.layerId = layer.id;
            layerDiv.draggable = true;
            if (this.selectedLayerIds && this.selectedLayerIds.has(layer.id)) {
                layerDiv.classList.add('active');
            }
            if (this.currentLayer && this.currentLayer.id === layer.id) {
                layerDiv.classList.add('primary');
            }
            
            const isImage = (layer.type || 'screen') === 'image';
            const activePanels = isImage ? 0 : layer.panels.filter(p => !p.blank && !p.hidden).length;
            
            const infoText = isImage
                ? `${layer.imageWidth || 0}×${layer.imageHeight || 0}px • ${Math.round((layer.imageScale || 1) * 100)}%`
                : `${layer.columns}x${layer.rows} (${activePanels} panels) • ${layer.cabinet_width}×${layer.cabinet_height}px`;
            const lockBadge = layer.locked ? '<span title="Locked" style="margin-left: 6px; color:#bbb;">🔒</span>' : '';
            layerDiv.innerHTML = `
                <div class="layer-header">
                    <div style="display:flex; align-items:center; gap:4px;">
                        <input type="text" class="layer-name-input" data-layer-id="${layer.id}" value="${layer.name}" style="background: transparent; border: 1px solid transparent; color: #e0e0e0; padding: 2px 4px; border-radius: 3px; font-size: 13px; font-weight: 600; width: 80px;">
                        ${lockBadge}
                    </div>
                    <div class="layer-controls">
                        <button class="layer-btn" onclick="app.toggleLayerVisibility(${layer.id})" title="Toggle Visibility">
                            ${layer.visible ? '👁' : '👁‍🗨'}
                        </button>
                    </div>
                </div>
                <div class="layer-info">
                    ${infoText}
                </div>
            `;
            
            // Single click to select
            layerDiv.addEventListener('click', (e) => {
                if (!e.target.classList.contains('layer-btn') && !e.target.classList.contains('layer-name-input')) {
                    const isToggle = e.metaKey || e.ctrlKey;
                    const isRange = e.shiftKey;
                    if (isRange) {
                        this.selectLayerRange(layer);
                    } else if (isToggle) {
                        this.toggleLayerSelection(layer);
                    } else {
                        this.selectLayer(layer);
                    }
                }
            });

            // Right-click context menu on layer list
            layerDiv.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const isToggle = e.metaKey || e.ctrlKey;
                if (isToggle) {
                    this.toggleLayerSelection(layer);
                } else {
                    this.selectLayer(layer);
                }
                this.showContextMenu(e.clientX, e.clientY);
            });

            const handleDragStart = (e) => {
                e.dataTransfer.setData('text/plain', String(layer.id));
                e.dataTransfer.effectAllowed = 'move';
                this.dragLayerId = layer.id;
            };
            layerDiv.addEventListener('dragstart', handleDragStart);
            const headerEl = layerDiv.querySelector('.layer-header');
            const infoEl = layerDiv.querySelector('.layer-info');
            if (headerEl) {
                headerEl.draggable = true;
                headerEl.addEventListener('dragstart', handleDragStart);
            }
            if (infoEl) {
                infoEl.draggable = true;
                infoEl.addEventListener('dragstart', handleDragStart);
            }
            layerDiv.addEventListener('dragover', (e) => {
                e.preventDefault();
                const rect = layerDiv.getBoundingClientRect();
                const midpoint = rect.top + rect.height / 2;
                const position = e.clientY < midpoint ? 'top' : 'bottom';
                layerDiv.classList.toggle('drag-over-top', position === 'top');
                layerDiv.classList.toggle('drag-over-bottom', position === 'bottom');
                layerDiv.classList.add('drag-over');
                this.dragOverPosition = position;
            });
            layerDiv.addEventListener('dragleave', () => {
                layerDiv.classList.remove('drag-over', 'drag-over-top', 'drag-over-bottom');
            });
            layerDiv.addEventListener('drop', (e) => {
                e.preventDefault();
                layerDiv.classList.remove('drag-over', 'drag-over-top', 'drag-over-bottom');
                const draggedId = this.dragLayerId || parseInt(e.dataTransfer.getData('text/plain'), 10);
                const targetId = layer.id;
                if (!draggedId || draggedId === targetId) return;
                const rect = layerDiv.getBoundingClientRect();
                const midpoint = rect.top + rect.height / 2;
                const insertAfter = e.clientY >= midpoint;
                this.reorderLayersByDrag(draggedId, targetId, insertAfter);
            });
            
            // Handle name input changes
            const nameInput = layerDiv.querySelector('.layer-name-input');
            nameInput.readOnly = true;
            nameInput.addEventListener('focus', () => {
                if (nameInput.readOnly) {
                    nameInput.blur();
                }
            });
            nameInput.addEventListener('mousedown', (e) => {
                if (nameInput.readOnly) {
                    e.preventDefault();
                }
            });
            nameInput.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                nameInput.readOnly = false;
                nameInput.style.border = '1px solid #4A90E2';
                nameInput.style.background = '#1a1a1a';
                nameInput.focus();
                nameInput.select();
            });
            nameInput.addEventListener('blur', () => {
                nameInput.readOnly = true;
                nameInput.style.border = '1px solid transparent';
                nameInput.style.background = 'transparent';
                const newName = nameInput.value.trim() || layer.name;
                if (newName !== layer.name) {
                    layer.name = newName;
                    fetch(`/api/layer/${layer.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: newName })
                    });
                }
            });
            nameInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    nameInput.blur();
                }
                e.stopPropagation();
            });
            nameInput.addEventListener('click', (e) => {
                // single click should select, not edit
                e.stopPropagation();
            });
            
            container.appendChild(layerDiv);
        });

        this.updateLayerOrderControls();
    }

    updateLayerOrderControls() {
        const upBtn = document.getElementById('btn-layer-up');
        const downBtn = document.getElementById('btn-layer-down');
        if (!upBtn || !downBtn) return;
        const hasSelection = !!this.currentLayer;
        upBtn.disabled = !hasSelection;
        downBtn.disabled = !hasSelection;
    }

    moveLayerById(layerId, delta) {
        if (!this.project || !this.project.layers) return;
        const displayIds = [...document.querySelectorAll('#layers-list .layer-item')].map(el => parseInt(el.dataset.layerId, 10));
        const idx = displayIds.indexOf(layerId);
        if (idx < 0) return;
        const nextIdx = idx + delta;
        if (nextIdx < 0 || nextIdx >= displayIds.length) return;
        displayIds.splice(nextIdx, 0, displayIds.splice(idx, 1)[0]);
        this.applyDisplayOrder(displayIds, 'Reorder Layers');
    }

    reorderLayersByDrag(draggedId, targetId, insertAfter = false) {
        const displayIds = [...document.querySelectorAll('#layers-list .layer-item')].map(el => parseInt(el.dataset.layerId, 10));
        const from = displayIds.indexOf(draggedId);
        const to = displayIds.indexOf(targetId);
        if (from < 0 || to < 0) return;
        const [moved] = displayIds.splice(from, 1);
        let insertIndex = to;
        if (insertAfter && to >= 0) {
            insertIndex = to + 1;
        }
        if (from < to && insertAfter) {
            insertIndex -= 1;
        }
        displayIds.splice(insertIndex, 0, moved);
        this.applyDisplayOrder(displayIds, 'Reorder Layers');
    }

    applyDisplayOrder(displayIds, historyAction) {
        if (!this.project || !this.project.layers) return;
        const layerMap = new Map(this.project.layers.map(l => [l.id, l]));
        const newDisplay = displayIds.map(id => layerMap.get(id)).filter(Boolean);
        const newOrder = [...newDisplay].reverse();
        sendClientLog('reorder_layers', {
            action: historyAction,
            newOrder: newOrder.map(l => ({ id: l.id, name: l.name }))
        });
        this.saveState(historyAction);
        this.project.layers = newOrder;
        this.updateUI();
        this.saveProject();
    }
    
    saveProject() {
        fetch('/api/project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.project)
        })
        .then(() => {
            document.getElementById('status-message').textContent = 'Project saved';
            setTimeout(() => {
                document.getElementById('status-message').textContent = 'Ready';
            }, 2000);
        });
    }
    
    async saveProjectToFile() {
        // Ensure raster size in project reflects current toolbar/canvas values
        if (window.canvasRenderer && this.project) {
            this.project.raster_width = window.canvasRenderer.rasterWidth;
            this.project.raster_height = window.canvasRenderer.rasterHeight;
        }
        sendClientLog('save_project_file_capabilities', {
            hasSaveFilePicker: this.supportsFilePickerAPIs()
        });
        if (!this.supportsFilePickerAPIs() && !this._warnedNoFilePicker) {
            this._warnedNoFilePicker = true;
            sendClientLog('save_picker_apis_unavailable_warning', {});
        }
        const projectData = JSON.stringify(this.project, null, 2);
        const blob = new Blob([projectData], { type: 'application/json' });
        await this.saveBlobWithPicker(blob, `${this.project.name}.json`, 'application/json');
        
        document.getElementById('status-message').textContent = 'Project saved to file';
        setTimeout(() => {
            document.getElementById('status-message').textContent = 'Ready';
        }, 2000);
    }
    
    loadProjectFromFile() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';
        input.style.display = 'none';
        document.body.appendChild(input);
        sendClientLog('open_file_dialog_requested');
        input.onchange = (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (event) => {
                    try {
                        const projectData = JSON.parse(event.target.result);
                        sendClientLog('load_project_file_start', { name: projectData.name || 'Unnamed', layers: projectData.layers ? projectData.layers.length : 0 });
                        // Prevent previous project's id-based client-props from contaminating
                        // freshly loaded external files.
                        localStorage.removeItem('ledRasterClientProps');
                        this.project = projectData;
                        if (this.project.layers) {
                            this.project.layers.forEach(layer => {
                                this.applyMissingLayerDefaults(layer);
                                this.normalizeLoadedPowerFlowPattern(layer);
                            });
                        }

                        if (projectData.raster_width && projectData.raster_height) {
                            window.canvasRenderer.rasterWidth = projectData.raster_width;
                            window.canvasRenderer.rasterHeight = projectData.raster_height;
                            document.getElementById('toolbar-raster-width').value = projectData.raster_width;
                            document.getElementById('toolbar-raster-height').value = projectData.raster_height;
                            this.saveRasterSize();
                        }

                        // Show locally right away (even if server sync fails)
                        this.currentLayer = this.project.layers ? this.project.layers[0] : null;
                        this.updateUI();
                        this.saveClientSideProperties();
                        window.canvasRenderer.fitToView();

                        fetch('/api/project', {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(this.project)
                        })
                            .then(res => res.json())
                            .then(data => {
                                if (!data || !Array.isArray(data.layers)) {
                                    throw new Error('Invalid project data returned from server');
                                }
                                this.project = data;
                                this.dedupeProjectLayers('load_project_file');
                                if (this.project.layers) {
                                    this.project.layers.forEach(layer => {
                                        this.applyMissingLayerDefaults(layer);
                                        this.normalizeLoadedPowerFlowPattern(layer);
                                    });
                                }
                                this.currentLayer = this.project.layers[0] || null;
                                this.updateUI();
                                this.saveClientSideProperties();
                                window.canvasRenderer.fitToView();
                                // Push all layers to server so client-side properties
                                // (showDataFlowPortInfo, showPowerCircuitInfo, computed power/capacity)
                                // are synced for every layer, not just the selected one.
                                this.updateLayers(this.project.layers, false, 'File Load Sync');
                                this.resetHistory('Initial State');
                                document.getElementById('status-message').textContent = 'Project loaded';
                                setTimeout(() => {
                                    document.getElementById('status-message').textContent = 'Ready';
                                }, 2000);
                                sendClientLog('load_project_file_success', { name: this.project.name, layers: this.project.layers ? this.project.layers.length : 0 });
                            })
                            .catch((err) => {
                                sendClientLog('load_project_file_error', { message: err.message });
                                this.resetHistory('Initial State');
                                document.getElementById('status-message').textContent = 'Project loaded (server sync failed)';
                                setTimeout(() => {
                                    document.getElementById('status-message').textContent = 'Ready';
                                }, 2000);
                            });
                    } catch (error) {
                        sendClientLog('load_project_file_error', { message: error.message });
                        alert('Error loading project file: ' + error.message);
                    }
                };
                reader.readAsText(file);
            } else {
                sendClientLog('open_file_dialog_cancelled');
            }
            if (input.parentNode) input.parentNode.removeChild(input);
        };
        input.click();
    }

    applyMissingLayerDefaults(layer) {
        if (layer.locked === undefined) layer.locked = false;
        if (layer.powerVoltage === undefined) layer.powerVoltage = 110;
        if (layer.powerVoltageCustom === undefined) layer.powerVoltageCustom = layer.powerVoltage;
        if (layer.powerAmperage === undefined) layer.powerAmperage = 15;
        if (layer.powerAmperageCustom === undefined) layer.powerAmperageCustom = layer.powerAmperage;
        if (layer.panelWatts === undefined) layer.panelWatts = 200;
        if (layer.powerMaximize === undefined) layer.powerMaximize = false;
        if (layer.powerOrganized === undefined) layer.powerOrganized = true;
        if (layer.powerCustomPath === undefined) layer.powerCustomPath = false;
        if (!layer.powerFlowPattern) layer.powerFlowPattern = layer.flowPattern || 'tl-h';
        if (layer.powerLineWidth === undefined) layer.powerLineWidth = 8;
        if (!layer.powerLineColor) layer.powerLineColor = '#FF0000';
        if (!layer.powerArrowColor) layer.powerArrowColor = '#0042AA';
        if (layer.powerRandomColors === undefined) layer.powerRandomColors = false;
        if (layer.powerColorCodedView === undefined) layer.powerColorCodedView = false;
        layer.powerCircuitColors = this.normalizePowerCircuitColors(layer.powerCircuitColors);
        if (layer.powerLabelSize === undefined) layer.powerLabelSize = 14;
        if (!layer.powerLabelBgColor) layer.powerLabelBgColor = '#D95000';
        if (!layer.powerLabelTextColor) layer.powerLabelTextColor = '#000000';
        if (!layer.powerLabelTemplate) layer.powerLabelTemplate = 'S1-#';
        if (!layer.powerLabelOverrides) layer.powerLabelOverrides = {};
        if (!layer.powerCustomPaths) layer.powerCustomPaths = {};
        if (layer.powerCustomIndex === undefined) layer.powerCustomIndex = 1;
        if (!layer.primaryTextColor) layer.primaryTextColor = '#000000';
        if (!layer.backupTextColor) layer.backupTextColor = '#FFFFFF';
        if (!layer.border_color_pixel) layer.border_color_pixel = layer.border_color || '#ffffff';
        if (!layer.border_color_cabinet) layer.border_color_cabinet = layer.border_color || '#ffffff';
        if (!layer.border_color_data) layer.border_color_data = layer.border_color || '#ffffff';
        if (!layer.border_color_power) layer.border_color_power = layer.border_color || '#ffffff';
        // Computed/transient fields should never be trusted from file payload
        delete layer._powerError;
        delete layer._powerCircuits;
        delete layer._powerTotalAmps1;
        delete layer._powerTotalAmps3;
        delete layer._powerCircuitsRequired;
        delete layer._capacityError;
        delete layer._autoPortsRequired;
        delete layer._portsRequired;
    }

    normalizeLoadedPowerFlowPattern(layer) {
        if (!layer || !Array.isArray(layer.panels) || layer.panels.length === 0) return;
        if (!layer.flowPattern || !layer.powerFlowPattern) return;
        if (layer.powerFlowPattern === 'custom') return;
        if (layer.powerFlowPattern === layer.flowPattern) return;

        const originalPattern = layer.powerFlowPattern;
        const current = this.calculatePowerAssignments(layer);
        if (!current || !current.error) return;

        layer.powerFlowPattern = layer.flowPattern;
        const migrated = this.calculatePowerAssignments(layer);
        if (migrated && !migrated.error) {
            sendClientLog('loaded_power_pattern_migrated', {
                layerId: layer.id,
                from: originalPattern,
                to: layer.flowPattern
            });
            return;
        }

        layer.powerFlowPattern = originalPattern;
    }
    
    renameLayer(layer, nameElement) {
        const currentName = layer.name;
        let renameFinished = false;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = currentName;
        input.className = 'layer-name-input';
        input.style.cssText = 'background: #1a1a1a; border: 1px solid #4A90E2; color: #e0e0e0; padding: 2px 4px; border-radius: 3px; font-size: 13px; font-weight: 600; width: 100%;';
        
        nameElement.textContent = '';
        nameElement.appendChild(input);
        input.focus();
        input.select();
        
        const finishRename = () => {
            if (renameFinished) return;
            renameFinished = true;
            const newName = input.value.trim() || currentName;
            layer.name = newName;

            if (newName !== currentName) {
                this.saveState('Rename Layer');
                if (typeof sendClientLog === 'function') {
                    sendClientLog('rename_layer', { id: layer.id, from: currentName, to: newName });
                }
            }
            
            fetch(`/api/layer/${layer.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            })
            .then(() => {
                this.renderLayers();
            });
        };
        
        input.addEventListener('blur', finishRename);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                finishRename();
            } else if (e.key === 'Escape') {
                layer.name = currentName;
                this.renderLayers();
            }
        });
    }
    
    // ===== HISTORY SYSTEM =====
    resetHistory(initialAction = 'Initial State') {
        this.history = [];
        this.historyIndex = -1;
        this.saveState(initialAction);
        sendClientLog('history_reset', { action: initialAction });
    }
    
    saveState(action) {
        // Save current project state
        const state = {
            action: action,
            project: JSON.parse(JSON.stringify(this.project)),
            timestamp: Date.now()
        };
        
        
        // Remove any future states if we're not at the end
        if (this.historyIndex < this.history.length - 1) {
            this.history = this.history.slice(0, this.historyIndex + 1);
        }
        
        // Add new state
        this.history.push(state);
        
        // Limit history size
        if (this.history.length > this.maxHistory) {
            this.history.shift();
        } else {
            this.historyIndex++;
        }
        sendClientLog('save_state', {
            action,
            historyIndex: this.historyIndex,
            historyLength: this.history.length,
            layers: this.project.layers ? this.project.layers.length : 0,
            tab: window.canvasRenderer ? window.canvasRenderer.viewMode : '?',
            selectedLayers: this.selectedLayerIds ? [...this.selectedLayerIds] : [],
            currentLayerId: this.currentLayer ? this.currentLayer.id : null
        });
        
    }
    
    undo() {
        
        if (this.historyIndex > 0) {
            this.historyIndex--;
            const state = this.history[this.historyIndex];
            
            
            this.project = JSON.parse(JSON.stringify(state.project));
            this.dedupeProjectLayers('undo_restore');
            sendClientLog('undo', {
                action: state.action,
                historyIndex: this.historyIndex,
                historyLength: this.history.length,
                layers: this.project.layers ? this.project.layers.length : 0,
                layerNames: this.project.layers ? this.project.layers.map(l => l.name) : []
            });
            
            // Update current layer reference
            if (this.currentLayer) {
                this.currentLayer = this.project.layers.find(l => l.id === this.currentLayer.id) || null;
            }
            this.updateCustomFlowUI();
            
            // Sync the restored state to the backend
            fetch('/api/project', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.project)
            })
            .then(response => {
                return response.json();
            })
            .then(() => {
                this.updateUI();
            })
            .catch(error => {
                console.error('Undo backend sync failed:', error);
            });
        } else {
        }
    }
    
    redo() {
        
        if (this.historyIndex < this.history.length - 1) {
            this.historyIndex++;
            const state = this.history[this.historyIndex];
            
            
            this.project = JSON.parse(JSON.stringify(state.project));
            this.dedupeProjectLayers('redo_restore');
            sendClientLog('redo', {
                action: state.action,
                historyIndex: this.historyIndex,
                historyLength: this.history.length,
                layers: this.project.layers ? this.project.layers.length : 0,
                layerNames: this.project.layers ? this.project.layers.map(l => l.name) : []
            });
            
            // Update current layer reference
            if (this.currentLayer) {
                this.currentLayer = this.project.layers.find(l => l.id === this.currentLayer.id) || null;
            }
            this.updateCustomFlowUI();
            
            // Sync the restored state to the backend
            fetch('/api/project', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.project)
            })
            .then(response => {
                return response.json();
            })
            .then(() => {
                this.updateUI();
            })
            .catch(error => {
                console.error('Redo backend sync failed:', error);
            });
        } else {
        }
    }
    
    // ===== DELETE LAYER =====
    
    deleteCurrentLayer() {
        
        if (!this.currentLayer || this.deletionInProgress) {
            return;
        }
        
        // Collect all selected layer IDs to delete
        const idsToDelete = this.selectedLayerIds && this.selectedLayerIds.size > 1
            ? [...this.selectedLayerIds]
            : [this.currentLayer.id];
        
        // Don't delete if it would remove ALL layers
        if (idsToDelete.length >= this.project.layers.length) {
            // Keep at least one layer
            if (this.project.layers.length <= 1) return;
            idsToDelete.pop(); // Remove last one from delete list to keep it
        }
        
        this.deletionInProgress = true;
        this.saveState('Delete Layer');
        
        // Find index of current layer for post-delete selection
        const currentIndex = this.project.layers.findIndex(l => l.id === this.currentLayer.id);
        this.currentLayer = null;
        
        // Delete all selected layers sequentially
        const deleteNext = (ids) => {
            if (ids.length === 0) {
                // All deletes done - refresh project
                fetch('/api/project')
                    .then(res => res.json())
                    .then(project => {
                        this.project = project;
                        this.dedupeProjectLayers('delete_layer');
                        
                        if (this.project.layers.length > 0) {
                            const newIndex = Math.min(currentIndex, this.project.layers.length - 1);
                            this.currentLayer = this.project.layers[newIndex];
                            this.selectedLayerIds = new Set([this.currentLayer.id]);
                            this.lastSelectedLayerId = this.currentLayer.id;
                            this.selectionAnchorLayerId = this.currentLayer.id;
                        } else {
                            this.currentLayer = null;
                            this.selectedLayerIds = new Set();
                            this.lastSelectedLayerId = null;
                            this.selectionAnchorLayerId = null;
                        }
                        
                        this.updateUI();
                    })
                    .finally(() => {
                        this.deletionInProgress = false;
                    });
                return;
            }
            
            const id = ids.shift();
            sendClientLog('delete_layer', { id: id, name: (this.project.layers.find(l => l.id === id) || {}).name });
            
            fetch(`/api/layer/${id}`, { method: 'DELETE' })
                .then(res => res.json())
                .then(project => {
                    this.project = project;
                    deleteNext(ids);
                })
                .catch(error => {
                    console.error('DELETE failed:', error);
                    deleteNext(ids); // Continue with remaining deletes
                });
        };
        
        deleteNext([...idsToDelete]);
    }
    
    // ===== DUPLICATE LAYER =====
    
    duplicateLayer(layer) {
        // Smart name incrementing
        const getNextName = (baseName) => {
            // Check if name ends with a number
            const match = baseName.match(/^(.*?)(\d+)$/);
            
            if (match) {
                // Name ends with number (e.g., "Screen1" or "Nvidia12")
                const base = match[1];
                const num = parseInt(match[2]);
                return `${base}${num + 1}`;
            } else {
                // Name doesn't end with number (e.g., "Nvidia")
                return `${baseName} 1`;
            }
        };

        if ((layer.type || 'screen') === 'image') {
            const duplicateData = {
                name: getNextName(layer.name),
                imageData: layer.imageData,
                imageWidth: layer.imageWidth,
                imageHeight: layer.imageHeight,
                imageScale: layer.imageScale || 1.0,
                offset_x: layer.offset_x + 50,
                offset_y: layer.offset_y + 50
            };
            fetch('/api/layer/add-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(duplicateData)
            })
            .then(res => res.json())
            .then(newLayer => {
                this.upsertProjectLayer(newLayer);
                this.selectLayer(newLayer);
                this.updateUI();
                this.saveState('Duplicate Image Layer');
            });
            return;
        }
        
        // Collect hidden panel positions (row, col) to apply to new layer
        const hiddenPanels = layer.panels
            .filter(p => p.hidden)
            .map(p => ({ row: p.row, col: p.col }));
        
        const duplicateData = {
            name: getNextName(layer.name),
            columns: layer.columns,
            rows: layer.rows,
            cabinet_width: layer.cabinet_width,
            cabinet_height: layer.cabinet_height,
            offset_x: layer.offset_x + 50, // Offset by 50px
            offset_y: layer.offset_y + 50,
            color1: layer.color1,
            color2: layer.color2,
            panel_width_mm: layer.panel_width_mm,
            panel_height_mm: layer.panel_height_mm,
            panel_weight: layer.panel_weight,
            weight_unit: layer.weight_unit,
            halfFirstColumn: !!layer.halfFirstColumn,
            halfLastColumn: !!layer.halfLastColumn,
            halfFirstRow: !!layer.halfFirstRow,
            halfLastRow: !!layer.halfLastRow,
            show_numbers: layer.show_numbers,
            number_size: layer.number_size,
            show_panel_borders: layer.show_panel_borders,
            show_circle_with_x: layer.show_circle_with_x,
            border_color: layer.border_color,
            border_width: layer.border_width,
            cabinetIdStyle: layer.cabinetIdStyle,
            cabinetIdPosition: layer.cabinetIdPosition,
            cabinetIdColor: layer.cabinetIdColor,
            showLabelName: layer.showLabelName,
            showLabelSizePx: layer.showLabelSizePx,
            showLabelSizeM: layer.showLabelSizeM,
            showLabelSizeFt: layer.showLabelSizeFt,
            showLabelWeight: layer.showLabelWeight,
            showLabelInfo: layer.showLabelInfo,
            labelsColor: layer.labelsColor,
            labelsFontSize: layer.labelsFontSize,
            infoLabelSize: layer.infoLabelSize,
            showPowerCircuitInfo: !!layer.showPowerCircuitInfo,
            showOffsetTL: layer.showOffsetTL,
            showOffsetTR: layer.showOffsetTR,
            showOffsetBL: layer.showOffsetBL,
            showOffsetBR: layer.showOffsetBR,
            powerVoltage: layer.powerVoltage,
            powerVoltageCustom: layer.powerVoltageCustom,
            powerAmperage: layer.powerAmperage,
            powerAmperageCustom: layer.powerAmperageCustom,
            panelWatts: layer.panelWatts,
            powerMaximize: !!layer.powerMaximize,
            powerOrganized: !!layer.powerOrganized,
            powerCustomPath: !!layer.powerCustomPath,
            powerFlowPattern: layer.powerFlowPattern,
            powerLineWidth: layer.powerLineWidth,
            powerLineColor: layer.powerLineColor,
            powerArrowColor: layer.powerArrowColor,
            powerRandomColors: !!layer.powerRandomColors,
            powerColorCodedView: !!layer.powerColorCodedView,
            powerCircuitColors: JSON.parse(JSON.stringify(layer.powerCircuitColors || {})),
            powerLabelSize: layer.powerLabelSize,
            powerLabelBgColor: layer.powerLabelBgColor,
            powerLabelTextColor: layer.powerLabelTextColor,
            powerLabelTemplate: layer.powerLabelTemplate,
            powerLabelOverrides: JSON.parse(JSON.stringify(layer.powerLabelOverrides || {})),
            powerCustomPaths: JSON.parse(JSON.stringify(layer.powerCustomPaths || {})),
            powerCustomIndex: layer.powerCustomIndex,
            hiddenPanels: hiddenPanels  // Pass hidden panel info
        };
        
        // Store client-side properties to copy after layer is created
        const clientProps = {
            arrowLineWidth: layer.arrowLineWidth,
            arrowColor: layer.arrowColor,
            dataFlowColor: layer.dataFlowColor,
            dataFlowLabelSize: layer.dataFlowLabelSize,
            primaryColor: layer.primaryColor,
            primaryTextColor: layer.primaryTextColor,
            backupColor: layer.backupColor,
            backupTextColor: layer.backupTextColor,
            flowPattern: layer.flowPattern,
            bitDepth: layer.bitDepth,
            frameRate: layer.frameRate,
            processorType: layer.processorType,
            portMappingMode: layer.portMappingMode,
            screenNameSizeCabinet: layer.screenNameSizeCabinet,
            screenNameSizeDataFlow: layer.screenNameSizeDataFlow,
            screenNameSizePower: layer.screenNameSizePower,
            screenNameOffsetXCabinet: layer.screenNameOffsetXCabinet,
            screenNameOffsetYCabinet: layer.screenNameOffsetYCabinet,
            screenNameOffsetXDataFlow: layer.screenNameOffsetXDataFlow,
            screenNameOffsetYDataFlow: layer.screenNameOffsetYDataFlow,
            screenNameOffsetXPower: layer.screenNameOffsetXPower,
            screenNameOffsetYPower: layer.screenNameOffsetYPower,
            border_color_pixel: layer.border_color_pixel,
            border_color_cabinet: layer.border_color_cabinet,
            border_color_data: layer.border_color_data,
            border_color_power: layer.border_color_power,
            powerLabelBgColor: layer.powerLabelBgColor,
            powerLabelTextColor: layer.powerLabelTextColor,
            powerVoltage: layer.powerVoltage,
            powerVoltageCustom: layer.powerVoltageCustom,
            powerAmperage: layer.powerAmperage,
            powerAmperageCustom: layer.powerAmperageCustom,
            panelWatts: layer.panelWatts,
            powerMaximize: layer.powerMaximize,
            powerOrganized: layer.powerOrganized,
            powerCustomPath: layer.powerCustomPath,
            powerFlowPattern: layer.powerFlowPattern,
            powerLineWidth: layer.powerLineWidth,
            powerLineColor: layer.powerLineColor,
            powerArrowColor: layer.powerArrowColor,
            powerRandomColors: layer.powerRandomColors,
            powerColorCodedView: layer.powerColorCodedView,
            powerCircuitColors: JSON.parse(JSON.stringify(layer.powerCircuitColors || {})),
            powerLabelSize: layer.powerLabelSize,
            powerLabelTemplate: layer.powerLabelTemplate,
            powerLabelOverrides: JSON.parse(JSON.stringify(layer.powerLabelOverrides || {})),
            powerCustomPaths: JSON.parse(JSON.stringify(layer.powerCustomPaths || {})),
            powerCustomIndex: layer.powerCustomIndex,
            showPowerCircuitInfo: !!layer.showPowerCircuitInfo,
            showDataFlowPortInfo: !!layer.showDataFlowPortInfo,
            weight_unit: layer.weight_unit,
            panel_weight: layer.panel_weight,
            infoLabelSize: layer.infoLabelSize,
            portLabelTemplatePrimary: layer.portLabelTemplatePrimary,
            portLabelTemplateReturn: layer.portLabelTemplateReturn,
            portLabelOverridesPrimary: JSON.parse(JSON.stringify(layer.portLabelOverridesPrimary || {})),
            portLabelOverridesReturn: JSON.parse(JSON.stringify(layer.portLabelOverridesReturn || {})),
            customPortPaths: JSON.parse(JSON.stringify(layer.customPortPaths || {})),
            customPortIndex: layer.customPortIndex,
            randomDataColors: !!layer.randomDataColors,
            arrowSize: layer.arrowSize
        };

        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(duplicateData)
        })
        .then(res => res.json())
        .then(newLayer => {
            // Copy client-side properties to new layer
            Object.assign(newLayer, clientProps);
            
            sendClientLog('duplicate_layer', {
                sourceId: layer.id, sourceName: layer.name,
                newId: newLayer.id, newName: newLayer.name,
                columns: newLayer.columns, rows: newLayer.rows,
                offset_x: newLayer.offset_x, offset_y: newLayer.offset_y
            });
            
            this.upsertProjectLayer(newLayer);
            this.selectLayer(newLayer);
            this.updateUI();
            
            // Save client-side properties
            this.saveClientSideProperties();
            
            // Save state AFTER duplicate completes
            this.saveState('Duplicate Layer');
        });
    }
    
    // ===== COPY/PASTE =====
    
    copyLayer() {
        if (!this.currentLayer) return;
        
        this.clipboard = JSON.parse(JSON.stringify(this.currentLayer));
        sendClientLog('copy_layer', {
            id: this.currentLayer.id,
            name: this.currentLayer.name,
            type: this.currentLayer.type || 'screen'
        });
    }
    
    pasteLayer() {
        if (!this.clipboard) return;
        
        // Smart name incrementing (same logic as duplicate)
        const getNextName = (baseName) => {
            const match = baseName.match(/^(.*?)(\d+)$/);
            if (match) {
                const base = match[1];
                const num = parseInt(match[2]);
                return `${base}${num + 1}`;
            } else {
                return `${baseName} 1`;
            }
        };
        
        if ((this.clipboard.type || 'screen') === 'image') {
            const pasteData = {
                name: getNextName(this.clipboard.name),
                imageData: this.clipboard.imageData,
                imageWidth: this.clipboard.imageWidth,
                imageHeight: this.clipboard.imageHeight,
                imageScale: this.clipboard.imageScale || 1.0,
                offset_x: (this.clipboard.offset_x || 0) + 50,
                offset_y: (this.clipboard.offset_y || 0) + 50
            };
            fetch('/api/layer/add-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pasteData)
            })
            .then(res => res.json())
            .then(newLayer => {
                this.upsertProjectLayer(newLayer);
                this.selectLayer(newLayer);
                this.updateUI();
                this.saveState('Paste Image Layer');
            });
            return;
        }

        const pasteData = {
            name: getNextName(this.clipboard.name),
            columns: this.clipboard.columns,
            rows: this.clipboard.rows,
            cabinet_width: this.clipboard.cabinet_width,
            cabinet_height: this.clipboard.cabinet_height,
            offset_x: this.clipboard.offset_x + 50,
            offset_y: this.clipboard.offset_y + 50,
            color1: this.clipboard.color1,
            color2: this.clipboard.color2,
            panel_width_mm: this.clipboard.panel_width_mm,
            panel_height_mm: this.clipboard.panel_height_mm,
            panel_weight: this.clipboard.panel_weight,
            weight_unit: this.clipboard.weight_unit,
            halfFirstColumn: !!this.clipboard.halfFirstColumn,
            halfLastColumn: !!this.clipboard.halfLastColumn,
            halfFirstRow: !!this.clipboard.halfFirstRow,
            halfLastRow: !!this.clipboard.halfLastRow,
            show_numbers: this.clipboard.show_numbers,
            number_size: this.clipboard.number_size,
            show_panel_borders: this.clipboard.show_panel_borders,
            show_circle_with_x: this.clipboard.show_circle_with_x,
            border_color: this.clipboard.border_color,
            cabinetIdStyle: this.clipboard.cabinetIdStyle,
            cabinetIdPosition: this.clipboard.cabinetIdPosition,
            cabinetIdColor: this.clipboard.cabinetIdColor,
            showLabelName: this.clipboard.showLabelName,
            showLabelSizePx: this.clipboard.showLabelSizePx,
            showLabelSizeM: this.clipboard.showLabelSizeM,
            showLabelSizeFt: this.clipboard.showLabelSizeFt,
            showLabelWeight: this.clipboard.showLabelWeight,
            showLabelInfo: this.clipboard.showLabelInfo,
            labelsColor: this.clipboard.labelsColor,
            labelsFontSize: this.clipboard.labelsFontSize,
            infoLabelSize: this.clipboard.infoLabelSize,
            showPowerCircuitInfo: !!this.clipboard.showPowerCircuitInfo,
            showOffsetTL: this.clipboard.showOffsetTL,
            showOffsetTR: this.clipboard.showOffsetTR,
            showOffsetBL: this.clipboard.showOffsetBL,
            showOffsetBR: this.clipboard.showOffsetBR,
            powerVoltage: this.clipboard.powerVoltage,
            powerVoltageCustom: this.clipboard.powerVoltageCustom,
            powerAmperage: this.clipboard.powerAmperage,
            powerAmperageCustom: this.clipboard.powerAmperageCustom,
            panelWatts: this.clipboard.panelWatts,
            powerMaximize: !!this.clipboard.powerMaximize,
            powerOrganized: !!this.clipboard.powerOrganized,
            powerCustomPath: !!this.clipboard.powerCustomPath,
            powerFlowPattern: this.clipboard.powerFlowPattern,
            powerLineWidth: this.clipboard.powerLineWidth,
            powerLineColor: this.clipboard.powerLineColor,
            powerArrowColor: this.clipboard.powerArrowColor,
            powerRandomColors: !!this.clipboard.powerRandomColors,
            powerColorCodedView: !!this.clipboard.powerColorCodedView,
            powerCircuitColors: JSON.parse(JSON.stringify(this.clipboard.powerCircuitColors || {})),
            powerLabelSize: this.clipboard.powerLabelSize,
            powerLabelBgColor: this.clipboard.powerLabelBgColor,
            powerLabelTextColor: this.clipboard.powerLabelTextColor,
            powerLabelTemplate: this.clipboard.powerLabelTemplate,
            powerLabelOverrides: JSON.parse(JSON.stringify(this.clipboard.powerLabelOverrides || {})),
            powerCustomPaths: JSON.parse(JSON.stringify(this.clipboard.powerCustomPaths || {})),
            powerCustomIndex: this.clipboard.powerCustomIndex,
            showDataFlowPortInfo: !!this.clipboard.showDataFlowPortInfo,
            portLabelTemplatePrimary: this.clipboard.portLabelTemplatePrimary,
            portLabelTemplateReturn: this.clipboard.portLabelTemplateReturn,
            portLabelOverridesPrimary: JSON.parse(JSON.stringify(this.clipboard.portLabelOverridesPrimary || {})),
            portLabelOverridesReturn: JSON.parse(JSON.stringify(this.clipboard.portLabelOverridesReturn || {})),
            customPortPaths: JSON.parse(JSON.stringify(this.clipboard.customPortPaths || {})),
            customPortIndex: this.clipboard.customPortIndex,
            randomDataColors: !!this.clipboard.randomDataColors,
            arrowSize: this.clipboard.arrowSize
        };
        const pasteClientProps = {
            border_color_pixel: this.clipboard.border_color_pixel,
            border_color_cabinet: this.clipboard.border_color_cabinet,
            border_color_data: this.clipboard.border_color_data,
            border_color_power: this.clipboard.border_color_power,
            primaryTextColor: this.clipboard.primaryTextColor,
            backupTextColor: this.clipboard.backupTextColor,
            powerLabelBgColor: this.clipboard.powerLabelBgColor,
            powerLabelTextColor: this.clipboard.powerLabelTextColor
        };
        
        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pasteData)
        })
        .then(res => res.json())
        .then(newLayer => {
            Object.assign(newLayer, pasteClientProps);
            sendClientLog('paste_layer', {
                sourceId: this.clipboard.id, sourceName: this.clipboard.name,
                newId: newLayer.id, newName: newLayer.name,
                columns: newLayer.columns, rows: newLayer.rows,
                offset_x: newLayer.offset_x, offset_y: newLayer.offset_y
            });
            this.upsertProjectLayer(newLayer);
            this.selectLayer(newLayer);
            this.updateUI();
            
            // Save state AFTER paste completes
            this.saveState('Paste Layer');
        });
    }
    
    hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 255, g: 0, b: 0 };
    }
    
    rgbToHex(r, g, b) {
        return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    registerGlobalClientLogging();
    sendClientLog('client_ready', { ua: navigator.userAgent });
    window.app = new LEDRasterApp();
});
