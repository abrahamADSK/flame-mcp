"""
test_markdown_render.py
=======================
The in-Flame chat panel renders the assistant's markdown (Chat 98).

Before this, the panel escaped the text and converted newlines, so every
answer landed literally: ``## Conform plan``, ``**confirm**`` and table rows
spelled out as ``|---|---|``. On a recorded demo that reads as a tool that
cannot format its own output.

``_md_to_html`` is a pure text→HTML function at module scope, so unlike the
widget methods it can be exercised directly — the bridge imports cleanly
offline (Qt is only imported inside the widget ``__init__``).

Qt's rich-text engine supports a SUBSET of HTML/CSS, which is why the output
uses plain tags with inline styles and ``<table border=…>`` attributes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_BRIDGE_PATH = Path(__file__).resolve().parents[1] / "hooks" / "flame_mcp_bridge.py"
_spec = importlib.util.spec_from_file_location("_flame_bridge_md", _BRIDGE_PATH)
assert _spec is not None and _spec.loader is not None
_bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bridge)

md = _bridge._md_to_html


class TestBlocks:
    def test_heading_becomes_bold_not_hashes(self):
        out = md("## Conform plan")
        assert "##" not in out
        assert "Conform plan" in out
        assert "<b" in out

    def test_table_becomes_a_table(self):
        out = md("| Shot | Frame |\n|---|---|\n| SEQ001_SH001 | 1 |")
        assert "<table" in out
        assert "|---|" not in out
        assert "SEQ001_SH001" in out
        assert out.count("<tr>") == 2  # header + one row

    def test_malformed_table_degrades_to_text(self):
        """A header with no separator row is not a table — it must still be
        readable rather than vanish."""
        out = md("| Shot | Frame |\n| SEQ001_SH001 | 1 |")
        assert "<table" not in out
        assert "SEQ001_SH001" in out

    def test_fenced_code_is_verbatim_and_not_parsed(self):
        out = md("```\nopenclip_create(shot_id=2659)\n**not bold**\n```")
        assert "openclip_create(shot_id=2659)" in out
        # The ** inside a fence stays literal. Match "<b " / "<b style" rather
        # than "<b", which also matches the "<br>" line breaks inside the block.
        assert "<b style" not in out
        assert "**not bold**" in out

    def test_bullets_and_numbers(self):
        out = md("- first\n- second\n1. third")
        assert out.count("•") == 2
        assert "1." in out

    def test_nested_bullet_is_indented_further(self):
        out = md("- top\n  - nested")
        indents = [int(s.split("px", 1)[0]) for s in out.split("margin-left:")[1:]]
        assert indents[1] > indents[0]

    def test_horizontal_rule(self):
        assert "<hr" in md("---")

    def test_blockquote(self):
        out = md("> A library sequence is read-only.")
        assert "A library sequence is read-only." in out
        # The '>' marker is consumed, not escaped into the body.
        assert "&gt;" not in out


class TestInline:
    def test_bold(self):
        out = md("Reply **confirm** to proceed.")
        assert "**" not in out
        assert "<b" in out

    def test_inline_code_is_not_emphasis_parsed(self):
        """Asterisks inside a code span must survive as literal text."""
        out = md("use `a**b` here")
        assert "a**b" in out
        assert "<b" not in out

    def test_italics(self):
        out = md("this is *emphasis* here")
        assert "<i>emphasis</i>" in out

    def test_link_keeps_label_and_dims_url(self):
        out = md("see [the docs](https://example.com/x)")
        assert "the docs" in out
        assert "https://example.com/x" in out


class TestSafety:
    def test_html_in_the_answer_is_escaped(self):
        """The model can quote markup; it must never reach the panel live."""
        out = md("a <script>alert(1)</script> tag")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_ampersand_escaped_before_tags_are_added(self):
        out = md("Tom & Jerry")
        assert "Tom &amp; Jerry" in out

    def test_html_inside_a_table_cell_is_escaped(self):
        out = md("| a | b |\n|---|---|\n| <b>x</b> | y |")
        assert "&lt;b&gt;x&lt;/b&gt;" in out

    def test_empty_input_is_harmless(self):
        assert md("") == ""


class TestRealAnswer:
    """A composite close to what the conform actually produced."""

    SAMPLE = (
        "## Conform plan\n\n"
        "The cut is **Master v1** with `6` shots.\n\n"
        "| Shot | Frame |\n|---|---|\n| SEQ001_SH001 | **1** |\n\n"
        "1. One open clip per shot\n"
        "2. Organise by Sequence\n"
        "   - rename before the timeline\n\n"
        "> A library sequence is read-only.\n\n"
        "```\nopenclip_create(shot_id=2659)\n```\n\n"
        "Reply **confirm** to proceed.\n"
    )

    @pytest.mark.parametrize("leak", ["##", "**", "|---|"])
    def test_no_markdown_syntax_reaches_the_panel(self, leak):
        assert leak not in md(self.SAMPLE)

    @pytest.mark.parametrize(
        "fragment", ["<table", "<b style", "<div style", "•", "Master v1"]
    )
    def test_every_block_renders(self, fragment):
        assert fragment in md(self.SAMPLE)
