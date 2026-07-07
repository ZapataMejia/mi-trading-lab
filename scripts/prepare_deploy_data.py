#!/usr/bin/env python3
"""Prepara datos forex para deploy: genera gzip completo y/o subset deploy."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "forex_cache"
FULL = CACHE / "EURUSD_M5.csv"
DEPLOY = CACHE / "EURUSD_M5_deploy.csv"
FULL_GZ = CACHE / "EURUSD_M5_full.csv.gz"


def main() -> int:
    if FULL.is_file():
        rc = subprocess.call([sys.executable, str(ROOT / "scripts" / "build_full_forex_gz.py")])
        if rc != 0:
            return rc

    if DEPLOY.exists() and not FULL.exists():
        print(f"OK: {DEPLOY.name} listo para fallback")
        return 0

    if FULL_GZ.is_file():
        mb = FULL_GZ.stat().st_size / 1_000_000
        print(f"OK: {FULL_GZ.name} ({mb:.1f} MB) — usar install_forex_data.py en deploy")
        return 0

    if DEPLOY.exists():
        print(f"OK: {DEPLOY.name}")
        return 0

    print("WARN: sin datos forex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
