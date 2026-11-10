// app-network: the processors' IP addresses (owner, 2026-11-09: "add to
// the processors the ability to IP addresses and that would be represented
// on the binder").
//
// Each unit - a processor, and its backup unit when one is on - has an IP,
// a subnet mask, a gateway and a short note. The show keeps one subnet and
// one gateway that every unit reads where its own is blank: the field shows
// the show's value in grey, and that value is what prints. Breakout boxes
// have none.
//
// Where it lives: the processor's ⚙ (app-processors.js
// _buildProcGearContent), a NETWORK block under BACKUP PROCESSOR - the
// unit's four fields, the backup unit's four under them, and the show's
// subnet and gateway last. Each field commits on its own (Enter, Tab or
// leaving it) as one request and one undo step. The header strip carries
// the unit's IP once one is typed.
//
// Checks never block: an entry that is not an address is marked red in its
// field with the reason in its tooltip, two units on one IP are named in a
// red line under each and as a row in the Data tray's warning strip, and
// the binder prints whatever was typed.
//
// The binder (app-binder.js): each processor's hardware sheet carries a
// NETWORK table (its unit, its backup unit), each Data sheet's FACTS its
// processor's IP, and the NETWORK page lists every unit - all of it only
// once some unit has an IP, so a show without them prints as it always
// did. The plain functions (which units, what each reads, which entries
// are bad, which IPs are shared) are network-ip.js's, a classic script
// the node tests run.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// network-ip.js is a classic script: its top-level const is a global
// binding, not a property of window, so it is read by name.
const NET = () => (typeof NetworkIp !== 'undefined' ? NetworkIp : null);
const RED = '#d05a52';
// The fields a unit has and the words each goes by.
const UNIT_FIELDS = [
    ['ip', 'IP', 'IP address, this unit\'s address on the show network.'],
    ['subnet', 'Subnet', 'Subnet mask, like 255.255.255.0 or /24.'],
    ['gateway', 'Gateway', 'Gateway, the router address, if the network has one.'],
    ['note', 'Note', 'Note, a few words for the crew, like "control laptop port 2" or "VLAN 20".'],
];
const WORD = { ip: 'IP', subnet: 'Subnet', gateway: 'Gateway', note: 'Note' };

class _Network {

    // ---- state ---------------------------------------------------------------

    // The show's subnet and gateway as stored, {} with none.
    networkShowDefaults() {
        const raw = this.project && this.project.network;
        return raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
    }

    // The show's own network settings off a processor reply onto the
    // project, under the tree's rule: never written onto a project that
    // has none, and an emptied set leaves no key behind - so a show that
    // never met the feature saves byte for byte as it was, and an undo
    // snapshot carries exactly what the server holds.
    _adoptShowNetwork(data) {
        if (!this.project || !data || !data.network || typeof data.network !== 'object') return;
        if (Object.keys(data.network).length) this.project.network = { ...data.network };
        else delete this.project.network;
    }

    // Every unit, tray order, main then its backup unit (NetworkIp.units).
    networkUnits(procs = this._processorsResolved) {
        const net = NET();
        if (!net) return [];
        return net.units(procs || [], this.networkShowDefaults(), {
            title: (p) => (typeof this._bProcessorTitle === 'function'
                ? this._bProcessorTitle(p) : (p.name || p.deviceName || p.id)),
            backupOf: (p) => (typeof this._backupUnitMainId === 'function' ? !!this._backupUnitMainId(p) : false),
        });
    }

    networkDuplicates(units = this.networkUnits()) {
        const net = NET();
        return net ? net.duplicates(units) : [];
    }

    // Whether the binder has a Network page to print: some unit has an IP.
    binderUsesNetwork() {
        const net = NET();
        return !!net && net.anyIp(this.networkUnits());
    }

    // ---- edits ---------------------------------------------------------------

    // One field of one unit: `slot` 'main' (the processor) or 'bu' (its
    // backup unit). One request, one undo step; a value equal to the one
    // stored sends nothing.
    setUnitNetworkField(procId, slot, field, value) {
        const proc = (this._processorsResolved || []).find(p => p.id === procId);
        if (!proc) return null;
        const node = slot === 'bu' ? proc.backupUnit : proc;
        const stored = ((node && node.network) || {})[field] || '';
        const text = String(value == null ? '' : value).trim();
        if (text === stored) return null;
        sendClientLog('network_field_set', { procId, slot, field, blank: !text });
        const word = slot === 'bu' ? 'Backup Processor' : 'Processor';
        return this._processorRequest(`/api/processors/${procId}`, 'PUT',
            { [slot === 'bu' ? 'backupNetwork' : 'network']: { [field]: text } },
            `Edit ${word} ${WORD[field]}`);
    }

    // The show's subnet or gateway, every unit's where its own is blank.
    setShowNetworkField(field, value) {
        const text = String(value == null ? '' : value).trim();
        if (text === (this.networkShowDefaults()[field] || '')) return null;
        sendClientLog('network_show_field_set', { field, blank: !text });
        return this._processorRequest('/api/processors/network', 'PUT',
            { [field]: text }, `Edit Show ${WORD[field]}`);
    }

