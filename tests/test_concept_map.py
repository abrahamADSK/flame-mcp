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
    CRITICAL_BEHAVIORS,
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


# ── Entity hierarchy entries ──────────────────────────────────────────────


_EXPECTED_ENTITY_TYPES = {
    "Project", "Workspace", "Library", "Reel", "Clip",
    "Desktop", "ReelGroup", "BatchGroup", "Node",
    "Sequence", "Segment", "Selection",
}


class TestEntityHierarchy:
    """Verify the Flame Object Model entity entries from Section 3.1."""

    def test_entity_entries_exist(self):
        """All 12 entity types have dedicated entries in the concept map."""
        entity_types_in_map = {
            e.get("entity_type") for e in CONCEPT_MAP if e.get("entity_type")
        }
        missing = _EXPECTED_ENTITY_TYPES - entity_types_in_map
        assert not missing, f"Missing entity types: {missing}"

    def test_resolve_concept_returns_entity(self):
        """resolve_concept('Library') returns an entry with entity_type."""
        result = resolve_concept("flame entity: Library")
        assert result is not None
        assert result.get("entity_type") == "Library"
        assert "libraries" in result["api_path"].lower()

    def test_resolve_clip_entity(self):
        """resolve_concept for Clip returns hierarchy path + str() note."""
        result = resolve_concept("flame entity: Clip")
        assert result is not None
        assert result.get("entity_type") == "Clip"
        assert "str()" in result["notes"] or "PyAttribute" in result["notes"]

    def test_resolve_sequence_entity(self):
        """resolve_concept for Sequence returns timeline hierarchy."""
        result = resolve_concept("flame entity: Sequence")
        assert result is not None
        assert result.get("entity_type") == "Sequence"
        assert "versions" in result["notes"].lower()

    def test_resolve_batch_group_entity(self):
        """resolve_concept for BatchGroup returns desktop path."""
        result = resolve_concept("flame entity: BatchGroup")
        assert result is not None
        assert result.get("entity_type") == "BatchGroup"
        assert "schedule_idle_event" in result["notes"]

    def test_entity_type_field_values(self):
        """All entity_type values are valid Flame class names."""
        for entry in CONCEPT_MAP:
            et = entry.get("entity_type")
            if et is not None:
                assert et in _EXPECTED_ENTITY_TYPES, (
                    f"Unknown entity_type '{et}' in concept '{entry['concept']}'"
                )


# ── Critical behaviors ────────────────────────────────────────────────────


class TestCriticalBehaviors:
    """Verify the CRITICAL_BEHAVIORS structured reference block."""

    def test_critical_behaviors_complete(self):
        """All 4 critical behaviors are present."""
        assert len(CRITICAL_BEHAVIORS) == 4
        ids = {b["id"] for b in CRITICAL_BEHAVIORS}
        assert ids == {"str_wrap", "projects_not_iterable", "no_name_subscript", "schedule_idle_event"}

    def test_behavior_structure(self):
        """Each behavior has required keys."""
        for b in CRITICAL_BEHAVIORS:
            assert "id" in b
            assert "summary" in b
            assert "applies_to" in b
            assert isinstance(b["applies_to"], list)
            assert len(b["applies_to"]) > 0
            assert "example" in b

    def test_str_wrap_applies_to_clip(self):
        """str_wrap behavior applies to Clip."""
        b = next(b for b in CRITICAL_BEHAVIORS if b["id"] == "str_wrap")
        assert "Clip" in b["applies_to"]

    def test_schedule_idle_applies_to_batch(self):
        """schedule_idle_event behavior applies to BatchGroup."""
        b = next(b for b in CRITICAL_BEHAVIORS if b["id"] == "schedule_idle_event")
        assert "BatchGroup" in b["applies_to"]

    def test_all_applies_to_reference_valid_entities(self):
        """Every entity referenced in applies_to exists in entity map."""
        entity_types_in_map = {
            e.get("entity_type") for e in CONCEPT_MAP if e.get("entity_type")
        }
        for b in CRITICAL_BEHAVIORS:
            for et in b["applies_to"]:
                assert et in entity_types_in_map, (
                    f"Behavior '{b['id']}' references '{et}' but no entity entry exists"
                )


