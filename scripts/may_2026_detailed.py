"""Backtest DETALLADO mayo 2026 (1-31): 5 bots con metricas adicionales.

Extiende `scripts/may_2026_simulation.py` agregando:
  - Drawdown maximo ($ y % desde pico previo)
  - Peor / mejor trade individual
  - Volatilidad (std dev del PnL por trade)
  - PnL diario mas alto / mas bajo
  - Dias positivos vs negativos
  - Profit factor (ganado / perdido absoluto)

Misma logica de simulacion, mismos costos, mismo stake fijo $10, bankroll $100.
"""
from __future__ import annotations

import math
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


def simulate_detailed(sig: pd.DataFrame, stake: float = FIXED_STAKE_USD) -> dict:
    """Stake fijo, sin compounding. Devuelve metricas DETALLADAS con DD, profit factor, etc."""
    bankroll = INITIAL_BANKROLL
    n = wins = 0
    pnl_list: list[float] = []
    ts_list:  list[pd.Timestamp] = []
    bankroll_curve: list[float] = [INITIAL_BANKROLL]
    skipped_fill_high = skipped_no_edge_post_costs = 0
    game_over_at: pd.Timestamp | None = None
    best_fill = None  # para reportar contexto del mejor trade

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
        ts_list.append(t["window_start"])
        bankroll_curve.append(bankroll)
        if outcome_correct:
            wins += 1
        n += 1

    # ---- Metricas adicionales ----
    if not pnl_list:
        return {
            "candidates": len(sig),
            "skipped_fill_high": skipped_fill_high,
            "skipped_no_edge_post": skipped_no_edge_post_costs,
            "trades": 0, "wins": 0, "wr_pct": 0.0,
            "profit_usd": 0.0, "bankroll_final": INITIAL_BANKROLL,
            "roi_pct": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
            "best_trade_fill": None, "best_trade_ts": None,
            "worst_trade_ts": None,
            "dd_max_usd": 0.0, "dd_max_pct": 0.0,
            "dd_peak_bankroll": INITIAL_BANKROLL, "dd_valley_bankroll": INITIAL_BANKROLL,
            "dd_peak_ts": None, "dd_valley_ts": None,
            "volatility_usd": 0.0,
            "daily_best_usd": 0.0, "daily_worst_usd": 0.0,
            "daily_best_date": None, "daily_worst_date": None,
            "days_positive": 0, "days_negative": 0, "days_flat": 0,
            "total_days_traded": 0,
            "profit_factor": float("nan"),
            "gross_win_usd": 0.0, "gross_loss_usd": 0.0,
            "game_over_at": game_over_at,
        }

    # Drawdown: comparar bankroll_curve (incluye punto inicial) contra picos prev
    peak = bankroll_curve[0]
    peak_idx = 0
    max_dd_usd = 0.0
    max_dd_pct = 0.0
    peak_at_max = peak
    valley_at_max = peak
    peak_idx_at_max = 0
    valley_idx_at_max = 0
    for i, b in enumerate(bankroll_curve):
        if b > peak:
            peak = b
            peak_idx = i
        dd = b - peak
        if dd < max_dd_usd:
            max_dd_usd = dd
            max_dd_pct = (dd / peak) * 100 if peak > 0 else 0.0
            peak_at_max = peak
            valley_at_max = b
            peak_idx_at_max = peak_idx
            valley_idx_at_max = i

    # bankroll_curve[0] = inicial; bankroll_curve[i+1] corresponde a pnl_list[i] / ts_list[i]
    def _ts_for_curve_idx(i: int) -> pd.Timestamp | None:
        if i == 0:
            return START_TS
        return ts_list[i - 1] if i - 1 < len(ts_list) else None

    peak_ts   = _ts_for_curve_idx(peak_idx_at_max)
    valley_ts = _ts_for_curve_idx(valley_idx_at_max)

    # Volatilidad (std muestral del PnL por trade)
    mean = sum(pnl_list) / len(pnl_list)
    if len(pnl_list) > 1:
        var = sum((p - mean) ** 2 for p in pnl_list) / (len(pnl_list) - 1)
        vol = math.sqrt(var)
    else:
        vol = 0.0

    # Agregado diario
    df_trades = pd.DataFrame({"ts": ts_list, "pnl": pnl_list})
    df_trades["date"] = df_trades["ts"].dt.date
    daily = df_trades.groupby("date")["pnl"].sum().sort_index()
    daily_best_val   = float(daily.max())
    daily_worst_val  = float(daily.min())
    daily_best_date  = daily.idxmax()
    daily_worst_date = daily.idxmin()
    days_positive = int((daily > 0).sum())
    days_negative = int((daily < 0).sum())
    days_flat     = int((daily == 0).sum())
    total_days_traded = int(daily.shape[0])

    # Profit factor
    gross_win  = sum(p for p in pnl_list if p > 0)
    gross_loss = -sum(p for p in pnl_list if p < 0)
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    else:
        profit_factor = float("inf") if gross_win > 0 else float("nan")

    # Mejor trade + contexto (fill price)
    best_idx  = max(range(len(pnl_list)), key=lambda i: pnl_list[i])
    worst_idx = min(range(len(pnl_list)), key=lambda i: pnl_list[i])
    best_ts   = ts_list[best_idx]
    worst_ts  = ts_list[worst_idx]

    return {
        "candidates":             len(sig),
        "skipped_fill_high":      skipped_fill_high,
        "skipped_no_edge_post":   skipped_no_edge_post_costs,
        "trades":                 n,
        "wins":                   wins,
        "wr_pct":                 (100 * wins / n) if n else 0.0,
        "profit_usd":             bankroll - INITIAL_BANKROLL,
        "bankroll_final":         bankroll,
        "roi_pct":                100 * (bankroll - INITIAL_BANKROLL) / INITIAL_BANKROLL,
        "best_trade":             pnl_list[best_idx],
        "worst_trade":            pnl_list[worst_idx],
        "best_trade_ts":          best_ts,
        "worst_trade_ts":         worst_ts,
        "dd_max_usd":             max_dd_usd,
        "dd_max_pct":             max_dd_pct,
        "dd_peak_bankroll":       peak_at_max,
        "dd_valley_bankroll":     valley_at_max,
        "dd_peak_ts":             peak_ts,
        "dd_valley_ts":           valley_ts,
        "volatility_usd":         vol,
        "daily_best_usd":         daily_best_val,
        "daily_worst_usd":        daily_worst_val,
        "daily_best_date":        daily_best_date,
        "daily_worst_date":       daily_worst_date,
        "days_positive":          days_positive,
        "days_negative":          days_negative,
        "days_flat":              days_flat,
        "total_days_traded":      total_days_traded,
        "profit_factor":          profit_factor,
        "gross_win_usd":          gross_win,
        "gross_loss_usd":         gross_loss,
        "game_over_at":           game_over_at,
    }


