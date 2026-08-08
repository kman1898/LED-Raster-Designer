// app-colors: feature methods for LEDRasterApp (verbatim from the old
// monolithic app.js), attached to the prototype via the carrier class.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _Colors {
    // ── v0.8.7.8: Gradient overlay editor ──────────────────────────────
    // standard multi-stop gradient editor in the Colors panel. Edits
    // currentLayer.gradient* and mirrors the whole config onto every selected
    // screen layer (so multi-select bulk-applies, like the color pickers).

    _gradientLayer() {
        const l = this.currentLayer;
        return (l && (l.type || 'screen') === 'screen') ? l : null;
    }

    // Make sure a layer carries a complete gradient config before we edit it,
    // so partial edits don't leave undefined fields that get dropped across the
    // server round-trip (the layer may predate the gradient feature).
    _ensureGradientDefaults(layer) {
        if (!layer || (layer.type || 'screen') !== 'screen') return;
        if (layer.gradientEnabled == null) layer.gradientEnabled = false;
        if (!layer.gradientType) layer.gradientType = 'linear';
        if (!layer.gradientScope) layer.gradientScope = 'screen';
        if (layer.gradientPanelAlternate == null) layer.gradientPanelAlternate = false;
        if (layer.gradientRadialCenterX == null) layer.gradientRadialCenterX = 0.5;
        if (layer.gradientRadialCenterY == null) layer.gradientRadialCenterY = 0.5;
        if (layer.gradientRadialRadius == null) layer.gradientRadialRadius = 1;
        if (layer.gradientAngle == null) layer.gradientAngle = 0;
        if (layer.gradientOpacity == null) layer.gradientOpacity = 0.6;
        if (!layer.gradientBlend) layer.gradientBlend = 'normal';
        if (!Array.isArray(layer.gradientStops) || layer.gradientStops.length < 2) {
            layer.gradientStops = [{ pos: 0, color: '#1d9e75' }, { pos: 1, color: '#2145dc' }];
        }
    }

    // Apply a partial patch to the gradient config of every selected screen
    // layer (deep-cloning arrays so layers don't share references), re-render,
    // and optionally persist. Keeps currentLayer authoritative for the editor.
    _applyGradient(patch, isFinal) {
        this.applyToSelectedLayers(layer => {
            if ((layer.type || 'screen') !== 'screen') return;
            this._ensureGradientDefaults(layer);
            Object.keys(patch).forEach(k => {
                const v = patch[k];
                layer[k] = (k === 'gradientStops' && Array.isArray(v))
                    ? v.map(s => ({ pos: s.pos, color: s.color }))
                    : v;
            });
        });
        if (window.canvasRenderer) window.canvasRenderer.render();
        // isFinal is the commit (live drags/inputs pass false and only
        // repaint). Record ONE undo step here — every gradient control funnels
        // through this method, so the whole editor was previously non-undoable.
        if (isFinal) {
            this.updateLayers(this.getSelectedLayers());
            this.debouncedSaveState('Update Gradient', 400, 'gradient');
        }
    }

    _gradientStops() {
        const l = this._gradientLayer();
        const stops = l && Array.isArray(l.gradientStops) ? l.gradientStops : [];
        return stops.length >= 2 ? stops : [{ pos: 0, color: '#1d9e75' }, { pos: 1, color: '#2145dc' }];
    }

    setupGradientEditor() {
        this.gradientSelectedStop = 0;
        const $ = (id) => document.getElementById(id);
        const enabled = $('gradient-enabled');
        const controls = $('gradient-controls');
        const typeSel = $('gradient-type');
        const angleRow = $('gradient-angle-row');
        const angle = $('gradient-angle');
        const angleNum = $('gradient-angle-num');
        const opacity = $('gradient-opacity');
        const opacityNum = $('gradient-opacity-num');
        const blend = $('gradient-blend');
        const bar = $('gradient-bar');
        const stopColor = $('gradient-stop-color');
        const stopHex = $('gradient-stop-hex');
        const stopPos = $('gradient-stop-pos');
        const stopRemove = $('gradient-stop-remove');
        if (!enabled || !bar) return;

        enabled.addEventListener('change', () => {
            if (!this._gradientLayer()) { enabled.checked = false; return; }
            this._applyGradient({ gradientEnabled: enabled.checked }, true);
            if (controls) controls.style.display = enabled.checked ? 'block' : 'none';
        });

        const radialRows = $('gradient-radial-rows');
        if (typeSel) typeSel.addEventListener('change', () => {
            this._applyGradient({ gradientType: typeSel.value }, true);
            const isRadial = typeSel.value === 'radial';
            if (angleRow) angleRow.style.display = isRadial ? 'none' : 'block';
            if (radialRows) radialRows.style.display = isRadial ? 'block' : 'none';
        });

        // Radial center X/Y and size: each a slider + typeable % field that
        // maps to a 0–1 fraction (center) or × multiplier (size /100).
        const wireFrac = (sliderId, numId, key, lo, hi) => {
            const s = $(sliderId), n = $(numId);
            const apply = (val, isFinal) => {
                let v = Math.round(Number(val));
                if (!Number.isFinite(v)) v = 0;
                v = Math.min(hi, Math.max(lo, v));
                if (s) s.value = v;
                if (n) n.value = v;
                this._applyGradient({ [key]: v / 100 }, isFinal);
            };
            if (s) {
                s.addEventListener('input', () => apply(s.value, false));
                s.addEventListener('change', () => apply(s.value, true));
            }
            if (n) n.addEventListener('change', () => apply(n.value, true));
        };
        wireFrac('gradient-rcx', 'gradient-rcx-num', 'gradientRadialCenterX', -50, 150);
        wireFrac('gradient-rcy', 'gradient-rcy-num', 'gradientRadialCenterY', -50, 150);
        wireFrac('gradient-rsize', 'gradient-rsize-num', 'gradientRadialRadius', 10, 400);

        const scopeSel = $('gradient-scope');
        const altRow = $('gradient-alternate-row');
        if (scopeSel) scopeSel.addEventListener('change', () => {
            this._applyGradient({ gradientScope: scopeSel.value }, true);
            if (altRow) altRow.style.display = (scopeSel.value === 'panel') ? 'flex' : 'none';
        });
        const alt = $('gradient-panel-alternate');
        if (alt) alt.addEventListener('change', () => {
            this._applyGradient({ gradientPanelAlternate: alt.checked }, true);
        });

        // Preset library (custom swatch menu).
        const presetTrigger = $('gradient-preset-trigger');
        const presetMenu = $('gradient-preset-menu');
        if (presetTrigger && presetMenu) {
            presetTrigger.addEventListener('click', (e) => {
                e.stopPropagation();
                presetMenu.style.display = (presetMenu.style.display === 'none') ? 'block' : 'none';
            });
            // Close on outside click.
            document.addEventListener('click', (e) => {
                if (presetMenu.style.display !== 'none'
                    && !presetMenu.contains(e.target) && e.target !== presetTrigger
                    && !presetTrigger.contains(e.target)) {
                    presetMenu.style.display = 'none';
                }
            });
        }
        const presetSave = $('gradient-preset-save');
        if (presetSave) presetSave.addEventListener('click', () => this.saveCurrentGradientPreset());
        this.refreshGradientPresetDropdown();

        // Angle: slider + typeable number field, kept in sync.
        const applyAngle = (val, isFinal) => {
            let v = Math.round(Number(val));
            if (!Number.isFinite(v)) v = 0;
            v = ((v % 360) + 360) % 360;   // wrap into 0–359
            if (angle) angle.value = v;
            if (angleNum) angleNum.value = v;
            this._applyGradient({ gradientAngle: v }, isFinal);
        };
        if (angle) {
            angle.addEventListener('input', () => applyAngle(angle.value, false));
            angle.addEventListener('change', () => applyAngle(angle.value, true));
        }
        if (angleNum) {
            angleNum.addEventListener('change', () => applyAngle(angleNum.value, true));
        }
        // Opacity: slider + typeable number field (0–100%).
        const applyOpacity = (val, isFinal) => {
            let v = Math.round(Number(val));
            if (!Number.isFinite(v)) v = 0;
            v = Math.min(100, Math.max(0, v));
            if (opacity) opacity.value = v;
            if (opacityNum) opacityNum.value = v;
            this._applyGradient({ gradientOpacity: v / 100 }, isFinal);
        };
        if (opacity) {
            opacity.addEventListener('input', () => applyOpacity(opacity.value, false));
            opacity.addEventListener('change', () => applyOpacity(opacity.value, true));
        }
        if (opacityNum) {
            opacityNum.addEventListener('change', () => applyOpacity(opacityNum.value, true));
        }
        if (blend) blend.addEventListener('change', () => {
            this._applyGradient({ gradientBlend: blend.value }, true);
        });

        // Selected-stop color / hex / position editors.
        const setStop = (mutate, isFinal) => {
            const stops = this._gradientStops().map(s => ({ pos: s.pos, color: s.color }));
            const i = Math.min(this.gradientSelectedStop, stops.length - 1);
            if (i < 0 || !stops[i]) return;
            mutate(stops[i]);
            this._applyGradient({ gradientStops: stops }, isFinal);
            this.renderGradientBar();
        };
        if (stopColor) {
            stopColor.addEventListener('input', () => setStop(s => { s.color = stopColor.value; if (stopHex) stopHex.value = stopColor.value.toUpperCase(); }, false));
            stopColor.addEventListener('change', () => setStop(s => { s.color = stopColor.value; }, true));
        }
        if (stopHex) stopHex.addEventListener('change', () => {
            let v = stopHex.value.trim();
            if (/^#?[0-9a-fA-F]{6}$/.test(v)) {
                if (v[0] !== '#') v = '#' + v;
                if (stopColor) stopColor.value = v;
                setStop(s => { s.color = v; }, true);
            }
        });
        if (stopPos) stopPos.addEventListener('change', () => {
            const p = Math.min(100, Math.max(0, Number(stopPos.value) || 0)) / 100;
            setStop(s => { s.pos = p; }, true);
        });
        if (stopRemove) stopRemove.addEventListener('click', () => {
            const stops = this._gradientStops().map(s => ({ pos: s.pos, color: s.color }));
            if (stops.length <= 2) return;
            stops.splice(this.gradientSelectedStop, 1);
            this.gradientSelectedStop = Math.max(0, this.gradientSelectedStop - 1);
            this._applyGradient({ gradientStops: stops }, true);
            this.loadGradientEditor();
        });

        // Click empty bar → add a stop at that position (interpolated color).
        bar.addEventListener('mousedown', (e) => {
            if (e.target !== bar) return;   // marker drags handled per-marker
            const rect = bar.getBoundingClientRect();
            const pos = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
            const stops = this._gradientStops().map(s => ({ pos: s.pos, color: s.color }));
            stops.push({ pos, color: this._sampleGradient(stops, pos) });
            stops.sort((a, b) => a.pos - b.pos);
            this.gradientSelectedStop = stops.findIndex(s => s.pos === pos);
            this._applyGradient({ gradientStops: stops }, true);
            this.loadGradientEditor();
        });

        this._gradientBarEl = bar;
    }

    // Sample a hex color along the current stop list at position p (0..1).
    _sampleGradient(stops, p) {
        const sorted = stops.slice().sort((a, b) => a.pos - b.pos);
        if (p <= sorted[0].pos) return sorted[0].color;
        if (p >= sorted[sorted.length - 1].pos) return sorted[sorted.length - 1].color;
        for (let i = 0; i < sorted.length - 1; i++) {
            const a = sorted[i], b = sorted[i + 1];
            if (p >= a.pos && p <= b.pos) {
                const t = (b.pos - a.pos) ? (p - a.pos) / (b.pos - a.pos) : 0;
                const ca = this.hexToRgb(a.color), cb = this.hexToRgb(b.color);
                const mix = (x, y) => Math.round(x + (y - x) * t);
                const toHex = (n) => n.toString(16).padStart(2, '0');
                return `#${toHex(mix(ca.r, cb.r))}${toHex(mix(ca.g, cb.g))}${toHex(mix(ca.b, cb.b))}`;
            }
        }
        return sorted[0].color;
    }

    // Paint the gradient bar background + stop markers, and wire marker drag.
    renderGradientBar() {
        const bar = this._gradientBarEl || document.getElementById('gradient-bar');
        if (!bar) return;
        const stops = this._gradientStops().slice().sort((a, b) => a.pos - b.pos);
        const css = stops.map(s => `${s.color} ${Math.round(s.pos * 100)}%`).join(', ');
        bar.style.background = `linear-gradient(to right, ${css})`;
        bar.innerHTML = '';
        const orig = this._gradientStops();
        stops.forEach((s) => {
            const idx = orig.indexOf(s);
            const m = document.createElement('div');
            const selected = idx === this.gradientSelectedStop;
            m.style.cssText = `position:absolute; top:-3px; width:12px; height:32px; margin-left:-6px; left:${s.pos * 100}%; border-radius:3px; border:2px solid ${selected ? '#fff' : '#222'}; box-shadow:0 0 0 1px rgba(0,0,0,0.6); background:${s.color}; cursor:grab;`;
            m.addEventListener('mousedown', (e) => {
                e.stopPropagation();
                this.gradientSelectedStop = idx;
                this.loadGradientEditor();
                const rect = bar.getBoundingClientRect();
                const move = (ev) => {
                    const pos = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
                    const cur = this._gradientStops().map(x => ({ pos: x.pos, color: x.color }));
                    if (cur[idx]) { cur[idx].pos = pos; }
                    this._applyGradient({ gradientStops: cur }, false);
                    if (document.getElementById('gradient-stop-pos')) document.getElementById('gradient-stop-pos').value = Math.round(pos * 100);
                    this.renderGradientBar();
                };
                const up = () => {
                    document.removeEventListener('mousemove', move);
                    document.removeEventListener('mouseup', up);
                    this.updateLayers(this.getSelectedLayers());
                };
                document.addEventListener('mousemove', move);
                document.addEventListener('mouseup', up);
            });
            bar.appendChild(m);
        });
        if (typeof this.updateGradientPresetPreview === 'function') this.updateGradientPresetPreview();
    }

    // Reflect currentLayer's gradient config into all editor controls.
    loadGradientEditor() {
        const l = this._gradientLayer();
        const $ = (id) => document.getElementById(id);
        const enabled = $('gradient-enabled');
        const controls = $('gradient-controls');
        if (!enabled) return;
        if (!l) { enabled.checked = false; if (controls) controls.style.display = 'none'; return; }
        enabled.checked = !!l.gradientEnabled;
        if (controls) controls.style.display = l.gradientEnabled ? 'block' : 'none';
        if ($('gradient-type')) $('gradient-type').value = l.gradientType || 'linear';
        if ($('gradient-scope')) $('gradient-scope').value = l.gradientScope || 'screen';
        if ($('gradient-alternate-row')) $('gradient-alternate-row').style.display = (l.gradientScope === 'panel') ? 'flex' : 'none';
        if ($('gradient-panel-alternate')) $('gradient-panel-alternate').checked = !!l.gradientPanelAlternate;
        const isRadial = (l.gradientType || 'linear') === 'radial';
        if ($('gradient-angle-row')) $('gradient-angle-row').style.display = isRadial ? 'none' : 'block';
        if ($('gradient-radial-rows')) $('gradient-radial-rows').style.display = isRadial ? 'block' : 'none';
        const setPair = (sliderId, numId, frac) => {
            const v = Math.round(frac * 100);
            if ($(sliderId)) $(sliderId).value = v;
            if ($(numId)) $(numId).value = v;
        };
        setPair('gradient-rcx', 'gradient-rcx-num', (l.gradientRadialCenterX != null) ? l.gradientRadialCenterX : 0.5);
        setPair('gradient-rcy', 'gradient-rcy-num', (l.gradientRadialCenterY != null) ? l.gradientRadialCenterY : 0.5);
        setPair('gradient-rsize', 'gradient-rsize-num', (l.gradientRadialRadius != null) ? l.gradientRadialRadius : 1);
        const ang = Number(l.gradientAngle) || 0;
        if ($('gradient-angle')) $('gradient-angle').value = ang;
        if ($('gradient-angle-num')) $('gradient-angle-num').value = ang;
        const opPct = Math.round(((l.gradientOpacity != null) ? l.gradientOpacity : 0.6) * 100);
        if ($('gradient-opacity')) $('gradient-opacity').value = opPct;
        if ($('gradient-opacity-num')) $('gradient-opacity-num').value = opPct;
        if ($('gradient-blend')) $('gradient-blend').value = l.gradientBlend || 'normal';
        const stops = this._gradientStops();
        if (this.gradientSelectedStop >= stops.length) this.gradientSelectedStop = 0;
        const sel = stops[this.gradientSelectedStop] || stops[0];
        if (sel) {
            if ($('gradient-stop-color')) $('gradient-stop-color').value = sel.color;
            if ($('gradient-stop-hex')) $('gradient-stop-hex').value = (sel.color || '').toUpperCase();
            if ($('gradient-stop-pos')) $('gradient-stop-pos').value = Math.round((sel.pos || 0) * 100);
        }
        if ($('gradient-stop-remove')) $('gradient-stop-remove').disabled = stops.length <= 2;
        this.renderGradientBar();
        if (typeof this.updateGradientPresetPreview === 'function') this.updateGradientPresetPreview();
    }

    // ── v0.8.7.8: Gradient preset library ──────────────────────────────
    // A preset stores the full gradient *look* (type/angle/scope/opacity/
    // blend/alternate + stops). Built-ins ship with the app; user presets
    // live in localStorage. Applying a preset turns the gradient on.

    _builtinGradientPresets() {
        const S = (...c) => c.map((color, i) => ({ pos: c.length === 1 ? 0 : i / (c.length - 1), color }));
        return [
            { name: 'Black, White', gradientType: 'linear', gradientStops: S('#000000', '#ffffff') },
            { name: 'Spectrum', gradientType: 'linear', gradientStops: [
                { pos: 0, color: '#ff0000' }, { pos: 0.17, color: '#ff9900' }, { pos: 0.34, color: '#ffff00' },
                { pos: 0.5, color: '#33cc33' }, { pos: 0.67, color: '#0066ff' }, { pos: 0.84, color: '#6600cc' }, { pos: 1, color: '#cc00cc' } ] },
            { name: 'Transparent Rainbow', gradientType: 'linear', gradientStops: [
                { pos: 0, color: '#ff0040' }, { pos: 0.2, color: '#ff9900' }, { pos: 0.4, color: '#ffee00' },
                { pos: 0.6, color: '#00cc66' }, { pos: 0.8, color: '#0099ff' }, { pos: 1, color: '#cc33ff' } ] },
            { name: 'Red, Green', gradientType: 'linear', gradientStops: S('#e21f26', '#00a651') },
            { name: 'Violet, Orange', gradientType: 'linear', gradientStops: S('#7b2ff7', '#f7971e') },
            { name: 'Blue, Red, Yellow', gradientType: 'linear', gradientStops: S('#2145dc', '#e21f26', '#ffe400') },
            { name: 'Blue, Yellow, Blue', gradientType: 'linear', gradientStops: S('#1f5fd0', '#ffe400', '#1f5fd0') },
            { name: 'Orange, Yellow, Orange', gradientType: 'linear', gradientStops: S('#f7591f', '#ffe400', '#f7591f') },
            { name: 'Violet, Green, Orange', gradientType: 'linear', gradientStops: S('#8e2de2', '#00a651', '#f7971e') },
            { name: 'Yellow, Violet, Orange, Blue', gradientType: 'linear', gradientStops: S('#ffe400', '#8e2de2', '#f7971e', '#2145dc') },
            { name: 'Copper', gradientType: 'linear', gradientStops: [
                { pos: 0, color: '#3a1c0e' }, { pos: 0.4, color: '#b5683a' }, { pos: 0.6, color: '#e9a178' }, { pos: 1, color: '#7a3b1e' } ] },
            { name: 'Chrome', gradientType: 'linear', gradientStops: [
                { pos: 0, color: '#2b2f33' }, { pos: 0.35, color: '#c9d2d9' }, { pos: 0.5, color: '#7c8a96' }, { pos: 0.65, color: '#eef3f6' }, { pos: 1, color: '#3a4248' } ] },
            { name: 'Gold', gradientType: 'linear', gradientStops: [
                { pos: 0, color: '#7a5a10' }, { pos: 0.5, color: '#ffd75e' }, { pos: 1, color: '#a9791a' } ] },
            { name: 'Fire', gradientType: 'linear', gradientAngle: 90, gradientStops: [
                { pos: 0, color: '#000000' }, { pos: 0.45, color: '#cc1100' }, { pos: 0.8, color: '#ff7700' }, { pos: 1, color: '#ffdd00' } ] },
            { name: 'Ocean', gradientType: 'linear', gradientStops: S('#001f3f', '#0074d9', '#7fdbff') },
            { name: 'Sunset', gradientType: 'linear', gradientStops: S('#2c3e50', '#fd746c', '#ffc371') },
            { name: 'Ice', gradientType: 'linear', gradientStops: S('#0b486b', '#3b8686', '#cfeff5') },
            { name: 'Neon', gradientType: 'linear', gradientStops: S('#ff00cc', '#00ffff') },
            { name: 'Pastels', gradientType: 'linear', gradientStops: S('#ffd1dc', '#c1f0c1', '#c9e4ff', '#fff2b2') },
            { name: 'Blues', gradientType: 'linear', gradientStops: S('#cfe8ff', '#3a7bd5', '#0b2a5b') },
            { name: 'Greens', gradientType: 'linear', gradientStops: S('#d6f5d6', '#3fae3f', '#0e3b13') },
            { name: 'Purples', gradientType: 'linear', gradientStops: S('#efd6ff', '#8e44ad', '#2c0b3a') },
        ];
    }

    _userGradientPresets() {
        try { return JSON.parse(localStorage.getItem('ledRasterGradientPresets') || '[]') || []; }
        catch { return []; }
    }
    _setUserGradientPresets(arr) {
        try { localStorage.setItem('ledRasterGradientPresets', JSON.stringify(arr || [])); } catch (_) {}
    }

    // CSS left→right gradient string for previewing a stop list as a swatch.
    _gradientCssBar(stops) {
        const arr = (Array.isArray(stops) ? stops.slice() : [])
            .filter(s => s && s.color)
            .sort((a, b) => (Number(a.pos) || 0) - (Number(b.pos) || 0));
        if (arr.length < 2) return arr[0] ? arr[0].color : '#444';
        return `linear-gradient(to right, ${arr.map(s => `${s.color} ${Math.round((Number(s.pos) || 0) * 100)}%`).join(', ')})`;
    }

    // Build the custom preset menu with a gradient swatch per row.
    refreshGradientPresetDropdown() {
        const menu = document.getElementById('gradient-preset-menu');
        if (!menu) return;
        menu.innerHTML = '';
        const groups = [
            { label: 'Built-in', items: this._builtinGradientPresets(), prefix: 'builtin', canDelete: false },
            { label: 'Saved', items: this._userGradientPresets(), prefix: 'user', canDelete: true },
        ];
        groups.forEach(g => {
            if (!g.items.length) return;
            const h = document.createElement('div');
            h.textContent = g.label;
            h.style.cssText = 'font-size:10px; color:#888; text-transform:uppercase; letter-spacing:0.5px; padding:4px 4px 2px;';
            menu.appendChild(h);
            g.items.forEach(p => {
                const row = document.createElement('div');
                row.style.cssText = 'display:flex; align-items:center; gap:6px; padding:3px 4px; border-radius:4px; cursor:pointer;';
                row.addEventListener('mouseenter', () => { row.style.background = '#2a2a2a'; });
                row.addEventListener('mouseleave', () => { row.style.background = 'transparent'; });
                const sw = document.createElement('span');
                sw.style.cssText = `flex:1; min-width:0; height:16px; border-radius:3px; border:1px solid rgba(0,0,0,0.5); background:${this._gradientCssBar(p.gradientStops)};`;
                const nm = document.createElement('span');
                nm.textContent = p.name;
                nm.style.cssText = 'flex:1.4; font-size:11px; color:#ddd; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;';
                row.appendChild(sw); row.appendChild(nm);
                row.addEventListener('click', () => {
                    this.applyGradientPreset(`${g.prefix}:${p.name}`);
                    this._closeGradientPresetMenu();
                });
                if (g.canDelete) {
                    const x = document.createElement('button');
                    x.textContent = '×';
                    x.title = 'Delete preset';
                    x.style.cssText = 'background:transparent; border:none; color:#999; font-size:14px; cursor:pointer; padding:0 4px;';
                    x.addEventListener('click', (e) => {
                        e.stopPropagation();
                        this._setUserGradientPresets(this._userGradientPresets().filter(u => u.name !== p.name));
                        this.refreshGradientPresetDropdown();
                    });
                    row.appendChild(x);
                }
                menu.appendChild(row);
            });
        });
    }

    _closeGradientPresetMenu() {
        const menu = document.getElementById('gradient-preset-menu');
        if (menu) menu.style.display = 'none';
    }

    // Reflect the current layer's gradient as the trigger's preview swatch.
    updateGradientPresetPreview() {
        const prev = document.getElementById('gradient-preset-preview');
        if (!prev) return;
        prev.style.background = this._gradientCssBar(this._gradientStops());
    }

    applyGradientPreset(value) {
        if (!value) return;
        const [kind, ...rest] = value.split(':');
        const name = rest.join(':');
        const isUser = kind === 'user';
        const list = isUser ? this._userGradientPresets() : this._builtinGradientPresets();
        const p = list.find(x => x.name === name);
        if (!p) return;
        // Built-in presets are just color sets, apply ONLY the stops and keep
        // the current type/scope/opacity/blend/radial setup (so a radial stays
        // radial, etc.). User presets carry the full look they were saved with.
        const patch = {
            gradientEnabled: true,
            gradientStops: (p.gradientStops || []).map(s => ({ pos: s.pos, color: s.color })),
        };
        if (isUser) {
            const carry = ['gradientType', 'gradientAngle', 'gradientScope', 'gradientOpacity',
                'gradientBlend', 'gradientPanelAlternate',
                'gradientRadialCenterX', 'gradientRadialCenterY', 'gradientRadialRadius'];
            carry.forEach(k => { if (p[k] != null) patch[k] = p[k]; });
        }
        this._applyGradient(patch, true);
        this.loadGradientEditor();
    }

    saveCurrentGradientPreset() {
        const l = this._gradientLayer();
        if (!l) return;
        const name = (window.prompt('Save gradient preset as:') || '').trim();
        if (!name) return;
        const preset = {
            name,
            gradientType: l.gradientType || 'linear',
            gradientAngle: Number(l.gradientAngle) || 0,
            gradientScope: l.gradientScope || 'screen',
            gradientOpacity: (l.gradientOpacity != null) ? l.gradientOpacity : 0.6,
            gradientBlend: l.gradientBlend || 'normal',
            gradientPanelAlternate: !!l.gradientPanelAlternate,
            gradientRadialCenterX: (l.gradientRadialCenterX != null) ? l.gradientRadialCenterX : 0.5,
            gradientRadialCenterY: (l.gradientRadialCenterY != null) ? l.gradientRadialCenterY : 0.5,
            gradientRadialRadius: (l.gradientRadialRadius != null) ? l.gradientRadialRadius : 1,
            gradientStops: this._gradientStops().map(s => ({ pos: s.pos, color: s.color })),
        };
        const users = this._userGradientPresets().filter(p => p.name !== name);
        users.push(preset);
        this._setUserGradientPresets(users);
        this.refreshGradientPresetDropdown();
    }

    // ── v0.8.7.8: Multi-color cabinet palette editor ───────────────────

    _defaultPalette() {
        return ['#BC382F', '#BA7517', '#D2E94D', '#1D9E75', '#2145DC', '#7414F5'];
    }

    _paletteColors() {
        const l = this._gradientLayer();
        const pal = l && Array.isArray(l.panelColors) ? l.panelColors : [];
        return pal.length ? pal.slice() : this._defaultPalette();
    }

    // Apply panelColorMode / panelColors to every selected screen layer.
    _applyPanelColors(patch, isFinal) {
        this.applyToSelectedLayers(layer => {
            if ((layer.type || 'screen') !== 'screen') return;
            if (patch.panelColors && (!Array.isArray(layer.panelColors) || layer.panelColors.length === 0)) {
                // seed handled by caller; ensure array exists
            }
            Object.keys(patch).forEach(k => {
                const v = patch[k];
                layer[k] = (k === 'panelColors' && Array.isArray(v)) ? v.slice() : v;
            });
        });
        if (window.canvasRenderer) window.canvasRenderer.render();
        // isFinal is the commit; record ONE undo step (every palette control
        // funnels through here, so the whole palette editor was non-undoable).
        if (isFinal) {
            this.updateLayers(this.getSelectedLayers());
            this.debouncedSaveState('Update Palette', 400, 'palette');
        }
    }

    setupPaletteEditor() {
        this.paletteSelectedIndex = 0;
        const $ = (id) => document.getElementById(id);
        const modeSel = $('panel-color-mode');
        const editor = $('panel-palette-editor');
        const color = $('palette-color');
        const hex = $('palette-hex');
        const addBtn = $('palette-add');
        const removeBtn = $('palette-remove');
        if (!modeSel) return;

        modeSel.addEventListener('change', () => {
            const l = this._gradientLayer();
            if (!l) { modeSel.value = 'checker'; return; }
            const patch = { panelColorMode: modeSel.value };
            // Seed a starter palette the first time a palette mode is chosen.
            if (modeSel.value !== 'checker' && (!Array.isArray(l.panelColors) || l.panelColors.length === 0)) {
                patch.panelColors = this._defaultPalette();
            }
            this._applyPanelColors(patch, true);
            if (editor) editor.style.display = (modeSel.value === 'checker') ? 'none' : 'block';
            this.loadPaletteEditor();
        });

        const setSwatch = (mutate, isFinal) => {
            const pal = this._paletteColors();
            const i = Math.min(this.paletteSelectedIndex, pal.length - 1);
            if (i < 0 || !pal[i]) return;
            mutate(pal, i);
            this._applyPanelColors({ panelColors: pal }, isFinal);
            this.renderPaletteSwatches();
        };
        if (color) {
            color.addEventListener('input', () => setSwatch((pal, i) => { pal[i] = color.value; if (hex) hex.value = color.value.toUpperCase(); }, false));
            color.addEventListener('change', () => setSwatch((pal, i) => { pal[i] = color.value; }, true));
        }
        if (hex) hex.addEventListener('change', () => {
            let v = hex.value.trim();
            if (/^#?[0-9a-fA-F]{6}$/.test(v)) {
                if (v[0] !== '#') v = '#' + v;
                if (color) color.value = v;
                setSwatch((pal, i) => { pal[i] = v; }, true);
            }
        });
        if (addBtn) addBtn.addEventListener('click', () => {
            const pal = this._paletteColors();
            pal.push(color ? color.value : '#ffffff');
            this.paletteSelectedIndex = pal.length - 1;
            this._applyPanelColors({ panelColors: pal }, true);
            this.loadPaletteEditor();
        });
        if (removeBtn) removeBtn.addEventListener('click', () => {
            const pal = this._paletteColors();
            if (pal.length <= 1) return;
            pal.splice(this.paletteSelectedIndex, 1);
            this.paletteSelectedIndex = Math.max(0, this.paletteSelectedIndex - 1);
            this._applyPanelColors({ panelColors: pal }, true);
            this.loadPaletteEditor();
        });
    }

    renderPaletteSwatches() {
        const host = document.getElementById('panel-palette-swatches');
        if (!host) return;
        const pal = this._paletteColors();
        host.innerHTML = '';
        pal.forEach((c, i) => {
            const sw = document.createElement('button');
            const selected = i === this.paletteSelectedIndex;
            sw.style.cssText = `width:24px; height:24px; padding:0; border-radius:4px; cursor:pointer; background:${c}; border:2px solid ${selected ? '#fff' : '#333'}; box-shadow:0 0 0 1px rgba(0,0,0,0.5);`;
            sw.title = c;
            sw.addEventListener('click', () => { this.paletteSelectedIndex = i; this.loadPaletteEditor(); });
            host.appendChild(sw);
        });
    }

    loadPaletteEditor() {
        const l = this._gradientLayer();
        const $ = (id) => document.getElementById(id);
        const modeSel = $('panel-color-mode');
        const editor = $('panel-palette-editor');
        if (!modeSel) return;
        if (!l) { modeSel.value = 'checker'; if (editor) editor.style.display = 'none'; return; }
        const mode = l.panelColorMode || 'checker';
        modeSel.value = mode;
        if (editor) editor.style.display = (mode === 'checker') ? 'none' : 'block';
        const pal = this._paletteColors();
        if (this.paletteSelectedIndex >= pal.length) this.paletteSelectedIndex = 0;
        const sel = pal[this.paletteSelectedIndex] || pal[0];
        if (sel) {
            if ($('palette-color')) $('palette-color').value = sel;
            if ($('palette-hex')) $('palette-hex').value = sel.toUpperCase();
        }
        if ($('palette-remove')) $('palette-remove').disabled = pal.length <= 1;
        this.renderPaletteSwatches();
    }

    getSelectedLayers() {
        if (!this.project || !this.project.layers) return [];
        this.dedupeProjectLayers('get_selected_layers');
        if (!this.selectedLayerIds || this.selectedLayerIds.size === 0) {
            return this.currentLayer ? [this.currentLayer] : [];
        }
        return this.project.layers.filter(l => this.selectedLayerIds.has(l.id));
    }

    upsertProjectLayer(layer) {
        if (!this.project || !this.project.layers || !layer) return;
        const index = this.project.layers.findIndex(l => l.id === layer.id);
        if (index >= 0) {
            this.project.layers[index] = layer;
        } else {
            this.project.layers.push(layer);
        }
    }

    dedupeProjectLayers(reason = 'unknown') {
        if (!this.project || !Array.isArray(this.project.layers)) return;
        const seen = new Set();
        const deduped = [];
        const dropped = [];
        this.project.layers.forEach(layer => {
            if (!layer || layer.id === undefined || layer.id === null) return;
            if (seen.has(layer.id)) {
                dropped.push(layer.id);
                return;
            }
            seen.add(layer.id);
            deduped.push(layer);
        });
        if (dropped.length > 0) {
            this.project.layers = deduped;
            this.selectedLayerIds = new Set([...this.selectedLayerIds].filter(id => seen.has(id)));
            if (this.currentLayer && !seen.has(this.currentLayer.id)) {
                this.currentLayer = this.project.layers.length > 0 ? this.project.layers[0] : null;
            } else if (this.currentLayer) {
                this.currentLayer = this.project.layers.find(l => l.id === this.currentLayer.id) || this.currentLayer;
            }
            if (typeof sendClientLog === 'function') {
                sendClientLog('project_layers_deduped', { reason, droppedIds: dropped });
            }
        }
    }

    applyToSelectedLayers(fn) {
        const layers = this.getSelectedLayers();
        // v0.11.0: a screen group is ONE screen, so an edit to a member is an
        // edit to the wall. Rather than teach ~70 control handlers about
        // groups, snapshot the shareable fields here, let `fn` do its existing
        // work, then copy across only what actually changed (see
        // GROUP_SHARED_LAYER_FIELDS in app-screen-groups.js). Diffing is what
        // keeps an unrelated edit from silently repainting a peer.
        const snapshot = this._snapshotSharedFields
            ? this._snapshotSharedFields(layers) : null;
        layers.forEach(fn);
        if (snapshot && this._propagateChangedSharedFields) {
            this._propagateChangedSharedFields(layers, snapshot);
        }
    }

    setSelectedLayersByIds(ids, primaryId = null) {
        this.selectedLayerIds = new Set(ids);
        if (primaryId && this.selectedLayerIds.has(primaryId)) {
            this.currentLayer = this.project.layers.find(l => l.id === primaryId) || this.currentLayer;
        } else if (this.selectedLayerIds.size > 0) {
            const firstId = this.selectedLayerIds.values().next().value;
            this.currentLayer = this.project.layers.find(l => l.id === firstId) || this.currentLayer;
        } else {
            this.currentLayer = null;
        }
        if (this.currentLayer) {
            this.lastSelectedLayerId = this.currentLayer.id;
            this.selectionAnchorLayerId = this.currentLayer.id;
        }
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    toggleLayerSelection(layer) {
        if (!layer) return;
        if (!this.selectedLayerIds || this.selectedLayerIds.size === 0) {
            this.selectedLayerIds = new Set([layer.id]);
            this.currentLayer = layer;
        } else if (this.selectedLayerIds.has(layer.id)) {
            this.selectedLayerIds.delete(layer.id);
            if (this.currentLayer && this.currentLayer.id === layer.id) {
                const nextId = this.selectedLayerIds.values().next().value;
                this.currentLayer = nextId ? this.project.layers.find(l => l.id === nextId) : null;
            }
        } else {
            this.selectedLayerIds.add(layer.id);
            this.currentLayer = layer;
        }
        this.lastSelectedLayerId = layer.id;
        if (!this.selectionAnchorLayerId) {
            this.selectionAnchorLayerId = layer.id;
        }
        // Slice 4 + Slice 13: auto-activate this layer's canvas, but PRESERVE
        // any existing cross-canvas multi-selection. Without this flag,
        // setActiveCanvas would drop selected layers in other canvases - which
        // breaks the "select layers across canvases and bulk-edit them" flow
        // (e.g. shift-click SR in c1, then DJ in c2, then change panel size on
        // both at once).
        this._activateCanvasForLayer(this.currentLayer, { preserveSelection: true });
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    selectLayerRange(layer) {
        if (!layer || !this.project || !this.project.layers) return;
        const order = this.layerListOrder || [...this.project.layers].reverse().map(l => l.id);
        const anchorId = this.selectionAnchorLayerId || (this.currentLayer ? this.currentLayer.id : layer.id);
        const startIndex = order.indexOf(anchorId);
        const endIndex = order.indexOf(layer.id);
        if (startIndex === -1 || endIndex === -1) {
            this.selectLayer(layer);
            return;
        }
        const [from, to] = startIndex <= endIndex ? [startIndex, endIndex] : [endIndex, startIndex];
        const rangeIds = order.slice(from, to + 1);
        this.selectedLayerIds = new Set(rangeIds);
        this.currentLayer = layer;
        this.lastSelectedLayerId = layer.id;
        // Slice 4 + Slice 13: same preserveSelection trick as
        // toggleLayerSelection so a shift-click range selection that crosses
        // canvas boundaries doesn't get its other-canvas members culled
        // when the active canvas auto-switches.
        this._activateCanvasForLayer(layer, { preserveSelection: true });
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    clearLayerSelection() {
        this.selectedLayerIds = new Set();
        this.currentLayer = null;
        this.renderLayers();
        this.loadLayerToInputs();
        window.canvasRenderer.render();
    }

    getFullPanelPixels(layer) {
        if (!layer) return 0;
        return (Number(layer.cabinet_width) || 0) * (Number(layer.cabinet_height) || 0);
    }

    getPanelPixelArea(panel) {
        if (!panel) return 0;
        return (Number(panel.width) || 0) * (Number(panel.height) || 0);
    }
}

for (const k of Object.getOwnPropertyNames(_Colors.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Colors.prototype, k));
    }
}
