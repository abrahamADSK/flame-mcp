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


class TestListReelsRule:
    def test_picks_first_populated_reel(self):
        text = (
            "[Default Library]\n"
            "  Reel 1  (3 clips)\n"
            "  Reel 2  (0 clips)\n"
            "[Assets]\n"
            "  Main  (5 clips)\n"
        )
        out = s._suggest_after_list_reels(text)
        assert len(out) == 1
        assert out[0]["tool"] == "list_clips"
        assert out[0]["params_hint"] == {
            "library_name": "Default Library",
            "reel_name": "Reel 1",
        }

    def test_skips_empty_reels_within_library(self):
        text = (
            "[Default Library]\n"
            "  Reel 1  (0 clips)\n"
            "  Reel 2  (2 clips)\n"
        )
        out = s._suggest_after_list_reels(text)
        assert out[0]["params_hint"]["reel_name"] == "Reel 2"

    def test_skips_hidden_libraries(self):
        text = (
            "[Timeline FX]\n"
            "  Phantom  (1 clips)\n"
            "[Default Library]\n"
            "  Main  (4 clips)\n"
        )
        out = s._suggest_after_list_reels(text)
        assert out[0]["params_hint"]["library_name"] == "Default Library"

    def test_no_library_header_returns_empty(self):
        # Filtered case (list_reels with library_name=...) — no [Library] header.
        text = "  Reel 1  (3 clips)\n  Reel 2  (1 clips)\n"
        assert s._suggest_after_list_reels(text) == []

    def test_library_not_found_returns_empty(self):
        assert s._suggest_after_list_reels("Library 'Foo' not found.") == []

    def test_only_empty_reels_returns_empty(self):
        text = "[Default Library]\n  Reel 1  (0 clips)\n"
        assert s._suggest_after_list_reels(text) == []

    def test_singular_clip_still_matches(self):
        text = "[Default Library]\n  Reel 1  (1 clip)\n"
        out = s._suggest_after_list_reels(text)
        assert out and out[0]["params_hint"]["reel_name"] == "Reel 1"


class TestListClipsRule:
    def test_picks_first_clip_under_first_header(self):
        text = (
            "[Default Library] / [Reel 1] — 3 clip(s)\n"
            "  clip_01  00:00:10\n"
            "  clip_02  00:00:08\n"
            "  clip_03  00:00:12\n"
        )
        out = s._suggest_after_list_clips(text)
        assert len(out) == 1
        assert out[0]["tool"] == "get_clip_metadata"
        assert out[0]["params_hint"] == {
            "library_name": "Default Library",
            "reel_name": "Reel 1",
            "clip_name": "clip_01",
        }

    def test_handles_clip_without_duration(self):
        text = (
            "[Assets] / [Main] — 1 clip(s)\n"
            "  solo_clip\n"
        )
        out = s._suggest_after_list_clips(text)
        assert out[0]["params_hint"]["clip_name"] == "solo_clip"

    def test_ignores_ellipsis_more_line(self):
        text = (
            "[Assets] / [Main] — 60 clip(s)\n"
            "  … and 10 more (use limit=0 to see all)\n"
        )
        # Ellipsis line is not a valid clip — rule yields empty.
        assert s._suggest_after_list_clips(text) == []

    def test_ellipsis_after_valid_clips_is_ignored(self):
        text = (
            "[Assets] / [Main] — 60 clip(s)\n"
            "  clip_01\n"
            "  clip_02\n"
            "  … and 58 more (use limit=0 to see all)\n"
        )
        out = s._suggest_after_list_clips(text)
        assert out[0]["params_hint"]["clip_name"] == "clip_01"

    def test_no_header_returns_empty(self):
        assert s._suggest_after_list_clips("No reels matched filter 'X'.") == []

    def test_header_without_clips_returns_empty(self):
        text = "[Assets] / [Empty] — 0 clip(s)\n"
        assert s._suggest_after_list_clips(text) == []


class TestListFlameLogsRule:
    def test_picks_first_log_after_header(self):
        text = (
            "📁 /opt/Autodesk/logs  (3 files)\n"
            "\n"
            "  flame.log                                      150 KB  2026-04-22 10:15\n"
            "  wiretap.log                                     45 KB  2026-04-22 09:50\n"
            "  python.log                                       2 KB  2026-04-20 14:30\n"
        )
        out = s._suggest_after_list_flame_logs(text)
        assert len(out) == 1
        assert out[0]["tool"] == "read_flame_log"
        assert out[0]["params_hint"]["log_name"] == "flame.log"
        assert out[0]["params_hint"]["lines"] == 200
        assert "Error" in out[0]["params_hint"]["grep"]

    def test_no_logs_returns_empty(self):
        assert s._suggest_after_list_flame_logs(
            "No log files found in /opt/Autodesk/logs"
        ) == []

    def test_error_response_returns_empty(self):
        assert s._suggest_after_list_flame_logs(
            "❌ Log directory not found: /opt/Autodesk/logs"
        ) == []

    def test_error_listing_returns_empty(self):
        assert s._suggest_after_list_flame_logs(
            "❌ Error listing logs: permission denied"
        ) == []


class TestRegistryContract:
    def test_registry_has_list_libraries(self):
        assert "list_libraries" in s.SUGGESTION_RULES

    def test_registry_has_all_rules(self):
        for tool in (
            "list_libraries", "list_reels", "list_clips", "list_flame_logs",
        ):
            assert tool in s.SUGGESTION_RULES, f"{tool} missing from registry"
