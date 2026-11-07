"""A half tile's WATTS (owner, 2026-10-20): "we can change it to 50% unless
stated otherwise by the panel type in panel library".

A half cabinet draws 50% of the full cabinet's watts - or, where the panel
library has the model's matching half-size variant with watts listed on
both, that half's share of the full model's watts. It used to be area x
1.3 (65%), which read a wall with a half row about 3% heavy. Weight keeps
its own rule (the library's half, else 65% of the full cabinet).

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_half_tile_power.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_rulings_1018_final import page  # noqa: E402,F401 - fixture

CATALOG = {
    'FOO': [
        {'name': 'Foo 3.9 Full Tile', 'width_mm': 500, 'height_mm': 1000, 'pixels_w': 128, 'pixels_h': 256,
         'pitch_mm': 3.9, 'weight_kg': 13.0, 'watts_max': 200},
        {'name': 'Foo 3.9 Half Tile', 'width_mm': 500, 'height_mm': 500, 'pixels_w': 128, 'pixels_h': 128,
         'pitch_mm': 3.9, 'weight_kg': 7.5, 'watts_max': 90},
        # a half with no watts listed: the 50%
        {'name': 'Bar 3.9 Full Tile', 'width_mm': 500, 'height_mm': 1000, 'pixels_w': 128, 'pixels_h': 256,
         'pitch_mm': 3.9, 'weight_kg': 14.0, 'watts_max': 220},
        {'name': 'Bar 3.9 Half Tile', 'width_mm': 500, 'height_mm': 500, 'pixels_w': 128, 'pixels_h': 128,
         'pitch_mm': 3.9, 'weight_kg': 8.0},
    ],
}

POWER_JS = """([catalog, cases]) => {
    const app = window.app;
    const keep = { catalog: app._panelCatalog, flat: app._panelCatalogFlat,
                   wcache: app._halfWeightCache, pcache: app._halfWattsCache };
    const out = [];
    try {
        app._ingestCatalog(catalog);
        for (const c of cases) {
            const l = Object.assign({ id: 900, name: 'H', type: 'screen', columns: 2, rows: 2,
                cabinet_width: 128, cabinet_height: 256, panel_width_mm: 500, panel_height_mm: 1000,
                panel_weight: 13, weight_unit: 'kg', panelWatts: 200 }, c);
            const full = { row: 1, col: 0, width: 128, height: 256, halfTile: 'none' };
            const half = { row: 0, col: 0, width: 128, height: 128, halfTile: 'height' };
            out.push({ full: app.getPanelLoadFactor(l, full), half: app.getPanelLoadFactor(l, half),
                       halfKg: app.getPanelWeightKg(l, half) });
        }
    } finally {
        app._panelCatalog = keep.catalog; app._panelCatalogFlat = keep.flat;
        app._halfWeightCache = keep.wcache; app._halfWattsCache = keep.pcache;
    }
    return out;
}"""


def test_a_half_tile_draws_half_unless_the_library_says_otherwise(page):
    pg, errors = page
    foo, bar, typed = pg.evaluate(POWER_JS, [CATALOG, [
        {},                                  # Foo: its half lists 90 W of 200 W
        {'panel_weight': 14},                # Bar: its half lists no watts
        {'panel_weight': 13.5},              # typed by hand: no model
    ]])
    assert foo['full'] == 1 and bar['full'] == 1 and typed['full'] == 1
    assert foo['half'] == pytest.approx(0.45), foo
    assert bar['half'] == pytest.approx(0.5), bar
    assert typed['half'] == pytest.approx(0.5), typed
    # weight keeps its own rule: the library's half, else 65%
    assert foo['halfKg'] == pytest.approx(7.5), foo
    assert typed['halfKg'] == pytest.approx(0.65 * 13.5), typed
    assert errors == []
