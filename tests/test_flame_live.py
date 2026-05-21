"""
test_flame_live.py
==================
Live-Flame regression guards. These tests connect to a REAL Flame bridge
and exercise the real tool code end-to-end — no mocking. They are skipped
automatically when no bridge is reachable (CI, fresh clone, Flame closed),
following the skipif-on-availability pattern recommended after the
mock-only blindspot lesson: a suite that always mocks `_call_flame` cannot
catch bugs that only manifest against real Flame (e.g. `str(obj.name)`
returning quote-wrapped strings).

Run locally with Flame open to activate these guards.
"""

import os
import socket

import pytest


def _flame_unreachable() -> bool:
    """True when no live Flame bridge accepts a connection.

    Probes the same candidate sockets the server uses. Evaluated at
    collection time so the guard auto-skips off a live host.
    """
    if not hasattr(socket, "AF_UNIX"):
        return True
    from flame_mcp.server import _socket_candidates

    for cand in _socket_candidates():
        if not os.path.exists(cand):
            continue
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            c.settimeout(1.0)
            c.connect(cand)
            return False  # something is listening → reachable
        except OSError:
            continue
        finally:
            c.close()
    return True


_BRIDGE_DOWN = _flame_unreachable()


@pytest.mark.skipif(
    _BRIDGE_DOWN,
    reason="Live Flame bridge not reachable — open Flame to run this guard.",
)
class TestLiveHiddenLibraries:
    """Guards the Chat 52 fix: hidden system libraries must not leak.

    On Flame 2026 ``str(lib.name)`` is quote-wrapped (``'Default Library'``),
    which silently defeated the ``str(l.name) not in HIDDEN`` filter and
    let the system libraries through. The `.strip("'")` normalisation fixes
    it; this test asserts the real, live output excludes them.
    """

    def test_list_libraries_excludes_system_libraries(self):
        from flame_mcp.server import list_libraries

        out = list_libraries()
        assert "Grabbed References" not in out, (
            "hidden system library 'Grabbed References' leaked into "
            "list_libraries output (quote-normalisation regression):\n" + out
        )
        assert "Timeline FX" not in out, (
            "hidden system library 'Timeline FX' leaked into "
            "list_libraries output (quote-normalisation regression):\n" + out
        )
