// app-curve: the Header/Footer tab's Curve. A Curve checkbox on the
// selected screens; ticked, a compact form (the curve as a % of a full
// circle or degrees of sweep, concave or convex, Simplest / Even /
// Tightest, how close is close enough, the angles the locks have, and
// where the build starts) and the result: a build sheet strip of the bars
// with the angle at every join between them, a small plan of the wall
// from above against the drawn arc, the readouts, and every way to build
// it, ranked, each with Use this.
//
// The math is the curve calculator's own (curve-math.js). The bar sizes
// are the tab's lit sizes (the stock on the truck), in panel widths; the
// panel width is the screen's own.
//
// CURVE ON MEANS THE CALCULATOR OWNS THAT SCREEN'S BARS AND JOINT ANGLES:
// it lays the screen's bars on its side (header or footer), the tab's
// real bars, so the totals, the pull list and the binder count them, and
// writes the angle at every joint between columns into the screen's 3D
// placement (stage3d.jointsCol, concave positive, flat joints written as
// 0 so the screen-wide column figure never leaks in). Every change is one
// undo step. While Curve is on, Custom does not lay bars on that screen
// and Auto lays the curve again. Turned off, the joints go back to the
// screen-wide figure and the bars stay where they are. Lit sizes that
// cannot cover the wall exactly lay nothing (owner, 2026-11-09): the tab
// names the gap and the screen's bars and joints stay as they are.
//
// THE MATH RUNS IN THE BACKGROUND (curve-worker.js), so the page never
// stops: an edit changes the settings at once, the tab says "Working",
// and the bars and angles land, with the edit, as one undo step when the
// answer comes back. A newer edit of the same screen supersedes an older
// one, and an answer for a screen that has changed since (an undo, a
// reload) is dropped, so a stale result never lands. Answers are kept by
// everything they depend on.
//
// THE DATUM: Left, Center and Right pick at once; the red mark on the plan
// drags onto any panel middle or joint, in half steps (8 is the middle of
// panel 8, 8.5 the joint between 8 and 9), snapped as the calculator snaps
// it. A build picked by hand from Ways to build it holds until anything
// the joints depend on changes, then the app picks again (curvePickKey).
//
// Stored on the layer as riggingCurve (curve-math.js cleanCurve holds its
// shape); a show without it has every screen off, unchanged. The reference
// table of every joint at one angle is left out to keep the tab compact.
import { LEDRasterApp } from './app-core.js';
import { s3dSanitize } from './app-stage3d.js';
import {
    cleanCurve, convertCurveEntry, datumLabel, formatAngle, formatLength, formatSmall, parseAngles,
    screenCurve, snapDatum,
} from './curve-math.js';

const CACHE_MAX = 40;
const NS = 'http://www.w3.org/2000/svg';
const WORKER_URL = '/static/js/curve-worker.js';

const listWords = (names) => (names.length <= 1 ? (names[0] || '')
    : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1]);