    // ---- the processor's ⚙ ---------------------------------------------------

    // One field: its caption over its box, the box red with the reason in
    // its tooltip while its entry is not an address (live as it is typed),
    // the show's value in grey where it stands in.
    _netField(kind, caption, tip, value, placeholder, key, commit) {
        const cell = this._buildTextField(caption, value, placeholder, key, commit);
        cell.style.flex = '1 1 100px';
        const input = cell.querySelector('input');
        input.style.width = '100%';
        input.spellcheck = false;
        input.autocomplete = 'off';
        const mark = () => {
            const why = NET() ? NET().problem(kind, input.value) : '';
            input.classList.toggle('hw-pop-net-bad', !!why);
            input.setAttribute('aria-invalid', why ? 'true' : 'false');
            input.title = why || tip;
        };
        input.addEventListener('input', mark);
        mark();
        cell.title = tip;
        return cell;
    }

    // A unit's four fields, two to a line, under its name where the
    // processor has a backup unit (with one unit the popover's heading
    // names it), and a red line naming any unit sharing its IP.
    _netUnitRows(proc, unit, named, dups) {
        const box = document.createElement('div');
        box.className = 'hw-pop-net-unit';
        box.dataset.lrdField = `processor-net-unit-${proc.id}-${unit.slot}`;
        if (named) {
            const name = document.createElement('div');
            name.className = 'hw-pop-net-name';
            name.textContent = unit.slot === 'bu' ? `${unit.name} (backup)` : unit.name;
            box.appendChild(name);
        }
        const show = this.networkShowDefaults();
        const lines = [document.createElement('div'), document.createElement('div')];
        lines.forEach(l => { l.className = 'hw-pop-net-line'; box.appendChild(l); });
        const prefix = unit.slot === 'bu' ? 'processor-bu-net' : 'processor-net';
        UNIT_FIELDS.forEach(([field, caption, tip], i) => {
            // a blank subnet or gateway shows the show's in grey: the
            // placeholder, and the tooltip says it is the one that prints
            const inherited = (field === 'subnet' || field === 'gateway') ? (show[field] || '') : '';
            const fieldTip = inherited && !unit.own[field]
                ? `${tip} Blank uses the show's ${inherited}, which prints.` : tip;
            lines[i < 2 ? 0 : 1].appendChild(this._netField(
                field, caption, fieldTip, unit.own[field], inherited,
                `${prefix}-${field}-${proc.id}`,
                (val) => this.setUnitNetworkField(proc.id, unit.slot, field, val)));
        });
        const dup = dups.find(d => d.units.some(u => u.key === unit.key));
        if (dup) {
            const others = dup.units.filter(u => u.key !== unit.key).map(u => u.name);
            const warn = document.createElement('div');
            warn.className = 'hw-pop-net-dup';
            warn.dataset.lrdField = `processor-net-dup-${proc.id}-${unit.slot}`;
            warn.textContent = `Same IP as ${NET().andList(others)}.`;
            warn.title = NET().duplicateText(dup);
            box.appendChild(warn);
        }
        return box;
    }

    // THE NETWORK BLOCK on a processor's ⚙: the unit, its backup unit when
    // one is on, then the show's subnet and gateway (every unit's where
    // its own is blank).
    _buildProcNetworkBlock(proc) {
        const block = document.createElement('div');
        block.className = 'hw-pop-red-block hw-pop-network';
        block.dataset.lrdField = `processor-network-${proc.id}`;
        const strip = document.createElement('div');
        strip.className = 'hw-pop-red-strip';
        const cap = document.createElement('span');
        cap.className = 'hw-pop-red-cap';
        cap.textContent = 'NETWORK';
        cap.title = 'Network, each unit\'s IP, subnet, gateway and a note. '
            + 'They print on the binder.';
        strip.appendChild(cap);
        block.appendChild(strip);
        const all = this.networkUnits();
        const dups = this.networkDuplicates(all);
        const mine = all.filter(u => u.procId === proc.id);
        mine.forEach(u => block.appendChild(this._netUnitRows(proc, u, mine.length > 1, dups)));
        // the show's two, under a caption that says whose they are
        const showCap = document.createElement('div');
        showCap.className = 'hw-pop-net-name hw-pop-net-show';
        showCap.textContent = 'Every processor';
        showCap.title = 'Show subnet and gateway, used by every unit whose own is blank.';
        block.appendChild(showCap);
        const line = document.createElement('div');
        line.className = 'hw-pop-net-line';
        const show = this.networkShowDefaults();
        [['subnet', 'Show subnet', 'Show subnet, every unit\'s subnet mask unless it has its own.'],
         ['gateway', 'Show gateway', 'Show gateway, every unit\'s gateway unless it has its own.']]
            .forEach(([field, caption, tip]) => {
                line.appendChild(this._netField(field, caption, tip, show[field] || '', '',
                    `show-net-${field}`, (val) => this.setShowNetworkField(field, val)));
            });
        block.appendChild(line);
        return block;
    }

