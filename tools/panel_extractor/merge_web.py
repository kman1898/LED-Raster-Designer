#!/usr/bin/env python3
"""Merge web-researched panel data into the catalog.

Input JSON format (one array of panel objects) with these fields:
  name, manufacturer (required)
  width_mm, height_mm, pixels_w, pixels_h, weight_kg, watts_max, watts_ave,
  pitch_mm, source (all optional)

Unlike merge.py (which uses the FidoLED name→mfr map for resolution), this
script trusts the explicit `manufacturer` field in each record. Use it for
web-sourced data.

Usage: python3 merge_web.py panels.json [--overwrite]

  --overwrite  Replace any existing entry with the same (manufacturer, name)
               instead of skipping it. Used for fixing bad entries from the
               legacy memory-dump extraction.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CATALOG_PATH = REPO / 'src' / 'static' / 'data' / 'panel_catalog.json'
SKIP_LIST_PATH = HERE / 'skip_list.txt'

def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--')]
    flags = [a for a in argv[1:] if a.startswith('--')]
    overwrite = '--overwrite' in flags
    if len(args) != 1:
        print(f'usage: {argv[0]} <panels.json> [--overwrite]', file=sys.stderr); sys.exit(2)
    with open(args[0]) as f:
        incoming = json.load(f)

    catalog = json.load(open(CATALOG_PATH))
    # index by (mfr, name) -> list_index for in-place overwrite
    index = {}
    for mfr, panels in catalog.items():
        for i, p in enumerate(panels):
            index[(mfr, p['name'])] = i
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
        if key in index:
            if overwrite:
                catalog[mfr][index[key]] = entry
                updated += 1
            else:
                duplicate += 1
        else:
            catalog.setdefault(mfr, []).append(entry)
            index[key] = len(catalog[mfr]) - 1
            added += 1
    for mfr in catalog:
        catalog[mfr].sort(key=lambda e: e['name'].lower())
    with open(CATALOG_PATH, 'w') as f:
        json.dump(catalog, f, indent=2)
    total = sum(len(v) for v in catalog.values())
    print(f'merge_web: added={added} updated={updated} duplicate={duplicate} skipped={skipped}',
          file=sys.stderr)
    print(f'catalog now: {total} panels, {len(catalog)} manufacturers',
          file=sys.stderr)

if __name__ == '__main__':
    main(sys.argv)
