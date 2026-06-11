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
#   ./install.sh -d         # short form of --doctor
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

# ── --doctor / -d: health check subcommand ───────────────────────────────────
# Usage: ./install.sh --doctor   OR   ./install.sh -d
#
# Runs 5 independent checks using an inline Python script with the same
# visual format as maya-mcp and fpt-mcp:
#   1. MCP registration in claude.json
#   2. Bridge symlink to /opt/Autodesk/shared/python/
#   3. .env file with real values
#   4. Venv importability (import flame_mcp)
#   5. RAG index presence
#
# 4-state severity: PASS=0, SKIP=1, WARN=2, FAIL=3
# Exit code: 0 on PASS/WARN/SKIP, 1 on any FAIL.
# ─────────────────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--doctor" ] || [ "${1:-}" = "-d" ]; then
    PYTHON_VENV="$SCRIPT_DIR/.venv/bin/python"
    if [ ! -x "$PYTHON_VENV" ]; then
        echo ""
        echo -e "\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
        echo -e "\033[1m  flame-mcp — doctor\033[0m"
        echo -e "\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
        echo ""
        echo -e "  \033[0;31m✗\033[0m Venv is missing: $PYTHON_VENV"
        echo -e "    Run './install.sh' to create it."
        echo ""
        exit 1
    fi

    "$PYTHON_VENV" - "$SCRIPT_DIR" "$HOME/.claude.json" <<'PYEOF'
"""
Doctor implementation — flame-mcp
Each check returns (status, message) where status is PASS/FAIL/WARN/SKIP.
Visual format aligned with maya-mcp and fpt-mcp ecosystem.
"""
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(sys.argv[1])
CLAUDE_JSON = Path(sys.argv[2])

RESET = "\033[0m"
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"


def _symbol(status: str) -> str:
    return {
        "PASS": f"{GREEN}✓{RESET}",
        "FAIL": f"{RED}✗{RESET}",
        "WARN": f"{YELLOW}⚠{RESET}",
        "SKIP": f"{CYAN}·{RESET}",
    }[status]


# ── Check 1: MCP registration ───────────────────────────────────────────────
def check_claude_json() -> tuple[str, str]:
    mcp_json = REPO_ROOT / ".mcp.json"
    for cfg_path in [mcp_json, CLAUDE_JSON]:
        if not cfg_path.is_file():
            continue
        try:
            data = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            continue
        servers = data.get("mcpServers", {})
        if "flame" in servers or "flame-mcp" in servers:
            return ("PASS", f"flame-mcp found in {cfg_path.name}")
    return (
        "FAIL",
        "flame-mcp NOT found in .mcp.json or ~/.claude.json. "
        "Run: claude mcp add flame -- \"$(pwd)/.venv/bin/python\" -m flame_mcp.server",
    )


# ── Check 2: Bridge symlink ─────────────────────────────────────────────────
def check_bridge_symlink() -> tuple[str, str]:
    hook_path = Path("/opt/Autodesk/shared/python/flame_mcp_bridge.py")
    hook_src = REPO_ROOT / "hooks" / "flame_mcp_bridge.py"
    if hook_path.exists():
        if hook_path.is_symlink():
            target = Path(os.readlink(str(hook_path)))
            if target == hook_src:
                return ("PASS", f"{hook_path} -> {hook_src}")
            return (
                "FAIL",
                f"Symlink points to {target} (expected {hook_src}). "
                f"Run: sudo ln -sf {hook_src} {hook_path}",
            )
        # Regular file, not a symlink
        return (
            "WARN",
            f"{hook_path} exists as a regular file, not a symlink. "
            f"Consider: sudo ln -sf {hook_src} {hook_path}",
        )
    if Path("/opt/Autodesk").is_dir():
        return (
            "FAIL",
            f"{hook_path} not found. "
            f"Run: sudo ln -sf {hook_src} {hook_path}",
        )
    return (
        "SKIP",
        "/opt/Autodesk not found (Flame not installed on this machine)",
    )


# ── Check 3: .env file ──────────────────────────────────────────────────────
def check_env_file() -> tuple[str, str]:
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return (
            "FAIL",
            f".env not found at {env_file}. "
            f"Copy .env.example to .env and fill in your keys.",
        )
    content = env_file.read_text(errors="replace")
    placeholder_patterns = [
        r"your[-_]?key",
        r"PLACEHOLDER",
        r"CHANGEME",
        r"xxx",
        r"TODO",
    ]
    for pat in placeholder_patterns:
        if re.search(pat, content, re.IGNORECASE):
            return (
                "WARN",
                f".env exists but contains placeholder values. "
                f"Edit {env_file} and set real values.",
            )
    return ("PASS", f".env present with values configured")


