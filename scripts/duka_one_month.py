#!/usr/bin/env python3
"""Descarga un mes Dukascopy vía duka (subprocess-safe)."""
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duka.core.fetch as duka_fetch
import pandas as pd
from duka.app import app as duka_app
from duka.core.utils import TimeFrame

duka_fetch.URL = "https://datafeed.dukascopy.com/datafeed/{currency}/{year}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"

TMP = ROOT / "data/forex_cache/duka_chunks"
y, m = int(sys.argv[1]), int(sys.argv[2])
start = date(y, m, 1)
end = date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
tag = TMP / f"EURUSD_{y:04d}{m:02d}.csv"
TMP.mkdir(parents=True, exist_ok=True)
print(f"download {y}-{m:02d}...", flush=True)
duka_app(["EURUSD"], start, end, 1, TimeFrame.M5, str(TMP), True)
produced = sorted(TMP.glob("EURUSD-*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
df = pd.read_csv(produced[0])
if "time" in df.columns:
    df = df.rename(columns={"time": "timestamp"})
df.to_csv(tag, index=False)
for p in TMP.glob("EURUSD-*.csv"):
    p.unlink(missing_ok=True)
print(f"OK {len(df)} -> {tag.name}", flush=True)
