# LED Raster Designer — Changelog (v0.6.2.1 → v0.6.2.5)

## v0.6.2.5 — March 11, 2026

### CI/CD & Testing
- Added **CI workflow** (`ci.yml`): runs flake8 lint, JavaScript lint (ESLint), and pytest across Python 3.10 / 3.11 / 3.12 on every push and PR to `main`.
- Added **Release workflow** (`release.yml`): triggered by version tags (`v*`), builds macOS `.app` and Windows `.exe` via PyInstaller, with optional code signing and notarization, then creates a draft GitHub Release with both ZIPs.
- Added comprehensive **test suite** (573 lines across 5 test files):
  - `test_helpers.py` — helper/utility function tests
  - `test_layers.py` — layer CRUD, reorder, copy/paste, visibility, lock
  - `test_panels.py` — panel toggle and state management
  - `test_export.py` — image export and render pipeline
  - `test_project.py` — save/load project round-trip
  - `conftest.py` — shared Flask test client fixture
- Added `requirements-dev.txt` for development dependencies.

### Bug Fixes
- Fixed **float-to-int conversion bug** in `render_layer_to_image` — fractional pixel coordinates now correctly convert to integers before drawing.
- Removed **unused global declarations** in `save_project` and `delete_layer` (code cleanup).

### Documentation & Legal
- Added professional README header with CI status badges.
- Added proprietary LICENSE file for MeshTech Systems LLC.

---

## v0.6.2.4 — March 10, 2026

### Bug Fixes
- Fixed **undo/redo for inline layer rename** — double-click rename (edit → blur) now properly records undo history.
- Fixed **undo/redo for toggle panel blank** — toggling a panel's blank state is now undoable.

---

## v0.6.2.3 — March 10, 2026

### Enhancements
- **Comprehensive undo/redo coverage** for all layer property changes:
  - Colors, sizes, flow patterns, power settings, labels, borders, and all other sidebar properties now create undo history entries.
- Changed `updateLayers` default to always save history, ensuring every UI-driven change is undoable.

### Bug Fixes
- Fixed undo/redo for **toggle panel hidden** (Alt+click).
- Fixed undo/redo for **layer visibility toggle**.
- Fixed undo/redo for **layer lock toggle**.

---

## v0.6.2.2 — March 10, 2026

### Bug Fixes
- Fixed **undo/redo not working for raster size changes** — width and height changes are now captured in undo history and properly restored on undo/redo.

---

## v0.6.2.1 — March 8, 2026

### Bug Fixes
- Fixed **multi-select offset fields** overwriting each other on drag release and manual input.
- After drag-moving multiple layers, offset inputs now properly show mixed-value indicator.

### Backlog
- Added multi-project tabs feature to TODO backlog.
