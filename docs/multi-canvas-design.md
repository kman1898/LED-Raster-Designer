# Multi-Canvas Design — v0.8

Status: **DRAFT**, awaiting final approval.
Branch: `feature/v0.8`.
Owner: kman1898.

This document is the source of truth for the multi-canvas feature. Edits here require a brief comment in the PR explaining why. Everything below is locked unless explicitly amended.

---

## 1. Goals

- One project can contain **multiple canvases**, each representing a separate processor / output / raster.
- A canvas is essentially a self-contained raster — same as today's single-canvas project, just one of many.
- Layers can be **dragged from one canvas to another** (move) or duplicated to another canvas (Cmd/Alt+drag).
- Every view tab (Pixel Map, Cabinet ID, Show Look, Data, Power) renders **all canvases simultaneously** in the workspace.
- Existing v0.7 single-canvas projects **auto-migrate** to one canvas on load.

## 2. Non-goals (explicitly OUT for v0.8)

- A single layer being a member of multiple canvases simultaneously (shared/aliased layers). One layer = one canvas. Future v0.9+.
- Per-canvas Save (saving a single canvas to its own file). Future, optional.
- Backwards compatibility with v0.7 — once a project is opened + saved as v0.8 it is no longer openable in v0.7.
- A separate project-level "show raster". The workspace itself is the stage.
- SCR (NovaStar) export changes. Currently broken; out of scope.

## 3. Glossary

