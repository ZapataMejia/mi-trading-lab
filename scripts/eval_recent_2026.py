#!/usr/bin/env python3
"""Backtest Liquidity Sweep SAFE en periodo reciente (ej. ene-mar 2026)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from webapp.backend.engine.fondeo_engine import FondeoConfig
from webapp.backend.engine.liquidity_sweep_engine import LiquiditySweepConfig, run_liquidity_sweep
from webapp.backend.engine.ws_eval import evaluate_ws_classic
from webapp.backend.markets.forex import _normalize_ohlc

OUT = ROOT / "data/forex_cache/eval_recent_2026.json"
START = sys.argv[1] if len(sys.argv) > 1 else "2026-01-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2026-03-31"

CFG = LiquiditySweepConfig(
    lookback_bars=36,
    sess_start=700,
    sess_end=1400,
    risk_pct=1.5,
    tp_ratio=1.5,
    sl_buffer_pips=3.0,
    max_trades_per_day=1,
    broker_utc_offset_hours=7,
    mm_risk_pct=1.5,
    equity_sample_bars=12,
)
WS = FondeoConfig(
    risk_pct=1.5,
    max_trades_per_day=1,
    initial_balance=5000,
    broker_utc_offset_hours=7,
    equity_sample_bars=12,
)


def main() -> None:
    df = _normalize_ohlc(pd.read_csv(ROOT / "data/forex_cache/EURUSD_M5.csv"))
    chunk = df[(df["timestamp"] >= START) & (df["timestamp"] <= END + " 23:59:59")].reset_index(drop=True)
    if len(chunk) < 100:
        print(f"ERROR: solo {len(chunk)} barras en {START}→{END}")
        sys.exit(1)

    r = run_liquidity_sweep(chunk, CFG)
    ev = evaluate_ws_classic(r, WS)
    payload = {
        "period": {"start": START, "end": END},
        "bars": len(chunk),
        "data_from": str(chunk["timestamp"].iloc[0]),
        "data_to": str(chunk["timestamp"].iloc[-1]),
        "metrics": r.metrics,
        "total_pnl": round(r.total_pnl, 2),
        "ws_eval": {
            "pass_all": ev["checks"]["pass_all"],
            "checks": ev["checks"],
            "static_dd_pct": ev["static_dd_pct"],
            "max_daily_loss_pct": ev["max_daily_loss_pct"],
            "days_to_meta": ev["days_to_meta"],
            "trading_days": ev.get("trading_days"),
        },
        "trades": [
            {
                "timestamp": t.timestamp,
                "direction": t.direction,
                "pnl": round(t.pnl, 2),
                "entry_price": t.entry_price,
                "extra": t.extra,
            }
            for t in r.trades
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
