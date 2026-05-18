#!/usr/bin/env python3
"""
introspect_flame_api.py
=======================
Walk the live ``flame`` Python module exposed by Autodesk Flame and emit a
structured JSON description of its module attributes, free functions and
classes (with methods + attributes). The output becomes the source of truth
for downstream consumers that need to know which symbols actually exist at
runtime — never what a docstring or a chat transcript *claims* exists.

Operational requirement
-----------------------
The ``flame`` module is ONLY importable inside Flame's embedded Python
interpreter. This script therefore CANNOT run in CI or from a normal
system Python.

Two supported run modes:
  1. Inside Flame's Python (e.g. via the Workspace > Python console, or
     by exec'ing the file from a Flame hook).
  2. Via the ``execute_python`` MCP tool exposed by flame-mcp, which
     forwards the script body to the bridge running inside Flame.

If executed outside Flame, ``import flame`` fails and the script exits
with code 2 and a clear message — see ``--check``.

Cadence
-------
Re-run once per Flame major release (e.g. 2026.x -> 2027.x). Commit the
regenerated ``rag/api_graph.json`` alongside the code change that bumps
the supported Flame version. Patch releases (2026.2.1 -> 2026.2.2) rarely
change the Python API surface; rerunning is optional but cheap.

Consumers downstream
--------------------
- **F3a — concept_map bypass**: ``src/flame_mcp/concept_map.py`` will be
  auto-extended from the JSON so the curated table never claims a method
  that no longer exists in the running Flame.
- **F4b — AST dry-run walker**: the AST validator will load this JSON to
  reject ``execute_python`` snippets that reference unknown attributes or
  call methods with the wrong arity, before any code is shipped to the
  bridge.
- **F5b (Ruta A) — structured plan output schema**: the JSON shape feeds
  the JSON-Schema that the LLM emits when producing structured plans, so
  the schema mirrors reality 1:1.

Usage
-----
    python scripts/introspect_flame_api.py                # writes rag/api_graph.json
    python scripts/introspect_flame_api.py --check        # exit 2 if flame missing
    python scripts/introspect_flame_api.py --output X.json

Design notes
------------
- ``dir(flame)`` is walked; classes found there are introspected one extra
  level (methods + attributes). Instances of those classes are NEVER
  recursed into — we describe the static API surface only.
- Dunder names (``__foo__``) are skipped except for ``__doc__`` and
  ``__bases__`` which are useful to consumers.
- Every introspection step is wrapped in ``try/except`` because Flame's
  Python bindings are Boost.Python / pybind11 wrappers around C++; broken
  ``__getattr__`` / ``inspect.signature`` failures are common. We prefer
  a partial graph with ``"signature": "unknown"`` markers over a crash.
- The ``notes`` array on each function/method is a curated set of trap
  hints (e.g. ``schedule_idle_event``-required, name-attribute coercion)
  derived from CLAUDE.md's "Common API traps" section. The heuristic
  errs on the side of empty: false positives would mislead the LLM.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "rag" / "api_graph.json"

# Dunders we want to keep when walking attribute names.
_KEEP_DUNDERS: frozenset[str] = frozenset({"__doc__", "__bases__"})

# Curated trap hints. Each tuple is (substring_to_match, note_to_emit).
# The substring is matched (case-insensitive) against either the symbol
# name or its docstring. We keep this small and explicit on purpose —
# false positives are worse than missed hints.
_TRAP_HINTS: tuple[tuple[str, str], ...] = (
    ("render", "Wrap blocking renders in flame.schedule_idle_event(...) to avoid freezing the UI."),
    ("export", "PyExporter().export() must be wrapped in flame.schedule_idle_event(...). Never poll."),
    ("clear", "Container .clear() methods can crash Flame; prefer flame.delete(child) per item."),
    ("selection", "flame.selection does NOT exist. Use flame.media_panel.selected_entries."),
)

# Exit codes (kept stable for shell callers).
EXIT_OK = 0
EXIT_FLAME_MISSING = 2
EXIT_WRITE_ERROR = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_getattr(obj: Any, name: str) -> Any:
    """Return ``getattr(obj, name)`` or ``None`` on any exception.

    Flame's Boost.Python bindings sometimes raise unexpected errors for
    perfectly normal attribute reads (broken ``__getattr__`` chains on
    deprecated objects, properties that hit the database, etc.). Never
    let those abort the whole walk.
    """
    try:
        return getattr(obj, name)
    except Exception:
        return None


def _safe_signature(obj: Any) -> str:
    """Return a printable signature or ``"unknown"`` on failure.

    Most C-implemented bindings raise ``ValueError`` from
    ``inspect.signature``. A small fraction raise ``TypeError`` (e.g.
    builtins). We catch everything and fall back to the literal string
    ``"unknown"`` so downstream tools can treat it as a sentinel.
    """
    try:
        return f"{obj.__name__}{inspect.signature(obj)}"
    except (TypeError, ValueError):
        # Last-ditch fallback: at least give the name if we have one.
        name = _safe_getattr(obj, "__name__")
        return f"{name}(...)" if name else "unknown"
    except Exception:
        return "unknown"


def _safe_doc(obj: Any) -> str:
    """Return a trimmed docstring or empty string."""
    try:
        doc = inspect.getdoc(obj)
    except Exception:
        doc = None
    if not doc:
        return ""
    # Cap docstring length to keep the JSON manageable.
    doc = doc.strip()
    return doc if len(doc) <= 800 else doc[:800] + "..."


def _trap_notes(name: str, doc: str) -> list[str]:
    """Return curated note strings triggered by name or docstring."""
    notes: list[str] = []
    haystack = f"{name} {doc}".lower()
    for needle, note in _TRAP_HINTS:
        if needle in haystack and note not in notes:
            notes.append(note)
    return notes


def _is_visible(name: str) -> bool:
    """Return True for names that should appear in the graph.

    Skip dunders except a small allowlist. Keep single-underscore names
    (Flame surfaces some as semi-public).
    """
    if name.startswith("__") and name.endswith("__"):
        return name in _KEEP_DUNDERS
    return True


# ---------------------------------------------------------------------------
# Introspection core
# ---------------------------------------------------------------------------

def _describe_class(cls: Any) -> dict[str, Any]:
    """Return a dict describing a single Flame class.

    Methods and attributes are introspected one level deep. We do NOT
    recurse into instances or return types — that would explode the
    graph and add no value for static validation.
    """
    info: dict[str, Any] = {
        "doc": _safe_doc(cls),
        "bases": [],
        "methods": {},
        "attrs": {},
    }

    # __bases__ — list of base class names. Always wrap in try; some
    # C-extension classes lie about their MRO.
    try:
        info["bases"] = [b.__name__ for b in cls.__bases__ if b is not object]
    except Exception:
        info["bases"] = []

    # Walk class members.
    try:
        member_names = dir(cls)
    except Exception:
        member_names = []

    for name in member_names:
        if not _is_visible(name):
            continue
        member = _safe_getattr(cls, name)
        if member is None:
            # Could be a real None attribute or a getattr failure; either
            # way we have nothing useful to record beyond the name.
            info["attrs"][name] = {"kind": "unknown", "type_hint": "NoneType", "doc": ""}
            continue

        # Callable -> method.
        if callable(member) and not inspect.isclass(member):
            doc = _safe_doc(member)
            entry: dict[str, Any] = {
                "signature": _safe_signature(member),
                "doc": doc,
                "returns_hint": None,  # populated below if we can infer one
            }
            # Try to surface a return annotation if Python knows about one.
            try:
                sig = inspect.signature(member)
                if sig.return_annotation is not inspect.Signature.empty:
                    entry["returns_hint"] = str(sig.return_annotation)
            except (TypeError, ValueError):
                pass
            except Exception:
                pass

            notes = _trap_notes(name, doc)
            if notes:
                entry["notes"] = notes
            info["methods"][name] = entry
            continue

        # Non-callable -> attribute / descriptor.
        type_name = type(member).__name__
        info["attrs"][name] = {
            "kind": type_name,
            "type_hint": type_name,
            "doc": _safe_doc(member),
        }

    return info


def build_graph(flame_module: Any) -> dict[str, Any]:
    """Walk the ``flame`` module and return the full graph dict."""
    module_attrs: dict[str, dict[str, Any]] = {}
    functions: dict[str, dict[str, Any]] = {}
    classes: dict[str, dict[str, Any]] = {}

    try:
        top_names = dir(flame_module)
    except Exception:
        top_names = []

    for name in top_names:
        if not _is_visible(name):
            continue
        obj = _safe_getattr(flame_module, name)
        if obj is None:
            module_attrs[f"flame.{name}"] = {"type": "NoneType", "doc": ""}
            continue

        # Class -> classes bucket.
        if inspect.isclass(obj):
            try:
                classes[obj.__name__] = _describe_class(obj)
            except Exception as exc:
                # Last-resort guardrail: record the class with an error
                # marker so we never lose the fact that it exists.
                classes[obj.__name__] = {
                    "doc": f"<introspection failed: {exc!r}>",
                    "bases": [],
                    "methods": {},
                    "attrs": {},
                }
            continue

        # Callable but not a class -> module-level function.
        if callable(obj):
            doc = _safe_doc(obj)
            entry: dict[str, Any] = {
                "kind": "function",
                "signature": _safe_signature(obj),
                "doc": doc,
            }
            notes = _trap_notes(name, doc)
            if notes:
                entry["notes"] = notes
            functions[f"flame.{name}"] = entry
            continue

        # Otherwise -> module-level attribute (PyBatch, PyMediaPanel, ...).
        module_attrs[f"flame.{name}"] = {
            "type": type(obj).__name__,
            "doc": _safe_doc(obj),
        }

    # Best-effort Flame version. ``flame.get_version()`` is the documented
    # entry point; fall back to ``__version__`` if it raises.
    flame_version = "unknown"
    get_version = _safe_getattr(flame_module, "get_version")
    if callable(get_version):
        try:
            flame_version = str(get_version())
        except Exception:
            flame_version = "unknown"
    if flame_version == "unknown":
        ver_attr = _safe_getattr(flame_module, "__version__")
        if ver_attr:
            flame_version = str(ver_attr)

    return {
        "_meta": {
            "flame_version": flame_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "introspector": "scripts/introspect_flame_api.py",
            "classes_total": len(classes),
            "module_attrs_total": len(module_attrs),
            "functions_total": len(functions),
        },
        "module_attrs": module_attrs,
        "functions": functions,
        "classes": classes,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_FLAME_MISSING_MSG = (
    "REQUIRES FLAME OPEN -- bridge or in-Flame Python only.\n"
    "Hint: run this script via the flame-mcp `execute_python` tool, or paste"
    " its contents into Flame's Python console.\n"
    "It cannot be executed under a system Python because the `flame`"
    " module is only provided by Flame's embedded interpreter."
)


def _try_import_flame() -> Any | None:
    """Attempt to import the ``flame`` module. Return module or None."""
    try:
        import flame  # type: ignore[import-not-found]
        return flame
    except ImportError:
        return None
    except Exception:
        # An import that raises something other than ImportError is still
        # a hard failure for our purposes; log it for debugging and treat
        # the module as missing.
        traceback.print_exc(file=sys.stderr)
        return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="introspect_flame_api.py",
        description="Introspect Flame's Python API and emit rag/api_graph.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)}).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Only verify that the `flame` module is importable. "
            "Exit 0 if available, 2 if missing."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    flame_module = _try_import_flame()
    if flame_module is None:
        print(_FLAME_MISSING_MSG, file=sys.stderr)
        return EXIT_FLAME_MISSING

    if args.check:
        print(f"OK: `flame` module is importable (version={_safe_getattr(flame_module, '__version__') or 'unknown'}).")
        return EXIT_OK

    graph = build_graph(flame_module)

    out_path: Path = args.output
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(graph, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: failed to write {out_path}: {exc}", file=sys.stderr)
        return EXIT_WRITE_ERROR

    meta = graph["_meta"]
    print(
        "Wrote {path}\n"
        "  flame_version       = {ver}\n"
        "  classes_total       = {classes}\n"
        "  module_attrs_total  = {attrs}\n"
        "  functions_total     = {fns}".format(
            path=out_path,
            ver=meta["flame_version"],
            classes=meta["classes_total"],
            attrs=meta["module_attrs_total"],
            fns=meta["functions_total"],
        )
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
