# `_stats` per-session reset — design & patch proposal

Status: **helper merged, server.py wiring pending manual apply**
Owner: main Claude session (server.py is off-limits to subagents —
see `~/.claude/projects/-Users-abraham-Projects/memory/feedback_agent_file_safety.md`).
Related: Chat 44 audit, `docs/ARCHITECTURE.md` §11.

## 1. Problem

`src/flame_mcp/server.py::_stats` is a module-level dict that accrues
metrics (exec calls, tokens in/out, RAG savings, patterns learned, …)
for the lifetime of the MCP server process. Claude Desktop keeps the
server spawned across many Claude sessions (days / weeks), so
`session_stats()` reports cumulative numbers rather than "this
session". The efficiency badge (✅ / ⚠️) computed from those numbers
is meaningless once the process has served more than one Claude
session.

## 2. What the MCP protocol gives us (nothing useful)

We audited `mcp.server.fastmcp.Context` in the currently pinned
`mcp` package:

| Field                 | Populated by Claude Code? | Stable across tool calls in one Claude session? | Changes at new session? |
|----------------------|:-:|:-:|:-:|
| `request_id`          | yes (UUID per call) | no — **per call** | yes |
| `client_id` (via meta)| **no**              | —                 | —   |
| `session`             | yes (MCP session)   | yes — per stdio pipe | only on process restart |

Over stdio the server process is the session: there is no "new
session" signal the server can observe. We therefore cannot drive
the reset off a protocol event — we have to synthesise one.

## 3. Chosen design

Two triggers, both implemented in `flame_mcp._session_stats`:

1.  **Idle auto-reset** — if the gap between the previous tool call
    and the new one is `>= idle_reset_seconds` (default 1800 s = 30
    min), zero the counters on entry to the new call. Captures the
    common "next morning" case.
2.  **Explicit `reset_session_stats()` MCP tool** — a new read-only
    tool the model or the operator can call to zero the counters on
    demand. Covers back-to-back sessions under the idle threshold
    and is the only honest answer for operators who want an exact
    audit boundary.

Both update `_stats_reset_at`, which is already surfaced in
`session_stats()` via the `(since HH:MM:SS)` header.

Why these two specifically:
- Idle reset is non-intrusive and works without any model
  cooperation — most Claude sessions are separated by significant
  idle time.
- Explicit reset is deterministic — operators and advanced users
  get a precise zero point and audit trail.
- Neither trigger requires Anthropic to change Claude Code or the
  MCP spec.

## 4. Helper module (merged)

`src/flame_mcp/_session_stats.py`:

- `make_empty_stats() -> dict` — canonical zero template. Must be
  kept in sync with `server.py::_stats`; a future concept invariant
  (`_stats_keys_bidirectional`) should lock the two.
