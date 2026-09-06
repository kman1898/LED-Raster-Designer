// app-presets: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog, setupColorPickerWithHex } from './helpers.js';

class _Presets {
    // ── Preset CRUD (server) ──
    fetchPresetList() {
        // Returns list of names (compat).
        return fetch('/api/presets').then(r => r.json()).then(d => d.presets || []);
    }

    fetchPresetEntries() {
        // Returns list of {name, columns, rows, cabinet_width, cabinet_height, panel_width_mm, panel_height_mm}
        return fetch('/api/presets').then(r => r.json()).then(d => d.entries || []);
    }

    formatPresetSublabel(entry) {
        if (!entry) return 'Saved preset';
        const parts = [];
        if (entry.columns != null && entry.rows != null) {
            parts.push(`${entry.columns}×${entry.rows}`);
        }
        if (entry.cabinet_width != null && entry.cabinet_height != null) {
            parts.push(`${entry.cabinet_width}×${entry.cabinet_height}px`);
        }
        if (entry.panel_width_mm != null && entry.panel_height_mm != null) {
            parts.push(`${entry.panel_width_mm}×${entry.panel_height_mm}mm`);
        }
        if (entry.panelWatts != null) {
            parts.push(`${entry.panelWatts}W/panel`);
        }
        return parts.length > 0 ? parts.join(' • ') : 'Saved preset';
    }

    fetchPreset(name) {
        return fetch(`/api/presets/${encodeURIComponent(name)}`).then(r => {
            if (!r.ok) return r.json().then(e => Promise.reject(e));
            return r.json();
        });
    }

