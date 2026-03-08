# LED Raster Designer v0.6.2.0

A professional LED video wall layout designer for live events, concerts, and installations. Design LED cabinet layouts, configure data flow paths, plan power distribution, and export production documentation.

## Download

Download the latest release — no coding required:

**[Download for Mac](../../releases/latest)** — Unzip, double-click **LED Raster Designer.app**, done.

A 💡 icon appears in your menu bar to reopen the browser or quit the app.

---

## Build from Source

If you prefer to build it yourself:

### Prerequisites
- **Python 3.10+** — Download from [python.org](https://www.python.org/downloads/)
- **Windows users:** During Python install, CHECK the box **"Add Python to PATH"**

### Mac
1. Download or clone this repo
2. Open **Terminal** and run:
   ```
   cd "/path/to/LED Raster Designer"
   make mac
   ```
3. When it finishes, double-click **LED Raster Designer.app** in the folder
4. Your browser opens automatically — start designing
5. A 💡 icon appears in your menu bar — click it to reopen the browser or quit

### Windows
1. Download or clone this repo
2. Open **Command Prompt** and run:
   ```
   cd "C:\path\to\LED Raster Designer"
   make windows
   ```
   If you don't have `make`, run these instead:
   ```
   cd src
   python -m pip install -r requirements.txt
   python -m pip install pyinstaller pystray
   python -m PyInstaller led_raster_designer.spec --noconfirm
   ```
3. When it finishes, double-click **LED Raster Designer.exe** in the folder
4. Your browser opens automatically — start designing
5. A lightbulb icon appears in your system tray — right-click it to reopen the browser or quit

### Network Access
Other devices on your network can connect to the app at `http://[your-ip]:8050` (shown on startup).

---

## Features

### Four View Modes

| Tab | Purpose |
|-----|---------|
| **Pixel Map** | Layout view with checkerboard pattern, panel borders, circle test pattern, and screen labels |
| **Cabinet ID** | Cabinet numbering with customizable styles (A1, 1,1, 01, etc.) |
| **Data** | Data routing visualization with serpentine patterns and port assignments |
| **Power** | Power distribution planning with circuit routing and color-coded visualization |

### Screen Management
- Add, duplicate, delete, and reorder screen layers
- Add image/logo layers with scale control
- Multi-select screens (Shift+click range, Cmd/Ctrl+click toggle, drag-select on canvas)
- Layer locking, visibility toggle, and drag reorder
- Double-click layer name to rename

### Canvas Controls

| Control | Action |
|---------|--------|
| **Spacebar + Drag** | Pan the canvas |
| **Scroll Wheel** | Zoom in/out |
| **Shift + Drag** | Move selected screen |
| **Alt + Click** | Toggle panel hidden/visible |
| **Fit Button** | Fit all content to view |
| **1:1 Button** | Reset to 100% zoom |

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Cmd/Ctrl + Z** | Undo |
| **Cmd/Ctrl + Shift + Z** | Redo |
| **Cmd/Ctrl + C** | Copy layer |
| **Cmd/Ctrl + V** | Paste layer |
| **Cmd/Ctrl + J** | Duplicate layer |
| **Delete / Backspace** | Delete layer |

### Data Tab
- 8 serpentine flow patterns (all corner starts × horizontal/vertical)
- Port capacity calculator supporting NovaStar (Legacy, Armor, COEX), Brompton Tessera, and Megapixel HELIOS
- Configurable bit depth (8/10/12-bit) and frame rate
- Custom data path mode with click-to-draw and selection-based pattern application
- Editable port labels with templates and per-port overrides
- Over-capacity error detection with visual overlay

### Power Tab
- Circuit-based serpentine routing with configurable voltage, amperage, and watts
- Color-coded circuit visualization with customizable per-circuit colors
- Supports organized and max-capacity mapping modes
- 1-phase and 3-phase power calculations
- Circuit start labels with directional pointers

### Export
- Multi-view PNG export (Pixel Map, Cabinet ID, Data, Power)
- PSD export with layer support
- PDF export
- Configurable export suffixes

### Preferences
- Default raster size, grid colors, flow patterns, and line widths
- Default processor, bit depth, frame rate, voltage, and amperage
- Panel size (mm) and weight unit (kg/lb)
- Settings persist across sessions

---

## Building from Source

If you want to build the app yourself instead of using the pre-built releases, see [BUILD.md](BUILD.md).

Requires Python 3.10+. Source code is in the `src/` folder.

---

## Contact

For questions or feedback during beta testing, please contact the development team.
