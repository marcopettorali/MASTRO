#!/usr/bin/env bash
# =============================================================================
#  start.sh
#  Starts the MASTRO backend (port 9100) and frontend (port 5174).
#
#  The orchestrator/ adapter provides the infrastructure connection.
#
#  Usage:
#    ./scripts/start.sh
#    ORCHESTRATOR_URL=http://orchestrator-host:9000 ./scripts/start.sh
#
#  Press Ctrl+C to stop both processes.
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

VENV_DIR="$PROJECT_ROOT/venv"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_PORT=9100
export MASTRO_URL="http://127.0.0.1:$BACKEND_PORT"   # used by the MCP Gateway to reach this backend

[ -f "$VENV_DIR/bin/activate" ] || fail "Virtual-env not found. Run first: ./scripts/install.sh"
[ -d "$FRONTEND_DIR/node_modules" ] || fail "node_modules missing. Run first: ./scripts/install.sh"

[ -f config/agents.json ]       || warn "config/agents.json not found — no agent configured (Settings → Agents & Skills)."
[ -f config/llm_settings.json ] || warn "config/llm_settings.json not found — configure the LLM endpoint (Settings → LLM Settings)."

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  echo ""
  info "Stopping the processes..."
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null
  wait 2>/dev/null
  ok "All processes terminated."
}
trap cleanup EXIT INT TERM

info "Starting backend (uvicorn, port $BACKEND_PORT)..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
uvicorn backend.app:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!

for i in $(seq 1 20); do
  if curl -s "http://127.0.0.1:$BACKEND_PORT/api/ping" > /dev/null 2>&1; then
    ok "Backend ready at http://127.0.0.1:$BACKEND_PORT"
    break
  fi
  [ "$i" -eq 20 ] && warn "Backend did not answer within 20s — it may still be starting."
  sleep 1
done

info "Starting frontend (Vite dev server, port 5174)..."
(cd "$FRONTEND_DIR" && npm run dev) &
FRONTEND_PID=$!

sleep 2
echo ""
echo -e "${GREEN}  MASTRO started${NC}"
echo -e "  Frontend:  ${CYAN}http://localhost:5174${NC}"
echo -e "  Backend:   ${CYAN}http://localhost:$BACKEND_PORT${NC}"
echo -e "  Adapter:   ${CYAN}orchestrator/${NC}"
echo ""
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop."

wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
