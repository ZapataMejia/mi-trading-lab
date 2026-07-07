"""Descarga histórico M1 del Nasdaq desde Dukascopy y lo deja en el formato
que espera el backtester (data/raw/nasdaq/{symbol}_{tf}.parquet, índice
tz-aware America/New_York, columnas open/high/low/close/volume).

- Instrumento: E_NQ-100 (Nasdaq 100 en puntos reales, cobertura casi 24h).
- Baja año por año a data/raw/nasdaq/_dukas_parts/ para poder reanudar.
- Luego concatena y genera 1m / 5m / 15m / 1h.

Uso:
  python scripts/fetch_dukascopy_nasdaq.py --start 2012 --end 2026 --symbol NQDK
"""
from __future__ import annotations

import argparse
import time as _time
from datetime import datetime
from pathlib import Path

import pandas as pd

import dukascopy_python as dk
from dukascopy_python.instruments import INSTRUMENT_IDX_AMERICA_E_NQ_100

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw" / "nasdaq"
PARTS = DATA / "_dukas_parts"
PARTS.mkdir(parents=True, exist_ok=True)
TZ = "America/New_York"


def fetch_year(year: int) -> pd.DataFrame:
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)
    df = dk.fetch(
        INSTRUMENT_IDX_AMERICA_E_NQ_100,
        dk.INTERVAL_MIN_1,
        dk.OFFER_SIDE_BID,
        start,
        end,
    )
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    # dukascopy devuelve índice UTC tz-aware -> a ET
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(TZ)
    df.index.name = "timestamp"
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2012)
    ap.add_argument("--end", type=int, default=datetime.now().year)
    ap.add_argument("--symbol", default="NQDK")
    args = ap.parse_args()

    years = list(range(args.start, args.end + 1))
    print(f"Descargando E_NQ-100 M1 {args.start}..{args.end}  ({len(years)} años)")

    for y in years:
        part = PARTS / f"{y}.parquet"
        if part.exists():
            print(f"  [skip] {y} ya existe ({part.name})")
            continue
        t = _time.time()
        try:
            df = fetch_year(y)
        except Exception as e:
            print(f"  [ERR ] {y}: {type(e).__name__}: {e}")
            continue
        if len(df) == 0:
            print(f"  [vacío] {y}: sin datos")
            continue
        df.to_parquet(part)
        print(f"  [ok ] {y}: {len(df):>7} velas  {df.index.min()} .. {df.index.max()}  ({_time.time()-t:.0f}s)")

    # --- concatenar y generar timeframes ---
    parts = sorted(PARTS.glob("*.parquet"))
    if not parts:
        print("No hay partes descargadas, salgo.")
        return
    frames = [pd.read_parquet(p) for p in parts]
    m1 = pd.concat(frames).sort_index()
    m1 = m1[~m1.index.duplicated(keep="first")]
    print(f"\nM1 total: {len(m1):,} velas  {m1.index.min()} .. {m1.index.max()}")

    out1 = DATA / f"{args.symbol}_1m.parquet"
    m1.to_parquet(out1)
    print(f"  guardado {out1.name}")

    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    for tf, rule in [("5m", "5min"), ("15m", "15min"), ("1h", "1h")]:
        r = m1.resample(rule, label="left", closed="left").agg(agg).dropna()
        out = DATA / f"{args.symbol}_{tf}.parquet"
        r.to_parquet(out)
        print(f"  guardado {out.name}: {len(r):,} velas")


if __name__ == "__main__":
    main()
