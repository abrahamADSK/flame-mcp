"""
test_tool_permissions.py
========================
Tests for the destructive-op auto-approval gate (audit finding).

install.sh step 8 and server.py::_sync_tool_permissions used to pre-approve
EVERY @mcp.tool — including execute_python, execute_plan and the destructive
undo tool — into permissions.allow. Combined with a (then) dead undo/audit
subsystem, a single LLM hallucination could delete a populated client library
with no prompt, no undo, no trace.

The fix: discover_mcp_tools(include_destructive=False) excludes _DST tools so
they fall through to the Claude Code permission prompt (explicit operator
confirmation). Only read-only (_RO) and non-destructive write (_RW) tools are
auto-approved.
"""

import flame_mcp.server as server

_SOURCE = open(server.__file__, encoding="utf-8").read()


# Tools that MUST require explicit confirmation (never auto-approved).
_DESTRUCTIVE = {
    "mcp__flame__execute_python",
    "mcp__flame__execute_plan",
    "mcp__flame__create_library",
    "mcp__flame__create_reel",
    "mcp__flame__create_folder",
    "mcp__flame__create_reel_group",
    "mcp__flame__create_batch_group",
    "mcp__flame__create_sequence",
    "mcp__flame__rename_segments",
    "mcp__flame__import_clips",
    "mcp__flame__timeline_insert",
    "mcp__flame__timeline_overwrite",
    "mcp__flame__render_batch",
    "mcp__flame__export_clip",
    "mcp__flame__undo_last_operation",
}

# A few clearly read-only tools that SHOULD be auto-approved.
_READ_ONLY_SAMPLE = {
    "mcp__flame__ping",
    "mcp__flame__list_libraries",
    "mcp__flame__list_reels",
    "mcp__flame__get_project_info",
    "mcp__flame__operation_history",
    "mcp__flame__collect_media_paths",
}


class TestDiscoverMcpTools:
    def test_destructive_excluded_when_flag_false(self):
        safe = server.discover_mcp_tools(_SOURCE, include_destructive=False)
        for tool in _DESTRUCTIVE:
            assert tool not in safe, f"{tool} must NOT be auto-approved"

    def test_read_only_tools_are_included(self):
        safe = server.discover_mcp_tools(_SOURCE, include_destructive=False)
        for tool in _READ_ONLY_SAMPLE:
            assert tool in safe, f"{tool} should be auto-approved"

    def test_include_destructive_is_superset(self):
        full = server.discover_mcp_tools(_SOURCE, include_destructive=True)
        safe = server.discover_mcp_tools(_SOURCE, include_destructive=False)
        assert safe < full, "full set must strictly contain the safe set"
        # Every excluded tool must be a destructive one.
        assert (full - safe) == _DESTRUCTIVE

    def test_undo_tool_is_gated(self):
        """Regression: the _DST undo tool was being auto-approved alongside
        the (then) dead undo subsystem — the worst-case combination."""
        safe = server.discover_mcp_tools(_SOURCE, include_destructive=False)
        assert "mcp__flame__undo_last_operation" not in safe
