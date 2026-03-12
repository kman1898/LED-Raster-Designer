# LED Raster Designer — AI Development Handoff

> **"LED Raster Designer" is a PLACEHOLDER NAME.** Final product name TBD.

> **Last updated in this file:** v0.5.6.15 — February 10, 2026 (historical snapshot)
>
> **Current source of truth:**
> - `README.md` (current behavior/features)
> - `VERSION.txt` (completed release history)
> - `TODO.txt` (open work only)

---

## Latest Changes (v0.5.6.15)

- Data/Power info line now anchors under screen name and shows amps for power.

## Previous Changes (v0.5.6.14)

- FIX: Data/Power info checkbox now stays enabled.

## Previous Changes (v0.5.6.13)

- FIX: screen name size now persists for Cabinet/Data/Power tabs.
- Multi-select: Shift+drag now moves all selected layers.
- Data/Power: optional port/circuit info under screen name.

## Previous Changes (v0.5.6.12)

- FIX: border colors now apply from all tabs (no reliance on updateLayerFromInputs).

## Previous Changes (v0.5.6.11)

- FIX: color picker updates restored (removed stale power custom debug handler).

## Previous Changes (v0.5.6.10)

- Logging: 3-file rotation at 20MB each (led_raster_designer.log, .1, .2).
- Color pickers: macOS swatch hiding fixed for all pickers.

## Previous Changes (v0.5.6.9)

- Power: label list inputs now fit without horizontal scrolling.

## Previous Changes (v0.5.6.8)

- Power: label list now refreshes on tab entry (fixes empty list on first open).

## Previous Changes (v0.5.6.6)

- macOS: redundant swatch removed (native picker only).
- Windows/Linux: swatch retained for custom picker.

## Previous Changes (v0.5.6.5)

- macOS: native system color picker restored for all pickers.
- Windows/Linux: custom macOS-style picker retained.
- Color inputs now use type=color so macOS picker works everywhere.

## Previous Changes (v0.5.6.4)

- macOS now uses native system color picker on all browsers.
- Windows/Linux continue to use the custom macOS-style picker.
- Power: selection highlights update live while dragging.
- Custom selection now clears on any click (not just inside layer).

## Previous Changes (v0.5.6.3)

- Color pickers now use the custom macOS-style picker on all platforms/browsers.
- Added canvas-based eyedropper fallback when native EyeDropper is unavailable.
- Power: flow pattern clicks no longer reset custom voltage/amperage state.
- Power: custom panel selection enabled on the canvas.

## Previous Changes (v0.5.6.2)

- Power tab: fixed circuit rendering after changing flow patterns.
- Power tab: custom mode moved near flow pattern, grid layout normalized.
- Power tab: Maximize and Organized now mutually exclusive.

## Previous Changes (v0.5.6.0)

- Power tab overhaul: circuit-based serpentine routing, voltage/amperage/watts inputs.
- Calculated power display with total amps for 1φ and 3φ.
- Power custom path mode and flow pattern support.

## Previous Changes (v0.5.5.42)

- Updated default screen colors to #404680 and #959CB8.

## Previous Changes (v0.5.5.41)

- Fixed checkerboard color pickers to use the custom/native picker pipeline.

## Previous Changes (v0.5.5.40)

- Custom picker: corrected macOS swatch order and layout.
- Added "no color" swatch styling in the popover (non-destructive).
- Custom picker eyedropper now uses icon button.
- macOS native color input styled to match swatch sizing.

## Previous Changes (v0.5.5.39)

- macOS: native system color picker; Windows/Linux: custom macOS-style picker.
- Added EyeDropper support in custom picker where browser supports it.
- Swatch order updated to match macOS layout.

## Previous Changes (v0.5.5.38)

- Custom macOS-style color picker (swatches + modal) replacing native pickers.
- README: updated to current version and noted custom color picker.

## Previous Changes (v0.5.5.37)

- README: rewritten install section with Windows/Mac/Linux instructions.
- Canvas: clicking empty space no longer deselects the current layer.
- Port label bulk apply now restarts numbering from 1 for each selected group.

