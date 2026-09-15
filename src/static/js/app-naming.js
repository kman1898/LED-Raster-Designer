// app-naming: the label engine for LEDRasterApp - port labels (processor
// first, then per-layer overrides and templates), the return-label rule,
// multi/circuit naming and shared-soca resolution, circuit letters and
// colours. The label editors' focus-preserving rebuild helpers live here
// with the editors they serve.
import { LEDRasterApp } from './app-core.js';

class _Naming {

    // The label this port takes off the processor, or null when it takes none
    // - which is every port of every project that defines no processor.
    //
    // Split out from getPortLabelText only so the label editor can ask the
    // same question without re-deriving it: it needs to know not just what the
    // label is but where it came from, because a box the user can type in that
    // no longer changes the drawing is a trap.
    getProcessorPortLabel(layer, portNum) {
        const onProcessor = this._processorPortLabels
            && this._processorPortLabels[String(layer && layer.id)];
        return (onProcessor && onProcessor[portNum]) || null;
    }

    // The same question for the RETURN end of the same socket. A separate
    // lookup rather than a suffix rule here, because the return label is now
    // resolved where the primary is (resolve_card): a name typed on the
    // return end wins, and only an untyped one derives from the primary
    // (deriveReturnLabel). Same per-frame budget as the primary: two object
    // lookups, nothing resolved.
    getProcessorPortReturnLabel(layer, portNum) {
        const onProcessor = this._processorPortReturnLabels
            && this._processorPortReturnLabels[String(layer && layer.id)];
        return (onProcessor && onProcessor[portNum]) || null;
    }

    // The return end's name when nobody typed one: the primary with its
    // leading P turned into an R, else the primary with an R after it.
    //
    // P is primary and R is redundant - that is what the screen's own
    // templates say (P# out, R# back), and a card named P1 has to read the
    // same way: P1-1 out, R1-1 back, never P1-1R. Case follows the name
    // (p1-1 back as r1-1). The P is a prefix only when what follows it is
    // not a letter - a digit (P1-1), a separator (P-1), or nothing (P); a P
    // that begins a word (PORT-3, PANEL-2, Px) is the first letter of a
    // name and there is nothing to swap. Those, and every primary with no
    // P at all - SR-1, HOUSE-LEFT - keep the R after them, so a drawing
    // already issued with SR-1R prints SR-1R again.
    //
    // The server states this rule in derive_return_label (processor_catalog)
    // and every resolved port arrives with its return already derived; this
    // copy exists for the Processors panel's placeholders, which advertise
    // the rule before a port has a label, and as the frame loop's fallback
    // for an index with no return entry. A test holds the two byte-for-byte.
    deriveReturnLabel(primary) {
        if (!primary) return null;
        const first = primary.charAt(0);
        // ASCII letters only, spelt the same way the server spells it, so
        // the two copies cannot disagree over what counts as a letter.
        const word = /^[A-Za-z]/.test(primary.slice(1, 2));
        if (!word) {
            if (first === 'P') return `R${primary.slice(1)}`;
            if (first === 'p') return `r${primary.slice(1)}`;
        }
        return `${primary}R`;
    }

    // The one place a port's label is decided. The canvas, both label editors
    // and every export come through here, so a rule added here reaches all of
    // them at once - and a second path added anywhere else would print one
    // thing on screen and another on the PDF.
    getPortLabelText(layer, portNum, type) {
        // THE PROCESSOR NAMES ITS OWN PORTS, AND IT WINS OUTRIGHT.
        //
        // A port that is assigned to a sending-card port takes that port's
        // label - the name on the card or the box a tech is standing in front
        // of - and no per-layer override applies to it. That is the point of
        // the Processors panel: the wall labels itself off the machine driving
        // it instead of off a template typed into every screen. The way to
        // change an assigned port's label is to rename the port, or the card,
        // in the Processors panel; both ends of the run take that name.
        //
        // BOTH ENDS, NOT THE SAME TEXT. A redundant loop leaves the socket and
        // comes back to it, so the two ends print at opposite corners of the
        // wall and the drawing is the only thing saying which is which. Two
        // labels reading SR-1 make a backup run impossible to trace, which is
        // the one job the return label has. The return end is nameable in the
        // Processors panel the same way the primary is - the house's backup
        // loom is often labelled off its own series, BU-1 back for SR-1 out -
        // and a typed name arrives here through the return index. With none
        // typed the return is derived from the primary (deriveReturnLabel):
        // P1-1 out, R1-1 back - which is what P1 / R1 said before a
        // processor was naming anything - and SR-1 out, SR-1R back where
        // there is no P to swap.
        //
        // _processorPortLabels and _processorPortReturnLabels are flat
        // layerId -> portNum -> label lookups, rebuilt only when the
        // assignment changes (see _indexAssignmentLabels in
        // app-port-assignment.js). This runs for every port of every screen
        // on every frame, so it must never resolve anything itself.
        const assigned = this.getProcessorPortLabel(layer, portNum);
        if (type === 'return') {
            const assignedReturn = this.getProcessorPortReturnLabel(layer, portNum);
            if (assignedReturn) return assignedReturn;
            if (assigned) return this.deriveReturnLabel(assigned);
        } else if (assigned) {
            return assigned;
        }

        // No processor in the project, or a port that is not on one: exactly
        // what every project did before processors existed, override included.
        // This is the fallback that keeps drawings already issued printing the
        // labels they were issued with.
        const template = type === 'return' ? (layer.portLabelTemplateReturn || 'R#') : (layer.portLabelTemplatePrimary || 'P#');
        const overrides = type === 'return' ? (layer.portLabelOverridesReturn || {}) : (layer.portLabelOverridesPrimary || {});
        if (overrides && overrides[portNum]) return overrides[portNum];
        return template.replace('#', portNum);
    }

