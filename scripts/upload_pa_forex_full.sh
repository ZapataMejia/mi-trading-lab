#!/usr/bin/env bash
# Sube el histórico completo EURUSD a PythonAnywhere (requiere SSH configurado).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PA_USER="${PA_USER:-mitradinglab}"
PA_HOST="${PA_HOST:-ssh.pythonanywhere.com}"
REMOTE_DIR="/home/${PA_USER}/mi-trading-lab/data/forex_cache"

GZ="${ROOT}/data/forex_cache/EURUSD_M5_full.csv.gz"
if [[ ! -f "$GZ" ]]; then
  echo "Generando gzip…"
  python3 "${ROOT}/scripts/build_full_forex_gz.py"
fi

echo "Subiendo $(basename "$GZ") (~26 MB)…"
scp "$GZ" "${PA_USER}@${PA_HOST}:${REMOTE_DIR}/"

echo "Instalando en el servidor…"
ssh "${PA_USER}@${PA_HOST}" "cd /home/${PA_USER}/mi-trading-lab && python3 scripts/install_forex_data.py"

echo "Comprobando rango…"
ssh "${PA_USER}@${PA_HOST}" "curl -s https://${PA_USER}.pythonanywhere.com/api/fondeo/data-range?symbol=EURUSD&timeframe=M5"
echo ""
echo "Listo. Recarga la web app en el dashboard de PythonAnywhere si hace falta."
