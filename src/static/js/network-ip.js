// The processors' network settings (owner, 2026-11-09: "add to the
// processors the ability to IP addresses and that would be represented on
// the binder"): which units there are, what each one's IP, subnet mask,
// gateway and note read as, which entries are not addresses, and which IPs
// two units share. Plain functions, no DOM, so tests/test_network_ip.py can
// run the file under node.
// Classic script: defines the global NetworkIp, loads before the app.
//
// The stored shape (processor_catalog.network_of): each processor's
// `network` and its backup unit's, {ip, subnet, gateway, note}, a blank
// field no key; the show's {subnet, gateway}, which a unit reads wherever
// its own is blank. Nothing here refuses anything: a bad entry is marked
// red in its field and printed as typed.
const NetworkIp = (() => {
    const text = (v) => (typeof v === 'string' ? v.trim() : '');

    // Four whole numbers from 0 to 255, dot separated, no sign, no spaces
    // and no leading zero ("010" is read as octal by some tools).
    function isIPv4(value) {
        const parts = text(value).split('.');
        if (parts.length !== 4) return false;
        return parts.every(p => /^(0|[1-9]\d{0,2})$/.test(p) && Number(p) <= 255);
    }

    // A subnet mask: dotted (255.255.255.0) with its ones all to the left,
    // or a prefix length, /24 or 24, from 1 to 32.
    function isSubnetMask(value) {
        const t = text(value);
        const prefix = /^\/?(\d{1,2})$/.exec(t);
        if (prefix) {
            const n = Number(prefix[1]);
            return String(n) === prefix[1] && n >= 1 && n <= 32;
        }
        if (!isIPv4(t)) return false;
        const bits = t.split('.').map(p => Number(p).toString(2).padStart(8, '0')).join('');
        return /^1+0*$/.test(bits);
    }

    // The plain words a field's tooltip says when its entry is not one;
    // '' for a good entry or a blank one. `kind`: ip, subnet or gateway.
    function problem(kind, value) {
        const t = text(value);
        if (!t) return '';
        if (kind === 'subnet') {
            return isSubnetMask(t) ? ''
                : 'Not a subnet mask, use one like 255.255.255.0 or /24. It still prints as typed.';
        }
        if (kind === 'ip' || kind === 'gateway') {
            return isIPv4(t) ? ''
                : `Not ${kind === 'ip' ? 'an IP address' : 'a gateway address'}: use four numbers `
                    + 'from 0 to 255 with dots between, like 10.0.0.10. It still prints as typed.';
        }
        return '';
    }

    function fieldsOf(raw) {
        const r = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
        return { ip: text(r.ip), subnet: text(r.subnet), gateway: text(r.gateway), note: text(r.note) };
    }

    // Every unit, in tray order, main then its backup unit:
    //   { key, slot: 'main' | 'bu', procId, role: 'main' | 'backup', name,
    //     model, ip, subnet,
    //     gateway, note, own: {ip, subnet, gateway, note},
    //     shown: { subnet: bool, gateway: bool } }
    // `subnet` and `gateway` are what prints: the unit's own, else the
    // show's (`shown` true where the show's stands in). `procs` is the
    // resolved tree; `opts.title(proc)` names a processor (its name, else
    // its model), `opts.backupOf(proc)` says whether a processor is
    // another's designated backup (a second unit whose every card backs
    // up that one), which reads as a backup too.
    function units(procs, show, opts = {}) {
        const showNet = fieldsOf(show);
        const title = opts.title || (p => text(p.name) || p.deviceName || p.id);
        const out = [];
        const add = (proc, slot, role, name, raw) => {
            const own = fieldsOf(raw);
            out.push({
                key: `${proc.id}:${slot}`, slot,
                procId: proc.id, role, name, model: proc.deviceName || '',
                ip: own.ip, note: own.note,
                subnet: own.subnet || showNet.subnet,
                gateway: own.gateway || showNet.gateway,
                own,
                shown: { subnet: !own.subnet && !!showNet.subnet, gateway: !own.gateway && !!showNet.gateway },
            });
        };
        for (const proc of procs || []) {
            if (!proc || !proc.id) continue;
            const backupOf = opts.backupOf ? opts.backupOf(proc) : false;
            add(proc, 'main', backupOf ? 'backup' : 'main', title(proc), proc.network);
            if (proc.backupUnit) {
                add(proc, 'bu', 'backup', proc.backupUnit.name || `${title(proc)} BU`, proc.backupUnit.network);
            }
        }
        return out;
    }

    // Whether any unit has an IP: the Network page prints only then.
    function anyIp(list) {
        return (list || []).some(u => !!u.ip);
    }

    // IPs two or more units share: [{ ip, units: [unit, ...] }], in the
    // order the first of each is listed. Compared as typed, trimmed.
    function duplicates(list) {
        const by = new Map();
        for (const u of list || []) {
            if (!u.ip) continue;
            if (!by.has(u.ip)) by.set(u.ip, []);
            by.get(u.ip).push(u);
        }
        return [...by.entries()].filter(([, us]) => us.length > 1).map(([ip, us]) => ({ ip, units: us }));
    }

    // "A and B", "A, B and C".
    function andList(names) {
        if (names.length <= 1) return names.join('');
        return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
    }

    // The warning a shared IP earns, naming every unit on it.
    function duplicateText(dup) {
        return `${andList(dup.units.map(u => u.name))} have the same IP, ${dup.ip}. `
            + 'Give each unit its own.';
    }

    return { isIPv4, isSubnetMask, problem, units, anyIp, duplicates, duplicateText, andList };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = NetworkIp;
