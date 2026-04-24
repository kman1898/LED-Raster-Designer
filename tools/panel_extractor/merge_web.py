#!/usr/bin/env python3
"""Merge web-researched panel data into the catalog.

Input JSON format (one array of panel objects) with these fields:
  name, manufacturer (required)
  width_mm, height_mm, pixels_w, pixels_h, weight_kg, watts_max, watts_ave,
  pitch_mm, source (all optional)

Unlike merge.py (which uses the FidoLED name→mfr map for resolution), this
script trusts the explicit `manufacturer` field in each record. Use it for
web-sourced data.

Usage: python3 merge_web.py panels.json
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CATALOG_PATH = REPO / 'src' / 'static' / 'data' / 'panel_catalog.json'
SKIP_LIST_PATH = HERE / 'skip_list.txt'

def main(argv):
    if len(argv) != 2:
        print(f'usage: {argv[0]} <panels.json>', file=sys.stderr); sys.exit(2)
    with open(argv[1]) as f:
        incoming = json.load(f)

    catalog = json.load(open(CATALOG_PATH))
    have = {(m, p['name']) for m, panels in catalog.items() for p in panels}
    added = updated = duplicate = skipped = 0
    for p in incoming:
        mfr = p.get('manufacturer')
        name = p.get('name')
        if not mfr or not name:
            skipped += 1; continue
        # Skip entries with no real data (all None)
        has_data = any(p.get(k) is not None for k in
                       ('width_mm', 'height_mm', 'pixels_w', 'pixels_h',
                        'weight_kg', 'watts_max'))
        if not has_data:
            skipped += 1; continue
        entry = {
            'name': name,
            'connector': p.get('connector'),
            'width_mm': p.get('width_mm'),
            'height_mm': p.get('height_mm'),
            'pixels_w': p.get('pixels_w'),
            'pixels_h': p.get('pixels_h'),
            'pitch_mm': p.get('pitch_mm'),
            'weight_kg': p.get('weight_kg'),
            'weight_lb': (p.get('weight_kg') * 2.20462
                         if p.get('weight_kg') is not None else None),
            'proc_type': p.get('proc_type'),
            'watts_max': p.get('watts_max'),
            'watts_ave': p.get('watts_ave'),
            'source': p.get('source', 'web_research'),
        }
        # Compute pitch_mm if missing
        if entry['pitch_mm'] is None and entry['pixels_w'] and entry['width_mm']:
            entry['pitch_mm'] = round(entry['width_mm'] / entry['pixels_w'], 3)
        key = (mfr, name)
        if key in have:
            duplicate += 1
        else:
            catalog.setdefault(mfr, []).append(entry)
            have.add(key)
            added += 1
    for mfr in catalog:
        catalog[mfr].sort(key=lambda e: e['name'].lower())
    with open(CATALOG_PATH, 'w') as f:
        json.dump(catalog, f, indent=2)
    total = sum(len(v) for v in catalog.values())
    print(f'merge_web: added={added} duplicate={duplicate} skipped={skipped}',
          file=sys.stderr)
    print(f'catalog now: {total} panels, {len(catalog)} manufacturers',
          file=sys.stderr)

if __name__ == '__main__':
    main(sys.argv)
