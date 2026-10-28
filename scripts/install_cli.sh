#!/usr/bin/env bash
# =============================================================================
#  install_cli.sh
#  Installs and configures the `mastro` CLI of the MASTRO platform.
#
#  The CLI is a standalone HTTP client: it does not start any server, it talks
#  REST to the MASTRO backend. This script:
#    1. Creates a dedicated virtual-env (independent of the orchestrator venv)
#    2. Installs the `mastro` command and its dependencies (httpx)
#    3. Asks which port the backend listens on and stores it permanently
#    4. Makes `mastro` callable from any shell (~/.local/bin)
#    5. Checks that the backend is reachable and starts the CLI
#
#  Usage:
#    chmod +x scripts/install_cli.sh
#    ./scripts/install_cli.sh
#
#  The port can also be passed non-interactively:
#    ./scripts/install_cli.sh --port 9100
#
#  The Orchestrator backend URL (default http://127.0.0.1:9000) can be changed later with:
#    mastro config set-orchestrator-url http://HOST:9000
# =============================================================================
set -euo pipefail

# ── Colours and helpers ───────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ── Project directory ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find the project root by walking up the directories until cli/mastro_cli.py
# is found, so the script works regardless of where it sits in the tree.
find_project_root() {
  local d="$1"
  while [ "$d" != "/" ]; do
    if [ -f "$d/cli/mastro_cli.py" ]; then
      echo "$d"; return 0
    fi
    d="$(dirname "$d")"
  done
  return 1
}

PROJECT_ROOT="$(find_project_root "$SCRIPT_DIR")" || \
  fail "MASTRO project root not found walking up from $SCRIPT_DIR (looking for cli/mastro_cli.py). Run the script from inside the project tree."
CLI_DIR="$PROJECT_ROOT/cli"

MASTRO_HOME="$HOME/.mastro"
VENV_DIR="$MASTRO_HOME/venv"
BIN_DIR="$HOME/.local/bin"
WRAPPER="$BIN_DIR/mastro"

DEFAULT_HOST="127.0.0.1"
DEFAULT_PORT="9100"

# ── Argument parsing (optional non-interactive port) ──────────────────────────
PORT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="${2:-}"; shift 2 ;;
    --port=*) PORT="${1#*=}"; shift ;;
    -h|--help)
      echo "Usage: $0 [--port PORT]"
      exit 0 ;;
    *) fail "Unrecognized argument: $1" ;;
  esac
done

# ── 0. Prerequisites ──────────────────────────────────────────────────────────
info "Checking prerequisites..."
command -v python3 >/dev/null 2>&1 || fail "python3 not found. Install it before proceeding."
[ -f "$CLI_DIR/mastro_cli.py" ] || fail "CLI not found in $CLI_DIR — run the script from the MASTRO project root."

# Check that the venv module is really available (on Debian/Ubuntu/WSL it is
# a separate package: without it, `python3 -m venv` creates an incomplete dir).
if ! python3 -m venv --help >/dev/null 2>&1 || ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  PYV="$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 3)"
  fail "The Python 'venv' module is not available.
       Install it (Debian/Ubuntu/WSL) with:
         sudo apt update && sudo apt install -y python3-venv python${PYV}-venv python3-pip
       then run this script again."
fi
ok "Prerequisites satisfied (CLI: $CLI_DIR)."

# ── 1. Dedicated virtual-env for the CLI ──────────────────────────────────────
# A venv is valid only if it contains a working pip: we really check it,
# and recreate from scratch a pre-existing but broken venv.
venv_is_healthy() {
  [ -x "$VENV_DIR/bin/python" ] && "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1
}

if venv_is_healthy; then
  warn "CLI virtual-env already present and working in $VENV_DIR — reusing it."
else
  if [ -e "$VENV_DIR" ]; then
    warn "Existing virtual-env in $VENV_DIR is incomplete or broken — recreating it."
    rm -rf "$VENV_DIR"
  fi
  info "Creating dedicated virtual-env in $VENV_DIR ..."
  if ! python3 -m venv "$VENV_DIR"; then
    rm -rf "$VENV_DIR"
    fail "Virtual-env creation failed (see the error above)."
  fi
  # Check that the venv is actually complete (pip present).
  if ! venv_is_healthy; then
    rm -rf "$VENV_DIR"
    PYV="$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 3)"
    fail "Venv created but without a working pip. The system venv package is missing:
       sudo apt update && sudo apt install -y python3-venv python${PYV}-venv python3-pip
       then run this script again."
  fi
  ok "Virtual-env created and verified."
fi

