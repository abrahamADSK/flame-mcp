#!/usr/bin/env bash
# =============================================================================
# flame-mcp installer
# =============================================================================
# Installs the Flame MCP bridge and server on macOS.
#
# What this script does:
#   1. Checks prerequisites (Python 3.11+, Claude Code)
#   2. Creates a Python virtual environment in the project folder
#   3. Installs Python dependencies
#   4. Copies the Flame hook to /opt/Autodesk/shared/python/
#   5. Registers the MCP server with Claude Code
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
# =============================================================================

set -e

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Colour

ok()   { echo -e "${GREEN}  ✓${NC} $1"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $1"; }
err()  { echo -e "${RED}  ✗${NC} $1"; exit 1; }
info() { echo -e "${BLUE}  →${NC} $1"; }

echo ""
echo "================================================="
echo "  flame-mcp installer"
echo "================================================="
echo ""

# ── Locate script directory ───────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
info "Project directory: $SCRIPT_DIR"

# ── 1. Check Python 3.11+ ─────────────────────────────────────────────────────
info "Checking Python version..."
if ! command -v python3 &>/dev/null; then
    err "python3 not found. Install it with: brew install python3"
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    err "Python 3.11 or higher is required. Found: $PYTHON_VERSION"
fi
ok "Python $PYTHON_VERSION"

# ── 2. Check Claude Code ──────────────────────────────────────────────────────
info "Checking Claude Code..."
if ! command -v claude &>/dev/null; then
    err "Claude Code not found. Install it with: npm install -g @anthropic-ai/claude-code"
fi
CLAUDE_VERSION=$(claude --version 2>/dev/null | head -1)
ok "Claude Code: $CLAUDE_VERSION"

# ── 3. Create virtual environment ────────────────────────────────────────────
info "Setting up Python virtual environment..."
if [ -d "$SCRIPT_DIR/.venv" ]; then
    warn "Virtual environment already exists, skipping creation."
else
    python3 -m venv "$SCRIPT_DIR/.venv"
    ok "Virtual environment created at .venv/"
fi

PYTHON_VENV="$SCRIPT_DIR/.venv/bin/python"
PIP_VENV="$SCRIPT_DIR/.venv/bin/pip"

# ── 4. Install dependencies ───────────────────────────────────────────────────
info "Installing Python dependencies..."
"$PIP_VENV" install --quiet --no-user -r "$SCRIPT_DIR/requirements.txt"
ok "Dependencies installed (mcp, chromadb, sentence-transformers)"

# ── 5. Install Flame hook ─────────────────────────────────────────────────────
HOOK_SRC="$SCRIPT_DIR/hooks/flame_mcp_bridge.py"
HOOK_DST="/opt/Autodesk/shared/python/flame_mcp_bridge.py"

info "Installing Flame hook to /opt/Autodesk/shared/python/..."

if [ ! -d "/opt/Autodesk/shared/python" ]; then
    warn "/opt/Autodesk/shared/python/ not found."
    warn "Is Autodesk Flame installed? Skipping hook installation."
    warn "To install manually: sudo cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/"
else
    if sudo cp "$HOOK_SRC" "$HOOK_DST"; then
        ok "Flame hook installed. Restart Flame to activate the bridge."
    else
        err "Failed to copy hook. Try running: sudo cp hooks/flame_mcp_bridge.py /opt/Autodesk/shared/python/"
    fi
fi

# ── 6. Build RAG index ────────────────────────────────────────────────────────
RAG_INDEX="$SCRIPT_DIR/rag/index"
if [ -d "$RAG_INDEX" ] && [ "$(ls -A "$RAG_INDEX" 2>/dev/null)" ]; then
    ok "RAG index already present (pre-built). Skipping rebuild."
    info "To force a rebuild: python rag/build_index.py"
else
    info "Building RAG documentation index..."
    info "(Downloads embedding model ~130 MB from HuggingFace on first run)"
    if "$PYTHON_VENV" "$SCRIPT_DIR/rag/build_index.py"; then
        ok "RAG index built."
    else
        warn "RAG index build failed — search_flame_docs will show an error."
        warn "Fix with: source .venv/bin/activate && python rag/build_index.py"
    fi
fi

# ── 7. Register MCP server with Claude Code ───────────────────────────────────
info "Registering MCP server with Claude Code..."

SERVER_SCRIPT="$SCRIPT_DIR/flame_mcp_server.py"

# Remove existing registration silently, then re-add
claude mcp remove flame 2>/dev/null || true
claude mcp add flame -- "$PYTHON_VENV" "$SERVER_SCRIPT"
ok "MCP server 'flame' registered with Claude Code."

# ── 8. Auto-approve MCP tools in Claude Code ──────────────────────────────────
# Writes tool permissions to .claude/settings.local.json (permissions.allow).
# Claude Code reads this file for project-level tool approvals.
# Any future tool added to flame_mcp_server.py is auto-approved on next install.
info "Configuring Claude Code tool auto-approval..."

CLAUDE_SETTINGS="$SCRIPT_DIR/.claude/settings.local.json"

SERVER_SCRIPT="$SERVER_SCRIPT" CLAUDE_SETTINGS="$CLAUDE_SETTINGS" "$PYTHON_VENV" - <<'PYEOF'
import ast, json, os
from pathlib import Path

server_script = os.environ['SERVER_SCRIPT']
settings_file = Path(os.environ['CLAUDE_SETTINGS'])

# Extract all @mcp.tool() decorated function names
with open(server_script) as f:
    tree = ast.parse(f.read())

new_tools = []
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == 'tool'):
                new_tools.append(f'mcp__flame__{node.name}')

