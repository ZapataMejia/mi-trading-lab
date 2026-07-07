#!/usr/bin/env python3
"""Busca configs que PASEN eval WS en ventana ≤60 días."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.ws_eval import evaluate_ws_classic, simulate_eval_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/ws_eval_60d_best.json"


def load():
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def passes_any_60d_chunk(bars, cfg, starts: list[str]) -> bool:
    for s in starts:
        chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < pd.Timestamp(s, tz="UTC") + pd.Timedelta(days=60))]
        if len(chunk) < 500:
            continue
        ev = evaluate_ws_classic(run_fondeo_backtest(chunk, cfg), cfg)
        if ev["checks"]["pass_all"]:
            return True
    return False


def build_grid() -> list[dict]:
    grid: list[dict] = []
    emas = [
        (2, 5), (2, 6), (3, 6), (3, 7), (3, 8), (4, 8), (4, 9),
        (5, 11), (6, 14), (7, 16), (8, 18), (9, 18), (9, 20),
    ]
    sessions = [
        (600, 1200), (600, 1400), (600, 1600),
        (700, 1100), (700, 1200), (700, 1400), (700, 1600),
        (800, 1000), (800, 1100), (800, 1200), (800, 1400),
    ]
    for fast, slow in emas:
        for tp in [1.0, 1.2, 1.5, 2.0, 2.5, 3.0]:
            for ss, se in sessions:
                grid.append({
                    "fast_period": fast, "slow_period": slow, "risk_pct": 2.1,
                    "tp_ratio": tp, "sess_start": ss, "sess_end": se,
                    "max_trades_per_day": 2, "broker_utc_offset_hours": 7,
                })
    return grid


def main() -> None:
    bars = load()
    grid = build_grid()
    probe_starts = ["2017-06-01", "2018-02-01", "2019-04-01", "2020-06-01", "2021-04-01"]
    print(f"HUNT 60d — {len(grid)} combos\n", flush=True)

    candidates: list[dict] = []
    for i, p in enumerate(grid, 1):
        if i % 100 == 0:
            print(f"  probe {i}/{len(grid)} cand={len(candidates)}", flush=True)
        cfg = FondeoConfig(**p, mm_risk_pct=2.1)
        if not passes_any_60d_chunk(bars, cfg, probe_starts):
            continue
        candidates.append(p)

    print(f"\nProbe: {len(candidates)} pasan algún tramo 60d fijo\n", flush=True)

    survivors: list[dict] = []
    for p in candidates:
        cfg = FondeoConfig(**p, mm_risk_pct=2.1)
        w60 = simulate_eval_windows(bars, cfg, window_days=60, step="2MS")
        if w60.passed == 0:
            continue
        r = run_fondeo_backtest(bars, cfg)
        ev = evaluate_ws_classic(r, cfg)
        w30 = simulate_eval_windows(bars, cfg, window_days=30, step="2MS")
        survivors.append({
            **p,
            "w60_rate": w60.pass_rate_pct,
            "w60_pass": w60.passed,
            "w60_attempts": w60.attempts,
            "w60_med_days": w60.median_days_to_meta,
            "w30_rate": w30.pass_rate_pct,
            "full_trades": r.metrics["n_trades"],
            "tpm": round(r.metrics["n_trades"] / 63, 2),
            "full_pnl": round(r.total_pnl, 2),
            "full_dd": ev["static_dd_pct"],
            "full_pass": ev["checks"]["pass_all"],
        })
        print(f"  ✓ EMA {p['fast_period']}/{p['slow_period']} TP{p['tp_ratio']} 60d={w60.pass_rate_pct}%", flush=True)

    survivors.sort(key=lambda x: (x["w60_rate"], x["w30_rate"]), reverse=True)
    print(f"\nSurvivors rolling 60d: {len(survivors)}\n", flush=True)
    for j, x in enumerate(survivors[:10], 1):
        print(f"{j}. EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} {x['sess_start']}-{x['sess_end']} | 60d {x['w60_rate']}%", flush=True)

    best = survivors[0] if survivors else None
    OUT.write_text(json.dumps({"survivors": len(survivors), "best": best, "top": survivors[:10]}, indent=2), encoding="utf-8")
    print(f"Guardado {OUT}", flush=True)


if __name__ == "__main__":
    main()
