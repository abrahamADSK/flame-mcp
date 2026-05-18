"""
routing.py
==========
F3a — Dual-source routing.

When the LLM asks "which Flame API do I need for X?", the router has two
sources of truth, consulted in order:

1. ``concept_map.py`` (hand-curated, ~100 entries). Includes operational
   notes ("flame.selection does NOT exist", "wrap render in
   schedule_idle_event"). Fast, zero-latency, but only as broad as a
   human has cared to curate.

2. ``rag/api_graph.json`` (introspected from Flame at install/upgrade
   time by ``scripts/introspect_flame_api.py``). Broader coverage — every
   symbol that actually exists in the Flame Python API — but no curated
   safety notes beyond a handful of generic trap hints attached by the
   introspector (see ``_TRAP_HINTS`` in that script).

This module exposes:

- :func:`_route_from_graph` — search the graph for a match. Filters out
  any entry the introspector flagged with ``notes`` (trap hints): those
  symbols are unsafe to surface raw and must be routed through
  ``concept_map`` or RAG instead, where they get a curated warning.

- :func:`resolve_query` — the dual-source entry point. Tries
  ``resolve_concept`` first; on miss, falls back to ``_route_from_graph``.
  Always attaches a ``_provenance`` field (``"concept_map"`` |
  ``"graph"``) so callers can route on it and so F0 telemetry can break
  down latency / fallo by source.

Design constraints (issue #9 acceptance criteria):

- The F3b adversarial golden entries MUST continue to fail
  ``must_not_contain`` after F3a lands. The graph entry for
  ``flame.batch.render`` exists and carries a ``schedule_idle_event``
  trap note from the introspector; the safety filter below refuses to
  surface that ``api_path`` raw, forcing the LLM to either get the
  curated concept_map entry first (which it does — ``concept_map`` is
  consulted ahead of the graph) or to fall through to RAG.

- The graph file is gitignored and only exists on machines where the
  introspector has been run inside Flame. Tests must work in CI without
  it; the loader returns an empty dict on missing file, and consumers
  treat empty dicts as "no match available".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from flame_mcp.concept_map import _tokenize, resolve_concept

# ---------------------------------------------------------------------------
# Graph loader
# ---------------------------------------------------------------------------

_API_GRAPH_PATH = (
    Path(__file__).resolve().parent.parent.parent / "rag" / "api_graph.json"
)

# Module-level cache. Set on first call; reset by passing a different path
# or by callers that monkey-patch this module directly in tests.
_API_GRAPH_CACHE: Optional[dict] = None


def _load_api_graph(path: Path = _API_GRAPH_PATH) -> dict:
    """Load and cache ``rag/api_graph.json``.

    Returns an empty dict on missing file or malformed JSON. This is the
    correct behaviour for CI and for fresh clones — the introspector
    must be run inside Flame to produce the file, so its absence is
    expected and routing should degrade gracefully to concept_map +
    RAG.
    """
    global _API_GRAPH_CACHE
    if _API_GRAPH_CACHE is not None:
        return _API_GRAPH_CACHE
    if not path.exists():
        _API_GRAPH_CACHE = {}
        return _API_GRAPH_CACHE
    try:
        _API_GRAPH_CACHE = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _API_GRAPH_CACHE = {}
    return _API_GRAPH_CACHE


def _reset_graph_cache() -> None:
    """Test-only hook to force the next ``_load_api_graph`` call to re-read."""
    global _API_GRAPH_CACHE
    _API_GRAPH_CACHE = None


# ---------------------------------------------------------------------------
# Graph routing
# ---------------------------------------------------------------------------

_MIN_GRAPH_SCORE = 2  # token-overlap threshold; below this is noise

# Concept entries the graph routing should NEVER surface, even when the
# underlying symbol is technically a real Flame attribute. These are the
# adversarial traps that the F3b golden dataset asserts the router
# refuses to propose without context.
_FORBIDDEN_API_PATHS: frozenset[str] = frozenset({
    "flame.selection",  # does not exist; raises on real Flame
    "flame.projects.current_project.libraries",  # returns None
})


def _route_from_graph(
    query: str,
    graph: Optional[dict] = None,
) -> Optional[dict]:
    """Search the introspected API graph for the best match to ``query``.

    Returns a dict shaped like a ``concept_map`` entry so callers can
    treat both sources uniformly::

        {
            "concept":   <inferred from path>,
            "api_layer": "python_api",
            "tool":      "execute_python",
            "api_path":  "flame.X.Y" or "ClassName.method",
            "notes":     "<joined trap notes if any — see safety filter>",
            "_provenance": "graph",
        }

    Returns ``None`` when:

    - The query is empty or yields no tokens.
    - The graph is empty (file missing in CI / on a fresh clone).
    - No entry scores above the minimum threshold.
    - The best-scoring entry carries trap ``notes`` from the
      introspector (e.g. ``schedule_idle_event`` warning on ``render``,
      ``.clear()`` crash warning). Such entries are unsafe to surface
      raw because the must_not_contain checks in F3b assert the router
      never proposes the bare forbidden form. The LLM falls through to
      ``search_flame_docs`` which returns the curated docs that include
      the safe pattern.
    - The matched path is in :data:`_FORBIDDEN_API_PATHS`.

    Args:
        query: Natural-language query.
        graph: Optional pre-loaded graph dict. Mainly for tests; defaults
            to the cached ``rag/api_graph.json``.
    """
    if not query or not query.strip():
        return None
    graph = graph if graph is not None else _load_api_graph()
    if not graph:
        return None

    query_tokens = _tokenize(query)
    if not query_tokens:
        return None

    best: Optional[tuple[int, str, dict]] = None

    # Module-level functions: keys are already "flame.X".
    for path, entry in (graph.get("functions") or {}).items():
        if path in _FORBIDDEN_API_PATHS:
            continue
        name = path.replace("flame.", "")
        tokens = _tokenize(name) | _tokenize(entry.get("doc", ""))
        score = len(query_tokens & tokens)
        if score > 0 and (best is None or score > best[0]):
            best = (score, path, entry)

    # Class methods: synthesise "ClassName.method" as the api_path.
    for class_name, class_info in (graph.get("classes") or {}).items():
        class_tokens = _tokenize(class_name)
        class_doc_tokens = _tokenize(class_info.get("doc", ""))
        for method_name, method_entry in (class_info.get("methods") or {}).items():
            full_path = f"{class_name}.{method_name}"
            if full_path in _FORBIDDEN_API_PATHS:
                continue
            tokens = (
                class_tokens
                | class_doc_tokens
                | _tokenize(method_name)
                | _tokenize(method_entry.get("doc", ""))
            )
            score = len(query_tokens & tokens)
            if score > 0 and (best is None or score > best[0]):
                best = (score, full_path, method_entry)

    if best is None or best[0] < _MIN_GRAPH_SCORE:
        return None

    _, path, entry = best
    notes_list = entry.get("notes") or []

    # Safety filter: any introspector-flagged trap forces None so the
    # adversarial path can never be surfaced raw. The curated
    # concept_map entry (or RAG) handles the same query with the
    # required warning attached.
    if notes_list:
        return None

    # Best-effort concept label from the path tail.
    tail = path.rsplit(".", 1)[-1]
    concept_label = tail.replace("_", " ")

    return {
        "concept": concept_label,
        "api_layer": "python_api",
        "tool": "execute_python",
        "api_path": path,
        "notes": "",
        "_provenance": "graph",
    }


# ---------------------------------------------------------------------------
# Public chained entry point
# ---------------------------------------------------------------------------


def resolve_query(
    query: str,
    graph: Optional[dict] = None,
) -> Optional[dict]:
    """Dual-source routing — concept_map first, then api_graph.json.

    Returns the resolver dict with an additional ``_provenance`` field:

    - ``"concept_map"`` when ``resolve_concept`` matched.
    - ``"graph"`` when the graph fallback matched.
    - ``None`` when neither matched (caller should fall back to RAG).

    Args:
        query: Natural-language description of the desired operation.
        graph: Optional pre-loaded graph dict (test hook).
    """
    via_concept = resolve_concept(query)
    if via_concept is not None:
        annotated = dict(via_concept)
        annotated["_provenance"] = "concept_map"
        return annotated
    return _route_from_graph(query, graph=graph)
