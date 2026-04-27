#!/usr/bin/env python3
"""Write the next N (mfr, panel) pairs that are still missing from the
catalog to /tmp/panel_batch.txt. Then click_batch.applescript can drive
FidoLED through each of them.

Usage:
    python3 next_batch.py [N]    # default N=50
"""
import json, sys
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CATALOG_PATH = REPO / 'src' / 'static' / 'data' / 'panel_catalog.json'
NAME_MAP_PATH = REPO / 'src' / 'static' / 'data' / 'panel_catalog_full_list.txt'
# Panels that keep showing as "missing" but never load into FidoLED's
# in-memory cache (probably deprecated records, non-$N$RJ45 format, or just
# data the extractor can't parse). We skip them so the batch loop doesn't
# spin on the same unreachable entries forever.
SKIP_LIST_PATH = HERE / 'skip_list.txt'

def load_skip_list():
    skip = set()
    if SKIP_LIST_PATH.exists():
        with open(SKIP_LIST_PATH) as f:
            for line in f:
                parts = line.rstrip('\n').split('\t')
                if len(parts) == 2:
                    skip.add((parts[0], parts[1]))
    return skip

def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 50
    catalog = {}
    if CATALOG_PATH.exists():
        with open(CATALOG_PATH) as f:
            catalog = json.load(f)
    have = {(mfr, p['name']) for mfr, panels in catalog.items() for p in panels}
    skip = load_skip_list()

    # Walk the full list in order, collecting missing entries not in skip list
    missing = []
    with open(NAME_MAP_PATH) as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 2: continue
            mfr, name = parts
            if mfr == 'Please Select': continue
            if (mfr, name) in have: continue
            if (mfr, name) in skip: continue
            missing.append((mfr, name))

    if not missing:
        print('All panels already loaded! Nothing to do.', file=sys.stderr)
        open('/tmp/panel_batch.txt', 'w').close()
        return

    batch = missing[:n]
    with open('/tmp/panel_batch.txt', 'w') as f:
        for mfr, name in batch:
            f.write(f'{mfr}\t{name}\n')

    mfr_count = len(set(m for m, _ in batch))
    print(f'Wrote {len(batch)} panels to /tmp/panel_batch.txt '
          f'(across {mfr_count} manufacturers)', file=sys.stderr)
    print(f'Total still missing after this batch: {len(missing) - len(batch)}',
          file=sys.stderr)

if __name__ == '__main__':
    main(sys.argv)
