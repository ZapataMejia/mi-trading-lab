#!/usr/bin/env bash
# Mi Trading Lab — arranque local (tu Mac, $0)
# Hermana en otro país: instala Tailscale (ver webapp/USO_REMOTO.md)
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔═══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Mi Trading Lab — modo local         ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════╝${NC}"
echo ""

if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ Falta .venv — corre: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt${NC}"
    exit 1
fi
if [ ! -d "webapp/frontend/node_modules" ]; then
    echo -e "${YELLOW}⚠  Instalando dependencias del frontend...${NC}"
    (cd webapp/frontend && npm install)
fi

# Orígenes CORS (localhost + WiFi + Tailscale remoto)
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "")"
TS_IP=""
TS_NAME=""
if command -v tailscale >/dev/null 2>&1; then
    TS_IP="$(tailscale ip -4 2>/dev/null || true)"
    TS_NAME="$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Self',{}).get('DNSName','').rstrip('.'))" 2>/dev/null || true)"
fi

ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
[ -n "$LAN_IP" ] && ORIGINS="${ORIGINS},http://${LAN_IP}:3000"
[ -n "$TS_IP" ] && ORIGINS="${ORIGINS},http://${TS_IP}:3000"
[ -n "$TS_NAME" ] && ORIGINS="${ORIGINS},http://${TS_NAME}:3000"
export ALLOWED_ORIGINS="$ORIGINS"

free_port() {
    local PORT=$1
    local PIDS
    PIDS=$(lsof -ti :"$PORT" 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo -e "${YELLOW}⚠  Puerto $PORT ocupado — liberando${NC}"
        kill -9 $PIDS 2>/dev/null || true
        sleep 1
    fi
}
free_port 8000
free_port 3000

mkdir -p webapp/logs
BACKEND_LOG="webapp/logs/backend.log"
FRONTEND_LOG="webapp/logs/frontend.log"
: > "$BACKEND_LOG"
: > "$FRONTEND_LOG"

cleanup() {
    echo ""
    echo -e "${YELLOW}Apagando lab...${NC}"
    [ -n "${BACKEND_PID:-}" ] && kill $BACKEND_PID 2>/dev/null || true
    [ -n "${FRONTEND_PID:-}" ] && kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

echo -e "${GREEN}▶ Backend${NC} (puerto 8000)"
# shellcheck disable=SC1091
source .venv/bin/activate
uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 --reload >> "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

for _ in {1..30}; do
    curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
    sleep 0.5
done
if ! curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo -e "${RED}❌ Backend no arrancó — ver webapp/logs/backend.log${NC}"
    tail -20 "$BACKEND_LOG"
    cleanup
fi
echo -e "${GREEN}  ✓ Backend listo${NC}"

echo -e "${GREEN}▶ Frontend${NC} (puerto 3000)"
(cd webapp/frontend && npm run dev -- --hostname 0.0.0.0 >> "../../$FRONTEND_LOG" 2>&1) &
FRONTEND_PID=$!

for _ in {1..40}; do
    curl -sf -o /dev/null http://127.0.0.1:3000 2>/dev/null && break
    sleep 0.5
done
echo -e "${GREEN}  ✓ Frontend listo${NC}"

SIM_URL="http://localhost:3000/fondeo/liquidity-sweep"
sleep 1
open "$SIM_URL"

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Lab corriendo (gratis, en tu Mac)${NC}"
echo ""
echo -e "  Tú:  ${BLUE}${SIM_URL}${NC}"

if [ -n "$TS_IP" ]; then
    REMOTE="http://${TS_IP}:3000/fondeo/liquidity-sweep"
    echo -e "  Hermana (otro país, Tailscale): ${BLUE}${REMOTE}${NC}"
    [ -n "$TS_NAME" ] && echo -e "  También: ${BLUE}http://${TS_NAME}:3000/fondeo/liquidity-sweep${NC}"
    echo -e "  ${YELLOW}→ Ella debe tener Tailscale encendido. Guía: webapp/USO_REMOTO.md${NC}"
elif [ -n "$LAN_IP" ]; then
    echo -e "  ${YELLOW}⚠  Tailscale no conectado — solo WiFi local.${NC}"
    echo -e "  Para hermana en otro país: instala Tailscale → webapp/USO_REMOTO.md"
else
    echo -e "  ${YELLOW}→ Solo localhost. Para remoto: Tailscale (USO_REMOTO.md)${NC}"
fi

echo ""
echo -e "  Asistente:  /asistente"
echo -e "  Apagar:     cierra esta ventana o Ctrl+C"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

tail -f "$BACKEND_LOG" "$FRONTEND_LOG"
