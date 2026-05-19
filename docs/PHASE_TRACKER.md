# PHASE_TRACKER.md

Mirror of the Chat 51 performance + reliability roadmap. Updated atomically when a phase changes state.
Source-of-truth = open GitHub Issues/PRs; this file is a navigation aid for single-glance overview without
GitHub navigation. See [`docs/CHAT_51_PLAN.md`](./CHAT_51_PLAN.md) for full plan rationale.

## Summary

```
phases_total:    11
phases_done:     10   (F0, F1a, F1b, F2-intro, F2-wt, F3a, F3b, F4a, F4b, F6a)
phases_pending:   1   (F5b)
open_prs:         0
prs_merged:      10   (#3 F0, #4 F1a, #5 F1b, #6 F2-intro, #7 F2-wt, #8 F3b, #15 F3a, #16 F4a, #17 F4b, #18 F6a)
open_issues:     1    (#12 F5b)
last_updated:     2026-05-19
post_merge:       main at F6a; tests 491 passed / 113 skipped; invariants 33/33
```

## Status table

| Phase | Title | Status | PR / Issue | Depends on | Notes |
|-------|-------|--------|------------|------------|-------|
| F0 | Baseline telemetry — JSONL + p_fallo counters | ✅ Merged | [PR #3](https://github.com/abrahamADSK/flame-mcp/pull/3) | — | Merged 2026-05-18 → main |
| F1a | `_stats_footer` modes — default minimal (AJUSTE 4) | ✅ Merged | [PR #4](https://github.com/abrahamADSK/flame-mcp/pull/4) | F0 ✓ | Merged 2026-05-18 → main |
| F1b | Ollama `keep_alive` 10m→30m + config knob | ✅ Merged | [PR #5](https://github.com/abrahamADSK/flame-mcp/pull/5) | F0 ✓ | Merged 2026-05-18 → main (rebased over F1a; config.example.json conflict resolved) |
| F2-intro | `introspect_flame_api.py` → `rag/api_graph.json` | ✅ Merged | [PR #6](https://github.com/abrahamADSK/flame-mcp/pull/6) | F0 ✓ | Merged 2026-05-18 → main; unlocks F3a/F4b/F5b |
| F2-wt | Wiretap CLI + SDK smoke harness | ✅ Merged | [PR #7](https://github.com/abrahamADSK/flame-mcp/pull/7) | F0 ✓ | Merged 2026-05-18 → main |
| F3a | concept_map bypass via api_graph.json | ✅ Merged | [PR #15](https://github.com/abrahamADSK/flame-mcp/pull/15) | F2-intro ✓ | Merged 2026-05-18 → main; closes #9; dual-source chain `concept_map → graph → none`, trap-flagged entries refused |
| F3b | Golden routing dataset + adversarial gate | ✅ Merged | [PR #8](https://github.com/abrahamADSK/flame-mcp/pull/8) | F0 ✓ | Merged 2026-05-18 → main; **unblocks F6a** |
| F4a | Workspace snapshot TTL 12s + write-invalidation (AJUSTE 2) | ✅ Merged | [PR #16](https://github.com/abrahamADSK/flame-mcp/pull/16) | F0 ✓ | Merged 2026-05-18 → main; closes #10; 7 RO tools cached, execute_python invalidates after every exec |
| F4b | AST dry-run walker | ✅ Merged | [PR #17](https://github.com/abrahamADSK/flame-mcp/pull/17) | F2-intro ✓ | Merged 2026-05-19 → main; closes #11; rejects hallucinated `flame.X.Y` before bridge round-trip |
| F5b | Ruta A — structured plan output (AJUSTE 1) | ⏳ Pending | [Issue #12](https://github.com/abrahamADSK/flame-mcp/issues/12) | F2-intro ✓ | Not started — deepest architectural change; LLM stops writing raw Python |
| F6a | Trim CLAUDE.md (AJUSTE 3) | ✅ Merged | [PR #18](https://github.com/abrahamADSK/flame-mcp/pull/18) | F3b ✓ | Merged 2026-05-19 → main; closes #13; 359→290 lines, ~1200 tokens/turn saved |

**Legend:** ✅ Merged (in main) · ✅ Done (on branch, MERGEABLE) · ⏳ Pending · 🔒 Blocked

## Update protocol

Keep this file fresh by following these rules. The file is committed atomically with the change that
triggers the update (per global CLAUDE.md "code + docs same commit" rule).

- **PR merges** → flip its phase row from `✅ Done` (on branch) to `✅ Done` (merged), update the summary
  `prs_merged` count, and decrement `open_prs`.
- **Issue closes** (phase implemented and PR opened) → flip its row from `⏳ Pending` to `✅ Done`, link
  the new PR instead of the issue, decrement `open_issues`, increment `open_prs` and `phases_done`,
  decrement `phases_pending`.
- **New phase appears** → add a row, update `phases_total` and the relevant pending/done counters.
- **Phase cancelled** → strike-through the title in the row, move it to a `## Cancelled` subsection at the
  bottom of the file with a one-line reason, decrement `phases_total` (or keep it and flag separately —
  pick one convention and stick to it).
- **Dependency unblocked** → update the `Notes` column of the now-unblocked row (e.g. `**Unblocked**`).
- Always update `last_updated` to today's date in `YYYY-MM-DD` format.

## Cancelled

_(none)_
