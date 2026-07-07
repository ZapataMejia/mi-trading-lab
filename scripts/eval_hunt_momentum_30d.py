#!/usr/bin/env python3
"""Momentum sesión: ruptura primeras N barras + TP amplio — busca pass 30d."""
from __future__ import annotations

import itertools
import json
import sys
import time as time_lib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import _day_key, _hhmm, _in_session, _position_size
from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade
from webapp.backend.engine.ws_eval import evaluate_ws_classic, simulate_eval_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"
OUT = ROOT / "data/forex_cache/hunt_momentum_30d.json"


@dataclass
class MomentumConfig:
    sess_start: int = 700
    sess_end: int = 1000
    risk_pct: float = 2.1
    tp_ratio: float = 2.0
    sl_ratio: float = 1.0
    max_trades_per_day: int = 2
    initial_balance: float = 5000.0
    mm_risk_pct: float = 2.1
    broker_utc_offset_hours: int = 7
    mode: str = "open_drive"  # open_drive | range_break
    lookback_bars: int = 6


def run_momentum(bars: pd.DataFrame, cfg: MomentumConfig, symbol: str = "EURUSD") -> BacktestResult:
    t0 = time_lib.time()
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    off = cfg.broker_utc_offset_hours
    initial = cfg.initial_balance
    risk_frac = cfg.risk_pct / 100.0
    balance = initial
    trades: list[Trade] = []
    equity: list[EquityPoint] = []
    position = None
    day_key = -1
    trades_today = 0
    session_bars: list[float] = []
    session_high = session_low = 0.0
    in_sess_prev = False

    def snap(ts):
        equity.append(EquityPoint(ts.isoformat(), round(balance, 2), round(balance - initial, 2), len(trades)))

    def close(exit_p, ts, reason):
        nonlocal balance, position
        if not position:
            return
        d, entry, n = position["direction"], position["entry"], position["notional"]
        pnl = n * (exit_p - entry) / entry if d == "long" else n * (entry - exit_p) / entry
        balance += pnl
        trades.append(Trade(ts.isoformat(), symbol, d, round(entry, 5), round(exit_p, 5), round(n, 2), round(n, 2), round(pnl, 2), pnl > 0, round(balance, 2), {"reason": reason}))
        position = None
        snap(ts)

    for row in df.itertuples(index=False):
        ts, h, l, c = row.timestamp, float(row.high), float(row.low), float(row.close)
        dk = _day_key(ts, off)
        in_sess = _in_session(ts, cfg.sess_start, cfg.sess_end, off)

        if dk != day_key:
            day_key, trades_today = dk, 0
            session_bars, in_sess_prev = [], False
            session_high, session_low = h, l

        if position:
            sl, tp, d = position["sl"], position["tp"], position["direction"]
            if d == "long":
                if l <= sl:
                    close(sl, ts, "sl")
                elif h >= tp:
                    close(tp, ts, "tp")
            else:
                if h >= sl:
                    close(sl, ts, "sl")
                elif l <= tp:
                    close(tp, ts, "tp")
            if position and not in_sess:
                close(c, ts, "session")

        if in_sess:
            session_high, session_low = max(session_high, h), min(session_low, l)
            session_bars.append(c)

        if (
            in_sess
            and not in_sess_prev
            and len(session_bars) == 1
            and trades_today < cfg.max_trades_per_day
            and position is None
        ):
            pass  # first bar of session — wait for lookback

        if (
            in_sess
            and len(session_bars) >= cfg.lookback_bars
            and trades_today < cfg.max_trades_per_day
            and position is None
        ):
            ref_hi = max(session_bars[-cfg.lookback_bars :])
            ref_lo = min(session_bars[-cfg.lookback_bars :])
            if cfg.mode == "open_drive" and c > ref_hi:
                sl = c * (1 - risk_frac * cfg.sl_ratio)
                tp = c * (1 + risk_frac * cfg.tp_ratio)
                n = _position_size(balance, c, sl, cfg.mm_risk_pct)
                if n > 0:
                    position = {"direction": "long", "entry": c, "sl": sl, "tp": tp, "notional": n}
                    trades_today += 1
            elif cfg.mode == "open_drive" and c < ref_lo:
                sl = c * (1 + risk_frac * cfg.sl_ratio)
                tp = c * (1 - risk_frac * cfg.tp_ratio)
                n = _position_size(balance, c, sl, cfg.mm_risk_pct)
                if n > 0 and sl > c:
                    position = {"direction": "short", "entry": c, "sl": sl, "tp": tp, "notional": n}
                    trades_today += 1

        in_sess_prev = in_sess

    if position:
        close(float(df.iloc[-1]["close"]), df.iloc[-1]["timestamp"], "eod")

    m = compute_metrics(trades, equity, initial)
    return BacktestResult(
        "momentum.session", "Session Momentum", "forex",
        df["timestamp"].iloc[0].isoformat(), df["timestamp"].iloc[-1].isoformat(),
        initial, round(balance, 2), round(balance - initial, 2),
        round((balance - initial) / initial * 100, 2),
        trades, equity, m, cfg.__dict__, round(time_lib.time() - t0, 4),
    )


def main() -> None:
    load = _normalize_ohlc(pd.read_csv(CSV))
    bars = load[(load["timestamp"] >= "2017-01-03") & (load["timestamp"] <= "2022-03-31")]

    grid = []
    for mode, tp, ss, se, off, lb in itertools.product(
        ["open_drive"],
        [1.5, 2.0, 2.5, 3.0],
        [700, 800],
        [1000, 1100, 1200],
        [0, 2, 7],
        [4, 6, 12],
    ):
        grid.append(MomentumConfig(sess_start=ss, sess_end=se, tp_ratio=tp, broker_utc_offset_hours=off, lookback_bars=lb, mode=mode))

    best: list[dict] = []
    for cfg in grid:
        r = run_momentum(bars, cfg)
        if r.metrics["n_trades"] < 20:
            continue
        ev = evaluate_ws_classic(r, cfg)  # type: ignore[arg-type]
        w30 = simulate_eval_windows(bars, cfg, window_days=30, step="MS")  # type: ignore[arg-type]
        if w30.passed > 0 or ev["checks"]["pass_all"]:
            best.append({
                **cfg.__dict__,
                "w30_rate": w30.pass_rate_pct,
                "w30_pass": w30.passed,
                "full_pass": ev["checks"]["pass_all"],
                "full_pnl": r.total_pnl,
                "trades": r.metrics["n_trades"],
                "days_meta": ev["days_to_meta"],
            })

    best.sort(key=lambda x: x["w30_rate"], reverse=True)
    OUT.write_text(json.dumps({"count": len(best), "top": best[:15]}, indent=2), encoding="utf-8")
    print(f"Momentum hunt: {len(best)} con pass 30d>0", flush=True)
    for x in best[:5]:
        print(f"  TP{x['tp_ratio']} {x['sess_start']}-{x['sess_end']} lb{x['lookback_bars']} | 30d {x['w30_rate']}% full={x['full_pass']}", flush=True)


if __name__ == "__main__":
    main()
