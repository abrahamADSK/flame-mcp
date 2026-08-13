"""Tests for the fpt_link tool (Chat 93; write path removed in Chat 98).

fpt_link REPORTS the NATIVE Flame↔FPT project link — the
``shotgun_project_name`` ProjectEntry attribute, the same attribute Flame's
shipped FPT plugin (presets/<ver>/shotgun) reads and writes. Contract:

  * get    — read-only report of the current link. The ONLY action.
  * set    — REMOVED (Chat 98). Writing the attribute makes Flame save the
             whole project (catalogue + framestore) and the bridge runs tool
             code on a worker thread, not Flame's main thread; both in-vivo
             attempts ended in Flame's error report. The native plugin does
             the same write from the MAIN thread. Links are now created and
             broken only from Flame's own FPT menu.
  * break  — REMOVED (Chat 98), same reason.

The bridge is mocked (`mock_bridge` fixture) — these tests pin the generated
code and the refusal behaviour, not live Flame.
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
    assert "ERROR" in out and "read-only" in out
    mock_bridge.assert_not_called()


def test_set_refused_and_never_reaches_flame(mock_bridge):
    """The removed write path must fail loudly, not silently no-op."""
    out = fpt_link(action="set")
    assert "ERROR" in out
    assert "READ-ONLY" in out
    assert "Flow Production Tracking menu" in out  # points at the supported route
    mock_bridge.assert_not_called()


def test_break_refused_and_never_reaches_flame(mock_bridge):
    out = fpt_link(action="break")
    assert "ERROR" in out
    assert "READ-ONLY" in out
    mock_bridge.assert_not_called()


# ── generated bridge code ────────────────────────────────────────────────────


def test_get_reads_attribute_without_writing(mock_bridge):
    fpt_link(action="get")
    code = mock_bridge.call_args[0][0]
    assert "shotgun_project_name" in code
    assert "prj.shotgun_project_name =" not in code  # never assigns
    assert "get_value" in code  # bootstrap.py read pattern


def test_no_assignment_survives_anywhere_in_the_tool(mock_bridge):
    """Guard against the write path creeping back in via any action."""
    for action in ("get", "GET", "set", "break", "toggle"):
        mock_bridge.reset_mock()
        fpt_link(action=action)
        if mock_bridge.called:
            assert "shotgun_project_name =" not in mock_bridge.call_args[0][0]


def test_get_is_the_default_action(mock_bridge):
    fpt_link()
    assert mock_bridge.called
    assert "fpt_link=" in mock_bridge.call_args[0][0]


def test_action_case_insensitive(mock_bridge):
    fpt_link(action="GET")
    assert mock_bridge.called
