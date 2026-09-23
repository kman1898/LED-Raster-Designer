"""Deleting a canvas from the sidebar kebab: the confirm text and the
selection afterwards (Issue 112 follow-ups, 2026-09-22).

* The confirm says where the kept screens go - "that canvas" only when every
  kept screen is shown on ONE canvas, otherwise "their other canvas" with the
  canvases named - and warns which kept screen will land on top of a screen
  already homed on its target (position is kept, so this is the only notice).
* After the delete a screen the server removed is no longer current or
  selected; a surviving selected screen takes over, else nothing is selected.

Run alone (the live server is shared with the other browser test files):
    python3 -m pytest tests/test_canvas_delete_ui.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project as this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    pg.evaluate(BOOT_JS)
    yield pg
    context.close()


BOOT_JS = r"""
window.__cd = {
  // A fresh project with `nCanvases` canvases (c1..cN) and the given screens:
  // {name, canvas, x, y, show, cols, rows, rotation} - `show` is a Show Look
  // drag onto that canvas; cols/rows default to 2x2; rotation is PUT after.
  async fresh(nCanvases, screens) {
    await fetch('/api/project/new', { method: 'POST' });
    // A new project seeds one screen on c1; these tests name every screen.
    const seeded = await (await fetch('/api/project')).json();
    for (const l of seeded.layers) await fetch('/api/layer/' + l.id, { method: 'DELETE' });
    for (let i = 1; i < nCanvases; i++) {
      await fetch('/api/canvas', { method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: '{}' });
    }
    const ids = {};
    for (const s of screens) {
      const r = await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name: s.name, columns: s.cols || 2, rows: s.rows || 2,
          cabinet_width: 128, cabinet_height: 128,
          offset_x: s.x || 0, offset_y: s.y || 0, canvas_id: s.canvas,
        }),
      });
      const l = await r.json();
      ids[s.name] = l.id;
      if (s.rotation) {
        await fetch('/api/layer/' + l.id, {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ rotation: s.rotation }),
        });
      }
      if (s.show) {
        await fetch('/api/layer/' + l.id + '/show_canvas', {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ show_canvas_id: s.show }),
        });
      }
    }
    window.app.project = await (await fetch('/api/project')).json();
    window.app.currentLayer = null;
    window.app.selectedLayerIds = new Set();
    window.app.lastSelectedLayerId = null;
    window.app.renderLayers();
    if (window.app._flushPendingSaveState) window.app._flushPendingSaveState();
    window.app.resetHistory('Initial State');
    return ids;
  },
  select(ids) {
    window.app.selectedLayerIds = new Set(ids);
    window.app.currentLayer = window.app.project.layers.find(l => l.id === ids[ids.length - 1]);
    window.app.lastSelectedLayerId = ids[ids.length - 1];
  },
  stubConfirm(answer) {
    window.__cd.asked = [];
    window.confirm = (m) => { window.__cd.asked.push(m); return answer; };
  },
  // Drive the real sidebar kebab: its menu button, then the Delete entry.
  async deleteViaKebab(canvasId) {
    const btn = document.querySelector(
      `.canvas-group[data-canvas-id="${canvasId}"] .canvas-menu-btn`);
    if (!btn) throw new Error('no kebab for ' + canvasId);
    btn.click();
    await new Promise(r => setTimeout(r, 150));
    const del = document.querySelector('.canvas-menu-popup button[data-action="delete"]');
    if (!del) throw new Error('no Delete entry in the canvas menu');
    del.click();
  },
  async settle(ms) { await new Promise(r => setTimeout(r, ms || 400)); },
};
"""


def _ask(page, n_canvases, screens, canvas_id='c1'):
    """Open Delete on ``canvas_id`` with confirm stubbed to No; return the
    confirm text and the screen ids."""
    return page.evaluate(r"""async ([n, screens, cid]) => {
      const ids = await window.__cd.fresh(n, screens);
      window.__cd.stubConfirm(false);
      await window.__cd.deleteViaKebab(cid);
      await window.__cd.settle(300);
      const srv = await (await fetch('/api/project')).json();
      return { ids, asked: window.__cd.asked, canvases: srv.canvases.map(c => c.id) };
    }""", [n_canvases, screens, canvas_id])


def test_confirm_names_the_one_canvas_the_kept_screens_move_to(page):
    out = _ask(page, 2, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0, 'show': 'c2'},
        {'name': 'S2', 'canvas': 'c1', 'x': 600, 'y': 0},
    ])
    assert len(out['asked']) == 1, out
    msg = out['asked'][0]
    assert msg.startswith("Delete canvas 'Canvas 1' and its 1 layer?"), msg
    assert "1 screen shown on 'Canvas 2' will move to that canvas instead." in msg, msg
    assert 'overlap' not in msg, msg
    assert out['canvases'] == ['c1', 'c2'], 'No must not delete'


def test_confirm_says_their_other_canvas_when_the_kept_screens_split(page):
    out = _ask(page, 3, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0, 'show': 'c2'},
        {'name': 'S2', 'canvas': 'c1', 'x': 600, 'y': 0, 'show': 'c3'},
        {'name': 'S3', 'canvas': 'c1', 'x': 1200, 'y': 0},
    ])
    msg = out['asked'][0]
    assert 'will move to that canvas' not in msg, msg
    assert ("2 screens shown on other canvases ('Canvas 2', 'Canvas 3') "
            "will move to their other canvas instead.") in msg, msg


def test_confirm_warns_which_kept_screen_lands_on_a_screen_already_there(page):
    """S1 keeps its pixel-map position when it moves to Canvas 2, where S3
    already sits on the same pixels; S2 moves to a clear spot."""
    out = _ask(page, 2, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0, 'show': 'c2'},
        {'name': 'S2', 'canvas': 'c1', 'x': 2000, 'y': 0, 'show': 'c2'},
        {'name': 'S3', 'canvas': 'c2', 'x': 100, 'y': 100},
        {'name': 'S4', 'canvas': 'c2', 'x': 1000, 'y': 1000},
    ])
    msg = out['asked'][0]
    assert msg.startswith("Delete canvas 'Canvas 1'?"), msg
    assert "2 screens shown on 'Canvas 2' will move to that canvas instead." in msg, msg
    assert "Warning: S1 will overlap S3 on 'Canvas 2'." in msg, msg
    assert 'S2 will overlap' not in msg and 'S4' not in msg, msg


def test_confirm_lists_every_screen_a_kept_one_overlaps(page):
    out = _ask(page, 2, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0, 'show': 'c2'},
        {'name': 'S3', 'canvas': 'c2', 'x': 100, 'y': 100},
        {'name': 'S4', 'canvas': 'c2', 'x': 200, 'y': 0},
    ])
    msg = out['asked'][0]
    assert "Warning: S1 will overlap S3 and S4 on 'Canvas 2'." in msg, msg


def test_confirm_does_not_claim_the_delete_cannot_be_undone(page):
    """Undo restores a deleted canvas and its screens (the Delete Canvas
    history entry is a full snapshot), so the confirm must not say otherwise."""
    out = _ask(page, 2, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0},
        {'name': 'S2', 'canvas': 'c1', 'x': 600, 'y': 0},
    ])
    msg = out['asked'][0]
    assert msg == "Delete canvas 'Canvas 1' and its 2 layers?", msg
    assert 'cannot be undone' not in msg.lower(), msg


def test_overlap_warning_uses_the_rotated_footprint_not_the_unrotated_box(page):
    """A 4x1 at (0,0) turned 90 stands 128 wide by 512 tall about its
    centre (x 192..320, y -192..320). Against a 2x2 at (400,0) the unrotated
    512x128 box overlapped and warned falsely; the drawn footprint does not."""
    out = _ask(page, 2, [
        {'name': 'Tall', 'canvas': 'c1', 'x': 0, 'y': 0, 'cols': 4, 'rows': 1,
         'rotation': 90, 'show': 'c2'},
        {'name': 'Box', 'canvas': 'c2', 'x': 400, 'y': 0},
    ])
    msg = out['asked'][0]
    assert "1 screen shown on 'Canvas 2' will move to that canvas instead." in msg, msg
    assert 'overlap' not in msg, msg


def test_overlap_warning_catches_a_rotated_screen_standing_on_another(page):
    """Same 4x1 at 90: its foot reaches y=320, so a 2x2 at (192,300) is
    under it. The unrotated box (y 0..128) missed that overlap."""
    out = _ask(page, 2, [
        {'name': 'Tall', 'canvas': 'c1', 'x': 0, 'y': 0, 'cols': 4, 'rows': 1,
         'rotation': 90, 'show': 'c2'},
        {'name': 'Box', 'canvas': 'c2', 'x': 192, 'y': 300},
    ])
    msg = out['asked'][0]
    assert "Warning: Tall will overlap Box on 'Canvas 2'." in msg, msg


def _delete_with(page, screens, selected, canvas_id='c1'):
    return page.evaluate(r"""async ([screens, selected, cid]) => {
      const ids = await window.__cd.fresh(2, screens);
      window.__cd.select(selected.map(n => ids[n]));
      window.app.loadLayerToInputs();
      const colsBefore = document.getElementById('screen-columns').value;
      window.__cd.stubConfirm(true);
      await window.__cd.deleteViaKebab(cid);
      await window.__cd.settle(900);
      const alive = window.app.project.layers.map(l => l.id);
      return {
        ids, alive, colsBefore,
        colsAfter: document.getElementById('screen-columns').value,
        current: window.app.currentLayer ? window.app.currentLayer.id : null,
        selected: [...window.app.selectedLayerIds],
        last: window.app.lastSelectedLayerId,
        canvases: window.app.project.canvases.map(c => c.id),
      };
    }""", [screens, selected, canvas_id])


def test_deleted_current_screen_is_no_longer_current_or_selected(page):
    """S2 goes with c1. It was current; afterwards nothing is current and the
    selection is empty (the next edit used to PUT /api/layer/<dead id>)."""
    out = _delete_with(page, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0, 'show': 'c2'},
        {'name': 'S2', 'canvas': 'c1', 'x': 600, 'y': 0},
    ], ['S2'])
    assert out['canvases'] == ['c2'], out
    assert out['ids']['S2'] not in out['alive'], out
    assert out['current'] is None, out
    assert out['selected'] == [], out
    assert out['last'] is None, out


def test_surviving_selected_screen_takes_over_as_current(page):
    """S1 (kept, moves to c2) and S2 (deleted) both selected, S2 current: S1
    becomes current and is the whole selection."""
    out = _delete_with(page, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0, 'show': 'c2'},
        {'name': 'S2', 'canvas': 'c1', 'x': 600, 'y': 0},
    ], ['S1', 'S2'])
    assert out['ids']['S1'] in out['alive'] and out['ids']['S2'] not in out['alive'], out
    assert out['current'] == out['ids']['S1'], out
    assert out['selected'] == [out['ids']['S1']], out
    assert out['last'] == out['ids']['S1'], out


def test_screen_info_panel_no_longer_shows_the_deleted_screens_values(page):
    """S2 (5 columns) was current and went with c1; nothing is selected
    afterwards. The panel used to keep S2's columns, rows and offsets, and
    the next Update Properties read them back. It shows the panel's
    no-single-value state instead."""
    out = _delete_with(page, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0, 'show': 'c2', 'cols': 3},
        {'name': 'S2', 'canvas': 'c1', 'x': 600, 'y': 0, 'cols': 5},
    ], ['S2'])
    assert out['colsBefore'] == '5', out
    assert out['current'] is None, out
    assert out['colsAfter'] != '5', out
    assert out['colsAfter'] == '', out


def test_screen_info_panel_shows_the_surviving_selected_screen(page):
    """S1 (3 columns) and S2 (5 columns) selected, S2 current and deleted:
    S1 takes over and the panel shows S1's values."""
    out = _delete_with(page, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0, 'show': 'c2', 'cols': 3},
        {'name': 'S2', 'canvas': 'c1', 'x': 600, 'y': 0, 'cols': 5},
    ], ['S1', 'S2'])
    assert out['colsBefore'] == '', 'a mixed selection shows the blank field: %r' % out
    assert out['current'] == out['ids']['S1'], out
    assert out['colsAfter'] == '3', out


def test_selection_on_another_canvas_is_untouched_by_the_delete(page):
    out = _delete_with(page, [
        {'name': 'S1', 'canvas': 'c1', 'x': 0, 'y': 0},
        {'name': 'S3', 'canvas': 'c2', 'x': 0, 'y': 0},
    ], ['S3'])
    assert out['current'] == out['ids']['S3'], out
    assert out['selected'] == [out['ids']['S3']], out
