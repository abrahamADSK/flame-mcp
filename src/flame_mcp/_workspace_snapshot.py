"""
_workspace_snapshot.py
======================
F4a — Workspace snapshot cache with TTL + write-invalidation.

The MCP read tools (`list_libraries`, `list_reels`, `list_clips`,
`list_desktop_reels`, `list_batch_groups`, `list_all_projects`,
`get_project_info`) all perform a socket round-trip to Flame and run
Python inside the embedded interpreter. On large projects the same
``list_libraries`` invocation can take 200–800 ms even when nothing has
changed since the previous call.

This module provides a small, thread-safe, per-process cache:

- :func:`get` / :func:`set_value` — value-by-key TTL store. TTL is
  monotonic-clock based so wall-clock skew can't corrupt it.
- :func:`invalidate` — drop entries by prefix (or all). Called from
  every `execute_python` invocation, since the LLM may have mutated
  workspace state.
- :func:`cache_workspace_read` — decorator wrapper for MCP tool bodies.
  Computes a key from the tool function name + positional + keyword
  args, returns the cached value when fresh, otherwise calls through
  and stores the result.

Why TTL 12 s
------------
Short enough that a user perceives the workspace as live (the next
manual ``list_libraries`` after they create something in Flame will hit
fresh data within 12 s anyway), long enough to amortise a back-to-back
read cycle from the LLM (e.g. ``list_libraries`` → ``list_reels(X)`` →
``list_clips(X, Y)`` typically lands in the cache window for the parent
lookups).

Why invalidation-on-write is mandatory
--------------------------------------
TTL alone is not enough. If the LLM deletes a clip via ``execute_python``
and the next turn asks ``list_clips`` 3 s later, TTL would serve the
pre-delete view and the LLM would believe the operation failed. The
``execute_python`` path therefore calls :func:`invalidate` after every
exec (success or failure), guaranteeing the next list reflects reality.
This is **AJUSTE 2** of the chat 51 v2 plan — v1 only had TTL.

Scope intentionally narrow
--------------------------
The cache is per-MCP-process (one MCP server can be the host for at
most one Flame instance). No cross-process sharing, no persistence to
disk, no LRU eviction (TTL is the only retention mechanism). When the
MCP server restarts, the cache is empty — same as before F4a.
"""

from __future__ import annotations

import functools
import threading
import time
from typing import Any, Callable, Optional, TypeVar

# Tuning knobs (constants, not config — kept tight on purpose).
DEFAULT_TTL_SECONDS: float = 12.0
WORKSPACE_PREFIX: str = "workspace."

# Internal state.
_lock: threading.RLock = threading.RLock()
_cache: dict[str, tuple[float, Any]] = {}

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


def get(key: str, *, ttl: float = DEFAULT_TTL_SECONDS) -> Optional[Any]:
    """Return cached value for ``key`` if fresher than ``ttl`` seconds.

    Returns ``None`` on miss or stale. A stale entry is dropped from the
    cache as a side-effect (lazy GC).
    """
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        timestamp, value = entry
        if time.monotonic() - timestamp > ttl:
            _cache.pop(key, None)
            return None
        return value


def set_value(key: str, value: Any) -> None:
    """Store ``value`` for ``key`` with current monotonic timestamp."""
    with _lock:
        _cache[key] = (time.monotonic(), value)


def invalidate(prefix: Optional[str] = None) -> int:
    """Drop entries by key prefix; ``None`` drops all. Returns count dropped.

    The default workspace invalidation call is ``invalidate(WORKSPACE_PREFIX)``
    — that wipes every cached ``list_*`` / ``get_*`` workspace read but
    leaves any future non-workspace cache namespaces (suggestions,
    routing, …) untouched.
    """
    with _lock:
        if prefix is None:
            count = len(_cache)
            _cache.clear()
            return count
        keys = [k for k in _cache if k.startswith(prefix)]
        for k in keys:
            _cache.pop(k, None)
        return len(keys)


def size() -> int:
    """Return number of entries currently cached. Mainly for tests."""
    with _lock:
        return len(_cache)


def _make_key(fn_name: str, args: tuple, kwargs: dict) -> str:
    """Compose a stable cache key from a function name + call args.

    Args order matters; kwargs are sorted by key for determinism. The
    key is namespaced with ``WORKSPACE_PREFIX`` so :func:`invalidate`
    can target the workspace bucket without touching future buckets.
    """
    sorted_kwargs = tuple(sorted(kwargs.items()))
    return f"{WORKSPACE_PREFIX}{fn_name}::{args}::{sorted_kwargs}"


# ---------------------------------------------------------------------------
# Decorator for MCP read tools
# ---------------------------------------------------------------------------


def cache_workspace_read(ttl: float = DEFAULT_TTL_SECONDS) -> Callable[[F], F]:
    """Decorate an MCP read tool body to cache its result for ``ttl`` seconds.

    Usage::

        @mcp.tool(annotations=_RO)
        @cache_workspace_read()
        def list_libraries() -> str:
            ...

    On cache hit the wrapped function is NOT called — the cached value
    is returned directly, skipping the socket round-trip to Flame and
    every side effect inside the function body (`_track_dedicated()`,
    `_stats` increments, suggestion annotation). This is intentional:
    a cache hit is, by definition, the same result as the previous call,
    so re-running the side effects would inflate the stats.

    The cache is keyed by the function's ``__name__`` plus its
    positional and keyword arguments. Each distinct argument tuple
    occupies its own cache slot — ``list_reels("LibA")`` and
    ``list_reels("LibB")`` are independent entries.

    Cache misses always call through and store the result before
    returning. Exceptions are NOT cached — the next call will retry.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _make_key(fn.__name__, args, kwargs)
            cached = get(key, ttl=ttl)
            if cached is not None:
                return cached
            result = fn(*args, **kwargs)
            set_value(key, result)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
