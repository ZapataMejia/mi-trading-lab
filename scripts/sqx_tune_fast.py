#!/usr/bin/env python3
"""Grid rápido: carga CSV una vez, filtra 2017-2022, prueba offsets y params."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
START, END = "2017-01-03", "2022-03-31"


def load() -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    df = df[(df["timestamp"] >= START) & (df["timestamp"] <= END)]
    return df.reset_index(drop=True)


def run_one(bars: pd.DataFrame, **kw) -> dict:
    cfg = FondeoConfig(**kw)
    r = run_fondeo_backtest(bars, cfg)
    m = r.metrics
    return {
        **kw,
        "trades": m["n_trades"],
        "pnl": round(r.total_pnl, 2),
        "dd": round(m["max_drawdown_pct"], 2),
        "pf": round(min(m["profit_factor"], 999), 2),
        "pass_dd": m["max_drawdown_pct"] > -10,
        "pass_meta": r.total_pnl >= 400,
    }


def main() -> None:
    bars = load()
    print(f"Barras {START}→{END}: {len(bars):,}\n")

    print("=== OFFSET sweep (baseline 9/20) ===")
    for off in [0, 2, 7]:
        x = run_one(bars, broker_utc_offset_hours=off)
        print(f"  off={off}: {x['trades']}t PnL ${x['pnl']} DD {x['dd']}% PF {x['pf']}")

    print("\n=== GRID offset=7 ===")
    results = []
    for fast, slow in [(9, 20), (12, 30), (7, 26)]:
        for risk in [1.5, 2.1]:
            for tp in [0.8, 1.0, 1.5]:
                for sess_end in [900, 1000]:
                    for max_td in [1, 2]:
                        results.append(
                            run_one(
                                bars,
                                fast_period=fast,
                                slow_period=slow,
                                risk_pct=risk,
                                tp_ratio=tp,
                                sess_start=800,
                                sess_end=sess_end,
                                max_trades_per_day=max_td,
                                mm_risk_pct=risk,
                                broker_utc_offset_hours=7,
                            )
                        )

    results.sort(key=lambda x: (x["pass_dd"], x["pass_meta"], x["pnl"]), reverse=True)
    print(f"Configs: {len(results)} | DD ok: {sum(x['pass_dd'] for x in results)} | Eval ok: {sum(x['pass_dd'] and x['pass_meta'] for x in results)}\n")
    print("TOP 10:")
    for i, x in enumerate(results[:10], 1):
        flags = " ".join(f for f, ok in [("META", x["pass_meta"]), ("DD", x["pass_dd"])] if ok)
        print(
            f"  {i}. EMA {x['fast_period']}/{x['slow_period']} r={x['risk_pct']} TP={x['tp_ratio']} "
            f"800-{x['sess_end']} max/d={x['max_trades_per_day']} | {x['trades']}t "
            f"PnL ${x['pnl']} DD {x['dd']}% PF {x['pf']} {flags}"
        )


if __name__ == "__main__":
    main()
