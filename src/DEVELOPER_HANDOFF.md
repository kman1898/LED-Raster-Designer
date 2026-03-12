# LED Raster Designer - Developer Handoff Document

> **NOTE: "LED Raster Designer" is a PLACEHOLDER NAME** - Final product name TBD
> **Consistency note:** For current state, treat `README.md`, `VERSION.txt`, and `TODO.txt` as authoritative.

## Project Overview

LED Raster Designer is a professional web-based application for designing LED wall layouts for live events, concerts, and installations. Think of it as a specialized CAD tool for LED video walls - it lets you design pixel maps, assign data flow paths, and export production-ready documentation.

**Target Competition:** Pixel Perfect Pro and similar professional LED mapping software

## Tech Stack

- **Backend:** Python Flask + Flask-SocketIO
- **Frontend:** Vanilla JavaScript + HTML5 Canvas
- **Real-time:** WebSocket communication
- **Export Libraries:** 
  - `pytoshop` - PSD file generation
  - `reportlab` - PDF generation
  - `Pillow` - Image processing

## Quick Start

```bash
# Install dependencies
pip3 install flask flask-socketio pillow numpy pytoshop reportlab

# Run the app
cd led_raster_designer
python3 app.py

# Open browser to:
# Local:   http://localhost:8050
# Network: http://<your-ip>:8050
```

## Project Structure

```
led_raster_designer/
├── app.py                 # Flask backend - API routes, WebSocket handlers
├── start.sh               # Startup script
├── requirements.txt       # Python dependencies
├── templates/
│   └── index.html         # Main HTML template (single-page app)
├── static/
│   ├── css/
│   │   └── style.css      # All styling
│   └── js/
│       ├── app.js         # Main application logic, UI handlers
│       └── canvas.js      # Canvas rendering, zoom/pan, all drawing
├── TODO.txt               # Feature roadmap and task list
├── VERSION.txt            # Version history
└── TRANSFORM_FEATURE_DESIGN.md  # Design doc for future transform feature
```

## Architecture Overview

### Data Flow
```
User Input → app.js → WebSocket/REST → app.py → WebSocket broadcast → All clients update
                ↓
         canvas.js (render)
```

### Key Concepts

1. **Project** - Contains raster dimensions and array of layers
2. **Layer (Screen)** - A single LED screen/wall with panels arranged in a grid
3. **Panel (Cabinet)** - Individual LED cabinet unit within a layer
4. **Raster** - The overall pixel canvas (e.g., 1920x1080)

### State Management

- **Server State:** `current_project` dict in app.py - source of truth for layers/panels
- **Client State:** `window.app.project` - synced via WebSocket
- **Undo/Redo:** Client-side state stack in app.js
- **Client-only Props:** Some properties (like Data Flow settings) are stored only client-side in localStorage

## Current Features (v0.6.1.10)

### Core Functionality
- Grid-based LED panel layout system
- Multiple screens/layers with independent settings
- Raster size configuration (custom width/height)
- Layer visibility, naming, selection
- Drag to move layers with magnetic snapping

### View Modes (4 tabs)
1. **Pixel Map** - Checkerboard pattern, circle-with-X test pattern, offset labels
2. **Cabinet ID** - Panel numbering (A1, B2, 1-1 formats), configurable position/color
3. **Data Flow** - Port assignments, 8 serpentine patterns, P/R input labels
4. **Power** - Circuit visualization, capacity calculations, custom power paths, and editable circuit labels

### Panel Operations
- Click panel to hide/delete (shows ghost outline)
- Hidden panels preserved across operations
- Duplicate layer copies hidden panel state

### Zoom & Navigation
- Zoom: 1% to 50,000%
- Pixel grid overlay at 1000%+ zoom (all tabs)
- Fit-to-view and 1:1 buttons
- Spacebar + drag for panning
- Mouse wheel zoom
- Magnetic snap to raster edges and other layers

### Labels & Display
- Screen name labels with size/position controls
- Dimension labels (pixels, meters, feet)
- Corner offset indicators (TL, TR, BL, BR)

### Export
- **PNG** - Single or ZIP for multiple views
- **PDF** - Multi-page with all views
- **PSD** - Layered Photoshop files, each screen as separate layer
- Client-side canvas capture for pixel-accurate output

## Key Files Deep Dive

### app.py (Backend)
- `create_layer()` - Generates layer with panel grid
- `/api/layer/add` - Create new layer
- `/api/layer/<id>` PUT - Update layer properties
- `/api/panel/<layer_id>/<panel_id>/toggle-hidden` - Hide/show panel
- `/api/export/*` - Export endpoints (PNG, PDF, PSD)
- WebSocket handlers for real-time sync

### canvas.js (Rendering)
- `CanvasRenderer` class - All drawing logic
- `render()` - Main render loop
- `renderPixelMap()`, `renderCabinetID()`, `renderDataFlow()` - View-specific rendering
- `renderPanel()` - Individual panel drawing with clipping
- Zoom/pan transformation math
- Export mode flag for clean output (no grid/boundary)

### app.js (Application Logic)
- `LEDRasterApp` class - Main application
- Layer selection, UI updates
- Undo/redo state management
- Export orchestration (renders each view, sends to server)
- Keyboard shortcuts (Delete, Ctrl+Z, etc.)
- Settings panel management

## Known Quirks / Important Notes

1. **Panel coordinates are in "world space"** - The canvas uses a transform for zoom/pan, so panel x/y are actual pixel positions in the raster

2. **Hidden panels** - Panels have a `hidden` boolean. They render as ghost outlines and are excluded from data flow calculations

3. **Client-side properties** - Some layer properties (flowPattern, arrowColor, etc.) are stored only in localStorage, not on server. See `saveClientSideProperties()` in app.js

4. **Export uses offscreen canvas** - To get pixel-perfect output, export creates a temporary canvas at exact raster dimensions with zoom=1

5. **PSD layers** - Each screen becomes a PSD layer at its exact position/size within the raster canvas

6. **Raster boundary clipping** - Panels/labels outside the raster bounds are clipped. The red dashed line shows the raster edge

## Roadmap Highlights

See `TODO.txt` for full list. Key upcoming items:

- **Transform Mode** - Resize/rotate layers (design doc in TRANSFORM_FEATURE_DESIGN.md)
- **Layer Reordering** - Drag & drop in layer panel
- **Native Launcher** - Electron app like Bitfocus Companion
- **Editable Data Flow Labels** - Custom P1/R1 text
- **Settings Panel** - Auto-save, default values

## Development Tips

1. **Hot reload works** - Flask debug mode reloads on Python changes. For JS/CSS, just refresh browser

2. **Console logging** - Both app.js and canvas.js have logging. Check browser console for client issues, terminal for server

3. **Version numbering** - Update in TWO places in index.html (title and h1 header)

4. **Testing exports** - The `/api/export/*` endpoints expect base64 image data from client canvas capture

5. **WebSocket events** - `project_data`, `layer_added`, `layer_updated`, `layer_deleted` - keep client/server in sync

## Questions?

This project is being developed iteratively with AI assistance. Check the conversation transcripts in `/mnt/transcripts/` for detailed context on past decisions and implementations.

---

*Last updated: v0.5.4.0 - February 2026*
