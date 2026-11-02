"""The owner's round 7 answers on the v1.5.4 notes.

  * The FEEDS example prints the service the way the binder does, with
    its size and system: "Fed from: HOUSE · 600 A · 120/208V 3φ · ...".
  * A crowded Power sheet's short bracket tags and key are a FIX.
  * The tray and distro-check warning for an output carrying more circuits
    than it takes is a FIX.
  * A half-locked group still lets you hide and show its screens.
  * Neither new FIX changes a count, so Opening an older show keeps its
    19 lines. (Round 8 adds a 20th, the overfull multi box note, and
    rewords these lines; tests/test_r8_release_rulings.py pins them.)

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r7_release_rulings.py -v
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


def _top_entry():
    text = _read(VERSION_TXT)
    starts = [m.start() for m in re.finditer(r'^v\d[\w.]* - ', text, re.M)]
    return text[starts[0]:starts[1]]


def _flat(text):
    return re.sub(r'\s+', ' ', text)


def _section(start, end):
    top = _top_entry()
    return _flat(top[top.index(start):top.index(end) if end else len(top)])


def test_the_feeder_example_names_the_service_with_its_size():
    feeders = _section('\nPOWER IN\n', '\nTHE PANEL ON EACH SCREEN\n')
    assert "like Powered from: HOUSE · 600 A · 120/208V 3φ · 200 A cam set 100'+50'." in feeders
    # the binder joins the service label and the feeder with " · ", and the
    # service label is "name · size · system"
    services = _read(JS, 'app-services.js')
    assert "return `${s.name || s.id} · ${this.serviceSizeText(s)}`;" in services
    assert "return `${+(Number(s.ratingA) || 0).toFixed(1)} A · ${this.distroSystemName(s)}`;" in services
    assert "[from, text].filter(Boolean).join(' · ')" in _read(JS, 'app-binder.js')


def test_the_crowded_power_sheet_fix():
    fixes = _section('\nFIXES\n', None)
    assert ("- FIX: When a Power sheet has too many multis for their labels to fit beside the "
            "wall, the brackets get short tags and a key on the sheet lists each tag's full name "
            "and length.") in fixes
    assert "Before, the labels were cut to D… or ran into each other." in fixes


def test_the_crowded_output_warning_fix():
    fixes = _section('\nFIXES\n', None)
    assert ("- FIX: The tray and the distro checks now warn you when an output carries more "
            "circuits than it takes, like two visible screens on a one-circuit output or a multi "
            "with more circuits than its output has.") in fixes


def test_a_half_locked_group_still_hides_and_shows():
    older = _section('OPENING AN OLDER SHOW', '\nFIXES\n')
    assert ("- CHANGE (IMPORTANT): A group saved half locked in an older show now counts as "
            "locked. You can still hide and show its screens") in older
    assert "any other edit waits until you pick Lock or Unlock for the group." in older


def test_the_new_lines_change_no_counts():
    top = _top_entry()
    older = top[top.index('OPENING AN OLDER SHOW'):top.index('\nFIXES\n')]
    assert len(re.findall(r'^- ', older, re.M)) == 20   # round 8: the overfull box note
    assert 'short tags' not in older and 'more circuits than it takes' not in older


def test_the_new_lines_read_plainly():
    top = _top_entry()
    body = top[top.index('\n', top.index('\n') + 1):]
    assert '—' not in body and '–' not in body and ' - ' not in body
    assert 'tail' not in body.lower()
