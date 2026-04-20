# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `scripts/cut-release.sh` — ecosystem-shared release orchestrator. Validates
  clean tree + semver arg + non-empty `[Unreleased]`, edits CHANGELOG +
  pyproject.toml, commits with `CUT_RELEASE_VERSION=X.Y.Z` so the
  `changelog_tag_sync` invariant tolerates the transient pre-commit drift,
  then tags, pushes, and creates a GitHub release with the CHANGELOG
  section as notes. Ships with `--dry-run` for safe previews. Byte-identical
  across the 4 MCP-ecosystem repos; canonical at
  `~/Projects/cut-release-canonical.sh`. Resolves the Chat 45 P1 release-flow
  tension that was blocking the ecosystem-wide `strict: true` flip.
- `scripts/invariant_types.py` — new `changelog_tag_sync` handler replaces
  the previous `subset`-based `changelog_tag_coherence` invariant. Adds
  release-in-progress tolerance anchored to env `CUT_RELEASE_VERSION` (set
  by `cut-release.sh` at commit time) OR `pyproject.toml`'s `version`
  field. The tolerance only fires for exactly one drifting version that
  matches the anchor — cannot be forged without bumping the real anchor.

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
