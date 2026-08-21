"""The release body is generated from src/VERSION.txt at build time.

Before this, the body came from `generate_release_notes: true`, which builds
it from the COMMIT LIST - so the notes written for users were discarded and
readers got a wall of commit subjects. Replacing that with a checked-in
RELEASE_NOTES.md fixed the output and created a quieter failure: forget to
regenerate it and the release ships the PREVIOUS version's text, which looks
completely plausible and is wrong.

So there is no checked-in notes file. These tests cover the two ways the
generator could fail silently: dropping entries (a release that under-reports
what changed) and accepting a tag that VERSION.txt disagrees with (a release
that ships the wrong version's notes entirely).
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_release_notes.py"
VERSION_TXT = ROOT / "src" / "VERSION.txt"

sys.path.insert(0, str(ROOT / "scripts"))
import generate_release_notes as gen  # noqa: E402


def run(tmp_path, *args, version_file=None):
    out = tmp_path / "NOTES.md"
    cmd = [sys.executable, str(SCRIPT), "--out", str(out),
           "--version-file", str(version_file or VERSION_TXT), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return proc, out


def top_version():
    return gen.read_top_entry(VERSION_TXT)[0]


# ── The guard that stops the wrong version's notes shipping ───────────────

def test_refuses_a_tag_that_version_txt_disagrees_with(tmp_path):
    proc, out = run(tmp_path, "--tag", "v99.99.99")
    assert proc.returncode != 0, (
        "generator accepted a tag VERSION.txt knows nothing about - the "
        "release would have shipped the wrong version's notes")
    assert "REFUSING TO BUILD NOTES" in (proc.stdout + proc.stderr)
    assert not out.exists(), "wrote notes despite refusing"


def test_accepts_the_matching_tag(tmp_path):
    version = top_version()
    for tag in (f"v{version}", version):          # with and without the v
        proc, out = run(tmp_path, "--tag", tag)
        assert proc.returncode == 0, proc.stderr
        assert out.read_text().startswith(f"# LED Raster Designer v{version}")


def test_a_prerelease_tag_ships_its_base_versions_notes(tmp_path):
    """v0.12.0-beta.1 IS v0.12.0, offered early - there is no separate beta
    changelog to ship, so only the base version has to match. A different
    BASE still refuses (the guard's whole point), which the wrong-tag test
    above already pins with a version no entry carries."""
    version = top_version()
    proc, out = run(tmp_path, "--tag", f"v{version}-beta.1")
    assert proc.returncode == 0, proc.stderr
    assert out.read_text().startswith(f"# LED Raster Designer v{version}")


def test_refuses_a_version_file_with_no_entries(tmp_path):
    empty = tmp_path / "VERSION.txt"
    empty.write_text("LED RASTER DESIGNER - VERSION HISTORY\n===\n\n")
    proc, _ = run(tmp_path, version_file=empty)
    assert proc.returncode != 0
    assert "no version entry" in (proc.stdout + proc.stderr)


# ── No entry may be dropped ──────────────────────────────────────────────

def test_every_entry_in_version_txt_reaches_the_notes(tmp_path):
    """The failure this is really guarding: a parser change quietly drops
    entries and the release under-reports what shipped. Nothing else would
    notice - the notes would still look complete."""
    version, body = gen.read_top_entry(VERSION_TXT)
    expected = [l for l in body if gen.BULLET.match(l)]
    proc, out = run(tmp_path, "--tag", version)
    assert proc.returncode == 0, proc.stderr

    text = out.read_text()
    rendered = len(re.findall(r"^- ", text, re.M))
    assert rendered == len(expected), (
        f"{len(expected)} entries in VERSION.txt but {rendered} in the notes")

    # and each one is present by its opening words, not merely by count
    for line in expected:
        opening = gen.BULLET.match(line).group(3)[:38]
        flat = " ".join(text.split())
        assert " ".join(opening.split()) in flat, f"entry missing: {opening!r}"


def test_sections_are_features_first_fixes_last(tmp_path):
    """Uses a fixed sample, NOT the live VERSION.txt. Asserting against
    whatever happens to be at the top made this fail the moment a patch
    release (fixes only, no "What's new") landed there - the test was
    tracking today's release shape instead of the ordering rule."""
    vf = tmp_path / "VERSION.txt"
    vf.write_text(SAMPLE)                       # NEW + CHANGE + both FIX kinds
    proc, out = run(tmp_path, "--tag", "9.9.9", version_file=vf)
    assert proc.returncode == 0, proc.stderr
    headings = re.findall(r"^## (.+)$", out.read_text(), re.M)
    assert headings[0] == "What's new"
    assert headings[-1] == "Install"
    assert headings.index("Changes worth knowing about") < headings.index(
        "Fixes that change numbers on drawings you already have")
    # the fixes that change existing drawings must precede the routine ones
    assert headings.index(
        "Fixes that change numbers on drawings you already have") \
        < headings.index("Other fixes")


def test_the_live_version_txt_still_generates(tmp_path):
    """Whatever shape the current top entry is, it must produce notes."""
    proc, out = run(tmp_path, "--tag", top_version())
    assert proc.returncode == 0, proc.stderr
    headings = re.findall(r"^## (.+)$", out.read_text(), re.M)
    assert headings, "no sections rendered"
    assert headings[-1] == "Install"


# ── Ordering inside an entry ─────────────────────────────────────────────

SAMPLE = """v9.9.9 - January 1, 2099
----------------------------

SCREEN GROUPS - one wall, however many cabinet sizes

- NEW: Lead sentence. Once grouped:
  - first sub point
    continued on the next line
  - second sub point
  Trailing prose that belongs AFTER the list.

- FIX (IMPORTANT): Something that changes numbers.

- CHANGE: Something deliberately different.

FIXES THAT CHANGE NUMBERS ON DRAWINGS YOU ALREADY HAVE

Intro prose that is not a bullet and must not become one.

- FIX: An ordinary fix.
"""


def test_prose_after_a_list_stays_after_the_list(tmp_path):
    """A bullet's parts must keep their order. Flattening to "all prose then
    all sub-points" stranded an "Once grouped:" lead-in from its own list."""
    vf = tmp_path / "VERSION.txt"
    vf.write_text(SAMPLE)
    proc, out = run(tmp_path, "--tag", "9.9.9", version_file=vf)
    assert proc.returncode == 0, proc.stderr
    text = out.read_text()
    assert text.index("Once grouped") < text.index("first sub point")
    assert text.index("second sub point") < text.index("Trailing prose")
    assert "continued on the next line" in " ".join(text.split())


def test_section_intro_prose_does_not_become_an_entry(tmp_path):
    vf = tmp_path / "VERSION.txt"
    vf.write_text(SAMPLE)
    proc, out = run(tmp_path, "--tag", "9.9.9", version_file=vf)
    assert proc.returncode == 0, proc.stderr
    assert len(re.findall(r"^- ", out.read_text(), re.M)) == 4


def test_area_label_only_when_it_reads_as_a_tag():
    # short heading -> label; long heading -> none, rather than a mouthful
    assert gen.area_label("SCREEN GROUPS - one wall, however many") == "Screen groups"
    assert gen.area_label("PORT MAPPING") == "Port mapping"
    assert gen.area_label(
        "FIXES THAT CHANGE NUMBERS ON DRAWINGS YOU ALREADY HAVE") is None


def test_headings_with_a_lowercase_tail_are_still_headings():
    """Anchoring this pattern with $ silently matched no real heading, which
    cost every area label without failing anything."""
    assert gen.SECTION_HEADING.match("SCREEN GROUPS - one wall, however many")
    assert gen.SECTION_HEADING.match("EXPORT, AND THE APP OPENING IN A BROWSER")
    assert not gen.SECTION_HEADING.match("Five passes over the group work")
    assert not gen.SECTION_HEADING.match("These were found by going back over")


def test_no_checked_in_release_notes_file():
    """A checked-in copy is the thing this replaced; if one comes back it will
    be stale within a release and nothing else will say so."""
    tracked = subprocess.run(["git", "ls-files", "RELEASE_NOTES.md"],
                             capture_output=True, text=True, cwd=ROOT).stdout
    assert not tracked.strip(), (
        "RELEASE_NOTES.md is tracked again - the release body is generated "
        "from src/VERSION.txt, so a checked-in copy can only go stale")


# ── A patch release is fixes and nothing else ────────────────────────────

PATCH_ONLY = """v9.9.9 - January 1, 2099
----------------------------

- FIX: One thing that was wrong.

- FIX: Another thing that was wrong.
"""

MIXED = """v9.9.9 - January 1, 2099
----------------------------

- FIX (IMPORTANT): A figure on your drawing changed.

- FIX: Something ordinary.
"""


def test_a_fixes_only_release_does_not_say_other_fixes(tmp_path):
    """"Other fixes" has nothing to be other THAN on a patch release, and
    reads as though the real list is somewhere further up the page."""
    vf = tmp_path / "VERSION.txt"
    vf.write_text(PATCH_ONLY)
    proc, out = run(tmp_path, "--tag", "9.9.9", version_file=vf)
    assert proc.returncode == 0, proc.stderr
    text = out.read_text()
    assert "## Fixes" in text
    assert "## Other fixes" not in text
    assert "Everything else that was wrong" not in text


def test_other_fixes_survives_when_it_is_doing_real_work(tmp_path):
    """With the important-fixes section present, "other" distinguishes the
    two - renaming there would lose that."""
    vf = tmp_path / "VERSION.txt"
    vf.write_text(MIXED)
    proc, out = run(tmp_path, "--tag", "9.9.9", version_file=vf)
    assert proc.returncode == 0, proc.stderr
    text = out.read_text()
    assert "## Other fixes" in text
    assert "## Fixes that change numbers on drawings you already have" in text
