#!/usr/bin/env python3
"""Descarga meses recientes con librería duka (más fiable que ticks manual)."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import duka.core.fetch as duka_fetch
from duka.app import app as duka_app
from duka.core.utils import TimeFrame

duka_fetch.URL = "https://datafeed.dukascopy.com/datafeed/{currency}/{year}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"

from webapp.backend.markets.forex import ForexDataAdapter, _normalize_ohlc

TMP = ROOT / "data/forex_cache/duka_chunks"
OUT = ROOT / "data/forex_cache/EURUSD_M5.csv"


def download_month_duka(y: int, m: int) -> pd.DataFrame:
    tag = TMP / f"EURUSD_{y:04d}{m:02d}.csv"
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
    print(f"download {y}-{m:02d} ({start} -> {end})...", flush=True)
    duka_app(["EURUSD"], start, end, 1, TimeFrame.M5, str(TMP), True)
    produced = sorted(TMP.glob("EURUSD-*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not produced:
        raise RuntimeError(f"Sin datos {y}-{m:02d}")
    df = pd.read_csv(produced[0])
    if "time" in df.columns:
        df = df.rename(columns={"time": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["volume"] = 0.0
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df.to_csv(tag, index=False)
    for p in TMP.glob("EURUSD-*.csv"):
        p.unlink(missing_ok=True)
    print(f"  OK {len(df):,} barras -> {tag.name}", flush=True)
    return df


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    months = []
    y, m = 2024, 11
    while (y, m) <= (2026, 7):
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1

    # Borrar chunks corruptos (pocos cientos de barras)
    for y, m in months:
        tag = TMP / f"EURUSD_{y:04d}{m:02d}.csv"
        if tag.exists() and sum(1 for _ in tag.open()) < 2000:
            print(f"remove bad chunk {tag.name}", flush=True)
            tag.unlink()

    new_frames = []
    for y, m in months:
        tag = TMP / f"EURUSD_{y:04d}{m:02d}.csv"
        if tag.exists() and sum(1 for _ in tag.open()) >= 2000:
            print(f"skip {tag.name}", flush=True)
            df = pd.read_csv(tag)
        else:
            df = download_month_duka(y, m)
        if "time" in df.columns:
            df = df.rename(columns={"time": "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        new_frames.append(df)

    new = pd.concat(new_frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    old = _normalize_ohlc(pd.read_csv(OUT))
    combined = pd.concat([old, new], ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    combined.to_csv(OUT, index=False)
    print(
        f"\nDONE {OUT}: {len(combined):,} barras | "
        f"{combined['timestamp'].iloc[0]} -> {combined['timestamp'].iloc[-1]}",
        flush=True,
    )
    dr = ForexDataAdapter.data_range("EURUSD", "M5")
    print(f"API range: {dr['date_from']} -> {dr['date_to']}", flush=True)


if __name__ == "__main__":
    main()