    // The template broken into the parts a label is built from:
    // <prefix><number><separator>#<suffix>, e.g. S1-#, S2-#, MULTI3-#.
    // `ok` is false for a template with no multi number in it at all (C#),
    // which has no multi concept to name and falls back to the raw replace.
    _powerTemplateParts(layer) {
        const raw = String((layer && layer.powerLabelTemplate) || 'S1-#');
        const m = raw.match(/^(.*?)(\d+)([^#\d]*)#(.*)$/);
        if (!m) return { ok: false, raw, prefix: '', start: 1, sep: '-', suffix: '' };
        return {
            ok: true, raw,
            prefix: m[1], start: parseInt(m[2], 10) || 1,
            sep: m[3], suffix: m[4],
        };
    }

    // A DERIVED multi name is <base><number> - a distro named SL numbers its
    // multis SL1, SL2, and that shape reads correctly. A base that ITSELF
    // ends in a digit does not: the default distro name is DISTRO 1, and
    // glueing its multis on printed DISTRO 11, DISTRO 12 - unreadable as
    // anything but distros eleven and twelve. So a digit-ending base takes a
    // separator before the number - the same one the screen's label template
    // carries (the '-' of S1-#), so the circuit labels built on top of the
    // name stay in one register: DISTRO 1-1 yields DISTRO 1-1-1..-6.
    // Only derived names come through here. A hand-typed multi name is the
    // user's text and is never reformatted.
    _deriveMultiName(base, number, tpl) {
        const sep = /\d$/.test(base) ? ((tpl && tpl.sep) || '-') : '';
        return `${base}${sep}${number}`;
    }

    // Old projects keyed the per-multi stores - lengths, tail positions,
    // breaker offsets, distro assignments - by the number the SCREEN's own
    // template produced, so `S3-#` stored its multis under 3, 4, 5. That was
    // only safe while the number WAS the identity. It is not any more: a
    // multi's number now comes from the distro it lands on, so keying by it
    // would orphan a multi's length and its tails the moment it was assigned.
    //
    // The stable identity is (layer, socaIndex) - the 1-based ordinal of the
    // multi inside its own screen's circuit plan - exactly as a port is
    // identified by (layerId, index) on the Data tab. The shift back to it is
    // the template's own start digit minus one, which is zero for every
    // project on the default `S1-#`.
    _socaKeyShift(layer) {
        return Math.max(0, this._powerTemplateParts(layer).start - 1);
    }

    // Rekey one layer's per-multi stores onto the stable index, once.
    //
    // The stamp is what makes it once: it rides on the layer through every
    // save path, so a project that has already been rekeyed is never shifted a
    // second time - which on an `S3-#` screen would walk its keys down past 1
    // and delete them.
    migrateSocaKeying(layer) {
        if (!layer || layer.powerSocaKeying === 'index') return false;
        layer.powerSocaKeying = 'index';
        const shift = this._socaKeyShift(layer);
        if (!shift) return false;
        let changed = false;
        for (const field of ['powerSocaDistro', 'powerSocaLengths',
                             'powerSocaPhasePos', 'powerSocaPhaseOffset',
                             'powerSocaNames', 'powerSocaNumber']) {
            const map = layer[field];
            if (!map || typeof map !== 'object') continue;
            const next = {};
            for (const key of Object.keys(map)) {
                const n = parseInt(key, 10);
                // Not a multi number, so not ours to move. Carried across
                // rather than dropped: this pass rewrites the store, and
                // anything it did not understand still has to survive it.
                if (!Number.isFinite(n)) { next[key] = map[key]; continue; }
                const idx = n - shift;
                if (idx >= 1) next[idx] = map[key];
            }
            layer[field] = next;
            changed = true;
        }
        return changed;
    }

    // What a multi is CALLED, and which physical tail of its 6-way fan each
    // circuit lands on - for the whole show, prepared once.
    //
    // It is show-wide because a multi's number is: numbering runs per distro,
    // over every screen, in layer-list order BOTTOM UP - which is project
    // layer order, the same order the Data tab hands out card ports
    // (_assignmentScreens: "project layer order, untouched"). Numbering per
    // screen is what let two screens both own an S1.
    //
    // THE NAME LADDER, top wins, mirroring manual -> box -> card -> processor
    // on the Data tab:
    //   1. an explicit powerLabelOverrides entry - handled by the label
    //      authority itself, because that names one CIRCUIT, not a multi
    //   2. the multi's own name, if somebody typed one
    //   3. the distro's name plus the multi's number under it: two multis on
    //      a distro named SL are SL1 and SL2, so their circuits read SL1-1..6.
    //      A digit-ending distro name gets a separator first (_deriveMultiName):
    //      DISTRO 1's multis are DISTRO 1-1, DISTRO 1-2, never DISTRO 11
    //   4. the screen's powerLabelTemplate prefix plus the number - the
    //      fallback for a multi on no distro. Numbered PER SCREEN from the
    //      template's own number (S1-# -> S1, S2, S3 on every screen that
    //      carries it), never out of a show-wide bucket: uniqueness across
    //      screens is the distro's job, not the template's (ruling
    //      2026-09-03, "SL main starts with 7-1")
    //
    // The circuits a screen is NAMED by. For an automatic screen that is its
    // plan. For a screen in custom mode it is the circuits the user DREW
    // and nothing else - never the automatic requirement screenCircuits
    // offers an unrouted custom screen for the distro roll-ups. That
    // fallback is the right count of cables to order, but as a naming
    // source it is a phantom: on the user's 28-wide wall it is empty (a
    // full row does not fit one circuit) and on a narrower wall it is 52
    // circuits that vanish the moment the first cabinet is clicked. A label
    // read off it named the active circuit by boxes that were never going
    // to exist (user, 2026-09-03: "i dont even have a port drawn and it
    // shows S3-1 but when i draw it changes to 1-1"). An unrouted custom
    // screen has no multis, so it takes no multi numbers and shifts no
    // other screen's - its first drawn circuit opens its first box.
    _labelCircuits(layer) {
        if (!layer || typeof this.screenCircuits !== 'function') return [];
        if (this.isCustomPower(layer) && !this.usesCustomCircuits(layer)) return [];
        return this.screenCircuits(layer) || [];
    }

    // Cached by layer object for the current render burst and dropped on the
    // next microtask: getPowerCircuitLabel runs for every circuit of every
    // screen on every frame, so it must never walk the show itself.
    _powerNaming(layer) {
        if (!this._circuitTailCache) {
            this._circuitTailCache = new Map();
            Promise.resolve().then(() => { this._circuitTailCache = null; });
        }
        let entry = this._circuitTailCache.get(layer);
        if (entry) return entry;
        // A miss rebuilds the WHOLE show, not this layer: one screen's numbers
        // depend on every screen before it, so there is no such thing as
        // naming one of them on its own.
        const screens = ((this.project && this.project.layers) || [])
            .filter(l => (l.type || 'screen') === 'screen');
        // Every pinned number per distro, collected BEFORE any number is
        // issued: auto numbering deals around a pin wherever it sits in
        // layer order, the way auto port numbering deals around a pinned
        // port. The circuit plans are kept and handed down so each screen
        // is planned once per rebuild, not once per pass.
        const pins = new Map();         // distro id -> Set(pinned numbers)
        const circuitsBy = new Map();
        for (const l of screens) {
            const circuits = this._labelCircuits(l);
            circuitsBy.set(l, circuits);
            const assign = l.powerSocaDistro || {};
            const chosen = l.powerSocaNumber || {};
            const count = this._socaSegments(l, circuits.length).length;
            for (let idx = 1; idx <= count; idx++) {
                // A pin means nothing off a distro: the number is the slot on
                // a physical box, and with no box named there is no slot.
                const d = assign[idx];
                const n = parseInt(chosen[idx], 10);
                if (!d || !Number.isFinite(n) || n < 1) continue;
                const set = pins.get(d) || new Set();
                set.add(n);
                pins.set(d, set);
            }
        }
        const seq = new Map();          // distro id ('' = unassigned) -> issued
        for (const l of screens) {
            this._circuitTailCache.set(l,
                this._namingFor(l, seq, pins, circuitsBy.get(l)));
        }
        // Second pass, once every multi has its number: two multis pinned to
        // one (distro, number) are ONE physical box, and a box's tails can
        // only be dealt with every member on the table.
        this._resolveSharedSocas(screens);
        entry = this._circuitTailCache.get(layer);
        if (!entry) {
            // A screen no project holds - a preset preview, a paste in
            // flight. Number it on its own rather than leave it nameless.
            // A pin on such a screen has no show to share with, so it
            // resolves standalone: stored tails or the natural 1..L.
            entry = this._namingFor(layer, new Map(), new Map());
            for (const rec of entry.socas.values()) {
                if (!rec.pinned) continue;
                rec.positions = this.socaCircuitPositions(
                    // read the STORE only - rec.positions is still null, so
                    // the pinned branch below cannot answer yet. The
                    // breakout type rides along so the tail clamp reads the
                    // screen's own box size, not the default six.
                    { powerSocaPhasePos: layer.powerSocaPhasePos,
                      powerBreakoutType: layer.powerBreakoutType },
                    rec.index, rec.circuits.length);
                rec.moved = !rec.positions.every((p, i) => p === i + 1);
                rec.circuits.forEach((num, i) => entry.slots.set(num, {
                    multi: rec.index, number: rec.number, name: rec.name,
                    tail: rec.positions[i], moved: rec.moved,
                }));
            }
            this._circuitTailCache.set(layer, entry);
        }
        return entry;
    }

    // One screen's share of the naming index, taking its numbers from the
    // running per-distro sequence the caller carries across screens - and
    // dealing those numbers around `pins`, the show-wide set of hand-picked
    // slots per distro. A pinned multi takes exactly the number picked;
    // its tails wait for _resolveSharedSocas, which knows whether the pin
    // shares its box.
    _namingFor(layer, seq, pins, circuitsIn) {
        const tpl = this._powerTemplateParts(layer);
        const socas = new Map();        // socaIndex -> {number, name, ...}
        const slots = new Map();        // circuit num -> {multi, tail, moved}
        if (!layer || typeof this.screenCircuits !== 'function') {
            return { socas, slots, tpl };
        }
        const circuits = circuitsIn || this._labelCircuits(layer);
        const assign = layer.powerSocaDistro || {};
        const named = layer.powerSocaNames || {};
        const chosen = layer.powerSocaNumber || {};
        const distros = this.getDistros();
        const perSoca = new Map();      // socaIndex -> [circuit num], plan order
        // Same split-aware segmentation as getSocaPlan - the naming index
        // and the plan must never disagree on what a multi is.
        const idxOf = this._socaIndexByOrdinal(
            this._socaSegments(layer, circuits.length));
        circuits.forEach((c, ci) => {
            const idx = idxOf[ci + 1];
            const arr = perSoca.get(idx) || [];
            arr.push(c.num);
            perSoca.set(idx, arr);
        });
        for (const [idx, nums] of perSoca) {
            const distroId = assign[idx] || null;
            const pin = distroId ? parseInt(chosen[idx], 10) : NaN;
            const pinned = Number.isFinite(pin) && pin >= 1;
            let number;
            if (pinned) {
                number = pin;
            } else if (distroId) {
                // Next auto number ON THAT DISTRO, skipping every slot a
                // pin claimed - a pin owns its number outright, wherever
                // the pinned screen sits in layer order. With no pins this
                // is the plain per-distro sequence it has always been.
                const taken = (pins && pins.get(distroId)) || null;
                let n = seq.get(distroId) || 0;
                do { n += 1; } while (taken && taken.has(n));
                seq.set(distroId, n);
                number = n;
            } else {
                // No distro: the SCREEN'S OWN template numbers its multis,
                // from the template's number, per screen - S1-# names this
                // screen's boxes S1, S2, S3 whatever every other screen
                // prints. These multis used to take numbers out of a
                // show-wide "unassigned" bucket in layer order, so a show
                // of four S1-# screens with no distro read S1, S6, S7 and
                // S12 down its layer list (user, 2026-09-03: "look at all
                // the drawn ports they are all wrong SL main starts with
                // 7-1"). Ruling: uniqueness across screens is not the
                // template's job - a distro names its multis uniquely, a
                // template names them the way it says. This is also the
                // number the pre-index arithmetic always printed, so the
                // per-screen ordinal and the raw number agree wherever the
                // drawn set has no gap.
                number = tpl.start + idx - 1;
            }
            const hand = String(named[idx] || '').trim();
            const name = this._multiNameFor(layer, idx, number, distroId, tpl, distros);
            if (pinned) {
                // Tails deferred: whether this pin shares its (distro,
                // number) - and therefore which tails are free - is only
                // knowable once every screen is numbered. The slots are
                // stamped in _resolveSharedSocas with the rest.
                socas.set(idx, {
                    index: idx, number, name, distroId, hand: !!hand,
                    pinned: true, circuits: nums.slice(),
                    positions: null, moved: false, share: null,
                });
                continue;
            }
            const pos = this.socaCircuitPositions(layer, idx, nums.length);
            const moved = !pos.every((p, i) => p === i + 1);
            socas.set(idx, {
                index: idx, number, name, distroId, hand: !!hand,
                pinned: false, circuits: nums.slice(), positions: pos, moved,
                share: null,
            });
            nums.forEach((num, i) => slots.set(num, {
                multi: idx, number, name, tail: pos[i], moved,
            }));
        }
        return { socas, slots, tpl };
    }

    // Rungs 2-4 of the name ladder for one multi (rung 1, the per-circuit
    // override, is the label authority's): the name somebody typed on it,
    // else its distro's name plus its number under that distro, else the
    // screen's template prefix plus its number. One function so the multis
    // the plan holds and the one a circuit is about to open climb the same
    // ladder - _predictedCircuitSlot names the box a not-yet-drawn circuit
    // will land on with this, and it must print what _namingFor will print
    // once the circuit is drawn.
    _multiNameFor(layer, idx, number, distroId, tpl, distros) {
        const hand = String(((layer && layer.powerSocaNames) || {})[idx] || '').trim();
        if (hand) return hand;
        const list = distros || this.getDistros();
        const distro = distroId ? list.find(d => d.id === distroId) : null;
        const base = distro ? String(distro.name || '').trim() : '';
        if (base) return this._deriveMultiName(base, number, tpl);
        return tpl.ok ? this._deriveMultiName(tpl.prefix, number, tpl) : '';
    }

    // Deal each shared box's six tails across its members, and say out loud
    // when they do not fit.
    //
    // Member order is PROJECT LAYER ORDER (soca index within a screen) -
    // the same bottom-up walk that numbers the multis - so the earlier
    // screen owns the lower tails and the wall reads on in order across the
    // seam. Within its slice every member's circuits ascend in wall order,
    // the same rule a single screen has always followed.
    //
    // Per member: a valid stored tail set (phase balancing, a hand move, a
    // join stamping the incumbents) is the user's arrangement and is NEVER
    // rearranged - stored sets claim their tails FIRST, so an unstored
    // member deals into the tails no stored set holds, wherever either
    // member sits in layer order. Two stored sets landing on one tail is a
    // CLASH, reported on the tiles the way port assignment reports an
    // occupied socket - both print verbatim, nothing is rearranged. Layer
    // order decides tails only among the unstored members. A box asked for
    // more than 6 legs runs off the fan: the extra circuits take tails
    // 7, 8, ... and the box reports the overflow - a soca has six tails,
    // and pretending otherwise would hide the one fact a tech needs.
    _resolveSharedSocas(screens) {
        const boxes = new Map();        // 'distroId:number' -> [{layer, entry, rec}]
        for (const l of screens) {
            const entry = this._circuitTailCache.get(l);
            if (!entry) continue;
            for (const rec of entry.socas.values()) {
                if (!rec.pinned) continue;
                const key = `${rec.distroId}:${rec.number}`;
                const arr = boxes.get(key) || [];
                arr.push({ layer: l, entry, rec });
                boxes.set(key, arr);
            }
        }
        for (const [key, members] of boxes) {
            const taken = new Set();
            let clash = false, overflow = false;
            // The physical box has as many tails as the SMALLEST member
            // breakout says it does - six for socas, three for an L21-30 -
            // and every claim past that is overflow whichever member made
            // it. Members of one box virtually always agree; when they do
            // not, the smaller figure is the only honest capacity.
            const cap = Math.min(...members
                .map(m => this.socaBoxSize(m.layer)));
            // Pass 1: every stored set takes exactly its tails. Doing this
            // before ANY dealing is what makes a stored set law: an
            // unstored member earlier in layer order can no longer sit
            // down on tails a later member's paperwork already claims.
            const dealt = [];
            for (const m of members) {
                const L = m.rec.circuits.length;
                const saved = ((m.layer.powerSocaPhasePos) || {})[m.rec.index];
                const valid = Array.isArray(saved) && saved.length === L
                    && saved.every(p => Number.isInteger(p) && p >= 1 && p <= cap)
                    && new Set(saved).size === L;
                if (!valid) { dealt.push(m); continue; }
                const pos = saved.slice().sort((a, b) => a - b);
                m.rec.clashTails = pos.filter(p => taken.has(p));
                m.rec.overTails = pos.filter(p => p > cap);
                pos.forEach(p => taken.add(p));
                m.rec.positions = pos;
            }
            // Pass 2: the unstored members take the box's free tails in
            // member (layer) order - the initial construction of a box in
            // one gesture, and the only place layer order breaks a tie.
            for (const m of dealt) {
                const L = m.rec.circuits.length;
                const pos = [];
                let t = 1;
                while (pos.length < L) {
                    if (!taken.has(t)) pos.push(t);
                    t += 1;
                }
                m.rec.clashTails = [];
                m.rec.overTails = pos.filter(p => p > cap);
                pos.forEach(p => taken.add(p));
                m.rec.positions = pos;
            }
            for (const m of members) {
                m.rec.moved = !m.rec.positions.every((p, i) => p === i + 1);
                if (m.rec.clashTails.length) clash = true;
                if (m.rec.overTails.length) overflow = true;
            }
            for (const m of members) {
                m.rec.share = members.length > 1 ? {
                    key, number: m.rec.number, distroId: m.rec.distroId,
                    clash, overflow,
                    members: members.map(x => ({
                        layerId: x.layer.id, layerName: x.layer.name,
                        soca: x.rec.index, legs: x.rec.circuits.length,
                        tails: x.rec.positions.slice(),
                        clashTails: x.rec.clashTails.slice(),
                        overTails: x.rec.overTails.slice(),
                    })),
                } : null;
                m.rec.circuits.forEach((num, i) => m.entry.slots.set(num, {
                    multi: m.rec.index, number: m.rec.number, name: m.rec.name,
                    tail: m.rec.positions[i], moved: m.rec.moved,
                }));
            }
        }
    }

    // THE ONE PLACE A CIRCUIT'S LABEL IS DECIDED. The canvas bubbles, the soca
    // panel, the splitter rows, the distro feeds list, the label editor and
    // every export come through here, so a rule added here reaches all of them
    // at once - and a second path anywhere else would print one thing on
    // screen and another on the PDF.
    getPowerCircuitLabel(layer, circuitNum) {
        const overrides = layer.powerLabelOverrides || {};
        // THE USER'S TEXT, AND IT WINS OUTRIGHT. Nothing below ever rewrites
        // a label somebody typed - drawings already issued keep printing what
        // they were issued with.
        if (overrides && overrides[circuitNum]) return overrides[circuitNum];
        const nm = this._powerNaming(layer);
        const tpl = nm.tpl;
        const slot = nm.slots.get(parseInt(circuitNum, 10));
        // The multi's name, then the tail it lands on. The tail is the TRUE
        // PHYSICAL TAIL of the 6-way fan: identical to the sequence position
        // until phase balancing or a breaker offset moves the multi's circuits
        // onto other tails, at which point the wall reads S1-1, S1-2, S1-3,
        // S1-5, S1-6 - the occupied tails ascending in wall order, gaps where
        // a tail is skipped.
        if (slot && slot.name) {
            return `${slot.name}${tpl.sep}${slot.tail}${tpl.suffix}`;
        }
        // A template with no multi number in it has no multi to name.
        if (!tpl.ok) return tpl.raw.replace('#', circuitNum);
        // A circuit the plan does not hold: the number the custom badge is
        // drawing under before its first cabinet lands, an editor row past
        // the drawn circuits. It is named by WHERE IT WILL LAND - the multi
        // and the tail the index above hands it the moment it holds a
        // cabinet - and never by arithmetic on the raw number. The two used
        // to disagree the moment the drawn numbers had a gap in them (a
        // cleared circuit, a skipped number, a splitter merge): the plan
        // names a circuit by its position on the fan, so with 2 empty the
        // drawn 13 lands on ordinal 12 and reads S2-6, while floor((13-1)/6)
        // said S3-1. The badge printed the arithmetic and the bubble printed
        // the plan (user, 2026-09-03: "it would say 3-1 and do 2-6. 2-6 was
        // actually correct. then it would go to 3-2 and i'd be drawing
        // 3-1"). One authority, one answer, before and after the click.
        const p = this._predictedCircuitSlot(layer, nm, circuitNum);
        return `${p.name}${tpl.sep}${p.tail}${tpl.suffix}`;
    }

    // Where circuit `circuitNum` WOULD land if it were drawn now: the multi
    // and physical tail the naming index will give it once it holds a
    // cabinet. Its ordinal is its place among the plan's circuit numbers
    // (with no gap that is the number itself), its multi the split-aware
    // segment that ordinal falls in, and its tail the box's lowest free tail
    // dealt in wall order with the tails already occupied - so a contiguous
    // 1..12 predicts 13 as S3-1, and 1,3..12 predicts 13 as S2-6, exactly
    // what the drawn circuit reads. A multi the plan does not have yet takes
    // the next number in its bucket and the same name ladder _namingFor
    // walks (hand-typed, distro-derived, template), so the label is the
    // label the wall prints, not a guess at it.
    _predictedCircuitSlot(layer, nm, circuitNum) {
        const n = Math.max(1, parseInt(circuitNum, 10) || 1);
        const drawn = [...nm.slots.keys()];
        const ordinal = drawn.filter(k => k < n).length + 1;
        const segs = this._socaSegments(layer, drawn.length + 1);
        const seg = segs.find(s => ordinal >= s.start && ordinal <= s.end)
            || segs[segs.length - 1];
        const idx = seg.index;
        const at = ordinal - seg.start + 1;
        const rec = nm.socas.get(idx);
        if (rec) {
            // The box exists: the newcomer takes its lowest free tail, and
            // the box's tails are then read ascending in wall order - the
            // same rule socaCircuitPositions applies to a stored set.
            const have = (rec.positions || []).slice();
            let free = 1;
            while (have.includes(free)) free += 1;
            const tails = have.concat(free).sort((a, b) => a - b);
            return { name: rec.name, tail: tails[at - 1] || at };
        }
        // A multi the plan does not have yet, numbered the way _namingFor
        // will number it once it exists. On no distro that is the screen's
        // own template number for this multi index - per screen, so the
        // first box a screen opens is S1 whatever the rest of the show
        // prints. On a distro it is the running sequence of that distro,
        // walked in PROJECT LAYER ORDER up to and including this screen,
        // next free number, every pin on the distro skipped - not "the
        // show's last number plus one", which on a show whose FIRST screen
        // is the one being drawn named its first box after every box the
        // later screens already had. Its name comes off the same ladder the
        // drawn multis climb.
        const distroId = (layer.powerSocaDistro || {})[idx] || null;
        let number = nm.tpl.start + idx - 1;
        if (distroId) {
            const screens = ((this.project && this.project.layers) || [])
                .filter(l => (l.type || 'screen') === 'screen');
            const entryOf = (l) => (this._circuitTailCache && this._circuitTailCache.get(l))
                || (l === layer ? nm : null);
            const pinned = new Set();
            let seq = 0;
            for (const l of screens.includes(layer) ? screens : [layer]) {
                const entry = entryOf(l);
                if (!entry) continue;
                for (const r of entry.socas.values()) {
                    if (r.distroId !== distroId) continue;
                    if (r.pinned) pinned.add(r.number);
                    else if (l === layer || screens.indexOf(l) < screens.indexOf(layer)) {
                        seq = Math.max(seq, r.number);
                    }
                }
            }
            number = seq;
            do { number += 1; } while (pinned.has(number));
        }
        const name = this._multiNameFor(layer, idx, number, distroId, nm.tpl);
        const pos = this.socaCircuitPositions(layer, idx, at);
        return { name, tail: pos[at - 1] || at };
    }

    getDefaultPowerCircuitColors() {
        return {
            A: '#BC382F',
            B: '#CC6B30',
            C: '#D2E94D',
            D: '#2CF82B',
            E: '#2145DC',
            F: '#7414F5'
        };
    }

    normalizeHexColor(value, fallback = '#FF0000') {
        const raw = String(value || '').trim();
        if (/^#[0-9a-fA-F]{6}$/.test(raw)) return raw.toUpperCase();
        if (/^[0-9a-fA-F]{6}$/.test(raw)) return `#${raw.toUpperCase()}`;
        return fallback;
    }

    normalizePowerCircuitColors(colors) {
        const defaults = this.getDefaultPowerCircuitColors();
        const next = { ...defaults };
        if (colors && typeof colors === 'object') {
            Object.keys(defaults).forEach(letter => {
                if (colors[letter]) {
                    next[letter] = this.normalizeHexColor(colors[letter], defaults[letter]);
                }
            });
        }
        // Migrate old default green (Circuit 4) to the new default.
        if ((next.D || '').toUpperCase() === '#79FC4C') {
            next.D = defaults.D;
        }
        return next;
    }

    getPowerCircuitLetter(circuitNum) {
        let n = Math.max(1, parseInt(circuitNum, 10) || 1);
        let out = '';
        while (n > 0) {
            n -= 1;
            out = String.fromCharCode(65 + (n % 26)) + out;
            n = Math.floor(n / 26);
        }
        return out;
    }

    getPowerCircuitColor(layer, circuitNum) {
        const colors = this.normalizePowerCircuitColors(layer && layer.powerCircuitColors);
        const n = Math.max(1, parseInt(circuitNum, 10) || 1);
        const slots = ['A', 'B', 'C', 'D', 'E', 'F'];
        const slotKey = slots[(n - 1) % slots.length];
        return colors[slotKey] || '#BC382F';
    }

    // Keep the caret where the user put it across an editor rebuild.
    //
    // Editing a label and pressing Tab fires the input's `change` handler,
    // which PUTs to the server. The browser moves focus to the NEXT input
    // immediately; the rebuild (`list.innerHTML = ''`) only happens a
    // round-trip later, when the response - or the socket `layer_updated`
    // echo - lands. By then the field the user is typing in is the one the
    // rebuild destroys, so focus falls to <body> and the next keystroke goes
    // nowhere. Pressing Tab again appears to work only because an unedited
    // field fires no `change` and nothing rebuilds.
    //
    // Capture the focused field's stable key plus its caret, then restore in
    // a microtask: that runs after the synchronous rebuild whichever return
    // path the builder takes, and does not care which of the two triggers
    // fired.
    _preserveEditorFocus() {
        const active = document.activeElement;
        const key = active && active.dataset ? active.dataset.lrdField : null;
        if (!key) return;
        let start = null;
        let end = null;
        try {
            start = active.selectionStart;
            end = active.selectionEnd;
        } catch (_) {
            // Not every input type exposes a selection (number, color, ...).
            start = null;
            end = null;
        }
        Promise.resolve().then(() => {
            const el = document.querySelector(`[data-lrd-field="${key}"]`);
            // Gone - the port/circuit count shrank out from under it. Leave
            // focus alone rather than throwing.
            if (!el || el === document.activeElement) return;
            // A collapsed section swallows focus() silently (the field is
            // display:none), so the restore opens the section first - the
            // stated rule for any programmatic focus into a folded section.
            if (typeof this._expandSectionsFor === 'function') {
                this._expandSectionsFor(el);
            }
            try {
                el.focus();
            } catch (_) {
                return;
            }
            if (start === null || typeof el.setSelectionRange !== 'function') return;
            try {
                el.setSelectionRange(start, end);
            } catch (_) { /* selection unsupported on this element */ }
        });
    }

    // The synchronous sibling of the round-trip delay _preserveEditorFocus()
    // was written for.
    //
    // The label editors above only rebuild when the PUT response (or socket
    // echo) lands, so by the time their wipe runs the Tab gesture is over and
    // document.activeElement IS the field the user landed in - the helper can
    // see it and put it back. Several editors in this suite (the Port List
    // name cells, the patch rail, the distro panel, the soca runs) restate
    // their DOM synchronously inside the field's own `change` handler
    // instead. That runs MID-gesture: the browser has already chosen the next
    // tab stop but not focused it yet, so the wipe destroys a target no
    // capture can know about and focus falls to <body>.
    //
    // So those sites push the restate one macrotask out. The gesture then
    // completes onto the real element, and the rebuild that follows goes
    // through _preserveEditorFocus() exactly like every round-trip rebuild
    // does. Model writes and undo snapshots stay in the handler - only the
    // DOM restatement moves.
    _rebuildAfterGesture(fn) {
        setTimeout(fn, 0);
    }

    // The per-port override editor died with the Signal sidebar. The
    // overrides themselves are untouched: the Fallback Labels block in
    // Data Settings bulk-applies and clears them, an assigned port renames
    // on its dock chip, and the canvas keeps drawing every stored
    // override. Kept as a no-op because every "labels may have moved" path
    // calls it.
    updatePortLabelEditor() {
    }


    // Same story on the power side: the per-circuit override edits on its
    // circuit chip in the dock (which every naming path already redraws),
    // and the Circuit Labels block in Power Settings bulk-applies and
    // clears. Kept as a no-op for its callers.
    updatePowerLabelEditor() {
    }


    updatePowerCircuitColorEditor() {
        if (!this.currentLayer) return;
        const section = document.getElementById('power-circuit-color-section');
        const list = document.getElementById('power-circuit-color-list');
        if (section) {
            section.style.display = this.currentLayer.powerColorCodedView ? 'block' : 'none';
        }
        if (!list) return;
        this._preserveEditorFocus();
        list.innerHTML = '';
        const colors = this.normalizePowerCircuitColors(this.currentLayer.powerCircuitColors);
        Object.keys(colors).forEach((letter, index) => {
            const row = document.createElement('div');
            row.style.display = 'grid';
            row.style.gridTemplateColumns = '20px 26px 1fr';
            row.style.gap = '6px';
            row.style.alignItems = 'center';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.setAttribute('data-circuit-letter', letter);
            cb.dataset.lrdField = `power-circuit-color-${letter}`;

            const swatch = document.createElement('div');
            swatch.style.width = '20px';
            swatch.style.height = '20px';
            swatch.style.borderRadius = '4px';
            swatch.style.border = '1px solid #333';
            swatch.style.background = colors[letter];

            const text = document.createElement('div');
            text.style.fontSize = '12px';
            text.style.color = '#ccc';
            text.textContent = `Circuit ${index + 1}`;

            row.appendChild(cb);
            row.appendChild(swatch);
            row.appendChild(text);
            list.appendChild(row);
        });
    }
}

for (const k of Object.getOwnPropertyNames(_Naming.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Naming.prototype, k));
    }
}
