"""
test_collect_media_paths.py
===========================
Regression test for the collect_media_paths code-generation blocker.

History: collect_media_paths built its execute_python snippet with an inline
ternary (`f"    {reel_filter}\n" if reel_name else ""`) embedded in an implicit
string concatenation. The ternary bound across the whole concatenation chain,
so:
  - with reel_name set, the clips-iteration block was dropped and the source
    ended on a bodyless `if` (SyntaxError);
  - with reel_name unset, only the trailing `for c in r.clips:` block survived
    with no import/library/outer-loop setup (unexpected-indent SyntaxError).

The tool was therefore non-functional on EVERY invocation. This test captures
the generated source (by stubbing the bridge) and asserts it compiles for both
the reel_name-set and reel_name-unset branches, so the regression can never
re-land silently.
"""

from unittest.mock import patch

import flame_mcp.server as server


def _capture_generated_code(library_name: str, reel_name: str) -> str:
    """Call collect_media_paths with a stubbed bridge and return the Python
    source it would have executed inside Flame."""
    captured: dict[str, str] = {}

    def _fake_call_flame(code: str, **kwargs: object) -> dict:
        captured["code"] = code
        return {"output": "ok", "error": "", "_bridge_ms": 0}

    with patch.object(server, "_call_flame", _fake_call_flame):
        server.collect_media_paths(library_name, reel_name)

    return captured["code"]


class TestCollectMediaPathsGeneratesParseableSource:
    """The generated execute_python source must always compile."""

    def test_compiles_with_reel_name_set(self):
        src = _capture_generated_code("Default Library", "Reel 1")
        # Must not raise SyntaxError.
        compile(src, "<g>", "exec")
        # The reel filter and the clips loop must both be present.
        assert "if str(r.name).strip(\"'\") == 'Reel 1':" in src
        assert "for c in r.clips:" in src
        assert "paths.append" in src

    def test_compiles_with_reel_name_unset(self):
        src = _capture_generated_code("Default Library", "")
        # Must not raise SyntaxError.
        compile(src, "<g>", "exec")
        # No reel filter, but the full setup + clips loop must be present.
        assert "import flame" in src
        assert "for r in lib.reels:" in src
        assert "for c in r.clips:" in src
        assert "if str(r.name)" not in src  # no reel filter when unset

    def test_both_branches_have_library_guard(self):
        for reel_name in ("Reel 1", ""):
            src = _capture_generated_code("My Lib", reel_name)
            compile(src, "<g>", "exec")
            assert "ERROR: library not found" in src
            assert "My Lib" in src
