"""
test_golden.py
==============
F3b — Golden routing test.

Loads ``tests/golden/flame_queries.jsonl`` and, for every entry, validates
the behaviour of :func:`flame_mcp.concept_map.resolve_concept` (plus a
mocked :func:`flame_mcp.rag.search.search`) against the entry's
expectations.

What this suite is NOT
----------------------
- It does NOT call live Flame.
- It does NOT touch the real ChromaDB index — ``search_flame_docs`` is
  monkey-patched so the test stays hermetic and CI-safe.
- It does NOT score answer quality. It measures *routing*: did the
  resolver pick the right tool, and did it avoid forbidden API symbols?

Per-entry checks
----------------
1. ``must_not_contain`` (mandatory guardrail). Checked against the
   resolver's ``api_path`` ONLY — not ``notes``. The distinction is
   load-bearing: ``api_path`` is the code the LLM may copy, so any
   forbidden symbol there is a real routing hazard. ``notes`` are
   LLM-facing *warnings* about traps (e.g. "flame.selection does NOT
   exist"); they MUST be allowed to mention the forbidden symbol by
   name to teach the LLM. Including notes here would false-positive
   on every adversarial entry whose curated note already warns about
   the trap.
2. ``expected_tool``. When provided, the resolved concept's ``tool``
   field must match exactly. ``expected_tool: null`` means the entry is
   a known fall-through case (e.g. Spanish-only queries that the current
   resolver does not handle) and is recorded as ``skipped`` rather than
   failing.
3. ``must_contain``. If provided, at least one of the listed substrings
   must appear in the resolver's ``api_path`` + ``notes`` text. This
   softer positive check IS allowed to read notes because the goal here
   is to confirm the LLM sees the right vocabulary, including the
   safety warnings.

Adversarial integrity rule
--------------------------
Any entry tagged ``adversarial`` MUST carry a non-empty
``must_not_contain`` list. The F6a precondition gate
(``scripts/check_adversarial_count.py``) re-asserts this at the dataset
level. The test below re-asserts it per entry so a broken adversarial
record cannot pass silently.

Coverage report
---------------
The session-scoped fixture at the bottom prints a pass-rate breakdown by
category and by tag at the end of the run. The breakdown is informational
— failing entries are *expected* in early phases and inform later work.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pytest

from flame_mcp.routing import resolve_query as resolve_concept

# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

GOLDEN_PATH = Path(__file__).parent / "golden" / "flame_queries.jsonl"


def _load_golden() -> list[dict[str, Any]]:
    """Load every non-blank line of the JSONL dataset as a dict."""
    if not GOLDEN_PATH.exists():
        return []
    with GOLDEN_PATH.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


_ENTRIES: list[dict[str, Any]] = _load_golden()


# ---------------------------------------------------------------------------
# Mocked search_flame_docs
# ---------------------------------------------------------------------------


def _mock_search(query: str, n_results: int = 3) -> tuple[str, int]:
    """Return a deterministic placeholder so tests are hermetic.

    The real :func:`flame_mcp.rag.search.search` reads a ChromaDB index
    that is not built in CI. For routing tests we only need the function
    to *exist* and return a tuple of ``(text, tokens_used)``.
    """
    return (f"[mocked search response for: {query}]", 0)


@pytest.fixture(autouse=True)
def _mock_rag_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the RAG search at the import boundary for every test."""
    try:
        import flame_mcp.rag.search as rag_search

        monkeypatch.setattr(rag_search, "search", _mock_search, raising=False)
    except ImportError:
        # If the rag package is not importable in this environment, the
        # test still runs — resolve_concept is independent of it.
        pass


# ---------------------------------------------------------------------------
# Per-entry tests
# ---------------------------------------------------------------------------


def _routing_text(concept: dict[str, Any] | None) -> str:
    """Lower-cased ``api_path`` text of a resolved concept.

    Returns ``api_path`` only — NOT ``notes``. The distinction matters:
    ``api_path`` is the suggested code the LLM may copy, so any forbidden
    symbol there is a real routing hazard. ``notes`` are LLM-facing
    *warnings* (e.g. "flame.selection does NOT exist"); those need to
    mention the forbidden symbol by name in order to teach. Including
    notes in the must_not_contain check would false-positive on every
    adversarial entry whose curated note already warns about the trap.

    For unmatched queries (``concept is None``) returns the empty string
    so the guardrail check degenerates to a guaranteed pass.
    """
    if concept is None:
        return ""
    return concept.get("api_path", "").lower()


