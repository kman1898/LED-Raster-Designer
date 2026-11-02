// app-quick-palettes: the Pixel Map tab's Quick Palettes section - eight
// one-click Color 1 / Color 2 pairs for the selected screens, a style
// switch, Shuffle, and a Hue slider that fine-tunes the set and the
// screens together. The colour maths is quick-palettes.js; the eight pairs
// a user keeps for themselves are a preference (app-preferences.js,
// quickPaletteSource / quickPaletteColors).
import { LEDRasterApp } from './app-core.js';
import {
    QUICK_PALETTE_STYLES, generateQuickPalettes, hueOf, normalizeQuickPalettes, rotateHue,
} from './quick-palettes.js';

const STYLE_KEY = 'ledRasterQuickPaletteStyle';

class _QuickPalettes {
    // ── state ─────────────────────────────────────────────────────────
    // Per session, not per screen: the style the user last picked (kept
    // across launches), the hue the auto set is built round, whether the
    // set was shuffled, and the Hue slider's offset. The set is rebuilt
    // round a screen's own colour when the selection changes to another
    // screen, so picking a swatch never moves the set out from under you.
    _qpState() {
        if (!this._quickPalette) {
            let style = 'tonal';
            try {
                const saved = localStorage.getItem(STYLE_KEY);
                if (saved && QUICK_PALETTE_STYLES[saved]) style = saved;
            } catch (e) { /* storage blocked: the default style */ }
            this._quickPalette = {
                style, baseHue: null, current: null, shuffled: false,
                shift: 0, selectionKey: null, drag: null,
            };
        }
        return this._quickPalette;
    }

    // The selected screens (image and text layers carry no tile colours).
    _qpScreens() {
        return (this.getSelectedLayers() || []).filter(l => l && (l.type || 'screen') === 'screen');
    }

    _qpPairOf(layer) {
        const hex = (c, fallback) => {
            if (c && Number.isFinite(Number(c.r)) && Number.isFinite(Number(c.g)) && Number.isFinite(Number(c.b))) {
                return this.rgbToHex(Number(c.r), Number(c.g), Number(c.b)).toUpperCase();
            }
            return fallback;
        };
        return [hex(layer && layer.color1, '#404680'), hex(layer && layer.color2, '#959CB8')];
    }

    _qpSource() {
        const prefs = this.getPreferences();
        return prefs.quickPaletteSource === 'custom' ? 'custom' : 'auto';
    }

    // The eight pairs as the swatches show them: the user's own set or
    // the one built round the screen's colour, turned by the Hue slider.
    getQuickPalettes() {
        const st = this._qpState();
        let pairs;
        if (this._qpSource() === 'custom') {
            pairs = normalizeQuickPalettes(this.getPreferences().quickPaletteColors);
        } else {
            const keepCurrent = !st.shuffled && st.style === 'tonal' && st.current;
            pairs = generateQuickPalettes(st.baseHue, st.style, keepCurrent ? st.current : null);
        }
        return pairs.map(([a, b]) => [rotateHue(a, st.shift), rotateHue(b, st.shift)]);
    }

