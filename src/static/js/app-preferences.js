// app-preferences: the Preferences modal and its model - the defaults, the
// localStorage-backed getPreferences/getLocalPreferences pair, the tabbed
// modal (setup, open, fill, read back) and the font picker with its
// system-font enumeration. Moved verbatim out of app-export-io.js and
// attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The six circuit colours that ship, A to F: the Power tab's "Circuit
// colors" default, and what any position of a stored set falls back to.
const SHIPPED_CIRCUIT_COLORS = ['#BC382F', '#CC6B30', '#D2E94D', '#2CF82B', '#2145DC', '#7414F5'];

class _Preferences {
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
            // ---- Colours a NEW screen starts with (initializeLayerDefaults,
            // and addLayer for the two the server sets: the screen name and
            // the cabinet ID text). A screen that exists keeps its own; the
            // Screen Info panel changes those. The six circuit colours are
            // A to F in order (getDefaultPowerCircuitColors keys them).
            screenNameColor: '#FFFFFF',
            cabinetIdColor: '#FFFFFF',
            dataLineColor: '#FFFFFF',
            dataArrowColor: '#0042AA',
            dataPrimaryColor: '#00FF00',
            dataPrimaryTextColor: '#000000',
            dataBackupColor: '#FF0000',
            dataBackupTextColor: '#FFFFFF',
            powerLineColor: '#FF0000',
            powerArrowColor: '#0042AA',
            powerLabelBgColor: '#D95000',
            powerLabelTextColor: '#000000',
            powerCircuitColors: SHIPPED_CIRCUIT_COLORS.slice(),
            flowPattern: 'tl-h',
            powerFlowPattern: 'tl-h',
            dataLineWidth: 6,
            powerLineWidth: 8,
            processorType: 'novastar-armor',
            lowLatency: false,
            bitDepth: 8,
            frameRate: 60,
            powerVoltage: 110,
            powerAmperage: 15,
            powerWatts: 200,
            canvasGap: 0,
            // Project-wide canvas font. Applies to every label drawn on the
            // canvas (screen names, cabinet IDs, info bars, port/circuit
            // labels, etc.). The picker is populated from the fonts installed
            // on the machine running the app.
            font: 'Arial',
            // The engineer whose name the pull sheet prints. A preference,
            // not a project field: the same person show after show, and a
            // file handed to another engineer prints theirs (app-pull-list).
            engineerName: '',
            // The binder's sheet size and the logo its title block heads
            // with - a PNG / JPEG as a data URL, downscaled to 1200 px on
            // its long side before it is stored (app-binder): the same
            // shop show after show, so preferences like the engineer's
            // name.
            binderSheet: 'tabloid',
            binderLogo: '',
            // Whether a binder sheet wears its border, its title block
            // column and its rev line at all. On: the sheet as it has
            // always been. Off: the drawing takes the whole sheet inside a
            // small margin, named at the foot by its view bubble and
            // subject heading alone.
            binderTitleBlock: true,
            // ---- Distros & multis: what Add distro makes (app-power
            // addDistro), the type a box reads when nothing on the distro
            // says otherwise (distroBoxType's last rung), and what a NEW
            // screen starts with for its breakout and splitter packing
            // (app-core addLayer). Applied at creation only.
            distroRatingA: 400,
            distroVoltage: 208,
            distroPhase: 3,
            multiType: 'soca208',
            breakoutType: 'soca-true1',
            splittersEnabled: false,
            // ---- Binder: what the export dialog's Binder block opens with
            // where the project has no value of its own (app-binder
            // getBinderInfo fills the blanks; the palette, maps and sheet
            // ticks are seeded on open).
            binderScreenOrder: 'alpha',
            binderPalette: 'colour',
            binderMaps: 'both',
            binderCover: true,
            binderPull: true,
            binderHardware: true,
            binderWiring: true,
            binderDesigner: '',
            binderPmName: '',
            binderPmPhone: '',
            binderPmEmail: '',
            binderDrafter: '',
            // ---- Pull sheet & cables: the pull-sheet settings a project
            // starts from (app-pull-list getPullSheetDefaults; the
            // project's own pullSheet wins where set), and the length a
            // NEW snake (app-processors snakePorts), the loose-port quick
            // fill (app-dock) and the power-cable quick fill (app-dock)
            // write. A blank snake length means a new snake starts with
            // none, as it always has.
            pullRev: '1.0',
            powerJumpName: 'Tru-1 Power Jump',
            powerJumpLength: 6,
            dataJumpName: 'Data Jump',
            dataJumpLength: 6,
            snakeHomeRunFt: null,
            loosePortCableFt: 100,
            powerCableFt: 10
        };
    }

    // The six circuit colour picker ids, A to F.
    _circuitColorPrefIds() {
        return ['a', 'b', 'c', 'd', 'e', 'f'].map(l => `pref-power-circuit-color-${l}`);
    }

    // The preference's six circuit colours as a checked list, A to F: a
    // stored entry that is not a hex colour (or a stored set that is not
    // a list at all) falls back to the shipped colour in that position.
    getPreferenceCircuitColorList(prefs) {
        const p = prefs || this.getPreferences();
        const list = Array.isArray(p.powerCircuitColors) ? p.powerCircuitColors : [];
        return SHIPPED_CIRCUIT_COLORS.map((fallback, i) => this.normalizeHexColor(list[i], fallback));
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

    // The seven tabs, in strip order. The strip remembers the last tab
    // opened within the session (not across reloads).
    _prefsTabKeys() {
        return ['wall', 'look', 'data', 'power', 'distros', 'binder', 'pull'];
    }

    showPreferencesTab(key) {
        const modal = document.getElementById('preferences-modal');
        if (!modal) return;
        const want = this._prefsTabKeys().includes(key) ? key : 'wall';
        modal.querySelectorAll('.pm-tabstrip .view-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.key === want);
            t.setAttribute('aria-selected', t.dataset.key === want ? 'true' : 'false');
        });
        modal.querySelectorAll('.pm-section').forEach(s => {
            s.classList.toggle('active', s.dataset.key === want);
        });
        this._prefsTab = want;
    }

    // The Distros & multis pickers list what the app itself offers - the
    // box types the distro OUTPUTS row names, the breakouts the Power
    // panel's #power-breakout-type names - built once from the catalogs
    // in app-power, never restated here.
    _fillPreferenceCatalogs() {
        const fill = (id, list) => {
            const sel = document.getElementById(id);
            if (!sel || sel.options.length || !Array.isArray(list)) return;
            list.forEach(t => {
                const o = document.createElement('option');
                o.value = t.id;
                o.textContent = t.name;
                sel.appendChild(o);
            });
        };
        if (typeof this.getDistroOutputTypes === 'function') {
            fill('pref-multi-type', this.getDistroOutputTypes());
        }
        if (typeof this.getPowerBreakoutTypes === 'function') {
            fill('pref-breakout-type', this.getPowerBreakoutTypes());
        }
    }

    // The Binder tab's logo row: the preview and Remove when one is
    // pending, "None" when not. The pending logo is what Save stores;
    // Cancel forgets it like any other edit.
    _syncPreferenceLogoRow() {
        const src = this._prefsPendingLogo || '';
        const show = (id, v) => { const el = document.getElementById(id); if (el) el.style.display = v ? '' : 'none'; };
        const prev = document.getElementById('pref-binder-logo-preview');
        if (prev && prev.getAttribute('src') !== src) prev.src = src;
        show('pref-binder-logo-preview', !!src);
        show('pref-binder-logo-remove', !!src);
        show('pref-binder-logo-none', !src);
    }

    _sayPreferenceLogoStatus(msg) {
        const el = document.getElementById('pref-binder-logo-status');
        if (el) { el.textContent = msg || ''; el.style.display = msg ? '' : 'none'; }
    }

    setupPreferences() {
        this.renderPreferencePatternButtons('pref-data-flow-pattern-grid', 'pref-data-flow-pattern-btn');
        this.renderPreferencePatternButtons('pref-power-flow-pattern-grid', 'pref-power-flow-pattern-btn');
        this._fillPreferenceCatalogs();
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

        // The strip: one section up at a time.
        if (modal) {
            modal.querySelectorAll('.pm-tabstrip .view-tab').forEach(t => {
                t.addEventListener('click', () => this.showPreferencesTab(t.dataset.key));
            });
        }

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
                // the binder logo changed: the decoded copy is stale
                this._binderLogoImage = null;
                sendClientLog('preferences_saved', {
                    projectName: this.project ? this.project.name : null,
                    layers: this.project && this.project.layers ? this.project.layers.length : 0,
                    reset: !!this._prefsResetPending,
                    appliesToCurrentProject: !!(this.project && this.project.name === 'Untitled Project' && this.project.layers && this.project.layers.length === 1)
                });
                this._prefsResetPending = false;
                // Preferences are defaults for future/new projects.
                // Only apply to the current project when it is the startup default untitled project.
                this.applyPreferencesToDefaultLayerIfMatch(false);
                this.saveClientSideProperties();
                // v0.8.8.x: font change is project-wide and affects every
                // on-canvas label, repaint so the new font shows immediately.
                if (window.canvasRenderer) window.canvasRenderer.render();
                modal.style.display = 'none';
            });
        }
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                this._prefsResetPending = false;
                modal.style.display = 'none';
            });
        }
        // Reset Defaults asks first. Yes puts every field on every tab
        // back to its shipped value - in the dialog only: Save writes them,
        // Cancel discards the reset like any other edit.
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                if (!window.confirm('Put every preference back to its default?')) return;
                const defaults = this.getPreferencesDefaults();
                this._prefsPendingLogo = '';
                this.fillPreferencesUI(defaults);
                this._prefsResetPending = true;
                sendClientLog('preferences_reset', {
                    projectName: this.project ? this.project.name : null,
                    layers: this.project && this.project.layers ? this.project.layers.length : 0
                });
            });
        }
        if (modal) {
            modal.addEventListener('mousedown', (e) => {
                prefsBackdropDown = (e.target === modal);
            });
            modal.addEventListener('click', (e) => {
                if (e.target === modal && prefsBackdropDown) {
                    this._prefsResetPending = false;
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
        // The binder logo: a PNG / JPEG read and downscaled the way the
        // export dialog reads one (app-binder), held until Save.
        const logo = document.getElementById('pref-binder-logo');
        if (logo) {
            logo.addEventListener('change', async () => {
                const file = logo.files && logo.files[0];
                logo.value = '';
                if (!file || typeof this.readBinderLogoDataUrl !== 'function') return;
                const r = await this.readBinderLogoDataUrl(file);
                if (r.error) { this._sayPreferenceLogoStatus(r.error); return; }
                this._sayPreferenceLogoStatus('');
                this._prefsPendingLogo = r.dataUrl;
                this._syncPreferenceLogoRow();
            });
        }
        const logoRemove = document.getElementById('pref-binder-logo-remove');
        if (logoRemove) {
            logoRemove.addEventListener('click', () => {
                this._prefsPendingLogo = '';
                this._sayPreferenceLogoStatus('');
                this._syncPreferenceLogoRow();
            });
        }
        syncVoltageCustom();
        syncAmperageCustom();
    }

    openPreferencesModal() {
        const prefs = this.getPreferences();
        this._prefsResetPending = false;
        this._prefsPendingLogo = (typeof this.getBinderLogo === 'function') ? this.getBinderLogo() : (prefs.binderLogo || '');
        this._sayPreferenceLogoStatus('');
        this._fillPreferenceCatalogs();
        this.fillPreferencesUI(prefs);
        // Hydrate the Fonts picker, then pull in the machine's installed fonts
        // (refreshes the picker again when they arrive).
        this._loadSystemFonts();
        this.showPreferencesTab(this._prefsTab || 'wall');
        const modal = document.getElementById('preferences-modal');
        if (modal) modal.style.display = 'block';
    }

    // Every field on every tab from one preferences object - the stored
    // set on open, the shipped set after a Reset Defaults.
    fillPreferencesUI(prefs) {
        const setVal = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.value = value == null ? '' : value;
        };
        const setChecked = (id, on) => {
            const el = document.getElementById(id);
            if (el) el.checked = !!on;
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
        setVal('pref-screen-name-color', prefs.screenNameColor);
        setVal('pref-cabinet-id-color', prefs.cabinetIdColor);
        setVal('pref-data-line-color', prefs.dataLineColor);
        setVal('pref-data-arrow-color', prefs.dataArrowColor);
        setVal('pref-data-primary-color', prefs.dataPrimaryColor);
        setVal('pref-data-primary-text-color', prefs.dataPrimaryTextColor);
        setVal('pref-data-backup-color', prefs.dataBackupColor);
        setVal('pref-data-backup-text-color', prefs.dataBackupTextColor);
        setVal('pref-power-line-color', prefs.powerLineColor);
        setVal('pref-power-arrow-color', prefs.powerArrowColor);
        setVal('pref-power-label-bg-color', prefs.powerLabelBgColor);
        setVal('pref-power-label-text-color', prefs.powerLabelTextColor);
        const circuitColors = this.getPreferenceCircuitColorList(prefs);
        this._circuitColorPrefIds().forEach((id, i) => setVal(id, circuitColors[i]));
        this._refreshFontPrefsUI(prefs.font || 'Arial');
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
        setChecked('pref-low-latency', prefs.lowLatency);
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
        // Distros & multis
        setVal('pref-distro-rating', prefs.distroRatingA);
        setVal('pref-distro-voltage', String(prefs.distroVoltage));
        setVal('pref-distro-phase', Number(prefs.distroPhase) === 1 ? '1' : '3');
        setVal('pref-multi-type', prefs.multiType);
        setVal('pref-breakout-type', prefs.breakoutType);
        setChecked('pref-splitters-enabled', prefs.splittersEnabled);
        // Binder
        setVal('pref-binder-sheet', prefs.binderSheet || 'tabloid');
        setVal('pref-binder-screen-order', prefs.binderScreenOrder || 'alpha');
        setChecked('pref-binder-printer', prefs.binderPalette === 'printer');
        setChecked('pref-binder-colour', prefs.binderPalette !== 'printer');
        const maps = prefs.binderMaps === 'power' || prefs.binderMaps === 'data' ? prefs.binderMaps : 'both';
        setChecked('pref-binder-side-power', maps === 'power');
        setChecked('pref-binder-side-data', maps === 'data');
        setChecked('pref-binder-side-both', maps === 'both');
        setChecked('pref-binder-cover', prefs.binderCover !== false);
        setChecked('pref-binder-pull', prefs.binderPull !== false);
        setChecked('pref-binder-hardware', prefs.binderHardware !== false);
        setChecked('pref-binder-wiring', prefs.binderWiring !== false);
        setChecked('pref-binder-title-block', prefs.binderTitleBlock !== false);
        setVal('pref-binder-designer', prefs.binderDesigner);
        setVal('pref-binder-pm-name', prefs.binderPmName);
        setVal('pref-binder-pm-phone', prefs.binderPmPhone);
        setVal('pref-binder-pm-email', prefs.binderPmEmail);
        setVal('pref-binder-drafter', prefs.binderDrafter);
        this._syncPreferenceLogoRow();
        // Pull sheet & cables
        setVal('pref-pull-engineer', prefs.engineerName);
        setVal('pref-pull-rev', prefs.pullRev);
        setVal('pref-pull-power-jump-name', prefs.powerJumpName);
        setVal('pref-pull-power-jump-length', prefs.powerJumpLength);
        setVal('pref-pull-data-jump-name', prefs.dataJumpName);
        setVal('pref-pull-data-jump-length', prefs.dataJumpLength);
        setVal('pref-snake-home-run-length', prefs.snakeHomeRunFt);
        setVal('pref-loose-port-cable-length', prefs.loosePortCableFt);
        setVal('pref-power-cable-length', prefs.powerCableFt);
    }

    readPreferencesFromUI() {
        const defaults = this.getPreferencesDefaults();
        const readNum = (id, fallback) => {
            const el = document.getElementById(id);
            if (!el) return fallback;
            const val = parseFloat(el.value);
            return Number.isFinite(val) && val > 0 ? val : fallback;
        };
        // A length that may be left blank on purpose: blank is null.
        const readOptNum = (id, fallback) => {
            const el = document.getElementById(id);
            if (!el) return fallback;
            if (String(el.value).trim() === '') return null;
            const val = parseFloat(el.value);
            return Number.isFinite(val) && val > 0 ? val : fallback;
        };
        const readStr = (id, fallback) => {
            const el = document.getElementById(id);
            return el && el.value ? el.value : fallback;
        };
        // Free text that may be blank on purpose (a name nobody has typed).
        // Read with the dialog CLOSED (a save from elsewhere carrying the
        // set through), a field nobody filled means the stored value, not
        // a blank - the engineer typed into the export dialog survives.
        const modal = document.getElementById('preferences-modal');
        const dialogOpen = !!modal && getComputedStyle(modal).display !== 'none';
        const readText = (id, fallback) => {
            const el = document.getElementById(id);
            if (!el || !dialogOpen) return fallback;
            return String(el.value).trim();
        };
        const readBool = (id, fallback) => {
            const el = document.getElementById(id);
            return el ? !!el.checked : fallback;
        };
        // A colour picker: stored the way the layer stores it, as
        // upper-case #RRGGBB (a picker hands back lower case).
        const readColor = (id, fallback) => {
            const el = document.getElementById(id);
            return el && el.value ? this.normalizeHexColor(el.value, fallback) : fallback;
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
        const stored = this.getPreferences();
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
            screenNameColor: readColor('pref-screen-name-color', defaults.screenNameColor),
            cabinetIdColor: readColor('pref-cabinet-id-color', defaults.cabinetIdColor),
            dataLineColor: readColor('pref-data-line-color', defaults.dataLineColor),
            dataArrowColor: readColor('pref-data-arrow-color', defaults.dataArrowColor),
            dataPrimaryColor: readColor('pref-data-primary-color', defaults.dataPrimaryColor),
            dataPrimaryTextColor: readColor('pref-data-primary-text-color', defaults.dataPrimaryTextColor),
            dataBackupColor: readColor('pref-data-backup-color', defaults.dataBackupColor),
            dataBackupTextColor: readColor('pref-data-backup-text-color', defaults.dataBackupTextColor),
            powerLineColor: readColor('pref-power-line-color', defaults.powerLineColor),
            powerArrowColor: readColor('pref-power-arrow-color', defaults.powerArrowColor),
            powerLabelBgColor: readColor('pref-power-label-bg-color', defaults.powerLabelBgColor),
            powerLabelTextColor: readColor('pref-power-label-text-color', defaults.powerLabelTextColor),
            powerCircuitColors: this._circuitColorPrefIds().map((id, i) => readColor(id, defaults.powerCircuitColors[i])),
            flowPattern: prefDataPatternActive ? (prefDataPatternActive.getAttribute('data-pattern') || defaults.flowPattern) : defaults.flowPattern,
            powerFlowPattern: prefPowerPatternActive ? (prefPowerPatternActive.getAttribute('data-pattern') || defaults.powerFlowPattern) : defaults.powerFlowPattern,
            dataLineWidth: readNum('pref-data-line-width', defaults.dataLineWidth),
            powerLineWidth: readNum('pref-power-line-width', defaults.powerLineWidth),
            processorType: readStr('pref-processor-type', defaults.processorType),
            lowLatency: readBool('pref-low-latency', defaults.lowLatency),
            bitDepth: readNum('pref-bit-depth', defaults.bitDepth),
            frameRate: readNum('pref-frame-rate', defaults.frameRate),
            powerVoltage: Number.isFinite(voltageVal) && voltageVal > 0 ? voltageVal : defaults.powerVoltage,
            powerAmperage: Number.isFinite(amperageVal) && amperageVal > 0 ? amperageVal : defaults.powerAmperage,
            powerWatts: readNum('pref-power-watts', defaults.powerWatts),
            canvasGap: readNum('pref-canvas-gap', defaults.canvasGap),
            font: readStr('pref-font', defaults.font),
            // Distros & multis
            distroRatingA: readNum('pref-distro-rating', defaults.distroRatingA),
            distroVoltage: readNum('pref-distro-voltage', defaults.distroVoltage),
            distroPhase: readNum('pref-distro-phase', defaults.distroPhase) === 1 ? 1 : 3,
            multiType: readStr('pref-multi-type', defaults.multiType),
            breakoutType: readStr('pref-breakout-type', defaults.breakoutType),
            splittersEnabled: readBool('pref-splitters-enabled', defaults.splittersEnabled),
            // Binder
            binderSheet: readStr('pref-binder-sheet', defaults.binderSheet),
            binderScreenOrder: readStr('pref-binder-screen-order', defaults.binderScreenOrder),
            binderPalette: readBool('pref-binder-printer', false) ? 'printer' : 'colour',
            binderMaps: readBool('pref-binder-side-power', false) ? 'power'
                : readBool('pref-binder-side-data', false) ? 'data' : 'both',
            binderCover: readBool('pref-binder-cover', defaults.binderCover),
            binderPull: readBool('pref-binder-pull', defaults.binderPull),
            binderHardware: readBool('pref-binder-hardware', defaults.binderHardware),
            binderWiring: readBool('pref-binder-wiring', defaults.binderWiring),
            binderTitleBlock: readBool('pref-binder-title-block', defaults.binderTitleBlock),
            binderDesigner: readText('pref-binder-designer', stored.binderDesigner != null ? stored.binderDesigner : defaults.binderDesigner),
            binderPmName: readText('pref-binder-pm-name', stored.binderPmName != null ? stored.binderPmName : defaults.binderPmName),
            binderPmPhone: readText('pref-binder-pm-phone', stored.binderPmPhone != null ? stored.binderPmPhone : defaults.binderPmPhone),
            binderPmEmail: readText('pref-binder-pm-email', stored.binderPmEmail != null ? stored.binderPmEmail : defaults.binderPmEmail),
            binderDrafter: readText('pref-binder-drafter', stored.binderDrafter != null ? stored.binderDrafter : defaults.binderDrafter),
            // the logo chosen in the dialog, else the one stored (the
            // dialog opens with it pending, so Remove clears it on Save)
            binderLogo: this._prefsPendingLogo != null ? this._prefsPendingLogo : (stored.binderLogo || defaults.binderLogo),
            // Pull sheet & cables
            engineerName: readText('pref-pull-engineer', stored.engineerName != null ? stored.engineerName : defaults.engineerName),
            pullRev: readStr('pref-pull-rev', defaults.pullRev),
            powerJumpName: readStr('pref-pull-power-jump-name', defaults.powerJumpName),
            powerJumpLength: readNum('pref-pull-power-jump-length', defaults.powerJumpLength),
            dataJumpName: readStr('pref-pull-data-jump-name', defaults.dataJumpName),
            dataJumpLength: readNum('pref-pull-data-jump-length', defaults.dataJumpLength),
            snakeHomeRunFt: dialogOpen ? readOptNum('pref-snake-home-run-length', defaults.snakeHomeRunFt)
                : (stored.snakeHomeRunFt != null ? stored.snakeHomeRunFt : defaults.snakeHomeRunFt),
            loosePortCableFt: readNum('pref-loose-port-cable-length', defaults.loosePortCableFt),
            powerCableFt: readNum('pref-power-cable-length', defaults.powerCableFt),
        };
    }

    // v0.8.8.x: web-safe font stack offered in the picker, plus user-added
    // custom fonts from preferences. Any font name works as a CSS font-family.
    _webSafeFonts() {
        return ['Arial', 'Helvetica', 'Verdana', 'Tahoma', 'Trebuchet MS',
            'Georgia', 'Times New Roman', 'Courier New', 'Impact', 'Monaco',
            'system-ui'];
    }
    // Fetch the list of fonts installed on the machine running the app (once).
    // The server enumerates them; the browser can render any of them in canvas.
    _loadSystemFonts() {
        if (this._systemFontsLoaded) return Promise.resolve(this._systemFonts || []);
        if (this._systemFontsPromise) return this._systemFontsPromise;
        this._systemFontsPromise = fetch('/api/system-fonts')
            .then(r => r.json())
            .then(d => {
                this._systemFonts = Array.isArray(d.fonts) ? d.fonts : [];
                this._systemFontsLoaded = true;
                // If the Preferences modal is open, refresh the picker so the
                // installed fonts appear without the user reopening it.
                const modal = document.getElementById('preferences-modal');
                if (modal && modal.style.display !== 'none') {
                    const sel = document.getElementById('pref-font');
                    this._refreshFontPrefsUI(sel ? sel.value : undefined);
                }
                return this._systemFonts;
            })
            .catch(() => { this._systemFonts = []; this._systemFontsLoaded = true; return []; });
        return this._systemFontsPromise;
    }
    // Active canvas-text font. Reads from prefs.font (one project-wide value).
    getProjectFont() {
        const prefs = this.getPreferences() || {};
        return prefs.font || 'Arial';
    }

    // Grouped options for the Preferences font picker: a few recommended
    // quick-picks, then every font installed on this machine.
    _fontOptionGroups() {
        const seen = new Set();
        const dedupe = (arr) => {
            const out = [];
            (arr || []).forEach(f => {
                const name = (f || '').trim();
                if (!name || seen.has(name.toLowerCase())) return;
                seen.add(name.toLowerCase()); out.push(name);
            });
            return out;
        };
        const web = dedupe(this._webSafeFonts());
        const system = dedupe(Array.isArray(this._systemFonts) ? this._systemFonts : []);
        return [
            { label: 'Recommended', fonts: web },
            { label: 'Installed on this computer', fonts: system },
        ].filter(g => g.fonts.length);
    }

    _refreshFontPrefsUI(selectedFont) {
        const sel = document.getElementById('pref-font');
        if (sel) {
            sel.innerHTML = '';
            const groups = this._fontOptionGroups();
            const opts = [];
            const want = selectedFont || sel.value || 'Arial';
            // If the saved font isn't in any group yet (e.g. installed fonts
            // still loading), surface it at the top so the value sticks.
            if (want && !groups.some(g => g.fonts.some(f => f.toLowerCase() === want.toLowerCase()))) {
                const o = document.createElement('option');
                o.value = want; o.textContent = want;
                o.style.fontFamily = `"${want}", sans-serif`;
                sel.appendChild(o); opts.push(want);
            }
            groups.forEach(g => {
                const og = document.createElement('optgroup');
                og.label = g.fonts.length > 30 ? `${g.label} (${g.fonts.length})` : g.label;
                g.fonts.forEach(name => {
                    const o = document.createElement('option');
                    o.value = name; o.textContent = name;
                    o.style.fontFamily = `"${name}", sans-serif`;
                    og.appendChild(o); opts.push(name);
                });
                sel.appendChild(og);
            });
            if (opts.some(o => o.toLowerCase() === want.toLowerCase())) sel.value = want;
        }
    }
}

for (const k of Object.getOwnPropertyNames(_Preferences.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Preferences.prototype, k));
    }
}
