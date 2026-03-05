# flame-mcp

> Control Autodesk Flame with natural language using Claude and the Model Context Protocol (MCP).

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

The system maintains a local semantic search index (`rag/index/`) built from `FLAME_API.md`. Before every `execute_python` call, Claude searches this index to find the correct API pattern — avoiding guesswork and saving tokens.

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
🔍 RAG · max relevance 72% · ~210 tokens · ~1290 saved vs full doc
📊 Session · 3 exec · 2 RAG
   Tokens used    : ~640  🟢 low
   Tokens saved (RAG): ~2580  (80% of total)
```

Ratings:
- 🟢 low — under 100 tokens for the call
- 🟡 medium — 100–400 tokens
- 🔴 high — over 400 tokens

`session_stats()` gives the full session breakdown including how many patterns were auto-learned (`🧠 self-improved!`).

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
    └── flame-mcp-reference.pdf  # Full reference guide (this document)
```

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
