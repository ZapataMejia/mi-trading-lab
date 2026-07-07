#!/usr/bin/env python3
"""Backtest hedge completo — guarda reporte para el lab."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig
from webapp.backend.engine.hedged_eval import run_hedged_backtest, simulate_hedged_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hedge_lab_report.json"

COURSE = FondeoConfig(
    fast_period=9,
    slow_period=20,
    risk_pct=2.1,
    tp_ratio=1.0,
    sess_start=800,
    sess_end=1000,
    max_trades_per_day=2,
    broker_utc_offset_hours=7,
    mm_risk_pct=2.1,
)


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(CSV))
    df = df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")].reset_index(drop=True)
    print(f"Hedge lab backtest — {len(df):,} barras EURUSD M5\n", flush=True)

    windows = {}
    for days in (7, 14, 30, 60):
        w = simulate_hedged_windows(df, COURSE, window_days=days, step="2MS", commission_usd=5)
        windows[f"{days}d"] = {
            "pair_wins": w.pair_wins,
            "attempts": w.attempts,
            "pass_rate_pct": w.pass_rate_pct,
            "median_days": w.median_days,
            "a_wins": w.a_wins,
            "b_wins": w.b_wins,
            "both_fail": w.both_fail,
        }
        print(
            f"  Ventanas {days:2d}d: {w.pair_wins}/{w.attempts} ({w.pass_rate_pct}%)  "
            f"med={w.median_days}d  A:{w.a_wins} B:{w.b_wins} fail:{w.both_fail}",
            flush=True,
        )

    # Muestras mensuales 60d (últimos intentos representativos)
    samples: list[dict] = []
    starts = pd.date_range("2017-06-01", "2021-06-01", freq="4MS", tz="UTC")
    for s in starts:
        e = s + pd.Timedelta(days=60)
        chunk = df[(df["timestamp"] >= s) & (df["timestamp"] < e)]
        if len(chunk) < 500:
            continue
        r = run_hedged_backtest(chunk, COURSE, commission_usd=5)
        d = r.to_dict()
        samples.append({
            "start": str(s.date()),
            "days": 60,
            "outcome": r.outcome,
            "winner": r.winner,
            "days_to_win": r.days_to_win,
            "pnl_a": d["account_a"]["total_pnl"],
            "pnl_b": d["account_b"]["total_pnl"],
            "dd_a": d["account_a"]["ws_eval"]["static_dd_pct"],
            "dd_b": d["account_b"]["ws_eval"]["static_dd_pct"],
            "trades_a": d["account_a"]["n_trades"],
            "trades_b": d["account_b"]["n_trades"],
        })

    wins = [s for s in samples if s["outcome"] in ("a_wins", "b_wins")]
    print(f"\n  Muestras 60d (cada ~4 meses): {len(samples)}  wins={len(wins)}", flush=True)
    for s in samples[:5]:
        print(
            f"    {s['start']} → {s['outcome']}  A ${s['pnl_a']:+.0f}  B ${s['pnl_b']:+.0f}  ({s['trades_a']} trades)",
            flush=True,
        )

    # Full period (no es 1 eval — referencia)
    full = run_hedged_backtest(df, COURSE, commission_usd=5, stop_at_meta=False)
    fd = full.to_dict()
    print(
        f"\n  Periodo completo 2017-2022 (referencia, NO 1 eval):",
        flush=True,
    )
    print(f"    A ${fd['account_a']['total_pnl']:+.2f}  B ${fd['account_b']['total_pnl']:+.2f}", flush=True)

    report = {
        "config": COURSE.to_dict(),
        "bars": len(df),
        "windows": windows,
        "samples_60d": samples,
        "full_period": {
            "outcome": full.outcome,
            "account_a_pnl": fd["account_a"]["total_pnl"],
            "account_b_pnl": fd["account_b"]["total_pnl"],
            "account_a_dd": fd["account_a"]["ws_eval"]["static_dd_pct"],
            "account_b_dd": fd["account_b"]["ws_eval"]["static_dd_pct"],
        },
        "verdict": _verdict(windows),
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  Guardado: {OUT}", flush=True)
    print(f"\n  {report['verdict']}", flush=True)


def _verdict(windows: dict) -> str:
    r14 = windows.get("14d", {}).get("pass_rate_pct", 0)
    r30 = windows.get("30d", {}).get("pass_rate_pct", 0)
    if r14 >= 30:
        return "OK histórico — seguir a demo VPS (fase 2)."
    if r14 > 0:
        return "Pass rate bajo en histórico — demo VPS obligatoria antes de confiar."
    return "0% ventanas 7-30d en histórico — el par no llega a +8% con reglas curso en CSV; validar en demo en vivo."


if __name__ == "__main__":
    main()
