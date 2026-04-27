#!/bin/bash
# Clipboard-based panel extractor. For each (mfr, panel) in /tmp/panel_batch.txt,
# selects the panel in FidoLED, clicks Calculate, clicks "Copy to Clipboard",
# reads pbpaste, parses the text, and writes a JSON array to stdout.
#
# Requires: Modules Wide = 1 and Modules High = 1 set in FidoLED.
# Works on the regular /Applications/FidoLED.app — no re-signing needed.
#
# Usage:
#   python3 next_batch.py 50
#   bash clipboard_extract.sh > /tmp/raw_panels.json
#   python3 merge_web.py /tmp/raw_panels.json
set -euo pipefail
cd "$(dirname "$0")"

if ! pgrep -f "FidoLED" > /dev/null; then
    echo "ERROR: FidoLED not running" >&2; exit 1
fi

TOTAL=$(wc -l < /tmp/panel_batch.txt | tr -d ' ')
echo "[" > /tmp/clip_out.json
FIRST=1
COUNT=0
CONSEC_ERR=0   # Abort batch after this many consecutive ERR/INVALID-INDEX responses
MAX_CONSEC_ERR=5

while IFS=$'\t' read -r MFR PANEL; do
    [ -z "$MFR" ] && continue
    COUNT=$((COUNT + 1))

    # Escape double-quotes for AppleScript (unlikely but safe)
    MFR_ESC=$(echo "$MFR" | sed 's/"/\\"/g')
    PANEL_ESC=$(echo "$PANEL" | sed 's/"/\\"/g')

    # Clear the clipboard first so we can detect failed selections
    pbcopy < /dev/null

    # Run AppleScript: select + calc + copy + close. Returns the results
    # window title so we can verify we got the right panel (not stale state).
    WIN_TITLE=$(osascript <<EOF 2>/dev/null
tell application "System Events"
    tell process "FidoLED"
        try
            key code 53
            delay 0.1
            key code 53
            delay 0.15
        end try
        try
            set mfrPopup to pop up button 2 of window "FidoLED"
            click mfrPopup
            delay 0.6
            click menu item "$MFR_ESC" of menu 1 of mfrPopup
            delay 0.9
            set panelPopup to pop up button 3 of window "FidoLED"
            click panelPopup
            delay 0.6
            click menu item "$PANEL_ESC" of menu 1 of panelPopup
            delay 0.5
            click button "Calculate" of window "FidoLED"
            delay 1.3
            set resultWin to missing value
            repeat with w in windows
                if name of w is not "FidoLED" then
                    set resultWin to w
                    exit repeat
                end if
            end repeat
            if resultWin is not missing value then
                set wTitle to name of resultWin
                click button "Copy to Clipboard" of resultWin
                delay 0.3
                click button "Close" of resultWin
                delay 0.2
                return wTitle
            end if
            return "NO_RESULT_WINDOW"
        on error errMsg
            return "ERR:" & errMsg
        end try
    end tell
end tell
EOF
)

    # Detect cascading FidoLED popup-state corruption: if we see N consecutive
    # AppleScript errors, the popup is wedged and further calls will all fail.
    # Bail so the user can restart FidoLED rather than waste time.
    case "$WIN_TITLE" in
        ERR:*|NO_RESULT_WINDOW)
            CONSEC_ERR=$((CONSEC_ERR + 1))
            echo "  [MISMATCH] expected='$MFR $PANEL' got='$WIN_TITLE'" >&2
            if [ "$CONSEC_ERR" -ge "$MAX_CONSEC_ERR" ]; then
                echo "  [ABORT] $CONSEC_ERR consecutive errors — FidoLED popup likely wedged. Stopping batch early." >&2
                break
            fi
            continue
            ;;
        *)
            CONSEC_ERR=0
            ;;
    esac

    # Verify window title matches what we asked for (mfr + panel) — case-insensitive
    # since FidoLED's results window may use different capitalization than the
    # menu item we clicked (e.g. "Litepix 3+" → "LITEPIX 3+"). The data is still
    # correct; only the title casing differs.
    EXPECTED="$MFR $PANEL"
    if [ "$(echo "$WIN_TITLE" | tr '[:upper:]' '[:lower:]')" != "$(echo "$EXPECTED" | tr '[:upper:]' '[:lower:]')" ]; then
        echo "  [MISMATCH] expected='$EXPECTED' got='$WIN_TITLE'" >&2
        continue
    fi

    # Read clipboard and parse
    CLIP=$(pbpaste)
    if [ -z "$CLIP" ]; then
        echo "  [NO_CLIP] $MFR / $PANEL" >&2
        continue
    fi

    # Parse using Python for robustness (regexes on variable text)
    PY_OUT=$(python3 - <<PYEOF
import re, json, sys
text = """$CLIP"""
mfr = """$MFR_ESC"""
panel = """$PANEL_ESC"""
# Extract fields
r = {'manufacturer': mfr, 'name': panel}
m = re.search(r'Pixels:\s*([\d,]+)\s*x\s*([\d,]+)', text)
if m:
    r['pixels_w'] = int(m.group(1).replace(',', ''))
    r['pixels_h'] = int(m.group(2).replace(',', ''))
m = re.search(r'Physical\(mm\):\s*([\d,.]+)\s*Wide\s*x\s*([\d,.]+)\s*High', text)
if m:
    r['width_mm'] = float(m.group(1).replace(',', ''))
    r['height_mm'] = float(m.group(2).replace(',', ''))
m = re.search(r"Physical\(Kg's\):\s*([\d.]+)", text)
if m:
    r['weight_kg'] = float(m.group(1))
m = re.search(r'Power Max.*?:\s*([\d.]+)\s*amps', text)
if m:
    amps = float(m.group(1))
    r['watts_max'] = round(amps * 110, 1)  # 1-phase 110V
    r['amps_max_110v'] = amps
r['source'] = 'fidoled clipboard'
# Valid if we got physical specs AND power. If power is missing it usually
# means voltage wasn't set in FidoLED — treat as failed so it re-runs next
# batch with correct settings rather than nuking the existing power value.
if 'width_mm' in r and 'pixels_w' in r and 'watts_max' in r:
    print(json.dumps(r))
else:
    sys.exit(0)
PYEOF
)

    if [ -n "$PY_OUT" ]; then
        if [ $FIRST -eq 1 ]; then
            echo "$PY_OUT" >> /tmp/clip_out.json
            FIRST=0
        else
            echo ",$PY_OUT" >> /tmp/clip_out.json
        fi
        # Brief progress to stderr every 10 panels
        if [ $((COUNT % 10)) -eq 0 ]; then
            echo "  [$COUNT/$TOTAL] last: $MFR / $PANEL" >&2
        fi
    else
        # Most common cause: voltage wasn't set in FidoLED so the clipboard
        # output had no "Power Max ... amps" line. Surface this clearly so
        # the user knows what to fix before the next batch.
        if echo "$CLIP" | grep -q "Power Max"; then
            echo "  [FAIL] $MFR / $PANEL (parse failed)" >&2
        else
            echo "  [NO_POWER] $MFR / $PANEL — clipboard had no power line (set 110V?)" >&2
        fi
    fi
done < /tmp/panel_batch.txt

echo "]" >> /tmp/clip_out.json
cat /tmp/clip_out.json
