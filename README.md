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
Claude → MCP Server → TCP socket → Flame Python API → Result back to Claude
```

---

## How it works

The system has two components:

**`hooks/flame_mcp_bridge.py`** — A Flame Python hook that starts a local TCP socket server (port 4444) when Flame launches. It receives Python code, executes it inside Flame's Python interpreter with full access to the `flame` module, and returns the result.

**`flame_mcp_server.py`** — An MCP server that Claude launches. It exposes tools that Claude can call by name, translates natural language into Python code, and communicates with the bridge over the socket.

```
┌──────────────────┐    MCP (stdio)    ┌──────────────────────┐    TCP 4444    ┌─────────────────┐
│  Claude Code /   │ ◄──────────────── │   flame_mcp_server   │ ◄──────────── │  Autodesk Flame │
│  Claude Desktop  │ ─────────────────►│   (Python, macOS)    │ ─────────────►│  Python bridge  │
└──────────────────┘                   └──────────────────────┘                └─────────────────┘
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
- A Linux machine (same LAN or localhost) running [Ollama](https://ollama.com) 0.14+ with GPU
- Or a free [ollama.com](https://ollama.com) cloud account (no GPU required)
- See [Ollama setup](#ollama-setup-optional) below

> **Note on Python versions:** The MCP server runs on your system Python (3.11+). Code executed *inside* Flame uses Flame's bundled Python interpreter (Flame 2026 ships Python 3.11.5).

---

## Installation

### Automatic (recommended)

```bash
git clone https://github.com/abrahamADSK/flame-mcp.git
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

### Manual

```bash
# 1. Clone and set up
git clone https://github.com/abrahamADSK/flame-mcp.git
cd flame-mcp

# 2. Virtual environment + dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt --no-user

# 3. Build the RAG index
python rag/build_index.py

# 4. Install the Flame hook
sudo cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/

# 5. Register with Claude Code
claude mcp add flame -- "$(pwd)/.venv/bin/python" "$(pwd)/flame_mcp_server.py"

# 6. (Optional) Claude Desktop
#    Copy claude_desktop_config.json to ~/Library/Application Support/Claude/
```

---

## Usage

### 1. Flame menu — MCP Bridge

When Flame starts, the hook registers an **MCP Bridge** submenu in Flame's main menu bar:

```
MCP Bridge  [● Active]
├── Status: ● Active — port 4444   → shows current bridge status
├── Start bridge                   → start TCP listener on port 4444
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

- Reads `ANTHROPIC_API_KEY` from environment or `~/Projects/flame-mcp/.env`
- Executes Flame code via the TCP bridge (thread-safe, non-blocking)
- Uses the local RAG index to look up API patterns before every call
- Requires PySide6 (bundled with Flame 2026+)

**Model selector dropdown** — four backends, switch without leaving Flame:

| Backend | Model | Requires | Works offline? |
|---------|-------|----------|----------------|
| `anthropic` | Sonnet 4.5, Haiku 4.5 | Claude account | ✗ |
| `ollama` | qwen3-coder 30B | glorfindel on LAN + GPU | ✗ |
| `ollama_cloud` ☁ | qwen3-coder 480B | Ollama on Mac + internet | ✗ |
| `ollama_mac` 🍎 | qwen2.5-coder 7B | Ollama on Mac | ✓ |

Selection is persisted to `~/Projects/flame-mcp/config.json` between sessions. The combo label shows the server hostname for `ollama`, or `localhost → ☁` / `localhost` for the Mac backends.

### 3. Claude Code (terminal)

```bash
cd ~/Projects/flame-mcp
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

## MCP Tools

| Tool | Description |
|------|-------------|
| `execute_python` | Execute arbitrary Python code inside Flame with full API access |
| `get_project_info` | Return name, frame rate, resolution, bit depth of the active project |
| `list_libraries` | List all libraries in the project with reel counts |
| `list_reels` | List reels in a library, or across all libraries |
| `get_flame_version` | Return the running Flame version string |
| `search_flame_docs` | Semantic RAG search over FLAME_API.md — call before execute_python |
| `learn_pattern` | Add a new working pattern to FLAME_API.md and rebuild the index |
| `session_stats` | Show token usage and RAG savings for the current session |

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

### Knowledge base (375 chunks total)

| File | Chunks | Content |
|---|---|---|
| `FLAME_API.md` | 116 | Core Flame Python API — PyClip, PyReel, PyBatch, PyLibrary, connectors, markers, PyTime, import/export code samples. Auto-extended by `learn_pattern`. |
| `docs/flame_advanced_api.md` | 74 | Action node (PyActionNode, output types, FBX import), Color Management (CDL/LUT/CTF via PyClrMgmtNode), Exporter (PyExporter), MediaHub, Conform/AAF workflow patterns, Timeline FX/BFX, Python hooks reference, operator-phrase → API lookup table. |
| `docs/flame_api_full.md` | 71 | Extended API reference — PySequence, PyTrack, PyVersion, PyMarker, PyProject, PyWorkspace, batch nodes, render pipeline, archive. |
| `docs/flame_segment_timeline_api.md` | 61 | Full PySegment API (trim, slip, create_effect, connected_segments), corrected PyClip.render() signature, PyBatch.create_batch_group(), PySequence methods, post-conform batch group creation patterns. |
| `docs/flame_community_workflows.md` | 23 | Logik Forum operator terminology → API mapping. Conform jargon, batch compositing terms, render/delivery slang, 35-row operator→API lookup table. |
| `docs/flame_cookbook_official.md` | 22 | Official Autodesk Python API code samples — clip import/reformat/render, Timeline FX create/bypass/save/load, batch group creation, node wiring, multi-pass render, Action compass nodes. |
| `docs/flame_vocabulary.md` | 8 | Flame-specific terminology glossary — how operators refer to things vs. the Python API names. |

### How it learns

1. `search_flame_docs` returns the **max relevance score** of the best match
2. If **score < 60%**, the pattern is not well-documented — Claude is warned
3. After a **successful** `execute_python`, Claude calls `learn_pattern(description, code)`
4. `learn_pattern` appends the working code as a new pattern block in `FLAME_API.md`
5. The RAG index is **rebuilt in the background** via subprocess
6. Next session, the same operation finds a high-relevance match (>70%) instantly

### Manually rebuild the index

```bash
cd ~/Projects/flame-mcp
source .venv/bin/activate
python rag/build_index.py
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
├── flame_mcp_server.py         # MCP server — runs on macOS, talks to Claude
├── hooks/
│   └── flame_mcp_bridge.py    # Flame hook — TCP bridge + Qt chat widget
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
│   ├── flame_mcp_bridge.log   # TCP bridge activity log
│   └── flame_rag.log          # RAG query log with relevance scores
└── docs/
    ├── flame-mcp-reference.pdf      # Full reference guide
    ├── FLAME_API.md                 # (root) Core API + self-learned patterns
    ├── flame_advanced_api.md        # Action, Color Mgmt, Exporter, Conform, TL FX
    ├── flame_api_full.md            # Extended API — sequences, tracks, projects
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
│ ollama          │ Mac → glorfindel LAN │ Best quality, big GPU model        │
│ ollama_cloud ☁  │ Mac localhost → ☁    │ Anywhere with internet, no GPU     │
│ ollama_mac  🍎  │ Mac localhost        │ Offline emergency, no internet     │
└─────────────────┴──────────────────────┴────────────────────────────────────┘
```

`ollama_cloud` and `ollama_mac` both require **Ollama installed on the Mac** — a lightweight daemon (~50 MB, no models bundled) that listens at `localhost:11434` and implements the Anthropic Messages API. For cloud models it acts as a transparent proxy to ollama.com; for local models it runs them directly using Mac CPU/GPU.

> Ollama was **not** previously required on the Mac — it only ran on glorfindel. This is a new requirement for the two Mac-based backends.

### Option 1 — Self-hosted GPU (ollama backend)

Best quality. Runs on the Linux workstation (glorfindel) with a dedicated GPU.

**On the Linux machine (glorfindel):**

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

# Pull and create a custom model with the correct context window
ollama pull qwen3-coder:30b-a3b-q4_K_M
cat > ~/Modelfile <<'EOF'
FROM qwen3-coder:30b-a3b-q4_K_M
PARAMETER num_ctx 24576
PARAMETER num_keep 4
EOF
ollama create qwen3-flame -f ~/Modelfile
```

**In the Flame widget:**
1. Select **qwen3-coder 30B** from the model dropdown
2. Enter the server URL (e.g. `http://192.168.1.50:11434`) and press Enter
3. The combo label updates to show `· glorfindel` confirming the server is saved

> **GPU requirements:** qwen3-coder 30B (Q4_K_M, ~18.5 GB) fits in a 24 GB GPU (e.g. RTX 3090) with a 24K context window. Reduce `num_ctx` if you have less VRAM.

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

Small model stored locally on the Mac. Works with no internet and no glorfindel — useful when working remotely on a laptop.

**On the Mac (one-time setup, ~4 GB download):**

```bash
brew install ollama
ollama serve
ollama pull qwen2.5-coder:7b
```

**In the Flame widget:**
1. Select **qwen2.5-coder 7B 🍎** from the model dropdown
2. The combo shows `· localhost` — ready to use offline

Quality is lower than the 30B or 480B models but it handles most Flame API tasks correctly. Runs on Mac CPU (no GPU required); response time is slower than GPU backends.

### How the backends work internally

Ollama implements the [Anthropic Messages API](https://ollama.com/blog/claude) natively (v0.14+). The bridge sets `ANTHROPIC_BASE_URL` before launching the `claude` CLI subprocess:

- `ollama` → `http://<ollama_url>` (glorfindel LAN address)
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
- Run `lsof -i :4444` — should show Flame listening

**Low RAG relevance scores on common operations**
- If a pattern scores < 60%, Claude will auto-learn it after a successful run
- You can also manually rebuild the index: `python rag/build_index.py`

**Claude Chat (embedded) doesn't open**
- Check `logs/flame_mcp_bridge.log` for error details
- Ensure `ANTHROPIC_API_KEY` is set in your environment or in `~/Projects/flame-mcp/.env`
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
Edit both `flame_mcp_bridge.py` and `flame_mcp_server.py`, change `BRIDGE_PORT = 4444` to an unused port. Values must match.

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

## License

[MIT](LICENSE)
