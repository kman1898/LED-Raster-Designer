"""Frame rates offered = frame rates the processor actually publishes.

The list used to be a fixed 19 rates, narrowed only by "<= 120 Hz for Armor".
NovaStar publish no figure at 48, 72, 100, 150, 180, 192 or 200 Hz, so picking
one made lookupPortCapacity INTERPOLATE between the neighbouring published
rows. Capacity runs as 1/fps, so a straight line between two points on that
curve always sits ABOVE it:

    novastar-armor 10-bit @ 100 Hz   interpolated 219,908   true 197,917   +11.1%
    novastar-armor 10-bit @  72 Hz   interpolated 296,875   true 274,884   +8.0%

Overstated capacity under-counts ports, which is the direction that leaves a
crew short on site. Brompton was never affected - its published table already
covers every rate the control offers.

Run locally:
    python -m pytest tests/test_frame_rate_options.py -v --browser chromium
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    return pg


def _options_for(page, processor_type, frame_rate=60):
    """Rebuild the control for one processor and read back what it offers."""
    return page.evaluate("""([proc, fr]) => {
        const a = window.app;
        const saved = { layer: a.currentLayer };
        a.currentLayer = Object.assign({}, a.project.layers[0] || {},
            { id: 9901, type: 'screen', processorType: proc, frameRate: fr });
        try {
            a.updateFrameRateOptions();
            const sel = document.getElementById('frame-rate');
            return {
                offered: Array.from(sel.options).map(o => Number(o.value)),
                selected: Number(sel.value),
                layerRate: a.currentLayer.frameRate,
            };
        } finally {
            a.currentLayer = saved.layer;
        }
    }""", [processor_type, frame_rate])


# ── the rates that used to interpolate are simply not offerable ───────────

@pytest.mark.parametrize('rate', [48, 72, 100, 150, 180, 192, 200])
def test_novastar_never_offers_a_rate_it_publishes_no_figure_for(page, rate):
    for proc in ('novastar-armor', 'novastar-coex-1g', 'novastar-5g'):
        offered = _options_for(page, proc)['offered']
        assert rate not in offered, (
            f'{proc} offers {rate} Hz, which it publishes no figure for - '
            f'the capacity would be interpolated and overstated')


def test_brompton_keeps_every_rate_because_its_table_covers_them(page):
    offered = _options_for(page, 'brompton')['offered']
    for rate in (48, 72, 100, 150, 180, 192, 200, 250):
        assert rate in offered, f'brompton lost {rate} Hz, which it publishes'


def test_the_drop_frame_rates_survive(page):
    """23.976 / 29.97 / 59.94 round onto published 24 / 30 / 60 rows, and each
    is SLOWER than the row it borrows - so the published figure understates
    them, which costs ports rather than saving them."""
    for proc in ('novastar-armor', 'novastar-5g', 'brompton', 'megapixel-1g'):
        offered = _options_for(page, proc)['offered']
        for rate in (23.976, 29.97, 59.94):
            assert rate in offered, f'{proc} lost {rate} Hz'


def test_every_offered_rate_resolves_without_interpolation(page):
    """The real guard: whatever is offered must hit a published row exactly."""
    mismatches = page.evaluate("""() => {
        const a = window.app;
        const out = [];
        const procs = Object.keys(a.portCapacityTables || {});
        procs.forEach(proc => {
            const table = a.portCapacityTables[proc];
            const saved = a.currentLayer;
            a.currentLayer = { id: 9902, type: 'screen',
                               processorType: proc, frameRate: 60 };
            try {
                a.updateFrameRateOptions();
                const sel = document.getElementById('frame-rate');
                Array.from(sel.options).map(o => Number(o.value)).forEach(r => {
                    Object.keys(table).forEach(bd => {
                        if (table[bd][Math.round(r)] === undefined) {
                            out.push(proc + ' ' + bd + '-bit @ ' + r + 'Hz');
                        }
                    });
                });
            } finally { a.currentLayer = saved; }
        });
        return out;
    }""")
    assert mismatches == [], (
        'these offered rates have no published row and would interpolate: '
        + ', '.join(mismatches))


# ── an existing project on a rate that is no longer offerable ─────────────

def test_an_unsupported_rate_falls_back_to_the_next_one_DOWN(page):
    """Owner's rule: a processor topping out at 60 asked for 72 or 120 lands
    on 60. The processor cannot run the faster rate, so the screen is really
    running a slower one and the published figure for THAT rate is the truth."""
    got = _options_for(page, 'novastar-armor', frame_rate=100)
    assert got['selected'] == 60, got
    assert got['layerRate'] == 60, 'the layer itself was not moved'


def test_the_fallback_does_not_jump_to_a_flat_default(page):
    """It used to snap to 60 regardless. A 240 Hz Armor screen dropping four
    rows to 60 would QUADRUPLE its pixels-per-port."""
    got = _options_for(page, 'novastar-armor', frame_rate=240)
    assert got['selected'] == 120, got
    assert got['layerRate'] == 120


def test_a_supported_rate_is_left_alone(page):
    for proc, rate in (('novastar-5g', 144), ('brompton', 100), ('brompton', 250)):
        got = _options_for(page, proc, frame_rate=rate)
        assert got['selected'] == rate, (proc, rate, got)
        assert got['layerRate'] == rate


def test_a_rate_below_every_published_row_takes_the_lowest(page):
    got = _options_for(page, 'novastar-armor', frame_rate=12)
    assert got['selected'] == min(got['offered']), got


def test_an_unknown_processor_does_not_empty_the_control(page):
    got = _options_for(page, 'not-a-real-processor')
    assert len(got['offered']) > 0, 'the control was emptied and the user stranded'
