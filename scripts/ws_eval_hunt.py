#!/usr/bin/env python3
"""Caza configs que pasen eval WS CLASSIC — prioriza ventanas 14/30/60 días."""
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
FULL_START, FULL_END = "2017-01-03", "2022-03-31"


def load() -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= FULL_START) & (df["timestamp"] <= FULL_END)].reset_index(drop=True)


def cfg_from(params: dict) -> FondeoConfig:
    return FondeoConfig(
        fast_period=params["fast_period"],
        slow_period=params["slow_period"],
        risk_pct=params["risk_pct"],
        tp_ratio=params["tp_ratio"],
        sess_start=params["sess_start"],
        sess_end=params["sess_end"],
        max_trades_per_day=params["max_trades_per_day"],
        mm_risk_pct=params["risk_pct"],
        broker_utc_offset_hours=params["broker_utc_offset_hours"],
        allow_long=params.get("allow_long", True),
        allow_short=params.get("allow_short", True),
    )


def label(p: dict) -> str:
    return (
        f"EMA {p['fast_period']}/{p['slow_period']} r={p['risk_pct']} TP={p['tp_ratio']} "
        f"{p['sess_start']}-{p['sess_end']} off={p['broker_utc_offset_hours']} max={p['max_trades_per_day']}/d"
    )


