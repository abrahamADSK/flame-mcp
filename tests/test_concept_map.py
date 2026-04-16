"""
test_concept_map.py
===================
Tests for the concept_map module: static lookup table for Flame operations.

Covers:
  - resolve_concept returns correct tool for known concepts
  - resolve_concept returns None for unknown/empty queries
  - All CONCEPT_MAP entries have the required keys
  - No duplicate concepts in the map
  - Minimum entry count (30+)
  - Fuzzy matching on partial / natural-language queries
"""

import pytest

from flame_mcp.concept_map import (
    CONCEPT_MAP,
    _REQUIRED_KEYS,
    resolve_concept,
)


# ── Structural validation ────────────────────────────────────────────────────


class TestConceptMapStructure:
    """Validate the integrity of the CONCEPT_MAP data structure."""

    def test_minimum_entry_count(self):
        """CONCEPT_MAP must contain at least 30 entries."""
        assert len(CONCEPT_MAP) >= 30, (
            f"Expected at least 30 concept entries, got {len(CONCEPT_MAP)}"
        )

    def test_all_entries_have_required_keys(self):
        """Every entry must have all required keys: concept, api_layer, tool, api_path, notes."""
        for i, entry in enumerate(CONCEPT_MAP):
            missing = _REQUIRED_KEYS - set(entry.keys())
            assert not missing, (
                f"Entry {i} ({entry.get('concept', '???')}) missing keys: {missing}"
            )

    def test_no_duplicate_concepts(self):
        """No two entries should have the same concept name."""
        concepts = [entry["concept"] for entry in CONCEPT_MAP]
        seen = set()
        duplicates = []
        for c in concepts:
            if c in seen:
                duplicates.append(c)
            seen.add(c)
        assert not duplicates, f"Duplicate concepts found: {duplicates}"

    def test_all_values_are_nonempty_strings(self):
        """All field values must be non-empty strings."""
        for i, entry in enumerate(CONCEPT_MAP):
            for key in _REQUIRED_KEYS:
                val = entry[key]
                assert isinstance(val, str) and val.strip(), (
                    f"Entry {i} ({entry['concept']}): field '{key}' is empty or not a string"
                )

    def test_api_layer_values_are_valid(self):
        """api_layer must be one of the recognized layer names."""
        valid_layers = {"python_api", "wiretap_cli", "wiretap_sdk", "dedicated_tool"}
        for entry in CONCEPT_MAP:
            assert entry["api_layer"] in valid_layers, (
                f"Entry '{entry['concept']}' has invalid api_layer: '{entry['api_layer']}'"
            )


# ── resolve_concept: known queries ───────────────────────────────────────────


class TestResolveConceptKnown:
    """Verify resolve_concept returns the correct tool for well-known queries."""

    @pytest.mark.parametrize(
        "query, expected_tool",
        [
            ("list libraries", "list_libraries"),
            ("list reels", "list_reels"),
            ("list clips", "list_clips"),
            ("get project info", "get_project_info"),
            ("get flame version", "get_flame_version"),
            ("check bridge connection", "ping"),
            ("list all projects", "list_all_projects"),
            ("get clip metadata", "get_clip_metadata"),
            ("get selected clips", "get_selected_clips"),
            ("list desktop reels", "list_desktop_reels"),
            ("list batch groups", "list_batch_groups"),
            ("browse wiretap tree", "flame_wiretap_tree"),
            ("list flame logs", "list_flame_logs"),
            ("read flame log", "read_flame_log"),
            ("search flame documentation", "search_flame_docs"),
            ("session statistics", "session_stats"),
        ],
    )
    def test_dedicated_tool_resolution(self, query, expected_tool):
        """Dedicated tool queries must resolve to their exact tool name."""
        result = resolve_concept(query)
        assert result is not None, f"No match for query: '{query}'"
        assert result["tool"] == expected_tool, (
            f"Query '{query}' resolved to tool '{result['tool']}', expected '{expected_tool}'"
        )

    @pytest.mark.parametrize(
        "query, expected_tool",
        [
            ("render batch", "execute_python"),
            ("export clip", "execute_python"),
            ("import clips", "execute_python"),
            ("create library", "execute_python"),
            ("delete clip", "execute_python"),
            ("create batch group", "execute_python"),
        ],
    )
    def test_python_api_resolution(self, query, expected_tool):
        """Python API operations must resolve to execute_python."""
        result = resolve_concept(query)
        assert result is not None, f"No match for query: '{query}'"
        assert result["tool"] == expected_tool, (
            f"Query '{query}' resolved to tool '{result['tool']}', expected '{expected_tool}'"
        )


