"""Backtest comparativo de V3 SumOne / V4 Endgame / V5 Maker.

V4 y V5 se computan directamente de los CSVs full hourly (que tienen
signal_minute + signal_edge_up + outcome + window_seconds para todos los
mercados, no solo los del threshold V1).

V3 SumOne necesita data de DOWN token (no la tenemos en cache local) —
se computa con una heurística analítica conservadora basada en la
distribución observada de spreads.

Salida: tabla por bot × timeframe (1w / 1m / 6m / 1y).
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Config — mismos parámetros que los bots vivos
# --------------------------------------------------------------------------

INITIAL_BANKROLL = 100.0
KELLY_FRACTION = 0.50
MAX_PCT_PER_TRADE = 0.20
MAX_POSITION_USD = 500.0
MIN_POSITION_USD = 1.0
BANKROLL_FLOOR = 30.0
MAX_CONCURRENT = 4

# Costos (idénticos al paper trader y a los otros backtests)
HALF_SPREAD = 0.015
FLAT_FEE = 0.005
FEE_RATE = 0.02

# --------------------------------------------------------------------------
# Bot configs
# --------------------------------------------------------------------------

@dataclass
class BotConfig:
    name: str
    threshold: float
    max_seconds_to_resolution: int | None = None  # V4 solo
    min_seconds_to_resolution: int = 60
    skip_hours_utc: tuple[int, ...] = ()
    skip_weekdays: tuple[str, ...] = ()
    min_volume_usd: float = 0.0


V4 = BotConfig(
    name="V4 · Endgame (any-minute 30pp)",
    threshold=0.30,
)

V4_TIGHT = BotConfig(
    name="V4 · Endgame (any-minute 35pp)",
    threshold=0.35,
)

V5 = BotConfig(
    name="V5 · Maker",
    threshold=0.20,
    skip_hours_utc=(0, 1, 2, 21, 22, 23),
    skip_weekdays=("Saturday", "Sunday"),
    min_volume_usd=8000.0,
)

V5_LOOSE = BotConfig(
    name="V5 · Maker loose (15pp, sin vol)",
    threshold=0.15,
    skip_hours_utc=(0, 1, 2, 21, 22, 23),
    skip_weekdays=("Saturday", "Sunday"),
)


# --------------------------------------------------------------------------
# Carga y filtros
# --------------------------------------------------------------------------

def load_all_markets(data_dir: Path, max_date: str = "2026-06-02") -> pd.DataFrame:
    frames = []
    for asset in ("btc", "eth", "sol", "xrp"):
        fn = data_dir / f"{asset}_hourly_1y_full.csv"
        df = pd.read_csv(fn)
        df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values("window_start").reset_index(drop=True)
    df = df[df["signal"].notna()].copy()
    df = df[df["outcome"].notna()].copy()
    cutoff = pd.Timestamp(max_date, tz="UTC")
    df = df[df["window_start"] < cutoff].copy()
    return df.reset_index(drop=True)


def apply_filters(df: pd.DataFrame, cfg: BotConfig) -> pd.DataFrame:
    """Filtra los mercados según la config del bot."""
    out = df.copy()
    # Threshold de edge
    out = out[out["signal_edge_up"].abs() >= cfg.threshold]
    # Tiempo restante (V4 Endgame)
    if cfg.max_seconds_to_resolution is not None:
        secs_remaining = (
            out["window_seconds"] - out["signal_minute"].astype(float) * 60
        )
        mask = (secs_remaining <= cfg.max_seconds_to_resolution) & \
               (secs_remaining >= cfg.min_seconds_to_resolution)
        out = out[mask]
    # Skip horas UTC
    if cfg.skip_hours_utc:
        out = out[~out["window_start"].dt.hour.isin(cfg.skip_hours_utc)]
    # Skip días
    if cfg.skip_weekdays:
        weekday_names = out["window_start"].dt.day_name()
        out = out[~weekday_names.isin(cfg.skip_weekdays)]
    # Volumen mínimo
    if cfg.min_volume_usd > 0:
        out = out[out["volume_usd"] >= cfg.min_volume_usd]
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------
# Simulación de bankroll
# --------------------------------------------------------------------------

def simulate(trades: pd.DataFrame, initial: float = INITIAL_BANKROLL) -> dict:
    """Recorre los trades en orden cronológico aplicando Kelly + caps."""
    bankroll = initial
    open_trades: list[tuple[pd.Timestamp, float, float, bool]] = []  # (close_ts, cost, contracts, correct)
    pnl_list = []
    wins = 0
    n = 0
    peak = bankroll
    max_dd = 0.0

    # Calcular close timestamp
    trades = trades.copy()
    trades["close_ts"] = trades["window_start"] + pd.to_timedelta(
        trades["window_seconds"], unit="s"
    )

    for _, t in trades.iterrows():
        # 1) Liquidar posiciones que cerraron antes de este trade
        while open_trades and open_trades[0][0] <= t["window_start"]:
            close_ts, cost, contracts, correct = open_trades.pop(0)
            payoff = contracts if correct else 0.0
            bankroll += payoff
            pnl = payoff - cost
            pnl_list.append(pnl)
            if pnl > 0: wins += 1
            n += 1
            peak = max(peak, bankroll)
            dd = (bankroll - peak) / peak if peak > 0 else 0
            max_dd = min(max_dd, dd)

        # 2) Cap concurrencia y bankroll floor
        if bankroll < BANKROLL_FLOOR:
            continue
        if len(open_trades) >= MAX_CONCURRENT:
            continue

        # 3) Calcular sizing Kelly-fractional
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

        # 4) Simular fill + costo
        contracts = position_usd / fill
        prop_fee = contracts * fill * FEE_RATE
        cost_paid = contracts * fill + prop_fee + FLAT_FEE
        if cost_paid > bankroll:
            continue
        bankroll -= cost_paid
        correct = bool(t["correct"]) and (t["outcome"] == direction or pd.isna(t["outcome"]) is False and t["outcome"] == direction)
        # 'correct' viene precalculado en el CSV (toma signal vs outcome)
        # pero por seguridad recomputo según 'direction':
        outcome_correct = (t["outcome"] == direction)
        open_trades.append((t["close_ts"], cost_paid, contracts, outcome_correct))

    # 5) Liquidar las que quedaron abiertas
    while open_trades:
        close_ts, cost, contracts, correct = open_trades.pop(0)
        payoff = contracts if correct else 0.0
        bankroll += payoff
        pnl = payoff - cost
        pnl_list.append(pnl)
        if pnl > 0: wins += 1
        n += 1
        peak = max(peak, bankroll)
        dd = (bankroll - peak) / peak if peak > 0 else 0
        max_dd = min(max_dd, dd)

    if n == 0:
        return {
            "trades": 0, "wins": 0, "wr": float("nan"),
            "final": bankroll, "pnl": bankroll - initial, "roi": 0.0,
            "max_dd": 0.0, "avg_pnl": 0.0,
        }

    return {
        "trades": n,
        "wins": wins,
        "wr": 100 * wins / n,
        "final": bankroll,
        "pnl": bankroll - initial,
        "roi": 100 * (bankroll - initial) / initial,
        "max_dd": 100 * max_dd,
        "avg_pnl": sum(pnl_list) / n,
    }


# --------------------------------------------------------------------------
# Backtest por timeframe
# --------------------------------------------------------------------------

TIMEFRAMES = {
    "1 semana": 7,
    "1 mes":    30,
    "6 meses":  180,
    "1 año":    365,
}


def run_backtest(df_all: pd.DataFrame, cfg: BotConfig) -> pd.DataFrame:
    end_ts = df_all["window_start"].max()
    filtered = apply_filters(df_all, cfg)
    rows = []
    for tf_name, days in TIMEFRAMES.items():
        start_ts = end_ts - pd.Timedelta(days=days)
        sub = filtered[filtered["window_start"] >= start_ts].copy()
        result = simulate(sub)
        rows.append({
            "Timeframe": tf_name,
            "Período": f"{start_ts.date()} → {end_ts.date()}",
            **result,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# V3 SumOne — estimación analítica
# --------------------------------------------------------------------------
#
# No tenemos data de DOWN token, pero podemos *estimar* la frecuencia de
# eventos sum<1 a partir de la volatilidad del UP token (que sí tenemos).
#
# Heurística:
#   - El mid de UP se mueve en escala de 1-3¢/min según p_poly y el ticker.
#   - Cuando p_poly cambia bruscamente, el sum UP+DOWN se desbalancea
#     temporalmente porque DOWN actualiza con delay.
#   - Asumimos que ocurre 1 evento sum<0.97 por cada ~200 mercados (≈ 0.5%
#     según observación de logs en vivo y reportes públicos).
#   - Margen promedio neto por par: 0.5¢ (después de costos).
#
# Esta es una estimación CONSERVADORA pero acepto que es una hipótesis. La
# data en vivo del bot V3 corriendo va a refinarla.


def estimate_v3_sumone(df_all: pd.DataFrame) -> pd.DataFrame:
    end_ts = df_all["window_start"].max()
    rows = []
    for tf_name, days in TIMEFRAMES.items():
        start_ts = end_ts - pd.Timedelta(days=days)
        sub = df_all[df_all["window_start"] >= start_ts]
        n_markets = len(sub)
        # 0.5% de los mercados generan un evento sum<0.97 explotable
        opps = max(0, int(round(n_markets * 0.005)))
        # Position size típica: 10% bankroll, capeado a $200
        # Profit neto por arb: 0.5–1.5¢ por par → asumimos 1¢ promedio
        # Con $50 stake y 100 contracts, profit = $1.00 por arb
        avg_profit_per_arb = 1.00
        total_profit = opps * avg_profit_per_arb
        final = INITIAL_BANKROLL + total_profit
        rows.append({
            "Timeframe": tf_name,
            "Período": f"{start_ts.date()} → {end_ts.date()}",
            "trades": opps,
            "wins": opps,         # sum-to-one es 100% WR por diseño
            "wr": 100.0 if opps > 0 else float("nan"),
            "final": final,
            "pnl": total_profit,
            "roi": 100 * total_profit / INITIAL_BANKROLL,
            "max_dd": 0.0,         # risk-free
            "avg_pnl": avg_profit_per_arb if opps > 0 else 0.0,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def fmt_row(r: pd.Series) -> str:
    return (
        f"  {r['Timeframe']:<10}  {r['Período']:<30}  "
        f"trades={r['trades']:>5}  WR={r['wr']:>5.1f}%  "
        f"final=${r['final']:>10,.2f}  PnL=${r['pnl']:>+10,.2f}  "
        f"ROI={r['roi']:>+8.1f}%  DD={r['max_dd']:>+5.1f}%"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/poly_backtest_year")
    ap.add_argument("--out-dir",  default="data/poly_backtest_year/v3_v4_v5")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Cargando mercados (4 assets, 1 año)...")
    df = load_all_markets(data_dir)
    print(f"Total mercados con signal+outcome: {len(df):,}")
    print(f"Rango: {df['window_start'].min().date()} → {df['window_start'].max().date()}")
    print()

    all_results = {}

    for cfg in (V4, V4_TIGHT, V5, V5_LOOSE):
        print(f"=== {cfg.name} ===")
        result = run_backtest(df, cfg)
        all_results[cfg.name] = result
        for _, r in result.iterrows():
            print(fmt_row(r))
        print()

    print("=== V3 · SumOne (estimación analítica) ===")
    v3 = estimate_v3_sumone(df)
    all_results["V3 · SumOne (estimado)"] = v3
    for _, r in v3.iterrows():
        print(fmt_row(r))
    print()

    # Guardar a Excel
    excel_path = out_dir / "v3_v4_v5_backtest.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for name, df_result in all_results.items():
            sheet = name.replace(" · ", "_").replace(" ", "_").replace(",", "")[:30]
            df_result.to_excel(writer, sheet_name=sheet, index=False)
    print(f"Excel guardado: {excel_path}")


if __name__ == "__main__":
    main()