class TestPipelineRecipes:
    """The two cross-server workflow entries (Chat 98).

    They carry a multi-step ``recipe`` that is deliberately NOT scored by the
    matcher: a procedure names many tools, and scoring it let the conform
    entry outrank 'import clips' for the query "import clips into a reel"
    (measured while adding these).
    """

    def _entry(self, concept):
        return next(e for e in CONCEPT_MAP if e["concept"] == concept)

    def test_conform_resolves_from_a_bare_verb(self):
        """The word the user actually types must reach the recipe."""
        for query in ("conform", "conform the main cut", "conform this cut"):
            match = resolve_concept(query)
            assert match is not None, f"no match for {query!r}"
            assert match["concept"] == "conform cut"

    def test_fpt_link_concept_resolves(self):
        match = resolve_concept("which fpt project is this linked to")
        assert match is not None
        assert match["tool"] == "fpt_link"

    def test_recipes_are_not_scored(self):
        """A recipe must not pull queries away from single-operation concepts."""
        from flame_mcp.concept_map import _score_entry, _tokenize

        conform = self._entry("conform cut")
        # Tokens that appear ONLY in the recipe must contribute nothing.
        recipe_only = _tokenize(conform["recipe"]) - (
            _tokenize(conform["concept"])
            | _tokenize(conform["tool"])
            | _tokenize(conform["api_path"])
            | _tokenize(conform["notes"])
        )
        assert recipe_only, "recipe adds no vocabulary — test would be vacuous"
        assert _score_entry(recipe_only, conform) == 0.0

    def test_conform_does_not_steal_import_clips(self):
        """The regression this design prevents."""
        assert resolve_concept("import clips into a reel")["concept"] == "import clips"

    def test_conform_recipe_states_the_load_bearing_gotchas(self):
        recipe = self._entry("conform cut")["recipe"].lower()
        assert "edl" in recipe          # no tool imports one
        assert "choice_required" in recipe  # the Task selector is a gate
        assert "one-based" in recipe    # record frame vs edit_in
        assert "to_desktop" in recipe   # library sequences are locked

    def test_fpt_link_recipe_forbids_the_mismatch_claim(self):
        recipe = self._entry("fpt link")["recipe"].lower()
        assert "different" in recipe and "mismatch" in recipe


class TestConformRecipeHardening:
    """Chat 98 in-vivo: the recipe let the console ask five separate times.

    Each assertion below pins one question it must NOT ask again.
    """

    def _recipe(self):
        return next(
            e for e in CONCEPT_MAP if e["concept"] == "conform cut"
        )["recipe"].lower()

    def test_probes_the_task_graph_before_asking_for_a_step(self):
        """openclip_create already suggests a Task from upstream_tasks."""
        recipe = self._recipe()
        assert "upstream_tasks" in recipe
        assert "suggested" in recipe

    def test_questions_are_batched_into_one(self):
        assert "at most once" in self._recipe()

    def test_desktop_is_decided_not_asked(self):
        recipe = self._recipe()
        assert "to_desktop=true" in recipe
        assert "not a question" in recipe

    def test_one_master_sequence_not_one_per_sequence(self):
        """The console read 'a library per Sequence' as 'a timeline per
        Sequence' and asked which one was meant."""
        assert "not one per sequence" in self._recipe()

    def test_names_the_clip_path_when_the_template_cannot_resolve(self):
        """A project with no PipelineConfiguration broke the whole run."""
        recipe = self._recipe()
        assert "pipelineconfiguration" in recipe
        assert "finishing/clip/" in recipe


class TestConformNaming:
    """Reel names carry information, not echoes (Chat 98 user report).

    The unhardened recipe said 'a library per Sequence with a reel', so the
    console named each reel after its library — SEQ001/SEQ001, a duplicated
    hierarchy with no information. The names are now explicit.
    """

    def _recipe(self):
        return next(
            e for e in CONCEPT_MAP if e["concept"] == "conform cut"
        )["recipe"]

    def test_sequence_reels_are_named_sources(self):
        assert "'sources'" in self._recipe()
        assert "never name the reel after its library" in self._recipe()

    def test_master_lives_in_conform_library(self):
        recipe = self._recipe()
        assert "'Conform'" in recipe
        assert "'master'" in recipe
        assert "the SEQUENCE carries the Cut's name" in recipe


