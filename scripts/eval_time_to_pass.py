#!/usr/bin/env python3
"""Días hasta pasar eval desde arranque aleatorio (sin límite ventana)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig, run_fondeo_backtest
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/eval_time_to_pass.json"

CONFIGS = [
    ("curso 9/20 8-10", dict(fast_period=9, slow_period=20, tp_ratio=1.0, sess_start=800, sess_end=1000, broker_utc_offset_hours=7)),
    ("lab 9/18 7-11", dict(fast_period=9, slow_period=18, tp_ratio=1.0, sess_start=700, sess_end=1100, broker_utc_offset_hours=7)),
    ("3/8 TP2.5 7-14", dict(fast_period=3, slow_period=8, tp_ratio=2.5, sess_start=700, sess_end=1400, broker_utc_offset_hours=7)),
]


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(CSV))
    df = df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")]
    starts = pd.date_range("2017-01-03", "2021-06-01", freq="2MS", tz="UTC")
    max_days = 180

    report: dict = {}
    for name, p in CONFIGS:
        cfg = FondeoConfig(**p, risk_pct=2.1, max_trades_per_day=2, mm_risk_pct=2.1, equity_sample_bars=12)
        passed = breached = timeout = 0
        days_list: list[int] = []

        for s in starts:
            end = s + pd.Timedelta(days=max_days)
            chunk = df[(df["timestamp"] >= s) & (df["timestamp"] < end)]
            if len(chunk) < 500:
                continue
            r = run_fondeo_backtest(chunk, cfg)
            ev = evaluate_ws_classic(r, cfg)
            if ev["checks"]["pass_all"]:
                passed += 1
                if ev["days_to_meta"] is not None:
                    days_list.append(ev["days_to_meta"])
            elif ev["static_dd_pct"] <= -8.0:
                breached += 1
            else:
                timeout += 1

        total = passed + breached + timeout
        med = sorted(days_list)[len(days_list) // 2] if days_list else None
        report[name] = {
            "params": p,
            "attempts": total,
            "passed": passed,
            "breached": breached,
            "timeout_180d": timeout,
            "pass_rate_pct": round(100 * passed / total, 1) if total else 0,
            "median_days_to_pass": med,
        }
        print(
            f"{name}: pass {passed}/{total} ({report[name]['pass_rate_pct']}%) "
            f"breach {breached} timeout180 {timeout} med_days={med}",
            flush=True,
        )

    best = max(report.items(), key=lambda x: (x[1]["pass_rate_pct"], x[1]["passed"]))
    report["recommendation"] = f"Mejor: {best[0]} — {best[1]['pass_rate_pct']}% pasa en ≤180d, mediana {best[1]['median_days_to_pass']}d"
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{report['recommendation']}\n→ {OUT}", flush=True)


if __name__ == "__main__":
    main()
