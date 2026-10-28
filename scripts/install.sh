#!/usr/bin/env bash
# =============================================================================
#  install.sh
#  Installs MASTRO (agentic layer) on the local machine.
#
#  The replaceable orchestrator/ adapter supplies infrastructure integration.
#
#  Steps:
#    1. Creates the default configuration files (if missing)
#    2. Creates a Python virtual-env and installs the dependencies
#    3. Installs the npm dependencies of the React frontend
#
#  Usage:
#    ./scripts/install.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
info "Project directory: $PROJECT_ROOT"

# ── 0. Prerequisites ──────────────────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || fail "python3 not found. Install it before proceeding."
command -v node    >/dev/null 2>&1 || fail "node not found. Install Node.js >= 18 before proceeding."
command -v npm     >/dev/null 2>&1 || fail "npm not found. Install npm before proceeding."
ok "Prerequisites satisfied (Python $(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'), Node.js $(node --version))."

# ── 1. Default configuration files ────────────────────────────────────────────
mkdir -p config

if [ ! -f config/llm_settings.json ]; then
  cat > config/llm_settings.json <<'JSON'
{
  "base_url": "http://localhost:11434/v1",
  "model": "qwen2.5:32b",
  "api_key": "ollama",
  "temperature": 0.2,
  "max_tokens": 2048,
  "timeout_s": 120
}
JSON
  info "Created config/llm_settings.json (default: local Ollama)"
fi

if [ ! -f config/mongodb.json ]; then
  cat > config/mongodb.json <<'JSON'
{
  "uri": "",
  "database": "mastro_agent"
}
JSON
  info "Created config/mongodb.json (empty URI = in-memory only)"
fi
ok "Configuration files ready."

# ── 2. Python virtual-env and dependencies ────────────────────────────────────
VENV_DIR="$PROJECT_ROOT/venv"
if [ -f "$VENV_DIR/bin/activate" ]; then
  warn "Virtual-env already present in $VENV_DIR — skipping creation."
else
  info "Creating Python virtual-env in $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet
info "Installing Python dependencies (requirements.txt)..."
pip install -r "$PROJECT_ROOT/requirements.txt" --quiet
pip install -e "$PROJECT_ROOT" --quiet
if [ -f "$PROJECT_ROOT/orchestrator/requirements.txt" ]; then
  pip install -r "$PROJECT_ROOT/orchestrator/requirements.txt" --quiet
fi
python -m orchestrator init-config "$PROJECT_ROOT/config"
deactivate
ok "Python dependencies installed."

# ── 3. Frontend dependencies ──────────────────────────────────────────────────
info "Installing frontend npm dependencies..."
(cd "$PROJECT_ROOT/frontend" && npm install --silent)
ok "npm dependencies installed."

echo ""
echo -e "${GREEN}  MASTRO installed.${NC}"
echo ""
echo -e "  Start it with:  ${CYAN}./scripts/start.sh${NC}"
echo -e "  Configure and start the managed infrastructure as described in orchestrator/README.md."
echo ""
