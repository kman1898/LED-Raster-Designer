# Transform Mode Feature Design

## Overview
Add ability to resize screens by dragging corner/edge handles with live visual feedback.

## User Interface

### Activation
**Option 1: Toggle Button**
- Add "Transform" button in top toolbar next to Snap toggle
- Button states: OFF (default) / ON (transform mode active)
- Keyboard shortcut: `T` key to toggle

**Option 2: Modifier Key** (Simpler)
- Hold `Cmd/Ctrl` + `Shift` + click corner/edge
- No UI toggle needed
- More like Photoshop's free transform

**RECOMMENDATION: Start with Option 2 (modifier key) - simpler to implement**

## Visual Feedback

### Corner Handles (Like Offset Corners)
When transform mode active or hovering:
- Show handles at ALL 4 corners (just like offset display)
- Each corner is independently controllable
- Color: #4A90E2 (same blue as selection box)
- Size: 8x8px squares
- Always visible when in transform mode (not hover-only)

**Key Point**: Just like offset corners (TL, TR, BL, BR) can each show data,
transform handles at each corner can each control the resize independently.

### Live Overlay During Resize
When dragging ANY corner:
```
┌─────────────────────┐
│                     │
│     16 x 9 panels   │  ← Centered overlay
│                     │
└─────────────────────┘
```
- Semi-transparent black background: `rgba(0, 0, 0, 0.7)`
- White text: 24px bold
- Format: `{columns} x {rows} panels`
- Position: Centered on the layer being resized

## Interaction

### Resize Logic - Any Corner Control
Each corner controls resize differently (maintains anchor point at opposite corner):

1. **Bottom-Right (BR)**: Resize from top-left anchor
   - Anchor: TL stays fixed at (offset_x, offset_y)
   - Grows/shrinks right and down

2. **Top-Left (TL)**: Resize from bottom-right anchor  
   - Anchor: BR stays fixed
   - Changes offset_x, offset_y AND dimensions
   - Grows/shrinks left and up

3. **Top-Right (TR)**: Resize from bottom-left anchor
   - Anchor: BL stays fixed
   - Changes offset_y AND dimensions
   - Grows/shrinks right and up

4. **Bottom-Left (BL)**: Resize from top-right anchor
   - Anchor: TR stays fixed
   - Changes offset_x AND dimensions
   - Grows/shrinks left and down

**All corners are equally accessible - just like offset display options!**

## Technical Implementation

### Canvas.js Changes
```javascript
// New state flags
this.isResizing = false;
this.resizeCorner = null;  // 'br', 'tl', 'tr', 'bl'
this.resizeStartDims = null;

// In handleMouseDown
if (Cmd/Ctrl + Shift + nearCorner) {
    this.isResizing = true;
    this.resizeCorner = 'br';
    this.resizeStartDims = {
        columns: layer.columns,
        rows: layer.rows
    };
}

// In handleMouseMove
if (this.isResizing) {
    // Calculate new dimensions
    // Render overlay
}

// In handleMouseUp
if (this.isResizing) {
    // Update layer via app.updateLayer()
    // Clear overlay
}
```

### Overlay Rendering
```javascript
renderResizeOverlay(columns, rows, layer) {
    const layerCenterX = layer.offset_x + (layer.columns * layer.cabinet_width) / 2;
    const layerCenterY = layer.offset_y + (layer.rows * layer.cabinet_height) / 2;
    
    const text = `${columns} x ${rows} panels`;
    
    this.ctx.save();
    this.ctx.font = `bold ${24 / this.zoom}px Arial`;
    const metrics = this.ctx.measureText(text);
    const padding = 20 / this.zoom;
    
    // Background
    this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    this.ctx.fillRect(
        layerCenterX - metrics.width/2 - padding,
        layerCenterY - 12 / this.zoom - padding,
        metrics.width + padding * 2,
        24 / this.zoom + padding * 2
    );
    
    // Text
    this.ctx.fillStyle = '#ffffff';
    this.ctx.textAlign = 'center';
    this.ctx.textBaseline = 'middle';
    this.ctx.fillText(text, layerCenterX, layerCenterY);
    this.ctx.restore();
}
```

### Corner Detection
```javascript
isNearCorner(worldX, worldY, layer, threshold = 15) {
    const layerRight = layer.offset_x + (layer.columns * layer.cabinet_width);
    const layerBottom = layer.offset_y + (layer.rows * layer.cabinet_height);
    
    const corners = {
        br: { x: layerRight, y: layerBottom },
        tl: { x: layer.offset_x, y: layer.offset_y },
        tr: { x: layerRight, y: layer.offset_y },
        bl: { x: layer.offset_x, y: layerBottom }
    };
    
    for (let [corner, pos] of Object.entries(corners)) {
        const dist = Math.sqrt(
            Math.pow(worldX - pos.x, 2) + 
            Math.pow(worldY - pos.y, 2)
        );
        if (dist < threshold / this.zoom) {
            return corner;
        }
    }
    return null;
}
```

## Implementation Phases

### Phase 1 (MVP) - All Corners Working
- ✅ Detect Cmd/Ctrl + Shift + click near ANY corner (like offset corners)
- ✅ Show live overlay with panel count during drag
- ✅ All 4 corners work with proper anchor logic
- ✅ Update dimensions AND offsets on mouse up (for TL, TR, BL corners)
- ✅ Cursor changes to appropriate resize cursor per corner

**Corner-specific cursors:**
- BR: `nwse-resize` (↘)
- TL: `nwse-resize` (↖)
- TR: `nesw-resize` (↗)
- BL: `nesw-resize` (↙)

### Phase 2 - Visual Handles
- Draw corner handles when in transform mode
- Show all 4 handles simultaneously (like offset display)
- Hover effects
- Better visual feedback

### Phase 3 - Toggle Button & Shortcut
- Add "Transform" button in toolbar
- `T` key shortcut to toggle transform mode
- When ON, handles always visible

### Phase 4 - Edge Handles (Optional)
- Middle handles on edges for 1D resize
- Top/Bottom: Resize rows only
- Left/Right: Resize columns only

## Testing Checklist
- [ ] Resize from 8x5 to 16x9 works
- [ ] Minimum 1x1 enforced
- [ ] Overlay shows correct dimensions during drag
- [ ] Overlay disappears after drag
- [ ] Undo/redo works with resize
- [ ] Magnetic snapping doesn't interfere
- [ ] Works at different zoom levels
- [ ] Cursor changes to resize cursor when near corner
- [ ] Hidden panels are preserved during resize

## Future Enhancements
- Constrain aspect ratio (hold Shift during resize)
- Numeric input during resize (type "16" to set width)
- Snap to common aspect ratios (16:9, 4:3, etc.)
- Preview ghost outline during resize
