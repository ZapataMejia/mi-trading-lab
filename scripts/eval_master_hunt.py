#!/usr/bin/env python3
"""Hunt rápido 2 fases: scan → ventanas eval en top candidatas."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.hedged_eval import simulate_hedged_windows
from webapp.backend.engine.london_breakout_engine import LondonBreakoutConfig, run_london_breakout
from webapp.backend.engine.ws_eval import evaluate_ws_classic, simulate_eval_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/eval_master_hunt.json"


def load(start: str = "2017-01-03", end: str = "2022-03-31") -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].reset_index(drop=True)


def ema_grid() -> list[dict]:
    emas = [(3, 8), (4, 9), (5, 11), (6, 14), (8, 18), (9, 18), (9, 20), (12, 26)]
    sessions = [(700, 1100), (700, 1200), (800, 1000), (800, 1100), (800, 1200), (800, 1400)]
    offsets = [0, 2, 7]
    tps = [1.0, 1.5, 2.0, 2.5, 3.0]
    out = []
    for (f, s), (ss, se), off, tp in itertools.product(emas, sessions, offsets, tps):
        out.append({
            "fast_period": f, "slow_period": s, "risk_pct": 2.1, "tp_ratio": tp,
            "sess_start": ss, "sess_end": se, "max_trades_per_day": 2,
            "broker_utc_offset_hours": off,
        })
    return out


def london_grid() -> list[dict]:
    out = []
    for mode in ("breakout", "fade"):
        for tp in (1.0, 1.5, 2.0):
            for off in (0, 2, 7):
                for ts, te in ((700, 1100), (800, 1100), (800, 1200)):
                    out.append({
                        "mode": mode, "tp_range_mult": tp, "broker_utc_offset_hours": off,
                        "trade_start": ts, "trade_end": te, "asian_start": 0, "asian_end": 700,
                        "risk_pct": 2.1, "max_trades_per_day": 2,
                    })
    return out


def main() -> None:
    full = load()
    scan = load("2020-01-01", "2022-03-31")
    print(f"EVAL MASTER HUNT — scan {len(scan):,} · full {len(full):,}\n", flush=True)

    # --- EMA single: fase 1 scan ---
    ema_cands: list[dict] = []
    for i, p in enumerate(ema_grid(), 1):
        if i % 200 == 0:
            print(f"  ema scan {i} ok={len(ema_cands)}", flush=True)
        cfg = FondeoConfig(**p, mm_risk_pct=2.1, equity_sample_bars=12)
        r = run_fondeo_backtest(scan, cfg)
        if r.metrics["n_trades"] < 15:
            continue
        ev = evaluate_ws_classic(r, cfg)
        months = max(1, (scan["timestamp"].max() - scan["timestamp"].min()).days / 30)
        tpm = r.metrics["n_trades"] / months
        if ev["checks"]["pass_static_dd"] and ev["checks"]["pass_daily_dd"] and tpm >= 0.8:
            ema_cands.append({**p, "scan_pnl": r.total_pnl, "scan_trades": r.metrics["n_trades"], "tpm": round(tpm, 2)})

    ema_cands.sort(key=lambda x: (x["scan_pnl"], x["tpm"]), reverse=True)
    ema_cands = ema_cands[:40]
    print(f"\nEMA scan: {len(ema_cands)} candidatas → ventanas\n", flush=True)

    best_single: list[dict] = []
    for p in ema_cands:
        cfg = FondeoConfig(**{k: p[k] for k in FondeoConfig.__dataclass_fields__ if k in p}, mm_risk_pct=2.1, equity_sample_bars=12)
        w14 = simulate_eval_windows(full, cfg, window_days=14, step="2MS")
        w30 = simulate_eval_windows(full, cfg, window_days=30, step="2MS")
        r = run_fondeo_backtest(full, cfg)
        ev = evaluate_ws_classic(r, cfg)
        if w14.passed == 0 and w30.passed == 0 and not ev["checks"]["pass_all"]:
            continue
        best_single.append({
            **p,
            "single_14d": w14.pass_rate_pct,
            "single_14d_w": w14.passed,
            "single_30d": w30.pass_rate_pct,
            "single_30d_w": w30.passed,
            "full_pass": ev["checks"]["pass_all"],
            "full_pnl": round(r.total_pnl, 2),
            "dd": ev["static_dd_pct"],
        })
    best_single.sort(key=lambda x: (x["single_14d"], x["single_30d"], x["full_pass"]), reverse=True)

    # --- Hedge top EMA ---
    best_hedge: list[dict] = []
    for p in ema_cands[:25]:
        cfg = FondeoConfig(**{k: p[k] for k in FondeoConfig.__dataclass_fields__ if k in p}, mm_risk_pct=2.1, equity_sample_bars=12)
        h14 = simulate_hedged_windows(full, cfg, window_days=14, step="2MS", commission_usd=3)
        h30 = simulate_hedged_windows(full, cfg, window_days=30, step="2MS", commission_usd=3)
        if h14.pair_wins == 0 and h30.pair_wins == 0:
            continue
        best_hedge.append({
            **p,
            "hedge_14d": h14.pass_rate_pct,
            "hedge_14d_w": h14.pair_wins,
            "hedge_30d": h30.pass_rate_pct,
            "hedge_med": h14.median_days,
        })
    best_hedge.sort(key=lambda x: x["hedge_14d"], reverse=True)

    # --- London breakout ---
    print("\nLondon breakout scan...\n", flush=True)
    london_cands: list[dict] = []
    for p in london_grid():
        cfg = LondonBreakoutConfig(**p, mm_risk_pct=2.1)
        r = run_london_breakout(scan, cfg)
        if r.metrics["n_trades"] < 10:
            continue
        ev = evaluate_ws_classic(r, cfg)  # type: ignore[arg-type]
        if ev["checks"]["pass_static_dd"]:
            london_cands.append({**p, "scan_pnl": r.total_pnl, "trades": r.metrics["n_trades"]})
    london_cands.sort(key=lambda x: x["scan_pnl"], reverse=True)
    london_cands = london_cands[:20]

    best_london: list[dict] = []
    for p in london_cands:
        cfg = LondonBreakoutConfig(**{k: p[k] for k in LondonBreakoutConfig.__dataclass_fields__ if k in p}, mm_risk_pct=2.1)
        w14 = simulate_eval_windows(full, cfg, window_days=14, step="2MS")  # needs adapter - use FondeoConfig wrapper issue
        # London uses different config - run window sim manually
        from webapp.backend.engine.london_breakout_engine import run_london_breakout as rl
        passed14 = passed30 = 0
        total14 = total30 = 0
        starts = pd.date_range("2017-01-03", "2021-06-01", freq="2MS", tz="UTC")
        for s in starts:
            for days, bucket in ((14, "14"), (30, "30")):
                e = s + pd.Timedelta(days=days)
                chunk = full[(full["timestamp"] >= s) & (full["timestamp"] < e)]
                if len(chunk) < 500:
                    continue
                rr = rl(chunk, cfg)
                ev = evaluate_ws_classic(rr, cfg)  # type: ignore[arg-type]
                if days == 14:
                    total14 += 1
                    if ev["checks"]["pass_all"]:
                        passed14 += 1
                else:
                    total30 += 1
                    if ev["checks"]["pass_all"]:
                        passed30 += 1
        r14 = round(100 * passed14 / total14, 1) if total14 else 0
        r30 = round(100 * passed30 / total30, 1) if total30 else 0
        if passed14 == 0 and passed30 == 0:
            continue
        rf = run_london_breakout(full, cfg)
        evf = evaluate_ws_classic(rf, cfg)  # type: ignore[arg-type]
        best_london.append({**p, "single_14d": r14, "single_14d_w": passed14, "single_30d": r30, "full_pass": evf["checks"]["pass_all"], "full_pnl": rf.total_pnl})

    best_london.sort(key=lambda x: (x["single_14d"], x["single_30d"]), reverse=True)

    print("=== TOP SINGLE EMA ===", flush=True)
    for x in best_single[:5]:
        print(f"  EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} {x['sess_start']}-{x['sess_end']} off{x['broker_utc_offset_hours']} | 14d {x['single_14d']}% 30d {x['single_30d']}% full={x['full_pass']}", flush=True)
    print("\n=== TOP HEDGE ===", flush=True)
    for x in best_hedge[:5]:
        print(f"  EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} | hedge 14d {x['hedge_14d']}%", flush=True)
    if not best_hedge:
        print("  (ninguna)", flush=True)
    print("\n=== TOP LONDON ===", flush=True)
    for x in best_london[:5]:
        print(f"  {x['mode']} TP{x['tp_range_mult']} {x['trade_start']}-{x['trade_end']} | 14d {x['single_14d']}% 30d {x['single_30d']}%", flush=True)
    if not best_london:
        print("  (ninguna)", flush=True)

    report = {
        "best_single_ema": best_single[:10],
        "best_hedge": best_hedge[:10],
        "best_london": best_london[:10],
        "recommendation": _recommend(best_single, best_hedge, best_london),
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{report['recommendation']}\nGuardado {OUT}", flush=True)


def _recommend(single, hedge, london) -> str:
    if single and single[0].get("single_14d", 0) >= 20:
        x = single[0]
        return f"Usar SINGLE EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} sesión {x['sess_start']}-{x['sess_end']} offset {x['broker_utc_offset_hours']}"
    if london and london[0].get("single_14d", 0) >= 15:
        x = london[0]
        return f"Usar LONDON {x['mode']} TP mult {x['tp_range_mult']} ventana {x['trade_start']}-{x['trade_end']}"
    if hedge and hedge[0].get("hedge_14d", 0) >= 15:
        x = hedge[0]
        return f"Usar HEDGE EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']}"
    if single and single[0].get("full_pass"):
        return "Ninguna ventana 14d fiable; config pasa periodo largo — eval lenta, no semanas"
    return "Sin config fiable en histórico; demo VPS 2 semanas obligatoria"


if __name__ == "__main__":
    main()
