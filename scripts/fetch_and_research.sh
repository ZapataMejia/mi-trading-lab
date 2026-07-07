#!/usr/bin/env bash
# Descarga EURUSD M5 Dukascopy (duka, URL corregida) + merge + research.
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
export PYTHONUNBUFFERED=1

python3 << 'PY'
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, ".")
import duka.core.fetch as duka_fetch
from duka.app import app as duka_app
from duka.core.utils import TimeFrame
import pandas as pd

duka_fetch.URL = "https://datafeed.dukascopy.com/datafeed/{currency}/{year}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"
TMP = Path("data/forex_cache/duka_chunks")
OUT = Path("data/forex_cache/EURUSD_M5.csv")
TMP.mkdir(parents=True, exist_ok=True)

months: list[tuple[int, int]] = []
y, m = 2017, 1
while (y, m) <= (2022, 3):
    months.append((y, m))
    m += 1
    if m > 12:
        m = 1
        y += 1

for y, m in months:
    tag = TMP / f"EURUSD_{y:04d}{m:02d}.csv"
    if tag.exists() and tag.stat().st_size > 1000:
        print(f"skip {tag.name}", flush=True)
        continue
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
    print(f"download {y}-{m:02d} ({start} -> {end})...", flush=True)
    duka_app(["EURUSD"], start, end, 1, TimeFrame.M5, str(TMP), True)
    produced = sorted(TMP.glob("EURUSD-*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if produced:
        df = pd.read_csv(produced[0])
        df.to_csv(tag, index=False)
        for p in TMP.glob("EURUSD-*.csv"):
            p.unlink(missing_ok=True)
        print(f"  saved {tag.name} ({len(df):,} rows)", flush=True)
    else:
        print(f"  WARN: no output for {y}-{m:02d}", flush=True)

frames = []
for p in sorted(TMP.glob("EURUSD_*.csv")):
    df = pd.read_csv(p)
    if "time" in df.columns:
        df = df.rename(columns={"time": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["volume"] = 0.0
    frames.append(df[["timestamp", "open", "high", "low", "close", "volume"]])

out = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
OUT.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(OUT, index=False)
print(f"DONE {OUT}: {len(out):,} barras | {out['timestamp'].iloc[0]} -> {out['timestamp'].iloc[-1]}", flush=True)
PY

python scripts/fondeo_research.py --csv data/forex_cache/EURUSD_M5.csv | tee data/forex_cache/_research.log
echo "Listo. Research en data/forex_cache/_research.log"
