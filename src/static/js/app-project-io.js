// app-project-io: saving and loading the project as a file for
// LEDRasterApp - saveProject, saveProjectToFile, loadProjectFromFile,
// resetApplicationState, and the normalizers a loaded project passes
// through (missing layer defaults, power flow pattern, Armor port
// mapping).
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _ProjectIo {
    // The build this page is: what a saved project is stamped with as
    // `app_version` (the server stamps the same on every POST /api/project
    // and on a new project; a load never stamps, so a file saved before
    // the stamp existed still carries none - see app-naming
    // normalizePowerCircuitColors for what reads it). /api/version is the
    // authority (VERSION.txt on the local server, the About dialog's
    // source); it is fetched once, and until it answers the baked page
    // title stands in - the same fallback whatsnew.js uses. Synchronous,
    // so a save never waits on the network for its stamp.
    appVersion() {
        if (this._appVersion) return this._appVersion;
        if (!this._appVersionFetch) {
            this._appVersionFetch = fetch('/api/version')
                .then(r => r.json())
                .then(d => {
                    if (d && d.version) {
                        this._appVersion = String(d.version);
                        this._showBuildVersion(this._appVersion);
                    }
                })
                .catch(() => {});
        }
        const m = /v(\d+\.\d+\.\d+(?:-[\w.]+)?)/.exec(document.title || '');
        return m ? m[1] : '';
    }

    // The page ships with the release number baked into its title and
    // header. A beta build's server answers "1.5.3-beta.1", and both say so,
    // so nobody mistakes a beta for the release.
    _showBuildVersion(version) {
        if (!version || typeof document === 'undefined') return;
        const label = 'v' + version;
        document.title = document.title.replace(/v\d+\.\d+\.\d+(?:-[\w.]+)?/, label);
        const el = document.getElementById('app-version-label');
        if (el) el.textContent = label;
    }

    // The project as the file on disk holds it: this build's version
    // stamped on, then pretty-printed. saveProjectToFile writes exactly
    // this, so a round trip through File > Open reads the stamp back.
    serializeProjectForFile(project = this.project) {
        project.app_version = this.appVersion();
        return JSON.stringify(this._projectWithOpenRedraw(project), null, 2);
    }

    // `project` as a file holds it: with the circuit redraw still open
    // written down beside it, for the show to end as it opens
    // (app-run-overrides _powerRedrawRecord). Never written onto the project
    // itself.
    _projectWithOpenRedraw(project) {
        const open = project === this.project && typeof this._powerRedrawRecord === 'function'
            ? this._powerRedrawRecord() : null;
        return open ? { ...project, openPowerRedraw: open } : project;
    }

    saveProject() {
        this.project.app_version = this.appVersion();
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
        // An edit still waiting on its debounced history entry lands first:
        // that entry is where the multi numbers it held are written onto
        // the distros (app-naming _commitMultiNumbers), and the file must
        // carry them.
        if (typeof this._flushPendingSaveState === 'function') this._flushPendingSaveState();
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
        const result = await this.saveBlobWithPicker(
            () => {
                const projectData = this.serializeProjectForFile(project);
                return new Blob([projectData], { type: 'application/json' });
            },
            `${this.project.name}.json`,
            'application/json',
            { save: true }
        );
        // Recent Files lists the show only once its file is written: a
        // cancelled or failed save leaves the list as it was. The path,
        // when the host's dialog chose it, is what the entry keeps
        // (addToRecentFiles, which never throws).
        if (!result || !result.saved) return result;
        this.markProjectClean();
        this.addToRecentFiles(this._projectWithOpenRedraw(project), { path: result.path || null });
        document.getElementById('status-message').textContent = 'Project saved to file';
        setTimeout(() => {
            document.getElementById('status-message').textContent = 'Ready';
        }, 2000);
        return result;
    }

    // ── Unsaved changes (QA round 3, 2026-11-03) ──
    //
    // New, Open and a Recent file each replace the project, and opening a
    // show from Recent dropped unsaved work without a word. All of them
    // now ask first, in the app's own dialog: Save, Don't Save, Cancel.
    //
    // "Unsaved" is read off the undo history: the entry in force when the
    // project was last saved to a file, opened, made new or loaded with
    // the page (resetHistory 'Initial State') is marked, and any other
    // entry in force means an edit since. Undo back to the mark reads as
    // saved again. The pristine startup project never asks.
    //
    // Automated browsers (navigator.webdriver) are not asked unless a test
    // sets window.__lrdAskUnsaved = true, the rule the start page, the
    // guide and the startup picker keep: a test that opens one show after
    // another would otherwise stop at the question.
    //
    // A reload starts a new history, so the answer is also kept on the
    // server (routes_project.py, POST /api/project/unsaved) whenever it
    // changes, and the page load reads it back (loadProject): a show
    // reloaded with unsaved edits has no saved entry in its new history
    // (_unsavedCarried below), and reads unsaved until it is saved.
    markProjectClean() {
        if (this._unsavedCarried === true) {
            // The load's own reset, over edits made before the reload.
            this._unsavedCarried = false;
            this._cleanHistoryEntry = null;
        } else {
            this._cleanHistoryEntry = Array.isArray(this.history)
                ? (this.history[this.historyIndex] || null) : null;
        }
        this._noteUnsavedState();
    }

    _unsavedNow() {
        if (!this.project) return false;
        if (typeof this._isPristineStartupProject === 'function' && this._isPristineStartupProject()) return false;
        if (!Array.isArray(this.history) || this.historyIndex < 0) return false;
        return this.history[this.historyIndex] !== this._cleanHistoryEntry;
    }

    projectHasUnsavedChanges() {
        if (typeof this._flushPendingSaveState === 'function') this._flushPendingSaveState();
        return this._unsavedNow();
    }

    // Tell the server when the answer changed (history steps, undo, redo,
    // a save, an open, a new project, the page going away). Nothing is
    // said before the page's first load has read the server's answer: a
    // step taken then would overwrite it with the boot's empty history.
    // The posts go one at a time, each saying the answer as it stands
    // when its turn comes, so two quick changes (a reset's step and its
    // mark) can never land in the wrong order. Leaving the page says it
    // at once (sendBeacon) when it differs from the last one sent.
    _noteUnsavedState({ beacon = false } = {}) {
        if (!this._initialLoadComplete) return;
        if (beacon) {
            const unsaved = this._unsavedNow();
            if (unsaved === this._serverUnsaved || !navigator.sendBeacon) return;
            this._serverUnsaved = unsaved;
            navigator.sendBeacon('/api/project/unsaved',
                new Blob([JSON.stringify({ unsaved })], { type: 'application/json' }));
            return;
        }
        if (this._unsavedPostQueued) return;
        this._unsavedPostQueued = true;
        this._unsavedPost = (this._unsavedPost || Promise.resolve()).then(() => {
            this._unsavedPostQueued = false;
            const unsaved = this._unsavedNow();
            if (unsaved === this._serverUnsaved) return null;
            this._serverUnsaved = unsaved;
            return fetch('/api/project/unsaved', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ unsaved }),
            }).then(res => {
                if (!res.ok) throw new Error(`answered ${res.status}`);
            });
        }).catch(error => {
            // Not known to the server: the next change says it again.
            this._serverUnsaved = undefined;
            sendClientLog('project_unsaved_post_failed', { error: String(error && error.message || error) });
        });
    }

    // Resolves true when the project may be replaced: nothing unsaved,
    // Don't Save, or Save and the file was written. Cancel, Esc, or a Save
    // whose dialog was cancelled resolve false and nothing changes.
    // `what` finishes the question: 'open' or 'new'.
    async confirmUnsavedChanges(what) {
        if (typeof navigator !== 'undefined' && navigator.webdriver
                && !(typeof window !== 'undefined' && window.__lrdAskUnsaved === true)) return true;
        if (!this.projectHasUnsavedChanges()) return true;
        const name = (this.project && this.project.name) || 'this project';
        const doing = what === 'new' ? 'starting a new project' : 'opening another show';
        sendClientLog('unsaved_changes_asked', { what: what || null });
        const answer = await this.appAsk({
            id: 'unsaved-changes-modal',
            title: 'Save changes?',
            message: `Save the changes to ${name} before ${doing}? If you don't save, your changes are lost.`,
            buttons: [
                { label: 'Save', value: 'save', primary: true },
                { label: "Don't Save", value: 'discard' },
                { label: 'Cancel', value: 'cancel' },
            ],
            cancel: 'cancel',
        });
        sendClientLog('unsaved_changes_answered', { what: what || null, answer });
        if (answer === 'discard') return true;
        if (answer !== 'save') return false;
        const saved = await this.saveProjectToFile();
        return !!(saved && saved.saved);
    }

    // File > New and the toolbar's New: asks about unsaved changes, then
    // makes the new project.
    async requestNewProject() {
        if (!(await this.confirmUnsavedChanges('new'))) return false;
        this.createNewProject();
        return true;
    }

    // File > Open. On the host the OS Open dialog picks the file and the
    // server reads it, so the show's path is known (Recent Files keeps the
    // path and re-reads the file next time). A remote client, or a host
    // whose dialog cannot open, uses the browser's file chooser; the path
    // is not known then, and Recent keeps a copy of the show instead.
    // Either way the show opens through _openProjectData.
    async loadProjectFromFile() {
        if (!(await this.confirmUnsavedChanges('open'))) return false;
        sendClientLog('open_file_dialog_requested');
        // A client already known to be remote goes straight to the
        // browser's chooser, inside the click that asked for it.
        if (this.isLocalConnection() && typeof this.ensureHostCapability === 'function') {
            await this.ensureHostCapability();
        }
        if (this.isLocalConnection()) {
            const picked = await this.nativeSelectOpenPath();
            if (picked.cancelled) {
                sendClientLog('open_file_dialog_cancelled', { how: 'native' });
                return false;
            }
            if (picked.path) return this.openProjectFromPath(picked.path, { source: 'file' });
            sendClientLog('open_file_native_dialog_unavailable', {});
        }
        this._chooseProjectFileInBrowser();
        return true;
    }

    // The browser's own file chooser (the path stays unknown).
    _chooseProjectFileInBrowser() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';
        input.style.display = 'none';
        document.body.appendChild(input);
        input.onchange = (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (event) => {
                    this._openProjectText(event.target.result, { source: 'file' });
                };
                reader.readAsText(file);
            } else {
                sendClientLog('open_file_dialog_cancelled');
            }
            if (input.parentNode) input.parentNode.removeChild(input);
        };
        input.click();
    }

    // Read the show at `path` from disk (the host's read-file route) and
    // open it. A file that is no longer there is said in a dialog, never
    // stood in for by an older copy. Resolves true when the show opened.
    async openProjectFromPath(path, opts = {}) {
        const read = await this.nativeReadFile(path);
        if (read.ok) return this._openProjectText(read.text, { ...opts, path });
        const source = opts.source || 'file';
        if (read.missing) {
            sendClientLog('open_project_path_missing', { path, source });
            await this.recentFileMissing(path);
            return false;
        }
        sendClientLog('open_project_path_error', { path, source, message: read.error });
        this.appAlert(`The show could not be read: ${read.error}`,
            { id: 'open-error-modal', title: 'Could not open', detail: path });
        return false;
    }

    // A project file's text, parsed and opened (_openProjectData).
    _openProjectText(text, opts = {}) {
        let projectData;
        try {
            projectData = JSON.parse(text);
        } catch (error) {
            sendClientLog('load_project_file_error', { message: error.message, source: opts.source || 'file' });
            this.appAlert('This file is not a show the app can open: ' + error.message,
                { id: 'open-error-modal', title: 'Could not open' });
            return Promise.resolve(false);
        }
        return this._openProjectData(projectData, opts);
    }

    // Open a show. File > Open and every Recent Files entry come through
    // here, so a show gets the same migrations and repairs whichever way
    // it came. `opts.source` is 'file' or 'recent'; `opts.path` the file
    // it was read from (Recent keeps it); `opts.recentKey` the Recent
    // entry a stored copy came from. Resolves true once the server holds
    // the show.
    _openProjectData(projectData, opts = {}) {
        const source = opts.source || 'file';
        const recent = source === 'recent';
        try {
            sendClientLog('load_project_file_start', {
                name: projectData.name || 'Unnamed',
                layers: projectData.layers ? projectData.layers.length : 0,
                source, hasPath: !!opts.path
            });
            // An opening show takes the place of the start page and of the
            // startup screen it stood over.
            if (typeof this.closeStartPage === 'function') this.closeStartPage();
            this._startupTargetId = null;
            // Clean-slate reset so stale sidebar values can't leak into new project
            this.resetApplicationState();
            // Until the server holds the opened show, a layer
            // save must not trim it (app-merge-runs.js
            // trimPortsOffWall): the repair runs once, on the
            // server's copy, where the cards can follow.
            this._projectOpening = true;
            // A redraw the file was saved with still open: read off it here
            // so the server and the undo history never hold it, and ended
            // below on the server's copy.
            const leftOpen = projectData.openPowerRedraw || null;
            delete projectData.openPowerRedraw;
            this.project = projectData;
            if (this.project.layers) {
                this.project.layers.forEach(layer => {
                    this.applyMissingLayerDefaults(layer);
                    this.normalizeLoadedPowerFlowPattern(layer);
                });
            }
            // A show saved before US circuits packed to 80%
            // keeps its automatic 2fers and 3fers as saved
            // (app-power keepOlderShowShares). Read off the
            // file's own stamp, so it is asked here, before the
            // stamp below, and again on the server's copy.
            const olderShares = this.olderShowKeepsShares(this.project);
            if (olderShares) this.keepOlderShowShares();
            // A show saved before the column-first Down numbering
            // (1.6.0 beta 4): its card pins and port names move
            // with their cabinets to the new numbers, here, so
            // the PUT below carries them (app-merge-runs.js
            // _followOldStackNumbering).
            const stackNotes = (typeof this.predatesStackNumbering === 'function'
                && this.predatesStackNumbering(this.project))
                ? this._followOldStackNumbering() : [];
            // A show saved before Organized stacked its leftovers,
            // read off the same stamp and followed on the server's
            // copy below.
            const olderLeftovers = typeof this.predatesLeftoverStacks === 'function'
                && this.predatesLeftoverStacks(this.project);
            // A show saved before an unchanged redraw went back to
            // the walk (app-run-overrides dropUnchangedRedrawsOnOpen),
            // read off the same stamp.
            const olderRedraws = typeof this.redrawsPredateRelease === 'function'
                && this.redrawsPredateRelease(this.project);
            // A group with no stored answer (a show saved before
            // grouped walls walked power as one across processor
            // canvases) is decided here, once, before the PUT so the
            // server and the first undo snapshot hold the answer
            // (app-screen-groups decidePowerPerMemberOnOpen).
            if (typeof this.decidePowerPerMemberOnOpen === 'function') {
                this.decidePowerPerMemberOnOpen(this.project);
            }
            // A show saved before the binder's logo was the show's
            // (1.7.0) takes the logo the old preference holds, read
            // off the same stamp (app-binder.js
            // adoptPreferenceBinderLogo), so the PUT below and the
            // first undo snapshot carry it.
            if (typeof this.adoptPreferenceBinderLogo === 'function') {
                this.adoptPreferenceBinderLogo(this.project);
            }
            // The migrations above have run against the file's
            // own stamp; from here the project is this build's.
            // Stamped BEFORE the PUT below, because a load never
            // stamps on the server, and an unstamped server copy
            // re-ran the old-green migration on every page reload
            // - repainting a set chosen since (2026-09-23).
            this.project.app_version = this.appVersion();
            // v0.11.0: fix up Armor layers that carry a Max Capacity
            // flag they were never actually drawn with. Runs before
            // the PUT so the server (and the first undo snapshot)
            // get the corrected mode.
            this.normalizeArmorPortMapping(this.project);
            // An old show's Names value (show-wide, per tab) given to
            // each of its groups, so every wall opens named the way it
            // was (app-core.js migrateGroupNameDisplay; the server does
            // the same on the PUT below).
            this.migrateGroupNameDisplay();

            // v0.8.7.2.1: ONLY trust root-level raster fields for
            // legacy (pre-v0.8, no canvases array) files. Multi-
            // canvas files keep the source-of-truth on each canvas
            // object, and writing the root value into
            // canvasRenderer.rasterWidth would clobber the active
            // canvas's per-canvas raster (the setter routes to
            // either raster_width or show_raster_width depending
            // on the current tab). Bug repro: the file's root
            // raster_width was a mirror of the active canvas's
            // *show* raster (because the user last saved on Show
            // Look), so opening the file overwrote the active
            // canvas's pixel-map raster with its show raster
            // value. syncRasterFromProject below reads from each
            // canvas directly so multi-canvas projects are
            // unaffected by skipping this block.
            const _hasCanvases = Array.isArray(projectData.canvases)
                && projectData.canvases.length > 0;
            if (!_hasCanvases && projectData.raster_width && projectData.raster_height) {
                window.canvasRenderer.rasterWidth = projectData.raster_width;
                window.canvasRenderer.rasterHeight = projectData.raster_height;
                document.getElementById('toolbar-raster-width').value = projectData.raster_width;
                document.getElementById('toolbar-raster-height').value = projectData.raster_height;
                this.saveRasterSize();
            }

            // Show locally right away (even if server sync fails)
            this.updateUI();
            // the canvas the show was saved on (app-canvas-ui)
            this._selectOpeningScreen();
            this.saveClientSideProperties();
            window.canvasRenderer.fitToView();

            const loaded = this.project;
            return this._layerSavesSettled().then(() => fetch('/api/project', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(loaded)
            }))
                .then(res => res.json())
                .then(data => {
                    if (!data || !Array.isArray(data.layers)) {
                        throw new Error('Invalid project data returned from server');
                    }
                    this.project = data;
                    this.dedupeProjectLayers(recent ? 'load_recent_file' : 'load_project_file');
                    if (this.project.layers) {
                        this.project.layers.forEach(layer => {
                            this.applyMissingLayerDefaults(layer);
                            this.normalizeLoadedPowerFlowPattern(layer);
                        });
                    }
                    // the keep worked out again on the copy the
                    // server stored, the one the session edits
                    if (olderShares) this.keepOlderShowShares();
                    // v0.11.0: no-op when the pre-PUT pass already
                    // fixed them; kept so the object that feeds
                    // resetHistory() below is always normalized.
                    this.normalizeArmorPortMapping(this.project);
                    // A show saved with ports drawn on cabinets
                    // a shrink took off the wall is repaired as
                    // it opens: the steps go, a port left with
                    // none goes, and the ports after it close up
                    // (app-merge-runs.js trimPortsOffWall). On
                    // the server's copy, so the cards follow.
                    if (typeof this.trimPortsOffWall === 'function') {
                        this.trimPortsOffWall({ load: true });
                    }
                    // A redraw left open ends the way Esc ends it, each
                    // cable and label with its cabinets, ahead of the
                    // repair below, which has no hold to read them by.
                    if (typeof this.finishRedrawLeftOpen === 'function') {
                        this.finishRedrawLeftOpen(leftOpen);
                    }
                    // A circuit redrawn without a change goes back to
                    // the walk, so the circuits after a shrunk one
                    // slide left (app-run-overrides).
                    if (typeof this.dropUnchangedRedrawsOnOpen === 'function') {
                        const freed = this.dropUnchangedRedrawsOnOpen(olderRedraws);
                        if (freed.notes.length && typeof this._toast === 'function') {
                            this._toast(freed.notes.join(' '), false, 8000);
                        }
                    }
                    // A show saved before Organized stacked its leftovers:
                    // its pins and port names ride their cabinets to the
                    // new numbers, behind the repair above and ahead of
                    // the commit below, which lets go of the pins past the
                    // last port (app-merge-runs.js followOldLeftoverStacks).
                    if (olderLeftovers) stackNotes.push(...this.followOldLeftoverStacks());
                    // A distro with multis in use and no output rows
                    // opens with the rows that cover them: no multi is
                    // ever off its distro's face (app-distro-systems).
                    if (typeof this.fillFacesInUseOnOpen === 'function'
                            && this.fillFacesInUseOnOpen().length) {
                        this._persistDistros();
                    }
                    // Sync the canvas's pixel/show raster backing fields from the
                    // loaded project so Show Look picks up the file's values
                    // (and falls back to the pixel raster when show wasn't saved).
                    this.syncRasterFromProject();
                    this.updateUI();
                    // the canvas the show was saved on (app-canvas-ui)
                    this._selectOpeningScreen();
                    this.saveClientSideProperties();
                    window.canvasRenderer.fitToView();
                    // Push all layers to server so client-side properties
                    // (showDataFlowPortInfo, showPowerCircuitInfo, computed power/capacity)
                    // are synced for every layer, not just the selected one.
                    this.updateLayers(this.project.layers, false, recent ? 'Recent File Load Sync' : 'File Load Sync');
                    this.resetHistory('Initial State');
                    if (stackNotes.length && typeof this._toast === 'function') {
                        this._toast(stackNotes.join(' '), false, 12000);
                    }
                    document.getElementById('status-message').textContent =
                        recent ? 'Project loaded from recent files' : 'Project loaded';
                    setTimeout(() => {
                        document.getElementById('status-message').textContent = 'Ready';
                    }, 2000);
                    sendClientLog('load_project_file_success', {
                        name: this.project.name,
                        layers: this.project.layers ? this.project.layers.length : 0,
                        source, hasPath: !!opts.path
                    });
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
                            layers: this.project.layers ? this.project.layers.length : 0,
                            source
                        });
                        if (typeof this._toast === 'function') {
                            this._toast(
                                'Project upgraded to multi-canvas format (v0.8). Save to keep changes. Older app versions can no longer open this file.',
                                false,
                                10000
                            );
                        }
                    }
                    // Recent Files last, and it never throws: the open
                    // never depends on it. (A full localStorage threw
                    // here once, and the open was logged as failed with
                    // every step after it skipped.) A stored copy reopened
                    // moves to the top as it is; anything else is listed,
                    // by its path when the path is known.
                    if (opts.recentKey) this.touchRecentFile(opts.recentKey);
                    else this.addToRecentFiles(this.project, { path: opts.path || null });
                    return true;
                })
                .catch((err) => {
                    this._projectOpening = false;
                    sendClientLog('load_project_file_error', { message: err.message, source });
                    this.resetHistory('Initial State');
                    document.getElementById('status-message').textContent = 'Project loaded (server sync failed)';
                    setTimeout(() => {
                        document.getElementById('status-message').textContent = 'Ready';
                    }, 2000);
                    return false;
                });
        } catch (error) {
            this._projectOpening = false;
            sendClientLog('load_project_file_error', { message: error.message, source });
            this.appAlert((recent ? 'The recent show did not open: ' : 'The show did not open: ') + error.message,
                { id: 'open-error-modal', title: 'Could not open' });
            return Promise.resolve(false);
        }
    }

    /**
     * Clean-slate reset before loading a new project or creating a new one.
     * Clears selection state, stale client props, and undo history so that
     * sidebar inputs cannot leak old values into the incoming project.
     */
    resetApplicationState() {
        // A redraw is of the show it was opened on. Left standing, it held
        // the same cabinets of the next one.
        this._overrideEditing = null;
        this._powerHeld = null;
        if (typeof this._storeRedrawForReload === 'function') this._storeRedrawForReload(null);
        this.selectedLayerIds = new Set();
        this.currentLayer = null;
        this.lastSelectedLayerId = null;
        this.selectionAnchorLayerId = null;
        localStorage.removeItem('ledRasterClientProps');
        // Another show numbers its hardware from 1 again: card1 there is
        // not card1 here, so no card's or box's cable sheet or fold is
        // carried across (app-dock-cable-sheets.js _forgetHardwareViews).
        if (typeof this._forgetHardwareViews === 'function') {
            this._forgetHardwareViews(null, true);
        }
        // ...nor any distro's: its ids start again at d1 too.
        if (typeof this._forgetDistroViews === 'function') {
            this._forgetDistroViews({ all: true });
        }
        this.resetHistory('Initial State');
        // The project about to be adopted is another show: the multi numbers
        // the outgoing one held (app-naming) must not reach it while it
        // loads. Its own are taken by the resetHistory its load ends with.
        this._multiBaseline = null;
        // The tray's Add a processor picker starts blank in another show: a
        // model left picked from the last one read as gear this show has
        // (QA, 1.6.0).
        const picker = typeof document !== 'undefined'
            && document.getElementById('processor-add-device');
        if (picker) picker.value = '';
    }

    applyMissingLayerDefaults(layer) {
        if (layer.locked === undefined) layer.locked = false;
        // v0.11.0: File > Open and Recent Files come through here, not through
        // loadClientSideProperties, so the brompton-ull migration has to run on
        // this path too or an old file would keep a processor that is no longer
        // offered. Runs before the default below: it sets lowLatency itself.
        this.migrateLowLatencyProcessor(layer);
        if (layer.lowLatency === undefined) layer.lowLatency = false;
        if (layer.powerVoltage === undefined) this.setScreenVoltage(layer, 110);
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
        this.normalizePowerBreakout(layer);   // a screen always carries an eligible breakout (2026-09-22)
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
        // v0.11.0 (step 6): cross-member path entries are NOT transient, so
        // they are deliberately not in the delete list below - they are the
        // user's hand-drawn wiring and a file is where it lives. What a file
        // cannot be trusted about is whether the peer an entry names is still
        // a reachable member of the owner's group, so the entries are
        // VALIDATED here instead of dropped. Every file path runs through
        // applyMissingLayerDefaults (File > Open and Recent Files both), and
        // this.project is already the loaded project by the time the caller
        // loops over its layers, so group membership is visible from here.
        this.sanitizeCrossLayerPaths(layer);
        // Computed/transient fields should never be trusted from file payload
        delete layer._powerError;
        delete layer._powerCircuits;
        // Per-frame render maps for cross-member circuits. A saved file can
        // carry them as `{}` (a Map does not survive JSON), and a stale empty
        // map reads as "this cabinet belongs to no circuit" until the next
        // render rebuilds it.
        delete layer._powerPanelCircuitScopedMap;
        delete layer._powerPanelIndexScopedMap;
        delete layer._powerCircuitOwners;
        delete layer._powerTotalAmps1;
        delete layer._powerTotalAmps3;
        delete layer._powerCircuitsRequired;
        delete layer._capacityError;
        delete layer._autoPortsRequired;
        delete layer._portsRequired;
        delete layer._lowLatencyDerate;
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

    // v0.11.0: NovaStar Armor used to discard portMappingMode entirely -
    // calculatePortAssignments forced Organized on it no matter what the layer
    // said. Projects saved in that window can carry 'max-capacity' on an Armor
    // screen while having been drawn (and printed) as Organized the whole time.
    // Now that Armor honours both modes, opening such a file would silently
    // redraw an already-issued map, so pin those layers back to the mode they
    // really rendered with. LOAD PATHS ONLY: switching a layer to Armor by hand
    // is a deliberate choice, and undo/redo must never re-apply this.
    // Returns the number of layers changed.
    normalizeArmorPortMapping(project) {
        if (!project || !Array.isArray(project.layers)) return 0;
        let changed = 0;
        project.layers.forEach(layer => {
            if (!layer || (layer.type || 'screen') !== 'screen') return;
            // A missing processorType renders as Armor (calculatePortAssignments
            // defaults to it), so those layers were drawn Organized too and get
            // the same treatment.
            if ((layer.processorType || 'novastar-armor') !== 'novastar-armor') return;
            if (layer.portMappingMode !== 'max-capacity') return;
            layer.portMappingMode = 'organized';
            changed++;
        });
        if (changed > 0) {
            sendClientLog('armor_port_mapping_normalized', { layers: changed });
        }
        return changed;
    }
}

for (const k of Object.getOwnPropertyNames(_ProjectIo.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ProjectIo.prototype, k));
    }
}
