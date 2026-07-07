#!/usr/bin/env python3
"""EMA sin cierre de sesión (solo abre en ventana) — ¿pasa en 30d?"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import (
    FondeoConfig,
    _apply_slippage,
    _day_key,
    _in_session,
    _position_size,
)
from webapp.backend.engine.metrics import compute_metrics
from webapp.backend.engine.types import BacktestResult, EquityPoint, Trade
from webapp.backend.engine.ws_eval import evaluate_ws_classic, simulate_eval_windows
from webapp.backend.markets.forex import _normalize_ohlc

CSV = ROOT / "data/forex_cache/EURUSD_M5.csv"


def run_no_sess_close(bars: pd.DataFrame, cfg: FondeoConfig, symbol: str = "EURUSD") -> BacktestResult:
    """Igual que fondeo pero NO cierra al fin de sesión — solo SL/TP."""
    import time as time_lib

    t0 = time_lib.time()
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    slip = cfg.slippage_pips * cfg.pip_size
    need = max(cfg.fast_period, cfg.slow_period) + 2
    offset = cfg.broker_utc_offset_hours
    initial = float(cfg.initial_balance)
    k_f = 2.0 / (cfg.fast_period + 1.0)
    k_s = 2.0 / (cfg.slow_period + 1.0)
    risk_frac = cfg.risk_pct / 100.0
    tp_frac = risk_frac * cfg.tp_ratio

    ema_fast = ema_slow = float("nan")
    prev_ema_fast = prev_ema_slow = float("nan")
    bars_seen = day_key = trades_today = 0
    balance = initial
    position = None
    trades: list[Trade] = []
    equity: list[EquityPoint] = []

    def snap(ts):
        equity.append(EquityPoint(ts.isoformat(), round(balance, 2), round(balance - initial, 2), len(trades)))

    def close_pos(exit_p, ts, reason):
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
        if position:
            d, sl, tp = position["direction"], position["sl"], position["tp"]
            if d == "long":
                if l <= sl:
                    close_pos(_apply_slippage(sl, "long", "exit", slip), ts, "sl")
                elif h >= tp:
                    close_pos(_apply_slippage(tp, "long", "exit", slip), ts, "tp")
            else:
                if h >= sl:
                    close_pos(_apply_slippage(sl, "short", "exit", slip), ts, "sl")
                elif l <= tp:
                    close_pos(_apply_slippage(tp, "short", "exit", slip), ts, "tp")

        bars_seen += 1
        prev_ema_fast, prev_ema_slow = ema_fast, ema_slow
        if pd.isna(ema_fast):
            ema_fast = ema_slow = c
            continue
        ema_fast = c * k_f + ema_fast * (1 - k_f)
        ema_slow = c * k_s + ema_slow * (1 - k_s)
        if pd.isna(prev_ema_fast):
            continue

        dk = _day_key(ts, offset)
        if dk != day_key:
            day_key, trades_today = dk, 0

        if bars_seen >= need and _in_session(ts, cfg.sess_start, cfg.sess_end, offset) and trades_today < cfg.max_trades_per_day and position is None:
            up = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow
            dn = prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow
            if up and cfg.allow_long:
                sl, tp = c * (1 - risk_frac), c * (1 + tp_frac)
                entry = _apply_slippage(c, "long", "entry", slip)
                n = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                if n > 0:
                    position = {"direction": "long", "entry": entry, "sl": sl, "tp": tp, "notional": n}
                    trades_today += 1
            elif dn and cfg.allow_short:
                sl, tp = c * (1 + risk_frac), c * (1 - tp_frac)
                entry = _apply_slippage(c, "short", "entry", slip)
                n = _position_size(balance, entry, sl, cfg.mm_risk_pct)
                if n > 0 and sl > c:
                    position = {"direction": "short", "entry": entry, "sl": sl, "tp": tp, "notional": n}
                    trades_today += 1

    if position:
        lc = float(df.iloc[-1]["close"])
        close_pos(_apply_slippage(lc, position["direction"], "exit", slip), df.iloc[-1]["timestamp"], "eod")

    m = compute_metrics(trades, equity, initial)
    return BacktestResult(
        "fondeo.no_sess_close", "EMA no session close", "forex",
        df["timestamp"].iloc[0].isoformat(), df["timestamp"].iloc[-1].isoformat(),
        initial, round(balance, 2), round(balance - initial, 2), round((balance - initial) / initial * 100, 2),
        trades, equity, m, cfg.to_dict(), round(time_lib.time() - t0, 4),
    )


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(CSV))
    df = df[(df["timestamp"] >= "2017-01-03") & (df["timestamp"] <= "2022-03-31")]
    emas = [(2, 5), (3, 6), (3, 8), (4, 9), (5, 11), (9, 18)]
    tps = [1.5, 2.0, 2.5, 3.0]
    sessions = [(700, 1100), (700, 1400), (800, 1200)]
    best = []
    for (f, s), tp, (ss, se) in itertools.product(emas, tps, sessions):
        for off in (0, 7):
            cfg = FondeoConfig(f, s, 2.1, tp, ss, se, 2, 5000, 2.1, broker_utc_offset_hours=off, equity_sample_bars=24)
            r = run_no_sess_close(df, cfg)
            if r.metrics["n_trades"] < 15:
                continue
            ev = evaluate_ws_classic(r, cfg)
            w30 = simulate_eval_windows(df, cfg, window_days=30, step="MS")
            if w30.passed > 0:
                best.append({**cfg.to_dict(), "w30": w30.pass_rate_pct, "w30p": w30.passed, "med": w30.median_days_to_meta, "full": ev["checks"]["pass_all"], "pnl": r.total_pnl})
    best.sort(key=lambda x: x["w30"], reverse=True)
    out = ROOT / "data/forex_cache/hunt_no_sess_close_30d.json"
    out.write_text(json.dumps({"top": best[:20], "count": len(best)}, indent=2))
    print(f"No session close: {len(best)} configs con 30d pass>0", flush=True)
    for x in best[:8]:
        print(f"  EMA {x['fast_period']}/{x['slow_period']} TP{x['tp_ratio']} | 30d {x['w30']}% med {x['med']}d", flush=True)


if __name__ == "__main__":
    main()
