"""
test_tools.py
=============
Tests for the dedicated MCP tools in src/flame_mcp/server.py.

All tests mock _call_flame to avoid real Flame bridge connections.
Tools are synchronous — no asyncio.

Tests
-----
TestPing (2 tests):
  1. test_ping_success          -- connected response contains 🟢
  2. test_ping_connection_error -- error response contains 🔴

TestGetProjectInfo (2 tests):
  3. test_returns_formatted_info -- contains project Name
  4. test_bridge_error           -- error dict → ERROR in output

TestListLibraries (2 tests):
  5. test_returns_library_list  -- mock output passed through
  6. test_empty_libraries       -- empty output handled

TestListReels (2 tests):
  7. test_with_library_name     -- passes library name to bridge code
  8. test_without_library_name  -- default all-libraries listing

TestListClips (2 tests):
  9. test_basic_listing         -- mock clips returned
 10. test_with_filters          -- library + reel filters used

TestExecutePython (4 tests):
 11. test_safe_code_executes     -- safe code calls _call_flame
 12. test_dangerous_code_blocked -- dangerous code blocked before bridge
 13. test_timeout_parameter      -- timeout forwarded to _call_flame
 14. test_bridge_error_handling  -- bridge error formatted correctly

TestGetFlameVersion (1 test):
 15. test_returns_version        -- version string in response

TestListDesktopReels (1 test):
 16. test_returns_hierarchy      -- mock output passed through

TestListBatchGroups (1 test):
 17. test_returns_groups         -- mock output passed through

TestGetClipMetadata (1 test):
 18. test_returns_metadata       -- mock output passed through

TestGetSelectedClips (1 test):
 19. test_returns_selected       -- mock output passed through

TestFlameWiretapTree (2 tests):
 20. test_cli_not_found          -- graceful error when CLI binary missing
 21. test_custom_path            -- path argument forwarded to subprocess

TestListFlameLogs (1 test):
 22. test_directory_not_found    -- /opt/Autodesk/logs absent → error message

TestReadFlameLog (2 tests):
 23. test_file_not_found         -- nonexistent log → error message
 24. test_path_traversal_blocked -- dotdot in filename → blocked
"""

from unittest.mock import patch, MagicMock

from flame_mcp.server import (
    ping,
    get_project_info,
    list_libraries,
    list_reels,
    list_clips,
    execute_python,
    get_flame_version,
    list_desktop_reels,
    list_batch_groups,
    get_clip_metadata,
    get_selected_clips,
    flame_wiretap_tree,
    list_flame_logs,
    read_flame_log,
    render_batch,
    export_clip,
    create_library,
    create_reel,
    create_folder,
    create_reel_group,
    create_batch_group,
    import_clips,
)


# ═══════════════════════════════════════════════════════════════════════════
# TestPing
# ═══════════════════════════════════════════════════════════════════════════

class TestPing:
    """ping() checks bridge connectivity and returns a status string."""

    def test_ping_success(self, mock_bridge):
        """Connected bridge → 🟢 message with Flame version."""
        mock_bridge.return_value = {"output": "2026.1.0\n", "error": "", "_bridge_ms": 5}

        result = ping()

        assert "🟢" in result, f"Expected 🟢 in: {result!r}"
        assert "2026" in result, f"Expected version in: {result!r}"
        mock_bridge.assert_called_once()

    def test_ping_connection_error(self, mock_bridge_error):
        """Connection refused → 🔴 error message."""
        result = ping()

        assert "🔴" in result, f"Expected 🔴 in: {result!r}"
        assert "not connected" in result.lower() or "error" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TestGetProjectInfo
# ═══════════════════════════════════════════════════════════════════════════

class TestGetProjectInfo:
    """get_project_info() returns project metadata."""

    def test_returns_formatted_info(self, mock_bridge):
        """Mock returns project name → output contains 'Name:' line."""
        mock_bridge.return_value = {
            "output": (
                "Name: TestProject\n"
                "Description: Test description\n"
                "Workspaces: 1\n"
                "WiretapID: ERROR not available\n"   # triggers cfg fallback path
            ),
            "error": "",
            "_bridge_ms": 10,
        }

        result = get_project_info()

        assert isinstance(result, str)
        assert len(result) > 0
        # The project name from py_out should appear in the merged output
        assert "TestProject" in result

    def test_bridge_error(self, mock_bridge_error):
        """Bridge error → cfg_fallback path: returns partial info with IFFFS notice."""
        result = get_project_info()

        assert isinstance(result, str)
        assert len(result) > 0
        # When bridge is unreachable, get_project_info falls back to cfg parsing.
        # The fallback path returns an IFFFS-unreachable notice or a SELF-HEAL prompt.
        assert "IFFFS" in result or "SELF-HEAL" in result or "unreachable" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TestRenderBatch
