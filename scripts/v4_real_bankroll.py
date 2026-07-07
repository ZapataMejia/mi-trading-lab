"""Simulación de bankroll para V4 real con Kelly y diferentes thresholds.

Lee los CSVs del backtest real (V4 30 días, 30pp) y simula el bankroll con:
  - Kelly fractional × 0.50
  - Max 20% bankroll por trade
  - Cap $500 por trade
  - Floor $30 (corte si bankroll cae por debajo)

Reporta:
  - 30 días con threshold 30pp (datos reales)
  - 30 días con threshold 35pp (sub-conjunto)
  - 30 días con threshold 40pp (sub-conjunto)
  - 1 semana (últimos 7 días)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

INITIAL_BANKROLL = 100.0
KELLY_FRACTION = 0.50
MAX_PCT_PER_TRADE = 0.20
MAX_POSITION_USD = 500.0
MIN_POSITION_USD = 1.0
BANKROLL_FLOOR = 30.0

HALF_SPREAD = 0.015
FLAT_FEE = 0.005
FEE_RATE = 0.02


def simulate(sig: pd.DataFrame) -> dict:
    bankroll = INITIAL_BANKROLL
    wins = 0
    n = 0
    pnl_total = 0.0
    peak = bankroll
    max_dd = 0.0
    sig = sig.sort_values("window_start").reset_index(drop=True)
    for _, t in sig.iterrows():
        if bankroll < BANKROLL_FLOOR:
            continue
        edge = t["signal_edge_up"]
        direction = "UP" if edge > 0 else "DOWN"
        p_poly = t["p_poly_at_signal"]
        p_fair = t["p_fair_at_signal"]
        if direction == "UP":
            naive_fill = p_poly
            p_model = p_fair
        else:
            naive_fill = 1.0 - p_poly
            p_model = 1.0 - p_fair
        fill = min(1.0, naive_fill + HALF_SPREAD)
        if fill >= 0.99:
            continue
        fill_total = fill * (1.0 + FEE_RATE)
        edge_after = p_model - fill_total
        if edge_after <= 0:
            continue
        f_kelly = edge_after / max(1e-6, 1.0 - fill_total)
        f = max(0.0, min(f_kelly * KELLY_FRACTION, MAX_PCT_PER_TRADE))
        position_usd = min(bankroll * f, MAX_POSITION_USD, bankroll * 0.95)
        if position_usd < MIN_POSITION_USD:
            continue
        contracts = position_usd / fill
        prop_fee = contracts * fill * FEE_RATE
        cost_paid = contracts * fill + prop_fee + FLAT_FEE
        if cost_paid > bankroll:
            continue
        outcome_correct = (t["outcome"] == direction)
        payoff = contracts if outcome_correct else 0.0
        bankroll = bankroll - cost_paid + payoff
        pnl = payoff - cost_paid
        pnl_total += pnl
        if outcome_correct: wins += 1
        n += 1
        peak = max(peak, bankroll)
        dd = (bankroll - peak) / peak if peak > 0 else 0
        max_dd = min(max_dd, dd)

    return {
        "trades": n,
        "wr": (100 * wins / n) if n else float("nan"),
        "pnl": pnl_total,
        "final": bankroll,
        "max_dd": 100 * max_dd,
        "avg_per_trade": (pnl_total / n) if n else 0,
    }


def fmt(r: dict, label: str) -> str:
    return (
        f"  {label:<35}  trades={r['trades']:>4}  "
        f"WR={r['wr']:>5.1f}%  PnL=${r['pnl']:>+8,.2f}  "
        f"final=${r['final']:>9,.2f}  DD={r['max_dd']:>+5.1f}%  "
        f"avg=${r['avg_per_trade']:>+6.4f}"
    )


def main():
    df = pd.read_csv("data/poly_backtest_year/v4_real/v4_real_30d_combined.csv")
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    sig = df[df["signal"].isin(["UP", "DOWN"])].copy()
    sig["edge_abs"] = sig["signal_edge_up"].abs()
    print(f"Total V4 signals (30 dias, 4 assets): {len(sig)}")
    print(f"Periodo: {sig['window_start'].min().date()} -> {sig['window_start'].max().date()}")
    print()

    print("=== Escenarios threshold creciente ===")
    for th in (0.30, 0.35, 0.40, 0.50):
        s = sig[sig["edge_abs"] >= th]
        r = simulate(s)
        print(fmt(r, f"V4 threshold {int(th*100)}pp"))
    print()

    print("=== Timeframes (threshold 30pp) ===")
    end_ts = sig["window_start"].max()
    for label, days in (("1 semana", 7), ("1 mes", 30)):
        start_ts = end_ts - pd.Timedelta(days=days)
        s = sig[sig["window_start"] >= start_ts]
        r = simulate(s)
        print(fmt(r, f"V4 30pp · {label}"))
    print()

    print("=== Timeframes (threshold 35pp) — más exigente ===")
    sig35 = sig[sig["edge_abs"] >= 0.35]
    for label, days in (("1 semana", 7), ("1 mes", 30)):
        start_ts = end_ts - pd.Timedelta(days=days)
        s = sig35[sig35["window_start"] >= start_ts]
        r = simulate(s)
        print(fmt(r, f"V4 35pp · {label}"))
    print()

    print("=== Timeframes (threshold 40pp) — tight ===")
    sig40 = sig[sig["edge_abs"] >= 0.40]
    for label, days in (("1 semana", 7), ("1 mes", 30)):
        start_ts = end_ts - pd.Timedelta(days=days)
        s = sig40[sig40["window_start"] >= start_ts]
        r = simulate(s)
        print(fmt(r, f"V4 40pp · {label}"))


if __name__ == "__main__":
    main()
