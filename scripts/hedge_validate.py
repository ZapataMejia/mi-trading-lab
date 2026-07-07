#!/usr/bin/env python3
"""Validación hedge — pass rate ventanas 7/14/30 días (defaults curso)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig
from webapp.backend.engine.hedged_eval import simulate_hedged_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(CSV))
    df = df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")]
    cfg = FondeoConfig(
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
    print("Hedge validate — curso 9/20, 8-10, offset +7, guardián +8% equity\n")
    for days in (7, 14, 30):
        w = simulate_hedged_windows(df, cfg, window_days=days, step="2MS", commission_usd=5)
        med = f"{w.median_days}d" if w.median_days is not None else "—"
        print(f"  {days:2d}d: {w.pair_wins:2d}/{w.attempts} ({w.pass_rate_pct:5.1f}%)  med {med}  (A:{w.a_wins} B:{w.b_wins} fail:{w.both_fail})")
    print("\nCriterio orientativo: ≥30% en 14d → seguir a demo VPS.")
    print("Ver sqx/VALIDAR_HEDGE.md para fases 2–3.")


if __name__ == "__main__":
    main()