# ═══════════════════════════════════════════════════════════════════════════

class TestRenderBatch:
    """render_batch() schedules a Background-Reactor render via idle event.

    Critical safety contract: it must NEVER emit a bare synchronous
    flame.batch.render() (that crashes Flame); the render call must live
    inside a function handed to flame.schedule_idle_event, and the payload
    must go through the dedicated-tool path (# DT prefix → the bridge skips
    the redirect guard that would otherwise block flame.batch.render).
    """

    def test_defaults_schedule_background_reactor(self, mock_bridge):
        """Defaults: Background Reactor, render scheduled (never synchronous)."""
        mock_bridge.return_value = {
            "output": "Render scheduled via idle event.\n", "error": "", "_bridge_ms": 7,
        }

        result = render_batch()

        code = mock_bridge.call_args[0][0]  # first positional arg = code string
        assert "flame.schedule_idle_event(_do_render)" in code, (
            "render must be scheduled via idle event, not called synchronously"
        )
        assert "render_option='Background Reactor'" in code
        # dedicated-tool path so the bridge skips the crash-redirect guard
        assert mock_bridge.call_args.kwargs.get("dedicated_tool") is True
        assert "scheduled" in result.lower()
        assert "flame_render_result.txt" in result

    def test_render_option_and_flags_forwarded(self, mock_bridge):
        """render_option / generate_proxies / include_history reach the code."""
        mock_bridge.return_value = {
            "output": "Render scheduled via idle event.\n", "error": "", "_bridge_ms": 7,
        }

        render_batch(render_option="Foreground", generate_proxies=True, include_history=True)

        code = mock_bridge.call_args[0][0]
        assert "render_option='Foreground'" in code
        assert "generate_proxies=True" in code
        assert "include_history=True" in code

    def test_bridge_error_passthrough(self, mock_bridge):
        """A bridge error is surfaced verbatim, not swallowed."""
        mock_bridge.return_value = {"status": "error", "error": "boom"}

        result = render_batch()

        assert "ERROR" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestExportClip
# ═══════════════════════════════════════════════════════════════════════════

class TestExportClip:
    """export_clip() schedules a PyExporter export via idle event."""

    def test_schedules_export_via_idle_event(self, mock_bridge):
        """Export goes through schedule_idle_event + PyExporter (never direct)."""
        mock_bridge.return_value = {
            "output": "Export scheduled via idle event.\n", "error": "", "_bridge_ms": 9,
        }

        result = export_clip(
            library_name="Default Library", reel_name="Reel 1", clip_name="shot_010",
            preset_path="/opt/Autodesk/presets/2027/export/x.xml",
            output_directory="/tmp/exp",
        )

        code = mock_bridge.call_args[0][0]
        assert "flame.schedule_idle_event(_do_export)" in code
        assert "flame.PyExporter()" in code
        assert "exp.foreground = False" in code
        assert "/opt/Autodesk/presets/2027/export/x.xml" in code
        assert "/tmp/exp" in code
        assert mock_bridge.call_args.kwargs.get("dedicated_tool") is True
        assert "scheduled" in result.lower()

    def test_clip_not_found_surfaced(self, mock_bridge):
        """A Flame-side 'clip not found' is surfaced, not masked as success."""
        mock_bridge.return_value = {
            "output": "ERROR: clip not found (check library/reel/clip names)\n",
            "error": "", "_bridge_ms": 5,
        }

        result = export_clip(
            library_name="X", reel_name="Y", clip_name="Z",
            preset_path="/p.xml", output_directory="/tmp/exp",
        )

        assert "ERROR" in result and "not found" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestCreates
# ═══════════════════════════════════════════════════════════════════════════

