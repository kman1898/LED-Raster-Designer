#!/usr/bin/env python3
"""Turn the top entry of src/VERSION.txt into the GitHub release body.

WHY THIS EXISTS
    release.yml used to publish with generate_release_notes: true, which
    builds the body from the COMMIT LIST - so the notes written for users in
    VERSION.txt were thrown away and readers got a wall of commit subjects.
    Replacing that with a hand-maintained RELEASE_NOTES.md fixed the output
    but created a new way to rot: forget to regenerate it and the next
    release ships the previous version's text, silently and plausibly.

    So the release body is generated from VERSION.txt at build time. There is
    one source of truth, and it is the file the changelog already lives in.

WHAT IT GUARANTEES
    --tag makes the build FAIL if the top entry of VERSION.txt is not the
    version being tagged. Shipping v0.12.0 with v0.11.0's notes is exactly
    the mistake this is here to prevent, and a failed build is a much
    cheaper way to find out than a published release.

FORMAT IT EXPECTS (VERSION.txt)
    v0.11.0 - August 8, 2026
    ----------------------------

    SECTION HEADING IN CAPS
    - NEW: One-line summary. Then as much prose as it needs, wrapped and
      indented two spaces.
      - a sub-point, indented two, continued at four
    - FIX (IMPORTANT): ...
    - CHANGE: ...

OUTPUT
    Markdown ordered features first and fixes last, because that is the order
    a release is read in: what did I gain, what changed under me, what got
    fixed. The IMPORTANT fixes are lifted into their own section - they are
    the ones that change figures someone may have already ordered against,
    and they must not be buried among routine fixes.
"""

import argparse
import re
import sys
import textwrap
from pathlib import Path

VERSION_HEADER = re.compile(r"^v(\d[\w.]*) - (.+)$")
# Deliberately NOT anchored with $: real headings carry a lowercase tail
# ("SCREEN GROUPS - one wall, however many cabinet sizes"), and anchoring
# silently matched none of them. Prose cannot match it either way - the run of
# 4+ shouty characters has to come immediately after the first, so "Five
# passes over the new group work" fails on "ive".
SECTION_HEADING = re.compile(r"^[A-Z][A-Z0-9]*[A-Z0-9 ,&/'()-]{4,}")
BULLET = re.compile(r"^- (NEW|FIX|CHANGE)(?: \((IMPORTANT)\))?: (.*)$")

# An area label is only worth printing when it is short enough to read as a
# tag. "SCREEN GROUPS - one wall..." gives "Screen groups"; a heading like
# "FIXES THAT CHANGE NUMBERS ON DRAWINGS YOU ALREADY HAVE" gives nothing,
# which is correct - it describes the section, not the entry's subject.
MAX_AREA = 20


def area_label(heading):
    head = heading.split(" - ")[0].split(",")[0].strip()
    if not head or len(head) > MAX_AREA:
        return None
    return head[0].upper() + head[1:].lower()


def derive_summary(lines):
    """A lede from the first section heading, so CI needs no extra file.

    "SCREEN GROUPS - one wall, however many cabinet sizes" becomes
    "Screen groups: one wall, however many cabinet sizes." A heading with no
    descriptive tail gives nothing, and the notes simply open at the first
    section - better than inventing a sentence.
    """
    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.startswith(("-", " ")):
            continue
        if SECTION_HEADING.match(line) and " - " in line:
            head, tail = line.split(" - ", 1)
            return f"{head[0].upper()}{head[1:].lower()}: {tail.strip()}."
        if SECTION_HEADING.match(line):
            return None
    return None


def parse_entry(lines):
    """Parse one version entry into ordered items.

    Each item keeps its parts IN ORDER - prose, list, prose - because the
    prose after a list is not a footnote, it is the rest of the sentence.
    Flattening it to "all text then all bullets" scrambles the reading order
    (it stranded an "Once grouped:" lead-in from its own list).
    """
    items, section, cur = [], "", None
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        m = BULLET.match(line)
        if m:
            cur = {
                "kind": m.group(1),
                "important": bool(m.group(2)),
                "area": area_label(section),
                "parts": [{"type": "p", "text": m.group(3)}],
            }
            items.append(cur)
        elif line.startswith("  - "):
            if cur is None:
                continue
            if not cur["parts"] or cur["parts"][-1]["type"] != "ul":
                cur["parts"].append({"type": "ul", "items": []})
            cur["parts"][-1]["items"].append(line[4:])
        elif line.startswith("    ") and cur and cur["parts"] \
                and cur["parts"][-1]["type"] == "ul":
            cur["parts"][-1]["items"][-1] += " " + line.strip()
        elif line.startswith("  "):
            if cur is None:
                continue
            if cur["parts"][-1]["type"] == "p":
                cur["parts"][-1]["text"] += " " + line.strip()
            else:
                cur["parts"].append({"type": "p", "text": line.strip()})
        elif SECTION_HEADING.match(line):
            section, cur = line, None
        else:
            cur = None          # section intro prose; not part of any bullet
    return items


