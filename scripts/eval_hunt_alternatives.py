#!/usr/bin/env python3
"""Hunt estrategias alternativas (ICT, liquidity, London) vs eval WS 30d."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig
from webapp.backend.engine.ict_judas_engine import JudasConfig, run_judas_swing
from webapp.backend.engine.liquidity_sweep_engine import LiquiditySweepConfig, run_liquidity_sweep
from webapp.backend.engine.london_breakout_engine import LondonBreakoutConfig, run_london_breakout
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hunt_alternatives.json"


def load_bars() -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def ws_cfg(off: int = 7) -> FondeoConfig:
    return FondeoConfig(
        fast_period=9, slow_period=20, risk_pct=2.1, tp_ratio=1.0,
        sess_start=800, sess_end=1000, max_trades_per_day=2,
        broker_utc_offset_hours=off, equity_sample_bars=48,
    )


def eval_30d(bars, run_fn, cfg_obj, off: int) -> dict:
    starts = pd.date_range("2017-01-03", "2021-09-01", freq="MS", tz="UTC")
    passed = total = 0
    days_list: list[int] = []
    wcfg = ws_cfg(off)
    for s in starts:
        e = s + pd.Timedelta(days=30)
        chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < e)]
        if len(chunk) < 400:
            continue
        total += 1
        r = run_fn(chunk, cfg_obj)
        ev = evaluate_ws_classic(r, wcfg)
        if ev["checks"]["pass_all"]:
            passed += 1
            if ev["days_to_meta"] is not None:
                days_list.append(ev["days_to_meta"])
    med = sorted(days_list)[len(days_list) // 2] if days_list else None
    rate = round(100 * passed / total, 1) if total else 0.0
    return {"w30_pass": passed, "w30_total": total, "w30_rate": rate, "w30_med": med}


def score_full(bars, run_fn, cfg_obj, off: int) -> dict:
    r = run_fn(bars, cfg_obj)
    ev = evaluate_ws_classic(r, ws_cfg(off))
    w30 = eval_30d(bars, run_fn, cfg_obj, off)
    return {
        **w30,
        "full_pass": ev["checks"]["pass_all"],
        "full_pnl": round(r.total_pnl, 2),
        "full_dd": round(ev["static_dd_pct"], 2),
        "full_trades": r.metrics["n_trades"],
        "full_pf": round(min(r.metrics.get("profit_factor") or 0, 999), 2),
    }


def main() -> None:
    bars = load_bars()
    results: list[dict] = []

    # --- ICT Judas Swing (consenso internet #1 para Londres) ---
    judas_grid = list(itertools.product(
        [(0, 700), (0, 600), (100, 700)],
        [(700, 1000), (700, 1100), (800, 1000), (800, 1100)],
        ["asian_opposite", "range_mult"],
        [1.5, 2.0, 2.5],
        [6.0, 8.0, 12.0],
        [0, 7],
    ))
    print(f"ICT Judas: {len(judas_grid)} combos", flush=True)
    for i, ((as_, ae), (ks, ke), tp_mode, tp_mult, min_rng, off) in enumerate(judas_grid, 1):
        cfg = JudasConfig(
            asian_start=as_, asian_end=ae, kill_start=ks, kill_end=ke,
            tp_mode=tp_mode, tp_range_mult=tp_mult, min_asian_range_pips=min_rng,
            broker_utc_offset_hours=off, equity_sample_bars=48,
        )
        s = score_full(bars, run_judas_swing, cfg, off)
        row = {"strategy": "ict_judas", **cfg.to_dict(), **s}
        if s["full_trades"] >= 10:
            results.append(row)
        if s["w30_pass"] > 0:
            print(f"  HIT Judas {ks}-{ke} {tp_mode} off{off} | 30d {s['w30_rate']}%", flush=True)
        if i % 50 == 0:
            print(f"  judas {i}/{len(judas_grid)}", flush=True)

    # --- Liquidity sweep ---
    liq_grid = list(itertools.product(
        [12, 24, 36, 48],
        [1.5, 2.0, 2.5, 3.0],
        [(700, 1100), (700, 1400), (800, 1200)],
        [0, 7],
    ))
    print(f"\nLiquidity sweep: {len(liq_grid)} combos", flush=True)
    for i, (lb, tp, (ss, se), off) in enumerate(liq_grid, 1):
        cfg = LiquiditySweepConfig(
            lookback_bars=lb, tp_ratio=tp, sess_start=ss, sess_end=se,
            broker_utc_offset_hours=off, equity_sample_bars=48,
        )
        s = score_full(bars, run_liquidity_sweep, cfg, off)
        row = {"strategy": "liq_sweep", **cfg.to_dict(), **s}
        if s["full_trades"] >= 10:
            results.append(row)
        if s["w30_pass"] > 0:
            print(f"  HIT Liq lb={lb} TP{tp} | 30d {s['w30_rate']}%", flush=True)

    # --- London breakout + fade (re-test parametrizado) ---
    lon_grid = list(itertools.product(
        ["breakout", "fade"],
        [(0, 700), (0, 600)],
        [(700, 1100), (800, 1100)],
        [1.0, 1.5, 2.0],
        [0, 7],
    ))
    print(f"\nLondon: {len(lon_grid)} combos", flush=True)
    for mode, (as_, ae), (ts_, te), mult, off in lon_grid:
        cfg = LondonBreakoutConfig(
            asian_start=as_, asian_end=ae, trade_start=ts_, trade_end=te,
            tp_range_mult=mult, mode=mode, broker_utc_offset_hours=off, equity_sample_bars=48,
        )
        s = score_full(bars, run_london_breakout, cfg, off)
        row = {"strategy": f"london_{mode}", **cfg.to_dict(), **s}
        if s["full_trades"] >= 10:
            results.append(row)
        if s["w30_pass"] > 0:
            print(f"  HIT London {mode} | 30d {s['w30_rate']}%", flush=True)

    # Ranking: prioridad pass 30d, luego full pass, luego pnl
    results.sort(
        key=lambda x: (x["w30_rate"], x["w30_pass"], x["full_pass"], x["full_pnl"]),
        reverse=True,
    )
    survivors_30d = [r for r in results if r["w30_pass"] > 0]
    full_pass = [r for r in results if r["full_pass"]]

    print(f"\n=== RESUMEN ===", flush=True)
    print(f"Configs con trades≥10: {len(results)}", flush=True)
    print(f"Pasan eval 30d rolling: {len(survivors_30d)}", flush=True)
    print(f"Pasan eval 5 años: {len(full_pass)}", flush=True)

    for x in (survivors_30d[:8] or results[:8]):
        print(
            f"  [{x['strategy']}] 30d={x['w30_rate']}% ({x['w30_pass']}/{x['w30_total']}) "
            f"med={x['w30_med']}d | full={'PASS' if x['full_pass'] else 'fail'} "
            f"${x['full_pnl']} DD{x['full_dd']}% trades={x['full_trades']}",
            flush=True,
        )

    OUT.write_text(
        json.dumps({
            "internet_consensus": [
                "ICT Judas Swing London open",
                "Liquidity sweep SMC",
                "London Asian breakout (1 trade/day)",
                "Price action R:R 1:2+",
                "0.5-1% risk (nosotros 2.1% max WS)",
            ],
            "survivors_30d": len(survivors_30d),
            "full_pass_count": len(full_pass),
            "top_30d": survivors_30d[:15],
            "top_full": sorted(full_pass, key=lambda x: x["full_pnl"], reverse=True)[:15],
            "top_overall": results[:25],
        }, indent=2),
        encoding="utf-8",
    )
    print(f"\n→ {OUT}", flush=True)


if __name__ == "__main__":
    main()
