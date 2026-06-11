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


def _no_project_loaded() -> bool:
    """True unless a Flame project is FULLY loaded.

    Chat 63 incident: with Flame at the project picker (bridge up, project
    NOT loaded), this harness scheduled a real render + export via idle
    events; they queued against a half-initialized main thread and Flame
    deadlocked (force quit required). A reachable bridge is NOT enough —
    these tests queue main-thread work, so they only run when a cheap
    read-only probe confirms the project context exists. User-declared
    invariant: never queue main-thread work against a half-loaded Flame.
    """
    if _BRIDGE_DOWN:
        return True
    from flame_mcp.server import _call_flame

    try:
        probe = _call_flame(
            "print(str(flame.projects.current_project.name))", timeout=5
        )
    except Exception:
        return True
    if probe.get("status") == "error":
        return True
    out = (probe.get("output") or "").strip()
    err = probe.get("error") or ""
    return not out or "Traceback" in err or "Error" in err


_NO_PROJECT = _no_project_loaded()


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


@pytest.mark.skipif(
    _NO_PROJECT,
    reason="No Flame project fully loaded — this guard queues main-thread "
    "work (idle-event render) and must never run against a half-loaded "
    "Flame (Chat 63 freeze).",
)
class TestLiveRenderBatch:
    """Guards 4C.1: render_batch must schedule a render against REAL Flame
    without being blocked or crashing.

    This is the case execute_python CANNOT cover: the generic guard blocks any
    snippet containing ``flame.batch.render(`` (it cannot tell the call is
    safely wrapped in schedule_idle_event). render_batch is a dedicated tool
    whose payload is marked ``# DT``, so the bridge skips that guard. This test
    proves the dedicated path reaches Flame and the schedule is accepted.

    NOTE: this fires a real Background-Reactor render of the CURRENT batch
    group. Run only against a scratch/test project.
    """

    def test_render_batch_schedules_without_block(self):
        from flame_mcp.server import _render_batch_impl as render_batch

        out = render_batch()  # defaults: Background Reactor, current batch group
        # The dedicated-tool path must NEVER trip the execute_python crash guard.
        assert "Blocked" not in out and "🛑" not in out, (
            "render_batch was blocked by the crash guard — the dedicated-tool "
            "(# DT) bypass regressed:\n" + out
        )
        # schedule_idle_event is a GUI-thread API: Flame only exposes it while it
        # is the foreground/active app. Backgrounded, the tool reports it
        # unavailable — skip rather than fail (not a code regression).
        if "unavailable" in out.lower() or "no attribute" in out:
            pytest.skip("Flame not foreground — schedule_idle_event unavailable")
        assert "scheduled" in out.lower(), (
            "render_batch did not schedule against live Flame:\n" + out
        )


@pytest.mark.skipif(
    _NO_PROJECT,
    reason="No Flame project fully loaded — this guard sends main-thread "
    "work and must never run against a half-loaded Flame (Chat 63 freeze).",
)
class TestLiveExportClip:
    """Guards 4C.2: export_clip reaches REAL Flame via the dedicated path and is
    not blocked by the execute_python crash guard.

    Uses a deliberately nonexistent reel/clip so the test is deterministic and
    side-effect-free: the resolve step (data API, always available) returns
    'clip not found', proving the dedicated payload reached Flame and ran —
    without depending on the GUI-thread export API being bound.
    """

    def test_export_clip_reaches_flame_without_block(self):
        from flame_mcp.server import _export_clip_impl as export_clip

        out = export_clip(
            library_name="Default Library",
            reel_name="__mcp_nonexistent__",
            clip_name="__mcp_nonexistent__",
            preset_path="/tmp/none.xml",
            output_directory="/tmp/flame_export_test",
        )
        assert "Blocked" not in out and "🛑" not in out, (
            "export_clip was blocked by the crash guard — the dedicated-tool "
            "(# DT) bypass regressed:\n" + out
        )
        if "unavailable" in out.lower() or "no attribute" in out:
            pytest.skip("Flame not foreground — export API unavailable")
        assert "not found" in out.lower() or "scheduled" in out.lower(), (
            "export_clip did not reach Flame's resolve/schedule path:\n" + out
        )
