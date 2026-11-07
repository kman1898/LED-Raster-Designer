"""The owner's round 6 answers on the v1.5.4 notes and What's New.

  * The locked-screen refusal lists what the app really refuses: no
    "pasting power settings", which no feature does.
  * Opening an older show lists a half-locked group (now locked), the
    corrected Graphite figures and a 16 A Amperage box, and the hidden
    screens line says they keep their multi numbers and outputs.
  * A distro with only hidden screens is left off the binder too, and a
    service with no distro that prints gets no Service sheet.
  * The FEEDS example is the binder's "Fed from: ..." line.
  * What's New keeps 8 items and has none of the old wording.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r6_release_rulings.py -v
"""

import os
import re

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, '..')
JS = os.path.join(ROOT, 'src', 'static', 'js')
VERSION_TXT = os.path.join(ROOT, 'src', 'VERSION.txt')


def _read(*parts):
    with open(os.path.join(*parts), encoding='utf-8') as f:
        return f.read()


def _entry_160():
    """These rulings are about what 1.6.0 shipped, so they read its entry
    by version, wherever it sits in the file."""
    text = _read(VERSION_TXT)
    starts = [m.start() for m in re.finditer(r'^v\d[\w.]* - ', text, re.M)]
    at = next(i for i, s in enumerate(starts) if text.startswith('v1.6.0 - ', s))
    return text[starts[at]:starts[at + 1]]


def _flat(text):
    return re.sub(r'\s+', ' ', text)


def _older():
    top = _entry_160()
    return top[top.index('OPENING AN OLDER SHOW'):top.index('\nFIXES\n')]


def _bullets(section):
    return [_flat(b).strip() for b in re.split(r'\n(?=- )', section) if b.startswith('- ')]


def test_the_date():
    assert _entry_160().startswith('v1.6.0 - November 6, 2026\n')


def test_the_refusal_lists_only_what_the_app_refuses():
    flat = _flat(_entry_160())
    assert 'pasting power settings' not in flat and 'paste' not in flat.lower()
    # the short notes say the refusal once, without the list of gestures
    assert 'A change that would repack a locked screen is refused, and the message names the screen.' in flat


def test_the_feeder_example_is_the_fed_from_line():
    top = _entry_160()
    feeders = _flat(top[top.index('\nA POWER IN FOR EVERY DISTRO\n'):top.index('\nA START PAGE, THEN A PANEL\n')])
    assert 'The binder says what each distro is powered from' in feeders
    assert "Power in: 50'" not in feeders
    # "feed", never "feeder" (2026-11-01). A pull sheet row only ever said
    # feeder in the 1.5.4 betas, never in a public release, so the notes
    # for 1.6.0 (read against 1.5.3) say nothing about carrying it over.
    assert 'feeder' not in top.lower(), top


def test_opening_an_older_show_lists_the_round_6_changes():
    older = _older()
    bullets = _bullets(older)
    # the short notes: near-duplicates share a line, every count change is still here
    assert len(bullets) == 20, bullets
    assert '80%' in bullets[2] and '16 A breaker · 12.8 A usable' in bullets[2], bullets[2]
    assert all(b.startswith('- CHANGE (IMPORTANT): ') for b in bullets[-6:]), bullets[-6:]
    assert not any(b.startswith('- CHANGE') for b in bullets[:2] + bullets[3:-6])
    flat = _flat(older)
    # (e) the 16 A box, short
    assert ('- CHANGE (IMPORTANT): A screen you set to 16 A in an older show to allow for the '
            '80% rule now reads 16 A breaker · 12.8 A usable. Change it to the breaker size.') in flat
    # (c) hidden screens keep their slots, their loads are left out
    assert ('- CHANGE (IMPORTANT): Hidden screens keep their multi numbers and outputs reserved, '
            "so no other screen takes them, but they're left out of distro and service loads "
            'everywhere') in flat
    # (f) only hidden screens counts as nothing on it, and a service with
    # no distro that prints gets no Service sheet
    assert ('- CHANGE (IMPORTANT): A distro with nothing on it, or only hidden screens, is left '
            'off the binder, and a service with nothing printing on it gets no Service '
            'sheet.') in flat
    # (d) the corrected Graphite figures
    assert 'GP2.6 (4 in 1) half tiles now draw 50% of a full tile instead of 64%.' in flat
    # no panel row by size any more: a screen with no panel name has none
    assert ('GP2.6, GP3.1 and GP3.9 Full Tile screens saved at 8.5 kg no longer match the '
            'library, which now lists 9.0 kg, so their half tiles weigh 65% of a full tile.') in flat
    assert 'print by size' not in flat
    assert 'Pick the panel from the library again to get the new figures.' in flat
    # (b) a half-locked group is locked (round 7: hide and show still work)
    assert ('- CHANGE (IMPORTANT): A group saved half locked in an older show now counts as '
            'locked.') in flat
    assert 'Edits to any of its screens are refused' not in flat


def test_the_graphite_figures_match_the_library():
    """The percentages in the notes are the bundled library's own."""
    import json
    cat = json.loads(_read(ROOT, 'src', 'static', 'data', 'panel_catalog.json'))
    roe = {p['name']: p for p in cat['ROE']}
    full, half = roe['Graphite GP2.6 (4 in 1) Full Tile'], roe['Graphite GP2.6 (4 in 1) Half Tile']
    assert half['watts_max'] / full['watts_max'] == 0.5
    for model in ('GP2.6', 'GP3.1', 'GP3.9'):
        assert roe[f'Graphite {model} Full Tile']['weight_kg'] == 9.0, model


def test_the_notes_read_plainly():
    top = _entry_160()
    body = top[top.index('\n', top.index('\n') + 1):]
    assert '—' not in body and '–' not in body
    assert ' - ' not in body
    assert 'tail' not in body.lower()


def test_whats_new_has_none_of_the_old_wording():
    src = _read(JS, 'whatsnew_content.js')
    entry = src[src.index("'1.6': {"):src.index("'1.5.3': {")]
    assert len(re.findall(r'\{\s*h:', entry)) == 8
    assert 'pasting' not in entry and 'paste' not in entry.lower()
    assert "Feed: 50'" not in entry and 'feeder' not in entry.lower()
