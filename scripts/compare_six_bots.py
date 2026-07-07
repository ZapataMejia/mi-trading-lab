"""Comparativa cabeza a cabeza de los 6 contendientes:
  V1  · Alerts                  (5pp, sin filtros)
  V2B · Selective               (10pp + skip horas/sab + vol $5k)
  V4A · Endgame 30pp (real)     (último mes, últimos 5 min, threshold 30pp)
  V4B · Endgame 40pp (real)     (último mes, últimos 5 min, threshold 40pp)
  V5A · Maker 20pp + skip       (config actual)
  V5B · Maker 15pp loose        (sin filtros volumen)

Para comparar todos en el MISMO período usamos los últimos 30 días del histórico
(2026-04-27 → 2026-05-26). V4 ya está en ese período por construcción (real
fetch). V1/V2B/V5 se filtran al mes.

Output:
  - Tabla impresa
  - Excel a data/poly_backtest_year/six_bots_comparison.xlsx
"""
from __future__ import annotations

from dataclasses import dataclass
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

END_TS = pd.Timestamp("2026-05-27", tz="UTC")
START_TS = pd.Timestamp("2026-04-27", tz="UTC")


@dataclass
class BotConfig:
    name: str
    threshold: float
    skip_hours_utc: tuple[int, ...] = ()
    skip_weekdays: tuple[str, ...] = ()
    min_volume_usd: float = 0.0


# ----- Configs -----
V1 = BotConfig(name="V1 · Alerts (5pp)", threshold=0.05)
V2B = BotConfig(
    name="V2B · Selective (10pp + skip)",
    threshold=0.10,
    skip_hours_utc=(21, 23),
    skip_weekdays=("Saturday",),
    min_volume_usd=5000.0,
)
V5A = BotConfig(
    name="V5A · Maker (20pp + skip + vol $8k)",
    threshold=0.20,
    skip_hours_utc=(0, 1, 2, 21, 22, 23),
    skip_weekdays=("Saturday", "Sunday"),
    min_volume_usd=8000.0,
)
V5B = BotConfig(
    name="V5B · Maker loose (15pp + skip)",
    threshold=0.15,
    skip_hours_utc=(0, 1, 2, 21, 22, 23),
    skip_weekdays=("Saturday", "Sunday"),
)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_historical() -> pd.DataFrame:
    """11-meses históricos con signal_minute (primer signal de V1)."""
    frames = []
    for a in ("btc", "eth", "sol", "xrp"):
        df = pd.read_csv(f"data/poly_backtest_year/{a}_hourly_1y_full.csv")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    df = df[df["signal"].notna() & df["outcome"].notna()]
    df = df[df["window_start"] >= START_TS]
    df = df[df["window_start"] < END_TS]
    df["edge_abs"] = df["signal_edge_up"].abs()
    df["hour"] = df["window_start"].dt.hour
    df["weekday"] = df["window_start"].dt.day_name()
    return df


def load_v4_real() -> pd.DataFrame:
    """30-días REAL backtest con price history minuto a minuto."""
    df = pd.read_csv("data/poly_backtest_year/v4_real/v4_real_30d_combined.csv")
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    df = df[df["signal"].isin(["UP", "DOWN"])].copy()
    df["edge_abs"] = df["signal_edge_up"].abs()
    return df


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def apply_filters_historical(df: pd.DataFrame, cfg: BotConfig) -> pd.DataFrame:
    out = df[df["edge_abs"] >= cfg.threshold].copy()
    if cfg.skip_hours_utc:
        out = out[~out["hour"].isin(cfg.skip_hours_utc)]
    if cfg.skip_weekdays:
        out = out[~out["weekday"].isin(cfg.skip_weekdays)]
    if cfg.min_volume_usd > 0:
        out = out[out["volume_usd"] >= cfg.min_volume_usd]
    return out.reset_index(drop=True)


