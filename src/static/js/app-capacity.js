// app-capacity: the port capacity rules for LEDRasterApp - supported
// bit depths and frame rates per processor, the Low Latency profiles and
// their derates, minimum load width, the port capacity lookup table
// walk, the rectangle constraint, and the Low Latency / bit depth UI
// that reflects them.
import { LEDRasterApp } from './app-core.js';

class _Capacity {
    // Get supported bit depths for a processor
    getSupportedBitDepths(processorType) {
        const table = this.portCapacityTables[processorType];
        if (!table) return [8, 10, 12];
        return Object.keys(table).map(Number).sort((a, b) => a - b);
    }
    
    // Get supported frame rates for a processor + bit depth
    getSupportedFrameRates(processorType, bitDepth) {
        const table = this.portCapacityTables[processorType];
        if (!table || !table[bitDepth]) return [];
        return Object.keys(table[bitDepth]).map(Number).sort((a, b) => a - b);
    }
    
    // v0.11.0: descriptor for a processor's Low Latency behaviour, or null when
    // the processor has no entry (a stale value like the retired brompton-ull).
    getLowLatencyProfile(processorType) {
        return this.lowLatencyProfiles[processorType || 'novastar-armor'] || null;
    }

    // v0.11.0: true when the processor's Low Latency behaviour is real but its
    // math has not shipped yet ('y-derate' / 'port-width' in pass 1). Callers
    // must SAY so rather than let the displayed capacity imply it is included.
    isLowLatencyCapacityPending(processorType) {
        const profile = this.getLowLatencyProfile(processorType);
        if (!profile || !profile.supported) return false;
        const kind = (profile.capacity && profile.capacity.kind) || 'none';
        return !this.lowLatencyImplementedKinds.includes(kind);
    }

    // v0.11.0: apply the processor's Low Latency capacity behaviour on top of a
    // table lookup.
    //   'factor'      - Brompton publishes ULL as the normal column halved and
    //                   floored, so floor here too. Flooring also means we
    //                   never hand back MORE capacity than the manual does.
    //   'none'        - no pixels-per-port cost.
    //   'novastar-ll' - geometric: the table value IS the port's TOTAL, so it
    //                   comes back unchanged. The (1 - Y/H) derate needs each
    //                   port's position and is applied in
    //                   calculatePortAssignments instead.
    applyLowLatencyCapacity(capacity, processorType, lowLatency) {
        if (!lowLatency || !(capacity > 0)) return capacity;
        const profile = this.getLowLatencyProfile(processorType);
        if (!profile || !profile.supported) return capacity;
        const cap = profile.capacity || {};
        if (cap.kind === 'factor') return Math.floor(capacity * cap.factor);
        return capacity;
    }

    // v0.11.0: the geometric Low Latency rules for THIS layer, or null when
    // they do not apply (low latency off, or a processor family whose low
    // latency is a plain capacity change). Returns the descriptor's own
    // capacity block: { yDerate } - true on every NovaStar line, legacy and
    // COEX, per NovaStar's own answer.
    getLowLatencyGeometry(layer) {
        if (!layer || !layer.lowLatency) return null;
        if ((layer.type || 'screen') !== 'screen') return null;
        const profile = this.getLowLatencyProfile(layer.processorType || 'novastar-armor');
        if (!profile || !profile.supported) return null;
        const cap = profile.capacity || {};
        return cap.kind === 'novastar-ll' ? cap : null;
    }

    // v0.11.0: pixel-raster height of the layer's OWN canvas - the H in the
    // NovaStar (1 - Y/H) derate. Panel x/y are already canvas-relative (the
    // server builds them from offset_x/offset_y), so they compare directly
    // against this. Falls back to the pre-canvases project raster, then 0;
    // 0 means "unknown" and callers must not derate rather than guess.
    getLayerCanvasHeight(layer) {
        if (!layer) return 0;
        const canvases = (this.project && this.project.canvases) || [];
        const canvas = (Array.isArray(canvases) && layer.canvas_id)
            ? canvases.find(c => c && c.id === layer.canvas_id)
            : null;
        const height = canvas
            ? Number(canvas.raster_height) || 0
            : Number(this.project && this.project.raster_height) || 0;
        return height > 0 ? height : 0;
    }

