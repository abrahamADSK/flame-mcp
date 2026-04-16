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
#   ./install.sh            # full install
#   ./install.sh --doctor   # health check (no changes)
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

# ── --doctor: health check subcommand ────────────────────────────────────────
if [ "${1:-}" = "--doctor" ]; then
    echo ""
    echo "================================================="
    echo "  flame-mcp doctor"
    echo "================================================="
    echo ""

    WORST=0  # 0=pass, 1=fail

    doctor_pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; }
    doctor_fail() { echo -e "  ${RED}[FAIL]${NC} $1"; WORST=1; }
    doctor_warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
    doctor_skip() { echo -e "  ${BLUE}[SKIP]${NC} $1"; }

    # ── a) claude.json registration ──────────────────────────────────────────
    # Claude Code stores MCP servers in ~/.claude.json (global) or .mcp.json (project)
    CLAUDE_JSON="$HOME/.claude.json"
    MCP_JSON="$SCRIPT_DIR/.mcp.json"
    FOUND_REG=0
    for cfg_file in "$MCP_JSON" "$CLAUDE_JSON"; do
        if [ -f "$cfg_file" ] && python3 -c "
import json, sys
with open('$cfg_file') as f:
    cfg = json.load(f)
servers = cfg.get('mcpServers', {})
if 'flame' in servers or 'flame-mcp' in servers:
    sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
            FOUND_REG=1
            doctor_pass "MCP registration: flame-mcp found in $(basename "$cfg_file")"
            break
        fi
    done
    if [ "$FOUND_REG" -eq 0 ]; then
        doctor_fail "MCP registration: flame-mcp NOT found in .mcp.json or ~/.claude.json"
        echo -e "         ${NC}Run: claude mcp add flame -- \"\$(pwd)/.venv/bin/python\" -m flame_mcp.server"
    fi

    # ── b) Bridge symlink valid ──────────────────────────────────────────────
    HOOK_PATH="/opt/Autodesk/shared/python/flame_mcp_bridge.py"
    HOOK_SRC="$SCRIPT_DIR/hooks/flame_mcp_bridge.py"
    if [ -e "$HOOK_PATH" ]; then
        if [ -L "$HOOK_PATH" ]; then
            LINK_TARGET="$(readlink "$HOOK_PATH")"
            if [ "$LINK_TARGET" = "$HOOK_SRC" ]; then
                doctor_pass "Bridge symlink: $HOOK_PATH -> $HOOK_SRC"
            else
                doctor_fail "Bridge symlink: points to $LINK_TARGET (expected $HOOK_SRC)"
                echo -e "         ${NC}Run: sudo ln -sf $HOOK_SRC $HOOK_PATH"
            fi
        else
            # Regular file, not a symlink — acceptable but less ideal
            doctor_warn "Bridge hook: $HOOK_PATH exists (regular file, not a symlink)"
            echo -e "         ${NC}Consider: sudo ln -sf $HOOK_SRC $HOOK_PATH"
        fi
    elif [ -d "/opt/Autodesk" ]; then
        doctor_fail "Bridge hook: $HOOK_PATH not found"
        echo -e "         ${NC}Run: sudo ln -sf $HOOK_SRC $HOOK_PATH"
    else
        doctor_skip "Bridge hook: /opt/Autodesk not found (Flame not installed on this machine)"
    fi

    # ── c) .env check ────────────────────────────────────────────────────────
    ENV_FILE="$SCRIPT_DIR/.env"
    if [ -f "$ENV_FILE" ]; then
        # Check for placeholder values
        if grep -qE '(your[-_]?key|PLACEHOLDER|CHANGEME|xxx|TODO)' "$ENV_FILE" 2>/dev/null; then
            doctor_warn ".env: exists but contains placeholder values"
            echo -e "         ${NC}Edit $ENV_FILE and set real values"
        else
            doctor_pass ".env: present with values configured"
        fi
    else
        doctor_fail ".env: file not found at $ENV_FILE"
        echo -e "         ${NC}Copy .env.example to .env and fill in your keys"
    fi

    # ── d) Venv importability ────────────────────────────────────────────────
    PYTHON_VENV="$SCRIPT_DIR/.venv/bin/python"
    if [ -x "$PYTHON_VENV" ]; then
        if "$PYTHON_VENV" -c "import flame_mcp" 2>/dev/null; then
            doctor_pass "Venv: 'import flame_mcp' succeeds"
        else
            doctor_fail "Venv: 'import flame_mcp' fails"
            echo -e "         ${NC}Run: source .venv/bin/activate && pip install -e . (or pip install -r requirements.txt)"
        fi
    else
        doctor_fail "Venv: .venv/bin/python not found"
        echo -e "         ${NC}Run: ./install.sh  (creates the virtual environment)"
    fi

    # ── e) RAG index present ─────────────────────────────────────────────────
    RAG_INDEX="$SCRIPT_DIR/rag/index"
    if [ -d "$RAG_INDEX" ]; then
        # Count non-hidden files (exclude .gitkeep)
        FILE_COUNT=$(find "$RAG_INDEX" -mindepth 1 -not -name '.*' -not -name '.gitkeep' | head -1)
        if [ -n "$FILE_COUNT" ]; then
            doctor_pass "RAG index: index files present in rag/index/"
        else
            doctor_warn "RAG index: rag/index/ is empty (no index built)"
            echo -e "         ${NC}Run: .venv/bin/python -m flame_mcp.rag.build_index"
        fi
    else
        doctor_warn "RAG index: rag/index/ directory not found"
        echo -e "         ${NC}Run: .venv/bin/python -m flame_mcp.rag.build_index"
    fi

    echo ""
    if [ "$WORST" -eq 0 ]; then
        echo -e "  ${GREEN}All checks passed.${NC}"
    else
        echo -e "  ${RED}Some checks failed. See remediation steps above.${NC}"
    fi
    echo ""
    exit "$WORST"
