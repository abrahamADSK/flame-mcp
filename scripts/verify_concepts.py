#!/usr/bin/env python3
"""Verify cross-cutting concepts declared in .concepts.yml.

Exit codes:
    0  all invariants passed, OR strict: false (soft-launch mode),
       OR --accept-current-as-truth + --i-reviewed-diff (report mode),
       OR the triple-flag WRITER mode (see below).
    1  at least one invariant failed AND strict: true
    2  invalid CLI usage (e.g. only one of the escape-hatch flags given)

Usage:
    python scripts/verify_concepts.py
    python scripts/verify_concepts.py --verbose
    python scripts/verify_concepts.py --strict           # force strict regardless of YAML
    python scripts/verify_concepts.py \\
        --accept-current-as-truth --i-reviewed-diff      # REPORT-ONLY escape hatch
    python scripts/verify_concepts.py \\
        --accept-current-as-truth --i-reviewed-diff --write   # WRITER MODE (Chat 46)

Escape hatch — two modes (Chat 44 REPORT, Chat 46 WRITER)
---------------------------------------------------------
Double flag required for REPORT MODE: both --accept-current-as-truth AND
--i-reviewed-diff must be passed together. The first flag alone errors out.
This avoids accidental drift acceptance.

Triple flag required for WRITER MODE: add --write. Writer mode attempts
to update the declared mirrors so the current code state is accepted as
truth. Only a subset of invariant types have writers implemented (see
WRITERS dict in invariant_types.py — currently tool_count and
review_expiry). For other types, the runner prints "WRITER UNSUPPORTED"
and falls back to the REPORT MODE message for that invariant.

REPORT MODE is read-only, intended for repos that have been abandoned for
months and need a one-shot review before flipping strict: true — the user
runs it, reads the report, and then resolves drift manually.

WRITER MODE is the power tool for routine add-a-tool / refresh-review
flows where the correction is mechanical (bump a count, bump a date).
Review the git diff before committing.

No auto-commit. Writer mode leaves changes in the working tree for the
user to inspect.
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

from invariant_types import INVARIANT_TYPES, WRITERS  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent
CONCEPTS_FILE = REPO_ROOT / ".concepts.yml"


def _describe_would_update(concept_name: str, inv: dict, msg: str) -> str:
    """Return a human-readable "would-update" line for a drifting invariant.

    REPORT MODE is read-only, so this function only describes what an
    eventual writer mode would touch. The granularity is intentionally
    coarse — the mirrors declared in the concept block are named as the
    targets; the user is expected to review the diff manually.

    Parameters
    ----------
    concept_name : str
        Name of the enclosing concept (e.g. 'release_discipline').
    inv : dict
        The invariant entry from .concepts.yml (type, id, and type-specific
        parameters).
    msg : str
        The failure message from the invariant check itself, used as
        ground-truth context in the report line.
    """
    inv_type = inv.get("type", "<unknown>")
    inv_id = inv.get("id", concept_name)

    # Collect declared mirrors for the suggestion (best-effort; YAML may
    # put them inside a_source/b_source/code_file/doc_file/etc.).
    mirrors: list[str] = []
    for key in ("code_file", "doc_file", "file", "path"):
        v = inv.get(key)
        if isinstance(v, str):
            mirrors.append(v)
    for side_key in ("a", "b", "a_source", "b_source", "code_grep"):
        side = inv.get(side_key)
        if isinstance(side, dict):
            for k in ("file", "file_pattern"):
                v = side.get(k)
                if isinstance(v, str) and v not in mirrors:
                    mirrors.append(v)
    mirror_list = ", ".join(mirrors) if mirrors else "<declared mirrors>"
    return (
        f"    {inv_id} [{inv_type}]: {msg} "
        f"→ would update {mirror_list} to match current state"
    )


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
    parser.add_argument(
        "--accept-current-as-truth", action="store_true",
        help=(
            "Escape hatch (requires --i-reviewed-diff). REPORT MODE: describes "
            "what each drifting invariant would need to accept the current "
            "state as truth. Does not write anything. Exits 0 even on drift."
        ),
    )
    parser.add_argument(
        "--i-reviewed-diff", action="store_true",
        help=(
            "Safety partner for --accept-current-as-truth. Both flags must be "
            "passed together; the single-flag form is a CLI error (exit 2)."
        ),
    )
    parser.add_argument(
        "--write", action="store_true",
        help=(
            "WRITER MODE (Chat 46). Requires BOTH escape-hatch flags plus "
            "this flag (triple-flag). For invariants whose type has a "
            "registered writer (tool_count, review_expiry), applies the "
            "correction to disk. Types without a writer fall back to REPORT "
            "behaviour with a 'WRITER UNSUPPORTED' line. No auto-commit — "
            "review `git diff` before committing."
        ),
    )
    args = parser.parse_args()

    # Escape-hatch flag validation: require BOTH or NEITHER (plus --write
    # requires both to be set).
    accept = args.accept_current_as_truth
    reviewed = args.i_reviewed_diff
    write_mode = args.write
    if accept ^ reviewed:
        missing = "--i-reviewed-diff" if accept else "--accept-current-as-truth"
        print(
            f"[concepts] ERROR: --accept-current-as-truth and --i-reviewed-diff "
            f"must be passed together (missing: {missing}). "
            f"This double-flag requirement is intentional — it prevents "
            f"accidental drift acceptance.",
            file=sys.stderr,
        )
        return 2
    if write_mode and not (accept and reviewed):
        print(
            "[concepts] ERROR: --write requires BOTH --accept-current-as-truth "
            "and --i-reviewed-diff (triple-flag mode). Writer mode mutates "
            "files on disk; both safety flags must also be set.",
            file=sys.stderr,
        )
        return 2
    report_mode = accept and reviewed

    if not CONCEPTS_FILE.exists():
        print(f"[concepts] no .concepts.yml at {CONCEPTS_FILE} — nothing to check")
        return 0

    data = yaml.safe_load(CONCEPTS_FILE.read_text(encoding="utf-8")) or {}
    concepts = data.get("concepts") or {}
    strict = bool(data.get("strict", False)) or args.strict

    if not concepts:
        print(f"[concepts] registry empty ({CONCEPTS_FILE.name}) — nothing to check")
        return 0

    # Keep the originating concept name + raw invariant dict alongside the
    # pass/fail tuple so report mode can describe the would-update targets
    # without re-parsing the YAML.
    results: list[tuple[bool, str, str, str, dict]] = []
    for concept_name, concept in concepts.items():
        invariants = concept.get("invariants") or []
        for i, inv in enumerate(invariants):
            inv_type = inv.get("type")
            inv_id = inv.get("id", f"{concept_name}[{i}]")
            check = INVARIANT_TYPES.get(inv_type)
            if check is None:
                results.append((False, inv_id, f"unknown invariant type: {inv_type}", concept_name, inv))
                continue
            try:
                passed, msg = check(inv)
            except Exception as e:
                passed, msg = False, f"EXCEPTION during check: {e}"
            results.append((passed, inv_id, msg, concept_name, inv))

    failed = [r for r in results if not r[0]]
    total = len(results)
    passed_count = total - len(failed)

    for ok, inv_id, msg, _concept_name, _inv in results:
        if ok and not args.verbose:
            continue
        mark = "✓" if ok else "✗"
        print(f"  {mark} {inv_id}: {msg}")

    summary = f"[concepts] {passed_count}/{total} invariants passed"
    print(summary, file=sys.stderr)

    if not failed:
        if report_mode:
            # Report mode is harmless when everything is green — just state it.
            print(
                "[concepts] REPORT MODE — no writes performed",
                file=sys.stderr,
            )
            print(
                "[concepts]   No drift to accept; registry already matches reality.",
                file=sys.stderr,
            )
        return 0

    if report_mode:
        mode_label = "WRITER MODE" if write_mode else "REPORT MODE"
        print(f"[concepts] {mode_label}", file=sys.stderr)

        wrote = 0
        unsupported = 0
        write_failed = 0
        for _ok, inv_id, msg, concept_name, inv in failed:
            inv_type = inv.get("type", "<unknown>")
            if write_mode and inv_type in WRITERS:
                try:
                    ok_w, w_msg = WRITERS[inv_type](inv)
                except Exception as exc:
                    ok_w, w_msg = False, f"writer raised {type(exc).__name__}: {exc}"
                if ok_w:
                    print(f"[concepts]   WROTE {inv_id}: {w_msg}", file=sys.stderr)
                    wrote += 1
                else:
                    print(
                        f"[concepts]   WRITE FAILED {inv_id}: {w_msg} "
                        f"(fallback: manual)",
                        file=sys.stderr,
                    )
                    write_failed += 1
            else:
                if write_mode:
                    print(
                        f"[concepts]   WRITER UNSUPPORTED for type {inv_type!r} "
                        f"[{inv_id}]: resolve manually",
                        file=sys.stderr,
                    )
                    unsupported += 1
                print(
                    _describe_would_update(concept_name, inv, msg),
                    file=sys.stderr,
                )

        if write_mode:
            print(
                f"[concepts] WRITER summary: wrote={wrote}, unsupported={unsupported}, "
                f"failed={write_failed}. Review `git diff` before committing.",
                file=sys.stderr,
            )
        else:
            print(
                f"[concepts]   Would accept {len(failed)} drift(s) as the new truth.",
                file=sys.stderr,
            )
            print(
                "[concepts] Run without flags to verify the current truth sticks "
                "once drift has been resolved manually.",
                file=sys.stderr,
            )
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