# ── 2. Installing the `mastro` command ───────────────────────────────────────
# No error suppression: if something goes wrong we show the pip log.
info "Installing the CLI and its dependencies (httpx)..."
PIP="$VENV_DIR/bin/pip"
PIP_LOG="$(mktemp)"
if ! "$PIP" install --upgrade pip >"$PIP_LOG" 2>&1 || ! "$PIP" install -e "$PROJECT_ROOT" "$CLI_DIR" >>"$PIP_LOG" 2>&1; then
  echo "----- pip output --------"; cat "$PIP_LOG"; echo "-------------------------"
  rm -f "$PIP_LOG"
  fail "CLI installation failed (see the pip output above)."
fi
rm -f "$PIP_LOG"
if [ -f "$PROJECT_ROOT/orchestrator/requirements.txt" ]; then
  "$PIP" install -r "$PROJECT_ROOT/orchestrator/requirements.txt"
fi

# Real check: the command must exist AND run, the file alone is not enough.
if [ ! -x "$VENV_DIR/bin/mastro" ] || ! "$VENV_DIR/bin/mastro" --help >/dev/null 2>&1; then
  fail "Installation completed but 'mastro' is not executable in $VENV_DIR/bin/."
fi
ok "'mastro' command installed and verified."

# ── 3. Choosing the backend port ──────────────────────────────────────────────
if [ -z "$PORT" ]; then
  echo ""
  read -rp "Which port is the MASTRO backend listening on? [${DEFAULT_PORT}]: " PORT
  PORT="${PORT:-$DEFAULT_PORT}"
fi

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  fail "Invalid port: '$PORT' (expected a number between 1 and 65535)."
fi

BACKEND_URL="http://${DEFAULT_HOST}:${PORT}"
info "Configuring the CLI for the backend: $BACKEND_URL"
"$VENV_DIR/bin/mastro" config set-url "$BACKEND_URL" >/dev/null
ok "Port $PORT saved in $MASTRO_HOME/config.json"
info "(to point to a different host: mastro config set-url http://HOST:$PORT)"
info "(Orchestrator backend: mastro config set-orchestrator-url http://HOST:9000, default http://127.0.0.1:9000)"

# ── 4. Make `mastro` available in PATH ──────────────
mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/mastro" "$WRAPPER"
# Check that the link really points to an executable (no silent broken links).
if [ ! -x "$WRAPPER" ] || ! "$WRAPPER" --help >/dev/null 2>&1; then
  fail "Invalid link $WRAPPER. Use directly: $VENV_DIR/bin/mastro"
fi
ok "Links created and verified: $WRAPPER -> $VENV_DIR/bin/mastro"

if echo ":$PATH:" | grep -q ":$BIN_DIR:"; then
  ok "$BIN_DIR is already in PATH — 'mastro' can be used right away."
else
  PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
  RC=""
  case "${SHELL:-}" in
    *zsh) RC="$HOME/.zshrc" ;;
    *)    RC="$HOME/.bashrc" ;;
  esac
  warn "$BIN_DIR is not in PATH, so the shell cannot find 'mastro' yet."
  ADD=""
  read -rp "Add the line to your ${RC} automatically? [y/N]: " ADD || ADD=""
  if [[ "$ADD" =~ ^[sSyY]$ ]]; then
    if [ -f "$RC" ] && grep -qF "$PATH_LINE" "$RC"; then
      ok "Line already present in $RC."
    else
      printf '\n# Added by install_cli.sh (MASTRO CLI)\n%s\n' "$PATH_LINE" >> "$RC"
      ok "Added to $RC."
    fi
    warn "Open a new shell or run:  source $RC"
  else
    warn "Add this line manually to $RC (or ~/.zshrc):"
    echo -e "       ${CYAN}${PATH_LINE}${NC}"
    warn "For this session, enable it right away with:  export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi
fi

# ── 5. Check and start the CLI ────────────────────────────────────────────────
echo ""
info "Checking backend reachability..."
if "$VENV_DIR/bin/mastro" --timeout 5 agent list >/dev/null 2>&1; then
  ok "Backend reachable at $BACKEND_URL"
else
  warn "Backend not reachable right now at $BACKEND_URL."
  warn "Start it with ./scripts/start.sh — the port stays configured."
fi

echo ""
info "Active CLI configuration:"
"$VENV_DIR/bin/mastro" config show

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  'mastro' CLI ready!${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo -e "  Configured backend:   ${CYAN}${BACKEND_URL}${NC}"
echo ""
echo -e "  Useful commands:"
echo -e "    ${CYAN}mastro --help${NC}              — list of commands"
echo -e "    ${CYAN}mastro status${NC}              — aggregated system status"
echo -e "    ${CYAN}mastro agent list${NC}          — configured agents"
echo -e "    ${CYAN}mastro intent \"...\" --agent <id>${NC} — send a natural-language intent"
echo ""
echo -e "  To change the port later:"
echo -e "    ${CYAN}mastro config set-url http://${DEFAULT_HOST}:<port>${NC}"
echo -e "    or run this script again (${CYAN}install_cli.sh${NC})"
echo ""
