// Entry module: assembles LEDRasterApp from its feature modules, then boots.
// Load order matters only in that app-core must come first; the feature
// modules each attach their methods to LEDRasterApp.prototype on import.
import { LEDRasterApp } from './app-core.js';
import './app-presets.js';
import './app-colors.js';
import './app-screen-info.js';
import './app-export-io.js';
import './app-logs-recent.js';
import './app-power.js';
import './app-pull-list.js';
import './app-canvas-ui.js';
import './app-screen-groups.js';
import './app-processors.js';
import './app-port-assignment.js';
import './app-dock.js';
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
