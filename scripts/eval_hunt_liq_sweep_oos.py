#!/usr/bin/env python3
"""Grid Liquidity Sweep OOS — optimizar pass 30d en 2022-2024 con margen DD diario."""
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
OUT = ROOT / "data/forex_cache/hunt_liq_sweep_oos.json"
BEST = ROOT / "data/forex_cache/liq_sweep_best.json"

PERIOD_START = "2022-01-01"
PERIOD_END = "2024-10-30"
W30_START = "2022-01-01"
W30_END = "2024-08-01"
MAX_DAILY_DD = 4.5  # margen bajo límite WS 5%

_BARS: pd.DataFrame | None = None

CURRENT_BEST = {
    "lookback_bars": 36,
    "sess_start": 700,
    "sess_end": 1200,
    "risk_pct": 2.0,
    "tp_ratio": 1.5,
    "max_trades_per_day": 2,
    "sl_buffer_pips": 2.0,
    "broker_utc_offset_hours": 7,
}


def _init(csv_path: str) -> None:
    global _BARS
    df = _normalize_ohlc(pd.read_csv(csv_path))
    _BARS = df[
        (df["timestamp"] >= PERIOD_START) & (df["timestamp"] <= PERIOD_END)
    ].reset_index(drop=True)


def _cfg(d: dict) -> LiquiditySweepConfig:
    return LiquiditySweepConfig(
        **d,
        mm_risk_pct=d["risk_pct"],
        equity_sample_bars=12,
        equal_tolerance_pips=3.0,
        initial_balance=5000.0,
    )


def _ws(c: LiquiditySweepConfig) -> FondeoConfig:
    return FondeoConfig(
        risk_pct=c.risk_pct,
        max_trades_per_day=c.max_trades_per_day,
        initial_balance=c.initial_balance,
        broker_utc_offset_hours=c.broker_utc_offset_hours,
        equity_sample_bars=c.equity_sample_bars,
    )


def _screen_one(params: dict) -> dict | None:
    assert _BARS is not None
    cfg = _cfg(params)
    r = run_liquidity_sweep(_BARS, cfg)
    if r.metrics["n_trades"] < 20:
        return None
    ev = evaluate_ws_classic(r, _ws(cfg))
    if not ev["checks"]["pass_all"]:
        return None
    if ev["max_daily_loss_pct"] > MAX_DAILY_DD:
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
    starts = pd.date_range(W30_START, W30_END, freq="2MS", tz="UTC")
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
    risks = [1.0, 1.2, 1.5, 1.8, 2.0]
    max_td = [1, 2]
    buffers = [2.0, 3.0]
    out = []
    for lb, (ss, se), tp, risk, mtd, buf in itertools.product(
        lookbacks, sessions, tps, risks, max_td, buffers
    ):
        out.append({
            "lookback_bars": lb,
            "sess_start": ss,
            "sess_end": se,
            "tp_ratio": tp,
            "risk_pct": risk,
            "max_trades_per_day": mtd,
            "sl_buffer_pips": buf,
            "broker_utc_offset_hours": 7,
        })
    return out


def score(row: dict) -> float:
    daily = row.get("full_daily_dd", 99)
    daily_bonus = max(0, MAX_DAILY_DD - daily) * 20
    return (
        row["w30_rate"] * 100
        + row["w30_pass"] * 3
        + daily_bonus
        + row.get("full_dd", 0)
        + min(row.get("full_pnl", 0), 3000) * 0.005
    )


def _eval_baseline() -> dict:
    _init(str(CSV))
    base = _screen_one(CURRENT_BEST)
    if not base:
        base = {**CURRENT_BEST, "full_pass": False, "full_dd": None, "full_daily_dd": None}
    return {**base, **_eval30_one({**CURRENT_BEST, **base})}


