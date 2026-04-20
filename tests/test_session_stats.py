"""
test_session_stats.py
=====================
Unit tests for the per-session stats reset helpers
(`flame_mcp._session_stats`). Covers the pure logic; the server.py
integration lives behind a patch proposal and is not exercised here.
"""

from __future__ import annotations

import datetime

import pytest

from flame_mcp._session_stats import (
    DEFAULT_IDLE_RESET_SECONDS,
    apply_idle_reset,
    make_empty_stats,
    reset_stats,
    should_auto_reset,
)


def _dt(hour: int = 10, minute: int = 0, second: int = 0) -> datetime.datetime:
    """Tiny helper to build datetimes with fewer kwargs at the call site."""
    return datetime.datetime(2026, 4, 20, hour, minute, second)


# ── make_empty_stats ────────────────────────────────────────────────────────

def test_empty_stats_has_all_canonical_keys() -> None:
    """Zero template must carry exactly the keys the server consumes."""
    stats = make_empty_stats()
    expected = {
        "exec_calls", "tokens_in", "tokens_out", "rag_calls",
        "tokens_saved", "dedicated_calls", "tokens_saved_tools",
        "patterns_learned", "patterns_staged", "patterns_failed",
        "timings",
    }
    assert set(stats.keys()) == expected


def test_empty_stats_counters_are_zero() -> None:
    """Every numeric counter starts at zero and timings is an empty list."""
    stats = make_empty_stats()
    for key, value in stats.items():
        if key == "timings":
            assert value == []
        else:
            assert value == 0, f"counter {key} not zeroed"


# ── should_auto_reset ───────────────────────────────────────────────────────

def test_should_auto_reset_false_on_first_call() -> None:
    """`last_call_at=None` → no reset (counters already fresh)."""
    assert should_auto_reset(_dt(), None) is False


def test_should_auto_reset_false_within_idle_window() -> None:
    """Gap shorter than the threshold → no reset."""
    now = _dt(10, 30, 0)
    last = _dt(10, 29, 0)   # 60 s gap, threshold 1800 s
    assert should_auto_reset(now, last) is False


def test_should_auto_reset_true_at_exact_threshold() -> None:
    """Threshold is `>=`, so the exact boundary triggers a reset."""
    now = _dt(10, 30, 0)
    last = now - datetime.timedelta(seconds=DEFAULT_IDLE_RESET_SECONDS)
    assert should_auto_reset(now, last) is True


def test_should_auto_reset_true_past_threshold() -> None:
    """Gap longer than the threshold → reset."""
    now = _dt(12, 0, 0)
    last = _dt(10, 0, 0)    # 2 h gap, threshold 30 min
    assert should_auto_reset(now, last) is True


def test_should_auto_reset_custom_threshold() -> None:
    """Caller-supplied threshold overrides the default."""
    now = _dt(10, 0, 10)
    last = _dt(10, 0, 0)    # 10 s gap
    assert should_auto_reset(now, last, idle_reset_seconds=5) is True
    assert should_auto_reset(now, last, idle_reset_seconds=15) is False


# ── apply_idle_reset ────────────────────────────────────────────────────────

def test_apply_idle_reset_does_nothing_within_window() -> None:
    """Fresh gap → stats unchanged, did_reset is False."""
    stats = make_empty_stats()
    stats["exec_calls"] = 7
    stats["tokens_in"] = 1234

    did, _ = apply_idle_reset(stats, _dt(10, 5, 0), _dt(10, 0, 0))

    assert did is False
    assert stats["exec_calls"] == 7
    assert stats["tokens_in"] == 1234


def test_apply_idle_reset_zeros_counters_past_window() -> None:
    """Gap over the window → every counter is cleared, identity preserved."""
    stats = make_empty_stats()
    original_id = id(stats)
    stats["exec_calls"] = 42
    stats["tokens_in"] = 99999
    stats["timings"].append({"op": "exec", "total_ms": 12})

    did, reset_at = apply_idle_reset(stats, _dt(12, 0, 0), _dt(10, 0, 0))

    assert did is True
    assert reset_at == _dt(12, 0, 0)
    assert id(stats) == original_id, "dict identity must be preserved"
    assert stats["exec_calls"] == 0
    assert stats["tokens_in"] == 0
    assert stats["timings"] == []


def test_apply_idle_reset_preserves_identity_for_module_refs() -> None:
    """
    server.py takes a module-level reference to `_stats`. If the
    helper rebinds instead of mutating, those references go stale.
    This test locks in the in-place behaviour.
    """
    stats = make_empty_stats()
    external_ref = stats
    stats["exec_calls"] = 5

    apply_idle_reset(stats, _dt(12, 0, 0), _dt(10, 0, 0))

    assert external_ref is stats
    assert external_ref["exec_calls"] == 0


def test_apply_idle_reset_ignores_first_call() -> None:
    """No previous timestamp → never reset, even with a distant `now`."""
    stats = make_empty_stats()
    stats["exec_calls"] = 3

    did, _ = apply_idle_reset(stats, _dt(23, 59, 0), None)

    assert did is False
    assert stats["exec_calls"] == 3


# ── reset_stats (explicit) ──────────────────────────────────────────────────

def test_reset_stats_clears_unconditionally() -> None:
    """Explicit reset zeroes every counter regardless of timing."""
    stats = make_empty_stats()
    stats["exec_calls"] = 10
    stats["tokens_out"] = 50000
    stats["timings"].append({"op": "rag", "score": 85})

    reset_at = reset_stats(stats, _dt(10, 0, 1))

    assert reset_at == _dt(10, 0, 1)
    assert stats["exec_calls"] == 0
    assert stats["tokens_out"] == 0
    assert stats["timings"] == []


def test_reset_stats_preserves_identity() -> None:
    """Explicit reset must also mutate in place (same contract)."""
    stats = make_empty_stats()
    external_ref = stats
    stats["exec_calls"] = 99

    reset_stats(stats, _dt())

    assert external_ref is stats
    assert external_ref["exec_calls"] == 0