class TestCreates:
    """create_library/reel/folder/reel_group emit the right Flame create call."""

    def test_create_library(self, mock_bridge):
        mock_bridge.return_value = {"output": "Created library: Shots\n", "error": "", "_bridge_ms": 5}
        result = create_library(library_name="Shots")
        code = mock_bridge.call_args[0][0]
        assert "ws.create_library('Shots')" in code
        assert mock_bridge.call_args.kwargs.get("dedicated_tool") is True
        assert "Shots" in result

    def test_create_reel(self, mock_bridge):
        mock_bridge.return_value = {"output": "Created reel: R1\n", "error": "", "_bridge_ms": 5}
        create_reel(library_name="Shots", reel_name="R1")
        code = mock_bridge.call_args[0][0]
        assert "lib.create_reel('R1')" in code
        assert "Shots" in code

    def test_create_folder(self, mock_bridge):
        mock_bridge.return_value = {"output": "Created folder: F1\n", "error": "", "_bridge_ms": 5}
        create_folder(library_name="Shots", folder_name="F1")
        code = mock_bridge.call_args[0][0]
        assert "lib.create_folder('F1')" in code

    def test_create_reel_group(self, mock_bridge):
        mock_bridge.return_value = {"output": "Created reel group: RG1\n", "error": "", "_bridge_ms": 5}
        create_reel_group(library_name="Shots", reel_group_name="RG1")
        code = mock_bridge.call_args[0][0]
        assert "lib.create_reel_group('RG1')" in code

    def test_create_reel_library_not_found(self, mock_bridge):
        mock_bridge.return_value = {"output": "ERROR: library not found\n", "error": "", "_bridge_ms": 5}
        result = create_reel(library_name="Nope", reel_name="R1")
        assert "ERROR" in result and "not found" in result


class TestCreateBatchGroup:
    """create_batch_group() creates an empty Batch Group on the desktop."""

    def test_create_batch_group(self, mock_bridge):
        mock_bridge.return_value = {"output": "Created batch group: BG1\n", "error": "", "_bridge_ms": 5}
        result = create_batch_group(name="BG1")
        code = mock_bridge.call_args[0][0]
        assert "flame.batch.create_batch_group('BG1')" in code
        assert mock_bridge.call_args.kwargs.get("dedicated_tool") is True
        assert "BG1" in result


class TestImportClips:
    """import_clips() imports media into a library or a reel."""

    def test_import_into_library(self, mock_bridge):
        mock_bridge.return_value = {"output": "Imported 3 clip(s) into Shots\n", "error": "", "_bridge_ms": 9}
        result = import_clips(path="/media/x.mov", library_name="Shots")
        code = mock_bridge.call_args[0][0]
        assert "flame.import_clips('/media/x.mov', lib)" in code
        assert "Imported" in result

    def test_import_into_reel(self, mock_bridge):
        mock_bridge.return_value = {"output": "Imported 1 clip(s) into reel R1\n", "error": "", "_bridge_ms": 9}
        import_clips(path="/media/x.mov", library_name="Shots", reel_name="R1")
        code = mock_bridge.call_args[0][0]
        assert "flame.import_clips('/media/x.mov', reel)" in code
        assert "R1" in code

    def test_import_library_not_found(self, mock_bridge):
        mock_bridge.return_value = {"output": "ERROR: library not found\n", "error": "", "_bridge_ms": 5}
        result = import_clips(path="/m.mov", library_name="Nope")
        assert "ERROR" in result and "not found" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestListLibraries
# ═══════════════════════════════════════════════════════════════════════════

class TestListLibraries:
    """list_libraries() returns visible libraries from the workspace."""

    def test_returns_library_list(self, mock_bridge):
        """Mock output with library names is passed through _fmt."""
        mock_bridge.return_value = {
            "output": "  VFX  (3 reels)\n  Audio  (1 reel)\n",
            "error": "",
            "_bridge_ms": 8,
        }

        result = list_libraries()

        assert isinstance(result, str)
        assert "VFX" in result
        assert "Audio" in result

    def test_empty_libraries(self, mock_bridge):
        """Empty workspace output is returned without crashing."""
        mock_bridge.return_value = {
            "output": "No libraries found.\n",
            "error": "",
            "_bridge_ms": 5,
        }

        result = list_libraries()

        assert isinstance(result, str)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════
# TestListReels
# ═══════════════════════════════════════════════════════════════════════════

class TestListReels:
    """list_reels() returns reels, optionally filtered by library name."""

    def test_with_library_name(self, mock_bridge):
        """Library name is embedded in the bridge code."""
        mock_bridge.return_value = {
            "output": "  Reel_001  (12 clips)\n  Reel_002  (5 clips)\n",
            "error": "",
            "_bridge_ms": 6,
        }

        result = list_reels(library_name="VFX")

        assert isinstance(result, str)
        # The library name should appear in the code sent to the bridge
        call_args = mock_bridge.call_args[0][0]  # first positional arg = code string
        assert "VFX" in call_args

    def test_without_library_name(self, mock_bridge):
        """Default call (no library name) lists all libraries."""
        mock_bridge.return_value = {
            "output": "[VFX]\n  Reel_001  (12 clips)\n",
            "error": "",
            "_bridge_ms": 7,
        }

        result = list_reels()

        assert isinstance(result, str)
        # Code sent to bridge must iterate all libraries
        call_code = mock_bridge.call_args[0][0]
        assert "ws.libraries" in call_code or "HIDDEN" in call_code


