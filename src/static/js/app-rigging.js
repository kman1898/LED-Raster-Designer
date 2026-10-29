// app-rigging: the Header/Footer tab's left column. A Header | Footer choice
// (which row of bars the panel is working on), a row of bar sizes (1-6
// panels wide, any number highlighted; 3 and up sit behind a + button) and
// an Auto button that fits bars of the highlighted sizes across every
// selected screen's width. The sizes and the resulting bars ride on each
// screen (riggingSizes; riggingBars for the header, riggingFooterBars for
// the footer); the bars draw in this view (canvas-rigging.js), and
// riggingPullRows hands them to the pull list (app-pull-list.js).
import { LEDRasterApp } from './app-core.js';
import { setupColorPickerWithHex } from './helpers.js';

const RIGGING_SIZES = [1, 2, 3, 4, 5, 6];
const DEFAULT_SIZES = [1, 2];
const DEFAULT_BAR_COLOR = '#000000';
const DEFAULT_TEXT_COLOR = '#FFFFFF';
// The layer field each row of bars lives in.
const BAR_FIELD = { header: 'riggingBars', footer: 'riggingFooterBars' };
const KIND_WORD = { header: 'Header', footer: 'Footer' };

class _Rigging {
    _wireRigging() {
        const picker = document.getElementById('rigging-size-picker');
        const auto = document.getElementById('rigging-auto-btn');
        const clear = document.getElementById('rigging-clear-btn');
        if (!picker || !auto || !clear) return;

        document.querySelectorAll('#rigging-mode-picker .rigging-mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this._riggingMode = btn.dataset.mode === 'footer' ? 'footer' : 'header';
                this.refreshRiggingPanel();
            });
        });
        picker.querySelectorAll('.rigging-size-btn[data-size]').forEach(btn => {
            btn.addEventListener('click', () => this.toggleRiggingSize(parseInt(btn.dataset.size, 10)));
        });
        // 3 and up stay behind the + until it is pressed.
        const more = document.getElementById('rigging-size-more');
        if (more) more.addEventListener('click', () => {
            this._riggingMoreOpen = !this._riggingMoreOpen;
            this.refreshRiggingPanel();
        });
        const selectAll = document.getElementById('rigging-select-all-btn');
        if (selectAll) selectAll.addEventListener('click', () => this.selectAllRiggingScreens());
        auto.addEventListener('click', () => this.applyAutoRigging());
        clear.addEventListener('click', () => this.clearRiggingBars());

        // Bar color: live while dragging, saved (and undoable) on release.
        // One color pair per screen, for its header and footer bars alike.
        setupColorPickerWithHex('rigging-color', 'rigging-color-hex', (val, isFinal) => {
            const screens = this._riggingScreens();
            if (screens.length === 0) return;
            screens.forEach(l => { l.riggingColor = val; });
            if (isFinal) this.updateLayers(screens, true, 'Bar Color');
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
        setupColorPickerWithHex('rigging-text-color', 'rigging-text-color-hex', (val, isFinal) => {
            const screens = this._riggingScreens();
            if (screens.length === 0) return;
            screens.forEach(l => { l.riggingTextColor = val; });
            if (isFinal) this.updateLayers(screens, true, 'Bar Text Color');
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
    }

    _riggingScreens() {
        return this.getSelectedLayers().filter(l => (l.type || 'screen') === 'screen');
    }

    // Which row the panel works on: 'header' (above the wall) or 'footer'.
    _riggingKind() {
        return this._riggingMode === 'footer' ? 'footer' : 'header';
    }

    // The bars of one row on a screen (always an array).
    riggingBarsOf(layer, kind) {
        const bars = layer && layer[BAR_FIELD[kind === 'footer' ? 'footer' : 'header']];
        return Array.isArray(bars) ? bars : [];
    }

    // The sizes the picker shows: the current screen's. A screen nobody has
    // picked for starts on 1 and 2; a screen whose picks were all switched
    // off keeps its empty list.
    _riggingSizesOf(layer) {
        if (!layer) return [];
        return Array.isArray(layer.riggingSizes) ? layer.riggingSizes : [...DEFAULT_SIZES];
    }

    toggleRiggingSize(size) {
        const screens = this._riggingScreens();
        if (screens.length === 0 || !RIGGING_SIZES.includes(size)) return;
        const primary = this.currentLayer && screens.includes(this.currentLayer) ? this.currentLayer : screens[0];
        const next = new Set(this._riggingSizesOf(primary));
        if (next.has(size)) next.delete(size); else next.add(size);
        const sizes = [...next].sort((a, b) => a - b);
        screens.forEach(l => { l.riggingSizes = [...sizes]; });
        this.updateLayers(screens, true, 'Bar Sizes');
        this.refreshRiggingPanel();
    }

    // Every screen in the show, on every canvas, selected - so one Auto or
    // Clear acts on all of them. (Cmd/Ctrl+A stops at the active canvas.)
    selectAllRiggingScreens() {
        const ids = this._riggingScreensInShow().map(l => l.id);
        if (ids.length === 0) return;
        const primaryId = this.currentLayer && ids.includes(this.currentLayer.id)
            ? this.currentLayer.id : ids[ids.length - 1];
        this.setSelectedLayersByIds(ids, primaryId);
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    applyAutoRigging() {
        const screens = this._riggingScreens();
        if (screens.length === 0) return;
        const kind = this._riggingKind();
        const field = BAR_FIELD[kind];
        const misses = [];
        // The sizes highlighted in the panel are the ones Auto uses, for
        // every selected screen - not each screen's own last pick.
        const primary = this.currentLayer && screens.includes(this.currentLayer) ? this.currentLayer : screens[0];
        const sizes = this._riggingSizesOf(primary);
        screens.forEach(l => {
            l.riggingSizes = [...sizes];
            const bars = RiggingMath.fitBars(l.columns, sizes);
            if (!bars) { misses.push(l.name); return; }
            l[field] = bars;
        });
        this.updateLayers(screens, true, `Auto ${KIND_WORD[kind]} Bars`);
        this.refreshRiggingPanel(misses);
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    clearRiggingBars() {
        const kind = this._riggingKind();
        const field = BAR_FIELD[kind];
        const screens = this._riggingScreens().filter(l => this.riggingBarsOf(l, kind).length);
        if (screens.length === 0) return;
        screens.forEach(l => { l[field] = []; });
        this.updateLayers(screens, true, `Clear ${KIND_WORD[kind]} Bars`);
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // Redraws the panel from the current screen. `misses` names screens the
    // last Auto could not fit with the highlighted sizes.
    refreshRiggingPanel(misses) {
        const picker = document.getElementById('rigging-size-picker');
        if (!picker) return;
        this.refreshRiggingTotals();
        const kind = this._riggingKind();
        const screens = this._riggingScreens();
        const primary = this.currentLayer && screens.includes(this.currentLayer) ? this.currentLayer : screens[0];
        const sizes = this._riggingSizesOf(primary);

        document.querySelectorAll('#rigging-mode-picker .rigging-mode-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === kind);
        });
        picker.querySelectorAll('.rigging-size-btn[data-size]').forEach(btn => {
            btn.classList.toggle('active', sizes.includes(parseInt(btn.dataset.size, 10)));
        });
        // 3-6 show once the + is open, or at once when one of them is lit
        // (a lit size is never hidden).
        const extra = document.getElementById('rigging-size-extra');
        const more = document.getElementById('rigging-size-more');
        const open = !!this._riggingMoreOpen || sizes.some(s => s >= 3);
        if (extra) extra.style.display = open ? 'flex' : 'none';
        if (more) {
            more.textContent = open ? '−' : '+';
            more.classList.toggle('active', open);
            more.setAttribute('aria-expanded', open ? 'true' : 'false');
        }

        const colorEl = document.getElementById('rigging-color');
        const colorHex = document.getElementById('rigging-color-hex');
        const color = (primary && primary.riggingColor) || DEFAULT_BAR_COLOR;
        if (colorEl) colorEl.value = color.toLowerCase();
        if (colorHex) colorHex.value = color.toUpperCase();
        const textEl = document.getElementById('rigging-text-color');
        const textHex = document.getElementById('rigging-text-color-hex');
        const textColor = (primary && primary.riggingTextColor) || DEFAULT_TEXT_COLOR;
        if (textEl) textEl.value = textColor.toLowerCase();
        if (textHex) textHex.value = textColor.toUpperCase();

        const auto = document.getElementById('rigging-auto-btn');
        const clear = document.getElementById('rigging-clear-btn');
        if (auto) auto.disabled = screens.length === 0 || sizes.length === 0;
        if (clear) clear.disabled = !screens.some(l => this.riggingBarsOf(l, kind).length);

        const status = document.getElementById('rigging-status');
        if (!status) return;
        // Blank unless the last Auto could not make a screen's width: the
        // panel shows the totals and nothing else.
        status.textContent = misses && misses.length
            ? `No exact fit with these sizes: ${misses.join(', ')}` : '';
    }

    // Every screen in the show (hidden ones too - they are still on the
    // truck), for the totals box and the pull list.
    _riggingScreensInShow() {
        const layers = (this.project && this.project.layers) || [];
        return layers.filter(l => (l.type || 'screen') === 'screen');
    }

    refreshRiggingTotals() {
        const screens = this._riggingScreensInShow();
        const fill = (kind, countId, listId) => {
            const count = document.getElementById(countId);
            const list = document.getElementById(listId);
            if (!count || !list) return;
            const { total, bySize } = RiggingMath.tally(screens.map(l => this.riggingBarsOf(l, kind)));
            count.textContent = String(total);
            list.textContent = Object.keys(bySize).map(Number).sort((a, b) => b - a)
                .map(size => `${RiggingMath.sizeWord(size)}: ${bySize[size]}`).join('\n');
        };
        fill('header', 'rigging-total-count', 'rigging-total-breakdown');
        fill('footer', 'rigging-footer-total-count', 'rigging-footer-total-breakdown');
    }

    // One pull-list row per bar size and row (header or footer) on a screen:
    // the screen's own line in its position, merged into the show totals
    // like any other gear. `side: 'rigging'` keeps it off the Power and Data
    // cable lists (the binder's pull sheet prints it under its own Header
    // bars and Footer bars tables).
    riggingPullRows(layer) {
        const rows = [];
        for (const kind of ['header', 'footer']) {
            const bySize = RiggingMath.tally([this.riggingBarsOf(layer, kind)]).bySize;
            Object.keys(bySize).map(Number).sort((a, b) => b - a).forEach(size => rows.push({
                type: RiggingMath.barName(size, kind), length: 'EA', qty: bySize[size],
                label: (layer && layer.name) || '', notes: '', side: 'rigging',
            }));
        }
        return rows;
    }
}

for (const k of Object.getOwnPropertyNames(_Rigging.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Rigging.prototype, k));
    }
}
