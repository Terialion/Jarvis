#!/usr/bin/env bash
# Jarvis one-command install script (Linux/macOS).
#
# Usage: curl -fsSL https://raw.githubusercontent.com/terialion/jarvis/main/scripts/install.sh | bash
#    or: gh repo clone terialion/jarvis && cd jarvis && bash scripts/install.sh
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[jarvis]${NC} $*"; }
warn() { echo -e "${RED}[jarvis]${NC} $*"; }

JARVIS_ROOT="${JARVIS_ROOT:-$HOME/.jarvis}"
REPO_URL="${REPO_URL:-https://github.com/terialion/jarvis.git}"

# ── Detect platform ───────────────────────────────────────────
case "$(uname -s)" in
    Linux*)  PLATFORM=linux ;;
    Darwin*) PLATFORM=macos ;;
    *) warn "Unsupported platform: $(uname -s)"; exit 1 ;;
esac

# ── Check prerequisites ───────────────────────────────────────
log "Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
    warn "Python 3.11+ required. Install it first: https://python.org/downloads/"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if [ "$(echo "$PY_VERSION >= 3.11" | bc -l 2>/dev/null || echo 0)" = "0" ]; then
    warn "Python 3.11+ required (found $PY_VERSION)"
    exit 1
fi
log "Python $PY_VERSION ✓"

HAS_NODE=false
if command -v node &>/dev/null; then
    NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
    if [ "$NODE_VERSION" -ge 18 ]; then
        HAS_NODE=true
        log "Node.js $(node -v) ✓"
    fi
fi
if [ "$HAS_NODE" = false ]; then
    log "Node.js 18+ not found — TUI mode will be unavailable. Install nodejs for best experience."
fi

# ── Clone or use existing repo ─────────────────────────────────
if [ -d "$JARVIS_ROOT" ]; then
    log "Using existing Jarvis at $JARVIS_ROOT"
    cd "$JARVIS_ROOT"
    git pull --ff-only 2>/dev/null || true
else
    log "Cloning Jarvis to $JARVIS_ROOT..."
    git clone "$REPO_URL" "$JARVIS_ROOT"
    cd "$JARVIS_ROOT"
fi

# ── Python setup ──────────────────────────────────────────────
log "Setting up Python virtual environment..."
python3 -m venv .venv

# shellcheck disable=SC1091
source .venv/bin/activate

log "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -e ".[dev]" -q

# ── Node.js setup (TUI) ──────────────────────────────────────
if [ "$HAS_NODE" = true ]; then
    log "Installing TUI dependencies..."
    cd "$JARVIS_ROOT/jarvis_tui"
    npm install --silent 2>/dev/null || npm install
    cd "$JARVIS_ROOT"
fi

# ── Shell integration ─────────────────────────────────────────
SHELL_RC=""
case "$SHELL" in
    */bash) SHELL_RC="$HOME/.bashrc" ;;
    */zsh)  SHELL_RC="$HOME/.zshrc" ;;
    */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
    *)      SHELL_RC="$HOME/.profile" ;;
esac

# Ensure .local/bin is in PATH
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

# Create jarvis launcher
cat > "$LOCAL_BIN/jarvis" << LAUNCHER
#!/usr/bin/env bash
cd "$JARVIS_ROOT" && source .venv/bin/activate && python -m jarvis "\$@"
LAUNCHER
chmod +x "$LOCAL_BIN/jarvis"

if ! echo "$PATH" | grep -q "$LOCAL_BIN"; then
    echo "export PATH=\"$LOCAL_BIN:\$PATH\"" >> "$SHELL_RC"
    log "Added $LOCAL_BIN to PATH in $SHELL_RC"
fi

# ── Configure ─────────────────────────────────────────────────
if [ ! -f "$JARVIS_ROOT/.env" ]; then
    log ""
    log "Configuration: Create $JARVIS_ROOT/.env with:"
    echo "  JARVIS_LLM_API_KEY=sk-your-key"
    echo "  JARVIS_LLM_PROVIDER=deepseek"
    echo "  JARVIS_LLM_MODEL=deepseek-v4-pro"
fi

# ── Done ──────────────────────────────────────────────────────
log ""
echo -e "${GREEN}Jarvis installed successfully!${NC}"
echo ""
echo "  Run:   jarvis"
echo "  TUI:   jarvis --tui"
echo ""
if [ -f "$SHELL_RC" ]; then
    echo "  Restart your shell or run: source $SHELL_RC"
fi
