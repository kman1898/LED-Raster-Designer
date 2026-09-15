// app-export-io: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _ExportIo {
    
    // Update export filename preview
    updateExportPreview() {
        const projectName = document.getElementById('export-name').value.trim() || 'Project';
        const format = document.getElementById('export-format').value;
        
        const viewNames = this.getExportViewNames();
        const suffixes = this.getExportSuffixesFromUI();
        
        const views = [];
        if (document.getElementById('export-pixel-map').checked) views.push('pixel-map');
        if (document.getElementById('export-cabinet-id').checked) views.push('cabinet-id');
        if (document.getElementById('export-show-look') && document.getElementById('export-show-look').checked) views.push('show-look');
        if (document.getElementById('export-data-flow').checked) views.push('data-flow');
        if (document.getElementById('export-power').checked) views.push('power');

        const preview = document.getElementById('export-preview');

        // Hide view checkboxes for Resolume XML (geometry only, no rendered
        // views) and for the pull sheet (a workbook, not a picture).
        const viewSection = document.getElementById('export-views-section');
        if (viewSection) {
            const geometryOnly = (format === 'resolume-xml' || format === 'pull-sheet' || format === 'binder');
            viewSection.style.display = geometryOnly ? 'none' : '';
        }

        if (format === 'binder') {
            preview.classList.add('value-accent');
            preview.style.color = '';
            preview.textContent = (typeof this.binderFileName === 'function')
                ? this.binderFileName(projectName) : `${projectName} - binder.pdf`;
            return;
        }

        if (format === 'pull-sheet') {
            preview.classList.add('value-accent');
            preview.style.color = '';
            preview.textContent = `${projectName}-pull-sheet.xlsx`;
            return;
        }

        if (format === 'resolume-xml') {
            // v0.11.0: the preview keeps .value-accent. It is the only thing in
            // its box and the accent reads as HIGHLIGHT there, unlike
            // Pixels/Port and Panels/Port, which share a box with error
            // colours and so use .value-normal. Error colours stay inline.
            preview.classList.add('value-accent');
            preview.style.color = '';
            preview.textContent = `${projectName}.xml`;
            return;
        }

        if (views.length === 0) {
            preview.textContent = '(Select at least one view)';
            preview.classList.remove('value-accent');
            preview.style.color = '#ff6b6b';
            return;
        }

        preview.classList.add('value-accent');
        preview.style.color = '';

        // Slice 11: factor selected canvases into the preview. Each
        // (canvas, view) combo is one file (PNG/PSD) or one page (PDF).
        const canvasIds = (typeof this.getSelectedExportCanvasIds === 'function')
            ? this.getSelectedExportCanvasIds() : [null];
        if (canvasIds.length === 0) {
            preview.textContent = '(Select at least one canvas)';
            preview.classList.remove('value-accent');
            preview.style.color = '#ff6b6b';
            return;
        }
        const projectCanvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        // v0.8.7.5: per-canvas Name inputs in the export modal are
        // prefilled with the canvas's stored name and the user can edit
        // them in place (same pattern as the view-suffix inputs). The
        // value is filename-only, the canvas's stored name in the
        // sidebar / project is untouched. Empty falls back to canvas.name.
        const nameByCid = {};
        document.querySelectorAll('.export-canvas-name-override').forEach(inp => {
            const cid = inp.dataset.canvasId;
            const v = (inp.value || '').trim();
            if (cid && v) nameByCid[cid] = v;
        });
        const canvasNameOf = (cid) => {
            if (!cid) return '';
            const c = projectCanvases.find(x => x && x.id === cid);
            const raw = nameByCid[cid] || (c && c.name) || 'Canvas';
            return this.sanitizeFilename(raw);
        };
        const multiCanvas = canvasIds.length > 1 && canvasIds[0] !== null;
        const buildName = (cid, suffix, ext) => {
            const cname = canvasNameOf(cid);
            return (multiCanvas && cname)
                ? `${projectName}_${suffix}_${cname}.${ext}`
                : `${projectName}_${suffix}.${ext}`;
        };

        // v0.8.7.1: read per-canvas perspective dropdowns so the filename
        // preview reflects the user's modal override, not the underlying
        // canvas state. Build a synthetic canvas object per cid with the
        // override applied for the suffix calculation.
        const overrideByCid = {};
        document.querySelectorAll('.export-canvas-perspective').forEach(sel => {
            const cid = sel.dataset.canvasId;
            const kind = sel.dataset.kind;
            if (!cid || !kind) return;
            if (!overrideByCid[cid]) overrideByCid[cid] = {};
            const key = kind === 'data' ? 'data_flow_perspective' : 'power_perspective';
            overrideByCid[cid][key] = (sel.value === 'back') ? 'back' : 'front';
        });
        const canvasForSuffix = (cid) => {
            if (!cid) return null;
            const c = (this.project && this.project.canvases || []).find(x => x && x.id === cid);
            if (!c) return null;
            return Object.assign({}, c, overrideByCid[cid] || {});
        };

        if (format === 'pdf') {
            const pageCount = canvasIds.length * views.length;
            preview.textContent = `${projectName}.pdf (${pageCount} page${pageCount > 1 ? 's' : ''})`;
        } else if (format === 'psd' || format === 'png') {
            const ext = format;
            const lines = [];
            for (const cid of canvasIds) {
                const cForSuffix = canvasForSuffix(cid);
                for (const v of views) {
                    const suffix = this.getExportSuffixForView(v, suffixes, viewNames, cForSuffix);
                    lines.push(buildName(cid, suffix, ext));
                }
            }
            if (lines.length === 1) preview.textContent = lines[0];
            else preview.innerHTML = lines.join('<br>');
        }
    }

    getExportViewNames() {
        return {
            'pixel-map': 'Pixel Map',
            'cabinet-id': 'Cabinet Map',
            'show-look': 'Show Look',
            'data-flow': 'Data Map',
            'power': 'Power Map'
        };
    }

    getExportSuffixDefaults() {
        return {
            'pixel-map': 'Pixel Map',
            'cabinet-id': 'Cabinet Map',
            'show-look': 'Show Look',
            'data-flow': 'Data Map',
            'power': 'Power Map'
        };
    }

    loadExportSuffixesToUI() {
        const defaults = this.getExportSuffixDefaults();
        let saved = {};
        try {
            saved = JSON.parse(localStorage.getItem('exportSuffixes') || '{}');
        } catch (e) {
            saved = {};
        }
        const apply = (id, key) => {
            const el = document.getElementById(id);
            if (!el) return;
            const val = typeof saved[key] === 'string' ? saved[key] : defaults[key];
            el.value = val || '';
        };
        apply('export-suffix-pixel-map', 'pixel-map');
        apply('export-suffix-cabinet-id', 'cabinet-id');
        apply('export-suffix-show-look', 'show-look');
        apply('export-suffix-data-flow', 'data-flow');
        apply('export-suffix-power', 'power');
    }

    saveExportSuffixesFromUI() {
        const suffixes = this.getExportSuffixesFromUI();
        localStorage.setItem('exportSuffixes', JSON.stringify(suffixes));
    }

    getExportSuffixesFromUI() {
        const defaults = this.getExportSuffixDefaults();
        const read = (id, key) => {
            const el = document.getElementById(id);
            if (!el) return defaults[key];
            return (el.value || '').trim();
        };
        return {
            'pixel-map': read('export-suffix-pixel-map', 'pixel-map'),
            'cabinet-id': read('export-suffix-cabinet-id', 'cabinet-id'),
            'show-look': read('export-suffix-show-look', 'show-look'),
            'data-flow': read('export-suffix-data-flow', 'data-flow'),
            'power': read('export-suffix-power', 'power')
        };
    }

    getExportSuffixForView(view, suffixes, viewNames, canvas) {
        const raw = (suffixes && typeof suffixes[view] === 'string') ? suffixes[view].trim() : '';
        let suffix = raw || viewNames[view];
        // v0.8.6: perspective is per-canvas. When exporting a specific
        // canvas, read THAT canvas's perspective (not the project-root
        // legacy field). For legacy single-canvas projects (canvas=null)
        // fall back to the project root field.
        const perspectiveKey = view === 'data-flow' ? 'data_flow_perspective'
            : view === 'power' ? 'power_perspective'
            : null;
        if (perspectiveKey) {
            const value = canvas
                ? canvas[perspectiveKey]
                : (this.project && this.project[perspectiveKey]);
            if (value === 'back' && !/_back$/i.test(suffix)) {
                suffix = `${suffix}_back`;
            }
        }
        return suffix;
    }
    
    // Export Resolume Arena Advanced Output XML
    async exportResolumeXml(projectName) {
        const rasterW = parseInt(document.getElementById('toolbar-raster-width').value) || 3840;
        const rasterH = parseInt(document.getElementById('toolbar-raster-height').value) || 2160;

        const response = await fetch('/api/export/resolume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                raster_width: rasterW,
                raster_height: rasterH
            })
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || 'Resolume export failed');
        }
        const blob = await response.blob();
        await this.saveBlobWithPicker(blob, `${projectName}.xml`, 'application/xml');
        sendClientLog('export_resolume_complete', { projectName, rasterW, rasterH });
    }

    /**
     * Open and fully initialize the export modal.
     *
     * All export entry points route through this method so the toolbar and
     * File menu cannot drift apart as modal options evolve.
     */
    openExportModal(format = null) {
        const modal = document.getElementById('export-modal');
        if (!modal) return;

        const formatSelect = document.getElementById('export-format');
        if (formatSelect && format) {
            formatSelect.value = format;
        }

        modal.style.display = 'block';
        document.getElementById('export-name').value =
            this.project.name || 'Untitled Project';
        this.loadExportSuffixesToUI();
        this.populateExportCanvasesList();

        // Re-evaluate format-specific controls such as the PSD scale row.
        if (formatSelect) {
            formatSelect.dispatchEvent(new Event('change'));
        }
        if (typeof this.syncPullSheetControls === 'function') this.syncPullSheetControls();
        // The Binder block's palette, maps and sheet ticks start from the
        // preferences each time the dialog OPENS - not on every later
        // sync, which would undo what was ticked in this dialog.
        this._binderSeedFromPrefs = true;
        if (typeof this.syncBinderControls === 'function') this.syncBinderControls();
        this.updateExportPreview();
    }

    // Perform export using client-side canvas capture at 1:1 pixel scale
    /**
     * Slice 11: build the dynamic Canvases checklist in the export modal.
     * Visible canvases are checked, hidden ones unchecked but still
     * selectable. Each row gets a stable id so the export-confirm handler
     * can read them.
     */
    populateExportCanvasesList() {
        const list = document.getElementById('export-canvases-list');
        if (!list) return;
        list.innerHTML = '';
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        if (canvases.length === 0) {
            // Legacy / pre-Slice-1 project: no canvas list. Show a static
            // placeholder so the user understands what's being exported.
            const note = document.createElement('div');
            note.style.cssText = 'font-size:11px;color:#888;padding:6px 0;';
            note.textContent = 'Single-canvas project, entire workspace will be exported.';
            list.appendChild(note);
            return;
        }
        canvases.forEach((c, idx) => {
            if (!c || !c.id) return;
            const row = document.createElement('div');
            row.className = 'export-view-row';
            const isHidden = c.visible === false;
            // v0.8.7.5: col-1 of the row holds checkbox + swatch + an
            // editable canvas-name input (replacing the previous static
            // name span). Editing the input changes the canvas segment
            // in the exported filename only, the canvas's stored name
            // in the sidebar / project file is untouched. Using a div
            // (not a label) so clicking the input doesn't toggle the
            // checkbox.
            const labelCol = document.createElement('div');
            labelCol.className = 'export-view-label';
            labelCol.style.gap = '6px';
            const swatch = document.createElement('span');
            swatch.style.cssText = `display:inline-block;width:10px;height:10px;border-radius:2px;background:${c.color || '#4A90E2'};flex:none;`;
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = !isHidden;
            checkbox.dataset.canvasId = c.id;
            checkbox.className = 'export-canvas-checkbox';
            checkbox.addEventListener('change', () => this.updateExportPreview());
            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.className = 'export-canvas-name-override';
            nameInput.dataset.canvasId = c.id;
            nameInput.value = c.name || `Canvas ${idx + 1}`;
            nameInput.title = 'Edit to rename this canvas in the exported filename. Does NOT rename the canvas in the project.';
            // Inline override so the input stays compact inside the
            // 140px label column and doesn't pick up the chunky 8px
            // padding from `.export-view-row input[type="text"]`.
            nameInput.style.cssText = `flex:1;min-width:60px;padding:2px 6px;font-size:12px;background:#222;color:${isHidden ? '#888' : '#ddd'};border:1px solid #444;border-radius:3px;`;
            nameInput.addEventListener('input', () => this.updateExportPreview());
            labelCol.appendChild(checkbox);
            labelCol.appendChild(swatch);
            labelCol.appendChild(nameInput);
            if (isHidden) {
                const hiddenTag = document.createElement('span');
                hiddenTag.textContent = '(hidden)';
                hiddenTag.style.cssText = 'color:#888;font-size:11px;flex:none;';
                labelCol.appendChild(hiddenTag);
            }
            row.appendChild(labelCol);
            // v0.8.6: per-canvas perspective overrides for Data + Power
            // exports. Default to whatever the canvas currently has.
            // These dropdowns set/restore the canvas's perspective during
            // export only, they don't persist back to the project.
            const persp = document.createElement('div');
            persp.style.cssText = 'display:flex;gap:8px;margin-left:22px;font-size:11px;color:#aaa;align-items:center;';
            const mkSel = (kind, current) => {
                const wrap = document.createElement('span');
                wrap.style.cssText = 'display:inline-flex;gap:4px;align-items:center;';
                const lbl = document.createElement('span');
                lbl.textContent = kind === 'data' ? 'Data:' : 'Power:';
                const sel = document.createElement('select');
                sel.className = `export-canvas-perspective export-canvas-perspective-${kind}`;
                sel.dataset.canvasId = c.id;
                sel.dataset.kind = kind;
                sel.style.cssText = 'background:#222;color:#ddd;border:1px solid #444;border-radius:3px;padding:1px 4px;font-size:11px;';
                ['front', 'back'].forEach(v => {
                    const o = document.createElement('option');
                    o.value = v;
                    o.textContent = v === 'front' ? 'Front' : 'Back';
                    if (v === current) o.selected = true;
                    sel.appendChild(o);
                });
                // v0.8.7.1: refresh filename preview when this dropdown
                // changes so the user sees _back / no-suffix instantly.
                sel.addEventListener('change', () => this.updateExportPreview());
                wrap.appendChild(lbl);
                wrap.appendChild(sel);
                return wrap;
            };
            const curData = (c.data_flow_perspective === 'back') ? 'back' : 'front';
            const curPower = (c.power_perspective === 'back') ? 'back' : 'front';
            persp.appendChild(mkSel('data', curData));
            persp.appendChild(mkSel('power', curPower));
            row.appendChild(persp);
            list.appendChild(row);
        });
    }

    /**
     * Slice 11: read the canvas checkboxes back. Returns array of canvas
     * ids in their project.canvases order. Returns [null] for legacy
     * projects so performExport falls into single-canvas mode.
     */
    getSelectedExportCanvasIds() {
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        if (canvases.length === 0) return [null];
        const checked = new Set();
        document.querySelectorAll('.export-canvas-checkbox').forEach(cb => {
            if (cb.checked && cb.dataset.canvasId) checked.add(cb.dataset.canvasId);
        });
        // Preserve project.canvases order in the output.
        return canvases.filter(c => c && checked.has(c.id)).map(c => c.id);
    }

    /**
     * Slice 11: multi-canvas-aware export. Iterates canvases × views,
     * temporarily hiding the OTHER canvases per pass and translating the
     * render so each canvas becomes its own export image at its native
     * raster size. canvasIds=[null] is the legacy single-canvas path.
     */
    async performExport(projectName, format, views, canvasIds) {
        const viewNames = this.getExportViewNames();
        const suffixes = this.getExportSuffixesFromUI();

        // Store current renderer state.
        const originalViewMode = window.canvasRenderer.viewMode;
        const originalZoom = window.canvasRenderer.zoom;
        const originalPanX = window.canvasRenderer.panX;
        const originalPanY = window.canvasRenderer.panY;
        const originalActiveCanvasId = (this.project && this.project.active_canvas_id) || null;
        const mainCanvas = window.canvasRenderer.canvas;
        const originalCtx = window.canvasRenderer.ctx;

        const transparentBg = document.getElementById('export-transparent-bg');
        const useTransparentBg = transparentBg && transparentBg.checked;

        // Snapshot every canvas's visibility so we can flip them per pass
        // and restore at the end. Legacy projects skip this entirely.
        const canvases = (this.project && Array.isArray(this.project.canvases))
            ? this.project.canvases : [];
        const visibilitySnapshot = canvases.map(c => ({ id: c.id, visible: c.visible }));
        // v0.8.6: snapshot every canvas's perspective so we can apply the
        // export-dialog overrides per pass and restore at the end. Read
        // the per-canvas perspective dropdowns once up-front.
        const perspectiveSnapshot = canvases.map(c => ({
            id: c.id,
            data_flow_perspective: c.data_flow_perspective,
            power_perspective: c.power_perspective,
        }));
        const perspectiveOverrides = {};
        document.querySelectorAll('.export-canvas-perspective').forEach(sel => {
            const cid = sel.dataset.canvasId;
            const kind = sel.dataset.kind;
            if (!cid || !kind) return;
            if (!perspectiveOverrides[cid]) perspectiveOverrides[cid] = {};
            const key = kind === 'data' ? 'data_flow_perspective' : 'power_perspective';
            perspectiveOverrides[cid][key] = (sel.value === 'back') ? 'back' : 'front';
        });
        // Apply overrides to every canvas BEFORE the per-canvas/per-view
        // loop so each render call sees the user's chosen perspective.
        canvases.forEach(c => {
            const o = perspectiveOverrides[c.id];
            if (!o) return;
            if (o.data_flow_perspective) c.data_flow_perspective = o.data_flow_perspective;
            if (o.power_perspective) c.power_perspective = o.power_perspective;
        });
        // v0.8.7.5: per-canvas Name inputs from the export modal. Each is
        // prefilled with the canvas's stored name and the user can edit
        // in place. Filename-only, never written back to the canvas
        // object. Empty entries fall back to canvas.name below.
        const nameOverridesByCid = {};
        document.querySelectorAll('.export-canvas-name-override').forEach(inp => {
            const cid = inp.dataset.canvasId;
            const v = (inp.value || '').trim();
            if (cid && v) nameOverridesByCid[cid] = v;
        });

        const exportCanvas = document.createElement('canvas');
        const exportCtx = exportCanvas.getContext('2d', { alpha: useTransparentBg });
        window.canvasRenderer.canvas = exportCanvas;
        window.canvasRenderer.ctx = exportCtx;
        // v0.8.7: optional resolution-scale multiplier (PSD only). Native
        // scale = 1 (existing behavior for PNG/PDF). Higher values render
        // PSD at scale × native raster so vector content (panels, labels,
        // arrows, text) stays crisp at higher zoom. PNG/PDF
        // skip the scale (their use cases don't benefit and the larger
        // file sizes would surprise users).
        // The actual scale used is clamped per pass to keep PSD dimensions
        // under PSD format's 30000×30000 hard limit (PSB is bigger but
        // pytoshop only writes classic PSD). Computed inside the loop.
        const scaleSel = document.getElementById('export-scale');
        const requestedScale = scaleSel ? Math.max(1, Math.min(8, Number(scaleSel.value) || 1)) : 1;
        // v0.8.7: PSD format max dimension is 30000px, but browsers cap
        // 2D canvas at much lower (Chrome: 16384, Safari/FF higher). The
        // toDataURL on an oversized canvas silently returns "data:," and
        // the server can't parse the empty image. Use 16000 to stay
        // within Chrome's hard cap with a safety margin.
        const PSD_MAX_DIM = 16000;
        let scaleClampedAnywhere = false;
        window.canvasRenderer.exportMode = true;
        window.canvasRenderer.exportTransparentBg = useTransparentBg;

        const renderedItems = [];
        const multiCanvas = canvasIds.length > 1 && canvasIds[0] !== null;

        try {
            for (const cid of canvasIds) {
                // Resolve target canvas. cid===null means legacy single-
                // canvas: use project-root raster fields, no workspace shift.
                const targetCanvas = cid
                    ? canvases.find(c => c && c.id === cid)
                    : null;
                if (cid && !targetCanvas) continue;

                if (cid) {
                    // Make ONLY this canvas visible during the per-view loop
                    // so other canvases' layers don't bleed into the export
                    // (handles overlap, cross-canvas labels, etc.). Active
                    // canvas swap drives the rasterWidth/Height accessors
                    // that decide export-canvas dimensions per view.
                    canvases.forEach(c => { c.visible = (c.id === cid); });
                    this.project.active_canvas_id = cid;
                }

                for (const view of views) {
                    window.canvasRenderer.viewMode = view;
                    // rasterWidth/Height read from the active canvas (Slice 6)
                    // and pick show_raster_* automatically when view is
                    // show-look (so Show Look exports at its own resolution).
                    const rasterWidth = window.canvasRenderer.rasterWidth || 1920;
                    const rasterHeight = window.canvasRenderer.rasterHeight || 1080;
                    // v0.8.7: per-pass PSD scale, clamped so the resulting
                    // image dimensions stay under PSD's 30000×30000 hard
                    // limit. PNG/PDF always run at 1x. If the user picked
                    // 8x but the canvas is too big, we silently use the
                    // largest scale that fits and surface a single status
                    // message after the export completes.
                    let exportScale = (format === 'psd') ? requestedScale : 1;
                    if (exportScale > 1) {
                        const maxScaleByWidth = Math.floor(PSD_MAX_DIM / rasterWidth);
                        const maxScaleByHeight = Math.floor(PSD_MAX_DIM / rasterHeight);
                        const maxSafe = Math.max(1, Math.min(maxScaleByWidth, maxScaleByHeight));
                        if (exportScale > maxSafe) {
                            exportScale = maxSafe;
                            scaleClampedAnywhere = true;
                        }
                    }
                    window.canvasRenderer.zoom = exportScale;
                    exportCanvas.width = rasterWidth * exportScale;
                    exportCanvas.height = rasterHeight * exportScale;
                    // Translate the workspace so this canvas's top-left
                    // (workspace_x, workspace_y) lands at (0, 0) in the
                    // export canvas. Legacy: pan to 0,0.
                    // v0.8.5.3 fix: Show Look / Data / Power views render
                    // each canvas at its show_workspace_x/y (when set) -
                    // the export pan must match or the captured PNG comes
                    // out shifted and missing layers that live at
                    // negative-relative show positions.
                    const isShowExport = (view === 'show-look' || view === 'data-flow' || view === 'power');
                    let wsx = 0, wsy = 0;
                    if (targetCanvas) {
                        if (isShowExport) {
                            wsx = (targetCanvas.show_workspace_x == null
                                ? (targetCanvas.workspace_x || 0)
                                : (targetCanvas.show_workspace_x || 0));
                            wsy = (targetCanvas.show_workspace_y == null
                                ? (targetCanvas.workspace_y || 0)
                                : (targetCanvas.show_workspace_y || 0));
                        } else {
                            wsx = targetCanvas.workspace_x || 0;
                            wsy = targetCanvas.workspace_y || 0;
                        }
                    }
                    // v0.8.7: panX/panY are in screen pixels. With zoom =
                    // exportScale the workspace origin needs to land at
                    // -wsx*scale screen pixels for the canvas's top-left
                    // to render at (0, 0) of the export image.
                    window.canvasRenderer.panX = -wsx * exportScale;
                    window.canvasRenderer.panY = -wsy * exportScale;

                    window.canvasRenderer.render();

                    const dataUrl = exportCanvas.toDataURL('image/png');
                    const suffix = this.getExportSuffixForView(view, suffixes, viewNames, targetCanvas);
                    // v0.8.7.5: per-canvas Name input from the export modal
                    // takes precedence over targetCanvas.name when present.
                    // Empty / whitespace = fall back to canvas name.
                    const overrideRaw = nameOverridesByCid[cid];
                    const canvasName = targetCanvas
                        ? this.sanitizeFilename(overrideRaw || targetCanvas.name || 'Canvas')
                        : null;
                    // Filename: include canvas token only when exporting
                    // more than one canvas (v0.8.7.4). Single-canvas
                    // exports keep `Project_View.ext`; the Name input on
                    // a single-canvas export only matters if you happen
                    // to also have a hidden sibling canvas selected.
                    const fileBase = (multiCanvas && canvasName)
                        ? `${projectName}_${suffix}_${canvasName}`
                        : `${projectName}_${suffix}`;
                    // PDF page label includes canvas + view when multi.
                    const pdfLabel = (multiCanvas && canvasName)
                        ? `${canvasName}, ${suffix}`
                        : suffix;
                    renderedItems.push({
                        canvasId: cid,
                        canvasName,
                        view,
                        suffix,
                        fileBase,
                        pdfLabel,
                        dataUrl,
                        width: rasterWidth * exportScale,
                        height: rasterHeight * exportScale,
                        scale: exportScale,
                    });
                }
            }
        } finally {
            // Restore canvas visibility, perspective, active canvas, renderer state.
            visibilitySnapshot.forEach(s => {
                const c = canvases.find(c => c && c.id === s.id);
                if (c) c.visible = s.visible;
            });
            perspectiveSnapshot.forEach(s => {
                const c = canvases.find(c => c && c.id === s.id);
                if (!c) return;
                c.data_flow_perspective = s.data_flow_perspective;
                c.power_perspective = s.power_perspective;
            });
            if (this.project) this.project.active_canvas_id = originalActiveCanvasId;
            window.canvasRenderer.canvas = mainCanvas;
            window.canvasRenderer.ctx = originalCtx;
            window.canvasRenderer.exportMode = false;
            window.canvasRenderer.exportTransparentBg = false;
            window.canvasRenderer.viewMode = originalViewMode;
            window.canvasRenderer.zoom = originalZoom;
            window.canvasRenderer.panX = originalPanX;
            window.canvasRenderer.panY = originalPanY;
            window.canvasRenderer.render();
        }

        // v0.8.7: notify the user if any pass had to clamp the requested
        // PSD scale to fit PSD's 30000×30000 dimension limit. We don't
        // block, we just report the actual scale used so the file lands
        // and the user knows.
        if (scaleClampedAnywhere) {
            const usedScales = [...new Set(renderedItems.map(i => i.scale))].sort((a, b) => a - b);
            const status = document.getElementById('status-message');
            if (status) {
                status.textContent = `PSD scale reduced (max ${usedScales[usedScales.length - 1]}x), PSD format max is 30000px`;
                setTimeout(() => { if (status.textContent.startsWith('PSD scale')) status.textContent = 'Ready'; }, 6000);
            }
            sendClientLog && sendClientLog('export_psd_scale_clamped', {
                requested: requestedScale,
                used: usedScales,
            });
        }

        // Dispatch to format-specific writer. Multi-canvas just means
        // more items, each writer already loops over them.
        if (format === 'png') {
            await this.downloadRenderedPNGs(renderedItems);
        } else if (format === 'pdf') {
            await this.downloadAsPdf(projectName, renderedItems);
        } else if (format === 'psd') {
            await this.downloadAsPsd(projectName, renderedItems);
        }
    }
    
    dataUrlToBlob(dataUrl) {
        const [meta, base64] = dataUrl.split(',');
        const contentType = meta.split(':')[1].split(';')[0];
        const byteCharacters = atob(base64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        return new Blob([new Uint8Array(byteNumbers)], { type: contentType });
    }

    downloadBlob(blob, filename) {
        const link = document.createElement('a');
        link.download = filename;
        link.href = URL.createObjectURL(blob);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Returns { path, cancelled, unavailable } - the same contract as
    // nativeSelectDirectory, and for the same reason.
    //
    // This used to return a bare path-or-null, and the caller read null as
    // "the user cancelled" and stopped. That was survivable while the host at
    // a LAN address was misclassified as remote, because the native path was
    // skipped entirely and the file still arrived as a browser download.
    // Once that misclassification was fixed, the same null began meaning
    // "the dialog could not open" - and a failed dialog silently ABANDONED
    // the export. No file anywhere, no message. Worse than the bug it
    // replaced. Cancel must stop; unavailable must fall back.
    async nativeSelectSavePath(suggestedName) {
        let data = null;
        try {
            const response = await fetch('/api/native-dialog/save-file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ suggested_name: suggestedName })
            });
            if (!response.ok) return { path: null, cancelled: false, unavailable: true };
            data = await response.json();
        } catch (err) {
            return { path: null, cancelled: false, unavailable: true };
        }
        if (data && data.ok && data.path) {
            return { path: data.path, cancelled: false, unavailable: false };
        }
        return {
            path: null,
            cancelled: !!(data && data.cancelled),
            unavailable: !(data && data.cancelled),
        };
    }


    // Only the HOST is warned about a missing folder chooser.
    //
    // On the host, a chooser is what should happen, so failing to get one is a
    // real fault and the reason is worth surfacing. On a machine connected
    // over the network, a plain download IS the expected behaviour - the files
    // land on that machine, which is the point - so a warning there would be
    // crying wolf about something working as intended.
    //
    // (Browsers only expose folder access over a SECURE connection, so a
    // remote client on plain http:// could not be given a chooser anyway.)
    _noFolderChooserMessage() {
        if (!this.isLocalConnection()) return null;
        return 'Could not open the folder chooser, so the files were saved to '
            + 'your browser\'s downloads folder instead. The reason is in '
            + 'Help > Show Logs.';
    }

    // Returns { path, cancelled, unavailable }.
    //
    // The two failure modes MUST stay apart. `cancelled` means the user
    // dismissed the folder chooser and nothing should be written;
    // `unavailable` means the dialog could not be opened at all and the
    // browser download is the only way to get the files out. They used to
    // collapse into a bare null, so pressing Cancel on an export still dumped
    // every file into Downloads.
    async nativeSelectDirectory() {
        let data = null;
        try {
            const response = await fetch('/api/native-dialog/select-directory', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            if (!response.ok) return { path: null, cancelled: false, unavailable: true };
            data = await response.json();
        } catch (err) {
            return { path: null, cancelled: false, unavailable: true };
        }
        if (data && data.ok && data.path) {
            return { path: data.path, cancelled: false, unavailable: false };
        }
        return {
            path: null,
            cancelled: !!(data && data.cancelled),
            // Anything that is not an explicit cancel is treated as the dialog
            // being unavailable, so an unexpected shape still yields files.
            unavailable: !(data && data.cancelled),
        };
    }

    async nativeWriteFile(path, blob) {
        // v0.8.7: send the blob as raw multipart bytes instead of a base64
        // data URI. The old JSON path JSON.stringify-ed a ~36MB base64
        // string for a 26MB PSD, which blows up to "out of memory" or
        // sends an empty body on some browsers (we saw `has_data: false`
        // in server logs for 8x PSD exports). FormData streams the blob
        // directly without a giant string allocation.
        const fd = new FormData();
        fd.append('path', path);
        fd.append('file', blob);
        const response = await fetch('/api/native-dialog/write-file', {
            method: 'POST',
            body: fd,
        });
        if (!response.ok) return false;
        const data = await response.json();
        return !!(data && data.ok);
    }

    // Is this browser running ON the machine hosting the app?
    //
    // The hostname alone cannot answer that. When the launcher binds the
    // server to a network interface so the drawing can be opened from another
    // machine, the HOST's own browser also reaches it at that LAN address -
    // and http://192.168.2.5:8050 looks exactly the same whether it is this
    // machine or a laptop across the room. Judging by hostname concluded
    // "remote", so Export skipped the folder chooser and dropped the files
    // into the browser's downloads folder with no way to choose where.
    //
    // Only the server can tell, by comparing the caller's address to its own,
    // so ask it once and remember the answer.
    isLocalConnection() {
        if (this._isHostClient !== undefined && this._isHostClient !== null) {
            return this._isHostClient;
        }
        // Not probed yet: fall back to the address test, which is right
        // whenever the app is opened at localhost (the usual case).
        const host = window.location.hostname;
        return host === 'localhost' || host === '127.0.0.1' || host === '::1';
    }

    // Memoised probe. Safe to call on every export; only the first one
    // reaches the server.
    async ensureHostCapability() {
        if (this._hostCapabilityProbe) return this._hostCapabilityProbe;
        this._hostCapabilityProbe = (async () => {
            try {
                const r = await fetch('/api/native-dialog/available');
                // 403 is the server saying "you are not this machine" - a real
                // answer, not a failure.
                this._isHostClient = r.ok;
            } catch (err) {
                // Server unreachable: leave it unknown so isLocalConnection
                // falls back to the address test rather than locking the host
                // out of its own dialogs - and DROP the memo, so the next
                // export asks again. Caching a transient network blip would
                // reinstate the original bug for the rest of the session with
                // no way to recover short of a reload.
                this._isHostClient = null;
                this._hostCapabilityProbe = null;
            }
            sendClientLog('host_capability_probe', {
                isHost: this._isHostClient,
                hostname: window.location.hostname,
            });
            return this._isHostClient;
        })();
        return this._hostCapabilityProbe;
    }

    browserDownload(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 5000);
        sendClientLog('save_blob_browser_download', { filename });
    }

    async saveBlobWithPicker(blobOrFn, filename, mimeType) {
        await this.ensureHostCapability();
        // Sanitize so a project name with "/" or other illegal chars doesn't
        // get rejected by showSaveFilePicker / OS file APIs.
        filename = this.sanitizeFilename(filename);
        // blobOrFn can be a Blob OR an async function returning one. Lazy-blob
        // form lets the caller defer expensive serialization (e.g. stringifying
        // a 1MB project) until AFTER showSaveFilePicker resolves, keeping the
        // user-activation gesture fresh for createWritable. See bug fix for
        // 0-byte JSON saves on large multi-canvas projects.
        const resolveBlob = async () => (typeof blobOrFn === 'function' ? await blobOrFn() : blobOrFn);
        // 1. Try the File System Access API (Chrome/Edge on secure contexts).
        //    Skip on localhost, we have a better server-side native dialog
        //    available that doesn't break on cloud-synced folders (Nextcloud,
        //    iCloud, Dropbox, OneDrive). Chrome's createWritable rejects with
        //    NotAllowedError when the target lives under a sync agent's xattrs,
        //    which produced 0-byte saves before this guard.
        if (window.showSaveFilePicker && !this.isLocalConnection()) {
            try {
                sendClientLog('save_blob_picker_start', { filename, mimeType });
                const ext = filename.split('.').pop() || '';
                const handle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{ description: 'File', accept: { [mimeType]: [`.${ext}`] } }]
                });
                const blob = await resolveBlob();
                const writable = await handle.createWritable();
                await writable.write(blob);
                await writable.close();
                sendClientLog('save_blob_picker_success', { filename });
                return;
            } catch (err) {
                if (err && err.name === 'AbortError') return;
                // NotAllowedError on createWritable: Chrome already created the
                // empty file via the picker but lost the user-activation needed
                // to write to it. Fall through to native/browser fallback so we
                // don't leave the user with a 0-byte file and nothing else.
                sendClientLog('save_blob_picker_failed', {
                    filename,
                    name: err && err.name,
                    message: err && err.message
                });
                // Try native dialog (Mac/Win/Linux), opens a fresh dialog so
                // we get our own gesture-bound path. If unavailable, use
                // browserDownload as last resort.
            }
        }
        // 2. Use native server-side dialog (opens on the host machine).
        // ONLY when this client IS the host: a remote client's save must land
        // on the remote machine (browser download below), not on the server.
        try {
            if (!this.isLocalConnection()) throw new Error('remote client: skip host dialog');
            const picked = await this.nativeSelectSavePath(filename);
            if (picked.cancelled) {
                // The user said no. Stop - saving anyway ignores them.
                sendClientLog('save_blob_native_dialog_cancelled', { filename });
                if (typeof this._toast === 'function') {
                    this._toast('Export cancelled - nothing was saved.', false, 4000);
                }
                return;
            }
            const savePath = picked.path;
            if (!savePath) {
                // Dialog could not open. Fall through to the browser download
                // rather than lose the export.
                sendClientLog('save_blob_native_dialog_unavailable', { filename });
                throw new Error('native dialog unavailable');
            }
            sendClientLog('save_blob_native_dialog_selected', { filename, savePath });
            const blob = await resolveBlob();
            const ok = await this.nativeWriteFile(savePath, blob);
            if (ok) {
                sendClientLog('save_blob_native_dialog_success', { filename, savePath });
                return;
            }
            sendClientLog('save_blob_native_dialog_write_failed', { filename, savePath });
        } catch (err) {
            sendClientLog('save_blob_native_dialog_error', { filename, message: err.message });
        }
        // 3. Last resort: trigger a normal browser download so the user always
        // ends up with a file (even if both the picker and the native dialog
        // failed). Better than silently leaving a 0-byte stub on disk.
        try {
            const blob = await resolveBlob();
            this.browserDownload(blob, filename);
        } catch (err) {
            sendClientLog('save_blob_browser_download_error', { filename, message: err && err.message });
        }
    }

    sanitizeFilename(name) {
        // Strip path separators and characters Windows/macOS reject in filenames.
        // Also collapse leading/trailing dots & whitespace which Windows rejects.
        if (!name) return 'untitled';
        const cleaned = String(name)
            .replace(/[\\/:*?"<>|\x00-\x1F]/g, '_')
            .replace(/^[\s.]+|[\s.]+$/g, '')
            .trim();
        return cleaned || 'untitled';
    }

    async saveMultipleFiles(files) {
        // Ask the server whether we are the host BEFORE deciding how to save.
        await this.ensureHostCapability();
        // Sanitize each filename so path separators (e.g. "/" in a project name)
        // don't break getFileHandle() with "Name is not allowed."
        files = files.map(f => ({ ...f, filename: this.sanitizeFilename(f.filename) }));
        sendClientLog('save_multiple_files_start', {
            count: files.length,
            hasDirectoryPicker: !!window.showDirectoryPicker,
            hasSaveFilePicker: !!window.showSaveFilePicker
        });
        // v0.8: same Chrome activation issue we hit on JSON saves, when
        // the user is on localhost (this Flask app), the multi-canvas export
        // burns the user-gesture token rendering all the canvases between
        // showDirectoryPicker resolving and the per-file getFileHandle/
        // createWritable calls. Chrome rejects with NotAllowedError and we
        // get zero files on disk. Skip the FS Access API entirely on
        // localhost and use the native server-side directory dialog, which
        // doesn't have this restriction.
        if (window.showDirectoryPicker && !this.isLocalConnection()) {
            try {
                const dirHandle = await window.showDirectoryPicker();
                for (const file of files) {
                    const handle = await dirHandle.getFileHandle(file.filename, { create: true });
                    const writable = await handle.createWritable();
                    await writable.write(file.blob);
                    await writable.close();
                }
                sendClientLog('save_multiple_files_directory_success', { count: files.length });
                return;
            } catch (err) {
                if (err && err.name === 'AbortError') return;
                sendClientLog('save_multiple_files_directory_failed', {
                    name: err && err.name, message: err && err.message
                });
                // fall through to native fallback so the user still gets files
            }
        }
        // Use native server-side directory picker (opens on the host machine).
        // Tried BEFORE per-file showSaveFilePicker because picking once is
        // far less work than N separate save dialogs. ONLY when this client
        // IS the host: a remote client's files must land on the remote
        // machine (per-file download below), not on the server.
        try {
            if (!this.isLocalConnection()) throw new Error('remote client: skip host dialog');
            const picked = await this.nativeSelectDirectory();
            if (picked.cancelled) {
                // The user said no. Saving to Downloads anyway is not a
                // fallback, it is ignoring them.
                sendClientLog('save_multiple_files_cancelled_by_user', { count: files.length });
                if (typeof this._toast === 'function') {
                    this._toast('Export cancelled - nothing was saved.', false, 4000);
                }
                return;
            }
            const targetDir = picked.path;
            if (targetDir) {
                for (const file of files) {
                    const filePath = `${targetDir.replace(/[\\/]$/, '')}/${file.filename}`;
                    const ok = await this.nativeWriteFile(filePath, file.blob);
                    if (!ok) {
                        sendClientLog('save_multiple_files_native_dialog_write_failed', { file: file.filename, filePath });
                        throw new Error(`Native write failed for ${file.filename}`);
                    }
                }
                sendClientLog('save_multiple_files_native_dialog_success', { count: files.length, directory: targetDir });
                return;
            }
            sendClientLog('save_multiple_files_native_dialog_unavailable', { count: files.length });
        } catch (err) {
            sendClientLog('save_multiple_files_native_dialog_error', { message: err.message });
        }
        // Last resort: per-file saveBlobWithPicker (multiple dialogs) or
        // browser download.
        //
        // Say so. Falling back silently is what made this look broken: the
        // folder chooser never appeared, the files landed in Downloads, and
        // nothing on screen connected the two. The reason itself is in the
        // app log (Help > Show Logs) under native_dialog_command_failed.
        const noChooserMsg = this._noFolderChooserMessage();
        if (noChooserMsg && typeof this._toast === 'function') {
            this._toast(noChooserMsg, true, 9000);
        }
        if (window.showSaveFilePicker) {
            for (const file of files) {
                const mimeType = file.blob && file.blob.type ? file.blob.type : 'application/octet-stream';
                await this.saveBlobWithPicker(file.blob, file.filename, mimeType);
            }
            sendClientLog('save_multiple_files_picker_success', { count: files.length });
            return;
        }
        for (const file of files) {
            try { this.browserDownload(file.blob, file.filename); } catch (_) {}
        }
    }

    async downloadRenderedPNGs(renderedViews) {
        if (renderedViews.length === 1) {
            const blob = this.dataUrlToBlob(renderedViews[0].dataUrl);
            await this.saveBlobWithPicker(blob, `${renderedViews[0].fileBase}.png`, 'image/png');
            return;
        }
        const files = renderedViews.map(v => ({
            filename: `${v.fileBase}.png`,
            blob: this.dataUrlToBlob(v.dataUrl)
        }));
        await this.saveMultipleFiles(files);
    }
    
    async downloadAsPdf(projectName, renderedViews) {
        // Slice 11: multi-canvas PDF. Each rendered item contributes one
        // page; the per-page name uses canvas + view when multi-canvas
        // (set on renderedItem.pdfLabel by performExport), else just the
        // view suffix. Server already handles variable per-page sizes.
        const response = await fetch('/api/export/pdf-from-images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                images: renderedViews.map(v => ({
                    name: v.pdfLabel || v.suffix,
                    data: v.dataUrl,
                    width: v.width || window.canvasRenderer.rasterWidth,
                    height: v.height || window.canvasRenderer.rasterHeight
                })),
                width: window.canvasRenderer.rasterWidth,
                height: window.canvasRenderer.rasterHeight
            })
        });

        if (!response.ok) throw new Error('Failed to create PDF');

        const blob = await response.blob();
        await this.saveBlobWithPicker(blob, `${projectName}.pdf`, 'application/pdf');
    }
    
    async downloadAsPsd(projectName, renderedViews) {
        const files = [];
        for (const view of renderedViews) {
            // Slice 11: when exporting per-canvas, only include layers from
            // that canvas in the PSD layer list, otherwise the PSD reports
            // sibling canvases' layers as if they were in this image.
            // Legacy / single-canvas: include every layer (canvasId is null).
            // v0.8.6.3: the rendered item stores the view string in
            // `view.view` (set by performExport), NOT `view.viewMode`. The
            // old isShowView check read the wrong field and was always
            // false, so PSD layer metadata always grouped by Pixel Map
            // canvas_id even for Show Look / Data / Power exports.
            const isShowView = view.view === 'show-look'
                || view.view === 'data-flow' || view.view === 'power';
            const psdLayers = this.project.layers.filter(l => {
                if (!view.canvasId) return true;
                // Show Look / Data / Power exports use the layer's
                // effective show canvas (show_canvas_id || canvas_id) so a
                // layer reassigned in Show Look exports under its show
                // canvas's PSD instead of its Pixel Map canvas's.
                const cid = (isShowView && l.show_canvas_id) ? l.show_canvas_id : l.canvas_id;
                return cid === view.canvasId;
            }).map(l => {
                const b = this.getLayerBounds(l);
                let x1 = b.x1, y1 = b.y1, x2 = b.x2, y2 = b.y2;
                // v0.8.6.3: in Show Look the rendered image places each
                // layer at panel + (showOffset - layer.offset). PSD layer
                // metadata must reflect that shift so layer rectangles in
                // the resulting PSD line up with the pixels.
                if (isShowView) {
                    const procX = Number(l.offset_x) || 0;
                    const procY = Number(l.offset_y) || 0;
                    const showX = (l.showOffsetX != null) ? Number(l.showOffsetX) : procX;
                    const showY = (l.showOffsetY != null) ? Number(l.showOffsetY) : procY;
                    const dx = showX - procX;
                    const dy = showY - procY;
                    x1 += dx; x2 += dx;
                    y1 += dy; y2 += dy;
                }
                // v0.8.7: when PSD export is rendered at scale > 1, the
                // image is scale × native; layer rectangles must scale to
                // match or they'll cover only the top-left corner.
                const s = Number(view.scale) || 1;
                if (s !== 1) {
                    x1 *= s; x2 *= s; y1 *= s; y2 *= s;
                }
                return {
                    name: l.name,
                    offset_x: x1,
                    offset_y: y1,
                    width: x2 - x1,
                    height: y2 - y1,
                    visible: l.visible
                };
            });
            const response = await fetch('/api/export/psd-from-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_name: projectName,
                    view_name: view.suffix,
                    image_data: view.dataUrl,
                    width: view.width || window.canvasRenderer.rasterWidth,
                    height: view.height || window.canvasRenderer.rasterHeight,
                    layers: psdLayers
                })
            });
            if (!response.ok) {
                // v0.8.7: surface the server error so the user sees what
                // actually went wrong (e.g. PSD dimension limits, OOM)
                // instead of a generic message.
                let detail = '';
                try {
                    const j = await response.clone().json();
                    if (j && j.error) detail = `: ${j.error}`;
                } catch (_) {}
                throw new Error(`Failed to create PSD${detail}`);
            }
            const blob = await response.blob();
            files.push({ filename: `${view.fileBase}.psd`, blob });
        }
        if (files.length === 1) {
            await this.saveBlobWithPicker(files[0].blob, files[0].filename, 'application/octet-stream');
            return;
        }
        await this.saveMultipleFiles(files);
    }

}

for (const k of Object.getOwnPropertyNames(_ExportIo.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ExportIo.prototype, k));
    }
}
