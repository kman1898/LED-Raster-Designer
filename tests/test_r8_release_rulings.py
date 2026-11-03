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
            'circuits than it takes, like two visible screens on a one-circuit output or a multi '
            'with more circuits than its output has. The pull sheet and the distro sheet already '
            'showed a crowded direct output and a multi on a one-circuit output, and now they '
            'flag a multi box carrying more circuits than it holds too.') in fixes
    assert 'already showed these' not in fixes


def test_the_overfull_box_note_is_listed_for_older_shows():
    older = _older()
    bullets = _bullets(older)
    line = ('- FIX (IMPORTANT): A multi box carrying more circuits than it holds gets a note on '
            'the pull sheet, like 8 circuits on a six-circuit output, and a Crowded line on the '
            'distro sheet.')
    assert line in bullets
    # among the ones that were wrong before: after the first four, before
    # the last six, and the intro still counts them right
    assert 4 <= bullets.index(line) < len(bullets) - 6
    assert len(bullets) == 22   # beta.4 QA: loop backup boxes, CVT4K-S input 2 at 9
    intro = _flat(older[:older.index('\n- ')])
    assert 'The first four come from the new 80% fill' in intro
    assert "the last six change what's listed or what you can do" in intro
    assert all(b.startswith('- CHANGE (IMPORTANT): ') for b in bullets[-6:])


def test_the_overfull_box_note_is_the_apps_own_wording():
    # the pull sheet's note and the distro sheet's Crowded line
    pull = _read(JS, 'app-pull-list.js')
    assert "box.overfull ? `${box.overfull.circuits} circuits on a `" in pull
    assert "+ `${this._fanWord(box.overfull.size)}-circuit output` : ''" in pull
    binder = _read(JS, 'app-binder.js')
    assert "pairs.push(['Crowded', `${ov.label} ${ov.type.name} carries ${ov.circuits} circuits`" in binder


def test_deep_stacks_print_larger():
    fixes = _fixes()
    assert ("Power sheets whose labels already fit print as they did; deep stacks print their "
            "labels larger where there's room.") in fixes
    assert 'Other Power sheets print as they did' not in fixes


def test_tags_come_from_the_distros_own_name():
    fixes = _fixes()
    assert ("- FIX: When a Power sheet has too many multis for their labels to fit beside the "
            "wall, the brackets get short tags and a key on the sheet lists each tag's full name "
            "and length. Tags come from the distro's own name, so B1 is always DISTRO B's "
            "multi 1. Before, the labels were cut to D… or ran into each other.") in fixes


def test_balance_leaves_hidden_screens_multis_alone():
    flat = _flat(_older())
    assert ('- CHANGE (IMPORTANT): Hidden screens keep their multi numbers and outputs reserved, '
            "so no other screen takes them, but they're left out of distro and service loads "
            'everywhere, so the distro and Service sheets match the pull sheet. Balance holds '
            'their multis in place and leaves them out of what it searches.') in flat


def test_hiding_joins_the_locked_screen_refusal():
    flat = _flat(_top_entry())
    assert ('A change that would repack a locked screen is refused, and the message names '
            "the screen: turning 100% rated on or off, changing a distro's system, removing a "
            'distro, plugging in, moving or unplugging a multi, grouping, sharing circuits '
            'through a 2fer or 3fer or removing one, 2fer it or 3fer it, typing a power '
            'setting on a screen grouped with it, or hiding or showing a screen.') in flat
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
