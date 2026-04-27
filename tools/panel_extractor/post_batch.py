#!/usr/bin/env python3
"""Post-batch step: auto-skip menu-item-not-found triggers, rebuild no_source_list.txt.

Run after merge_web.py. Reads /tmp/resync.err for AppleScript "Can't get menu
item" failures and adds those panels to skip_list.txt so they don't re-enter
the queue. Then rebuilds no_source_list.txt from the current catalog.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CATALOG = REPO / 'src' / 'static' / 'data' / 'panel_catalog.json'

err = open('/tmp/resync.err').read() if Path('/tmp/resync.err').exists() else ''
catalog = json.load(open(CATALOG))

# Auto-skip panels that AppleScript could not find in FidoLED's menus
existing = set(open(HERE / 'skip_list.txt').read().splitlines()) if (HERE / 'skip_list.txt').exists() else set()
added = []
for line in err.splitlines():
    m = re.search(r"expected='([^']+)'.*Can.t get menu item", line)
    if not m:
        continue
    label = m.group(1)
    words = label.split(' ')
    for s in range(1, len(words)):
        mfr_u = '_'.join(words[:s])
        mfr_s = ' '.join(words[:s])
        mfr = mfr_u if mfr_u in catalog else (mfr_s if mfr_s in catalog else None)
        if mfr:
            entry = f"{mfr}\t{' '.join(words[s:])}"
            if entry not in existing:
                added.append(entry)
                existing.add(entry)
            break

if added:
    with open(HERE / 'skip_list.txt', 'a') as f:
        for entry in added:
            f.write(entry + '\n')
    print(f"Auto-skipped {len(added)} unfindable panels:")
    for entry in added:
        print(' ', entry)

# Rebuild no_source_list.txt
skip = set()
for line in open(HERE / 'skip_list.txt').read().splitlines():
    if '\t' in line:
        skip.add(tuple(line.split('\t')))
no_src = [
    (mfr, p['name'])
    for mfr, panels in catalog.items()
    for p in panels
    if not p.get('source') and (mfr, p['name']) not in skip
]
with open(HERE / 'no_source_list.txt', 'w') as f:
    for mfr, name in no_src:
        f.write(f"{mfr}\t{name}\n")
print(f"NO_SOURCE remaining: {len(no_src)}")
