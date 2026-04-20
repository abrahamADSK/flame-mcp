"""
_session_stats.py
=================
Per-session reset machinery for the MCP server's `_stats` dict.

Problem
-------
`server.py::_stats` accumulates metrics (exec calls, tokens in/out,
patterns learned, …) for the lifetime of the MCP server process.
Long-running processes (Claude Desktop keeping the server spawned for
days) produce `session_stats()` outputs that span multiple Claude
sessions, making the token-efficiency rating meaningless. The issue
is carried forward as §11 in docs/ARCHITECTURE.md.

No MCP-level session signal
---------------------------
MCP over stdio does NOT expose a "Claude session boundary" to the
server. Each `Context` has a `request_id` (unique per tool call) and
optionally a `client_id` (only if the client populates `meta.client_id`,
which Claude Code does not today). There is therefore no reliable
notification the server can subscribe to that says "a new Claude
session started".

Chosen approach
---------------
Two reset triggers combine to keep the stats honest without touching
the MCP protocol:

1.  **Idle-based auto-reset.** If the gap between the previous call and
    the new one exceeds `idle_reset_seconds` (default 1800 s = 30 min),
    the counter is reset automatically on the new call. A cold Claude
    session — even when it hits the same already-running server
    process — will almost always have a gap of at least tens of
    minutes from the previous activity, so this captures the common
    case without manual intervention.

2.  **Explicit reset tool.** Expose a `reset_session_stats()` MCP tool
    so the model or the operator can zero the counters deliberately
    at the start of a new task. This covers the fast back-to-back
    sessions (< idle threshold) and gives operators an audit-friendly
    "start a fresh log" action.

Both triggers update `_stats_reset_at`, which is already surfaced in
`session_stats()` via the `(since HH:MM:SS)` header. Consumers therefore
see immediately when the counter was last zeroed.

Public API
----------
make_empty_stats() -> dict
    Canonical zero-value template. Shared by the initializer and the
    reset paths so they cannot drift.

should_auto_reset(now, last_call_at, *, idle_reset_seconds) -> bool
    Pure predicate: returns True when the gap exceeds the idle window.
    `last_call_at` may be None (first call ever) → returns False.

apply_idle_reset(stats, now, last_call_at, *, idle_reset_seconds)
    Mutates `stats` in place (preserves identity — important because
    server.py already takes a module-level reference to `_stats`) and
    returns `(did_reset, reset_at)` so the caller can update the
    `_stats_reset_at` bookkeeping.
"""

from __future__ import annotations

import datetime
from typing import Optional, Tuple


# Canonical idle threshold. Tuned to be long enough that a user who
# steps away briefly and comes back is not surprised by a reset, but
# short enough that a "next morning" Claude session starts clean.
DEFAULT_IDLE_RESET_SECONDS = 30 * 60  # 30 minutes


def make_empty_stats() -> dict:
    """
    Return a freshly initialised `_stats` dict.

    Kept in sync with the one in `server.py` — any new counter added
    there must be added here too (and vice-versa). A concept-registry
    invariant should lock these two in the future; for now the pair
    is small enough to audit by eye.

    Returns
    -------
    dict
        Dictionary with every counter zeroed and the timings buffer
        set to an empty list.
    """
    return {
        "exec_calls":         0,
        "tokens_in":          0,   # tokens sent to Flame (code)
        "tokens_out":         0,   # tokens received from Flame (output)
        "rag_calls":          0,
        "tokens_saved":       0,   # tokens saved by RAG vs loading full doc
        "dedicated_calls":    0,   # calls to hardcoded tools (no RAG needed)
        "tokens_saved_tools": 0,   # tokens saved by dedicated tools
        "patterns_learned":   0,   # auto-learned patterns added to FLAME_API.md
        "patterns_staged":    0,   # C5 — candidates staged by non-trusted models
        "patterns_failed":    0,   # C5 — failed executions logged for gap analysis
        "timings":            [],  # REC-001: ring buffer of recent call timings (max 20)
    }


def should_auto_reset(
    now: datetime.datetime,
    last_call_at: Optional[datetime.datetime],
    *,
    idle_reset_seconds: int = DEFAULT_IDLE_RESET_SECONDS,
) -> bool:
    """
    Decide whether an idle-gap reset is due.

    Parameters
    ----------
    now : datetime.datetime
        Timestamp of the new call. Tests inject this explicitly;
        production code passes `datetime.datetime.now()`.
    last_call_at : datetime.datetime | None
        Timestamp of the previous call. `None` on the first call
        ever — treated as "do not reset" because the counters are
        already fresh.
    idle_reset_seconds : int, keyword-only, default 1800
        Idle window, in seconds. Defaults to 30 minutes.

    Returns
    -------
    bool
        True iff `(now - last_call_at).total_seconds() >= idle_reset_seconds`.
    """
    if last_call_at is None:
        return False
    gap = (now - last_call_at).total_seconds()
    return gap >= idle_reset_seconds


def apply_idle_reset(
    stats: dict,
    now: datetime.datetime,
    last_call_at: Optional[datetime.datetime],
    *,
    idle_reset_seconds: int = DEFAULT_IDLE_RESET_SECONDS,
) -> Tuple[bool, datetime.datetime]:
    """
    Mutate `stats` in place if an idle reset is due.

    Parameters
    ----------
    stats : dict
        The live `_stats` dict. IDENTITY IS PRESERVED: the function
        calls `.clear()` and `.update(make_empty_stats())` so every
        module that holds a reference to the same dict sees the
        reset without re-binding.
    now, last_call_at, idle_reset_seconds :
        See `should_auto_reset`.

    Returns
    -------
    (did_reset, reset_at) : tuple[bool, datetime.datetime]
        - `did_reset`  — True iff the dict was cleared.
        - `reset_at`   — `now` when reset, otherwise the caller's
          previous reset timestamp should be preserved (the helper
          cannot know that value, so it returns `now` either way and
          expects the caller to ignore the field unless did_reset).
    """
    if not should_auto_reset(now, last_call_at, idle_reset_seconds=idle_reset_seconds):
        return False, now
    stats.clear()
    stats.update(make_empty_stats())
    return True, now


def reset_stats(stats: dict, now: datetime.datetime) -> datetime.datetime:
    """
    Unconditional reset (wired to the `reset_session_stats` MCP tool).

    Parameters
    ----------
    stats : dict
        The live `_stats` dict. Cleared in place (identity preserved).
    now : datetime.datetime
        Timestamp stamped as the new `_stats_reset_at`.

    Returns
    -------
    datetime.datetime
        The same `now` value, returned for caller convenience.
    """
    stats.clear()
    stats.update(make_empty_stats())
    return now
