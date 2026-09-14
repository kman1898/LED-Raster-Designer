// Entry module: assembles LEDRasterApp from its feature modules, then boots.
// Load order matters only in that app-core must come first; the feature
// modules each attach their methods to LEDRasterApp.prototype on import.
import { LEDRasterApp } from './app-core.js';
import './app-presets.js';
import './app-colors.js';
import './app-screen-info.js';
import './app-export-io.js';
import './app-port-routing.js';
import './app-preferences.js';
import './app-menubar.js';
import './app-logs-recent.js';
import './app-power.js';
import './app-context-menu.js';
import './app-distros.js';
import './app-phase-balance.js';
import './app-naming.js';
import './app-pixel-select.js';
import './app-cross-layer-paths.js';
import './app-run-overrides.js';
import './app-custom-runs.js';
import './app-layers-panel.js';
import './app-pull-list.js';
import './app-beaches.js';
import './app-pull-sheet-editor.js';
import './app-binder.js';
import './app-binder-wiring.js';
import './app-canvas-ui.js';
import './app-screen-groups.js';
import './app-processors.js';
import './app-port-assignment.js';
import './app-dock.js';
import './app-dock-cable-sheets.js';
import './app-dock-sweep.js';
import './app-dock-drag.js';
import './app-dock-menus.js';
import './app-history.js';
import { registerGlobalClientLogging, sendClientLog } from './helpers.js';

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