def fmt_bot(label: str, desc: str, r: dict) -> None:
    print(f"  {label}")
    print(f"    {desc}")
    print(f"    Candidatos (post filtros)    : {r['candidates']:>6}")
    print(f"    Trades ejecutados            : {r['trades']:>6}")
    print(f"    Ganadores                    : {r['wins']:>6} ({r['wr_pct']:.1f}%)")
    print(f"    Profit neto del mes          : ${r['profit_usd']:>+10,.2f}")
    print(f"    Bankroll final               : ${r['bankroll_final']:>+10,.2f}")
    print(f"    ROI mensual                  : {r['roi_pct']:>+7.2f}%")
    print(f"    --- Riesgo ---")
    print(f"    Drawdown maximo              : ${r['dd_max_usd']:>+10,.2f}  ({r['dd_max_pct']:>+6.2f}%)")
    print(f"      pico   ${r['dd_peak_bankroll']:.2f} @ {r['dd_peak_ts']}")
    print(f"      valle  ${r['dd_valley_bankroll']:.2f} @ {r['dd_valley_ts']}")
    print(f"    Volatilidad (std PnL/trade)  : ${r['volatility_usd']:>10,.2f}")
    print(f"    --- Trades extremos ---")
    print(f"    Peor trade                   : ${r['worst_trade']:>+10,.2f}  @ {r['worst_trade_ts']}")
    print(f"    Mejor trade                  : ${r['best_trade']:>+10,.2f}  @ {r['best_trade_ts']}")
    print(f"    --- Dias ---")
    print(f"    Dias operados                : {r['total_days_traded']:>6}")
    print(f"    Dias positivos               : {r['days_positive']:>6}")
    print(f"    Dias negativos               : {r['days_negative']:>6}")
    print(f"    Dias flat                    : {r['days_flat']:>6}")
    print(f"    Mejor dia                    : ${r['daily_best_usd']:>+10,.2f}  ({r['daily_best_date']})")
    print(f"    Peor dia                     : ${r['daily_worst_usd']:>+10,.2f}  ({r['daily_worst_date']})")
    print(f"    --- Profit factor ---")
    pf = r['profit_factor']
    pf_str = "inf" if pf == float("inf") else (f"{pf:.2f}" if not (isinstance(pf, float) and math.isnan(pf)) else "n/a")
    print(f"    Profit factor                : {pf_str:>6}  (ganado ${r['gross_win_usd']:.2f} / perdido ${r['gross_loss_usd']:.2f})")
    if r["game_over_at"] is not None:
        print(f"    *** GAME OVER en {r['game_over_at']} (bankroll < ${BANKROLL_FLOOR}) ***")
    print()


