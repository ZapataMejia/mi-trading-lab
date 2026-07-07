"""Engine de backtest para estrategias Polymarket.

Toma una PolymarketStrategy + un DataFrame de mercados pre-procesados y
simula la ejecucion con costos realistas, devolviendo BacktestResult.

Costos modelados:
  - half_spread (cruzas el spread al entrar) — default 1.5cents
  - flat_fee (gas/relayer en Polygon)         — default 0.5cents
  - fee_rate (taker proporcional)             — default 2%
"""
from __future__ import annotations

import time
from typing import Any

import pandas as pd

from strategies.base import PolymarketStrategy
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade
from webapp.backend.engine.metrics import compute_metrics


def _apply_polymarket_filters(df: pd.DataFrame, strategy: type[PolymarketStrategy]) -> pd.DataFrame:
    """Aplica los filtros declarativos de la estrategia al universo."""
    out = df.copy()
    out["edge_abs"] = out["signal_edge_up"].abs()
    if "hour" not in out.columns:
        out["hour"] = out["window_start"].dt.hour
    if "weekday" not in out.columns:
        out["weekday"] = out["window_start"].dt.day_name()
    if "asset" not in out.columns and "slug" in out.columns:
        out["asset"] = out["slug"].str.extract(r"^([a-z]+)")[0]

    out = out[out["edge_abs"] >= strategy.threshold]
    if strategy.asset_filter:
        out = out[out["asset"].isin([a.lower() for a in strategy.asset_filter])]
    if strategy.skip_hours_utc:
        out = out[~out["hour"].isin(strategy.skip_hours_utc)]
    if strategy.skip_weekdays:
        out = out[~out["weekday"].isin(strategy.skip_weekdays)]
    if strategy.only_weekdays:
        out = out[out["weekday"].isin(strategy.only_weekdays)]
    if strategy.min_volume_usd > 0 and "volume_usd" in out.columns:
        out = out[out["volume_usd"] >= strategy.min_volume_usd]

    return out.sort_values("window_start").reset_index(drop=True)


