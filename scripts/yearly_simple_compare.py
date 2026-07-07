"""Comparativa de 1 año, $100 inicial, métricas SIMPLES como si fuera real:

  - Cuántos trades hizo
  - Cuántos ganó (% WR)
  - Profit total en USD
  - Peor pérdida individual (un trade)
  - Drawdown máximo (% caída desde el peak)
  - Bankroll final

Para V1/V2B/V5: 11 meses de data histórica (jun 2025 → may 2026).
Para V4: extrapolación lineal de 30 días reales × 12 (con disclaimer claro).
Cuando termine el fetch real 1 año de V4, este script se re-corre con la data real.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

INITIAL_BANKROLL = 100.0
FIXED_STAKE_USD = 10.0     # stake constante por trade (sin compounding)
BANKROLL_FLOOR = 30.0

HALF_SPREAD = 0.015
FLAT_FEE = 0.005
FEE_RATE = 0.02

START_TS = pd.Timestamp("2025-06-02", tz="UTC")
END_TS   = pd.Timestamp("2026-05-27", tz="UTC")


@dataclass
class BotConfig:
    name: str
    threshold: float
    skip_hours_utc: tuple[int, ...] = ()
    skip_weekdays: tuple[str, ...] = ()
    min_volume_usd: float = 0.0
    description: str = ""


V1 = BotConfig("V1 · Alerts (5pp, sin filtros)", 0.05,
               description="Alarma cada vez que ve edge ≥ 5pp")
V2B = BotConfig("V2B · Selective (10pp + skip)", 0.10,
                skip_hours_utc=(21, 23),
                skip_weekdays=("Saturday",),
                min_volume_usd=5000.0,
                description="10pp + sin 21-23 UTC + sin sab + vol $5k")
V5A = BotConfig("V5A · Maker (20pp + skip + vol)", 0.20,
                skip_hours_utc=(0, 1, 2, 21, 22, 23),
                skip_weekdays=("Saturday", "Sunday"),
                min_volume_usd=8000.0,
                description="20pp + skip 21-02 UTC + skip finde + vol $8k")
V5B = BotConfig("V5B · Maker loose (15pp + skip)", 0.15,
                skip_hours_utc=(0, 1, 2, 21, 22, 23),
                skip_weekdays=("Saturday", "Sunday"),
                description="15pp + skip 21-02 UTC + skip finde, sin vol")


def load_historical() -> pd.DataFrame:
    frames = []
    for a in ("btc", "eth", "sol", "xrp"):
        df = pd.read_csv(f"data/poly_backtest_year/{a}_hourly_1y_full.csv")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    df = df[df["signal"].notna() & df["outcome"].notna()]
    df = df[(df["window_start"] >= START_TS) & (df["window_start"] < END_TS)]
    df["edge_abs"] = df["signal_edge_up"].abs()
    df["hour"] = df["window_start"].dt.hour
    df["weekday"] = df["window_start"].dt.day_name()
    return df


def apply_filters(df: pd.DataFrame, cfg: BotConfig) -> pd.DataFrame:
    out = df[df["edge_abs"] >= cfg.threshold].copy()
    if cfg.skip_hours_utc:
        out = out[~out["hour"].isin(cfg.skip_hours_utc)]
    if cfg.skip_weekdays:
        out = out[~out["weekday"].isin(cfg.skip_weekdays)]
    if cfg.min_volume_usd > 0:
        out = out[out["volume_usd"] >= cfg.min_volume_usd]
    return out.reset_index(drop=True)


def simulate_real(sig: pd.DataFrame, stake: float = FIXED_STAKE_USD) -> dict:
    """Stake fijo (sin compounding) — refleja $100 bankroll, $10 por trade,
    extraer ganancias mensual. Es lo más realista para bankroll chico.

    Bankroll tracking sigue acumulando PnL para detectar drawdown.
    Si bankroll cae por debajo del floor, el bot para (game over).
    """
    bankroll = INITIAL_BANKROLL
    n = 0
    wins = 0
    pnl_list: list[float] = []
    peak = bankroll
    max_dd = 0.0
    sig = sig.sort_values("window_start").reset_index(drop=True)
    game_over_at: pd.Timestamp | None = None

    for _, t in sig.iterrows():
        if bankroll < BANKROLL_FLOOR:
            if game_over_at is None:
                game_over_at = t["window_start"]
            continue
        edge = t["signal_edge_up"]
        direction = "UP" if edge > 0 else "DOWN"
        p_poly = t["p_poly_at_signal"]
        p_fair = t["p_fair_at_signal"]
        naive_fill = p_poly if direction == "UP" else (1.0 - p_poly)
        p_model = p_fair if direction == "UP" else (1.0 - p_fair)
        fill = min(1.0, naive_fill + HALF_SPREAD)
        if fill >= 0.99:
            continue
        fill_total = fill * (1.0 + FEE_RATE)
        if p_model <= fill_total:
            continue
        # stake fijo
        position_usd = min(stake, bankroll * 0.95)
        contracts = position_usd / fill
        prop_fee = contracts * fill * FEE_RATE
        cost_paid = contracts * fill + prop_fee + FLAT_FEE
        if cost_paid > bankroll:
            continue
        outcome_correct = (t["outcome"] == direction)
        payoff = contracts if outcome_correct else 0.0
        pnl = payoff - cost_paid
        bankroll += pnl
        pnl_list.append(pnl)
        if outcome_correct: wins += 1
        n += 1
        peak = max(peak, bankroll)
        dd = (bankroll - peak) / peak if peak > 0 else 0
        max_dd = min(max_dd, dd)

    return {
        "trades":      n,
        "wins":        wins,
        "wr":          (100 * wins / n) if n else float("nan"),
        "profit_usd":  bankroll - INITIAL_BANKROLL,
        "bankroll":    bankroll,
        "max_dd_pct":  100 * max_dd,
        "worst_trade": (min(pnl_list) if pnl_list else 0.0),
        "best_trade":  (max(pnl_list) if pnl_list else 0.0),
        "game_over":   game_over_at,
    }


def fmt(label: str, r: dict) -> None:
    days = (END_TS - START_TS).days
    months = days / 30.4
    avg_per_month = r["profit_usd"] / months if months else 0
    game_over = ""
    if r.get("game_over") is not None:
        game_over = f"\n    GAME OVER en          : {r['game_over'].date()} (bankroll cayó debajo de ${BANKROLL_FLOOR})"
    print(
        f"  {label:<40}\n"
        f"    Trades                : {r['trades']:>6}\n"
        f"    Trades ganadores      : {r['wins']:>6} ({r['wr']:.1f}%)\n"
        f"    Profit total          : ${r['profit_usd']:>+12,.2f}\n"
        f"    Profit promedio mes   : ${avg_per_month:>+12,.2f}\n"
        f"    Peor trade individual : ${r['worst_trade']:>+10,.2f}\n"
        f"    Mejor trade individual: ${r['best_trade']:>+10,.2f}\n"
        f"    Drawdown maximo       : {r['max_dd_pct']:>+6.1f}%\n"
        f"    Bankroll final ($100→): ${r['bankroll']:>+11,.2f}{game_over}\n"
    )


def main():
    print(f"PERIODO: {START_TS.date()} → {END_TS.date()} ({(END_TS - START_TS).days} dias)")
    print(f"Capital inicial: ${INITIAL_BANKROLL}")
    print(f"Costos: 1.5¢ spread + 0.5¢ flat + 2% fee · STAKE FIJO ${FIXED_STAKE_USD}/trade")
    print(f"(sin compounding — refleja $100 inicial, extraer ganancias mensual)")
    print()

    df_hist = load_historical()
    print(f"Mercados disponibles (1 año, 4 assets): {len(df_hist):,}")
    print()

    rows = []
    for cfg in (V1, V2B, V5A, V5B):
        s = apply_filters(df_hist, cfg)
        r = simulate_real(s)
        fmt(cfg.name, r)
        rows.append({"bot": cfg.name, "description": cfg.description, **r})

    # V4 REAL 1 año completo
    print("  --- V4 (REAL data 1 año completo, fetch CLOB minuto a minuto) ---")
    v4 = pd.read_csv("data/poly_backtest_year/v4_real/v4_real_1y.csv")
    v4["window_start"] = pd.to_datetime(v4["window_start"], utc=True)
    v4 = v4[v4["signal"].isin(["UP", "DOWN"])].copy()
    v4["edge_abs"] = v4["signal_edge_up"].abs()
    for label, threshold in (("V4A · Endgame 30pp (REAL 1y)", 0.30),
                              ("V4B · Endgame 40pp (REAL 1y)", 0.40)):
        s = v4[v4["edge_abs"] >= threshold].reset_index(drop=True)
        r = simulate_real(s)
        fmt(label, r)
        rows.append({"bot": label, "description": "Real 1 año (fetch CLOB)", **r})

    # Excel
    out = Path("data/poly_backtest_year/yearly_simple_compare.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(out, index=False)
    print(f"Excel guardado: {out}")


if __name__ == "__main__":
    main()