def main() -> None:
    params_list = grid_params()
    workers = min(8, os.cpu_count() or 4)
    print(
        f"OOS HUNT — {len(params_list)} combos · {workers} workers\n"
        f"Periodo full: {PERIOD_START} → {PERIOD_END}\n"
        f"Ventanas 30d: {W30_START} → {W30_END} · daily DD ≤ {MAX_DAILY_DD}%\n",
        flush=True,
    )
    t0 = time.time()
    survivors: list[dict] = []

    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(str(CSV),)) as ex:
        futs = {ex.submit(_screen_one, p): p for p in params_list}
        done = 0
        for fut in as_completed(futs):
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(params_list)} survivors={len(survivors)}", flush=True)
            try:
                res = fut.result()
                if res:
                    survivors.append(res)
            except Exception as e:
                print(f"  ERR: {e}", flush=True)

    print(f"\nFase 1: {len(survivors)} pass OOS full + daily≤{MAX_DAILY_DD}% ({time.time()-t0:.0f}s)", flush=True)
    if not survivors:
        OUT.write_text(json.dumps({"error": "0 survivors", "period": [PERIOD_START, PERIOD_END]}, indent=2))
        return

    survivors.sort(key=lambda x: (-x["full_daily_dd"], x["full_dd"]), reverse=True)
    top = survivors[:min(120, len(survivors))]
    print(f"\nFASE 2 MP — 30d en top {len(top)}\n", flush=True)

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(str(CSV),)) as ex:
        futs = [ex.submit(_eval30_one, r) for r in top]
        for i, fut in enumerate(as_completed(futs), 1):
            row = fut.result()
            results.append(row)
            if row["w30_rate"] >= 50:
                print(
                    f"  HIT 30d={row['w30_rate']}% daily={row['full_daily_dd']}% "
                    f"lb={row['lookback_bars']} {row['sess_start']}-{row['sess_end']} "
                    f"TP{row['tp_ratio']} r{row['risk_pct']}% max{row['max_trades_per_day']}/d",
                    flush=True,
                )
            if i % 30 == 0:
                print(f"  {i}/{len(top)}", flush=True)

    baseline = _eval_baseline()
    results.sort(key=score, reverse=True)
    best = results[0]
    improved = best["w30_rate"] > baseline["w30_rate"]

    print(f"\nBASELINE (config actual): 30d={baseline['w30_rate']}% daily={baseline.get('full_daily_dd')}%", flush=True)
    print(
        f"MEJOR: lb={best['lookback_bars']} {best['sess_start']}-{best['sess_end']} "
        f"TP{best['tp_ratio']} r{best['risk_pct']}% max{best['max_trades_per_day']}/d buf{best['sl_buffer_pips']}",
        flush=True,
    )
    print(
        f"  30d={best['w30_rate']}% ({best['w30_pass']}/{best['w30_total']}) med={best['w30_med']}d "
        f"DD={best['full_dd']}% daily={best['full_daily_dd']}%",
        flush=True,
    )
    print(f"  Mejora vs baseline: {best['w30_rate'] - baseline['w30_rate']:+.1f}pp", flush=True)

    payload = {
        "objective": f"Pass rate 30d ≥55% en OOS {PERIOD_START}→{PERIOD_END}, daily DD ≤{MAX_DAILY_DD}%",
        "period_full": [PERIOD_START, PERIOD_END],
        "period_windows_30d": [W30_START, W30_END],
        "max_daily_dd_margin": MAX_DAILY_DD,
        "combos": len(params_list),
        "full_pass": len(survivors),
        "baseline": baseline,
        "best": best,
        "improved": improved,
        "target_55pct_met": best["w30_rate"] >= 55,
        "top15": results[:15],
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"→ {OUT}", flush=True)

    if improved or best["w30_rate"] >= baseline["w30_rate"]:
        BEST.write_text(
            json.dumps(
                {
                    "source": "eval_hunt_liq_sweep_oos.py — OOS 2022-2024",
                    "baseline": {
                        "lookback_bars": CURRENT_BEST["lookback_bars"],
                        "sess_start": CURRENT_BEST["sess_start"],
                        "sess_end": CURRENT_BEST["sess_end"],
                        "risk_pct": CURRENT_BEST["risk_pct"],
                        "tp_ratio": CURRENT_BEST["tp_ratio"],
                        "w30_rate": baseline["w30_rate"],
                        "full_dd": baseline.get("full_dd"),
                        "full_daily_dd": baseline.get("full_daily_dd"),
                    },
                    "best": {
                        k: best[k]
                        for k in (
                            "lookback_bars", "sess_start", "sess_end", "risk_pct", "tp_ratio",
                            "sl_buffer_pips", "max_trades_per_day", "broker_utc_offset_hours",
                            "w30_rate", "w30_pass", "w30_total", "w30_med",
                            "full_dd", "full_daily_dd", "full_trades", "full_pass",
                        )
                    },
                    "improved_vs_baseline_pp": round(best["w30_rate"] - baseline["w30_rate"], 1),
                    "target_55pct_met": best["w30_rate"] >= 55,
                    "note": f"OOS hunt · daily DD ≤{MAX_DAILY_DD}% · ventanas 30d cada 2 meses",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"→ {BEST}", flush=True)


if __name__ == "__main__":
    main()