def run_polymarket_backtest(
    strategy: type[PolymarketStrategy],
    universe: pd.DataFrame,
    period_start: pd.Timestamp | None = None,
    period_end: pd.Timestamp | None = None,
) -> BacktestResult:
    """Corre el backtest de una estrategia Polymarket sobre `universe`.

    Args:
      strategy: clase Strategy (NO instancia).
      universe: DataFrame con columnas:
          window_start (UTC), asset, signal, signal_edge_up,
          p_poly_at_signal, p_fair_at_signal, outcome, [volume_usd]
      period_start/end: opcional, filtra el rango temporal.
    """
    t0 = time.time()
    df = universe.copy()
    df["window_start"] = pd.to_datetime(df["window_start"], utc=True)
    if period_start is not None:
        df = df[df["window_start"] >= period_start]
    if period_end is not None:
        df = df[df["window_start"] < period_end]
    df = df[df["signal"].notna() & df["outcome"].notna()].copy()

    candidate_markets = len(df)
    sig = _apply_polymarket_filters(df, strategy)

    bankroll = float(strategy.initial_bankroll)
    floor = float(strategy.bankroll_floor)
    stake = float(strategy.stake)
    half_spread = strategy.half_spread
    flat_fee = strategy.flat_fee
    fee_rate = strategy.fee_rate

    # Sizing config (replica el del bot real en src/polymarket/paper_trader.py).
    # Importante: max_position_usd simula el cap impuesto por la liquidez real
    # de los orderbooks de Polymarket 1h (típicamente $200-5k de depth).
    sizing_mode = getattr(strategy, "sizing_mode", "fixed")
    kelly_fraction = float(getattr(strategy, "kelly_fraction", 0.25))
    max_pct_per_trade = float(getattr(strategy, "max_pct_per_trade", 0.10))
    max_position_usd = float(getattr(strategy, "max_position_usd", 200.0))
    min_position_usd = float(getattr(strategy, "min_position_usd", 1.0))

    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []
    game_over_at: str | None = None
    skipped = 0
    pnl_cum = 0.0

    if not sig.empty:
        equity_curve.append(EquityPoint(
            timestamp=sig.iloc[0]["window_start"].isoformat(),
            bankroll=bankroll,
            pnl_cumulative=0.0,
            trades_to_date=0,
        ))

    for _, row in sig.iterrows():
        if bankroll < floor:
            if game_over_at is None:
                game_over_at = row["window_start"].isoformat()
            skipped += 1
            continue

        edge = row["signal_edge_up"]
        direction = "UP" if edge > 0 else "DOWN"
        p_poly = row["p_poly_at_signal"]
        p_fair = row["p_fair_at_signal"]

        # Fill = price + half-spread (cross the spread on entry)
        naive_fill = p_poly if direction == "UP" else (1.0 - p_poly)
        p_model = p_fair if direction == "UP" else (1.0 - p_fair)
        fill = min(1.0, naive_fill + half_spread)

        if fill >= 0.99:
            skipped += 1
            continue
        fill_total_inc_fee = fill * (1.0 + fee_rate)
        if p_model <= fill_total_inc_fee:
            skipped += 1
            continue

        # Sizing — replica el bot real (src/polymarket/paper_trader.py L538-553)
        # + cap absoluto USD para simular la liquidez real del orderbook.
        if sizing_mode == "kelly":
            # Kelly para una apuesta binaria: f* = (p_model - fill_total) / (1 - fill_total)
            # Donde fill_total = fill * (1 + fee_rate). Asumimos flat_fee despreciable.
            edge_after = p_model - fill_total_inc_fee
            f_kelly = edge_after / max(1e-6, 1.0 - fill_total_inc_fee)
            f = max(0.0, min(f_kelly * kelly_fraction, max_pct_per_trade))
            position_usd = bankroll * f
        else:
            position_usd = stake

        # Caps: max absoluto (liquidez), 95% del bankroll, y mínimo del orderbook
        position_usd = min(position_usd, max_position_usd, bankroll * 0.95)
        if position_usd < min_position_usd:
            skipped += 1
            continue

        contracts = position_usd / fill
        prop_fee = contracts * fill * fee_rate
        cost_paid = contracts * fill + prop_fee + flat_fee
        if cost_paid > bankroll:
            skipped += 1
            continue

        # Resolution
        outcome_correct = (row["outcome"] == direction)
        payoff = contracts if outcome_correct else 0.0
        pnl = payoff - cost_paid

        bankroll += pnl
        pnl_cum += pnl

        trades.append(Trade(
            timestamp=row["window_start"].isoformat(),
            asset=str(row.get("asset", "unknown")),
            direction=direction,
            entry_price=round(fill, 4),
            exit_price=1.0 if outcome_correct else 0.0,
            stake_usd=round(position_usd, 2),
            cost_paid=round(cost_paid, 4),
            pnl=round(pnl, 4),
            is_winner=outcome_correct,
            bankroll_after=round(bankroll, 4),
            extra={
                "edge_signed": float(edge),
                "p_poly": float(p_poly),
                "p_fair": float(p_fair),
                "volume_usd": float(row.get("volume_usd", 0) or 0),
            },
        ))
        equity_curve.append(EquityPoint(
            timestamp=row["window_start"].isoformat(),
            bankroll=round(bankroll, 4),
            pnl_cumulative=round(pnl_cum, 4),
            trades_to_date=len(trades),
        ))

    metrics = compute_metrics(trades, equity_curve, strategy.initial_bankroll)

    # Periodo efectivo
    if not df.empty:
        ps = df["window_start"].min().isoformat()
        pe = df["window_start"].max().isoformat()
    else:
        ps = (period_start.isoformat() if period_start is not None else "")
        pe = (period_end.isoformat() if period_end is not None else "")

    final_bk = bankroll
    total_pnl = final_bk - strategy.initial_bankroll
    # ROI sobre el CAPITAL DESPLEGADO (sum de stakes), no sobre el initial bankroll.
    # Para estrategias con stake fijo y bankroll chico esto da una medida realista,
    # en vez del % monstruoso de "30,000%+ sobre $100".
    total_stake_deployed = sum(t.stake_usd for t in trades)
    if total_stake_deployed > 0:
        total_pnl_pct = total_pnl / total_stake_deployed * 100
    else:
        total_pnl_pct = (total_pnl / strategy.initial_bankroll * 100) if strategy.initial_bankroll else 0.0

    return BacktestResult(
        strategy_id=strategy.strategy_id(),
        strategy_name=strategy.name,
        market_type=strategy.market_type,
        period_start=ps,
        period_end=pe,
        initial_bankroll=strategy.initial_bankroll,
        final_bankroll=round(final_bk, 4),
        total_pnl=round(total_pnl, 4),
        total_pnl_pct=round(total_pnl_pct, 2),
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
        game_over_at=game_over_at,
        skipped_markets=skipped,
        candidate_markets=candidate_markets,
        config_used=strategy.config_dict(),
        duration_seconds=round(time.time() - t0, 3),
    )
