#!/usr/bin/env bash
# setup_linux.sh
# ==============
# Run this on the Linux machine (Rocky 9 / Ubuntu / Debian) that will host
# the Ollama server for the Flame MCP bridge.
#
# What it does:
#   1. Installs Ollama (if not already present)
#   2. Detects GPU VRAM and recommends the right model
#   3. Creates a systemd service so Ollama starts on boot, listening on all
#      interfaces (0.0.0.0) so the Mac can reach it
#   4. Pulls the recommended model
#   5. Opens the firewall port (firewalld / ufw)
#   6. Prints the URL to paste into the Mac's install.sh
#
# Usage:
#   bash setup_linux.sh
#
# Requirements:
#   - NVIDIA GPU with drivers installed  (check: nvidia-smi)
#   - curl  (check: curl --version)
#   - systemd  (check: systemctl --version)
#
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}   $*"; }
fail() { echo -e "  ${RED}✗${NC}  $*" >&2; exit 1; }

echo ""
echo "================================================="
echo "  Flame MCP — Linux Ollama Server Setup"
echo "================================================="
echo ""

# ── 1. Detect GPU ─────────────────────────────────────────────────────────────
echo -e "${YELLOW}─── Step 1: GPU detection ───────────────────────────────────────${NC}"

VRAM_MB=0
GPU_NAME="(no NVIDIA GPU detected)"
if command -v nvidia-smi &>/dev/null 2>&1; then
    VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null \
              | head -1 | tr -d ' \r' || echo 0)
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | xargs)
    ok "GPU: $GPU_NAME  ($VRAM_MB MB VRAM)"
else
    warn "nvidia-smi not found. Install NVIDIA drivers before running models."
    VRAM_MB=0
fi

RAM_GB=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}' || echo 0)
echo "     RAM: ${RAM_GB} GB"

# Recommend model
if   [ "$VRAM_MB" -ge 20000 ] 2>/dev/null; then
    RECOMMENDED="qwen3-coder:30b"
    MODEL_INFO="~18 GB VRAM · ~60 tok/s · best quality for Flame scripting"
elif [ "$VRAM_MB" -ge 10000 ] 2>/dev/null; then
    RECOMMENDED="qwen2.5-coder:14b"
    MODEL_INFO="~10 GB VRAM · ~80 tok/s"
elif [ "$VRAM_MB" -ge  6000 ] 2>/dev/null; then
    RECOMMENDED="qwen2.5-coder:7b"
    MODEL_INFO="~5 GB VRAM · ~100 tok/s"
elif [ "$RAM_GB"  -ge    32 ] 2>/dev/null; then
    RECOMMENDED="qwen2.5-coder:7b"
    MODEL_INFO="CPU inference (slow — GPU strongly recommended)"
else
    warn "Insufficient resources detected. Proceeding anyway."
    RECOMMENDED="qwen2.5-coder:7b"
    MODEL_INFO="smallest available model"
fi

echo ""
echo "  Recommended model: $RECOMMENDED"
echo "  ($MODEL_INFO)"
echo ""
read -r -p "  Use $RECOMMENDED? Press Enter to confirm or type a different model: " MODEL_CHOICE
MODEL="${MODEL_CHOICE:-$RECOMMENDED}"

# ── 2. Install Ollama ─────────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}─── Step 2: Install Ollama ──────────────────────────────────────${NC}"

if command -v ollama &>/dev/null 2>&1; then
    OLLAMA_VER=$(ollama --version 2>/dev/null | head -1)
    ok "Ollama already installed: $OLLAMA_VER"
else
    echo "  Installing Ollama via official install script…"
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama installed."
fi

# ── 3. Configure systemd service to listen on all interfaces ──────────────────
echo ""
echo -e "${YELLOW}─── Step 3: Configure Ollama service ────────────────────────────${NC}"
echo "  Setting OLLAMA_HOST=0.0.0.0:11434 so the Mac can connect."
echo "  (Default Ollama only listens on 127.0.0.1)"

OVERRIDE_DIR="/etc/systemd/system/ollama.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/override.conf"

