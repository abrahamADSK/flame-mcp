"""
test_redirect.py
================
Tests for the execute_python redirect system.

execute_python inspects the submitted code for patterns that match a
dedicated tool (e.g. ws.libraries → list_libraries()).  When a match is
found it returns a redirect message instead of forwarding to Flame.

Soft redirects (_SOFT_REDIRECT_PATTERNS) are suppressed when the code
also contains a creation/modification intent keyword (create_sequence,
.overwrite, import_clips, etc.).  Hard redirects (not in the soft set)
always fire regardless of intent.

All tests patch _call_flame so no real Flame connection is needed.

Tests
-----
TestRedirectPatterns (5 tests):
  1. test_redirect_get_project_info   -- current_project.name → get_project_info()
  2. test_redirect_list_libraries     -- ws.libraries → list_libraries()
  3. test_redirect_list_reels         -- .reels → list_reels()
  4. test_redirect_flame_selection    -- flame.selection → get_selected_clips()
  5. test_redirect_wiretap_tree       -- wiretap_print_tree → flame_wiretap_tree()

TestSoftRedirectSuppression (3 tests):
  6. test_soft_redirect_with_creation_intent  -- ws.libraries + create_sequence → NOT redirected
  7. test_hard_redirect_with_creation_intent  -- flame.selection + create_sequence → IS redirected
  8. test_no_creation_intent                  -- ws.libraries without intent → IS redirected
"""

import pytest

from flame_mcp_server import execute_python


# ═══════════════════════════════════════════════════════════════════════════
# TestRedirectPatterns
# ═══════════════════════════════════════════════════════════════════════════

class TestRedirectPatterns:
    """execute_python redirects to dedicated tools when pattern matches."""

    def test_redirect_get_project_info(self, mock_bridge):
        """Code querying current_project.name redirects to get_project_info()."""
        code = "print(current_project.name)"
        result = execute_python(code)

        assert "REDIRECT" in result or "Use" in result, (
            f"Expected redirect message, got: {result!r}"
        )
        mock_bridge.assert_not_called()  # _call_flame must not be invoked

    def test_redirect_list_libraries(self, mock_bridge):
        """Code iterating ws.libraries redirects to list_libraries()."""
        code = "for lib in ws.libraries:\n    print(str(lib.name))"
        result = execute_python(code)

        assert "REDIRECT" in result, f"Expected REDIRECT in: {result!r}"
        mock_bridge.assert_not_called()

    def test_redirect_list_reels(self, mock_bridge):
        """Code accessing .reels attribute redirects to list_reels()."""
        code = "for reel in lib.reels:\n    print(str(reel.name))"
        result = execute_python(code)

        assert "REDIRECT" in result, f"Expected REDIRECT in: {result!r}"
        mock_bridge.assert_not_called()

    def test_redirect_flame_selection(self, mock_bridge):
        """Code using flame.selection redirects to get_selected_clips().

        flame.selection does not exist — the correct API is
        flame.media_panel.selected_entries.
        """
        code = "items = flame.selection\nprint(items)"
        result = execute_python(code)

        assert "REDIRECT" in result, f"Expected REDIRECT in: {result!r}"
        mock_bridge.assert_not_called()

    def test_redirect_wiretap_tree(self, mock_bridge):
        """Code calling wiretap_print_tree redirects to flame_wiretap_tree()."""
        code = "wiretap_print_tree('/projects')"
        result = execute_python(code)

        assert "REDIRECT" in result, f"Expected REDIRECT in: {result!r}"
        mock_bridge.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# TestSoftRedirectSuppression
# ═══════════════════════════════════════════════════════════════════════════

class TestSoftRedirectSuppression:
    """Soft redirects are suppressed when creation/modification intent is detected."""

    def test_soft_redirect_with_creation_intent(self, mock_bridge):
        """ws.libraries (soft redirect) + create_sequence( (creation intent) → NOT redirected.

        Traversing the hierarchy (library → reel) is required for creation ops,
        so the soft redirect for ws.libraries is suppressed.
        """
        code = (
            "ws = flame.projects.current_project.current_workspace\n"
            "lib = ws.libraries[0]\n"
            "reel = lib.reels[0]\n"
            "reel.create_sequence(name='SH010', nb_tracks=1, start_frame=1001)\n"
            "print('done')\n"
        )
        result = execute_python(code)

        # _call_flame must be called (redirect was suppressed)
        mock_bridge.assert_called_once()
        assert "REDIRECT" not in result, (
            f"Soft redirect should be suppressed with creation intent, got: {result!r}"
        )

    def test_hard_redirect_with_creation_intent(self, mock_bridge):
        """flame.selection (hard redirect) + creation intent → STILL redirected.

        flame.selection is NOT in _SOFT_REDIRECT_PATTERNS (it uses the wrong
        API regardless of intent), so the redirect always fires.
        """
        code = (
            "items = flame.selection\n"
            "reel.create_sequence(name='SH010')\n"
        )
        result = execute_python(code)

        assert "REDIRECT" in result, (
            f"Hard redirect should fire even with creation intent, got: {result!r}"
        )
        mock_bridge.assert_not_called()

    def test_no_creation_intent(self, mock_bridge):
        """ws.libraries without creation intent → IS redirected.

        A soft redirect fires when there is no creation/modification keyword
        in the submitted code.
        """
        code = "for lib in ws.libraries:\n    print(str(lib.name))"
        result = execute_python(code)

        assert "REDIRECT" in result, (
            f"Soft redirect should fire without creation intent, got: {result!r}"
        )
        mock_bridge.assert_not_called()
