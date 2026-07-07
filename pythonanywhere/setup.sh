#!/bin/bash
# Ejecutar en consola Bash de PythonAnywhere (cuenta free)
# Asume zip subido a ~/mi-trading-lab-pa.zip
set -euo pipefail
cd ~
unzip -qo mi-trading-lab-pa.zip
cd mi-trading-lab-pa
mkvirtualenv --python=/usr/bin/python3.10 mi-trading-lab 2>/dev/null || true
workon mi-trading-lab
pip install -r requirements-pa.txt
python3 scripts/install_forex_data.py
echo "OK deps + datos forex. Configura Web app (ver pythonanywhere/README.md)"