class TestBuildCompRecipe:
    """The comp-build recipe (Chat 98, user-specified layer rules)."""

    def _entry(self):
        return next(e for e in CONCEPT_MAP
                    if e["concept"].startswith("build comp"))

    def test_operator_commands_resolve_to_it(self):
        for q in ("build comp", "expand multilayer node",
                  "compose shadow and light layers"):
            m = resolve_concept(q)
            assert m is not None and m["concept"].startswith("build comp"), q

    def test_layer_identification_rules(self):
        recipe = self._entry()["recipe"]
        assert "shadow_mult" in recipe
        assert "charmatte" in recipe
        assert "INVERTED" in recipe
        # lights match by substring, both cases; discs are TWO distinct layers
        assert "'Light' or 'light'" in recipe
        assert "'disco' and 'disco y beam' are DISTINCT" in recipe

    def test_comp_structure(self):
        recipe = self._entry()["recipe"]
        assert "MULTIPLY" in recipe          # shadow first
        assert "SCREEN" in recipe            # lights cascade
        assert "beams LAST" in recipe        # club formula, Chat 92
        assert recipe.index("SHADOW FIRST") < recipe.index("LIGHTS IN CASCADE")

    def test_every_batch_call_is_main_threaded(self):
        recipe = self._entry()["recipe"]
        assert "schedule_idle_event" in recipe
        assert "even reading node lists or sockets" in recipe

    def test_one_shot_at_a_time_and_chain_closed(self):
        """Operator correction (Chat 98): the Write File CONNECTION is part
        of the wiring — what stays manual is the Create Open Clip check and
        the render, never the connection."""
        recipe = self._entry()["recipe"]
        assert "ONE shot at a time" in recipe
        assert "Write File FRONT" in recipe
        assert "never the connection" in recipe

    def test_operator_wiring_semantics(self):
        """The result travels on FRONT (Chat 98 in-vivo correction): beauty
        enters the shadow Comp's Front, each Result feeds the next Front,
        layers arrive on Back, charmatte gates via the SECOND matte input."""
        recipe = self._entry()["recipe"]
        assert "beauty (rgba) -> FRONT" in recipe
        assert "Result -> the NEXT Comp's FRONT" in recipe
        assert "SECOND matte input" in recipe
        assert "FULL attributes list" in recipe  # invert found by dump, not fuzzy search

    def test_layout_is_a_diagonal_not_organize(self):
        recipe = self._entry()["recipe"]
        assert "top-left to bottom-right" in recipe
        assert "Do NOT rely on" in recipe and "organize()" in recipe

    def test_socket_names_never_guessed(self):
        recipe = self._entry()["recipe"]
        assert "never guess them" in recipe
        assert "connect_nodes(output_node, output_socket_name" in recipe


class TestBatchTemplateClearsTheGuards:
    """The recipe's batch template must pass every guard FIRST TIME (Chat 98).

    A 'create a batch group per shot' order burned the operator's remaining
    session tokens: each guard objection (redirect, next() default, None-check
    form) cost a full model round-trip. The recipe now carries a verbatim
    template; these tests run it through the REAL guard layers so a future
    guard change that would reject it fails CI instead of billing the
    operator.
    """

    def _template(self):
        entry = next(e for e in CONCEPT_MAP
                     if e["concept"].startswith("build comp"))
        return entry["recipe"].split("```\n", 1)[1].split("\n```", 1)[0]

    def test_template_compiles(self):
        compile(self._template(), "<tpl>", "exec")

    def test_template_clears_the_safety_layer(self):
        from flame_mcp.safety import _check_dangerous
        assert not _check_dangerous(self._template())

    def test_template_clears_the_ast_validator(self):
        from flame_mcp._ast_validate import validate_python
        v = validate_python(self._template())
        assert v.ok, getattr(v, "issues", v)

    def test_template_carries_creation_intent(self):
        """Matching the creation pattern is what suppresses the soft
        redirects AND routes it through the write throttle."""
        import re
        assert re.search(r"schedule_idle_event|create_batch_group\s*\(",
                         self._template())

    def test_template_is_main_threaded_with_file_result(self):
        tpl = self._template()
        assert "flame.schedule_idle_event(_do_build)" in tpl
        assert "json.dump" in tpl


class TestTernaryGuardAccepted:
    """`y if x else z` is a valid None guard (Chat 98 false positive)."""

    def test_ternary_form_passes(self):
        from flame_mcp.safety import _check_dangerous
        code = (
            "lib = next((l for l in ws.libraries if str(l.name) == 'X'), None)\n"
            "name = str(lib.name) if lib else 'missing'\n"
            "print(name)\n"
        )
        warning = _check_dangerous(code)
        assert not (warning and "None check" in str(warning)), warning

    def test_unguarded_next_still_flagged(self):
        from flame_mcp.safety import _check_dangerous
        code = (
            "lib = next((l for l in ws.libraries if str(l.name) == 'X'), None)\n"
            "print(str(lib.name))\n"
        )
        warning = _check_dangerous(code)
        assert warning and "None check" in str(warning), "guard must still catch it"


class TestCompBatchRouting:
    """Comp-batch phrasings reach the recipe directly (Chat 98 in-vivo gap).

    Without the routing vocabulary every phrasing fuzzy-matched the generic
    'list batch groups' concept and the recipe was only reachable via
    'conform' — three failed queries per session, each a billed turn. The
    matcher does no stemming: 'batches' and 'batch' are distinct tokens.
    """

    @pytest.mark.parametrize("query", [
        "create the comp batches for all shots",
        "setup comp batch",
        "create comp batches",
    ])
    def test_comp_batch_phrasings_reach_the_recipe(self, query):
        m = resolve_concept(query)
        assert m is not None and m["concept"].startswith("build comp"), query

    def test_no_theft_from_batch_concepts(self):
        assert resolve_concept("list batch groups")["concept"] == "list batch groups"
        assert resolve_concept("render batch")["concept"] == "render batch"
