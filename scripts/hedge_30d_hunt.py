#!/usr/bin/env python3
"""Hedge 2 cuentas — ventanas 30d con equity guardian."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig
from webapp.backend.engine.hedged_eval import simulate_hedged_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hedge_30d_hunt.json"


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(CSV))
    bars = df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")]

    emas = [(9, 20), (9, 18), (5, 11), (3, 8), (8, 18)]
    sessions = [(800, 1000), (700, 1100), (700, 1400), (800, 1200)]
    tps = [1.0, 1.5, 2.0, 2.5]
    hits = []

    combos = list(itertools.product(emas, sessions, tps, (0, 7)))
    print(f"Hedge 30d — {len(combos)} configs\n", flush=True)

    for i, ((f, s), (ss, se), tp, off) in enumerate(combos, 1):
        cfg = FondeoConfig(
            fast_period=f, slow_period=s, risk_pct=2.1, tp_ratio=tp,
            sess_start=ss, sess_end=se, max_trades_per_day=2,
            broker_utc_offset_hours=off, equity_sample_bars=48,
        )
        w30 = simulate_hedged_windows(bars, cfg, window_days=30, step="MS", commission_usd=5.0)
        if w30.pair_wins > 0:
            hits.append({
                **cfg.to_dict(), "w30_rate": w30.pass_rate_pct, "w30_wins": w30.pair_wins,
                "w30_attempts": w30.attempts, "w30_med": w30.median_days,
                "a_wins": w30.a_wins, "b_wins": w30.b_wins,
            })
            print(
                f"  HIT EMA {f}/{s} TP{tp} {ss}-{se} off{off} | {w30.pass_rate_pct}% med={w30.median_days}d",
                flush=True,
            )
        if i % 20 == 0:
            print(f"  {i}/{len(combos)} hits={len(hits)}", flush=True)

    hits.sort(key=lambda x: (x["w30_rate"], x["w30_wins"]), reverse=True)
    print(f"\nSurvivors: {len(hits)}", flush=True)
    OUT.write_text(json.dumps({"survivors": len(hits), "top": hits[:20]}, indent=2), encoding="utf-8")
    print(f"→ {OUT}", flush=True)


if __name__ == "__main__":
    main()
