"""ICT London Open — Judas Swing (Asian range sweep + fade).

Lo que recomienda internet para prop firms:
- Marcar rango asiático (ARH/ARL)
- En apertura Londres: esperar sweep de liquidez (Judas)
- Entrar en contra cuando el cierre vuelve dentro del rango
- SL detrás del extremo del sweep; TP en el lado opuesto del rango asiático
"""
from __future__ import annotations

import time as time_lib
from dataclasses import dataclass
from typing import Any

import pandas as pd

from webapp.backend.engine.fondeo_engine import _day_key, _hhmm, _in_session, _position_size
from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade


@dataclass
class JudasConfig:
    asian_start: int = 0
    asian_end: int = 700
    kill_start: int = 700
    kill_end: int = 1000
    risk_pct: float = 2.1
    tp_mode: str = "asian_opposite"  # asian_opposite | range_mult
    tp_range_mult: float = 2.0
    sl_buffer_pips: float = 2.0
    min_asian_range_pips: float = 8.0
    max_trades_per_day: int = 1
    initial_balance: float = 5000.0
    mm_risk_pct: float = 2.1
    broker_utc_offset_hours: int = 7
    pip_size: float = 0.0001
    allow_long: bool = True
    allow_short: bool = True
    equity_sample_bars: int = 12

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def run_judas_swing(
    bars: pd.DataFrame,
    cfg: JudasConfig,
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
    slip = cfg.sl_buffer_pips * cfg.pip_size

    balance = initial
    trades: list[Trade] = []
    equity: list[EquityPoint] = []
    position: dict[str, Any] | None = None

    day_key = -1
    trades_today = 0
    asian_high = asian_low = 0.0
    asian_ready = False
    swept_high = swept_low = False
    bars_seen = 0
    sample = max(1, cfg.equity_sample_bars)

    def unrealized(mark: float) -> float:
        if position is None:
            return 0.0
        d, entry, notional = position["direction"], position["entry"], position["notional"]
        if d == "long":
            return notional * (mark - entry) / entry
        return notional * (entry - mark) / entry

    def equity_at(mark: float) -> float:
        return balance + unrealized(mark)

    def snap(ts: pd.Timestamp, mark: float) -> None:
        eq = equity_at(mark)
        equity.append(
            EquityPoint(ts.isoformat(), round(eq, 2), round(eq - initial, 2), len(trades))
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
                extra={"reason": reason, "strategy": "judas"},
            )
        )
        position = None
        snap(ts, exit_p)

    for row in df.itertuples(index=False):
        ts, h, l, c = row.timestamp, float(row.high), float(row.low), float(row.close)
        bars_seen += 1
        dk = _day_key(ts, offset)
        hh = _hhmm(ts, offset)

        if dk != day_key:
            day_key = dk
            trades_today = 0
            asian_high = h
            asian_low = l
            asian_ready = False
            swept_high = swept_low = False

        if cfg.asian_start <= hh <= cfg.asian_end:
            asian_high = max(asian_high, h)
            asian_low = min(asian_low, l)
        elif hh > cfg.asian_end and not asian_ready and asian_high > asian_low:
            rng_pips = (asian_high - asian_low) / cfg.pip_size
            asian_ready = rng_pips >= cfg.min_asian_range_pips

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
            if position and hh > cfg.kill_end:
                close_pos(c, ts, "kill_end")

        if (
            asian_ready
            and _in_session(ts, cfg.kill_start, cfg.kill_end, offset)
            and trades_today < cfg.max_trades_per_day
            and position is None
        ):
            rng = asian_high - asian_low

            # Judas sweep high → short (fade)
            if cfg.allow_short and not swept_high and h > asian_high and c < asian_high:
                swept_high = True
                sl = h + slip
                if cfg.tp_mode == "asian_opposite":
                    tp = asian_low
                else:
                    tp = c - rng * cfg.tp_range_mult
                entry = c
                notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                if notional > 0 and sl > entry > tp:
                    position = {"direction": "short", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                    trades_today += 1

            # Judas sweep low → long (fade)
            elif cfg.allow_long and not swept_low and l < asian_low and c > asian_low:
                swept_low = True
                sl = l - slip
                if cfg.tp_mode == "asian_opposite":
                    tp = asian_high
                else:
                    tp = c + rng * cfg.tp_range_mult
                entry = c
                notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                if notional > 0 and tp > entry > sl:
                    position = {"direction": "long", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                    trades_today += 1

        if bars_seen % sample == 0:
            worst = l if position and position["direction"] == "long" else h
            mark = worst if position else c
            snap(ts, mark)

    if position is not None:
        close_pos(float(df.iloc[-1]["close"]), df.iloc[-1]["timestamp"], "eod")

    metrics = compute_metrics(trades, equity, initial)
    return BacktestResult(
        strategy_id="ict.judas",
        strategy_name="ICT Judas Swing",
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


def _empty(cfg: JudasConfig, symbol: str, t0: float) -> BacktestResult:
    return BacktestResult(
        strategy_id="ict.judas",
        strategy_name="ICT Judas Swing",
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
