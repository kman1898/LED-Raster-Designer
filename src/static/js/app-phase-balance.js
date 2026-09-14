// app-phase-balance: the 3-phase balancing engine for LEDRasterApp - the
// search over partly-filled multis, the suggest/apply pair, the Balance
// dialog and the phasing help sheet. It also owns the phasing schemes,
// leg phasors and per-soca circuit positions / phase offsets the engine
// and the distro panel both read.
import { LEDRasterApp } from './app-core.js';

class _PhaseBalance {

    // Every PARTLY-FILLED multi that lands on a 3-phase distro, with the
    // tail set it currently occupies. The unit of balancing is the multi,
    // so this is what the balancer searches over. Full multis are excluded:
    // under the wall-order rule the only lever is WHICH tails a multi uses,
    // and a 6-circuit multi uses all six - there is nothing to choose.
    //
    // `distroId` scopes the walk to one distro. Balancing is per distro now
    // (each Balance button lives on its distro's row): legs never interact
    // across services, so a show-wide pass was only ever N independent
    // problems solved at once - and it moved multis on distros the user was
    // not looking at. No argument keeps the show-wide walk for the callers
    // that genuinely want every distro (clearPhaseBalance's preview, tests).
    _balanceTargets(distroId) {
        const out = [];
        const distros = this.getDistros();
        const seenBoxes = new Set();
        for (const layer of (this.project.layers || [])) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const circuitV = parseFloat(layer.powerVoltage) || 0;
            for (const s of this.getSocaPlan(layer)) {
                const d = distros.find(x => x.id === assign[s.soca]);
                if (!d || d.phase !== 3) continue;
                if (distroId && d.id !== distroId) continue;
                const share = this.getSocaShare(layer, s.soca);
                if (share) {
                    // A shared box is ONE multi to the balancer: its
                    // used-tail set spans every member, and moving tails
                    // re-deals the whole box - member order (layer order),
                    // ascending within each member, the same rule
                    // _resolveSharedSocas states. Emitted once, at the
                    // first member; a box already in clash or overflow has
                    // no legal arrangement to search, so it is left alone
                    // until the clash is resolved.
                    if (seenBoxes.has(share.key)) continue;
                    seenBoxes.add(share.key);
                    if (share.clash || share.overflow) continue;
                    const total = share.members.reduce((t, m) => t + m.legs, 0);
                    const members = share.members.map(m => {
                        const ml = (this.project.layers || [])
                            .find(l => l.id === m.layerId);
                        return ml ? { layer: ml, soca: m.soca, legs: m.legs,
                                      tails: m.tails.slice() } : null;
                    }).filter(Boolean);
                    if (members.length !== share.members.length) continue;
                    // Full is full against the BOX's fan - the smallest
                    // member breakout's size, the same capacity the shared
                    // deal answers to. Six for socas, three for an L21-30.
                    const boxSize = Math.min(...members
                        .map(m => this.socaBoxSize(m.layer)));
                    if (total >= boxSize) continue;
                    // per-circuit amps and labels, member order - index k of
                    // from/to below is the k-th circuit of this walk
                    const legsDetail = members.flatMap(m =>
                        (this.getSocaPlan(m.layer)
                            .find(x => x.soca === m.soca) || { legs: [] }).legs);
                    members.forEach(m => {
                        const saved = (m.layer.powerSocaPhasePos || {})[m.soca];
                        m.hadStore = Array.isArray(saved);
                        m.savedStore = m.hadStore ? saved.slice() : null;
                    });
                    out.push({
                        layer, soca: s.soca, name: s.name, distroId: d.id,
                        legs: total, members, boxSize,
                        layerName: members.map(m => m.layer.name).join(' + '),
                        positions: members.flatMap(m => m.tails)
                            .sort((a, b) => a - b),
                        fromFlat: members.flatMap(m => m.tails),
                        amps: legsDetail.map(l => l.amps),
                        labels: legsDetail.map(l => l.label),
                        scheme: this._circuitSchemeFor(d, circuitV).id
                    });
                    continue;
                }
                if (s.legs.length >= this.socaBoxSize(layer)) continue;
                out.push({
                    layer, soca: s.soca, name: s.name, distroId: d.id,
                    legs: s.legs.length,
                    boxSize: this.socaBoxSize(layer),
                    positions: this.socaCircuitPositions(layer, s.soca, s.legs.length),
                    amps: s.legs.map(l => l.amps),
                    // The circuits' CURRENT labels through the one authority,
                    // captured before the search mutates the store - the
                    // balance dialog names each moved circuit by the bubble
                    // on the canvas, never by a re-derived ordinal.
                    labels: s.legs.map(l => l.label),
                    scheme: this._circuitSchemeFor(d, circuitV).id
                });
            }
        }
        return out;
    }

    // Why nothing on this distro is movable, said in the balancer's own
    // terms. The reference show pressed Balance and read silence: the DJ
    // booths' three multis were assigned to C2 but the grouped wall's auto
    // plan errors out, so the multis do not EXIST - and the dialog computed
    // to a no-op without saying why. Every reason a multi is passed over is
    // collected here so the no-targets dialog can state them instead:
    //   full     6-circuit multis (and full shared boxes) - nothing to choose
    //   clashed  shared boxes left alone until their tail clash/overflow is
    //            resolved
    //   phantom  screens whose powerSocaDistro names this distro for a multi
    //            the current circuit plan does not produce - an empty plan
    //            (power error, peer-served member) or one that shrank
    _balanceBlockers(distroId) {
        const out = { full: [], clashed: [], phantom: [] };
        if (!distroId) return out;
        const seenBoxes = new Set();
        for (const layer of (this.project.layers || [])) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const plan = this.getSocaPlan(layer);
            for (const s of plan) {
                if (assign[s.soca] !== distroId) continue;
                const share = this.getSocaShare(layer, s.soca);
                if (share) {
                    if (seenBoxes.has(share.key)) continue;
                    seenBoxes.add(share.key);
                    // deduped: a box whose members are two multis of ONE
                    // screen should not name the screen twice
                    const names = [...new Set(share.members
                        .map(m => m.layerName))].join(' + ');
                    if (share.clash || share.overflow) {
                        out.clashed.push({ name: s.name, layers: names,
                            overflow: !!share.overflow });
                    } else if (share.members.reduce((t, m) => t + m.legs, 0)
                            >= this.socaBoxSize(layer)) {
                        out.full.push({ name: s.name, layers: names });
                    }
                    continue;
                }
                if (s.legs.length >= this.socaBoxSize(layer)) {
                    out.full.push({ name: s.name, layers: layer.name });
                }
            }
            // Assignments pointing past the plan: the multi the user set up
            // is not in the drawing any more. Say so - this is exactly the
            // state that reads as "balancing won't calculate".
            const have = new Set(plan.map(s => s.soca));
            const missing = Object.keys(assign)
                .filter(k => assign[k] === distroId
                    && !have.has(parseInt(k, 10)));
            if (missing.length) {
                out.phantom.push({
                    layers: layer.name, count: missing.length,
                    reason: plan.length
                        ? 'the circuit plan no longer reaches that multi'
                        : (this._socaPlanEmptyReason(layer)
                            || 'the screen routes no circuits'),
                });
            }
        }
        return out;
    }

    // Deal a shared box's chosen tail SET across its members: ascending
    // tails to members in member order, each member's slice ascending - the
    // box-wide statement of the wall-order rule.
    _dealBoxTails(members, tailSet) {
        const sorted = tailSet.slice().sort((a, b) => a - b);
        let off = 0;
        for (const m of members) {
            const store = m.layer.powerSocaPhasePos
                || (m.layer.powerSocaPhasePos = {});
            store[m.soca] = sorted.slice(off, off + m.legs);
            off += m.legs;
        }
    }

    // Worst imbalance, which is what we minimise - across every 3-phase
    // distro show-wide, or over the one distro a scoped balance is working.
    _worstImbalance(distroId) {
        return this.getDistroLoads()
            .filter(b => b.id && b.legs && (!distroId || b.id === distroId))
            .reduce((m, b) => Math.max(m, b.imbalancePct), 0);
    }

    // Search WHICH tails of the fan each partly-filled multi uses.
    //
    // Wall-order rule: circuits always map to the chosen tails ascending in
    // wall order, so the search space is tail SUBSETS (C(6,L) per multi -
    // at most 20), never permutations. They still multiply across multis, so
    // this is greedy local search: repeatedly try every single-tail change
    // (swap one used tail for a free one, re-sort), keep improvements, stop
    // when nothing helps. Deterministic. Where circuit loads are equal this
    // finds exactly what the old permutation search found - the phase math
    // only sees the subset; where they differ, wall order deliberately wins
    // over the last few percent of imbalance.
    //
    // Nothing is persisted; the project is restored before returning.
    //
    // `distroId` scopes both the targets and the figure being minimised to
    // one distro - the per-distro Balance button's path. Unscoped remains
    // the show-wide search it always was.
    suggestPhaseBalance(distroId) {
        const targets = this._balanceTargets(distroId);
        const before = this._worstImbalance(distroId);
        if (!targets.length) return { before, after: before, targets: [], moves: [], searched: 0 };

        // For a shared box `positions` is the combined tail SET (ascending)
        // and `fromFlat` the member-order walk of the same tails - the
        // search moves the set, the moves report per circuit.
        const original = targets.map(t => (t.fromFlat || t.positions).slice());
        const current = targets.map(t => t.positions.slice());
        const write = () => targets.forEach((t, i) => {
            if (t.members) { this._dealBoxTails(t.members, current[i]); return; }
            const store = t.layer.powerSocaPhasePos || (t.layer.powerSocaPhasePos = {});
            store[t.soca] = current[i].slice();
        });
        let searched = 0;
        const score = () => { write(); searched += 1; return this._worstImbalance(distroId); };

        let best = score();
        for (let pass = 0; pass < 40; pass++) {
            let moved = false;
            for (let t = 0; t < targets.length; t++) {
                const L = current[t].length;
                for (let i = 0; i < L; i++) {
                    // trade the tail at slot i for one nothing is using;
                    // re-sort so the array stays ascending wall order.
                    // The fan is the target's OWN box - six tails on a
                    // soca, three on an L21-30.
                    for (let p = 1; p <= (targets[t].boxSize || 6); p++) {
                        if (current[t].includes(p)) continue;
                        const was = current[t].slice();
                        current[t][i] = p;
                        current[t].sort((x, y) => x - y);
                        const sc = score();
                        if (sc < best - 0.01) { best = sc; moved = true; }
                        else current[t] = was;
                    }
                }
            }
            if (!moved) break;
        }
        const winner = current.map(a => a.slice());

        // put the project back exactly as it was; the label tail-slot cache
        // may have been built against a candidate arrangement mid-search
        // (getSocaPlan labels every leg), so drop it with the candidates
        targets.forEach((t, i) => {
            if (t.members) {
                // members whose default was DEALT (no store) go back to
                // having no store - writing the dealt tails would freeze an
                // arrangement nobody chose
                t.members.forEach(m => {
                    const store = m.layer.powerSocaPhasePos
                        || (m.layer.powerSocaPhasePos = {});
                    if (m.hadStore) store[m.soca] = m.savedStore.slice();
                    else delete store[m.soca];
                });
                return;
            }
            const store = t.layer.powerSocaPhasePos || (t.layer.powerSocaPhasePos = {});
            if (original[i].every((p, k) => p === k + 1)) delete store[t.soca];
            else store[t.soca] = original[i].slice();
        });
        this._circuitTailCache = null;

        return {
            before, after: best, searched,
            targets: targets.map(t => `${t.name} (${t.layerName || t.layer.name}, ${t.legs} circuits)`),
            moves: targets.map((t, i) => ({
                layerId: t.layer.id, layerName: t.layerName || t.layer.name,
                soca: t.soca,
                name: t.name, legs: t.legs,
                members: t.members ? t.members.map(m => ({
                    layerId: m.layer.id, soca: m.soca, legs: m.legs })) : null,
                from: original[i], to: winner[i],
                amps: t.amps, labels: t.labels
            })).filter(m => m.from.some((p, k) => p !== m.to[k]))
        };
    }

    applyPhaseBalance(moves) {
        const touched = new Set();
        for (const m of moves || []) {
            // A shared box's move re-deals the whole set: ascending tails to
            // members in member order, each member's slice stored on its own
            // layer - the same deal write() ran during the search.
            if (m.members && m.members.length) {
                const sorted = m.to.slice().sort((a, b) => a - b);
                let off = 0;
                for (const mem of m.members) {
                    const layer = (this.project.layers || [])
                        .find(l => l.id === mem.layerId);
                    if (!layer) { off += mem.legs; continue; }
                    const store = layer.powerSocaPhasePos
                        || (layer.powerSocaPhasePos = {});
                    store[mem.soca] = sorted.slice(off, off + mem.legs);
                    off += mem.legs;
                    touched.add(layer);
                }
                continue;
            }
            const layer = (this.project.layers || []).find(l => l.id === m.layerId);
            if (!layer) continue;
            const store = layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {});
            if (m.to.every((p, k) => p === k + 1)) delete store[m.soca];
            else store[m.soca] = m.to.slice();
            touched.add(layer);
        }
        this._circuitTailCache = null;
        if (touched.size) this.updateLayers([...touched], true, 'Balance Phase Legs');
        return touched.size;
    }

    // Show what the balancer found and let the user accept or decline it.
    // Advisory by design: this moves a multi to a different set of breakers
    // on paper, and somebody still has to plug it in that way.
    //
    // Scoped to one distro when `distroId` is given - the per-distro
    // Balance button's dialog reports that distro's before/after and moves
    // only its multis. With nothing movable it STATES why (full multis,
    // clashed boxes, assignments the plan no longer produces) rather than
    // computing silently to a no-op: the reference show read that silence
    // as "balancing won't calculate".
    showBalanceDialog(distroId) {
        const r = this.suggestPhaseBalance(distroId);
        const ID = 'balance-modal';
        document.getElementById(ID)?.remove();
        const esc = (s) => this._esc ? this._esc(s) : s;
        const gain = r.before - r.after;
        const distro = distroId
            ? this.getDistros().find(d => d.id === distroId) : null;
        let noTargets = `<p style="margin:0; color:#a6b0bb;">Every multi on a three-phase distro is full, so the legs are already
               as even as the pattern allows. Imbalance comes from partly-filled
               multis — there are none here.</p>`;
        if (distroId) {
            const b = this._balanceBlockers(distroId);
            const lines = [];
            if (b.full.length) lines.push(
                `${b.full.map(f => esc(f.name)).join(', ')} ${b.full.length === 1 ? 'is' : 'are'} full — with every circuit taken the legs are already as even as they get, there is nothing to choose.`);
            b.clashed.forEach(c => lines.push(
                `${esc(c.name)} (${esc(c.layers)}) is shared ${c.overflow
                    ? 'with more circuits than the six it holds'
                    : 'with a circuit claimed twice'} — resolve the clash first.`));
            b.phantom.forEach(p => lines.push(
                `${esc(p.layers)} assigns ${p.count === 1 ? 'a multi' : p.count + ' multis'} to this distro but ${esc(p.reason)}`));
            noTargets = `<p style="margin:0 0 6px; color:#a6b0bb;">Nothing on this distro can move${lines.length ? ':' : ' — no partly-filled multi lands on it.'}</p>`
                + lines.map(l => `<div style="color:#a6b0bb; margin:0 0 4px; padding-left:10px;">· ${l}</div>`).join('');
        }
        const body = !r.targets.length
            ? noTargets
            : !r.moves.length
            ? `<p style="margin:0; color:#a6b0bb;">Checked ${r.searched} arrangement${r.searched === 1 ? '' : 's'} of
               ${r.targets.length} partly-filled multi${r.targets.length === 1 ? '' : 's'} and could not beat the current
               ${r.before.toFixed(1)}% imbalance. Landing them elsewhere will not help;
               filling the short multis or moving circuits between them would.</p>`
            : `<div style="display:flex; align-items:baseline; gap:10px; margin-bottom:14px;">
                 <span style="font-size:22px; color:#e05050;">${r.before.toFixed(1)}%</span>
                 <span style="color:#7d8894;">→</span>
                 <span style="font-size:22px; color:#5fa85f;">${r.after.toFixed(1)}%</span>
                 <span style="color:#8fa0b2; font-size:11px;">worst-leg imbalance · ${gain.toFixed(1)} points better</span>
               </div>
               <div style="font-size:11px; color:#8a949f; margin-bottom:6px;">Re-plug these circuits along the same
               fan — no rewiring, no re-patching:</div>
               ${r.moves.map(m => `
                 <div style="margin-bottom:10px;">
                   <div style="color:#e8eef5; margin-bottom:3px;">${esc(m.name)}
                     <span style="color:#7d8894; font-weight:400;">· ${esc(m.layerName)}</span></div>
                   <table style="width:100%; border-collapse:collapse; font-size:11px;">
                     ${m.to.map((p, k) => p === m.from[k] ? '' : `<tr>
                       <td style="padding:2px 8px; color:#a6b0bb; width:40%;">${esc((m.labels || [])[k] || `circuit ${k + 1}`)}
                         <span style="color:#6d7681;">(${m.amps[k].toFixed(1)} A)</span></td>
                       <td style="padding:2px 8px; color:#a6b0bb;">socket ${m.from[k]} → <strong style="color:#e8eef5;">socket ${p}</strong></td>
                     </tr>`).join('')}
                   </table>
                 </div>`).join('')}
               <div style="margin-top:12px; font-size:11px; color:#7d8894;">Balancing picks WHICH sockets of the fan a partly-filled
               multi uses — skipping one lands the remainder on different
               legs. Circuits keep wall order across the chosen sockets,
               so the labels still read in order across the wall.
               Evaluated ${r.searched} arrangements.</div>`;

        const el = document.createElement('div');
        el.id = ID;
        el.className = 'modal';
        el.style.display = 'block';
        el.innerHTML = `
<div class="modal-content" style="background:#252525; border-radius:8px; padding:0; width:540px; max-width:94vw; margin:80px auto; border:1px solid #3a3a3a; overflow:hidden;">
  <div style="display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #3a3a3a;">
    <h2 style="margin:0; font-size:15px; letter-spacing:0.5px;">BALANCE PHASE LEGS${distro ? ` — ${esc(distro.name).toUpperCase()}` : ''}</h2>
    <button class="btn btn-secondary balance-close" style="padding:4px 12px;">✕</button>
  </div>
  <div style="padding:16px 20px; font-size:12px; line-height:1.55;">${body}</div>
  <div style="display:flex; gap:8px; justify-content:flex-end; padding:0 20px 16px;">
    <button class="btn btn-secondary balance-reset" title="Put every multi back on its natural breaker position">Reset offsets</button>
    <button class="btn btn-secondary balance-close">${r.moves.length ? 'Leave it' : 'Close'}</button>
    ${r.moves.length ? '<button class="btn balance-apply">Apply</button>' : ''}
  </div>
</div>`;
        document.body.appendChild(el);
        el.querySelectorAll('.balance-close').forEach(b =>
            b.addEventListener('click', () => el.remove()));
        el.addEventListener('click', (e) => { if (e.target === el) el.remove(); });
        // Balancing renumbers labels (true tails), so refresh EVERY pane
        // that prints them - splitter rows and the label editor included,
        // plus the canvas bubbles - not just the load roll-ups. The server
        // echo would repaint them a round-trip later anyway; doing it here
        // means the left pane and the map agree the moment the dialog
        // closes (same refresh set as _writeSplitterManual).
        const refreshAll = () => {
            this.refreshDistroPanel();
            this.refreshSocaRuns();
            this.refreshSplitterPanel();
            this.updatePowerLabelEditor && this.updatePowerLabelEditor();
            if (window.canvasRenderer) window.canvasRenderer.render();
        };
        const resetBtn = el.querySelector('.balance-reset');
        if (resetBtn) resetBtn.addEventListener('click', () => {
            // A scoped dialog resets only its own distro's multis - the
            // other services' arrangements are not this button's to drop.
            this.clearPhaseBalance(distroId);
            el.remove();
            refreshAll();
        });
        const applyBtn = el.querySelector('.balance-apply');
        if (applyBtn) applyBtn.addEventListener('click', () => {
            this.applyPhaseBalance(r.moves);
            el.remove();
            refreshAll();
        });
    }

    // Plain-language explanation of what the phasing schemes mean and why the
    // choice changes the leg loads. Built on demand rather than living in
    // index.html so the copy sits next to the math it describes.
    //
    // The scheme table is GENERATED from powerPhasingSchemes and the leg map
    // itself: names come from the same records the select prints, and the
    // circuit row is read out of _circuitLegs. A user asked what the
    // difference between "line-to-line" and "paired" was because the same
    // scheme was named one way here and another way there; nothing here
    // restates a name or a mapping in prose, so they cannot drift apart again.
    showPhasingHelp() {
        const ID = 'phasing-help-modal';
        document.getElementById(ID)?.remove();
        const schemes = this.powerPhasingSchemes();
        const byId = (id) => schemes.find(s => s.id === id);
        // the six positions of the fan, straight out of the leg map
        const spread = (id) => [1, 2, 3, 4, 5, 6]
            .map(i => this._circuitLegs(i, id).join('')).join(' ');
        const el = document.createElement('div');
        el.id = ID;
        el.className = 'modal';
        el.style.display = 'block';
        el.innerHTML = `
<div class="modal-content" style="background:#252525; border-radius:8px; padding:0; width:660px; max-width:94vw; margin:60px auto; border:1px solid #3a3a3a; display:flex; flex-direction:column; max-height:calc(100vh - 120px); overflow:hidden;">
  <div style="display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid #3a3a3a;">
    <h2 style="margin:0; font-size:15px; letter-spacing:0.5px;">HOW MULTIS LAND ON THE PHASE LEGS</h2>
    <button class="btn btn-secondary phasing-help-close" style="padding:4px 12px;">✕</button>
  </div>
  <div style="padding:16px 20px; overflow-y:auto; font-size:12px; color:#c3ccd6; line-height:1.6;">

    <p style="margin:0 0 14px;"><strong style="color:#e8eef5;">A distro fed from camlock is three-phase. Every circuit
    coming off the breakout is single-phase</strong> — whether it sits on one
    hot and a neutral, or across two hots with no neutral. Three-phase never
    reaches a panel. The legs only decide <em>which</em> hots each circuit
    sits across, and therefore how the load spreads over the service.</p>

    <div style="background:#2b2f35; border-left:3px solid #4a6fa5; padding:10px 12px; border-radius:0 4px 4px 0; margin:0 0 14px;">
      <div style="color:#e8eef5; margin-bottom:5px;">Two things vary, and they are independent</div>
      <div style="color:#a6b0bb; margin-bottom:8px;">Every scheme is named for both, coupling first, order second — so
      <em>${byId('paired-ll').name}</em> and <em>${byId('rotating-ll').name}</em>
      are the same coupling dealt differently, not two answers to one question.</div>
      <table style="width:100%; border-collapse:collapse;">
        <tr>
          <td style="padding:3px 8px 3px 0; vertical-align:top; color:#e8eef5; white-space:nowrap;">Coupling</td>
          <td style="padding:3px 0; color:#a6b0bb;"><strong style="color:#c3ccd6;">Line-to-neutral</strong> is one hot and
          a neutral (X). <strong style="color:#c3ccd6;">Line-to-line</strong> is two hots and no neutral (XY). This is the
          electrical relationship, and it follows the circuit voltage: line-to-neutral
          runs at the service divided by √3 — 120 V off a 208 V service, 230 V off a
          400 V one.</td>
        </tr>
        <tr>
          <td style="padding:3px 8px 3px 0; vertical-align:top; color:#e8eef5; white-space:nowrap;">Order</td>
          <td style="padding:3px 0; color:#a6b0bb;"><strong style="color:#c3ccd6;">Rotating</strong> advances on every
          circuit (X Y Z X Y Z). <strong style="color:#c3ccd6;">Paired</strong> puts two consecutive circuits on the same
          assignment before advancing (X X Y Y Z Z). This is how the distro is wired
          internally, which is why it is a setting here and not something the voltage
          can answer.</td>
        </tr>
      </table>
    </div>

    <div style="background:#3a2626; border-left:3px solid #b34a3a; padding:10px 12px; border-radius:0 4px 4px 0; margin:0 0 14px; color:#e0c0ba;">
      <strong style="color:#f5cdc4;">No standard assigns a circuit to a leg.</strong>
      ANSI E1.80, USITT RP-1 and NEC 520.68 all cover the <em>pinout</em> —
      which pin carries which circuit's conductors — and none of them assigns
      a circuit to a leg. No major distro manufacturer publishes a universal
      mapping. Motion Laboratories' own maintenance manual says to "verify
      the pinout of each output, including that the correct phase is on the
      correct pin per the pinout. (The pinout is marked on the panel near the
      output devices.)" <strong style="color:#f5cdc4;">Read the unit.</strong>
    </div>

    <p style="margin:0 0 14px; color:#a6b0bb;">What every source does agree on is the
    <em>balance goal</em>: two circuits per leg line-to-neutral, two circuits
    per leg-pair line-to-line. Only the order varies — and the order is exactly
    what decides where a partly-filled multi dumps its remainder. Each pattern
    below is documented on a real distro or rack, none is a default.</p>

    <table class="phasing-scheme-table" style="width:100%; border-collapse:collapse; margin-bottom:10px;">
      <tr style="border-bottom:1px solid #3a3a3a;">
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Scheme</th>
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Circuits 1–6</th>
        <th style="text-align:left; padding:6px 8px; font-size:10px; color:#8a949f; text-transform:uppercase;">Where it is documented</th>
      </tr>
      ${schemes.map(sc => `
      <tr style="border-bottom:1px solid #303030;">
        <td style="padding:8px; vertical-align:top; color:#e8eef5;">${sc.name}<br><span style="color:#7d8894; font-size:11px;">${sc.lineToLine ? 'two hots, no neutral' : 'one hot and a neutral'}</span></td>
        <td style="padding:8px; vertical-align:top; font-family:ui-monospace,Menlo,monospace; font-size:11px;">${spread(sc.id)}</td>
        <td style="padding:8px; vertical-align:top; color:#a6b0bb;">${sc.where}</td>
      </tr>`).join('')}
    </table>

    <p style="margin:0 0 16px; color:#a6b0bb;">The two paired line-to-line schemes differ
    only in the order the pairs come round: <em>${byId('paired-ll-alt').pattern}</em>
    follows the cyclic order X → Y → Z → X, the way AB → BC → CA does, and
    <em>${byId('paired-ll').pattern}</em> does not. That is the ordering fact,
    not a ranking — neither is a default, and the only way to know which one a
    given soca uses is to read it.</p>

    <div style="background:#2b2f35; border-left:3px solid #4a6fa5; padding:10px 12px; border-radius:0 4px 4px 0;">
      <div style="color:#e8eef5; margin-bottom:5px;">Why your legs are uneven</div>
      <div style="color:#a6b0bb;">Imbalance almost always comes from <strong>partly-filled
      multis</strong>, not from the screens. A full 6-circuit multi balances
      itself under any scheme. A multi that stops at 4 or 5 circuits dumps its
      remainder onto whichever legs come first in the pattern — with paired
      legs that is always X. Fill the multi, move a circuit to another multi,
      or use the rotating pattern if the distro is wired that way.</div>
    </div>

    <div style="margin-top:14px; color:#7d8894; font-size:11px;">
      Per-leg current is a phasor sum, not a straight addition: a line-to-line
      circuit is one load drawing the <em>same</em> current in both its legs, sitting
      ±30° off each leg's line-to-neutral reference. Imbalance is NEMA-style —
      the largest deviation from the average of the three legs.
    </div>
  </div>
</div>`;
        document.body.appendChild(el);
        el.querySelector('.phasing-help-close').addEventListener('click', () => el.remove());
        el.addEventListener('click', (e) => { if (e.target === el) el.remove(); });
    }

    // How a distro lands a multi's 6 circuits on its phase legs.
    //
    // This is a property of the DISTRO's internal bus and breaker
    // arrangement. It is NOT the connector pinout: ANSI E1.80-2024 defines
    // 120V Type U and 208V Types C/D/E, but those describe which PIN carries
    // which circuit's conductors - the standard's own table key is only
    // "L = Ungrounded Circuit Conductor" and it never assigns a circuit to
    // L1, L2 or L3. Two distros with identical E1.80 pinouts can still land
    // their circuits on different legs. Read the distro, not the connector.
    //
    // Every pattern below is documented on a real North American distro or
    // rack. There is no national standard for phase rotation - a search of
    // E1.80, USITT RP-1, NEC 520.68, and the published material from every
    // major distro manufacturer turned up nothing that assigns a circuit to
    // a leg. Motion Laboratories' own maintenance manual says to "verify the
    // pinout of each output, including that the correct phase is on the
    // correct pin per the pinout. (The pinout is marked on the panel near the
    // output devices.)" That is the industry position: read the unit.
    //
    // What IS consistent across every source is the balance goal - two
    // circuits per leg line-to-neutral, two circuits per leg-PAIR
    // line-to-line. Only the order varies, and the order is what changes a
    // partly-filled multi.
    //
    // NAMING. A scheme varies along TWO independent axes and the name gives
    // both, coupling first, order second:
    //   coupling  line-to-neutral (one leg, X) or line-to-line (two, XY)
    //   order     rotating (advance every circuit) or paired (two circuits
    //             on one assignment, then advance)
    // Naming only one axis made two orthogonal things look like alternatives
    // - the same scheme read as "paired" in the list and "line-to-line" on
    // the derived entry, and a user asked what the difference was. `name` is
    // therefore COMPUTED from the axes so no caller can spell it its own way.
    //
    // The volts are deliberately not in the name: line-to-neutral is 120V on
    // a 208V service and 230V on a 400V one, so the figure belongs to the
    // SERVICE, not the scheme. It is derived as V / sqrt(3) where it helps.
    powerPhasingSchemes() {
        const named = (s) => ({
            ...s,
            coupling: s.lineToLine ? 'Line-to-line' : 'Line-to-neutral',
            name: `${s.lineToLine ? 'Line-to-line' : 'Line-to-neutral'}, ${s.order} (${s.pattern})`,
        });
        return [
            { id: 'rotating-ln', lineToLine: false, order: 'rotating',
              pattern: 'X Y Z X Y Z',
              where: 'Published phasing sheet for a 36-way house distro. No practitioner source corroborates it, so confirm before relying on it.' },
            { id: 'paired-ln', lineToLine: false, order: 'paired',
              pattern: 'X X Y Y Z Z',
              where: 'What several practitioners report as usual.' },
            { id: 'paired-ll', lineToLine: true, order: 'paired',
              pattern: 'XY ZX YZ',
              where: 'Two independent rental houses publish this exact map.' },
            { id: 'paired-ll-alt', lineToLine: true, order: 'paired',
              pattern: 'XY YZ ZX',
              where: 'Same grouping, other pair order — published as the Strand LightRack module pinout.' },
            { id: 'rotating-ll', lineToLine: true, order: 'rotating',
              pattern: 'XY XZ YZ',
              where: 'Reported as a competing family. Spreads a partly-filled multi best.' }
        ].map(named);
    }

    // Default scheme for a distro: line-to-line when the circuit voltage
    // matches the service voltage (208V circuits on a 208V wye), otherwise
    // line-to-neutral.
    powerPhasingFor(distro, circuitVoltage) {
        const schemes = this.powerPhasingSchemes();
        const explicit = distro && distro.phasing && schemes.find(s => s.id === distro.phasing);
        if (explicit) return explicit;
        const ll = distro && circuitVoltage > 0 && Math.abs(circuitVoltage - distro.voltage) < 1;
        return schemes.find(s => s.id === (ll ? 'paired-ll' : 'rotating-ln'));
    }

    // The circuit voltage this distro actually sees: whatever the screens
    // feeding it run at, walked in the SAME order getDistroLoads walks them so
    // the select and the leg maths can never name two different schemes.
    //
    // A distro with nothing assigned yet has no evidence to read, so it is
    // taken at its word - a service whose circuits sit at the service voltage,
    // which is what choosing 208V means. It is a default like any other here
    // and the moment a multi lands on the distro the real circuit voltage
    // replaces it.
    distroCircuitVoltage(distro) {
        if (!distro || !this.project) return 0;
        let seen = null;
        for (const layer of this.project.layers || []) {
            if ((layer.type || 'screen') !== 'screen') continue;
            const assign = layer.powerSocaDistro || {};
            const plan = this.getSocaPlan(layer);
            if (!plan.some(s => assign[s.soca] === distro.id)) continue;
            seen = parseFloat(layer.powerVoltage) || 0;
        }
        return seen === null ? (Number(distro.voltage) || 0) : seen;
    }

    // What the phasing control has to say out loud: the scheme in force, and
    // whether it is DERIVED from the voltage or was picked by hand.
    //
    // Two distros can run the same scheme, one because somebody read the box
    // and one because nobody has - and only the first survives a voltage
    // change. Without this distinction on screen "a manual choice overrides
    // the default" is a rule the user cannot see operating.
    distroPhasingState(distro) {
        const schemes = this.powerPhasingSchemes();
        const chosen = distro && distro.phasing
            && schemes.find(s => s.id === distro.phasing);
        const circuitV = this.distroCircuitVoltage(distro);
        // Ask for the derived answer explicitly rather than reading it off
        // powerPhasingFor(distro, ...), which would hand back the explicit
        // choice and hide what the voltage would have chosen.
        const derived = this.powerPhasingFor(
            { voltage: distro && distro.voltage, phasing: null }, circuitV);
        return {
            explicit: !!chosen,
            derived,
            circuitVoltage: circuitV,
            scheme: chosen || derived
        };
    }

    // Order a leg pair cyclically (X>Y>Z>X). The first leg of the cyclic pair
    // carries the line-to-line current at +30 deg relative to its own
    // line-to-neutral voltage, the second at -30 deg.
    _cyclicPair(a, b) {
        const C = ['X', 'Y', 'Z'];
        const ia = C.indexOf(a), ib = C.indexOf(b);
        return ib === (ia + 1) % 3 ? [a, b] : [b, a];
    }

    _addLegPhasor(store, leg, amps, degrees) {
        const r = degrees * Math.PI / 180;
        store[leg].re += amps * Math.cos(r);
        store[leg].im += amps * Math.sin(r);
    }

    // `offset` slides the used circuits along the multi's own six positions:
    // a multi with 4 circuits in use can occupy positions 1-4, 2-5 or 3-6.
    // The load does not move to another multi - it is the same 6-way fan,
    // just landed on different legs of it.
    //
    // The offset MUST be bounded by socaPhaseOffsetMax so the last circuit
    // stays within position 6. The modulo below is only a guard; if it ever
    // actually wraps, the offset was invalid and the answer is nonsense -
    // a 5-circuit multi at offset 3 would want positions 4..8, and wrapping
    // 7 and 8 back to 1 and 2 silently invents a plan nobody can patch.
    //
    // `boxSize` is the fan the positions index into. A 3-tail L21-30 box
    // has no order axis to choose - one circuit per assignment - so its
    // line-to-line map is the fixed cyclic pair walk (XY YZ ZX, the box's
    // own internal wiring) whatever paired/rotating scheme the distro
    // runs its socas on, and its line-to-neutral map is one leg per tail.
    _circuitLegs(legIndex, schemeId, offset = 0, boxSize = 6) {
        const size = Number(boxSize) === 3 ? 3 : 6;
        const i = ((legIndex - 1 + (Number(offset) || 0)) % size + size) % size;
        if (size === 3) {
            const ln = schemeId === 'paired-ln' || schemeId === 'rotating-ln';
            if (ln) return [['X'], ['Y'], ['Z']][i];
            return [['X','Y'], ['Y','Z'], ['Z','X']][i];
        }
        if (schemeId === 'paired-ll') return [['X','Y'], ['X','Y'], ['Z','X'], ['Z','X'], ['Y','Z'], ['Y','Z']][i];
        if (schemeId === 'paired-ll-alt') return [['X','Y'], ['X','Y'], ['Y','Z'], ['Y','Z'], ['Z','X'], ['Z','X']][i];
        if (schemeId === 'rotating-ll') return [['X','Y'], ['X','Z'], ['Y','Z'], ['X','Y'], ['X','Z'], ['Y','Z']][i];
        if (schemeId === 'paired-ln') return [['X'], ['X'], ['Y'], ['Y'], ['Z'], ['Z']][i];
        return [['X', 'Y', 'Z'][i % 3]];
    }

    // How far a multi's used circuits can slide as a BLOCK before the last
    // one runs off the end of the fan. Kept for the legacy block model;
    // socaCircuitPositions supersedes it.
    socaPhaseOffsetMax(legsUsed, boxSize = 6) {
        return Math.max(0, (Number(boxSize) || 6) - (Number(legsUsed) || 6));
    }

    // Which position on the multi's 6-way fan each used circuit occupies.
    //
    // WALL-ORDER RULE (user decision, fixed): balancing - or anything else -
    // only ever chooses WHICH tails of the fan are in use (the SET). The
    // assignment of circuits to the chosen tails is always wall order ->
    // ascending tail number, so a wall using tails {1,2,3,5,6} reads
    // S1-1, S1-2, S1-3, S1-5, S1-6 left to right, never a permutation.
    // Stored arrays are therefore sorted ascending ON READ: projects that
    // still carry a permutation from the old balancer ([6,2,5,1,3]) or a
    // rotation ([5,6,1,2,3]) display wall-ordered immediately, keeping the
    // same occupied tails, without a re-balance.
    //
    // Returns a position (1-6) per used circuit, ascending in circuit
    // (wall) order. Falls back to the legacy block offset - which selects
    // the occupied tails off+1..off+L, already ascending - then to the
    // natural 1..L.
    socaCircuitPositions(layer, socaNum, legsUsed) {
        const size = this.socaBoxSize(layer);
        const L = Math.max(0, Math.min(size, Number(legsUsed) || 0));
        const saved = ((layer && layer.powerSocaPhasePos) || {})[socaNum];
        if (Array.isArray(saved) && saved.length === L
            && saved.every(p => Number.isInteger(p) && p >= 1 && p <= size)
            && new Set(saved).size === L) {
            return saved.slice().sort((a, b) => a - b);
        }
        // A multi PINNED to a number can be sharing one physical box with a
        // multi on another screen, and then its unstored default is not the
        // natural 1..L - it is the box's NEXT FREE tails, dealt in
        // _resolveSharedSocas with every member on the table. Read the dealt
        // answer rather than re-deriving it here; a pin the naming pass has
        // not resolved (mid-build, an orphan screen) falls through to the
        // legacy default below.
        if (layer && (layer.powerSocaDistro || {})[socaNum]) {
            const pin = parseInt((layer.powerSocaNumber || {})[socaNum], 10);
            if (Number.isFinite(pin) && pin >= 1) {
                const rec = this._powerNaming(layer).socas.get(Number(socaNum));
                if (rec && Array.isArray(rec.positions)
                        && rec.positions.length === (Number(legsUsed) || 0)) {
                    return rec.positions.slice();
                }
            }
        }
        const off = this.socaPhaseOffset(layer, socaNum, L);
        return Array.from({ length: L }, (_, i) => i + 1 + off);
    }

    // The scheme ONE CIRCUIT actually lands with: coupling is physics -
    // a 110V Edison circuit needs a hot and a neutral, a 208V circuit two
    // hots - so the circuit's own voltage decides line-to-neutral vs
    // line-to-line, and only the dealing ORDER is the distro's wiring to
    // declare. An explicit distro scheme therefore applies to a circuit
    // only when its coupling matches what that circuit's voltage derives;
    // otherwise the voltage's own derived default takes over for that
    // circuit alone. This is what lets a 110V multi and a 208V multi share
    // one distro without the explicit choice pairing up Edison circuits:
    // the 110V circuits ride one leg each, the 208V circuits their pairs
    // (user ruling, 2026-08-28). The gear select still shows a mismatched
    // explicit choice and says so - paperwork is displayed, never obeyed
    // into an impossible hookup.
    _circuitSchemeFor(distro, circuitVoltage) {
        const derived = this.powerPhasingFor(
            { voltage: distro && distro.voltage, phasing: null },
            circuitVoltage);
        const chosen = this.powerPhasingFor(distro, circuitVoltage);
        return chosen.lineToLine === derived.lineToLine ? chosen : derived;
    }

    // Positions must be a set of distinct 1-6 values, one per used circuit -
    // two circuits cannot share a tail. Only the SET matters (wall-order
    // rule): stored sorted ascending, and a permutation of 1..L is the
    // natural arrangement - but only on a multi that owns its whole box.
    // On a SHARED box tails 1..L are one specific claim among six, not a
    // default: dropping the store there hands the member back to the deal,
    // and the deal answers by layer order - which is exactly how "put me
    // back on 1-4" once evaporated and let the joiner keep tail 1.
    setSocaCircuitPositions(layer, socaNum, positions, legsUsed) {
        if (!layer) return false;
        const size = this.socaBoxSize(layer);
        const L = Math.max(0, Math.min(size, Number(legsUsed) || 0));
        const ok = Array.isArray(positions) && positions.length === L
            && positions.every(p => Number.isInteger(p) && p >= 1 && p <= size)
            && new Set(positions).size === L;
        if (!ok) return false;
        const store = layer.powerSocaPhasePos || (layer.powerSocaPhasePos = {});
        const sorted = positions.slice().sort((a, b) => a - b);
        const natural = sorted.every((p, i) => p === i + 1);
        if (natural && !this.getSocaShare(layer, socaNum)) {
            delete store[socaNum];
        } else {
            store[socaNum] = sorted;
        }
        this._circuitTailCache = null;
        this.updateLayers([layer], true, 'Move Circuits');
        return true;
    }

    // Which position within the multi the first used circuit sits on (0-based).
    // Clamped on read as well as on write, so a stored value that is no longer
    // valid - the screen shed a circuit since it was set - degrades to the
    // nearest legal position instead of wrapping off the end.
    socaPhaseOffset(layer, socaNum, legsUsed) {
        const map = (layer && layer.powerSocaPhaseOffset) || {};
        const raw = Math.max(0, Number(map[socaNum]) || 0);
        return Math.min(raw,
            this.socaPhaseOffsetMax(legsUsed, this.socaBoxSize(layer)));
    }

    setSocaPhaseOffset(layer, socaNum, offset, legsUsed) {
        if (!layer) return;
        // Always leave an object behind, never delete the property itself:
        // an absent key is simply missing from the update payload and the
        // server keeps whatever it had, so "clear this" would silently not
        // clear. An empty object overwrites.
        const map = layer.powerSocaPhaseOffset || (layer.powerSocaPhaseOffset = {});
        const v = Math.min(Math.max(0, Number(offset) || 0),
                           this.socaPhaseOffsetMax(legsUsed,
                               this.socaBoxSize(layer)));
        if (v) map[socaNum] = v; else delete map[socaNum];
        this._circuitTailCache = null;
        this.updateLayers([layer], true, 'Set Breaker Offset');
    }

    // Drop every multi back to its natural breaker position - show-wide, or
    // only the multis assigned to one distro when `distroId` is given (the
    // scoped balance dialog's reset).
    clearPhaseBalance(distroId) {
        const screens = (this.project.layers || []).filter(l => (l.type || 'screen') === 'screen');
        if (!distroId) {
            screens.forEach(l => { l.powerSocaPhaseOffset = {}; l.powerSocaPhasePos = {}; });
        } else {
            screens.forEach(l => {
                const assign = l.powerSocaDistro || {};
                for (const store of [l.powerSocaPhaseOffset, l.powerSocaPhasePos]) {
                    if (!store) continue;
                    for (const k of Object.keys(store)) {
                        if (assign[k] === distroId) delete store[k];
                    }
                }
            });
        }
        this._circuitTailCache = null;
        if (screens.length) this.updateLayers(screens, true, 'Reset Phase Offsets');
        return screens.length;
    }
}

for (const k of Object.getOwnPropertyNames(_PhaseBalance.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_PhaseBalance.prototype, k));
    }
}
