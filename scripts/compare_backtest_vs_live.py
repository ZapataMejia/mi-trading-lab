"""Compara backtest del 2-9 jun vs reporte real del bot del VPS (Telegram).

Reporte real (de Telegram /week del 8 jun):
    V4B    8t  WR 62.5%   +$800.51
    V4A   29t  WR 44.8%   +$294.23
    V1   670t  WR 47.0%    +$10.06
    V2B    1t  WR  0.0%     -$9.22
    V4C    6t  WR 33.3%    -$31.13
    TOTAL 714t              +$1,064.45

Backtest aplica las MISMAS reglas que cada bot usa, sobre data fresca.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

CSV = Path("data/poly_backtest_year/v4_real/v4_real_jun2_jun9_v2.csv")
CSV_ENDGAME = Path("data/poly_backtest_year/v4_real/v4_real_jun2_jun9_endgame.csv")

# Reporte real (Telegram /week del lunes 8 jun)
LIVE = {
    "V1":  {"trades": 670, "wr_pct": 47.0, "pnl": +10.06,   "rules": "threshold 5pp, sin filtros (hourly)"},
    "V2B": {"trades":   1, "wr_pct":  0.0, "pnl":  -9.22,   "rules": "threshold 15pp + skip h21,23 + skip sab + vol>=$5k"},
    "V4A": {"trades":  29, "wr_pct": 44.8, "pnl": +294.23,  "rules": "threshold 30pp endgame 5min"},
    "V4B": {"trades":   8, "wr_pct": 62.5, "pnl": +800.51,  "rules": "threshold 40pp endgame 5min"},
    "V4C": {"trades":   6, "wr_pct": 33.3, "pnl":  -31.13,  "rules": "threshold 30pp endgame 5min, solo SOL"},
}


def apply_filters(df: pd.DataFrame,
                  threshold: float,
                  endgame_5min: bool = False,
                  asset_only: str | None = None,
                  skip_hours: tuple = (),
                  skip_weekdays: tuple = (),
                  min_volume: float = 0.0) -> pd.DataFrame:
    """Aplica los filtros de una estrategia y devuelve solo trades válidos."""
    sig = df[df["signal"].isin(["UP", "DOWN"])].copy()
    sig["window_start"] = pd.to_datetime(sig["window_start"], utc=True)
    sig["hour"] = sig["window_start"].dt.hour
    sig["weekday"] = sig["window_start"].dt.day_name()
    sig["edge_abs"] = sig["signal_edge_up"].abs()

    sig = sig[sig["edge_abs"] >= threshold]
    if asset_only:
        sig = sig[sig["asset"] == asset_only]
    if skip_hours:
        sig = sig[~sig["hour"].isin(skip_hours)]
    if skip_weekdays:
        sig = sig[~sig["weekday"].isin(skip_weekdays)]
    if min_volume > 0:
        sig = sig[sig["volume_usd"] >= min_volume]
    return sig


def simulate_fixed(sig: pd.DataFrame, stake: float = 10.0) -> dict:
    """Simula con stake fijo y devuelve trades, wins, pnl."""
    if sig.empty:
        return {"trades": 0, "wins": 0, "losses": 0, "wr_pct": 0.0, "pnl": 0.0}

    wins = 0
    pnl_total = 0.0
    for _, row in sig.iterrows():
        direction = row["signal"]
        outcome = row["outcome"]
        won = (outcome == direction)
        # Fill price ya viene del scraper (col `fill_price` incluye half-spread+fee)
        fill = float(row["fill_price"])
        if fill <= 0 or fill >= 1.0:
            continue
        contracts = stake / fill
        prop_fee = contracts * fill * 0.02
        flat_fee = 0.005
        cost = contracts * fill + prop_fee + flat_fee
        payoff = contracts if won else 0.0
        pnl = payoff - cost
        pnl_total += pnl
        if won:
            wins += 1

    n = len(sig)
    return {
        "trades": n,
        "wins": wins,
        "losses": n - wins,
        "wr_pct": wins / n * 100 if n else 0,
        "pnl": pnl_total,
    }


def main():
    if not CSV.exists():
        print(f"ERROR: no encuentro {CSV}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(CSV)
    print(f"Cargado {len(df):,} mercados (full-cycle) de {CSV}")
    print(f"Ventana: {df['window_start'].min()} → {df['window_start'].max()}")

    # V4 usa data del scrape "endgame" (último 5 min de cada mercado)
    if CSV_ENDGAME.exists():
        df_endgame = pd.read_csv(CSV_ENDGAME)
        print(f"Cargado {len(df_endgame):,} mercados (endgame) de {CSV_ENDGAME}")
    else:
        print(f"WARN: no encuentro {CSV_ENDGAME}, V4 va a usar el CSV full-cycle (subestimará trades)")
        df_endgame = df
    print()

    bots_bt = {
        "V1":  simulate_fixed(apply_filters(df, threshold=0.05), stake=10),
        "V2B": simulate_fixed(apply_filters(df, threshold=0.15, skip_hours=(21, 23),
                                            skip_weekdays=("Saturday",), min_volume=5000), stake=10),
        "V4A": simulate_fixed(apply_filters(df_endgame, threshold=0.30), stake=10),
        "V4B": simulate_fixed(apply_filters(df_endgame, threshold=0.40), stake=10),
        "V4C": simulate_fixed(apply_filters(df_endgame, threshold=0.30, asset_only="solana"), stake=10),
    }

    # --- Reporte comparado --------------------------------------------------
    print("=" * 110)
    print(f"BACKTEST vs LIVE · Ventana 2026-06-02 → 2026-06-09 · Stake fijo $10 (lo que muestra hoy el backtest)")
    print("=" * 110)
    print(f"{'Bot':<5} | {'BACKTEST trades':>16} | {'BT WR':>7} | {'BT PnL':>10} | {'LIVE trades':>12} | {'LIVE WR':>8} | {'LIVE PnL':>10} | match?")
    print("-" * 110)
    for bot, lv in LIVE.items():
        bt = bots_bt[bot]
        # match: si ambos +/-, si trades en mismo orden de magnitud
        same_sign = (bt["pnl"] >= 0) == (lv["pnl"] >= 0)
        bt_t = bt["trades"]
        lv_t = lv["trades"]
        trades_close = lv_t == 0 or 0.3 <= bt_t / max(1, lv_t) <= 3.0
        verdict = "✓" if same_sign and trades_close else "✗" if not same_sign else "~"
        print(f"{bot:<5} | {bt_t:>16,} | {bt['wr_pct']:>6.1f}% | ${bt['pnl']:>9,.2f} | {lv_t:>12,} | {lv['wr_pct']:>7.1f}% | ${lv['pnl']:>9,.2f} | {verdict}")

    print("-" * 110)
    total_bt_t = sum(b['trades'] for b in bots_bt.values())
    total_bt_pnl = sum(b['pnl'] for b in bots_bt.values())
    total_lv_t = sum(b['trades'] for b in LIVE.values())
    total_lv_pnl = sum(b['pnl'] for b in LIVE.values())
    print(f"{'TOTAL':<5} | {total_bt_t:>16,} | {'':>7} | ${total_bt_pnl:>9,.2f} | {total_lv_t:>12,} | {'':>8} | ${total_lv_pnl:>9,.2f} |")
    print()
    print("Notas:")
    print(" - Backtest usa stake fijo $10/trade. Live usa Kelly (apuesta % del bankroll).")
    print(" - V4* usa CSV endgame (filtra señales SOLO en los últimos 5 min antes de resolución).")
    print(" - V1/V2B usan CSV full-cycle (signal en cualquier minuto del ciclo).")
    print(" - Backtest entra 100% de las señales que detecta; el bot real pierde ~30-40%")
    print("   a slippage/latencia/missed entries, así que conteo BT > live es esperado.")
    print(" - Lo comparable es: SIGNO del PnL, WR ratio, orden de magnitud del count.")


if __name__ == "__main__":
    main()
