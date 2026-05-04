# LED Raster Designer v0.8.0

A professional LED video wall layout designer for live events, concerts, and installations.

Design LED cabinet layouts, plan the real-world stage layout, configure data flow paths, plan power distribution, and export production documentation.

---

## Getting Started

### Mac
1. **[Download the latest Mac release](../../releases/latest)**
2. Unzip the file
3. Double-click **LED Raster Designer.app**
4. Your browser opens automatically, start designing
5. Look for the 💡 in your menu bar to reopen the browser or quit

### Windows
1. **[Download the latest Windows release](../../releases/latest)**
2. Unzip the file
3. Double-click **LED Raster Designer.exe**
4. Your browser opens automatically, start designing
5. Look for the lightbulb in your system tray (bottom-right) to reopen the browser or quit

### Network Access
Other devices on your local network can use the app by going to `http://[your-ip]:8050` in their browser (the exact address is shown when the app starts).

---

## Features

### Multi-Canvas (new in v0.8)

A project can hold multiple independent **canvases**, each with its own raster size, workspace position, perspective, and layers. Think of one canvas per processor / per stage / per tour leg.

- Right-sidebar **Screens** panel groups layers by canvas. Each canvas has a color swatch, name, eye toggle (visibility), and a **+ Add** button to drop new layers in.
- Drag a canvas by its dashed outline to reposition it in the workspace. Magnetic snap aligns edges with neighboring canvases.
- Drag (Shift+Drag) a screen layer onto another canvas to **move** it there. Cmd/Alt+Shift+Drag duplicates instead. The layer snaps to (0,0) in the new canvas.
- Per-canvas raster: the toolbar **Raster: W x H** and the Show Look raster always reflect the active canvas. Each canvas can be sized independently.
- Per-canvas Front/Back perspective for Data and Power. Switching the active canvas updates the toggle.
- **Cross-canvas multi-select**: Shift+click layers in different canvases and bulk-edit them at once (panel size, voltage, processor type, etc.). The selection survives the active-canvas auto-switch.
- **Hidden canvases** are excluded from the Data/Power totals and from exports by default.
- **Per-canvas presets**: a new screen added to a canvas inherits hardware settings (voltage, amperage, panel size, processor type) from the most recent screen already in that canvas.

### Five View Modes

| Tab | What it does |
|-----|-------------|
| **Pixel Map** | Layout view that mirrors what your processor expects. Checkerboard test pattern, panel borders, circle test pattern, and screen labels. |
| **Cabinet ID** | Cabinet numbering with customizable styles (A1, 1,1, 01, etc.). Matches the Pixel Map layout. |
| **Show Look** | Rearrange screens to match the real-world stage layout. Pixel Map keeps the processor-required layout; Show Look's layout drives Data and Power so wiring/power maps match how the show is actually built. Per-screen "show position" separate from "processor position", and an independent raster size. |
| **Data** | Data routing visualization with serpentine flow patterns and port assignments. Renders at the Show Look layout. |
| **Power** | Power distribution planning with circuit routing and color-coded visualization. Renders at the Show Look layout. |

### Screen Management
- Add, duplicate, delete, and reorder screen layers
- Add image/logo layers with scale control
- Add text label layers (per-tab visibility, alignment, fonts, etc.)
- Multi-select screens (Shift+click range, Cmd/Ctrl+click toggle, drag-select on canvas)
- Layer locking, visibility toggle, and drag reorder
- Double-click a layer name to rename it
- Save layers as presets to reuse across projects

### Per-Panel Editing
Drag-select any group of panels in Pixel Map view, then bulk-toggle their state, or use modifier keys for fast single-panel edits.

| Action | What it does |
|--------|-------------|
| **Alt + Click** | Toggle a panel as **blank** (hidden, useful for non-rectangular walls). When a multi-selection is active, applies to the entire selection. |
| **Alt + Shift + Click** | Toggle a panel as **half-tile** (auto-detects half-width vs half-height based on which wall edge the panel sits on). Bulk version uses majority-vote across the selection so a row stays consistent. |
| **Drag-select** | Marquee-select panels to bulk-action via the sidebar buttons. Count badge shows how many are selected. |
| **Right-click** | Context menu in Pixel Map view with the same blank / half-tile / restore actions. |

Half-tiles count as **0.5 panel** for data/port math and **0.65 panel** for power/weight (the typical industry derate).

### Canvas Controls

| Control | What it does |
|---------|-------------|
| **Spacebar + Drag** | Pan the canvas |
| **Scroll Wheel** | Zoom in/out |
| **Shift + Drag a screen** | Move the screen (in Pixel Map = processor position; in Show Look = stage position) |
| **Drag-select on empty space** | Marquee-select layers (Pixel Map) or panels (when starting on a current-layer panel) |
| **Magnetic Snap toggle** | Snap dragged screens to other screens' edges and to raster bounds |
| **Fit / 1:1 buttons** | Fit raster to view, or reset to 100% zoom |
| **Sidebar collapse chevrons** | Tap the ‹ / › on the inner edge of either sidebar to hide/show it independently. State persists across reloads. |

### Keyboard Shortcuts

| Shortcut | What it does |
|----------|-------------|
| **Cmd/Ctrl + Z** | Undo |
| **Cmd/Ctrl + Shift + Z** | Redo |
| **Cmd/Ctrl + C / V** | Copy / Paste layer |
| **Cmd/Ctrl + J** | Duplicate layer |
| **Cmd/Ctrl + Shift + 1** | Fit raster to view |
| **Cmd/Ctrl + Shift + 2** | Zoom to selected screen at 1:1 |
| **Cmd/Ctrl + Shift + '** | Toggle magnetic snap |
| **Tab / Shift + Tab** | Next / previous port (in Data Flow custom mode) |
| **Delete / Backspace** | Delete layer |

