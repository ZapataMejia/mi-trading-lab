"""Opening Range Breakout + filtro ADX — consenso prop firms (London/NY, trend only)."""
from __future__ import annotations

import time as time_lib
from dataclasses import dataclass
from typing import Any

import pandas as pd

from webapp.backend.engine.fondeo_engine import _day_key, _hhmm, _in_session, _position_size
from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade


@dataclass
class OrbAdxConfig:
    sess_start: int = 800
    sess_end: int = 1200
    orb_bars: int = 6
    adx_period: int = 14
    adx_min: float = 20.0
    risk_pct: float = 1.0
    tp_range_mult: float = 1.5
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


def _adx(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    if len(closes) < period + 2:
        return 0.0
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        trs.append(tr)
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    n = period
    atr = sum(trs[:n])
    pdm = sum(plus_dm[:n])
    mdm = sum(minus_dm[:n])
    if atr <= 0:
        return 0.0
    for i in range(n, len(trs)):
        atr = atr - atr / n + trs[i]
        pdm = pdm - pdm / n + plus_dm[i]
        mdm = mdm - mdm / n + minus_dm[i]
    if atr <= 0:
        return 0.0
    pdi = 100 * pdm / atr
    mdi = 100 * mdm / atr
    if pdi + mdi <= 0:
        return 0.0
    dx = 100 * abs(pdi - mdi) / (pdi + mdi)
    return dx


def run_orb_adx(
    bars: pd.DataFrame,
    cfg: OrbAdxConfig,
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
    orb_done = False
    orb_high = orb_low = 0.0
    orb_count = 0
    hist_h: list[float] = []
    hist_l: list[float] = []
    hist_c: list[float] = []
    bars_seen = 0
    sample = max(1, cfg.equity_sample_bars)

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
                extra={"reason": reason, "strategy": "orb_adx"},
            )
        )
        position = None
        snap(ts, exit_p)

    for row in df.itertuples(index=False):
        ts, h, l, c = row.timestamp, float(row.high), float(row.low), float(row.close)
        bars_seen += 1
        dk = _day_key(ts, offset)
        in_sess = _in_session(ts, cfg.sess_start, cfg.sess_end, offset)

        if dk != day_key:
            day_key = dk
            trades_today = 0
            orb_done = False
            orb_high = orb_low = 0.0
            orb_count = 0

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
            if position and not in_sess:
                close_pos(c, ts, "session")

        hist_h.append(h)
        hist_l.append(l)
        hist_c.append(c)
        adx_val = _adx(hist_h, hist_l, hist_c, cfg.adx_period)

        if in_sess and not orb_done:
            if orb_count == 0:
                orb_high, orb_low = h, l
            else:
                orb_high = max(orb_high, h)
                orb_low = min(orb_low, l)
            orb_count += 1
            if orb_count >= cfg.orb_bars:
                orb_done = True

        if (
            orb_done
            and in_sess
            and position is None
            and trades_today < cfg.max_trades_per_day
            and adx_val >= cfg.adx_min
            and orb_high > orb_low
        ):
            rng = orb_high - orb_low
            if cfg.allow_long and c > orb_high:
                entry = c
                sl = orb_low - slip
                tp = entry + rng * cfg.tp_range_mult
                notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                if notional > 0 and tp > entry > sl:
                    position = {"direction": "long", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                    trades_today += 1
            elif cfg.allow_short and c < orb_low:
                entry = c
                sl = orb_high + slip
                tp = entry - rng * cfg.tp_range_mult
                notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                if notional > 0 and sl > entry > tp:
                    position = {"direction": "short", "entry": entry, "sl": sl, "tp": tp, "notional": notional}
                    trades_today += 1

        if bars_seen % sample == 0:
            worst = l if position and position["direction"] == "long" else h
            snap(ts, worst if position else c)

    if position is not None:
        close_pos(float(df.iloc[-1]["close"]), df.iloc[-1]["timestamp"], "eod")

    metrics = compute_metrics(trades, equity, initial)
    return BacktestResult(
        strategy_id="prop.orb_adx",
        strategy_name="ORB + ADX",
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


def _empty(cfg: OrbAdxConfig, symbol: str, t0: float) -> BacktestResult:
    return BacktestResult(
        strategy_id="prop.orb_adx",
        strategy_name="ORB + ADX",
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
