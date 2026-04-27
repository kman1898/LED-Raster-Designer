#!/bin/bash
# Loop clipboard_extract.sh in batches of N until no more missing panels
set -euo pipefail
cd "$(dirname "$0")"
BATCH=${1:-50}
CYCLE=0
while true; do
    CYCLE=$((CYCLE+1))
    BEFORE=$(python3 -c "import json; print(sum(len(v) for v in json.load(open('../../src/static/data/panel_catalog.json')).values()))")
    python3 next_batch.py $BATCH > /dev/null 2>&1
    if [ ! -s /tmp/panel_batch.txt ]; then
        echo "No more missing panels — done!"; break
    fi
    COUNT_IN=$(wc -l < /tmp/panel_batch.txt | tr -d ' ')
    echo ""
    echo "=== Cycle $CYCLE ($COUNT_IN panels to click) ==="
    bash clipboard_extract.sh > /tmp/raw_panels.json 2>> /tmp/clip_all.log
    GOT=$(python3 -c "import json; print(len(json.load(open('/tmp/raw_panels.json'))))" 2>/dev/null || echo 0)
    echo "Extracted $GOT / $COUNT_IN"
    python3 merge_web.py /tmp/raw_panels.json 2>&1 | tail -3
    AFTER=$(python3 -c "import json; print(sum(len(v) for v in json.load(open('../../src/static/data/panel_catalog.json')).values()))")
    ADDED=$((AFTER - BEFORE))
    echo "Cycle $CYCLE added $ADDED, total: $AFTER"
    # Stop if a cycle adds 0 (stuck on panels that don't match)
    if [ $ADDED -eq 0 ]; then
        echo "No panels added this cycle — adding batch to skip list and stopping"
        while IFS=$'\t' read -r MFR PANEL; do
            [ -n "$MFR" ] && echo "$MFR	$PANEL" >> skip_list.txt
        done < /tmp/panel_batch.txt
        break
    fi
done
