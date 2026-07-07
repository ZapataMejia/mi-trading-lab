#!/usr/bin/env python3
"""Genera EURUSD_M5_full.csv.gz desde el CSV local completo (2003→hoy)."""
from __future__ import annotations

import gzip
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "forex_cache"
FULL = CACHE / "EURUSD_M5.csv"
OUT = CACHE / "EURUSD_M5_full.csv.gz"


def main() -> int:
    if not FULL.is_file():
        print(f"ERROR: no existe {FULL}", file=sys.stderr)
        return 1

    print(f"Comprimiendo {FULL.name}…")
    with FULL.open("rb") as src, gzip.open(OUT, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)

    full_mb = FULL.stat().st_size / 1_000_000
    gz_mb = OUT.stat().st_size / 1_000_000
    print(f"OK: {OUT.name} — {gz_mb:.1f} MB (desde {full_mb:.1f} MB sin comprimir)")
    if gz_mb > 95:
        print("WARN: gzip >95 MB — revisar límite GitHub", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
