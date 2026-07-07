#!/usr/bin/env bash
# Sube EURUSD completo al VPS grande (desde tu Mac).
# Requiere: OpenSSH server en Windows o copia manual por RDP.
#
# Uso:
#   VPS_HOST=100.x.x.x VPS_USER=Administrador ./scripts/upload_vps_lab_forex.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VPS_HOST="${VPS_HOST:?Define VPS_HOST (IP Tailscale o IP publica del VPS grande)}"
VPS_USER="${VPS_USER:-Administrador}"
REMOTE_DIR="${VPS_REMOTE:-/c/Users/${VPS_USER}/mi-trading-lab/data/forex_cache}"

GZ="${ROOT}/data/forex_cache/EURUSD_M5_full.csv.gz"
if [[ ! -f "$GZ" ]]; then
  echo "Generando gzip…"
  python3 "${ROOT}/scripts/build_full_forex_gz.py" 2>/dev/null || true
fi
if [[ ! -f "$GZ" ]]; then
  GZ="${ROOT}/data/forex_cache/EURUSD_M5_deploy.csv"
fi

echo "Subiendo $(basename "$GZ") a ${VPS_USER}@${VPS_HOST}…"
scp "$GZ" "${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/"

echo "Instalando en VPS (SSH)…"
ssh "${VPS_USER}@${VPS_HOST}" "cd mi-trading-lab && .venv-lab/Scripts/python.exe scripts/install_forex_data.py"

echo "Listo."
