"""ICT Silver Bullet simplificado — sweep + displacement + FVG retest (M5).

Ventana fija (NY AM ~10-11 ET), sweep previo, displacement crea FVG, entrada en retest.
Referencia: consenso ICT prop firms — 1:2 RR mínimo, 0.5-1% riesgo.
"""
from __future__ import annotations

import time as time_lib
from dataclasses import dataclass
from typing import Any

import pandas as pd

from webapp.backend.engine.fondeo_engine import _day_key, _in_session, _position_size
from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade


@dataclass
class SilverBulletConfig:
    window_start: int = 1500
    window_end: int = 1600
    pre_lookback: int = 24
    min_displacement_pips: float = 4.0
    fvg_min_pips: float = 1.5
    risk_pct: float = 1.0
    tp_ratio: float = 2.0
    sl_buffer_pips: float = 2.0
    max_trades_per_day: int = 1
    initial_balance: float = 5000.0
    mm_risk_pct: float = 1.0
    broker_utc_offset_hours: int = 7
    pip_size: float = 0.0001
    allow_long: bool = True
    allow_short: bool = True
    equity_sample_bars: int = 12

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def run_silver_bullet(
    bars: pd.DataFrame,
    cfg: SilverBulletConfig,
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
    min_disp = cfg.min_displacement_pips * cfg.pip_size
    min_fvg = cfg.fvg_min_pips * cfg.pip_size

    balance = initial
    trades: list[Trade] = []
    equity: list[EquityPoint] = []
    position: dict[str, Any] | None = None
    day_key = -1
    trades_today = 0
    bars_seen = 0
    sample = max(1, cfg.equity_sample_bars)

    pre_h: list[float] = []
    pre_l: list[float] = []
    swept_high = swept_low = False
    pending_fvg: dict[str, Any] | None = None

    def unrealized(mark: float) -> float:
        if position is None:
            return 0.0
        d, entry, notional = position["direction"], position["entry"], position["notional"]
        if d == "long":
            return notional * (mark - entry) / entry
        return notional * (entry - mark) / entry

    def snap(ts: pd.Timestamp, mark: float) -> None:
        eq = balance + unrealized(mark)
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
                extra={"reason": reason, "strategy": "silver_bullet"},
            )
        )
        position = None
        snap(ts, exit_p)

    for row in df.itertuples(index=False):
        ts, o, h, l, c = row.timestamp, float(row.open), float(row.high), float(row.low), float(row.close)
        bars_seen += 1
        dk = _day_key(ts, offset)
        in_win = _in_session(ts, cfg.window_start, cfg.window_end, offset)

        if dk != day_key:
            day_key = dk
            trades_today = 0
            swept_high = swept_low = False
            pending_fvg = None
            pre_h.clear()
            pre_l.clear()

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
            if position and not in_win:
                close_pos(c, ts, "session")

        if not in_win:
            pre_h.append(h)
            pre_l.append(l)
            if len(pre_h) > cfg.pre_lookback:
                pre_h.pop(0)
                pre_l.pop(0)
            if bars_seen % sample == 0:
                snap(ts, c)
            continue

        swing_h = max(pre_h) if pre_h else h
        swing_l = min(pre_l) if pre_l else l

        body = abs(c - o)
        if h > swing_h and c < swing_h:
            swept_high = True
        if l < swing_l and c > swing_l:
            swept_low = True

        # displacement bearish → FVG short
        if cfg.allow_short and body >= min_disp and c < o and swept_high:
            if len(pre_h) >= 2:
                gap = pre_h[-1] - l
                if gap >= min_fvg:
                    pending_fvg = {"dir": "short", "top": pre_h[-1], "bot": l, "sl": h + slip}

        # displacement bullish → FVG long
        if cfg.allow_long and body >= min_disp and c > o and swept_low:
            if len(pre_l) >= 2:
                gap = h - pre_l[-1]
                if gap >= min_fvg:
                    pending_fvg = {"dir": "long", "top": h, "bot": pre_l[-1], "sl": l - slip}

        if (
            pending_fvg
            and position is None
            and trades_today < cfg.max_trades_per_day
        ):
            mid = (pending_fvg["top"] + pending_fvg["bot"]) / 2
            d = pending_fvg["dir"]
            if d == "short" and h >= mid and c <= pending_fvg["top"]:
                entry = c
                sl = pending_fvg["sl"]
                tp = entry - (sl - entry) * cfg.tp_ratio
                notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                if notional > 0 and sl > entry > tp:
                    position = {"direction": "short", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                    trades_today += 1
                    pending_fvg = None
            elif d == "long" and l <= mid and c >= pending_fvg["bot"]:
                entry = c
                sl = pending_fvg["sl"]
                tp = entry + (entry - sl) * cfg.tp_ratio
                notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                if notional > 0 and tp > entry > sl:
                    position = {"direction": "long", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                    trades_today += 1
                    pending_fvg = None

        pre_h.append(h)
        pre_l.append(l)
        if len(pre_h) > cfg.pre_lookback:
            pre_h.pop(0)
            pre_l.pop(0)

        if bars_seen % sample == 0:
            worst = l if position and position["direction"] == "long" else h
            snap(ts, worst if position else c)

    if position is not None:
        close_pos(float(df.iloc[-1]["close"]), df.iloc[-1]["timestamp"], "eod")

    metrics = compute_metrics(trades, equity, initial)
    return BacktestResult(
        strategy_id="ict.silver_bullet",
        strategy_name="Silver Bullet",
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


def _empty(cfg: SilverBulletConfig, symbol: str, t0: float) -> BacktestResult:
    return BacktestResult(
        strategy_id="ict.silver_bullet",
        strategy_name="Silver Bullet",
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