if sudo mkdir -p "$OVERRIDE_DIR" && sudo tee "$OVERRIDE_FILE" > /dev/null <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
then
    ok "Systemd override written: $OVERRIDE_FILE"
else
    warn "Could not write systemd override (permission denied?)."
    warn "Set this manually in /etc/systemd/system/ollama.service.d/override.conf"
fi

# Reload & restart service
if systemctl is-active --quiet ollama 2>/dev/null || systemctl is-enabled --quiet ollama 2>/dev/null; then
    sudo systemctl daemon-reload
    sudo systemctl restart ollama
    ok "Ollama service restarted."
else
    sudo systemctl daemon-reload
    sudo systemctl enable --now ollama 2>/dev/null || true
    ok "Ollama service enabled and started."
fi

# Wait for Ollama to be ready
echo "  Waiting for Ollama to start…"
for i in $(seq 1 10); do
    if curl -sf --max-time 1 "http://localhost:11434/api/version" >/dev/null 2>&1; then
        ok "Ollama is running."
        break
    fi
    sleep 1
done

# ── 4. Pull model ─────────────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}─── Step 4: Pull model ──────────────────────────────────────────${NC}"

ESTIMATED_SIZE="~18 GB"
[ "$MODEL" = "qwen2.5-coder:14b" ] && ESTIMATED_SIZE="~10 GB"
[ "$MODEL" = "qwen2.5-coder:7b"  ] && ESTIMATED_SIZE=" ~5 GB"

read -r -p "  Pull $MODEL now? ($ESTIMATED_SIZE download) [Y/n] " pull_ans
if [[ ! "$pull_ans" =~ ^[Nn]$ ]]; then
    echo "  Running: ollama pull $MODEL"
    ollama pull "$MODEL"
    ok "Model '$MODEL' downloaded and ready."
else
    echo "  Skipped. Pull it later with:  ollama pull $MODEL"
fi

# ── 5. Open firewall port ─────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}─── Step 5: Firewall ────────────────────────────────────────────${NC}"

if command -v firewall-cmd &>/dev/null 2>&1; then
    # firewalld (Rocky 9 / RHEL / CentOS)
    if sudo firewall-cmd --query-port=11434/tcp --permanent 2>/dev/null | grep -q yes; then
        ok "Port 11434/tcp already open in firewalld."
    else
        sudo firewall-cmd --add-port=11434/tcp --permanent
        sudo firewall-cmd --reload
        ok "Port 11434/tcp opened in firewalld."
    fi
elif command -v ufw &>/dev/null 2>&1; then
    # ufw (Ubuntu / Debian)
    sudo ufw allow 11434/tcp
    ok "Port 11434/tcp allowed in ufw."
else
    warn "No firewall tool found (firewall-cmd / ufw). Open port 11434/tcp manually."
fi

# ── 6. Summary ────────────────────────────────────────────────────────────────
echo ""
# Get local IP (first non-loopback IPv4)
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || ip route get 1 2>/dev/null | awk '{print $NF;exit}')
LOCAL_IP="${LOCAL_IP:-<this-machine-ip>}"

echo "================================================="
echo -e "  ${GREEN}Setup complete!${NC}"
echo "================================================="
echo ""
echo "  Ollama is running and accepting connections."
echo "  Model: $MODEL"
echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  URL to enter on the Mac during install.sh  │"
echo "  │                                             │"
echo -e "  │  ${GREEN}http://$LOCAL_IP:11434${NC}                     │"
echo "  │                                             │"
echo "  └─────────────────────────────────────────────┘"
echo ""
echo "  Or update config.json on the Mac manually:"
echo '    "backend":    "ollama"'
echo "    \"ollama_url\": \"http://$LOCAL_IP:11434\""
echo "    \"model\":      \"$MODEL\""
echo ""
echo "  Test from the Mac:"
echo "    curl http://$LOCAL_IP:11434/api/version"
echo ""
echo "  Reboot check:"
echo "    sudo systemctl status ollama"
echo ""
