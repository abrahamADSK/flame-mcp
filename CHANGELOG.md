# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `create_sequence` raised `AttributeError: 'PyMediaPanel' object has no
  attribute 'create_sequence'` on Flame 2027 — it called
  `flame.media_panel.create_sequence(name=…)` (which does not exist) and
  ignored the resolved reel. Now calls `PyReel.create_sequence(name=…)`, so the
  sequence is created in the target library/reel — the API already canonical in
  the RAG docs, test fixtures and golden set. Confirmed in-vivo on Flame 2027
  (build 2027.pr238). Adds the previously-missing `test_create_sequence`
  regression guard (asserts `reel.create_sequence(`, rejects
  `media_panel.create_sequence`) plus a reel-not-found case. `create_sequence`
  is a pre-4C tool and was outside the Chat 53 "validated live" set, which is
  why the bug shipped uncaught.

## [1.9.0] — 2026-05-21

### Added — 4C write tools + execute_plan ops (Chat 53)

- Ten dedicated write tools, each registered as a closed-schema
  `execute_plan` op and **validated live against Flame 2027**:
  - `render_batch` — Background Reactor render of the current Batch Group,
    scheduled via `flame.schedule_idle_event` (calling `flame.batch.render()`
    synchronously crashes Flame and the `execute_python` AST guard blocks it,
    so a dedicated `# DT` tool is required to run the documented-safe form).
  - `export_clip` — `PyExporter` export via idle event (same deadlock guard).
  - `import_clips` — import media from disk into a library/reel.
  - `create_library`, `create_reel`, `create_folder`, `create_reel_group`,
    `create_batch_group` — container creation.
  - `timeline_insert`, `timeline_overwrite` — `PySequence.insert` / `overwrite`.
- `execute_plan` annotation flipped read-only → destructive, since a plan can
  now trigger these write ops.
- MCP tool count 28 → 38; README table, CLAUDE.md rule 16 and the
  `execute_plan` docstring updated in lockstep under the concept registry.
- `render_batch` / `export_clip` detect when the GUI-thread APIs
  (`schedule_idle_event`, `PyExporter`) are unbound (Flame backgrounded) and
  return a clear "bring Flame to the foreground" message instead of a raw
  `AttributeError`.

### Fixed — docs Flame 2027 correctness (Chat 53)

- Wiretap SDK/CLI documentation paths updated 2026.2.2 → 2027
  (python3.11 → 3.13).
- Four PySegment/PySequence API-signature errors corrected against the 2027
  graph: `is_rendered` removed from PySegment (clip-level only);
  `create_version(stereo=…)` not `name=`; `create_connection` /
  `remove_connection` take no argument; `smart_replace*` take a `PyClip`,
  not a reel.

### Changed — Flame 2027 support (Chat 52)

- Migrated the supported Flame version 2026 → **2027**. Regenerated
  `rag/api_graph.json` from a live Flame 2027 box (`flame_version: 2027`;
  72 classes / 25 functions / 10 module attrs). The 2027 Python API is a
  strict **superset** of 2026 — 5 new classes (`PyMetadataNode`,
  `PyMetadataTimelineFX`, `PyMetadataValue`, `PyNodeMarker`,
  `PyReadFileNode`) and 2 new functions (`flame.clear_graphics_memory`,
  `flame.clear_unreferenced_cache`), **zero removals** — so F4b now
  accepts 2027 symbols and no existing pattern breaks.
- Updated version strings and Autodesk doc URLs (2026 → 2027) in
  `CLAUDE.md`, the `README.md` compatibility table (2027 row now
  3.13.3 / PySide6 / Tested), and the `FLAME_API.md` header. Flame 2027
  ships Python 3.13.
- Validation: 517 tests + 36/36 concept invariants green against the 2027
  graph; live `get_flame_version` → `2027` on the bridge. **Not yet
  re-validated on 2027:** Wiretap SDK/CLI paths (docs still cite 2026.2.2)
  and the full write-op tool round-trip. Installed build is `2027.pr238`.

### Fixed — Chat 52 in-vivo validation findings

- **Name comparisons failed against real Flame.** On Flame 2026,
  `str(obj.name)` returns a single-quote-wrapped string for
  libraries/reels/clips (`'Default Library'`, not `Default Library`).
  Every name comparison (`== name`, `in HIDDEN`) therefore mismatched
  against a live bridge: hidden system libraries (`Timeline FX`,
  `Grabbed References`) leaked into `list_libraries`, and name-based
  lookups in `list_reels`, `list_clips`, `get_clip_metadata` and
  `get_source_path` always returned "not found". Normalised every
  `str(x.name)` comparison with `.strip("'")` (the convention already
  used in `FLAME_API.md`). Mock-only tests masked this because the
  mocked bridge returns clean names.

- **Bridge socket resolution trapped by stale files.** `_BRIDGE_SOCKET`
  was resolved once at import time by file *existence*, so a leftover
  socket file (e.g. `<repo>/run/flame_mcp.sock` from a prior dev
  session) hijacked the resolver even when the live bridge listened on
  `/tmp/flame_mcp.sock` — every tool returned "Cannot connect to Flame".
  Replaced with probe-on-connect (`_connect_bridge`): try each candidate
  socket by actually connecting, first that accepts wins, TCP fallback
  last. A dead socket file is now harmless. Added
  `tests/test_bridge_connect.py` (real local sockets, runs in CI).

## [1.8.0] — 2026-05-19

### Added — F5b: Ruta A — structured plan output (Issue #12, AJUSTE 1)

The deepest reliability win of the chat 51 roadmap. The LLM can now
submit a structured JSON plan via the new `execute_plan` MCP tool
instead of writing raw Python. The plan is validated against a closed
schema (each op carries a typed pydantic args model with
`extra="forbid"`). Hallucinated symbols and wrong arg shapes are
rejected at the protocol level — they never reach Flame.

- New `src/flame_mcp/_plan_schema.py` module:
  - Schema shape v1: `{"ops": [{"op": "<name>", "args": {...}}, ...]}`.
  - 6 registered ops in v1: `list_libraries`, `list_reels`,
    `list_clips`, `get_project_info`, `get_clip_metadata`, `ping`.
  - Per-op pydantic models enforce `extra="forbid"` +
    `str_strip_whitespace=True`.
  - `validate_plan(plan)` returns parsed (op_name, args_instance)
    pairs or raises `PlanValidationError` with LLM-facing message.
  - `dispatch_plan(plan)` validates then dispatches op-by-op with
    per-op headers + final summary; short-circuits on handler
    failure with the exact index reported.
  - `register_op(name, handler)` wires server-side handlers at
    import time (server.py is the only caller); raises on unknown
    name to surface typos loudly.
- New `execute_plan` MCP tool in `src/flame_mcp/server.py`:
  - Wires handlers for the 6 ops above (each delegates to its
    existing dedicated tool — F5b is a protocol change, not a
    behaviour change).
  - On schema rejection: increments `_stats['plan_ops_rejected_by_schema']`
    and returns the rejection message without touching Flame.
  - On success: increments `_stats['plan_ops_executed']` by the op
    count.
- `execute_python` is NOT deprecated. F5b co-exists. Migration path:
  observe F0 telemetry, migrate frequent `execute_python` calls into
  new plan ops, only deprecate `execute_python` once the corresponding
  plan ops are stable.
- `tests/test_plan_schema.py` — 21 unit tests covering schema
  rejection (unknown op, extra keys, missing keys, wrong types, empty
  ops, non-dict plan), args model rejection (missing required, unknown
  arg), dispatch order preservation, short-circuit on handler failure
  (subsequent ops NOT invoked), `register_op` typo detection,
  `describe_registry` JSON-serialisability, sorted `op_names`.
- `README.md` — tool count `27 → 28`, `execute_plan` added to the
  tool table.
- `CLAUDE.md` — new rule 16 with 3 worked examples for `execute_plan`.
- `.concepts.yml` — new `structured_plan_output` concept with 3
  invariants: 2 × `file_exists` (module, tests) + `every_op_is_a_tool`
  subset (op keys in `_OP_REGISTRY` ⊂ `@mcp.tool` decorator names in
  server.py). Pre-commit verifier: 36/36 (was 33/33).

Tests: 512 passed, 113 skipped, 0 failed (was 491/113).

### Changed — F6a: trim CLAUDE.md (Issue #13, AJUSTE 3 — unblocked by F3b)

- `CLAUDE.md` reduced 359 → 290 lines (~19 %, ~69 lines / ~4.8 KB
  removed). Operator-only sections moved out so the LLM system prompt
  no longer carries content the LLM never acts on.
- New `docs/DEPLOY.md` — receives the relocated content:
  - "Prerequisites for local models" (Ollama install + alias setup).
  - "Deploy workflow — after every code change" section (symlink
    setup, `pkill` + `cp` recipes per file, **MCP Bridge → Reload
    hook** step). Two paths (with-symlink / fresh-machine fallback).
- `CLAUDE.md` retains a 2-line pointer to `docs/DEPLOY.md` so the
  operator can find the workflow when reading the prompt-facing file.
- `CLAUDE.md` also drops the "## Community" subsection (Logik Forum
  + Autodesk Community URLs) — not actionable for the LLM, and the
  URLs remain searchable when needed.
- `.concepts.yml` gains a `claude_md_trim` concept with 3 invariants:
  1 × `file_exists` (`docs/DEPLOY.md`) + 2 × `claim_verifies` that
  re-expansion of `CLAUDE.md` cannot re-introduce the deploy section
  heading or the embedded shell commands. Pre-commit verifier: 33/33
  (was 30/30 after F4b).

### AJUSTE 3 gate

The trim was blocked until F3b shipped ≥ 10 adversarial entries
(`scripts/check_adversarial_count.py`) so the LLM-facing API trap
warnings now have an executable defense via the golden routing
dataset. Current state: 16 adversarial ≥ 10 required ✓.

Token impact (rough): ~1200 fewer tokens per LLM turn that loads the
system prompt. Strictly Pareto — no LLM behavioural rule was modified,
only operator-facing text relocated.

Tests: 491 passed, 113 skipped, 0 failed (golden suite unchanged).

### Added — F4b: AST dry-run walker (Issue #11)

- New `src/flame_mcp/_ast_validate.py` module — static validator that
  walks the AST of any source about to be sent to `execute_python` and
  flags `flame.X.Y` references that do not exist in `rag/api_graph.json`
  (the introspected truth from F2-intro).
  - `validate_python(source, graph=None)` returns an `AstValidation`
    dataclass with `issues: list[UnresolvedSymbol]` and `graph_loaded`
    flag (False when the graph file is missing or empty → walker
    degrades to a no-op, never blocks legitimate code).
  - `UnresolvedSymbol` carries the dotted path, line/col, and an
    optional `suggestion` from `difflib.get_close_matches`.
  - `format_issues(validation)` returns a human-readable rejection
    message with each symbol's position, suggestion, and the
    `ast_dry_run: false` config escape hatch.
- `src/flame_mcp/server.py::execute_python` runs the walker as
  pre-flight when `config.json -> ast_dry_run` is true (default).
  On rejection, returns the formatted message + footer WITHOUT
  touching the bridge and increments `_stats['ast_dry_run_rejected']`.
- `tests/test_ast_validate.py` — 15 unit tests: missing-graph and
  malformed-JSON degradation, graph-symbols flatten, happy-path
  acceptance (including prefix-resolved chains so legitimate
  `flame.batch.render` calls inside `schedule_idle_event` are NOT
  rejected), hallucinated-symbol rejection (`flame.selection`,
  `flame.foo_bar_baz`), close-match suggestion, multi-issue
  collection, syntax-error silence (let the bridge surface it),
  non-`flame.*` chain ignored, `format_issues` formatting.
- `.concepts.yml` gains an `ast_dry_run_validator` concept with 3
  invariants: 2 × `file_exists` (module, tests) + 1 × `subset` pinning
  the validator import in server.py. Pre-commit verifier: 30/30
  (was 27/27).

What F4b CAN and CANNOT catch (documented in module docstring):

- CAN catch: `flame.selection` (non-existent), `flame.foo_bar_baz`
  (invented), method typos on known classes.
- CANNOT catch: usage traps where the symbol IS valid but the call
  pattern is wrong (e.g. `flame.batch.render` without
  `schedule_idle_event`). Those are F3b's golden adversarial dataset's
  scope, enforced at the routing layer.

Tests: 491 passed, 113 skipped, 0 failed (was 476/113).

### Added — F4a: workspace snapshot with TTL 12s + write-invalidation (Issue #10, AJUSTE 2)

- New `src/flame_mcp/_workspace_snapshot.py` module — thread-safe,
  per-process cache for workspace read tools.
  - `get(key, ttl=12.0)` / `set_value(key, value)` — monotonic-clock
    TTL store. Lazy GC on stale entries.
  - `invalidate(prefix=None)` — drop by key prefix (or all). Returns
    count dropped.
  - `cache_workspace_read(ttl=12.0)` — decorator wrapper for MCP tool
    bodies. Caches keyed by `__name__` + positional args + sorted
    kwargs. Skips function body on hit (no socket round-trip, no
    `_stats` inflation). Exceptions are NOT cached.
- `src/flame_mcp/server.py` — 7 read tools now decorated with
  `@_cache_workspace_read()`: `get_project_info`, `list_libraries`,
  `list_reels`, `list_clips`, `list_desktop_reels`, `list_batch_groups`,
  `list_all_projects`. `execute_python` calls
  `_workspace_invalidate(_WORKSPACE_PREFIX)` after every exec
  (success or failure — partial mutations on error are still
  mutations). This is **AJUSTE 2** of the chat 51 v2 plan: TTL alone
  was insufficient because a post-delete read within TTL would have
  served the pre-delete view.
- `tests/test_workspace_snapshot.py` — 14 unit tests: get/set, TTL
  expiry (monotonic-clock injected via monkeypatch — no `time.sleep`,
  suite stays < 100 ms), invalidate prefix vs all, decorator caches
  by arg tuple, decorator does not cache exceptions, decorator
  respects custom TTL, decorator invalidation forces refresh, 2-thread
  concurrent-read smoke test.
- `.concepts.yml` gains a `workspace_snapshot_cache` concept with 3
  invariants: 2 × `file_exists` (module, tests) + 1 × `subset` pinning
  the `_workspace_invalidate(_WORKSPACE_PREFIX)` call in server.py
  against the `def invalidate` declaration. Pre-commit verifier:
  27/27 (was 24/24).

Tests: 476 passed, 113 skipped, 0 failed (was 462/113).

### Added — F3a: concept_map bypass via api_graph.json (Issue #9)

- New `src/flame_mcp/routing.py` module with two functions:
  - `_route_from_graph(query, graph=None)` searches the introspected
    `rag/api_graph.json` (produced by F2-intro) for the best match,
    returning a concept-shaped dict with `_provenance="graph"`. **Safety
    filter**: any matched entry whose introspector-attached `notes` list
    is non-empty (trap hints like `schedule_idle_event`, `.clear()`
    crash) is refused — function returns `None` so the LLM falls
    through to RAG (which has the curated docs). A small
    `_FORBIDDEN_API_PATHS` allowlist also short-circuits known
    non-existent symbols (`flame.selection`,
    `flame.projects.current_project.libraries`).
  - `resolve_query(query, graph=None)` is the dual-source chain:
    `resolve_concept` (curated, low-latency) → `_route_from_graph`
    (introspected, broader). Every non-None result carries a
    `_provenance` field (`"concept_map"` | `"graph"`) for telemetry.
- `src/flame_mcp/server.py::resolve_concept` MCP tool now delegates to
  `routing.resolve_query` so the LLM-facing tool transparently benefits
  from graph fallback. Response surfaces `Source: <provenance>` line.
- `tests/test_routing.py` — 15 unit tests covering safe-symbol
  surfacing, trap-flagged refusal, missing-file degradation, malformed
  JSON, cache behaviour, and the `resolve_concept → _route_from_graph`
  chain with `_provenance` propagation.
- `tests/fixtures/api_graph_sample.json` — small hermetic graph
  fixture (3 functions, 2 classes with methods, trap notes on
  `PyBatch.render` and `PyClip.clear`) so the tests work in CI where
  the real graph is not generated.
- `tests/test_golden.py` switches its import from `resolve_concept`
  to `routing.resolve_query` (aliased) so the F3b adversarial suite now
  exercises the full chain. All 16 adversarial entries still fail
  `must_not_contain` (no regression). All 48 happy-path entries
  continue to resolve via `concept_map` (no expected_tool change).
- `.concepts.yml` gains a new `dual_source_routing` concept with 4
  invariants: 3 × `file_exists` (routing.py, fixture, tests) plus a
  `subset` invariant pinning the `from flame_mcp.routing import
  resolve_query` import in server.py against the `def resolve_query`
  declaration. Pre-commit verifier: 24/24 (was 20/20).

Tests: 462 passed, 113 skipped, 0 failed (was 447/113).

## [1.7.0] — 2026-05-18

### Added — Chat 51 performance + reliability plan (6 phases F0–F3b)

- **F0 — Baseline telemetry** (PR #3). New `_session_stats.py` helpers
  `persist_timing` / `persist_turn` write append-only JSONL to
  `logs/timings.jsonl` (per-call) and `logs/turns.jsonl` (per-turn) with
  ~5 MB size-cap rotation to `.1`. New counters `turns_total` and
  `failed_turns` enable `p_fallo = failed_turns / turns_total` as a
  cross-session reliability metric. Server-side `_track_timing` enriches
  each entry with `ts`, `model`, `backend`, `tool_name`, `score`,
  `error`. Bridge-side `_agent_loop` writes one turn row per invocation
  from the outer `finally` so timeouts and early-exits are still
  captured. `.gitignore` extended to cover `*.jsonl` and `*.jsonl.1`.
  Tests +9 (209/209). Concept verifier: 20/20.

- **F1a — `_stats_footer` modes** (PR #4, AJUSTE 4). `_stats_footer(mode)`
  accepts `none` / `minimal` / `full`, default `minimal` reads from
  `config.json -> stats_footer_mode`. `minimal` returns `""` (per-call
  timing already lives in the `execute_python` preamble), `full` restores
  the historical multi-line aggregate. Net reduction of ~80–150 tokens
  per LLM turn that uses `execute_python` or `search_flame_docs`. Tests
  +6 (27/27 in test_session_stats).

- **F1b — Ollama `keep_alive` config knob** (PR #5). New
  `src/flame_mcp/_config.py::resolve_keep_alive` helper reads
  `config.json -> ollama_keep_alive` as a duration string (`"30m"`) or
  int seconds; rejects dict/list/None/bool with default fallback.
  Default bumped 10 min → 30 min so reading-pauses between turns don't
  trigger Ollama cold-load (5–30 s penalty on 9B models). Bridge
  `_preload_ollama_model` delegates via helper with inline fallback
  (Chat 44 helper-extraction pattern). Tests +9 (19/19 in test_config).

- **F2-intro — Flame API introspector** (PR #6). New
  `scripts/introspect_flame_api.py` walks Flame's embedded `flame`
  Python module and emits structured JSON to `rag/api_graph.json` with
  module-level attributes, free functions, and classes (with methods +
  attrs). Becomes source-of-truth for downstream F3a (concept_map
  bypass), F4b (AST dry-run walker), F5b (structured plan schema).
  `--check` exits 2 with sentinel when run outside Flame. Cadence:
  regenerate per Flame major release (2026.x → 2027.x). Tests +3.

- **F2-wt — Wiretap smoke harness** (PR #7). New
  `scripts/wiretap_smoke.sh` iterates the 37 Wiretap CLI tools listed
  in `docs/wiretap_cli_reference.md`, default `--help`, hard skip for
  5 destructive tools, `timeout 5s` wrapper, captures exit + first 5
  lines stdout/stderr + ms. Emits Markdown table to
  `docs/wiretap_smoke_report.md`. Companion `scripts/wiretap_sdk_smoke.py`
  runs the SDK init→server→node→getNumChildren sequence and emits
  JSON to stdout. Both bash 3.2 / shellcheck / py_compile clean.

- **F3b — Golden routing dataset + adversarial gate** (PR #8). New
  `tests/golden/flame_queries.jsonl` with 83 curated queries (48
  happy-path, 16 adversarial, 14 Spanish fall-through) across 9
  categories. Schema: `{id, query, lang, expected_tool, expected_concept,
  must_contain[], must_not_contain[], tags[], category}`. Adversarial
  entries assert the router does NOT propose forbidden symbols
  (`flame.selection`, `flame.batch.render` without `schedule_idle_event`,
  `.clear()` on containers, etc.). Hermetic pytest runner
  `tests/test_golden.py` mocks `flame_mcp.rag.search.search` and uses
  `resolve_concept` directly. New pre-commit gate
  `scripts/check_adversarial_count.py` exits 0 iff ≥10 adversarial
  entries with non-empty `must_not_contain` — currently 16, **unblocks
  F6a** (CLAUDE.md trim).

### Added — Architecture documentation (PR #14)

- `docs/CHAT_51_PLAN.md` — 7-phase roadmap reconstructed from the six
  open PRs after the original `/ultraplan` v2 output was lost. Covers
  the expected-latency metric, the four v2 AJUSTES, and acceptance
  criteria for the five pending phases (F3a, F4a, F4b, F5b, F6a).
- `docs/ARCHITECTURE.md` extended with §§13–16: granular Mermaid
  request-flow diagrams (top-level orchestration, RAG internals,
  `execute_python` pipeline, LLM decision tree from CLAUDE.md rules);
  seven parallel self-learning loops with cross-loop properties;
  21-row pre-designed elements catalogue with origin chat per row;
  honest uniqueness analysis vs a stock MCP server. References
  renumbered §12 → §17.
- `docs/PHASE_TRACKER.md` — single-glance status table mirroring the
  six merged PRs and the five new pending-phase issues, with an
  update protocol.

### Pending — next-phase issues opened

- #9 F3a — concept_map bypass via `api_graph.json`.
- #10 F4a — workspace snapshot TTL 12 s + write-invalidation (AJUSTE 2).
- #11 F4b — AST dry-run walker.
- #12 F5b — Ruta A: structured plan output schema (AJUSTE 1).
- #13 F6a — trim CLAUDE.md (AJUSTE 3, unblocked by F3b).

## [1.6.0] — 2026-04-22

### Added
- `src/flame_mcp/suggestions.py` — `list_flame_logs → read_flame_log`
  rule. Parses the `📁 <dir> (N files)` header + indented log rows
  sorted by mtime, picks the first (most recent) log, and seeds a
  `read_flame_log` call with the standard diagnostic grep pattern
  `Error|Traceback|Exception|crash` and `lines=200`. Natural triage
  flow when the user runs `list_flame_logs` because something looked
  off. Short-circuits on "❌ Log directory not found", "❌ Error
  listing logs", and "No log files found" responses.
- `scripts/invariant_types.py` — `_write_subset` handler registered
  in WRITERS (Phase C + D, Chat 48). Covers `b_source.type:
  anchor_list` (without `item_pattern`) and `file_regex_matches`
  (with YAML opt-in `b_source.writer.line_template`). Enables
  `/propagate-change` Path A to auto-fix subset-drift without
  manual edits for the common cases.
- `.github/workflows/ci.yml` — Codecov coverage upload step
  (`codecov/codecov-action@v4`), gated to `matrix.python-version ==
  '3.12'`.

### Fixed
- `scripts/invariant_types.py` — `version_match` handler honors
  opt-in `tolerate_release_in_progress: true`. Applied to
  `.concepts.yml` on the `pyproject_matches_latest_tag` invariant to
  unblock `cut-release.sh` under strict mode.

## [1.5.0] — 2026-04-22

### Added
- `src/flame_mcp/suggestions.py` — next_suggested_actions pattern port
  (Chat 47). Text-contract variant of the fpt-mcp/maya-mcp rule engine:
  hints are appended to tool output as a visible `➡ Next you could also:`
  trailing block rather than mutating JSON. Ships with `list_libraries →
  list_reels` rule, `FLAME_MCP_DISABLE_SUGGESTIONS` kill switch, and a
  cap of 3 suggestions per response. Wired via
  `maybe_annotate_with_suggestions` in `server.py`.
- `.concepts.yml` — `next_suggested_actions_contract` concept with
  `every_rule_is_wired` invariant (ast_dict_keys `SUGGESTION_RULES` ⊂
  regex capture of `maybe_annotate_with_suggestions("<tool>", …)`
  call-sites). Pre-commit fails if a rule is registered without being
  wired at the tool level.
- `src/flame_mcp/suggestions.py` — two new chaining rules (Chat 48,
  this release): `list_reels → list_clips` (fires on no-filter responses
  with `[Library]` headers, skips hidden libs and empty reels) and
  `list_clips → get_clip_metadata` (parses `[Library] / [Reel] — N
  clip(s)` header, picks first visible clip, ignores `… and N more`
  summary lines). Completes the navigation breadcrumb
  `list_libraries → list_reels → list_clips → get_clip_metadata`. Tests
  grew from 183 to 197 (+14); invariant count 15 → 20.
- `.github/workflows/ci.yml` — GitHub Actions CI workflow. Four blocking
  jobs: pytest across Python 3.10/3.11/3.12 matrix, ruff lint, mypy,
  verify_concepts. Pytest coverage reported inline via `--cov=<pkg>
  --cov-report=term`.
- `.github/workflows/pr-review.yml` — automated Claude PR review
  (`anthropics/claude-code-action@v1`). Byte-identical across the 4
  ecosystem repos; canonical at `~/Projects/pr-review-canonical.yml`.
  Prompts Claude to audit concept-registry compliance first, then
  correctness, style, and ecosystem coherence. Uses
  `claude_code_oauth_token` (not API key) — ecosystem standard is
  Max/Pro subscription via OAuth. Requires GitHub App + workflow
  permission `id-token: write` + `--model claude-sonnet-4-6` pin so the
  OAuth token (Sonnet-scoped) works against the default-Opus action.
- `scripts/verify_concepts.py --write` — WRITER MODE (Chat 46). Requires
  the triple flag `--accept-current-as-truth --i-reviewed-diff --write`.
  Dispatches to per-type writers in `invariant_types.py::WRITERS`.
  Currently supports `tool_count` and `review_expiry`; other types
  report `WRITER UNSUPPORTED`. No auto-commit.
- `scripts/cut-release.sh` — ecosystem-shared release orchestrator.
  Validates clean tree + semver arg + non-empty `[Unreleased]`, edits
  CHANGELOG + `pyproject.toml`, commits with `CUT_RELEASE_VERSION=X.Y.Z`
  so the `changelog_tag_sync` invariant tolerates the transient
  pre-commit drift, then tags, pushes, and creates a GitHub release.
  Byte-identical across the 4 MCP-ecosystem repos.
- `scripts/invariant_types.py` — new `changelog_tag_sync` handler
  replaces the previous `subset`-based `changelog_tag_coherence`.
  Release-in-progress tolerance anchored to `CUT_RELEASE_VERSION` env
  OR `pyproject.toml`'s `version` field.
- `scripts/invariant_types.py` — `ast_dict_keys` canonical (Chat 47)
  now reads `ast.AnnAssign` in addition to `ast.Assign`, so typed-dict
  declarations like `SUGGESTION_RULES: dict[...] = {...}` resolve
  correctly. Synced byte-identical across 4 repos.
- `scripts/verify_concepts.py` — `ci_skip: true` flag on individual
  invariants + auto-skip of `review_expiry` under `GITHUB_ACTIONS`
  (Chat 47). Keeps dev-side invariants active via pre-commit while CI
  runs stay green without shipping `~/Projects/.external_versions.yml`
  or broad `gh` auth.

### Changed
- `.concepts.yml` — `strict: false → true`. The pre-commit hook now
  blocks commits on any unresolved invariant drift instead of only
  reporting it. Ecosystem-wide flip on 2026-04-20 (Chat 46), unblocked
  by the `changelog_tag_sync` release-in-progress tolerance.
- CI pipeline cleanup (Chat 47): ruff baseline cleared (all warnings
  fixed, job flipped to blocking), mypy baseline cleared (per-repo
  `[tool.mypy]` with `ignore_missing_imports=true` +
  `no_strict_optional=true`, job flipped to blocking). Both jobs now
  block merge rather than `continue-on-error: true`.

### Fixed
- `tests/test_rag_search.py` — `TestRagRealIndex` skipif guard now
  checks for `chroma.sqlite3` sentinel inside the index dir rather
  than `is_dir()` (Chat 47). A committed `.gitkeep` fooled the old
  guard in CI, causing real-index tests to attempt to run against an
  empty directory.
- `.github/workflows/pr-review.yml` — added `id-token: write` workflow
  permission (Chat 48). The action calls `getOidcToken()` during
  `setupGitHubToken`; without it the action errored with "Unable to
  get ACTIONS_ID_TOKEN_REQUEST_URL env variable" in 3 retries.
- `.github/workflows/pr-review.yml` — pinned `--model claude-sonnet-4-6`
  via `claude_args` (Chat 48). OAuth tokens from `claude setup-token`
  are scoped to Sonnet on Max/Pro; the action's default model (Opus
  after v1.0.100) returned `401 Invalid bearer token` against those
  credentials (see anthropics/claude-code-action#584).

### Documentation
- `README.md` — added a "Configuration precedence (env-var vs
  config.json)" subsection that surfaces the transport-vs-model
  asymmetry user-facing. Previously only in `docs/ARCHITECTURE.md
  §9/§11` (Chat 45 gotcha #4 closure).

## [1.4.3] - 2026-04-20

### Added
- `scripts/verify_concepts.py` — `--accept-current-as-truth` + `--i-reviewed-diff` double-flag escape hatch (REPORT MODE ONLY). When both flags are passed, the runner inspects every failing invariant and prints a human-readable "would update \<mirror\>" line describing what a hypothetical writer mode would change, then exits 0 without touching any file. Single-flag usage is rejected with exit code 2 by design — the double-flag requirement prevents accidental drift acceptance. Intended for repos that drifted while dormant and need a one-shot review before flipping `strict: true`. Writer mode is deferred to a future pass with explicit user sign-off. Chat 44 ultraplan Q5.

## [1.4.2] - 2026-04-20

### Added
- `.concepts.yml` — `github_release_per_tag` concept with the `every_v1plus_tag_has_github_release` invariant. Enforces that every `vX.Y.Z` tag (v1.0.0+) has a matching published GitHub Release; `gh release list` is the oracle. Pre-1.0 tags excluded (pre-release noise). Ecosystem-wide policy introduced in Chat 45 — now enforced per repo via the concept registry.

## [1.4.1] - 2026-04-20

### Fixed
- `hooks/flame_mcp_bridge.py` — `ollama_mac` backend now runs `_preload_ollama_model()` before spawning the claude subprocess. Without the preflight, Ollama's Anthropic-compat `/v1/messages` endpoint silently fell back to 4096 tokens on Mac-local inference even when the Modelfile declared a larger window. `_preload_ollama_model` gained optional `url` and `num_ctx` kwargs so the Mac branch can target `OLLAMA_MAC_URL` + `OLLAMA_MAC_NUM_CTX=8192`. Chat 45 / Agent D investigation.
- `.concepts.yml` — new `ollama_preflight_parity` concept with two `file_regex_matches` invariants guarding the two preflight call sites. `ollama_cloud` is deliberately excluded (cloud runners manage their own context window).

### Changed
- `scripts/invariant_types.py` + `scripts/verify_concepts.py` — synced to the ecosystem-canonical version (Chat 45 Agent F consolidation). Adds `ast_decorator_functions.name_kwarg`, `ast_enum_values`, and `ast_decorator_kwarg` (back-compat alias). Byte-identical with fpt-mcp, maya-mcp, vision3d.

## [1.4.0] - 2026-04-20

### Added
- `reset_session_stats` MCP tool (read-only) — zero the session stats counters on demand. Tool inventory 26 → 27.
- Idle-gap auto-reset: the first tool call after `stats_idle_reset_seconds` (default 30 min) of inactivity auto-zeros `_stats`. Overridable via `config.json → stats_idle_reset_seconds`.
- `.concepts.yml` invariant `stats_keys_schema_shared` locking `server.py::_stats` keys to `flame_mcp._session_stats.make_empty_stats()` so new counters cannot be added to only one side.

### Changed
- `src/flame_mcp/server.py` — `_stats` now initialised via `make_empty_stats()`; `_call_flame` and `search_flame_docs` invoke `_track_call()` on entry to drive the idle-gap reset. `_stats_reset_at` surfaced by `session_stats()` updates whenever either reset trigger fires.
- `docs/ARCHITECTURE.md` §1 — tool count 26 → 27.

## [1.3.1] - 2026-04-20

### Added
- `src/flame_mcp/_config.py` — shared `load_model_config()` helper. Canonical loader for the four widget-facing config.json keys (`model`, `backend`, `ollama_url`, `ollama_cloud_key`). Imported by the bridge via a `sys.path`-inserted bootstrap so it works even from `/opt/Autodesk/shared/python/`.
- `src/flame_mcp/_session_stats.py` — `make_empty_stats()`, `should_auto_reset()`, `apply_idle_reset()`, `reset_stats()`. Pure logic for the pending per-Claude-session `_stats` reset (server.py wiring proposed, not yet applied — see `docs/session_stats_reset.md`).
- `tests/test_config.py` (9 cases) and `tests/test_session_stats.py` (13 cases). Full suite 149 → 171.
- `docs/session_stats_reset.md` — design doc + unified-diff patch proposal for server.py and `.concepts.yml`. Follow-up `v1.4.0` will apply the patch and expose a new `reset_session_stats` MCP tool.

### Changed
- `hooks/flame_mcp_bridge.py::_load_model_config` now delegates to `flame_mcp._config.load_model_config()`. An inline fallback remains for Flame hosts deployed without the repo on disk.
- `docs/ARCHITECTURE.md` §11 — dead-code bullet retired (see *Removed*); `_load_model_config` and `_stats` bullets updated to reflect the helper landings and the pending server.py patch.

### Removed
- `src/flame_mcp/rag/generate_flame_api.py` — orphan generator. Not imported anywhere, produced an output file (`docs/flame_api_full.md`) that is absent from disk and from `rag/corpus.json`. Flagged for deletion in the Chat 44 audit (§11).
- README directory-tree illustration entry for `flame_api_full.md` (file never existed in the shipped tree).
- FLAME_API.md attribution header "Auto-generated by …" (stale — the file is curated by hand and extended at runtime by `learn_pattern`).

## [1.3.0] - 2026-04-17

### Added
- `.concepts.yml` cross-cutting concept registry with 13 machine-checkable invariants
- `scripts/verify_concepts.py` runner + `scripts/invariant_types.py` (7 invariant types, 6 source types, stdlib + PyYAML only)
- `.pre-commit-config.yaml` wiring `verify_concepts.py` to every commit via the pre-commit framework
- `docs/ARCHITECTURE.md` rewritten as ground truth from reverse-engineered source (replaces the stale 18-tools doc)
- `CLAUDE.md` rule 15 pointing future sessions at `.concepts.yml` before cross-cutting edits
- GLM-4.7 Flash documented in backend table (was implemented but undocumented)

### Changed
- README MCP-tools section updated from 18 to 26 tools (the 8 missing ones now listed: `collect_media_paths`, `create_sequence`, `get_source_path`, `get_write_node_settings`, `operation_history`, `rename_segments`, `resolve_concept`, `undo_last_operation`)
- README model selector table rewritten to match `AVAILABLE_MODELS` (removed non-existent `qwen3-coder`, `qwen2.5-coder`, Sonnet 4.5, Haiku 4.5; added GLM-4.7 Flash)
- README knowledge-base table: 7 → 14 documents, chunk counts aligned with actual `rag/corpus.json` (783)
- `hooks/flame_mcp_bridge.py`: Claude Opus 4.6 → 4.7 in `AVAILABLE_MODELS`
- `src/flame_mcp/server.py`: `WRITE_ALLOWED_MODELS` — dropped `claude-opus-4-5`, added `claude-opus-4-7`, kept forward-compatible prefixes
- `src/flame_mcp/server.py::_rating()` returns empty string for Ollama backends (token-cost warnings suppressed, matching README claim)
- `pyproject.toml` version bump 0.1.0 → 1.3.0 (catch-up release including all commits since v1.2.1)
- `install.sh` Ollama server prompts now reference `qwen3.5-mcp` and `glm-4.7-flash` instead of stale `qwen3-coder` / `qwen2.5-coder`
- `scripts/setup_ollama_linux.sh` (renamed from `setup_linux.sh`; moved to `scripts/`) VRAM tiering updated to current `AVAILABLE_MODELS`
- Modelfile setup simplified: `ollama cp qwen3.5:9b qwen3.5-mcp` instead of referencing a non-existent `Modelfile.qwen35mcp` file
- `CLAUDE.md`: retired unbacked `"think": false` claim; Modelfile section aligned with the runtime-preflight reality

### Removed
- Reference to `Modelfile.qwen35mcp` (file never existed in the repo; bridge handles `num_ctx` at runtime)

### Previously pending
- Stopped tracking `rag/index/` generated files; added `.gitkeep` placeholder
- Fixed stale `python rag/build_index.py` references to `python -m flame_mcp.rag.build_index`

## [1.2.1] - 2026-04-14

### Fixed
- Harden reasoning on Flame panel claude subprocess to prevent bridge crashes

## [1.2.0] - 2026-04-14

### Added
- Index Wiretap CLI (37 tools) and Wiretap SDK Python bindings (22 classes) in RAG

## [1.1.2] - 2026-04-14

### Fixed
- Align `INDEX_DIR` and `CORPUS_PATH` with real on-disk data layout
- Make `test_cli_not_found` deterministic by mocking `subprocess.run`

### Changed
- Rebuild RAG index after adding auto-learned sequence-from-reel pattern

## [1.1.1] - 2026-04-10

### Added
- Migrate tool pre-approval to user-level `~/.claude/settings.json` (auto-detected via `ast.parse`)

### Fixed
- Update maya-mcp entry from `core/server.py` to `-m maya_mcp.server`

### Changed
- Clean internal artifacts and translate Spanish content to English

## [1.1.0] - 2026-04-08

### Added
- In-session RAG cache (A12) consistent with maya-mcp and fpt-mcp

### Changed
- **Breaking:** Migrate to `src/flame_mcp/` package layout; extract `safety.py` as separate module
- Update all `flame_mcp_server.py` references to new `src/flame_mcp/` layout

## [1.0.0] - 2026-04-07

### Added
- Automated test suite with 62 tests covering safety, redirect, tools, and RAG
- `MODEL_STRATEGY.md` with Ollama setup, Modelfile, and `KEEP_ALIVE` config
- Ollama as optional prerequisite in README and `install.sh`

### Fixed
- Tighten redirect pattern regexes to avoid false positives

## [0.10.0] - 2026-04-07

### Added
- LLM Strategy v2: Qwen3.5-mcp as primary local model with updated `AVAILABLE_MODELS`
- `.env.example` for ecosystem consistency
- Ecosystem section with cross-repo links in README
- Timing profiling at each pipeline stage boundary (REC-001)
- Log first 200 chars of assistant response in bridge log (REC-002)
- `.mcp.json` so `claude -p` discovers MCP server (OBS-024)
- QA test plans from audit agent (Level 0-1 coverage)
- `NOTICE.md` for third-party license attributions
- Smart method-group chunking in `build_index.py`
- Phase D: YouTube transcript patterns, OCR frames, GitHub pattern fetcher

### Fixed
- Remove all legacy `~/Projects/flame-mcp` hardcoded paths from docs and bridge
- `install.sh` Python 3.11+ discovery on macOS
- Widget cwd resolution and socket path for installed hook
- Dynamic `_PROJECT_ROOT` resolution replacing 11 hardcoded paths
- Suppress structural redirects when creation intent is detected
- Three-level path resolution for project `.cfg` fallback (OBS-028)
- Root cause fixes for systemic tool-selection failure (OBS-011/013)
- Apply all Level 0 and Level 1 QA observations (OBS-002 to OBS-023)
- Remove `husky.py` (Autodesk proprietary)
- Bridge-only redirect via `# DT\n` code prefix (OBS-025)

### Changed
- Rewrite `ARCHITECTURE.md` for v0.9.0 current state
- Rebuild RAG index multiple times with improved chunking (668 chunks)

## [0.9.0] - 2026-03-09

### Added
- Hybrid BM25 + semantic search (C3)
- HyDE query expansion (C4)
- Three-level learning system (C5): trusted models auto-learn, read-only models stage for review
- Mandatory citation rule (C2)

### Changed
- Upgrade embedding model to `bge-large-en-v1.5` (C6)
- Rebuild FLAME_API.md from live Flame introspection (B7)

### Fixed
- Block `PyExporter.export()` deadlock and export hang post-mortem
- Remove personal paths and untrack `crash_recovery.json`

## [0.8.0] - 2026-03-09

### Added
- 18 MCP tools total: log reader (`list_flame_logs`, `read_flame_log`), pagination, timeout param
- `ollama_mac` backend for fully offline local inference
- `/undo` and `/undo N` chat commands for instant Flame undo
- `/wrong` and `/wrong <reason>` chat commands for correction feedback
- Warn bubble type (amber) for `ollama_mac` tool-use limitations
- Runtime config keys (B5) and RAG index validator (B6)
- Self-healing: dedicated tools warn on empty fields and prompt `learn_pattern`

### Fixed
- Model update to Sonnet 4.6 with A4/A9/A13/A14 bug fixes
- Ollama: cap agentic turns, replace `/no_think` prefix with think-block stream filtering
- Crash recovery and bridge connection rule for Ollama
- `config.json` fail-safe JSON reads in all save functions
- `get_project_info`: use `wiretap_get_metadata` XML for accurate frame rate/resolution
- Full audit: `sys` import, desktop clips, `openWorldHint`, Pydantic, `CLAUDE.md`
- Wiretap SDK section added to `FLAME_API.md`
- Crash on `lib.folders` access in `list_libraries`
- Library delete pattern: add `str()` cast and `None` default
- Filter hidden system libraries (`Timeline FX`, `Grabbed References`) from all list tools
- Strip JSON envelope leak from `tool_result` content
- `ollama_cloud`: route through local Ollama server with `:cloud` model tag

### Changed
- Recalibrate token rating thresholds (low<500, medium<2000, high>=2000)
- Suppress token warnings for Ollama backends

## [0.7.0] - 2026-03-06

### Added
- Ollama cloud API key field in the UI
- Editable Ollama server URL field in the chat widget
- Ollama local/cloud backend support in the bridge

### Fixed
- Reduce `num_ctx` 32K to 24K to keep inference on GPU
- Pre-load model via native API to force `num_ctx`
- Correct qwen3-coder model tag references
- Show server/key in combo labels; fix Ollama cloud URL; extend cloud watchdog

## [0.6.0] - 2026-03-06

### Added
- Model selector dropdown in Qt chat widget
- `ping()` tool for bridge connectivity checks
- `list_clips` and `list_desktop_reels` dedicated tools
- Auto-approve all MCP tools in `~/.claude/settings.json` via install.sh

### Fixed
- Track dedicated tool savings; fix `None` attrs; block `.startswith` on `PyAttribute`
- Enforce RAG call before every `execute_python`, no exceptions
- Remove 'when unsure' escape from `search_flame_docs` docstring

### Changed
- Simplify `ARCHITECTURE.md` Mermaid diagram for clean GitHub rendering

## [0.5.0] - 2026-03-06

### Added
- Pre-built RAG index shipped with repo (BAAI/bge-small-en-v1.5)
- Action, Color Management, Conform, Segment and Timeline API reference docs
- Official cookbook and community workflow docs for RAG enrichment
- Knowledge base documentation in README (~340 chunks)

### Fixed
- Add `ROOT` to `sys.path` so `rag.config` imports correctly when run directly

## [0.4.0] - 2026-03-06

### Changed
- Replace `all-MiniLM` with `BAAI/bge-small-en-v1.5` embedding model
- Add vocabulary doc and Ollama embeddings; fix timeline/crash patterns

## [0.1.0] - 2026-03-06

### Added
- Initial release: MCP server with `execute_python` and `search_flame_docs` tools
- Flame Python hook (`flame_mcp_bridge.py`) with Unix socket bridge
- Qt chat widget embedded in Flame
- RAG semantic search over FLAME_API.md
- Safety validator with crash-prevention patterns
- Complete reference documentation (README + PDF guide)

[Unreleased]: https://github.com/abrahamADSK/flame-mcp/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/abrahamADSK/flame-mcp/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.1.2...v1.2.0
[1.1.2]: https://github.com/abrahamADSK/flame-mcp/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/abrahamADSK/flame-mcp/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/abrahamADSK/flame-mcp/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.10.0...v1.0.0
[0.10.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/abrahamADSK/flame-mcp/compare/v0.1.0...v0.4.0
[0.1.0]: https://github.com/abrahamADSK/flame-mcp/releases/tag/v0.1.0
