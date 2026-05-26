"""
test_safety.py
==============
Tests for _check_dangerous() — the safety module that detects code
patterns known to crash or destabilise Autodesk Flame.

Uses regex scanning and AST analysis to detect dangerous patterns.
Returns a formatted error string on detection, None for safe code.

Tests
-----
TestDangerousPatterns (10 tests):
  1. test_len_flame_projects          -- len(flame.projects)
  2. test_iterate_flame_projects      -- for x in flame.projects
  3. test_index_flame_projects        -- flame.projects[0]
  4. test_project_libraries           -- flame.projects.current_project.libraries
  5. test_batch_render                -- flame.batch.render()
  6. test_import_wiretap              -- import wiretap (regex path)
  7. test_ast_import_wiretap          -- import wiretap (AST Import node path)
  8. test_ast_batch_render            -- obj.batch.render() (AST only; no flame. prefix)
  9. test_safe_code_passes            -- safe code returns None
 10. test_multiple_hits               -- code with two patterns returns both
"""


from flame_mcp.safety import _check_dangerous


# ═══════════════════════════════════════════════════════════════════════════
# TestDangerousPatterns
# ═══════════════════════════════════════════════════════════════════════════

class TestDangerousPatterns:
    """_check_dangerous() detects all known Flame crash patterns."""

    # ── 1. len(flame.projects) ────────────────────────────────────────────

    def test_len_flame_projects(self):
        """len(flame.projects) is detected — PyProjectSelector has no __len__."""
        code = "n = len(flame.projects)\nprint(n)"
        result = _check_dangerous(code)

        assert result is not None, "Expected dangerous pattern to be detected"
        assert "Blocked" in result or "blocked" in result.lower()
        assert "projects" in result.lower()

    # ── 2. for x in flame.projects ───────────────────────────────────────

    def test_iterate_flame_projects(self):
        """Iterating flame.projects is detected — PyProjectSelector is not iterable."""
        code = "for proj in flame.projects:\n    print(proj)"
        result = _check_dangerous(code)

        assert result is not None
        assert "projects" in result.lower()

    # ── 3. flame.projects[0] ─────────────────────────────────────────────

    def test_index_flame_projects(self):
        """Indexing flame.projects is detected — PyProjectSelector is not subscriptable."""
        code = "p = flame.projects[0]"
        result = _check_dangerous(code)

        assert result is not None
        assert "projects" in result.lower()

    # ── 4. flame.projects.current_project.libraries ───────────────────────

    def test_project_libraries(self):
        """Accessing .current_project.libraries is detected — returns None, use ws."""
        code = "libs = flame.projects.current_project.libraries"
        result = _check_dangerous(code)

        assert result is not None
        assert "libraries" in result.lower() or "workspace" in result.lower()

    # ── 5. flame.batch.render() ───────────────────────────────────────────

    def test_batch_render(self):
        """flame.batch.render() is detected — blocks Flame's main thread."""
        code = "flame.batch.render()"
        result = _check_dangerous(code)

        assert result is not None
        assert "batch" in result.lower() or "render" in result.lower()

    # ── 6. import wiretap (regex path) ───────────────────────────────────

    def test_import_wiretap(self):
        """'import wiretap' is detected via regex — crash-prone module."""
        code = "import wiretap\nwt = wiretap.WireTapServerHandle('localhost')"
        result = _check_dangerous(code)

        assert result is not None
        assert "wiretap" in result.lower()

    # ── 7. import wiretap (AST path) ─────────────────────────────────────

    def test_ast_import_wiretap(self):
        """'import wiretap' is also caught by AST analysis (Import node check).

        The AST walker detects Import/ImportFrom nodes whose alias name starts
        with 'wiretap'. This test verifies the AST path fires alongside regex.
        """
        code = "import wiretap"  # caught by both regex and AST Import node
        result = _check_dangerous(code)

        assert result is not None, "import wiretap must be detected"
        assert "wiretap" in result.lower()

    # ── 8. getattr-based batch.render() (AST only) ───────────────────────

    def test_ast_batch_render(self):
        """obj.batch.render() is detected via AST — no 'flame.' prefix needed.

        The regex only matches 'flame.batch.render()' literally. The AST walker
        detects any Call node whose attribute chain ends in .batch.render(),
        catching obfuscated references that bypass the regex.
        """
        code = "result = obj.batch.render()"  # no 'flame.' prefix → regex skips it
        result = _check_dangerous(code)

        assert result is not None, "obj.batch.render() should be caught by AST"
        assert "batch" in result.lower() or "render" in result.lower()

    # ── 9. Safe code returns None ─────────────────────────────────────────

    def test_safe_code_passes(self):
        """Normal Flame code returns None (no dangerous pattern found)."""
        safe_code = (
            "ws = flame.projects.current_project.current_workspace\n"
            "HIDDEN = {'Timeline FX', 'Grabbed References'}\n"
            "visible = [l for l in ws.libraries if str(l.name) not in HIDDEN]\n"
            "for lib in visible:\n"
            "    print(str(lib.name))\n"
        )
        result = _check_dangerous(safe_code)

        assert result is None, f"Safe code should not be blocked, got: {result!r}"

    # ── 10. Multiple patterns produce multiple hits ───────────────────────

    def test_multiple_hits(self):
        """Code triggering multiple patterns reports all of them."""
        code = (
            "n = len(flame.projects)\n"       # pattern 1
            "for p in flame.projects:\n"      # pattern 2
            "    print(p)\n"
        )
        result = _check_dangerous(code)

        assert result is not None
        # Both patterns should appear as separate bullet points
        bullet_count = result.count("•")
        assert bullet_count >= 2, (
            f"Expected at least 2 bullet hits, got {bullet_count} in:\n{result}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TestNextNoneGuardForms (TAREA 7 — sub-part 2)
# ═══════════════════════════════════════════════════════════════════════════

class TestNextNoneGuardForms:
    """The `next(..., None)` 'unchecked result' guard accepts the common
    existence-check forms, not just `if x is None`.

    Before TAREA 7 the negative-lookahead only recognised `if x is [not] None`,
    so a perfectly valid `if not lib:` / `if lib:` guard was flagged as an
    unchecked result and the code was blocked.
    """

    def _none_check_flagged(self, code: str) -> bool:
        result = _check_dangerous(code)
        return result is not None and "None check" in result

    def test_if_not_x_is_accepted(self):
        """`if not lib:` is a valid None check — must NOT be flagged."""
        code = (
            "lib = next((l for l in ws.libraries), None)\n"
            "if not lib:\n"
            "    print('not found')\n"
            "else:\n"
            "    print(str(lib.name))\n"
        )
        assert not self._none_check_flagged(code), (
            f"`if not x:` is a valid guard, should not be flagged: {code!r}"
        )

    def test_if_truthy_is_accepted(self):
        """`if lib:` (truthy guard) must NOT be flagged."""
        code = (
            "lib = next((l for l in ws.libraries), None)\n"
            "if lib:\n"
            "    print(str(lib.name))\n"
        )
        assert not self._none_check_flagged(code)

    def test_if_is_none_still_accepted(self):
        """The canonical `if x is None:` guard remains accepted."""
        code = (
            "lib = next((l for l in ws.libraries), None)\n"
            "if lib is None:\n"
            "    print('nf')\n"
        )
        assert not self._none_check_flagged(code)

    def test_unchecked_result_still_flagged(self):
        """No guard at all — the result IS used unchecked, must still flag."""
        code = (
            "lib = next((l for l in ws.libraries), None)\n"
            "print(str(lib.name))\n"
        )
        assert self._none_check_flagged(code), (
            "An unchecked next(..., None) result must still be flagged"
        )