    // ── wiring ────────────────────────────────────────────────────────
    setupQuickPalettes() {
        const $ = (id) => document.getElementById(id);
        if (!$('quick-palettes-panel')) return;
        // Handlers read the state each time, never a copy taken here.
        const S = () => this._qpState();

        document.querySelectorAll('#quick-palette-styles .qp-style').forEach(btn => {
            btn.addEventListener('click', () => {
                S().style = btn.dataset.style;
                try { localStorage.setItem(STYLE_KEY, S().style); } catch (e) { /* storage blocked */ }
                this.renderQuickPalettes();
            });
        });

        $('quick-palette-shuffle').addEventListener('click', () => {
            // Shuffle builds a fresh set from a random hue and puts the
            // slider back to 0, so the eight it shows are the new set.
            const st = S();
            st.baseHue = Math.floor(Math.random() * 360);
            st.shuffled = true;
            st.shift = 0;
            this.renderQuickPalettes();
        });

        const hue = $('quick-palette-hue');
        // A drag (or a run of arrow-key steps) turns each selected screen
        // from the colours it had when the drag started, so many small
        // moves never drift, and records one undo step when it ends.
        const startDrag = () => {
            const st = S();
            if (st.drag) return;
            st.drag = {
                from: st.shift,
                layers: this._qpScreens().map(l => ({ id: l.id, pair: this._qpPairOf(l) })),
            };
        };
        const follow = (isFinal) => {
            const st = S();
            startDrag();
            st.shift = Math.max(-180, Math.min(180, parseInt(hue.value, 10) || 0));
            const delta = st.shift - st.drag.from;
            const byId = new Map(st.drag.layers.map(x => [x.id, x.pair]));
            this.applyToSelectedLayers(layer => {
                const pair = byId.get(layer.id);
                if (!pair) return;
                layer.color1 = this.hexToRgb(rotateHue(pair[0], delta));
                layer.color2 = this.hexToRgb(rotateHue(pair[1], delta));
            });
            if (window.canvasRenderer) window.canvasRenderer.render();
            this.renderQuickPalettes();
            this._qpSyncColorInputs();
            if (isFinal) {
                st.drag = null;
                this.updateLayers(this.getSelectedLayers());
                this.debouncedSaveState('Adjust Palette Hue', 400, 'quick-palette-hue');
            }
        };
        hue.addEventListener('pointerdown', startDrag);
        hue.addEventListener('input', () => follow(false));
        hue.addEventListener('change', () => follow(true));
        hue.addEventListener('dblclick', () => { hue.value = '0'; follow(true); });
        $('quick-palette-hue-reset').addEventListener('click', () => {
            if (S().shift === 0) return;
            hue.value = '0';
            follow(true);
        });

        this.renderQuickPalettes();
    }

    // Colour the selected screens with pair `index` of the set on show.
    applyQuickPalette(index) {
        const pair = this.getQuickPalettes()[index];
        if (!pair) return;
        const c1 = this.hexToRgb(pair[0]);
        const c2 = this.hexToRgb(pair[1]);
        this.applyToSelectedLayers(layer => {
            if ((layer.type || 'screen') !== 'screen') return;
            layer.color1 = { ...c1 };
            layer.color2 = { ...c2 };
            // A pair is a checkerboard: a screen on a multi-colour pattern
            // or drawn see-through would not show it, so both go back to
            // the plain checkerboard.
            if (layer.panelColorMode && layer.panelColorMode !== 'checker') layer.panelColorMode = 'checker';
            if (layer.transparentFill) layer.transparentFill = false;
        });
        if (window.canvasRenderer) window.canvasRenderer.render();
        this.updateLayers(this.getSelectedLayers());
        this.saveState('Apply Quick Palette');
        this._qpSyncColorInputs();
        if (typeof this.loadPaletteEditor === 'function') this.loadPaletteEditor();
        const tf = document.getElementById('transparent-fill');
        if (tf && this.currentLayer) tf.checked = !!this.currentLayer.transparentFill;
        this.renderQuickPalettes();
    }

    // The Colors section's two pickers show the current screen's pair.
    _qpSyncColorInputs() {
        const layer = this.currentLayer;
        if (!layer || (layer.type || 'screen') !== 'screen') return;
        const [h1, h2] = this._qpPairOf(layer);
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        set('color1-picker', h1.toLowerCase());
        set('color2-picker', h2.toLowerCase());
        set('color1-hex', h1);
        set('color2-hex', h2);
        const s1 = document.getElementById('color1-picker-swatch');
        const s2 = document.getElementById('color2-picker-swatch');
        if (s1) s1.style.background = h1;
        if (s2) s2.style.background = h2;
        // These fields now show what the screen holds; the Screen Info
        // baseline must agree or the next edit reads them as user edits.
        if (typeof this._captureScreenInfoBaseline === 'function') this._captureScreenInfoBaseline();
    }

