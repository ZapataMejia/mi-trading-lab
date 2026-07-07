#!/usr/bin/env python3
"""Grid Liquidity Sweep MP — optimizar pass rate 30d."""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig
from webapp.backend.engine.liquidity_sweep_engine import LiquiditySweepConfig, run_liquidity_sweep
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hunt_liq_sweep_grid.json"

_BARS: pd.DataFrame | None = None
BASELINE = {
    "lookback_bars": 24, "sess_start": 700, "sess_end": 1400,
    "risk_pct": 2.1, "tp_ratio": 1.5, "max_trades_per_day": 2,
    "sl_buffer_pips": 2.0, "broker_utc_offset_hours": 7,
}


def _init(csv_path: str) -> None:
    global _BARS
    df = _normalize_ohlc(pd.read_csv(csv_path))
    _BARS = df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def _cfg(d: dict) -> LiquiditySweepConfig:
    return LiquiditySweepConfig(
        **d, mm_risk_pct=d["risk_pct"], equity_sample_bars=12,
        equal_tolerance_pips=3.0, initial_balance=5000.0,
    )


def _ws(c: LiquiditySweepConfig) -> FondeoConfig:
    return FondeoConfig(
        risk_pct=c.risk_pct, max_trades_per_day=c.max_trades_per_day,
        initial_balance=c.initial_balance, broker_utc_offset_hours=c.broker_utc_offset_hours,
        equity_sample_bars=c.equity_sample_bars,
    )


def _screen_one(params: dict) -> dict | None:
    assert _BARS is not None
    cfg = _cfg(params)
    r = run_liquidity_sweep(_BARS, cfg)
    if r.metrics["n_trades"] < 30:
        return None
    ev = evaluate_ws_classic(r, _ws(cfg))
    if not ev["checks"]["pass_all"]:
        return None
    return {
        **params,
        "full_pass": True,
        "full_pnl": round(r.total_pnl, 2),
        "full_dd": round(ev["static_dd_pct"], 2),
        "full_daily_dd": round(ev["max_daily_loss_pct"], 2),
        "full_trades": r.metrics["n_trades"],
        "full_pf": round(min(r.metrics.get("profit_factor") or 0, 999), 2),
        "days_to_meta": ev["days_to_meta"],
    }


def _eval30_one(row: dict) -> dict:
    assert _BARS is not None
    params = {k: row[k] for k in (
        "lookback_bars", "sess_start", "sess_end", "tp_ratio", "risk_pct",
        "max_trades_per_day", "sl_buffer_pips", "broker_utc_offset_hours",
    )}
    cfg = _cfg(params)
    w = _ws(cfg)
    starts = pd.date_range("2017-01-03", "2021-09-01", freq="MS", tz="UTC")
    passed = total = 0
    days_list: list[int] = []
    for s in starts:
        chunk = _BARS[(_BARS["timestamp"] >= s) & (_BARS["timestamp"] < s + pd.Timedelta(days=30))]
        if len(chunk) < 400:
            continue
        total += 1
        r = run_liquidity_sweep(chunk, cfg)
        ev = evaluate_ws_classic(r, w)
        if ev["checks"]["pass_all"]:
            passed += 1
            if ev["days_to_meta"] is not None:
                days_list.append(ev["days_to_meta"])
    med = sorted(days_list)[len(days_list) // 2] if days_list else None
    rate = round(100 * passed / total, 1) if total else 0.0
    return {**row, "w30_pass": passed, "w30_total": total, "w30_rate": rate, "w30_med": med}


def grid_params() -> list[dict]:
    lookbacks = [18, 24, 36, 48]
    sessions = [(700, 1100), (700, 1200), (700, 1400), (800, 1100)]
    tps = [1.5, 2.0, 2.5, 3.0]
    risks = [1.5, 2.0, 2.1]
    max_td = [1, 2]
    buffers = [2.0, 3.0]
    out = []
    for lb, (ss, se), tp, risk, mtd, buf in itertools.product(
        lookbacks, sessions, tps, risks, max_td, buffers
    ):
        out.append({
            "lookback_bars": lb, "sess_start": ss, "sess_end": se,
            "tp_ratio": tp, "risk_pct": risk, "max_trades_per_day": mtd,
            "sl_buffer_pips": buf, "broker_utc_offset_hours": 7,
        })
    return out


def score(row: dict) -> float:
    return row["w30_rate"] * 100 + row["w30_pass"] * 2 + row["full_dd"] + min(row.get("full_pnl", 0), 5000) * 0.01


def main() -> None:
    params_list = grid_params()
    workers = min(8, os.cpu_count() or 4)
    print(f"FASE 1 MP — {len(params_list)} combos · {workers} workers\n", flush=True)
    t0 = time.time()
    survivors: list[dict] = []

    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(str(CSV),)) as ex:
        futs = {ex.submit(_screen_one, p): p for p in params_list}
        done = 0
        for fut in as_completed(futs):
            done += 1
            if done % 80 == 0:
                print(f"  {done}/{len(params_list)} survivors={len(survivors)}", flush=True)
            try:
                res = fut.result()
                if res:
                    survivors.append(res)
            except Exception as e:
                print(f"  ERR: {e}", flush=True)

    print(f"\nFase 1: {len(survivors)} pass full ({time.time()-t0:.0f}s)", flush=True)
    if not survivors:
        OUT.write_text(json.dumps({"error": "0 survivors"}, indent=2))
        return

    survivors.sort(key=lambda x: (x["full_dd"], x["full_pf"]), reverse=True)
    top = survivors[:min(100, len(survivors))]
    print(f"\nFASE 2 MP — 30d en top {len(top)}\n", flush=True)

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(str(CSV),)) as ex:
        futs = [ex.submit(_eval30_one, r) for r in top]
        for i, fut in enumerate(as_completed(futs), 1):
            row = fut.result()
            results.append(row)
            if row["w30_rate"] >= 42:
                print(f"  HIT 30d={row['w30_rate']}% lb={row['lookback_bars']} {row['sess_start']}-{row['sess_end']} TP{row['tp_ratio']}", flush=True)
            if i % 25 == 0:
                print(f"  {i}/{len(top)}", flush=True)

    baseline_row = _screen_one(BASELINE) or {}
    _init(str(CSV))
    baseline = {**baseline_row, **_eval30_one({**BASELINE, **baseline_row})}

    results.sort(key=score, reverse=True)
    best = results[0]
    improved = best["w30_rate"] > baseline["w30_rate"]

    print(f"\nBASELINE: 30d={baseline['w30_rate']}% DD={baseline.get('full_dd')}%", flush=True)
    print(f"MEJOR: lb={best['lookback_bars']} {best['sess_start']}-{best['sess_end']} TP{best['tp_ratio']} "
          f"r{best['risk_pct']}% max{best['max_trades_per_day']}/d", flush=True)
    print(f"  30d={best['w30_rate']}% ({best['w30_pass']}/{best['w30_total']}) med={best['w30_med']}d "
          f"DD={best['full_dd']}% daily={best['full_daily_dd']}%", flush=True)
    print(f"  Mejora: {'SÍ' if improved else 'NO'} ({best['w30_rate']-baseline['w30_rate']:+.1f}pp)", flush=True)

    OUT.write_text(json.dumps({
        "combos": len(params_list),
        "full_pass": len(survivors),
        "baseline": baseline,
        "best": best,
        "improved": improved,
        "top15": results[:15],
    }, indent=2), encoding="utf-8")
    print(f"→ {OUT}", flush=True)


if __name__ == "__main__":
    main()
