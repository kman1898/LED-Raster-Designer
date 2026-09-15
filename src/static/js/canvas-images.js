// canvas.js mixin: Image and text layers: the raster draw and the drop-shadow pipeline behind it.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
Object.assign(CanvasRenderer.prototype, {
    renderImageLayer(layer) {
        if (!layer || !layer.imageData) return;
        if (!layer._imageObj || layer._imageObj.src !== layer.imageData) {
            const img = new Image();
            img.onload = () => {
                if (layer._imageObj !== img) return;
                this.render();
            };
            img.src = layer.imageData;
            layer._imageObj = img;
        }
        const img = layer._imageObj;
        if (!img || !img.complete) return;
        const scale = Number(layer.imageScale) || 1;
        const w = (Number(layer.imageWidth) || img.width) * scale;
        const h = (Number(layer.imageHeight) || img.height) * scale;
        const x = Number(layer.offset_x) || 0;
        const y = Number(layer.offset_y) || 0;
        const prevSmoothing = this.ctx.imageSmoothingEnabled;
        this.ctx.imageSmoothingEnabled = true;
        const shadow = this._imageDropShadowParams(layer);
        if (shadow) this._drawImageDropShadow(img, x, y, w, h, shadow);
        this.ctx.drawImage(img, x, y, w, h);
        this.ctx.imageSmoothingEnabled = prevSmoothing;
    },

    // Read + clamp the per-layer Drop Shadow settings. Returns null when the
    // layer has no shadow, so every project made before this existed renders
    // byte for byte the way it always did.
    _imageDropShadowParams(layer) {
        if (!layer || !layer.imageShadowEnabled) return null;
        const num = (v, dflt, lo, hi) => {
            if (v === null || v === undefined || v === '') return dflt;
            const n = Number(v);
            if (!Number.isFinite(n)) return dflt;
            return Math.max(lo, Math.min(hi, n));
        };
        const size = num(layer.imageShadowSize, 10, 0, 250);
        const distance = num(layer.imageShadowDistance, 10, 0, 250);
        // Nothing to draw: no blur, no dilation and no offset means the
        // shadow would sit exactly under the image and never show.
        if (size <= 0 && distance <= 0) return null;
        const color = /^#[0-9a-fA-F]{6}$/.test(String(layer.imageShadowColor || ''))
            ? String(layer.imageShadowColor) : '#000000';
        return {
            color,
            opacity: num(layer.imageShadowOpacity, 75, 0, 100) / 100,
            angle: num(layer.imageShadowAngle, 120, 0, 360),
            distance,
            spread: num(layer.imageShadowSpread, 0, 0, 100) / 100,
            size,
        };
    },

    // Photoshop's Drop Shadow for an image layer, baked into the frame so the
    // PNG/PDF export gets it too (the export runs this same renderer).
    //
    // Deliberately NOT ctx.shadowBlur/shadowOffsetX/shadowColor: those have no
    // Spread at all, and their offset and blur are in DEVICE pixels - the
    // current transform does not touch them - so the shadow would keep its
    // screen size at every zoom and come out the wrong size in every export.
    // They also leak into every later draw unless each path is wrapped in
    // save()/restore(). Everything below is measured in WORLD units and only
    // rasterised at the transform's own scale, so it tracks zoom and export
    // resolution the way the image itself does.
    _drawImageDropShadow(img, x, y, w, h, p) {
        const ctx = this.ctx;
        if (!(w > 0) || !(h > 0)) return;
        // Device pixels per world unit. A mirrored canvas flips the sign of
        // `a`; hypot keeps the magnitude, and the mirror then applies to the
        // composited shadow exactly as it applies to the image.
        let k = 1;
        if (typeof ctx.getTransform === 'function') {
            const t = ctx.getTransform();
            k = Math.hypot(t.a, t.b);
        } else {
            k = this.zoom || 1;
        }
        if (!Number.isFinite(k) || k <= 0) k = 1;

        // Spread is the fraction of Size that is solid before the falloff
        // starts. The two halves share one budget, so the shadow reaches
        // `size` past the silhouette at any spread; +2 covers the blur's tail.
        const solid = p.spread * p.size;
        const soft = p.size - solid;
        const pad = p.size + 2;

        // A deep zoom can ask for a scratch bigger than the browser will
        // allocate. Drop the raster density rather than the shadow.
        const MAX_DIM = 4096;
        const fitW = (w + pad * 2) * k;
        const fitH = (h + pad * 2) * k;
        if (fitW > MAX_DIM || fitH > MAX_DIM) {
            k = k * Math.min(MAX_DIM / fitW, MAX_DIM / fitH);
        }
        const cw = Math.max(1, Math.ceil((w + pad * 2) * k));
        const chh = Math.max(1, Math.ceil((h + pad * 2) * k));

        // The raster only depends on the silhouette, its size on screen, and
        // the two shape settings - Distance, Angle and Opacity are applied
        // when it is composited, further down. So a PAN, which changes neither
        // the scale nor the settings, can reuse the last one.
        //
        // That matters: the dilation below is a getImageData plus two sweeps
        // over every pixel of the scratch, and the scratch grows with zoom to
        // the 4096 cap. Rebuilding it per frame turned a pan into single-digit
        // fps as soon as Spread was above zero. Cached on the image object, so
        // it is bounded by the number of image layers and freed with them.
        const cacheKey = `${cw}x${chh}|${p.spread}|${p.size}|${p.color}`;
        const cached = img._lrdShadowRaster;
        if (cached && cached.key === cacheKey) {
            this._compositeImageShadow(cached.canvas, x, y, w, h, pad, p);
            return;
        }

        let src = this._imageShadowScratch(0, cw, chh);

        // 1. The alpha silhouette, already tinted: draw the image, then paint
        //    the shadow colour through its own alpha with source-in.
        src.ctx.imageSmoothingEnabled = true;
        src.ctx.drawImage(img, pad * k, pad * k, w * k, h * k);
        src.ctx.globalCompositeOperation = 'source-in';
        src.ctx.fillStyle = p.color;
        src.ctx.fillRect(0, 0, cw, chh);
        src.ctx.globalCompositeOperation = 'source-over';

        const hasFilter = ('filter' in src.ctx);
        const solidPx = solid * k;
        const softPx = soft * k;

        // 2a. Spread = dilate the silhouette by `solid` world units, done as a
        //     distance transform plus a threshold (see _dilateAlpha). Two
        //     cheaper-looking options were tried and rejected:
        //
        //     - Stamping the silhouette around a ring of offsets only covers
        //       translates AT the radius, and the union of a shape with its
        //       ring copies is not its union with the whole disc: a thin
        //       stroke comes out striped at the half-radius.
        //     - Blur-then-threshold looks exact on paper (an ideal Gaussian
        //       crosses 15.87% one sigma out) but is not: the browser's blur
        //       is an approximation that Skia downsamples for large sigma, so
        //       the same threshold moved the edge 33px instead of 40 at
        //       sigma 40 - and the error grows as the shape gets small
        //       relative to the spread.
        //
        //     The distance transform has neither problem and is the same at
        //     every zoom, which the Spread test pins to the pixel.
        if (solidPx >= 0.5) {
            try {
                const id = src.ctx.getImageData(0, 0, cw, chh);
                this._dilateAlpha(id, cw, chh, solidPx, this._hexToRgbTriple(p.color));
                src.ctx.putImageData(id, 0, 0);
            } catch (e) {
                // A tainted canvas (an image served cross-origin) blocks the
                // read. Fall through with the undilated silhouette: a
                // narrower shadow beats no shadow and beats a thrown frame.
            }
        }

        // 2b. The remaining falloff. sigma = soft/2 so the visible edge dies
        //     out about `soft` world units from the silhouette, the same way a
        //     CSS box-shadow blur radius reads.
        if (softPx >= 0.5 && hasFilter) {
            const dst = this._imageShadowScratch(1, cw, chh);
            dst.ctx.filter = `blur(${softPx / 2}px)`;
            dst.ctx.drawImage(src.canvas, 0, 0);
            dst.ctx.filter = 'none';
            src = dst;
        }

        // 3. Keep the finished raster on the image, then composite it.
        const keep = document.createElement('canvas');
        keep.width = cw;
        keep.height = chh;
        keep.getContext('2d').drawImage(src.canvas, 0, 0);
        img._lrdShadowRaster = { key: cacheKey, canvas: keep };
        this._compositeImageShadow(keep, x, y, w, h, pad, p);
    },

    // Distance, Angle and Opacity are applied HERE rather than baked into the
    // raster, so dragging any of the three reuses the cached one.
    //
    // Photoshop's angle points at the LIGHT, counter-clockwise from east in a
    // y-up frame; the shadow falls the other way and canvas y grows downward,
    // so the default 120 deg (light upper-left) throws the shadow down-right.
    _compositeImageShadow(raster, x, y, w, h, pad, p) {
        const ctx = this.ctx;
        const rad = p.angle * Math.PI / 180;
        const offX = -p.distance * Math.cos(rad);
        const offY = p.distance * Math.sin(rad);
        ctx.save();
        ctx.globalAlpha = ctx.globalAlpha * p.opacity;
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(raster,
            x - pad + offX, y - pad + offY,
            w + pad * 2, h + pad * 2);
        ctx.restore();
    },

    // Grow an alpha mask outward by `radius` device pixels, in place, and
    // repaint it in `rgb`. This is the Spread half of the drop shadow.
    //
    // A 3-4 chamfer distance transform: two sweeps (down-right, then up-left)
    // build the distance from every transparent pixel to the nearest solid
    // one, in thirds of a pixel, and everything within `radius` becomes
    // solid. The 3/4 step weights approximate Euclidean distance to about 2%,
    // which is well under a pixel at any Spread the UI allows, and unlike a
    // blur it does not care how large the shape is or how the browser
    // implements filters - the edge lands exactly where Spread says.
    _dilateAlpha(imageData, w, h, radius, rgb) {
        const d = imageData.data;
        const n = w * h;
        const INF = 0x3fffffff;
        const dt = new Int32Array(n);
        for (let i = 0, p = 3; i < n; i++, p += 4) {
            dt[i] = d[p] >= 128 ? 0 : INF;
        }
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                const i = y * w + x;
                let v = dt[i];
                if (v === 0) continue;
                if (x > 0 && dt[i - 1] + 3 < v) v = dt[i - 1] + 3;
                if (y > 0) {
                    if (dt[i - w] + 3 < v) v = dt[i - w] + 3;
                    if (x > 0 && dt[i - w - 1] + 4 < v) v = dt[i - w - 1] + 4;
                    if (x < w - 1 && dt[i - w + 1] + 4 < v) v = dt[i - w + 1] + 4;
                }
                dt[i] = v;
            }
        }
        for (let y = h - 1; y >= 0; y--) {
            for (let x = w - 1; x >= 0; x--) {
                const i = y * w + x;
                let v = dt[i];
                if (v === 0) continue;
                if (x < w - 1 && dt[i + 1] + 3 < v) v = dt[i + 1] + 3;
                if (y < h - 1) {
                    if (dt[i + w] + 3 < v) v = dt[i + w] + 3;
                    if (x < w - 1 && dt[i + w + 1] + 4 < v) v = dt[i + w + 1] + 4;
                    if (x > 0 && dt[i + w - 1] + 4 < v) v = dt[i + w - 1] + 4;
                }
                dt[i] = v;
            }
        }
        const cut = radius * 3;
        for (let i = 0, p = 0; i < n; i++, p += 4) {
            d[p] = rgb[0];
            d[p + 1] = rgb[1];
            d[p + 2] = rgb[2];
            d[p + 3] = dt[i] <= cut ? 255 : 0;
        }
    },

    // Two reusable scratch canvases for the shadow pass. Allocating a fresh
    // pair per layer per frame churned enough memory to stutter a pan.
    _imageShadowScratch(index, w, h) {
        if (!this._imgShadowScratch) this._imgShadowScratch = [];
        let s = this._imgShadowScratch[index];
        if (!s) {
            const canvas = document.createElement('canvas');
            s = { canvas, ctx: canvas.getContext('2d', { willReadFrequently: true }) };
            this._imgShadowScratch[index] = s;
        }
        // Assigning width/height also clears the canvas; only clear by hand
        // when the size is already right.
        if (s.canvas.width !== w || s.canvas.height !== h) {
            s.canvas.width = w;
            s.canvas.height = h;
        } else {
            s.ctx.clearRect(0, 0, w, h);
        }
        s.ctx.globalCompositeOperation = 'source-over';
        s.ctx.globalAlpha = 1;
        if ('filter' in s.ctx) s.ctx.filter = 'none';
        return s;
    },

    _hexToRgbTriple(hex) {
        const m = /^#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/.exec(String(hex || ''));
        if (!m) return [0, 0, 0];
        return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
    },

    renderTextLayer(layer) {
        if (!layer) return;
        // Check per-tab visibility
        const viewMode = this.viewMode || 'pixel-map';
        if (viewMode === 'pixel-map' && !layer.showOnPixelMap) return;
        if (viewMode === 'cabinet-id' && !layer.showOnCabinetId) return;
        if (viewMode === 'data-flow' && !layer.showOnDataFlow) return;
        if (viewMode === 'power' && !layer.showOnPower) return;
        // v0.8.3: Show Look is its own tab and needs an independent gate.
        // Default true so existing projects don't suddenly hide text on it.
        if (viewMode === 'show-look' && layer.showOnShowLook === false) return;

        const x = Number(layer.offset_x) || 0;
        const y = Number(layer.offset_y) || 0;
        const w = Number(layer.textWidth) || 400;
        const h = Number(layer.textHeight) || 100;
        const padding = Number(layer.textPadding) || 12;
        const fontSize = Number(layer.fontSize) || 24;
        const fontFamily = layer.fontFamily || 'Arial';
        const fontColor = layer.fontColor || '#ffffff';
        const bgColor = layer.bgColor || '#000000';
        const bgOpacity = layer.bgOpacity != null ? Number(layer.bgOpacity) : 0.7;
        const textAlign = layer.textAlign || 'left';

        // Background
        this.ctx.save();
        this.ctx.globalAlpha = bgOpacity;
        this.ctx.fillStyle = bgColor;
        this.ctx.fillRect(x, y, w, h);
        this.ctx.globalAlpha = 1.0;

        // Border
        if (layer.showBorder) {
            this.ctx.strokeStyle = layer.borderColor || '#555555';
            this.ctx.lineWidth = 1;
            this.ctx.strokeRect(x, y, w, h);
        }

        // Per-tab text content. Fallback chain:
        //   1. This tab's own textContent<Tab> (explicit per-tab override)
        //   2. The global textContent (legacy default)
        //   3. ANY other per-tab field that's non-empty (so typing into one
        //      tab carries over to the others until the user explicitly
        //      sets a different value per tab). Without this third step,
        //      typing only in Pixel Map left Cabinet ID / Data Flow / Power
        //      / Show Look rendering blank.
        // v0.8.3: shared `textContent` is the default for every tab. Each
        // tab also has an override flag (`textContentOverride<Tab>`); when
        // on, that tab uses its own `textContent<Tab>` field instead of the
        // shared one. Legacy projects (pre-v0.8.3) may have content only in
        // the per-tab fields with `textContent` empty: fall back to whichever
        // per-tab field is non-empty so nothing visually disappears.
        const tabKey = (viewMode === 'pixel-map')  ? 'textContentPixelMap'
                     : (viewMode === 'cabinet-id') ? 'textContentCabinetId'
                     : (viewMode === 'show-look')  ? 'textContentShowLook'
                     : (viewMode === 'data-flow')  ? 'textContentDataFlow'
                     : (viewMode === 'power')      ? 'textContentPower'
                     : null;
        const overrideKey = (viewMode === 'pixel-map')  ? 'textContentOverridePixelMap'
                          : (viewMode === 'cabinet-id') ? 'textContentOverrideCabinetId'
                          : (viewMode === 'show-look')  ? 'textContentOverrideShowLook'
                          : (viewMode === 'data-flow')  ? 'textContentOverrideDataFlow'
                          : (viewMode === 'power')      ? 'textContentOverridePower'
                          : null;
        let text = '';
        if (overrideKey && layer[overrideKey]) {
            text = (tabKey ? layer[tabKey] : '') || '';
        } else {
            text = layer.textContent || '';
        }
        if (!text) {
            const fallbackKeys = ['textContentPixelMap', 'textContentCabinetId',
                                  'textContentShowLook', 'textContentDataFlow',
                                  'textContentPower'];
            for (const k of fallbackKeys) {
                if (layer[k]) { text = layer[k]; break; }
            }
        }

        // Append dynamic info lines
        const dynamicLines = [];
        if (layer.showRasterSize && window.canvasRenderer) {
            const rw = window.canvasRenderer.rasterWidth || 1920;
            const rh = window.canvasRenderer.rasterHeight || 1080;
            dynamicLines.push(`Raster: ${rw} × ${rh}`);
        }
        if (layer.showProjectName && window.app && window.app.project) {
            dynamicLines.push(window.app.project.name || 'Untitled Project');
        }
        if (layer.showDate) {
            dynamicLines.push(new Date().toLocaleDateString());
        }
        // v0.8 Slice 10: dynamic data/power stats now honor a per-layer
        // scope: 'canvas' (text layer's parent canvas), 'project' (all
        // canvases, original behaviour, default), or 'both' (renders one
        // line for the canvas, then one for the project total).
        const scope = layer.dynamicInfoScope || 'project';
        const wantsData = layer.showPrimaryPorts || layer.showBackupPorts;
        const wantsPower = layer.showCircuits || layer.showSinglePhase || layer.showThreePhase;
        if ((wantsData || wantsPower) && window.app) {
            // Resolve the canvas this text layer sits on. For "canvas" /
            // "both" scopes we need to pass canvas_id into the aggregators.
            const ownCanvasId = layer.canvas_id || null;
            const ownCanvas = (ownCanvasId && window.app._activeCanvas)
                ? (window.app.project && window.app.project.canvases || []).find(c => c && c.id === ownCanvasId)
                : null;
            const canvasLabel = ownCanvas ? (ownCanvas.name || 'Canvas') : 'Canvas';
            const passes = []; // [{ key: 'canvas'|'project', label: '... (X)' or '... (Total)' }]
            if (scope === 'canvas') passes.push({ key: 'canvas', suffix: ` (${canvasLabel})` });
            else if (scope === 'project') passes.push({ key: 'project', suffix: '' });
            else { // 'both'
                passes.push({ key: 'canvas', suffix: ` (${canvasLabel})` });
                passes.push({ key: 'project', suffix: ' (Total)' });
            }
            passes.forEach(pass => {
                const filter = pass.key === 'canvas' ? ownCanvasId : undefined;
                if (wantsData) {
                    const counts = window.app.getPortCounts(filter);
                    if (layer.showPrimaryPorts && counts.primary > 0) {
                        dynamicLines.push(`Primary Ports${pass.suffix}: ${counts.primary}`);
                    }
                    if (layer.showBackupPorts && counts.backup > 0) {
                        dynamicLines.push(`Backup Ports${pass.suffix}: ${counts.backup}`);
                    }
                }
                if (wantsPower) {
                    const pwr = window.app.getPowerCounts(filter);
                    // A project may legitimately span voltages - two walls on
                    // different supplies. getPowerCounts refuses to blend them
                    // (the combined amps come back NULL, because 800 W at 110 V
                    // plus 800 W at 208 V is not 1600 W at either), so print a
                    // line PER VOLTAGE instead of one figure belonging to
                    // neither wall. Calling .toFixed on the null combined value
                    // used to take the whole renderer down.
                    const perVoltage = pwr.voltageMismatch && Array.isArray(pwr.byVoltage)
                        ? pwr.byVoltage.filter(b => b && b.circuits > 0)
                        : null;
                    if (perVoltage && perVoltage.length > 0) {
                        perVoltage.forEach(b => {
                            if (layer.showCircuits) {
                                dynamicLines.push(`Circuits${pass.suffix} @ ${b.voltage}V: ${b.circuits}`);
                            }
                            if (layer.showSinglePhase) {
                                dynamicLines.push(`1-Phase${pass.suffix} @ ${b.voltage}V: ${b.amps1ph.toFixed(2)}A`);
                            }
                            if (layer.showThreePhase && b.circuits >= 3) {
                                dynamicLines.push(`3-Phase${pass.suffix} @ ${b.voltage}V: ${b.amps3ph.toFixed(2)}A`);
                            }
                        });
                    } else {
                        if (layer.showCircuits && pwr.circuits > 0) {
                            dynamicLines.push(`Circuits${pass.suffix}: ${pwr.circuits} @ ${pwr.voltage}V`);
                        }
                        if (layer.showSinglePhase && pwr.circuits > 0 && pwr.singlePhaseAmps != null) {
                            dynamicLines.push(`1-Phase${pass.suffix}: ${pwr.singlePhaseAmps.toFixed(2)}A`);
                        }
                        if (layer.showThreePhase && pwr.circuits >= 3 && pwr.threePhaseAmps != null) {
                            dynamicLines.push(`3-Phase${pass.suffix}: ${pwr.threePhaseAmps.toFixed(2)}A`);
                        }
                    }
                }
            });
        }
        if (dynamicLines.length > 0) {
            text = text ? `${text}\n${dynamicLines.join('\n')}` : dynamicLines.join('\n');
        }

        if (text) {
            // Clip text rendering to the text-layer's own box so overlong
            // content can't spill onto neighboring canvases or out of the
            // layer's raster footprint. The clip is scoped to a separate
            // save() so the background + border (already drawn above) are
            // unaffected.
            this.ctx.save();
            this.ctx.beginPath();
            this.ctx.rect(x, y, w, h);
            this.ctx.clip();

            this.ctx.fillStyle = fontColor;
            // Build font string with bold/italic
            let fontStyle = '';
            if (layer.fontItalic) fontStyle += 'italic ';
            if (layer.fontBold) fontStyle += 'bold ';
            this.ctx.font = `${fontStyle}${fontSize}px ${fontFamily}`;
            this.ctx.textBaseline = 'top';
            this.ctx.textAlign = textAlign;

            const lines = text.split('\n');
            const lineHeight = fontSize * 1.3;
            let textX = x + padding;
            if (textAlign === 'center') textX = x + w / 2;
            else if (textAlign === 'right') textX = x + w - padding;

            lines.forEach((line, i) => {
                const ty = y + padding + i * lineHeight;
                // Cheap vertical-overflow short-circuit so we don't measure +
                // fillText for lines fully below the box (clip would suppress
                // them anyway, but skipping saves work on big text dumps).
                if (ty > y + h) return;
                this._fillText(line, textX, ty);
                if (layer.fontUnderline && line.length > 0) {
                    const metrics = this.ctx.measureText(line);
                    let ulX = textX;
                    if (textAlign === 'center') ulX = textX - metrics.width / 2;
                    else if (textAlign === 'right') ulX = textX - metrics.width;
                    const ulY = ty + fontSize + 2;
                    this.ctx.beginPath();
                    this.ctx.strokeStyle = fontColor;
                    this.ctx.lineWidth = Math.max(1, fontSize / 15);
                    this.ctx.moveTo(ulX, ulY);
                    this.ctx.lineTo(ulX + metrics.width, ulY);
                    this.ctx.stroke();
                }
            });
            this.ctx.restore();
        }

        this.ctx.restore();
    },
});
