"""Tests for the fpt_link tool (Chat 93).

fpt_link drives the NATIVE Flame↔FPT project link — the
``shotgun_project_name`` ProjectEntry attribute, the same attribute Flame's
shipped FPT plugin (presets/<ver>/shotgun) reads and writes. Contract:

  * get    — read-only report of the current link.
  * set    — writes the attribute; overwriting a DIFFERENT existing link is
             guarded in the generated bridge code by ``confirm``.
  * break  — clears the attribute; refused client-side without confirm=true
             (express user request only).

The bridge is mocked (`mock_bridge` fixture) — these tests pin the generated
code and the guard behaviour, not live Flame.
"""

from flame_mcp import server


def _tool(name):
    """Unwrap the FastMCP-decorated tool to its underlying function."""
    fn = getattr(server, name)
    return getattr(fn, "fn", fn)


fpt_link = None  # populated lazily so import errors surface per-test


def setup_module(module):
    module.fpt_link = _tool("fpt_link")


# ── client-side validation (no bridge call) ──────────────────────────────────


def test_unknown_action_rejected(mock_bridge):
    out = fpt_link(action="toggle")
    assert "ERROR" in out and "get, set, break" in out
    mock_bridge.assert_not_called()


def test_set_requires_project_name(mock_bridge):
    out = fpt_link(action="set")
    assert "ERROR" in out and "fpt_project_name" in out
    mock_bridge.assert_not_called()


def test_break_requires_confirm(mock_bridge):
    out = fpt_link(action="break")
    assert "ERROR" in out and "confirm=true" in out
    mock_bridge.assert_not_called()


# ── generated bridge code ────────────────────────────────────────────────────


def test_get_reads_attribute_without_writing(mock_bridge):
    fpt_link(action="get")
    code = mock_bridge.call_args[0][0]
    assert "shotgun_project_name" in code
    assert "prj.shotgun_project_name =" not in code  # never assigns
    assert "get_value" in code  # bootstrap.py read pattern


def test_set_writes_target_with_overwrite_guard(mock_bridge):
    fpt_link(action="set", fpt_project_name="mcp_project_abraham")
    code = mock_bridge.call_args[0][0]
    assert "target = 'mcp_project_abraham'" in code
    assert "prj.shotgun_project_name = target" in code
    # overwrite guard present and driven by the confirm flag
    assert "cur and cur != target and not confirm" in code
    assert "confirm = False" in code


def test_set_with_confirm_disarms_guard(mock_bridge):
    fpt_link(action="set", fpt_project_name="other_project", confirm=True)
    code = mock_bridge.call_args[0][0]
    assert "confirm = True" in code


def test_break_clears_attribute(mock_bridge):
    fpt_link(action="break", confirm=True)
    code = mock_bridge.call_args[0][0]
    assert "prj.shotgun_project_name = ''" in code
    assert "BROKEN" in code


def test_action_case_insensitive(mock_bridge):
    fpt_link(action="GET")
    assert mock_bridge.called
