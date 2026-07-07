#!/usr/bin/env python3
"""Tiempo para pasar eval WS — Liquidity Sweep SAFE · ventanas rolling."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig
from webapp.backend.engine.liquidity_sweep_engine import LiquiditySweepConfig, run_liquidity_sweep
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

OUT = ROOT / "data/forex_cache/eval_timing_safe.json"
CFG = LiquiditySweepConfig(
    lookback_bars=36,
    sess_start=700,
    sess_end=1400,
    risk_pct=1.5,
    tp_ratio=1.5,
    sl_buffer_pips=3.0,
    max_trades_per_day=1,
    broker_utc_offset_hours=7,
    mm_risk_pct=1.5,
    equity_sample_bars=12,
)
WS = FondeoConfig(
    risk_pct=1.5,
    max_trades_per_day=1,
    initial_balance=5000,
    broker_utc_offset_hours=7,
    equity_sample_bars=12,
)


def windows(bars: pd.DataFrame, days: int, start: str, end: str, step: str = "MS") -> list[dict]:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    starts = pd.date_range(start, end, freq=step, tz="UTC")
    rows = []
    for s in starts:
        e = s + pd.Timedelta(days=days)
        chunk = df[(df["timestamp"] >= s) & (df["timestamp"] < e)]
        if len(chunk) < 400:
            continue
        r = run_liquidity_sweep(chunk, CFG)
        ev = evaluate_ws_classic(r, WS)
        rows.append({
            "start": s.strftime("%Y-%m-%d"),
            "pass": ev["checks"]["pass_all"],
            "days_to_meta": ev["days_to_meta"],
            "static_dd": ev["static_dd_pct"],
            "daily_dd": ev["max_daily_loss_pct"],
            "pnl": round(r.total_pnl, 2),
        })
    return rows


def summarize(rows: list[dict], label: str) -> dict:
    total = len(rows)
    passed = [x for x in rows if x["pass"]]
    days = [x["days_to_meta"] for x in passed if x["days_to_meta"] is not None]
    days.sort()
    rate = round(100 * len(passed) / total, 1) if total else 0
    med = days[len(days) // 2] if days else None
    p75 = days[int(len(days) * 0.75)] if days else None
    within_30 = sum(1 for d in days if d <= 30)
    return {
        "label": label,
        "attempts": total,
        "passed": len(passed),
        "pass_rate_pct": rate,
        "median_days_to_meta": med,
        "p75_days_to_meta": p75,
        "min_days": min(days) if days else None,
        "max_days": max(days) if days else None,
        "pct_pass_reach_meta_within_window": round(100 * within_30 / len(days), 1) if days else None,
        "expected_attempts_to_pass_once": round(total / len(passed), 2) if passed else None,
    }


def main() -> None:
    print("Cargando EURUSD M5...", flush=True)
    df = _normalize_ohlc(pd.read_csv(ROOT / "data/forex_cache/EURUSD_M5.csv"))
    d0, d1 = df["timestamp"].iloc[0], df["timestamp"].iloc[-1]
    print(f"Datos: {d0} -> {d1} ({len(df):,} barras)\n", flush=True)

    periods = [
        ("2017-2022 lab", "2017-01-03", "2022-03-31"),
        ("2022-2024 OOS", "2022-01-01", "2024-10-30"),
        ("2017-2024 full", "2017-01-03", "2024-10-30"),
    ]

    report: dict = {
        "config": CFG.to_dict(),
        "data_range": [str(d0)[:10], str(d1)[:10]],
        "periods": {},
    }

    for label, ps, pe in periods:
        chunk = df[(df["timestamp"] >= ps) & (df["timestamp"] <= pe + " 23:59:59")]
        print(f"=== {label} ({len(chunk):,} barras) ===", flush=True)
        period_report = {}
        for wdays in (30, 60, 90):
            rows = windows(chunk, wdays, ps, pe, step="2MS" if wdays == 30 else "QS")
            s = summarize(rows, f"{wdays}d")
            period_report[f"window_{wdays}d"] = s
            print(
                f"  {wdays}d: pass {s['pass_rate_pct']}% ({s['passed']}/{s['attempts']}) "
                f"| med {s['median_days_to_meta']}d | esperado {s['expected_attempts_to_pass_once']} intentos",
                flush=True,
            )
        # Full period single eval
        r = run_liquidity_sweep(chunk, CFG)
        ev = evaluate_ws_classic(r, WS)
        period_report["full_period"] = {
            "pass": ev["checks"]["pass_all"],
            "days_to_meta": ev["days_to_meta"],
            "static_dd": ev["static_dd_pct"],
            "daily_dd": ev["max_daily_loss_pct"],
            "trades": r.metrics["n_trades"],
        }
        report["periods"][label] = period_report
        print(f"  full: pass={ev['checks']['pass_all']} meta_en={ev['days_to_meta']}d daily={ev['max_daily_loss_pct']}%\n", flush=True)

    # Proyección usuario (2 cuentas, 2-3 meses)
    oos30 = report["periods"]["2022-2024 OOS"]["window_30d"]
    p = oos30["pass_rate_pct"] / 100
    report["user_projection"] = {
        "pass_rate_30d_oos": oos30["pass_rate_pct"],
        "median_days_when_passes": oos30["median_days_to_meta"],
        "expected_monthly_attempts_to_pass": oos30["expected_attempts_to_pass_once"],
        "prob_1_account_passes_first_try_pct": round(p * 100, 1),
        "prob_2_accounts_at_least_one_passes_pct": round((1 - (1 - p) ** 2) * 100, 1),
        "realistic_timeline": (
            f"Cuando pasa: meta en ~{oos30['median_days_to_meta']} días (mediana). "
            f"~{oos30['pass_rate_pct']}% de ventanas 30d pasan → "
            f"con 2 cuentas ~{round((1-(1-p)**2)*100,1)}% de lograr al menos 1 pass en el primer intento. "
            f"Si falla, reintento mes 2-3."
        ),
    }

    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"→ {OUT}", flush=True)
    print("\n" + report["user_projection"]["realistic_timeline"], flush=True)


if __name__ == "__main__":
    main()