def main():
    print("=" * 88)
    print(f"BACKTEST DETALLADO MAYO 2026 — {START_TS.date()} a {(END_TS - pd.Timedelta(days=1)).date()}")
    print(f"Bankroll inicial: ${INITIAL_BANKROLL}  |  Stake fijo: ${FIXED_STAKE_USD}/trade")
    print(f"Costos: half-spread {HALF_SPREAD*100}c + flat {FLAT_FEE*100}c + {FEE_RATE*100:.0f}% prop")
    print("=" * 88)
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
        r = simulate_detailed(s)
        fmt_bot(cfg.name, cfg.description, r)
        results.append({"bot": cfg.name, **r})
    # V4A, V4B, V4C usan v4_real
    for cfg in (V4A, V4B, V4C):
        s = apply_filters(v4, cfg)
        r = simulate_detailed(s)
        fmt_bot(cfg.name, cfg.description, r)
        results.append({"bot": cfg.name, **r})

    # ---- TABLA COMPLETA ----
    print("=" * 88)
    print("TABLA COMPLETA — todas las metricas")
    print("=" * 88)
    cols = [
        ("Bot",          "{:<32}", lambda r: r["bot"]),
        ("Trades",       "{:>7}",  lambda r: r["trades"]),
        ("WR%",          "{:>6.1f}", lambda r: r["wr_pct"]),
        ("Profit$",      "{:>+9.2f}", lambda r: r["profit_usd"]),
        ("Bank$",        "{:>8.2f}", lambda r: r["bankroll_final"]),
        ("DDmax$",       "{:>+8.2f}", lambda r: r["dd_max_usd"]),
        ("DDmax%",       "{:>+7.2f}", lambda r: r["dd_max_pct"]),
        ("Worst$",       "{:>+8.2f}", lambda r: r["worst_trade"]),
        ("Best$",        "{:>+9.2f}", lambda r: r["best_trade"]),
        ("D+",           "{:>3}", lambda r: r["days_positive"]),
        ("D-",           "{:>3}", lambda r: r["days_negative"]),
        ("PF",           "{:>5}", lambda r: ("inf" if r["profit_factor"]==float("inf")
                                              else f"{r['profit_factor']:.2f}")),
        ("WorstDay$",    "{:>+10.2f}", lambda r: r["daily_worst_usd"]),
        ("BestDay$",     "{:>+10.2f}", lambda r: r["daily_best_usd"]),
    ]
    header_parts = [fmt.replace(":>", ":>").replace(":<", ":<").format(name)
                    if False else f"{name:>{len(fmt.format(0)) if name != 'Bot' else 32}}"
                    for name, fmt, _ in cols]
    # simpler header build
    header = (f"{'Bot':<32}{'Trades':>8}{'WR%':>7}{'Profit$':>10}{'Bank$':>9}"
              f"{'DDmax$':>9}{'DDmax%':>8}{'Worst$':>9}{'Best$':>10}"
              f"{'D+':>4}{'D-':>4}{'PF':>6}{'WorstDay$':>11}{'BestDay$':>11}")
    print(header)
    print("-" * len(header))
    for r in results:
        pf = r['profit_factor']
        pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(
            f"{r['bot']:<32}"
            f"{r['trades']:>8}"
            f"{r['wr_pct']:>7.1f}"
            f"{r['profit_usd']:>+10.2f}"
            f"{r['bankroll_final']:>9.2f}"
            f"{r['dd_max_usd']:>+9.2f}"
            f"{r['dd_max_pct']:>+8.2f}"
            f"{r['worst_trade']:>+9.2f}"
            f"{r['best_trade']:>+10.2f}"
            f"{r['days_positive']:>4}"
            f"{r['days_negative']:>4}"
            f"{pf_str:>6}"
            f"{r['daily_worst_usd']:>+11.2f}"
            f"{r['daily_best_usd']:>+11.2f}"
        )
    print()

    # ---- RANKING POR ESTABILIDAD (menor DD primero) ----
    print("=" * 88)
    print("RANKING POR ESTABILIDAD — drawdown $ menos negativo primero (mas estable arriba)")
    print("=" * 88)
    ranked = sorted(results, key=lambda r: r["dd_max_usd"], reverse=True)  # menos negativo primero
    print(f"{'#':<3}{'Bot':<32}{'DDmax$':>10}{'DDmax%':>9}{'Profit$':>10}{'PF':>7}{'D+/D-':>9}")
    print("-" * 80)
    for i, r in enumerate(ranked, 1):
        pf = r['profit_factor']
        pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(
            f"{i:<3}{r['bot']:<32}"
            f"{r['dd_max_usd']:>+10.2f}"
            f"{r['dd_max_pct']:>+9.2f}"
            f"{r['profit_usd']:>+10.2f}"
            f"{pf_str:>7}"
            f"{r['days_positive']:>4}/{r['days_negative']:<3}"
        )
    print()

    # ---- CSV ----
    out = "data/poly_backtest_year/may_2026_detailed.csv"
    # Convertir timestamps a string para CSV
    rows = []
    for r in results:
        row = dict(r)
        for k in ("best_trade_ts","worst_trade_ts","dd_peak_ts","dd_valley_ts",
                  "daily_best_date","daily_worst_date","game_over_at"):
            if row.get(k) is not None:
                row[k] = str(row[k])
        rows.append(row)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"CSV guardado: {out}")


if __name__ == "__main__":
    main()
