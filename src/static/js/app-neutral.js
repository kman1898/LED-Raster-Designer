// app-neutral: the NEUTRAL of a distro's power in (owner's decision,
// 2026-11-11: "Estimate and warn"). Show the current the power in's
// neutral carries next to the leg amps, LED supply harmonics included,
// and warn when it passes the neutral's rating. The person says whether a
// distro's power in has a 100% or a 200% neutral (`neutral200`).
//
// THE PHYSICS. Every line-to-neutral circuit on a distro returns on the
// one neutral of its power in. Line-to-line circuits (208V on 120/208, 240V
// on 120/240, an L21-30 box) return on the other line and put nothing on
// the neutral.
//
//   * Fundamental. A circuit's current here is the figure the app already
//     shows for it: watts over the circuit's own typed voltage (110 stays
//     ~9% conservative, and watts are read as VA, both kept as they are by
//     the owner's choice). Read as the 60/50 Hz current, it is in phase
//     with its leg's line-to-neutral voltage. On a 3-phase wye the three
//     legs sit 120 degrees apart (X 0, Y -120, Z +120), so the neutral's
//     fundamental is the PHASOR sum of the legs' line-to-neutral currents:
//     a balanced distro cancels to zero, one leg alone returns all of it.
//   * Triplen harmonics. A switch-mode supply draws its current in pulses
//     near the voltage peaks, rich in the 3rd harmonic (and the 9th, 15th,
//     ...). Three times 120 degrees is 360, so the triplens of the three
//     legs are IN PHASE and add arithmetically on the neutral instead of
//     cancelling. With `h` the supply's effective triplen fraction (the
//     triplens' RMS over the fundamental, sqrt(h3^2 + h9^2 + ...)) the
//     neutral's triplen current is sum over legs of h x I_leg.
//   * The two are different frequencies, so they add as RMS:
//         I_N = sqrt(I_N1^2 + I_N3^2)
//     Balanced at I a leg: I_N1 = 0, I_N3 = 3 h I, so I_N = 3 h I.
//     All on X: I_N1 = I, I_N3 = h I, so I_N = I sqrt(1 + h^2) - the whole
//     current X draws, harmonics and all, comes back on the neutral.
//     The non-triplen harmonics (5th, 7th, ...) cancel like the
//     fundamental on a balanced wye and are left out.
//   * Split-phase 120/240. The two hots are 180 degrees apart, and so are
//     their odd harmonics (3 x 180 = 540 = 180), so the neutral carries the
//     DIFFERENCE of the legs, fundamental and triplens alike:
//         I_N = sqrt((I_X1 - I_Y1)^2 + (h_X I_X1 - h_Y I_Y1)^2)
//     which is never more than the busier leg. A 100% neutral is always
//     enough there, so a split-phase distro shows its figure and never
//     warns. A single hot (120V, 230V) returns its line current on the
//     neutral, which the line's own check already covers: no figure.
//   * EU 230/400 is the same wye with 230V line to neutral, every circuit
//     line to neutral.
//
// THE LIMIT. The neutral is rated at the power in's rating per leg, or
// twice it on a 200% neutral. It has no breaker of its own, and NEC
// 215.2(A)(1) lets a grounded conductor that is not on an overcurrent
// device carry 100% of a continuous load, so the warning (red) is past the
// neutral's rating. The 80% continuous figure the legs are held to on a US
// system is shown beside it, and past it reads amber, the way the legs'
// limit reads (distroMainLimit).
import { LEDRasterApp } from './app-core.js';

// The supply settings, as a fraction of the fundamental current (percent).
// Sources, quoted in the 2026-11-11 report to the owner:
//   * Active PFC (low), 33%: LED display supplies with active PFC are rated
//     PF >= 0.95. With the displacement factor at 1, PF = 1 / sqrt(1 +
//     THD^2), so PF 0.95 bounds THD at sqrt(1 / 0.95^2 - 1) = 32.9%, and
//     the triplens can be no more than all of it.
//   * No PFC (high), 87%: a capacitor-input rectifier's 3rd harmonic
//     measured "up to 87% of the fundamental" (IEEE IAS 1993), with the
//     neutral reaching about 1.7 times the line current.
export const SUPPLY_HARMONICS = [
    { id: 'pfc', name: 'Active PFC (low)', pct: 33 },
    { id: 'nopfc', name: 'No PFC (high)', pct: 87 },
];

