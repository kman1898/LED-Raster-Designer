// app-rigging: the Header/Footer tab's left column. A Header | Footer choice
// (which row of bars the panel is working on), a row of bar sizes (1-6
// panels wide, any number highlighted; 3 and up sit behind a + button) and
// an Auto button that fits bars of the highlighted sizes across every
// selected screen's width. The sizes and the resulting bars ride on each
// screen (riggingSizes; riggingBars for the header, riggingFooterBars for
// the footer); the bars draw in this view (canvas-rigging.js), and
// riggingPullRows hands them to the pull list (app-pull-list.js).
//
// A LOCKED SCREEN STAYS UNCHANGED: the buttons go through _writableLayers,
// which names the locked screens on every press and hands back the rest;
// the colors, which stream while the picker is dragged, go through the
// applyToSelectedLayers hold.
//
// BARS THAT NO LONGER FIT (owner, 2026-11-06: "the bars no longer fit and
// offer Auto again, rather than changing them silently"): the bars are
// stored as panels, so a wall resized or turned can leave a row that no
// longer adds up to its width. Nothing here touches them until the person
// says. riggingMisfits finds them; the tab's warning box names them and
// offers Auto, a toast says so the moment the edit lands (riggingFitCheck),
// the canvas draws them at their true width against the wall's
// (canvas-rigging.js), and the pull rows, the binder and every export say
// so too. The quantities stay what is drawn: withdrawing them would send
// the wall out with no bars at all.
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
        const fitAuto = document.getElementById('rigging-fit-auto');
        if (fitAuto) fitAuto.addEventListener('click', () => this.fitMisfitRigging());

        // Bar color: live while dragging, saved (and undoable) on release.
        // One color pair per screen, for its header and footer bars alike.
        setupColorPickerWithHex('rigging-color', 'rigging-color-hex', (val, isFinal) => {
            this._setRiggingColor('riggingColor', val, isFinal, 'Bar Color');
        });
        setupColorPickerWithHex('rigging-text-color', 'rigging-text-color-hex', (val, isFinal) => {
            this._setRiggingColor('riggingTextColor', val, isFinal, 'Bar Text Color');
        });
    }

    _setRiggingColor(field, val, isFinal, action) {
        if (this._riggingScreens().length === 0) return;
        this.applyToSelectedLayers(l => {
            if ((l.type || 'screen') === 'screen') l[field] = val;
        });
        if (isFinal) {
            const screens = this._riggingScreens().filter(l => !this._layerLocked(l));
            if (screens.length) this.updateLayers(screens, true, action);
        }
        if (window.canvasRenderer) window.canvasRenderer.render();
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
        const selected = this._riggingScreens();
        if (selected.length === 0 || !RIGGING_SIZES.includes(size)) return;
        const primary = this.currentLayer && selected.includes(this.currentLayer) ? this.currentLayer : selected[0];
        const next = new Set(this._riggingSizesOf(primary));
        if (next.has(size)) next.delete(size); else next.add(size);
        const sizes = [...next].sort((a, b) => a - b);
        const screens = this._writableLayers(selected);
        if (screens.length) {
            screens.forEach(l => { l.riggingSizes = [...sizes]; });
            this.updateLayers(screens, true, 'Bar Sizes');
        }
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
        const selected = this._riggingScreens();
        if (selected.length === 0) return;
        const kind = this._riggingKind();
        const field = BAR_FIELD[kind];
        const misses = [];
        // The sizes highlighted in the panel are the ones Auto uses, for
        // every selected screen - not each screen's own last pick.
        const primary = this.currentLayer && selected.includes(this.currentLayer) ? this.currentLayer : selected[0];
        const sizes = this._riggingSizesOf(primary);
        const screens = this._writableLayers(selected);
        if (screens.length === 0) return;
        screens.forEach(l => {
            l.riggingSizes = [...sizes];
            // Across the wall as it stands: a wall turned a quarter is its
            // rows wide.
            const bars = RiggingMath.fitBars(this.riggingWallPanels(l), sizes);
            if (!bars) { misses.push(l.name); return; }
            l[field] = bars;
        });
        this.updateLayers(screens, true, `Auto ${KIND_WORD[kind]} Bars`);
        this.refreshRiggingPanel(misses);
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // The warning box's Auto: every row that no longer fits, fitted again
    // with its screen's own lit sizes, on whichever screens it is and
    // whatever is selected. One undo step.
    fitMisfitRigging() {
        const misfits = this.riggingShownMisfits();
        if (misfits.length === 0) return;
        const writable = new Set(this._writableLayers([...new Set(misfits.map(m => m.layer))]));
        const misses = [];
        const changed = new Set();
        misfits.filter(m => writable.has(m.layer)).forEach(m => {
            const bars = RiggingMath.fitBars(m.wall, this._riggingSizesOf(m.layer));
            if (!bars) { if (!misses.includes(m.layer.name)) misses.push(m.layer.name); return; }
            m.layer[BAR_FIELD[m.kind]] = bars;
            changed.add(m.layer);
        });
        if (changed.size) this.updateLayers([...changed], true, 'Auto Bars');
        this.refreshRiggingPanel(misses);
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    clearRiggingBars() {
        const kind = this._riggingKind();
        const field = BAR_FIELD[kind];
        const withBars = this._riggingScreens().filter(l => this.riggingBarsOf(l, kind).length);
        if (withBars.length === 0) return;
        const screens = this._writableLayers(withBars);
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

    // Every screen in the show, for Select All Screens.
    _riggingScreensInShow() {
        const layers = (this.project && this.project.layers) || [];
        return layers.filter(l => (l.type || 'screen') === 'screen');
    }

    // The wall's real width in panels: what its bars have to add up to.
    riggingWallPanels(layer) {
        return layer ? RiggingMath.wallPanels(layer.columns, layer.rows, layer.rotation) : 0;
    }

    // The rows on a screen that no longer add up to its wall:
    // [{ layer, kind, word, have, wall }].
    riggingMisfits(layer) {
        const wall = this.riggingWallPanels(layer);
        const out = [];
        for (const kind of ['header', 'footer']) {
            const bars = this.riggingBarsOf(layer, kind);
            if (RiggingMath.barsFit(bars, wall)) continue;
            out.push({ layer, kind, word: KIND_WORD[kind], have: RiggingMath.barPanels(bars), wall });
        }
        return out;
    }

    // The same across the show: the screens the pull list counts, so a
    // hidden screen, which does not count, does not warn.
    riggingShownMisfits() {
        return this._pullScreens().flatMap(l => this.riggingMisfits(l));
    }

    // "Main Wall: header bars cover 12 panels, the wall is 16."
    riggingMisfitLine(m, named = true) {
        const said = `${m.word} bars cover ${m.have} panels, the wall is ${m.wall}.`;
        return named ? `${m.layer.name}: ${said.charAt(0).toLowerCase()}${said.slice(1)}` : said;
    }

    // One message for the toast and the exports, '' when every row fits.
    riggingFitWarning(misfits = this.riggingShownMisfits()) {
        if (!misfits.length) return '';
        const lines = misfits.slice(0, 4).map(m => this.riggingMisfitLine(m));
        if (misfits.length > 4) lines.push(`And ${misfits.length - 4} more.`);
        return `Header/Footer bars no longer fit. ${lines.join(' ')} Press Auto on the Header/Footer tab to fit them.`;
    }

    // After a commit (updateLayers): says so once when the edit left a row
    // of bars that no longer fits on a screen it touched, and redraws the
    // tab's box. A row that was already short says nothing new.
    riggingFitCheck(layers) {
        const misfits = this.riggingShownMisfits();
        const key = (m) => `${m.layer.id}:${m.kind}:${m.have}:${m.wall}`;
        const said = this._riggingFitSaid || new Set();
        const touched = new Set((layers || []).map(l => l.id));
        const fresh = misfits.filter(m => touched.has(m.layer.id) && !said.has(key(m)));
        this._riggingFitSaid = new Set(misfits.map(key));
        if (fresh.length && typeof this._toast === 'function') {
            this._toast(this.riggingFitWarning(fresh), true, 8000);
        }
        this.refreshRiggingTotals();
    }

    // The tab's warning box: the rows that no longer fit, and Auto for them.
    _refreshRiggingFitBox() {
        const box = document.getElementById('rigging-fit-warning');
        const text = document.getElementById('rigging-fit-text');
        if (!box || !text) return;
        const misfits = this.riggingShownMisfits();
        box.style.display = misfits.length ? '' : 'none';
        const lines = misfits.slice(0, 6).map(m => this.riggingMisfitLine(m));
        if (misfits.length > 6) lines.push(`And ${misfits.length - 6} more.`);
        text.textContent = lines.join('\n');
    }

    refreshRiggingTotals() {
        this._refreshRiggingFitBox();
        // The pull list's screens: hidden doesn't count (owner, 2026-11-06),
        // so the box and the pull list can never disagree.
        const screens = this._pullScreens();
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
    // bars and Footer bars tables). A row of bars that no longer fits keeps
    // its quantities, marked on the label every table prints and with the
    // figures in the notes, so what it asks for is never taken as right.
    riggingPullRows(layer) {
        const rows = [];
        const name = (layer && layer.name) || '';
        const misfits = this.riggingMisfits(layer);
        for (const kind of ['header', 'footer']) {
            const miss = misfits.find(m => m.kind === kind);
            const bySize = RiggingMath.tally([this.riggingBarsOf(layer, kind)]).bySize;
            Object.keys(bySize).map(Number).sort((a, b) => b - a).forEach(size => rows.push({
                type: RiggingMath.barName(size, kind), length: 'EA', qty: bySize[size],
                label: miss ? `${name} (bars no longer fit)` : name,
                notes: miss ? `${this.riggingMisfitLine(miss, false)} Press Auto on the Header/Footer tab.` : '',
                side: 'rigging',
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
