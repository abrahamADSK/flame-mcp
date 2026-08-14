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

TestGetProjectInfo (4 tests):
  3. test_returns_formatted_info -- contains project Name
  4. test_bridge_error           -- error dict → ERROR in output
  4a. test_wiretap_xml_uses_real_project_tags -- real 2027 XML parsed, no SELF-HEAL
  4b. test_wiretap_partial_result_falls_back_to_cfg -- partial XML → .cfg fallback

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
    _execute_python_impl as execute_python,
    get_flame_version,
    list_desktop_reels,
    list_batch_groups,
    get_clip_metadata,
    get_selected_clips,
    _flame_wiretap_tree_impl as flame_wiretap_tree,
    list_flame_logs,
    read_flame_log,
    _render_batch_impl as render_batch,
    _export_clip_impl as export_clip,
    create_library,
    create_reel,
    create_folder,
    create_reel_group,
    create_batch_group,
    create_sequence,
    _import_clips_impl as import_clips,
    timeline_insert,
    timeline_overwrite,
)


# Real Flame 2027 PROJECT-node Wiretap XML, captured 2026-06-11 via
#   wiretap_get_metadata -h localhost:IFFFS -n /projects/FPT202525_basic_test -m XML
# Ground truth for the get_project_info parser: the project node exposes
# FrameWidth/FrameHeight/FrameDepth/FieldDominance/ColourPolicyName
# (NOT the Width/Height/BitDepth/ScanMode names used by clip nodes).
_REAL_PROJECT_XML = (
    "<Project><Name>FPT202525_basic_test</Name><Nickname></Nickname>"
    "<Description></Description>"
    "<ShotgunProjectName>FPT202525_basic_test</ShotgunProjectName>"
    "<CreationDate>01/16/26 12:35:19</CreationDate>"
    "<CatalogDir>/opt/Autodesk/clip/stonefs/FPT202525_basic_test.prj</CatalogDir>"
    "<SetupDir>FPT202525_basic_test</SetupDir><Partition>stonefs</Partition>"
    "<Version>2025.2</Version><FrameWidth>1920</FrameWidth>"
    "<FrameHeight>1080</FrameHeight><FrameDepth>8-bit</FrameDepth>"
    "<AspectRatio>1.77778</AspectRatio>"
    "<FieldDominance>PROGRESSIVE</FieldDominance>"
    "<ProxyWidth>960</ProxyWidth><ProxyWidthHint>0.500000</ProxyWidthHint>"
    "<ProxyMinFrameSize>720</ProxyMinFrameSize>"
    "<ProxyQuality>lanczos</ProxyQuality><ProxyDepth>8-bit</ProxyDepth>"
    "<HdrMode>Dolby Vision 2.9</HdrMode><HdrCmuType>iCMU</HdrCmuType>"
    "<HdrMasteringId>7</HdrMasteringId>"
    "<ColourPolicyName></ColourPolicyName>"
    "<OCIOConfigFile>/opt/Autodesk/project/FPT202525_basic_test/"
    "colour_mgmt/config.ocio</OCIOConfigFile><ProcessMode>2</ProcessMode>"
    "<IntermediatesProfile>65541</IntermediatesProfile>"
    "<FrameRate>23.976 fps</FrameRate>"
    "<DefaultStartFrame>1</DefaultStartFrame></Project>"
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

    def test_wiretap_xml_uses_real_project_tags(self, mock_bridge):
        """Real 2027 project XML → resolution/depth/scan parsed, no SELF-HEAL.

        Regression for the Chat 64 gotcha (empty wiretap metadata on fresh
        sessions): the parser used guessed tag names (Width/BitDepth/
        ScanMode/ColourSpace) that do not exist in the PROJECT-node XML, so
        Resolution/Bit depth/Scan mode rendered '—' and SELF-HEAL fired on
        every call. The fixture below is a real Flame 2027 dump
        (wiretap_get_metadata -m XML on /projects/FPT202525_basic_test,
        captured 2026-06-11) — the project node uses FrameWidth/FrameHeight/
        FrameDepth/FieldDominance, unlike clip nodes.
        """
        from flame_mcp import _workspace_snapshot
        _workspace_snapshot.invalidate()  # defeat the 12s read cache between tests
        mock_bridge.return_value = {
            "output": (
                "Name: FPT202525_basic_test\n"
                "Description: —\n"
                "Workspaces: 1\n"
                "WiretapID: /projects/FPT202525_basic_test\n"
            ),
            "error": "",
            "_bridge_ms": 10,
        }
        with patch("flame_mcp.server.subprocess.run") as run:
            run.return_value = MagicMock(stdout=_REAL_PROJECT_XML, returncode=0)
            result = get_project_info()

        assert "Frame rate: 23.976 fps" in result
        assert "Resolution: 1920x1080" in result
        assert "Bit depth: 8-bit" in result
        assert "Scan mode: PROGRESSIVE" in result
        # Complete wiretap data → no SELF-HEAL, no .cfg fallback engaged
        assert "SELF-HEAL" not in result
        assert "source: .cfg" not in result
        # The documented stream selector for wiretap_get_metadata is -m (not -s)
        argv = run.call_args[0][0]
        assert "-m" in argv and "XML" in argv and "-s" not in argv

    def test_wiretap_partial_result_falls_back_to_cfg(self, mock_bridge):
        """FrameRate-only XML (required Resolution missing) → .cfg fallback.

        A partial wiretap answer must not be displayed as authoritative:
        before the fix the fallback guard required ALL fields to be dashes,
        so 'Resolution: —x—' leaked through whenever FrameRate matched.
        """
        from flame_mcp import _workspace_snapshot
        _workspace_snapshot.invalidate()  # defeat the 12s read cache between tests
        mock_bridge.return_value = {
            "output": (
                "Name: NoSuchProj_UnitTest\n"
                "Description: —\n"
                "Workspaces: 1\n"
                "WiretapID: /projects/NoSuchProj_UnitTest\n"
            ),
            "error": "",
            "_bridge_ms": 10,
        }
        with patch("flame_mcp.server.subprocess.run") as run:
            run.return_value = MagicMock(
                stdout="<Project><FrameRate>24 fps</FrameRate></Project>",
                returncode=0,
            )
            result = get_project_info()

        # The bug symptom — a dashed Resolution presented as wiretap truth —
        # must never appear; the .cfg fallback path takes over instead
        # (for a nonexistent project that yields the IFFFS/.cfg notice).
        assert "Resolution: —x—" not in result
        assert "source: .cfg" in result or "IFFFS" in result


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

    def test_create_sequence(self, mock_bridge):
        mock_bridge.return_value = {"output": "Created sequence: SEQ\n", "error": "", "_bridge_ms": 5}
        result = create_sequence(library_name="Shots", reel_name="R1", sequence_name="SEQ")
        code = mock_bridge.call_args[0][0]
        # Regression guard: the sequence MUST be created in the resolved reel.
        # The original bug called flame.media_panel.create_sequence(name=...),
        # which raises AttributeError on Flame 2027 (PyMediaPanel has no such
        # method) and never targets the resolved reel. Confirmed in-vivo on
        # Flame 2027 (build 2027.pr238). Correct API is PyReel.create_sequence.
        assert "reel.create_sequence(name='SEQ')" in code
        assert "media_panel.create_sequence" not in code
        assert mock_bridge.call_args.kwargs.get("dedicated_tool") is True
        assert "SEQ" in result

    def test_create_sequence_reel_not_found(self, mock_bridge):
        mock_bridge.return_value = {"output": "ERROR: reel not found\n", "error": "", "_bridge_ms": 5}
        result = create_sequence(library_name="Shots", reel_name="Nope", sequence_name="SEQ")
        assert "ERROR" in result and "not found" in result

    def test_create_sequence_duration_passed_as_pytime(self, mock_bridge):
        # Regression guard (Chat 63 gotcha): the tool had no duration parameter
        # at all, so "create a 50-frame sequence" silently produced Flame's
        # 1-frame default. The frame count must reach PyReel.create_sequence
        # wrapped in flame.PyTime(frames).
        mock_bridge.return_value = {"output": "Created sequence: SEQ (50 frames)\n", "error": "", "_bridge_ms": 5}
        result = create_sequence(library_name="Shots", reel_name="R1", sequence_name="SEQ", duration=50)
        code = mock_bridge.call_args[0][0]
        assert "reel.create_sequence(name='SEQ', duration=flame.PyTime(50))" in code
        assert "SEQ" in result

    def test_create_sequence_duration_omitted_keeps_flame_default(self, mock_bridge):
        # duration=0 (the default) must NOT emit a duration kwarg, preserving
        # Flame's own default behaviour for callers that never asked for one.
        mock_bridge.return_value = {"output": "Created sequence: SEQ (1 frames)\n", "error": "", "_bridge_ms": 5}
        create_sequence(library_name="Shots", reel_name="R1", sequence_name="SEQ")
        code = mock_bridge.call_args[0][0]
        assert "duration=" not in code


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


class TestTimeline:
    """timeline_insert/overwrite resolve sequence + source clip then dispatch."""

    def test_insert(self, mock_bridge):
        mock_bridge.return_value = {"output": "Timeline insert: OK\n", "error": "", "_bridge_ms": 9}
        result = timeline_insert(
            sequence_library="Shots", sequence_reel="R1", sequence_name="SEQ",
            source_library="Media", source_reel="R2", source_clip="clipA",
        )
        code = mock_bridge.call_args[0][0]
        assert "seq.insert(*_edit_args)" in code
        assert "record_frame = None" in code
        assert '"sequences"' in code and '"clips"' in code
        assert mock_bridge.call_args.kwargs.get("dedicated_tool") is True
        assert "OK" in result

    def test_overwrite(self, mock_bridge):
        mock_bridge.return_value = {"output": "Timeline overwrite: OK\n", "error": "", "_bridge_ms": 9}
        timeline_overwrite(
            sequence_library="Shots", sequence_reel="R1", sequence_name="SEQ",
            source_library="Media", source_reel="R2", source_clip="clipA",
        )
        code = mock_bridge.call_args[0][0]
        assert "seq.overwrite(*_edit_args)" in code

    def test_sequence_not_found(self, mock_bridge):
        mock_bridge.return_value = {"output": "ERROR: sequence not found\n", "error": "", "_bridge_ms": 5}
        result = timeline_insert(
            sequence_library="X", sequence_reel="Y", sequence_name="Z",
            source_library="A", source_reel="B", source_clip="C",
        )
        assert "ERROR" in result and "not found" in result

    def test_default_refuses_library_lock_and_offers_desktop(self, mock_bridge):
        # Library sequences raise "Clip is locked" (verified in-vivo, Flame 2027).
        # Default (to_desktop=False) must NOT move anything: it catches the lock
        # and returns a LOCKED offer. The move lives only behind `elif to_desktop:`.
        mock_bridge.return_value = {"output": "LOCKED: ...\n", "error": "", "_bridge_ms": 5}
        timeline_insert(
            sequence_library="Shots", sequence_reel="R1", sequence_name="SEQ",
            source_library="Media", source_reel="R2", source_clip="clipA",
        )
        code = mock_bridge.call_args[0][0]
        assert "to_desktop = False" in code
        assert 'except RuntimeError' in code and '"locked"' in code
        assert "to_desktop=True" in code  # the offer text
        # auto-move is impossible in default mode: move is gated under elif to_desktop
        assert "elif to_desktop:" in code
        assert "flame.media_panel.move(seq, dreel)" in code
        # default path still dispatches the plain edit
        assert "seq.insert(*_edit_args)" in code

    def test_to_desktop_moves_then_edits(self, mock_bridge):
        # Explicit confirmation: move the sequence to the desktop, then edit it.
        mock_bridge.return_value = {"output": "Timeline insert: OK - moved 'SEQ' ...\n", "error": "", "_bridge_ms": 9}
        timeline_overwrite(
            sequence_library="Shots", sequence_reel="R1", sequence_name="SEQ",
            source_library="Media", source_reel="R2", source_clip="clipA",
            to_desktop=True,
        )
        code = mock_bridge.call_args[0][0]
        assert "to_desktop = True" in code
        assert "flame.media_panel.move(seq, dreel)" in code
        assert "target.overwrite(*_edit_args)" in code

    def test_resolves_sequence_from_desktop_after_move(self, mock_bridge):
        # After a to_desktop move the sequence is no longer in any library:
        # the template must also resolve it from the desktop reels and edit
        # it there directly (desktop sequences carry no library lock) —
        # Chat 92 conform: events 2..N of a multi-event conform hit this.
        mock_bridge.return_value = {
            "output": "Timeline overwrite: OK - sequence resolved on the desktop and edited there\n",
            "error": "", "_bridge_ms": 9}
        result = timeline_overwrite(
            sequence_library="Shots", sequence_reel="R1", sequence_name="SEQ",
            source_library="Media", source_reel="R2", source_clip="clipA",
            record_frame=201,
        )
        code = mock_bridge.call_args[0][0]
        assert "seq_on_desktop" in code
        assert 'getattr(_r, "sequences", None)' in code
        assert "elif seq_on_desktop:" in code
        assert "checked sequence library/reel/name and the desktop reels" in code
        assert "OK" in result

    def test_record_frame_explicit(self, mock_bridge):
        # record_frame places the edit at an explicit sequence frame via
        # flame.PyTime (conform driver: CutItem edit_in positions, Chat 91).
        mock_bridge.return_value = {"output": "Timeline overwrite: OK\n", "error": "", "_bridge_ms": 9}
        timeline_overwrite(
            sequence_library="Shots", sequence_reel="R1", sequence_name="SEQ",
            source_library="Media", source_reel="R2", source_clip="clipA",
            record_frame=101,
        )
        code = mock_bridge.call_args[0][0]
        assert "record_frame = 101" in code
        assert "flame.PyTime(record_frame)" in code
        assert "seq.overwrite(*_edit_args)" in code

    def test_record_frame_defaults_to_none(self, mock_bridge):
        # Without record_frame the edit uses Flame's default position: the
        # generated code must carry record_frame = None (1-arg dispatch).
        mock_bridge.return_value = {"output": "Timeline insert: OK\n", "error": "", "_bridge_ms": 9}
        timeline_insert(
            sequence_library="Shots", sequence_reel="R1", sequence_name="SEQ",
            source_library="Media", source_reel="R2", source_clip="clipA",
        )
        code = mock_bridge.call_args[0][0]
        assert "record_frame = None" in code
        assert "_edit_args = (src,) if record_frame is None else" in code


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


class TestTimelineStaleWrapperGuard:
    """A successful edit must never be reported as a failure (Chat 98).

    Moving the sequence to the desktop makes Flame resync the workspace,
    which can invalidate the Python wrappers the template still holds.
    In-vivo, reading dreel.name AFTER the move raised a C++
    unordered_map::at exception — the overwrite had already landed (clip
    placed, sequence on the desktop), but the tool returned an error and
    the conform stopped at 1 of 6 shots.
    """

    def _desktop_code(self):
        from unittest.mock import patch
        with patch("flame_mcp.server._call_flame") as mock_bridge:
            mock_bridge.return_value = {
                "output": "Timeline overwrite: OK\n", "error": "", "_bridge_ms": 9}
            timeline_overwrite(
                sequence_library="Shots", sequence_reel="R1",
                sequence_name="SEQ", source_library="Media", source_reel="R2",
                source_clip="clipA", to_desktop=True,
            )
            return mock_bridge.call_args[0][0]

    def test_reel_name_is_captured_before_the_move(self):
        code = self._desktop_code()
        branch = code.split("elif to_desktop:", 1)[1]
        assert branch.index("dname = str(dreel.name)") < branch.index(
            "flame.media_panel.move(seq, dreel)")

    def test_reporting_cannot_fail_the_landed_edit(self):
        code = self._desktop_code()
        branch = code.split("elif to_desktop:", 1)[1]
        # The success/failure prints are inside a try, and the fallback still
        # says OK — the edit has landed by then.
        assert branch.index("target.overwrite(*_edit_args)") < branch.index("try:")
        assert "post-edit" in branch
        assert "report degraded" in branch


class TestTimelineMainThread:
    """Timeline edits run on Flame's MAIN thread via schedule_idle_event
    (Chat 98, CER-backed).

    Two SIGSEGVs killed the sixth overwrite of a conform; the crash
    backtrace shows Flame dying on its main thread REDRAWING the editdesk
    UI (MenuDoDrawItem → lxUploadBufferToTexture → null) right after an
    autosave, while the edit ran on the bridge worker thread. An idle event
    runs on the main thread — between redraws and after any in-flight save —
    so the race is impossible by construction. Same documented-safe pattern
    as render_batch and structural deletes.
    """

    def _code(self, **kw):
        from unittest.mock import patch
        args = dict(
            sequence_library="Conform", sequence_reel="master",
            sequence_name="Master v1", source_library="SEQ001",
            source_reel="sources", source_clip="SEQ001_SH001",
        )
        args.update(kw)
        with patch("flame_mcp.server._call_flame") as mock_bridge:
            mock_bridge.return_value = {
                "output": "Timeline overwrite: OK\n", "error": "", "_bridge_ms": 9}
            timeline_overwrite(**args)
            return mock_bridge.call_args[0][0]

    def test_edit_is_scheduled_not_direct(self):
        code = self._code(to_desktop=True)
        assert "flame.schedule_idle_event(_do_edit)" in code
        # the whole edit body lives inside the scheduled function
        body = code.split("def _do_edit():", 1)[1].split(
            "flame.schedule_idle_event", 1)[0]
        assert "target.overwrite(*_edit_args)" in body
        assert "flame.media_panel.move(seq, dreel)" in body

    def test_cheap_probe_precedes_the_schedule(self):
        """Chat 63 invariant: a read-only probe confirms a loaded project
        BEFORE anything is queued on the main thread."""
        code = self._code()
        assert code.index("flame.projects.current_project.name") < code.index(
            "schedule_idle_event")

    def test_result_comes_back_through_a_file(self):
        code = self._code()
        assert "_result_path" in code
        assert '"message"' in code
        # bounded poll inside the bridge's 30 s exec guard
        assert "time.monotonic() + 20" in code

    def test_timeout_message_says_the_edit_may_still_land(self):
        """A poll timeout is not a failure: the idle event may simply not
        have run yet. The message must say so instead of inviting a blind
        retry that would double the edit."""
        code = self._code()
        assert "may still land" in code

    def test_errors_inside_the_idle_event_are_captured(self):
        """An exception on the main thread has nowhere to propagate — it
        must land in the result file, not vanish."""
        code = self._code()
        idle_body = code.split("def _do_edit():", 1)[1].split(
            "flame.schedule_idle_event", 1)[0]
        assert 'print("ERROR: " + repr(_exc))' in idle_body


class TestListBatchGroupsMainThread:
    """list_batch_groups drills node lists on Flame's MAIN thread (Chat 98).

    A worker-thread drill (getNodeList) on freshly built batch groups killed
    Flame mid-listing — the shell log ends inside the drill. Batch state is
    UI-backed, so even READS of it get the idle-event + file-result harness.
    """

    def _code(self):
        from unittest.mock import patch
        from flame_mcp import _workspace_snapshot
        from flame_mcp.server import list_batch_groups
        # The workspace read-cache would satisfy a repeated identical call
        # without touching the bridge — clear it so call_args is real.
        _workspace_snapshot.invalidate()
        fn = getattr(list_batch_groups, "fn", list_batch_groups)
        with patch("flame_mcp.server._call_flame") as mock_bridge:
            mock_bridge.return_value = {
                "output": "1 batch group(s):\n", "error": "", "_bridge_ms": 9}
            fn()
            return mock_bridge.call_args

    def test_listing_is_scheduled_not_direct(self):
        args = self._code()
        code = args[0][0]
        assert "flame.schedule_idle_event(_do_list)" in code
        body = code.split("def _do_list():", 1)[1].split(
            "flame.schedule_idle_event", 1)[0]
        assert "desktop.batch_groups" in body

    def test_poll_fits_inside_the_socket_timeout(self):
        args = self._code()
        code = args[0][0]
        assert "time.monotonic() + 20" in code
        assert args.kwargs.get("timeout") == 30
