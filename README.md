# flame-mcp

> Control Autodesk Flame with natural language using Claude and the Model Context Protocol (MCP).

> [!WARNING]
> **Experimental project — use at your own risk.**
> This is an independent, unofficial experiment created with [Claude Code](https://claude.com/claude-code). It is **not** affiliated with, endorsed by, or officially supported by Autodesk in any way. The Flame name and trademarks belong to Autodesk, Inc.
>
> Executing AI-generated code inside a live Flame session carries real risks: **unexpected crashes, loss of unsaved work, unintended modifications to projects, sequences, or media.** Always work on a duplicate or test project. Never run this on production material without a full backup. The author(s) accept no responsibility for data loss, corruption, or any other damage resulting from its use.

`flame-mcp` connects [Claude](https://claude.ai) to [Autodesk Flame](https://www.autodesk.com/products/flame) via a lightweight Python bridge. Type what you want to do in plain language — Claude translates it into Flame API calls and executes them live.

```
You: "Delete all reels named TEST from Default Library"
Claude → MCP Server → Unix socket → Flame Python API → Result back to Claude
```

---

## Features

The system has two components:

**`hooks/flame_mcp_bridge.py`** — A Flame Python hook that starts a local Unix domain socket server when Flame launches (falls back to TCP port 4444 if AF_UNIX is unavailable). It receives Python code, executes it inside Flame's Python interpreter with full access to the `flame` module, and returns the result.

**`src/flame_mcp/server.py`** — An MCP server that Claude launches. It exposes tools that Claude can call by name, translates natural language into Python code, and communicates with the bridge over the socket.

```
┌──────────────────┐    MCP (stdio)    ┌──────────────────────┐  Unix socket   ┌─────────────────┐
│  Claude Code /   │ ◄──────────────── │  flame_mcp/server    │ ◄────────────  │  Autodesk Flame │
│  Claude Desktop  │ ─────────────────►│   (Python, macOS)    │ ─────────────► │  Python bridge  │
└──────────────────┘                   └──────────────────────┘  (TCP fallback) └─────────────────┘
```

Compatible with **Claude Code** (terminal), **Claude Desktop**, and **Cowork** — all three contexts use the same MCP server and behave identically.

---

## Requirements

- macOS
- [Autodesk Flame](https://www.autodesk.com/products/flame) 2025 or later
- Python 3.11 or higher (`python3 --version`)
- [Node.js](https://nodejs.org) v22 or higher (required by Claude Code)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) 2.x (`npm install -g @anthropic-ai/claude-code`)
- A Claude account ([claude.ai](https://claude.ai)) — Pro, Max, or API key

**Optional — local / free inference with Ollama:**
- [Ollama](https://ollama.com) >= 0.17.6 installed on your Mac, a Linux GPU server, or both
  - macOS: `brew install ollama && brew services start ollama`
  - Linux: see https://ollama.com/download/linux (systemd)
  - Verify: `ollama --version`
- Create the `qwen3.5-mcp` tag (required — `AVAILABLE_MODELS` in
  `hooks/flame_mcp_bridge.py` expects this exact name):
  ```bash
  ollama pull qwen3.5:9b
  ollama cp qwen3.5:9b qwen3.5-mcp
  ```
  The bridge forces `num_ctx=24576` at runtime via a pre-flight POST to
  Ollama's native `/api/generate` endpoint, so a custom Modelfile with
  `PARAMETER num_ctx` is **not needed** — the Anthropic-compat endpoint
  ignores Modelfile settings anyway. If you want different defaults on
  `num_ctx` for some reason, see the advanced Ollama setup below.
- See [Ollama setup](#ollama-setup-optional) below for backend options

> **Note on Python versions:** The MCP server runs on your system Python (3.11+). Code executed *inside* Flame uses Flame's bundled Python interpreter (Flame 2026 ships Python 3.11.5).

---

## Installation

### Automatic (recommended)

```bash
git clone https://github.com/abrahamADSK/flame-mcp.git  # replace with your fork URL if applicable
cd flame-mcp
chmod +x install.sh
./install.sh
```

The installer will:
1. Create a Python virtual environment
2. Install dependencies (`mcp`, `chromadb`, `sentence-transformers`)
3. Copy the Flame hook to `/opt/Autodesk/shared/python/` (requires `sudo`)
4. Register the MCP server with Claude Code
5. Build the RAG documentation index
6. Generate `.claude/settings.local.json` with all 18 MCP tools allowed

### Verify installation

After installing, run the health check to confirm everything is in place:

```bash
./install.sh --doctor
```

This runs a 5-check sweep (venv, dependencies, hook, Claude registration, RAG index) and prints PASS/FAIL/WARN/SKIP with remediation hints for each check. Recommended before first use.

### Manual

```bash
# 1. Clone and set up
git clone https://github.com/abrahamADSK/flame-mcp.git  # replace with your fork URL if applicable
cd flame-mcp

# 2. Virtual environment + dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt --no-user

# 3. Build the RAG index
python -m flame_mcp.rag.build_index

# 4. Install the Flame hook
sudo cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/

# 5. Register with Claude Code
claude mcp add flame -- "$(pwd)/.venv/bin/python" -m flame_mcp.server

# 6. (Optional) Claude Desktop
#    Copy claude_desktop_config.json to ~/Library/Application Support/Claude/
```

---

## Usage

### 1. Flame menu — MCP Bridge

When Flame starts, the hook registers an **MCP Bridge** submenu in Flame's main menu bar:

```
MCP Bridge  [● Active]
├── Status: ● Active — unix socket  → shows current bridge status
├── Start bridge                   → start Unix socket listener (TCP fallback)
├── Stop bridge                    → stop the listener
├── Restart bridge                 → stop + start
├── Claude Chat  (embedded)        → open Qt chat window inside Flame
├── Launch Claude (terminal)...    → open Claude Code in Terminal.app
├── Reload hook                    → hot-reload the bridge without restarting Flame
├── Connection test                → test TCP round-trip, shows latency
└── View log...                    → open the bridge log file in TextEdit
```

The status indicator updates every time you open the menu:
- `● Active` — bridge is listening, ready to receive commands
- `○ Inactive` — bridge is stopped

### 2. Embedded Claude Chat

**Claude Chat (embedded)** opens a native Qt window directly inside Flame — no terminal required. Type natural language requests and Claude responds, controlling Flame in real time.

- Reads `ANTHROPIC_API_KEY` from environment or `~/flame-mcp/.env`
- Executes Flame code via the Unix socket bridge (thread-safe, non-blocking)
- Uses the local RAG index to look up API patterns before every call
- Requires PySide6 (bundled with Flame 2026+)

#### Chat commands

In addition to natural language, the chat input accepts these special commands:

| Command | Description |
|---------|-------------|
| `/undo` | Undo the last Flame action. Triggers `flame.execute_shortcut("Undo")` directly — bypasses Claude, instant. |
| `/undo N` | Undo the last **N** Flame actions (e.g. `/undo 3`). After each Claude response the chat shows how many actions were performed, so you know the right N. |
| `/wrong` | Tell Claude the last response was incorrect. Injects a correction message into the conversation so Claude re-analyses and tries again without learning the wrong pattern. |
| `/wrong <reason>` | Same as `/wrong` but with context (e.g. `/wrong me diste el desktop en vez de la librería`). Claude uses the reason to understand exactly what to correct. |

> **Tip:** `/undo` and `/wrong` can be combined. If Claude deleted something it shouldn't have, type `/undo N` first to reverse the Flame action, then `/wrong <reason>` so it doesn't repeat the mistake.

**Model selector dropdown** — backends defined in `hooks/flame_mcp_bridge.py :: AVAILABLE_MODELS`, switch without leaving Flame:

<!-- concept:llm_backend_table start -->
| Backend | Models available (model IDs in backticks) | Requires | Works offline? |
|---------|-------------------------------------------|----------|----------------|
| anthropic | Claude Sonnet 4.6 (`claude-sonnet-4-6`), Claude Opus 4.7 (`claude-opus-4-7`) | Anthropic API key | ✗ |
| ollama | Qwen3.5 9B (`qwen3.5-mcp`), GLM-4.7 Flash (`glm-4.7-flash`) | gpu-server on LAN + GPU, LAN reachable at `config.json → ollama_url` | ✗ |
| ollama_mac 🍎 | Qwen3.5 9B (`qwen3.5-mcp`), Qwen3.5 4B (`qwen3.5:4b`) | Ollama on Mac (`brew install ollama`), models pulled locally | ✓ |
<!-- concept:llm_backend_table end -->

Selection is persisted to `~/flame-mcp/config.json` between sessions. The combo label shows the server hostname for `ollama`, or `localhost` for `ollama_mac`. Anthropic model IDs are reviewed every 14 days against the [Anthropic model catalogue](https://docs.anthropic.com/claude/docs/models-overview) via `~/Projects/.external_versions.yml` (enforced by `verify_concepts.py`).

### 3. Claude Code (terminal)

```bash
cd ~/flame-mcp
source .venv/bin/activate
claude
```

Then talk naturally:

```
> List all libraries and reels
> Create a new reel called "MASTER" in Default Library
> Delete all reels named TEST, TEST2 from Default Library
> What's the current project frame rate?
```

---

<!-- concept:mcp_tool_count start -->
## MCP Tools (27)
<!-- concept:mcp_tool_count end -->

<!-- concept:mcp_tool_table start -->
| Tool | Description |
|------|-------------|
| `execute_python` | Execute arbitrary Python code inside Flame with full API access |
| `get_project_info` | Return name, frame rate, resolution, bit depth of the active project |
| `list_libraries` | List all libraries in the project with reel counts |
| `list_reels` | List reels in a library, or across all libraries |
| `list_clips` | List clips in a library/reel, or across all libraries |
| `list_desktop_reels` | List the full desktop structure: reel groups, reels, and clip names |
| `list_batch_groups` | List all batch groups in the active desktop with their reel counts |
| `list_all_projects` | List all Flame projects available on this workstation |
| `get_clip_metadata` | Get detailed metadata for a specific clip (resolution, frame rate, duration, etc.) |
| `get_selected_clips` | Return the clips currently selected in the Flame media panel or desktop |
| `get_source_path` | Get the filesystem source path of a clip, reel, or library |
| `collect_media_paths` | Collect filesystem paths for all clips in a library or reel |
| `get_write_node_settings` | Get the Write File node settings from the current Batch setup |
| `flame_wiretap_tree` | Inspect the Wiretap IFFFS node tree at a given path |
| `get_flame_version` | Return the running Flame version string |
| `ping` | Check whether the bridge to Autodesk Flame is reachable |
| `search_flame_docs` | Semantic RAG search over Flame API documentation — call before execute_python |
| `resolve_concept` | Fast static lookup: map a user concept to the correct API path and tool |
| `learn_pattern` | Add a new working pattern to FLAME_API.md and rebuild the index |
| `session_stats` | Show token usage and RAG savings for the current session |
| `reset_session_stats` | Zero the session stats counters immediately (idle auto-reset fires after 30 min inactivity) |
| `list_flame_logs` | List all log files available in /opt/Autodesk/logs |
| `read_flame_log` | Read a Flame log file with optional tail/grep filtering |
| `create_sequence` | Create a new empty sequence in a Flame library/reel |
| `rename_segments` | Rename a clip (all its segments) in a Flame library/reel |
| `operation_history` | Show the last N execute_python operations recorded this session |
| `undo_last_operation` | Undo the last undoable execute_python operation |
<!-- concept:mcp_tool_table end -->

### Tool workflow

Every Claude response to a Flame request follows this sequence:

```
search_flame_docs(query)          ← look up correct API patterns
  └─ if score < 60%: warn         ← pattern may not be documented
execute_python(code)              ← run the code in Flame
  └─ if score was < 60% and ok:
       learn_pattern(desc, code)  ← teach the system (self-improvement)
session_stats()                   ← show token summary
```

---

## Self-improving RAG

The system maintains a local semantic search index (`rag/index/`) built from all documents in the `docs/` folder plus `FLAME_API.md`. Before every `execute_python` call, Claude searches this index to find the correct API pattern — avoiding guesswork and saving tokens.

### Knowledge base (≈800 chunks across 14 documents)

<!-- concept:rag_corpus_docs start -->
| File | Chunks | Content |
|---|---|---|
| `FLAME_API.md` | ~295 | Core Flame Python API — PyClip, PyReel, PyBatch, PyLibrary, connectors, markers, PyTime, import/export code samples. Auto-extended by `learn_pattern`. |
| `flame_advanced_api.md` | ~78 | Action node (PyActionNode, output types, FBX import), Color Management (CDL/LUT/CTF), Exporter (safe schedule_idle_event pattern), MediaHub, Conform/AAF workflow, Timeline FX/BFX, Python hooks reference. |
| `flame_segment_timeline_api.md` | ~61 | Full PySegment API (trim, slip, create_effect, connected_segments), corrected PyClip.render() signature, PyBatch.create_batch_group(), PySequence methods, post-conform batch group creation patterns. |
| `flame_code_samples.md` | ~46 | Extracted Autodesk official zip samples — clip ops, render, Timeline FX wiring, Action compass nodes. |
| `flame_youtube_patterns.md` | ~60 | Patterns extracted from Logik-TV / YouTube tutorials (OCR + transcript mining). |
| `flame_community_workflows.md` | ~23 | Logik Forum operator terminology → API mapping. Conform jargon, batch compositing terms, render/delivery slang. |
| `flame_cookbook_official.md` | ~22 | Official Autodesk Python API code samples. |
| `flame_reference_guide.md` | ~30 | Troubleshooting + env-setup reference. |
| `flame_ocr_patterns.md` | ~15 | OCR-extracted patterns (v1 pipeline). |
| `flame_ocr_patterns_v2.md` | ~23 | OCR-extracted patterns (v2 pipeline). |
| `flame_openclip_patterns.md` | ~8 | OpenCLIP pattern extractor outputs. |
| `flame_vocabulary.md` | ~8 | Flame-specific terminology glossary — operators vs. the Python API names. |
| `wiretap_sdk_python_reference.md` | ~76 | Wiretap Python SDK — low-level bridge from `flame` module to the Wiretap server. |
| `wiretap_cli_reference.md` | ~38 | Wiretap command-line reference — `wiretap_print_tree`, `wiretap_duplicate_node`, etc. |
<!-- concept:rag_corpus_docs end -->

### How it learns (3-level system)

1. `search_flame_docs` returns the **max relevance score** of the best match
2. If **score < 60%**, the pattern is not well-documented — Claude is warned
3. After a **successful** `execute_python`, Claude calls `learn_pattern(description, code)`
4. Outcome depends on the active model's trust level:
   - **Trusted model** (Sonnet / Opus) → appended to `FLAME_API.md`, index rebuilt in background
   - **Read-only model** (Qwen, Llama…) → staged in `rag/candidates.json` for human review
5. On **failed** execution with low RAG score → logged to `rag/failed.json` as a knowledge gap
6. Next session, verified patterns return >70% relevance instantly

### Manually rebuild the index

```bash
cd ~/flame-mcp
source .venv/bin/activate
python -m flame_mcp.rag.build_index
```

### RAG log

Every search query, its results, and relevance scores are logged to:
```
logs/flame_rag.log
```

---

## Token tracking

Every tool call appends a compact stats footer:

```
─────────────────────────────
🔍 RAG · max relevance 72% · ~210 tokens · ~1290 avoided vs full doc
📊 Session · 3 exec · 2 RAG
   Tokens used             : ~640  🟢 low
   Avoided by RAG/tools    : ~2580  (80% of context)
```

Ratings:
- 🟢 low — under 100 tokens for the call
- 🟡 medium — 100–400 tokens
- 🔴 high — over 400 tokens

`session_stats()` gives the full session breakdown including how many patterns were auto-learned (`🧠 self-improved!`).

> **Note:** Token cost warnings (🟡 🔴) are only shown when using Anthropic cloud models. For Ollama backends (local or cloud) they are suppressed — there are no rate limits or token costs involved.

---

## Project structure

```
flame-mcp/
├── src/flame_mcp/server.py     # MCP server — runs on macOS, talks to Claude
├── hooks/
│   └── flame_mcp_bridge.py    # Flame hook — Unix socket bridge + Qt chat widget
├── rag/
│   ├── build_index.py         # Build / rebuild the ChromaDB index
│   ├── search.py              # Semantic search, returns (text, max_score)
│   └── index/                 # ChromaDB vector store (git-ignored)
├── FLAME_API.md               # Flame Python API reference + patterns (RAG source)
├── CLAUDE.md                  # Instructions for Claude Code terminal context
├── claude_desktop_config.json # Claude Desktop MCP config (copy to ~/Library/...)
├── requirements.txt
├── install.sh
├── LICENSE
├── logs/
│   ├── flame_mcp_bridge.log   # bridge activity log
│   └── flame_rag.log          # RAG query log with relevance scores
└── docs/
    ├── flame-mcp-reference.pdf      # Full reference guide
    ├── FLAME_API.md                 # (root) Core API + self-learned patterns
    ├── flame_advanced_api.md        # Action, Color Mgmt, Exporter, Conform, TL FX
    ├── flame_segment_timeline_api.md# PySegment, PyClip.render, PyBatch.create_batch_group
    ├── flame_community_workflows.md # Logik Forum operator jargon → API
    ├── flame_cookbook_official.md   # Official Autodesk Python code samples
    └── flame_vocabulary.md          # Operator terminology glossary
```

---

## Ollama setup (optional)

Three Ollama-based backends are available, covering every scenario:

```
┌─────────────────┬──────────────────────┬────────────────────────────────────┐
│ Backend         │ Physical path        │ Use case                           │
├─────────────────┼──────────────────────┼────────────────────────────────────┤
│ ollama          │ Mac → gpu-server LAN │ Best quality, big GPU model        │
│ ollama_cloud ☁  │ Mac localhost → ☁    │ Anywhere with internet, no GPU     │
│ ollama_mac  🍎  │ Mac localhost        │ Offline emergency, no internet     │
└─────────────────┴──────────────────────┴────────────────────────────────────┘
```

`ollama_cloud` and `ollama_mac` both require **Ollama installed on the Mac** — a lightweight daemon (~50 MB, no models bundled) that listens at `localhost:11434` and implements the Anthropic Messages API. For cloud models it acts as a transparent proxy to ollama.com; for local models it runs them directly using Mac CPU/GPU.

> Ollama was **not** previously required on the Mac — it only ran on gpu-server. This is a new requirement for the two Mac-based backends.

### Option 1 — Self-hosted GPU (ollama backend)

Best quality. Runs on the Linux workstation (gpu-server) with a dedicated GPU.

**On the Linux machine (gpu-server):**

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Allow remote connections and keep models warm
sudo systemctl edit ollama --force --full
# Add under [Service]:
#   Environment="OLLAMA_HOST=0.0.0.0:11434"
#   Environment="OLLAMA_KEEP_ALIVE=10m"
#   Environment="OLLAMA_NEW_ENGINE=true"
sudo systemctl restart ollama

# Pull the two models defined in AVAILABLE_MODELS (hooks/flame_mcp_bridge.py)
ollama pull qwen3.5:9b
ollama cp qwen3.5:9b qwen3.5-mcp          # matches the `qwen3.5-mcp` tag
ollama pull glm-4.7-flash                  # matches the `glm-4.7-flash` tag
```

**In the Flame widget:**
1. Select **Qwen3.5 9B 🖥** (or **GLM-4.7 Flash 🖥**) from the model dropdown
2. Enter the server URL (e.g. `http://192.168.1.50:11434`) and press Enter
3. The combo label updates to show `· gpu-server` confirming the server is saved

> **GPU requirements:** Qwen3.5 9B (~6.6 GB Q4_K_M) and GLM-4.7 Flash fit comfortably in a 24 GB GPU (RTX 3090) with `num_ctx=24576` set at runtime by the bridge. The bridge pre-flight overrides Modelfile `num_ctx` on every session (Ollama's Anthropic-compat endpoint ignores it otherwise).

### Option 2 — Ollama cloud proxy (ollama_cloud backend)

Free 480B parameter model running on ollama.com's infrastructure. Works anywhere with internet, no GPU required. Requires Ollama on the Mac.

**On the Mac (one-time setup):**

```bash
brew install ollama
# Start the daemon (add to login items if you want it always running)
ollama serve
```

**In the Flame widget:**
1. Select **qwen3-coder 480B ☁** from the model dropdown
2. The combo shows `· localhost → ☁` — no further configuration needed
3. On first use the model tag `qwen3-coder:480b-cloud` is downloaded automatically

The Mac daemon forwards the request to ollama.com's servers. Authentication with ollama.com is handled by the daemon using your logged-in account — no API key needed in the widget.

> To log in to ollama.com from the Mac: `ollama login` in Terminal.

### Option 3 — Mac offline fallback (ollama_mac backend)

Small model stored locally on the Mac. Works with no internet and no gpu-server — useful when working remotely on a laptop.

**On the Mac (one-time setup, ~4 GB download):**

```bash
brew install ollama
ollama serve
ollama pull qwen2.5-coder:7b
```

**In the Flame widget:**
1. Select **qwen2.5-coder 7B 🍎** from the model dropdown
2. The combo shows `· localhost` — ready to use offline

Quality is significantly lower than the 30B or 480B models. Runs on Mac CPU (no GPU required); response time is slower than GPU backends.

> ⚠️ **Tool use limitation:** 7B models often fail to invoke MCP tools correctly — they may print raw JSON instead of executing the tool call. This backend is best suited for text queries (API questions, code explanations) rather than live Flame control. For actual Flame operations use `anthropic`, `ollama`, or `ollama_cloud`.

### How the backends work internally

Ollama implements the [Anthropic Messages API](https://ollama.com/blog/claude) natively (v0.14+). The bridge sets `ANTHROPIC_BASE_URL` before launching the `claude` CLI subprocess:

- `ollama` → `http://<ollama_url>` (gpu-server LAN address)
- `ollama_cloud` → `http://localhost:11434` (Mac daemon → cloud proxy)
- `ollama_mac` → `http://localhost:11434` (Mac daemon → local model)

For the `ollama` (LAN GPU) backend only, the bridge also sends a pre-flight request to Ollama's native `/api/generate` endpoint to force-load the model with the correct context window. This is necessary because Ollama's Anthropic-compatible endpoint ignores the `num_ctx` set in a Modelfile.

---

## Flame hook locations

Flame loads Python hooks at startup from these paths (in order of priority):

| Path | Scope |
|------|-------|
| `$DL_PYTHON_HOOK_PATH` | Custom environment variable |
| `/opt/Autodesk/shared/python/` | All installed Flame versions |
| `/opt/Autodesk/<version>/python/` | Specific Flame version |
| `/opt/Autodesk/user/<username>/python/` | Specific system user |

This project uses `/opt/Autodesk/shared/python/` so the bridge works across all Flame versions.

---

## Troubleshooting

**Claude can't connect to Flame**
- Make sure Flame is open
- Check `MCP Bridge → Status` in the Flame menu
- Verify `flame_mcp_bridge.py` is in `/opt/Autodesk/shared/python/`
- Check the Unix socket exists: `ls -la ~/flame-mcp/run/flame_mcp.sock` — should be `srw-------`
- If Unix socket is absent, the bridge falls back to TCP; run `lsof -i :4444` to confirm Flame is listening

**Low RAG relevance scores on common operations**
- If a pattern scores < 60%, Claude will auto-learn it after a successful run
- You can also manually rebuild the index: `python -m flame_mcp.rag.build_index`

**Claude Chat (embedded) doesn't open**
- Check `logs/flame_mcp_bridge.log` for error details
- Ensure `ANTHROPIC_API_KEY` is set in your environment or in `~/flame-mcp/.env`
- Flame 2026+ uses PySide6; older versions use PySide2 (both supported)

**Ollama model runs on CPU instead of GPU**
- Check `journalctl -u ollama -n 50` for `library=cpu` or `offloaded 0/N layers`
- Ensure CUDA is initialised: `python3 -c "import ctypes; print(ctypes.CDLL('libcuda.so.1').cuInit(0))"`  — should return `0`; if `999`, reboot the Linux machine
- Add Ollama's CUDA libs to ldconfig: create `/etc/ld.so.conf.d/ollama-cuda.conf` with `/usr/local/lib/ollama/cuda_v12` and run `sudo ldconfig`
- Set `OLLAMA_NEW_ENGINE=true` in the systemd override

**Ollama model truncates context (`truncating input prompt: limit=4096`)**
- The Anthropic-compatible endpoint ignores Modelfile `num_ctx` — this is expected
- The bridge fixes it automatically via a pre-flight `/api/generate` request; check the bridge log for `Ollama pre-load OK`
- If the issue persists, verify the Modelfile has `PARAMETER num_ctx 24576` and the model was created with `ollama create`

**Ollama cloud / mac-local: "Ollama not found on this Mac"**
- Install and start the Mac daemon: `brew install ollama && ollama serve`
- Verify it's running: `curl http://localhost:11434/api/version`
- For `ollama_mac` only, also pull the model: `ollama pull qwen2.5-coder:7b`
- For `ollama_cloud`, log in so the daemon can authenticate: `ollama login`

**Ollama cloud model not responding**
- The 480B model may take 2–5 minutes on first inference — the widget has a 5-minute watchdog
- Check daemon logs: `journalctl --user -u ollama` (Linux) or `ollama serve` output (Mac)

**Port 4444 is already in use**
The bridge uses a Unix domain socket by default (`~/flame-mcp/run/flame_mcp.sock`), so TCP port 4444 is only used as a fallback when AF_UNIX is unavailable. If you still need to change the TCP fallback port, edit `BRIDGE_PORT = 4444` in both `flame_mcp_bridge.py` and `src/flame_mcp/server.py`. To override the socket path: set `FLAME_BRIDGE_SOCKET=/path/to/custom.sock` in your environment.

**`pip install` fails with `--user` conflict**
Add `--no-user` to pip commands. Happens when `install.user = true` is set globally.

---

## Compatibility

| Flame version | Internal Python | Qt       | Status |
|---------------|----------------|----------|--------|
| 2023          | 3.9.7          | PySide2  | ✓ Compatible |
| 2024          | 3.9.x          | PySide2  | ✓ Compatible |
| 2025          | 3.11.x         | PySide2  | ✓ Compatible |
| 2026          | 3.11.5         | PySide6  | ✓ Tested |
| 2027 preview  | 3.13.3         | PySide6  | ✓ Compatible |

---

## Ecosystem

`flame-mcp` is part of a four-component VFX pipeline. Each component has a defined role:

| Repo | Role |
|------|------|
| [flame-mcp](https://github.com/abrahamADSK/flame-mcp) | Controls Autodesk Flame for compositing, conform, and finishing |
| [maya-mcp](https://github.com/abrahamADSK/maya-mcp) | Controls Autodesk Maya for 3D modeling, animation, and rendering |
| [fpt-mcp](https://github.com/abrahamADSK/fpt-mcp) | Connects to Autodesk Flow Production Tracking (ShotGrid) for production tracking, asset management, and publishes |
| [vision3d](https://github.com/abrahamADSK/vision3d) | GPU inference server for AI-powered 3D generation — the remote backend for maya-mcp's image-to-3D and text-to-3D tools |

`flame-mcp` operates at the finishing stage of the pipeline. When both `fpt-mcp` and `flame-mcp` are active, Claude can query ShotGrid for shot status, resolve the correct media path, and execute Flame operations against it in a single conversation. `maya-mcp` can hand off rendered outputs that `flame-mcp` then picks up for conform and grade. `vision3d` is not directly consumed by `flame-mcp`.

---

## License

[MIT](LICENSE)