# Merge with existing settings (preserves Bash allow entries)
settings_file.parent.mkdir(parents=True, exist_ok=True)
if settings_file.exists():
    settings = json.loads(settings_file.read_text())
else:
    settings = {}

settings.setdefault('permissions', {}).setdefault('allow', [])
existing = set(settings['permissions']['allow'])
settings['permissions']['allow'] = sorted(existing | set(new_tools),
    key=lambda x: (not x.startswith('mcp__'), x))

settings_file.write_text(json.dumps(settings, indent=2))

print(f'  {len(new_tools)} flame tools auto-approved in {settings_file}')
for t in sorted(new_tools):
    print(f'    + {t}')
PYEOF

ok "Tool auto-approval configured — no permission prompts on first use."

# ── 9. Hardware detection + Ollama model recommendation ───────────────────────
echo ""
echo -e "${YELLOW}─── Step 9: Hardware detection & Ollama setup ───────────────────${NC}"

# Detect VRAM (NVIDIA only; add AMD/Metal support as needed)
VRAM_MB=0
if command -v nvidia-smi &>/dev/null 2>&1; then
    VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null \
              | head -1 | tr -d ' \r' || echo 0)
fi

# Detect total RAM in GB
if command -v free &>/dev/null 2>&1; then
    RAM_GB=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}')
else
    # macOS fallback
    RAM_GB=$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%d", $1/1024/1024/1024}')
fi
RAM_GB=${RAM_GB:-0}

echo "  GPU VRAM : ${VRAM_MB} MB"
echo "  RAM      : ${RAM_GB} GB"

# Determine recommended Ollama model based on VRAM
RECOMMENDED_OLLAMA_MODEL=""
if [ "$VRAM_MB" -ge 20000 ] 2>/dev/null; then
    RECOMMENDED_OLLAMA_MODEL="qwen3-coder:30b-a3b"
    echo -e "  → ${GREEN}Recommended local model: qwen3-coder:30b-a3b${NC} (~18 GB VRAM, ~60 tok/s)"
elif [ "$VRAM_MB" -ge 10000 ] 2>/dev/null; then
    RECOMMENDED_OLLAMA_MODEL="qwen2.5-coder:14b"
    echo -e "  → ${GREEN}Recommended local model: qwen2.5-coder:14b${NC} (~10 GB VRAM, ~80 tok/s)"
