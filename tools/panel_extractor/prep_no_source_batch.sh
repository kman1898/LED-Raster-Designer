#!/bin/bash
# Prepare the next batch of no-source panels for re-extraction.
# - Kills any running FidoLED instances
# - Relaunches /Applications/FidoLED.app
# - Writes the next N panels (default 100) from no_source_list.txt to
#   /tmp/panel_batch.txt
#
# After this runs, the user should set Modules Wide=1, Modules High=1 in
# FidoLED, then we run `bash clipboard_extract.sh`.
#
# Usage: bash prep_no_source_batch.sh [N]
set -euo pipefail
cd "$(dirname "$0")"

N="${1:-100}"
LIST="no_source_list.txt"

if [ ! -s "$LIST" ]; then
    echo "no_source_list.txt is empty or missing." >&2
    exit 1
fi

REMAINING=$(wc -l < "$LIST" | tr -d ' ')
echo "Remaining no-source panels: $REMAINING"
echo "This batch: first $N"

# Kill any running FidoLED instances (regular + re-signed)
pkill -9 -f "FidoLED" 2>/dev/null || true
sleep 1.5

# Launch the stock FidoLED detached (so cancelling our shell doesn't kill it)
open /Applications/FidoLED.app
sleep 2

# Write top N panels to /tmp/panel_batch.txt
head -n "$N" "$LIST" > /tmp/panel_batch.txt
echo "Wrote $(wc -l < /tmp/panel_batch.txt | tr -d ' ') panels to /tmp/panel_batch.txt"
echo
echo "First 3:"
head -3 /tmp/panel_batch.txt
echo "Last 3:"
tail -3 /tmp/panel_batch.txt
echo
echo "Now: in FidoLED, set Modules Wide = 1 and Modules High = 1, then say 'ready'."
