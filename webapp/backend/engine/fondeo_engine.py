"""Backtest Fondeo EMA Cross — paridad con sqx/indicators/FondeoEMAcross.java."""
from __future__ import annotations

import time as time_lib
from dataclasses import dataclass
from typing import Any

import pandas as pd

from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade


@dataclass
class FondeoConfig:
    fast_period: int = 9
    slow_period: int = 20
    risk_pct: float = 2.1
    tp_ratio: float = 1.0
    sess_start: int = 800
    sess_end: int = 1000
    max_trades_per_day: int = 2
    initial_balance: float = 5000.0
    mm_risk_pct: float = 2.1
    slippage_pips: float = 2.0
    pip_size: float = 0.0001
    allow_short: bool = True
    allow_long: bool = True
    # Horas a sumar al timestamp UTC para hora broker (Dukascopy chart UTC+0; MT5 live a menudo +2)
    broker_utc_offset_hours: int = 0
    # 1 = cada barra; 6 = cada 30 min M5 (más rápido en grid search)
    equity_sample_bars: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "risk_pct": self.risk_pct,
            "tp_ratio": self.tp_ratio,
            "sess_start": self.sess_start,
            "sess_end": self.sess_end,
            "max_trades_per_day": self.max_trades_per_day,
            "initial_balance": self.initial_balance,
            "mm_risk_pct": self.mm_risk_pct,
            "slippage_pips": self.slippage_pips,
            "pip_size": self.pip_size,
            "allow_short": self.allow_short,
            "allow_long": self.allow_long,
            "broker_utc_offset_hours": self.broker_utc_offset_hours,
            "equity_sample_bars": self.equity_sample_bars,
        }


def _broker_ts(ts: pd.Timestamp, offset_hours: int) -> pd.Timestamp:
    if offset_hours:
        return ts + pd.Timedelta(hours=offset_hours)
    return ts


def _day_key(ts: pd.Timestamp, offset_hours: int = 0) -> int:
    loc = _broker_ts(ts, offset_hours)
    return loc.year * 10000 + loc.month * 100 + loc.day


def _hhmm(ts: pd.Timestamp, offset_hours: int = 0) -> int:
    loc = _broker_ts(ts, offset_hours)
    return loc.hour * 100 + loc.minute


def _in_session(ts: pd.Timestamp, sess_start: int, sess_end: int, offset_hours: int = 0) -> bool:
    h = _hhmm(ts, offset_hours)
    return sess_start <= h <= sess_end


def _position_size(balance: float, entry: float, sl: float, mm_risk_pct: float) -> float:
    """Notional en USD para arriesgar mm_risk_pct% si toca SL."""
    risk_amount = balance * (mm_risk_pct / 100.0)
    sl_dist = abs(entry - sl)
    if sl_dist <= 0 or entry <= 0:
        return 0.0
    return risk_amount * entry / sl_dist


def _apply_slippage(price: float, direction: str, side: str, slippage: float) -> float:
    """Slippage en contra del trader (pips). side: entry|exit."""
    slip = slippage
    if direction == "long":
        return price + slip if side == "entry" else price - slip
    return price - slip if side == "entry" else price + slip