elif [ "$VRAM_MB" -ge 6000 ] 2>/dev/null; then
    RECOMMENDED_OLLAMA_MODEL="qwen2.5-coder:7b"
    echo -e "  → ${YELLOW}Recommended local model: qwen2.5-coder:7b${NC} (~6 GB VRAM, fast but lighter)"
elif [ "$RAM_GB" -ge 32 ] 2>/dev/null; then
    RECOMMENDED_OLLAMA_MODEL="qwen2.5-coder:7b"
    echo -e "  → ${YELLOW}No dedicated GPU detected. CPU inference with qwen2.5-coder:7b${NC} (slow)"
else
    echo -e "  → ${YELLOW}Insufficient resources for local models. Using Anthropic cloud (default).${NC}"
fi

# Config file path
CONFIG_FILE="$SCRIPT_DIR/config.json"

# Only proceed if a local model is viable and Ollama is available
if [ -n "$RECOMMENDED_OLLAMA_MODEL" ] && command -v ollama &>/dev/null 2>&1; then
    echo ""
    read -r -p "  Configure Ollama local backend with $RECOMMENDED_OLLAMA_MODEL? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then

        # Update config.json
        python3 - <<PYEOF
import json, os, sys
cfg_path = "$CONFIG_FILE"
cfg = {}
if os.path.exists(cfg_path):
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
    except Exception:
        pass
cfg['model']   = "$RECOMMENDED_OLLAMA_MODEL"
cfg['backend'] = "ollama_local"
if 'ollama_cloud_key' not in cfg:
    cfg['ollama_cloud_key'] = ""
os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
with open(cfg_path, 'w') as f:
    json.dump(cfg, f, indent=2)
print(f"  config.json updated: model={cfg['model']} backend={cfg['backend']}")
PYEOF

        ok "config.json set to Ollama local backend ($RECOMMENDED_OLLAMA_MODEL)."

        # Offer to pull the model
        echo ""
        ESTIMATED_SIZE="~18 GB"
        [ "$RECOMMENDED_OLLAMA_MODEL" = "qwen2.5-coder:14b" ] && ESTIMATED_SIZE="~10 GB"
        [ "$RECOMMENDED_OLLAMA_MODEL" = "qwen2.5-coder:7b"  ] && ESTIMATED_SIZE="~5 GB"
        read -r -p "  Pull $RECOMMENDED_OLLAMA_MODEL now? ($ESTIMATED_SIZE download) [y/N] " pull_ans
        if [[ "$pull_ans" =~ ^[Yy]$ ]]; then
            echo "  Running: ollama pull $RECOMMENDED_OLLAMA_MODEL"
            ollama pull "$RECOMMENDED_OLLAMA_MODEL"
            ok "Model pulled and ready."
        else
            echo "  Skipped. Pull it later with:  ollama pull $RECOMMENDED_OLLAMA_MODEL"
        fi
    else
        echo "  Skipped. Default Anthropic models remain active."
        echo "  To configure Ollama later, edit: $CONFIG_FILE"
        echo "    Set:  \"model\": \"qwen3-coder:30b-a3b\",  \"backend\": \"ollama_local\""
    fi
elif [ -n "$RECOMMENDED_OLLAMA_MODEL" ] && ! command -v ollama &>/dev/null 2>&1; then
    echo ""
    echo -e "  ${YELLOW}Ollama not installed.${NC} Your GPU ($VRAM_MB MB) supports $RECOMMENDED_OLLAMA_MODEL."
    echo "  Install Ollama from https://ollama.com, then:"
    echo "    ollama pull $RECOMMENDED_OLLAMA_MODEL"
    echo "  And in config.json set:"
    echo "    \"model\": \"$RECOMMENDED_OLLAMA_MODEL\",  \"backend\": \"ollama_local\""
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "================================================="
echo -e "  ${GREEN}Installation complete!${NC}"
echo "================================================="
echo ""
echo "  Next steps:"
echo "  1. Restart Autodesk Flame"
echo "  2. Verify the bridge is active in Flame's Python console:"
echo "     [FlameMCPBridge] Activo en 127.0.0.1:4444"
echo "  3. Open Claude Code from this project folder:"
echo "     cd $SCRIPT_DIR && claude"
echo ""
