#!/usr/bin/env python3
"""WS hunt v2 — sin guardar equity en memoria."""
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
OUT = ROOT / "data/forex_cache/ws_eval_best.json"


def load() -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def metrics_only(bars, cfg) -> dict | None:
    r = run_fondeo_backtest(bars, cfg)
    if r.metrics["n_trades"] < 10:
        return None
    ev = evaluate_ws_classic(r, cfg)
    if not ev["checks"]["pass_static_dd"]:
        return None
    return {
        "trades": r.metrics["n_trades"],
        "tpm": round(r.metrics["n_trades"] / 63, 2),
        "pnl": round(r.total_pnl, 2),
        "dd": ev["static_dd_pct"],
        "pf": round(min(r.metrics["profit_factor"] or 0, 999), 2),
        "full_pass": ev["checks"]["pass_all"],
    }


def main() -> None:
    bars = load()
    print(f"WS HUNT v2 — {len(bars):,} barras\n", flush=True)

    ema = [(3, 8), (4, 9), (5, 11), (5, 13), (6, 14), (7, 16), (8, 18), (9, 18), (9, 20), (9, 26)]
    grid = []
    for fast, slow in ema:
        for tp in [0.8, 1.0, 1.2, 1.5, 2.0]:
            for ss, se in [(700, 1200), (700, 1400), (800, 1100), (800, 1200), (800, 1400), (800, 1600)]:
                grid.append({
                    "fast_period": fast, "slow_period": slow, "risk_pct": 2.1,
                    "tp_ratio": tp, "sess_start": ss, "sess_end": se,
                    "max_trades_per_day": 2, "broker_utc_offset_hours": 7,
                })

    print(f"Combos: {len(grid)}\n", flush=True)
    ranked: list[dict] = []

    for i, p in enumerate(grid, 1):
        if i % 50 == 0:
            print(f"  scan {i}/{len(grid)} ok={len(ranked)}", flush=True)
        cfg = FondeoConfig(**p, mm_risk_pct=2.1, equity_sample_bars=12)
        m = metrics_only(bars, cfg)
        if m:
            ranked.append({**p, **m})

    ranked.sort(key=lambda x: (x["full_pass"], x["tpm"], x["pnl"]), reverse=True)
    top = ranked[:30]
    print(f"\nDD ok: {len(ranked)} | ventanas top {len(top)}\n", flush=True)

    survivors: list[dict] = []
    for j, p in enumerate(top, 1):
        cfg = FondeoConfig(**{k: p[k] for k in p if k in FondeoConfig.__dataclass_fields__}, mm_risk_pct=2.1, equity_sample_bars=12)
        w14 = simulate_eval_windows(bars, cfg, 14, step="2MS")
        w30 = simulate_eval_windows(bars, cfg, 30, step="2MS")
        w60 = simulate_eval_windows(bars, cfg, 60, step="2MS")
        w90 = simulate_eval_windows(bars, cfg, 90, step="2MS")
        if not any(w.passed for w in (w14, w30, w60, w90)):
            continue
        survivors.append({
            **{k: p[k] for k in p if k not in ("trades", "tpm", "pnl", "dd", "pf", "full_pass")},
            "full_trades": p["trades"], "trades_per_month": p["tpm"],
            "full_pnl": p["pnl"], "full_dd": p["dd"], "full_pf": p["pf"], "full_pass": p["full_pass"],
            "w14": w14.pass_rate_pct, "w14_n": f"{w14.passed}/{w14.attempts}",
            "w30": w30.pass_rate_pct, "w30_n": f"{w30.passed}/{w30.attempts}",
            "w60": w60.pass_rate_pct, "w60_n": f"{w60.passed}/{w60.attempts}",
            "w90": w90.pass_rate_pct, "w90_n": f"{w90.passed}/{w90.attempts}",
            "w60_med": w60.median_days_to_meta,
        })
        print(f"  ✓ {j} EMA {p['fast_period']}/{p['slow_period']} TP{p['tp_ratio']} 60d={w60.pass_rate_pct}%", flush=True)

    survivors.sort(key=lambda x: (x["w60"], x["w90"], x["w30"], x["full_pass"]), reverse=True)

    print(f"\nSurvivors: {len(survivors)}\n", flush=True)
    for i, x in enumerate(survivors[:10], 1):
        print(
            f"{i}. EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} {x['sess_start']}-{x['sess_end']} | "
            f"{x['full_trades']}t ${x['full_pnl']} DD{x['full_dd']}% | "
            f"60d {x['w60_n']} ({x['w60']}%) 90d {x['w90_n']} ({x['w90']}%)",
            flush=True,
        )

    best = survivors[0] if survivors else (ranked[0] if ranked else None)
    if best and "full_trades" not in best:
        best = {**best, "full_trades": best.get("trades"), "full_pnl": best.get("pnl"),
                "full_dd": best.get("dd"), "full_pf": best.get("pf"), "fallback_full_period": True}

    OUT.write_text(json.dumps({"survivors": len(survivors), "best": best, "top": survivors[:10]}, indent=2), encoding="utf-8")
    print(f"\nGuardado {OUT}", flush=True)


if __name__ == "__main__":
    main()
