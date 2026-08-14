#!/usr/bin/env python3
"""Command-line front end for the SCR exporter.

The mapping itself lives in src/scr_project.py because the app exports through
it too - keeping one implementation means the Export button and this script
cannot drift apart about what a canvas maps to.

    python3 tools/scr_export.py --url http://localhost:8061 --out wall.scr
    python3 tools/scr_export.py --project saved.json --out wall.scr
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from scr_project import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
