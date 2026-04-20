# flame-mcp — Architecture (as found in code)

> **Scope.** This document describes the system that actually runs when
> `flame-mcp` is installed. It is the **ground truth** against which README
> marketing copy, CLAUDE.md behavioural rules, and in-code docstrings are
> audited. When this file and code disagree, the code wins and this file
> is the one that needs fixing — track any divergence as a drift entry in
> `.concepts.yml`.
>
> Last authored after the Chat 44 reverse-engineering pass (four read-only
> audit agents). Regenerate whenever `src/flame_mcp/server.py` or
> `hooks/flame_mcp_bridge.py` changes in a structural way (a new tool, a
> different transport, a new backend, a new config key).

---

## 1. Overview

`flame-mcp` is an **MCP server** for Autodesk Flame. It exposes 26 tools
over MCP stdio and implements them by sending Python snippets to a hook
running inside Flame over a local Unix-domain socket (TCP port 4444 as
fallback). A RAG index over the Flame Python API and a suite of curated
`docs/*.md` files is consulted before every freeform code execution to
keep the agent on documented API paths.

## 2. Process model

Two processes cooperate; they share `config.json` on disk but no memory:

```
 +------------------------------+            +------------------------------+
 |  MCP server (this repo)      |            |  Flame (Autodesk binary)     |
 |  .venv/bin/python -m flame_  |  socket    |  Python 3.11.5 embedded      |
 |  mcp.server  (stdio to MCP   | ---------> |  hooks/flame_mcp_bridge.py   |
 |  client: Claude Code,        |  JSONL     |  loaded as a user hook at    |
 |  Desktop, Cowork, etc.)      |            |  /opt/Autodesk/shared/...    |
 +------------------------------+            +------------------------------+
```

- **Entry point**: `[project.scripts] flame-mcp = "flame_mcp.server:main"`.
  Inside the module, `mcp = FastMCP("flame", ...)`; `mcp.run(transport="stdio")`.
  Before run, `_sync_tool_permissions()` AST-parses this very file to register
  tool approvals into `~/.claude/settings.json`.
- **Flame hook**: file at `hooks/flame_mcp_bridge.py`. A symlink at
  `/opt/Autodesk/shared/python/flame_mcp_bridge.py` (created once by
  `install.sh`) lets every `git pull` deploy updates without copying.
  Flame calls the hook's `app_initialized(project_name)` callback on
  startup, which starts a socket server in a daemon thread.

## 3. Transport

- **Unix domain socket** at `<repo>/run/flame_mcp.sock` (or
  `/tmp/flame_mcp.sock` when the repo path is not resolvable inside Flame).
  Override with `FLAME_BRIDGE_SOCKET` env var.
- **TCP port 4444** is the fallback when `AF_UNIX` is unavailable. Override
  with `FLAME_BRIDGE_PORT`. In practice macOS always has `AF_UNIX` and the
  TCP path is exercised only on exotic platforms.
- **Wire format**: one JSON object per line. Client -> bridge:
  `{"code": "<python>"}` (optionally prefixed with `# DT\n` to mark the
  call as originating from a dedicated tool and skip the bridge-side
  redirect safety check). Bridge -> client:
  `{"status": "success"|"error", "output": "...", "return_value": "..."}`.

## 4. Module layout

```
src/flame_mcp/
├── server.py              <- MCP entry; 26 @mcp.tool decorators; socket client
├── safety.py              <- _DANGEROUS_PATTERNS, _REDIRECT_PATTERNS
├── journal.py             <- Journal + UndoCodeGenerator (operation history)
├── concept_map.py         <- static user-intent -> API resolver (resolve_concept)
└── rag/
    ├── build_index.py     <- corpus chunking + ChromaDB build + BM25 prep
    ├── search.py          <- hybrid BM25 + semantic via RRF; HyDE query expansion
    ├── config.py          <- EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
    └── validate_index.py  <- smoke tests for the built index

hooks/
└── flame_mcp_bridge.py    <- Flame-side socket server + Qt chat widget + LLM
                             backend selection (model combo, preflight num_ctx)

rag/
├── corpus.json            <- 783 chunks extracted from FLAME_API.md + docs/*.md
└── index/                 <- ChromaDB persistent store (gitignored)
```

No circular imports.

## 5. Runtime flow — `list_libraries()` end-to-end

