// app-logs-recent: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _LogsRecent {
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
        // v0.10.8: a debounced filter fetch must not fire after the close
        if (this._logsFilterTimer) {
            clearTimeout(this._logsFilterTimer);
            this._logsFilterTimer = null;
        }
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
        const sinceUnit = document.getElementById('logs-since-unit');
        const untilUnit = document.getElementById('logs-until-unit');
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
        // Filter inputs: re-fetch through the current window (the bounds are
        // applied server-side now, so a filter change needs a new request).
        // v0.10.8: typing used to filter on every keystroke, so a half-typed
        // "2026" briefly emptied the pane. Debounce the keystroke path;
        // change/blur (and Clear filter) apply immediately.
        const applyFilter = () => this._debouncedLogFilter();
        const applyFilterNow = () => {
            if (this._logsFilterTimer) {
                clearTimeout(this._logsFilterTimer);
                this._logsFilterTimer = null;
            }
            this.refreshLogs(true);
        };
        if (sinceInput) {
            sinceInput.addEventListener('input', applyFilter);
            sinceInput.addEventListener('change', applyFilterNow);
        }
        if (untilInput) {
            untilInput.addEventListener('input', applyFilter);
            untilInput.addEventListener('change', applyFilterNow);
        }
        // Unit dropdowns: switching a unit re-shapes the field (number vs
        // Date… free text) and re-filters immediately - the number in the
        // box means something different now.
        if (sinceUnit) sinceUnit.addEventListener('change', () => {
            this._syncLogFilterFieldMode('logs-since');
            applyFilterNow();
        });
        if (untilUnit) untilUnit.addEventListener('change', () => {
            this._syncLogFilterFieldMode('logs-until');
            applyFilterNow();
        });
        if (filterClearBtn) {
            filterClearBtn.addEventListener('click', () => {
                if (sinceInput) sinceInput.value = '';
                if (untilInput) untilInput.value = '';
                if (sinceUnit) sinceUnit.value = 'min';
                if (untilUnit) untilUnit.value = 'min';
                this._syncLogFilterFieldMode('logs-since');
                this._syncLogFilterFieldMode('logs-until');
                applyFilterNow();
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

    // Parse one filter TEXT into an epoch-ms bound. The UI now feeds this
    // either a composed "<n> <unit>" from the number + unit dropdown, or
    // the raw text of a field in Date… mode; the full grammar stays so
    // both paths (and anything pasted into Date… mode) keep working.
    // Accepts relative
    // ("10 min ago", "2h ago", "30s", "1d ago"), the words now / today /
    // yesterday, and absolute "YYYY-MM-DD[ HH:MM[:SS]]".
    // v0.11.x: a bare number means MINUTES ("1" = 1 min ago). It used to
    // fall through both grammars (relative required a unit, absolute a full
    // date) and flag the field invalid, forcing "1 m" for the most common
    // filter of all. Minutes is the unit the log window is actually read
    // in, and the tradeoff is tiny: a year being typed toward an absolute
    // date ("2026") now transiently reads as ~1.4 days of minutes instead
    // of transiently invalid - benign either way, and the keystroke path is
    // debounced. The first "-" makes it invalid-until-complete as before.
    // `bound` is 'start' or 'end'. v0.10.8: an absolute value is snapped to the
    // precision the user actually typed so BOTH ends of the range are
    // inclusive - "To: 2026-07-25" means through 23:59:59.999 that day, and
    // "To: 2026-07-25 20:14" means through 20:14:59.999. The old code took
    // "20:14" to mean 20:14:00 and then compared exclusively, dropping
    // everything in the minute the user asked for.
    // Returns null for empty/unparseable input.
    parseLogFilterTime(input, bound = 'start') {
        if (!input) return null;
        const trimmed = String(input).trim();
        if (!trimmed) return null;
        const lower = trimmed.toLowerCase();
        const end = bound === 'end';
        // Word forms
        if (lower === 'now') return Date.now();
        if (lower === 'today' || lower === 'yesterday') {
            const d = new Date();
            if (lower === 'yesterday') d.setDate(d.getDate() - 1);
            return end
                ? new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999).getTime()
                : new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0).getTime();
        }
        // Relative: "<n> <unit> ago" or just "<n><unit>" / "<n> <unit>",
        // with the unit optional - a bare number defaults to minutes.
        const relMatch = lower
            .replace(/\s+ago\s*$/, '')  // strip trailing "ago"
            .trim()
            .match(/^(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)?$/);
        if (relMatch) {
            const n = parseFloat(relMatch[1]);
            const unit = relMatch[2] || 'min';
            let ms;
            if (/^s(ec(ond)?s?)?$/.test(unit)) ms = n * 1000;
            else if (/^m(in(ute)?s?)?$/.test(unit)) ms = n * 60 * 1000;
            else if (/^h(r|rs|our|ours)?$/.test(unit)) ms = n * 60 * 60 * 1000;
            else if (/^d(ay|ays)?$/.test(unit)) ms = n * 24 * 60 * 60 * 1000;
            else return null;
            return Date.now() - ms;
        }
        // Absolute. v0.10.8: built field-by-field as LOCAL time instead of
        // handed to Date.parse. The spec reads a bare "2026-07-25" as UTC but
        // "2026-07-25T20:14:16" as local, so a date-only bound was skewed by
        // the UTC offset (4h in EDT) and "To: 2026-07-25" hid the whole day.
        // The regex also refuses partial input ("2026"), which Date.parse
        // happily turned into a valid-but-wrong instant while the user typed.
        const abs = trimmed.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?)?$/);
        if (!abs) return null;
        const y = parseInt(abs[1], 10);
        const mo = parseInt(abs[2], 10);
        const day = parseInt(abs[3], 10);
        const hasTime = abs[4] !== undefined;
        const hasSec = abs[6] !== undefined;
        const h = hasTime ? parseInt(abs[4], 10) : (end ? 23 : 0);
        const mi = hasTime ? parseInt(abs[5], 10) : (end ? 59 : 0);
        const s = hasSec ? parseInt(abs[6], 10) : (end ? 59 : 0);
        const ms = end ? 999 : 0;
        if (mo < 1 || mo > 12 || day < 1 || day > 31) return null;
        if (h > 23 || mi > 59 || s > 59) return null;
        const dt = new Date(y, mo - 1, day, h, mi, s, ms);
        // Reject dates that rolled over ("2026-02-30" would land in March)
        if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== day) return null;
        return dt.getTime();
    }

    // Extract the log line's timestamp in epoch ms. Log lines are JSON with a
    // "timestamp": "YYYY-MM-DD HH:MM:SS" field. Returns null if not parseable.
    parseLogLineTime(line) {
        if (!line) return null;
        // Fast path: pull out the first "timestamp": "..." occurrence. The
        // outer timestamp is always first; details.clientTime is UTC and is
        // deliberately never what this matches.
        const m = line.match(/"timestamp"\s*:\s*"([^"]+)"/);
        if (!m) return null;
        // v0.10.8: built as LOCAL time to match the writer, rather than relying
        // on Date.parse's format-dependent UTC/local behaviour.
        const p = m[1].match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/);
        if (!p) return null;
        return new Date(+p[1], +p[2] - 1, +p[3], +p[4], +p[5], +p[6]).getTime();
    }

    // v0.11.x: the From/To fields are a number plus a unit dropdown
    // (Sec / Min / Hours / Days, default Min) - no typing conventions to
    // learn. The Date… unit swaps the field to free text and hands it to
    // parseLogFilterTime unchanged, so the old grammar (absolute
    // "YYYY-MM-DD[ HH:MM[:SS]]", now / today / yesterday, "2h ago")
    // survives behind an explicit choice instead of being removed.

    _logFilterUnit(inputId) {
        const sel = document.getElementById(inputId + '-unit');
        return (sel && sel.value) || 'min';
    }

    // Read one field (input + unit) into epoch ms. Returns { text, ms };
    // ms is null for blank or unparseable input. The number path composes
    // "<n> <unit>" and reuses parseLogFilterTime, so the dropdown and the
    // Date… text path can never disagree about the arithmetic.
    _readLogFilterField(inputId, bound) {
        const input = document.getElementById(inputId);
        const text = ((input && input.value) || '').trim();
        if (!text) return { text: '', ms: null };
        const unit = this._logFilterUnit(inputId);
        if (unit === 'date') return { text, ms: this.parseLogFilterTime(text, bound) };
        return { text, ms: this.parseLogFilterTime(text + ' ' + unit, bound) };
    }

    // Re-shape a filter input to match its unit: a number box for the time
    // units, the old free-text box for Date…. Placeholder/title follow so
    // the hint always describes what the field currently accepts.
    _syncLogFilterFieldMode(inputId) {
        const input = document.getElementById(inputId);
        if (!input) return;
        const from = inputId === 'logs-since';
        if (this._logFilterUnit(inputId) === 'date') {
            input.type = 'text';
            input.style.width = '160px';
            input.placeholder = 'YYYY-MM-DD HH:MM';
            input.title = from
                ? 'Start of range, included. YYYY-MM-DD, YYYY-MM-DD HH:MM[:SS], today, yesterday, or now. A date with no time starts at 00:00:00. Blank = no start bound.'
                : 'End of range, included. YYYY-MM-DD covers that whole day; HH:MM covers that whole minute. Also today / yesterday / now. Blank = now.';
        } else {
            const word = { s: 'seconds', min: 'minutes', h: 'hours', d: 'days' }[this._logFilterUnit(inputId)] || 'minutes';
            input.type = 'number';
            input.step = 'any';
            input.min = '0';
            input.style.width = '70px';
            input.placeholder = from ? '10' : '5';
            input.title = from
                ? `Start of range, included — this many ${word} ago. Pick a unit next to it, or Date… to type an absolute date. Blank = no start bound.`
                : `End of range, included — this many ${word} ago. Same units as From. Blank = now.`;
        }
    }

    // v0.10.8: single reader for both fields, so the fetch query and the
    // client-side pass can never disagree about the window.
    _logFilterBounds() {
        const since = this._readLogFilterField('logs-since', 'start');
        const until = this._readLogFilterField('logs-until', 'end');
        const bad = [];
        if (since.text && since.ms === null) bad.push('From');
        if (until.text && until.ms === null) bad.push('To');
        return {
            sinceMs: since.ms,
            untilMs: until.ms,
            bad,
            hasText: !!(since.text || until.text),
            valid: bad.length === 0
        };
    }

    _filterLogLines(lines, meta) {
        const statusEl = document.getElementById('logs-filter-status');
        const { sinceMs, untilMs, bad, hasText, valid } = this._logFilterBounds();
        if (!hasText) {
            if (statusEl) { statusEl.style.color = '#888'; statusEl.textContent = ''; }
            return { lines, sinceMs: null, untilMs: null, valid: true };
        }
        if (!valid) {
            // v0.10.8: an unparseable field used to fall open and quietly show
            // the whole unfiltered log behind a vague "invalid" note. Say
            // plainly that no filtering happened.
            if (statusEl) {
                statusEl.style.color = '#f0ad4e';
                statusEl.textContent = `${bad.join(' and ')} unrecognized — filter not applied`;
            }
            return { lines, sinceMs, untilMs, valid: false };
        }
        // Second pass over lines the server already filtered: same bounds and
        // same timestamp parsing, so it normally changes nothing. It exists to
        // catch anything the server could not read and to keep the count right
        // when a response arrives after the fields moved on.
        const filtered = lines.filter(line => {
            const t = this.parseLogLineTime(line);
            if (t === null) return false;  // drop lines without a timestamp
            if (sinceMs !== null && t < sinceMs) return false;
            if (untilMs !== null && t > untilMs) return false;
            return true;
        });
        if (statusEl) {
            statusEl.style.color = '#888';
            // v0.10.8: the server knows how many lines in the WHOLE file match;
            // say so instead of implying the capped page is the whole answer.
            const total = meta && typeof meta.matched_count === 'number'
                ? meta.matched_count
                : filtered.length;
            statusEl.textContent = total > filtered.length
                ? `showing most recent ${filtered.length} of ${total} matching entries`
                : `${filtered.length} matching ${filtered.length === 1 ? 'entry' : 'entries'}`;
        }
        return { lines: filtered, sinceMs, untilMs, valid: true };
    }

    _debouncedLogFilter(delay = 300) {
        if (this._logsFilterTimer) clearTimeout(this._logsFilterTimer);
        this._logsFilterTimer = setTimeout(() => {
            this._logsFilterTimer = null;
            this.refreshLogs(true);
        }, delay);
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
        // v0.10.8: the window goes to the server as epoch ms so the WHOLE log
        // file is searched. Filtering only the fetched tail meant "From: 1d
        // ago" could never reach anything older than the last N lines. Bounds
        // are sent only when every filled-in field parses; a bad field means
        // "not filtering" on both sides.
        const { sinceMs, untilMs, valid } = this._logFilterBounds();
        let url = `/api/logs?lines=${lines}`;
        if (valid) {
            if (sinceMs !== null) url += `&since=${Math.floor(sinceMs)}`;
            if (untilMs !== null) url += `&until=${Math.floor(untilMs)}`;
        }
        fetch(url)
            .then(r => r.json())
            .then(data => this._renderLogs(data, force))
            .catch(err => this._renderLogsError(err));
    }

    _renderLogs(data, force) {
        const pre = document.getElementById('logs-content');
        const meta = document.getElementById('logs-meta');
        if (!pre) return;
        const rawLines = Array.isArray(data.lines) ? data.lines : [];
        const { lines: visibleLines } = this._filterLogLines(rawLines, data);
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
            // v0.11.0: same Armor Port Mapping fix-up as loadProjectFromFile.
            // Runs before the PUT so the server (and the first undo snapshot)
            // get the corrected mode.
            this.normalizeArmorPortMapping(this.project);
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
                    // v0.11.0: no-op when the pre-PUT pass already fixed them;
                    // kept so the object that feeds resetHistory() below is
                    // always normalized.
                    this.normalizeArmorPortMapping(this.project);
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
}

for (const k of Object.getOwnPropertyNames(_LogsRecent.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_LogsRecent.prototype, k));
    }
}
