#!/usr/bin/env python3
"""WS hunt v3 — scan rápido + revalidación DD exacta + ventanas eval."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.ws_eval import evaluate_ws_classic, simulate_eval_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/ws_eval_best.json"


def load():
    df = _normalize_ohlc(__import__("pandas").read_csv(CSV))
    return df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def eval_cfg(bars, p: dict, sample: int = 1) -> dict | None:
    cfg = FondeoConfig(**p, mm_risk_pct=p["risk_pct"], equity_sample_bars=sample)
    r = run_fondeo_backtest(bars, cfg)
    if r.metrics["n_trades"] < 12:
        return None
    ev = evaluate_ws_classic(r, cfg)
    return {
        **p,
        "trades": r.metrics["n_trades"],
        "tpm": round(r.metrics["n_trades"] / 63, 2),
        "pnl": round(r.total_pnl, 2),
        "dd": ev["static_dd_pct"],
        "daily_dd": ev["max_daily_loss_pct"],
        "pf": round(min(r.metrics["profit_factor"] or 0, 999), 2),
        "full_pass": ev["checks"]["pass_all"],
        "pass_static": ev["checks"]["pass_static_dd"],
        "pass_daily": ev["checks"]["pass_daily_dd"],
        "pass_meta": ev["checks"]["pass_meta"],
        "pass_min_days": ev["checks"]["pass_min_days"],
        "trading_days": ev["trading_days"],
    }


def build_grid() -> list[dict]:
    grid: list[dict] = []
    emas = [
        (3, 8), (4, 9), (5, 11), (5, 13), (6, 14), (7, 16),
        (8, 18), (9, 18), (9, 20), (9, 26), (12, 26),
    ]
    sessions = [
        (700, 1000), (700, 1100), (700, 1200),
        (800, 900), (800, 1000), (800, 1100), (800, 1200), (800, 1400),
    ]
    for fast, slow in emas:
        for tp in [0.8, 1.0, 1.2, 1.5, 2.0, 2.5]:
            for ss, se in sessions:
                for risk in [2.0, 2.1]:
                    for off in [7]:
                        grid.append({
                            "fast_period": fast,
                            "slow_period": slow,
                            "risk_pct": risk,
                            "tp_ratio": tp,
                            "sess_start": ss,
                            "sess_end": se,
                            "max_trades_per_day": 2,
                            "broker_utc_offset_hours": off,
                        })
    return grid


def main() -> None:
    bars = load()
    grid = build_grid()
    print(f"WS HUNT v3 — {len(bars):,} barras · {len(grid)} combos\n", flush=True)

    # Fase 1: scan rápido
    rough: list[dict] = []
    for i, p in enumerate(grid, 1):
        if i % 100 == 0:
            print(f"  scan {i}/{len(grid)} rough={len(rough)}", flush=True)
        m = eval_cfg(bars, p, sample=24)
        if m and m["pass_static"] and m["pf"] >= 0.95 and m["tpm"] >= 0.5:
            rough.append(m)

    rough.sort(key=lambda x: (x["full_pass"], x["tpm"], x["pnl"]), reverse=True)
    print(f"\nFase 1: {len(rough)} candidatas rough\n", flush=True)

    # Fase 2: DD exacto
    exact: list[dict] = []
    for p in rough[:80]:
        keys = {k: p[k] for k in FondeoConfig.__dataclass_fields__ if k in p}
        m = eval_cfg(bars, keys, sample=1)
        if m and m["pass_static"] and m["pass_daily"]:
            exact.append(m)

    exact.sort(key=lambda x: (x["full_pass"], x["tpm"], x["pnl"]), reverse=True)
    print(f"Fase 2: {len(exact)} pasan DD exacto\n", flush=True)

    # Fase 3: ventanas eval
    survivors: list[dict] = []
    for j, p in enumerate(exact[:40], 1):
        keys = {k: p[k] for k in FondeoConfig.__dataclass_fields__ if k in p}
        cfg = FondeoConfig(**keys, mm_risk_pct=keys["risk_pct"], equity_sample_bars=1)
        w14 = simulate_eval_windows(bars, cfg, 14, step="2MS")
        w30 = simulate_eval_windows(bars, cfg, 30, step="2MS")
        w60 = simulate_eval_windows(bars, cfg, 60, step="2MS")
        if not any(w.passed for w in (w14, w30, w60)):
            continue
        survivors.append({
            **keys,
            "full_trades": p["trades"],
            "trades_per_month": p["tpm"],
            "full_pnl": p["pnl"],
            "full_dd": p["dd"],
            "full_pf": p["pf"],
            "full_pass": p["full_pass"],
            "w14": w14.pass_rate_pct,
            "w14_n": f"{w14.passed}/{w14.attempts}",
            "w30": w30.pass_rate_pct,
            "w30_n": f"{w30.passed}/{w30.attempts}",
            "w60": w60.pass_rate_pct,
            "w60_n": f"{w60.passed}/{w60.attempts}",
            "w60_med": w60.median_days_to_meta,
        })
        print(
            f"  ✓ EMA {p['fast_period']}/{p['slow_period']} TP{p['tp_ratio']} "
            f"{p['sess_start']}-{p['sess_end']} | 60d {w60.pass_rate_pct}%",
            flush=True,
        )

    survivors.sort(key=lambda x: (x["w60"], x["w30"], x["full_pass"]), reverse=True)
    print(f"\nSurvivors: {len(survivors)}\n", flush=True)

    best = survivors[0] if survivors else (exact[0] if exact else (rough[0] if rough else None))
    if best:
        best = {k: v for k, v in best.items() if k != "equity_sample_bars"}
        if not survivors:
            best["fallback_full_period"] = True

    payload = {
        "survivors": len(survivors),
        "best": best,
        "top": survivors[:10],
        "exact_count": len(exact),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Guardado {OUT}\n", flush=True)
    if best:
        print(json.dumps(best, indent=2), flush=True)


if __name__ == "__main__":
    main()