### Data Tab
- 8 serpentine flow patterns (all corner starts × horizontal/vertical)
- **Custom data path mode**, click panels in order to draw your own port routing, or drag-select a region and apply a flow pattern just to that region
- Port capacity calculator supporting:
  - **NovaStar** (Legacy, Armor, COEX)
  - **Brompton Tessera**
  - **Megapixel HELIOS**
- Configurable bit depth (8 / 10 / 12-bit) and frame rate
- Editable port labels with templates and per-port overrides (auto-increments soca numbers like S1-1..S1-6, S2-1..S2-6 from any starting template)
- Over-capacity error detection with visual overlay
- Per-screen primary / backup port colors and label sizes
- Optional per-port info display directly on the panel
- **Front / Back view perspective**, independent toggle in the sidebar. Back view horizontally mirrors the canvas geometry (so wiring matches what you see standing behind the wall) while keeping every label readable, shows a "BACK VIEW" badge in the corner, and auto-appends `_back` to the export filename suffix.

### Power Tab
- Circuit-based serpentine routing with configurable voltage, amperage, and watts
- **Custom power path mode**, draw circuits manually for non-standard wiring
- Color-coded circuit visualization with customizable per-circuit colors
- Organized and max-capacity mapping modes
- 1-phase and 3-phase power calculations
- Circuit start labels with directional pointers
- Per-circuit label overrides
- **Front / Back view perspective**, same independent toggle as Data, with mirrored geometry and "BACK VIEW" badge.

### Project Management
- Save / open projects as `.json` files (preserves all layers, settings, and panel state)
- Recent Files menu in the File menu
- Auto-update check (notifies when a new release is available)
- Per-panel state (hidden, half-tile) survives column/row resizes (state is anchored to grid position, not sequential id)
- **v0.7 → v0.8 auto-migration** on load: opens any older project and converts it into the multi-canvas format with one canvas containing all the original layers. A one-time toast reminds you to save in the new format. v0.7 builds opening a v0.8 file get a clean "format newer than supported" error.

### Export
- Multi-view PNG export, pick which views (Pixel Map, Cabinet ID, Show Look, Data, Power) to render in one go
- **Multi-canvas aware** (v0.8): the Export dialog adds a Canvases section above Views. Each (canvas × view) is one PNG / one PSD / one PDF page. PDF page headers include canvas + view name. Resolume XML now emits one `<Screen>` per canvas, sized to that canvas's raster.
- PSD export with per-screen layers (per-canvas filtered, only that canvas's layers in each PSD)
- PDF export (multi-page across selected canvases × views)
- Resolume Arena Advanced Output XML export (one `<Screen>` per canvas, named after the canvas)
- NovaStar SCR export (sending-card mapping)
- Configurable export filename suffixes per view (saved as defaults)
- Project-name input flags illegal filename characters (\\ / : * ? " < > |) and auto-sanitizes them on export

### Verified Panel Catalog
- Built-in panel presets for many manufacturers (ROE, Leyard, Barco, INFiLED, ARTFOX, etc.)
- ⭐ marker on panels with verified specs (cross-checked against manufacturer datasheets)
- **Live catalog refresh**, `↻ Refresh` button in the Add Screen modal pulls the latest `panel_catalog.json` from GitHub without needing to reinstall the app. Boot-time silent check shows a "📦 Update available" pill when newer panels are out. Refreshed catalog persists per browser.
- **Favorites**, heart any panel in the catalog to pin it to the left column alongside your saved presets. Drag-reorder the left column to suit your typical workflow. Per-user, persists in localStorage.
- "Submit a correction" / "Add missing panel" link inside the app opens a pre-filled GitHub issue (with a confirmation that the user must click "Submit new issue" on GitHub for it to actually reach us, submissions used to silently drop)

### Preferences
- Default raster size, grid colors, flow patterns, and line widths
- Default processor, bit depth, frame rate, voltage, and amperage
- Default panel size (mm) and weight unit (kg / lb)
- Settings persist across sessions

---

## For Developers, Building from Source

If you want to build the app yourself instead of downloading the release:

### Prerequisites
- **Python 3.10+**, Download from [python.org](https://www.python.org/downloads/)
- **Windows users:** During Python install, CHECK the box **"Add Python to PATH"**

### Mac
1. Clone or download this repo
2. Open **Terminal** and run:
   ```
   cd "/path/to/LED Raster Designer"
   make mac
   ```
3. The app appears in the folder, double-click **LED Raster Designer.app**

### Windows
1. Clone or download this repo
2. Double-click **Build Windows.bat**
3. The app appears in the folder, double-click **LED Raster Designer App\LED Raster Designer.exe**

### Cleaning Build Files
- **Mac:** `make clean`
- **Windows:** `Build Windows.bat clean` (from Command Prompt)

Source code is in the `src/` folder. See [BUILD.md](BUILD.md) for more details.

---

## Reporting Bugs and Requesting Features

Open an issue at [github.com/kman1898/LED-Raster-Designer/issues](../../issues). For feature suggestions please include the use case, and for bug reports please attach the relevant log (Help → Show Logs… → Copy).

---

## Contact

For questions or feedback during beta testing, please contact the development team.
