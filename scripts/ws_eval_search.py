#!/usr/bin/env python3
"""Búsqueda WS eval optimizada — ventanas solo en top candidatas."""
from __future__ import annotations

import itertools
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
OUT = ROOT / "data/forex_cache/ws_eval_best.json"
START, END = "2017-01-03", "2022-03-31"
# Arranques cada 6 meses (más rápido que mensual)
WINDOW_STEP = "6MS"


def load() -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= START) & (df["timestamp"] <= END)].reset_index(drop=True)


def score_full(ev: dict, r) -> float:
    s = r.total_pnl
    if ev["checks"]["pass_all"]:
        s += 3000
    elif ev["checks"]["pass_meta"] and ev["checks"]["pass_static_dd"]:
        s += 1000
    s += ev["checks"]["pass_static_dd"] * 500
    s += min(r.metrics["profit_factor"], 3) * 100
    return s


def main() -> None:
    bars = load()
    print(f"WS EVAL FAST — {len(bars):,} barras\n", flush=True)

    grid = {
        "fast_period": [5, 7, 9],
        "slow_period": [15, 18, 20, 26],
        "risk_pct": [2.1],
        "tp_ratio": [1.0, 1.2, 1.5, 2.0],
        "sess_start": [700, 800],
        "sess_end": [1000, 1100, 1200],
        "max_trades_per_day": [2],
        "broker_utc_offset_hours": [7],
    }

    keys = list(grid.keys())
    phase1: list[dict] = []
    total = 0

    for combo in itertools.product(*grid.values()):
        params = dict(zip(keys, combo))
        if params["slow_period"] <= params["fast_period"] or params["sess_end"] <= params["sess_start"]:
            continue
        total += 1
        cfg = FondeoConfig(**params, mm_risk_pct=params["risk_pct"])
        r = run_fondeo_backtest(bars, cfg)
        if r.metrics["n_trades"] < 10:
            continue
        ev = evaluate_ws_classic(r, cfg)
        if not ev["checks"]["pass_static_dd"]:
            continue
        phase1.append({"params": params, "cfg": cfg, "r": r, "ev": ev, "full_score": score_full(ev, r)})

    phase1.sort(key=lambda x: x["full_score"], reverse=True)
    print(f"Fase 1: {len(phase1)}/{total} con DD≤8%\n", flush=True)

    top_n = min(25, len(phase1))
    print(f"Fase 2: ventanas 14/30d en top {top_n}...\n", flush=True)

    candidates = []
    for item in phase1[:top_n]:
        cfg = item["cfg"]
        params = item["params"]
        w14 = simulate_eval_windows(bars, cfg, 14, step=WINDOW_STEP)
        w30 = simulate_eval_windows(bars, cfg, 30, step=WINDOW_STEP)
        ev = item["ev"]
        r = item["r"]
        candidates.append({
            **params,
            "full_trades": r.metrics["n_trades"],
            "full_pnl": round(r.total_pnl, 2),
            "full_dd": ev["static_dd_pct"],
            "full_pf": round(min(r.metrics["profit_factor"], 999), 2),
            "full_pass": ev["checks"]["pass_all"],
            "w14_rate": w14.pass_rate_pct,
            "w14_pass": w14.passed,
            "w14_attempts": w14.attempts,
            "w14_med_days": w14.median_days_to_meta,
            "w30_rate": w30.pass_rate_pct,
            "w30_pass": w30.passed,
            "w30_attempts": w30.attempts,
            "score": w14.pass_rate_pct * 10 + w30.pass_rate_pct * 5 + (2000 if ev["checks"]["pass_all"] else 0),
        })

    candidates.sort(key=lambda x: (x["w14_rate"], x["w30_rate"], x["full_pass"], x["score"]), reverse=True)

    print("TOP 12:")
    print("-" * 72)
    for i, x in enumerate(candidates[:12], 1):
        print(
            f"{i:2}. EMA {x['fast_period']}/{x['slow_period']} TP={x['tp_ratio']} "
            f"sess {x['sess_start']}-{x['sess_end']} max/d={x['max_trades_per_day']}"
        )
        print(
            f"    Full: {x['full_trades']}t ${x['full_pnl']} DD {x['full_dd']}% PF {x['full_pf']} "
            f"pass={'SI' if x['full_pass'] else 'NO'} | "
            f"14d {x['w14_pass']}/{x['w14_attempts']} ({x['w14_rate']}%) | "
            f"30d {x['w30_pass']}/{x['w30_attempts']} ({x['w30_rate']}%)"
        )

    best = next((x for x in candidates if x["full_pass"] and x["w14_rate"] > 0), candidates[0] if candidates else None)
    payload = {"searched": total, "phase1": len(phase1), "top12": candidates[:12], "best": best}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nGuardado {OUT}", flush=True)
    if best:
        print("\nMEJOR:", json.dumps(best, indent=2), flush=True)


if __name__ == "__main__":
    main()
