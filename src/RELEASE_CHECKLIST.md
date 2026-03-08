# LED Raster Designer - Release Checklist

Use this checklist **every time** a new version is created and zipped.

## 1) Source + Docs
- [ ] Version number updated in `VERSION.txt` (top entry).
- [ ] Version number updated in `README.md` title.
- [ ] README content verified against current UI/behavior.
- [ ] `TODO.txt` updated (only open work; completed items moved to `VERSION.txt`).

## 2) Clean Logs (for zips)
- [ ] Ensure zip contains an **empty** `logs/` folder.
- [ ] Ensure **no** `led_raster_designer.log` is inside the zip.

## 3) Build the Zip
- [ ] Zip name matches: `led_raster_designer_vX.Y.Z.W.zip`
- [ ] Zip contents root folder is `led_raster_designer`
- [ ] Zip saved to: `../Archive/`

## 4) Sanity Pass (Beta Tester)
- [ ] App launches (Windows and Mac install steps still valid).
- [ ] Save/Open works.
- [ ] Export works (single + multi).
- [ ] Data + Power visuals render without errors.

## 5) Archive Verification
- [ ] Confirm zip appears in `Archive/`
- [ ] Confirm logs are empty inside the zip
