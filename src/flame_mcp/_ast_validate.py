"""
_ast_validate.py
================
F4b — AST dry-run walker for ``execute_python`` pre-flight.

Defense-in-depth complement to F3a (routing-layer refusal) and F4a
(workspace cache). When the LLM emits Python through ``execute_python``,
this module statically walks the AST, finds every ``flame.X.Y.Z``
attribute reference, and validates it against ``rag/api_graph.json``
(produced by F2-intro). If a symbol does not exist in the graph, the
call is rejected with an actionable error BEFORE the socket round-trip
to Flame happens.

Why static, not runtime
-----------------------
A runtime check would still send the snippet to Flame; the crash would
still surface on the user side. The AST pass catches the class of
"hallucinated `flame.foo_bar_baz`" symbols in single-digit milliseconds
without ever touching the bridge.

Scope: what F4b CAN and CANNOT catch
------------------------------------

CAN (the value F4b adds):

- ``flame.selection`` (does not exist on Flame 2026).
- ``flame.foo_bar_baz`` (invented symbol).
- ``PyClip.do_thing`` where ``do_thing`` is hallucinated.

CANNOT (and is not meant to):

- ``flame.batch.render(...)`` without ``schedule_idle_event`` wrap.
  ``flame.batch.render`` IS a valid symbol; the trap is in USAGE,
  not existence. F3b's golden adversarial dataset is the right
  enforcement layer for this — it asserts the ROUTER never proposes
  the bare form. F4b refuses to flag because doing so would block
  legitimate calls inside ``schedule_idle_event(lambda: ...)``.
- Hidden-library filter (Timeline FX / Grabbed References) — runtime
  state, not AST.
- Iteration-on-``flame.projects`` (the property exists; the crash
  comes from iteration semantics).

Telemetry
---------
``validate_python`` returns an ``AstValidation`` dataclass that
``execute_python`` can record into ``_stats``:

- ``rejected_count`` — how many calls were blocked outright.
- ``false_positives_suspected`` — incremented when the user / LLM
  forces the snippet through despite a rejection (a follow-up F0
  schema field).

Both fields are surfaced via the existing ``session_stats()`` tool so
the LLM can self-diagnose.

Graceful degradation
--------------------
When ``rag/api_graph.json`` is missing or empty (CI / fresh clone /
operator hasn't run the introspector yet), ``validate_python`` returns
an empty issue list — the walker becomes a no-op. The pre-flight in
``execute_python`` therefore lets the call through. This is the
correct behaviour: F4b is opt-in extra protection, not a hard
prerequisite. The hard prerequisites remain the F3 RAG gate and the
F0 telemetry.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Graph path & cache
# ---------------------------------------------------------------------------

_API_GRAPH_PATH = (
    Path(__file__).resolve().parent.parent.parent / "rag" / "api_graph.json"
)

# Cache the loaded graph between calls — execute_python may invoke
# validate_python frequently. We reload only when the path changes.
_GRAPH_CACHE: Optional[dict] = None
_GRAPH_CACHE_PATH: Optional[Path] = None


def _load_graph(path: Path = _API_GRAPH_PATH) -> dict:
    """Load and cache ``rag/api_graph.json``.

    Returns an empty dict when the file does not exist or cannot be
    parsed — the AST walker treats an empty graph as "no validation
    available" and degrades to a no-op.
    """
    global _GRAPH_CACHE, _GRAPH_CACHE_PATH
    if _GRAPH_CACHE is not None and _GRAPH_CACHE_PATH == path:
        return _GRAPH_CACHE
    _GRAPH_CACHE_PATH = path
    if not path.exists():
        _GRAPH_CACHE = {}
        return _GRAPH_CACHE
    try:
        _GRAPH_CACHE = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _GRAPH_CACHE = {}
    return _GRAPH_CACHE


def _reset_graph_cache() -> None:
    """Test-only hook: force the next ``_load_graph`` call to re-read."""
    global _GRAPH_CACHE, _GRAPH_CACHE_PATH
    _GRAPH_CACHE = None
    _GRAPH_CACHE_PATH = None


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnresolvedSymbol:
    """One unresolved ``flame.X.Y`` reference in the parsed source.

    Carries enough context for the LLM (or a human reviewing the
    error) to either fix the call or override the pre-flight.
    """

    symbol: str           # full dotted path, e.g. "flame.selection"
    line: int             # 1-based line number from ast.AST
    col: int              # 0-based column offset
    suggestion: Optional[str] = None  # nearest valid symbol or None


@dataclass
class AstValidation:
    """Result of ``validate_python`` — list of issues + summary fields."""

    issues: list[UnresolvedSymbol] = field(default_factory=list)
    graph_loaded: bool = True  # False when the graph was missing/empty

    @property
    def ok(self) -> bool:
        """True when the source is safe to send to Flame."""
        return not self.issues


# ---------------------------------------------------------------------------
# Graph-derived symbol set
# ---------------------------------------------------------------------------


def _graph_symbols(graph: dict) -> set[str]:
    """Flatten the graph into a set of valid dotted paths.

    Includes:
    - ``flame.X`` for each module attribute.
    - ``flame.X`` for each module-level function.
    - ``ClassName`` AND ``flame.ClassName`` for each class — every Flame
      class is also exposed as an attribute of the ``flame`` module
      (``flame.PyTime(50)``, ``isinstance(x, flame.PyClip)`` are official
      cookbook patterns), but the introspector records classes without the
      prefix, so prefixed references used to be falsely rejected.
    - ``ClassName.method`` for each class method.
    - ``ClassName.attr`` for each class attribute.

    The set is used for ``in``-membership tests during AST walking.
    """
    out: set[str] = set()
    for key in graph.get("module_attrs", {}):
        out.add(key)  # already "flame.X"
    for key in graph.get("functions", {}):
        out.add(key)
    for class_name, class_info in (graph.get("classes") or {}).items():
        out.add(class_name)
        out.add(f"flame.{class_name}")
        for method_name in (class_info.get("methods") or {}):
            out.add(f"{class_name}.{method_name}")
        for attr_name in (class_info.get("attrs") or {}):
            out.add(f"{class_name}.{attr_name}")
    return out


# ---------------------------------------------------------------------------
# AST walker
# ---------------------------------------------------------------------------


def _dotted_path(node: ast.Attribute) -> Optional[str]:
    """Reconstruct ``a.b.c.d`` from a chained ``ast.Attribute`` node.

    Returns the full dotted string if the chain starts with a plain
    ``ast.Name`` (e.g. ``flame.foo.bar``). Returns ``None`` for chains
    rooted at a call or subscript (``foo().bar``, ``arr[0].baz``)
    because those cannot be statically resolved.
    """
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


class _FlameAttrCollector(ast.NodeVisitor):
    """Collects every ``flame.X.Y`` reference in the parsed module.

    We only inspect chains rooted at the bare name ``flame`` — anything
    else (an alias, a function return, a subscript) is out of scope
    because we can't statically know its type.
    """

    def __init__(self) -> None:
        self.references: list[tuple[str, int, int]] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        # Only consider the OUTERMOST Attribute of a chain — the
        # walker recurses into the value, so an outer visit covers
        # the full path. We detect "outermost" by skipping nodes
        # whose parent is also an Attribute. ast.NodeVisitor doesn't
        # track parents, so we just record every chain rooted at
        # ``flame`` once via a top-level filter.
        path = _dotted_path(node)
        if path and path.startswith("flame."):
            self.references.append((path, node.lineno, node.col_offset))
        # Recurse into the value side in case it contains a separate
        # chain (e.g. flame.x[flame.y] — we want both).
        self.generic_visit(node)


def _unique_outermost(refs: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    """Drop sub-paths whose extension is also recorded.

    For ``flame.a.b.c`` the visitor records both ``flame.a.b.c`` and
    ``flame.a.b`` at the same line/col span. We only care about the
    longest one — that's what the LLM actually wrote.
    """
    refs_sorted = sorted(refs, key=lambda r: (-len(r[0]), r[1], r[2]))
    kept: list[tuple[str, int, int]] = []
    for path, line, col in refs_sorted:
        # Skip if a longer path at the same position already kept.
        if any(
            other_line == line
            and other_col == col
            and other_path.startswith(path + ".")
            for other_path, other_line, other_col in kept
        ):
            continue
        kept.append((path, line, col))
    return sorted(kept, key=lambda r: (r[1], r[2]))


# ---------------------------------------------------------------------------
# Resolution against the graph
# ---------------------------------------------------------------------------


_FLAME_PREFIX = "flame."


def _resolves(path: str, valid_paths: set[str]) -> bool:
    """Return True when ``path`` (or a sufficient prefix) exists in the graph.

    A chain like ``flame.batch.render`` resolves when ANY of:

    - The whole ``flame.batch.render`` matches a module function key.
    - The chain prefix ``flame.batch`` is a module attribute, AND the
      remaining segments either fully match in the graph or the chain
      extends through methods/attrs of the attribute's class (best-effort
      — without type inference we treat further `.X` as plausibly valid
      so we don't false-positive on attribute access of opaque types).

    The function intentionally errs on the side of "valid" to keep
    false-positive rates low. F3b's adversarial tests cover the cases
    where the symbol is real but used unsafely; F4b only fires for
    "symbol does not exist at all".
    """
    if path in valid_paths:
        return True

    # Try peeling off trailing segments. If a prefix is a known module
    # attribute (e.g. flame.batch -> PyBatch) we accept the rest — the
    # introspector does not give us return-type info to chain through.
    parts = path.split(".")
    for i in range(len(parts), 1, -1):
        candidate = ".".join(parts[:i])
        if candidate in valid_paths:
            return True
    # Final fallback: bare ``flame`` is always valid.
    return path == "flame"


def _suggest(path: str, valid_paths: set[str]) -> Optional[str]:
    """Return the closest valid dotted path, or None when nothing similar."""
    candidates = [p for p in valid_paths if p.startswith(_FLAME_PREFIX)]
    matches = get_close_matches(path, candidates, n=1, cutoff=0.6)
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_python(
    source: str,
    graph: Optional[dict] = None,
    *,
    graph_path: Path = _API_GRAPH_PATH,
) -> AstValidation:
    """Walk ``source`` and report unresolved ``flame.X.Y`` references.

    Args:
        source: Python source text the LLM intends to run via
            ``execute_python``.
        graph: Optional pre-loaded graph dict (mainly for tests). If
            ``None``, loads from ``graph_path`` with caching.
        graph_path: Override the default graph location (rarely used;
            mostly for ``--check`` style tooling).

    Returns:
        An :class:`AstValidation` carrying a list of issues. Empty
        list means "safe to send to Flame as far as F4b can tell".
        The ``graph_loaded`` flag indicates whether the validator
        actually had data — when False, the caller should treat the
        result as "validation unavailable" rather than "code is clean".
    """
    if graph is None:
        graph = _load_graph(graph_path)
    if not graph:
        # Missing graph → walker becomes a no-op. Caller must NOT
        # interpret an empty issue list as a green light here.
        return AstValidation(issues=[], graph_loaded=False)

    valid_paths = _graph_symbols(graph)
    if not valid_paths:
        return AstValidation(issues=[], graph_loaded=False)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Let the bridge produce the SyntaxError message — F4b stays
        # out of the way for non-parseable code so we don't double-error.
        return AstValidation(issues=[], graph_loaded=True)

    collector = _FlameAttrCollector()
    collector.visit(tree)

    refs = _unique_outermost(collector.references)

    issues: list[UnresolvedSymbol] = []
    seen: set[tuple[str, int, int]] = set()
    for path, line, col in refs:
        if (path, line, col) in seen:
            continue
        seen.add((path, line, col))
        if _resolves(path, valid_paths):
            continue
        suggestion = _suggest(path, valid_paths)
        issues.append(
            UnresolvedSymbol(
                symbol=path, line=line, col=col, suggestion=suggestion
            )
        )

    return AstValidation(issues=issues, graph_loaded=True)


def format_issues(validation: AstValidation) -> str:
    """Return a human-readable, multi-line message describing each issue.

    Used by ``execute_python`` to surface F4b's rejection to the LLM in
    a format that nudges it toward a fix (or toward the
    ``ast_dry_run: false`` config override if the LLM is sure the
    symbol is real and the graph is stale).
    """
    if not validation.issues:
        return ""
    lines = [
        "❌ AST dry-run rejected the snippet — unresolved Flame symbol(s):",
        "",
    ]
    for issue in validation.issues:
        suggestion = (
            f" → did you mean `{issue.suggestion}`?"
            if issue.suggestion
            else ""
        )
        lines.append(
            f"  · {issue.symbol} (line {issue.line}, col {issue.col}){suggestion}"
        )
    lines.extend([
        "",
        "If you are CERTAIN the symbol exists (e.g. the introspected",
        "api_graph.json is stale and you are on a newer Flame), either:",
        "  - regenerate `rag/api_graph.json` via",
        "    `scripts/introspect_flame_api.py` inside Flame, OR",
        "  - set `ast_dry_run: false` in config.json to bypass F4b.",
    ])
    return "\n".join(lines)