# ── Check 4: Venv importability ──────────────────────────────────────────────
def check_venv_import() -> tuple[str, str]:
    try:
        import flame_mcp  # noqa: F401
    except Exception as exc:
        return (
            "FAIL",
            f"'import flame_mcp' fails: {type(exc).__name__}: {exc}. "
            f"Run: source .venv/bin/activate && pip install -e . "
            f"(or pip install -r requirements.txt)",
        )
    return ("PASS", "'import flame_mcp' succeeds from venv")


# ── Check 5: RAG index ──────────────────────────────────────────────────────
def check_rag_index() -> tuple[str, str]:
    rag_index = REPO_ROOT / "rag" / "index"
    if not rag_index.is_dir():
        return (
            "WARN",
            f"rag/index/ directory not found. "
            f"Run: .venv/bin/python -m flame_mcp.rag.build_index",
        )
    # Check for non-hidden files (exclude .gitkeep)
    contents = [
        f for f in rag_index.iterdir()
        if not f.name.startswith(".") and f.name != ".gitkeep"
    ]
    if not contents:
        return (
            "WARN",
            f"rag/index/ is empty (no index built). "
            f"Run: .venv/bin/python -m flame_mcp.rag.build_index",
        )
    return ("PASS", "RAG index files present in rag/index/")


# ── Run all checks ──────────────────────────────────────────────────────────
CHECKS = [
    ("MCP registration", check_claude_json),
    ("Bridge symlink", check_bridge_symlink),
    (".env file", check_env_file),
    ("Venv importability", check_venv_import),
    ("RAG index", check_rag_index),
]


def main() -> int:
    print("")
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print(f"{BOLD}  flame-mcp — doctor{RESET}")
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print("")

    worst = "PASS"
    rank = {"PASS": 0, "SKIP": 1, "WARN": 2, "FAIL": 3}

    for i, (label, fn) in enumerate(CHECKS, start=1):
        try:
            status, msg = fn()
        except Exception as exc:
            status, msg = "FAIL", f"check raised {type(exc).__name__}: {exc}"
        print(f"  {_symbol(status)} [{i}/{len(CHECKS)}] {BOLD}{label}{RESET}: {msg}")
        if rank[status] > rank[worst]:
            worst = status

    print("")
    if worst == "PASS":
        print(f"{GREEN}{BOLD}All checks passed — install is ready.{RESET}")
        return 0
    if worst in ("WARN", "SKIP"):
        print(f"{YELLOW}{BOLD}Install is usable but has warnings — review above.{RESET}")
        return 0
    print(f"{RED}{BOLD}Install is incomplete — fix the FAIL items above.{RESET}")
    return 1


sys.exit(main())
PYEOF
    exit $?
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
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
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
# reach it. To set up the Linux machine itself, run scripts/setup_ollama_linux.sh there.
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
    # concept:ollama_gpu_models_install start
    echo '  Models exposed by AVAILABLE_MODELS (hooks/flame_mcp_bridge.py):'
    echo '    `qwen3.5-mcp`       -  Qwen3.5 9B (alias of qwen3.5:9b, ~6.6 GB VRAM Q4_K_M)'
    echo '    `qwen3.5:4b`        -  Qwen3.5 4B (~2.5 GB Q4_K_M, small-GPU fallback)'
    echo '    `glm-4.7-flash`     -  GLM-4.7 Flash (NOT recommended — tool-calling broken in Ollama as of June 2026, issues #13820/#13840)'
    # concept:ollama_gpu_models_install end
    echo ""
    echo "  Pull commands on the Linux server (scripts/setup_ollama_linux.sh automates this):"
    echo "    ollama pull qwen3.5:9b && ollama cp qwen3.5:9b qwen3.5-mcp  # recommended (10+ GB VRAM)"
    echo "    ollama pull qwen3.5:4b                                        # small-GPU fallback (4+ GB VRAM)"
    echo "    # ollama pull glm-4.7-flash  (NOT recommended — tool-calling broken in Ollama as of June 2026)"
    echo ""
    read -r -p "  Model to activate [default: qwen3.5-mcp]: " OLLAMA_MODEL
    OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.5-mcp}"

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
    echo "  To set up the Linux machine, copy scripts/setup_ollama_linux.sh and run it there:"
    echo "    scp $SCRIPT_DIR/scripts/setup_ollama_linux.sh user@<linux-ip>:~/"
    echo "    ssh user@<linux-ip> 'bash setup_ollama_linux.sh'"

else
    echo "  Skipped. Anthropic cloud models remain active."
    echo ""
    echo "  To configure Ollama later, edit $CONFIG_FILE:"
    echo '    "backend":    "ollama"'
    echo '    "ollama_url": "http://<linux-ip>:11434"'
    echo '    "model":      "qwen3.5-mcp"'
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
