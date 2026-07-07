"""London / Asian range breakout — estrategia alternativa para eval prop firm."""
from __future__ import annotations

import time as time_lib
from dataclasses import dataclass
from typing import Any

import pandas as pd

from webapp.backend.engine.fondeo_engine import (
    FondeoConfig,
    _day_key,
    _hhmm,
    _in_session,
    _position_size,
)
from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade


@dataclass
class LondonBreakoutConfig:
    asian_start: int = 0      # HHMM broker — rango asiático
    asian_end: int = 700
    trade_start: int = 700      # ventana operativa
    trade_end: int = 1100
    risk_pct: float = 2.1
    tp_range_mult: float = 1.5  # TP = mult × rango asiático
    max_trades_per_day: int = 2
    initial_balance: float = 5000.0
    mm_risk_pct: float = 2.1
    broker_utc_offset_hours: int = 7
    mode: str = "breakout"      # breakout | fade (sweep reversal)
    equity_sample_bars: int = 12

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def run_london_breakout(
    bars: pd.DataFrame,
    cfg: LondonBreakoutConfig,
    symbol: str = "EURUSD",
) -> BacktestResult:
    t0 = time_lib.time()
    if bars is None or bars.empty:
        return _empty(cfg, symbol, t0)

    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    offset = cfg.broker_utc_offset_hours
    initial = float(cfg.initial_balance)
    risk_frac = cfg.risk_pct / 100.0

    balance = initial
    trades: list[Trade] = []
    equity: list[EquityPoint] = []
    position: dict[str, Any] | None = None

    day_key = -1
    trades_today = 0
    asian_high = asian_low = 0.0
    asian_ready = False

    def snap(ts: pd.Timestamp) -> None:
        equity.append(
            EquityPoint(ts.isoformat(), round(balance, 2), round(balance - initial, 2), len(trades))
        )

    def close_pos(exit_p: float, ts: pd.Timestamp, reason: str) -> None:
        nonlocal balance, position
        if position is None:
            return
        d, entry, notional = position["direction"], position["entry"], position["notional"]
        pnl = notional * (exit_p - entry) / entry if d == "long" else notional * (entry - exit_p) / entry
        balance += pnl
        trades.append(
            Trade(
                timestamp=ts.isoformat(),
                asset=symbol,
                direction=d,
                entry_price=round(entry, 5),
                exit_price=round(exit_p, 5),
                stake_usd=round(notional, 2),
                cost_paid=round(notional, 2),
                pnl=round(pnl, 2),
                is_winner=pnl > 0,
                bankroll_after=round(balance, 2),
                extra={"reason": reason},
            )
        )
        position = None
        snap(ts)

    for row in df.itertuples(index=False):
        ts, o, h, l, c = row.timestamp, float(row.open), float(row.high), float(row.low), float(row.close)
        dk = _day_key(ts, offset)
        hh = _hhmm(ts, offset)

        if dk != day_key:
            day_key = dk
            trades_today = 0
            asian_high = h
            asian_low = l
            asian_ready = False

        if cfg.asian_start <= hh <= cfg.asian_end:
            asian_high = max(asian_high, h)
            asian_low = min(asian_low, l)
        elif hh > cfg.asian_end and not asian_ready and asian_high > asian_low:
            asian_ready = True

        if position is not None:
            sl, tp = position["sl"], position["tp"]
            d = position["direction"]
            if d == "long":
                if l <= sl:
                    close_pos(sl, ts, "sl")
                elif h >= tp:
                    close_pos(tp, ts, "tp")
            else:
                if h >= sl:
                    close_pos(sl, ts, "sl")
                elif l <= tp:
                    close_pos(tp, ts, "tp")
            if position and not _in_session(ts, cfg.trade_start, cfg.trade_end, offset):
                close_pos(c, ts, "session")

        if (
            asian_ready
            and _in_session(ts, cfg.trade_start, cfg.trade_end, offset)
            and trades_today < cfg.max_trades_per_day
            and position is None
            and asian_high > asian_low
        ):
            rng = asian_high - asian_low
            if cfg.mode == "breakout":
                if c > asian_high:
                    sl = asian_low
                    tp = c + rng * cfg.tp_range_mult
                    entry = c
                    notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                    if notional > 0 and entry > sl:
                        position = {"direction": "long", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                        trades_today += 1
                elif c < asian_low:
                    sl = asian_high
                    tp = c - rng * cfg.tp_range_mult
                    entry = c
                    notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                    if notional > 0 and sl > entry:
                        position = {"direction": "short", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                        trades_today += 1
            else:  # fade: sweep asian high/low then close back inside
                if h > asian_high and c < asian_high:
                    sl = h
                    tp = c - rng * cfg.tp_range_mult
                    entry = c
                    notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                    if notional > 0 and sl > entry:
                        position = {"direction": "short", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                        trades_today += 1
                elif l < asian_low and c > asian_low:
                    sl = l
                    tp = c + rng * cfg.tp_range_mult
                    entry = c
                    notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                    if notional > 0 and entry > sl:
                        position = {"direction": "long", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                        trades_today += 1

    if position is not None:
        close_pos(float(df.iloc[-1]["close"]), df.iloc[-1]["timestamp"], "eod")

    metrics = compute_metrics(trades, equity, initial)
    return BacktestResult(
        strategy_id="london.breakout",
        strategy_name="London Asian Breakout",
        market_type="forex",
        period_start=df["timestamp"].iloc[0].isoformat(),
        period_end=df["timestamp"].iloc[-1].isoformat(),
        initial_bankroll=initial,
        final_bankroll=round(balance, 2),
        total_pnl=round(balance - initial, 2),
        total_pnl_pct=round((balance - initial) / initial * 100, 2),
        trades=trades,
        equity_curve=equity,
        metrics=metrics,
        config_used=cfg.to_dict(),
        duration_seconds=round(time_lib.time() - t0, 4),
    )


def _empty(cfg: LondonBreakoutConfig, symbol: str, t0: float) -> BacktestResult:
    return BacktestResult(
        strategy_id="london.breakout",
        strategy_name="London Asian Breakout",
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