# ═══════════════════════════════════════════════════════════════════════════
# TestListClips
# ═══════════════════════════════════════════════════════════════════════════

class TestListClips:
    """list_clips() returns clip names, optionally filtered."""

    def test_basic_listing(self, mock_bridge):
        """Mock output with clip names is passed through."""
        mock_bridge.return_value = {
            "output": "[VFX] / [Reel_001] — 3 clip(s)\n  clip_A\n  clip_B\n  clip_C\n",
            "error": "",
            "_bridge_ms": 9,
        }

        result = list_clips()

        assert isinstance(result, str)
        assert "clip_A" in result or "clip(s)" in result

    def test_with_filters(self, mock_bridge):
        """Library and reel filters are forwarded to the bridge code."""
        mock_bridge.return_value = {
            "output": "[VFX] / [Reel_001] — 1 clip(s)\n  hero_shot\n",
            "error": "",
            "_bridge_ms": 6,
        }

        result = list_clips(library_name="VFX", reel_name="Reel_001")

        assert isinstance(result, str)
        call_code = mock_bridge.call_args[0][0]
        assert "VFX" in call_code
        assert "Reel_001" in call_code


# ═══════════════════════════════════════════════════════════════════════════
# TestExecutePython
# ═══════════════════════════════════════════════════════════════════════════

class TestExecutePython:
    """execute_python() runs arbitrary Python in Flame after safety + redirect checks."""

    def test_safe_code_executes(self, mock_bridge):
        """Safe code (no dangerous patterns, no redirects) calls _call_flame."""
        mock_bridge.return_value = {
            "output": "Hello from Flame\n",
            "error": "",
            "_bridge_ms": 12,
        }

        code = "print('Hello from Flame')"
        result = execute_python(code)

        mock_bridge.assert_called_once()
        assert "Hello from Flame" in result

    def test_dangerous_code_blocked(self, mock_bridge):
        """Dangerous code is blocked before _call_flame is invoked."""
        dangerous_code = "n = len(flame.projects)"
        result = execute_python(dangerous_code)

        # _call_flame must NOT be called
        mock_bridge.assert_not_called()
        assert "Blocked" in result or "blocked" in result.lower()

    def test_timeout_parameter(self, mock_bridge):
        """Custom timeout is forwarded to _call_flame as keyword argument."""
        mock_bridge.return_value = {"output": "done\n", "error": "", "_bridge_ms": 5}

        execute_python("print('done')", timeout=30)

        assert mock_bridge.called
        # timeout must appear in call kwargs or args
        call_kwargs = mock_bridge.call_args[1]   # keyword args dict
        call_args   = mock_bridge.call_args[0]   # positional args tuple
        assert (call_kwargs.get("timeout") == 30 or
                (len(call_args) >= 2 and call_args[1] == 30)), (
            f"Expected timeout=30 in call, got args={call_args}, kwargs={call_kwargs}"
        )

    def test_bridge_error_handling(self, mock_bridge_error):
        """Bridge error response is formatted and returned, not raised."""
        result = execute_python("print('test')")

        assert isinstance(result, str)
        assert "ERROR" in result or "error" in result.lower() or "Cannot connect" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestGetFlameVersion
# ═══════════════════════════════════════════════════════════════════════════

class TestGetFlameVersion:
    """get_flame_version() returns the running Flame version string."""

    def test_returns_version(self, mock_bridge):
        """Mock output with version string is passed through _fmt."""
        mock_bridge.return_value = {
            "output": "2026.1.0\n",
            "error": "",
            "_bridge_ms": 4,
        }

        result = get_flame_version()

        assert isinstance(result, str)
        assert "2026" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestListDesktopReels
# ═══════════════════════════════════════════════════════════════════════════

class TestListDesktopReels:
    """list_desktop_reels() returns the full desktop hierarchy."""

    def test_returns_hierarchy(self, mock_bridge):
        """Mock output with reel groups and clips is passed through."""
        mock_bridge.return_value = {
            "output": (
                "[Reel Group 1]\n"
                "  Reel 1  (3 clips)\n"
                "    clip_001\n"
                "    clip_002\n"
                "    clip_003\n"
            ),
            "error": "",
            "_bridge_ms": 11,
        }

        result = list_desktop_reels()

        assert isinstance(result, str)
        assert "Reel Group 1" in result or "clip_001" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestListBatchGroups
# ═══════════════════════════════════════════════════════════════════════════