def read_top_entry(version_txt):
    lines = Path(version_txt).read_text(encoding="utf-8").splitlines()
    starts = [i for i, l in enumerate(lines) if VERSION_HEADER.match(l)]
    if not starts:
        raise SystemExit(f"{version_txt}: no version entry found")
    first = starts[0]
    end = starts[1] if len(starts) > 1 else len(lines)
    version = VERSION_HEADER.match(lines[first]).group(1)
    return version, lines[first + 2:end]


def wrap(text, indent="", first=None):
    return textwrap.fill(text, width=92, initial_indent=first if first is not None
                         else indent, subsequent_indent=indent,
                         break_long_words=False, break_on_hyphens=False)


def render_item(item):
    out, first = [], True
    for part in item["parts"]:
        if part["type"] == "p":
            if first:
                lead = f'**{item["area"]}** — ' if item["area"] else ""
                out.append(wrap(lead + part["text"], indent="  ", first="- "))
                first = False
            else:
                out.append("")
                out.append(wrap(part["text"], indent="  "))
        else:
            out.extend(wrap(s, indent="    ", first="  - ") for s in part["items"])
    return "\n".join(out)


SECTIONS = [
    ("What's new", "The headline of this release.",
     lambda i: i["kind"] == "NEW"),
    ("Changes worth knowing about",
     "Behaviour that is deliberately different from the last version.",
     lambda i: i["kind"] == "CHANGE"),
    ("Fixes that change numbers on drawings you already have",
     "These correct figures you may have already read off a drawing and "
     "ordered against. Worth a minute before your next show.",
     lambda i: i["kind"] == "FIX" and i["important"]),
    ("Other fixes", "Everything else that was wrong and now is not.",
     lambda i: i["kind"] == "FIX" and not i["important"]),
]

INSTALL = """## Install

**macOS** — download the `.dmg` and drag the app to Applications.

**Windows** — download the `.zip`, extract it, then run `LED Raster Designer.exe`.

SHA-256 checksums for both files are attached as `checksums.txt`.
"""


def build(version, items, summary=None):
    md = [f"# LED Raster Designer v{version}", ""]
    if summary:
        md += [wrap(summary), ""]

    groups = [(title, blurb, [i for i in items if matches(i)])
              for title, blurb, matches in SECTIONS]
    groups = [g for g in groups if g[2]]

    # A patch release is fixes and nothing else, and then "Other fixes"
    # has nothing to be other THAN - it reads as though the real list is
    # somewhere further up the page. Only rename when it stands alone; when
    # the important-fixes section is also present, "other" is doing real work.
    if len(groups) == 1 and groups[0][0] == "Other fixes":
        groups = [("Fixes", "What this release fixes.", groups[0][2])]

    for title, blurb, group in groups:
        md += [f"## {title}", "", wrap(blurb), ""]
        for item in group:
            md += [render_item(item), ""]
    md.append(INSTALL)
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version-file", default="src/VERSION.txt")
    ap.add_argument("--out", default="RELEASE_NOTES.md")
    ap.add_argument("--tag", help="tag being built, e.g. v0.11.0 or 0.11.0. "
                                  "Build fails if VERSION.txt disagrees.")
    ap.add_argument("--summary", help="optional one-paragraph lede")
    args = ap.parse_args()

    version, body = read_top_entry(args.version_file)

    if args.tag:
        want = args.tag.lstrip("v")
        if want != version:
            sys.exit(
                f"REFUSING TO BUILD NOTES: tag is v{want} but the top entry in "
                f"{args.version_file} is v{version}.\n"
                f"The release would have shipped the wrong version's notes. "
                f"Add the v{want} entry to {args.version_file}, or tag v{version}."
            )

    summary = args.summary or derive_summary(body)
    items = parse_entry(body)
    if not items:
        sys.exit(f"REFUSING TO BUILD NOTES: no entries parsed for v{version}. "
                 f"Has the VERSION.txt bullet format changed?")

    Path(args.out).write_text(build(version, items, summary), encoding="utf-8")
    kinds = {}
    for i in items:
        kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
    print(f"wrote {args.out} for v{version}: {len(items)} entries "
          f"({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))})")


if __name__ == "__main__":
    main()
