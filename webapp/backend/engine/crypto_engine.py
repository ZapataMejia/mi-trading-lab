"""Engine de backtest para crypto strategies (perpetuos / spot).

Diseno
======
- Itera bar por bar el OHLCV recibido (de CryptoDataAdapter o de un CSV).
- En cada bar:
    1. Mete el bar en `state["history"]` (deque).
    2. Calcula equity mark-to-market y aplica el bankroll_floor (game over).
    3. Llama `strat_inst.on_bar(bar, state)` para que la strategy decida.
    4. Procesa la Order devuelta (open / close / reverse).
    5. Snapshotea equity_curve.

Convencion de fills
-------------------
- on_bar() corre al CIERRE del bar; la Order generada se ejecuta a `bar.close`
  con slippage aplicado siempre EN CONTRA del trader:
      long entry  -> close * (1 + slip)
      short entry -> close * (1 - slip)
      close long  -> close * (1 - slip)
      close short -> close * (1 + slip)
- Fee taker en notional al entrar Y al cerrar (`fee_rate` * notional).

Leverage
--------
- Soporte hasta 10x (clamp). Notional = margin (size_usd) * leverage.
- PnL escala con notional. Margin no se "lockea" explicitamente; en su lugar
  el cash representa la equity sin contar la apertura de posicion (modelo
  simplificado pero suficiente para backtests).
"""
from __future__ import annotations

import logging
import time as time_lib
from collections import deque
from typing import Any

import pandas as pd

from strategies.base import Bar, CryptoStrategy, Order
from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade

logger = logging.getLogger("webapp.engine.crypto")


def _empty_result(strategy: type[CryptoStrategy], t0: float) -> BacktestResult:
    return BacktestResult(
        strategy_id=strategy.strategy_id(),
        strategy_name=strategy.name,
        market_type=strategy.market_type,
        period_start="",
        period_end="",
        initial_bankroll=float(strategy.initial_bankroll),
        final_bankroll=float(strategy.initial_bankroll),
        total_pnl=0.0,
        total_pnl_pct=0.0,
        metrics=compute_metrics([], [], strategy.initial_bankroll),
        config_used=strategy.config_dict(),
        duration_seconds=round(time_lib.time() - t0, 4),
    )


def _bar_from_row(row) -> Bar:
    ts = row.timestamp
    if not isinstance(ts, pd.Timestamp):
        ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return Bar(
        timestamp=int(ts.timestamp()),
        open=float(row.open),
        high=float(row.high),
        low=float(row.low),
        close=float(row.close),
        volume=float(row.volume),
    )


