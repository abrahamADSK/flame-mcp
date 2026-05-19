# Deploy & operator guide for flame-mcp

Operator-facing setup and deploy instructions. **Not loaded into the
LLM system prompt.** For LLM behavioural rules see `CLAUDE.md` at the
repo root.

This file was extracted from `CLAUDE.md` in chat 51 phase F6a (PR
linked from the same commit) so the per-turn prompt no longer carries
~80 lines of bash workflow the LLM never acts on. The F3b adversarial
suite (`tests/golden/flame_queries.jsonl`) is the load-bearing defense
against API misuse; this document is reference for the human installer.

---

## Prerequisites for local models

```bash
# Install Ollama (macOS)
brew install ollama
brew services start ollama

# Pull the model
ollama pull qwen3.5:9b
# On Mac 24GB (fallback):
ollama pull qwen3.5:4b
```

The bridge handles `num_ctx=24576` at runtime via the Ollama preflight
(F1b ships a `keep_alive` knob too — default 30 min). No custom
Modelfile required; the alias `qwen3.5-mcp` is just
`ollama cp qwen3.5:9b qwen3.5-mcp`.

---

## Deploy workflow — after every code change

### One-time setup: symlink `flame_mcp_bridge.py` (recommended)

Flame loads the bridge hook from the hardcoded path
`/opt/Autodesk/shared/python/flame_mcp_bridge.py`. On a fresh workstation,
symlink that path to the working tree so every `git pull` deploys the
latest bridge instantly — no per-change `cp` required:

```bash
sudo ln -sf ~/Projects/flame-mcp/hooks/flame_mcp_bridge.py \
           /opt/Autodesk/shared/python/flame_mcp_bridge.py
```

Verify:

```bash
ls -la /opt/Autodesk/shared/python/flame_mcp_bridge.py
# Should show: ... -> /Users/<you>/Projects/flame-mcp/hooks/flame_mcp_bridge.py
```

The M4 Pro workstation has this symlink in place since 2026-03-09. You
still need **MCP Bridge → Reload hook** in Flame after each bridge
change, because the Flame Python process caches the compiled bytecode
of the hook module in memory — the symlink serves the source file, not
the bytecode. Reload forces `importlib.reload` inside Flame.

### `src/flame_mcp/server.py` only:

```bash
git push && pkill -f flame_mcp.server
```

Claude Desktop respawns the server automatically with the new code.

### `hooks/flame_mcp_bridge.py` only:

**With symlink in place** (recommended — current M4 Pro setup):

```bash
git push
```

Then in Flame: **MCP Bridge → Reload hook**

**Without symlink** (fresh machine, pre-setup fallback):

```bash
git push && cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/flame_mcp_bridge.py
```

Then in Flame: **MCP Bridge → Reload hook**

The `cp` is idempotent — running it on a host that already has the
symlink reports "identical" and does nothing, so you can script either
workflow without branching.

### Both files:

**With symlink**:

```bash
git push && pkill -f flame_mcp.server
```

**Without symlink**:

```bash
git push && pkill -f flame_mcp.server && cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/flame_mcp_bridge.py
```

Then in Flame: **MCP Bridge → Reload hook**