def apply_filters_v4(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    return df[df["edge_abs"] >= threshold].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Bankroll simulation
# ---------------------------------------------------------------------------

def simulate(sig: pd.DataFrame) -> dict:
    bankroll = INITIAL_BANKROLL
    n = 0
    wins = 0
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
        pnl_total += payoff - cost_paid
        if outcome_correct: wins += 1
        n += 1
        peak = max(peak, bankroll)
        dd = (bankroll - peak) / peak if peak > 0 else 0
        max_dd = min(max_dd, dd)

    return {
        "trades": n,
        "wr": (100 * wins / n) if n else float("nan"),
        "pnl_kelly": pnl_total,
        "final": bankroll,
        "max_dd": 100 * max_dd,
        "avg_per_trade": (pnl_total / n) if n else 0,
    }


# ---------------------------------------------------------------------------
# Also: stake-$1 fixed simulation (no compounding) for honest mean
# ---------------------------------------------------------------------------

def simulate_fixed_stake(sig: pd.DataFrame, stake: float = 1.0) -> dict:
    """Each trade uses exactly `stake` regardless of bankroll. Useful to compare
    raw edge across bots without compounding distortion."""
    n = 0
    wins = 0
    pnl = 0.0
    sig = sig.sort_values("window_start").reset_index(drop=True)
    for _, t in sig.iterrows():
        edge = t["signal_edge_up"]
        direction = "UP" if edge > 0 else "DOWN"
        p_poly = t["p_poly_at_signal"]
        if direction == "UP":
            naive_fill = p_poly
        else:
            naive_fill = 1.0 - p_poly
        fill = min(1.0, naive_fill + HALF_SPREAD)
        if fill >= 0.99:
            continue
        contracts = stake / fill
        prop_fee = contracts * fill * FEE_RATE
        cost = contracts * fill + prop_fee + FLAT_FEE
        outcome_correct = (t["outcome"] == direction)
        payoff = contracts if outcome_correct else 0.0
        pnl += payoff - cost
        if outcome_correct: wins += 1
        n += 1
    return {
        "trades": n,
        "wr": (100 * wins / n) if n else float("nan"),
        "pnl_stake1": pnl,
        "avg_pnl_per_trade": (pnl / n) if n else 0,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Período: {START_TS.date()} → {END_TS.date()} (30 días)")
    print()

    df_hist = load_historical()
    df_v4 = load_v4_real()
    print(f"Historical signals (filtros V1+): {len(df_hist):,}")
    print(f"V4 real signals (raw):            {len(df_v4):,}")
    print()

    results = []
    # V1
    s = apply_filters_historical(df_hist, V1)
    fixed = simulate_fixed_stake(s)
    kelly = simulate(s)
    results.append(("V1 · Alerts (5pp)", "Histórico", s, fixed, kelly))

    # V2B
    s = apply_filters_historical(df_hist, V2B)
    fixed = simulate_fixed_stake(s)
    kelly = simulate(s)
    results.append(("V2B · Selective (10pp + skip)", "Histórico", s, fixed, kelly))

    # V4A — 30pp real
    s = apply_filters_v4(df_v4, 0.30)
    fixed = simulate_fixed_stake(s)
    kelly = simulate(s)
    results.append(("V4A · Endgame 30pp (REAL)", "Real (last 5min)", s, fixed, kelly))

    # V4B — 40pp real
    s = apply_filters_v4(df_v4, 0.40)
    fixed = simulate_fixed_stake(s)
    kelly = simulate(s)
    results.append(("V4B · Endgame 40pp (REAL)", "Real (last 5min)", s, fixed, kelly))

    # V5A — 20pp + skip + vol $8k
    s = apply_filters_historical(df_hist, V5A)
    fixed = simulate_fixed_stake(s)
    kelly = simulate(s)
    results.append(("V5A · Maker (20pp + skip + vol)", "Histórico", s, fixed, kelly))

    # V5B — 15pp loose
    s = apply_filters_historical(df_hist, V5B)
    fixed = simulate_fixed_stake(s)
    kelly = simulate(s)
    results.append(("V5B · Maker loose (15pp + skip)", "Histórico", s, fixed, kelly))

    # Table
    rows = []
    print(f"{'Bot':<38} | {'Trades':>6} | {'WR':>6} | {'PnL $1':>8} | {'avg':>8} | {'PnL Kelly':>11} | {'final':>10} | {'DD':>5}")
    print("-" * 130)
    for name, source, sig, fixed, kelly in results:
        row = {
            "bot":        name,
            "fuente":     source,
            "trades_30d": fixed["trades"],
            "trades_dia": round(fixed["trades"] / 30, 2),
            "wr_pct":     round(fixed["wr"], 1) if fixed["wr"] == fixed["wr"] else None,
            "pnl_stake1": round(fixed["pnl_stake1"], 2),
            "avg_per_trade_stake1": round(fixed["avg_pnl_per_trade"], 4),
            "pnl_kelly_30d_dolar":  round(kelly["pnl_kelly"], 2),
            "final_kelly":          round(kelly["final"], 2),
            "max_dd_pct":           round(kelly["max_dd"], 1),
        }
        rows.append(row)
        wr_str = f"{fixed['wr']:.1f}%" if fixed["wr"] == fixed["wr"] else "n/a"
        print(
            f"{name:<38} | {fixed['trades']:>6} | {wr_str:>6} | "
            f"${fixed['pnl_stake1']:>+7.2f} | ${fixed['avg_pnl_per_trade']:>+7.4f} | "
            f"${kelly['pnl_kelly']:>+10,.2f} | ${kelly['final']:>9,.2f} | "
            f"{kelly['max_dd']:>+4.1f}%"
        )

    # Excel
    out_path = Path("data/poly_backtest_year/six_bots_comparison.xlsx")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(out_path, index=False)
    print()
    print(f"Excel guardado: {out_path}")


if __name__ == "__main__":
    main()
