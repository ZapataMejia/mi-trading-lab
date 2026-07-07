#!/usr/bin/env python3
"""WS hunt v4 — scan en 1 año (rápido) + validación full + ventanas eval."""
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
FULL_START, FULL_END = "2017-01-03", "2022-03-31"
SCAN_START, SCAN_END = "2020-01-01", "2022-03-31"


def load(start: str, end: str):
    df = _normalize_ohlc(__import__("pandas").read_csv(CSV))
    return df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].reset_index(drop=True)


def eval_cfg(bars, p: dict) -> dict | None:
    cfg = FondeoConfig(**p, mm_risk_pct=p["risk_pct"])
    r = run_fondeo_backtest(bars, cfg)
    if r.metrics["n_trades"] < 6:
        return None
    ev = evaluate_ws_classic(r, cfg)
    months = max(1, (bars["timestamp"].max() - bars["timestamp"].min()).days / 30)
    tpm = r.metrics["n_trades"] / months
    return {
        **p,
        "trades": r.metrics["n_trades"],
        "tpm": round(tpm, 2),
        "pnl": round(r.total_pnl, 2),
        "dd": ev["static_dd_pct"],
        "daily_dd": ev["max_daily_loss_pct"],
        "pf": round(min(r.metrics["profit_factor"] or 0, 999), 2),
        "full_pass": ev["checks"]["pass_all"],
        "pass_static": ev["checks"]["pass_static_dd"],
        "pass_daily": ev["checks"]["pass_daily_dd"],
    }


def build_grid() -> list[dict]:
    grid: list[dict] = []
    emas = [(3, 8), (4, 9), (5, 11), (6, 14), (7, 16), (8, 18), (9, 18), (9, 20), (9, 26), (12, 26)]
    sessions = [(700, 1100), (700, 1200), (800, 900), (800, 1000), (800, 1100), (800, 1200), (800, 1400)]
    for fast, slow in emas:
        for tp in [0.8, 1.0, 1.2, 1.5, 2.0, 2.5]:
            for ss, se in sessions:
                grid.append({
                    "fast_period": fast, "slow_period": slow, "risk_pct": 2.1,
                    "tp_ratio": tp, "sess_start": ss, "sess_end": se,
                    "max_trades_per_day": 2, "broker_utc_offset_hours": 7,
                })
    return grid


def main() -> None:
    scan_bars = load(SCAN_START, SCAN_END)
    full_bars = load(FULL_START, FULL_END)
    grid = build_grid()
    print(f"WS HUNT v4 — scan {len(scan_bars):,} barras · full {len(full_bars):,} · {len(grid)} combos\n", flush=True)

    rough: list[dict] = []
    for i, p in enumerate(grid, 1):
        if i % 50 == 0:
            print(f"  scan {i}/{len(grid)} ok={len(rough)}", flush=True)
        m = eval_cfg(scan_bars, p)
        if m and m["pass_static"] and m["pf"] >= 1.0 and m["tpm"] >= 1.0:
            rough.append(m)

    rough.sort(key=lambda x: (x["full_pass"], x["tpm"], x["pnl"]), reverse=True)
    print(f"\nScan 2y: {len(rough)} candidatas\n", flush=True)

    exact: list[dict] = []
    for p in rough[:60]:
        keys = {k: p[k] for k in FondeoConfig.__dataclass_fields__ if k in p}
        m = eval_cfg(full_bars, keys)
        if m and m["pass_static"] and m["pass_daily"] and m["pf"] >= 1.0:
            exact.append(m)

    exact.sort(key=lambda x: (x["full_pass"], x["tpm"], x["pnl"]), reverse=True)
    print(f"Full 5y: {len(exact)} pasan DD\n", flush=True)

    survivors: list[dict] = []
    for p in exact[:35]:
        keys = {k: p[k] for k in FondeoConfig.__dataclass_fields__ if k in p}
        cfg = FondeoConfig(**keys, mm_risk_pct=2.1)
        w14 = simulate_eval_windows(full_bars, cfg, 14, step="2MS")
        w30 = simulate_eval_windows(full_bars, cfg, 30, step="2MS")
        w60 = simulate_eval_windows(full_bars, cfg, 60, step="2MS")
        if not any(w.passed for w in (w14, w30, w60)):
            continue
        row = {
            **keys,
            "full_trades": p["trades"],
            "trades_per_month": p["tpm"],
            "full_pnl": p["pnl"],
            "full_dd": p["dd"],
            "full_pf": p["pf"],
            "full_pass": p["full_pass"],
            "w14": w14.pass_rate_pct, "w14_n": f"{w14.passed}/{w14.attempts}",
            "w30": w30.pass_rate_pct, "w30_n": f"{w30.passed}/{w30.attempts}",
            "w60": w60.pass_rate_pct, "w60_n": f"{w60.passed}/{w60.attempts}",
            "w60_med": w60.median_days_to_meta,
        }
        survivors.append(row)
        print(
            f"  ✓ EMA {p['fast_period']}/{p['slow_period']} TP{p['tp_ratio']} "
            f"{p['sess_start']}-{p['sess_end']} | 30d={w30.pass_rate_pct}% 60d={w60.pass_rate_pct}%",
            flush=True,
        )

    survivors.sort(key=lambda x: (x["w60"], x["w30"], x["full_pass"]), reverse=True)
    print(f"\nSurvivors: {len(survivors)}\n", flush=True)

    best = survivors[0] if survivors else (exact[0] if exact else (rough[0] if rough else None))
    if best and not survivors:
        best = {**{k: best[k] for k in best if k in FondeoConfig.__dataclass_fields__ or k in (
            "trades", "tpm", "pnl", "dd", "pf", "full_pass")}, "fallback_full_period": True,
                "full_trades": best.get("trades"), "full_pnl": best.get("pnl"),
                "full_dd": best.get("dd"), "full_pf": best.get("pf")}

    OUT.write_text(json.dumps({"survivors": len(survivors), "best": best, "top": survivors[:10]}, indent=2), encoding="utf-8")
    print(f"Guardado {OUT}\n", flush=True)
    if best:
        print(json.dumps(best, indent=2), flush=True)


if __name__ == "__main__":
    main()