1. Claude Code (stdio) calls the `list_libraries` MCP tool.
2. `server.py::list_libraries()` (around line 876) builds a hardcoded Python
   snippet and calls `_call_flame(code, dedicated_tool=True)`.
3. `_call_flame` prepends `# DT\n` so the bridge recognises it as trusted
   and skips the redirect-pattern safety check.
4. The server connects to the Unix socket (or TCP 4444 fallback) and writes
   the JSON line.
5. Bridge `_handle_connection()` reads the line, detects `# DT`, strips it,
   and executes the payload in Flame's embedded Python (`exec()` inside a
   sandbox that exposes `flame`, `cmds`, `json`, etc.).
6. The return value is JSON-marshalled and written back on the same socket.
7. `_call_flame` returns the dict; `_fmt()` formats it and appends
   `_stats_footer()` (token counters, RAG savings, call count). `_rating()`
   skips the 🟡/🔴 icons when the current backend starts with `ollama`.
8. Claude Code receives the MCP tool output.

## 6. RAG subsystem

- **Build time** (`rag/build_index.py`): reads 14 documents listed in the
  README "Knowledge base" table + `FLAME_API.md`. Splits into chunks at
  semantic sentence boundaries, embeds with
  `BAAI/bge-large-en-v1.5`, and writes both a BM25 index and a ChromaDB
  persistent store at `rag/index/`.
- **Search time** (`rag/search.py`): hybrid retrieval — BM25 (exact method
  names) + semantic (synonyms) combined via Reciprocal Rank Fusion. A HyDE
  query expansion wraps the query in a Flame-code template before embedding
  to improve recall on natural-language questions.
- **Score**: 0–100. Tools record `_last_rag_score` to gate `execute_python`
  (see §7 "RAG gate"). Below the threshold (default 60, configurable via
  `config.json -> rag_fallback_threshold`) the server warns the user that
  the code may be undocumented.
- **Self-healing**: after a successful `execute_python` whose preceding
  `search_flame_docs` scored below threshold, if the active model is in
  `WRITE_ALLOWED_MODELS` (Sonnet/Opus substring match), `learn_pattern()`
  appends the code pattern to `FLAME_API.md` and rebuilds the index. For
  read-only models the pattern is staged in `rag/candidates.json` instead.

## 7. Safety & redirect enforcement

- **`_DANGEROUS_PATTERNS`** (`safety.py`): regexes that flag destructive or
  system-level operations; matched at both server entry and bridge entry
  so the bridge is never trusted alone.
- **`_REDIRECT_PATTERNS`** (`safety.py`): patterns that indicate the LLM
  should have used a dedicated tool (e.g. listing libraries via raw code
  instead of `list_libraries()`). Bridge writes mismatches to
  `/tmp/flame_mcp_redirect.log` and rejects the call unless the code carries
  the `# DT` marker.
- **RAG gate** (`server.py::execute_python`): if the most recent
  `search_flame_docs` score is `< rag_fallback_threshold`, `execute_python`
  refuses to run and returns a structured error that prompts the LLM to
  consult more specific docs first. Tracked by `_OBS_013`.
- **Dry run**: `execute_python(dry_run=True)` runs the safety checks and
  returns the report without executing.

## 8. LLM backend selection (lives in the hook, not the server)

- **`AVAILABLE_MODELS`** (`hooks/flame_mcp_bridge.py`) is a list of
  `(display_name, model_id, backend)` tuples. Current entries:
  `claude-sonnet-4-6`, `claude-opus-4-7` (anthropic); `qwen3.5-mcp`,
  `glm-4.7-flash` (ollama, LAN GPU); `qwen3.5-mcp`, `qwen3.5:4b` (ollama_mac,
  local CPU/MPS).
- **Widget**: a Qt combo box in the Flame panel selects the active entry.
  The selection is persisted in `config.json -> model` + `config.json -> backend`.
- **Backend environments** (`_get_ollama_env`, lines ~1483–1514):
  - `anthropic`: reads `ANTHROPIC_API_KEY` from the environment.
  - `ollama`: sets `ANTHROPIC_BASE_URL` to `config.json -> ollama_url` and
    stubs `ANTHROPIC_API_KEY = "ollama"`.
  - `ollama_mac` / `ollama_cloud`: same as `ollama` but with
    `ANTHROPIC_BASE_URL = "http://localhost:11434"`.
