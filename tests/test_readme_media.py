"""The README's pictures are all there, all shown, and none left over.

scripts/capture_readme_media.py makes every file in .github/media from the
app itself (OUTPUTS). This pins, without a browser:

  - every .github/media path README.md names exists;
  - every file the script makes is in .github/media, within its size limit
    (the social preview at exactly 1280 x 640);
  - every file in .github/media is one README.md shows, or the social
    preview (set in the repository's settings, not shown in the README),
    so nothing in the folder is left to rot.

A view that changed since the pictures were taken is not caught here: rerun
python scripts/capture_readme_media.py after a release changes the views.
"""

import os
import re
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import capture_readme_media as media  # noqa: E402

README = os.path.join(ROOT, 'README.md')
MEDIA_DIR = os.path.join(ROOT, '.github', 'media')
RERUN = 'run python scripts/capture_readme_media.py'


def _readme_media():
    with open(README, encoding='utf-8') as f:
        text = f.read()
    return set(re.findall(r'\.github/media/([A-Za-z0-9._-]+)', text))


def _png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    assert head[:8] == b'\x89PNG\r\n\x1a\n', f'{path} is not a PNG'
    return struct.unpack('>II', head[16:24])


def test_every_readme_media_path_exists():
    missing = sorted(n for n in _readme_media()
                     if not os.path.isfile(os.path.join(MEDIA_DIR, n)))
    assert not missing, f'README.md shows .github/media files that are not there: {missing}; {RERUN}'


def test_every_output_exists_within_its_limit():
    missing = [n for n in media.OUTPUTS if not os.path.isfile(os.path.join(MEDIA_DIR, n))]
    assert not missing, f'not in .github/media: {missing}; {RERUN}'
    for name in media.OUTPUTS:
        limit = media.GIF_LIMIT if name == media.GIF else media.PNG_LIMIT
        size = os.path.getsize(os.path.join(MEDIA_DIR, name))
        assert size <= limit, f'{name} is {size:,} bytes, over {limit:,}'
    assert _png_size(os.path.join(MEDIA_DIR, media.SOCIAL)) == media.SOCIAL_SIZE


def test_readme_shows_every_output_but_the_social_preview():
    unshown = sorted(set(media.OUTPUTS) - _readme_media() - {media.SOCIAL})
    assert not unshown, f'README.md does not show {unshown}'


def test_nothing_in_the_media_folder_is_orphaned():
    shown = _readme_media() | {media.SOCIAL}
    present = set(os.listdir(MEDIA_DIR)) if os.path.isdir(MEDIA_DIR) else set()
    orphans = sorted(present - shown)
    assert not orphans, (f'.github/media holds files README.md does not show: {orphans}; '
                         'remove them or show them')
    strays = sorted(present - set(media.OUTPUTS))
    assert not strays, (f'.github/media holds files capture_readme_media.py does not make: '
                        f'{strays}; add them to its OUTPUTS or remove them')