// PENDING THE OWNER'S RULING (2026-11-11): what a show reads before anyone
// picks a setting. No hardware is assumed, so until he rules it is the
// most conservative well-sourced figure, No PFC. Nothing is written for it:
// an old show opens with no key and reads this.
export const SUPPLY_HARMONICS_DEFAULT = 'nopfc';

// The legs' line-to-neutral angles on a wye, degrees.
const WYE_ANGLE = { X: 0, Y: -120, Z: 120 };

class _Neutral {
    // A stored setting as { id, name, pct }, or null when there is none:
    // 'pfc' / 'nopfc' name a preset, a number 0..100 is a Custom percent.
    _harmonicsRead(v) {
        const preset = SUPPLY_HARMONICS.find(s => s.id === v);
        if (preset) return { ...preset };
        if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null;
        const n = Number(v);
        if (!Number.isFinite(n) || n < 0 || n > 100) return null;
        return { id: 'custom', name: 'Custom', pct: n };
    }

    // The show's setting. `pending` is true while the show has none of its
    // own (the default, until the owner rules on it).
    showSupplyHarmonics() {
        const own = this._harmonicsRead(this.project && this.project.supplyHarmonics);
        if (own) return { ...own, pending: false };
        return { ...this._harmonicsRead(SUPPLY_HARMONICS_DEFAULT), pending: true };
    }

    // One screen's: its own when it has one, else the show's. `own` says
    // which.
    screenSupplyHarmonics(layer) {
        const own = this._harmonicsRead(layer && layer.supplyHarmonics);
        if (own) return { ...own, own: true };
        return { ...this.showSupplyHarmonics(), own: false };
    }

    // The effective triplen fraction a screen's circuits are read at.
    supplyTriplenFraction(layer) {
        return this.screenSupplyHarmonics(layer).pct / 100;
    }

    // "No PFC, 87%" - a setting as a sentence names it.
    supplyHarmonicsText(h) {
        if (!h) return '';
        const pct = `${+Number(h.pct).toFixed(1)}%`;
        return h.id === 'custom' ? `${pct}` : `${h.name.replace(/ \((low|high)\)$/, '')}, ${pct}`;
    }

    // The show's setting, changed: a preset id or a Custom percent. One
    // undo step; the project keeps the key (save_project merges top-level
    // keys).
    setShowSupplyHarmonics(value) {
        const read = this._harmonicsRead(value);
        if (!read) return false;
        const store = read.id === 'custom' ? read.pct : read.id;
        if (this.project.supplyHarmonics === store) return false;
        this.project.supplyHarmonics = store;
        if (typeof this.saveState === 'function') this.saveState('Set LED Supply Harmonics');
        this._persistSupplyHarmonics();
        this.refreshSupplyHarmonicsViews();
        return true;
    }

    _persistSupplyHarmonics() {
        const body = { supplyHarmonics: this.project.supplyHarmonics };
        const send = () => fetch('/api/project', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).catch(() => {});
        this._harmonicsPush = (this._harmonicsPush || Promise.resolve()).then(send);
        return this._harmonicsPush;
    }