## Previous Changes (v0.5.5.36)

- README updated to document all current features and usage.

## Previous Changes (v0.5.5.35)

- Layer name editing: double-click now enters edit; single click stays selection.

## Previous Changes (v0.5.5.34)

- Layer list: name field no longer focuses on single-click; double-click to rename.
- Selected layers now show per-layer bounding boxes (Photoshop-style).

## Previous Changes (v0.5.5.33)

- Layer list: single-click selects without entering edit; double-click to rename.
- Canvas drag-select now shows a selection box and darkens intersected layers.
- Added visual distinction for primary selected layer in the list.

## Previous Changes (v0.5.5.32)

- Photoshop-style multi-select: Shift+click range + Cmd/Ctrl toggle in layer list.
- Canvas drag-select to multi-select layers; Cmd/Ctrl toggle on canvas click.
- Sidebar edits now apply to all selected layers, with mixed-value display.

## Previous Changes (v0.5.5.31)

- Data Flow: port label list now updates immediately when processor/bit depth/frame rate/mapping/pattern change.

## Previous Changes (v0.5.5.30)

- Custom Data Flow: when no custom paths exist, port count now falls back to capacity-based ports.

## Previous Changes (v0.5.5.29)

- Data Flow tab now performs a deferred port list refresh to fix initial list underpopulation.
- Port label editor debug now logs rendered row count.

## Previous Changes (v0.5.5.28)

- Added debug logging for port capacity + port label list to diagnose startup port list issue.

## Previous Changes (v0.5.5.27)

- Port label list now recalculates ports on Data Flow entry to avoid showing only Port 1.

## Previous Changes (v0.5.5.26)

- Data Flow tab now refreshes port capacity + port label list on entry.

## Previous Changes (v0.5.5.25)

- Port Labels panel: added Select All and Deselect All for bulk renaming.

## Previous Changes (v0.5.5.24)

- README updated with current features, shortcuts, processors, and custom mode notes.

## Previous Changes (v0.5.5.23)

- Custom mode now clears capacity error overlay on entry.
- Custom path edits persist to localStorage after add/clear/pattern actions.
- Custom selection highlight is darker for clearer visibility.
- Custom pattern debug logging includes first/last panel and grid size.

## How This Project Is Being Built

This application is developed collaboratively between a human developer (Matt) and **two AI coding assistants working in tandem:**

- **AI Assistant** — Primary development partner since project inception. All architecture decisions, core rendering, UI layout, export pipeline, and feature implementation to date have been done through AI-assisted conversations.
- **Codex (OpenAI)** — Joining development as of v0.5.5.2 for expanded feature work, refactoring, and parallel development tasks.

### Workflow Rules

1. **Either AI may receive tasks at any time.** Matt works back and forth between AI assistants depending on context and availability.
2. **This document is the single source of truth** for project state. When either AI makes significant changes, this doc should be updated.
3. **VERSION.txt tracks granular changes.** Check it for detailed per-version changelogs.
4. **TODO.txt tracks the roadmap.** Check it before starting new features to avoid conflicts.
5. **Don't assume the other AI's work is wrong.** If something looks unusual, it was probably an intentional design decision. Ask Matt before refactoring existing patterns.
6. **Version numbering:** Update in TWO places in `index.html` — the `<title>` tag and the `<h1>` header span.
7. **Client-side properties** are a deliberate pattern, not a bug. Some layer properties live only in localStorage (see details below).
8. **Archive zips are mandatory for every version.** When the version changes, create `Archive/led_raster_designer_vX.Y.Z.zip` in the parent folder.

---

## Project Overview

A professional web-based tool for designing LED video wall pixel maps for live events, concerts, and installations. Users lay out LED cabinet grids within a raster canvas, configure data flow paths, and export production-ready documentation (PNG, PDF, PSD).

