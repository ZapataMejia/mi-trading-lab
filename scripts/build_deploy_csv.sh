#!/usr/bin/env bash
# Genera data/forex_cache/EURUSD_M5_deploy.csv para subir al repo (<100MB)
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
python scripts/prepare_deploy_data.py