    savePresetToServer(name, data) {
        return fetch(`/api/presets/${encodeURIComponent(name)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data })
        }).then(r => r.json().then(body => r.ok ? body : Promise.reject(body)));
    }

    deletePresetOnServer(name) {
        return fetch(`/api/presets/${encodeURIComponent(name)}`, { method: 'DELETE' })
            .then(r => r.json().then(body => r.ok ? body : Promise.reject(body)));
    }

    // ── Add-Layer favorites (per-user, localStorage) ──
    // `favorites` is an array of panel snapshots ({ _mfr, name, width_mm, ... })
    // captured when the user hearted a catalog row. Snapshotting lets us
    // render favorites even before the catalog JSON has loaded.
    // `order` is an array of left-column row IDs ('__default__', 'preset:<name>',
    // 'panel:<mfr>|<name>'); items not in the array fall back to natural order.
    getAddLayerFavorites() {
        try { return JSON.parse(localStorage.getItem('addLayer.favorites') || '[]') || []; }
        catch { return []; }
    }
    setAddLayerFavorites(arr) {
        try { localStorage.setItem('addLayer.favorites', JSON.stringify(arr || [])); } catch {}
    }
    getAddLayerOrder() {
        try { return JSON.parse(localStorage.getItem('addLayer.order') || '[]') || []; }
        catch { return []; }
    }
    setAddLayerOrder(arr) {
        try { localStorage.setItem('addLayer.order', JSON.stringify(arr || [])); } catch {}
    }
    _favoriteKey(mfr, name) { return `${mfr}|${name}`; }
    _isCatalogFavorited(mfr, name) {
        const key = this._favoriteKey(mfr, name);
        return this.getAddLayerFavorites().some(p => this._favoriteKey(p._mfr, p.name) === key);
    }
    _toggleCatalogFavorite(panel) {
        const key = this._favoriteKey(panel._mfr, panel.name);
        const favs = this.getAddLayerFavorites();
        const idx = favs.findIndex(p => this._favoriteKey(p._mfr, p.name) === key);
        if (idx >= 0) {
            favs.splice(idx, 1);
        } else {
            // Snapshot only the fields we need so we don't bloat localStorage.
            favs.push({
                _mfr: panel._mfr, name: panel.name,
                width_mm: panel.width_mm, height_mm: panel.height_mm,
                pixels_w: panel.pixels_w, pixels_h: panel.pixels_h,
                weight_kg: panel.weight_kg, watts_max: panel.watts_max,
                source: panel.source
            });
        }
        this.setAddLayerFavorites(favs);
    }

    // ── Preset Picker Modal (triggered by + Add Screen) ──
    openPresetPicker() {
        const modal = document.getElementById('preset-picker-modal');
        const list = document.getElementById('preset-picker-list');
        if (!modal || !list) return;
        list.innerHTML = '<div style="padding: 12px; color: #888; font-size: 12px;">Loading…</div>';
        modal.style.display = 'block';
        // Selection model: { type: 'preset'|'panel', key }, default preset is always '__default__'
        this._pickerSelection = { type: 'preset', key: '__default__' };
        this._updatePickerSummary();
        this._renderPresetPickerLeftColumn();
        // Load catalog in parallel
        this._loadPanelCatalog();
    }

    _renderPresetPickerLeftColumn() {
        const list = document.getElementById('preset-picker-list');
        if (!list) return;
        list.innerHTML = '<div style="padding: 12px; color: #888; font-size: 12px;">Loading…</div>';
        this.fetchPresetEntries().then(entries => {
            list.innerHTML = '';
            const prefs = this.getPreferences() || {};
            const prefEntry = {
                columns: prefs.columns, rows: prefs.rows,
                cabinet_width: prefs.panelWidth, cabinet_height: prefs.panelHeight,
                panel_width_mm: prefs.panelWidthMM, panel_height_mm: prefs.panelHeightMM,
                panelWatts: prefs.powerWatts
            };
            // Build unified row list. Default is always pinned first.
            const defaultRow = {
                id: '__default__',
                kind: 'default',
                label: 'Default (from Preferences)',
                sublabel: this.formatPresetSublabel(prefEntry),
                pickerKey: '__default__'
            };
            const presetRows = entries.map(entry => ({
                id: `preset:${entry.name}`,
                kind: 'preset',
                label: entry.name,
                sublabel: this.formatPresetSublabel(entry),
                pickerKey: entry.name
            }));
            const favRows = this.getAddLayerFavorites().map(p => ({
                id: `panel:${this._favoriteKey(p._mfr, p.name)}`,
                kind: 'favorite',
                panel: p,
                label: `${(p._mfr || '').replace(/_/g,' ')} ${p.name || ''}`.trim(),
                sublabel: this.formatPresetSublabel({
                    cabinet_width: p.pixels_w, cabinet_height: p.pixels_h,
                    panel_width_mm: p.width_mm, panel_height_mm: p.height_mm,
                    panelWatts: p.watts_max
                }),
                pickerKey: this._favoriteKey(p._mfr, p.name)
            }));
            // Sort by saved order; unknowns appended.
            const order = this.getAddLayerOrder();
            const orderIdx = id => {
                const i = order.indexOf(id);
                return i === -1 ? Number.MAX_SAFE_INTEGER : i;
            };
            const mixed = [...presetRows, ...favRows].sort((a, b) => orderIdx(a.id) - orderIdx(b.id));
            const rows = [defaultRow, ...mixed];

            rows.forEach((row, idx) => {
                const item = document.createElement('div');
                item.className = 'preset-picker-row';
                item.dataset.key = row.pickerKey;
                item.dataset.kind = row.kind;
                item.dataset.id = row.id;
                item.style.cssText = 'padding: 10px 12px; border-radius: 4px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px;';
                // Default + non-default rows get drag enabled (except default, it stays pinned)
                if (row.kind !== 'default') {
                    item.draggable = true;
                    this._wirePresetRowDrag(item);
                }
                if (idx === 0) item.style.background = '#2d4a7a';
                const leftCol = document.createElement('div');
                leftCol.style.cssText = 'flex: 1; min-width: 0; overflow: hidden;';
                leftCol.innerHTML = `<div style="color:#fff; font-size:13px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${this.escapeHtml(row.label)}</div><div style="color:#888; font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${row.sublabel}</div>`;
                item.appendChild(leftCol);
                // Heart on favorite rows (always filled, clicking removes from favorites)
                if (row.kind === 'favorite') {
                    const heartBtn = document.createElement('button');
                    heartBtn.className = 'btn';
                    heartBtn.innerHTML = '♥';
                    heartBtn.title = 'Remove from favorites';
                    heartBtn.style.cssText = 'background: transparent; color: #e25555; font-size: 14px; padding: 2px 8px; border: 1px solid #444;';
                    heartBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        this._toggleCatalogFavorite(row.panel);
                        this._renderPresetPickerLeftColumn();
                        this._renderPanelCatalogList();
                    });
                    item.appendChild(heartBtn);
                }
                if (row.kind === 'preset') {
                    const delBtn = document.createElement('button');
                    delBtn.className = 'btn';
                    delBtn.textContent = '🗑';
                    delBtn.title = `Delete preset "${row.pickerKey}"`;
                    delBtn.style.cssText = 'background: transparent; color: #c55; font-size: 14px; padding: 2px 8px; border: 1px solid #444;';
                    delBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (!confirm(`Delete preset "${row.pickerKey}"?`)) return;
                        this.deletePresetOnServer(row.pickerKey).then(() => {
                            this._renderPresetPickerLeftColumn();
                        }).catch(err => alert('Failed to delete preset: ' + (err && err.error || 'unknown')));
                    });
                    item.appendChild(delBtn);
                }
                item.addEventListener('click', () => {
                    if (row.kind === 'favorite') {
                        this._pickerSelection = { type: 'panel', key: this._favoriteKey(row.panel._mfr, row.panel.name), panel: row.panel, label: row.label };
                    } else {
                        this._pickerSelection = { type: 'preset', key: row.pickerKey, label: row.label };
                    }
                    this._highlightPickerSelection();
                    this._updatePickerSummary();
                });
                list.appendChild(item);
            });
            this._highlightPickerSelection();
        });
    }

    // HTML5 drag-and-drop reorder for the left column. Default row is pinned
    // (not draggable, not a drop target). Order persists in localStorage.
    _wirePresetRowDrag(item) {
        item.addEventListener('dragstart', (e) => {
            this._dragRowId = item.dataset.id;
            item.style.opacity = '0.4';
            try { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', item.dataset.id); } catch {}
        });
        item.addEventListener('dragend', () => {
            item.style.opacity = '';
            this._dragRowId = null;
            document.querySelectorAll('#preset-picker-list .preset-picker-row').forEach(el => {
                el.style.borderTop = '';
                el.style.borderBottom = '';
            });
        });
        item.addEventListener('dragover', (e) => {
            if (!this._dragRowId || this._dragRowId === item.dataset.id) return;
            if (item.dataset.kind === 'default') return;
            e.preventDefault();
            try { e.dataTransfer.dropEffect = 'move'; } catch {}
            const rect = item.getBoundingClientRect();
            const before = (e.clientY - rect.top) < rect.height / 2;
            item.style.borderTop = before ? '2px solid #4A90E2' : '';
            item.style.borderBottom = before ? '' : '2px solid #4A90E2';
        });
        item.addEventListener('dragleave', () => {
            item.style.borderTop = '';
            item.style.borderBottom = '';
        });
        item.addEventListener('drop', (e) => {
            e.preventDefault();
            const draggedId = this._dragRowId;
            const targetId = item.dataset.id;
            if (!draggedId || draggedId === targetId || item.dataset.kind === 'default') return;
            const rect = item.getBoundingClientRect();
            const dropBefore = (e.clientY - rect.top) < rect.height / 2;
            // Build new order from current DOM, excluding default and dragged.
            const ids = Array.from(document.querySelectorAll('#preset-picker-list .preset-picker-row'))
                .map(el => el.dataset.id)
                .filter(id => id && id !== '__default__' && id !== draggedId);
            const insertAt = ids.indexOf(targetId) + (dropBefore ? 0 : 1);
            ids.splice(insertAt, 0, draggedId);
            this.setAddLayerOrder(ids);
            this._renderPresetPickerLeftColumn();
        });
    }

    // ── Panel catalog source-of-truth resolution ──
    // Prefers a cached refresh from GitHub (in localStorage) over the bundled
    // file shipped with this app version. If the user hits Refresh and a
    // newer catalog is fetched, we cache it and every subsequent _loadPanelCatalog
    // call uses the cached copy automatically.
    _getCachedCatalog() {
        try {
            const raw = localStorage.getItem('panelCatalog.cached');
            if (!raw) return null;
            return JSON.parse(raw);
        } catch { return null; }
    }
    _setCachedCatalog(catalog, sha, fetchedAt) {
        try {
            localStorage.setItem('panelCatalog.cached', JSON.stringify(catalog));
            if (sha) localStorage.setItem('panelCatalog.cachedSha', sha);
            if (fetchedAt) localStorage.setItem('panelCatalog.cachedAt', fetchedAt);
        } catch {}
    }
    _getCachedCatalogSha() { return localStorage.getItem('panelCatalog.cachedSha') || ''; }
    _getCachedCatalogAt()  { return localStorage.getItem('panelCatalog.cachedAt') || ''; }

    _ingestCatalog(catalog) {
        this._panelCatalog = catalog || {};
        this._panelCatalogFlat = [];
        Object.keys(this._panelCatalog).forEach(mfr => {
            (this._panelCatalog[mfr] || []).forEach(p => {
                this._panelCatalogFlat.push(Object.assign({ _mfr: mfr, _searchKey: (mfr + ' ' + (p.name || '')).toLowerCase() }, p));
            });
        });
    }

    _loadPanelCatalog() {
        const listEl = document.getElementById('panel-catalog-list');
        const mfrSel = document.getElementById('panel-catalog-mfr');
        const searchEl = document.getElementById('panel-catalog-search');
        const countEl = document.getElementById('panel-catalog-count');
        if (!listEl) return;
        listEl.innerHTML = '<div style="padding: 12px; color: #888; font-size: 12px;">Loading catalog…</div>';
        const finish = () => {
            // Repopulate manufacturer dropdown when source changes (e.g. after refresh).
            if (mfrSel) {
                const cur = mfrSel.value;
                // Clear all but the "All manufacturers" option
                while (mfrSel.options.length > 1) mfrSel.remove(1);
                const mfrs = Object.keys(this._panelCatalog).sort((a, b) => a.localeCompare(b));
                mfrs.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = `${m.replace(/_/g, ' ')} (${this._panelCatalog[m].length})`;
                    mfrSel.appendChild(opt);
                });
                if (cur && Array.from(mfrSel.options).some(o => o.value === cur)) mfrSel.value = cur;
                if (!mfrSel._pickerWired) {
                    mfrSel._pickerWired = true;
                    mfrSel.addEventListener('change', () => this._renderPanelCatalogList());
                }
            }
            if (searchEl && !searchEl._pickerWired) {
                searchEl._pickerWired = true;
                let t;
                searchEl.addEventListener('input', () => {
                    clearTimeout(t);
                    t = setTimeout(() => this._renderPanelCatalogList(), 120);
                });
            }
            if (countEl) {
                const total = Object.values(this._panelCatalog).reduce((s, a) => s + a.length, 0);
                countEl.textContent = `· ${total.toLocaleString()} panels · ${Object.keys(this._panelCatalog).length} mfrs`;
            }
            this._renderPanelCatalogList();
            this._renderCatalogSourceTag();
        };
        if (this._panelCatalog) { finish(); return; }
        // Prefer the cached refreshed catalog if present, else the bundled file.
        const cached = this._getCachedCatalog();
        if (cached) {
            this._ingestCatalog(cached);
            finish();
            return;
        }
        fetch('/static/data/panel_catalog.json').then(r => r.json()).then(data => {
            this._ingestCatalog(data);
            finish();
        }).catch(() => {
            listEl.innerHTML = '<div style="padding: 12px; color: #c55; font-size: 12px;">Failed to load panel catalog.</div>';
        });
    }

    // Background check on app boot, fetches the upstream catalog SHA and
    // stashes the fresh catalog in localStorage if it differs from what the
    // user currently has loaded. Sets `_catalogUpdateAvailable` so the picker
    // can show an "Update available" badge next time it's opened.
    checkPanelCatalogUpdate() {
        // Resolve the user's current effective SHA (cached refresh wins over bundled).
        const cachedSha = this._getCachedCatalogSha();
        const apply = (payload) => {
            if (!payload || !payload.sha) return;
            this._latestCatalogSha = payload.sha;
            this._latestCatalogFetchedAt = payload.fetchedAt || '';
            this._latestCatalogPanelCount = payload.panelCount || 0;
            // Stash the catalog so the user can apply it instantly without
            // another network call when they click the badge.
            if (payload.catalog) this._pendingCatalog = payload.catalog;
            const baseline = cachedSha || (this._bundledCatalogSha || '');
            this._catalogUpdateAvailable = !!baseline && payload.sha !== baseline;
            this._renderCatalogSourceTag();
        };
        // First pull bundled SHA (cheap, no network), then ask the upstream proxy.
        const infoFetch = this._bundledCatalogSha
            ? Promise.resolve({ bundledSha: this._bundledCatalogSha })
            : fetch('/api/panel-catalog/info').then(r => r.json()).then(d => {
                this._bundledCatalogSha = d.bundledSha || '';
                this._bundledCatalogPanelCount = d.panelCount || 0;
                return d;
            }).catch(() => ({}));
        infoFetch.then(() => fetch('/api/panel-catalog/refresh').then(r => r.ok ? r.json() : Promise.reject(r)))
            .then(apply)
            .catch(() => { /* offline / blocked, silently keep current */ });
    }

    // Manual user-triggered refresh from the button in the catalog header.
    refreshPanelCatalogNow(opts = {}) {
        // Re-entrancy guard: if a refresh is already in flight, return that
        // promise instead of starting a parallel one. Spam-clicking the
        // button used to stack 9 fetches behind each other and confuse the
        // UI state.
        if (this._catalogRefreshInFlight) return this._catalogRefreshInFlight;
        const btn = document.getElementById('panel-catalog-refresh-btn');
        if (btn) {
            btn.disabled = true;
            // pointer-events:none belt-and-suspenders the disabled attribute
            // (some bound listeners fire on disabled buttons in webviews).
            btn.style.pointerEvents = 'none';
            btn.style.opacity = '0.6';
            btn.textContent = '↻ Refreshing…';
        }
        // Hard 15s client-side timeout so a hung server can't pin the UI.
        const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        const timeoutId = setTimeout(() => { try { ctrl && ctrl.abort(); } catch {} }, 15000);
        const fetchOpts = ctrl ? { signal: ctrl.signal } : {};
        const p = fetch('/api/panel-catalog/refresh', fetchOpts)
            .then(r => r.ok ? r.json() : r.json().then(b => Promise.reject(b)).catch(() => Promise.reject({status: r.status})))
            .then(payload => {
                if (!payload || !payload.catalog) throw new Error('bad payload');
                this._setCachedCatalog(payload.catalog, payload.sha, payload.fetchedAt);
                this._latestCatalogSha = payload.sha;
                this._latestCatalogFetchedAt = payload.fetchedAt || '';
                this._catalogUpdateAvailable = false;
                this._pendingCatalog = null;
                this._ingestCatalog(payload.catalog);
                this._renderPanelCatalogList();
                this._renderCatalogSourceTag();
                if (!opts.silent) {
                    const count = payload.panelCount || 0;
                    this._toast(`Catalog refreshed, ${count.toLocaleString()} panels`);
                }
            })
            .catch((err) => {
                if (!opts.silent) {
                    const detail = err && err.error ? ` (${err.error})` : '';
                    this._toast(`Couldn’t reach GitHub, keeping current catalog${detail}`, true);
                }
            })
            .finally(() => {
                clearTimeout(timeoutId);
                this._catalogRefreshInFlight = null;
                if (btn) {
                    btn.disabled = false;
                    btn.style.pointerEvents = '';
                    btn.style.opacity = '';
                    btn.textContent = '↻ Refresh';
                }
            });
        this._catalogRefreshInFlight = p;
        return p;
    }

    // Renders the small "source tag" shown in the catalog column header:
    //   - "Bundled (vX.Y.Z)" or "Updated <date>"
    //   - When an update is available, the tag becomes a clickable green pill.
    _renderCatalogSourceTag() {
        const el = document.getElementById('panel-catalog-source-tag');
        if (!el) return;
        const cachedAt = this._getCachedCatalogAt();
        const updateAvail = !!this._catalogUpdateAvailable;
        if (updateAvail) {
            el.style.cssText = 'display:inline-block; cursor:pointer; padding:2px 8px; border-radius:10px; background:#1a5fb4; color:#fff; font-size:10px; font-weight:600; letter-spacing:0.3px;';
            el.textContent = '📦 Update available · click to apply';
            el.title = 'A newer panel catalog is available from GitHub. Click to apply.';
            el.onclick = () => {
                if (this._pendingCatalog) {
                    this._setCachedCatalog(this._pendingCatalog, this._latestCatalogSha, this._latestCatalogFetchedAt);
                    this._ingestCatalog(this._pendingCatalog);
                    this._catalogUpdateAvailable = false;
                    this._pendingCatalog = null;
                    // Re-render dropdown + list with new data
                    this._loadPanelCatalog();
                    this._toast('Catalog updated');
                } else {
                    // Pending data wasn't stashed (boot check failed?), fall back to a fresh refresh
                    this.refreshPanelCatalogNow();
                }
            };
        } else {
            el.style.cssText = 'display:inline-block; padding:2px 0; color:#777; font-size:10px;';
            el.onclick = null;
            if (cachedAt) {
                const d = new Date(cachedAt);
                const when = isNaN(d) ? cachedAt : d.toLocaleDateString();
                el.textContent = `Updated ${when}`;
                el.title = `Catalog last refreshed from GitHub on ${cachedAt}`;
            } else {
                el.textContent = 'Bundled';
                el.title = 'Using the panel catalog bundled with this app version. Click Refresh to pull updates.';
            }
        }
    }

    _toast(msg, isError, durationMs) {
        let host = document.getElementById('app-toast-host');
        if (!host) {
            host = document.createElement('div');
            host.id = 'app-toast-host';
            host.style.cssText = 'position:fixed; bottom:20px; left:50%; transform:translateX(-50%); z-index:11000; display:flex; flex-direction:column; gap:6px; align-items:center;';
            document.body.appendChild(host);
        }
        const t = document.createElement('div');
        t.style.cssText = `padding:10px 16px; border-radius:6px; font-size:13px; color:#fff; background:${isError ? '#a8324b' : '#2d4a7a'}; box-shadow:0 2px 12px rgba(0,0,0,0.4); opacity:0; transition:opacity 0.18s ease; max-width: 520px; text-align: center;`;
        t.textContent = msg;
        host.appendChild(t);
        requestAnimationFrame(() => { t.style.opacity = '1'; });
        const lifetime = (typeof durationMs === 'number' && durationMs > 0) ? durationMs : 2400;
        setTimeout(() => {
            t.style.opacity = '0';
            setTimeout(() => t.remove(), 220);
        }, lifetime);
    }

    // A panel is "verified" if its `source` flags it as cross-checked against
    // the manufacturer's published spec sheet/PDF rather than only the aggregated catalog's
    // (sometimes-outdated) internal database. Treats any source starting with
    // "official:" or containing "spec PDF" / "absen ... PDF" as verified.
    _isPanelVerified(p) {
        const s = (p && p.source || '').toLowerCase();
        if (!s) return false;
        // Anti-patterns: any entry whose specs were inferred rather than read
        // off a real spec sheet/PDF/website is not verified, even if the
        // source string mentions an authoritative site.
        if (/\b(est|estimated|derived|same as|inferred|approx)\b/.test(s)) return false;
        if (/\+\s*(frame|air frame|t4|ladder|windbrace|spotlight)/.test(s)) return false;
        // Trusted sources, manufacturer's own site / PDF, or a reputable
        // third-party dealer that publishes the full datasheet.
        if (s.startsWith('official:')) return true;
        if (s.startsWith('roevisual')) return true;          // roevisual.com (ROE)
        if (s.startsWith('absen ')) return true;             // absen JP / VN spec PDFs
        if (s.startsWith('ledwallcentral')) return true;     // dealer with full datasheets
        if (s.startsWith('xled.pro')) return true;           // dealer datasheet
        if (s.includes('spec pdf')) return true;
        if (s.includes('-specification.pdf')) return true;
        if (s.includes('brochure')) return true;             // any "...brochure" reference
        if (s.includes('per brochure')) return true;
        return false;
    }

    _renderPanelCatalogList() {
        const listEl = document.getElementById('panel-catalog-list');
        const mfrSel = document.getElementById('panel-catalog-mfr');
        const searchEl = document.getElementById('panel-catalog-search');
        if (!listEl || !this._panelCatalogFlat) return;
        const q = (searchEl && searchEl.value || '').trim().toLowerCase();
        const mfrFilter = mfrSel && mfrSel.value || '';
        let rows = this._panelCatalogFlat;
        if (mfrFilter) rows = rows.filter(p => p._mfr === mfrFilter);
        if (q) rows = rows.filter(p => p._searchKey.indexOf(q) !== -1);
        // Cap render to keep DOM light
        const MAX = 300;
        const total = rows.length;
        rows = rows.slice(0, MAX);
        listEl.innerHTML = '';
        if (!total) {
            listEl.innerHTML = '<div style="padding: 12px; color: #888; font-size: 12px;">No panels match.</div>';
            return;
        }
        rows.forEach(p => {
            const item = document.createElement('div');
            item.className = 'panel-catalog-row';
            item.dataset.mfr = p._mfr;
            item.dataset.name = p.name || '';
            item.style.cssText = 'padding: 8px 10px; border-bottom: 1px solid #222; cursor: pointer;';
            const specs = [];
            if (p.width_mm != null && p.height_mm != null) specs.push(`${p.width_mm}×${p.height_mm}mm`);
            if (p.pixels_w != null && p.pixels_h != null) specs.push(`${p.pixels_w}×${p.pixels_h}px`);
            if (p.weight_kg != null) specs.push(`${p.weight_kg}kg`);
            if (p.watts_max != null) specs.push(`${p.watts_max}W`);
            // Verified ⭐: panel specs were cross-checked against the manufacturer's
            // own published spec sheet/PDF (not just the aggregated catalog).
            const verified = this._isPanelVerified(p);
            const star = verified ? `<span title="Verified against ${this.escapeHtml(p.source || '')}" style="color:#f5c842; margin-right:4px;">⭐</span>` : '';
            const isFav = this._isCatalogFavorited(p._mfr, p.name);
            // Layout: text on the left, heart pinned on the right.
            item.style.cssText = 'padding: 8px 10px; border-bottom: 1px solid #222; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px;';
            const textCol = document.createElement('div');
            textCol.style.cssText = 'flex: 1; min-width: 0;';
            textCol.innerHTML = `<div style="color:#fff; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${star}<span style="color:#8ab4f8;">${this.escapeHtml(p._mfr.replace(/_/g, ' '))}</span> · ${this.escapeHtml(p.name || '')}</div><div style="color:#888; font-size:11px;">${specs.join(' · ')}</div>`;
            item.appendChild(textCol);
            const heartBtn = document.createElement('button');
            heartBtn.className = 'btn';
            heartBtn.innerHTML = isFav ? '♥' : '♡';
            heartBtn.title = isFav ? 'Remove from favorites' : 'Add to favorites';
            heartBtn.style.cssText = `background: transparent; color: ${isFav ? '#e25555' : '#888'}; font-size: 14px; padding: 2px 8px; border: 1px solid #333;`;
            heartBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this._toggleCatalogFavorite(p);
                this._renderPanelCatalogList();
                this._renderPresetPickerLeftColumn();
            });
            item.appendChild(heartBtn);
            item.addEventListener('click', () => {
                this._pickerSelection = { type: 'panel', key: p._mfr + '|' + p.name, panel: p, label: `${p._mfr.replace(/_/g,' ')} ${p.name}` };
                this._highlightPickerSelection();
                this._updatePickerSummary();
            });
            listEl.appendChild(item);
        });
        if (total > MAX) {
            const more = document.createElement('div');
            more.style.cssText = 'padding: 8px 10px; color: #888; font-size: 11px; text-align: center; background: #1d1d1d;';
            more.textContent = `Showing first ${MAX} of ${total.toLocaleString()}. Refine search or pick a manufacturer.`;
            listEl.appendChild(more);
        }
        this._highlightPickerSelection();
    }

    _highlightPickerSelection() {
        const sel = this._pickerSelection || {};
        document.querySelectorAll('#preset-picker-list .preset-picker-row').forEach(el => {
            const kind = el.dataset.kind;
            let match = false;
            if (kind === 'favorite') {
                match = sel.type === 'panel' && el.dataset.key === sel.key;
            } else {
                match = sel.type === 'preset' && el.dataset.key === sel.key;
            }
            el.style.background = match ? '#2d4a7a' : 'transparent';
        });
        document.querySelectorAll('#panel-catalog-list .panel-catalog-row').forEach(el => {
            const key = el.dataset.mfr + '|' + el.dataset.name;
            el.style.background = (sel.type === 'panel' && key === sel.key) ? '#2d4a7a' : 'transparent';
        });
    }

    _updatePickerSummary() {
        const summary = document.getElementById('preset-picker-summary');
        if (!summary) return;
        const sel = this._pickerSelection || {};
        if (sel.type === 'panel' && sel.panel) {
            const p = sel.panel;
            const parts = [];
            if (p.width_mm != null) parts.push(`${p.width_mm}×${p.height_mm}mm`);
            if (p.pixels_w != null) parts.push(`${p.pixels_w}×${p.pixels_h}px`);
            if (p.weight_kg != null) parts.push(`${p.weight_kg}kg`);
            if (p.watts_max != null) parts.push(`${p.watts_max}W`);
            summary.textContent = `Panel: ${sel.label}, ${parts.join(' · ')}`;
        } else if (sel.type === 'preset' && sel.key && sel.key !== '__default__') {
            summary.textContent = `Preset: ${sel.label || sel.key}`;
        } else {
            summary.textContent = 'Default, uses your Preferences values.';
        }
    }

    closePresetPicker() {
        const modal = document.getElementById('preset-picker-modal');
        if (modal) modal.style.display = 'none';
    }

    confirmPresetPicker() {
        const sel = this._pickerSelection || { type: 'preset', key: '__default__' };
        this.closePresetPicker();
        if (sel.type === 'panel' && sel.panel) {
            this.addLayer(this._panelToPresetData(sel.panel));
            return;
        }
        if (sel.type === 'preset') {
            if (!sel.key || sel.key === '__default__') {
                this.addLayer();
                return;
            }
            this.fetchPreset(sel.key).then(resp => {
                const data = resp && resp.data ? resp.data : null;
                if (data) data._presetName = sel.key;
                this.addLayer(data);
            }).catch(err => {
                alert('Failed to load preset: ' + (err && err.error || 'unknown'));
                this.addLayer();
            });
        }
    }

    // Convert a catalog panel into preset-shaped data that addLayer() consumes.
    // Grid (columns/rows) comes from Preferences; panel-specific fields override.
    _panelToPresetData(panel) {
        const prefs = this.getPreferences() || {};
        const weightUnit = prefs.weightUnit || 'kg';
        const weightKg = panel.weight_kg;
        const weight = (weightKg != null)
            ? (weightUnit === 'lb' ? +(weightKg * 2.20462).toFixed(2) : weightKg)
            : prefs.panelWeight;
        const data = {
            columns: prefs.columns,
            rows: prefs.rows,
            cabinet_width: panel.pixels_w != null ? panel.pixels_w : prefs.panelWidth,
            cabinet_height: panel.pixels_h != null ? panel.pixels_h : prefs.panelHeight,
            panel_width_mm: panel.width_mm,
            panel_height_mm: panel.height_mm,
            panel_weight: weight,
            weight_unit: weightUnit,
            _presetName: `${(panel._mfr || panel.manufacturer || '').replace(/_/g, ' ')} ${panel.name}`.trim()
        };
        if (panel.watts_max != null) data.panelWatts = panel.watts_max;
        return data;
    }

    // ── Spec correction / new-panel submission ──
    // Opens a pre-filled GitHub issue so users can submit a PDF spec sheet,
    // a back-of-panel photo, just flag bad data, or request a brand-new
    // panel that's missing from the catalog. Zero-server: GitHub hosts the
    // upload (drag-drop into the issue comment), we read it on our normal
    // triage workflow, no API keys / S3 / email gateway needed.
    openPanelSpecCorrection() {
        const sel = this._pickerSelection || {};
        const hasSelection = sel.type === 'panel' && sel.panel;

        // Branch: correction (existing panel) vs. new panel (missing one).
        // confirm() returns true=OK ("Fix existing"), false=Cancel ("Add new").
        // If the user already selected a panel in the catalog, default to fix.
        let mode;
        if (hasSelection) {
            mode = 'fix';
        } else {
            const choice = window.confirm(
                'Submit which kind of correction?\n\n' +
                '  OK   = "Fix specs on an existing panel"\n' +
                '  Cancel = "Add a panel that\'s missing from the catalog"'
            );
            mode = choice ? 'fix' : 'add';
        }

        let panelRef = '';
        let currentValues = '';
        if (hasSelection) {
            const p = sel.panel;
            panelRef = `${(p._mfr || p.manufacturer || '').replace(/_/g, ' ')} ${p.name}`.trim();
            const lines = [];
            if (p.width_mm != null) lines.push(`- Cabinet: ${p.width_mm} × ${p.height_mm} mm`);
            if (p.pixels_w != null) lines.push(`- Pixels: ${p.pixels_w} × ${p.pixels_h}`);
            if (p.weight_kg != null) lines.push(`- Weight: ${p.weight_kg} kg`);
            if (p.watts_max != null) lines.push(`- Max power: ${p.watts_max} W`);
            if (p.source) lines.push(`- Source: ${p.source}`);
            currentValues = lines.join('\n');
        } else {
            const ask = (mode === 'fix')
                ? 'Which panel has bad specs? (e.g. "Absen JP8 Pro")\n\nTip: select the panel in the catalog first to pre-fill this.'
                : 'What panel is missing? Manufacturer + model name (e.g. "Absen NEW-X 1.5")';
            panelRef = window.prompt(ask, '') || '';
            if (!panelRef) return;
        }

        const notesPrompt = (mode === 'fix')
            ? `What's wrong with "${panelRef}"?\n\nDescribe the discrepancy. After you click OK we'll open a GitHub issue, drag any spec sheet PDF or a photo of the panel back into the comment box there to attach it.`
            : `Tell us about "${panelRef}", paste any specs you have (cabinet mm, pixels, weight, max watts).\n\nAfter you click OK we'll open a GitHub issue, drag the official spec sheet PDF or a photo of the panel back into the comment box to attach it.`;
        const notes = window.prompt(notesPrompt, '');
        if (notes === null) return;  // cancelled

        const versionEl = document.querySelector('h1 span');
        const appVersion = (versionEl && versionEl.textContent) || '';

        const bodyLines = (mode === 'fix') ? [
            `**Panel:** ${panelRef}`,
            '',
            '**Current catalog values:**',
            currentValues || '_(no panel selected, please paste the catalog values you saw)_',
            '',
            '**What\'s wrong:**',
            notes || '_(left blank)_',
            '',
            '**Spec sheet / photo:**',
            '⬆️ Drag a PDF or photo into this comment box to attach it.',
            '',
            '---',
            `App version: ${appVersion}`,
        ] : [
            `**Panel to add:** ${panelRef}`,
            '',
            '**Specs (best-guess from user):**',
            notes || '_(left blank)_',
            '',
            '**Spec sheet / photo:**',
            '⬆️ Drag the official spec sheet PDF or a photo of the panel back into this comment box to attach it.',
            '',
            '---',
            `App version: ${appVersion}`,
        ];
        const titlePrefix = (mode === 'fix') ? 'Spec correction' : 'Add panel';
        const label = (mode === 'fix') ? 'spec-correction' : 'add-panel';
        const params = new URLSearchParams({
            title: `${titlePrefix}: ${panelRef}`,
            labels: label,
            body: bodyLines.join('\n'),
        });
        const url = `https://github.com/kman1898/LED-Raster-Designer/issues/new?${params.toString()}`;
        // Make sure the user knows the GitHub tab is the actual submission,
        // we've had submissions get lost because the user filled out the
        // app-side prompts and assumed that was enough.
        const ok = confirm(
            'This will open GitHub in a new tab with your submission pre-filled.\n\n' +
            'IMPORTANT: You must be signed in to GitHub and click the green "Submit new issue" button there for it to actually reach us.\n\n' +
            'Continue?'
        );
        if (!ok) return;
        window.open(url, '_blank', 'noopener');
    }

    // ── Save-as-Preset Modal ──
    openPresetSaveModal() {
        if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'screen') {
            alert('Select a screen layer first to save as a preset.');
            return;
        }
        const modal = document.getElementById('preset-save-modal');
        const nameInput = document.getElementById('preset-save-name');
        const warning = document.getElementById('preset-save-warning');
        const sublabel = document.getElementById('preset-save-sublabel');
        if (!modal || !nameInput) return;
        nameInput.value = this.currentLayer.name || '';
        warning.textContent = '';
        if (sublabel) sublabel.textContent = `Saving settings from "${this.currentLayer.name || 'current layer'}".`;
        modal.style.display = 'block';
        setTimeout(() => nameInput.focus(), 50);
        this._presetSaveExistingNames = null;
        this._renderPresetSaveExistingList([]);
        this.updatePresetSaveConfirmButton();
        this.fetchPresetList().then(list => {
            this._presetSaveExistingNames = list;
            this._renderPresetSaveExistingList(list);
            this.updatePresetSaveWarning();
            this.updatePresetSaveConfirmButton();
        });
    }

    _renderPresetSaveExistingList(names) {
        const section = document.getElementById('preset-save-existing-section');
        const list = document.getElementById('preset-save-existing-list');
        if (!section || !list) return;
        list.innerHTML = '';
        if (!Array.isArray(names) || names.length === 0) {
            section.style.display = 'none';
            return;
        }
        section.style.display = 'block';
        names.forEach(name => {
            const row = document.createElement('div');
            row.className = 'preset-save-existing-row';
            row.style.cssText = 'padding: 6px 8px; color: #ddd; font-size: 12px; cursor: pointer; border-radius: 3px;';
            row.textContent = name;
            row.title = `Click to overwrite "${name}"`;
            row.addEventListener('mouseenter', () => { row.style.background = '#2d4a7a'; });
            row.addEventListener('mouseleave', () => { row.style.background = 'transparent'; });
            row.addEventListener('click', () => {
                const nameInput = document.getElementById('preset-save-name');
                if (nameInput) {
                    nameInput.value = name;
                    nameInput.focus();
                    this.updatePresetSaveWarning();
                    this.updatePresetSaveConfirmButton();
                }
            });
            list.appendChild(row);
        });
    }

    updatePresetSaveConfirmButton() {
        const btn = document.getElementById('preset-save-confirm');
        const nameInput = document.getElementById('preset-save-name');
        if (!btn || !nameInput) return;
        const name = nameInput.value.trim();
        const existing = this._presetSaveExistingNames || [];
        if (name && existing.includes(name)) {
            btn.textContent = 'Overwrite';
        } else {
            btn.textContent = 'Save';
        }
    }

    closePresetSaveModal() {
        const modal = document.getElementById('preset-save-modal');
        if (modal) modal.style.display = 'none';
    }

    updatePresetSaveWarning() {
        const nameInput = document.getElementById('preset-save-name');
        const warning = document.getElementById('preset-save-warning');
        if (!nameInput || !warning) return;
        const name = nameInput.value.trim();
        if (!name) {
            warning.textContent = '';
            return;
        }
        const existing = this._presetSaveExistingNames || [];
        if (existing.includes(name)) {
            warning.textContent = `⚠ A preset named "${name}" already exists. Saving will overwrite it.`;
        } else {
            warning.textContent = '';
        }
    }

    confirmPresetSave() {
        const nameInput = document.getElementById('preset-save-name');
        const warning = document.getElementById('preset-save-warning');
        if (!nameInput) return;
        const name = nameInput.value.trim();
        if (!name) {
            warning.textContent = 'Please enter a name.';
            return;
        }
        const existing = this._presetSaveExistingNames || [];
        if (existing.includes(name)) {
            if (!confirm(`A preset named "${name}" already exists. Overwrite it?`)) return;
        }
        const data = this.serializeLayerAsPreset(this.currentLayer);
        if (!data) {
            warning.textContent = 'No layer selected.';
            return;
        }
        this.savePresetToServer(name, data).then(() => {
            this.closePresetSaveModal();
        }).catch(err => {
            warning.textContent = 'Failed: ' + (err && err.error || 'unknown error');
        });
    }

    setupPresetModals() {
        const pickerCancel = document.getElementById('preset-picker-cancel');
        const pickerAdd = document.getElementById('preset-picker-add');
        if (pickerCancel) pickerCancel.addEventListener('click', () => this.closePresetPicker());
        if (pickerAdd) pickerAdd.addEventListener('click', () => this.confirmPresetPicker());

        const submitLink = document.getElementById('panel-submit-correction');
        if (submitLink) submitLink.addEventListener('click', (e) => {
            e.preventDefault();
            this.openPanelSpecCorrection();
        });

        const refreshBtn = document.getElementById('panel-catalog-refresh-btn');
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.refreshPanelCatalogNow());

        const saveCancel = document.getElementById('preset-save-cancel');
        const saveConfirm = document.getElementById('preset-save-confirm');
        const saveName = document.getElementById('preset-save-name');
        if (saveCancel) saveCancel.addEventListener('click', () => this.closePresetSaveModal());
        if (saveConfirm) saveConfirm.addEventListener('click', () => this.confirmPresetSave());
        if (saveName) {
            saveName.addEventListener('input', () => {
                this.updatePresetSaveWarning();
                this.updatePresetSaveConfirmButton();
            });
            saveName.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this.confirmPresetSave();
                else if (e.key === 'Escape') this.closePresetSaveModal();
            });
        }
        // Close modals on backdrop click
        ['preset-picker-modal', 'preset-save-modal'].forEach(id => {
            const m = document.getElementById(id);
            if (m) {
                m.addEventListener('click', (e) => {
                    if (e.target === m) m.style.display = 'none';
                });
            }
        });
    }

    escapeHtml(s) {
        if (s == null) return '';
        return String(s).replace(/[&<>"']/g, ch => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
        ));
    }

    addImageLayer(imageData, imageWidth, imageHeight) {
        const name = this.getNextImageLayerName();
        fetch('/api/layer/add-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                imageData,
                imageWidth,
                imageHeight,
                offset_x: 0,
                offset_y: 0,
                imageScale: 1.0
            })
        })
        .then(res => res.json())
        .then(layer => {
            sendClientLog('add_image_layer', { id: layer.id, name: layer.name });
            this.initializeLayerDefaults(layer);
            if (layer.imageData) {
                const img = new Image();
                img.onload = () => {
                    if (layer._imageObj !== img) return;
                    window.canvasRenderer.render();
                };
                img.src = layer.imageData;
                layer._imageObj = img;
            }
            this.upsertProjectLayer(layer);
            // Snapshot AFTER the layer is in the project. Taken before the
            // async add (as it was), Undo-then-Redo restored a snapshot with
            // no image layer and the add was lost — the v0.10.0 Add Layer bug.
            this.saveState('Add Image Layer');
            this.selectLayer(layer);
            window.canvasRenderer.fitToView();
            window.canvasRenderer.render();
            this.saveClientSideProperties();
        });
    }

    addTextLayer() {
        const name = this.getNextTextLayerName();
        fetch('/api/layer/add-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, textContent: '', offset_x: 0, offset_y: 0 })
        })
        .then(res => res.json())
        .then(layer => {
            sendClientLog('add_text_layer', { id: layer.id, name: layer.name });
            this.upsertProjectLayer(layer);
            // Snapshot AFTER the layer exists (see addImageLayer).
            this.saveState('Add Text Layer');
            this.selectLayer(layer);
            window.canvasRenderer.fitToView();
            window.canvasRenderer.render();
            this.saveClientSideProperties();
        });
    }

    getNextTextLayerName() {
        const base = 'Text';
        const existing = this.project.layers
            .filter(l => (l.type || 'screen') === 'text')
            .map(l => l.name || '')
            .filter(name => name.startsWith(base));
        let maxNum = 0;
        existing.forEach(name => {
            const m = name.match(/^Text\s*(\d+)$/i);
            if (m) maxNum = Math.max(maxNum, parseInt(m[1], 10));
        });
        return `Text ${maxNum + 1}`;
    }

    // Map current view mode to the per-tab text content property
    getTextContentPropForTab() {
        const viewMode = window.canvasRenderer ? window.canvasRenderer.viewMode : 'pixel-map';
        const map = {
            'pixel-map': 'textContentPixelMap',
            'cabinet-id': 'textContentCabinetId',
            'show-look': 'textContentShowLook',
            'data-flow': 'textContentDataFlow',
            'power': 'textContentPower'
        };
        return map[viewMode] || 'textContentPixelMap';
    }

    // v0.8.3: per-tab override flag prop name for the current view mode.
    getTextContentOverridePropForTab() {
        const viewMode = window.canvasRenderer ? window.canvasRenderer.viewMode : 'pixel-map';
        const map = {
            'pixel-map': 'textContentOverridePixelMap',
            'cabinet-id': 'textContentOverrideCabinetId',
            'show-look': 'textContentOverrideShowLook',
            'data-flow': 'textContentOverrideDataFlow',
            'power': 'textContentOverridePower'
        };
        return map[viewMode] || 'textContentOverridePixelMap';
    }

    // v0.8.3: resolve the text shown for `layer` on the active tab.
    // If the tab override is on, use that tab's own field; else use the
    // shared `textContent`. Falls back to any non-empty per-tab field for
    // legacy projects (pre-v0.8.3) where shared was empty but per-tab had
    // content.
    resolveTextContentForActiveTab(layer) {
        if (!layer) return '';
        const overrideProp = this.getTextContentOverridePropForTab();
        const tabProp = this.getTextContentPropForTab();
        if (layer[overrideProp]) return layer[tabProp] || '';
        if (layer.textContent) return layer.textContent;
        // Legacy fallback: a project saved before v0.8.3 might have content
        // only in the per-tab fields. Surface whatever's there so the user
        // can see and edit it.
        const legacyKeys = ['textContentPixelMap', 'textContentCabinetId',
                            'textContentShowLook', 'textContentDataFlow',
                            'textContentPower'];
        for (const k of legacyKeys) {
            if (layer[k]) return layer[k];
        }
        return '';
    }

    getTextTabLabel() {
        const viewMode = window.canvasRenderer ? window.canvasRenderer.viewMode : 'pixel-map';
        const map = {
            'pixel-map': '(Pixel Map)',
            'cabinet-id': '(Cabinet ID)',
            'show-look': '(Show Look)',
            'data-flow': '(Data)',
            'power': '(Power)'
        };
        return map[viewMode] || '(Pixel Map)';
    }

    setupTextLayerControls() {
        // Text content textarea. v0.8.3: writes to the shared `textContent`
        // field by default; if the per-tab override is on, writes to that
        // tab's own `textContent<Tab>` instead.
        const contentEl = document.getElementById('text-layer-content');
        if (contentEl) {
            contentEl.addEventListener('input', () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                const overrideProp = this.getTextContentOverridePropForTab();
                const tabProp = this.getTextContentPropForTab();
                const val = contentEl.value;
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    if (layer[overrideProp]) {
                        layer[tabProp] = val;
                    } else {
                        layer.textContent = val;
                    }
                });
                // Typing is a genuine continuous stream, so a burst of
                // keystrokes stays one undo step.
                this.debouncedSaveState('Update Text Label', 500, 'text:content');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        }

        // v0.8.3: per-tab content override checkbox. Toggling ON seeds the
        // per-tab field with the currently displayed (shared) text so the
        // user has something to edit instead of an empty box. Toggling OFF
        // reverts the textarea to the shared text without touching the
        // per-tab value (so re-enabling restores their previous override).
        const overrideEl = document.getElementById('text-layer-content-override');
        if (overrideEl) {
            overrideEl.addEventListener('change', () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                const overrideProp = this.getTextContentOverridePropForTab();
                const tabProp = this.getTextContentPropForTab();
                const enabling = overrideEl.checked;
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    layer[overrideProp] = enabling;
                    if (enabling && !layer[tabProp]) {
                        // Seed override with current shared value so user
                        // doesn't lose context when flipping the checkbox.
                        layer[tabProp] = layer.textContent || '';
                    }
                });
                this.saveState('Toggle Text Tab Override');
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                this.updateLayerControls();
                window.canvasRenderer.render();
            });
        }

        const fields = [
            { id: 'text-layer-font-size', prop: 'fontSize', type: 'number' },
            { id: 'text-layer-align', prop: 'textAlign', type: 'select' },
            { id: 'text-layer-width', prop: 'textWidth', type: 'number' },
            { id: 'text-layer-height', prop: 'textHeight', type: 'number' },
            { id: 'text-layer-bg-opacity', prop: 'bgOpacity', type: 'float' },
            { id: 'text-layer-padding', prop: 'textPadding', type: 'number' },
            { id: 'text-layer-show-border', prop: 'showBorder', type: 'checkbox' },
            { id: 'text-layer-show-raster-size', prop: 'showRasterSize', type: 'checkbox' },
            { id: 'text-layer-show-project-name', prop: 'showProjectName', type: 'checkbox' },
            { id: 'text-layer-show-date', prop: 'showDate', type: 'checkbox' },
            { id: 'text-layer-show-primary-ports', prop: 'showPrimaryPorts', type: 'checkbox' },
            { id: 'text-layer-show-backup-ports', prop: 'showBackupPorts', type: 'checkbox' },
            { id: 'text-layer-show-circuits', prop: 'showCircuits', type: 'checkbox' },
            { id: 'text-layer-show-single-phase', prop: 'showSinglePhase', type: 'checkbox' },
            { id: 'text-layer-show-three-phase', prop: 'showThreePhase', type: 'checkbox' },
            // Slice 10: scope dropdown for the dynamic data/power lines.
            // 'canvas' = text layer's parent canvas, 'project' = all canvases,
            // 'both' = render both lines per metric.
            { id: 'text-layer-dynamic-info-scope', prop: 'dynamicInfoScope', type: 'select' },
            { id: 'text-layer-show-pixel-map', prop: 'showOnPixelMap', type: 'checkbox' },
            { id: 'text-layer-show-cabinet-id', prop: 'showOnCabinetId', type: 'checkbox' },
            { id: 'text-layer-show-show-look', prop: 'showOnShowLook', type: 'checkbox' },
            { id: 'text-layer-show-data-flow', prop: 'showOnDataFlow', type: 'checkbox' },
            { id: 'text-layer-show-power', prop: 'showOnPower', type: 'checkbox' },
        ];
        fields.forEach(f => {
            const el = document.getElementById(f.id);
            if (!el) return;
            const event = f.type === 'checkbox' ? 'change' : (f.type === 'select' ? 'change' : 'input');
            el.addEventListener(event, () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                let val;
                if (f.type === 'checkbox') val = el.checked;
                else if (f.type === 'number') val = parseInt(el.value, 10) || 0;
                else if (f.type === 'float') val = parseFloat(el.value) || 0;
                else val = el.value;
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    layer[f.prop] = val;
                });
                this.debouncedSaveState('Update Text Label', 500, `text:${f.prop}`);
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        });
        // Color pickers.
        //
        // These two used to have their own picker/hex wiring, which did
        // everything the field handlers above do EXCEPT call updateLayers().
        // So recolouring a text label looked right and stayed right until the
        // page reloaded: nothing ever PUT it, and the server kept the colour
        // the layer was created with. Going through the shared helper fixes
        // that and gets the isFinal distinction with it - the live drag
        // re-renders, and only the commit hits the server.
        const setupTextColor = (pickerId, hexId, prop) => {
            setupColorPickerWithHex(pickerId, hexId, (val, isFinal) => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    layer[prop] = val;
                });
                window.canvasRenderer.render();
                if (!isFinal) return;
                this.debouncedSaveState('Update Text Color', 500, `text:${prop}`);
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
            });
        };
        setupTextColor('text-layer-font-color', 'text-layer-font-color-hex', 'fontColor');
        setupTextColor('text-layer-bg-color', 'text-layer-bg-color-hex', 'bgColor');

        // Bold / Italic / Underline toggle buttons
        const setupStyleToggle = (btnId, prop) => {
            const btn = document.getElementById(btnId);
            if (!btn) return;
            btn.addEventListener('click', () => {
                if (!this.currentLayer || (this.currentLayer.type || 'screen') !== 'text') return;
                const newVal = !this.currentLayer[prop];
                this.applyToSelectedLayers(layer => {
                    if ((layer.type || 'screen') !== 'text') return;
                    layer[prop] = newVal;
                });
                btn.classList.toggle('active', newVal);
                this.debouncedSaveState('Update Text Style', 500, `text:${prop}`);
                this.saveClientSideProperties();
                this.updateLayers(this.getSelectedLayers());
                window.canvasRenderer.render();
            });
        };
        setupStyleToggle('text-layer-bold', 'fontBold');
        setupStyleToggle('text-layer-italic', 'fontItalic');
        setupStyleToggle('text-layer-underline', 'fontUnderline');
    }

    loadTextLayerToInputs() {
        const panel = document.getElementById('text-layer-panel');
        if (!panel) return;
        const layer = this.currentLayer;
        if (!layer || (layer.type || 'screen') !== 'text') {
            panel.style.display = 'none';
            return;
        }
        panel.style.display = 'block';
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
        const setChecked = (id, val) => { const el = document.getElementById(id); if (el) el.checked = val; };

        // v0.8.3: textarea reflects shared content unless this tab is
        // overridden, in which case it reflects this tab's own field.
        const overrideProp = this.getTextContentOverridePropForTab();
        const isOverride = !!layer[overrideProp];
        setVal('text-layer-content', this.resolveTextContentForActiveTab(layer));
        setChecked('text-layer-content-override', isOverride);

        // Update tab indicator: append "(override)" when active tab is on its
        // own content so it's obvious why typing only affects this tab.
        const tabIndicator = document.getElementById('text-layer-tab-indicator');
        if (tabIndicator) {
            tabIndicator.textContent = isOverride
                ? `${this.getTextTabLabel()} · OVERRIDE`
                : '· SHARED ACROSS TABS';
        }

        setVal('text-layer-font-size', layer.fontSize || 24);
        setVal('text-layer-align', layer.textAlign || 'left');
        setVal('text-layer-width', layer.textWidth || 400);
        setVal('text-layer-height', layer.textHeight || 100);
        setVal('text-layer-font-color', layer.fontColor || '#ffffff');
        setVal('text-layer-font-color-hex', (layer.fontColor || '#ffffff').toUpperCase());
        setVal('text-layer-bg-color', layer.bgColor || '#000000');
        setVal('text-layer-bg-color-hex', (layer.bgColor || '#000000').toUpperCase());
        setVal('text-layer-bg-opacity', layer.bgOpacity != null ? layer.bgOpacity : 0.7);
        setVal('text-layer-padding', layer.textPadding || 12);
        setChecked('text-layer-show-border', layer.showBorder !== false);
        setChecked('text-layer-show-raster-size', !!layer.showRasterSize);
        setChecked('text-layer-show-project-name', !!layer.showProjectName);
        setChecked('text-layer-show-date', !!layer.showDate);
        setChecked('text-layer-show-pixel-map', layer.showOnPixelMap !== false);
        setChecked('text-layer-show-cabinet-id', layer.showOnCabinetId !== false);
        setChecked('text-layer-show-show-look', layer.showOnShowLook !== false);
        setChecked('text-layer-show-data-flow', layer.showOnDataFlow !== false);
        setChecked('text-layer-show-power', layer.showOnPower !== false);
        setChecked('text-layer-show-primary-ports', !!layer.showPrimaryPorts);
        setChecked('text-layer-show-backup-ports', !!layer.showBackupPorts);
        setChecked('text-layer-show-circuits', !!layer.showCircuits);
        setChecked('text-layer-show-single-phase', !!layer.showSinglePhase);
        setChecked('text-layer-show-three-phase', !!layer.showThreePhase);
        const scopeSel = document.getElementById('text-layer-dynamic-info-scope');
        if (scopeSel) scopeSel.value = layer.dynamicInfoScope || 'project';

        // Style toggle buttons
        const boldBtn = document.getElementById('text-layer-bold');
        const italicBtn = document.getElementById('text-layer-italic');
        const underlineBtn = document.getElementById('text-layer-underline');
        if (boldBtn) boldBtn.classList.toggle('active', !!layer.fontBold);
        if (italicBtn) italicBtn.classList.toggle('active', !!layer.fontItalic);
        if (underlineBtn) underlineBtn.classList.toggle('active', !!layer.fontUnderline);
    }

    // Aggregate data port counts across all visible screen layers.
    // Slice 9: exclude layers whose canvas is hidden.
    // Slice 10: optional onlyCanvasId filter for per-canvas sidebar totals.
    getPortCounts(onlyCanvasId) {
        if (!this.project || !this.project.layers) return { primary: 0, backup: 0 };
        let totalPrimary = 0;
        const hiddenCanvasIds = this._hiddenCanvasIdSet();
        // v0.8.6.3: Data Flow renders at Show Look position and groups by
        // show_canvas_id, so per-canvas Data totals on that tab should
        // count by show_canvas_id || canvas_id, not by Pixel Map canvas_id.
        const isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const effCid = (l) => (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
        this.project.layers.forEach(layer => {
            if ((layer.type || 'screen') !== 'screen') return;
            if (layer.visible === false) return;  // v0.11.0: missing key means visible
            const lcid = effCid(layer);
            if (lcid && hiddenCanvasIds.has(lcid)) return;
            if (onlyCanvasId && lcid !== onlyCanvasId) return;
            const activePanels = (layer.panels || []).filter(p => !p.blank && !p.hidden);
            if (activePanels.length === 0) return;
            // v0.11.0 fix: this used to re-run calculatePortAssignments and
            // count distinct a.port, which is the AUTOMATIC map and nothing
            // else. A screen hand-wired to three ports read 3 in the sidebar,
            // 3 on its screen label and 3 in the group roll-up - and 1 here,
            // on the text layer that gets printed and handed to the crew,
            // because four cabinets fit one Brompton port.
            //
            // getLayerPortsRequired is the one implementation v0.11.0
            // collapsed the other three copies into: it prefers the drawn
            // customPortPaths over the automatic figure and returns 0 for a
            // member whose cabinets are already fed by a peer's crossing
            // port, so summing it across the project can neither miss a
            // hand-drawn port nor count one cable twice.
            //
            // v0.12 adds the second way a member reports 0: a group of
            // matching panels routes AUTOMATICALLY as one bigger screen, and
            // the group's first member carries the whole wall's figure. The
            // sum here is unchanged by that - one wall, counted once - and it
            // is the wall's real requirement rather than the sum of what its
            // sections would each have needed apart.
            totalPrimary += this.getLayerPortsRequired(layer) || 0;
        });
        // Every primary port has a backup/return port
        return { primary: totalPrimary, backup: totalPrimary };
    }

    // Aggregate power stats across all visible screen layers.
    // Slice 9: exclude layers whose canvas is hidden.
    // Slice 10: optional onlyCanvasId filter for per-canvas sidebar totals.
    //
    // v0.11.0 fix, three parts:
    //   circuits  came from a bulk division, ceil(layerWatts / circuitWatts),
    //             which ignores row/column packing entirely and can only ever
    //             UNDER-count. It now comes from the map the app actually
    //             draws, through the same getLayerCircuitsRequired the group
    //             roll-up uses, so a hand-drawn circuit map is honoured too -
    //             and, since v0.12, so is a group whose members are the same
    //             panel and the same wattage, where ONE combined walk's figure
    //             is reported by the group's first member and by nobody else.
    //   voltage   mixed voltages were blended: all the watts divided by
    //             whichever voltage was seen first. There is no honest
    //             combined amps figure across two voltages, so the combined
    //             ones go null and `byVoltage` carries the real per-wall
    //             answers. Same contract as getGroupTotals.
    //   watts     panelWatts is read parseFloat(...) || 0, as every other
    //             reader in the app does (calculatePowerAssignments,
    //             getGroupTotals, updatePowerCapacityDisplay, the canvas
    //             power label). The old `|| 200` stand-in invented a wattage
    //             the user never entered.
    getPowerCounts(onlyCanvasId) {
        const empty = {
            circuits: 0, totalWatts: 0, singlePhaseAmps: 0, threePhaseAmps: 0,
            voltage: 0, voltages: [], voltageMismatch: false, byVoltage: [],
            wattsUnset: [],
        };
        if (!this.project || !this.project.layers) return empty;
        let totalCircuits = 0;
        let totalWattsAll = 0;
        const voltages = [];
        const byVoltage = new Map();
        const wattsUnset = [];
        const hiddenCanvasIds = this._hiddenCanvasIdSet();
        // v0.8.6.3: same Show-Look-aware grouping as getPortCounts.
        const isShowView = !!(window.canvasRenderer && window.canvasRenderer.isShowLookView
            && window.canvasRenderer.isShowLookView());
        const effCid = (l) => (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
        this.project.layers.forEach(layer => {
            if ((layer.type || 'screen') !== 'screen') return;
            if (layer.visible === false) return;  // v0.11.0: missing key means visible
            const lcid = effCid(layer);
            if (lcid && hiddenCanvasIds.has(lcid)) return;
            if (onlyCanvasId && lcid !== onlyCanvasId) return;
            const activePanels = (layer.panels || []).filter(p => !p.blank && !p.hidden);
            if (activePanels.length === 0) return;
            const voltage = Number(layer.powerVoltage) || 110;
            const panelWatts = parseFloat(layer.panelWatts) || 0;
            if (!(panelWatts > 0)) wattsUnset.push(layer.id);
            if (!voltages.includes(voltage)) voltages.push(voltage);
            const equivalentPanels = activePanels.reduce((sum, p) => sum + this.getPanelLoadFactor(layer, p), 0);
            const layerWatts = panelWatts * equivalentPanels;
            totalWattsAll += layerWatts;
            // The circuits the app DRAWS, not a bulk division. Worked example:
            // 3 columns x 6 rows, 200 W a cabinet, 110 V x 20 A = 2200 W a
            // circuit, Organized column-first. Each column is 6 x 200 =
            // 1200 W and two columns are 2400 W > 2200, so the map is one
            // circuit per column = 3. ceil(3600 / 2200) said 2.
            const powerAssignments = this.calculatePowerAssignments(layer)
                || { circuits: [], error: null };
            const autoCircuits = (powerAssignments.circuits || []).length;
            const circuits = this.getLayerCircuitsRequired(layer, autoCircuits) || 0;
            totalCircuits += circuits;
            const bucket = byVoltage.get(voltage)
                || { voltage, watts: 0, circuits: 0, amps1ph: 0, amps3ph: 0 };
            bucket.watts += layerWatts;
            bucket.circuits += circuits;
            byVoltage.set(voltage, bucket);
        });
        // I = P / V single phase, I = P / (V x 1.73) three phase.
        byVoltage.forEach(b => {
            b.amps1ph = b.voltage > 0 ? b.watts / b.voltage : 0;
            b.amps3ph = b.voltage > 0 ? b.watts / (b.voltage * 1.73) : 0;
        });
        const voltageMismatch = voltages.length > 1;
        // No layers counted keeps the old 110 V stand-in so a project with
        // nothing in it reports 0 A rather than dividing by zero.
        const voltage = voltageMismatch ? null : (voltages[0] || 110);
        const singlePhaseAmps = voltageMismatch
            ? null : (voltage > 0 ? totalWattsAll / voltage : 0);
        const threePhaseAmps = voltageMismatch
            ? null : (voltage > 0 ? totalWattsAll / (voltage * 1.73) : 0);
        return {
            circuits: totalCircuits,
            totalWatts: totalWattsAll,
            singlePhaseAmps,
            threePhaseAmps,
            voltage,
            voltages,
            // True when the project spans more than one voltage. The combined
            // amps are null in that case - callers must show byVoltage (or
            // per-screen figures) instead of printing a blended number that
            // belongs to neither wall.
            voltageMismatch,
            byVoltage: [...byVoltage.values()],
            // Screens whose panelWatts is unset/zero: they contribute 0 W and
            // 0 circuits, so a caller can say "not entered" rather than let a
            // confident 0 A stand for a wall nobody has costed yet.
            wattsUnset,
        };
    }

    getNextImageLayerName() {
        const base = 'Image';
        const existing = this.project.layers
            .filter(l => (l.type || 'screen') === 'image')
            .map(l => l.name || '')
            .filter(name => name.startsWith(base));
        let maxNum = 0;
        existing.forEach(name => {
            const m = name.match(/^Image\\s*(\\d+)$/i);
            if (m) maxNum = Math.max(maxNum, parseInt(m[1], 10));
        });
        return `Image ${maxNum + 1}`;
    }

    handleImageFileSelection(e) {
        const input = e.target;
        const file = input.files && input.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            const dataUrl = reader.result;
            const img = new Image();
            img.onload = () => {
                if (this.imageFileAction === 'replace' && this.currentLayer && this.currentLayer.type === 'image') {
                    this.currentLayer.imageData = dataUrl;
                    this.currentLayer.imageWidth = img.width;
                    this.currentLayer.imageHeight = img.height;
                    this.updateLayer(true, 'Replace Image');
                    window.canvasRenderer.render();
                } else {
                    this.addImageLayer(dataUrl, img.width, img.height);
                }
            };
            img.src = dataUrl;
        };
        reader.readAsDataURL(file);
        // reset input for next time
        input.value = '';
    }
    
    // Initialize default values for a layer
    initializeLayerDefaults(layer) {
        const prefs = this.getPreferences();
        if ((layer.type || 'screen') === 'image') {
            layer.imageScale = layer.imageScale || 1.0;
            return;
        }
        if ((layer.type || 'screen') === 'text') {
            return;
        }
        layer.arrowLineWidth = prefs.dataLineWidth;  // Default line width for data flow
        layer.arrowColor = '#0042AA';
        layer.dataFlowColor = '#FFFFFF';
        layer.dataFlowLabelSize = prefs.dataLabelSize;
        layer.primaryColor = '#00FF00';
        layer.primaryTextColor = '#000000';
        layer.backupColor = '#FF0000';
        layer.backupTextColor = '#FFFFFF';
        layer.flowPattern = prefs.flowPattern;
        layer.bitDepth = prefs.bitDepth;
        layer.frameRate = prefs.frameRate;
        layer.processorType = prefs.processorType;
        layer.lowLatency = !!prefs.lowLatency;
        layer.portMappingMode = 'organized';
        layer.halfFirstColumn = !!layer.halfFirstColumn;
        layer.halfLastColumn = !!layer.halfLastColumn;
        layer.halfFirstRow = !!layer.halfFirstRow;
        layer.halfLastRow = !!layer.halfLastRow;
        layer.portLabelTemplatePrimary = 'P#';
        layer.portLabelTemplateReturn = 'R#';
        layer.portLabelOverridesPrimary = {};
        layer.portLabelOverridesReturn = {};
        // v0.11.0 (step 6): still the right reset, and it is the only one that
        // can be right. A brand-new layer has no group, so it has no peer a
        // cross-member path entry could legally name; a preset that carries
        // paths overlays them AFTER this (applyPresetClientProps), already
        // filtered down to the {row, col} entries that mean "this screen".
        layer.customPortPaths = {};
        layer.customPortIndex = 1;
        // Screen name size on the other tabs follows the label font size default
        // so the screen name is the same size across all tabs.
        layer.screenNameSizeCabinet = prefs.labelFontSize || 30;
        layer.screenNameSizeDataFlow = prefs.labelFontSize || 30;
        layer.screenNameSizePower = prefs.labelFontSize || 30;
        // Cabinet ID number size default to 30
        layer.number_size = 30;
        layer.randomDataColors = false;
        // Power defaults
        layer.powerVoltage = prefs.powerVoltage;
        layer.powerVoltageCustom = prefs.powerVoltage;
        layer.powerAmperage = prefs.powerAmperage;
        layer.powerAmperageCustom = prefs.powerAmperage;
        layer.panelWatts = prefs.powerWatts;
        layer.powerMaximize = false;
        layer.powerOrganized = true;
        layer.powerCustomPath = false;
        layer.powerFlowPattern = prefs.powerFlowPattern || 'tl-h';
        layer.powerLineWidth = prefs.powerLineWidth;
        layer.powerLineColor = '#FF0000';
        layer.powerArrowColor = '#0042AA';
        layer.powerRandomColors = false;
        layer.powerColorCodedView = false;
        layer.powerCircuitColors = this.getDefaultPowerCircuitColors();
        layer.powerLabelSize = prefs.powerLabelSize;
        layer.powerLabelBgColor = '#D95000';
        layer.powerLabelTextColor = '#000000';
        layer.powerLabelTemplate = 'S1-#';
        layer.powerLabelOverrides = {};
        layer.powerCircuitCables = {};
        layer.powerSocaNames = {};
        // Born keyed by the multi's stable index, so the one-time rekey never
        // runs over a screen that was already built the new way.
        layer.powerSocaKeying = 'index';
        layer.powerCustomPaths = {};   // same reason as customPortPaths above
        layer.powerCustomIndex = 1;
        layer.border_color_pixel = layer.border_color || prefs.borderColor;
        layer.border_color_cabinet = layer.border_color || prefs.borderColor;
        layer.border_color_data = layer.border_color || prefs.borderColor;
        layer.border_color_power = layer.border_color || prefs.borderColor;
        // v0.8.8.x: per-layer cabinet border width in LED pixels.
        if (layer.panel_border_width == null) layer.panel_border_width = 2;
        // v0.8.7.8: multi-color cabinet palette. 'checker' keeps the legacy
        // 2-color checkerboard (color1/color2); palette modes distribute
        // panelColors across cabinets by grid position.
        if (!layer.panelColorMode) layer.panelColorMode = 'checker';
        if (!Array.isArray(layer.panelColors)) layer.panelColors = [];

        // v0.8.7.8: standard gradient overlay. When enabled, a gradient
        // is composited on top of the checkerboard test pattern (Pixel Map /
        // Show Look / Cabinet ID) at gradientOpacity using gradientBlend.
        // Stops are { pos: 0..1, color: '#rrggbb' }.
        if (layer.gradientEnabled == null) layer.gradientEnabled = false;
        if (!layer.gradientType) layer.gradientType = 'linear';
        if (!layer.gradientScope) layer.gradientScope = 'screen';       // screen = whole screen, panel = per cabinet
        if (layer.gradientPanelAlternate == null) layer.gradientPanelAlternate = false; // mirror every other cabinet
        if (layer.gradientRadialCenterX == null) layer.gradientRadialCenterX = 0.5; // radial center, fraction of rect
        if (layer.gradientRadialCenterY == null) layer.gradientRadialCenterY = 0.5;
        if (layer.gradientRadialRadius == null) layer.gradientRadialRadius = 1;      // radial size, × base radius
        if (layer.gradientAngle == null) layer.gradientAngle = 0;       // 0 = left→right, 90 = top→bottom
        if (layer.gradientOpacity == null) layer.gradientOpacity = 0.6;
        if (!layer.gradientBlend) layer.gradientBlend = 'normal';       // normal|multiply|screen|overlay|...
        if (!Array.isArray(layer.gradientStops) || layer.gradientStops.length < 2) {
            layer.gradientStops = [
                { pos: 0, color: '#1d9e75' },
                { pos: 1, color: '#2145dc' },
            ];
        }
        // Only fall back to prefs if the server-created layer didn't already
        // carry these from the add request (e.g. from a preset or catalog panel).
        if (layer.panel_weight == null) layer.panel_weight = prefs.panelWeight;
        if (layer.weight_unit == null) layer.weight_unit = prefs.weightUnit || 'kg';
    }
}

for (const k of Object.getOwnPropertyNames(_Presets.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Presets.prototype, k));
    }
}
