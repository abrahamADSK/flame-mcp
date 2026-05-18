"""
test_routing.py
===============
F3a — Unit tests for ``flame_mcp.routing``.

Three behaviours to lock in:

- :func:`_route_from_graph` returns a usable concept-shaped dict for safe
  symbols and ``None`` for trap-flagged ones.
- :func:`_route_from_graph` returns ``None`` when the graph is missing
  (CI / fresh clone case).
- :func:`resolve_query` chains ``resolve_concept`` first; when concept_map
  misses, falls back to the graph; ``_provenance`` field is set
  consistently.

Hermetic: every test loads the fixture at
``tests/fixtures/api_graph_sample.json`` directly. No file I/O against
the real ``rag/api_graph.json`` (which is gitignored and only generated
inside Flame).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flame_mcp import routing


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "api_graph_sample.json"


@pytest.fixture()
def sample_graph() -> dict:
    """Load the bundled sample graph."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Reset routing's graph cache before every test for isolation."""
    routing._reset_graph_cache()


# ---------------------------------------------------------------------------
# _load_api_graph — missing-file branch
# ---------------------------------------------------------------------------


def test_load_api_graph_returns_empty_when_file_missing(tmp_path: Path) -> None:
    """When the configured graph path does not exist, return ``{}``."""
    missing = tmp_path / "no_such_graph.json"
    assert routing._load_api_graph(missing) == {}


def test_load_api_graph_returns_empty_on_malformed_json(tmp_path: Path) -> None:
    """Malformed JSON degrades to empty dict, never raises."""
    bad = tmp_path / "broken.json"
    bad.write_text("{this is not json", encoding="utf-8")
    assert routing._load_api_graph(bad) == {}


def test_load_api_graph_caches_after_first_call(sample_graph: dict) -> None:
    """Second call returns the same cached object."""
    # Prime the cache by injecting the fixture directly.
    routing._API_GRAPH_CACHE = sample_graph
    again = routing._load_api_graph(Path("/nonexistent"))
    assert again is sample_graph


# ---------------------------------------------------------------------------
# _route_from_graph — safe symbols
# ---------------------------------------------------------------------------


def test_route_from_graph_returns_safe_module_function(sample_graph: dict) -> None:
    """A function with no trap notes is surfaced as a usable concept."""
    result = routing._route_from_graph("get flame version", graph=sample_graph)
    assert result is not None
    assert result["api_path"] == "flame.get_version"
    assert result["_provenance"] == "graph"
    assert result["tool"] == "execute_python"
    assert result["api_layer"] == "python_api"


def test_route_from_graph_returns_safe_class_method(sample_graph: dict) -> None:
    """A method without trap notes is surfaced via ClassName.method path."""
    result = routing._route_from_graph(
        "create batch group", graph=sample_graph
    )
    assert result is not None
    assert result["api_path"] == "PyBatch.create_batch_group"
    assert result["_provenance"] == "graph"


def test_route_from_graph_finds_wiretap_helper(sample_graph: dict) -> None:
    """The wiretap node id helper is reachable via the graph."""
    result = routing._route_from_graph(
        "find by wiretap node id", graph=sample_graph
    )
    assert result is not None
    assert result["api_path"] == "flame.find_by_wiretap_node_id"


# ---------------------------------------------------------------------------
# _route_from_graph — trap-flagged symbols and forbidden paths
# ---------------------------------------------------------------------------


def test_route_from_graph_refuses_trap_flagged_render(sample_graph: dict) -> None:
    """``render`` carries a schedule_idle_event trap note → refuse to surface.

    This is what keeps F3b's adversarial entries failing
    ``must_not_contain`` after F3a lands: the graph technically contains
    ``PyBatch.render`` but the introspector's notes mark it as unsafe,
    so the bypass returns None and the LLM has to consult RAG (or
    concept_map upstream of this function) for the safe pattern.
    """
    result = routing._route_from_graph("render batch", graph=sample_graph)
    assert result is None


def test_route_from_graph_refuses_trap_flagged_clear(sample_graph: dict) -> None:
    """``.clear()`` carries a crash warning note → refuse to surface."""
    result = routing._route_from_graph("clear container", graph=sample_graph)
    assert result is None


def test_route_from_graph_returns_none_on_empty_query() -> None:
    assert routing._route_from_graph("", graph={"functions": {}}) is None
    assert routing._route_from_graph("   ", graph={"functions": {}}) is None


def test_route_from_graph_returns_none_on_empty_graph() -> None:
    assert routing._route_from_graph("anything", graph={}) is None


def test_route_from_graph_returns_none_on_no_overlap(sample_graph: dict) -> None:
    """Token-overlap below threshold returns None (not a false-positive)."""
    result = routing._route_from_graph(
        "completely unrelated cooking recipe", graph=sample_graph
    )
    assert result is None


# ---------------------------------------------------------------------------
# resolve_query — dual-source chain
# ---------------------------------------------------------------------------


def test_resolve_query_prefers_concept_map_when_available(
    sample_graph: dict,
) -> None:
    """A query that ``concept_map`` answers should be tagged ``concept_map``.

    "list libraries" is a curated concept entry, so the bypass should
    NOT be reached.
    """
    result = routing.resolve_query("list libraries", graph=sample_graph)
    assert result is not None
    assert result["_provenance"] == "concept_map"
    assert result["tool"] == "list_libraries"


def test_resolve_query_falls_back_to_graph_on_concept_map_miss(
    sample_graph: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When concept_map has no match, the graph supplies a safe one.

    We force concept_map to miss via monkeypatch so the test exercises
    the fallback unambiguously — the real concept_map is large and most
    natural-language queries already match it.
    """
    monkeypatch.setattr(routing, "resolve_concept", lambda q: None)
    result = routing.resolve_query(
        "find by wiretap node id", graph=sample_graph
    )
    assert result is not None
    assert result["_provenance"] == "graph"
    assert result["api_path"] == "flame.find_by_wiretap_node_id"


def test_resolve_query_returns_none_when_both_sources_miss(
    sample_graph: dict,
) -> None:
    """Genuine miss in both sources returns None (caller falls to RAG)."""
    result = routing.resolve_query(
        "xyzzy plugh nonsense", graph=sample_graph
    )
    assert result is None


def test_resolve_query_provenance_field_is_always_present_on_hit(
    sample_graph: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every non-None result carries ``_provenance``."""
    # Real concept_map for the "list libraries" hit.
    via_concept = routing.resolve_query("list libraries", graph=sample_graph)
    assert via_concept is not None and "_provenance" in via_concept
    assert via_concept["_provenance"] == "concept_map"

    # Force concept_map to miss so the graph branch fires deterministically.
    monkeypatch.setattr(routing, "resolve_concept", lambda q: None)
    via_graph = routing.resolve_query(
        "find by wiretap node id", graph=sample_graph
    )
    assert via_graph is not None and "_provenance" in via_graph
    assert via_graph["_provenance"] == "graph"