    // The screens' own setting: a preset id, a Custom percent, or null to
    // follow the show. A locked screen keeps its own and is named.
    setScreenSupplyHarmonics(layers, value) {
        const read = value === null ? null : this._harmonicsRead(value);
        if (value !== null && !read) return 0;
        const store = read ? (read.id === 'custom' ? read.pct : read.id) : null;
        const same = (l) => (store === null ? l.supplyHarmonics === undefined || l.supplyHarmonics === null
            : l.supplyHarmonics === store);
        const all = (layers || []).filter(l => l && (l.type || 'screen') === 'screen');
        if (typeof this._showLockedError === 'function') {
            this._showLockedError(all.filter(l => this._layerLocked(l) && !same(l)));
        }
        const write = all.filter(l => !(this._layerLocked && this._layerLocked(l)) && !same(l));
        if (!write.length) return 0;
        write.forEach(l => {
            if (store === null) l.supplyHarmonics = null;
            else l.supplyHarmonics = store;
        });
        this.updateLayers(write, true, 'Set LED Supply Harmonics');
        this.refreshSupplyHarmonicsViews();
        return write.length;
    }

    // The tray re-reads every neutral. Deferred past the gesture, as the
    // other Power fields' rebuilds are (_rebuildAfterGesture), so a Tab
    // out of the percent box lands where it was going.
    refreshSupplyHarmonicsViews() {
        this.syncSupplyHarmonicsControls();
        const render = () => {
            if (typeof this.renderHardwareDock === 'function') {
                try { this.renderHardwareDock(); } catch (_) { /* tray not built yet */ }
            }
        };
        if (typeof this._rebuildAfterGesture === 'function') this._rebuildAfterGesture(render);
        else render();
    }

    // ---- the sidebar's two selects ----------------------------------------

    // Static controls in index.html (Power, under Watts per Panel), wired
    // once; synced in place, a focused one left alone.
    syncSupplyHarmonicsControls() {
        this._wireSupplyHarmonicsControls();
        const show = this.showSupplyHarmonics();
        const sel = document.getElementById('power-harmonics-show');
        const pct = document.getElementById('power-harmonics-show-pct');
        if (sel && sel !== document.activeElement) sel.value = show.id;
        if (pct) {
            pct.style.display = show.id === 'custom' ? '' : 'none';
            if (pct !== document.activeElement) pct.value = show.id === 'custom' ? String(show.pct) : '';
        }
        const layer = this.currentLayer;
        const screen = layer && (layer.type || 'screen') === 'screen';
        const own = screen ? this._harmonicsRead(layer.supplyHarmonics) : null;
        const ssel = document.getElementById('power-harmonics-screen');
        const spct = document.getElementById('power-harmonics-screen-pct');
        if (ssel) {
            const follow = ssel.querySelector('option[value=""]');
            if (follow) follow.textContent = `Same as show (${this.supplyHarmonicsText(show)})`;
            if (ssel !== document.activeElement) ssel.value = own ? own.id : '';
        }
        if (spct) {
            spct.style.display = own && own.id === 'custom' ? '' : 'none';
            if (spct !== document.activeElement) spct.value = own && own.id === 'custom' ? String(own.pct) : '';
        }
    }

    _wireSupplyHarmonicsControls() {
        if (this._supplyHarmonicsWired) return;
        const sel = document.getElementById('power-harmonics-show');
        if (!sel) return;
        this._supplyHarmonicsWired = true;
        const pct = document.getElementById('power-harmonics-show-pct');
        sel.addEventListener('change', () => {
            // Custom starts from the figure in force, stored as a percent,
            // and its box opens.
            const v = sel.value === 'custom' ? this.showSupplyHarmonics().pct : sel.value;
            if (!this.setShowSupplyHarmonics(v)) this.syncSupplyHarmonicsControls();
        });
        if (pct) pct.addEventListener('change', () => {
            if (!this.setShowSupplyHarmonics(pct.value)) this.syncSupplyHarmonicsControls();
        });
        const ssel = document.getElementById('power-harmonics-screen');
        const spct = document.getElementById('power-harmonics-screen-pct');
        const targets = () => {
            const layer = this.currentLayer;
            if (!layer) return [];
            return typeof this._socaPanelTargets === 'function' ? this._socaPanelTargets(layer) : [layer];
        };
        if (ssel) ssel.addEventListener('change', () => {
            const v = ssel.value;
            let n = 0;
            if (v === '') n = this.setScreenSupplyHarmonics(targets(), null);
            // Custom starts from the figure the screen reads now.
            else if (v === 'custom') {
                n = this.setScreenSupplyHarmonics(targets(),
                    this.screenSupplyHarmonics(this.currentLayer).pct);
            } else n = this.setScreenSupplyHarmonics(targets(), v);
            if (!n) this.syncSupplyHarmonicsControls();
        });
        if (spct) spct.addEventListener('change', () => {
            if (!this.setScreenSupplyHarmonics(targets(), spct.value)) this.syncSupplyHarmonicsControls();
        });
    }

