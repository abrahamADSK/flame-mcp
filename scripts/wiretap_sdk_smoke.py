#!/usr/bin/env python3
"""Smoke test for the Wiretap Python SDK shipped with Autodesk Flame 2026.

Purpose
-------
Phase F2.wt of the chat 51 performance plan. We need *behaviour* evidence for
the Wiretap SDK so concept_map.py can dispatch SDK operations deterministically.
The companion bash script (``wiretap_smoke.sh``) covers the 37 CLI binaries;
this script probes the Python SDK symbols and runs a tiny non-destructive
connection sequence.

What it does
------------
1. Add the Flame-embedded SDK path to ``sys.path``.
2. ``import libwiretapPythonClientAPI as WT``.
3. Enumerate top-level symbols (callable + classes + constants).
4. Run a minimal read-only sequence::

       WT.WireTapClientInit()
       server = WT.WireTapServerHandle('localhost')
       root   = WT.WireTapNodeHandle(server, '/')
       n      = root.getNumChildren()
       WT.WireTapClientUninit()

   Every step is wrapped in try/except so a failure at step N still reports
   results for steps 1..N-1.

Outputs
-------
- **stdout**: structured JSON (one object). Pipe to ``jq`` or capture from
  the bash smoke script. This is what gets embedded in the markdown report.
- **stderr**: human-readable summary lines (one per step).

Exit codes
----------
- 0 — SDK imported and at least the symbol enumeration succeeded.
- 2 — SDK not found on disk (operator hint: run on a Flame workstation).
- 3 — Found on disk but import failed (rare; usually a Python version mismatch).

Safe to run on a non-Flame machine: it detects the missing SDK and exits 2.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Where the Flame-embedded Python ships the Wiretap SDK. Override with the
#: ``WIRETAP_SDK_PATH`` env var if Autodesk moves it in a future release.
SDK_PATH = os.environ.get(
    "WIRETAP_SDK_PATH",
    "/opt/Autodesk/python/2026.2.2/lib/python3.11/site-packages",
)

#: Module name exported by the SDK.
MODULE_NAME = "libwiretapPythonClientAPI"

#: Wiretap host for the connection probe. Localhost is the only address that
#: is guaranteed to be safe; the SDK does not mutate anything on a bare
#: ``getNumChildren()`` of ``/``.
WT_HOST = os.environ.get("WIRETAP_HOST", "localhost")


# ---------------------------------------------------------------------------
# Step helpers — each returns (ok, value_or_error)
# ---------------------------------------------------------------------------


def _step(name: str, fn) -> dict[str, Any]:
    """Run a single probe step and return a structured record.

    Parameters
    ----------
    name:
        Human label for the step (also used as JSON key).
    fn:
        Zero-arg callable performing the step. Return value is captured under
        ``value``; exceptions are caught and stringified under ``error``.

    Returns
    -------
    dict
        ``{"step": name, "ok": bool, "value": ..., "error": ..., "ms": int}``.
    """
    t0 = time.monotonic()
    try:
        value = fn()
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        print(f"[ok]   {name} -> {value!r} ({elapsed_ms} ms)", file=sys.stderr)
        return {"step": name, "ok": True, "value": repr(value), "ms": elapsed_ms}
    except Exception as exc:  # noqa: BLE001 — we want every failure captured.
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        msg = f"{type(exc).__name__}: {exc}"
        print(f"[fail] {name} -> {msg} ({elapsed_ms} ms)", file=sys.stderr)
        return {"step": name, "ok": False, "error": msg, "ms": elapsed_ms}


def enumerate_symbols(module) -> list[str]:
    """Return a sorted list of public symbols exported by ``module``."""
    return sorted(name for name in dir(module) if not name.startswith("_"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: PLR0915 — linear narrative is clearer than splitting.
    result: dict[str, Any] = {
        "sdk_path": SDK_PATH,
        "module": MODULE_NAME,
        "host": WT_HOST,
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "ok": False,
        "skip_reason": None,
        "symbols": [],
        "steps": [],
    }

    # 1. Check the SDK directory exists on disk. We don't try to import if it
    #    doesn't — that just spams a stack trace for an obvious "not on a
    #    Flame box" case.
    if not os.path.isdir(SDK_PATH):
        result["skip_reason"] = (
            f"SDK path not found: {SDK_PATH} "
            "(run this on a Flame workstation, or set WIRETAP_SDK_PATH)"
        )
        print(json.dumps(result, indent=2))
        print(f"[skip] {result['skip_reason']}", file=sys.stderr)
        return 2

    if SDK_PATH not in sys.path:
        sys.path.insert(0, SDK_PATH)

    # 2. Import the SDK.
    try:
        WT = __import__(MODULE_NAME)
    except Exception as exc:  # noqa: BLE001
        result["skip_reason"] = (
            f"import {MODULE_NAME} failed: {type(exc).__name__}: {exc}"
        )
        print(json.dumps(result, indent=2))
        print(f"[fail] {result['skip_reason']}", file=sys.stderr)
        return 3

    # 3. Enumerate symbols.
    symbols = enumerate_symbols(WT)
    result["symbols"] = symbols
    result["symbol_count"] = len(symbols)
    print(f"[ok]   imported {MODULE_NAME} ({len(symbols)} symbols)", file=sys.stderr)

    # 4. Tiny non-destructive sequence. We bind intermediate handles to
    #    closure variables so later steps can reference them. State lives in
    #    a small dict to keep _step purely functional.
    state: dict[str, Any] = {}

    def _init():
        return WT.WireTapClientInit()

    def _server():
        state["server"] = WT.WireTapServerHandle(WT_HOST)
        return state["server"]

    def _root():
        state["root"] = WT.WireTapNodeHandle(state["server"], "/")
        return state["root"]

    def _num_children():
        # The SDK exposes getNumChildren(out_int). It writes the count into
        # an int reference and returns a bool. We tolerate either signature.
        node = state["root"]
        # Newer pattern: int holder via WireTapInt.
        try:
            n_holder = WT.WireTapInt(0)
            ok = node.getNumChildren(n_holder)
            return {"ok": bool(ok), "n": int(n_holder)}
        except Exception:  # noqa: BLE001
            # Some bindings return the count directly.
            return node.getNumChildren()

    def _uninit():
        return WT.WireTapClientUninit()

    result["steps"].append(_step("WireTapClientInit", _init))
    result["steps"].append(_step("WireTapServerHandle", _server))
    result["steps"].append(_step("WireTapNodeHandle('/')", _root))
    result["steps"].append(_step("getNumChildren", _num_children))
    result["steps"].append(_step("WireTapClientUninit", _uninit))

    # 5. Final verdict — ok if every step succeeded.
    result["ok"] = all(s["ok"] for s in result["steps"])

    print(json.dumps(result, indent=2))
    summary = "ok" if result["ok"] else "partial"
    print(
        f"[done] {summary}: {sum(s['ok'] for s in result['steps'])}/"
        f"{len(result['steps'])} steps succeeded",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
