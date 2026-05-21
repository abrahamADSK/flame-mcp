"""
test_bridge_connect.py
======================
Tests for the F7 probe-on-connect transport resolution in
``src/flame_mcp/server.py`` (`_socket_candidates` / `_connect_bridge`).

Unlike the dedicated-tool tests, these exercise the REAL socket
selection path with real local Unix sockets (no Flame required, so they
run in CI). They exist because the rest of the suite mocks `_call_flame`
wholesale and therefore never touches transport selection — a
mock-only blindspot that previously let a stale leftover socket file
trap the resolver at import time (the bug this code fixes).

Tests
-----
TestSocketCandidates (2):
  1. test_env_override_single   -- FLAME_BRIDGE_SOCKET → that path only
  2. test_default_order         -- no env → [repo/run, /tmp] in order

TestConnectBridge (2):
  3. test_probe_skips_dead_socket -- dead candidate skipped, live one wins
  4. test_nothing_reachable       -- no transport → ConnectionRefusedError
"""

import os
import shutil
import socket
import tempfile
import threading

import pytest

from flame_mcp.server import _connect_bridge, _socket_candidates


@pytest.fixture
def short_tmp():
    """A short temp dir under /tmp.

    AF_UNIX socket paths are capped at ~104 bytes on macOS, so pytest's
    deeply-nested ``tmp_path`` overflows. Anchor under ``/tmp`` to stay
    well under the limit.
    """
    d = tempfile.mkdtemp(dir="/tmp")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


class TestSocketCandidates:
    def test_env_override_single(self, monkeypatch):
        monkeypatch.setenv("FLAME_BRIDGE_SOCKET", "/custom/path.sock")
        assert _socket_candidates() == ["/custom/path.sock"]

    def test_default_order(self, monkeypatch):
        monkeypatch.delenv("FLAME_BRIDGE_SOCKET", raising=False)
        cands = _socket_candidates()
        assert cands[-1] == "/tmp/flame_mcp.sock"
        assert cands[0].endswith("run/flame_mcp.sock")
        assert len(cands) == 2


class TestConnectBridge:
    def test_probe_skips_dead_socket(self, short_tmp, monkeypatch):
        """A stale (dead) socket file must NOT trap the resolver; the
        probe moves on and connects to the live candidate."""
        stale = os.path.join(short_tmp, "stale.sock")
        live = os.path.join(short_tmp, "live.sock")

        # STALE: bind then close, leaving a dead socket file on disk.
        dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        dead.bind(stale)
        dead.close()
        assert os.path.exists(stale)

        # LIVE: a real listener accepting one connection.
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(live)
        srv.listen(1)
        threading.Thread(
            target=lambda: srv.accept() if True else None, daemon=True
        ).start()

        try:
            # Stale FIRST (higher priority) — exactly the bug scenario.
            monkeypatch.setattr(
                "flame_mcp.server._socket_candidates",
                lambda: [stale, live],
            )
            conn = _connect_bridge(timeout=2.0)
            try:
                assert conn.getpeername() == live
            finally:
                conn.close()
        finally:
            srv.close()

    def test_nothing_reachable(self, short_tmp, monkeypatch):
        """Only a dead socket + TCP refused → ConnectionRefusedError so
        the caller surfaces the standard guidance message."""
        stale = os.path.join(short_tmp, "stale.sock")
        dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        dead.bind(stale)
        dead.close()

        monkeypatch.setattr(
            "flame_mcp.server._socket_candidates", lambda: [stale]
        )
        monkeypatch.setattr("flame_mcp.server.BRIDGE_PORT", 1)  # → refused
        with pytest.raises(ConnectionRefusedError):
            _connect_bridge(timeout=2.0)
