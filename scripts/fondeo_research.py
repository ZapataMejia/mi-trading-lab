#!/usr/bin/env python3
"""Investigación sistemática Fondeo EMA — criterios evaluación WS $5k."""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.markets.forex import ForexDataAdapter, _normalize_ohlc

# Reglas evaluación WS CLASSIC $5k fase 1
EVAL = {
    "capital": 5000,
    "meta_pct": 8.0,
    "max_dd_pct": 8.0,
    "daily_dd_pct": 5.0,
    "min_trading_days": 4,
    "risk_per_trade_pct": 2.1,
    "max_trades_day": 2,
}


def load_bars(csv: str | None) -> pd.DataFrame:
    if csv:
        return _normalize_ohlc(pd.read_csv(csv))
    return ForexDataAdapter.load_bars("EURUSD", "M5")


def eval_flags(r, cfg: FondeoConfig) -> dict:
    m = r.metrics
    meta_usd = EVAL["capital"] * EVAL["meta_pct"] / 100
    return {
        "pass_meta": r.total_pnl >= meta_usd,
        "pass_dd": m["max_drawdown_pct"] > -EVAL["max_dd_pct"],
        "pass_trades": m["n_trades"] >= 10,
        "pass_pf": m["profit_factor"] >= 1.0,
        "pass_session": all(
            cfg.sess_start <= t.extra.get("session_hhmm", 0) <= cfg.sess_end for t in r.trades
        ) if r.trades else True,
    }


def score(flags: dict, r) -> float:
    s = r.total_pnl
    s += flags["pass_dd"] * 500
    s += flags["pass_meta"] * 300
    s += flags["pass_pf"] * 100
    s -= abs(r.metrics["max_drawdown_pct"]) * 20
    return s


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=None)
    p.add_argument("--offset", type=int, default=0, help="broker UTC offset hours")
    args = p.parse_args()

    bars = load_bars(args.csv)
    print("=" * 60)
    print("FONdeo RESEARCH — eval WS $5k")
    print("=" * 60)
    print(f"Barras: {len(bars):,}")
    print(f"Rango:  {bars['timestamp'].min()} → {bars['timestamp'].max()}")
    days = (bars["timestamp"].max() - bars["timestamp"].min()).days
    print(f"Días:   {days}")
    if days < 365:
        print("\n⚠  MENOS DE 1 AÑO — sube CSV Dukascopy desde SQX (2017-2022) para resultados fiables.")
    print()

    # Baseline curso
    base = FondeoConfig(broker_utc_offset_hours=args.offset)
    rb = run_fondeo_backtest(bars, base)
    fb = eval_flags(rb, base)
    print("BASELINE (9/20, 2.1%, sess 8-10, max 2/d)")
    print(f"  Trades: {rb.metrics['n_trades']} | WR: {rb.metrics['win_rate_pct']:.1f}%")
    print(f"  PnL: ${rb.total_pnl:.0f} ({rb.total_pnl_pct:.1f}%) | PF: {rb.metrics['profit_factor']:.2f}")
    print(f"  Max DD: {rb.metrics['max_drawdown_pct']:.1f}%")
    print(f"  Eval: meta={'✓' if fb['pass_meta'] else '✗'} dd={'✓' if fb['pass_dd'] else '✗'} pf={'✓' if fb['pass_pf'] else '✗'}")
    print()

    results = []
    grid = {
        "fast_period": [7, 9, 12],
        "slow_period": [18, 20, 26, 30],
        "risk_pct": [1.0, 1.5, 2.1],
        "tp_ratio": [0.8, 1.0, 1.5],
        "sess_start": [700, 800],
        "sess_end": [900, 1000, 1100],
        "max_trades_per_day": [1, 2],
        "broker_utc_offset_hours": [0, 2],
    }

    keys = list(grid.keys())
    for combo in itertools.product(*grid.values()):
        params = dict(zip(keys, combo))
        if params["slow_period"] <= params["fast_period"]:
            continue
        cfg = FondeoConfig(
            fast_period=params["fast_period"],
            slow_period=params["slow_period"],
            risk_pct=params["risk_pct"],
            tp_ratio=params["tp_ratio"],
            sess_start=params["sess_start"],
            sess_end=params["sess_end"],
            max_trades_per_day=params["max_trades_per_day"],
            mm_risk_pct=params["risk_pct"],
            broker_utc_offset_hours=params["broker_utc_offset_hours"],
        )
        r = run_fondeo_backtest(bars, cfg)
        if r.metrics["n_trades"] < 5:
            continue
        flags = eval_flags(r, cfg)
        results.append({
            **params,
            "trades": r.metrics["n_trades"],
            "wr": r.metrics["win_rate_pct"],
            "pnl": r.total_pnl,
            "pnl_pct": r.total_pnl_pct,
            "dd": r.metrics["max_drawdown_pct"],
            "pf": r.metrics["profit_factor"],
            **flags,
            "score": score(flags, r),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    print(f"Grid: {len(results)} configs con ≥5 trades\n")

    # Solo las que pasan DD
    dd_ok = [x for x in results if x["pass_dd"]]
    print(f"Con DD < {EVAL['max_dd_pct']}%: {len(dd_ok)}")
    print("\nTOP 15 (score compuesto: PnL + DD + meta):")
    print("-" * 60)
    for i, x in enumerate(results[:15], 1):
        tags = []
        if x["pass_dd"]:
            tags.append("DD✓")
        if x["pass_meta"]:
            tags.append("META✓")
        if x["pass_pf"]:
            tags.append("PF✓")
        print(
            f"{i:2}. EMA {x['fast_period']}/{x['slow_period']} risk={x['risk_pct']}% TP={x['tp_ratio']} "
            f"sess {x['sess_start']}-{x['sess_end']} off={x['broker_utc_offset_hours']} max/d={x['max_trades_per_day']}"
        )
        print(
            f"    {x['trades']}t WR={x['wr']:.0f}% PnL=${x['pnl']:.0f} ({x['pnl_pct']:.1f}%) "
            f"DD={x['dd']:.1f}% PF={x['pf']:.2f} {' '.join(tags)}"
        )

    all_pass = [x for x in results if x["pass_dd"] and x["pass_meta"] and x["pass_pf"]]
    print()
    if all_pass:
        b = all_pass[0]
        print("🏆 MEJOR CONFIG QUE PASA TODO (en este dataset):")
        print(f"   EMA {b['fast_period']}/{b['slow_period']}, risk={b['risk_pct']}%, TP={b['tp_ratio']}")
        print(f"   Sesión {b['sess_start']}-{b['sess_end']}, offset={b['broker_utc_offset_hours']}h, max {b['max_trades_per_day']}/d")
        print(f"   → Validar en SQX con mismos parámetros")
    else:
        print("Ninguna config pasa meta+DD+PF en este dataset.")
        print("Referencia SQX (2017-2022, defaults): 48 trades, +$1729, DD 53% — hay que bajar DD.")
        if dd_ok:
            b = max(dd_ok, key=lambda x: x["pnl"])
            print(f"\nMejor candidato DD-safe: EMA {b['fast_period']}/{b['slow_period']} risk={b['risk_pct']}% "
                  f"TP={b['tp_ratio']} sess {b['sess_start']}-{b['sess_end']}")


if __name__ == "__main__":
    main()
