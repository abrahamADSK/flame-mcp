#!/usr/bin/env python3
"""Verify cross-cutting concepts declared in .concepts.yml.

Exit codes:
    0  all invariants passed, OR strict: false (soft-launch mode)
    1  at least one invariant failed AND strict: true

Usage:
    python scripts/verify_concepts.py
    python scripts/verify_concepts.py --verbose
    python scripts/verify_concepts.py --strict           # force strict regardless of YAML

No --fix mode. Verification only. Humans resolve drift.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Local import: scripts/ is not a package; add it to sys.path explicitly.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import yaml  # type: ignore
except ImportError:
    print(
        "[concepts] PyYAML not installed. Run: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)

from invariant_types import INVARIANT_TYPES  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent
CONCEPTS_FILE = REPO_ROOT / ".concepts.yml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify cross-cutting concepts.")
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print passing checks too (default: only failures).",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Force strict mode (non-zero exit on failure) regardless of YAML setting.",
    )
    args = parser.parse_args()

    if not CONCEPTS_FILE.exists():
        print(f"[concepts] no .concepts.yml at {CONCEPTS_FILE} — nothing to check")
        return 0

    data = yaml.safe_load(CONCEPTS_FILE.read_text(encoding="utf-8")) or {}
    concepts = data.get("concepts") or {}
    strict = bool(data.get("strict", False)) or args.strict

    if not concepts:
        print(f"[concepts] registry empty ({CONCEPTS_FILE.name}) — nothing to check")
        return 0

    results: list[tuple[bool, str, str]] = []
    for concept_name, concept in concepts.items():
        invariants = concept.get("invariants") or []
        for i, inv in enumerate(invariants):
            inv_type = inv.get("type")
            inv_id = inv.get("id", f"{concept_name}[{i}]")
            check = INVARIANT_TYPES.get(inv_type)
            if check is None:
                results.append((False, inv_id, f"unknown invariant type: {inv_type}"))
                continue
            try:
                passed, msg = check(inv)
            except Exception as e:
                passed, msg = False, f"EXCEPTION during check: {e}"
            results.append((passed, inv_id, msg))

    failed = [r for r in results if not r[0]]
    total = len(results)
    passed_count = total - len(failed)

    for ok, inv_id, msg in results:
        if ok and not args.verbose:
            continue
        mark = "✓" if ok else "✗"
        print(f"  {mark} {inv_id}: {msg}")

    summary = f"[concepts] {passed_count}/{total} invariants passed"
    print(summary, file=sys.stderr)

    if not failed:
        return 0

    if strict:
        print(
            f"[concepts] STRICT: {len(failed)} drift(s) detected — blocking.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[concepts] SOFT-LAUNCH (strict: false): {len(failed)} drift(s) "
        f"reported but NOT blocking. Flip strict: true in .concepts.yml when ready.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
