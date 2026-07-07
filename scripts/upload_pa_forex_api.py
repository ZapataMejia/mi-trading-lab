#!/usr/bin/env python3
"""Sube EURUSD_M5_full.csv.gz a PythonAnywhere vía API y lo instala."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
GZ = ROOT / "data" / "forex_cache" / "EURUSD_M5_full.csv.gz"
USER = os.environ.get("PA_USER", "mitradinglab")
TOKEN = os.environ.get("PYTHONANYWHERE_API_TOKEN") or os.environ.get("PA_API_TOKEN")
REMOTE = f"/home/{USER}/mi-trading-lab/data/forex_cache/EURUSD_M5_full.csv.gz"


def main() -> int:
    if not TOKEN:
        print("Falta PYTHONANYWHERE_API_TOKEN (Account → API token en PA)", file=sys.stderr)
        return 1
    if not GZ.is_file():
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_full_forex_gz.py")])

    url = f"https://www.pythonanywhere.com/api/v0/user/{USER}/files/path{REMOTE}"
    print(f"Subiendo {GZ.name} ({GZ.stat().st_size / 1e6:.1f} MB)…")
    with GZ.open("rb") as fh:
        resp = requests.post(
            url,
            files={"content": (GZ.name, fh, "application/gzip")},
            headers={"Authorization": f"Token {TOKEN}"},
            timeout=600,
        )
    if resp.status_code not in (200, 201):
        print(f"ERROR upload: {resp.status_code} {resp.text[:500]}", file=sys.stderr)
        return 1
    print("Upload OK. Ejecuta en consola Bash de PA:")
    print(f"  cd ~/mi-trading-lab && python3 scripts/install_forex_data.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
