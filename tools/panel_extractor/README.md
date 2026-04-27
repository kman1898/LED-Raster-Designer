# Panel Catalog Extractor

Tooling to extract the LED panel database (width, height, pixel count,
weight, max power) from FidoLED and merge it into
`src/static/data/panel_catalog.json`, which powers the in-app Panel Catalog.

## Approach

FidoLED exposes a "Copy to Clipboard" button on its Calculate results window
that outputs clean plain text. We drive the app via AppleScript: select a
(manufacturer, panel) pair, click Calculate, click Copy to Clipboard, read
`pbpaste`, parse, merge. Works against the stock `/Applications/FidoLED.app` —
no re-signing needed.

An earlier memory-dump approach (lldb `process save-core` + SQLite page
parsing) is retired; the clipboard method is faster and more reliable.

## One-time setup

1. Grant Accessibility permission to Terminal (System Settings → Privacy &
   Security → Accessibility).
2. Launch FidoLED (`open /Applications/FidoLED.app`).
3. In FidoLED set **Modules Wide = 1** and **Modules High = 1** so Calculate
   doesn't error on unknown configs.

## Running

```bash
cd tools/panel_extractor

# Extract in batches of 50 until the catalog is complete
bash clipboard_loop.sh 50
```

Each cycle picks the next N panels from `panel_catalog_full_list.txt` that
aren't already in the catalog or in `skip_list.txt`, drives FidoLED, writes
a JSON batch, and merges into the main catalog.

## Files

- `clipboard_extract.sh` — drives FidoLED for one batch, parses clipboard
  output, emits JSON.
- `clipboard_loop.sh` — runs `clipboard_extract.sh` in a loop until no
  panels remain.
- `next_batch.py` — picks the next N missing (manufacturer, panel) pairs
  into `/tmp/panel_batch.txt`, excluding anything in `skip_list.txt`.
- `merge_web.py` — merges an extraction batch (or manually curated JSON)
  into the catalog, grouped by manufacturer.
- `skip_list.txt` — panels known to fail extraction; excluded from batches.

## Catalog file

`src/static/data/panel_catalog.json` — grouped by manufacturer:

```json
{
  "Absen": [
    {
      "name": "X5",
      "manufacturer": "Absen",
      "width_mm": 500,
      "height_mm": 562.5,
      "pixels_w": 96,
      "pixels_h": 108,
      "weight_kg": 10,
      "watts_max": 156,
      "amps_max_110v": 1.42,
      "source": "fidoled clipboard"
    }
  ]
}
```

`src/static/data/panel_catalog_full_list.txt` — tab-separated
(manufacturer, panel_name) for every panel in FidoLED's dropdown. Used as
the source-of-truth of what's missing.