**Target market:** Event production professionals, LED technicians, video engineers
**Competition:** Pixel Perfect Pro and similar LED mapping software
**Key differentiator:** Grid-based automatic panel generation vs. manual drawing. Multi-processor support with accurate manufacturer capacity data.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3 / Flask / Flask-SocketIO |
| Frontend | Vanilla JavaScript (no framework) |
| Rendering | HTML5 Canvas (2D context) |
| Real-time | WebSocket via Socket.IO |
| PSD export | `pytoshop` library |
| PDF export | `reportlab` library |
| Image processing | `Pillow` / `numpy` |

### Quick Start

```bash
pip3 install flask flask-socketio pillow numpy pytoshop reportlab
cd led_raster_designer
python3 app.py
# Local:   http://localhost:8050
# Network: http://<your-ip>:8050  (binds 0.0.0.0)
```

---

## Project Structure

```
led_raster_designer/
├── app.py                      # Flask backend — API routes, project state, export endpoints
├── requirements.txt            # Python dependencies
├── start.sh                    # Shell startup script
├── templates/
│   └── index.html              # Single-page app — ALL HTML/UI lives here (~700 lines)
├── static/
│   ├── css/style.css           # All styling
│   └── js/
│       ├── app.js              # LEDRasterApp class — UI logic, state, port capacity (~3000 lines)
│       └── canvas.js           # CanvasRenderer class — all drawing, zoom/pan (~1870 lines)
├── CODEX_HANDOFF.md            # THIS FILE — primary reference for AI developers
├── DEVELOPER_HANDOFF.md        # Earlier handoff doc (human-focused)
├── TODO.txt                    # Feature roadmap with priorities
├── VERSION.txt                 # Detailed changelog (every version since v0.3.9.4)
└── TRANSFORM_FEATURE_DESIGN.md # Design doc for future transform/resize feature
```

---

## Architecture

### Data Model

```
Project
├── name: string
├── raster_width: int (e.g. 1920)
├── raster_height: int (e.g. 1080)
└── layers: Layer[]
    ├── id: int (auto-increment)
    ├── name: string (e.g. "Screen1")
    ├── columns/rows: int (grid dimensions)
    ├── cabinet_width/cabinet_height: int (pixels per panel)
    ├── offset_x/offset_y: int (position in raster)
    ├── color1/color2: {r,g,b} (checkerboard colors)
    ├── visible: bool
    ├── show_panel_borders, show_circle_with_x, etc.
    └── panels: Panel[]
        ├── id/number: int
        ├── row/col: int
        ├── x/y: int (absolute pixel position = offset + col*width)
        ├── width/height: int (same as cabinet_width/height)
        ├── is_color1: bool (checkerboard alternation)
        └── hidden: bool (deleted/invisible panel)
```

### State Management (IMPORTANT)

There are **two types** of layer properties:

1. **Server-side** (stored in `current_project` dict in app.py, synced via WebSocket):
   - Grid dimensions, positions, panel states, colors, visibility, borders, labels, offsets
   - Persisted when project is saved/loaded

2. **Client-side only** (stored in `localStorage`, keyed by layer ID):
   - `processorType`, `portMappingMode`, `bitDepth`, `frameRate`
   - `flowPattern`, `arrowColor`, `dataFlowColor`, `primaryColor`, `backupColor`
   - `randomDataColors`, `dataFlowLabelSize`, `arrowLineWidth`
   - Tab-specific screen name sizes and positions
   - See `saveClientSideProperties()` and the load block in `handleProjectData()` in app.js

This split is intentional — these are display/calculation settings that don't need server persistence for now. Eventually they should move server-side.

### Rendering Pipeline

```
render() in canvas.js:
  1. Clear canvas
  2. Apply zoom/pan transform
  3. Draw raster boundary (red dashed line, zoom-independent thickness)
  4. For each visible layer:
     a. Render panels via renderPanel() → dispatches to view mode renderer
     b. Render mode-specific overlays (circle-with-X, pixel grid, data flow arrows)
     c. Render capacity error overlay if applicable
  5. Render labels in second pass (for proper occlusion by higher layers)
  6. Render selection highlight
```

---

## Current Features (v0.5.5.2)

