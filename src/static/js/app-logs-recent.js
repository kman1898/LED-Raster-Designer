// app-logs-recent: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The most the copies kept in Recent Files may take together, in
// characters (about 3 MB of localStorage, which counts UTF-16), so other
// writes always have room (saveRecentFiles).
const RECENT_COPY_BUDGET = 1500000;

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
                ? `Start of range, included: this many ${word} ago. Pick a unit next to it, or Date… to type an absolute date. Blank = no start bound.`
                : `End of range, included: this many ${word} ago. Same units as From. Blank = now.`;
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
                statusEl.textContent = `${bad.join(' and ')} unrecognized, so the filter is not applied`;
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
        // Fallback: a temporary textarea and execCommand. Also taken when
        // the clipboard API refuses - the Mac app's web view rejects
        // writeText now and then (the owner's log, 2026-09-25, showed an
        // unhandled rejection and a Copy that needed a second click).
        const viaTextarea = () => {
            const ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy'); } catch (e) { /* ignore */ }
            document.body.removeChild(ta);
            this._flashCopyButton();
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text)
                .then(() => this._flashCopyButton(), viaTextarea);
        } else {
            viaTextarea();
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
    //
    // The list lives in this browser's localStorage (per machine). Since
    // 1.6.0 an entry made where the file's path is known (the host's own
    // Save and Open dialogs) keeps only the path, the show's name, its
    // screen count and when it was last used, and opening it reads the
    // FILE again (openProjectFromPath): the show on disk, as last saved
    // on any machine. Before that, every entry held a whole copy of the
    // show, and the copy went stale: a full localStorage (about 5 MB on
    // the Mac) made the update throw after the file was written, a show
    // saved on the other machine opened as this machine's copy, two files
    // of one name shared one entry, and a cancelled save still updated it.
    //
    // An entry whose path is not known (a browser download, or a remote
    // client's save, or an entry from before 1.6.0) still keeps its copy,
    // and opening it says so. Entries are keyed by path, else by name.

    getRecentFiles() {
        try {
            const list = JSON.parse(localStorage.getItem('ledRasterRecentFiles') || '[]');
            return Array.isArray(list) ? list.filter(e => e && (e.path || e.name)) : [];
        } catch (e) {
            return [];
        }
    }

    // Write the list. Never throws: a full localStorage drops the oldest
    // stored copies (path entries cost almost nothing) and tries again.
    // The kept copies together stay under RECENT_COPY_BUDGET characters
    // (the newest copy is always kept), so Recent Files can no longer fill
    // localStorage on its own. Returns whether the list was written.
    saveRecentFiles(files) {
        const list = this._withinCopyBudget(Array.isArray(files) ? files.slice() : []);
        let dropped = 0;
        for (;;) {
            try {
                localStorage.setItem('ledRasterRecentFiles', JSON.stringify(list));
                if (dropped) sendClientLog('recent_files_quota_trimmed', { dropped, kept: list.length });
                return true;
            } catch (e) {
                const quota = e && (e.name === 'QuotaExceededError'
                    || e.name === 'NS_ERROR_DOM_QUOTA_REACHED' || e.code === 22 || e.code === 1014);
                let oldest = -1;
                if (quota) {
                    for (let i = list.length - 1; i >= 0; i--) {
                        if (list[i] && list[i].data) { oldest = i; break; }
                    }
                }
                if (oldest < 0) {
                    sendClientLog('recent_files_write_failed', {
                        name: e && e.name, message: e && e.message, entries: list.length, dropped
                    });
                    return false;
                }
                list.splice(oldest, 1);
                dropped += 1;
            }
        }
    }

    // The list with the oldest kept copies dropped until the copies fit
    // the budget; path entries are never dropped here.
    _withinCopyBudget(list) {
        let used = 0, first = true;
        return list.filter(e => {
            if (!e || !e.data) return true;
            let size = 0;
            try { size = JSON.stringify(e.data).length; } catch (_) { return false; }
            if (!first && used + size > RECENT_COPY_BUDGET) return false;
            first = false;
            used += size;
            return true;
        });
    }

    // Make room in localStorage for another write: drop the oldest kept
    // copy from Recent Files. True when one went.
    pruneRecentCopies() {
        const list = this.getRecentFiles();
        for (let i = list.length - 1; i >= 0; i--) {
            if (!list[i] || !list[i].data) continue;
            const name = list[i].name;
            list.splice(i, 1);
            try {
                localStorage.setItem('ledRasterRecentFiles', JSON.stringify(list));
            } catch (e) {
                // Still too big to write back: take the whole list out.
                try { localStorage.removeItem('ledRasterRecentFiles'); } catch (_) { return false; }
                sendClientLog('recent_files_cleared_for_space', { entries: list.length + 1 });
                return true;
            }
            sendClientLog('recent_files_copy_dropped_for_space', { name });
            try { this.updateRecentFilesMenu(); } catch (_) { /* the list is still written */ }
            return true;
        }
        return false;
    }

    // A path as a key: one spelling per file (Windows paths and drive
    // letters are case-blind, and take either slash).
    _recentPathKey(path) {
        const p = String(path || '').replace(/\\/g, '/');
        return /^[a-z]:\//i.test(p) || p.startsWith('//') ? p.toLowerCase() : p;
    }

    recentFileKey(entry) {
        if (!entry) return '';
        return entry.path ? 'path:' + this._recentPathKey(entry.path) : 'name:' + (entry.name || '');
    }

    _recentScreenCount(projectData) {
        const layers = projectData && Array.isArray(projectData.layers) ? projectData.layers : [];
        return layers.filter(l => l && (l.type || 'screen') === 'screen').length;
    }

    // List the show at the top of Recent Files: by its path when the
    // file's path is known (no copy of the show is kept), else as a copy
    // under its name. Never throws, so a save or an open never fails on
    // its account.
    addToRecentFiles(projectData, opts = {}) {
        try {
            if (!projectData || !projectData.name) return false;
            const path = opts.path || null;
            const now = Date.now();
            const entry = path
                ? { name: projectData.name, path, timestamp: now,
                    screenCount: this._recentScreenCount(projectData) }
                : { name: projectData.name, timestamp: now, savedAt: now,
                    screenCount: this._recentScreenCount(projectData),
                    data: JSON.parse(JSON.stringify(projectData)) };
            const key = this.recentFileKey(entry);
            // The same file goes; so does a kept copy under the same name,
            // which this listing supersedes (an older copy of the same show
            // is what reopened stale).
            const rest = this.getRecentFiles().filter(f => this.recentFileKey(f) !== key
                && !(!f.path && f.name === entry.name));
            rest.unshift(entry);
            const ok = this.saveRecentFiles(rest.slice(0, 20));
            this.updateRecentFilesMenu();
            return ok;
        } catch (e) {
            sendClientLog('recent_files_add_failed', { message: e && e.message });
            return false;
        }
    }

    // A reopened entry moves to the top as it is (a kept copy is not
    // re-copied, so its date stays the date of the copy).
    touchRecentFile(key) {
        try {
            const list = this.getRecentFiles();
            const i = list.findIndex(f => this.recentFileKey(f) === key);
            if (i < 0) return false;
            const [entry] = list.splice(i, 1);
            entry.timestamp = Date.now();
            list.unshift(entry);
            const ok = this.saveRecentFiles(list);
            this.updateRecentFilesMenu();
            return ok;
        } catch (e) {
            sendClientLog('recent_files_touch_failed', { message: e && e.message });
            return false;
        }
    }

    removeRecentFile(key) {
        try {
            const list = this.getRecentFiles().filter(f => this.recentFileKey(f) !== key);
            const ok = this.saveRecentFiles(list);
            this.updateRecentFilesMenu();
            return ok;
        } catch (e) {
            return false;
        }
    }

    // What a row says: the file's name when the path is known, else the
    // show's name; under it the date and the screen count.
    recentFileLabel(entry) {
        if (entry && entry.path) {
            const base = String(entry.path).split(/[\\/]/).pop() || entry.path;
            return base.replace(/\.json$/i, '');
        }
        return (entry && entry.name) || 'Untitled';
    }

    // The labels of a whole list: two files of one name (two folders)
    // each say their folder too, "Show A (Tour)" and "Show A (Backup)".
    recentFileLabels(list) {
        const labels = (list || []).map(e => this.recentFileLabel(e));
        const counts = {};
        labels.forEach(l => { counts[l] = (counts[l] || 0) + 1; });
        return labels.map((l, i) => {
            const e = list[i];
            if (counts[l] < 2 || !e || !e.path) return l;
            const parts = String(e.path).split(/[\\/]/).filter(Boolean);
            return parts.length >= 2 ? `${l} (${parts[parts.length - 2]})` : l;
        });
    }

    recentFileDetail(entry) {
        const date = new Date(entry.timestamp);
        const dateStr = isNaN(date.getTime()) ? ''
            : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        let n = entry.screenCount;
        if (typeof n !== 'number') {
            n = entry.data ? this._recentScreenCount(entry.data) : (entry.layerCount || 0);
        }
        const screens = `${n} ${n === 1 ? 'screen' : 'screens'}`;
        return dateStr ? `${dateStr} · ${screens}` : screens;
    }

    updateRecentFilesMenu() {
        // The start page shows the same list (app-start-page.js).
        if (typeof this.renderStartPageRecent === 'function') this.renderStartPageRecent();
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
        const labels = this.recentFileLabels(recent);
        recent.forEach((file, idx) => {
            const item = document.createElement('div');
            item.className = 'menu-option';
            item.setAttribute('data-action', `recent-file-${idx}`);
            if (file.path) item.title = file.path;
            item.innerHTML = `<div class="recent-file-item"><span class="recent-file-name">${this.escapeHtml(labels[idx])}</span><span class="recent-file-date">${this.escapeHtml(this.recentFileDetail(file))}</span></div>`;
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

    // The one escapeHtml on the prototype (a second, in app-presets.js, was
    // silently overwritten by this one). Escapes quotes too, so it is safe
    // inside an attribute value as well as in text.
    escapeHtml(s) {
        if (s == null) return '';
        return String(s).replace(/[&<>"']/g, ch => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
        ));
    }

    // Open entry `idx`. An entry with a path reads the file from disk;
    // one without opens the copy it kept and says so. Both open through
    // _openProjectData, File > Open's own path. Resolves true when the
    // show opened.
    async loadRecentFile(idx) {
        const recent = this.getRecentFiles();
        if (idx < 0 || idx >= recent.length) return false;
        const file = recent[idx];
        if (file && file.path) {
            sendClientLog('recent_file_open', { path: file.path });
            return this.openProjectFromPath(file.path, { source: 'recent' });
        }
        if (!file || !file.data) {
            alert('Recent file data is unavailable.');
            return false;
        }
        const when = new Date(file.savedAt || file.timestamp);
        const whenStr = isNaN(when.getTime()) ? 'an earlier session'
            : when.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
        sendClientLog('recent_file_open_copy', { name: file.name, savedAt: file.savedAt || file.timestamp || null });
        const opened = await this._openProjectData(JSON.parse(JSON.stringify(file.data)),
            { source: 'recent', recentKey: this.recentFileKey(file) });
        if (opened && typeof this._toast === 'function') {
            this._toast(`This is the copy of ${file.name} kept in Recent Files from ${whenStr}, not the file itself. Use File > Open to open the file.`, false, 9000);
        }
        return opened;
    }

    // A listed file that is no longer on disk: say so, and offer to take
    // it off the list. Never opens anything in its place. Resolves true
    // when the entry was removed.
    recentFileMissing(path) {
        const key = this.recentFileKey({ path });
        const listed = this.getRecentFiles().some(f => this.recentFileKey(f) === key);
        const name = this.recentFileLabel({ path });
        const modal = document.createElement('div');
        modal.id = 'recent-missing-modal';
        modal.className = 'modal';
        modal.style.display = 'block';
        modal.innerHTML = `<div class="modal-content recent-missing-content">
            <h2>File not found</h2>
            <p class="recent-missing-text"></p>
            <div class="recent-missing-path"></div>
            <div class="recent-missing-buttons"></div>
        </div>`;
        modal.querySelector('.recent-missing-text').textContent =
            `${name} is no longer where it was saved. It may have been moved, renamed or deleted.`
            + (listed ? ' Remove it from Recent Files?' : '');
        modal.querySelector('.recent-missing-path').textContent = path;
        const buttons = modal.querySelector('.recent-missing-buttons');
        return new Promise(resolve => {
            const done = (remove) => {
                document.removeEventListener('keydown', onKey, true);
                modal.remove();
                if (remove) this.removeRecentFile(key);
                sendClientLog('recent_file_missing_answered', { path, removed: !!remove });
                resolve(!!remove);
            };
            const onKey = (e) => {
                if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(false); }
            };
            const button = (label, primary, remove) => {
                const b = document.createElement('button');
                b.className = primary ? 'btn btn-primary' : 'btn';
                b.textContent = label;
                b.addEventListener('click', () => done(remove));
                buttons.appendChild(b);
                return b;
            };
            if (listed) {
                button('Keep in list', false, false);
                button('Remove', true, true).id = 'recent-missing-remove';
            } else {
                button('OK', true, false);
            }
            document.addEventListener('keydown', onKey, true);
            document.body.appendChild(modal);
        });
    }

    // ── End Recent Files ─────────────────────────────────────────
}

for (const k of Object.getOwnPropertyNames(_LogsRecent.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_LogsRecent.prototype, k));
    }
}
