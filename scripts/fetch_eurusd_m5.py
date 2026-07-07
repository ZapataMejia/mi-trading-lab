#!/usr/bin/env python3
"""Descarga EURUSD M5 en chunks (Yahoo ~60d por request) y guarda CSV unificado."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TradingLab/1.0)"}
OUT = Path("data/forex_cache/EURUSD_M5.csv")


def fetch_chunk(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    params = {
        "interval": "5m",
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
    }
    r = requests.get(YAHOO, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    ts = result["timestamp"]
    q = result["indicators"]["quote"][0]
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(ts, unit="s", utc=True),
        "open": q["open"],
        "high": q["high"],
        "low": q["low"],
        "close": q["close"],
        "volume": q.get("volume") or [0] * len(ts),
    })
    return df.dropna(subset=["open", "high", "low", "close"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2017-01-03")
    p.add_argument("--end", default="2022-03-31")
    p.add_argument("--chunk-days", type=int, default=55)
    args = p.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")
    chunk = pd.Timedelta(days=args.chunk_days)

    frames: list[pd.DataFrame] = []
    cur = start
    n = 0
    while cur < end:
        n += 1
        nxt = min(cur + chunk, end)
        print(f"[{n}] {cur.date()} -> {nxt.date()}...", flush=True)
        try:
            df = fetch_chunk(cur, nxt)
            frames.append(df)
            print(f"    +{len(df)} barras")
        except Exception as exc:
            print(f"    SKIP: {exc}")
        cur = nxt
        time.sleep(1.2)

    if not frames:
        raise SystemExit("No se descargó nada")

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"\nGuardado {OUT}: {len(out):,} barras")
    print(f"  {out['timestamp'].iloc[0]} -> {out['timestamp'].iloc[-1]}")


if __name__ == "__main__":
    main()
