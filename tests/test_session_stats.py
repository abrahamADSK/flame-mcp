"""
test_session_stats.py
=====================
Unit tests for the per-session stats reset helpers
(`flame_mcp._session_stats`). Covers the pure logic; the server.py
integration lives behind a patch proposal and is not exercised here.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path


from flame_mcp._session_stats import (
    DEFAULT_IDLE_RESET_SECONDS,
    TELEMETRY_MAX_BYTES,
    apply_idle_reset,
    make_empty_stats,
    persist_timing,
    persist_turn,
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
        # F0: p_fallo counters added in chat 51.
        "turns_total", "failed_turns",
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


def test_empty_stats_includes_p_fallo_counters() -> None:
    """F0 — turns_total and failed_turns are present and zero so p_fallo
    starts as 0/0 (undefined → reported as 0% by the consumer)."""
    stats = make_empty_stats()
    assert stats["turns_total"] == 0
    assert stats["failed_turns"] == 0


# ── persist_timing / persist_turn ──────────────────────────────────────────

def test_persist_timing_writes_one_jsonl_line(tmp_path: Path) -> None:
    """A single call appends exactly one well-formed JSON line."""
    log = tmp_path / "timings.jsonl"
    persist_timing(log, {"op": "exec", "bridge_ms": 10, "total_ms": 12})

    contents = log.read_text(encoding="utf-8").splitlines()
    assert len(contents) == 1
    parsed = json.loads(contents[0])
    assert parsed == {"op": "exec", "bridge_ms": 10, "total_ms": 12}


def test_persist_timing_appends_across_calls(tmp_path: Path) -> None:
    """Successive calls append; existing content is preserved."""
    log = tmp_path / "timings.jsonl"
    persist_timing(log, {"op": "exec", "n": 1})
    persist_timing(log, {"op": "rag",  "n": 2})

    lines = log.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["n"] for line in lines] == [1, 2]


def test_persist_timing_creates_parent_directory(tmp_path: Path) -> None:
    """Parent directory is created on demand — caller need not pre-mkdir."""
    log = tmp_path / "nested" / "dir" / "timings.jsonl"
    persist_timing(log, {"op": "exec"})
    assert log.exists()


def test_persist_timing_rotates_when_oversized(tmp_path: Path) -> None:
    """When the log reaches TELEMETRY_MAX_BYTES it is rotated to .1 and the
    new line lands in a fresh file. A previous .1 is overwritten."""
    log = tmp_path / "timings.jsonl"
    rotated = tmp_path / "timings.jsonl.1"
    # Stub a previous rotation that must be overwritten.
    rotated.write_text("STALE\n", encoding="utf-8")
    # Fill primary log past the rotation threshold.
    log.write_bytes(b"X" * (TELEMETRY_MAX_BYTES + 1))

    persist_timing(log, {"op": "exec", "after": "rotation"})

    # The previous primary became .1 (overwriting "STALE"); new line is alone.
    assert "STALE" not in rotated.read_text(encoding="utf-8")
    new_lines = log.read_text(encoding="utf-8").splitlines()
    assert len(new_lines) == 1
    assert json.loads(new_lines[0])["after"] == "rotation"


def test_persist_timing_swallows_io_errors(tmp_path: Path) -> None:
    """An unwritable path must NOT raise — telemetry never crashes callers."""
    # A regular file masquerading as a directory: any append inside it
    # raises OSError, which the helper must swallow.
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    log = blocker / "timings.jsonl"

    # Must not raise.
    persist_timing(log, {"op": "exec"})


def test_persist_timing_handles_non_serialisable_values(tmp_path: Path) -> None:
    """Non-JSON-native values are coerced via str (default=str) so the
    call still succeeds for common edge cases (e.g. datetime)."""
    log = tmp_path / "timings.jsonl"
    persist_timing(log, {"op": "exec", "ts": datetime.datetime(2026, 5, 13, 12, 0, 0)})

    parsed = json.loads(log.read_text(encoding="utf-8"))
    assert parsed["op"] == "exec"
    assert "2026-05-13" in parsed["ts"]


def test_persist_turn_delegates_to_persist_timing(tmp_path: Path) -> None:
    """The bridge-side helper shares the timing contract; both must produce
    interchangeable JSONL output for jq aggregation."""
    log = tmp_path / "turns.jsonl"
    persist_turn(log, {"model": "claude-opus", "exit_code": 0})

    parsed = json.loads(log.read_text(encoding="utf-8"))
    assert parsed == {"model": "claude-opus", "exit_code": 0}


# ── F1a: _stats_footer modes ────────────────────────────────────────────────
# The footer used to ship ~80–120 tokens on every tool response. Modes:
#   - none    → ""
#   - minimal → "" (per-call timing is already in the caller's preamble)
#   - full    → historical multi-line aggregate
# Default mode comes from config.json -> stats_footer_mode (fallback "minimal").

def test_stats_footer_explicit_none(monkeypatch) -> None:
    """`mode='none'` returns empty regardless of config or stats state."""
    from flame_mcp import server as srv
    srv._stats.update(make_empty_stats())
    srv._stats["exec_calls"] = 12  # would normally show up in "full"
    assert srv._stats_footer(mode="none") == ""


def test_stats_footer_explicit_minimal_is_empty() -> None:
    """`mode='minimal'` returns empty: per-call timing lives in the
    execute_python preamble; the session block is intentionally suppressed
    to keep next-turn prefill small."""
    from flame_mcp import server as srv
    srv._stats.update(make_empty_stats())
    srv._stats["exec_calls"] = 12
    assert srv._stats_footer(mode="minimal") == ""


def test_stats_footer_explicit_full_renders_session_block() -> None:
    """`mode='full'` returns the historical aggregate so session_stats() (and
    operators who config `stats_footer_mode: full`) can still see it."""
    from flame_mcp import server as srv
    srv._stats.update(make_empty_stats())
    srv._stats["exec_calls"]         = 3
    srv._stats["rag_calls"]          = 2
    srv._stats["dedicated_calls"]    = 1
    srv._stats["tokens_in"]          = 100
    srv._stats["tokens_out"]         = 50
    srv._stats["tokens_saved"]       = 800
    srv._stats["tokens_saved_tools"] = 200

    out = srv._stats_footer(mode="full")
    assert "Session · 3 exec · 2 RAG · 1 tools" in out
    assert "Tokens used       : ~150" in out
    assert "Avoided by RAG    : ~800" in out
    assert "Total avoided     : ~1000" in out


def test_stats_footer_default_reads_config(monkeypatch) -> None:
    """When mode is None, the function reads `stats_footer_mode` from
    config. Default fallback is 'minimal' → empty string."""
    from flame_mcp import server as srv
    # Force config to return "full" — the default call must honour it.
    monkeypatch.setattr(srv, "_get_config", lambda: {"stats_footer_mode": "full"})
    srv._stats.update(make_empty_stats())
    srv._stats["exec_calls"] = 1
    out = srv._stats_footer()  # mode=None → read from config
    assert "Session · 1 exec" in out


def test_stats_footer_default_minimal_when_config_absent(monkeypatch) -> None:
    """Missing config key falls back to 'minimal' → empty string."""
    from flame_mcp import server as srv
    monkeypatch.setattr(srv, "_get_config", lambda: {})
    srv._stats.update(make_empty_stats())
    srv._stats["exec_calls"] = 99
    assert srv._stats_footer() == ""


def test_stats_footer_invalid_mode_falls_back_to_minimal(monkeypatch) -> None:
    """Typos / garbage config values must NOT spam the LLM with the full
    block by accident — silent fallback to minimal keeps the safer
    behaviour."""
    from flame_mcp import server as srv
    monkeypatch.setattr(srv, "_get_config", lambda: {"stats_footer_mode": "verbose"})
    srv._stats.update(make_empty_stats())
    srv._stats["exec_calls"] = 5
    assert srv._stats_footer() == ""
    # Also for an explicit garbage arg.
    assert srv._stats_footer(mode="garbage") == ""


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