    // ---- the neutral ---------------------------------------------------------

    // The per-leg store getDistroLoads books line-to-neutral circuits into:
    // `f` the fundamental amps, `h` the triplen amps (h x amps).
    _neutralStore() {
        return { X: { f: 0, h: 0 }, Y: { f: 0, h: 0 }, Z: { f: 0, h: 0 } };
    }

    _bookNeutral(store, leg, amps, frac) {
        if (!store || !store[leg] || !(amps > 0)) return;
        const h = Number.isFinite(frac) && frac >= 0 ? frac : this.showSupplyHarmonics().pct / 100;
        store[leg].f += amps;
        store[leg].h += h * amps;
    }

    // The neutral's rating: the power in's rating per leg (the distro's
    // Rating, which picking an Input sets), twice it on a 200% neutral.
    distroNeutralRatingA(d) {
        const r = Number(d && d.ratingA) || 0;
        return r * (d && d.neutral200 ? 2 : 1);
    }

    // The neutral of one distro from its line-to-neutral store, or null
    // where it carries none (no legs, line-to-line circuits only, nothing
    // on it):
    //   { amps, fundA, triplenA, lnA, ratingA, size (100|200), limitA,
    //     limitPct, us, checked, over, pastLimit, pct }
    // `checked` is false on split-phase, whose neutral never carries more
    // than its busier leg (see the header).
    distroNeutral(d, store) {
        if (!d || !store) return null;
        const names = this.distroLegNames(d);
        if (names.length < 2) return null;
        const lnA = names.reduce((t, k) => t + store[k].f, 0);
        if (!(lnA > 1e-9)) return null;
        let fundA, triplenA;
        if (names.length === 2) {
            fundA = Math.abs(store.X.f - store.Y.f);
            triplenA = Math.abs(store.X.h - store.Y.h);
        } else {
            let re = 0, im = 0;
            for (const k of names) {
                const r = WYE_ANGLE[k] * Math.PI / 180;
                re += store[k].f * Math.cos(r);
                im += store[k].f * Math.sin(r);
            }
            fundA = Math.hypot(re, im);
            // a balanced wye's fundamental is zero, not a rounding residue
            if (fundA < lnA * 1e-12) fundA = 0;
            triplenA = names.reduce((t, k) => t + store[k].h, 0);
        }
        const amps = Math.hypot(fundA, triplenA);
        const ratingA = this.distroNeutralRatingA(d);
        const rule = this.distroMainLimit(d);
        const limitA = ratingA * rule.pct;
        const checked = names.length === 3 && ratingA > 0;
        const over = checked && amps > ratingA + 1e-9;
        return {
            amps, fundA, triplenA, lnA, ratingA,
            size: d.neutral200 ? 200 : 100,
            limitA, limitPct: rule.pct, us: rule.us,
            pct: ratingA > 0 ? (amps / ratingA) * 100 : 0,
            checked,
            over,
            // amber: past the 80% figure but not past the rating (red)
            pastLimit: checked && !over && rule.pct < 1 && amps > limitA + 1e-9,
        };
    }

    // The supply settings a distro's circuits were read at, as words: one
    // setting, or "mixed" where its screens differ.
    distroHarmonicsText(d) {
        const seen = new Map();
        for (const layer of this.project.layers || []) {
            if ((layer.type || 'screen') !== 'screen' || layer.visible === false) continue;
            const on = Object.values(layer.powerSocaDistro || {}).some(id => id === d.id);
            if (!on) continue;
            const h = this.screenSupplyHarmonics(layer);
            seen.set(`${h.id}:${h.pct}`, h);
        }
        if (seen.size > 1) return 'mixed LED supply settings';
        const h = seen.size ? [...seen.values()][0] : this.showSupplyHarmonics();
        return this.supplyHarmonicsText(h);
    }

