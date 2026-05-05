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
    // Always update the current callbacks so re-opens target the right color
    colorPickerState.popoverOnPick = onPick;
    colorPickerState.popoverOnShowColors = onShowColors;

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
                    if (color && colorPickerState.popoverOnPick) {
                        colorPickerState.popoverOnPick(color);
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
            if (colorPickerState.popoverOnShowColors) colorPickerState.popoverOnShowColors();
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

function hexToRgbLocal(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : { r: 255, g: 0, b: 0 };
}

function openColorModal(onPick) {
    // Always update the current callback so re-opens target the right color
    colorPickerState.modalOnPick = onPick;

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
                        if (colorPickerState.modalOnPick) colorPickerState.modalOnPick(result.sRGBHex);
                        currentSwatch.style.background = result.sRGBHex;
                    }
                    return;
                } catch (e) {
                    // user cancelled
                    return;
                }
            }
            startCanvasEyedropper(colorPickerState.modalOnPick, currentSwatch);
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

        // Make the color modal draggable by its header
        header.style.cursor = 'grab';
        let dragOffsetX = 0, dragOffsetY = 0, isDragging = false;
        header.addEventListener('mousedown', (e) => {
            if (e.target === close) return; // don't drag when clicking close
            isDragging = true;
            header.style.cursor = 'grabbing';
            const rect = modal.getBoundingClientRect();
            dragOffsetX = e.clientX - rect.left;
            dragOffsetY = e.clientY - rect.top;
            e.preventDefault();
        });
        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            // Remove centering transform, use absolute positioning
            modal.style.transform = 'none';
            modal.style.left = `${e.clientX - dragOffsetX}px`;
            modal.style.top = `${e.clientY - dragOffsetY}px`;
        });
        document.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                header.style.cursor = 'grab';
            }
        });

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

        const updateColorUI = (hex) => {
            if (!hex) return;
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

        const setColorFromHex = (hex) => {
            if (!hex) return;
            if (colorPickerState.modalOnPick) colorPickerState.modalOnPick(hex);
            pushRecentColor(hex);
            renderRecentSwatches();
            updateColorUI(hex);
        };

        // Selection marker state
        let markerX = -1, markerY = -1;
        const drawMarker = () => {
            // Redraw wheel then overlay marker
            drawHueWheel(colorPickerState.wheelCtx, wheel.width, wheel.height);
            if (markerX >= 0 && markerY >= 0) {
                const ctx = colorPickerState.wheelCtx;
                ctx.beginPath();
                ctx.arc(markerX, markerY, 8, 0, 2 * Math.PI);
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(markerX, markerY, 9.5, 0, 2 * Math.PI);
                ctx.strokeStyle = '#000000';
                ctx.lineWidth = 1;
                ctx.stroke();
            }
        };

        const pickFromWheel = (e) => {
            const rect = wheel.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            // Check if within wheel radius
            const cx = wheel.width / 2, cy = wheel.height / 2;
            const r = Math.min(cx, cy) - 2;
            const dx = x - cx, dy = y - cy;
            if (Math.sqrt(dx * dx + dy * dy) > r) return;
            // Redraw clean wheel first so we read the actual color, not the marker
            drawHueWheel(colorPickerState.wheelCtx, wheel.width, wheel.height);
            const color = getWheelColor(colorPickerState.wheelCtx, x, y, parseInt(slider.value, 10) / 100);
            if (color) {
                markerX = x;
                markerY = y;
                drawMarker();
                setColorFromHex(color);
            }
        };

        let dragging = false;
        wheel.addEventListener('mousedown', (e) => { dragging = true; pickFromWheel(e); });
        window.addEventListener('mousemove', (e) => { if (dragging) pickFromWheel(e); });
        window.addEventListener('mouseup', () => { dragging = false; });
        slider.addEventListener('input', () => {
            if (markerX >= 0 && markerY >= 0) {
                // Re-pick color at current marker position with new brightness
                drawHueWheel(colorPickerState.wheelCtx, wheel.width, wheel.height);
                const color = getWheelColor(colorPickerState.wheelCtx, markerX, markerY, parseInt(slider.value, 10) / 100);
                if (color) {
                    setColorFromHex(color);
                }
                drawMarker();
            }
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
        // Make color modal draggable by its header
        header.style.cursor = 'move';
        header.addEventListener('mousedown', (e) => {
            if (e.target === close) return;
            const rect = modal.getBoundingClientRect();
            const dragOffsetX = e.clientX - rect.left;
            const dragOffsetY = e.clientY - rect.top;
            const onMove = (ev) => {
                modal.style.left = (ev.clientX - dragOffsetX) + 'px';
                modal.style.top = (ev.clientY - dragOffsetY) + 'px';
                modal.style.transform = 'none';
            };
            const onUp = () => {
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
            e.preventDefault();
        });
        updateColorUI(colorPickerState.recent[0] || '#FFFFFF');
    }

    renderRecentSwatches();
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

function renderRecentSwatches() {
    const container = colorPickerState.modal?.querySelector('.recent-swatches');
    if (!container) return;
    container.innerHTML = '';
    colorPickerState.recent.forEach(color => {
        const sw = document.createElement('div');
        sw.className = 'recent-swatch';
        sw.style.background = color;
        sw.addEventListener('click', () => {
            if (colorPickerState.modalOnPick) colorPickerState.modalOnPick(color);
        });
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
        // Pixel Map bulk-select: drag-select panels of the current layer to
        // bulk-toggle blank or half-tile state. Set of "row,col" strings.
        this.pixelMapSelection = new Set();
        
        // Undo/Redo system
        this.history = [];
        this.historyIndex = -1;
        this.maxHistory = 50;
        this._saveStateTimer = null;
        this._pendingSaveAction = null;
        
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

        // Restore collapsed sidebar state before anything paints so there's
        // no flash of the open panel.
        this.initSidebarToggles();

        // Check server session FIRST - if server restarted, clear localStorage
        this.checkServerSession().then(() => {
            this.connectWebSocket();
            this.loadProject();
            this.setupEventListeners();
            sendClientLog('app_init', { ua: navigator.userAgent });
            // Background-check upstream panel catalog after the rest of boot
            // settles so we don't slow first paint. Failure is silent.
            setTimeout(() => this.checkPanelCatalogUpdate(), 1500);
        });
    }

    /**
     * Wire the left/right sidebar collapse toggles. Each side is independent
     * and the collapsed state persists in localStorage so the panel stays
     * the way the user left it across reloads. The toggle button is
     * positioned dynamically against the sidebar's actual geometry (via
     * getBoundingClientRect), so it always sits flush with the sidebar's
     * inner edge regardless of monitor size, sidebar width, or window
     * resize. ResizeObserver keeps it pinned in place if the sidebar's
     * dimensions ever change at runtime.
     */
    initSidebarToggles() {
        const sides = [
            { key: 'left', sidebarId: 'left-sidebar', toggleId: 'left-sidebar-toggle', expandSym: '›', collapseSym: '‹' },
            { key: 'right', sidebarId: 'right-sidebar', toggleId: 'right-sidebar-toggle', expandSym: '‹', collapseSym: '›' },
        ];
        sides.forEach(({ key, sidebarId, toggleId, expandSym, collapseSym }) => {
            const sidebar = document.getElementById(sidebarId);
            const btn = document.getElementById(toggleId);
            if (!sidebar || !btn) return;
            const storageKey = `ledRasterSidebarCollapsed_${key}`;
            const positionToggle = () => {
                const rect = sidebar.getBoundingClientRect();
                if (key === 'left') {
                    btn.style.left = `${Math.round(rect.right)}px`;
                    btn.style.right = '';
                } else {
                    btn.style.right = `${Math.round(window.innerWidth - rect.left)}px`;
                    btn.style.left = '';
                }
            };
            const resizeCanvas = () => {
                if (!window.canvasRenderer) return;
                if (window.canvasRenderer.setupCanvas) window.canvasRenderer.setupCanvas();
                window.canvasRenderer.render();
            };
            const apply = (collapsed) => {
                sidebar.classList.toggle('collapsed', collapsed);
                document.body.classList.toggle(`${key}-sidebar-collapsed`, collapsed);
                btn.textContent = collapsed ? expandSym : collapseSym;
                btn.title = collapsed
                    ? `Expand ${key} panel`
                    : `Collapse ${key} panel`;
                // The CSS width transition runs ~180ms. Reposition the
                // toggle and resize the canvas at multiple points during /
                // after the animation so the canvas always fills the
                // available wrapper width, otherwise the canvas keeps its
                // pre-collapse pixel dimensions and the user sees a black
                // strip on the side where the sidebar used to be.
                requestAnimationFrame(() => { positionToggle(); resizeCanvas(); });
                setTimeout(() => { positionToggle(); resizeCanvas(); }, 60);
                setTimeout(() => { positionToggle(); resizeCanvas(); }, 220);
            };
            const saved = localStorage.getItem(storageKey) === '1';
            apply(saved);
            btn.addEventListener('click', () => {
                const nowCollapsed = !sidebar.classList.contains('collapsed');
                localStorage.setItem(storageKey, nowCollapsed ? '1' : '0');
                apply(nowCollapsed);
                if (typeof sendClientLog === 'function') {
                    sendClientLog('sidebar_toggle', { side: key, collapsed: nowCollapsed });
                }
            });
            // Keep the toggle pinned to the sidebar edge whenever the
            // sidebar resizes (window resize, scrollbar appearance, etc.).
            if (typeof ResizeObserver === 'function') {
                new ResizeObserver(positionToggle).observe(sidebar);
            }
            window.addEventListener('resize', positionToggle);
        });
    }
    
    // Check if server has restarted - if so, clear localStorage
    // Also fetch server-side preferences so all clients share the same config
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

        // Fetch server-side preferences (shared across all clients)
        try {
            const prefResp = await fetch('/api/preferences');
            const serverPrefs = await prefResp.json();
            if (serverPrefs && Object.keys(serverPrefs).length > 0) {
                // Server has preferences, use them (overrides localStorage)
                this._serverPreferences = serverPrefs;
                console.log('Loaded server-side preferences:', Object.keys(serverPrefs));
            } else {
                // No server prefs yet, seed from localStorage if available
                const localPrefs = this.getLocalPreferences();
                if (Object.keys(localPrefs).length > 0) {
                    this._serverPreferences = localPrefs;
                    // Push local prefs to server so other clients pick them up
                    fetch('/api/preferences', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(localPrefs)
                    });
                    console.log('Seeded server preferences from localStorage');
                }
            }
        } catch (e) {
            console.error('Error fetching server preferences:', e);
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
                this.syncRasterFromProject();
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
            // On reconnect (after sleep), skip preference enforcement, the project
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
        this.socket.on('preferences_updated', (prefs) => {
            console.log('WEBSOCKET preferences_updated received');
            this._serverPreferences = prefs;
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
            infoLabelSize: layer.infoLabelSize,
            // Text layer properties
            textContent: layer.textContent,
            textContentPixelMap: layer.textContentPixelMap,
            textContentCabinetId: layer.textContentCabinetId,
            textContentShowLook: layer.textContentShowLook,
            textContentDataFlow: layer.textContentDataFlow,
            textContentPower: layer.textContentPower,
            textContentOverridePixelMap: layer.textContentOverridePixelMap,
            textContentOverrideCabinetId: layer.textContentOverrideCabinetId,
            textContentOverrideShowLook: layer.textContentOverrideShowLook,
            textContentOverrideDataFlow: layer.textContentOverrideDataFlow,
            textContentOverridePower: layer.textContentOverridePower,
            textWidth: layer.textWidth,
            textHeight: layer.textHeight,
            fontSize: layer.fontSize,
            fontFamily: layer.fontFamily,
            fontColor: layer.fontColor,
            bgColor: layer.bgColor,
            bgOpacity: layer.bgOpacity,
            textAlign: layer.textAlign,
            textPadding: layer.textPadding,
            showBorder: layer.showBorder,
            borderColor: layer.borderColor,
            showOnPixelMap: layer.showOnPixelMap,
            showOnCabinetId: layer.showOnCabinetId,
            showOnShowLook: layer.showOnShowLook,
            showOnDataFlow: layer.showOnDataFlow,
            showOnPower: layer.showOnPower,
            showRasterSize: layer.showRasterSize,
            showProjectName: layer.showProjectName,
            showDate: layer.showDate,
            showPrimaryPorts: layer.showPrimaryPorts,
            showBackupPorts: layer.showBackupPorts,
            showCircuits: layer.showCircuits,
            showSinglePhase: layer.showSinglePhase,
            showThreePhase: layer.showThreePhase,
            fontBold: layer.fontBold,
            fontItalic: layer.fontItalic,
            fontUnderline: layer.fontUnderline
        };
    }
    
    loadProject() {
        fetch('/api/project')
            .then(res => res.json())
            .then(data => {
                this.project = data;
                this.dedupeProjectLayers('load_project');
                if (data && data.raster_width && data.raster_height) {
                    this.syncRasterFromProject();
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

                // Mark initial load complete, subsequent socket project_data
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
            // Show Look position, default to processor offset for older
            // projects so they open looking identical to before.
            if (layer.showOffsetX === undefined || layer.showOffsetX === null) {
                layer.showOffsetX = layer.offset_x || 0;
            }
            if (layer.showOffsetY === undefined || layer.showOffsetY === null) {
                layer.showOffsetY = layer.offset_y || 0;
            }
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
                showPowerCircuitInfo: layer.showPowerCircuitInfo,
                // Text layer properties
                textContent: layer.textContent,
                textContentPixelMap: layer.textContentPixelMap,
                textContentCabinetId: layer.textContentCabinetId,
                textContentShowLook: layer.textContentShowLook,
                textContentDataFlow: layer.textContentDataFlow,
                textContentPower: layer.textContentPower,
                textContentOverridePixelMap: layer.textContentOverridePixelMap,
                textContentOverrideCabinetId: layer.textContentOverrideCabinetId,
                textContentOverrideShowLook: layer.textContentOverrideShowLook,
                textContentOverrideDataFlow: layer.textContentOverrideDataFlow,
                textContentOverridePower: layer.textContentOverridePower,
                textWidth: layer.textWidth,
                textHeight: layer.textHeight,
                fontSize: layer.fontSize,
                fontFamily: layer.fontFamily,
                fontColor: layer.fontColor,
                bgColor: layer.bgColor,
                bgOpacity: layer.bgOpacity,
                textAlign: layer.textAlign,
                textPadding: layer.textPadding,
                showBorder: layer.showBorder,
                borderColor: layer.borderColor,
                showOnPixelMap: layer.showOnPixelMap,
                showOnCabinetId: layer.showOnCabinetId,
                showOnShowLook: layer.showOnShowLook,
                showOnDataFlow: layer.showOnDataFlow,
                showOnPower: layer.showOnPower,
                showRasterSize: layer.showRasterSize,
                showProjectName: layer.showProjectName,
                showDate: layer.showDate,
                showPrimaryPorts: layer.showPrimaryPorts,
                showBackupPorts: layer.showBackupPorts,
                showCircuits: layer.showCircuits,
                showSinglePhase: layer.showSinglePhase,
                showThreePhase: layer.showThreePhase,
                fontBold: layer.fontBold,
                fontItalic: layer.fontItalic,
                fontUnderline: layer.fontUnderline
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

    /**
     * Slice 6: refresh the toolbar Raster: W x H inputs from the active
     * canvas's raster (Pixel Map raster on pixel-map / cabinet-id, Show
     * Look raster on show-look / data / power). Also seeds any missing
     * show_raster_* on the active canvas so older projects (where show
     * raster was never set) open with show = pixel.
     *
     * Renderer fields are accessor-backed (Slice 6), they read straight
     * from the active canvas, so no per-renderer assignment is needed.
     * Legacy fallback (no canvases array): seed the renderer's _fallback*
     * backing fields from the project root so single-canvas pre-Slice-1
     * projects still display.
     */
    syncRasterFromProject() {
        if (!this.project) return;
        const r = window.canvasRenderer;
        if (!r) return;
        const canvases = Array.isArray(this.project.canvases) ? this.project.canvases : [];
        if (canvases.length > 0) {
            const c = canvases.find(x => x.id === this.project.active_canvas_id) || canvases[0];
            if (c) {
                if (!c.show_raster_width)  c.show_raster_width  = c.raster_width;
                if (!c.show_raster_height) c.show_raster_height = c.raster_height;
            }
        } else {
            // Pre-Slice-1 project, seed the renderer's fallback backing
            // fields so the legacy single-canvas getter path returns sane
            // values until the project gets migrated by the server.
            const pw = Number(this.project.raster_width) || 1920;
            const ph = Number(this.project.raster_height) || 1080;
            const sw = Number(this.project.show_raster_width) || pw;
            const sh = Number(this.project.show_raster_height) || ph;
            r._fallbackPixelRasterWidth = pw;
            r._fallbackPixelRasterHeight = ph;
            r._fallbackShowRasterWidth = sw;
            r._fallbackShowRasterHeight = sh;
        }
        const rwIn = document.getElementById('toolbar-raster-width');
        const rhIn = document.getElementById('toolbar-raster-height');
        if (rwIn) rwIn.value = r.rasterWidth;
        if (rhIn) rhIn.value = r.rasterHeight;
    }
    
    // Load raster size from localStorage (checks version first).
    //
    // Slice 6: at boot the project hasn't loaded yet, the active canvas's
    // raster is the source of truth and we must NOT clobber it with stale
    // localStorage. So we only seed the renderer's fallback backing fields
    // (used when no canvases array exists yet) and refresh the toolbar
    // inputs. Once loadProject() runs, syncRasterFromProject() takes over
    // and the toolbar reflects the active canvas.
    loadRasterSize() {
        const savedVersion = localStorage.getItem('ledRasterPropsVersion');
        const currentVersion = '0.4.7';

        const seed = (w, h) => {
            const r = window.canvasRenderer;
            if (!r) return;
            r._fallbackPixelRasterWidth = w;
            r._fallbackPixelRasterHeight = h;
            r._fallbackShowRasterWidth = w;
            r._fallbackShowRasterHeight = h;
            const wIn = document.getElementById('toolbar-raster-width');
            const hIn = document.getElementById('toolbar-raster-height');
            if (wIn) wIn.value = w;
            if (hIn) hIn.value = h;
        };

        if (savedVersion !== currentVersion) {
            console.log('Version mismatch in loadRasterSize - clearing ALL localStorage');
            localStorage.removeItem('ledRasterSize');
            localStorage.removeItem('ledRasterClientProps');
            localStorage.setItem('ledRasterPropsVersion', currentVersion);
            const prefs = this.getPreferences();
            seed(prefs.rasterWidth, prefs.rasterHeight);
            this.saveRasterSize();
            return;
        }

        const saved = localStorage.getItem('ledRasterSize');
        if (saved) {
            try {
                const size = JSON.parse(saved);
                if (size.width && size.height) seed(size.width, size.height);
            } catch (e) {
                console.error('Error loading raster size:', e);
            }
        } else {
            const prefs = this.getPreferences();
            seed(prefs.rasterWidth, prefs.rasterHeight);
            this.saveRasterSize();
        }
    }
    
    /**
     * Clean-slate reset before loading a new project or creating a new one.
     * Clears selection state, stale client props, and undo history so that
     * sidebar inputs cannot leak old values into the incoming project.
     */
    resetApplicationState() {
        this.selectedLayerIds = new Set();
        this.currentLayer = null;
        this.lastSelectedLayerId = null;
        this.selectionAnchorLayerId = null;
        localStorage.removeItem('ledRasterClientProps');
        this.resetHistory('Initial State');
    }

    createNewProject() {
        this.resetApplicationState();
        fetch('/api/project/new', {
            method: 'POST'
        })
            .then(res => res.json())
            .then(data => {
                this.project = data;
                this.dedupeProjectLayers('new_project');
                this.syncRasterFromProject();
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

                // Fit to view
                setTimeout(() => {
                    window.canvasRenderer.fitToView();
                }, 100);
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

        const projectNameEl = document.getElementById('project-name');
        projectNameEl.value = this.project.name;
        // Refresh illegal-character warning whenever the project name changes
        // programmatically (e.g. on project load).
        projectNameEl.dispatchEvent(new Event('input'));
        // Sync the Front/Back perspective toggle buttons to the loaded
        // project's saved values.
        if (this.refreshPerspectiveButtons) this.refreshPerspectiveButtons();

        // Load project notes
        const notesEl = document.getElementById('project-notes');
        if (notesEl) notesEl.value = this.project.notes || '';

        this.renderLayers();
        this.loadTextLayerToInputs();
        // Slice 10: keep the Totals panels (Data Flow + Power tabs) in sync
        // with whatever just changed. Always cheap, two aggregations over
        // the visible screen layers, plus a handful of textContent writes.
        if (typeof this.refreshTotalsSidebar === 'function') {
            try { this.refreshTotalsSidebar(); } catch (_) {}
        }

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
    
    setupPixelMapBulkActions() {
        const wireBtn = (id, fn) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('click', () => {
                const panels = this.getPixelMapSelectedPanels();
                if (panels.length === 0) return;
                fn(panels);
            });
        };
        wireBtn('bulk-set-blank',       (panels) => this.setPanelsBlankBulk(panels, true));
        wireBtn('bulk-unset-blank',     (panels) => this.setPanelsBlankBulk(panels, false));
        wireBtn('bulk-set-half-auto',   (panels) => this.setPanelsHalfTileBulk(panels, 'auto'));
        wireBtn('bulk-set-half-width',  (panels) => this.setPanelsHalfTileBulk(panels, 'width'));
        wireBtn('bulk-set-half-height', (panels) => this.setPanelsHalfTileBulk(panels, 'height'));
        wireBtn('bulk-clear-half',      (panels) => this.setPanelsHalfTileBulk(panels, 'none'));

        // Esc clears the pixel-map selection. Only react when no input is focused
        // and the pixel-map view is active.
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            const tag = (document.activeElement && document.activeElement.tagName) || '';
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
            if (window.canvasRenderer && window.canvasRenderer.viewMode === 'pixel-map'
                    && this.pixelMapSelection && this.pixelMapSelection.size > 0) {
                this.clearPixelMapSelection();
                e.preventDefault();
                e.stopPropagation();
            }
        }, true);
    }

    /**
     * Wire the Front / Back perspective toggles in the Data Flow and Power
     * sidebars. Each tab has its own perspective stored on the project
     * (project.data_flow_perspective, project.power_perspective). 'back'
     * horizontally mirrors the wiring view so techs working behind the wall
     * see things from their perspective; labels stay readable (un-mirrored
     * inside the canvas mirror transform during render).
     */
    setupPerspectiveToggles() {
        document.querySelectorAll('.perspective-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const target = btn.getAttribute('data-target');
                const value = btn.getAttribute('data-perspective');
                if (!target || !value || !this.project) return;
                // v0.8 Slice 8: perspective is per-canvas. Write to the active
                // canvas (which routes through updateCanvas → server PUT, undo
                // entry, and a re-render via _applyProjectUpdate). Mirror
                // project-root field too so legacy code paths keep working
                // until they're all migrated to read from active canvas.
                const active = this._activeCanvas();
                const currentVal = (active && active[target]) || this.project[target] || 'front';
                if (currentVal === value) return;
                this.project[target] = value;
                if (active && typeof this.updateCanvas === 'function') {
                    this.updateCanvas(active.id, { [target]: value });
                } else {
                    this.refreshPerspectiveButtons();
                    this.saveProject();
                    if (window.canvasRenderer) window.canvasRenderer.render();
                }
                if (typeof sendClientLog === 'function') {
                    sendClientLog('perspective_change', {
                        target, value, canvasId: active && active.id
                    });
                }
            });
        });
        this.refreshPerspectiveButtons();
    }

    /**
     * Find the active canvas object, or null. v0.8 Slice 8 helper.
     */
    _activeCanvas() {
        if (!this.project || !Array.isArray(this.project.canvases)) return null;
        const id = this.project.active_canvas_id;
        if (!id) return this.project.canvases[0] || null;
        return this.project.canvases.find(c => c && c.id === id) || null;
    }

    /**
     * v0.8 Slice 9: ids of all canvases whose visibility is explicitly off.
     * Used by aggregate counters (data ports, power totals) to exclude
     * hidden canvases so the numbers in the sidebar match what's drawn.
     */
    _hiddenCanvasIdSet() {
        const set = new Set();
        if (!this.project || !Array.isArray(this.project.canvases)) return set;
        this.project.canvases.forEach(c => {
            if (c && c.visible === false && c.id) set.add(c.id);
        });
        return set;
    }

    /**
     * v0.8 Slice 10: paint the Totals panels on the Data Flow + Power tabs.
     * Two columns each: active canvas + project-wide. Numbers come from
     * getPortCounts/getPowerCounts which already exclude hidden canvases.
     * Cheap to call on every updateUI, the Totals panels are display:none
     * unless the user is on the relevant tab.
     */
    refreshTotalsSidebar() {
        const setText = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };
        const active = (typeof this._activeCanvas === 'function') ? this._activeCanvas() : null;
        const activeId = active ? active.id : null;
        const activeName = active ? `(${active.name || 'Canvas'})` : '(no active canvas)';
        // Data Flow totals
        const dataCanvas = activeId ? this.getPortCounts(activeId) : { primary: 0, backup: 0 };
        const dataProject = this.getPortCounts();
        setText('data-totals-canvas-name', activeName);
        setText('data-totals-canvas-primary', dataCanvas.primary);
        setText('data-totals-canvas-backup', dataCanvas.backup);
        setText('data-totals-project-primary', dataProject.primary);
        setText('data-totals-project-backup', dataProject.backup);
        // Power totals, show "0" cleanly when there's no active canvas / no
        // load yet. Amps formatted to 2 decimals to match the per-layer
        // capacity readout.
        const pwrCanvas = activeId ? this.getPowerCounts(activeId)
            : { circuits: 0, totalWatts: 0, singlePhaseAmps: 0, threePhaseAmps: 0 };
        const pwrProject = this.getPowerCounts();
        const fmtAmps = (a) => (a > 0) ? `${a.toFixed(2)} A` : '0';
        const fmtWatts = (w) => (w > 0) ? `${Math.round(w).toLocaleString()} W` : '0';
        setText('power-totals-canvas-name', activeName);
        setText('power-totals-canvas-watts', fmtWatts(pwrCanvas.totalWatts));
        setText('power-totals-canvas-circuits', pwrCanvas.circuits);
        setText('power-totals-canvas-1ph', fmtAmps(pwrCanvas.singlePhaseAmps));
        setText('power-totals-canvas-3ph', fmtAmps(pwrCanvas.threePhaseAmps));
        setText('power-totals-project-watts', fmtWatts(pwrProject.totalWatts));
        setText('power-totals-project-circuits', pwrProject.circuits);
        setText('power-totals-project-1ph', fmtAmps(pwrProject.singlePhaseAmps));
        setText('power-totals-project-3ph', fmtAmps(pwrProject.threePhaseAmps));
    }

    /**
     * Reflect the active canvas's perspective values on the toggle buttons.
     * Falls back to the project root for pre-Slice-1 / legacy projects that
     * have no canvas list yet. Called on project load and on every active-
     * canvas switch.
     */
    refreshPerspectiveButtons() {
        if (!this.project) return;
        const active = this._activeCanvas();
        document.querySelectorAll('.perspective-btn').forEach(btn => {
            const target = btn.getAttribute('data-target');
            const value = btn.getAttribute('data-perspective');
            if (!target || !value) return;
            const current = (active && active[target]) || this.project[target] || 'front';
            btn.classList.toggle('active', current === value);
        });
    }

    setupEventListeners() {
        this.setupPixelMapBulkActions();
        this.setupPerspectiveToggles();
        // Project name editing
        const projectNameInput = document.getElementById('project-name');
        const projectNameWarning = document.getElementById('project-name-warning');
        const updateProjectNameWarning = () => {
            if (!projectNameWarning) return;
            const v = projectNameInput.value || '';
            const bad = v.match(/[\\/:*?"<>|]/g);
            if (bad && bad.length > 0) {
                const unique = [...new Set(bad)].join(' ');
                projectNameWarning.textContent = `Note: ${unique} will be replaced with _ in exported filenames.`;
                projectNameWarning.style.display = 'block';
            } else {
                projectNameWarning.style.display = 'none';
            }
        };
        if (projectNameInput) {
            projectNameInput.addEventListener('input', updateProjectNameWarning);
            projectNameInput.addEventListener('change', () => {
                if (this.project) {
                    this.project.name = projectNameInput.value.trim() || 'Untitled Project';
                    this.saveProject();
                }
                updateProjectNameWarning();
            });
            // Run once on init in case a loaded project has illegal chars
            updateProjectNameWarning();
        }
        
        // Project Notes
        const notesTextarea = document.getElementById('project-notes');
        const notesToggle = document.getElementById('notes-toggle');
        const notesPanel = document.getElementById('notes-panel');
        if (notesTextarea) {
            notesTextarea.addEventListener('input', () => {
                if (this.project) {
                    this.project.notes = notesTextarea.value;
                    this.saveProject();
                }
            });
        }
        if (notesToggle && notesPanel) {
            const toggleNotes = () => {
                notesPanel.classList.toggle('collapsed');
                notesToggle.textContent = notesPanel.classList.contains('collapsed') ? '▶' : '▼';
            };
            notesToggle.addEventListener('click', (e) => { e.stopPropagation(); toggleNotes(); });
            document.getElementById('notes-panel-header').addEventListener('click', toggleNotes);
        }

        // Help panel, same collapse pattern as Notes. Defaults to collapsed
        // so the layer-groups list above gets the spare space; user can
        // expand on demand via the header.
        const helpPanel = document.getElementById('help-tooltip-panel');
        const helpHeader = document.getElementById('help-tooltip-header');
        const helpToggle = document.getElementById('help-tooltip-toggle');
        if (helpPanel && helpHeader && helpToggle) {
            const toggleHelp = () => {
                helpPanel.classList.toggle('collapsed');
                helpToggle.textContent = helpPanel.classList.contains('collapsed') ? '▶' : '▼';
            };
            helpToggle.addEventListener('click', (e) => { e.stopPropagation(); toggleHelp(); });
            helpHeader.addEventListener('click', toggleHelp);
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
                // v0.8.6.1: re-render the Screens sidebar so groups reflect
                // the view-effective canvas (Show Look groups by
                // show_canvas_id; Pixel Map groups by canvas_id).
                if (typeof this.renderLayers === 'function') {
                    try { this.renderLayers(); } catch (_) {}
                }
                sendClientLog('tab_switch', {
                    tab: mode,
                    currentLayer: this.currentLayer ? { id: this.currentLayer.id, name: this.currentLayer.name } : null,
                    selectedLayers: this.selectedLayerIds ? [...this.selectedLayerIds] : []
                });
                this.updateLayerPanelVisibility(
                    !!this.currentLayer && (this.currentLayer.type || 'screen') === 'image',
                    !!this.currentLayer && (this.currentLayer.type || 'screen') === 'text'
                );
                this.loadLayerToInputs();
                this.loadTextLayerToInputs();
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
        
        // v0.8 Slice 2.5: the global "+ Add Screen / + Add Image / + Add Text"
        // and "▲ Up / ▼ Down" buttons were removed. Per-canvas "+ Add" chooser
        // (built in buildCanvasGroupEl) and per-layer ▲▼ arrows now own those
        // affordances. We still wire the file-input change handler because
        // the per-canvas "Image / Logo" chooser entry reuses it.
        const addCanvasBtn = document.getElementById('btn-add-canvas');
        if (addCanvasBtn) {
            addCanvasBtn.addEventListener('click', () => this.addCanvas());
        }
        const savePresetBtn = document.getElementById('btn-save-preset');
        if (savePresetBtn) {
            savePresetBtn.addEventListener('click', () => this.openPresetSaveModal());
        }
        this.setupPresetModals();
        const addImageInput = document.getElementById('add-image-input');
        if (addImageInput) {
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

        // Text layer sidebar controls
        this.setupTextLayerControls();

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
                // Convert displayed percent (1:1 device-pixel based) into the
                // internal raster→CSS scale used by canvasRenderer.
                const targetZoom = (typeof window.canvasRenderer._percentToZoom === 'function')
                    ? window.canvasRenderer._percentToZoom(percent)
                    : percent / 100;
                window.canvasRenderer.setZoom(targetZoom);
            }
            const displayed = (typeof window.canvasRenderer._zoomToPercent === 'function')
                ? window.canvasRenderer._zoomToPercent(window.canvasRenderer.zoom)
                : Math.round(window.canvasRenderer.zoom * 100);
            zoomInput.value = `${displayed}%`;
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
         'screen-columns', 'screen-rows', 'number-size', 'panel-width-mm', 'panel-height-mm', 'panel-weight-kg', 'image-scale', 'image-scale-range',
         'show-offset-x', 'show-offset-y'].forEach(id => {
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

        // Show Look "Reset to Pixel Map Position" button
        const showResetBtn = document.getElementById('show-look-reset');
        if (showResetBtn) {
            showResetBtn.addEventListener('click', () => {
                const layers = this.getSelectedLayers ? this.getSelectedLayers() : (this.currentLayer ? [this.currentLayer] : []);
                if (layers.length === 0) return;
                this.saveState('Reset Show Look Position');
                layers.forEach(l => {
                    l.showOffsetX = l.offset_x;
                    l.showOffsetY = l.offset_y;
                    // v0.8.5: also clear the Show Look canvas override so
                    // the layer falls back to mirroring its Pixel Map
                    // canvas membership (canvas_id).
                    l.show_canvas_id = null;
                });
                this.updateLayers(layers, false);
                // v0.8.5.2: also re-link the Show Look raster of every
                // canvas touched by these layers back to its Pixel Map
                // raster, so a single Reset click fully restores Show Look
                // to mirror Pixel Map (position + canvas membership +
                // raster size). Pushed via the canvas PUT endpoint.
                if (this.project && Array.isArray(this.project.canvases)
                        && typeof this.updateCanvas === 'function') {
                    const canvasIds = new Set();
                    layers.forEach(l => { if (l && l.canvas_id) canvasIds.add(l.canvas_id); });
                    canvasIds.forEach(cid => {
                        const c = this.project.canvases.find(x => x && x.id === cid);
                        if (!c) return;
                        const rw = Number(c.raster_width) || 0;
                        const rh = Number(c.raster_height) || 0;
                        const sw = Number(c.show_raster_width) || 0;
                        const sh = Number(c.show_raster_height) || 0;
                        const patch = {};
                        if (rw && rw !== sw) patch.show_raster_width = rw;
                        if (rh && rh !== sh) patch.show_raster_height = rh;
                        // v0.8.5.3: also re-link show workspace position to
                        // the Pixel Map workspace position (clear override).
                        if (c.show_workspace_x != null) {
                            c.show_workspace_x = null;
                            patch.show_workspace_x = null;
                        }
                        if (c.show_workspace_y != null) {
                            c.show_workspace_y = null;
                            patch.show_workspace_y = null;
                        }
                        if (Object.keys(patch).length === 0) return;
                        Object.assign(c, patch);
                        this.updateCanvas(cid, patch);
                    });
                }
                this.loadLayerToInputs();
                if (window.canvasRenderer) window.canvasRenderer.render();
            });
        }
        // v0.8.5.2: project-wide Show Look reset. Resets EVERY layer's
        // showOffset to its offset_x/y, clears every show_canvas_id, and
        // re-links every canvas's show_raster_* to its raster_* — one
        // click puts the entire Show Look (and Data + Power, which render
        // at the show layout) back to mirroring Pixel Map.
        const showResetAllBtn = document.getElementById('show-look-reset-all');
        if (showResetAllBtn) {
            showResetAllBtn.addEventListener('click', () => {
                if (!this.project) return;
                this.saveState('Reset Entire Show Look');
                const allLayers = (this.project.layers || []).filter(
                    l => (l.type || 'screen') === 'screen'
                );
                allLayers.forEach(l => {
                    l.showOffsetX = l.offset_x;
                    l.showOffsetY = l.offset_y;
                    l.show_canvas_id = null;
                });
                if (allLayers.length > 0) this.updateLayers(allLayers, false);
                if (Array.isArray(this.project.canvases)
                        && typeof this.updateCanvas === 'function') {
                    this.project.canvases.forEach(c => {
                        if (!c) return;
                        const rw = Number(c.raster_width) || 0;
                        const rh = Number(c.raster_height) || 0;
                        const sw = Number(c.show_raster_width) || 0;
                        const sh = Number(c.show_raster_height) || 0;
                        const patch = {};
                        if (rw && rw !== sw) patch.show_raster_width = rw;
                        if (rh && rh !== sh) patch.show_raster_height = rh;
                        // v0.8.5.3: clear the Show Look workspace override
                        // so canvases visually re-pin to their Pixel Map
                        // positions in Show Look / Data / Power.
                        if (c.show_workspace_x != null) {
                            c.show_workspace_x = null;
                            patch.show_workspace_x = null;
                        }
                        if (c.show_workspace_y != null) {
                            c.show_workspace_y = null;
                            patch.show_workspace_y = null;
                        }
                        if (Object.keys(patch).length === 0) return;
                        Object.assign(c, patch);
                        this.updateCanvas(c.id, patch);
                    });
                }
                this.loadLayerToInputs();
                if (window.canvasRenderer) window.canvasRenderer.render();
            });
        }
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
                this.updateLayers([this.currentLayer]);
                this.debouncedSaveState('Image Scale');
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

        // (legacy half-* checkboxes removed; per-panel halfTile editing
        // replaces them via Alt+Shift+Click and the bulk action sidebar.)
        
        // Cabinet ID style radio buttons
        const cabinetIdStyleRadios = document.querySelectorAll('input[name="cabinet-id-style"]');
        cabinetIdStyleRadios.forEach(radio => {
            radio.addEventListener('change', () => {
                this.applyToSelectedLayers(layer => {
                    layer.cabinetIdStyle = radio.value;
                });
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
                this.saveState('Change Cabinet ID Style');
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
                this.saveState('Change Cabinet ID Position');
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
        
        // Screen Name checkboxes on other tabs, each writes its own per-tab property
        const tabLabelMap = {
            'show-label-name-cabinet': 'showLabelNameCabinet',
            'show-label-name-data': 'showLabelNameDataFlow',
            'show-label-name-power': 'showLabelNamePower'
        };
        Object.entries(tabLabelMap).forEach(([id, prop]) => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    if (this.currentLayer) {
                        this.applyToSelectedLayers(layer => {
                            layer[prop] = checkbox.checked;
                        });
                        this.updateLayers(this.getSelectedLayers());
                        window.canvasRenderer.render();
                        this.saveState('Toggle Screen Name');
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
                // v0.8.2 Re-entrancy guard: when the change event re-fires
                // mid-flight (browser quirk on some platforms — observed on
                // mac WKWebView clicking the toggle once produced two change
                // events 367ms apart), the second invocation immediately
                // flips the state back so the user's single click ended up
                // disabling Custom mode. Drop the second event entirely.
                if (this._customFlowToggleInFlight) return;
                this._customFlowToggleInFlight = true;
                try {
                    this.toggleCustomFlowMode(customModeToggle.checked);
                } finally {
                    setTimeout(() => { this._customFlowToggleInFlight = false; }, 600);
                }
            });
        }
        if (customPrevPortBtn) {
            customPrevPortBtn.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomFlowState(this.currentLayer);
                this.currentLayer.customPortIndex = Math.max(1, (this.currentLayer.customPortIndex || 1) - 1);
                this.saveState('Custom Port Change');
                this.saveClientSideProperties();
                // v0.8.2: PUT to the server. Without this, all the local
                // mutations (Next/Prev/Clear/Apply) accumulate only on the
                // client; the next time something else triggers a real PUT
                // (Mode Toggle, tab switch with stale state, etc.) the
                // client's view collapses or contradicts the server's.
                this.updateLayers(this.getSelectedLayers());
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
                this.updateLayers(this.getSelectedLayers());
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
                this.updateLayers(this.getSelectedLayers());
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
                this.updateLayers(this.getSelectedLayers());
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
                    this.updateLayers(this.getSelectedLayers());
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
                const parsed = this.evaluateNumericExpression(powerPanelWattsInput.value);
                const val = parsed === null ? 0 : parsed;
                // Write the resolved number back so the field shows the result
                if (parsed !== null) powerPanelWattsInput.value = this._formatEvaluatedNumber(parsed);
                else powerPanelWattsInput.style.outline = '2px solid #c55';
                if (parsed !== null) powerPanelWattsInput.style.outline = '';
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
                // v0.8.2: re-entrancy guard — single click was producing two
                // change events 367ms apart, with the second flipping the
                // state back to the opposite of what the user wanted. See
                // matching guard in customModeToggle handler above.
                if (this._customPowerToggleInFlight) return;
                this._customPowerToggleInFlight = true;
                try {
                    this.toggleCustomPowerMode(powerCustomToggle.checked);
                } finally {
                    setTimeout(() => { this._customPowerToggleInFlight = false; }, 600);
                }
            });
        }
        if (powerCustomPrev) {
            powerCustomPrev.addEventListener('click', () => {
                if (!this.currentLayer) return;
                this.ensureCustomPowerState(this.currentLayer);
                this.currentLayer.powerCustomIndex = Math.max(1, (this.currentLayer.powerCustomIndex || 1) - 1);
                this.saveState('Power Custom Circuit Change');
                this.saveClientSideProperties();
                // v0.8.2: PUT to the server. See matching comment on the data-
                // flow Custom handlers above. Without this, every Next/Prev/
                // Clear Circuit/Clear All/Pattern Apply mutated only the
                // client; the next Mode Toggle would then PUT a single-circuit
                // collapsed view of layer.powerCustomPaths.
                this.updateLayers(this.getSelectedLayers());
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
                this.updateLayers(this.getSelectedLayers());
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
                this.updateLayers(this.getSelectedLayers());
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
                this.updateLayers(this.getSelectedLayers());
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
                    this.updateLayers(this.getSelectedLayers());
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
                rasterWidthInput.value = width;
                // Slice 6: the toolbar Raster: W x H field is the active
                // canvas's raster (Pixel Map raster on pixel-map / cabinet-id;
                // Show Look raster on show-look / data / power). Writes go
                // straight to the active canvas via PUT /api/canvas/<id>,
                // no project-root mirror, no _mirrorRasterToActiveCanvas hack.
                //
                // While show raster equals pixel raster ("linked"), changing
                // the pixel raster also updates the show raster, Show Look
                // tracks Pixel Map by default until the user splits them.
                const renderer = window.canvasRenderer;
                const isShow = renderer.isShowLookView();
                this._writeToolbarRasterToActiveCanvas('width', width, isShow);
                renderer.render();
            });
        }

        if (rasterHeightInput) {
            rasterHeightInput.addEventListener('change', () => {
                const height = evaluateMathExpression(rasterHeightInput.value) || 1080;
                rasterHeightInput.value = height;
                const renderer = window.canvasRenderer;
                const isShow = renderer.isShowLookView();
                this._writeToolbarRasterToActiveCanvas('height', height, isShow);
                renderer.render();
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
        
        document.getElementById('btn-preferences').addEventListener('click', () => {
            this.openPreferencesModal();
        });

        document.getElementById('btn-export').addEventListener('click', () => {
            // Show export modal
            document.getElementById('export-modal').style.display = 'block';
            // Set project name from current project
            document.getElementById('export-name').value = this.project.name || 'Untitled Project';
            this.loadExportSuffixesToUI();
            // Slice 11: rebuild canvas checklist on every open so renames /
            // additions / deletions show up. Visible canvases default-checked.
            this.populateExportCanvasesList();
            // Update preview
            this.updateExportPreview();
        });
        
        // Update preview when options change
        ['export-name', 'export-format', 'export-pixel-map', 'export-cabinet-id', 'export-show-look', 'export-data-flow', 'export-power',
         'export-suffix-pixel-map', 'export-suffix-cabinet-id', 'export-suffix-show-look', 'export-suffix-data-flow', 'export-suffix-power'].forEach(id => {
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
            
            // Resolume XML export, no views needed, just geometry
            if (format === 'resolume-xml') {
                document.getElementById('export-modal').style.display = 'none';
                document.getElementById('status-message').textContent = 'Exporting Resolume XML...';
                try {
                    await this.exportResolumeXml(projectName);
                    document.getElementById('status-message').textContent = 'Export complete!';
                    setTimeout(() => { document.getElementById('status-message').textContent = 'Ready'; }, 3000);
                } catch (error) {
                    console.error('Resolume export error:', error);
                    document.getElementById('status-message').textContent = 'Export failed!';
                    sendClientLog('export_failed', { message: error.message, format: 'resolume-xml' });
                }
                return;
            }

            // Get selected views
            const views = [];
            if (document.getElementById('export-pixel-map').checked) views.push('pixel-map');
            if (document.getElementById('export-cabinet-id').checked) views.push('cabinet-id');
            if (document.getElementById('export-show-look') && document.getElementById('export-show-look').checked) views.push('show-look');
            if (document.getElementById('export-data-flow').checked) views.push('data-flow');
            if (document.getElementById('export-power').checked) views.push('power');

            if (views.length === 0) {
                alert('Please select at least one view to export.');
                return;
            }

            // Slice 11: collect selected canvas IDs from the dynamic
            // checklist. If the project has no canvases array (legacy /
            // pre-Slice-1 fallback), pass [null] so performExport treats it
            // as a single synthetic canvas using project-root raster dims,
            // matching v0.7 export behaviour exactly.
            const canvasIds = this.getSelectedExportCanvasIds();
            if (canvasIds.length === 0) {
                alert('Please select at least one canvas to export.');
                return;
            }

            if (!this.supportsFilePickerAPIs() && !this.supportsDirectoryPickerAPIs() && !this._warnedNoFilePickerExport) {
                this._warnedNoFilePickerExport = true;
                sendClientLog('export_picker_apis_unavailable_warning', {});
            }

            document.getElementById('export-modal').style.display = 'none';
            document.getElementById('status-message').textContent = 'Exporting...';

            try {
                await this.performExport(projectName, format, views, canvasIds);
                
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
    
    getNextScreenName() {
        let maxNum = 0;
        if (this.project && this.project.layers) {
            for (const l of this.project.layers) {
                // Match "Screen1", "Screen 1", "Screen_1", "screen 12", etc.
                const m = (l.name || '').match(/^Screen[\s_]*(\d+)$/i);
                if (m) {
                    const n = parseInt(m[1], 10);
                    if (n > maxNum) maxNum = n;
                }
            }
        }
        // Also ensure we don't collide with the total layer count
        const layerCount = this.project && this.project.layers ? this.project.layers.length : 0;
        if (layerCount > maxNum) maxNum = layerCount;
        return `Screen${maxNum + 1}`;
    }

    addLayer(presetData) {
        // Server-side props control panel generation (columns/rows/cabinet sizes/colors/etc.)
        // Client-side props (data flow, power, labels...) are applied after the layer is returned.
        const prefs = this.getPreferences();
        let serverProps;
        if (presetData && typeof presetData === 'object') {
            serverProps = {
                columns: presetData.columns != null ? presetData.columns : prefs.columns,
                rows: presetData.rows != null ? presetData.rows : prefs.rows,
                cabinet_width: presetData.cabinet_width != null ? presetData.cabinet_width : prefs.panelWidth,
                cabinet_height: presetData.cabinet_height != null ? presetData.cabinet_height : prefs.panelHeight,
                color1: presetData.color1 || this.hexToRgb(prefs.color1),
                color2: presetData.color2 || this.hexToRgb(prefs.color2),
                border_color: presetData.border_color || prefs.borderColor,
                panel_weight: presetData.panel_weight != null ? presetData.panel_weight : prefs.panelWeight,
                weight_unit: presetData.weight_unit || prefs.weightUnit
            };
        } else {
            serverProps = {
                columns: prefs.columns,
                rows: prefs.rows,
                cabinet_width: prefs.panelWidth,
                cabinet_height: prefs.panelHeight,
                color1: this.hexToRgb(prefs.color1),
                color2: this.hexToRgb(prefs.color2),
                border_color: prefs.borderColor,
                panel_weight: prefs.panelWeight,
                weight_unit: prefs.weightUnit
            };
        }

        this.saveState('Add Layer');

        fetch('/api/layer/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: this.getNextScreenName(),
                offset_x: 0,
                offset_y: 0,
                ...serverProps
            })
        })
        .then(res => res.json())
        .then(layer => {
            sendClientLog('add_layer', {
                id: layer.id, name: layer.name,
                columns: layer.columns, rows: layer.rows,
                cabinet_width: layer.cabinet_width, cabinet_height: layer.cabinet_height,
                offset_x: layer.offset_x, offset_y: layer.offset_y,
                preset: presetData ? (presetData._presetName || true) : false,
                totalLayers: this.project.layers ? this.project.layers.length + 1 : 1
            });
            // Initialize client-side defaults first (baseline)
            this.initializeLayerDefaults(layer);
            // Then overlay preset client-side props on top
            const appliedPreset = presetData && typeof presetData === 'object';
            if (appliedPreset) {
                this.applyPresetClientProps(layer, presetData);
            }

            this.upsertProjectLayer(layer);
            this.selectLayer(layer);
            window.canvasRenderer.fitToView();

            // Save the new defaults to localStorage
            this.saveClientSideProperties();

            // IMPORTANT: when a preset was applied, the server only knows the
            // structural fields sent via /api/layer/add (columns, cabinet dims,
            // colors, etc.). Preset values like bitDepth, frameRate, panelWatts,
            // powerVoltage, flowPattern, label sizes, etc. live only on the
            // client at this point. Any subsequent server re-fetch (e.g. after
            // delete_layer or file load) would clobber them. Push the enriched
            // layer back now so server + client stay in sync.
            if (appliedPreset) {
                this.updateLayers([layer]);
            }
        });
    }

    // Properties excluded from presets (identity, runtime position, cached computations).
    // Everything else on a layer can be preserved as a preset.
    getPresetExcludedKeys() {
        return new Set([
            'id', 'name', 'visible', 'locked',
            'offset_x', 'offset_y',
            'panels',  // panel array is regenerated from columns/rows on server
            '_powerError', '_powerCircuits', '_powerPanelCircuitMap', '_powerPanelIndexMap',
            '_powerCircuitNumKeys', '_powerTotalAmps1', '_powerTotalAmps3',
            '_powerCircuitsRequired', '_capacityError', '_portsRequired', '_autoPortsRequired',
            '_imageObj', 'imageData'
        ]);
    }

    serializeLayerAsPreset(layer) {
        if (!layer) return null;
        const excluded = this.getPresetExcludedKeys();
        const out = {};
        Object.keys(layer).forEach(k => {
            if (excluded.has(k)) return;
            if (k.startsWith('_')) return;  // skip runtime caches
            out[k] = layer[k];
        });
        // Ensure common layer-default keys are always present even if the
        // source layer was loaded from an older project file that lacked them.
        // Without this, a fresh layer created from the preset would fall back
        // to `initializeLayerDefaults` values instead of the intended preset.
        const ensuredDefaults = {
            portMappingMode: 'organized',
            randomDataColors: false
        };
        Object.keys(ensuredDefaults).forEach(k => {
            if (out[k] === undefined) out[k] = ensuredDefaults[k];
        });
        return out;
    }

    applyPresetClientProps(layer, presetData) {
        const excluded = this.getPresetExcludedKeys();
        // Server-side structural props already applied via /api/layer/add; skip them here.
        const serverKeys = new Set(['columns', 'rows', 'cabinet_width', 'cabinet_height',
            'color1', 'color2', 'border_color', 'panel_weight', 'weight_unit']);
        Object.keys(presetData).forEach(k => {
            if (excluded.has(k)) return;
            if (serverKeys.has(k)) return;
            if (k.startsWith('_')) return;
            layer[k] = presetData[k];
        });
    }

    // ── Preset CRUD (server) ──
    fetchPresetList() {
        // Returns list of names (compat).
        return fetch('/api/presets').then(r => r.json()).then(d => d.presets || []);
    }

    fetchPresetEntries() {
        // Returns list of {name, columns, rows, cabinet_width, cabinet_height, panel_width_mm, panel_height_mm}
        return fetch('/api/presets').then(r => r.json()).then(d => d.entries || []);
    }

    formatPresetSublabel(entry) {
        if (!entry) return 'Saved preset';
        const parts = [];
        if (entry.columns != null && entry.rows != null) {
            parts.push(`${entry.columns}×${entry.rows}`);
        }
        if (entry.cabinet_width != null && entry.cabinet_height != null) {
            parts.push(`${entry.cabinet_width}×${entry.cabinet_height}px`);
        }
        if (entry.panel_width_mm != null && entry.panel_height_mm != null) {
            parts.push(`${entry.panel_width_mm}×${entry.panel_height_mm}mm`);
        }
        if (entry.panelWatts != null) {
            parts.push(`${entry.panelWatts}W/panel`);
        }
        return parts.length > 0 ? parts.join(' • ') : 'Saved preset';
    }

    fetchPreset(name) {
        return fetch(`/api/presets/${encodeURIComponent(name)}`).then(r => {
            if (!r.ok) return r.json().then(e => Promise.reject(e));
            return r.json();
        });
    }

    savePresetToServer(name, data) {
        return fetch(`/api/presets/${encodeURIComponent(name)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data })
        }).then(r => r.json().then(body => r.ok ? body : Promise.reject(body)));
    }

    deletePresetOnServer(name) {
        return fetch(`/api/presets/${encodeURIComponent(name)}`, { method: 'DELETE' })
            .then(r => r.json().then(body => r.ok ? body : Promise.reject(body)));
    }

    // ── Add-Layer favorites (per-user, localStorage) ──
    // `favorites` is an array of panel snapshots ({ _mfr, name, width_mm, ... })
    // captured when the user hearted a catalog row. Snapshotting lets us
    // render favorites even before the catalog JSON has loaded.
    // `order` is an array of left-column row IDs ('__default__', 'preset:<name>',
    // 'panel:<mfr>|<name>'); items not in the array fall back to natural order.
    getAddLayerFavorites() {
        try { return JSON.parse(localStorage.getItem('addLayer.favorites') || '[]') || []; }
        catch { return []; }
    }
    setAddLayerFavorites(arr) {
        try { localStorage.setItem('addLayer.favorites', JSON.stringify(arr || [])); } catch {}
    }
    getAddLayerOrder() {
        try { return JSON.parse(localStorage.getItem('addLayer.order') || '[]') || []; }
        catch { return []; }
    }
    setAddLayerOrder(arr) {
        try { localStorage.setItem('addLayer.order', JSON.stringify(arr || [])); } catch {}
    }
    _favoriteKey(mfr, name) { return `${mfr}|${name}`; }
    _isCatalogFavorited(mfr, name) {
        const key = this._favoriteKey(mfr, name);
        return this.getAddLayerFavorites().some(p => this._favoriteKey(p._mfr, p.name) === key);
    }
    _toggleCatalogFavorite(panel) {
        const key = this._favoriteKey(panel._mfr, panel.name);
        const favs = this.getAddLayerFavorites();
        const idx = favs.findIndex(p => this._favoriteKey(p._mfr, p.name) === key);
        if (idx >= 0) {
            favs.splice(idx, 1);
        } else {
            // Snapshot only the fields we need so we don't bloat localStorage.
            favs.push({
                _mfr: panel._mfr, name: panel.name,
                width_mm: panel.width_mm, height_mm: panel.height_mm,
                pixels_w: panel.pixels_w, pixels_h: panel.pixels_h,
                weight_kg: panel.weight_kg, watts_max: panel.watts_max,
                source: panel.source
            });
        }
        this.setAddLayerFavorites(favs);
    }

    // ── Preset Picker Modal (triggered by + Add Screen) ──
    openPresetPicker() {
        const modal = document.getElementById('preset-picker-modal');
        const list = document.getElementById('preset-picker-list');
        if (!modal || !list) return;
        list.innerHTML = '<div style="padding: 12px; color: #888; font-size: 12px;">Loading…</div>';
        modal.style.display = 'block';
        // Selection model: { type: 'preset'|'panel', key }, default preset is always '__default__'
        this._pickerSelection = { type: 'preset', key: '__default__' };
        this._updatePickerSummary();
        this._renderPresetPickerLeftColumn();
        // Load catalog in parallel
        this._loadPanelCatalog();
    }

    _renderPresetPickerLeftColumn() {
        const list = document.getElementById('preset-picker-list');
        if (!list) return;
        list.innerHTML = '<div style="padding: 12px; color: #888; font-size: 12px;">Loading…</div>';
        this.fetchPresetEntries().then(entries => {
            list.innerHTML = '';
            const prefs = this.getPreferences() || {};
            const prefEntry = {
                columns: prefs.columns, rows: prefs.rows,
                cabinet_width: prefs.panelWidth, cabinet_height: prefs.panelHeight,
                panel_width_mm: prefs.panelWidthMM, panel_height_mm: prefs.panelHeightMM,
                panelWatts: prefs.powerWatts
            };
            // Build unified row list. Default is always pinned first.
            const defaultRow = {
                id: '__default__',
                kind: 'default',
                label: 'Default (from Preferences)',
                sublabel: this.formatPresetSublabel(prefEntry),
                pickerKey: '__default__'
            };
            const presetRows = entries.map(entry => ({
                id: `preset:${entry.name}`,
                kind: 'preset',
                label: entry.name,
                sublabel: this.formatPresetSublabel(entry),
                pickerKey: entry.name
            }));
            const favRows = this.getAddLayerFavorites().map(p => ({
                id: `panel:${this._favoriteKey(p._mfr, p.name)}`,
                kind: 'favorite',
                panel: p,
                label: `${(p._mfr || '').replace(/_/g,' ')} ${p.name || ''}`.trim(),
                sublabel: this.formatPresetSublabel({
                    cabinet_width: p.pixels_w, cabinet_height: p.pixels_h,
                    panel_width_mm: p.width_mm, panel_height_mm: p.height_mm,
                    panelWatts: p.watts_max
                }),
                pickerKey: this._favoriteKey(p._mfr, p.name)
            }));
            // Sort by saved order; unknowns appended.
            const order = this.getAddLayerOrder();
            const orderIdx = id => {
                const i = order.indexOf(id);
                return i === -1 ? Number.MAX_SAFE_INTEGER : i;
            };
            const mixed = [...presetRows, ...favRows].sort((a, b) => orderIdx(a.id) - orderIdx(b.id));
            const rows = [defaultRow, ...mixed];

            rows.forEach((row, idx) => {
                const item = document.createElement('div');
                item.className = 'preset-picker-row';
                item.dataset.key = row.pickerKey;
                item.dataset.kind = row.kind;
                item.dataset.id = row.id;
                item.style.cssText = 'padding: 10px 12px; border-radius: 4px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px;';
                // Default + non-default rows get drag enabled (except default, it stays pinned)
                if (row.kind !== 'default') {
                    item.draggable = true;
                    this._wirePresetRowDrag(item);
                }
                if (idx === 0) item.style.background = '#2d4a7a';
                const leftCol = document.createElement('div');
                leftCol.style.cssText = 'flex: 1; min-width: 0; overflow: hidden;';
                leftCol.innerHTML = `<div style="color:#fff; font-size:13px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${this.escapeHtml(row.label)}</div><div style="color:#888; font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${row.sublabel}</div>`;
                item.appendChild(leftCol);
                // Heart on favorite rows (always filled, clicking removes from favorites)
                if (row.kind === 'favorite') {
                    const heartBtn = document.createElement('button');
                    heartBtn.className = 'btn';
                    heartBtn.innerHTML = '♥';
                    heartBtn.title = 'Remove from favorites';
                    heartBtn.style.cssText = 'background: transparent; color: #e25555; font-size: 14px; padding: 2px 8px; border: 1px solid #444;';
                    heartBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        this._toggleCatalogFavorite(row.panel);
                        this._renderPresetPickerLeftColumn();
                        this._renderPanelCatalogList();
                    });
                    item.appendChild(heartBtn);
                }
                if (row.kind === 'preset') {
                    const delBtn = document.createElement('button');
                    delBtn.className = 'btn';
                    delBtn.textContent = '🗑';
                    delBtn.title = `Delete preset "${row.pickerKey}"`;
                    delBtn.style.cssText = 'background: transparent; color: #c55; font-size: 14px; padding: 2px 8px; border: 1px solid #444;';
                    delBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (!confirm(`Delete preset "${row.pickerKey}"?`)) return;
                        this.deletePresetOnServer(row.pickerKey).then(() => {
                            this._renderPresetPickerLeftColumn();
                        }).catch(err => alert('Failed to delete preset: ' + (err && err.error || 'unknown')));
                    });
                    item.appendChild(delBtn);
                }
                item.addEventListener('click', () => {
                    if (row.kind === 'favorite') {
                        this._pickerSelection = { type: 'panel', key: this._favoriteKey(row.panel._mfr, row.panel.name), panel: row.panel, label: row.label };
                    } else {
                        this._pickerSelection = { type: 'preset', key: row.pickerKey, label: row.label };
                    }
                    this._highlightPickerSelection();
                    this._updatePickerSummary();
                });
                list.appendChild(item);
            });
            this._highlightPickerSelection();
        });
    }

    // HTML5 drag-and-drop reorder for the left column. Default row is pinned
    // (not draggable, not a drop target). Order persists in localStorage.
    _wirePresetRowDrag(item) {
        item.addEventListener('dragstart', (e) => {
            this._dragRowId = item.dataset.id;
            item.style.opacity = '0.4';
            try { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', item.dataset.id); } catch {}
        });
        item.addEventListener('dragend', () => {
            item.style.opacity = '';
            this._dragRowId = null;
            document.querySelectorAll('#preset-picker-list .preset-picker-row').forEach(el => {
                el.style.borderTop = '';
                el.style.borderBottom = '';
            });
        });
        item.addEventListener('dragover', (e) => {
            if (!this._dragRowId || this._dragRowId === item.dataset.id) return;
            if (item.dataset.kind === 'default') return;
            e.preventDefault();
            try { e.dataTransfer.dropEffect = 'move'; } catch {}
            const rect = item.getBoundingClientRect();
            const before = (e.clientY - rect.top) < rect.height / 2;
            item.style.borderTop = before ? '2px solid #4A90E2' : '';
            item.style.borderBottom = before ? '' : '2px solid #4A90E2';
        });
        item.addEventListener('dragleave', () => {
            item.style.borderTop = '';
            item.style.borderBottom = '';
        });
        item.addEventListener('drop', (e) => {
            e.preventDefault();
            const draggedId = this._dragRowId;
            const targetId = item.dataset.id;
            if (!draggedId || draggedId === targetId || item.dataset.kind === 'default') return;
            const rect = item.getBoundingClientRect();
            const dropBefore = (e.clientY - rect.top) < rect.height / 2;
            // Build new order from current DOM, excluding default and dragged.
            const ids = Array.from(document.querySelectorAll('#preset-picker-list .preset-picker-row'))
                .map(el => el.dataset.id)
                .filter(id => id && id !== '__default__' && id !== draggedId);
            const insertAt = ids.indexOf(targetId) + (dropBefore ? 0 : 1);
            ids.splice(insertAt, 0, draggedId);
            this.setAddLayerOrder(ids);
            this._renderPresetPickerLeftColumn();
        });
    }

    // ── Panel catalog source-of-truth resolution ──
    // Prefers a cached refresh from GitHub (in localStorage) over the bundled
    // file shipped with this app version. If the user hits Refresh and a
    // newer catalog is fetched, we cache it and every subsequent _loadPanelCatalog
    // call uses the cached copy automatically.
    _getCachedCatalog() {
        try {
            const raw = localStorage.getItem('panelCatalog.cached');
            if (!raw) return null;
            return JSON.parse(raw);
        } catch { return null; }
    }
    _setCachedCatalog(catalog, sha, fetchedAt) {
        try {
            localStorage.setItem('panelCatalog.cached', JSON.stringify(catalog));
            if (sha) localStorage.setItem('panelCatalog.cachedSha', sha);
            if (fetchedAt) localStorage.setItem('panelCatalog.cachedAt', fetchedAt);
        } catch {}
    }
    _getCachedCatalogSha() { return localStorage.getItem('panelCatalog.cachedSha') || ''; }
    _getCachedCatalogAt()  { return localStorage.getItem('panelCatalog.cachedAt') || ''; }

    _ingestCatalog(catalog) {
        this._panelCatalog = catalog || {};
        this._panelCatalogFlat = [];
        Object.keys(this._panelCatalog).forEach(mfr => {
            (this._panelCatalog[mfr] || []).forEach(p => {
                this._panelCatalogFlat.push(Object.assign({ _mfr: mfr, _searchKey: (mfr + ' ' + (p.name || '')).toLowerCase() }, p));
            });
        });
    }

    _loadPanelCatalog() {
        const listEl = document.getElementById('panel-catalog-list');
        const mfrSel = document.getElementById('panel-catalog-mfr');
        const searchEl = document.getElementById('panel-catalog-search');
        const countEl = document.getElementById('panel-catalog-count');
        if (!listEl) return;
        listEl.innerHTML = '<div style="padding: 12px; color: #888; font-size: 12px;">Loading catalog…</div>';
        const finish = () => {
            // Repopulate manufacturer dropdown when source changes (e.g. after refresh).
            if (mfrSel) {
                const cur = mfrSel.value;
                // Clear all but the "All manufacturers" option
                while (mfrSel.options.length > 1) mfrSel.remove(1);
                const mfrs = Object.keys(this._panelCatalog).sort((a, b) => a.localeCompare(b));
                mfrs.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = `${m.replace(/_/g, ' ')} (${this._panelCatalog[m].length})`;
                    mfrSel.appendChild(opt);
                });
                if (cur && Array.from(mfrSel.options).some(o => o.value === cur)) mfrSel.value = cur;
                if (!mfrSel._pickerWired) {
                    mfrSel._pickerWired = true;
                    mfrSel.addEventListener('change', () => this._renderPanelCatalogList());
                }
            }
            if (searchEl && !searchEl._pickerWired) {
                searchEl._pickerWired = true;
                let t;
                searchEl.addEventListener('input', () => {
                    clearTimeout(t);
                    t = setTimeout(() => this._renderPanelCatalogList(), 120);
                });
            }
            if (countEl) {
                const total = Object.values(this._panelCatalog).reduce((s, a) => s + a.length, 0);
                countEl.textContent = `· ${total.toLocaleString()} panels · ${Object.keys(this._panelCatalog).length} mfrs`;
            }
            this._renderPanelCatalogList();
            this._renderCatalogSourceTag();
        };
        if (this._panelCatalog) { finish(); return; }
        // Prefer the cached refreshed catalog if present, else the bundled file.
        const cached = this._getCachedCatalog();
        if (cached) {
            this._ingestCatalog(cached);
            finish();
            return;
        }
        fetch('/static/data/panel_catalog.json').then(r => r.json()).then(data => {
            this._ingestCatalog(data);
            finish();
        }).catch(() => {
            listEl.innerHTML = '<div style="padding: 12px; color: #c55; font-size: 12px;">Failed to load panel catalog.</div>';
        });
    }

    // Background check on app boot, fetches the upstream catalog SHA and
    // stashes the fresh catalog in localStorage if it differs from what the
    // user currently has loaded. Sets `_catalogUpdateAvailable` so the picker
    // can show an "Update available" badge next time it's opened.
    checkPanelCatalogUpdate() {
        // Resolve the user's current effective SHA (cached refresh wins over bundled).
        const cachedSha = this._getCachedCatalogSha();
        const baselineSha = cachedSha || (this._bundledCatalogSha || '');
        const apply = (payload) => {
            if (!payload || !payload.sha) return;
            this._latestCatalogSha = payload.sha;
            this._latestCatalogFetchedAt = payload.fetchedAt || '';
            this._latestCatalogPanelCount = payload.panelCount || 0;
            // Stash the catalog so the user can apply it instantly without
            // another network call when they click the badge.
            if (payload.catalog) this._pendingCatalog = payload.catalog;
            const baseline = cachedSha || (this._bundledCatalogSha || '');
            this._catalogUpdateAvailable = !!baseline && payload.sha !== baseline;
            this._renderCatalogSourceTag();
        };
        // First pull bundled SHA (cheap, no network), then ask the upstream proxy.
        const infoFetch = this._bundledCatalogSha
            ? Promise.resolve({ bundledSha: this._bundledCatalogSha })
            : fetch('/api/panel-catalog/info').then(r => r.json()).then(d => {
                this._bundledCatalogSha = d.bundledSha || '';
                this._bundledCatalogPanelCount = d.panelCount || 0;
                return d;
            }).catch(() => ({}));
        infoFetch.then(() => fetch('/api/panel-catalog/refresh').then(r => r.ok ? r.json() : Promise.reject(r)))
            .then(apply)
            .catch(() => { /* offline / blocked, silently keep current */ });
    }

    // Manual user-triggered refresh from the button in the catalog header.
    refreshPanelCatalogNow(opts = {}) {
        // Re-entrancy guard: if a refresh is already in flight, return that
        // promise instead of starting a parallel one. Spam-clicking the
        // button used to stack 9 fetches behind each other and confuse the
        // UI state.
        if (this._catalogRefreshInFlight) return this._catalogRefreshInFlight;
        const btn = document.getElementById('panel-catalog-refresh-btn');
        if (btn) {
            btn.disabled = true;
            // pointer-events:none belt-and-suspenders the disabled attribute
            // (some bound listeners fire on disabled buttons in webviews).
            btn.style.pointerEvents = 'none';
            btn.style.opacity = '0.6';
            btn.textContent = '↻ Refreshing…';
        }
        // Hard 15s client-side timeout so a hung server can't pin the UI.
        const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        const timeoutId = setTimeout(() => { try { ctrl && ctrl.abort(); } catch {} }, 15000);
        const fetchOpts = ctrl ? { signal: ctrl.signal } : {};
        const p = fetch('/api/panel-catalog/refresh', fetchOpts)
            .then(r => r.ok ? r.json() : r.json().then(b => Promise.reject(b)).catch(() => Promise.reject({status: r.status})))
            .then(payload => {
                if (!payload || !payload.catalog) throw new Error('bad payload');
                this._setCachedCatalog(payload.catalog, payload.sha, payload.fetchedAt);
                this._latestCatalogSha = payload.sha;
                this._latestCatalogFetchedAt = payload.fetchedAt || '';
                this._catalogUpdateAvailable = false;
                this._pendingCatalog = null;
                this._ingestCatalog(payload.catalog);
                this._renderPanelCatalogList();
                this._renderCatalogSourceTag();
                if (!opts.silent) {
                    const count = payload.panelCount || 0;
                    this._toast(`Catalog refreshed, ${count.toLocaleString()} panels`);
                }
            })
            .catch((err) => {
                if (!opts.silent) {
                    const detail = err && err.error ? ` (${err.error})` : '';
                    this._toast(`Couldn’t reach GitHub, keeping current catalog${detail}`, true);
                }
            })
            .finally(() => {
                clearTimeout(timeoutId);
                this._catalogRefreshInFlight = null;
                if (btn) {
                    btn.disabled = false;
                    btn.style.pointerEvents = '';
                    btn.style.opacity = '';
                    btn.textContent = '↻ Refresh';
                }
            });
        this._catalogRefreshInFlight = p;
        return p;
    }

    // Renders the small "source tag" shown in the catalog column header:
    //   - "Bundled (vX.Y.Z)" or "Updated <date>"
    //   - When an update is available, the tag becomes a clickable green pill.
    _renderCatalogSourceTag() {
        const el = document.getElementById('panel-catalog-source-tag');
        if (!el) return;
        const cachedAt = this._getCachedCatalogAt();
        const updateAvail = !!this._catalogUpdateAvailable;
        if (updateAvail) {
            el.style.cssText = 'display:inline-block; cursor:pointer; padding:2px 8px; border-radius:10px; background:#1a5fb4; color:#fff; font-size:10px; font-weight:600; letter-spacing:0.3px;';
            el.textContent = '📦 Update available · click to apply';
            el.title = 'A newer panel catalog is available from GitHub. Click to apply.';
            el.onclick = () => {
                if (this._pendingCatalog) {
                    this._setCachedCatalog(this._pendingCatalog, this._latestCatalogSha, this._latestCatalogFetchedAt);
                    this._ingestCatalog(this._pendingCatalog);
                    this._catalogUpdateAvailable = false;
                    this._pendingCatalog = null;
                    // Re-render dropdown + list with new data
                    this._loadPanelCatalog();
                    this._toast('Catalog updated');
                } else {
                    // Pending data wasn't stashed (boot check failed?), fall back to a fresh refresh
                    this.refreshPanelCatalogNow();
                }
            };
        } else {
            el.style.cssText = 'display:inline-block; padding:2px 0; color:#777; font-size:10px;';
            el.onclick = null;
            if (cachedAt) {
                const d = new Date(cachedAt);
                const when = isNaN(d) ? cachedAt : d.toLocaleDateString();
                el.textContent = `Updated ${when}`;
                el.title = `Catalog last refreshed from GitHub on ${cachedAt}`;
            } else {
                el.textContent = 'Bundled';
                el.title = 'Using the panel catalog bundled with this app version. Click Refresh to pull updates.';
            }
        }
    }

    _toast(msg, isError, durationMs) {
        let host = document.getElementById('app-toast-host');
        if (!host) {
            host = document.createElement('div');
            host.id = 'app-toast-host';
            host.style.cssText = 'position:fixed; bottom:20px; left:50%; transform:translateX(-50%); z-index:11000; display:flex; flex-direction:column; gap:6px; align-items:center;';
            document.body.appendChild(host);
        }
        const t = document.createElement('div');
        t.style.cssText = `padding:10px 16px; border-radius:6px; font-size:13px; color:#fff; background:${isError ? '#a8324b' : '#2d4a7a'}; box-shadow:0 2px 12px rgba(0,0,0,0.4); opacity:0; transition:opacity 0.18s ease; max-width: 520px; text-align: center;`;
        t.textContent = msg;
        host.appendChild(t);
        requestAnimationFrame(() => { t.style.opacity = '1'; });
        const lifetime = (typeof durationMs === 'number' && durationMs > 0) ? durationMs : 2400;
        setTimeout(() => {
            t.style.opacity = '0';
            setTimeout(() => t.remove(), 220);
        }, lifetime);
    }

    // A panel is "verified" if its `source` flags it as cross-checked against
    // the manufacturer's published spec sheet/PDF rather than only FidoLED's
    // (sometimes-outdated) internal database. Treats any source starting with
    // "official:" or containing "spec PDF" / "absen ... PDF" as verified.
    _isPanelVerified(p) {
        const s = (p && p.source || '').toLowerCase();
        if (!s) return false;
        // Anti-patterns: any entry whose specs were inferred rather than read
        // off a real spec sheet/PDF/website is not verified, even if the
        // source string mentions an authoritative site.
        if (/\b(est|estimated|derived|same as|inferred|approx)\b/.test(s)) return false;
        if (/\+\s*(frame|air frame|t4|ladder|windbrace|spotlight)/.test(s)) return false;
        // Trusted sources, manufacturer's own site / PDF, or a reputable
        // third-party dealer that publishes the full datasheet.
        if (s.startsWith('official:')) return true;
        if (s.startsWith('roevisual')) return true;          // roevisual.com (ROE)
        if (s.startsWith('absen ')) return true;             // absen JP / VN spec PDFs
        if (s.startsWith('ledwallcentral')) return true;     // dealer with full datasheets
        if (s.startsWith('xled.pro')) return true;           // dealer datasheet
        if (s.includes('spec pdf')) return true;
        if (s.includes('-specification.pdf')) return true;
        if (s.includes('brochure')) return true;             // any "...brochure" reference
        if (s.includes('per brochure')) return true;
        return false;
    }

    _renderPanelCatalogList() {
        const listEl = document.getElementById('panel-catalog-list');
        const mfrSel = document.getElementById('panel-catalog-mfr');
        const searchEl = document.getElementById('panel-catalog-search');
        if (!listEl || !this._panelCatalogFlat) return;
        const q = (searchEl && searchEl.value || '').trim().toLowerCase();
        const mfrFilter = mfrSel && mfrSel.value || '';
        let rows = this._panelCatalogFlat;
        if (mfrFilter) rows = rows.filter(p => p._mfr === mfrFilter);
        if (q) rows = rows.filter(p => p._searchKey.indexOf(q) !== -1);
        // Cap render to keep DOM light
        const MAX = 300;
        const total = rows.length;
        rows = rows.slice(0, MAX);
        listEl.innerHTML = '';
        if (!total) {
            listEl.innerHTML = '<div style="padding: 12px; color: #888; font-size: 12px;">No panels match.</div>';
            return;
        }
        rows.forEach(p => {
            const item = document.createElement('div');
            item.className = 'panel-catalog-row';
            item.dataset.mfr = p._mfr;
            item.dataset.name = p.name || '';
            item.style.cssText = 'padding: 8px 10px; border-bottom: 1px solid #222; cursor: pointer;';
            const specs = [];
            if (p.width_mm != null && p.height_mm != null) specs.push(`${p.width_mm}×${p.height_mm}mm`);
            if (p.pixels_w != null && p.pixels_h != null) specs.push(`${p.pixels_w}×${p.pixels_h}px`);
            if (p.weight_kg != null) specs.push(`${p.weight_kg}kg`);
            if (p.watts_max != null) specs.push(`${p.watts_max}W`);
            // Verified ⭐: panel specs were cross-checked against the manufacturer's
            // own published spec sheet/PDF (not just FidoLED's database).
            const verified = this._isPanelVerified(p);
            const star = verified ? `<span title="Verified against ${this.escapeHtml(p.source || '')}" style="color:#f5c842; margin-right:4px;">⭐</span>` : '';
            const isFav = this._isCatalogFavorited(p._mfr, p.name);
            // Layout: text on the left, heart pinned on the right.
            item.style.cssText = 'padding: 8px 10px; border-bottom: 1px solid #222; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px;';
            const textCol = document.createElement('div');
            textCol.style.cssText = 'flex: 1; min-width: 0;';
            textCol.innerHTML = `<div style="color:#fff; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${star}<span style="color:#8ab4f8;">${this.escapeHtml(p._mfr.replace(/_/g, ' '))}</span> · ${this.escapeHtml(p.name || '')}</div><div style="color:#888; font-size:11px;">${specs.join(' · ')}</div>`;
            item.appendChild(textCol);
            const heartBtn = document.createElement('button');
            heartBtn.className = 'btn';
            heartBtn.innerHTML = isFav ? '♥' : '♡';
            heartBtn.title = isFav ? 'Remove from favorites' : 'Add to favorites';
            heartBtn.style.cssText = `background: transparent; color: ${isFav ? '#e25555' : '#888'}; font-size: 14px; padding: 2px 8px; border: 1px solid #333;`;
            heartBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this._toggleCatalogFavorite(p);
                this._renderPanelCatalogList();
                this._renderPresetPickerLeftColumn();
            });
            item.appendChild(heartBtn);
            item.addEventListener('click', () => {
                this._pickerSelection = { type: 'panel', key: p._mfr + '|' + p.name, panel: p, label: `${p._mfr.replace(/_/g,' ')} ${p.name}` };
                this._highlightPickerSelection();
                this._updatePickerSummary();
            });
            listEl.appendChild(item);
        });
        if (total > MAX) {
            const more = document.createElement('div');
            more.style.cssText = 'padding: 8px 10px; color: #888; font-size: 11px; text-align: center; background: #1d1d1d;';
            more.textContent = `Showing first ${MAX} of ${total.toLocaleString()}. Refine search or pick a manufacturer.`;
            listEl.appendChild(more);
        }
        this._highlightPickerSelection();
    }

    _highlightPickerSelection() {
        const sel = this._pickerSelection || {};
        document.querySelectorAll('#preset-picker-list .preset-picker-row').forEach(el => {
            const kind = el.dataset.kind;
            let match = false;
            if (kind === 'favorite') {
                match = sel.type === 'panel' && el.dataset.key === sel.key;
            } else {
                match = sel.type === 'preset' && el.dataset.key === sel.key;
            }
            el.style.background = match ? '#2d4a7a' : 'transparent';
        });
        document.querySelectorAll('#panel-catalog-list .panel-catalog-row').forEach(el => {
            const key = el.dataset.mfr + '|' + el.dataset.name;
            el.style.background = (sel.type === 'panel' && key === sel.key) ? '#2d4a7a' : 'transparent';
        });
    }

    _updatePickerSummary() {
        const summary = document.getElementById('preset-picker-summary');
        if (!summary) return;
        const sel = this._pickerSelection || {};
        if (sel.type === 'panel' && sel.panel) {
            const p = sel.panel;
            const parts = [];
            if (p.width_mm != null) parts.push(`${p.width_mm}×${p.height_mm}mm`);
            if (p.pixels_w != null) parts.push(`${p.pixels_w}×${p.pixels_h}px`);
            if (p.weight_kg != null) parts.push(`${p.weight_kg}kg`);
            if (p.watts_max != null) parts.push(`${p.watts_max}W`);
            summary.textContent = `Panel: ${sel.label}, ${parts.join(' · ')}`;
        } else if (sel.type === 'preset' && sel.key && sel.key !== '__default__') {
            summary.textContent = `Preset: ${sel.label || sel.key}`;
        } else {
            summary.textContent = 'Default, uses your Preferences values.';
        }
    }

    closePresetPicker() {
        const modal = document.getElementById('preset-picker-modal');
        if (modal) modal.style.display = 'none';
    }

    confirmPresetPicker() {
        const sel = this._pickerSelection || { type: 'preset', key: '__default__' };
        this.closePresetPicker();
        if (sel.type === 'panel' && sel.panel) {
            this.addLayer(this._panelToPresetData(sel.panel));
            return;
        }
        if (sel.type === 'preset') {
            if (!sel.key || sel.key === '__default__') {
                this.addLayer();
                return;
            }
            this.fetchPreset(sel.key).then(resp => {
                const data = resp && resp.data ? resp.data : null;
                if (data) data._presetName = sel.key;
                this.addLayer(data);
            }).catch(err => {
                alert('Failed to load preset: ' + (err && err.error || 'unknown'));
                this.addLayer();
            });
        }
    }

    // Convert a catalog panel into preset-shaped data that addLayer() consumes.
    // Grid (columns/rows) comes from Preferences; panel-specific fields override.
    _panelToPresetData(panel) {
        const prefs = this.getPreferences() || {};
        const weightUnit = prefs.weightUnit || 'kg';
        const weightKg = panel.weight_kg;
        const weight = (weightKg != null)
            ? (weightUnit === 'lb' ? +(weightKg * 2.20462).toFixed(2) : weightKg)
            : prefs.panelWeight;
        const data = {
            columns: prefs.columns,
            rows: prefs.rows,
            cabinet_width: panel.pixels_w != null ? panel.pixels_w : prefs.panelWidth,
            cabinet_height: panel.pixels_h != null ? panel.pixels_h : prefs.panelHeight,
            panel_width_mm: panel.width_mm,
            panel_height_mm: panel.height_mm,
            panel_weight: weight,
            weight_unit: weightUnit,
            _presetName: `${(panel._mfr || panel.manufacturer || '').replace(/_/g, ' ')} ${panel.name}`.trim()
        };
        if (panel.watts_max != null) data.panelWatts = panel.watts_max;
        return data;
    }

    // ── Spec correction / new-panel submission ──
    // Opens a pre-filled GitHub issue so users can submit a PDF spec sheet,
    // a back-of-panel photo, just flag bad data, or request a brand-new
    // panel that's missing from the catalog. Zero-server: GitHub hosts the
    // upload (drag-drop into the issue comment), we read it on our normal
    // triage workflow, no API keys / S3 / email gateway needed.
    openPanelSpecCorrection() {
        const sel = this._pickerSelection || {};
        const hasSelection = sel.type === 'panel' && sel.panel;

        // Branch: correction (existing panel) vs. new panel (missing one).
        // confirm() returns true=OK ("Fix existing"), false=Cancel ("Add new").
        // If the user already selected a panel in the catalog, default to fix.
        let mode;
        if (hasSelection) {
            mode = 'fix';
        } else {
            const choice = window.confirm(
                'Submit which kind of correction?\n\n' +
                '  OK   = "Fix specs on an existing panel"\n' +
                '  Cancel = "Add a panel that\'s missing from the catalog"'
            );
            mode = choice ? 'fix' : 'add';
        }

        let panelRef = '';
        let currentValues = '';
        if (hasSelection) {
            const p = sel.panel;
            panelRef = `${(p._mfr || p.manufacturer || '').replace(/_/g, ' ')} ${p.name}`.trim();
            const lines = [];
            if (p.width_mm != null) lines.push(`- Cabinet: ${p.width_mm} × ${p.height_mm} mm`);
            if (p.pixels_w != null) lines.push(`- Pixels: ${p.pixels_w} × ${p.pixels_h}`);
            if (p.weight_kg != null) lines.push(`- Weight: ${p.weight_kg} kg`);
            if (p.watts_max != null) lines.push(`- Max power: ${p.watts_max} W`);
            if (p.source) lines.push(`- Source: ${p.source}`);
            currentValues = lines.join('\n');
        } else {
            const ask = (mode === 'fix')
                ? 'Which panel has bad specs? (e.g. "Absen JP8 Pro")\n\nTip: select the panel in the catalog first to pre-fill this.'
                : 'What panel is missing? Manufacturer + model name (e.g. "Absen NEW-X 1.5")';
            panelRef = window.prompt(ask, '') || '';
            if (!panelRef) return;
        }

        const notesPrompt = (mode === 'fix')
            ? `What's wrong with "${panelRef}"?\n\nDescribe the discrepancy. After you click OK we'll open a GitHub issue, drag any spec sheet PDF or a photo of the panel back into the comment box there to attach it.`
            : `Tell us about "${panelRef}", paste any specs you have (cabinet mm, pixels, weight, max watts).\n\nAfter you click OK we'll open a GitHub issue, drag the official spec sheet PDF or a photo of the panel back into the comment box to attach it.`;
        const notes = window.prompt(notesPrompt, '');
        if (notes === null) return;  // cancelled

        const versionEl = document.querySelector('h1 span');
        const appVersion = (versionEl && versionEl.textContent) || '';

        const bodyLines = (mode === 'fix') ? [
            `**Panel:** ${panelRef}`,
            '',
            '**Current catalog values:**',
            currentValues || '_(no panel selected, please paste the catalog values you saw)_',
            '',
            '**What\'s wrong:**',
            notes || '_(left blank)_',
            '',
            '**Spec sheet / photo:**',
            '⬆️ Drag a PDF or photo into this comment box to attach it.',
            '',
            '---',
            `App version: ${appVersion}`,
        ] : [
            `**Panel to add:** ${panelRef}`,
            '',
            '**Specs (best-guess from user):**',
            notes || '_(left blank)_',
            '',
            '**Spec sheet / photo:**',
            '⬆️ Drag the official spec sheet PDF or a photo of the panel back into this comment box to attach it.',
            '',
            '---',
            `App version: ${appVersion}`,
        ];
        const titlePrefix = (mode === 'fix') ? 'Spec correction' : 'Add panel';
        const label = (mode === 'fix') ? 'spec-correction' : 'add-panel';
        const params = new URLSearchParams({
            title: `${titlePrefix}: ${panelRef}`,
            labels: label,
            body: bodyLines.join('\n'),
        });
        const url = `https://github.com/kman1898/LED-Raster-Designer/issues/new?${params.toString()}`;
        // Make sure the user knows the GitHub tab is the actual submission,
        // we've had submissions get lost because the user filled out the
        // app-side prompts and assumed that was enough.
        const ok = confirm(
            'This will open GitHub in a new tab with your submission pre-filled.\n\n' +
            'IMPORTANT: You must be signed in to GitHub and click the green "Submit new issue" button there for it to actually reach us.\n\n' +
            'Continue?'
        );
        if (!ok) return;
        window.open(url, '_blank', 'noopener');
    }

    // ── Save-as-Preset Modal ──
    openPresetSaveModal() {
        if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'screen') {
            alert('Select a screen layer first to save as a preset.');
            return;
        }
        const modal = document.getElementById('preset-save-modal');
        const nameInput = document.getElementById('preset-save-name');
        const warning = document.getElementById('preset-save-warning');
        const sublabel = document.getElementById('preset-save-sublabel');
        if (!modal || !nameInput) return;
        nameInput.value = this.currentLayer.name || '';
        warning.textContent = '';
        if (sublabel) sublabel.textContent = `Saving settings from "${this.currentLayer.name || 'current layer'}".`;
        modal.style.display = 'block';
        setTimeout(() => nameInput.focus(), 50);
        this._presetSaveExistingNames = null;
        this._renderPresetSaveExistingList([]);
        this.updatePresetSaveConfirmButton();
        this.fetchPresetList().then(list => {
            this._presetSaveExistingNames = list;
            this._renderPresetSaveExistingList(list);
            this.updatePresetSaveWarning();
            this.updatePresetSaveConfirmButton();
        });
    }

    _renderPresetSaveExistingList(names) {
        const section = document.getElementById('preset-save-existing-section');
        const list = document.getElementById('preset-save-existing-list');
        if (!section || !list) return;
        list.innerHTML = '';
        if (!Array.isArray(names) || names.length === 0) {
            section.style.display = 'none';
            return;
        }
        section.style.display = 'block';
        names.forEach(name => {
            const row = document.createElement('div');
            row.className = 'preset-save-existing-row';
            row.style.cssText = 'padding: 6px 8px; color: #ddd; font-size: 12px; cursor: pointer; border-radius: 3px;';
            row.textContent = name;
            row.title = `Click to overwrite "${name}"`;
            row.addEventListener('mouseenter', () => { row.style.background = '#2d4a7a'; });
            row.addEventListener('mouseleave', () => { row.style.background = 'transparent'; });
            row.addEventListener('click', () => {
                const nameInput = document.getElementById('preset-save-name');
                if (nameInput) {
                    nameInput.value = name;
                    nameInput.focus();
                    this.updatePresetSaveWarning();
                    this.updatePresetSaveConfirmButton();
                }
            });
            list.appendChild(row);
        });
    }

    updatePresetSaveConfirmButton() {
        const btn = document.getElementById('preset-save-confirm');
        const nameInput = document.getElementById('preset-save-name');
        if (!btn || !nameInput) return;
        const name = nameInput.value.trim();
        const existing = this._presetSaveExistingNames || [];
        if (name && existing.includes(name)) {
            btn.textContent = 'Overwrite';
        } else {
            btn.textContent = 'Save';
        }
    }

    closePresetSaveModal() {
        const modal = document.getElementById('preset-save-modal');
        if (modal) modal.style.display = 'none';
    }

    updatePresetSaveWarning() {
        const nameInput = document.getElementById('preset-save-name');
        const warning = document.getElementById('preset-save-warning');
        if (!nameInput || !warning) return;
        const name = nameInput.value.trim();
        if (!name) {
            warning.textContent = '';
            return;
        }
        const existing = this._presetSaveExistingNames || [];
        if (existing.includes(name)) {
            warning.textContent = `⚠ A preset named "${name}" already exists. Saving will overwrite it.`;
        } else {
            warning.textContent = '';
        }
    }

    confirmPresetSave() {
        const nameInput = document.getElementById('preset-save-name');
        const warning = document.getElementById('preset-save-warning');
        if (!nameInput) return;
        const name = nameInput.value.trim();
        if (!name) {
            warning.textContent = 'Please enter a name.';
            return;
        }
        const existing = this._presetSaveExistingNames || [];
        if (existing.includes(name)) {
            if (!confirm(`A preset named "${name}" already exists. Overwrite it?`)) return;
        }
        const data = this.serializeLayerAsPreset(this.currentLayer);
        if (!data) {
            warning.textContent = 'No layer selected.';
            return;
        }
        this.savePresetToServer(name, data).then(() => {
            this.closePresetSaveModal();
        }).catch(err => {
            warning.textContent = 'Failed: ' + (err && err.error || 'unknown error');
        });
    }

    setupPresetModals() {
        const pickerCancel = document.getElementById('preset-picker-cancel');
        const pickerAdd = document.getElementById('preset-picker-add');
        if (pickerCancel) pickerCancel.addEventListener('click', () => this.closePresetPicker());
        if (pickerAdd) pickerAdd.addEventListener('click', () => this.confirmPresetPicker());

        const submitLink = document.getElementById('panel-submit-correction');
        if (submitLink) submitLink.addEventListener('click', (e) => {
            e.preventDefault();
            this.openPanelSpecCorrection();
        });

        const refreshBtn = document.getElementById('panel-catalog-refresh-btn');
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.refreshPanelCatalogNow());

        const saveCancel = document.getElementById('preset-save-cancel');
        const saveConfirm = document.getElementById('preset-save-confirm');
        const saveName = document.getElementById('preset-save-name');
        if (saveCancel) saveCancel.addEventListener('click', () => this.closePresetSaveModal());
        if (saveConfirm) saveConfirm.addEventListener('click', () => this.confirmPresetSave());
        if (saveName) {
            saveName.addEventListener('input', () => {
                this.updatePresetSaveWarning();
                this.updatePresetSaveConfirmButton();
            });
            saveName.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this.confirmPresetSave();
                else if (e.key === 'Escape') this.closePresetSaveModal();
            });
        }
        // Close modals on backdrop click
        ['preset-picker-modal', 'preset-save-modal'].forEach(id => {
            const m = document.getElementById(id);
            if (m) {
                m.addEventListener('click', (e) => {
                    if (e.target === m) m.style.display = 'none';
                });
            }
        });
    }

    escapeHtml(s) {
        if (s == null) return '';
        return String(s).replace(/[&<>"']/g, ch => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
        ));
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

    addTextLayer() {
        const name = this.getNextTextLayerName();
        this.saveState('Add Text Layer');
        fetch('/api/layer/add-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, textContent: '', offset_x: 0, offset_y: 0 })
        })
        .then(res => res.json())
        .then(layer => {
            sendClientLog('add_text_layer', { id: layer.id, name: layer.name });
            this.upsertProjectLayer(layer);
            this.selectLayer(layer);
            window.canvasRenderer.fitToView();
            window.canvasRenderer.render();
            this.saveClientSideProperties();
        });
    }

    getNextTextLayerName() {
        const base = 'Text';
        const existing = this.project.layers
            .filter(l => (l.type || 'screen') === 'text')
            .map(l => l.name || '')
            .filter(name => name.startsWith(base));
        let maxNum = 0;
        existing.forEach(name => {
            const m = name.match(/^Text\s*(\d+)$/i);
            if (m) maxNum = Math.max(maxNum, parseInt(m[1], 10));
        });
        return `Text ${maxNum + 1}`;
    }

    // Map current view mode to the per-tab text content property
    getTextContentPropForTab() {
        const viewMode = window.canvasRenderer ? window.canvasRenderer.viewMode : 'pixel-map';
        const map = {
            'pixel-map': 'textContentPixelMap',
            'cabinet-id': 'textContentCabinetId',
            'show-look': 'textContentShowLook',
            'data-flow': 'textContentDataFlow',
            'power': 'textContentPower'
        };
        return map[viewMode] || 'textContentPixelMap';
    }

    // v0.8.3: per-tab override flag prop name for the current view mode.
    getTextContentOverridePropForTab() {
        const viewMode = window.canvasRenderer ? window.canvasRenderer.viewMode : 'pixel-map';
        const map = {
            'pixel-map': 'textContentOverridePixelMap',
            'cabinet-id': 'textContentOverrideCabinetId',
            'show-look': 'textContentOverrideShowLook',
            'data-flow': 'textContentOverrideDataFlow',
            'power': 'textContentOverridePower'
        };
        return map[viewMode] || 'textContentOverridePixelMap';
    }

    // v0.8.3: resolve the text shown for `layer` on the active tab.
    // If the tab override is on, use that tab's own field; else use the
    // shared `textContent`. Falls back to any non-empty per-tab field for
    // legacy projects (pre-v0.8.3) where shared was empty but per-tab had
    // content.
    resolveTextContentForActiveTab(layer) {
        if (!layer) return '';
        const overrideProp = this.getTextContentOverridePropForTab();
        const tabProp = this.getTextContentPropForTab();
        if (layer[overrideProp]) return layer[tabProp] || '';
        if (layer.textContent) return layer.textContent;
        // Legacy fallback: a project saved before v0.8.3 might have content
        // only in the per-tab fields. Surface whatever's there so the user
        // can see and edit it.
        const legacyKeys = ['textContentPixelMap', 'textContentCabinetId',
                            'textContentShowLook', 'textContentDataFlow',
                            'textContentPower'];
        for (const k of legacyKeys) {
            if (layer[k]) return layer[k];
        }
        return '';
    }

    getTextTabLabel() {
        const viewMode = window.canvasRenderer ? window.canvasRenderer.viewMode : 'pixel-map';
        const map = {
            'pixel-map': '(Pixel Map)',
            'cabinet-id': '(Cabinet ID)',
            'show-look': '(Show Look)',
            'data-flow': '(Data)',
            'power': '(Power)'
        };
        return map[viewMode] || '(Pixel Map)';
    }

    setupTextLayerControls() {
        // Text content textarea. v0.8.3: writes to the shared `textContent`
        // field by default; if the per-tab override is on, writes to that
        // tab's own `textContent<Tab>` instead.
        const contentEl = document.getElementById('text-layer-content');
        if (contentEl) {
            contentEl.addEventListener('input', () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                const overrideProp = this.getTextContentOverridePropForTab();
                const tabProp = this.getTextContentPropForTab();
                const val = contentEl.value;
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    if (layer[overrideProp]) {
                        layer[tabProp] = val;
                    } else {
                        layer.textContent = val;
                    }
                });
                this.debouncedSaveState('Update Text Label');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        // v0.8.3: per-tab content override checkbox. Toggling ON seeds the
        // per-tab field with the currently displayed (shared) text so the
        // user has something to edit instead of an empty box. Toggling OFF
        // reverts the textarea to the shared text without touching the
        // per-tab value (so re-enabling restores their previous override).
        const overrideEl = document.getElementById('text-layer-content-override');
        if (overrideEl) {
            overrideEl.addEventListener('change', () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                const overrideProp = this.getTextContentOverridePropForTab();
                const tabProp = this.getTextContentPropForTab();
                const enabling = overrideEl.checked;
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    layer[overrideProp] = enabling;
                    if (enabling && !layer[tabProp]) {
                        // Seed override with current shared value so user
                        // doesn't lose context when flipping the checkbox.
                        layer[tabProp] = layer.textContent || '';
                    }
                });
                this.saveState('Toggle Text Tab Override');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                this.updateLayerControls();
                window.canvasRenderer.render();
            });
        }

        const fields = [
            { id: 'text-layer-font-size', prop: 'fontSize', type: 'number' },
            { id: 'text-layer-align', prop: 'textAlign', type: 'select' },
            { id: 'text-layer-width', prop: 'textWidth', type: 'number' },
            { id: 'text-layer-height', prop: 'textHeight', type: 'number' },
            { id: 'text-layer-bg-opacity', prop: 'bgOpacity', type: 'float' },
            { id: 'text-layer-padding', prop: 'textPadding', type: 'number' },
            { id: 'text-layer-show-border', prop: 'showBorder', type: 'checkbox' },
            { id: 'text-layer-show-raster-size', prop: 'showRasterSize', type: 'checkbox' },
            { id: 'text-layer-show-project-name', prop: 'showProjectName', type: 'checkbox' },
            { id: 'text-layer-show-date', prop: 'showDate', type: 'checkbox' },
            { id: 'text-layer-show-primary-ports', prop: 'showPrimaryPorts', type: 'checkbox' },
            { id: 'text-layer-show-backup-ports', prop: 'showBackupPorts', type: 'checkbox' },
            { id: 'text-layer-show-circuits', prop: 'showCircuits', type: 'checkbox' },
            { id: 'text-layer-show-single-phase', prop: 'showSinglePhase', type: 'checkbox' },
            { id: 'text-layer-show-three-phase', prop: 'showThreePhase', type: 'checkbox' },
            // Slice 10: scope dropdown for the dynamic data/power lines.
            // 'canvas' = text layer's parent canvas, 'project' = all canvases,
            // 'both' = render both lines per metric.
            { id: 'text-layer-dynamic-info-scope', prop: 'dynamicInfoScope', type: 'select' },
            { id: 'text-layer-show-pixel-map', prop: 'showOnPixelMap', type: 'checkbox' },
            { id: 'text-layer-show-cabinet-id', prop: 'showOnCabinetId', type: 'checkbox' },
            { id: 'text-layer-show-show-look', prop: 'showOnShowLook', type: 'checkbox' },
            { id: 'text-layer-show-data-flow', prop: 'showOnDataFlow', type: 'checkbox' },
            { id: 'text-layer-show-power', prop: 'showOnPower', type: 'checkbox' },
        ];
        fields.forEach(f => {
            const el = document.getElementById(f.id);
            if (!el) return;
            const event = f.type === 'checkbox' ? 'change' : (f.type === 'select' ? 'change' : 'input');
            el.addEventListener(event, () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                let val;
                if (f.type === 'checkbox') val = el.checked;
                else if (f.type === 'number') val = parseInt(el.value, 10) || 0;
                else if (f.type === 'float') val = parseFloat(el.value) || 0;
                else val = el.value;
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    layer[f.prop] = val;
                });
                this.debouncedSaveState('Update Text Label');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        });
        // Color pickers
        const setupColorSync = (pickerId, hexId, prop) => {
            const picker = document.getElementById(pickerId);
            const hex = document.getElementById(hexId);
            if (!picker || !hex) return;
            const apply = (val) => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    layer[prop] = val;
                });
                this.debouncedSaveState('Update Text Color');
                this.saveClientSideProperties();
                window.canvasRenderer.render();
            };
            picker.addEventListener('input', () => { hex.value = picker.value.toUpperCase(); apply(picker.value); });
            hex.addEventListener('change', () => { picker.value = hex.value; apply(hex.value); });
        };
        setupColorSync('text-layer-font-color', 'text-layer-font-color-hex', 'fontColor');
        setupColorSync('text-layer-bg-color', 'text-layer-bg-color-hex', 'bgColor');

        // Bold / Italic / Underline toggle buttons
        const setupStyleToggle = (btnId, prop) => {
            const btn = document.getElementById(btnId);
            if (!btn) return;
            btn.addEventListener('click', () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                const newVal = !this.currentLayer[prop];
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    layer[prop] = newVal;
                });
                btn.classList.toggle('active', newVal);
                this.debouncedSaveState('Update Text Style');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        };
        setupStyleToggle('text-layer-bold', 'fontBold');
        setupStyleToggle('text-layer-italic', 'fontItalic');
        setupStyleToggle('text-layer-underline', 'fontUnderline');
    }

    loadTextLayerToInputs() {
        const panel = document.getElementById('text-layer-panel');
        if (!panel) return;
        const layer = this.currentLayer;
        if (!layer || (layer.type || 'screen') !== 'text') {
            panel.style.display = 'none';
            return;
        }
        panel.style.display = 'block';
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
        const setChecked = (id, val) => { const el = document.getElementById(id); if (el) el.checked = val; };

        // v0.8.3: textarea reflects shared content unless this tab is
        // overridden, in which case it reflects this tab's own field.
        const overrideProp = this.getTextContentOverridePropForTab();
        const isOverride = !!layer[overrideProp];
        setVal('text-layer-content', this.resolveTextContentForActiveTab(layer));
        setChecked('text-layer-content-override', isOverride);

        // Update tab indicator: append "(override)" when active tab is on its
        // own content so it's obvious why typing only affects this tab.
        const tabIndicator = document.getElementById('text-layer-tab-indicator');
        if (tabIndicator) {
            tabIndicator.textContent = isOverride
                ? `${this.getTextTabLabel()} · OVERRIDE`
                : '· SHARED ACROSS TABS';
        }

        setVal('text-layer-font-size', layer.fontSize || 24);
        setVal('text-layer-align', layer.textAlign || 'left');
        setVal('text-layer-width', layer.textWidth || 400);
        setVal('text-layer-height', layer.textHeight || 100);
        setVal('text-layer-font-color', layer.fontColor || '#ffffff');
        setVal('text-layer-font-color-hex', (layer.fontColor || '#ffffff').toUpperCase());
        setVal('text-layer-bg-color', layer.bgColor || '#000000');
        setVal('text-layer-bg-color-hex', (layer.bgColor || '#000000').toUpperCase());
        setVal('text-layer-bg-opacity', layer.bgOpacity != null ? layer.bgOpacity : 0.7);
        setVal('text-layer-padding', layer.textPadding || 12);
        setChecked('text-layer-show-border', layer.showBorder !== false);
        setChecked('text-layer-show-raster-size', !!layer.showRasterSize);
        setChecked('text-layer-show-project-name', !!layer.showProjectName);
        setChecked('text-layer-show-date', !!layer.showDate);
        setChecked('text-layer-show-pixel-map', layer.showOnPixelMap !== false);
        setChecked('text-layer-show-cabinet-id', layer.showOnCabinetId !== false);
        setChecked('text-layer-show-show-look', layer.showOnShowLook !== false);
        setChecked('text-layer-show-data-flow', layer.showOnDataFlow !== false);
        setChecked('text-layer-show-power', layer.showOnPower !== false);
        setChecked('text-layer-show-primary-ports', !!layer.showPrimaryPorts);
        setChecked('text-layer-show-backup-ports', !!layer.showBackupPorts);
        setChecked('text-layer-show-circuits', !!layer.showCircuits);
        setChecked('text-layer-show-single-phase', !!layer.showSinglePhase);
        setChecked('text-layer-show-three-phase', !!layer.showThreePhase);
        const scopeSel = document.getElementById('text-layer-dynamic-info-scope');
        if (scopeSel) scopeSel.value = layer.dynamicInfoScope || 'project';

        // Style toggle buttons
        const boldBtn = document.getElementById('text-layer-bold');
        const italicBtn = document.getElementById('text-layer-italic');
        const underlineBtn = document.getElementById('text-layer-underline');
        if (boldBtn) boldBtn.classList.toggle('active', !!layer.fontBold);
        if (italicBtn) italicBtn.classList.toggle('active', !!layer.fontItalic);
        if (underlineBtn) underlineBtn.classList.toggle('active', !!layer.fontUnderline);
    }

    // Aggregate data port counts across all visible screen layers.
    // Slice 9: exclude layers whose canvas is hidden.
    // Slice 10: optional onlyCanvasId filter for per-canvas sidebar totals.
    getPortCounts(onlyCanvasId) {
        if (!this.project || !this.project.layers) return { primary: 0, backup: 0 };
        let totalPrimary = 0;
        const hiddenCanvasIds = this._hiddenCanvasIdSet();
        this.project.layers.forEach(layer => {
            if ((layer.type || 'screen') !== 'screen') return;
            if (!layer.visible) return;
            if (layer.canvas_id && hiddenCanvasIds.has(layer.canvas_id)) return;
            if (onlyCanvasId && layer.canvas_id !== onlyCanvasId) return;
            const activePanels = (layer.panels || []).filter(p => !p.blank && !p.hidden);
            if (activePanels.length === 0) return;
            const assignments = this.calculatePortAssignments(layer);
            if (!assignments || assignments.length === 0) return;
            const ports = new Set();
            assignments.forEach(a => {
                if (a && a.port) ports.add(a.port);
            });
            totalPrimary += ports.size;
        });
        // Every primary port has a backup/return port
        return { primary: totalPrimary, backup: totalPrimary };
    }

    // Aggregate power stats across all visible screen layers.
    // Slice 9: exclude layers whose canvas is hidden.
    // Slice 10: optional onlyCanvasId filter for per-canvas sidebar totals.
    getPowerCounts(onlyCanvasId) {
        if (!this.project || !this.project.layers) return { circuits: 0, totalWatts: 0, singlePhaseAmps: 0, threePhaseAmps: 0, voltage: 0 };
        let totalCircuits = 0;
        let totalWattsAll = 0;
        const voltages = new Set();
        const hiddenCanvasIds = this._hiddenCanvasIdSet();
        this.project.layers.forEach(layer => {
            if ((layer.type || 'screen') !== 'screen') return;
            if (!layer.visible) return;
            if (layer.canvas_id && hiddenCanvasIds.has(layer.canvas_id)) return;
            if (onlyCanvasId && layer.canvas_id !== onlyCanvasId) return;
            const activePanels = (layer.panels || []).filter(p => !p.blank && !p.hidden);
            if (activePanels.length === 0) return;
            const voltage = Number(layer.powerVoltage) || 110;
            const amperage = Number(layer.powerAmperage) || 20;
            const panelWatts = Number(layer.panelWatts) || 200;
            voltages.add(voltage);
            const equivalentPanels = activePanels.reduce((sum, p) => sum + this.getPanelLoadFactor(layer, p), 0);
            const layerWatts = panelWatts * equivalentPanels;
            totalWattsAll += layerWatts;
            const circuitWatts = voltage * amperage;
            if (circuitWatts > 0) {
                totalCircuits += Math.ceil(layerWatts / circuitWatts);
            }
        });
        const voltage = [...voltages][0] || 110;
        const singlePhaseAmps = voltage > 0 ? totalWattsAll / voltage : 0;
        const threePhaseAmps = voltage > 0 ? totalWattsAll / (voltage * 1.73) : 0;
        return { circuits: totalCircuits, totalWatts: totalWattsAll, singlePhaseAmps, threePhaseAmps, voltage };
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
        if ((layer.type || 'screen') === 'text') {
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
        // Only fall back to prefs if the server-created layer didn't already
        // carry these from the add request (e.g. from a preset or catalog panel).
        if (layer.panel_weight == null) layer.panel_weight = prefs.panelWeight;
        if (layer.weight_unit == null) layer.weight_unit = prefs.weightUnit || 'kg';
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
        // Slice 4 + Slice 13: auto-activate this layer's canvas, but PRESERVE
        // any existing cross-canvas multi-selection. Without this flag,
        // setActiveCanvas would drop selected layers in other canvases - which
        // breaks the "select layers across canvases and bulk-edit them" flow
        // (e.g. shift-click SR in c1, then DJ in c2, then change panel size on
        // both at once).
        this._activateCanvasForLayer(this.currentLayer, { preserveSelection: true });
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
        // Slice 4 + Slice 13: same preserveSelection trick as
        // toggleLayerSelection so a shift-click range selection that crosses
        // canvas boundaries doesn't get its other-canvas members culled
        // when the active canvas auto-switches.
        this._activateCanvasForLayer(layer, { preserveSelection: true });
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

    // v0.8: workspace offset for the layer's parent canvas. Used by every
    // rect-test that compares workspace-coord rectangles against panel-coord
    // (canvas-relative) panel positions. Returns {wx:0, wy:0} for legacy
    // single-canvas projects so existing math is unaffected.
    _getLayerWorkspaceOffset(layer) {
        if (!layer || !this.project) return { wx: 0, wy: 0 };
        const arr = this.project.canvases;
        if (!Array.isArray(arr) || arr.length === 0) return { wx: 0, wy: 0 };
        const cid = layer.canvas_id;
        if (!cid) return { wx: 0, wy: 0 };
        for (const c of arr) {
            if (c && c.id === cid) return { wx: c.workspace_x || 0, wy: c.workspace_y || 0 };
        }
        return { wx: 0, wy: 0 };
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
            // Shift bounds by the layer's canvas's workspace offset so they
            // line up with the workspace-coord rect (rect is in screen-world
            // space; bounds are canvas-relative).
            const off = this._getLayerWorkspaceOffset(layer);
            const intersects = (b.x1 + off.wx) <= maxX && (b.x2 + off.wx) >= minX
                && (b.y1 + off.wy) <= maxY && (b.y2 + off.wy) >= minY;
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
        // Slice 4 + v0.8.3: auto-activate the canvas of the new primary
        // layer, but pass preserveSelection so a marquee that crosses
        // canvas boundaries doesn't clobber the multi-layer selection
        // we just built. Without this, the first drag-select on Data /
        // Power / Cabinet ID would silently drop everything from the
        // non-active canvas.
        this._activateCanvasForLayer(this.currentLayer, { preserveSelection: true });
        this.renderLayers();
        this.loadLayerToInputs();
        this.loadTextLayerToInputs();
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
        // Slice 4: auto-activate this layer's canvas. Idempotent, short-
        // circuits when already active so programmatic selectLayer calls
        // (post-load, post-create, post-delete) don't fire spurious PUTs.
        this._activateCanvasForLayer(layer);
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
        this.loadTextLayerToInputs();
        // Repopulate the active view's per-layer label editor so the port-rename
        // (data-flow view) or circuit-rename (power view) sidebar reflects the
        // newly selected layer immediately. Without this, the editor only
        // refreshed the next time something else nudged it, which made the
        // first click after a layer-change appear empty until a second click.
        const viewMode = window.canvasRenderer && window.canvasRenderer.viewMode;
        if (viewMode === 'data-flow') {
            this.updatePortLabelEditor();
        } else if (viewMode === 'power') {
            this.updatePowerLabelEditor();
        }
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
                // Show Look position, keep in sync across the server
                // round-trip (server whitelists the field, but echoing the
                // same value is safer than dropping it).
                showOffsetX: layer.showOffsetX,
                showOffsetY: layer.showOffsetY,
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
                // Preserve client-computed port counts across the server
                // roundtrip, server doesn't whitelist these fields, so its
                // echo carries stale values that would otherwise overwrite
                // the freshly recomputed numbers (causes ports-required and
                // the port-rename editor to show too few ports in custom
                // flow mode after toggling).
                _portsRequired: layer._portsRequired,
                _autoPortsRequired: layer._autoPortsRequired,
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
                } else if (window.canvasRenderer.viewMode === 'data-flow') {
                    this.updatePortCapacityDisplay();
                    this.updatePortLabelEditor();
                }
                // Always re-render after server response to reflect final state
                window.canvasRenderer.render();
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
        const showOffsetXVal = readNumber('show-offset-x').value;
        const showOffsetYVal = readNumber('show-offset-y').value;

        // For multi-select: only apply the offset field that was actually changed by the user.
        // This prevents typing in Y from overwriting all layers' X values (or vice versa).
        const multiSelected = targetLayers.length > 1;
        const lastChanged = this._lastChangedInputId || null;
        const applyOffsetX = offsetXVal !== null && (!multiSelected || lastChanged === 'offset-x');
        const applyOffsetY = offsetYVal !== null && (!multiSelected || lastChanged === 'offset-y');
        // Show-offset writes are gated strictly on lastChanged so that editing
        // the pixel-map offset doesn't fight the auto-link logic below (which
        // mirrors the new offset_x to showOffsetX while they're equal). The
        // show-offset inputs only set their fields when the user actually
        // edits them (single-select OR multi-select).
        const applyShowOffsetX = showOffsetXVal !== null && lastChanged === 'show-offset-x';
        const applyShowOffsetY = showOffsetYVal !== null && lastChanged === 'show-offset-y';
        const cabinetWidthVal = readNumber('cabinet-width').value;
        const cabinetHeightVal = readNumber('cabinet-height').value;
        const columnsVal = readNumber('screen-columns').value;
        const rowsVal = readNumber('screen-rows').value;
        const numberSizeVal = readNumber('number-size').value;
        // The four screen-level half-tile flags were replaced by per-panel
        // halfTile state. The variables below remain (always null) so the
        // existing "if halfXxxVal !== null" assignment block stays a no-op
        // without further changes elsewhere.
        const halfFirstColumnVal = null;
        const halfLastColumnVal = null;
        const halfFirstRowVal = null;
        const halfLastRowVal = null;
        
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
        // labelsFontSize is now read via readNumber('labels-fontsize') below;
        // the element handle above used to be referenced directly with parseInt
        // and converted blank input into NaN, which then leaked through the
        // multi-select bulk update as a real null write. The readNumber path
        // returns null cleanly and skips the assignment in that case.
        const useFractionalInchesEl = document.getElementById('use-fractional-inches');

        const showLabelNameVal = showLabelNameEl && !showLabelNameEl.indeterminate ? showLabelNameEl.checked : null;
        const showLabelSizePxVal = showLabelSizePxEl && !showLabelSizePxEl.indeterminate ? showLabelSizePxEl.checked : null;
        const showLabelSizeMVal = showLabelSizeMEl && !showLabelSizeMEl.indeterminate ? showLabelSizeMEl.checked : null;
        const showLabelSizeFtVal = showLabelSizeFtEl && !showLabelSizeFtEl.indeterminate ? showLabelSizeFtEl.checked : null;
        const showLabelInfoVal = showLabelInfoEl && !showLabelInfoEl.indeterminate ? showLabelInfoEl.checked : null;
        const showLabelWeightVal = showLabelWeightEl && !showLabelWeightEl.indeterminate ? showLabelWeightEl.checked : null;
        const labelsColorVal = labelsColorEl ? labelsColorEl.value : null;
        // Use readNumber() so blank/NaN reads come back as null and are skipped
        // by the `!== null` guard below. Without this, multi-select with mixed
        // values shows an empty input, parseInt('') = NaN, and every selected
        // layer's labelsFontSize gets clobbered to NaN → null on the server.
        const labelsFontSizeVal = readNumber('labels-fontsize').value;
        const infoLabelSizeVal = readNumber('info-label-size').value;
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
                // Capture whether the show offset is currently linked to the
                // processor offset (i.e. equal). If so, editing the pixel-map
                // offset should also update showOffset so Show Look / Data /
                // Power follow the move. Once they diverge (because the user
                // explicitly set a different show offset), pixel-map edits
                // stop touching showOffset.
                const linkedX = Number(layer.showOffsetX ?? layer.offset_x ?? 0) === Number(layer.offset_x ?? 0);
                const linkedY = Number(layer.showOffsetY ?? layer.offset_y ?? 0) === Number(layer.offset_y ?? 0);
                if (applyOffsetX) {
                    layer.offset_x = offsetXVal;
                    if (linkedX) layer.showOffsetX = offsetXVal;
                }
                if (applyOffsetY) {
                    layer.offset_y = offsetYVal;
                    if (linkedY) layer.showOffsetY = offsetYVal;
                }
                if (applyShowOffsetX) layer.showOffsetX = showOffsetXVal;
                if (applyShowOffsetY) layer.showOffsetY = showOffsetYVal;
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
        this.debouncedSaveState('Update Properties');
    }

    loadLayerToInputs() {
        const layers = this.getSelectedLayers();
        if (layers.length === 0) return;
        const primary = this.currentLayer || layers[0];
        const allImages = layers.every(l => (l.type || 'screen') === 'image');
        const allText = layers.every(l => (l.type || 'screen') === 'text');
        const screenGridSection = document.getElementById('screen-grid-settings');
        const imageSection = document.getElementById('image-layer-section');
        if (screenGridSection) {
            screenGridSection.style.display = (allImages || allText) ? 'none' : '';
        }
        if (imageSection) {
            imageSection.style.display = allImages ? '' : 'none';
        }
        document.querySelectorAll('.screen-only').forEach(el => {
            if (el.classList.contains('tab-panel')) return;
            el.style.display = (allImages || allText) ? 'none' : '';
        });
        document.querySelectorAll('.image-only').forEach(el => {
            if (el.classList.contains('tab-panel')) return;
            el.style.display = allImages ? '' : 'none';
        });
        document.querySelectorAll('.text-only').forEach(el => {
            if (el.classList.contains('tab-panel')) return;
            el.style.display = allText ? '' : 'none';
        });
        this.updateLayerPanelVisibility(allImages, allText);

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
                el.placeholder = '-';
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
        // Show Look offsets, separate from processor offsets (Pixel Map).
        setTextInput('show-offset-x', getCommon(l => (l.showOffsetX ?? l.offset_x) || 0));
        setTextInput('show-offset-y', getCommon(l => (l.showOffsetY ?? l.offset_y) || 0));

        // Image layer controls
        const imageScaleEl = document.getElementById('image-scale');
        const imageScaleRangeEl = document.getElementById('image-scale-range');
        const imageSizeEl = document.getElementById('image-size-display');
        if (allImages) {
            const scaleCommon = getCommon(l => Math.round((l.imageScale || 1) * 100));
            if (imageScaleEl) {
                imageScaleEl.value = scaleCommon.mixed ? '' : scaleCommon.value;
                imageScaleEl.placeholder = scaleCommon.mixed ? '-' : '';
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
                imageSizeEl.textContent = '-';
            }
        }
        setTextInput('cabinet-width', getCommon(l => l.cabinet_width));
        setTextInput('cabinet-height', getCommon(l => l.cabinet_height));
        setTextInput('screen-columns', getCommon(l => l.columns));
        setTextInput('screen-rows', getCommon(l => l.rows));
        // (legacy half-* checkboxes were removed when half-tile state moved
        // to per-panel; the four screen-level flags are migrated to per-panel
        // halfTile values on first load.)
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
                    hex.placeholder = '-';
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
        // show-label-name always reflects the pixel-map property (showLabelName).
        // Per-tab checkboxes (show-label-name-cabinet etc.) are set separately below.
        // Helper: read per-tab property, falling back to global showLabelName → true
        const _tabLabel = (l, prop) => l[prop] !== undefined ? l[prop] : (l.showLabelName !== undefined ? l.showLabelName : true);
        setCheckbox('show-label-name', getCommon(l => l.showLabelName !== undefined ? l.showLabelName : true));
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
        
        // Update Screen Name checkboxes on other tabs, each reads its own per-tab property
        // with fallback to global showLabelName → true (backwards compat with old project files)
        if (document.getElementById('show-label-name-cabinet')) {
            setCheckbox('show-label-name-cabinet', getCommon(l => _tabLabel(l, 'showLabelNameCabinet')));
        }
        if (document.getElementById('show-label-name-data')) {
            setCheckbox('show-label-name-data', getCommon(l => _tabLabel(l, 'showLabelNameDataFlow')));
        }
        if (document.getElementById('show-label-name-power')) {
            setCheckbox('show-label-name-power', getCommon(l => _tabLabel(l, 'showLabelNamePower')));
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

    updateLayerPanelVisibility(allImages, allText) {
        const mode = window.canvasRenderer ? window.canvasRenderer.viewMode : 'pixel-map';
        const activeTab = mode === 'data-flow' ? 'data-flow' : mode;
        const nonScreen = allImages || allText;
        document.querySelectorAll('.tab-panel').forEach(panel => {
            if (panel.getAttribute('data-tab') !== activeTab) {
                panel.style.display = 'none';
                return;
            }
            if (panel.classList.contains('screen-only')) {
                panel.style.display = nonScreen ? 'none' : 'block';
                return;
            }
            if (panel.classList.contains('image-only')) {
                panel.style.display = allImages ? 'block' : 'none';
                return;
            }
            if (panel.classList.contains('text-only')) {
                panel.style.display = allText ? 'block' : 'none';
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

            // Rectangle-constraint processors (NovaStar Armor / 1G) reserve a
            // pixel rectangle that encloses every visible cabinet in the port.
            // We compute that rect from each panel's actual x/y/width/height
            // (so half-tiles contribute their reduced footprint instead of the
            // full cell). See calcBoundingRectLoad below.
            const calcBoundingRectLoad = (unitIdxList) => {
                if (!usesRectangle) {
                    // Non-rectangle processors: sum actual pixel areas
                    return unitIdxList.reduce((total, idx) => {
                        const panels = orderedForCapacity.filter(p => (isHorizontalFirst ? p.row === idx : p.col === idx));
                        return total + panels.reduce((sum, p) => sum + this.getPanelPixelArea(p), 0);
                    }, 0);
                }
                // Rectangle constraint (NovaStar Armor / 1G): the processor reserves
                // a pixel rectangle that encloses every visible cabinet in the port.
                // Compute that bounding rect from each panel's actual x/y/width/height
                // so half-tiles correctly contribute their reduced footprint instead
                // of the full cabinet cell.
                let minX = Infinity, maxX = -Infinity;
                let minY = Infinity, maxY = -Infinity;
                let hasVisible = false;
                unitIdxList.forEach(idx => {
                    const visible = orderedForCapacity.filter(p => (isHorizontalFirst ? p.row === idx : p.col === idx) && !p.hidden);
                    visible.forEach(p => {
                        hasVisible = true;
                        const x1 = Number(p.x) || 0;
                        const y1 = Number(p.y) || 0;
                        const x2 = x1 + (Number(p.width) || 0);
                        const y2 = y1 + (Number(p.height) || 0);
                        if (x1 < minX) minX = x1;
                        if (y1 < minY) minY = y1;
                        if (x2 > maxX) maxX = x2;
                        if (y2 > maxY) maxY = y2;
                    });
                });
                if (!hasVisible) return 0;
                return (maxX - minX) * (maxY - minY);
            };

            let current = { unitIndices: [], load: 0 };

            unitIndices.forEach(unitIdx => {
                const unitPanelsAll = orderedForCapacity.filter(p => (isHorizontalFirst ? p.row === unitIdx : p.col === unitIdx));
                if (unitPanelsAll.length === 0) return;
                // Skip rows/columns with no visible panels
                const visibleInUnit = unitPanelsAll.filter(p => !p.hidden);
                if (visibleInUnit.length === 0) return;

                // Check if this single unit exceeds port capacity. For
                // rectangle-constraint processors, use the pixel-extent of the
                // visible panels in the unit (so half-tiles count as half).
                const singleUnitLoad = usesRectangle
                    ? (() => {
                        const visible = unitPanelsAll.filter(p => !p.hidden);
                        if (visible.length === 0) return 0;
                        let mnX = Infinity, mxX = -Infinity, mnY = Infinity, mxY = -Infinity;
                        visible.forEach(p => {
                            const x1 = Number(p.x) || 0, y1 = Number(p.y) || 0;
                            const x2 = x1 + (Number(p.width) || 0);
                            const y2 = y1 + (Number(p.height) || 0);
                            if (x1 < mnX) mnX = x1; if (y1 < mnY) mnY = y1;
                            if (x2 > mxX) mxX = x2; if (y2 > mxY) mxY = y2;
                        });
                        return (mxX - mnX) * (mxY - mnY);
                    })()
                    : unitPanelsAll.reduce((sum, p) => sum + this.getPanelPixelArea(p), 0);
                if (singleUnitLoad > portCapacity) {
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

                // Calculate what the bounding rect load would be if we add this unit
                const candidateIndices = [...current.unitIndices, unitIdx];
                const candidateLoad = calcBoundingRectLoad(candidateIndices);

                if (current.unitIndices.length > 0 && candidateLoad > portCapacity) {
                    // Adding this unit would exceed capacity, start new port
                    current.load = calcBoundingRectLoad(current.unitIndices);
                    ports.push(current);
                    current = { unitIndices: [unitIdx], load: singleUnitLoad };
                } else {
                    current.unitIndices.push(unitIdx);
                    current.load = candidateLoad;
                }
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
        if (document.getElementById('export-show-look') && document.getElementById('export-show-look').checked) views.push('show-look');
        if (document.getElementById('export-data-flow').checked) views.push('data-flow');
        if (document.getElementById('export-power').checked) views.push('power');

        const preview = document.getElementById('export-preview');

        // Hide view checkboxes for Resolume XML (geometry only, no rendered views)
        const viewSection = document.getElementById('export-views-section');
        if (viewSection) {
            viewSection.style.display = format === 'resolume-xml' ? 'none' : '';
        }

        if (format === 'resolume-xml') {
            preview.style.color = '#4A90E2';
            preview.textContent = `${projectName}.xml`;
            return;
        }

        if (views.length === 0) {
            preview.textContent = '(Select at least one view)';
            preview.style.color = '#ff6b6b';
            return;
        }

        preview.style.color = '#4A90E2';

        // Slice 11: factor selected canvases into the preview. Each
        // (canvas, view) combo is one file (PNG/PSD) or one page (PDF).
        const canvasIds = (typeof this.getSelectedExportCanvasIds === 'function')
            ? this.getSelectedExportCanvasIds() : [null];
        if (canvasIds.length === 0) {
            preview.textContent = '(Select at least one canvas)';
            preview.style.color = '#ff6b6b';
            return;
        }
        const projectCanvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        const canvasNameOf = (cid) => {
            if (!cid) return '';
            const c = projectCanvases.find(x => x && x.id === cid);
            return c ? this.sanitizeFilename(c.name || 'Canvas') : '';
        };
        const multiCanvas = canvasIds.length > 1 && canvasIds[0] !== null;
        const buildName = (cid, suffix, ext) => {
            const cname = canvasNameOf(cid);
            return (multiCanvas && cname)
                ? `${projectName} - ${cname} - ${suffix}.${ext}`
                : `${projectName} ${suffix}.${ext}`;
        };

        if (format === 'pdf') {
            const pageCount = canvasIds.length * views.length;
            preview.textContent = `${projectName}.pdf (${pageCount} page${pageCount > 1 ? 's' : ''})`;
        } else if (format === 'psd' || format === 'png') {
            const ext = format;
            const lines = [];
            for (const cid of canvasIds) {
                for (const v of views) {
                    const suffix = this.getExportSuffixForView(v, suffixes, viewNames);
                    lines.push(buildName(cid, suffix, ext));
                }
            }
            if (lines.length === 1) preview.textContent = lines[0];
            else preview.innerHTML = lines.join('<br>');
        }
    }

    getExportViewNames() {
        return {
            'pixel-map': 'Pixel Map',
            'cabinet-id': 'Cabinet Map',
            'show-look': 'Show Look',
            'data-flow': 'Data Map',
            'power': 'Power Map'
        };
    }

    getExportSuffixDefaults() {
        return {
            'pixel-map': 'Pixel Map',
            'cabinet-id': 'Cabinet Map',
            'show-look': 'Show Look',
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
        apply('export-suffix-show-look', 'show-look');
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
            'show-look': read('export-suffix-show-look', 'show-look'),
            'data-flow': read('export-suffix-data-flow', 'data-flow'),
            'power': read('export-suffix-power', 'power')
        };
    }

    getExportSuffixForView(view, suffixes, viewNames, canvas) {
        const raw = (suffixes && typeof suffixes[view] === 'string') ? suffixes[view].trim() : '';
        let suffix = raw || viewNames[view];
        // v0.8.6: perspective is per-canvas. When exporting a specific
        // canvas, read THAT canvas's perspective (not the project-root
        // legacy field). For legacy single-canvas projects (canvas=null)
        // fall back to the project root field.
        const perspectiveKey = view === 'data-flow' ? 'data_flow_perspective'
            : view === 'power' ? 'power_perspective'
            : null;
        if (perspectiveKey) {
            const value = canvas
                ? canvas[perspectiveKey]
                : (this.project && this.project[perspectiveKey]);
            if (value === 'back' && !/_back$/i.test(suffix)) {
                suffix = `${suffix}_back`;
            }
        }
        return suffix;
    }
    
    // Export Resolume Arena Advanced Output XML
    async exportResolumeXml(projectName) {
        const rasterW = parseInt(document.getElementById('toolbar-raster-width').value) || 3840;
        const rasterH = parseInt(document.getElementById('toolbar-raster-height').value) || 2160;

        const response = await fetch('/api/export/resolume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                raster_width: rasterW,
                raster_height: rasterH
            })
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || 'Resolume export failed');
        }
        const blob = await response.blob();
        await this.saveBlobWithPicker(blob, `${projectName}.xml`, 'application/xml');
        sendClientLog('export_resolume_complete', { projectName, rasterW, rasterH });
    }

    // Perform export using client-side canvas capture at 1:1 pixel scale
    /**
     * Slice 11: build the dynamic Canvases checklist in the export modal.
     * Visible canvases are checked, hidden ones unchecked but still
     * selectable. Each row gets a stable id so the export-confirm handler
     * can read them.
     */
    populateExportCanvasesList() {
        const list = document.getElementById('export-canvases-list');
        if (!list) return;
        list.innerHTML = '';
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        if (canvases.length === 0) {
            // Legacy / pre-Slice-1 project: no canvas list. Show a static
            // placeholder so the user understands what's being exported.
            const note = document.createElement('div');
            note.style.cssText = 'font-size:11px;color:#888;padding:6px 0;';
            note.textContent = 'Single-canvas project, entire workspace will be exported.';
            list.appendChild(note);
            return;
        }
        canvases.forEach((c, idx) => {
            if (!c || !c.id) return;
            const row = document.createElement('div');
            row.className = 'export-view-row';
            const isHidden = c.visible === false;
            const label = document.createElement('label');
            label.className = 'export-view-label';
            label.style.gap = '6px';
            const swatch = document.createElement('span');
            swatch.style.cssText = `display:inline-block;width:10px;height:10px;border-radius:2px;background:${c.color || '#4A90E2'};flex:none;`;
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = !isHidden;
            checkbox.dataset.canvasId = c.id;
            checkbox.className = 'export-canvas-checkbox';
            checkbox.addEventListener('change', () => this.updateExportPreview());
            const text = document.createElement('span');
            text.textContent = (c.name || `Canvas ${idx + 1}`) + (isHidden ? '  (hidden)' : '');
            if (isHidden) text.style.color = '#888';
            label.appendChild(checkbox);
            label.appendChild(swatch);
            label.appendChild(text);
            row.appendChild(label);
            // v0.8.6: per-canvas perspective overrides for Data + Power
            // exports. Default to whatever the canvas currently has.
            // These dropdowns set/restore the canvas's perspective during
            // export only — they don't persist back to the project.
            const persp = document.createElement('div');
            persp.style.cssText = 'display:flex;gap:8px;margin-left:22px;font-size:11px;color:#aaa;align-items:center;';
            const mkSel = (kind, current) => {
                const wrap = document.createElement('span');
                wrap.style.cssText = 'display:inline-flex;gap:4px;align-items:center;';
                const lbl = document.createElement('span');
                lbl.textContent = kind === 'data' ? 'Data:' : 'Power:';
                const sel = document.createElement('select');
                sel.className = `export-canvas-perspective export-canvas-perspective-${kind}`;
                sel.dataset.canvasId = c.id;
                sel.dataset.kind = kind;
                sel.style.cssText = 'background:#222;color:#ddd;border:1px solid #444;border-radius:3px;padding:1px 4px;font-size:11px;';
                ['front', 'back'].forEach(v => {
                    const o = document.createElement('option');
                    o.value = v;
                    o.textContent = v === 'front' ? 'Front' : 'Back';
                    if (v === current) o.selected = true;
                    sel.appendChild(o);
                });
                wrap.appendChild(lbl);
                wrap.appendChild(sel);
                return wrap;
            };
            const curData = (c.data_flow_perspective === 'back') ? 'back' : 'front';
            const curPower = (c.power_perspective === 'back') ? 'back' : 'front';
            persp.appendChild(mkSel('data', curData));
            persp.appendChild(mkSel('power', curPower));
            row.appendChild(persp);
            list.appendChild(row);
        });
    }

    /**
     * Slice 11: read the canvas checkboxes back. Returns array of canvas
     * ids in their project.canvases order. Returns [null] for legacy
     * projects so performExport falls into single-canvas mode.
     */
    getSelectedExportCanvasIds() {
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        if (canvases.length === 0) return [null];
        const checked = new Set();
        document.querySelectorAll('.export-canvas-checkbox').forEach(cb => {
            if (cb.checked && cb.dataset.canvasId) checked.add(cb.dataset.canvasId);
        });
        // Preserve project.canvases order in the output.
        return canvases.filter(c => c && checked.has(c.id)).map(c => c.id);
    }

    /**
     * Slice 11: multi-canvas-aware export. Iterates canvases × views,
     * temporarily hiding the OTHER canvases per pass and translating the
     * render so each canvas becomes its own export image at its native
     * raster size. canvasIds=[null] is the legacy single-canvas path.
     */
    async performExport(projectName, format, views, canvasIds) {
        const viewNames = this.getExportViewNames();
        const suffixes = this.getExportSuffixesFromUI();

        // Store current renderer state.
        const originalViewMode = window.canvasRenderer.viewMode;
        const originalZoom = window.canvasRenderer.zoom;
        const originalPanX = window.canvasRenderer.panX;
        const originalPanY = window.canvasRenderer.panY;
        const originalActiveCanvasId = (this.project && this.project.active_canvas_id) || null;
        const mainCanvas = window.canvasRenderer.canvas;
        const originalCtx = window.canvasRenderer.ctx;

        const transparentBg = document.getElementById('export-transparent-bg');
        const useTransparentBg = transparentBg && transparentBg.checked;

        // Snapshot every canvas's visibility so we can flip them per pass
        // and restore at the end. Legacy projects skip this entirely.
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        const visibilitySnapshot = canvases.map(c => ({ id: c.id, visible: c.visible }));
        // v0.8.6: snapshot every canvas's perspective so we can apply the
        // export-dialog overrides per pass and restore at the end. Read
        // the per-canvas perspective dropdowns once up-front.
        const perspectiveSnapshot = canvases.map(c => ({
            id: c.id,
            data_flow_perspective: c.data_flow_perspective,
            power_perspective: c.power_perspective,
        }));
        const perspectiveOverrides = {};
        document.querySelectorAll('.export-canvas-perspective').forEach(sel => {
            const cid = sel.dataset.canvasId;
            const kind = sel.dataset.kind;
            if (!cid || !kind) return;
            if (!perspectiveOverrides[cid]) perspectiveOverrides[cid] = {};
            const key = kind === 'data' ? 'data_flow_perspective' : 'power_perspective';
            perspectiveOverrides[cid][key] = (sel.value === 'back') ? 'back' : 'front';
        });
        // Apply overrides to every canvas BEFORE the per-canvas/per-view
        // loop so each render call sees the user's chosen perspective.
        canvases.forEach(c => {
            const o = perspectiveOverrides[c.id];
            if (!o) return;
            if (o.data_flow_perspective) c.data_flow_perspective = o.data_flow_perspective;
            if (o.power_perspective) c.power_perspective = o.power_perspective;
        });

        const exportCanvas = document.createElement('canvas');
        const exportCtx = exportCanvas.getContext('2d', { alpha: useTransparentBg });
        window.canvasRenderer.canvas = exportCanvas;
        window.canvasRenderer.ctx = exportCtx;
        window.canvasRenderer.zoom = 1.0;
        window.canvasRenderer.exportMode = true;
        window.canvasRenderer.exportTransparentBg = useTransparentBg;

        const renderedItems = [];
        const multiCanvas = canvasIds.length > 1 && canvasIds[0] !== null;

        try {
            for (const cid of canvasIds) {
                // Resolve target canvas. cid===null means legacy single-
                // canvas: use project-root raster fields, no workspace shift.
                const targetCanvas = cid
                    ? canvases.find(c => c && c.id === cid)
                    : null;
                if (cid && !targetCanvas) continue;

                if (cid) {
                    // Make ONLY this canvas visible during the per-view loop
                    // so other canvases' layers don't bleed into the export
                    // (handles overlap, cross-canvas labels, etc.). Active
                    // canvas swap drives the rasterWidth/Height accessors
                    // that decide export-canvas dimensions per view.
                    canvases.forEach(c => { c.visible = (c.id === cid); });
                    this.project.active_canvas_id = cid;
                }

                for (const view of views) {
                    window.canvasRenderer.viewMode = view;
                    // rasterWidth/Height read from the active canvas (Slice 6)
                    // and pick show_raster_* automatically when view is
                    // show-look (so Show Look exports at its own resolution).
                    const rasterWidth = window.canvasRenderer.rasterWidth || 1920;
                    const rasterHeight = window.canvasRenderer.rasterHeight || 1080;
                    exportCanvas.width = rasterWidth;
                    exportCanvas.height = rasterHeight;
                    // Translate the workspace so this canvas's top-left
                    // (workspace_x, workspace_y) lands at (0, 0) in the
                    // export canvas. Legacy: pan to 0,0.
                    // v0.8.5.3 fix: Show Look / Data / Power views render
                    // each canvas at its show_workspace_x/y (when set) —
                    // the export pan must match or the captured PNG comes
                    // out shifted and missing layers that live at
                    // negative-relative show positions.
                    const isShowExport = (view === 'show-look' || view === 'data-flow' || view === 'power');
                    let wsx = 0, wsy = 0;
                    if (targetCanvas) {
                        if (isShowExport) {
                            wsx = (targetCanvas.show_workspace_x == null
                                ? (targetCanvas.workspace_x || 0)
                                : (targetCanvas.show_workspace_x || 0));
                            wsy = (targetCanvas.show_workspace_y == null
                                ? (targetCanvas.workspace_y || 0)
                                : (targetCanvas.show_workspace_y || 0));
                        } else {
                            wsx = targetCanvas.workspace_x || 0;
                            wsy = targetCanvas.workspace_y || 0;
                        }
                    }
                    window.canvasRenderer.panX = -wsx;
                    window.canvasRenderer.panY = -wsy;

                    window.canvasRenderer.render();

                    const dataUrl = exportCanvas.toDataURL('image/png');
                    const suffix = this.getExportSuffixForView(view, suffixes, viewNames, targetCanvas);
                    const canvasName = targetCanvas
                        ? this.sanitizeFilename(targetCanvas.name || 'Canvas')
                        : null;
                    // Filename: include canvas token only when exporting
                    // more than one. Single-canvas exports keep the v0.7
                    // naming so existing user workflows aren't disrupted.
                    const fileBase = (multiCanvas && canvasName)
                        ? `${projectName} - ${canvasName} - ${suffix}`
                        : `${projectName} ${suffix}`;
                    // PDF page label includes canvas + view when multi.
                    const pdfLabel = (multiCanvas && canvasName)
                        ? `${canvasName}, ${suffix}`
                        : suffix;
                    renderedItems.push({
                        canvasId: cid,
                        canvasName,
                        view,
                        suffix,
                        fileBase,
                        pdfLabel,
                        dataUrl,
                        width: rasterWidth,
                        height: rasterHeight,
                    });
                }
            }
        } finally {
            // Restore canvas visibility, perspective, active canvas, renderer state.
            visibilitySnapshot.forEach(s => {
                const c = canvases.find(c => c && c.id === s.id);
                if (c) c.visible = s.visible;
            });
            perspectiveSnapshot.forEach(s => {
                const c = canvases.find(c => c && c.id === s.id);
                if (!c) return;
                c.data_flow_perspective = s.data_flow_perspective;
                c.power_perspective = s.power_perspective;
            });
            if (this.project) this.project.active_canvas_id = originalActiveCanvasId;
            window.canvasRenderer.canvas = mainCanvas;
            window.canvasRenderer.ctx = originalCtx;
            window.canvasRenderer.exportMode = false;
            window.canvasRenderer.exportTransparentBg = false;
            window.canvasRenderer.viewMode = originalViewMode;
            window.canvasRenderer.zoom = originalZoom;
            window.canvasRenderer.panX = originalPanX;
            window.canvasRenderer.panY = originalPanY;
            window.canvasRenderer.render();
        }

        // Dispatch to format-specific writer. Multi-canvas just means
        // more items, each writer already loops over them.
        if (format === 'png') {
            await this.downloadRenderedPNGs(renderedItems);
        } else if (format === 'pdf') {
            await this.downloadAsPdf(projectName, renderedItems);
        } else if (format === 'psd') {
            await this.downloadAsPsd(projectName, renderedItems);
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

    isLocalConnection() {
        const host = window.location.hostname;
        return host === 'localhost' || host === '127.0.0.1' || host === '::1';
    }

    browserDownload(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 5000);
        sendClientLog('save_blob_browser_download', { filename });
    }

    async saveBlobWithPicker(blobOrFn, filename, mimeType) {
        // Sanitize so a project name with "/" or other illegal chars doesn't
        // get rejected by showSaveFilePicker / OS file APIs.
        filename = this.sanitizeFilename(filename);
        // blobOrFn can be a Blob OR an async function returning one. Lazy-blob
        // form lets the caller defer expensive serialization (e.g. stringifying
        // a 1MB project) until AFTER showSaveFilePicker resolves, keeping the
        // user-activation gesture fresh for createWritable. See bug fix for
        // 0-byte JSON saves on large multi-canvas projects.
        const resolveBlob = async () => (typeof blobOrFn === 'function' ? await blobOrFn() : blobOrFn);
        // 1. Try the File System Access API (Chrome/Edge on secure contexts).
        //    Skip on localhost, we have a better server-side native dialog
        //    available that doesn't break on cloud-synced folders (Nextcloud,
        //    iCloud, Dropbox, OneDrive). Chrome's createWritable rejects with
        //    NotAllowedError when the target lives under a sync agent's xattrs,
        //    which produced 0-byte saves before this guard.
        if (window.showSaveFilePicker && !this.isLocalConnection()) {
            try {
                sendClientLog('save_blob_picker_start', { filename, mimeType });
                const ext = filename.split('.').pop() || '';
                const handle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{ description: 'File', accept: { [mimeType]: [`.${ext}`] } }]
                });
                const blob = await resolveBlob();
                const writable = await handle.createWritable();
                await writable.write(blob);
                await writable.close();
                sendClientLog('save_blob_picker_success', { filename });
                return;
            } catch (err) {
                if (err && err.name === 'AbortError') return;
                // NotAllowedError on createWritable: Chrome already created the
                // empty file via the picker but lost the user-activation needed
                // to write to it. Fall through to native/browser fallback so we
                // don't leave the user with a 0-byte file and nothing else.
                sendClientLog('save_blob_picker_failed', {
                    filename,
                    name: err && err.name,
                    message: err && err.message
                });
                // Try native dialog (Mac/Win/Linux), opens a fresh dialog so
                // we get our own gesture-bound path. If unavailable, use
                // browserDownload as last resort.
            }
        }
        // 2. Use native server-side dialog (opens on the host machine)
        try {
            const savePath = await this.nativeSelectSavePath(filename);
            if (!savePath) {
                sendClientLog('save_blob_native_dialog_cancelled', { filename });
                return;
            }
            sendClientLog('save_blob_native_dialog_selected', { filename, savePath });
            const blob = await resolveBlob();
            const ok = await this.nativeWriteFile(savePath, blob);
            if (ok) {
                sendClientLog('save_blob_native_dialog_success', { filename, savePath });
                return;
            }
            sendClientLog('save_blob_native_dialog_write_failed', { filename, savePath });
        } catch (err) {
            sendClientLog('save_blob_native_dialog_error', { filename, message: err.message });
        }
        // 3. Last resort: trigger a normal browser download so the user always
        // ends up with a file (even if both the picker and the native dialog
        // failed). Better than silently leaving a 0-byte stub on disk.
        try {
            const blob = await resolveBlob();
            this.browserDownload(blob, filename);
        } catch (err) {
            sendClientLog('save_blob_browser_download_error', { filename, message: err && err.message });
        }
    }

    sanitizeFilename(name) {
        // Strip path separators and characters Windows/macOS reject in filenames.
        // Also collapse leading/trailing dots & whitespace which Windows rejects.
        if (!name) return 'untitled';
        const cleaned = String(name)
            .replace(/[\\/:*?"<>|\x00-\x1F]/g, '_')
            .replace(/^[\s.]+|[\s.]+$/g, '')
            .trim();
        return cleaned || 'untitled';
    }

    async saveMultipleFiles(files) {
        // Sanitize each filename so path separators (e.g. "/" in a project name)
        // don't break getFileHandle() with "Name is not allowed."
        files = files.map(f => ({ ...f, filename: this.sanitizeFilename(f.filename) }));
        sendClientLog('save_multiple_files_start', {
            count: files.length,
            hasDirectoryPicker: !!window.showDirectoryPicker,
            hasSaveFilePicker: !!window.showSaveFilePicker
        });
        // v0.8: same Chrome activation issue we hit on JSON saves, when
        // the user is on localhost (this Flask app), the multi-canvas export
        // burns the user-gesture token rendering all the canvases between
        // showDirectoryPicker resolving and the per-file getFileHandle/
        // createWritable calls. Chrome rejects with NotAllowedError and we
        // get zero files on disk. Skip the FS Access API entirely on
        // localhost and use the native server-side directory dialog, which
        // doesn't have this restriction.
        if (window.showDirectoryPicker && !this.isLocalConnection()) {
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
                sendClientLog('save_multiple_files_directory_failed', {
                    name: err && err.name, message: err && err.message
                });
                // fall through to native fallback so the user still gets files
            }
        }
        // Use native server-side directory picker (opens on the host machine).
        // Tried BEFORE per-file showSaveFilePicker because picking once is
        // far less work than N separate save dialogs.
        try {
            const targetDir = await this.nativeSelectDirectory();
            if (targetDir) {
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
            }
            sendClientLog('save_multiple_files_native_dialog_cancelled', { count: files.length });
        } catch (err) {
            sendClientLog('save_multiple_files_native_dialog_error', { message: err.message });
        }
        // Last resort: per-file saveBlobWithPicker (multiple dialogs) or
        // browser download.
        if (window.showSaveFilePicker) {
            for (const file of files) {
                const mimeType = file.blob && file.blob.type ? file.blob.type : 'application/octet-stream';
                await this.saveBlobWithPicker(file.blob, file.filename, mimeType);
            }
            sendClientLog('save_multiple_files_picker_success', { count: files.length });
            return;
        }
        for (const file of files) {
            try { this.browserDownload(file.blob, file.filename); } catch (_) {}
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
        // Slice 11: multi-canvas PDF. Each rendered item contributes one
        // page; the per-page name uses canvas + view when multi-canvas
        // (set on renderedItem.pdfLabel by performExport), else just the
        // view suffix. Server already handles variable per-page sizes.
        const response = await fetch('/api/export/pdf-from-images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                images: renderedViews.map(v => ({
                    name: v.pdfLabel || v.suffix,
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
            // Slice 11: when exporting per-canvas, only include layers from
            // that canvas in the PSD layer list, otherwise the PSD reports
            // sibling canvases' layers as if they were in this image.
            // Legacy / single-canvas: include every layer (canvasId is null).
            const psdLayers = this.project.layers.filter(l => {
                if (!view.canvasId) return true;
                // v0.8.5: Show Look / Data / Power exports use the layer's
                // effective show canvas (show_canvas_id || canvas_id) so a
                // layer reassigned in Show Look exports under its show
                // canvas's PSD instead of its Pixel Map canvas's.
                const isShowView = view.viewMode === 'show-look'
                    || view.viewMode === 'data-flow' || view.viewMode === 'power';
                const cid = (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
                return cid === view.canvasId;
            }).map(l => {
                const b = this.getLayerBounds(l);
                return {
                    name: l.name,
                    offset_x: b.x1,
                    offset_y: b.y1,
                    width: b.x2 - b.x1,
                    height: b.y2 - b.y1,
                    visible: l.visible
                };
            });
            const response = await fetch('/api/export/psd-from-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_name: projectName,
                    view_name: view.suffix,
                    image_data: view.dataUrl,
                    width: view.width || window.canvasRenderer.rasterWidth,
                    height: view.height || window.canvasRenderer.rasterHeight,
                    layers: psdLayers
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
            powerWatts: 200,
            canvasGap: 0
        };
    }

    getLocalPreferences() {
        let saved = {};
        try {
            saved = JSON.parse(localStorage.getItem('appPreferences') || '{}');
        } catch (e) {
            saved = {};
        }
        return saved;
    }

    getPreferences() {
        const defaults = this.getPreferencesDefaults();
        // Server preferences take priority (shared across all clients),
        // fall back to localStorage for backwards compatibility
        const saved = (this._serverPreferences && Object.keys(this._serverPreferences).length > 0)
            ? this._serverPreferences
            : this.getLocalPreferences();
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
                // Save to server so all clients share the same preferences
                this._serverPreferences = prefs;
                fetch('/api/preferences', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(prefs)
                });
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
                // Sync reset to server
                this._serverPreferences = defaults;
                fetch('/api/preferences', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(defaults)
                });
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
        setVal('pref-canvas-gap', prefs.canvasGap);
        const modal = document.getElementById('preferences-modal');
        if (modal) modal.style.display = 'block';
    }

    readPreferencesFromUI() {
        const defaults = this.getPreferencesDefaults();
        const readNum = (id, fallback) => {
            const el = document.getElementById(id);
            if (!el) return fallback;
            const val = parseFloat(el.value);
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
            powerWatts: readNum('pref-power-watts', defaults.powerWatts),
            canvasGap: readNum('pref-canvas-gap', defaults.canvasGap)
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
            // Don't close menu when hovering over submenu parent
            if (target.classList.contains('menu-has-submenu')) return;
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

        // Populate recent files submenu
        this.updateRecentFilesMenu();
    }

    updateShortcutLabels() {
        const isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform) || /Mac/.test(navigator.userAgent);
        document.querySelectorAll('.menu-option[data-label]').forEach(option => {
            // Skip options with submenus, they manage their own content
            if (option.classList.contains('menu-has-submenu')) return;
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
            case 'bulk-set-blank':
                this.setPanelsBlankBulk(this.getPixelMapSelectedPanels(), true);
                break;
            case 'bulk-unset-blank':
                this.setPanelsBlankBulk(this.getPixelMapSelectedPanels(), false);
                break;
            case 'bulk-set-half-auto':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'auto');
                break;
            case 'bulk-set-half-width':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'width');
                break;
            case 'bulk-set-half-height':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'height');
                break;
            case 'bulk-clear-half':
                this.setPanelsHalfTileBulk(this.getPixelMapSelectedPanels(), 'none');
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
            case 'toggle-snap':
                if (window.canvasRenderer) {
                    window.canvasRenderer.magneticSnap = !window.canvasRenderer.magneticSnap;
                    const snapCb = document.getElementById('magnetic-snap');
                    if (snapCb) snapCb.checked = window.canvasRenderer.magneticSnap;
                }
                break;
            case 'keyboard-shortcuts':
                this.openShortcutsModal();
                break;
            case 'show-logs':
                this.openLogsModal();
                break;
            case 'about':
                this.openAboutModal();
                break;
            default:
                if (action && action.startsWith('recent-file-')) {
                    const idx = parseInt(action.replace('recent-file-', ''), 10);
                    this.loadRecentFile(idx);
                }
                break;
        }
    }

    openShortcutsModal() {
        var modal = document.getElementById('shortcuts-modal');
        if (!modal) return;
        modal.style.display = 'block';
        var closeBtn = document.getElementById('shortcuts-close');
        if (closeBtn) {
            closeBtn.onclick = function() { modal.style.display = 'none'; };
        }
        modal.onclick = function(e) {
            if (e.target === modal) modal.style.display = 'none';
        };
    }

    openAboutModal() {
        var modal = document.getElementById('about-modal');
        if (!modal) return;
        var versionEl = document.getElementById('about-version');
        if (versionEl) {
            fetch('/api/version')
                .then(function(r) { return r.json(); })
                .then(function(d) { versionEl.textContent = 'v' + (d.version || ''); })
                .catch(function() { versionEl.textContent = ''; });
        }
        modal.style.display = 'block';
        var closeBtn = document.getElementById('about-close');
        if (closeBtn) {
            closeBtn.onclick = function() { modal.style.display = 'none'; };
        }
        modal.onclick = function(e) {
            if (e.target === modal) modal.style.display = 'none';
        };
    }

    // ── Logs Viewer (Help → Show Logs…) ──
    openLogsModal() {
        const modal = document.getElementById('logs-modal');
        if (!modal) return;
        modal.style.display = 'block';
        this._ensureLogsModalWired();
        this._logsUserScrolledUp = false;
        this.refreshLogs(true);
    }

    closeLogsModal() {
        const modal = document.getElementById('logs-modal');
        if (modal) modal.style.display = 'none';
        this._stopLogsAutoRefresh();
    }

    _ensureLogsModalWired() {
        if (this._logsModalWired) return;
        this._logsModalWired = true;
        const modal = document.getElementById('logs-modal');
        const closeBtn = document.getElementById('logs-close');
        const refreshBtn = document.getElementById('logs-refresh');
        const copyBtn = document.getElementById('logs-copy');
        const revealBtn = document.getElementById('logs-reveal');
        const clearBtn = document.getElementById('logs-clear');
        const linesSel = document.getElementById('logs-lines');
        const autoCb = document.getElementById('logs-autorefresh');
        const wrapCb = document.getElementById('logs-wrap');
        const sinceInput = document.getElementById('logs-since');
        const untilInput = document.getElementById('logs-until');
        const filterClearBtn = document.getElementById('logs-filter-clear');
        const pre = document.getElementById('logs-content');

        if (closeBtn) closeBtn.addEventListener('click', () => this.closeLogsModal());
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.refreshLogs(true));
        if (copyBtn) copyBtn.addEventListener('click', () => this.copyLogs());
        if (revealBtn) revealBtn.addEventListener('click', () => this.revealLogsFolder());
        if (clearBtn) clearBtn.addEventListener('click', () => this.clearLogs());
        if (linesSel) linesSel.addEventListener('change', () => this.refreshLogs(true));
        if (autoCb) autoCb.addEventListener('change', () => {
            if (autoCb.checked) this._startLogsAutoRefresh();
            else this._stopLogsAutoRefresh();
        });
        if (wrapCb && pre) {
            wrapCb.addEventListener('change', () => {
                pre.style.whiteSpace = wrapCb.checked ? 'pre-wrap' : 'pre';
            });
        }
        // Filter inputs: re-render on input without re-fetching
        const applyFilter = () => this._rerenderLogsWithFilter();
        if (sinceInput) sinceInput.addEventListener('input', applyFilter);
        if (untilInput) untilInput.addEventListener('input', applyFilter);
        if (filterClearBtn) {
            filterClearBtn.addEventListener('click', () => {
                if (sinceInput) sinceInput.value = '';
                if (untilInput) untilInput.value = '';
                applyFilter();
            });
        }
        if (pre) {
            pre.addEventListener('scroll', () => {
                // If user scrolls away from the bottom, stop auto-scrolling on refresh
                const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 16;
                this._logsUserScrolledUp = !atBottom;
            });
        }
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) this.closeLogsModal();
            });
        }
    }

    // Parse relative ("10 min ago", "2h ago", "30s", "1d ago") or absolute
    // timestamps ("YYYY-MM-DD HH:MM:SS" or any Date-parseable string) into an
    // epoch-ms number. Returns null for empty/unparseable input.
    parseLogFilterTime(input) {
        if (!input) return null;
        const trimmed = String(input).trim();
        if (!trimmed) return null;
        // Relative: "<n> <unit> ago" or just "<n><unit>" / "<n> <unit>"
        const relMatch = trimmed
            .toLowerCase()
            .replace(/\s+ago\s*$/, '')  // strip trailing "ago"
            .trim()
            .match(/^(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$/);
        if (relMatch) {
            const n = parseFloat(relMatch[1]);
            const unit = relMatch[2];
            let ms;
            if (/^s(ec(ond)?s?)?$/.test(unit)) ms = n * 1000;
            else if (/^m(in(ute)?s?)?$/.test(unit)) ms = n * 60 * 1000;
            else if (/^h(r|rs|our|ours)?$/.test(unit)) ms = n * 60 * 60 * 1000;
            else if (/^d(ay|ays)?$/.test(unit)) ms = n * 24 * 60 * 60 * 1000;
            else return null;
            return Date.now() - ms;
        }
        // Absolute: try Date.parse. Accepts ISO, "YYYY-MM-DD HH:MM:SS",
        // "YYYY-MM-DDTHH:MM:SS", etc.
        // Log format "2026-04-22 13:20:48" is not strict ISO; convert space to T.
        const iso = trimmed.replace(' ', 'T');
        const parsed = Date.parse(iso);
        if (!isNaN(parsed)) return parsed;
        const parsed2 = Date.parse(trimmed);
        if (!isNaN(parsed2)) return parsed2;
        return null;
    }

    // Extract the log line's timestamp in epoch ms. Log lines are JSON with a
    // "timestamp": "YYYY-MM-DD HH:MM:SS" field. Returns null if not parseable.
    parseLogLineTime(line) {
        if (!line) return null;
        // Fast path: pull out the first "timestamp": "..." occurrence
        const m = line.match(/"timestamp"\s*:\s*"([^"]+)"/);
        if (!m) return null;
        const iso = m[1].replace(' ', 'T');
        const parsed = Date.parse(iso);
        return isNaN(parsed) ? null : parsed;
    }

    _filterLogLines(lines) {
        const sinceInput = document.getElementById('logs-since');
        const untilInput = document.getElementById('logs-until');
        const sinceMs = this.parseLogFilterTime(sinceInput && sinceInput.value);
        const untilMs = this.parseLogFilterTime(untilInput && untilInput.value);
        const statusEl = document.getElementById('logs-filter-status');
        const hasSinceText = !!(sinceInput && sinceInput.value.trim());
        const hasUntilText = !!(untilInput && untilInput.value.trim());
        if (!hasSinceText && !hasUntilText) {
            if (statusEl) statusEl.textContent = '';
            return { lines, sinceMs: null, untilMs: null, valid: true };
        }
        // Validate: if user typed text but it didn't parse, highlight the issue
        const parts = [];
        if (hasSinceText && sinceMs === null) parts.push('Since: invalid');
        if (hasUntilText && untilMs === null) parts.push('Until: invalid');
        if (parts.length) {
            if (statusEl) { statusEl.textContent = parts.join(' · '); statusEl.style.color = '#f0ad4e'; }
            return { lines, sinceMs, untilMs, valid: false };
        }
        const filtered = lines.filter(line => {
            const t = this.parseLogLineTime(line);
            if (t === null) return false;  // drop lines without a timestamp
            if (sinceMs !== null && t < sinceMs) return false;
            if (untilMs !== null && t > untilMs) return false;
            return true;
        });
        if (statusEl) {
            statusEl.style.color = '#888';
            statusEl.textContent = `filtered to ${filtered.length} of ${lines.length}`;
        }
        return { lines: filtered, sinceMs, untilMs, valid: true };
    }

    _rerenderLogsWithFilter() {
        // Re-render last-fetched lines through the current filter (no re-fetch)
        if (!this._logsLastLines) return;
        const pre = document.getElementById('logs-content');
        if (!pre) return;
        const { lines } = this._filterLogLines(this._logsLastLines);
        pre.textContent = lines.join('\n');
        if (!this._logsUserScrolledUp) pre.scrollTop = pre.scrollHeight;
    }

    _startLogsAutoRefresh() {
        this._stopLogsAutoRefresh();
        this._logsAutoInterval = setInterval(() => this.refreshLogs(false), 2000);
    }

    _stopLogsAutoRefresh() {
        if (this._logsAutoInterval) {
            clearInterval(this._logsAutoInterval);
            this._logsAutoInterval = null;
        }
    }

    refreshLogs(force) {
        const linesSel = document.getElementById('logs-lines');
        const lines = linesSel ? parseInt(linesSel.value, 10) || 500 : 500;
        fetch(`/api/logs?lines=${lines}`)
            .then(r => r.json())
            .then(data => this._renderLogs(data, force))
            .catch(err => this._renderLogsError(err));
    }

    _renderLogs(data, force) {
        const pre = document.getElementById('logs-content');
        const meta = document.getElementById('logs-meta');
        if (!pre) return;
        const rawLines = Array.isArray(data.lines) ? data.lines : [];
        this._logsLastLines = rawLines;
        const { lines: visibleLines } = this._filterLogLines(rawLines);
        pre.textContent = visibleLines.join('\n');
        if (meta) {
            const sizeKB = (data.file_size_bytes || 0) / 1024;
            const sizeStr = sizeKB >= 1024
                ? `${(sizeKB / 1024).toFixed(1)} MB`
                : `${sizeKB.toFixed(1)} KB`;
            const archives = data.archive_count || 0;
            const archiveStr = archives > 0 ? ` · ${archives} archived` : '';
            meta.textContent = `${rawLines.length} lines loaded · ${sizeStr}${archiveStr}`;
        }
        // Auto-scroll to bottom unless the user scrolled up
        if (force || !this._logsUserScrolledUp) {
            pre.scrollTop = pre.scrollHeight;
            this._logsUserScrolledUp = false;
        }
    }

    _renderLogsError(err) {
        const pre = document.getElementById('logs-content');
        if (pre) pre.textContent = `Failed to load logs: ${err && err.message || err}`;
    }

    copyLogs() {
        const pre = document.getElementById('logs-content');
        if (!pre) return;
        const text = pre.textContent || '';
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => this._flashCopyButton());
        } else {
            // Fallback: temporary textarea
            const ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy'); } catch (e) { /* ignore */ }
            document.body.removeChild(ta);
            this._flashCopyButton();
        }
    }

    _flashCopyButton() {
        const btn = document.getElementById('logs-copy');
        if (!btn) return;
        const orig = btn.textContent;
        btn.textContent = 'Copied ✓';
        setTimeout(() => { btn.textContent = orig; }, 1200);
    }

    revealLogsFolder() {
        fetch('/api/logs/reveal', { method: 'POST' })
            .then(r => {
                if (!r.ok) return r.json().then(e => Promise.reject(e));
            })
            .catch(err => alert('Failed to open logs folder: ' + (err && err.error || 'unknown')));
    }

    clearLogs() {
        if (!confirm('Clear the current log file? Archived (rotated) logs will be preserved.')) return;
        fetch('/api/logs', { method: 'DELETE' })
            .then(r => {
                if (!r.ok) return r.json().then(e => Promise.reject(e));
                return r.json();
            })
            .then(() => this.refreshLogs(true))
            .catch(err => alert('Failed to clear logs: ' + (err && err.error || 'unknown')));
    }

    // ── Recent Files ──────────────────────────────────────────────

    getRecentFiles() {
        try {
            return JSON.parse(localStorage.getItem('ledRasterRecentFiles') || '[]');
        } catch (e) {
            return [];
        }
    }

    saveRecentFiles(files) {
        localStorage.setItem('ledRasterRecentFiles', JSON.stringify(files));
    }

    addToRecentFiles(projectData) {
        if (!projectData || !projectData.name) return;
        const recent = this.getRecentFiles();
        // Remove existing entry with the same name
        const filtered = recent.filter(f => f.name !== projectData.name);
        // Add to front
        filtered.unshift({
            name: projectData.name,
            timestamp: Date.now(),
            layerCount: projectData.layers ? projectData.layers.length : 0,
            data: projectData
        });
        // Keep max 10
        // Keep max 20 recent files
        this.saveRecentFiles(filtered.slice(0, 20));
        this.updateRecentFilesMenu();
    }

    clearRecentFiles() {
        this.saveRecentFiles([]);
        this.updateRecentFilesMenu();
    }

    updateRecentFilesMenu() {
        const list = document.getElementById('recent-files-list');
        const divider = document.getElementById('recent-files-divider');
        if (!list) return;
        list.innerHTML = '';
        const recent = this.getRecentFiles();
        if (recent.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'recent-files-empty';
            empty.textContent = 'No recent files';
            list.appendChild(empty);
            if (divider) divider.style.display = 'none';
            return;
        }
        if (divider) divider.style.display = '';
        recent.forEach((file, idx) => {
            const item = document.createElement('div');
            item.className = 'menu-option';
            item.setAttribute('data-action', `recent-file-${idx}`);
            const date = new Date(file.timestamp);
            const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            item.innerHTML = `<div class="recent-file-item"><span class="recent-file-name">${this.escapeHtml(file.name)}</span><span class="recent-file-date">${dateStr} &middot; ${file.layerCount || 0} layers</span></div>`;
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                // Hide all menus
                document.querySelectorAll('.menu-dropdown').forEach(m => m.style.display = 'none');
                document.querySelectorAll('#menu-bar .menu-item').forEach(m => m.classList.remove('active'));
                this.loadRecentFile(idx);
            });
            list.appendChild(item);
        });
    }

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    loadRecentFile(idx) {
        const recent = this.getRecentFiles();
        if (idx < 0 || idx >= recent.length) return;
        const file = recent[idx];
        if (!file || !file.data) {
            alert('Recent file data is unavailable.');
            return;
        }
        try {
            this.resetApplicationState();
            this.project = file.data;
            if (this.project.layers) {
                this.project.layers.forEach(layer => {
                    this.applyMissingLayerDefaults(layer);
                    this.normalizeLoadedPowerFlowPattern(layer);
                });
            }
            // Sync renderer's pixel/show raster fields from the loaded file.
            // syncRasterFromProject handles view-aware raster + toolbar input.
            this.syncRasterFromProject();
            if (file.data.raster_width && file.data.raster_height) {
                this.saveRasterSize();
            }
            this.updateUI();
            if (this.project.layers && this.project.layers.length > 0) {
                this.selectLayer(this.project.layers[0]);
            }
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
                    this.dedupeProjectLayers('load_recent_file');
                    this.syncRasterFromProject();
                    if (this.project.layers) {
                        this.project.layers.forEach(layer => {
                            this.applyMissingLayerDefaults(layer);
                            this.normalizeLoadedPowerFlowPattern(layer);
                        });
                    }
                    this.updateUI();
                    if (this.project.layers && this.project.layers.length > 0) {
                        this.selectLayer(this.project.layers[0]);
                    }
                    this.saveClientSideProperties();
                    window.canvasRenderer.fitToView();
                    this.updateLayers(this.project.layers, false, 'Recent File Load Sync');
                    this.resetHistory('Initial State');
                    document.getElementById('status-message').textContent = 'Project loaded from recent files';
                    setTimeout(() => {
                        document.getElementById('status-message').textContent = 'Ready';
                    }, 2000);
                    // Slice 12: same migration toast path as loadProjectFromFile.
                    // Recent-file loads also go through PUT /api/project so the
                    // server emits _migration_notice when the cached payload
                    // lacked format_version: "0.8".
                    if (data && data._migration_notice) {
                        delete this.project._migration_notice;
                        sendClientLog('migration_notice_shown', {
                            name: this.project.name,
                            layers: this.project.layers ? this.project.layers.length : 0,
                            source: 'recent'
                        });
                        if (typeof this._toast === 'function') {
                            this._toast(
                                'Project upgraded to multi-canvas format (v0.8). Save to keep changes. Older app versions can no longer open this file.',
                                false,
                                10000
                            );
                        }
                    }
                })
                .catch(() => {
                    this.resetHistory('Initial State');
                    document.getElementById('status-message').textContent = 'Project loaded (server sync failed)';
                    setTimeout(() => {
                        document.getElementById('status-message').textContent = 'Ready';
                    }, 2000);
                });
            // Update timestamp so it moves to top of recent list
            this.addToRecentFiles(file.data);
        } catch (error) {
            alert('Error loading recent file: ' + error.message);
        }
    }

    // ── End Recent Files ─────────────────────────────────────────

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
        // Show/hide pixel-map-only menu group based on view + selection.
        const inPixelMap = window.canvasRenderer && window.canvasRenderer.viewMode === 'pixel-map';
        const haveSelection = this.pixelMapSelection && this.pixelMapSelection.size > 0;
        const showPixelMapItems = inPixelMap && haveSelection;
        menu.querySelectorAll('.pixel-map-only').forEach(el => {
            el.style.display = showPixelMapItems ? '' : 'none';
        });
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
            // v0.8.2: PUT to server (keyboard shortcut path needs the same
            // server sync as the on-screen Next/Prev buttons).
            this.updateLayers(this.getSelectedLayers());
            this.updateCustomFlowUI();
            this.updatePortLabelEditor();
            window.canvasRenderer.render();
        } else if (view === 'power' && this.isCustomPower(this.currentLayer)) {
            this.ensureCustomPowerState(this.currentLayer);
            this.currentLayer.powerCustomIndex = Math.max(1, (this.currentLayer.powerCustomIndex || 1) + delta);
            this.saveState('Power Custom Circuit Change');
            this.saveClientSideProperties();
            this.updateLayers(this.getSelectedLayers());
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
            if (capacityEl) capacityEl.textContent = '-';
            if (panelsPerPortEl) panelsPerPortEl.textContent = '-';
            if (portsRequiredEl) portsRequiredEl.textContent = '-';
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
            if (wattsEl) wattsEl.textContent = '-';
            if (panelsEl) panelsEl.textContent = '-';
            if (circuitsEl) circuitsEl.textContent = '-';
            if (amps1El) amps1El.textContent = '-';
            if (amps3El) amps3El.textContent = '-';
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
        // A multi/soca has 6 ports, so labels wrap every 6 circuits and the
        // soca number in the template increments. Works for any template
        // shaped like <prefix><number><separator>#, e.g. S1-#, S2-#, MULTI3-#.
        const m = String(template).match(/^(.*?)(\d+)([^#\d]*)#(.*)$/);
        if (m) {
            const prefix = m[1];
            const startMulti = parseInt(m[2], 10) || 1;
            const sep = m[3];
            const suffix = m[4];
            const n = Math.max(1, parseInt(circuitNum, 10) || 1);
            const multi = startMulti + Math.floor((n - 1) / 6);
            const circuitInMulti = ((n - 1) % 6) + 1;
            return `${prefix}${multi}${sep}${circuitInMulti}${suffix}`;
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
                this.saveState('Edit Port Label');
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
                this.saveState('Edit Port Label');
            });

            row.appendChild(cb);
            row.appendChild(label);
            row.appendChild(primaryInput);
            row.appendChild(returnInput);
            list.appendChild(row);
        }
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
                this.saveState('Edit Circuit Label');
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
        this.applyToSelectedLayers(layer => {
            if (enabled) {
                if (layer.flowPattern && layer.flowPattern !== 'custom') {
                    layer.lastFlowPattern = layer.flowPattern;
                }
                layer.flowPattern = 'custom';
                this.ensureCustomFlowState(layer);
            } else {
                layer.flowPattern = layer.lastFlowPattern || 'tl-h';
            }
        });
        if (!enabled) {
            this.customSelectMode = false;
            this.customSelection.clear();
        }
        this.saveState('Custom Mode Toggle');
        this.saveClientSideProperties();
        // Recompute port count BEFORE the server roundtrip so the layer's
        // _portsRequired is fresh when preservedProps captures it.
        this.updatePortCapacityDisplay();
        this.updateLayers(this.getSelectedLayers());
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
        this.applyToSelectedLayers(layer => {
            if (enabled) {
                if (layer.powerFlowPattern && layer.powerFlowPattern !== 'custom') {
                    layer.lastPowerFlowPattern = layer.powerFlowPattern;
                }
                layer.powerFlowPattern = 'custom';
                layer.powerCustomPath = true;
                this.ensureCustomPowerState(layer);
            } else {
                layer.powerFlowPattern = layer.lastPowerFlowPattern || 'tl-h';
                layer.powerCustomPath = false;
            }
        });
        if (!enabled) {
            this.powerCustomSelection.clear();
        }
        this.saveState('Power Custom Mode Toggle');
        this.saveClientSideProperties();
        this.updateLayers(this.getSelectedLayers());
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
        const off = this._getLayerWorkspaceOffset(layer);
        const minX = Math.min(rect.x1, rect.x2) - off.wx;
        const maxX = Math.max(rect.x1, rect.x2) - off.wx;
        const minY = Math.min(rect.y1, rect.y2) - off.wy;
        const maxY = Math.max(rect.y1, rect.y2) - off.wy;
        layer.panels.forEach(panel => {
            if (panel.hidden) return;
            const intersects = panel.x <= maxX && (panel.x + panel.width) >= minX &&
                panel.y <= maxY && (panel.y + panel.height) >= minY;
            if (intersects) this.customSelection.add(this.getPanelKey(panel));
        });
        this.updateCustomFlowUI();
        window.canvasRenderer.render();
    }

    // ---------- Pixel Map bulk-select (panel selection on the Pixel Map tab) ----------

    selectPixelMapPanelsInRect(layer, rect) {
        if (!layer || !rect) return;
        this.pixelMapSelection.clear();
        // rect is in workspace coords; panel coords are canvas-relative,
        // shift by the layer's parent canvas's workspace offset before
        // comparing. (No-op for single-canvas projects.)
        const off = this._getLayerWorkspaceOffset(layer);
        const minX = Math.min(rect.x1, rect.x2) - off.wx;
        const maxX = Math.max(rect.x1, rect.x2) - off.wx;
        const minY = Math.min(rect.y1, rect.y2) - off.wy;
        const maxY = Math.max(rect.y1, rect.y2) - off.wy;
        // Include hidden ("blank") panels so they can be selected for bulk
        // restore via the sidebar / Alt+click action.
        (layer.panels || []).forEach(panel => {
            const intersects = panel.x <= maxX && (panel.x + panel.width) >= minX &&
                panel.y <= maxY && (panel.y + panel.height) >= minY;
            if (intersects) this.pixelMapSelection.add(this.getPanelKey(panel));
        });
        this.updatePixelMapBulkActionUI();
        window.canvasRenderer.render();
    }

    togglePixelMapPanelSelection(panel) {
        if (!panel) return;
        const key = this.getPanelKey(panel);
        if (this.pixelMapSelection.has(key)) {
            this.pixelMapSelection.delete(key);
        } else {
            this.pixelMapSelection.add(key);
        }
        this.updatePixelMapBulkActionUI();
        window.canvasRenderer.render();
    }

    clearPixelMapSelection() {
        if (!this.pixelMapSelection || this.pixelMapSelection.size === 0) return;
        this.pixelMapSelection.clear();
        this.updatePixelMapBulkActionUI();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    getPixelMapSelectedPanels() {
        if (!this.currentLayer || !this.currentLayer.panels) return [];
        return this.currentLayer.panels.filter(p => this.pixelMapSelection.has(this.getPanelKey(p)));
    }

    /**
     * Auto-detect half-tile direction for a panel based on its visible neighbors:
     *  - top/bottom edge (no neighbor above or below): 'height'
     *  - left/right edge (no neighbor left or right): 'width'
     *  - corner (two missing): default 'height' (top/bottom is the common case)
     *  - interior (all four neighbors visible): 'height' (rare; user can force-W via UI)
     */
    autoDetectHalfDirection(layer, panel) {
        if (!layer || !panel) return 'height';
        const get = (r, c) => (layer.panels || []).find(p => p.row === r && p.col === c);
        const neighborVisible = (r, c) => {
            const n = get(r, c);
            return !!(n && !n.hidden);
        };
        const hasAbove = neighborVisible(panel.row - 1, panel.col);
        const hasBelow = neighborVisible(panel.row + 1, panel.col);
        const hasLeft = neighborVisible(panel.row, panel.col - 1);
        const hasRight = neighborVisible(panel.row, panel.col + 1);
        const verticalEdge = !hasAbove || !hasBelow;
        const horizontalEdge = !hasLeft || !hasRight;
        if (verticalEdge && !horizontalEdge) return 'height';
        if (horizontalEdge && !verticalEdge) return 'width';
        // Corner or interior, default to 'height' (top/bottom edges are the common case).
        return 'height';
    }

    async setPanelsHalfTileBulk(panels, halfTile) {
        if (!this.currentLayer || !panels || panels.length === 0) return;
        const layerId = this.currentLayer.id;
        // For 'auto', vote across the selection: pick the direction the
        // majority of panels would auto-detect to, then apply that uniformly.
        // Avoids a row of selected panels splitting into different directions
        // when one happens to be an interior panel.
        let resolved = halfTile;
        if (halfTile === 'auto') {
            let widthVotes = 0;
            let heightVotes = 0;
            panels.forEach(p => {
                const d = this.autoDetectHalfDirection(this.currentLayer, p);
                if (d === 'width') widthVotes++;
                else heightVotes++;
            });
            // Tie goes to 'height' (top/bottom is the more common case).
            resolved = widthVotes > heightVotes ? 'width' : 'height';
        }
        const body = {
            panels: panels.map(p => ({
                id: p.id,
                halfTile: resolved,
            })),
        };
        try {
            const res = await fetch(`/api/layer/${layerId}/panels/set_half_tile`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            await res.json();
        } catch (err) {
            console.error('setPanelsHalfTileBulk failed', err);
            return;
        }
        this.saveState('Bulk Set Half-tile');
        sendClientLog && sendClientLog('bulk_set_half_tile', {
            layer_id: layerId,
            count: panels.length,
            mode: halfTile,
        });
    }

    /**
     * Bulk hide/show panels, what the UI calls "Set Blank" (matching the
     * Alt+click behaviour, which toggles the per-panel `hidden` flag so the
     * cabinet disappears from the wall layout).
     */
    async setPanelsBlankBulk(panels, blank) {
        if (!this.currentLayer || !panels || panels.length === 0) return;
        const layerId = this.currentLayer.id;
        const targetHidden = !!blank;
        const toChange = panels.filter(p => !!p.hidden !== targetHidden);
        if (toChange.length === 0) return;
        // Apply locally so the canvas updates immediately while the server PUT is in flight.
        toChange.forEach(p => { p.hidden = targetHidden; });
        if (window.canvasRenderer) window.canvasRenderer.render();
        try {
            await fetch(`/api/layer/${layerId}/panels/set_hidden`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ panels: toChange.map(p => ({ id: p.id, hidden: targetHidden })) }),
            });
        } catch (err) {
            console.error('setPanelsBlankBulk failed', err);
        }
        this.saveState('Bulk Set Blank');
        sendClientLog && sendClientLog('bulk_set_blank', {
            layer_id: layerId,
            count: toChange.length,
            hidden: targetHidden,
        });
    }

    /**
     * Update the sidebar bulk-action panel based on current selection.
     * Shows count + action buttons when at least one panel is selected,
     * hides when empty.
     */
    updatePixelMapBulkActionUI() {
        const panel = document.getElementById('pixel-map-bulk-actions');
        if (!panel) return;
        const count = this.pixelMapSelection ? this.pixelMapSelection.size : 0;
        const countEl = document.getElementById('pixel-map-bulk-count');
        // Wrap label too so we can fix pluralization without rebuilding markup.
        const labelEl = document.getElementById('pixel-map-bulk-label');
        if (count > 0) {
            panel.style.display = 'block';
            if (countEl) countEl.textContent = count.toLocaleString();
            if (labelEl) labelEl.textContent = count === 1 ? 'panel' : 'panels';
        } else {
            panel.style.display = 'none';
        }
    }

    selectPowerPanelsInRect(layer, rect) {
        if (!layer) return;
        if (!this.isCustomPower(layer)) return;
        this.powerCustomSelection.clear();
        const off = this._getLayerWorkspaceOffset(layer);
        const minX = Math.min(rect.x1, rect.x2) - off.wx;
        const maxX = Math.max(rect.x1, rect.x2) - off.wx;
        const minY = Math.min(rect.y1, rect.y2) - off.wy;
        const maxY = Math.max(rect.y1, rect.y2) - off.wy;
        layer.panels.forEach(panel => {
            if (panel.hidden) return;
            const intersects = panel.x <= maxX && (panel.x + panel.width) >= minX &&
                panel.y <= maxY && (panel.y + panel.height) >= minY;
            if (intersects) this.powerCustomSelection.add(this.getPanelKey(panel));
        });
        this.updateCustomPowerUI();
        window.canvasRenderer.render();
    }

    /**
     * Find the OTHER port number (if any) that already owns this panel in
     * the layer's custom data-flow paths. Returns the conflicting port's
     * number, or null if the panel is unassigned (or only assigned to the
     * caller-supplied excludePortNum, which we treat as "not a conflict").
     */
    _findPanelOwnerPort(layer, panel, excludePortNum) {
        if (!layer || !layer.customPortPaths || !panel) return null;
        const key = `${panel.row},${panel.col}`;
        for (const portNumStr of Object.keys(layer.customPortPaths)) {
            const portNum = Number(portNumStr) || portNumStr;
            if (portNum === excludePortNum) continue;
            const path = layer.customPortPaths[portNumStr] || [];
            if (path.some(p => `${p.row},${p.col}` === key)) return portNum;
        }
        return null;
    }

    /**
     * Same as _findPanelOwnerPort but for power circuits.
     */
    _findPanelOwnerCircuit(layer, panel, excludeCircuitNum) {
        if (!layer || !layer.powerCustomPaths || !panel) return null;
        const key = `${panel.row},${panel.col}`;
        for (const circuitNumStr of Object.keys(layer.powerCustomPaths)) {
            const circuitNum = Number(circuitNumStr) || circuitNumStr;
            if (circuitNum === excludeCircuitNum) continue;
            const path = layer.powerCustomPaths[circuitNumStr] || [];
            if (path.some(p => `${p.row},${p.col}` === key)) return circuitNum;
        }
        return null;
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
        if (exists) return;
        // Reject if the panel already belongs to a different port, user
        // must clear the existing assignment first. Avoids silent
        // double-mapping that the user has to undo manually.
        const conflict = this._findPanelOwnerPort(this.currentLayer, panel, portNum);
        if (conflict !== null) {
            if (typeof this._toast === 'function') {
                this._toast(`Panel R${panel.row + 1}C${panel.col + 1} is already wired to port ${conflict}. Clear it from port ${conflict} first.`, true);
            }
            return;
        }
        this.currentLayer.customPortPaths[portNum].push({ row: panel.row, col: panel.col });
        this.saveState('Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel port assignments persist.
        this.updateLayers(this.getSelectedLayers());
        if (this.customDebug) {
            console.log('[CustomFlow] Add panel', { portNum, row: panel.row, col: panel.col });
        }
        this.updatePortLabelEditor();
        window.canvasRenderer.render();
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
        if (exists) return;
        const conflict = this._findPanelOwnerCircuit(this.currentLayer, panel, circuitNum);
        if (conflict !== null) {
            if (typeof this._toast === 'function') {
                this._toast(`Panel R${panel.row + 1}C${panel.col + 1} is already wired to circuit ${conflict}. Clear it from circuit ${conflict} first.`, true);
            }
            return;
        }
        this.currentLayer.powerCustomPaths[circuitNum].push({ row: panel.row, col: panel.col });
        this.saveState('Power Custom Path Edit');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so per-panel circuit assignments persist.
        this.updateLayers(this.getSelectedLayers());
        if (this.powerCustomDebug) {
            console.log('[CustomPower] Add panel', { circuitNum, row: panel.row, col: panel.col });
        }
        window.canvasRenderer.render();
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
        // Reject the entire pattern apply if any selected panel already
        // belongs to a different port. Prevents silent double-mapping.
        const conflicts = [];
        for (const p of ordered) {
            const owner = this._findPanelOwnerPort(this.currentLayer, p, portNum);
            if (owner !== null) conflicts.push({ row: p.row, col: p.col, owner });
        }
        if (conflicts.length > 0) {
            const sample = conflicts.slice(0, 3)
                .map(c => `R${c.row + 1}C${c.col + 1}→port ${c.owner}`).join(', ');
            const more = conflicts.length > 3 ? ` (+${conflicts.length - 3} more)` : '';
            if (typeof this._toast === 'function') {
                this._toast(`Cannot apply: ${conflicts.length} panel${conflicts.length === 1 ? '' : 's'} already wired to other ports, ${sample}${more}.`, true);
            }
            return;
        }
        this.currentLayer.customPortPaths[portNum] = ordered.map(p => ({ row: p.row, col: p.col }));
        this.saveState('Custom Pattern Apply');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so the bulk pattern assignment persists.
        this.updateLayers(this.getSelectedLayers());
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
        // Reject if any selected panel already belongs to a different
        // circuit, same policy as data-flow custom pattern apply.
        const conflicts = [];
        for (const p of ordered) {
            const owner = this._findPanelOwnerCircuit(this.currentLayer, p, circuitNum);
            if (owner !== null) conflicts.push({ row: p.row, col: p.col, owner });
        }
        if (conflicts.length > 0) {
            const sample = conflicts.slice(0, 3)
                .map(c => `R${c.row + 1}C${c.col + 1}→circuit ${c.owner}`).join(', ');
            const more = conflicts.length > 3 ? ` (+${conflicts.length - 3} more)` : '';
            if (typeof this._toast === 'function') {
                this._toast(`Cannot apply: ${conflicts.length} panel${conflicts.length === 1 ? '' : 's'} already wired to other circuits, ${sample}${more}.`, true);
            }
            return;
        }
        this.currentLayer.powerCustomPaths[circuitNum] = ordered.map(p => ({ row: p.row, col: p.col }));
        this.saveState('Power Custom Pattern Apply');
        this.saveClientSideProperties();
        // v0.8.2: PUT to server so the bulk pattern assignment persists.
        this.updateLayers(this.getSelectedLayers());
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
            
            const layerType = layer.type || 'screen';
            const isImage = layerType === 'image';
            const isText = layerType === 'text';
            const activePanels = (isImage || isText) ? 0 : layer.panels.filter(p => !p.blank && !p.hidden).length;

            let infoText;
            if (isText) {
                const preview = (layer.textContent || '').substring(0, 30);
                infoText = `Text • ${layer.fontSize || 24}px${preview ? ' • ' + preview : ''}`;
            } else if (isImage) {
                infoText = `${layer.imageWidth || 0}×${layer.imageHeight || 0}px • ${Math.round((layer.imageScale || 1) * 100)}%`;
            } else {
                infoText = `${layer.columns}x${layer.rows} (${activePanels} panels) • ${layer.cabinet_width}×${layer.cabinet_height}px`;
            }
            const lockBadge = layer.locked ? '<span title="Locked" style="margin-left: 6px; color:#bbb;">🔒</span>' : '';
            // v0.8 Slice 2.5: per-layer ▲▼ arrows replace the global Up/Down
            // buttons. Disabled state (top/bottom of the layer's canvas group)
            // is computed in updateLayerOrderControls() after the regroup pass
            // so we know the within-canvas ordering.
            layerDiv.innerHTML = `
                <div class="layer-header">
                    <div style="display:flex; align-items:center; gap:4px; flex:1; min-width:0;">
                        <input type="text" class="layer-name-input" data-layer-id="${layer.id}" value="${layer.name}" style="background: transparent; border: 1px solid transparent; color: #e0e0e0; padding: 2px 4px; border-radius: 3px; font-size: 13px; font-weight: 600; flex:1; min-width:0;">
                        ${lockBadge}
                    </div>
                    <div class="layer-controls">
                        <div class="layer-arrows">
                            <button class="layer-btn layer-move-up" data-layer-id="${layer.id}" title="Move up within canvas">▲</button>
                            <button class="layer-btn layer-move-down" data-layer-id="${layer.id}" title="Move down within canvas">▼</button>
                        </div>
                        <button class="layer-btn" onclick="app.toggleLayerVisibility(${layer.id})" title="Toggle Visibility">
                            ${layer.visible ? '👁' : '👁‍🗨'}
                        </button>
                    </div>
                </div>
                <div class="layer-info">
                    ${infoText}
                </div>
            `;
            
            // Per-layer reorder arrows (Slice 2.5).
            const upArrow = layerDiv.querySelector('.layer-move-up');
            const downArrow = layerDiv.querySelector('.layer-move-down');
            if (upArrow) {
                upArrow.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (upArrow.disabled) return;
                    this.moveLayerWithinCanvas(layer.id, -1);
                });
            }
            if (downArrow) {
                downArrow.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (downArrow.disabled) return;
                    this.moveLayerWithinCanvas(layer.id, 1);
                });
            }

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
            
            // Handle name input: single-click selects layer, double-click edits name
            const nameInput = layerDiv.querySelector('.layer-name-input');
            nameInput.readOnly = true;
            nameInput.draggable = true;
            nameInput.style.cursor = 'default';
            nameInput.addEventListener('dragstart', handleDragStart);

            const enterEditMode = () => {
                nameInput.readOnly = false;
                nameInput.draggable = false;
                nameInput.style.cursor = 'text';
                nameInput.style.border = '1px solid #4A90E2';
                nameInput.style.background = '#1a1a1a';
                nameInput.focus();
                nameInput.select();
            };

            const exitEditMode = () => {
                nameInput.readOnly = true;
                nameInput.draggable = true;
                nameInput.style.cursor = 'default';
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
            };

            nameInput.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                enterEditMode();
            });
            nameInput.addEventListener('blur', exitEditMode);
            nameInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    nameInput.blur();
                }
                if (!nameInput.readOnly) e.stopPropagation();
            });
            
            container.appendChild(layerDiv);
        });

        // v0.8 Slice 2: regroup the flat layer list by canvas. The existing
        // layer items above are preserved as-is, we just lift them into
        // per-canvas group containers and add canvas headers + per-canvas
        // "+ Add Screen" buttons + cross-canvas drag/drop.
        this.regroupLayersByCanvas(container);

        this.updateLayerOrderControls();
    }

    // -------------------------------------------------------------------
    // Multi-canvas (v0.8 Slice 2), sidebar canvas grouping.
    //
    // Slice 2 keeps workspace rendering unchanged; the sidebar restructure
    // is the entire visible deliverable. Each canvas gets a header row
    // (color swatch / name / 👁 / ⋮ / drag handle), its layers underneath
    // (filtered by layer.canvas_id), and a per-canvas "+ Add Screen"
    // button. A canvas drag handle reorders canvases. Layers can be
    // dragged onto another group's header to move them cross-canvas
    // (Cmd/Alt = duplicate).
    // -------------------------------------------------------------------

    regroupLayersByCanvas(container) {
        const project = this.project;
        if (!project || !Array.isArray(project.canvases) || project.canvases.length === 0) return;
        const activeId = project.active_canvas_id;

        // Snapshot the existing rendered layer items, keyed by id, then clear.
        const layerNodes = new Map();
        container.querySelectorAll('.layer-item').forEach(el => {
            const lid = parseInt(el.dataset.layerId, 10);
            if (Number.isFinite(lid)) layerNodes.set(lid, el);
        });
        container.innerHTML = '';

        // v0.8.6.1: pick the layer's view-effective canvas so the sidebar
        // grouping matches what the canvas is rendering. Show Look / Data /
        // Power group by `show_canvas_id || canvas_id`; Pixel Map / Cabinet
        // ID group by `canvas_id`.
        const isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const layerCanvasId = (l) => (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;

        // Sidebar shows canvases in array order, with each canvas's
        // (reverse-ordered) layers underneath, matches the existing
        // newest-on-top convention.
        project.canvases.forEach(canvas => {
            const group = this.buildCanvasGroupEl(canvas, activeId === canvas.id);
            container.appendChild(group);
            const body = group.querySelector('.canvas-group-body');

            // Append matching layer nodes in reverse render order
            // (Photoshop style, newest on top).
            const reversed = [...project.layers].reverse();
            reversed.forEach(layer => {
                if (layerCanvasId(layer) !== canvas.id) return;
                const node = layerNodes.get(layer.id);
                if (node) body.appendChild(node);
            });
        });
    }

    buildCanvasGroupEl(canvas, isActive) {
        const wrap = document.createElement('div');
        wrap.className = 'canvas-group' + (isActive ? ' active' : '');
        if (canvas.visible === false) wrap.classList.add('hidden');
        wrap.dataset.canvasId = canvas.id;
        wrap.style.setProperty('--canvas-color', canvas.color || '#4A90E2');

        // v0.8.6.1: count by view-effective canvas so the header count
        // matches the layers actually shown under this group in the
        // current view (Show Look uses show_canvas_id when set).
        const _isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const _effCid = (l) => (_isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
        const layerCount = (this.project.layers || []).filter(l => _effCid(l) === canvas.id).length;
        wrap.innerHTML = `
            <div class="canvas-group-header" draggable="true" title="Click to activate · Drag to reorder">
                <span class="canvas-drag-handle" title="Drag to reorder">⋮⋮</span>
                <span class="canvas-color-swatch" style="background:${canvas.color || '#4A90E2'};"></span>
                <input class="canvas-name-input" type="text" value="${this._escapeAttr(canvas.name || 'Canvas')}" readonly>
                <button class="canvas-vis-btn" title="Toggle canvas visibility">${canvas.visible === false ? '👁‍🗨' : '👁'}</button>
                <button class="canvas-menu-btn" title="Canvas actions">⋮</button>
            </div>
            <div class="canvas-group-body"></div>
            <div class="canvas-group-footer">
                <button class="btn btn-secondary canvas-add-btn" title="Add a layer to this canvas">+ Add</button>
            </div>
        `;
        this._wireCanvasGroupEl(wrap, canvas, layerCount);
        return wrap;
    }

    _escapeAttr(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    _wireCanvasGroupEl(wrap, canvas, layerCount) {
        const header = wrap.querySelector('.canvas-group-header');
        const nameInput = wrap.querySelector('.canvas-name-input');
        const visBtn = wrap.querySelector('.canvas-vis-btn');
        const menuBtn = wrap.querySelector('.canvas-menu-btn');
        const addBtn = wrap.querySelector('.canvas-add-btn');

        // Click header anywhere except on inputs/buttons => activate canvas.
        header.addEventListener('click', (e) => {
            if (e.target.closest('button') || e.target.closest('input')) return;
            this.setActiveCanvas(canvas.id);
        });

        // Double-click name to rename inline.
        nameInput.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            nameInput.readOnly = false;
            nameInput.focus();
            nameInput.select();
        });
        const commitName = () => {
            nameInput.readOnly = true;
            const newName = nameInput.value.trim();
            if (newName && newName !== canvas.name) {
                this.updateCanvas(canvas.id, { name: newName });
            } else {
                nameInput.value = canvas.name || '';
            }
        };
        nameInput.addEventListener('blur', commitName);
        nameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); nameInput.blur(); }
            else if (e.key === 'Escape') { nameInput.value = canvas.name || ''; nameInput.blur(); }
            if (!nameInput.readOnly) e.stopPropagation();
        });

        visBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.updateCanvas(canvas.id, { visible: canvas.visible === false });
        });

        menuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.openCanvasMenu(canvas, menuBtn);
        });

        addBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.openCanvasAddMenu(canvas, addBtn);
        });

        // -- Drag & drop --
        // Drag canvas header => reorder canvases.
        header.addEventListener('dragstart', (e) => {
            // If the drag originated from the name input (when readonly was true
            // and user grabbed the field), still treat as canvas reorder.
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('application/x-canvas-id', canvas.id);
            e.dataTransfer.setData('text/plain', `canvas:${canvas.id}`);
            this._dragCanvasId = canvas.id;
            wrap.classList.add('dragging');
        });
        header.addEventListener('dragend', () => {
            wrap.classList.remove('dragging');
            this._dragCanvasId = null;
        });

        // Drop target: canvas header accepts canvas-reorder OR layer drop.
        wrap.addEventListener('dragover', (e) => {
            // Layer being dragged onto this canvas => indicate cross-canvas drop.
            const isCanvas = !!this._dragCanvasId;
            const isLayer = this.dragLayerId != null && !isCanvas;
            if (!isCanvas && !isLayer) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = (isLayer && (e.metaKey || e.altKey)) ? 'copy' : 'move';
            wrap.classList.add('drag-target');
        });
        wrap.addEventListener('dragleave', (e) => {
            // Only clear the highlight when leaving the wrap entirely.
            if (!wrap.contains(e.relatedTarget)) wrap.classList.remove('drag-target');
        });
        wrap.addEventListener('drop', (e) => {
            wrap.classList.remove('drag-target');
            // Canvas reorder?
            const draggedCanvasId = this._dragCanvasId
                || e.dataTransfer.getData('application/x-canvas-id');
            if (draggedCanvasId && draggedCanvasId !== canvas.id) {
                e.preventDefault();
                this.reorderCanvasBeforeTarget(draggedCanvasId, canvas.id);
                return;
            }
            // Cross-canvas layer drop?
            // Only handle when the drop landed on the canvas header / footer
            // (not on an existing layer-item inside this canvas), otherwise
            // we would double-fire alongside the within-list reorder handler.
            if (this.dragLayerId != null) {
                const onLayerItem = e.target.closest && e.target.closest('.layer-item');
                if (onLayerItem) return;
                const draggedLayer = (this.project.layers || []).find(l => l.id === this.dragLayerId);
                if (!draggedLayer) return;
                // v0.8.6.1: in Show Look / Data / Power, dropping onto a
                // canvas group rewrites show_canvas_id (Show Look layer
                // membership) so Pixel Map's canvas_id stays untouched.
                // Pixel Map / Cabinet ID drops still rewrite canvas_id.
                const _isShowView = !!(window.canvasRenderer
                    && window.canvasRenderer.isShowLookView
                    && window.canvasRenderer.isShowLookView());
                const effCid = _isShowView
                    ? (draggedLayer.show_canvas_id || draggedLayer.canvas_id)
                    : draggedLayer.canvas_id;
                if (effCid !== canvas.id) {
                    e.preventDefault();
                    if (_isShowView) {
                        if (typeof this.moveLayerShowCanvas === 'function') {
                            this.moveLayerShowCanvas(draggedLayer.id, canvas.id);
                        }
                    } else {
                        const mode = (e.metaKey || e.altKey) ? 'duplicate' : 'move';
                        this.moveLayerToCanvas(draggedLayer.id, canvas.id, mode);
                    }
                }
            }
        });
    }

    // -------------------------------------------------------------------
    // Canvas API helpers (Slice 2). All call backend endpoints introduced
    // in /api/canvas* and update this.project from the response.
    // -------------------------------------------------------------------

    _applyProjectUpdate(data) {
        if (!data) return;
        // Preserve client-side properties that may be on existing layers
        // before we overwrite the project reference.
        const savedClientProps = {};
        if (this.project && this.project.layers) {
            this.project.layers.forEach(l => {
                savedClientProps[l.id] = this.extractClientSideProps
                    ? this.extractClientSideProps(l) : null;
            });
        }
        this.project = data;
        if (data.layers && this.applyClientSideProperties) {
            // re-apply localStorage-side overrides if available
            try { this.loadClientSideProperties && this.loadClientSideProperties({ skipPreferences: true }); } catch (_) {}
        }
        // If the active canvas's properties changed, sync raster size for
        // the workspace toolbar (Slice 4 will deepen this, Slice 2 just
        // keeps the sidebar consistent).
        if (data.raster_width && data.raster_height && this.syncRasterFromProject) {
            try { this.syncRasterFromProject(); } catch (_) {}
        }
        this.renderLayers();
        // Rebind currentLayer to the fresh object in the new project payload
        // (same id, new reference) and refresh the settings panel inputs so
        // post-mutation values (offset_x snapped to 0,0 after a cross-canvas
        // move, raster size after a resize, etc.) propagate without forcing
        // the user to deselect+reselect to see the change.
        if (this.currentLayer && data.layers) {
            const refreshed = data.layers.find(l => l.id === this.currentLayer.id);
            if (refreshed) {
                this.currentLayer = refreshed;
                if (typeof this.loadLayerToInputs === 'function') {
                    try { this.loadLayerToInputs(); } catch (_) {}
                }
            }
        }
        // Slice 8: re-sync perspective toggles after any canvas mutation
        // (perspective edited on a sibling canvas, active canvas swapped on
        // server, etc.).
        if (typeof this.refreshPerspectiveButtons === 'function') {
            try { this.refreshPerspectiveButtons(); } catch (_) {}
        }
        // Re-render the workspace canvas. The previous `if (this.render)`
        // check was always false (app has no .render method), so the
        // workspace pixels never refreshed after a canvas CRUD response,
        // most visibly: toggling a canvas's visibility updated state but
        // never repainted the workspace, so the canvas appeared not to hide.
        if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
            try { window.canvasRenderer.render(); } catch (_) {}
        }
    }

    addCanvas() {
        // Seed new canvases from the user's preferred default canvas size so
        // every "+ Add Canvas" click matches the same baseline as a brand-new
        // project, not whatever the currently active canvas happens to be.
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : null;
        const body = {};
        if (prefs && Number.isFinite(prefs.rasterWidth) && prefs.rasterWidth > 0) {
            body.raster_width = prefs.rasterWidth;
            body.show_raster_width = prefs.rasterWidth;
        }
        if (prefs && Number.isFinite(prefs.rasterHeight) && prefs.rasterHeight > 0) {
            body.raster_height = prefs.rasterHeight;
            body.show_raster_height = prefs.rasterHeight;
        }
        return fetch('/api/canvas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            // saveState AFTER mutation so the snapshot captures the new canvas.
            // One Cmd+Z then reverts exactly this Add.
            if (typeof this.saveState === 'function') this.saveState('Add Canvas');
        });
    }

    // Canvas mutation routed through one helper so every mutating call
    // gets one (and only one) post-mutation undo entry.
    updateCanvas(canvasId, patch) {
        // Pick the most informative undo label from the patch keys.
        const keys = patch ? Object.keys(patch) : [];
        let label = 'Update Canvas';
        if (keys.includes('name')) label = 'Rename Canvas';
        else if (keys.includes('color')) label = 'Change Canvas Color';
        else if (keys.includes('visible')) label = 'Toggle Canvas Visibility';
        else if (keys.includes('workspace_x') || keys.includes('workspace_y')) label = 'Move Canvas';
        else if (keys.includes('raster_width') || keys.includes('raster_height')
            || keys.includes('show_raster_width') || keys.includes('show_raster_height')) label = 'Resize Canvas';
        else if (keys.includes('data_flow_perspective') || keys.includes('power_perspective')) label = 'Change Perspective';
        return fetch(`/api/canvas/${canvasId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(patch || {})
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            if (typeof this.saveState === 'function') this.saveState(label);
        });
    }

    /**
     * Slice 7: reassign a layer to a different canvas via the existing
     * Slice-2 endpoint. ``mode`` is "move" or "duplicate".
     * - "move": same layer id, offsets reset to 0,0; selection follows.
     * - "duplicate": new layer id appended in target canvas; original
     *   stays put and remains selected.
     */
    /**
     * v0.8.5: Reassign a layer's Show Look canvas membership. Used by
     * cross-canvas drops on the Show Look / Data / Power tabs. Does not
     * touch canvas_id, offset_x/y, or panel geometry, so the layer's
     * Pixel Map / Cabinet ID position and processor membership stay
     * exactly where they were. Pass null to clear the override and let
     * Show Look fall back to mirroring canvas_id.
     */
    moveLayerShowCanvas(layerId, targetCanvasId) {
        return fetch(`/api/layer/${layerId}/show_canvas`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ show_canvas_id: targetCanvasId })
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            if (typeof this.renderLayers === 'function') this.renderLayers();
            if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
                window.canvasRenderer.render();
            }
            if (typeof this.saveState === 'function') {
                this.saveState('Move Layer (Show Look) to Canvas');
            }
            return data;
        });
    }

    /**
     * v0.8.5: Multi-layer Show Look canvas reassign (mirrors moveLayersCrossCanvas).
     */
    async moveLayersShowCanvas(layerIds, targetCanvasId) {
        if (!Array.isArray(layerIds) || layerIds.length === 0) return;
        let lastData = null;
        for (const id of layerIds) {
            const r = await fetch(`/api/layer/${id}/show_canvas`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ show_canvas_id: targetCanvasId })
            });
            lastData = await r.json();
        }
        if (lastData) {
            this._applyProjectUpdate(lastData);
            if (typeof this.renderLayers === 'function') this.renderLayers();
            if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
                window.canvasRenderer.render();
            }
            if (typeof this.saveState === 'function') {
                this.saveState(`Move ${layerIds.length} Layers (Show Look) to Canvas`);
            }
        }
        return lastData;
    }

    moveLayerCrossCanvas(layerId, targetCanvasId, mode) {
        const wantMove = (mode !== 'duplicate');
        return fetch(`/api/layer/${layerId}/canvas`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ canvas_id: targetCanvasId, mode: wantMove ? 'move' : 'duplicate' })
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            // After move: the same layer id now lives in the target canvas;
            // make sure it stays the current layer so the sidebar follows.
            if (wantMove && this.project && Array.isArray(this.project.layers)) {
                const moved = this.project.layers.find(l => l.id === layerId);
                if (moved) {
                    this.currentLayer = moved;
                    if (this.project) this.project.active_canvas_id = targetCanvasId;
                    if (typeof this.renderLayers === 'function') this.renderLayers();
                    if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
                        window.canvasRenderer.render();
                    }
                }
            }
            // saveState AFTER server applies the cross-canvas move so the
            // snapshot includes the canvas_id swap + the snap-to-(0,0) offset
            // reset. Single Cmd+Z reverts the whole operation.
            if (typeof this.saveState === 'function') {
                this.saveState(wantMove ? 'Move Layer to Canvas' : 'Duplicate Layer to Canvas');
            }
            // For duplicate: leave selection on the original (default behavior).
            return data;
        });
    }

    /**
     * Multi-select cross-canvas drag: PUT each selected layer's canvas
     * sequentially (avoids server race), then sync state so all moved
     * layers stay selected and the active canvas follows. Mode applies
     * to ALL layers in the batch (move OR duplicate, not mixed).
     */
    async moveLayersCrossCanvas(layerIds, targetCanvasId, mode) {
        const wantMove = (mode !== 'duplicate');
        if (!Array.isArray(layerIds) || layerIds.length === 0) return;
        let lastData = null;
        for (const id of layerIds) {
            const r = await fetch(`/api/layer/${id}/canvas`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ canvas_id: targetCanvasId, mode: wantMove ? 'move' : 'duplicate' })
            });
            lastData = await r.json();
        }
        if (lastData) {
            this._applyProjectUpdate(lastData);
            if (wantMove && this.project && Array.isArray(this.project.layers)) {
                // Re-select all moved layers (same ids); set active canvas
                // to target so the sidebar reflects the destination.
                this.project.active_canvas_id = targetCanvasId;
                this.selectedLayerIds = new Set(layerIds);
                const primary = this.project.layers.find(l => l.id === layerIds[0]);
                if (primary) this.currentLayer = primary;
                if (typeof this.renderLayers === 'function') this.renderLayers();
                if (window.canvasRenderer && typeof window.canvasRenderer.render === 'function') {
                    window.canvasRenderer.render();
                }
            }
            // saveState AFTER all PUTs settle so one Cmd+Z reverts the whole
            // multi-layer cross-canvas move/duplicate.
            if (typeof this.saveState === 'function') {
                this.saveState(wantMove
                    ? `Move ${layerIds.length} Layers to Canvas`
                    : `Duplicate ${layerIds.length} Layers to Canvas`);
            }
        }
        return lastData;
    }

    /**
     * Slice 5: after a canvas-drag drop, warn (non-blocking) if the
     * dragged canvas's workspace bounds intersect any other visible
     * canvas's bounds. Does NOT auto-snap or reject, just toasts.
     * Bounds use the active view's raster (pixel-map vs show-look),
     * matching what the user sees in `_drawCanvasOutline`.
     */
    _checkCanvasOverlapAndToast(canvasId) {
        if (!this.project || !Array.isArray(this.project.canvases)) return;
        const useShow = !!(window.canvasRenderer && typeof window.canvasRenderer.isShowLookView === 'function'
            && window.canvasRenderer.isShowLookView());
        const bounds = (c) => {
            const w = (useShow && c.show_raster_width) || c.raster_width || 0;
            const h = (useShow && c.show_raster_height) || c.raster_height || 0;
            // v0.8.5.3: in Show Look use the canvas's show workspace
            // position (falls back to workspace_x/y when null). The check
            // was reading workspace_x/y in both views, which gave false
            // overlap toasts when only the show position had moved.
            let x, y;
            if (useShow) {
                x = (c.show_workspace_x == null ? (c.workspace_x || 0) : (c.show_workspace_x || 0));
                y = (c.show_workspace_y == null ? (c.workspace_y || 0) : (c.show_workspace_y || 0));
            } else {
                x = c.workspace_x || 0;
                y = c.workspace_y || 0;
            }
            return { x, y, w, h };
        };
        const dragged = this.project.canvases.find(c => c && c.id === canvasId);
        if (!dragged || dragged.visible === false) return;
        const a = bounds(dragged);
        if (a.w <= 0 || a.h <= 0) return;
        const intersects = (a, b) =>
            a.x < b.x + b.w && a.x + a.w > b.x &&
            a.y < b.y + b.h && a.y + a.h > b.y;
        for (const other of this.project.canvases) {
            if (!other || other.id === canvasId || other.visible === false) continue;
            const b = bounds(other);
            if (b.w <= 0 || b.h <= 0) continue;
            if (intersects(a, b)) {
                this._toast('Canvases overlapping, visual rendering may be confusing.', true);
                return;
            }
        }
    }

    deleteCanvas(canvasId) {
        return fetch(`/api/canvas/${canvasId}`, { method: 'DELETE' })
            .then(r => r.json().then(body => ({ ok: r.ok, body })))
            .then(({ ok, body }) => {
                if (!ok) {
                    this._toast(body && body.error ? body.error : 'Cannot delete canvas', true);
                    return;
                }
                this._applyProjectUpdate(body);
                if (typeof this.saveState === 'function') this.saveState('Delete Canvas');
            });
    }

    duplicateCanvas(canvasId) {
        return fetch(`/api/canvas/${canvasId}/duplicate`, { method: 'POST' })
            .then(r => r.json()).then(data => {
                this._applyProjectUpdate(data);
                if (typeof this.saveState === 'function') this.saveState('Duplicate Canvas');
            });
    }

    setActiveCanvas(canvasId, opts = {}) {
        // Optimistic UI update so the highlight feels instant; backend
        // confirms.
        if (!this.project) return Promise.resolve();
        if (this.project.active_canvas_id === canvasId && !opts.force) {
            // No-op: already active. Skip the network round-trip and
            // re-render to avoid spamming PUTs from layer-selection paths.
            return Promise.resolve();
        }
        this.project.active_canvas_id = canvasId;
        // Slice 5: active canvas constrains selection. Drop any selected
        // layer ids that don't belong to the new active canvas, and clear
        // currentLayer if it's now in a different canvas. Layers without a
        // canvas_id (legacy / orphan) are kept on the safe side. This keeps
        // the user's mental model consistent ("the active canvas is what
        // I'm working in") and prevents stale highlights on the inactive
        // canvas after a click.
        // Slice 13 escape hatch: callers performing an explicit cross-canvas
        // multi-select (shift-click toggle / shift-click range) pass
        // preserveSelection:true to keep their full selection alive, so the
        // user can bulk-edit screens across canvases at once.
        if (!opts.preserveSelection
                && Array.isArray(this.project.layers)
                && this.selectedLayerIds && this.selectedLayerIds.size > 0) {
            const layerById = {};
            for (const l of this.project.layers) layerById[l.id] = l;
            const filtered = new Set();
            for (const id of this.selectedLayerIds) {
                const l = layerById[id];
                if (!l) continue;
                if (!l.canvas_id || l.canvas_id === canvasId) filtered.add(id);
            }
            this.selectedLayerIds = filtered;
        }
        if (!opts.preserveSelection
                && this.currentLayer && this.currentLayer.canvas_id
                && this.currentLayer.canvas_id !== canvasId) {
            // Promote the most-recently-selected layer in the new active
            // canvas (if any) to currentLayer, otherwise null.
            let next = null;
            if (this.selectedLayerIds && this.selectedLayerIds.size > 0
                && Array.isArray(this.project.layers)) {
                const lastId = this.lastSelectedLayerId;
                if (lastId && this.selectedLayerIds.has(lastId)) {
                    next = this.project.layers.find(l => l.id === lastId) || null;
                }
                if (!next) {
                    const firstId = this.selectedLayerIds.values().next().value;
                    next = this.project.layers.find(l => l.id === firstId) || null;
                }
            }
            this.currentLayer = next;
            if (!next) this.lastSelectedLayerId = null;
        }
        // Slice 6: toolbar raster reflects the active canvas's raster.
        // syncRasterFromProject reads straight from the active canvas now,
        // so no project-root mirror needed.
        try { this.syncRasterFromProject(); } catch (_) {}
        // Slice 8: per-canvas perspective, sync the Front/Back toggle state
        // when the active canvas changes so the sidebar reflects the canvas
        // the user is now editing.
        if (typeof this.refreshPerspectiveButtons === 'function') {
            try { this.refreshPerspectiveButtons(); } catch (_) {}
        }
        if (!opts.silent) {
            this.renderLayers();
            if (window.canvasRenderer) window.canvasRenderer.render();
        }
        return fetch(`/api/canvas/${canvasId}/active`, { method: 'PUT' })
            .then(r => r.json()).then(data => {
                // Quietly absorb server state without re-rendering twice.
                if (data && data.canvases) this.project = data;
            });
    }

    /**
     * Slice 6: deprecated, kept as a no-op so any lingering callers don't
     * crash during the deprecation window. The renderer reads straight from
     * the active canvas via accessors now, so there is no project-root copy
     * to keep in sync.
     */
    _syncRootRasterFromActiveCanvas() {
        // intentionally empty, see syncRasterFromProject().
    }

    /**
     * Slice 4: when a layer becomes the user-selected layer, also activate
     * its canvas (if different). Idempotent, setActiveCanvas short-circuits
     * when already active, so we won't spam PUTs from re-selecting the same
     * layer or selecting siblings inside the already-active canvas.
     */
    _activateCanvasForLayer(layer, opts) {
        if (!layer || !layer.canvas_id) return;
        if (!this.project) return;
        if (layer.canvas_id === this.project.active_canvas_id) return;
        this.setActiveCanvas(layer.canvas_id, opts);
    }

    reorderCanvasBeforeTarget(draggedId, targetId) {
        if (!this.project || !this.project.canvases) return;
        const ids = this.project.canvases.map(c => c.id);
        const from = ids.indexOf(draggedId);
        const to = ids.indexOf(targetId);
        if (from < 0 || to < 0 || from === to) return;
        ids.splice(from, 1);
        ids.splice(ids.indexOf(targetId), 0, draggedId);
        return fetch('/api/canvas/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ canvas_ids: ids })
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            if (typeof this.saveState === 'function') this.saveState('Reorder Canvases');
        });
    }

    moveLayerToCanvas(layerId, canvasId, mode = 'move') {
        return fetch(`/api/layer/${layerId}/canvas`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ canvas_id: canvasId, mode })
        }).then(r => r.json()).then(data => {
            this._applyProjectUpdate(data);
            if (typeof this.saveState === 'function') {
                this.saveState(mode === 'duplicate' ? 'Duplicate Layer to Canvas' : 'Move Layer to Canvas');
            }
        });
    }

    // v0.8 Slice 2.5: per-canvas "+ Add" chooser (Screen / Image / Text).
    // Routes to the existing add flows after activating the target canvas
    // so the new layer always lands in the canvas whose "+ Add" was clicked
    // (mirrors the Slice 2 add-screen pattern, server uses active_canvas_id
    // when assigning new layers).
    openCanvasAddMenu(canvas, anchor) {
        document.querySelectorAll('.canvas-add-popup, .canvas-menu-popup, .canvas-color-popup').forEach(el => el.remove());
        const menu = document.createElement('div');
        menu.className = 'canvas-menu-popup canvas-add-popup';
        menu.innerHTML = `
            <button data-action="screen">Screen…</button>
            <button data-action="image">Image / Logo…</button>
            <button data-action="text">Text</button>
        `;
        document.body.appendChild(menu);
        const r = anchor.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.top = `${r.bottom + 4}px`;
        menu.style.left = `${Math.max(8, r.left)}px`;
        menu.style.zIndex = '12000';

        const close = () => {
            menu.remove();
            document.removeEventListener('mousedown', onOutside, true);
            document.removeEventListener('keydown', onKey, true);
        };
        const onOutside = (e) => { if (!menu.contains(e.target)) close(); };
        const onKey = (e) => { if (e.key === 'Escape') close(); };
        setTimeout(() => {
            document.addEventListener('mousedown', onOutside, true);
            document.addEventListener('keydown', onKey, true);
        }, 0);

        menu.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const act = btn.dataset.action;
                close();
                this._handleCanvasAddAction(canvas, act);
            });
        });
    }

    _handleCanvasAddAction(canvas, action) {
        // Activate the target canvas so the existing add flows (which look
        // at active_canvas_id server-side) place the layer correctly.
        const after = () => {
            if (action === 'screen') {
                this.openPresetPicker();
            } else if (action === 'image') {
                this.imageFileAction = 'add';
                const input = document.getElementById('add-image-input');
                if (input) input.click();
            } else if (action === 'text') {
                this.addTextLayer();
            }
        };
        Promise.resolve(this.setActiveCanvas(canvas.id, { silent: true })).then(after);
    }

    openCanvasMenu(canvas, anchor) {
        // Close any pre-existing menu.
        document.querySelectorAll('.canvas-menu-popup').forEach(el => el.remove());
        const menu = document.createElement('div');
        menu.className = 'canvas-menu-popup';
        menu.innerHTML = `
            <button data-action="rename">Rename</button>
            <button data-action="duplicate">Duplicate</button>
            <button data-action="color">Change Color…</button>
            <button data-action="delete" class="danger">Delete</button>
        `;
        document.body.appendChild(menu);
        const r = anchor.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.top = `${r.bottom + 4}px`;
        menu.style.left = `${Math.max(8, r.right - 160)}px`;
        menu.style.zIndex = '12000';

        const close = () => {
            menu.remove();
            document.removeEventListener('mousedown', onOutside, true);
            document.removeEventListener('keydown', onKey, true);
        };
        const onOutside = (e) => { if (!menu.contains(e.target)) close(); };
        const onKey = (e) => { if (e.key === 'Escape') close(); };
        // Defer to avoid catching the click that opened us.
        setTimeout(() => {
            document.addEventListener('mousedown', onOutside, true);
            document.addEventListener('keydown', onKey, true);
        }, 0);

        menu.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const act = btn.dataset.action;
                close();
                this._handleCanvasMenuAction(canvas, act);
            });
        });
    }

    _handleCanvasMenuAction(canvas, action) {
        if (action === 'rename') {
            const input = document.querySelector(`.canvas-group[data-canvas-id="${canvas.id}"] .canvas-name-input`);
            if (input) {
                input.readOnly = false;
                input.focus();
                input.select();
            }
        } else if (action === 'duplicate') {
            this.duplicateCanvas(canvas.id);
        } else if (action === 'color') {
            this.openCanvasColorPicker(canvas);
        } else if (action === 'delete') {
            const layerCount = (this.project.layers || []).filter(l => l.canvas_id === canvas.id).length;
            const msg = layerCount > 0
                ? `Delete canvas '${canvas.name}' and its ${layerCount} layer${layerCount === 1 ? '' : 's'}? This cannot be undone.`
                : `Delete canvas '${canvas.name}'?`;
            if (window.confirm(msg)) this.deleteCanvas(canvas.id);
        }
    }

    openCanvasColorPicker(canvas) {
        document.querySelectorAll('.canvas-color-popup').forEach(el => el.remove());
        const palette = ['#4A90E2', '#F5A623', '#7ED321', '#BD10E0',
                         '#D0021B', '#50E3C2', '#F8E71C', '#9013FE'];
        const popup = document.createElement('div');
        popup.className = 'canvas-color-popup';
        popup.innerHTML = `
            <div class="canvas-color-swatches">
                ${palette.map(c => `<button class="color-swatch" data-color="${c}" style="background:${c};" title="${c}"></button>`).join('')}
            </div>
            <div class="canvas-color-hex-row">
                <label>Hex:</label>
                <input type="text" class="canvas-color-hex" value="${canvas.color || ''}" maxlength="7">
                <button class="canvas-color-apply">Apply</button>
            </div>
        `;
        document.body.appendChild(popup);
        const anchor = document.querySelector(`.canvas-group[data-canvas-id="${canvas.id}"] .canvas-menu-btn`);
        if (anchor) {
            const r = anchor.getBoundingClientRect();
            popup.style.position = 'fixed';
            popup.style.top = `${r.bottom + 4}px`;
            popup.style.left = `${Math.max(8, r.right - 200)}px`;
            popup.style.zIndex = '12000';
        }
        const close = () => {
            popup.remove();
            document.removeEventListener('mousedown', onOutside, true);
        };
        const onOutside = (e) => { if (!popup.contains(e.target)) close(); };
        setTimeout(() => document.addEventListener('mousedown', onOutside, true), 0);

        popup.querySelectorAll('.color-swatch').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.updateCanvas(canvas.id, { color: btn.dataset.color });
                close();
            });
        });
        popup.querySelector('.canvas-color-apply').addEventListener('click', (e) => {
            e.stopPropagation();
            const hex = popup.querySelector('.canvas-color-hex').value.trim();
            if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
                this.updateCanvas(canvas.id, { color: hex });
                close();
            } else {
                this._toast('Invalid hex color (expected #RRGGBB)', true);
            }
        });
    }

    updateLayerOrderControls() {
        // v0.8 Slice 2.5: per-layer ▲▼ arrows. Disable the up arrow on the
        // top-most layer of each canvas group, the down arrow on the
        // bottom-most. Display order in the sidebar is reverse of the layer
        // array (newest on top), so within a canvas the FIRST displayed
        // layer is the LAST one in the array, the up arrow on that one is
        // disabled, etc.
        if (!this.project || !this.project.canvases) return;
        // Group layer ids by canvas, in display order (reverse-array).
        const reversed = [...(this.project.layers || [])].reverse();
        const byCanvas = new Map();
        reversed.forEach(l => {
            if (!byCanvas.has(l.canvas_id)) byCanvas.set(l.canvas_id, []);
            byCanvas.get(l.canvas_id).push(l.id);
        });
        document.querySelectorAll('#layers-list .layer-item').forEach(el => {
            const lid = parseInt(el.dataset.layerId, 10);
            const layer = (this.project.layers || []).find(l => l.id === lid);
            if (!layer) return;
            const ids = byCanvas.get(layer.canvas_id) || [];
            const idx = ids.indexOf(lid);
            const up = el.querySelector('.layer-move-up');
            const down = el.querySelector('.layer-move-down');
            if (up) up.disabled = idx <= 0;
            if (down) down.disabled = idx < 0 || idx >= ids.length - 1;
        });
    }

    moveLayerById(layerId, delta) {
        // Kept for backward compatibility (keyboard shortcuts may call this).
        // Delegates to within-canvas reorder so cross-canvas hops never
        // happen via arrow-key reorder either.
        this.moveLayerWithinCanvas(layerId, delta);
    }

    // v0.8 Slice 2.5: reorder a layer up/down by one slot, but only within
    // its own canvas group. Display order is reverse of array order, so
    // delta=-1 (visual up) corresponds to a HIGHER array index swap.
    moveLayerWithinCanvas(layerId, delta) {
        if (!this.project || !this.project.layers) return;
        const layer = this.project.layers.find(l => l.id === layerId);
        if (!layer) return;
        // Build the within-canvas display-order id list.
        const reversed = [...this.project.layers].reverse();
        const sameCanvasIds = reversed.filter(l => l.canvas_id === layer.canvas_id).map(l => l.id);
        const localIdx = sameCanvasIds.indexOf(layerId);
        const nextLocal = localIdx + delta;
        if (localIdx < 0 || nextLocal < 0 || nextLocal >= sameCanvasIds.length) return;
        const swapWithId = sameCanvasIds[nextLocal];
        // Build the full display-order id list and swap just those two.
        const displayIds = reversed.map(l => l.id);
        const a = displayIds.indexOf(layerId);
        const b = displayIds.indexOf(swapWithId);
        if (a < 0 || b < 0) return;
        [displayIds[a], displayIds[b]] = [displayIds[b], displayIds[a]];
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
    
    /**
     * Slice 6: write a toolbar Raster: W x H change to the active canvas via
     * PUT /api/canvas/<id>. Source-of-truth lives on the canvas object, no
     * project-root mirror. `axis` is 'width' or 'height'; `value` is the new
     * dimension; `isShow` selects show_raster_* vs raster_*.
     *
     * v0.8.5.2: Pixel Map and Show Look rasters are fully independent.
     * Editing one never auto-syncs the other (previously a "linked" edit
     * on Pixel Map also wrote show_raster_*; that contradicted the design
     * goal of independent layouts).
     */
    _writeToolbarRasterToActiveCanvas(axis, value, isShow) {
        if (!this.project || !Array.isArray(this.project.canvases)) return;
        const canvasId = this.project.active_canvas_id;
        const c = this.project.canvases.find(x => x.id === canvasId);
        if (!c) return;
        const patch = {};
        if (isShow) {
            if (axis === 'width')  patch.show_raster_width  = value;
            if (axis === 'height') patch.show_raster_height = value;
        } else {
            if (axis === 'width')  patch.raster_width  = value;
            if (axis === 'height') patch.raster_height = value;
        }
        // Optimistic local update so the renderer (which reads from the
        // canvas object via getters) repaints immediately, before the PUT
        // round-trip. The server response will overwrite this with the
        // canonical state.
        Object.assign(c, patch);
        this.saveRasterSize();
        if (typeof sendClientLog === 'function') {
            sendClientLog('raster_change', {
                axis, value, isShow,
                view: window.canvasRenderer && window.canvasRenderer.viewMode,
                canvas_id: canvasId,
            });
        }
        if (typeof this.updateCanvas === 'function') {
            this.updateCanvas(canvasId, patch);
        }
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
        // Pass a lazy blob factory so JSON.stringify (slow on large multi-canvas
        // projects, ~1MB) runs AFTER showSaveFilePicker resolves. This keeps
        // Chrome's user-activation token fresh for createWritable; otherwise
        // Chrome rejects the write with NotAllowedError and leaves a 0-byte file.
        const project = this.project;
        await this.saveBlobWithPicker(
            () => {
                const projectData = JSON.stringify(project, null, 2);
                return new Blob([projectData], { type: 'application/json' });
            },
            `${this.project.name}.json`,
            'application/json'
        );

        this.addToRecentFiles(this.project);
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
                        // Clean-slate reset so stale sidebar values can't leak into new project
                        this.resetApplicationState();
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
                        this.updateUI();
                        if (this.project.layers && this.project.layers.length > 0) {
                            this.selectLayer(this.project.layers[0]);
                        }
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
                                // Sync the canvas's pixel/show raster backing fields from the
                                // loaded project so Show Look picks up the file's values
                                // (and falls back to the pixel raster when show wasn't saved).
                                this.syncRasterFromProject();
                                this.updateUI();
                                if (this.project.layers && this.project.layers.length > 0) {
                                    this.selectLayer(this.project.layers[0]);
                                }
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
                                this.addToRecentFiles(this.project);
                                sendClientLog('load_project_file_success', { name: this.project.name, layers: this.project.layers ? this.project.layers.length : 0 });
                                // Slice 12: server flagged this file as
                                // freshly migrated from v0.7. Show a one-time
                                // toast and strip the transient flag so it
                                // never ends up in the saved JSON. The toast
                                // is suppressed automatically on subsequent
                                // loads because the saved file now carries
                                // format_version: "0.8".
                                if (data && data._migration_notice) {
                                    delete this.project._migration_notice;
                                    sendClientLog('migration_notice_shown', {
                                        name: this.project.name,
                                        layers: this.project.layers ? this.project.layers.length : 0
                                    });
                                    if (typeof this._toast === 'function') {
                                        this._toast(
                                            'Project upgraded to multi-canvas format (v0.8). Save to keep changes. Older app versions can no longer open this file.',
                                            false,
                                            10000
                                        );
                                    }
                                }
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

    resetApplicationState() {
        this.selectedLayerIds = new Set();
        this.currentLayer = null;
        this.lastSelectedLayerId = null;
        this.selectionAnchorLayerId = null;
        localStorage.removeItem('ledRasterClientProps');
        this.resetHistory('Initial State');
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

    debouncedSaveState(action, delay = 500) {
        this._pendingSaveAction = action;
        if (this._saveStateTimer) clearTimeout(this._saveStateTimer);
        this._saveStateTimer = setTimeout(() => {
            this.saveState(this._pendingSaveAction || action);
            this._saveStateTimer = null;
            this._pendingSaveAction = null;
        }, delay);
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

        if ((layer.type || 'screen') === 'text') {
            const duplicateData = {
                name: getNextName(layer.name),
                offset_x: (layer.offset_x || 0) + 50,
                offset_y: (layer.offset_y || 0) + 50,
                textContent: layer.textContent || '',
                textContentPixelMap: layer.textContentPixelMap || '',
                textContentCabinetId: layer.textContentCabinetId || '',
                textContentShowLook: layer.textContentShowLook || '',
                textContentDataFlow: layer.textContentDataFlow || '',
                textContentPower: layer.textContentPower || '',
                textContentOverridePixelMap: !!layer.textContentOverridePixelMap,
                textContentOverrideCabinetId: !!layer.textContentOverrideCabinetId,
                textContentOverrideShowLook: !!layer.textContentOverrideShowLook,
                textContentOverrideDataFlow: !!layer.textContentOverrideDataFlow,
                textContentOverridePower: !!layer.textContentOverridePower,
                textWidth: layer.textWidth || 400,
                textHeight: layer.textHeight || 100,
                fontSize: layer.fontSize || 24,
                fontFamily: layer.fontFamily || 'Arial',
                fontColor: layer.fontColor || '#ffffff',
                bgColor: layer.bgColor || '#000000',
                bgOpacity: layer.bgOpacity != null ? layer.bgOpacity : 0.7,
                textAlign: layer.textAlign || 'left',
                textPadding: layer.textPadding || 12,
                showBorder: layer.showBorder !== false,
                borderColor: layer.borderColor || '#555555',
                showOnPixelMap: layer.showOnPixelMap !== false,
                showOnCabinetId: layer.showOnCabinetId !== false,
                showOnShowLook: layer.showOnShowLook !== false,
                showOnDataFlow: layer.showOnDataFlow !== false,
                showOnPower: layer.showOnPower !== false,
                showRasterSize: !!layer.showRasterSize,
                showProjectName: !!layer.showProjectName,
                showDate: !!layer.showDate,
                showPrimaryPorts: !!layer.showPrimaryPorts,
                showBackupPorts: !!layer.showBackupPorts,
                showCircuits: !!layer.showCircuits,
                showSinglePhase: !!layer.showSinglePhase,
                showThreePhase: !!layer.showThreePhase,
                fontBold: !!layer.fontBold,
                fontItalic: !!layer.fontItalic,
                fontUnderline: !!layer.fontUnderline
            };
            fetch('/api/layer/add-text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(duplicateData)
            })
            .then(res => res.json())
            .then(newLayer => {
                // Copy text properties to new layer
                Object.assign(newLayer, duplicateData);
                this.upsertProjectLayer(newLayer);
                this.selectLayer(newLayer);
                this.updateUI();
                this.saveState('Duplicate Text Layer');
            });
            return;
        }

        // Collect hidden panel positions (row, col) to apply to new layer.
        // Backwards-compat: older server builds only knew about hiddenPanels.
        const hiddenPanels = layer.panels
            .filter(p => p.hidden)
            .map(p => ({ row: p.row, col: p.col }));
        // v0.8.0 fix: half-tile state was being lost on duplicate. Build a
        // full per-panel state list (halfTile + hidden + blank) so the
        // server can rebuild the duplicate's geometry to match the source.
        const panelStates = layer.panels
            .filter(p => p.hidden || p.blank || (p.halfTile && p.halfTile !== 'none'))
            .map(p => ({
                row: p.row,
                col: p.col,
                halfTile: p.halfTile || 'none',
                hidden: !!p.hidden,
                blank: !!p.blank,
            }));
        
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
            showLabelNameCabinet: layer.showLabelNameCabinet,
            showLabelNameDataFlow: layer.showLabelNameDataFlow,
            showLabelNamePower: layer.showLabelNamePower,
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
            hiddenPanels: hiddenPanels,  // Pass hidden panel info (legacy)
            panelStates: panelStates,    // Half-tile + hidden + blank (v0.8.0)
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

        if ((this.clipboard.type || 'screen') === 'text') {
            const pasteData = {
                name: getNextName(this.clipboard.name),
                offset_x: (this.clipboard.offset_x || 0) + 50,
                offset_y: (this.clipboard.offset_y || 0) + 50,
                textContent: this.clipboard.textContent || '',
                textContentPixelMap: this.clipboard.textContentPixelMap || '',
                textContentCabinetId: this.clipboard.textContentCabinetId || '',
                textContentShowLook: this.clipboard.textContentShowLook || '',
                textContentDataFlow: this.clipboard.textContentDataFlow || '',
                textContentPower: this.clipboard.textContentPower || '',
                textContentOverridePixelMap: !!this.clipboard.textContentOverridePixelMap,
                textContentOverrideCabinetId: !!this.clipboard.textContentOverrideCabinetId,
                textContentOverrideShowLook: !!this.clipboard.textContentOverrideShowLook,
                textContentOverrideDataFlow: !!this.clipboard.textContentOverrideDataFlow,
                textContentOverridePower: !!this.clipboard.textContentOverridePower,
                textWidth: this.clipboard.textWidth || 400,
                textHeight: this.clipboard.textHeight || 100,
                fontSize: this.clipboard.fontSize || 24,
                fontFamily: this.clipboard.fontFamily || 'Arial',
                fontColor: this.clipboard.fontColor || '#ffffff',
                bgColor: this.clipboard.bgColor || '#000000',
                bgOpacity: this.clipboard.bgOpacity != null ? this.clipboard.bgOpacity : 0.7,
                textAlign: this.clipboard.textAlign || 'left',
                textPadding: this.clipboard.textPadding || 12,
                showBorder: this.clipboard.showBorder !== false,
                borderColor: this.clipboard.borderColor || '#555555',
                showOnPixelMap: this.clipboard.showOnPixelMap !== false,
                showOnCabinetId: this.clipboard.showOnCabinetId !== false,
                showOnShowLook: this.clipboard.showOnShowLook !== false,
                showOnDataFlow: this.clipboard.showOnDataFlow !== false,
                showOnPower: this.clipboard.showOnPower !== false,
                showRasterSize: !!this.clipboard.showRasterSize,
                showProjectName: !!this.clipboard.showProjectName,
                showDate: !!this.clipboard.showDate,
                showPrimaryPorts: !!this.clipboard.showPrimaryPorts,
                showBackupPorts: !!this.clipboard.showBackupPorts,
                showCircuits: !!this.clipboard.showCircuits,
                showSinglePhase: !!this.clipboard.showSinglePhase,
                showThreePhase: !!this.clipboard.showThreePhase,
                fontBold: !!this.clipboard.fontBold,
                fontItalic: !!this.clipboard.fontItalic,
                fontUnderline: !!this.clipboard.fontUnderline
            };
            fetch('/api/layer/add-text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pasteData)
            })
            .then(res => res.json())
            .then(newLayer => {
                Object.assign(newLayer, pasteData);
                this.upsertProjectLayer(newLayer);
                this.selectLayer(newLayer);
                this.updateUI();
                this.saveState('Paste Text Layer');
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
            showLabelNameCabinet: this.clipboard.showLabelNameCabinet,
            showLabelNameDataFlow: this.clipboard.showLabelNameDataFlow,
            showLabelNamePower: this.clipboard.showLabelNamePower,
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

    // Evaluate a simple arithmetic expression using + - * / and parentheses.
    // Returns a finite number, or null if the input is empty/invalid. Used by
    // the Watts per Panel field (and anywhere else we want a "spreadsheet-y"
    // numeric input) so users can type e.g. "200+50" or "1000/3" directly.
    evaluateNumericExpression(raw) {
        if (raw == null) return null;
        const s = String(raw).trim();
        if (s === '') return null;
        // Allow only digits, . , whitespace, and the four operators + - * / plus parentheses
        const cleaned = s.replace(/,/g, '').replace(/\s+/g, '');
        if (!/^[-+*/().\d]+$/.test(cleaned)) return null;
        // Reject dangerous patterns (consecutive operators other than a leading unary minus in a sub-expr)
        if (/[*/]{2,}|\+{2,}|-{3,}|[-+*/]$|^[*/]/.test(cleaned)) return null;
        try {
            // Function constructor with no scope access, still safer than eval(),
            // and the regex above guarantees only arithmetic characters are present.
            // eslint-disable-next-line no-new-func
            const result = Function('"use strict"; return (' + cleaned + ');')();
            if (typeof result !== 'number' || !isFinite(result)) return null;
            return result;
        } catch (e) {
            return null;
        }
    }

    // Format an evaluated number for display in the input: drop trailing zeros
    // but keep reasonable precision for fractional results (e.g. 1000/3).
    _formatEvaluatedNumber(n) {
        if (!isFinite(n)) return '0';
        if (Number.isInteger(n)) return String(n);
        // Up to 4 decimal places, trim trailing zeros
        return parseFloat(n.toFixed(4)).toString();
    }
    
    rgbToHex(r, g, b) {
        return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    registerGlobalClientLogging();
    sendClientLog('client_ready', { ua: navigator.userAgent });
    window.app = new LEDRasterApp();

    // Resolume-style help tooltip panel
    const helpBody = document.getElementById('help-tooltip-body');
    const helpDefaultText = 'Move your mouse over the interface element that you would like more info about.';
    if (helpBody) {
        document.addEventListener('mouseover', (e) => {
            const tip = e.target.closest('[data-tooltip]');
            if (tip) {
                helpBody.textContent = tip.dataset.tooltip;
            }
        });
        document.addEventListener('mouseout', (e) => {
            const tip = e.target.closest('[data-tooltip]');
            if (tip) {
                helpBody.textContent = helpDefaultText;
            }
        });
    }
});