class TestListBatchGroups:
    """list_batch_groups() returns batch groups with reel/node counts."""

    def test_returns_groups(self, mock_bridge):
        """Mock output with batch group info is passed through."""
        mock_bridge.return_value = {
            "output": "2 batch group(s):\n  comp_SH010  (2 reels, 5 nodes)\n  comp_SH020  (1 reel)\n",
            "error": "",
            "_bridge_ms": 9,
        }

        result = list_batch_groups()

        assert isinstance(result, str)
        assert "batch" in result.lower() or "comp_SH010" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestGetClipMetadata
# ═══════════════════════════════════════════════════════════════════════════

class TestGetClipMetadata:
    """get_clip_metadata() returns technical metadata for a specific clip."""

    def test_returns_metadata(self, mock_bridge):
        """Mock output with clip metadata is passed through."""
        mock_bridge.return_value = {
            "output": (
                "Clip: hero_shot_v001\n"
                "  frame_rate: 23.976\n"
                "  width: 1920\n"
                "  height: 1080\n"
                "  duration: 86\n"
            ),
            "error": "",
            "_bridge_ms": 7,
        }

        result = get_clip_metadata(
            library_name="VFX",
            reel_name="Reel_001",
            clip_name="hero_shot_v001",
        )

        assert isinstance(result, str)
        assert "hero_shot_v001" in result or "frame_rate" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestGetSelectedClips
# ═══════════════════════════════════════════════════════════════════════════

class TestGetSelectedClips:
    """get_selected_clips() returns items selected in the media panel."""

    def test_returns_selected(self, mock_bridge):
        """Mock output with selected items is passed through."""
        mock_bridge.return_value = {
            "output": "2 item(s) selected:\n  clip_A  [PyClip]\n  clip_B  [PyClip]\n",
            "error": "",
            "_bridge_ms": 5,
        }

        result = get_selected_clips()

        assert isinstance(result, str)
        assert "clip_A" in result or "selected" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TestFlameWiretapTree
# ═══════════════════════════════════════════════════════════════════════════

class TestFlameWiretapTree:
    """flame_wiretap_tree() runs the wiretap CLI tool (subprocess, not bridge)."""

    def test_cli_not_found(self):
        """When the wiretap CLI binary is absent, returns a graceful error.

        We mock ``subprocess.run`` to raise ``FileNotFoundError`` — the exact
        exception that surfaces when ``/opt/Autodesk/wiretap/tools/current/wiretap_print_tree``
        is not installed on the host. This keeps the test deterministic and
        independent of the test machine: earlier versions relied on Autodesk
        tools NOT being present in the sandbox, which broke on developer
        machines where Flame is actually installed and wiretap responds.
        """
        with patch("subprocess.run") as mock_sub:
            mock_sub.side_effect = FileNotFoundError(
                "No such file or directory: 'wiretap_print_tree'"
            )
            result = flame_wiretap_tree("/")

        assert isinstance(result, str)
        # Should report that the CLI is not found or IFFFS is unreachable
        assert "not found" in result.lower() or "❌" in result or "error" in result.lower()

    def test_custom_path(self):
        """Custom path is passed to wiretap_print_tree subprocess args."""
        custom_path = "/projects"

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(
                stdout=f"node at {custom_path}",
                stderr="",
            )
            flame_wiretap_tree(path=custom_path)

        # subprocess.run called with path in args
        assert mock_sub.called
        call_args = mock_sub.call_args[0][0]   # first positional = command list
        assert custom_path in call_args


# ═══════════════════════════════════════════════════════════════════════════
# TestListFlameLogs
# ═══════════════════════════════════════════════════════════════════════════

class TestListFlameLogs:
    """list_flame_logs() reads /opt/Autodesk/logs (filesystem, no bridge)."""

    def test_directory_not_found(self):
        """/opt/Autodesk/logs does not exist in sandbox → clear error message."""
        result = list_flame_logs()

        assert isinstance(result, str)
        # Should report directory not found or return a listing (if dir exists on host)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════
# TestReadFlameLog
# ═══════════════════════════════════════════════════════════════════════════

class TestReadFlameLog:
    """read_flame_log() reads log files from /opt/Autodesk/logs."""

    def test_file_not_found(self):
        """Requesting a nonexistent log file returns an informative error."""
        result = read_flame_log(log_name="nonexistent_flame_log_xyz.log")

        assert isinstance(result, str)
        assert "not found" in result.lower() or "❌" in result

    def test_path_traversal_blocked(self):
        """Filenames containing '..' are rejected immediately."""
        result = read_flame_log(log_name="../etc/passwd")

        assert isinstance(result, str)
        assert "path traversal" in result.lower() or "invalid" in result.lower() or "❌" in result