# ── resolve_concept: fuzzy / natural-language queries ────────────────────────


class TestResolveConceptFuzzy:
    """Verify fuzzy matching handles natural-language variations."""

    def test_natural_language_libraries(self):
        """'show me the libraries' should resolve to list_libraries."""
        result = resolve_concept("show me the libraries")
        assert result is not None
        assert result["tool"] == "list_libraries"

    def test_natural_language_project(self):
        """'what project is open' should resolve to get_project_info."""
        result = resolve_concept("what project info")
        assert result is not None
        assert result["tool"] == "get_project_info"

    def test_partial_match_batch(self):
        """'batch render' should match the render batch concept."""
        result = resolve_concept("batch render")
        assert result is not None
        assert "batch" in result["concept"].lower() or "render" in result["concept"].lower()

    def test_gotcha_flame_selection(self):
        """Queries about flame.selection should resolve to get_selected_clips."""
        result = resolve_concept("flame selection does not exist")
        assert result is not None
        assert result["tool"] == "get_selected_clips"

    def test_gotcha_project_libraries_none(self):
        """Queries about project.libraries returning None should match the gotcha entry."""
        result = resolve_concept("project libraries returns none")
        assert result is not None
        assert "libraries" in result["concept"].lower()

    def test_wiretap_query(self):
        """'wiretap tree' should resolve to flame_wiretap_tree."""
        result = resolve_concept("wiretap tree")
        assert result is not None
        assert result["tool"] == "flame_wiretap_tree"

    def test_desktop_clips_query(self):
        """'what is on the desktop' should resolve to desktop reels."""
        result = resolve_concept("desktop reels clips")
        assert result is not None
        assert result["tool"] == "list_desktop_reels"


# ── resolve_concept: no match / edge cases ───────────────────────────────────


class TestResolveConceptNoMatch:
    """Verify resolve_concept returns None for unknown or empty queries."""

    def test_empty_string(self):
        """Empty string must return None."""
        assert resolve_concept("") is None

    def test_whitespace_only(self):
        """Whitespace-only string must return None."""
        assert resolve_concept("   ") is None

    def test_completely_unrelated(self):
        """A query with no matching keywords returns None."""
        assert resolve_concept("quantum entanglement photosynthesis") is None

    def test_gibberish(self):
        """Random gibberish returns None."""
        assert resolve_concept("xyzzy plugh qwfp") is None

    def test_single_nonsense_word(self):
        """A single non-matching word returns None."""
        assert resolve_concept("zzznotaflameword") is None


# ── resolve_concept: result structure ────────────────────────────────────────


class TestResolveConceptResultStructure:
    """Verify the structure of returned results."""

    def test_result_has_all_keys(self):
        """A successful match must contain all required keys."""
        result = resolve_concept("list libraries")
        assert result is not None
        for key in _REQUIRED_KEYS:
            assert key in result, f"Result missing key: '{key}'"

    def test_result_is_dict(self):
        """Result must be a dict (not a copy — it references CONCEPT_MAP entries)."""
        result = resolve_concept("list clips")
        assert isinstance(result, dict)

    def test_none_result_type(self):
        """No-match result must be exactly None, not an empty dict."""
        result = resolve_concept("xyzzy plugh qwfp")
        assert result is None