fi


# ── 1. Check Python 3.11+ ─────────────────────────────────────────────────────
# macOS ships python3 via Xcode CLT which may be 3.9.  Search for a newer
# versioned binary first (Homebrew, pyenv, system) before falling back.
info "Checking Python version..."

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11; do
    # Check Homebrew paths explicitly (not always in Flame's PATH)
    for prefix in /opt/homebrew/bin /usr/local/bin; do
        if [ -x "$prefix/$candidate" ]; then
            PYTHON_BIN="$prefix/$candidate"
            break 2
        fi
    done
    # Then check PATH
    if command -v "$candidate" &>/dev/null; then
        PYTHON_BIN="$(command -v "$candidate")"
        break
    fi
done

# Fallback: unversioned python3 (may be 3.9 on macOS)
if [ -z "$PYTHON_BIN" ]; then
    if command -v python3 &>/dev/null; then
        PYTHON_BIN="$(command -v python3)"
    else
        err "python3 not found. Install it with: brew install python@3.12"
    fi
fi

PYTHON_VERSION=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    err "Python 3.11+ required (found $PYTHON_VERSION at $PYTHON_BIN). Install with: brew install python@3.12"
fi
ok "Python $PYTHON_VERSION ($PYTHON_BIN)"

# ── 2. Check Claude Code ──────────────────────────────────────────────────────
info "Checking Claude Code..."
if ! command -v claude &>/dev/null; then
    err "Claude Code not found. Install it with: npm install -g @anthropic-ai/claude-code"
fi
CLAUDE_VERSION=$(claude --version 2>/dev/null | head -1)
ok "Claude Code: $CLAUDE_VERSION"

# ── 2b. Check Ollama (optional — for local/free inference) ───────────────────
info "Checking Ollama (optional)..."
if command -v ollama &>/dev/null; then
    OLLAMA_VERSION=$(ollama --version 2>/dev/null | head -1)
    ok "Ollama found: $OLLAMA_VERSION"
else
    warn "Ollama not found — skip if using Anthropic cloud models."
    warn "  macOS: brew install ollama && brew services start ollama"
    warn "  Linux: https://ollama.com/download/linux"
    warn "  See README.md → Ollama setup for details."
fi

# ── 3. Create virtual environment ────────────────────────────────────────────
info "Setting up Python virtual environment..."
if [ -d "$SCRIPT_DIR/.venv" ]; then
    warn "Virtual environment already exists, skipping creation."
else
    "$PYTHON_BIN" -m venv "$SCRIPT_DIR/.venv"
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
    info "To force a rebuild: python -m flame_mcp.rag.build_index"
else
    info "Building RAG documentation index..."
    info "(Downloads embedding model ~130 MB from HuggingFace on first run)"
    if "$PYTHON_VENV" -m flame_mcp.rag.build_index; then
        ok "RAG index built."
    else
        warn "RAG index build failed — search_flame_docs will show an error."
        warn "Fix with: source .venv/bin/activate && python -m flame_mcp.rag.build_index"
    fi
fi

# ── 7. Register MCP server with Claude Code ───────────────────────────────────
info "Registering MCP server with Claude Code..."

SERVER_SCRIPT="$SCRIPT_DIR/src/flame_mcp/server.py"

# Remove existing registration silently, then re-add
claude mcp remove flame 2>/dev/null || true
claude mcp add flame -- "$PYTHON_VENV" -m flame_mcp.server
ok "MCP server 'flame' registered with Claude Code."

# ── 8. Auto-approve MCP tools in Claude Code ──────────────────────────────────
# Writes tool permissions to ~/.claude/settings.json (user-level, permissions.allow).
# Claude Code reads this file globally — works from any project directory.
# Any future tool added to src/flame_mcp/server.py is auto-approved on next install.
info "Configuring Claude Code tool auto-approval..."

