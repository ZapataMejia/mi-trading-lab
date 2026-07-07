"""Liquidity sweep — stop hunt + reclaim (SMC/ICT price action).

Reglas (consenso web prop firms):
- Identificar swing high/low reciente o equal highs/lows
- Precio barre el nivel (wick) y cierra de vuelta dentro → reversal
- SL detrás del extremo del sweep; TP 1.5–3R
"""
from __future__ import annotations

import time as time_lib
from dataclasses import dataclass
from typing import Any

import pandas as pd

from webapp.backend.engine.indicators import adx as _adx, atr_pips as _atr_pips
from webapp.backend.engine.fondeo_engine import _day_key, _hhmm, _in_session, _position_size
from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade


@dataclass
class LiquiditySweepConfig:
    lookback_bars: int = 24
    equal_tolerance_pips: float = 3.0
    sess_start: int = 700
    sess_end: int = 1100
    risk_pct: float = 2.1
    tp_ratio: float = 2.0
    sl_buffer_pips: float = 2.0
    max_trades_per_day: int = 2
    initial_balance: float = 5000.0
    mm_risk_pct: float = 2.1
    broker_utc_offset_hours: int = 7
    pip_size: float = 0.0001
    allow_long: bool = True
    allow_short: bool = True
    equity_sample_bars: int = 12
    # Filtro régimen (ADX/ATR) — 0 = desactivado
    use_regime_filter: bool = False
    adx_period: int = 14
    adx_min: float = 0.0
    adx_max: float = 0.0
    atr_period: int = 14
    min_atr_pips: float = 0.0
    max_atr_pips: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _swing_levels(highs: list[float], lows: list[float], tol: float) -> tuple[float | None, float | None]:
    if len(highs) < 3:
        return None, None
    sh = max(highs)
    sl = min(lows)
    eq_high = sum(1 for x in highs if abs(x - sh) <= tol) >= 2
    eq_low = sum(1 for x in lows if abs(x - sl) <= tol) >= 2
    return (sh if eq_high or True else None), (sl if eq_low or True else None)


def _regime_allows(hist_h: list[float], hist_l: list[float], hist_c: list[float], cfg: LiquiditySweepConfig) -> bool:
    if not cfg.use_regime_filter:
        return True
    adx_val = _adx(hist_h, hist_l, hist_c, cfg.adx_period)
    atr_val = _atr_pips(hist_h, hist_l, hist_c, cfg.atr_period, cfg.pip_size)
    if cfg.adx_min > 0 and adx_val < cfg.adx_min:
        return False
    if cfg.adx_max > 0 and adx_val > cfg.adx_max:
        return False
    if cfg.min_atr_pips > 0 and atr_val < cfg.min_atr_pips:
        return False
    if cfg.max_atr_pips > 0 and atr_val > cfg.max_atr_pips:
        return False
    return True


def run_liquidity_sweep(
    bars: pd.DataFrame,
    cfg: LiquiditySweepConfig,
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
    tol = cfg.equal_tolerance_pips * cfg.pip_size
    slip = cfg.sl_buffer_pips * cfg.pip_size
    risk_frac = cfg.risk_pct / 100.0
    tp_frac = risk_frac * cfg.tp_ratio

    balance = initial
    trades: list[Trade] = []
    equity: list[EquityPoint] = []
    position: dict[str, Any] | None = None
    day_key = -1
    trades_today = 0
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
        entry_f, exit_f, notional_f = float(entry), float(exit_p), float(notional)
        pnl = round(
            notional_f * (exit_f - entry_f) / entry_f
            if d == "long"
            else notional_f * (entry_f - exit_f) / entry_f,
            2,
        )
        balance += pnl
        trades.append(
            Trade(
                timestamp=ts.isoformat(),
                asset=symbol,
                direction=d,
                entry_price=round(entry_f, 5),
                exit_price=round(exit_f, 5),
                stake_usd=round(notional_f, 2),
                cost_paid=round(notional_f, 2),
                pnl=pnl,
                is_winner=pnl > 0,
                bankroll_after=round(balance, 2),
                extra={
                    "reason": reason,
                    "strategy": "liq_sweep",
                    "entry_time": position.get("entry_time", ts.isoformat()),
                    "sl": round(position["sl"], 5),
                    "tp": round(position["tp"], 5),
                },
            )
        )
        position = None
        snap(ts, exit_p)

    h = df["high"].to_numpy(dtype=float)
    lo = df["low"].to_numpy(dtype=float)
    cl = df["close"].to_numpy(dtype=float)
    timestamps = df["timestamp"]
    n = len(df)
    lookback = cfg.lookback_bars

    for i in range(n):
        ts = timestamps.iloc[i]
        hi, lx, cx = float(h[i]), float(lo[i]), float(cl[i])
        bars_seen += 1
        dk = _day_key(ts, offset)
        if dk != day_key:
            day_key = dk
            trades_today = 0

        if position is not None:
            sl, tp = position["sl"], position["tp"]
            d = position["direction"]
            if d == "long":
                if lx <= sl:
                    close_pos(sl, ts, "sl")
                elif hi >= tp:
                    close_pos(tp, ts, "tp")
            else:
                if hi >= sl:
                    close_pos(sl, ts, "sl")
                elif lx <= tp:
                    close_pos(tp, ts, "tp")
            if position and not _in_session(ts, cfg.sess_start, cfg.sess_end, offset):
                close_pos(cx, ts, "session")

        if (
            i >= lookback
            and _in_session(ts, cfg.sess_start, cfg.sess_end, offset)
            and trades_today < cfg.max_trades_per_day
            and position is None
        ):
            win = slice(i - lookback, i)
            swing_high = float(h[win].max())
            swing_low = float(lo[win].min())
            regime_ok = True
            if cfg.use_regime_filter:
                regime_ok = _regime_allows(
                    h[win].tolist(),
                    lo[win].tolist(),
                    cl[win].tolist(),
                    cfg,
                )

            if regime_ok:
                # Sweep high → short
                if cfg.allow_short and hi > swing_high and cx < swing_high:
                    sl = hi + slip
                    entry = cx
                    tp = entry - (sl - entry) * cfg.tp_ratio
                    notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                    if notional > 0 and sl > entry > tp:
                        position = {
                            "direction": "short",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "notional": notional,
                            "entry_time": ts.isoformat(),
                        }
                        trades_today += 1

                # Sweep low → long
                elif cfg.allow_long and lx < swing_low and cx > swing_low:
                    sl = lx - slip
                    entry = cx
                    tp = entry + (entry - sl) * cfg.tp_ratio
                    notional = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                    if notional > 0 and tp > entry > sl:
                        position = {
                            "direction": "long",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "notional": notional,
                            "entry_time": ts.isoformat(),
                        }
                        trades_today += 1

        if bars_seen % sample == 0:
            worst = lx if position and position["direction"] == "long" else hi
            snap(ts, worst if position else cx)

    if position is not None:
        close_pos(float(cl[-1]), timestamps.iloc[-1], "eod")

    metrics = compute_metrics(trades, equity, initial)
    return BacktestResult(
        strategy_id="smc.liq_sweep",
        strategy_name="Liquidity Sweep",
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


def _empty(cfg: LiquiditySweepConfig, symbol: str, t0: float) -> BacktestResult:
    return BacktestResult(
        strategy_id="smc.liq_sweep",
        strategy_name="Liquidity Sweep",
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
