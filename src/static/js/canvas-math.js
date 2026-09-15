// canvas.js mixin: Pure port-capacity math: pixel load, capacity and load stats for a port's panels. No drawing.
// Classic script. Loads after canvas.js (which declares class CanvasRenderer)
// and before main.js; every method here lands on CanvasRenderer.prototype by
// name, so a name defined in two canvas-*.js files is a silent overwrite -
// tests/test_js_modules.py fails on that.
Object.assign(CanvasRenderer.prototype, {
    // v0.11.0: pixel load of ONE port, in the same terms calculatePortAssignments
    // charged it. The accounting differs per processor and both forms live here
    // so the custom-path branch (which never goes through calculatePortAssignments)
    // is scored the same way the automatic map is:
    //   - rectangle-constraint processors (NovaStar Armor) pay for the pixel
    //     RECTANGLE that encloses every visible cabinet in the port, holes and
    //     all - the same rect calcBoundingRectLoad builds;
    //   - everything else pays the sum of the cabinets' pixel areas, which for
    //     these processors is exactly the running `load` the port map used
    //     (hidden cabinets never reach the traversal there, getOrderedPanelsByPattern
    //     drops them unless the processor is a rectangle one).
    //
    // v0.11.0 screen groups: the rectangle branch unions raw p.x / p.y across
    // the port's cabinets, and for a port that runs onto a group peer that is
    // still the right thing - panel coords are laid out from layer.offset_x by
    // _build_panels, so they are CANVAS-relative, and two members of the same
    // processor canvas already share one frame. Converting to show-look world
    // coords first would be actively wrong: it would fold in each member's
    // Show Look offset, which is where the screen was dragged for the show
    // file, not where the processor sees the pixels. The frame is enforced by
    // the caller (_crossMemberLoadPanels refuses a port whose cabinets straddle
    // two processor rasters, which Show Look's show_canvas_id can produce).
    getPortPixelLoad(layer, portPanels) {
        const app = window.app;
        if (!app || !layer || !Array.isArray(portPanels)) return 0;
        const visible = portPanels.filter(p => p && !p.hidden);
        if (visible.length === 0) return 0;

        const usesRectangle = typeof app.usesRectangleConstraint === 'function'
            && app.usesRectangleConstraint(layer.processorType || 'novastar-armor');
        if (!usesRectangle) {
            return visible.reduce((sum, p) => sum + app.getPanelPixelArea(p), 0);
        }

        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        visible.forEach(p => {
            const x1 = Number(p.x) || 0;
            const y1 = Number(p.y) || 0;
            const x2 = x1 + (Number(p.width) || 0);
            const y2 = y1 + (Number(p.height) || 0);
            if (x1 < minX) minX = x1;
            if (y1 < minY) minY = y1;
            if (x2 > maxX) maxX = x2;
            if (y2 > maxY) maxY = y2;
        });
        return (maxX - minX) * (maxY - minY);
    },

    // v0.11.0: capacity of ONE port, so a percentage is always measured against
    // the capacity THAT port actually has. The base figure is the app's own
    // table lookup (never re-derived here); on NovaStar Low Latency the
    // (1 - Y/H) derate is then applied from the port's OWN topmost cabinet,
    // exactly as calculatePortAssignments does, so a port that starts low on
    // the canvas is scored against its reduced figure and not the table value.
    // layer._lowLatencyDerate is the sidebar note's layer-wide summary, so it
    // is only a fallback here - it carries the worst case, not this port's.
    //
    // v0.11.0: the NovaStar 5G narrow-port penalty is then subtracted, from
    // this port's OWN bounding box, in the same order calculatePortAssignments
    // uses (table value -> Y-derate -> penalty). Without it a penalised 5G port
    // would be scored as a percentage of a capacity it does not have.
    //
    // v0.11.0 screen groups: `layer` is always the port's OWNER, even when the
    // port runs onto a group peer, and every figure below is read from it. That
    // is not laziness about which member to ask - the port is physically on the
    // owner's processor, so the owner's bit depth, frame rate, processor type
    // and low-latency flag are the ones that decide what it can carry. It also
    // matters that they are not blended: GROUP_SHARED_SETTINGS validates
    // processorType, bitDepth and frameRate at group creation, but lowLatency
    // and portMappingMode are only propagated on EDIT, so a group built before
    // that can hold members that disagree. Mixing them would produce a capacity
    // no member actually has.
    //
    // The 5G narrow-port penalty and the (1 - Y/H) derate both stay meaningful
    // across members because they measure the port's own bounding box against
    // the processor canvas, and same-canvas members' panel coords already share
    // that frame - see _crossMemberLoadPanels, which also refuses to hand this
    // function a port whose cabinets straddle two processor rasters.
    getPortCapacityForPanels(layer, portPanels) {
        const app = window.app;
        if (!app || !layer || typeof app.calculatePortCapacity !== 'function') return 0;
        const processorType = layer.processorType || 'novastar-armor';
        const base = app.calculatePortCapacity(
            layer.bitDepth || 8,
            layer.frameRate || 60,
            processorType,
            !!layer.lowLatency
        );
        if (!(base > 0)) return 0;

        const visible = (portPanels || []).filter(p => p && !p.hidden);
        // The app's own function does the arithmetic and owns the scope guard;
        // this only measures the port. A no-op on every processor but 5G.
        const withWidthPenalty = (capacity) => {
            if (visible.length === 0) return capacity;
            if (typeof app.minLoadWidthPortCapacity !== 'function') return capacity;
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            visible.forEach(p => {
                const x1 = Number(p.x) || 0;
                const y1 = Number(p.y) || 0;
                const x2 = x1 + (Number(p.width) || 0);
                const y2 = y1 + (Number(p.height) || 0);
                if (x1 < minX) minX = x1;
                if (y1 < minY) minY = y1;
                if (x2 > maxX) maxX = x2;
                if (y2 > maxY) maxY = y2;
            });
            return app.minLoadWidthPortCapacity(
                capacity, processorType, maxX - minX, maxY - minY);
        };

        const geometry = typeof app.getLowLatencyGeometry === 'function'
            ? app.getLowLatencyGeometry(layer)
            : null;
        if (!geometry || !geometry.yDerate) return withWidthPenalty(base);

        const canvasHeight = typeof app.getLayerCanvasHeight === 'function'
            ? app.getLayerCanvasHeight(layer)
            : 0;
        if (!(canvasHeight > 0) || typeof app.lowLatencyPortCapacity !== 'function') {
            // No honest H: derate nothing rather than guess, which is what the
            // port map itself does. The recorded derate, when present, carries
            // the same underated figure.
            const derate = layer._lowLatencyDerate;
            return withWidthPenalty(
                (derate && derate.portCapacity > 0) ? derate.portCapacity : base);
        }

        if (visible.length === 0) return base;
        const minY = Math.min(...visible.map(p => Number(p.y) || 0));
        return withWidthPenalty(app.lowLatencyPortCapacity(base, minY, canvasHeight));
    },

    // v0.11.0: how full one port is, as a percentage of ITS capacity. Returns
    // null when there is no capacity figure to measure against (unknown
    // processor, image layer), so callers draw nothing rather than "NaN%".
    //
    // 100% IS A GOOD PORT. A port filled exactly to capacity is legal and
    // reads 100 in the ordinary colour; only one that exceeds capacity is a
    // fault. This used to treat load == capacity as over, which drew a red
    // badge on a port that fits.
    //
    // The digits and the colour still always agree, which is the property
    // worth keeping: a port that fits can never print more than 100, and one
    // that does not can never print less than 101. Without those clamps a
    // 100.4% port would round to a passing-looking "100" while glowing red,
    // and a 99.6% port would print 100 with no way to tell it apart from a
    // port that is genuinely full.
    getPortLoadStats(layer, portPanels) {
        const capacity = this.getPortCapacityForPanels(layer, portPanels);
        if (!(capacity > 0)) return null;
        const load = this.getPortPixelLoad(layer, portPanels);
        const percent = (load / capacity) * 100;
        const over = load > capacity;
        const shown = over
            ? Math.max(101, Math.round(percent))
            : Math.min(100, Math.round(percent));
        return {
            load,
            capacity,
            percent,
            shown,
            // Binary: a port either fits or it does not. There used to be an
            // amber 90%+ "warn" band, which made sense while 100% was a fault
            // and you wanted warning before it. Now that a port filled exactly
            // to capacity is legal, amber marked good ports as suspect - and a
            // drawing where every healthy port is plain means any colour on it
            // is a real problem.
            state: over ? 'over' : 'ok'
        };
    },
});