SERVER_SCRIPT="$SERVER_SCRIPT" "$PYTHON_VENV" - <<'PYEOF'
import ast, json, os
from pathlib import Path

server_script = os.environ['SERVER_SCRIPT']
settings_path = Path.home() / ".claude" / "settings.json"

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

# Merge with existing settings (preserves entries from other servers)
settings_path.parent.mkdir(parents=True, exist_ok=True)
settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text())
    except Exception:
        pass

settings.setdefault('permissions', {}).setdefault('allow', [])
existing = set(settings['permissions']['allow'])
new_set = set(new_tools)
new_count = len(new_set - existing)
merged = sorted(existing | new_set)
settings['permissions']['allow'] = merged

tmp = str(settings_path) + ".tmp"
with open(tmp, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
os.replace(tmp, str(settings_path))

print(f'[flame-mcp] {new_count} new tools pre-approved ({len(merged)} total in ~/.claude/settings.json)')
for t in sorted(new_set):
    print(f'    + {t}')
PYEOF

ok "Tool auto-approval configured — no permission prompts on first use."

# ── 9. Ollama server configuration (optional) ─────────────────────────────────
# Flame + this bridge run on THIS Mac.
# Ollama runs on a SEPARATE Linux machine (RTX 3090 etc.) on the same LAN.
# This step stores the Linux box's IP/port in config.json so the bridge can
# reach it. To set up the Linux machine itself, run setup_linux.sh there.
echo ""
echo -e "${YELLOW}─── Step 9: Ollama server setup (optional) ──────────────────────${NC}"
echo "  Ollama must be installed on your Linux machine, NOT on this Mac."
echo "  If you have (or plan to have) an Ollama server on your LAN, enter its"
echo "  address now. Leave blank to keep using Anthropic cloud models."
echo ""

CONFIG_FILE="$SCRIPT_DIR/config.json"

read -r -p "  Linux Ollama server address [e.g. 192.168.1.50:11434] (blank to skip): " OLLAMA_ADDR

if [ -n "$OLLAMA_ADDR" ]; then
    # Normalise: strip trailing slash, add http:// if missing
    OLLAMA_ADDR="${OLLAMA_ADDR%/}"
    [[ "$OLLAMA_ADDR" != http* ]] && OLLAMA_ADDR="http://$OLLAMA_ADDR"

    # Test reachability
    echo "  Testing connection to $OLLAMA_ADDR …"
    if curl -sf --max-time 2 "$OLLAMA_ADDR/api/version" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓ Ollama server reachable.${NC}"
    else
        echo -e "  ${YELLOW}⚠  Cannot reach $OLLAMA_ADDR right now.${NC}"
        echo "     Saving the URL anyway — you can start Ollama on Linux later."
        echo "     On the Linux machine:  OLLAMA_HOST=0.0.0.0 ollama serve"
    fi

    echo ""
    echo "  Recommended models by GPU VRAM on the Linux server:"
    echo "    ≥ 20 GB  →  qwen3-coder:30b-a3b  (~18 GB VRAM · ~60 tok/s · best quality)"
    echo "    ≥ 10 GB  →  qwen2.5-coder:14b    (~10 GB VRAM · ~80 tok/s)"
    echo "    ≥  6 GB  →  qwen2.5-coder:7b     ( ~5 GB VRAM · ~100 tok/s)"
    echo ""
    read -r -p "  Model to activate [default: qwen3-coder:30b-a3b]: " OLLAMA_MODEL
    OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3-coder:30b-a3b}"

    "$PYTHON_BIN" - <<PYEOF
import json, os
cfg_path = "$CONFIG_FILE"
cfg = {}
if os.path.exists(cfg_path):
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
    except Exception:
        pass
cfg['model']            = "$OLLAMA_MODEL"
cfg['backend']          = "ollama"
cfg['ollama_url']       = "$OLLAMA_ADDR"
if 'ollama_cloud_key' not in cfg:
    cfg['ollama_cloud_key'] = ""
os.makedirs(os.path.dirname(os.path.abspath(cfg_path)), exist_ok=True)
with open(cfg_path, 'w') as f:
    json.dump(cfg, f, indent=2)
print(f"  config.json → backend=ollama  model={cfg['model']}  ollama_url={cfg['ollama_url']}")
PYEOF

    ok "Ollama backend configured."
    echo ""
    echo "  To set up the Linux machine, copy setup_linux.sh and run it there:"
    echo "    scp $SCRIPT_DIR/setup_linux.sh user@<linux-ip>:~/"
    echo "    ssh user@<linux-ip> 'bash setup_linux.sh'"

else
    echo "  Skipped. Anthropic cloud models remain active."
    echo ""
    echo "  To configure Ollama later, edit $CONFIG_FILE:"
    echo '    "backend":    "ollama"'
    echo '    "ollama_url": "http://<linux-ip>:11434"'
    echo '    "model":      "qwen3-coder:30b-a3b"'
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
