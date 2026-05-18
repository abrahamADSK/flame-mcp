#!/usr/bin/env python3
"""
check_adversarial_count.py
==========================
F6a precondition gate.

The chat 51 performance + reliability plan declares phase F6a (trim
CLAUDE.md) as BLOCKED until the golden dataset contains an adversarial
sub-set large enough to catch the hallucinations that the rules in
CLAUDE.md are designed to prevent. This script is that gate.

Usage::

    python scripts/check_adversarial_count.py

Exit codes
----------
0 — dataset has at least :data:`MIN_ADVERSARIAL` entries tagged
    ``"adversarial"`` AND every adversarial entry carries a non-empty
    ``must_not_contain`` list.
1 — dataset is missing, malformed, or fails one of the checks above.
    Failing detail is written to stderr.

The gate is intentionally minimal: no third-party deps, no project
imports, no side effects. It can be wired into a pre-commit hook or a
CI step without altering the rest of the test suite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Default location of the dataset relative to this script.
GOLDEN = (
    Path(__file__).resolve().parent.parent / "tests" / "golden" / "flame_queries.jsonl"
)

# Minimum number of adversarial entries required before F6a may start.
MIN_ADVERSARIAL = 10


def _load_entries(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts; preserve insertion order."""
    entries: list[dict] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(
                f"BLOCKED: {path}:{lineno} is not valid JSON ({exc})",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
    return entries


def main() -> int:
    """Return 0 if the gate passes, 1 otherwise. See module docstring."""
    if not GOLDEN.exists():
        print(f"BLOCKED: {GOLDEN} not found", file=sys.stderr)
        return 1

    entries = _load_entries(GOLDEN)
    adversarial = [e for e in entries if "adversarial" in e.get("tags", [])]
    missing = [e.get("id", "?") for e in adversarial if not e.get("must_not_contain")]

    if len(adversarial) < MIN_ADVERSARIAL:
        print(
            f"BLOCKED: only {len(adversarial)} adversarial queries "
            f"(need at least {MIN_ADVERSARIAL})",
            file=sys.stderr,
        )
        return 1

    if missing:
        print(
            "BLOCKED: adversarial entries missing must_not_contain: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(adversarial)} adversarial queries with must_not_contain")
    return 0


if __name__ == "__main__":
    sys.exit(main())
