#!/usr/bin/env python
"""Tune the vis-network force-directed layout in a graphify graph.html to
reduce edge crossings without changing the organic look.

Stronger repulsion + longer/softer springs + far more stabilization
iterations => the layout spreads out and settles with fewer crossings.

Robust: regex-patches each physics key by name (any current value), so it
survives graphify regenerations and is safe to run in CI after `export html`.

Usage: graphify_relayout.py <graph.html> [<graph.html> ...]
"""
import sys
import re
from pathlib import Path

# key -> (regex capturing "key:" prefix, replacement value)
TUNE = [
    (r"(gravitationalConstant:\s*)-?[0-9.]+", r"\g<1>-140"),   # was -60: stronger repulsion
    (r"(centralGravity:\s*)[0-9.]+",          r"\g<1>0.008"),  # gentle pull to center
    (r"(springLength:\s*)[0-9.]+",            r"\g<1>240"),    # was 120: longer edges
    (r"(springConstant:\s*)[0-9.]+",          r"\g<1>0.045"),  # was 0.08: softer
    (r"(avoidOverlap:\s*)[0-9.]+",            r"\g<1>1"),      # was 0.8: no node overlap
    (r"(stabilization:\s*\{\s*iterations:\s*)[0-9]+", r"\g<1>1200"),  # was 200: settle harder
]


def main() -> int:
    rc = 0
    for path in sys.argv[1:]:
        p = Path(path)
        if not p.exists():
            print(f"{path}: MISSING")
            rc = 1
            continue
        html = p.read_text(encoding="utf-8")
        applied = 0
        for pat, rep in TUNE:
            html, c = re.subn(pat, rep, html, count=1)
            applied += c
        p.write_text(html, encoding="utf-8")
        print(f"{path}: {applied}/{len(TUNE)} layout params tuned")
        if applied < len(TUNE):
            rc = 1  # template drifted — caller should look
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