    // v0.11.0: capacity of one NovaStar Low Latency port, given the topmost
    // canvas Y of its visible cabinets. Every NovaStar line calls this now -
    // top alignment is a requirement of the mode itself, not a COEX extra.
    // `total` is the plain table lookup at the current bit depth and frame
    // rate - never a fixed constant, so the derate tracks 8/10/12-bit and the
    // frame rate like everything else.
    // Y = 0 (a top-aligned port, which is what a correctly built layout gives)
    // returns `total` untouched. An unknown canvas height derates NOTHING.
    lowLatencyPortCapacity(total, minY, canvasHeight) {
        if (!(total > 0)) return 0;
        if (!(canvasHeight > 0)) return total;
        const factor = Math.min(1, Math.max(0, 1 - ((Number(minY) || 0) / canvasHeight)));
        return Math.floor(factor * total);
    }

    // v0.11.0: NovaStar 5G's minimum Ethernet-port load width, in pixels, or 0
    // for every other processor - which is to say "this rule does not exist
    // there", not "the threshold happens to be zero".
    //
    // PROVENANCE, so nobody widens this later: NovaStar publish the note under
    // the "Ethernet Port Load Capacity" table on their 5G page (XA50 Pro /
    // CA50E receiving cards) and NOWHERE else -
    //   "The load capacity of a single Ethernet port can only achieve its
    //    maximum when the load width is 128 pixels or more. If the load width
    //    is less than that, the load capacity will be reduced accordingly,
    //    calculated as (128 - load width) x load height."
    // It is deliberately NOT applied to novastar-armor, novastar-coex-1g,
    // brompton, megapixel-1g or megapixel-2.5g. The owner has rejected
    // extending it to those lines, including on a "it is the conservative
    // direction" argument: the rule is not published for them, and inventing
    // it would under-report their capacity and add ports to a live show for no
    // reason. Change the processor key here only against a published source.
    novastarMinLoadWidth(processorType) {
        return processorType === 'novastar-5g' ? 128 : 0;
    }

    // v0.11.0: `capacity` less the 5G minimum-load-width penalty, for a port
    // whose VISIBLE cabinets span `width` x `height` pixels.
    //
    // "load width" is the ETHERNET PORT'S load width - the horizontal pixel
    // extent of the cabinets carried on that port - not one cabinet's width.
    // A port carrying two 60 x 120 cabinets side by side is 120 px wide, so
    // 120 < 128 and it IS penalised.
    //
    // Physically the controller reserves a band at least 128 px wide: a port
    // filling only 120 px of it wastes (128 - 120) x height, and the usable
    // capacity drops by exactly that wasted area. Same "reserved area" idea as
    // the Armor bounding-rectangle rule. Clamped at 0 - a port narrow and tall
    // enough to eat the whole figure carries nothing, not a negative.
    minLoadWidthPortCapacity(capacity, processorType, width, height) {
        const minWidth = this.novastarMinLoadWidth(processorType);
        if (!(minWidth > 0) || !(capacity > 0)) return capacity;
        const w = Number(width) || 0;
        const h = Number(height) || 0;
        if (!(w > 0) || !(h > 0) || w >= minWidth) return capacity;
        return Math.max(0, capacity - ((minWidth - w) * h));
    }

    // Calculate port capacity using lookup tables with interpolation
    // v0.11.0: `lowLatency` layers the processor's Low Latency behaviour on
    // top of the raw lookup. Split in two so pass 2, which needs per-port
    // geometry, has a seam that does not disturb the table lookup.
    calculatePortCapacity(bitDepth, frameRate, processorType, lowLatency = false) {
        const capacity = this.lookupPortCapacity(bitDepth, frameRate, processorType);
        return this.applyLowLatencyCapacity(capacity, processorType, lowLatency);
    }

