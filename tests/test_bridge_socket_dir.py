"""Socket-directory preparation in the Flame bridge hook.

The installed hook binds in /tmp; the bridge must never chmod a shared
system directory. Only its own <repo>/run/ is locked to 0700.
"""

import importlib.util
from pathlib import Path

_BRIDGE_PATH = Path(__file__).resolve().parents[1] / "hooks" / "flame_mcp_bridge.py"
_spec = importlib.util.spec_from_file_location("_flame_mcp_bridge_sockdir", _BRIDGE_PATH)
assert _spec is not None and _spec.loader is not None
_bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bridge)


def _record_chmod(monkeypatch):
    calls = []
    monkeypatch.setattr(_bridge.os, "chmod", lambda p, m: calls.append((p, m)))
    return calls


def test_shared_tmp_dir_is_never_chmodded(monkeypatch):
    """The installed path (/tmp) is left exactly as the system set it."""
    calls = _record_chmod(monkeypatch)
    _bridge._prepare_socket_dir("/tmp/flame_mcp.sock")
    assert calls == []


def test_own_run_dir_is_created_and_locked(monkeypatch, tmp_path):
    """The bridge's own run/ directory is created and set 0700."""
    own = tmp_path / "run"
    monkeypatch.setattr(_bridge, "_OWN_RUN_DIR", str(own))
    calls = _record_chmod(monkeypatch)
    _bridge._prepare_socket_dir(str(own / "flame_mcp.sock"))
    assert own.is_dir()
    assert calls == [(str(own), 0o700)]


def test_custom_override_dir_is_created_but_not_chmodded(monkeypatch, tmp_path):
    """A FLAME_BRIDGE_SOCKET elsewhere gets its directory, not a mode change."""
    monkeypatch.setattr(_bridge, "_OWN_RUN_DIR", str(tmp_path / "run"))
    calls = _record_chmod(monkeypatch)
    other = tmp_path / "elsewhere"
    _bridge._prepare_socket_dir(str(other / "flame_mcp.sock"))
    assert other.is_dir()
    assert calls == []
