# LED Raster Designer v1.4.0

A professional LED video wall layout designer for live events, concerts, and installations.

Design LED cabinet layouts, plan the real-world stage layout, configure data flow paths, plan power distribution, and export production documentation.

---

## Getting Started

### Mac
1. **[Download the latest Mac release](../../releases/latest)** (a `.dmg` file)
2. Open the `.dmg` and **drag LED Raster Designer onto the Applications folder** shown in the window
3. Open **LED Raster Designer** from your Applications folder (or Launchpad)
4. When macOS asks, **allow it to access devices on your Local Network**, this is required so other devices (and your own browser) can reach the app
5. Your browser opens automatically, start designing
6. Look for the 💡 in your menu bar to reopen the browser or quit

> **Why Applications matters:** macOS only shows the Local Network permission prompt for apps installed in `/Applications`. If you run it from the Downloads folder or directly from the disk image, the prompt never appears and the app can't be reached over your network. Always install it to Applications first.
>
> If you ever need them, logs live in **`~/Library/Logs/LED Raster Designer/`** (also reachable via the app's **Show Logs → Open Folder** button).

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

LED Raster Designer takes a show from the wall to the rack to the paper: lay out the cabinets, wire every port and circuit to the hardware that feeds it, check the maths, and print a drawing set a shop can build from.

### Five views

| Tab | What it does |
|-----|-------------|
| **Pixel Map** | The layout your processor expects. Checkerboard and circle test patterns, cabinet borders, screen labels, blanks and half-tiles for non-rectangular walls. |
| **Cabinet ID** | Cabinet numbering in the style you choose (A1, 1,1, 01 and more). An id never leaves its cabinet. |
| **Show Look** | Rearrange the screens to match the stage. Pixel Map keeps the processor layout; Show Look drives the Data and Power views, so wiring and power maps read the way the show is built. |
| **Data** | Ports snaked across the wall in any of eight flow patterns or drawn by hand, wired to the processor, card and breakout box that carry them. |
| **Power** | Circuits across the wall the same way, wired to the distro and the multi that feed them, with the amps on every leg. |

### Screens and canvases

- A project holds any number of **canvases**, each with its own raster, workspace position and screens. Drag a canvas by its dashed outline; magnetic snap aligns it with its neighbours.
- Add screens from a catalog of **2,500 cabinets from 180 manufacturers**, or from your own presets. Heart a cabinet to keep it in the left column. The catalog refreshes from GitHub without a reinstall, and the app opens a pre-filled issue when a figure needs correcting.
- **Groups**: select several screens and Group Screens. A wall built from more than one cabinet size behaves as one screen: one name, one set of totals, cabinet numbers that run straight through, and ports and circuits that cross the seam.
- **Beaches**: a position the show keeps (SR, SL, upstage, whatever you call them). Screens, distros and breakout boxes each pick theirs; the pull sheet and the binder follow that order.
- Image and logo layers with scale, opacity and a drop shadow; text labels with per-tab visibility and fonts.
- Multi-select across canvases (Shift-click a range, Cmd/Ctrl-click to toggle, drag on empty canvas) and edit the selection at once.

### The hardware tray

Processors, cards, breakout boxes and ports on the Data tab; distros, multis and circuits on the Power tab. All of it lives in a tray along the bottom of the window.

- **Wire by dragging.** Drag a port, a card, a box or a whole processor onto a screen and it lands in order from the first unassigned port; drag a circuit chip, a multi or a distro the same way. Nothing lands by itself: a port is on a socket because you put it there, and Clear always takes it off.
- **The attachment flag** on the tray header counts what is still unattached, red until everything is wired, and flies you to the screen when you click it.
- An attached port prints the socket it sits on, so the drawing reads 6, 7, 8, 9 exactly as the tray does.
- **Processors** from a catalog of 61 devices across NovaStar, Brompton and Megapixel, each figure from the device's own specification and nothing guessed. A screen only lands on gear its platform can drive.
- **Redundancy is one bar** behind the processor's gear: Off, Whole unit, Per card, Per port. Brompton pairs fixed the way the unit does; NovaStar's second sending card is the Backed up pick. A gold pill on every tray header reads the shape in force.
- **Every cable on paper.** The ≡ on a multi or a card flips its chips into a cable sheet with a length and connector per circuit or port. Hold Alt and sweep port chips to snake them under one home run; a snaked port carries its own extension. Show Cable Tags prints them on the wall and in the export.

### Power that adds up

- **Distros** with a rating, a voltage and a phase. Load rolls up from circuit to multi to distro; three-phase legs are phasor sums, and a folded distro still shows its load bars. Balance, per distro, spreads the multis across the legs without changing the order the wall reads in.
- Every number on a distro is a plug you drag: **Multi 208, Multi 120, L21-30**. While you drag, the circuits the drop will feed light up with the amps they add.
- A 110 V screen takes Edison only, and each of its circuits rides one leg of the same three-phase distro. The L21-30 is three 208 V circuits off a 30 A per leg feed, checked by the same maths.
- **Shared circuits** through a 2fer or 3fer: hold Alt, sweep the runs, right-click. A share never passes the circuit's amps in automatic mode; in custom mode, where you own the runs, it is allowed and flagged OVER.
- Custom drawing on either tab stops at capacity, and a flow pattern applied to a selected block deals it out at capacity.

### Papers

Everything under File > Export or the Export dialog saves straight to a file: no print dialogs, no windows to close.

| Export | What you get |
|--------|-------------|
| **PNG / PDF / PSD** | Any of the five views, per canvas. One PNG per view, one PDF with a page per view, one PSD with a layer per screen, or with each screen's panels, borders, cabinet ids, data, power and name as separate layers in a group per screen. |
| **SVG** | Any view as vector artwork: labels as real text, cabinets and runs as shapes, grouped per screen and per element. Opens in Illustrator with everything editable, and in Photoshop as a smart object. |
| **Resolume XML** | Advanced Output screens, one per canvas, sized to its raster. |
| **Pull Sheet** | A filled copy of the shop's pull-sheet workbook: one block per beach, multis with their home runs, True1 by length, 2fers and 3fers, breakouts, snakes, extensions, barrels and jumpers. File > Pull Sheet edits the list in the app first. |
| **Binder** | One PDF as numbered sheets: overview, a Power and a Data sheet per screen with the wall, its circuits, ports, cables and facts, pull sheets, hardware. Tabloid by default, or Letter, ARCH C, ARCH D, A4, A3. Every sheet carries a border and a title block with your logo and a revision log. Tick Wiring and each map gets a wiring sheet behind it, every run drawn port to socket. Real text in the PDF, so it is sharp and searchable. Right-click a screen for Export this screen. |

### Guides

Help > Quick Start Guide, What's New in 1.0 and Advanced Guide do not describe the app; they run it. Every step performs one real action in front of you on a scratch Demo Show, at a person's pace, and a line under the step says what just happened. Enter is Next, a Go to box jumps to any step, and your own project comes back the moment you leave.

### Preferences

Seven tabs (Wall, Look, Data, Power, Distros and multis, Binder, Pull sheet and cables) with a default for nearly everything you create, an interface accent color, and a Reset Defaults button. A default applies only to what you make next; a show's own value always wins.

### Keyboard shortcuts

Help > Keyboard Shortcuts lists every gesture the app has, grouped by where it works, with Cmd or Ctrl for your platform. The ones you will use first:

| Shortcut | What it does |
|----------|-------------|
| **Cmd/Ctrl + Z**, **Cmd/Ctrl + Shift + Z** | Undo, redo. Every action is covered, including tray and distro edits. |
| **Cmd/Ctrl + O**, **Cmd/Ctrl + S** | Open, save a project |
| **Option/Alt + S**, **Cmd/Ctrl + Option/Alt + S** | Export PNG, export PSD |
| **Cmd/Ctrl + C / V**, **Cmd/Ctrl + J** | Copy, paste, duplicate a layer |
| **Cmd/Ctrl + Shift + 1**, **Cmd/Ctrl + Shift + 2** | Fit to view, zoom to selection at 1:1 |
| **Space + drag**, **scroll wheel** | Pan, zoom |
| **Shift + drag a screen** | Move it (in Show Look, its stage position) |
| **Alt + click a cabinet**, **Alt + Shift + click** | Blank it, make it a half-tile |
| **Hold Alt on a run** | Light it; Alt-click takes that port or circuit over for hand redrawing |
| **Tab / Shift + Tab** | Next, previous port or circuit in custom mode |

### Projects

- Save and open `.json` projects; Recent Files in the File menu. A project from any earlier version opens and is brought up to date on load.
- Cancelling a save or export saves nothing, on every platform.
- The app checks for a new release and offers it from Help.

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

Source code is in the `src/` folder.

### Where things live

Front end (`src/static/js/`):

| File | Owns |
|---|---|
| `app-core.js` | the App class: state, socket, initial UI setup |
| `app-wiring.js` | every DOM listener, one `_wire*` method per area |
| `app-client-props.js`, `app-preferences.js` | per-layer client settings in localStorage; preference defaults, storage, the tabbed modal |
| `app-screen-info.js`, `app-capacity.js` | the Screen Info panel, totals, layer updates; port capacity rules (bit depth, frame rate, low latency) |
| `app-selection.js`, `app-pixel-select.js`, `app-colors.js` | the multi-select set and bulk edits; cabinet selection and Pixel Map bulk edits; gradient and palette editors |
| `app-layers-panel.js`, `app-context-menu.js` | the Screens panel rows; the canvas right-click menu |
| `app-screen-groups.js`, `app-beaches.js`, `app-presets.js` | screen groups and group-wide actions; beach list and picker; screen presets and the cabinet catalog picker |
| `app-canvas-ui.js`, `app-project-io.js` | canvas tabs (add, rename, delete, reorder); save and open project files, reset, normalize |
| `app-history.js`, `app-clipboard.js` | undo/redo and snapshots; duplicate, copy and paste layers |
| `app-export-io.js`, `app-export-svg.js`, `app-menubar.js`, `app-logs-recent.js` | export dialog, preview, writing files; the SVG export's drawing recorder and writer; menu bar, shortcuts, About; log viewer and recent files |
| `app-processors.js`, `app-port-routing.js`, `app-port-assignment.js` | the processor tree and gear popovers; walking cabinets into per-port runs; port-numbering issues and their fixes |
| `app-custom-runs.js`, `app-run-overrides.js`, `app-cross-layer-paths.js` | hand-drawn runs (capacity, stepping, pattern fill); a port or circuit taken over by hand; paths across group members |
| `app-power.js`, `app-distros.js`, `app-phase-balance.js`, `app-naming.js` | circuits, soca splits, outputs, breakouts, cables; the distro model; three-phase balancing; port, circuit and multi labels |
| `app-dock.js`, `app-dock-cable-sheets.js`, `app-dock-sweep.js`, `app-dock-drag.js`, `app-dock-menus.js` | the hardware tray: rendering, cable sheets, snake brackets and the Alt sweep, the drag engine, right-click menus |
| `app-binder.js`, `app-binder-wiring.js` | the binder drawing set, sheets and title blocks; the Power Wiring and Data Wiring sheets |
| `app-pull-list.js`, `app-pull-sheet-editor.js`, `app-jumpers.js` | the cable pull list every paper reads; per-row edits over it; the jumper between two cabinets of a run (vertical, horizontal, long) and each screen's jumper lengths |
| `app-fiber.js` | fiber cables on breakout boxes: TAC, MTP and opticalCON, the strands each link takes, strand names and backup binding |
| `canvas.js` | the renderer class (classic script): viewport, view modes, base drawing |
| `canvas-input.js`, `canvas-images.js`, `canvas-data.js`, `canvas-power.js`, `canvas-labels.js`, `canvas-selection.js`, `canvas-math.js` | renderer mixins: gestures and hit-testing; image and text layers; the Data view; the Power view; labels and cabinet IDs; selection overlays; port load math |
| `helpers.js`, `main.js` | shared utilities and client logging; the entry point that imports every module |
| `color_picker.js`, `theme.js`, `quickstart.js`, `updater.js`, `whatsnew.js`, `whatsnew_content.js` | the color popover; accent color; the guides; update banner; the What's New splash and its text |

Back end (`src/`):

| File | Owns |
|---|---|
| `app.py` | Flask app and sockets, logging, the project/layer/group/beach model and live state, `/` and `/static` |
| `routes_export.py`, `resolume_geometry.py` | every `/api/export/*` route and its render helpers; contours, islands and the Resolume XML (pure functions) |
| `routes_project.py`, `routes_canvas.py`, `routes_layers.py` | get, new, save, restore project and beaches; canvases; layers and per-panel state |
| `routes_processors.py`, `routes_port_assignment.py`, `routes_panel_catalog.py`, `routes_presets.py` | the processor tree; which socket each screen port uses; the cabinet catalog; preset files |
| `routes_preferences.py`, `routes_logs.py`, `routes_system.py`, `routes_version.py`, `routes_dialog.py`, `routes_pull_sheet.py` | preferences; logs; system fonts; version and update check; native save dialogs (loopback only); the pull sheet workbook |
| `processor_catalog.py`, `port_assignment.py`, `pull_sheet.py` | the processor catalog and its rules; pins, clashes, overflow and offers; writing the pull list into the workbook |
| `scr_decoder.py`, `scr_encoder.py`, `scr_project.py` | sending-card configuration files |
| `launcher_mac.py`, `launcher_pc.py`, `launcher_settings.py`, `launcher_window.py`, `updater.py` | the launchers; the release check |

Two rules keep this layout honest:

- **The mixin idiom.** A feature module is a private class whose own methods are copied onto `LEDRasterApp.prototype`; `app-core.js` holds the class itself. A new `app-*.js` file must be imported in `main.js` or it never loads (`app-binder.js` must precede `app-binder-wiring.js`). `canvas.js` is a classic script (`window.CanvasRenderer`); each `canvas-*.js` mixes onto `CanvasRenderer.prototype` with `Object.assign` and is a `<script>` tag in `index.html` after `canvas.js` and before `main.js`. Python route files are Flask blueprints registered at the bottom of `app.py`; they read live state as `app.current_project` via `import app`, never through `from app import`.
- **The guides' Go to restores shipped snapshots.** `src/static/data/tour_snapshots.json` holds every step's entry state for the three guides, generated by `python3 scripts/build_tour_snapshots.py`. Re-run it after changing a guide's steps or bumping the version; `tests/test_tour_snapshots.py` fails until you do.
- **One home per method.** `tests/test_js_modules.py` fails when a method name is defined in more than one module (prototype mixing is silent: the later file wins), when an `app-*.js` is not imported by `main.js`, or when a script tag in `index.html` points at a missing file. Move a method; don't copy it.

---

## Reporting Bugs and Requesting Features

Open an issue at [github.com/kman1898/LED-Raster-Designer/issues](../../issues). For feature suggestions please include the use case, and for bug reports please attach the relevant log (Help → Show Logs… → Copy).

---

## Versioning & Releases

Versions follow `vMAJOR.MINOR.PATCH` (e.g. `v1.0.0`). PATCH is a fix or small
change; MINOR is new features; MAJOR is a change to what the app is. The version string is kept in sync across `README.md`, `src/VERSION.txt`,
`src/templates/index.html`, and `src/led_raster_designer.spec`.

Every **public** release is git-tagged `vX.Y.Z` and gets release notes drawn from
the matching `src/VERSION.txt` entry, never the auto-generated PR list alone, so
the GitHub Releases page reads consistently. Internal test builds are produced via
the workflow's manual dispatch and are **not** tagged, so the public release
history has no gaps.

---

## Contact

Questions and feedback are welcome as issues at [github.com/kman1898/LED-Raster-Designer/issues](../../issues).