    // Raw manufacturer-table lookup, before any Low Latency behaviour.
    lookupPortCapacity(bitDepth, frameRate, processorType) {
        processorType = processorType || 'novastar-armor';
        const table = this.portCapacityTables[processorType];
        
        if (!table) return 0;
        
        // Find closest bit depth
        const availableBitDepths = Object.keys(table).map(Number);
        let useBitDepth = bitDepth;
        if (!table[bitDepth]) {
            // Find closest available bit depth (prefer higher for safety)
            useBitDepth = availableBitDepths.reduce((best, bd) => 
                Math.abs(bd - bitDepth) < Math.abs(best - bitDepth) ? bd : best
            );
        }
        
        const fpsTable = table[useBitDepth];
        if (!fpsTable) return 0;
        
        // Exact match
        const exactFps = Math.round(frameRate);
        if (fpsTable[exactFps]) return fpsTable[exactFps];
        
        // Interpolate between two closest frame rates
        const fpsList = Object.keys(fpsTable).map(Number).sort((a, b) => a - b);
        
        // Find surrounding entries
        let lower = fpsList[0];
        let upper = fpsList[fpsList.length - 1];
        
        for (let i = 0; i < fpsList.length - 1; i++) {
            if (fpsList[i] <= frameRate && fpsList[i + 1] >= frameRate) {
                lower = fpsList[i];
                upper = fpsList[i + 1];
                break;
            }
        }
        
        // Below the table: clamp UP to the lowest published row. Capacity runs
        // as 1/frame rate, so the lowest published row is LESS capacity than a
        // slower frame rate really has - the conservative direction, more
        // ports than needed and never fewer. It is also the only way 23.976 Hz
        // (offered in the frame rate list, below every table's 24 Hz first
        // row) has an answer at all, and the tables round it to 24 anyway.
        if (frameRate <= fpsList[0]) return fpsTable[fpsList[0]];
        // ABOVE the table: no capacity. DANGEROUS as it stood - this clamped
        // to the LAST row, so novastar-armor (no row past 120 Hz) answered a
        // 240 Hz question with its 120 Hz figure: double the real capacity and
        // therefore half the ports. The group settings dialog can produce
        // exactly that state, because processor, bit depth and frame rate are
        // picked independently of one another.
        //
        // Nothing is extrapolated to replace it. The manufacturer's published
        // table is authoritative and no figure in this app is derived from a
        // formula, so a frame rate the manufacturer does not publish for this
        // processor has no answer - and 0 is the value the UI already treats
        // as "no capacity": Pixels/Port renders "N/A", Panels/Port renders
        // ERROR, Ports Required renders ERROR, and calculatePortAssignments
        // returns no assignment rather than a plausible map. Loud and empty
        // beats quiet and wrong. Use getSupportedFrameRates to see what a
        // processor actually publishes.
        if (frameRate > fpsList[fpsList.length - 1]) return 0;
        
        // Linear interpolation
        const lowerCap = fpsTable[lower];
        const upperCap = fpsTable[upper];
        const ratio = (frameRate - lower) / (upper - lower);
        return Math.floor(lowerCap + (upperCap - lowerCap) * ratio);
    }
    
    // Check if processor uses rectangle-based port assignment (NovaStar Armor only)
    usesRectangleConstraint(processorType) {
        return processorType === 'novastar-armor';
    }
    
    // v0.11.0: keep the Low Latency checkbox and its note in step with the
    // selected layer's processor. The note is the descriptor's own text; when
    // the behaviour is a pass-2 geometric one the note says the constraint is
    // NOT in the figures, so nobody reads an unchanged Pixels/Port as proof
    // that low latency has been accounted for.
    //
    // Three things sit in this area and they each say ONE thing, once:
    //   #low-latency-note        - beside the checkbox, what turning Low
    //                              Latency ON would cost. Shown only while it
    //                              is OFF, because once it is on the rules list
    //                              says the same thing properly and at length.
    //   #low-latency-rules       - under the readout, the rules in force for
    //                              this processor. Shown only while ON.
    //   #low-latency-derate-note - under the rules, what the derate is costing
    //                              THIS screen right now. Shown only when a
    //                              port is actually being derated.
    // Two of the three can be on screen at a time and they never overlap.
    updateLowLatencyUI() {
        const checkbox = document.getElementById('low-latency');
        const note = document.getElementById('low-latency-note');
        // The derate note below the figures is re-stated by
        // updatePortCapacityDisplay once the ports are known; clear it here so
        // it cannot survive that function's early returns on a stale layer.
        this.setLowLatencyDerateNote(null);
        // Same reason: a stale layer's rules must not outlive it.
        this.setLowLatencyRules(null);
        if (!checkbox && !note) return;

        const layer = this.currentLayer;
        const isScreen = !!layer && (layer.type || 'screen') === 'screen';
        const processorType = (isScreen && layer.processorType) || 'novastar-armor';
        const profile = isScreen ? this.getLowLatencyProfile(processorType) : null;
        const supported = !!(profile && profile.supported);
        const enabled = !!(isScreen && layer.lowLatency && supported);

        if (checkbox) {
            checkbox.checked = !!(isScreen && layer.lowLatency);
            checkbox.disabled = !supported;
        }
        if (note) {
            // v0.11.0: stand down once the rules list is up. This note used to
            // show in both states, which put a short version of the rules
            // directly above the long version and read as two half-answers.
            let text = (supported && !enabled) ? (profile.note || '') : '';
            if (text && this.isLowLatencyCapacityPending(processorType)) {
                text += ' Not applied to the figures below yet.';
            }
            note.textContent = text;
            // v0.11.0: the receiving-card list is a tooltip - too long for the
            // note itself, and the MRV328/MRV336 trap is already in the note.
            // Set in both states: the rules list carries the same tooltip on
            // its own card line, and this one is what the checkbox row offers.
            note.title = supported ? (profile.cards || '') : '';
        }
        if (enabled) this.setLowLatencyRules(profile);
    }

