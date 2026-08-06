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

TestBatchDrillSuppression (4 tests):
  batch-group content traversal has no dedicated read tool, so soft
  redirects are suppressed when batch context + content drill co-occur;
  a pure batch listing (no drill) and library traversal still redirect.
"""


from flame_mcp.server import _execute_python_impl as execute_python


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


# ═══════════════════════════════════════════════════════════════════════════
# TestModificationIntentSuppression (TAREA 7 — sub-parts 1 & 3)
# ═══════════════════════════════════════════════════════════════════════════

class TestModificationIntentSuppression:
    """copy / move / method-form delete / timeline insert are modification
    intents: a soft redirect on the hierarchy traversal they require
    (.libraries / .reels / .clips) must be suppressed, not fired.

    Before TAREA 7 only create_* / .overwrite / import_clips / flame.delete(
    counted as intent, so a legitimate copy/move/delete/insert that walked the
    hierarchy was redirected as if it were a read query — which forced the
    model to obfuscate the traversal with getattr() to dodge the redirect.
    """

    def test_media_panel_copy_suppresses_redirect(self, mock_bridge):
        """flame.media_panel.copy(...) traversing .reels/.clips → NOT redirected."""
        code = (
            "ws = flame.projects.current_project.current_workspace\n"
            "src = ws.libraries[0].reels[0].clips[0]\n"
            "flame.media_panel.copy(src, ws.libraries[0].reels[1])\n"
        )
        result = execute_python(code)

        mock_bridge.assert_called_once()
        assert "REDIRECT" not in result, (
            f"copy intent should suppress the soft redirect, got: {result!r}"
        )

    def test_media_panel_move_suppresses_redirect(self, mock_bridge):
        """flame.media_panel.move(...) traversing .reels → NOT redirected."""
        code = (
            "flame.media_panel.move(lib.reels[0].clips[0], lib.reels[1])\n"
        )
        result = execute_python(code)

        mock_bridge.assert_called_once()
        assert "REDIRECT" not in result, (
            f"move intent should suppress the soft redirect, got: {result!r}"
        )

    def test_method_delete_suppresses_redirect(self, mock_bridge):
        """Method-form delete (clip.delete()) traversing .reels/.clips → NOT redirected.

        Only ``flame.delete(`` used to count as intent; the equally common
        ``obj.delete()`` method form did not, so the traversal was redirected.
        """
        code = (
            "for c in lib.reels[0].clips:\n"
            "    c.delete()\n"
        )
        result = execute_python(code)

        mock_bridge.assert_called_once()
        assert "REDIRECT" not in result, (
            f"method-form delete should suppress the soft redirect, got: {result!r}"
        )

    def test_timeline_insert_suppresses_redirect(self, mock_bridge):
        """seq.insert(...) traversing .reels/.clips → NOT redirected."""
        code = (
            "dst = lib.reels[1]\n"
            "seq = dst.clips[0]\n"
            "seq.insert(src_clip, insert_time=t, destination_track=0)\n"
        )
        result = execute_python(code)

        mock_bridge.assert_called_once()
        assert "REDIRECT" not in result, (
            f"insert intent should suppress the soft redirect, got: {result!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TestBatchDrillSuppression (Chat 92 in-vivo false positive)
# ═══════════════════════════════════════════════════════════════════════════

class TestBatchDrillSuppression:
    """Reading INSIDE a batch group must stay reachable via execute_python.

    list_reels/list_clips are library-scoped and list_batch_groups returns
    only node/reel counts, so no dedicated tool can answer "which clips are
    in this batch group?".  In-vivo the `.reels` soft pattern matched
    `flame.batch.reels` and redirected to list_reels(library_name) — a
    dead end.  Soft redirects are suppressed when batch context AND content
    drill co-occur; pure listings and library traversal are unaffected.
    """

    def test_current_batch_reels_drill_not_redirected(self, mock_bridge):
        """Iterating flame.batch.reels → clips is allowed (no dedicated tool)."""
        code = (
            "for r in flame.batch.reels:\n"
            "    for c in r.clips:\n"
            "        print(str(c.name))\n"
        )
        result = execute_python(code)

        mock_bridge.assert_called_once()
        assert "REDIRECT" not in result, (
            f"batch drill should suppress the soft redirect, got: {result!r}"
        )

    def test_batch_group_traversal_drill_not_redirected(self, mock_bridge):
        """Finding a batch group, then drilling into its reels, is allowed."""
        code = (
            "bg = [b for b in desktop.batch_groups if str(b.name) == 'Batch'][0]\n"
            "for r in bg.reels:\n"
            "    print(str(r.name), len(r.clips))\n"
        )
        result = execute_python(code)

        mock_bridge.assert_called_once()
        assert "REDIRECT" not in result, (
            f"batch-group drill should suppress the soft redirect, got: {result!r}"
        )

    def test_shelf_reels_drill_not_redirected(self, mock_bridge):
        """Shelf reels only exist on batch groups — drilling them is allowed."""
        code = (
            "for r in flame.batch.shelf_reels:\n"
            "    print(str(r.name), [str(c.name) for c in r.clips])\n"
        )
        result = execute_python(code)

        mock_bridge.assert_called_once()
        assert "REDIRECT" not in result, (
            f"shelf_reels drill should suppress the soft redirect, got: {result!r}"
        )

    def test_pure_batch_listing_still_redirected(self, mock_bridge):
        """Batch-group listing with NO content drill → list_batch_groups() covers it."""
        code = "for bg in desktop.batch_groups:\n    print(str(bg.name))"
        result = execute_python(code)

        assert "REDIRECT" in result, (
            f"pure batch listing should still redirect, got: {result!r}"
        )
        mock_bridge.assert_not_called()

    def test_desktop_sequence_drill_not_redirected(self, mock_bridge):
        """Desktop reel sequences have no dedicated position/listing tool —
        drilling them via execute_python must stay reachable (Chat 92:
        verifying a conform sequence's location was dead-ended twice)."""
        code = (
            "dsk = ws.desktop\n"
            "for rg in dsk.reel_groups:\n"
            "    for r in rg.reels:\n"
            "        for s in (r.sequences or []):\n"
            "            print(str(s.name))\n"
        )
        result = execute_python(code)

        mock_bridge.assert_called_once()
        assert "REDIRECT" not in result, (
            f"desktop drill should suppress the soft redirect, got: {result!r}"
        )

    def test_pure_desktop_reel_listing_still_redirected(self, mock_bridge):
        """Desktop reel listing with NO content drill → list_desktop_reels()."""
        code = "for rg in ws.desktop.reel_groups:\n    print(str(rg.name))"
        result = execute_python(code)

        assert "REDIRECT" in result, (
            f"pure desktop listing should still redirect, got: {result!r}"
        )
        mock_bridge.assert_not_called()
