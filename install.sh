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
