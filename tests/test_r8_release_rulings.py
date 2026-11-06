"""The owner's round 8 answers on the v1.5.4 notes.

  * The crowding FIX says "already showed" only for a crowded direct
    output and a multi on a one-circuit output; an overfull multi box is
    new on the pull sheet and the distro sheet.
  * That note reaches older shows, so Opening an older show lists it, as
    a FIX among the ones that were wrong before (the intro counts hold).
  * Power sheets whose labels already fit print as they did; deep stacks
    print their labels larger.
  * Balance holds a hidden screen's multis in place and leaves them out
    of its search.
  * Hiding or showing a screen is refused when it would change a locked
    screen's circuits, in the one locked-screen refusal sentence.
  * Bracket tags come from the distro's own name.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r8_release_rulings.py -v
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


def _older():
    top = _top_entry()
    return top[top.index('OPENING AN OLDER SHOW'):top.index('\nFIXES\n')]


def _fixes():
    top = _top_entry()
    return _flat(top[top.index('\nFIXES\n'):])


def _bullets(section):
    return [_flat(b).strip() for b in re.split(r'\n(?=- )', section) if b.startswith('- ')]


def test_already_showed_covers_only_what_was_already_shown():
    fixes = _fixes()
    assert ('- FIX: The tray and the distro checks now warn you when an output carries more '
            'circuits than it takes.') in fixes
    assert 'already showed these' not in fixes


def test_the_overfull_box_note_is_listed_for_older_shows():
    older = _older()
    bullets = _bullets(older)
    line = ('- FIX (IMPORTANT): A multi box carrying more circuits than it holds gets a note on '
            'the pull sheet and a Crowded line on the distro sheet.')
    assert line in bullets
    # among the ones that were wrong before: after the 80% lines, before
    # the last five
    assert 3 <= bullets.index(line) < len(bullets) - 5
    assert len(bullets) == 20   # the short notes share near-duplicates on a line
    assert all(b.startswith('- CHANGE (IMPORTANT): ') for b in bullets[-5:])


def test_the_overfull_box_note_is_the_apps_own_wording():
    # the pull sheet's note and the distro sheet's Crowded line
    pull = _read(JS, 'app-pull-list.js')
    assert "box.overfull ? `${box.overfull.circuits} circuits on a `" in pull
    assert "+ `${this._fanWord(box.overfull.size)}-circuit output` : ''" in pull
    binder = _read(JS, 'app-binder.js')
    assert "pairs.push(['Crowded', `${ov.label} ${ov.type.name} carries ${ov.circuits} circuits`" in binder


def test_hidden_screens_keep_their_outputs_and_leave_the_loads():
    flat = _flat(_older())
    assert ('- CHANGE (IMPORTANT): Hidden screens keep their multi numbers and outputs reserved, '
            "so no other screen takes them, but they're left out of distro and service loads") in flat


def test_hiding_joins_the_locked_screen_refusal():
    flat = _flat(_top_entry())
    assert 'A change that would repack a locked screen is refused, and the message names the screen.' in flat
    # a half-locked group hides and shows only where no locked circuit changes
    assert ('- CHANGE (IMPORTANT): A group saved half locked in an older show now counts as '
            'locked. You can still hide and show its screens when that doesn\'t change their '
            'circuits, but any other edit waits until you pick Lock or Unlock for the '
            'group.') in flat
    assert "since that doesn't change them" not in flat


def test_the_new_lines_read_plainly():
    top = _top_entry()
    body = top[top.index('\n', top.index('\n') + 1):]
    assert '—' not in body and '–' not in body and ' - ' not in body
    assert 'tail' not in body.lower()
    for word in ('labelled', 'colour', 'centre'):
        assert word not in body.lower()
