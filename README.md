# flame-mcp

> Control Autodesk Flame with natural language using Claude Code and the Model Context Protocol (MCP).

`flame-mcp` connects [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) to [Autodesk Flame](https://www.autodesk.com/products/flame) via a lightweight Python bridge. Type what you want to do in plain language — Claude translates it into Flame API calls and executes them live.

```
You: "List all reels in the current project"
Claude → MCP Server → TCP socket → Flame Python API → Result back to Claude
```

---

## How it works

The system has two components:

**`hooks/flame_mcp_bridge.py`** — A Flame Python hook that starts a local TCP socket server (port 4444) when Flame launches. It receives Python code, executes it inside Flame's Python interpreter with full access to the `flame` module, and returns the result.

**`flame_mcp_server.py`** — An MCP server that Claude Code launches automatically. It exposes tools that Claude can call by name, translates natural language requests into Python code, and communicates with the bridge over the socket.

```
┌──────────────────┐       MCP (stdio)      ┌──────────────────────┐       TCP 4444       ┌─────────────────┐
│   Claude Code    │ ◄───────────────────── │   flame_mcp_server   │ ◄─────────────────── │  Autodesk Flame │
│   (terminal)     │ ─────────────────────► │   (Python, macOS)    │ ────────────────────► │  Python bridge  │
└──────────────────┘                        └──────────────────────┘                       └─────────────────┘
```

---

## Requirements

- macOS
- [Autodesk Flame](https://www.autodesk.com/products/flame) 2025 or later
- Python 3.11 or higher (`python3 --version`)
- [Node.js](https://nodejs.org) v22 or higher (required by Claude Code)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) 2.x (`npm install -g @anthropic-ai/claude-code`)
- A Claude account ([claude.ai](https://claude.ai)) — Pro, Max, or API key

> **Note on Python versions:** The MCP server runs on your system Python (3.11+). Code executed *inside* Flame uses Flame's bundled Python interpreter, which varies by version (Flame 2026 ships Python 3.11.5, Flame 2027 ships Python 3.13.3).

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
2. Install dependencies
3. Copy the Flame hook to `/opt/Autodesk/shared/python/` (requires `sudo`)
4. Register the MCP server with Claude Code

### Manual

```bash
# 1. Clone and set up the project
git clone https://github.com/abrahamADSK/flame-mcp.git
cd flame-mcp

# 2. Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt --no-user

# 3. Install the Flame hook (requires sudo — writes to Autodesk system directory)
sudo cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/

# 4. Register the MCP server with Claude Code
claude mcp add flame -- "$(pwd)/.venv/bin/python" "$(pwd)/flame_mcp_server.py"
# Expected output:
# Added stdio MCP server flame with command: ... to local config
# File modified: ~/.claude.json [project: ~/Projects/flame-mcp]
```

---

## Usage

1. **Open Flame.** The bridge starts automatically. A **MCP Bridge** menu appears in Flame's main menu bar showing the current status:
   ```
   MCP Bridge  [● Active]
   ├── Status: ● Active — port 4444
   ├── Start bridge
   ├── Stop bridge
   └── Restart bridge
   ```
   You can also confirm the bridge is active from the terminal:
   ```bash
   lsof -i :4444
   # Expected: flame <PID> ... TCP localhost:4444 (LISTEN)
   ```

2. **Launch Claude Code** from the project folder:
   ```bash
   cd ~/Projects/flame-mcp
   source .venv/bin/activate
   claude
   ```

3. **Talk to Claude** in natural language:
   ```
   > What's the current project?
   > List all libraries and reels
   > Show me all clips in the "Deliverables" reel
   ```

---

## Available tools

| Tool | Description |
|------|-------------|
| `execute_python` | Execute arbitrary Python code inside Flame with full API access |
| `get_project_info` | Return name, frame rate, resolution and bit depth of the active project |
| `list_libraries` | List all libraries in the project with reel counts |
| `list_reels` | List reels in a library, or across all libraries |
| `get_flame_version` | Return the running Flame version |

The most powerful tool is `execute_python` — it lets Claude execute any Python code with full access to the `flame` module, so it can do anything the Flame Python API supports.

---

## Project structure

```
flame-mcp/
├── flame_mcp_server.py     # MCP server — runs on macOS, talks to Claude Code
├── hooks/
│   └── flame_mcp_bridge.py # Flame hook — runs inside Flame, listens on TCP 4444
├── requirements.txt        # Python dependencies
├── install.sh              # Automatic installer
├── LICENSE                 # MIT
└── docs/
    ├── guide_en.pdf        # Full step-by-step setup guide (English)
    └── guide_es.pdf        # Full step-by-step setup guide (Spanish)
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

This project uses `/opt/Autodesk/shared/python/` so the bridge works across all Flame versions installed on the system.

---

## Troubleshooting

**Claude can't connect to Flame**
- Make sure Flame is open
- Check that `flame_mcp_bridge.py` is in `/opt/Autodesk/shared/python/`
- Restart Flame after installing the hook
- Verify the bridge message appears in Flame's Python console

**Port 4444 is already in use**
Edit both files and change `BRIDGE_PORT = 4444` to an unused port. The value must match in both files.

**`pip install` fails with `--user` conflict**
Add `--no-user` to the pip command. This happens when pip is globally configured with `install.user = true`, which conflicts with virtual environments.

---

## Compatibility

| Flame version | Internal Python | Status |
|---------------|----------------|--------|
| 2023          | 3.9.7          | ✓ Compatible |
| 2024          | 3.9.x          | ✓ Compatible |
| 2025          | 3.11.x         | ✓ Compatible |
| 2026          | 3.11.5         | ✓ Tested |
| 2027 preview  | 3.13.3         | ✓ Compatible |

---

## License

[MIT](LICENSE)
