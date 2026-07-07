"""Simulacion 1-31 mayo 2026: 5 bots, $100 bankroll, $10 stake fijo (sin compounding).

Bots:
  V1   - Alerts        : edge >= 5pp, sin filtros, todos los assets (BTC/ETH/SOL/XRP hourly)
  V2B  - Selective     : edge >= 10pp, skip hour UTC 21/23, skip sabado, vol >= $5000
  V4A  - Endgame 30pp  : edge >= 30pp, ultimos 5 min (CSV ya filtrado a signal_minute 55-59)
  V4B  - Endgame 40pp  : igual que V4A pero threshold 40pp
  V4C  - SOL-only 30pp : igual que V4A pero asset == 'solana'

Costos realistas (mismos que yearly_simple_compare.py):
  - half_spread = 1.5c
  - flat_fee    = 0.5c
  - fee_rate    = 2% proporcional
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

INITIAL_BANKROLL = 100.0
FIXED_STAKE_USD  = 10.0
BANKROLL_FLOOR   = 30.0

HALF_SPREAD = 0.015
FLAT_FEE    = 0.005
FEE_RATE    = 0.02

START_TS = pd.Timestamp("2026-05-01", tz="UTC")
END_TS   = pd.Timestamp("2026-06-01", tz="UTC")  # exclusivo


@dataclass
class BotConfig:
    name: str
    threshold: float
    skip_hours_utc: tuple[int, ...] = ()
    skip_weekdays: tuple[str, ...] = ()
    min_volume_usd: float = 0.0
    only_asset: str | None = None
    description: str = ""


V1  = BotConfig("V1  Alerts (5pp, sin filtros)", 0.05,
                description="Alarma cada vez que ve edge >= 5pp")
V2B = BotConfig("V2B Selective (10pp + skip)", 0.10,
                skip_hours_utc=(21, 23),
                skip_weekdays=("Saturday",),
                min_volume_usd=5000.0,
                description="10pp + sin 21/23 UTC + sin sab + vol $5k")
V4A = BotConfig("V4A Endgame 30pp", 0.30,
                description="Endgame 5min, edge >= 30pp, todos los assets")
V4B = BotConfig("V4B Endgame 40pp", 0.40,
                description="Endgame 5min, edge >= 40pp, todos los assets")
V4C = BotConfig("V4C SOL-only 30pp", 0.30,
                only_asset="solana",
                description="Endgame 5min, edge >= 30pp, solo SOL")


def load_hourly() -> pd.DataFrame:
    frames = []
    for a in ("btc", "eth", "sol", "xrp"):
        df = pd.read_csv(f"data/poly_backtest_year/{a}_hourly_1y_full.csv")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    df = df[df["signal"].isin(["UP", "DOWN"]) & df["outcome"].notna()]
    df = df[(df["window_start"] >= START_TS) & (df["window_start"] < END_TS)]
    df["edge_abs"] = df["signal_edge_up"].abs()
    df["hour"]    = df["window_start"].dt.hour
    df["weekday"] = df["window_start"].dt.day_name()
    return df.reset_index(drop=True)


def load_v4() -> pd.DataFrame:
    df = pd.read_csv("data/poly_backtest_year/v4_real/v4_real_1y.csv")
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    df = df[df["signal"].isin(["UP", "DOWN"]) & df["outcome"].notna()]
    df = df[(df["window_start"] >= START_TS) & (df["window_start"] < END_TS)]
    df["edge_abs"] = df["signal_edge_up"].abs()
    df["hour"]    = df["window_start"].dt.hour
    df["weekday"] = df["window_start"].dt.day_name()
    return df.reset_index(drop=True)


def apply_filters(df: pd.DataFrame, cfg: BotConfig) -> pd.DataFrame:
    out = df[df["edge_abs"] >= cfg.threshold].copy()
    if cfg.skip_hours_utc:
        out = out[~out["hour"].isin(cfg.skip_hours_utc)]
    if cfg.skip_weekdays:
        out = out[~out["weekday"].isin(cfg.skip_weekdays)]
    if cfg.min_volume_usd > 0:
        out = out[out["volume_usd"] >= cfg.min_volume_usd]
    if cfg.only_asset is not None:
        out = out[out["asset"].str.lower() == cfg.only_asset.lower()]
    return out.sort_values("window_start").reset_index(drop=True)


def simulate(sig: pd.DataFrame, stake: float = FIXED_STAKE_USD) -> dict:
    """Stake fijo, sin compounding. Devuelve metricas del mes."""
    bankroll = INITIAL_BANKROLL
    n = wins = 0
    pnl_list: list[float] = []
    skipped_fill_high = skipped_no_edge_post_costs = 0
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
        p_model    = p_fair if direction == "UP" else (1.0 - p_fair)
        fill = min(1.0, naive_fill + HALF_SPREAD)
        if fill >= 0.99:
            skipped_fill_high += 1
            continue
        fill_total = fill * (1.0 + FEE_RATE)
        if p_model <= fill_total:
            skipped_no_edge_post_costs += 1
            continue
        position_usd = min(stake, bankroll * 0.95)
        contracts    = position_usd / fill
        prop_fee     = contracts * fill * FEE_RATE
        cost_paid    = contracts * fill + prop_fee + FLAT_FEE
        if cost_paid > bankroll:
            continue
        outcome_correct = (t["outcome"] == direction)
        payoff = contracts if outcome_correct else 0.0
        pnl    = payoff - cost_paid
        bankroll += pnl
        pnl_list.append(pnl)
        if outcome_correct:
            wins += 1
        n += 1

    return {
        "candidates":               len(sig),
        "skipped_fill_high":        skipped_fill_high,
        "skipped_no_edge_post":     skipped_no_edge_post_costs,
        "trades":                   n,
        "wins":                     wins,
        "wr_pct":                   (100 * wins / n) if n else 0.0,
        "profit_usd":               bankroll - INITIAL_BANKROLL,
        "bankroll_final":           bankroll,
        "roi_pct":                  100 * (bankroll - INITIAL_BANKROLL) / INITIAL_BANKROLL,
        "best_trade":               (max(pnl_list) if pnl_list else 0.0),
        "worst_trade":              (min(pnl_list) if pnl_list else 0.0),
        "game_over_at":             game_over_at,
    }


def fmt_bot(label: str, desc: str, r: dict) -> None:
    print(f"  {label}")
    print(f"    {desc}")
    print(f"    Candidatos (post filtros)    : {r['candidates']:>6}")
    print(f"    Skipped (fill >= 0.99)       : {r['skipped_fill_high']:>6}")
    print(f"    Skipped (no edge post-costs) : {r['skipped_no_edge_post']:>6}")
    print(f"    Trades ejecutados            : {r['trades']:>6}")
    print(f"    Ganadores                    : {r['wins']:>6} ({r['wr_pct']:.1f}%)")
    print(f"    Profit neto del mes          : ${r['profit_usd']:>+9,.2f}")
    print(f"    Mejor trade                  : ${r['best_trade']:>+9,.2f}")
    print(f"    Peor trade                   : ${r['worst_trade']:>+9,.2f}")
    print(f"    Bankroll final ($100 inicial): ${r['bankroll_final']:>+9,.2f}")
    print(f"    ROI mensual                  : {r['roi_pct']:>+6.2f}%")
    if r["game_over_at"] is not None:
        print(f"    *** GAME OVER en {r['game_over_at']} (bankroll < ${BANKROLL_FLOOR}) ***")
    print()


def main():
    print("=" * 72)
    print(f"SIMULACION MAYO 2026 — {START_TS.date()} a {(END_TS - pd.Timedelta(days=1)).date()}")
    print(f"Bankroll inicial: ${INITIAL_BANKROLL}  |  Stake fijo: ${FIXED_STAKE_USD}/trade")
    print(f"Costos: half-spread {HALF_SPREAD*100}c + flat {FLAT_FEE*100}c + {FEE_RATE*100:.0f}% prop")
    print("=" * 72)
    print()

    hourly = load_hourly()
    v4     = load_v4()
    print(f"Hourly (BTC/ETH/SOL/XRP) signals en mayo 2026: {len(hourly):>5}")
    print(f"V4 endgame (signal_minute>=55) signals en mayo: {len(v4):>5}")
    print()

    results = []
    # V1 y V2B usan hourly
    for cfg in (V1, V2B):
        s = apply_filters(hourly, cfg)
        r = simulate(s)
        fmt_bot(cfg.name, cfg.description, r)
        results.append({"bot": cfg.name, **r})
    # V4A, V4B, V4C usan v4_real
    for cfg in (V4A, V4B, V4C):
        s = apply_filters(v4, cfg)
        r = simulate(s)
        fmt_bot(cfg.name, cfg.description, r)
        results.append({"bot": cfg.name, **r})

    # Tabla resumen
    print("=" * 72)
    print("RESUMEN — ordenado por profit del mes (desc)")
    print("=" * 72)
    df = pd.DataFrame(results).sort_values("profit_usd", ascending=False)
    header = f"{'Bot':<32}{'Trades':>8}{'WR%':>7}{'Profit$':>10}{'Bank$':>10}{'ROI%':>8}{'Best$':>8}{'Worst$':>8}"
    print(header)
    print("-" * len(header))
    for _, row in df.iterrows():
        print(
            f"{row['bot']:<32}"
            f"{row['trades']:>8}"
            f"{row['wr_pct']:>7.1f}"
            f"{row['profit_usd']:>+10.2f}"
            f"{row['bankroll_final']:>10.2f}"
            f"{row['roi_pct']:>+8.2f}"
            f"{row['best_trade']:>+8.2f}"
            f"{row['worst_trade']:>+8.2f}"
        )
    print()

    out = "data/poly_backtest_year/may_2026_simulation.csv"
    df.to_csv(out, index=False)
    print(f"CSV guardado: {out}")


if __name__ == "__main__":
    main()