def run_fondeo_backtest(
    bars: pd.DataFrame,
    cfg: FondeoConfig,
    symbol: str = "EURUSD",
    period_start: pd.Timestamp | None = None,
    period_end: pd.Timestamp | None = None,
) -> BacktestResult:
    t0 = time_lib.time()

    if bars is None or bars.empty:
        return _empty_result(cfg, symbol, t0)

    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    if period_start is not None:
        df = df[df["timestamp"] >= pd.to_datetime(period_start, utc=True)]
    if period_end is not None:
        df = df[df["timestamp"] <= pd.to_datetime(period_end, utc=True)]
    df = df.sort_values("timestamp").reset_index(drop=True)
    if df.empty:
        return _empty_result(cfg, symbol, t0)

    slip = cfg.slippage_pips * cfg.pip_size
    need = max(cfg.fast_period, cfg.slow_period) + 2

    ema_fast = float("nan")
    ema_slow = float("nan")
    prev_ema_fast = float("nan")
    prev_ema_slow = float("nan")
    bars_seen = 0

    day_key = -1
    trades_today = 0

    k_f = 2.0 / (cfg.fast_period + 1.0)
    k_s = 2.0 / (cfg.slow_period + 1.0)
    risk_frac = cfg.risk_pct / 100.0
    tp_frac = risk_frac * cfg.tp_ratio

    balance = float(cfg.initial_balance)
    peak = balance
    trades: list[Trade] = []
    equity: list[EquityPoint] = []

    position: dict[str, Any] | None = None

    def snapshot(ts: pd.Timestamp) -> None:
        nonlocal peak
        peak = max(peak, balance)
        equity.append(
            EquityPoint(
                timestamp=ts.isoformat(),
                bankroll=round(balance, 2),
                pnl_cumulative=round(balance - cfg.initial_balance, 2),
                trades_to_date=len(trades),
            )
        )

    offset = cfg.broker_utc_offset_hours
    sample = max(1, cfg.equity_sample_bars)

    def close_position(exit_price: float, ts: pd.Timestamp, reason: str) -> None:
        nonlocal balance, position
        if position is None:
            return
        direction = position["direction"]
        entry = position["entry"]
        notional = position["notional"]
        if direction == "long":
            pnl = notional * (exit_price - entry) / entry
        else:
            pnl = notional * (entry - exit_price) / entry
        balance += pnl
        trades.append(
            Trade(
                timestamp=ts.isoformat(),
                asset=symbol,
                direction=direction,
                entry_price=round(entry, 5),
                exit_price=round(exit_price, 5),
                stake_usd=round(notional, 2),
                cost_paid=round(notional, 2),
                pnl=round(pnl, 2),
                is_winner=pnl > 0,
                bankroll_after=round(balance, 2),
                extra={
                    "reason": reason,
                    "sl": position["sl"],
                    "tp": position["tp"],
                    "session_hhmm": _hhmm(ts, offset),
                },
            )
        )
        position = None
        snapshot(ts)

    for row in df.itertuples(index=False):
        ts = row.timestamp
        o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)

        if position is not None:
            direction = position["direction"]
            sl, tp = position["sl"], position["tp"]
            if direction == "long":
                if l <= sl:
                    close_position(_apply_slippage(sl, "long", "exit", slip), ts, "sl")
                elif h >= tp:
                    close_position(_apply_slippage(tp, "long", "exit", slip), ts, "tp")
            else:
                if h >= sl:
                    close_position(_apply_slippage(sl, "short", "exit", slip), ts, "sl")
                elif l <= tp:
                    close_position(_apply_slippage(tp, "short", "exit", slip), ts, "tp")

        bars_seen += 1
        prev_ema_fast = ema_fast
        prev_ema_slow = ema_slow

        if pd.isna(ema_fast):
            ema_fast = c
            ema_slow = c
            if bars_seen % sample == 0:
                snapshot(ts)
            continue

        ema_fast = c * k_f + ema_fast * (1.0 - k_f)
        ema_slow = c * k_s + ema_slow * (1.0 - k_s)

        if pd.isna(prev_ema_fast):
            if bars_seen % sample == 0:
                snapshot(ts)
            continue

        dk = _day_key(ts, offset)
        if dk != day_key:
            day_key = dk
            trades_today = 0

        signal_long = False
        signal_short = False
        long_sl = long_tp = short_sl = short_tp = 0.0

        if bars_seen >= need and _in_session(ts, cfg.sess_start, cfg.sess_end, offset):
            if trades_today < cfg.max_trades_per_day and position is None:
                cross_up = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow
                cross_dn = prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow

                if cross_up and cfg.allow_long:
                    sl = c * (1.0 - risk_frac)
                    tp = c * (1.0 + tp_frac)
                    if sl > 0 and tp > c:
                        signal_long = True
                        long_sl, long_tp = sl, tp
                        trades_today += 1
                elif cross_dn and cfg.allow_short:
                    sl = c * (1.0 + risk_frac)
                    tp = c * (1.0 - tp_frac)
                    if tp > 0 and sl > c:
                        signal_short = True
                        short_sl, short_tp = sl, tp
                        trades_today += 1

        if signal_long:
            entry = _apply_slippage(c, "long", "entry", slip)
            notional = _position_size(balance, entry, long_sl, cfg.mm_risk_pct)
            if notional > 0:
                position = {
                    "direction": "long",
                    "entry": entry,
                    "sl": long_sl,
                    "tp": long_tp,
                    "notional": notional,
                }
        elif signal_short:
            entry = _apply_slippage(c, "short", "entry", slip)
            notional = _position_size(balance, entry, short_sl, cfg.mm_risk_pct)
            if notional > 0:
                position = {
                    "direction": "short",
                    "entry": entry,
                    "sl": short_sl,
                    "tp": short_tp,
                    "notional": notional,
                }

        if bars_seen % sample == 0:
            snapshot(ts)

    if position is not None:
        last = df.iloc[-1]
        ts = last["timestamp"]
        c = float(last["close"])
        direction = position["direction"]
        exit_p = _apply_slippage(c, direction, "exit", slip)
        close_position(exit_p, ts, "eod")

    metrics = compute_metrics(trades, equity, cfg.initial_balance)
    if metrics.get("profit_factor") == float("inf"):
        metrics["profit_factor"] = 999.0

    p_start = df["timestamp"].iloc[0].isoformat()
    p_end = df["timestamp"].iloc[-1].isoformat()

    return BacktestResult(
        strategy_id="fondeo.ema_cross",
        strategy_name="Fondeo EMA Cross",
        market_type="forex",
        period_start=p_start,
        period_end=p_end,
        initial_bankroll=cfg.initial_balance,
        final_bankroll=round(balance, 2),
        total_pnl=round(balance - cfg.initial_balance, 2),
        total_pnl_pct=round((balance - cfg.initial_balance) / cfg.initial_balance * 100, 2),
        trades=trades,
        equity_curve=equity,
        metrics=metrics,
        config_used=cfg.to_dict(),
        duration_seconds=round(time_lib.time() - t0, 4),
    )


def _empty_result(cfg: FondeoConfig, symbol: str, t0: float) -> BacktestResult:
    return BacktestResult(
        strategy_id="fondeo.ema_cross",
        strategy_name="Fondeo EMA Cross",
        market_type="forex",
        period_start="",
        period_end="",
        initial_bankroll=cfg.initial_balance,
        final_bankroll=cfg.initial_balance,
        total_pnl=0.0,
        total_pnl_pct=0.0,
        trades=[],
        equity_curve=[],
        metrics=compute_metrics([], [], cfg.initial_balance),
        config_used=cfg.to_dict(),
        duration_seconds=round(time_lib.time() - t0, 4),
    )