    // The unit's IP on its header strip once one is typed - red while
    // another unit shares it. A click opens the ⚙, where it is set.
    _dockIpPill(proc) {
        const units = this.networkUnits();
        const unit = units.find(u => u.procId === proc.id && u.slot === 'main');
        if (!unit || !unit.ip) return null;
        const dup = this.networkDuplicates(units).find(d => d.units.some(u => u.key === unit.key));
        const pill = document.createElement('button');
        pill.type = 'button';
        pill.className = 'hw-dock-ippill' + (dup ? ' hw-dock-ippill-dup' : '');
        pill.dataset.lrdField = `processor-ip-pill-${proc.id}`;
        pill.textContent = unit.ip;
        pill.title = (dup ? NET().duplicateText(dup) + ' ' : `IP ${unit.ip}. `)
            + 'Click to open the processor\'s ⚙, where it is set.';
        pill.addEventListener('click', (e) => {
            e.stopPropagation();
            if (typeof this._dockOpenProcGear === 'function') this._dockOpenProcGear(proc.id);
        });
        return pill;
    }

    // The Data tray's warning rows: one per IP two or more units share.
    networkIssueRows() {
        const net = NET();
        if (!net) return [];
        return this.networkDuplicates().map(dup => {
            const row = document.createElement('div');
            row.className = 'hw-dock-issue hw-dock-issue-net';
            const msg = document.createElement('span');
            msg.className = 'hw-dock-issue-msg';
            msg.textContent = net.duplicateText(dup);
            row.appendChild(msg);
            const btn = document.createElement('button');
            btn.className = 'btn';
            btn.style.padding = '4px 8px';
            btn.style.fontSize = '11px';
            btn.style.background = '#333';
            btn.textContent = 'Open';
            btn.title = `Open ${dup.units[0].name}'s ⚙, where its IP is set.`;
            btn.addEventListener('click', () => {
                if (typeof this._dockOpenProcGear === 'function') this._dockOpenProcGear(dup.units[0].procId);
            });
            row.appendChild(btn);
            return row;
        });
    }

    // ---- the binder ----------------------------------------------------------

    // A Data sheet's FACTS lines for one processor: its IP, and its backup
    // unit's - only once some unit in the show has an IP; a unit with none
    // prints a blank value.
    _bNetworkFacts(proc) {
        const units = this.networkUnits();
        if (!NET() || !NET().anyIp(units)) return [];
        return units.filter(u => u.procId === proc.id)
            .map(u => [u.slot === 'bu' ? 'Backup IP' : 'IP', u.ip]);
    }

    // A processor sheet's NETWORK table: the named units of `proc` (`slots`:
    // 'main', 'bu') - UNIT, IP, SUBNET, GATEWAY, NOTE - or null while no
    // unit in the show has an IP. Empty cells stay blank.
    _bProcNetworkTable(book, proc, slots) {
        const units = this.networkUnits();
        if (!NET() || !NET().anyIp(units)) return null;
        const rows = units.filter(u => u.procId === proc.id && slots.includes(u.slot))
            .map(u => ({ cells: [u.name, u.ip, u.subnet, u.gateway, u.note] }));
        if (!rows.length) return null;
        return this._bTableLines(book, {
            title: 'Network',
            cols: [{ title: 'unit', w: 1.1, list: 2, words: true }, { title: 'ip', w: 1 },
                   { title: 'subnet', w: 1 }, { title: 'gateway', w: 1 },
                   { title: 'note', w: 1.2, list: 2, words: true }],
            rows,
        });
    }

    // THE NETWORK PAGE: one table of every unit - PROCESSOR, MODEL, UNIT
    // (Main or Backup), IP, SUBNET, GATEWAY, NOTE - tray order, each main
    // then its backup unit. One page, its own number in the hardware
    // series; a list longer than the sheet continues "(cont.)". Nothing
    // where no unit has an IP. Front and Rear do not apply.
    _bNetworkSheets(book) {
        const units = this.networkUnits();
        if (!NET() || !NET().anyIp(units)) return;
        const lines = this._bTableLines(book, {
            title: `${units.length} ${units.length === 1 ? 'unit' : 'units'}`,
            width: Math.floor(book.geo.da.w),
            cols: [{ title: 'processor', w: 1.4, list: 2, words: true }, { title: 'model', w: 1.1, list: 2, words: true },
                   { title: 'unit', w: 0.7 }, { title: 'ip', w: 1 }, { title: 'subnet', w: 1 },
                   { title: 'gateway', w: 1 }, { title: 'note', w: 1.8, list: 2, words: true }],
            rows: units.map(u => ({ cells: [u.name, u.model, u.role === 'backup' ? 'Backup' : 'Main',
                                            u.ip, u.subnet, u.gateway, u.note] })),
        });
        this._bColumnSheets(book, {
            colW: Math.floor(book.geo.da.w),
            page: () => ({ kind: 'network', title: 'Network', sheetTitle: 'NETWORK', subject: 'Network' }),
        }, [{ kind: 'network', name: 'Network', blocks: [{ lines }] }]);
    }
}

for (const k of Object.getOwnPropertyNames(_Network.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Network.prototype, k));
    }
}
