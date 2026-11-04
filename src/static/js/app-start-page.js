// app-start-page: the start page a launch opens on (1.6.0) - New project,
// Open file…, and the Recent Files list - for LEDRasterApp.
//
// Owner, 2026-11-03: on launch the app first asks what to do. New opens
// the panel picker (app-presets.js, startup mode); Cancel there comes back
// here. Open file… is File > Open. A recent file opens as File > Recent
// Files would (the same list, app-logs-recent.js). X or Esc closes the
// page and leaves an empty project, as the startup picker's Cancel does.
// File > New skips the page and goes straight to the picker.
//
// Every launch shows it (QA round 3), over a project a guide's recovery
// brought back too. With no startup screen under it, New is File > New
// (it asks about unsaved changes first) and X just closes the page.
//
// The launch opens it through maybeOpenStartupPicker('launch'), so it
// waits for the first-run guide and the What's New window like the picker
// did. It stands over the launch's startup screen (_startupTargetId) until
// a choice is made; a show that opens takes its place (_openProjectData
// closes it). Automated browsers never see it unless a test sets
// window.__lrdStartPage = true before the page loads.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _StartPage {
    // Is the launch's start page wanted in this browser? Real browsers,
    // always; an automated one only when the test asks.
    _startPageAllowed() {
        if (typeof navigator !== 'undefined' && navigator.webdriver) {
            return typeof window !== 'undefined' && window.__lrdStartPage === true;
        }
        return true;
    }

    startPageOpen() {
        const m = document.getElementById('start-page-modal');
        return !!m && m.style.display === 'block';
    }

    _buildStartPage() {
        let modal = document.getElementById('start-page-modal');
        if (modal) return modal;
        modal = document.createElement('div');
        modal.id = 'start-page-modal';
        modal.className = 'modal';
        modal.style.display = 'none';
        modal.innerHTML = `<div class="modal-content start-page-content" role="dialog" aria-modal="true" aria-labelledby="start-page-title">
            <h2 id="start-page-title">LED Raster Designer</h2>
            <button type="button" id="start-page-close" class="start-page-close" title="Close" aria-label="Close">&times;</button>
            <div class="start-page-actions">
                <button type="button" id="start-page-new" class="btn btn-primary">New project</button>
                <button type="button" id="start-page-open" class="btn">Open file…</button>
            </div>
            <div class="start-page-heading">Recent</div>
            <div id="start-page-recent" class="start-page-recent"></div>
        </div>`;
        document.body.appendChild(modal);
        modal.querySelector('#start-page-new').addEventListener('click', () => this.startPageNew());
        modal.querySelector('#start-page-open').addEventListener('click', () => this.startPageOpenFile());
        modal.querySelector('#start-page-close').addEventListener('click', () => this.dismissStartPage());
        // Esc closes it, unless a dialog of its own is up over it (the
        // missing-file question answers its own Esc).
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape' || !this.startPageOpen()) return;
            if (document.getElementById('recent-missing-modal')) return;
            // A guide step showing the page: Esc is the guide's (it
            // closes the page with the rest of its transients).
            const q = window.QuickStart;
            try { if (q && q.state && q.state().visible) return; } catch (_) { /* no guide */ }
            e.preventDefault();
            e.stopPropagation();
            this.dismissStartPage();
        }, true);
        return modal;
    }

    // The Recent list, the same one File > Recent Files shows.
    renderStartPageRecent() {
        const host = document.getElementById('start-page-recent');
        if (!host) return;
        host.innerHTML = '';
        const recent = typeof this.getRecentFiles === 'function' ? this.getRecentFiles() : [];
        if (recent.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'start-page-empty';
            empty.textContent = 'No recent files';
            host.appendChild(empty);
            return;
        }
        const labels = this.recentFileLabels(recent);
        recent.forEach((file, idx) => {
            const row = document.createElement('button');
            row.type = 'button';
            row.className = 'start-page-recent-row';
            row.dataset.index = String(idx);
            if (file.path) row.title = file.path;
            const name = document.createElement('span');
            name.className = 'start-page-recent-name';
            name.textContent = labels[idx];
            const detail = document.createElement('span');
            detail.className = 'start-page-recent-detail';
            detail.textContent = this.recentFileDetail(file);
            row.appendChild(name);
            row.appendChild(detail);
            row.addEventListener('click', () => {
                sendClientLog('start_page_recent', { index: idx, hasPath: !!file.path });
                // The page stays until the show opens (_openProjectData
                // closes it); a file no longer there is asked about over it.
                this.loadRecentFile(idx);
            });
            host.appendChild(row);
        });
    }

    openStartPage(reason) {
        const modal = this._buildStartPage();
        this.renderStartPageRecent();
        modal.style.display = 'block';
        sendClientLog('start_page_open', {
            reason: reason || null,
            recent: typeof this.getRecentFiles === 'function' ? this.getRecentFiles().length : 0
        });
        const first = modal.querySelector('#start-page-new');
        if (first) first.focus();
    }

    // Hide it, nothing else. True when it was up.
    closeStartPage() {
        const modal = document.getElementById('start-page-modal');
        if (!modal || modal.style.display !== 'block') return false;
        modal.style.display = 'none';
        return true;
    }

    // New project: the panel picker for the startup screen; its Cancel
    // comes back here (cancelPresetPicker).
    startPageNew() {
        this.closeStartPage();
        sendClientLog('start_page_new', { layerId: this._startupTargetId == null ? null : this._startupTargetId });
        if (this._startupTargetId == null) {
            // Over a project the launch brought back: File > New.
            this.requestNewProject();
            return;
        }
        if (!this._startupScreenStands(this._startupTargetId)) {
            // The project moved on under the page: nothing to pick for.
            sendClientLog('startup_picker_stale', { action: 'start_page_new', layerId: this._startupTargetId == null ? null : this._startupTargetId });
            return;
        }
        this.openPresetPicker({ mode: 'startup', fromStartPage: true });
    }

    // Open file…: File > Open. The page stays up behind the dialog, so a
    // cancel lands back on it.
    startPageOpenFile() {
        sendClientLog('start_page_open_file', {});
        this.loadProjectFromFile();
    }

    // X or Esc: an empty project, the startup picker's Cancel result. Over
    // a project the launch brought back, the page just closes.
    dismissStartPage() {
        if (!this.closeStartPage()) return;
        sendClientLog('start_page_closed', { kept: this._startupTargetId == null });
        if (this._startupTargetId == null) return;
        this._startEmpty();
    }
}

for (const k of Object.getOwnPropertyNames(_StartPage.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_StartPage.prototype, k));
    }
}
