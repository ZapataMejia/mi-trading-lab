#!/usr/bin/env python3
"""Hunt 30d RÁPIDO — score = pass rate ventana 30 días."""
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

# Import no-session-close runner
sys.path.insert(0, str(ROOT / "scripts"))
from eval_hunt_no_sess_close import run_no_sess_close  # noqa: E402

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hunt_30d_fast.json"


def load() -> pd.DataFrame:
    df = _normalize_ohlc(pd.read_csv(CSV))
    return df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)


def grid() -> list[dict]:
    emas = [(2, 5), (3, 6), (3, 8), (4, 9), (5, 11), (6, 14), (8, 18), (9, 18), (9, 20)]
    sessions = [(600, 1400), (700, 1100), (700, 1400), (800, 1000), (800, 1200), (800, 1400)]
    offsets = [0, 7]
    tps = [1.0, 1.5, 2.0, 2.5, 3.0]
    out = []
    for (f, s), (ss, se), off, tp in itertools.product(emas, sessions, offsets, tps):
        out.append({"fast_period": f, "slow_period": s, "risk_pct": 2.1, "tp_ratio": tp,
                    "sess_start": ss, "sess_end": se, "max_trades_per_day": 2, "broker_utc_offset_hours": off})
    return out


def eval_30d(bars, cfg: FondeoConfig, runner=run_fondeo_backtest) -> dict:
    w30 = simulate_eval_windows(bars, cfg, window_days=30, step="MS", end="2021-09-01")
    # Override runner by patching - simulate_eval_windows uses run_fondeo_backtest only
    return {"w30_rate": w30.pass_rate_pct, "w30_pass": w30.passed, "w30_attempts": w30.attempts, "w30_med": w30.median_days_to_meta}


def eval_30d_custom(bars, cfg: FondeoConfig, run_fn) -> dict:
    from webapp.backend.engine.ws_eval import evaluate_ws_classic
    starts = pd.date_range("2017-01-03", "2021-09-01", freq="MS", tz="UTC")
    passed = total = 0
    days_list = []
    for s in starts:
        e = s + pd.Timedelta(days=30)
        chunk = bars[(bars["timestamp"] >= s) & (bars["timestamp"] < e)]
        if len(chunk) < 400:
            continue
        total += 1
        r = run_fn(chunk, cfg)
        ev = evaluate_ws_classic(r, cfg)
        if ev["checks"]["pass_all"]:
            passed += 1
            if ev["days_to_meta"] is not None:
                days_list.append(ev["days_to_meta"])
    med = sorted(days_list)[len(days_list) // 2] if days_list else None
    rate = round(100 * passed / total, 1) if total else 0
    return {"w30_rate": rate, "w30_pass": passed, "w30_attempts": total, "w30_med": med}


def main() -> None:
    bars = load()
    g = grid()
    print(f"HUNT 30d FAST — {len(g)} combos × 2 modos\n", flush=True)

    results_sess: list[dict] = []
    results_hold: list[dict] = []

    for i, p in enumerate(g, 1):
        if i % 50 == 0:
            print(f"  {i}/{len(g)} sess={len(results_sess)} hold={len(results_hold)}", flush=True)
        cfg = FondeoConfig(**p, mm_risk_pct=2.1, equity_sample_bars=48)

        m1 = eval_30d_custom(bars, cfg, run_fondeo_backtest)
        if m1["w30_pass"] > 0:
            r = run_fondeo_backtest(bars, cfg)
            ev = evaluate_ws_classic(r, cfg)
            results_sess.append({**p, **m1, "mode": "session_close", "full_pass": ev["checks"]["pass_all"], "full_pnl": round(r.total_pnl, 2)})

        m2 = eval_30d_custom(bars, cfg, run_no_sess_close)
        if m2["w30_pass"] > 0:
            r = run_no_sess_close(bars, cfg)
            ev = evaluate_ws_classic(r, cfg)
            results_hold.append({**p, **m2, "mode": "hold_overnight", "full_pass": ev["checks"]["pass_all"], "full_pnl": round(r.total_pnl, 2)})

    results_sess.sort(key=lambda x: (x["w30_rate"], x["w30_pass"]), reverse=True)
    results_hold.sort(key=lambda x: (x["w30_rate"], x["w30_pass"]), reverse=True)

    print(f"\n=== SESSION CLOSE: {len(results_sess)} configs ===", flush=True)
    for x in results_sess[:8]:
        print(f"  EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} {x['sess_start']}-{x['sess_end']} off{x['broker_utc_offset_hours']} | {x['w30_rate']}% ({x['w30_pass']}/{x['w30_attempts']}) med={x['w30_med']}d", flush=True)

    print(f"\n=== HOLD OVERNIGHT (abre sesión, cierra SL/TP): {len(results_hold)} configs ===", flush=True)
    for x in results_hold[:8]:
        print(f"  EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} {x['sess_start']}-{x['sess_end']} | {x['w30_rate']}% med={x['w30_med']}d", flush=True)

    best = results_hold[:5] or results_sess[:5]
    OUT.write_text(json.dumps({"session_close": results_sess[:15], "hold_overnight": results_hold[:15], "best": best}, indent=2), encoding="utf-8")
    print(f"\n→ {OUT}", flush=True)


if __name__ == "__main__":
    main()
