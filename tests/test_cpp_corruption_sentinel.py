"""The C++ corruption warning must come from the bridge, not from text.

Chat 99 in-vivo: mid-render, the console told the operator that Flame had
thrown an internal C++ exception and the interface might be corrupted. The
logs said otherwise — the render completed (100 frames, correct embedded
timecode) and neither the app log nor the shell log carried any exception.

The console was inferring the crash from tool TEXT: it fired when a result
contained ('possibly_corrupted' OR 'unordered_map::at') AND 'ERROR:'. One
search_flame_docs response concatenates several chunks, and
docs/flame_vocabulary.md carries an "Error messages" table listing
`unordered_map::at` while other chunks carry `print('ERROR: ...')` samples.
Documentation must be free to DESCRIBE a crash; only the bridge may raise
the alarm.
"""

import re

import flame_mcp.server as server


class TestSentinelEmission:

    def test_sentinel_only_on_a_real_bridge_detection(self):
        corrupted = server._fmt({
            "status": "error", "error": "unordered_map::at: key not found",
            "flame_state": "possibly_corrupted"})
        assert server.CPP_CORRUPTION_SENTINEL in corrupted
        assert corrupted.startswith(server.CPP_CORRUPTION_SENTINEL)
        assert "ERROR:" in corrupted

    def test_ordinary_python_error_carries_no_sentinel(self):
        """An AttributeError is not a Flame crash — even when its text
        happens to mention the C++ marker."""
        for err in ("AttributeError: 'NoneType' object has no attribute 'x'",
                    "see the docs about unordered_map::at for context"):
            out = server._fmt({"status": "error", "error": err})
            assert server.CPP_CORRUPTION_SENTINEL not in out
            assert "ERROR:" in out

    def test_success_never_carries_the_sentinel(self):
        out = server._fmt({"status": "ok", "output": "unordered_map::at ERROR: sample"})
        assert server.CPP_CORRUPTION_SENTINEL not in out

    def test_sentinel_is_unmistakable(self):
        """It must be a literal no document, recipe or corpus chunk could
        contain by accident."""
        s = server.CPP_CORRUPTION_SENTINEL
        assert s.startswith("\u27ea") and s.endswith("\u27eb")
        assert not re.search(r"[A-Za-z]", s.strip("\u27ea\u27eb").replace("_", "").replace("FLAMECPPCORRUPTION", ""))


class TestConsoleMatching:

    def _console(self):
        with open("hooks/flame_mcp_bridge.py", encoding="utf-8") as fh:
            return fh.read()

    def test_console_matches_the_same_literal(self):
        src = self._console()
        assert '_cpp_sentinel = "\\u27eaFLAME_CPP_CORRUPTION\\u27eb"' in src
        assert "if _cpp_sentinel in full_text:" in src

    def test_console_no_longer_scans_for_markers(self):
        src = self._console()
        assert "_cpp_marker = ('possibly_corrupted' in full_text" not in src
        assert "or 'unordered_map::at' in full_text)" not in src

    def test_the_documented_crash_table_would_not_fire_today(self):
        """The exact corpus chunk that misfired, re-checked against the new
        rule: it mentions the C++ marker and sits next to ERROR: samples,
        and must NOT contain the sentinel."""
        chunk = ("## Error messages and what they mean\n"
                 "| `unordered_map::at: key not found` | C++ Flame internal "
                 "crash — object no longer valid | restart Flame |\n"
                 "print('ERROR: ' + repr(_exc))")
        assert server.CPP_CORRUPTION_SENTINEL not in chunk