def run_crypto_backtest(
    strategy: type[CryptoStrategy],
    klines: pd.DataFrame,
    period_start: pd.Timestamp | None = None,
    period_end: pd.Timestamp | None = None,
) -> BacktestResult:
    """Corre el backtest de una crypto strategy sobre `klines`.

    Args:
        strategy:     Subclase de CryptoStrategy (NO instancia).
        klines:       DataFrame con columnas timestamp/open/high/low/close/volume.
        period_start: filtro temporal opcional.
        period_end:   filtro temporal opcional.
    """
    t0 = time_lib.time()

    if klines is None or klines.empty:
        return _empty_result(strategy, t0)

    df = klines.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    if period_start is not None:
        df = df[df["timestamp"] >= pd.to_datetime(period_start, utc=True)]
    if period_end is not None:
        df = df[df["timestamp"] <= pd.to_datetime(period_end, utc=True)]
    df = df.sort_values("timestamp").reset_index(drop=True)
    if df.empty:
        return _empty_result(strategy, t0)

    # Strategy instance (on_bar puede usar self.X)
    strat_inst = strategy()

    declared_lookback = int(getattr(strategy, "lookback", 0) or 0)
    history_max = max(declared_lookback + 5, 300)  # piso para EMA200 y similares

    state: dict[str, Any] = {
        "position": None,
        "cash": float(strategy.initial_bankroll),
        "history": deque(maxlen=history_max),
        "peak_bankroll": float(strategy.initial_bankroll),
    }

    fee_rate = float(getattr(strategy, "fee_rate", 0.0006))
    slippage = float(getattr(strategy, "slippage_bps", 5.0)) / 10_000.0
    floor = float(strategy.bankroll_floor)
    initial_bk = float(strategy.initial_bankroll)
    default_stake = float(strategy.stake)

    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = [EquityPoint(
        timestamp=df.iloc[0]["timestamp"].isoformat(),
        bankroll=round(initial_bk, 6),
        pnl_cumulative=0.0,
        trades_to_date=0,
    )]
    pnl_cum = 0.0
    game_over_at: str | None = None
    skipped = 0
    asset = strategy.symbol.lower()

    # ------------------------------------------------------------------
    # Helpers de PnL/posicion
    # ------------------------------------------------------------------
    def _open_position(side: str, size_usd: float, leverage: float, price: float, ts_iso: str) -> None:
        """Abre nueva posicion. Asume que no hay otra abierta (caller debe cerrar primero)."""
        margin_req = size_usd if size_usd > 0 else default_stake
        margin = max(0.0, min(margin_req, state["cash"] * 0.95))
        if margin <= 0:
            return
        leverage = max(1.0, min(10.0, float(leverage or 1.0)))
        if side == "long":
            entry = price * (1 + slippage)
        else:
            entry = price * (1 - slippage)
        notional = margin * leverage
        entry_fee = notional * fee_rate
        state["cash"] -= entry_fee
        state["position"] = {
            "side": side,
            "entry": entry,
            "margin": margin,
            "leverage": leverage,
            "notional": notional,
            "entry_ts": ts_iso,
            "entry_fee": entry_fee,
        }

    def _close_position(price: float, ts_iso: str) -> float:
        """Cierra la posicion abierta. Devuelve trade_pnl (NETO de fees)."""
        pos = state["position"]
        if not pos:
            return 0.0
        if pos["side"] == "long":
            exit_p = price * (1 - slippage)
            pct = (exit_p - pos["entry"]) / pos["entry"]
        else:
            exit_p = price * (1 + slippage)
            pct = (pos["entry"] - exit_p) / pos["entry"]
        gross = pos["notional"] * pct
        exit_fee = pos["notional"] * fee_rate
        # cashflow on close: ya descontamos entry_fee al abrir, asi que aca
        # solo aplicamos pnl bruto y fee de salida.
        state["cash"] += gross - exit_fee
        bankroll_after = state["cash"]
        trade_pnl = gross - exit_fee - pos["entry_fee"]
        trades.append(Trade(
            timestamp=pos["entry_ts"],
            asset=asset,
            direction=pos["side"],
            entry_price=round(pos["entry"], 6),
            exit_price=round(exit_p, 6),
            stake_usd=round(pos["margin"], 4),
            cost_paid=round(pos["entry_fee"] + exit_fee, 6),
            pnl=round(trade_pnl, 6),
            is_winner=(trade_pnl > 0),
            bankroll_after=round(bankroll_after, 6),
            extra={
                "leverage": pos["leverage"],
                "notional": round(pos["notional"], 4),
                "exit_timestamp": ts_iso,
                "pct_change": round(pct, 6),
            },
        ))
        state["position"] = None
        return trade_pnl

    def _equity_now(close_price: float) -> float:
        equity = state["cash"]
        pos = state["position"]
        if pos is not None:
            if pos["side"] == "long":
                pct = (close_price - pos["entry"]) / pos["entry"]
            else:
                pct = (pos["entry"] - close_price) / pos["entry"]
            equity += pos["notional"] * pct
        return equity

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------
    for row in df.itertuples(index=False):
        bar = _bar_from_row(row)
        ts_iso = row.timestamp.isoformat() if hasattr(row.timestamp, "isoformat") \
            else pd.Timestamp(row.timestamp).isoformat()

        # Append history ANTES del step para que la barra actual sea visible.
        state["history"].append(bar)

        # Game over: si despues de mark-to-market quedamos por debajo del floor,
        # cerramos posicion forzadamente y dejamos de operar.
        equity_mtm = _equity_now(bar.close)
        if equity_mtm < floor and game_over_at is None:
            if state["position"]:
                pnl_cum += _close_position(bar.close, ts_iso)
            game_over_at = ts_iso
            equity_curve.append(EquityPoint(
                timestamp=ts_iso,
                bankroll=round(state["cash"], 6),
                pnl_cumulative=round(pnl_cum, 6),
                trades_to_date=len(trades),
            ))
            continue
        if game_over_at:
            equity_curve.append(EquityPoint(
                timestamp=ts_iso,
                bankroll=round(state["cash"], 6),
                pnl_cumulative=round(pnl_cum, 6),
                trades_to_date=len(trades),
            ))
            skipped += 1
            continue

        # Step de la strategy
        try:
            order: Order | None = strat_inst.on_bar(bar, state)
        except Exception as exc:
            logger.warning("on_bar() lanzo excepcion en %s: %s", ts_iso, exc)
            order = None

        if order is not None:
            side = order.side
            if side == "close":
                if state["position"]:
                    pnl_cum += _close_position(bar.close, ts_iso)
            elif side in ("long", "short"):
                pos = state["position"]
                if pos is None:
                    _open_position(side, order.size_usd, order.leverage, bar.close, ts_iso)
                elif pos["side"] != side:
                    # Reversal: cerrar y abrir opuesto en el mismo bar
                    pnl_cum += _close_position(bar.close, ts_iso)
                    _open_position(side, order.size_usd, order.leverage, bar.close, ts_iso)
                # Same side: ignoramos (no hacemos pyramiding por simplicidad)

        equity_after = _equity_now(bar.close)
        if equity_after > state["peak_bankroll"]:
            state["peak_bankroll"] = equity_after
        equity_curve.append(EquityPoint(
            timestamp=ts_iso,
            bankroll=round(equity_after, 6),
            pnl_cumulative=round(pnl_cum, 6),
            trades_to_date=len(trades),
        ))

    # Cerrar posicion abierta al final (mark-to-close)
    if state["position"]:
        last_close = float(df.iloc[-1]["close"])
        last_ts = df.iloc[-1]["timestamp"].isoformat()
        pnl_cum += _close_position(last_close, last_ts)
        # actualizar el ultimo punto de la equity curve con cash post-cierre
        equity_curve[-1] = EquityPoint(
            timestamp=last_ts,
            bankroll=round(state["cash"], 6),
            pnl_cumulative=round(pnl_cum, 6),
            trades_to_date=len(trades),
        )

    final_bk = state["cash"]
    total_pnl = final_bk - initial_bk
    total_pnl_pct = (total_pnl / initial_bk) * 100.0 if initial_bk > 0 else 0.0
    metrics = compute_metrics(trades, equity_curve, initial_bk)

    return BacktestResult(
        strategy_id=strategy.strategy_id(),
        strategy_name=strategy.name,
        market_type=strategy.market_type,
        period_start=df.iloc[0]["timestamp"].isoformat(),
        period_end=df.iloc[-1]["timestamp"].isoformat(),
        initial_bankroll=round(initial_bk, 6),
        final_bankroll=round(final_bk, 6),
        total_pnl=round(total_pnl, 6),
        total_pnl_pct=round(total_pnl_pct, 4),
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
        game_over_at=game_over_at,
        skipped_markets=skipped,
        candidate_markets=len(df),
        config_used=strategy.config_dict(),
        duration_seconds=round(time_lib.time() - t0, 4),
    )
