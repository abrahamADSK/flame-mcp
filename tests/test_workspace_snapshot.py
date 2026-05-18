"""
test_workspace_snapshot.py
==========================
F4a — Unit tests for ``flame_mcp._workspace_snapshot``.

Covered:

- :func:`get` returns ``None`` on miss, returns value on hit, drops
  stale entries after TTL expiry (lazy GC).
- :func:`set_value` overwrites prior entries with a fresh timestamp.
- :func:`invalidate` with no prefix wipes everything; with a prefix
  drops matching keys only and reports the count.
- :func:`size` reports current entry count.
- :func:`cache_workspace_read` decorator skips the function body on hit
  and stores the result on miss; distinguishes argument tuples.
- Exceptions raised by the wrapped function are NOT cached.
- TTL is monotonic-clock based — we exercise it via ``monkeypatch`` of
  ``time.monotonic`` rather than ``time.sleep`` so the suite stays
  fast (< 100 ms).
- A simple "concurrent read" scenario via two threads to confirm the
  lock does not deadlock.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from flame_mcp import _workspace_snapshot as ws


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    """Reset the cache between tests for isolation."""
    ws.invalidate(None)


# ---------------------------------------------------------------------------
# Core get/set/invalidate
# ---------------------------------------------------------------------------


def test_get_returns_none_on_miss() -> None:
    assert ws.get("does-not-exist") is None


def test_set_then_get_returns_value() -> None:
    ws.set_value("k", "v")
    assert ws.get("k") == "v"


def test_set_overwrites_prior_value() -> None:
    ws.set_value("k", "first")
    ws.set_value("k", "second")
    assert ws.get("k") == "second"


def test_get_returns_none_after_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stale entries are dropped lazily on the next ``get``."""
    clock = [1000.0]

    def fake_monotonic() -> float:
        return clock[0]

    monkeypatch.setattr(ws.time, "monotonic", fake_monotonic)
    ws.set_value("k", "v")
    assert ws.get("k", ttl=5.0) == "v"
    clock[0] += 6.0  # 6 s elapsed > 5 s TTL
    assert ws.get("k", ttl=5.0) is None
    # Side effect: the stale entry was GC'd.
    assert ws.size() == 0


def test_get_within_ttl_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(ws.time, "monotonic", lambda: clock[0])
    ws.set_value("k", "v")
    clock[0] += 4.0  # 4 s < 5 s TTL
    assert ws.get("k", ttl=5.0) == "v"


def test_invalidate_with_no_prefix_drops_all() -> None:
    ws.set_value("workspace.a", 1)
    ws.set_value("workspace.b", 2)
    ws.set_value("other.c", 3)
    assert ws.invalidate(None) == 3
    assert ws.size() == 0


def test_invalidate_with_prefix_targets_subset() -> None:
    ws.set_value("workspace.a", 1)
    ws.set_value("workspace.b", 2)
    ws.set_value("other.c", 3)
    dropped = ws.invalidate("workspace.")
    assert dropped == 2
    assert ws.get("other.c") == 3
    assert ws.get("workspace.a") is None


def test_invalidate_with_prefix_no_match_returns_zero() -> None:
    ws.set_value("k", "v")
    assert ws.invalidate("nomatch.") == 0
    # Existing entry still intact.
    assert ws.get("k") == "v"


# ---------------------------------------------------------------------------
# cache_workspace_read decorator
# ---------------------------------------------------------------------------


def test_decorator_caches_first_call_result() -> None:
    calls = {"n": 0}

    @ws.cache_workspace_read()
    def tool() -> str:
        calls["n"] += 1
        return f"result-{calls['n']}"

    assert tool() == "result-1"
    assert tool() == "result-1"  # cache hit
    assert calls["n"] == 1


def test_decorator_distinguishes_args() -> None:
    calls: list[tuple[Any, ...]] = []

    @ws.cache_workspace_read()
    def tool(library_name: str = "") -> str:
        calls.append((library_name,))
        return f"reels-of-{library_name or 'all'}"

    assert tool("LibA") == "reels-of-LibA"
    assert tool("LibB") == "reels-of-LibB"
    assert tool("LibA") == "reels-of-LibA"  # cache hit on first arg
    assert len(calls) == 2  # only LibA + LibB executed once each


def test_decorator_does_not_cache_exceptions() -> None:
    calls = {"n": 0}

    @ws.cache_workspace_read()
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return "ok"

    with pytest.raises(RuntimeError):
        flaky()
    # Next call should retry, not return the exception or a stale hit.
    assert flaky() == "ok"
    assert calls["n"] == 2


def test_decorator_respects_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(ws.time, "monotonic", lambda: clock[0])
    calls = {"n": 0}

    @ws.cache_workspace_read(ttl=3.0)
    def tool() -> str:
        calls["n"] += 1
        return f"r{calls['n']}"

    assert tool() == "r1"
    clock[0] += 2.0  # within TTL
    assert tool() == "r1"
    clock[0] += 2.0  # TTL exceeded
    assert tool() == "r2"
    assert calls["n"] == 2


def test_decorator_invalidation_forces_refresh() -> None:
    calls = {"n": 0}

    @ws.cache_workspace_read()
    def tool() -> str:
        calls["n"] += 1
        return f"r{calls['n']}"

    assert tool() == "r1"
    ws.invalidate(ws.WORKSPACE_PREFIX)
    # Cache cleared → function must be called again.
    assert tool() == "r2"
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Concurrency smoke test (lock does not deadlock)
# ---------------------------------------------------------------------------


def test_concurrent_reads_do_not_deadlock() -> None:
    """Two threads hammering get/set/invalidate in parallel must complete.

    Not a stress test — just a smoke test that the RLock is reentrant
    enough for nested calls and the basic protocol doesn't lock up.
    """
    ws.set_value("k", "init")
    stop = threading.Event()
    errors: list[Exception] = []

    def worker_get() -> None:
        try:
            for _ in range(200):
                if stop.is_set():
                    break
                ws.get("k")
        except Exception as exc:
            errors.append(exc)

    def worker_set() -> None:
        try:
            for i in range(200):
                if stop.is_set():
                    break
                ws.set_value("k", f"v{i}")
                if i % 50 == 0:
                    ws.invalidate("workspace.")
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=worker_get)
    t2 = threading.Thread(target=worker_set)
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)
    stop.set()
    assert not errors
    assert not t1.is_alive() and not t2.is_alive()