    // Called when Screen Info fills for a selection (loadLayerToInputs). A
    // selection of other screens rebuilds the auto set round the first
    // one's colour, slider at 0; the same selection only repaints.
    loadQuickPalettes() {
        const st = this._qpState();
        const screens = this._qpScreens();
        const key = screens.map(l => l.id).join(',');
        if (key !== st.selectionKey && !st.drag) {
            st.selectionKey = key;
            const pair = screens.length ? this._qpPairOf(screens[0]) : null;
            st.current = pair;
            st.baseHue = hueOf(pair ? pair[0] : null);
            st.shuffled = false;
            st.shift = 0;
        }
        this.renderQuickPalettes();
    }

    renderQuickPalettes() {
        const panel = document.getElementById('quick-palettes-panel');
        const host = document.getElementById('quick-palette-swatches');
        if (!panel || !host) return;
        const st = this._qpState();
        const custom = this._qpSource() === 'custom';
        panel.classList.toggle('qp-custom', custom);
        document.querySelectorAll('#quick-palette-styles .qp-style').forEach(btn => {
            btn.setAttribute('aria-pressed', String(btn.dataset.style === st.style));
        });
        const hue = document.getElementById('quick-palette-hue');
        if (hue && String(st.shift) !== hue.value) hue.value = String(st.shift);
        // Paint the track with the screen's Color 1 as each slider position
        // would turn it (relative to where the slider sits now).
        if (hue) {
            const lead = this.currentLayer && (this.currentLayer.type || 'screen') === 'screen'
                ? this._qpPairOf(this.currentLayer)[0] : '#404680';
            const stops = [];
            for (let d = -180; d <= 180; d += 30) stops.push(rotateHue(lead, d - st.shift));
            hue.style.background = `linear-gradient(90deg, ${stops.join(', ')})`;
        }
        const readout = document.getElementById('quick-palette-hue-reset');
        if (readout) readout.textContent = `${st.shift > 0 ? '+' : ''}${st.shift}°`;

        const pairs = this.getQuickPalettes();
        const layer = this.currentLayer && (this.currentLayer.type || 'screen') === 'screen' ? this.currentLayer : null;
        const on = layer ? this._qpPairOf(layer).join('|') : null;
        const disabled = this._qpScreens().length === 0;
        host.innerHTML = '';
        let active = -1;
        pairs.forEach((pair, i) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'qp-swatch';
            b.id = `quick-palette-${i + 1}`;
            b.dataset.index = String(i);
            b.title = `${pair[0]} / ${pair[1]}`;
            b.setAttribute('aria-label', `Palette ${i + 1}: ${pair[0]} and ${pair[1]}`);
            const isOn = on === pair.join('|') && active < 0;
            if (isOn) active = i;
            b.setAttribute('aria-pressed', String(isOn));
            b.disabled = disabled;
            for (let r = 0; r < 3; r++) {
                for (let c = 0; c < 3; c++) {
                    const cell = document.createElement('i');
                    cell.style.background = (r + c) % 2 === 0 ? pair[0] : pair[1];
                    b.appendChild(cell);
                }
            }
            b.addEventListener('click', () => this.applyQuickPalette(i));
            host.appendChild(b);
        });

        const note = document.getElementById('quick-palette-note');
        if (note) {
            if (disabled) note.textContent = 'Select a screen to colour it.';
            else if (custom) note.textContent = 'Your palettes, from Preferences.';
            else if (active === 0 && !st.shuffled && st.style === 'tonal' && st.shift === 0) note.textContent = 'Palette 1 is this screen’s colours.';
            else note.textContent = active >= 0 ? `Palette ${active + 1}` : '';
        }
    }
}

for (const k of Object.getOwnPropertyNames(_QuickPalettes.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_QuickPalettes.prototype, k));
    }
}

