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
//
// A reload is not a launch (owner, 2026-11-04). Reloading the page while
// a show is open brought the start page up over it and dropped the person
// back on Pixel Map. Now a reload brings back just the tab they were on
// (selection, canvas, zoom and pan start fresh as before) and shows the
// start page only if it was on screen, no choice made yet, when the page
// went: the page itself, the panel picker its New opened, or a launch's
// page still waiting behind the first-run guide or What's New. A picker
// File > New opened comes back as that picker. A project the page's X (or
// the picker's Cancel) left empty stays empty. Left as it is, it is still
// the pristine project: the server puts a startup screen in it on the page
// load (app.index), and the reload takes it out again. Worked on after
// that (renamed, a canvas or a beach added, a screen added and undone), it
// is no longer pristine and the server leaves it empty by itself.
//
// How a reload is told from a launch: the launcher opens the app in a new
// browser tab every launch (launcher_settings open_url: `open -a`,
// webbrowser.open), so the place is kept in sessionStorage, which a
// reload keeps and a new tab never has. It is written as the page goes
// (pagehide) and read once at boot, and it counts only when the browser
// calls the load a reload (or Back/Forward to the page) and the server is
// the same one that wrote it (a tab reloaded after the app was quit and
// started again is a launch). Storage that cannot be read or written, a
// navigation of any other kind, or no record at all is a launch.
//
// A launch is once per server run (owner, 2026-11-09): "It should only do
// that on the app originally opening. Treated like a live service once it
// is already running." Another tab, another browser on this computer, or
// a tablet at the computer's address joins the show as it stands, with no
// start page, no launch picker and no first-run guide. The server keeps
// the rule (routes_project.py _claim_launch): each page asks once at boot
// (_claimLaunchPage), the first page on the host to ask is the launch
// page, and the question stays open until somebody answers it (the X, a
// pick or Cancel in the startup picker, File > New, a show opened:
// _settleLaunch). The launch page's own reload hands its claim on (its id
// rides in the reload record), so the start page up at a reload still
// comes back; one closed with it up gives it to the next page on the host.
// Automated browsers ask only when a test sets __lrdStartPage or
// __lrdStartupPicker.
import { LEDRasterApp, PAGE_CLIENT_ID } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The per-tab record a reload reads back (_saveReloadPlace).
const RELOAD_PLACE_KEY = 'lrdReloadPlace';

class _StartPage {
    // Is the launch's start page wanted in this browser? Real browsers,
    // always; an automated one only when the test asks.
    _startPageAllowed() {
        if (typeof navigator !== 'undefined' && navigator.webdriver) {
            return typeof window !== 'undefined' && window.__lrdStartPage === true;
        }
        return true;
    }

    // ── One launch per server run (owner, 2026-11-09) ──

    // This page's id, made once: the server knows the launch page by it,
    // and its socket carries it (app-core.js connectWebSocket).
    // The one id every request of the page carries too (app-core
    // PAGE_CLIENT_ID, the X-LRD-Page header), so the server knows a page's
    // requests and its socket for the same page (a guide's lock lasts as
    // long as its page's socket, routes_project guide_page).
    launchPageId() {
        if (!this._launchPageId) this._launchPageId = PAGE_CLIENT_ID;
        return this._launchPageId;
    }