class _Curve {
    _wireRiggingCurve() {
        const box = document.getElementById('rigging-curve-on');
        if (!box || box.dataset.wired) return;
        box.dataset.wired = '1';
        box.addEventListener('change', () => this.setRiggingCurveOn(box.checked));
        const group = (sel, key) => document.querySelectorAll(sel).forEach(btn => {
            btn.addEventListener('click', () => this.setRiggingCurveField(key, btn.dataset.value));
        });
        group('#rigging-curve-entry .rigging-curve-btn', 'entry');
        group('#rigging-curve-bend .rigging-curve-btn', 'bend');
        group('#rigging-curve-goal .rigging-curve-btn', 'goal');
        group('#rigging-curve-from .rigging-curve-btn', 'from');
        const field = (id, key) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', () => this.setRiggingCurveField(key, el.value));
        };
        field('rigging-curve-value', 'value');
        field('rigging-curve-tol', 'tolerance');
        field('rigging-curve-angles', 'angles');
        const ways = document.getElementById('rigging-curve-ways');
        if (ways) ways.addEventListener('click', (e) => {
            const btn = e.target && e.target.closest ? e.target.closest('[data-pick]') : null;
            if (btn) this.setRiggingCurveField('pick', btn.dataset.pick);
        });
        this._wireCurvePlanDrag(document.getElementById('rigging-curve-plan'));
    }

    // ---- what is stored ---------------------------------------------------

    riggingCurveOf(layer) {
        return cleanCurve(layer && layer.riggingCurve);
    }

    riggingCurveOn(layer) {
        return !!layer && (layer.type || 'screen') === 'screen' && this.riggingCurveOf(layer).on;
    }

    // Readouts in the show's own unit: meters on a meter show, feet and
    // inches otherwise.
    _curveSystem() {
        return (typeof this.cableUnit === 'function' && this.cableUnit() === 'm') ? 'metric' : 'imperial';
    }

    // Why a screen cannot take a Curve, or '' when it can.
    _curveCannot(layer) {
        const cols = Number(layer.columns) || 0;
        if (this.riggingWallPanels(layer) !== cols) {
            return 'it is turned a quarter, so its bars run down its columns';
        }
        if (this.riggingSideOf(layer) === 'both') return 'it has a header and a footer';
        const row = this.riggingRow(layer, this.riggingSideOf(layer));
        if (row.layers.length > 1) return 'its bars run across its group, and a curve is one screen\'s';
        return '';
    }

    // What the calculator is asked for a screen as it stands.
    _curveInput(layer, settings = null) {
        const s = settings || this.riggingCurveOf(layer);
        return {
            panels: Number(layer.columns) || 0,
            panelWidthM: (Number(layer.panel_width_mm) || 500) / 1000,
            sizes: this._riggingSizesOf(layer),
            settings: { ...s, on: true },
            system: this._curveSystem(),
        };
    }

    // ---- the background calculator -----------------------------------------

    _curveKeep(key, out) {
        if (!this._curveCache) this._curveCache = new Map();
        if (this._curveCache.size >= CACHE_MAX) this._curveCache.delete(this._curveCache.keys().next().value);
        this._curveCache.set(key, out);
    }

    // The answer already worked out for a screen as it stands, or null.
    riggingCurveCached(layer) {
        const key = JSON.stringify(this._curveInput(layer));
        return (this._curveCache && this._curveCache.get(key)) || null;
    }

    // The calculator's answer on this thread, for the tests and for a
    // browser with no workers. Kept like any other answer.
    riggingCurveSolve(layer, settings = null) {
        const input = this._curveInput(layer, settings);
        const key = JSON.stringify(input);
        const hit = this._curveCache && this._curveCache.get(key);
        if (hit) return hit;
        const out = screenCurve(input);
        this._curveKeep(key, out);
        return out;
    }

    _curveWorker() {
        if (this._curveWorkerBroken) return null;
        if (this._curveWorkerObj) return this._curveWorkerObj;
        try {
            if (typeof Worker !== 'function') throw new Error('no workers');
            const w = new Worker(WORKER_URL, { type: 'module' });
            w.onmessage = (e) => {
                const { id, out, error } = e.data || {};
                const job = this._curveJobs && this._curveJobs.get(id);
                if (!job) return;
                this._curveJobs.delete(id);
                if (error) job.resolve(screenCurve(job.input));
                else job.resolve(out);
            };
            w.onerror = () => {
                // The worker could not start or died: every job still
                // waiting is answered here, and the page works on alone.
                this._curveWorkerBroken = true;
                const jobs = [...((this._curveJobs && this._curveJobs.values()) || [])];
                if (this._curveJobs) this._curveJobs.clear();
                jobs.forEach(job => job.resolve(screenCurve(job.input)));
            };
            this._curveWorkerObj = w;
            return w;
        } catch (_) {
            this._curveWorkerBroken = true;
            return null;
        }
    }

    // A promise of the calculator's answer for `input`: kept, shared by
    // everyone who asks while it runs, worked out in the background.
    riggingCurveRequest(input) {
        const key = JSON.stringify(input);
        const hit = this._curveCache && this._curveCache.get(key);
        if (hit) return Promise.resolve(hit);
        if (!this._curvePending) this._curvePending = new Map();
        const pending = this._curvePending.get(key);
        if (pending) return pending;
        const w = this._curveWorker();
        const p = new Promise(resolve => {
            if (!w) {
                setTimeout(() => resolve(screenCurve(input)), 0);
                return;
            }
            if (!this._curveJobs) this._curveJobs = new Map();
            this._curveJobSeq = (this._curveJobSeq || 0) + 1;
            this._curveJobs.set(this._curveJobSeq, { input, resolve });
            w.postMessage({ id: this._curveJobSeq, input });
        }).then(out => {
            this._curvePending.delete(key);
            this._curveKeep(key, out);
            return out;
        });
        this._curvePending.set(key, p);
        return p;
    }

    // True while the calculator is working for the tab.
    riggingCurveBusy() {
        return (this._curveBusy || 0) > 0 || !!(this._curvePending && this._curvePending.size);
    }

    // ---- laying it --------------------------------------------------------

    // The answer written onto the screen: its bars on its side and the
    // angle at every column joint.
    _curveWrite(layer, out) {
        const side = this.riggingSideOf(layer) === 'footer' ? 'footer' : 'header';
        let at = 0;
        this._riggingWrite(layer, side, out.bars.map(size => { const b = { start: at, size }; at += size; return b; }));
        layer.riggingCustom = false;
        const jointsCol = {};
        out.joints.forEach((a, j) => { jointsCol[String(j)] = a; });
        const prev = this._s3dPlacementOf(layer);
        layer.stage3d = s3dSanitize({ ...prev, jointsCol });
    }

    // True when the screen carries exactly this answer's bars and angles.
    _curveLaidMatches(layer, out) {
        const side = this.riggingSideOf(layer) === 'footer' ? 'footer' : 'header';
        const bars = this.riggingPlaced(layer, side);
        let at = 0;
        const want = out.bars.map(size => { const b = { start: at, size }; at += size; return b; });
        if (JSON.stringify(bars.map(b => [b.start, b.size])) !== JSON.stringify(want.map(b => [b.start, b.size]))) return false;
        const table = (layer.stage3d && layer.stage3d.jointsCol) || {};
        const placed = s3dSanitize({ jointsCol: Object.fromEntries(out.joints.map((a, j) => [String(j), a])) }).jointsCol;
        return out.joints.every((_, j) => table[String(j)] === placed[String(j)]);
    }

    // Curve off: the column joints go back to the screen-wide figure.
    _curveUnlay(layer) {
        const prev = layer.stage3d ? s3dSanitize(layer.stage3d) : null;
        if (prev && Object.keys(prev.jointsCol).length) layer.stage3d = { ...prev, jointsCol: {} };
    }

    // The curved screens among `layers` laid again from their settings as
    // they now stand, in the background; when the answers are in, those
    // screens and `others` (whose edit rides in the same step) are saved as
    // one undo step named `action`. False, with nothing scheduled, when
    // none of `layers` is curved. `opts.misses` are rows the caller could
    // not fit, said with any the Curve could not lay.
    riggingCurveRelayLater(layers, action, others = [], opts = {}) {
        const curved = (layers || []).filter(l => this.riggingCurveOn(l) && !this._curveCannot(l));
        if (!curved.length) return false;
        const project = this.project;
        this._curveSeq = (this._curveSeq || 0) + 1;
        const seq = this._curveSeq;
        if (!this._curveLatest) this._curveLatest = new Map();
        const jobs = curved.map(l => {
            const input = this._curveInput(l);
            this._curveLatest.set(l.id, seq);
            return { id: l.id, key: JSON.stringify(input), name: l.name || `Screen ${l.id}`, p: this.riggingCurveRequest(input) };
        });
        const otherIds = [...new Set((others || []).map(l => l.id))];
        // The edit itself is an undo step at once, so an undo pressed while
        // the answer is on its way takes back this edit, not the one
        // before it. The answer, when it lands, joins that same step.
        // An edit made while the one before is still being worked out
        // joins its step: two quick clicks are one undo step.
        const open = this._curveOpenEntry;
        if (open && Array.isArray(this.history) && this.history[this.historyIndex] === open
            && this.historyIndex === this.history.length - 1) {
            this.history.pop();
            this.historyIndex -= 1;
        }
        const before = Array.isArray(this.history) ? this.history[this.historyIndex] : null;
        const commit = [...new Set([...curved, ...(others || [])])];
        this.updateLayers(commit, true, action);
        const entry = Array.isArray(this.history) ? this.history[this.historyIndex] : null;
        const own = entry && entry !== before ? entry : null;
        this._curveOpenEntry = own;
        this._curveBusy = (this._curveBusy || 0) + 1;
        this.refreshRiggingCurve();
        const done = Promise.all(jobs.map(j => j.p)).then(outs => {
            this._curveBusy -= 1;
            // An undo, a redo or a reload since: this answer belongs to a
            // show that is gone.
            if (this.project !== project) { this.refreshRiggingPanel(); return; }
            const byId = (id) => (this.project.layers || []).find(l => l.id === id);
            const changed = [];
            const stale = new Set();
            const misses = [...(opts.misses || [])];
            jobs.forEach((j, i) => {
                // a newer edit of this screen is on its way (it carries this
                // one's change too), or the screen is no longer what was
                // asked about: nothing of this request lands on it
                const live = byId(j.id);
                if (this._curveLatest.get(j.id) !== seq || !live
                    || JSON.stringify(this._curveInput(live)) !== j.key) {
                    stale.add(j.id);
                    return;
                }
                if (outs[i].errors.length) misses.push(j.name);
                else this._curveWrite(live, outs[i]);
                changed.push(live);
            });
            const laid = changed.length > 0;
            otherIds.forEach(id => {
                const live = byId(id);
                if (live && !stale.has(id) && !changed.includes(live)) changed.push(live);
            });
            if (laid) {
                // The edit's own step is still the newest: the answer takes
                // its place, edit and answer as one step. A step made since
                // (another edit) leaves this one its own.
                if (own && this.history[this.historyIndex] === own && this.historyIndex === this.history.length - 1) {
                    this.history.pop();
                    this.historyIndex -= 1;
                }
                this.updateLayers(changed, true, action);
            }
            if (this._curveOpenEntry === own) this._curveOpenEntry = null;
            this.refreshRiggingPanel(misses.length ? misses : undefined);
            if (window.canvasRenderer) window.canvasRenderer.render();
        });
        this._curveLast = done;
        return true;
    }

    // The selected screens (and none locked) that a Curve edit acts on.
    _curveTargets(onlyOn) {
        const screens = this._riggingScreens().filter(l => !onlyOn || this.riggingCurveOn(l));
        return this._writableLayers(screens);
    }

    setRiggingCurveOn(on) {
        const screens = this._curveTargets(false);
        const changed = [];
        const refused = [];
        for (const l of screens) {
            const s = this.riggingCurveOf(l);
            if (on) {
                const why = this._curveCannot(l);
                if (why) { refused.push([l, why]); continue; }
                if (s.on) continue;
                l.riggingCurve = { ...s, on: true };
            } else {
                if (!s.on) continue;
                l.riggingCurve = { ...s, on: false };
                this._curveUnlay(l);
            }
            changed.push(l);
        }
        if (refused.length) {
            this._toast(refused.map(([l, why]) => `${l.name || `Screen ${l.id}`} cannot take a Curve: ${why}.`).join(' '), true, 7000);
        }
        if (changed.length) {
            if (!on || !this.riggingCurveRelayLater(changed, 'Curve On', changed)) {
                this.updateLayers(changed, true, on ? 'Curve On' : 'Curve Off');
            }
        }
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // One field of the form, on every selected screen with its Curve on,
    // laid again. One undo step.
    setRiggingCurveField(key, raw) {
        const screens = this._curveTargets(true);
        if (!screens.length) { this.refreshRiggingPanel(); return; }
        const primary = this._riggingPrimary(screens);
        const base = this.riggingCurveOf(primary);
        const patch = {};
        if (key === 'entry') {
            if (raw !== 'percent' && raw !== 'degrees') return;
            patch.entry = raw;
        } else if (key === 'bend') {
            if (raw !== 'concave' && raw !== 'convex') return;
            patch.bend = raw;
        } else if (key === 'goal') {
            if (!['simplest', 'even', 'tightest'].includes(raw)) return;
            patch.goal = raw;
        } else if (key === 'from') {
            const n = typeof raw === 'number' ? raw : (/^\d+(\.\d+)?$/.test(String(raw)) ? Number(raw) : null);
            if (n !== null) patch.from = n;
            else if (['center', 'left', 'right'].includes(raw)) patch.from = raw;
            else return;
        } else if (key === 'pick') {
            if (raw === 'auto') {
                patch.pick = null;
            } else {
                const out = this.riggingCurveCached(primary);
                if (!out || !out.result || !out.result.options.some(o => o.id === raw)) return;
                patch.pick = { id: String(raw), key: out.pickKey };
            }
        } else if (key === 'value') {
            const v = Number(String(raw).replace(/[%°\s]/g, ''));
            const max = base.entry === 'degrees' ? 360 : 100;
            if (!Number.isFinite(v) || v < 0 || v > max) {
                this._toast(base.entry === 'degrees' ? 'Curve, type degrees of sweep from 0 to 360.' : 'Curve, type a % of a full circle from 0 to 100.', true, 5000);
                this.refreshRiggingPanel();
                return;
            }
            patch.value = v;
        } else if (key === 'tolerance') {
            const v = Number(String(raw).replace(/[a-z"\s]/gi, ''));
            if (!Number.isFinite(v) || v < 0) { this.refreshRiggingPanel(); return; }
            patch.toleranceMm = this._curveSystem() === 'metric' ? v : v * 25.4;
        } else if (key === 'angles') {
            const list = parseAngles(raw);
            if (!list || !list.length) {
                this._toast('Lock angles, type the angles the bars lock at, like 2.5, 5, 7.5, 10.', true, 5000);
                this.refreshRiggingPanel();
                return;
            }
            patch.angles = list;
        } else {
            return;
        }
        const changed = [];
        for (const l of screens) {
            const s = this.riggingCurveOf(l);
            const next = { ...s, ...patch };
            if (typeof next.from === 'number') next.from = snapDatum(next.from, Number(l.columns) || 1);
            // Switching % and degrees says the same curve the other way:
            // the wall does not change.
            if (patch.entry && patch.entry !== s.entry) {
                next.value = Math.round(convertCurveEntry(s.value,
                    s.entry === 'degrees' ? 'sweep_deg' : 'percent_circle',
                    patch.entry === 'degrees' ? 'sweep_deg' : 'percent_circle') * 1e6) / 1e6;
            }
            if (JSON.stringify(next) === JSON.stringify(s)) continue;
            l.riggingCurve = next;
            changed.push(l);
        }
        if (changed.length && !this.riggingCurveRelayLater(changed, 'Curve', changed)) {
            this.updateLayers(changed, true, 'Curve');
        }
        this.refreshRiggingPanel();
        if (window.canvasRenderer) window.canvasRenderer.render();
    }

    // A Custom gesture or a Remove Bar on a curved screen: refused, said
    // in one line. True when refused.
    riggingCurveRefusesHand(layers) {
        const curved = (layers || []).filter(l => this.riggingCurveOn(l));
        if (!curved.length) return false;
        const names = listWords(curved.map(l => l.name || `Screen ${l.id}`));
        this._toast(`${names} ${curved.length === 1 ? 'has its' : 'have their'} bars laid by the Curve. Turn Curve off to lay bars by hand.`, true, 6000);
        return true;
    }

    // ---- the panel --------------------------------------------------------

    refreshRiggingCurve() {
        const block = document.getElementById('rigging-curve');
        const box = document.getElementById('rigging-curve-on');
        if (!block || !box) return;
        const screens = this._riggingScreens();
        const primary = this._riggingPrimary(screens);
        block.style.display = primary ? '' : 'none';
        if (!primary) return;
        const s = this.riggingCurveOf(primary);
        const onCount = screens.filter(l => this.riggingCurveOn(l)).length;
        box.checked = s.on;
        box.indeterminate = onCount > 0 && onCount < screens.length;
        const fields = document.getElementById('rigging-curve-fields');
        if (fields) fields.style.display = s.on ? '' : 'none';
        const note = document.getElementById('rigging-curve-note');
        if (note) {
            note.style.display = s.on ? '' : 'none';
            note.textContent = this._riggingToolNow() === 'custom'
                ? 'The Curve lays this screen\'s bars, so Custom does not. Turn Curve off to lay them by hand.'
                : 'The Curve lays this screen\'s bars from the lit sizes. Auto lays it again.';
        }
        const working = document.getElementById('rigging-curve-working');
        if (!s.on) {
            if (working) working.style.display = 'none';
            return;
        }

        const lit = (sel, value) => document.querySelectorAll(sel).forEach(btn => {
            btn.classList.toggle('active', btn.dataset.value === value);
        });
        lit('#rigging-curve-entry .rigging-curve-btn', s.entry);
        lit('#rigging-curve-bend .rigging-curve-btn', s.bend);
        lit('#rigging-curve-goal .rigging-curve-btn', s.goal);
        lit('#rigging-curve-from .rigging-curve-btn', typeof s.from === 'string' ? s.from : '');
        const fromLabel = document.getElementById('rigging-curve-from-label');
        if (fromLabel) {
            fromLabel.textContent = typeof s.from === 'number'
                ? `From ${datumLabel(snapDatum(s.from, Number(primary.columns) || 1))}. Drag the red dot on the plan to move it.`
                : 'Or drag the red dot on the plan onto any panel or joint.';
        }
        const system = this._curveSystem();
        const set = (id, value) => {
            const el = document.getElementById(id);
            if (el && document.activeElement !== el && el.value !== value) el.value = value;
        };
        set('rigging-curve-value', String(Math.round(s.value * 1000) / 1000));
        set('rigging-curve-tol', system === 'metric'
            ? String(Math.round(s.toleranceMm * 10) / 10)
            : String(Math.round(s.toleranceMm / 25.4 * 100) / 100));
        set('rigging-curve-angles', s.angles.join(', '));
        const tolUnit = document.getElementById('rigging-curve-tol-unit');
        if (tolUnit) tolUnit.textContent = system === 'metric' ? 'mm' : 'in';
        const valueUnit = document.getElementById('rigging-curve-value-unit');
        if (valueUnit) valueUnit.textContent = s.entry === 'degrees' ? 'degrees of sweep' : '% of a circle';

        // The answer for the screen as it stands: kept, or asked for in the
        // background and drawn when it comes.
        let out = this.riggingCurveCached(primary);
        if (!out) {
            const input = this._curveInput(primary);
            this.riggingCurveRequest(input).then(() => this.refreshRiggingCurve());
        }
        if (working) working.style.display = (!out || this.riggingCurveBusy()) ? '' : 'none';
        const errorsEl = document.getElementById('rigging-curve-errors');
        const result = document.getElementById('rigging-curve-result');
        if (!out) {
            if (errorsEl) errorsEl.style.display = 'none';
            return;
        }
        if (errorsEl) {
            errorsEl.style.display = out.errors.length ? '' : 'none';
            errorsEl.textContent = out.errors.join('\n');
        }
        if (result) result.style.display = out.errors.length ? 'none' : '';
        if (out.errors.length) return;
        // A redo can bring back an edit whose answer never landed: say so
        // rather than show a curve the screen does not carry.
        if (note && !this.riggingCurveBusy() && !this._curveLaidMatches(primary, out)) {
            note.textContent = 'These bars and angles are not this curve\'s yet. Press Auto to lay it.';
        }
        this._curveDrawSheet(document.getElementById('rigging-curve-sheet'), out);
        this._curveDrawPlan(document.getElementById('rigging-curve-plan'), out);
        const r = out.result;
        const a = r.achieved;
        const head = document.getElementById('rigging-curve-head');
        if (head) head.textContent = this._curveHeadline(r);
        const len = (m) => formatLength(m, system);
        const rows = [
            ['Sweep', `${formatAngle(a.sweep_deg, 1)}, ${a.percent_circle.toFixed(1)}% of a circle`],
            ['Radius', Number.isFinite(a.radius_face_m) ? `${len(a.radius_face_m)} to the face` : 'straight'],
            ['Width', len(a.chord_m)],
            ['Depth', len(a.depth_m)],
            ['Off the drawing', `${formatSmall(r.max_arc_deviation_m, system)} at worst`],
        ];
        const read = document.getElementById('rigging-curve-readouts');
        if (read) {
            const sig = JSON.stringify(rows);
            if (read.dataset.sig !== sig) {
                read.dataset.sig = sig;
                read.innerHTML = '';
                rows.forEach(([k, v]) => {
                    const row = document.createElement('div');
                    row.style.cssText = 'display: flex; justify-content: space-between; gap: 8px;';
                    const kEl = document.createElement('span');
                    kEl.style.color = '#aaa';
                    kEl.textContent = k;
                    const vEl = document.createElement('span');
                    vEl.textContent = v;
                    vEl.style.textAlign = 'right';
                    row.append(kEl, vEl);
                    read.appendChild(row);
                });
            }
        }
        const reason = document.getElementById('rigging-curve-reason');
        if (reason) reason.textContent = r.choice_reason;
        const warn = document.getElementById('rigging-curve-warnings');
        if (warn) {
            // The bars warning restates the build sheet strip above it.
            const shown = out.warnings.filter(w => !w.startsWith('Bars:'));
            warn.style.display = shown.length ? '' : 'none';
            warn.textContent = shown.join('\n\n');
        }
        this._curveDrawWays(document.getElementById('rigging-curve-ways'), r, system);
    }

    // "7.5° at 9 joints, 6 flat"
    _curveHeadline(r) {
        if (!r.angle_usage.length) return 'Every joint flat: a straight wall';
        const parts = r.angle_usage.map(u => `${formatAngle(u.angle_deg)} at ${u.count} joint${u.count === 1 ? '' : 's'}`);
        if (r.flat_joints) parts.push(`${r.flat_joints} flat`);
        return parts.join(', ');
    }

    // Ways to build it: every candidate build, ranked as the calculator
    // ranks them (the closest and the closest even always among them),
    // the one in use marked, every other with Use this.
    _curveDrawWays(host, r, system) {
        if (!host) return;
        const manual = r.config.pattern_choice !== 'auto' && r.chosen_option_id !== r.recommended_option_id;
        const rows = r.options.map(o => ({
            id: o.id,
            angles: o.used_angles_deg.length ? o.used_angles_deg.map(a => formatAngle(a)).join(' + ') : 'All flat',
            even: o.even && o.used_angles_deg.length > 0,
            joints: `${o.curved_joints} bent, ${o.flat_joints} flat`,
            builds: `${o.percent_circle.toFixed(1)}%`,
            off: `${formatSmall(o.deviation_m, system)} off${o.within_tolerance ? '' : ', over'}`,
            over: !o.within_tolerance,
            chosen: o.id === r.chosen_option_id,
            app: o.id === r.recommended_option_id,
        }));
        const sig = JSON.stringify([rows, manual]);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        const title = document.createElement('div');
        title.style.cssText = 'font-weight: 600; color: #fff; margin: 6px 0 2px;';
        title.textContent = 'Ways to build it';
        host.appendChild(title);
        if (manual) {
            const line = document.createElement('div');
            line.style.cssText = 'display: flex; align-items: center; gap: 6px; color: #aaa; font-size: 11px; margin-bottom: 2px;';
            const words = document.createElement('span');
            words.textContent = 'You picked this one by hand.';
            const back = document.createElement('button');
            back.type = 'button';
            back.className = 'btn btn-secondary';
            back.dataset.pick = 'auto';
            back.textContent = 'Let the app pick';
            back.style.setProperty('padding', '1px 6px', 'important');
            back.style.setProperty('font-size', '11px', 'important');
            line.append(words, back);
            host.appendChild(line);
        }
        rows.forEach(row => {
            const el = document.createElement('div');
            el.className = 'rigging-curve-way';
            el.dataset.way = row.id;
            el.style.cssText = `display: flex; align-items: center; gap: 6px; padding: 3px 0; border-top: 1px solid #2a2a2a; font-size: 11px; color: ${row.chosen ? '#fff' : '#bbb'};`;
            const text = document.createElement('div');
            text.style.cssText = 'flex: 1; min-width: 0;';
            const top = document.createElement('div');
            top.style.cssText = 'font-weight: 600;';
            top.textContent = row.angles + (row.even ? ', even' : '') + (row.chosen ? ', in use' : (row.app ? ', the app\'s pick' : ''));
            const bottom = document.createElement('div');
            bottom.style.color = row.over ? '#f5a623' : '#999';
            bottom.textContent = `${row.joints}, ${row.builds}, ${row.off}`;
            text.append(top, bottom);
            el.appendChild(text);
            if (!row.chosen) {
                const use = document.createElement('button');
                use.type = 'button';
                use.className = 'btn btn-secondary';
                use.dataset.pick = row.id;
                use.textContent = 'Use this';
                use.style.setProperty('padding', '2px 6px', 'important');
                use.style.setProperty('font-size', '11px', 'important');
                use.style.flex = 'none';
                use.setAttribute('data-tooltip', `Use this, build the wall with ${row.angles === 'All flat' ? 'every joint flat' : row.angles}. It holds until the curve, the bars or the wall change.`);
                el.appendChild(use);
            }
            host.appendChild(el);
        });
    }

    // The build sheet strip: the bars left to right, sized to their panels
    // and marked with their size, a tag with the angle on every join that
    // bends, and the datum marked under the strip.
    _curveDrawSheet(host, out) {
        if (!host) return;
        const bars = out.bars;
        const joints = out.joints;
        const panels = joints.length + 1;
        const datum = out.result.datum_at;
        const room = Math.max(120, (host.clientWidth || 200) - 2);
        const sig = JSON.stringify([bars, joints, datum, room]);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        // The strip fits the panel; past 14 px a panel it scrolls instead.
        const slots = Math.max(panels, bars.reduce((t, n) => t + n, 0));
        const W = Math.max(room, Math.round(14 * slots));
        const H = 52;
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('width', String(W));
        svg.setAttribute('height', String(H));
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.style.display = 'block';
        const px = W / slots;
        const add = (tag, attrs, text) => {
            const el = document.createElementNS(NS, tag);
            Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, String(v)));
            if (text != null) el.textContent = text;
            svg.appendChild(el);
            return el;
        };
        const barTop = 22, barH = 16;
        let at = 0;
        bars.forEach((n, i) => {
            const x = at * px;
            add('rect', { x: x + 0.5, y: barTop, width: Math.max(1, n * px - 1), height: barH, fill: '#2a2a2a', stroke: '#888', 'stroke-width': 1, 'data-bar': i });
            add('text', { x: x + n * px / 2, y: barTop + 12, 'text-anchor': 'middle', 'font-size': 10, fill: '#ddd' }, String(n));
            at += n;
        });
        // The tags: the angle at each join that bends, over its seam, on a
        // second line where it would run into the one before.
        const ends = [-Infinity, -Infinity];
        joints.forEach((a, j) => {
            if (!a) return;
            const x = (j + 1) * px;
            const text = formatAngle(Math.abs(a));
            const half = text.length * 2.7 + 1;
            const line = x - half > ends[0] ? 0 : (x - half > ends[1] ? 1 : 0);
            ends[line] = x + half;
            add('line', { x1: x, y1: line ? 11 : barTop - 3, x2: x, y2: barTop + barH, stroke: '#e22330', 'stroke-width': 1.5 });
            add('text', { x, y: line ? 19 : 9, 'text-anchor': 'middle', 'font-size': 9, fill: '#f0f0f0', 'data-angle': j }, text);
        });
        // The datum: where the crew sets out from (0.5 is the left end).
        const dx = (datum - 0.5) * px;
        add('path', { d: `M ${dx} ${barTop + barH + 2} l -5 7 l 10 0 z`, fill: '#e22330', 'data-datum': datum });
        host.appendChild(svg);
    }

    // The wall from above, drawn level, the drawn arc dashed: audience at
    // the bottom. The red mark is the datum, dragged onto any panel middle
    // or joint (_wireCurvePlanDrag).
    _curveDrawPlan(host, out) {
        if (!host) return;
        const r = out.result;
        const face = [];
        r.placements.forEach((p, i) => { if (i === 0) face.push(p.face[0]); face.push(p.face[1]); });
        const arc = r.target_vertices;
        const sig = JSON.stringify([face, r.datum_at, host.clientWidth]);
        if (host.dataset.sig === sig) return;
        host.dataset.sig = sig;
        host.innerHTML = '';
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const p of face.concat(arc)) {
            if (p.x < x0) x0 = p.x;
            if (p.x > x1) x1 = p.x;
            if (p.y < y0) y0 = p.y;
            if (p.y > y1) y1 = p.y;
        }
        const W = Math.max(120, (host.clientWidth || 200) - 2), pad = 8;
        const span = Math.max(1e-6, x1 - x0);
        const k = (W - 2 * pad) / span;
        const H = Math.max(24, Math.min(90, Math.round((y1 - y0) * k + 2 * pad)));
        const kk = Math.min(k, (H - 2 * pad) / Math.max(1e-6, y1 - y0));
        const ox = (W - span * kk) / 2 - x0 * kk;
        const oy = (H - (y1 - y0) * kk) / 2 - y0 * kk;
        const to = (p) => ({ x: p.x * kk + ox, y: p.y * kk + oy });
        const pts = (list) => list.map(p => { const q = to(p); return `${q.x.toFixed(1)},${q.y.toFixed(1)}`; }).join(' ');
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('width', String(W));
        svg.setAttribute('height', String(H));
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.style.display = 'block';
        const line = (list, attrs) => {
            const el = document.createElementNS(NS, 'polyline');
            el.setAttribute('points', pts(list));
            el.setAttribute('fill', 'none');
            Object.entries(attrs).forEach(([a, v]) => el.setAttribute(a, String(v)));
            svg.appendChild(el);
        };
        line(arc, { stroke: '#888', 'stroke-width': 1, 'stroke-dasharray': '3 3' });
        line(face, { stroke: '#e22330', 'stroke-width': 2 });
        // Every spot a crew can set out from: each joint (half steps, the
        // ends at 0.5 and n + 0.5) and each panel's middle.
        const spots = [];
        face.forEach((p, k) => spots.push({ at: k + 0.5, ...to(p) }));
        for (let i = 1; i < face.length; i++) {
            spots.push({ at: i, ...to({ x: (face[i - 1].x + face[i].x) / 2, y: (face[i - 1].y + face[i].y) / 2 }) });
        }
        const here = spots.find(s => s.at === r.datum_at) || spots[0];
        const mark = document.createElementNS(NS, 'circle');
        mark.setAttribute('cx', here.x.toFixed(1));
        mark.setAttribute('cy', here.y.toFixed(1));
        mark.setAttribute('r', '5');
        mark.setAttribute('fill', '#e22330');
        mark.setAttribute('stroke', '#fff');
        mark.setAttribute('stroke-width', '1.5');
        mark.setAttribute('data-datum', String(r.datum_at));
        mark.style.cursor = 'grab';
        svg.appendChild(mark);
        host._curvePlan = { spots, mark, svg, panels: face.length - 1, at: r.datum_at };
        host.appendChild(svg);
    }

    // The nearest spot on the plan to a client point.
    _curvePlanSpot(host, clientX, clientY) {
        const plan = host && host._curvePlan;
        if (!plan) return null;
        const box = plan.svg.getBoundingClientRect();
        const x = clientX - box.left, y = clientY - box.top;
        let best = null, bestD = Infinity;
        for (const s of plan.spots) {
            const d = Math.hypot(s.x - x, s.y - y);
            if (d < bestD) { best = s; bestD = d; }
        }
        return best;
    }

    // Drag the red mark (or press anywhere on the plan) to move the datum.
    // The mark follows the pointer from spot to spot; letting go builds
    // from there. Never selects the page's text.
    _wireCurvePlanDrag(host) {
        if (!host || host.dataset.dragWired) return;
        host.dataset.dragWired = '1';
        host.style.userSelect = 'none';
        host.style.touchAction = 'none';
        let drag = null;
        const show = (spot) => {
            const plan = host._curvePlan;
            if (!plan || !spot) return;
            plan.mark.setAttribute('cx', spot.x.toFixed(1));
            plan.mark.setAttribute('cy', spot.y.toFixed(1));
            plan.mark.setAttribute('data-datum', String(spot.at));
        };
        host.addEventListener('pointerdown', (e) => {
            if (e.button !== 0 || !host._curvePlan) return;
            e.preventDefault();
            drag = { id: e.pointerId, spot: this._curvePlanSpot(host, e.clientX, e.clientY) };
            try { host.setPointerCapture(e.pointerId); } catch (_) {}
            host._curvePlan.mark.style.cursor = 'grabbing';
            show(drag.spot);
        });
        host.addEventListener('pointermove', (e) => {
            if (!drag || e.pointerId !== drag.id) return;
            e.preventDefault();
            drag.spot = this._curvePlanSpot(host, e.clientX, e.clientY) || drag.spot;
            show(drag.spot);
        });
        const end = (e, keep) => {
            if (!drag || e.pointerId !== drag.id) return;
            const spot = drag.spot;
            drag = null;
            try { host.releasePointerCapture(e.pointerId); } catch (_) {}
            if (host._curvePlan) host._curvePlan.mark.style.cursor = 'grab';
            if (keep && spot && spot.at !== host._curvePlan.at) this.setRiggingCurveField('from', spot.at);
            else host.dataset.sig = '';
            if (!keep) this.refreshRiggingCurve();
        };
        host.addEventListener('pointerup', (e) => end(e, true));
        host.addEventListener('pointercancel', (e) => end(e, false));
        host.addEventListener('selectstart', (e) => e.preventDefault());
    }
}

for (const k of Object.getOwnPropertyNames(_Curve.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Curve.prototype, k));
    }
}