    // v0.11.0: list the Low Latency rules in force for the selected layer's
    // processor, directly under the Pixels/Port readout - the one figure that
    // cannot show them. That figure is the flat table lookup for the whole
    // layer, so it carries neither the per-port (1 - Y/H) derate nor the 5G
    // narrow-port penalty, and on its own it can disagree with the per-port
    // percentages on the canvas. This list is what reconciles the two.
    //
    // `profile` is the lowLatencyProfiles entry, or null to clear (Low Latency
    // off, no layer, an image layer, or a stale processor with no entry).
    //
    // DISPLAY ONLY. Every rule here is already in the math - see
    // applyLowLatencyCapacity ('factor' / 'none'), lowLatencyPortCapacity
    // ((1 - Y/H)) and minLoadWidthPortCapacity (the 128 px penalty). The 128 px
    // rule appears only on the entry whose novastarMinLoadWidth is non-zero, so
    // the UI's scope is the math's scope rather than a rule invented for the
    // other lines.
    setLowLatencyRules(profile) {
        const el = document.getElementById('low-latency-rules');
        if (!el) return;
        const rules = (profile && Array.isArray(profile.rules)) ? profile.rules : [];
        el.textContent = '';
        if (rules.length === 0) {
            el.style.display = 'none';
            return;
        }
        rules.forEach(rule => {
            const item = document.createElement('li');
            item.textContent = (rule && rule.text) || '';
            if (rule && rule.tip) item.title = rule.tip;
            el.appendChild(item);
        });
        el.style.display = '';
    }

    // v0.11.0: say WHY a Low Latency port count moved. Pixels/Port is the
    // port's TOTAL; a NovaStar port that does not start at canvas Y=0 keeps
    // only (1 - Y/H) of it, so without this line nudging a screen down the
    // canvas would silently change Ports Required and read as a bug. `derate`
    // is layer._lowLatencyDerate - null whenever nothing was derated, and then
    // the line is cleared.
    setLowLatencyDerateNote(derate) {
        const el = document.getElementById('low-latency-derate-note');
        if (!el) return;
        if (!derate || !(derate.deratedPorts > 0)) {
            el.textContent = '';
            el.style.display = 'none';
            return;
        }
        const verb = derate.deratedPorts === 1 ? 'port starts' : 'ports start';
        el.textContent = `Low Latency: ${derate.deratedPorts} of ${derate.totalPorts} `
            + `${verb} below the top of the ${derate.canvasHeight.toLocaleString()} px `
            + `canvas, so capacity there drops to as little as `
            + `${derate.worstCapacity.toLocaleString()} px, from `
            + `${derate.portCapacity.toLocaleString()} px.`;
        el.style.display = '';
    }

    // Update bit depth dropdown options based on selected processor
    updateBitDepthOptions() {
        const bitDepthSelect = document.getElementById('bit-depth');
        if (!bitDepthSelect || !this.currentLayer) return;
        
        const processorType = this.currentLayer.processorType || 'novastar-armor';
        const supported = this.getSupportedBitDepths(processorType);
        const currentBitDepth = this.currentLayer.bitDepth || 8;
        
        // Update options
        bitDepthSelect.innerHTML = '';
        supported.forEach(bd => {
            const opt = document.createElement('option');
            opt.value = bd;
            opt.textContent = `${bd}-bit`;
            bitDepthSelect.appendChild(opt);
        });
        
        // If current bit depth is still valid, keep it; otherwise pick the first
        if (supported.includes(currentBitDepth)) {
            bitDepthSelect.value = currentBitDepth;
        } else {
            bitDepthSelect.value = supported[0];
            this.currentLayer.bitDepth = supported[0];
        }
    }
}

for (const k of Object.getOwnPropertyNames(_Capacity.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Capacity.prototype, k));
    }
}