    // Boot: is this page the launch? Asked once, beside the project's
    // read; resolves true for the launch page. This page's reload record
    // names the page before it, so the launch page's reload keeps the
    // claim. An automated browser asks only when a test wants the launch
    // UI; any answer the server cannot give is a join.
    _claimLaunchPage() {
        if (this._launchClaim) return this._launchClaim;
        const automated = typeof navigator !== 'undefined' && navigator.webdriver
            && window.__lrdStartPage !== true && window.__lrdStartupPicker !== true;
        if (automated) {
            this._launchRole = 'join';
            this._launchClaim = Promise.resolve(false);
            return this._launchClaim;
        }
        const place = this._reloadPlace;
        const prior = place ? [place.page, place.before].filter(p => typeof p === 'string' && p) : [];
        this._launchPrior = prior.length ? prior[0] : null;
        this._launchClaim = fetch('/api/launch/claim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ page: this.launchPageId(), prior }),
        }).then(res => (res.ok ? res.json() : null)).then((answer) => {
            const start = !!(answer && answer.startPage === true);
            this._launchRole = start ? 'launch' : 'join';
            sendClientLog('launch_claim', { startPage: start, why: answer && answer.why ? answer.why : null, reload: prior.length > 0 });
            return start;
        }).catch((error) => {
            this._launchRole = 'join';
            sendClientLog('launch_claim_failed', { error: String(error && error.message || error) });
            return false;
        });
        return this._launchClaim;
    }

    // The launch's question is answered: nobody gets the start page again
    // this run, and a page load adds no startup screen (app.index). Sent
    // once per page; resolves either way.
    _settleLaunch(why) {
        if (this._launchSettleSent) return this._launchSettleSent;
        let sent;
        try {
            sent = fetch('/api/launch/settle', {
                method: 'POST',
                keepalive: true,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ why: why || null }),
            }).then(() => true, () => false);
        } catch (_) { sent = Promise.resolve(false); }
        this._launchSettleSent = sent;
        return sent;
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
        // A guide's step shows the page too; only the launch's counts
        // toward a reload (_launchChoicePending).
        this._startPageReason = reason || null;
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
        this._startPageReason = null;
        return true;
    }

    // New project: the panel picker for the startup screen; its Cancel
    // comes back here (cancelPresetPicker).
    async startPageNew() {
        sendClientLog('start_page_new', { layerId: this._startupTargetId == null ? null : this._startupTargetId });
        if (this._startupTargetId == null) {
            // Over a project the launch brought back: File > New. The page
            // stays up behind "Save changes?", so Cancel lands back on it,
            // as Open file… and a Recent file do (1.6.0 QA, beta.6: it
            // closed first, and Cancel left no start page at all). The new
            // project's picker closes it (maybeOpenStartupPicker('new')).
            const made = await this.requestNewProject();
            if (made) this.closeStartPage();
            return made;
        }
        this.closeStartPage();
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
        const guide = this._startPageReason === 'guide';
        if (!this.closeStartPage()) return;
        sendClientLog('start_page_closed', { kept: this._startupTargetId == null });
        if (this._startupTargetId == null) {
            // The launch's answer: keep what is here. (_startEmpty answers
            // for the other case.)
            if (!guide) this._settleLaunch('start_page_closed');
            return;
        }
        this._startEmpty();
    }

    // ── A reload keeps the place (owner, 2026-11-04) ──

    // How the browser says this page was loaded: 'reload', 'back_forward',
    // 'navigate', or null when it does not say.
    _navigationType() {
        try {
            const entry = performance.getEntriesByType('navigation')[0];
            if (entry && entry.type) return entry.type;
        } catch (_) { /* no Navigation Timing */ }
        try {
            const t = performance.navigation ? performance.navigation.type : null;
            if (t === 1) return 'reload';
            if (t === 2) return 'back_forward';
            if (t === 0) return 'navigate';
        } catch (_) { /* nothing to ask */ }
        return null;
    }

    // Is a guide holding the window? Its tab and its project are not the
    // person's (the guide's own recovery puts theirs back after a reload).
    _guideHoldsWindow() {
        const q = typeof window !== 'undefined' ? window.QuickStart : null;
        try {
            const st = q && typeof q.state === 'function' ? q.state() : null;
            return !!(st && (st.visible || st.running));
        } catch (_) { return false; }
    }

    // The choice a launch or File > New asked for and nobody has made yet:
    // 'launch' (the start page, or the picker its New opened, or a launch
    // still waiting to show it), 'new' (File > New's picker), or null.
    _launchChoicePending() {
        if (this._startupWaiting === 'launch' || this._startupWaiting === 'new') return this._startupWaiting;
        if (this.startPageOpen() && this._startPageReason !== 'guide') return 'launch';
        const picker = document.getElementById('preset-picker-modal');
        if (picker && picker.style.display && picker.style.display !== 'none'
                && this._pickerMode === 'startup') {
            return this._pickerFromStartPage === true ? 'launch' : 'new';
        }
        return null;
    }

    // Boot: read (and drop) the record this tab's last page left, and keep
    // it when this load is a reload of that same server's page. Called once
    // the server session is known, before the project loads. Anything
    // unreadable is a launch.
    _takeReloadPlace() {
        let raw = null;
        try {
            raw = window.sessionStorage.getItem(RELOAD_PLACE_KEY);
            window.sessionStorage.removeItem(RELOAD_PLACE_KEY);
        } catch (_) { raw = null; }
        this._reloadPlace = null;
        this._reloadPlaceTaken = true;
        if (!raw) return null;
        let place = null;
        try { place = JSON.parse(raw); } catch (_) { place = null; }
        if (!place || typeof place !== 'object') return null;
        const nav = this._navigationType();
        if (nav !== null && nav !== 'reload' && nav !== 'back_forward') return null;
        if (!this._serverSessionId || place.server !== this._serverSessionId) return null;
        this._reloadPlace = {
            tab: typeof place.tab === 'string' ? place.tab : null,
            pending: place.pending === 'launch' || place.pending === 'new' ? place.pending : null,
            empty: place.empty === true,
            page: typeof place.page === 'string' ? place.page : null,
            before: typeof place.before === 'string' ? place.before : null,
        };
        return this._reloadPlace;
    }

    // pagehide: write down where this page is, for a reload to read back.
    _saveReloadPlace() {
        if (!this._reloadPlaceTaken) return;   // the old record is still unread
        let place;
        if (!this._reloadPlaceSettled) {
            // Gone before the boot finished: what the boot was about to do.
            // A page that joined the live show was about to do nothing.
            place = this._reloadPlace
                ? Object.assign({}, this._reloadPlace)
                : { tab: null, pending: this._launchRole === 'join' ? null : 'launch', empty: false };
        } else {
            const guide = this._guideHoldsWindow();
            const active = document.querySelector('#view-tabs .view-tab.active[data-mode]');
            const p = this.project;
            place = {
                tab: guide || !active ? null : active.getAttribute('data-mode'),
                pending: this._launchChoicePending(),
                empty: !guide && !!p && p.is_pristine === true
                    && Array.isArray(p.layers) && p.layers.length === 0,
            };
        }
        place.server = this._serverSessionId || null;
        // Who this page was: the launch page's reload keeps its claim
        // (_claimLaunchPage). Gone before the server answered, the claim
        // may still be the page's before it, so that one is named too.
        place.page = this.launchPageId();
        place.before = this._launchRole === undefined && this._launchPrior ? this._launchPrior : null;
        try {
            window.sessionStorage.setItem(RELOAD_PLACE_KEY, JSON.stringify(place));
        } catch (_) { /* no storage: the next load is a launch */ }
    }

    // The tab a reload came back to, when this project still has it.
    _restoreReloadTab(mode) {
        if (!mode) return false;
        const tab = [...document.querySelectorAll('#view-tabs .view-tab[data-mode]')]
            .find(t => t.getAttribute('data-mode') === mode);
        if (!tab || tab.classList.contains('active')) return false;
        if (tab.disabled || tab.hidden || tab.classList.contains('view-hidden')) return false;
        const style = window.getComputedStyle(tab);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        tab.click();
        return true;
    }

    // Boot, once the project has loaded: a reload goes back to its tab and
    // shows only the choice that was still open; a launch asks as always
    // (maybeOpenStartupPicker('launch')).
    resumeOrLaunch() {
        const place = this._reloadPlace;
        this._reloadPlace = null;
        this._reloadPlaceSettled = true;
        if (!place) {
            if (typeof this.maybeOpenStartupPicker === 'function') this.maybeOpenStartupPicker('launch');
            return false;
        }
        const tabRestored = this._restoreReloadTab(place.tab);
        sendClientLog('reload_resume', {
            tab: place.tab, tabRestored, pending: place.pending, empty: place.empty,
        });
        if (place.pending) {
            if (typeof this.maybeOpenStartupPicker === 'function') this.maybeOpenStartupPicker(place.pending);
        } else if (place.empty && this._isPristineStartupProject()) {
            // The page load put a startup screen back in the pristine
            // project the page's X left empty: take it out again.
            this._startupTargetId = this.project.layers[0].id;
            this._startEmpty();
        }
        return true;
    }
}

for (const k of Object.getOwnPropertyNames(_StartPage.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_StartPage.prototype, k));
    }
}
