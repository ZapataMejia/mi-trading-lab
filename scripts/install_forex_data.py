#!/usr/bin/env python3
"""Instala EURUSD_M5.csv en deploy: histórico completo (gzip) o subset deploy."""
from __future__ import annotations

import gzip
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "forex_cache"
FULL_GZ = CACHE / "EURUSD_M5_full.csv.gz"
DEPLOY = CACHE / "EURUSD_M5_deploy.csv"
TARGET = CACHE / "EURUSD_M5.csv"


def install() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)

    if FULL_GZ.is_file():
        print(f"Extrayendo {FULL_GZ.name} → {TARGET.name}…")
        with gzip.open(FULL_GZ, "rb") as src, TARGET.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        tsidx = Path(str(TARGET) + ".tsidx")
        if tsidx.is_file():
            tsidx.unlink()
        mb = TARGET.stat().st_size / 1_000_000
        print(f"OK: histórico completo — {mb:.1f} MB")
        return 0

    if DEPLOY.is_file():
        shutil.copy2(DEPLOY, TARGET)
        print(f"OK: subset deploy ({DEPLOY.name})")
        return 0

    if TARGET.is_file() and TARGET.stat().st_size > 1_000_000:
        print(f"OK: {TARGET.name} ya presente")
        return 0

    print("WARN: sin datos forex — sube EURUSD_M5_full.csv.gz o EURUSD_M5_deploy.csv", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(install())