- **Context-window preflight**: before the `claude` subprocess runs against
  an Ollama backend, the hook POSTs `{"options": {"num_ctx": 24576}}` to
  `/api/generate` with an empty prompt. This forces Ollama to load the
  model with the full context window; without it, Ollama's
  Anthropic-compat `/v1/messages` endpoint defaults to 4096 and ignores
  any `num_ctx` declared in the Modelfile. The preflight runs for the
  `ollama` backend only — `ollama_mac` and `ollama_cloud` currently do
  NOT get it (see §11).
- **Subprocess launch**: `_agent_loop` spawns `claude -p --output-format
  stream-json` with the backend-specific env, then streams stdout/stderr
  to the Qt chat widget.

## 9. Configuration precedence

MCP server (`server.py::_get_config`):
1. `config.json` at the repo root.
2. Silent empty dict on read error (graceful degradation).

Keys: `rag_fallback_threshold` (default 60), `fallback_model`
(default `"Sonnet"`), `write_allowed_models` (overrides
`WRITE_ALLOWED_MODELS` when non-empty).

Bridge (`flame_mcp_bridge.py::_load_model_config`):
1. Same `config.json`.
2. Hardcoded defaults: `DEFAULT_MODEL = "claude-sonnet-4-6"`,
   `DEFAULT_BACKEND = "anthropic"`,
   `DEFAULT_OLLAMA_URL = "http://localhost:11434"`.

Keys: `model`, `backend`, `ollama_url`, `ollama_cloud_key`.

Socket transport overrides (both processes):
1. Env var: `FLAME_BRIDGE_SOCKET`, `FLAME_BRIDGE_PORT`.
2. Repo-relative path (if detectable).
3. `/tmp` / TCP fallback.

Model selection has **no** env var override — this asymmetry with transport
is undocumented user-facing but is a known trait of the code (see §11).

## 10. Logging & telemetry

- `_stats` dict (`server.py`, ~line 117): exec calls, tokens in/out,
  tokens saved by RAG, tokens saved by dedicated tools, patterns learned.
  Token counts are character-count estimates (`len(text) // 3`), not real
  Anthropic API counters.
- `_stats_footer()` appends the stats to every tool response; `_rating()`
  adds 🟢/🟡/🔴 badges **only for Anthropic backends** — Ollama is suppressed
  (implemented in Chat 44 to match the long-standing README claim).
- `logs/flame_rag.log` (search queries and scores), `logs/flame_mcp_bridge.log`
  (bridge events, model changes, preflight results), `logs/crash_recovery.json`
  (last `execute_python` snapshot for post-crash diagnostics, 24 h TTL).
- `session_stats()` tool exposes the counters to the LLM for
  self-diagnosis. Stats are **process-global** and are NOT reset when a
  Claude session ends — they accumulate until the MCP server restarts.

## 11. Known architectural smells (carry-forward from Chat 44 audit)

The following are documented, not fixed. They are not bugs per se —
several are deliberate trade-offs — but fresh Claude sessions should know
about them before "fixing" something that looks off.

- **Silent failure when the RAG index is missing.** `search.py` returns
  `None` and logs only to file; the caller degrades gracefully but the
  user never sees the error.
- **`_load_model_config` is duplicated** across the server and the bridge
  with identical logic but different implementations (process boundary —
  no shared module to import from).
- **Env-var vs config.json asymmetry**: transport settings are env-first,
  model settings are config-first. Undocumented in user-facing README.
- **Backend-specific timeouts are hardcoded** (600 s for `ollama`, 300 s
  for `ollama_cloud`) with no config override.
- **Crash-recovery TTL of 24 h is hardcoded** (`crash_recovery.json`).
- **`_stats` is session-global** and never reset — cumulative across every
  Claude session until the MCP server process dies.
- **`ollama_mac` skips the num_ctx preflight** that the `ollama` backend
  gets. In practice Mac users may see responses truncated at 4096 tokens
  silently. Not promoted to a bug because no complaint has been filed
  yet (pending targeted Mac-local benchmarking).

## 12. References

- `.concepts.yml` — declarative registry of cross-cutting concepts + invariants.
- `scripts/verify_concepts.py` — runs the invariants on every commit.
- `.pre-commit-config.yaml` — wires the verify script to git.
- `~/Projects/.external_versions.yml` — Anthropic / Ollama / Autodesk /
  ShotGrid review-expiry state.
- `CLAUDE.md` — behavioural rules for Claude sessions operating on the repo.
- `FLAME_API.md` — canonical Flame Python API cheatsheet (auto-extended by
  `learn_pattern`).
