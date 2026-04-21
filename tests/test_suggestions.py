"""Tests for flame_mcp.suggestions (text-response hint contract)."""

from __future__ import annotations

import pytest

from flame_mcp import suggestions as s


@pytest.fixture
def restore_rules():
    original = dict(s.SUGGESTION_RULES)
    yield s.SUGGESTION_RULES
    s.SUGGESTION_RULES.clear()
    s.SUGGESTION_RULES.update(original)


class TestHelperContract:
    def test_unknown_tool_returns_verbatim(self):
        assert s.maybe_annotate_with_suggestions("not_a_tool", "hello") == "hello"

    def test_empty_suggestions_is_noop(self, restore_rules):
        restore_rules["list_libraries"] = lambda _: []
        # A response that would not trigger the built-in rule.
        assert s.maybe_annotate_with_suggestions("list_libraries", "  Default Library  (1 reel)") == "  Default Library  (1 reel)"

    def test_non_empty_suggestions_append_block(self, restore_rules):
        restore_rules["list_libraries"] = lambda _: [
            {"tool": "t", "reason": "why", "params_hint": {"k": "v"}}
        ]
        out = s.maybe_annotate_with_suggestions("list_libraries", "body")
        assert out.startswith("body")
        assert "➡ Next you could also:" in out
        assert "why → t(k='v')" in out

    def test_already_annotated_is_idempotent(self, restore_rules):
        restore_rules["list_libraries"] = lambda _: [
            {"tool": "t", "reason": "new", "params_hint": {}}
        ]
        payload = "body\n\n➡ Next you could also:\n  • existing → t"
        assert s.maybe_annotate_with_suggestions("list_libraries", payload) == payload

    def test_rule_raising_returns_verbatim(self, restore_rules):
        def boom(_):
            raise RuntimeError("nope")
        restore_rules["list_libraries"] = boom
        assert s.maybe_annotate_with_suggestions("list_libraries", "body") == "body"

    def test_suggestions_capped_at_three(self, restore_rules):
        restore_rules["list_libraries"] = lambda _: [
            {"tool": f"t{i}", "reason": "r", "params_hint": {}} for i in range(7)
        ]
        out = s.maybe_annotate_with_suggestions("list_libraries", "body")
        assert out.count("  • ") == 3


class TestKillSwitch:
    def test_env_var_disables_annotation(self, monkeypatch, restore_rules):
        restore_rules["list_libraries"] = lambda _: [
            {"tool": "t", "reason": "r", "params_hint": {}}
        ]
        monkeypatch.setenv("FLAME_MCP_DISABLE_SUGGESTIONS", "1")
        assert s.maybe_annotate_with_suggestions("list_libraries", "body") == "body"


class TestListLibrariesRule:
    def test_empty_response_returns_no_suggestion(self):
        assert s._suggest_after_list_libraries("No libraries found.") == []

    def test_picks_first_visible_library(self):
        text = (
            "  Default Library  (3 reels, 1 folder)\n"
            "  Assets  (2 reels)\n"
        )
        out = s._suggest_after_list_libraries(text)
        assert len(out) == 1
        assert out[0]["tool"] == "list_reels"
        assert out[0]["params_hint"]["library_name"] == "Default Library"

    def test_skips_hidden_libraries(self):
        text = (
            "  Timeline FX  (0 reels)\n"
            "  Default Library  (1 reel)\n"
        )
        out = s._suggest_after_list_libraries(text)
        assert out[0]["params_hint"]["library_name"] == "Default Library"

    def test_unrecognised_format_returns_empty(self):
        # A bare error message without any `  NAME  (...)` line.
        assert s._suggest_after_list_libraries("Flame is offline.") == []


class TestRegistryContract:
    def test_registry_has_list_libraries(self):
        assert "list_libraries" in s.SUGGESTION_RULES
