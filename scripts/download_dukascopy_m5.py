#!/usr/bin/env python3
"""Descarga EURUSD M5 Dukascopy mes a mes (secuencial, estable)."""
from __future__ import annotations

import argparse
import struct
import sys
import time
from datetime import date, datetime, timedelta
from lzma import LZMADecompressor, FORMAT_AUTO
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

URL = "https://datafeed.dukascopy.com/datafeed/{currency}/{year}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"
OUT = ROOT / "data/forex_cache/EURUSD_M5.csv"
TMP = ROOT / "data/forex_cache/duka_chunks"
M5 = 300


def fetch_hour(symbol: str, day: date, hour: int) -> bytes:
    url = URL.format(currency=symbol, year=day.year, month=day.month - 1, day=day.day, hour=hour)
    for attempt in range(5):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                return b""
        except Exception:
            pass
        time.sleep(0.3 * (attempt + 1))
    return b""


def decompress_lzma(data: bytes) -> bytes:
    if not data:
        return b""
    results = []
    while data:
        decomp = LZMADecompressor(FORMAT_AUTO, None, None)
        try:
            res = decomp.decompress(data)
        except Exception:
            break
        results.append(res)
        data = decomp.unused_data
        if not decomp.eof and not data:
            break
    return b"".join(results)


def parse_ticks(raw: bytes, day: date) -> list[tuple]:
    buf = decompress_lzma(raw)
    if not buf:
        return []
    ticks = []
    step = 20
    base = datetime(day.year, day.month, day.day)
    hour_carry = 0
    prev_min = -1
    for i in range(0, len(buf) // step):
        ms, ask, bid, va, vb = struct.unpack("!IIIff", buf[i * step : (i + 1) * step])
        dt = base + timedelta(milliseconds=int(ms))
        if prev_min >= 0 and dt.minute < prev_min:
            hour_carry += 1
        prev_min = dt.minute
        dt = dt + timedelta(hours=hour_carry)
        mid = (ask + bid) / 2 / 100000.0
        ticks.append((dt, mid))
    return ticks


def to_m5(ticks: list[tuple]) -> pd.DataFrame:
    if not ticks:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    rows = []
    bucket = None
    o = h = l = c = None
    for ts, price in sorted(ticks, key=lambda x: x[0]):
        key = int(ts.timestamp()) // M5 * M5
        if bucket != key and bucket is not None:
            rows.append((pd.Timestamp(bucket, unit="s", tz="UTC"), o, h, l, c))
        if bucket != key:
            bucket = key
            o = h = l = c = price
        else:
            h = max(h, price)
            l = min(l, price)
            c = price
    if bucket is not None:
        rows.append((pd.Timestamp(bucket, unit="s", tz="UTC"), o, h, l, c))
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    df["volume"] = 0.0
    return df


def trading_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() != 5:  # skip Saturday
            yield d
        d += timedelta(days=1)


def download_month(symbol: str, year: int, month: int) -> pd.DataFrame:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    all_ticks: list[tuple] = []
    for day in trading_days(start, end):
        for hour in range(24):
            raw = fetch_hour(symbol, day, hour)
            if raw:
                all_ticks.extend(parse_ticks(raw, day))
    return to_m5(all_ticks)


def merge_all() -> pd.DataFrame:
    frames = []
    for p in sorted(TMP.glob("EURUSD_*.csv")):
        df = pd.read_csv(p)
        if "time" in df.columns:
            df = df.rename(columns={"time": "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = 0.0
        frames.append(df[["timestamp", "open", "high", "low", "close", "volume"]])
    if not frames:
        raise SystemExit("Sin chunks")
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates("timestamp").sort_values("timestamp")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2017-01")
    p.add_argument("--end", default="2022-03")
    p.add_argument("--merge-only", action="store_true")
    p.add_argument("--merge", action="store_true", help="Unificar chunks al terminar")
    args = p.parse_args()

    if args.merge_only:
        out = merge_all()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(OUT, index=False)
        print(f"OK {OUT}: {len(out):,} barras | {out['timestamp'].iloc[0]} -> {out['timestamp'].iloc[-1]}")
        return

    sy, sm = map(int, args.start.split("-"))
    ey, em = map(int, args.end.split("-"))
    TMP.mkdir(parents=True, exist_ok=True)

    y, m = sy, sm
    while (y, m) <= (ey, em):
        tag = TMP / f"EURUSD_{y:04d}{m:02d}.csv"
        if tag.exists() and tag.stat().st_size > 1000:
            print(f"skip {tag.name}", flush=True)
        else:
            print(f"download {y}-{m:02d}...", flush=True)
            df = download_month("EURUSD", y, m)
            df.to_csv(tag, index=False)
            print(f"  {len(df):,} barras -> {tag.name}", flush=True)
        m += 1
        if m > 12:
            m = 1
            y += 1

    if args.merge:
        print("merging...", flush=True)
        out = merge_all()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(OUT, index=False)
        print(f"OK {OUT}: {len(out):,} barras | {out['timestamp'].iloc[0]} -> {out['timestamp'].iloc[-1]}")


if __name__ == "__main__":
    main()
