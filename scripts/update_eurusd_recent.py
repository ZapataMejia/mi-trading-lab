#!/usr/bin/env python3
"""Actualiza EURUSD_M5.csv con meses recientes desde Dukascopy (append, no borra histórico)."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from scripts.download_dukascopy_m5 import TMP, download_month
from webapp.backend.markets.forex import ForexDataAdapter, _normalize_ohlc

OUT = ROOT / "data/forex_cache/EURUSD_M5.csv"


def last_date_in_csv() -> date | None:
    if not OUT.exists():
        return None
    _d0, d1 = ForexDataAdapter._csv_date_range(OUT)
    if not d1:
        return None
    return pd.Timestamp(d1).date()


def merge_months(start_y: int, start_m: int, end_y: int, end_m: int) -> pd.DataFrame:
    frames = []
    y, m = start_y, start_m
    while (y, m) <= (end_y, end_m):
        p = TMP / f"EURUSD_{y:04d}{m:02d}.csv"
        if p.exists() and p.stat().st_size > 100:
            df = pd.read_csv(p)
            if "time" in df.columns:
                df = df.rename(columns={"time": "timestamp"})
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            for col in ("open", "high", "low", "close"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["volume"] = 0.0
            frames.append(df[["timestamp", "open", "high", "low", "close", "volume"]])
        m += 1
        if m > 12:
            m, y = 1, y + 1
    if not frames:
        raise SystemExit("Sin chunks nuevos en el rango")
    return pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")


def append_months(start_y: int, start_m: int, end_y: int, end_m: int) -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    y, m = start_y, start_m
    while (y, m) <= (end_y, end_m):
        tag = TMP / f"EURUSD_{y:04d}{m:02d}.csv"
        if tag.exists() and tag.stat().st_size > 1000:
            print(f"skip {tag.name}", flush=True)
        else:
            print(f"download {y}-{m:02d}...", flush=True)
            df = download_month("EURUSD", y, m)
            df.to_csv(tag, index=False)
            print(f"  {len(df):,} barras", flush=True)
        m += 1
        if m > 12:
            m, y = 1, y + 1


def main() -> None:
    p = argparse.ArgumentParser(description="Append meses recientes a EURUSD_M5.csv")
    p.add_argument("--from", dest="from_", default=None, help="YYYY-MM (default: mes de la última barra)")
    p.add_argument("--to", default=None, help="YYYY-MM (default: mes actual)")
    args = p.parse_args()

    today = date.today()
    end_y, end_m = today.year, today.month
    if args.to:
        end_y, end_m = map(int, args.to.split("-"))

    if args.from_:
        start_y, start_m = map(int, args.from_.split("-"))
    else:
        last = last_date_in_csv()
        if last is None:
            print("No hay CSV. Usa download_dukascopy_m5.py primero.")
            raise SystemExit(1)
        start_y, start_m = last.year, last.month
        print(f"Última barra en CSV: {last}", flush=True)

    append_months(start_y, start_m, end_y, end_m)
    new_bars = merge_months(start_y, start_m, end_y, end_m)

    if OUT.exists():
        old = _normalize_ohlc(pd.read_csv(OUT))
        combined = pd.concat([old, new_bars], ignore_index=True)
        combined = combined.drop_duplicates("timestamp").sort_values("timestamp")
    else:
        combined = new_bars

    OUT.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUT, index=False)
    print(
        f"\nOK {OUT}: {len(combined):,} barras | "
        f"{combined['timestamp'].iloc[0]} -> {combined['timestamp'].iloc[-1]}",
        flush=True,
    )


if __name__ == "__main__":
    main()
