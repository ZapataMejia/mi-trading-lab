#!/usr/bin/env python3
"""Diagnóstico: en ventanas 30d, ¿qué regla falla más?"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd

from eval_hunt_no_sess_close import run_no_sess_close
from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"

CONFIGS = [
    ("9/18 hold TP3", dict(fast_period=9, slow_period=18, tp_ratio=3.0, sess_start=700, sess_end=1600, broker_utc_offset_hours=7), "hold"),
    ("3/8 hold TP2.5", dict(fast_period=3, slow_period=8, tp_ratio=2.5, sess_start=700, sess_end=1400, broker_utc_offset_hours=7), "hold"),
    ("9/18 session TP1", dict(fast_period=9, slow_period=18, tp_ratio=1.0, sess_start=700, sess_end=1100, broker_utc_offset_hours=7), "session"),
    ("2/5 hold TP4", dict(fast_period=2, slow_period=5, tp_ratio=4.0, sess_start=600, sess_end=1600, broker_utc_offset_hours=7), "hold"),
]


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(CSV))
    bars = df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)
    starts = pd.date_range("2017-01-03", "2021-09-01", freq="MS", tz="UTC")

    for name, params, mode in CONFIGS:
        cfg = FondeoConfig(**params, risk_pct=2.1, max_trades_per_day=2, mm_risk_pct=2.1, equity_sample_bars=48)
        run_fn = run_no_sess_close if mode == "hold" else run_fondeo_backtest
        fails: dict[str, int] = {}
        meta_hits = 0
        total = 0
        best_pnl = -9999.0
        for s in starts:
            e = s + pd.Timedelta(days=30)
            chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < e)]
            if len(chunk) < 400:
                continue
            total += 1
            r = run_fn(chunk, cfg)
            ev = evaluate_ws_classic(r, cfg)
            if r.total_pnl >= 400:
                meta_hits += 1
            best_pnl = max(best_pnl, r.total_pnl)
            if not ev["checks"]["pass_all"]:
                for k, v in ev["checks"].items():
                    if k != "pass_all" and not v:
                        fails[k] = fails.get(k, 0) + 1
        print(f"\n{name} ({mode}) — {total} ventanas")
        print(f"  Meta +$400 alcanzada: {meta_hits}/{total} ({round(100*meta_hits/total,1)}%)")
        print(f"  Mejor PnL 30d: ${best_pnl:.0f}")
        print(f"  Fallos por regla:", {k: fails[k] for k in sorted(fails, key=fails.get, reverse=True)})


if __name__ == "__main__":
    main()