def _routing_grounding(concept: dict[str, Any] | None) -> str:
    """Concatenated ``api_path`` + ``notes`` text used for must_contain checks.

    Soft positive checks (must_contain) are allowed to match against the
    warnings text — that is the only place where the LLM is reminded of
    correct phrasing. Kept separate from ``_routing_text`` so the
    asymmetric semantics is explicit and reviewable.
    """
    if concept is None:
        return ""
    return (concept.get("api_path", "") + " " + concept.get("notes", "")).lower()


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e["id"])
def test_adversarial_has_guardrail(entry: dict[str, Any]) -> None:
    """Adversarial entries MUST declare must_not_contain."""
    if "adversarial" not in entry.get("tags", []):
        pytest.skip("not an adversarial entry")
    must_not = entry.get("must_not_contain") or []
    assert must_not, (
        f"{entry['id']}: adversarial entry has empty must_not_contain; "
        "this is forbidden because the F6a gate relies on the guardrail"
    )


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e["id"])
def test_routing_must_not_contain(entry: dict[str, Any]) -> None:
    """The resolver output must not include any forbidden API symbol."""
    concept = resolve_concept(entry["query"])
    text = _routing_text(concept)
    for forbidden in entry.get("must_not_contain") or []:
        assert forbidden.lower() not in text, (
            f"{entry['id']}: forbidden symbol '{forbidden}' appeared in "
            f"routing output for query {entry['query']!r}"
        )


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e["id"])
def test_routing_expected_tool(entry: dict[str, Any]) -> None:
    """When ``expected_tool`` is set, the resolved tool must match.

    A null/absent ``expected_tool`` marks a known fall-through case and
    is skipped (not xfailed) so the test report stays readable.
    """
    expected = entry.get("expected_tool")
    if expected is None:
        pytest.skip(f"{entry['id']}: no expected_tool (fall-through case)")
    concept = resolve_concept(entry["query"])
    assert concept is not None, (
        f"{entry['id']}: resolver returned None for query "
        f"{entry['query']!r}, expected tool {expected!r}"
    )
    assert concept["tool"] == expected, (
        f"{entry['id']}: resolved to tool {concept['tool']!r}, "
        f"expected {expected!r} (concept: {concept['concept']!r})"
    )


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e["id"])
def test_routing_must_contain(entry: dict[str, Any]) -> None:
    """If ``must_contain`` is non-empty, at least one substring must appear.

    The substring is searched in the resolver's notes/api_path text. A
    mocked search response (deterministic, not queried here) keeps the
    test hermetic. Empty ``must_contain`` skips the entry.
    """
    expected_substrings = entry.get("must_contain") or []
    if not expected_substrings:
        pytest.skip(f"{entry['id']}: no must_contain assertions")
    concept = resolve_concept(entry["query"])
    text = _routing_grounding(concept)
    matched = [s for s in expected_substrings if s.lower() in text]
    assert matched, (
        f"{entry['id']}: none of must_contain={expected_substrings} "
        f"appeared in routing output for query {entry['query']!r} "
        f"(resolved concept: {concept['concept'] if concept else None!r})"
    )


# ---------------------------------------------------------------------------
# Session-end coverage report (informational; never fails the suite)
# ---------------------------------------------------------------------------
#
# A static dataset summary is printed at module import time via the
# fixture below. It does NOT measure per-outcome counts (that requires a
# proper pytest plugin hook in ``conftest.py``); it surfaces dataset
# composition (totals, adversarial count, lang/category breakdown) so
# the F4 verification phase can spot a missing category at a glance.


@pytest.fixture(scope="session", autouse=True)
def _print_golden_summary(request: pytest.FixtureRequest) -> None:
    """Print dataset composition once per session."""
    if not _ENTRIES:
        return

    by_category: Counter = Counter(e["category"] for e in _ENTRIES)
    by_lang: Counter = Counter(e["lang"] for e in _ENTRIES)
    by_tag: dict[str, int] = defaultdict(int)
    for e in _ENTRIES:
        for tag in e.get("tags", []):
            by_tag[tag] += 1

    def _emit_report() -> None:
        reporter = request.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is None:
            return
        reporter.write_sep("=", "golden-routing dataset")
        reporter.write_line(f"dataset: {GOLDEN_PATH} ({len(_ENTRIES)} entries)")
        reporter.write_line("by category: " + ", ".join(
            f"{c}={n}" for c, n in sorted(by_category.items())
        ))
        reporter.write_line("by lang:     " + ", ".join(
            f"{c}={n}" for c, n in sorted(by_lang.items())
        ))
        reporter.write_line("by tag:      " + ", ".join(
            f"{c}={n}" for c, n in sorted(by_tag.items())
        ))

    request.addfinalizer(_emit_report)