### Core
- Grid-based LED panel layout with configurable cabinet sizes
- Multiple independent screen layers
- Custom raster dimensions
- Export rendering snaps draw coordinates to whole pixels (export mode only) for crisp pixel-to-pixel output
- Drag to move layers with magnetic snapping (to raster edges and other layers)
- Spacebar + drag panning, mouse wheel zoom (1% to 50,000%)
- Pixel grid overlay at 1000%+ zoom
- Undo/redo (Ctrl+Z / Ctrl+Shift+Z)
- Copy/paste layers (Ctrl+C / Ctrl+V)
- Delete key removes selected layer
- Duplicate layer (copies all settings including hidden panels)
- Layer visibility toggle
- Fit-to-view and 1:1 zoom buttons

### View Modes (4 tabs)
1. **Pixel Map** — Checkerboard pattern, optional circle-with-X test pattern, corner offset labels (TL/TR/BL/BR showing pixel coordinates)
2. **Cabinet ID** — Panel numbering with 3 schemes (A1/B2, 1-1/2-3, sequential 1/2/3), configurable position (center/corner) and color
3. **Data Flow** — Serpentine data path visualization with 8 flow patterns (4 corners × horizontal/vertical), port capacity splitting, editable P/R port labels (use # for port number), custom path mode (click/arrow keys or apply patterns to selected panels), configurable colors and line widths
4. **Power** — Placeholder (not yet implemented)

### Port Capacity System (v0.5.5.0+)
Multi-processor support with manufacturer lookup tables:

| Processor | Port Speed | Bit Depths | Rectangle Constraint |
|---|---|---|---|
| NovaStar Armor (MSD/MRV) | 1G | 8/10/12 (max 120 Hz) | YES — must fill complete rows/columns |
| NovaStar COEX A10s/A8s | 1G | 8/10/12 | No |
| NovaStar COEX CX40 | 5G | 8/10/12 | No |
| Brompton Tessera | 1G | 8/10/12 | No |
| Brompton Tessera (ULL) | 1G | 8/10/12 | No (half capacity) |
| Megapixel HELIOS | 1G | 10/12 only | No |
| Megapixel HELIOS | 2.5G | 10/12 only | No |

All capacity values are from official manufacturer documentation. Lookup tables in `portCapacityTables` in app.js. Frame rates that fall between table entries are linearly interpolated.

### Port Mapping Modes (v0.5.5.1+)
- **Organized** — Ports fill complete rows (horizontal flow) or columns (vertical flow). No mid-row/column splits.
- **Max Capacity** — Ports fill to maximum pixel count, can split anywhere in the flow.
- NovaStar 1G is always locked to organized/rectangle mode (buttons disabled).

### Hidden Panel Rules
- **NovaStar 1G:** Hidden panels STILL count toward port capacity (receiver card sees full rectangle)
- **All other processors:** Hidden panels are skipped (don't count toward capacity)

### Panel Operations
- Click a panel to hide/delete it (renders as semi-transparent ghost outline)
- Hidden state preserved when moving, duplicating, or changing grid size
- Duplicate layer copies hidden panel positions

### Labels & Display
- Screen name labels (per-tab size and position via Shift+drag)
- Dimension labels: pixels, meters, feet (with fractional inches option)
- Info label: columns×rows, aspect ratio, panel physical size, weight
- Corner offset indicators showing pixel coordinates

### Export
- **PNG** — Single image or ZIP with all 4 view modes
- **PDF** — Multi-page document with all views via reportlab
- **PSD** — Layered Photoshop file, each screen as a separate layer at correct position/size (no background layer)
- All exports use an offscreen canvas at exact raster dimensions for pixel accuracy

---

## Key Functions Reference

### app.js — LEDRasterApp

| Function | Purpose |
|---|---|
| `calculatePortCapacity(bitDepth, frameRate, processorType)` | Lookup table capacity with interpolation |
| `calculatePortAssignments(layer)` | Assigns panels to ports based on processor/mode |
| `updatePortCapacityDisplay()` | Updates sidebar stats + button states |
| `usesRectangleConstraint(processorType)` | Returns true only for `novastar-armor` |
| `updateBitDepthOptions()` | Filters bit depth dropdown per processor |
| `saveClientSideProperties()` | Saves client-only props to localStorage |
| `duplicateLayer(layer)` | Full deep copy including hidden panels |
| `saveState(action)` / `undo()` / `redo()` | State stack management |

### canvas.js — CanvasRenderer

| Function | Purpose |
|---|---|
| `render()` | Main render loop — clears, transforms, draws everything |
| `renderPanel(panel, layer)` | Dispatches to view-mode-specific renderer |
| `renderPixelMap(panel, layer)` | Checkerboard fill + borders (hidden = ghost outline) |
| `renderCabinetID(panel, layer)` | Same fill + cabinet numbers rendered separately |
| `renderDataFlow(panel, layer)` | Same fill (arrows rendered in separate pass) |
| `renderDataFlowArrows(layer)` | Serpentine paths, port splitting, P1/R1 labels |
| `renderPixelGrid(layer)` | 1px grid overlay at high zoom |
| `renderLayerOffsets(layer)` | Corner coordinate labels (clipped to raster) |
| `renderCapacityErrorOverlay(layer)` | Red overlay when port can't fit complete row/col |
| `getPanelFlowOrder(layer, pattern)` | Returns panels in serpentine order for a flow pattern |

---

## Known Issues & Gotchas

1. **PSD export at native resolution** — The export is pixel-accurate at 1:1. Zooming in Photoshop will look blocky because that's actual LED pixels. This is correct behavior.

2. **Client-side property split** — If localStorage is cleared, Data Flow settings (processor, flow pattern, colors) reset to defaults. Layer geometry survives because it's server-side.

3. **Raster boundary clipping** — Everything outside the raster is clipped. Offsets, labels, and panel fills all respect this boundary. The red dashed boundary line scales inversely with zoom to stay visible.

4. **Data flow arrows still use organized layout internally** — The arrow rendering in `renderDataFlowArrows` splits by rows/columns. Max Capacity mode works for port assignment but the visual arrows use a simplified approach (slicing the ordered panel array by count). Complex non-rectangular port boundaries may not render perfectly in Max Capacity mode.

5. **Version in two places** — Always update both `<title>` and `<h1>` in index.html.

---

## Roadmap Summary

See `TODO.txt` for the full prioritized list. Key upcoming areas:

**High Priority:**
- Transform Mode (resize/rotate layers) — design doc in TRANSFORM_FEATURE_DESIGN.md
- Power tab implementation
- Top menu bar (File/Edit/View/Settings/Help)
- Right-click context menus

**Medium Priority:**
- Layer reordering (drag & drop)
- Multi-layer selection and alignment tools
- Editable Data Flow labels (custom P1/R1 text)
- Export improvements (CSV, multi-PNG batch)
- Settings panel (auto-save, defaults)

**Low Priority / Future:**
- Native launcher app (Electron, like Bitfocus Companion)
- Layer grouping
- Templates system
- Custom panel shapes
- Performance optimizations (viewport culling, canvas caching)

---

## Development Guidelines

1. **Test in the Data Flow tab** — This is the most complex view with capacity calculations, arrow rendering, and port splitting. Changes to layer/panel logic should be verified here.

2. **Hidden panels are tricky** — Different processors treat them differently. NovaStar 1G counts them, everything else skips them. Always check both paths.

3. **Export mode** — `this.exportMode` flag in canvas.js suppresses the raster boundary, grid, and selection highlight for clean output. Make sure new visual elements check this flag.

4. **Zoom-independent elements** — Text, labels, and UI overlays should scale with `1/this.zoom` so they maintain constant screen size. World-space elements (panels, borders) scale naturally with zoom.

5. **Flask runs on 0.0.0.0:8050** — Accessible from any network interface. The console shows both localhost and LAN URLs on startup.

6. **No build step** — Everything is vanilla JS/CSS/HTML served by Flask. Just edit and refresh. Python changes auto-reload in debug mode.

---

*This document should be updated whenever significant architectural changes are made. All AI assistants should read this file at the start of any session involving this project.*
