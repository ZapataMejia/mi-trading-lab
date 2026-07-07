#!/usr/bin/env python3
"""Hunt v2 — buscar mejor que SAFE en histórico 2017-2026, objetivo pass 30d ≥50%."""
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

OUT = ROOT / "data/forex_cache/hunt_safe_v2.json"
SAFE = LiquiditySweepConfig(
    lookback_bars=36, sess_start=700, sess_end=1400, risk_pct=1.5, tp_ratio=1.5,
    sl_buffer_pips=3.0, max_trades_per_day=1, broker_utc_offset_hours=7, mm_risk_pct=1.5,
    equity_sample_bars=12,
)
_BARS: pd.DataFrame | None = None
PERIOD = ("2017-01-03", "2024-10-30")
W30 = ("2017-01-03", "2022-03-31")
MAX_DAILY = 4.5


def _init() -> None:
    global _BARS
    df = _normalize_ohlc(pd.read_csv(ROOT / "data/forex_cache/EURUSD_M5.csv"))
    _BARS = df[(df["timestamp"] >= PERIOD[0]) & (df["timestamp"] <= PERIOD[1] + " 23:59:59")].reset_index(drop=True)


def _cfg(d: dict) -> LiquiditySweepConfig:
    base = {k: v for k, v in d.items() if k not in ("mm_risk_pct", "equity_sample_bars", "equal_tolerance_pips")}
    return LiquiditySweepConfig(**base, mm_risk_pct=d["risk_pct"], equity_sample_bars=12, equal_tolerance_pips=3.0)


def _ws(c: LiquiditySweepConfig) -> FondeoConfig:
    return FondeoConfig(risk_pct=c.risk_pct, max_trades_per_day=c.max_trades_per_day,
                        initial_balance=5000, broker_utc_offset_hours=c.broker_utc_offset_hours, equity_sample_bars=12)


def _screen(p: dict) -> dict | None:
    assert _BARS is not None
    cfg = _cfg(p)
    r = run_liquidity_sweep(_BARS, cfg)
    if r.metrics["n_trades"] < 50:
        return None
    ev = evaluate_ws_classic(r, _ws(cfg))
    if not ev["checks"]["pass_all"] or ev["max_daily_loss_pct"] > MAX_DAILY:
        return None
    return {**p, "full_dd": ev["static_dd_pct"], "full_daily_dd": ev["max_daily_loss_pct"],
            "full_trades": r.metrics["n_trades"], "days_to_meta": ev["days_to_meta"]}


def _w30(row: dict) -> dict:
    assert _BARS is not None
    cfg = _cfg({k: row[k] for k in (
        "lookback_bars", "sess_start", "sess_end", "tp_ratio", "risk_pct",
        "max_trades_per_day", "sl_buffer_pips", "broker_utc_offset_hours")})
    w = _ws(cfg)
    starts = pd.date_range(W30[0], W30[1], freq="2MS", tz="UTC")
    passed = total = 0
    days = []
    for s in starts:
        chunk = _BARS[(_BARS["timestamp"] >= s) & (_BARS["timestamp"] < s + pd.Timedelta(days=30))]
        if len(chunk) < 400:
            continue
        total += 1
        ev = evaluate_ws_classic(run_liquidity_sweep(chunk, cfg), w)
        if ev["checks"]["pass_all"]:
            passed += 1
            if ev["days_to_meta"] is not None:
                days.append(ev["days_to_meta"])
    med = sorted(days)[len(days) // 2] if days else None
    rate = round(100 * passed / total, 1) if total else 0
    return {**row, "w30_pass": passed, "w30_total": total, "w30_rate": rate, "w30_med": med}


def grid() -> list[dict]:
    out = []
    for lb, (ss, se), tp, risk, mtd, buf in itertools.product(
        [24, 36, 48, 60], [(700, 1100), (700, 1200), (700, 1400), (800, 1200)],
        [1.5, 2.0, 2.5], [1.0, 1.2, 1.5, 1.8], [1, 2], [2.0, 3.0, 4.0],
    ):
        out.append({"lookback_bars": lb, "sess_start": ss, "sess_end": se, "tp_ratio": tp,
                    "risk_pct": risk, "max_trades_per_day": mtd, "sl_buffer_pips": buf,
                    "broker_utc_offset_hours": 7})
    return out


def main() -> None:
    params = grid()
    workers = min(8, os.cpu_count() or 4)
    print(f"HUNT v2 · {len(params)} combos · periodo {PERIOD[0]}→{PERIOD[1]}\n", flush=True)
    _init()
    t0 = time.time()
    survivors = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as ex:
        futs = {ex.submit(_screen, p): p for p in params}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            if r:
                survivors.append(r)
            if i % 100 == 0:
                print(f"  {i}/{len(params)} survivors={len(survivors)}", flush=True)
    print(f"Fase1: {len(survivors)} ({time.time()-t0:.0f}s)", flush=True)
    survivors.sort(key=lambda x: (-x["full_daily_dd"], x["full_dd"]), reverse=True)
    top = survivors[:100]
    results = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as ex:
        for fut in as_completed([ex.submit(_w30, r) for r in top]):
            row = fut.result()
            results.append(row)
            if row["w30_rate"] >= 45:
                print(f"  HIT {row['w30_rate']}% lb={row['lookback_bars']} r={row['risk_pct']}", flush=True)
    _init()
    safe_row = _screen(SAFE.to_dict()) or SAFE.to_dict()
    baseline = _w30(safe_row)
    results.sort(key=lambda x: (x["w30_rate"], x["w30_pass"], -x["full_daily_dd"]), reverse=True)
    best = results[0] if results else None
    payload = {"baseline_safe": baseline, "best": best, "improved": best and best["w30_rate"] > baseline["w30_rate"],
               "top10": results[:10], "combos": len(params), "survivors": len(survivors)}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if best:
        print(f"\nSAFE: {baseline['w30_rate']}% | MEJOR: {best['w30_rate']}% lb={best['lookback_bars']}", flush=True)
    print(f"→ {OUT}", flush=True)


if __name__ == "__main__":
    main()