| Term | Meaning |
|------|---------|
| **Canvas** | A single raster + processor. Has a workspace position, its own raster size, and a set of layers. |
| **Workspace** | The unbounded 2D area inside the canvas viewport where canvases are laid out. Pan + zoom. |
| **Active canvas** | The canvas whose properties are shown in the left sidebar; receives `+ Add Screen`; its raster size is what the toolbar `Raster` field edits. |
| **Layer** | An on-screen element (screen / image / text). Belongs to exactly one canvas. Has positions in *that canvas's* coordinate space. |
| **Show Look** | A view mode where each layer renders at its `showOffsetX/Y` (still relative to its canvas's raster). |
| **Layer group** | The visual grouping of layers under a canvas in the right-side Screens panel. One layer group per canvas. |

---

## 4. Data model

### 4.1 v0.7 (current)

```jsonc
{
  "name": "MyShow",
  "raster_width": 11520,
  "raster_height": 2272,
  "show_raster_width": 11520,
  "show_raster_height": 2272,
  "data_flow_perspective": "front",
  "power_perspective": "front",
  "layers": [
    { "id": 1, "name": "SR", "offset_x": 0, "offset_y": 0,
      "showOffsetX": 0, "showOffsetY": 0,
      "processorType": "novastar-armor",
      "powerVoltage": 208, "powerAmperage": 20,
      ... }
  ]
}
```

`raster_width/height`, `show_raster_*`, processor type, voltage/amperage are project-level today. They are about to be canvas-level.

### 4.2 v0.8 (target)

```jsonc
{
  "name": "MyShow",
  "format_version": "0.8",                  // NEW. presence of this field === multi-canvas project
  "active_canvas_id": "c1",                 // NEW. which canvas's properties show in sidebar
  "canvases": [                             // NEW. array, ordered (z-order in sidebar reflects this)
    {
      "id": "c1",
      "name": "Canvas 1",
      "color": "#4A90E2",                   // auto-cycled from palette, user-overridable
      "workspace_x": 0,                     // NEW. position in workspace (px)
      "workspace_y": 0,
      "raster_width": 11520,                // moved from project to canvas
      "raster_height": 2272,
      "show_raster_width": 11520,           // moved from project to canvas
      "show_raster_height": 2272,
      "data_flow_perspective": "front",     // moved from project to canvas
      "power_perspective": "front",         // moved from project to canvas
      "visible": true                       // NEW. canvas-level eye toggle (hides canvas + all its layers)
    }
  ],
  "layers": [
    {
      "id": 1,
      "canvas_id": "c1",                    // NEW. which canvas this layer belongs to
      "name": "SR",
      "offset_x": 0, "offset_y": 0,         // unchanged. relative to canvas.raster
      "showOffsetX": 0, "showOffsetY": 0,   // unchanged. relative to canvas.show_raster
      "processorType": "novastar-armor",    // remains on layer (each layer can technically override
                                            //  its canvas's processor; sidebar picker still works
                                            //  per-layer for backwards compatibility)
      ... everything else unchanged
    }
  ]
}
```

**Key invariants:**

- `canvases` array is non-empty (at least one canvas always exists).
- Every `layer.canvas_id` matches an existing `canvas.id`.
- `active_canvas_id` matches an existing `canvas.id`.
- Canvas IDs are stable strings (e.g. `c1`, `c2`, …). Renaming a canvas does not change its ID.
- Layer IDs remain globally unique (current behavior). They are not re-numbered when moving between canvases.

### 4.3 What stays project-level vs moves to canvas

| Field | v0.7 location | v0.8 location |
|-------|---------------|---------------|
| `raster_width` / `raster_height` | project | canvas |
| `show_raster_width` / `show_raster_height` | project | canvas |
| `data_flow_perspective` | project | canvas |
| `power_perspective` | project | canvas |
| `name` | project | project (unchanged) |
| Layers (the array) | project | project (unchanged); each entry now has `canvas_id` |
| Processor type / voltage / amperage / panel watts | layer | layer (unchanged) |
| Recent files, presets, preferences | project / user | unchanged |

Notes:
- Processor type stays on each layer because: today a layer can override its canvas's defaults, and we don't want to lose that flexibility. Adding a layer to a canvas should *default* the layer's processor to the canvas's preferred type, but the user can still change it per-layer.
- Per-canvas defaults (voltage / amperage / panel watts) live in the canvas object as **defaults applied to new layers added to that canvas** — actual values still live on the layer.

### 4.4 Migration (v0.7 → v0.8)

On project load:

1. Read project file.
2. If `format_version` is not present (`undefined` or any pre-0.8 value), it's a v0.7 project. Run the migrator:
   - Generate one canvas (`id: "c1"`, `name: project.name || "Canvas 1"`, color from palette[0], `workspace_x: 0`, `workspace_y: 0`).
   - Copy `raster_width`, `raster_height`, `show_raster_width`, `show_raster_height`, `data_flow_perspective`, `power_perspective` from project → canvas.
   - For every layer, set `layer.canvas_id = "c1"`.
   - Set `project.canvases = [c1]`, `project.active_canvas_id = "c1"`, `project.format_version = "0.8"`.
   - Strip the migrated fields from the project root.
3. **Show one-time toast** on first migration: *"Project upgraded to multi-canvas format (v0.8). Save to keep changes. Older app versions can no longer open this file."*
   - Toast appears only once per project, gated by checking if the project file on disk lacks `format_version`. If user saves, future loads see `format_version: "0.8"` and toast does not appear.

### 4.5 Backwards-compat policy

- v0.7 builds opening a v0.8 file: the project file's top-level `raster_width` is missing → app shows a "Project format is newer than this version. Please update." dialog and refuses to load. (CI test: open v0.8 file in v0.7 build, assert clean error.)
- We do **not** ship a "Save as legacy v0.7" option in v0.8.

---

## 5. UI architecture

### 5.1 Right sidebar — Layer Groups

Replaces today's flat Screens list.

```
SCREENS
─────────────────────────
🟦 Canvas 1                [👁] [⋮]   ← color swatch, visibility toggle, action menu
   [Lock all]   [+ Add Screen]
   ⋮⋮ SR                              ← drag-handle on left for reorder
   ⋮⋮ UPSTAGE
   ⋮⋮ SL

🟧 Canvas 2                [👁] [⋮]   ← active canvas: subtle highlight + colored ring
   [Lock all]   [+ Add Screen]
   ⋮⋮ DJ
─────────────────────────
[+ Add Canvas]
```

**Canvas action menu (⋮)** options:
- Rename
- Duplicate canvas (creates a copy with all layers; new canvas auto-positioned in workspace; layer IDs reassigned)
- Change color
- Delete canvas (confirm dialog; if canvas has layers, warn "Delete canvas + N layers?"; deleting the last canvas not allowed)

**Canvas drag-handle** on the canvas header → reorder canvases (changes canvases array order = z-order).

**Layer drag-handle** → reorder within group, OR drag onto another canvas group → moves layer cross-canvas (G3 behavior: offset_x/y reset to 0,0; showOffsetX/Y reset to 0,0).

**Cmd/Alt+drag** a layer to another canvas → duplicate (new layer ID, copied properties, dropped at 0,0 in new canvas).

### 5.2 Workspace rendering

The workspace shows **every visible canvas** at its `workspace_x, workspace_y` position. Each canvas is an dashed-outlined rectangle of size `raster_width × raster_height` (or `show_raster_width × show_raster_height` in Show Look). Inside each canvas, its layers render at their per-canvas-relative offsets.

| Tab | Canvas rect uses | Layers positioned at |
|-----|------------------|----------------------|
| Pixel Map | `raster_width × raster_height` | `offset_x, offset_y` |
| Cabinet ID | `raster_width × raster_height` | `offset_x, offset_y` |
| Show Look | `show_raster_width × show_raster_height` | `showOffsetX, showOffsetY` |
| Data Flow | `show_raster_width × show_raster_height` | `showOffsetX, showOffsetY` |
| Power | `show_raster_width × show_raster_height` | `showOffsetX, showOffsetY` |

In every case the screen position of a layer is `canvas.workspace_x + layer_offset_within_canvas`.

**Canvas rect drawn only if canvas has at least one visible layer.** Empty canvases don't clutter the workspace but still exist (visible in the sidebar; the user can add layers to them).

### 5.3 Color coding

- Each canvas has a `color` (hex string).
- Default palette (auto-cycled for new canvases):
  - `#4A90E2` (blue), `#F5A623` (orange), `#7ED321` (green), `#BD10E0` (purple), `#D0021B` (red), `#50E3C2` (teal), `#F8E71C` (yellow), `#9013FE` (deep purple).
  - After 8 canvases, cycle back to the start (collisions allowed — user can change manually).
- Color appears on:
  - The canvas's dashed-outline rectangle in the workspace
  - The layer name border / badge in the Screens panel (subtle left-edge stripe in the canvas's color)
  - The layer's outline color for selection highlights
  - The canvas color swatch in the Screens panel header
- **Active canvas** gets:
  - A bolder outline (1.5× line width) on its workspace rect
  - A faint background tint (canvas color at ~6% alpha) inside its rect
  - Subtle highlight on the canvas header in the sidebar

### 5.4 Selecting the active canvas

A canvas becomes active when:
- User clicks the canvas header in the Screens sidebar
- User clicks any layer in that canvas (sidebar or workspace)
- User clicks empty area within that canvas's rect in the workspace
- User adds a new canvas (the new canvas becomes active)

The toolbar `Raster: [W] x [H]` field always edits the **active canvas's** raster (Pixel Map or Show Look depending on view tab). The left sidebar properties panel shows the active canvas's settings.

### 5.5 Dragging canvases in the workspace

- Hover a canvas's outline → cursor changes to "move" indicator on the outline edges (drag-by-edge model, like keynote-style artboards).
- Drag → updates `canvas.workspace_x/y`. All layers stay glued (layer offsets are relative to the canvas, so they move with it).
- **Overlap handling**: if the user drops a canvas overlapping another, show a non-blocking warning toast: *"Canvases overlapping — visual rendering may be confusing."* No auto-snap, no rejection. User decides.

### 5.6 Auto-layout for new canvases

- New canvas is placed to the **right** of the rightmost existing canvas, with a gap of `max(200, 5% of rightmost canvas width)` pixels.
- Default raster size for new canvas = same as the active canvas's raster (so it feels like cloning the dimensions; avoids surprise).
- Default show raster = matches the new canvas's raster.

### 5.7 Layer drag between canvases (workspace)

- Pick up a layer from any canvas, drag onto another canvas's rect, drop.
- On drop:
  - `layer.canvas_id` updated to the new canvas's ID
  - `layer.offset_x = 0`, `layer.offset_y = 0`
  - `layer.showOffsetX = 0`, `layer.showOffsetY = 0`
  - Layer's color reflects new canvas's color (auto)
- **Cmd/Alt+drag** = duplicate (layer copied with new ID, dropped at 0,0 of target canvas).
- Drop indicator: target canvas's rect highlights + drop position icon at canvas top-left.

### 5.8 Hidden canvases

- Canvas-level 👁 toggle in the sidebar.
- Hiding a canvas:
  - Hides the canvas's rect in the workspace
  - Hides all layers in that canvas (visually only — does not change `layer.visible`)
  - Layers in the Screens panel under a hidden canvas group are dimmed
  - Hidden canvas not included in capacity / power totals or export selection by default
- Toggling visible re-shows everything.

---

## 6. Per-view behavior

### 6.1 Pixel Map / Cabinet ID

- Each canvas's Pixel Map raster rect drawn at its workspace position.
- Layers within use `offset_x/y` for position relative to canvas.
- Standard checkerboard / cabinet ID rendering per layer, unchanged.
- Front/Back perspective toggle in sidebar → applies to the active canvas only.

### 6.2 Show Look

- Each canvas's Show Look raster rect drawn at its workspace position. May differ in size from that canvas's Pixel Map raster (existing per-view raster size feature, preserved per canvas).
- Layers within use `showOffsetX/Y` for position relative to canvas.
- "Reset to Pixel Map Position" button still per-layer; sets `showOffsetX = offset_x` etc.
- The auto-link feature (drag in Pixel Map syncs Show Look while linked) continues to work per-canvas.

### 6.3 Data Flow / Power

- Same rendering as Show Look (per-canvas, layers at show position, canvas rect = show raster).
- Front/Back perspective toggle per canvas (sidebar reflects active canvas's setting).
- Wiring (port labels, arrows, circuit lines) renders per layer based on each layer's processor type.
- **Sidebar totals** show **active canvas** values (e.g. "Total Amps: 862 A").
- A new **"Project Total"** section at the bottom of the sidebar shows aggregated totals across all visible canvases (sum of amps, sum of ports, etc.).
- Capacity / power error badges render on individual layers regardless of which canvas is active (existing behavior, just extended).

### 6.4 Toolbar

- `Raster: [W] x [H]` field edits **active canvas's** raster (Pixel Map raster on Pixel Map / Cabinet ID tabs; Show Look raster on Show Look / Data / Power tabs — same per-view behavior as today, just per-canvas).
- Project name field unchanged.
- Fit / 1:1 / zoom buttons operate on the workspace as a whole.

---

## 7. Save / Load

### 7.1 Save flow

- Same save path as today (JSON file on disk).
- On save, the project structure is written in v0.8 format. `format_version: "0.8"` is always written.
- Per-user `Recent Files` list updated (existing behavior).

### 7.2 Load flow

- Read JSON.
- If `format_version === "0.8"`: load directly.
- If `format_version` missing or older: run migrator (Section 4.4), show one-time toast.
- If `format_version` newer than supported (e.g. user opens a v0.9 file in v0.8 build): show "Project format is newer than this version" dialog, do not load.

### 7.3 Auto-save / undo

- Cross-canvas layer drag is undoable (restores previous canvas + previous offsets).
- Canvas creation / deletion / rename / reorder / move / color change are all undoable.
- Undo history is a single stack at the project level — does not split per canvas.

---

## 8. Export

### 8.1 Export dialog

Expanded with a **canvas picker** above the existing view-mode picker:

```
EXPORT
──────────────────────
Canvases:
  ☑ Canvas 1     ← all visible canvases checked by default
  ☑ Canvas 2
  ☐ Canvas 3 (hidden)

Views:
  ☑ Pixel Map
  ☐ Cabinet ID
  ☑ Show Look
  ☑ Data
  ☑ Power

Format:  ◉ PNG   ○ PDF   ○ PSD

Filename pattern:  {project} - {canvas} - {view}.png
                    └ token preview ─┘
──────────────────────
[Cancel]  [Export]
```

- Filename pattern uses tokens: `{project}`, `{canvas}`, `{view}`. Default per format:
  - PNG: `{project} - {canvas} - {view}.png`
  - PDF: `{project} - {view}.pdf` (multi-page; one page per canvas per view)
  - PSD: `{project} - {canvas} - {view}.psd`
- **PDF is multi-page**: page order = canvas order × view order. Each page has the canvas + view in its header.
- **PSD per canvas + view**: one file per (canvas, view) combination.
- Hidden canvases are unchecked by default but can be re-checked manually.

### 8.2 Resolume Arena XML export

- Already handles per-screen output. Updated to iterate all visible canvases' layers. (Each canvas could be a separate Resolume "screen".)

---

## 9. Keyboard / mouse

| Action | Keys |
|--------|------|
| Move layer to other canvas | drag layer onto canvas (workspace) or canvas group (sidebar) |
| Duplicate layer to other canvas | Cmd/Alt + drag layer onto canvas |
| Reorder canvas | drag canvas header in sidebar, OR drag canvas in workspace to change `workspace_x/y` |
| Activate canvas | click anywhere in canvas (workspace), or click canvas header (sidebar) |
| Hide canvas | click 👁 in sidebar canvas header |
| Add new canvas | `+ Add Canvas` button in sidebar bottom |
| Rename canvas | double-click canvas name in sidebar header (or canvas action menu → Rename) |

---

## 10. Implementation slices (vertical tracers)

Each slice is a self-contained PR (target ~120-200 LOC, tests included). Order matters: each slice depends on the previous. All PRs target `feature/v0.8` (not `main`).

| # | Slice | What ships | Tests |
|---|-------|-----------|-------|
| 1 | **Data model + migrator** | Project file gains `canvases` + `format_version`; layers gain `canvas_id`; auto-migrator runs on load. UI unchanged (still single canvas). | Unit: migrator on real v0.7 fixtures; round-trip save/load preserves data. |
| 2 | **Canvas list UI in sidebar** | Sidebar Screens panel groups layers under canvas headers. + Add Canvas button. Rename, Delete, Duplicate, Reorder. Color cycling. | Unit: canvas CRUD; UI snapshot test of sidebar layout. |
| 3 | **Canvas rect rendering in workspace** | Each canvas's rect drawn at its `workspace_x/y` position (initially auto-laid horizontally). Color-coded outlines. Empty canvases not drawn. | Visual regression: 1-canvas, 2-canvas, 3-canvas projects render correctly. |
| 4 | **Active canvas selection** | Click on canvas (workspace or sidebar) makes it active. Sidebar properties + toolbar raster reflect active. + Add Screen targets active. | Unit: active-canvas state transitions; integration test for sidebar update. |
| 5 | **Drag canvas in workspace** | Drag a canvas's outline to reposition. Layers stay glued. Overlap warning toast. | Unit: drag math; integration test for layer follow-along. |
| 6 | **Per-canvas raster (Pixel Map / Show Look)** | Each canvas has its own raster sizes; toolbar edits active canvas's raster. Layers render relative to their canvas. | Unit: layer position computation; integration: change one canvas raster, others unaffected. |
| 7 | **Drag layer between canvases** | Drag a layer from one canvas to another (workspace + sidebar). offset/showOffset reset to 0,0. Cmd/Alt+drag = duplicate. | Unit: drop logic; integration: undo restores. |
| 8 | **Per-canvas processor / perspective settings** | Front/Back perspective per canvas. Voltage/amperage/etc per canvas defaults applied on new layer. | Integration: switching active canvas updates sidebar. |
| 9 | **Hidden canvases** | 👁 toggle hides canvas + all layers visually. Hidden canvases excluded from totals. | Unit: visibility filter; integration: render skips hidden. |
| 10 | **Project totals in Data / Power sidebar** | Active-canvas totals + Project total section. | Unit: aggregation math. |
| 11 | **Export multi-canvas** | Export dialog gains canvas picker. PDF multi-page. Per-canvas PNG/PSD. | Integration: export each format with 2 canvases, verify file structure. |
| 12 | **Migration UX + cleanup** | One-time toast on first v0.7→v0.8 migration. v0.7 file format detection on save. README + VERSION updates. | Manual: load v0.7 fixture, verify toast + save, reload, verify no second toast. |
| 13 | **Polish + ship v0.8.0** | Icon set, animations on canvas reorder, edge cases (last-canvas-can't-be-deleted, drag from one canvas onto itself, etc). Final QA pass. Ship release. | Full regression. |

After Slice 13, **multi-canvas is rock solid** and we move to the expanded processor hardware detail feature (XD boxes, CVT counts, etc.).

### 10.1 Per-slice version stance

- Slices 1-12 ship as PRs into `feature/v0.8` (no version bump on each — feature branch is WIP).
- Slice 13 (or whichever final slice ships v0.8.0) is the version bump + tag + release.

---

## 11. Risk register

| Risk | Mitigation |
|------|-----------|
| v0.7 project loses data during migration | Auto-migrator round-trip-tested against multiple real v0.7 fixtures (EDC, Griztronics, etc.) before slice 2. |
| Workspace performance with 5+ canvases | Each canvas's render path is unchanged; only the per-layer translate shifts to include `workspace_x/y`. Should not regress. Benchmark with 10-canvas synthetic project in slice 3. |
| Accidental cross-canvas drag during normal work | Drop detection requires a clear hover-over-other-canvas state with visual indicator. Drag distance threshold preserved. |
| Existing per-view raster size (v0.7.6 feature) confuses users in multi-canvas | Each canvas keeps its own per-view raster size pair (Pixel Map raster + Show Look raster). No new concepts introduced. |
| Color collisions confusing | After 8 canvases palette wraps. User can manually change. Documented. |
| Load failure on a v0.8 file in v0.7 build | App refuses to load with clean dialog. CI test added (Slice 1). |
| Undo across canvas operations gets out of sync | All canvas-level operations go through the same undo stack as layer operations. Tested in slice 4 onward. |

---

## 12. Open questions

(none — all design decisions locked through Round 3. This section reserved for issues found during implementation.)

---

## 13. Out of scope (deferred)

- **Sharing a layer across canvases** (one layer in two canvases simultaneously). Likely v0.9 if real demand emerges.
- **Per-canvas Show Look toggle to "combine all canvases into one virtual stage"** — current model lets users do this manually by overlapping canvases or dragging layers cross-canvas.
- **Export of a single layer in isolation** — user mentioned as a "not bad idea later." Out for v0.8.
- **SCR (NovaStar sending card) export** — currently broken. Separate fix, not part of v0.8.
- **Per-canvas keyboard shortcut** (e.g. Cmd+1 jumps to Canvas 1) — easy to add later if users want it.

---

## 14. Sign-off

- Drafted: 2026-05-02 by kman1898
- Approved: _pending review_
