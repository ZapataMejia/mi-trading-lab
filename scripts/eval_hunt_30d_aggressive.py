#!/usr/bin/env python3
"""Hunt agresivo: ¿qué config PASA eval WS en ventana ≤30 días?"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.hedged_eval import run_hedged_backtest, simulate_hedged_windows
from webapp.backend.engine.ws_eval import evaluate_ws_classic, simulate_eval_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hunt_30d_results.json"


def load() -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def build_grid() -> list[dict]:
    emas = [
        (2, 4), (2, 5), (2, 6), (3, 5), (3, 6), (3, 7), (3, 8),
        (4, 7), (4, 8), (4, 9), (5, 9), (5, 11), (6, 14), (8, 18),
        (9, 18), (9, 20),
    ]
    sessions = [
        (600, 1000), (600, 1200), (600, 1400), (600, 1600),
        (700, 1000), (700, 1100), (700, 1200), (700, 1400), (700, 1600),
        (800, 1000), (800, 1100), (800, 1200), (800, 1400), (800, 1600),
    ]
    offsets = [0, 2, 5, 7]
    tps = [1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
    max_td = [1, 2]
    grid = []
    for (f, s), (ss, se), off, tp, mtd in itertools.product(emas, sessions, offsets, tps, max_td):
        if s <= f:
            continue
        grid.append({
            "fast_period": f, "slow_period": s, "risk_pct": 2.1, "tp_ratio": tp,
            "sess_start": ss, "sess_end": se, "max_trades_per_day": mtd,
            "broker_utc_offset_hours": off,
        })
    return grid


def probe_30d(bars: pd.DataFrame, cfg: FondeoConfig, starts: list[str]) -> tuple[bool, int | None]:
    """¿Algún tramo fijo de 30d pasa eval completa?"""
    for s in starts:
        e = pd.Timestamp(s, tz="UTC") + pd.Timedelta(days=30)
        chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < e)]
        if len(chunk) < 400:
            continue
        r = run_fondeo_backtest(chunk, cfg)
        ev = evaluate_ws_classic(r, cfg)
        if ev["checks"]["pass_all"]:
            return True, ev["days_to_meta"]
    return False, None


def main() -> None:
    bars = load()
    grid = build_grid()
    probe_starts = [
        "2017-03-01", "2017-09-01", "2018-03-01", "2018-09-01",
        "2019-03-01", "2019-09-01", "2020-03-01", "2020-09-01",
        "2021-03-01", "2021-09-01",
    ]
    print(f"HUNT 30d AGRESIVO — {len(grid)} combos\n", flush=True)

    survivors: list[dict] = []
    for i, p in enumerate(grid, 1):
        if i % 500 == 0:
            print(f"  probe {i}/{len(grid)} survivors={len(survivors)}", flush=True)
        cfg = FondeoConfig(**p, mm_risk_pct=2.1, equity_sample_bars=24)
        ok, days = probe_30d(bars, cfg, probe_starts)
        if not ok:
            continue
        w30 = simulate_eval_windows(bars, cfg, window_days=30, step="MS")
        w14 = simulate_eval_windows(bars, cfg, window_days=14, step="MS")
        survivors.append({
            **p,
            "probe_days": days,
            "w30_rate": w30.pass_rate_pct,
            "w30_pass": w30.passed,
            "w30_attempts": w30.attempts,
            "w30_med": w30.median_days_to_meta,
            "w14_rate": w14.pass_rate_pct,
            "w14_pass": w14.passed,
        })

    survivors.sort(key=lambda x: (x["w30_rate"], x["w14_rate"], x["w30_pass"]), reverse=True)
    print(f"\nSurvivors probe+rolling: {len(survivors)}\n", flush=True)

    top = survivors[:20]
    for j, x in enumerate(top, 1):
        print(
            f"{j}. EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} "
            f"{x['sess_start']}-{x['sess_end']} off{x['broker_utc_offset_hours']} mtd{x['max_trades_per_day']} | "
            f"30d {x['w30_rate']}% ({x['w30_pass']}/{x['w30_attempts']}) med={x['w30_med']}d",
            flush=True,
        )

    # Hedge en top 5 single
    hedge_results: list[dict] = []
    for p in survivors[:15]:
        cfg = FondeoConfig(**{k: p[k] for k in FondeoConfig.__dataclass_fields__ if k in p}, mm_risk_pct=2.1, equity_sample_bars=24)
        h = simulate_hedged_windows(bars, cfg, window_days=30, step="MS", commission_usd=3)
        if h.pair_wins > 0:
            hedge_results.append({**p, "hedge_30d": h.pass_rate_pct, "hedge_wins": h.pair_wins})

    OUT.write_text(
        json.dumps({"survivors": len(survivors), "top": top, "hedge_top": hedge_results[:10]}, indent=2),
        encoding="utf-8",
    )
    print(f"\nGuardado {OUT}", flush=True)
    if not survivors:
        print("RESULTADO: 0 configs pasan eval en 30d con motor EMA actual.", flush=True)


if __name__ == "__main__":
    main()
