# Chat 51 — Performance + Reliability Plan (v2)

**Status as of 2026-05-18:** 6 of 11 phases delivered (all on feature branches, 6 open PRs MERGEABLE / CI green), 5 phases pending.

This document was reconstructed in Chat 51 from the open PRs (#3–#8) and their commit messages after the original `/ultraplan` output was lost (the session that generated it was never handed off via `/mcp-handoff`). It is now the source-of-truth for the roadmap.

---

## Goal & metric

Cut **both** latency and routing reliability at once. The metric to minimise is **expected latency**, not raw nominal latency:

```
latency_expected = nominal × (1 − p_fallo) + (nominal + 5–8 s) × p_fallo
```

Where:
- `nominal` is the median bridge+model time for a successful turn.
- `p_fallo` is the empirical fraction of turns that retry/fail (Flame crash recovery, wrong API path, hallucinated symbol, etc.).
- The `+5–8 s` penalty captures the cost of a failed turn the user can perceive (rollback, retry, follow-up clarification).

A 30 % nominal-latency cut is wiped out by a 5-point `p_fallo` regression, so every phase is judged on whether it improves *both* axes — or at least is strictly Pareto on one and neutral on the other.

---

## v2 — the four AJUSTES

The plan was revised once in Claude Code review. The four ajustes are load-bearing:

| # | Affected phase | Decision |
|---|---|---|
| **AJUSTE 1** | **F5b** | Use **Ruta A** (structured plan output schema) instead of constraining the LLM to a Python grammar. The model proposes a structured plan, the server validates and executes — the LLM never writes raw Python. |
| **AJUSTE 2** | **F4a** | Workspace snapshot caches `current_workspace` state with **TTL 12 s + invalidation on writes**. Avoids re-walking the entire workspace tree on every routing decision. |
| **AJUSTE 3** | **F6a** | The CLAUDE.md trim is **BLOCKED** until the golden dataset (F3b) has ≥10 adversarial entries with non-empty `must_not_contain`. Without this gate, trimming could silently erase an API trap warning. |
| **AJUSTE 4** | **F1a** | `_stats_footer` defaults to **`minimal`** mode (was: remove entirely). Operators can flip to `full` via `config.json -> stats_footer_mode` for diagnostics. Strictly Pareto: fewer tokens per turn, no information loss. |

---

## Phase table

| Phase | What | Status | PR | Depends on | Unblocks |
|---|---|---|---|---|---|
| **F0** | Baseline telemetry — persistent JSONL + `p_fallo` counters | ✅ Done | [#3](https://github.com/abrahamADSK/flame-mcp/pull/3) | — | F1a, F1b, F2-intro, F2-wt, F3b |
| **F1a** | `_stats_footer` modes (none/minimal/full), default `minimal` | ✅ Done | [#4](https://github.com/abrahamADSK/flame-mcp/pull/4) | F0 | — |
| **F1b** | Ollama `keep_alive` bump 10 m → 30 m + config knob | ✅ Done | [#5](https://github.com/abrahamADSK/flame-mcp/pull/5) | F0 | — |
| **F2-intro** | `introspect_flame_api.py` → `rag/api_graph.json` | ✅ Done | [#6](https://github.com/abrahamADSK/flame-mcp/pull/6) | F0 | F3a, F4b, F5b |
| **F2-wt** | Wiretap CLI + SDK smoke harness (37 tools, behaviour evidence) | ✅ Done | [#7](https://github.com/abrahamADSK/flame-mcp/pull/7) | F0 | — |
| **F3a** | `concept_map` bypass — route directly off `api_graph.json` | ❌ Pending | — | F2-intro | — |
| **F3b** | Golden routing dataset (83 queries, 16 adversarial) + pre-commit gate | ✅ Done | [#8](https://github.com/abrahamADSK/flame-mcp/pull/8) | F0 | **F6a** |
| **F4a** | Workspace snapshot — TTL 12 s + invalidation on writes (AJUSTE 2) | ❌ Pending | — | F0 | — |
| **F4b** | AST dry-run walker | ❌ Pending | — | F2-intro | — |
| **F5b** | Ruta A — structured plan output schema (AJUSTE 1) | ❌ Pending | — | F2-intro | — |
| **F6a** | Trim CLAUDE.md (AJUSTE 3 — unblocked once F3b ✓ ≥10 adversariales) | ❌ Pending, **UNBLOCKED** | — | F3b ✓ | — |

---

## Done — phase details

### F0 — Baseline telemetry — [PR #3](https://github.com/abrahamADSK/flame-mcp/pull/3)

**What**: Persistent JSONL telemetry (`logs/timings.jsonl`, `logs/turns.jsonl`) + new counters `turns_total`/`failed_turns` so `p_fallo = failed_turns/turns_total`.

**Why**: Every later phase claims a `nominal` or `p_fallo` improvement. Without a cross-session baseline those claims are unverifiable.

**Files**: `src/flame_mcp/_session_stats.py` (helpers), `src/flame_mcp/server.py` (`_track_timing` enrichment + `execute_python` counter bumps), `hooks/flame_mcp_bridge.py` (`_agent_loop` per-turn append from outer `finally`, captures timeouts), `.gitignore` (`*.jsonl`, `*.jsonl.1`), `tests/test_session_stats.py` (+9 cases).

**Acceptance**: 209/209 tests pass, 20/20 invariants, 10–20-turn Flame session produces ≥10 lines in `timings.jsonl` and one row per turn in `turns.jsonl`. `p_fallo` computable via `jq '.failed_turns / .turns_total' < session_stats.json`.

### F1a — `_stats_footer` modes — [PR #4](https://github.com/abrahamADSK/flame-mcp/pull/4)

**What**: `_stats_footer(mode=None)` reads `config.json -> stats_footer_mode` (default `minimal`). Modes: `none`/`minimal`/`full`. `minimal` returns `""` (per-call timing already lives in the `execute_python` preamble). `full` restores the historical multi-line aggregate.

**Why**: The footer was prepending ~80–150 tokens to every tool result, inflating the next turn's prefill 1:1. Strictly Pareto.

**Files**: `src/flame_mcp/server.py` (`_stats_footer` signature change), `config.example.json` (declares the knob), `tests/test_session_stats.py` (+6 cases, total 27/27).

**Token impact**: −80…−150 tokens per LLM turn that uses `execute_python` or `search_flame_docs`. `session_stats()` is unaffected (builds its own block).

### F1b — Ollama `keep_alive` 30 m + config knob — [PR #5](https://github.com/abrahamADSK/flame-mcp/pull/5)

**What**: Bump default `keep_alive` 10 m → 30 m and expose as `ollama_keep_alive` config knob. Accepts duration string (`"30m"`/`"1h"`) or int seconds.

**Why**: 10 minutes is shorter than a typical reading-and-thinking gap between turns. After >10 min idle the next turn paid a cold-load penalty (5–30 s on a 9B model) the user blamed on model speed.

**Files**: `src/flame_mcp/_config.py` (new `resolve_keep_alive` helper, type-guard rejects dict/list/None/bool), `hooks/flame_mcp_bridge.py` (`_preload_ollama_model` delegation + inline fallback per chat-44 helper-extraction pattern), `config.example.json`, `tests/test_config.py` (+9 cases, 19/19 / 219/219 full suite).

### F2-intro — `introspect_flame_api.py` — [PR #6](https://github.com/abrahamADSK/flame-mcp/pull/6)

**What**: `scripts/introspect_flame_api.py` walks Flame's `flame` Python module and emits a structured JSON (`rag/api_graph.json`) describing module-level attributes, free functions, and classes (with methods + attrs).

**Why**: Becomes the runtime source-of-truth consumed by **F3a** (concept_map bypass), **F4b** (AST dry-run walker), and **F5b** (structured plan output schema). Replaces hand-curated guess-work with introspected ground truth.

**Operational notes**:
- Cannot run in CI; `flame` is only importable inside Flame's embedded Python or via the flame-mcp `execute_python` bridge.
- `--check` exits 2 with a clear "REQUIRES FLAME OPEN" sentinel when run on a system Python.
- Best-effort: every step wrapped in try/except — partial graph beats crash.
- **Cadence**: re-run once per Flame major release (2026.x → 2027.x) and commit the regenerated `rag/api_graph.json` with the version bump.

**Files**: `scripts/introspect_flame_api.py`, `tests/test_introspect_flame_api.py` (3 cases — "no flame module" branch + JSON shape against stub).

### F2-wt — Wiretap smoke harness — [PR #7](https://github.com/abrahamADSK/flame-mcp/pull/7)

**What**: Two scripts that produce behaviour evidence for the 37-tool Wiretap CLI and the Python SDK (signature ≠ behaviour).

- `scripts/wiretap_smoke.sh`: iterates over CLI tools listed in `docs/wiretap_cli_reference.md`, default `--help`, hard skip for 5 destructive tools, wraps every call in `timeout 5s`, captures exit + first 5 lines stdout/stderr + ms, emits markdown to `docs/wiretap_smoke_report.md`. bash 3.2-clean, shellcheck-clean.
- `scripts/wiretap_sdk_smoke.py`: adds Flame embedded site-packages to `sys.path`, imports `libwiretapPythonClientAPI`, runs `WireTapClientInit → ServerHandle → NodeHandle('/') → getNumChildren → WireTapClientUninit`. Emits structured JSON to stdout + human trace to stderr. Detects missing SDK, exit 2.
- `docs/wiretap_smoke_report.md`: scaffold with empty/pending rows for 37 tools + 5-row sample paste from a dev-box run.

### F3b — Golden routing dataset + adversarial gate — [PR #8](https://github.com/abrahamADSK/flame-mcp/pull/8)

**What**: 83 curated golden queries (16 adversarial, 48 happy-path, 14 Spanish fall-through) covering 9 categories. Hermetic pytest runner (mocks `flame_mcp.rag.search.search`, uses `resolve_concept` directly). Pre-commit gate `scripts/check_adversarial_count.py` (exit 0 iff ≥10 adversarial with non-empty `must_not_contain`).

**Why**: F6a (CLAUDE.md trim) was BLOCKED until ≥10 adversarial entries existed. Without the gate, a trim could silently erase an API trap warning the LLM relies on.

**Files**: `tests/golden/flame_queries.jsonl`, `tests/test_golden.py`, `scripts/check_adversarial_count.py`.

**Adversarial coverage** (the 16 most common Flame LLM hallucinations):
- `flame.selection` (doesn't exist — use `flame.media_panel.selected_entries`)
- `project.libraries` (returns None — use `current_workspace.libraries`)
- `flame.batch.render(...)` without `schedule_idle_event` (crashes Flame)
- `.clear()` on containers (crashes Flame; use `flame.delete(child)` per item)
- `flame.delete(...)` without dry-run inspect first
- Iterating `flame.projects` (crashes — use `list_all_projects`)
- Hidden libraries `Timeline FX` / `Grabbed References` (must be filtered)
- `PyAttribute` direct-string assignment instead of `set` API
- Wiretap-only metadata reads (resolution, frame rate) attempted via Python API
- Name-attribute coercion gotchas

**Key semantic decision** (refined from initial agent draft):
- `must_not_contain` is checked against `api_path` **only**, not `notes`. Rationale: `concept_map.notes` deliberately mention forbidden symbols by name to teach the LLM (e.g. *"flame.selection does NOT exist"*); including notes in the guardrail false-positives every adversarial.
- `must_contain` reads both `api_path` + `notes` via the separate `_routing_grounding` helper, so the asymmetry is explicit.

**Known limits** (documented for downstream phases):
- Spanish fall-through (14 entries → `None`): `concept_map` is English-keyed. Translation/multi-language synonyms would close it. Not in F3b scope.
- `must_not_contain` is substring-based; over-broad substrings false-positive (ADV003 was the lesson). Future enhancement: `must_not_match` with regex.

**Result**: 428/428 full-suite tests pass, 16 adversarial / 10 required ✓ → **F6a unblocked**.

---

## Pending — phase details

### F3a — `concept_map` bypass (depends on F2-intro)

**What**: Route directly off the introspected `rag/api_graph.json` for symbols that are unambiguous, falling back to `concept_map` only when the graph has no answer. The concept map remains the source for LLM-facing safety notes ("does NOT exist", "crashes Flame").

**Why**: `concept_map` requires hand-curation per concept; `api_graph.json` is regenerated from Flame itself. Anything the graph can answer authoritatively shouldn't require a concept-map entry.

**Acceptance criteria** (proposed):
- New `_route_from_graph(query)` helper in `src/flame_mcp/rag/search.py` (or analogous) returning an `api_path` + provenance tag `graph` / `concept_map` / `none`.
- Golden dataset (F3b) re-run after the bypass — happy-path entries that previously hit `concept_map` should now hit `graph` with the same `expected_tool` resolution.
- All 16 adversarial entries still fail with the documented `must_not_contain` — `api_graph.json` must not surface forbidden symbols (i.e., the introspector should not expose them, or the bypass must filter them; decision deferred to implementation).

### F4a — Workspace snapshot — TTL 12 s + invalidation on writes (AJUSTE 2)

**What**: In-memory cache of `current_workspace` state with TTL 12 s. Any write tool (`flame.delete`, library/clip creation, name changes, etc.) invalidates the snapshot synchronously.

**Why**: Re-walking the workspace tree on every routing decision is expensive on large projects. 12 s is short enough that the user perceives the state as live; invalidation-on-write guarantees we never serve a state that we just contradicted.

**Acceptance criteria** (proposed):
- New `src/flame_mcp/_workspace_snapshot.py` with `get_snapshot()` (TTL-checked) and `invalidate()`.
- Every write path in `server.py` calls `invalidate()` before returning.
- Test suite: TTL expiry, hit/miss, invalidation on each write tool.
- Latency probe: `read_workspace` (or equivalent) median latency must drop measurably; capture via the F0 telemetry.

### F4b — AST dry-run walker (depends on F2-intro)

**What**: Static analysis pass over generated Python (when applicable to the new F5b plan output) that walks the AST and validates every `flame.<symbol>` against `rag/api_graph.json` before `execute_python` ever runs it.

**Why**: Catches the entire class of "hallucinated symbol that crashes Flame" before it reaches the bridge — cheaper than a Flame crash + recovery cycle. Pairs with the F3b adversarial set as a defense-in-depth layer.

**Acceptance criteria** (proposed):
- New `scripts/dry_run_ast.py` or `src/flame_mcp/_ast_validate.py` taking Python source + `api_graph.json` path → list of unresolved symbols.
- Wired into `execute_python` as an opt-in pre-flight (config knob `ast_dry_run: true`, default true).
- Test suite covers each adversarial entry from F3b — the walker should reject all 16 before they reach Flame.

### F5b — Ruta A: structured plan output (AJUSTE 1) (depends on F2-intro)

**What**: The LLM proposes a structured plan (JSON schema) instead of writing raw Python. The server validates the plan against `api_graph.json`, dispatches each step, and returns the result.

**Why**: The LLM never writes Python = cannot hallucinate Python. The plan schema constrains the model to operations the server can actually perform. Latency win: shorter LLM output (structured vs free-form) and shorter server-side validation than parsing Python.

**Acceptance criteria** (proposed):
- Plan JSON schema versioned in `src/flame_mcp/_plan_schema.py` (or `docs/plan_schema_v1.json`).
- `execute_python` gains a sibling `execute_plan` tool that takes the structured form.
- Each plan op maps 1:1 to an `api_graph.json` entry.
- F3b golden re-run: a majority of happy-path entries should be expressible as a plan; failures define the v1 schema gaps.

### F6a — Trim CLAUDE.md (AJUSTE 3, NOW UNBLOCKED)

**What**: Remove the verbose API-warning sections from `CLAUDE.md` now that the F3b adversarial set captures the same traps as test guarantees.

**Why**: Every chat prefill carries the entire `CLAUDE.md`. The verbose warnings are there because the LLM hallucinates without them — but F3b now enforces the same constraints as failing tests, so the warnings become belt-and-suspenders cost.

**Acceptance criteria**:
- `python scripts/check_adversarial_count.py` returns exit 0 (currently passes: 16 ≥ 10). ✓
- Run trim. Re-run F3b golden suite — all 16 adversarial entries must still fail with `must_not_contain` (proves the trap is captured by the test, not the prompt).
- If any adversarial passes (i.e. the LLM doesn't hallucinate it without the prompt warning), it must NOT be trimmed from `CLAUDE.md` — those warnings are still load-bearing.
- Token reduction in `CLAUDE.md` measured and reported.

---

## Recovery note

This document was reconstructed in **Chat 51 (2026-05-18)** from:
- The 6 open PR descriptions (#3, #4, #5, #6, #7, #8 on `abrahamADSK/flame-mcp`).
- The commit message bodies on the corresponding feature branches.

The original `/ultraplan` v2 output was lost because the session that generated it (~2026-05-13/14) was never closed with `/mcp-handoff`. `MILESTONES.md` and `MASTER_HISTORY.md` consequently jump from Chat 50 (2026-04-29) directly to Chat 51 with no record of the 13–14 May implementation work.

**Lesson** (to be captured in feedback memory): when a `/ultraplan` session ends, persist the plan output to a versioned doc in the relevant repo BEFORE `/clear` or session close. Ephemeral plan output + un-handoff'd session = roadmap loss.

---

## Status header — keep updated

```
phases_total:    11
phases_done:      6   (F0, F1a, F1b, F2-intro, F2-wt, F3b)
phases_pending:   5   (F3a, F4a, F4b, F5b, F6a — F6a unblocked)
open_prs:         6   (#3, #4, #5, #6, #7, #8 — all MERGEABLE, CI green)
prs_merged:       0
last_updated:     2026-05-18
```
