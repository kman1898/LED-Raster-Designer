# LED Raster Designer - Developer Guide

## Overview

LED Raster Designer is a professional web-based application for designing LED wall layouts for live events, concerts, and installations. It competes with existing software like Pixel Perfect Pro, focusing on a grid-based architecture where LED panels are automatically generated as grids.

**Current Version:** 0.6.1.10

> Consistency note:
> - `README.md` = user-facing behavior/features
> - `VERSION.txt` = completed release history
> - `TODO.txt` = open work only

## Tech Stack

- **Backend:** Python Flask + Flask-SocketIO
- **Frontend:** Vanilla JavaScript, HTML5 Canvas
- **Real-time Communication:** WebSocket (Socket.IO)
- **Image Processing:** PIL/Pillow, NumPy
- **PSD Export:** pytoshop library
- **PDF Export:** reportlab library

## Project Structure

```
led_raster_designer/
├── app.py                 # Flask backend - API endpoints, WebSocket handlers
├── start.sh               # Startup script
├── requirements.txt       # Python dependencies
├── static/
│   ├── js/
│   │   ├── app.js         # Main application logic, UI, state management
│   │   └── canvas.js      # Canvas rendering, all drawing/visualization
│   └── css/
│       └── style.css      # All styling
├── templates/
│   └── index.html         # Single-page app HTML structure
├── TODO.txt               # Feature roadmap and bug tracking
├── TRANSFORM_FEATURE_DESIGN.md  # Design doc for future transform feature
└── DEVELOPER_GUIDE.md     # This file
```

## Getting Started

### Prerequisites
```bash
pip3 install flask flask-socketio pillow numpy pytoshop reportlab
```

### Running the App
```bash
cd led_raster_designer
python3 app.py
```

Server starts on `http://localhost:8050` (also accessible via network IP on port 8050)

## Architecture

### Data Model

**Project Structure:**
```javascript
{
  name: "Project Name",
  raster_width: 1920,      // Total canvas width in LED pixels
  raster_height: 1080,     // Total canvas height in LED pixels
  layers: [...]            // Array of screen/layer objects
}
```

**Layer (Screen) Structure:**
```javascript
{
  id: 1,
  name: "Screen1",
  columns: 8,              // Number of panels horizontally
  rows: 5,                 // Number of panels vertically
  cabinet_width: 128,      // Panel width in LED pixels
  cabinet_height: 128,     // Panel height in LED pixels
  offset_x: 0,             // X position in raster
  offset_y: 0,             // Y position in raster
  visible: true,
  color1: {r, g, b},       // Checkerboard color 