    // The Power tab's lines about one distro's neutral: red past its
    // rating, amber past the 80% continuous figure. Plain words.
    distroNeutralWarnings(d, load) {
        const N = load && load.neutral;
        if (!N || !N.checked) return [];
        const name = this.distroLabel(d);
        const amps = Math.round(N.amps);
        const us = this.distroRegion(d) !== 'eu';
        if (N.over) {
            const fix = N.size < 200
                ? (us ? 'Use a power in with a 200% neutral, or move 120V circuits to 208V.'
                    : 'Use a power in with a 200% neutral, or spread the load over more distros.')
                : (us ? 'Move 120V circuits to 208V, or spread the load over more distros.'
                    : 'Spread the load over more distros.');
            return [{
                text: `${name}'s power in neutral carries about ${amps} A with LED supply `
                    + `harmonics, over its ${N.size}% neutral (${+N.ratingA.toFixed(1)} A). ${fix}`,
            }];
        }
        if (N.pastLimit) {
            return [{
                mild: true,
                text: `${name}'s power in neutral carries about ${amps} A with LED supply `
                    + `harmonics, past 80% of its ${N.size}% neutral (${+N.limitA.toFixed(1)} A `
                    + `of ${+N.ratingA.toFixed(1)} A).`,
            }];
        }
        return [];
    }

    // The neutral's piece of a LEGS line: "N 38A", red past its rating,
    // amber past 80%, with the figures in its title.
    _dockNeutralChip(d, load) {
        const N = load && load.neutral;
        if (!d || !N) return null;
        const el = document.createElement('span');
        el.className = 'hw-dock-legs-n';
        el.dataset.lrdNeutral = d.id;
        el.textContent = `N ${N.amps.toFixed(0)}A`;
        if (N.over) el.classList.add('hw-dock-legs-n-over');
        else if (N.pastLimit) el.classList.add('hw-dock-legs-n-warn');
        el.title = this.distroNeutralTitle(d, N);
        return el;
    }

    distroNeutralTitle(d, N) {
        const fig = (a) => `${a.toFixed(1)} A`;
        const lines = [`Neutral on the power in: about ${fig(N.amps)} with LED supply harmonics `
            + `(${this.distroHarmonicsText(d)}).`];
        if (N.checked) {
            lines.push(`Rated ${fig(N.ratingA)}, a ${N.size}% neutral`
                + (N.limitPct < 1 ? `; 80% of it is ${fig(N.limitA)}.` : '.'));
            lines.push('The 120V circuits\' currents partly cancel on the neutral, but the '
                + 'supplies\' third-harmonic currents add up on it. Set 100% or 200% '
                + 'neutral behind the distro\'s gear.');
        } else {
            lines.push('On a split-phase distro the neutral carries the difference between '
                + 'the two legs, never more than the busier leg.');
        }
        return lines.join(' ');
    }

    // "38.2 A with LED supply harmonics (No PFC, 87%) · 100% neutral 30 A ·
    // OVER" - the binder's Neutral line.
    distroNeutralText(d, N, num = (x) => x.toFixed(1)) {
        if (!N) return '';
        const parts = [`${num(N.amps)} A with LED supply harmonics (${this.distroHarmonicsText(d)})`];
        if (N.checked) {
            parts.push(`${N.size}% neutral ${+N.ratingA.toFixed(1)} A`);
            if (N.over) parts.push('OVER');
            else if (N.pastLimit) parts.push(`past 80% (${+N.limitA.toFixed(1)} A)`);
        } else {
            parts.push('the difference between the legs');
        }
        return parts.join(' · ');
    }
}

for (const k of Object.getOwnPropertyNames(_Neutral.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Neutral.prototype, k));
    }
}
