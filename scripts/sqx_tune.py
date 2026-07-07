#!/usr/bin/env python3
"""Pruebas sistemáticas Fondeo EMA vs datos SQX export."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/sqx_tune_results.json"

EVAL = {"meta_usd": 400, "max_dd": -10.0}


def load(start: str, end: str) -> pd.DataFrame:
    df = pd.read_csv(CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].copy()


def run_suite(bars: pd.DataFrame) -> list[dict]:
    results = []
    for off in [0, 2, 7]:
        for risk in [1.0, 1.5, 2.1]:
            for tp in [0.8, 1.0, 1.5]:
                for fast, slow in [(9, 20), (12, 30), (7, 26)]:
                    if slow <= fast:
                        continue
                    for sess_end in [900, 1000, 1100]:
                        for max_td in [1, 2]:
                            cfg = FondeoConfig(
                                fast_period=fast,
                                slow_period=slow,
                                risk_pct=risk,
                                tp_ratio=tp,
                                sess_start=800,
                                sess_end=sess_end,
                                max_trades_per_day=max_td,
                                mm_risk_pct=risk,
                                broker_utc_offset_hours=off,
                            )
                            r = run_fondeo_backtest(bars, cfg)
                            m = r.metrics
                            if m["n_trades"] < 15:
                                continue
                            results.append({
                                "off": off, "fast": fast, "slow": slow, "risk": risk,
                                "tp": tp, "sess_end": sess_end, "max_td": max_td,
                                "trades": m["n_trades"], "wr": round(m["win_rate_pct"], 1),
                                "pnl": round(r.total_pnl, 2), "pnl_pct": round(r.total_pnl_pct, 2),
                                "dd": round(m["max_drawdown_pct"], 2),
                                "pf": round(min(m["profit_factor"], 999), 2),
                                "pass_dd": m["max_drawdown_pct"] > EVAL["max_dd"],
                                "pass_meta": r.total_pnl >= EVAL["meta_usd"],
                            })
    return results


def main() -> None:
    bars = load("2017-01-03", "2022-03-31")
    print(f"Datos SQX: {len(bars):,} barras\n")

    base = FondeoConfig()
    for off in [0, 2, 7]:
        r = run_fondeo_backtest(bars, FondeoConfig(broker_utc_offset_hours=off))
        m = r.metrics
        print(f"Baseline 9/20 off={off}: {m['n_trades']}t PnL ${r.total_pnl:.0f} DD {m['max_drawdown_pct']:.1f}% PF {m['profit_factor']:.2f}")

    print("\nGrid search...")
    results = run_suite(bars)
    results.sort(key=lambda x: (x["pass_dd"], x["pass_meta"], x["pnl"]), reverse=True)

    dd_ok = [x for x in results if x["pass_dd"]]
    all_ok = [x for x in results if x["pass_dd"] and x["pass_meta"]]

    print(f"\nConfigs >=15 trades: {len(results)}")
    print(f"DD < 10%: {len(dd_ok)} | Pasa eval (DD+meta $400): {len(all_ok)}")

    print("\nTOP 10:")
    for i, x in enumerate(results[:10], 1):
        flags = []
        if x["pass_meta"]:
            flags.append("META")
        if x["pass_dd"]:
            flags.append("DD")
        print(
            f"{i}. off={x['off']} EMA {x['fast']}/{x['slow']} r={x['risk']} TP={x['tp']} "
            f"sess 800-{x['sess_end']} max/d={x['max_td']} | {x['trades']}t "
            f"PnL ${x['pnl']} DD {x['dd']}% PF {x['pf']} {' '.join(flags)}"
        )

    payload = {"baseline_sqx_ref": {"trades": 48, "pnl": 1729, "dd": -53}, "top10": results[:10], "pass_eval": all_ok[:5], "total": len(results)}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nGuardado {OUT}")


if __name__ == "__main__":
    main()