- `should_auto_reset(now, last_call_at, *, idle_reset_seconds) -> bool`
- `apply_idle_reset(stats, now, last_call_at, *, idle_reset_seconds)`
  `-> (did_reset, reset_at)` — **mutates `stats` in place** (preserves
  identity, so server.py's module-level reference stays valid).
- `reset_stats(stats, now) -> datetime.datetime` — unconditional
  clear for the explicit tool.

Tests: `tests/test_session_stats.py` (13 cases, all passing).

## 5. Patch proposal for `server.py`

Two small edits — both additive, neither removes existing behaviour.
Apply in a single commit together with a `.concepts.yml` entry (see
§6) and a CHANGELOG entry.

### 5.1 Initialisation + tracker

```diff
--- a/src/flame_mcp/server.py
+++ b/src/flame_mcp/server.py
@@ -29,6 +29,11 @@ from flame_mcp.safety import (
     _CREATION_INTENT_RE,
 )
+from flame_mcp._session_stats import (
+    apply_idle_reset,
+    make_empty_stats,
+    reset_stats as _reset_stats_helper,
+)

 _SERVER_DIR = Path(__file__).resolve().parent.parent.parent

@@ -115,21 +120,18 @@ _DEDICATED_TOOL_SAVINGS = 800

-_stats = {
-    'exec_calls':         0,
-    'tokens_in':          0,   # tokens sent to Flame (code)
-    'tokens_out':         0,   # tokens received from Flame (output)
-    'rag_calls':          0,
-    'tokens_saved':       0,   # tokens saved by RAG vs loading full doc
-    'dedicated_calls':    0,   # calls to hardcoded tools (no RAG needed)
-    'tokens_saved_tools': 0,   # tokens saved by dedicated tools
-    'patterns_learned':   0,   # auto-learned patterns added to FLAME_API.md
-    'patterns_staged':    0,   # C5 — candidates staged by non-trusted models
-    'patterns_failed':    0,   # C5 — failed executions logged for gap analysis
-    'timings':           [],   # REC-001: ring buffer of recent call timings (max 20)
-}
+# Canonical stats dict. Schema lives in flame_mcp._session_stats.make_empty_stats
+# to keep the initialiser and the reset path from drifting.
+_stats = make_empty_stats()
 # Records when _stats was last reset (server start or Flame crash recovery)
 _stats_reset_at = datetime.datetime.now()
+# Timestamp of the previous MCP tool call — drives the idle-gap auto-reset.
+# Updated by _track_call() on every server-entry point that mutates _stats.
+_last_call_at: datetime.datetime | None = None
+# Idle window (seconds) after which _stats is auto-zeroed on the next call.
+# Overridable via config.json -> stats_idle_reset_seconds.
+_STATS_IDLE_RESET_SECONDS = int(
+    _get_config().get("stats_idle_reset_seconds", 30 * 60)
+)
```

### 5.2 Call tracker + explicit reset tool

```diff
@@ -230,6 +232,27 @@ def _rating(tokens: int) -> str:
     else:
         return "🔴 high"

+
+def _track_call() -> None:
+    """
+    Update the last-call timestamp and auto-reset _stats if the caller
+    has been idle for >= _STATS_IDLE_RESET_SECONDS. Must be called at
+    the top of every MCP tool entry point that mutates _stats.
+    """
+    global _last_call_at, _stats_reset_at
+    now = datetime.datetime.now()
+    did_reset, reset_at = apply_idle_reset(
+        _stats, now, _last_call_at,
+        idle_reset_seconds=_STATS_IDLE_RESET_SECONDS,
+    )
+    if did_reset:
+        _stats_reset_at = reset_at
+    _last_call_at = now
+
+
 def _stats_footer() -> str:
```

Then prepend `_track_call()` to every `@mcp.tool()` that currently
writes to `_stats` (execute_python, the dedicated tools that bump
`tokens_out`, search_flame_docs, learn_pattern). Single line each:

```diff
@@ def execute_python(...):
+    _track_call()
     # existing body...
```

(Alternative, less invasive: put `_track_call()` at the start of
`_call_flame` and `search_flame_docs` only — those are the funnel
points all other tools go through.)

### 5.3 Explicit reset tool

```diff
@@ def session_stats() -> str:
     ...
+
+@mcp.tool(annotations=_RO)
+def reset_session_stats() -> str:
+    """
+    Zero the session stats counters immediately.
+
+    Use at the start of a new Claude session (or a fresh debugging
+    run) when the idle-based auto-reset has not fired — for example
+    when two sessions happen back-to-back. Returns a confirmation
+    line with the new reset timestamp.
+    """
+    global _stats_reset_at
+    now = datetime.datetime.now()
+    _stats_reset_at = _reset_stats_helper(_stats, now)
+    return f"📊 Session stats reset at {now.strftime('%H:%M:%S')}"
```

### 5.4 Footer wording (cosmetic, optional)

The `session_stats()` "(since HH:MM:SS)" header already reflects the
new reset correctly because `_stats_reset_at` is updated by the
helper. No rewording required.

## 6. `.concepts.yml` updates bundled with the server.py patch

When applying §5, also add an invariant that locks `_stats`'s key
schema between server.py and the helper so one cannot be extended
without the other:

```yaml
  stats_keys_schema_shared:
    description: >
      The set of keys in server.py's `_stats` dict must match the
      set produced by flame_mcp._session_stats.make_empty_stats().
      Prevents silent drift when a new counter is added to only one
      side.
    source_of_truth:
      file: src/flame_mcp/_session_stats.py
      symbol: make_empty_stats
    mirrors:
      - file: src/flame_mcp/server.py
        symbol: _stats (module-level dict)
    invariants:
      - id: stats_keys_bidirectional
        type: claim_verifies
        claim: "server.py initialises _stats via make_empty_stats()"
        code_grep:
          regex: '_stats\s*=\s*make_empty_stats\(\)'
          file_pattern: 'src/flame_mcp/server.py'
        expected: found
```

## 7. Tool inventory bookkeeping

Adding `reset_session_stats` grows the tool count by one. The
`readme_tool_count_matches_code` invariant will fail until
`README.md`'s `## MCP Tools (N)` heading and the tool table inside
`concept:mcp_tool_table` are updated. Do both in the same commit as
the server.py patch.

## 8. Rollout

1.  Main Claude session opens `src/flame_mcp/server.py` and applies
    the diffs from §5 + the `.concepts.yml` stanza from §6 + the
    README tool-table/count bump from §7 — all in one commit.
2.  Run `python -m pytest tests/` and
    `python scripts/verify_concepts.py` — both must pass.
3.  Cut `v1.4.0` (new MCP tool = minor bump per the ecosystem
    convention) with CHANGELOG entry documenting both the reset
    behaviour and the new tool.

## 9. Rejected alternatives

- **Key stats by `client_id`** — rejected: Claude Code does not
  populate `meta.client_id`. The bucket would always be `None`.
- **Subscribe to MCP `initialize` notifications** — rejected: stdio
  transport re-initializes only when the process restarts, which
  already gives a fresh process with fresh `_stats`. Adds no signal.
- **Fixed wall-clock reset (e.g. midnight)** — rejected: arbitrary,
  surprises operators in non-local timezones.
- **Remove `_stats` entirely** — rejected: the counters power the
  efficiency footer and the `session_stats` tool, both relied on by
  the ecosystem.