def main() -> None:
    bars = load()
    print(f"WS EVAL HUNT — {len(bars):,} barras\n", flush=True)

    ema_pairs = [(3, 8), (4, 9), (5, 11), (5, 13), (6, 14), (7, 16), (8, 18), (9, 20), (9, 26), (12, 26)]
    grid: list[dict] = []
    for fast, slow in ema_pairs:
        for tp in [0.8, 1.0, 1.2, 1.5, 2.0, 2.5]:
            for ss, se in [(700, 1100), (700, 1200), (700, 1400), (800, 1000), (800, 1100), (800, 1200), (800, 1400)]:
                for off in [7]:
                    for maxd in [2]:
                        grid.append({
                            "fast_period": fast, "slow_period": slow, "risk_pct": 2.1,
                            "tp_ratio": tp, "sess_start": ss, "sess_end": se,
                            "max_trades_per_day": maxd, "broker_utc_offset_hours": off,
                        })

    print(f"Grid: {len(grid)} combos\n", flush=True)
    phase1: list[dict] = []

    for i, params in enumerate(grid, 1):
        if i % 80 == 0:
            print(f"  fase1 {i}/{len(grid)} candidatas={len(phase1)}", flush=True)
        cfg = cfg_from(params)
        r = run_fondeo_backtest(bars, cfg)
        if r.metrics["n_trades"] < 15:
            continue
        ev = evaluate_ws_classic(r, cfg)
        if not ev["checks"]["pass_static_dd"] or not ev["checks"]["pass_daily_dd"]:
            continue
        tpm = r.metrics["n_trades"] / 63
        phase1.append({**params, "r": r, "ev": ev, "tpm": tpm})

    phase1.sort(key=lambda x: x["tpm"], reverse=True)
    top = phase1[:60]
    print(f"Fase1: {len(phase1)} DD ok | Fase2 ventanas en top {len(top)}\n", flush=True)

    survivors: list[dict] = []
    for j, item in enumerate(top, 1):
        if j % 10 == 0:
            print(f"  fase2 {j}/{len(top)} survivors={len(survivors)}", flush=True)
        params = {k: item[k] for k in item if k not in ("r", "ev", "tpm")}
        cfg = cfg_from(params)
        r, ev, tpm = item["r"], item["ev"], item["tpm"]
        w14 = simulate_eval_windows(bars, cfg, 14, step="MS")
        w30 = simulate_eval_windows(bars, cfg, 30, step="MS")
        w60 = simulate_eval_windows(bars, cfg, 60, step="MS")
        if w14.pass_rate_pct == 0 and w30.pass_rate_pct == 0 and w60.pass_rate_pct == 0:
            continue
        survivors.append({
            **params,
            "label": label(params),
            "full_trades": r.metrics["n_trades"],
            "trades_per_month": round(tpm, 2),
            "full_pnl": round(r.total_pnl, 2),
            "full_dd": ev["static_dd_pct"],
            "full_pf": round(min(r.metrics["profit_factor"] or 0, 999), 2),
            "full_pass": ev["checks"]["pass_all"],
            "w14": w14.pass_rate_pct, "w14_n": f"{w14.passed}/{w14.attempts}", "w14_med": w14.median_days_to_meta,
            "w30": w30.pass_rate_pct, "w30_n": f"{w30.passed}/{w30.attempts}",
            "w60": w60.pass_rate_pct, "w60_n": f"{w60.passed}/{w60.attempts}",
            "score": w14.pass_rate_pct * 20 + w30.pass_rate_pct * 10 + w60.pass_rate_pct * 5
            + (2000 if ev["checks"]["pass_all"] else 0) + tpm * 50,
        })

    survivors.sort(key=lambda x: (x["w14"], x["w30"], x["w60"], x["full_pass"], x["score"]), reverse=True)

    print(f"\nSurvivors (ventana eval >0%): {len(survivors)}\n", flush=True)
    print("TOP 15:")
    print("-" * 80)
    for i, x in enumerate(survivors[:15], 1):
        print(f"{i:2}. {x['label']}", flush=True)
        print(
            f"    Full: {x['full_trades']}t ({x['trades_per_month']}/mes) ${x['full_pnl']} DD{x['full_dd']}% "
            f"PF{x['full_pf']} pass={'SI' if x['full_pass'] else 'NO'}",
            flush=True,
        )
        print(
            f"    14d {x['w14_n']} ({x['w14']}%) med{x['w14_med']}d | "
            f"30d {x['w30_n']} ({x['w30']}%) | 60d {x['w60_n']} ({x['w60']}%)",
            flush=True,
        )

    # Validación por año en top 5
    print("\nValidación por año (top 5):", flush=True)
    for x in survivors[:5]:
        cfg = cfg_from(x)
        yrs = []
        for y in range(2017, 2023):
            chunk = bars[(bars["timestamp"] >= f"{y}-01-01") & (bars["timestamp"] < f"{y+1}-01-01")]
            if len(chunk) < 1000:
                continue
            r = run_fondeo_backtest(chunk, cfg)
            ev = evaluate_ws_classic(r, cfg)
            yrs.append(f"{y}:{'OK' if ev['checks']['pass_all'] else 'NO'}({r.metrics['n_trades']}t)")
        print(f"  {x['label'][:50]}", flush=True)
        print(f"    {' | '.join(yrs)}", flush=True)

    best = survivors[0] if survivors else None
    # Fallback: mejor full-pass con más trades/mes si ninguna ventana corta
    if not best and phase1:
        fallback = max(phase1, key=lambda x: (x["ev"]["checks"]["pass_all"], x["tpm"], x["r"].total_pnl))
        p = {k: fallback[k] for k in fallback if k not in ("r", "ev", "tpm")}
        best = {
            **p,
            "label": label(p),
            "full_trades": fallback["r"].metrics["n_trades"],
            "trades_per_month": round(fallback["tpm"], 2),
            "full_pnl": round(fallback["r"].total_pnl, 2),
            "full_dd": fallback["ev"]["static_dd_pct"],
            "full_pf": round(min(fallback["r"].metrics["profit_factor"] or 0, 999), 2),
            "full_pass": fallback["ev"]["checks"]["pass_all"],
            "w14": 0, "w30": 0, "w60": 0,
            "fallback": True,
        }
        print(f"\nFallback full-period: {best['label']}", flush=True)

    payload = {"survivors": len(survivors), "top15": survivors[:15], "best": best}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nGuardado {OUT}", flush=True)
    if best:
        print("\n🏆 MEJOR:", best["label"], flush=True)
    else:
        print("\n⚠ Ninguna config pasó ventanas 14/30/60d — ampliando criterio...", flush=True)


if __name__ == "__main__":
    main()
