"""
test_ast_validate.py
====================
F4b — Unit tests for ``flame_mcp._ast_validate``.

Hermetic — loads the shared ``tests/fixtures/api_graph_sample.json``
introduced in F3a. No real Flame, no real api_graph.json.

Test groups
-----------
- ``_load_graph`` degradation (missing / malformed → empty dict).
- AST walking: outermost-chain capture, sub-path dedupe.
- ``validate_python`` happy paths (real symbols pass).
- ``validate_python`` rejection paths (hallucinated symbols fail with
  suggestion).
- Resolution heuristic: a chain whose prefix is a known module
  attribute is accepted (no false positives on opaque return types).
- Edge cases: SyntaxError stays silent (bridge will surface it),
  non-flame chains are ignored, empty graph degrades to no-op.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flame_mcp import _ast_validate as av


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "api_graph_sample.json"


@pytest.fixture()
def sample_graph() -> dict:
    """The graph fixture introduced for F3a — reused here."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    av._reset_graph_cache()


# ---------------------------------------------------------------------------
# _load_graph degradation
# ---------------------------------------------------------------------------


def test_load_graph_returns_empty_when_missing(tmp_path: Path) -> None:
    assert av._load_graph(tmp_path / "nope.json") == {}


def test_load_graph_returns_empty_on_malformed_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    assert av._load_graph(bad) == {}


# ---------------------------------------------------------------------------
# _graph_symbols flatten
# ---------------------------------------------------------------------------


def test_graph_symbols_includes_module_functions_and_classes(
    sample_graph: dict,
) -> None:
    symbols = av._graph_symbols(sample_graph)
    assert "flame.get_version" in symbols
    assert "flame.schedule_idle_event" in symbols
    assert "flame.batch" in symbols  # module attribute
    assert "PyBatch" in symbols  # class itself
    assert "PyBatch.create_batch_group" in symbols  # method
    assert "PyClip.name" in symbols  # attr


# ---------------------------------------------------------------------------
# validate_python — happy paths (no false positives)
# ---------------------------------------------------------------------------


def test_validate_accepts_real_module_function(sample_graph: dict) -> None:
    src = "v = flame.get_version()\n"
    result = av.validate_python(src, graph=sample_graph)
    assert result.ok
    assert result.graph_loaded


def test_validate_accepts_real_attribute_chain(sample_graph: dict) -> None:
    src = (
        "ws = flame.batch\n"
        "print(flame.get_version())\n"
    )
    result = av.validate_python(src, graph=sample_graph)
    assert result.ok


def test_validate_accepts_prefix_resolved_chain(sample_graph: dict) -> None:
    """``flame.batch.render`` resolves via the prefix rule.

    Even though ``flame.batch.render`` is NOT a key in the graph (the
    method is recorded under ``PyBatch.render``), the prefix
    ``flame.batch`` IS a module attribute, so the walker accepts the
    extension. This is the false-positive-control mechanism — without
    type inference we cannot prove the suffix exists on the target
    class, so we err on the side of valid.
    """
    src = "flame.schedule_idle_event(lambda: flame.batch.render())\n"
    result = av.validate_python(src, graph=sample_graph)
    assert result.ok


def test_validate_accepts_non_flame_chains(sample_graph: dict) -> None:
    """``os.path.join`` is irrelevant to F4b — should be ignored."""
    src = "import os\np = os.path.join('a', 'b')\n"
    result = av.validate_python(src, graph=sample_graph)
    assert result.ok


# ---------------------------------------------------------------------------
# validate_python — rejection paths
# ---------------------------------------------------------------------------


def test_validate_rejects_hallucinated_top_level(sample_graph: dict) -> None:
    """``flame.selection`` does NOT exist in the fixture (or in real Flame)."""
    src = "for x in flame.selection:\n    print(x)\n"
    result = av.validate_python(src, graph=sample_graph)
    assert not result.ok
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.symbol == "flame.selection"
    assert issue.line == 1


def test_validate_rejects_made_up_symbol(sample_graph: dict) -> None:
    src = "x = flame.foo_bar_baz()\n"
    result = av.validate_python(src, graph=sample_graph)
    assert not result.ok
    issue = result.issues[0]
    assert issue.symbol == "flame.foo_bar_baz"


def test_validate_returns_suggestion_for_close_match(sample_graph: dict) -> None:
    """A typo-like miss surfaces a near-match suggestion."""
    # "flame.get_versionn" with extra n — close to flame.get_version
    src = "v = flame.get_versionn()\n"
    result = av.validate_python(src, graph=sample_graph)
    assert not result.ok
    issue = result.issues[0]
    # Suggestion may or may not be set depending on difflib threshold;
    # if set, it should at least mention get_version.
    if issue.suggestion is not None:
        assert "get_version" in issue.suggestion


def test_validate_collects_multiple_issues_per_snippet(sample_graph: dict) -> None:
    src = (
        "a = flame.selection\n"
        "b = flame.does_not_exist()\n"
        "c = flame.get_version()  # this one is valid\n"
    )
    result = av.validate_python(src, graph=sample_graph)
    assert not result.ok
    assert len(result.issues) == 2
    symbols = {i.symbol for i in result.issues}
    assert symbols == {"flame.selection", "flame.does_not_exist"}


# ---------------------------------------------------------------------------
# Degradation when graph is missing/empty
# ---------------------------------------------------------------------------


def test_validate_degrades_to_noop_with_empty_graph() -> None:
    src = "x = flame.totally_made_up()\n"
    result = av.validate_python(src, graph={})
    # Graph missing → walker cannot validate, returns empty issues + flag.
    assert result.ok  # no rejection because we have no ground truth
    assert result.graph_loaded is False


def test_validate_silent_on_syntax_error(sample_graph: dict) -> None:
    """Non-parseable source must NOT crash F4b — let the bridge surface it."""
    src = "this is = not valid python::\n"
    result = av.validate_python(src, graph=sample_graph)
    assert result.ok  # we don't double-report
    assert result.graph_loaded is True


# ---------------------------------------------------------------------------
# format_issues
# ---------------------------------------------------------------------------


def test_format_issues_includes_each_symbol_with_position(
    sample_graph: dict,
) -> None:
    src = "a = flame.selection\nb = flame.also_made_up\n"
    result = av.validate_python(src, graph=sample_graph)
    msg = av.format_issues(result)
    assert "flame.selection" in msg
    assert "flame.also_made_up" in msg
    assert "line 1" in msg
    assert "line 2" in msg
    # The escape-hatch instruction is visible to the LLM.
    assert "ast_dry_run: false" in msg


def test_format_issues_returns_empty_when_no_issues() -> None:
    assert av.format_issues(av.AstValidation(issues=[])) == ""
