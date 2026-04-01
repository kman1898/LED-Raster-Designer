#!/usr/bin/env python3
"""Quick SCR binary comparison tool. Usage: python3 tools/scr_compare.py native.scr export.scr"""
import struct, sys

def parse(path):
    with open(path, 'rb') as f: data = f.read()
    ns = data[0x13A]
    off = 0x13B + ns * 4
    screens = []
    for si in range(ns):
        cols = struct.unpack_from('<H', data, off+6)[0]
        rows = struct.unpack_from('<H', data, off+8)[0]
        marker = data[off+10:off+14]
        off += 14
        recs = {}
        for c in range(cols):
            for r in range(rows):
                o = off + (c*rows+r)*17
                recs[(c,r)] = {'s':data[o+13],'p':data[o+14],'ch':struct.unpack_from('<H',data,o+15)[0]}
        off += cols*rows*17 + 11
        screens.append({'cols':cols,'rows':rows,'marker':marker.hex(),'recs':recs})
    return screens

def show_row(scr, brow, label=''):
    cols, rows = scr['cols'], scr['rows']
    vis = [(c, scr['recs'][(c,brow)]) for c in range(cols) if scr['recs'][(c,brow)]['s']!=0xFF]
    vcols = [v[0] for v in vis]
    print(f"  {label}brow={brow} (app {(brow+1)%rows}): {len(vis)} vis cols={min(vcols) if vcols else '-'}-{max(vcols) if vcols else '-'}")
    for c, r in vis:
        print(f"    c={c:2d} s={r['s']} p={r['p']:2d} ch={r['ch']}")

if __name__ == '__main__':
    native = parse(sys.argv[1])
    export = parse(sys.argv[2]) if len(sys.argv) > 2 else None
    for si, s in enumerate(native):
        print(f"\n=== Screen {si} ({s['cols']}x{s['rows']}) marker={s['marker']} ===")
        show_row(s, s['rows']-1, 'NAT origin ')
        show_row(s, 0, 'NAT adjacent ')
        if export and si < len(export):
            e = export[si]
            show_row(e, e['rows']-1, 'EXP origin ')
            show_row(e, 0, 'EXP adjacent ')
            # Diff origin rows
            orow = s['rows']-1
            for c in range(s['cols']):
                nr, er = s['recs'][(c,orow)], e['recs'][(c,orow)]
                if nr['s'] != er['s'] or nr['p'] != er['p'] or nr['ch'] != er['ch']:
                    print(f"  DIFF c={c}: nat s={nr['s']} p={nr['p']} ch={nr['ch']} | exp s={er['s']} p={er['p']} ch={er['ch']}")
